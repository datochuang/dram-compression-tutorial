"""Whole-system runs of the interface simulator: clean runs and injected faults, checkers strict."""
import json

import pytest

from lz4sim.config import SMALL
from ifsim.params import Params
from ifsim.system import System

WL = dict(hot_ro_pages=100, hot_rw_pages=200)


def run(n=6000, seed=3, **kw):
    s = System(SMALL, Params(**kw), seed=seed, workload=WL, strict=True)
    s.run(n)
    return s, s.audit()


@pytest.mark.parametrize('mode', ['irq', 'poll'])
@pytest.mark.parametrize('inflight', [1, 4])
def test_clean_run(mode, inflight):
    s, a = run(wait_mode=mode, reclaim_inflight=inflight)
    assert a['violations'] == 0
    assert s.env.results['fault_ro'] > 100 and s.env.results['fault_rw'] > 30
    assert s.mm.st['rw_compress_ok'] > 100
    assert s.drv.st['timeouts'] == 0 and s.hw.st['resets'] == 0
    # every rule with a checker was exercised
    for rid, owner, kind, n, bad in s.chk.summary():
        assert bad == 0
        if kind in ('checker', 'audit'):
            assert n > 0, f'{rid} never evaluated'


def test_same_seed_same_run():
    a, _ = run(n=3000)
    b, _ = run(n=3000)
    assert a.t_end == b.t_end and a.sim.events == b.sim.events and a.mm.lat == b.mm.lat


def test_two_cores_and_small_rings():
    s, a = run(cores=2, job_entries=4, cpl_entries=4, reclaim_inflight=4)
    assert a['violations'] == 0
    assert max(s.drv.occ) <= 3


@pytest.mark.parametrize('mode', ['irq', 'poll'])
def test_hw_hang_reset_and_reissue(mode):
    """FW-RST-1 and HW-RST-1: a job that never completes ends in a soft reset; nothing is lost."""
    s, a = run(wait_mode=mode, hw_hang_jobs=(40, 300), reclaim_inflight=2)
    assert s.hw.st['hung'] == 2 and s.hw.st['resets'] == 2
    assert s.drv.st['timeouts'] >= 2 and s.drv.st['resets'] == 2 and s.drv.st['reissued'] >= 2
    assert a['violations'] == 0 and 'lost' not in a['pages']
    assert max(max(v) for v in s.mm.lat.values()) >= s.p.job_timeout_ns      # the waiting program saw the timeout


def test_dropped_interrupt_is_recovered_without_reset():
    s, a = run(irq_drop_every=50)
    assert s.irq.dropped > 5
    assert s.drv.st['late_completions'] > 0 and s.drv.st['resets'] == 0
    assert a['violations'] == 0


def test_corrupted_stream_is_reported_and_only_that_page_is_lost():
    s, a = run(n=20000, corrupt_every=500)
    assert s.env.injected > 10
    assert s.hw.st['st_BAD_STREAM'] > 0
    assert s.mm.st['lost_rw'] == s.hw.st['st_BAD_STREAM'] == a['pages']['lost']
    assert a['violations'] == 0                                              # AUDIT-3 holds for every other page


@pytest.mark.parametrize('extra', [0, 1])
def test_stream_no_smaller_than_the_page_is_stored_raw(monkeypatch, extra):
    """limit is 4096: a stream of exactly 4096 B, or more, is not stored. The page itself is, with the RAW flag."""
    import ifsim.hw as hwmod
    real = hwmod.compress
    monkeypatch.setattr(hwmod, 'compress', lambda page: (real(page) + bytes(8192))[:4096 + extra])
    s = System(SMALL.with_(rw_raw_store=True), Params(), seed=1, workload=WL, strict=True)
    assert s.mm.limit == 4096
    s.run(4000)
    assert s.audit()['violations'] == 0
    assert s.mm.st['rw_compress_ok'] > 30 and s.mm.st['rw_comp_bytes'] == 4096 * s.mm.st['rw_compress_ok']
    assert s.mm.st['rw_comp_chunks'] == 8 * s.mm.st['rw_compress_ok'] and not s.mm.st['lost_rw']
    assert s.env.results['fault_rw'] > 10              # and they come back


def test_trace_file(tmp_path):
    path = tmp_path / 'trace.jsonl'
    s = System(SMALL, Params(), seed=3, workload=WL, trace_path=str(path))
    s.run(800)
    s.close()
    lines = path.read_text().splitlines()
    assert len(lines) == s.mon.n
    first = json.loads(lines[0])
    assert {'t', 'src', 'ev'} <= set(first)
    kinds = {(json.loads(x)['src'], json.loads(x)['ev']) for x in lines}
    assert {('fw', 'mmio_w'), ('hw', 'reg'), ('hw', 'irq'), ('fw', 'pte'), ('user', 'fault')} <= kinds

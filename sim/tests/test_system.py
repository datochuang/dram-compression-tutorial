import json

import pytest

from lz4sim.config import SMALL
from lz4sim.sim import Simulation, VARIANTS

WL = dict(hot_ro_pages=100, hot_rw_pages=200)


def run(variant, seed=3, accesses=6000, trace=None, **kw):
    sim = Simulation(variant, SMALL, seed=seed, trace_path=trace, workload=dict(WL, **kw.pop('wl', {})), **kw)
    sim.build()
    sim.boot()
    sim.run(accesses)
    sim.audit()
    s = sim.stats()
    sim.close()
    return sim, s


@pytest.mark.parametrize('variant', VARIANTS)
def test_end_to_end(variant, tmp_path):
    trace = tmp_path / 't.jsonl'
    sim, s = run(variant, trace=str(trace))
    assert s['faults_ro'] > 0 and s['faults_rw'] > 0
    assert s['rw_compress_ok'] > 0
    assert s['lost_pages'] == 0 and not s['oom']
    assert s['audit'] == 'ok'
    recs = [json.loads(line) for line in trace.read_text().splitlines()]
    jobs = [r for r in recs if r['ev'] == 'job']
    done = [r for r in recs if r['ev'] == 'done']
    assert len(jobs) == len(done) == s['jobs']
    assert all(j['hex'] for j in jobs)
    assert any(r['ev'] == 'cot' for r in recs)
    if variant == 'baseline':
        assert all(r['who'] == 'hw' for r in recs if r['ev'] == 'cot')
        assert s['stack_pops'] > 0 and s['ctlb_hit'] > 0
    else:
        assert all(r['who'] == 'kernel' for r in recs if r['ev'] == 'cot')
        assert s['bitmap_reserves'] == s['op_COMPRESS']
        assert s['bad_desc'] == 0


def test_both_variants_see_the_same_image_and_workload():
    _, a = run('baseline', seed=5)
    _, b = run('software', seed=5)
    assert a['ro_chunks'] == b['ro_chunks'] and a['ro_raw_pages'] == b['ro_raw_pages']
    assert a['accesses'] == b['accesses'] and a['writes'] == b['writes']


@pytest.mark.parametrize('variant', VARIANTS)
def test_corruption_is_detected(variant):
    _, s = run(variant, corrupt_every=300)
    assert s['injected_corruptions'] > 0
    assert s['lost_pages'] > 0
    assert s['st_BAD_STREAM'] == s['lost_pages']
    assert s['audit'] == 'ok'


@pytest.mark.parametrize('variant', VARIANTS)
def test_raw_store_removes_incompressible_pinning(variant):
    _, s = run(variant, wl=dict(rw_ratio=0.9, rw_sd=0.1))
    assert s['rw_incompressible'] > 0
    sim = Simulation(variant, SMALL.with_(rw_raw_store=True), seed=3, workload=dict(WL, rw_ratio=0.9, rw_sd=0.1))
    sim.build()
    sim.boot()
    sim.run(6000)
    sim.audit()
    r = sim.stats()
    sim.close()
    assert r['rw_incompressible'] == 0 and r['rw_raw_stored'] > 0
    assert r['audit'] == 'ok'

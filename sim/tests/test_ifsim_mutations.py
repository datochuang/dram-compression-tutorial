"""Does each checker catch the bug it is there for?

Every case plants one deliberate bug in the FW model or the HW model (or feeds
the checker a hand-made event) and expects one named rule to fire first.
A checker that never fires proves nothing, so the last test insists that every
rule marked checker or audit has a case here.
"""
import pytest

from lz4sim.config import SMALL
from ifsim.checkers import Violation
from ifsim.params import Params
from ifsim.platform import Ctx
from ifsim.spec import SPEC
from ifsim.system import System

WL = dict(hot_ro_pages=100, hot_rw_pages=200)

# (who carries the bug, name of the bug, rule that must fire)
PLANTED = [
    ('drv', 'bell_first', 'FW-JOB-1'),       # doorbell before the descriptor is written
    ('drv', 'cfg_live', 'FW-CFG-1'),         # config register written while enabled
    ('drv', 'head_ahead', 'FW-CPL-1'),       # CPL_HEAD moved past CPL_TAIL
    ('drv', 'dup_tag', 'FW-JOB-5'),          # tag of a job still out is used again
    ('drv', 'slot_rewrite', 'FW-JOB-3'),     # slot written again after the doorbell
    ('mm', 'pte_early', 'FW-MM-5'),          # PTE made valid before the completion
    ('mm', 'no_pte_inval', 'FW-MM-1'),       # COMPRESS started on a page still mapped
    ('mm', 'cot_keep', 'FW-MM-6'),           # RW page mapped back with its COT entry left valid
    ('mm', 'busy_chunks', 'FW-MM-2'),        # COMPRESS given a chunk that holds another page
    ('mm', 'no_trim', 'AUDIT-1'),            # unused reserved chunks never returned
    ('mm', 'cot_wrong_len', 'FW-MM-3'),      # COT entry differs from the completion
    ('mm', 'decomp_wrong', 'FW-MM-4'),       # DECOMPRESS descriptor differs from the COT entry
    ('hw', 'wrong_tag', 'HW-CPL-1'),         # completion carries another tag
    ('hw', 'stray_write', 'HW-MEM-1'),       # write outside the chunks of the job
    ('hw', 'tail_first', 'HW-CPL-2'),        # CPL_TAIL moved before the completion is in memory
    ('hw', 'bad_data', 'HW-DATA-1'),         # OK reported for a stream that is not the page
    ('hw', 'decomp_bad', 'HW-DATA-2'),       # OK reported for a frame that is not the page
    ('hw', 'irq_stuck', 'HW-IRQ-1'),         # interrupt line not following the ring
    ('hw', 'reread', 'HW-MEM-2'),            # descriptor read a second time
]


# FW-JOB-3 can only fire while a job waits in the ring. With several engines the HW has
# usually fetched the job before the FW gets to rewrite its slot, so this bug runs with one.
ONE_ENGINE_ONLY = {'slot_rewrite'}
CASES = [(w, b, r, n) for w, b, r in PLANTED for n in (1, 4) if n == 1 or b not in ONE_ENGINE_ONLY]


def system(strict=True, **kw):
    kw.setdefault('reclaim_inflight', 2)
    return System(SMALL, Params(**kw), seed=3, workload=WL, strict=strict)


@pytest.mark.parametrize('who,bug,rule,engines', CASES, ids=[f'{b}-{n}' for _, b, _, n in CASES])
def test_planted_bug_is_caught(who, bug, rule, engines):
    s = system(engines=engines)
    getattr(s, who).mut[bug] = 30
    with pytest.raises(Violation) as e:
        s.run(6000)
        s.audit()
    assert e.value.rule == rule, str(e.value)


def test_ring_deeper_than_the_completion_ring():
    """FW-JOB-4: more jobs out than the completion ring can hold."""
    s = system(cpl_entries=4, reclaim_inflight=8)
    s.drv.slots.cap = 15                      # the bug: depth taken from the job ring only
    with pytest.raises(Violation) as e:
        s.run(6000)
    assert e.value.rule == 'FW-JOB-4'


# ---- directed cases: hand-made events straight into the checker
def booted(strict=True, **kw):
    s = system(strict, **kw)
    s.sim.run(stop=s.sim.process(s.drv.init(Ctx(s.sim, 'boot')), 'init'))
    s.mm.emit_boot()
    return s


def fw(s, ev, **kw):
    s.chk.on(s.sim.now, 'fw', ev, kw)


def put_job(s, slot, tag, h, frame, chunks):
    d = dict(opcode=SPEC.enum['opcode'].COMPRESS, count=len(chunks), limit=3072, frame_pa=frame, tag=tag, chunk=chunks)
    pa = s.drv.job_base + slot * 64
    s.dram.write(pa, SPEC.pack('job_desc', d))
    fw(s, 'job', tag=tag, h=h, op=d['opcode'])
    fw(s, 'mem_w', pa=pa, n=48, what='job_slot')


def test_illegal_ring_configuration():
    s = system()
    for name, val in (('JOB_BASE', 0x8000_0000), ('JOB_SIZE', 12), ('CPL_BASE', 0x8000_1000), ('CPL_SIZE', 16)):
        fw(s, 'mmio_w', reg=name, val=val)
    with pytest.raises(Violation) as e:
        fw(s, 'mmio_w', reg='CTRL', val=1)
    assert e.value.rule == 'FW-CFG-2'


def test_completion_ring_must_start_on_a_cache_line():
    """The HW accepts CPL_BASE on any completion slot. The FW rule is stricter, for FW-CACHE-5."""
    s = system()
    assert s.drv.cpl_base % SPEC.const.RING_ALIGN == 0 and s.drv.job_base % SPEC.const.RING_ALIGN == 0
    pool = (('POOL_BASE', s.cfg.pool_base), ('POOL_CHUNKS', s.cfg.pool_chunks))
    for off, legal in ((SPEC.const.RING_ALIGN, True), (SPEC.const.CPL_SLOT_SIZE, False)):
        s = system()
        for name, val in (('JOB_BASE', s.drv.job_base), ('JOB_SIZE', 16), ('CPL_BASE', s.drv.cpl_base + off),
                          ('CPL_SIZE', 16)) + pool:
            fw(s, 'mmio_w', reg=name, val=val)
        if legal:
            fw(s, 'mmio_w', reg='CTRL', val=1)
        else:
            with pytest.raises(Violation) as e:
                fw(s, 'mmio_w', reg='CTRL', val=1)
            assert e.value.rule == 'FW-CFG-2'


def test_ring_inside_the_chunk_pool():
    s = system()
    for name, val in (('JOB_BASE', s.cfg.pool_base), ('JOB_SIZE', 16), ('CPL_BASE', s.drv.cpl_base), ('CPL_SIZE', 16),
                      ('POOL_BASE', s.cfg.pool_base), ('POOL_CHUNKS', s.cfg.pool_chunks)):
        fw(s, 'mmio_w', reg=name, val=val)
    with pytest.raises(Violation) as e:
        fw(s, 'mmio_w', reg='CTRL', val=1)
    assert e.value.rule == 'FW-CFG-2'


@pytest.mark.parametrize('val', [16, 99])
def test_doorbell_out_of_range(val):
    s = booted()
    with pytest.raises(Violation) as e:
        fw(s, 'mmio_w', reg='JOB_TAIL', val=val)
    assert e.value.rule == 'FW-JOB-2'


def test_doorbell_overruns_the_ring():
    s = booted(strict=False)
    free = [s.cfg.frame_pa(f) for f in s.mm.free_frames][:16]
    for i in range(15):
        put_job(s, i, 100 + i, None, free[i % len(free)], ())
    fw(s, 'mmio_w', reg='JOB_TAIL', val=15)            # 15 of 16 slots: allowed
    assert not s.chk.nviol['FW-JOB-2']
    put_job(s, 15, 200, None, free[0], ())
    fw(s, 'mmio_w', reg='JOB_TAIL', val=0)             # the 16th: head would look like tail
    assert s.chk.nviol['FW-JOB-2'] == 1


def test_two_jobs_on_one_frame():
    s = booted()
    frame = s.cfg.frame_pa(s.mm.free_frames[0])
    free = sorted(s.mm.bitmap.enumerate_free())
    put_job(s, 0, 100, 5, frame, free[:6])
    put_job(s, 1, 101, 6, frame, free[6:12])
    with pytest.raises(Violation) as e:
        fw(s, 'mmio_w', reg='JOB_TAIL', val=2)
    assert e.value.rule == 'FW-JOB-6'


def test_ro_cot_entry_written_at_run_time():
    s = booted()
    h = next(h for h in range(s.cfg.pages) if s.cfg.is_ro(h))
    with pytest.raises(Violation) as e:
        fw(s, 'mem_w', pa=s.cfg.entry_pa(h), n=32, what='cot')
    assert e.value.rule == 'FW-MM-7'


def test_completion_ring_overrun():
    s = booted(strict=False)
    for i in range(1, 17):
        s.chk.on(0, 'hw', 'reg', dict(reg='CPL_TAIL', val=i % 16))
    assert s.chk.nviol['HW-CPL-3'] == 1                # only the 16th step lands on CPL_HEAD


# ---- several jobs in the HW at once (CAP.ENGINES)
def hw(s, ev, **kw):
    s.chk.on(s.sim.now, 'hw', ev, kw)


def hand_over(s, jobs):
    """jobs: [(tag, page, frame number, chunks)], all COMPRESS. Written to the ring and handed over with one doorbell."""
    for i, (tag, h, f, chunks) in enumerate(jobs):
        put_job(s, i, tag, h, s.cfg.frame_pa(f), chunks)
    fw(s, 'mmio_w', reg='JOB_TAIL', val=len(jobs))


def fetch(s, slot):
    hw(s, 'mem_r', pa=s.drv.job_base + slot * 64, n=48)
    hw(s, 'reg', reg='JOB_HEAD', val=slot + 1)


def post(s, slot, tag, status):
    pa = s.drv.cpl_base + slot * 16
    s.dram.write(pa, SPEC.pack('completion', dict(status=status, flags=0, length=0, checksum=0, tag=tag, aux=0)))
    hw(s, 'mem_w', pa=pa, n=16)
    hw(s, 'reg', reg='CPL_TAIL', val=slot + 1)
    hw(s, 'irq', level=1)


def three_jobs(s):
    frames = s.mm.free_frames[:3]
    free = sorted(s.mm.bitmap.enumerate_free())
    return [(100 + i, None, frames[i], free[6 * i:6 * i + 6]) for i in range(3)]


def test_checker_takes_the_engine_count_from_cap():
    for n in (1, 2, 4):
        s = system(engines=n)
        assert s.chk.engines == n == SPEC.get('CAP', 'ENGINES', s.hw.mmio_read(SPEC.off['CAP']))


def test_fetch_with_every_engine_holding_a_job():
    """HW-MEM-2: the HW takes a job only when an engine is idle."""
    s = booted(engines=2)
    hand_over(s, three_jobs(s))
    fetch(s, 0)
    fetch(s, 1)                                        # two engines, two jobs: allowed
    hw(s, 'mem_r', pa=s.drv.job_base + 2 * 64, n=48)
    with pytest.raises(Violation) as e:
        hw(s, 'reg', reg='JOB_HEAD', val=3)
    assert e.value.rule == 'HW-MEM-2'


def test_completions_in_another_order_than_the_fetches():
    """HW-CPL-1: the completion names a job the HW holds, whichever was fetched first."""
    s = booted(engines=2)
    hand_over(s, three_jobs(s))
    fetch(s, 0)
    fetch(s, 1)
    post(s, 0, 101, SPEC.enum['status'].INCOMPRESSIBLE)        # the second job ends first
    fetch(s, 2)                                                # so an engine is idle again
    post(s, 1, 100, SPEC.enum['status'].INCOMPRESSIBLE)
    assert not s.chk.nviol and s.chk.cov['HW-CPL-1'] == 2
    with pytest.raises(Violation) as e:
        post(s, 2, 101, SPEC.enum['status'].INCOMPRESSIBLE)    # that job already has its completion
    assert e.value.rule == 'HW-CPL-1'


def test_burst_is_checked_against_every_job_in_the_hw():
    """HW-MEM-1 with several engines. A burst has no engine number, so the checker asks that it lies
    inside some job the HW holds. A write into ANOTHER job's chunk therefore passes: a known limit."""
    s = booted(engines=2)
    jobs = three_jobs(s)
    hand_over(s, jobs)
    fetch(s, 0)
    fetch(s, 1)
    chunk = lambda j, k=0: s.cfg.chunk_pa(jobs[j][3][k])
    hw(s, 'mem_r', pa=s.cfg.frame_pa(jobs[1][2]), n=256)       # job 1 reads its frame while job 0 is older
    hw(s, 'mem_w', pa=chunk(1), n=256)
    hw(s, 'mem_w', pa=chunk(0, 5), n=8)                        # whichever engine wrote this, it is accepted
    assert not s.chk.nviol
    with pytest.raises(Violation) as e:
        hw(s, 'mem_w', pa=chunk(2), n=8)                       # job 2 is still in the ring: nobody may write there
    assert e.value.rule == 'HW-MEM-1'


def test_audit_catches_a_frame_owned_twice():
    s = system(strict=False)
    s.run(3000)
    assert s.audit()['violations'] == 0
    s.mm.free_frames.append(s.mm.frame_of[next(iter(s.mm.lru))])
    s.audit()
    assert s.chk.nviol['AUDIT-2'] == 1


def test_audit_catches_wrong_page_contents():
    s = system(strict=False)
    s.run(3000)
    h = next(iter(s.mm.lru))
    s.dram.view(s.cfg.frame_pa(s.mm.frame_of[h]), 4096)[100] ^= 0x55
    s.audit()
    assert s.chk.nviol['AUDIT-3'] == 1


def test_audit_catches_work_left_over():
    s = system(strict=False)
    s.run(3000)
    s.mm.inflight = 1
    s.audit()
    assert s.chk.nviol['AUDIT-4'] == 1


DIRECTED = {'FW-JOB-4', 'FW-CFG-2', 'FW-JOB-2', 'FW-JOB-6', 'FW-MM-7', 'HW-CPL-3', 'AUDIT-2', 'AUDIT-3', 'AUDIT-4'}


def test_every_checker_has_a_case_that_makes_it_fire():
    covered = {rule for _, _, rule in PLANTED} | DIRECTED
    need = {rid for rid, r in SPEC.rules.items() if r['check'] in ('checker', 'audit')}
    assert need <= covered, f'no negative test for {sorted(need - covered)}'

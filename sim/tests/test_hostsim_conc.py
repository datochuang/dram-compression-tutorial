"""Host simulation with several threads: the same hostsim/kernel.py under a deterministic scheduler."""
import pytest

from hostsim import conc
from hostsim.cache import CacheError
from hostsim.check import AuditError
from hostsim.kernel import LOST, PRESENT, FaultNotAllowed, KernelBug, OutOfMemory
from hostsim.machine import NoProgress

# what stops each mutant, and a word that must be in the message
STOPPED_BY = {
    'shared_tag': (KernelBug, 'completion tag'),
    'no_wake_frame': (conc.Deadlock, 'waits for frame'),
    'no_wake_page': (conc.Deadlock, "waits for ('page'"),
    'wait_not_atomic': (conc.Deadlock, 'waits for'),
    'unlatched_reclaimer': (conc.Deadlock, 'waits for frame'),
    'no_decompressing': (conc.JobRace, 'two jobs at once'),
    'no_compressing': (FaultNotAllowed, 'cannot be served'),
    'local_tlb_flush': (conc.StaleTlb, 'still translates'),
    'no_cache_clean': (CacheError, 'C1'),
    'no_cache_invalidate': (CacheError, 'C3'),
    'invalidate_dcache_only': (CacheError, 'C3: the CPU runs'),
    'forget_pin': (FaultNotAllowed, 'cannot be served'),
    'protect_1': (NoProgress, 'faulted'),
    'too_few_frames': (OutOfMemory, 'waits for frame'),
    'no_sw_decode': (AuditError, 'A7'),
    'sw_decode_no_clean': (CacheError, 'C3: the CPU runs'),
    'leak_on_job_failure': (AuditError, 'A2'),
    'kill_in_kernel': (AuditError, 'with no job in flight'),
    'no_boot_flush': (CacheError, 'C2'),
    'chunk_read_cached': (CacheError, 'C3: the CPU reads chunk'),
}


def booted(seed=1, cfg=conc.TINY, **kw):
    m = conc.ConcMachine(cfg, seed=seed, chooser=None, **kw)
    m.build_image()
    m.boot()
    return m


@pytest.fixture(scope='module')
def seen():
    """What happened in 80 random schedules of the kernel as it is. Each one ended with the audit."""
    return conc.survey(80)


# ------------------------------------------------------------------ the kernel as it is
def test_random_schedules_end_clean_and_take_every_path(seen):
    assert seen['schedules'] == 80
    for path in ('first_touch', 'fault_ro', 'fault_rw', 'spurious', 'wait_page_compressing',
                 'wait_page_decompressing', 'wait_frame', 'pin_page', 'cache_clean', 'cache_invalidate'):
        assert seen.get(path, 0) > 0, path
    assert seen['pin_page'] == seen['unpin_page']
    assert seen['jobs_queued_max'] >= 2                     # jobs of two threads were in flight together
    assert seen['streams_checked'] > 0
    assert not seen.get('lost') and not seen.get('threads_ended_lost')


def test_same_seed_same_schedule():
    a, b = conc.one(5), conc.one(5)
    assert a.sched.steps == b.sched.steps and a.kinds == b.kinds
    assert a.kernel.state == b.kernel.state and a.hw.st == b.hw.st
    assert conc.one(6).sched.steps != a.sched.steps


def test_every_schedule_with_one_interruption_ends_clean():
    assert conc.explore(1, seed=1, users=2, length=8) > 50


def test_every_schedule_with_two_interruptions_ends_clean():
    assert conc.explore(2, seed=2, users=2, length=4) > 200


def test_a_damaged_stream_ends_only_the_threads_that_touch_it():
    n = conc.survey(40, damage=0.05)
    assert n['injected'] > 0 and n['lost'] > 0
    assert 0 < n['threads_ended_lost'] <= 3 * 40
    assert n['instructions'] > 0 and n['streams_checked'] > 0


def test_lost_page_is_handed_to_every_thread_that_waits_for_it():
    m = conc.one(1, damage=0.05)
    seeds = 1
    while not any(s == LOST for s in m.kernel.state):
        seeds += 1
        m = conc.one(seeds, damage=0.05)
    assert 'lost' in m.ended.values()
    assert m.result['streams_checked'] > 0                  # the audit ran with the lost page in place


def test_failing_jobs_and_an_ended_thread_lose_nothing():
    n = conc.survey(60, faults=2, kill=True)
    assert n['COMPRESS_BUS_ERROR'] and n['DECOMPRESS_BUS_ERROR'] and n['DECOMPRESS_BAD_STREAM']
    assert n['sw_decode'] == n['sw_decode_ok'] == n['DECOMPRESS_BUS_ERROR'] + n['DECOMPRESS_BAD_STREAM']
    assert n['compress_failed'] == n['COMPRESS_BUS_ERROR']
    assert not n.get('lost') and not n.get('threads_ended_lost') and not n.get('lz4_off')
    assert 0 < n['threads_ended_killed'] <= n['kills'] <= 60


def test_without_the_lz4_hw_every_stored_page_still_comes_back():
    """Enough frames for every RW page: the run ends, and RO pages keep going out and coming back."""
    n = conc.survey(40, hw_down=True, cfg=conc.ROOMY)
    assert n['lz4_off'] > 30 and n['no_answer'] >= n['lz4_off']
    assert n['sw_decode'] == n['sw_decode_ok'] > n['lz4_off']
    assert n['evict_ro'] > 0 and not n.get('lost')


def test_without_the_lz4_hw_the_usual_machine_runs_out_of_frames():
    ends = []
    for seed in range(1, 21):
        try:
            conc.one(seed, hw_down=True)
            ends.append('done')
        except OutOfMemory:
            ends.append('out of memory')                  # and nothing else: no deadlock, no audit error
    assert ends.count('out of memory') > 10


# ------------------------------------------------------------------ the checks do catch things
def test_table_of_mutants_is_complete():
    assert set(STOPPED_BY) == set(conc.MUTANTS)


@pytest.mark.parametrize('name', sorted(conc.MUTANTS))
def test_mutant_is_stopped(name):
    kind, word = STOPPED_BY[name]
    hit = conc.first_failure(name, runs=60)
    assert hit, f'{name}: no check stopped it'
    seed, e = hit
    assert isinstance(e, kind), f'{name}: stopped by {type(e).__name__}: {e}'
    assert word in str(e)


def test_mutant_settings_are_clean_with_the_real_kernel():
    """The two mutants that change the machine, not the kernel, fail for the reason given and no other."""
    for seed in range(1, 11):
        conc.one(seed, cfg=conc.TIGHT, users=1, pin=False, reclaimer_first=True)      # protect 2: runs
        conc.one(seed, reclaimer_first=True)                                          # the usual machine
    with pytest.raises(NoProgress):
        conc.one(1, cfg=conc.TIGHT, users=1, pin=False, reclaimer_first=True, protect=1)
    with pytest.raises(OutOfMemory):
        conc.one(1, cfg=conc.TIGHT, users=2, pin=False)
    for name in ('no_sw_decode', 'sw_decode_no_clean', 'leak_on_job_failure', 'kill_in_kernel', 'no_boot_flush',
                 'chunk_read_cached'):                    # failing jobs, an ended thread, verify: clean with the real kernel
        kw = {k: v for k, v in conc.MUTANTS[name].items() if k not in ('change', 'prepare')}
        for seed in range(1, 31):
            conc.one(seed, **kw)


# ------------------------------------------------------------------ contexts and pins
@pytest.mark.parametrize('context', ('isr', 'hrt'))
def test_fault_where_nobody_can_wait_is_reported(context):
    m = booted()
    code = m.cfg.ro_first + 1                               # stored in the chunk pool since boot
    with pytest.raises(FaultNotAllowed) as e:
        m.go([[('context', context), ('run', code, None, False)]])
    assert f'{code:#x}' in str(e.value)


def test_same_access_from_a_thread_is_served():
    m = booted()
    code = m.cfg.ro_first + 1
    m.go([[('run', code, None, False)]])
    assert m.kinds['fault_ro'] == 1 and m.ended == {'user0': 'done'}


def test_pinned_page_stays_while_the_others_churn():
    """user0 pins a page and goes on; two other threads use every frame. An ISR can still reach the page."""
    m = booted(seed=3)
    h = 1
    busy = conc.scripts(m.cfg, 3, users=3, length=40, pin=False)
    driver = [('pin', h)] + busy[0] + [('isr', h, True), ('alias', h, True), ('unpin', h)]
    seen_states = []
    real = m.kernel.pick_victim

    def pick():
        v = real()
        seen_states.append((v, m.kernel.state[h], m.kernel.pins[h]))
        return v
    m.kernel.pick_victim = pick
    m.go([driver, busy[1], busy[2]])
    pinned = [(v, s) for v, s, pins in seen_states if pins]
    assert len(pinned) > 20
    assert all(v != h and s == PRESENT for v, s in pinned)
    assert m.kernel.pins[h] == 0 and m.ended['user0'] == 'done'


def test_unpin_without_pin_is_a_kernel_bug():
    m = booted()
    with pytest.raises(KernelBug):
        m.go([[('run', m.cfg.ro_first, 0, True), ('unpin', 0)]])


def test_thread_that_ends_gives_up_its_protection():
    m = conc.one(4)
    assert not m.kernel.fresh and not any(m.kernel.fresh_n) and not any(m.kernel.pins)


def test_frames_needed_follow_the_sizing_rule():
    """frames > threads x protect + pinned pages. Three frames carry one thread, not two."""
    assert conc.TIGHT.frames == 3
    conc.one(1, cfg=conc.TIGHT, users=1, pin=False)          # 3 > 1 x 2
    with pytest.raises(OutOfMemory):
        conc.one(1, cfg=conc.TIGHT, users=2, pin=False)      # 3 > 2 x 2 does not hold

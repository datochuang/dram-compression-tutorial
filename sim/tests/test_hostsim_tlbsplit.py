"""Option conc.SplitTlb: TLB refill and TLB clearing in steps, with one example scheme of clear requests.

The scheme is a model experiment, not the platform's mechanism (which is not known). Each failure test
pins one interleaving the experiment found; the seeds are deterministic.
"""
import pytest

from hostsim import conc, tlbsplit
from hostsim.conc import SplitTlb


def fail(seed, o, **kw):
    try:
        conc.one(seed, tlb=o, **kw)
    except Exception as e:
        return e
    return None


def story(e):
    """(task, what) of the TLB events behind a failure, as tlbsplit prints them."""
    return [(who, text) for _, who, text in tlbsplit.story(e)]


def ordered(events, *steps):
    """Each (task, text) of steps appears in events, in this order."""
    i = 0
    for who, text in events:
        if i < len(steps) and who == steps[i][0] and steps[i][1] in text:
            i += 1
    return i == len(steps)


# ------------------------------------------------------------------ off by default
def test_off_by_default_nothing_changes():
    m = conc.one(3)
    assert m.split is None and not m.events and not m.targets
    assert all(t.ready_if is None for t in m.sched.tasks)
    assert 'refills' not in m.port.st and 'clear_requests' not in m.port.st


# ------------------------------------------------------------------ schemes that hold
SAFE = [SplitTlb(delivery='thread', lock_wait_irq=True, refill_irq=False),
        SplitTlb(delivery='core', refill_locked=True, isr_irq=True),
        SplitTlb(delivery='thread', refill_locked=True, isr_irq=True)]


@pytest.mark.parametrize('o', SAFE, ids=lambda o: o.label())
def test_scheme_holds_under_random_and_explored_schedules(o):
    seen = 0
    for seed in range(1, 31):
        for users in (2, 3):
            m = conc.one(seed, tlb=o, users=users)
            seen += m.port.st['clear_requests']
        conc.one(seed, tlb=o, users=4, chooser=tlbsplit.WideWindows(seed))
    assert seen > 0
    assert conc.explore(1, tlb=o, seed=1, users=2, length=8) > 100


def test_entries_are_used_while_their_clearing_goes_on():
    """The allowance in translate_split is exercised: such uses happen and nothing goes wrong."""
    n = sum(conc.one(seed, tlb=SAFE[0], users=3).port.st['tlb_use_while_clearing'] for seed in range(1, 41))
    assert n > 0


# ------------------------------------------------------------------ the check still catches things
def test_split_mode_still_catches_a_missing_clear():
    def no_requests(m):
        m.port.shootdown = False
    for seed in range(1, 41):
        try:
            conc.one(seed, tlb=SAFE[0], change=no_requests)
        except conc.StaleTlb as e:
            assert 'still translates' in str(e)
            return
    pytest.fail('no StaleTlb without clear requests')


# ------------------------------------------------------------------ the failures found
def test_sibling_of_the_initiator_writes_a_stale_entry_late():
    """Per-core requests: the initiator's own core is cleared locally, which does not stop a refill that
    its sibling hardware thread is in the middle of."""
    e = fail(1, SplitTlb(delivery='core', refill_irq=False), users=2)
    assert isinstance(e, conc.StaleTlb)
    assert ordered(story(e), ('user1', 'refill A'), ('reclaimer', 'invalid, own core 1'),
                   ('reclaimer', 'every target acknowledged'), ('user1', 'refill B'), ('user1', 'STALE'))


def test_one_thread_refills_while_its_sibling_takes_the_request():
    """Per-core requests, refill not interruptible: the other hardware thread of the core takes the request."""
    e = fail(1, SplitTlb(delivery='core', refill_irq=False), users=3)
    assert isinstance(e, conc.StaleTlb)
    assert ordered(story(e), ('user2', 'refill A'), ('reclaimer', 'invalid'), ('clear@core0', 'taken by user0'),
                   ('reclaimer', 'every target acknowledged'), ('user2', 'refill B'), ('user2', 'STALE'))


def test_thread_takes_the_request_in_the_middle_of_its_own_refill():
    e = fail(13, SplitTlb(delivery='thread', refill_irq=True), users=3)
    assert isinstance(e, conc.StaleTlb)
    assert ordered(story(e), ('user2', 'refill A'), ('reclaimer', 'invalid'), ('clear@hwt user2', 'taken by user2'),
                   ('reclaimer', 'every target acknowledged'), ('user2', 'refill B'), ('user2', 'STALE'))


@pytest.mark.parametrize('delivery', ('core', 'thread'))
def test_interrupts_off_while_waiting_for_the_lock_deadlock(delivery):
    with pytest.raises(conc.Deadlock) as e:
        conc.explore(1, tlb=SplitTlb(delivery=delivery, lock_wait_irq=False, refill_irq=False), seed=1, users=2, length=8)
    assert 'holds mm_lock and waits for the clear' in str(e.value)
    assert 'waits for mm_lock with interrupts off' in str(e.value)


def test_recheck_leaves_a_window_for_the_sibling():
    """Fix 'recheck': between writing the entry (B) and reading the PTE again (C) the other hardware thread
    of the core can use the entry."""
    e = fail(95, SplitTlb(delivery='core', recheck=True), users=3, chooser=tlbsplit.WideWindows(95))
    assert isinstance(e, conc.StaleTlb)
    ev = story(e)
    assert ordered(ev, ('user0', 'refill A'), ('reclaimer', 'every target acknowledged'), ('user0', 'refill B'),
                   ('user2', 'STALE'))
    assert not any('refill C' in text for _, text in ev)


def test_recheck_with_requests_per_thread_still_has_the_window():
    e = fail(32, SplitTlb(delivery='thread', refill_irq=True, recheck=True), users=4, chooser=tlbsplit.WideWindows(32))
    assert isinstance(e, conc.StaleTlb)


def test_refill_under_the_lock_in_an_isr_deadlocks():
    """Fix 'refill_locked': an ISR that misses in the TLB waits for mm_lock with interrupts off."""
    e = fail(12, SplitTlb(delivery='core', refill_locked=True, isr_irq=False), users=2)
    assert isinstance(e, conc.Deadlock) and 'is in an ISR' in str(e)


def test_refill_under_the_lock_with_interrupts_off_deadlocks():
    e = fail(1, SplitTlb(delivery='core', refill_locked=True, lock_wait_irq=False, isr_irq=True), users=2)
    assert isinstance(e, conc.Deadlock) and 'interrupts off' in str(e)

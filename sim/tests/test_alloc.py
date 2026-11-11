import random

import pytest

from lz4sim.config import SMALL
from lz4sim.dram import DRAM
from lz4sim.trace import Trace
from lz4sim.alloc_stack import HwFreeStack
from lz4sim.alloc_bitmap import KernelBitmap, DoubleFree, DoubleAllocation


def test_stack_init_pop_push_roundtrip():
    cfg = SMALL
    st = HwFreeStack(cfg, DRAM(cfg), Trace())
    first = 1000
    free = st.init(first)
    assert free == cfg.pool_chunks - first == st.free_count()
    assert st.enumerate_free() == set(range(first, cfg.pool_chunks))
    popped = []
    while True:
        c = st.pop()
        if c is None:
            break
        popped.append(c)
    assert sorted(popped) == list(range(first, cfg.pool_chunks))
    assert st.free_count() == 0
    assert st.st['refills'] > 0
    for c in popped:
        st.push(c)
    assert st.free_count() == free
    assert st.enumerate_free() == set(range(first, cfg.pool_chunks))
    assert st.st['spills'] > 0


def test_stack_sram_stays_within_thresholds():
    cfg = SMALL
    st = HwFreeStack(cfg, DRAM(cfg), Trace())
    st.init(500)
    rng = random.Random(0)
    held = []
    for _ in range(20000):
        if held and rng.random() < 0.5:
            st.push(held.pop())
        else:
            c = st.pop()
            if c is not None:
                held.append(c)
        assert len(st.sram) <= cfg.sram_cap
    assert st.free_count() + len(held) == cfg.pool_chunks - 500
    assert st.enumerate_free().isdisjoint(held)


def test_bitmap_reserve_release_and_checks():
    cfg = SMALL
    bm = KernelBitmap(cfg, Trace())
    assert bm.free == cfg.pool_chunks
    r = bm.reserve(7)
    assert r == list(range(7))
    bm.release(r[5:], op='trim')
    assert bm.free == cfg.pool_chunks - 5
    with pytest.raises(DoubleFree):
        bm.release([6])
    with pytest.raises(DoubleAllocation):
        bm.mark_used(0)
    rest = bm.reserve(bm.free)
    assert bm.free == 0 and bm.reserve(1) is None
    assert bm.enumerate_free() == set()
    bm.release(rest)
    assert bm.enumerate_free() == set(range(5, cfg.pool_chunks))


def test_bitmap_cursor_skips_full_words():
    cfg = SMALL
    bm = KernelBitmap(cfg, Trace())
    for c in range(6400):
        bm.mark_used(c)
    assert bm.reserve(1) == [6400]
    assert bm.st['words_scanned'] == 101     # 100 all-ones words skipped, then one word examined
    assert bm.reserve(1) == [6401]
    assert bm.st['words_scanned'] == 102     # the cursor stayed on the same word

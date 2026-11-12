"""The step detail (hostsim/micro.py): tables, operations, instruction counts, and the document made from them."""
import json
import os
import re

import pytest

from hostsim import deps, micro, micro_doc
from lz4sim import kernel


@pytest.fixture(scope='module')
def nums():
    with open(os.path.join(micro_doc.SPEC_DIR, micro_doc.NUMBERS), encoding='utf-8') as f:
        return json.load(f)


def test_every_step_has_a_detail_and_it_agrees_with_the_dependency_declaration():
    assert set(micro.DETAIL) == set(deps.STEPS)
    assert micro.check() == []


def test_every_access_names_a_table_of_the_layout():
    names = {r['name'] for r in micro.layout()}
    for step, d in {**micro.DETAIL, **micro.LOCK}.items():
        for a in d.acc:
            assert a[0] in names, (step, a[0])


def test_layout_fits_the_memory_map():
    z = micro.sizes()
    rows = {r['name']: r for r in micro.layout()}
    assert rows['cot']['base'] == z['cot_base'] and rows['cot']['bytes'] <= z['pool_base'] - z['cot_base']
    assert rows['chunk']['base'] == z['pool_base'] and rows['chunk']['bytes'] == z['fc_base'] - z['pool_base']
    assert rows['frame']['base'] == z['fc_base'] and rows['frame']['bytes'] == z['dram_end'] - z['fc_base']
    kmem = sum(r['bytes'] for r in rows.values() if r['where'] in ('kmem', 'pt', 'ring'))
    assert kmem < z['hrt_base'] - z['pinned_base']


def test_c_reference_numbers_the_states_as_the_kernel_does():
    with open(os.path.join(micro.KSTEP, 'kstep.h'), encoding='utf-8') as f:
        m = re.search(r'enum \{ (S_COMPRESSED[^}]*) \};', f.read())
    names = [x.strip() for x in m.group(1).split(',')]
    assert [getattr(kernel, n) for n in names] == list(range(6))


def test_stored_measurement_covers_every_key_and_the_calibration_holds(nums):
    S = nums['measure']['steps']
    assert S['calib5']['instr'] == 5
    for step, d in {**micro.DETAIL, **micro.LOCK}.items():
        if d.key:
            assert d.key in S, step
    for case in deps.CASES:
        for step in deps.CASES[case].split() if isinstance(deps.CASES[case], str) else deps.CASES[case]:
            d = micro.LOCK.get(step) or micro.DETAIL[step]
            assert (micro.instr(step, nums['measure'], case) is not None) == bool(d.key), (case, step)


def test_walk_lists_only_true_predecessors_and_counts_a_line_once(nums):
    w = micro_doc.weights()
    for case in deps.CASES:
        rows = micro.walk(case, nums['measure'], w)
        red = deps.reduced(case)
        for r in rows:
            if r['step'] in micro.LOCK:
                continue
            assert {a for _, a, _, _, _ in r['after']} == {a for (a, b) in red if b == r['step']}, (case, r['step'])
        t = micro.totals(rows)
        miss = micro.MODEL['miss']
        assert t['lo'] == round(t['instr'] * micro.MODEL['cpi']) + t['mmio'] * micro.MODEL['mmio'] + t['dram'] * miss
        assert t['hi'] == t['lo'] + (t['new'] - t['dram']) * miss
        # the completion entry is written by the LZ4 HW: reading it is a miss in the low bound as well
        cpl = [r for r in rows if r['step'] == 'cpl_read']
        assert t['dram'] == len(cpl) and all(r['lo'] == r['hi'] for r in cpl)
    # the frame the hand stops at is the frame put back; the words reserved are the words trimmed
    ev = {r['step']: r for r in micro.walk('evict_rw', nums['measure'], w)}
    assert ev['reserve']['new'] == 1 and ev['trim']['new'] == 0 and ev['put_frame']['new'] == 0


def test_document_on_disk_is_what_the_stored_numbers_render_to(nums):
    with open(os.path.join(micro_doc.SPEC_DIR, micro_doc.DOC), encoding='utf-8') as f:
        assert f.read() == micro_doc.render(nums)
    assert '{{' not in micro_doc.render(nums)


@pytest.mark.skipif(not micro.can_measure(), reason='needs clang on an AArch64 Mac')
def test_a_fresh_measurement_gives_the_stored_counts(nums):
    """Bulk steps go through the C library, whose count moves by a few instructions; the rest is exact."""
    fresh = micro.measure()['steps']
    for key, old in nums['measure']['steps'].items():
        slack = max(0, round(old['instr'] * 0.03)) if old['instr'] >= 100 else 0
        assert abs(fresh[key]['instr'] - old['instr']) <= slack, (key, fresh[key]['instr'], old['instr'])

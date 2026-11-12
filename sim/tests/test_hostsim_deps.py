"""The dependency graphs of the kernel's operations (hostsim/deps.py) and the document made from them."""
import json
import os

import pytest

from hostsim import conc, deps, deps_doc, deps_fig


@pytest.fixture(scope='module')
def nums():
    with open(os.path.join(deps_doc.SPEC_DIR, deps_doc.NUMBERS), encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope='module')
def base():
    return deps_doc.timed()['base_irq']


# ------------------------------------------------------------ the declaration against the running kernel
def test_declared_order_is_the_order_the_kernel_logs():
    for case, (want, got) in deps.occurrences().items():
        assert want == got, case


def test_declared_reads_and_writes_are_what_a_run_touches():
    """A fresh trace over the three runs: nothing touched that no step declares, nothing declared and never touched."""
    seen, lock, runs = deps.trace_runs()
    rows, stray = deps.compare(seen)
    assert not stray
    for r in rows:
        assert not r['undeclared'], r['steps']
        assert not r['unseen'], r['steps']
    assert {r['name'] for r in runs} == {'plain', 'damaged streams', 'failing LZ4 HW'}
    assert any(r['results'].get('lost') for r in runs), 'no run reached a lost page'
    held_only = [k for k, v in lock.items() if v.get('held') and not v.get('free')]
    assert {'state[h]', 'cot[h]', 'pte[h]', 'free_frames', 'bitmap', 'hand'} <= set(held_only)
    for name in ('tag', 'job_ring', 'cpl_ring', 'chunk[c]'):
        assert not lock[name].get('held'), name


def test_stored_trace_is_clean(nums):
    t = nums['trace']
    assert not t['stray']
    assert all(not r['undeclared'] and not r['unseen'] for r in t['rows'])
    # the only time a frame is written with the lock held is the zero fill of a first touch
    first = sum(r['results'].get('first_touch', 0) for r in t['runs'])
    assert first and t['lock']['frame[f]']['held'] == first


# ------------------------------------------------------------------------------ the graphs themselves
def test_every_case_is_a_dag_in_code_order():
    for case in deps.CASES:
        ns = deps.nodes(case)
        E = deps.edges(case)                              # raises when a rule runs against the code order
        assert all(ns.index(a) < ns.index(b) for a, b in E), case
        R = deps.reduced(case)
        assert set(R) <= set(E)
        assert deps.reach(ns, R) == deps.reach(ns, E), case


def test_rules_name_real_steps_and_real_mutants():
    for r in deps.RULES:
        assert r.a in deps.STEPS and r.b in deps.STEPS, (r.a, r.b)
        assert r.zh
        assert r.witness is None or r.witness in conc.MUTANTS, r.witness
    used = {(e['rule'].a, e['rule'].b) for c in deps.CASES for e in deps.edges(c).values() if e['rule']}
    assert used == {(r.a, r.b) for r in deps.RULES}, 'a rule that no case uses'


def test_steps_that_must_stay_together_share_one_section():
    for steps, _, zh, witness in deps.ATOMIC:
        assert witness in conc.MUTANTS and zh
        together = [case for case in deps.CASES for sec in [deps.sections(case)]
                    if all(sec.get(s) for s in steps) and len({sec[s] for s in steps}) == 1]
        assert together, steps                            # the group describes at least one case as it is written


def test_one_operation_alone_takes_the_sum_of_its_steps(base):
    w = deps.weights(base)
    for case in deps.CASES:
        s = deps.schedule(case, w)
        (op,) = deps.overlap([(case, case, 0)], w)
        assert op['end'] == s['serial'], case
        assert s['span'] <= s['serial']
        assert all(v >= 0 for v in s['slack'].values())
        assert all(s['slack'][n] == 0 for n in s['critical'])


def test_nothing_of_weight_can_run_beside_the_hw_job(base):
    w = deps.weights(base)
    for case in deps.CASES:
        assert all(deps.cost(n, w) == 0 for n in deps.beside_hw(case)), case


def test_three_at_once_waits_for_the_engine_not_the_lock(base):
    w = deps.weights(base)
    ops = {o['case']: o for o in deps.overlap(list(deps.SHOWN_TOGETHER), w)}

    def waited(o, kind):
        return sum(b - a for k, _, a, b in o['segs'] if k == kind)
    assert waited(ops['evict_rw'], 'wait_engine') == 0
    for case in ('fault_ro', 'fault_rw'):
        o = ops[case]
        alone = deps.schedule(case, w)['serial']
        assert o['end'] - o['start'] == alone + waited(o, 'wait_lock') + waited(o, 'wait_engine')
        assert waited(o, 'wait_engine') > 10 * waited(o, 'wait_lock')


# ------------------------------------------------------------------- against the timed model's own run
def test_lock_and_engine_shares_agree_with_the_timed_model(base):
    cap = deps.capacity(base)
    for name in ('lock', 'engine'):
        assert cap['share'][name] == pytest.approx(cap['measured'][name], rel=0.01), name
    assert cap['share']['reclaimer'] > cap['share']['engine'] > cap['share']['lock']
    assert sum(cap['lock_by_case'].values()) == pytest.approx(1)


def test_lock_holds(nums):
    for h in nums['holds']:
        assert h['fault']['ns_max'] <= 600 and h['fault']['victims_max'] == 0
        assert h['reclaim']['victims_max'] > 1, 'the reclaimer no longer keeps the lock across victims'
        assert h['reclaim']['frames_max'] == h['frames'] + 1 and h['scan_max_at'] == 1
        assert h['scan_rest_max'] < h['frames']
    small = next(h for h in nums['holds'] if h['cfg'] == 'small')
    assert deps.holds('small', 20000) == small


# ---------------------------------------------------------------------------- the generated files
def test_document_is_up_to_date(nums):
    """spec/kernel-sw-dependency-v0.md is generated from the stored numbers and today's declarations."""
    text = deps_doc.render(nums)
    assert '{{' not in text
    with open(os.path.join(deps_doc.SPEC_DIR, deps_doc.DOC), encoding='utf-8') as f:
        assert f.read() == text, 'run: python3 sim/run_host.py gen-deps --reuse'
    for case in deps.CASES:
        assert f'graph-{case}.svg' in text


def test_figures_are_up_to_date(base):
    for name, body in deps_fig.render(deps.weights(base)).items():
        with open(os.path.join(deps_fig.FIG_DIR, name), encoding='utf-8') as f:
            assert f.read() == body, f'{name}: run python3 sim/run_host.py gen-deps --reuse'

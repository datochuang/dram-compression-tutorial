"""User software: every page belongs to one user program, and the label changes nothing else."""
import pytest

from lz4sim.config import SMALL
from lz4sim.replay import run_data
from lz4sim.sim import Simulation, VARIANTS
from lz4sim.workload import CLIENTS, MAX_CLIENTS, Workload, parse_clients

WL = dict(hot_ro_pages=100, hot_rw_pages=200)


def run(variant, accesses=1200, **wl):
    sim = Simulation(variant, SMALL, seed=3, workload=dict(WL, **wl), trace_level='all', keep_trace=True)
    sim.build()
    sim.boot()
    sim.run(accesses)
    s = sim.stats()
    sim.close()
    return sim, s


def test_every_page_has_one_owner():
    wl = Workload(SMALL, seed=1, **WL)
    assert [c['name'] for c in wl.clients] == [n for n, _ in CLIENTS]
    assert sum(c['pages'] for c in wl.clients) == SMALL.pages == len(wl.owner)
    seen = bytearray(SMALL.pages)
    for i, c in enumerate(wl.clients):
        for key in ('data', 'heap', 'ro'):
            a, b = c[key]
            assert a <= b
            for h in range(a, b):
                seen[h] += 1
                assert wl.client_of(h) == i
    assert set(seen) == {1}
    # the default shares are uneven on purpose
    assert len({c['pages'] for c in wl.clients}) == len(wl.clients)


def test_parse_and_reject():
    assert parse_clients('UI:40, MEDIA:27') == (('UI', 40.0), ('MEDIA', 27.0))
    assert parse_clients('A,B') == (('A', 1.0), ('B', 1.0))
    for bad in ((), (('A', 1), ('A', 2)), (('A', 0),), (('', 1),), tuple((f'C{i}', 1) for i in range(MAX_CLIENTS + 1))):
        with pytest.raises(ValueError):
            Workload(SMALL, seed=1, clients=bad, **WL)


@pytest.mark.parametrize('variant', VARIANTS)
def test_access_events_name_the_client(variant):
    sim, s = run(variant)
    data = run_data(sim, s)
    names = [c['name'] for c in data['meta']['clients']]
    assert names == [n for n, _ in CLIENTS]
    assert data['boot'][-1]['clients'] == data['meta']['clients']
    count = [0] * len(names)
    for sc in data['scenes']:
        acc = sc[-1]
        assert acc['ev'] == 'access' and acc['client'] == sim.wl.client_of(acc['h'])
        count[acc['client']] += 1
    assert count == [s[f'{n}_accesses'] for n in names] and sum(count) == 1200
    assert sum(s[f'{n}_faults'] for n in names) == s['faults']


@pytest.mark.parametrize('variant', VARIANTS)
def test_label_does_not_change_the_run(variant):
    def stream(sim):
        out = []
        for e in sim.trace.records:
            e = dict(e)
            e.pop('client', None)
            e.pop('clients', None)
            out.append(e)
        return out
    a, sa = run(variant)
    b, sb = run(variant, clients=(('ONE', 1),))
    assert stream(a) == stream(b)
    assert sb['ONE_accesses'] == 1200 and sb['ONE_pages'] == SMALL.pages
    assert sa['faults'] == sb['faults'] and sa['sim_time_ms'] == sb['sim_time_ms']

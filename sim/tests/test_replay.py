import json
import re

import pytest

from lz4sim.config import SMALL, SystemConfig
from lz4sim.replay import JS_FILES, check_size, render, run_data
from lz4sim.sim import Simulation, VARIANTS

WL = dict(hot_ro_pages=100, hot_rw_pages=200)


def replay_run(variant, accesses=1500):
    sim = Simulation(variant, SMALL, seed=3, workload=WL, trace_level='all', keep_trace=True)
    sim.build()
    sim.boot()
    sim.run(accesses)
    s = sim.stats()
    sim.close()
    return run_data(sim, s), s


@pytest.mark.parametrize('variant', VARIANTS)
def test_one_scene_per_access(variant):
    data, s = replay_run(variant)
    assert data['boot'][-1]['ev'] == 'boot'
    assert len(data['scenes']) == 1500
    assert all(sum(e['ev'] == 'access' for e in sc) == 1 for sc in data['scenes'])
    res = [e['res'] for sc in data['scenes'] for e in sc if e['ev'] == 'access']
    assert res.count('fault') == s['faults'] and res.count('hit') == s['hits']
    assert data['meta']['pool_chunks'] == SMALL.pool_chunks and data['meta']['variant'] == variant


def test_page_embeds_both_runs():
    runs = [replay_run(v, 400)[0] for v in VARIANTS]
    html = render(runs)
    assert html.startswith('<!doctype html>')
    m = re.search(r'<script type="application/json" id="replay-data">(.*?)</script>', html, re.S)
    back = json.loads(m.group(1).replace('<\\/', '</'))
    assert [r['meta']['variant'] for r in back['runs']] == list(VARIANTS)
    assert 'R.Stage' in html and 'R.Director' in html and 'R.chars' in html and len(JS_FILES) == 5
    frag = render(runs, fragment=True)
    assert '<!doctype' not in frag and '<body' not in frag and frag.lstrip().startswith('<title>')


def test_full_size_machine_is_refused():
    with pytest.raises(SystemExit):
        check_size(SystemConfig(), 1000)
    check_size(SMALL, 1000)


def test_start_design_and_title():
    runs = [replay_run(v, 200)[0] for v in VARIANTS]
    html = render(runs, start='software')
    assert '"start":"software"' in html and '<title>LZ4 Replay SW-leaning</title>' in html
    assert '<title>LZ4 Replay 3D</title>' in render(runs)
    only_sw = render([r for r in runs if r['meta']['variant'] == 'software'])
    assert '<title>LZ4 Replay SW-leaning</title>' in only_sw and '"start"' not in only_sw
    with pytest.raises(ValueError):
        render(runs[:1], start='software')

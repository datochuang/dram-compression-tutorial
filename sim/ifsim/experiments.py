"""The fixed set of runs behind the results document.

Every run is seeded, so the same code gives the same numbers. `run_all` returns
a plain dict that can be stored as JSON and turned into the document later
without running anything again.
"""
import itertools
import time

from lz4sim.config import SMALL, SystemConfig

from . import report as R
from .params import Params
from .system import Stalled, System

CONFIGS = {
    'full': (SystemConfig, None),
    'small': (lambda: SMALL, dict(hot_ro_pages=100, hot_rw_pages=200)),
}
N_FULL = 400_000
N_SMALL = 20_000

LAT = ('p50', 'p99', 'max')
# key, swept parameters (the product of all axes is run), fixed parameters, columns of the table, memory map
SWEEPS = [
    ('wait_cores', {'wait_mode': ['irq', 'poll'], 'cores': [1, 2, 4]}, {}, LAT + ('notify', 'kcpu', 'tend', 'fails'), 'small'),
    ('load', {'wait_mode': ['irq', 'poll'], 'think_ns': [20000, 5000, 2000, 1000, 500]}, {},
     LAT + ('queue', 'frame', 'engine', 'kcpu', 'fwaits', 'stall', 'fails'), 'small'),
    ('full_load', {'engines': [1, 4], 'think_ns': [5000, 2000], 'reclaim_inflight': [1, 2, 4]}, {},
     LAT + ('queue', 'qmax', 'hwmax', 'imax', 'fdc', 'lmax', 'frame', 'engine', 'kcpu', 'fwaits', 'fails'), 'full'),
    ('reclaim_inflight', {'engines': [1, 2, 4], 'reclaim_inflight': [1, 2, 3, 4, 8]}, {'think_ns': 2000},
     LAT + ('queue', 'qmax', 'hwmax', 'imax', 'fdc', 'lmax', 'frame', 'ring', 'peak', 'fwaits', 'fails'), 'small'),
    ('engines', {'engines': [1, 2, 4, 8]}, {}, LAT + ('queue', 'qmax', 'hw', 'hwmax', 'engine', 'peak', 'allbusy', 'fails'), 'small'),
    ('engines_load', {'engines': [1, 2, 4, 8], 'think_ns': [2000, 500]}, {'reclaim_inflight': 4},
     LAT + ('queue', 'qmax', 'hw', 'hwmax', 'imax', 'fdc', 'lmax', 'dec', 'comp', 'arb', 'peak', 'allbusy', 'fwaits'), 'small'),
    ('ring_size', {'job_entries': [2, 4, 8, 16]}, {'think_ns': 2000, 'reclaim_inflight': 2},
     LAT + ('submit', 'queue', 'ring', 'stall', 'fails'), 'small'),
    ('comp_speed', {'comp_bytes_per_cycle': [0.5, 1.0, 2.0, 4.0]}, {}, LAT + ('queue', 'engine', 'fails'), 'small'),
    ('decomp_speed', {'decomp_bytes_per_cycle': [1.0, 2.0, 4.0, 8.0]}, {}, LAT + ('hw', 'engine', 'fails'), 'small'),
    ('bus_bg', {'bus_bg_share': [0.0, 0.2, 0.5, 0.8]}, {}, LAT + ('hw', 'fails'), 'small'),
    ('wakeup', {'wakeup_ns': [500, 1000, 2000, 5000, 20000]}, {}, LAT + ('notify', 'fails'), 'small'),
    ('irq_latency', {'irq_latency_ns': [200, 1000, 5000]}, {}, LAT + ('notify', 'fails'), 'small'),
]

# key, parameters, accesses
FAULTS = [
    ('hang_irq', dict(hw_hang_jobs=(40, 300)), N_SMALL),
    ('hang_poll', dict(hw_hang_jobs=(40, 300), wait_mode='poll'), N_SMALL),
    ('irq_drop', dict(irq_drop_every=50), N_SMALL),
    ('corrupt', dict(corrupt_every=500), N_SMALL),
]


def run_one(cfg='small', n=None, seed=1, name='', trace=None, strict=False, **params):
    """One run with the checker attached. Returns the metrics dict of report.collect."""
    make, wl = CONFIGS[cfg]
    n = n or (N_FULL if cfg == 'full' else N_SMALL)
    s = System(make(), Params(**params), seed=seed, workload=wl, trace_path=trace, strict=strict)
    t0 = time.time()
    try:
        s.run(n)
        audit = s.audit()
        m = R.collect(s, name or cfg)
        m['audit'] = audit
    except Stalled as e:
        m = {'name': name or cfg, 'stalled': str(e)}
    finally:
        s.close()
    m['wall_s'] = round(time.time() - t0, 1)
    m['cfg'] = cfg
    m['params'] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in params.items()}
    return m


def sweep(axes, fixed=None, cfg='small', n=None, seed=1, log=None):
    """Run the product of the axes. Returns [(dict of swept values, metrics)]."""
    keys = list(axes)
    out = []
    for combo in itertools.product(*(axes[k] for k in keys)):
        kv = dict(zip(keys, combo))
        m = run_one(cfg, n, seed, **{**(fixed or {}), **kv})
        if log:
            log(f'  {kv} {m["wall_s"]} s')
        out.append((kv, m))
    return out


def slim(m):
    """What a sweep row needs, without the long per-rule and per-client lists."""
    if 'stalled' in m:
        return {'stalled': m['stalled']}
    r = R.sweep_row(m)
    for kind in ('fault_ro', 'fault_rw'):
        r[kind + '_parts'] = m['parts'].get(kind)
    r['worst'] = max((dict(w, kind=k) for k, w in m['worst'].items() if k in R.WAITED), key=lambda w: w['ns'], default=None)
    r.update(jobs=m['hw_jobs'], irqs=m['drv'].get('irqs', 0), poll_spins=m['drv'].get('poll_spins', 0),
             ring_full_waits=m['drv'].get('ring_full_waits', 0), min_free=m['min_free_frames'],
             stall_share=max(c['stall_share'] for c in m['clients']), lost=m['lost_pages'],
             mm_lock_busy=m['mm_lock']['busy_share'], runq_ns=m['runq_ns'], results=m['results'])
    return r


def run_all(log=print, seed=1):
    out = {'seed': seed, 'n_full': N_FULL, 'n_small': N_SMALL, 'sweeps': {}, 'faults': {}}
    for mode in ('irq', 'poll'):
        log(f'baseline full {mode}')
        out['base_' + mode] = run_one('full', seed=seed, name='full ' + mode, wait_mode=mode)
        log(f'  {out["base_" + mode]["wall_s"]} s')
    log('baseline full irq, one engine')
    out['base_irq_e1'] = run_one('full', seed=seed, name='full irq, 1 engine', engines=1)
    log(f'  {out["base_irq_e1"]["wall_s"]} s')
    out['small_irq'] = run_one('small', seed=seed, name='small irq')
    for key, axes, fixed, cols, cfg in SWEEPS:
        log(f'sweep {key}')
        rows = sweep(axes, fixed, cfg, seed=seed, log=log)
        out['sweeps'][key] = {'keys': list(axes), 'fixed': fixed, 'cols': list(cols), 'cfg': cfg,
                              'rows': [(kv, slim(m)) for kv, m in rows]}
    for key, params, n in FAULTS:
        log(f'fault injection {key}')
        m = run_one('small', n, seed=3, name=key, **params)
        out['faults'][key] = {'params': m['params'], 'n': n, 'drv': m.get('drv'), 'hw': m.get('hw'), 'mm': m.get('mm'),
                              'lost': m.get('lost_pages'), 'violations': m.get('violations'), 'audit': m.get('audit'),
                              'lat': m.get('lat', {}).get('waited'), 'stalled': m.get('stalled')}
    return out

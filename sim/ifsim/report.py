"""Numbers out of a finished run: latency, where the time went, utilisation, budgets, rule coverage.

collect() turns a System into a plain dict (JSON friendly); the md_* functions
turn such dicts into Markdown tables. The prose around the tables lives in the
document templates, not here.
"""
from collections import Counter
from dataclasses import fields
from math import ceil

from .mm import PARTS
from .params import Budgets, Params, PARAM_DOC

WAITED = ('fault_ro', 'fault_rw', 'inflight')      # accesses that had to wait for the LZ4 HW
KIND_ZH = {'first': '第一次碰 RW page（補零）', 'fault_ro': 'RO page 解壓縮', 'fault_rw': 'RW page 解壓縮',
           'inflight': '碰到正在壓縮或解壓縮的 page', 'spurious': '別人已經處理好', 'lost': '資料損毀', 'waited': '需要等 LZ4 HW 的全部'}
PART_ZH = {'cpu': 'kernel 自己的指令', 'lock': '等 mm_lock', 'frame': '等 free frame', 'inflight': '等別人的 job',
           'submit': '等 ring 空位與 ring_lock', 'queue': '在 job ring 排隊', 'hw': 'LZ4 HW 處理', 'notify': 'completion 到 thread 醒來'}


def pct(xs, q):
    """Nearest-rank percentile of a list (q in 0..100)."""
    if not xs:
        return 0
    ys = sorted(xs)
    return ys[min(len(ys) - 1, max(0, ceil(q / 100 * len(ys)) - 1))]


def _dist(xs):
    return {'n': len(xs), 'mean': sum(xs) / len(xs) if xs else 0, 'p50': pct(xs, 50), 'p90': pct(xs, 90),
            'p99': pct(xs, 99), 'max': max(xs) if xs else 0}


def collect(s, name=''):
    p, cfg, mm, drv, hw, env = s.p, s.cfg, s.mm, s.drv, s.hw, s.env
    t = s.t_end or 1
    lat = {k: _dist(v) for k, v in mm.lat.items()}
    waited = [x for k in WAITED for x in mm.lat.get(k, ())]
    lat['waited'] = _dist(waited)
    parts = {k: {q: mm.parts[k][q] / len(mm.lat[k]) for q in PARTS} for k in mm.lat if mm.lat[k]}
    worst = {k: {'ns': w[0], 'parts': w[1], 'page': w[2], 't': w[3]} for k, w in mm.worst.items()}
    part_max = {q: max((mm.part_max[k][q] for k in WAITED if k in mm.part_max), default=0) for q in PARTS}
    kcpu = {'fault': sum(c.kcpu for c in env.ctxs), 'irq': drv.irq_ctx.kcpu, 'reclaim': mm.rctx.kcpu}
    occ = dict(sorted(drv.occ.items()))
    clients = []
    for c, st in zip(s.wl.clients, env.per_client):
        n = sum(v for k, v in st.items() if k != 'wait_ns')
        faults = n - st['hit']
        clients.append({'name': c['name'], 'accesses': n, 'faults': faults, 'stall_ns': st['wait_ns'],
                        'stall_share': st['wait_ns'] / t, 'mean_stall_ns': st['wait_ns'] / faults if faults else 0})
    conc = hw.conc()
    conc[0] = t - sum(conc[k] for k in range(1, hw.n + 1))      # the run is measured up to the last access, like busy_ns
    arb = {ch: {'bursts': a.bursts, 'waited': a.waited, 'wait_ns': a.wait_ns} for ch, a in zip(('read', 'write'), hw.arb)}
    m = {
        'name': name, 'seed': s.seed, 'accesses': s.accesses, 't_end_ns': s.t_end, 'events': s.sim.events,
        'wait_mode': p.wait_mode, 'cores': p.cores, 'reclaim_inflight': p.reclaim_inflight,
        'frames': cfg.frames, 'pages': cfg.pages, 'pool_chunks': cfg.pool_chunks,
        'results': dict(env.results), 'lat': lat, 'parts': parts, 'worst': worst, 'part_max': part_max,
        'hw_jobs': hw.st['jobs'], 'hw_job_ns': {s.spec.enum_name['opcode'].get(op, str(op)): _dist(v) for op, v in hw.job_ns.items()},
        'engines': hw.n,
        'engine_util': hw.busy_ns / (t * hw.n),             # mean over the engines
        'hw_conc': [conc[k] / t for k in range(hw.n + 1)],  # share of the time with k engines holding a job
        'hw_any_share': 1 - conc[0] / t, 'hw_all_share': conc[hw.n] / t, 'hw_peak': hw.peak,
        'overtook': hw.st['overtook'],                      # completions posted before a job fetched earlier
        'arb': arb,
        'arb_wait_per_burst': sum(a['wait_ns'] for a in arb.values()) / max(1, sum(a['bursts'] for a in arb.values())),
        'bus_share': s.bus.busy_ns['hw'] / t, 'bus_wait_per_burst': s.bus.wait_ns['hw'] / max(1, s.bus.bursts['hw']),
        'bus_bytes': s.bus.bytes['hw'],
        'kcpu_ns': kcpu, 'kernel_cpu_share': sum(kcpu.values()) / (p.cores * t),
        'ring_depth': drv.depth, 'ring_occ': occ, 'ring_peak': max(occ) if occ else 0,
        'ring_peak_share': (max(occ) if occ else 0) / drv.depth,
        'mm_lock': {'wait_ns': mm.lock.wait_ns, 'waited': mm.lock.waited, 'grants': mm.lock.grants, 'max_q': mm.lock.max_q,
                    'busy_share': mm.lock.busy_ns / t},
        'ring_lock': {'wait_ns': drv.lock.wait_ns, 'waited': drv.lock.waited, 'grants': drv.lock.grants,
                      'max_q': drv.lock.max_q, 'busy_share': drv.lock.busy_ns / t},
        'runq_ns': sum(c.runq_ns for c in env.ctxs),
        'mm': dict(mm.st), 'drv': dict(drv.st), 'hw': dict(hw.st), 'irq_edges': s.irq.edges,
        'min_free_frames': mm.min_free, 'peak_pool_chunks': mm.peak_pool,
        'frame_waits': mm.st['frame_waits'], 'lost_pages': mm.st['lost_ro'] + mm.st['lost_rw'],
        'clients': clients,
        'rules': s.chk.summary() if s.chk else [], 'violations': sum(s.chk.nviol.values()) if s.chk else None,
    }
    return m


def check_budgets(m, b=None):
    """[(budget name, what it means, target, measured, pass)]"""
    b = b or Budgets()
    w = m['lat']['waited']
    rows = [
        ('fault_p50_ns', '要等 LZ4 HW 的 page fault，中位數', b.fault_p50_ns, w['p50']),
        ('fault_p99_ns', '同上，第 99 百分位', b.fault_p99_ns, w['p99']),
        ('fault_max_ns', '同上，最大值', b.fault_max_ns, w['max']),
        ('kernel_cpu_share', 'kernel 花在壓縮層的 CPU 時間佔全部 core 時間', b.kernel_cpu_share, m['kernel_cpu_share']),
        ('engine_util', '每個 LZ4 engine 手上有 job 的時間比例，取所有 engine 的平均', b.engine_util, m['engine_util']),
        ('job_ring_peak', 'job ring 最高佔用除以可用格數', b.job_ring_peak, m['ring_peak_share']),
        ('frame_waits', '找不到 free frame 而要等的 fault 次數', b.frame_waits, m['frame_waits']),
        ('lost_pages', '遺失的 page 數', b.lost_pages, m['lost_pages']),
    ]
    return [(n, d, t, v, v <= t) for n, d, t, v in rows]


# ---- Markdown
def us(ns):
    return f'{ns / 1000:.2f}'


def _fmt(name, v):
    if name.endswith('_ns'):
        return f'{us(v)} µs'
    if isinstance(v, float):
        return f'{v * 100:.1f}%'
    return str(v)


def table(head, rows):
    out = ['| ' + ' | '.join(head) + ' |', '|' + '|'.join(['---'] * len(head)) + '|']
    out += ['| ' + ' | '.join(str(c) for c in r) + ' |' for r in rows]
    return '\n'.join(out)


def md_run(m):
    r = m['results']
    rows = [('模擬時間', f"{m['t_end_ns'] / 1e6:.1f} ms"), ('access 次數', m['accesses']),
            ('直接命中', r.get('hit', 0)), ('第一次碰 RW page', r.get('first', 0)),
            ('RO page 解壓縮 fault', r.get('fault_ro', 0)), ('RW page 解壓縮 fault', r.get('fault_rw', 0)),
            ('碰到進行中 job 的 fault', r.get('inflight', 0)),
            ('COMPRESS 成功', m['mm'].get('rw_compress_ok', 0)), ('COMPRESS 回 INCOMPRESSIBLE', m['mm'].get('rw_incompressible', 0)),
            ('RO page 直接丟棄', m['mm'].get('ro_drops', 0)), ('LZ4 HW job 總數', m['hw_jobs']),
            ('interrupt 次數', m['drv'].get('irqs', 0)), ('free frame 最低', m['min_free_frames']),
            ('chunk pool 最高用量', f"{m['peak_pool_chunks']} / {m['pool_chunks']}"),
            ('checker 違規', m['violations'])]
    return table(('項目', '數值'), rows)


def md_budgets(m, b=None):
    rows = [(f'`{n}`', d, _fmt(n, t), _fmt(n, v), 'PASS' if ok else '**FAIL**') for n, d, t, v, ok in check_budgets(m, b)]
    return table(('Budget', '意思', '暫定目標', '量到', '結果'), rows)


def md_latency(m):
    rows = []
    for k in ('first', 'fault_ro', 'fault_rw', 'inflight', 'waited'):
        d = m['lat'].get(k)
        if d and d['n']:
            rows.append((KIND_ZH[k], d['n'], us(d['mean']), us(d['p50']), us(d['p90']), us(d['p99']), us(d['max'])))
    return table(('Fault 種類', '次數', '平均 µs', 'p50 µs', 'p90 µs', 'p99 µs', '最大 µs'), rows)


def md_parts(m, kinds=('fault_ro', 'fault_rw')):
    kinds = [k for k in kinds if k in m['parts']]
    rows = []
    for q in PARTS:
        row = [f'`{q}`', PART_ZH[q]]
        for k in kinds:
            tot = sum(m['parts'][k].values()) or 1
            row.append(f"{us(m['parts'][k][q])} µs（{m['parts'][k][q] / tot * 100:.0f}%）")
        rows.append(row)
    rows.append(['合計', ''] + [f"{us(sum(m['parts'][k].values()))} µs" for k in kinds])
    return table(['階段', '內容'] + [KIND_ZH[k] + '，平均' for k in kinds], rows)


def md_worst(m):
    rows = []
    for k, w in m['worst'].items():
        if k in WAITED:
            top = sorted(w['parts'].items(), key=lambda kv: -kv[1])[:3]
            rows.append((KIND_ZH[k], f"{us(w['ns'])} µs", f"{w['page']:#x}", f"{w['t'] / 1e6:.3f} ms",
                         '、'.join(f'`{q}` {us(v)} µs' for q, v in top if v)))
    return table(('Fault 種類', '最慢一次', 'page', '發生時間', '時間最多的三個階段'), rows)


def md_resources(m):
    k = m['kcpu_ns']
    tot = sum(k.values()) or 1
    occ = '、'.join(f'{n} 個 job：{c} 次' for n, c in m['ring_occ'].items())
    arb = m['arb']
    rows = [
        ('LZ4 engine 數', m['engines']),
        ('每個 engine 手上有 job 的時間比例，平均', f"{m['engine_util'] * 100:.1f}%"),
        ('至少一個 engine 有 job 的時間比例', f"{m['hw_any_share'] * 100:.1f}%"),
        ('剛好 k 個 engine 有 job 的時間比例，k 從 0 起', '、'.join(f'{x * 100:.2f}%' for x in m['hw_conc'])),
        ('同時在 HW 裡的 job 最多幾個', m['hw_peak']),
        ('比先取走的 job 早寫出的 completion', f"{m['overtook']} / {m['hw_jobs']}"),
        ('在 master port 等其他 job 的 burst 數 / 全部 burst 數',
         '、'.join(f"{zh} {arb[c]['waited']} / {arb[c]['bursts']}" for c, zh in (('read', '讀'), ('write', '寫')))),
        ('上一列等的時間，攤到每個 burst', f"{m['arb_wait_per_burst']:.1f} ns"),
        ('DRAM port 被 LZ4 HW 佔用的比例', f"{m['bus_share'] * 100:.1f}%"),
        ('每個 burst 平均等 CPU 與 HRT 的流量', f"{m['bus_wait_per_burst']:.1f} ns"),
        ('COMPRESS job 的 HW 時間 p50 / 最大', ' / '.join(us(m['hw_job_ns'].get('COMPRESS', {}).get(x, 0)) for x in ('p50', 'max')) + ' µs'),
        ('DECOMPRESS job 的 HW 時間 p50 / 最大', ' / '.join(us(m['hw_job_ns'].get('DECOMPRESS', {}).get(x, 0)) for x in ('p50', 'max')) + ' µs'),
        ('kernel CPU 佔全部 core 時間', f"{m['kernel_cpu_share'] * 100:.2f}%"),
        ('其中 fault path / interrupt handler / reclaimer', ' / '.join(f"{k[x] / tot * 100:.0f}%" for x in ('fault', 'irq', 'reclaim'))),
        ('doorbell 當下未完成的 job 數', occ),
        ('job ring 最高佔用', f"{m['ring_peak']} / {m['ring_depth']}"),
        ('`mm_lock` 被持有的時間比例', f"{m['mm_lock']['busy_share'] * 100:.1f}%"),
        ('`mm_lock` 要等的次數 / 取得次數 / 最長排隊', f"{m['mm_lock']['waited']} / {m['mm_lock']['grants']} / {m['mm_lock']['max_q']}"),
        ('`ring_lock` 要等的次數 / 取得次數', f"{m['ring_lock']['waited']} / {m['ring_lock']['grants']}"),
    ]
    return table(('項目', '數值'), rows)


def md_clients(m):
    rows = [(c['name'], c['accesses'], c['faults'], f"{us(c['mean_stall_ns'])} µs", f"{c['stall_share'] * 100:.2f}%")
            for c in m['clients']]
    return table(('User SW', 'access 次數', 'fault 次數', '每次 fault 平均停頓', '停頓佔執行時間'), rows)


def md_rules(m, spec):
    how = {'checker': '執行中 checker', 'audit': '結束時 audit', 'test': '注入測試', 'review': '人工 review'}
    rows = [(f'`{rid}`', owner, how[kind], n if kind in ('checker', 'audit') else '', bad if kind in ('checker', 'audit') else '')
            for rid, owner, kind, n, bad in m['rules']]
    return table(('Rule', '誰的義務', '怎麼驗', '檢查次數', '違規'), rows)


def md_params(p=None, changed=None):
    p = p or Params()
    base = Params()
    rows = []
    for f in fields(p):
        if f.name not in PARAM_DOC:
            continue
        src, doc = PARAM_DOC[f.name]
        v = getattr(p, f.name)
        mark = '' if v == getattr(base, f.name) else '（本次改過）'
        shown = (str(int(v)) if v == int(v) else f'{v:g}') if isinstance(v, float) else v
        rows.append((f'`{f.name}`', shown, src, doc + mark))
    return table(('參數', '值', '來源', '意思'), rows)


def md_budget_defs(b=None):
    return table(('Budget', '暫定目標'), [(f'`{n}`', _fmt(n, v)) for n, v in (b or Budgets()).items()])


def sweep_row(m):
    w = m['lat']['waited']
    return {'p50': w['p50'], 'p99': w['p99'], 'max': w['max'], 'engine_util': m['engine_util'],
            'engines': m['engines'], 'hw_any_share': m['hw_any_share'], 'hw_all_share': m['hw_all_share'],
            'hw_peak': m['hw_peak'], 'overtook': m['overtook'], 'arb_wait_per_burst': m['arb_wait_per_burst'],
            'hw_job_p50': {op: d['p50'] for op, d in m['hw_job_ns'].items()},
            'queue_max': m['part_max']['queue'], 'hw_max': m['part_max']['hw'], 'part_max': m['part_max'],
            'kernel_cpu_share': m['kernel_cpu_share'], 'ring_peak': m['ring_peak'], 'frame_waits': m['frame_waits'],
            'during_compress': m['mm'].get('fault_during_compress', 0),
            't_end_ns': m['t_end_ns'], 'violations': m['violations'],
            'fails': [n for n, _, _, _, ok in check_budgets(m) if not ok]}


def _part(q):
    return lambda r: us((r['fault_ro_parts'] or {}).get(q, 0))


SWEEP_COLS = {
    'p50': ('p50 µs', lambda r: us(r['p50'])),
    'p99': ('p99 µs', lambda r: us(r['p99'])),
    'max': ('最大 µs', lambda r: us(r['max'])),
    'engine': ('engine 忙碌，平均', lambda r: f"{r['engine_util'] * 100:.1f}%"),
    'allbusy': ('engine 全滿', lambda r: f"{r['hw_all_share'] * 100:.2f}%"),
    'peak': ('同時最多幾個 job', lambda r: r['hw_peak']),
    'arb': ('port 互等 ns/burst', lambda r: f"{r['arb_wait_per_burst']:.1f}"),
    'dec': ('DECOMPRESS 的 HW 時間 p50 µs', lambda r: us(r['hw_job_p50'].get('DECOMPRESS', 0))),
    'comp': ('COMPRESS 的 HW 時間 p50 µs', lambda r: us(r['hw_job_p50'].get('COMPRESS', 0))),
    'kcpu': ('kernel CPU', lambda r: f"{r['kernel_cpu_share'] * 100:.2f}%"),
    'ring': ('ring 最高', lambda r: r['ring_peak']),
    'fwaits': ('等 frame 次數', lambda r: r['frame_waits']),
    'fdc': ('fault 碰到正在 COMPRESS 的 page，次數', lambda r: r['during_compress']),
    'tend': ('完成時間 ms', lambda r: f"{r['t_end_ns'] / 1e6:.1f}"),
    'stall': ('停頓最多的 user SW', lambda r: f"{r['stall_share'] * 100:.1f}%"),
    'submit': ('`submit` µs', _part('submit')),
    'queue': ('`queue` µs', _part('queue')),
    'qmax': ('`queue` 最長 µs', lambda r: us(r['queue_max'])),
    'hwmax': ('`hw` 最長 µs', lambda r: us(r['hw_max'])),
    'imax': ('`inflight` 最長 µs', lambda r: us(r['part_max']['inflight'])),
    'lmax': ('`lock` 最長 µs', lambda r: us(r['part_max']['lock'])),
    'frame': ('`frame` µs', _part('frame')),
    'hw': ('`hw` µs', _part('hw')),
    'notify': ('`notify` µs', _part('notify')),
    'fails': ('沒過的 budget', lambda r: '、'.join(f'`{x}`' for x in r['fails']) or '無'),
}
DEFAULT_COLS = ('p50', 'p99', 'max', 'engine', 'kcpu', 'ring', 'fwaits', 'tend', 'fails')


def md_sweep(rows, keys, cols=DEFAULT_COLS):
    """rows: [(dict of the swept parameters, experiments.slim row)]. Latency columns are over all faults
    that wait for the LZ4 HW; the columns named after a stage are the mean of that stage in an RO fault."""
    out = []
    for kv, r in rows:
        if 'stalled' in r:
            out.append([kv[k] for k in keys] + ['沒有跑完'] + [''] * (len(cols) - 1))
        else:
            out.append([kv[k] for k in keys] + [SWEEP_COLS[c][1](r) for c in cols])
    return table([f'`{k}`' for k in keys] + [SWEEP_COLS[c][0] for c in cols], out)


def md_sweep_worst(rows, keys):
    """The slowest fault of each run of a sweep and where its time went."""
    out = []
    for kv, r in rows:
        w = r.get('worst')
        if not w:
            continue
        top = sorted(w['parts'].items(), key=lambda q: -q[1])[:3]
        out.append([kv[k] for k in keys] + [KIND_ZH[w['kind']], us(w['ns']), '、'.join(f'`{q}` {us(v)}' for q, v in top if v)])
    return table([f'`{k}`' for k in keys] + ['最慢的一次是哪一種 fault', '合計 µs', '時間最多的三個階段 µs'], out)


def md_wait_compare(a, b):
    """The stages of an RO fault and the headline numbers of two baseline runs side by side."""
    rows = []
    for q in PARTS:
        rows.append((f'`{q}`', PART_ZH[q], us(a['parts']['fault_ro'][q]), us(b['parts']['fault_ro'][q])))
    rows.append(('RO fault 合計', '', us(sum(a['parts']['fault_ro'].values())), us(sum(b['parts']['fault_ro'].values()))))
    for label, f in (('要等 LZ4 HW 的 fault，p50 µs', lambda m: us(m['lat']['waited']['p50'])),
                     ('同上，p99 µs', lambda m: us(m['lat']['waited']['p99'])),
                     ('同上，最大 µs', lambda m: us(m['lat']['waited']['max'])),
                     ('kernel CPU 佔全部 core 時間', lambda m: f"{m['kernel_cpu_share'] * 100:.2f}%"),
                     ('停頓最多的 user SW，停頓佔執行時間', lambda m: f"{max(c['stall_share'] for c in m['clients']) * 100:.2f}%"),
                     ('interrupt 次數', lambda m: m['drv'].get('irqs', 0)),
                     ('polling 讀 `CPL_TAIL` 的次數', lambda m: m['drv'].get('poll_spins', 0))):
        rows.append((label, '', f(a), f(b)))
    return table(('項目', '內容', 'interrupt', 'polling'), rows)


def md_engine_compare(runs):
    """Baseline runs that differ only in the number of engines, side by side. runs: [metrics]."""
    part = lambda q: (lambda m: us(m['parts']['fault_ro'][q]))
    lat = lambda q: (lambda m: us(m['lat']['waited'][q]))
    rows = [('要等 LZ4 HW 的 fault，p50 µs', lat('p50')), ('同上，p99 µs', lat('p99')), ('同上，最大 µs', lat('max')),
            ('RO fault 的 `queue`，平均 µs', part('queue')), ('RO fault 的 `hw`，平均 µs', part('hw')),
            ('RO fault 的 `notify`，平均 µs', part('notify')),
            ('RO fault 合計，平均 µs', lambda m: us(sum(m['parts']['fault_ro'].values()))),
            ('所有 fault 裡 `queue` 最長的一次 µs', lambda m: us(m['part_max']['queue'])),
            ('所有 fault 裡 `hw` 最長的一次 µs', lambda m: us(m['part_max']['hw'])),
            ('COMPRESS job 的 HW 時間 p50 / 最大 µs', lambda m: ' / '.join(us(m['hw_job_ns']['COMPRESS'][x]) for x in ('p50', 'max'))),
            ('DECOMPRESS job 的 HW 時間 p50 / 最大 µs', lambda m: ' / '.join(us(m['hw_job_ns']['DECOMPRESS'][x]) for x in ('p50', 'max'))),
            ('每個 engine 有 job 的時間比例，平均', lambda m: f"{m['engine_util'] * 100:.2f}%"),
            ('至少一個 engine 有 job 的時間比例', lambda m: f"{m['hw_any_share'] * 100:.2f}%"),
            ('兩個以上 engine 同時有 job 的時間比例', lambda m: f"{sum(m['hw_conc'][2:]) * 100:.3f}%"),
            ('同時在 HW 裡的 job 最多幾個', lambda m: m['hw_peak']),
            ('比先取走的 job 早寫出的 completion', lambda m: m['overtook']),
            ('在 master port 等其他 job 的 burst', lambda m: sum(a['waited'] for a in m['arb'].values())),
            ('上一列等的時間，攤到每個 burst，ns', lambda m: f"{m['arb_wait_per_burst']:.1f}"),
            ('kernel CPU 佔全部 core 時間', lambda m: f"{m['kernel_cpu_share'] * 100:.2f}%"),
            ('interrupt 次數', lambda m: m['drv'].get('irqs', 0)),
            ('模擬時間 ms', lambda m: f"{m['t_end_ns'] / 1e6:.1f}"),
            ('checker 違規', lambda m: m['violations'])]
    return table(['項目'] + [f"{m['engines']} 個 engine" for m in runs], [[label] + [f(m) for m in runs] for label, f in rows])


FAULT_ZH = {
    'hang_irq': 'HW 在第 40 與第 300 個 job 卡住，interrupt',
    'hang_poll': 'HW 在第 40 與第 300 個 job 卡住，polling',
    'irq_drop': '每 50 次 interrupt 漏掉 1 次',
    'corrupt': '每 500 次 access 翻掉一個壓縮中 RW page 的 1 個 byte',
}


def md_faults(faults):
    rows = []
    for key, f in faults.items():
        if f.get('stalled'):
            rows.append((FAULT_ZH.get(key, key), '沒有跑完', '', '', '', '', '', '', ''))
            continue
        d, h = f['drv'], f['hw']
        rows.append((FAULT_ZH.get(key, key), d.get('timeouts', 0), d.get('resets', 0), d.get('reissued', 0),
                     d.get('late_completions', 0), h.get('st_BAD_STREAM', 0), f['lost'],
                     us(f['lat']['p50']) + ' / ' + us(f['lat']['max']), f['violations']))
    return table(('注入的故障', 'timeout', 'soft reset', '重送的 job', '遲到的 completion', 'BAD_STREAM', '遺失的 page',
                  'fault p50 / 最大 µs', 'checker 違規'), rows)


def results_extra(data, spec):
    """Placeholders of templates/sim_results.tmpl.md, filled from the dict of experiments.run_all."""
    ex = {'seed': data['seed'], 'n_full': data['n_full'], 'n_small': data['n_small']}
    for key in ('base_irq', 'base_poll'):
        m = data[key]
        for name, f in (('run', md_run), ('budgets', md_budgets), ('latency', md_latency), ('parts', md_parts),
                        ('worst', md_worst), ('resources', md_resources), ('clients', md_clients)):
            ex[f'{key}:{name}'] = f(m)
    ex['compare'] = md_wait_compare(data['base_irq'], data['base_poll'])
    ex['engines'] = Params().engines
    ex['compare_engines'] = md_engine_compare([data['base_irq_e1'], data['base_irq']])
    ex['rules'] = md_rules(data['base_irq'], spec)
    for key, s in data['sweeps'].items():
        ex['sweep:' + key] = md_sweep(s['rows'], s['keys'], s.get('cols') or DEFAULT_COLS)
        ex['worst:' + key] = md_sweep_worst(s['rows'], s['keys'])
    ex['faults'] = md_faults(data['faults'])
    return ex

"""Generate spec/kernel-sw-dependency-v0.md and the figures in figures/kernel-deps/.

Everything in the document that is a number or a table comes from deps.py: the declared steps, the
edges derived from them, the schedule under the assumed step costs, and two things that take a run
(the trace of what kernel.py really touches, and how long mm_lock is held). The runs take about
15 s, so their result is kept beside the document in a JSON file.
"""
import json
import os

from ifsim.gen import fill
from ifsim.report import table

from . import conc, deps, deps_fig

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'spec'))
TEMPLATE = os.path.join(HERE, 'templates', 'kernel_sw_dependency.tmpl.md')
DOC, NUMBERS = 'kernel-sw-dependency-v0.md', 'kernel-sw-dependency-v0.json'
TIMED = os.path.join(SPEC_DIR, 'sim-results-v0.json')
FIG = '../figures/kernel-deps/'
APPENDIX = tuple(c for c in deps.CASES if c not in deps.DRAWN)

WHO_ZH = {'cpu': 'CPU', 'lock': 'kernel，握 mm_lock', 'kernel': 'kernel，不握 lock', 'hw': 'LZ4 HW',
          'notify': 'kernel，interrupt 與叫醒'}
# what-if: ns taken out of the lock per occurrence of a case
WHAT_IF = (
    ('`first_touch` 的填 0 移到 lock 外', {'first_touch': ('zero_frame',)}),
    ('`evict_rw` 的 TLB invalidate 移到 lock 外', {'evict_rw': ('tlb_inval',), 'evict_rw_incompressible': ('tlb_inval',)}),
    ('`evict_ro` 的 TLB invalidate 也移到 lock 外', {'evict_ro': ('tlb_inval',)}),
)


def timed():
    with open(TIMED, encoding='utf-8') as f:
        return json.load(f)


def code(xs):
    return '、'.join(f'`{x}`' for x in xs) if xs else ''


def ns(v):
    return f'{v:,}'.replace(',', ' ') if isinstance(v, int) else f'{v:.0f}'


def pct(v, d=1):
    return f'{100 * v:.{d}f}%'


def who(case, n):
    k = deps.kind(case, n)
    sec = deps.sections(case)[n]
    return WHO_ZH[k] + (f'，第 {sec} 段' if sec else '')


def cost_of(n, w):
    s = deps.STEPS[n]
    if s.unknown:
        return '？'
    c = deps.cost(n, w)
    return ns(c) if c else '0'


# ------------------------------------------------------------------ per case
def md_summary(w):
    rows = []
    for c in deps.CASES:
        s = deps.schedule(c, w)
        off = [n for n in deps.nodes(c) if s['slack'][n]]
        rows.append((f'`{c}`', deps.CASE_ZH[c], len(deps.nodes(c)), len(deps.edges(c)), len(deps.reduced(c)),
                     ns(s['serial']), ns(s['span']), ns(s['serial'] - s['span']), len(off)))
    return table(('動作', '說明', '步驟', '所有先後關係', '去掉可推得的之後', '一步接一步 ns', '圖上最長路徑 ns',
                  '差 ns', '不在最長路徑上的步驟'), rows)


def md_steps(case, w):
    s = deps.schedule(case, w)
    rows = []
    for i, n in enumerate(deps.nodes(case), 1):
        st = deps.STEPS[n]
        rows.append((i, st.label, who(case, n), cost_of(n, w), ns(s['est'][n]),
                     '在最長路徑上' if not s['slack'][n] else ns(s['slack'][n])))
    return table(('#', '步驟，圖上的字', '誰做', '成本 ns', '最早能開始 ns', '可以晚多少 ns'), rows)


def md_edges(case):
    E = deps.reduced(case)
    order = deps.nodes(case)
    rows = []
    for (a, b), v in sorted(E.items(), key=lambda kv: (order.index(kv[0][1]), order.index(kv[0][0]))):
        why = []
        if v['kind'] == 'return':
            why.append('thread 離開 kernel 之前，這一段的每一步都要做完')
        if v['via']:
            why.append('兩步都碰 ' + code(v['via']) + '，至少一方是寫')
        r = v['rule']
        if r:
            why.append('規則：' + r.zh)
        rows.append((deps.STEPS[a].label, deps.STEPS[b].label, '。'.join(why),
                     f'`{r.witness}`' if r and r.witness else ''))
    return table(('先', '後', '為什麼有先後', '拿掉會被哪個 mutant 抓到'), rows)


def md_case(case, w, level='####'):
    s = deps.schedule(case, w)
    off = [deps.STEPS[n].label for n in deps.nodes(case) if s['slack'][n]]
    head = (f'{level} `{case}`：{deps.CASE_ZH[case]}\n\n'
            f'![{deps_fig.CASE_EN[case]}]({FIG}graph-{case}.svg)\n\n'
            f'{len(deps.nodes(case))} 個步驟。一步接一步做完是 {ns(s["serial"])} ns，圖上最長的路徑是 {ns(s["span"])} ns。')
    if off:
        head += '不在最長路徑上的步驟：' + '、'.join(off) + '。'
    else:
        head += '每一步都在最長路徑上。'
    return '\n\n'.join((head, md_steps(case, w), '先後關係，已去掉可以由其他關係推得的：', md_edges(case)))


def md_glossary():
    seen, rows = set(), []
    for c in deps.CASES:
        for n in deps.nodes(c):
            if n in seen:
                continue
            seen.add(n)
            st = deps.STEPS[n]
            rows.append((st.label, st.zh, code(sorted(st.r)), code(sorted(st.w)), code(st.cost) or ('未知' if st.unknown else '')))
    return table(('步驟，圖上的字', '做什麼', '讀', '寫', '成本取自哪個參數'), rows)


def md_weights(w):
    used = sorted({k for c in deps.CASES for n in deps.nodes(c) for k in deps.STEPS[n].cost})
    rows = [(f'`{k}`', ns(w[k]), '時間模型量到的 LZ4 HW job 平均時間' if k.startswith('hw_') else '`ifsim.params` 的預設值，假設')
            for k in used]
    return table(('成本', 'ns', '來源'), rows)


def md_timeline(w):
    rows = []
    for c in deps_fig.TIMELINE:
        o = deps.overlap([(c, c, 0)], w)[0]
        by = {k: 0 for k in WHO_ZH}
        for k, _, a, b in o['segs']:
            by[k] += b - a
        rows.append([f'`{c}`'] + [ns(by[k]) for k in ('cpu', 'lock', 'kernel', 'hw', 'notify')] + [ns(o['end'])])
    return table(('動作', 'CPU 進出 exception', 'kernel，握 mm_lock', 'kernel，不握 lock', 'LZ4 HW job',
                  'interrupt 與叫醒', '合計 ns'), rows)


# ------------------------------------------------------------------ the checks
def md_occurrences():
    rows = []
    for case, (want, got) in deps.occurrences().items():
        rows.append((f'`{case}`', len(want), len(got), '相同' if list(want) == list(got) else '**不同**'))
    return table(('動作', '宣告推得的 log 筆數', '真實執行的 log 筆數', '逐筆比對'), rows)


def md_trace_runs(t):
    rows = [(r['name'], ns(r['accesses']), r['results'].get('first_touch', 0), r['results'].get('fault_ro', 0),
             r['results'].get('fault_rw', 0), r['results'].get('rw_unmaps', 0), r['results'].get('lost', 0))
            for r in t['runs']]
    return table(('執行', 'access', 'first touch', 'fault RO', 'fault RW', '趕出 RW page', 'LOST'), rows)


def md_lock(t):
    rows = []
    for name, v in t['lock'].items():
        held, free = v.get('held', 0), v.get('free', 0)
        how = '一律握著 mm_lock' if not free else '從不握 mm_lock' if not held else '兩種都有'
        rows.append((f'`{name}`', ns(held), ns(free), how))
    return table(('kernel 碰的東西', '握著 lock 時的次數', '沒握 lock 時的次數', '結論'), rows)


def md_rules():
    rows = []
    for r in deps.RULES:
        used = [c for c in deps.CASES if r.a in deps.nodes(c) and r.b in deps.nodes(c)]
        rows.append((deps.STEPS[r.a].label, deps.STEPS[r.b].label, r.zh + ('。' + r.note if r.note else ''),
                     f'`{r.witness}`' if r.witness else '沒有', len(used)))
    return table(('先', '後', '理由', '見證的 mutant', '出現在幾個動作'), rows)


def md_atomic():
    rows = [('、'.join(deps.STEPS[n].label for n in steps), zh, f'`{wit}`') for steps, _, zh, wit in deps.ATOMIC]
    return table(('要在同一段 critical section 裡的步驟', '為什麼', '拆開會被哪個 mutant 抓到'), rows)


# ------------------------------------------------------------------ between operations
SHARED = ('free_frames', 'frame_waiters', 'reclaimer', 'fresh_n[*]', 'hand', 'owner[*]', 'state[*]', 'accessed[*]',
          'tlb', 'bitmap', 'pool_full', 'incompressible', 'strikes', 'lz4_off', 'tag', 'job_ring', 'cpl_ring', 'engine')
SHARED_ZH = {
    'free_frames': 'free frame list', 'frame_waiters': '等 frame 的 thread', 'reclaimer': '叫醒 reclaimer',
    'fresh_n[*]': '每個 thread 剛拿回來、還沒重跑的 page', 'hand': 'clock 的指針', 'owner[*]': 'frame 屬於哪個 page，掃描時整張讀',
    'state[*]': 'page 的 state，掃描時整張讀', 'accessed[*]': 'accessed bit，掃描時讀也清', 'tlb': '所有 core 的 TLB',
    'bitmap': 'chunk pool 的 bitmap', 'pool_full': 'chunk pool 滿了的記號', 'incompressible': '壓不小的 page 名單',
    'strikes': 'LZ4 HW 連續出錯的次數', 'lz4_off': 'LZ4 HW 已停用', 'tag': '下一個 job 的 tag',
    'job_ring': 'job ring', 'cpl_ring': 'completion ring', 'engine': 'LZ4 HW 的引擎，一次一個 job'}


RING_GUARD = {'tag': '不靠 mm_lock。介面規格的 `ring_lock`', 'job_ring': '不靠 mm_lock。介面規格的 `ring_lock`',
              'cpl_ring': '不靠 mm_lock。driver 依 tag 把 completion 交給送出那個 job 的 thread',
              'accessed[*]': 'kernel 這一側靠 mm_lock。CPU MMU 設 bit 時不經過 lock'}


def md_shared(t):
    rows = []
    for name in SHARED:
        rd, wr = [], []
        for c, uses in deps.users_of(deps.base(name)).items():
            if c in APPENDIX and c != 'evict_rw_incompressible':
                continue
            for step, mode, _ in uses:
                lab = deps.STEPS[step].label
                if 'W' in mode and lab not in wr:
                    wr.append(lab)
                if 'R' in mode and lab not in rd:
                    rd.append(lab)
        v = t['lock'].get(name, {})
        guard = (RING_GUARD[name] if name in RING_GUARD else
                 'mm_lock' if v and not v.get('free') else '不靠 mm_lock' if v and not v.get('held') else
                 'LZ4 HW 自己' if name == 'engine' else 'mm_lock' if name in ('fresh_n[*]', 'owner[*]', 'state[*]', 'accessed[*]') else '')
        rows.append((f'`{name}`', SHARED_ZH[name], '、'.join(wr), '、'.join(x for x in rd if x not in wr), guard))
    return table(('共用的東西', '是什麼', '誰寫', '誰只讀', '靠什麼保護'), rows)


def md_pairs():
    pairs = (('fault_ro', 'fault_ro'), ('fault_rw', 'fault_rw'), ('first_touch', 'fault_rw'), ('fault_rw', 'evict_ro'),
             ('fault_rw', 'evict_rw'), ('evict_rw', 'evict_rw'))
    rows = [(f'`{a}`', f'`{b}`', code(sorted(deps.shared_between(a, b)))) for a, b in pairs]
    return table(('動作一', '動作二，不同 page', '兩邊都碰、至少一邊寫的東西'), rows)


def md_together(w):
    rows = []
    for o in deps.overlap(list(deps.SHOWN_TOGETHER), w):
        alone = deps.schedule(o['case'], w)['serial']
        wl = sum(b - a for k, _, a, b in o['segs'] if k == 'wait_lock')
        we = sum(b - a for k, _, a, b in o['segs'] if k == 'wait_engine')
        rows.append((o['label'], ns(o['start']), ns(alone), ns(o['end'] - o['start']), ns(wl), ns(we)))
    return table(('誰', '開始 ns', '單獨跑 ns', '一起跑 ns', '等 mm_lock ns', '等 LZ4 引擎 ns'), rows)


# ------------------------------------------------------------------ capacity
def md_demand(cap):
    rows = [(f'`{r["case"]}`', ns(r['n']), ns(r['lock']), ns(r['engine']), ns(r['cpu']), ns(r['chain']),
             pct(cap['lock_by_case'][r['case']])) for r in cap['rows']]
    return table(('動作', '基準執行裡的次數', '握 mm_lock ns', '佔 LZ4 引擎 ns', '佔 CPU ns', '整條 ns', '佔全部握 lock 時間'), rows)


def md_capacity(cap):
    rows = []
    for k, zh in (('lock', 'mm_lock'), ('engine', f'LZ4 引擎，{cap["engines"]} 個，平均每個'),
                  ('reclaimer', 'reclaimer thread，一次一個 page')):
        share = cap['share'][k]
        m = cap['measured'].get(k)
        rows.append((zh, ns(round(cap['per_fault_ns'][k])), pct(share, 2), pct(m, 2) if m is not None else '沒有直接量',
                     f'{1 / share:.0f} 倍'))
    return table(('數量有限的東西', '每次 fault 平均用掉 ns', '由步驟成本算出的忙碌比例', '時間模型量到的', '照比例還能撐幾倍負載'), rows)


def md_what_if(cap, w):
    base = cap['use_ns']['lock']
    count = {r['case']: r['n'] for r in cap['rows']}
    rows = [('現在', ns(round(base / cap['faults'])), pct(base / cap['t_end_ns'], 2), '')]
    saved_all = 0
    for label, moves in WHAT_IF:
        saved = sum(count[c] * sum(deps.cost(n, w) for n in steps) for c, steps in moves.items())
        saved_all += saved
        rows.append((label, ns(round((base - saved) / cap['faults'])), pct((base - saved) / cap['t_end_ns'], 2),
                     pct(saved / base)))
    rows.append(('以上三項都做', ns(round((base - saved_all) / cap['faults'])), pct((base - saved_all) / cap['t_end_ns'], 2),
                 pct(saved_all / base)))
    return table(('做法', '每次 fault 平均握 lock ns', 'mm_lock 忙碌比例', '少掉的握 lock 時間'), rows)


def md_holds(hs):
    rows = []
    for h in hs:
        for who_, zh in (('fault', 'fault 路徑'), ('reclaim', 'reclaimer')):
            r = h[who_]
            rows.append((h['cfg'], zh, ns(r['holds']), ns(r['ns_mean']), ns(r['ns_p50']), ns(r['ns_p99']), ns(r['ns_max']),
                         r['victims_max'], ns(r['frames_p50']), ns(r['frames_p99']), ns(r['frames_max'])))
    return table(('機器', '誰握 lock', '握的次數', '平均 ns', 'p50 ns', 'p99 ns', '最長 ns', '一次最多趕出幾個 page',
                  '掃過的 frame p50', 'p99', '最多'), rows)


def md_load(T):
    rows = []
    for key, v in T['sweeps']['load']['rows']:
        if key['wait_mode'] != 'irq':
            continue
        p = v['fault_ro_parts']
        rows.append((ns(key['think_ns']), f'{20000 // key["think_ns"]} 倍', ns(v['p50']), ns(v['p99']), pct(v['engine_util']),
                     pct(v['mm_lock_busy']), ns(v['frame_waits']), ns(round(p['lock'])), ns(round(p['frame'])),
                     ns(round(p['queue']))))
    return table(('兩次 access 之間 ns', '負載', 'fault p50 ns', 'p99 ns', 'LZ4 引擎忙，平均每個', 'mm_lock 忙', '等不到 frame 的次數',
                  '一次 RO fault 裡等 lock ns', '等 frame ns', '在 ring 裡排隊 ns'), rows)


def md_inflight(T):
    rows = []
    for key, v in T['sweeps']['reclaim_inflight']['rows']:
        if key['engines'] not in (1, 4):
            continue
        p = v['fault_ro_parts']
        rows.append((key['engines'], key['reclaim_inflight'], ns(v['p50']), ns(v['p99']), ns(v['max']), ns(v['frame_waits']),
                     ns(round(p['frame'])), ns(round(p['queue'])), ns(v['part_max']['queue']), ns(v['part_max']['hw']),
                     ns(v['part_max']['inflight'])))
    return table(('engine 數', 'reclaimer 同時送出的 COMPRESS', 'fault p50 ns', 'p99 ns', '最大 ns', '等不到 frame 的次數',
                  '一次 RO fault 裡等 frame ns', '在 ring 裡排隊 ns', '在 ring 裡排隊，最長的一次 ns', 'HW 那一段，最長的一次 ns',
                  '等同一個 page 的 job，最長的一次 ns'), rows)


def all_busy_max(T):
    """The largest share of time all engines held a job, over every run with the default number of engines."""
    n = T['base_irq']['engines']
    shares = [T['base_irq']['hw_all_share']] + [v['hw_all_share'] for s in T['sweeps'].values() for _, v in s['rows']
                                                  if 'stalled' not in v and v['engines'] == n]
    return pct(max(shares), 1)


def worst_cases(T):
    """The longest single waits the timed model saw, for the hand-written text about N engines."""
    def rows(sweep, engines, **fixed):
        return [v for k, v in T['sweeps'][sweep]['rows']
                if k['engines'] == engines and all(k[a] == b for a, b in fixed.items())]
    out = {'q1_base': T['base_irq_e1']['part_max']['queue'], 'q4_base': T['base_irq']['part_max']['queue']}
    for e in (1, 4):
        full = rows('full_load', e)
        out[f'full{e}_q_max'] = max(v['part_max']['queue'] for v in full)
        out[f'full{e}_hw_max'] = max(v['part_max']['hw'] for v in full)
        out[f'full{e}_i_max'] = max(v['part_max']['inflight'] for v in full)
        several = [v for k, v in T['sweeps']['reclaim_inflight']['rows'] if k['engines'] == e and k['reclaim_inflight'] >= 2]
        out[f'in{e}_p99_lo'] = min(v['p99'] for v in several)
        out[f'in{e}_p99_hi'] = max(v['p99'] for v in several)
        out[f'in{e}_q_max'] = max(v['part_max']['queue'] for v in several)
        out[f'in{e}_q8'] = round(rows('reclaim_inflight', e, reclaim_inflight=8)[0]['fault_ro_parts']['queue'])
        heavy = rows('engines_load', e, think_ns=500)[0]
        out[f'heavy{e}_q_max'] = heavy['part_max']['queue']
        out[f'heavy{e}_hw_max'] = heavy['part_max']['hw']
    # the slowest fault of the heaviest full-size run that has no frame waits: N engines, 10 times the load, 2 COMPRESS out
    w = rows('full_load', 4, think_ns=2000, reclaim_inflight=2)[0]['worst']
    out['full4_worst'] = w['ns']
    out['full4_worst_i'] = w['parts'].get('inflight', 0)
    return {k: ns(v) for k, v in out.items()}


def md_parts(T):
    rows = []
    for name, zh in (('base_irq', 'interrupt'), ('base_poll', 'polling')):
        b = T[name]
        p = b['parts']['fault_ro']
        rows.append((zh, ns(b['lat']['fault_ro']['p50']), ns(b['lat']['fault_ro']['p99']), ns(round(p['cpu'])),
                     ns(round(p['lock'])), ns(round(p['submit'])), ns(round(p['queue'])), ns(round(p['hw'])),
                     ns(round(p['notify'])), pct(b['kernel_cpu_share'], 2)))
    return table(('等 completion 的方式', 'RO fault p50 ns', 'p99 ns', 'CPU 與 kernel', '等 lock', '送 job', '在 ring 裡排隊',
                  'HW', '通知', 'kernel 佔 CPU'), rows)


# ------------------------------------------------------------------ the document
def render(nums):
    T = timed()
    base = T['base_irq']
    w = deps.weights(base)
    cap = deps.capacity(base)
    t = nums['trace']
    full = next(h for h in nums['holds'] if h['cfg'] == 'full')
    small = next(h for h in nums['holds'] if h['cfg'] == 'small')
    sch = {c: deps.schedule(c, w) for c in deps.CASES}
    tog = {o['case']: o for o in deps.overlap(list(deps.SHOWN_TOGETHER), w)}
    rare = [f'{"、".join(r["steps"])} 寫 `{x[1]}`' for r in t['rows'] for x in r['rare_unseen']]
    notify = w['irq_latency_ns'] + w['irq_handler_ns'] + w['wakeup_ns']
    hi = T['sweeps']['load']['rows']
    worst = next(v for k, v in hi if k['wait_mode'] == 'irq' and k['think_ns'] == 500)
    extra = {
        'summary': md_summary(w), 'weights': md_weights(w), 'glossary': md_glossary(), 'timeline': md_timeline(w),
        'occurrences': md_occurrences(), 'trace_runs': md_trace_runs(t), 'lock_table': md_lock(t),
        'rules': md_rules(), 'atomic': md_atomic(), 'shared': md_shared(t), 'pairs': md_pairs(),
        'together': md_together(w), 'demand': md_demand(cap), 'capacity': md_capacity(cap),
        'what_if': md_what_if(cap, w), 'holds': md_holds(nums['holds']), 'load': md_load(T),
        'inflight': md_inflight(T), 'parts': md_parts(T),
        'appendix': '\n\n'.join(md_case(c, w, '###') for c in APPENDIX),
        'n_steps': len({n for c in deps.CASES for n in deps.nodes(c)}), 'n_cases': len(deps.CASES),
        'n_rules': len(deps.RULES), 'n_witness': sum(1 for r in deps.RULES if r.witness),
        'n_mutants': len(conc.MUTANTS), 'n_groups': len(t['rows']),
        'n_undeclared': sum(len(r['undeclared']) for r in t['rows']),
        'n_unseen': sum(len(r['unseen']) for r in t['rows']), 'n_stray': len(t['stray']),
        'rare': '；'.join(rare) if rare else '沒有',
        'trace_accesses': ns(sum(sum(v.values()) for v in t['lock'].values())),
        'notify_ns': ns(notify), 'fault_ro_serial': ns(sch['fault_ro']['serial']),
        'notify_share': pct(notify / sch['fault_ro']['serial'], 0),
        'hw_dec': ns(w['hw_decompress']), 'hw_comp': ns(w['hw_compress']),
        'hw_dec_share': pct(w['hw_decompress'] / sch['fault_ro']['serial'], 0),
        'exc_ns': ns(w['fault_entry_ns'] + w['fault_exit_ns']),
        'exc_share': pct((w['fault_entry_ns'] + w['fault_exit_ns']) / sch['fault_ro']['serial'], 0),
        'engines': cap['engines'], **worst_cases(T), 'all_busy_max': all_busy_max(T),
        'faults_per_s': ns(round(cap['faults_per_s'])), 'lock_share': pct(cap['share']['lock'], 1),
        'engine_share': pct(cap['share']['engine'], 1), 'reclaimer_share': pct(cap['share']['reclaimer'], 1),
        'lock_first_share': pct(cap['lock_by_case']['first_touch'], 0),
        'lock_evict_share': pct(sum(v for k, v in cap['lock_by_case'].items() if k.startswith('evict')), 0),
        'full_frames': ns(full['frames']), 'full_scan_max': ns(full['reclaim']['frames_max']),
        'full_hold_max': ns(full['reclaim']['ns_max']), 'full_victims_max': full['reclaim']['victims_max'],
        'full_picks': ns(full['clock_picks']), 'full_steps': ns(full['clock_steps']),
        'full_scan_mean': f'{full["clock_steps"] / full["clock_picks"]:.1f}',
        'small_scan_max': ns(small['reclaim']['frames_max']), 'small_frames': ns(small['frames']),
        'pick_ns': ns(w['victim_pick_ns']),
        'scan_10': ns(full['reclaim']['frames_max'] * 10 // 1000), 'scan_2': ns(full['reclaim']['frames_max'] * 2 // 1000),
        'tog_ro': ns(tog['fault_ro']['end'] - tog['fault_ro']['start']),
        'tog_rw': ns(tog['fault_rw']['end'] - tog['fault_rw']['start']),
        'worst_engine': pct(worst['engine_util'], 0), 'worst_lock': pct(worst['mm_lock_busy'], 0),
        'worst_frame': ns(round(worst['fault_ro_parts']['frame'])), 'worst_p50': ns(worst['p50']),
        'poll_p50': ns(T['base_poll']['lat']['fault_ro']['p50']), 'irq_p50': ns(base['lat']['fault_ro']['p50']),
        'poll_kcpu': pct(T['base_poll']['kernel_cpu_share'], 2), 'irq_kcpu': pct(base['kernel_cpu_share'], 2),
        'tlb_ns': ns(w['tlb_inval_ns']), 'zero_ns': ns(w['zero_fill_ns']), 'fig': FIG,
        'full_scan_at': full['scan_max_at'], 'full_scan_rest': ns(full['scan_rest_max']),
        'small_scan_at': small['scan_max_at'], 'small_scan_rest': ns(small['scan_rest_max']),
        'ring_waited': ns(base['ring_lock']['waited']), 'ring_grants': ns(base['ring_lock']['grants']),
        'ring_busy': pct(base['ring_lock']['busy_share'], 2),
    }
    for c in deps.CASES:
        extra['case:' + c] = (lambda c=c: md_case(c, w))
        extra[f'serial:{c}'] = ns(sch[c]['serial'])
        extra[f'span:{c}'] = ns(sch[c]['span'])
    with open(TEMPLATE, encoding='utf-8') as f:
        return fill(f.read(), extra)


def collect():
    """The parts that take a run, in the shape they have after a trip through the JSON file."""
    return json.loads(json.dumps(deps.measure(), default=list))


def write(reuse=False):
    path = os.path.join(SPEC_DIR, NUMBERS)
    if reuse:
        with open(path, encoding='utf-8') as f:
            nums = json.load(f)
    else:
        nums = collect()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(nums, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write('\n')
    doc = os.path.join(SPEC_DIR, DOC)
    with open(doc, 'w', encoding='utf-8') as f:
        f.write(render(nums))
    figs = deps_fig.write(deps.weights(timed()['base_irq']))
    return [doc, path] + list(figs or [])

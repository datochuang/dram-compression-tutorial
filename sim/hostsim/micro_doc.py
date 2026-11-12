"""Generate spec/kernel-step-detail-v0.md from micro.py.

The instruction counts take a build and a run of sim/kstep/measure.c on an AArch64 Mac, and the scan lengths
take two runs of the host simulation, so both are kept beside the document in a JSON file. --reuse renders
the document again from that file.
"""
import json
import os

from ifsim.gen import fill
from ifsim.report import table

from . import deps, deps_doc, micro

SPEC_DIR = deps_doc.SPEC_DIR
TEMPLATE = os.path.join(micro.HERE, 'templates', 'kernel_step_detail.tmpl.md')
DOC, NUMBERS = 'kernel-step-detail-v0.md', 'kernel-step-detail-v0.json'
ns = deps_doc.ns


def size(n):
    if n >= 1 << 20:
        return f'{n / (1 << 20):.1f} MiB'
    if n >= 1 << 10:
        return f'{n / (1 << 10):.0f} KiB' if n >= 10 << 10 else f'{n / (1 << 10):.1f} KiB'
    return f'{n} B'


def entry(e):
    return '1 bit' if e < 1 else f'{e} B'


def weights():
    return deps.weights(deps_doc.timed()['base_irq'])


# ------------------------------------------------------------------------------------------------ tables
def md_layout():
    rows = []
    for r in micro.layout():
        at = f'{r["base"]:#010x}' if r['base'] else ''
        rows.append((f'`{r["name"]}`', micro.WHERE_ZH[r['where']], at, entry(r['entry']), ns(r['entries']),
                     size(r['bytes']), ns(r['lines']), r['holds']))
    return table(('資料結構', '放在哪', '固定位址', '一筆', '筆數', '總大小', 'cache line 數', '內容'), rows)


def md_map():
    z = micro.sizes()
    rows = [('pinned 區', z['pinned_base'], z['hrt_base'], 'kernel 的程式與所有 kernel 記憶體、page table、兩個 ring'),
            ('HRT 區', z['hrt_base'], z['cot_base'], 'HRT client 的記憶體，不壓縮，這份文件的步驟都不碰'),
            ('COT 區', z['cot_base'], z['pool_base'], '`cot`'),
            ('chunk pool', z['pool_base'], z['fc_base'], '`chunk`'),
            ('frame 區', z['fc_base'], z['dram_end'], '`frame`')]
    return table(('區域', '起點', '終點', '大小', '放什麼'),
                 [(n, f'{a:#010x}', f'{b:#010x}', size(b - a), what) for n, a, b, what in rows])


def md_model(nums):
    m = nums['model']
    rows = [('CPU 時脈', f'{m["cpu_hz"] // 1_000_000} MHz', '1 cycle 等於 1 ns，數字可以直接和 `ifsim.params` 的 ns 並排。待 K1'),
            ('每道指令的 cycle', m['cpi'], '需要的 line 都在 L1 cache 裡的時候。待 K1'),
            ('一條 line 從 DRAM 進來', f'{m["miss"]} cycle', '`lz4sim.config` 的 `dram_ns` 100 ns'),
            ('寫一次 LZ4 HW register', f'{m["mmio"]} cycle', '`ifsim.params` 的 `mmio_ns` 50 ns')]
    return table(('假設', '值', '來源'), rows)


def acc_text(a, where=True):
    tbl, mode, nbytes, index, temp, _ = a
    name = f'`{tbl}[{index}]`' if tbl not in ('scalars', 'reg') else '、'.join(f'`{x}`' for x in index.split())
    out = f'{name} {mode} {entry(nbytes) if nbytes != 8 or tbl != "incompressible" else "1 bit"}'
    if where:
        out += '，' + micro.WHERE_ZH[micro.TABLES[tbl][0]]
    return out


TEMP_ZH = {'line': '1 條', 'dram': '1 條，一定從 DRAM', 'seq': '每 16 筆 1 條', 'bulk': '64 條'}


def lines_text(d):
    out = []
    for a in d.acc:
        if a[4] in TEMP_ZH:
            out.append(f'`{a[0]}` {TEMP_ZH[a[4]]}')
    return '；'.join(out) or '0'


def md_steps(nums):
    M, w = nums['measure'], weights()
    rows = []
    for name in ('lock', 'unlock') + tuple(deps.STEPS):
        d = micro.LOCK.get(name) or micro.DETAIL[name]
        who = 'FW' if name in micro.LOCK else deps.STEPS[name].who
        n = micro.instr(name, M)
        if name == 'desc':
            n = f'{M["steps"]["desc_decompress"]["instr"]} 或 {M["steps"]["desc_compress"]["instr"]}'
        if name in ('pick_victim', 'reserve'):
            n = '見 3.3'
        a = None if name in micro.LOCK else micro.assumed_ns(name, w)
        cell = n if n is not None else {'assumed': f'假設 {ns(a)} ns' if a else '假設',
                                         'hw': f'模型 {ns(a)} ns' if a else '', 'counted': '64 次 cache 操作',
                                         'unknown': '沒有量', 'cpu': '', 'os': ''}[d.basis]
        op = d.op + ('。' + d.also if d.also else '')
        rows.append((f'`{name}`', who, '<br>'.join(acc_text(x) for x in d.acc if x[4] != 'none') or '無',
                     op, cell, lines_text(d), micro.BASIS_ZH[d.basis]))
    return table(('步驟', '誰', '讀寫的資料與所在', '運算', '指令數', '碰到的 cache line', '依據'), rows)


def md_sweeps(nums):
    S = nums['measure']['steps']
    g = lambda k: S[k]['instr']
    first = g('pick_victim.rw_first')
    pick = [('最後選中的那一個，RW page', g('pick_victim.rw_first'), '`owner`、`state`、`pins`、`fresh_n`、`pte` 各 1 條'),
            ('最後選中的那一個，RO page', g('pick_victim.ro_first'), '同上'),
            ('路過一個空的 frame', round((g('pick_victim.16_free') - first) / 16), '只有 `owner`，每 16 個 frame 1 條'),
            ('路過一個 fresh 的 page', round((g('pick_victim.16_fresh') - first) / 16), '`state`、`pins`、`fresh_n` 各 1 條'),
            ('路過一個已知壓不小的 RW page', round((g('pick_victim.16_incompressible') - first) / 16),
             '`state`、`pins`、`fresh_n` 各 1 條'),
            ('路過一個 accessed 的 page，並清掉 bit 10', round((g('pick_victim.16_accessed') - first) / 16),
             '`state`、`pins`、`fresh_n`、`pte` 各 1 條')]
    res = [(zh, words, g(k)) for k, zh, words in (
        ('reserve.empty_pool', '全部是空的', '1.11'), ('reserve.2_words', '每個 word 剩 7 個 0', '2'),
        ('reserve.11_words', '每 10 個 word 才有一個不是全 1，那一個剩 7 個 0', '11'),
        ('reserve.7_words', '每個 word 只剩 1 個 0', '7'))]
    skip = round((g('reserve.11_words') - g('reserve.2_words')) / 9)
    return {'pick': table(('clock 掃描看的 frame', '指令數', '碰到的 cache line'), pick),
            'reserve': table(('bitmap 的樣子', '掃過的 word', '指令數'), res), 'reserve_skip': skip,
            'reserve_chunk': round((g('reserve.2_words') - 2 * skip) / 7)}


def md_runs(nums):
    rows = []
    for cfg, r in nums['runs'].items():
        rows.append((f'`{cfg}`', ns(r['accesses']), ns(r['frames']), ns(r['picks']), f'{r["looked"] / r["picks"]:.1f}',
                     ns(r['longest']), ns(r['reserves']), f'{r["words"] / r["reserves"]:.2f}', r['words_max']))
    return table(('設定', '存取次數', 'frame 數', 'clock 選了幾次', '每次平均看幾個 frame', '最長一次',
                  '`reserve` 次數', '每次平均掃幾個 word', '最多'), rows)


WHO_ZH = {'CPU': 'CPU', 'HW': 'LZ4 HW', 'FW': 'kernel'}
KIND_ZH = {'data': '資料', 'rule': '規則', 'return': '返回'}


def cyc_cell(r):
    if r['instr'] is not None:
        out = f'{r["lo"]}' if r['lo'] == r['hi'] else f'{r["lo"]} 到 {r["hi"]}'
        return out + (f'，另寫 {r["bulk"]} 條 line' if r['bulk'] else '')
    a = r['assumed']
    return {'assumed': f'假設 {ns(a)}' if a else '假設，沒有數字', 'hw': f'模型 {ns(a)}' if a else '模型',
            'counted': '64 次 cache 操作，時間未知', 'unknown': '沒有量', 'cpu': 'CPU 硬體，未計',
            'os': 'OS，未計'}[r['basis']]


def md_case(case, nums):
    M, w = nums['measure'], weights()
    rows = []
    for r in micro.walk(case, M, w):
        d = micro.LOCK.get(r['step']) or micro.DETAIL[r['step']]
        after = '；'.join(f'{n} `{a}`（{KIND_ZH[k]}{"：" + "、".join(via) if via else ""}）' for n, a, k, via, _ in r['after'])
        if r['step'] in micro.LOCK:
            after = ''
        rows.append((r['n'] or '', f'`{r["step"]}`', WHO_ZH[r['who']], r['section'] or '',
                     '<br>'.join(acc_text(x, where=False) for x in d.acc if x[4] != 'none') or '',
                     r['instr'] if r['instr'] is not None else '', r['new'] or '', cyc_cell(r), after or
                     ('' if r['step'] in micro.LOCK else '沒有：最先能做')))
    return table(('#', '步驟', '誰', 'lock 段', '讀寫', '指令數', '新的 line', 'cycle', '要等誰做完'), rows)


def lock_sections(rows):
    """Per lock section: instructions, new lines, low and high cycles, and the steps in it without a count."""
    secs = {}
    for r in rows:
        if r['section'] and r['instr'] is not None:
            s = secs.setdefault(r['section'], [0, 0, 0, 0, []])
            s[0] += r['instr']; s[1] += r['new']; s[2] += r['lo']; s[3] += r['hi']
        if r['section'] and r['instr'] is None and r['step'] not in micro.LOCK:
            secs.setdefault(r['section'], [0, 0, 0, 0, []])[4].append(r['step'])
    return secs


def md_case_block(case, nums):
    M, w = nums['measure'], weights()
    rows = micro.walk(case, M, w)
    t = micro.totals(rows)
    secs = lock_sections(rows)
    hold = '；'.join(f'第 {k} 段 {v[0]} 道指令、{v[1]} 條新的 line，{v[2]} 到 {v[3]} cycle'
                     + (f'，另加 {"、".join("`" + x + "`" for x in v[4])}' if v[4] else '') for k, v in secs.items())
    head = (f'### 4.{list(deps.CASES).index(case) + 1} `{case}`：{deps.CASE_ZH[case]}\n\n'
            f'kernel 自己跑、量得到的步驟共 {t["steps"]} 個：{t["instr"]} 道指令，{t["new"]} 條新的 cache line，'
            f'{t["mmio"]} 次 register 寫入。照第 1 節的模型是 {ns(t["lo"])} 到 {ns(t["hi"])} cycle。'
            f'握 lock 的部分：{hold}。')
    return head + '\n\n' + md_case(case, nums)


def md_summary(nums):
    M, w = nums['measure'], weights()
    rows = []
    for case in deps.CASES:
        t = micro.totals(micro.walk(case, M, w))
        rows.append((f'`{case}`', t['instr'], t['new'], t['mmio'], f'{ns(t["lo"])} 到 {ns(t["hi"])}', ns(t['old_ns']),
                     ns(t['assumed_ns']), ns(t['hw_ns']) if t['hw_ns'] else '', '、'.join(f'`{x}`' for x in t['open'])))
    return table(('場景', '指令數', '新的 line', 'register 寫入', '模型 cycle', '同一批步驟原本的假設 ns',
                  'CPU 與 OS 的假設 ns', 'LZ4 HW 模型 ns', '沒有數字的步驟'), rows)


def md_compare(nums):
    """Each ifsim.params assumption for a kernel step beside what the step measures to."""
    M, w = nums['measure'], weights()
    S = M['steps']
    m = nums['model']
    rows = []
    for name, key, lines, mmio in (('take_frame', 'take_frame', 2, 0), ('zero_frame', 'zero_frame', 0, 0),
                                   ('cot_read', 'cot_read', 1, 0), ('cot_clear', 'cot_clear', 1, 0),
                                   ('cot_store', 'cot_store', 1, 0), ('release_chunks', 'release_chunks', 1, 0),
                                   ('pte_map', 'pte_map', 1, 0), ('desc', 'desc_decompress', 0, 0),
                                   ('submit', 'submit', 1, 1), ('cpl_read', 'cpl_read', 1, 1),
                                   ('reserve', 'reserve.2_words', 1, 0), ('pick_victim', 'pick_victim.rw_first', 5, 0)):
        n = S[key]['instr']
        lo = round(n * m['cpi'] + mmio * m['mmio'])
        rows.append((f'`{name}`', '、'.join(f'`{c}`' for c in deps.STEPS[name].cost), ns(deps.cost(name, w)), n, lines, mmio or '',
                     f'{lo} 到 {lo + lines * m["miss"]}'))
    return table(('步驟', '`ifsim.params` 的假設', '假設 ns', '量到的指令數', 'cache line', 'register 寫入', '模型 cycle'), rows)


# ------------------------------------------------------------------------------------------------ render
def render(nums):
    M, w = nums['measure'], weights()
    S = M['steps']
    sw = md_sweeps(nums)
    T = {c: micro.totals(micro.walk(c, M, w)) for c in deps.CASES}
    full, small = nums['runs']['full'], nums['runs']['small']
    m = nums['model']
    scan_mean = full['looked'] / full['picks']
    passed = scan_mean - 1
    first = S['pick_victim.rw_first']['instr']
    per = lambda k: (S[k]['instr'] - first) / 16
    cheap, dear = per('pick_victim.16_free'), per('pick_victim.16_accessed')
    scan_lines = round(5 + passed * 4)
    scan_hi = round(first + passed * dear)
    ro, rw = T['fault_ro'], T['evict_rw']
    sec = {c: lock_sections(micro.walk(c, M, w)) for c in ('fault_ro', 'evict_rw', 'first_touch')}
    rest = ro['assumed_ns'] + ro['hw_ns']
    extra = {
        'compiler': M['compiler'], 'flags': M['flags'], 'calib': S['calib5']['instr'],
        'n_steps': len(deps.STEPS), 'n_measured': sum(1 for d in micro.DETAIL.values() if d.key),
        'layout': md_layout(), 'map': md_map(), 'model': md_model(nums), 'steps': md_steps(nums),
        'sweep_pick': sw['pick'], 'sweep_reserve': sw['reserve'], 'reserve_skip': sw['reserve_skip'],
        'reserve_chunk': sw['reserve_chunk'], 'runs': md_runs(nums), 'summary': md_summary(nums),
        'compare': md_compare(nums),
        'cases': '\n\n'.join(md_case_block(c, nums) for c in deps.CASES),
        'ro_instr': T['fault_ro']['instr'], 'ro_new': T['fault_ro']['new'], 'ro_lo': ns(T['fault_ro']['lo']),
        'ro_hi': ns(T['fault_ro']['hi']), 'ro_old': ns(T['fault_ro']['old_ns']),
        'ro_platform': ns(T['fault_ro']['assumed_ns']), 'ro_hw': ns(T['fault_ro']['hw_ns']),
        'rw_instr': T['evict_rw']['instr'], 'rw_new': T['evict_rw']['new'], 'rw_lo': ns(T['evict_rw']['lo']),
        'rw_hi': ns(T['evict_rw']['hi']),
        'scan_mean': f'{scan_mean:.1f}', 'scan_small': f'{small["looked"] / small["picks"]:.1f}',
        'scan_passed': f'{passed:.1f}', 'scan_longest': ns(full['longest']), 'scan_frames': ns(full['frames']),
        'scan_instr_lo': round(first + passed * cheap), 'scan_instr_hi': scan_hi, 'scan_lines': scan_lines,
        'scan_cyc_hi': ns(scan_hi + scan_lines * m['miss']), 'scan_assumed': ns(w['victim_pick_ns']),
        'scan_long_lo': f'{full["longest"] * dear / 1e6:.1f}',
        'scan_long_hi': f'{full["longest"] * (dear + 4 * m["miss"]) / 1e6:.1f}',
        'per_free': round(cheap), 'per_accessed': round(dear),
        'ro_all_lo': ns(ro['lo'] + rest), 'ro_all_hi': ns(ro['hi'] + rest),
        'ro_share_lo': f'{100 * ro["lo"] / (ro["lo"] + rest):.0f}%', 'ro_share_hi': f'{100 * ro["hi"] / (ro["hi"] + rest):.0f}%',
        'ro_line_share': f'{100 * ro["new"] * m["miss"] / ro["hi"]:.0f}%',
        **{f'{tag}{k}_{name}': ns(v[i]) for tag, c in (('ro', 'fault_ro'), ('rw', 'evict_rw'), ('ft', 'first_touch'))
           for k, v in sec[c].items() for i, name in enumerate(('instr', 'new', 'lo', 'hi'))},
        'words_mean': f'{full["words"] / full["reserves"]:.2f}', 'words_max': full['words_max'],
        'reserve_instr': S['reserve.2_words']['instr'], 'zero_instr': S['zero_frame']['instr'],
        'copy_instr': S['frame_write']['instr'], 'desc_c': S['desc_compress']['instr'],
        'desc_d': S['desc_decompress']['instr'], 'cot_store': S['cot_store']['instr'],
        'kmem_total': size(sum(r['bytes'] for r in micro.layout() if r['where'] == 'kmem')),
        'pt_total': size(sum(r['bytes'] for r in micro.layout() if r['name'] == 'pte')),
        'cot_total': size(sum(r['bytes'] for r in micro.layout() if r['name'] == 'cot')),
        'page_tables': '、'.join(f'`{n}`' for n, _ in micro.per_page_lines()),
        'miss': m['miss'], 'mmio': m['mmio'],
    }
    with open(TEMPLATE, encoding='utf-8') as f:
        return fill(f.read(), extra)


def collect():
    return json.loads(json.dumps({'measure': micro.measure(), 'runs': micro.run_stats(), 'model': micro.MODEL}))


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
    return [doc, path]

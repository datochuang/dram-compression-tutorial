"""Generate spec/lz4-hw-design-spec-v0.md: the hardware design spec the RTL is written from.

The prose is in templates/lz4_hw_design_spec.tmpl.md. Everything that can be computed is
computed here: the worked example comes from running the reference models on the example
page, the code listings are the source of the reference models, the register and structure
tables come from interface.json, and the numbers of the parameter study come from a JSON
file kept beside the document (the study takes half a minute and its heap pages differ a
little from run to run).
"""
import inspect
import json
import os
import textwrap
from collections import Counter
from math import ceil

from ifsim.gen import fields, fill
from ifsim.report import table
from ifsim.spec import SPEC

from . import job as J
from . import lz4core as C
from . import study as S
from . import vectors as V

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'spec'))
TEMPLATE = os.path.join(HERE, 'templates', 'lz4_hw_design_spec.tmpl.md')
DOC, NUMBERS = 'lz4-hw-design-spec-v0.md', 'lz4-hw-design-spec-v0.json'
SHOWN = {'hash4': C.hash4, 'put_length': C.put_length, 'put_sequence': C.put_sequence, 'encode': C.encode,
         'decode': C.decode, 'check': J.check, 'compress': J.compress, 'decompress': J.decompress}
SLOT = 5                       # ring slot of the worked example, both rings
MHZ = (200, 400, 800)          # the clock is not known yet; times are shown for these


def source(fn):
    return '```python\n' + textwrap.dedent(inspect.getsource(fn)).rstrip() + '\n```'


def _hex(b):
    return ' '.join(f'{x:02X}' for x in b)


def _pa(x):
    return f'0x{x:08X}'


# ---- the worked example
def example():
    """The COMPRESS of the interface spec's example and the DECOMPRESS that brings the page back."""
    page = V.records_page()
    e = C.encode(page)
    d = V.desc(J.OP.COMPRESS, limit=3584)
    mem = J.Mem()
    mem.poke(d['frame_pa'], page)
    res = J.run(SPEC.pack('job_desc', d), V.REGS, mem)
    used = d['chunk'][:ceil(len(e.stream) / J.CHUNK)]
    d2 = V.desc(J.OP.DECOMPRESS, d['frame_pa'] + J.PAGE, used, comp_len=len(e.stream), checksum=C.crc32(e.stream), tag=0x2A9)
    mem2 = J.Mem()
    for i, c in enumerate(used):
        mem2.poke(V.REGS.chunk_pa(c), mem.peek(V.REGS.chunk_pa(c), J.CHUNK))
    res2 = J.run(SPEC.pack('job_desc', d2), V.REGS, mem2)
    assert res2.completion['status'] == J.ST.OK and mem2.peek(d2['frame_pa'], J.PAGE) == page
    return {'page': page, 'e': e, 'd': d, 'mem': mem, 'res': res, 'd2': d2, 'mem2': mem2, 'res2': res2}


def md_bursts(x, which):
    d, mem, res = (x['d'], x['mem'], x['res']) if which == 'c' else (x['d2'], x['mem2'], x['res2'])
    chunk_of = {V.REGS.chunk_pa(c): (i, c) for i, c in enumerate(d['chunk'][:d['count']])}
    rows = [('R', V.RING['JOB_BASE'] + SLOT * SPEC.const.JOB_SLOT_SIZE, 48, f'job ring 第 {SLOT} 格的 descriptor')]
    for kind, pa, n in mem.log:
        if pa in chunk_of:
            i, c = chunk_of[pa]
            what = f'`chunk[{i}]`，chunk 號碼 0x{c:05X}'
            if which == 'c':
                lo = i * J.CHUNK
                hi = min(len(x['e'].stream), lo + J.CHUNK)
                what += f'：stream 的 byte {lo} 到 {hi - 1}' + (f'，後面 {lo + J.CHUNK - hi} B 是補的' if hi < lo + J.CHUNK else '')
        else:
            o = pa - d['frame_pa']
            what = f'frame 的 byte {o} 到 {o + n - 1}'
        rows.append((kind, pa, n, what))
    rows.append(('W', V.RING['CPL_BASE'] + SLOT * SPEC.const.CPL_SLOT_SIZE, 16, f'completion ring 第 {SLOT} 格'))
    return table(('#', '方向', '位址', '大小 B', 'beat', '內容'),
                 [(i + 1, '讀' if k == 'R' else '寫', _pa(pa), n, n // C.BEAT, what) for i, (k, pa, n, what) in enumerate(rows)])


def md_trace(x):
    """The encoder on the first positions of the example page, up to and with its first match."""
    page = x['page']
    tab, rows = {}, []
    for ip in range(J.PAGE):
        w = int.from_bytes(page[ip:ip + 4], 'little')
        h = C.hash4(w)
        cand = tab.get(h)
        tab[h] = ip
        if cand is None:
            seen, verdict = '空', '沒有 candidate，這個 byte 是 literal'
        elif int.from_bytes(page[cand:cand + 4], 'little') != w:
            seen, verdict = str(cand), f'位置 {cand} 的 4 個 byte 不同，這個 byte 是 literal'
        else:
            seen, verdict = str(cand), f'**位置 {cand} 的 4 個 byte 相同：match，offset 是 {ip - cand}**'
        rows.append((ip, f'`{_hex(page[ip:ip + 4])}`', f'0x{w:08X}', f'0x{h:03X}', seen, ip, verdict))
        if verdict.startswith('**'):
            break
    return table(('`ip`', '`page[ip..ip+3]`', '`word`', '`h`', '讀到的 `table[h]`', '寫入 `table[h]`', '結果'), rows)


def _parts(page, pos, ll, ml, off):
    """One sequence as the pieces it is written in."""
    tok = (min(ll, 15) << 4) | (min(ml - C.MINMATCH, 15) if ml else 0)
    out = [('token', bytes([tok]))]
    ext = bytearray()
    if ll >= 15:
        C.put_length(ext, ll)
        out.append(('literal 長度的延伸', bytes(ext)))
    if ll:
        out.append(('literal', page[pos:pos + ll]))
    if ml:
        out.append(('offset', off.to_bytes(2, 'little')))
        ext = bytearray()
        if ml - C.MINMATCH >= 15:
            C.put_length(ext, ml - C.MINMATCH)
            out.append(('match 長度的延伸', bytes(ext)))
    return out


def md_seqs(x, head=3, tail=2):
    page, seqs = x['page'], x['e'].seqs
    pos, at, rows = 0, 0, []
    for i, (ll, ml, off) in enumerate(seqs):
        parts = _parts(page, pos, ll, ml, off)
        size = sum(len(b) for _, b in parts)
        if i < head or i >= len(seqs) - tail:
            shown = '，'.join(f'{name} `{_hex(b)}`' if len(b) <= 8 or name != 'literal' else f'{len(b)} 個 literal'
                             for name, b in parts)
            rows.append((i + 1, at, pos, ll, ml or '沒有', off or '', shown))
        elif i == head:
            rows.append(('…', '', '', '', '', '', f'中間 {len(seqs) - head - tail} 個 sequence'))
        pos += ll + ml
        at += size
    assert at == len(x['e'].stream) and pos == J.PAGE
    return table(('sequence', '在 stream 的位置', '在 page 的位置', 'literal 數', 'match 長度', 'offset', '寫進 stream 的 byte，依序'), rows)


def md_dtrace(x, head=3, tail=2):
    """The decoder on the same stream: every variable at the end of a sequence."""
    s, seqs = x['e'].stream, x['e'].seqs
    ipos = opos = 0
    rows = []
    for i, (ll, ml, off) in enumerate(seqs):
        size = sum(len(b) for _, b in _parts(x['page'], opos, ll, ml, off))
        if i < head or i >= len(seqs) - tail:
            lit = f'`page[{opos}..{opos + ll - 1}]`' if ll else '沒有'
            src = f'`page[{opos + ll - off}]` 起，' + ('history register' if off < C.HISTORY else 'page buffer') if ml else ''
            rows.append((i + 1, ipos, f'0x{s[ipos]:02X}', ll, lit, off or '', ml or '沒有', src, ipos + size, opos + ll + ml))
        elif i == head:
            rows.append(('…', '', '', '', '', '', '', '', '', ''))
        ipos += size
        opos += ll + ml
    return table(('sequence', '開始時的 `ipos`', '`token`', '`ll`', 'literal 寫到', '`offset`', '`ml`', 'match 從哪裡讀',
                  '結束時的 `ipos`', '結束時的 `opos`'), rows)


def phases(x):
    e = x['e']
    enc, dec = C.encode_cycles(e), C.decode_cycles(e.seqs)
    supply = S.chunks(len(e.stream)) * (S.RD_LAT + S.BURST)
    comp, behind, after = S.job_cycles(e)
    c = [('FETCH 與 CHECK', '讀 descriptor 6 個 beat，檢查', S.FETCH),
         ('LOAD', 'frame 的 8 個 burst 進 page buffer', S.LOAD),
         ('ENCODE', f'{e.searched} 個位置查過 hash table，{e.matches} 個 match；前面的 chunk 在這段時間裡寫出去', enc),
         ('最後一個 chunk', 'encoder 結束時還沒送出的那個 burst', S.LAST_WRITE),
         ('POST', '寫 completion 2 個 beat，推進 `CPL_TAIL`', S.POST)]
    d = [('FETCH 與 CHECK', '讀 descriptor 6 個 beat，檢查', S.FETCH),
         ('DECODE', f'{len(e.seqs)} 個 sequence；chunk 的讀取與 frame 前 7 個 burst 的寫入都在這段時間裡', max(dec + S.RD_LAT, supply)),
         ('最後一個 burst', 'decoder 結束時還沒送出的 frame 最後 512 B', S.LAST_WRITE),
         ('POST', '寫 completion 2 個 beat，推進 `CPL_TAIL`', S.POST)]
    assert sum(r[2] for r in c) == comp and sum(r[2] for r in d) == behind
    return c, d, after


def md_phases(rows):
    return table(('階段', '做什麼', 'cycle'), list(rows) + [('**合計**', '', f'**{sum(r[2] for r in rows)}**')])


# ---- the study
def md_study(rows):
    return table(('encoder', '平均 stream 長度 B', '佔 4096 B 的比例', '平均用幾個 chunk', '超過 7 個 chunk 的 page'),
                 [(r['name'], f"{r['mean_len']:.1f}", f"{100 * r['mean_len'] / C.PAGE:.1f}%", f"{r['mean_chunks']:.2f}",
                   f"{r['over_rw_limit_pct']:.1f}%") for r in rows])


def _d(x):
    return f"{x['mean']:.0f} / {x['p50']} / {x['p99']} / {x['max']}"


def md_cycles(sets):
    rows = [(S.SET_ZH[k], _d(v['cycles']['sequences']), _d(v['cycles']['encode_core']), _d(v['cycles']['decode_core']),
             _d(v['cycles']['compress_job']), _d(v['cycles']['decompress_job']), _d(v['cycles']['decompress_job_store_after']))
            for k, v in sets.items()]
    return table(('page 的來源', 'sequence 數', 'encoder core', 'decoder core', 'COMPRESS job', 'DECOMPRESS job',
                  'DECOMPRESS job，CRC 驗完才寫 frame'), rows)


def md_time(sets):
    rows = []
    for k, v in sets.items():
        for job, key in (('COMPRESS', 'compress_job'), ('DECOMPRESS', 'decompress_job')):
            c = v['cycles'][key]
            rows.append([S.SET_ZH[k], job] + [f"{c['mean'] / f:.1f} / {c['p99'] / f:.1f}" for f in MHZ])
    return table(['page 的來源', 'job'] + [f'{f} MHz' for f in MHZ], rows)


def md_sources(nums):
    return table(('檔案', '大小 B', 'SHA-256 的前 16 位'), [(f"`{s['file']}`", s['bytes'], f"`{s['sha256']}`") for s in nums['sources']])


# ---- the vectors
ENC_GROUPS = (
    ('example', '第 2 節的例子'),
    ('zeros', '整個 page 是 0：一個 match 一路到結尾前 5 個 byte，match 長度要 16 個延伸 byte'),
    ('random', '什麼都對不上：一個 sequence，4096 個 literal，stream 比 page 長'),
    ('words', '像文字：幾百個短的 sequence'),
    ('two_symbols', '幾乎每個位置都 match，offset 很短，hash table 的同一格馬上又被用到：考 forwarding'),
    ('four_symbols', '同上，literal 多一些'),
    ('runs', '同一個 byte 連續 8 個或 16 個上下：各種短長度的重疊 match'),
    ('lit_', '第一個 match 前面的 literal 數是這個值，0 那一個是兩個 match 緊接著、中間沒有 literal：長度欄位 15 的邊界與延伸 byte 255 的邊界'),
    ('match_', 'match 長度是這個值：同樣的邊界'),
    ('offset_', 'offset 是這個值'),
    ('late_', '同樣的 8 個 byte 晚一個位置出現：那裡不能開始 match'),
    ('len_', 'stream 的長度恰好是這個值：chunk 的邊界、limit 3584 的邊界、4096 的邊界'),
)
BAD_ZH = {
    'bad_cut_in_literals': 'stream 在一串 literal 中間結束',
    'bad_cut_in_offset': 'stream 在 offset 的第一個 byte 之後結束',
    'bad_cut_in_length': 'stream 在 match 長度的延伸 byte 中間結束',
    'bad_cut_after_match': 'stream 在一個 match 之後結束，那裡應該要有 token',
    'bad_cut_after_literals': 'stream 在前面某個 sequence 的 literal 之後結束：結束的位置合法，輸出遠不到 4096 B',
    'bad_half_page': '一個正確的 block，但它是 2048 B 的 page',
    'bad_offset_zero': 'offset 是 0',
    'bad_offset_far': '輸出才 8 個 byte，offset 是 9',
    'bad_literals_over': '最後一個 sequence 有 6 個 literal，只放得下 5 個',
    'bad_match_over': '輸出 1 個 byte 之後來一個長度 4096 的 match',
    'bad_length_runaway': '4096 個 0xFF：literal 長度沒有盡頭',
    'bad_extra_byte': '完整的 block 後面多一個 byte',
    'bad_extra_sequence': '完整的 block 後面多一個 match',
}


def md_encode_vectors():
    v = V.encode_vectors()
    rows = []
    for key, zh in ENC_GROUPS:
        names = [n for n, _, _ in v if (n.startswith(key) if key.endswith('_') else n == key)]
        vals = '、'.join(n[len(key):] for n in names) if key.endswith('_') else ''
        rows.append((f'`{key}*`' if key.endswith('_') else f'`{key}`', len(names), zh, vals))
    assert sum(r[1] for r in rows) == len(v)
    return table(('名稱', '個數', '考什麼', '值'), rows)


def md_bad_streams():
    return table(('名稱', 'stream 長度 B', '哪裡壞', '`decode` 哪一項檢查發現'),
                 [(f'`{n}`', len(s), BAD_ZH[n], f'`{why}`') for n, _, s, why in V.bad_streams()])


def md_job_vectors():
    kinds = (('c_', 'COMPRESS'), ('d_', 'DECOMPRESS'), ('bad_desc_', 'descriptor 不合法'), ('bus_', 'bus error，暫定'))
    names = [n for n in SPEC.enum_name['status'].values()]
    count = Counter((next(k for k, _ in kinds if j['name'].startswith(k)), j['status']) for j in V.job_vectors())
    rows = [[zh, f'`{k}*`'] + [count.get((k, s), '') for s in names] for k, zh in kinds]
    rows.append(['**合計**', ''] + [sum(count.get((k, s), 0) for k, _ in kinds) for s in names])
    return table(['類別', '名稱'] + [f'`{s}`' for s in names], rows)


def md_bad_desc():
    by = {}
    for j in V.job_vectors():
        if j['name'].startswith('bad_desc_'):
            by.setdefault(j['completion_fields']['aux'], []).append(j['name'][len('bad_desc_'):])
    return table(('`aux`', '個數', '名稱，前面都加 `bad_desc_`'),
                 [(f"`{SPEC.enum_name['bad_desc'][a]}`", len(n), '、'.join(f'`{x}`' for x in n)) for a, n in sorted(by.items())])


HW_RULES = {
    'HW-MEM-1': ('`lz4_ctrl`、`lz4_rdma`、`lz4_wdma`', 'bus monitor：每個 burst 的位址與方向都在 `hwref.job.allowed` 列出的範圍內，或是 ring 的那一格'),
    'HW-MEM-2': ('`lz4_ctrl`', 'bus monitor：每個 job 恰好一次 6 個 beat 的讀，位址是 `JOB_HEAD` 那一格；`JOB_HEAD` 在最後一個 beat 之後才變'),
    'HW-CPL-1': ('`lz4_ctrl`', 'scoreboard：completion 的順序與 tag 對得上送進去的 job'),
    'HW-CPL-2': ('`lz4_ctrl`、`lz4_wdma`', 'monitor：`CPL_TAIL` 改變的那個 cycle，這個 job 所有寫入 burst 的 response 都已經回來，completion 的也是'),
    'HW-CPL-3': ('`lz4_ctrl`', '測試：bench 故意不推 `CPL_HEAD`。monitor 確認 ring 滿的時候沒有寫入 completion ring 的 burst'),
    'HW-IRQ-1': ('`lz4_csr`', 'assertion：每個 cycle 拿 `irq` 與 register 的值比'),
    'HW-DATA-1': ('`lz4_enc`、`lz4_pack`、`lz4_crc32`', 'scoreboard：chunk 與 completion 逐 byte 比對 `hwref.job`'),
    'HW-DATA-2': ('`lz4_dec`、`lz4_crc32`', 'scoreboard：frame 與 completion 逐 byte 比對 `hwref.job`；壞的 stream 一律回 `BAD_STREAM`'),
    'HW-STATE-1': ('全部，特別是 hash table 的 valid、兩個 FIFO、CRC', '同一個 job 接在不同的 job 後面、接在 reset 後面各做一次，結果相同'),
    'HW-RST-1': ('`lz4_ctrl`、`lz4_csr`、兩個 DMA', '在 job FSM 的每一個 state 注入 soft reset'),
}


def md_hw_rules():
    assert set(HW_RULES) == {r for r in SPEC.rules if r.startswith('HW-')}
    return table(('編號', '規則，原文來自介面規格', '主要由哪個 block 負責', 'RTL bench 怎麼驗'),
                 [(f'`{rid}`', SPEC.rules[rid]['text'], *HW_RULES[rid]) for rid in HW_RULES])


def md_memories():
    hb = C.HASH_BITS
    rows = [('page buffer，even bank', '256 × 64 bit', 16384, '兩個 port，各自可讀可寫，寫入有 byte enable'),
            ('page buffer，odd bank', '256 × 64 bit', 16384, '同上'),
            ('hash table 的位置', f'{1 << hb} × 12 bit', (1 << hb) * 12, '一個讀 port，一個寫 port'),
            ('hash table 的 valid', f'{1 << hb} 個 flop', 1 << hb, '一個 cycle 全部清成 0'),
            ('IN FIFO', '128 × 64 bit', 8192, '一個讀 port，一個寫 port'),
            ('OUT FIFO', '128 × 64 bit', 8192, '同上'),
            ('decoder 的 history', f'{C.HISTORY} × 8 bit', C.HISTORY * 8, 'flop')]
    rows.append(('**合計**', '', sum(r[2] for r in rows), ''))
    return table(('記憶體', '大小', 'bit 數', '需要的 port'), rows)


# ---- the document
def numbers(n=300, seed=1):
    return S.run(n, seed)


def render(nums):
    x = example()
    e = x['e']
    c_rows, d_rows, after = phases(x)
    sets = nums['sets']
    base = {k: v['rows'][0] for k, v in sets.items()}
    hc = {k: v['rows'][-1] for k, v in sets.items()}
    extra = {'src:' + n: source(f) for n, f in SHOWN.items()}
    extra.update({
        'ex:bursts_c': md_bursts(x, 'c'), 'ex:bursts_d': md_bursts(x, 'd'), 'ex:trace': md_trace(x), 'ex:seqs': md_seqs(x),
        'ex:dtrace': md_dtrace(x), 'hw_rules': md_hw_rules(),
        'ex:phases_c': md_phases(c_rows), 'ex:phases_d': md_phases(d_rows),
        'ex:cycles_c': sum(r[2] for r in c_rows), 'ex:cycles_d': sum(r[2] for r in d_rows), 'ex:cycles_d_after': after,
        'ex:len': len(e.stream), 'ex:seqs_n': len(e.seqs), 'ex:matches': e.matches, 'ex:searched': e.searched,
        'ex:crc': f'0x{C.crc32(e.stream):08X}', 'ex:chunks': S.chunks(len(e.stream)),
        'ex:pad': S.chunks(len(e.stream)) * J.CHUNK - len(e.stream),
        'ex:stream_head': _hex(e.stream[:32]), 'ex:stream_tail': _hex(e.stream[-14:]),
        'ex:desc_c': _desc_table(x['d']), 'ex:cpl_c': _cpl_table(x['res'].completion),
        'ex:desc_d': _desc_table(x['d2']), 'ex:cpl_d': _cpl_table(x['res2'].completion),
        'ex:core_c': C.encode_cycles(e), 'ex:core_d': C.decode_cycles(e.seqs),
        'ex:short_offsets': sum(1 for _, m, o in e.seqs if m and o < C.HISTORY),
        'ex:max_match': max(m for _, m, _ in e.seqs), 'ex:max_lit': max(l for l, _, _ in e.seqs),
        'slot': SLOT, 'job_slot_pa': _pa(V.RING['JOB_BASE'] + SLOT * 64), 'cpl_slot_pa': _pa(V.RING['CPL_BASE'] + SLOT * 16),
        'job_base': _pa(V.RING['JOB_BASE']), 'cpl_base': _pa(V.RING['CPL_BASE']),
        'pool_base': _pa(V.REGS.pool_base), 'frame_base': _pa(V.REGS.frame_base),
        'hash_bits': C.HASH_BITS, 'hash_entries': 1 << C.HASH_BITS, 'history': C.HISTORY,
        'memories': md_memories(),
        'pages_per_set': nums['pages_per_set'], 'sources': md_sources(nums),
        'cycles': md_cycles(sets), 'time': md_time(sets), 'mhz': '、'.join(str(f) for f in MHZ),
        'vec:encode': md_encode_vectors(), 'vec:bad': md_bad_streams(), 'vec:jobs': md_job_vectors(), 'vec:bad_desc': md_bad_desc(),
        'vec:n_encode': len(V.encode_vectors()), 'vec:n_decode': len(V.decode_vectors()), 'vec:n_bad': len(V.bad_streams()),
        'vec:n_jobs': len(V.job_vectors()),
        'bin_pct': f"{100 * base['binaries']['mean_len'] / C.PAGE:.0f}", 'bin_hc_pct': f"{100 * hc['binaries']['mean_len'] / C.PAGE:.0f}",
        'bin_over': f"{base['binaries']['over_rw_limit_pct']:.0f}",
        'heap_pct': f"{100 * base['heap']['mean_len'] / C.PAGE:.0f}", 'heap_chunks': f"{base['heap']['mean_chunks']:.2f}",
        'rd_lat': S.RD_LAT, 'wr_resp': S.WR_RESP,
    })
    extra.update({'study:' + k: md_study(v['rows']) for k, v in sets.items()})
    for k in sets:
        for key in ('compress_job', 'decompress_job', 'decompress_job_store_after', 'encode_core', 'decode_core'):
            for q in ('mean', 'p99', 'max'):
                extra[f'cyc:{k}.{key}.{q}'] = f"{sets[k]['cycles'][key][q]:.0f}"
    with open(TEMPLATE, encoding='utf-8') as f:
        return fill(f.read(), extra)


def _desc_table(d):
    return fields('job_desc', d)


def _cpl_table(c):
    return fields('completion', c)


def write(reuse=False, n=300, seed=1):
    path = os.path.join(SPEC_DIR, NUMBERS)
    if reuse and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            nums = json.load(f)
    else:
        nums = numbers(n, seed)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(nums, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write('\n')
    with open(os.path.join(SPEC_DIR, DOC), 'w', encoding='utf-8') as f:
        f.write(render(nums))
    return os.path.join(SPEC_DIR, DOC), path

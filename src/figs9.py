# Generates the to-scale figures of section 9 (512 MiB design) and inserts them after their markers in page.html.
import re

X0 = 40
DASH = 'stroke-dasharray:4 3'
def r(x, y, w, h, cls, style=''):
    st = f' style="{style}"' if style else ''
    return f'<rect class="{cls}" x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}"{st}/>'
def t(x, y, s, cls='', anchor='middle'):
    c = f' class="{cls}"' if cls else ''
    a = '' if anchor == 'start' else (' text-anchor="end"' if anchor == 'end' else ' text-anchor="middle"')
    return f'<text{c} x="{x:.1f}" y="{y}"{a}>{s}</text>'
def fits(lab, w):
    return len(lab) * 6.8 + 6 <= w
def wrap(view_h, aria, body, caption, defs=''):
    return (f'<figure>\n  <div class="fig"><svg viewBox="0 0 900 {int(view_h)}" role="img" aria-label="{aria}">\n    {defs}'
            + '\n    '.join(body) + f'\n  </svg></div>\n  <figcaption>{caption}</figcaption>\n</figure>\n')

# Workload numbers (MiB). Keep in sync with plan512.py.
PIN, HRT, COT, POOL, FC = 56, 36, 5, 275, 140
RO, DATA, HEAP = 248, 26, 306
RW = DATA + HEAP
HOT_RO, HOT_RW = 30, 80
RO_OBJ, RW_OBJ = 136.4, 113.4
COT_RO, COT_RW = 1.94, 1.97

# ---------- A: image before and after the build ----------
def fig_image():
    s1 = 2.0; o = []
    o.append('<defs><marker id="m9i" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0L8 4L0 8z" fill="currentColor"/></marker></defs>')
    o.append(t(X0, 22, f'Image as linked, uncompressed: {34 + RO + DATA} MiB', 'h', 'start'))
    y = 32; h = 46; x = X0
    for name, size, cls, sub in [('Pinned', 34, 'r-warn', '34'), (f'RO {RO} MiB', RO, 'r-mat', '.text and .rodata of normal code'), ('.data', DATA, 'r-lit', '26')]:
        w = size * s1
        o.append(r(x, y, w, h, cls)); o.append(t(x + w / 2, y + 19, name)); o.append(t(x + w / 2, y + 36, sub, 's')); x += w
    o.append(f'<line class="ln" x1="{X0 + 34*s1 + RO*s1/2:.1f}" y1="80" x2="{X0 + 34*s1 + RO_OBJ*s1/2:.1f}" y2="128" marker-end="url(#m9i)"/>')
    o.append(t(X0 + 34 * s1 + RO * s1 / 2 + 10, 108, 'build tool: LZ4 on each 4 KB RO page', 's', 'start'))
    o.append(t(X0, 152, 'Image on flash: about 198 MiB', 'h', 'start'))
    y = 162; x = X0
    for name, size, cls, sub in [('Pinned', 34, 'r-warn', '34'), (f'RO chunk image {RO_OBJ}', RO_OBJ, 'r-mat', 'LZ4, about 279,000 chunks'), ('', COT_RO, 'r-acc', ''), ('.data', DATA, 'r-lit', '26')]:
        w = size * s1
        o.append(r(x, y, w, h, cls))
        if name.startswith('RO'): o.append(r(x, y, w, h, 'zc'))
        if name: o.append(t(x + w / 2, y + 19, name)); o.append(t(x + w / 2, y + 36, sub, 's'))
        else:
            o.append(f'<line class="ln2" x1="{x + w/2:.1f}" y1="{y + h}" x2="{x + w/2:.1f}" y2="{y + h + 14}"/>'); o.append(t(x + w / 2, y + h + 26, f'RO COT entries, {COT_RO} MiB', 's'))
        x += w
    o.append(t(X0, 256, 'Every block is to scale: 1 px = 0.5 MiB.', 's', 'start'))
    o.append(t(X0, 274, '.bss, heap and stack are not in the image: they are only a VA range, zero-filled on first use.', 's', 'start'))
    return wrap(284, f'未壓縮的 image 有 pinned 34 MiB、RO {RO} MiB、.data {DATA} MiB。建置工具把 RO 逐頁壓縮後，flash 上的 image 是 pinned 34 MiB、RO chunk 映像 {RO_OBJ} MiB、RO 的 COT entry {COT_RO} MiB、.data {DATA} MiB，約 198 MiB', o,
                f'建置前後的 image，照比例畫。只有 RO 被壓縮：{RO} MiB 變成 {RO_OBJ} MiB 的 chunk 映像，另外附上這些 page 的 COT entry。.bss、heap、stack 只是一段 VA，執行時用到才配置，image 裡沒有它們。')

# ---------- E: hot vs cold concept ----------
def fig_hotcold():
    o = []
    o.append('<defs><marker id="m9h" markerUnits="userSpaceOnUse" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="9" markerHeight="9" orient="auto"><path d="M0 0L8 4L0 8z" fill="currentColor"/></marker></defs>')
    o.append(r(20, 30, 230, 64, 'bx')); o.append(t(135, 56, 'Hot pages', 'h')); o.append(t(135, 76, 'used recently', 's'))
    o.append(r(20, 170, 230, 64, 'bx')); o.append(t(135, 196, 'Cold pages', 'h')); o.append(t(135, 216, 'not used for a while', 's'))
    o.append(r(470, 30, 400, 64, 'r-lit')); o.append(t(670, 56, 'Frame cache: uncompressed', 'h')); o.append(t(670, 76, 'the CPU reads and writes them directly', 's'))
    o.append(r(470, 170, 400, 64, 'r-mat')); o.append(r(470, 170, 400, 64, 'zc')); o.append(t(670, 196, 'Chunk pool: compressed', 'h')); o.append(t(670, 216, 'smaller; the CPU cannot use them as they are', 's'))
    o.append('<line class="ln" x1="250" y1="62" x2="468" y2="62" marker-end="url(#m9h)"/>'); o.append(t(359, 54, 'kept here', 's'))
    o.append('<line class="ln" x1="250" y1="202" x2="468" y2="202" marker-end="url(#m9h)"/>'); o.append(t(359, 194, 'only here', 's'))
    o.append('<line class="ln" x1="620" y1="94" x2="620" y2="168" marker-end="url(#m9h)"/>'); o.append(t(612, 124, 'becomes cold:', 's', 'end')); o.append(t(612, 140, 'RW compressed, RO frame dropped', 's', 'end'))
    o.append('<line class="ln" x1="720" y1="168" x2="720" y2="96" marker-end="url(#m9h)"/>'); o.append(t(728, 124, 'used again:', 's', 'start')); o.append(t(728, 140, 'page fault, decompress', 's', 'start'))
    o.append(t(20, 262, 'Only cold data saves space. Pinned and HRT data are never moved, hot or cold.', 's', 'start'))
    return wrap(276, '熱的 page 以未壓縮形式留在 frame cache，CPU 直接讀寫；冷的 page 只以壓縮形式留在 pool。變冷時 RW 被壓縮、RO 的 frame 被丟掉；再被用到時 page fault 並解壓縮', o,
                '熱的 page 留在 frame cache，冷的 page 只以壓縮形式留在 pool。只有冷資料能省空間，熱資料一定要以未壓縮的大小佔著 frame。')

# ---------- B and C: DRAM with and without LZ4 ----------
S2 = 1 / 0.8
REG = [('Pinned', PIN), ('HRT', HRT), ('COT', COT), ('Chunk pool', POOL), ('Frame cache', FC)]
def dram(title, fills, used_note, plain, plain_note, aria, caption):
    o = []
    o.append(t(X0, 20, title, 'h', 'start'))
    o.append(t(X0, 46, 'With LZ4 (this design): 512 MiB DRAM', 'h', 'start'))
    by = 86; bh = 50; x = X0; pos = {}
    for name, size in REG:
        pos[name] = (x, size * S2); x += size * S2
    for name, segs in fills.items():
        x, w = pos[name]; cx = x
        for cls, mib, lab in segs:
            sw = mib * S2
            if cls == 'free': o.append(r(cx, by, sw, bh, 'bx', DASH))
            else:
                o.append(r(cx, by, sw, bh, cls))
                if name == 'Chunk pool': o.append(r(cx, by, sw, bh, 'zc'))
            if lab and fits(lab, sw): o.append(t(cx + sw / 2, by + bh / 2 + 4, lab, 's'))
            cx += sw
    for name, size in REG:
        x, w = pos[name]
        o.append(f'<rect x="{x:.1f}" y="{by}" width="{w:.1f}" height="{bh}" fill="none" stroke="currentColor" stroke-width="1.6"/>')
        if name == 'COT':
            ly = by - 26
            o.append(f'<line class="ln2" x1="{x + w/2:.1f}" y1="{ly + 4}" x2="{x + w/2:.1f}" y2="{by}"/>'); o.append(t(x + w / 2, ly, f'COT {size}', 's'))
        elif name in ('Chunk pool', 'Frame cache'):
            o.append(t(x + w / 2, by - 8, f'{name} {size} MiB', 's'))
    o.append(t(X0, by + bh + 18, used_note, 's', 'start'))
    py = by + bh + 58; ph = 40; dw = 512 * S2; cx = X0
    o.append(t(X0, py - 10, 'Without LZ4: everything stays uncompressed', 'h', 'start'))
    for cls, mib, lab in plain:
        sw = mib * S2
        if cls == 'free': o.append(r(cx, py, sw, ph, 'bx', DASH))
        else: o.append(r(cx, py, sw, ph, cls))
        crosses = cx < X0 + dw < cx + sw
        if lab and crosses: o.append(t(cx + sw / 2, py - 6, lab, 's'))
        elif lab and fits(lab, sw): o.append(t(cx + sw / 2, py + ph / 2 + 4, lab, 's'))
        cx += sw
    o.append(f'<rect x="{X0}" y="{py}" width="{dw:.1f}" height="{ph}" fill="none" stroke="currentColor" stroke-width="1.6"/>')
    o.append(f'<line class="ln" x1="{X0 + dw:.1f}" y1="{py}" x2="{X0 + dw:.1f}" y2="{py + ph + 8}"/>')
    o.append(t(X0, py + ph + 18, plain_note, 's', 'start'))
    lx = X0; ly = py + ph + 46
    for cls, lab, st in [('r-warn', 'pinned / HRT', ''), ('r-mat', 'RO', ''), ('r-lit', 'RW', ''), ('r-acc', 'COT entries in use', ''), ('bx', 'free', DASH), ('zc', 'compressed (LZ4)', '')]:
        o.append(r(lx, ly - 11, 14, 14, cls, st))
        if cls == 'zc': o.append(r(lx, ly - 11, 14, 14, 'bx', 'fill:none'))
        o.append(t(lx + 20, ly, lab, 's', 'start')); lx += 40 + len(lab) * 7
    o.append(t(X0, ly + 22, 'Hatched = compressed. Solid = uncompressed. Every block, in both bars, is to scale: 1 px = 0.8 MiB.', 's', 'start'))
    return wrap(ly + 34, aria, o, caption)

def fig_boot():
    return dram('DRAM right after boot', {
        'Pinned': [('r-warn', PIN, 'Pinned')], 'HRT': [('r-warn', HRT, 'HRT')],
        'COT': [('r-acc', COT_RO, ''), ('free', COT - COT_RO, '')],
        'Chunk pool': [('r-mat', RO_OBJ, f'RO {RO_OBJ} LZ4'), ('free', POOL - RO_OBJ, f'free {POOL - RO_OBJ:.1f}')],
        'Frame cache': [('r-lit', DATA, ''), ('free', FC - DATA, f'free {FC - DATA}')]},
        'In use: 259.4 of 512 MiB. Pinned 56, HRT 36, COT 5. The frame cache holds only .data (26 MiB).',
        [('r-warn', PIN, 'Pinned'), ('r-warn', HRT, 'HRT'), ('r-mat', RO, f'RO {RO}'), ('r-lit', DATA, ''), ('free', 512 - 366, 'free 146')],
        'In use: 366 of 512 MiB. RO is loaded uncompressed and must stay: no storage to read it back from.',
        '剛開機時的 DRAM。上面是本文的設計：pinned 56 MiB 與 HRT 36 MiB；COT 只有 RO 的 entry；pool 裡只有壓縮的 RO 物件 136.4 MiB；frame cache 只有 .data 26 MiB；共用 259.4 MiB。下面是不用 LZ4：RO 以未壓縮的 248 MiB 放在 DRAM，共 366 MiB',
        '剛開機時用的 DRAM 最少。Frame cache 裡只有 .data 26 MiB，其餘 114 MiB 空著，等 RO 被讀到、heap 長大時使用。Pool 裡只有 RO 物件，138.6 MiB 空著，留給執行時被壓縮的 RW page。下方不用 LZ4 時，RO 必須以未壓縮的 248 MiB 全部放在 DRAM，所以多用了約 107 MiB；不過這時兩者都放得進 512 MiB。')

def fig_peak():
    return dram('DRAM after running for a while: RW at its peak', {
        'Pinned': [('r-warn', PIN, 'Pinned')], 'HRT': [('r-warn', HRT, 'HRT')],
        'COT': [('r-acc', COT_RO + COT_RW, ''), ('free', COT - COT_RO - COT_RW, '')],
        'Chunk pool': [('r-mat', RO_OBJ, f'RO {RO_OBJ} LZ4'), ('r-lit', RW_OBJ, f'cold RW {RW_OBJ}'), ('free', POOL - RO_OBJ - RW_OBJ, '')],
        'Frame cache': [('r-mat', HOT_RO, 'hot RO'), ('r-lit', HOT_RW, f'hot RW {HOT_RW}'), ('free', FC - HOT_RO - HOT_RW, f'{FC - HOT_RO - HOT_RW}')]},
        'In use: 456.8 of 512 MiB. Frame cache: hot RO 30 + hot RW 80 + free 30. Pool: free 25.2. Margin 55.2 MiB.',
        [('r-warn', PIN, 'Pinned'), ('r-warn', HRT, 'HRT'), ('r-mat', HOT_RO, 'hot RO'), ('r-mat', RO - HOT_RO, f'cold RO {RO - HOT_RO}'), ('r-lit', HOT_RW, f'hot RW {HOT_RW}'), ('r-lit', RW - HOT_RW, f'cold RW {RW - HOT_RW}')],
        'Needs 672 MiB: the bar runs 160 MiB past the 512 MiB line, so this needs a 1 GiB part.',
        'RW 用到最多時的 DRAM。上面是本文的設計：frame cache 裡熱的 RO 30 MiB、熱的 RW 80 MiB，空 30 MiB；pool 裡 RO 物件 136.4 MiB、冷的 RW 壓縮後 113.4 MiB，空 25.2 MiB；共用 456.8 MiB。下面是不用 LZ4：需要 672 MiB，超出 512 MiB 邊界 160 MiB',
        'RW 用到最多時，本文的設計用了 456.8 MiB，還有 55.2 MiB 的 margin。熱資料在上下兩條一樣大：熱的 RO 30 MiB、熱的 RW 80 MiB。差別全在冷資料：冷的 RO 218 MiB 和冷的 RW 252 MiB，不壓縮時各以原本的大小佔著 DRAM；壓縮後，全部 RO 只要 136.4 MiB，冷的 RW 只要 113.4 MiB。')

# ---------- D: where the saving comes from ----------
def fig_saving():
    s3 = 1.5; L = 190; o = []
    o.append(t(20, 22, 'Where the 215 MiB comes from, at the RW peak (each item: without LZ4 above, with LZ4 below)', 'h', 'start'))
    st = {'y': 50}; bh = 22; gap = 30
    def bar(x, y, mib, cls, lab, hatch=False, dash=False):
        w = mib * s3
        o.append(r(x, y, w, bh, cls, DASH if dash else ''))
        if hatch: o.append(r(x, y, w, bh, 'zc'))
        if lab and w >= 34: o.append(t(x + w / 2, y + 15, lab, 's'))
        return x + w
    def group(name, top, bottom, saved, note=None, squeeze=None):
        y = st['y']
        o.append(t(20, y + 15, name, 'h', 'start'))
        o.append(t(L - 8, y + 15, 'without', 's', 'end')); o.append(t(L - 8, y + gap + 15, 'with LZ4', 's', 'end'))
        x = L
        for seg in top: x = bar(x, y, *seg)
        o.append(t(x + 6, y + 15, f'{sum(sg[0] for sg in top):g}' if top else '0', 's', 'start'))
        x = L
        for seg in bottom: x = bar(x, y + gap, *seg)
        tot = sum(sg[0] for sg in bottom)
        if saved:
            x2 = bar(x, y + gap, saved, 'bx', '', dash=True)
            o.append(t(x2 + 6, y + gap + 15, f'{tot:g}, saves {saved:g}', 's', 'start'))
        else:
            o.append(t(x + 6, y + gap + 15, f'{tot:g}' + (', extra' if not top else ''), 's', 'start'))
        if squeeze:
            a0, a1, b0, b1 = squeeze
            o.append(f'<path class="ln2" d="M{L + a0 * s3:.1f} {y + bh} L{L + b0 * s3:.1f} {y + gap} M{L + a1 * s3:.1f} {y + bh} L{L + b1 * s3:.1f} {y + gap}"/>')
        if note: o.append(t(L, y + gap + bh + 14, note, 's', 'start'))
        st['y'] = y + gap + bh + (36 if note else 22)
    group('Pinned+HRT', [(PIN + HRT, 'r-warn', 'not compressible 92')], [(PIN + HRT, 'r-warn', 'same 92')], 0)
    group('RO', [(HOT_RO, 'r-mat', 'hot 30'), (RO - HOT_RO, 'r-mat', f'cold {RO - HOT_RO}')],
          [(RO_OBJ, 'r-mat', f'all RO, LZ4: {RO_OBJ}', True), (HOT_RO, 'r-mat', 'copy 30')], 81.6,
          f'All {RO} MiB shrink to {RO_OBJ} MiB; the 30 MiB in use also need an uncompressed copy.', (0, RO, 0, RO_OBJ))
    group('RW', [(HOT_RW, 'r-lit', 'hot 80'), (RW - HOT_RW, 'r-lit', f'cold {RW - HOT_RW}')],
          [(HOT_RW, 'r-lit', 'hot 80'), (RW_OBJ, 'r-lit', f'{RW_OBJ} LZ4', True)], 138.6,
          f'Only the cold {RW - HOT_RW} MiB is compressed, to {RW_OBJ} MiB; the hot 80 MiB stays uncompressed.', (HOT_RW, RW, HOT_RW, HOT_RW + RW_OBJ))
    group('COT', [], [(COT, 'r-acc', '')], 0)
    y = st['y']
    o.append(t(20, y + 6, 'Total: 672 MiB without LZ4, 456.8 MiB with LZ4: 215.2 MiB saved, about 32%. Scale: 1 px = 0.67 MiB.', 'h', 'start'))
    return wrap(y + 20, 'RW 用到最多時逐項對照：pinned 與 HRT 92 MiB 不變；RO 248 MiB 全部壓成 136.4 MiB，用到的 30 MiB 另有一份未壓縮的，共 166.4 MiB，省 81.6 MiB；RW 熱的 80 MiB 不壓縮，冷的 252 MiB 壓成 113.4 MiB，省 138.6 MiB；COT 多用 5 MiB。合計 672 MiB 變成 456.8 MiB', o,
                '逐項對照，同一比例、左端對齊。斜線是壓縮後的資料，虛線梯形連到它壓縮前的那一段，虛線空框是省下的空間。這次冷資料佔大部分：RO 有 88% 是冷的，RW 有 76% 是冷的，所以整體能省約 32%。')

ARCH = None  # the architecture figure is written directly in page.html

FIGS = {'a': fig_image, 'e': fig_hotcold, 'b': fig_boot, 'd': fig_saving, 'c': fig_peak}
p = 'page.html'; s = open(p, encoding='utf-8').read()
for k, fn in FIGS.items():
    marker = f'<!--fig9{k}-->'
    assert s.count(marker) == 1, marker
    s = re.sub(re.escape(marker) + r'\n<figure>.*?</figure>\n', lambda m: marker, s, flags=re.S)
    s = s.replace(marker, marker + '\n' + fn())
open(p, 'w', encoding='utf-8').write(s)
print('figures inserted')

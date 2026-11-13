#!/usr/bin/env python3
"""Draw the processor and the compression layer: what is per core, what is shared.

Writes processor-overview.svg beside this file. Numbers come from
spec/kernel-step-detail-v0.md section 2 (memory map and table sizes).
Platform assumptions P1 to P4 are in the project CLAUDE.md.
"""
from pathlib import Path
from xml.sax.saxutils import escape

W, H = 1800, 1330
FONT = "Helvetica Neue, Helvetica, Arial, sans-serif"

C = dict(
    ink='#1A202C', mute='#4A5568', line='#4A5568',
    user_f='#FFF3D1', user_s='#B7791F',
    kern_f='#EFE7FF', kern_s='#6B46C1',
    cpu_f='#E3F0FC', cpu_s='#2B6CB0', tlb_f='#BFDDF7', l2_f='#A9D1F5',
    lz4_f='#DDF3E2', lz4_s='#2F855A',
    ram_f='#F4F5F7', ram_s='#4A5568', cell_f='#FFFFFF',
    lock='#C53030', exc='#C05621', proc_f='#FAFBFC',
)
out = []


def rect(x, y, w, h, fill, stroke, rx=6, sw=1.5, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def text(x, y, s, size=13, weight='normal', anchor='start', fill=None, style=None, rotate=None):
    fill = fill or C['ink']
    st = f' font-style="{style}"' if style else ''
    tr = f' transform="rotate({rotate} {x} {y})"' if rotate else ''
    out.append(f'<text xml:space="preserve" x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}"{st}{tr}>{escape(s)}</text>')


def lines(x, y, rows, size=12, gap=None, **kw):
    gap = gap or round(size * 1.35)
    for i, s in enumerate(rows):
        text(x, y + i * gap, s, size, **kw)


def arrow(pts, color, label=None, lx=None, ly=None, dash=None, both=False, anchor='start', sw=2):
    d = 'M ' + ' L '.join(f'{x} {y}' for x, y in pts)
    mk = {C['line']: 'a-ink', C['exc']: 'a-exc', C['kern_s']: 'a-kern', C['lz4_s']: 'a-lz4', C['cpu_s']: 'a-cpu'}[color]
    ds = f' stroke-dasharray="{dash}"' if dash else ''
    ms = f' marker-start="url(#{mk}-s)"' if both else ''
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}"{ds} marker-end="url(#{mk})"{ms}/>')
    if label:
        text(lx, ly, label, 12, 'bold', anchor, color)


def padlock(x, y, label):
    """Small padlock with the lock's name; (x, y) is the top left of the icon."""
    c = C['lock']
    out.append(f'<path d="M {x+3} {y+7} v -3 a 4 4 0 0 1 8 0 v 3" fill="none" stroke="{c}" stroke-width="2"/>')
    out.append(f'<rect x="{x}" y="{y+7}" width="14" height="10" rx="2" fill="{c}"/>')
    text(x + 19, y + 16, label, 12, 'bold', fill=c)


def core(x0, name):
    rect(x0, 135, 390, 445, '#FFFFFF', C['cpu_s'], rx=10, sw=2)
    text(x0 + 14, 160, name, 18, 'bold')
    text(x0 + 376, 160, 'hardware, one set per core', 12, anchor='end', fill=C['mute'])
    for i, tx in enumerate((x0 + 15, x0 + 200)):
        rect(tx, 175, 175, 135, '#FDFDFD', C['mute'], sw=1.2)
        text(tx + 10, 193, f'hardware thread T{i}', 13, fill=C['mute'])
        rect(tx + 10, 202, 155, 44, C['user_f'], C['user_s'])
        text(tx + 87, 221, 'user SW thread', 13, 'bold', 'middle')
        text(tx + 87, 238, 'asks with a VA', 12, anchor='middle')
        rect(tx + 10, 254, 155, 48, C['kern_f'], C['kern_s'], dash='6 4', sw=2)
        text(tx + 87, 273, 'kernel SW instance', 13, 'bold', 'middle')
        text(tx + 87, 290, 'same code · own stack', 12, anchor='middle')
    # MMU and TLB
    rect(x0 + 15, 365, 360, 105, C['cpu_f'], C['cpu_s'])
    rect(x0 + 27, 377, 336, 56, C['tlb_f'], C['cpu_s'])
    text(x0 + 195, 400, 'TLB:  VA → PA', 17, 'bold', 'middle')
    text(x0 + 195, 421, 'one per core, shared by both threads (P3)', 12, anchor='middle')
    text(x0 + 27, 455, 'CPU MMU', 15, 'bold')
    text(x0 + 363, 455, 'no HW page walk (P1): miss → exception', 12, 'bold', 'end', C['exc'])
    # each thread: ask, miss goes back to the thread that asked, its kernel instance refills
    for tx in (x0 + 15, x0 + 200):
        arrow([(tx + 30, 310), (tx + 30, 375)], C['line'], 'VA', tx + 36, 345)
        arrow([(tx + 90, 377), (tx + 90, 312)], C['exc'], 'miss', tx + 85, 345, anchor='end')
        arrow([(tx + 135, 310), (tx + 135, 375)], C['kern_s'], 'refill', tx + 141, 345)
    # L1
    rect(x0 + 15, 500, 360, 60, C['cpu_f'], C['cpu_s'])
    text(x0 + 195, 524, 'L1 cache (I and D)', 15, 'bold', 'middle')
    text(x0 + 195, 544, 'private to this core · looked up with the PA', 12, anchor='middle')
    arrow([(x0 + 195, 470), (x0 + 195, 498)], C['line'], 'PA', x0 + 203, 489)
    arrow([(x0 + 195, 560), (x0 + 195, 613)], C['line'], 'PA, on an L1 miss', x0 + 203, 600)


def build():
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}" role="img" '
               'aria-label="Each core has its own MMU, TLB and L1 cache. All cores share one L2 cache, the DRAM, one copy of the kernel SW, '
               'the page table, the COT and one LZ4 HW. Shared tables and the job ring are guarded by locks.">')
    defs = ['<defs>']
    for key, col in (('a-ink', C['line']), ('a-exc', C['exc']), ('a-kern', C['kern_s']), ('a-lz4', C['lz4_s']), ('a-cpu', C['cpu_s'])):
        defs.append(f'<marker id="{key}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="{col}"/></marker>')
        defs.append(f'<marker id="{key}-s" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M10 0 L0 5 L10 10 z" fill="{col}"/></marker>')
    defs.append('<pattern id="hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
                '<rect width="10" height="10" fill="#ECEEF1"/><line x1="0" y1="0" x2="0" y2="10" stroke="#8A94A3" stroke-width="3"/></pattern>')
    defs.append('</defs>')
    out.extend(defs)
    rect(0, 0, W, H, '#FFFFFF', 'none', rx=0, sw=0)

    # title
    text(30, 45, 'Processor and compression layer: what is per core, what is shared', 28, 'bold')
    text(30, 72, 'Platform assumptions: P1 no hardware page table walk · P2 per-core L1, one shared L2 · P3 one TLB per core, shared by its threads · P4 LZ4 HW takes N jobs at once. '
         'The number of cores and threads is illustrative.', 14, fill=C['mute'])

    # processor
    rect(30, 95, 1310, 610, C['proc_f'], C['line'], rx=12, sw=2.5)
    text(70, 121, 'PROCESSOR: several cores, several hardware threads per core', 15, 'bold', fill=C['mute'])
    core(70, 'Core 0')
    core(500, 'Core 1')
    core(930, 'Core N')
    rect(70, 615, 1250, 70, C['l2_f'], C['cpu_s'], sw=2)
    text(695, 644, 'L2 cache: ONE, shared by all cores (P2)', 18, 'bold', 'middle')
    text(695, 667, 'sees physical addresses only · kernel tables and user SW data compete for it', 13, anchor='middle')

    # the one kernel image, executed by every instance

    # notes
    rect(1360, 95, 410, 222, '#FFFFFF', C['line'])
    text(1375, 119, 'One access, three outcomes', 16, 'bold')
    lines(1375, 143, ['1  TLB hit: hardware only.',
                      '    VA → PA, then L1, L2, DRAM.'], 13)
    lines(1375, 187, ['2  TLB miss, page is in a frame: the thread that',
                      '    missed enters kernel SW, which reads the page',
                      "    table and refills its core's TLB."], 13)
    lines(1375, 249, ['3  TLB miss, page is compressed: kernel takes',
                      '    mm_lock, reads the COT, takes a frame; LZ4 HW',
                      '    decompresses; kernel takes mm_lock again',
                      '    and maps the page.'], 13)

    # LZ4 HW
    rect(1440, 335, 330, 370, C['lz4_f'], C['lz4_s'], rx=10, sw=2.5)
    text(1605, 366, 'LZ4 HW', 22, 'bold', 'middle')
    text(1605, 389, 'N engines, up to N jobs at once (P4)', 14, 'bold', 'middle', C['lz4_s'])
    for i, lab in enumerate(('engine 0', 'engine 1', '…', 'engine N−1')):
        rect(1458 + i * 74, 400, 68, 28, '#FFFFFF', C['lz4_s'], rx=4, sw=1.5)
        text(1492 + i * 74, 419, lab, 11, 'bold', 'middle')
    lines(1458, 456, ['· a free engine takes the next job',
                      '· completions in finish order, found by tag',
                      '· DECOMPRESS: chunks to a frame',
                      '· COMPRESS: a frame to chunks',
                      '· computes and checks the CRC-32',
                      '· reads and writes DRAM with PAs,',
                      '   bypassing L1 and L2',
                      '· engines share no data state'], 13, gap=20)
    padlock(1458, 606, 'ring_lock before a job is queued')
    lines(1458, 650, ['Shared by every core. N is not decided.', 'Job N+1 waits in the ring for a free engine.'], 12, fill=C['mute'])
    arrow([(1340, 440), (1438, 440)], C['kern_s'], 'doorbell', 1389, 432, anchor='middle')
    arrow([(1440, 500), (1342, 500)], C['exc'], 'interrupt', 1391, 492, anchor='middle')
    text(1391, 520, 'to one core', 11, anchor='middle', fill=C['mute'])

    # DRAM
    rect(30, 790, 1740, 400, C['ram_f'], C['ram_s'], rx=12, sw=2.5)
    text(75, 817, 'DRAM, 512 MiB of physical address space (widths not to scale)', 18, 'bold')
    arrow([(695, 685), (695, 788)], C['line'], 'PA, on an L2 miss', 704, 745)

    # pinned region
    rect(45, 835, 690, 340, '#FFFFFF', C['ram_s'])
    text(64, 856, 'pinned region · 0x80000000 · 56 MiB · never compressed', 13, 'bold')
    rect(80, 872, 180, 130, C['kern_f'], C['kern_s'], sw=3)
    text(170, 899, 'kernel SW code', 16, 'bold', 'middle')
    text(170, 922, 'ONE copy', 15, 'bold', 'middle', C['kern_s'])
    lines(170, 947, ['run by every hardware', 'thread that takes an', 'exception or interrupt'], 12, anchor='middle')
    rect(275, 872, 215, 130, C['cell_f'], C['ram_s'])
    text(287, 895, 'page table  pte[]', 15, 'bold')
    lines(287, 917, ['8 B per page', 'kernel reads it on a TLB miss', 'hardware never reads it (P1)'], 12)
    padlock(287, 973, 'mm_lock to change it')
    rect(505, 872, 215, 130, C['cell_f'], C['ram_s'])
    text(517, 895, 'kernel tables', 15, 'bold')
    lines(517, 917, ['state[]  frame_of[]  owner[]', 'bitmap  free_stack', 'hand, counters'], 12)
    padlock(517, 973, 'mm_lock')
    rect(80, 1015, 180, 145, C['cell_f'], C['ram_s'])
    text(92, 1038, 'kernel stacks', 15, 'bold')
    lines(92, 1060, ['one per thread', 'private to its instance:', 'no lock needed'], 12)
    rect(275, 1015, 215, 145, C['cell_f'], C['ram_s'])
    text(287, 1038, 'job ring, completion ring', 15, 'bold')
    lines(287, 1060, ['one of each, 16 slots each', 'kernel writes jobs,', 'LZ4 HW writes completions'], 12)
    padlock(287, 1116, 'ring_lock to add a job')
    rect(505, 1015, 215, 145, '#FFF5F5', C['lock'], dash='5 4')
    padlock(517, 1026, 'what the locks mean')
    lines(517, 1062, ['One instance at a time inside.', 'mm_lock is the one lock over', 'every table. It is held for table',
                      'work only, not while waiting', 'for the LZ4 HW.'], 12)

    # HRT
    rect(750, 835, 135, 340, '#FFFFFF', C['ram_s'])
    text(817, 862, 'HRT memory', 15, 'bold', 'middle')
    lines(817, 886, ['0x83800000', '36 MiB', '', 'not compressed', '', 'never needs', 'decompression'], 12, anchor='middle')

    # COT
    rect(900, 835, 160, 340, '#FFFFFF', C['ram_s'])
    text(980, 862, 'COT', 17, 'bold', 'middle')
    lines(980, 886, ['0x85c00000', '4.5 MiB', '', '32 B per page:', 'which chunks,', 'stream length,', 'CRC-32'], 12, anchor='middle')
    padlock(946, 1010, 'mm_lock')

    # chunk pool, hatched because it holds compressed data
    rect(1075, 835, 335, 340, 'url(#hatch)', C['ram_s'])
    rect(1100, 850, 285, 138, '#FFFFFF', C['ram_s'], sw=1)
    text(1242, 877, 'chunk pool', 17, 'bold', 'middle')
    lines(1242, 901, ['0x86100000 · 275 MiB', 'compressed streams', '563200 chunks of 512 B', 'written by the LZ4 HW'], 12, anchor='middle')

    # frames
    rect(1425, 835, 330, 340, C['cell_f'], C['ram_s'])
    text(1590, 877, 'frame region', 17, 'bold', 'middle')
    lines(1590, 901, ['0x97400000 · 140 MiB', 'uncompressed pages (PRESENT)', '35840 frames of 4 KiB', 'where a user SW TLB entry points'], 12, anchor='middle')
    for i in range(6):
        rect(1447 + i * 48, 1010, 40, 40, C['user_f'] if i in (0, 1, 3) else '#FFFFFF', C['ram_s'], rx=3, sw=1)
    text(1590, 1072, 'filled = holds a page, empty = free frame', 12, anchor='middle', fill=C['mute'])

    # every instance runs the one kernel image
    arrow([(95, 278), (54, 278), (54, 937), (78, 937)], C['kern_s'], dash='6 4')
    text(46, 455, 'every kernel SW instance runs the one copy of the code', 12, 'bold', 'middle', C['kern_s'], rotate=-90)

    # LZ4 HW to DRAM
    arrow([(1490, 705), (1490, 750), (1300, 750), (1300, 833)], C['lz4_s'], 'streams', 1392, 743, both=True, anchor='middle')
    arrow([(1640, 705), (1640, 833)], C['lz4_s'], 'pages', 1649, 770, both=True)

    # legend
    y = 1218
    text(30, y + 14, 'Legend', 14, 'bold')
    items = [(C['user_f'], C['user_s'], None, 'user SW, the party served'),
             (C['kern_f'], C['kern_s'], '6 4', 'kernel SW: one copy, an instance per trapping thread'),
             (C['cpu_f'], C['cpu_s'], None, 'CPU hardware, per core'),
             (C['l2_f'], C['cpu_s'], None, 'CPU hardware, shared'),
             (C['lz4_f'], C['lz4_s'], None, 'LZ4 HW, shared'),
             ('url(#hatch)', C['ram_s'], None, 'compressed data')]
    x = 100
    for f, s, d, lab in items:
        rect(x, y, 26, 18, f, s, rx=3, dash=d)
        text(x + 34, y + 14, lab, 13)
        x += 34 + int(len(lab) * 7.0) + 28
    padlock(x, y - 1, 'shared: take this lock first')
    lines(30, y + 52, ['TLBs are private copies of the page table and hardware does not keep them coherent. Before a frame is reused or compressed, '
                       'the kernel removes that page from the TLB of every core.',
                       'Up to one kernel SW instance per hardware thread can run at the same time. They meet only at the locks and at the LZ4 HW, which runs up to N jobs at once.'],
          13, gap=21, fill=C['ink'])
    out.append('</svg>')
    return '\n'.join(out)


if __name__ == '__main__':
    target = Path(__file__).resolve().parent / 'processor-overview.svg'
    target.write_text(build(), encoding='utf-8')
    print(target)

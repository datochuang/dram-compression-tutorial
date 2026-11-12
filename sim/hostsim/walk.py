"""Walk-throughs: the step log of one real occurrence of each case, as a table.

Every row is one step with who did it (CPU, FW = kernel, HW = LZ4 HW) and the
values it used. Nothing here is written by hand; a row exists because the code
in kernel.py, hw.py or machine.py logged it.
"""
from ifsim.report import table
from ifsim.spec import SPEC

from .machine import Machine

WHO = {'CPU': 'CPU', 'FW': 'kernel', 'HW': 'LZ4 HW'}
STEP = {
    ('CPU', 'access'): 'user SW 的一道指令要存取這個 page',
    ('CPU', 'page_fault'): 'CPU MMU 查到 PTE 無效，CPU 進入 page fault exception',
    ('CPU', 'instruction_runs'): 'CPU 回到同一道指令重新執行，這次 PTE 有效',
    ('FW', 'lock'): '取得 lock',
    ('FW', 'unlock'): '放開 lock',
    ('FW', 'take_frame'): '從 free frame stack 取一個 frame',
    ('FW', 'put_frame'): '把 frame 還給 free frame stack',
    ('FW', 'zero_frame'): '把 frame 填成 0',
    ('FW', 'cache_clean'): '把 CPU cache 裡這個 frame 的 dirty line 寫回 DRAM',
    ('FW', 'cache_invalidate'): '把這個 frame 的 line 從每個 core 的 data cache 與 instruction cache 丟掉',
    ('FW', 'state'): '改 page state',
    ('FW', 'pte_map'): '寫入 PTE，設為有效',
    ('FW', 'pte_unmap'): '把 PTE 設為無效並 flush TLB',
    ('FW', 'cot_read'): '讀這個 page 的 COT entry',
    ('FW', 'cot_write'): '寫這個 page 的 COT entry',
    ('FW', 'job'): '組好 descriptor 交給 LZ4 HW，然後等待',
    ('FW', 'completion'): '收到 completion',
    ('FW', 'bitmap_reserve'): '從 bitmap 保留 chunk',
    ('FW', 'bitmap_trim'): '把沒用到的 chunk 還給 bitmap',
    ('FW', 'bitmap_release'): '把 chunk 還給 bitmap',
    ('FW', 'pick_victim'): 'clock 選出要搬走的 page',
    ('FW', 'bitmap_failed'): 'job 失敗，把保留的 chunk 全部還給 bitmap',
    ('FW', 'sw_decode'): 'kernel 自己的 LZ4 decoder：CPU 讀 chunk，核對 CRC-32，解壓縮',
    ('FW', 'frame_write'): 'CPU 把解出來的 page 寫進 frame',
    ('FW', 'no_completion'): 'driver 等不到 completion，已經放棄',
    ('FW', 'lz4_off'): '從這裡起不再使用 LZ4 HW，直到下次開機',
    ('FW', 'cache_flush_layer'): '開機：把 frame 區與 chunk pool 的 line 寫回 DRAM 並從每個 core 的 cache 丟掉',
    ('HW', 'bus_error'): 'bus 存取失敗，job 中止，回報 BUS_ERROR',
    ('HW', 'compress'): '讀 frame，壓縮，把 stream 寫進 chunk',
    ('HW', 'decompress'): '讀 chunk，核對 CRC-32，解壓縮，寫進 frame',
}
HEX8 = {'frame_pa', 'checksum', 'crc', 'expected_crc'}
LISTS = {'chunk', 'chunks', 'wrote_chunks', 'read_chunks'}
RAW = {'desc': 'job descriptor', 'cpl': 'completion', 'entry': 'COT entry'}
ENUM = {'opcode': 'opcode', 'status': 'status'}


def fmt(key, v):
    if key in HEX8:
        return f'0x{v:08X}'
    if key in LISTS:
        return '[' + ', '.join(f'0x{c:X}' for c in v) + ']'
    if key in ('h', 'tag', 'flags'):
        return f'0x{v:X}'
    if key in ENUM:
        return SPEC.enum_name[ENUM[key]].get(v, str(v))
    if key in ('old', 'new'):
        return str(v).upper()
    return str(v)


def capture(n=20000, **kw):
    """Build and boot a small machine, then run n accesses with the step log on."""
    m = Machine('small', **kw)
    m.build_image()
    m.boot()
    m.log.sink = []
    m.run(n)
    return m, m.log.sink


def _spans(log, name):
    """Every [enter name ... leave name] slice, with the pick_victim step in front of an eviction."""
    out, start = [], None
    for i, (who, what, v) in enumerate(log):
        if what == 'enter ' + name:
            start = i - 1 if i and log[i - 1][1] == 'pick_victim' else i
        elif what == 'leave ' + name and start is not None:
            out.append(log[start:i + 1])
            start = None
    return out


def _accesses(log):
    out, start = [], None
    for i, (who, what, v) in enumerate(log):
        if what == 'access':
            start = i
        elif what == 'instruction_runs':
            out.append(log[start:i + 1])
    return out


def _has(ev, what, **match):
    return any(w == what and all(v.get(k) == x for k, x in match.items()) for _, w, v in ev)


def scenarios(log):
    """First clean occurrence of each case in a step log. A case that did not occur is missing."""
    out = {}
    for ev in _accesses(log):
        faults = [v['result'] for _, w, v in ev if w == 'leave page_fault']
        if len(faults) != 1 or _has(ev, 'enter reclaim'):
            continue
        out.setdefault(faults[0], ev)
    for ev in _spans(log, 'evict_ro'):
        out.setdefault('evict_ro', ev)
    ST = SPEC.enum['status']
    for ev in _spans(log, 'evict_rw'):
        if _has(ev, 'completion', status=ST.OK):
            out.setdefault('evict_rw_ok', ev)
        elif _has(ev, 'completion', status=ST.INCOMPRESSIBLE):
            out.setdefault('evict_rw_incompressible', ev)
    for ev in _spans(log, 'reclaim'):
        if _has(ev, 'enter evict_ro') and _has(ev, 'enter evict_rw'):
            out.setdefault('reclaim', ev)
    return out


def lost_scenario(seed=3, n=8000, corrupt_every=200):
    """A run with fault injection: the first access that meets a damaged stream."""
    _, log = capture(n, seed=seed, corrupt_every=corrupt_every)
    for i, (who, what, v) in enumerate(log):
        if what == 'leave page_fault' and v['result'] == 'lost':
            j = i
            while log[j][1] != 'access':
                j -= 1
            return log[j:i + 1]
    return None


def rescued_scenario(seed=1, warm=6000, n=4000, mode='bus_error'):
    """A run where one DECOMPRESS job fails although the stored stream is intact: the first access
    that the kernel's own decoder brings back."""
    m = Machine('small', seed=seed)
    m.build_image()
    m.boot()
    m.run(warm)
    m.hw.inject('DECOMPRESS', mode)
    m.log.sink = []
    m.run(n)
    for ev in _accesses(m.log.sink):
        if _has(ev, 'sw_decode') and not _has(ev, 'enter reclaim'):
            return ev
    return None


def md(ev):
    """One scenario as a step table, followed by the raw bytes of every structure in it."""
    rows, raws, depth = [], [], 0
    for who, what, v in ev:
        v = dict(v)
        if what.startswith('enter '):
            text = f'進入 `{what[6:]}`'
        elif what.startswith('leave '):
            text = f'離開 `{what[6:]}`'
        else:
            text = STEP[who, what]
        for key in RAW:
            if key in v:
                raws.append((len(rows) + 1, RAW[key], v.pop(key)))
        vals = '，'.join(f'{k} = {fmt(k, x)}' for k, x in v.items())
        rows.append((len(rows) + 1, WHO[who], text, vals))
    out = table(('#', '誰', '步驟', '用到的值'), rows)
    if raws:
        lines = []
        for n, name, raw in raws:
            lines.append(f'step {n}  {name}, {len(raw)} B')
            lines += ['    ' + ' '.join(f'{b:02X}' for b in raw[i:i + 16]) for i in range(0, len(raw), 16)]
        out += '\n\n記憶體裡的 byte，由低位址到高位址：\n\n```text\n' + '\n'.join(lines) + '\n```'
    return out


def md_reclaim(ev, keep=6):
    """One whole reclaim run, one row per victim."""
    rows, pick = [], None
    for who, what, v in ev:
        if what == 'pick_victim':
            pick = v
        elif what in ('leave evict_ro', 'leave evict_rw'):
            rows.append((len(rows) + 1, fmt('h', pick['h']), 'RO' if what.endswith('ro') else 'RW',
                         pick['frames_looked_at'], '`' + what[6:] + '`', v['result']))
    total = sum(r[5] for r in rows)
    shown = rows if len(rows) <= 2 * keep else rows[:keep] + [('…', '…', '…', '…', '…', '…')] + rows[-keep:]
    return (table(('#', '選到的 page h', '種類', 'clock 看了幾個 frame', '處理', '釋放的 frame'), shown)
            + f'\n\n這一次 `reclaim` 共處理 {len(rows)} 個 page，釋放 {total} 個 frame。')


def text(ev):
    """Plain text for the terminal."""
    L = []
    for i, (who, what, v) in enumerate(ev, 1):
        vals = ', '.join(f'{k}={x.hex() if isinstance(x, bytes) else fmt(k, x)}' for k, x in v.items())
        L.append(f'{i:3d}  {WHO[who]:7s} {what:18s} {vals}')
    return '\n'.join(L)

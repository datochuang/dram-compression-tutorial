"""Every kernel step down to the bytes: which table, where it lives, what is computed, what it costs.

deps.py says which steps exist, what each reads and writes by name, and which step has to wait for which.
It says nothing about bytes. This module adds, for every step of deps.STEPS:

    the accesses    table, entry size, index, where the table lives
    the operation   the arithmetic in words
    instructions    counted by running the step: sim/kstep/kstep.h is the step in C with one fixed layout,
                    sim/kstep/measure.c runs it and reads the CPU's count of retired instructions
    cache lines     counted from the layout: how many 64 B lines the step touches that the operation has not
                    touched before
    cycles          a model on top of the two: named assumptions, nothing more

Three kinds of numbers come out and every one is tagged:

    measured   instructions of a step that was run (AArch64, clang -O2). The same binary retires the same
               instructions on any AArch64 core; another compiler or another instruction set moves them.
    counted    cache lines, register writes, cache maintenance operations: read off the layout and the code
    assumed    the cycle model, and every step that needs the privileged side of a CPU or the OS (exception
               entry, TLB invalidate, interrupt, wake-up): those keep the value of ifsim.params

The accesses declared here are held against the read and write sets of deps.py, which a traced run checks.
"""
import json
import os
import platform
import shutil
import subprocess
import tempfile

from lz4sim.config import SystemConfig

from . import deps

HERE = os.path.dirname(os.path.abspath(__file__))
KSTEP = os.path.normpath(os.path.join(HERE, '..', 'kstep'))
SPEC = os.path.normpath(os.path.join(HERE, '..', '..', 'spec'))
LINE = 64                               # bytes of a CPU cache line, as the interface spec assumes (RING_ALIGN)

# ---------------------------------------------------------------------------------------- the cycle model
# Every value is an assumption. K1 (which CPU, which kernel) is open.
MODEL = {
    'cpu_hz': 1_000_000_000,            # 1 cycle = 1 ns, so the numbers sit beside those of ifsim.params
    'cpi': 1.0,                         # cycles per instruction while every line it needs is in the L1 cache
    'miss': 100,                        # cycles to get one line from DRAM (lz4sim.config dram_ns at 1 GHz)
    'mmio': 50,                         # cycles of one write to a register of the LZ4 HW (ifsim.params mmio_ns)
}

# ---------------------------------------------------------------------------------------------- the tables
# where: kmem   kernel memory: pinned, outside the compression layer, address chosen by the linker
#        cot    DRAM at cot_base
#        pt     the page table the CPU MMU walks (kernel memory; its shape is an assumption, K1)
#        ring   the two rings: pinned kernel memory that the LZ4 HW reads and writes through its master port
#        reg    registers of the LZ4 HW
#        frame  the frame area          pool   the chunk pool
#        local  the thread's own stack and CPU registers
#        cpu    inside the CPU: TLB, caches, exception registers
#        os     objects of the OS scheduler (K1)          hw     inside the LZ4 HW
WHERE_ZH = {
    'kmem': 'kernel 記憶體（pinned）', 'cot': 'DRAM 的 COT 區', 'pt': 'CPU MMU 的 page table',
    'ring': 'ring 記憶體（pinned）', 'reg': 'LZ4 HW register', 'frame': 'DRAM 的 frame 區',
    'pool': 'DRAM 的 chunk pool', 'local': 'thread 自己的 stack', 'cpu': 'CPU 內部', 'os': 'OS scheduler',
    'hw': 'LZ4 HW 內部',
}
# name: (where, bytes of one entry, what the count is, what it holds)
TABLES = {
    'state': ('kmem', 1, 'pages', '每個 page 的狀態，6 個值'),
    'frame_of': ('kmem', 4, 'pages', '每個 page 現在在哪個 frame，沒有就是 -1'),
    'fresh_n': ('kmem', 2, 'pages', '這個 page 在幾個 thread 的 fresh 名單裡'),
    'pins': ('kmem', 2, 'pages', '`pin_page` 的計數'),
    'incompressible': ('kmem', 1 / 8, 'pages', '每個 page 一個 bit：壓不進 7 個 chunk'),
    'owner': ('kmem', 4, 'frames', '每個 frame 屬於哪個 page，空的就是 -1'),
    'free_stack': ('kmem', 4, 'frames', 'free frame 的 stack，`free_top` 是個數'),
    'bitmap': ('kmem', 8, 'words', '每個 chunk 一個 bit，1 是使用中；`cursor` 是下次開始找的 word'),
    'scalars': ('kmem', 48, 1, '`free_top`、`hand`、`cursor`、`free_chunks`、`tag`、`strikes`、`job_tail`、`cpl_head`、'
                               '`frame_waiters`、`pool_full`、`lz4_off`、`mm_lock`'),
    'fresh': ('kmem', 8, 'threads', '每個 thread 一份：最近 fault 進來的 page（`protect` = 1）'),
    'cot': ('cot', 32, 'pages', '每個 page 的 COT entry：flags、chunk 數、stream 長度、CRC-32、8 個 3 B 的 chunk 編號'),
    'pte': ('pt', 8, 'pages', 'PTE：frame 位址、valid（bit 0）、accessed flag（bit 10）'),
    'job_ring': ('ring', 64, 'job_entries', 'job ring，一格 64 B，descriptor 用前 48 B'),
    'cpl_ring': ('ring', 16, 'cpl_entries', 'completion ring，一筆 16 B'),
    'reg': ('reg', 4, 2, '`JOB_TAIL`（0x28，doorbell）與 `CPL_HEAD`（0x3C）'),
    'frame': ('frame', 4096, 'frames', 'page 解開後的內容'),
    'chunk': ('pool', 512, 'pool_chunks', '壓縮後的 stream'),
}


def sizes(cfg=None):
    cfg = cfg or SystemConfig()
    return {'pages': cfg.pages, 'frames': cfg.frames, 'words': (cfg.pool_chunks + 63) // 64,
            'pool_chunks': cfg.pool_chunks, 'job_entries': 16, 'cpl_entries': 16, 'threads': 4,
            'ro_first': cfg.ro_first, 'fc_low': cfg.fc_low, 'fc_high': cfg.fc_high,
            'compress_limit': cfg.compress_limit, 'cot_base': cfg.cot_base, 'pool_base': cfg.pool_base,
            'fc_base': cfg.fc_base, 'pinned_base': cfg.pinned_base, 'hrt_base': cfg.hrt_base,
            'dram_end': cfg.dram_end}


def layout(cfg=None):
    """One row per table: where, entry size, entries, bytes, cache lines, fixed address if it has one."""
    z = sizes(cfg)
    base = {'cot': z['cot_base'], 'frame': z['fc_base'], 'chunk': z['pool_base']}
    rows = []
    for name, (where, entry, count, holds) in TABLES.items():
        n = count if isinstance(count, int) else z[count]
        size = int(entry * n + 0.999)
        rows.append({'name': name, 'where': where, 'entry': entry, 'entries': n, 'bytes': size,
                     'lines': -(-size // LINE), 'base': base.get(name), 'holds': holds})
    return rows


# ---------------------------------------------------------------------------------------------- the steps
# One access: (table, mode, bytes, index, temperature, names in deps.py)
#   mode         R, W or RW
#   index        which entry: h (the page), f (the frame), old (another page), top, w (bitmap words), ...
#   temperature  hot    a scalar of the kernel or the top of a stack: assumed to be in the L1 cache
#                line   one line of a big table at an index nobody chose: a miss the first time an operation
#                       touches it
#                dram   a line the LZ4 HW has just written: always fetched from DRAM
#                seq    a table walked in order: one new line every (64 / entry) entries
#                bulk   a whole frame or stream, counted separately
#                mmio   a register of the LZ4 HW
#                local  stack or CPU registers of the running thread
#                none   not memory of the kernel (CPU, OS or LZ4 HW internals)
class D:
    def __init__(self, acc, op, key=None, basis='measured', per=None, also=None, extra=()):
        self.acc, self.op, self.key, self.basis = acc, op, key, basis
        self.per = per or {}            # the cost of doing one more unit: {unit: measurement key or text}
        self.also = also                # what the measurement leaves out
        self.extra = extra              # deps names this step touches through an OS or CPU service


def A(table, mode, nbytes, index, temp, names):
    return (table, mode, nbytes, index, temp, tuple(names.split()))


DETAIL = {
    'access': D([A('pte', 'R', 8, 'h', 'none', 'pte[h]')],
                'CPU MMU：TLB 裡沒有這一頁，硬體走 page table，讀到的 PTE bit 0 是 0', basis='cpu',
                extra=('tlb',)),
    'exception': D([], 'CPU 存下 PC 與狀態，跳到 exception vector；kernel 讀出 fault 位址，`h = (va - base) >> 12`',
                   basis='assumed', extra=('regs',)),
    'check_state': D([A('state', 'R', 1, 'h', 'line', 'state[h]'), A('scalars', 'R', 4, 'free_top', 'hot', 'free_frames')],
                     '讀 1 個 byte；依序比對 PRESENT、LOST、COMPRESSING 或 DECOMPRESSING；再看 `free_top` 是不是 0',
                     key='check_state'),
    'wait_page': D([], 'OS：把 thread 掛到 page h 的等待佇列，放開 lock 睡著', basis='os', extra=('waiters[h]',)),
    'wait_frame': D([A('scalars', 'RW', 4, 'frame_waiters', 'hot', 'frame_waiters')],
                    'OS：叫醒 reclaimer，把 thread 掛到等 frame 的佇列，放開 lock 睡著', basis='os'),
    'take_frame': D([A('scalars', 'RW', 4, 'free_top', 'hot', 'free_frames'),
                     A('free_stack', 'R', 4, 'top', 'hot', 'free_frames'),
                     A('frame_of', 'W', 4, 'h', 'line', 'frame_of[h]'), A('owner', 'W', 4, 'f', 'line', 'owner[f]')],
                    'stack pop：`f = free_stack[--free_top]`；兩個 store；`pa = fc_base + (f << 12)`', key='take_frame'),
    'zero_frame': D([A('frame', 'W', 4096, 'f', 'bulk', 'frame[f] cache[f]')],
                    '`DC ZVA` 64 次，一次把一條 64 B 的 line 清成 0，不必先從 DRAM 讀進來', key='zero_frame',
                    also='C library 的 memset；換一個 library 指令數會變'),
    'cot_read': D([A('cot', 'R', 32, 'h', 'line', 'cot[h]')],
                  '位址 `cot_base + h * 32`；讀 32 B（兩個 16 B 的 load）到 stack；測 valid flag', key='cot_read'),
    'mark_decompressing': D([A('scalars', 'R', 1, 'lz4_off', 'hot', 'lz4_off'), A('state', 'W', 1, 'h', 'line', 'state[h]')],
                            '讀 `lz4_off` 決定用不用 HW；寫 1 個 byte', key='mark_decompressing'),
    'note_hw': D([A('scalars', 'RW', 4, 'strikes', 'hot', 'strikes'), A('scalars', 'RW', 1, 'lz4_off', 'hot', 'lz4_off')],
                 '答對就把 `strikes` 歸零，答錯加 1；到 3 就把 `lz4_off` 寫成 1', key='note_hw'),
    'cot_clear': D([A('cot', 'W', 32, 'h', 'line', 'cot[h]')], '把 32 B 寫成 0（兩個 16 B 的 store）', key='cot_clear'),
    'release_chunks': D([A('bitmap', 'RW', 8, 'w', 'line', 'bitmap'), A('scalars', 'W', 4, 'free_chunks', 'hot', 'bitmap'),
                         A('scalars', 'W', 1, 'pool_full', 'hot', 'pool_full')],
                        '對每個 chunk：從 COT entry 的 3 個 byte 組出編號 c，`bitmap[c >> 6] &= ~(1 << (c & 63))`；'
                        '`free_chunks += n`；`pool_full = 0`', key='release_chunks',
                        per={'chunk': '5 個 chunk 共 80 道，每個約 16 道'}),
    'set_present': D([A('state', 'W', 1, 'h', 'line', 'state[h]')], '寫 1 個 byte', key='set_state'),
    'set_lost': D([A('state', 'W', 1, 'h', 'line', 'state[h]')], '寫 1 個 byte', key='set_state'),
    'set_compressed': D([A('state', 'W', 1, 'h', 'line', 'state[h]')], '寫 1 個 byte', key='set_state'),
    'mark_compressing': D([A('state', 'W', 1, 'h', 'line', 'state[h]')], '寫 1 個 byte', key='set_state'),
    'pte_map': D([A('pte', 'W', 8, 'h', 'line', 'pte[h] accessed[h]')],
                 '`pte = pa | 屬性 | accessed | valid`，一個 8 B 的 store', key='pte_map',
                 also='PTE 從 invalid 變 valid 不必清 TLB；CPU 要求的 barrier 沒有算進去'),
    'wake_page': D([], 'OS：page h 的等待佇列裡有人就叫醒；沒有人時只是一次比較', basis='os', extra=('waiters[h]',)),
    'note_fresh': D([A('fresh', 'RW', 8, 't', 'hot', ''), A('fresh_n', 'RW', 2, 'h', 'line', 'fresh_n[h]'),
                     A('fresh_n', 'RW', 2, 'old', 'line', 'fresh_n[*]')],
                    '這個 thread 的名單換進 h、換出上一個 page old；`fresh_n[h]++`；`fresh_n[old]--`', key='note_fresh'),
    'wake_check': D([A('scalars', 'R', 4, 'free_top', 'hot', 'free_frames')], '比較 `free_top <= fc_low`',
                    key='wake_check', also='比較成立時叫醒 reclaimer 是一次 OS 呼叫，沒有算進去', extra=('reclaimer',)),
    'desc': D([A('scalars', 'RW', 4, 'tag', 'hot', 'tag')],
              '`tag` 做 atomic 加 1；在 stack 上填 48 B：opcode、chunk 數、limit、frame 位址、長度、CRC-32、tag、'
              '8 個 3 B 的 chunk 編號', key='desc_decompress',
              per={'DECOMPRESS': 'chunk 編號從 COT entry 整塊複製 24 B', 'COMPRESS': '7 個編號各自拆成 3 個 byte'}),
    'submit': D([A('scalars', 'RW', 4, 'job_tail', 'hot', 'job_ring'), A('job_ring', 'W', 48, 'tail', 'line', 'job_ring'),
                 A('reg', 'W', 4, 'JOB_TAIL', 'mmio', 'job_ring')],
                '把 48 B 複製到 `job_ring[tail]`（3 個 16 B 的 store）；`tail = (tail + 1) & 15`；寫 register `JOB_TAIL`',
                key='submit', also='`FW-CACHE-3`：ring 是 cacheable 的話，寫 doorbell 之前還要 clean 這一條 line'),
    'hw_decompress': D([A('job_ring', 'R', 48, 'tail', 'none', 'job_ring'), A('chunk', 'R', 512, 'c', 'none', 'chunk[c]'),
                        A('frame', 'W', 4096, 'f', 'none', 'frame[f]'), A('cpl_ring', 'W', 16, 'head', 'none', 'cpl_ring')],
                       'LZ4 HW：讀 descriptor、讀 chunk、核對 CRC-32、解壓縮寫進 frame、寫 completion、拉 interrupt',
                       basis='hw', extra=('irq', 'engine')),
    'hw_fail': D([A('job_ring', 'R', 48, 'tail', 'none', 'job_ring'), A('chunk', 'R', 512, 'c', 'none', 'chunk[c]'),
                  A('frame', 'W', 4096, 'f', 'none', 'frame[f]'), A('cpl_ring', 'W', 16, 'head', 'none', 'cpl_ring')],
                 'LZ4 HW：沒有把 page 交出來，completion 的 status 不是 OK', basis='hw', extra=('irq', 'engine')),
    'hw_compress': D([A('job_ring', 'R', 48, 'tail', 'none', 'job_ring'), A('frame', 'R', 4096, 'f', 'none', 'frame[f]'),
                      A('chunk', 'W', 512, 'c', 'none', 'chunk[c]'), A('cpl_ring', 'W', 16, 'head', 'none', 'cpl_ring')],
                     'LZ4 HW：讀 descriptor、讀 frame、壓縮寫進 chunk、算 CRC-32、寫 completion、拉 interrupt',
                     basis='hw', extra=('irq', 'engine')),
    'notify': D([], 'interrupt 進 CPU；handler 確認是 LZ4 HW；OS 把睡著的 thread 排回去跑', basis='assumed',
                extra=('irq', 'wake')),
    'cpl_read': D([A('scalars', 'RW', 4, 'cpl_head', 'hot', 'cpl_ring'), A('cpl_ring', 'R', 16, 'head', 'dram', 'cpl_ring'),
                   A('reg', 'W', 4, 'CPL_HEAD', 'mmio', 'cpl_ring')],
                  '從 `cpl_ring[head]` 讀 16 B；`head = (head + 1) & 15`；寫 register `CPL_HEAD`；比對 tag',
                  key='cpl_read', also='這 16 B 是 LZ4 HW 剛寫的，CPU cache 裡不會有：一定是一次 DRAM 讀取', extra=('wake',)),
    'cache_invalidate': D([A('frame', 'W', 4096, 'f', 'bulk', 'cache[f]')],
                          '對 frame 的 64 條 line 各做一次 `DC IVAC`，instruction cache 另做', basis='counted'),
    'sw_decode': D([A('chunk', 'R', 512, 'c', 'bulk', 'chunk[c]')],
                   'kernel 自己的 LZ4 decoder：讀最多 7 個 chunk，核對 CRC-32，解出 4096 B 到 kernel 的 buffer',
                   basis='unknown'),
    'frame_write': D([A('frame', 'W', 4096, 'f', 'bulk', 'frame[f] cache[f]')],
                     '把 4096 B 從 kernel 的 buffer 複製進 frame', key='frame_write',
                     also='C library 的 memcpy；換一個 library 指令數會變'),
    'sw_clean': D([A('frame', 'W', 4096, 'f', 'bulk', 'frame[f] cache[f]')],
                  '對 frame 的 64 條 line 各做一次 `DC CVAC`：dirty 的 line 寫回 DRAM', basis='counted'),
    'reclaim_check': D([A('scalars', 'R', 4, 'free_top', 'hot', 'free_frames')], '比較 `free_top < fc_high`',
                       key='reclaim_check'),
    'pick_victim': D([A('scalars', 'RW', 4, 'hand', 'hot', 'hand'), A('owner', 'R', 4, 'hand', 'seq', 'owner[*]'),
                      A('state', 'R', 1, 'h', 'line', 'state[*]'), A('pins', 'R', 2, 'h', 'line', 'pins[*]'),
                      A('fresh_n', 'R', 2, 'h', 'line', 'fresh_n[*]'),
                      A('scalars', 'R', 2, 'pool_full lz4_off', 'hot', 'pool_full lz4_off'),
                      A('incompressible', 'R', 8, 'h', 'hot', 'incompressible'),
                      A('pte', 'RW', 8, 'h', 'line', 'accessed[*]')],
                     'clock 掃描，每看一個 frame：`h = owner[hand++]`；`state[h]` 是不是 PRESENT；`pins[h] | fresh_n[h]`；'
                     'RW page 再看 `pool_full`、`lz4_off` 與 incompressible 的那個 bit；最後測 PTE 的 bit 10，'
                     '是 1 就清成 0 並放過它', key='pick_victim.rw_first',
                     per={'frame': '見 3.3 的表'}),
    'reserve': D([A('scalars', 'RW', 8, 'cursor free_chunks', 'hot', 'bitmap'), A('bitmap', 'RW', 8, 'cursor', 'line', 'bitmap'),
                  A('scalars', 'W', 1, 'pool_full', 'hot', 'pool_full')],
                 '從 `bitmap[cursor]` 開始一次讀一個 64-bit word；全是 1 就跳到下一個 word；否則取反，用 `RBIT` 加 `CLZ` '
                 '找最低的 free bit（count trailing zeros），`x &= x - 1` 清掉它，重複到拿滿 7 個；把 word 寫回去',
                 key='reserve.2_words', per={'word': '見 3.3 的表'}),
    'find_frame': D([A('frame_of', 'R', 4, 'h', 'line', 'frame_of[h]')], '讀 4 B；`pa = fc_base + (f << 12)`',
                    key='find_frame'),
    'pte_clear': D([A('pte', 'W', 8, 'h', 'line', 'pte[h]')], '把 8 B 寫成 0', key='pte_clear'),
    'tlb_inval': D([], '`TLBI`（所有 core）、`DSB`、`ISB`：3 道指令，時間花在等所有 core 完成', basis='assumed',
                   extra=('tlb',)),
    'cache_clean': D([A('frame', 'W', 4096, 'f', 'bulk', 'frame[f] cache[f]')],
                     '對 frame 的 64 條 line 各做一次 `DC CVAC`：dirty 的 line 寫回 DRAM', basis='counted'),
    'cot_store': D([A('cot', 'W', 32, 'h', 'line', 'cot[h]')],
                   '在 stack 上組 32 B：flags、chunk 數、長度、CRC-32、每個 chunk 編號拆成 3 個 byte；兩個 16 B 的 store',
                   key='cot_store'),
    'trim': D([A('bitmap', 'RW', 8, 'w', 'line', 'bitmap'), A('scalars', 'W', 4, 'free_chunks', 'hot', 'bitmap')],
              '對沒用到的每個 chunk：`bitmap[c >> 6] &= ~(1 << (c & 63))`；`free_chunks += n`', key='trim',
              per={'chunk': '2 個 chunk 共 18 道'}),
    'release_all': D([A('bitmap', 'RW', 8, 'w', 'line', 'bitmap'), A('scalars', 'W', 4, 'free_chunks', 'hot', 'bitmap')],
                     '7 個 chunk 的 bit 全部清成 0；`free_chunks += 7`', key='release_all'),
    'mark_incompressible': D([A('incompressible', 'RW', 8, 'h', 'hot', 'incompressible')],
                             '`incompressible[h >> 6] |= 1 << (h & 63)`', key='mark_incompressible'),
    'put_frame': D([A('frame_of', 'RW', 4, 'h', 'line', 'frame_of[h]'), A('owner', 'W', 4, 'f', 'line', 'owner[f]'),
                    A('scalars', 'RW', 4, 'free_top', 'hot', 'free_frames'),
                    A('free_stack', 'W', 4, 'top', 'hot', 'free_frames'),
                    A('scalars', 'RW', 4, 'frame_waiters', 'hot', 'frame_waiters')],
                   '`f = frame_of[h]`；`frame_of[h] = -1`；`owner[f] = -1`；stack push；看有沒有人在等 frame',
                   key='put_frame', also='有人在等時叫醒他們是一次 OS 呼叫，沒有算進去'),
    'eret': D([], 'kernel 還原現場，`ERET` 回到 user SW', basis='assumed', extra=('regs', 'pc')),
    'rerun': D([A('pte', 'RW', 8, 'h', 'none', 'pte[h] accessed[h]'), A('frame', 'R', 4096, 'f', 'none', 'frame[f] cache[f]')],
               'CPU 重跑同一道指令：TLB 還是沒有這一頁，硬體再走一次 page table，這次 PTE 是 valid', basis='cpu',
               extra=('pc',)),
    'kill': D([], 'OS：結束這個 user SW', basis='os', extra=('regs',)),
}
LOCK = {'lock': D([A('scalars', 'RW', 1, 'mm_lock', 'hot', '')], 'atomic exchange（`SWPAB`），沒有人握著時一次就拿到', key='lock',
                  also='有人握著時要等，等多久不在這裡'),
        'unlock': D([A('scalars', 'W', 1, 'mm_lock', 'hot', '')], '`STLRB` 寫 0', key='unlock')}
BASIS_ZH = {'measured': '量測', 'counted': '計數', 'assumed': '假設', 'unknown': '未知', 'cpu': 'CPU 硬體',
            'os': 'OS，未計', 'hw': 'LZ4 HW 模型'}
BULK_LINES = 4096 // LINE
# the same entry under another name: the frame the clock hand stops at is the victim's frame f, and the words the
# reservation was made in are the words that trim and release_all give bits back to
SAME = {('owner', 'hand'): 'f', ('bitmap', 'cursor'): 'w'}


# ------------------------------------------------------------------------------- declared against deps.py
def check():
    """Hold the accesses against deps.STEPS. Returns the disagreements; an empty list is the pass."""
    out = []
    for name, s in deps.STEPS.items():
        d = DETAIL.get(name)
        if d is None:
            out.append((name, 'no detail'))
            continue
        r = {n for a in d.acc if 'R' in a[1] for n in a[5]} | set(d.extra)
        w = {n for a in d.acc if 'W' in a[1] for n in a[5]} | set(d.extra)
        shared_r = {x for x in s.r if x not in deps.PRIVATE}
        shared_w = {x for x in s.w if x not in deps.PRIVATE}
        if shared_r - r:
            out.append((name, 'reads not shown', sorted(shared_r - r)))
        if shared_w - w:
            out.append((name, 'writes not shown', sorted(shared_w - w)))
        named = {n for a in d.acc for n in a[5]} | set(d.extra)
        if named - set(s.r) - set(s.w):
            out.append((name, 'shown but not declared in deps', sorted(named - set(s.r) - set(s.w))))
    for name in DETAIL:
        if name not in deps.STEPS:
            out.append((name, 'not a step'))
    return out


# -------------------------------------------------------------------------------------------- measurement
def build_flags(cfg=None):
    z = sizes(cfg)
    return [f'-DPAGES={z["pages"]}', f'-DFRAMES={z["frames"]}', f'-DPOOL_CHUNKS={z["pool_chunks"]}',
            f'-DRO_FIRST={z["ro_first"]}', f'-DFC_BASE={z["fc_base"]:#x}u', f'-DFC_LOW={z["fc_low"]}',
            f'-DFC_HIGH={z["fc_high"]}', f'-DCOMPRESS_LIMIT={z["compress_limit"]}',
            f'-DJOB_ENTRIES={z["job_entries"]}', f'-DCPL_ENTRIES={z["cpl_entries"]}', '-DFRAME_MASK=255']


def can_measure():
    return platform.system() == 'Darwin' and platform.machine() == 'arm64' and shutil.which('clang') is not None


def measure(cfg=None):
    """Build sim/kstep/measure.c and run it. Returns {'steps': {key: {'instr', 'note'}}, 'compiler', 'machine'}."""
    if not can_measure():
        raise RuntimeError('the instruction counter used here needs macOS on Apple silicon with clang')
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, 'measure')
        cmd = ['clang', '-O2', '-Wall', '-Wextra', '-Werror', '-I', SPEC, *build_flags(cfg), '-o', exe,
               os.path.join(KSTEP, 'measure.c')]
        subprocess.run(cmd, check=True)
        steps = json.loads(subprocess.run([exe], check=True, capture_output=True, text=True).stdout)
    ver = subprocess.run(['clang', '--version'], capture_output=True, text=True).stdout.splitlines()[0]
    return {'steps': {k: {'instr': round(v['instr']), 'raw': v['instr'], 'note': v['note']} for k, v in steps.items()},
            'compiler': ver, 'flags': '-O2', 'machine': platform.machine()}


def run_stats():
    """How far the clock hand and the bitmap search really go, from two plain runs of the host simulation."""
    from .machine import Machine
    out = {}
    for cfg, n in (('small', 20_000), ('full', 400_000)):
        m = Machine(cfg, seed=1)
        m.build_image()
        m.boot()
        m.run(n)
        k, b = m.kernel.st, m.bitmap.st
        out[cfg] = {'accesses': n, 'frames': m.cfg.frames, 'picks': k['clock_picks'], 'looked': k['clock_steps'],
                    'longest': k['clock_longest'], 'reserves': b['reserves'], 'words': b['words_scanned'],
                    'words_max': m.bitmap.scan_max}
    return out


# ------------------------------------------------------------------------------------------------- costs
def instr(step, M, case=None):
    """Measured instructions of a step, or None. The descriptor and the clock scan depend on the case."""
    d = LOCK.get(step) or DETAIL[step]
    key = d.key
    if key is None:
        return None
    if step == 'desc' and case and case.startswith('evict'):
        key = 'desc_compress'
    if step == 'pick_victim' and case == 'evict_ro':
        key = 'pick_victim.ro_first'
    return M['steps'][key]['instr']


def assumed_ns(step, w):
    """What ifsim.params assumes for the step, or None when it has no figure."""
    s = deps.STEPS.get(step)
    if s is None or s.unknown or not s.cost:
        return None
    return deps.cost(step, w)


def walk(case, M, w):
    """The steps of a case in order, each with its accesses, the lines that are new, and its cost."""
    seen, rows, sec = set(), [], deps.sections(case)
    red = deps.reduced(case)
    num = {s: i + 1 for i, s in enumerate(deps.nodes(case))}
    for step in deps.CASES[case]:
        d = LOCK.get(step) or DETAIL[step]
        new = again = dram = 0
        for table, mode, nbytes, index, temp, _ in d.acc:
            if temp == 'dram':
                new += 1
                dram += 1
            elif temp == 'line':
                key = (table, index)
                if key in seen:
                    again += 1
                else:
                    new += 1
                    seen.add(key)
            if (table, index) in SAME:
                seen.add((table, SAME[table, index]))
        n = instr(step, M, case)
        mmio = sum(1 for a in d.acc if a[4] == 'mmio')
        bulk = sum(BULK_LINES for a in d.acc if a[4] == 'bulk' and a[0] == 'frame')
        row = {'step': step, 'who': 'FW' if step in LOCK else deps.STEPS[step].who, 'basis': d.basis,
               'section': None if step in LOCK else sec.get(step), 'instr': n, 'new': new, 'again': again,
               'mmio': mmio, 'bulk': bulk, 'dram': dram, 'assumed': None if step in LOCK else assumed_ns(step, w),
               'n': num.get(step)}
        if n is not None:
            # a line the LZ4 HW has just written is never in the CPU's cache: it is in the low bound as well
            row['lo'] = round(n * MODEL['cpi'] + mmio * MODEL['mmio'] + dram * MODEL['miss'])
            row['hi'] = row['lo'] + (new - dram) * MODEL['miss']
        row['after'] = sorted(((num[a], a, v['kind'], v['via'], v['rule'].zh if v['rule'] else '')
                               for (a, b), v in red.items() if b == step), key=lambda x: x[0])
        rows.append(row)
    return rows


def totals(rows):
    """Sum of the steps the kernel runs with a measured count; and what is left as assumption or unknown."""
    k = [r for r in rows if r['instr'] is not None]
    return {'steps': len(k), 'instr': sum(r['instr'] for r in k), 'new': sum(r['new'] for r in k),
            'mmio': sum(r['mmio'] for r in k), 'dram': sum(r['dram'] for r in k),
            'lo': sum(r['lo'] for r in k), 'hi': sum(r['hi'] for r in k),
            'old_ns': sum(r['assumed'] or 0 for r in k),
            'assumed_ns': sum(r['assumed'] or 0 for r in rows if r['instr'] is None and r['who'] != 'HW'),
            'hw_ns': sum(r['assumed'] or 0 for r in rows if r['who'] == 'HW'),
            'open': [r['step'] for r in rows if r['instr'] is None and r['assumed'] is None
                     and r['basis'] in ('unknown', 'counted')]}


def per_page_lines():
    """Tables indexed by the page that one page fault touches: each is a line of its own today."""
    return [(n, TABLES[n][1]) for n in ('state', 'frame_of', 'fresh_n', 'pins', 'cot', 'pte')]

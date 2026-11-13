"""Dependencies between the steps of the kernel control procedures.

kernel.py says in which order the kernel does things. This file says why:
every step is listed once with what it reads and what it writes, and the
dependency graph of each case follows from those sets. Nothing here changes
the kernel.

    STEPS      one entry per step: who does it, what it reads and writes, where it is in kernel.py,
               what it puts into the step log, which timing parameters pay for it
    CASES      each case of the control procedure as the steps in the order kernel.py runs them,
               with 'lock' and 'unlock' where the lock is taken and dropped
    RULES      order that does not follow from the read and write sets, each with its reason
               and, where one exists, the mutant of conc.MUTANTS that shows what happens without it
    ATOMIC     steps that have to stay inside one critical section, and why

Three things are checked against execution, by the tests:
    the step log of a real occurrence of each case is the log the case predicts;
    every read and write of a kernel table and every port call made by a traced kernel sits at a
    statement that a step claims, and the union of what happened there equals what the steps declare;
    the lock time and the LZ4 engine time that the step costs add up to are the ones the timed model measured.

Names of what is read and written. With an index the thing exists per page, per frame or per chunk:
    [h]  this operation's own page      [f]  its own frame      [c]  its own chunks
    [*]  pages or frames of others, which only the scan of the reclaimer touches
Names without an index that are in PRIVATE are values only the running thread has: s is the state it read,
e the COT entry, cpl the completion, page the page its own decoder produced. A step that runs only because
of what such a value says reads that value, which is how a decision becomes an edge.
A '?' behind a name: declared, but the single-thread runs used for the check never get there.
"""
import ast
import heapq
import inspect
import sys
from collections import Counter, defaultdict, deque

from ifsim.params import Params

from . import kernel as kernel_mod
from .kernel import OutOfMemory
from .machine import Machine, Port

# what only the thread that runs the operation can see: locals, registers, wires of the LZ4 HW
PRIVATE = {'s', 'f', 'e', 'c', 'desc', 'cpl', 'irq', 'wake', 'regs', 'pc', 'page', 'victim'}
# one of each in the whole system
GLOBAL = ('free_frames', 'bitmap', 'pool_full', 'incompressible', 'hand', 'tlb', 'tag', 'job_ring', 'cpl_ring',
          'engine', 'strikes', 'lz4_off', 'reclaimer', 'frame_waiters')
# functions of kernel.py whose statements are steps; everything else in the file is a helper of one of them
BODY = ('page_fault', 'first_touch', 'fault_in', 'sw_decode', 'reclaim', 'pick_victim', 'evict_ro', 'evict_rw')


class Step:
    def __init__(self, who, label, zh, r='', w='', at=(), log=(), cost=(), unknown=False):
        self.who, self.label, self.zh = who, label, zh
        self.rare = {('R', x[:-1]) for x in r.split() if x.endswith('?')} | \
                    {('W', x[:-1]) for x in w.split() if x.endswith('?')}
        self.r = frozenset(x.rstrip('?') for x in r.split())
        self.w = frozenset(x.rstrip('?') for x in w.split())
        self.at, self.log, self.cost, self.unknown = tuple(at), tuple(log), tuple(cost), unknown


S = Step
STEPS = {
    # ---- the CPU, around the kernel
    'access': S('CPU', 'instruction touches page h', 'user SW 的一道指令碰到 page h，CPU MMU 查 PTE，發現不是 valid',
                r='pte[h] tlb', log=['access']),
    'exception': S('CPU', 'page fault exception', 'CPU 進入 page fault exception，存下現場，轉進 kernel',
                   w='regs', log=['page_fault'], cost=['fault_entry_ns']),
    'eret': S('CPU', 'return from exception', 'kernel 的處理結束，CPU 從 exception 返回',
              r='regs', w='pc', cost=['fault_exit_ns']),
    'rerun': S('CPU', 'instruction runs again', '同一道指令重跑一次，這次 PTE 是 valid',
               r='pc pte[h] frame[f] cache[f]', w='accessed[h]', log=['instruction_runs']),
    'kill': S('FW', 'end the user program', '沒有任何一份資料可用，kernel 結束這個 user SW', r='regs'),
    # ---- page fault, with the lock
    'check_state': S('FW', 'read state[h], any free frame?', '讀 state[h] 決定走哪一條路，並確認還有空的 frame',
                     r='state[h] free_frames', w='s',
                     at=[('page_fault', 's = self.state[h]'), ('page_fault', 'if not self.free_frames:')]),
    'wait_page': S('FW', 'wait for the job on page h', '這個 page 正有 job 在跑：睡到 job 結束',
                   w='waiters[h]?', at=[('page_fault', 'port.wait_page(h)')]),
    'wait_frame': S('FW', 'wait for a free frame', '沒有空的 frame：叫醒 reclaimer，睡到有 frame 還回來',
                    w='frame_waiters', at=[('page_fault', 'port.wait_frame()')]),
    'take_frame': S('FW', 'take a free frame', '從 free frame list 拿一個 frame，記下它屬於 page h',
                    r='free_frames', w='free_frames frame_of[h] owner[f] f',
                    at=[('page_fault', 'f = self.take_frame(h)')], log=['take_frame'], cost=['frame_alloc_ns']),
    'zero_frame': S('FW', 'fill frame with zeros', 'CPU 把整個 frame 寫成 0', r='f s', w='frame[f] cache[f]',
                    at=[('first_touch', 'self.port.zero_frame(pa)')], log=['zero_frame'], cost=['zero_fill_ns']),
    'cot_read': S('FW', 'read COT entry', '讀 page h 的 COT entry：哪幾個 chunk、stream 多長、CRC-32',
                  r='cot[h] s', w='e', at=[('fault_in', 'e = self.cot_read(h)')], log=['cot_read'], cost=['cot_read_ns']),
    'mark_decompressing': S('FW', 'state = DECOMPRESSING', 'state[h] 改成 DECOMPRESSING：從這裡起這個 page 屬於這個 job',
                            r='lz4_off', w='state[h]',
                            at=[('fault_in', 'use_hw = not self.lz4_off'), ('fault_in', 'self.set_state(h, DECOMPRESSING)')],
                            log=['state']),
    # page: on BAD_STREAM the answer was wrong only if the kernel's own decoder got the page out, so the verdict
    # of sw_decode is read. On BUS_ERROR and on OK it is not needed; the declaration is per step, not per status.
    'note_hw': S('FW', 'count HW strikes', '記錄 LZ4 HW 這次有沒有答對；連錯三次就停用', r='cpl page strikes lz4_off',
                 w='strikes lz4_off?', at=[('fault_in', 'self.note_hw('), ('evict_rw', 'self.note_hw(')]),
    'cot_clear': S('FW', 'clear COT entry', 'RW page：frame 現在是唯一的一份，先把 COT entry 清掉',
                   r='cpl', w='cot[h]', at=[('fault_in', 'self.cot_write(h, None)')], log=['cot_write'],
                   cost=['cot_write_ns']),
    'release_chunks': S('FW', 'give chunks back', 'RW page：把原本存放 stream 的 chunk 還給 bitmap',
                        r='cpl e', w='bitmap pool_full',
                        at=[('fault_in', 'self.bitmap.release(chunks)'), ('fault_in', 'self.pool_full = False')],
                        log=['bitmap_release'], cost=['bitmap_release_ns']),
    'set_present': S('FW', 'state = PRESENT', 'state[h] 改成 PRESENT', w='state[h]',
                     at=[('first_touch', 'self.set_state(h, PRESENT)'), ('fault_in', 'self.set_state(h, PRESENT)'),
                         ('evict_rw', 'self.set_state(h, PRESENT)')], log=['state']),
    'set_lost': S('FW', 'state = LOST', 'state[h] 改成 LOST', w='state[h]',
                  at=[('fault_in', 'self.set_state(h, LOST)')], log=['state']),
    'pte_map': S('FW', 'make PTE valid', '把 PTE 寫成 valid：從這裡起 user SW 碰得到這個 page', r='f',
                 w='pte[h] accessed[h]',
                 at=[('first_touch', 'self.port.pte_map(h, pa)'), ('fault_in', 'port.pte_map(h, pa)'),
                     ('evict_rw', 'port.pte_map(h, pa)')], log=['pte_map'], cost=['pte_write_ns']),
    'wake_page': S('FW', 'wake waiters of page h', '叫醒在等這個 page 的其他 thread', w='waiters[h]',
                   at=[('fault_in', 'port.wake_page(h)'), ('evict_rw', 'port.wake_page(h)')]),
    'note_fresh': S('FW', 'protect page from reclaimer', '把 page h 記進這個 thread 的 fresh 名單：指令重跑之前 reclaimer 不能拿走它',
                    r='fresh_n[h] fresh_n[*] s cpl page', w='fresh_n[h] fresh_n[*]',
                    at=[('page_fault', 'self.note_fresh(h)')]),
    'wake_check': S('FW', 'few frames left? wake reclaimer', 'free frame 低於 fc_low 就叫醒 reclaimer',
                    r='free_frames', w='reclaimer',
                    at=[('page_fault', 'if len(self.free_frames) <= cfg.fc_low:'), ('page_fault', 'port.wake_reclaimer()')]),
    # ---- one LZ4 job, without the lock
    'desc': S('FW', 'build job descriptor', '取一個新的 tag，組出 48 B 的 job descriptor', r='e c f tag', w='tag desc',
              at=[('fault_in', 'cpl = self.lz4_job('), ('evict_rw', 'cpl = self.lz4_job(')], log=['job'],
              cost=['desc_build_ns']),
    'submit': S('FW', 'write job ring, doorbell', '把 descriptor 寫進 job ring，寫 doorbell register', r='desc',
                w='job_ring', at=[('fault_in', 'cpl = self.lz4_job('), ('evict_rw', 'cpl = self.lz4_job(')],
                cost=['desc_write_ns', 'mmio_ns']),
    'hw_decompress': S('HW', 'DECOMPRESS chunks to frame', 'LZ4 HW 讀 chunk，核對 CRC-32，解壓縮寫進 frame，寫 completion',
                       r='job_ring chunk[c]', w='frame[f] cpl_ring irq engine', log=['decompress'],
                       cost=['hw_decompress']),
    'hw_fail': S('HW', 'DECOMPRESS fails', 'LZ4 HW 沒有把 page 交出來（這裡是 bus error），寫 completion',
                 r='job_ring chunk[c]', w='frame[f] cpl_ring irq engine', log=['bus_error'], cost=['hw_decompress']),
    'hw_compress': S('HW', 'COMPRESS frame to chunks', 'LZ4 HW 讀 frame，壓縮寫進 chunk，算 CRC-32，寫 completion',
                     r='job_ring frame[f]', w='chunk[c] cpl_ring irq engine', log=['compress'], cost=['hw_compress']),
    'notify': S('FW', 'interrupt, handler, wake thread', 'interrupt 進來，handler 讀 completion ring，叫醒在等的 thread',
                r='irq', w='wake', at=[('fault_in', 'cpl = self.lz4_job('), ('evict_rw', 'cpl = self.lz4_job(')],
                cost=['irq_latency_ns', 'irq_handler_ns', 'wakeup_ns']),
    'cpl_read': S('FW', 'read completion, check tag', '讀 16 B 的 completion，核對是自己那個 tag', r='cpl_ring wake',
                  w='cpl', at=[('fault_in', 'cpl = self.lz4_job('), ('evict_rw', 'cpl = self.lz4_job(')],
                  log=['completion'], cost=['cpl_read_ns']),
    'cache_invalidate': S('FW', 'cache invalidate frame', '把這個 frame 在所有 core 的 data 和 instruction cache line 丟掉',
                          r='f', w='cache[f]', at=[('fault_in', 'port.cache_invalidate(pa)')],
                          log=['cache_invalidate'], unknown=True),
    'sw_decode': S('FW', 'kernel decodes the stream', 'kernel 自己的 LZ4 decoder：CPU 讀 chunk，核對 CRC-32，解壓縮',
                   r='e cpl chunk[c]', w='page', at=[('sw_decode', 'page = self.decode_stored(')],
                   log=['sw_decode'], unknown=True),
    'frame_write': S('FW', 'CPU writes page into frame', 'CPU 把解出來的 page 寫進 frame', r='page f',
                     w='frame[f] cache[f]', at=[('sw_decode', 'self.port.frame_write(pa, page)')],
                     log=['frame_write'], unknown=True),
    'sw_clean': S('FW', 'cache clean frame', 'CPU 剛寫過這個 frame：把 dirty line 寫回 DRAM', r='f',
                  w='cache[f] frame[f]', at=[('sw_decode', 'self.port.cache_clean(pa)')], log=['cache_clean'],
                  unknown=True),
    # ---- the reclaimer
    'reclaim_check': S('FW', 'free frames < fc_high?', 'free frame 還不到 fc_high 就繼續找下一個 page', r='free_frames',
                       at=[('reclaim', 'while len(self.free_frames) < cfg.fc_high:')]),
    'pick_victim': S('FW', 'clock scan: pick a victim', 'clock 掃描：沿著 frame 找一個可以趕出去的 page，沿路清掉 accessed bit',
                     r='hand owner[*] state[*] pins[*] fresh_n[*] accessed[*] pool_full lz4_off incompressible',
                     w='hand accessed[*] victim', at=[('pick_victim', None)], log=['pick_victim'],
                     cost=['victim_pick_ns']),
    'reserve': S('FW', 'reserve 7 chunks', '先從 bitmap 保留最壞情況的 7 個 chunk', r='victim bitmap',
                 w='bitmap c pool_full?',
                 at=[('evict_rw', 'chunks = self.bitmap.reserve(self.need)'), ('evict_rw', 'self.pool_full = True')],
                 log=['bitmap_reserve'], cost=['bitmap_reserve_ns']),
    'find_frame': S('FW', 'look up frame of page h', '查出這個 page 現在在哪個 frame', r='victim frame_of[h]', w='f',
                    at=[('evict_rw', 'pa = cfg.frame_pa(self.frame_of[h])')]),
    'pte_clear': S('FW', 'make PTE invalid', '把 PTE 寫成 invalid', r='victim', w='pte[h]',
                   at=[('evict_ro', 'self.port.pte_unmap(h)'), ('evict_rw', 'port.pte_unmap(h)')], log=['pte_unmap'],
                   cost=['pte_write_ns']),
    'tlb_inval': S('FW', 'TLB invalidate, all cores', '把這一筆從所有 core 的 TLB 清掉', w='tlb',
                   at=[('evict_ro', 'self.port.pte_unmap(h)'), ('evict_rw', 'port.pte_unmap(h)')],
                   cost=['tlb_inval_ns']),
    'mark_compressing': S('FW', 'state = COMPRESSING', 'state[h] 改成 COMPRESSING：從這裡起這個 page 屬於這個 job',
                          w='state[h]', at=[('evict_rw', 'self.set_state(h, COMPRESSING)')], log=['state']),
    'cache_clean': S('FW', 'cache clean frame', '把這個 frame 在所有 core 的 dirty line 寫回 DRAM，LZ4 HW 才讀得到最新的內容',
                     r='f', w='cache[f] frame[f]', at=[('evict_rw', 'port.cache_clean(pa)')], log=['cache_clean'],
                     unknown=True),
    'cot_store': S('FW', 'write COT entry', '把 chunk 編號、stream 長度、CRC-32 寫進 COT entry', r='cpl c', w='cot[h]',
                   at=[('evict_rw', 'self.cot_write(h, {')], log=['cot_write'], cost=['cot_write_ns']),
    'trim': S('FW', 'give unused chunks back', '把沒用到的 chunk 還給 bitmap', r='cpl c', w='bitmap',
              at=[('evict_rw', "self.bitmap.release(chunks[used:], op='trim')")], log=['bitmap_trim'],
              cost=['bitmap_release_ns']),
    'release_all': S('FW', 'give all 7 chunks back', '壓不進 7 個 chunk，或 HW 失敗：7 個 chunk 全部還給 bitmap',
                     r='cpl c', w='bitmap',
                     at=[('evict_rw', 'self.bitmap.release(chunks)'), ('evict_rw', "self.bitmap.release(chunks, op='failed')")],
                     log=['bitmap_release'], cost=['bitmap_release_ns']),
    'mark_incompressible': S('FW', 'remember: incompressible', '記下這個 page 壓不小，之後不再選它', r='cpl',
                             w='incompressible', at=[('evict_rw', 'self.incompressible.add(h)')]),
    'put_frame': S('FW', 'frame back to free list', '把 frame 還回 free frame list，叫醒在等 frame 的 thread',
                   r='frame_of[h] free_frames', w='frame_of[h] owner[f] free_frames frame_waiters',
                   at=[('evict_ro', 'self.put_frame(h)'), ('evict_rw', 'self.put_frame(h)'),
                       ('fault_in', 'self.put_frame(h)')], log=['put_frame']),
    'set_compressed': S('FW', 'state = COMPRESSED', 'state[h] 改成 COMPRESSED', w='state[h]',
                        at=[('evict_ro', 'self.set_state(h, COMPRESSED)'), ('evict_rw', 'self.set_state(h, COMPRESSED)')],
                        log=['state']),
}
del S

_JOB = 'desc submit {hw} notify cpl_read'
_ENTER = 'access exception lock check_state take_frame '
_LEAVE = ' note_fresh wake_check unlock eret rerun'
_FAULT = _ENTER + 'cot_read mark_decompressing unlock ' + _JOB + ' cache_invalidate '
_EVICT_RW = ('lock reclaim_check pick_victim reserve find_frame pte_clear tlb_inval mark_compressing unlock cache_clean '
             + _JOB.format(hw='hw_compress') + ' lock note_hw ')
CASES = {name: tuple(text.split()) for name, text in {
    'first_touch': _ENTER + 'zero_frame set_present pte_map' + _LEAVE,
    'fault_ro': _FAULT.format(hw='hw_decompress') + 'lock note_hw set_present pte_map wake_page' + _LEAVE,
    'fault_rw': _FAULT.format(hw='hw_decompress') + 'lock note_hw cot_clear release_chunks set_present pte_map wake_page'
                + _LEAVE,
    'fault_rescue': _FAULT.format(hw='hw_fail') + 'sw_decode frame_write sw_clean lock note_hw cot_clear release_chunks '
                    'set_present pte_map wake_page' + _LEAVE,
    'fault_lost': _FAULT.format(hw='hw_decompress') + 'sw_decode lock note_hw put_frame set_lost wake_page unlock kill',
    'evict_ro': 'lock reclaim_check pick_victim pte_clear tlb_inval put_frame set_compressed unlock',
    'evict_rw': _EVICT_RW + 'cot_store trim put_frame set_compressed wake_page unlock',
    'evict_rw_incompressible': _EVICT_RW + 'release_all mark_incompressible set_present pte_map wake_page unlock',
}.items()}
CASE_ZH = {
    'first_touch': '第一次碰一個 RW page（沒有 LZ4 job）',
    'fault_ro': 'page fault，RO page，由 LZ4 HW 解壓縮',
    'fault_rw': 'page fault，RW page，由 LZ4 HW 解壓縮',
    'fault_rescue': 'page fault，LZ4 HW 沒交出 page，kernel 自己解回來（RW page）',
    'fault_lost': 'page fault，存放的 stream 壞了，page 遺失',
    'evict_ro': 'reclaimer 趕出一個 RO page（沒有 LZ4 job）',
    'evict_rw': 'reclaimer 趕出一個 RW page，由 LZ4 HW 壓縮',
    'evict_rw_incompressible': 'reclaimer 想趕出一個 RW page，但它壓不進 7 個 chunk',
}
DRAWN = ('first_touch', 'fault_rw', 'evict_ro', 'evict_rw')
ONLY_RW = ('cot_clear', 'release_chunks')                 # what fault_rw has and fault_ro has not


class Rule:
    def __init__(self, a, b, why, zh, witness=None, note=''):
        self.a, self.b, self.why, self.zh, self.witness, self.note = a, b, why, zh, witness, note


RULES = [
    Rule('access', 'exception', 'the CPU MMU finds the PTE not valid', 'CPU MMU 查到 PTE 不是 valid，才會有 exception'),
    Rule('exception', 'check_state', 'the kernel runs once the CPU has taken the exception',
         'CPU 進了 exception，kernel 的 handler 才開始跑'),
    Rule('reclaim_check', 'pick_victim', 'a victim is picked only while frames are short',
         'free frame 不夠，才會去找下一個 page'),
    Rule('sw_decode', 'set_present', 'PRESENT only after the page is back', 'page 真的解回來了，才能是 PRESENT',
         'no_sw_decode'),
    Rule('sw_decode', 'cot_clear', 'the stored copy is needed until the page is back in the frame',
         'page 回到 frame 之前，存放的那一份還要用，COT entry 和 chunk 都不能動'),
    Rule('sw_decode', 'set_lost', 'LOST only after the decoder of the kernel has failed as well',
         'LZ4 HW 和 kernel 自己的 decoder 都解不出來，才能判定 LOST', 'no_sw_decode'),
    Rule('sw_decode', 'put_frame', 'the frame is given up only when no decoder can fill it',
         '確定沒有 decoder 能把這個 frame 填好，才把它還掉'),
    Rule('zero_frame', 'pte_map', 'frame content before the PTE is valid', 'PTE 變成 valid 之前，frame 的內容要先就緒'),
    Rule('mark_decompressing', 'submit', 'page marked before the lock is dropped for the job',
         '放開 lock 去跑 job 之前，要先把 page 標成 DECOMPRESSING，否則另一個 thread 會對同一個 page 再開一個 job',
         'no_decompressing'),
    Rule('mark_compressing', 'submit', 'page marked before the lock is dropped for the job',
         '放開 lock 去跑 job 之前，要先把 page 標成 COMPRESSING，否則碰到這個 page 的 thread 不知道要等',
         'no_compressing'),
    Rule('cache_clean', 'submit', 'after the doorbell the LZ4 HW may read the frame at any moment',
         'doorbell 一寫，LZ4 HW 隨時會開始讀 frame，所以 cache clean 要在 submit 之前做完', 'no_cache_clean'),
    Rule('cpl_read', 'cache_invalidate', 'the kernel learns from the completion that the HW has stopped writing',
         'LZ4 HW 寫完 frame 之後才能丟 cache line；kernel 是從 completion 才知道 HW 寫完了',
         'no_cache_invalidate',
         '「需要這一步」有 mutant 見證。「要在 HW 寫完之後」這個順序沒有：模型裡先丟也過得了，'
         '因為模型沒有 prefetch 或其他 core 在 job 進行中把舊資料讀回 cache。這個順序來自 Linux arm64 的 '
         'arch_sync_dma_for_cpu，不是來自執行'),
    Rule('cache_invalidate', 'pte_map', 'no old cache line when user SW reaches the page',
         'user SW 碰得到這個 page 之前，cache 裡不能留著比 DRAM 舊的 line', 'no_cache_invalidate'),
    Rule('cache_invalidate', 'frame_write', 'old lines dropped before the CPU writes the frame itself',
         'kernel 自己寫 frame 之前，先把舊的 line 丟掉'),
    Rule('frame_write', 'sw_clean', 'what the CPU wrote must reach DRAM', 'CPU 寫進 cache 的內容要寫回 DRAM',
         'sw_decode_no_clean'),
    Rule('sw_clean', 'pte_map', 'frame content before the PTE is valid', 'PTE 變成 valid 之前，frame 的內容要先就緒',
         'sw_decode_no_clean'),
    Rule('cpl_read', 'set_present', 'PRESENT only after the kernel has seen how the job ended',
         'kernel 看過 job 的結果之後，page 才能是 PRESENT'),
    Rule('cpl_read', 'pte_map', 'PTE valid only after the kernel has seen how the job ended',
         'kernel 看過 job 的結果之後，PTE 才能是 valid'),
    Rule('cot_clear', 'release_chunks', 'entry first, so it never points at free chunks',
         '先清 COT entry 再還 chunk：entry 永遠不會指到已經還掉的 chunk',
         note='兩步在同一個 critical section 裡，別的 thread 看不到中間狀態。這個順序是為了當機後從 DRAM 看得懂，沒有 mutant'),
    Rule('set_present', 'wake_page', 'waiters wake up to read the new state', '等的 thread 醒來要讀到新的 state',
         'no_wake_page'),
    Rule('set_compressed', 'wake_page', 'waiters wake up to read the new state', '等的 thread 醒來要讀到新的 state',
         'no_wake_page'),
    Rule('set_lost', 'wake_page', 'waiters wake up to read the new state', '等的 thread 醒來要讀到新的 state',
         'no_wake_page'),
    Rule('pte_clear', 'tlb_inval', 'PTE first, then the TLBs', '先改 PTE，再清 TLB，否則 TLB 會從舊的 PTE 再填回來'),
    Rule('tlb_inval', 'put_frame', 'no core may reach the frame through an old TLB entry once another page owns it',
         'frame 交給別的 page 之前，任何 core 都不能再透過舊的 TLB entry 碰到它', 'local_tlb_flush'),
    Rule('tlb_inval', 'cache_clean', 'no core may write the frame after the clean',
         'cache clean 之後不能再有 core 寫這個 frame，所以要先讓所有 core 都碰不到它', 'local_tlb_flush'),
    Rule('cpl_read', 'put_frame', 'the frame is the only copy until the job has ended',
         'job 結束之前，frame 是唯一的一份'),
    Rule('cot_store', 'put_frame', 'frame freed only when the stored copy is complete and recorded',
         '壓縮好的那一份寫完而且記進 COT 之後，才能把 frame 還掉'),
    Rule('cpl_read', 'set_compressed', 'COMPRESSED only after the kernel has seen how the job ended',
         'kernel 看過 job 的結果之後，page 才能是 COMPRESSED'),
    Rule('note_fresh', 'eret', 'page protected before the thread leaves the kernel',
         'thread 離開 kernel 之前，page 要先受保護', 'protect_1',
         note='mutant 見證的是保護的 page 數不夠會怎樣，不是這個順序'),
]

ATOMIC = [
    (('check_state', 'take_frame', 'mark_decompressing'), 'test and set of state[h]',
     '讀 state[h]、拿 frame、把 state[h] 改成 DECOMPRESSING 要一氣呵成：兩個 thread 同時碰同一個 page，只有一個能開 job',
     'no_decompressing'),
    (('set_present', 'pte_map', 'note_fresh', 'wake_page'), 'page appears complete or not at all',
     'state 變成 PRESENT、PTE 變成 valid、記進 fresh 名單、叫醒等的 thread：reclaimer 的掃描要嘛全看到，要嘛全沒看到',
     'no_wake_page'),
    (('pick_victim', 'pte_clear', 'tlb_inval', 'mark_compressing'), 'victim leaves PRESENT in one step',
     '選中的 page 從 PRESENT 到 PTE invalid 到 COMPRESSING 中間不能有人插進來：否則會有 fault 看到 PRESENT 卻碰不到',
     'no_compressing'),
    (('pick_victim', 'pte_clear', 'tlb_inval', 'put_frame', 'set_compressed'), 'victim leaves PRESENT in one step',
     'RO page 同理：PTE invalid、frame 還回去、state 變成 COMPRESSED 在同一段裡', 'local_tlb_flush'),
    (('cot_store', 'trim', 'put_frame', 'set_compressed', 'wake_page'), 'stored copy recorded before anybody looks',
     'COT entry 寫好、frame 還掉、state 變成 COMPRESSED 在同一段裡：醒來的 fault 會立刻讀這個 COT entry', 'no_wake_page'),
    (('put_frame',), 'free list and its waiters', '還 frame 和叫醒等 frame 的 thread 在同一段裡', 'no_wake_frame'),
]


# ---------------------------------------------------------------- the graph
def nodes(case):
    return [s for s in CASES[case] if s not in ('lock', 'unlock')]


def sections(case):
    """step -> letter of the critical section it runs in, or None when the lock is not held."""
    out, cur, n = {}, None, 0
    for s in CASES[case]:
        if s == 'lock':
            cur, n = 'ABCD'[n], n + 1
        elif s == 'unlock':
            cur = None
        else:
            out[s] = cur
    return out


def base(x):
    return x.split('[')[0]


def conflict(x, y):
    """Two names are the same thing, or one of them is the scan that may meet any page or frame."""
    return x == y or (base(x) == base(y) and ('[*]' in (x[-3:], y[-3:])))


def edges(case):
    """(a, b) -> {'kind', 'via', 'rule'}: b has to come after a.
    data: a writes what b reads or writes, or a reads what b writes. rule: an entry of RULES.
    return: the thread leaves the kernel only when the procedure is finished."""
    ns = nodes(case)
    E = {}
    for j, b in enumerate(ns):
        for a in ns[:j]:
            A, B = STEPS[a], STEPS[b]
            via = sorted({x for x in A.w for y in B.r | B.w if conflict(x, y)} |
                         {x for x in A.r for y in B.w if conflict(x, y)})
            if via:
                E[a, b] = {'kind': 'data', 'via': via, 'rule': None}
    for r in RULES:
        if r.a in ns and r.b in ns:
            if ns.index(r.a) > ns.index(r.b):
                raise ValueError(f'{case}: rule {r.a} before {r.b} is not what the kernel does')
            E.setdefault((r.a, r.b), {'kind': 'rule', 'via': [], 'rule': None})['rule'] = r
    for last in ('eret', 'kill'):
        if last in ns:
            end = ns.index(last)
            busy = {a for a, b in E if ns.index(b) < end}      # has a later step inside the kernel
            for a in ns[:end]:
                if STEPS[a].who == 'FW' and a not in busy:
                    E.setdefault((a, last), {'kind': 'return', 'via': [], 'rule': None})   # a rule's reason stays
    return E


def reach(ns, E):
    succ = {n: [b for a, b in E if a == n] for n in ns}
    out = {}
    for n in reversed(ns):
        out[n] = set(succ[n]).union(*(out[b] for b in succ[n]))
    return out


def reduced(case):
    """The edges that are left when every edge implied by a longer way round is dropped."""
    ns, E = nodes(case), edges(case)
    R = reach(ns, E)
    return {(a, b): v for (a, b), v in E.items()
            if not any(b in R[c] for (a2, c) in E if a2 == a and c != b)}


def weights(results=None):
    """ns per cost name: the assumptions of ifsim.params, and the LZ4 HW job times the timed model measured."""
    w = {k: v for k, v in vars(Params()).items() if isinstance(v, int)}
    if results:
        w['hw_decompress'] = round(results['hw_job_ns']['DECOMPRESS']['mean'])
        w['hw_compress'] = round(results['hw_job_ns']['COMPRESS']['mean'])
    return w


def cost(step, w):
    return sum(w.get(c, 0) for c in STEPS[step].cost)


def schedule(case, w):
    """Earliest start and slack of every step if steps could run side by side wherever the graph allows.
    serial: the same steps one after the other, as the kernel runs them."""
    ns, E = nodes(case), edges(case)
    pred = defaultdict(list)
    for a, b in E:
        pred[b].append(a)
    est = {}
    for n in ns:
        est[n] = max((est[a] + cost(a, w) for a in pred[n]), default=0)
    span = max(est[n] + cost(n, w) for n in ns)
    lst = {}
    for n in reversed(ns):
        lst[n] = min((lst[b] for a, b in E if a == n), default=span) - cost(n, w)
    crit = [n for n in ns if lst[n] == est[n]]
    return {'est': est, 'slack': {n: lst[n] - est[n] for n in ns}, 'span': span, 'critical': crit,
            'serial': sum(cost(n, w) for n in ns), 'unknown': [n for n in ns if STEPS[n].unknown]}


def beside_hw(case):
    """Kernel steps that neither lead to the LZ4 HW job nor follow from it: they could run while the HW works."""
    ns, E = nodes(case), edges(case)
    R = reach(ns, E)
    hw = [n for n in ns if STEPS[n].who == 'HW']
    if not hw:
        return []
    return [n for n in ns if STEPS[n].who == 'FW' and n not in R[hw[0]] and hw[0] not in R[n]]


def layers(case):
    """Row of each step in the drawing: code order from top to bottom, and two neighbours share a row
    when neither needs the other and they run in the same critical section."""
    ns, E, sec = nodes(case), edges(case), sections(case)
    row, prev = {}, None
    for n in ns:
        r = max([row[a] + 1 for a, b in E if b == n] + [row[prev] if prev else 0])
        if prev and (sec[n] != sec[prev] or STEPS[n].who != STEPS[prev].who):
            r = max(r, row[prev] + 1)
        row[n], prev = r, n
    return row


# ------------------------------------------------- operations against each other
def touched(case):
    """name -> 'R', 'W' or 'RW' over all steps of the case, private values left out."""
    out = defaultdict(set)
    for n in nodes(case):
        for x in STEPS[n].r:
            out[x].add('R')
        for x in STEPS[n].w:
            out[x].add('W')
    return {x: ''.join(sorted(m)) for x, m in out.items() if base(x) not in PRIVATE}


def shared_between(a, b):
    """What two operations on different pages both touch, with at least one of them writing.
    Their own page, frame and chunks are different things, so only the global names and the scan are left."""
    A, B = touched(a), touched(b)
    out = {}
    for x, mx in A.items():
        for y, my in B.items():
            if base(x) != base(y) or 'W' not in mx + my:
                continue
            if '[' in x and '[*]' not in (x[-3:], y[-3:]):
                continue
            out[base(x) + ('[*]' if '[' in x else '')] = (mx, my)
    return out


def users_of(name):
    """case -> [(step, mode, section)] for one shared name."""
    out = {}
    for case in CASES:
        sec = sections(case)
        rows = [(n, ('R' if any(base(x) == name for x in STEPS[n].r) else '') +
                 ('W' if any(base(x) == name for x in STEPS[n].w) else ''), sec[n]) for n in nodes(case)]
        rows = [r for r in rows if r[1]]
        if rows:
            out[case] = rows
    return out


# --------------------------------------------------- several operations at once
def kind(case, step):
    """What a step keeps busy: 'cpu' exception entry and exit, 'lock' kernel with the lock, 'kernel' kernel
    without it, 'hw' the LZ4 engine, 'notify' the way back from the LZ4 HW to the sleeping thread."""
    s = STEPS[step]
    if s.who != 'FW':
        return {'CPU': 'cpu', 'HW': 'hw'}[s.who]
    return 'notify' if step == 'notify' else 'lock' if sections(case)[step] else 'kernel'


def overlap(ops, w):
    """Operations that run at the same time, each on a core of its own, under the assumed step costs.
    They share two things: the lock and the one LZ4 engine, both first come first served.
    ops: (label, case, start ns). Returns per operation its segments (kind, step, from, to) and its end;
    'wait_lock' and 'wait_engine' are the stretches where it stands still.
    This is arithmetic on the step costs for a picture, not the timed model; the timed model is ifsim."""
    todo = [deque(CASES[case]) for _, case, _ in ops]
    segs = [[] for _ in ops]
    end = [0] * len(ops)
    heap = [(t0, i) for i, (_, _, t0) in enumerate(ops)]
    heapq.heapify(heap)
    holder = {'lock': None, 'engine': None}
    queue = {'lock': deque(), 'engine': deque()}

    def take(res, i, t):
        if holder[res] is None:
            holder[res] = i
            return True
        queue[res].append((i, t))
        return False

    def give(res, t):
        holder[res] = None
        if queue[res]:
            j, since = queue[res].popleft()
            holder[res] = j
            if t > since:
                segs[j].append(('wait_' + res, None, since, t))
            heapq.heappush(heap, (t, j))

    while heap:
        t, i = heapq.heappop(heap)
        case = ops[i][1]
        while todo[i]:
            s = todo[i][0]
            if s == 'lock':
                todo[i].popleft()
                if not take('lock', i, t):
                    break
            elif s == 'unlock':
                todo[i].popleft()
                give('lock', t)
            elif s == '_engine_free':
                todo[i].popleft()
                give('engine', t)
            else:
                if STEPS[s].who == 'HW' and holder['engine'] != i:
                    if not take('engine', i, t):
                        todo[i][0] = s                    # stays first in line; runs when the engine is handed over
                        break
                todo[i].popleft()
                c = cost(s, w)
                if STEPS[s].who == 'HW':
                    todo[i].appendleft('_engine_free')
                if c:
                    segs[i].append((kind(case, s), s, t, t + c))
                    heapq.heappush(heap, (t + c, i))
                    break
        end[i] = max(end[i], t)
    return [{'label': ops[i][0], 'case': ops[i][1], 'start': ops[i][2], 'end': end[i], 'segs': segs[i]}
            for i in range(len(ops))]


# what the picture of three operations at once shows: an eviction, and two faults that arrive while it runs
SHOWN_TOGETHER = (('reclaimer: evict_rw', 'evict_rw', 0), ('core 1: fault_ro', 'fault_ro', 300),
                  ('core 2: fault_rw', 'fault_rw', 900))


# ---------------------------------------------------------------- capacity
COUNT_OF = {'first_touch': ('results', 'first'), 'fault_ro': ('results', 'fault_ro'), 'fault_rw': ('results', 'fault_rw'),
            'evict_ro': ('mm', 'ro_drops'), 'evict_rw': ('mm', 'rw_compress_ok'),
            'evict_rw_incompressible': ('mm', 'rw_incompressible')}


def demand(case, w):
    """ns of each thing that only one can use at a time, for one occurrence of the case."""
    ns, sec = nodes(case), sections(case)
    return {'lock': sum(cost(n, w) for n in ns if sec[n]),
            'engine': sum(cost(n, w) for n in ns if STEPS[n].who == 'HW'),
            'cpu': sum(cost(n, w) for n in ns if STEPS[n].who != 'HW' and n != 'notify')
            + (w['irq_handler_ns'] if 'notify' in ns else 0),
            'chain': sum(cost(n, w) for n in ns)}


def capacity(results):
    """Share of time each serial resource is busy in the baseline run of the timed model, from step costs
    times how often each case happened there, beside what that run measured. The LZ4 HW has `engines`
    engines; its share is the mean over them, which is also what the timed model reports."""
    w, t = weights(results), results['t_end_ns']
    engines = results.get('engines', 1)
    rows, use = [], Counter()
    for case, (a, b) in COUNT_OF.items():
        n, d = results[a][b], demand(case, w)
        rows.append(dict(d, case=case, n=n))
        use['lock'] += n * d['lock']
        use['engine'] += n * d['engine']
        if case.startswith('evict'):
            use['reclaimer'] += n * d['chain']
    faults = sum(results['results'][k] for k in ('first', 'fault_ro', 'fault_rw'))
    share = {k: v / (t * engines if k == 'engine' else t) for k, v in use.items()}
    return {'rows': rows, 'use_ns': dict(use), 'share': share, 't_end_ns': t, 'faults': faults, 'engines': engines,
            'faults_per_s': faults / t * 1e9, 'per_fault_ns': {k: v / faults for k, v in use.items()},
            'measured': {'lock': results['mm_lock']['busy_share'], 'engine': results['engine_util']},
            'lock_by_case': {r['case']: r['n'] * r['lock'] / use['lock'] for r in rows}}


# --------------------------------------------------- the step log of a real run
def log_of(case):
    """The step log one occurrence of the case leaves behind, as the names of its entries."""
    out = []
    for s in CASES[case]:
        out += [s] if s in ('lock', 'unlock') else list(STEPS[s].log)
    return out


def log_seen(events):
    return [what for _, what, _ in events if not what.startswith(('enter ', 'leave '))]


def occurrences():
    """case -> (the step log the case predicts, the step log of a real occurrence of it)."""
    from . import walk
    _, log = walk.capture()
    sc = walk.scenarios(log)
    real = {'first_touch': sc['first_touch'], 'fault_ro': sc['fault_ro'], 'fault_rw': sc['fault_rw'],
            'fault_rescue': walk.rescued_scenario(), 'fault_lost': walk.lost_scenario(),
            'evict_ro': sc['evict_ro'], 'evict_rw': sc['evict_rw_ok'],
            'evict_rw_incompressible': sc['evict_rw_incompressible']}
    out = {}
    for case, ev in real.items():
        want = log_of(case)
        if case.startswith('evict'):
            want = want[1:-1]                             # the lock is taken and dropped by reclaim(), around the victims
        out[case] = (want, log_seen(ev))
    return out


HOLD_COST = {'take_frame': ['frame_alloc_ns'], 'zero_frame': ['zero_fill_ns'], 'pte_map': ['pte_write_ns'],
             'cot_read': ['cot_read_ns'], 'cot_write': ['cot_write_ns'], 'bitmap_release': ['bitmap_release_ns'],
             'bitmap_trim': ['bitmap_release_ns'], 'bitmap_failed': ['bitmap_release_ns'],
             'bitmap_reserve': ['bitmap_reserve_ns'], 'pick_victim': ['victim_pick_ns'],
             'pte_unmap': ['pte_write_ns', 'tlb_inval_ns']}


class Holds:
    """Listens to the step log and keeps, for every stretch between lock and unlock: how many victims went
    out, how many frames the clock scan looked at, and the ns the logged steps cost under the assumed weights."""

    def __init__(self, w=None):
        self.w = w or weights()
        self.rows = []                                    # (ns, steps, evict_ro, evict_rw, frames looked at, reclaimer)
        self.cur, self.reclaim, self.scan_max = None, 0, 0
        self.picks = []                                   # frames looked at, one entry per pick

    def append(self, ev):
        _, what, v = ev
        if what == 'enter reclaim':
            self.reclaim += 1
        elif what == 'leave reclaim':
            self.reclaim -= 1
        elif what == 'lock':
            self.cur = [0, 0, 0, 0, 0, bool(self.reclaim)]
        elif what == 'unlock':
            self.rows.append(tuple(self.cur))
            self.cur = None
        elif self.cur is not None:
            c = self.cur
            c[0] += sum(self.w[k] for k in HOLD_COST.get(what, ()))
            c[1] += not what.startswith(('enter ', 'leave '))
            c[2] += what == 'enter evict_ro'
            c[3] += what == 'enter evict_rw'
            if what == 'pick_victim':
                c[4] += v['frames_looked_at']
                self.scan_max = max(self.scan_max, v['frames_looked_at'])
                self.picks.append(v['frames_looked_at'])

    def summary(self):
        def pct(xs, p):
            xs = sorted(xs)
            return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else 0
        at = self.picks.index(self.scan_max) if self.picks else 0
        out = {'scan_max': self.scan_max, 'scan_max_at': at + 1 if self.picks else 0,   # which pick, counted from 1
               'scan_rest_max': max(self.picks[:at] + self.picks[at + 1:], default=0)}
        for name, pick in (('fault', False), ('reclaim', True)):
            rows = [r for r in self.rows if r[5] == pick]
            ns, frames = [r[0] for r in rows], [r[4] for r in rows]
            out[name] = {'holds': len(rows), 'ns_mean': round(sum(ns) / max(1, len(ns))), 'ns_p50': pct(ns, .5),
                         'ns_p99': pct(ns, .99), 'ns_max': max(ns, default=0),
                         'steps_max': max((r[1] for r in rows), default=0),
                         'evict_ro_max': max((r[2] for r in rows), default=0),
                         'victims_max': max((r[2] + r[3] for r in rows), default=0),
                         'frames_p50': pct(frames, .5), 'frames_p99': pct(frames, .99),
                         'frames_max': max(frames, default=0),
                         'frames_total': sum(frames)}
        return out


def holds(cfg='small', n=20000, seed=1):
    m = Machine(cfg, seed=seed)
    m.build_image()
    m.boot()
    h = Holds()
    m.log.sink = h
    m.run(n)
    return dict(h.summary(), cfg=cfg, accesses=n, frames=m.cfg.frames, fc_low=m.cfg.fc_low, fc_high=m.cfg.fc_high,
                clock_picks=m.kernel.st['clock_picks'], clock_steps=m.kernel.st['clock_steps'])


# ------------------------------------------- what a running kernel really touches
def statements():
    """(function, first line, last line, text of the first line) of every statement of the BODY functions.
    Of a compound statement only the header counts; its body is made of statements of its own."""
    src = inspect.getsource(kernel_mod)
    lines = src.splitlines()
    out = []
    for fn in ast.walk(ast.parse(src)):
        if isinstance(fn, ast.FunctionDef) and fn.name in BODY:
            for st in ast.walk(fn):
                if isinstance(st, ast.stmt) and st is not fn:
                    body = getattr(st, 'body', None)
                    end = body[0].lineno - 1 if body else st.end_lineno
                    out.append((fn.name, st.lineno, end, lines[st.lineno - 1].split('  #')[0].strip()))
    return out


def anchors():
    """step -> the (function, line) of every statement it claims."""
    sts = statements()
    out = {}
    for name, s in STEPS.items():
        out[name] = {(fn, a) for want, frag in s.at for fn, a, _, text in sts
                     if fn == want and (frag is None or frag in text)}
    return out


class Trace:
    """Every read and write of a kernel table and every port call, with the statement of kernel.py it came from."""

    def __init__(self):
        self.on, self.port = False, None
        self.seen = defaultdict(set)                      # (function, statement line) -> {(mode, name)}
        self.lock = defaultdict(Counter)                  # name -> Counter of 'held', 'free'
        self.file, self.machine = kernel_mod.__file__, inspect.getsourcefile(Machine)
        self.span = {}
        for fn, a, b, _ in statements():
            for line in range(a, b + 1):
                if (fn, line) not in self.span or self.span[fn, line] < a:
                    self.span[fn, line] = a               # the innermost statement wins

    def hit(self, mode, name, idx=None, kind=None):
        if not self.on:
            return
        fr, helper = sys._getframe(1), None
        while fr is not None:
            co = fr.f_code
            if co.co_filename == self.file:
                if co.co_name in BODY:
                    break
                helper = helper or co.co_name
            elif co.co_filename == self.machine:
                return                                    # the machine looking at a table, not the kernel
            fr = fr.f_back
        else:
            return
        if helper == 'set_state' and mode == 'R':
            return                                        # the old state, read only to print it in the step log
        fn = fr.f_code.co_name
        if kind == 'page':
            name += '[*]' if fn == 'pick_victim' or fr.f_locals.get('h') != idx else '[h]'
        elif kind == 'frame':
            name += '[*]' if fn == 'pick_victim' else '[f]'
        elif kind == 'chunk':
            name += '[c]'
        self.seen[fn, self.span.get((fn, fr.f_lineno), fr.f_lineno)].add((mode, name))
        self.lock[name]['held' if self.port.locked else 'free'] += 1


class _Rec:
    """Stands in front of one kernel table and reports every read and write of it."""

    def __init__(self, inner, name, kind, t):
        self.__dict__.update(inner=inner, name=name, kind=kind, t=t)

    def __getitem__(self, i):
        self.t.hit('R', self.name, i, self.kind)
        return self.inner[i]

    def __setitem__(self, i, v):
        self.t.hit('W', self.name, i, self.kind)
        self.inner[i] = v

    def __len__(self):
        self.t.hit('R', self.name)
        return len(self.inner)

    def __bool__(self):
        self.t.hit('R', self.name)
        return bool(self.inner)

    def __contains__(self, x):
        self.t.hit('R', self.name)
        return x in self.inner

    def __iter__(self):
        return iter(self.inner)

    def pop(self, *a):
        self.t.hit('R', self.name)
        self.t.hit('W', self.name)
        return self.inner.pop(*a)

    def append(self, x):
        self.t.hit('W', self.name)
        self.inner.append(x)

    def add(self, x):
        self.t.hit('W', self.name)
        self.inner.add(x)

    def reserve(self, *a, **k):
        self.t.hit('R', self.name)
        self.t.hit('W', self.name)
        return self.inner.reserve(*a, **k)

    def release(self, *a, **k):
        self.t.hit('W', self.name)
        return self.inner.release(*a, **k)

    def __getattr__(self, a):
        return getattr(self.inner, a)

    def __setattr__(self, a, v):
        setattr(self.inner, a, v)


# what one port call reads and writes: (mode, name, kind of the first argument)
PORT_EFFECTS = {
    'cot_read': [('R', 'cot', 'page')], 'cot_write': [('W', 'cot', 'page')],
    'zero_frame': [('W', 'frame', 'frame'), ('W', 'cache', 'frame')],
    'frame_write': [('W', 'frame', 'frame'), ('W', 'cache', 'frame')],
    'frame_read': [('R', 'frame', 'frame')], 'chunk_read': [('R', 'chunk', 'chunk')],
    'cache_clean': [('W', 'cache', 'frame'), ('W', 'frame', 'frame')], 'cache_invalidate': [('W', 'cache', 'frame')],
    'pte_map': [('W', 'pte', 'page'), ('W', 'accessed', 'page')], 'pte_unmap': [('W', 'pte', 'page'), ('W', 'tlb', None)],
    'pte_test_clear_accessed': [('R', 'accessed', 'page'), ('W', 'accessed', 'page')],
    'lz4_job': [('W', 'job_ring', None), ('R', 'cpl_ring', None)],
    'wait_page': [('W', 'waiters', 'page')], 'wake_page': [('W', 'waiters', 'page')],
    'wait_frame': [('W', 'frame_waiters', None)], 'wake_frame': [('W', 'frame_waiters', None)],
    'wake_reclaimer': [('W', 'reclaimer', None)],
}
SCALARS = ('hand', 'tag', 'pool_full', 'strikes', 'lz4_off')
TABLES = (('state', 'page'), ('frame_of', 'page'), ('fresh_n', 'page'), ('pins', 'page'), ('owner', 'frame'),
          ('free_frames', None), ('incompressible', None), ('bitmap', None))


def traced(cfg='small', **kw):
    """A machine whose kernel and port report to a Trace. Tracing starts after boot."""
    t = Trace()

    def scalar(name):
        def get(self):
            t.hit('R', name)
            return self.__dict__['_' + name]

        def put(self, v):
            t.hit('W', name)
            self.__dict__['_' + name] = v
        return property(get, put)

    def call(name, effects):
        inner = getattr(Port, name)

        def run(self, *a, **k):
            for mode, res, kind in effects:
                t.hit(mode, res, a[0] if kind else None, kind)
            return inner(self, *a, **k)
        return run

    K = type('TracedKernel', (Machine.KERNEL,), {name: scalar(name) for name in SCALARS})
    P = type('TracedPort', (Port,), {name: call(name, eff) for name, eff in PORT_EFFECTS.items()})
    M = type('TracedMachine', (Machine,), {'KERNEL': K, 'PORT': P})
    m = M(cfg, **kw)
    m.build_image()
    m.boot()
    k = m.kernel
    for name, kind in TABLES:
        setattr(k, name, _Rec(getattr(k, name), name, kind, t))
    t.port, t.on = m.port, True
    return m, t


def trace_runs():
    """Three runs that between them reach every case: a plain one, one with damaged streams,
    one where the LZ4 HW fails until the kernel stops using it."""
    seen, lock = defaultdict(set), defaultdict(Counter)
    runs = []

    def keep(name, m, t):
        for k, v in t.seen.items():
            seen[k] |= v
        for k, v in t.lock.items():
            lock[k] += v
        runs.append({'name': name, 'accesses': m.accesses, 'results': dict(m.st)})

    m, t = traced(seed=1)
    m.run(20000)
    keep('plain', m, t)
    m, t = traced(seed=3, corrupt_every=200)
    m.run(8000)
    keep('damaged streams', m, t)
    m, t = traced(seed=1)
    m.run(6000)
    for _ in range(2):
        m.hw.inject('DECOMPRESS', 'bus_error')
        m.hw.inject('COMPRESS', 'bus_error')
    m.run(2000)
    for _ in range(4):
        m.hw.inject('DECOMPRESS', 'bus_error')
    try:
        m.run(2000)                                       # three strikes: from here RW pages stay in their frames
    except OutOfMemory:
        pass                                              # and sooner or later no frame can be freed (decision D14)
    keep('failing LZ4 HW', m, t)
    return seen, lock, runs


def groups():
    """Steps that claim the same statement cannot be told apart by the trace: they are compared together."""
    at = anchors()
    owner = {}
    for name, where in at.items():
        for w in where:
            owner.setdefault(w, []).append(name)
    parent = {n: n for n in at if at[n]}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for names in owner.values():
        for n in names[1:]:
            parent[find(n)] = find(names[0])
    out = defaultdict(list)
    for n in parent:
        out[find(n)].append(n)
    return [(sorted(g), set().union(*(at[n] for n in g))) for g in out.values()]


def compare(seen):
    """Declared against observed, per group of steps. Private values are not kernel tables and are left out."""
    rows, claimed = [], set()
    for names, where in sorted(groups()):
        declared = {(m, x) for n in names for m, xs in (('R', STEPS[n].r), ('W', STEPS[n].w)) for x in xs
                    if base(x) not in PRIVATE}
        rare = set().union(*(STEPS[n].rare for n in names))
        observed = set().union(*(seen.get(w, set()) for w in where))
        claimed |= where
        rows.append({'steps': names, 'where': sorted(where), 'declared': sorted(declared), 'observed': sorted(observed),
                     'undeclared': sorted(observed - declared), 'unseen': sorted(declared - observed - rare),
                     'rare_unseen': sorted((declared & rare) - observed)})
    stray = {k: sorted(v) for k, v in seen.items() if k not in claimed}
    return rows, stray


def measure(full_n=400000):
    """Everything that takes a run: the trace check and the lock holds. Kept in a JSON file beside the document."""
    seen, lock, runs = trace_runs()
    rows, stray = compare(seen)
    return {'trace': {'rows': rows, 'stray': {f'{k[0]}:{k[1]}': v for k, v in stray.items()},
                      'lock': {k: dict(v) for k, v in sorted(lock.items())}, 'runs': runs},
            'holds': [holds('small', 20000), holds('full', full_n)]}

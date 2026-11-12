"""Kernel control procedures of the SW-leaning design, as plain sequential code.

This file is the reference for the control procedure. It has no notion of
time and no knowledge of how a job reaches the LZ4 HW. Everything it needs from
the outside world is a call on `port`:

    port.lock() / port.unlock()        the one lock over every table below
    port.cot_read(h) / cot_write(h, b) the 32 B COT entry of page h, in DRAM
    port.zero_frame(pa)                fill one frame with zeros
    port.frame_write(pa, page)         copy one page into a frame (at boot, and by the kernel's own decoder)
    port.frame_read(pa)                read one frame through the kernel's own mapping (option `verify` only)
    port.chunk_read(c)                 read one 512 B chunk, never through a cache line that is older than DRAM
    port.pte_map(h, pa)                make the PTE of page h valid
    port.pte_unmap(h)                  make it invalid and flush it from every TLB
    port.pte_test_clear_accessed(h)    read and clear the accessed bit of the PTE
    port.lz4_job(desc)                 hand one 48 B descriptor to the LZ4 HW, wait, return the 16 B completion;
                                       None when the driver got no answer and has given up (timeout, reset, resend)
    port.cache_clean(pa)               write every dirty line of one frame from the CPU caches of every core back to DRAM
    port.cache_invalidate(pa)          drop every line of one frame from the data and instruction caches of every core
    port.cache_flush_layer()           once at boot: clean, then drop, every line of the frame area and the chunk pool
    port.wait_page(h) / wake_page(h)   sleep until the job on page h is finished
    port.wait_frame() / wake_frame()   sleep until a frame is free
    port.wake_reclaimer()              let the reclaimer thread run; the request is kept if it is running already
    port.may_wait()                    False in an ISR, with interrupts off, with another lock held, in an HRT thread
    port.thread()                      the thread this code runs in

Tables the kernel owns (nothing else reads or writes them):

    state[h]         one of the six page states
    frame_of[h]      frame number of a page that has one, else -1
    owner[f]         page that holds frame f, else -1
    free_frames      stack of free frame numbers
    bitmap           one bit per chunk of the pool
    incompressible   RW pages the LZ4 HW could not fit into 7 chunks
    fresh[t]         per thread, the pages of its most recent faults; the reclaimer leaves them alone
    fresh_n[h]       in how many of those lists page h is
    pins[h]          how many callers of pin_page hold page h in its frame
    strikes, lz4_off wrong answers of the LZ4 HW in a row; after three, or one job without an answer,
                     the HW is not used again until the next boot
    COT              in DRAM, 32 B per page; the LZ4 HW never reads it
"""
import functools
from array import array
from collections import Counter, OrderedDict, deque
from math import ceil
from zlib import crc32

from lz4sim.kernel import (S_UNTOUCHED as UNTOUCHED, S_COMPRESSED as COMPRESSED, S_PRESENT as PRESENT,
                           S_COMPRESSING as COMPRESSING, S_DECOMPRESSING as DECOMPRESSING, S_LOST as LOST, S_NAME)


class KernelBug(Exception):
    """Something the control procedure says cannot happen."""


class OutOfMemory(Exception):
    pass


class FaultNotAllowed(Exception):
    """A page that can be compressed was touched where nobody can wait for it. A bug in the code that touched it."""


def procedure(fn):
    """Mark a procedure of the spec: it is counted, and its entry and its result go to the step log."""
    @functools.wraps(fn)
    def run(self, *args):
        self.st[fn.__name__] += 1
        self.log('FW', 'enter ' + fn.__name__, **({'h': args[0]} if args else {}))
        result = fn(self, *args)
        self.log('FW', 'leave ' + fn.__name__, result=result)
        return result
    return run


class Kernel:
    STRIKES = 3

    def __init__(self, spec, cfg, port, bitmap, policy='clock', log=None, protect=1, decoder=None, verify=False):
        self.spec, self.cfg, self.port, self.bitmap = spec, cfg, port, bitmap
        self.policy = policy
        self.log = log or (lambda *a, **k: None)
        self.OP, self.ST, self.FL = spec.enum['opcode'], spec.enum['status'], spec.enum['flag']
        self.EMPTY = bytes(spec.size('cot_entry'))
        self.limit = cfg.compress_limit_for_rw()          # 3584: a stream longer than 7 chunks is not worth storing
        self.need = ceil(self.limit / cfg.chunk)          # chunks reserved for one COMPRESS
        self.state = bytearray(cfg.pages)
        self.frame_of = array('i', [-1]) * cfg.pages
        self.owner = array('i', [-1]) * cfg.frames
        self.free_frames = []
        self.incompressible = set()
        self.pool_full = False
        self.protect = protect                            # at least the pages one instruction can touch
        self.fresh = {}
        self.fresh_n = array('H', [0]) * cfg.pages
        self.pins = array('H', [0]) * cfg.pages
        self.hand = 0                                     # clock hand, a frame number
        self.lru = OrderedDict()                          # only for policy 'lru'
        self.tag = 0
        self.decoder = decoder                            # the kernel's own LZ4 decoder: (stream, size) -> page or None
        self.verify = verify                              # bring-up option: decode every stored stream and compare
        self.strikes = 0
        self.lz4_off = False
        self.st = Counter()

    # ------------------------------------------------------------------ boot
    @procedure
    def boot(self):
        """Run once. The boot loader has already put the RO chunks and the COT in DRAM."""
        cfg, port = self.cfg, self.port
        port.cache_flush_layer()                          # whatever the caches hold from before boot: start from DRAM
        used, top = 0, -1
        for h in range(cfg.pages):
            e = self.spec.unpack('cot_entry', port.cot_read(h))
            if e['flags'] & self.FL.VALID:                # every chunk a valid entry lists is taken
                for c in e['chunk'][:e['count']]:
                    self.bitmap.mark_used(c)
                    top = max(top, c)
                used += e['count']
            self.state[h] = COMPRESSED if cfg.is_ro(h) else UNTOUCHED
        self.bitmap.cursor = (top + 1) // 64              # the search for free chunks starts behind the RO image
        self.free_frames = list(range(cfg.frames - 1, -1, -1))
        return used

    def boot_load(self, h, page):
        """Boot loader hands over one initialised RW page (.data). It goes straight into a frame."""
        f = self.take_frame(h)
        self.port.frame_write(self.cfg.frame_pa(f), page)
        self.set_state(h, PRESENT)
        self.port.pte_map(h, self.cfg.frame_pa(f))
        self.note_present(h)

    # ------------------------------------------------------------ page fault
    @procedure
    def page_fault(self, h):
        """The CPU raised a page fault: user SW touched page h and its PTE is not valid."""
        port, cfg = self.port, self.cfg
        if not port.may_wait():                           # ISR, interrupts off, a lock held, or an HRT thread
            raise FaultNotAllowed(f'page {h:#x} was touched where a page fault cannot be served')
        port.lock()
        while True:
            s = self.state[h]
            if s == PRESENT:                              # another thread brought it in while this one waited
                self.note_fresh(h)                        # this thread's instruction needs it all the same
                port.unlock()
                return 'spurious'
            if s == LOST:                                 # no copy anywhere: the caller kills the user program
                port.unlock()
                return 'lost'
            if s in (COMPRESSING, DECOMPRESSING):         # a job on this very page is in flight
                port.wait_page(h)                         # sleeps without the lock, returns with it
                continue
            if not self.free_frames:
                port.wake_reclaimer()                     # it may be asleep
                port.wait_frame()                         # sleeps without the lock, returns with it
                continue
            break
        f = self.take_frame(h)
        if s == UNTOUCHED:
            result = self.first_touch(h, f)
        else:
            result = self.fault_in(h, f)
        if result != 'lost':
            self.note_fresh(h)                            # must survive until the CPU has run the instruction
        if len(self.free_frames) <= cfg.fc_low:
            port.wake_reclaimer()
        port.unlock()
        return result                                     # the CPU now runs the faulting instruction again

    def first_touch(self, h, f):
        """An RW page nobody has written yet: it reads as zeros. No LZ4 HW job."""
        pa = self.cfg.frame_pa(f)
        self.port.zero_frame(pa)
        self.set_state(h, PRESENT)
        self.port.pte_map(h, pa)
        self.note_present(h)
        return 'first_touch'

    def fault_in(self, h, f):
        """A compressed page: one DECOMPRESS job from its chunks into frame f. If the LZ4 HW does not
        deliver the page, the kernel decodes the stored stream itself. The page is lost only if that fails too."""
        port, cfg = self.port, self.cfg
        pa = cfg.frame_pa(f)
        e = self.cot_read(h)
        if not e['flags'] & self.FL.VALID:
            raise KernelBug(f'page {h:#x} is compressed but its COT entry is not valid')
        chunks = e['chunk'][:e['count']]
        use_hw = not self.lz4_off                         # read with the lock, used after it
        self.set_state(h, DECOMPRESSING)                  # from here the page belongs to this job
        port.unlock()
        status = None                                     # no answer from the HW, or the HW is not used
        if use_hw:
            cpl = self.lz4_job(opcode=self.OP.DECOMPRESS, count=e['count'], limit=cfg.page, frame_pa=pa,
                               comp_len=e['comp_len'], flags=e['flags'] & self.FL.RAW, checksum=e['checksum'],
                               chunk=chunks)
            status = None if cpl is None else cpl['status']
        port.cache_invalidate(pa)                         # the HW wrote DRAM, or the kernel is about to write the
        #                                                   frame itself: no older line of this frame may survive
        if status not in (None, self.ST.OK, self.ST.BAD_STREAM, self.ST.BUS_ERROR):
            raise KernelBug(f'DECOMPRESS of page {h:#x} ended with status {status}, aux {cpl["aux"]}')
        ok = status == self.ST.OK or self.sw_decode(h, e, chunks, pa)
        port.lock()
        if use_hw:                                        # BAD_STREAM on a stream the kernel could decode: the HW was wrong
            self.note_hw(status, wrong=status == self.ST.BUS_ERROR or (ok and status == self.ST.BAD_STREAM))
        if not ok:                                        # the stored stream is damaged: the page is gone
            self.put_frame(h)
            self.set_state(h, LOST)
            port.wake_page(h)
            return 'lost'
        if not cfg.is_ro(h):                              # RW: the frame is now the only copy
            self.cot_write(h, None)                       # entry first, so it never points at free chunks
            self.bitmap.release(chunks)
            self.pool_full = False
        self.set_state(h, PRESENT)
        port.pte_map(h, pa)                               # last step: from here user SW reaches the page
        self.note_present(h)
        port.wake_page(h)
        return 'fault_ro' if cfg.is_ro(h) else 'fault_rw'

    def sw_decode(self, h, e, chunks, pa):
        """The second opinion: the kernel's own LZ4 decoder, run by the CPU, from the stored stream into the frame.
        Called without the lock. The page is DECOMPRESSING, so its chunks and its frame belong to this thread."""
        page = self.decode_stored(chunks, e['comp_len'], e['checksum'], e['flags'])
        self.st['sw_decode'] += 1
        self.st['sw_decode_ok'] += page is not None
        self.log('FW', 'sw_decode', h=h, read_chunks=chunks, stream_len=e['comp_len'], expected_crc=e['checksum'],
                 result='decoded' if page is not None else 'failed')
        if page is not None:
            self.port.frame_write(pa, page)
            self.log('FW', 'frame_write', frame_pa=pa)
            self.port.cache_clean(pa)                     # the CPU wrote it: code is run from DRAM, and the frame may
                                                          # be handed to the LZ4 HW later without another clean
        return page is not None

    def decode_stored(self, chunks, length, checksum, flags):
        """Stored stream to page by the CPU: read the chunks, check the CRC-32, decode. None if either fails."""
        cfg = self.cfg
        used = chunks[:ceil(length / cfg.chunk)]
        stream = b''.join(self.port.chunk_read(c) for c in used)[:length]
        if crc32(stream) != checksum:
            return None
        page = stream if flags & self.FL.RAW else self.decoder(stream, cfg.page)
        return page if page is not None and len(page) == cfg.page else None

    # --------------------------------------------------------------- reclaim
    @procedure
    def reclaim(self):
        """Body of the reclaimer thread for one wake-up: free frames until fc_high are free."""
        port, cfg = self.port, self.cfg
        port.lock()
        freed = 0
        while len(self.free_frames) < cfg.fc_high:
            h = self.pick_victim()
            if h is None:                                 # nothing left that may go
                self.st['reclaim_stuck'] += 1
                break
            if cfg.is_ro(h):
                freed += self.evict_ro(h)
            else:
                freed += self.evict_rw(h)
        port.unlock()
        return freed

    def pick_victim(self):
        """Next page to push out of its frame, or None. RO pages can always go. An RW page
        can go unless it is known incompressible, the chunk pool has no room, or the LZ4 HW is no longer used."""
        if self.policy == 'lru':                          # the ideal, for comparison only
            return self.pick_victim_lru()
        cfg = self.cfg
        for step in range(2 * cfg.frames):                # one lap clears accessed bits, the next finds a page
            f = self.hand
            self.hand = (f + 1) % cfg.frames
            h = self.owner[f]
            if h < 0 or self.state[h] != PRESENT:         # free frame, or a job is using it
                continue
            if self.pins[h] or self.fresh_n[h]:           # held by pin_page, or just faulted in and not used yet
                continue
            if not cfg.is_ro(h) and (self.pool_full or self.lz4_off or h in self.incompressible):
                continue
            if self.port.pte_test_clear_accessed(h):      # touched since the hand last passed: second chance
                continue
            self.note_pick(h, f, step + 1)
            return h
        return None

    def note_pick(self, h, f, looked_at):
        self.st['clock_steps'] += looked_at
        self.st['clock_picks'] += 1
        self.st['clock_longest'] = max(self.st['clock_longest'], looked_at)
        self.log('FW', 'pick_victim', h=h, frame_pa=self.cfg.frame_pa(f), frames_looked_at=looked_at)

    @procedure
    def evict_ro(self, h):
        """RO page: its compressed copy never left the pool, so the frame is simply dropped."""
        self.port.pte_unmap(h)
        self.note_gone(h)
        self.put_frame(h)
        self.set_state(h, COMPRESSED)
        return 1

    @procedure
    def evict_rw(self, h):
        """RW page: one COMPRESS job from its frame into freshly reserved chunks."""
        port, cfg = self.port, self.cfg
        chunks = self.bitmap.reserve(self.need)           # worst case up front; the unused ones go back below
        if chunks is None:
            self.pool_full = True                         # RW pages are skipped until chunks come back
            self.st['pool_full'] += 1
            return 0
        pa = cfg.frame_pa(self.frame_of[h])
        port.pte_unmap(h)                                 # before the job: nobody can write the frame while the HW reads it
        self.note_gone(h)
        self.set_state(h, COMPRESSING)                    # from here the page belongs to this job
        port.unlock()
        port.cache_clean(pa)                              # what the CPU wrote must be in DRAM before the HW reads it
        cpl = self.lz4_job(opcode=self.OP.COMPRESS, count=len(chunks), limit=self.limit, frame_pa=pa, chunk=chunks)
        status = None if cpl is None else cpl['status']
        stored = status == self.ST.OK
        if stored and self.verify:                        # bring-up option: decode what was stored and compare
            stored = self.stored_right(cpl, chunks, pa)
        port.lock()
        self.note_hw(status, wrong=not stored and status != self.ST.INCOMPRESSIBLE)
        if stored:
            used = ceil(cpl['length'] / cfg.chunk)
            self.cot_write(h, {'flags': self.FL.VALID | (cpl['flags'] & self.FL.RAW), 'count': used,
                               'comp_len': cpl['length'], 'checksum': cpl['checksum'], 'chunk': chunks[:used]})
            if used < len(chunks):
                self.bitmap.release(chunks[used:], op='trim')
            self.put_frame(h)                             # only now: the stored copy is complete and recorded
            self.set_state(h, COMPRESSED)
            freed = 1
        elif status == self.ST.INCOMPRESSIBLE:            # keep the page where it is and do not try it again
            self.bitmap.release(chunks)
            self.incompressible.add(h)
            self.set_state(h, PRESENT)
            port.pte_map(h, pa)
            self.note_present(h)
            freed = 0
        elif status in (None, self.ST.OK, self.ST.BUS_ERROR):   # the HW failed, not the page: keep it, do not mark it
            self.bitmap.release(chunks, op='failed')      # whatever the HW wrote there is never looked at
            self.st['compress_failed'] += 1
            self.set_state(h, PRESENT)
            port.pte_map(h, pa)                           # the frame was only read: it still holds the page
            self.note_present(h)
            freed = 0
        else:
            raise KernelBug(f'COMPRESS of page {h:#x} ended with status {status}, aux {cpl["aux"]}')
        port.wake_page(h)
        return freed

    def stored_right(self, cpl, chunks, pa):
        """Option `verify`, for bring-up: read back what the LZ4 HW just stored, decode it with the kernel's own
        decoder and compare it with the frame. Called without the lock; the page is COMPRESSING."""
        page = self.decode_stored(chunks, cpl['length'], cpl['checksum'], cpl['flags'])
        right = page is not None and page == self.port.frame_read(pa)
        self.st['verified'] += 1
        self.st['verify_failed'] += not right
        return right

    # ------------------------------------------------------------ pin, unpin
    @procedure
    def pin_page(self, h):
        """Somebody is about to reach page h in a way the CPU MMU cannot stop or a page fault cannot serve:
        from an ISR, through the kernel's own mapping of the frame, or by giving the frame to another bus
        master. The page is brought into a frame and stays there until unpin_page. The caller may wait here."""
        port = self.port
        while True:
            port.lock()
            if self.state[h] == PRESENT:
                self.pins[h] += 1                         # the reclaimer skips it from now on
                port.unlock()
                return 'pinned'
            port.unlock()
            if self.page_fault(h) == 'lost':
                return 'lost'

    @procedure
    def unpin_page(self, h):
        port = self.port
        port.lock()
        if not self.pins[h]:
            raise KernelBug(f'page {h:#x} is not pinned')
        self.pins[h] -= 1
        if not self.pins[h] and len(self.free_frames) <= self.cfg.fc_low:
            port.wake_reclaimer()                         # one more page it may take
        port.unlock()

    # --------------------------------------------------------- small helpers
    def lz4_job(self, **fields):
        """Build one descriptor, give it to the LZ4 HW, wait, return the completion as a dict.
        None when the driver got no answer and has given up."""
        self.tag = tag = (self.tag + 1) & 0xFFFFFFFF or 1  # one step: other threads come through here too
        desc = self.spec.pack('job_desc', dict(fields, tag=tag))
        self.log('FW', 'job', desc=desc, **dict(fields, tag=tag))
        raw = self.port.lz4_job(desc)
        if raw is None:
            self.log('FW', 'no_completion', tag=tag)
            return None
        cpl = self.spec.unpack('completion', raw)
        self.log('FW', 'completion', cpl=raw, **cpl)
        if cpl['tag'] != tag:                             # compared with this job's own tag, not with the newest one
            raise KernelBug(f'completion tag {cpl["tag"]:#x}, expected {tag:#x}')
        return cpl

    def note_hw(self, status, wrong):
        """After every job, with the lock held. status None: no answer, the driver has given up.
        wrong: the HW answered and the answer was not right. Three of those in a row, or one job
        without an answer, and the LZ4 HW is not used again until the next boot."""
        if status is None:
            self.strikes = self.STRIKES
        elif wrong:
            self.strikes += 1
        else:
            self.strikes = 0
        if self.strikes >= self.STRIKES and not self.lz4_off:
            self.lz4_off = True                           # stored pages come back through sw_decode, RW pages stay in frames
            self.st['lz4_off'] += 1
            self.log('FW', 'lz4_off')

    def cot_read(self, h):
        raw = self.port.cot_read(h)
        e = self.spec.unpack('cot_entry', raw)
        self.log('FW', 'cot_read', h=h, entry=raw, count=e['count'], comp_len=e['comp_len'],
                 checksum=e['checksum'], chunk=e['chunk'][:e['count']])
        return e

    def cot_write(self, h, entry):
        raw = self.spec.pack('cot_entry', entry) if entry else self.EMPTY
        self.port.cot_write(h, raw)
        self.log('FW', 'cot_write', h=h, entry=raw, valid=int(bool(entry)))

    def take_frame(self, h):
        f = self.free_frames.pop()
        self.frame_of[h] = f
        self.owner[f] = h
        self.log('FW', 'take_frame', h=h, frame_pa=self.cfg.frame_pa(f), free_frames=len(self.free_frames))
        return f

    def put_frame(self, h):
        f = self.frame_of[h]
        self.frame_of[h] = -1
        self.owner[f] = -1
        self.free_frames.append(f)
        self.log('FW', 'put_frame', h=h, frame_pa=self.cfg.frame_pa(f), free_frames=len(self.free_frames))
        self.port.wake_frame()                            # a fault may be waiting for exactly this

    def note_fresh(self, h):
        """Page h came in for the instruction this thread is stuck on. It and the pages of the thread's
        faults just before it stay in their frames, because one instruction can need several pages at once."""
        mine = self.fresh.setdefault(self.port.thread(), deque())
        mine.append(h)
        self.fresh_n[h] += 1
        if len(mine) > self.protect:
            self.fresh_n[mine.popleft()] -= 1

    def thread_gone(self, t):
        """A thread ended: its pages are ordinary pages again. Called with the lock held."""
        for h in self.fresh.pop(t, ()):
            self.fresh_n[h] -= 1
        if len(self.free_frames) <= self.cfg.fc_low:
            self.port.wake_reclaimer()                    # pages it may take now

    def set_state(self, h, s):
        self.log('FW', 'state', h=h, old=S_NAME[self.state[h]], new=S_NAME[s])
        self.state[h] = s

    # ---------------------------------- the ideal policy, for comparison only
    # Exact LRU needs to know about every access. A kernel only hears about
    # faults, so this cannot be built; it shows how far the clock is from ideal.
    def note_present(self, h):
        self.lru[h] = None

    def note_gone(self, h):
        self.lru.pop(h, None)

    def oracle_touch(self, h):
        self.lru.move_to_end(h)

    def pick_victim_lru(self):
        cfg = self.cfg
        for h in self.lru:
            if self.pins[h] or self.fresh_n[h]:
                continue
            if cfg.is_ro(h) or not (self.pool_full or self.lz4_off or h in self.incompressible):
                return h
        return None

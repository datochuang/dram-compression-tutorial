"""FW page manager: page states, the fault path, the background reclaimer.

Owns the COT, the chunk bitmap, the frame list and the PTEs. It reaches the
LZ4 HW only through Driver.submit and shared memory only through Platform.

One lock (mm_lock) covers page state, frames, bitmap and COT. It is dropped
while a job is in flight; the page is then in state compressing or
decompressing and other threads wait on its event.

`mut` holds deliberate bugs for the checker tests: {name: ordinal of the job}.
"""
from collections import Counter, defaultdict
from itertools import islice
from math import ceil

from lz4sim.kernel import (S_COMPRESSED, S_PRESENT, S_UNTOUCHED, S_COMPRESSING,
                           S_DECOMPRESSING, S_LOST, S_NAME)

from .des import Resource, Signal
from .platform import Ctx

PARTS = ('cpu', 'lock', 'frame', 'inflight', 'submit', 'queue', 'hw', 'notify')


class PageManager:
    def __init__(self, sim, spec, cfg, p, plat, mon, drv, boot):
        """boot: what the boot loader left behind (state, frame_of, lru, free_frames, bitmap)."""
        self.sim, self.spec, self.cfg, self.p = sim, spec, cfg, p
        self.plat, self.mon, self.drv = plat, mon, drv
        self.state = boot.state
        self.frame_of = boot.frame_of
        self.lru = boot.lru
        self.free_frames = boot.free_frames
        self.bitmap = boot.bitmap
        self.mapped = bytearray(cfg.pages)          # the PTE valid bit of every page
        for h in self.lru:
            self.mapped[h] = 1
        self.lock = Resource(sim, 'mm_lock')
        self.busy = {}                              # page -> event fired when its job is finished
        self.frame_sig = Signal(sim)                # a frame was freed
        self.reclaim_sig = Signal(sim)              # free frames are low
        self.cdone_sig = Signal(sim)                # a background COMPRESS finished
        self.inflight = 0                           # background COMPRESS jobs outstanding
        self.rctx = Ctx(sim, 'reclaim')
        self.incompressible = set()
        self.pool_full = False
        self.jobs = 0
        self.st = Counter()
        self.lat = defaultdict(list)                # kind -> fault latencies, ns
        self.parts = defaultdict(Counter)           # kind -> where that time went
        self.worst = {}                             # kind -> (ns, parts) of the slowest fault
        self.part_max = defaultdict(Counter)        # kind -> the longest each stage ever took in one fault
        self.min_free = len(self.free_frames)
        self.peak_pool = 0
        self.mut = {}
        self.OP = spec.enum['opcode']
        self.ST = spec.enum['status']
        self.FL = spec.enum['flag']
        self.EMPTY = bytes(spec.size('cot_entry'))
        self.limit = cfg.compress_limit_for_rw()
        self.need = ceil(self.limit / cfg.chunk)
        sim.process(self._reclaimer(), 'reclaim')

    def _m(self, name):
        n = self.mut.get(name)
        if n is None or self.jobs < n:
            return False
        del self.mut[name]
        return True

    def emit_boot(self):
        """Tell the monitor which PTEs the boot loader made valid."""
        for h in self.lru:
            self.mon.emit('fw', 'pte', h=h, valid=1, pa=self.cfg.frame_pa(self.frame_of[h]), boot=1)

    # ---- small steps
    def _set(self, h, s):
        self.state[h] = s
        self.mon.emit('fw', 'state', h=h, s=S_NAME[s])

    def _pte(self, ctx, h, valid):
        """Write one PTE. Invalid includes the TLB invalidate; the page is out of reach when this returns."""
        p = self.p
        yield ctx.cpu(p.pte_write_ns if valid else p.pte_write_ns + p.tlb_inval_ns)
        self.mapped[h] = int(valid)
        self.mon.emit('fw', 'pte', h=h, valid=int(valid), pa=self.cfg.frame_pa(self.frame_of[h]))

    def _take_frame(self, h):
        self.frame_of[h] = self.free_frames.pop()
        n = len(self.free_frames)
        if n < self.min_free:
            self.min_free = n
        if n <= self.cfg.fc_low:
            self.reclaim_sig.fire()

    def _free_frame(self, h):
        self.free_frames.append(self.frame_of[h])
        self.frame_of[h] = -1
        self.frame_sig.fire()

    def _note_pool(self):
        used = self.cfg.pool_chunks - self.bitmap.free
        if used > self.peak_pool:
            self.peak_pool = used

    # ---- the access path, called in the context of a user thread
    def access(self, ctx, h, write):
        """One page access by user SW. Returns 'hit' or how the page fault ended."""
        if self.mapped[h]:                           # PTE valid: the CPU MMU translates, no FW involved
            self.lru.move_to_end(h)
            return 'hit'
        sim, p, cfg, plat = self.sim, self.p, self.cfg, self.plat
        t0 = sim.now
        part = Counter()
        kind = None
        yield ctx.cpu(p.fault_entry_ns)
        while True:
            part['lock'] += yield self.lock.acquire()
            s = self.state[h]
            if s == S_PRESENT:                       # another thread, or a finished job, already mapped it
                self.lock.release()
                kind = 'inflight' if part['inflight'] else 'spurious'
                break
            if s == S_LOST:
                self.lock.release()
                kind = 'lost'
                break
            if s in (S_COMPRESSING, S_DECOMPRESSING):
                ev = self.busy[h]
                self.lock.release()
                if s == S_COMPRESSING:
                    self.st['fault_during_compress'] += 1
                t = sim.now
                yield from ctx.block(ev)
                part['inflight'] += sim.now - t
                continue
            if not self.free_frames:
                self.lock.release()
                self.st['frame_waits'] += 1
                self.reclaim_sig.fire()
                t = sim.now
                yield from ctx.block(self.frame_sig.wait())
                part['frame'] += sim.now - t
                continue
            self._take_frame(h)
            yield ctx.cpu(p.frame_alloc_ns)
            fpa = cfg.frame_pa(self.frame_of[h])
            if s == S_UNTOUCHED:                     # first touch: a zero page, no HW job
                yield from plat.mem_write(ctx, fpa, bytes(cfg.page), p.zero_fill_ns, 'zero_fill')
                self._set(h, S_PRESENT)
                yield from self._pte(ctx, h, True)
                self.lru[h] = None
                self.lock.release()
                kind = 'first'
                break
            # compressed: read the COT entry, DECOMPRESS into the new frame
            ro = cfg.is_ro(h)
            raw = yield from plat.mem_read(ctx, cfg.entry_pa(h), len(self.EMPTY), p.cot_read_ns, 'cot')
            e = self.spec.unpack('cot_entry', raw)
            if not e['flags'] & self.FL.VALID:
                raise RuntimeError(f'page {h:#x} is compressed but its COT entry is not valid')
            self._set(h, S_DECOMPRESSING)
            self.busy[h] = sim.event()
            self.lock.release()
            self.jobs += 1
            yield ctx.cpu(p.desc_build_ns)
            chunks = e['chunk'][:e['count']]
            desc = {'opcode': self.OP.DECOMPRESS, 'count': e['count'], 'limit': cfg.page, 'frame_pa': fpa,
                    'comp_len': e['comp_len'], 'flags': e['flags'] & self.FL.RAW,
                    'checksum': e['checksum'], 'chunk': chunks}
            if self._m('decomp_wrong'):
                desc['checksum'] ^= 1
            if self._m('pte_early'):
                self.drv.after_bell = lambda job: self.mon.emit('fw', 'pte', h=h, valid=1, pa=fpa)
            cpl, tm = yield from self.drv.submit(ctx, desc, h)
            part.update(tm)
            part['lock'] += yield self.lock.acquire()
            if cpl['status'] == self.ST.OK:
                if not ro:                           # the frame is now the only copy: drop the stored one
                    if not self._m('cot_keep'):
                        yield from plat.mem_write(ctx, cfg.entry_pa(h), self.EMPTY, p.cot_write_ns, 'cot')
                    self.bitmap.release(chunks)
                    yield ctx.cpu(p.bitmap_release_ns)
                    self.pool_full = False
                self._set(h, S_PRESENT)
                yield from self._pte(ctx, h, True)   # PTE valid is the last step
                self.lru[h] = None
                kind = 'fault_ro' if ro else 'fault_rw'
            else:
                self.st['decompress_' + self.spec.enum_name['status'].get(cpl['status'], '?')] += 1
                self._free_frame(h)
                self._set(h, S_LOST)
                self.st['lost_ro' if ro else 'lost_rw'] += 1
                kind = 'lost'
            self.busy.pop(h).succeed()
            self.lock.release()
            break
        yield ctx.cpu(p.fault_exit_ns)
        total = sim.now - t0
        part['cpu'] = total - sum(part.values())
        self.lat[kind].append(total)
        self.parts[kind].update(part)
        pm = self.part_max[kind]
        for q, v in part.items():
            if v > pm[q]:
                pm[q] = v
        if total > self.worst.get(kind, (0,))[0]:
            self.worst[kind] = (total, dict(part), h, t0)
        return kind

    # ---- background reclaim
    def _reclaimer(self):
        cfg = self.cfg
        while True:
            if len(self.free_frames) > cfg.fc_low:
                yield self.reclaim_sig.wait()
                continue
            self.st['reclaim_runs'] += 1
            stuck = yield from self._reclaim_to(cfg.fc_high)
            if stuck:                                # nothing left to evict: wait until something changes
                self.st['reclaim_stuck'] += 1
                yield self.sim.any_of(self.reclaim_sig.wait(), self.frame_sig.wait())

    def _reclaim_to(self, target):
        sim, p, cfg, ctx = self.sim, self.p, self.cfg, self.rctx
        while len(self.free_frames) + self.inflight < target:
            if self.inflight >= p.reclaim_inflight:
                yield self.cdone_sig.wait()
                continue
            yield self.lock.acquire()
            yield ctx.cpu(p.victim_pick_ns)
            h = self._pick_victim()
            if h is None:
                self.lock.release()
                if not self.inflight:
                    return True
                yield self.cdone_sig.wait()
                continue
            if cfg.is_ro(h):                         # the stored copy is still there: just drop the frame
                yield from self._pte(ctx, h, False)
                del self.lru[h]
                self._free_frame(h)
                self._set(h, S_COMPRESSED)
                self.st['ro_drops'] += 1
                self.lock.release()
                continue
            if self.bitmap.free < self.need:
                self.pool_full = True
                self.st['rw_pool_full'] += 1
                self.lru.move_to_end(h)
                self.lock.release()
                continue
            chunks = self.bitmap.reserve(self.need)
            yield ctx.cpu(p.bitmap_reserve_ns)
            self._note_pool()
            if self._m('no_pte_inval'):
                self.mapped[h] = 0
            else:
                yield from self._pte(ctx, h, False)
            del self.lru[h]
            self._set(h, S_COMPRESSING)
            self.busy[h] = sim.event()
            self.inflight += 1
            self.lock.release()
            sim.process(self._compress_one(h, chunks), 'compress')
        return False

    def _pick_victim(self):
        """Oldest page that can go: RO always, RW unless known incompressible or the pool is full."""
        cfg, lru = self.cfg, self.lru
        moved = 0
        while True:
            batch = list(islice(lru, 64))
            if not batch:
                return None
            for h in batch:
                if cfg.is_ro(h) or not (self.pool_full or h in self.incompressible):
                    return h
            if self.pool_full:
                return next((h for h in lru if cfg.is_ro(h)), None)
            for h in batch:                          # the oldest 64 are all incompressible: move them away
                lru.move_to_end(h)
            moved += len(batch)
            self.st['skip_incompressible'] += len(batch)
            if moved >= len(lru):
                return None

    def _compress_one(self, h, chunks):
        sim, p, cfg, plat, ctx = self.sim, self.p, self.cfg, self.plat, self.rctx
        self.jobs += 1
        yield ctx.cpu(p.desc_build_ns)
        listed = list(chunks)
        if self._m('busy_chunks'):
            listed[0] = 0                            # chunk 0 belongs to the RO image
        desc = {'opcode': self.OP.COMPRESS, 'count': len(listed), 'limit': self.limit,
                'frame_pa': cfg.frame_pa(self.frame_of[h]), 'chunk': listed}
        cpl, tm = yield from self.drv.submit(ctx, desc, h)
        yield self.lock.acquire()
        if cpl['status'] == self.ST.OK:
            used = ceil(cpl['length'] / cfg.chunk)
            entry = {'flags': self.FL.VALID | (cpl['flags'] & self.FL.RAW), 'count': used,
                     'comp_len': cpl['length'], 'checksum': cpl['checksum'], 'chunk': chunks[:used]}
            if self._m('cot_wrong_len'):
                entry['comp_len'] -= 1
            yield from plat.mem_write(ctx, cfg.entry_pa(h), self.spec.pack('cot_entry', entry),
                                      p.cot_write_ns, 'cot')
            if used < len(chunks) and not self._m('no_trim'):
                self.bitmap.release(chunks[used:])   # give back what the stream did not need
                yield ctx.cpu(p.bitmap_release_ns)
            self._free_frame(h)
            self._set(h, S_COMPRESSED)
            self.st['rw_compress_ok'] += 1
            self.st['rw_comp_bytes'] += cpl['length']
            self.st['rw_comp_chunks'] += used
        else:                                        # keep the page hot
            self.bitmap.release(chunks)
            yield ctx.cpu(p.bitmap_release_ns)
            self._set(h, S_PRESENT)
            yield from self._pte(ctx, h, True)
            self.lru[h] = None
            if cpl['status'] == self.ST.INCOMPRESSIBLE:
                self.incompressible.add(h)
                self.st['rw_incompressible'] += 1
            else:
                self.st['compress_' + self.spec.enum_name['status'].get(cpl['status'], '?')] += 1
        self.busy.pop(h).succeed()
        self.inflight -= 1
        self.lock.release()
        self.cdone_sig.fire()

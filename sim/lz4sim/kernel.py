"""The kernel side: page states, frame cache, reclaim, fault handling.

KernelBase holds what both variants share. BaselineKernel talks to an
accelerator that owns the free-chunk stack and the RW COT entries; it only
issues COMPRESS / DECOMPRESS / INVALIDATE / INIT. SoftwareKernel owns the COT and
the chunk bitmap itself and hands the accelerator self-contained descriptors.

Every page is in one of these states:
    compressed     object in the pool, no frame (RO at boot; RW after COMPRESS)
    present        in a frame, PTE valid
    untouched      RW only: never written, no frame, no object
    compressing    RW only: COMPRESS in flight, frame still held
    decompressing  DECOMPRESS in flight
    lost           BAD_STREAM: no copy anywhere
"""
from array import array
from collections import Counter, OrderedDict
from itertools import islice
from math import ceil

from .codec import checksum
from .formats import (COTEntry, BaselineDesc, VariantDesc, EMPTY_ENTRY, F_VALID, F_RAW,
                      OP_COMPRESS, OP_DECOMPRESS, OP_INVALIDATE, OP_INIT,
                      ST_OK, ST_INCOMPRESSIBLE, ST_POOL_FULL, ST_BAD_STREAM)

S_COMPRESSED, S_PRESENT, S_UNTOUCHED, S_COMPRESSING, S_DECOMPRESSING, S_LOST = range(6)
S_NAME = ['compressed', 'present', 'untouched', 'compressing', 'decompressing', 'lost']


class DataMismatch(Exception):
    pass


class OutOfMemory(Exception):
    pass


class KernelBase:
    variant = 'base'

    def __init__(self, cfg, dram, accel, trace, wl, clk, expect):
        self.cfg = cfg
        self.dram = dram
        self.accel = accel
        self.trace = trace
        self.wl = wl
        self.clk = clk
        self.expect = expect
        self.zero_page = bytes(cfg.page)
        self.zero_crc = checksum(self.zero_page)
        self.state = bytearray(cfg.pages)
        for h in range(cfg.rw_pages):
            self.state[h] = S_UNTOUCHED
        self.frame_of = array('i', [-1]) * cfg.pages
        self.lru = OrderedDict()
        self.free_frames = list(range(cfg.frames - 1, -1, -1))
        self.incompressible = set()
        self.pool_full = False
        self.oom = False
        self.st = Counter()
        self.peak_frames = 0
        self.peak_pool = 0
        self.fault_lat_sum = 0.0
        self.fault_lat_max = 0.0
        self.comp_bytes = 0
        self.comp_chunks = 0
        self.cst = [Counter() for _ in wl.clients]   # per user program: what it asked for and what it waited

    # ---- boot
    def boot(self, first_free):
        self.boot_alloc(first_free)

    def load_page(self, h, page):
        """Boot loader: an initialised RW page (.data) placed in a frame."""
        f = self._alloc_frame(h)
        self.dram.write(self.cfg.frame_pa(f), page)
        self.expect[h] = checksum(page)
        self._set_state(h, S_PRESENT)
        self._pte(h, True)
        self.lru[h] = None
        self.st['loaded'] += 1

    # ---- the access path
    def access(self, h, write):
        cfg = self.cfg
        s = self.state[h]
        c = self.wl.owner[h]            # the user program this page belongs to
        cs = self.cst[c]
        cs['accesses'] += 1
        if s == S_PRESENT:
            self.lru.move_to_end(h)
            self.st['hits'] += 1
            cs['hits'] += 1
            self.trace.emit('access', h=h, w=int(write), res='hit', client=c)
            if write:
                self._write(h)
            return 'hit'
        if s == S_UNTOUCHED:
            self._ensure_frame()
            if self.oom:
                return 'oom'
            f = self._alloc_frame(h)
            self.dram.write(cfg.frame_pa(f), self.zero_page)
            self.expect[h] = self.zero_crc
            self._set_state(h, S_PRESENT)
            self._pte(h, True)
            self.lru[h] = None
            self.clk.t += cfg.kernel_fault_ns
            self.clk.kernel_fg += cfg.kernel_fault_ns
            self.st['first_touch'] += 1
            cs['first_touch'] += 1
            self.trace.emit('access', h=h, w=int(write), res='first', client=c)
            if write:
                self._write(h, fill=True)
            return 'first'
        if s == S_COMPRESSED:
            self._ensure_frame()
            if self.oom:
                return 'oom'
            t0 = self.clk.t
            f = self._alloc_frame(h)
            self.clk.t += cfg.kernel_fault_ns
            self.clk.kernel_fg += cfg.kernel_fault_ns
            ok = self._fault_in(h, f)
            if not ok:
                self._release_frame(h)
                self._set_state(h, S_LOST)
                self.st['lost'] += 1
                self.st['lost_ro' if cfg.is_ro(h) else 'lost_rw'] += 1
                cs['lost'] += 1
                self.trace.emit('access', h=h, w=int(write), res='lost', client=c)
                return 'lost'
            self._set_state(h, S_PRESENT)
            self._pte(h, True)
            self.lru[h] = None
            self._verify(h)
            lat = self.clk.t - t0
            self.fault_lat_sum += lat
            self.fault_lat_max = max(self.fault_lat_max, lat)
            self.st['faults'] += 1
            self.st['faults_ro' if cfg.is_ro(h) else 'faults_rw'] += 1
            cs['faults'] += 1
            cs['fault_lat'] += lat
            self.trace.emit('access', h=h, w=int(write), res='fault', lat_ns=round(lat), client=c)
            if write:
                self._write(h)
            return 'fault'
        self.st['lost_access'] += 1
        return 'lost'

    def _write(self, h, fill=False):
        mv = self.dram.view(self.cfg.frame_pa(self.frame_of[h]), self.cfg.page)
        if fill:
            self.wl.fill(mv)
        else:
            self.wl.mutate(mv)
        self.expect[h] = checksum(mv)
        self.st['writes'] += 1

    def _verify(self, h):
        mv = self.dram.view(self.cfg.frame_pa(self.frame_of[h]), self.cfg.page)
        if checksum(mv) != self.expect[h]:
            raise DataMismatch(f'page {h:#x} restored with wrong contents')

    # ---- frames and reclaim
    def _alloc_frame(self, h):
        f = self.free_frames.pop()
        self.frame_of[h] = f
        used = self.cfg.frames - len(self.free_frames)
        if used > self.peak_frames:
            self.peak_frames = used
        self.trace.emit('frame', who='kernel', op='alloc', h=h, pa=self.cfg.frame_pa(f))
        return f

    def _release_frame(self, h):
        f = self.frame_of[h]
        self.frame_of[h] = -1
        self.free_frames.append(f)
        self.trace.emit('frame', who='kernel', op='free', h=h, pa=self.cfg.frame_pa(f))

    def _ensure_frame(self):
        if len(self.free_frames) > self.cfg.fc_low:
            return
        t0, cpu0 = self.clk.t, self.clk.kernel_fg
        self._reclaim(self.cfg.fc_high)
        # reclaim is background work: charge the CPU time to kernel_bg and do not
        # advance the foreground clock (no contention model in this milestone)
        self.clk.kernel_bg += self.clk.kernel_fg - cpu0
        self.clk.kernel_fg = cpu0
        self.clk.t = t0
        if not self.free_frames:
            self.oom = True
            self.st['oom'] += 1

    def _reclaim(self, target):
        self.st['reclaims'] += 1
        while len(self.free_frames) < target:
            h = self._pick_victim()
            if h is None:
                self.st['reclaim_stuck'] += 1
                break
            self.clk.t += self.cfg.kernel_evict_ns
            self.clk.kernel_fg += self.cfg.kernel_evict_ns
            if self.cfg.is_ro(h):
                self._drop_ro(h)
            else:
                self._evict_rw(h)

    def _pick_victim(self):
        cfg = self.cfg
        moved = 0
        while True:
            batch = list(islice(self.lru, 64))
            if not batch:
                return None
            for h in batch:
                if cfg.is_ro(h):
                    return h
                if self.pool_full or h in self.incompressible:
                    continue
                return h
            if self.pool_full:
                for h in self.lru:
                    if cfg.is_ro(h):
                        return h
                return None
            # the oldest 64 are all incompressible RW pages: send them to the MRU end
            for h in batch:
                self.lru.move_to_end(h)
            moved += len(batch)
            self.st['skip_incompressible'] += len(batch)
            if moved >= len(self.lru):
                return None

    def _drop_ro(self, h):
        self._pte(h, False)
        self._release_frame(h)
        self._set_state(h, S_COMPRESSED)
        del self.lru[h]
        self.st['ro_drops'] += 1

    def _note_pool(self):
        used = self.cfg.pool_chunks - self.free_chunks()
        if used > self.peak_pool:
            self.peak_pool = used

    # ---- trace helpers
    def _set_state(self, h, s):
        old = self.state[h]
        self.state[h] = s
        self.trace.emit('state', h=h, **{'from': S_NAME[old], 'to': S_NAME[s]})

    def _pte(self, h, valid):
        pa = self.cfg.frame_pa(self.frame_of[h]) if valid else 0
        self.trace.emit('pte', who='kernel', h=h, valid=int(valid), pa=pa)

    # ---- per-variant
    def boot_alloc(self, first_free):
        raise NotImplementedError

    def free_chunks(self):
        raise NotImplementedError

    def free_chunk_set(self):
        raise NotImplementedError

    def _evict_rw(self, h):
        raise NotImplementedError

    def _fault_in(self, h, f):
        raise NotImplementedError

    def alloc_stats(self):
        return {}


class BaselineKernel(KernelBase):
    variant = 'baseline'

    def __init__(self, cfg, dram, accel, trace, wl, clk, expect, stack):
        super().__init__(cfg, dram, accel, trace, wl, clk, expect)
        self.stack = stack

    def boot_alloc(self, first_free):
        comp, lat = self.accel.submit(BaselineDesc(OP_INIT, handle=first_free))
        if comp.status != ST_OK:
            raise RuntimeError('INIT failed')
        self.clk.t += lat

    def free_chunks(self):
        return self.stack.free_count()

    def free_chunk_set(self):
        return self.stack.enumerate_free()

    def _evict_rw(self, h):
        cfg = self.cfg
        f = self.frame_of[h]
        self._pte(h, False)
        self._set_state(h, S_COMPRESSING)
        desc = BaselineDesc(OP_COMPRESS, handle=h, frame_pa=cfg.frame_pa(f),
                            limit=cfg.compress_limit_for_rw(), tag=h)
        comp, lat = self.accel.submit(desc)
        self.clk.t += lat
        if comp.status == ST_OK:
            self._release_frame(h)
            self._set_state(h, S_COMPRESSED)
            del self.lru[h]
            self.st['rw_compress_ok'] += 1
            self.comp_bytes += comp.length
            self.comp_chunks += ceil(comp.length / cfg.chunk)
            if comp.flags & F_RAW:
                self.st['rw_raw'] += 1
            self._note_pool()
            return True
        self._set_state(h, S_PRESENT)
        self._pte(h, True)
        self.lru.move_to_end(h)
        if comp.status == ST_INCOMPRESSIBLE:
            self.incompressible.add(h)
            self.st['rw_incompressible'] += 1
        elif comp.status == ST_POOL_FULL:
            self.pool_full = True
            self.st['rw_pool_full'] += 1
        else:
            raise RuntimeError(f'unexpected COMPRESS status {comp.status}')
        return False

    def _fault_in(self, h, f):
        cfg = self.cfg
        self._set_state(h, S_DECOMPRESSING)
        desc = BaselineDesc(OP_DECOMPRESS, handle=h, frame_pa=cfg.frame_pa(f), limit=cfg.page, tag=h)
        comp, lat = self.accel.submit(desc)
        self.clk.t += lat
        if comp.status != ST_OK:
            if comp.status != ST_BAD_STREAM:
                raise RuntimeError(f'unexpected DECOMPRESS status {comp.status}')
            self.st['bad_stream'] += 1
            return False
        if not cfg.is_ro(h):
            comp2, lat2 = self.accel.submit(BaselineDesc(OP_INVALIDATE, handle=h, tag=h))
            self.clk.t += lat2
            if comp2.status != ST_OK:
                raise RuntimeError(f'unexpected INVALIDATE status {comp2.status}')
            self.incompressible.discard(h)
            self.pool_full = False
            self.st['rw_invalidate'] += 1
        return True

    def alloc_stats(self):
        s = self.stack.st
        a = self.accel.st
        return {'stack_pops': s['pops'], 'stack_pushes': s['pushes'], 'stack_refills': s['refills'],
                'stack_spills': s['spills'], 'stack_sram_end': len(self.stack.sram),
                'stack_list_chunks_end': self.stack.list_chunks,
                'ctlb_hit': a['ctlb_hit'], 'ctlb_miss': a['ctlb_miss']}


class SoftwareKernel(KernelBase):
    variant = 'software'

    def __init__(self, cfg, dram, accel, trace, wl, clk, expect, bitmap):
        super().__init__(cfg, dram, accel, trace, wl, clk, expect)
        self.bitmap = bitmap

    def boot_alloc(self, first_free):
        self.bitmap.build_from_cot(self.dram)

    def free_chunks(self):
        return self.bitmap.free

    def free_chunk_set(self):
        return self.bitmap.enumerate_free()

    def _write_entry(self, h, entry):
        data = entry.pack() if entry is not None else EMPTY_ENTRY
        self.dram.write(self.cfg.entry_pa(h), data)
        self.trace.emit('cot', who='kernel', h=h,
                        entry=(entry or COTEntry()).to_dict(), hex=data.hex())

    def _evict_rw(self, h):
        cfg = self.cfg
        limit = cfg.compress_limit_for_rw()
        need = ceil(limit / cfg.chunk)
        if self.bitmap.free < need:
            self.pool_full = True
            self.st['rw_pool_full'] += 1
            self.lru.move_to_end(h)
            return False
        self.pool_full = False
        chunks = self.bitmap.reserve(need)
        f = self.frame_of[h]
        self._pte(h, False)
        self._set_state(h, S_COMPRESSING)
        desc = VariantDesc(OP_COMPRESS, frame_pa=cfg.frame_pa(f), chunks=tuple(chunks), limit=limit, tag=h)
        comp, lat = self.accel.submit(desc)
        self.clk.t += lat + cfg.kernel_job_ns
        self.clk.kernel_fg += cfg.kernel_job_ns
        if comp.status == ST_OK:
            used = ceil(comp.length / cfg.chunk)
            entry = COTEntry(F_VALID | (comp.flags & F_RAW), used, comp.length, comp.checksum,
                             tuple(chunks[:used]))
            self._write_entry(h, entry)
            if used < len(chunks):
                self.bitmap.release(chunks[used:], op='trim')
            self._release_frame(h)
            self._set_state(h, S_COMPRESSED)
            del self.lru[h]
            self.st['rw_compress_ok'] += 1
            self.comp_bytes += comp.length
            self.comp_chunks += used
            if comp.flags & F_RAW:
                self.st['rw_raw'] += 1
            self._note_pool()
            return True
        self.bitmap.release(chunks)
        self._set_state(h, S_PRESENT)
        self._pte(h, True)
        self.lru.move_to_end(h)
        if comp.status == ST_INCOMPRESSIBLE:
            self.incompressible.add(h)
            self.st['rw_incompressible'] += 1
        else:
            raise RuntimeError(f'unexpected COMPRESS status {comp.status}')
        return False

    def _fault_in(self, h, f):
        cfg = self.cfg
        entry = COTEntry.unpack(self.dram.read(cfg.entry_pa(h), 32))
        self.trace.emit('cot_read', who='kernel', h=h, entry=entry.to_dict())
        if not entry.valid:
            raise RuntimeError(f'fault on {h:#x} without a valid entry')
        self._set_state(h, S_DECOMPRESSING)
        desc = VariantDesc(OP_DECOMPRESS, frame_pa=cfg.frame_pa(f), chunks=entry.chunks, limit=cfg.page,
                           comp_len=entry.comp_len, flags=entry.flags & F_RAW,
                           checksum=entry.checksum, tag=h)
        comp, lat = self.accel.submit(desc)
        self.clk.t += lat + cfg.kernel_job_ns
        self.clk.kernel_fg += cfg.kernel_job_ns
        if comp.status != ST_OK:
            if comp.status != ST_BAD_STREAM:
                raise RuntimeError(f'unexpected DECOMPRESS status {comp.status}')
            self.st['bad_stream'] += 1
            return False
        if not cfg.is_ro(h):
            self._write_entry(h, None)
            self.bitmap.release(list(entry.chunks))
            self.incompressible.discard(h)
            self.pool_full = False
            self.st['rw_free'] += 1
        return True

    def alloc_stats(self):
        b = self.bitmap
        n = b.st['reserves'] or 1
        return {'bitmap_bytes': b.bytes, 'bitmap_reserves': b.st['reserves'],
                'bitmap_releases': b.st['releases'], 'bitmap_words_scanned': b.st['words_scanned'],
                'bitmap_words_per_reserve': b.st['words_scanned'] / n,
                'bitmap_words_max': b.scan_max, 'bitmap_wraps': b.st['wraps'],
                'bad_desc': self.accel.st['bad_desc']}

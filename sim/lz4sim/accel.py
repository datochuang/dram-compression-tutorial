"""The LZ4 accelerator in its two forms.

Shared by both forms, each in one place:

  engine.py   Lz4Engine: compress, scatter, gather, checksum, decompress, stream timing
  AccelBase   the job frame: take a descriptor, run it, write a completion record,
              count and time the job
  formats.py  the descriptor, completion and COT entry layouts and the status codes

What differs is only who supplies the chunk numbers, the stream length and the
checksum to the engine, and who writes the COT:

BaselineAccel (hardware-leaning): owns the free-chunk stack and a 1-entry CTLB,
reads COT entries, writes RW entries at the end of COMPRESS, frees objects on
INVALIDATE, builds the free list on INIT.

SoftwareAccel (software-leaning): stateless between jobs. The descriptor
carries every address; the engine never reads or writes the COT, only range
checks what it was given.

Latency model (no contention): dram_ns per dependent DRAM access on the critical
path (descriptor fetch, table read, first data, completion write) plus the
streaming time of 4096 bytes at the engine rate.
"""
from collections import Counter
from .engine import Lz4Engine
from .formats import (COTEntry, Completion, EMPTY_ENTRY, F_VALID, F_RAW,
                      OP_COMPRESS, OP_DECOMPRESS, OP_INVALIDATE, OP_INIT, OP_NAME,
                      ST_OK, ST_INCOMPRESSIBLE, ST_POOL_FULL, ST_BAD_STREAM, ST_BAD_HANDLE,
                      ST_BAD_DESC, ST_NAME, CHUNK_SLOTS)


class AccelBase:
    def __init__(self, cfg, dram, trace, clk):
        self.cfg = cfg
        self.dram = dram
        self.trace = trace
        self.clk = clk
        self.eng = Lz4Engine(cfg, dram)   # the shared datapath, identical in both designs
        self.st = Counter()

    def submit(self, desc):
        self.trace.emit('job', who='kernel', op=OP_NAME.get(desc.opcode, desc.opcode),
                        desc=desc.to_dict(), hex=desc.pack().hex())
        comp, lat = self._run(desc)
        self.st['jobs'] += 1
        self.st['op_' + OP_NAME.get(desc.opcode, str(desc.opcode))] += 1
        self.st['st_' + ST_NAME[comp.status]] += 1
        self.clk.accel += lat
        self.trace.emit('done', who='hw', status=ST_NAME[comp.status], len=comp.length,
                        csum=comp.checksum, flags=comp.flags, tag=comp.tag, lat_ns=round(lat),
                        hex=comp.pack().hex())
        return comp, lat


class BaselineAccel(AccelBase):
    def __init__(self, cfg, dram, trace, clk, stack):
        super().__init__(cfg, dram, trace, clk)
        self.stack = stack
        self.ctlb_handle = -1
        self.ctlb_entry = None

    def _lookup(self, h):
        """COT entry through the 1-entry CTLB; returns (entry, dram accesses)."""
        if h == self.ctlb_handle:
            self.st['ctlb_hit'] += 1
            return self.ctlb_entry, 0
        entry = COTEntry.unpack(self.dram.read(self.cfg.entry_pa(h), 32))
        self.ctlb_handle, self.ctlb_entry = h, entry
        self.st['ctlb_miss'] += 1
        return entry, 1

    def _run(self, d):
        cfg = self.cfg
        dram_ns = cfg.dram_ns
        if d.opcode == OP_INIT:
            free = self.stack.init(d.handle)
            return Completion(ST_OK, tag=d.tag, aux=free), dram_ns * (2 + self.stack.st['init_writes'])
        if d.opcode not in (OP_COMPRESS, OP_DECOMPRESS, OP_INVALIDATE):
            return Completion(ST_BAD_DESC, tag=d.tag), dram_ns * 2
        if d.handle >= cfg.pages:
            return Completion(ST_BAD_HANDLE, tag=d.tag), dram_ns * 2
        h = d.handle

        if d.opcode == OP_COMPRESS:
            ev0 = self.stack.dram_events()
            blob, raw, status = self.eng.compress_frame(d.frame_pa, d.limit)
            stream = self.eng.comp_ns()
            if status is not None:
                # the engine popped a chunk per 512 B of output until it crossed the
                # limit, then handed every chunk back
                popped = []
                for _ in range(d.limit // cfg.chunk):
                    c = self.stack.pop()
                    if c is None:
                        break
                    popped.append(c)
                for c in reversed(popped):
                    self.stack.push(c)
                self.trace.emit('chunk', who='hw', op='pop', chunks=popped)
                self.trace.emit('chunk', who='hw', op='push', chunks=list(reversed(popped)))
                extra = self.stack.dram_events() - ev0
                return Completion(status, tag=d.tag), dram_ns * (3 + extra) + stream
            n = self.eng.chunks_for(blob)
            chunks = []
            for _ in range(n):
                c = self.stack.pop()
                if c is None:
                    for c2 in reversed(chunks):
                        self.stack.push(c2)
                    self.trace.emit('chunk', who='hw', op='pop', chunks=chunks)
                    self.trace.emit('chunk', who='hw', op='push', chunks=list(reversed(chunks)))
                    extra = self.stack.dram_events() - ev0
                    return Completion(ST_POOL_FULL, tag=d.tag), dram_ns * (3 + extra) + stream
                chunks.append(c)
            self.trace.emit('chunk', who='hw', op='pop', chunks=chunks)
            self.eng.scatter(blob, chunks)
            entry = COTEntry(F_VALID | (F_RAW if raw else 0), n, len(blob), self.eng.checksum(blob), tuple(chunks))
            self.dram.write(cfg.entry_pa(h), entry.pack())
            self.trace.emit('cot', who='hw', h=h, entry=entry.to_dict(), hex=entry.pack().hex())
            self.ctlb_handle, self.ctlb_entry = h, entry
            extra = self.stack.dram_events() - ev0
            return (Completion(ST_OK, len(blob), entry.checksum, d.tag, F_RAW if raw else 0),
                    dram_ns * (4 + extra) + stream)

        if d.opcode == OP_DECOMPRESS:
            entry, acc = self._lookup(h)
            stream = self.eng.decomp_ns()
            if not entry.valid:
                return Completion(ST_BAD_HANDLE, tag=d.tag), dram_ns * (2 + acc)
            if not self.eng.decompress_to_frame(entry.chunks, entry.comp_len, entry.raw, entry.checksum, d.frame_pa):
                self.st['bad_stream'] += 1
                return Completion(ST_BAD_STREAM, tag=d.tag), dram_ns * (3 + acc) + stream
            return (Completion(ST_OK, cfg.page, entry.checksum, d.tag, entry.flags & F_RAW),
                    dram_ns * (3 + acc) + stream)

        # OP_INVALIDATE
        ev0 = self.stack.dram_events()
        entry, acc = self._lookup(h)
        if not entry.valid or entry.ro:
            return Completion(ST_BAD_HANDLE, tag=d.tag), dram_ns * (2 + acc)
        for c in entry.chunks:
            self.stack.push(c)
        self.trace.emit('chunk', who='hw', op='push', chunks=list(entry.chunks))
        self.dram.write(cfg.entry_pa(h), EMPTY_ENTRY)
        self.trace.emit('cot', who='hw', h=h, entry=COTEntry().to_dict(), hex=EMPTY_ENTRY.hex())
        self.ctlb_handle, self.ctlb_entry = -1, None
        extra = self.stack.dram_events() - ev0
        return Completion(ST_OK, 0, 0, d.tag), dram_ns * (3 + acc + extra)


class SoftwareAccel(AccelBase):
    def _check(self, d):
        cfg = self.cfg
        if d.opcode not in (OP_COMPRESS, OP_DECOMPRESS):
            return False
        if len(d.chunks) > CHUNK_SLOTS:
            return False
        if any(c >= cfg.pool_chunks for c in d.chunks):
            return False
        if not (cfg.fc_base <= d.frame_pa < cfg.dram_end) or d.frame_pa % cfg.page:
            return False
        return True

    def _run(self, d):
        cfg = self.cfg
        dram_ns = cfg.dram_ns
        if not self._check(d):
            self.st['bad_desc'] += 1
            return Completion(ST_BAD_DESC, tag=d.tag), dram_ns * 2

        if d.opcode == OP_COMPRESS:
            blob, raw, status = self.eng.compress_frame(d.frame_pa, d.limit)
            stream = self.eng.comp_ns()
            if status is not None:
                return Completion(status, tag=d.tag), dram_ns * 3 + stream
            n = self.eng.chunks_for(blob)
            if n > len(d.chunks):
                self.st['bad_desc'] += 1
                return Completion(ST_BAD_DESC, tag=d.tag), dram_ns * 3 + stream
            self.eng.scatter(blob, d.chunks[:n])
            return (Completion(ST_OK, len(blob), self.eng.checksum(blob), d.tag, F_RAW if raw else 0),
                    dram_ns * 3 + stream)

        # OP_DECOMPRESS
        stream = self.eng.decomp_ns()
        if not self.eng.decompress_to_frame(d.chunks, d.comp_len, bool(d.flags & F_RAW), d.checksum, d.frame_pa):
            self.st['bad_stream'] += 1
            return Completion(ST_BAD_STREAM, tag=d.tag), dram_ns * 3 + stream
        return Completion(ST_OK, cfg.page, d.checksum, d.tag, d.flags & F_RAW), dram_ns * 3 + stream

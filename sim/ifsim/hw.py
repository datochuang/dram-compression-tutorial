"""LZ4 HW model: registers, job ring consumer, staged job execution, completion ring producer.

Stateless between jobs: everything a job needs is in its 48 B descriptor. The HW
never reads the COT. Timing is per stage, not per clock: descriptor fetch, input
DMA, the LZ4 core and output DMA overlap the way a streaming pipeline does, each
DMA burst goes through the Bus.

`mut` holds deliberate bugs for the checker tests: {name: ordinal of the job}.
"""
from collections import Counter
from math import ceil

from lz4sim.codec import compress, decompress, checksum
from lz4sim.dram import BusError


class Lz4Hw:
    def __init__(self, sim, spec, p, bus, mon, irq, dram, meter):
        self.sim, self.spec, self.p = sim, spec, p
        self.bus, self.mon, self.irq, self.dram, self.meter = bus, mon, irq, dram, meter
        self.r = {reg['name']: reg['reset'] for reg in spec.registers}
        self.epoch = 0
        self.busy = False
        self.resetting = False
        self.halted = False
        self.error = False
        self._wait = None
        self.fetched = 0
        self.busy_ns = 0
        self.st = Counter()
        self.job_ns = {1: [], 2: []}          # opcode -> fetch to completion posted
        self.hang = set(p.hw_hang_jobs)
        self.mut = {}
        self.EN = spec.bit('CTRL', 'ENABLE')
        self.RST = spec.bit('CTRL', 'SOFT_RESET')
        sim.process(self._engine(), 'lz4hw')

    def _m(self, name):
        """True once, at the first place that asks from job ordinal mut[name] on."""
        n = self.mut.get(name)
        if n is None or self.fetched < n:
            return False
        del self.mut[name]
        return True

    # ---- register interface
    def mmio_write(self, off, val):
        reg = self.spec.reg_at.get(off)
        if reg is None:
            return
        name, r = reg['name'], self.r
        val &= 0xFFFFFFFF
        if name == 'CTRL':
            if val & self.RST:
                self._reset()
                return
            en = val & self.EN
            if en and not r['CTRL']:
                code = self._check_cfg()
                if code:
                    self._halt(code)
                    return
            r['CTRL'] = en
            self._kick()
        elif name == 'IRQ_STATUS':
            if val & self.spec.bit('IRQ_STATUS', 'ERROR'):
                self.error = False
                self._irq()
        elif name == 'IRQ_ENABLE':
            r[name] = val & 3
            self._irq()
        elif name == 'JOB_TAIL':
            if val >= r['JOB_SIZE']:
                self._halt(self.spec.enum['halt_code'].BAD_INDEX)
                return
            r[name] = val
            self._kick()
        elif name == 'CPL_HEAD':
            if val >= r['CPL_SIZE']:
                self._halt(self.spec.enum['halt_code'].BAD_INDEX)
                return
            r[name] = val
            self._irq()
            self._kick()
        elif name in self.spec.config_regs:
            if r['CTRL'] & self.EN:
                self.st['cfg_write_ignored'] += 1
            else:
                r[name] = val
        # anything else is read-only: the write is dropped

    def mmio_read(self, off):
        reg = self.spec.reg_at.get(off)
        if reg is None:
            return 0
        name, r = reg['name'], self.r
        if name == 'STATUS':
            return int(self.busy or self.resetting) | (int(self.halted) << 1)
        if name == 'IRQ_STATUS':
            return int(r['CPL_TAIL'] != r['CPL_HEAD']) | (int(self.error) << 1)
        return r[name]

    def _check_cfg(self):
        r, c = self.r, self.spec.const
        top = 1 << self.spec.get('CAP', 'RING_SHIFT_MAX', r['CAP'])
        for size in (r['JOB_SIZE'], r['CPL_SIZE']):
            if size < 2 or size > top or size & (size - 1):
                return self.spec.enum['halt_code'].BAD_RING_CFG
        if r['JOB_BASE'] % c.JOB_SLOT_SIZE or r['CPL_BASE'] % c.CPL_SLOT_SIZE:
            return self.spec.enum['halt_code'].BAD_RING_CFG
        return 0

    def _irq(self):
        r = self.r
        if self.mut.get('irq_stuck', 1 << 60) <= self.fetched:
            return
        en = r['IRQ_ENABLE']
        self.irq.set((r['CPL_TAIL'] != r['CPL_HEAD'] and en & 1) or (self.error and en & 2))

    def _halt(self, code):
        self.halted = True
        self.error = True
        self.r['ERR_CODE'] = code
        self.st['halts'] += 1
        self.mon.emit('hw', 'halt', code=code)
        self._irq()

    def _reset(self):
        r = self.r
        self.epoch += 1
        for name in ('JOB_HEAD', 'JOB_TAIL', 'CPL_TAIL', 'CPL_HEAD', 'ERR_CODE', 'CTRL'):
            r[name] = 0
        self.halted = False
        self.error = False
        self.resetting = True
        self.st['resets'] += 1
        self._irq()
        self.mon.emit('hw', 'reset')
        self._kick()

    def _new_wait(self):
        self._wait = self.sim.event()
        return self._wait

    def _kick(self):
        w = self._wait
        if w is not None and not w.done:
            w.succeed()

    # ---- the engine: one job at a time, in ring order
    def _engine(self):
        sim, r, p, spec = self.sim, self.r, self.p, self.spec
        JS, CS = spec.const.JOB_SLOT_SIZE, spec.const.CPL_SLOT_SIZE
        DS = spec.size('job_desc')
        while True:
            if self.resetting:
                yield sim.timeout(p.reset_ns)
                self.resetting = False
                self.busy = False
                continue
            if not r['CTRL'] & self.EN or self.halted or r['JOB_HEAD'] == r['JOB_TAIL']:
                self.busy = False
                yield self._new_wait()
                continue
            self.busy = True
            ep, t0 = self.epoch, sim.now
            head = r['JOB_HEAD']
            try:
                raw = yield from self.bus.xfer('hw', r['JOB_BASE'] + head * JS, DS)
            except BusError:
                self._halt(spec.enum['halt_code'].RING_BUS_ERROR)
                continue
            if ep != self.epoch:
                continue
            self.fetched += 1
            r['JOB_HEAD'] = (head + 1) & (r['JOB_SIZE'] - 1)
            self.mon.emit('hw', 'reg', reg='JOB_HEAD', val=r['JOB_HEAD'])
            d = spec.unpack('job_desc', raw)
            if self._m('reread'):
                yield from self.bus.xfer('hw', r['JOB_BASE'] + head * JS, DS)
            self.meter.mark(d['tag'], 'fetch', t0)
            if self.fetched in self.hang:                     # fault injection: this job never finishes
                self.st['hung'] += 1
                while ep == self.epoch:
                    yield self._new_wait()
                continue
            cpl = yield from self._execute(d, ep)
            if ep != self.epoch:
                continue
            if self._m('wrong_tag'):
                cpl['tag'] ^= 0x8000
            while ((r['CPL_TAIL'] + 1) & (r['CPL_SIZE'] - 1)) == r['CPL_HEAD'] and ep == self.epoch:
                self.st['cpl_stall'] += 1                     # completion ring full: wait for the FW
                yield self._new_wait()
            if ep != self.epoch:
                continue
            tail = r['CPL_TAIL']
            nxt = (tail + 1) & (r['CPL_SIZE'] - 1)
            tail_first = self._m('tail_first')
            if tail_first:
                r['CPL_TAIL'] = nxt
                self.mon.emit('hw', 'reg', reg='CPL_TAIL', val=nxt)
            try:
                yield from self.bus.xfer('hw', r['CPL_BASE'] + tail * CS, CS, spec.pack('completion', cpl))
            except BusError:
                self._halt(spec.enum['halt_code'].RING_BUS_ERROR)
                continue
            if ep != self.epoch:
                continue
            self.busy_ns += sim.now - t0
            self.job_ns.setdefault(d['opcode'], []).append(sim.now - t0)
            self.st['jobs'] += 1
            self.st['st_' + spec.enum_name['status'].get(cpl['status'], '?')] += 1
            self.meter.mark(d['tag'], 'post', sim.now)
            if not tail_first:
                r['CPL_TAIL'] = nxt
                self.mon.emit('hw', 'reg', reg='CPL_TAIL', val=nxt)
            self._irq()

    def _cpl(self, status, tag, length=0, csum=0, flags=0, aux=0):
        return {'status': status, 'flags': flags, 'length': length, 'checksum': csum, 'tag': tag, 'aux': aux}

    def _check(self, d):
        """Descriptor checks the HW does by itself. Returns a bad_desc code or 0."""
        r, c, B = self.r, self.spec.const, self.spec.enum['bad_desc']
        op, n = d['opcode'], d['count']
        E = self.spec.enum['opcode']
        if op not in (E.COMPRESS, E.DECOMPRESS):
            return B.OPCODE
        if not 1 <= n <= c.CHUNK_SLOTS:
            return B.COUNT
        if any(x >= r['POOL_CHUNKS'] for x in d['chunk'][:n]):
            return B.CHUNK_RANGE
        fpa = d['frame_pa']
        if fpa % c.PAGE_SIZE or not r['FRAME_BASE'] <= fpa < r['FRAME_BASE'] + r['FRAME_COUNT'] * c.PAGE_SIZE:
            return B.FRAME_RANGE
        room = min(c.PAGE_SIZE, n * c.CHUNK_SIZE)
        if op == E.COMPRESS:
            if not 0 < d['limit'] <= room:
                return B.LENGTH
        else:
            L = d['comp_len']
            if not 0 < L <= room or (d['flags'] & self.spec.enum['flag'].RAW and L != c.PAGE_SIZE):
                return B.LENGTH
        return 0

    def _bursts(self, pa, n):
        b = self.p.burst_bytes
        return [(pa + o, min(b, n - o)) for o in range(0, n, b)]

    def _execute(self, d, ep):
        sim, p, r = self.sim, self.p, self.r
        c, S, F = self.spec.const, self.spec.enum['status'], self.spec.enum['flag']
        PAGE, CHUNK = c.PAGE_SIZE, c.CHUNK_SIZE
        tag = d['tag']
        yield sim.timeout(p.hw_overhead_ns)
        aux = self._check(d)
        if aux:
            self.st['bad_desc'] += 1
            return self._cpl(S.BAD_DESC, tag, aux=aux)
        t0 = sim.now
        chunks = d['chunk'][:d['count']]
        view = self.dram.view
        cpa = lambda i: r['POOL_BASE'] + chunks[i] * CHUNK
        fpa = d['frame_pa']
        ins, outs = [], []
        if d['opcode'] == self.spec.enum['opcode'].COMPRESS:
            # The frame cannot change during the job (its PTE is invalid), so the result is
            # computed from a snapshot now and only the bus traffic is spread over time.
            page = bytes(view(fpa, PAGE))
            blob, raw, status = compress(page), False, S.OK
            if len(blob) > d['limit'] or len(blob) >= PAGE:   # a stream of a whole page or more saves nothing
                if d['limit'] >= PAGE:
                    blob, raw = page, True
                else:
                    blob, status = blob[:d['limit']], S.INCOMPRESSIBLE
            ins = self._bursts(fpa, PAGE)
            data = blob
            if self._m('bad_data'):
                data = bytes([blob[0] ^ 0xFF]) + blob[1:]
            for i in range(ceil(len(data) / CHUNK)):
                piece = data[i * CHUNK:(i + 1) * CHUNK]
                outs += [(pa, piece[pa - cpa(i):pa - cpa(i) + n]) for pa, n in self._bursts(cpa(i), len(piece))]
            if self._m('stray_write'):
                outs.append((r['POOL_BASE'] + ((chunks[-1] + 1) % r['POOL_CHUNKS']) * CHUNK, bytes(8)))
            core = p.cycles_ns(PAGE / p.comp_bytes_per_cycle)
            if status == S.OK:
                cpl = self._cpl(S.OK, tag, len(blob), checksum(blob), F.RAW if raw else 0)
            else:
                cpl = self._cpl(status, tag)
        else:
            L = d['comp_len']
            m = ceil(L / CHUNK)
            stream = b''.join(bytes(view(cpa(i), CHUNK)) for i in range(m))[:L]
            page = None
            if checksum(stream) == d['checksum']:
                page = stream if d['flags'] & F.RAW else decompress(stream, PAGE)
            for i in range(m):
                ins += self._bursts(cpa(i), min(CHUNK, L - i * CHUNK))
            core = p.cycles_ns(PAGE / p.decomp_bytes_per_cycle)
            if page is not None:
                if self._m('decomp_bad'):
                    page = bytes([page[0] ^ 0xFF]) + page[1:]
                outs = [(pa, page[pa - fpa:pa - fpa + n]) for pa, n in self._bursts(fpa, PAGE)]
                cpl = self._cpl(S.OK, tag, PAGE, d['checksum'], d['flags'] & F.RAW)
            else:
                self.st['bad_stream'] += 1
                cpl = self._cpl(S.BAD_STREAM, tag)
        pin = sim.process(self._dma_in(ins, ep))
        pout = sim.process(self._dma_out(outs, t0, core, pin, ep))
        yield pin
        yield pout
        left = t0 + core - sim.now
        if left > 0:
            yield sim.timeout(left)
        return cpl

    def _dma_in(self, bursts, ep):
        for pa, n in bursts:
            yield from self.bus.xfer('hw', pa, n)
            if ep != self.epoch:
                return

    def _dma_out(self, bursts, t0, core, pin, ep):
        """Output burst k of nb can leave once the core has produced it; the last one also waits for the input."""
        sim, nb = self.sim, len(bursts)
        for k, (pa, data) in enumerate(bursts):
            avail = t0 + core * (k + 1) // nb
            if sim.now < avail:
                yield sim.timeout(avail - sim.now)
            if k == nb - 1 and not pin.done:
                yield pin
            if ep != self.epoch:
                return
            yield from self.bus.xfer('hw', pa, len(data), data)

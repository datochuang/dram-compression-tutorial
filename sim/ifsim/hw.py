"""LZ4 HW model: registers, job ring consumer, staged job execution, completion ring producer.

Stateless between jobs: everything a job needs is in its 48 B descriptor. The HW
never reads the COT. Timing is per stage, not per clock: descriptor fetch, input
DMA, the LZ4 core and output DMA overlap the way a streaming pipeline does, each
DMA burst goes through the Bus.

There are p.engines engines (CAP.ENGINES), each a copy of the same datapath, so
up to that many jobs run at once. What exists once is shared by them:
  - the job ring: one descriptor is fetched at a time, in ring order, and only
    when an engine is idle; the job goes to the lowest-numbered idle engine;
  - the completion ring: one completion is written at a time, in the order the
    jobs finished, so not always the order they were fetched in;
  - the DRAM master port: one read burst and one write burst at a time (_Arb).
An engine holds its job from the fetch until its completion is posted.

`mut` holds deliberate bugs for the checker tests: {name: ordinal of the job}.
"""
from bisect import insort
from collections import Counter
from itertools import count
from math import ceil

from lz4sim.codec import compress, decompress, checksum
from lz4sim.dram import BusError


RING = 'ring'          # the requester of a descriptor fetch or a completion write
_DROPPED = object()    # a burst that was never issued


class _Arb:
    """One channel of the DRAM master port, shared by the ring logic and the engines (lz4_arb).

    One burst at a time and no hand-over inside a burst. A ring burst goes before
    any engine; the engines take turns. Each requester has at most one burst
    waiting. A requester that finds the channel free gets it without an event,
    so one engine alone never waits here.
    """

    def __init__(self, sim, n):
        self.sim, self.n = sim, n
        self.owner = None
        self.req = {}              # requester -> (event, time of the request)
        self.last = n - 1          # engine served last
        self.bursts = 0
        self.waited = 0
        self.wait_ns = 0

    def _grant(self, who):
        self.owner = who
        self.bursts += 1
        if who is not RING:
            self.last = who

    def take(self, who):
        """None when the channel is granted at once, otherwise the event that fires at the grant."""
        if self.owner is None:
            self._grant(who)
            return None
        ev = self.sim.event()
        self.req[who] = (ev, self.sim.now)
        return ev

    def give(self):
        self.owner = None
        if not self.req:
            return
        who = RING if RING in self.req else min(self.req, key=lambda k: (k - self.last - 1) % self.n)
        ev, t = self.req.pop(who)
        self._grant(who)
        self.waited += 1
        self.wait_ns += self.sim.now - t
        ev.succeed()


class Lz4Hw:
    def __init__(self, sim, spec, p, bus, mon, irq, dram, meter):
        self.sim, self.spec, self.p = sim, spec, p
        self.bus, self.mon, self.irq, self.dram, self.meter = bus, mon, irq, dram, meter
        self.n = n = p.engines
        lsb, mask = spec.mask['CAP', 'ENGINES']
        if not 1 <= n <= mask >> lsb:
            raise ValueError(f'engines must be 1 to {mask >> lsb}')
        self.r = {reg['name']: reg['reset'] for reg in spec.registers}
        self.r['CAP'] = (self.r['CAP'] & ~mask) | (n << lsb)      # a build parameter of this instance
        self.epoch = 0
        self.resetting = False
        self.halted = False
        self.stopped = False                  # halted with RING_BUS_ERROR: the rings are not touched again
        self.error = False
        self._wait = None
        self.active = [False] * n             # engine holds a job: from the fetch to the completion posted
        self.cur = {}                         # engine -> descriptor of its job
        self.seq = {}                         # engine -> ordinal of its job, as fetched
        self.fetching = False                 # a descriptor fetch is on its way
        self.posting = False                  # a completion write is on its way
        self.done = []                        # (finish time, engine) of the jobs waiting to post
        self.quiet = set()                    # engines that have stopped after a soft reset
        self._wrapping = False
        self.arb = (_Arb(sim, n), _Arb(sim, n))      # read channel, write channel
        self.fetched = 0
        self.busy_ns = 0                      # summed over the engines
        self.conc_ns = Counter()              # engines holding a job -> time spent like that
        self.peak = 0
        self._ct = 0
        self.st = Counter()
        self.job_ns = {1: [], 2: []}          # opcode -> fetch to completion posted
        self.hang = set(p.hw_hang_jobs)
        self.mut = {}
        self.EN = spec.bit('CTRL', 'ENABLE')
        self.RST = spec.bit('CTRL', 'SOFT_RESET')
        for e in range(n):
            sim.process(self._engine(e), f'lz4hw{e}')

    @property
    def busy(self):
        """STATUS.BUSY without the reset part: some job is between its fetch and its completion."""
        return any(self.active)

    def _set(self, e, on):
        if self.active[e] == on:
            return
        now, k = self.sim.now, sum(self.active)
        self.conc_ns[k] += now - self._ct
        self._ct = now
        self.active[e] = on
        if on and k + 1 > self.peak:
            self.peak = k + 1

    def conc(self):
        """Time spent with k engines holding a job, k from 0 to n, up to now."""
        c = Counter(self.conc_ns)
        c[sum(self.active)] += self.sim.now - self._ct
        return [c[k] for k in range(self.n + 1)]

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
        if code == self.spec.enum['halt_code'].RING_BUS_ERROR:
            self.stopped = True               # jobs in flight end without a completion
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
        self.stopped = False
        self.error = False
        self.resetting = True
        self.fetching = self.posting = False
        self.done.clear()
        self.st['resets'] += 1
        self._irq()
        self.mon.emit('hw', 'reset')
        self._kick()

    def _new_wait(self):
        """The event of the next _kick. Every engine that waits shares it."""
        if self._wait is None or self._wait.done:
            self._wait = self.sim.event()
        return self._wait

    def _kick(self):
        w = self._wait
        if w is not None and not w.done:
            w.succeed()

    def _xfer(self, who, ep, pa, n, data=None):
        """One burst through the shared master port: wait for the channel, then the Bus.

        A burst still waiting for its turn when its job is given up (soft reset, or
        a halt that stops the rings) is not issued; _DROPPED comes back instead.
        """
        arb = self.arb[data is not None]
        ev = arb.take(who)
        if ev is not None:
            yield ev
            if ep != self.epoch or self.stopped:
                arb.give()
                return _DROPPED
        try:
            return (yield from self.bus.xfer('hw', pa, n, data))
        finally:
            arb.give()

    # ---- one engine: one job at a time. Fetching and posting are taken in turn with the other engines
    def _engine(self, e):
        sim, r, p, spec = self.sim, self.r, self.p, self.spec
        JS, CS = spec.const.JOB_SLOT_SIZE, spec.const.CPL_SLOT_SIZE
        DS = spec.size('job_desc')
        H = spec.enum['halt_code']
        while True:
            self._set(e, False)
            self.cur.pop(e, None)
            self.seq.pop(e, None)
            if self.resetting:
                self.quiet.add(e)
                if len(self.quiet) < self.n or self._wrapping:
                    yield self._new_wait()
                    continue
                self._wrapping = True                         # the last engine to stop does the wrap-up
                yield sim.timeout(p.reset_ns)
                self._wrapping = False
                self.resetting = False
                self.quiet.clear()
                self._kick()
                continue
            if (not r['CTRL'] & self.EN or self.halted or r['JOB_HEAD'] == r['JOB_TAIL']
                    or self.fetching or not all(self.active[:e])):
                yield self._new_wait()                        # nothing to take, or it is another engine's turn
                continue
            self._set(e, True)
            self.fetching = True
            ep, t0 = self.epoch, sim.now
            head = r['JOB_HEAD']
            try:
                raw = yield from self._xfer(RING, ep, r['JOB_BASE'] + head * JS, DS)
            except BusError:
                self.fetching = False
                self._halt(H.RING_BUS_ERROR)
                continue
            if ep != self.epoch:
                continue
            if raw is _DROPPED:
                self.fetching = False
                continue
            self.fetched += 1
            nth = self.fetched
            r['JOB_HEAD'] = (head + 1) & (r['JOB_SIZE'] - 1)
            self.mon.emit('hw', 'reg', reg='JOB_HEAD', val=r['JOB_HEAD'])
            d = spec.unpack('job_desc', raw)
            self.cur[e], self.seq[e] = d, nth
            if self._m('reread'):
                yield from self._xfer(RING, ep, r['JOB_BASE'] + head * JS, DS)
                if ep != self.epoch:
                    continue
            self.fetching = False
            self._kick()                                      # the next job can go to another engine
            self.meter.mark(d['tag'], 'fetch', t0)
            if nth in self.hang:                              # fault injection: this job never finishes
                self.st['hung'] += 1
                while ep == self.epoch:
                    yield self._new_wait()
                continue
            cpl = yield from self._execute(e, d, ep)
            if ep != self.epoch:
                continue
            if self._m('wrong_tag'):
                cpl['tag'] ^= 0x8000
            # Jobs post in the order they finished. Two that finish in the same ns and both have to
            # wait go by engine number; if the way is free the first to get here goes.
            insort(self.done, (sim.now, e))
            stalled = False
            while ep == self.epoch:
                mine = not self.posting and not self.stopped and self.done[0][1] == e
                if mine and ((r['CPL_TAIL'] + 1) & (r['CPL_SIZE'] - 1)) != r['CPL_HEAD']:
                    break
                if mine and not stalled:
                    stalled = True
                    self.st['cpl_stall'] += 1                 # completion ring full: wait for the FW
                yield self._new_wait()
            if ep != self.epoch:
                continue
            self.done.pop(0)
            self.posting = True
            tail = r['CPL_TAIL']
            nxt = (tail + 1) & (r['CPL_SIZE'] - 1)
            tail_first = self._m('tail_first')
            if tail_first:
                r['CPL_TAIL'] = nxt
                self.mon.emit('hw', 'reg', reg='CPL_TAIL', val=nxt)
            try:
                x = yield from self._xfer(RING, ep, r['CPL_BASE'] + tail * CS, CS, spec.pack('completion', cpl))
            except BusError:
                self.posting = False
                self._halt(H.RING_BUS_ERROR)
                x = _DROPPED
            if ep != self.epoch:
                continue
            if x is _DROPPED:                                 # the rings are stopped: hold the job until the reset
                self.posting = False
                while ep == self.epoch:
                    yield self._new_wait()
                continue
            self.busy_ns += sim.now - t0
            self.job_ns.setdefault(d['opcode'], []).append(sim.now - t0)
            self.st['jobs'] += 1
            if any(x < nth for x in self.seq.values()):       # a job fetched earlier is still in the HW
                self.st['overtook'] += 1
            self.st['st_' + spec.enum_name['status'].get(cpl['status'], '?')] += 1
            self.meter.mark(d['tag'], 'post', sim.now)
            if not tail_first:
                r['CPL_TAIL'] = nxt
                self.mon.emit('hw', 'reg', reg='CPL_TAIL', val=nxt)
            self.posting = False
            self._irq()
            self._kick()                                      # the next finished job can post

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

    def _execute(self, e, d, ep):
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
                outs.append((None, bytes(8)))                 # where it goes is picked when it is issued
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
        pin = sim.process(self._dma_in(e, ins, ep))
        pout = sim.process(self._dma_out(e, outs, t0, core, pin, ep))
        yield pin
        yield pout
        left = t0 + core - sim.now
        if left > 0:
            yield sim.timeout(left)
        return cpl

    def _dma_in(self, e, bursts, ep):
        for pa, n in bursts:
            yield from self._xfer(e, ep, pa, n)
            if ep != self.epoch or self.stopped:
                return

    def _dma_out(self, e, bursts, t0, core, pin, ep):
        """Output burst k of nb can leave once the core has produced it; the last one also waits for the input."""
        sim, nb = self.sim, len(bursts)
        for k, (pa, data) in enumerate(bursts):
            avail = t0 + core * (k + 1) // nb
            if sim.now < avail:
                yield sim.timeout(avail - sim.now)
            if k == nb - 1 and not pin.done:
                yield pin
            if ep != self.epoch or self.stopped:
                return
            if pa is None:
                pa = self._stray(e)
            yield from self._xfer(e, ep, pa, len(data), data)

    def _stray(self, e):
        """Planted bug stray_write: the address of a chunk that no job in the HW lists, away from the newest ones."""
        r, CHUNK = self.r, self.spec.const.CHUNK_SIZE
        held = {x for d in self.cur.values() for x in d['chunk'][:d['count']]}
        first = self.cur[e]['chunk'][0] + r['POOL_CHUNKS'] // 2
        ch = next(x for x in ((first + k) % r['POOL_CHUNKS'] for k in count()) if x not in held)
        return r['POOL_BASE'] + ch * CHUNK

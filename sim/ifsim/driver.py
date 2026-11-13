"""FW driver for the LZ4 HW: ring set-up, job submission, completion handling, timeout and reset.

Written only against Platform and Ctx. `submit` is what the page manager calls;
it returns when the completion of that job has been read.

`mut` holds deliberate bugs for the checker tests: {name: ordinal of the submit}.
"""
from collections import Counter, OrderedDict

from .des import Resource
from .platform import Ctx


class Job:
    __slots__ = ('tag', 'h', 'op', 'raw', 'cpl', 'ev', 't_bell')

    def __init__(self, tag, h, op, raw, ev):
        self.tag, self.h, self.op, self.raw, self.ev = tag, h, op, raw, ev
        self.cpl = None
        self.t_bell = 0


class Driver:
    def __init__(self, sim, spec, cfg, p, plat, mon, irq, meter, ring_base):
        self.sim, self.spec, self.cfg, self.p = sim, spec, cfg, p
        self.plat, self.mon, self.meter = plat, mon, meter
        self.mode = p.wait_mode
        if self.mode not in ('irq', 'poll'):
            raise ValueError("wait_mode must be 'irq' or 'poll'")
        self.JS, self.CS = spec.const.JOB_SLOT_SIZE, spec.const.CPL_SLOT_SIZE
        self.job_base = ring_base
        self.cpl_base = ring_base + p.job_entries * self.JS
        self.ring_end = self.cpl_base + p.cpl_entries * self.CS
        self.jmask, self.cmask = p.job_entries - 1, p.cpl_entries - 1
        self.tail = 0                  # next job slot to fill
        self.head = 0                  # next completion slot to read
        self.pending = OrderedDict()   # tag -> Job, in doorbell order
        self.depth = min(p.job_entries, p.cpl_entries) - 1
        self.slots = Resource(sim, 'job_slots', self.depth)
        self.lock = Resource(sim, 'ring_lock')
        self.irq_ctx = Ctx(sim, 'irq')
        self.next_tag = 1
        self.submits = 0
        self.st = Counter()
        self.occ = Counter()           # outstanding jobs seen at each doorbell
        self.mut = {}
        self.after_bell = None         # test hook: called once right after the next doorbell
        self.EN = spec.bit('CTRL', 'ENABLE')
        self.RST = spec.bit('CTRL', 'SOFT_RESET')
        self.BUSY = spec.bit('STATUS', 'BUSY')
        self.DONE = spec.bit('IRQ_STATUS', 'DONE')
        self.ERROR = spec.bit('IRQ_STATUS', 'ERROR')
        irq.handler = self._irq_handler

    def _m(self, name):
        """True once, at the first place that asks from submit ordinal mut[name] on."""
        n = self.mut.get(name)
        if n is None or self.submits < n:
            return False
        del self.mut[name]
        return True

    # ---- bring-up
    def init(self, ctx):
        plat, cfg, p = self.plat, self.cfg, self.p
        ident = yield from plat.reg_read(ctx, 'ID')
        if ident != self.spec.const.ID_VALUE:
            raise RuntimeError(f'unexpected ID {ident:#x}')
        for name, val in (('JOB_BASE', self.job_base), ('JOB_SIZE', p.job_entries),
                          ('CPL_BASE', self.cpl_base), ('CPL_SIZE', p.cpl_entries),
                          ('POOL_BASE', cfg.pool_base), ('POOL_CHUNKS', cfg.pool_chunks),
                          ('FRAME_BASE', cfg.fc_base), ('FRAME_COUNT', cfg.frames)):
            yield from plat.reg_write(ctx, name, val)
        yield from plat.reg_write(ctx, 'IRQ_ENABLE', self.DONE | self.ERROR if self.mode == 'irq' else 0)
        yield from plat.reg_write(ctx, 'CTRL', self.EN)

    # ---- one job
    def submit(self, ctx, desc, h):
        """Queue one job and wait for its completion. Returns (completion, timing)."""
        sim, p, plat = self.sim, self.p, self.plat
        t_sub = sim.now
        if self.slots.users >= self.slots.cap:
            self.st['ring_full_waits'] += 1
        yield from ctx.block(self.slots.acquire())
        yield self.lock.acquire()
        self.submits += 1
        tag = self.next_tag
        self.next_tag = (tag + 1) & 0xFFFFFFFF or 1
        if self.pending and self._m('dup_tag'):
            tag = next(iter(self.pending))
        desc['tag'] = tag
        job = Job(tag, h, desc['opcode'], self.spec.pack('job_desc', desc), sim.event())
        self.pending[tag] = job
        self.mon.emit('fw', 'job', tag=tag, h=h, op=job.op)
        slot_pa = self.job_base + self.tail * self.JS
        nxt = (self.tail + 1) & self.jmask
        bell_first = self._m('bell_first')
        if bell_first:
            yield from plat.reg_write(ctx, 'JOB_TAIL', nxt)
        yield from plat.mem_write(ctx, slot_pa, job.raw, p.desc_write_ns, 'job_slot')
        self.tail = nxt
        if not bell_first:
            yield from plat.reg_write(ctx, 'JOB_TAIL', nxt)
        if len(self.pending) > p.engines and self._m('slot_rewrite'):     # every engine is on an earlier job
            yield from plat.mem_write(ctx, slot_pa, job.raw, p.desc_write_ns, 'job_slot')
        if self._m('cfg_live'):
            yield from plat.reg_write(ctx, 'JOB_SIZE', p.job_entries)
        job.t_bell = sim.now
        self.occ[len(self.pending)] += 1
        hook, self.after_bell = self.after_bell, None
        if hook:
            hook(job)
        self.lock.release()
        cpl = yield from self._wait(ctx, job)
        self.slots.release()
        m = self.meter.pop(tag)
        fetch, post = m.get('fetch', job.t_bell), m.get('post', sim.now)
        timing = {'submit': job.t_bell - t_sub, 'queue': fetch - job.t_bell, 'hw': post - fetch, 'notify': sim.now - post}
        return cpl, timing

    def _wait(self, ctx, job):
        sim, p = self.sim, self.p
        if self.mode == 'irq':
            while not job.ev.done:
                yield from ctx.block(sim.any_of(job.ev, sim.timeout(p.job_timeout_ns)))
                if job.cpl is None and sim.now - job.t_bell >= p.job_timeout_ns:
                    yield from self._on_timeout(ctx, job)
        else:
            while job.cpl is None:
                yield ctx.cpu(p.poll_interval_ns)          # busy wait: the core stays taken
                self.st['poll_spins'] += 1
                if job.cpl is not None:
                    break
                if sim.now - job.t_bell >= p.job_timeout_ns:
                    yield from self._on_timeout(ctx, job)
                else:
                    yield from self._drain(ctx, job)
        return job.cpl

    # ---- completions
    def _drain(self, ctx, own=None):
        yield self.lock.acquire()
        n = yield from self._drain_locked(ctx, own)
        self.lock.release()
        return n

    def _drain_locked(self, ctx, own=None):
        sim, p, plat = self.sim, self.p, self.plat
        tail = yield from plat.reg_read(ctx, 'CPL_TAIL')
        n = 0
        while self.head != tail:
            raw = yield from plat.mem_read(ctx, self.cpl_base + self.head * self.CS, self.CS, p.cpl_read_ns, 'cpl_slot')
            c = self.spec.unpack('completion', raw)
            self.head = (self.head + 1) & self.cmask
            n += 1
            job = self.pending.pop(c['tag'], None)          # FW-CPL-2: match by tag
            if job is None:
                self.st['stray_cpl'] += 1
                continue
            job.cpl = c
            self.st['completions'] += 1
            if self.mode == 'irq' and job is not own:
                sim.timeout(p.wakeup_ns).then(lambda e, j=job, c=c: j.ev.succeed(c))   # wake the sleeping thread
            else:
                job.ev.succeed(c)
        if n:
            self.st['drains'] += 1
            head = self.head
            if self._m('head_ahead'):
                head = (head + 1) & self.cmask
            yield from plat.reg_write(ctx, 'CPL_HEAD', head)
        return n

    def _irq_handler(self):
        ctx, plat = self.irq_ctx, self.plat
        self.st['irqs'] += 1
        yield ctx.cpu(self.p.irq_handler_ns)
        st = yield from plat.reg_read(ctx, 'IRQ_STATUS')
        if st & self.ERROR:
            self.st['error_irqs'] += 1
            yield from plat.reg_write(ctx, 'IRQ_STATUS', self.ERROR)
            yield self.lock.acquire()
            yield from self._recover_locked(ctx)
            self.lock.release()
        elif st & self.DONE:
            yield from self._drain(ctx)

    # ---- timeout and reset (FW-RST-1)
    def _on_timeout(self, ctx, job):
        sim, p = self.sim, self.p
        yield self.lock.acquire()
        if job.cpl is None and sim.now - job.t_bell >= p.job_timeout_ns:
            self.st['timeouts'] += 1
            yield from self._drain_locked(ctx, job)         # first look: was the interrupt missed?
            if job.cpl is not None:
                self.st['late_completions'] += 1
            else:
                yield from self._recover_locked(ctx)
        self.lock.release()

    def _recover_locked(self, ctx):
        sim, p, plat = self.sim, self.p, self.plat
        self.st['resets'] += 1
        yield from plat.reg_write(ctx, 'CTRL', self.RST)
        while (yield from plat.reg_read(ctx, 'STATUS')) & self.BUSY:
            yield ctx.cpu(p.poll_interval_ns)
        self.tail = self.head = 0
        yield from plat.reg_write(ctx, 'CTRL', self.EN)
        for job in self.pending.values():                   # jobs are idempotent: send them all again
            self.mon.emit('fw', 'job', tag=job.tag, h=job.h, op=job.op)
            yield from plat.mem_write(ctx, self.job_base + self.tail * self.JS, job.raw, p.desc_write_ns, 'job_slot')
            self.tail += 1
            self.st['reissued'] += 1
        if self.pending:
            yield from plat.reg_write(ctx, 'JOB_TAIL', self.tail)
        for job in self.pending.values():
            job.t_bell = sim.now

"""Checkers beside the design: interface protocol, memory-management rules, data scoreboard, audit.

The checker subscribes to the Monitor and keeps its OWN picture of the rings,
the jobs, the PTEs and the COT, built only from boundary events and from DRAM
contents. It never reads the internal state of the FW model or the HW model
while running (the end-of-run audit does, on purpose). Every rule it evaluates
is one of the rule ids in interface.json; `cov` counts evaluations, `viol`
keeps the failures. With strict=True the first failure raises Violation.

The HW runs up to CAP.ENGINES jobs at once, so `inhw` is a set of jobs, not one
job. A burst carries no engine number (one master port, one ID), so HW-MEM-1
can only ask that a burst lies inside SOME job the HW holds. An engine that
writes into the range of another engine's job passes HW-MEM-1; only the data
scoreboard can catch that, at the completion of the job that was hit.
"""
from collections import Counter, defaultdict, deque
from math import ceil

from lz4sim.codec import checksum, decompress
from lz4sim.kernel import S_COMPRESSED, S_PRESENT, S_UNTOUCHED, S_LOST, S_NAME


class Violation(Exception):
    def __init__(self, rule, msg, t=0):
        super().__init__(f'{rule} at {t} ns: {msg}')
        self.rule, self.msg, self.t = rule, msg, t


class _Job:
    __slots__ = ('tag', 'h', 'd', 'op', 'frame', 'chunks', 'rd', 'wr', 'snap', 'cpl')


class Checker:
    KEEP = 20          # failures kept per rule

    def __init__(self, system, strict=False):
        s = system
        self.sys = s
        self.spec, self.cfg, self.dram, self.expect, self.sim = s.spec, s.cfg, s.dram, s.expect, s.sim
        self.strict = strict
        self.cov = Counter()
        self.viol = defaultdict(list)
        self.nviol = Counter()
        c = self.spec.const
        self.PAGE, self.CHUNK, self.JS, self.CS = c.PAGE_SIZE, c.CHUNK_SIZE, c.JOB_SLOT_SIZE, c.CPL_SLOT_SIZE
        self.DS, self.ES = self.spec.size('job_desc'), self.spec.size('cot_entry')
        self.OP, self.ST, self.FL = self.spec.enum['opcode'], self.spec.enum['status'], self.spec.enum['flag']
        self.EN, self.RST = self.spec.bit('CTRL', 'ENABLE'), self.spec.bit('CTRL', 'SOFT_RESET')
        self.reg = {r['name']: r['reset'] for r in self.spec.registers}
        self.reg['CAP'] = s.hw.mmio_read(self.spec.off['CAP'])      # what the FW would read from this HW instance
        self.engines = self.spec.get('CAP', 'ENGINES', self.reg['CAP'])
        self.enabled = False
        self.error = False
        self.irq_level = 0
        self._clear_rings()
        self.limbo = {}                 # tag -> job dropped by a soft reset, waiting to be sent again
        self.grace = None               # (jobs, slot) the HW may still finish a burst of after a reset
        self.tag_h = {}                 # probe: tag -> page
        self.frame_page = {}            # frame pa -> page with a valid PTE
        self.page_frame = {}
        self.frame_job, self.chunk_job, self.page_job = {}, {}, {}
        self.last_job = {}              # page -> (op, status, job) of the last completion posted
        self.corrupted = set()          # pages hit by the fault injector
        self.cot = {}                   # page -> valid COT entry
        self.chunk_owner = {}
        cfg = self.cfg
        self.cot_lo, self.cot_hi = cfg.cot_base, cfg.cot_base + cfg.pages * self.ES
        for h in range(cfg.pages):
            e = self._entry(h)
            if e:
                self.cot[h] = e
                for ch in e['chunk']:
                    self.chunk_owner[ch] = h
        s.mon.subs.append(self.on)
        self._on = {('fw', 'mmio_w'): self._fw_mmio_w, ('fw', 'mem_w'): self._fw_mem_w, ('fw', 'job'): self._fw_job,
                    ('fw', 'pte'): self._fw_pte, ('hw', 'reg'): self._hw_reg, ('hw', 'mem_r'): self._hw_mem_r,
                    ('hw', 'mem_w'): self._hw_mem_w, ('hw', 'halt'): self._hw_halt, ('env', 'inject'): self._inject}

    # ---- plumbing
    def _clear_rings(self):
        self.job_tail = self.job_head = self.cpl_tail = self.cpl_head = 0
        self.slot_written = set()       # job slots holding a full descriptor not yet handed over
        self.slot_owned = set()         # job slots between doorbell and JOB_HEAD passing them
        self.slot_read = False          # the HW has read the slot at JOB_HEAD
        self.cpl_written = False        # the HW has written the slot at CPL_TAIL
        self.queued, self.inhw, self.posted = deque(), [], deque()    # inhw: fetched, no completion yet
        self.tags = set()

    def fail(self, rule, msg):
        self.nviol[rule] += 1
        if len(self.viol[rule]) < self.KEEP:
            self.viol[rule].append((self.sim.now, msg))
        if self.strict:
            raise Violation(rule, msg, self.sim.now)

    def chk(self, rule, ok, msg):
        self.cov[rule] += 1
        if not ok:
            self.fail(rule, msg() if callable(msg) else msg)
        return ok

    def _entry(self, h):
        """The COT entry of page h as it is in DRAM now, None when not valid."""
        e = self.spec.unpack('cot_entry', self.dram.view(self.cfg.entry_pa(h), self.ES))
        if not e['flags'] & self.FL.VALID:
            return None
        e['chunk'] = e['chunk'][:e['count']]
        return e

    def _irq_expected(self):
        en = self.reg['IRQ_ENABLE']
        return int(bool((self.cpl_tail != self.cpl_head and en & 1) or (self.error and en & 2)))

    def on(self, t, src, ev, kw):
        if src == 'hw' and ev == 'irq':
            self.irq_level = kw['level']
            return
        # HW-IRQ-1 is looked at one event late: the line is updated right after the event that changes it.
        self.cov['HW-IRQ-1'] += 1
        if self.irq_level != self._irq_expected():
            self.fail('HW-IRQ-1', f'line is {self.irq_level}, expected {self._irq_expected()} before {src}.{ev}')
            self.irq_level = self._irq_expected()            # report once, not on every later event
        f = self._on.get((src, ev))
        if f:
            f(kw)

    # ---- FW side: registers
    def _fw_mmio_w(self, kw):
        name, val = kw['reg'], kw['val']
        reg = self.reg
        if name in self.spec.config_regs:
            if self.chk('FW-CFG-1', not self.enabled, f'{name} written while ENABLE is 1'):
                reg[name] = val
        elif name == 'CTRL':
            if val & self.RST:
                self._soft_reset()
            elif val & self.EN and not self.enabled:
                self._check_cfg()
                self.enabled = True
                self.grace = None
            elif not val & self.EN:
                self.enabled = False
        elif name == 'IRQ_ENABLE':
            reg[name] = val & 3
        elif name == 'IRQ_STATUS':
            if val & self.spec.bit('IRQ_STATUS', 'ERROR'):
                self.error = False
        elif name == 'JOB_TAIL':
            self._doorbell(val)
        elif name == 'CPL_HEAD':
            self._cpl_head(val)

    def _check_cfg(self):
        r, c = self.reg, self.spec.const
        top = 1 << self.spec.get('CAP', 'RING_SHIFT_MAX', r['CAP'])
        ok = all(2 <= n <= top and not n & (n - 1) for n in (r['JOB_SIZE'], r['CPL_SIZE']))
        # stricter than the HW check on CPL_BASE (one completion slot): FW-CACHE-5 wants whole cache lines
        ok = ok and not r['JOB_BASE'] % c.RING_ALIGN and not r['CPL_BASE'] % c.RING_ALIGN
        if ok:
            rings = ((r['JOB_BASE'], r['JOB_BASE'] + r['JOB_SIZE'] * self.JS),
                     (r['CPL_BASE'], r['CPL_BASE'] + r['CPL_SIZE'] * self.CS))
            areas = ((r['POOL_BASE'], r['POOL_BASE'] + r['POOL_CHUNKS'] * self.CHUNK),
                     (r['FRAME_BASE'], r['FRAME_BASE'] + r['FRAME_COUNT'] * self.PAGE))
            ok = all(a1 <= b0 or b1 <= a0 for a0, a1 in rings for b0, b1 in areas)
            ok = ok and (rings[0][1] <= rings[1][0] or rings[1][1] <= rings[0][0])
        self.chk('FW-CFG-2', ok, 'ring configuration is not legal at ENABLE')

    def _soft_reset(self):
        self.grace = (list(self.inhw), self.job_head)
        for j in list(self.queued) + list(self.inhw) + list(self.posted):
            self.limbo[j.tag] = j
        self._clear_rings()
        self.enabled = False
        self.error = False
        for name in ('JOB_HEAD', 'JOB_TAIL', 'CPL_TAIL', 'CPL_HEAD', 'ERR_CODE'):
            self.reg[name] = 0

    def _release(self, j):
        if self.frame_job.get(j.frame) is j:
            del self.frame_job[j.frame]
        for ch in j.chunks:
            if self.chunk_job.get(ch) is j:
                del self.chunk_job[ch]
        if self.page_job.get(j.h) is j:
            del self.page_job[j.h]

    # ---- FW side: job ring
    def _doorbell(self, val):
        size = self.reg['JOB_SIZE']
        if not self.chk('FW-JOB-2', val < size, f'JOB_TAIL {val} is not below JOB_SIZE {size}'):
            return
        added = (val - self.job_tail) % size
        held = (self.job_tail - self.job_head) % size
        if not self.chk('FW-JOB-2', held + added <= size - 1,
                        f'JOB_TAIL {self.job_tail} to {val} with JOB_HEAD {self.job_head}: goes back or overruns'):
            return
        for i in range(added):
            idx = (self.job_tail + i) % size
            self.chk('FW-JOB-1', idx in self.slot_written, f'slot {idx} handed over before its descriptor was written')
            self.slot_written.discard(idx)
            self.slot_owned.add(idx)
            self._new_job(idx)
        self.job_tail = val

    def _new_job(self, idx):
        spec, r = self.spec, self.reg
        d = spec.unpack('job_desc', self.dram.view(r['JOB_BASE'] + idx * self.JS, self.DS))
        j = _Job()
        j.tag, j.d, j.op, j.frame, j.cpl = d['tag'], d, d['opcode'], d['frame_pa'], None
        j.chunks = d['chunk'][:min(d['count'], len(d['chunk']))]
        j.h = h = self.tag_h.get(j.tag)
        old = self.limbo.pop(j.tag, None)
        if old is not None:
            self._release(old)
        self.chk('FW-JOB-5', j.tag not in self.tags, f'tag {j.tag:#x} is already in use')
        self.chk('FW-JOB-4', len(self.tags) + 1 <= r['CPL_SIZE'] - 1,
                 f'{len(self.tags) + 1} jobs without a consumed completion, CPL_SIZE is {r["CPL_SIZE"]}')
        self.tags.add(j.tag)
        self.queued.append(j)
        pool = r['POOL_BASE']
        cr = [(pool + ch * self.CHUNK, pool + (ch + 1) * self.CHUNK) for ch in j.chunks]
        fr = [(j.frame, j.frame + self.PAGE)]
        if j.op == self.OP.COMPRESS:
            j.rd, j.wr = fr, cr
        elif j.op == self.OP.DECOMPRESS:
            j.rd, j.wr = cr, fr
        else:
            j.rd = j.wr = []
        j.snap = None
        if h is None:                                   # not a page job (directed tests): protocol checks only
            return
        self.chk('FW-JOB-6', j.frame not in self.frame_job and not any(ch in self.chunk_job for ch in j.chunks)
                 and h not in self.page_job, f'page {h:#x}: frame or chunk already in an outstanding job')
        self.frame_job[j.frame] = j
        self.page_job[h] = j
        for ch in j.chunks:
            self.chunk_job[ch] = j
        self.chk('FW-MM-1', j.frame not in self.frame_page,
                 lambda: f'job on frame {j.frame:#x} while page {self.frame_page[j.frame]:#x} has a valid PTE to it')
        view = self.dram.view
        if j.op == self.OP.COMPRESS:
            self.chk('FW-MM-2', not any(ch in self.chunk_owner for ch in j.chunks),
                     lambda: f'page {h:#x}: COMPRESS lists a chunk owned by a valid COT entry')
            j.snap = bytes(view(j.frame, self.PAGE))
        elif j.op == self.OP.DECOMPRESS:
            e = self.cot.get(h)
            same = (e is not None and d['count'] == e['count'] and d['comp_len'] == e['comp_len']
                    and d['checksum'] == e['checksum'] and j.chunks == e['chunk']
                    and (d['flags'] & self.FL.RAW) == (e['flags'] & self.FL.RAW))
            self.chk('FW-MM-4', same, f'page {h:#x}: DECOMPRESS descriptor differs from the COT entry')
            n = min(d['comp_len'], len(j.chunks) * self.CHUNK)
            j.snap = b''.join(bytes(view(lo, self.CHUNK)) for lo, _ in cr)[:n]

    def _cpl_head(self, val):
        size = self.reg['CPL_SIZE']
        adv = (val - self.cpl_head) % size if val < size else size
        avail = (self.cpl_tail - self.cpl_head) % size
        if not self.chk('FW-CPL-1', adv <= avail,
                        f'CPL_HEAD {self.cpl_head} to {val} with CPL_TAIL {self.cpl_tail}: goes back or passes the tail'):
            return
        for _ in range(adv):
            self.tags.discard(self.posted.popleft().tag)
        self.cpl_head = val

    # ---- FW side: shared memory and probes
    def _fw_mem_w(self, kw):
        pa, n, r = kw['pa'], kw['n'], self.reg
        jb = r['JOB_BASE']
        if jb <= pa < jb + r['JOB_SIZE'] * self.JS:
            idx = (pa - jb) // self.JS
            self.chk('FW-JOB-3', idx not in self.slot_owned, f'slot {idx} rewritten while the HW owns it')
            if pa == jb + idx * self.JS and n >= self.DS:
                self.slot_written.add(idx)
        elif self.cot_lo <= pa < self.cot_hi:
            self._cot_write((pa - self.cot_lo) // self.ES)

    def _cot_write(self, h):
        cfg = self.cfg
        if not self.chk('FW-MM-7', not cfg.is_ro(h), f'COT entry of RO page {h:#x} written at run time'):
            return
        old = self.cot.pop(h, None)
        if old:
            for ch in old['chunk']:
                if self.chunk_owner.get(ch) == h:
                    del self.chunk_owner[ch]
        e = self._entry(h)
        if e is None:
            return
        lj = self.last_job.get(h)
        ok = lj is not None and lj[0] == self.OP.COMPRESS and lj[1] == self.ST.OK
        if ok:
            j = lj[2]
            used = ceil(j.cpl['length'] / self.CHUNK)
            ok = (e['comp_len'] == j.cpl['length'] and e['checksum'] == j.cpl['checksum'] and e['count'] == used
                  and (e['flags'] & self.FL.RAW) == (j.cpl['flags'] & self.FL.RAW) and e['chunk'] == j.chunks[:used]
                  and not e['flags'] & self.FL.RO)
        self.chk('FW-MM-3', ok, f'page {h:#x}: COT entry does not follow from a COMPRESS that returned OK')
        for ch in e['chunk']:
            if ch in self.chunk_owner:
                self.fail('AUDIT-1', f'chunk {ch:#x} given to page {h:#x} but owned by {self.chunk_owner[ch]:#x}')
            self.chunk_owner[ch] = h
        self.cot[h] = e

    def _fw_job(self, kw):
        self.tag_h[kw['tag']] = kw['h']

    def _fw_pte(self, kw):
        h, pa = kw['h'], kw['pa']
        if not kw['valid']:
            if self.frame_page.get(pa) == h:
                del self.frame_page[pa]
            self.page_frame.pop(h, None)
            self.last_job.pop(h, None)
            return
        if not kw.get('boot'):
            ro = self.cfg.is_ro(h)
            self.chk('FW-MM-5', h not in self.page_job and pa not in self.frame_job
                     and not any(j.h == h for j in self.limbo.values()) and pa not in self.frame_page,
                     f'page {h:#x}: PTE made valid while a job is outstanding or the frame is mapped elsewhere')
            lj = self.last_job.pop(h, None)
            if ro:
                ok = lj is not None and lj[0] == self.OP.DECOMPRESS and lj[1] == self.ST.OK
            else:
                ok = h not in self.cot and not (lj and lj[0] == self.OP.DECOMPRESS and lj[1] != self.ST.OK)
            self.chk('FW-MM-6', ok, f'page {h:#x}: PTE made valid without a good DECOMPRESS or with its COT entry still valid')
            self.chk('AUDIT-3', checksum(self.dram.view(pa, self.PAGE)) == self.expect[h],
                     f'page {h:#x} mapped with contents that differ from what user SW last wrote')
        self.frame_page[pa] = h
        self.page_frame[h] = pa

    def _inject(self, kw):
        self.corrupted.add(kw['h'])

    # ---- HW side
    def _hw_halt(self, kw):
        self.error = True

    def _in(self, ranges, pa, n):
        return any(lo <= pa and pa + n <= hi for lo, hi in ranges)

    def _held(self):
        """The jobs a HW burst may belong to: those in the HW, or after a reset those it was running."""
        return self.inhw or (self.grace[0] if self.grace else ())

    def _hw_mem_r(self, kw):
        pa, n, r = kw['pa'], kw['n'], self.reg
        jb = r['JOB_BASE']
        if jb <= pa < jb + r['JOB_SIZE'] * self.JS:
            idx = (pa - jb) // self.JS
            if self.grace and idx == self.grace[1] and not self.enabled:
                return                                   # the fetch burst that was on the bus at reset
            ok = idx == self.job_head and self.job_head != self.job_tail and not self.slot_read
            self.chk('HW-MEM-2', ok, f'descriptor slot {idx} read out of turn (JOB_HEAD {self.job_head})')
            if pa == jb + idx * self.JS and n >= self.DS:
                self.slot_read = True
            return
        self.chk('HW-MEM-1', any(self._in(j.rd, pa, n) for j in self._held()),
                 f'HW read {n} B at {pa:#x} outside the jobs it holds')

    def _hw_mem_w(self, kw):
        pa, n, r = kw['pa'], kw['n'], self.reg
        slot = r['CPL_BASE'] + self.cpl_tail * self.CS
        if pa == slot and n == self.CS and self.enabled:
            self.cov['HW-MEM-1'] += 1
            self.cpl_written = True
            return
        self.chk('HW-MEM-1', any(self._in(j.wr, pa, n) for j in self._held()),
                 f'HW wrote {n} B at {pa:#x} outside the jobs it holds')

    def _hw_reg(self, kw):
        name, val, r = kw['reg'], kw['val'], self.reg
        if name == 'JOB_HEAD':
            size = r['JOB_SIZE']
            ok = self.job_head != self.job_tail and val == (self.job_head + 1) % size
            if not self.chk('HW-MEM-2', ok and self.slot_read,
                            f'JOB_HEAD {self.job_head} to {val}: no job there or its descriptor was not read'):
                if not ok:
                    return
            self.chk('HW-MEM-2', len(self.inhw) < self.engines,
                     f'job fetched while the HW holds {len(self.inhw)} jobs, CAP.ENGINES is {self.engines}')
            self.slot_owned.discard(self.job_head)
            self.slot_read = False
            self.job_head = val
            self.grace = None
            if self.queued:
                self.inhw.append(self.queued.popleft())
        elif name == 'CPL_TAIL':
            self._posted(val)

    def _posted(self, val):
        r, size = self.reg, self.reg['CPL_SIZE']
        ok = val == (self.cpl_tail + 1) % size
        self.chk('HW-CPL-3', ok and val != self.cpl_head,
                 f'CPL_TAIL {self.cpl_tail} to {val} with CPL_HEAD {self.cpl_head}: the ring was full')
        self.chk('HW-CPL-2', self.cpl_written, 'CPL_TAIL advanced before the completion was written')
        self.cpl_written = False
        c = self.spec.unpack('completion', self.dram.view(r['CPL_BASE'] + self.cpl_tail * self.CS, self.CS))
        self.cpl_tail = val
        j = next((x for x in self.inhw if x.tag == c['tag']), None)
        if not self.chk('HW-CPL-1', j is not None,
                        lambda: f'completion with tag {c["tag"]:#x}, the HW holds '
                                + (', '.join(f'{x.tag:#x}' for x in self.inhw) or 'no job')):
            if not self.inhw:
                return
            j = self.inhw[0]                             # keep the ring picture going: take the oldest
        self.inhw.remove(j)
        j.cpl = c
        self.posted.append(j)
        self._release(j)
        if j.h is None:
            return
        self.last_job[j.h] = (j.op, c['status'], j)
        self._scoreboard(j, c)

    def _scoreboard(self, j, c):
        """Data checks at the moment the completion becomes visible."""
        view, d, ST = self.dram.view, j.d, self.ST
        if j.op == self.OP.COMPRESS and c['status'] == ST.OK:
            L = c['length']
            ok = 0 < L <= d['limit'] and L <= len(j.chunks) * self.CHUNK
            if ok:
                stream = b''.join(bytes(view(lo, self.CHUNK)) for lo, _ in j.wr)[:L]
                ok = checksum(stream) == c['checksum'] and bytes(view(j.frame, self.PAGE)) == j.snap
                if ok:
                    page = stream if c['flags'] & self.FL.RAW else decompress(stream, self.PAGE)
                    ok = page == j.snap
            self.chk('HW-DATA-1', ok, f'page {j.h:#x}: COMPRESS returned OK but the stored stream is not the page')
        elif j.op == self.OP.DECOMPRESS and j.snap is not None:
            good = checksum(j.snap) == d['checksum']
            page = None
            if good:
                page = j.snap if d['flags'] & self.FL.RAW else decompress(j.snap, self.PAGE)
            if c['status'] == ST.OK:
                self.chk('HW-DATA-2', page is not None and bytes(view(j.frame, self.PAGE)) == page,
                         f'page {j.h:#x}: DECOMPRESS returned OK but the frame is not the decoded stream')
            elif c['status'] == ST.BAD_STREAM:
                self.chk('HW-DATA-2', page is None, f'page {j.h:#x}: BAD_STREAM reported for a good stream')

    # ---- end of run
    def audit(self):
        """AUDIT-1..4 on the quiescent system. Looks inside the FW model on purpose."""
        s, cfg, view = self.sys, self.cfg, self.dram.view
        mm = s.mm
        # AUDIT-1: bitmap == union of the chunks of valid entries, no chunk shared
        owner, shared = {}, 0
        for h in range(cfg.pages):
            e = self._entry(h)
            for ch in (e['chunk'] if e else ()):
                shared += ch in owner
                owner[ch] = h
        free = mm.bitmap.enumerate_free()
        self.chk('AUDIT-1', not shared and not (owner.keys() & free) and len(owner) + len(free) == cfg.pool_chunks,
                 f'chunks: {len(owner)} owned, {len(free)} free, {cfg.pool_chunks} in the pool, {shared} shared')
        if owner != self.chunk_owner:
            raise AssertionError('checker error: its picture of the COT differs from the COT in DRAM')
        # AUDIT-2: every frame is free or belongs to exactly one present page
        used = {}
        bad = 0
        for h in range(cfg.pages):
            f = mm.frame_of[h]
            if mm.state[h] == S_PRESENT:
                bad += f < 0 or f in used or not mm.mapped[h]
                used[f] = h
            else:
                bad += f >= 0 or bool(mm.mapped[h])
        freef = set(mm.free_frames)
        self.chk('AUDIT-2', not bad and not (used.keys() & freef) and len(used) + len(freef) == cfg.frames
                 and len(freef) == len(mm.free_frames) and len(mm.lru) == len(used),
                 f'frames: {len(used)} in use, {len(freef)} free, {cfg.frames} in all, {bad} inconsistent pages')
        # AUDIT-3: every page still holds what user SW last wrote
        wrong = []
        counts = Counter()
        for h in range(cfg.pages):
            st = mm.state[h]
            counts[S_NAME[st]] += 1
            if st == S_PRESENT:
                ok = checksum(view(cfg.frame_pa(mm.frame_of[h]), self.PAGE)) == self.expect[h]
            elif st == S_COMPRESSED:
                e = self._entry(h)
                ok = e is not None
                if ok:
                    stream = b''.join(bytes(view(cfg.chunk_pa(ch), self.CHUNK)) for ch in e['chunk'])[:e['comp_len']]
                    page = stream if e['flags'] & self.FL.RAW else decompress(stream, self.PAGE)
                    ok = checksum(stream) == e['checksum'] and page is not None and checksum(page) == self.expect[h]
                ok = ok or h in self.corrupted
            elif st == S_LOST:
                ok = h in self.corrupted
            else:
                ok = st == S_UNTOUCHED
            if not ok:
                wrong.append(h)
        self.chk('AUDIT-3', not wrong, f'{len(wrong)} pages with wrong contents, first {wrong[0]:#x}' if wrong else '')
        # AUDIT-4: nothing in flight
        idle = (not self.queued and not self.inhw and not self.posted and not self.limbo
                and self.job_tail == self.job_head and self.cpl_tail == self.cpl_head
                and not self.irq_level and not mm.inflight and not s.drv.pending and not mm.busy)
        self.chk('AUDIT-4', idle, 'jobs or completions left over at the end of the run')
        return {'pages': dict(counts), 'chunks_owned': len(owner), 'chunks_free': len(free),
                'frames_used': len(used), 'frames_free': len(freef), 'violations': sum(self.nviol.values())}

    def summary(self):
        """[(rule id, owner, how it is checked, evaluations, failures)] in spec order."""
        return [(rid, r['owner'], r['check'], self.cov.get(rid, 0), self.nviol.get(rid, 0))
                for rid, r in self.spec.rules.items()]

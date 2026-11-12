"""The surroundings of the FW: cores, user programs, and the fault injector.

Each user program is one thread that alternates between user work (think_ns)
and one page access. User SW is the party served: it never talks to the LZ4 HW,
it only touches its own pages and sometimes has to wait.
"""
import random
from collections import Counter

from lz4sim.codec import checksum
from lz4sim.kernel import S_COMPRESSED

from .des import Resource
from .platform import Ctx


class Env:
    def __init__(self, sim, spec, cfg, p, mon, mm, wl, expect, dram, seed=1):
        self.sim, self.spec, self.cfg, self.p = sim, spec, cfg, p
        self.mon, self.mm, self.wl, self.expect, self.dram = mon, mm, wl, expect, dram
        self.cores = [Resource(sim, f'core{i}') for i in range(p.cores)]
        self.rng = random.Random(seed + 1)
        self.ctxs = []
        self.results = Counter()
        self.per_client = [Counter() for _ in wl.clients]
        self.user_ns = 0
        self.count = 0
        self.injected = 0
        self.done = sim.event()
        self._left = 0

    def start(self, n):
        per = [[] for _ in self.wl.clients]
        for h, w in self.wl.accesses(n):
            per[self.wl.client_of(h)].append((h, w))
        self._left = len(per)
        for i, accs in enumerate(per):
            self.sim.process(self._thread(i, accs), self.wl.clients[i]['name'])

    def _thread(self, i, accs):
        sim, p, mm, cfg = self.sim, self.p, self.mm, self.cfg
        core = self.cores[i % len(self.cores)]
        ctx = Ctx(sim, self.wl.clients[i]['name'], core)
        self.ctxs.append(ctx)
        cs = self.per_client[i]
        yield core.acquire()
        for h, w in accs:
            yield sim.timeout(p.think_ns)
            self.user_ns += p.think_ns
            t0 = sim.now
            kind = yield from mm.access(ctx, h, w)
            self.results[kind] += 1
            cs[kind] += 1
            if kind != 'hit':
                cs['wait_ns'] += sim.now - t0
                self.mon.emit('user', 'fault', h=h, w=int(w), kind=kind, ns=sim.now - t0, client=i)
            if w and kind != 'lost':                 # the instruction restarts and the store goes through
                mv = self.dram.view(cfg.frame_pa(mm.frame_of[h]), cfg.page)
                if kind == 'first':
                    self.wl.fill(mv)
                else:
                    self.wl.mutate(mv)
                self.expect[h] = checksum(mv)
            self.count += 1
            if p.corrupt_every and self.count % p.corrupt_every == 0:
                self._inject()
            if core.q:                               # someone else wants this core: take turns
                core.release()
                ctx.runq_ns += yield core.acquire()
        core.release()
        self._left -= 1
        if not self._left:
            self.done.succeed()

    def _inject(self):
        """Fault injection: flip one byte in the first chunk of a compressed RW page."""
        cfg, mm = self.cfg, self.mm
        cands = [h for h in range(cfg.rw_pages) if mm.state[h] == S_COMPRESSED]
        if not cands:
            return
        h = self.rng.choice(cands)
        e = self.spec.unpack('cot_entry', self.dram.view(cfg.entry_pa(h), 32))
        if not e['flags'] & self.spec.enum['flag'].VALID:
            return
        c = e['chunk'][0]
        off = self.rng.randrange(min(e['comp_len'], cfg.chunk))
        self.dram.view(cfg.chunk_pa(c), cfg.chunk)[off] ^= 0xFF
        self.injected += 1
        self.mon.emit('env', 'inject', h=h, chunk=c, offset=off)

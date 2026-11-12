"""Everything between the FW model and the HW model: the monitor that sees every
boundary event, the DRAM port used by the HW master, the interrupt line, the
execution context of a piece of FW, and the narrow API the FW is written against.

The FW model may touch the outside world only through Platform and Ctx. A port
to C++ keeps this API and replaces what is behind it.
"""
import json
import random
from collections import Counter
from math import ceil


class Monitor:
    """Boundary events go here. Checkers, statistics and the trace file subscribe."""

    def __init__(self, sim, path=None):
        self.sim = sim
        self.subs = []
        self.f = open(path, 'w') if path else None
        self.n = 0

    def emit(self, src, ev, **kw):
        t = self.sim.now
        self.n += 1
        for s in self.subs:
            s(t, src, ev, kw)
        if self.f:
            self.f.write(json.dumps({'t': t, 'src': src, 'ev': ev, **kw}, separators=(',', ':')) + '\n')

    def close(self):
        if self.f:
            self.f.close()
            self.f = None


class Meter:
    """Time stamps of one job at the points where it crosses the interface, keyed by tag."""

    def __init__(self):
        self.j = {}

    def mark(self, tag, what, t):
        self.j.setdefault(tag, {})[what] = t

    def pop(self, tag):
        return self.j.pop(tag, {})


class Bus:
    """The DRAM port as the HW master sees it. One burst is one transfer.

    Other traffic (CPU, HRT) is not simulated access by access: with probability
    bus_bg_share a burst finds the port taken and waits a uniform part of
    bus_bg_burst_ns.
    """

    def __init__(self, sim, dram, p, mon, seed=1):
        self.sim, self.dram, self.p, self.mon = sim, dram, p, mon
        self.rng = random.Random(seed * 7919 + 13)
        self.busy_ns = Counter()
        self.wait_ns = Counter()
        self.bytes = Counter()
        self.bursts = Counter()

    def xfer(self, master, pa, n, data=None):
        p = self.p
        w = 0
        if p.bus_bg_share and self.rng.random() < p.bus_bg_share:
            w = int(self.rng.random() * p.bus_bg_burst_ns)
        d = p.bus_setup_ns + ceil(n / p.bus_bytes_per_ns)
        yield self.sim.timeout(w + d)
        self.busy_ns[master] += d
        self.wait_ns[master] += w
        self.bytes[master] += n
        self.bursts[master] += 1
        if data is None:
            out = self.dram.read(pa, n)
            self.mon.emit(master, 'mem_r', pa=pa, n=n)
            return out
        self.dram.write(pa, data)
        self.mon.emit(master, 'mem_w', pa=pa, n=n)
        return None


class IrqLine:
    """Level-sensitive interrupt line from the HW to one handler."""

    def __init__(self, sim, p, mon):
        self.sim, self.p, self.mon = sim, p, mon
        self.level = False
        self.handler = None
        self.active = False
        self.edges = 0
        self.dropped = 0
        self.served = 0

    def set(self, level):
        level = bool(level)
        if level == self.level:
            return
        self.level = level
        self.mon.emit('hw', 'irq', level=int(level))
        if not level:
            return
        self.edges += 1
        if self.p.irq_drop_every and self.edges % self.p.irq_drop_every == 0:
            self.dropped += 1                       # fault injection: this edge never reaches the CPU
            return
        if self.handler is not None and not self.active:
            self.active = True
            self.sim.process(self._serve(), 'irq')

    def _serve(self):
        yield self.sim.timeout(self.p.irq_latency_ns)
        while self.level:
            self.served += 1
            yield from self.handler()
        self.active = False


class Ctx:
    """Where a piece of FW runs: a user thread on a core, the interrupt handler, or a kernel thread."""

    def __init__(self, sim, name, core=None):
        self.sim = sim
        self.name = name
        self.core = core
        self.kcpu = 0          # kernel CPU time spent in this context
        self.runq_ns = 0       # time spent waiting to get the core back

    def cpu(self, ns):
        self.kcpu += ns
        return self.sim.timeout(ns)

    def block(self, ev):
        """Sleep until ev fires. A thread gives up its core while it sleeps."""
        if ev.done:
            return ev.value
        if self.core is None:
            return (yield ev)
        self.core.release()
        v = yield ev
        self.runq_ns += yield self.core.acquire()
        return v


class Platform:
    """The FW's view of the hardware: registers and shared memory, each with a CPU cost."""

    def __init__(self, sim, spec, dram, p, mon):
        self.sim, self.spec, self.dram, self.p, self.mon = sim, spec, dram, p, mon
        self.hw = None

    def now(self):
        return self.sim.now

    def reg_write(self, ctx, name, val):
        yield ctx.cpu(self.p.mmio_ns)
        self.mon.emit('fw', 'mmio_w', reg=name, val=val)
        self.hw.mmio_write(self.spec.off[name], val)

    def reg_read(self, ctx, name):
        yield ctx.cpu(self.p.mmio_ns)
        val = self.hw.mmio_read(self.spec.off[name])
        self.mon.emit('fw', 'mmio_r', reg=name, val=val)
        return val

    def mem_write(self, ctx, pa, data, ns, what=''):
        yield ctx.cpu(ns)
        self.dram.view(pa, len(data))[:] = data
        self.mon.emit('fw', 'mem_w', pa=pa, n=len(data), what=what)

    def mem_read(self, ctx, pa, n, ns, what=''):
        yield ctx.cpu(ns)
        data = bytes(self.dram.view(pa, n))
        self.mon.emit('fw', 'mem_r', pa=pa, n=n, what=what)
        return data

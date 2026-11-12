"""Put the pieces together: boot image, HW model, FW model, environment, checkers."""
from types import SimpleNamespace

from lz4sim.config import SystemConfig, MiB
from lz4sim.kernel import S_UNTOUCHED
from lz4sim.sim import Simulation

from .des import Sim
from .driver import Driver
from .env import Env
from .hw import Lz4Hw
from .mm import PageManager
from .params import Params
from .platform import Bus, Ctx, IrqLine, Meter, Monitor, Platform
from .spec import SPEC


class Stalled(Exception):
    """The event queue ran dry before the user programs finished."""


class System:
    def __init__(self, cfg=None, p=None, seed=1, workload=None, trace_path=None, check=True, strict=False):
        self.cfg = cfg = cfg or SystemConfig()
        self.p = p = p or Params()
        self.spec = spec = SPEC
        self.seed = seed
        # The build tool and the boot loader are the ones lz4sim already has: same image, same pages.
        boot = Simulation('software', cfg, seed=seed, workload=workload)
        boot.build()
        boot.boot()
        k = boot.kernel
        self.boot = boot
        self.dram, self.wl, self.expect = boot.dram, boot.wl, boot.expect
        for h in range(cfg.rw_pages):                # a page never touched reads as zeros
            if k.state[h] == S_UNTOUCHED:
                self.expect[h] = k.zero_crc
        self.sim = sim = Sim()
        self.mon = mon = Monitor(sim, trace_path)
        self.meter = Meter()
        self.bus = Bus(sim, self.dram, p, mon, seed)
        self.irq = IrqLine(sim, p, mon)
        self.plat = Platform(sim, spec, self.dram, p, mon)
        self.hw = Lz4Hw(sim, spec, p, self.bus, mon, self.irq, self.dram, self.meter)
        self.plat.hw = self.hw
        self.ring_base = cfg.pinned_base + cfg.pin_img_mib * MiB      # start of the pinned run-time region
        self.drv = Driver(sim, spec, cfg, p, self.plat, mon, self.irq, self.meter, self.ring_base)
        state = SimpleNamespace(state=k.state, frame_of=k.frame_of, lru=k.lru,
                                free_frames=k.free_frames, bitmap=boot.bitmap)
        self.mm = PageManager(sim, spec, cfg, p, self.plat, mon, self.drv, state)
        self.env = Env(sim, spec, cfg, p, mon, self.mm, self.wl, self.expect, self.dram, seed)
        self.chk = None
        if check:
            from .checkers import Checker
            self.chk = Checker(self, strict=strict)
        self.t_end = 0
        self.accesses = 0

    def run(self, accesses, limit_ns=None):
        sim = self.sim
        if limit_ns is None:                          # watchdog in simulated time, far above any sane run
            limit_ns = 10 ** 9 + accesses * 10 ** 6
        init = sim.process(self.drv.init(Ctx(sim, 'boot')), 'init')
        sim.run(stop=init)
        self.mm.emit_boot()
        self.env.start(accesses)
        self.accesses = accesses
        sim.run(until=limit_ns, stop=self.env.done)
        if not self.env.done.done:
            raise Stalled(f'user programs did not finish by {sim.now} ns: {len(self.mm.free_frames)} free frames, '
                          f'{self.mm.inflight} COMPRESS in flight, {len(self.drv.pending)} jobs pending')
        self.t_end = sim.now                          # end of the measured window
        sim.run(until=sim.now + 10 ** 8)              # let background work and stale timers drain
        return self

    def audit(self):
        if self.chk is None:
            return {}
        return self.chk.audit()

    def close(self):
        self.mon.close()

"""JSON Lines trace of system behaviour.

One record per line: {"n": sequence, "t": simulated ns, "ev": kind, ...}.
Level "jobs" records everything the hardware sees or touches plus page state
changes; level "all" adds every page access, PTE change and kernel table read.
"""
import json
from collections import Counter

FULL_ONLY = {'access', 'pte', 'cot_read'}


class Clock:
    def __init__(self):
        self.t = 0.0           # simulated time, ns
        self.kernel_fg = 0.0   # kernel CPU time on the fault path
        self.kernel_bg = 0.0   # kernel CPU time in reclaim
        self.accel = 0.0       # accelerator busy time


class Trace:
    def __init__(self, path=None, level='jobs', clk=None, keep=False):
        self.f = open(path, 'w') if path else None
        self.records = [] if keep else None   # in-memory copy, used by the 3D replay exporter
        self.level = level
        self.clk = clk or Clock()
        self.n = 0
        self.counts = Counter()

    @property
    def enabled(self):
        return self.f is not None or self.records is not None

    def emit(self, ev, **fields):
        if self.f is None and self.records is None:
            return
        if self.level != 'all' and ev in FULL_ONLY:
            return
        self.n += 1
        self.counts[ev] += 1
        rec = {'n': self.n, 't': round(self.clk.t), 'ev': ev}
        rec.update(fields)
        if self.records is not None:
            self.records.append(rec)
        if self.f is not None:
            self.f.write(json.dumps(rec, separators=(',', ':')))
            self.f.write('\n')

    def close(self):
        if self.f:
            self.f.close()
            self.f = None

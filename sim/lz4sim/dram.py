"""Physical DRAM as one byte array addressed by PA, with access counters."""


class BusError(Exception):
    pass


class DRAM:
    def __init__(self, cfg):
        self.cfg = cfg
        self.base = cfg.dram_base
        self.size = cfg.dram_end - cfg.dram_base
        self.mem = bytearray(self.size)
        self.reset_stats()

    def reset_stats(self):
        self.reads = self.writes = 0
        self.read_bytes = self.write_bytes = 0

    def _off(self, pa, n):
        off = pa - self.base
        if off < 0 or off + n > self.size:
            raise BusError(f'PA {pa:#x} + {n} outside DRAM')
        return off

    def read(self, pa, n):
        off = self._off(pa, n)
        self.reads += 1
        self.read_bytes += n
        return bytes(self.mem[off:off + n])

    def write(self, pa, data):
        off = self._off(pa, len(data))
        self.mem[off:off + len(data)] = data
        self.writes += 1
        self.write_bytes += len(data)

    def view(self, pa, n):
        """Zero-copy window, not counted as accelerator traffic (CPU stores, audits)."""
        off = self._off(pa, n)
        return memoryview(self.mem)[off:off + n]

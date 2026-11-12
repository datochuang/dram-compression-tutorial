"""The CPU caches against the LZ4 HW, kept as a few flags per frame and per chunk.

The LZ4 HW is a bus master of its own. It reads and writes DRAM and sees
nothing of what sits in a CPU cache. Unless the bus keeps the two coherent,
the kernel has to do it by hand around every job, and a mistake is silent: the
CRC-32 is taken over the stream, so it agrees with whatever page the HW saw.

No data is copied here. DRAM in the simulation is always right; the flags say
what a real CPU or the real HW would have seen instead, and the first access
that would have seen something else raises CacheError.

    C1  the LZ4 HW reads a frame or a chunk while a CPU cache holds a newer line of it:
        the HW works on old data
    C2  the LZ4 HW writes a frame or a chunk while a CPU cache holds a dirty line of it:
        the line is written back later, over what the HW wrote
    C3  the CPU reads or runs from a frame, or reads a chunk, through a line that is older than DRAM,
        or runs from a frame whose newest bytes are still only in the data cache
    C4  a dirty line is dropped: what the CPU wrote is gone

One set of flags stands for the caches of all cores, because the port calls
are defined to act on every core.

Nobody knows what the caches hold when the kernel starts: the boot loader has
written the chunk pool and may have used the frame area for anything. So every
frame and every chunk starts as held and dirty, and stays so until flush_all.
"""
from collections import Counter

HELD_D, HELD_I, DIRTY, STALE_D, STALE_I = 1, 2, 4, 8, 16


class CacheError(Exception):
    pass


class CpuCache:
    def __init__(self, cfg):
        self.cfg = cfg
        self.flag = bytearray([HELD_D | HELD_I | DIRTY]) * cfg.frames
        self.chunk = bytearray([HELD_D | DIRTY]) * cfg.pool_chunks
        self.st = Counter()

    def _f(self, pa):
        return (pa - self.cfg.fc_base) // self.cfg.page

    # ---- the CPU
    def cpu_uses(self, pa, write, code):
        """One instruction reads, writes or runs from the frame."""
        f = self._f(pa)
        x = self.flag[f]
        if x & (STALE_I if code else STALE_D):
            raise CacheError(f'C3: the CPU {"runs" if code else "reads"} frame {pa:#x} through a line older than DRAM')
        if code and x & DIRTY:
            raise CacheError(f'C3: the CPU runs frame {pa:#x} while its newest bytes are only in the data cache')
        self.flag[f] = x | (HELD_I if code else HELD_D) | (DIRTY if write else 0)

    def cpu_fill(self, pa):
        """The CPU overwrites the whole frame: every data line is new and dirty.
        An instruction line of the frame that is still held is now older than the data."""
        f = self._f(pa)
        x = (self.flag[f] | HELD_D | DIRTY) & ~STALE_D
        self.flag[f] = x | (STALE_I if x & HELD_I else 0)

    def cpu_reads_chunk(self, c, fresh=True):
        """The kernel reads one chunk. fresh: lines of it that the cache still holds are dropped first."""
        x = self.chunk[c]
        if fresh:
            if x & DIRTY:
                raise CacheError(f'C4: a dirty line of chunk {c:#x} is dropped')
            x = 0
        if x & STALE_D:
            raise CacheError(f'C3: the CPU reads chunk {c:#x} through a line older than DRAM')
        self.chunk[c] = x | HELD_D
        self.st['chunk_reads'] += 1

    # ---- the LZ4 HW
    def hw_reads(self, pa):
        if self.flag[self._f(pa)] & DIRTY:
            raise CacheError(f'C1: the LZ4 HW reads frame {pa:#x} while a CPU cache holds a newer line')

    def hw_writes(self, pa):
        f = self._f(pa)
        x = self.flag[f]
        if x & DIRTY:
            raise CacheError(f'C2: the LZ4 HW writes frame {pa:#x} while a CPU cache holds a dirty line')
        if x & HELD_D:
            x |= STALE_D
        if x & HELD_I:
            x |= STALE_I
        self.flag[f] = x

    def hw_reads_chunk(self, c):
        if self.chunk[c] & DIRTY:
            raise CacheError(f'C1: the LZ4 HW reads chunk {c:#x} while a CPU cache holds a newer line')

    def hw_writes_chunk(self, c):
        x = self.chunk[c]
        if x & DIRTY:
            raise CacheError(f'C2: the LZ4 HW writes chunk {c:#x} while a CPU cache holds a dirty line')
        if x & HELD_D:
            self.chunk[c] = x | STALE_D

    # ---- what the kernel can do about it
    def clean(self, pa):
        self.flag[self._f(pa)] &= ~DIRTY                  # the lines stay in the cache, equal to DRAM
        self.st['clean'] += 1

    def invalidate(self, pa, icache=True):
        f = self._f(pa)
        if self.flag[f] & DIRTY:
            raise CacheError(f'C4: a dirty line of frame {pa:#x} is dropped')
        self.flag[f] &= 0 if icache else (HELD_I | STALE_I)
        self.st['invalidate'] += 1

    def flush_all(self):
        """Clean, then invalidate, every line of the frame area and of the chunk pool. Once, at boot."""
        self.flag = bytearray(self.cfg.frames)
        self.chunk = bytearray(self.cfg.pool_chunks)
        self.st['flush_all'] += 1

"""Everything around the kernel in the host simulation: DRAM, the CPU MMU, the build tool,
the boot loader, the user programs and the step log.

One thread runs everything. Where the real system would have a second thread
do something meanwhile (the reclaimer), it runs to completion at the point
where it would be woken.
"""
import hashlib
import random
from array import array
from collections import Counter
from math import ceil

from ifsim.spec import SPEC
from lz4sim.alloc_bitmap import KernelBitmap
from lz4sim.config import SMALL, SystemConfig
from lz4sim.dram import DRAM
from lz4sim.workload import Workload

from . import codec as codec_mod
from .cache import CpuCache
from .codec import crc32
from .hw import Lz4Hw
from .kernel import Kernel, KernelBug, OutOfMemory

CONFIGS = {
    'full': (SystemConfig, {}),
    'small': (lambda: SMALL, dict(hot_ro_pages=100, hot_rw_pages=200)),
}


class DataMismatch(Exception):
    pass


class NoProgress(Exception):
    """The same instruction faulted again and again: each time the page was taken away before the CPU ran it."""


RETRY_LIMIT = 8


class Log:
    """Step log: (who, what, values). Off unless somebody is listening."""

    def __init__(self):
        self.sink = None

    def __call__(self, who, what, **values):
        if self.sink is not None:
            self.sink.append((who, what, values))


class _BitmapTrace:
    def __init__(self, log):
        self.log = log

    def emit(self, kind, who='kernel', op='', **kw):
        self.log('FW', 'bitmap_' + op, **kw)


class Port:
    """What the kernel may call. Also the CPU MMU: PTEs with their accessed and dirty bits."""

    def __init__(self, m):
        self.m, self.cfg, self.dram, self.log = m, m.cfg, m.dram, m.log
        self.pte = array('Q', [0]) * m.cfg.pages          # frame PA, 0 when the PTE is not valid
        self.accessed = bytearray(m.cfg.pages)
        self.dirty = bytearray(m.cfg.pages)
        self.locked = False
        self.booting = True
        self.reclaim_wanted = False
        self.map_accessed = 1
        self.st = Counter()

    def _held(self):
        if not (self.locked or self.booting):
            raise KernelBug('kernel table touched without the lock')

    def lock(self):
        if self.locked:
            raise KernelBug('lock taken twice')
        self.locked = True
        self.log('FW', 'lock')

    def unlock(self):
        if not self.locked:
            raise KernelBug('unlock without lock')
        self.locked = False
        self.log('FW', 'unlock')

    def cot_read(self, h):
        self._held()
        return self.dram.read(self.cfg.entry_pa(h), 32)

    def cot_write(self, h, raw):
        self._held()
        self.dram.write(self.cfg.entry_pa(h), raw)

    def zero_frame(self, pa):
        self.dram.write(pa, bytes(self.cfg.page))
        self.m.cache.cpu_fill(pa)                         # the kernel's own CPU writes the zeros
        self.log('FW', 'zero_frame', frame_pa=pa)

    def frame_write(self, pa, page):
        self.dram.write(pa, page)
        self.m.cache.cpu_fill(pa)

    def frame_read(self, pa):
        self.m.cache.cpu_uses(pa, False, False)           # the kernel's own CPU reads it, through the data cache
        return bytes(self.dram.view(pa, self.cfg.page))

    def chunk_read(self, c, fresh=True):
        """fresh: lines of the chunk that a CPU cache still holds are dropped first, or the mapping is not cached."""
        self.m.cache.cpu_reads_chunk(c, fresh)
        return bytes(self.dram.view(self.cfg.chunk_pa(c), self.cfg.chunk))

    def cache_flush_layer(self):
        self.m.cache.flush_all()
        self.log('FW', 'cache_flush_layer')

    def cache_clean(self, pa):
        self.m.cache.clean(pa)
        self.log('FW', 'cache_clean', frame_pa=pa)

    def cache_invalidate(self, pa):
        self.m.cache.invalidate(pa)
        self.log('FW', 'cache_invalidate', frame_pa=pa)

    def may_wait(self):
        return self.m.context == 'thread'

    def thread(self):
        return 0

    def pte_map(self, h, pa):
        self._held()
        self.pte[h] = pa
        self.accessed[h] = self.map_accessed              # the kernel writes the PTE with the accessed bit set
        self.dirty[h] = 0
        self.log('FW', 'pte_map', h=h, frame_pa=pa)

    def pte_unmap(self, h):
        self._held()
        self.m.on_unmap(h)
        self.pte[h] = 0
        self.st['tlb_flushes'] += 1
        self.log('FW', 'pte_unmap', h=h)

    def pte_test_clear_accessed(self, h):
        self._held()
        a = self.accessed[h]
        self.accessed[h] = 0
        return a

    def lz4_job(self, desc):
        if self.locked:
            raise KernelBug('job handed to the LZ4 HW with the lock held')
        return self.m.hw.run(desc)

    def wait_page(self, h):
        raise KernelBug(f'page {h:#x} is busy, which one thread cannot cause')

    def wake_page(self, h):
        self._held()

    def wait_frame(self):
        self.unlock()
        self.m.kernel.reclaim()                           # what the reclaimer thread would do meanwhile
        self.reclaim_wanted = False
        self.lock()
        if not self.m.kernel.free_frames:
            raise OutOfMemory('no frame can be freed')

    def wake_frame(self):
        self._held()

    def wake_reclaimer(self):
        self.reclaim_wanted = True


class Machine:
    PORT, KERNEL = Port, Kernel

    def __init__(self, cfg='small', seed=1, codec='lib', policy='clock', corrupt_every=0, workload=None,
                 map_accessed=1, protect=1, verify=False):
        make, wl = CONFIGS[cfg] if isinstance(cfg, str) else (lambda: cfg, {})
        self.cfg = cfg = make()
        self.seed, self.policy = seed, policy
        self.spec = SPEC
        self.dram = DRAM(cfg)
        self.log = Log()
        self.codec = codec_mod.make(codec) if isinstance(codec, str) else codec
        self.wl = Workload(cfg, seed, **{**wl, **(workload or {})})
        self.hw = Lz4Hw(SPEC, cfg, self.dram, self.codec, self.log)
        self.cache = self.hw.watch = CpuCache(cfg)
        self.context = 'thread'                           # or 'isr', 'hrt': where a page fault cannot be served
        self.port = self.PORT(self)
        self.port.map_accessed = map_accessed
        self.bitmap = KernelBitmap(cfg, _BitmapTrace(self.log))
        # the kernel's own decoder is not the one inside the LZ4 HW, whatever `codec` says
        self.kernel = self.KERNEL(SPEC, cfg, self.port, self.bitmap, policy, self.log, protect,
                                  decoder=codec_mod.LibCodec().decompress, verify=verify)
        self.zero_crc = crc32(bytes(cfg.page))
        self.expect = array('I', [self.zero_crc]) * cfg.pages   # CRC-32 of what every page must contain
        self.refetched = bytearray(cfg.pages)             # RW page came back from the pool and was not written since
        self.corrupt_every = corrupt_every
        self.corrupt_rng = random.Random(seed + 1)
        self.corrupted = set()
        self.st = Counter()
        self.cst = [Counter() for _ in self.wl.clients]   # per user program
        self.build = Counter()
        self.min_free_chunks = cfg.pool_chunks
        self.accesses = 0
        self.guard = None

    # ---- build tool (off line, on the build machine) and boot
    def build_image(self):
        """Compress every RO page, lay the streams out from chunk 0 without gaps, write their COT entries."""
        cfg, dram, FL = self.cfg, self.dram, self.spec.enum['flag']
        c = 0
        for h in range(cfg.ro_first, cfg.pages):
            page = self.wl.ro_page()
            self.expect[h] = crc32(page)
            stream, flags = self.codec.compress(page), FL.VALID | FL.RO
            if stream is None or len(stream) > cfg.compress_limit:
                stream, flags = page, flags | FL.RAW      # stored as it is, in 8 chunks
                self.build['ro_raw'] += 1
            n = ceil(len(stream) / cfg.chunk)
            if c + n > cfg.pool_chunks:
                raise RuntimeError('the RO image does not fit in the chunk pool')
            dram.write(cfg.chunk_pa(c), stream)
            dram.write(cfg.entry_pa(h), self.spec.pack('cot_entry', {
                'flags': flags, 'count': n, 'comp_len': len(stream), 'checksum': crc32(stream),
                'chunk': range(c, c + n)}))
            c += n
            self.build['ro_bytes'] += len(stream)
            self.build['ro_hist_%d' % n] += 1
        self.build['ro_chunks'] = c
        # memory the compression layer must never touch: kernel image, pinned run-time data, HRT memory
        size = cfg.cot_base - cfg.dram_base
        self.dram.view(cfg.hrt_base, cfg.cot_base - cfg.hrt_base)[:] = random.Random(self.seed).randbytes(cfg.cot_base - cfg.hrt_base)
        self.guard = hashlib.blake2b(self.dram.view(cfg.dram_base, size)).digest()
        return c

    def boot(self):
        cfg, k = self.cfg, self.kernel
        k.boot()
        for h in range(cfg.data_pages):                   # boot loader: the initialised .data pages
            page = self.wl.rw_page()
            self.expect[h] = crc32(page)
            k.boot_load(h, page)
        self.port.booting = False
        self.build['free_chunks_at_boot'] = self.bitmap.free
        self.min_free_chunks = self.bitmap.free
        self.dram.reset_stats()
        return self

    # ---- user SW
    def access(self, h, write):
        """One access of user SW to page h, as the CPU carries it out."""
        port, k = self.port, self.kernel
        who = self.wl.owner[h]
        cs = self.cst[who]
        kind, fill, tries = 'hit', False, 0
        self.log('CPU', 'access', h=h, op='write' if write else 'read', user_sw=self.wl.clients[who]['name'])
        while not port.pte[h]:                            # CPU: the PTE is not valid, page fault
            self.log('CPU', 'page_fault', h=h)
            r = k.page_fault(h)
            if kind == 'hit':
                kind = r                                  # the access is counted under its first fault
            else:
                self.st['refaults'] += 1                  # the page was taken away again before the CPU got to it
                tries += 1
                if tries == RETRY_LIMIT:
                    raise NoProgress(f'page {h:#x} was faulted in {tries + 1} times and never reached')
            fill |= r == 'first_touch'
            if r == 'lost':                               # the user program cannot continue
                self.st[kind] += 1
                cs[kind] += 1
                return 'lost'
            if r in ('fault_ro', 'fault_rw'):
                if crc32(self.dram.view(port.pte[h], self.cfg.page)) != self.expect[h]:
                    raise DataMismatch(f'page {h:#x} came back with different contents')
                self.refetched[h] = r == 'fault_rw'
            if port.reclaim_wanted:                       # the reclaimer thread runs now
                port.reclaim_wanted = False
                k.reclaim()
            if self.bitmap.free < self.min_free_chunks:
                self.min_free_chunks = self.bitmap.free
            # CPU: back from the exception, the same instruction runs again
        self.st[kind] += 1
        cs[kind] += 1
        # CPU: the PTE is valid (now), the instruction runs
        self.log('CPU', 'instruction_runs', h=h, frame_pa=port.pte[h])
        port.accessed[h] = 1
        if self.policy == 'lru':
            k.oracle_touch(h)
        self.cache.cpu_uses(port.pte[h], write, self.cfg.is_ro(h))
        if write:
            port.dirty[h] = 1
            self.refetched[h] = 0
            mv = self.dram.view(port.pte[h], self.cfg.page)
            if fill:                                      # the program initialises its new page
                self.wl.fill(mv)
            else:
                self.wl.mutate(mv)
            self.expect[h] = crc32(mv)
            self.st['writes'] += 1
        return kind

    def on_unmap(self, h):
        if not self.cfg.is_ro(h):
            self.st['rw_unmaps'] += 1
            if self.refetched[h]:                         # its old stored copy would still have been good
                self.st['rw_unmaps_unwritten'] += 1
                self.refetched[h] = 0

    def run(self, n, check_every=0):
        from .check import audit
        for i, (h, w) in enumerate(self.wl.accesses(n), 1):
            self.access(h, w)
            self.accesses += 1
            if self.corrupt_every and i % self.corrupt_every == 0:
                self.inject()
            if check_every and i % check_every == 0:
                audit(self)
        return self

    def inject(self):
        """Fault injection: flip one byte of the stored stream of a compressed RW page."""
        from .kernel import COMPRESSED
        cfg, k = self.cfg, self.kernel
        cands = [h for h in range(cfg.rw_pages) if k.state[h] == COMPRESSED and h not in self.corrupted]
        if not cands:
            return
        h = self.corrupt_rng.choice(cands)
        e = self.spec.unpack('cot_entry', self.dram.view(cfg.entry_pa(h), 32))
        off = self.corrupt_rng.randrange(min(e['comp_len'], cfg.chunk))
        self.dram.view(cfg.chunk_pa(e['chunk'][0]), cfg.chunk)[off] ^= 0xFF
        self.corrupted.add(h)
        self.st['injected'] += 1


def make(cfg='small', n=None, **kw):
    """Build, boot and run. n=None: 20000 accesses on small, 400000 on full."""
    m = Machine(cfg, **kw)
    m.build_image()
    m.boot()
    if n is None:
        n = 400_000 if cfg == 'full' else 20_000
    if n:
        m.run(n)
    return m

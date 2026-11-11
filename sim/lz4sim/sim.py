"""Top level: build the image, boot, run a workload, audit, report."""
import json
import os
import random
from array import array
from collections import Counter, OrderedDict
from math import ceil

from .config import SystemConfig, MiB
from .codec import compress, checksum
from .dram import DRAM
from .trace import Trace, Clock
from .workload import Workload
from .formats import COTEntry, F_VALID, F_RO, F_RAW
from .alloc_stack import HwFreeStack
from .alloc_bitmap import KernelBitmap
from .accel import BaselineAccel, SoftwareAccel
from .kernel import BaselineKernel, SoftwareKernel, S_COMPRESSED, S_PRESENT, S_LOST, S_NAME

VARIANTS = ('baseline', 'software')


class AuditError(Exception):
    pass


class Simulation:
    def __init__(self, variant, cfg=None, seed=1, trace_path=None, trace_level='jobs',
                 workload=None, corrupt_every=0, keep_trace=False):
        if variant not in VARIANTS:
            raise ValueError(f'variant must be one of {VARIANTS}')
        self.variant = variant
        self.cfg = cfg = cfg or SystemConfig()
        self.seed = seed
        self.dram = DRAM(cfg)
        self.clk = Clock()
        self.trace = Trace(trace_path, trace_level, self.clk, keep=keep_trace)
        self.wl = Workload(cfg, seed, **(workload or {}))
        self.expect = array('I', [0]) * cfg.pages
        self.corrupt_every = corrupt_every
        self.corrupt_rng = random.Random(seed + 1)
        if variant == 'baseline':
            self.stack = HwFreeStack(cfg, self.dram, self.trace)
            self.accel = BaselineAccel(cfg, self.dram, self.trace, self.clk, self.stack)
            self.kernel = BaselineKernel(cfg, self.dram, self.accel, self.trace, self.wl,
                                         self.clk, self.expect, self.stack)
        else:
            self.bitmap = KernelBitmap(cfg, self.trace)
            self.accel = SoftwareAccel(cfg, self.dram, self.trace, self.clk)
            self.kernel = SoftwareKernel(cfg, self.dram, self.accel, self.trace, self.wl,
                                         self.clk, self.expect, self.bitmap)
        self.bst = Counter()
        self.ro_chunks = 0
        self.ro_comp_bytes = 0
        self.free_boot = 0
        self.results = Counter()
        self.accesses = 0
        self.samples = []
        self.injected = 0
        self.audit_result = {}

    # ---- phases
    def build(self):
        """Build tool: compress every RO page, lay the chunks out from chunk 0, write the RO entries."""
        cfg, dram = self.cfg, self.dram
        zero = self.kernel.zero_page
        full = self.trace.level == 'all'
        c = 0
        for h in range(cfg.ro_first, cfg.pages):
            page = self.wl.ro_page()
            self.expect[h] = checksum(page)
            if page == zero:
                self.bst['ro_zero'] += 1
            blob = compress(page)
            raw = False
            if len(blob) > cfg.compress_limit:
                blob, raw = page, True
                self.bst['ro_raw'] += 1
            n = ceil(len(blob) / cfg.chunk)
            if c + n > cfg.pool_chunks:
                raise RuntimeError('the RO image does not fit in the pool')
            dram.write(cfg.chunk_pa(c), blob)
            entry = COTEntry(F_VALID | F_RO | (F_RAW if raw else 0), n, len(blob),
                             checksum(blob), tuple(range(c, c + n)))
            dram.write(cfg.entry_pa(h), entry.pack())
            if full:
                self.trace.emit('cot', who='build', h=h, entry=entry.to_dict(), hex=entry.pack().hex())
            c += n
            self.ro_comp_bytes += len(blob)
        self.ro_chunks = c
        self.trace.emit('build', who='build', ro_pages=cfg.ro_pages, ro_chunks=c,
                        ro_raw=self.bst['ro_raw'], comp_bytes=self.ro_comp_bytes)
        return c

    def boot(self):
        cfg = self.cfg
        self.kernel.boot(self.ro_chunks)
        for h in range(cfg.data_pages):
            self.kernel.load_page(h, self.wl.rw_page())
        self.free_boot = self.kernel.free_chunks()
        self.dram.reset_stats()
        self.trace.emit('boot', who='kernel', free_chunks=self.free_boot,
                        frames_used=cfg.frames - len(self.kernel.free_frames), clients=self.wl.clients)

    def run(self, n, sample_every=0):
        cfg, k, clk = self.cfg, self.kernel, self.clk
        for i, (h, w) in enumerate(self.wl.accesses(n)):
            r = k.access(h, w)
            self.results[r] += 1
            clk.t += cfg.access_gap_ns
            self.accesses += 1
            if k.oom:
                break
            if self.corrupt_every and (i + 1) % self.corrupt_every == 0:
                self._inject()
            if sample_every and (i + 1) % sample_every == 0:
                self._sample()
        return self.results

    def close(self):
        self.trace.close()

    # ---- helpers
    def _inject(self):
        """Fault injection: flip one byte in the first chunk of a compressed RW object."""
        k, cfg = self.kernel, self.cfg
        cands = [h for h in range(cfg.rw_pages) if k.state[h] == S_COMPRESSED]
        if not cands:
            return
        h = self.corrupt_rng.choice(cands)
        entry = COTEntry.unpack(self.dram.view(cfg.entry_pa(h), 32))
        if not entry.valid:
            return
        c = entry.chunks[0]
        off = self.corrupt_rng.randrange(min(entry.comp_len, cfg.chunk))
        mv = self.dram.view(cfg.chunk_pa(c), cfg.chunk)
        mv[off] ^= 0xFF
        self.injected += 1
        self.trace.emit('inject', who='sim', h=h, chunk=c, offset=off)

    def _sample(self):
        k, cfg = self.kernel, self.cfg
        self.samples.append(OrderedDict([
            ('access', self.accesses), ('t_ms', round(self.clk.t / 1e6, 3)),
            ('frames_used', cfg.frames - len(k.free_frames)),
            ('pool_used', cfg.pool_chunks - k.free_chunks()),
            ('faults', k.st['faults']), ('rw_compress_ok', k.st['rw_compress_ok']),
            ('ro_drops', k.st['ro_drops']),
            ('rw_objects', k.st['rw_compress_ok'] - k.st['rw_invalidate'] - k.st['rw_free'])]))

    def write_timeline(self, path):
        with open(path, 'w') as f:
            if self.samples:
                f.write(','.join(self.samples[0].keys()) + '\n')
                for s in self.samples:
                    f.write(','.join(str(v) for v in s.values()) + '\n')

    def dump(self, folder):
        """Memory images for an external test bench: the COT and the chunk pool."""
        cfg = self.cfg
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, 'cot.bin'), 'wb') as f:
            f.write(self.dram.view(cfg.cot_base, cfg.pages * 32))
        with open(os.path.join(folder, 'pool.bin'), 'wb') as f:
            f.write(self.dram.view(cfg.pool_base, cfg.pool_chunks * cfg.chunk))
        meta = {'variant': self.variant, 'cot_base': cfg.cot_base, 'pool_base': cfg.pool_base,
                'fc_base': cfg.fc_base, 'pages': cfg.pages, 'ro_first': cfg.ro_first,
                'pool_chunks': cfg.pool_chunks, 'chunk': cfg.chunk, 'page': cfg.page}
        with open(os.path.join(folder, 'meta.json'), 'w') as f:
            json.dump(meta, f, indent=1)

    # ---- checks
    def audit(self):
        """Every chunk is owned by exactly one valid entry or is free; frames match present pages."""
        cfg, k = self.cfg, self.kernel
        used = {}
        valid_rw = 0
        for h in range(cfg.pages):
            mv = self.dram.view(cfg.entry_pa(h), 32)
            if not (mv[0] & F_VALID):
                if cfg.is_ro(h):
                    raise AuditError(f'RO entry {h:#x} is not valid')
                if k.state[h] == S_COMPRESSED:
                    raise AuditError(f'RW page {h:#x} is compressed but has no entry')
                continue
            e = COTEntry.unpack(mv)
            if not cfg.is_ro(h):
                valid_rw += 1
                if k.state[h] not in (S_COMPRESSED, S_LOST):
                    raise AuditError(f'RW page {h:#x} has a valid entry in state {S_NAME[k.state[h]]}')
            if e.count != ceil(e.comp_len / cfg.chunk):
                raise AuditError(f'entry {h:#x}: count {e.count} does not match comp_len {e.comp_len}')
            for c in e.chunks:
                if c in used:
                    raise AuditError(f'chunk {c:#x} belongs to {used[c]:#x} and {h:#x}')
                used[c] = h
        free = k.free_chunk_set()
        both = used.keys() & free
        if both:
            raise AuditError(f'{len(both)} chunks are both used and free, e.g. {min(both):#x}')
        if len(used) + len(free) != cfg.pool_chunks:
            raise AuditError(f'chunk leak: used {len(used)} + free {len(free)} != {cfg.pool_chunks}')
        present = sum(1 for h in range(cfg.pages) if k.state[h] == S_PRESENT)
        if present != cfg.frames - len(k.free_frames) or present != len(k.lru):
            raise AuditError('present pages, frames in use and the LRU list disagree')
        self.audit_result = {'audit': 'ok', 'audit_used_chunks': len(used),
                             'audit_free_chunks': len(free), 'audit_rw_objects': valid_rw,
                             'audit_present_pages': present}
        return self.audit_result

    # ---- numbers
    def stats(self):
        cfg, k, a, clk, wl = self.cfg, self.kernel, self.accel, self.clk, self.wl
        d = OrderedDict()
        d['#system'] = None
        d['variant'] = self.variant
        d['pages'] = cfg.pages
        d['pool_chunks'] = cfg.pool_chunks
        d['frames'] = cfg.frames
        d['compress_limit'] = cfg.compress_limit_for_rw()

        d['#build'] = None
        d['ro_pages'] = cfg.ro_pages
        d['ro_zero_pages'] = self.bst['ro_zero']
        d['ro_raw_pages'] = self.bst['ro_raw']
        d['ro_comp_ratio'] = self.ro_comp_bytes / (cfg.ro_pages * cfg.page)
        d['ro_chunks'] = self.ro_chunks
        d['ro_chunks_analytic'] = round(cfg.ro_mib * MiB * wl.ro_ratio / cfg.chunk)
        d['ro_image_mib'] = self.ro_chunks * cfg.chunk / MiB
        d['ro_chunk_overhead_pct'] = (self.ro_chunks * cfg.chunk - self.ro_comp_bytes) / max(1, self.ro_chunks * cfg.chunk) * 100

        d['#boot'] = None
        d['free_chunks_boot'] = self.free_boot
        d['data_pages_loaded'] = k.st['loaded']
        if self.variant == 'baseline':
            d['list_chunks_boot'] = self.stack.st['init_writes']
        else:
            d['bitmap_build_used'] = self.bitmap.st['build_used']

        d['#workload'] = None
        p = wl.params()
        for key in ('hot_ro_pages', 'hot_rw_pages', 'p_hot', 'write_frac', 'phase_len', 'ro_ratio', 'rw_ratio'):
            d[key] = p[key]

        d['#run'] = None
        d['accesses'] = self.accesses
        d['hits'] = k.st['hits']
        d['first_touch'] = k.st['first_touch']
        d['faults'] = k.st['faults']
        d['faults_ro'] = k.st['faults_ro']
        d['faults_rw'] = k.st['faults_rw']
        d['fault_rate_pct'] = k.st['faults'] / max(1, self.accesses) * 100
        d['writes'] = k.st['writes']
        d['lost_pages'] = k.st['lost']
        d['injected_corruptions'] = self.injected

        d['#user software'] = None
        for c, cs in zip(wl.clients, k.cst):
            n = c['name']
            d[f'{n}_pages'] = c['pages']
            d[f'{n}_accesses'] = cs['accesses']
            d[f'{n}_faults'] = cs['faults']
            d[f'{n}_fault_wait_avg_us'] = cs['fault_lat'] / max(1, cs['faults']) / 1e3

        d['#reclaim'] = None
        d['reclaims'] = k.st['reclaims']
        d['ro_drops'] = k.st['ro_drops']
        d['rw_compress_ok'] = k.st['rw_compress_ok']
        d['rw_raw_stored'] = k.st['rw_raw']
        d['rw_incompressible'] = k.st['rw_incompressible']
        d['rw_pool_full'] = k.st['rw_pool_full']
        d['incompressible_pinned_end'] = len(k.incompressible)
        d['reclaim_stuck'] = k.st['reclaim_stuck']
        d['oom'] = bool(k.oom)

        d['#jobs'] = None
        d['jobs'] = a.st['jobs']
        for key in sorted(x for x in a.st if x.startswith('op_')):
            d[key] = a.st[key]
        for key in sorted(x for x in a.st if x.startswith('st_')):
            d[key] = a.st[key]

        d['#pool'] = None
        used_end = cfg.pool_chunks - k.free_chunks()
        d['pool_used_end'] = used_end
        d['pool_free_end'] = k.free_chunks()
        d['pool_used_peak'] = max(k.peak_pool, used_end)
        d['pool_used_peak_mib'] = d['pool_used_peak'] * cfg.chunk / MiB
        d['rw_objects_end'] = k.st['rw_compress_ok'] - k.st['rw_invalidate'] - k.st['rw_free']
        ok = max(1, k.st['rw_compress_ok'])
        d['rw_avg_comp_len'] = k.comp_bytes / ok
        d['rw_avg_chunks'] = k.comp_chunks / ok
        d['rw_comp_ratio'] = k.comp_bytes / (ok * cfg.page)
        d['rw_chunk_overhead_pct'] = (k.comp_chunks * cfg.chunk - k.comp_bytes) / max(1, k.comp_chunks * cfg.chunk) * 100

        d['#frames'] = None
        d['frames_used_end'] = cfg.frames - len(k.free_frames)
        d['frames_used_peak'] = k.peak_frames

        d['#dram'] = None
        d['dram_in_use_end_mib'] = cfg.fixed_mib + (used_end * cfg.chunk + d['frames_used_end'] * cfg.page) / MiB
        d['dram_in_use_peak_mib'] = cfg.fixed_mib + (d['pool_used_peak'] * cfg.chunk + k.peak_frames * cfg.page) / MiB
        d['dram_reads'] = self.dram.reads
        d['dram_writes'] = self.dram.writes
        d['dram_read_mib'] = self.dram.read_bytes / MiB
        d['dram_write_mib'] = self.dram.write_bytes / MiB

        d['#allocator'] = None
        d.update(k.alloc_stats())

        d['#time'] = None
        t = max(1.0, clk.t)
        d['sim_time_ms'] = clk.t / 1e6
        d['fault_latency_avg_us'] = k.fault_lat_sum / max(1, k.st['faults']) / 1e3
        d['fault_latency_max_us'] = k.fault_lat_max / 1e3
        d['accel_busy_ms'] = clk.accel / 1e6
        d['accel_util_pct'] = clk.accel / t * 100
        d['kernel_fg_ms'] = clk.kernel_fg / 1e6
        d['kernel_bg_ms'] = clk.kernel_bg / 1e6
        d['cpu_pct'] = (clk.kernel_fg + clk.kernel_bg) / t * 100

        d['#audit'] = None
        d.update(self.audit_result or {'audit': 'skipped'})
        return d


def fmt(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'yes' if v else 'no'
    if isinstance(v, int):
        return f'{v:,}'
    if isinstance(v, float):
        return f'{v:,.2f}'
    return str(v)


def _merge_keys(runs):
    """Union of the stats keys, each new key placed right after the key that preceded it."""
    keys = []
    for _, s in runs:
        pos = -1
        for key in s:
            if key in keys:
                pos = keys.index(key)
            else:
                pos += 1
                keys.insert(pos, key)
    return keys


def format_report(runs):
    """runs: list of (label, stats). Section keys start with '#'."""
    keys = _merge_keys(runs)
    w0 = max(len(key) for key in keys) + 2
    w = max(16, max(len(label) for label, _ in runs) + 2)
    lines = [' ' * w0 + ''.join(f'{label:>{w}}' for label, _ in runs)]
    for key in keys:
        if key.startswith('#'):
            lines.append('')
            lines.append(key[1:].upper())
            continue
        lines.append(f'{key:<{w0}}' + ''.join(f'{fmt(s.get(key)):>{w}}' for _, s in runs))
    return '\n'.join(lines)

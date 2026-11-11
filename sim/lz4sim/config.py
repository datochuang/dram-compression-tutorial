"""System geometry, policy knobs and timing constants.

All numbers default to the 512 MiB design in docs/lz4-verify/plan512.py so the
simulator, the explainer and the decks describe the same machine.
"""
from dataclasses import dataclass, replace

MiB = 1 << 20


@dataclass(frozen=True)
class SystemConfig:
    # geometry
    page: int = 4096
    chunk: int = 512
    dram_base: int = 0x8000_0000
    pin_img_mib: int = 34
    pin_run_mib: int = 22
    hrt_mib: int = 36
    cot_mib: int = 5
    pool_mib: int = 275
    fc_mib: int = 140
    ro_mib: int = 248
    data_mib: int = 26
    heap_mib: int = 306

    # policy
    compress_limit: int = 3584      # COMPRESS gives up above this many bytes (7 chunks)
    rw_raw_store: bool = False      # store incompressible RW pages raw in 8 chunks instead of keeping them hot
    fc_low: int = 512               # reclaim starts when free frames drop to this
    fc_high: int = 1024             # reclaim stops when free frames reach this

    # baseline free-chunk stack (hardware)
    sram_cap: int = 512
    refill_below: int = 64
    spill_above: int = 448
    list_group: int = 170           # one list chunk holds the other 169 numbers of its group

    # timing
    clock_hz: float = 1.0e9
    decomp_bytes_per_cycle: float = 4.0
    comp_bytes_per_cycle: float = 1.0
    dram_ns: float = 100.0          # one dependent DRAM access
    kernel_fault_ns: float = 3000.0  # kernel work on one page fault, both variants
    kernel_evict_ns: float = 2000.0  # kernel work to pick and unmap one victim, both variants
    kernel_job_ns: float = 300.0     # extra kernel work per job in the software variant (entry, bitmap)
    access_gap_ns: float = 20000.0   # simulated time between two page touches of the workload

    def __post_init__(self):
        if self.page % self.chunk:
            raise ValueError('page must be a multiple of chunk')
        if self.pages * 32 > self.cot_mib * MiB:
            raise ValueError('COT region too small for the page count')
        if self.fc_high >= self.frames or self.fc_low >= self.fc_high:
            raise ValueError('frame watermarks must satisfy low < high < frames')
        if self.refill_below + self.list_group > self.sram_cap or self.spill_above < self.list_group:
            raise ValueError('stack thresholds do not fit the SRAM')
        if self.compress_limit > self.page:
            raise ValueError('compress_limit cannot exceed the page size')

    # derived geometry
    @property
    def chunks_per_page(self):
        return self.page // self.chunk

    @property
    def rw_mib(self):
        return self.data_mib + self.heap_mib

    @property
    def rw_pages(self):
        return self.rw_mib * MiB // self.page

    @property
    def ro_pages(self):
        return self.ro_mib * MiB // self.page

    @property
    def data_pages(self):
        return self.data_mib * MiB // self.page

    @property
    def pages(self):
        return self.rw_pages + self.ro_pages

    @property
    def ro_first(self):
        return self.rw_pages

    @property
    def pool_chunks(self):
        return self.pool_mib * MiB // self.chunk

    @property
    def frames(self):
        return self.fc_mib * MiB // self.page

    @property
    def fixed_mib(self):
        return self.pin_img_mib + self.pin_run_mib + self.hrt_mib + self.cot_mib

    # physical map
    @property
    def pinned_base(self):
        return self.dram_base

    @property
    def hrt_base(self):
        return self.dram_base + (self.pin_img_mib + self.pin_run_mib) * MiB

    @property
    def cot_base(self):
        return self.hrt_base + self.hrt_mib * MiB

    @property
    def pool_base(self):
        return self.cot_base + self.cot_mib * MiB

    @property
    def fc_base(self):
        return self.pool_base + self.pool_mib * MiB

    @property
    def dram_end(self):
        return self.fc_base + self.fc_mib * MiB

    def chunk_pa(self, c):
        return self.pool_base + c * self.chunk

    def frame_pa(self, f):
        return self.fc_base + f * self.page

    def entry_pa(self, h):
        return self.cot_base + h * 32

    def is_ro(self, h):
        return h >= self.ro_first

    def compress_limit_for_rw(self):
        return self.page if self.rw_raw_store else self.compress_limit

    def with_(self, **kw):
        return replace(self, **kw)


# A small machine for unit tests and quick experiments: same structure, 1/64 the size.
SMALL = SystemConfig(pin_img_mib=1, pin_run_mib=1, hrt_mib=1, cot_mib=1, pool_mib=4, fc_mib=2,
                     ro_mib=2, data_mib=1, heap_mib=4, fc_low=16, fc_high=48)

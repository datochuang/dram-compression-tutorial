"""Timing parameters and budgets.

Every number here is an ASSUMPTION until it is replaced by a measurement or a
datasheet value. `source` in PARAM_DOC says where each one came from. Times are
integer nanoseconds.
"""
from dataclasses import dataclass, replace, fields


@dataclass(frozen=True)
class Params:
    # ---- environment
    cores: int = 4                    # CPU cores; one user program per thread, thread i runs on core i mod cores
    think_ns: int = 20000             # user work between two page accesses of one program
    wait_mode: str = 'irq'            # how FW waits for a completion: 'irq' or 'poll'
    # ---- rings
    job_entries: int = 16
    cpl_entries: int = 16
    # ---- LZ4 HW
    engines: int = 4                  # LZ4 engines, CAP.ENGINES: jobs the HW runs at once (4 for now, given 2026-11-13)
    clock_hz: float = 1e9
    comp_bytes_per_cycle: float = 1.0
    decomp_bytes_per_cycle: float = 4.0
    hw_overhead_ns: int = 50          # descriptor decode and job wrap-up
    burst_bytes: int = 256            # one DMA burst
    bus_bytes_per_ns: float = 8.0     # DRAM port throughput seen by the HW master
    bus_setup_ns: int = 20            # address phase and turnaround per burst
    bus_bg_share: float = 0.2         # chance that a HW burst finds the bus taken by other traffic (CPU, HRT)
    bus_bg_burst_ns: int = 100        # how long such a competing burst lasts at most
    reset_ns: int = 200               # soft reset wrap-up after the last burst
    # ---- FW: CPU cost of each step
    mmio_ns: int = 50                 # one register read or write
    fault_entry_ns: int = 600         # exception entry, find the page
    fault_exit_ns: int = 400          # return to user SW, instruction restarts
    frame_alloc_ns: int = 100
    cot_read_ns: int = 100
    cot_write_ns: int = 150
    desc_build_ns: int = 150
    desc_write_ns: int = 100          # store 48 B into the job ring
    cpl_read_ns: int = 80             # load 16 B from the completion ring
    bitmap_reserve_ns: int = 250      # find and mark 7 chunks
    bitmap_release_ns: int = 100
    pte_write_ns: int = 100
    tlb_inval_ns: int = 500           # invalidate one TLB entry on every core
    victim_pick_ns: int = 300
    zero_fill_ns: int = 400
    irq_latency_ns: int = 1000        # interrupt line high to first handler instruction
    irq_handler_ns: int = 150         # fixed handler cost per entry, on top of register and ring accesses
    wakeup_ns: int = 2000             # handler wakes a sleeping thread until it runs again
    poll_interval_ns: int = 200       # polling mode: spin this long between two reads of CPL_TAIL
    job_timeout_ns: int = 1_000_000   # FW gives up waiting for a completion
    # ---- FW: policy
    reclaim_inflight: int = 2         # COMPRESS jobs the reclaimer keeps outstanding at once (1 until 2026-11-13)
    # ---- fault injection
    hw_hang_jobs: tuple = ()          # ordinals (1-based, as fetched) of jobs the HW never finishes
    irq_drop_every: int = 0           # every Nth rising edge of the interrupt line is not delivered
    corrupt_every: int = 0            # every N accesses flip one byte of a compressed RW page

    def with_(self, **kw):
        return replace(self, **kw)

    def cycles_ns(self, n):
        return int(round(n * 1e9 / self.clock_hz))


PARAM_DOC = {
    'cores': ('假設', '跑 user SW 的 core 數'),
    'think_ns': ('lz4sim 的 access_gap_ns', '一個 user SW 兩次 page access 之間自己做事的時間，ns'),
    'wait_mode': ('設計選擇', 'FW 等 completion 的方式，irq 或 poll'),
    'job_entries': ('假設', 'job ring 的格數'),
    'cpl_entries': ('假設', 'completion ring 的格數'),
    'engines': ('負責人暫定，2026-11-13', 'LZ4 engine 的數量 N，也就是 `CAP.ENGINES`。HW 同時執行的 job 數上限'),
    'clock_hz': ('lz4sim', 'LZ4 HW 的 clock，Hz'),
    'comp_bytes_per_cycle': ('lz4sim', 'COMPRESS 每個 clock 吃進幾個 byte'),
    'decomp_bytes_per_cycle': ('lz4sim', 'DECOMPRESS 每個 clock 吐出幾個 byte'),
    'hw_overhead_ns': ('假設', '每個 job 解讀 descriptor 與收尾的時間，ns'),
    'burst_bytes': ('假設', 'HW 一個 bus burst 的大小，B'),
    'bus_bytes_per_ns': ('假設', 'HW 在 DRAM port 上的 throughput，B 每 ns'),
    'bus_setup_ns': ('假設', '每個 burst 的固定開銷，ns'),
    'bus_bg_share': ('假設', 'DRAM port 被 CPU 與 HRT 流量佔住的時間比例'),
    'bus_bg_burst_ns': ('假設', '擋在前面的 burst 最長多久，ns'),
    'reset_ns': ('假設', 'soft reset 收尾的時間，ns'),
    'mmio_ns': ('假設', '讀或寫一個 register，ns'),
    'fault_entry_ns': ('假設', '進入 page fault 到找到 page，ns'),
    'fault_exit_ns': ('假設', '從 page fault 返回，ns'),
    'frame_alloc_ns': ('假設', '拿一個 free frame，ns'),
    'cot_read_ns': ('假設', '讀一筆 COT entry，ns'),
    'cot_write_ns': ('假設', '寫一筆 COT entry，ns'),
    'desc_build_ns': ('假設', '填好一個 descriptor，ns'),
    'desc_write_ns': ('假設', '把 48 B 的 descriptor 寫進 job ring，ns'),
    'cpl_read_ns': ('假設', '從 completion ring 讀 16 B，ns'),
    'bitmap_reserve_ns': ('假設', '在 bitmap 找到並預留 7 個 chunk，ns'),
    'bitmap_release_ns': ('假設', '在 bitmap 釋放 chunk，ns'),
    'pte_write_ns': ('假設', '寫一個 PTE，ns'),
    'tlb_inval_ns': ('假設', '在每個 core 清掉一筆 TLB entry，ns'),
    'victim_pick_ns': ('假設', '挑一個 victim page，ns'),
    'zero_fill_ns': ('假設', '把一個 frame 補零，ns'),
    'irq_latency_ns': ('假設', 'interrupt line 拉高到 handler 第一個指令，ns'),
    'irq_handler_ns': ('假設', 'handler 每次進入的固定開銷，ns'),
    'wakeup_ns': ('假設', 'handler 叫醒 thread 到它真的開始跑，ns'),
    'poll_interval_ns': ('假設', 'polling 時兩次讀 CPL_TAIL 的間隔，ns'),
    'job_timeout_ns': ('假設', 'FW 等 completion 的 timeout，ns'),
    'reclaim_inflight': ('設計選擇。負責人 2026-11-13 同意從 1 改掉，2 是照模擬選的', 'reclaimer 同時在外的 COMPRESS job 數'),
}


@dataclass(frozen=True)
class Budgets:
    """Provisional targets. They are placeholders until the user gives real ones."""
    fault_p50_ns: int = 10_000        # page fault that needs DECOMPRESS: median, access to instruction restart
    fault_p99_ns: int = 30_000
    fault_max_ns: int = 100_000
    kernel_cpu_share: float = 0.05    # kernel CPU time for compression over total core time
    engine_util: float = 0.50         # LZ4 engine busy share
    job_ring_peak: float = 0.50       # peak job ring occupancy over usable entries
    frame_waits: int = 0              # faults that found no free frame
    lost_pages: int = 0

    def items(self):
        return [(f.name, getattr(self, f.name)) for f in fields(self)]

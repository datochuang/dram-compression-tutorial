# Kernel SW 每個步驟的細節：資料結構、所在、運算、cycle、相依，第 0 版

> 這份文件由 `python3 sim/run_host.py gen-steps` 產生。表格來自 `sim/hostsim/micro.py` 與 `sim/hostsim/deps.py`。
> 指令數是把 `sim/kstep/kstep.h` 編譯後實際執行量到的，存在 `kernel-step-detail-v0.json`。加上 `--reuse` 只重新排版，不重量。
> 第 0、5、6 節是對這一版數字手寫的。重量之後數字有變的話，這三節要重讀一次。
> 這份文件只有分析與提案。`kernel.py` 沒有為了效能做任何修改。

## 0. 結論

這份文件回答四個問題：每個步驟讀寫哪個資料結構、那個資料結構放在哪、做了什麼運算、要多少 cycle。第五個問題是哪些步驟真的有先後關係，答案沿用相依圖文件 `kernel-sw-dependency-v0.md` 的推導，這裡把它放到每個步驟旁邊。

數字分成三種，全文都標明是哪一種。

| 種類 | 怎麼來的 | 可信到哪裡 |
|---|---|---|
| 量測 | 指令數。把步驟寫成固定 layout 的 C，用 Apple clang version 15.0.0 (clang-1500.3.9.4) 以 `-O2` 編成 AArch64，執行後讀 CPU 的指令計數器 | 換 compiler 或換指令集會變，量級不會變 |
| 計數 | 碰到幾條 cache line、寫幾次 LZ4 HW register、做幾次 cache 維護操作。從 layout 與介面規格數出來 | 只要 layout 不變就是確定的 |
| 假設 | 把指令數與 line 數換成 cycle 的模型，以及 exception、interrupt、叫醒 thread、TLB invalidate 的時間 | 取決於用哪顆 CPU 與哪個 OS，是 K1 |

結論有六點。

1. **kernel 自己查表改表的工作很小。** 一次 RO page 的 fault，kernel 量得到的步驟加起來是 137 道指令、9 條新的 cache line、2 次 register 寫入。照第 1 節的模型是 337 到 1 137 cycle。同一批步驟在 `ifsim.params` 裡原本假設 680 ns，量級相符。
2. **一次 fault 的時間不在 kernel 的表上。** 同一次 RO fault 還要加上假設的 exception 進出、interrupt、叫醒 thread 共 4 150 ns，以及 LZ4 HW 模型的 1 269 ns。合計約 5 756 到 6 556 ns，kernel 的表只佔 6% 到 17%。所以 K1 的答案比任何表的最佳化都重要。
3. **在 kernel 的表上，cache line 比指令重要。** RO fault 的上限 1 137 cycle 裡，79% 是把 line 從 DRAM 讀進來。原因是每個 page 的資訊分散在 `state`、`frame_of`、`fresh_n`、`pins`、`cot`、`pte` 六張表，各佔一條 line。
4. **唯一不小的是 clock 掃描。** 全尺寸的執行裡每選一個 page 平均看 4.9 個 frame。每路過一個 frame 最多碰 4 條新的 line。照模型是 83 到 2 299 cycle，原本的假設是 300 ns。最長的一次看了 35 841 個 frame，整段握著 `mm_lock`，照模型約 1.4 到 15.8 ms。
5. **在 bitmap 找空位不需要硬體幫忙。** 找一個 0 是 `MVN`、`RBIT`、`CLZ` 三道指令。保留 7 個 chunk 量到 111 道指令。全尺寸的執行裡每次平均掃 1.06 個 word，最多 2 個。
6. **握 lock 的時間很短。** RO fault 的第 A 段是 39 道指令與 4 條 line，第 B 段是 35 道與 3 條。照模型兩段各不到 0.5 µs，不含叫醒等待者的 OS 呼叫。趕出 RW page 的第 A 段是 167 道與 6 條，另外加上假設 500 ns 的 TLB invalidate。

## 1. 方法

### 1.1 指令數怎麼量

Python 的模型把表放在抽象的容器裡，看不出一個步驟要幾道指令。所以把同一份控制程序另外寫成 C，放在 `sim/kstep/kstep.h`。每個步驟是一個 always-inline 的函式，表的 layout 固定，如第 2 節。

量測程式是 `sim/kstep/measure.c`。每個步驟有兩個版本：一個只準備參數，一個準備參數後執行步驟。兩個版本各呼叫幾萬次，前後讀 `proc_pid_rusage` 的 `ri_instructions`，相減再除以次數就是這個步驟的指令數。重複 5 次取最小值。

驗證有兩道。一是校正步驟：放 5 個 `NOP` 進去，量到的是 5。二是對幾個步驟逐一讀反組譯的結果，`unlock` 2 道、`wake_check` 2 道、`put_frame` 13 道、`check_state` 14 道，都與量到的相同。

編譯選項：`-O2`

46 個步驟裡有 29 個量得到。其餘的不是 kernel 的表格工作：CPU 硬體做的、OS 做的、LZ4 HW 做的、整頁的 cache 維護、軟體解壓縮。它們列在第 6 節。

### 1.2 cache line 怎麼數

一條 cache line 是 64 B。每個步驟宣告它讀寫哪張表的哪一筆，宣告與 `deps.py` 的讀寫集合逐一核對過。一個動作第一次碰到某張表的某一筆時，算一條新的 line。同一個動作後來再碰同一筆，不再算。

三種情況不算新的 line。一是 `scalars`：十幾個 kernel 的純量放在同一條 line，每個動作都用，假設它一直在 cache 裡。二是 thread 自己的 stack 與 CPU register。三是 free frame 的 stack 頂端：剛放回去的馬上又被拿走。

循序讀的表只有 clock 掃描的 `owner[hand]`，每 16 筆才換一條 line，沒有算進新的 line。同一筆資料換個名字再出現也不重複算：指針停下的那個 frame 就是後來 `put_frame` 的 `f`，`reserve` 改過的 word 就是後來 `trim` 還 bit 的 word。

`cpl_ring` 是例外的另一邊：completion 是 LZ4 HW 寫進 DRAM 的，kernel 讀它一定是從 DRAM 讀，介面規格的 FW-CACHE-3 也是這樣要求。所以這一條 line 連下限也算進去。

### 1.3 換成 cycle 的模型

| 假設 | 值 | 來源 |
|---|---|---|
| CPU 時脈 | 1000 MHz | 1 cycle 等於 1 ns，數字可以直接和 `ifsim.params` 的 ns 並排。待 K1 |
| 每道指令的 cycle | 1.0 | 需要的 line 都在 L1 cache 裡的時候。待 K1 |
| 一條 line 從 DRAM 進來 | 100 cycle | `lz4sim.config` 的 `dram_ns` 100 ns |
| 寫一次 LZ4 HW register | 50 cycle | `ifsim.params` 的 `mmio_ns` 50 ns |

一個步驟的下限是「指令數加上 register 寫入」，也就是需要的 line 都已經在 L1 cache；唯一的例外是 `cpl_ring` 那一條，它一定從 DRAM 讀，下限就含它的 100 cycle。上限是再加上其餘每條新的 line 100 cycle，也就是全部從 DRAM 讀。真實的數字在兩者之間，取決於 L2 cache 有多大。pinned 區裡的 kernel 表加起來約 1.6 MiB，page table 另外 1.1 MiB，COT 是 4.5 MiB。

## 2. 資料結構放在哪

### 2.1 DRAM 的分區

數字是全尺寸設定 `SystemConfig()`。

| 區域 | 起點 | 終點 | 大小 | 放什麼 |
|---|---|---|---|---|
| pinned 區 | 0x80000000 | 0x83800000 | 56.0 MiB | kernel 的程式與所有 kernel 記憶體、page table、兩個 ring |
| HRT 區 | 0x83800000 | 0x85c00000 | 36.0 MiB | HRT client 的記憶體，不壓縮，這份文件的步驟都不碰 |
| COT 區 | 0x85c00000 | 0x86100000 | 5.0 MiB | `cot` |
| chunk pool | 0x86100000 | 0x97400000 | 275.0 MiB | `chunk` |
| frame 區 | 0x97400000 | 0xa0000000 | 140.0 MiB | `frame` |

### 2.2 每張表

| 資料結構 | 放在哪 | 固定位址 | 一筆 | 筆數 | 總大小 | cache line 數 | 內容 |
|---|---|---|---|---|---|---|---|
| `state` | kernel 記憶體（pinned） |  | 1 B | 148 480 | 145 KiB | 2 320 | 每個 page 的狀態，6 個值 |
| `frame_of` | kernel 記憶體（pinned） |  | 4 B | 148 480 | 580 KiB | 9 280 | 每個 page 現在在哪個 frame，沒有就是 -1 |
| `fresh_n` | kernel 記憶體（pinned） |  | 2 B | 148 480 | 290 KiB | 4 640 | 這個 page 在幾個 thread 的 fresh 名單裡 |
| `pins` | kernel 記憶體（pinned） |  | 2 B | 148 480 | 290 KiB | 4 640 | `pin_page` 的計數 |
| `incompressible` | kernel 記憶體（pinned） |  | 1 bit | 148 480 | 18 KiB | 290 | 每個 page 一個 bit：壓不進 7 個 chunk |
| `owner` | kernel 記憶體（pinned） |  | 4 B | 35 840 | 140 KiB | 2 240 | 每個 frame 屬於哪個 page，空的就是 -1 |
| `free_stack` | kernel 記憶體（pinned） |  | 4 B | 35 840 | 140 KiB | 2 240 | free frame 的 stack，`free_top` 是個數 |
| `bitmap` | kernel 記憶體（pinned） |  | 8 B | 8 800 | 69 KiB | 1 100 | 每個 chunk 一個 bit，1 是使用中；`cursor` 是下次開始找的 word |
| `scalars` | kernel 記憶體（pinned） |  | 48 B | 1 | 48 B | 1 | `free_top`、`hand`、`cursor`、`free_chunks`、`tag`、`strikes`、`job_tail`、`cpl_head`、`frame_waiters`、`pool_full`、`lz4_off`、`mm_lock` |
| `fresh` | kernel 記憶體（pinned） |  | 8 B | 4 | 32 B | 1 | 每個 thread 一份：最近 fault 進來的 page（`protect` = 1） |
| `cot` | DRAM 的 COT 區 | 0x85c00000 | 32 B | 148 480 | 4.5 MiB | 74 240 | 每個 page 的 COT entry：flags、chunk 數、stream 長度、CRC-32、8 個 3 B 的 chunk 編號 |
| `pte` | CPU MMU 的 page table |  | 8 B | 148 480 | 1.1 MiB | 18 560 | PTE：frame 位址、valid（bit 0）、accessed flag（bit 10） |
| `job_ring` | ring 記憶體（pinned） |  | 64 B | 16 | 1.0 KiB | 16 | job ring，一格 64 B，descriptor 用前 48 B |
| `cpl_ring` | ring 記憶體（pinned） |  | 16 B | 16 | 256 B | 4 | completion ring，一筆 16 B |
| `reg` | LZ4 HW register |  | 4 B | 2 | 8 B | 1 | `JOB_TAIL`（0x28，doorbell）與 `CPL_HEAD`（0x3C） |
| `frame` | DRAM 的 frame 區 | 0x97400000 | 4096 B | 35 840 | 140.0 MiB | 2 293 760 | page 解開後的內容 |
| `chunk` | DRAM 的 chunk pool | 0x86100000 | 512 B | 563 200 | 275.0 MiB | 4 505 600 | 壓縮後的 stream |

沒有固定位址的表在 pinned 區裡，位址由 linker 決定。pinned 區不經過壓縮層，kernel 碰它不會發生 page fault。

以 page 編號 `h` 當索引的表有六張：`state`、`frame_of`、`fresh_n`、`pins`、`cot`、`pte`。處理一個 page 的時候，這六張表的第 `h` 筆在六條不同的 line 上。以 frame 編號 `f` 當索引的是 `owner` 與 `free_stack`。

這個 layout 是 C 參考實作為了能量測而選的，其中幾項還沒有經過你決定，列在 6.2。

## 3. 每個步驟

### 3.1 總表

| 步驟 | 誰 | 讀寫的資料與所在 | 運算 | 指令數 | 碰到的 cache line | 依據 |
|---|---|---|---|---|---|---|
| `lock` | FW | `mm_lock` RW 1 B，kernel 記憶體（pinned） | atomic exchange（`SWPAB`），沒有人握著時一次就拿到。有人握著時要等，等多久不在這裡 | 4 | 0 | 量測 |
| `unlock` | FW | `mm_lock` W 1 B，kernel 記憶體（pinned） | `STLRB` 寫 0 | 2 | 0 | 量測 |
| `access` | CPU | 無 | CPU MMU：TLB 裡沒有這一頁，硬體走 page table，讀到的 PTE bit 0 是 0 |  | 0 | CPU 硬體 |
| `exception` | CPU | 無 | CPU 存下 PC 與狀態，跳到 exception vector；kernel 讀出 fault 位址，`h = (va - base) >> 12` | 假設 600 ns | 0 | 假設 |
| `eret` | CPU | 無 | kernel 還原現場，`ERET` 回到 user SW | 假設 400 ns | 0 | 假設 |
| `rerun` | CPU | 無 | CPU 重跑同一道指令：TLB 還是沒有這一頁，硬體再走一次 page table，這次 PTE 是 valid |  | 0 | CPU 硬體 |
| `kill` | FW | 無 | OS：結束這個 user SW |  | 0 | OS，未計 |
| `check_state` | FW | `state[h]` R 1 B，kernel 記憶體（pinned）<br>`free_top` R 4 B，kernel 記憶體（pinned） | 讀 1 個 byte；依序比對 PRESENT、LOST、COMPRESSING 或 DECOMPRESSING；再看 `free_top` 是不是 0 | 14 | `state` 1 條 | 量測 |
| `wait_page` | FW | 無 | OS：把 thread 掛到 page h 的等待佇列，放開 lock 睡著 |  | 0 | OS，未計 |
| `wait_frame` | FW | `frame_waiters` RW 4 B，kernel 記憶體（pinned） | OS：叫醒 reclaimer，把 thread 掛到等 frame 的佇列，放開 lock 睡著 |  | 0 | OS，未計 |
| `take_frame` | FW | `free_top` RW 4 B，kernel 記憶體（pinned）<br>`free_stack[top]` R 4 B，kernel 記憶體（pinned）<br>`frame_of[h]` W 4 B，kernel 記憶體（pinned）<br>`owner[f]` W 4 B，kernel 記憶體（pinned） | stack pop：`f = free_stack[--free_top]`；兩個 store；`pa = fc_base + (f << 12)` | 12 | `frame_of` 1 條；`owner` 1 條 | 量測 |
| `zero_frame` | FW | `frame[f]` W 4096 B，DRAM 的 frame 區 | `DC ZVA` 64 次，一次把一條 64 B 的 line 清成 0，不必先從 DRAM 讀進來。C library 的 memset；換一個 library 指令數會變 | 341 | `frame` 64 條 | 量測 |
| `cot_read` | FW | `cot[h]` R 32 B，DRAM 的 COT 區 | 位址 `cot_base + h * 32`；讀 32 B（兩個 16 B 的 load）到 stack；測 valid flag | 6 | `cot` 1 條 | 量測 |
| `mark_decompressing` | FW | `lz4_off` R 1 B，kernel 記憶體（pinned）<br>`state[h]` W 1 B，kernel 記憶體（pinned） | 讀 `lz4_off` 決定用不用 HW；寫 1 個 byte | 7 | `state` 1 條 | 量測 |
| `note_hw` | FW | `strikes` RW 4 B，kernel 記憶體（pinned）<br>`lz4_off` RW 1 B，kernel 記憶體（pinned） | 答對就把 `strikes` 歸零，答錯加 1；到 3 就把 `lz4_off` 寫成 1 | 5 | 0 | 量測 |
| `cot_clear` | FW | `cot[h]` W 32 B，DRAM 的 COT 區 | 把 32 B 寫成 0（兩個 16 B 的 store） | 4 | `cot` 1 條 | 量測 |
| `release_chunks` | FW | `bitmap[w]` RW 8 B，kernel 記憶體（pinned）<br>`free_chunks` W 4 B，kernel 記憶體（pinned）<br>`pool_full` W 1 B，kernel 記憶體（pinned） | 對每個 chunk：從 COT entry 的 3 個 byte 組出編號 c，`bitmap[c >> 6] &= ~(1 << (c & 63))`；`free_chunks += n`；`pool_full = 0` | 80 | `bitmap` 1 條 | 量測 |
| `set_present` | FW | `state[h]` W 1 B，kernel 記憶體（pinned） | 寫 1 個 byte | 3 | `state` 1 條 | 量測 |
| `set_lost` | FW | `state[h]` W 1 B，kernel 記憶體（pinned） | 寫 1 個 byte | 3 | `state` 1 條 | 量測 |
| `pte_map` | FW | `pte[h]` W 8 B，CPU MMU 的 page table | `pte = pa | 屬性 | accessed | valid`，一個 8 B 的 store。PTE 從 invalid 變 valid 不必清 TLB；CPU 要求的 barrier 沒有算進去 | 6 | `pte` 1 條 | 量測 |
| `wake_page` | FW | 無 | OS：page h 的等待佇列裡有人就叫醒；沒有人時只是一次比較 |  | 0 | OS，未計 |
| `note_fresh` | FW | `fresh[t]` RW 8 B，kernel 記憶體（pinned）<br>`fresh_n[h]` RW 2 B，kernel 記憶體（pinned）<br>`fresh_n[old]` RW 2 B，kernel 記憶體（pinned） | 這個 thread 的名單換進 h、換出上一個 page old；`fresh_n[h]++`；`fresh_n[old]--` | 19 | `fresh_n` 1 條；`fresh_n` 1 條 | 量測 |
| `wake_check` | FW | `free_top` R 4 B，kernel 記憶體（pinned） | 比較 `free_top <= fc_low`。比較成立時叫醒 reclaimer 是一次 OS 呼叫，沒有算進去 | 2 | 0 | 量測 |
| `desc` | FW | `tag` RW 4 B，kernel 記憶體（pinned） | `tag` 做 atomic 加 1；在 stack 上填 48 B：opcode、chunk 數、limit、frame 位址、長度、CRC-32、tag、8 個 3 B 的 chunk 編號 | 26 或 55 | 0 | 量測 |
| `submit` | FW | `job_tail` RW 4 B，kernel 記憶體（pinned）<br>`job_ring[tail]` W 48 B，ring 記憶體（pinned）<br>`JOB_TAIL` W 4 B，LZ4 HW register | 把 48 B 複製到 `job_ring[tail]`（3 個 16 B 的 store）；`tail = (tail + 1) & 15`；寫 register `JOB_TAIL`。`FW-CACHE-3`：ring 是 cacheable 的話，寫 doorbell 之前還要 clean 這一條 line | 13 | `job_ring` 1 條 | 量測 |
| `hw_decompress` | HW | 無 | LZ4 HW：讀 descriptor、讀 chunk、核對 CRC-32、解壓縮寫進 frame、寫 completion、拉 interrupt | 模型 1 269 ns | 0 | LZ4 HW 模型 |
| `hw_fail` | HW | 無 | LZ4 HW：沒有把 page 交出來，completion 的 status 不是 OK | 模型 1 269 ns | 0 | LZ4 HW 模型 |
| `hw_compress` | HW | 無 | LZ4 HW：讀 descriptor、讀 frame、壓縮寫進 chunk、算 CRC-32、寫 completion、拉 interrupt | 模型 4 266 ns | 0 | LZ4 HW 模型 |
| `notify` | FW | 無 | interrupt 進 CPU；handler 確認是 LZ4 HW；OS 把睡著的 thread 排回去跑 | 假設 3 150 ns | 0 | 假設 |
| `cpl_read` | FW | `cpl_head` RW 4 B，kernel 記憶體（pinned）<br>`cpl_ring[head]` R 16 B，ring 記憶體（pinned）<br>`CPL_HEAD` W 4 B，LZ4 HW register | 從 `cpl_ring[head]` 讀 16 B；`head = (head + 1) & 15`；寫 register `CPL_HEAD`；比對 tag。這 16 B 是 LZ4 HW 剛寫的，CPU cache 裡不會有：一定是一次 DRAM 讀取 | 12 | `cpl_ring` 1 條，一定從 DRAM | 量測 |
| `cache_invalidate` | FW | `frame[f]` W 4096 B，DRAM 的 frame 區 | 對 frame 的 64 條 line 各做一次 `DC IVAC`，instruction cache 另做 | 64 次 cache 操作 | `frame` 64 條 | 計數 |
| `sw_decode` | FW | `chunk[c]` R 512 B，DRAM 的 chunk pool | kernel 自己的 LZ4 decoder：讀最多 7 個 chunk，核對 CRC-32，解出 4096 B 到 kernel 的 buffer | 沒有量 | `chunk` 64 條 | 未知 |
| `frame_write` | FW | `frame[f]` W 4096 B，DRAM 的 frame 區 | 把 4096 B 從 kernel 的 buffer 複製進 frame。C library 的 memcpy；換一個 library 指令數會變 | 791 | `frame` 64 條 | 量測 |
| `sw_clean` | FW | `frame[f]` W 4096 B，DRAM 的 frame 區 | 對 frame 的 64 條 line 各做一次 `DC CVAC`：dirty 的 line 寫回 DRAM | 64 次 cache 操作 | `frame` 64 條 | 計數 |
| `reclaim_check` | FW | `free_top` R 4 B，kernel 記憶體（pinned） | 比較 `free_top < fc_high` | 2 | 0 | 量測 |
| `pick_victim` | FW | `hand` RW 4 B，kernel 記憶體（pinned）<br>`owner[hand]` R 4 B，kernel 記憶體（pinned）<br>`state[h]` R 1 B，kernel 記憶體（pinned）<br>`pins[h]` R 2 B，kernel 記憶體（pinned）<br>`fresh_n[h]` R 2 B，kernel 記憶體（pinned）<br>`pool_full`、`lz4_off` R 2 B，kernel 記憶體（pinned）<br>`incompressible[h]` R 1 bit，kernel 記憶體（pinned）<br>`pte[h]` RW 8 B，CPU MMU 的 page table | clock 掃描，每看一個 frame：`h = owner[hand++]`；`state[h]` 是不是 PRESENT；`pins[h] | fresh_n[h]`；RW page 再看 `pool_full`、`lz4_off` 與 incompressible 的那個 bit；最後測 PTE 的 bit 10，是 1 就清成 0 並放過它 | 見 3.3 | `owner` 每 16 筆 1 條；`state` 1 條；`pins` 1 條；`fresh_n` 1 條；`pte` 1 條 | 量測 |
| `reserve` | FW | `cursor`、`free_chunks` RW 8 B，kernel 記憶體（pinned）<br>`bitmap[cursor]` RW 8 B，kernel 記憶體（pinned）<br>`pool_full` W 1 B，kernel 記憶體（pinned） | 從 `bitmap[cursor]` 開始一次讀一個 64-bit word；全是 1 就跳到下一個 word；否則取反，用 `RBIT` 加 `CLZ` 找最低的 free bit（count trailing zeros），`x &= x - 1` 清掉它，重複到拿滿 7 個；把 word 寫回去 | 見 3.3 | `bitmap` 1 條 | 量測 |
| `find_frame` | FW | `frame_of[h]` R 4 B，kernel 記憶體（pinned） | 讀 4 B；`pa = fc_base + (f << 12)` | 5 | `frame_of` 1 條 | 量測 |
| `pte_clear` | FW | `pte[h]` W 8 B，CPU MMU 的 page table | 把 8 B 寫成 0 | 2 | `pte` 1 條 | 量測 |
| `tlb_inval` | FW | 無 | `TLBI`（所有 core）、`DSB`、`ISB`：3 道指令，時間花在等所有 core 完成 | 假設 500 ns | 0 | 假設 |
| `mark_compressing` | FW | `state[h]` W 1 B，kernel 記憶體（pinned） | 寫 1 個 byte | 3 | `state` 1 條 | 量測 |
| `cache_clean` | FW | `frame[f]` W 4096 B，DRAM 的 frame 區 | 對 frame 的 64 條 line 各做一次 `DC CVAC`：dirty 的 line 寫回 DRAM | 64 次 cache 操作 | `frame` 64 條 | 計數 |
| `cot_store` | FW | `cot[h]` W 32 B，DRAM 的 COT 區 | 在 stack 上組 32 B：flags、chunk 數、長度、CRC-32、每個 chunk 編號拆成 3 個 byte；兩個 16 B 的 store | 44 | `cot` 1 條 | 量測 |
| `trim` | FW | `bitmap[w]` RW 8 B，kernel 記憶體（pinned）<br>`free_chunks` W 4 B，kernel 記憶體（pinned） | 對沒用到的每個 chunk：`bitmap[c >> 6] &= ~(1 << (c & 63))`；`free_chunks += n` | 18 | `bitmap` 1 條 | 量測 |
| `release_all` | FW | `bitmap[w]` RW 8 B，kernel 記憶體（pinned）<br>`free_chunks` W 4 B，kernel 記憶體（pinned） | 7 個 chunk 的 bit 全部清成 0；`free_chunks += 7` | 51 | `bitmap` 1 條 | 量測 |
| `mark_incompressible` | FW | `incompressible[h]` RW 1 bit，kernel 記憶體（pinned） | `incompressible[h >> 6] |= 1 << (h & 63)` | 8 | 0 | 量測 |
| `put_frame` | FW | `frame_of[h]` RW 4 B，kernel 記憶體（pinned）<br>`owner[f]` W 4 B，kernel 記憶體（pinned）<br>`free_top` RW 4 B，kernel 記憶體（pinned）<br>`free_stack[top]` W 4 B，kernel 記憶體（pinned）<br>`frame_waiters` RW 4 B，kernel 記憶體（pinned） | `f = frame_of[h]`；`frame_of[h] = -1`；`owner[f] = -1`；stack push；看有沒有人在等 frame。有人在等時叫醒他們是一次 OS 呼叫，沒有算進去 | 13 | `frame_of` 1 條；`owner` 1 條 | 量測 |
| `set_compressed` | FW | `state[h]` W 1 B，kernel 記憶體（pinned） | 寫 1 個 byte | 3 | `state` 1 條 | 量測 |

表中的 `h` 是 page 編號，`f` 是 frame 編號，`t` 是 thread，`old` 是這個 thread 的 fresh 名單裡被擠掉的那個 page。指令數是範例情況：一個 page 壓成 5 個 chunk，COMPRESS 預留 7 個 chunk。

### 3.2 與原本假設的對照

`ifsim.params` 裡 kernel 步驟的成本原本都是整數的假設。下表把假設與量到的放在一起。

| 步驟 | `ifsim.params` 的假設 | 假設 ns | 量到的指令數 | cache line | register 寫入 | 模型 cycle |
|---|---|---|---|---|---|---|
| `take_frame` | `frame_alloc_ns` | 100 | 12 | 2 |  | 12 到 212 |
| `zero_frame` | `zero_fill_ns` | 400 | 341 | 0 |  | 341 到 341 |
| `cot_read` | `cot_read_ns` | 100 | 6 | 1 |  | 6 到 106 |
| `cot_clear` | `cot_write_ns` | 150 | 4 | 1 |  | 4 到 104 |
| `cot_store` | `cot_write_ns` | 150 | 44 | 1 |  | 44 到 144 |
| `release_chunks` | `bitmap_release_ns` | 100 | 80 | 1 |  | 80 到 180 |
| `pte_map` | `pte_write_ns` | 100 | 6 | 1 |  | 6 到 106 |
| `desc` | `desc_build_ns` | 150 | 26 | 0 |  | 26 到 26 |
| `submit` | `desc_write_ns`、`mmio_ns` | 150 | 13 | 1 | 1 | 63 到 163 |
| `cpl_read` | `cpl_read_ns` | 80 | 12 | 1 | 1 | 62 到 162 |
| `reserve` | `bitmap_reserve_ns` | 250 | 111 | 1 |  | 111 到 211 |
| `pick_victim` | `victim_pick_ns` | 300 | 44 | 5 |  | 44 到 544 |

大部分假設落在模型的上下限之間。兩個例外：`desc` 假設 150 ns，量到 26 或 55 道指令而且不碰新的 line；`pick_victim` 假設 300 ns，只看一個 frame 就已經可能超過，見下一小節。

### 3.3 成本隨數量變的步驟

**clock 掃描 `pick_victim`。** 指針每前進一格看一個 frame。

| clock 掃描看的 frame | 指令數 | 碰到的 cache line |
|---|---|---|
| 最後選中的那一個，RW page | 44 | `owner`、`state`、`pins`、`fresh_n`、`pte` 各 1 條 |
| 最後選中的那一個，RO page | 33 | 同上 |
| 路過一個空的 frame | 10 | 只有 `owner`，每 16 個 frame 1 條 |
| 路過一個 fresh 的 page | 20 | `state`、`pins`、`fresh_n` 各 1 條 |
| 路過一個已知壓不小的 RW page | 33 | `state`、`pins`、`fresh_n` 各 1 條 |
| 路過一個 accessed 的 page，並清掉 bit 10 | 40 | `state`、`pins`、`fresh_n`、`pte` 各 1 條 |

路過的 frame 之所以貴，是因為 frame 連續而 page 不連續：`owner[hand]` 是循序的，但是它給出的 `h` 沒有規律，所以 `state[h]`、`pins[h]`、`fresh_n[h]`、`pte[h]` 每個 frame 都落在新的 line 上。

**在 bitmap 保留 chunk `reserve`。** 從 `cursor` 指的 word 開始，對每個 word 取反、`RBIT`、`CLZ` 找到最低的 0，設成 1，再用 `x &= x - 1` 的方式找下一個。量到每個 chunk 約 14 道指令，每掃過一個 word 約 7 道。

| bitmap 的樣子 | 掃過的 word | 指令數 |
|---|---|---|
| 全部是空的 | 1.11 | 106 |
| 每個 word 剩 7 個 0 | 2 | 111 |
| 每 10 個 word 才有一個不是全 1，那一個剩 7 個 0 | 11 | 174 |
| 每個 word 只剩 1 個 0 | 7 | 220 |

**實際執行時走多遠。** 下表來自 host simulation 的兩次執行。

| 設定 | 存取次數 | frame 數 | clock 選了幾次 | 每次平均看幾個 frame | 最長一次 | `reserve` 次數 | 每次平均掃幾個 word | 最多 |
|---|---|---|---|---|---|---|---|---|
| `full` | 400 000 | 35 840 | 46 692 | 4.9 | 35 841 | 31 364 | 1.06 | 2 |
| `small` | 20 000 | 512 | 1 747 | 4.7 | 513 | 1 303 | 1.06 | 2 |

最長的那一次掃描發生在開機後 frame 第一次用完的時候：每個 page 的 accessed flag 都是 1，指針要繞完整圈把它們清掉。這是控制程序文件的 D3。

## 4. 每個場景

每個場景一張表，一列一個步驟，照程式執行的順序。「要等誰做完」只列真正的相依，來源是 `deps.reduced`：「資料」表示後面的步驟要用前面寫出的值，「規則」表示順序是正確性規則要求的，「返回」表示要等它做完才能離開 exception。兩個步驟之間如果沒有列出關係，它們的先後只是程式寫的順序，可以對調。

「新的 line」與「cycle」的算法在第 1 節。`lock` 與 `unlock` 沒有編號，因為它們不在相依圖裡，但是指令數算在合計內。

各場景的合計如下。

| 場景 | 指令數 | 新的 line | register 寫入 | 模型 cycle | 同一批步驟原本的假設 ns | CPU 與 OS 的假設 ns | LZ4 HW 模型 ns | 沒有數字的步驟 |
|---|---|---|---|---|---|---|---|---|
| `first_touch` | 403 | 6 | 0 | 403 到 1 003 | 600 | 1 000 |  |  |
| `fault_ro` | 137 | 9 | 2 | 337 到 1 137 | 680 | 4 150 | 1 269 | `cache_invalidate` |
| `fault_rw` | 221 | 10 | 2 | 421 到 1 321 | 930 | 4 150 | 1 269 | `cache_invalidate` |
| `fault_rescue` | 1012 | 10 | 2 | 1 212 到 2 112 | 930 | 4 150 | 1 269 | `cache_invalidate`、`sw_decode`、`sw_clean` |
| `fault_lost` | 123 | 6 | 2 | 323 到 823 | 580 | 3 750 | 1 269 | `cache_invalidate`、`sw_decode` |
| `evict_ro` | 59 | 5 | 0 | 59 到 559 | 400 | 500 |  |  |
| `evict_rw` | 342 | 9 | 2 | 542 到 1 342 | 1 280 | 3 650 | 4 266 | `cache_clean` |
| `evict_rw_incompressible` | 332 | 8 | 2 | 532 到 1 232 | 1 230 | 3 650 | 4 266 | `cache_clean` |

### 4.1 `first_touch`：第一次碰一個 RW page（沒有 LZ4 job）

kernel 自己跑、量得到的步驟共 9 個：403 道指令，6 條新的 cache line，0 次 register 寫入。照第 1 節的模型是 403 到 1 003 cycle。握 lock 的部分：第 A 段 397 道指令、6 條新的 line，397 到 997 cycle。

| # | 步驟 | 誰 | lock 段 | 讀寫 | 指令數 | 新的 line | cycle | 要等誰做完 |
|---|---|---|---|---|---|---|---|---|
| 1 | `access` | CPU |  |  |  |  | CPU 硬體，未計 | 沒有：最先能做 |
| 2 | `exception` | CPU |  |  |  |  | 假設 600 | 1 `access`（規則） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 3 | `check_state` | kernel | A | `state[h]` R 1 B<br>`free_top` R 4 B | 14 | 1 | 14 到 114 | 2 `exception`（規則） |
| 4 | `take_frame` | kernel | A | `free_top` RW 4 B<br>`free_stack[top]` R 4 B<br>`frame_of[h]` W 4 B<br>`owner[f]` W 4 B | 12 | 2 | 12 到 212 | 3 `check_state`（資料：free_frames） |
| 5 | `zero_frame` | kernel | A | `frame[f]` W 4096 B | 341 |  | 341，另寫 64 條 line | 4 `take_frame`（資料：f） |
| 6 | `set_present` | kernel | A | `state[h]` W 1 B | 3 |  | 3 | 3 `check_state`（資料：state[h]） |
| 7 | `pte_map` | kernel | A | `pte[h]` W 8 B | 6 | 1 | 6 到 106 | 5 `zero_frame`（規則） |
| 8 | `note_fresh` | kernel | A | `fresh[t]` RW 8 B<br>`fresh_n[h]` RW 2 B<br>`fresh_n[old]` RW 2 B | 19 | 2 | 19 到 219 | 3 `check_state`（資料：s） |
| 9 | `wake_check` | kernel | A | `free_top` R 4 B | 2 |  | 2 | 4 `take_frame`（資料：free_frames） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 10 | `eret` | CPU |  |  |  |  | 假設 400 | 6 `set_present`（返回）；7 `pte_map`（返回）；8 `note_fresh`（規則）；9 `wake_check`（返回） |
| 11 | `rerun` | CPU |  |  |  |  | CPU 硬體，未計 | 10 `eret`（資料：pc） |

### 4.2 `fault_ro`：page fault，RO page，由 LZ4 HW 解壓縮

kernel 自己跑、量得到的步驟共 16 個：137 道指令，9 條新的 cache line，2 次 register 寫入。照第 1 節的模型是 337 到 1 137 cycle。握 lock 的部分：第 A 段 39 道指令、4 條新的 line，39 到 439 cycle；第 B 段 35 道指令、3 條新的 line，35 到 335 cycle，另加 `wake_page`。

| # | 步驟 | 誰 | lock 段 | 讀寫 | 指令數 | 新的 line | cycle | 要等誰做完 |
|---|---|---|---|---|---|---|---|---|
| 1 | `access` | CPU |  |  |  |  | CPU 硬體，未計 | 沒有：最先能做 |
| 2 | `exception` | CPU |  |  |  |  | 假設 600 | 1 `access`（規則） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 3 | `check_state` | kernel | A | `state[h]` R 1 B<br>`free_top` R 4 B | 14 | 1 | 14 到 114 | 2 `exception`（規則） |
| 4 | `take_frame` | kernel | A | `free_top` RW 4 B<br>`free_stack[top]` R 4 B<br>`frame_of[h]` W 4 B<br>`owner[f]` W 4 B | 12 | 2 | 12 到 212 | 3 `check_state`（資料：free_frames） |
| 5 | `cot_read` | kernel | A | `cot[h]` R 32 B | 6 | 1 | 6 到 106 | 3 `check_state`（資料：s） |
| 6 | `mark_decompressing` | kernel | A | `lz4_off` R 1 B<br>`state[h]` W 1 B | 7 |  | 7 | 3 `check_state`（資料：state[h]） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 7 | `desc` | kernel |  | `tag` RW 4 B | 26 |  | 26 | 4 `take_frame`（資料：f）；5 `cot_read`（資料：e） |
| 8 | `submit` | kernel |  | `job_tail` RW 4 B<br>`job_ring[tail]` W 48 B<br>`JOB_TAIL` W 4 B | 13 | 1 | 63 到 163 | 6 `mark_decompressing`（規則）；7 `desc`（資料：desc） |
| 9 | `hw_decompress` | LZ4 HW |  |  |  |  | 模型 1 269 | 8 `submit`（資料：job_ring） |
| 10 | `notify` | kernel |  |  |  |  | 假設 3 150 | 9 `hw_decompress`（資料：irq） |
| 11 | `cpl_read` | kernel |  | `cpl_head` RW 4 B<br>`cpl_ring[head]` R 16 B<br>`CPL_HEAD` W 4 B | 12 | 1 | 162 | 10 `notify`（資料：wake） |
| 12 | `cache_invalidate` | kernel |  | `frame[f]` W 4096 B |  |  | 64 次 cache 操作，時間未知 | 11 `cpl_read`（規則） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 13 | `note_hw` | kernel | B | `strikes` RW 4 B<br>`lz4_off` RW 1 B | 5 |  | 5 | 11 `cpl_read`（資料：cpl） |
| 14 | `set_present` | kernel | B | `state[h]` W 1 B | 3 |  | 3 | 11 `cpl_read`（規則） |
| 15 | `pte_map` | kernel | B | `pte[h]` W 8 B | 6 | 1 | 6 到 106 | 12 `cache_invalidate`（規則） |
| 16 | `wake_page` | kernel | B |  |  |  | OS，未計 | 14 `set_present`（規則） |
| 17 | `note_fresh` | kernel | B | `fresh[t]` RW 8 B<br>`fresh_n[h]` RW 2 B<br>`fresh_n[old]` RW 2 B | 19 | 2 | 19 到 219 | 11 `cpl_read`（資料：cpl） |
| 18 | `wake_check` | kernel | B | `free_top` R 4 B | 2 |  | 2 | 4 `take_frame`（資料：free_frames） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 19 | `eret` | CPU |  |  |  |  | 假設 400 | 13 `note_hw`（返回）；15 `pte_map`（返回）；16 `wake_page`（返回）；17 `note_fresh`（規則）；18 `wake_check`（返回） |
| 20 | `rerun` | CPU |  |  |  |  | CPU 硬體，未計 | 19 `eret`（資料：pc） |

### 4.3 `fault_rw`：page fault，RW page，由 LZ4 HW 解壓縮

kernel 自己跑、量得到的步驟共 18 個：221 道指令，10 條新的 cache line，2 次 register 寫入。照第 1 節的模型是 421 到 1 321 cycle。握 lock 的部分：第 A 段 39 道指令、4 條新的 line，39 到 439 cycle；第 B 段 119 道指令、4 條新的 line，119 到 519 cycle，另加 `wake_page`。

| # | 步驟 | 誰 | lock 段 | 讀寫 | 指令數 | 新的 line | cycle | 要等誰做完 |
|---|---|---|---|---|---|---|---|---|
| 1 | `access` | CPU |  |  |  |  | CPU 硬體，未計 | 沒有：最先能做 |
| 2 | `exception` | CPU |  |  |  |  | 假設 600 | 1 `access`（規則） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 3 | `check_state` | kernel | A | `state[h]` R 1 B<br>`free_top` R 4 B | 14 | 1 | 14 到 114 | 2 `exception`（規則） |
| 4 | `take_frame` | kernel | A | `free_top` RW 4 B<br>`free_stack[top]` R 4 B<br>`frame_of[h]` W 4 B<br>`owner[f]` W 4 B | 12 | 2 | 12 到 212 | 3 `check_state`（資料：free_frames） |
| 5 | `cot_read` | kernel | A | `cot[h]` R 32 B | 6 | 1 | 6 到 106 | 3 `check_state`（資料：s） |
| 6 | `mark_decompressing` | kernel | A | `lz4_off` R 1 B<br>`state[h]` W 1 B | 7 |  | 7 | 3 `check_state`（資料：state[h]） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 7 | `desc` | kernel |  | `tag` RW 4 B | 26 |  | 26 | 4 `take_frame`（資料：f）；5 `cot_read`（資料：e） |
| 8 | `submit` | kernel |  | `job_tail` RW 4 B<br>`job_ring[tail]` W 48 B<br>`JOB_TAIL` W 4 B | 13 | 1 | 63 到 163 | 6 `mark_decompressing`（規則）；7 `desc`（資料：desc） |
| 9 | `hw_decompress` | LZ4 HW |  |  |  |  | 模型 1 269 | 8 `submit`（資料：job_ring） |
| 10 | `notify` | kernel |  |  |  |  | 假設 3 150 | 9 `hw_decompress`（資料：irq） |
| 11 | `cpl_read` | kernel |  | `cpl_head` RW 4 B<br>`cpl_ring[head]` R 16 B<br>`CPL_HEAD` W 4 B | 12 | 1 | 162 | 10 `notify`（資料：wake） |
| 12 | `cache_invalidate` | kernel |  | `frame[f]` W 4096 B |  |  | 64 次 cache 操作，時間未知 | 11 `cpl_read`（規則） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 13 | `note_hw` | kernel | B | `strikes` RW 4 B<br>`lz4_off` RW 1 B | 5 |  | 5 | 11 `cpl_read`（資料：cpl） |
| 14 | `cot_clear` | kernel | B | `cot[h]` W 32 B | 4 |  | 4 | 11 `cpl_read`（資料：cpl） |
| 15 | `release_chunks` | kernel | B | `bitmap[w]` RW 8 B<br>`free_chunks` W 4 B<br>`pool_full` W 1 B | 80 | 1 | 80 到 180 | 14 `cot_clear`（規則） |
| 16 | `set_present` | kernel | B | `state[h]` W 1 B | 3 |  | 3 | 11 `cpl_read`（規則） |
| 17 | `pte_map` | kernel | B | `pte[h]` W 8 B | 6 | 1 | 6 到 106 | 12 `cache_invalidate`（規則） |
| 18 | `wake_page` | kernel | B |  |  |  | OS，未計 | 16 `set_present`（規則） |
| 19 | `note_fresh` | kernel | B | `fresh[t]` RW 8 B<br>`fresh_n[h]` RW 2 B<br>`fresh_n[old]` RW 2 B | 19 | 2 | 19 到 219 | 11 `cpl_read`（資料：cpl） |
| 20 | `wake_check` | kernel | B | `free_top` R 4 B | 2 |  | 2 | 4 `take_frame`（資料：free_frames） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 21 | `eret` | CPU |  |  |  |  | 假設 400 | 13 `note_hw`（返回）；15 `release_chunks`（返回）；17 `pte_map`（返回）；18 `wake_page`（返回）；19 `note_fresh`（規則）；20 `wake_check`（返回） |
| 22 | `rerun` | CPU |  |  |  |  | CPU 硬體，未計 | 21 `eret`（資料：pc） |

### 4.4 `fault_rescue`：page fault，LZ4 HW 沒交出 page，kernel 自己解回來（RW page）

kernel 自己跑、量得到的步驟共 19 個：1012 道指令，10 條新的 cache line，2 次 register 寫入。照第 1 節的模型是 1 212 到 2 112 cycle。握 lock 的部分：第 A 段 39 道指令、4 條新的 line，39 到 439 cycle；第 B 段 119 道指令、4 條新的 line，119 到 519 cycle，另加 `wake_page`。

| # | 步驟 | 誰 | lock 段 | 讀寫 | 指令數 | 新的 line | cycle | 要等誰做完 |
|---|---|---|---|---|---|---|---|---|
| 1 | `access` | CPU |  |  |  |  | CPU 硬體，未計 | 沒有：最先能做 |
| 2 | `exception` | CPU |  |  |  |  | 假設 600 | 1 `access`（規則） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 3 | `check_state` | kernel | A | `state[h]` R 1 B<br>`free_top` R 4 B | 14 | 1 | 14 到 114 | 2 `exception`（規則） |
| 4 | `take_frame` | kernel | A | `free_top` RW 4 B<br>`free_stack[top]` R 4 B<br>`frame_of[h]` W 4 B<br>`owner[f]` W 4 B | 12 | 2 | 12 到 212 | 3 `check_state`（資料：free_frames） |
| 5 | `cot_read` | kernel | A | `cot[h]` R 32 B | 6 | 1 | 6 到 106 | 3 `check_state`（資料：s） |
| 6 | `mark_decompressing` | kernel | A | `lz4_off` R 1 B<br>`state[h]` W 1 B | 7 |  | 7 | 3 `check_state`（資料：state[h]） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 7 | `desc` | kernel |  | `tag` RW 4 B | 26 |  | 26 | 4 `take_frame`（資料：f）；5 `cot_read`（資料：e） |
| 8 | `submit` | kernel |  | `job_tail` RW 4 B<br>`job_ring[tail]` W 48 B<br>`JOB_TAIL` W 4 B | 13 | 1 | 63 到 163 | 6 `mark_decompressing`（規則）；7 `desc`（資料：desc） |
| 9 | `hw_fail` | LZ4 HW |  |  |  |  | 模型 1 269 | 8 `submit`（資料：job_ring） |
| 10 | `notify` | kernel |  |  |  |  | 假設 3 150 | 9 `hw_fail`（資料：irq） |
| 11 | `cpl_read` | kernel |  | `cpl_head` RW 4 B<br>`cpl_ring[head]` R 16 B<br>`CPL_HEAD` W 4 B | 12 | 1 | 162 | 10 `notify`（資料：wake） |
| 12 | `cache_invalidate` | kernel |  | `frame[f]` W 4096 B |  |  | 64 次 cache 操作，時間未知 | 11 `cpl_read`（規則） |
| 13 | `sw_decode` | kernel |  | `chunk[c]` R 512 B |  |  | 沒有量 | 11 `cpl_read`（資料：cpl） |
| 14 | `frame_write` | kernel |  | `frame[f]` W 4096 B | 791 |  | 791，另寫 64 條 line | 12 `cache_invalidate`（資料：cache[f]）；13 `sw_decode`（資料：page） |
| 15 | `sw_clean` | kernel |  | `frame[f]` W 4096 B |  |  | 64 次 cache 操作，時間未知 | 14 `frame_write`（資料：cache[f]、frame[f]） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 16 | `note_hw` | kernel | B | `strikes` RW 4 B<br>`lz4_off` RW 1 B | 5 |  | 5 | 13 `sw_decode`（資料：page） |
| 17 | `cot_clear` | kernel | B | `cot[h]` W 32 B | 4 |  | 4 | 13 `sw_decode`（規則） |
| 18 | `release_chunks` | kernel | B | `bitmap[w]` RW 8 B<br>`free_chunks` W 4 B<br>`pool_full` W 1 B | 80 | 1 | 80 到 180 | 17 `cot_clear`（規則） |
| 19 | `set_present` | kernel | B | `state[h]` W 1 B | 3 |  | 3 | 13 `sw_decode`（規則） |
| 20 | `pte_map` | kernel | B | `pte[h]` W 8 B | 6 | 1 | 6 到 106 | 15 `sw_clean`（規則） |
| 21 | `wake_page` | kernel | B |  |  |  | OS，未計 | 19 `set_present`（規則） |
| 22 | `note_fresh` | kernel | B | `fresh[t]` RW 8 B<br>`fresh_n[h]` RW 2 B<br>`fresh_n[old]` RW 2 B | 19 | 2 | 19 到 219 | 13 `sw_decode`（資料：page） |
| 23 | `wake_check` | kernel | B | `free_top` R 4 B | 2 |  | 2 | 4 `take_frame`（資料：free_frames） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 24 | `eret` | CPU |  |  |  |  | 假設 400 | 16 `note_hw`（返回）；18 `release_chunks`（返回）；20 `pte_map`（返回）；21 `wake_page`（返回）；22 `note_fresh`（規則）；23 `wake_check`（返回） |
| 25 | `rerun` | CPU |  |  |  |  | CPU 硬體，未計 | 24 `eret`（資料：pc） |

### 4.5 `fault_lost`：page fault，存放的 stream 壞了，page 遺失

kernel 自己跑、量得到的步驟共 14 個：123 道指令，6 條新的 cache line，2 次 register 寫入。照第 1 節的模型是 323 到 823 cycle。握 lock 的部分：第 A 段 39 道指令、4 條新的 line，39 到 439 cycle；第 B 段 21 道指令、0 條新的 line，21 到 21 cycle，另加 `wake_page`。

| # | 步驟 | 誰 | lock 段 | 讀寫 | 指令數 | 新的 line | cycle | 要等誰做完 |
|---|---|---|---|---|---|---|---|---|
| 1 | `access` | CPU |  |  |  |  | CPU 硬體，未計 | 沒有：最先能做 |
| 2 | `exception` | CPU |  |  |  |  | 假設 600 | 1 `access`（規則） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 3 | `check_state` | kernel | A | `state[h]` R 1 B<br>`free_top` R 4 B | 14 | 1 | 14 到 114 | 2 `exception`（規則） |
| 4 | `take_frame` | kernel | A | `free_top` RW 4 B<br>`free_stack[top]` R 4 B<br>`frame_of[h]` W 4 B<br>`owner[f]` W 4 B | 12 | 2 | 12 到 212 | 3 `check_state`（資料：free_frames） |
| 5 | `cot_read` | kernel | A | `cot[h]` R 32 B | 6 | 1 | 6 到 106 | 3 `check_state`（資料：s） |
| 6 | `mark_decompressing` | kernel | A | `lz4_off` R 1 B<br>`state[h]` W 1 B | 7 |  | 7 | 3 `check_state`（資料：state[h]） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 7 | `desc` | kernel |  | `tag` RW 4 B | 26 |  | 26 | 4 `take_frame`（資料：f）；5 `cot_read`（資料：e） |
| 8 | `submit` | kernel |  | `job_tail` RW 4 B<br>`job_ring[tail]` W 48 B<br>`JOB_TAIL` W 4 B | 13 | 1 | 63 到 163 | 6 `mark_decompressing`（規則）；7 `desc`（資料：desc） |
| 9 | `hw_decompress` | LZ4 HW |  |  |  |  | 模型 1 269 | 8 `submit`（資料：job_ring） |
| 10 | `notify` | kernel |  |  |  |  | 假設 3 150 | 9 `hw_decompress`（資料：irq） |
| 11 | `cpl_read` | kernel |  | `cpl_head` RW 4 B<br>`cpl_ring[head]` R 16 B<br>`CPL_HEAD` W 4 B | 12 | 1 | 162 | 10 `notify`（資料：wake） |
| 12 | `cache_invalidate` | kernel |  | `frame[f]` W 4096 B |  |  | 64 次 cache 操作，時間未知 | 11 `cpl_read`（規則） |
| 13 | `sw_decode` | kernel |  | `chunk[c]` R 512 B |  |  | 沒有量 | 11 `cpl_read`（資料：cpl） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 14 | `note_hw` | kernel | B | `strikes` RW 4 B<br>`lz4_off` RW 1 B | 5 |  | 5 | 13 `sw_decode`（資料：page） |
| 15 | `put_frame` | kernel | B | `frame_of[h]` RW 4 B<br>`owner[f]` W 4 B<br>`free_top` RW 4 B<br>`free_stack[top]` W 4 B<br>`frame_waiters` RW 4 B | 13 |  | 13 | 13 `sw_decode`（規則） |
| 16 | `set_lost` | kernel | B | `state[h]` W 1 B | 3 |  | 3 | 13 `sw_decode`（規則） |
| 17 | `wake_page` | kernel | B |  |  |  | OS，未計 | 16 `set_lost`（規則） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 18 | `kill` | kernel |  |  |  |  | OS，未計 | 12 `cache_invalidate`（返回）；14 `note_hw`（返回）；15 `put_frame`（返回）；17 `wake_page`（返回） |

### 4.6 `evict_ro`：reclaimer 趕出一個 RO page（沒有 LZ4 job）

kernel 自己跑、量得到的步驟共 7 個：59 道指令，5 條新的 cache line，0 次 register 寫入。照第 1 節的模型是 59 到 559 cycle。握 lock 的部分：第 A 段 53 道指令、5 條新的 line，53 到 553 cycle，另加 `tlb_inval`。

| # | 步驟 | 誰 | lock 段 | 讀寫 | 指令數 | 新的 line | cycle | 要等誰做完 |
|---|---|---|---|---|---|---|---|---|
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 1 | `reclaim_check` | kernel | A | `free_top` R 4 B | 2 |  | 2 | 沒有：最先能做 |
| 2 | `pick_victim` | kernel | A | `hand` RW 4 B<br>`owner[hand]` R 4 B<br>`state[h]` R 1 B<br>`pins[h]` R 2 B<br>`fresh_n[h]` R 2 B<br>`pool_full`、`lz4_off` R 2 B<br>`incompressible[h]` R 1 bit<br>`pte[h]` RW 8 B | 33 | 4 | 33 到 433 | 1 `reclaim_check`（規則） |
| 3 | `pte_clear` | kernel | A | `pte[h]` W 8 B | 2 |  | 2 | 2 `pick_victim`（資料：victim） |
| 4 | `tlb_inval` | kernel | A |  |  |  | 假設 500 | 3 `pte_clear`（規則） |
| 5 | `put_frame` | kernel | A | `frame_of[h]` RW 4 B<br>`owner[f]` W 4 B<br>`free_top` RW 4 B<br>`free_stack[top]` W 4 B<br>`frame_waiters` RW 4 B | 13 | 1 | 13 到 113 | 4 `tlb_inval`（規則） |
| 6 | `set_compressed` | kernel | A | `state[h]` W 1 B | 3 |  | 3 | 2 `pick_victim`（資料：state[*]） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |

### 4.7 `evict_rw`：reclaimer 趕出一個 RW page，由 LZ4 HW 壓縮

kernel 自己跑、量得到的步驟共 18 個：342 道指令，9 條新的 cache line，2 次 register 寫入。照第 1 節的模型是 542 到 1 342 cycle。握 lock 的部分：第 A 段 167 道指令、6 條新的 line，167 到 767 cycle，另加 `tlb_inval`；第 B 段 83 道指令、1 條新的 line，83 到 183 cycle，另加 `wake_page`。

| # | 步驟 | 誰 | lock 段 | 讀寫 | 指令數 | 新的 line | cycle | 要等誰做完 |
|---|---|---|---|---|---|---|---|---|
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 1 | `reclaim_check` | kernel | A | `free_top` R 4 B | 2 |  | 2 | 沒有：最先能做 |
| 2 | `pick_victim` | kernel | A | `hand` RW 4 B<br>`owner[hand]` R 4 B<br>`state[h]` R 1 B<br>`pins[h]` R 2 B<br>`fresh_n[h]` R 2 B<br>`pool_full`、`lz4_off` R 2 B<br>`incompressible[h]` R 1 bit<br>`pte[h]` RW 8 B | 44 | 4 | 44 到 444 | 1 `reclaim_check`（規則） |
| 3 | `reserve` | kernel | A | `cursor`、`free_chunks` RW 8 B<br>`bitmap[cursor]` RW 8 B<br>`pool_full` W 1 B | 111 | 1 | 111 到 211 | 2 `pick_victim`（資料：pool_full、victim） |
| 4 | `find_frame` | kernel | A | `frame_of[h]` R 4 B | 5 | 1 | 5 到 105 | 2 `pick_victim`（資料：victim） |
| 5 | `pte_clear` | kernel | A | `pte[h]` W 8 B | 2 |  | 2 | 2 `pick_victim`（資料：victim） |
| 6 | `tlb_inval` | kernel | A |  |  |  | 假設 500 | 5 `pte_clear`（規則） |
| 7 | `mark_compressing` | kernel | A | `state[h]` W 1 B | 3 |  | 3 | 2 `pick_victim`（資料：state[*]） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 8 | `cache_clean` | kernel |  | `frame[f]` W 4096 B |  |  | 64 次 cache 操作，時間未知 | 4 `find_frame`（資料：f）；6 `tlb_inval`（規則） |
| 9 | `desc` | kernel |  | `tag` RW 4 B | 55 |  | 55 | 3 `reserve`（資料：c）；4 `find_frame`（資料：f） |
| 10 | `submit` | kernel |  | `job_tail` RW 4 B<br>`job_ring[tail]` W 48 B<br>`JOB_TAIL` W 4 B | 13 | 1 | 63 到 163 | 7 `mark_compressing`（規則）；8 `cache_clean`（規則）；9 `desc`（資料：desc） |
| 11 | `hw_compress` | LZ4 HW |  |  |  |  | 模型 4 266 | 10 `submit`（資料：job_ring） |
| 12 | `notify` | kernel |  |  |  |  | 假設 3 150 | 11 `hw_compress`（資料：irq） |
| 13 | `cpl_read` | kernel |  | `cpl_head` RW 4 B<br>`cpl_ring[head]` R 16 B<br>`CPL_HEAD` W 4 B | 12 | 1 | 162 | 12 `notify`（資料：wake） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 14 | `note_hw` | kernel | B | `strikes` RW 4 B<br>`lz4_off` RW 1 B | 5 |  | 5 | 13 `cpl_read`（資料：cpl） |
| 15 | `cot_store` | kernel | B | `cot[h]` W 32 B | 44 | 1 | 44 到 144 | 13 `cpl_read`（資料：cpl） |
| 16 | `trim` | kernel | B | `bitmap[w]` RW 8 B<br>`free_chunks` W 4 B | 18 |  | 18 | 13 `cpl_read`（資料：cpl） |
| 17 | `put_frame` | kernel | B | `frame_of[h]` RW 4 B<br>`owner[f]` W 4 B<br>`free_top` RW 4 B<br>`free_stack[top]` W 4 B<br>`frame_waiters` RW 4 B | 13 |  | 13 | 15 `cot_store`（規則） |
| 18 | `set_compressed` | kernel | B | `state[h]` W 1 B | 3 |  | 3 | 13 `cpl_read`（規則） |
| 19 | `wake_page` | kernel | B |  |  |  | OS，未計 | 18 `set_compressed`（規則） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |

### 4.8 `evict_rw_incompressible`：reclaimer 想趕出一個 RW page，但它壓不進 7 個 chunk

kernel 自己跑、量得到的步驟共 18 個：332 道指令，8 條新的 cache line，2 次 register 寫入。照第 1 節的模型是 532 到 1 232 cycle。握 lock 的部分：第 A 段 167 道指令、6 條新的 line，167 到 767 cycle，另加 `tlb_inval`；第 B 段 73 道指令、0 條新的 line，73 到 73 cycle，另加 `wake_page`。

| # | 步驟 | 誰 | lock 段 | 讀寫 | 指令數 | 新的 line | cycle | 要等誰做完 |
|---|---|---|---|---|---|---|---|---|
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 1 | `reclaim_check` | kernel | A | `free_top` R 4 B | 2 |  | 2 | 沒有：最先能做 |
| 2 | `pick_victim` | kernel | A | `hand` RW 4 B<br>`owner[hand]` R 4 B<br>`state[h]` R 1 B<br>`pins[h]` R 2 B<br>`fresh_n[h]` R 2 B<br>`pool_full`、`lz4_off` R 2 B<br>`incompressible[h]` R 1 bit<br>`pte[h]` RW 8 B | 44 | 4 | 44 到 444 | 1 `reclaim_check`（規則） |
| 3 | `reserve` | kernel | A | `cursor`、`free_chunks` RW 8 B<br>`bitmap[cursor]` RW 8 B<br>`pool_full` W 1 B | 111 | 1 | 111 到 211 | 2 `pick_victim`（資料：pool_full、victim） |
| 4 | `find_frame` | kernel | A | `frame_of[h]` R 4 B | 5 | 1 | 5 到 105 | 2 `pick_victim`（資料：victim） |
| 5 | `pte_clear` | kernel | A | `pte[h]` W 8 B | 2 |  | 2 | 2 `pick_victim`（資料：victim） |
| 6 | `tlb_inval` | kernel | A |  |  |  | 假設 500 | 5 `pte_clear`（規則） |
| 7 | `mark_compressing` | kernel | A | `state[h]` W 1 B | 3 |  | 3 | 2 `pick_victim`（資料：state[*]） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |
| 8 | `cache_clean` | kernel |  | `frame[f]` W 4096 B |  |  | 64 次 cache 操作，時間未知 | 4 `find_frame`（資料：f）；6 `tlb_inval`（規則） |
| 9 | `desc` | kernel |  | `tag` RW 4 B | 55 |  | 55 | 3 `reserve`（資料：c）；4 `find_frame`（資料：f） |
| 10 | `submit` | kernel |  | `job_tail` RW 4 B<br>`job_ring[tail]` W 48 B<br>`JOB_TAIL` W 4 B | 13 | 1 | 63 到 163 | 7 `mark_compressing`（規則）；8 `cache_clean`（規則）；9 `desc`（資料：desc） |
| 11 | `hw_compress` | LZ4 HW |  |  |  |  | 模型 4 266 | 10 `submit`（資料：job_ring） |
| 12 | `notify` | kernel |  |  |  |  | 假設 3 150 | 11 `hw_compress`（資料：irq） |
| 13 | `cpl_read` | kernel |  | `cpl_head` RW 4 B<br>`cpl_ring[head]` R 16 B<br>`CPL_HEAD` W 4 B | 12 | 1 | 162 | 12 `notify`（資料：wake） |
|  | `lock` | kernel |  | `mm_lock` RW 1 B | 4 |  | 4 |  |
| 14 | `note_hw` | kernel | B | `strikes` RW 4 B<br>`lz4_off` RW 1 B | 5 |  | 5 | 13 `cpl_read`（資料：cpl） |
| 15 | `release_all` | kernel | B | `bitmap[w]` RW 8 B<br>`free_chunks` W 4 B | 51 |  | 51 | 13 `cpl_read`（資料：cpl） |
| 16 | `mark_incompressible` | kernel | B | `incompressible[h]` RW 1 bit | 8 |  | 8 | 13 `cpl_read`（資料：cpl） |
| 17 | `set_present` | kernel | B | `state[h]` W 1 B | 3 |  | 3 | 13 `cpl_read`（規則） |
| 18 | `pte_map` | kernel | B | `pte[h]` W 8 B | 6 |  | 6 | 13 `cpl_read`（規則） |
| 19 | `wake_page` | kernel | B |  |  |  | OS，未計 | 17 `set_present`（規則） |
|  | `unlock` | kernel |  | `mm_lock` W 1 B | 2 |  | 2 |  |

## 5. 觀察與提案

以下都是提案，沒有改動程式。

### 5.1 kernel 的表格工作不是瓶頸，K1 才是

RO fault 的 5 756 到 6 556 ns 裡，kernel 量得到的部分是 337 到 1 137 cycle。其餘 4 150 ns 是 exception 進出、interrupt 與叫醒 thread，這三項到現在都是假設。相依圖文件的結論在這裡得到另一個角度的支持：要讓 fault 變快，先決定 CPU 與 OS，再決定等 completion 的方式。

### 5.2 把每個 page 的小欄位併成一筆

`state` 1 B、`pins` 2 B、`fresh_n` 2 B、`frame_of` 4 B 合計 9 B。併成一筆 16 B 的記錄之後，一次 fault 在 `state[h]`、`frame_of[h]`、`fresh_n[h]` 碰的 3 條 line 變成 1 條，省下最多 200 cycle。對 fault 來說，這是 1 137 裡的 200，值得做但是不急。

對 clock 掃描的幫助比較大：每路過一個 frame 從最多 4 條 line 降到 2 條，剩下的是合併後的記錄與 `pte[h]`。

### 5.3 讓 clock 掃描不必跳著讀

更進一步的做法是把掃描要看的東西改成以 frame 當索引，和 `owner` 放在一起。page 編號只需要 18 bit，`owner` 那 4 B 的高位元可以放一個「不可趕出」的旗標，在 pin、fresh、incompressible 改變的時候同步更新。這樣路過一個不可趕出的 frame 只需要循序的一條 line 的十六分之一。accessed flag 仍然在 PTE 裡，所以路過一個可以趕出但是剛被用過的 page 還是要碰 `pte[h]`。

代價是多一份要保持一致的資料，屬於容易出錯的那一類。照你對軟硬體分工的偏好，它留在軟體，而且要有 mutant 測試守住。

這一項與 K4 是同一件事的兩面：K4 限制每握一次 lock 最多看幾個 frame，這一項降低每看一個 frame 的成本。先做 K4。

### 5.4 不需要為 bitmap 做硬體

`reserve` 量到 111 道指令，碰 1 條 line，與原本假設的 250 ns 相符。實際執行時幾乎不需要掃第二個 word。在 bitmap 找 leading zero 是 CPU 一道指令的事，放進硬體不會更快，反而要把 bitmap 的所有權交出去。這支持相依圖文件「不讓硬體管 chunk」的結論。

### 5.5 整頁的操作

`zero_frame` 量到 341 道指令，寫 64 條 line。Apple 的 C library 用 `DC ZVA` 一次清 64 B，別的 CPU 不一定有這麼快的做法。它在 `first_touch` 裡是握著 lock 做的，相依圖文件已經提案把它移到 lock 外面，這裡的數字不改變那個提案。

`frame_write` 複製 4096 B 量到 791 道指令，只出現在 LZ4 HW 失敗的救援路徑。

### 5.6 相依關係告訴我們什麼

以 RO fault 的第 A 段為例：`take_frame`、`cot_read`、`mark_decompressing` 三個步驟都只等 `check_state`，彼此之間沒有關係。它們各自只有 6 到 12 道指令，並排沒有意義。有意義的是另一個方向：`desc` 只需要 `take_frame` 的 `f` 與 `cot_read` 的 COT entry，已經在 lock 外面；`cot_read` 也只需要知道狀態是 COMPRESSED。握 lock 的部分已經接近最少。

第 B 段也一樣：`note_hw`、`set_present`、`note_fresh` 都只等 `cpl_read`，`pte_map` 只等 `cache_invalidate`。整個 fault 的骨幹是一條鏈：`check_state`、`desc`、`submit`、LZ4 HW、`notify`、`cpl_read`、`cache_invalidate`、`pte_map`、`eret`。

## 6. 沒有量到的，與等你決定的

### 6.1 沒有量到的

| 項目 | 現在用什麼 | 為什麼量不到 |
|---|---|---|
| `exception`、`eret` | 假設 600 ns 與 400 ns | 取決於 CPU 與 OS 的進入路徑，K1 |
| `notify` | 假設 3 150 ns：interrupt 進入、處理、叫醒 thread | 取決於 OS 的排程，K1 |
| `tlb_inval` | 假設 500 ns | 取決於 CPU 與 core 的數目，K1 |
| `cache_invalidate`、`cache_clean`、`sw_clean` | 計數：每個 frame 64 次 cache 維護操作 | 每次操作的時間取決於 CPU；接成 coherent 的 master port 可以免掉，介面規格的 O11 |
| `sw_decode` | 沒有數字 | 軟體解壓縮只在 LZ4 HW 失敗時走到，還沒有 C 的實作 |
| `wait_page`、`wait_frame`、`wake_page`、`kill` | 沒有數字 | OS 的等待與叫醒，K1 |
| `lock` 有人搶的時候 | 量到的是沒有人搶的 4 道指令 | 等待時間是排隊的問題，在相依圖文件第 5 節 |
| PTE 寫入後的 barrier | 沒有算 | 取決於 CPU 的規定，K1 |
| 每道指令 1 cycle | 假設 | 取決於 CPU 的管線，K1 |

### 6.2 C 參考實作自己選的設計，等你確認

1. PTE 是 8 B，放在一張以 `h` 當索引的平面表。真正的 page table 是幾層、PTE 長什麼樣子，取決於 K1。
2. `incompressible` 做成每個 page 1 bit 的 bitmap。
3. fresh 名單是每個 thread 一個小的環狀陣列，`protect` 是 1 時只有一格。
4. job ring 沒有自己的 lock：`submit` 假設同一時間只有一個 thread 在送 job。兩個以上的 thread 同時 fault 時需要一個 driver lock，還沒有量。
5. `scalars` 的十幾個純量放在同一條 line。多個 core 同時改它會互相搶這條 line，這是多核心才有的成本，這份文件沒有算。
6. 5.2 的合併記錄與 5.3 的 frame 旗標是否採用。

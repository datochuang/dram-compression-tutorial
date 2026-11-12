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
| 量測 | 指令數。把步驟寫成固定 layout 的 C，用 {{compiler}} 以 `-O2` 編成 AArch64，執行後讀 CPU 的指令計數器 | 換 compiler 或換指令集會變，量級不會變 |
| 計數 | 碰到幾條 cache line、寫幾次 LZ4 HW register、做幾次 cache 維護操作。從 layout 與介面規格數出來 | 只要 layout 不變就是確定的 |
| 假設 | 把指令數與 line 數換成 cycle 的模型，以及 exception、interrupt、叫醒 thread、TLB invalidate 的時間 | 取決於用哪顆 CPU 與哪個 OS，是 K1 |

結論有六點。

1. **kernel 自己查表改表的工作很小。** 一次 RO page 的 fault，kernel 量得到的步驟加起來是 {{ro_instr}} 道指令、{{ro_new}} 條新的 cache line、2 次 register 寫入。照第 1 節的模型是 {{ro_lo}} 到 {{ro_hi}} cycle。同一批步驟在 `ifsim.params` 裡原本假設 {{ro_old}} ns，量級相符。
2. **一次 fault 的時間不在 kernel 的表上。** 同一次 RO fault 還要加上假設的 exception 進出、interrupt、叫醒 thread 共 {{ro_platform}} ns，以及 LZ4 HW 模型的 {{ro_hw}} ns。合計約 {{ro_all_lo}} 到 {{ro_all_hi}} ns，kernel 的表只佔 {{ro_share_lo}} 到 {{ro_share_hi}}。所以 K1 的答案比任何表的最佳化都重要。
3. **在 kernel 的表上，cache line 比指令重要。** RO fault 的上限 {{ro_hi}} cycle 裡，{{ro_line_share}} 是把 line 從 DRAM 讀進來。原因是每個 page 的資訊分散在 {{page_tables}} 六張表，各佔一條 line。
4. **唯一不小的是 clock 掃描。** 全尺寸的執行裡每選一個 page 平均看 {{scan_mean}} 個 frame。每路過一個 frame 最多碰 4 條新的 line。照模型是 {{scan_instr_lo}} 到 {{scan_cyc_hi}} cycle，原本的假設是 {{scan_assumed}} ns。最長的一次看了 {{scan_longest}} 個 frame，整段握著 `mm_lock`，照模型約 {{scan_long_lo}} 到 {{scan_long_hi}} ms。
5. **在 bitmap 找空位不需要硬體幫忙。** 找一個 0 是 `MVN`、`RBIT`、`CLZ` 三道指令。保留 7 個 chunk 量到 {{reserve_instr}} 道指令。全尺寸的執行裡每次平均掃 {{words_mean}} 個 word，最多 {{words_max}} 個。
6. **握 lock 的時間很短。** RO fault 的第 A 段是 {{roA_instr}} 道指令與 {{roA_new}} 條 line，第 B 段是 {{roB_instr}} 道與 {{roB_new}} 條。照模型兩段各不到 0.5 µs，不含叫醒等待者的 OS 呼叫。趕出 RW page 的第 A 段是 {{rwA_instr}} 道與 {{rwA_new}} 條，另外加上假設 500 ns 的 TLB invalidate。

## 1. 方法

### 1.1 指令數怎麼量

Python 的模型把表放在抽象的容器裡，看不出一個步驟要幾道指令。所以把同一份控制程序另外寫成 C，放在 `sim/kstep/kstep.h`。每個步驟是一個 always-inline 的函式，表的 layout 固定，如第 2 節。

量測程式是 `sim/kstep/measure.c`。每個步驟有兩個版本：一個只準備參數，一個準備參數後執行步驟。兩個版本各呼叫幾萬次，前後讀 `proc_pid_rusage` 的 `ri_instructions`，相減再除以次數就是這個步驟的指令數。重複 5 次取最小值。

驗證有兩道。一是校正步驟：放 5 個 `NOP` 進去，量到的是 {{calib}}。二是對幾個步驟逐一讀反組譯的結果，`unlock` 2 道、`wake_check` 2 道、`put_frame` 13 道、`check_state` 14 道，都與量到的相同。

編譯選項：`{{flags}}`

{{n_steps}} 個步驟裡有 {{n_measured}} 個量得到。其餘的不是 kernel 的表格工作：CPU 硬體做的、OS 做的、LZ4 HW 做的、整頁的 cache 維護、軟體解壓縮。它們列在第 6 節。

### 1.2 cache line 怎麼數

一條 cache line 是 64 B。每個步驟宣告它讀寫哪張表的哪一筆，宣告與 `deps.py` 的讀寫集合逐一核對過。一個動作第一次碰到某張表的某一筆時，算一條新的 line。同一個動作後來再碰同一筆，不再算。

三種情況不算新的 line。一是 `scalars`：十幾個 kernel 的純量放在同一條 line，每個動作都用，假設它一直在 cache 裡。二是 thread 自己的 stack 與 CPU register。三是 free frame 的 stack 頂端：剛放回去的馬上又被拿走。

循序讀的表只有 clock 掃描的 `owner[hand]`，每 16 筆才換一條 line，沒有算進新的 line。同一筆資料換個名字再出現也不重複算：指針停下的那個 frame 就是後來 `put_frame` 的 `f`，`reserve` 改過的 word 就是後來 `trim` 還 bit 的 word。

`cpl_ring` 是例外的另一邊：completion 是 LZ4 HW 寫進 DRAM 的，kernel 讀它一定是從 DRAM 讀，介面規格的 FW-CACHE-3 也是這樣要求。所以這一條 line 連下限也算進去。

### 1.3 換成 cycle 的模型

{{model}}

一個步驟的下限是「指令數加上 register 寫入」，也就是需要的 line 都已經在 L1 cache；唯一的例外是 `cpl_ring` 那一條，它一定從 DRAM 讀，下限就含它的 100 cycle。上限是再加上其餘每條新的 line 100 cycle，也就是全部從 DRAM 讀。真實的數字在兩者之間，取決於 L2 cache 有多大。pinned 區裡的 kernel 表加起來約 {{kmem_total}}，page table 另外 {{pt_total}}，COT 是 {{cot_total}}。

## 2. 資料結構放在哪

### 2.1 DRAM 的分區

數字是全尺寸設定 `SystemConfig()`。

{{map}}

### 2.2 每張表

{{layout}}

沒有固定位址的表在 pinned 區裡，位址由 linker 決定。pinned 區不經過壓縮層，kernel 碰它不會發生 page fault。

以 page 編號 `h` 當索引的表有六張：{{page_tables}}。處理一個 page 的時候，這六張表的第 `h` 筆在六條不同的 line 上。以 frame 編號 `f` 當索引的是 `owner` 與 `free_stack`。

這個 layout 是 C 參考實作為了能量測而選的，其中幾項還沒有經過你決定，列在 6.2。

## 3. 每個步驟

### 3.1 總表

{{steps}}

表中的 `h` 是 page 編號，`f` 是 frame 編號，`t` 是 thread，`old` 是這個 thread 的 fresh 名單裡被擠掉的那個 page。指令數是範例情況：一個 page 壓成 5 個 chunk，COMPRESS 預留 7 個 chunk。

### 3.2 與原本假設的對照

`ifsim.params` 裡 kernel 步驟的成本原本都是整數的假設。下表把假設與量到的放在一起。

{{compare}}

大部分假設落在模型的上下限之間。兩個例外：`desc` 假設 150 ns，量到 {{desc_d}} 或 {{desc_c}} 道指令而且不碰新的 line；`pick_victim` 假設 300 ns，只看一個 frame 就已經可能超過，見下一小節。

### 3.3 成本隨數量變的步驟

**clock 掃描 `pick_victim`。** 指針每前進一格看一個 frame。

{{sweep_pick}}

路過的 frame 之所以貴，是因為 frame 連續而 page 不連續：`owner[hand]` 是循序的，但是它給出的 `h` 沒有規律，所以 `state[h]`、`pins[h]`、`fresh_n[h]`、`pte[h]` 每個 frame 都落在新的 line 上。

**在 bitmap 保留 chunk `reserve`。** 從 `cursor` 指的 word 開始，對每個 word 取反、`RBIT`、`CLZ` 找到最低的 0，設成 1，再用 `x &= x - 1` 的方式找下一個。量到每個 chunk 約 {{reserve_chunk}} 道指令，每掃過一個 word 約 {{reserve_skip}} 道。

{{sweep_reserve}}

**實際執行時走多遠。** 下表來自 host simulation 的兩次執行。

{{runs}}

最長的那一次掃描發生在開機後 frame 第一次用完的時候：每個 page 的 accessed flag 都是 1，指針要繞完整圈把它們清掉。這是控制程序文件的 D3。

## 4. 每個場景

每個場景一張表，一列一個步驟，照程式執行的順序。「要等誰做完」只列真正的相依，來源是 `deps.reduced`：「資料」表示後面的步驟要用前面寫出的值，「規則」表示順序是正確性規則要求的，「返回」表示要等它做完才能離開 exception。兩個步驟之間如果沒有列出關係，它們的先後只是程式寫的順序，可以對調。

「新的 line」與「cycle」的算法在第 1 節。`lock` 與 `unlock` 沒有編號，因為它們不在相依圖裡，但是指令數算在合計內。

各場景的合計如下。

{{summary}}

{{cases}}

## 5. 觀察與提案

以下都是提案，沒有改動程式。

### 5.1 kernel 的表格工作不是瓶頸，K1 才是

RO fault 的 {{ro_all_lo}} 到 {{ro_all_hi}} ns 裡，kernel 量得到的部分是 {{ro_lo}} 到 {{ro_hi}} cycle。其餘 {{ro_platform}} ns 是 exception 進出、interrupt 與叫醒 thread，這三項到現在都是假設。相依圖文件的結論在這裡得到另一個角度的支持：要讓 fault 變快，先決定 CPU 與 OS，再決定等 completion 的方式。

### 5.2 把每個 page 的小欄位併成一筆

`state` 1 B、`pins` 2 B、`fresh_n` 2 B、`frame_of` 4 B 合計 9 B。併成一筆 16 B 的記錄之後，一次 fault 在 `state[h]`、`frame_of[h]`、`fresh_n[h]` 碰的 3 條 line 變成 1 條，省下最多 200 cycle。對 fault 來說，這是 {{ro_hi}} 裡的 200，值得做但是不急。

對 clock 掃描的幫助比較大：每路過一個 frame 從最多 4 條 line 降到 2 條，剩下的是合併後的記錄與 `pte[h]`。

### 5.3 讓 clock 掃描不必跳著讀

更進一步的做法是把掃描要看的東西改成以 frame 當索引，和 `owner` 放在一起。page 編號只需要 18 bit，`owner` 那 4 B 的高位元可以放一個「不可趕出」的旗標，在 pin、fresh、incompressible 改變的時候同步更新。這樣路過一個不可趕出的 frame 只需要循序的一條 line 的十六分之一。accessed flag 仍然在 PTE 裡，所以路過一個可以趕出但是剛被用過的 page 還是要碰 `pte[h]`。

代價是多一份要保持一致的資料，屬於容易出錯的那一類。照你對軟硬體分工的偏好，它留在軟體，而且要有 mutant 測試守住。

這一項與 K4 是同一件事的兩面：K4 限制每握一次 lock 最多看幾個 frame，這一項降低每看一個 frame 的成本。先做 K4。

### 5.4 不需要為 bitmap 做硬體

`reserve` 量到 {{reserve_instr}} 道指令，碰 1 條 line，與原本假設的 250 ns 相符。實際執行時幾乎不需要掃第二個 word。在 bitmap 找 leading zero 是 CPU 一道指令的事，放進硬體不會更快，反而要把 bitmap 的所有權交出去。這支持相依圖文件「不讓硬體管 chunk」的結論。

### 5.5 整頁的操作

`zero_frame` 量到 {{zero_instr}} 道指令，寫 64 條 line。Apple 的 C library 用 `DC ZVA` 一次清 64 B，別的 CPU 不一定有這麼快的做法。它在 `first_touch` 裡是握著 lock 做的，相依圖文件已經提案把它移到 lock 外面，這裡的數字不改變那個提案。

`frame_write` 複製 4096 B 量到 {{copy_instr}} 道指令，只出現在 LZ4 HW 失敗的救援路徑。

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

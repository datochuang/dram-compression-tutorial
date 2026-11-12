# Kernel 控制程序，第 0 版

對象是要一起決定算法與控制程序的人。這一版只看「做什麼、照什麼順序做」，完全不看時間。

> 這份文件由 `python3 sim/run_host.py gen-doc` 產生。程式碼區塊是 `sim/hostsim/kernel.py` 的原文，逐步表是實際執行留下的紀錄，數字在 `control-procedures-v0.json`。
> 第 1 節的發現、7.3 與 7.4 的讀法、8.4 的讀法與第 10 節的待決事項是對這一版數字手寫的。重跑之後數字有變的話，這幾處要重讀一次。

## 0. 這一版模擬的是什麼

host simulation 是普通的 Python 程式，沒有時間。它有兩種跑法，用的是同一份 `kernel.py`。

| 跑法 | 用來回答什麼 | 程式 |
|---|---|---|
| 一個 thread | 每個程序裡各步驟的順序。第 3、4 節的逐步表與第 8 節的數字來自這裡 | `machine.py` |
| 多個 thread 交錯執行 | 等待與叫醒、TLB、CPU cache、pin、不能等的 context 是否正確。第 5、6、7 節 | `conc.py` |

| 角色 | 在模擬裡是什麼 | 程式 |
|---|---|---|
| user SW | 一個 thread 時是 UI、MEDIA、NET、LOG 四支程式輪流存取。多個 thread 時每個 thread 照自己的腳本跑，其中一個兼作 driver | `machine.py` 的 `access`，`conc.py` 的 `scripts` |
| CPU 與 CPU MMU | 查 PTE，無效就進 page fault，回來後重新執行同一道指令。多個 thread 時每個 core 有自己的 TLB | `machine.py`，`conc.py` 的 `instruction` |
| CPU cache | 每個 frame 與每個 chunk 幾個 flag：CPU cache 裡有沒有它的 line，line 比 DRAM 新還是舊。開機時全部當作有 line 而且還沒寫回 | `cache.py` |
| kernel | 這份文件的主角。介面規格裡稱為 FW | `kernel.py` |
| LZ4 HW | 一個函式：收 48 B 的 descriptor，回 16 B 的 completion。可以指定某個 job 失敗，或從某一刻起不再回答 | `hw.py` |
| kernel 自己的 LZ4 decoder | 只會解壓縮的軟體 decoder，由 CPU 執行。不是 LZ4 HW 裡面那一個 | `codec.py` |
| 壓縮與解壓縮 | 本機的 liblz4。加 `--codec cli` 改成每個 page 呼叫一次本機的 `lz4` 工具，產生的 byte 完全相同 | `codec.py` |
| DRAM | 一塊 byte array，位址配置與正式設計相同 | `lz4sim/dram.py` |

刻意拿掉的東西：job ring、doorbell、interrupt、等待時間。這些在 `sim/ifsim` 裡，等控制程序定下來再對齊。timeout 與 reset 在這裡只留下結果：`lz4_job` 回 None，表示 driver 等不到 completion，而且已經放棄。

kernel 對外只透過下面這些呼叫，其他什麼都碰不到。這張表也就是 kernel 對平台的全部要求。粗體是為了正確性新增或改了定義的。

| 呼叫 | 作用 |
|---|---|
| `lock`、`unlock` | 保護下面所有表格的唯一一把 lock |
| `cot_read`、`cot_write` | 讀寫某個 page 在 DRAM 裡的 32 B COT entry |
| `zero_frame` | 把一個 frame 填成 0 |
| `frame_write` | 把一個 page 的內容複製進 frame。開機時用，**`sw_decode` 也用** |
| **`frame_read`** | 經由 kernel 自己的 mapping 讀一個 frame。只有 `verify` 選項用 |
| **`chunk_read`** | 讀一個 512 B 的 chunk。讀到的是 DRAM 現在的內容，不是 cache 裡留著的舊 line |
| `pte_map` | 把某個 page 的 PTE 設為有效，指向一個 frame |
| `pte_unmap` | 把 PTE 設為無效，並從所有 core 的 TLB 清掉。**全部清完才回來** |
| `pte_test_clear_accessed` | 讀出並清掉 PTE 的 accessed bit |
| `lz4_job` | 交一個 descriptor 給 LZ4 HW，等它做完，拿回 completion。**好幾個 thread 可以同時呼叫，各自拿回自己那個 job 的 completion。等不到 completion 而且 driver 已經放棄時回 None，不可以永遠等** |
| **`cache_clean`** | 把一個 frame 在所有 core 的 cache 裡還沒寫回的 line 寫回 DRAM |
| **`cache_invalidate`** | 把一個 frame 在所有 core 的 data cache 與 instruction cache 裡的 line 作廢 |
| **`cache_flush_layer`** | 開機時做一次：frame 區與 chunk pool 在所有 core 的 line，先寫回再作廢 |
| `wait_page`、`wake_page` | 等某個 page 上進行中的 job 結束。**放開 lock 與睡著是同一步** |
| `wait_frame`、**`wake_frame`** | 等到有 free frame。**放開 lock 與睡著是同一步** |
| `wake_reclaimer` | 叫醒 reclaimer thread。**它正在跑的話，這次要求要留到它跑完再看一次** |
| **`may_wait`** | 現在這個 context 可不可以睡 |
| **`thread`** | 現在是哪個 thread |

## 1. 發現

F1 到 F9 來自一個 thread 的執行。F10 到 F17 是處理正確性問題時找到的：F10、F11、F16 是多個 thread 交錯執行時跑出來的，其餘是先讀程式想到、再用模擬確認的。F18 到 F24 是拿 Linux zram 的原始碼對照之後補的，對照的過程在 `reference/linux-zram-study.md`：F21 是模擬跑出來的，其餘是對照時想到、再用模擬確認的。

| 編號 | 發現 | 依據 | 現在的處理 |
|---|---|---|---|
| F1 | 在模擬表現得出來的範圍內，控制程序從頭到尾資料正確 | 第 9 節：正式大小的機器跑 {{accesses}} 次 access 後，{{streams_checked}} 個存放中的 stream 全部解得回原本的內容，壓縮層以外的 {{guard_mib}} MiB 一個 byte 都沒變。第 7 節：{{conc_schedules}} 個隨機 schedule 與 {{conc_explored}} 個列舉出的 schedule 全部通過。模擬看不到的列在 7.6 | 成立 |
| F2 | reclaimer 不可以搬走剛 fault 進來、CPU 還沒用到的 page | 8.4：不保護的話，記憶體快用完時同一道指令會一直 fault，機器不再前進，而且永遠不會報出記憶體不足 | 已加進控制程序：`fresh`。保護幾個 page 見 D4 |
| F3 | incompressible page 留在 frame 的做法，在資料不好壓時會讓機器停住，這時 chunk pool 還有一大半是空的 | 8.4：壓縮後 90% 的資料，跑到 4834 次 access 就沒有 frame 可用，chunk pool 8192 個 chunk 裡還有 5088 個沒用。80% 時跑得完，但 LZ4 job 多 35% | 沒改，待決定，見 D1 |
| F4 | 可用的 RW 容量是統計上的，不是保證的 | 8.5：全部壓不動時放不下全部的 RW 空間 | 需要記憶體用完時的處理方式，見 D2 |
| F5 | 新 PTE 的 accessed bit 設不設，差別不大，方向也不固定 | 8.1：正式大小的機器上不設的話 LZ4 job 多 {{jobs_without_pct}}%。小機器上反而少 {{small_without_pct}}% | 先設為 1。保護剛 fault 進來的 page 靠的是 `fresh`，不是這個 bit。見 D5 |
| F6 | clock 第一次選 page 要繞完整整一圈 | 8.2：最長一次看了 {{clock_longest}} 個 frame，全程握著 lock | 沒改，見 D3 |
| F7 | clock 比理想的 LRU 多做 {{jobs_gap_pct}}% 的 LZ4 job | 8.1：{{jobs_clock}} 對 {{jobs_lru}}。理想 LRU 需要知道每一次 access，kernel 做不到 | 沒改，見 D3 |
| F8 | 開機後找 free chunk 要從 RO image 後面開始 | 不這樣做的話第一次 `reserve` 要掃過 {{ro_words}} 個 word。改了以後單次最多 {{scan_max}} 個 | 已改，在 `boot` 裡 |
| F9 | RW page 取回後沒被寫過又被搬走的情況不多 | 8.2：{{unwritten}} 次，占 {{unwritten_pct}}% | 不值得為它保留舊的 stream，先不做 |
| F10 | completion 的 tag 原本是跟「最新送出的 tag」比 | 多個 thread 的第一次執行就停在 `completion tag 0x1, expected 0x3`。兩個 job 同時在外面時，先回來的那個一定對不上 | 已改：`lz4_job` 把自己的 tag 留在區域變數裡 |
| F11 | 等 frame 的 fault 原本沒有人叫醒 | 原本 `put_frame` 不叫醒任何人，fault 去等 frame 之前也不叫 reclaimer。7.4 的 `no_wake_frame`：第 1 個 schedule 所有 thread 就都卡住 | 已改：`put_frame` 呼叫 `wake_frame`，`page_fault` 在 `wait_frame` 之前先 `wake_reclaimer` |
| F12 | LZ4 HW 直接讀寫 DRAM，不經過 CPU cache，原本的程序完全沒處理 | 第 6 節。COMPRESS 會壓到舊的內容，DECOMPRESS 之後 CPU 會讀到或執行到舊的內容。兩種都不會被 CRC-32 發現 | 已改：`cache_clean` 與 `cache_invalidate`。HW 的 master port 如果與 CPU cache coherent 就不需要，見 D8 |
| F13 | `fresh` 每個 core 一份是錯的，要每個 thread 一份，而且要保護不只一個 page | 5.4。一道指令可能同時需要好幾個 page。thread 在等第二個 page 時會睡著，同一個 core 換別的 thread 跑 | 已改：每個 thread 自己的清單，長度是 `protect`。見 D4 |
| F14 | 不能等的 context 碰到不在 frame 裡的 page，原本沒有任何規則 | 5.1。ISR、握著 lock 的 kernel 程式、HRT thread 都不能進 `page_fault` 睡覺。這種錯只有 page 剛好被搬走時才會發生，平常測不到 | 已加：`page_fault` 開頭的檢查，以及 `pin_page` 與 `unpin_page`。見 D9、D10 |
| F15 | kernel 經由自己的 mapping，或別的 bus master，碰 user SW 的 frame 時，CPU MMU 擋不住 | 5.2。page 被搬走之後那個 frame 已經是別的 page 的，不會有 page fault | 已加：一樣用 `pin_page`。見 D11 |
| F16 | 兩個叫醒的細節沒做對，thread 就會永遠睡著 | 7.4 的 `wait_not_atomic` 與 `unlatched_reclaimer`：都在第 4 個 schedule 卡住 | 已寫成對平台的要求，見 7.5 |
| F17 | frame 的數量有下限，低於它不是變慢而是互相等到停住 | 7.4 的 `too_few_frames`：3 個 frame、兩個 thread，兩邊都在等對方手上的 frame | 已寫成規則，見 5.4。pin 的數量要不要設上限見 D12 |
| F18 | LZ4 HW 回 BUS_ERROR 時，原本的程序停在 `KernelBug` | 介面規格有這個 status，`fault_in` 與 `evict_rw` 原本卻沒有處理它的路 | 已改，見 3.6：DECOMPRESS 由 kernel 自己解，COMPRESS 把 page 留在 frame |
| F19 | 一次 BAD_STREAM 就把 page 標成 LOST，太早 | BAD_STREAM 只說 LZ4 HW 這一次沒解出來。是 stream 壞了還是 HW 出錯，kernel 分不出來，而 LOST 不能復原。7.4 的 `no_sw_decode`：stream 完好的 page 被標成 LOST | 已改：kernel 用自己的 decoder 從同一份 stream 再解一次，兩邊都失敗才是 LOST。見 3.6 與 D13 |
| F20 | 「free frame 在 CPU cache 裡沒有還沒寫回的 line」在開機那一刻不成立 | boot loader 寫過 chunk pool，也可能用過 frame 區。7.4 的 `no_boot_flush`：第 1 個 schedule 就違反 C2 | 已改：`boot` 第一步做 `cache_flush_layer`，範圍是 frame 區與 chunk pool |
| F21 | `sw_decode` 寫過的 frame，之後會帶著還沒寫回的 line 變成 free | 模擬跑出來的。CPU 寫了 frame。page 是 RO 的話，之後 `evict_ro` 直接釋放它，中間沒有 `cache_clean`，下一個 DECOMPRESS 寫這個 frame 時違反 C2。page 是程式碼的話還有第二個問題：新內容只在 data cache，CPU 取指令時看不到 | 已改：`sw_decode` 寫完立刻 `cache_clean`。7.4 的 `sw_decode_no_clean` |
| F22 | kernel 讀 chunk 時不可以經過 cache 裡的舊 line | chunk 是 LZ4 HW 寫的。kernel 之前讀過同一個 chunk 的話，cache 裡留的是上一個 stream。7.4 的 `chunk_read_cached` | 已寫進 `chunk_read` 的定義，見 6.2 |
| F23 | thread 在 `page_fault` 裡面被終止，上一版只有規則，沒有模擬 | 7.4 的 `kill_in_kernel`：page 留在 DECOMPRESSING，卻沒有 job 在做 | 已模擬：終止的要求等 thread 離開 kernel 才生效。規則在 7.5 |
| F24 | LZ4 HW 持續答錯或不回答時，要有停用它的規則 | 沒有的話，每個 fault 都要先等一次失敗才輪到 kernel 自己解 | 已加，見 3.6：連續 {{strikes}} 次答錯，或一次沒有 completion，就不再使用，到下次開機為止。之後系統怎麼辦見 D14 |

## 2. Kernel 管的資料

| 表格 | 內容 | 放在哪裡 |
|---|---|---|
| `state[h]` | page h 現在的 state，六種之一 | kernel 自己的記憶體 |
| `frame_of[h]` | page h 占用的 frame 編號，沒有就是 -1 | kernel 自己的記憶體 |
| `owner[f]` | frame f 被哪個 page 占用，沒有就是 -1 | kernel 自己的記憶體 |
| `free_frames` | free frame 的 stack | kernel 自己的記憶體 |
| `bitmap` | chunk pool 每個 chunk 一個 bit，1 表示使用中 | kernel 自己的記憶體 |
| `incompressible` | LZ4 HW 壓不進 7 個 chunk 的 RW page | kernel 自己的記憶體 |
| `fresh[t]` | thread t 最近 `protect` 次 fault 取回的 page，reclaimer 不碰 | kernel 自己的記憶體，每個 thread 一份 |
| `fresh_n[h]` | page h 出現在幾個 thread 的 `fresh` 裡 | kernel 自己的記憶體 |
| `pins[h]` | page h 被 `pin_page` 了幾次還沒 `unpin_page` | kernel 自己的記憶體 |
| `strikes`、`lz4_off` | LZ4 HW 連續答錯了幾次，以及是不是已經決定不再使用它 | kernel 自己的記憶體 |
| COT | 每個 page 一筆 32 B 的 entry，記錄它的 stream 放在哪些 chunk | DRAM。LZ4 HW 不讀它 |

除了 COT，其他表格都不必保存到下次開機。`boot` 會從 COT 把 bitmap 重建出來。

kernel 的程式、stack 與上面這些表格全部放在壓縮層之外。理由在 5.1。

### 2.1 開機

| 順序 | 誰 | 做什麼 |
|---|---|---|
| 1 | build tool，在開發機上 | 把每個 RO page 壓好，從 chunk 0 開始連續排放，並寫好它們的 COT entry |
| 2 | boot loader | 把 RO 的 chunk 和 COT 放進 DRAM。RW page 的 COT entry 全部是 0 |
| 3 | kernel，`boot` | 先做 `cache_flush_layer`，見 6.2。再掃過整個 COT，把有效 entry 列出的 chunk 在 bitmap 上標成使用中，再把找 free chunk 的起點放在 RO image 後面 |
| 4 | kernel，`boot_load` | 把有初值的 `.data` page 直接放進 frame，見 D7 |

{{src:boot}}

{{src:boot_load}}

### 2.2 State 的變化

下面是模擬中實際發生過的 state 變化，以及是哪個程序改的。沒有列在這裡的變化就是不會發生的。

{{transitions}}

## 3. Page fault

### 3.1 第一次碰的 RW page

user SW 第一次寫一個還沒用過的 RW page。不需要 LZ4 HW。

{{walk:first_touch}}

### 3.2 RO page

RO page 的 stream 一直留在 chunk pool，所以只要解壓縮，COT 不用改。

{{walk:fault_ro}}

### 3.3 RW page

RW page 解回 frame 之後，frame 是唯一的一份，所以要把 COT entry 清掉並把 chunk 還回去。

{{walk:fault_rw}}

### 3.4 程序

{{src:page_fault}}

{{src:first_touch}}

{{src:fault_in}}

每個 job 都經過同一個小函式。tag 留在區域變數裡，因為別的 thread 也會同時經過這裡。

{{src:lz4_job}}

LZ4 HW 沒把 page 交回來時，kernel 自己解。第二個函式也給 4.8 的選項用。

{{src:sw_decode}}

{{src:decode_stored}}

### 3.5 順序上的規則

| 規則 | 理由 |
|---|---|
| 一進來先問 `may_wait`，不行就報錯 | 不能睡的 context 進來只會卡死。見 5.1 |
| 讀 state、決定怎麼做、把 state 改成 DECOMPRESSING，這三件事在同一次握著 lock 的期間做完 | 一個 page 同一時間最多只有一個 job |
| 交 job 給 LZ4 HW 之前放開 lock，拿到 completion 之後再取得 | 等 HW 的時候不擋住別的 fault |
| 每次重新取得 lock 之後，重新讀 state，不沿用放開之前讀到的值。可以沿用的只有三樣：這個 page 的 frame 編號、chunk 清單、COT entry 的內容 | 放開的期間別的 thread 可能改了任何表格。那三樣不會變，是因為 page 在 DECOMPRESSING，別人碰到它只會等 |
| 要不要用 LZ4 HW，在握著 lock 時讀一次 `lz4_off`，之後用讀到的那份 | 同上，放開之後別的 thread 可能改它 |
| completion 的 tag 跟這個 job 自己的 tag 比 | 同時有好幾個 job 在外面 |
| DECOMPRESS 回來之後、取得 lock 之前做 `cache_invalidate`，不論 status 是什麼，也不論這次有沒有用到 LZ4 HW | 見第 6 節 |
| LZ4 HW 沒回 OK 時，先由 `sw_decode` 再解一次。兩邊都失敗才標成 LOST | LOST 不能復原。見 3.6 |
| `sw_decode` 寫 frame 是在 `cache_invalidate` 之後，寫完立刻 `cache_clean` | 順序反過來的話，`cache_invalidate` 會丟掉 CPU 剛寫的 line。`cache_clean` 的理由見 6.3 |
| RW page：先清 COT entry，再把 chunk 還給 bitmap | COT entry 永遠不會指向 free 的 chunk |
| `pte_map` 是最後一步 | PTE 一有效，user SW 就碰得到，所以其他事都要先做完 |
| 回去之前把這個 page 記進這個 thread 的 `fresh`。別的 thread 先取回的也記 | reclaimer 不會在 CPU 重試之前把它搬走。見 5.4 |
| 沒有 free frame 時先 `wake_reclaimer` 再 `wait_frame` | reclaimer 可能正睡著 |
| 做完之後如果 free frame 不多於 `fc_low` 個，叫醒 reclaimer。正式大小的機器是 {{fc_low}} 個 | fault 本身不做 reclaim，只有完全沒有 frame 時才等 |
| CPU 回來重新執行同一道指令，PTE 還是無效就再 fault 一次 | 這是 CPU 本來的行為，kernel 不必另外處理 |
| `page_fault` 只處理 PTE 無效造成的 fault。寫一個 RO page 是權限錯誤，不走這裡 | RO page 的 PTE 是唯讀的，見 4.7 |

DECOMPRESSING 與 COMPRESSING 是所有 thread 碰到同一個 page 時會合的地方。任何要拿掉這兩個 state、或讓它們涵蓋的範圍變小的修改，都要先在 7.4 加一個反例，確認檢查擋得住，才可以動。Linux 在 2017 年為了速度繞過它對應的會合點，藏了一個會掉資料的 race 六年多，2025 年 12 月整個拿掉。出處在 `reference/linux-zram-study.md` 的 3.4。

### 3.6 LZ4 HW 答錯或不回答

LZ4 HW 可能回一個不是 OK 的 status，也可能完全不回。kernel 分不出是 stream 壞了還是 HW 出錯，所以用自己的 decoder 當第二個意見。這個 decoder 只會解壓縮，是 kernel image 的一部分，放在壓縮層之外。要不要帶它見 D13。

兩個 decoder 的嚴格程度不必相同。LZ4 HW 的 decoder 不檢查 encoder 結尾的那幾條規定，一般的軟體 decoder 會檢查，見硬體設計規格 7.4 與 12.4。存進 chunk pool 的 stream 都出自守規定的 encoder，所以兩邊對同一份完好的 stream 答案相同。之後換 encoder 時要重新確認這一點。

下面是實際的一次：DECOMPRESS 回 BUS_ERROR，stream 其實完好，page 沒有損失。

{{walk:rescued}}

每一種回答怎麼處理：

| LZ4 HW 的回答 | kernel 做什麼 | 算不算 HW 答錯 |
|---|---|---|
| DECOMPRESS 回 OK | 照 3.2 與 3.3 | 不算，計數歸零 |
| DECOMPRESS 回 BAD_STREAM，`sw_decode` 解得出來 | 用 `sw_decode` 寫進 frame 的內容，page 回到 PRESENT | 算 |
| DECOMPRESS 回 BAD_STREAM，`sw_decode` 也失敗 | stream 真的壞了，page 標成 LOST | 不算，計數歸零 |
| DECOMPRESS 回 BUS_ERROR | 由 `sw_decode` 決定：解得出來就是 PRESENT，否則 LOST | 算 |
| COMPRESS 回 OK 或 INCOMPRESSIBLE | 照 4.4 與 4.5 | 不算，計數歸零 |
| COMPRESS 回 BUS_ERROR | chunk 全部還回去，PTE 恢復，page 留在 frame。不記進 `incompressible` | 算 |
| COMPRESS 回 OK，開著 `verify` 而且比對不符 | 同上。見 4.8 | 算 |
| 交出去之後沒有 completion，`lz4_job` 回 None | DECOMPRESS 走 `sw_decode`，COMPRESS 把 page 留在 frame | 立刻停用 |

{{src:note_hw}}

連續 {{strikes}} 次答錯，或一次沒有 completion，kernel 就設 `lz4_off`，到下次開機為止不再使用 LZ4 HW。沒有 completion 就立刻停用的理由：`lz4_job` 回 None 表示 driver 已經做過 timeout、reset 與重送，都沒有用。再送下一個 job 只是再等一次 timeout。

停用之後：

| 項目 | 停用之後 |
|---|---|
| RO page 的 fault | `sw_decode`，一樣取得回來 |
| 已經存在 chunk pool 的 RW page 的 fault | `sw_decode`，取回後照常清 COT entry、還 chunk |
| 搬走 RO page | 照常，本來就不需要 LZ4 HW |
| 搬走 RW page | 不做。`pick_victim` 跳過所有 RW page |
| 整體 | RW page 只進 frame、不再出去。frame 放得下所有用到的 RW page 就能繼續跑，放不下就會走到沒有 frame 可以釋放 |

所以停用是撐住，不是正常運作。多個 thread 下的結果在 7.3。之後系統該怎麼辦是產品的決定，見 D14。

## 4. Reclaim

### 4.1 一次 reclaim 的全貌

reclaimer 被叫醒後，一直搬到 free frame 達到 `fc_high` 個為止。正式大小的機器是 {{fc_high}} 個，小機器是 {{small_fc_high}} 個。下面是小機器上的一次。

{{walk:reclaim}}

{{src:reclaim}}

### 4.2 選哪一個 page

clock：一根指針繞著 frame 走。碰到 accessed bit 是 1 的 page 就清成 0 並放過它，碰到 0 的就選它。pin 住的 page 與任何 thread 的 `fresh` 裡的 page 直接跳過。`lz4_off` 之後所有 RW page 也跳過。

{{src:pick_victim}}

### 4.3 搬走 RO page

不需要 LZ4 HW，因為 stream 一直都在。

{{walk:evict_ro}}

{{src:evict_ro}}

### 4.4 搬走 RW page

{{walk:evict_rw_ok}}

### 4.5 RW page 壓不進 7 個 chunk

LZ4 HW 回 INCOMPRESSIBLE，frame 沒被動過。kernel 把 chunk 還回去，page 留在原地。

{{walk:evict_rw_incompressible}}

### 4.6 程序

{{src:evict_rw}}

frame 一還回去就叫醒等 frame 的 thread。

{{src:put_frame}}

### 4.7 順序上的規則

| 規則 | 理由 |
|---|---|
| 只有 reclaimer thread 做 reclaim，而且只有一個 | `evict_rw` 等 job 時會放開 lock。只有一個的話，同一時間最多一個 COMPRESS |
| 先向 bitmap 保留 7 個 chunk，保留不到就什麼都不做 | 失敗時沒有任何東西需要復原 |
| `pte_unmap` 在交 job 之前，而且所有 core 的 TLB 都清完才往下走 | LZ4 HW 讀 frame 的期間，沒有人能寫這個 frame |
| `pte_unmap` 之後、交 job 之前做 `cache_clean` | CPU 寫的內容可能還在 cache 裡。見第 6 節 |
| 成功後先寫 COT entry，再把沒用到的 chunk 還回去，最後才釋放 frame | frame 被釋放的時候，存放的那一份已經完整而且有紀錄 |
| descriptor 只給 chunk 編號，COT entry 由 kernel 在收到 completion 後寫 | LZ4 HW 不需要知道 COT 存在 |
| INCOMPRESSIBLE 時把 page 記下來，之後 clock 會跳過它 | 不重複送一個已知會失敗的 job |
| COMPRESS 沒成功、也不是 INCOMPRESSIBLE 時：保留的 chunk 全部還回去，PTE 恢復，page 留在 frame，不記進 `incompressible` | 失敗的是 LZ4 HW，不是這個 page。frame 只被讀過，內容還在。HW 在 chunk 裡寫了什麼不必管，沒有 COT entry 指向它們。7.4 的 `leak_on_job_failure` |
| 重新取得 lock 之後，沿用的只有這個 page 的 frame 編號與保留的 chunk 清單 | 與 3.5 同一條。page 在 COMPRESSING，別人碰到它只會等 |
| RO page 的 PTE 是唯讀的 | `evict_ro` 直接丟掉 frame。有人寫過的話，那些寫入就不見了 |
| `put_frame` 叫醒等 frame 的 thread | 否則它們沒有別的機會醒來 |

### 4.8 bring-up 用的選項：存完再解開比對

`verify` 打開時，COMPRESS 回 OK 之後，kernel 把剛存進 chunk 的 stream 用自己的 decoder 解開，與 frame 逐 byte 比對，相同才釋放 frame。它抓的是 CRC-32 抓不到的那種錯：LZ4 HW 存了內容不對、但 stream 與 CRC 彼此一致的資料。

{{src:stored_right}}

| 項目 | 內容 |
|---|---|
| 代價 | 每次 COMPRESS 多一次軟體解壓縮與一次 4096 B 的比對 |
| 什麼時候開 | RTL 與 FPGA 的 bring-up，以及晶片回來的頭一段時間。量產要不要留著，等有時間的模擬再看 |
| 比對不符時 | 當作 COMPRESS 失敗，算一次答錯。page 留在 frame，資料沒有損失 |
| 模擬裡的結果 | 讓 LZ4 HW 存錯一次內容。開著 `verify`：當場擋下，page 沒事。關著：要到結束時的 A4 才發現，這時 frame 早已釋放 |

## 5. 不能等的地方

`page_fault` 會睡：等 LZ4 HW、等別人的 job、等 free frame。所以有些地方不可以發生 page fault。這一節是這些地方的規則。

### 5.1 哪些 context 不能 page fault

| context | 為什麼不能 | 規則 |
|---|---|---|
| ISR | ISR 不能睡 | 它要碰的 page，事先由 thread 用 `pin_page` 留在 frame 裡 |
| 關著 interrupt 或握著 spinlock 的 kernel 程式 | 睡了就沒有人放 lock，completion 的 interrupt 也進不來 | 同上 |
| 握著 kernel 表格那把 lock 的程式 | `page_fault` 要拿的是同一把 lock | kernel 的程式、stack 與表格全部在壓縮層之外 |
| `page_fault` 與 reclaimer 本身，LZ4 HW 的 driver 與它的 ISR | fault 處理到一半再 fault，沒有人能處理 | 同上 |
| HRT thread | 等一個 job 要多久沒有上限 | 見 5.3 |

`page_fault` 一進來先問 `may_wait`，不行就報 `FaultNotAllowed`。產品上這應該是 kernel panic，印出 page 與 PC，見 D9。

立刻報錯的理由：這種錯只有在那個 page 剛好被搬走時才會發生。平常測試時 page 多半在 frame 裡，測不到。悄悄卡住比立刻停下難查得多。

### 5.2 `pin_page` 與 `unpin_page`

下面三種存取，事前要先 pin。

| 誰要碰 user SW 的 page | 為什麼光靠 CPU MMU 不夠 |
|---|---|
| ISR 或其他不能等的 context | 會 page fault，但是 fault 沒辦法處理 |
| kernel 經由自己的 mapping | kernel 的 mapping 一直指著那個 frame。page 被搬走後不會 fault，kernel 直接讀寫到別的 page |
| DMA 或其他 bus master | 完全不經過 CPU MMU |

{{src:pin_page}}

{{src:unpin_page}}

| 規則 | 理由 |
|---|---|
| `pin_page` 只能在可以等的 thread 裡呼叫 | 它可能要先把 page 取回來 |
| pin 是計數的 | 兩個 driver 可以各自 pin 同一個 page |
| 只有 PRESENT 的 page 能 pin。正在 COMPRESS 的要等它結束再取回 | 否則 pin 到的是一個馬上要被釋放的 frame |
| `pick_victim` 跳過 pin 住的 page | pin 的意義就是這個 |
| `unpin_page` 之後如果 free frame 不多，叫醒 reclaimer | 多了一個可以搬的 page |
| thread 結束之前把自己 pin 的都 unpin | 否則那個 frame 永遠回不來 |
| `pin_page` 回 `lost` 時，呼叫的人結束這次操作並回報錯誤，不可以碰那個 page。擁有這個 page 的 user SW 被結束 | page 已經沒有任何一份。這時它沒有 frame，照樣去碰就是碰到別的 page |
| pin 住的 page 要算進 frame 的下限 | 見 5.4 |

模擬裡 user0 扮演 driver：pin 一個 page，從 ISR 碰它，再經由 kernel 的 mapping 碰它，然後 unpin。忘了 pin 的結果在 7.4 的 `forget_pin`。

### 5.3 HRT thread

HRT 自己的記憶體本來就在壓縮層之外。問題在它間接碰到的東西：共用的函式庫程式碼、共用的資料、放在一般區域的 stack。只要其中一個 page 在壓縮層裡，HRT thread 就可能 page fault。

兩種做法列在 D10。我的建議是 HRT thread 的位址空間完全不對應壓縮層的 page。這樣只要碰到就一定 fault，第一次執行就看得到。如果只靠 pin，漏掉一個 page 要等它剛好被搬走才會出事。

另一件相關的事：`pte_unmap` 要清所有 core 的 TLB。HRT 的 core 如果完全不對應壓縮層的 page，就不必參與。

### 5.4 一道指令需要好幾個 page

一道指令可能同時需要程式碼的 page 與資料的 page，跨過 page 邊界時更多。CPU 每次 fault 回來都從頭重跑這道指令，所以這些 page 要同時在 frame 裡，指令才跑得完。

`fresh` 就是為了這件事：每個 thread 記住自己最近 `protect` 次 fault 取回的 page，reclaimer 不搬它們。

{{src:note_fresh}}

{{src:thread_gone}}

| 規則 | 理由 |
|---|---|
| 每個 thread 一份，不是每個 core 一份 | thread 等第二個 page 時會睡著，同一個 core 換別的 thread 跑，它也會 fault。每個 core 一份的話，第一個 thread 的 page 就被擠掉了 |
| `protect` 至少是一道指令最多會碰到的 page 數 | 少了的話同一道指令永遠湊不齊它要的 page。7.4 的 `protect_1` |
| 別的 thread 先取回的 page 也記進自己的 `fresh` | 這個 thread 的指令一樣需要它 |
| 保護到這個 thread 再 fault `protect` 次，或 thread 結束為止 | kernel 不知道指令什麼時候跑完，只知道下一次 fault |
| thread 結束時呼叫 `thread_gone` | 否則它的 page 永遠不能搬 |
| frame 的數量要大於 thread 數乘 `protect`，再加上 pin 住的 page 數 | 最壞的情況是每個 thread 都占滿自己的份，這時還要有一個 frame 給正在 fault 的那個 thread。7.4 的 `too_few_frames` |

最後一條在正式大小的機器上很容易滿足：{{frames}} 個 frame，thread 數乘 `protect` 只有幾十到幾百。但 D1 選 A 的話，incompressible page 也占著 frame 不能搬，要一起算進去。

## 6. CPU cache 與 LZ4 HW

LZ4 HW 是 bus master，直接讀寫 DRAM。CPU 則是經過自己的 cache 讀寫。除非 HW 的 master port 接成與 CPU cache coherent，否則兩邊看到的同一個 frame 可能不一樣。

這種錯不會被 CRC-32 發現。CRC 是 LZ4 HW 對它自己讀到或寫出的 byte 算的，所以永遠跟 HW 看到的內容一致。

### 6.1 沒處理會出什麼事

| 情況 | 發生什麼 | 結果 |
|---|---|---|
| COMPRESS 一個 CPU 剛寫過的 frame | CPU 寫的內容還在 cache 裡，DRAM 裡是舊的。HW 壓的是舊的 | user SW 的寫入不見了。stream 與它的 CRC 彼此一致，沒有任何檢查會報錯 |
| DECOMPRESS 到一個 CPU cache 裡還留著舊 line 的 frame | DRAM 是對的，CPU 讀到的是 cache 裡前一個 page 的內容 | user SW 讀到別的 page 的資料 |
| 同上，而且 page 是程式碼 | instruction cache 裡是前一個 page 的指令 | CPU 執行到別的程式碼 |

### 6.2 kernel 做什麼

| 時機 | 呼叫 | 為什麼在這個時間點 |
|---|---|---|
| `evict_rw`：`pte_unmap` 之後，交 COMPRESS 之前 | `cache_clean` | `pte_unmap` 之後沒有人能再寫這個 frame，這時寫回 DRAM 的才是最後的內容 |
| `fault_in`：DECOMPRESS 回來之後，`pte_map` 之前 | `cache_invalidate`，所有 core 的 data cache 與 instruction cache | 做在 job 之後，job 進行中才被帶進 cache 的 line 也一併清掉。不論 status 是什麼都做，kernel 不必知道 HW 寫了多少 |
| `boot`：第一步 | `cache_flush_layer`，frame 區與 chunk pool，所有 core | 開機前誰用過這些記憶體、cache 裡留著什麼，kernel 不知道。做完這一步，6.3 的不變量才開始成立 |
| `sw_decode`：`frame_write` 之後 | `cache_clean` | 這個 frame 是 CPU 寫的。見 6.3 |
| `sw_decode` 與 `verify`：讀 chunk | 包在 `chunk_read` 的定義裡 | chunk 是 LZ4 HW 寫的。做法有兩種：讀之前先把那幾條 line 作廢，或把 chunk pool 對應成 non-cacheable |

`cache_clean` 與 `cache_invalidate` 都在沒握 lock 的時候做。這段期間 page 的 state 是 COMPRESSING 或 DECOMPRESSING，別人不會碰它。

`zero_frame` 是 CPU 自己寫的，LZ4 HW 不參與，所以不需要處理。

### 6.3 為什麼這樣就夠

靠的是一個不變量：free frame 在任何 CPU cache 裡都沒有還沒寫回的 line。所以 DECOMPRESS 寫一個 frame 的時候，不會有舊的 line 事後蓋回 DRAM。

| 一個 frame 怎麼變成 free | 為什麼沒有還沒寫回的 line |
|---|---|
| 開機後還沒用過 | `boot` 第一步的 `cache_flush_layer` |
| RO page 被搬走 | user SW 不能寫 RO page。frame 的內容如果是 `sw_decode` 寫的，寫完當場已經 `cache_clean` |
| RW page 的 COMPRESS 回 OK | 交 job 之前已經 `cache_clean`，而且 `pte_unmap` 之後沒有人能寫 |
| LZ4 HW 與 `sw_decode` 都沒解出來，page 變成 LOST | 這個 frame 從拿到手到釋放，CPU 都沒寫過 |

所以任何會寫 frame 的 kernel 程式都要守住它。`zero_frame` 與開機時的 `frame_write` 寫的是 RW page，它之後要離開 frame 一定經過 `evict_rw` 的 `cache_clean`。`sw_decode` 寫的可能是 RO page，RO page 離開 frame 時沒有任何 cache 操作，所以 `sw_decode` 自己做。

之後如果加上不經過 COMPRESS 就釋放 RW frame 的功能，例如把 page 還給系統，釋放之前也要 `cache_clean`。

chunk 這一邊比較單純。寫 chunk 的只有 LZ4 HW 與開機前的 boot loader，CPU 從來不寫，所以開機那次 `cache_flush_layer` 之後，cache 裡不會有 chunk 的還沒寫回的 line。CPU 讀 chunk 只發生在 `sw_decode` 與 `verify`，規則就是 `chunk_read`。

### 6.4 模擬怎麼檢查

`cache.py` 對每個 frame 與每個 chunk 記幾個 flag，採最悲觀的假設：CPU 碰過就當作整個 frame 都在 cache 裡，寫過就當作都還沒寫回。開機時全部從「有 line、還沒寫回」開始，直到 `cache_flush_layer`。所有 core 合成一份，因為這些呼叫的定義就是作用在所有 core。

| 編號 | 檢查 |
|---|---|
| C1 | LZ4 HW 讀一個 frame 或 chunk 時，CPU cache 裡沒有比 DRAM 新的 line |
| C2 | LZ4 HW 寫一個 frame 或 chunk 時，CPU cache 裡沒有還沒寫回的 line |
| C3 | CPU 讀或執行一個 frame、或讀一個 chunk 時，不會經過比 DRAM 舊的 line。CPU 執行一個 frame 時，它最新的內容不會只在 data cache 裡 |
| C4 | 作廢 line 的時候不會丟掉還沒寫回的 line |

拿掉 `cache_clean` 會違反 C1，拿掉 `cache_invalidate` 或只清 data cache 會違反 C3。拿掉開機的 `cache_flush_layer` 會違反 C2。`sw_decode` 之後不做 `cache_clean`，以及 `chunk_read` 經過舊的 line，都違反 C3。六種都在第 1 個 schedule 被擋下，見 7.4。

### 6.5 兩邊都會碰的其他記憶體

兩個 ring 不在 host simulation 裡。這一節的規則都寫進介面規格，編號 `FW-CACHE-1` 到 `FW-CACHE-5`。前兩條就是 6.2 的 `cache_clean` 與 `cache_invalidate`。

`FW-CACHE-5` 是通則：LZ4 HW 會寫的每一塊記憶體，不與 CPU 會寫的其他資料共用 cache line。否則 CPU 寫回自己那部分時，會把同一條 line 上 HW 寫的內容蓋掉。frame 與 chunk 的大小都是 cache line 的整數倍而且對齊，本來就滿足。要另外處理的是 completion ring。

| 記憶體 | 誰寫 | 誰讀 | 規則 |
|---|---|---|---|
| job ring 的 descriptor | kernel | LZ4 HW | 寫 JOB_TAIL 之前，descriptor 已經在 DRAM 裡。把 ring 對應成 non-cacheable 最單純 |
| completion ring | LZ4 HW | kernel | kernel 讀的時候不經過舊的 line。同上。不對應成 non-cacheable 的話，`CPL_BASE` 要對齊 64 B，ring 占滿整數條 line，這是 `FW-CACHE-5` |
| chunk pool | 開機時是 boot loader，之後只有 LZ4 HW | LZ4 HW。kernel 只在 `sw_decode` 與 `verify` 讀 | boot loader 放進去的 RO chunk 在 ENABLE 之前已經在 DRAM 裡，由 `cache_flush_layer` 保證。kernel 從不寫 chunk，讀的時候用 `chunk_read` |
| COT | boot loader 與 kernel | kernel | LZ4 HW 不讀 COT，所以沒有這個問題 |

## 7. 多個 thread 交錯執行

### 7.1 模型

跑的是同一份 `kernel.py`。每個 user SW thread、reclaimer thread 與 LZ4 HW 各是一個 task，任何時刻只有一個 task 在跑。task 跑到下面這些位置時，接下來換誰跑由 scheduler 決定。

| 可以換人的位置 | 對應到真實系統的什麼 |
|---|---|
| 取得 lock 之前 | 另一個 core 先拿到 lock |
| CPU 執行一道指令之前 | fault 回來到重跑指令之間，別的 thread 或 reclaimer 先跑 |
| job 在 LZ4 HW 裡的期間 | HW 在忙的時候所有 thread 都能跑 |
| 任何等待：等 job、等 page、等 frame | thread 睡著 |

同樣的選擇會得到完全相同的執行，所以出錯的 schedule 可以重跑，錯誤訊息裡附最後 40 步。

| scheduler | 做法 |
|---|---|
| 隨機 | 每個位置用固定 seed 的亂數決定換不換人 |
| 列舉 | 平常不打斷任何人。把「在某一步打斷、換成某個 task」的所有可能各跑一次，再加上打斷兩次的所有組合 |
| 優先權 | 指定的 task 只要能跑就先跑。用來模擬 reclaimer 的優先權比 user SW 高 |

腳本裡除了存取，還可以安插下面這些事件。位置由固定的 seed 決定，所以一樣可以重跑。

| 事件 | 作用 |
|---|---|
| `damage` | 把存放中的一個 stream 改掉一個 byte |
| `hwfault` | 讓下一個 COMPRESS 或 DECOMPRESS 回 BUS_ERROR，或讓下一個 DECOMPRESS 對完好的 stream 回 BAD_STREAM |
| `hwdown` | 從這裡起 LZ4 HW 不再回答，`lz4_job` 回 None |
| `kill` | 終止另一個 user SW thread。它正在 kernel 裡的話，等它回來才生效 |

機器刻意做得很小：{{tiny_frames}} 個 frame，{{tiny_rw}} 個 RW page，{{tiny_ro}} 個 RO page，兩個 core，三個 user SW thread，每個 thread 30 步。frame 一直不夠用，所以等待的路徑一直在發生。每個 thread 的一步是一道指令，用一個程式碼 page，多半再加一個資料 page。有些 page 三個 thread 共用。

### 7.2 檢查什麼

| 檢查 | 內容 | 違反時報的錯 |
|---|---|---|
| lock | kernel 經由 port 碰表格時，握著 lock 的是自己。交 job 時沒有握 lock | `KernelBug` |
| TLB | 沒有 core 還在用 kernel 已經拿掉的 translation | `StaleTlb` |
| job | 兩個 job 不共用 frame 或 chunk。CPU 不碰 job 手上的 frame。pin 住的 frame 不會進 job | `JobRace` |
| 資料 | 每道指令看到的都是 user SW 最後寫的內容 | `DataMismatch` |
| cache | C1 到 C4 | `CacheError` |
| context | 不能等的地方沒有 page fault | `FaultNotAllowed` |
| kernel mapping | kernel 經由自己的 mapping 碰的 page 確實有 frame | `AliasError` |
| 前進 | 同一道指令不會一直 fault | `NoProgress` |
| 結束 | 每個 thread 都跑完。有人還在等的話，分辨是真的沒有 frame 還是沒人叫醒 | `OutOfMemory`、`Deadlock` |
| audit | 全部結束後做第 9 節的 A0 到 A7 | `AuditError` |

### 7.3 結果

沒有任何一個 schedule 違反檢查。

{{conc_survey}}

LZ4 HW 出錯與 thread 被終止的部分，跑的也是沒改過的 kernel：

{{conc_survey_faults}}

列舉的部分：

{{conc_explore}}

讀法：

- 上一版列為「程式裡有寫、沒被執行過」的四種情況，現在都執行過很多次。碰到正在 DECOMPRESS 的 page {{conc_w_dec}} 次，碰到正在 COMPRESS 的 {{conc_w_comp}} 次，醒來發現別人已經取回 {{conc_spurious}} 次，等 frame {{conc_w_frame}} 次。
- 等 frame 的次數這麼多是因為機器只有 {{tiny_frames}} 個 frame。這是刻意的，不代表正式機器的行為。
- 弄壞 stream 的那一組確認了 LOST 這條路在多個 thread 下也走得通：等同一個 page 的 thread 都被叫醒，都拿到 `lost`。這一組裡 kernel 自己再解了 {{dmg_sw}} 次，解出來 {{dmg_sw_ok}} 次。stream 真的壞了的時候，第二個意見不會把壞的資料交給 user SW。
- 第二張表左欄：{{f_n}} 個 schedule 裡 `sw_decode` 做了 {{f_sw}} 次，全部解回正確的內容。COMPRESS 失敗 {{f_cfail}} 次，page 都留在 frame。{{f_killed}} 個 thread 被終止。沒有 page 變成 LOST，也沒有 schedule 走到停用 LZ4 HW。
- 第二張表右欄：{{d_n}} 個 schedule 裡 {{d_off}} 個走到停用，其餘的在 HW 停止回答之後沒有再送 job。停用之後 RO page 照常進出，`evict_ro` {{d_ro}} 次，`sw_decode` {{d_sw}} 次全部正確。`evict_rw` 的 {{d_rw}} 次是停止回答之前做的，加上發現它不回答的那幾次。
- 右欄的機器有 {{roomy_frames}} 個 frame，放得下全部 {{tiny_rw}} 個 RW page。同樣的事件放在 {{tiny_frames}} 個 frame 的機器上會停在 `OutOfMemory`，測試裡有這一項。這就是 3.6 最後一張表「整體」那一列。
- 隨機與列舉都不是證明。它們能說的是：這個模型表現得出來的交錯裡，試過的這些沒有錯。

### 7.4 拿掉一樣東西，看哪一項檢查擋下來

這張表回答兩個問題：控制程序裡的每一步是不是真的需要，以及模擬的檢查是不是真的抓得到錯。每一列只改一樣東西，然後跑隨機 schedule，直到有檢查擋下來。

{{conc_mutants}}

讀法：

- {{conc_mutants_all}} 種裡 {{conc_mutants_stopped}} 種被擋下。
- `shared_tag` 與 `no_wake_frame` 是先前修掉的兩個錯原本的樣子。`sw_decode_no_clean` 是這一次的：模擬先跑出這個錯，才有 `cache_clean` 這一步，見 F21。
- `no_compressing` 是間接被擋下的。少了 COMPRESSING，`pin_page` 會 pin 到一個正在被搬走的 page，之後 ISR 碰它時才出事。
- `protect_1` 用的是優先權 scheduler。reclaimer 每次都搶在 user SW 重跑指令之前，把它上一次取回的 page 搬走。隨機 schedule 很難連續碰上這麼多次，但在 reclaimer 優先權較高的真實系統上這是常態。
- `too_few_frames` 沒有改控制程序，改的是機器。它示範 5.4 最後一條規則不成立時的結果。
- `no_sw_decode` 與 `leak_on_job_failure` 執行當中沒有任何檢查會響，靠的是結束時的 audit：前者是新加的 A7，後者是 A2。
- `kill_in_kernel` 沒有改控制程序，改的是平台。它示範 7.5 那條「等它回來」的要求不成立時的結果。

### 7.5 對平台的要求

port 的實作要做到下面這些，控制程序才正確。右欄寫了名稱的，在 7.4 有對應的反例。

| 要求 | 不做到的話 |
|---|---|
| `wait_page` 與 `wait_frame`：放開 lock 與睡著是同一步，中間不能漏掉叫醒。也就是 condition variable 的語意 | `wait_not_atomic`：叫醒落在空隙裡，thread 永遠睡著 |
| `wake_reclaimer`：reclaimer 正在跑的時候，要求要留著，它睡之前會再看一次 | `unlatched_reclaimer`：所有 thread 等 frame，reclaimer 在睡 |
| `pte_unmap`：所有 core 的 TLB 都清完才回來 | `local_tlb_flush`：別的 core 繼續寫一個正在被壓縮的 frame |
| `cache_clean` 與 `cache_invalidate`：作用在所有 core。invalidate 包含 instruction cache | `no_cache_clean`、`no_cache_invalidate`、`invalidate_dcache_only` |
| `lz4_job`：可以被好幾個 thread 同時呼叫，completion 用 tag 交還給送出它的那個 thread | `shared_tag` |
| `may_wait`：ISR、關著 interrupt、握著別的 lock、HRT thread 都回答不行 | 該報錯的地方變成卡住 |
| thread 在 `page_fault`、`pin_page`、`unpin_page` 裡面的時候不可以被終止，要等它回來 | `kill_in_kernel`：page 留在 DECOMPRESSING，卻沒有 job 在做，等它的 thread 永遠等下去 |
| `lz4_job`：等不到 completion 時不可以永遠等。driver 做完 timeout、reset 與重送之後回 None | 送 job 的 thread 不回來，page 留在 DECOMPRESSING 或 COMPRESSING，等同一個 page 的 thread 全部卡住 |
| `chunk_read`：讀到的是 DRAM 現在的內容 | `chunk_read_cached` |
| `cache_flush_layer`：開機時把 frame 區與 chunk pool 在所有 core 的 line 寫回並作廢 | `no_boot_flush` |
| `cache_clean`、`cache_invalidate`、`chunk_read`、`frame_write`、`frame_read`：都經由 kernel 自己的 mapping 做，因為這時 user SW 的 PTE 是無效的 | 做不到的話這些呼叫沒有位址可用。取決於 CPU 與 kernel，見 D8、D11 |
| thread 結束時：先 unpin 它 pin 的 page，再呼叫 `thread_gone` | frame 永遠回不來 |
| `spurious` 回去之後 CPU 還是 fault 的話，清掉這個 core 對這個 page 的 TLB 項目 | 有些 CPU 會把無效的 translation 也記在 TLB 裡。取決於 CPU |
| RO page 的 PTE 是唯讀的。寫入造成的 fault 不交給 `page_fault` | 見 4.7 |

### 7.6 這個模型看不到的

| 看不到的 | 原因 | 靠什麼補 |
|---|---|---|
| 任何與時間有關的事 | 沒有時間 | `sim/ifsim` |
| 兩個 core 真的同時執行握著 lock 的區段 | 模型裡握著 lock 的區段不可分割，所以 lock 從來不會被搶 | lock 本身的正確性是平台的責任 |
| 沒握 lock 就直接讀 kernel 的表格 | 只有經過 port 的存取會被檢查 | review：`kernel.py` 裡表格只在握著 lock 時讀寫 |
| 打斷三次以上才會出現的錯 | 列舉只做到兩次，隨機不保證碰到 | 之後可以加大，時間會快速增加 |
| CPU 的 memory ordering，寫 PTE 之後需要的 barrier | 取決於 CPU | 平台移植時處理 |
| job ring 滿了、interrupt 掉了、timeout、reset | 這裡的 LZ4 HW 是一個函式。只模擬它們最後的結果：`lz4_job` 回 None | `sim/ifsim` |

## 8. 不含時間的數字

正式大小的機器：{{pages}} 個 page，{{frames}} 個 frame，chunk pool {{pool_chunks}} 個 chunk，{{accesses}} 次 access，seed 1，一個 thread。負載是合成的，所以這些數字是用來比較做法，不是用來預測產品。

### 8.1 三種執行的結果

{{results}}

各個 user SW 在第一種執行裡的情況：

{{clients}}

### 8.2 Reclaim

{{reclaim}}

clock 最長的一次選擇看了 {{clock_longest}} 個 frame。那是第一次 reclaim：開機後每個 page 的 accessed bit 都是 1，指針要先繞一圈把它們清掉。

### 8.3 Chunk pool 與 bitmap

{{pool}}

{{hist}}

### 8.4 資料不好壓、記憶體用完的時候

小機器：512 個 frame，chunk pool 8192 個 chunk，1280 個 RW page。把 RW 資料換成更難壓的，看控制程序怎麼結束。

{{stress}}

讀法：

- 「留在 frame」的做法，在壓縮後 80% 的資料下有 182 個 frame 被 incompressible page 占住，等於 frame 少了三分之一，所以 job 變多。
- 到 90% 時幾乎所有 frame 都被占住。chunk pool 還有一大半是空的，機器卻沒有 frame 可用。
- 「RAW 存進 8 個 chunk」不省空間，但能把 page 從 frame 移到 chunk pool。三種資料下 job 數相同，都跑得完。
- 沒有 `fresh` 保護時，機器不會報 `OutOfMemory`，而是卡在同一道指令上：reclaimer 唯一能搬的就是剛 fault 進來的那個 page。

### 8.5 放得下多少 RW page

frame 加上開機後 chunk pool 的空位，能放多少個 RW page，取決於資料好不好壓。

{{capacity}}

## 9. 檢查

每次執行結束後，以及測試裡每隔一段 access，整台機器會被檢查一次。檢查只看 DRAM、PTE 與 kernel 的表格，不管 kernel 是怎麼走到這裡的。

| 編號 | 檢查 |
|---|---|
| A0 | 沒有人還握著 lock |
| A1 | 一個 page 有 frame，若且唯若它是 PRESENT。PTE、`frame_of`、`owner` 三者一致。每個 frame 不是 free 就是只被一個 page 占用 |
| A2 | 每個 chunk 不是在 bitmap 裡 free，就是只被一筆有效的 COT entry 列出 |
| A3 | RO page 的 COT entry 永遠有效。RW page 的 entry 有效，若且唯若它是 COMPRESSED 或 LOST |
| A4 | 每個 page 不管現在在哪裡，內容都是 user SW 最後寫進去的。存放中的 stream 會實際解開來比對 |
| A5 | kernel image、pinned data、HRT 記憶體一個 byte 都沒變 |
| A6 | pin 住的 page 與任何 thread 的 `fresh` 裡的 page 都是 PRESENT。`fresh_n` 與各 thread 的清單一致 |
| A7 | LOST 的 page，存放的 stream 確實是壞的：CRC-32 不符，或解不出 user SW 最後寫的內容 |

另外，每次 fault 完成後，取回的 page 內容會立刻跟 user SW 最後寫入的內容比對。執行當中的檢查在 6.4 與 7.2。

{{audit}}

資料損毀的情況另外測過：把存放中的 RW stream 改掉一個 byte，LZ4 HW 在寫 frame 之前就用 CRC-32 發現，回 BAD_STREAM。kernel 自己再讀一次 chunk，CRC-32 一樣不符，才把 page 標成 LOST。下面是實際的一次。

{{walk:lost}}

## 10. 要一起決定的事

D1 到 D7 是第一版就有的。D4 的內容因為 F13 改過。D8 到 D12 是處理正確性問題時新增的。D13 與 D14 是對照 Linux zram 之後新增的。D13 我先替你選了 B 並照它實作，請確認。D6、D8、D11 的內容這次有補充。

| 編號 | 問題 | 選項 | 我的建議 |
|---|---|---|---|
| D1 | 壓不進 7 個 chunk 的 RW page 怎麼辦 | A：留在 frame，之後不再嘗試。這是目前的做法。B：RAW 存進 8 個 chunk | B。8.4 顯示 A 會在 chunk pool 還很空的時候就把 frame 用完。B 不需要改介面，COMPRESS 的 `limit` 給 4096 就是了 |
| D2 | frame 與 chunk pool 都滿了怎麼辦 | A：讓那次 fault 的 user SW 收到錯誤。B：事先限制 user SW 能用的 RW page 數，保證放得下。C：free chunk 低於某個水位時先通知 user SW 釋放記憶體 | 需要你決定產品要哪一種行為。B 最單純，但 8.5 顯示保證得到的容量比平常少很多 |
| D3 | 選 page 的方法 | A：現在的 clock。B：clock 加上每次握 lock 最多看固定個數的 frame。C：優先搬 RO page，因為搬 RO 不用 COMPRESS | 先用 B 解決 F6。F7 的差距等有真實的 access 紀錄再評估，合成負載不足以決定 |
| D4 | `protect` 是多少，也就是每個 thread 的 `fresh` 保護幾個 page | 至少是一道指令最多會碰到的 page 數 | 取決於 CPU。模擬裡一道指令最多用兩個 page，所以用 2。指令與資料都可能跨過 page 邊界的 CPU 至少要 4。需要知道是哪一顆 CPU |
| D5 | CPU MMU 有沒有 accessed bit，清掉它的時候 TLB 要不要處理 | 有硬體 accessed bit、用 fault 模擬、或完全沒有 | 取決於 CPU。沒有的話 clock 要換做法 |
| D6 | LOST 的 page 之後怎麼辦 | RO page 可以從 flash 重新載入。RW page 沒有別的來源 | RO 重新載入值得做。RW 與 D2 一起決定。現在要 LZ4 HW 與 kernel 的 decoder 都解不出來才會 LOST，所以 LOST 表示 DRAM 裡那份 stream 真的壞了 |
| D7 | `.data` 開機時直接放進 frame，還是跟 RO 一樣先壓好放進 chunk pool | 現在是直接放進 frame | 維持現狀，等開機流程確定再看 |
| D8 | LZ4 HW 的 master port 與 CPU cache 的關係 | A：不 coherent，kernel 做 `cache_clean` 與 `cache_invalidate`。這是目前的寫法。B：整合時接成 coherent，兩個呼叫變成空的 | 規格照 A 寫，因為 A 在兩種接法下都正確。B 省下每個 job 的兩次 cache 操作，值不值得等有時間的模擬再看。另外要確認 CPU 的 cache 會不會因為 virtual address 不同，讓同一個 frame 有兩份 line。會的話 `zero_frame` 之後也要處理。還要從 CPU 手冊確認三件事：cache 操作的指令需不需要那個位址有有效的 mapping；kernel 位址與 user 位址會不會各自在 cache 裡留一份 line；「所有 core」是硬體廣播，還是 kernel 要自己通知每個 core。這些呼叫執行時 user SW 的 PTE 是無效的，所以只能經由 kernel 自己的 mapping 做 |
| D9 | 不能等的 context 發生 page fault 時怎麼辦 | A：kernel panic，印出 page 與 PC。B：只留紀錄 | A。這是程式的錯，不是執行時的狀況，越早停越好查 |
| D10 | 怎麼保證 HRT thread 不會 page fault | A：HRT thread 的位址空間不對應壓縮層的任何 page，它用到的共用程式碼與資料另外放一份在壓縮層之外。B：開機時把它會碰到的 page 全部 pin 住 | A。漏掉的話第一次存取就看得到。B 漏掉一個 page，要等它剛好被搬走才出事 |
| D11 | 一個 page 會有幾個 mapping | 控制程序目前假設每個 page 只有一個 PTE。要確認兩件事：kernel 有沒有自己對應所有 frame 的 mapping，不同的 user SW 會不會共用 page | 取決於用哪個 kernel 或 RTOS。有 kernel mapping 的話，kernel 碰 user SW 的 buffer 一律包在 `pin_page` 與 `unpin_page` 之間。有共用 page 的話，`pte_unmap` 要找得到全部的 PTE。這個答案也決定 `cache_clean`、`cache_invalidate`、`chunk_read`、`frame_write` 做不做得到：它們都需要 kernel 有一個碰得到 frame 與 chunk 的 mapping |
| D12 | pin 住的 page 數要不要設上限 | A：不設。B：設上限，超過時 `pin_page` 回錯誤 | B。上限取 frame 數減掉 thread 數乘 `protect` 再留一些餘裕，5.4 的下限就永遠成立。目前的程式還沒有這個上限 |
| D13 | LZ4 HW 失效時要不要有軟體的後路 | A：沒有。LZ4 HW 沒回 OK 就把同一個 job 重送一次，再失敗就是 LOST。HW 壞了系統就停。B：kernel 帶一個只會解壓縮的 LZ4 decoder，放在壓縮層之外 | B，目前照 B 實作。HW 失效之後 RO 的程式碼還取得回來，系統至少能回報與收尾。也因為有它，3.6 不重送：第二個意見來自另一份實作，比同一個 HW 再做一次可靠。連續 {{strikes}} 次這個門檻是我先定的。選 A 的話，3.6 要改回重送一次，`lz4_off` 之後所有 fault 都會失敗 |
| D14 | 停用 LZ4 HW 之後系統怎麼辦 | A：繼續跑，立刻回報，由產品決定什麼時候重開機。RW page 只進不出，frame 用完時照 D2。B：立刻進入安全狀態並重開機 | A。停用之後 RO page 還能進出，足夠把狀況報出去。但它只是撐住，見 3.6。需要你決定產品要哪一種 |

## 11. 這一版沒有涵蓋的

| 情況 | 現況 |
|---|---|
| lock 真的被搶、兩個 core 真的同時執行 | 見 7.6 |
| job ring、doorbell、interrupt、timeout、reset | 在 `sim/ifsim`。對齊時要補兩件事：好幾個 thread 同時送 job，ring 沒有空格時送的人要等；ring 這一層的 timeout、reset 與重送，怎麼變成 `lz4_job` 回 None。後者的流程在介面規格第 9 節 |
| 停用 LZ4 HW 之後的系統行為 | 等 D14。模擬只做到 kernel 這一層：RO page 繼續進出，RW page 不再搬 |
| `verify` 在量產要不要開 | 等有時間的模擬 |
| 共用 page 與 kernel mapping 的實際做法 | 等 D11 |
| 效能類的問題，照決定先不處理 | priority inversion、慢性 thrash 的偵測、TLB 清除的合併、內容全部相同的 page、把 page 還給系統、incompressible 標記的清除、閒置 page 的再壓縮、大的 mapping、ramdump 工具 |

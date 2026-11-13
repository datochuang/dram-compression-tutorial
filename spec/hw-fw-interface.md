# LZ4 加速器 HW/FW 介面規格

版本 0.1-draft，草稿。對象是寫 LZ4 HW 的人與寫 kernel 壓縮層的人。本文把 kernel 這一側稱為 FW。

> 本文由 `sim/ifsim/interface.json` 與 `sim/ifsim/templates/hw_fw_interface.tmpl.md` 產生，指令是 `python3 sim/run_if.py gen-spec`。
> 表格裡的 offset、欄位與規則文字都來自 `interface.json`，模擬器的 HW model、FW model 與 checker 讀的是同一份檔案。要改介面請改那份檔案再重新產生，不要直接改本文。

## 1. 範圍與分工

本文只規定 LZ4 HW 與 FW 之間看得到的東西：register、兩個 ring、三種資料結構、雙方各自要守的規則、interrupt 與 reset 的行為。HW 內部怎麼做 LZ4、FW 怎麼挑 victim page，都不在這裡。

採用偏 SW 控制的做法。複雜而且容易出錯的部分都在 FW，HW 只做一件事：照 descriptor 把一個 page 壓縮或解壓縮。

平台前提 P4，2026-11-13 指定：LZ4 HW 可以同時接受 N 個 job。本文的讀法是 HW 裡有 N 個 engine，同一時間最多執行 N 個 job。N 由 `CAP.ENGINES` 回報。負責人在 2026-11-13 指定 N 先用 4，這是暫定值。register、兩個 ring、descriptor 與 completion 的格式都不因此改變。改變的有三件事：

| 改變的 | 一個 engine 時 | N 個 engine 時 | 在哪裡 |
|---|---|---|---|
| completion 的順序 | 與 job 被取走的順序相同 | 做完的順序，不保證與取走的順序相同 | 第 4 節，`HW-CPL-1` |
| HW 同時碰的記憶體 | 一個 job 的 frame 與 chunk | 最多 N 個 job 的 frame 與 chunk | `HW-MEM-1`，`FW-JOB-6` |
| 錯誤與 reset 影響的 job | 最多一個執行中的 job | 最多 N 個執行中的 job | 第 9 節 |

這個讀法與其中的選擇是寫這份規格時先採用的，還沒有經過負責人確認。待確認的列在未決事項 O7 與 O13 到 O16。模擬器在 2026-11-13 照這個讀法擴充成 N 個 engine，預設 4，見 7.2 後面的說明與 `sim-results-v0.md`。

| 東西 | 擁有者 | 另一方能做什麼 |
|---|---|---|
| COT，每個 page 一筆 entry | FW | HW 不讀也不寫 |
| chunk bitmap，哪些 chunk 是空的 | FW | HW 不知道它存在 |
| page 的狀態與 PTE | FW | HW 不知道它存在 |
| 要壓縮哪個 page、何時壓縮 | FW | HW 不參與 |
| job ring 的內容 | FW 寫 | HW 每個 job 讀一格，一次 |
| completion ring 的內容 | HW 寫 | FW 讀 |
| page frame 與 chunk 的內容 | job 進行中歸 HW，其餘時間歸 FW | 見第 7 節的規則 |
| register | 各欄位見第 3 節 | |

HW 在兩個 job 之間不保留任何狀態，除了 register。同時執行的 job 之間也不共用任何資料狀態。每個 job 需要的資訊都在它的 descriptor 裡。這帶來兩個好處：HW reset 之後不必重建任何東西，FW 把還沒完成的 job 重送一次就好；HW 能碰的記憶體範圍可以用四個 register 圈死，圈不到 HRT 的記憶體。

前提：跑 user SW 的 CPU 有 MMU，page fault 是精確而且可以重新執行的。只有 MPU 的 core 不能用這個方案。

## 2. 一個 job 從頭到尾

先看兩個實際的 job，再看一般的格式。位址用 full-size 的 address map：frame 區從 0x97400000 開始，chunk pool 從 0x86100000 開始。

### 2.1 DECOMPRESS：user SW 碰到一個壓縮著的 RW page

這個 page 的 stream 長 2296 B，放在 5 個 chunk 裡。

| 步驟 | 誰做 | 做什麼 |
|---|---|---|
| 1 | CPU | user SW 讀寫這個 page，PTE 是 invalid，CPU 進入 page fault |
| 2 | FW | 拿 `mm_lock`，確認 page 狀態是 compressed，拿一個 free frame 0x98634000，讀這個 page 的 COT entry，把狀態改成 decompressing，放開 `mm_lock` |
| 3 | FW | 把 COT entry 的 count、comp_len、checksum、chunk 原樣抄進 descriptor，填上 frame_pa 與自己取的 tag 0x2A7 |
| 4 | FW | 拿 `ring_lock`，把 48 B 的 descriptor 寫進 job ring 的下一格，然後寫 `JOB_TAIL`。寫 `JOB_TAIL` 就是 doorbell |
| 5 | HW | 有 engine 空著時，從 `JOB_HEAD` 那一格讀 48 B，讀完把 `JOB_HEAD` 加 1，把這個 job 交給那個 engine。這一格從此歸還 FW |
| 6 | HW | 檢查 descriptor：opcode、count、chunk 號碼、frame_pa、長度。有一項不對就跳到步驟 8，status 是 BAD_DESC，不碰任何記憶體 |
| 7 | HW | 依序讀 5 個 chunk 的前 2296 B，算 CRC-32 並與 descriptor 的 checksum 比對，解成 4096 B 寫進 frame |
| 8 | HW | 把 16 B 的 completion 寫進 `CPL_TAIL` 那一格，然後把 `CPL_TAIL` 加 1。`IRQ_STATUS.DONE` 變 1，`IRQ_ENABLE.DONE` 是 1 的話 interrupt line 拉高 |
| 9 | FW | interrupt handler 或 polling 的 thread 讀 `CPL_TAIL`，把自己的 head 到 tail 之間的 completion 逐格讀出，用 tag 找到對應的 job，最後寫 `CPL_HEAD`。兩者相等時 interrupt line 自動變低 |
| 10 | FW | status 是 OK：拿 `mm_lock`，把這個 page 的 COT entry 清成 0，在 bitmap 釋放那 5 個 chunk，狀態改成 present，最後才把 PTE 寫成 valid |
| 11 | CPU | 從 page fault 返回，重新執行剛才那個指令 |

RO page 的差別只在步驟 10：壓縮的那一份留著，COT entry 與 chunk 都不動，只寫 PTE。

步驟 5 到 8 進行的同時，其他 engine 可以在做別的 job。所以步驟 9 讀到的 completion 不一定照送出的順序，FW 只看 tag。

步驟 4 寫進 job ring 的 descriptor：

| Offset | 記憶體裡的 byte，由低位址到高位址 | 欄位 | 值 |
|---|---|---|---|
| 0x00 | `02` | `opcode` | DECOMPRESS（2） |
| 0x01 | `05` | `count` | 5 |
| 0x02 | `00 10` | `limit` | 4096 |
| 0x04 | `00 40 63 98` | `frame_pa` | 0x98634000 |
| 0x08 | `F8 08` | `comp_len` | 2296 |
| 0x0A | `00 00` | `flags` | 0x0000 |
| 0x0C | `EF BE AD DE` | `checksum` | 0xDEADBEEF |
| 0x10 | `A7 02 00 00` | `tag` | 0x000002A7 |
| 0x14 | `2F 1A 05 13 00 08 02 F0 05 10 B4 06 11 B4 06 00 00 00 00 00 00 00 00 00` | `chunk` | 0x51A2F、0x80013、0x5F002、0x6B410、0x6B411，其餘填 0 |
| 0x2C | `00 00 00 00` | `rsvd` | 0 |

步驟 8 HW 寫回的 completion：

| Offset | 記憶體裡的 byte，由低位址到高位址 | 欄位 | 值 |
|---|---|---|---|
| 0x00 | `00` | `status` | OK（0） |
| 0x01 | `00` | `flags` | 0x00 |
| 0x02 | `00 10` | `length` | 4096 |
| 0x04 | `EF BE AD DE` | `checksum` | 0xDEADBEEF |
| 0x08 | `A7 02 00 00` | `tag` | 0x000002A7 |
| 0x0C | `00 00 00 00` | `aux` | 0 |

### 2.2 COMPRESS：reclaimer 把一個 RW page 壓起來

free frame 少於低水位時，FW 的 reclaimer 挑一個最久沒用的 RW page。壓完的 stream 長 1837 B。

| 步驟 | 誰做 | 做什麼 |
|---|---|---|
| 1 | FW | 拿 `mm_lock`，挑 victim，在 bitmap 預留 7 個 chunk。7 是 limit 3584 B 除以 512 B 進位 |
| 2 | FW | 把這個 page 的 PTE 寫成 invalid，清掉每個 core 的 TLB，狀態改成 compressing，放開 `mm_lock`。從這一刻起 user SW 碰不到這個 frame |
| 3 | FW | 填 descriptor：frame_pa、limit 3584、預留的 7 個 chunk、tag 0x2A8。寫進 job ring，寫 `JOB_TAIL` |
| 4 | HW | 讀 descriptor，推進 `JOB_HEAD`，檢查 descriptor |
| 5 | HW | 讀 frame 的 4096 B，壓成 LZ4 block，邊壓邊算 CRC-32，依序寫進列出的 chunk。stream 超過 limit 就停下，status 是 INCOMPRESSIBLE |
| 6 | HW | 寫 completion，推進 `CPL_TAIL` |
| 7 | FW | 讀 completion。status 是 OK，length 是 1837：只用了前 4 個 chunk |
| 8 | FW | 拿 `mm_lock`，寫 COT entry：comp_len 與 checksum 來自 completion，chunk 是 descriptor 的前 4 個。在 bitmap 釋放沒用到的 3 個 chunk。把 frame 放回 free list，狀態改成 compressed |

status 是 INCOMPRESSIBLE 時，FW 釋放全部 7 個 chunk，把 PTE 寫回 valid，page 留在 frame 裡，之後不再挑它。

步驟 3 的 descriptor：

| Offset | 記憶體裡的 byte，由低位址到高位址 | 欄位 | 值 |
|---|---|---|---|
| 0x00 | `01` | `opcode` | COMPRESS（1） |
| 0x01 | `07` | `count` | 7 |
| 0x02 | `00 0E` | `limit` | 3584 |
| 0x04 | `00 C0 A1 97` | `frame_pa` | 0x97A1C000 |
| 0x08 | `00 00` | `comp_len` | 0 |
| 0x0A | `00 00` | `flags` | 0x0000 |
| 0x0C | `00 00 00 00` | `checksum` | 0x00000000 |
| 0x10 | `A8 02 00 00` | `tag` | 0x000002A8 |
| 0x14 | `44 C0 01 45 C0 01 71 0A 03 75 0A 03 E0 12 04 E1 12 04 3F 6B 06 00 00 00` | `chunk` | 0x1C044、0x1C045、0x30A71、0x30A75、0x412E0、0x412E1、0x66B3F，其餘填 0 |
| 0x2C | `00 00 00 00` | `rsvd` | 0 |

步驟 6 的 completion：

| Offset | 記憶體裡的 byte，由低位址到高位址 | 欄位 | 值 |
|---|---|---|---|
| 0x00 | `00` | `status` | OK（0） |
| 0x01 | `00` | `flags` | 0x00 |
| 0x02 | `2D 07` | `length` | 1837 |
| 0x04 | `BD 14 AD F7` | `checksum` | 0xF7AD14BD |
| 0x08 | `A8 02 00 00` | `tag` | 0x000002A8 |
| 0x0C | `00 00 00 00` | `aux` | 0 |

步驟 8 FW 寫進 COT 的 entry：

| Offset | 記憶體裡的 byte，由低位址到高位址 | 欄位 | 值 |
|---|---|---|---|
| 0x00 | `01` | `flags` | 0x01 |
| 0x01 | `04` | `count` | 4 |
| 0x02 | `2D 07` | `comp_len` | 1837 |
| 0x04 | `BD 14 AD F7` | `checksum` | 0xF7AD14BD |
| 0x08 | `44 C0 01 45 C0 01 71 0A 03 75 0A 03 00 00 00 00 00 00 00 00 00 00 00 00` | `chunk` | 0x1C044、0x1C045、0x30A71、0x30A75，其餘填 0 |

## 3. Register

全部是 32 bit，little-endian。offset 相對於 LZ4 HW 的 register base。標成 config 的 register 只能在 `CTRL.ENABLE` 是 0 的時候寫，HW 在 ENABLE 是 1 的時候忽略對它們的寫入。

| Offset | Register | 存取 | Reset 值 | config | 說明 |
|---|---|---|---|---|---|
| 0x00 | `ID` | RO | 0x4C5A0001 |  | 固定值 0x4C5A0001。FW 在 probe 時確認 |
| 0x04 | `CAP` | RO | 0x0004AC98 |  | 硬體能力 |
| 0x08 | `CTRL` | RW | 0x00000000 |  | 控制 |
| 0x0C | `STATUS` | RO | 0x00000000 |  | 狀態 |
| 0x10 | `IRQ_STATUS` | RO/W1C | 0x00000000 |  | interrupt 來源 |
| 0x14 | `IRQ_ENABLE` | RW | 0x00000000 |  | interrupt 遮罩，bit 位置與 IRQ_STATUS 相同 |
| 0x18 | `ERR_CODE` | RO | 0x00000000 |  | HALTED 的原因，見 enum halt_code |
| 0x20 | `JOB_BASE` | RW | 0x00000000 | 是 | job ring 的 PA，對齊 64 B |
| 0x24 | `JOB_SIZE` | RW | 0x00000000 | 是 | job ring 的格數，必須是 2 的次方 |
| 0x28 | `JOB_TAIL` | RW | 0x00000000 |  | doorbell。FW 寫入下一個要填的格號，硬體從 JOB_HEAD 做到這一格之前 |
| 0x2C | `JOB_HEAD` | RO | 0x00000000 |  | 硬體下一個要取的格號 |
| 0x30 | `CPL_BASE` | RW | 0x00000000 | 是 | completion ring 的 PA，對齊 16 B |
| 0x34 | `CPL_SIZE` | RW | 0x00000000 | 是 | completion ring 的格數，必須是 2 的次方 |
| 0x38 | `CPL_TAIL` | RO | 0x00000000 |  | 硬體下一個要寫的格號 |
| 0x3C | `CPL_HEAD` | RW | 0x00000000 |  | FW 下一個要讀的格號。FW 讀完 completion 後寫入 |
| 0x40 | `POOL_BASE` | RW | 0x00000000 | 是 | chunk pool 的 PA |
| 0x44 | `POOL_CHUNKS` | RW | 0x00000000 | 是 | chunk pool 的 chunk 數。descriptor 裡的 chunk 號碼必須小於它 |
| 0x48 | `FRAME_BASE` | RW | 0x00000000 | 是 | page frame 區的 PA |
| 0x4C | `FRAME_COUNT` | RW | 0x00000000 | 是 | page frame 區的 frame 數。descriptor 裡的 frame_pa 必須落在這一區 |

各 register 的欄位：

**`CAP`，offset 0x04**

| Bit | 欄位 | 存取 | 說明 |
|---|---|---|---|
| 3:0 | `CHUNK_SLOTS` | RO | 一個 job 最多的 chunk 數，目前是 8 |
| 7:4 | `CHUNK_SHIFT` | RO | log2(chunk size)，目前是 9 |
| 11:8 | `PAGE_SHIFT` | RO | log2(page size)，目前是 12 |
| 15:12 | `RING_SHIFT_MAX` | RO | ring 最多 2^RING_SHIFT_MAX 格，目前是 10 |
| 19:16 | `ENGINES` | RO | LZ4 engine 的數量 N，也就是同時執行的 job 數上限，1 到 15。N 暫定為 4，負責人在 2026-11-13 指定先用這個值。reset 值與模擬器的預設都照 4 |

**`CTRL`，offset 0x08**

| Bit | 欄位 | 存取 | 說明 |
|---|---|---|---|
| 0 | `ENABLE` | RW | 1 表示硬體開始從 job ring 取 job。由 0 寫成 1 時硬體檢查 ring 設定 |
| 1 | `SOFT_RESET` | RW | 寫 1 觸發 soft reset，讀回永遠是 0 |

**`STATUS`，offset 0x0C**

| Bit | 欄位 | 存取 | 說明 |
|---|---|---|---|
| 0 | `BUSY` | RO | 1 表示至少有一個 engine 正在執行 job，或 reset 還沒收尾 |
| 1 | `HALTED` | RO | 1 表示硬體因為 ERR_CODE 所列的原因停下，只有 soft reset 能解除 |

**`IRQ_STATUS`，offset 0x10**

| Bit | 欄位 | 存取 | 說明 |
|---|---|---|---|
| 0 | `DONE` | RO | 等於 CPL_TAIL != CPL_HEAD。FW 把 CPL_HEAD 推到 CPL_TAIL 就自動變 0，不需要另外清 |
| 1 | `ERROR` | W1C | 硬體進入 HALTED 時設成 1，FW 寫 1 清除 |

**`IRQ_ENABLE`，offset 0x14**

| Bit | 欄位 | 存取 | 說明 |
|---|---|---|---|
| 0 | `DONE` | RW | 1 表示 DONE 會拉起 interrupt line |
| 1 | `ERROR` | RW | 1 表示 ERROR 會拉起 interrupt line |

常數：

| 常數 | 值 | 說明 |
|---|---|---|
| `PAGE_SIZE` | 4096 | 一個 page frame 的大小，單位 byte |
| `CHUNK_SIZE` | 512 | chunk pool 裡一個 chunk 的大小，單位 byte |
| `CHUNK_SLOTS` | 8 | 一個 job 或一個 COT entry 最多列出的 chunk 數 |
| `JOB_SLOT_SIZE` | 64 | job ring 一格的間距。descriptor 佔前 48 B，其餘 16 B 保留 |
| `CPL_SLOT_SIZE` | 16 | completion ring 一格的大小 |
| `COT_ENTRY_SIZE` | 32 | COT 一筆 entry 的大小 |
| `RING_ALIGN` | 64 | FW 設定兩個 ring 的 base 時對齊的單位。等於 job ring 一格的間距，也是這份規格假設的 CPU cache line 大小 |
| `ID_VALUE` | 0x4C5A0001 | ID register 的固定值 0x4C5A0001 |

## 4. Ring 的協定

兩個 ring 都是 FW 配置的一段連續記憶體，放在 FW 自己 pinned 的區域，不在 chunk pool 也不在 frame 區。格數是 2 的次方。每個 ring 有兩個格號，都從 0 開始，加到格數就回到 0。

| | job ring | completion ring |
|---|---|---|
| 一格的大小 | 64 B，descriptor 佔前 48 B | 16 B |
| 誰寫內容 | FW | HW |
| tail：下一個要寫的格號 | `JOB_TAIL`，FW 寫 | `CPL_TAIL`，HW 寫，FW 只能讀 |
| head：下一個要讀的格號 | `JOB_HEAD`，HW 寫，FW 只能讀 | `CPL_HEAD`，FW 寫 |
| 空 | head 等於 tail | head 等於 tail |
| 滿 | tail 加 1 等於 head，所以永遠留一格不用 | 同左 |

一格 job slot 的所有權隨時間換手：

| 時間 | 擁有者 | 規則 |
|---|---|---|
| FW 寫 descriptor，到寫 `JOB_TAIL` 之前 | FW | HW 不讀 |
| 寫 `JOB_TAIL` 之後，到 `JOB_HEAD` 越過這一格之前 | HW | FW 不寫，見 `FW-JOB-3` |
| `JOB_HEAD` 越過之後 | FW | HW 不再回頭讀，見 `HW-MEM-2`，FW 可以重用 |

FW 一次可以寫好幾格再寫一次 `JOB_TAIL`。

HW 有 N 個 engine，N 由 `CAP.ENGINES` 回報。HW 照 ring 的順序取 job，有 engine 空著才取下一格。還沒輪到的 job 留在 ring 裡，不在 HW 裡面排隊。同一時間最多 N 個 job 在執行。

每個 job 做完就寫出 completion，一次寫一筆。completion 的順序是做完的順序，不保證與取走的順序相同：一個後取走的 DECOMPRESS 可以比先取走的 COMPRESS 早回來。FW 用 tag 找 job，不依賴順序，見 `FW-CPL-2`。

HW 不檢查同時執行的 job 有沒有用到同一個 frame 或同一個 chunk。這由 FW 保證，見 `FW-JOB-6`。FW 違反時，那幾個 job 的結果未定義。HW 寫的範圍仍然不超出它們列出的 frame 與 chunk。

job ring 與 completion ring 沒有因為 N 個 engine 而變多，各只有一個。好幾個 thread 會同時送 job，寫 descriptor 與 `JOB_TAIL` 的那一段仍然要拿 `ring_lock`。`ring_lock` 保護的是 ring 的 tail，不是 engine，所以 engine 變多它不會消失。要不要改成每個 core 或每個 engine 各一個 ring，見未決事項 O13。

FW 同時在外的 job 數不超過 JOB_SIZE 減 1 與 CPL_SIZE 減 1 兩者較小的那個。這樣 completion ring 不會滿。HW 仍然要處理 completion ring 滿的情況：停下來等，不覆寫，見 `HW-CPL-3`。

## 5. 資料結構

所有多 byte 的欄位都是 little-endian。chunk 號碼是 24 bit，低 byte 在前，乘 512 加 `POOL_BASE` 就是 chunk 的 PA。

### 5.1 job descriptor，48 B

| Offset | 大小 B | 欄位 | 說明 |
|---|---|---|---|
| 0x00 | 1 | `opcode` | 見 enum opcode |
| 0x01 | 1 | `count` | chunk[] 裡有效的格數，1 到 8 |
| 0x02 | 2 | `limit` | COMPRESS：stream 最多幾個 byte，超過就回 INCOMPRESSIBLE。DECOMPRESS：填 4096 |
| 0x04 | 4 | `frame_pa` | page frame 的 PA。COMPRESS 讀它，DECOMPRESS 寫它 |
| 0x08 | 2 | `comp_len` | DECOMPRESS：stream 的長度。COMPRESS：填 0 |
| 0x0A | 2 | `flags` | bit2 RAW：DECOMPRESS 的 stream 是沒壓縮的 4096 B |
| 0x0C | 4 | `checksum` | DECOMPRESS：stream 的 CRC-32。COMPRESS：填 0 |
| 0x10 | 4 | `tag` | FW 自訂，硬體原樣抄進 completion |
| 0x14 | 8 × 3 | `chunk` | chunk 號碼，每個 24 bit。COMPRESS 是可以寫的 chunk，DECOMPRESS 是 stream 所在的 chunk，依序 |
| 0x2C | 4 | `rsvd` | 保留，FW 寫 0，硬體忽略 |

### 5.2 completion，16 B

| Offset | 大小 B | 欄位 | 說明 |
|---|---|---|---|
| 0x00 | 1 | `status` | 見 enum status |
| 0x01 | 1 | `flags` | bit2 RAW：COMPRESS 存的是沒壓縮的 4096 B |
| 0x02 | 2 | `length` | COMPRESS OK：stream 的長度。DECOMPRESS OK：4096。其他狀態：0 |
| 0x04 | 4 | `checksum` | stream 的 CRC-32 |
| 0x08 | 4 | `tag` | descriptor 的 tag |
| 0x0C | 4 | `aux` | BAD_DESC 時是 enum bad_desc 的代碼，其餘是 0 |

### 5.3 COT entry，32 B

HW 不讀也不寫 COT。這裡列出來是因為 DECOMPRESS 的 descriptor 抄自它，COMPRESS 的結果寫進它，兩邊的欄位必須對得上。

| Offset | 大小 B | 欄位 | 說明 |
|---|---|---|---|
| 0x00 | 1 | `flags` | bit0 VALID，bit1 RO，bit2 RAW |
| 0x01 | 1 | `count` | 用到的 chunk 數 |
| 0x02 | 2 | `comp_len` | stream 的長度 |
| 0x04 | 4 | `checksum` | stream 的 CRC-32 |
| 0x08 | 8 × 3 | `chunk` | chunk 號碼，每個 24 bit，依序 |

## 6. 列舉值

opcode：

| 值 | 名稱 | 說明 |
|---|---|---|
| 1 | `COMPRESS` | 讀 frame，壓成 LZ4 block，寫進 descriptor 列出的 chunk |
| 2 | `DECOMPRESS` | 讀 descriptor 列出的 chunk，驗 CRC-32，解回 frame |

completion 的 status：

| 值 | 名稱 | 說明 |
|---|---|---|
| 0 | `OK` | 完成 |
| 1 | `INCOMPRESSIBLE` | COMPRESS 的 stream 超過 limit。chunk 內容不定，frame 沒被動過 |
| 3 | `BAD_STREAM` | DECOMPRESS 的 CRC-32 不符或 stream 格式錯。frame 內容不定 |
| 5 | `BUS_ERROR` | 讀寫 frame 或 chunk 時 bus 回報錯誤 |
| 6 | `BAD_DESC` | descriptor 沒通過檢查，硬體沒有碰任何 frame 或 chunk。原因在 aux |

status 是 BAD_DESC 時 `aux` 的值：

| 值 | 名稱 | 說明 |
|---|---|---|
| 1 | `OPCODE` | opcode 不是 COMPRESS 或 DECOMPRESS |
| 2 | `COUNT` | count 是 0 或大於 8 |
| 3 | `CHUNK_RANGE` | 有 chunk 號碼不小於 POOL_CHUNKS |
| 4 | `FRAME_RANGE` | frame_pa 不在 frame 區，或沒對齊 4096 |
| 5 | `LENGTH` | limit 或 comp_len 是 0、超過 4096 或超過 count 乘 512；RAW 的 comp_len 不是 4096 |

`ERR_CODE` 的值：

| 值 | 名稱 | 說明 |
|---|---|---|
| 0 | `NONE` | 沒有錯誤 |
| 1 | `BAD_RING_CFG` | ENABLE 時 ring 大小不是 2 的次方、超過上限，或 base 沒對齊 |
| 2 | `RING_BUS_ERROR` | 讀 job ring 或寫 completion ring 時 bus 回報錯誤 |
| 3 | `BAD_INDEX` | FW 寫入的 JOB_TAIL 或 CPL_HEAD 不小於 ring 的格數 |

flags 的 bit：

| 值 | 名稱 | 說明 |
|---|---|---|
| 1 | `VALID` | COT entry 有效 |
| 2 | `RO` | COT entry 屬於 RO page |
| 4 | `RAW` | stream 是沒壓縮的 4096 B |

## 7. 規則

每條規則有編號。模擬器的 checker 與測試都用同一個編號，C header 裡也有對應的字串，FW 的 assert 與 log 可以直接引用。

### 7.1 FW 要守的

| 編號 | 規則 | 怎麼驗 |
|---|---|---|
| `FW-CFG-1` | 標成 config 的 register 只能在 CTRL.ENABLE 是 0 的時候寫。 | 模擬器執行中檢查 |
| `FW-CFG-2` | 把 ENABLE 寫成 1 之前，JOB_SIZE 與 CPL_SIZE 是 2 的次方、介於 2 與 2^RING_SHIFT_MAX 之間，JOB_BASE 與 CPL_BASE 都對齊 RING_ALIGN，也就是 64 B，兩個 ring 都不落在 chunk pool 或 frame 區裡。HW 對 CPL_BASE 只檢查 16 B；64 B 是 FW 這一邊為了 FW-CACHE-5 多守的。 | 模擬器執行中檢查 |
| `FW-JOB-1` | 寫 JOB_TAIL 之前，新納入的每一格 descriptor 的 48 B 都已經寫完。 | 模擬器執行中檢查 |
| `FW-JOB-2` | JOB_TAIL 只往前走，新值小於 JOB_SIZE，而且 ring 永遠留一格空：尚未被硬體取走的 job 最多 JOB_SIZE 減 1 個。 | 模擬器執行中檢查 |
| `FW-JOB-3` | 一格 descriptor 從 doorbell 到 JOB_HEAD 越過它之前，FW 不寫那一格。 | 模擬器執行中檢查 |
| `FW-JOB-4` | 已 doorbell、completion 還沒被 FW 讀走的 job 最多 CPL_SIZE 減 1 個，所以 completion ring 不會滿。 | 模擬器執行中檢查 |
| `FW-JOB-5` | 已 doorbell、completion 還沒被 FW 讀走的 job，tag 互不相同。 | 模擬器執行中檢查 |
| `FW-JOB-6` | 一個 frame 或一個 chunk 同一時間只出現在一個未完成的 job 裡。未完成指 doorbell 之後、硬體還沒貼出 completion。硬體會同時執行好幾個 job，而且不檢查這一條。 | 模擬器執行中檢查 |
| `FW-CPL-1` | CPL_HEAD 只往前走，而且不超過 CPL_TAIL。 | 模擬器執行中檢查 |
| `FW-CPL-2` | FW 用 tag 找出 completion 對應的 job，不假設順序。 | 人工 review |
| `FW-MM-1` | job 的 doorbell 之前，沒有任何 valid 的 PTE 指到那個 frame。COMPRESS 的來源 frame 已經寫成 invalid 而且 TLB 清掉，DECOMPRESS 的目的 frame 還沒對應給任何 page。 | 模擬器執行中檢查 |
| `FW-MM-2` | COMPRESS 列出的 chunk 都是空的：沒有任何有效的 COT entry 指到它。 | 模擬器執行中檢查 |
| `FW-MM-3` | RW page 的 COT entry 只在 COMPRESS 回 OK 之後寫。comp_len、checksum、RAW 來自 completion，chunk 是 descriptor 的前 ceil(length/512) 個，順序不變。 | 模擬器執行中檢查 |
| `FW-MM-4` | DECOMPRESS 的 count、comp_len、checksum、RAW 與 chunk 原樣抄自那個 page 有效的 COT entry。 | 模擬器執行中檢查 |
| `FW-MM-5` | PTE 寫成 valid 之前：那個 page 沒有未完成的 job，那個 frame 不在任何未完成的 job 裡，也沒有對應到別的 page。 | 模擬器執行中檢查 |
| `FW-MM-6` | page 上一個 job 是 DECOMPRESS 時，只有 status 是 OK 才能把 PTE 寫成 valid。RW page 還要先把 COT entry 清成 0，PTE 最後才寫。 | 模擬器執行中檢查 |
| `FW-MM-7` | RO page 的 COT entry 在執行期間不寫。 | 模擬器執行中檢查 |
| `FW-CACHE-1` | COMPRESS 的 doorbell 之前，來源 frame 在所有 core 的 cache 裡沒有還沒寫回 DRAM 的 line。做法是 PTE 寫成 invalid、TLB 清掉之後做一次 cache clean。 | 人工 review |
| `FW-CACHE-2` | DECOMPRESS 的 completion 之後、PTE 寫成 valid 之前，目的 frame 在所有 core 的 data cache 與 instruction cache 裡的 line 都已經作廢，不論 status 是什麼。DECOMPRESS 的 doorbell 之前，目的 frame 在任何 cache 裡沒有還沒寫回的 line。 | 人工 review |
| `FW-CACHE-3` | 寫 JOB_TAIL 之前，descriptor 的 48 B 已經在 DRAM 裡，不只在 CPU cache 裡。FW 讀 completion 時不經過舊的 cache line。兩個 ring 對應成 non-cacheable，或每個 job 各做一次 clean 與 invalidate。 | 人工 review |
| `FW-CACHE-4` | 把 ENABLE 寫成 1 之前，整個 frame 區與整個 chunk pool 在所有 core 的 cache 裡沒有任何 line：boot loader 放進 chunk pool 的 RO chunk 已經在 DRAM 裡，開機過程留在 frame 區的 line 也已經寫回並作廢。ENABLE 之後 FW 不寫 chunk pool。FW 自己解 stream 而要讀 chunk 時，不經過 HW 寫入之前留下的 cache line。 | 人工 review |
| `FW-CACHE-5` | HW 會寫的每一塊記憶體，不與 CPU 會寫的其他資料共用同一條 cache line。frame 與 chunk 的大小都是 cache line 的整數倍，本來就成立。completion ring 從 cache line 的開頭開始，尾端補滿整條 line，那幾條 line 不放別的資料；或者把 ring 對應成 non-cacheable。 | 人工 review |
| `FW-RST-1` | job 逾時後先讀 completion ring。確定沒有 completion 才 soft reset，等 STATUS.BUSY 變 0，把所有未完成的 job 重新送一次。 | 注入測試 |

### 7.2 HW 要守的

| 編號 | 規則 | 怎麼驗 |
|---|---|---|
| `HW-MEM-1` | 硬體只讀寫四種位置：JOB_HEAD 那一格 descriptor、執行中的 job 的 frame、執行中的 job 列出的 chunk、CPL_TAIL 那一格 completion。執行中的 job 最多 CAP.ENGINES 個。COMPRESS 不寫 frame，DECOMPRESS 不寫 chunk。 | 模擬器執行中檢查 |
| `HW-MEM-2` | 硬體照 ring 的順序取 job，有 engine 空著才取。先把 descriptor 的 48 B 讀完才推進 JOB_HEAD，每個 job 只讀一次，之後不再回頭讀。 | 模擬器執行中檢查 |
| `HW-CPL-1` | 每個 job 恰好一個 completion，tag 原樣抄回。completion 照 job 做完的順序寫出，不保證與 job 被取走的順序相同。 | 模擬器執行中檢查 |
| `HW-CPL-2` | 一個 job 的資料全部寫完、它的 completion 的 16 B 也寫完之後，才推進 CPL_TAIL。completion 一次寫一筆，CPL_TAIL 一次加 1。 | 模擬器執行中檢查 |
| `HW-CPL-3` | completion ring 滿的時候，做完的 job 等著，不覆寫也不丟棄還沒被讀走的 completion。 | 模擬器執行中檢查 |
| `HW-IRQ-1` | interrupt line 等於 (IRQ_STATUS & IRQ_ENABLE) != 0，其中 DONE 等於 CPL_TAIL != CPL_HEAD。 | 模擬器執行中檢查 |
| `HW-DATA-1` | COMPRESS 回 OK 時：length 不超過 limit，checksum 是 stream 的 CRC-32，stream 解開後與 frame 的 4096 B 相同。 | 模擬器執行中檢查 |
| `HW-DATA-2` | DECOMPRESS 回 OK 時 frame 等於 stream 解開的 4096 B。回 BAD_STREAM 時 stream 確實有錯。 | 模擬器執行中檢查 |
| `HW-STATE-1` | 除了 register，硬體不保留跨 job 的狀態。一個 job 的結果只由它的 descriptor 與它列出的 frame、chunk 的內容決定，與同時在其他 engine 執行的 job 無關，也與它被分到哪一個 engine 無關。job 做到一半被 reset，重送同一個 descriptor 會得到相同結果。 | 人工 review |
| `HW-RST-1` | soft reset：進行中的 bus burst 做完就停，所有 engine 手上的 job 都放棄，不寫 completion。JOB_HEAD、JOB_TAIL、CPL_TAIL、CPL_HEAD、ERR_CODE、IRQ_STATUS 與 CTRL.ENABLE 清成 0，config register 與 IRQ_ENABLE 保留，然後 STATUS.BUSY 變 0。 | 注入測試 |

模擬器的 HW model 在 2026-11-13 擴充成 N 個 engine，預設 4。checker 照上面的文字檢查，有三點要知道：

| 規則 | checker 怎麼檢查 | 限制 |
|---|---|---|
| `HW-CPL-1` | 每個被取走的 job 恰好一個 completion，tag 相同。不檢查順序 | 無 |
| `HW-MEM-2` | descriptor 照 ring 的順序讀，而且讀的當下 HW 手上的 job 少於 `CAP.ENGINES` 個 | 無 |
| `HW-MEM-1` | 每個 burst 落在 HW 手上某一個 job 的 frame 或 chunk 範圍內 | burst 上沒有 engine 的編號，master port 只有一個 ID。一個 engine 寫到另一個執行中 job 的範圍，這一條抓不到，只有資料比對可能抓到。要補上就要讓 burst 帶 engine 編號，見 O14 與 O15 |

`FW-JOB-3` 在 N 大於 1 時很難被違反到：HW 通常在 FW 有機會重寫之前就把那一格取走了。這條規則的植入測試只在一個 engine 的設定下跑。

### 7.3 整個系統在靜止時要成立的

| 編號 | 規則 | 怎麼驗 |
|---|---|---|
| `AUDIT-1` | 任何靜止的時刻，bitmap 標成已用的 chunk 等於所有有效 COT entry 列出的 chunk 的聯集，沒有 chunk 被兩個 entry 共用。 | 模擬結束時 audit |
| `AUDIT-2` | 任何靜止的時刻，每個 frame 不是空的就是恰好屬於一個 present 的 page。 | 模擬結束時 audit |
| `AUDIT-3` | 每個 page 的內容，不論在 frame 裡或壓縮在 chunk 裡，都等於 user SW 最後寫入的內容。 | 模擬結束時 audit |
| `AUDIT-4` | 系統靜止時沒有未完成的 job，兩個 ring 都是空的，interrupt line 是低的。 | 模擬結束時 audit |

還有幾條規則這個模擬器沒有涵蓋，寫在 kernel 的控制程序 `control-procedures-v0.md` 裡，由 `sim/hostsim` 檢查：

| 規則 | 原因 | 控制程序的章節 |
|---|---|---|
| 會被 ISR、kernel 自己的 mapping、DMA 或其他 bus master 存取的 page，存取期間必須 pin 住 | ISR 不能等 page fault。其餘的不經過 CPU 的 MMU，不會產生 page fault | 5.1、5.2 |
| HRT client 的記憶體不在 `FRAME_BASE` 與 `POOL_BASE` 圈出的兩個區域裡。HRT thread 也不可以間接碰到壓縮層的 page | HW 只會碰這兩個區域與兩個 ring，HRT 的記憶體因此不受影響。HRT thread 不能等 page fault | 5.3 |
| 第二個 thread 碰到狀態是 compressing 或 decompressing 的 page 時，等同一個 job，不另外送 job | 否則同一個 frame 會出現在兩個 job 裡，違反 `FW-JOB-6` | 3.4、7.4 |
| 好幾個 thread 會同時送 job。每個 thread 用自己那個 job 的 tag 認 completion | 見 `FW-CPL-2` 與 `FW-JOB-5` | 3.4、7.4 |

### 7.4 CPU cache

HW 經由自己的 master port 直接讀寫 DRAM。這份規格假設這個 port 與 CPU cache 不 coherent，所以 FW 要守 `FW-CACHE-1` 到 `FW-CACHE-5`。這五條這個模擬器不檢查，只有 `FW-CACHE-5` 裡 `CPL_BASE` 對齊 64 B 這一點由 `FW-CFG-2` 的 checker 檢查。`FW-CACHE-1`、`FW-CACHE-2` 與 `FW-CACHE-4` 由 `sim/hostsim` 的 cache 模型檢查，理由與時機在控制程序的第 6 節。

不守的後果是資料悄悄錯掉，而且 CRC-32 不會發現：CRC 是 HW 對它自己讀到或寫出的 byte 算的。

| 記憶體 | CPU 經由 cache 碰它嗎 | 規則 |
|---|---|---|
| page frame | 會，user SW 一直在讀寫 | `FW-CACHE-1`、`FW-CACHE-2` |
| job ring 與 completion ring | 會，FW 寫 descriptor、讀 completion | `FW-CACHE-3`、`FW-CACHE-5` |
| chunk pool | 開機時 boot loader 寫 RO chunk。之後 FW 只在自己解 stream 時讀 | `FW-CACHE-4` |
| 開機時的 frame 區 | 會，boot loader 與開機程式可能用過 | `FW-CACHE-4` |
| COT | 會，但 HW 不讀它 | 不需要 |

`FW-CACHE-5` 管的是邊界。cache 的 clean 與 invalidate 以整條 line 為單位。HW 寫的資料與 CPU 寫的資料同在一條 line 時，invalidate 會丟掉 CPU 寫的那一半，clean 會把舊的那一半蓋回 HW 剛寫的內容。completion 一筆 16 B，一條 line 放得下 4 筆，所以 ring 的頭尾要對齊整條 line。

整合時如果把 master port 接成與 CPU cache coherent，這五條自動成立，FW 的 cache 操作可以拿掉。見未決事項 O11。

## 8. Interrupt 與 polling

interrupt line 是 level，等於 `(IRQ_STATUS & IRQ_ENABLE) != 0`。

`IRQ_STATUS.DONE` 不是事件 bit，是狀態：completion ring 不空的時候是 1。FW 不需要清它，把 `CPL_HEAD` 推到 `CPL_TAIL` 它就變 0。這樣設計是為了避開一個常見的 race：FW 讀完 completion 之後、清 interrupt 之前，HW 又貼了一個 completion，結果新的 interrupt 被清掉。用 level 的話，只要 ring 裡還有沒讀的 completion，line 就維持高，FW 不會漏。

FW 有兩種等 completion 的方式，介面都支援：

| 方式 | `IRQ_ENABLE.DONE` | FW 怎麼做 | 代價 |
|---|---|---|---|
| interrupt | 1 | 送出 job 的 thread 睡著讓出 core。handler 讀 completion，叫醒 thread | interrupt latency、handler 與 scheduler 叫醒的時間 |
| polling | 0 | 送出 job 的 thread 每隔一小段時間讀一次 `CPL_TAIL`，不讓出 core | 等待期間佔著 core |

哪一種比較好由模擬結果決定，見 `sim-results-v0.md`。

N 個 engine 時，兩次進 handler 之間可能有好幾個 engine 做完。DONE 是 level，FW 每次把 head 到 tail 之間的 completion 全部讀完，所以這一段不用改。completion ring 只有一個，interrupt line 也只有一條。它送到哪一個 core 由整合決定。

## 9. 錯誤處理與 reset

錯誤分三層，影響範圍一層比一層大。

| 層 | 例子 | HW 怎麼回報 | FW 怎麼處理 |
|---|---|---|---|
| 一個 job 的資料 | stream 壓不到 limit 以內；CRC-32 不符 | completion 的 status 是 INCOMPRESSIBLE 或 BAD_STREAM | INCOMPRESSIBLE：page 留在 frame。BAD_STREAM：FW 用自己的 decoder 再解一次，解得出來就照常使用，也解不出來才把這個 page 當成損毀，只影響擁有它的 user SW |
| 一個 job 的資料存取 | 讀寫 frame 或 chunk 時 bus 回報錯誤 | status 是 BUS_ERROR，其他欄位是 0。HW 不 halt，目的地的內容未定義 | DECOMPRESS：FW 用自己的 decoder 解同一份 stream 寫進 frame。COMPRESS：page 留在 frame，保留的 chunk 全部還回去，不把 page 記成壓不動 |
| 一個 job 的 descriptor | chunk 號碼超出 pool；frame_pa 不在 frame 區 | status 是 BAD_DESC，`aux` 是原因。HW 沒有碰任何 frame 或 chunk | 這是 FW 的 bug。記錄下來，不重送 |
| ring 本身 | ring 設定不合法；`JOB_TAIL` 超出格數；讀 ring 時 bus error | `STATUS.HALTED` 變 1，`ERR_CODE` 是原因，`IRQ_STATUS.ERROR` 變 1 | soft reset，重新設定，重送 |

N 個 engine 時，同一時間有好幾個 job 在執行。一個錯誤影響到哪些 job：

| 錯誤 | 出錯的那個 job | 同時在其他 engine 執行的 job |
|---|---|---|
| INCOMPRESSIBLE、BAD_STREAM、BUS_ERROR、BAD_DESC | 寫出 completion | 不受影響，照常做完 |
| halt，原因是 BAD_INDEX | 沒有這樣的 job，錯在 FW 寫的格號 | HW 不再取新的 job。已經在執行的 job 做完並寫出 completion |
| halt，原因是 RING_BUS_ERROR | 取不到 descriptor，或寫不出 completion | HW 不再碰兩個 ring。已經在執行的 job 在目前的 bus burst 做完後停下，沒有 completion。FW 在 reset 之後重送 |
| soft reset | 不適用 | 所有執行中的 job 都放棄，沒有 completion。FW 重送 |

BAD_RING_CFG 只會在 ENABLE 由 0 寫成 1 的時候發生，那時沒有 job 在執行。

HW 完全沒有回應時，FW 靠 timeout 發現：

| 步驟 | 誰做 | 做什麼 |
|---|---|---|
| 1 | FW | job 送出後超過 timeout 沒有 completion |
| 2 | FW | 先讀一次 completion ring。有 completion 就是 interrupt 漏了，照常處理，不 reset |
| 3 | FW | 確定沒有：對 `CTRL.SOFT_RESET` 寫 1 |
| 4 | HW | 進行中的 bus burst 做完就停，所有 engine 手上的 job 都放棄。四個 ring 格號、`ERR_CODE`、`IRQ_STATUS`、`CTRL.ENABLE` 清成 0。config register 與 `IRQ_ENABLE` 保留。收尾完成後 `STATUS.BUSY` 變 0 |
| 5 | FW | 等 `STATUS.BUSY` 變 0，把自己的兩個格號歸零，對 `CTRL.ENABLE` 寫 1 |
| 6 | FW | 把所有還沒拿到 completion 的 job 從第 0 格起重新寫進 job ring，tag 不變，寫 `JOB_TAIL` |

Reset 與重送都沒有用時，driver 回報這個 job 沒有 completion，不再等。FW 從這時起不再使用 HW，到下次開機為止。HW 連續三次答錯也一樣：BUS_ERROR、FW 自己解得開的 BAD_STREAM，都算答錯。停用之後 FW 怎麼繼續，見控制程序 3.6。

N 個 engine 時「連續三次」這個判準變弱。只有一個 engine 壞掉的話，它的錯誤答案會夾在其他 engine 的正確答案中間，而每一個正確答案都把計數歸零，連續三次可能永遠湊不滿。completion 裡也沒有 engine 的編號，FW 分不出是哪一個 engine 答的。資料不會因此錯掉，因為每一次答錯 FW 都各自處理。受影響的是多久之後才停用 HW。見未決事項 O15。

重送是安全的，因為 job 是 idempotent：COMPRESS 的來源 frame 沒有被改過，DECOMPRESS 的來源 chunk 沒有被改過，目的地寫到一半的內容會被整個重寫，見 `HW-STATE-1`。這也是 `FW-MM-1` 與 `FW-MM-5` 存在的原因：job 沒有完成之前，沒有任何 PTE 指到那個 frame。

## 10. 時序假設與暫定 budget

介面本身不規定時間。下面這些數字是模擬器用來估效能的參數，全部是假設，等拿到實際平台的數字再換。來源欄寫 lz4sim 的是沿用前一版模擬器的值，寫設計選擇的是 FW 可以自己調的 policy。

下面 budget 的實測值是 4 個 engine 的 model 跑出來的。`engine_util` 的定義是每個 engine 手上有 job 的時間比例，取所有 engine 的平均。

| 參數 | 值 | 來源 | 意思 |
|---|---|---|---|
| `cores` | 4 | 假設 | 跑 user SW 的 core 數 |
| `think_ns` | 20000 | lz4sim 的 access_gap_ns | 一個 user SW 兩次 page access 之間自己做事的時間，ns |
| `wait_mode` | irq | 設計選擇 | FW 等 completion 的方式，irq 或 poll |
| `job_entries` | 16 | 假設 | job ring 的格數 |
| `cpl_entries` | 16 | 假設 | completion ring 的格數 |
| `engines` | 4 | 負責人暫定，2026-11-13 | LZ4 engine 的數量 N，也就是 `CAP.ENGINES`。HW 同時執行的 job 數上限 |
| `clock_hz` | 1000000000 | lz4sim | LZ4 HW 的 clock，Hz |
| `comp_bytes_per_cycle` | 1 | lz4sim | COMPRESS 每個 clock 吃進幾個 byte |
| `decomp_bytes_per_cycle` | 4 | lz4sim | DECOMPRESS 每個 clock 吐出幾個 byte |
| `hw_overhead_ns` | 50 | 假設 | 每個 job 解讀 descriptor 與收尾的時間，ns |
| `burst_bytes` | 256 | 假設 | HW 一個 bus burst 的大小，B |
| `bus_bytes_per_ns` | 8 | 假設 | HW 在 DRAM port 上的 throughput，B 每 ns |
| `bus_setup_ns` | 20 | 假設 | 每個 burst 的固定開銷，ns |
| `bus_bg_share` | 0.2 | 假設 | DRAM port 被 CPU 與 HRT 流量佔住的時間比例 |
| `bus_bg_burst_ns` | 100 | 假設 | 擋在前面的 burst 最長多久，ns |
| `reset_ns` | 200 | 假設 | soft reset 收尾的時間，ns |
| `mmio_ns` | 50 | 假設 | 讀或寫一個 register，ns |
| `fault_entry_ns` | 600 | 假設 | 進入 page fault 到找到 page，ns |
| `fault_exit_ns` | 400 | 假設 | 從 page fault 返回，ns |
| `frame_alloc_ns` | 100 | 假設 | 拿一個 free frame，ns |
| `cot_read_ns` | 100 | 假設 | 讀一筆 COT entry，ns |
| `cot_write_ns` | 150 | 假設 | 寫一筆 COT entry，ns |
| `desc_build_ns` | 150 | 假設 | 填好一個 descriptor，ns |
| `desc_write_ns` | 100 | 假設 | 把 48 B 的 descriptor 寫進 job ring，ns |
| `cpl_read_ns` | 80 | 假設 | 從 completion ring 讀 16 B，ns |
| `bitmap_reserve_ns` | 250 | 假設 | 在 bitmap 找到並預留 7 個 chunk，ns |
| `bitmap_release_ns` | 100 | 假設 | 在 bitmap 釋放 chunk，ns |
| `pte_write_ns` | 100 | 假設 | 寫一個 PTE，ns |
| `tlb_inval_ns` | 500 | 假設 | 在每個 core 清掉一筆 TLB entry，ns |
| `victim_pick_ns` | 300 | 假設 | 挑一個 victim page，ns |
| `zero_fill_ns` | 400 | 假設 | 把一個 frame 補零，ns |
| `irq_latency_ns` | 1000 | 假設 | interrupt line 拉高到 handler 第一個指令，ns |
| `irq_handler_ns` | 150 | 假設 | handler 每次進入的固定開銷，ns |
| `wakeup_ns` | 2000 | 假設 | handler 叫醒 thread 到它真的開始跑，ns |
| `poll_interval_ns` | 200 | 假設 | polling 時兩次讀 CPL_TAIL 的間隔，ns |
| `job_timeout_ns` | 1000000 | 假設 | FW 等 completion 的 timeout，ns |
| `reclaim_inflight` | 2 | 設計選擇。負責人 2026-11-13 同意從 1 改掉，2 是照模擬選的 | reclaimer 同時在外的 COMPRESS job 數 |

暫定的 budget。目標都是先放的佔位值，還沒有人確認過，見未決事項 O1。

| Budget | 暫定目標 |
|---|---|
| `fault_p50_ns` | 10.00 µs |
| `fault_p99_ns` | 30.00 µs |
| `fault_max_ns` | 100.00 µs |
| `kernel_cpu_share` | 5.0% |
| `engine_util` | 50.0% |
| `job_ring_peak` | 50.0% |
| `frame_waits` | 0 |
| `lost_pages` | 0 |

## 11. 決策紀錄

這些是定義介面時做的選擇，還沒有經過 review，每一條都可以改。

| 編號 | 決定 | 理由 | 放棄的做法 |
|---|---|---|---|
| D1 | `IRQ_STATUS.DONE` 是 level，等於 completion ring 不空 | 沒有清 interrupt 的 race，FW 少一個步驟 | W1C 的事件 bit |
| D2 | job ring 一格 64 B，descriptor 用 48 B | 格號換算位址只要 shift；一格剛好一條 cache line；留 16 B 給以後的欄位 | 一格 48 B |
| D3 | HW 每個 job 只讀 descriptor 一次，讀完就推進 `JOB_HEAD` | slot 很快還給 FW；HW 讀到的內容不會中途改變 | job 做完才推進 `JOB_HEAD` |
| D4 | ring 用 head 與 tail 兩個格號，永遠留一格空 | 空與滿不必另外記；與 NVMe 的 queue 相同，容易理解 | 另外放一個計數 register |
| D5 | N 個 engine，completion 照做完的順序，tag 原樣抄回，FW 用 tag 找 job。2026-11-13 照平台前提 P4 改寫，原本是一個 engine、completion 照 job 的順序 | 短的 DECOMPRESS 不必等前面長的 COMPRESS。FW 的協定本來就用 tag，不用改 | HW 把 completion 排回取走的順序；FW 依賴順序 |
| D6 | FW 把在外的 job 數限制在兩個 ring 較小的格數減 1 | completion ring 不會滿，HW 不必常常停下 | 只靠 HW 停下等 |
| D7 | soft reset 保留 config register 與 `IRQ_ENABLE`，清掉格號 | FW 恢復只要 enable 再重送 | reset 後全部重新設定 |
| D8 | HW 用 `POOL_*` 與 `FRAME_*` 四個 register 檢查每個 descriptor | FW 有 bug 時 HW 也不會寫到這兩個區域以外，HRT 的記憶體不受影響 | 完全信任 FW |
| D9 | CRC-32 由 HW 在壓縮時算、解壓縮時驗，FW 只負責存進 COT | 資料損毀在解壓縮當下就被發現，FW 不必自己算 | FW 算 CRC |
| D10 | COMPRESS 一次給 7 個 chunk，用不完的由 FW 釋放 | HW 不需要 allocator；bitmap 只有 FW 在改 | HW 自己拿 chunk |
| D11 | page fault 的 DECOMPRESS 與 reclaimer 的 COMPRESS 共用一個 job ring | 最簡單。一個 engine 時，一個 COMPRESS 擋在前面，fault 最長多等一個 COMPRESS。4 個 engine 時要全部的 engine 都有 job 才會等，模擬裡基準負載下 fault 在 ring 裡等的時間是 0，負載 10 倍時最長的一次是 2.16 µs，見 `sim-results-v0.md` 的 1.3 與 1.7 | 兩個 ring，fault 優先 |
| D12 | descriptor 裡的 frame_pa 是 32 bit | 目前的 address map 在 4 GB 以內 | 64 bit 或 frame 號碼 |

## 12. 未決事項

| 編號 | 事項 | 需要誰決定 |
|---|---|---|
| O1 | budget 的實際目標：fault latency、kernel CPU 佔比、engine 忙碌比例 | 專案負責人 |
| O2 | 時序參數的實際數字：interrupt latency、thread 叫醒時間、TLB invalidate、DRAM port 的 throughput、LZ4 core 每個 clock 處理幾個 byte | 專案負責人，或平台的量測資料 |
| O3 | core 的數量，用哪個 kernel 或 RTOS | 專案負責人 |
| O4 | 是否需要第二個 ring 或優先權，讓 page fault 的 job 插到 COMPRESS 前面 | 模擬的結果：4 個 engine 時，fault 在 ring 裡等最長的一次是 2.16 µs，一個 engine 時是 15.82 µs。第二個 ring 或優先權最多拿回這 2.16 µs，而最慢的那幾次 fault 等的是別的東西。`sim-results-v0.md` 的 1.3、F15、F16。建議 4 個 engine 時不做。N 改小的話要重看 |
| O5 | 等 completion 的方式：interrupt、polling，或先 polling 一小段再睡 | 看模擬結果 |
| O6 | user SW 碰到正在 COMPRESS 的 page 時，要等它壓完再解，還是取消那個 job 直接把 PTE 寫回去 | 看模擬結果。取消需要介面多一個動作 |
| O7 | N 的值。`CAP.ENGINES` 是 4 bit，介面允許 1 到 15。負責人在 2026-11-13 指定先用 4，是暫定值。模擬的結果：2 個已經拿掉大部分排隊，4 個管的是重負載下最長的幾次，8 個和 4 個幾乎一樣，`sim-results-v0.md` 的 F14 | 專案負責人與 HW 設計定案。還要看面積與 DRAM port 的接法 |
| O8 | frame 或 chunk 的 bus error：模擬器還沒有做 | 之後補 |
| O9 | 省電：HW 閒置時的 clock gating，suspend 與 resume 之後 config register 是否還在 | HW 設計規格 |
| O10 | 先前討論中暫緩的項目：cold page 的 prefetch、有 phase 變化的 workload、kernel 的 page 狀態放在獨立陣列還是 invalid PTE 的空 bit | 動畫已經做完，可以排進來 |
| O11 | HW 的 master port 與 CPU cache 是否 coherent。目前照不 coherent 寫，FW 每個 job 做 cache clean 或 invalidate。兩個 ring 是否對應成 non-cacheable | SoC 整合。控制程序的 D8 |
| O12 | job ring 的格數要容得下同時在外的 job：每個正在 fault 的 thread 一個，加上 reclaimer 一個。格子不夠時送 job 的 thread 要等 | 看 thread 數。控制程序的第 11 節 |
| O13 | job ring 維持一個，還是每個 core 或每個 engine 各一個。一個 ring 時 `ring_lock` 留著，握著它的時間只有寫 48 B 與一次 register 寫入。多個 ring 可以拿掉 `ring_lock`，代價是 register 變多，HW 要在 ring 之間仲裁 | 專案負責人。目前照一個 ring 寫 |
| O14 | N 個 engine 怎麼接到 DRAM。目前照共用一個 master port 寫：整顆 HW 同一時間一個 read burst、一個 write burst。模擬器照這個接法做了簡化的 arbiter。4 個 engine、基準負載下，在 port 等其他 job 的時間攤到每個 burst 是 0.8 ns，一個 DECOMPRESS 的 HW 時間最長從 1.65 µs 變成 2.90 µs。負載 10 倍時是 1.73 µs 對 4.05 µs。`sim-results-v0.md` 的 F15。這是 event 層級的近似，不是 cycle 層級 | HW 設計與 SoC 整合。HW 設計規格 12.3 |
| O15 | 停用 HW 的判準。「連續三次答錯」在 N 個 engine 時可能抓不到只壞一個 engine 的情況，見第 9 節。選項：改成一段時間內的次數；completion 帶 engine 編號，FW 對每個 engine 分開計數 | 專案負責人。後者要改 completion 的格式。控制程序的 D15 |
| O16 | 要不要留一個 engine 給 DECOMPRESS。只靠 FW 就做得到：reclaimer 同時在外的 COMPRESS 不超過 N 減 1，N 至少要 2。模擬的結果：這條規則保證至少一個 engine 不做 COMPRESS，但那個 engine 可能正在做別的 fault 的 DECOMPRESS，所以 fault 仍然可能等。4 個 engine、負載 10 倍時，同時在外 3 個與 4 個的 `queue` 最長分別是 0.63 µs 與 0.72 µs，分不出差別。大的 memory map 上同時在外 2 個量到 2.16 µs，比 4 個的 1.65 µs 還長。`sim-results-v0.md` 的 1.3 | 專案負責人。從模擬看沒有必要訂成規則，reclaimer 同時在外 2 到 4 個都可以 |
| O17 | 已處理，2026-11-13。模擬器的 HW model 與 checker 擴充成 N 個 engine，預設 4。completion 順序、同時執行、soft reset 都執行過。還沒做的：`sim/hwref` 仍然是單一 job 的 cycle 層級參考；ring 的 bus error 造成的 halt 在 N 個 engine 下只有單元測試，沒有放進結果文件的故障注入 | 無 |

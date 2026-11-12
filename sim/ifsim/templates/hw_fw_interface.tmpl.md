# LZ4 加速器 HW/FW 介面規格

版本 {{version}}，草稿。對象是寫 LZ4 HW 的人與寫 kernel 壓縮層的人。本文把 kernel 這一側稱為 FW。

> 本文由 `sim/ifsim/interface.json` 與 `sim/ifsim/templates/hw_fw_interface.tmpl.md` 產生，指令是 `python3 sim/run_if.py gen-spec`。
> 表格裡的 offset、欄位與規則文字都來自 `interface.json`，模擬器的 HW model、FW model 與 checker 讀的是同一份檔案。要改介面請改那份檔案再重新產生，不要直接改本文。

## 1. 範圍與分工

本文只規定 LZ4 HW 與 FW 之間看得到的東西：register、兩個 ring、三種資料結構、雙方各自要守的規則、interrupt 與 reset 的行為。HW 內部怎麼做 LZ4、FW 怎麼挑 victim page，都不在這裡。

採用偏 SW 控制的做法。複雜而且容易出錯的部分都在 FW，HW 只做一件事：照 descriptor 把一個 page 壓縮或解壓縮。

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

HW 在兩個 job 之間不保留任何狀態，除了 register。每個 job 需要的資訊都在它的 descriptor 裡。這帶來兩個好處：HW reset 之後不必重建任何東西，FW 把還沒完成的 job 重送一次就好；HW 能碰的記憶體範圍可以用四個 register 圈死，圈不到 HRT 的記憶體。

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
| 5 | HW | 從 `JOB_HEAD` 那一格讀 48 B，讀完把 `JOB_HEAD` 加 1。這一格從此歸還 FW |
| 6 | HW | 檢查 descriptor：opcode、count、chunk 號碼、frame_pa、長度。有一項不對就跳到步驟 8，status 是 BAD_DESC，不碰任何記憶體 |
| 7 | HW | 依序讀 5 個 chunk 的前 2296 B，算 CRC-32 並與 descriptor 的 checksum 比對，解成 4096 B 寫進 frame |
| 8 | HW | 把 16 B 的 completion 寫進 `CPL_TAIL` 那一格，然後把 `CPL_TAIL` 加 1。`IRQ_STATUS.DONE` 變 1，`IRQ_ENABLE.DONE` 是 1 的話 interrupt line 拉高 |
| 9 | FW | interrupt handler 或 polling 的 thread 讀 `CPL_TAIL`，把自己的 head 到 tail 之間的 completion 逐格讀出，用 tag 找到對應的 job，最後寫 `CPL_HEAD`。兩者相等時 interrupt line 自動變低 |
| 10 | FW | status 是 OK：拿 `mm_lock`，把這個 page 的 COT entry 清成 0，在 bitmap 釋放那 5 個 chunk，狀態改成 present，最後才把 PTE 寫成 valid |
| 11 | CPU | 從 page fault 返回，重新執行剛才那個指令 |

RO page 的差別只在步驟 10：壓縮的那一份留著，COT entry 與 chunk 都不動，只寫 PTE。

步驟 4 寫進 job ring 的 descriptor：

{{example:decompress_desc}}

步驟 8 HW 寫回的 completion：

{{example:decompress_cpl}}

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

{{example:compress_desc}}

步驟 6 的 completion：

{{example:compress_cpl}}

步驟 8 FW 寫進 COT 的 entry：

{{example:cot_after_compress}}

## 3. Register

全部是 32 bit，little-endian。offset 相對於 LZ4 HW 的 register base。標成 config 的 register 只能在 `CTRL.ENABLE` 是 0 的時候寫，HW 在 ENABLE 是 1 的時候忽略對它們的寫入。

{{registers}}

各 register 的欄位：

{{register_fields}}

常數：

{{constants}}

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

FW 一次可以寫好幾格再寫一次 `JOB_TAIL`。HW 一次只做一個 job，照 ring 的順序做，completion 的順序與 job 相同。FW 仍然用 tag 找 job，不依賴順序，所以將來 HW 有多個 engine、completion 順序改變時，FW 的協定不用改。

FW 同時在外的 job 數不超過 JOB_SIZE 減 1 與 CPL_SIZE 減 1 兩者較小的那個。這樣 completion ring 不會滿。HW 仍然要處理 completion ring 滿的情況：停下來等，不覆寫，見 `HW-CPL-3`。

## 5. 資料結構

所有多 byte 的欄位都是 little-endian。chunk 號碼是 24 bit，低 byte 在前，乘 512 加 `POOL_BASE` 就是 chunk 的 PA。

### 5.1 job descriptor，48 B

{{struct:job_desc}}

### 5.2 completion，16 B

{{struct:completion}}

### 5.3 COT entry，32 B

HW 不讀也不寫 COT。這裡列出來是因為 DECOMPRESS 的 descriptor 抄自它，COMPRESS 的結果寫進它，兩邊的欄位必須對得上。

{{struct:cot_entry}}

## 6. 列舉值

opcode：

{{enum:opcode}}

completion 的 status：

{{enum:status}}

status 是 BAD_DESC 時 `aux` 的值：

{{enum:bad_desc}}

`ERR_CODE` 的值：

{{enum:halt_code}}

flags 的 bit：

{{enum:flag}}

## 7. 規則

每條規則有編號。模擬器的 checker 與測試都用同一個編號，C header 裡也有對應的字串，FW 的 assert 與 log 可以直接引用。

### 7.1 FW 要守的

{{rules:FW}}

### 7.2 HW 要守的

{{rules:HW}}

### 7.3 整個系統在靜止時要成立的

{{rules:AUDIT}}

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

## 9. 錯誤處理與 reset

錯誤分三層，影響範圍一層比一層大。

| 層 | 例子 | HW 怎麼回報 | FW 怎麼處理 |
|---|---|---|---|
| 一個 job 的資料 | stream 壓不到 limit 以內；CRC-32 不符 | completion 的 status 是 INCOMPRESSIBLE 或 BAD_STREAM | INCOMPRESSIBLE：page 留在 frame。BAD_STREAM：FW 用自己的 decoder 再解一次，解得出來就照常使用，也解不出來才把這個 page 當成損毀，只影響擁有它的 user SW |
| 一個 job 的資料存取 | 讀寫 frame 或 chunk 時 bus 回報錯誤 | status 是 BUS_ERROR，其他欄位是 0。HW 不 halt，目的地的內容未定義 | DECOMPRESS：FW 用自己的 decoder 解同一份 stream 寫進 frame。COMPRESS：page 留在 frame，保留的 chunk 全部還回去，不把 page 記成壓不動 |
| 一個 job 的 descriptor | chunk 號碼超出 pool；frame_pa 不在 frame 區 | status 是 BAD_DESC，`aux` 是原因。HW 沒有碰任何 frame 或 chunk | 這是 FW 的 bug。記錄下來，不重送 |
| ring 本身 | ring 設定不合法；`JOB_TAIL` 超出格數；讀 ring 時 bus error | `STATUS.HALTED` 變 1，`ERR_CODE` 是原因，`IRQ_STATUS.ERROR` 變 1 | soft reset，重新設定，重送 |

HW 完全沒有回應時，FW 靠 timeout 發現：

| 步驟 | 誰做 | 做什麼 |
|---|---|---|
| 1 | FW | job 送出後超過 timeout 沒有 completion |
| 2 | FW | 先讀一次 completion ring。有 completion 就是 interrupt 漏了，照常處理，不 reset |
| 3 | FW | 確定沒有：對 `CTRL.SOFT_RESET` 寫 1 |
| 4 | HW | 進行中的 bus burst 做完就停。四個 ring 格號、`ERR_CODE`、`IRQ_STATUS`、`CTRL.ENABLE` 清成 0。config register 與 `IRQ_ENABLE` 保留。收尾完成後 `STATUS.BUSY` 變 0 |
| 5 | FW | 等 `STATUS.BUSY` 變 0，把自己的兩個格號歸零，對 `CTRL.ENABLE` 寫 1 |
| 6 | FW | 把所有還沒拿到 completion 的 job 從第 0 格起重新寫進 job ring，tag 不變，寫 `JOB_TAIL` |

Reset 與重送都沒有用時，driver 回報這個 job 沒有 completion，不再等。FW 從這時起不再使用 HW，到下次開機為止。HW 連續三次答錯也一樣：BUS_ERROR、FW 自己解得開的 BAD_STREAM，都算答錯。停用之後 FW 怎麼繼續，見控制程序 3.6。

重送是安全的，因為 job 是 idempotent：COMPRESS 的來源 frame 沒有被改過，DECOMPRESS 的來源 chunk 沒有被改過，目的地寫到一半的內容會被整個重寫，見 `HW-STATE-1`。這也是 `FW-MM-1` 與 `FW-MM-5` 存在的原因：job 沒有完成之前，沒有任何 PTE 指到那個 frame。

## 10. 時序假設與暫定 budget

介面本身不規定時間。下面這些數字是模擬器用來估效能的參數，全部是假設，等拿到實際平台的數字再換。來源欄寫 lz4sim 的是沿用前一版模擬器的值，寫設計選擇的是 FW 可以自己調的 policy。

{{params}}

暫定的 budget。目標都是先放的佔位值，還沒有人確認過，見未決事項 O1。

{{budgets}}

## 11. 決策紀錄

這些是定義介面時做的選擇，還沒有經過 review，每一條都可以改。

| 編號 | 決定 | 理由 | 放棄的做法 |
|---|---|---|---|
| D1 | `IRQ_STATUS.DONE` 是 level，等於 completion ring 不空 | 沒有清 interrupt 的 race，FW 少一個步驟 | W1C 的事件 bit |
| D2 | job ring 一格 64 B，descriptor 用 48 B | 格號換算位址只要 shift；一格剛好一條 cache line；留 16 B 給以後的欄位 | 一格 48 B |
| D3 | HW 每個 job 只讀 descriptor 一次，讀完就推進 `JOB_HEAD` | slot 很快還給 FW；HW 讀到的內容不會中途改變 | job 做完才推進 `JOB_HEAD` |
| D4 | ring 用 head 與 tail 兩個格號，永遠留一格空 | 空與滿不必另外記；與 NVMe 的 queue 相同，容易理解 | 另外放一個計數 register |
| D5 | 一個 engine，completion 照 job 的順序，tag 原樣抄回，FW 用 tag 找 job | 目前最簡單；以後加 engine 時 FW 不用改 | FW 依賴順序 |
| D6 | FW 把在外的 job 數限制在兩個 ring 較小的格數減 1 | completion ring 不會滿，HW 不必常常停下 | 只靠 HW 停下等 |
| D7 | soft reset 保留 config register 與 `IRQ_ENABLE`，清掉格號 | FW 恢復只要 enable 再重送 | reset 後全部重新設定 |
| D8 | HW 用 `POOL_*` 與 `FRAME_*` 四個 register 檢查每個 descriptor | FW 有 bug 時 HW 也不會寫到這兩個區域以外，HRT 的記憶體不受影響 | 完全信任 FW |
| D9 | CRC-32 由 HW 在壓縮時算、解壓縮時驗，FW 只負責存進 COT | 資料損毀在解壓縮當下就被發現，FW 不必自己算 | FW 算 CRC |
| D10 | COMPRESS 一次給 7 個 chunk，用不完的由 FW 釋放 | HW 不需要 allocator；bitmap 只有 FW 在改 | HW 自己拿 chunk |
| D11 | page fault 的 DECOMPRESS 與 reclaimer 的 COMPRESS 共用一個 job ring | 最簡單。一個 COMPRESS 擋在前面時 fault 多等多久，由模擬量出來 | 兩個 ring，fault 優先 |
| D12 | descriptor 裡的 frame_pa 是 32 bit | 目前的 address map 在 4 GB 以內 | 64 bit 或 frame 號碼 |

## 12. 未決事項

| 編號 | 事項 | 需要誰決定 |
|---|---|---|
| O1 | budget 的實際目標：fault latency、kernel CPU 佔比、engine 忙碌比例 | 專案負責人 |
| O2 | 時序參數的實際數字：interrupt latency、thread 叫醒時間、TLB invalidate、DRAM port 的 throughput、LZ4 core 每個 clock 處理幾個 byte | 專案負責人，或平台的量測資料 |
| O3 | core 的數量，用哪個 kernel 或 RTOS | 專案負責人 |
| O4 | 是否需要第二個 ring 或優先權，讓 page fault 的 job 插到 COMPRESS 前面 | 看模擬結果 |
| O5 | 等 completion 的方式：interrupt、polling，或先 polling 一小段再睡 | 看模擬結果 |
| O6 | user SW 碰到正在 COMPRESS 的 page 時，要等它壓完再解，還是取消那個 job 直接把 PTE 寫回去 | 看模擬結果。取消需要介面多一個動作 |
| O7 | 多個 engine 與不照順序的 completion | 目前不做，介面已經留了 `CAP.ENGINES` 與 tag |
| O8 | frame 或 chunk 的 bus error：模擬器還沒有做 | 之後補 |
| O9 | 省電：HW 閒置時的 clock gating，suspend 與 resume 之後 config register 是否還在 | HW 設計規格 |
| O10 | 先前討論中暫緩的項目：cold page 的 prefetch、有 phase 變化的 workload、kernel 的 page 狀態放在獨立陣列還是 invalid PTE 的空 bit | 動畫已經做完，可以排進來 |
| O11 | HW 的 master port 與 CPU cache 是否 coherent。目前照不 coherent 寫，FW 每個 job 做 cache clean 或 invalidate。兩個 ring 是否對應成 non-cacheable | SoC 整合。控制程序的 D8 |
| O12 | job ring 的格數要容得下同時在外的 job：每個正在 fault 的 thread 一個，加上 reclaimer 一個。格子不夠時送 job 的 thread 要等 | 看 thread 數。控制程序的第 11 節 |

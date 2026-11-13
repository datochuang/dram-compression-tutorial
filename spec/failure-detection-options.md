# 意外的偵測、預防與 debug：可以考慮的做法

**狀態：只是記錄，沒有採用。** 2026-11-12 討論時列出，專案負責人的決定是先記下來，目前不打算加進設計。這份文件不改變任何一份規格。

**對象**：之後要決定可靠度與 debug 功能的人。

**依據**：「現在誰發現」那一欄來自 [hw-fw-interface.md](hw-fw-interface.md) 第 9 節、[control-procedures-v0.md](control-procedures-v0.md) 的 F12、4.8 節、D6 與 A0 到 A7、[lz4-hw-design-spec-v0.md](lz4-hw-design-spec-v0.md) 的 A8 與 P3。「可以考慮的做法」是提案，沒有模擬過，也沒有估過硬體成本。

## 1. CRC-32 現在的角色

LZ4 HW 壓縮時對 stream 算 CRC-32，kernel 存進 COT entry。解壓縮時 LZ4 HW 先比對，不符就回 `BAD_STREAM`。kernel 再用自己的 decoder 解一次，也失敗才把 page 標成 LOST。

它防的是：壓縮後的 stream 放在 chunk pool 的這段時間被改掉。它只偵測，不修復。

## 2. 每種意外現在由誰發現

| 意外 | 現在誰發現 | 結果 |
|---|---|---|
| chunk 裡的 stream 被誤踩或 bit-flip | CRC-32，解壓縮當下 | kernel 自己再解一次，也失敗才標 LOST，只影響那個 page 的主人 |
| COT entry 的 chunk 編號或長度壞掉 | CRC-32，因為讀到的不是原來那份 stream | 同上 |
| LZ4 HW 讀寫 chunk 或 frame 時 bus 出錯 | `BUS_ERROR` | DECOMPRESS：kernel 用自己的 decoder 救回。COMPRESS：page 留在 frame |
| LZ4 HW 壓錯內容，但 stream 與 CRC 彼此一致 | 只有 `verify` 選項 | 沒開就是悄悄錯 |
| CPU cache 沒清，LZ4 HW 壓到舊資料或 CPU 讀到舊資料 | 沒有檢查，只靠 `cache_clean` 與 `cache_invalidate` 的規則 | 悄悄錯。F12 |
| kernel 的表被踩：bitmap、`state`、`owner`、`frame_of` | 沒有 | 例如 bitmap 一個 bit 翻掉，同一個 chunk 發給兩個 page，很久之後才在另一個 page 上看到 CRC 不符 |
| 兩筆 COT entry 整筆對調 | 沒有，CRC 沒有綁 page 編號 | 拿到別的 page 的內容 |
| PRESENT 的 frame 被踩 | 沒有，和沒有壓縮時一樣 | 悄悄錯 |
| LZ4 HW 內部 SRAM bit-flip | 沒有，HW 規格的 A8 是不加 ECC 或 parity | 視發生在哪一步 |
| descriptor 不合法 | LZ4 HW 回 `BAD_DESC`，不碰任何記憶體 | 是 kernel 的 bug，記錄下來 |
| LZ4 HW 沒有回應 | kernel 的 timeout | 連續 3 次就 `lz4_off` |

## 3. 為什麼有壓縮會更難 debug

1. **放大**：stream 裡翻一個 bit，解出來可能整個 page 都錯。
2. **延後**：錯在存放時發生，要到下一次 fault 才發現。
3. **位置會動**：同一個 page 每次被趕出去都換 chunk，固定位址壞掉不會表現成固定的 page 壞掉。
4. **memory dump 看不懂**：要有 COT 與 decoder 才還原得出內容。

## 4. 可以考慮的做法

### 4.1 偵測

| 編號 | 做法 | 抓什麼 | 誰做，代價 |
|---|---|---|---|
| X1 | 再加一個對未壓縮 page 算的 CRC，LZ4 HW 讀寫 frame 時順便算 | LZ4 HW 壓錯、解錯、內部 SRAM 翻 bit。kernel 另外用 CPU 算一次來比，還能抓到 cache 沒清 | HW 多一個 CRC。COT entry 多 4 B，有沒有空位還沒查 |
| X2 | 把 page 編號混進存放的 CRC | COT entry 放錯位置 | 只動 kernel，幾道指令 |
| X3 | `verify` 改成抽樣，例如每 N 次壓縮做一次 | LZ4 HW encoder 的偶發錯 | 只動 kernel，每次抽樣多一次軟體解碼 |
| X4 | 一致性巡檢：從 COT 重建 bitmap 來比，檢查 PTE、`frame_of`、`owner` 三者一致 | kernel 的表被踩 | 只動 kernel。模擬器結束時的 A0 到 A7 就是這套檢查 |
| X5 | 背景 scrub：新增一個只驗 CRC、不寫 frame 的 opcode，閒時掃過所有 stream | 提早發現，縮小「什麼時候壞的」的範圍 | HW 多一個 opcode |
| X6 | DRAM ECC | bit-flip | 平台層的決定。壓縮讓一個 bit 的影響變大，加 ECC 的理由比沒有壓縮時強 |

### 4.2 預防與圍堵

| 編號 | 做法 | 效果 |
|---|---|---|
| X7 | chunk pool 與 COT 在 CPU 這邊對應成唯讀或不對應，只在 kernel 要寫的那一小段打開 | 軟體誤踩當場變成 exception，直接指出是哪一道指令。CPU 本來就不寫 chunk，chunk pool 可以永遠唯讀 |
| X8 | bus 層的 firewall：只有 LZ4 HW 這個 master 可以寫 chunk pool | 擋住其他 IP 的 DMA 誤寫 |
| X9 | RO page 損毀時從 flash 上的原始 image 重新載入 | RO page 不會變成 LOST。這是 D6，前提是 flash 上留有原始內容 |
| 已有 | LZ4 HW 能碰的範圍用四個 register 圈死；`BAD_DESC`；連續 3 次出錯就 `lz4_off`；LOST 只影響 page 的主人 | 壞掉的範圍不會擴大 |

### 4.3 debug 工具

| 編號 | 做法 | 用途 |
|---|---|---|
| X10 | `BAD_STREAM` 在 `aux` 回細項：UNDERRUN、OVERFLOW、OFFSET、SHORT、CRC。HW 規格的提案 P3 | 分辨存放中壞掉與 encoder 的 bug |
| X11 | LOST 時保留現場：chunk 不釋放，記下 COT entry、chunk 的 PA、兩個 CRC、壓縮時的 tag | 事後重讀比對。兩次讀到的不同是電氣問題，相同是存的時候就錯 |
| X12 | job trace ring：每個 descriptor 與 completion 記一筆，格式與 hostsim 的 log 相同 | 查那幾個 chunk 上一次是誰寫的。trace 可以丟回 hostsim 重播 |
| X13 | 離線工具：吃 memory dump 與 COT，還原所有 page 並跑 A0 到 A7 | 解決 dump 看不懂的問題 |
| X14 | 分段開關：關壓縮、純軟體 codec、LZ4 HW 加 `verify`、正常 | 切開是 DRAM、kernel 還是 LZ4 HW 的問題 |
| X15 | LZ4 HW 的錯誤注入 register：強制回 `BAD_STREAM`、`BUS_ERROR`，或翻 stream 一個 bit | 在真的晶片上驗 kernel 的救援路徑 |

## 5. 如果之後要做，建議的順序

1. X7。成本最低，而且是唯一能當場抓到誤踩者的做法。
2. X4。kernel 的表目前完全沒有保護，而它壞掉的症狀離原因最遠。
3. X11 與 X12。沒有這兩個，出事後幾乎沒有線索。
4. X10。硬體成本近乎零。
5. X1。唯一能補上「cache 沒清」與「LZ4 HW 內部出錯」兩個洞的檢查，但要動 HW 與 COT 格式，要趁規格還是 v0 時決定。

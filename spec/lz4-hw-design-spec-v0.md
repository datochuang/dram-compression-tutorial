# LZ4 硬體加速器設計規格 v0

介面版本 0.1-draft。這份文件由 `sim/hwref/doc.py` 產生：表格、數字、範例與 pseudo code 都直接取自 reference model，不要手改這個檔案，改 template 或 model 之後重新產生。

讀者是寫 RTL 與寫 test bench 的工程師。讀完應該能回答四件事：硬體對外有哪些訊號、內部切成哪些 block、每個 block 逐 byte 要做出什麼結果、怎麼證明 RTL 做對了。

## 0. 怎麼讀這份文件

每一條要求屬於下面三種之一，文字裡會標出來。

| 標記 | 意思 | RTL 可以不照做嗎 |
|---|---|---|
| **必須** | 從硬體外面看得到的行為：bus 上的 access、寫進記憶體的 byte、completion、register、interrupt | 不行，test bench 逐項比對 |
| **基準** | 這份文件建議的內部架構：pipeline 切法、FSM 狀態、記憶體組織 | 可以，只要外面看到的行為完全一樣 |
| **假設** | 還沒有人確認的前提，例如 bus 種類與 clock | 確認之後可能會改，集中列在第 12 節 |

要求的編號用來對應 test bench 的檢查項目：`AXI-n` bus 行為、`CSR-n` register、`JOB-n` 單一 job 的行為、`ENC-n` encoder、`DEC-n` decoder、`RST-n` reset。介面規格 [hw-fw-interface.md](hw-fw-interface.md) 裡的規則沿用原編號，例如 HW-MEM-1。

三份 reference model 是這份規格的可執行版本。文字與 model 不一致時以 model 為準，並請回報。

| Model | 檔案 | 它定義什麼 |
|---|---|---|
| LZ4 core | `sim/hwref/lz4core.py` | encoder 寫出的 stream、decoder 的輸出與檢查、CRC |
| 單一 job | `sim/hwref/job.py` | 一個 descriptor 進去之後，哪些記憶體被讀寫、completion 的 16 B |
| Ring 與 register | `sim/ifsim/hw.py` | CSR、job ring、completion ring、halt、soft reset |

## 1. 範圍與前提

這顆硬體只做一件事：照 kernel（以下稱 FW）給的 descriptor，把一個 4096 B 的 page 壓成 LZ4 stream 寫進指定的 chunk，或把 chunk 裡的 stream 解回一個 page frame。

系統採偏 SW 的設計，分工如下。

| 誰 | 負責 |
|---|---|
| FW | COT、chunk bitmap、page 狀態機、選哪個 page 壓、配 chunk 與 frame、填 descriptor、收 completion、所有 policy |
| HW | 讀 descriptor、搬資料、LZ4 encode 與 decode、CRC、寫 completion |

硬體在兩個 job 之間不保留任何與資料有關的狀態（HW-STATE-1）。它不讀 COT，不知道 page 屬於誰，不做任何配置決定。

這一版不包含：多個 engine 平行、LZ4 以外的演算法、跨 page 的字典、硬體自己處理 page fault、DFT 與 power intent 的細節。

### 1.1 假設

下面的項目沒有人確認過。規格先照這些寫，確認結果不同時要改的章節列在右邊。

| 編號 | 假設 | 不成立時要改 |
|---|---|---|
| A1 | Register 走 APB，資料走 AXI4 master，data 64 bit | 第 3 節，`lz4_rdma`、`lz4_wdma`、`lz4_csr` |
| A2 | APB 與 AXI 同一個 clock，頻率未定 | 第 3 節要加 CDC；第 9 節的時間 |
| A3 | Reset 非同步 assert、同步 deassert，低態有效 | 第 3 節 |
| A4 | 只有一個 engine，job 一個接一個做 | 第 5、6 節 |
| A5 | 有 byte write enable 的 dual-port SRAM macro 可用 | 第 5.4 節的 page buffer 組織 |
| A6 | Interconnect 接受 64 beat 的 INCR burst | `BURST_BEATS` 參數與第 9 節 |
| A7 | 實體位址 32 bit | 介面的 descriptor 也要跟著改 |
| A8 | 內部記憶體不加 ECC 或 parity | 第 5.4 節 |
| A9 | 這一版不做 power gating | 第 12 節 P4 |

## 2. 一個 job 走過硬體

先用一個實際的 job 看完整個流程，後面各節再給通用的規則。這個 job 與介面規格第 5 節的範例是同一個，所有數字都是 reference model 跑出來的。

Page 的內容是 `vectors.records_page()`：一串長短不一的紀錄，有重複的欄位也有不重複的資料。壓出來 1837 B，要 4 個 chunk。

### 2.1 COMPRESS

**步驟 1，FW：填 descriptor。** FW 選好要壓的 frame，從 bitmap 配 7 個 chunk，把 descriptor 寫進 job ring 的 slot 5，位址 0x80180140。`limit` 是 3584：這是 RW page，壓出來超過 7 個 chunk 就不值得存。

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

**步驟 2，FW：敲 doorbell。** FW 把 `JOB_TAIL` 寫成 5 的下一格。

**步驟 3，HW：讀 descriptor、檢查。** 硬體看到 `JOB_HEAD != JOB_TAIL`，用一個 6 beat 的 burst 讀回 48 B，`JOB_HEAD` 前進，接著依序做五項檢查（第 6.2 節）。這個 descriptor 全部通過。

**步驟 4，HW：搬資料與壓縮。** 硬體在 bus 上發出的 burst 依序如下。

| # | 方向 | 位址 | 大小 B | beat | 內容 |
|---|---|---|---|---|---|
| 1 | 讀 | 0x80180140 | 48 | 6 | job ring 第 5 格的 descriptor |
| 2 | 讀 | 0x97A1C000 | 512 | 64 | frame 的 byte 0 到 511 |
| 3 | 讀 | 0x97A1C200 | 512 | 64 | frame 的 byte 512 到 1023 |
| 4 | 讀 | 0x97A1C400 | 512 | 64 | frame 的 byte 1024 到 1535 |
| 5 | 讀 | 0x97A1C600 | 512 | 64 | frame 的 byte 1536 到 2047 |
| 6 | 讀 | 0x97A1C800 | 512 | 64 | frame 的 byte 2048 到 2559 |
| 7 | 讀 | 0x97A1CA00 | 512 | 64 | frame 的 byte 2560 到 3071 |
| 8 | 讀 | 0x97A1CC00 | 512 | 64 | frame 的 byte 3072 到 3583 |
| 9 | 讀 | 0x97A1CE00 | 512 | 64 | frame 的 byte 3584 到 4095 |
| 10 | 寫 | 0x89908800 | 512 | 64 | `chunk[0]`，chunk 號碼 0x1C044：stream 的 byte 0 到 511 |
| 11 | 寫 | 0x89908A00 | 512 | 64 | `chunk[1]`，chunk 號碼 0x1C045：stream 的 byte 512 到 1023 |
| 12 | 寫 | 0x8C24E200 | 512 | 64 | `chunk[2]`，chunk 號碼 0x30A71：stream 的 byte 1024 到 1535 |
| 13 | 寫 | 0x8C24EA00 | 512 | 64 | `chunk[3]`，chunk 號碼 0x30A75：stream 的 byte 1536 到 1836，後面 211 B 是補的 |
| 14 | 寫 | 0x80181050 | 16 | 2 | completion ring 第 5 格 |

Frame 的 8 個 read burst 把整個 page 放進 page buffer。之後 encoder 一個位置一個位置往前找。前幾個位置的經過：

| `ip` | `page[ip..ip+3]` | `word` | `h` | 讀到的 `table[h]` | 寫入 `table[h]` | 結果 |
|---|---|---|---|---|---|---|
| 0 | `00 10 00 00` | 0x00001000 | 0x004 | 空 | 0 | 沒有 candidate，這個 byte 是 literal |
| 1 | `10 00 00 02` | 0x02000010 | 0x030 | 空 | 1 | 沒有 candidate，這個 byte 是 literal |
| 2 | `00 00 02 00` | 0x00020000 | 0x080 | 空 | 2 | 沒有 candidate，這個 byte 是 literal |
| 3 | `00 02 00 60` | 0x60000200 | 0x001 | 空 | 3 | 沒有 candidate，這個 byte 是 literal |
| 4 | `02 00 60 01` | 0x01600002 | 0x014 | 空 | 4 | 沒有 candidate，這個 byte 是 literal |
| 5 | `00 60 01 B0` | 0xB0016000 | 0x35A | 空 | 5 | 沒有 candidate，這個 byte 是 literal |
| 6 | `60 01 B0 25` | 0x25B00160 | 0x33B | 空 | 6 | 沒有 candidate，這個 byte 是 literal |
| 7 | `01 B0 25 3F` | 0x3F25B001 | 0x29F | 空 | 7 | 沒有 candidate，這個 byte 是 literal |
| 8 | `B0 25 3F 9A` | 0x9A3F25B0 | 0x3D8 | 空 | 8 | 沒有 candidate，這個 byte 是 literal |
| 9 | `25 3F 9A 00` | 0x009A3F25 | 0x1A3 | 空 | 9 | 沒有 candidate，這個 byte 是 literal |
| 10 | `3F 9A 00 00` | 0x00009A3F | 0x219 | 空 | 10 | 沒有 candidate，這個 byte 是 literal |
| 11 | `9A 00 00 00` | 0x0000009A | 0x09A | 空 | 11 | 沒有 candidate，這個 byte 是 literal |
| 12 | `00 00 00 00` | 0x00000000 | 0x000 | 空 | 12 | 沒有 candidate，這個 byte 是 literal |
| 13 | `00 00 00 6D` | 0x6D000000 | 0x2D1 | 空 | 13 | 沒有 candidate，這個 byte 是 literal |
| 14 | `00 00 6D 6F` | 0x6F6D0000 | 0x1B7 | 空 | 14 | 沒有 candidate，這個 byte 是 literal |
| 15 | `00 6D 6F 64` | 0x646F6D00 | 0x09C | 空 | 15 | 沒有 candidate，這個 byte 是 literal |
| 16 | `6D 6F 64 65` | 0x65646F6D | 0x021 | 空 | 16 | 沒有 candidate，這個 byte 是 literal |
| 17 | `6F 64 65 6D` | 0x6D65646F | 0x3E1 | 空 | 17 | 沒有 candidate，這個 byte 是 literal |
| 18 | `64 65 6D 5F` | 0x5F6D6564 | 0x3CA | 空 | 18 | 沒有 candidate，這個 byte 是 literal |
| 19 | `65 6D 5F 72` | 0x725F6D65 | 0x19A | 空 | 19 | 沒有 candidate，這個 byte 是 literal |
| 20 | `6D 5F 72 78` | 0x78725F6D | 0x07C | 空 | 20 | 沒有 candidate，這個 byte 是 literal |
| 21 | `5F 72 78 00` | 0x0078725F | 0x044 | 空 | 21 | 沒有 candidate，這個 byte 是 literal |
| 22 | `72 78 00 00` | 0x00007872 | 0x06C | 空 | 22 | 沒有 candidate，這個 byte 是 literal |
| 23 | `78 00 00 00` | 0x00000078 | 0x078 | 空 | 23 | 沒有 candidate，這個 byte 是 literal |
| 24 | `00 00 00 00` | 0x00000000 | 0x000 | 12 | 24 | **位置 12 的 4 個 byte 相同：match，offset 是 12** |

位置 0 到 23 查到的 hash table entry 都是空的，這些 byte 成為 literal。位置 24 第一次查到候選位置而且 4 個 byte 相同，於是產生第一個 sequence。整個 page 總共查了 1115 個位置，產生 351 個 sequence，其中 350 個帶 match。

| sequence | 在 stream 的位置 | 在 page 的位置 | literal 數 | match 長度 | offset | 寫進 stream 的 byte，依序 |
|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 24 | 4 | 12 | token `F0`，literal 長度的延伸 `09`，24 個 literal，offset `0C 00` |
| 2 | 28 | 28 | 1 | 5 | 28 | token `11`，literal `01`，offset `1C 00` |
| 3 | 32 | 34 | 4 | 6 | 28 | token `42`，literal `E4 00 58 3D`，offset `1C 00` |
| … |  |  |  |  |  | 中間 346 個 sequence |
| 350 | 1824 | 3436 | 1 | 654 | 1 | token `1F`，literal `00`，offset `01 00`，match 長度的延伸 `FF FF 7D` |
| 351 | 1831 | 4091 | 5 | 沒有 |  | token `50`，literal `00 00 00 00 00` |

Stream 的前 32 個 byte：

```
F0 09 00 10 00 00 02 00 60 01 B0 25 3F 9A 00 00 00 00 6D 6F 64 65 6D 5F 72 78 0C 00 11 01 1C 00
```

最後 14 個 byte：

```
00 1F 00 01 00 FF FF 7D 50 00 00 00 00 00
```

**步驟 5，HW：寫 chunk。** Stream 的 byte 依序寫進 `chunk[0]`、`chunk[1]` …，每個 chunk 一個 512 B 的 burst。1837 B 用掉 4 個 chunk，最後一個 chunk 後面的 211 B 由硬體補 0。補的 0 不算進 CRC，FW 也不會去讀它。`chunk[4]` 到 `chunk[6]` 完全沒有被碰（HW-MEM-1）。

**步驟 6，HW：寫 completion。** 硬體等 completion ring 有空位，把 16 B 寫到 slot 5，位址 0x80181050，然後 `CPL_TAIL` 前進，`IRQ_STATUS.DONE` 變 1。

| Offset | 記憶體裡的 byte，由低位址到高位址 | 欄位 | 值 |
|---|---|---|---|
| 0x00 | `00` | `status` | OK（0） |
| 0x01 | `00` | `flags` | 0x00 |
| 0x02 | `2D 07` | `length` | 1837 |
| 0x04 | `BD 14 AD F7` | `checksum` | 0xF7AD14BD |
| 0x08 | `A8 02 00 00` | `tag` | 0x000002A8 |
| 0x0C | `00 00 00 00` | `aux` | 0 |

**步驟 7，FW：收 completion。** FW 讀到 `length` 1837，算出用了 4 個 chunk，把沒用到的 3 個還給 bitmap，把 `checksum` 與 chunk 編號記進 COT，最後推進 `CPL_HEAD`。

基準架構下，這個 job 各階段估計的 cycle 數：

| 階段 | 做什麼 | cycle |
|---|---|---|
| FETCH 與 CHECK | 讀 descriptor 6 個 beat，檢查 | 11 |
| LOAD | frame 的 8 個 burst 進 page buffer | 536 |
| ENCODE | 1115 個位置查過 hash table，350 個 match；前面的 chunk 在這段時間裡寫出去 | 4032 |
| 最後一個 chunk | encoder 結束時還沒送出的那個 burst | 67 |
| POST | 寫 completion 2 個 beat，推進 `CPL_TAIL` | 5 |
| **合計** |  | **4651** |

### 2.2 DECOMPRESS 同一個 stream

之後 CPU 碰到這個 page，FW 要把它解回來。

**步驟 1，FW：填 descriptor。** FW 配一個空的 frame，從 COT 抄出 chunk 編號、`comp_len` 與 `checksum`。

| Offset | 記憶體裡的 byte，由低位址到高位址 | 欄位 | 值 |
|---|---|---|---|
| 0x00 | `02` | `opcode` | DECOMPRESS（2） |
| 0x01 | `04` | `count` | 4 |
| 0x02 | `00 00` | `limit` | 0 |
| 0x04 | `00 D0 A1 97` | `frame_pa` | 0x97A1D000 |
| 0x08 | `2D 07` | `comp_len` | 1837 |
| 0x0A | `00 00` | `flags` | 0x0000 |
| 0x0C | `BD 14 AD F7` | `checksum` | 0xF7AD14BD |
| 0x10 | `A9 02 00 00` | `tag` | 0x000002A9 |
| 0x14 | `44 C0 01 45 C0 01 71 0A 03 75 0A 03 00 00 00 00 00 00 00 00 00 00 00 00` | `chunk` | 0x1C044、0x1C045、0x30A71、0x30A75，其餘填 0 |
| 0x2C | `00 00 00 00` | `rsvd` | 0 |

**步驟 2，HW：搬資料與解壓縮。**

| # | 方向 | 位址 | 大小 B | beat | 內容 |
|---|---|---|---|---|---|
| 1 | 讀 | 0x80180140 | 48 | 6 | job ring 第 5 格的 descriptor |
| 2 | 讀 | 0x89908800 | 512 | 64 | `chunk[0]`，chunk 號碼 0x1C044 |
| 3 | 讀 | 0x89908A00 | 512 | 64 | `chunk[1]`，chunk 號碼 0x1C045 |
| 4 | 讀 | 0x8C24E200 | 512 | 64 | `chunk[2]`，chunk 號碼 0x30A71 |
| 5 | 讀 | 0x8C24EA00 | 512 | 64 | `chunk[3]`，chunk 號碼 0x30A75 |
| 6 | 寫 | 0x97A1D000 | 512 | 64 | frame 的 byte 0 到 511 |
| 7 | 寫 | 0x97A1D200 | 512 | 64 | frame 的 byte 512 到 1023 |
| 8 | 寫 | 0x97A1D400 | 512 | 64 | frame 的 byte 1024 到 1535 |
| 9 | 寫 | 0x97A1D600 | 512 | 64 | frame 的 byte 1536 到 2047 |
| 10 | 寫 | 0x97A1D800 | 512 | 64 | frame 的 byte 2048 到 2559 |
| 11 | 寫 | 0x97A1DA00 | 512 | 64 | frame 的 byte 2560 到 3071 |
| 12 | 寫 | 0x97A1DC00 | 512 | 64 | frame 的 byte 3072 到 3583 |
| 13 | 寫 | 0x97A1DE00 | 512 | 64 | frame 的 byte 3584 到 4095 |
| 14 | 寫 | 0x80181050 | 16 | 2 | completion ring 第 5 格 |

硬體讀 ceil(1837 / 512) = 4 個 chunk。Decoder 不等全部讀完：stream 的 byte 一進來就開始解，解出來的 byte 一邊進 page buffer 當作之後 match 的來源，一邊排隊寫回 frame。Decoder 的幾個 sequence：

| sequence | 開始時的 `ipos` | `token` | `ll` | literal 寫到 | `offset` | `ml` | match 從哪裡讀 | 結束時的 `ipos` | 結束時的 `opos` |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0 | 0xF0 | 24 | `page[0..23]` | 12 | 4 | `page[12]` 起，history register | 28 | 28 |
| 2 | 28 | 0x11 | 1 | `page[28..28]` | 28 | 5 | `page[1]` 起，page buffer | 32 | 34 |
| 3 | 32 | 0x42 | 4 | `page[34..37]` | 28 | 6 | `page[10]` 起，page buffer | 39 | 44 |
| … |  |  |  |  |  |  |  |  |  |
| 350 | 1824 | 0x1F | 1 | `page[3436..3436]` | 1 | 654 | `page[3436]` 起，history register | 1831 | 4091 |
| 351 | 1831 | 0x50 | 5 | `page[4091..4095]` |  | 沒有 |  | 1837 | 4096 |

這個 stream 有 6 個 match 的 offset 小於 24，它們從 history register 複製，其餘的讀 page buffer（第 7.4 節說明為什麼分兩種）。

**步驟 3，HW：比對 CRC、寫 completion。** 硬體對讀進來的前 1837 個 byte 算 CRC-32，結果與 descriptor 的 `checksum` 相同，decoder 也剛好輸出 4096 B，所以 status 是 OK。

| Offset | 記憶體裡的 byte，由低位址到高位址 | 欄位 | 值 |
|---|---|---|---|
| 0x00 | `00` | `status` | OK（0） |
| 0x01 | `00` | `flags` | 0x00 |
| 0x02 | `00 10` | `length` | 4096 |
| 0x04 | `BD 14 AD F7` | `checksum` | 0xF7AD14BD |
| 0x08 | `A9 02 00 00` | `tag` | 0x000002A9 |
| 0x0C | `00 00 00 00` | `aux` | 0 |

| 階段 | 做什麼 | cycle |
|---|---|---|
| FETCH 與 CHECK | 讀 descriptor 6 個 beat，檢查 | 11 |
| DECODE | 351 個 sequence；chunk 的讀取與 frame 前 7 個 burst 的寫入都在這段時間裡 | 1950 |
| 最後一個 burst | decoder 結束時還沒送出的 frame 最後 512 B | 67 |
| POST | 寫 completion 2 個 beat，推進 `CPL_TAIL` | 5 |
| **合計** |  | **2033** |

上表是邊解邊寫（store-behind）的估計。如果改成整個 page 解完、CRC 確認之後才寫 frame，總數會是 2488 cycle（第 7.5 節比較兩種做法）。

## 3. 硬體介面

### 3.1 訊號

下表是 **假設** A1 到 A3 之下的 top level port。方向從這顆硬體看。

| 群組 | 訊號 | 方向 | 寬度 | 說明 |
|---|---|---|---|---|
| 共用 | `clk` | in | 1 | APB 與 AXI 共用 |
| 共用 | `rst_n` | in | 1 | 非同步 assert、同步 deassert |
| 共用 | `irq` | out | 1 | Level，高態有效，與 `clk` 同步 |
| APB slave | `psel`、`penable`、`pwrite` | in | 各 1 | |
| APB slave | `paddr` | in | 8 | Byte 位址，只接受 4 的倍數 |
| APB slave | `pwdata` | in | 32 | |
| APB slave | `prdata` | out | 32 | |
| APB slave | `pready` | out | 1 | 固定為 1 |
| APB slave | `pslverr` | out | 1 | 固定為 0 |
| AXI AR | `arvalid`、`arready` | out、in | 各 1 | |
| AXI AR | `araddr` | out | 32 | |
| AXI AR | `arlen` | out | 8 | |
| AXI AR | `arsize`、`arburst` | out | 3、2 | 固定 3（8 B）、固定 INCR |
| AXI AR | `arid` | out | `ID_W` | 固定為 0 |
| AXI R | `rvalid`、`rready` | in、out | 各 1 | |
| AXI R | `rdata` | in | 64 | |
| AXI R | `rresp`、`rlast`、`rid` | in | 2、1、`ID_W` | |
| AXI AW | `awvalid`、`awready` | out、in | 各 1 | |
| AXI AW | `awaddr`、`awlen` | out | 32、8 | |
| AXI AW | `awsize`、`awburst`、`awid` | out | 3、2、`ID_W` | 同 AR |
| AXI W | `wvalid`、`wready` | out、in | 各 1 | |
| AXI W | `wdata`、`wstrb` | out | 64、8 | |
| AXI W | `wlast` | out | 1 | |
| AXI B | `bvalid`、`bready` | in、out | 各 1 | |
| AXI B | `bresp`、`bid` | in | 2、`ID_W` | |

`AxCACHE`、`AxPROT`、`AxQOS`、`AxLOCK` 由整合的人決定固定值，硬體不會動態改變它們。

### 3.2 硬體會發出的 burst

硬體只發下面五種 burst，沒有其他種類。

| 用途 | 方向 | 位址 | Beat 數 | `AxLEN` |
|---|---|---|---|---|
| 讀 descriptor | read | `JOB_BASE + JOB_HEAD × 64` | 6 | 5 |
| 寫 completion | write | `CPL_BASE + CPL_TAIL × 16` | 2 | 1 |
| 讀或寫一個 chunk | read 或 write | `POOL_BASE + chunk × 512` | 64 | 63 |
| 讀或寫 frame 的八分之一 | read 或 write | `frame_pa + k × 512`，k 為 0 到 7 | 64 | 63 |

Descriptor 的 slot 是 64 B，硬體只讀前 48 B。

### 3.3 Bus 行為的要求

| 編號 | 等級 | 要求 |
|---|---|---|
| AXI-1 | 必須 | 每個 beat 的 bit [7:0] 是位址最低的那個 byte。記憶體裡的多 byte 欄位都是 little endian |
| AXI-2 | 必須 | 同一時間最多一個 read burst、一個 write burst 還沒結束。只用一個 ID |
| AXI-3 | 必須 | 所有 write beat 的 `wstrb` 全為 1。唯一例外是 soft reset 排空時補送的 beat，`wstrb` 為 0（RST-3） |
| AXI-4 | 必須 | 不發跨 4 KB 邊界的 burst。在 base 位址對齊的前提下這自動成立，見第 12 節 P1 |
| AXI-5 | 必須 | `rresp` 或 `bresp` 不是 OKAY 就算 bus error。出錯的 burst 仍然照協定收完或送完 |
| AXI-6 | 必須 | 結果不可以因為 `arready`、`rvalid`、`awready`、`wready`、`bvalid` 來得早或晚而不同。寫進記憶體的 byte、completion 與 access 的集合都一樣，只有時間不同 |
| AXI-7 | 必須 | 不讀也不寫 descriptor 沒有授權的位址（HW-MEM-1、HW-MEM-2）。授權的範圍由 `job.allowed()` 定義 |
| AXI-8 | 基準 | Read burst 期間 `rready` 一直是 1：發 AR 之前先確認內部有 64 個 word 的空位 |
| AXI-9 | 基準 | Write burst 的 beat 之間 `wvalid` 不掉下來：64 個 word 都備妥才發 AW。W 不早於 AW。`bready` 固定為 1 |
| AXI-10 | 基準 | Chunk 與 frame 的 burst 長度由參數 `BURST_BEATS` 決定，預設 64。改小時一個 chunk 拆成多個 burst，結果不變 |

AXI-8 與 AXI-9 讓硬體不會佔著 bus 卻不傳資料，對同一條 bus 上的其他 master 比較友善。

### 3.4 參數

| 參數 | 預設 | 範圍 | 說明 |
|---|---|---|---|
| `HASH_BITS` | 10 | 10 到 12 | Hash table 有 2^`HASH_BITS` 個 entry。改這個值會改變 stream，reference model 要用同一個值 |
| `ID_W` | 4 | 1 以上 | AXI ID 寬度 |
| `BURST_BEATS` | 64 | 16、32、64 | Chunk 與 frame 的 burst 長度 |

## 4. SW 控制介面

這一節是 FW 看到的硬體。完整的定義、每個欄位的理由與 FW 端的規則在 [hw-fw-interface.md](hw-fw-interface.md)，C header 在 [lz4_hwif.h](lz4_hwif.h)。這裡重複 RTL 需要的部分，兩份文件的表格由同一份 `interface.json` 產生。

### 4.1 Register

| Offset | Register | 存取 | Reset 值 | config | 說明 |
|---|---|---|---|---|---|
| 0x00 | `ID` | RO | 0x4C5A0001 |  | 固定值 0x4C5A0001。FW 在 probe 時確認 |
| 0x04 | `CAP` | RO | 0x0001AC98 |  | 硬體能力 |
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

欄位：

**`CAP`，offset 0x04**

| Bit | 欄位 | 存取 | 說明 |
|---|---|---|---|
| 3:0 | `CHUNK_SLOTS` | RO | 一個 job 最多的 chunk 數，目前是 8 |
| 7:4 | `CHUNK_SHIFT` | RO | log2(chunk size)，目前是 9 |
| 11:8 | `PAGE_SHIFT` | RO | log2(page size)，目前是 12 |
| 15:12 | `RING_SHIFT_MAX` | RO | ring 最多 2^N 格，目前是 10 |
| 19:16 | `ENGINES` | RO | LZ4 engine 的數量，目前是 1 |

**`CTRL`，offset 0x08**

| Bit | 欄位 | 存取 | 說明 |
|---|---|---|---|
| 0 | `ENABLE` | RW | 1 表示硬體開始從 job ring 取 job。由 0 寫成 1 時硬體檢查 ring 設定 |
| 1 | `SOFT_RESET` | RW | 寫 1 觸發 soft reset，讀回永遠是 0 |

**`STATUS`，offset 0x0C**

| Bit | 欄位 | 存取 | 說明 |
|---|---|---|---|
| 0 | `BUSY` | RO | 1 表示有 job 正在執行，或 reset 還沒收尾 |
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

### 4.2 寫 register 的副作用

| 編號 | 等級 | 要求 |
|---|---|---|
| CSR-1 | 必須 | 寫 `CTRL` 時 `SOFT_RESET` 為 1：執行 soft reset（第 6.5 節），同一次寫入的其他 bit 忽略。`SOFT_RESET` 讀回永遠是 0 |
| CSR-2 | 必須 | `ENABLE` 從 0 變 1 時檢查設定：`JOB_SIZE` 與 `CPL_SIZE` 是 2 的次方且在 2 到 2^`RING_SHIFT_MAX` 之間，`JOB_BASE` 是 64 的倍數，`CPL_BASE` 是 16 的倍數。不通過就 halt，代碼 BAD_RING_CFG，`ENABLE` 維持 0 |
| CSR-3 | 基準 | CSR-2 另外檢查 `POOL_BASE` 是 512 的倍數、`FRAME_BASE` 是 4096 的倍數。這比介面 0.1-draft 嚴格，是第 12 節的提案 P1 |
| CSR-4 | 必須 | `ENABLE` 從 1 變 0：正在做的 job 做完並寫出 completion，之後不再取新的 job |
| CSR-5 | 必須 | `ENABLE` 為 1 時，寫 `JOB_BASE`、`JOB_SIZE`、`CPL_BASE`、`CPL_SIZE`、`POOL_BASE`、`POOL_CHUNKS`、`FRAME_BASE`、`FRAME_COUNT` 沒有作用 |
| CSR-6 | 必須 | 寫 `JOB_TAIL` 的值大於等於 `JOB_SIZE`，或寫 `CPL_HEAD` 的值大於等於 `CPL_SIZE`：halt，代碼 BAD_INDEX，值不存進去 |
| CSR-7 | 必須 | 寫唯讀 register 沒有作用。讀沒有定義的 offset 得到 0，寫沒有作用 |
| CSR-8 | 必須 | `IRQ_STATUS.DONE` 不是 latch：它等於 `CPL_TAIL != CPL_HEAD`。`IRQ_STATUS.ERROR` 寫 1 清除 |
| CSR-9 | 必須 | `irq` = (`DONE` 且 `IRQ_ENABLE[0]`) 或 (`ERROR` 且 `IRQ_ENABLE[1]`)（HW-IRQ-1） |
| CSR-10 | 必須 | `STATUS.BUSY` 在硬體取走一個 descriptor 到它的 completion 寫完之間為 1，soft reset 排空期間也為 1 |
| CSR-11 | 必須 | Halt 時 `STATUS.HALTED` 與 `IRQ_STATUS.ERROR` 變 1，`ERR_CODE` 記下代碼，較晚發生的代碼蓋掉較早的。只有 soft reset 能離開 halt |

### 4.3 Ring

兩個 ring 都在 FW 配的記憶體裡，硬體只保存 base、size 與兩個 index。

| Ring | Slot 位址 | 誰寫 slot | 誰推進哪個 index |
|---|---|---|---|
| Job | `JOB_BASE + i × 64` | FW | FW 推 `JOB_TAIL`，HW 推 `JOB_HEAD` |
| Completion | `CPL_BASE + i × 16` | HW | HW 推 `CPL_TAIL`，FW 推 `CPL_HEAD` |

Index 加 1 之後與 size − 1 做 AND。Ring 空的條件是 head 等於 tail，滿的條件是 tail 的下一格等於 head，所以 size 為 N 的 ring 最多放 N − 1 筆。

| 編號 | 等級 | 要求 |
|---|---|---|
| JOB-1 | 必須 | Descriptor 的 48 B 讀完且沒有 bus error，`JOB_HEAD` 才前進，而且立刻前進，不等 job 做完。每個 job 只讀一次 descriptor（HW-MEM-2） |
| JOB-2 | 必須 | Completion 照 job 被取走的順序寫出，每個被取走的 descriptor 剛好一筆（HW-CPL-1）。例外只有 halt 代碼 RING_BUS_ERROR 與 soft reset 打斷的 job |
| JOB-3 | 必須 | Completion ring 滿的時候硬體等待，不覆蓋、不丟棄（HW-CPL-3）。`CPL_TAIL` 在這個 job 所有資料的 write response 與 completion 的 write response 都回來之後才前進（HW-CPL-2） |
| JOB-4 | 必須 | `tag` 原封不動抄進 completion（HW-CPL-1） |

### 4.4 FW 的操作順序

RTL 不實作這些，但 test bench 的 driver 要照這個順序，硬體的 reset 值與副作用也是配合它設計的。數字是第 2 節的範例。

初始化，全部是 FW：

1. 讀 `ID`，確認是 0x4C5A0001。讀 `CAP`。
2. 寫 `CTRL` = 0x2 做 soft reset，等 `STATUS.BUSY` 變 0。
3. 寫 `JOB_BASE` = 0x80180000、`JOB_SIZE`、`CPL_BASE` = 0x80181000、`CPL_SIZE`、`POOL_BASE` = 0x86100000、`POOL_CHUNKS`、`FRAME_BASE` = 0x97400000、`FRAME_COUNT`。
4. 寫 `IRQ_ENABLE` = 0x3。
5. 寫 `CTRL` = 0x1。讀 `STATUS`，確認 `HALTED` 是 0。

送一個 job：

1. FW：確認 job ring 沒滿。
2. FW：把 48 B 的 descriptor 寫進 slot `JOB_TAIL`。
3. FW：`JOB_TAIL` 寫成下一格。
4. HW：做 job，寫 completion，推 `CPL_TAIL`，拉 `irq`。

收 completion：

1. FW：讀 `CPL_TAIL`。
2. FW：從 `CPL_HEAD` 讀到 `CPL_TAIL` 的前一格，每筆依 `tag` 找回對應的 page。
3. FW：`CPL_HEAD` 寫成讀到的位置。HW：兩個 index 相等時 `DONE` 變 0，`irq` 放掉。

Halt 之後：FW 讀 `ERR_CODE`，寫 `CTRL` = 0x2，等 `BUSY` 變 0，重新設定，把還沒有 completion 的 job 重送（FW-RST-1）。

### 4.5 資料結構

Job descriptor，48 B：

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

Completion，16 B：

| Offset | 大小 B | 欄位 | 說明 |
|---|---|---|---|
| 0x00 | 1 | `status` | 見 enum status |
| 0x01 | 1 | `flags` | bit2 RAW：COMPRESS 存的是沒壓縮的 4096 B |
| 0x02 | 2 | `length` | COMPRESS OK：stream 的長度。DECOMPRESS OK：4096。其他狀態：0 |
| 0x04 | 4 | `checksum` | stream 的 CRC-32 |
| 0x08 | 4 | `tag` | descriptor 的 tag |
| 0x0C | 4 | `aux` | BAD_DESC 時是 enum bad_desc 的代碼，其餘是 0 |

Opcode：

| 值 | 名稱 | 說明 |
|---|---|---|
| 1 | `COMPRESS` | 讀 frame，壓成 LZ4 block，寫進 descriptor 列出的 chunk |
| 2 | `DECOMPRESS` | 讀 descriptor 列出的 chunk，驗 CRC-32，解回 frame |

Status：

| 值 | 名稱 | 說明 |
|---|---|---|
| 0 | `OK` | 完成 |
| 1 | `INCOMPRESSIBLE` | COMPRESS 的 stream 超過 limit。chunk 內容不定，frame 沒被動過 |
| 3 | `BAD_STREAM` | DECOMPRESS 的 CRC-32 不符或 stream 格式錯。frame 內容不定 |
| 5 | `BUS_ERROR` | 讀寫 frame 或 chunk 時 bus 回報錯誤 |
| 6 | `BAD_DESC` | descriptor 沒通過檢查，硬體沒有碰任何 frame 或 chunk。原因在 aux |

`status` 為 BAD_DESC 時 `aux` 的值：

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

Flag：

| 值 | 名稱 | 說明 |
|---|---|---|
| 1 | `VALID` | COT entry 有效 |
| 2 | `RO` | COT entry 屬於 RO page |
| 4 | `RAW` | stream 是沒壓縮的 4096 B |

### 4.6 硬體要守的介面規則

下表是介面規格裡以 HW 為對象的規則，最右欄是 test bench 用什麼檢查。

| 編號 | 規則，原文來自介面規格 | 主要由哪個 block 負責 | RTL bench 怎麼驗 |
|---|---|---|---|
| `HW-MEM-1` | 硬體只讀寫四種位置：JOB_HEAD 那一格 descriptor、目前 job 的 frame、目前 job 列出的 chunk、CPL_TAIL 那一格 completion。COMPRESS 不寫 frame，DECOMPRESS 不寫 chunk。 | `lz4_ctrl`、`lz4_rdma`、`lz4_wdma` | bus monitor：每個 burst 的位址與方向都在 `hwref.job.allowed` 列出的範圍內，或是 ring 的那一格 |
| `HW-MEM-2` | 硬體先把 descriptor 的 48 B 讀完才推進 JOB_HEAD，每個 job 只讀一次，之後不再回頭讀。 | `lz4_ctrl` | bus monitor：每個 job 恰好一次 6 個 beat 的讀，位址是 `JOB_HEAD` 那一格；`JOB_HEAD` 在最後一個 beat 之後才變 |
| `HW-CPL-1` | 每個 job 恰好一個 completion，順序與 job 相同，tag 原樣抄回。 | `lz4_ctrl` | scoreboard：completion 的順序與 tag 對得上送進去的 job |
| `HW-CPL-2` | job 的資料全部寫完、completion 的 16 B 也寫完之後，才推進 CPL_TAIL。 | `lz4_ctrl`、`lz4_wdma` | monitor：`CPL_TAIL` 改變的那個 cycle，這個 job 所有寫入 burst 的 response 都已經回來，completion 的也是 |
| `HW-CPL-3` | completion ring 滿的時候硬體停下等 FW，不覆寫還沒被讀走的 completion。 | `lz4_ctrl` | 測試：bench 故意不推 `CPL_HEAD`。monitor 確認 ring 滿的時候沒有寫入 completion ring 的 burst |
| `HW-IRQ-1` | interrupt line 等於 (IRQ_STATUS & IRQ_ENABLE) != 0，其中 DONE 等於 CPL_TAIL != CPL_HEAD。 | `lz4_csr` | assertion：每個 cycle 拿 `irq` 與 register 的值比 |
| `HW-DATA-1` | COMPRESS 回 OK 時：length 不超過 limit，checksum 是 stream 的 CRC-32，stream 解開後與 frame 的 4096 B 相同。 | `lz4_enc`、`lz4_pack`、`lz4_crc32` | scoreboard：chunk 與 completion 逐 byte 比對 `hwref.job` |
| `HW-DATA-2` | DECOMPRESS 回 OK 時 frame 等於 stream 解開的 4096 B。回 BAD_STREAM 時 stream 確實有錯。 | `lz4_dec`、`lz4_crc32` | scoreboard：frame 與 completion 逐 byte 比對 `hwref.job`；壞的 stream 一律回 `BAD_STREAM` |
| `HW-STATE-1` | 除了 register，硬體不保留跨 job 的狀態。job 做到一半被 reset，重送同一個 descriptor 會得到相同結果。 | 全部，特別是 hash table 的 valid、兩個 FIFO、CRC | 同一個 job 接在不同的 job 後面、接在 reset 後面各做一次，結果相同 |
| `HW-RST-1` | soft reset：進行中的 bus burst 做完就停，JOB_HEAD、JOB_TAIL、CPL_TAIL、CPL_HEAD、ERR_CODE、IRQ_STATUS 與 CTRL.ENABLE 清成 0，config register 與 IRQ_ENABLE 保留，然後 STATUS.BUSY 變 0。 | `lz4_ctrl`、`lz4_csr`、兩個 DMA | 在 job FSM 的每一個 state 注入 soft reset |

## 5. Block 切分

這一節全部是 **基準**。Block 的名字是建議的 module 名稱。

### 5.1 總覽

```
                 APB                                   irq
                  |                                     ^
            +-----v------+     start, desc      +-------+------+
            |  lz4_csr   |<-------------------->|   lz4_ctrl   |
            | registers  |  head/tail, halt     |   job FSM    |
            +------------+                      +---+------+---+
                                                    |      |
                             cmd (addr, beats)      |      |      cmd (addr, beats)
                         +--------------------------+      +--------------------------+
                         v                                                            v
   AXI AR/R  <--->  +----------+     +-----------------------------+     +----------+  <---> AXI AW/W/B
                    | lz4_rdma |---->|          datapath           |---->| lz4_wdma |
                    +----------+     |  pagebuf  enc  dec  pack    |     +----------+
                                     |  fifo x2  crc32             |
                                     +-----------------------------+
```

| Block | 功能 | 主要記憶體 |
|---|---|---|
| `lz4_csr` | APB slave、所有 register、設定檢查、halt 與 `ERR_CODE`、`irq` | 只有 flop |
| `lz4_ctrl` | Job 的 FSM：取 descriptor、檢查、啟動 datapath、決定 completion、soft reset 排空 | Descriptor 的 48 B register |
| `lz4_rdma` | AXI AR 與 R。收到一個命令（位址、beat 數）發一個 burst，把 beat 送進內部 stream，回報 `rresp` | 無 |
| `lz4_wdma` | AXI AW、W、B。收到命令後從內部 stream 取 beat 送出，回報 `bresp` | 無 |
| `lz4_pagebuf` | 4096 B 的 page buffer：COMPRESS 時放整個 page，DECOMPRESS 時放已經解出的 byte | 2 × 256 × 64 bit |
| `lz4_enc` | Encoder：找 match、產生 sequence。內含 `lz4_hash` | Hash table |
| `lz4_dec` | Decoder：解析 token 與長度、做四項檢查、複製 literal 與 match。內含 `lz4_unpack` 與 history register | History register |
| `lz4_pack` | 把每 cycle 1 到 8 個 byte 的輸出併成 64 bit 的 word，尾端補 0 | 無 |
| `lz4_unpack` | 把 64 bit 的 word 拆成 decoder 每 cycle 要的 1 到 8 個 byte | 無 |
| `lz4_fifo` | 兩個：IN（`lz4_rdma` 到 decoder）、OUT（`lz4_pack` 到 `lz4_wdma`），各 128 × 64 bit | 各 128 × 64 bit |
| `lz4_crc32` | CRC-32，每 cycle 最多 8 個 byte | 無 |

Block 之間的資料一律用同一種 stream 介面：`valid`、`ready`、`data[63:0]`、`bytes[3:0]`（1 到 8）、`last`。Byte 0 在 `data[7:0]`。

### 5.2 COMPRESS 的資料路徑

```
  frame                                                                         chunk[0..n-1]
    |                                                                                ^
    v                                                                                |
 lz4_rdma --64b--> lz4_pagebuf <--port A (ip), port B (cand)--> lz4_enc              |
                        |                                          |                 |
                        | RAW path                                 | 1..8 B/cycle    |
                        +------------------------------------> lz4_pack --> OUT fifo --> lz4_wdma
                                                                   |
                                                                   +--> lz4_crc32
```

1. `lz4_rdma` 用 8 個 burst 把 frame 讀進 page buffer。
2. `lz4_enc` 從 port A 讀目前位置、從 port B 讀候選位置，每 cycle 輸出 0 到 8 個 stream byte。
3. `lz4_pack` 併成 word 進 OUT FIFO。CRC 在 OUT FIFO 的入口計算，只算 stream 的 byte，不算補的 0。
4. OUT FIFO 累積 64 個 word，`lz4_ctrl` 就對 `lz4_wdma` 下一個寫 chunk 的命令。Encoder 結束時 `lz4_pack` 把最後一個 chunk 補 0 到 512 B。
5. Stream 超過上限時走 RAW 或 INCOMPRESSIBLE（第 7.3 節）。RAW 的資料從 page buffer 直接進 `lz4_pack`。

### 5.3 DECOMPRESS 的資料路徑

```
  chunk[0..n-1]                                                                     frame
    |                                                                                 ^
    v                                                                                 |
 lz4_rdma --> IN fifo --> lz4_unpack --> lz4_dec --1..8 B/cycle--> lz4_pack --> OUT fifo --> lz4_wdma
                 |                        ^   |
                 +--> lz4_crc32           |   +--> lz4_pagebuf (write)
                                          +------- lz4_pagebuf (read, offset >= 24)
                                          +------- history register (offset < 24)
```

1. IN FIFO 有 64 個 word 的空位時，`lz4_ctrl` 對 `lz4_rdma` 下一個讀 chunk 的命令。
2. CRC 在 IN FIFO 的出口計算，只算前 `comp_len` 個 byte。
3. `lz4_dec` 的輸出同時寫進 page buffer 與 `lz4_pack`。
4. OUT FIFO 累積 64 個 word 就寫 frame 的下一個八分之一。
5. Descriptor 帶 RAW flag 時不經過 decoder：IN FIFO 的 word 直接進 OUT FIFO，CRC 算全部 4096 B。

### 5.4 記憶體

| 記憶體 | 大小 | bit 數 | 需要的 port |
|---|---|---|---|
| page buffer，even bank | 256 × 64 bit | 16384 | 兩個 port，各自可讀可寫，寫入有 byte enable |
| page buffer，odd bank | 256 × 64 bit | 16384 | 同上 |
| hash table 的位置 | 1024 × 12 bit | 12288 | 一個讀 port，一個寫 port |
| hash table 的 valid | 1024 個 flop | 1024 | 一個 cycle 全部清成 0 |
| IN FIFO | 128 × 64 bit | 8192 | 一個讀 port，一個寫 port |
| OUT FIFO | 128 × 64 bit | 8192 | 同上 |
| decoder 的 history | 24 × 8 bit | 192 | flop |
| **合計** |  | 62656 |  |

**Page buffer 分成偶數與奇數兩個 bank。** Encoder 每 cycle 要從任意 byte 位置讀 8 個連續的 byte，這個視窗會橫跨兩個相鄰的 word。把 word `w` 放在 bank `w & 1` 的位址 `w >> 1`，相鄰的兩個 word 就一定在不同的 bank，每個 bank 用一個 port 就能讀到。兩個 bank 各有兩個 port，所以同一個 cycle 可以讀兩個不對齊的視窗：一個在目前位置，一個在候選位置。寫入需要 byte write enable，因為 decoder 的輸出不對齊 word。

**Hash table 的 valid bit 用 flop，不放進 RAM。** 每個 job 開始時必須在一個 cycle 內全部清成 0。這是 HW-STATE-1 的要求，也是輸出與 reference model 一致的必要條件：上一個 page 留下的 entry 會讓 encoder 找到不同的候選位置。Entry 本身存 12 bit 的位置，不必清。

**FIFO 深度 128 個 word。** 兩個 burst 的量：一個 burst 正在傳的時候，另一側還能再累積一個。

| 編號 | 等級 | 要求 |
|---|---|---|
| JOB-5 | 必須 | 每個 job 開始時，hash table 的 valid bit、兩個 FIFO、packer、CRC、所有位置計數器都回到初始值。任何 job 的結果不受之前的 job 影響（HW-STATE-1） |

## 6. 控制流程

### 6.1 Job FSM

`lz4_ctrl` 的狀態。**基準**，但每個狀態的進出條件對應的外部行為是 **必須**。

| 狀態 | 做什麼 | 離開的條件與去向 |
|---|---|---|
| IDLE | `BUSY` 為 0 | `ENABLE` 為 1、沒有 halt、`JOB_HEAD != JOB_TAIL`：到 FETCH |
| FETCH | 讀 descriptor，6 beat | 沒有 bus error：`JOB_HEAD` 前進，到 CHECK。有 bus error：halt，代碼 RING_BUS_ERROR，`JOB_HEAD` 不動，到 HALTED |
| CHECK | 五項檢查；清 valid bit、FIFO、CRC、計數器 | 不通過：到 POST，status BAD_DESC。COMPRESS：到 C_LOAD。DECOMPRESS：到 D_RUN |
| C_LOAD | 讀 frame 進 page buffer，8 個 burst | 讀完：到 C_ENCODE |
| C_ENCODE | Encoder 執行，stream 邊產生邊寫 chunk | 正常結束：到 C_DRAIN。Stream 超過上限且 `limit` 為 4096：到 C_RAW。超過上限且 `limit` 小於 4096：等進行中的 burst 結束後到 POST，status INCOMPRESSIBLE |
| C_RAW | 等進行中的 burst 結束，清 packer、FIFO、CRC，把 page buffer 依序寫到 `chunk[0..7]` | 寫完：到 POST，status OK，flags RAW |
| C_DRAIN | 最後一個 chunk 補 0 後寫出 | Response 回來：到 POST，status OK |
| D_RUN | 讀 chunk、decode、寫 frame | Decoder 結束或檢查失敗：到 D_DRAIN |
| D_DRAIN | 成功：把剩下的 word 寫完。失敗：等進行中的 burst 結束，不再發新的 | 到 POST，status OK 或 BAD_STREAM |
| POST | 等 completion ring 有空位，寫 2 beat，等 response | 沒有 bus error：`CPL_TAIL` 前進，到 IDLE。有 bus error：halt，代碼 RING_BUS_ERROR，`CPL_TAIL` 不動，到 HALTED |
| HALTED | 不動 | 只有 soft reset 能離開 |
| RST_DRAIN | 見第 6.5 節 | 排空完成：到 IDLE |

Halt 可能在任何狀態由 `lz4_csr` 觸發，例如 FW 寫了超出範圍的 `JOB_TAIL`。這時 **必須** 把正在做的 job 做完並寫出 completion，然後才停在 HALTED。只有 FETCH 與 POST 自己的 bus error 會讓 job 沒有 completion。

POST 等待空位的時候如果 FW 一直不推進 `CPL_HEAD`，硬體就一直等。這不是錯誤狀態，soft reset 可以解開。

### 6.2 Descriptor 的檢查

五項檢查有固定的順序：opcode、count、chunk 編號的範圍、frame 的範圍、長度。第一個不通過的決定 `aux`，之後的不再檢查。**必須**。精確的條件就是這段 model：

```python
def check(d, regs):
    """The checks the hardware makes before it touches a frame or a chunk, in this order. Returns a bad_desc code or 0."""
    n = d['count']
    if d['opcode'] not in (OP.COMPRESS, OP.DECOMPRESS):
        return BD.OPCODE
    if not 1 <= n <= SLOTS:
        return BD.COUNT
    if any(c >= regs.pool_chunks for c in d['chunk'][:n]):
        return BD.CHUNK_RANGE
    if d['frame_pa'] % PAGE or not regs.frame_base <= d['frame_pa'] < regs.frame_base + regs.frame_count * PAGE:
        return BD.FRAME_RANGE
    room = min(PAGE, n * CHUNK)
    if d['opcode'] == OP.COMPRESS:
        if not 0 < d['limit'] <= room:
            return BD.LENGTH
    elif not 0 < d['comp_len'] <= room or (d['flags'] & FL.RAW and d['comp_len'] != PAGE):
        return BD.LENGTH
    return 0
```

每個代碼都有對應的 job vector，包含「前一項也錯時回報的是前一項」的情況：

| `aux` | 個數 | 名稱，前面都加 `bad_desc_` |
|---|---|---|
| `OPCODE` | 3 | `opcode_0`、`opcode_3`、`opcode_255` |
| `COUNT` | 3 | `count_0`、`count_9`、`count_before_chunk` |
| `CHUNK_RANGE` | 3 | `chunk_first_outside`、`chunk_max`、`chunk_before_frame` |
| `FRAME_RANGE` | 5 | `frame_unaligned`、`frame_below`、`frame_above`、`frame_in_pool`、`frame_before_length` |
| `LENGTH` | 7 | `limit_0`、`limit_over_chunks`、`limit_4097`、`comp_len_0`、`comp_len_over_chunks`、`comp_len_4097`、`raw_short` |

BAD_DESC 的 completion：`status` 為 BAD_DESC，`aux` 為上表的代碼，`tag` 照抄，其他欄位為 0。硬體沒有讀寫任何 chunk 或 frame。

### 6.3 Halt

| 代碼 | 觸發的條件 | 當時的 job |
|---|---|---|
| BAD_RING_CFG | `ENABLE` 從 0 變 1 時設定檢查不通過 | 沒有 job |
| RING_BUS_ERROR | 讀 descriptor 或寫 completion 時 bus error | 這個 job 沒有 completion，FW 在 reset 之後重送 |
| BAD_INDEX | FW 寫了超出範圍的 `JOB_TAIL` 或 `CPL_HEAD` | 做完並寫出 completion |

### 6.4 資料的 bus error

讀寫 chunk 或 frame 時的 bus error 是介面規格的未決事項 O8。這一版 RTL 照提案 P2 做，**假設**：

| 編號 | 要求 |
|---|---|
| JOB-6 | 出錯的 burst 照協定完成。之後不再發新的資料 burst |
| JOB-7 | Completion 的 `status` 為 BUS_ERROR，`tag` 照抄，其他欄位為 0 |
| JOB-8 | 不 halt。下一個 job 正常執行 |
| JOB-9 | 目的地的內容視為未定義：COMPRESS 是 descriptor 列出的 chunk，DECOMPRESS 是 frame |

### 6.5 Reset

| 編號 | 等級 | 要求 |
|---|---|---|
| RST-1 | 必須 | `rst_n` 之後所有 register 是第 4.1 節的 reset 值，`irq` 為 0，bus 上沒有任何 valid |
| RST-2 | 必須 | Soft reset 不可以違反 AXI 協定：已經發出的 AR 要把所有 R beat 收完，已經發出的 AW 要把所有 W beat 送完並等到 B |
| RST-3 | 必須 | Soft reset 排空時補送的 write beat `wstrb` 為 0，不再改變記憶體。收到的 read beat 丟棄 |
| RST-4 | 必須 | 排空期間 `BUSY` 為 1。排空完成後 `JOB_HEAD`、`JOB_TAIL`、`CPL_TAIL`、`CPL_HEAD`、`ERR_CODE`、`CTRL` 為 0，`HALTED` 與 `ERROR` 為 0，`BUSY` 為 0（HW-RST-1） |
| RST-5 | 必須 | Soft reset 不改變 base、size、`IRQ_ENABLE`。排空期間寫 `CTRL.ENABLE` 沒有作用 |
| RST-6 | 必須 | 被 soft reset 打斷的 job 沒有 completion。它已經寫過的 chunk 或 frame 內容視為未定義 |

Soft reset 之後內部記憶體的內容不必清。JOB-5 保證下一個 job 不會看到它們。

## 7. 核心演算法

### 7.1 Stream 的格式，從範例看

Stream 是標準的 LZ4 block，沒有 frame header。它是一串 sequence，每個 sequence 說兩件事：先照抄幾個 byte（literal），再從前面已經出現的地方複製幾個 byte（match）。

範例的第一個 sequence 是 `F0 09`、24 個 literal、`0C 00`。

| Byte | 值 | 意思 |
|---|---|---|
| Token | 0xF0 | 高 4 bit 是 15：literal 長度至少 15，後面還有長度 byte。低 4 bit 是 0：match 長度 0 + 4 = 4 |
| Literal 長度 byte | 0x09 | 15 + 9 = 24 個 literal |
| Literal | 24 個 byte | 照抄 page 的位置 0 到 23 |
| Offset | 0x0C 0x00 | Little endian 的 12：match 從目前位置往回 12 個 byte 開始 |

第二個 sequence `11 01 1C 00` 更短：token 0x11 是 1 個 literal、match 長度 1 + 4 = 5，literal 是 0x01，offset 28。

倒數第二個 sequence `1F 00 01 00 FF FF 7D` 有很長的 match：token 的低 4 bit 是 15，offset 後面跟著長度 byte 0xFF、0xFF、0x7D，match 長度是 15 + 255 + 255 + 125 + 4 = 654。Offset 是 1，表示重複前一個 byte 654 次：match 可以與它自己正在產生的輸出重疊。

最後一個 sequence `50 00 00 00 00 00` 只有 token 與 5 個 literal，沒有 offset。Block 一定以這種只有 literal 的 sequence 結束。

通用的格式：

| 欄位 | 長度 | 出現的條件 | 內容 |
|---|---|---|---|
| Token | 1 B | 一定有 | 高 4 bit：literal 長度，15 表示還有長度 byte。低 4 bit：match 長度減 4，15 表示還有長度 byte |
| Literal 長度 byte | 0 個以上 | Token 高 4 bit 為 15 | 每個 byte 加進長度，值是 255 就繼續，不是 255 就結束 |
| Literal | 0 個以上 | | |
| Offset | 2 B | 最後一個 sequence 沒有 | Little endian，1 到 65535。在這顆硬體裡不會超過 4095 |
| Match 長度 byte | 0 個以上 | Token 低 4 bit 為 15 | 同 literal 長度 byte |

長度剛好是 15 加 255 的倍數時，最後要有一個值為 0 的 byte。

```python
def put_length(out, n):
    """The extra bytes behind a 4-bit length field that holds 15: 255 as long as 255 or more is left, then the rest."""
    n -= 15
    while n >= 255:
        out.append(255)
        n -= 255
    out.append(n)
```

```python
def put_sequence(out, literals, match_len, offset):
    """One LZ4 sequence. match_len 0 means the last sequence of the block: literals only."""
    ll = len(literals)
    ml = match_len - MINMATCH if match_len else 0
    out.append((min(ll, 15) << 4) | min(ml, 15))             # token
    if ll >= 15:
        put_length(out, ll)
    out += literals
    if match_len:
        out += offset.to_bytes(2, 'little')
        if ml >= 15:
            put_length(out, ml)
```

Encoder 另外守三條 LZ4 的規定：match 至少 4 B；page 的最後 12 B 不開始新的 match，所以最後一個搜尋位置是 4084；最後 5 B 一定是 literal，所以 match 最遠延伸到位置 4090。

### 7.2 Encoder

| 編號 | 等級 | 要求 |
|---|---|---|
| ENC-1 | 必須 | 對任何 4096 B 的 page，寫出的 stream 與 `lz4core.encode(page, HASH_BITS)` 逐 byte 相同 |
| ENC-2 | 必須 | Stream 是合法的 LZ4 block，`lz4core.decode` 與 liblz4 都能解回原本的 page |

ENC-1 比 ENC-2 嚴格，選它是為了驗證：test bench 直接比對 byte，不必判斷「另一種合法的壓法」算不算對。代價是 RTL 的 pipeline 必須重現下面這段演算法的每一個決定。

```python
def hash4(v, bits=HASH_BITS):
    """XOR of the 32-bit value cut into fields of `bits` bits, lowest field first."""
    h = 0
    while v:
        h ^= v & ((1 << bits) - 1)
        v >>= bits
    return h
```

```python
def encode(page, hash_bits=HASH_BITS):
    """Compress one page into an LZ4 block."""
    page = bytes(page)
    n = len(page)
    out, seqs = bytearray(), []
    table = [None] * (1 << hash_bits)            # hash -> last position seen with it; None: nothing yet in this page
    word = [int.from_bytes(page[i:i + 4], 'little') for i in range(max(0, n - 3))]
    last_start = n - MFLIMIT                     # last position where a match may start
    match_end = n - LASTLITERALS                 # a match stops before this position
    anchor = 0                                   # first byte not yet written to the stream
    ip = 0                                       # position being looked at
    searched = 0
    while ip <= last_start:
        h = hash4(word[ip], hash_bits)
        cand = table[h]                          # read the entry, then replace it: every position looked at goes in
        table[h] = ip
        searched += 1
        if cand is None or word[cand] != word[ip]:
            ip += 1                              # no match here; this byte becomes a literal
            continue
        length = MINMATCH
        while ip + length < match_end and page[cand + length] == page[ip + length]:
            length += 1
        put_sequence(out, page[anchor:ip], length, ip - cand)
        seqs.append((ip - anchor, length, ip - cand))
        ip += length                             # positions inside the match are not put into the table
        anchor = ip
    put_sequence(out, page[anchor:], 0, 0)
    seqs.append((n - anchor, 0, 0))
    return Encoded(bytes(out), seqs, searched)
```

要點：

- 一張 hash table，每個 entry 記一個位置。每個 job 開始時整張是空的。
- 每個搜尋的位置都先讀 entry 再把自己寫進去，不管有沒有 match。
- 讀到的候選位置只要 4 個 byte 相同就採用，不比較其他候選。
- Match 往後延伸到不相同或到位置 4091 為止。不往前延伸。
- Match 內部的位置不寫進 table。Match 結束後從下一個位置繼續搜尋。
- `HASH_BITS` 為 10 時，hash 是 32 bit 的值切成 `[9:0]`、`[19:10]`、`[29:20]`、`[31:30]` 四段做 XOR。

**基準的 pipeline，每 cycle 搜尋一個位置：**

| Stage | 做什麼 |
|---|---|
| H | 從 page buffer port A 取位置 `q` 開始的 8 個 byte，算前 4 個 byte 的 hash，送出 hash table 的讀位址 |
| C | Hash table 輸出候選位置 `cand`，經過 forwarding 修正。用 `cand` 當位址從 page buffer port B 讀 8 個 byte |
| M | 比較兩個 8 B 的視窗。把 `q` 寫進 hash table。前 4 個 byte 相同且 entry 有效就是 match |

三個位置同時在 pipeline 裡，後面的位置讀 table 時，前面的位置還沒寫進去。Reference model 是循序的，所以 **必須** 用 forwarding 補回來：

```
cand(q) = q-1            if hash(q) == hash(q-1)
        = q-2            else if hash(q) == hash(q-2)
        = table[hash(q)] otherwise
```

Forward 來的候選視為有效。RAM 在同一個位址同時讀寫時的輸出不可以被使用，上面的 forwarding 已經涵蓋這個情況。

位置 `q` 在 stage M 判定為 match 時，pipeline 裡的 `q+1` 與 `q+2` 作廢，**必須** 不寫進 hash table：在 model 裡它們位於 match 內部。Pipeline 切得更深時，規則相同：從每一個還沒寫入的較早位置 forward，match 之後作廢所有較晚的位置。

剛開始整合時可以先用不做 pipeline 的 FSM，每個位置花 3 個 cycle，不需要 forwarding，輸出一樣，之後再換成 pipeline。

**Match 之後的處理：**

1. Stage M 的 8 B 比較已經知道前 8 個 byte 裡有幾個相同。少於 8 個就確定了長度。
2. 8 個都相同時進入 EXTEND：兩個 port 各往後讀 8 B 比較，每 cycle 8 B，直到出現不同的 byte 或到位置 4091。
3. 輸出 token 與 literal 長度 byte。
4. 從 port A 讀 literal，每 cycle 8 B。
5. 輸出 offset 與 match 長度 byte。
6. 從 `ip + length` 重新填滿 pipeline，3 個 cycle。

搜尋位置超過 4084 之後，輸出最後一個 sequence：位置 `anchor` 到 4095 全部當 literal。

Cycle 數的估計方式在 `lz4core.encode_cycles`：每個搜尋位置 1 cycle；每個 match 固定 6 cycle，加上每 8 B match 1 cycle，前面有 literal 時再加 1 cycle 與每 8 B literal 1 cycle。範例的 page 是 4032 cycle。

### 7.3 COMPRESS 的結果

設 `cap` = min(`limit`, 4095)，`L` 是完整 stream 的長度。**必須**：

| 情況 | Completion | Chunk 的內容 |
|---|---|---|
| `L` ≤ `cap` | status OK，`length` = `L`，`checksum` = stream 的 CRC，flags 0 | 前 ceil(`L` / 512) 個 chunk 放 stream，最後一個的尾端未定義，基準補 0 |
| `L` > `cap` 且 `limit` 是 4096 | status OK，`length` = 4096，`checksum` = page 的 CRC，flags RAW | `chunk[0..7]` 放原本的 page |
| `L` > `cap` 且 `limit` 小於 4096 | status INCOMPRESSIBLE，`tag` 照抄，其他欄位 0 | Descriptor 列出的 chunk 內容未定義 |

精確的定義：

```python
def compress(d, regs, mem):
    listed = [(regs.chunk_pa(c), CHUNK) for c in d['chunk'][:d['count']]]
    try:
        page = b''.join(mem.read(d['frame_pa'] + o, CHUNK) for o in range(0, PAGE, CHUNK))
        stream, flags = C.encode(page).stream, 0
        if len(stream) >= PAGE or len(stream) > d['limit']:
            if d['limit'] < PAGE:
                return _done(d, ST.INCOMPRESSIBLE, undefined=listed)
            stream, flags = page, FL.RAW
        used = ceil(len(stream) / CHUNK)
        for i in range(used):                    # every chunk is written whole; behind the stream come zeros
            mem.write(listed[i][0], stream[i * CHUNK:(i + 1) * CHUNK].ljust(CHUNK, b'\0'))
    except BusError:
        return _done(d, ST.BUS_ERROR, undefined=listed)
    defined = [(listed[i][0], min(CHUNK, len(stream) - i * CHUNK)) for i in range(used)]
    tail = len(stream) % CHUNK
    return _done(d, ST.OK, len(stream), C.crc32(stream), flags, stream=stream, defined=defined,
                 undefined=[(listed[used - 1][0] + tail, CHUNK - tail)] if tail else [])
```

| 編號 | 等級 | 要求 |
|---|---|---|
| ENC-3 | 必須 | 不寫 `chunk[i]`，`i` ≥ `count`。成功時也不寫 `i` ≥ ceil(`length` / 512) 的 chunk |
| ENC-4 | 必須 | 每個用到的 chunk 都是一個完整的 512 B burst。最後一個 chunk 裡 stream 之後的 byte 不算進 CRC，在介面上是未定義：FW 不可以依賴，scoreboard 不比對 |
| ENC-7 | 基準 | 最後一個 chunk 裡 stream 之後的 byte 補 0，不把上一個 job 的資料留在裡面 |
| ENC-5 | 基準 | Encoder 邊產生邊寫 chunk，不等整個 page 壓完。Stream 的 byte 數一超過 `cap` 就停止 encoder |
| ENC-6 | 必須 | `limit` 是 4096 而且 stream 剛好 4096 B 以上時走 RAW，不存一個不比原本小的 stream |

ENC-5 的後果是：改走 RAW 時，前幾個 chunk 可能已經被寫過 stream，之後再被 page 的內容蓋掉。這是允許的，因為那些 chunk 本來就授權給這個 job。走 INCOMPRESSIBLE 時它們留著寫到一半的 stream，FW 照規則把這些 chunk 還回 bitmap，不讀內容。

### 7.4 Decoder

| 編號 | 等級 | 要求 |
|---|---|---|
| DEC-1 | 必須 | 對任何 byte 串與 `comp_len`，成功與否、成功時 frame 的 4096 B，都與 `lz4core.decode` 相同 |
| DEC-2 | 必須 | 任何輸入都不會讓硬體卡住、讀寫授權範圍以外的位址、或寫超過 4096 B。輸入可能是任意的垃圾 |
| DEC-3 | 必須 | 四項檢查任何一項失敗，或 CRC 不符，status 是 BAD_STREAM，`tag` 照抄，其他欄位 0 |

```python
def decode(stream, size=PAGE):
    """Open one LZ4 block that has to give exactly `size` bytes. Stops at the first check that fails."""
    s = bytes(stream)
    n = len(s)
    out, seqs = bytearray(), []
    i = 0                                        # next stream byte

    def fail(status):
        return Decoded(None, status, i, len(out), seqs)

    while True:
        if i >= n:
            return fail(UNDERRUN)
        token = s[i]
        i += 1
        ll = token >> 4                          # literal length
        if ll == 15:
            while True:
                if i >= n:
                    return fail(UNDERRUN)
                b = s[i]
                i += 1
                ll += b
                if len(out) + ll > size:         # checked at every byte, so the counter never needs more than 13 bits
                    return fail(OVERFLOW)
                if b != 255:
                    break
        if len(out) + ll > size:
            return fail(OVERFLOW)
        if i + ll > n:
            return fail(UNDERRUN)
        out += s[i:i + ll]
        i += ll
        if i == n:                               # the block ends behind the literals of its last sequence
            seqs.append((ll, 0, 0))
            break
        if i + 2 > n:
            return fail(UNDERRUN)
        offset = s[i] | (s[i + 1] << 8)
        i += 2
        if offset == 0 or offset > len(out):
            return fail(OFFSET)
        ml = (token & 15) + MINMATCH             # match length
        if token & 15 == 15:
            while True:
                if i >= n:
                    return fail(UNDERRUN)
                b = s[i]
                i += 1
                ml += b
                if len(out) + ml > size:
                    return fail(OVERFLOW)
                if b != 255:
                    break
        if len(out) + ml > size:
            return fail(OVERFLOW)
        for _ in range(ml):                      # byte by byte: the match may overlap what it is producing
            out.append(out[len(out) - offset])
        seqs.append((ll, ml, offset))
    if len(out) != size:
        return fail(SHORT)
    return Decoded(bytes(out), OK, i, len(out), seqs)
```

四項檢查：

| 檢查 | 條件 | 檢查的時機 |
|---|---|---|
| UNDERRUN | 還需要 stream 的 byte，但已經到 `comp_len` | 讀 token、每個長度 byte、literal、offset 之前 |
| OVERFLOW | 已輸出的 byte 數加上目前的長度超過 4096 | 每加一個長度 byte 之後，以及開始複製之前 |
| OFFSET | Offset 是 0，或大於已輸出的 byte 數 | 讀完 offset 之後 |
| SHORT | Stream 正常結束，輸出不到 4096 B | Block 結束時 |

OVERFLOW 在每個長度 byte 之後都檢查，所以長度計數器只需要 13 bit，不會被一長串 0xFF 灌爆。

Block 的結束只有一種：剛複製完一個 sequence 的 literal，而且 stream 剛好用完。讀 token 時 stream 已經用完算 UNDERRUN。

Decoder 不檢查 encoder 那三條結尾的規定。一個 match 一路複製到 page 的最後一個 byte、最後一個 sequence 沒有 literal 的 stream，只要輸出剛好 4096 B 就算成功。liblz4 的 decoder 會拒絕這種 stream；這顆硬體接受，因為多做這些檢查不會讓任何正確的 stream 變得更安全，CRC 已經負責確認內容。Vector `dec_offset_4092` 與 `dec_match_to_end` 就是這種情況。

目前 completion 不區分四種檢查與 CRC 不符。第 12 節的提案 P3 建議把代碼放進 `aux`。

**基準的狀態機：**

| 狀態 | 做什麼 | 下一個狀態 |
|---|---|---|
| TOKEN | 讀 1 B。`ll` = 高 4 bit，`ml` = 低 4 bit + 4 | `ll` 是 15：LIT_EXT。`ll` 大於 0：LIT_COPY。否則 OFFSET 或結束 |
| LIT_EXT | 讀 1 B 加進 `ll`，檢查 OVERFLOW | 讀到的不是 255：LIT_COPY |
| LIT_COPY | 每 cycle 從 stream 搬最多 8 B 到輸出 | 搬完且 stream 用完：結束。否則 OFFSET |
| OFFSET | 讀 2 B，檢查 OFFSET | Token 低 4 bit 是 15：MATCH_EXT。否則 MATCH_COPY |
| MATCH_EXT | 讀 1 B 加進 `ml`，檢查 OVERFLOW | 讀到的不是 255：MATCH_COPY |
| MATCH_COPY | 每 cycle 複製最多 8 B | 複製完：TOKEN |

**Match 的複製分兩種來源。** 輸出寫進 page buffer 之後要過幾個 cycle 才讀得回來。Offset 很小時，要複製的 byte 可能才剛產生，還沒進 page buffer。所以 decoder 另外用一個 register 保存最後 24 個輸出的 byte：

- Offset 小於 24：從 history register 複製。規則是 `out[opos + j] = out[opos − offset + (j mod offset)]`，一個 cycle 仍然可以產生 8 B，即使 offset 是 1。這條路徑多 1 個 cycle。
- Offset 大於等於 24：讀 page buffer。

為什麼是 24：下一個 beat 要讀的 byte 最遠到 `opos + 15 − offset`，目前正在寫的 word 從 `opos − (opos mod 8)` 開始。只要 offset 大於 15 + (`opos` mod 8)，讀的位置就落在比寫的位置更低的 word，不會讀到還沒寫進去的資料。`opos` mod 8 最大是 7，所以 offset 至少 23 就夠，取 24 讓它是 8 的倍數。

Cycle 數的估計在 `lz4core.decode_cycles`：每個 sequence 1 cycle 讀 token，加長度 byte 的個數，加每 8 B literal 1 cycle；有 match 時再加 2 cycle、長度 byte 的個數、每 8 B match 1 cycle，offset 小於 24 時多 1 cycle。範例的 stream 是 1947 cycle。

### 7.5 DECOMPRESS 的結果

```python
def decompress(d, regs, mem):
    frame = [(d['frame_pa'], PAGE)]
    length = d['comp_len']
    try:
        stream = b''.join(mem.read(regs.chunk_pa(c), CHUNK) for c in d['chunk'][:ceil(length / CHUNK)])[:length]
        page = None
        if C.crc32(stream) == d['checksum']:
            page = stream if d['flags'] & FL.RAW else C.decode(stream).page
        if page is None:
            return _done(d, ST.BAD_STREAM, stream=stream, undefined=frame)
        for o in range(0, PAGE, CHUNK):
            mem.write(d['frame_pa'] + o, page[o:o + CHUNK])
    except BusError:
        return _done(d, ST.BUS_ERROR, undefined=frame)
    return _done(d, ST.OK, PAGE, d['checksum'], d['flags'] & FL.RAW, stream=stream, defined=frame)
```

| 編號 | 等級 | 要求 |
|---|---|---|
| DEC-4 | 必須 | 只讀 `chunk[0]` 到 `chunk[ceil(comp_len / 512) − 1]`。每個 chunk 讀整個 512 B，`comp_len` 之後的 byte 忽略，不進 decoder 也不進 CRC |
| DEC-5 | 必須 | CRC 算的是讀進來的前 `comp_len` 個 byte，與 descriptor 的 `checksum` 比對 |
| DEC-6 | 必須 | 成功的 completion：status OK，`length` 4096，`checksum` 與 RAW flag 照抄 descriptor |
| DEC-7 | 必須 | Descriptor 帶 RAW flag 時 `comp_len` 是 4096，8 個 chunk 的內容直接寫到 frame，CRC 算全部 4096 B |
| DEC-8 | 必須 | Status 不是 OK 時 frame 的內容未定義，FW 不可以把它對應給任何人（FW-MM 規則）。硬體不寫 frame 以外的位址 |

**什麼時候寫 frame，兩種做法：**

| | Store-behind（基準） | Decode-then-store |
|---|---|---|
| 做法 | 解出來的 byte 立刻排隊寫 frame | 整個 page 留在 page buffer，CRC 與檢查都通過才寫 |
| 範例 job | 2033 cycle | 2488 cycle |
| BAD_STREAM 時的 frame | 可能已經寫了一部分 | 完全沒被寫 |
| 額外的硬體 | 無 | 無，page buffer 已經有整個 page |

基準選 store-behind，因為 fault 的延遲是這個設計最緊的預算，而 BAD_STREAM 之後那個 frame 本來就不能用。`hwref.job` 與 `hostsim` 的 model 在 BAD_STREAM 時不寫 frame，並把 frame 標成未定義；test bench 對未定義的範圍不比對，所以兩種做法都能通過。要選哪一種列在第 12 節。

### 7.6 CRC-32

與 zlib、Ethernet 相同。**必須**。

| 項目 | 值 |
|---|---|
| 多項式 | 0x04C11DB7，反射後 0xEDB88320 |
| 初始值 | 0xFFFFFFFF |
| 輸入與輸出 | 都反射，也就是每個 byte 從 bit 0 開始處理 |
| 最後 XOR | 0xFFFFFFFF |
| 檢查值 | 9 個 byte 的文字 123456789 得到 0xCBF43926 |

基準做法是每 cycle 處理 8 B 的組合邏輯，最後一個 word 不滿 8 B 時依 `bytes` 選 1 到 7 B 的版本。範例 stream 的 CRC 是 0xF7AD14BD。

## 8. 每種結果之後，記憶體與 completion 的狀態

這張表是 scoreboard 的依據。「未定義」表示 test bench 不比對、FW 不可以依賴。沒有列出的記憶體一律不可以被改變。

| Status | `length` | `checksum` | `flags` | `aux` | 目的地 | 來源 |
|---|---|---|---|---|---|---|
| OK，COMPRESS | Stream 長度 | Stream 的 CRC | 0 | 0 | 用到的 chunk 前 `length` 個 byte 是 stream，最後一個 chunk 的尾端未定義；沒用到的 chunk 不變 | Frame 不變 |
| OK，COMPRESS，RAW | 4096 | Page 的 CRC | RAW | 0 | `chunk[0..7]` 是原本的 page | Frame 不變 |
| INCOMPRESSIBLE | 0 | 0 | 0 | 0 | 列出的 `count` 個 chunk 未定義 | Frame 不變 |
| OK，DECOMPRESS | 4096 | 照抄 descriptor | 照抄 RAW | 0 | Frame 是原本的 page | Chunk 不變 |
| BAD_STREAM | 0 | 0 | 0 | 0 | Frame 未定義 | Chunk 不變 |
| BAD_DESC | 0 | 0 | 0 | 代碼 | 沒有任何 access | 沒有任何 access |
| BUS_ERROR，提案 P2 | 0 | 0 | 0 | 0 | 未定義 | 不變 |

所有 completion 的 `tag` 都照抄 descriptor。

## 9. 效能估計

這一節的數字是用基準架構數 cycle 算出來的估計，不是量測。RTL 完成後要用模擬量到的數字取代，並回填 `sim/ifsim` 的時間假設（介面規格的未決事項 O2）。

### 9.1 計算用的 bus 模型

| 項目 | 值 |
|---|---|
| AR 到第一個 R beat | 3 cycle |
| 最後一個 W beat 到 B | 2 cycle |
| Burst | 64 beat，beat 之間沒有等待 |
| 讀 descriptor | 11 cycle |
| 寫 completion | 5 cycle |
| 讀整個 frame | 536 cycle |
| 寫最後一個 burst | 67 cycle |

Bus 上沒有其他 master 搶、slave 不插 wait state。實際系統只會更慢。

### 9.2 四組 page 的 cycle 數

每組 300 個 page，來源見第 10.1 節。每格是平均 / p50 / p99 / 最大。

| page 的來源 | sequence 數 | encoder core | decoder core | COMPRESS job | DECOMPRESS job | DECOMPRESS job，CRC 驗完才寫 frame |
|---|---|---|---|---|---|---|
| binaries（本機的執行檔） | 255 / 246 / 557 / 574 | 4653 / 4959 / 5725 / 6690 | 1584 / 1541 / 2925 / 3323 | 5277 / 5582 / 6344 / 7309 | 1670 / 1627 / 3011 / 3409 | 2125 / 2082 / 3466 / 3864 |
| heap（Python 程序自己的 heap） | 290 / 297 / 393 / 409 | 3048 / 2944 / 4211 / 4615 | 1634 / 1638 / 1996 / 2112 | 3667 / 3563 / 4830 / 5234 | 1720 / 1724 / 2082 / 2198 | 2175 / 2179 / 2537 / 2653 |
| synthetic（host simulation 的 workload） | 5 / 5 / 5 / 5 | 2493 / 2549 / 3975 / 4117 | 552 / 553 / 554 / 554 | 3112 / 3168 / 4594 / 4736 | 638 / 639 / 640 / 640 | 1093 / 1094 / 1095 / 1095 |
| text（Python 原始碼） | 330 / 337 / 408 / 416 | 4009 / 4105 / 5100 / 5415 | 1804 / 1835 / 2083 / 2110 | 4628 / 4724 / 5719 / 6034 | 1890 / 1921 / 2169 / 2196 | 2345 / 2376 / 2624 / 2651 |

### 9.3 換算成時間

Clock 頻率還沒決定（A2），下表用 200、400、800 MHz 三個值換算，單位 µs。

| page 的來源 | job | 200 MHz | 400 MHz | 800 MHz |
|---|---|---|---|---|
| binaries（本機的執行檔） | COMPRESS | 26.4 / 31.7 | 13.2 / 15.9 | 6.6 / 7.9 |
| binaries（本機的執行檔） | DECOMPRESS | 8.4 / 15.1 | 4.2 / 7.5 | 2.1 / 3.8 |
| heap（Python 程序自己的 heap） | COMPRESS | 18.3 / 24.1 | 9.2 / 12.1 | 4.6 / 6.0 |
| heap（Python 程序自己的 heap） | DECOMPRESS | 8.6 / 10.4 | 4.3 / 5.2 | 2.2 / 2.6 |
| synthetic（host simulation 的 workload） | COMPRESS | 15.6 / 23.0 | 7.8 / 11.5 | 3.9 / 5.7 |
| synthetic（host simulation 的 workload） | DECOMPRESS | 3.2 / 3.2 | 1.6 / 1.6 | 0.8 / 0.8 |
| text（Python 原始碼） | COMPRESS | 23.1 / 28.6 | 11.6 / 14.3 | 5.8 / 7.1 |
| text（Python 原始碼） | DECOMPRESS | 9.5 / 10.8 | 4.7 / 5.4 | 2.4 / 2.7 |

### 9.4 與 ifsim 假設的差距

`sim/ifsim` 目前的時間假設是 1 GHz、COMPRESS 4096 cycle、DECOMPRESS 1024 cycle。對照上面的估計：

| 項目 | ifsim 假設 | 這份估計，heap page 平均 | 這份估計，heap page 最大 |
|---|---|---|---|
| COMPRESS job | 4096 cycle | 3667 cycle | 5234 cycle |
| DECOMPRESS job | 1024 cycle | 1720 cycle | 2198 cycle |
| Clock | 1 GHz | 未定，SoC 上這類 IP 常見的範圍低很多 | |

結論：

1. DECOMPRESS 的 cycle 數比 ifsim 的假設多，heap 與文字 page 大約是 1.7 到 1.9 倍。再加上 clock 很可能低於 1 GHz，page fault 的硬體時間會是原假設的數倍。Fault 的延遲預算要用這份估計重算。
2. COMPRESS 的 cycle 數在 heap page 上平均略低於假設，在文字與執行檔 page 上平均高出 13% 到 29%，最大值到 7309 cycle。壓得越小的 page 越快，因為 match 內部的位置不必搜尋。
3. DECOMPRESS 的時間有一大部分是固定的搬運：讀 chunk 與寫 8 個 frame burst。Decoder 核心再快，整個 job 也不會低於大約 600 cycle。
4. 兩個不改變輸出的加速方向留到 RTL 有量測之後再決定：frame 還在讀的時候就開始搜尋；decoder 把 token 與上一個 sequence 的複製重疊。

## 10. 參數選擇的依據

### 10.1 量測用的 page

四組，每組 300 個 4096 B 的 page。

| 組 | 怎麼取得 | 代表什麼 | 限制 |
|---|---|---|---|
| Heap | 執行量測的 Python 程序自己的記憶體，在活著的物件附近取整個 page | RW 的資料 page | 每次執行內容不同，數字會有 1% 左右的浮動。不是目標系統的資料 |
| 文字 | Python 標準函式庫的原始碼切成 page | 高度可壓縮的資料 | 目標系統上很少有這種 page |
| 執行檔 | 下表的檔案切成 page | RO 的 code page | 是這台開發機的執行檔，不是目標 SoC 的 firmware |
| 合成 | `sim/lz4sim` 的 workload 產生器 | 驅動 simulator 用的資料 | 見下面的說明 |

執行檔組用到的檔案：

| 檔案 | 大小 B | SHA-256 的前 16 位 |
|---|---|---|
| `/bin/zsh` | 1361216 | `1f473d234dd65157` |
| `/usr/bin/vim` | 5651232 | `0e7f7d3ff46a0ab7` |
| `/usr/bin/ssh` | 1555472 | `470f812f6e71ee4c` |
| `/bin/bash` | 1293840 | `fde343ee184953c1` |
| `/usr/bin/tar` | 275184 | `9ab7f0793033dc9d` |

合成 page 是 `sim/lz4sim` 用來驅動 simulator 的資料。它的重複方式太規則，下面會看到幾乎所有變體在它上面的結果相同，所以它不能用來比較 encoder 的設計，只能用來測流程。

### 10.2 各種變體的 stream 長度

每個 page 壓出來的平均 byte 數與平均 chunk 數，越小越好。第一列是這份規格採用的設計，最後兩列是 liblz4，當作軟體能做到的參考。

Heap：

| encoder | 平均 stream 長度 B | 佔 4096 B 的比例 | 平均用幾個 chunk | 超過 7 個 chunk 的 page |
|---|---|---|---|---|
| **硬體採用：1024 格，XOR hash** | 1291.4 | 31.5% | 3.17 | 0.0% |
| 256 格 | 1409.3 | 34.4% | 3.31 | 0.0% |
| 512 格 | 1305.9 | 31.9% | 3.21 | 0.0% |
| 2048 格 | 1284.1 | 31.3% | 3.17 | 0.0% |
| 4096 格 | 1284.1 | 31.4% | 3.17 | 0.0% |
| 乘法 hash，1024 格 | 1291.1 | 31.5% | 3.18 | 0.0% |
| 乘法 hash，4096 格 | 1278.4 | 31.2% | 3.16 | 0.0% |
| match 開頭後 2 個位置也放進 table | 1366.3 | 33.4% | 3.22 | 0.0% |
| match 結尾前 2 個位置也放進 table | 1289.3 | 31.5% | 3.17 | 0.0% |
| match 往回延伸 | 1284.2 | 31.4% | 3.17 | 0.0% |
| liblz4，預設 | 1243.7 | 30.4% | 3.11 | 0.0% |
| liblz4 HC，level 9 | 976.2 | 23.8% | 2.38 | 0.0% |

文字：

| encoder | 平均 stream 長度 B | 佔 4096 B 的比例 | 平均用幾個 chunk | 超過 7 個 chunk 的 page |
|---|---|---|---|---|
| **硬體採用：1024 格，XOR hash** | 2121.1 | 51.8% | 4.63 | 0.0% |
| 256 格 | 2528.3 | 61.7% | 5.45 | 0.7% |
| 512 格 | 2189.4 | 53.5% | 4.77 | 0.0% |
| 2048 格 | 2090.1 | 51.0% | 4.58 | 0.0% |
| 4096 格 | 2083.1 | 50.9% | 4.57 | 0.0% |
| 乘法 hash，1024 格 | 2112.3 | 51.6% | 4.62 | 0.0% |
| 乘法 hash，4096 格 | 2077.5 | 50.7% | 4.56 | 0.0% |
| match 開頭後 2 個位置也放進 table | 2101.3 | 51.3% | 4.60 | 0.0% |
| match 結尾前 2 個位置也放進 table | 2100.3 | 51.3% | 4.61 | 0.0% |
| match 往回延伸 | 2076.0 | 50.7% | 4.56 | 0.0% |
| liblz4，預設 | 2041.3 | 49.8% | 4.52 | 0.0% |
| liblz4 HC，level 9 | 1821.8 | 44.5% | 4.06 | 0.0% |

執行檔：

| encoder | 平均 stream 長度 B | 佔 4096 B 的比例 | 平均用幾個 chunk | 超過 7 個 chunk 的 page |
|---|---|---|---|---|
| **硬體採用：1024 格，XOR hash** | 3005.2 | 73.4% | 6.38 | 21.7% |
| 256 格 | 3221.7 | 78.7% | 6.86 | 47.3% |
| 512 格 | 3066.3 | 74.9% | 6.51 | 30.0% |
| 2048 格 | 2972.8 | 72.6% | 6.27 | 14.0% |
| 4096 格 | 2960.1 | 72.3% | 6.24 | 11.7% |
| 乘法 hash，1024 格 | 3002.2 | 73.3% | 6.37 | 21.0% |
| 乘法 hash，4096 格 | 2951.5 | 72.1% | 6.21 | 10.0% |
| match 開頭後 2 個位置也放進 table | 3004.4 | 73.3% | 6.37 | 18.7% |
| match 結尾前 2 個位置也放進 table | 2998.4 | 73.2% | 6.36 | 20.0% |
| match 往回延伸 | 2969.2 | 72.5% | 6.29 | 16.0% |
| liblz4，預設 | 2983.0 | 72.8% | 6.32 | 21.3% |
| liblz4 HC，level 9 | 2805.4 | 68.5% | 5.98 | 4.3% |

合成：

| encoder | 平均 stream 長度 B | 佔 4096 B 的比例 | 平均用幾個 chunk | 超過 7 個 chunk 的 page |
|---|---|---|---|---|
| **硬體採用：1024 格，XOR hash** | 1984.8 | 48.5% | 4.40 | 0.7% |
| 256 格 | 3977.7 | 97.1% | 7.77 | 96.7% |
| 512 格 | 1984.8 | 48.5% | 4.40 | 0.7% |
| 2048 格 | 1984.8 | 48.5% | 4.40 | 0.7% |
| 4096 格 | 1984.9 | 48.5% | 4.40 | 0.7% |
| 乘法 hash，1024 格 | 1984.8 | 48.5% | 4.40 | 0.7% |
| 乘法 hash，4096 格 | 1984.8 | 48.5% | 4.40 | 0.7% |
| match 開頭後 2 個位置也放進 table | 1984.8 | 48.5% | 4.40 | 0.7% |
| match 結尾前 2 個位置也放進 table | 1984.8 | 48.5% | 4.40 | 0.7% |
| match 往回延伸 | 1984.8 | 48.5% | 4.40 | 0.7% |
| liblz4，預設 | 2006.1 | 49.0% | 4.45 | 0.7% |
| liblz4 HC，level 9 | 1984.8 | 48.5% | 4.40 | 0.7% |

### 10.3 結論

1. **Hash table 用 1024 個 entry。** 從 256 加到 1024 有明顯的改善，從 1024 加到 4096 的平均長度改善在 2% 以內，而記憶體是 4 倍。唯一明顯的差別在執行檔組：超過 7 個 chunk 的 page 比例會降低大約一半。如果目標系統的 RW page 像執行檔一樣難壓，這一點值得重新評估。`HASH_BITS` 留成參數，之後要改不必動架構。
2. **Hash 用 XOR 摺疊，不用乘法。** 兩者的 stream 長度相差不到 1%，XOR 沒有乘法器，timing 容易得多。
3. **只做最基本的寫入規則。** 「match 之後多寫幾個位置」在文字與執行檔上略好，在 heap 上反而變差，而且讓 pipeline 的 forwarding 更複雜。往前延伸 match 有小幅改善，但 literal 的輸出要能撤回，留到之後評估。
4. **與 liblz4 預設的差距在 5% 以內。** 這個簡單的設計沒有明顯落後軟體。HC 可以再小很多，但它需要多個候選與 lazy matching，不適合單一 pipeline。
5. **執行檔 page 平均只壓到 73%，HC 也只有 68%。** 系統層先前假設 RO 的 code 可以壓到 55% 左右，這組資料不支持。這裡量的是這台開發機上的執行檔，不是目標 SoC 的 firmware image，需要用真正的 image 重量一次。這個結果影響的是容量規劃，不影響硬體設計。
6. **Heap page 平均壓到 32%，平均 3.17 個 chunk。** 這組資料是 Python 程序的 heap，同樣要用目標系統的 RW dump 重量。
7. **執行檔 page 有 22% 超過 7 個 chunk。** 以 RW 的 `limit` 來壓會得到 INCOMPRESSIBLE。RO 的 page 如果在 build 時由工具壓好，可以用 HC，不經過這顆硬體的 encoder；decoder 解得開任何合法的 LZ4 block。

## 11. 驗證

### 11.1 原則

RTL 的每一個外部行為都與 reference model 逐 byte 比對。Model 分三層，test bench 也分三層，下層先過再做上層。

| 層 | Reference | 待測範圍 | 比對什麼 |
|---|---|---|---|
| Core | `hwref.lz4core` | `lz4_enc`、`lz4_dec`、`lz4_crc32` 各自的 block bench | Stream 的 byte、解出的 page、哪一項檢查失敗、CRC |
| Job | `hwref.job` | 整顆硬體，一次一個 job | Completion 的 16 B、有定義的記憶體範圍、access 沒有超出授權 |
| Ring 與 CSR | `sim/ifsim/hw.py` 的行為 | 整顆硬體，連續的 job 與 register 操作 | Register 讀值、index、halt、`irq`、completion 的順序 |

### 11.2 Test bench 的組成

```
  +-----------+   APB    +---------+   AXI    +--------------------------+
  | FW driver |--------->|   DUT   |<-------->| AXI slave memory model   |
  +-----+-----+          +----+----+          | random wait, error inject|
        |                     | irq           +------------+-------------+
        v                     v                            |
  +-----------+         +-----------+               +------v------+
  | reference |-------->| scoreboard|<--------------| access log  |
  |  models   |         +-----------+               +-------------+
  +-----------+               ^
                              |
                     rule monitors, AXI protocol checker
```

| 元件 | 功能 |
|---|---|
| FW driver | 照第 4.4 節的順序操作 register 與 ring。可以故意違規，用來測錯誤處理 |
| AXI slave memory model | 稀疏的記憶體。每個 channel 可以隨機插入等待。可以指定某個位址範圍回 SLVERR |
| Access log | 記下 DUT 每一個 burst 的方向、位址、長度 |
| Scoreboard | Job 結束時比對 completion，比對 model 標成有定義的記憶體範圍，跳過未定義的範圍，確認其他記憶體沒變 |
| Rule monitor | 第 4.6 節每條 HW 規則一個，持續檢查 |
| AXI protocol checker | 標準的 AXI4 assertion |

建議用 cocotb：reference model 是 Python，可以直接 import，不必轉檔。如果團隊用 SystemVerilog 或 UVM，用下一節的 vector 檔案，model 不必進模擬器。選哪一種列在第 12 節。

### 11.3 Vector 檔案

```
python3 sim/run_hwref.py vectors --out <directory>
```

產生四類 vector，總共約 3.5 MB。

| 檔案 | 內容 |
|---|---|
| `index.json` | 介面版本、encoder 的參數、每個 core vector 的名稱、說明、stream 長度、CRC；壞掉的 stream 另外有預期失敗的檢查、失敗時的 stream 位置與已輸出的 byte 數 |
| `core/<name>.page.hex` | 4096 B 的 page，每行一個 byte 的 hex，低位址在前，可以直接給 `$readmemh` |
| `core/<name>.stream.hex` | Stream，格式同上 |
| `jobs.json` | Job vector 的陣列 |

**Encoder，61 個。** 每個是一個 4096 B 的 page 與預期的 stream。

| 名稱 | 個數 | 考什麼 | 值 |
|---|---|---|---|
| `example` | 1 | 第 2 節的例子 |  |
| `zeros` | 1 | 整個 page 是 0：一個 match 一路到結尾前 5 個 byte，match 長度要 16 個延伸 byte |  |
| `random` | 1 | 什麼都對不上：一個 sequence，4096 個 literal，stream 比 page 長 |  |
| `words` | 1 | 像文字：幾百個短的 sequence |  |
| `two_symbols` | 1 | 幾乎每個位置都 match，offset 很短，hash table 的同一格馬上又被用到：考 forwarding |  |
| `four_symbols` | 1 | 同上，literal 多一些 |  |
| `runs` | 1 | 同一個 byte 連續 8 個或 16 個上下：各種短長度的重疊 match |  |
| `lit_*` | 11 | 第一個 match 前面的 literal 數是這個值，0 那一個是兩個 match 緊接著、中間沒有 literal：長度欄位 15 的邊界與延伸 byte 255 的邊界 | 0、1、2、3、14、15、16、269、270、271、525 |
| `match_*` | 9 | match 長度是這個值：同樣的邊界 | 4、5、18、19、20、273、274、275、529 |
| `offset_*` | 20 | offset 是這個值 | 1、2、3、4、5、7、8、9、15、16、17、31、32、33、255、256、257、1024、2047、4084 |
| `late_*` | 1 | 同樣的 8 個 byte 晚一個位置出現：那裡不能開始 match | 4085 |
| `len_*` | 13 | stream 的長度恰好是這個值：chunk 的邊界、limit 3584 的邊界、4096 的邊界 | 511、512、513、1023、1024、1025、3583、3584、3585、4094、4095、4096、4097 |

**Decoder 專用，88 個。** 不是這個 encoder 產生的 stream：liblz4 預設與 HC 的輸出，各種短 offset 配各種 match 長度的手工組合，以及兩個超出 encoder 結尾規定的 stream（第 7.4 節）。Decoder 必須解得開任何 LZ4 compressor 寫的 block，不只是自己的 encoder 寫的。

**壞掉的 stream，13 個。** 每個標明預期失敗的檢查。

| 名稱 | stream 長度 B | 哪裡壞 | `decode` 哪一項檢查發現 |
|---|---|---|---|
| `bad_cut_in_literals` | 14 | stream 在一串 literal 中間結束 | `UNDERRUN` |
| `bad_cut_in_offset` | 16 | stream 在 offset 的第一個 byte 之後結束 | `UNDERRUN` |
| `bad_cut_in_length` | 8 | stream 在 match 長度的延伸 byte 中間結束 | `UNDERRUN` |
| `bad_cut_after_match` | 17 | stream 在一個 match 之後結束，那裡應該要有 token | `UNDERRUN` |
| `bad_cut_after_literals` | 15 | stream 在前面某個 sequence 的 literal 之後結束：結束的位置合法，輸出遠不到 4096 B | `SHORT` |
| `bad_half_page` | 18 | 一個正確的 block，但它是 2048 B 的 page | `SHORT` |
| `bad_offset_zero` | 37 | offset 是 0 | `OFFSET` |
| `bad_offset_far` | 37 | 輸出才 8 個 byte，offset 是 9 | `OFFSET` |
| `bad_literals_over` | 27 | 最後一個 sequence 有 6 個 literal，只放得下 5 個 | `OVERFLOW` |
| `bad_match_over` | 21 | 輸出 1 個 byte 之後來一個長度 4096 的 match | `OVERFLOW` |
| `bad_length_runaway` | 4096 | 4096 個 0xFF：literal 長度沒有盡頭 | `OVERFLOW` |
| `bad_extra_byte` | 69 | 完整的 block 後面多一個 byte | `UNDERRUN` |
| `bad_extra_sequence` | 71 | 完整的 block 後面多一個 match | `OVERFLOW` |

**Job，84 個。** 每個包含 register 設定、descriptor、執行前的記憶體、預期的 completion、執行後有定義的記憶體、未定義的範圍、授權的 access 範圍。

| 類別 | 名稱 | `OK` | `INCOMPRESSIBLE` | `BAD_STREAM` | `BUS_ERROR` | `BAD_DESC` |
|---|---|---|---|---|---|---|
| COMPRESS | `c_*` | 16 | 3 |  |  |  |
| DECOMPRESS | `d_*` | 24 |  | 16 |  |  |
| descriptor 不合法 | `bad_desc_*` |  |  |  |  | 21 |
| bus error，暫定 | `bus_*` |  |  |  | 4 |  |
| **合計** |  | 40 | 3 | 16 | 4 | 21 |

`bus_*` 的 vector 依據提案 P2，P2 定案前是暫定的。

### 11.4 隨機測試

Vector 是固定的回歸測試，另外要有隨機測試，model 在模擬時同步執行或事先批次產生。

| 項目 | 隨機的內容 |
|---|---|
| Page 的內容 | 全亂數、全相同、各種週期的重複、真實資料的片段、以上的混合；刻意產生 hash 碰撞多的資料 |
| Stream | 合法 stream 做 bit 翻轉、截短、加長、改 `comp_len`、改 `checksum`；純亂數 |
| Descriptor | 每個欄位的合法值與非法值，chunk 編號重複、不連續、在 pool 的頭尾 |
| Bus 的時間 | 每個 channel 的等待 0 到數十 cycle；長時間不給 `arready` 或 `wready`；`rvalid` 斷斷續續 |
| Ring | 各種 size；ring 滿與空；FW 很慢才收 completion；一次敲進很多 job |
| 錯誤注入 | 每一種 burst 的每一個 beat 位置回 SLVERR |
| Reset | 在 FSM 的每個狀態、burst 的每個階段下 soft reset，之後接正常的 job |

**結果與時間無關是一項獨立的檢查。** 同一個 job 用至少三種不同的 bus 等待設定各跑一次，completion、記憶體與 access 的順序必須完全相同（AXI-6）。

### 11.5 Block 層的 bench

| Block | 重點 |
|---|---|
| `lz4_enc` | 與 `encode` 逐 byte 比對。Forwarding 的每一種情況：與前一個位置同 hash、與前兩個位置同 hash、兩者同時。Match 在 4091 被截斷。下游隨機 back-pressure |
| `lz4_dec` | 與 `decode` 比對。上游隨機斷流、下游隨機 back-pressure。Offset 1 到 24 附近的每個值配上 `opos` mod 8 的每個值。每項檢查在每個狀態觸發 |
| `lz4_crc32` | 檢查值；1 到 8 B 的每種尾端長度 |
| `lz4_pagebuf` | 不對齊的 8 B 視窗在每個 byte 偏移的讀寫；兩個 port 同時讀同一個 word |
| `lz4_csr` | 第 4.2 節的每一條 |
| `lz4_rdma`、`lz4_wdma` | AXI 協定；error response 在每個 beat；soft reset 排空 |

### 11.6 Coverage

Functional coverage 至少包含：

- Token 高低 4 bit 各自的 0、1 到 14、15。
- 長度 byte 的個數 0、1、2、3 以上；最後一個長度 byte 是 0。
- Offset 的 1、2 到 7、8、9 到 24 減 1、24、更大、4095。
- Match 在位置 4091 結束；最後一個 sequence 的 literal 數是 5 與大於 5。
- Stream 長度相對於 `limit`：小 1、相等、大 1；相對於 512 的倍數：小 1、相等、大 1。
- 每一個 status；每一個 `aux` 代碼；每一個 halt 代碼。
- Decoder 的四項檢查各自在每個可能的狀態發生；CRC 不符。
- Forwarding 的三種情況；forward 之後 match 與不 match。
- Job FSM 的每個狀態轉移；POST 等待 ring 空位。
- 兩個 FIFO 的滿與空；read burst 與 write burst 同時進行。
- 每個狀態下的 soft reset 與 halt。
- 連續的 job 之間沒有 idle cycle；COMPRESS 與 DECOMPRESS 交錯。

Code coverage 的目標是 line、branch、FSM、toggle 都到 100%，達不到的逐項說明。

### 11.7 Formal，選做

適合 formal 的性質：FIFO 不 overflow 也不 underflow；AXI 協定；decoder 的輸出計數永遠不超過 4096；任何輸入下 decoder 都在有限的 cycle 內結束；`lz4_crc32` 的 8 B 版本等於 8 次 1 B 版本；pipeline 的 encoder 與 3 cycle FSM 版本在小尺寸的 page 上等價。

### 11.8 完成的條件

1. 四類 vector 全部通過，每個 job vector 在三種 bus 時間設定下都通過。
2. 隨機測試：每一層至少 100 萬個 page 或 stream，沒有不一致。
3. 第 11.6 節的 functional coverage 100%。
4. Code coverage 達標或有說明。
5. 每條 HW 規則與每個有編號的要求都有對應的檢查，對照表完成。
6. Synthesis 與 CDC、lint 檢查乾淨。
7. 量到的 cycle 數已經回填第 9 節與 `sim/ifsim`。

## 12. 決策、提案與待確認事項

### 12.1 這份規格已經做的選擇

| 選擇 | 理由 | 章節 |
|---|---|---|
| Encoder 的輸出與 model 逐 byte 相同 | 驗證最簡單 | 7.2 |
| 單一 hash table、greedy、每個位置 1 cycle | 見第 10 節的量測 | 7.2、10 |
| Valid bit 用 flop，每個 job 清除 | HW-STATE-1 與可重現 | 5.4 |
| Page buffer 分偶奇兩個 bank | 一個 cycle 讀兩個不對齊的視窗 | 5.4 |
| Decoder 用 24 B 的 history register | 短 offset 不必等 RAM | 7.4 |
| Store-behind | Fault 延遲 | 7.5 |
| Decoder 不檢查 encoder 的結尾規定 | 少三個比較器，行為由 model 定義 | 7.4 |
| 一個 engine | 先把一個做對 | 1 |

### 12.2 對介面規格的提案

這些還沒有改進 `interface.json`，需要決定。

| 編號 | 提案 | 現況 |
|---|---|---|
| P1 | FW-CFG-2 加上 `POOL_BASE` 是 512 的倍數、`FRAME_BASE` 是 4096 的倍數，硬體在 `ENABLE` 時檢查，不通過就 BAD_RING_CFG。這樣所有 burst 自動對齊，不會跨 4 KB 邊界 | RTL 基準已經照做（CSR-3）。`ifsim` 還沒有這項檢查 |
| P2 | 資料的 bus error（未決事項 O8）：完成出錯的 burst、不再發新的資料 burst、completion 為 BUS_ERROR、不 halt、目的地未定義 | 第 6.4 節照這個寫。4 個 `bus_*` vector 是暫定的 |
| P3 | BAD_STREAM 的 completion 在 `aux` 放細項：UNDERRUN、OVERFLOW、OFFSET、SHORT、CRC | 目前 `aux` 是 0。加上去對 debug 有幫助，硬體成本幾乎是零 |
| P4 | Power（未決事項 O9）：idle 時 clock gating 由硬體自己做；power down 時所有 register 遺失，FW 重新設定，流程同 soft reset 之後 | 這一版沒有做任何 power 相關的設計 |

### 12.3 待確認事項

下面每一項都需要專案負責人或整合的人回答。回答之前 RTL 照「目前的假設」做。

| # | 問題 | 這份規格目前的假設 | 影響 |
|---|---|---|---|
| 1 | Register 與資料各走什麼 bus，data 寬度多少 | APB、AXI4、64 bit | 第 3 節與兩個 DMA block |
| 2 | Clock 頻率，APB 與 AXI 是否同一個 clock | 同一個，頻率未定 | 第 9 節的時間；pipeline 要切多深 |
| 3 | `HASH_BITS` 用 10 還是 12 | 10 | Stream 小不到 2%，hash table 4 倍 |
| 4 | 寫入規則維持最基本的 | 是 | 見第 10.3 節第 3 點 |
| 5 | Store-behind 還是 decode-then-store | Store-behind | DECOMPRESS 多大約 450 cycle，換 BAD_STREAM 時 frame 不被寫 |
| 6 | 最後一個 chunk 的尾端要不要規定成必須是 0 | 基準補 0，介面上仍是未定義，bench 不比對 | 規定之後 scoreboard 多比對這一段，FW 仍然不該讀它 |
| 7 | 提案 P1 | 採用 | 介面規格與 `ifsim` 要跟著改 |
| 8 | 提案 P2 | 採用 | 同上 |
| 9 | 提案 P3 | 不採用，等決定 | 介面規格 |
| 10 | Soft reset 之後內部記憶體要不要清 | 不清 | 清的話 reset 多大約 1000 cycle |
| 11 | 提案 P4 | 這一版不做 | 之後補一節 |
| 12 | Test bench 用 cocotb 還是 SystemVerilog 或 UVM | cocotb | Vector 檔案兩種都能用 |
| 13 | 能不能取得目標 SoC 的 firmware image 與 RW 記憶體的 dump | 沒有 | 第 10 節的壓縮率目前來自開發機的資料 |
| 14 | 製程的 SRAM macro 有沒有 byte write enable 與 dual port | 有 | 沒有的話 page buffer 的組織要改 |
| 15 | `limit` 是 4096 而 stream 剛好 4096 B 時走 RAW | 是，2026-11-12 定案 | 規則是 ENC-6。`hwref`、`ifsim`、`hostsim` 三個 model 已經一致 |

### 12.4 Model 之間已知的差異

| 差異 | 說明 | 處理 |
|---|---|---|
| `ifsim` 與 `hostsim` 預設用 liblz4 產生 stream | 它們驗證的是控制流程，不是 stream 的 byte | 加 `--codec hw` 就用 `hwref.lz4core` |
| BAD_STREAM 時 model 不寫 frame | RTL 基準是 store-behind | Model 把 frame 標成未定義，test bench 不比對 |
| `hwref.job` 一次讀完所有 chunk 再處理 | RTL 邊讀邊解 | Access 的集合相同，順序不同。Test bench 比對集合，順序另外用 AXI-6 的方式檢查 |
| `ifsim` 沒有 P1 的對齊檢查 | 見 P1 | P1 定案後補 |
| kernel 自己的 LZ4 decoder 比這顆硬體嚴格 | 第 7.4 節那種不守 encoder 結尾規定的 stream，硬體接受，kernel 的 decoder 拒絕 | 存進 chunk pool 的 stream 都出自守 ENC 規則的 encoder，所以碰不到。之後換 encoder 要重新確認。見控制程序 3.6 |

## 13. 檔案與指令

| 檔案 | 內容 |
|---|---|
| [hw-fw-interface.md](hw-fw-interface.md) | HW 與 FW 的介面規格，這份文件的上游 |
| [lz4_hwif.h](lz4_hwif.h) | 介面的 C header |
| [lz4-hw-design-spec-v0.json](lz4-hw-design-spec-v0.json) | 第 9、10 節的原始數字 |
| `sim/ifsim/interface.json` | Register、結構、enum、規則的唯一來源 |
| `sim/hwref/lz4core.py` | Encoder、decoder、CRC 的 reference model，cycle 估計 |
| `sim/hwref/job.py` | 單一 job 的 reference model |
| `sim/hwref/vectors.py` | Test vector |
| `sim/hwref/study.py` | 第 10 節的量測 |
| `sim/hwref/doc.py` 與 `templates/` | 產生這份文件 |
| `sim/tests/test_hwref.py` | Model 自己的測試 |

```
python3 sim/run_hwref.py gen-doc            # 重新量測並產生這份文件，約半分鐘
python3 sim/run_hwref.py gen-doc --reuse    # 沿用上次的量測數字，只重排文字
python3 sim/run_hwref.py study              # 只印量測結果
python3 sim/run_hwref.py vectors --out DIR  # 寫出 test vector
cd sim && python3 -m pytest tests           # 所有測試
```

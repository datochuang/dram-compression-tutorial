# 介面模擬結果，第 0 版

介面版本 {{version}}，seed {{seed}}。對象是要決定介面與 budget 的人。

> 表格由 `python3 sim/run_if.py results` 產生，原始數字在 `sim-results-v0.json`。同一份程式與 seed 會得到同樣的數字。
> 第 1 節的發現是對這一版數字手寫的。重跑之後數字有變的話，那一節要重讀一次。

**所有時間參數都是假設，不是量測值。** 這份文件能回答的是「瓶頸在哪一段、對哪個參數敏感」，還不能回答「實際會是幾 µs」。參數表在 `hw-fw-interface.md` 第 10 節。

## 1. 發現

### 1.1 總表

| 編號 | 發現 | 依據 | 對規格的意義 |
|---|---|---|---|
| F1 | 基準負載下每一項暫定 budget 都過，而且離限制很遠 | 第 3 節：engine 忙 4.1%，job ring 最多 4 格，kernel CPU 1.29% | 目前的介面在這個負載下夠用 |
| F2 | interrupt 模式下，一次 DECOMPRESS fault 有一半的時間花在通知，不在 HW | 第 4 節：`notify` 3.28 µs，`hw` 1.25 µs，合計 6.27 µs | 最需要實際數字的是 interrupt latency 與 thread 叫醒時間 |
| F3 | polling 把 p50 從 6.20 µs 降到 3.23 µs，代價是 kernel CPU 從 1.29% 變 2.30% | 第 4 節 | 等待方式是 FW 的選擇，介面兩種都支援，不用改 |
| F4 | 最慢的 fault 是排在一個 COMPRESS 後面 | 第 3 節最慢的一次：`queue` 4 到 5 µs，一個 COMPRESS 的 HW 時間是 4.24 µs | 單一 ring 的代價是 p99 多一個 COMPRESS 的時間 |
| F5 | 負載加重時先撐不住的是 reclaimer，不是 HW | 5.2：負載 10 倍時 engine 只忙 28%，卻有 9489 次 fault 等不到 free frame | reclaimer 一次只送一個 COMPRESS 不夠 |
| F6 | reclaimer 同時送 2 個 COMPRESS 最好，再多反而變差 | 5.2：2 個時等 frame 的次數歸零，p99 從 34.11 µs 降到 12.02 µs。5.3：8 個時 `queue` 升到 5.30 µs，p99 升到 37.69 µs | 要更深就需要讓 fault 的 job 插隊，見介面規格 O4 |
| F7 | job ring 16 格有餘，4 格就夠，2 格不夠 | 5.4：4 格時 `submit` 0.33 µs，2 格時 7.93 µs | 16 格可以定案 |
| F8 | DECOMPRESS 每個 clock 4 B 已經夠，再快沒有用 | 5.6：8 B 時 p50 只從 6.33 µs 降到 6.20 µs，剩下的時間在 bus | LZ4 core 不必為了 fault latency 追求更高的 throughput |
| F9 | COMPRESS 的速度只影響尾巴 | 5.6：0.5 B 到 4 B，p50 不變，p99 從 13.51 µs 降到 6.84 µs | COMPRESS 的速度依 p99 的目標來定 |
| F10 | HW 卡住、漏 interrupt、資料損毀三種故障都照規格恢復，沒有連帶損失 | 第 6 節 | 第 9 節的 reset 流程成立 |
| F11 | 漏一次 interrupt 會讓所有 fault 停到 timeout 為止，最長 1 ms | 第 6 節：最大 1002.37 µs | 1 ms 的 timeout 太長，或者要有定期讀 ring 的備援 |
| F12 | 所有模擬的 checker 違規都是 0 | 第 7 節 | FW model 與 HW model 都符合介面規格第 7 節 |

### 1.2 時間花在哪裡

一次 RO page 的 DECOMPRESS fault，interrupt 模式，平均 6.27 µs：

| 階段 | 時間 µs | 佔比 | 誰決定 |
|---|---|---|---|
| `notify` | 3.28 | 52% | interrupt latency 1.0 µs、handler、叫醒 thread 2.0 µs。都是假設 |
| `cpu` | 1.45 | 23% | FW 的指令。exception 進出佔 1.0 µs。都是假設 |
| `hw` | 1.25 | 20% | LZ4 core 與 bus |
| `submit` | 0.15 | 2% | 寫 descriptor 與 doorbell |
| `queue` | 0.10 | 2% | 前面有沒有 COMPRESS |
| `lock` | 0.03 | 1% | `mm_lock` |

HW 做一個 DECOMPRESS 只要 1.25 µs，比叫醒一個睡著的 thread 還短。所以 fault 這條路睡下去等 interrupt 並不划算。對 `wakeup_ns` 的掃描也說明同一件事：它從 500 ns 變到 20000 ns，p50 從 4.85 µs 變到 24.35 µs，幾乎一比一。

值得接著模擬的做法：fault 這條路先 polling 幾 µs，等不到才睡；reclaimer 是背景工作，用 interrupt。目前模擬器的等待方式是全域的，還不能這樣混用。

### 1.3 單一 ring 的取捨

fault 的 DECOMPRESS 與 reclaimer 的 COMPRESS 排同一個 ring。HW 一次做一個，照順序做。

| reclaimer 同時在外的 COMPRESS | 好處 | 壞處 |
|---|---|---|
| 1 | fault 最多等一個 COMPRESS | 回收速度有上限。負載 10 倍時 free frame 用光 |
| 2 | 回收速度夠，free frame 不再用光 | fault 最多等兩個 COMPRESS，p99 仍在 13 µs 以內 |
| 4 以上 | 沒有額外好處 | fault 排在一串 COMPRESS 後面，p99 超過 20 µs |

所以在單一 ring 之下，2 是目前最好的設定。第二個 ring 或優先權在這個負載範圍內還不需要。

### 1.4 還不能下結論的

| 項目 | 原因 |
|---|---|
| 任何絕對數字 | 時間參數全部是假設 |
| core 數少於 user SW 數的情況 | 5.5 裡 interrupt 模式在 1 個 core 時 p50 是 42.70 µs，`notify` 平均 45.17 µs，幾乎全是 thread 醒來後排隊等 core。這是模型的 scheduler 不會 preempt 造成的，實際的 kernel 不一定如此。要等 core 數與 kernel 確定後把 scheduler 做實 |
| polling 的 CPU 代價 | 4 個 core 配 4 個 user SW 時，polling 佔住的 core 本來也沒有別人要用。core 比較少時才看得出代價 |
| kernel CPU 的 budget | 佔比隨負載變。負載 10 倍時是 9%。budget 需要連同負載一起定義 |

### 1.5 建議

| 項目 | 建議 | 狀態 |
|---|---|---|
| job ring 與 completion ring | 各 16 格 | 可以定案 |
| reclaimer 同時在外的 COMPRESS | 2 | 可以當預設值，FW 可調 |
| 單一 ring | 維持 | 維持到負載或 p99 目標改變為止 |
| 等 completion 的方式 | fault 先 polling 再睡，reclaimer 用 interrupt | 要先模擬 |
| job timeout | 比 1 ms 短很多，或加上定期讀 ring 的備援 | 要先決定可以接受的最長停頓 |
| DECOMPRESS 的 throughput | 每個 clock 4 B | 等 bus 的實際數字確認 |
| COMPRESS 的 throughput | 每個 clock 1 B 可以接受 | 依 p99 目標再看 |

### 1.6 需要專案提供的

| 編號 | 需要什麼 | 用在哪裡 |
|---|---|---|
| O1 | budget 的目標，連同負載：每個 user SW 每秒幾次 page access，其中多少比例會 fault | 判斷 PASS 與 FAIL |
| O2 | 實際的時間：interrupt latency、thread 叫醒時間、exception 進出、TLB invalidate、DRAM port 的 throughput、LZ4 core 每個 clock 幾個 byte | 取代假設值。前兩項影響最大 |
| O3 | core 數，用哪個 kernel 或 RTOS | scheduler 與 lock 的模型 |

## 2. 怎麼跑的

| 項目 | full | small |
|---|---|---|
| 用途 | 基準 | 參數掃描與故障注入 |
| page frame 數 | 35840 | 512 |
| chunk 數 | 563200 | 8192 |
| page 數 | 148480 | 1792 |
| 低水位 / 高水位的 free frame 數 | 512 / 1024 | 16 / 48 |
| access 次數 | {{n_full}} | {{n_small}} |
| 跑一次的時間 | 約 25 s | 約 1 s |

四個 user SW：UI、MEDIA、NET、LOG，各自一個 thread。預設 4 個 core，每個 thread 一個 core。每個 user SW 在兩次 page access 之間自己做 `think_ns` 的事，預設 20000 ns。

每一次模擬都掛著 checker。checker 只看 HW 與 FW 邊界上的事件與 DRAM 的內容，自己維護一份 ring、job、PTE、COT 的影子，逐條對照介面規格第 7 節的規則。模擬結束時再做一次 audit，把每個 page 的內容與預期值逐 byte 比對。

latency 的定義：從 CPU 進入 page fault 到指令重新執行。表格裡的 p50、p99、最大值只算需要等 LZ4 HW 的 fault，也就是碰到壓縮著的 page。

一次 fault 的時間拆成這幾段：

| 階段 | 內容 |
|---|---|
| `cpu` | FW 自己的指令：進出 exception、查 COT、填 descriptor、寫 PTE |
| `lock` | 等 `mm_lock` |
| `frame` | 沒有 free frame，等 reclaimer |
| `inflight` | 這個 page 已經有 job 在進行，等那個 job |
| `submit` | 等 job ring 的空位與 `ring_lock`，寫 descriptor 與 doorbell |
| `queue` | job 已經在 ring 裡，等 HW 做完前面的 job |
| `hw` | HW 讀 descriptor 到寫完 completion |
| `notify` | completion 寫好到送出 job 的 thread 重新開始跑 |

## 3. 基準：full，interrupt

{{base_irq:run}}

暫定 budget：

{{base_irq:budgets}}

latency：

{{base_irq:latency}}

各階段的平均：

{{base_irq:parts}}

最慢的一次：

{{base_irq:worst}}

資源：

{{base_irq:resources}}

每個 user SW：

{{base_irq:clients}}

## 4. interrupt 與 polling 的比較：full

同樣的 workload，只換 FW 等 completion 的方式。階段的數字是 RO page 解壓縮 fault 的平均，單位 µs。

{{compare}}

polling 的 budget：

{{base_poll:budgets}}

## 5. 參數掃描

除了 5.2 以外都用 small，每格 {{n_small}} 次 access。表格裡以階段命名的欄位是 RO page 解壓縮 fault 在那個階段的平均。

### 5.1 負載：`think_ns` 越小，access 越密

{{sweep:load}}

### 5.2 負載：full

每格 {{n_full}} 次 access，interrupt。

{{sweep:full_load}}

### 5.3 reclaimer 同時在外的 COMPRESS 數

`think_ns` 固定在 2000，interrupt。

{{sweep:reclaim_inflight}}

### 5.4 job ring 的格數

`think_ns` 固定在 2000，`reclaim_inflight` 固定在 2，completion ring 16 格。可用的深度是格數減 1。

{{sweep:ring_size}}

### 5.5 core 數與等待方式

{{sweep:wait_cores}}

### 5.6 LZ4 HW 的速度

COMPRESS 每個 clock 吃進的 byte 數：

{{sweep:comp_speed}}

DECOMPRESS 每個 clock 吐出的 byte 數：

{{sweep:decomp_speed}}

DRAM port 被其他流量佔住的比例：

{{sweep:bus_bg}}

### 5.7 interrupt 路徑的時間

thread 被叫醒到開始跑的時間：

{{sweep:wakeup}}

interrupt latency：

{{sweep:irq_latency}}

## 6. 故障注入

small，seed 3，每格 {{n_small}} 次 access。

{{faults}}

## 7. 規則涵蓋

基準那一次模擬裡每條規則被檢查的次數。標成注入測試或人工 review 的規則不在執行中檢查。

{{rules}}

每條由 checker 或 audit 負責的規則，在 `sim/tests/test_ifsim_mutations.py` 都有一個故意放進去的 bug，確認 checker 真的會抓到。只會通過的 checker 證明不了什麼。

## 8. 模型的限制

| 限制 | 影響 |
|---|---|
| 所有時間參數都是假設 | 絕對數字不可信，只能看比例與趨勢 |
| scheduler 不會 preempt。thread 醒來後要等佔著 core 的 thread 跑完它那一段 `think_ns` | core 數少於 user SW 數時，interrupt 模式的數字偏悲觀，見 5.5 |
| reclaimer 不佔 core，不與 user SW 搶 CPU | kernel CPU 佔比算進去了，但對 user SW 的排擠沒有 |
| 等 `mm_lock` 與 `ring_lock` 的時間沒有算進 kernel CPU | 高負載時 kernel CPU 佔比偏低 |
| 沒有 direct reclaim。fault 拿不到 free frame 時只能等 reclaimer | 高負載時 `frame` 階段偏長 |
| 被標成 INCOMPRESSIBLE 的 page 永遠不再被挑 | 長時間執行時可回收的 page 會變少 |
| DRAM port 上的其他流量用機率模型 | bus 的競爭只是近似 |
| frame 與 chunk 的 bus error 在這個模擬器裡沒有模擬 | `BUS_ERROR` 之後 FW 怎麼做，由 `sim/hostsim` 執行過，見控制程序 3.6 與 7.3。它花多少時間還沒有數字 |
| 這個模擬器的 FW model 沒有自己的 LZ4 decoder | BAD_STREAM 在這裡直接算損毀。控制程序 3.6 的第二個意見只在 `sim/hostsim` 執行過 |
| workload 是合成的：固定的 hot set 加隨機的 cold access | 沒有 phase 變化，沒有 burst |
| small 的水位只有 16 與 48 個 frame | small 比 full 更容易用光 free frame，5.1 的拐點比 full 來得早 |

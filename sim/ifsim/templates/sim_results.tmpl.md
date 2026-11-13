# 介面模擬結果，第 0 版

介面版本 {{version}}，seed {{seed}}。對象是要決定介面與 budget 的人。

> 表格由 `python3 sim/run_if.py results` 產生，原始數字在 `sim-results-v0.json`。同一份程式與 seed 會得到同樣的數字。
> 第 1 節的發現是對這一版數字手寫的。重跑之後數字有變的話，那一節要重讀一次。

**所有時間參數都是假設，不是量測值。** 這份文件能回答的是「瓶頸在哪一段、對哪個參數敏感」，還不能回答「實際會是幾 µs」。參數表在 `hw-fw-interface.md` 第 10 節。

**reclaimer 同時送出的 COMPRESS 數，預設值在 2026-11-13 從 1 改成 2。** 負責人同一天同意這個參數可以改，2 是照 5.2 與 5.3 的掃描選的。沒有另外寫 `reclaim_inflight` 的結果都是 2。改了之後變了什麼在 1.8。`sim/hostsim` 的 `kernel.py` 與控制程序的 pseudo code 仍然是一次送一個，沒有改。

**LZ4 HW 的 model 是 N 個 engine，這一版用 {{engines}} 個。** 平台前提 P4 在 2026-11-13 指定 LZ4 HW 可以同時接受 N 個 job，負責人同一天指定 N 先用 4。表格有 `engines` 一欄的照那一欄，其餘的結果都是 {{engines}} 個 engine。一個 engine 的對照在 1.7。N 個 engine 怎麼接到 DRAM 還沒有人決定，這裡照共用一個 master port 來算，見第 2 節與第 8 節。

## 1. 發現

### 1.1 總表

| 編號 | 發現 | 依據 | 對規格的意義 |
|---|---|---|---|
| F1 | 基準負載下每一項暫定 budget 都過，而且離限制很遠 | 第 3 節：每個 engine 平均忙 1.0%，至少一個 engine 在忙的時間是 3.5%，job ring 最多 4 格，kernel CPU 1.29% | 目前的介面在這個負載下夠用。這個負載下 4 個 engine 不是為了容量 |
| F2 | interrupt 模式下，一次 DECOMPRESS fault 有一半的時間花在通知，不在 HW | 第 4 節：`notify` 3.32 µs，`hw` 1.27 µs，合計 6.20 µs | 最需要實際數字的是 interrupt latency 與 thread 叫醒時間。engine 的數量不影響這一段 |
| F3 | polling 把 p50 從 6.20 µs 降到 3.23 µs，代價是 kernel CPU 從 1.29% 變 2.27% | 第 4 節 | 等待方式是 FW 的選擇，介面兩種都支援，不用改 |
| F4 | 4 個 engine 時 fault 不再排在 COMPRESS 後面。尾巴變短，中位數不變 | 1.7：p99 從 9.82 µs 降到 7.03 µs，最大值從 14.26 µs 降到 8.46 µs，p50 都是 6.20 µs。所有 fault 裡 `queue` 最長的一次從 7.19 µs 變成 0.00 µs | 一個 engine 時最慢的 fault 要等排在前面的 COMPRESS，一個是 4.24 µs。reclaimer 同時送 2 個時，前面最多有兩個。engine 變多買到的是最慢的那幾次 |
| F5 | 負載加重時先撐不住的是 reclaimer，不是 HW。engine 變多也一樣 | 5.2：負載 10 倍、4 個 engine、reclaimer 一次送一個 COMPRESS 時，每個 engine 只忙 7.3%，卻有 10484 次 fault 等不到 free frame，p99 是 31.75 µs。一個 engine 時是 9489 次與 34.11 µs | 多的 engine 要靠 reclaimer 多送才用得到。reclaimer 一次只送一個 COMPRESS 不夠。模擬器的預設值因此在 2026-11-13 改成 2 |
| F6 | reclaimer 同時送 2 個以上就夠。4 個 engine 時送多了也不再拖慢 fault | 5.2：4 個 engine、同時送 2 個時等 frame 的次數歸零，p99 是 7.93 µs，送 4 個是 8.24 µs。`queue` 最長的一次是 2.16 µs 與 1.65 µs，一個 engine 時是 8.37 µs 與 15.82 µs。5.3：送 8 個時 p99 是 8.95 µs，`queue` 最長 1.08 µs。一個 engine 送 8 個時是 37.69 µs 與 32.56 µs | 一個 engine 時「2 個最好，再多變差」的結論，在 4 個 engine 時不成立。上限不再由 fault 的等待決定，見 1.3 |
| F7 | job ring 16 格有餘，4 格就夠，2 格不夠 | 5.4：4 格時 `submit` 0.26 µs，2 格時 7.93 µs | 16 格可以定案 |
| F8 | DECOMPRESS 每個 clock 4 B 已經夠，再快沒有用 | 5.6：8 B 時 p50 只從 6.33 µs 降到 6.21 µs，剩下的時間在 bus | LZ4 core 不必為了 fault latency 追求更高的 throughput |
| F9 | 4 個 engine 時 COMPRESS 的速度幾乎不影響 fault | 5.6：0.5 B 到 4 B，p50 在 6.33 與 6.35 µs 之間，p99 在 6.98 到 7.20 µs 之間，沒有方向。2026-11-11 一個 engine、reclaimer 一次送一個的那一版是 13.51 µs 降到 6.84 µs | COMPRESS 的速度改由回收要多快來定，不由 fault 的 p99 來定 |
| F10 | HW 卡住、漏 interrupt、資料損毀三種故障都照規格恢復，沒有連帶損失 | 第 6 節。HW 卡住時 soft reset 放棄所有 engine 手上的 job，FW 全部重送 | 第 9 節的 reset 流程在 4 個 engine 時也成立 |
| F11 | 漏一次 interrupt 會讓所有 fault 停到 timeout 為止，最長 1 ms | 第 6 節：最大 1002.27 µs | 1 ms 的 timeout 太長，或者要有定期讀 ring 的備援。engine 的數量不影響這一點 |
| F12 | 所有模擬的 checker 違規都是 0 | 第 7 節。checker 已經照 N 個 engine 的規則改寫：`HW-CPL-1` 不再要求順序，`HW-MEM-2` 多檢查有 engine 空著才取 job，`FW-JOB-6` 檢查同時在外的 job 不共用 frame 與 chunk | FW model 與 HW model 都符合介面規格第 7 節 |
| F13 | completion 不照取走的順序回來。FW 用 tag 找 job，沒有出錯 | 第 3 節：52585 個 job 裡，有 697 個 completion 比先取走的 job 早寫出 | `FW-CPL-2` 是必要的，不是保險 |
| F14 | 2 個 engine 就拿掉大部分的排隊。第 3、第 4 個管的是重負載下最長的那幾次。8 個和 4 個幾乎一樣 | 5.8：基準負載下 1、2、4、8 個 engine 的 p99 是 10.13、7.58、6.98、6.98 µs，`queue` 最長的一次是 5.64、3.56、0.00、0.00 µs。5.9：負載 40 倍、reclaimer 同時送 4 個時，`queue` 最長的一次在 1、2、4、8 個 engine 分別是 15.59、5.35、1.19、0.00 µs，p99 分別是 28.82、12.00、9.99、9.50 µs | N 要看最長的等待來選，不是看平均。暫定的 4 在這個範圍內夠用 |
| F15 | engine 共用一個 DRAM port，同時做的 job 會互相拖慢。平均很小，最長的一次不小 | 第 3 節：等其他 job 的時間攤到每個 burst 是 1.0 ns。DECOMPRESS 的 HW 時間最大值從一個 engine 的 1.66 µs 變成 2.90 µs。5.9：負載 40 倍時，`hw` 最長的一次在 1、2、4、8 個 engine 分別是 1.61、2.36、3.52、3.90 µs。5.2：full、負載 10 倍時，4 個 engine 是 3.67 到 4.05 µs，一個 engine 是 1.66 到 1.73 µs | 排隊的等待有一部分換成 port 上的等待，總帳仍然是賺的。port 怎麼分還沒有人決定，見介面規格 O14。這裡的 arbiter 是簡化的 model |
| F16 | 4 個 engine、reclaimer 送得夠多之後，量到最慢的幾次 fault 都是碰到正在被 COMPRESS 的 page 的那一種。它等的是 kernel 自己送出的 COMPRESS，engine 再多也沒有用 | 5.2：full、負載 10 倍、同時送 2 個時，最慢的一次是 13.70 µs，其中 5.55 µs 是 `inflight`，在等同一個 page 的 COMPRESS 做完。5.3 與 5.9：4 個 engine 時 `inflight` 最長的一次在 5.45 到 7.59 µs 之間，8 個 engine 是 5.45 與 7.26 µs。次數很少：full 一次執行最多 5 次，small 最多 9 次。基準負載下也有：small 的基準 1 次，那一次 fault 是 11.50 µs，其中 `inflight` 2.41 µs，是那次執行最慢的一次。full、一個 engine 的基準 1 次。full、4 個 engine 的基準 0 次。一個 engine 時也有，而且更長：5.2 量到 11.37 µs，5.3 量到 17.12 µs | 這是控制程序的行為，不是 HW 的。次數少，所以平均與 p99 看不到，只有最大值看得到。兩個做法記在 dependency 分析的 6.5，都是效能類的修改，程式沒有動 |

### 1.2 時間花在哪裡

一次 RO page 的 DECOMPRESS fault，interrupt 模式，平均 6.20 µs：

| 階段 | 時間 µs | 佔比 | 誰決定 |
|---|---|---|---|
| `notify` | 3.32 | 53% | interrupt latency 1.0 µs、handler、叫醒 thread 2.0 µs。都是假設 |
| `cpu` | 1.45 | 23% | FW 的指令。exception 進出佔 1.0 µs。都是假設 |
| `hw` | 1.27 | 20% | LZ4 core 與 bus |
| `submit` | 0.15 | 2% | 寫 descriptor 與 doorbell |
| `lock` | 0.02 | 0% | `mm_lock` |
| `queue` | 0.00 | 0% | 所有 engine 都有 job 時才會等 |

HW 做一個 DECOMPRESS 只要 1.27 µs，比叫醒一個睡著的 thread 還短。所以 fault 這條路睡下去等 interrupt 並不划算。對 `wakeup_ns` 的掃描也說明同一件事：它從 500 ns 變到 20000 ns，p50 從 4.84 µs 變到 24.33 µs，幾乎一比一。

engine 從一個變成 4 個，這張表只有 `queue` 那一列變了，從 0.10 µs 變成 0.00 µs。平均的時間仍然花在通知。

值得接著模擬的做法：fault 這條路先 polling 幾 µs，等不到才睡；reclaimer 是背景工作，用 interrupt。目前模擬器的等待方式是全域的，還不能這樣混用。

### 1.3 單一 ring、N 個 engine 的取捨

fault 的 DECOMPRESS 與 reclaimer 的 COMPRESS 排同一個 ring。HW 照 ring 的順序取 job，有 engine 空著才取。所以 fault 的 job 要等，只發生在所有 engine 手上都有 job 的時候。

下表取自 5.3，負載 10 倍，small。每格依序是等 free frame 的次數、p99、所有 fault 裡 `queue` 最長的一次。

| reclaimer 同時在外的 COMPRESS | 一個 engine | 4 個 engine |
|---|---|---|
| 1 | 245 次、31.75 µs、5.21 µs | 258 次、28.54 µs、0.00 µs |
| 2 | 11 次、12.65 µs、7.18 µs | 10 次、8.24 µs、0.00 µs |
| 3 | 0 次、15.97 µs、10.40 µs | 0 次、8.44 µs、0.63 µs |
| 4 | 0 次、20.11 µs、15.09 µs | 0 次、8.60 µs、0.72 µs |
| 8 | 0 次、37.69 µs、32.56 µs | 0 次、8.95 µs、1.08 µs |

讀法有三點。

1. 同時在外 1 個時，兩欄都不夠。p99 高是因為 fault 在等 free frame，和 engine 的數量無關。這就是 F5。
2. 一個 engine 時，同時在外的 COMPRESS 每多一個，fault 最長就多等一個 COMPRESS。所以那時 2 是最好的設定。
3. 4 個 engine 時這個代價小很多。small 送到 8 個，`queue` 最長是 1.08 µs。full 的結果在 5.2：負載 10 倍，同時送 2 個與 4 個，`queue` 最長是 2.16 µs 與 1.65 µs，一個 engine 時是 8.37 µs 與 15.82 µs。

4 個 engine、同時在外 3 個以上時 `queue` 不是 0。原因是 user SW 的 DECOMPRESS 也佔 engine：3 個 COMPRESS 加上 1 個 DECOMPRESS 就佔滿 4 個 engine，下一個 fault 要等其中一個做完。介面規格 O16 的規則是同時在外的 COMPRESS 不超過 N 減 1。它保證的是至少有一個 engine 不在做 COMPRESS，不保證 fault 不用等。從上表看，3 與 4 的差別是 0.63 µs 對 0.72 µs，在這個負載範圍內分不出來。full 上同時送 2 個量到的 2.16 µs 還比送 4 個的 1.65 µs 長。所以這個最長值主要看幾個 fault 有沒有剛好碰在一起，不是看 COMPRESS 送了幾個。

第二個 ring 或優先權能拿回來的，最多就是上面這些 `queue` 最長值，量到最大的是 2.16 µs。同一批執行裡，`hw` 最長的一次因為共用 port 多了大約 2 µs，見 F15。最慢的那一次 fault 等的也不是 ring，見 F16。所以 4 個 engine 時，ring 的順序不是最慢那幾次的主因。

### 1.4 還不能下結論的

| 項目 | 原因 |
|---|---|
| 任何絕對數字 | 時間參數全部是假設 |
| N 是不是就定為 4 | 4 是暫定的。F14 說 2 個已經拿掉大部分排隊，4 個管的是重負載下最長的幾次。要不要為那幾次付 4 份 datapath 的面積，要看面積與 p99 的目標 |
| 好幾個 job 同時做時，每個 job 變慢多少 | F15 的數字來自簡化的 arbiter：讀與寫各一個 channel，一次一個 burst，engine 之間輪流。實際的接法還沒決定，介面規格 O14。每個 engine 各有 port 的話這一項會消失，換成 DRAM controller 那一側的競爭 |
| core 數少於 user SW 數的情況 | 5.5 裡 interrupt 模式在 1 個 core 時 p50 是 42.68 µs，`notify` 平均 44.98 µs，幾乎全是 thread 醒來後排隊等 core。這是模型的 scheduler 不會 preempt 造成的，實際的 kernel 不一定如此。要等 core 數與 kernel 確定後把 scheduler 做實 |
| polling 的 CPU 代價 | 4 個 core 配 4 個 user SW 時，polling 佔住的 core 本來也沒有別人要用。core 比較少時才看得出代價 |
| kernel CPU 的 budget | 佔比隨負載變。5.2 的 full 在負載 10 倍時是 9% 到 10%。budget 需要連同負載一起定義 |
| fault 的 thread 比 engine 多的情況 | 這裡只有 4 個 user SW，同時最多 4 個 DECOMPRESS。thread 更多時，fault 之間也會互相排隊 |

### 1.5 建議

| 項目 | 建議 | 狀態 |
|---|---|---|
| job ring 與 completion ring | 各 16 格 | 可以定案 |
| engine 的數量 | 4 夠用。2 個是下限的候選，8 個和 4 個幾乎一樣 | N 暫定 4。DRAM port 的接法確定後再看一次 |
| reclaimer 同時在外的 COMPRESS | 至少 2。4 個 engine 時 2 到 4 都可以，差別見 1.3 | FW 可調。模擬器的預設值在 2026-11-13 經負責人同意從 1 改成 2。`sim/hostsim` 的 `kernel.py` 與控制程序的 pseudo code 仍然一次送一個，要不要跟著改等負責人決定，見 dependency 分析的 K3 |
| 單一 ring | 維持 | 4 個 engine 時 fault 在 ring 裡最長等 2.16 µs。第二個 ring 或優先權最多拿回這一段，而它不是最慢那幾次的主因 |
| fault 碰到正在被 COMPRESS 的 page | 先決定要不要處理。做法見 dependency 分析的 6.5 | F16。效能類的修改，等負責人決定。程式沒有改 |
| 等 completion 的方式 | fault 先 polling 再睡，reclaimer 用 interrupt | 要先模擬。4 個 engine 之後，這是平均 latency 剩下最大的一項 |
| job timeout | 比 1 ms 短很多，或加上定期讀 ring 的備援 | 要先決定可以接受的最長停頓 |
| DECOMPRESS 的 throughput | 每個 clock 4 B | 等 bus 的實際數字確認 |
| COMPRESS 的 throughput | 每個 clock 1 B 可以接受 | 4 個 engine 時它不影響 fault，見 F9 |

### 1.6 需要專案提供的

| 編號 | 需要什麼 | 用在哪裡 |
|---|---|---|
| O1 | budget 的目標，連同負載：每個 user SW 每秒幾次 page access，其中多少比例會 fault | 判斷 PASS 與 FAIL |
| O2 | 實際的時間：interrupt latency、thread 叫醒時間、exception 進出、TLB invalidate、DRAM port 的 throughput、LZ4 core 每個 clock 幾個 byte | 取代假設值。前兩項影響最大 |
| O3 | core 數，用哪個 kernel 或 RTOS | scheduler 與 lock 的模型 |
| O7 | N 是否就定為 4 | 目前所有結果的預設 |
| O14 | N 個 engine 怎麼接到 DRAM | F15 與 5.9 的 `hw` 最長值都依賴它 |

### 1.7 一個 engine 與 {{engines}} 個 engine 的對照

同樣的 workload、同樣的 seed，只換 `engines`。full，interrupt，reclaimer 同時送 2 個 COMPRESS，是 2026-11-13 之後的預設值。

{{compare_engines}}

上表的一個 engine 那一欄，reclaimer 同時送 2 個，所以和 2026-11-11 那一版不同。把 `engines` 與 `reclaim_inflight` 都設成 1 另外跑一次，結果與 2026-11-11 那一版逐項相同，event 數也相同。所以擴充成 N 個 engine 沒有改到一個 engine 的行為。

2026-11-13 指定 P4 的時候，這份文件先用推論寫了每個發現會怎麼變。下表是那些推論和模擬對照的結果。

| 當時的推論 | 模擬的結果 |
|---|---|
| F1：一個 engine 就很閒，多的 engine 不是為了容量 | 成立。至少一個 engine 在忙的時間是 3.50%，一個 engine 時是 4.08% |
| F2、F3：通知與叫醒的時間和 engine 的數量無關 | 成立。`notify` 是 3.28 µs 與 3.32 µs |
| F4：有 engine 空著時 fault 不等 | 成立。`queue` 最長的一次從 7.19 µs 變成 0.00 µs |
| F5：先撐不住的仍然是 reclaimer | 成立。等 free frame 的次數是 9489 與 10484，沒有因為 engine 變多而減少 |
| F6：reclaimer 同時送幾個最好，要重掃，最好的值可能變大 | 成立，而且更進一步。4 個 engine 時 2 到 8 沒有明顯差別，見 1.3 |
| 同時在外的 COMPRESS 不超過 N 減 1，就一定有 engine 留給 fault | 只對一半。留下來的 engine 可能正在做別的 fault 的 DECOMPRESS，見 1.3 |
| F7：ring 裡排隊的只會更少 | ring 的最高佔用看不出差別，兩邊都是 4 格。在 ring 裡等的時間有差：`queue` 最長的一次是 7.19 µs 與 0.00 µs |
| F8、F9：N 個 job 共用一個 DRAM port，bus 那一段會變長 | 成立。平均只多 1.0 ns 一個 burst，最長的一次在基準負載多出 1.24 µs，負載 10 倍時多出大約 2 µs，見 F15 |
| F12：`HW-CPL-1` 的 checker 要一起改 | 已經改了，違規仍然是 0 |
| `engine_util` 的定義要改 | 已經改成每個 engine 的平均。另外列出至少一個在忙與全部在忙的比例 |

### 1.8 `reclaim_inflight` 的預設值從 1 改成 2 之後

負責人在 2026-11-13 同意這個參數可以改。選 2 的理由：它是讓等 free frame 的次數降下來的最小值，而且一個 engine 時也是最好的設定，N 之後有變也不用再調。4 個 engine 時 3 或 4 的結果差不多，見 1.3。

下表是 small、{{engines}} 個 engine、interrupt。每格依序是 p50、p99、最大值，單位 µs，最後是等 free frame 的次數。右欄取自 5.1。左欄是同一天稍早、預設值還是 1 的那一次完整執行，程式其餘部分相同。

| 負載 | `think_ns` | 預設值 1 | 預設值 2 |
|---|---|---|---|
| 基準 | 20000 | 6.35、7.10、7.89，0 次 | 6.33、6.98、11.50，0 次 |
| 4 倍 | 5000 | 6.35、7.53、15.02，0 次 | 6.35、7.81、12.05，0 次 |
| 10 倍 | 2000 | 6.39、28.54、36.23，258 次 | 6.40、8.24、14.94，10 次 |
| 20 倍 | 1000 | 6.57、40.04、45.96，1123 次 | 6.45、15.15、22.23，178 次 |
| 40 倍 | 500 | 9.56、41.61、49.99，1907 次 | 6.69、20.42、25.69，716 次 |

讀法有四點。

1. 負載 10 倍以上改善很大。等 free frame 的次數少了一個數量級，p99 從 28.54 µs 降到 8.24 µs。
2. 20 倍與 40 倍仍然有 fault 等不到 free frame。同時送 2 個把拐點往後推，沒有讓它消失。再往上要靠更早開始回收或更多同時在外的 COMPRESS，這裡沒有掃。
3. 基準負載的 p50 與 p99 幾乎沒有變。full、{{engines}} 個 engine 的基準，p99 是 7.01 µs 與 7.03 µs，最大值是 8.30 µs 與 8.46 µs。
4. small 基準的最大值從 7.89 µs 變成 11.50 µs。那一次是 F16 的那種 fault，整次執行只有 1 次。預設值是 1 的時候，基準負載沒有出現過這種 fault。次數太少，分不出是同時送 2 個讓它比較容易發生，還是時序變動之後剛好碰到。

5.2、5.3、5.4、5.9 四張表每一列都指定了 `reclaim_inflight`，改預設值之後逐項相同。

## 2. 怎麼跑的

| 項目 | full | small |
|---|---|---|
| 用途 | 基準 | 參數掃描與故障注入 |
| page frame 數 | 35840 | 512 |
| chunk 數 | 563200 | 8192 |
| page 數 | 148480 | 1792 |
| 低水位 / 高水位的 free frame 數 | 512 / 1024 | 16 / 48 |
| LZ4 engine 數，沒有另外寫的時候 | {{engines}} | {{engines}} |
| access 次數 | {{n_full}} | {{n_small}} |
| 跑一次的時間 | 約 30 s | 約 1 s |

四個 user SW：UI、MEDIA、NET、LOG，各自一個 thread。預設 4 個 core，每個 thread 一個 core。每個 user SW 在兩次 page access 之間自己做 `think_ns` 的事，預設 20000 ns。

LZ4 HW 的 model 有 N 個相同的 engine，N 是參數 `engines`。job ring 與 completion ring 各一個。HW 一次從 ring 取一個 descriptor，有 engine 空著才取，交給編號最小的空 engine。completion 照做完的順序寫出，一次寫一個。所有 engine 共用一個 DRAM master port：讀與寫各一個 channel，每個 channel 一次一個 burst，ring 的 burst 優先，engine 之間輪流。只有一個 job 在做的時候不用等。這個接法是 model 的假設，不是定案的設計，見介面規格 O14。

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
| `queue` | job 已經在 ring 裡，等 HW 取走。所有 engine 都有 job 時才會等 |
| `hw` | HW 讀 descriptor 到寫完 completion。包含在 DRAM port 等其他 job 的時間 |
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

除了 5.2 以外都用 small，每格 {{n_small}} 次 access。表格裡以階段命名的欄位是 RO page 解壓縮 fault 在那個階段的平均。標成最長的欄位是所有要等 LZ4 HW 的 fault 裡，那個階段最長的一次。「fault 碰到正在 COMPRESS 的 page」是整次執行裡發生的次數，見 F16。沒有 `engines` 一欄的表都是 {{engines}} 個 engine。

### 5.1 負載：`think_ns` 越小，access 越密

{{sweep:load}}

### 5.2 負載：full

每格 {{n_full}} 次 access，interrupt。`think_ns` 5000 是負載 4 倍，2000 是 10 倍。

{{sweep:full_load}}

每一次執行裡最慢的那一次 fault：

{{worst:full_load}}

### 5.3 reclaimer 同時在外的 COMPRESS 數

`think_ns` 固定在 2000，interrupt。讀法在 1.3。

{{sweep:reclaim_inflight}}

每一次執行裡最慢的那一次 fault：

{{worst:reclaim_inflight}}

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

### 5.8 engine 的數量：基準負載

`think_ns` 20000，reclaimer 同時送 2 個 COMPRESS，是預設值。engine 全滿是所有 engine 都有 job 的時間比例。

{{sweep:engines}}

### 5.9 engine 的數量：重負載

reclaimer 同時送 4 個 COMPRESS。`think_ns` 2000 是負載 10 倍，500 是 40 倍。port 互等是一個 burst 在 master port 等其他 job 的 burst 的平均時間。

{{sweep:engines_load}}

每一次執行裡最慢的那一次 fault：

{{worst:engines_load}}

engine 從 4 個變成 8 個，`queue` 最長的一次歸零，但 `hw` 最長的一次變長，p99 與最大值幾乎不變。原因是 8 個 engine 仍然共用一個 DRAM port，同時做的 job 越多，每個 job 在 port 上等得越久。

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
| N 個 engine 共用一個 master port 是 model 的假設。arbiter 是簡化的：讀寫各一個 channel，一次一個 burst，engine 之間輪流，沒有優先權 | 好幾個 job 同時做時的 `hw` 時間只是近似。實際的接法見介面規格 O14 |
| 這是 event 層級的 model，不是 cycle 層級。單一 job 的 cycle 數在硬體設計規格第 9 節，那裡仍然是一個 job 獨佔 port 的數字 | 兩份文件的 HW 時間不能直接相加 |
| burst 上沒有 engine 的編號。checker 對 `HW-MEM-1` 只能檢查一個 burst 落在 HW 手上某一個 job 的範圍內 | 一個 engine 寫到另一個執行中 job 的範圍，`HW-MEM-1` 抓不到，只有資料比對可能抓到 |
| 只有 4 個 user SW，同時最多 4 個 fault | fault 的 thread 比 engine 多的情況沒有跑到 |
| frame 與 chunk 的 bus error 在這個模擬器裡沒有模擬 | `BUS_ERROR` 之後 FW 怎麼做，由 `sim/hostsim` 執行過，見控制程序 3.6 與 7.3。它花多少時間還沒有數字 |
| 這個模擬器的 FW model 沒有自己的 LZ4 decoder | BAD_STREAM 在這裡直接算損毀。控制程序 3.6 的第二個意見只在 `sim/hostsim` 執行過 |
| workload 是合成的：固定的 hot set 加隨機的 cold access | 沒有 phase 變化，沒有 burst |
| small 的水位只有 16 與 48 個 frame | small 比 full 更容易用光 free frame，5.1 的拐點比 full 來得早 |

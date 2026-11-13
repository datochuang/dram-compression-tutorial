# kernel SW 的效率：該擔心什麼，不必擔心什麼

**對象**：team member 與 manager。知道 cache、TLB、CPU MMU 是什麼，不需要讀過壓縮層的規格。

**用途**：用定性的方式說明，壓縮層的 kernel SW 對系統效能的影響有多大、落在哪裡。不是量測報告。

**日期**：2026-11-12 第 0 版。2026-11-13 補上平台前提 P3 與 P4，N 暫定 4，引用的模擬數字換成 4 個 engine 的。等負責人補上其他平台前提後再修。

## 1. 結論

1. 壓縮層沒有在記憶體存取的路徑上發明一種新的機制。它是在一道已經存在的階梯上多加一階。
2. 在我們的平台上，kernel SW 今天就已經站在這道階梯上：每一次 TLB miss 都由 kernel SW 處理。壓縮層帶來的 fault 是 TLB miss 的一部分，不是另外多出來的一種中斷。
3. 平均效能由「多常發生」決定，而這主要是容量怎麼配置的問題，不是 kernel SW 寫得好不好的問題。
4. kernel SW 的效率仍然是問題，也應該好好優化。它決定的是尖峰與最壞情況的品質，也就是管理機制順不順。

## 2. 平台前提

| 前提 | 內容 |
|---|---|
| P1 | CPU MMU 沒有 hardware page table walk。TLB miss 之後一律由 kernel SW 處理 |
| P2 | multi-core、multi-thread。每個 core 有自己的 L1 cache，所有 core 共用一個 L2 cache |
| P3 | 每個 core 有一個 TLB，由該 core 的所有 hardware thread 共用。這一條目前是假設 |
| P4 | LZ4 HW 可以同時接受 N 個工作。N 暫定 4 |

## 3. 記憶體存取本來就是一道階梯

每一次記憶體存取，都是先試最快的那一層，不中才往下一層。越下面的一階，涵蓋的範圍越大，一次的代價越高，發生的次數越少。

| 階 | 沒中的時候發生什麼 | 誰處理 | 涵蓋的範圍 | 今天有沒有 |
|---|---|---|---|---|
| L1 cache | 去 L2 拿 | CPU 硬體 | 最小 | 有 |
| L2 cache | 去 DRAM 拿 | CPU 硬體 | 所有 core 共用，MiB 級 | 有 |
| TLB | 進 exception，kernel SW 查 page table、填 TLB | **kernel SW** | TLB 格數乘上 4 KiB | 有 |
| 不壓縮的 frame 區 | kernel SW 請 LZ4 HW 把 page 解壓縮回來 | kernel SW 與 LZ4 HW | 512 MiB 的設計裡約 140 MiB | **新增的一階** |

三個觀察：

- **在 frame 裡的 page，走的路和今天完全一樣。** TLB 中了就直接存取。TLB 沒中就由原本的 handler 填回去。壓縮層不在這條路上。
- **新增的一階排在 TLB 後面。** page 被壓縮時，它的 TLB entry 一定已經被清掉。所以每一次需要解壓縮的 fault，都先是一次 TLB miss。fault 的次數不可能超過 TLB miss 的次數。
- **新增的一階涵蓋的範圍比 TLB 大很多。** 所以它發生的次數只會是 TLB miss 的一小部分。這一小部分有多小，取決於負載，見第 7 節。

和「只有 CPU MMU」的系統相比：

| | 只有 CPU MMU | 加上壓縮層 |
|---|---|---|
| 存取可能進 exception 由 kernel SW 處理 | 是，每次 TLB miss | 是，同一個入口 |
| kernel SW 要查表、改表、拿 lock | 是 | 是，多兩張表 |
| 要清其他 core 的 TLB | 是，改 mapping 的時候 | 是，趕出 page 的時候 |
| real-time 的 thread 要避開 | 要 | 要。HRT 的記憶體不壓縮，HRT thread 不會碰到這一階 |
| 等一個硬體做完 | 沒有 | **新的**：等 LZ4 HW |
| 背景的回收工作 | 沒有，或只有 demand paging 的 | **新的**：選 page、壓縮 |

新的只有最後兩列。其餘都是已經在處理的同一類問題。

## 4. 幾個常見的擔心

| 擔心 | 比較準確的說法 |
|---|---|
| 每次記憶體存取都要經過 kernel SW | 不是。只有 page 不在 frame 區才進壓縮的路徑。其餘的存取和今天一樣 |
| kernel SW 一次只做一件事，所有 core 會排隊 | kernel SW 握 lock 的部分只有查表與改表。等 LZ4 HW 的那段時間不握 lock，其他 core 可以照常進出。真正會排隊的地方是 LZ4 HW 與回收的策略。照 P4，LZ4 HW 同時做 N 個工作，N 個以內不用排 |
| kernel SW 的指令多一倍，系統就慢一倍 | 中間隔了兩層。一次 fault 的時間，大部分是等 LZ4 HW 與被叫醒，kernel SW 自己的指令是小部分。而 fault 本身又只佔執行時間的一小部分 |
| 平均效能會被拖垮 | 平均由 fault 的次數決定。次數由「不壓縮的 frame 區相對於 working set 有多大」決定。這是容量配置，不是 kernel SW 的效率 |

第三列有一個模擬的比例可以參考。在合成負載、時間全部是假設值的模擬裡，一次解壓縮 fault 有一半的時間花在通知，LZ4 HW 佔兩成，kernel SW 自己的指令不到兩成。kernel SW 佔全部 core 時間的 1.29%。負載加到 10 倍時，先撐不住的是回收的策略，不是 kernel SW 的指令數，也不是 LZ4 HW。這些數字只能看比例，出處是 `spec/sim-results-v0.md`。2026-11-13 用 4 個 engine 重跑過，這幾個比例和一個 engine 時相同。模型是在 P1 指定之前做的，沒有算進 TLB miss handler。

## 5. 真正該擔心的

| 問題 | 為什麼是問題 | 屬於哪一類 |
|---|---|---|
| working set 超過不壓縮的 frame 區 | fault 會從偶爾變成連續，而且是陡的。一次 fault 比一次 L2 miss 貴很多，所以沒有緩衝 | 容量配置，產品要決定 frame 區多大 |
| 尖峰 | 切換畫面、掃過一個大 buffer、幾個 user SW 同時變忙，會讓一小段時間內 fault 連發。平均很好看，那一小段是卡的 | 管理機制 |
| 握 lock 的最長時間 | 目前選 page 的掃描在最壞情況下會握著 lock 繞完所有 frame。這比其他任何一段都長得多 | 管理機制，已知，有解法 |
| LZ4 HW 要服務所有 core | 一個 engine 時，急的解壓縮會排在不急的壓縮後面。模擬裡這一等在基準負載最長 7 µs，負載 10 倍時最長 16 µs。照 P4 暫定 4 個 engine 之後，同樣的模擬是 0 µs 與 2 µs | 管理機制，已知。4 個 engine 解掉大部分 |
| page 正在被壓縮時又被用到 | 這一次存取要等壓縮做完，再解壓縮回來。4 個 engine 的模擬裡，量到最慢的幾次 fault 都是這一種，多等 5 到 8 µs。engine 再多也沒有用 | 管理機制，2026-11-13 才看到。有兩個做法，還沒有評估 |
| frame 用完才開始回收 | fault 要等別人壓縮完才有 frame 可用 | 管理機制，已知，有解法 |

這些才是 kernel SW 值得花力氣的地方。它們的共同點是：重點不在每一步省幾道指令，而在每一段最長會多久、會不會互相卡住。

P4 改善的只有表裡的第四列。kernel SW 握 lock 的時間、通知與叫醒 thread 的時間、回收的策略，都和 LZ4 HW 同時能做幾個工作無關。lock 保護的是 kernel 的表，不是 LZ4 HW，所以 P4 也不會讓 lock 消失。

P4 也有代價。模擬裡 4 個 engine 共用一個 DRAM port，LZ4 HW 做一個工作最長的一次從 1.7 µs 變成 4 µs，平均幾乎不變。port 實際怎麼接還沒有決定。

這一類問題不是壓縮層獨有的。任何用 CPU MMU 做 demand paging 的系統都有同樣的問題，做法也是現成的：real-time 的部分避開、握 lock 的時間設上限、預留 free frame、急的工作優先。

## 6. P2 的影響：共用的 L2

所有 core 的 working set 本來就在同一個 L2 裡競爭。不壓縮的 frame 區是同一種共用資源，只是再往下一階。所以「幾個 core 同時變忙時互相擠壓」這件事，團隊在 L2 上已經有經驗，直覺可以沿用。

kernel SW 處理一次 fault 會碰到的表只有幾條 cache line，相對於 L2 很小。page 的 4 KiB 內容由 LZ4 HW 直接讀寫 DRAM，不經過 L2。

## 7. 還不知道的

| 不知道的 | 為什麼重要 |
|---|---|
| 真實負載下 fault 有多頻繁 | 第 1 節的第 3 點是前提，還不是量到的結果。現有的模擬用的是合成負載 |
| 這顆 CPU 的 TLB 有幾格、現有的 TLB miss handler 一次多久 | 有了這兩個數字，就能把新增的一階直接和已有的一階相比：次數是它的幾分之一，單價是它的幾倍 |
| interrupt 與叫醒 thread 實際要多久 | 一次 fault 裡最大的一塊，目前是假設值 |

## 8. 給 manager 的三句話

1. 壓縮層是在現有的 L1、L2、TLB 之後多加一階。kernel SW 今天就在處理 TLB miss，壓縮的 fault 是其中的一小部分。
2. 平均效能看的是不壓縮的區域配多大。kernel SW 的效率影響的是尖峰與最壞情況。
3. 要優化的地方是清楚的幾項：握 lock 的上限、回收同時送出兩個以上的壓縮、提早回收、page 正在被壓縮時又被用到的處理。它們和 demand paging 的老問題同類，不是未知的風險。

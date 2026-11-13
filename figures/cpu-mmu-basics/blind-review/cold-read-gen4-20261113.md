# 冷讀報告：cpu-mmu-basics 第 D 張（gen4）

- 日期：2026-11-13
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：cpu-mmu-basics 的第 D 張（gen4），`figures/cpu-mmu-basics/gen4/04-two-sides-two-rhythms.png`

---

## 圖 D：Two Sides, Two Rhythms: When the Kernel SW Wakes Up

先遮住底部 Key point 讀。

### 1. 人物與機器

這張圖沒有畫任何人物，也沒有畫任何機器，只有三條時間軸 lane、一張表和一個黃色框。

| 物件 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 最上面的 lane | `user SW` | 一條橘色長條，中間斷開一段，斷開處上方寫 `waits for its page` | 自己的 page 什麼時候回來，能不能繼續跑 |
| 中間的 lane | `kernel SW: CPU MMU side` | 一排很密的紫色短刻度。圖上說每個刻度是一次 TLB miss：讀一個 PTE、填一個 TLB entry | 頻率高、每次工作量小 |
| 下面的 lane | `kernel SW: compression layer side` | 只出現兩次，兩個虛線框：`page fault`（DECOMPRESS into a free frame）與 `reclaim`（COMPRESS a page, free its frame） | 很少發生，但每次工作量大 |
| 底下的時間軸 | `time`，附註 `spacing drawn to show the contrast, not measured` | 說明間距只是示意 | — |
| 表格 | `Side by side` | 兩欄對照 CPU MMU side 與 compression layer side | — |
| 黃色框 | `Where the two meet` | 列出兩個交會點 | — |

角色不清楚或缺席的地方：

- **兩條 kernel SW lane 是同一份 kernel，還是兩份？** 標籤都寫 `kernel SW:`，冒號後面是 side，我推測是同一個 kernel SW 的兩種工作，但畫面沒有明說。
- **硬體完全沒出場。** 表格裡出現 `LZ4 HW job`、`TLB`、`core`，但時間軸上沒有 LZ4 HW 的 lane，也沒有 CPU 或 TLB。沒有背景的讀者不知道 page fault 框裡的 DECOMPRESS 是 kernel 自己做還是交給硬體做；表格的 `lock, LZ4 HW job, lock again` 才給了線索。
- **刻度是誰的 TLB miss？** user SW 在等的那一段，CPU MMU 那一條仍然繼續有刻度（大約在 679 與 727 的位置）。既然這個 user SW 正停著，這些 TLB miss 應該是別的 thread 或別的 core 的，但圖上沒說。沒有背景的讀者會以為 lane 2 只服務 lane 1 這一個 user SW。

### 2. 看不懂的線或物件

1. **user SW 的缺口和 page fault 對不齊，因果看起來顛倒。** 橘色長條大約在 x≈652 斷開，在 x≈786 接回。觸發 page fault 的虛線（`this TLB miss finds the PTE invalid`）大約在 x≈706。也就是說 **user SW 在 TLB miss 發生之前就開始等了**。而 page fault 框一路畫到 x≈843，**user SW 卻在 fault 處理完之前就恢復了**。照常理，等待應該從那次 TLB miss 開始，到 fault 處理完才結束。一個仔細的工程師讀者會在這裡卡住。
2. **`waits for its page` 用橘色寫，和長條同色。** 第一眼可能讀成「橘色長條就是在等」，要再看一次才發現「等」是那個缺口。標籤若改成別的顏色、或者在缺口畫一段虛線並加上「running / waiting」的圖例，會比較清楚。
3. **「this TLB miss」沒有指到哪一個刻度。** 虛線從 x≈706 開始往下，但那個位置剛好在兩個刻度（≈679 與 ≈727）之間，不是落在某一個刻度上。讀者不確定是哪一次 TLB miss。
4. **右邊那根特別高的刻度身兼兩職。** 它同時是 `each tick: a TLB miss, read one PTE, fill one TLB entry` 這個圖例所指的範例，又是往下接到 reclaim 框、標著 `clear this page from every core's TLB` 的那一根。圖例說刻度是 TLB miss，可是 reclaim 那一條要表達的是「清掉 TLB entry」，不是 TLB miss。同一根刻度兩種意思，會讓人以為 reclaim 是由一次 TLB miss 觸發的。
5. **兩條虛線長得一樣，方向卻相反，而且都沒有箭頭。** 左邊那條的因果是 MMU 側 → 壓縮層側（TLB miss 發現 PTE 無效，於是進 page fault）。右邊那條的因果是壓縮層側 → MMU 側（reclaim 要求清掉每個 core 的 TLB）。沒有箭頭的話，讀者只能靠字推方向，而右邊那條的文字又和刻度的圖例混在一起。
6. **reclaim 期間 user SW 沒有斷。** 這點我讀懂了，意思是 reclaim 在背景做、不擋 user SW。但沒有背景的讀者可能會問：reclaim 是哪個 thread 在跑？它會不會也讓某個 user SW 停下來？圖上沒有交代，不過這對主旨影響不大。
7. **表格的 `how many` 列：是「多少個」什麼？** CPU MMU side 寫 `one per core, shared by its threads`，看得出是在講 TLB。compression layer side 寫 `one for the whole system`，是一個壓縮層？一份 page table？一個 LZ4 HW？還是一個 frame pool？列名沒有主詞，兩欄可能講的不是同一件東西。
8. **表格的 `who it serves` 列容易誤會。** compression layer side 寫 `only the kernel's own jobs`。可是上面的時間軸明明是 user SW 在等它的 page，壓縮層的工作最後是為了 user SW。讀者會覺得表和時間軸矛盾。我猜這一列想說的是「它的請求只來自 kernel，不是每次 load/store 都會碰到」，但字面上讀不出來。
9. 右上角的兩段紫色小字（`each tick: ...`、`clear this page from every core's TLB`）幾乎貼到圖的右邊緣，字也比較小，投影時可能看不清楚，或者被裁掉。

### 3. 圖說的一句話（不看 Key point）

同一個 kernel SW 有兩種工作：CPU MMU 這一邊每次 TLB miss 都要醒來做一點點事，非常頻繁；壓縮層這一邊只有在 page 搬進或搬出 frame 時才醒來，次數很少但每次比較重。兩邊只在「page fault 從 TLB miss 開始」以及「reclaim 要清掉 TLB」這兩個點交會。

### 4. 讀 Key point 之後：畫面和結論一致嗎？

Key point：*One kernel SW, two jobs: the CPU MMU side is small work done very often; the compression layer side is large work done only when a page moves.*

**一致。** 我只看畫面歸納出來的一句話和 Key point 幾乎相同：一個 kernel SW、兩種節奏、小而頻繁對大而稀少。

有兩點小落差：

- 「large work」在時間軸上只靠框比刻度寬來表達。要到表格 `work each time` 那一列才知道「大」在哪裡（lock、LZ4 HW job、再 lock）。
- Key point 只陳述差異，**沒有說出「所以不該合在一起設計」**。這張圖若是用來回應同事的提議，結論停在一半。標題 `Two Sides, Two Rhythms` 有暗示，但要讀者自己推。`One kernel SW` 這幾個字反而可能被提議合併的人拿去當理由：「既然本來就是同一個 kernel SW，為什麼不合在一起設計？」

### 5. 困惑指數

**2 / 5**。主旨（頻率與工作量的對比）一眼就懂。扣分是因為時間軸上的因果對不齊（user SW 在 TLB miss 之前就開始等、在 fault 做完之前就恢復），還有那根身兼兩職的高刻度。

### 6. 可疑的錯字或多餘文字

- 沒有看到拼錯的字。
- 重複：副標題、表格的 `how often` 列和 Key point 把同一句話講了三次。不算錯，但 Key point 可以騰出來講結論（為什麼要分開設計）。
- `waits for its page` 用和長條同色的橘色，容易誤讀（見第 2 題第 2 點）。
- `how many` 列缺主詞；`who it serves` 列的 `only the kernel's own jobs` 和時間軸的意思衝突（見第 2 題第 7、8 點）。
- 右上角兩段小字貼近右邊緣。

### 7. 用這張圖能不能回答同事「為什麼不合在一起設計」？

**大致可以，但要靠讀者自己推，圖沒有直接講出來。**

我用自己的話回答：

> 兩件事雖然都叫「page 的管理」，但節奏和性質差很多。CPU MMU 這一邊是每次 TLB miss 都要跑的熱路徑，每次只讀一個 PTE、填一格 TLB，而且它的規則是 CPU 給定的，我們改不了。壓縮層這一邊只有在 page 搬進或搬出 frame 時才跑，次數少，但每次要拿 lock、交給 LZ4 HW、再拿 lock，是我們自己設計、可以改的東西。把兩者綁在一起，等於讓每次都要跑的輕量 TLB refill 去背壓縮層的鎖與複雜度，或者讓我們能改的設計被 CPU 固定的規則綁死。兩邊真正交會的地方只有兩個：page fault 一定從 TLB miss 開始；reclaim 拿走 frame 時要把那個 page 從每個 core 的 TLB 清掉。所以比較合理的做法是分開設計，只把這兩個交會點的介面定清楚。

**圖哪裡幫到我：**

- 時間軸上密密的刻度對比兩個框，「頻率差很多」一眼就懂。
- 表格最後一列 `who designs it`（`comes with the CPU, fixed` 對比 `our own design, can change`）是最有力的論點，告訴我兩邊的設計自由度不同。
- 黃色框 `Where the two meet` 把交會點限縮成兩條，暗示介面可以很窄。

**圖哪裡讓我誤會或卡住：**

- 結論沒有明說。「不合併」要我從「兩種節奏」自己推，Key point 的 `One kernel SW` 甚至可能被拿來支持合併。
- `who it serves: only the kernel's own jobs` 讓我一度以為壓縮層和 user SW 無關，和時間軸上 user SW 在等 page 矛盾。
- user SW 的等待缺口和 fault 框對不齊，讓我懷疑 page fault 的因果順序是不是畫錯了。
- 那根高刻度讓我以為 reclaim 是由 TLB miss 觸發的，其實應該反過來，是 reclaim 去清 TLB。

---

## 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 | 是否建議重生 |
|---|---|---|---|---|
| D（gen4）`04-two-sides-two-rhythms.png` | 2 / 5 | 是。三條 lane 都有標籤；但沒有畫任何硬體，兩條 kernel SW lane 是否同一份要靠推 | 一致（Key point 只講差異，沒講「所以分開設計」） | 建議重生（局部修正，不必改構圖） |

**為什麼建議重生：**主旨清楚，構圖可以保留。但有一個工程讀者會挑出來的因果錯誤：user SW 的等待在 TLB miss 之前就開始、在 page fault 做完之前就結束。另外還有幾個會讓人誤會的地方。重生時建議：

1. user SW 的缺口從觸發 fault 的那次 TLB miss 開始，到 page fault 框結束才接回。
2. 觸發 fault 的虛線落在一個明確的刻度上。
3. 把「each tick」圖例的指示刻度和 reclaim 的「clear TLB」分開。clear TLB 改用不同的記號（例如一個 ✕ 或不同顏色），兩條虛線加上箭頭，標出相反的因果方向。
4. `waits for its page` 改用與長條不同的顏色，或在缺口畫上虛線。
5. 表格 `how many` 列補上主詞；`who it serves` 改成不會和 user SW 等 page 衝突的說法（例如「requests come from: every load/store」對比「requests come from: kernel only」）。
6. Key point 補一句結論，直接回答「所以分開設計，只在兩個交會點定介面」。

# 冷讀驗收報告：cpu-mmu-basics 圖 D（gen6）

- 日期：2026-11-13
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：cpu-mmu-basics 的第 D 張（gen6），`gen6/04-two-sides-two-rhythms.png`
- 讀者背景：只知道 CPU 沒有硬體 page table walk、TLB miss 由 kernel SW 處理，另有 LZ4 HW 壓縮層；同事主張兩者合併設計

## 1. 人物與機器

上半部是三條水平 lane 加一條 time 軸。

| 物件 | 我的理解 | 清楚嗎 |
|---|---|---|
| `user SW`（橙色線） | user 程式在跑。中間斷開一段，標 `waits for its page`，表示它停下來等 page | 清楚 |
| `kernel SW: CPU MMU side`（紫色短直線 tick） | 圖上說明 `each tick: a TLB miss, read one PTE, fill one TLB entry`。每一根 tick 是 kernel 的 TLB miss handler 跑一次 | 清楚 |
| `kernel SW: compression layer side` | 只有兩個虛線框：`page fault`（DECOMPRESS into a free frame）與 `reclaim`（COMPRESS a page, free its frame）。這一側只在這兩件事時醒來 | 清楚 |
| 菱形（在 CPU MMU lane 上） | `clear this page from every core's TLB`。reclaim 把 page 的 frame 拿走時，清掉所有 core 的 TLB 裡這個 page | 意思清楚；但菱形畫在 CPU MMU lane 上，誰執行它不完全確定（見第 2 題） |
| `time` 軸 | 時間由左到右；`spacing drawn to show the contrast, not measured` | 清楚 |
| `What sets the rate` 區 | 一條長條 `working set of user SW`，上面三個由小到大的括號：`TLB reach`、`L2`、`frames in DRAM` | 大致清楚，細節見第 2 題 |
| `Side by side` 表 | 兩欄對照 CPU MMU side 與 compression layer side，五列：rate set by、work each time、how many、on whose path、who designs it | 清楚 |
| `Where the two meet`（黃色便條） | 兩個交會點：every page fault begins as a TLB miss；taking a frame away clears that page from every TLB | 清楚，且和時間軸上兩條虛線箭頭一一對應 |

角色看不出來或沒有標籤的：

- `COT`（表格 how many 列，compression layer side 欄「one COT and one LZ4 HW for all cores」）：全圖沒有解釋 COT 是什麼。冷讀者只能猜是某種壓縮層的表。
- 誰觸發 `reclaim`：reclaim 框沒有任何箭頭進來，看不出是誰、因為什麼開始 reclaim（記憶體不夠？定時？）。
- CPU MMU lane 上的 tick 成對出現（`| |`），沒有說明為什麼成對。可能被讀成兩個 hardware thread、或兩個 core，也可能只是畫法。

## 2. 看不懂或讓人遲疑的線與物件

### 時間軸三條 lane 的對齊與因果

- **左邊的虛線箭頭（向下）**：從 CPU MMU lane 的一根 tick 往下指到 `page fault` 框，標 `this TLB miss finds the PTE invalid`。方向正確：TLB miss 在前、page fault 在後，是「page fault 起於 TLB miss」。清楚。
- **user SW 的斷口與 page fault 框的對齊**：橙線斷開的位置正好在那根 tick 上開始，合理。但橙線恢復的位置（約在 page fault 框右緣前一小段）比 page fault 框的右緣早一點，CPU MMU lane 的 tick 也在框結束前就恢復了。嚴格看會讀成「DECOMPRESS 還沒做完，user SW 就繼續跑、TLB 就又開始 miss」。差距小，多數讀者不會注意，但因果上應該是框結束之後才恢復。
- **page fault 結束後缺一個「重新 TLB miss、填入新 PTE」的 tick 標註**：圖沒有說 page fault 完成後 user SW 重跑那一次存取時發生什麼。冷讀者可以自己推，但不是圖給的。
- **右邊的虛線箭頭（向上）**：從 `reclaim` 框往上指到菱形，表示 reclaim 造成「清掉每個 core 的 TLB」。方向清楚。但菱形畫在 `kernel SW: CPU MMU side` lane 上，冷讀者可能誤以為是 CPU MMU 那一側的 handler 去做這件事；其實比較像是 reclaim 的 kernel SW 對 TLB 做的動作，結果落在 CPU MMU 這一側。
- **reclaim 期間 user SW 沒有停**：橙線在 reclaim 那段是連續的，暗示 reclaim 在背景進行、不擋 user SW。這是合理的讀法，但圖沒有明說。
- **user SW 等待期間沒有 tick**：等於說 user 停下來時沒有 TLB miss。在只有一個 user SW 的畫法下合理。

### 菱形

- 符號與 tick 不同，表示「不是 TLB miss，而是一次清除動作」。有旁邊文字，懂。

### What sets the rate

- **長條 `working set of user SW`**：user SW 正在用的 page 的總量。
- **三個括號**：從同一個左端起算，長度代表容量：`TLB reach`（TLB 能涵蓋的 page 量）最短，`L2` 中等，`frames in DRAM`（未壓縮存放的 frame 總量）最長，但比 working set 還短。
- **兩個紫色標籤**：
  - `past the TLB reach: TLB misses`：意思是 working set 超出 TLB reach 的部分會造成 TLB miss。但這個標籤擺的位置大約在 TLB reach 右端到 L2 右端之間，沒有用箭頭或刻度標出起點。冷讀者可能讀成「只有落在 TLB reach 與 L2 之間的那一段才產生 TLB miss」，而不是「超出 TLB reach 之後的全部」。
  - `past the frames: page faults`：意思是 working set 超出 frames 的那一小段造成 page fault。標籤的左半其實落在 frames 範圍內，同樣沒有起點刻度。意思讀得出來，但對位不精確。
- **L2 的角色**：L2 被畫成和 TLB reach、frames 同一把尺上的一個容量括號，但旁邊註明 `L2 changes the cost of each event, not the count`。所以 L2 不決定頻率，只決定每次事件的成本（例如 PTE、壓縮層的表是否還在 L2 裡）。文字講清楚了，但把它畫在「What sets the rate」標題下、和決定頻率的兩個括號並列，第一眼會以為它也是一個門檻。要靠旁註才會反過來理解。「成本」具體是什麼（PTE 讀取是否 hit L2？），圖上沒有說。
- **`not to scale; a faster-moving working set raises both rates`**：補上了「不只是大小，working set 變動得快也會讓兩邊頻率都變高」。這句很重要，但寫在右邊角落、字小，容易漏看。
- **和表格的小落差**：表格 `rate set by` 寫的是「short-term working set」對「long-term working set」，但長條只畫了一條 working set。冷讀者會問：短期與長期 working set 是同一條長條的不同看法，還是兩個東西？圖沒有把這個區分畫進長條。

## 3. 圖說的一句話（只看畫面）

CPU MMU 這一側的 kernel SW 在每次 TLB miss 都要醒來做一件小事，頻率由 TLB reach 對 working set 決定；壓縮層這一側的 kernel SW 只在 page 進出 frame 時才醒來做一件大事，頻率由 frames 對 working set 決定；兩邊只在「page fault 從 TLB miss 開始」與「拿走 frame 時清 TLB」兩點相接。

## 4. Key point 與畫面是否一致

Key point：「Two different jobs: the CPU MMU side is small work done very often; the compression layer side is large work done only when a page moves. They touch at just two points.」

**一致。** 時間軸（密集 tick 對兩個大框）、表格（read one PTE 對 lock + LZ4 HW job）、黃色便條與兩條虛線箭頭（兩個交會點）都直接支持這句話。

Key point 沒有提到 `What sets the rate` 區與 L2 的角色，所以中段的內容沒有被結論收進來，但不衝突。

## 5. 困惑指數

**2**。主訊息一眼可懂；扣分在於 What sets the rate 的紫色標籤沒有對位刻度、L2 畫在「決定頻率」區裡要靠旁註才知道它不決定頻率、COT 沒解釋，以及 user SW 恢復時間比 page fault 框早一點。

## 6. 可疑的錯字或多餘文字

- 沒有發現錯字。
- `COT`：未定義縮寫，對冷讀者等於多餘或缺說明。
- 標題副標與 Key point 內容高度重疊（兩者都在講「每次 TLB miss」對「page 進出 frame」），可以接受，但略重複。
- `spacing drawn to show the contrast, not measured` 與 `not to scale` 兩個免責聲明各管一區，不算多餘。
- 表格 `who designs it` 的 CPU MMU side 欄寫「comes with the CPU, fixed」：在「沒有硬體 page table walk、TLB miss 由 kernel SW 處理」的平台上，TLB miss handler 與 page table 的格式其實是 kernel 自己寫、自己決定的。這一格容易讓讀者以為 CPU MMU 那一側整個不能動。若它只指 TLB 硬體本身（格數、共用方式），應該寫清楚。這是內容上的疑點，不只是字面問題。

## 7. 用自己的話回答

### (a) 為什麼 CPU MMU 這邊的 kernel SW 比壓縮層那邊常被叫起來？什麼會讓兩邊頻率變高？L2 扮演什麼角色？

- TLB 很小，能涵蓋的 page 量（TLB reach）遠小於 DRAM 裡的 frame 數。working set 只要超出 TLB reach 就會一直 TLB miss，而這個平台每次 TLB miss 都要 kernel SW 去讀 PTE、填 TLB。壓縮層只有在 working set 超出 frames、需要把 page 移進或移出 frame（page fault 解壓、reclaim 壓縮）時才需要 kernel。frames 遠大於 TLB reach，所以壓縮層醒來的次數少得多。而且 CPU MMU 這邊在每一次 load/store 的路上，壓縮層只在「page 沒有 frame」的那一次存取路上。
- 讓頻率變高的：working set 變大（超出 TLB reach 越多，TLB miss 越多；超出 frames，page fault 開始出現），以及 working set 變動得快（圖右下角的註：faster-moving working set 兩邊頻率都升高）。
- L2 不改變次數，只改變每次事件的成本：TLB miss handler 要讀的 PTE、壓縮層用到的表若還在 L2 裡，每次處理就比較快；不在就要去 DRAM。圖沒有說明成本的具體差異。

### (b) 能不能用這張圖回答同事「為什麼不合在一起設計」？

可以回答一部分。

圖幫到的地方：
- 一眼看出兩邊的節奏差很多：一邊是高頻小事，一邊是低頻大事。把壓縮層的邏輯塞進 TLB miss 路徑，會讓每一次 TLB miss 都變貴（表格 `on whose path` 列支持這個推論）。
- 兩邊的資源規模不同：一個 core 一個 TLB 對全系統一個 COT 與一個 LZ4 HW。
- 黃色便條與兩條虛線箭頭把「交會點只有兩個」講得很具體，等於告訴同事：要一起設計的只有這兩個介面，其餘可以分開。

圖讓人誤會或沒說到的地方：
- 圖的論證是「兩邊不同」，沒有明說「所以合在一起會怎樣不好」。冷讀者要自己推出「合併會把壓縮層的成本加到每次 TLB miss 上」這一步。
- `who designs it: comes with the CPU, fixed` 可能讓同事反駁：既然 TLB miss handler 是 kernel SW、page table 格式也由 kernel 決定，CPU MMU 這一側並不是完全固定的，那為什麼不能一起設計？這一格反而可能削弱論點。
- 兩個交會點本身（PTE 無效的表示方式、清 TLB 的時機）其實需要兩邊一起決定，圖沒有說這兩點是「要共同設計的介面」，容易被讀成「兩邊完全無關」。

## 總表

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 |
| 角色是否清楚 | 是（唯一例外是 COT 未解釋、reclaim 的觸發者沒畫） |
| 畫面與結論是否一致 | 一致 |
| 是否建議重生 | 不建議 |

不建議重生的理由：困惑指數低於 3，角色清楚，因果箭頭方向正確，畫面與 Key point 一致。

可以考慮的小修（不需要重生也可以用文字或後製處理）：

1. What sets the rate 的兩個紫色標籤加上起點刻度或箭頭，對準「TLB reach 右端之後」與「frames 右端之後」。
2. L2 括號換個樣式（例如虛線或灰色），或把旁註放大，讓人一看就知道它不是決定頻率的門檻。
3. `COT` 寫出全名或加一句說明。
4. user SW 的橙線與 CPU MMU 的 tick 在 page fault 框結束之後才恢復。
5. `who designs it` 的 CPU MMU side 欄改寫，區分「TLB 硬體固定」與「TLB miss handler 與 page table 格式由 kernel 決定」。

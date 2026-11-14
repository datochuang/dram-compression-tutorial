# 冷讀報告：gen4/02-apart-in-space-and-time.r4.png

- 日期：2026-11-14
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：two-stage-task 的 `gen4/02-apart-in-space-and-time.r4.png`

標題是「CPU MMU and Compression Layer: Apart in Space and Time」，副標寫著「The CPU MMU stands on every access inside each core. The compression layer stands beside DRAM and works only when a page swaps.」。下面先遮住底部的 Key point 作答。

## 1. 機器與方塊

上半部「Space: where each one sits」

| 方塊 | 標籤 | 我讀成在做什麼 |
|---|---|---|
| 外框 | processor | 整顆 processor，上方有「ON EVERY ACCESS」標籤 |
| 兩個子框 | Core 0、Core 1 | 兩個 core，結構相同 |
| 每個 core 裡的兩個小框 | hw thread | 每個 core 有 2 個 hardware thread |
| 每個 core 裡的淺藍框 | CPU MMU and TLB | 每個 core 一個 MMU 加 TLB，兩個 thread 共用 |
| 每個 core 裡的淺藍框 | L1 | 每個 core 自己的 L1 |
| processor 底部的長淺藍框 | L2 | 兩個 core 共用的 L2 |
| 綠色框，有齒輪 | LZ4 HW / outside the processor | 壓縮引擎，在 processor 外面；上方標「OFF THE ACCESS PATH」 |
| 紫色虛線框 | kernel SW: TLB miss / read one PTE, fill the TLB | TLB miss 時 kernel SW 讀一筆 PTE、填 TLB |
| 紫色虛線框 | kernel SW: page swap / read the COT, hand LZ4 HW a job | page swap 時 kernel SW 查 COT、交一個 job 給 LZ4 HW |
| DRAM 大框 | DRAM | 外部記憶體，分成四區 |
| 4 個空白方格 | frame region: hot pages | 未壓縮、常用的 page |
| 4 個斜線方格 | chunk pool: cold pages | 壓縮過、不常用的 page（斜線 = 壓縮） |
| 表格 | page table | page table |
| 表格 | COT: where each compressed page is | 記錄每個壓縮 page 在哪裡的表 |

下半部「Time: how often each one works」有三條橫列：「CPU MMU: TLB lookup」、「kernel SW: TLB miss」、「kernel SW and LZ4 HW: page swap」，最下面是 time 軸。右下有「Why page swap is rare」示意框與黃色的「Rare, but each one counts」框。

**沒有無標籤的方塊。** 角色看得出來，但有三點不確定：

- 兩個 kernel SW 虛線框畫在 processor 的**外面**、右上角，靠近 LZ4 HW。第一眼會以為 kernel SW 是 processor 外的另一個東西。藍字「kernel SW runs on whichever core needs it」有補救，但它寫在右下角，離兩個框有一段距離，而且框的位置還是在說「外面」。
- 標題的「Compression Layer」到底指什麼？只指 LZ4 HW，還是 LZ4 HW 加上 kernel SW: page swap？圖上沒有一個框叫 compression layer。從副標「stands beside DRAM」推測是 LZ4 HW；但時間軸那一列寫的是「kernel SW and LZ4 HW: page swap」，又像是兩者合起來。
- COT、PTE、WCET 三個縮寫都沒有展開。COT 有說明文字（where each compressed page is），還算可猜；PTE 和 WCET 沒有背景的人不懂。

## 2. 看不懂的線或物件

1. **TLB miss 怎麼叫起 kernel SW，圖上沒有畫。** 從 CPU MMU and TLB 到「kernel SW: TLB miss」沒有箭頭（例如 exception），只有反方向的「fills the TLB」。讀者看得到結果，看不到觸發。
2. **存取路徑畫在 Core 0，fills the TLB 卻指向 Core 1。** 橘色的「every load and store」只畫在 Core 0（hw thread → CPU MMU and TLB → L1 → L2），紫色的「fills the TLB」卻指到 Core 1 的 MMU。第一眼會以為「Core 0 miss，kernel 去填 Core 1」，然後才想到兩者只是各舉一例。
3. **線交叉。** 從「kernel SW: TLB miss」往下到 page table 的紫色直線，和從「kernel SW: page swap」往左到 LZ4 HW 的「a job」箭頭交叉。「one PTE」這個標籤夾在兩條線之間，會一時分不清它是哪一條的。順著線走一次可以分清楚，但會停頓。
4. **page swap 沒有碰 page table。** page swap 只有「a job」（到 LZ4 HW）和「which chunks」（到 COT）兩條線，沒有線到 page table，也沒有 TLB 的清除。讀者會以為 page swap 不改 page table。可能是刻意簡化，但圖上看不出來。
5. **COMPRESS／DECOMPRESS 只畫輸出。** DECOMPRESS 從 LZ4 HW 指向 frame region，COMPRESS 指向 chunk pool。方向讀得懂（寫到哪裡），但資料從哪裡讀進 LZ4 HW 沒畫，因此看起來像 LZ4 HW 憑空產出資料。不致誤解。
6. **「on an L2 miss」的橘色虛線** 從 L2 指向 frame region，清楚。
7. DECOMPRESS 字上方有一個小點，像生成的雜點。

方向上沒有和故事矛盾的箭頭。

## 3. 圖說的一句話（不看 Key point）

CPU MMU 在每個 core 裡、每一次存取都經過它，kernel SW 為了 TLB miss 常常被叫起；LZ4 HW 在 processor 外、DRAM 旁，只有在 page swap 時才和 kernel SW 一起動作，次數很少，但每次都昂貴。

## 4. 空間

- **CPU MMU**：在 processor 裡、每個 core 各一個，位在 hw thread 和 L1 之間。它**在每一次存取的路上**（橘色箭頭穿過它）。TLB miss 時由 kernel SW 查 **page table**（一筆 PTE）。
- **LZ4 HW**：在 processor 外，標「outside the processor」與「OFF THE ACCESS PATH」，畫在 DRAM 上方。它**不在存取的路上**。查的表是 **COT**，但不是 LZ4 HW 自己查，是 kernel SW: page swap 查 COT 之後交 job 給它。
- 一個小落差：圖上「查哪張表」都是 kernel SW 在查，不是 MMU 或 LZ4 HW 自己查。這和題意相符，但沒背景的讀者可能要想一下才知道「CPU MMU 對應 page table、compression 對應 COT」。

## 5. 時間

- **CPU MMU: TLB lookup**：密密麻麻的橘色細線，幾乎每一刻都有。
- **kernel SW: TLB miss**：稀疏、不規則的紫色短線，大約每隔一小段就有一次，比 lookup 少很多，但仍然常見。
- **kernel SW and LZ4 HW: page swap**：整條時間軸只有兩次，每次是一個紫色虛線「page swap」框加一個綠色齒輪，寬度比其他兩列的事件大，暗示一次花比較久。
- 底下註明「spacing drawn to show the contrast, not measured」，誠實，好。

**「Why page swap is rare」我讀成的論點**：user SW 長時間會碰到的 page（長白條）大部分都放得進 frame region（括號），只有超出 frame region 的那一小段（斜線，壓縮的）才會造成 page swap；而大部分存取其實在 L2 就結束了。所以 page swap 只發生在工作集長出 frame region 的時候。

說服力：中等。

- frame region 比長白條短一點、斜線尾巴很小，這個「只有超出的部分才 swap」的意思清楚。
- **L2 那一條的角色不清楚。** 「L2: where most accesses end」畫成一條短條，放在 frame region 的括號裡。它的長度代表容量還是存取比例？而且壓縮過的 page 本來就不在 L2，L2 命中率高不會直接減少 page swap，它減少的是 DRAM 存取。這一條放在「Why page swap is rare」裡，論證跳了一步。
- 「those pages」指代模糊：是「user SW 長時間碰到的 page」。
- swap 的頻率其實取決於多常碰到斜線那一段，而不只是它有多大。圖用大小代表頻率，沒有背景的讀者會接受，但推敲時會覺得少一步。

黃色框「Rare, but each one counts」：每次 page swap 要 locks、一次 COT lookup、一個 LZ4 HW job；等它的 user SW 感受到的是最壞情況，所以要為 WCET 做預算。意思清楚，但「locks」沒說是誰的 lock，WCET 沒展開。

## 6. 讀 Key point 之後

Key point：「The CPU MMU sits inside every core, on every access, and wakes kernel SW often. The compression layer sits outside, beside DRAM, and works only on page swap: rarely, but each time counts toward the worst case.」

**判定：一致。**

- 「inside every core, on every access」：上半部兩個 core 都有 CPU MMU and TLB，橘色路徑穿過它。一致。
- 「wakes kernel SW often」：時間軸的紫色 TLB miss 短線、上半部的 kernel SW: TLB miss 框。一致。不過「wakes」這個觸發在上半部沒有箭頭（見 2.1）。
- 「sits outside, beside DRAM」：LZ4 HW 畫在 processor 外、DRAM 上方。一致。
- 「works only on page swap: rarely, but each time counts toward the worst case」：時間軸只有兩次、黃色框講 WCET。一致。
- 唯一的模糊：Key point 的「compression layer sits outside」只對 LZ4 HW 成立；page swap 的 kernel SW 部分在 core 上跑（右下藍字）。如果 compression layer 包含 kernel SW，就不是全部在外面。這不構成不一致，只是用詞的範圍沒有定義。

## 7. 困惑指數

**2**。主要意思（MMU 在路上、頻繁；LZ4 HW 在路外、稀少但貴）一眼就懂；停頓來自 kernel SW 框畫在 processor 外、Core 0／Core 1 的例子不對齊、一處線交叉，以及「Why page swap is rare」裡 L2 那一條的角色。

## 8. 可疑的錯字或多餘文字

- 沒看到錯字。
- DECOMPRESS 字上方一個小雜點。
- 「kernel SW runs on whichever core needs it」放在右下角、藍色，與它要說明的紫色 kernel SW 框距離遠，顏色也不同。
- 「L2: where most accesses end」在「Why page swap is rare」框裡偏離論點，可考慮刪去或改寫。
- PTE、WCET 沒展開（不是錯字，但沒有背景的讀者會卡住）。

## 顏色

| 顏色 | 我讀成 |
|---|---|
| 橘色 | 存取路徑與 CPU MMU 的頻繁動作（上半部的路徑、下半部的 TLB lookup 線） |
| 淺藍底 | processor 內的硬體方塊（CPU MMU and TLB、L1、L2） |
| 紫色（虛線框、箭頭、短線） | kernel SW 的動作 |
| 綠色（框、齒輪、箭頭） | LZ4 HW 與它搬的資料（COMPRESS、DECOMPRESS） |
| 斜線 | 壓縮過的資料 |
| 黃色底 | 要注意的結論、警告 |
| 藍色字 | 補充說明 |

整體一致：橘色、紫色、綠色在上下兩半的意思相同，齒輪在兩處都代表 LZ4 HW。唯一的小不一致是說明 kernel SW 的那句話用藍色，不是紫色。

## 用我自己的話說結論

CPU MMU 是每個 core 裡的常駐關卡，每一次讀寫都經過它，TLB 不夠時還要常常叫 kernel SW 來補；壓縮硬體則在 processor 外面、DRAM 旁邊，平常不在路上，只有在 page 太多、放不進未壓縮區而要換進換出時才出動。它出動的次數很少，但每次都要 kernel 拿 lock、查表、等硬體，等的那個程式會碰到最壞延遲，所以要以最壞情況來設計。

## 總表

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 |
| 角色是否清楚 | 是 |
| 畫面與結論是否一致 | 一致 |

## 是否建議重生

**不建議重生。** 困惑指數 2、角色清楚、箭頭方向沒有與故事矛盾、畫面與 Key point 一致，不符合重生條件。

如果要做小修，依重要程度：

1. 從 CPU MMU and TLB 加一條到「kernel SW: TLB miss」的箭頭（例如「TLB miss → exception」），讓「wakes kernel SW」在空間圖上看得到。
2. 讓存取路徑和「fills the TLB」落在同一個 core，或在 Core 1 也畫存取路徑。
3. 把「kernel SW runs on whichever core needs it」移到兩個 kernel SW 框旁邊，改成紫色。
4. 「Why page swap is rare」裡 L2 那一條改寫或刪除，讓論點只剩「工作集只比 frame region 多一點點」。
5. 避開「one PTE」直線與「a job」箭頭的交叉。

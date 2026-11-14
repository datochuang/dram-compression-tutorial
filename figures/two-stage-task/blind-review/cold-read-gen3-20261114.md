# 冷讀報告：gen3/02-apart-in-space-and-time.png

- 日期：2026-11-14
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：two-stage-task 的 `gen3/02-apart-in-space-and-time.png`

先遮住底部 Key point 讀畫面。要注意的是，標題下方那一行藍色副標題（「The CPU MMU stands on every access inside each core. The compression layer stands beside DRAM and works only when a page swaps.」）其實已經把結論先講出來了。所以「先不看 Key point」的效果打了折扣，讀者還沒看畫面就先拿到結論。

---

## 1. 機器與方塊

| 方塊（標籤） | 我讀成什麼 | 清楚嗎 |
|---|---|---|
| `processor` 大框 | 整顆 processor，裡面有兩個 core 和共用的 L2 | 清楚 |
| `Core 0`、`Core 1` | 兩個 core，每個 core 裡面有兩個 `hw thread`、一個 `CPU MMU and TLB`、一個 `L1` | 清楚 |
| `hw thread`（每個 core 兩個） | hardware thread，存取從這裡發出（Core 0 左邊那一個拉出橘色線） | 清楚 |
| `CPU MMU and TLB`（每個 core 一個） | 每個 core 一個 MMU 加 TLB，同一個 core 的兩個 thread 共用 | 清楚 |
| `L1`（每個 core 一個） | 每個 core 自己的 L1 | 清楚 |
| `L2`（藍色長條） | 兩個 core 共用的 L2 | 清楚 |
| `ON EVERY ACCESS` 標牌 | 說明 processor 這一邊在每一次存取的路上 | 清楚 |
| `kernel SW: TLB miss`（紫色虛線框）「read one PTE, fill the TLB」 | TLB miss 時跑的 kernel 程式，讀一個 PTE 後填進 TLB | 角色清楚，**位置不清楚**：畫在 processor 外面、浮在半空，看不出它其實在某個 core 上跑。沒有線表示它是被誰叫起來的（TLB miss 怎麼變成 kernel 介入沒有畫） |
| `kernel SW: page swap`（紫色虛線框）「read the COT, hand LZ4 HW a job」 | 做 page swap 的 kernel 程式，查 COT，然後交一個 job 給 LZ4 HW | 角色清楚，位置同樣不清楚；也看不出是什麼觸發它 |
| `OFF THE ACCESS PATH` 標牌 | LZ4 HW 不在存取的路上 | 清楚 |
| `LZ4 HW`（綠色、有齒輪）「outside the processor」 | processor 外面的壓縮／解壓縮硬體 | 清楚 |
| `DRAM` 大框 | 記憶體，用虛線分成四區 | 清楚 |
| `frame region: hot pages`（四個空白方格） | 放熱 page 的地方，存取直接到這裡 | 清楚 |
| `page table`（表格） | kernel 的 page table，放在 DRAM | 清楚 |
| `COT: where each compressed page is`（表格） | 記錄每個壓縮過的 page 放在哪裡的表。COT 三個字沒展開，但說明文字夠用 | 大致清楚 |
| `chunk pool: cold pages`（四個斜線方格） | 冷 page 壓縮後放的地方 | 大致清楚：斜線代表「壓縮過」是我猜的，圖上沒有圖例 |

沒有無標籤的方塊。角色看不出來的地方只有一個重點：**兩個 kernel SW 框在空間上屬於哪裡**。它們被畫在 processor 外面，跟 LZ4 HW 同一排，第一次看的讀者可能以為 kernel SW 是另一塊獨立的東西。

## 2. 看不懂的線或物件

- **橘色線「every load and store」**：從 Core 0 的一個 hw thread 往下穿過 CPU MMU and TLB、L1、L2，一直到 DRAM 的 frame region。意思清楚，但它一路畫到 DRAM，會讓人以為每一次 load/store 都打到 DRAM。右下角卻說「L2: where most accesses end」。兩處說法有點打架。
- **只有 Core 0 有橘色線，只有 Core 1 收到「fills the TLB」**：猜得出來是舉例，但不對稱，讀者會想 Core 1 不存取嗎？Core 0 的 TLB 不會被填嗎？
- **「one PTE」紫色箭頭**：從 kernel SW: TLB miss 往下指到 page table 區。框裡寫的是「read one PTE」，箭頭卻指向 page table，看起來像是在寫 page table。資料流向和箭頭方向相反。同樣的情形出現在「which chunks」箭頭（從 page swap 指向 COT，但框裡寫的是 read the COT）。看得懂，但要多想一下。另外「one PTE」的箭頭頭落在 page table 表格右邊的空白處，不是落在表格上。
- **綠色 DECOMPRESS 長斜線**：從 LZ4 HW 一路斜到左邊的 frame region，中途**穿過「one PTE」與「which chunks」兩條紫色直線**。我第一眼差點以為 DECOMPRESS 和 page table 有關係。這是唯一讓我短暫看錯路線的交叉。
- **LZ4 HW 的輸入沒畫**：COMPRESS 畫成 LZ4 HW → chunk pool，DECOMPRESS 畫成 LZ4 HW → frame region，只畫了輸出。COMPRESS 從 frame region 讀、DECOMPRESS 從 chunk pool 讀，這兩段都沒畫。讀者要自己補。
- **觸發關係沒畫**：TLB miss 怎麼從 CPU MMU 跳到 kernel SW、page swap 是被什麼（fault？空間不夠？）叫起來的，都沒有線。
- **斜線方格**：沒有圖例，只能從「cold pages」「COMPRESS」推測代表壓縮過的資料。
- **紫色虛線框**：虛線代表「軟體」還是「有時才出現」？沒說明，不過顏色與「kernel SW」字樣夠用了。

## 3. 圖說的一句話（不看 Key point）

CPU MMU 在每個 core 裡，每一次存取都經過它，偶爾叫 kernel 填 TLB；LZ4 HW 在 processor 外、DRAM 旁邊，不在存取的路上，只有 page swap 時才由 kernel 交 job 給它，雖然少見，但每次都很貴。

## 4. 空間（只看上半部）

- **CPU MMU**：在 processor 裡，每個 core 一份。它在每一次存取的路上（橘色線穿過它，標牌寫 ON EVERY ACCESS）。它自己查的是 **TLB**。TLB 沒有的時候由 kernel SW 去查 **page table**，再把結果填回 TLB。圖沒有直接說「硬體不自己走 page table」，但從「kernel SW: TLB miss → read one PTE → fills the TLB」可以推出來。
- **LZ4 HW 這一邊**：在 processor 外面、DRAM 旁邊（標牌 OFF THE ACCESS PATH）。不在任何一次存取的路上。查的是 **COT**，但查 COT 的是 kernel SW: page swap，不是 LZ4 HW 自己。LZ4 HW 只是收 job、寫 frame region 或 chunk pool。
- 誰在路上：hw thread → CPU MMU and TLB → L1 → L2 → DRAM frame region。誰不在：LZ4 HW、COT、chunk pool、兩個 kernel SW 框。
- 小疑問：kernel SW: TLB miss 是「在路上」還是「不在路上」？它在 TLB miss 時會擋住那一次存取，但畫的位置在 processor 外面，跟 OFF THE ACCESS PATH 那一邊比較近。

## 5. 時間（只看下半部）

- **CPU MMU: TLB lookup**：橘色密密麻麻、連成一片，代表每一次存取都動作，幾乎一直在動。
- **kernel SW: TLB miss**：紫色短直線，不規則但常常出現，大約幾十條。
- **kernel SW and LZ4 HW: page swap**：整條時間軸上只有兩個綠色「page swap」方塊，比較寬，代表每次比較久、但很少發生。
- 下方註明「spacing drawn to show the contrast, not measured」，誠實地說間距不是量測值。好。
- 小不一致：這一列的標籤寫「kernel SW and LZ4 HW」，方塊卻只有綠色（LZ4 HW 的顏色）。kernel SW 的紫色在這一列看不到。

**「Why page swap is rare」**：我讀成一個容量的論點。
- 最上面的括號是 frame region（hot pages），很寬。
- 左邊一個很小的括號是 L2，「where most accesses end」。
- 下面一條「pages user SW touches」長條，大部分落在 frame region 的範圍內，只有右端一小段斜線超出去。
- 文字：frame region 是 L2 的好幾倍；只有 working set 長得比 frame region 大時才會 page swap。

論點是「frame region 很大，大部分要用的 page 都放得下，只有超出的那一小段需要 swap，所以 swap 少」。

**說服力**：中等，有幾個地方不清楚。
- 這是**容量**的論點，但「少見」說的是**次數**。swap 多不多，要看超出的那一段（斜線）被存取得多不多，而長條本身沒有表達存取頻率。如果超出的 page 剛好常被碰，swap 一樣會很頻繁。上半部的「cold pages」暗示那一段很少碰，但這一塊裡面沒有說。
- **L2 括號為什麼出現在這裡**看不懂。它跟 page swap 少不少沒有直接關係；我猜是想說 TLB miss 或存取多半停在 L2，但這一塊的標題是「Why page swap is rare」，放 L2 反而分散注意力。L2 的小括號很小，又只有一個鉤子，文字「L2: where most accesses end」寫在鉤子右邊，看起來像是在標一段更長的範圍。
- 文字用「working set」，長條用「pages user SW touches」，要自己對起來。
- 斜線那一段約佔整條的一成多，視覺上不算「很少」。

**「Rare is not free」**（黃框）：每次 page swap 要拿 lock、查 COT、跑一個 LZ4 HW job；等它的 user SW 感受到的是最壞情況，所以要算 WCET。論點清楚。WCET 沒展開；「locks」在上半部完全沒有畫。

## 6. 讀 Key point 之後：畫面和結論一不一致

Key point：「The CPU MMU sits inside every core, on every access, and wakes kernel SW often. The compression layer sits outside, beside DRAM, and works only on page swap: rarely, but each time counts toward the worst case.」

**判定：一致。**

- 「inside every core, on every access」：上半部的 CPU MMU and TLB 位置、橘色線、ON EVERY ACCESS 標牌都對得上。
- 「wakes kernel SW often」：時間列的紫色短線對得上。
- 「outside, beside DRAM」：LZ4 HW「outside the processor」、OFF THE ACCESS PATH 對得上。
- 「works only on page swap: rarely」：兩個綠色方塊對得上。
- 「each time counts toward the worst case」：黃框對得上。

保留意見（不影響「一致」的判定，但值得注意）：
- 「compression layer」這個詞在畫面上沒有任何一個框叫這個名字。讀者要自己決定它指 LZ4 HW 一個，還是 kernel SW: page swap + LZ4 HW + COT + chunk pool 一整組。如果是後者，kernel SW: page swap 其實在 core 上跑，說「sits outside」就不完全對；畫面把 kernel SW 畫在 processor 外面，剛好掩蓋了這一點。
- 副標題幾乎就是 Key point 的另一個版本，資訊重複。

## 7. 困惑指數

**2 / 5**。結構（上空間、下時間、右邊論點、底下結論）一看就懂，主要訊息一眼就讀得到；扣分在 kernel SW 沒有位置、DECOMPRESS 線交叉、「Why page swap is rare」裡 L2 括號用途不明，以及只用容量講次數。

## 8. 可疑的錯字或多餘文字

- 沒看到拼字錯誤。
- 多餘：副標題與 Key point 內容幾乎相同。
- 縮寫沒展開：COT（有說明文字可以補）、WCET（沒有）、PTE（沒有，但對工程師算常識）。
- 「L2: where most accesses end」放在「Why page swap is rare」裡，跟這一塊的論點關係不明，可以算多餘或錯位。
- 「locks」只出現在黃框，上半部沒有對應的東西。

---

## 顏色

| 顏色 | 我讀成 | 一致嗎 |
|---|---|---|
| 橘色 | 每一次存取、CPU MMU 的 TLB lookup | 一致（上下兩半都用在同一件事） |
| 紫色（虛線框、箭頭、時間軸短線） | kernel SW | 大致一致；但 page swap 那一列標籤有 kernel SW，方塊卻只有綠色 |
| 綠色 | LZ4 HW、COMPRESS/DECOMPRESS、page swap | 一致 |
| 淡藍色填色 | processor 裡的硬體方塊（MMU/TLB、L1、L2） | 一致 |
| 藍色文字 | 說明與旁註（副標題、spacing 註記、rare 的兩行說明） | 一致 |
| 黃色底 | 警告／要記住的代價 | 一致 |
| 斜線 | 壓縮過的資料（猜的，沒有圖例） | 上下兩處（chunk pool、長條尾端）用法一致 |

## 我用自己的話講的結論

CPU MMU 和壓縮這一層在兩個軸上都分得很開：CPU MMU 長在每個 core 裡，每一次存取都要經過它，TLB 沒命中就叫 kernel 填一下，這件事很常發生；壓縮這一層在 processor 外、DRAM 旁，只有 page 要搬進搬出時才動作，因為 frame region 夠大所以很少發生，但每一次都要 lock、查表、等硬體，對等它的程式來說就是最壞情況，所以要用 WCET 來估。

## 總表

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 / 5 |
| 角色是否清楚 | 是（kernel SW 跑在哪裡不清楚，但角色本身清楚） |
| 畫面與結論是否一致 | 一致 |

## 是否建議重生

**不建議重生。** 困惑指數 2，角色清楚，箭頭方向沒有和故事矛盾，畫面和結論一致，不符合任何重生條件。

如果之後有機會修，可以考慮的小改（不是重生的理由）：
1. 讓 kernel SW 兩個框看得出是在 core 上跑的（例如用一條虛線連到某個 core，或標「runs on a core」）。
2. DECOMPRESS 的線改走不穿過紫色直線的路線，或補畫 LZ4 HW 的輸入（chunk pool → LZ4 HW、frame region → LZ4 HW）。
3. 「Why page swap is rare」拿掉 L2 括號，或說明它跟 swap 的關係；補一句「超出的那一段很少被碰」，讓容量論點接到次數。
4. 橘色線停在 L2，或加一個「miss」分支再到 DRAM，跟「L2: where most accesses end」對齊。
5. 副標題與 Key point 擇一，避免結論提前出現。

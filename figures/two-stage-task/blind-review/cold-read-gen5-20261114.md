# 冷讀驗收報告：two-stage-task gen5 第 2 張

- 日期：2026-11-14
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：two-stage-task 的 `gen5/02-apart-in-space-and-time.r2.png`

## 第一眼（兩秒鐘）

左右兩個大的虛線框，左邊藍色、右邊綠色，中間夾著一個小方塊（frame region）。下半部的對比最搶眼：左下是一整條密密麻麻的橘色條碼，右下只有兩個孤零零的事件。第一眼的訊息是「左邊很忙、右邊很閒，兩邊分開」。

## 1. 機器與方塊（遮住 Key point）

**左：藍色虛線框「CPU MMU domain」，標籤「ON EVERY ACCESS」**

| 方塊 | 標籤 | 我讀到的角色 |
|---|---|---|
| 大圓角框 | processor | 整顆 processor |
| 兩個 core 框 | Core 0、Core 1 | 兩個 core |
| 每個 core 裡兩個小框 | hw thread | 每個 core 有兩個 hardware thread |
| 每個 core 裡的藍框 | CPU MMU and TLB | 每個 core 自己一份 MMU 與 TLB |
| 每個 core 裡的藍框 | L1 | 每個 core 自己的 L1 |
| 橫跨兩個 core 下方的藍框 | L2 | 兩個 core 共用的 L2 |
| 紫色虛線框 | kernel SW: TLB miss（read one PTE, fill the TLB） | TLB miss 時由 kernel SW 讀一個 PTE、填 TLB |
| 表格框 | page table, in DRAM | page table，標明放在 DRAM |

**中間（兩個 domain 之間）**

| 方塊 | 標籤 | 我讀到的角色 |
|---|---|---|
| 三個空白小格的框 | frame region（hot pages, used by both） | 放熱 page 的地方，兩邊都會用到 |
| 浮動文字 | one kernel SW, two separate jobs and tables | 同一個 kernel SW，做兩件分開的工作、用兩套表 |

**右：綠色虛線框「compression domain」，標籤「OFF THE ACCESS PATH」**

| 方塊 | 標籤 | 我讀到的角色 |
|---|---|---|
| 綠框加齒輪 | LZ4 HW（outside the processor） | 壓縮硬體，在 processor 外面 |
| 紫色虛線框 | kernel SW: page swap（read the COT, hand LZ4 HW a job） | 做 page swap 的 kernel SW，查 COT 後交給 LZ4 HW 一個 job |
| 表格框 | COT, in DRAM: where each compressed page is | 記錄每個壓縮 page 在哪的表 |
| 四個斜線格 | chunk pool: cold pages, in DRAM | 放壓縮過的冷 page |
| 黃色便條 | Rare, but each one counts | 提醒：page swap 少，但每次都要算進 WCET |

所有方塊都有標籤，沒有無標籤的方塊。角色都看得出來。

唯一角色上的小疑問：左邊的 kernel SW: TLB miss 畫成 processor 裡、與 core 並列的一個方塊，乍看像是另一個硬體單元。紫色虛線（軟體的畫法）有幫忙，但沒有畫出它是「在某個 core 上跑」。

## 2. 看不懂或容易誤讀的線與物件

1. **page table 畫在 processor 框裡面。** 標籤寫「in DRAM」，但方塊整個落在 processor 的圓角框內。這張圖的主題是「空間」，這個位置與標籤互相矛盾，冷讀者會疑惑 page table 到底在 processor 裡還是在 DRAM。右邊的 COT 與 chunk pool 就沒有這個問題。
2. **橘色直線「every load and store; most end in L1 or L2」** 從 processor 框頂端外面往下穿過 Core 1 的 CPU MMU and TLB、L1，到 L2。只畫在 Core 1，起點不是 hw thread 而是框外的空白處，看不出存取從誰發出。線還正好壓在「CPU MMU and TLB」的字上（讀起來像「and | TLB」）。
3. **LZ4 HW 的兩條綠線只畫輸出、沒畫輸入。** COMPRESS 從 LZ4 HW 指向 chunk pool，DECOMPRESS 從 LZ4 HW 拐彎指向 frame region。資料從哪裡讀來（COMPRESS 讀 frame、DECOMPRESS 讀 chunk pool）沒有畫，看起來像 LZ4 HW 自己產生資料。DECOMPRESS 與 COMPRESS 兩個標籤靠得很近，瞄一眼可能對調。
4. **「which chunks」箭頭** 從 kernel SW: page swap 指向 COT。意思應該是「去 COT 查哪些 chunk」，箭頭方向（往 COT 指）讀成「寫進 COT」也說得通，略含糊。
5. **frame region 沒有標「in DRAM」**，而其他 DRAM 裡的東西都有標。「on an L2 miss」的橘色虛線指向它，能推出它在 DRAM，但要自己推。
6. 沒有箭頭交叉造成走錯路線的情況。

## 3. 只看畫面的一句話

同一顆 processor 上有兩件事：CPU MMU 在每個 core 裡、每次存取都會經過，TLB miss 時 kernel SW 很常被叫起來；壓縮層（kernel SW 加上 processor 外面的 LZ4 HW）在 DRAM 旁邊，只有 page swap 時才動，兩者只共用 frame region。

## 4. 空間

- **CPU MMU domain**：processor 本身——兩個 core、各自的 hw thread、CPU MMU and TLB、L1，共用的 L2，處理 TLB miss 的 kernel SW，以及 page table。
- **compression domain**：processor 外面的 LZ4 HW、做 page swap 的 kernel SW、COT、chunk pool。
- **在每次存取路上的**：CPU MMU and TLB、L1、L2（橘線穿過它們）；L2 miss 時再到 frame region。
- **不在路上的**：整個 compression domain（標籤明說 OFF THE ACCESS PATH）。
- **兩邊共用的**：frame region（明寫 used by both），以及 kernel SW（中間文字說是同一個 kernel SW，只是工作與表分開）。

## 5. 時間

- 左邊 DENSE：TLB lookup 是一整條連續的橘色條碼，等於每次存取都有；kernel SW: TLB miss 是不規則的紫色短線，大約十幾次。
- 右邊 SPARSE：同一段時間裡只有兩次 page swap，每次是紫色虛線框（kernel SW）加綠色齒輪（LZ4 HW）。
- 中間註明兩條時間軸是同一段時間、間距沒有實測。差距看起來很大：上百次 lookup 對十幾次 TLB miss 對兩次 page swap。page swap 的框比 TLB miss 的短線寬很多，我讀成每一次 page swap 比較久，但圖沒有明說寬度代表時間長短。

## 6. 讀 Key point 之後：畫面和結論一不一致

**一致。**

Key point 說 CPU MMU 在每個 core 裡、每次存取都會經過、常叫醒 kernel SW；壓縮層在外面、DRAM 旁邊，只在 page swap 時動作，次數少但每次都算進最壞情況。畫面上每一點都有對應：core 裡的 CPU MMU and TLB、橘色條碼、紫色短線、processor 外的 LZ4 HW、兩次 page swap、黃色便條的 WCET。

小的落差：

- 「compression layer sits beside DRAM」：畫面上 compression domain 裡的 COT 與 chunk pool 標「in DRAM」，但 frame region 與 page table 沒有和它們放在同一個 DRAM 區塊裡，DRAM 本身沒有被畫成一個範圍，「beside DRAM」要靠文字。
- 「OFF THE ACCESS PATH」與「each one counts toward the worst case」並列。冷讀者會問：既然不在存取路上，為什麼影響 WCET？答案應該是「存取碰到被壓縮的 page 時要等 page swap」，但畫面沒有畫出這條因果。這不算矛盾，是沒有解釋。
- 副標題與 Key point 幾乎是同一句話，重複。

## 7. 困惑指數

**2**。主結構（左右兩區、密對疏）一眼就懂；扣分在 page table 畫在 processor 框裡、LZ4 HW 的資料來源沒畫、以及「不在路上卻算 WCET」沒有解釋。

## 8. 可疑的錯字或多餘文字

- 「kernel SW:  page swap」冒號後面看起來多一個空格（手寫字型，可能只是間距）。
- 橘色直線壓在 Core 1 的「CPU MMU and TLB」上，字被切開。
- 頂端藍色副標題和底部 Key point 內容重複，其中一個可以省。
- 沒有看到明顯拼錯的字。

## 顏色

| 顏色 | 我讀到的意思 | 一致嗎 |
|---|---|---|
| 藍（淺藍填色、藍色虛線框） | CPU 這一邊的硬體：MMU、TLB、L1、L2、CPU MMU domain | 一致 |
| 綠（綠填色、綠色虛線框、綠色箭頭） | 壓縮這一邊：LZ4 HW、compression domain、COMPRESS 與 DECOMPRESS | 一致 |
| 紫（虛線框、箭頭、時間軸短線） | kernel SW 與它的動作 | 一致，兩邊的 kernel SW 都是紫色，時間軸上也是 |
| 橘 | 存取路徑、TLB lookup、L2 miss | 一致 |
| 黃便條 | 提醒、注意事項 | 一致 |
| 斜線 | 壓縮過的資料（chunk pool） | 一致 |

小問題：中間兩段中立的註解（one kernel SW…、both timelines…）與頂端副標題用藍色字，和 CPU MMU domain 同色，可能被當成屬於左邊。

## 用自己的話講結論

CPU MMU 是每個 core 裡、每次讀寫都會經過的關卡，TLB miss 時 kernel SW 就要出來填 TLB，這件事一直在發生。壓縮層是另一件事：它在 processor 外面、DRAM 旁邊，只有記憶體不夠、要把 page 換進換出時才動，次數少很多。兩者的共同點只有 frame region 與同一個 kernel SW。壓縮層雖然少見，但每次都要拿 lock、查 COT、等 LZ4 HW，所以要算進最壞情況。

## 總表

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 |
| 角色是否清楚 | 是 |
| 畫面與結論是否一致 | 一致 |

## 是否建議重生

**不建議重生。** 困惑指數 2，角色清楚，沒有與故事矛盾的箭頭，畫面與 Key point 一致。

如果之後因為其他原因要重生，可以順手修這幾點，依重要性排列：

1. page table 移出 processor 框，放到 DRAM 那一側（它標著 in DRAM）。
2. 橘色存取線從 hw thread 出發，不要壓在「CPU MMU and TLB」的字上。
3. 補上 LZ4 HW 的輸入：COMPRESS 從 frame region 讀、DECOMPRESS 從 chunk pool 讀。
4. 在 frame region 標「in DRAM」。
5. 用一個小箭頭或一句話交代「存取碰到被壓縮的 page 時要等 page swap」，解釋為什麼不在路上卻影響 WCET。

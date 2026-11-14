# 冷讀報告：two-stage-task gen1

- 日期：2026-11-14
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：two-stage-task 的 `gen1/01-two-stages.png`

---

## 圖 1：01-two-stages.png（標題「The Task in Two Stages」）

### 1. 人物與機器（先遮住 Key point）

**Stage 1 那一半（標籤「Stage 1: bring up the CPU MMU」，角標「MATURE DESIGN, NEW TO US」）**

| 物件 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 坐在筆電前的人 | user SW | 用橘色箭頭「every access」打到 CPU MMU and TLB | 每一次存取記憶體都要能過 |
| 藍色實線框 | CPU MMU and TLB，副標「in the chip, never turned on yet」 | 接收 user SW 的每一次存取 | 晶片裡本來就有，只是沒開過 |
| 紫色虛線框 | kernel SW，副標「TLB miss handler, page fault」 | 「fills the TLB」箭頭指向 CPU MMU；「reads and writes PTEs」箭頭往下到 page table | 維護 page table、補 TLB |
| 外框 | processor | 包住 user SW、CPU MMU、kernel SW | 表示這些都在 processor 這一層 |
| DRAM 框裡三個空白方格 | 無標籤 | 沒有箭頭碰到它們 | 看不出來。要對照 Stage 2 才猜得到是 frames |
| DRAM 框裡的表格 | page table | 被 kernel SW 讀寫 | 只有 kernel SW 碰它 |

**Stage 2 那一半（標籤「Stage 2: add compression to page swap」，角標「KNOWN FRAMEWORK, NEW DESTINATION」）**

| 物件 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 紫色虛線框 | kernel SW，副標「page swap: page out, page back in」 | 「hands it a job」箭頭往下交給 LZ4 HW | 決定什麼時候 page out、page back in |
| 綠色實線框，有齒輪 | LZ4 HW，副標「compresses and decompresses pages」 | 綠箭頭「page back in: DECOMPRESS」指向左邊 frames；「page out: COMPRESS」指向右邊斜線格 | 壓縮與解壓縮 page |
| 圓柱體 | 圖示本身無標籤；旁邊藍字「classic page swap sends pages here」 | 沒有任何箭頭接它，是旁註 | 要讀到最下面黃框的「not disk」才確定它是 disk |
| DRAM 左側白格 | frames: hot pages | 收 DECOMPRESS 的結果 | 常用的 page |
| DRAM 右側斜線格 | compressed space: cold pages | 收 COMPRESS 的結果 | 不常用的 page，斜線看起來代表「壓縮過」 |
| 上方外框 | 無標籤 | 包住 kernel SW、LZ4 HW、disk 圖示 | Stage 1 的同位置框寫著 processor，這裡沒寫。看不出 LZ4 HW 在 processor 裡面還是外面，disk 也被框在同一個框裡，更讓人猜不透這個框代表什麼 |

角色看不出來或沒標籤的：Stage 1 DRAM 的三個方格、Stage 2 的圓柱體、Stage 2 上方外框。

### 2. 看不懂的線或物件

- **CPU MMU 之後去哪裡？** user SW 的「every access」打到 CPU MMU 就停了。CPU MMU 沒有箭頭到 DRAM 的 frames，也沒有箭頭到 page table。讀者看不到「存取最後到了哪個 frame」。
- **kernel SW 怎麼知道要動作？** kernel SW 寫著 TLB miss handler 和 page fault，但沒有從 CPU MMU 指向 kernel SW 的箭頭（miss 或 fault 的觸發）。圖上只有 kernel SW 往 CPU MMU 的「fills the TLB」，方向是單向的。
- **只有 kernel SW 讀 page table、CPU MMU 不讀**：圖上確實是這樣畫的，但沒有任何字點出這是刻意的。沒背景的讀者不會注意到，也可能以為是漏畫。
- **Stage 2 的資料從哪裡來？** 兩條綠箭頭都從 LZ4 HW 出發，只畫了寫的去處。DECOMPRESS 應該從斜線格讀、COMPRESS 應該從 frames 讀，但這兩條來源都沒畫。乍看會以為 LZ4 HW 自己生出 page。
- **page table 在 Stage 2 不見了**，CPU MMU 和 user SW 也不見了。用「builds on」箭頭可以理解成「前提照舊」，但 page back in 之後誰改 page table、誰補 TLB，Stage 2 沒交代。
- **「clear a page from every core's TLB」**（Stage 1 checklist 第三項）：整張圖只畫了一個 CPU MMU and TLB，沒有畫多個 core。「every core」對冷讀者是突然冒出來的。
- **虛線框與實線框**：kernel SW 兩次都是虛線框，CPU MMU 和 LZ4 HW 是實線框。我猜虛線代表 SW、實線代表 HW，但圖上沒說明。
- **DRAM 中間的垂直虛線**：猜得出是把 frames 與 compressed space 分開，沒問題。
- **「builds on」大黑箭頭**：清楚，表示 Stage 2 建在 Stage 1 之上。

### 3. 圖說的一句話（不看 Key point）

工作分兩段：先用 kernel SW（page table、TLB miss handler、page fault）把 processor 本來就有、但從沒開過的 CPU MMU 開起來；再在 page swap 裡加上 LZ4 HW，讓冷的 page 壓縮後留在 DRAM 的一塊區域，而不是送去 disk。

### 4. 讀 Key point 後：畫面與結論

Key point：「Stage 1 turns on a mature CPU MMU that we have not used before. Stage 2 keeps the page swap framework and changes only where pages go: compressed space in DRAM, moved by LZ4 HW.」

**一致。** 兩個 stage 的角標、黃框、DRAM 分區都直接支撐這句話。唯一的小落差：Key point 說 Stage 2「changes only where pages go」，但 Stage 2 的 checklist 列了「manage the compressed space in DRAM」「choose which pages go cold」，看起來是不小的新工作，「only」讓工作量聽起來比 checklist 小。

### 5. 困惑指數

**2**。主線一看就懂；扣分在幾個沒標籤的物件（Stage 1 的方格、disk 圓柱、Stage 2 的外框）、CPU MMU 與 kernel SW 之間缺觸發箭頭，以及 checklist 提到 every core 但圖上只有一個 TLB。

### 6. 可疑的錯字或多餘文字

- 沒看到錯字。
- 副標題說「add compression **inside** page swap」，Stage 2 標題說「add compression **to** page swap」，用詞不同但意思一樣，不算錯。
- 「page back in」比常見的「page in」多一個字，不影響理解，全圖用法一致。
- 重複：副標題、兩個黃框、Key point 把同一件事講了三次。對工作說明來說可以接受，不算多餘到要刪。

---

## 跨圖觀察

（這次只有一張圖，以下以圖內兩個 stage 互相對照。）

### 命名物件長得一不一樣？有沒有走樣？

- **kernel SW**：兩個 stage 都是紫色虛線框、同樣字型，一致。副標不同（Stage 1 是 TLB miss handler, page fault；Stage 2 是 page swap），合理，代表同一個 kernel SW 在兩段要多做的事。
- **DRAM**：兩邊都是同樣的圓角框、左上角標「DRAM」，一致。但內容走樣：Stage 1 有 page table、Stage 2 沒有；Stage 1 的白格沒標籤、Stage 2 標成 frames。
- **processor**：只在 Stage 1 出現標籤，Stage 2 對應的框沒有名字，是最明顯的不一致。
- **CPU MMU、user SW**：只在 Stage 1 出現。

### 分類顏色

| 顏色 | 我認為代表 |
|---|---|
| 紫色（虛線框、箭頭、箭頭文字） | kernel SW 與它做的事 |
| 藍色填色框 | CPU MMU 這個 HW |
| 綠色（框、箭頭、箭頭文字） | LZ4 HW 與它做的事 |
| 橘色 | user SW 的存取 |
| 黃色填色框 | 理由或「不變的事」 |
| 斜線 | 壓縮過的資料 |
| 藍色文字 | 旁註（副標題、disk 說明） |

大致一致。唯一的小衝突：藍色同時用在 CPU MMU 的填色與旁註文字（副標題、disk 旁的說明），disk 說明的藍字會讓人一瞬間以為和 CPU MMU 有關。

### 用我自己的話說結論

這份工作不是從零做一個新東西，而是兩步：第一步把晶片裡現成、成熟但我們沒用過的 CPU MMU 打開，kernel SW 要寫 page table、TLB miss handler、page fault；第二步沿用一般的 page swap 流程，只是把「被趕出去的 page」從 disk 改成用 LZ4 HW 壓縮後放在 DRAM 的另一區，要用時再解壓回 frame。

### 讀完的感覺

- 對 Stage 1 有信心：圖明說 CPU MMU 是成熟設計，風險在我們不熟，不在 HW 本身。
- 擔心的地方：
  - Stage 1 的「clear a page from every core's TLB」只在 checklist 出現，圖上沒有多 core，讓人感覺這件事被輕輕帶過，可能其實是難點。
  - CPU MMU 與 kernel SW 之間怎麼交接（miss 時誰叫誰）沒畫，這是 Stage 1 的核心，卻是圖上最空的地方。
  - Stage 2 的黃框強調「只有去處變了」，但 checklist 的「管理壓縮空間」「選哪些 page 變冷」聽起來是新的設計工作，圖可能低估了 Stage 2。
  - LZ4 HW 在 processor 裡面還是外面，圖上看不出來。

---

## 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|
| 01-two-stages.png | 2 | 是（主要角色都有標籤；disk 圓柱、Stage 1 方格、Stage 2 外框無標籤，屬次要） | 一致（「changes only」略低估 Stage 2 的 checklist） |

## 建議重生

**無。** 這張圖困惑指數 2、主要角色清楚、畫面與結論一致，不符合重生條件。

若之後要小修，可考慮（非必要）：

1. Stage 2 上方外框加標籤，並把 LZ4 HW 放在 processor 內或外講清楚；disk 圓柱移出這個框並標「disk」。
2. 加一條 CPU MMU 到 kernel SW 的「TLB miss / page fault」箭頭，補上觸發方向。
3. Stage 1 DRAM 的三個方格標「frames」，與 Stage 2 對齊。
4. Stage 1 至少畫出兩個 core 的 TLB，讓「every core's TLB」有對應的畫面。
5. Stage 2 補上 COMPRESS 從 frames 讀、DECOMPRESS 從 compressed space 讀的來源線。

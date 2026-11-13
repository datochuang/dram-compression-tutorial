# cpu-mmu-basics gen2 冷讀驗收報告

- 日期：2026-11-13
- 方法：只給圖、不給提示詞的冷讀。讀者只拿到三張 PNG 與一句背景說明，沒有讀任何 prompt、規格或其他文件。
- 讀的是 cpu-mmu-basics 這一組 gen2 的 A、B、C 三張：
  - A：`gen2/01-why-translate.png`
  - B：`gen2/02-page-table-tlb-mmu.png`
  - C：`gen2/03-clear-every-tlb-first.png`
- 讀法：每張先遮住底部 Key point，回答第 1 到 3 題，再讀 Key point 回答第 4 到 6 題。一張寫完才讀下一張。

---

## 圖 A：Why an Address Is Translated

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 坐在筆電前的火柴人 | `user SW` | 送出 `read 0x00416C80` | 只在意自己的 logical address，不管資料實際在哪 |
| 左邊一直條、6 格 | `Logical address space`，副標 `what user SW sees` | 其中一格加粗，寫 `page 0x416`，裡面一個黑點寫 `offset 0xC80` | 表示 user SW 看到的位置 |
| 中間上方藍底方塊 | `Translation`，副標 `which frame holds this page?` | 收 `page 0x416`，送出 `its frame` | 只回答一個問題：這個 page 在哪個 frame |
| 中間白底表 | `The arithmetic` | 三行算式，把 `0x00416C80` 拆開、換 frame、再加回 offset | 數字怎麼對得起來 |
| 中間黃底表 | `What this buys` | 列三個好處 | 為什麼要多這一層 |
| 右邊一直條、6 格 | `DRAM`，副標 `physical addresses` | 其中一格加粗，寫 `frame at 0x80024000`，黑點寫 `offset 0xC80` | 資料實際所在 |

角色看不出來的地方：

- **`Translation` 方塊沒有說是誰做的。** 它是一個藍色的框，不是人也不是機器。讀者不知道這是 CPU 的硬體、kernel，還是一個抽象的步驟。
- **`the kernel` 只出現在黃底表的文字裡，畫面上沒有這個角色。** 第一次看的人不知道 kernel 是誰、站在哪裡、和 `Translation` 是什麼關係。

### 2. 看不懂的線或物件

- **`0x00416C80 = page 0x416 + offset 0xC80` 的「+」。** 照字面算 0x416 加 0xC80 是 0x1096，不是 0x00416C80。這裡的意思應該是「前面幾位是 page 編號，後面三位是 offset」，是接起來，不是相加。圖上有 `one page = 4096 B`，但沒有說 4096 就是 0x1000，也沒有說 offset 剛好是最後三個 hex 位數。沒學過的人在這一行會卡住。
- **page 用編號（`page 0x416`），frame 用 address（`frame at 0x80024000`）。** 兩邊的叫法不對稱。讀者會想：frame 有沒有編號？page 有沒有起始 address？第三行 `0x80024000 + 0xC80` 是真的相加，和第一行的「+」意思又不一樣。
- **`its frame` 這支箭頭。** 它從 `Translation` 指到 DRAM 的那一格。看不出來它是「答案」（frame 在哪）還是「這一次 read 真的走過去」。
- **沒有回程。** `read` 送出去之後，資料怎麼回到 user SW 沒有畫。對這張圖的重點影響不大，但流程是開口的。
- **黑點 `●`。** 兩邊都有，猜是「被讀的那一個 byte」。沒有圖例。
- **`the kernel can even take the frame away for a while`。** frame 被拿走之後 page 的內容去哪裡、user SW 這時候來讀會怎樣，這張圖沒有線索。讀者會帶著這個疑問往下看。
- 兩條直條其他格子是空白的，沒有編號。加粗的 page 在第 3 格，加粗的 frame 在第 2 格，位置不同。這一點有幫助：看得出來兩邊不是照順序一對一。

### 3. 圖說的一句話（不看 Key point）

user SW 用 logical address 讀資料，address 拆成 page 編號與 offset，中間有一步把 page 換成 DRAM 裡的 frame，offset 原封不動帶過去；多這一步的好處是 kernel 可以搬動或暫時收回 frame，user SW 不用知道。

### 4. 畫面和結論一不一致

Key point：`Translation answers one question: which frame holds this page right now? The offset inside the page never changes.`

**一致。** 藍色方塊的副標就是這個問題，兩邊的 `offset 0xC80` 也一樣。

兩個小落差：

- 標題問的是 Why（為什麼要轉），Key point 回答的是 What（轉換在回答什麼）。Why 的答案其實在黃底表 `What this buys`，Key point 沒有提。
- `right now` 這兩個字暗示答案會變。畫面是靜止的一刻，只有黃底表的文字支持這一點，沒有畫出「之前在別的 frame」。

### 5. 困惑指數

**2。** 主線由左到右三步，一眼就能跟上；扣分在算式第一行的「+」，以及 `Translation` 與 `kernel` 都沒有具體的角色。

### 6. 可疑的錯字或多餘文字

- 沒有看到拼錯的字。
- `0x00416C80 = page 0x416 + offset 0xC80`：不是錯字，但「+」的寫法容易被當成算錯。
- 頂端藍色那一行說明與 Key point 的內容部分重複（都在講「每次存取都要轉」），不算多餘，但資訊重疊。

---

## 圖 B：Page Table, TLB, CPU MMU: Who Holds the Mapping

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 大框（左） | `CPU` | 裝著 user SW、kernel SW、CPU MMU、TLB | 表示這些都在 CPU 裡面 |
| 坐在筆電前的火柴人 | `user SW` | 往下送出 `logical address` | 只送 address，其他不管 |
| 藍底方塊 | `CPU MMU`，副標 `checks the TLB on every access` | 收 logical address，往下 `look up the page` | 每一次存取都查 TLB，而且只查 TLB |
| 藍底方塊，內含一列白底資料 | `TLB`，副標 `a few recent entries only` | 放著一筆 `page 0x416: frame 0x80024000` | 快，但只放得下幾筆 |
| 紫色虛線框 | `kernel SW`，副標 `runs on the CPU when it is needed` | 一支紫色箭頭往右 `reads and writes the PTEs`，一支往下 `fills the entries` 到 TLB | 兩張表都是它在管 |
| 大框（右上） | `DRAM` | 裝著 page table | 放完整的那一份 |
| DRAM 裡的表 | `page table: one PTE per page` | 三列：`page 0x415: invalid`、`page 0x416: valid, frame 0x80024000`、`page 0x417: valid, frame 0x8003A000` | 每個 page 一筆，完整 |
| 白底說明框 | `Why two tables` | 比較兩張表：page table 完整但慢，TLB 快但小 | 為什麼需要兩份 |
| 黃底說明框 | `A PTE says one of two things` | 解釋 valid 與 invalid | PTE 的兩種內容 |

角色都有標籤，這一張沒有無標籤的人或機器。兩點要指出：

- **user SW 是人形，kernel SW 是虛線框。** 兩個都是 software，畫法不同。虛線大概是指「不是一直在跑」，圖上沒有圖例，要靠副標 `when it is needed` 自己推。
- **`PTE`、`TLB`、`MMU` 三個縮寫都沒有展開。** `PTE` 可以從 `page table: one PTE per page` 猜出是表裡的一筆，另外兩個只能當成名字接受。

### 2. 看不懂的線或物件

- **TLB 裡沒有這個 page 的時候會怎樣，沒有畫。** 這是我看這張圖最大的疑問。`CPU MMU` 往下查 TLB，TLB 只有幾筆，那查不到呢？圖上 kernel SW 有一支 `fills the entries` 的箭頭，副標寫 `when it is needed`，可以猜到「查不到時 kernel SW 會被叫起來補」，但從 `CPU MMU` 或 `TLB` 到 `kernel SW` 之間沒有任何線。誰叫 kernel SW、什麼時候叫，要讀者自己補。
- **橘色的路走到 TLB 就停了。** `logical address` 進 `CPU MMU`，`look up the page` 進 `TLB`，然後沒有下文：查到的 frame 沒有回到 CPU MMU，也沒有一支箭頭帶著 physical address 走到 DRAM 去拿資料。圖 A 的終點是 DRAM 裡的 frame，這張的 DRAM 裡只畫了 page table，沒有畫 frame，讀者可能以為 DRAM 裡只放 page table。
- **藍色小字 `no arrow here: the CPU MMU never reads the page table`。** 用文字說明「這裡沒有箭頭」。意思看得懂，但它放在 CPU 框與 DRAM 框中間的空隙，正上方就是 kernel SW 那支 `reads and writes the PTEs` 的紫色箭頭，第一眼會以為它在註解那支紫色箭頭。它要說的那條「不存在的線」是從 `CPU MMU` 到 `page table`，可是文字離 `CPU MMU` 很遠。
- **`reads and writes the PTEs` 是單向箭頭。** 文字說讀也寫，箭頭只指向 page table。小問題。
- **`invalid: this page has no frame right now`。** 那這個 page 的內容現在在哪？user SW 來讀 `page 0x415` 會怎樣？圖 A 留下的疑問（frame 被拿走）到這張還是沒有回答。
- **user SW 畫在 CPU 框裡面。** 可以理解成「在 CPU 上跑」，但人形坐在硬體的框裡，第一眼有點怪。
- TLB 那一筆寫 `page 0x416: frame 0x80024000`，page table 同一筆寫 `page 0x416: valid, frame 0x80024000`。少了 `valid`。可以理解成 TLB 只放 valid 的，但圖上沒有說。

### 3. 圖說的一句話（不看 Key point）

完整的對照表（page table）放在 DRAM 裡，由 kernel SW 讀寫；CPU 裡的 CPU MMU 每次存取只查 TLB 這一小份副本，TLB 的內容也是 kernel SW 填的，CPU MMU 自己從來不去讀 page table。

### 4. 畫面和結論一不一致

Key point：`The TLB is a small copy of the page table. The kernel SW fills the copy. Hardware never reads the page table.`

**一致。** 三句話各自對得到畫面：TLB 那一筆與 page table 的 `page 0x416` 相同；紫色箭頭 `fills the entries`；藍色小字 `no arrow here`。

一個用詞落差：畫面與頂端說明寫的是 `the CPU MMU never reads the page table`，Key point 換成 `Hardware never reads`。圖上同時寫 `kernel SW runs on the CPU`，而 kernel SW 會讀 page table。沒有背景的讀者可能會想：「kernel SW 在 CPU 上跑、又讀 page table，那 CPU 這個 hardware 不就讀了嗎？」用 `CPU MMU` 比用 `Hardware` 不容易誤會。

### 5. 困惑指數

**2。** 誰拿著哪一份、誰讀誰寫，顏色與箭頭都分得很清楚；扣分在「TLB 查不到時怎麼辦」完全沒畫，以及橘色的路停在 TLB 沒有走完。

### 6. 可疑的錯字或多餘文字

- 沒有看到拼錯的字。
- `PTE` 沒有展開就使用。
- frame 的寫法：圖 A 是 `frame at 0x80024000`，這張是 `frame 0x80024000`。差一個 `at`，意思相同。
- `Why two tables` 的內容和頂端藍色說明、DRAM 框裡的藍色小字 `the full list, far too big to fit in the CPU` 有重複（「完整但放在 DRAM」講了三次）。

---

## 圖 C：Taking a Frame Away: Clear Every TLB First

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 大框（左） | `Core 0` | 裝著 user SW 與 `TLB of Core 0` | 一個 core |
| 坐在筆電前的火柴人 | `user SW` | 往下送出 `page 0x16` 到 `TLB of Core 0` | 照常存取，不知道 kernel 在另一邊動手 |
| 藍底方塊 | `TLB of Core 0`，內容 `page 0x16: frame 0x80024000` | 一支長的橘色箭頭從它出發，橫過 Core 1 的框，指到 DRAM 裡的 frame，標 `TLB hit: straight to the frame, no kernel` | 只要它還有這一筆，就直接放行 |
| 大框（中） | `Core 1` | 裝著 kernel SW instance 與 `TLB of Core 1` | 另一個 core |
| 紫色虛線框 | `kernel SW instance`，副標 `running on Core 1` | 三支紫色箭頭：`1 set the PTE invalid` 到 page table；`2 clear the entry` 到 `TLB of Core 1`；`2 clear it on every other core too` 斜著到 `TLB of Core 0` | 要把 frame 收回來，而且要照順序 |
| 藍底方塊 | `TLB of Core 1`，內容 `page 0x16: frame 0x80024000` | 被 kernel SW 清掉那一筆 | 和 Core 0 的那一份各自獨立 |
| 大框（右） | `DRAM` | 裝著 page table 與一個 frame | 資料與表所在 |
| DRAM 裡的表 | `page table`，一列 `PTE of page 0x16` | 被 kernel SW 設成 invalid | 完整的那一份 |
| 空白方塊 | `frame 0x80024000` | 旁邊藍字 `3 only after step 2: the frame may be reused` | 要被收回的那個 frame |
| 白底說明框 | `If step 2 skips Core 0` | 三行說明漏掉 Core 0 的後果 | 做錯會怎樣 |
| 黃色便條 | `Two directions` | `invalid to valid: other cores need nothing`、`valid to invalid: clear the entry on every core.` | 哪個方向才需要清 |

角色都有標籤。看不出來的地方：

- **第 3 步沒有說是誰做的。** 第 1、2 步是紫色箭頭，從 kernel SW instance 出發；第 3 步只是 frame 旁邊的一行藍字，沒有箭頭，沒有主詞。
- **`CPU MMU` 不見了。** 圖 B 是 user SW 到 CPU MMU 再到 TLB，這張 user SW 直接接到 TLB。
- **`kernel SW instance` 的 `instance`。** 圖 B 叫 `kernel SW`。多了 `instance` 暗示有好幾個，Core 0 上有沒有另一個、它在做什麼，圖上沒有。

### 2. 看不懂的線或物件

- **那支最長的橘色箭頭是「正常情況」還是「出錯的情況」，分不出來。** 它從 `TLB of Core 0` 一路畫到 frame，標 `TLB hit: straight to the frame, no kernel`，顏色、粗細和圖 A、圖 B 的正常存取一樣。可是這張圖的主題是要把這個 frame 收回，照紫色的第 2 步，這一筆應該被清掉，這支箭頭就不該存在。它可能是「動手之前的樣子」，也可能是左下白底框說的「漏掉 Core 0 的後果」。圖上沒有任何記號（紅色、叉、虛線、before 與 after）告訴我是哪一種。這是這張圖最大的問題：正確的程序與出錯的情境畫在同一格畫面裡，沒有分開。
- **畫面是哪一個時間點，看不出來。** 兩個 TLB 都還寫著 `page 0x16: frame 0x80024000`，表示還沒清；但第 1、2 步的箭頭已經畫出來，第 3 步也寫了。page table 那一列只寫 `PTE of page 0x16`，沒有寫現在是 valid 還是 invalid。圖 B 的 page table 有寫 `valid, frame ...`，這張沒有。
- **那支橘色長箭頭橫穿過 Core 1 的框**，它的標籤正好落在 `TLB of Core 1` 的正下方。第一眼會以為 `TLB hit` 講的是 Core 1。
- **`page 0x16`。** 圖 A 與圖 B 一直用的例子是 `page 0x416` 對 `frame 0x80024000`。這張 frame 還是 `0x80024000`，page 卻變成 `0x16`。我不確定這是換了一個例子，還是 `0x416` 掉了一個 `4`。
- **Core 1 上的 kernel SW 怎麼清 Core 0 的 TLB。** 頂端說明寫 `Each core's TLB is a private copy`、`no TLB finds out by itself`。既然是 private，那支斜著跨過兩個 core 邊界的紫色箭頭是靠什麼做到的？圖上只有一支箭頭。
- **兩支箭頭都編號 2。** 可以理解成同一步有兩個對象，但兩者誰先誰後、要不要等 Core 0 清完才能做第 3 步，看不出來。
- **第 3 步是藍色，第 1、2 步是紫色。** 前兩張藍字是旁註，這裡藍字卻是程序的一步。
- **標題說 `Clear Every TLB First`，編號 1 卻是 `set the PTE invalid`。** 讀到 Key point 才知道 `First` 是「在動 frame 之前」，不是「第一步」。
- **為什麼要先設 PTE 再清 TLB**，圖上沒有說。
- **`no exception happens, so the kernel cannot stop it`。** `exception` 這個詞在三張圖裡第一次出現。前兩張沒有講過「TLB 查不到會產生 exception、kernel 因此接手」，所以這一句的前提我是用猜的。
- **`invalid to valid: other cores need nothing`。** 為什麼不用？我猜是「別的 core 的 TLB 本來就沒有這一筆，之後查不到自然會去補」，但這同樣要靠「TLB 查不到時會怎樣」這個沒有畫過的知識。`Two directions` 這個標題也沒有說是什麼的方向，要讀完兩行才知道是 PTE 的變化方向。
- **空白的 frame 方塊。** 圖 A 的 frame 是 DRAM 直條裡的一格，裡面有黑點；這張是一個獨立的空白方塊，名字寫在下面。空白是「已經清空」還是單純沒畫內容，不確定。
- **frame 被收走之後 page 的內容去哪裡**，三張圖都沒有回答。`reused` 是給誰用，也沒有說。

### 3. 圖說的一句話（不看 Key point）

kernel SW 要收回一個 frame 時，先把 page table 裡那一筆 PTE 設成 invalid，再把每一個 core 的 TLB 裡那一筆清掉（包括別的 core），之後才能把 frame 拿去用；漏掉任何一個 core，那個 core 還是會 TLB hit、直接讀寫舊的 frame，kernel 完全不會知道。

### 4. 畫面和結論一不一致

Key point：`Order: set the PTE invalid, clear the entry from every core's TLB, and only then touch the frame.`

**部分一致。**

- 一致的部分：編號 1、2、3 與 Key point 的三段順序相同。
- 不一致的部分：
  - 畫面上最顯眼的一條線是那支橘色的 `TLB hit` 長箭頭，它畫的是「Core 0 還能直接走到 frame」。Key point 講的是照順序做完之後不會有這件事。畫面沒有標明這支箭頭是做之前，還是做錯的後果，所以只看畫面時，我得到的印象偏向「有一條繞過 kernel 的路」，而不是「一個順序」。
  - 兩個 TLB 在畫面上都還留著那一筆，沒有任何「已清掉」的樣子，和 Key point 的結果狀態對不起來。
  - 用詞：畫面寫 `the frame may be reused`，Key point 寫 `touch the frame`；標題寫 `Clear Every TLB First`，Key point 的第一步是 `set the PTE invalid`。

### 5. 困惑指數

**3。** 1、2、3 的順序讀得出來，但正確程序與出錯情境疊在同一個畫面，橘色長箭頭的身分不明，加上 `exception` 與 TLB 查不到的行為前面沒有鋪陳，要來回看幾次才拼得起來。

### 6. 可疑的錯字或多餘文字

- **`page 0x16`**：出現三處（橘色箭頭、兩個 TLB、page table）。前兩張是 `page 0x416`，frame 相同。懷疑是掉字，或是沒有說明就換了例子。
- 句尾標點不統一：白底框第三行 `cannot stop it.` 有句點，前兩行沒有；黃色便條第二行 `on every core.` 有句點，第一行沒有。
- `kernel SW instance`、`the kernel`、`no kernel` 三種叫法同時出現在這一張。
- 沒有看到拼錯的英文字。

---

## 跨圖觀察

### 命名物件在每張裡長得一不一樣

| 物件 | 圖 A | 圖 B | 圖 C | 有沒有走樣 |
|---|---|---|---|---|
| user SW | 火柴人加筆電 | 同 | 同 | 沒有。三張一樣，是最穩定的角色 |
| kernel | 只在文字裡，叫 `the kernel` | 紫色虛線框，叫 `kernel SW` | 紫色虛線框，叫 `kernel SW instance`，文字裡另有 `the kernel` | 外形 B、C 一致。名字三張三種 |
| 做轉換的東西 | 藍底方塊 `Translation` | 藍底方塊 `CPU MMU` | 沒有畫 | A 到 B 可以靠藍色猜到是同一件事，但沒有明說。C 直接消失 |
| TLB | 沒有 | 藍底方塊，內含一列白底資料 | 藍底方塊，文字直接寫在藍底上；名字變成 `TLB of Core 0`、`TLB of Core 1` | 小走樣：少了白底的那一列 |
| page table | 沒有 | 有表頭、三列，每列寫 valid 或 invalid | 有表頭、一列，只寫 `PTE of page 0x16`，沒有狀態 | 走樣：C 的那一列沒有內容，看不出狀態 |
| frame | DRAM 直條裡加粗的一格，有黑點與 offset | 沒有畫，只出現在文字裡 | 獨立的空白方塊，名字在下方 | 走樣：三張三種情況 |
| DRAM | 一條 6 格的直條 | 圓角大框 | 圓角大框 | A 與 B、C 不同。A 是 address space 的畫法，B、C 是容器的畫法 |
| CPU | 沒有 | 一個大框 `CPU` | 兩個大框 `Core 0`、`Core 1`，沒有 `CPU` 外框 | B 到 C 沒有交代「一個 CPU 有好幾個 core」 |
| 例子的數字 | `page 0x416`、`frame at 0x80024000` | `page 0x416`、`frame 0x80024000` | `page 0x16`、`frame 0x80024000` | C 的 page 編號和前兩張不同 |

### 分類顏色每張一致嗎

大致一致，這是這組圖做得好的地方。

- **橘色：user SW 的存取路徑。** 三張一致。
- **紫色：kernel SW 與它的動作。** B、C 一致。A 沒有紫色，kernel 只在黑字裡。
- **藍底：做轉換的硬體（`Translation`、`CPU MMU`、`TLB`）。** 三張一致。
- **藍字：旁註。** A、B 一致。C 有一個例外：第 3 步用藍字寫，它是程序的一步，不是旁註。
- **黃底：補充的重點。** 三張都有。外形不同：A 是有格線的表，B 是素的方塊，C 是折角的便條。
- **白底圓角框：解釋用的文字。** 三張一致。

沒有圖例。顏色的意思都是我看了三張才歸納出來的。

### 連著看，故事線順不順

- **A 到 B：順。** A 留下「`Translation` 是誰做的、對照表放在哪」的問題，B 正好回答：CPU MMU 查 TLB，完整的表在 DRAM，kernel SW 管。例子的數字也接得上。
- **B 到 C：斷了一截。** C 一開場就用了三件前面沒有鋪陳的事：
  1. **TLB 裡查不到時會怎樣。** B 沒有畫。C 的 `no exception happens`、`invalid to valid: other cores need nothing`、為什麼先改 PTE 再清 TLB，全部要靠這個知識。
  2. **一個 CPU 有好幾個 core，每個 core 各有一個 TLB。** B 畫的是一個 `CPU` 框一個 TLB。C 直接變成 `Core 0`、`Core 1`，只有頂端一行藍字交代。
  3. **`TLB hit` 這個詞。** 前兩張沒有出現 hit 或 miss。
- **A 埋的伏筆只回收了一半。** A 說 `the kernel can even take the frame away for a while`，C 講的就是 take a frame away，這一點接得上。但 frame 被拿走之後 page 的內容去哪裡、user SW 之後再來讀會怎樣，三張都沒有講。
- **例子的 page 編號在 C 變了**（`0x416` 變 `0x16`），接續感被打斷。

### 我用自己的話講的結論

程式用的 address 不是記憶體真正的 address。每一次存取，CPU 都要把「哪一個 page」換成「DRAM 裡的哪一個 frame」，page 裡面的 offset 不變。完整的對照表（page table）放在 DRAM 裡，由 kernel SW 維護；CPU 的硬體不會自己去讀它，只看 CPU 裡面一份很小的副本（TLB），這份副本也是 kernel SW 填的。因為每個 core 各有一份副本，而且副本不會自己更新，所以 kernel SW 要收回一個 frame 時，要先把 page table 裡那一筆改成 invalid，再把每一個 core 的 TLB 裡那一筆清掉，最後才能動那個 frame；漏掉一個 core，那個 core 就會繼續直接讀寫舊的 frame，而且 kernel 不會收到任何通知。

我講不出來的部分：TLB 裡沒有那一筆時實際發生什麼事；frame 被收走後資料放在哪。

### 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|---|
| A `01-why-translate` | 2 | 是（`Translation` 沒說由誰做，`kernel` 只在文字裡） | 一致 |
| B `02-page-table-tlb-mmu` | 2 | 是 | 一致 |
| C `03-clear-every-tlb-first` | 3 | 是（第 3 步沒有主詞） | 部分一致 |

### 建議重生

照條件（困惑指數 3 以上、或角色不清、或畫面與結論不一致），只有一張：

- **圖 C `03-clear-every-tlb-first`**。理由：
  1. 橘色 `TLB hit` 長箭頭的身分不明。正確的程序與「漏掉 Core 0」的後果疊在同一個畫面，沒有記號區分。這是畫面與 Key point 只有部分一致的主因。
  2. 畫面沒有時間點：兩個 TLB 都還留著那一筆，page table 的 PTE 沒有寫狀態。
  3. `page 0x16` 和前兩張的 `page 0x416` 對不上。
  4. 第 3 步用藍字、沒有主詞；標題的 `First` 與編號 1 的內容對不上。
  5. 橘色長箭頭橫穿 Core 1 的框，標籤落在 `TLB of Core 1` 正下方，容易讀錯對象。

不在重生條件內，但冷讀時記下來的事：

- **B 與 C 之間缺一步。** 「TLB 查不到時會怎樣」三張都沒有畫，C 卻要用到。這不是哪一張圖畫壞了，是這一組少了一段。補在 B 裡，或在 B、C 之間多一張，由這組圖的作者決定。
- **圖 A**：算式第一行的「+」會被讀成相加。
- **圖 B**：橘色的路停在 TLB，沒有走到 DRAM 的 frame；`no arrow here` 的藍字離它要說的 `CPU MMU` 太遠；Key point 的 `Hardware` 和畫面的 `CPU MMU` 用詞不同。

# 冷讀報告：two-stage-task gen2/01-two-stages.png

- 日期：2026-11-14
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：two-stage-task 的 `gen2/01-two-stages.png`

讀者設定：硬體團隊成員，第一次接觸這顆 multi-core processor，沒看過任何文字說明。先遮住底部的 Key point，最後才讀。

---

## 1. 人物與機器

圖分成左右兩大欄：左邊是「Stage 1」，右邊是「Stage 2」。最上方有標題「The Task in Two Stages」，下面有一行藍字副標。

### 左欄 Stage 1：bring up the CPU MMU and memory management（右上角標籤 MATURE DESIGN, NEW TO US）

| 方塊 | 標籤 | 我讀成在做什麼 |
|---|---|---|
| 外框 | processor | 整顆 processor |
| 兩個框 | Core 0、Core 1 | 兩個 core |
| 每個 core 裡兩個小框 | hw thread | 每個 core 兩個 hardware thread，是發出存取的一方 |
| 每個 core 裡藍框 | CPU MMU and TLB / one TLB, shared by both threads | 位址轉換的硬體，一個 core 一個 TLB，兩個 thread 共用 |
| 每個 core 裡藍框 | L1 | 每個 core 自己的 L1 cache |
| 跨兩個 core 的藍框 | L2 / shared by all cores | 共用的 L2 |
| 藍字註記 | two cores, two threads each: an example | 說明核心數與 thread 數只是舉例 |
| 紫色虛線框 | memory management in kernel SW: known parts | kernel SW 裡的記憶體管理，裡面列出六個已知的組件 |
| 紫框內 | page tables | page table |
| 紫框內 | TLB miss handler | TLB miss 時處理的程式 |
| 紫框內 | page fault | page fault 處理 |
| 紫框內 | frame allocator | 分配實體 frame |
| 紫框內 | clear a page from every core's TLB | 把某個 page 從所有 core 的 TLB 清掉 |
| 紫框內，粗黑框 | page swap | page swap，特別加粗，顯然是重點 |
| 下方框 | DRAM，裡面有 page tables 與 frames（三個空格） | DRAM 裡放 page table 與 frame |
| 白框清單 | Our work（七項 checkbox） | Stage 1 要做的事 |
| 黃色便條 | Why we can expect it to work（兩項） | 為什麼這件事做得成 |

### 右欄 Stage 2：compression inside page swap（右上角標籤 A SPECIAL CASE OF PAGE SWAP）

| 方塊 | 標籤 | 我讀成在做什麼 |
|---|---|---|
| 紫色虛線框 | page swap / page out, page back in | 就是左邊那個 page swap，放大後的樣子 |
| 綠框，有齒輪 | LZ4 HW / outside the processor | 做壓縮與解壓縮的硬體，在 processor 外面 |
| 圓柱體 | **無標籤**，只在下方有藍字「the usual destination」 | 我猜是 disk 或 flash 的 swap 裝置，也就是 page swap 平常把 page 送去的地方。但圖上沒寫它是什麼 |
| 下方框 | DRAM，左半 frames: hot pages（空白格），右半 compressed space: cold pages（斜線格） | DRAM 被分成放一般 page 的 frame 與放壓縮後 page 的區域 |
| 白框清單 | Our work（四項） | Stage 2 要做的事 |
| 黃色便條 | What stays, what is new（兩項） | 哪些不變、哪些是新的 |

角色看不出來或沒標籤的：
- **圓柱體沒有名稱**。只靠「the usual destination」和「圓柱體 = 儲存裝置」的慣例猜它是 disk/flash。沒有 swap 背景的人可能不知道「usual destination」指的是什麼。
- 「Our work」的「Our」是誰沒有說。Stage 1 的清單幾乎都是 kernel SW 的工作（lock、TLB 清除、cache 維護），硬體團隊的讀者會想：這是我們硬體團隊要做的，還是 kernel 團隊？
- 其餘方塊的角色都清楚。

## 2. 看不懂的線或物件

- **左右兩欄之間的兩條細黑線**：我讀成「放大鏡」的引導線。兩條線從左邊加粗的 page swap 方塊出發，一條往上連到右邊的 page swap 紫框，線上寫「zoom in on page swap」；另一條往下連到右邊 DRAM 框的左上角。意思是：右邊整個上半部是左邊 page swap 這一格放大來看。上面那條有字，意思很清楚。下面那條沒字，終點剛好落在 DRAM 框的角上，第一眼會有一瞬間以為「page swap 直接連到 DRAM」，要看到上面那條的字才會懂兩條是一組放大線。整體來說能懂，不算困惑。
- **紫色箭頭「TLB miss enters kernel SW」**：從 Core 1 的 CPU MMU 出發，指向 TLB miss handler。箭頭穿過 page tables 方塊，文字也壓在 page tables 與 page fault 之間，看起來有點擠，第一眼會以為箭頭跟 page tables 有關。另外只有 Core 1 畫了這條、只有 Core 0 畫了「every access」，可以理解為舉例，但嚴格的讀者可能會問是否只有 Core 1 會 miss。
- **橘色箭頭「every access」**：從 Core 0 的 hw thread 指向 CPU MMU。清楚：每次存取都經過 MMU。
- **page tables 出現兩次**：kernel SW 框裡一次、DRAM 裡一次，中間沒有線。我讀成「kernel SW 管理 page table，資料本身放在 DRAM」，可以接受，但沒有線說明兩者是同一份東西。
- **Stage 1 的 DRAM 沒有跟任何東西連線**：processor、L2、kernel SW 都沒有線連到 DRAM。不影響這張圖的主旨，但它就只是「擺著」。
- **Stage 2 的兩條綠色箭頭**：從 LZ4 HW 往下分別指向 frames（page back in: DECOMPRESS）與 compressed space（page out: COMPRESS）。我讀成「做完之後結果寫到哪裡」。嚴格說，DECOMPRESS 是從壓縮區讀、寫到 frame；COMPRESS 是從 frame 讀、寫到壓縮區。箭頭只畫了寫出的方向，沒畫讀的來源。對這張圖的層次夠用，但懂行的讀者可能會覺得少了一半。
- **圓柱體孤立**：沒有任何線連到它，也沒有打叉或淡化表示「被取代」。要靠右下黃便條「new: the destination」才知道它是被換掉的那個舊目的地。
- **便條裡的 checkbox**：「Why we can expect it to work」與「What stays, what is new」的條目也有 checkbox。這兩張便條是理由與說明，不是待辦事項，checkbox 會讓人以為也是要打勾的工作。小問題。

## 3. 圖說的一句話（不看 Key point）

這份工作分兩段：先在這顆新 processor 上把成熟的 CPU MMU 與 kernel 記憶體管理架起來，再放大其中的 page swap，把 page 的去處從平常的儲存裝置換成 DRAM 裡的壓縮區，由 processor 外面的 LZ4 HW 負責壓縮與解壓縮。

## 4. 兩段的關係

我讀成：**右邊是左邊某一部分（page swap）的延伸或特例，不是全新的東西**。

畫面上的依據：
- 左邊 page swap 方塊特別加粗，右邊同名的紫色虛線框是同一種紫色。
- 兩欄之間的放大線，上面寫「zoom in on page swap」。
- Stage 2 標題「compression inside page swap」與標籤「A SPECIAL CASE OF PAGE SWAP」。
- 最上方副標「Compression is a special case of one of its parts: page swap」。
- 右下黃便條「stays: the page swap flow of page fault, page out, page back in / new: the destination, compressed DRAM, and how it is managed」。
- 新的東西（LZ4 HW）用了只在右邊出現的綠色。

這個關係在畫面上講了好幾次，很難讀錯。也看得出順序：Stage 2 依賴 Stage 1 先完成。

## 5. 讀 Key point 之後：畫面與結論一致嗎？

Key point：「Stage 1 brings up a mature CPU MMU and its memory management on many cores and threads. Stage 2 takes one of those parts, page swap, and gives it a new destination: compressed space in DRAM, moved by LZ4 HW.」

判定：**一致**。

- 「mature」對應左上標籤 MATURE DESIGN, NEW TO US 與紫框的「known parts」。
- 「many cores and threads」對應兩個 core 各兩個 thread，並標明是 example。
- 「takes one of those parts, page swap」對應加粗的 page swap 與放大線。
- 「new destination: compressed space in DRAM」對應右邊 DRAM 的斜線區與圓柱體「the usual destination」。
- 「moved by LZ4 HW」對應綠色 LZ4 HW 與兩條綠色箭頭。

唯一的落差很小：Key point 說「gives it a new destination」，畫面上舊的目的地（圓柱體）只是擺在旁邊，沒有畫出「本來去這裡、現在改去那裡」的對比。讀者要自己從便條把兩者連起來。

## 6. 困惑指數

**2 / 5**。主結構（兩段、右邊是左邊 page swap 的放大）一眼就懂；扣分在圓柱體沒名稱、紫色 TLB miss 箭頭壓在 page tables 上、放大線下半條的終點容易誤讀為連到 DRAM。

## 7. 可疑的錯字或多餘文字

- 沒有發現錯字。
- 「special case of page swap」在副標、Stage 2 標籤、Key point 各出現一次，加上 Stage 2 標題「compression inside page swap」，同一句話說了四次。對「讓人相信」的目的是有幫助的強調，不算錯，但略顯重複。
- 「one TLB, shared by both threads」在兩個 core 各寫一次，可接受。
- 「the hard part is that it is new to us, not the hardware」這句可以讀成兩種意思：(a) 難處在於我們不熟，而不是硬體本身有問題；(b) 難處是它對我們是新的，而不是新的硬體。意思大致相同，但句子結構有點繞，第一次讀要停一下。
- 便條裡的 checkbox（見第 2 節）屬於多餘的符號。

---

## 顏色各代表什麼？一致嗎？

| 顏色 | 我讀成 |
|---|---|
| 淺藍填色 | processor 裡的硬體：CPU MMU 與 TLB、L1、L2 |
| 紫色（框線、箭頭、文字） | kernel SW：記憶體管理的組件、TLB miss 進入 kernel、page swap 交 job 給 LZ4 HW |
| 綠色 | 新加的 LZ4 HW 與它做的 COMPRESS / DECOMPRESS |
| 橘色 | user 的存取（every access），以及標題底線 |
| 黃色便條 | 說明與理由，不是架構 |
| 斜線格 | 壓縮過的 page |
| 藍色文字 | 註解（副標、an example、the usual destination） |

大致一致。小瑕疵：藍色同時用在「processor 內硬體的填色」與「註解文字」，「the usual destination」用藍字寫在圓柱體下方，可能讓人以為圓柱體也是 processor 內的硬體。橘色同時是使用者存取與標題底線，不會造成誤會。

## 用自己的話說結論

這件事不是從零發明：前半段是把業界成熟的 CPU MMU 與 kernel 記憶體管理（page table、TLB miss handler、page fault、frame allocator、TLB 清除、page swap）在這顆多 core、多 thread 的新 processor 上架起來，難處在我們不熟，不在設計本身；後半段只動其中一個既有零件 page swap，把 page 換出去的地方從原本的儲存裝置改成 DRAM 裡的壓縮區，由 processor 外的 LZ4 HW 做壓縮與解壓縮，page swap 原本的流程不變。

## 讀完的感覺

- **有信心的部分**：Stage 2 的範圍被畫得很窄、很清楚，只是 page swap 的一個特例，新東西只有 LZ4 HW、壓縮區的管理、冷熱選擇與測試。這部分讓人覺得可控。
- **擔心的部分**：Stage 1。它被標為「mature」，但「Our work」有七項，其中好幾項是多 core、多 thread 的併發問題：page table 要用 lock 保持一致、同一個 core 的兩個 thread 同時 miss 同一個 TLB、重用 frame 前清掉每個 core 的 TLB、frame 換主人時 L1 與 L2 要正確。這些正是在一顆不熟的 processor 上最容易出錯的地方。圖用「design 是成熟的」來安撫，但沒有說明這些項目的機制我們是否已經知道（例如怎麼清別的 core 的 TLB）。硬體團隊讀到這裡會想問：這些是有現成的 kernel 可以用，還是要我們自己寫？
- **左邊的工作看起來**：偏多，不是太簡單。左欄的面積與清單長度都比右欄大，視覺上 Stage 1 才是主體。這和「建立在成熟基礎上」的訊息有一點拉扯：讀者會相信設計成熟，但也會意識到 Stage 1 的量不小。如果作者想傳達的是「Stage 1 量大但風險低」，目前的畫面說了「風險低」（mature、known parts、proven），沒有說「為什麼量大也不怕」。

## 總表

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 / 5 |
| 角色是否清楚 | 是（唯一例外是圓柱體沒有名稱，靠「the usual destination」與慣例可猜出） |
| 畫面與結論是否一致 | 一致 |

## 是否建議重生

**不建議重生。** 困惑指數 2、角色清楚、畫面與 Key point 一致，不符合重生條件。

若要小修（非必要），優先順序：
1. 圓柱體加名稱（例如 disk 或 flash swap），並畫一條從 page swap 出發、被取代的淡化或打叉的線，讓「換目的地」在畫面上看得到。
2. 紫色「TLB miss enters kernel SW」箭頭與文字不要壓在 page tables 方塊上。
3. 兩張黃便條拿掉 checkbox，改成一般條列。
4. 放大線下半條加一點標示，或讓它的終點落在 Stage 2 框的邊上而不是 DRAM 框的角上，避免讀成 page swap 連到 DRAM。

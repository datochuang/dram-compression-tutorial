# 冷讀報告：two-stage-task gen8/01-two-stages.png

- 日期：2026-11-14
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：two-stage-task 的 `gen8/01-two-stages.png`

## 第一眼兩秒鐘

最先讀到的字依序是：

1. 左邊藍色巨大字「A SURE PATH TO THE END」
2. 右邊綠色巨大字「SMALL SCOPE, MORE EXPLORATION」
3. 左上的標題「The Task in Two Stages」

兩段工作給人的感覺很清楚：左邊是「有把握、照著做就會到」的穩定工作，量多但方向確定；右邊是「範圍小，但答案還沒找到」的探索性工作。兩個大字的顏色不同（藍與綠），左右對照的意思一眼就看得到。左邊的畫面比較擠、項目多，右邊比較空、比較集中，也符合「左邊量大、右邊範圍小」的感覺。

## 遮住 Key point 之後

### 1. 機器與方塊

**Stage 1（左）**

- **processor**：外框，裡面有 Core 0、Core 1，底下標「two cores, two threads each: an example」，看得出 2 個 core、每個 2 個 thread 只是舉例。
- **Core 0 / Core 1**：各有兩個 **hw thread**、一個 **CPU MMU and TLB**（註明「one TLB, shared by both threads」）、一個 **L1**。
- **L2**：橫跨兩個 core，標「shared by all cores」。清楚。
- **橘色箭頭「every access」**：從 Core 0 的 hw thread 指到 CPU MMU and TLB，讀成「每一次存取都經過 MMU 與 TLB」。只畫在 Core 0，讀者會當成舉例，不影響理解。
- **DRAM**：裡面有 **page tables** 與三格空白的 **frames**。
- **紫色虛線框「memory management in kernel SW: known parts」**：六個方塊：page tables、TLB miss handler、page fault、frame allocator、clear a page from every core's TLB、page swap。page swap 用粗黑框強調，看得出它是要被放大的那一塊。
- **紫色箭頭「TLB miss enters kernel SW」**：從 Core 1 的 CPU MMU and TLB 指到 TLB miss handler。看得懂：TLB miss 之後由 kernel SW 處理。
- **Our work（白框，7 項 checkbox）**：要做的事列表。
- **Why we can expect it to work（黃色便條）**：兩個理由：設計成熟、難處在於「對我們是新的」而不是硬體本身。

**Stage 2（右）**

- **page swap（紫色虛線框，「page out, page back in」）**：對應左邊 kernel SW 裡的 page swap。
- **LZ4 HW（綠框，齒輪圖示，「outside the processor」）**：硬體加速器，位置在 processor 外面。清楚。
- **「hands it a job」箭頭**：page swap 交工作給 LZ4 HW。
- **兩條綠色箭頭**：LZ4 HW 往下指到 DRAM 的 frames（「page back in: DECOMPRESS」）與 compressed space（「page out: COMPRESS」）。
- **DRAM**：左半 frames: hot pages（空白方格），右半 compressed space: cold pages（斜線方格），中間虛線分隔。斜線代表壓縮過的資料，看得懂。
- **圓柱體「the usual destination」**：角色只能用猜的。沒有寫它是什麼（disk、flash、swap device？），也沒有任何線連到它。讀者大概會猜是「傳統 swap 寫到的儲存裝置」，但這是猜的。
- **Our work（4 項）**、**What stays, what is new（黃色便條）**。

**角色看不出來或沒標籤的：**

- 圓柱體：只寫「the usual destination」，沒說是什麼裝置。
- 兩個 Stage 之間有一條細長、空白的直立圓角框，裡面只有一條斜線穿過，沒有標籤，看不出這條框是什麼。

### 2. 看不懂的線或物件

- **中間那條空白直立框**：不知道是分隔欄、還是某個沒寫字的物件。
- **兩條「zoom」線**：一條從左邊 kernel SW 框的右上角往上斜到右邊，旁邊有旋轉的小字「zoom in on page swap」；另一條從 page swap 方塊的右下角斜到右邊 DRAM。看得出是「放大」的意思，但旋轉的小字很難讀，第一眼我讀成「page snap」。兩條線的端點也沒有對到右邊的 page swap 框，而是落在 Stage 2 的外框邊緣附近，放大的「範圍」有點模糊。
- **圓柱體沒有連線**：「the usual destination」孤立在一邊，讀者不確定它在新設計裡還用不用。要讀到底部便條「new: the destination」才知道它被換掉了。
- **page tables 出現兩次**：一次在 kernel SW 框裡、一次在 DRAM 裡。讀者大概能理解成「管理 page table 的程式」與「page table 本身放在 DRAM」，但圖上沒有說兩者的關係，也沒有連線。
- **LZ4 HW 的箭頭只畫寫入的去處**：DECOMPRESS 指向 frames、COMPRESS 指向 compressed space，但沒畫資料從哪裡讀。看成「LZ4 HW 把結果寫到哪裡」是說得通的，方向沒有與故事矛盾，只是比較省略。
- **「Why we can expect it to work」與「What stays, what is new」用 checkbox**：這兩塊是理由與說明，不是待辦事項，用 checkbox 會讓人誤以為也是要打勾的工作。小問題。

### 3. 圖說的一句話（只看畫面）

這份工作分兩段：先把這顆 multi-core processor 上已經成熟的 CPU MMU 與 kernel 的 memory management 帶起來（穩穩做就會到），再從中拿出 page swap 這一塊，讓 LZ4 HW 把被趕出去的 page 壓縮放在 DRAM 裡（範圍小、但要探索最佳設計）。

### 4. 兩段工作的性質（只看畫面）

**左邊（Stage 1）**

- 風險：低。
- 目標：清楚。
- 要不要探索：不太需要，是照已知設計一步一步做。
- 從哪裡讀出來：大字「A SURE PATH TO THE END」；副標「the CPU MMU already exists in the chip: steady work brings it up」；右上標籤「MATURE DESIGN, NEW TO US」；kernel SW 框標「known parts」；黃色便條「proven, mature design」「the hard part is that it is new to us, not the hardware」。另外 7 項 Our work 讓人感覺工作量不小，但每一項都寫得很具體（locks、TLB 清除、L1/L2 一致性、每個 core 與 thread 都要測）。

**右邊（Stage 2）**

- 風險：中到偏高，不確定性比左邊大。
- 目標：方向清楚（把 page swap 的目的地換成壓縮的 DRAM），但「最好的做法」還不清楚。
- 要不要探索：要。
- 從哪裡讀出來：大字「SMALL SCOPE, MORE EXPLORATION」；副標「only one part of page swap, but its best design is still to be found」；標籤「A SPECIAL CASE OF PAGE SWAP」；Our work 裡的「choose which pages go cold」「manage the compressed space in DRAM」都是要決定策略的項目。不過畫面本身沒有用問號、分支之類的視覺符號表現「探索」，主要靠文字傳達。

**兩段的關係**

- Stage 2 是 Stage 1 裡 page swap 那一塊的放大（zoom 線與粗框的 page swap 方塊）。
- 順序上是先 1 後 2，Stage 2 建立在 Stage 1 之上。
- 「What stays, what is new」說明 page swap 的流程（page fault、page out、page back in）不變，只換目的地與管理方式。

### 5. 讀 Key point 之後：畫面與結論一不一致

Key point：「Stage 1 brings up a mature CPU MMU and its memory management on many cores and threads. Stage 2 takes one of those parts, page swap, and gives it a new destination: compressed space in DRAM, moved by LZ4 HW.」

**一致。** 結構上完全對得上：Stage 1 是多 core、多 thread 上的成熟 MMU 與 memory management；Stage 2 是其中的 page swap，目的地換成 DRAM 裡的壓縮空間，由 LZ4 HW 搬。

附註：Key point 只講結構，沒有提到兩段的性質（左邊有把握、右邊要探索），而這正是畫面上最大的兩行字。不算矛盾，但結論那一條沒有把主視覺最強的訊息收進來。

### 6. 困惑指數

**2**。主訊息一眼就懂，只有中間那條空白直立框、旋轉的 zoom 小字、沒標裝置的圓柱體讓人停頓一下。

### 7. 可疑的錯字或多餘文字

- 旋轉的「zoom in on page swap」字小又斜，第一眼讀成「zoom in on page snap」。不確定是生成的字形問題還是單純難讀，建議確認。
- 兩個 Stage 之間的空白直立框看起來多餘。
- 「Why we can expect it to work」「What stays, what is new」前面的 checkbox 多餘（不是待辦事項）。
- 其他文字沒有看到明顯錯字。

## 總結

**用自己的話說結論：** 團隊要先把這顆 processor 已有的 CPU MMU 和 kernel 的記憶體管理在多 core、多 thread 上帶起來，這段雖然對團隊是新的，但設計成熟，穩穩做就能完成；接著只動其中 page swap 這一小塊，把原本送去「the usual destination」的 page 改成交給 processor 外面的 LZ4 HW 壓縮後放在 DRAM，這段範圍小，但最佳設計還要摸索。

**讀完的感覺：** 第一段工作量大但不可怕；第二段範圍小但才是真正要動腦、要試的地方。整體給人「有計畫、知道難處在哪」的安心感。

### 總表

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 |
| 角色是否清楚 | 是（圓柱體只標「the usual destination」、中間空白直立框沒有標籤，屬小問題） |
| 畫面與結論是否一致 | 一致（Key point 沒有收進「sure path / exploration」的性質對比，但不矛盾） |

### 是否建議重生

**不建議重生。** 困惑指數 2，角色清楚，箭頭方向沒有與故事矛盾，畫面與 Key point 一致。

若要小修，可考慮：

1. 拿掉兩個 Stage 之間的空白直立框，或讓 zoom 線的小字橫放、放大。
2. 圓柱體註明是什麼（例如 disk 或 flash），或畫一條被打叉的舊路徑，讓「目的地被換掉」不必等讀到便條才懂。
3. 理由與說明的便條拿掉 checkbox，改用一般條列。
4. 視需要在 Key point 加半句兩段工作性質的對比，讓結論與主視覺的大字呼應。

# 冷讀報告：cpu-mmu-kernel-sw gen1 第 1 到 5 張

- 日期：2026-11-16
- 方法：只給圖、不給提示詞的冷讀
- 範圍：cpu-mmu-kernel-sw gen1 的第 1 到 5 張（01-why-translate、02-page-table-tlb-cpu-mmu、03-three-outcomes、04-the-processor、05-parts-of-the-cpu-mmu-kernel-sw）
- 讀法：每張先遮住底部 Key point，讀完畫面再讀 Key point 比對。

---

## 圖 1：Why an Address Is Translated（01-why-translate.png）

### 1. 人物與機器

| 標籤 | 是誰 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| MEDIA | 戴耳機、拿筆電的小人 | 讀 address 0x00416C80（橘色箭頭「MEDIA reads 0x00416C80」指向左欄的 page 0x416） | 只在意自己的 logical address 拿到資料 |
| translation（藍底方塊） | 一個「問題」而不是一台機器：「which frame holds this page right now?」 | 收進 page 0x416，送出「its frame」到 DRAM | 這個 page 現在在哪個 frame |
| kernel SW（紫色虛線方塊） | 軟體 | 「decides which frame holds each page」，往上箭頭「keeps the answer up to date」 | 答案保持最新 |
| DRAM（右欄） | 記憶體 | 被指到 frame at 0x80024000、offset 0xC80 | 無動作 |

- 角色不清的地方：
  - 「translation」沒有說是誰在做（硬體？軟體？）。第 1 張刻意不提 CPU MMU 也說得通，但冷讀者會想問「是誰在翻譯」。
  - MEDIA 畫成一個人，但副標題說「A program uses its own addresses」。冷讀者要自己推出 MEDIA 是一個程式（不是使用者）。人形加耳機容易讓人以為是「看影片的使用者」。

### 2. 看不懂的線或物件

- 線的方向都清楚：MEDIA → page 0x416 → translation → its frame → DRAM 的 frame；kernel SW → translation（往上）。
- 左欄與右欄都是一疊空格子，左欄是 page、右欄是 frame，靠標題分辨，可以懂。
- 「offset 0xC80」前的黑點：可推出是 page 內的一個位置，兩邊位置相同，表達「offset 不變」。可以懂，但黑點本身沒說明。
- 小疑問：translation 方塊沒有畫出它從 kernel SW 拿到的答案存在哪裡（之後幾張才會講 page table，這裡可以接受）。

### 3. 圖說的一句話（不看 Key point）

程式 MEDIA 用自己的 address 讀資料，每次存取都要把 page 換成 DRAM 裡的 frame（offset 不變），而 page 在哪個 frame 由 kernel SW 決定並維持最新。

### 4. 對照 Key point

Key point：Translation answers one question: which frame holds this page right now? Because the kernel keeps that answer, it can move pages without the program noticing.

**一致。** 畫面中央的問題句與 Key point 一字不差；「What this buys」框也講了 kernel 可以搬 page、程式不知道。

### 5. 困惑指數

**1**。一條路線、一個例子、算術寫明，不需要背景就能懂。

### 6. 可疑的錯字或多餘文字

- 無錯字。算術檢查：0x00416C80 在 4 KB page 下是 page 0x416、offset 0xC80，正確；0x80024000 + 0xC80 = 0x80024C80，正確。
- 「the kernel can even take the frame away for a while」語意稍模糊：是把 frame 從這個 page 拿走（page 暫時不在 DRAM）。冷讀者可懂大概，但「take the frame away」對誰拿走沒說。

---

## 圖 2：Page Table, TLB, CPU MMU: Who Holds the Mapping（02-page-table-tlb-cpu-mmu.png）

### 1. 人物與機器

| 標籤 | 是誰 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| MEDIA | 和圖 1 同一個人形（耳機、筆電），現在畫在 Core 0 裡 | 送出「MEDIA's address」給 CPU MMU | 拿到資料 |
| CPU MMU（藍底方塊） | 硬體 | 「checks the TLB on every load and store」，往下「look up the page」到 TLB | 只看 TLB |
| TLB（藍底方塊） | core 裡的小表 | 「a few recent entries only」，現在有一格 page 0x416: frame 0x80024000 | 只放幾格 |
| TLB miss handler（紫色虛線） | kernel SW，「runs on this core when the TLB has no entry」 | 讀 DRAM 的 PTE，再「fills the entry」到 TLB | 補上缺的那一格 |
| DRAM / page table | 記憶體中的完整表 | 三列 PTE：0x415 not valid、0x416 valid、0x417 valid | 無動作 |

- 角色都有標籤，分工清楚：CPU MMU 只讀 TLB，kernel SW 讀 page table 並填 TLB。

### 2. 看不懂的線或物件

- **少一條觸發線**：TLB 沒有那一格時，是怎麼走到 TLB miss handler 的？畫面上 CPU MMU / TLB 到 handler 之間沒有任何箭頭，只有 handler 方塊裡一行字「when the TLB has no entry」。冷讀者會問：handler 是一直在跑、定期跑，還是被 miss 叫起來？（exception 的概念完全沒出現。）
- **少一條出口線**：CPU MMU 查到 frame 之後，去 DRAM 讀資料的那一步沒畫。圖 1 有「its frame → DRAM」，圖 2 停在 TLB，讀者看不到「翻譯完後真的去讀 frame」。
- 「reads the PTE」箭頭從 handler 指向 page table：箭頭方向是「去讀」，資料其實是反方向流回 handler。小問題，看文字可懂。
- 「no arrow here: on this chip the CPU MMU never reads the page table」這段藍字很有用，冷讀者能抓到重點。但它浮在 Core 0 與 DRAM 之間的空白，沒有指向哪一條「不存在的線」，第一眼有點像遺落的註解。

### 3. 圖說的一句話（不看 Key point）

每個 core 裡的 CPU MMU 只查 TLB 這個小表；TLB 沒有那一格時，由 kernel SW 的 TLB miss handler 去 DRAM 的完整 page table 讀 PTE，填進 TLB。

### 4. 對照 Key point

Key point：The TLB is a small copy of the page table. Many chips have hardware that refills the TLB from the page table by itself; ours does not, so the kernel SW fills every TLB entry.

**一致。** 「ours does not」對應畫面上的「no arrow here」。「Many chips have hardware that refills」這個對照在畫面上沒有畫，只在 Key point 出現，不構成矛盾。

### 5. 困惑指數

**2**。分工清楚；唯一卡住的是 handler 怎麼被叫起來，畫面沒交代。

### 6. 可疑的錯字或多餘文字

- 無錯字。數字與圖 1 一致（page 0x416 → frame 0x80024000）。
- 副標題說「The TLB is a small copy inside each core」，畫面只畫 Core 0，可以接受。
- 「Why two tables」與「New words」對 TLB 的說明有些重複（兩處都說 TLB 小、在 core 裡），不算錯。

---

## 圖 3：One Access, Three Outcomes（03-three-outcomes.png）

### 1. 人物與機器

| 標籤 | 是誰 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| UI | 戴鴨舌帽、拿筆電的人形（第一次出現） | 「UI loads」，TLB hit，直接到 frame | 結論「UI notices nothing」 |
| MEDIA | 戴耳機的人形，和圖 1、2 相同 | 「MEDIA loads」，TLB miss、PTE valid | 「MEDIA is a little slower」 |
| NET | 頭上有天線的人形（第一次出現） | 「NET loads」，TLB miss、PTE not valid，page fault | 「NET is much slower」 |
| CPU MMU and TLB（藍底） | 硬體，三欄都有 | 第 1 欄「the entry is there」；第 2、3 欄「no entry: exception」 | 有沒有那一格 |
| TLB miss handler（紫色虛線） | kernel SW | 讀 PTE；valid 就寫 TLB，not valid 就交給 page fault handler | PTE 的內容 |
| page fault handler（紫色虛線，第 3 欄） | kernel SW | 「gives the page a frame, sets the PTE valid, writes the TLB entry」 | 給 page 一個 frame |
| frame（第 1 欄） | DRAM 的一格 | 被直接讀 | 無 |

- 三個程式用三種不同的頭飾區分，冷讀者看得出是三個不同的程式。UI 與 NET 是新面孔，沒有說明它們是什麼程式，但標籤夠用。

### 2. 看不懂的線或物件

- 第 1 欄 frame 裡的小方格沒有標籤。猜是「要讀的那筆資料」（對應圖 1 的 offset 黑點），但圖 1、2 用的是黑點，這裡改成方格，冷讀者要自己對起來。
- 第 3 欄 page fault handler「gives the page a frame」：只說給 frame，沒說 frame 裡的資料從哪裡來。冷讀者可能以為 page fault 只是配一個空 frame。如果這組圖之後要講「資料從別處搬回來」（例如解壓縮），這裡是第一個伏筆，但畫面沒有任何暗示。
- 第 2、3 欄的終點是「the load runs again: TLB hit」，沒有再畫一條到 frame 的箭頭。可以推出會像第 1 欄那樣，影響不大。
- TLB miss handler → page fault handler 的關係：是 TLB miss handler 呼叫 page fault handler，還是轉交？畫面是一條「PTE not valid」箭頭，讀成「接著做」可以接受。
- 線的顏色清楚：橘色是程式的存取路線，紫色是 kernel SW 的路線。

### 3. 圖說的一句話（不看 Key point）

同樣一次 load 有三種結果：TLB 有那一格就直接讀；沒有就進 exception 由 kernel 的 TLB miss handler 補 TLB；PTE 也不 valid 就再由 page fault handler 給 page 一個 frame，每多一層程式就慢一點。

### 4. 對照 Key point

Key point：A TLB hit is hardware only. A TLB miss always enters the kernel; if the PTE is valid the kernel only refills the TLB, and if not, it must first give the page a frame.

**一致。** 三欄正好對應 Key point 的三句。

### 5. 困惑指數

**1**。三欄並排、終點一句話說快慢，冷讀者一看就懂。這張也補上了圖 2 缺的「miss 怎麼進 kernel」（exception）。

### 6. 可疑的錯字或多餘文字

- 無錯字。
- 「What follows on this chip」的「this cost exists with or without compression」：這是全組圖第一次出現「compression」這個字，前面沒有鋪陳。對完全沒背景的讀者，這一句會讓人問「哪個 compression？」。對專案讀者則是有意的提示。

---

## 圖 4：The Processor: What Each Core Has, What Is Shared（04-the-processor.png）

### 1. 人物與機器

| 標籤 | 是誰 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| UI（鴨舌帽） | 程式，在 Core 0 的「hw thread: UI」 | 橘色箭頭「every load and store」進 CPU MMU and TLB | 一般存取 |
| MEDIA（耳機） | 程式，在 Core 0 的「hw thread: MEDIA」 | 沒有箭頭，只是在場 | 不明 |
| NET（天線） | 程式，在 Core 1 的「hw thread: NET」 | 紫色箭頭「a TLB miss: this hw thread runs the kernel code」指向 Core 1 的 CPU MMU and TLB | TLB miss |
| LOG（拿筆的人形，第一次出現） | 程式，在 Core 1 的「hw thread: LOG」 | 紫色長線一路往下到 DRAM 的 page table，標「a TLB miss here too, at the same time」 | TLB miss，同時發生 |
| CPU MMU and TLB（每個 core 一個） | 硬體，「one TLB, shared by both hw threads」 | 無 | 無 |
| L1 cache（每個 core 一個）、L2 cache（「shared by every core」） | 硬體 | 無 | 無 |
| DRAM：kernel code（exists once）、page table（shared by every core）、frames | 記憶體 | LOG 的線指到 page table | 無 |

- 四個程式的標籤清楚，hw thread 的方塊也都有名字。LOG 是新角色，沒有說明，但標籤夠用。
- 「processor」框包住兩個 core 與 L2，DRAM 在 processor 外面，結構清楚。

### 2. 看不懂的線或物件

- **兩條紫色線畫法不一致，讓人困惑**：
  - NET 的紫線只到 Core 1 自己的 CPU MMU and TLB 就停了。
  - LOG 的紫線越過 Core 1 的邊框、穿過（或疊在）L2 cache 方塊上，一路到 DRAM 的 page table。
  - 兩條都標成 TLB miss，冷讀者會問：為什麼 NET 的 kernel code 不讀 page table、LOG 的卻讀？是兩件不同的事，還是同一件事各畫一半？
- **LOG 的線穿過 L2 cache 方塊**：看起來像是讀 page table 繞過 L1、穿過 L2，冷讀者分不出這是「經過 L2」還是「線剛好疊上去」。若要表達 page table 的存取會進 cache，這條線沒說清楚；若不要表達，就不該疊在 L2 上。
- **紫色箭頭的方向意義**：NET 的紫箭頭從 hw thread 指向 CPU MMU and TLB，在圖 3 的配色裡紫色是 kernel SW。讀成「kernel code 去寫 TLB」還是「TLB miss 從 TLB 送進 kernel」都可以，方向沒有幫忙。圖 3 的 exception 是從 CPU MMU 往下到 handler，這裡反過來從 thread 往 MMU。
- **兩個 TLB miss 都在 Core 1**：NET 和 LOG 是同一個 core 的兩個 hw thread，共用同一個 TLB。畫面在講「同時在 kernel 裡」，但例子剛好是「同一個 core、同一個 TLB」，這和右邊「each core's TLB is its own copy」的跨 core 訊息不同，冷讀者容易把兩件事混在一起。
- 右邊「Two things to take away」第一條「Core 1 may lack an entry Core 0 has」：畫面裡兩個 TLB 都沒有畫任何 entry，沒有視覺證據。第二條「no hardware keeps the TLBs in step with the page table」也沒有畫。兩條 take away 都只靠文字。
- 只有 UI 有橘色箭頭，MEDIA 沒有。可以理解為只是舉例，不影響。

### 3. 圖說的一句話（不看 Key point）

processor 有兩個 core，每個 core 有自己的 CPU MMU、TLB 與 L1，兩個 hw thread 共用這個 TLB；L2、DRAM 裡的 kernel code 與 page table 給所有 core 共用；同一時間可以有不只一個 hw thread 因為 TLB miss 在跑 kernel code。

### 4. 對照 Key point

Key point：The page table is shared; the TLBs are private copies in each core. Several hw threads can be in the kernel at the same moment, each on its own core's TLB.

**部分一致。**
- 第一句（page table 共用、TLB 每個 core 一份）與畫面一致。
- 第二句「each on its own core's TLB」讀起來像是「不同 core 的 thread 各用各的 TLB」，但畫面上同時進 kernel 的 NET 和 LOG 在同一個 core，用的是同一個 TLB。畫面的例子沒有展示 Key point 想講的情況，反而引出「兩個 thread 同時改同一個 TLB 會怎樣」這個畫面沒回答的問題。
- 另外，Key point 沒有提到 L1、L2，但畫面花了不少面積在 cache 上；cache 在這張的角色不明（是背景還是重點？）。

### 5. 困惑指數

**3**。結構（誰私有、誰共用）一看就懂；但承載「同時進 kernel」這個重點的兩條紫線畫法不一致，又剛好都在同一個 core，冷讀者讀不出確定的意思。

### 6. 可疑的錯字或多餘文字

- 無錯字。
- 「one TLB per core, shared by its hw threads: assumed, not yet checked in the CPU manual」：對新手是多餘的設計備註，會讓人分心想「那如果不是呢？」。若是給設計團隊看則有用。
- 「a TLB miss here too, at the same time」的位置在 processor 框外、DRAM 框上方，離 LOG 很遠，靠紫線才能對回 LOG。

---

## 圖 5：The Parts of the CPU MMU Kernel SW（05-parts-of-the-cpu-mmu-kernel-sw.png）

### 1. 人物與機器

| 標籤 | 是誰 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| UI（鴨舌帽） | 程式 | 橘色箭頭「TLB miss」進 TLB miss handler | 觸發者 |
| NET（天線） | 程式 | **沒有任何箭頭**，只站在 UI 旁邊 | 看不出來 |
| TLB miss handler（紫色虛線，疊三層） | kernel SW | 「runs on every TLB miss, very short, never sleeps, many hw threads can be in it at once」；「reads the PTE」到 kernel tables；「PTE not valid」往下到 page fault handler | 快 |
| page fault handler（紫色虛線，疊三層） | kernel SW | 「runs when the PTE is not valid, may sleep, finds out why, then fixes it」；「calls」services；「page is compressed: a function call」到 compression kernel SW | 找出原因並修好 |
| services the handlers call（紫色虛線） | kernel SW | 四項：map/unmap、clear a page from every core's TLB、frame allocator、switch programs | 改表 |
| kernel tables（黑色實線框，上方有鎖 mm_lock） | 資料：page tables、free frames、which page belongs to whom | 被「lock, change, unlock」 | 被保護 |
| compression kernel SW（紫色虛線） | kernel SW，「a separate set of sheets」 | 被 page fault handler 呼叫 | 處理資料被壓縮的 page |

- NET 的角色看不出來。猜測是要表示「也可能是別的程式觸發」或「多個 hw thread 同時」，但畫面沒有任何線或文字支撐。
- 疊三層的虛線框沒有標註意義。看了下方「Who runs it」的「several copies of the same code can run at once, one per hw thread」才能推出是「同時有好幾份在跑」。

### 2. 看不懂的線或物件

- **「TLB miss」箭頭是橘色**：在圖 3，TLB miss 進 handler 的箭頭是紫色，橘色是「程式的 load/store」。這裡同一件事換成橘色，顏色語意走樣。
- **這張完全沒有畫 TLB 與 CPU MMU**：TLB miss handler 最主要的工作（寫 TLB entry）在這張沒有線；「clear a page from every core's TLB」也沒有對應的 TLB。標題叫「CPU MMU Kernel SW」，但硬體一個都沒出現，冷讀者要自己記得圖 2、3。
- **「reads the PTE」箭頭打在 mm_lock 守著的 kernel tables 上**：這條線看起來像也要經過鎖，但下方 OPEN 說「does the TLB miss handler take mm_lock? not decided yet」。畫面與 OPEN 的意思可以並存，但箭頭本身會讓人誤以為已經決定要拿鎖。
- **「page tables」是複數**：圖 2、4 都是單數「the page table」、「page table: shared by every core」。這張忽然變成複數，又有「switch programs: change which page table is used」，暗示每個程式各有一張 page table。這個概念前四張完全沒有鋪陳，冷讀者會疑惑「到底是一張還是很多張」。
- 「which page belongs to whom」：whom 是程式？還是 compression？沒有說明。
- 鎖的圖示只靠近 kernel tables，services 經「lock, change, unlock」進去，意思清楚。
- 「OPEN」標籤的意思可以推出是「還沒決定」，可懂。

### 3. 圖說的一句話（不看 Key point）

CPU MMU 的 kernel SW 分成兩個 handler（TLB miss handler 很短、不睡；page fault handler 可能睡），它們跑在出問題的 hw thread 上，透過幾個 service 在 mm_lock 保護下改共用的 kernel tables，遇到被壓縮的 page 就呼叫另外的 compression kernel SW。

### 4. 對照 Key point

Key point：Two handlers, entered from exceptions, run on the hw thread that missed. They use a few services that change the shared tables under mm_lock. Compression is reached from the page fault handler by a plain function call.

**一致，有一個小落差。** 三句都有對應的畫面。小落差是「Two handlers, entered from exceptions」：畫面上只有 TLB miss handler 是由 exception（橘色 TLB miss 箭頭）進來，page fault handler 是從 TLB miss handler 經「PTE not valid」走下去的，看起來不是另一個 exception 進來。冷讀者會問 page fault 本身是不是另一個 exception。

### 5. 困惑指數

**2**。主體（兩個 handler、services、鎖、compression 的接點）清楚；但 NET 沒有角色、疊層框沒標註、TLB 沒畫、page table 單複數突變，加起來讓人卡幾下。

### 6. 可疑的錯字或多餘文字

- 無錯字。
- 「may sleep」、「never sleeps」：sleep 對沒背景的讀者是術語，New words 沒有解釋。
- 標題「CPU MMU Kernel SW」：CPU MMU 是硬體，這個詞組第一次看會讀成「CPU MMU 裡的 kernel SW」。意思是「管 CPU MMU 的 kernel SW」，可接受但可以更直白。
- NET 人形可以視為多餘物件。

---

## 跨圖觀察

### 命名物件有沒有走樣

- **人物**：MEDIA（耳機）、UI（鴨舌帽）、NET（天線）、LOG（拿筆）每次出現長相一致，頭飾可以區分，沒有走樣。MEDIA 在圖 1 到 4 出現，圖 5 不見；LOG 只在圖 4 出現；NET 在圖 5 只是站著。
- **CPU MMU 與 TLB**：圖 2 是兩個分開的藍色方塊（CPU MMU、TLB），圖 3、4 合成一個「CPU MMU and TLB」方塊，圖 5 完全沒畫。合併本身不構成誤讀，但圖 2 剛教「CPU MMU 只看 TLB」，下一張就把兩者合成一格，會稍微削弱這個區分。
- **page table**：圖 2、4 是單數，畫在 DRAM 裡；圖 5 變成 kernel tables 裡的複數「page tables」，位置不再標 DRAM。
- **TLB miss handler**：圖 2、3、5 都是紫色虛線框，名稱一致。圖 5 改成疊三層。
- **frame**：圖 1 是右欄一格，圖 3 是一個有小方格的框，圖 4 是 DRAM 裡四個小方格。可以認得，但內部記號（黑點、小方格）沒統一。

### 分類顏色

- 大致一致：藍底實線 = 硬體（translation、CPU MMU、TLB、L1、L2）；紫色虛線 = kernel SW；橘色線 = 程式的存取路線；紫色線 = kernel SW 的動作；藍色字 = 旁註。
- 例外：
  - 圖 5 的「TLB miss」箭頭是橘色，圖 3 同一件事是紫色。
  - 圖 4 NET 的紫箭頭從 hw thread 指向 CPU MMU and TLB，方向與圖 3（從 MMU 往下進 handler）相反。
  - 圖 1 的 translation 是藍底（硬體色），但圖 1 沒說它是硬體；到圖 2 才知道是 CPU MMU。這不算錯，算是顏色先行提示。

### 故事線

- 1 → 2 → 3 很順：為什麼要翻譯 → 翻譯的答案放在哪（page table 與 TLB，本晶片沒有硬體去讀 page table）→ 一次存取的三種結果（hit、miss 補 TLB、page fault）。
- 3 → 4 稍微轉彎：從「一次存取」跳到「整顆 processor 的結構」，目的是為「同時」鋪路。轉得過去，但圖 4 的「同時進 kernel」例子畫在同一個 core，和它想帶出的「每個 core 各有 TLB」不太對齊。
- 4 → 5 有斷點：
  - 圖 5 引入了「page tables 複數」、「switch programs」、「which page belongs to whom」、「sleep」、mm_lock，前面都沒鋪陳。
  - 圖 5 拿掉了所有硬體，讀者要自己把軟體方塊接回圖 3 的流程。
  - 「compression」只在圖 3 的旁註出現過一次，到圖 5 才變成一個方塊。對完全沒背景的讀者，compression 為什麼會出現沒有交代（可能是刻意留給後面的圖）。

### 用我自己的話說這五張的結論

程式用自己的 address，每次 load/store 都要把 page 換成 DRAM 裡的 frame，offset 不變。完整的對照表 page table 在 DRAM，由 kernel 維護；每個 core 裡的 CPU MMU 只查一個很小的 TLB。這顆晶片沒有硬體去讀 page table，所以 TLB 一沒有那一格就進 exception，由 kernel 的 TLB miss handler 讀 PTE 補 TLB；PTE 也不 valid 時就是 page fault，由 page fault handler 給 page 一個 frame。processor 有好幾個 core、每個 core 好幾個 hw thread，TLB 每個 core 一份、page table 大家共用，所以好幾個 hw thread 可能同時在 kernel 裡。kernel SW 因此由兩個 handler 加幾個 service 組成，各自跑在出事的 hw thread 上，改共用的表時拿 mm_lock；遇到資料被壓縮的 page，page fault handler 直接呼叫 compression kernel SW。

### 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|
| 1 Why an Address Is Translated | 1 | 是 | 一致 |
| 2 Page Table, TLB, CPU MMU | 2 | 是 | 一致 |
| 3 One Access, Three Outcomes | 1 | 是 | 一致 |
| 4 The Processor | 3 | 否（NET 與 LOG 的兩條紫線意思不同，看不出各自在做什麼） | 部分一致 |
| 5 The Parts of the CPU MMU Kernel SW | 2 | 否（NET 沒有任何動作，角色看不出來） | 一致（「entered from exceptions」對 page fault handler 有小落差） |

### 建議重生

1. **圖 4（必要）**：困惑指數 3、角色不清、畫面與 Key point 部分一致。
   - 把「同時進 kernel」的例子改成跨 core（例如 Core 0 一個 thread、Core 1 一個 thread 同時 TLB miss），各自指到自己 core 的 TLB，兩條線畫法相同、都去讀同一張 page table。這樣才對得上 Key point 的「each on its own core's TLB」與「page table is shared」。
   - 讀 page table 的線不要疊在 L2 方塊上，或者明確畫成經過 L2。
   - 在兩個 TLB 裡各畫一兩格 entry，讓「Core 1 may lack an entry Core 0 has」有視覺證據。
   - 「assumed, not yet checked in the CPU manual」若是給新手看可移除。
2. **圖 5（建議，小修即可，不一定要整張重生）**：角色不清。
   - NET 要嘛拿掉，要嘛給它一條箭頭（例如也 TLB miss 進同一個 handler 的另一層，說明疊層框的意思），並在疊層框旁加一句「one copy per hw thread」。
   - 「TLB miss」箭頭改回圖 3 的紫色，或畫一個小小的 CPU MMU and TLB 方塊當起點，讓 exception 的來源與 TLB miss handler 寫 TLB 的去處都看得到。
   - 「page tables」單複數要和前面一致；若要講「每個程式一張」，前面需要先鋪陳，或在 New words 補一句。
   - 「reads the PTE」箭頭不要打在 mm_lock 守住的框正中央，以免和 OPEN 的「未決定」衝突。

圖 1、2、3 不需要重生。圖 2 可以考慮補一條 CPU MMU 到 TLB miss handler 的觸發線（exception），但圖 3 已經補上，不是必要。

# 冷讀驗收報告：cpu-mmu-kernel-sw gen2 第 4、5、8 張

- 日期：2026-11-16
- 方法：只給圖、不給提示詞的冷讀
- 讀的是 cpu-mmu-kernel-sw gen2 的第 4、5、8 張（`04-the-processor.png`、`05-parts-of-the-cpu-mmu-kernel-sw.png`、`08-page-fault-handler.png`）
- 讀者設定：沒碰過 CPU MMU、page table、TLB 的工程師，前幾張已看過 page、frame、page table、PTE、TLB、TLB miss、page fault 的介紹。每張先遮住底部 Key point，最後才讀。

---

## 圖 4：The Processor: What Each Core Has, What Is Shared

### 1. 人物與機器

- **UI、MEDIA、NET、LOG**：四個坐在筆電前的火柴人，頭上標名字，下面各有一個框寫 `hw thread: UI`、`hw thread: MEDIA` 等。Core 0 裡是 UI 與 MEDIA，Core 1 裡是 NET 與 LOG。看起來是「在跑的程式」，同時又被標成 hw thread。讀者會問：火柴人是程式，還是 hw thread？圖把兩者畫成同一個東西（右側 New words 說「a core can run two programs at once, one on each hw thread」，算是補上了，但火柴人本身的身分仍是混在一起的）。
- **MEDIA**（Core 0）在 TLB miss，紫色字「MEDIA misses in Core 0's TLB: the kernel reads the PTE」。**NET**（Core 1）同時也 miss，「NET misses in Core 1's TLB at the same moment」。在意的是：兩個 core 同時去讀同一個 page table。
- **UI、LOG**：沒有動作，只是在場。
- **CPU MMU and TLB**（每個 core 一個藍框）：寫「one TLB, shared by both hw threads」，各有一格 entry（Core 0 是 `page 0x416: frame 0x80024000`，Core 1 是 `page 0x2A7: frame 0x8003A000`）。
- **L1 cache**（每個 core 一個）、**L2 cache**（shared by every core）：只是在場，沒有動作。
- **DRAM**：裡面有 kernel code（exists once）、page table（shared by every core）、frames（四個空方格）。
- **kernel**：沒有被畫成人物或方框，只出現在紫色說明字「the kernel reads the PTE」裡。讀者得自己推「kernel 就在 MEDIA 那條 hw thread 上跑」。右側 New words 的最後一條（kernel code exists once, but several hw threads can run it at the same time）有幫助，但不是畫面本身說的。

### 2. 看不懂的線或物件

- **兩條紫色長箭頭**從 `hw thread: MEDIA`、`hw thread: NET` 的框一路往下，穿過 TLB 框、穿過 L1、穿過 L2，進到 DRAM 的 page table。
  - 箭頭起點是 hw thread，不是 kernel，沒標「kernel」的讀者會以為是 hardware 自己走去 page table（也就是 hardware page table walk）。這和「這個晶片沒有硬體自己讀 page table」的前提相反，只有靠旁邊的小字「the kernel reads the PTE」才能拉回來。
  - 箭頭穿過 L1、L2 方框，是在說「讀 PTE 會經過 cache」，還是只是畫線剛好穿過去？看不出來。
  - MEDIA 的箭頭剛好從 Core 0 TLB 裡 `page 0x416` 那一格旁邊穿過。讀者可能以為 MEDIA miss 的就是 0x416，但 0x416 明明在 TLB 裡，這樣不會 miss。圖沒說 MEDIA 和 NET 各自 miss 的是哪個 page。
- **箭頭只有去、沒有回**：kernel 讀完 PTE 之後把結果寫回 TLB 的那一步沒畫。Key point 說「each on its own core's TLB」，畫面上看不到「寫回自己 core 的 TLB」。
- **frames 的四個空方格**：和 TLB 裡的 frame 位址（0x80024000、0x8003A000）沒有連線，只是擺著。
- **kernel code: exists once**：沒有線連到任何 core，讀者知道它存在，但看不出它和那兩條箭頭的關係。

### 3. 圖說的一句話（不看 Key point）

一個 processor 有兩個 core，每個 core 有自己的 TLB 和 L1，共用 L2 和 DRAM 裡同一份 page table；兩個 core 上的 thread 可以同時 TLB miss、同時去讀那份 page table。

### 4. 讀 Key point 後：一致性

Key point：「The page table is shared; the TLBs are private copies in each core. Several hw threads can be in the kernel at the same moment, each on its own core's TLB.」

**一致**。shared page table、per-core TLB、兩個 hw thread 同時在 kernel 裡，畫面都有。小落差：「each on its own core's TLB」的意思是「各自填自己 core 的 TLB」，畫面只畫了讀 page table，沒畫寫回 TLB；「in the kernel」也只靠小字說明，不是畫出來的。

### 5. 困惑指數：2

結構一看就懂；扣分在紫色箭頭從 hw thread 直接穿 cache 到 page table，沒讀小字會誤以為是硬體在走 page table，而且和 TLB 裡現有的 entry 重疊。

### 6. 可疑的錯字或多餘文字

- 沒看到錯字。
- 副標「Each core has its own CPU MMU, TLB and L1 cache. The L2 cache, DRAM and the page table are shared by every core.」和 L2 框的「shared by every core」、page table 框的「shared by every core」、New words 的 L1/L2 那條，同一件事說了三到四次，略冗。
- 「one TLB per core, shared by its hw threads: assumed, not yet checked in the CPU manual」是給內部看的但書，新手讀者會有點疑惑「那到底是不是」，但這是誠實的標註，不算錯。

---

## 圖 5：The Parts of the CPU MMU Kernel SW

### 1. 人物與機器

- **UI**：戴帽子的火柴人與筆電。唯一的人物，是觸發者：「UI's access misses in the TLB」。這張沒有標它是 hw thread。
- **TLB miss handler**（紫色虛線、疊三層）：runs on every TLB miss、very short, never sleeps、many hw threads can be in it at once。在意的是快、不能睡。
- **page fault handler**（紫色虛線、疊三層）：runs when the PTE is not valid、may sleep、finds out why, then fixes it。
- **services the handlers call**（紫色虛線大框）：四個 service：map or unmap a page（write its PTE）、clear a page from every core's TLB、frame allocator、switch programs（see sheet 10）。
- **kernel tables**（實線框）：page table、free frames、which page belongs to whom，加一個鎖圖示「mm_lock: taken by the services」。
- **compression kernel SW**（紫色虛線）：a separate set of sheets, called for a page whose data is compressed。
- 「drawn stacked: several hw threads can run the same handler at once」這行藍字把疊層的意思講清楚了，很好。
- 角色清楚，沒有無標籤的東西。

### 2. 看不懂的線或物件

- **「reads the PTE: with or without mm_lock is OPEN」**：這裡的 OPEN 是「還沒決定」的意思，但它緊接在 mm_lock 後面，又和右邊的鎖圖示同一張圖，新手很容易讀成「mm_lock 是開著的（沒鎖）」。同一張圖下方「Who runs it」框右上的黃色 **OPEN** 標籤也是同一種用法，這個詞在鎖的脈絡裡有歧義。
- **TLB miss handler 沒有「寫 TLB」的箭頭**：這張圖裡 TLB miss handler 只有「讀 PTE」和「PTE not valid → page fault handler」兩條線。它最主要的工作（把 PTE 填進 TLB）沒有畫，這張圖也沒有 TLB 這個物件。讀者會問：PTE 有效的時候，它讀完之後做什麼？
- **只有 page fault handler 有「calls」箭頭到 services**：TLB miss handler 會不會呼叫任何 service？圖上看起來不會。但框的標題是「services the handlers call」（複數 handlers），和線不一致。
- **switch programs 放在 services 裡**：「change which page table is used」聽起來是排程器的事，不太像 page fault handler 會呼叫的東西。讀者會疑惑為什麼它在這一框裡、誰呼叫它（圖指向 sheet 10，這張沒解釋）。
- **compression kernel SW 和 services、mm_lock 的關係**：compression 這一框沒有箭頭到 services 或 kernel tables，看不出它要不要拿 mm_lock、會不會改 page table。
- **沒有回程**：page fault handler 修好之後，UI 怎麼繼續？圖上沒有回到 UI 的線（第 8 張有說「LOG's instruction runs again」，這張沒有）。
- 「Who runs it」框右上的 OPEN 標籤蓋住整個框，但實際上只有最後一行（TLB miss handler 要不要拿 mm_lock）是未定的，前兩行是定案的敘述。

### 3. 圖說的一句話（不看 Key point）

kernel SW 有兩個入口：TLB miss 時先進 TLB miss handler，PTE 無效再交給 page fault handler；後者呼叫幾個在 mm_lock 下修改 kernel 表的 service，遇到壓縮過的 page 就呼叫 compression kernel SW；這些程式沒有自己的 thread，都在出事的 hw thread 上跑。

### 4. 讀 Key point 後：一致性

Key point：「The TLB miss handler, entered by an exception, and the page fault handler it hands over to both run on the hw thread that missed. They use a few services that change the shared tables under mm_lock. Compression is reached from the page fault handler by a plain function call.」

**部分一致**。
- 「both run on the hw thread that missed」、「compression by a plain function call」：一致。
- 「entered by an exception」：畫面沒有 exception 這個詞或符號，只有「UI's access misses in the TLB」的箭頭。
- 「They use a few services」：Key point 說兩個 handler 都用 service，畫面只有 page fault handler 有 calls 箭頭；TLB miss handler 是直接讀 page table，沒經過 service。

### 5. 困惑指數：2

架構清楚，分工一看就懂；扣分在 OPEN 一詞與 mm_lock 擺在一起容易讀錯，以及 TLB miss handler 少了「寫 TLB」這個主要動作。

### 6. 可疑的錯字或多餘文字

- 沒看到錯字。
- 「reads the PTE: with or without mm_lock is OPEN」文法上不通順，讀起來像一句沒寫完的話。建議改成類似「reads the PTE (takes mm_lock? not decided)」。
- 標題「The Parts of the CPU MMU Kernel SW」：「CPU MMU Kernel SW」連在一起，新手可能以為這是 CPU MMU 硬體裡的軟體。前面幾張若已定義過這個詞就沒問題。
- 「Who runs it」框的最後一行和上方箭頭上的「with or without mm_lock is OPEN」重複講同一個未決事項。

---

## 圖 8：The Page Fault Handler: Find the Cause, Then Fix It

### 1. 人物與機器

- **LOG**：火柴人與筆電，手上拿筆。「LOG loads from page S」，是觸發者。小落差：手上的筆會讓人聯想到「寫」，但文字說的是 load（讀）。
- **TLB miss handler**：S's PTE is not valid → 交給 page fault handler。
- **page fault handler**：上方有一個關著的鎖圖示「mm_lock」。take mm_lock, read S's PTE again, another hw thread may have fixed it meanwhile。在意的是「先拿鎖再看一次」。
- **五個原因框**（紫色虛線）：already valid now / first touch: no data yet / the data is compressed / the access is not allowed / the address belongs to nothing。
- **兩個結局框**：finish: fixed（set PTE valid if needed、write TLB entry、release mm_lock、return、LOG's instruction runs again），finish: refused（release mm_lock、report an error to LOG）。
- **compression kernel SW**：只在文字裡出現（「call the compression kernel SW to decompress it」），沒有自己的框。
- 角色清楚。

### 2. 看不懂的線或物件

- 分支結構清楚：前三個原因指向 finish: fixed，後兩個指向 finish: refused。箭頭方向沒有問題。
- **「the data is compressed」這一支的鎖**：黃色便條說 handler 睡覺時會放掉 mm_lock，但流程圖上這一支直接走到 finish: fixed 的「release mm_lock」，沒畫「放鎖、睡、再拿鎖」。讀者要把便條和流程圖自己拼起來，而且會問：醒來之後要不要再檢查一次 PTE？
- **黃色便條「in the model: a page fault is refused if it happens in an interrupt handler, in code that holds a lock, or in a hard real-time thread」**：
  - 「in the model」是哪個 model？這張圖沒交代。
  - 這是第六種「refused」的情況，但它不在五個原因框裡，也沒有箭頭到 finish: refused。Key point 說「two end with an error」，這條會讓讀者數不清楚。
  - 「in code that holds a lock」：page fault handler 自己就拿著 mm_lock，讀者會短暫困惑「那 handler 自己算不算」。
- **page S**：S 這個名字沒解釋，但不影響理解。
- 「report an error to LOG」：error 怎麼送給程式（程式會被結束嗎？）沒說，對這張圖的層次來說可以接受。

### 3. 圖說的一句話（不看 Key point）

TLB miss handler 發現 PTE 無效後交給 page fault handler；它先拿 mm_lock 再讀一次 PTE，依原因分成五種處理，三種修好後讓原指令重跑，兩種回報錯誤；壓縮過的 page 只是其中一種原因。

### 4. 讀 Key point 後：一致性

Key point：「The page fault handler checks the PTE again under the lock, then acts on the cause: three causes end with the page in a frame, two end with an error for the program. Bringing back a compressed page is just one of the causes.」

**一致**。三對二的分法、under the lock、compressed 只是其中之一，畫面都畫得很清楚。唯一會打架的是黃色便條裡的另一種 refused 情況，但它不改變 Key point 的結論。

### 5. 困惑指數：2

主流程一看就懂，是三張裡最清楚的；扣分在黃色便條的「in the model」與額外的 refused 情況沒接上流程圖，以及壓縮那一支放鎖的時機要讀者自己拼。

### 6. 可疑的錯字或多餘文字

- 沒看到錯字。
- 「Where page swap fits」框：「page swap」這個詞在這張圖裡沒定義，New words 也沒有它；它被等同於「the compressed one」，若前幾張沒定義過，新手會卡一下。
- 「Where page swap fits」的第二段（compression kernel SW runs on LOG's hw thread too, as a function call）和第 5 張的 Key point 重複，可視為刻意的回顧。
- New words 列了 interrupt handler 與 hard real-time thread，兩者只為了黃色便條的一句話而存在，篇幅比重偏高。

---

## 跨圖觀察

1. **人物連貫性好**：UI、MEDIA、NET、LOG 在第 4 張登場，第 5 張由 UI、第 8 張由 LOG 觸發，讀者能接上。但第 4 張把火柴人同時當「程式」又當「hw thread」，第 5、8 張又不再標 hw thread，程式與 hw thread 的關係只靠 New words 一句話撐著。
2. **kernel 從不畫成人物**：三張都一致地把 kernel SW 畫成「在出事的 hw thread 上跑的程式碼」，和第 5 張「no part has its own thread」相符，觀念一致。代價是第 4 張的紫色箭頭從 hw thread 直接畫到 page table，沒讀小字的人會看成硬體在走 page table，和平台前提相反。
3. **「寫 TLB」這一步只在第 8 張出現**：第 4 張只有讀 PTE 的去程，第 5 張的 TLB miss handler 也沒有寫 TLB 的線。新手可能到第 8 張才明白 TLB 是 kernel 寫的。
4. **OPEN 這個標記與 mm_lock 撞詞**：第 5 張在 mm_lock 旁邊用 OPEN 表示「未決」，在講鎖的圖裡容易讀成「鎖是開的」。建議改用「not decided」或「?」。
5. **mm_lock 的形象一致**：第 5、8 張都用同一個鎖圖示，第 8 張把它放在 page fault handler 頭上，很直觀。
6. **compression 的定位一致**：第 5、8 張都說是 page fault handler 的一個 function call、在同一條 hw thread 上跑，訊息前後一致。
7. Key point 的位置與字體一致，冷讀時容易遮住，好操作。

## 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|---|
| 4 The Processor | 2 | 是（火柴人「程式＝hw thread」混用，kernel 只在小字裡） | 一致（「寫回各自的 TLB」沒畫） |
| 5 Parts of the CPU MMU Kernel SW | 2 | 是 | 部分一致（exception 沒畫；Key point 說兩個 handler 都用 service，畫面只有 page fault handler 呼叫） |
| 8 Page Fault Handler | 2 | 是 | 一致 |

## 建議重生

照標準（困惑指數 3 以上、或角色不清、或畫面與結論不一致），**沒有必須重生的圖**。

可選的小修（若要再生一次時順手處理）：

- 圖 4：紫色箭頭起點改成標明「kernel on MEDIA's hw thread」，避開 TLB 裡現有的 entry，並加一條寫回自己 core TLB 的回程。
- 圖 5：把「with or without mm_lock is OPEN」改成「takes mm_lock? not decided」；給 TLB miss handler 加一條「write the TLB entry」的線；讓 Key point 的「They use a few services」與畫面對齊（或改成只說 page fault handler）。
- 圖 8：黃色便條的「in the model」交代是哪個 model，或把那種 refused 情況接到 finish: refused。

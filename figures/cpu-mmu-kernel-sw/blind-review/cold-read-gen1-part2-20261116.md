# 冷讀驗收報告：cpu-mmu-kernel-sw gen1 第 6 到 10 張

- 日期：2026-11-16
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：cpu-mmu-kernel-sw gen1 的第 6 到 10 張（`06-the-pte-is-ours.png`、`07-tlb-miss-handler.png`、`08-page-fault-handler.png`、`09-changing-a-mapping.png`、`10-many-programs.png`）

每張先遮住底部 Key point 讀畫面，再讀 Key point 對照。

---

## 第 6 張：The PTE Is Ours to Design

### 1. 人物與機器

- 沒有任何人物。這張是格式比較圖。
- 兩個「決定者」只用欄標題出現：左欄「Fixed by the CPU」，右欄「Decided by the kernel」。角色看得懂：CPU 決定 TLB entry 的格式，kernel 決定 PTE 的格式與 page table 的形狀。
- 「TLB miss handler」只出現在紫色弧線箭頭的文字上（the TLB miss handler converts and writes），沒有方塊，也沒有說它屬於 kernel。前幾張若已介紹過就沒問題，只看這張要自己推。

### 2. 看不懂的線或物件

- 紫色弧線箭頭從右邊 PTE 指向左邊 TLB entry，方向是「從 PTE 轉換後寫進 TLB」，看得懂。
- PTE 外面的紫色虛線框是什麼意思沒有說明。猜是「kernel 可以改的東西」，但畫面沒講。TLB entry 是淺藍底，PTE 是白底，顏色的分類也沒有說明。
- 兩個「OPEN」標籤（左上與表格右邊）的意思是「還沒決定、還不知道」，靠旁邊的藍字可以猜到，但這張本身沒定義 OPEN。
- TLB entry 有「page」欄，PTE 沒有；PTE 有「valid」欄，TLB entry 沒有。新手可能會問為什麼不同。畫面沒說 PTE 本身用位置代表 page、TLB 裡只放有效的 entry。
- 表格第三列「hash table / good when: many address spaces share it」：「share it」是指很多程式共用一張表，對新手太簡短；address space 這個詞在第 10 張才定義。

### 3. 圖說的一句話

TLB entry 的格式由 CPU 決定，PTE 的格式與 page table 的形狀由 kernel 自己決定；形狀有三種選法，在 TLB miss handler 要讀幾次與表要佔多少記憶體之間取捨，目前還沒決定。

### 4. 對照 Key point

一致。Key point 說「沒有硬體讀 page table，所以格式是 kernel 的選擇；handler 越快通常表越大；還沒決定」，三點畫面都有。「通常」這個字也照顧到了 hash table 那一列不完全符合「越快越大」。

### 5. 困惑指數

2。主旨一眼看得懂，只有紫色虛線框、OPEN 標籤、PTE 與 TLB entry 欄位差異沒解釋。

### 6. 可疑的錯字或多餘文字

- 右欄「PTE」標籤上方有一小段多出來的橫線，像是殘筆。
- 副標題「reads the  page  table」字距不均（手寫風格造成，不算錯字）。
- 右欄藍字「the kernel may also keep a used mark here: see sheet 7」：第 7 張只在 New words 裡定義 used mark，流程裡沒有畫出設 used mark 的步驟（見跨圖觀察）。

---

## 第 7 張：The TLB Miss Handler, Step by Step

### 1. 人物與機器

- 「NET」：棒狀人物，頭上有一根天線，坐在筆電前。是 user SW 泳道裡的程式。在做的事：從 page R 讀資料。它在意的是自己的 load 能完成。NET 是哪種程式（網路？）畫面沒說，前幾張若介紹過就沒問題。
- 三條泳道標籤清楚：「user SW」、「CPU」、「kernel SW, on NET's hw thread」。CPU 只做一件事：發現 TLB 沒有 R，丟 exception。kernel SW 做 3 到 7 步。
- 角色清楚。

### 2. 看不懂的線或物件

- 1→2→3→…→7→8 的箭頭方向清楚。7 到 8 的箭頭往上穿過 CPU 泳道但沒有 CPU 方塊，表示 CPU 重跑 load，可以接受。
- 第 6 步往下的紫色「not valid」分支，接到紫色虛線框「not valid: go to the page fault handler」，看得懂，也接上下一張。
- 第 4 步「find where R's PTE is from R's page number」讀起來卡住：像是在說「PTE 來自 page number」。應該是「from R's page number, find where R's PTE is」。
- 「used mark」在 New words 裡定義，說「likely only this handler can set it」，但 3 到 7 步沒有任何一步設 used mark。讀者會問：那它在哪一步設？第 6 張還指名「see sheet 7」。
- 底部黃色兩框（Why it must be tiny、Still to decide）與白色 New words 框，黃色是什麼分類沒說明；第 6 張的 OPEN 是白底，這張的 OPEN 框是黃底。
- 「Still to decide」的「how the handler reaches the page table without the TLB」對新手是個好問題，但它和 Why 框第三行「page table must be reachable without the TLB」重複。

### 3. 圖說的一句話

NET 讀 page R 時 TLB 沒有 entry，CPU 丟 exception，kernel 在 NET 自己的 hw thread 上存暫存器、找到並讀 R 的 PTE、寫進這個 core 的 TLB、還原後返回，NET 的 load 重跑就 hit；PTE 無效就轉給 page fault handler；因為它跑得極頻繁，必須很小、不能睡、本身不能 TLB miss。

### 4. 對照 Key point

一致。「讀一個 PTE、寫一個 TLB entry、每條指令都算數、自己不能 TLB miss」都在畫面上。

### 5. 困惑指數

2。流程本身一看就懂；扣分在第 4 步的句子與 used mark 沒有對應步驟。

### 6. 可疑的錯字或多餘文字

- 第 4 步「find where R's PTE is from R's page number」語序造成誤讀。
- New words 的「with no hardware walk」：「hardware walk」這個詞在這張沒定義（第 6 張用的是「no hardware reading the page table」），用詞不統一。

---

## 第 8 張：The Page Fault Handler: Find the Cause, Then Fix It

### 1. 人物與機器

- 「LOG」：棒狀人物，手拿鉛筆、坐在筆電前，頭上沒有天線。和 NET 外型不同，是另一個程式，可以分辨。在做的事：從 page S 讀資料。
- 方塊「TLB miss handler」、「page fault handler」（上方有鎖頭圖示與「mm_lock」）、五個原因框、「finish」框。
- 這張沒有泳道，看不出哪些在 CPU、哪些在 kernel SW，也看不出跑在哪個 hw thread。第 7 張用泳道交代得很清楚，這張只在左下文字框「the compression kernel SW runs on LOG's hw thread too」間接說到。不算角色不清，但比第 7 張弱。
- 「the compression kernel SW」是誰：沒有方塊、沒有定義。名稱裡有 compression，但它在這裡要做的是把壓縮的資料「解壓縮」回來，新手可能以為它是去壓縮。

### 2. 看不懂的線或物件

- 所有方塊都是紫色虛線框，包括 TLB miss handler。第 7 張的 TLB miss handler 步驟是黑色實線框，只有「not valid」分支是紫色虛線。這張的紫色虛線代表什麼看不出來。
- 從 page fault handler 到「already valid now」的箭頭從方塊右上角出發，形狀有點怪，但不影響理解。
- 五個原因裡，「the access is not allowed」與「the address belongs to nothing」兩個錯誤分支沒有往後的箭頭。讀者會問：mm_lock 有沒有放掉？LOG 之後怎樣？
- 「already valid now: just write the TLB entry」接到 finish，但 finish 第一行寫「set S's PTE valid」。已經 valid 的情況再設一次 valid，讀起來重複。
- 左下黃色便條「in the model: a page fault in an interrupt handler, with a lock held, or in a hard real-time thread is refused」：
  - 「the model」是什麼沒說明。
  - 最讓人困惑的是：同一張圖的 handler 自己拿著 mm_lock、去呼叫可能睡著的解壓縮。讀者會問「拿著 lock 時 fault 被拒絕，那 handler 拿著 mm_lock 睡覺為什麼可以？」畫面沒解釋這兩件事的差別（一個是發生 fault 的那段程式本來就拿著 lock，一個是 handler 自己拿的 lock）。
- 「Where page swap fits」：「page swap is one of the causes above: the compressed one」把 page swap 和壓縮畫上等號，page swap 這個詞在這張第一次出現、沒有定義。
- 「Key point」標籤是淺藍底，第 6、7、9、10 張都是白底。

### 3. 圖說的一句話

LOG 碰到 PTE 無效的 page S，TLB miss handler 轉給 page fault handler；它先拿 mm_lock、重讀 PTE，依原因分五路：已經有效、第一次碰、資料被壓縮、權限不准、位址不存在；前三路都在 finish 設好 PTE 與 TLB、放 lock、讓 LOG 重跑，後兩路是 LOG 的錯誤。

### 4. 對照 Key point

部分一致。「在 lock 下重查 PTE、依原因處理、壓縮只是其中一種原因」都對得上。但「the handler's start and finish are the same for all of them」與畫面不符：兩個錯誤原因沒有接到 finish，finish 也只寫了成功的收尾。

### 5. 困惑指數

3。主幹看得懂，但錯誤分支沒有收尾、「compression kernel SW」的名稱容易誤讀成壓縮、「拿著 lock 的 fault 被拒絕」和「handler 拿著 mm_lock 睡覺」放在同一張沒有解釋，這三點會讓新手停下來。

### 6. 可疑的錯字或多餘文字

- 「LOG loads from page S」橙色字擠在箭頭上方，字很小。
- finish 框「set S's PTE valid」在「already valid now」那一路是多餘的動作。
- 「in the model」沒有交代 model 是什麼。

---

## 第 9 張：Changing a Mapping: Which Way Matters

### 1. 人物與機器

- 沒有人物，也沒有畫 core 或 TLB。
- 「kernel SW」在左欄與右欄各有一個紫色虛線框。中間欄的 1、2、3 步沒有標誰在做，只能推是 kernel SW。
- 「page table」方塊（左欄）有標籤。
- 「other hardware」（中間第 3 步「hand it to other hardware」）是誰沒有說。新手不知道 frame 會交給什麼硬體。

### 2. 看不懂的線或物件

- 左欄只有一個箭頭標「1 write the PTE」，只有一步卻編了號 1，看起來像漏了第 2 步。
- 中間欄的「the reverse order lets a core refill the old entry from a PTE that is still valid」要想一下才懂：reverse order 是「先清 TLB、再設 PTE 無效」。沒有畫出這個錯誤順序的反例，只有一句藍字。
- 右欄「Allow less」只寫兩個動作，沒有編號，也沒有說要不要「wait until all are done」。中間欄特別強調要等，右欄沒說，讀者會問是不是可以不等。
- 整張講「every core's TLB」，但畫面上一個 core、一個 TLB 都沒有。「If one core is skipped」那一框全靠文字想像。
- 「in the model, a test that skips one core fails at once」：model 和 test 是什麼沒說明（第 8 張也有同樣的問題）。
- 「whether the TLB remembers that a PTE was not valid」對新手不好懂：TLB 不是只放有效的 entry 嗎？
- 這張的紫色虛線框代表 kernel SW 的動作，和第 8 張（所有 handler 方塊）、第 10 張（選項 A/B）的用法不同。

### 3. 圖說的一句話

讓 page 拿到 frame 只要寫 PTE，別的 core 下次 miss 自然讀到新的；拿走 frame 或降低權限時，要先把 PTE 改掉、再清掉每個 core 的 TLB 並等完成，最後才能重用 frame，順序反過來或漏一個 core 都會讓舊 entry 繼續被用。

### 4. 對照 Key point

一致。拿走 frame 的三步順序與「降權限也要清」都在畫面上。

### 5. 困惑指數

2。三欄對照很清楚，結論容易抓到；扣分在沒有畫 core 與 TLB、右欄沒說要不要等、「other hardware」與「the model」沒交代。

### 6. 可疑的錯字或多餘文字

- 左欄「1 write the PTE」孤立的編號 1。
- 沒有明顯的拼字錯誤。

---

## 第 10 張：Many Programs, One TLB per Core

### 1. 人物與機器

- 「UI」：戴帽子的棒狀人物、筆電。有自己的 page table。
- 「NET」：頭上有天線的棒狀人物、筆電。和第 7 張的 NET 外型一致。在中間欄「NET now runs on Core 0 and reads page 0x416」。
- 「MEDIA」、「LOG」：只以文字出現在 Core 1 的兩個 hw thread 方塊裡，沒有畫人物。LOG 在第 8 張是人物，這張變成文字；MEDIA 是第一次出現，沒有人物也沒有介紹。
- 機器：「TLB of Core 0」、「Core 1」裡的「TLB of Core 1, shared by both hw threads」，淺藍底，看得懂。
- 角色清楚。

### 2. 看不懂的線或物件

- 中間欄的危險是暗示的：Core 0 的 TLB 裡有「page 0x416: frame 0x80024000, left over from UI」，NET 正要讀 page 0x416。讀者要自己回頭對照左欄，才知道 NET 會讀到 UI 的 frame（0x80024000 而不是 NET 的 0x8003A000）。畫面上沒有打叉、沒有「wrong frame」之類的標記。
- page 用 page number（0x416），frame 用位址（0x80024000），兩者單位不同，新手可能困惑。
- 選項 A/B 用紫色虛線框，和前幾張紫色虛線的意思不同。
- Open questions 第三行「the kernel's own pages: mapped the same way in every program?」對新手是突然冒出來的，畫面上沒有任何 kernel page 的東西。
- 「New word: address space」放在 Open questions 框的右下角，和第 7、8 張獨立的「New words on this sheet」框格式不同；而且 address space 在副標題、選項 B、右欄都先用到了才定義。
- Open questions 框左上方外面有一個小點，像殘筆。

### 3. 圖說的一句話

每個程式有自己的 page table 時，同一個 page number 在不同程式對到不同 frame；一個 core 換程式時 TLB 裡留著上一個程式的 entry，要嘛每次切換清掉、要嘛每個 entry 加上 address space 的 tag；同一個 core 的兩個 hw thread 同時跑不同程式就只能靠 tag。

### 4. 對照 Key point

一致。

### 5. 困惑指數

2。三欄的推理線清楚；扣分在中間欄的錯誤沒有標出來，要讀者自己對照數字，以及 MEDIA 突然出現。

### 6. 可疑的錯字或多餘文字

- Open questions 框左上外面的小點。
- 沒有明顯的拼字錯誤。

---

## 跨圖觀察

### 命名物件的外型

- NET：第 7 張與第 10 張都是頭上一根天線、筆電，外型一致。
- LOG：第 8 張是拿鉛筆的人物；第 10 張只剩文字「hw thread: LOG」。不算走樣，但第 10 張沒有畫成人物，和 UI、NET 的待遇不同。
- UI：只在第 10 張出現，戴帽子，和 NET、LOG 分得開。
- MEDIA：只在第 10 張以文字出現，沒有人物，也沒有介紹。
- TLB：第 6 張的 TLB entry 與第 10 張的兩個 TLB 都是淺藍底，一致。第 7、8、9 張沒有把 TLB 畫成物件（第 9 張講的就是清 TLB，卻沒畫 TLB）。
- page table：第 9、10 張都是白底實線、上方標題列的方塊，一致。
- mm_lock：第 7 張是文字，第 8 張是鎖頭圖示加文字。
- TLB miss handler：第 7 張是五個黑色實線步驟框，第 8 張變成一個紫色虛線框。同一個東西兩種畫法。

### 分類顏色

- 淺藍底 = TLB：一致。
- 藍色手寫字 = 註解：一致。
- 橙色箭頭 = user SW 的存取：第 8、10 張一致；第 7 張的 user load 是黑色箭頭。
- 紫色虛線框：意思每張不同，沒有圖例。第 6 張是 kernel 決定的 PTE；第 7 張是 not valid 分支；第 8 張是所有 handler 方塊；第 9 張是 kernel SW 的動作；第 10 張是設計選項 A/B。這是最明顯的不一致。
- 黃色底：第 7 張用在「Why it must be tiny」與「Still to decide（OPEN）」；第 8 張用在「Unlike the TLB miss handler」；第 6、9、10 張的 OPEN 框是白底。黃色是「注意事項」還是「未決定」看不出來。
- Key point 標籤：第 8 張是淺藍底，其他四張是白底。
- New words 的格式：第 6、7、8 張是獨立框；第 9 張沒有；第 10 張縮成一行藍字。

### 故事線

順序是通的：第 6 張說 PTE 是 kernel 自己定的，第 7 張說 TLB miss 時 kernel 怎麼從 PTE 填 TLB，第 7 張的 not valid 分支接到第 8 張的 page fault handler，第 9 張講改 mapping 時清 TLB 的順序，第 10 張把問題擴大到多個程式與 hw thread 共用 TLB。

斷掉的地方：

1. 第 6 張說 used mark「see sheet 7」，第 7 張的流程裡沒有設 used mark 的步驟，只在 New words 裡定義。
2. 第 8 張的「compression kernel SW」與「page swap」第一次出現就直接用，沒有交代；名稱讓人以為是去壓縮而不是解壓縮。
3. 第 8 張到第 9 張之間少一句「為什麼要拿走 frame」。第 8 張的 first touch 與 compressed 都要一個 free frame，第 9 張的「take a frame away」就是為了生出 free frame，但兩張之間沒有連起來；第 9 張的「hand it to other hardware」也沒說是什麼硬體。
4. 「the model」在第 8、9 張出現，沒有交代是什麼。
5. 第 10 張的 MEDIA 沒有介紹就出現。

### 用我自己的話說這五張的結論

CPU 只規定 TLB 長什麼樣；因為沒有硬體讀 page table，PTE 和整張表長什麼樣都由 kernel 決定，而這個選擇會決定 TLB miss handler 要讀幾次記憶體、表要佔多大，目前還沒決定。每次 TLB miss 都由 kernel 在出事的那個 hw thread 上跑 TLB miss handler：讀一個 PTE、寫一個 TLB entry，它跑得非常頻繁，所以要極小、不能睡、本身不能 miss。PTE 無效就交給 page fault handler，它拿 mm_lock 重查一次（別的 thread 可能已經修好），再依原因處理；取回壓縮過的 page 只是其中一種原因，可以睡。改 mapping 時，給 frame 只要寫 PTE；拿走 frame 或降權限，一定要先改 PTE、再清所有 core 的 TLB 並等完成，最後才能重用 frame。多個程式各有 page table 時，同一個 core 的 TLB 可能留著別的程式的 entry，切換時要清掉或用 address space tag；同一個 core 的兩個 hw thread 同時跑不同程式就只能用 tag。

### 總表

| 張 | 標題 | 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|---|---|
| 6 | The PTE Is Ours to Design | 2 | 是 | 一致 |
| 7 | The TLB Miss Handler, Step by Step | 2 | 是 | 一致 |
| 8 | The Page Fault Handler: Find the Cause, Then Fix It | 3 | 是（但沒有泳道，compression kernel SW 沒交代） | 部分一致 |
| 9 | Changing a Mapping: Which Way Matters | 2 | 是（中間欄的步驟沒標誰做，可推得 kernel SW；沒有畫 core 與 TLB） | 一致 |
| 10 | Many Programs, One TLB per Core | 2 | 是 | 一致 |

### 建議重生

只有第 8 張符合條件（困惑指數 3，畫面與結論部分一致）：

- **第 8 張**：
  - Key point 說「start and finish are the same for all」，但兩個錯誤分支沒有接到 finish。要嘛畫出錯誤分支的收尾（放 mm_lock、對 LOG 回報錯誤），要嘛改 Key point 只說成功的三路。
  - 「the compression kernel SW」改成看得出是「解壓縮」的說法，或在 New words 定義。
  - 黃色便條「with a lock held … is refused」與 handler 自己拿 mm_lock 睡覺放在一起會被誤讀，需要一句話說明兩者的差別，或拿掉「with a lock held」。
  - 「already valid now」那一路接到 finish 時不該再「set S's PTE valid」。
  - 考慮加回第 7 張的泳道（user SW / CPU / kernel SW on LOG's hw thread），兩張畫法一致。
  - 「Key point」標籤的淺藍底改回白底。

不需要重生、但建議小修的：

- 第 7 張：第 4 步改成「from R's page number, find where R's PTE is」；在流程裡加一個設 used mark 的步驟（或把第 6 張的「see sheet 7」改掉）；「hardware walk」換成第 6 張的用詞。
- 第 9 張：拿掉孤立的編號「1」；右欄說明要不要等所有 core 清完；交代「other hardware」與「the model」。
- 第 10 張：中間欄在 TLB entry 旁標出「wrong frame for NET」之類的警告；MEDIA 加一句介紹或人物。
- 全組：替紫色虛線框與黃色底各定一個意思並在每張一致使用。

# cpu-mmu-kernel-sw gen1 冷讀報告（第 11 到 14 張）

- 日期：2026-11-16
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：cpu-mmu-kernel-sw gen1 的第 11 到 14 張
- 每張先遮住底部 Key point 讀畫面，再讀 Key point 對照。

---

## 第 11 張：11-refill-against-clear.png

標題：「A TLB Miss Handler Without a Lock Can Undo a Clear」

### 1. 人物與機器

- **Core 1, hw thread A 那一列**：一個坐在筆電前的火柴人，標籤「NET」。列標題寫「NET's TLB miss handler」。看起來 NET 是一個 user SW 程式，這一列跑的是因為 NET 發生 TLB miss 而進來的 handler。它在意的是「把 P 的位置填進 TLB，好讓 NET 繼續讀」。
  - 不確定的地方：火柴人標的是 NET（user SW），可是步驟 1 和 5 是 kernel 的 handler 在做。讀者可能會以為「NET 自己去讀 PTE、自己寫 TLB」。火柴人代表的是「user SW」還是「在這個 thread 上跑的 handler」，圖上沒有分開。
  - NET 為什麼會進 handler（NET 存取 P、TLB miss）這個觸發點沒有畫，要自己推。
- **Core 1, hw thread B 那一列**：沒有人物，列標題「kernel takes frame F away」。在做趕出 page、拿走 frame 的流程（步驟 2、3、4）。是誰（哪個程式、哪個 kernel 角色）觸發拿走 frame，沒標。
- **Core 0 那一列**：沒有人物、沒有說是誰在跑，只有一個方塊「clears P from Core 0's TLB, answers」。看得出來是被要求清 TLB 然後回覆，但「誰要求它」沒有箭頭連過去。
- 沒有畫 TLB、PTE、frame 本身這些物件，全部用文字方塊敘述。

### 2. 看不懂的線或物件

- **步驟 5 到步驟 1 的虛線**：箭頭頭落在步驟 1 上方，方向看起來是「從 5 指回 1」。可是意思是「5 寫的是 1 讀到的東西」，資料是從 1 流到 5，箭頭方向反了，或至少讓人困惑。虛線上的文字「the handler read and wrote at two moments; the clear fell in between」說明得清楚，靠文字救回來。
- **兩個步驟 3**：thread B 和 Core 0 都標 3。可以讀成「同時」，但沒有任何線把 B 的請求連到 Core 0，讀者不知道 Core 0 為什麼會清。
- **步驟 4「every core answered: frame F is reused」**：這句可以讀成「每個 core 回答『frame F 被重用了』」，也可以讀成「每個 core 都回覆了，所以 frame F 拿去重用」。後者才合理，但字面有歧義。
- **步驟 5「writes what it read in step 1: P is in frame F」**：沒說寫到哪裡（應該是 Core 1 的 TLB）。對新手來說「寫」的目標不明。
- **「STALE ENTRY」標籤**貼在步驟 6 上方。stale entry 是在步驟 5 產生的，步驟 6 是它的後果。標籤位置讓人以為步驟 6 本身是 stale entry。
- 時間軸只有一條橘色箭頭，沒有刻度，但順序靠編號，可以讀。

### 3. 圖說的一句話（不看 Key point）

一個 hw thread 上的 TLB miss handler 先讀了 PTE，同一時間另一個 hw thread 把 frame 拿走並清掉所有 TLB，handler 之後才把舊的對應寫進 TLB，結果 NET 讀到 frame F 裡別的 page 的資料。

### 4. 對照 Key point

Key point：「A TLB miss handler that takes no lock can write an entry the kernel has just cleared. Either the clear must wait for handlers in progress, or the handler must not run in the middle of a clear.」

- 判定：**一致**。第一句就是畫面在演的事。
- 第二句的兩種解法（clear 等 handler、或 handler 不能在 clear 中間跑）畫面完全沒畫，是 Key point 才新增的資訊。不算矛盾，但讀者看畫面得不到「該怎麼辦」。
- 標題說「Without a Lock」，畫面上沒有任何 lock 的圖示，只靠標題與 Key point 說明「沒拿 lock」。

### 5. 困惑指數：2

故事靠編號與文字讀得懂；扣分在 NET 火柴人與 handler 的身份混在一起、虛線箭頭方向反、Core 0 的清除沒有連到發起者。

### 6. 可疑的錯字或多餘文字

- 步驟 4 的「answered: frame F is reused」冒號用法造成歧義，建議改成「every core answered; frame F goes to another page」之類。
- 副標題「Found in the model: …」幾乎是把六個步驟再講一次，和下方「Why the clear missed it」也重複，略多餘。
- 「the model」在副標題第一次出現，要到中間的「What the model is」才解釋，順序倒過來。
- 沒有明顯錯字。

---

## 第 12 張：12-what-held-in-the-model.png

標題：「What Held in the Model, and One Deadlock」

### 1. 人物與機器

- 沒有任何火柴人或 user SW。整張是表格加一個 deadlock 小圖。
- **表格**：每一列是一種「TLB miss handler 的做法 × clear request 送到哪裡」的組合，第三欄是結果（stale entry / held / a window remains / deadlock）。
- **The deadlock 小圖**：兩個紫色虛線框，標籤「Core 1: kernel」與「Core 0: kernel」。
  - Core 1: kernel：拿著 mm_lock，在等 Core 0 回覆 clear。框外下方有一個鎖頭圖示標「mm_lock」，放在 Core 1 下面，讀得出是 Core 1 拿著。
  - Core 0: kernel：關著 interrupt 等 mm_lock，所以看不到 clear request。
  - 兩邊都只標「kernel」，Core 0 的 kernel 在做什麼工作（為什麼要 mm_lock，是 TLB miss handler 還是 page fault handler）沒寫。
- 沒有出現上一張的 NET、hw thread A/B 的角色，和第 11 張的人物沒有接上。

### 2. 看不懂的線或物件

- **「held」這個字**：表格結果欄用粗體「held」表示「模型裡沒出錯」，表格下方有註解。但同一張圖裡 mm_lock 也用「holds」（holds mm_lock）。標題「What Held in the Model」第一眼會讀成「模型裡被握住的是什麼（lock）」，和 lock 的 hold 撞字。這是本張最大的誤讀風險。
- **第五列「the ways in rows one, two and four」**：第二欄應該是「clear requests go to」，這一列卻寫「a hw thread waits for mm_lock with interrupts off」，不是在講 clear request 送到哪，欄位意思斷掉。而且第一列本身就是「沒拿 lock」，為什麼還會「等 mm_lock」？讀者看不懂第一、二列的做法要怎麼跟「等 mm_lock」組合。
- **「cannot take a request in the middle」（第二列）**、「if the handler can take a request in the middle」（第三列）、「interrupt handlers can take them」（第四列）：「take a request」是「在 handler 執行中途接受別的 core 送來的 clear request」的意思，要讀到右下「New words」的 interrupts off 和 clear request 才猜得出來，詞本身沒定義。
- **第三列「a window remains: the other hw thread can use the entry first」**：「the other hw thread」指誰？要知道「同一個 core 的兩個 hw thread 共用一個 TLB」才讀得懂。本張沒提醒這件事。
- **deadlock 小圖的箭頭**：上面「clear request」從 Core 1 指向 Core 0，下面「wants mm_lock」從 Core 0 指向 Core 1。方向清楚，是本張最好讀的部分。
- **Rules this suggests 方塊**：三行規則，右上角「OPEN / which one: not decided」。看不出三行是「三選一」還是「第一行一定要、第二三行二選一」。第一行在講避免 deadlock，第二三行在講避免 stale entry，性質不同，卻被說成「which one」。

### 3. 圖說的一句話（不看 Key point）

模型試了幾種 TLB miss handler 與 clear request 的組合，有兩種沒出錯，而「關著 interrupt 等 mm_lock」會造成兩個 core 互等的 deadlock。

### 4. 對照 Key point

Key point：「Two ways held in the model: clear requests to every hw thread with a handler that cannot be interrupted midway, or a handler that holds mm_lock. Waiting for mm_lock with interrupts off deadlocked in every way it was tried.」

- 判定：**一致**。兩個 held 列與 deadlock 列都對得上。
- Key point 用「cannot be interrupted midway」，表格用「cannot take a request in the middle」。Key point 的說法反而比表格好懂，表格應該跟著改。
- Key point 也用「held」，同樣有和 lock 的 hold 撞字的問題。

### 5. 困惑指數：3

deadlock 小圖清楚，但表格是本張主體，欄位意思在第五列斷掉、「take a request in the middle」沒定義、「held」與 holds mm_lock 撞字，規則方塊的「選哪一個」關係不清。

### 6. 可疑的錯字或多餘文字

- Rules 第一行「wait  for」中間多一個空格。
- 「the ways in rows one, two and four」用列號指稱，讀者要回頭數列，建議改成具名。
- 「held」建議換成「no failure found」或「passed」之類，避開 lock 的 hold。
- 副標題「over many random and searched orders of steps」的「searched」對新手意思不明（是 exhaustive search？）。

---

## 第 13 張：13-where-it-goes-wrong.png

標題：「Where It Goes Wrong If You Are Careless」

### 1. 人物與機器

- 沒有人物、沒有機器。六張卡片，每張有圖示、標題、Risk、Rule、Where（藍字）。角色不是本張的重點，不構成問題。
- 卡片與圖示：
  1. 「A TLB entry left behind」：2×2 方格，右下一格打叉。打叉可以讀成「這格是壞的（留下來的舊 entry）」，也可以讀成「這格被清掉了」，兩種讀法意思相反。
  2. 「An old entry written late」：時鐘加箭頭，「晚」的意思清楚。
  3. 「Waiting for the lock with interrupts off」：兩個圓圈加兩個彎箭頭互繞，可以讀成互等，還算清楚。
  4. 「A miss inside the TLB miss handler」：一個繞回自己的圓箭頭，讀成「遞迴」，清楚。
  5. 「Another program's entry」：兩張文件中間一個等號。等號想表達「看起來一樣」，但讀者也可能讀成「兩個程式共用同一份」，意思不夠明確。
  6. 「Two entries for one page」：兩個箭頭指向同一個方塊，清楚。

### 2. 看不懂的線或物件

- **藍字「Where:」的意思不統一**：有的是「在第幾張講過」（sheet 9、sheets 11 and 12），有的是「在哪裡找到」（found in the model、caught by a test in the model），有的是「要去哪裡查」（the CPU manual），第四張還寫成「Where: how: the CPU manual.」，兩個冒號，看不出在說什麼。
- **卡片 3 的 Risk 與 Rule 講的是兩個不同的 core**：Risk 寫「拿著 mm_lock 的 kernel 等一個永遠不來的回覆」（拿 lock 的那一邊），Rule 寫「永遠不要關著 interrupt 等 mm_lock」（等 lock 的那一邊）。沒看第 12 張的 deadlock 小圖的人，會不懂為什麼 Risk 和 Rule 對不上。
- **卡片 2 的 Rule「pick one of the two ways that held in the model」**：不自足，一定要回去看第 12 張，而且「held」又出現一次。
- **卡片 6 的 Rule「find out what the CPU does with two matching entries before relying on it」**：「it」指什麼不清楚（依賴 CPU 的行為？依賴兩個 hw thread 都能寫？）。

### 3. 圖說的一句話（不看 Key point）

kernel 自己在多 core 上填 TLB 時有六個陷阱，每個陷阱列出風險、該守的規則，以及在哪一張講過或還要查 CPU 手冊。

### 4. 對照 Key point

Key point：「Without hardware that refills the TLB, every TLB entry is written by the kernel, so every stale or duplicate entry is the kernel's to prevent. The order of steps and who may take a request are the rules.」

- 判定：**部分一致**。
  - 第一句只涵蓋 stale 和 duplicate entry（卡片 1、2、5、6），但卡片 3（deadlock）和卡片 4（handler 裡又 miss）不是 stale 或 duplicate entry 的問題，Key point 沒有涵蓋。
  - 第二句說規則就是「步驟順序」和「誰可以接受 request」，但卡片 4 的規則（把 handler 的 code、stack、page table 放在不經 TLB 也能碰到的地方）、卡片 5 的規則（切換時清 TLB 或加 address space tag）、卡片 6 的規則（先查 CPU 手冊）都不屬於這兩類。
  - 「who may take a request」又是第 12 張那個沒定義的說法。

### 5. 困惑指數：2

卡片格式整齊，每張自成一格好讀；扣分在「Where」意思不統一、少數圖示與 Rule 要靠前一張才懂，以及 Key point 收得太窄。

### 6. 可疑的錯字或多餘文字

- 「Where: how: the CPU manual.」雙冒號，像是寫壞了。
- 句尾句點不一致：卡片 3、4、5 的 Rule 有句點，卡片 1、2 沒有；Where 行也是有的有句點有的沒有。
- 副標題「Most of them do not crash at once; they quietly read the wrong frame」：六個裡有兩個（deadlock、handler 裡又 miss）不是讀錯 frame，用「Most」勉強成立，但讀者可能會把 deadlock 也想成讀錯 frame。

---

## 第 14 張：14-modeled-and-open.png

標題：「What Is in the Model, What Is Open」

### 1. 人物與機器

- 沒有人物、沒有機器。左邊「In the model so far」是打勾清單，右邊「Open」是三欄表格（question / why it matters / needs）。
- 左下藍字「a model on a host computer: not yet run on this processor」把「打勾」的意思限定為「模型裡驗過」，不是「晶片上做好了」，這句很重要而且有放。

### 2. 看不懂的線或物件

- **打勾清單第 2、3 項**（page fault handler 在 mm_lock 下再查一次 PTE；第一次碰到的 page 拿到全是 0 的 frame）在第 11 到 13 張都沒出現。可能在前 10 張有，單看這四張會覺得突然冒出來。
- **打勾清單第 4 項「two ways … that held against the example clear」**：「held」又一次；「the example clear」是第 12 張副標題的說法，單看這張不知道「example clear」是什麼。
- **打勾清單少了「不要關著 interrupt 等 mm_lock」**：第 12 張說這是模型裡找到的 deadlock，第 13 張也列為規則，但第 14 張的「In the model so far」沒有它。讀者會懷疑這條是不是不算數。
- **Open 表最後一列「every program pays it, compression or not」**：第 11 到 14 張第一次出現 compression 這個字，沒有前文，新手會愣一下（這組圖不是在講 CPU MMU 嗎？）。
- **needs 欄**：5 列「the CPU manual」、2 列「a design decision」、1 列「a product decision」、1 列「measurement on the chip」。副標題說「the rest are design and product decisions」，漏了 measurement on the chip。

### 3. 圖說的一句話（不看 Key point）

到目前為止模型驗過了四件事，還有九個問題沒答案，其中大部分要等 CPU 手冊，其餘是 kernel team 的設計決定、產品決定或要在晶片上量。

### 4. 對照 Key point

Key point：「The rules for the order of steps are checked in the model. What is open is mostly what this CPU provides; until the manual answers, the handlers cannot be written.」

- 判定：**一致**。左欄對第一句，右欄 needs 欄多數是 CPU manual 對第二句。

### 5. 困惑指數：1

左右兩欄分工明確，表格欄位清楚，有圖例說明 design decision 與 product decision。小問題只有幾個字眼與遺漏。

### 6. 可疑的錯字或多餘文字

- Key point 最後半句「until the manual answers, the handlers cannot be written」字體被擠得很窄，像是塞不下硬壓的，閱讀上吃力。
- 副標題漏了「measurement on the chip」這一類。
- 沒有明顯錯字。

---

## 跨圖觀察

### 命名物件有沒有走樣

- 這四張裡反覆出現的具名物件很少：
  - **NET 火柴人**只出現在第 11 張。
  - **mm_lock 鎖頭圖示**只出現在第 12 張。第 11 張標題講「Without a Lock」，畫面卻沒有鎖頭（例如畫一個「沒拿」的鎖），兩張對 lock 的表現方式不一致。
  - **Core 0、Core 1**：第 11 張是「Core 1, hw thread A / B」與「Core 0」的泳道；第 12 張變成「Core 1: kernel」「Core 0: kernel」的虛線框。兩張都是 Core 1 發起 clear、Core 0 被要求清，角色方向一致，沒有走樣。但第 12 張沒有 hw thread A/B，讀者不知道第 12 張的 Core 1 是第 11 張的 thread A 還是 thread B。
  - 「TLB」「PTE」「frame」在四張都只以文字出現，沒有畫成物件，所以沒有長相走樣的問題，但也代表無法和前 10 張的圖形物件呼應（我沒看前 10 張，無法判斷前面是否有畫）。
- 文字用語的走樣比圖形嚴重：同一個概念有三種說法——「take a request in the middle」（12 表格）、「be interrupted midway」（12 Key point）、「who may take a request」（13 Key point）。「clear」「clear request」「answers」也是在 11 用了、12 才定義。

### 分類顏色是否一致

- 四張都一樣：標題黑字加橘色底線、副標題與註解用藍字、方框黑線。這部分一致。
- 但沒有任何「分類顏色」：user SW、kernel、hardware 沒有用顏色區分。第 11 張 NET（user SW）那一列和 kernel 那一列同色，加深了「NET 和 handler 是誰」的混淆。
- 第 12 張 deadlock 小圖突然用紫色（虛線框與箭頭），四張裡只出現這一次，沒有說明紫色代表什麼。讀者會以為紫色有分類意義。
- 強調的方式不一：第 11 張用粗框（步驟 6）表示壞結果，第 12 張用粗體字（held）表示好結果。

### 故事線順不順

- 主線是順的：11「沒拿 lock 的 handler 會把 clear 掉的 entry 寫回去」→ 12「模型試了幾種做法，兩種沒出錯，另外發現一個 deadlock」→ 13「把這些和其他陷阱整理成六條規則」→ 14「哪些已在模型驗過、哪些還要等 CPU 手冊或決定」。
- 斷掉的地方：
  1. **11 的兩個解法和 12 的兩個 held 做法對不起來**。11 的 Key point 說「clear 要等進行中的 handler，或 handler 不能在 clear 中間跑」；12 的 held 是「handler 不能被中途打斷 + clear 送到每個 hw thread」與「handler 拿 mm_lock」。讀者要自己推：「不能被中途打斷」其實是「clear 等 handler 做完」，「拿 mm_lock」其實是「handler 不會在 clear 中間跑」。兩張說法交叉對應，沒有任何視覺連結，很容易對錯。
  2. **「clear 送到每個 core 還是每個 hw thread」這個軸在 12 突然出現**。11 的畫面是「清 Core 1 的 TLB、清 Core 0 的 TLB」，以 core 為單位；12 才說要送到每個 hw thread，可是沒說為什麼 hw thread 會有差（同一個 core 的 thread 共用 TLB，送給 core 時只有一個 thread 收到，另一個 thread 的 handler 不受影響）。這是 11 到 12 最大的缺口。
  3. **interrupt 在 11 完全沒出現**，12 卻以「interrupts off」為 deadlock 的主因。11 的 Core 0「clears…, answers」若能畫成「收到 interrupt 才清」，12 就接得上。
  4. 14 的打勾清單漏了 deadlock 的規則，與 12、13 不一致。

### 我用自己的話說的結論

這個晶片沒有硬體幫忙填 TLB，所以每一筆 TLB entry 都是 kernel 寫的。多 core、多 hw thread 同時跑時，kernel 要拿走一個 frame 會先清掉所有 TLB，但如果某個 TLB miss handler 在這之前已經讀了舊的 PTE、在清完之後才寫進 TLB，舊的對應就被寫回去，程式會安靜地讀到別人的資料。模型（在 host 電腦上跑的 kernel 模型，不是在這顆 CPU 上）試出兩種沒出錯的做法：handler 執行中不接受 clear request、且 clear request 要送到每個 hw thread；或 handler 拿 mm_lock。但若有人關著 interrupt 等 mm_lock，拿 lock 的那一邊又在等它回覆 clear，就會 deadlock，所以不能關著 interrupt 等 mm_lock。另外還有 handler 自己 miss、切換程式後的舊 entry、同一 core 兩個 thread 寫出兩筆 entry 等陷阱。順序的規則已在模型裡驗過，但 CPU 型號、TLB 大小、跨 core 清 TLB 的機制、兩個 thread 同時寫 TLB 的行為等都還要查 CPU 手冊，在那之前 handler 寫不出來；要不要讓 TLB miss handler 拿 mm_lock 還沒決定。

### 總表

| 張 | 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|---|
| 11 refill-against-clear | 2 | 否（NET 火柴人與 kernel handler 身份混在一起；Core 0 沒有發起者連線） | 一致（解法只在 Key point，畫面沒畫） |
| 12 what-held-in-the-model | 3 | 否（Core 0: kernel 在做什麼工作沒說；與 11 的 thread A/B 對不上） | 一致 |
| 13 where-it-goes-wrong | 2 | 是（無人物，卡片自足） | 部分一致（Key point 只涵蓋 stale/duplicate 與順序，漏了 deadlock、handler 內 miss、程式切換、查手冊） |
| 14 modeled-and-open | 1 | 是（無人物） | 一致 |

### 建議重生

1. **第 12 張（必要）**：困惑指數 3、角色不清。
   - 表格第五列改成獨立的一行或移到 deadlock 區，不要塞進「clear requests go to」欄。
   - 「take a request in the middle」統一換成「can be interrupted midway」。
   - 「held」換成不會和 lock 的 hold 撞字的詞（例如「no failure found」）。
   - 補一句「同一個 core 的兩個 hw thread 共用一個 TLB，所以 clear 要送到每個 hw thread」。
   - 說明 Core 0 的 kernel 在做什麼（例如它是 TLB miss handler 或 page fault handler，正要拿 mm_lock）。
   - Rules 方塊分清楚「一定要守的」（不關 interrupt 等 mm_lock）與「二選一的」（兩種 handler 做法）。
   - 紫色若無分類意義就拿掉。
2. **第 11 張（建議小修後重生）**：角色不清。
   - 把 NET（user SW）與在 thread A 上跑的 kernel TLB miss handler 分開畫，或在火柴人旁註明「handler runs on NET's hw thread」；補上「NET touches P → TLB miss」的起點。
   - 虛線箭頭改為從 1 指向 5。
   - 從 thread B 畫一條「clear request」箭頭到 Core 0 的步驟 3，並標出是 interrupt，好接到第 12 張。
   - STALE ENTRY 標籤移到步驟 5。
   - 步驟 4 文字消除歧義。
3. **第 13 張（可只改 Key point 與小字，不一定要整張重生）**：畫面與結論部分一致。
   - Key point 改寫成涵蓋六個陷阱，例如「every TLB entry and every wait is the kernel's to get right; some rules are checked in the model, the rest need the CPU manual」。
   - 修掉「Where: how:」雙冒號，統一 Where 行的意思與句點。

第 14 張不需重生；可順手補上 deadlock 規則到打勾清單、修副標題漏掉的 measurement、放寬 Key point 的字距。

# 冷讀驗收報告：kernel-sw-design gen1 第 5 到 8 張

- 日期：2026-11-15
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：kernel-sw-design 的第 5 到 8 張（`gen1/05-parts-of-the-kernel-sw.png`、`06-page-states.png`、`07-fault-path.png`、`08-reclaimer.png`）
- 讀者設定：知道前 4 張講過 page、frame、page table、TLB、TLB miss 進 kernel、page swap、512 B chunk、COT，其他都不知道

---

## 第 5 張：The Parts of the LZ4 Kernel SW

### 1. 人物與機器

- **UI**（戴帽子、拿筆電的人）：一個 user SW 程式。橘色箭頭寫「touches a compressed page」，它碰到一個壓縮過的 page，掉進 fault path。它在意的是拿到資料。
- **MEDIA**（戴耳機的人）：另一個 user SW 程式。旁邊藍字「most accesses never reach the kernel: the TLB hits」。我讀成 MEDIA 代表「大多數時候的正常情況」，沒有箭頭連出去。但這句藍字只放在 MEDIA 底下，看起來像是 MEDIA 專屬的說明，不像兩個人都適用的通則。
- **fault path**（紫色虛線框）：把壓縮的 page 拿回來；在 fault 的那個 core 上跑；由 TLB miss handler 呼叫；很多 core 可以同時在裡面。
- **kernel tables**（實線框，上方有鎖）：`mm_lock` 一把鎖保護四張表：page state、COT、free frames、chunk bitmap。在意的是一致性。
- **reclaimer**（紫色虛線框）：背景的 kernel thread，free frames 低的時候被叫醒，把冷的 page 推出去，所有壓縮都它做。
- **LZ4 HW**（綠色框、齒輪）：幾個 engine，所有 core 共用，做 COMPRESS 與 DECOMPRESS。
- 圖上沒有畫 core、CPU MMU、TLB。「runs on the core that faulted」的 core 在圖上看不到。

### 2. 看不懂的線或物件

- 上方紫色弧線「wake up: free frames are low」從 fault path 出發指向 reclaimer。我讀成「fault path 負責叫醒 reclaimer」，但不確定是 fault path 主動叫，還是 free frames 這張表到某個水位自動觸發。
- 「lock, look up, unlock」與「lock, pick a page, unlock」都只有單向箭頭指向表。其實會改表（拿 frame、改 state），單向箭頭看起來像只讀。
- DECOMPRESS 與 COMPRESS 只有送進 LZ4 HW 的箭頭，沒有回來的箭頭。HW 做完怎麼告訴 kernel，這張圖沒說。
- UI 到 fault path 的橘色箭頭直接跳過 CPU MMU 與 TLB miss，第 1 到 4 張剛學的那一段在這裡看不見。框裡有寫「called from the TLB miss handler」，所以讀得通，但箭頭本身是捷徑。
- 虛線框（fault path、reclaimer）與實線框（tables、LZ4 HW）的差別沒有說明。我猜虛線 = kernel SW 程式碼，實線 = 資料或硬體。

### 3. 新手卡住的地方

- **chunk bitmap**：前 4 張只提過 chunk 與 COT，沒有提過 bitmap。
- **page state**：是什麼 state？要等第 6 張才知道。
- **cold page**：沒定義（猜是很久沒用的 page）。
- **kernel thread、background**：對沒有 OS 背景的人不直觀。
- **fault path** 這個詞本身：是一段程式、一個 thread，還是一個 service？
- **free frames 是一張表**：讀者會以為 free frames 是 DRAM 裡的空位，不是 kernel 的表。

### 4. 圖說的一句話

kernel SW 有兩條路：fault 的 core 自己把壓縮 page 拿回來，背景的 reclaimer 把冷 page 壓出去；兩者共用一把鎖下的四張表，重的工作丟給共用的 LZ4 HW。

### 5. 讀 Key point 後：畫面和結論一致嗎？

**一致**。Key point 說的四件事（拿回來在 fault 的 core、推出去在一個背景 thread、共用一把鎖下的表、LZ4 HW 工作時不握鎖）畫面上都有。

### 6. 困惑指數：2

角色都有標籤，結構清楚；扣分在 chunk bitmap、單向箭頭與沒有回程箭頭。

### 7. 可疑的錯字或多餘文字

- 標題「The Parts of the LZ4 Kernel SW」：kernel SW 不是 LZ4 的，LZ4 只是 HW。讀起來像「LZ4 有一套 kernel SW」，容易誤會。
- Key point 裡「Bringing pages  back」有兩個空格。
- MEDIA 下面那句藍字的位置讓它像是 MEDIA 專屬說明。

---

## 第 6 張：The Six States of a Page

### 1. 人物與機器

- 沒有人物。六個 state 方框：UNTOUCHED、PRESENT、COMPRESSING、COMPRESSED（斜線，代表壓縮資料）、DECOMPRESSING、LOST。
- 箭頭上的字點出誰觸發：reclaimer（往 COMPRESSING 或直接 COMPRESSED）、page fault（COMPRESSED → DECOMPRESSING）、LZ4 HW（COMPRESSING、DECOMPRESSING 方框裡）。
- 下方兩個說明框：Read-only pages、While a job runs。
- 「kernel's decoder」是一個沒介紹過的角色，只出現在通往 LOST 的箭頭上。

### 2. 看不懂的線或物件

- **COMPRESSING → PRESENT「did not fit, or the HW failed」**：did not fit 是放不進什麼？一個 page 的 chunk 上限？還是壓完比原本還大？
- **DECOMPRESSING → LOST「both the HW and the kernel's decoder fail」**：暗示 HW 失敗時有 SW decoder 備援，但「HW 失敗、SW decoder 成功」那條路沒畫（應該也回 PRESENT）。LOST 之後程式會怎樣，也沒說。
- **read-only page 從哪裡開始**：說明框說 read-only 的壓縮版開機前就做好了，那 read-only page 一開始是 COMPRESSED 嗎？UNTOUCHED 寫的是「read-write page nobody has written yet」，所以 read-only 的起點沒有畫。
- **DECOMPRESSING → PRESENT「back in a frame」**：另一側寫了「stored: the frame is freed」，這一側沒寫 chunk 有沒有釋放。對 read-write 與 read-only 是不同的，圖上沒分。
- **PRESENT 方框**：read-only page 在 PRESENT 時同時有 frame 與壓縮版，但 PRESENT 寫的是「in a frame」，看不出它還有壓縮版。

### 3. 新手卡住的地方

- **job**：「whether a job is working on it」，job 是 LZ4 HW 的一個工作，前面沒正式介紹這個字。
- **kernel's decoder**：SW 版的 LZ4 decoder，沒介紹過。
- **chunk pool**：前面講的是 chunk，pool 是新詞，猜得到。
- **為什麼 read-only page 開機前就有壓縮版**：這是產品流程（image 事先壓好）的知識，圖沒解釋。
- **first touch: a frame of zeros**：為什麼沒寫過的 page 給全 0？需要知道 OS 的 zero page 慣例。
- **another thread that touches it waits**：怎麼等？等在哪裡？

### 4. 圖說的一句話

每個 page 在六種狀態中流轉：平常在 frame 裡（PRESENT），被 reclaimer 壓進 chunk pool（read-write 經過 COMPRESSING，read-only 直接丟 frame），被碰到時經過 DECOMPRESSING 回到 frame，HW 與 SW 都解不開就是 LOST。

### 5. 讀 Key point 後：畫面和結論一致嗎？

**部分一致**。

- 「Every page is in exactly one of six states」：一致。
- 「Read-only pages always keep their compressed copy」：與下方說明框一致，但 state 圖本身沒有表現出來（PRESENT 方框沒提，DECOMPRESSING → PRESENT 也沒分 read-only 與 read-write）。
- 「a read-write page has exactly one copy, in a frame or in the chunk pool」：畫面沒有支撐。COMPRESSING 與 DECOMPRESSING 期間兩邊都有資料；UNTOUCHED 一份都沒有；DECOMPRESSING → PRESENT 那條箭頭沒寫 chunk 被釋放。讀者得自己推出「chunk 在回到 PRESENT 時會被放掉」。

### 6. 困惑指數：3

主幹清楚，但 read-only 的起點、chunk 什麼時候釋放、kernel's decoder、did not fit 都要猜，而 Key point 的「exactly one copy」靠的正是沒畫的部分。

### 7. 可疑的錯字或多餘文字

- COMPRESSING 寫「the LZ4 HW is storing it」：storing 不像 compressing，讀起來像在搬資料。
- Key point 的字比其他張小很多，標籤框有淺藍底，其他張沒有，風格不一致。

---

## 第 7 張：Bringing a Page Back: the Fault Path

### 1. 人物與機器

- **LOG**（戴帽子的人）：user SW，載入 page Q（壓縮過）。第 5 張的人物是 UI 與 MEDIA，這裡換成第三個人 LOG，長相和 UI 幾乎一樣（帽子＋筆電），容易以為是同一個人改名。
- 三條泳道：user SW、Kernel SW on LOG's core、LZ4 HW。
- 九個編號步驟，kernel SW 步驟是實線黑框，3 與 7 有鎖，LZ4 HW 的 4 是綠框加齒輪。
- 兩個黃色便利貼：Why it stays short、For more detail。

### 2. 看不懂的線或物件

- **4 → 6 的箭頭跳過 5**：5 是「wait for the completion」，但 HW 做完的箭頭指向 6，不是叫醒 5。看起來像 HW 直接觸發 6，5 是一個沒有出口的方塊（5 → 6 的箭頭其實有，但兩個箭頭同時進 6，意思是「兩者都到了才做 6」，新手不一定讀得出來）。
- **1 → 2**：中間的 CPU MMU、TLB 查不到、進 exception 都省略了。「exception」這個字要到第 8 步才出現。
- **2 的判斷**：TLB miss handler 發現 PTE 不是 valid 才進 fault path。PTE 是 valid 的普通 TLB miss（只要填 TLB）怎麼走，這張沒畫；第 5 張說大多數 TLB hit，但 TLB miss 而 PTE valid 的情況兩張都沒交代。
- **6「drop the frame's old lines from every core's cache」**：為什麼要清？清什麼的舊資料？一個 core 怎麼清其他 core 的 cache？沒解釋。
- **3 → 4 的箭頭**：怎麼把 job 交給 HW（ring、register）沒畫，對冷讀者來說可以接受。

### 3. 新手卡住的地方

- **PTE**：page table entry，前 4 張可能講過，但縮寫在這張沒展開。
- **completion**：HW 回報做完的那個東西。
- **sleep, or poll**：兩種等法的差別。
- **cache lines、為什麼 HW 寫完要讓 cache 失效**：需要知道 LZ4 HW 直接寫 DRAM、不經過 CPU cache。
- **reserve**：「the frame comes from a reserve」，但步驟 3 寫的是「from the free frames」。reserve 要到第 8 張才解釋。
- **Q 正在 COMPRESSING 或 DECOMPRESSING 時被碰到**：第 6 張說會等，這張沒畫。
- **reserve 用完了怎麼辦**：「no compressing here」暗示永遠拿得到，但沒說拿不到時怎麼辦。

### 4. 圖說的一句話

LOG 碰到壓縮過的 page Q，LOG 自己的 core 進 kernel，握鎖一下拿 frame 並標 DECOMPRESSING，放鎖讓 LZ4 HW 解壓，等完成、清 cache，再握鎖一下釋放 chunk、標 PRESENT、設 PTE，填 TLB 後 LOG 的指令重跑。

### 5. 讀 Key point 後：畫面和結論一致嗎？

**一致**（有一個用詞落差）。拿 frame、一個 DECOMPRESS job、鎖只在兩個短步驟、指令重跑，畫面都有。落差是 Key point 說「reserved frame」，步驟 3 說「from the free frames」，便利貼說「from a reserve」，三個說法指同一件事，讀者要自己對上。

### 6. 困惑指數：2

泳道與編號讓順序很清楚；扣分在 4 → 6 跳過 5、第 6 步沒解釋、reserve 先用後解釋。

### 7. 可疑的錯字或多餘文字

- 「For more detail: figures/kernel-actions」：檔案路徑放在給新手的圖上，看圖的人無法使用，算多餘。
- 「a read-only page keeps its chunks in step seven」與步驟 7 方框寫的「free Q's chunks」互相矛盾，要讀到便利貼才知道是例外。放在「For more detail」底下也不對題，它不是延伸閱讀而是規則。
- 便利貼用「steps three and seven」文字，圖上是數字圈，小事。

---

## 第 8 張：Pushing a Cold Page Out: the Reclaimer

### 1. 人物與機器

- 沒有人物，也沒有代表 reclaimer 的角色或框（第 5 張的 reclaimer 框沒有出現）。reclaimer 只出現在副標題與文字裡。
- 三個面板：When it wakes（frame 堆疊與兩條水位線）、Which page: the clock（八個方框圍一圈，一根指針）、Push it out（read-only 與 read-write 兩欄步驟）。
- read-write 欄的 COMPRESS 是綠框加齒輪，代表 LZ4 HW。
- 「OPEN」是一個膠囊形的標籤，看不出是誰或什麼。

### 2. 看不懂的線或物件

- **frame 堆疊**：上方是虛線方框，下方三個實線方框。我猜實線 = 目前還有的 free frame，虛線 = 需要補的空位；低於 low watermark 所以叫醒，補到 high watermark。但「faults take frames from the top」：top 指的是實線堆的頂端還是整根柱子的頂端（虛線）？讀起來不確定。也可能反過來，實線是用掉的。
- **時鐘**：方框是 frame（或 page）？指針沒有轉動方向，方框上沒有「used」標記，所以面板下方的規則（clear the mark、skip）在圖上沒有對應的畫面。
- **OPEN**：是「這件事尚未決定（open issue）」的印章？還是時鐘的某個狀態？和下方藍字「who records used is not designed yet」放在一起，猜是 open issue，但只有一個字，沒把握。
- **read-only 欄**：三個框沒有箭頭連接，read-write 欄有箭頭。順序看起來一樣是由上而下，但風格不同。read-only 欄沒有鎖，read-write 欄有兩次鎖。read-only 改 PTE 不用鎖嗎？
- **read-write 第一框「reserve 7 free chunks」**：為什麼是 7？page 4 KB、chunk 512 B 是 8 個；7 是「壓完要省下至少一個 chunk 才划算」嗎？沒說。
- **read-write 沒有提到 page state**：第 6 張有 COMPRESSING、COMPRESSED，這裡沒寫什麼時候標 COMPRESSING、什麼時候標 COMPRESSED，也沒畫「did not fit, or the HW failed」回 PRESENT 的那條路。
- **「write the frame's cached lines back to DRAM」**：和第 7 張第 6 步是鏡像，原因同樣沒解釋。

### 3. 新手卡住的地方

- **watermark**（high、low）：沒解釋這個比喻。
- **clock 演算法**：「the clock」對沒學過 OS 的人是陌生名詞，畫面又是靜態的。
- **mark / used**：「used since the last pass? clear the mark」，mark 是誰、在什麼時候設的？藍字說還沒設計，新手會更不確定這個規則能不能動。
- **pinned**：沒定義。
- **為什麼是 7 個 chunk**。
- **clear every core's TLB**：怎麼清別的 core 的 TLB？為什麼要清每個 core 的？
- **cold page**：標題用了，仍沒定義。

### 4. 圖說的一句話

背景的 reclaimer 在 free frame 掉到低水位時醒來，用時鐘找最近沒用的 page，read-only 的直接把 frame 丟掉，read-write 的握鎖準備、交 LZ4 HW 壓縮、再握鎖記 COT 並釋放 frame，補到高水位就停。

### 5. 讀 Key point 後：畫面和結論一致嗎？

**一致**。「reclaimer 而不是 fault 做所有壓縮」與第 7 張的「no compressing here」對得起來；「挑最近沒用的」「不挑剛 fault 進來的」都在時鐘面板的規則裡。

### 6. 困惑指數：3

三個面板各自可讀，但水位堆疊的實線與虛線方向、OPEN、7 個 chunk、read-only 沒有鎖、和第 6 張的 state 沒有接起來，都要猜。

### 7. 可疑的錯字或多餘文字

- 「OPEN」：意思不明，像漏了一句話的標籤。
- Key point 的文字是藍色，其他三張是黑色。
- read-only 第一框「set its PTE not valid」與第二框「clear it from every core's TLB」拆兩框，read-write 合成一框，同一件事兩種畫法。

---

## 另一題：把壓縮過的 page 拿回來的 kernel SW 在哪裡跑？同時有幾份？

**在哪裡跑**：在碰到 page 的那個程式所在的 core 上跑，由那個 core 的 TLB miss handler 呼叫。第 5 張 fault path 框寫「runs on the core that faulted」「called from the TLB miss handler」；第 7 張副標題寫「Everything below runs on LOG's own core」，泳道標籤寫「Kernel SW, on LOG's core」。

**同時有幾份**：可以有很多份，每個正在 fault 的 core 一份。第 5 張寫「many cores can be in it at once」，第 7 張寫「other cores can do the same at the same time」與「while the LZ4 HW works, other cores can take the lock」。上限看起來是 core 的數量（或 hardware thread 的數量），圖沒有明說是哪一個。

**有沒有畫法讓我以為它是「只有一份、大家排隊去找它」**：有，主要在第 5 張。

- fault path 畫成單一個紫色虛線框，和 reclaimer 的框用完全相同的樣式、大小、對稱地放在左右兩邊。reclaimer 真的是一個 thread，所以並排的畫法讓人自然以為 fault path 也是「一個東西」。
- 「fault path」這個名字是名詞，聽起來像一個元件或 service；UI 的橘色箭頭「走進」這個框，像使用者去找一個櫃台。
- 從 fault path 出發的「wake up」弧線讓它看起來像一個會主動發訊號的常駐角色。
- 對比：LZ4 HW 框明確寫了「shared by every core」，fault path 框沒有畫成多層疊起來或多個副本。

能糾正這個印象的只有框裡最後一行小字「many cores can be in it at once」。第 7 張用泳道與副標題講得很清楚，所以連著看能修正，但只看第 5 張的人很可能誤會。

---

## 跨圖觀察

### 反覆出現的物件與顏色

- **LZ4 HW**：第 5、7、8 張都是淺綠底加齒輪，一致。
- **mm_lock**：都用掛鎖圖示，一致。
- **紫色**：第 5 張紫色虛線框 = kernel SW 的兩個部分，紫色字 = 箭頭說明；第 6 張紫色 = state 之間的轉換箭頭；第 7 張 kernel SW 步驟是黑色實線框，不是紫色；第 8 張 kernel SW 步驟又是紫色虛線框。kernel SW 的步驟在第 7 張與第 8 張長得不一樣，是同一組圖裡最明顯的不一致。
- **藍字**：大多是旁註（第 5、8 張），一致；但第 8 張的 Key point 也變藍色。
- **斜線**：第 6 張 COMPRESSED 有斜線，符合「斜線代表壓縮資料」；第 7、8 張沒有畫出 chunk 或資料方塊，所以沒機會用到，不算衝突。
- **人物**：第 5 張是 UI 與 MEDIA，第 7 張是 LOG。LOG 和 UI 長得幾乎一樣，名字不同。讀者會想知道 LOG 是不是新程式、為什麼不用 UI。
- **Key point 框**：第 6 張的標籤有淺藍底、字特別小；其他張是白底。
- **free frames 的叫法**：第 5 張「free frames」（一張表），第 7 張「free frames」與「a reserve」並用，第 8 張「a reserve of free frames」。第 8 張才說清楚，但第 7 張已經先用了。

### 故事線順不順

順序本身合理：第 5 張總覽兩條路與共用的表，第 6 張講 page 的狀態，第 7 張走一遍拿回來的路，第 8 張走一遍推出去的路。斷掉的地方：

1. **第 6 張的狀態和第 7、8 張沒有完全接上**。第 7 張有標 DECOMPRESSING 與 PRESENT，接得上；第 8 張完全沒提 COMPRESSING、COMPRESSED，也沒畫失敗回 PRESENT 的路。
2. **第 6 張的失敗路線（did not fit、HW failed、kernel's decoder、LOST）只在第 6 張出現一次**，第 7、8 張都沒有對應的步驟。
3. **「另一個 thread 碰到正在處理的 page 會等」** 只在第 6 張的說明框，第 7 張沒畫。
4. **chunk bitmap** 只在第 5 張出現，之後沒用到；第 8 張的「reserve 7 free chunks」應該就是在用它，但沒點名。
5. **cache 的維護**（第 7 張第 6 步、第 8 張 write back）兩張都出現，兩張都沒解釋原因。
6. **TLB miss 但 PTE valid** 的普通情況，第 5 張說「TLB hits」，第 7 張從「PTE not valid」開始，中間那種情況沒有任何一張交代。

### 我用自己的話說這 4 張的結論

kernel SW 分成兩條路，共用一把 `mm_lock` 保護的四張表。程式碰到壓縮過的 page 時，就在那個程式自己的 core 上處理：短暫握鎖從預先保留的 free frame 拿一個、標成 DECOMPRESSING，放鎖讓 LZ4 HW 解壓，做完再短暫握鎖釋放 chunk、標成 PRESENT、設好 PTE，程式的指令重跑；很多 core 可以同時這樣做。壓縮則全部交給一個背景的 reclaimer：free frame 低於低水位時醒來，用時鐘挑最近沒用的 page，read-only 的直接丟掉 frame（壓縮版開機前就有），read-write 的交給 LZ4 HW 壓縮後寫 COT、釋放 frame，補到高水位為止。每個 page 任何時候都在六種狀態之一，正在被 job 處理的 page 不會再被開第二個 job。

---

## 總表

| 張 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|
| 5 Parts of the kernel SW | 2 | 是 | 一致 |
| 6 Six states of a page | 3 | 是（kernel's decoder 除外） | 部分一致 |
| 7 Fault path | 2 | 是 | 一致（free frames 與 reserve 用詞落差） |
| 8 Reclaimer | 3 | 否（reclaimer 沒有畫出來，OPEN 不明） | 一致 |

## 建議重生

- **第 6 張**：困惑指數 3，且畫面與 Key point 部分不一致。Key point 的「read-write page has exactly one copy」靠的是圖上沒畫的「回到 PRESENT 時釋放 chunk」；read-only page 的起點沒畫；read-only 在 PRESENT 時也有壓縮版這件事沒表現；HW 失敗但 SW decoder 成功的路沒畫；kernel's decoder 沒介紹。建議在 DECOMPRESSING → PRESENT 標出 chunk 是否釋放（分 read-only 與 read-write），畫出 read-only 的起點，並把 COMPRESSING 的「storing」改成能看懂的字。
- **第 8 張**：困惑指數 3，角色不清。水位堆疊的實線與虛線分不出哪個是 free frame、「from the top」方向不明；OPEN 意思不明；7 個 chunk 沒解釋；read-only 欄沒鎖、沒箭頭，和 read-write 欄畫法不一；沒有接上第 6 張的 COMPRESSING、COMPRESSED 與失敗回 PRESENT 的路；kernel SW 步驟畫成紫色虛線，和第 7 張的黑色實線不一致。
- **第 5 張（可選，不在門檻內）**：困惑指數 2，但 fault path 和 reclaimer 畫成一模一樣的單一框，容易讓人以為 fault path 也只有一份。若要重生，建議把 fault path 畫成好幾份疊起來（每個 core 一份），並修掉標題「LZ4 Kernel SW」的誤導。

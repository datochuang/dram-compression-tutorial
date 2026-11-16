# 冷讀驗收報告：cpu-mmu-kernel-sw gen3 第 12 張

- 日期：2026-11-16
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：cpu-mmu-kernel-sw gen3 的第 12 張 `12-what-held-in-the-model.png`
- 背景：先讀第 11 張 `11-refill-against-clear.png`，只當前情提要，不評

## 第 11 張帶進來的前情

- Core 1 的 hw thread A 上，NET 碰到 page P，TLB miss；kernel 的 TLB miss handler 讀到 P 的 PTE：valid，frame F。
- 同時 Core 1 的 hw thread B 上的 kernel 要把 frame F 拿走：把 PTE 設成無效，清自己 core 的 TLB，再送 clear request 給 Core 0，等所有回答。
- handler 在清完之後才把第 2 步讀到的舊內容寫進 TLB，造成 stale entry，NET 讀到別的 page 的資料。
- 結論：不拿 lock 的 TLB miss handler 可能寫回 kernel 剛清掉的 entry。第 12 張要講「兩種在 model 裡沒出事的寫法」。

## 先遮住 Key point

### 1. 人物與機器

| 方框 | 是誰 | 在做什麼 | 在意什麼 | 看得出來嗎 |
|---|---|---|---|---|
| Part one 表格的每一列 | TLB miss handler 的一種寫法（不是人物） | 列出 handler 怎麼寫、clear request 送到哪一層、model 跑出來的結果 | 會不會留下 stale entry | 看得出來。但四列**沒有編號**，下面卻用「way two」「way four」稱呼 |
| Part two 左邊紫色虛線框「Core 1: kernel taking frame F away」 | Core 1 上的 kernel SW，就是第 11 張 hw thread B 那個拿走 frame 的程式 | 握著 mm_lock，等 Core 0 回答 clear request | 要 Core 0 清完 TLB 才能繼續 | 看得出來。旁邊的鎖頭圖示表示 mm_lock 在它手上，也清楚。只寫 Core 1，沒寫是哪一個 hw thread，和第 11 張的寫法不一致，但不影響理解 |
| Part two 右邊紫色虛線框「Core 0: any kernel code that wants mm_lock」 | Core 0 上任何想拿 mm_lock 的 kernel SW，例子是 page fault handler | 關著 interrupt 等 mm_lock，所以收不到 clear request | 拿到 mm_lock | 看得出來。但「為什麼它會關著 interrupt 去等 lock」沒解釋，讀者只能接受 |
| 右下「Rules this suggests」 | 不是角色，是從 model 結果推出的規則 | 一條必守，兩種寫法二選一 | — | 清楚。OPEN 標籤與「which one to pick: not decided」清楚表示還沒決定 |
| 「New words on this sheet」 | 名詞解釋 | — | — | 清楚 |

角色本身沒有看不出來的。真正看不出來的是「way two」與「way four」指的是表格哪一列：讀者得自己從上往下數，並且猜「way one」就是第一列。

### 2. 看不懂的線或物件

- **表格第三列的「clear requests go to」欄**：「each core, or each hw thread when the handler may take a request before it finishes」把條件句塞進欄位裡。讀起來像是「兩種都試過、兩種都失敗」，但不確定。
- **表格第三列的失敗原因**：「writes the entry, then reads the PTE again」沒說讀到 PTE 無效之後會做什麼（推測是把剛寫的 entry 再清掉）。沒有這一步，「the other hw thread of the core can use the stale entry first」的「first」是在誰之前，要靠讀者自己補。
- **表格第四列「and interrupt handlers can take requests」**：主詞是 interrupt handler，讀起來像是「interrupt handler 執行時還可以再接 clear request」。但 Rules 與 Key point 用的是「a handler that holds mm_lock, with interrupt handlers able to take requests」。到底是「TLB miss handler 等 mm_lock 時 interrupt 開著」，還是「interrupt handler 本身可以被 clear request 打斷」，我分不出來。這是整張圖最模糊的一句。
- **Part two 的兩支箭頭**：「clear request」由左往右、「wants mm_lock」由右往左。「wants mm_lock」的箭頭指向 Core 1 的框，意思是「Core 0 想要 Core 1 手上的 lock」，看得懂。
- **鎖頭圖示**放在 Core 1 框的下方外面，不在框裡，第一眼會想「這個 lock 是獨立的東西還是 Core 1 拿著」。框裡有寫 holds mm_lock，所以還能對上。

### 3. 一句話說這張圖在講什麼（只看畫面）

TLB miss handler 有四種寫法，model 裡只有「不拿 lock 但關 interrupt、clear request 送到每個 hw thread」與「握 mm_lock」這兩種沒留下 stale entry；另外 model 還發現一個與寫法無關的 deadlock：拿走 frame 的 kernel 握著 mm_lock 等別的 core 回答 clear request，而別的 core 關著 interrupt 在等這把 lock，所以規定任何 kernel code 都不可以關著 interrupt 等 mm_lock。

### 4. 讀 Key point 之後

Key point：「Two ways of writing the TLB miss handler had no failure in the model: way two, or way four with interrupt handlers able to take requests. Separately, no kernel code may wait for mm_lock with interrupts off, whichever way is picked.」

判定：**一致**，附一個保留。

- 兩種沒出事的寫法、另外一條必守的規則，和畫面完全對得上。
- 保留：Key point 和 Rules 都用「way two」「way four」，表格卻沒有編號。結論本身沒錯，但讀者要回頭數列才能把結論對到畫面上。

### 5. 困惑指數

**3 / 5**。主線（兩種寫法 OK、另一個 deadlock 要另外防）讀得出來，但表格沒編號、第三列條件句、第四列「interrupt handlers can take requests」的意思要猜，加上表格的「no failure」和 deadlock 的「happened with all four」第一眼像是打架。

### 6. 可疑的錯字或多餘文字

- 沒有看到拼字錯誤。
- 「then pick one: … / or pick: …」：「then pick one」接「or pick」語氣不順，像兩條獨立規則。改成「pick one: way two … / or way four …」比較好讀。
- 表格第一欄沒有「way 1 / way 2 / way 3 / way 4」的編號，這是缺字而不是多字，但影響最大。
- Part two 的 Core 1 只寫「Core 1」，第 11 張是「Core 1, hw thread B」。不算錯，但前後不一致。
- 標題「What Worked in the Model」與內文用的「no failure ... evidence, not proof」語氣有落差：標題說 worked，內文小心地說只是沒找到失敗。不是錯，但標題比內文肯定。

### 7. 表格與 deadlock 兩部分之間有沒有互相矛盾

有一處**看起來**矛盾，仔細讀才化解：

- 表格第二、四列的結果欄寫粗體「**no failure**」。
- Part two 底下寫「it happened with all four handler ways」，也就是 deadlock 在 way two 和 way four 也發生了。
- 同一個 model、同一種寫法，一邊說 no failure，一邊說 deadlock 發生過，第一眼是矛盾的。
- 化解的線索只有副標「a deadlock that has nothing to do with which way is picked」與 Key point 的「Separately」。讀者要自己理解成：表格的 no failure 只算 stale entry 這一種失敗，deadlock 另外算。表格欄名「result in the model」沒有限定範圍，所以會誤讀。建議把「no failure」改成「no stale entry」，或在欄名寫「stale entry in the model」。

另外兩處容易讓人起疑但不算矛盾：

- way two 是「keeps interrupts off」，規則卻是「no kernel code waits for mm_lock with interrupts off」。快讀的人會以為 way two 違反規則。其實 way two 不拿 lock，所以沒有在「等 mm_lock」。圖上沒點出這一點。
- way four 是「holds mm_lock」，也就是 TLB miss handler 自己會等 mm_lock。它要符合規則，就得在等的時候讓 interrupt 開著；「with interrupt handlers able to take requests」可能就是在說這件事，但字面意思對不上（見第 2 點），讀者無法確定 way four 的附帶條件是不是就是那條必守規則。

## 建議

- 表格四列加上「way 1」到「way 4」的編號（或在第一欄前加一欄）。
- 結果欄的「no failure」改成「no stale entry」，或欄名改成限定 stale entry。
- 第四列與 Rules 裡的「interrupt handlers able to take requests」改成不需要猜的說法，例如「waits for mm_lock with interrupts on」。
- 第三列把「then reads the PTE again」補上「and removes the entry if the PTE is not valid」，失敗原因才接得上。
- 這幾項都是文字層級，版面不用動。

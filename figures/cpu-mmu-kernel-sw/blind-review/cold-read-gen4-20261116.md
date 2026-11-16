# 冷讀報告：cpu-mmu-kernel-sw gen4 第 12 張

- 日期：2026-11-16
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：cpu-mmu-kernel-sw gen4 的第 12 張（像素修補後的 .r2），`12-what-held-in-the-model.png`
- 背景：先讀第 11 張 `11-refill-against-clear.png`，只當前情提要，不評

## 第 11 張帶進來的印象

不拿 lock 的 TLB miss handler 在第 2 步讀到 PTE，kernel 在第 3 到 5 步把 frame F 拿走並清掉所有 TLB，handler 在第 6 步才把舊的 entry 寫進去，造成 stale entry。Key point 說「Sheet 12 shows the two ways that had no failure in the model」。

## 先遮住 Key point

### 1. 人物與機器

| 方框 | 是誰 | 在做什麼 | 在意什麼 |
|---|---|---|---|
| Part one 表格 | 沒有角色，是 TLB miss handler 的四種寫法 | 每一種寫法對第 11 張那種清除跑過 model，看會不會留下 stale entry | 哪一種不會留下 stale entry |
| 表格下方三行藍字 | 作者的註解 | 解釋 none found 的強度、為什麼要送到每個 hw thread、way 2 與 way 4 對 interrupts 的差別 | 不要把 none found 讀成證明 |
| Part two 左框「Core 1: kernel taking frame F away」 | 第 11 張的 thread B，正在拿走 frame F 的 kernel | 握著 mm_lock，等 Core 0 回應 clear request | 等 Core 0 清完 TLB |
| Part two 右框「Core 0: any kernel code that wants mm_lock」 | Core 0 上任何要 mm_lock 的 kernel code，例子是 page fault handler | 關著 interrupts 等 mm_lock，所以收不到 clear request | 拿到 mm_lock |
| 「Rules this suggests」框，右上 OPEN | 從 model 歸納出的規則，尚未定案 | 一條必守規則加上二選一 | 選 way 2 還是 way 4 |
| 「New words on this sheet」 | 名詞框 | 定義 deadlock、interrupts off、interrupt handler | |

角色大致清楚。看不太出來的地方：

- 表格裡沒有寫 handler 跑在哪個 core、哪個 hw thread。要靠第 11 張自己對回去：handler 在 Core 1 thread A，拿走 frame 的 kernel 在 Core 1 thread B。
- OPEN 的「not decided」沒寫由誰決定。

### 2. 看不懂的線或物件

- Part two 的兩支箭頭看得懂：clear request 從 Core 1 到 Core 0，wants mm_lock 從 Core 0 指回握著鎖的 Core 1，鎖的圖示在 Core 1 那邊。
- way 1 和 way 2 差了兩件事：way 2 關 interrupts，**而且** clear request 從「each core」改成「each hw thread」。讀者分不出 stale entry 消失是靠哪一件，還是兩件都要。藍字「why each hw thread」補了一半，但沒有說「只關 interrupts、仍然送到每個 core」會怎樣。
- way 2 為什麼有效要讀者自己推：handler 關著 interrupts 跑完寫入，clear request 才進來，這時再把剛寫的 entry 清掉。表格只寫到「finishes before it takes a clear request」，沒有寫「然後 clear 把它清掉」這一步。
- way 4 為什麼有效也要自己推：要知道拿走 frame 的 kernel 也握著 mm_lock，兩者才會互斥。這件事表格沒寫，要看到下面 Part two 左框「holds mm_lock」才知道。
- way 4 的「even when the miss happens inside an interrupt handler」：沒有背景的讀者會問為什麼要特別提 interrupt handler。這句隱含「interrupt handler 裡 interrupts 通常是關的，所以 way 4 在那裡要另外打開」，圖上沒說。
- way 4 的 clear request 是送到每個 core 還是每個 hw thread，表格沒寫。
- Part two 的 clear request 送到「Core 0」，而 way 2 說 clear request 要送到「each hw thread」。顆粒度不一樣，小地方。
- 右框為什麼 page fault handler 會關著 interrupts 等 mm_lock，沒有解釋；當作「假設有人這樣寫」可以接受。

### 3. 只看畫面的一句話

TLB miss handler 的四種寫法裡，只有「關 interrupts 跑完、clear 送到每個 hw thread」（way 2）與「握 mm_lock 讀寫、等鎖時開著 interrupts」（way 4）在 model 裡沒出現 stale entry；另外不管選哪一種，只要有 kernel code 關著 interrupts 等 mm_lock，就會和握著 mm_lock 等 clear 回應的 kernel 互相等死。

## 讀 Key point 之後

### 4. 畫面和結論是否一致

**一致。** Key point 的兩句分別對上 Part one 與 Part two，「which one to use is not decided」對上 OPEN。

小落差：Key point 寫「never left a stale entry」，表格寫「none found」並且藍字特別說「evidence, not proof」。Key point 前面有「In the model」可以撐住，但語氣比表格強一點。

### 5. 困惑指數

**2 / 5**。結構清楚、Part one 與 Part two 的分界和標題講得很明白；扣分在 way 2 與 way 4 為什麼有效要讀者自己補推論，way 1 到 way 2 一次改了兩件事。

### 6. 可疑的錯字或多餘文字

- 沒看到錯字。
- 重複：way 2 與 way 4 的描述出現三次（表格、藍字第三行、Rules 框），interrupt handler 的條件也出現兩次。不算錯，但佔版面；若要騰空間，可以把空間拿去補「way 2 / way 4 為什麼有效」。
- 副標「tried against the example clear request」裡的「example」單看這張不知道指什麼，要記得第 11 張說 clear request 只是範例機制。

### 7. 表格與 deadlock 兩部分有沒有互相矛盾

本張內部沒有矛盾：表格只問 stale entry，deadlock 是另一種失敗，標題「a Separate Deadlock」與副標「has nothing to do with which way is picked」先講清楚了。way 2 關 interrupts 但不等鎖，不違反「no kernel code waits for mm_lock with interrupts off」，藍字也點出來了。

讀起來有張力的兩處：

1. **跨張的矛盾**：第 11 張的 Key point 說「Sheet 12 shows the two ways that had no failure in the model」，但第 12 張說 deadlock「happened with all four ways」。照第 12 張的說法，way 2 與 way 4 在 model 裡也有失敗（deadlock），只是沒有 stale entry。讀者從第 11 張翻過來會先以為 way 2 和 way 4 是「完全沒事」，讀到 Part two 才被修正。這要改第 11 張的 Key point（例如改成「no stale entry」），不是第 12 張的問題。
2. 表格欄名「stale entry in the model?」下的粗體「none found」很搶眼，第一眼容易讀成「這兩種沒問題」。有標題與 Part two 撐著，不會誤會到底，但先入為主的印象要靠後半張修正。

## 結論

- 第 12 張不需要重生。
- 建議改第 11 張 Key point 的「no failure」為「no stale entry」，消除跨張矛盾。
- 若有機會微調第 12 張文字：在 way 2 補「the clear then removes the entry」，在 way 4 補「the kernel taking a frame also holds mm_lock」；這兩點是讀者目前要自己推的。

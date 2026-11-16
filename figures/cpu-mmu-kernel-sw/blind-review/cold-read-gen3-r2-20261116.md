# 冷讀報告：cpu-mmu-kernel-sw gen3 第 12 張（.r2）

- 日期：2026-11-16
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：cpu-mmu-kernel-sw gen3 的第 12 張第二次生成（.r2），`12-what-held-in-the-model.png`
- 背景：先讀第 11 張 `11-refill-against-clear.png`，只當前情提要，不評

## 第 11 張帶進來的前情（讀者記得的）

Core 1 hw thread A 上的 NET 碰到 page P，TLB miss。handler 讀到 PTE「P 在 frame F」。同時 Core 1 hw thread B 上的 kernel 把 frame F 拿走，清掉 Core 1 的 TLB，並送 clear request 給 Core 0。全部清完之後，handler 才把舊的 entry 寫進 TLB，結果留下 stale entry。Key point 說 handler 不拿 lock 就會發生這種事，第 12 張會給兩個沒出問題的做法。

## 1. 人物與機器（先遮住 Key point）

**Part one（表格）**：沒有人物，只有四種寫 TLB miss handler 的做法。

| 列 | 是誰 | 在做什麼 | 在意什麼 |
|---|---|---|---|
| way 1 | TLB miss handler，不拿 lock | 就是第 11 張的做法 | 有 stale entry |
| way 2 | TLB miss handler，不拿 lock，但關 interrupt | 幾步做完才收 clear request | clear request 必須送到每一個 hw thread，沒找到 stale entry |
| way 3 | TLB miss handler，寫完再讀一次 PTE | PTE 變了就丟掉剛寫的 entry | 丟掉之前，同一個 core 的另一個 hw thread 會用到，所以仍然 stale |
| way 4 | TLB miss handler，拿著 mm_lock | 讀與寫都在 lock 裡 | 沒找到 stale entry |

**Part two（deadlock）**：兩個紫色虛線框，都是 kernel SW，角色清楚。

- 左框，Core 1：正在拿走 frame F 的 kernel。握著 mm_lock（有鎖頭圖示），等 Core 0 回應 clear request。
- 右框，Core 0：任何想拿 mm_lock 的 kernel code，例子是 page fault handler。關著 interrupt 等 mm_lock，所以永遠不會收 clear request。

**看不出來或有點模糊的角色**：

- 左框只寫 Core 1，沒寫是哪一個 hw thread。第 11 張說是 hw thread B，這裡沒交代，影響不大。
- 右框的 page fault handler 為什麼會關著 interrupt，圖上沒講。讀者會問「誰讓它關的？」
- 表格欄位「clear requests go to」是一個**設計選擇**還是**該做法的前提**，看不太出來。way 1 為什麼配「each core」、不能配「each hw thread」也沒有說明。

## 2. 看不懂的線或物件

- Part two 的兩支箭頭（clear request 往右、wants mm_lock 往左）看得懂，形成一個環。
- 表格 way 4 的第三欄後半句「code inside interrupt handlers must still be able to take clear requests」：放在「clear requests go to」這一欄不對題，它講的不是送到哪裡，而是一條額外的限制。而且右下角對 interrupt handler 的定義是「a request 或 device 打斷時跑的 kernel code」，照這個定義 TLB miss handler 不是 interrupt handler，那 way 4 為什麼特別要求 interrupt handler 能收 clear request？我猜是「在 interrupt handler 裡發生 TLB miss，就會在 interrupt 關著時等 mm_lock」，但這是我推的，圖上沒有。這是整張最難懂的一格。
- way 3 第三欄「each core, or each hw thread when the handler may take a request before it finishes」條件太長，讀兩次才懂，而且不管怎麼送，第四欄都是 yes，所以這個條件對結論沒影響，讀者會覺得多花了力氣。
- 右上「OPEN」標籤與小字「which one to pick: not decided」看得懂。

## 3. 只看畫面，一句話

在模型裡試了四種 TLB miss handler 的寫法，只有 way 2（不拿 lock、短暫關 interrupt、clear request 送到每個 hw thread）與 way 4（拿著 mm_lock）沒有出現 stale entry；另外有一個和選哪種寫法無關的 deadlock：握著 mm_lock 等別的 core 回應 clear request 時，那個 core 若關著 interrupt 在等 mm_lock，兩邊就永遠互等。

## 4. 對照 Key point

**一致。**

Key point 說：模型裡只有 way 2 與 way 4 沒留下 stale entry，選哪個還沒決定；另外，kernel code 不能關著 interrupt 等 mm_lock，這在四種寫法下都 deadlock 過。和表格、OPEN 標籤、Part two 的藍字完全對得上。

唯一的細節：Key point 說「never left a stale entry」，表格與藍字說「none found ... evidence, not proof」。Key point 的口氣稍微強一點，但前面加了「In the model」，不算矛盾。

## 5. 困惑指數

**3 / 5**。角色與結論都清楚，但表格第三欄（尤其 way 3 與 way 4 那兩格）要反覆讀，way 4 對 interrupt handler 的要求圖上沒有解釋它為什麼存在。

## 6. 可疑的錯字或多餘文字

- 沒有看到錯字或亂碼。
- 副標題「tried against the example clear request」的「the example」要靠第 11 張「the clear request is one example」才懂，單看第 12 張有點突兀。
- 「Rules this suggests」裡的 way 2、way 4 兩行與表格重複，Key point 又重複一次。三處說同一件事，不是錯，但偏多。
- 「Part two: a deadlock, in the model」的逗號可有可無。

## 7. 表格與 deadlock 之間有沒有互相矛盾的感覺

有兩處讓讀者一時以為矛盾，細想才解開：

1. **way 2 要「keeps interrupts off」，規則卻說「關著 interrupt 會 deadlock」。** 快速看會以為 way 2 自己就違反規則。細讀才知道規則是「關著 interrupt **等 mm_lock**」，way 2 不拿 lock，所以不衝突。圖上沒有一句話把這兩件事接起來，例如「way 2 關 interrupt 但不等任何 lock，所以不會 deadlock」。
2. **way 4 的 handler 要等 mm_lock，那它自己會不會就是 deadlock 的右框？** TLB miss handler 若在 interrupt 關著的時候跑（例如發生在 interrupt handler 裡），等 mm_lock 正好就是 Part two 的情況。表格第四欄只寫 stale entry 有沒有，沒有 deadlock 欄；way 4 的「interrupt handlers must still be able to take clear requests」似乎就是在防這件事，但沒說出因果。讀者會懷疑「way 4 是不是其實比 way 2 多一個 deadlock 風險」，而圖把兩者並列成二選一，沒交代這個代價。

另外，副標題與藍字說 deadlock「has nothing to do with which way is picked」「happened with all four ways」，這點和表格不矛盾；但對 way 4 而言，選了它反而讓「等 mm_lock」的地方變多，說「無關」略嫌太乾淨。

## 結論

- 角色清楚：Part two 兩個 kernel SW 框一看就懂；表格沒有人物，靠欄位說明。
- 畫面與 Key point 一致。
- 圖面沒有錯字或畫錯的地方，重生圖片本身不會改善什麼。
- 困惑來自內容措辭：way 4 第三欄的 interrupt handler 限制沒有解釋原因，way 2 的「interrupts off」與 deadlock 規則之間缺一句橋接。若要改，應先改提示詞再重生，不是單純重抽。

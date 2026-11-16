# cpu-mmu-kernel-sw gen2 冷讀報告（第 11 到 14 張）

- 日期：2026-11-16
- 方法：只給圖、不給提示詞的冷讀
- 讀的是 cpu-mmu-kernel-sw gen2 的第 11 到 14 張
- 讀者設定：沒碰過 CPU MMU、page table、TLB 的工程師，前 10 張看過，知道紫色虛線框與紫色箭頭代表 kernel SW

---

## 11 — A TLB Miss Handler Without a Lock Can Undo a Clear

### 1. 人物與機器

- **NET**（火柴人，坐在筆電前，標籤 NET）：在 Core 1 hw thread A 上跑的程式。步驟 1 碰到 page P 發生 TLB miss，步驟 7 讀 frame F 卻拿到別的 page 的資料。看起來在意的是「讀到對的資料」。旁邊小字寫「NET runs here; on a TLB miss the kernel's handler runs here too」，能看出它是一個 user 程式，但 **NET 這個名字本身沒解釋**，新讀者不知道它是網路程式還是隨便取的名字。
- **Core 1, hw thread A**：列標籤。NET 與 TLB miss handler 輪流在這一列跑。步驟 2 與 6 是 handler，畫成紫色虛線框，符合 kernel SW 的色碼。
- **Core 1, hw thread B**：列標籤，旁註「the kernel, taking frame F away」。沒有人物，但角色有寫清楚：kernel 在趕 frame F。
- **Core 0**：列標籤，**沒有說明是誰**。只能從步驟 4 推出它是另一個 core，在接 clear request、清自己的 TLB、回答。是 kernel 在做事，但這一列沒寫「kernel」。

### 2. 看不懂的線或物件

- **紫色虛線框只畫在步驟 2 與 6**。步驟 3、4、5 也是 kernel 在做事（設 PTE not valid、清 TLB、回答），卻是黑色實線框。依前面的色碼，讀者會以為 3、4、5 不是 kernel SW。可能是想用紫色強調「handler」，但圖上沒說。
- **步驟 4 到步驟 5 沒有回程箭頭**。步驟 3 到 4 有紫色「clear request」箭頭，但 Core 0 的「answers」怎麼回到 thread B 的步驟 5 沒有畫。
- 步驟 2 到 6 的黑色虛線，上面寫「read and write happen at two moments; the whole clear fits in between」，意思清楚，是這張圖最有用的一條線。
- 「STALE ENTRY」標籤往下指步驟 6，清楚。
- 步驟 3「clears P from Core 1's TLB」：thread A 也在 Core 1，讀者會問「那為什麼沒清到？」下方「Why the clear missed it」有回答（當時 TLB 裡還沒有 P 的 entry），回答得到。
- 「Found in the model」的 model 是什麼，要看中下方「What the model is」才知道，標題下方第一句就用到這個詞，讀者一開始會卡一下。

### 3. 圖說的一句話（不看 Key point）

handler 先讀了 PTE，kernel 在另一個 hw thread 上趁這段空檔把 frame 拿走並清完所有 TLB，handler 之後才把舊的對應寫進 TLB，結果 NET 讀到別的 page 的資料。

### 4. 對照 Key point

Key point：沒拿 lock 的 TLB miss handler 會寫回 kernel 剛清掉的 entry；第 12 張給出模型裡沒失敗的兩種做法。
**一致。** 畫面完整呈現了這個 race。Key point 預告第 12 張，畫面上沒有對應的提示，但不衝突。

### 5. 困惑指數：2

時間軸與步驟編號讓 race 很好跟；扣分在紫色框只套在 handler、步驟 4 回 5 缺箭頭、NET 與 Core 0 的身分要自己推。

### 6. 可疑的錯字或多餘文字

- 沒有明顯錯字。
- 步驟 5「all answers in」偏口語，第一次看會想「answers 是什麼」；配合步驟 4 的「answers」才懂。
- 「clear request」在「New words」裡說「one hw thread asks another to clear an entry; the other takes it like an interrupt」，但時間軸上 clear request 是從 thread B 送到 **Core 0**（一個 core，不是 hw thread），詞的定義與畫面的粒度不一樣。

---

## 12 — What Worked in the Model, and One Deadlock

### 1. 人物與機器

- 沒有人物。
- **Core 1: kernel taking frame F away**（紫色虛線框）：握著 mm_lock，等 Core 0 回答 clear request。下方有 mm_lock 的鎖頭圖示，看得出鎖在 Core 1 手上。角色清楚。
- **Core 0: page fault handler**（紫色虛線框）：想拿 mm_lock，在 interrupts off 的狀態下等，所以永遠不接 clear request。角色清楚。
- 上方表格不是角色，是四種做法的比較。

### 2. 看不懂的線或物件

- 兩條紫色箭頭方向清楚：clear request 從 Core 1 到 Core 0，wants mm_lock 從 Core 0 到 Core 1，構成互等。
- **表格第 2 列「takes no lock, and finishes before it takes a clear request」**：新讀者不懂「finishes before it takes a clear request」靠什麼做到。是 handler 跑的時候關 interrupt？圖上沒說。
- **表格第 3 列的結果「a window remains: the other hw thread of the core can use the entry first」**：這其實是失敗，但沒有像第 1 列那樣用一個短詞（stale entry）或標成 failure，讀者要想一下才知道這一列不行。這一列的第二欄「each core, or each hw thread when the handler may take a request before it finishes」也很長、很難一次讀懂。
- **「this happened in every way tried」與表格的「no failure」看起來互相矛盾**。表格說第 2、4 列 no failure，下方 deadlock 卻說「在每一種做法裡都發生」。讀者要自己推出：deadlock 是 page fault handler 關著 interrupt 等 mm_lock 造成的，與 TLB miss handler 怎麼做無關，所以每一列都會遇到；表格的 no failure 指的是 stale entry 那類問題。圖上沒有把這兩件事分開講清楚。
- **page fault handler 為什麼會關著 interrupt 等 mm_lock**，第 11 張沒鋪陳，這裡突然出現。
- deadlock 畫的是 Core 1 與 Core 0，表格討論的是 hw thread；兩者的關係（例如 Core 0 的另一個 hw thread 能不能代為接 request）沒交代。
- 右上「OPEN / which one to pick: not decided」清楚。

### 3. 圖說的一句話（不看 Key point）

模型試了四種 TLB miss handler 與 clear request 的搭配，兩種沒出錯；另外發現 page fault handler 關著 interrupt 等 mm_lock 時，會和握著 mm_lock 等回答的 kernel 互等成 deadlock。

### 4. 對照 Key point

Key point：兩種做法在模型裡沒失敗（clear request 送到每個 hw thread 且 handler 先跑完才接；或 handler 握 mm_lock）；關著 interrupt 等 mm_lock 在每一種做法裡都 deadlock。
**一致**，但 Key point 也沿用了「in every way it was tried」，所以畫面裡「no failure」與「deadlock 每種都發生」的表面矛盾，Key point 沒有化解。另外 Key point 的第二種做法只寫「a handler that holds mm_lock」，省略了表格裡「interrupt handlers can take requests」這個條件，而這個條件正是避開 deadlock 的關鍵。

### 5. 困惑指數：3

表格四列條件句很長、第 3 列的失敗沒明講、「no failure」和「every way tried deadlocks」乍看衝突，讀者需要讀兩三遍才拼得出來。

### 6. 可疑的錯字或多餘文字

- 沒有明顯錯字。
- 「no failure: none in any order the model tried; that is evidence, not proof」與「why each hw thread: ...」兩行藍字是有用的，不算多餘。
- 「New words」把 interrupts off 定義成「the hw thread takes no requests until they are on again」，好懂。

---

## 13 — Where It Goes Wrong If You Are Careless

### 1. 人物與機器

- 沒有人物也沒有機器。六張卡片，每張一個圖示、一個標題、Risk、Rule、藍字出處。不需要角色，結構清楚。

### 2. 看不懂的線或物件

- **卡 1「A TLB entry left behind」的圖示**：四格方塊其中一格打叉。打叉那格是「被留下的 entry」還是「已清掉的 entry」？讀不出來。
- **卡 5「Another program's entry」的圖示是兩張紙中間一個等號**，看起來比較像「兩份一樣的東西」，更像卡 6「Two entries for one page」的意思；卡 6 的兩個箭頭指向一個方塊，也能讀成「兩個東西寫進同一格」。兩張卡的圖示放錯位置的感覺。
- 卡 2 時鐘加箭頭表示「晚寫」、卡 3 兩圈互指表示互等、卡 4 循環箭頭表示自己 miss 自己，都看得懂。
- 卡 3 的 Risk「the kernel holding mm_lock waits for an answer that never comes」，配合第 12 張讀得懂；單看這張，不知道「answer」是什麼的回答。

### 3. 圖說的一句話（不看 Key point）

kernel 自己在多核上填 TLB 有六個陷阱，每個陷阱各有一條規則，有些已在模型裡驗過，有些要等 CPU 手冊。

### 4. 對照 Key point

Key point：每個 TLB entry 都由 kernel 寫，所以 stale、duplicate、wrong-program entry 都是 kernel 要防的；照順序做、別關著 interrupt 等 lock、讓 handler 的記憶體不靠 TLB 也碰得到；三個答案要等 CPU 手冊。
**一致。** 「三個答案等 CPU 手冊」對得上卡 4、5、6。小落差：卡 2 的規則「從兩種做法挑一種，還沒決定」在 Key point 裡沒有對應，只被「Keep the order of steps」模糊帶過。

### 5. 困惑指數：2

卡片格式整齊、一張一事；扣分在兩三個圖示意思不明或像是放錯卡。

### 6. 可疑的錯字或多餘文字

- 沒有錯字。
- 副標「Most of them do not crash at once; they quietly read the wrong frame」說得太滿：卡 3（deadlock）會卡住而不是讀錯 frame，卡 4（handler 裡又 miss）也不是讀錯 frame。

---

## 14 — What Is in the Model, What Is Open

### 1. 人物與機器

- 沒有人物也沒有機器。左邊是勾選清單「In the model so far」，右邊是「Open」表格（question / why it matters / needs）。不需要角色。

### 2. 看不懂的線或物件

- **最後一個勾「waiting for mm_lock with interrupts off deadlocks: a rule」**：打勾放在一件「會 deadlock」的事旁邊，第一眼像是「deadlock 被核可」。要讀到「a rule」才知道勾的意思是「這條規則已經在模型裡確認」。勾的意思是「模型裡有」而不是「做法定案」，圖上沒明說。
- 第 4 個勾「two ways ... had no failure」與 Open 表的「does the TLB miss handler take mm_lock — a design decision」是同一件事的兩面（模型驗了兩條路，選哪條沒定），能對得上，但讀者要自己連起來。
- 第 2、3 個勾（page fault handler 在 mm_lock 下再查一次 PTE、第一次碰到的 page 拿到全零的 frame）在第 11 到 13 張沒出現，應該來自前 10 張；單看後四張會覺得突然。
- 「needs」欄有一列是「measurement on the chip」，副標卻只說「open 的大多要 CPU 手冊，其餘是 design 和 product decision」，沒包括量測。

### 3. 圖說的一句話（不看 Key point）

模型（在 host 電腦上跑，還沒上這顆處理器）已經確認了幾條步驟順序的規則，還沒解決的問題大多要等 CPU 手冊，其餘是 kernel team 的設計決定、產品決定，以及要在晶片上量的時間。

### 4. 對照 Key point

Key point：步驟順序的規則在模型裡驗過了；open 的大多是這顆 CPU 提供什麼，手冊沒回答前 handler 寫不出來。
**一致。**

### 5. 困惑指數：2

左勾右表的對照很清楚；扣分在 deadlock 旁的打勾容易誤讀、副標漏了量測那一類。

### 6. 可疑的錯字或多餘文字

- 沒有錯字。
- 「separate address spaces for our programs」的「our」第一次出現，指誰沒說（應是產品自己的程式），不算錯。

---

## 跨圖觀察

**故事線**：11（一個具體的 race）→ 12（試了哪些修法、哪些成立，以及順帶發現的 deadlock）→ 13（把這幾張和前面的教訓整理成六個陷阱）→ 14（哪些已驗、哪些還開著）。由具體到整理到收尾，順序合理，每張都用藍字指回前面的張數，串得起來。

**斷掉的地方**：
1. **第 11 到 12 張之間，deadlock 是突然冒出來的。** 第 11 張只講 TLB miss handler 與 clear 的 race，沒提 page fault handler 會拿 mm_lock、也沒提 interrupts off。第 12 張下半直接把 page fault handler 關著 interrupt 等 mm_lock 擺出來，讀者不知道這個情境從哪來。
2. **第 12 張「no failure」與「deadlock happened in every way tried」的關係沒講清楚**，這是四張裡唯一會讓讀者真的卡住的地方。
3. 紫色色碼在第 11 張只套在 handler，kernel 在 thread B 與 Core 0 的動作沒有用紫色，與前面「紫色 = kernel SW」的約定不一致；第 12 張兩個框都是紫色，反而一致。
4. 第 14 張有兩個勾選項是後四張沒出現過的，靠前 10 張支撐，單看這段時銜接略跳。

**用自己的話說結論**：
這顆晶片的 TLB 由 kernel 自己填。TLB miss handler 先讀 PTE、後寫 TLB，中間如果另一個 hw thread 上的 kernel 剛好把那個 frame 拿走並清完所有 TLB，handler 就會把過期的對應寫回去，程式之後讀到別人的資料。模型（在 host 上跑的 kernel 模型，不是真晶片）試出兩種不會出事的做法：一是 handler 不拿 lock，但 clear request 要送到每一個 hw thread，而且 handler 跑完才接 request；二是 handler 讀寫期間握著 mm_lock，同時 interrupt handler 仍能接 clear request。兩種選哪一種還沒定。另外有一條必守規則：不能關著 interrupt 等 mm_lock，否則握著 mm_lock 等回答的 kernel 與等 mm_lock 的 handler 會互等成 deadlock。其他幾個陷阱（handler 自己 miss、換程式後的舊 entry、同一 page 兩個 entry）怎麼防，要等 CPU 手冊；手冊沒來之前 handler 寫不出來。

---

## 總表

| 張 | 標題 | 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|---|---|
| 11 | A TLB Miss Handler Without a Lock Can Undo a Clear | 2 | 是（NET 名稱與 Core 0 的身分要自己推） | 一致 |
| 12 | What Worked in the Model, and One Deadlock | 3 | 是 | 一致（但「no failure」與「every way tried deadlocks」的表面矛盾沒化解） |
| 13 | Where It Goes Wrong If You Are Careless | 2 | 是（無角色，不需要） | 一致 |
| 14 | What Is in the Model, What Is Open | 2 | 是（無角色，不需要） | 一致 |

## 建議重生

- **第 12 張**（困惑指數 3）。建議：
  - 把 deadlock 與表格分開講清楚：deadlock 來自 page fault handler 關著 interrupt 等 mm_lock，與 TLB miss handler 選哪種做法無關；把「this happened in every way tried」改成類似「this happened whichever handler way was used」。
  - 表格第 3 列的結果加上明確的失敗標記（例如「fails: ...」）。
  - 第 2 列「finishes before it takes a clear request」補一句怎麼做到（例如 handler 跑時不接 request）。
  - Key point 的第二種做法補上「interrupt handlers can take requests」這個條件。

不在重生清單、但可以順手修的小地方：
- 第 11 張：步驟 3、4、5 改成紫色虛線框（或在圖上註明紫色只標 handler）；補步驟 4 回步驟 5 的 answer 箭頭；Core 0 列加「the kernel」。
- 第 13 張：卡 1 打叉格的意思、卡 5 與卡 6 的圖示對調或重畫；副標不要說「most quietly read the wrong frame」。
- 第 14 張：deadlock 那一項的勾容易誤讀成「核可」；副標補上「measurement on the chip」。

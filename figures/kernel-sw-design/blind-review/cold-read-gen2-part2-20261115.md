# 冷讀驗收：kernel-sw-design 第二輪，第 6、8、9、12、13 張

- 日期：2026-11-15
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：kernel-sw-design 第二輪（gen2）的第 6、8、9、12、13 張
- 讀者設定：沒有這個主題背景的工程師。前面幾張介紹過的詞（page、frame、page table、TLB、page fault、chunk、COT、mm_lock、reclaimer）當作已知。第 7、10、11 張沒有看到。

---

## 第 6 張：The Six States of a Page（06-page-states.png）

### 1. 人物與機器
- 沒有畫人物或機器，畫的是六個狀態方塊：UNTOUCHED、PRESENT、COMPRESSING、COMPRESSED（斜線，表示壓縮過）、DECOMPRESSING、LOST。
- 動作者只出現在箭頭的文字裡：reclaimer、LZ4 HW、page fault、kernel 的 decoder。都看得出是誰。
- 兩個起點標得清楚：read-write page 從 UNTOUCHED 開始；read-only page 從 COMPRESSED 開始（開機前就壓好了）。

### 2. 看不懂的線、表格、數字或物件
- 「needs more than 7 chunks」：7 是怎麼來的，圖上沒說。我自己推是 4 KB 的 page 除以 512 B 等於 8 個 chunk，用到 8 個就沒省到空間，但這是讀者自己算的。
- UNTOUCHED 的說明是「nobody has written yet」，往 PRESENT 的箭頭卻寫「first touch」。讀一下算不算 first touch？用字不一致，會讓人想一下。
- DECOMPRESSING 到 LOST：HW 失敗後 kernel decoder 成功的那條路，圖上沒有獨立的箭頭，只能推論是走同一條「back in a frame」回 PRESENT。
- 進了 LOST 之後程式會怎樣，圖上沒說。

### 3. 新手卡住的地方
- 「7 chunks」這個門檻沒有解釋，讀者不知道為什麼是 7。

### 4. 圖說的一句話
每個 page 在六個狀態之一：reclaimer 把 PRESENT 的 page 送去壓縮（read-only 直接丟 frame），page fault 經過 DECOMPRESSING 把它帶回 frame，壓縮或解壓縮都失敗時才會到 LOST。

### 5. Key point 與畫面
一致。「read-only 一直保留壓縮的副本」與左下的方塊相符；「read-write 只有一份」與「stored: the frame is freed」「a read-write page frees its chunks」相符。（壓縮與解壓縮進行中短暫有兩份，Key point 沒提，不算矛盾。）

### 6. 困惑指數
2。狀態圖本身清楚，只有「7 chunks」與 LOST 之後的結果沒交代。

### 7. 可疑的錯字或多餘文字
- 無明顯錯字。
- 「nobody has written yet」與「first touch」的用字可以統一。

---

## 第 8 張：Pushing a Cold Page Out: the Reclaimer（08-reclaimer.png）

### 1. 人物與機器
- reclaimer：紫色虛線方塊，「one kernel thread, asleep most of the time」，清楚。
- free frames 的量表：高低兩條 watermark，灰色表示目前的存量，左邊「faults take frames」往下，右邊「the reclaimer frees frames」往上，清楚。
- clock：八個小方塊圍一圈加一根指針。方塊沒有標籤，不確定是 page 還是 frame（面板標題寫 page，下方方塊寫「At each frame the hand passes」）。方塊上也沒有畫 used mark，看不出指針為什麼停在這一格。
- Push it out：read-only 與 read-write 兩欄步驟，鎖頭圖示表示拿 mm_lock。綠色的 COMPRESS 方塊帶齒輪，推得出是 LZ4 HW 在做，但方塊上沒寫 LZ4 HW。

### 2. 看不懂的線、表格、數字或物件
- 「reserve 7 free chunks」：又是 7，仍然沒說來源。
- read-only 欄有兩個連續的 mm_lock 方塊，中間什麼都沒做。為什麼要放開再拿一次，看不出來。
- COMPRESS 與「write the frame's cached lines back」兩格沒有鎖頭，暗示這時不拿 lock，但圖上沒有明說。
- 「clear every core's TLB」用什麼機制，沒說（作為冷讀可以接受，只是會有人問）。

### 3. 新手卡住的地方
- 「7 chunks」的門檻（同第 6 張）。
- 「PTE」第一次以縮寫出現，如果前面的圖只說 page table 而沒說 PTE，新手會卡。

### 4. 圖說的一句話
free frame 低於 low watermark 時，背景的 reclaimer 醒來，用 clock 找最近沒用過的 page 推出去：read-only 只要讓 PTE 失效、清 TLB、放掉 frame；read-write 還要把 cache 寫回 DRAM、交給 LZ4 HW 壓縮、寫 COT，一直做到 high watermark。

### 5. Key point 與畫面
一致。「壓縮都由 reclaimer 做」與整張畫面相符；「never the page a thread has just faulted in」對應「just faulted in, or pinned? always skip」。

### 6. 困惑指數
2。流程清楚；clock 的方塊沒標籤、read-only 為什麼拿兩次 lock 會讓人停一下。

### 7. 可疑的錯字或多餘文字
- 「At each frame the hand passes」與面板標題「Which page」用字不一致，clock 選的是 page 還是 frame 要統一。

---

## 第 9 張：Design Choice: Keep Compression Off the Fault（09-keeping-faults-short.r3.png）

### 1. 人物與機器
- 左：一般 kernel 的 background reclaim thread 與 direct reclaim。右：我們的 reclaimer thread 與「no direct reclaim」。
- 「no direct reclaim」用了和 thread 一樣的紫色虛線框，看起來像一個角色，其實它是「沒有這件事」。
- 下方註解提到「the four programs」與「four LZ4 engines」，圖上沒有畫，也沒說這四個程式是誰。

### 2. 看不懂的線、表格、數字或物件
- 表格「faults that waited for a frame」：0、0、10、178、716 是絕對次數，沒有給總 fault 數，不知道 716 算多還是少。
- 「fault time, slowest one in a hundred」是第 99 百分位。上方的論點是 worst case，表格卻沒有最大值，讀者沒辦法用這張表判斷 worst case。
- normal 負載下沒有 fault 等 frame，p99 仍是 6.98 µs。這 6.98 µs 是怎麼來的（CPU 多快、LZ4 HW 多快、「small simulated machine」有多小）沒有交代。
- 「normal」負載的定義沒給，只說其他列是 normal 的幾倍。
- 左邊說一般 kernel「fast on average; the worst case is long」，但沒有對照數字，比較只有我們這一邊的資料。

### 3. 新手卡住的地方
- 「four LZ4 engines」：前面只說 LZ4 HW，engine 是什麼、為什麼有四個沒有解釋。
- 表格缺分母（總 fault 數或總 access 中有多少 fault），讀者無法判斷 10、178、716 的嚴重程度。

### 4. 圖說的一句話
一般 kernel 在 reclaim 落後時讓缺記憶體的 thread 自己壓縮，我們只讓 fault 解壓縮、落後時就睡著等 frame；模擬顯示 4 倍負載以內沒有 fault 等 frame，10 倍以上開始等，p99 時間變長。

### 5. Key point 與畫面
一致。normal 負載 0 次等待對應「never waits」，10 倍以上有等待對應「under heavy load it does」，OPEN「direct reclaim or not」與 Two knobs 對應「how to bound that wait is still open」。小落差：Key point 講「bound」，表格給的是 p99 而不是最大值。

### 6. 困惑指數
3。對照的論點清楚，但表格是這張圖的主角，卻缺分母、缺最大值、缺模擬條件，數字沒辦法讀出結論。

### 7. 可疑的錯字或多餘文字
- 副標題說「background compressor」，其他地方都叫 reclaimer，名字多了一個。
- 「no direct reclaim」不該用 thread 的虛線框樣式。

---

## 第 12 張：Where It Goes Wrong If You Are Careless（12-where-it-goes-wrong.png）

### 1. 人物與機器
- 沒有畫任何人物、機器或圖示，六個純文字方塊，每格 Risk 與 Rule。
- 每條 Rule 都寫了「by the kernel」或「by kernel and programs」，誰負責是清楚的。
- 這張是整組裡最像文字投影片的一張，白板圖的優勢沒有用到。

### 2. 看不懂的線、表格、數字或物件
- Stale cache lines：「drop its old lines after DECOMPRESS」——剛解壓縮進來的 frame 為什麼會有舊的 cache line？（推論是 frame 上一次用的資料還在 cache 裡），圖上沒說。
- A wrong answer from the LZ4 HW：「decode the stream with its own decoder first」可以讀成「每次都先用 SW decoder 解」，這和第 6 張「HW 給錯答案時才用的 software」相反。我推測意思是「丟掉 page 之前先用自己的 decoder 再解一次」，但字面有歧義。
- 「after three wrong answers in a row」：3 是怎麼來的沒說。
- 這一格只講 HW 誤報壞掉，沒講 HW 解出錯的資料卻說成功的情況。
- A page pushed out too soon：為什麼 page 會在指令執行前就被推走、為什麼會「again and again」，沒有畫出來；「last faulted-in pages」是幾個 page 也沒說。
- 副標題「Each of these was found or confirmed in the simulations」：哪些是找到、哪些是確認，沒有區分，也沒有證據。

### 3. 新手卡住的地方
- 「drop its old lines」（cache invalidate）沒有解釋，也沒說為什麼 DECOMPRESS 之後需要。
- 「stream」（壓縮後的資料流）第一次以這個詞出現。
- 「Two jobs on one frame」的「two engines」：同第 9 張，engine 沒有介紹過的話會卡。

### 4. 圖說的一句話
六個做錯就會壞資料或卡住的地方，每一個都有一條便宜的規則擋住，幾乎全由 kernel 負責。

### 5. Key point 與畫面
部分一致。
- 「keeps the CPU and the LZ4 HW from seeing different copies」對應 Stale cache lines；「protects pages that just came back」對應 pushed out too soon；「never trusts one wrong answer」對應 wrong answer 那格；「HW stays simple」對應「the HW does not check」。
- 不一致：Key point 說「The kernel does all the checking」，但「A fault where nobody may wait」那格寫的是「by kernel and programs」，有一部分是程式的責任。
- Key point 沒提 TLB、nobody may wait、two jobs 三格。

### 6. 困惑指數
3。每格單獨看懂一半，幾條規則需要背景（cache invalidate、SW decoder 的順序、3 次）才看得懂，又沒有圖幫忙。

### 7. 可疑的錯字或多餘文字
- 「decode the stream with its own decoder first」的「first」容易誤讀。

---

## 第 13 張：What Is Designed, What Is Open（13-designed-and-open.png）

### 1. 人物與機器
- 沒有人物或機器。左邊五項已設計（打勾），右邊九項 Open 的表格。
- 「who decides」欄混了人（design＝kernel team、product）與證據來源（real access traces、the CPU manual、real interrupt times）。欄名叫「who」，內容有一半是「what」。底下的註解只解釋了 design 與 product。

### 2. 看不懂的線、表格、數字或物件
- 「a page that needs more than 7 chunks — today it keeps its frame forever」：第 6 張只畫回 PRESENT，沒說「forever」（之後不會再試）。這是新資訊。
- 「frames and chunks both full — which program gets the error」：這個情況在我看到的圖裡沒有出現過。
- 「who sets the used mark — the CPU MMU may not set one」與第 8 張「the CPU MMU sets no used mark here」說法不同：一張說一定不會，一張說可能不會。
- 「sleep or poll — time against CPU」太簡短，讀者要自己補成「延遲與 CPU 佔用之間的取捨」。
- 「after the kernel stops using a faulty LZ4 HW — read-write pages can no longer be compressed」：隱含 kernel 沒有 SW compressor，圖上沒說。
- 第 6 張的 LOST 狀態沒有出現在 Open 裡，進 LOST 之後怎麼辦沒有交代。

### 3. 新手卡住的地方
- 「who decides」欄裡的 real access traces、the CPU manual、real interrupt times 不是人，讀者會不確定到底誰要做決定。
- 「sleep or poll」來自第 10 張，沒看過第 10 張會卡（整組依序看的話不會）。

### 4. 圖說的一句話
已經做出來並在模擬中檢查過的五項設計，和九個還要靠設計決定、產品決定、CPU 手冊或實測才能定的問題。

### 5. Key point 與畫面
部分一致。
- 「What is open is mostly policy: memory runs out / which pages to pick / how long a fault may take」分別對應 frames and chunks both full、how to pick cold pages、direct reclaim 與 fault on a page being compressed，相符。
- 落差：Key point 說「The structure is settled」，畫面的註解是「built and checked in simulation; not yet signed off」。settled 與 not yet signed off 給讀者的感覺不同。

### 6. 困惑指數
2。結構清楚，問題主要是欄名與幾句話和前面的圖說法不一致。

### 7. 可疑的錯字或多餘文字
- 「who decides」欄名與內容不符。
- 「may not set one」與第 8 張的說法不一致。

---

## 連著看：故事線

順序是「page 有哪些狀態 → reclaimer 怎麼把 page 推出去 → 為什麼壓縮不放在 fault 上 → 哪裡容易出錯 → 已定與未定」，大方向順。斷掉或接不上的地方：

1. **「7 chunks」三次出現都沒解釋**（第 6、8、13 張）。第 13 張還把它列成 Open，讀者到最後都不知道 7 從哪裡來。
2. **engine 這個詞突然出現**：第 9 張「four LZ4 engines」、第 12 張「two engines」。如果第 11 張之前沒介紹 LZ4 HW 有好幾個 engine，這裡會斷。
3. **第 9 張的「four programs」**沒有畫，也沒交代，讀者不知道模擬裡跑的是什麼。
4. **第 12 張的規則一半在前面出現過**（寫回 cache、清 TLB、跳過剛 fault 進來的 page 都在第 8 張），另一半是新的（DECOMPRESS 後丟掉舊 cache line、三次錯誤停用 HW、兩個 job 不能碰同一個 frame）。新的那些沒有前面的圖可以對照。
5. **第 13 張帶進新的情況**：「frames and chunks both full」與「keeps its frame forever」在前面沒看過。第 6 張的 LOST 在第 13 張沒有後續。
6. **用字不一致**：reclaimer／background compressor；clock 選 page／frame；CPU MMU「sets no」／「may not set」used mark。

## 總表

| 張 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|
| 6 The Six States of a Page | 2 | 是 | 一致 |
| 8 the Reclaimer | 2 | 是 | 一致 |
| 9 Keep Compression Off the Fault | 3 | 是 | 一致 |
| 12 Where It Goes Wrong | 3 | 是 | 部分一致 |
| 13 What Is Designed, What Is Open | 2 | 是 | 部分一致 |

## 我用自己的話講的結論

這個設計把「壓縮」整件事丟給背景的 reclaimer thread：它在 free frame 少於 low watermark 時醒來，用 clock 挑最近沒用過的 page，read-only 的直接放掉 frame（壓縮副本本來就在），read-write 的先把 cache 寫回 DRAM、交給 LZ4 HW 壓縮、記進 COT 才放掉 frame。fault 只做解壓縮，不像一般 kernel 那樣在缺記憶體時自己動手壓縮；代價是負載很重時 fault 要睡著等 reclaimer 生出 frame，模擬裡 10 倍負載以上開始發生。正確性靠 kernel 守幾條便宜的規則：cache 與 HW 看到同一份資料、TLB 清乾淨才重用 frame、剛 fault 進來的 page 不能馬上被推走、不信任 HW 單次的錯誤、同一個 frame 不能同時給兩個 job，HW 本身什麼都不檢查。結構已經在模擬裡跑過，還沒定的大多是政策：記憶體用完怎麼辦、怎麼挑冷 page、fault 最久可以多久，另外 used mark 誰來設要等 CPU 手冊。

## 建議重生

- **第 9 張**（困惑指數 3）：表格補分母（總 fault 數或比例）、補最大值或明說只看 p99、補「normal」與模擬機器的條件；「no direct reclaim」不要用 thread 的框；交代 four programs 與 four LZ4 engines，或改成前面已介紹過的說法。
- **第 12 張**（困惑指數 3，部分一致）：每格加一個小圖（cache 與 DRAM 兩份、TLB 指向舊 frame 等）；改寫 wrong answer 那格的「first」；說明 DECOMPRESS 後為什麼要丟舊 cache line；Key point 的「kernel does all the checking」改成承認 programs 也有一條規則。
- **第 13 張**（部分一致，輕修即可）：「who decides」欄改名或拆成「decided by / needs」；Key point 的「settled」與「not yet signed off」對齊；used mark 的說法與第 8 張統一。

另外不在重生清單、但值得一起修的：第 6、8 張的「7 chunks」加一句來源；第 8 張 clock 的 page／frame 用字統一。

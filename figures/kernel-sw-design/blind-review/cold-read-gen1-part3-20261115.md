# 冷讀驗收報告：kernel-sw-design gen1 第 9 到 13 張

- 日期：2026-11-15
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：kernel-sw-design 的第 9 到 13 張（`gen1/09-keeping-faults-short.r2.png`、`10-where-the-time-goes.png`、`11-many-cores-at-once.r2.png`、`12-where-it-goes-wrong.png`、`13-designed-and-open.png`）
- 讀者設定：完全不懂這個主題的工程師，只知道前 8 張介紹過的名詞（page、frame、CPU MMU、TLB、page swap、chunk、COT、mm_lock、fault 路徑、reclaimer 與高低水位）

---

## 第 9 張：Design Choice: Keep Compression Off the Fault

### 1. 人物與機器
- 沒有人物，全部是方塊。左邊「A common general-purpose kernel」有兩個紫色虛線框：background reclaim thread（補 free page 到水位以上）、direct reclaim（落後時，需要記憶體的 thread 自己壓縮 page）。
- 右邊「Ours」：reclaimer thread（補 free frame 到 high watermark）、no direct reclaim（落後時，fault 等 free frame），旁邊一個 OPEN 標「direct reclaim or not」。
- 下方是模擬表格與「Two knobs」方塊。
- 角色看得出來，但「the thread that needs memory」是 user SW 的 thread 還是 kernel 的 thread，沒有說。右邊「the fault waits」裡，等的是誰（fault 的 thread？那個 core？）也沒有說；fault 是事件，不是角色。
- 紫色虛線框代表什麼（thread？機制？）沒有圖例。

### 2. 看不懂的線、表格、數字或物件
- **load 這一欄**：normal、4 times、10 times……是什麼的倍數？fault 的頻率？存取量？沒有說。
- **faults that waited for a frame**：10、178、716 是總數，但分母（總共幾次 fault、跑多久）沒有給，看不出比例。
- **slowest one in a hundred**：我讀成 fault 時間的 99th percentile，但圖上沒寫「fault latency」，也沒寫是從哪裡量到哪裡。
- 40 倍負載下有 716 次 fault 等 frame，但 1% 最慢的只有 20.42 µs。這表示等 frame 的時間其實不長，還是等的 fault 不到 1%？沒有分母就判斷不了。
- 「small machine, four LZ4 engines, two COMPRESS jobs at once; synthetic load」：small machine 多小？four LZ4 engines 是第一次出現「engine」的數量（前 8 張只說 LZ4 HW）。「two COMPRESS jobs at once」和右邊 knob「how many COMPRESS jobs the reclaimer keeps out at once」是同一件事，可以讀出來，但沒有明連。
- 左邊寫「free pages above a watermark」，右邊寫「free frames up to the high watermark」。page 與 frame 混用，「above」與「up to」也不同，讀者會懷疑兩邊在講不一樣的東西。

### 3. 新手卡住的地方
- 「load」的定義。
- 「slowest one in a hundred」＝ percentile 的概念，以及它量的是哪一段時間。
- 「direct reclaim」只有一行解釋，讀者不知道為什麼它的 worst case「long and hard to bound」（因為壓縮可能要等鎖、等 HW、等很多 page？）。
- 「keeps out at once」＝ in flight，用語不直白。

### 4. 圖說的一句話
我們把壓縮全部放在背景的 reclaimer，fault 只做解壓縮；模擬顯示正常與 4 倍負載下沒有 fault 需要等 frame，10 倍以上開始有。

### 5. Key point 與畫面
**一致。** 「normal load never waits」對應表格的 0；「how to bound that wait is still open」對應 OPEN。小差異：OPEN 標的是「direct reclaim or not」，Key point 說的是「how to bound that wait」，兩者有關但說法不同，讀者要自己接起來。

### 6. 困惑指數：3
架構對比清楚，但表格缺 load 的定義與分母，數字讀得到卻解讀不了。

### 7. 可疑的錯字或多餘文字
- 副標題與兩個大框之間、靠近中間上方有一個多餘的藍色小點。
- 左右兩邊 page / frame、above / up to 的用語不一致。

---

## 第 10 張：Design Choice: How to Wait for the LZ4 HW

### 1. 人物與機器
- 沒有人物。上方一條長條：notify and wake up 3.32 µs（白）、kernel instructions 1.45 µs（紫色虛線）、LZ4 HW 1.27 µs（綠）。
- 下方兩個方案方塊：Sleep until the interrupt（core 去做別的事）、Poll the completion（core 空轉等 job 做完），中間 OPEN「which one, or poll briefly then sleep」。
- 「the core」可讀成 fault 的那個 core。但「notify」是誰通知誰（LZ4 HW 發 interrupt 給哪個 core？）、「wake up」叫醒的是誰（fault 的 thread？），畫面上沒有角色。

### 2. 看不懂的線、表格、數字或物件
- **長條的順序**：notify and wake up 在最左邊、LZ4 HW 在最右邊。如果這是時間線，順序是反的（應該先 HW 做完才通知）。如果只是拆解比例，應該說明它不是時間順序。
- **加總對不上**：3.32 + 1.45 + 1.27 = 6.04 µs，標題寫 about 6.20 µs，差 0.16 µs。差額可能就是右下「locks and the job ring: under 0.2 µs」，但那行字放在 LZ4 HW 綠框下面，讀起來像是 LZ4 HW 的附註，不像是一段沒畫出來的時間。
- **kernel CPU time 1.29% / 2.27%**：是什麼的百分比？全部 CPU 時間？哪個負載下？沒說。
- **Poll 的 median 3.23 µs**：6.20 − 3.32 = 2.88，比 3.23 小。poll 多出來的 0.35 µs 從哪來，沒有說。
- 紫色虛線框在第 9 張代表 thread 機制，這裡代表 kernel instructions。顏色與線型的意思不一致。
- 「interrupt and wake-up times are assumed」「instruction counts are assumed」：誠實標示了假設值，很好，但假設值是多少、從哪來不知道。

### 3. 新手卡住的地方
- 「completion」：完成的通知寫在哪裡？（completion ring？）沒有解釋。
- 「job ring」：只出現在小字裡，沒有介紹。
- 「wake up」為什麼要 3.32 µs：睡覺的 thread 要經過 interrupt、scheduler、context switch，新手不知道這條路有多長。
- 「poll briefly then sleep」這種混合做法沒有畫出來。

### 4. 圖說的一句話
一次解壓縮 fault 裡，LZ4 HW 本身只佔一小段，大部分時間花在通知與叫醒；改用 polling 可以把 fault 時間減半，但 CPU 用得比較多，要選哪個還沒決定。

### 5. Key point 與畫面
**一致。** 3.32 > 1.27（叫醒比解壓縮貴）、6.20 → 3.23（大約減半）、1.29% → 2.27%（CPU 多用）、「needs real interrupt times」對應「interrupt and wake-up times are assumed」。

### 6. 困惑指數：2
主訊息一眼看得出來，只有長條順序與加總不對讓人分心。

### 7. 可疑的錯字或多餘文字
- 長條三段加總 6.04 ≠ 6.20。
- 「locks and the job ring: under 0.2 µs」的位置讓它看起來屬於 LZ4 HW。

---

## 第 11 張：Many Cores Fault at Once

### 1. 人物與機器
- 三個人物，各有名字與 core：Core 0 的 UI（戴帽子拿筆電）、Core 1 的 MEDIA（戴耳機）、Core 2 的 NET（頭上有天線）。是三個 user 程式，角色清楚。
- 第四列「LZ4 HW engines」，綠色 LZ4 HW 方塊加齒輪，兩條綠色長條「engine: job P」「engine: job Q」。
- 每一列有鎖頭方塊「lock」、虛線等待框、最後「XX runs again」。
- 下方三個說明框：The lock is short、Completions in any order、The slowest case seen（OPEN）。

### 2. 看不懂的線、表格、數字或物件
- 鎖頭只寫「lock」，沒寫 mm_lock。讀者要自己推「這就是第 8 張以前講的那把鎖」。「The lock is short」用單數 the lock，暗示只有一把，算有提示。
- 每個程式拿兩次 lock（等之前一次、等之後一次），第二次拿 lock 做什麼（填 page table、改 COT？）沒寫。
- **job P 比 job Q 長很多**（大約 2.3 倍），原因沒說。同樣是解壓縮一個 page，讀者會想：是 page 不同、壓縮率不同，還是兩個 engine 搶 DRAM？
- **叫醒的延遲畫得不一致**：MEDIA 的等待框在 job Q 結束後還延續約一格才拿 lock（看起來是叫醒的時間），UI 的等待框卻剛好在 job P 結束時就結束。
- 時間軸沒有單位，虛線格只是對齊用。
- 「The slowest case seen」講的「a fault on a page that is being compressed」在上面的時間線裡沒有畫，是另一個情境；「two fixes are still open」沒有說是哪兩個 fix。

### 3. 新手卡住的地方
- 「tag」：each thread finds its own completion by its tag，tag 是什麼、誰給的，沒有介紹。
- 「completion」：同第 10 張。
- 「DECOMPRESSING」：大寫看起來是 page 的狀態名稱，可以從上下文猜，但沒有說這個狀態記在哪裡（COT？）。
- 「more engines do not help」：為什麼？因為等的是 kernel 自己送出的 COMPRESS，這個推理沒寫出來。

### 4. 圖說的一句話
三個 core 同時 fault，鎖只在改表的時候輪流拿；不同 page 的解壓縮同時在不同 engine 上跑，同一個 page 只送一個 job，第二個 fault 跟著等。

### 5. Key point 與畫面
**一致。** 「Faults on different pages run side by side and share the LZ4 HW's engines」對應 job P 與 job Q 重疊；「Faults on the same page share one job」對應 NET 的「no second job」；「Only the short table updates take turns」對應鎖頭方塊錯開。小意見：「share the engines」容易讀成搶同一個 engine，畫面上其實是各用一個。

### 6. 困惑指數：2
時間線畫得清楚，角色有名字；只有 tag、第二次拿鎖的用途、slowest case 的兩個 fix 沒交代。

### 7. 可疑的錯字或多餘文字
- 沒有錯字。UI 與 MEDIA 叫醒延遲畫法不一致。

### 特別題：mm_lock 有沒有在同一時間被兩個 core 拿著？
**沒有。** 照虛線格看，六個鎖頭方塊各佔一格，彼此不重疊：
- Core 0 第一次（最左格）→ Core 1 第一次（下一格）→ Core 2 第一次（再下一格）；
- 後半段 Core 1 第二次 → Core 0 第二次 → Core 2 第二次，也都在不同格。
- job P 結束時 UI 與 NET 同時被放行，UI 先拿鎖，NET 等 UI 放鎖之後才拿，這正好畫出「輪流」。

### 特別題：job P 與 job Q 的關係
- job P 是 UI 在 Core 0 送出的解壓縮 job，job Q 是 MEDIA 在 Core 1 送出的，兩個是不同 page 的 job，在兩個不同的 engine 上**同時**跑（時間重疊）。
- job Q 比 job P 晚開始但先結束，所以 MEDIA 比 UI 先恢復，這就是「Completions in any order」。
- NET 也要 page P，發現 P 已經在 DECOMPRESSING，就不送第二個 job，等 job P 的結果。所以 job P 被 UI 與 NET 兩個 fault 共用。

---

## 第 12 張：Where It Goes Wrong If You Are Careless

### 1. 人物與機器
- 沒有人物，也沒有圖，六個純文字框，每框一個 Risk 與一個 Rule。
- 規則是誰做的，大部分沒寫：「write back before COMPRESS」「clear the page from every core's TLB」「pin the page」是 kernel？reclaimer？只有第 3 框寫了 reclaimer、第 5 框寫了 kernel、第 6 框寫了 mm_lock 與 HW。**角色不清。**

### 2. 看不懂的線、表格、數字或物件
- **A page pushed out too soon**：「the same instruction faults again and again」為什麼會發生？（我猜是一條指令同時碰兩個 page，處理一個 fault 時把另一個趕出去，形成循環。）圖上沒解釋。「last faulted-in pages」是幾個？
- **A wrong answer from the LZ4 HW**：「a good page is thrown away」是什麼意思？「the kernel decodes the stream itself」是指 kernel 用軟體解壓縮來驗證，還是取代 HW？kernel 怎麼知道 HW 答錯？「three wrong answers in a row」的 3 從哪來？
- **A fault where nobody may wait**：「keep it outside」是放在哪個範圍之外？
- **Stale cache lines**：「write back」「drop old lines」需要知道 LZ4 HW 不經過 CPU cache（non-coherent），框裡的 Risk 一行有講，但新手仍不知道 write back 與 drop 是哪兩個 cache 指令。
- 副標說「Each of these was found or confirmed in the simulations」，但沒有說哪一條是哪一種模擬找到的。

### 3. 新手卡住的地方
- **HRT**（hard real-time）沒有展開。
- **pin**（把 page 釘在 frame 裡不讓趕出）沒有解釋。
- **stream**（壓縮後的資料流）沒有解釋。
- 為什麼 interrupt handler、拿著 lock 的程式「不能等」：需要知道這些情境不能 sleep。
- cache coherence：CPU cache 與 DRAM 內容不同的概念。

### 4. 圖說的一句話
kernel 要遵守六條規則，否則 cache、TLB、reclaim 順序、不能等的程式、HW 出錯、兩個 job 同一個 frame 都會把資料弄壞。

### 5. Key point 與畫面
**部分一致。**
- 「Most of the care is about the LZ4 HW and the CPU seeing different copies of the same bytes」：六框裡只有 Stale cache lines 明確是這件事，TLB 那框勉強算（舊 mapping），Two jobs on one frame 算 HW 之間的衝突。page pushed out too soon、nobody may wait、wrong answer 都不是「不同副本」的問題。「Most」說得太滿。
- 「the HW is kept simple and checks nothing」對應第 6 框，但第 5 框是 HW 會答錯，Key point 沒有提到。

### 6. 困惑指數：3
每一框單獨看大致懂，但好幾個 Risk 的因果沒寫，且 Key point 的總結和六框的分布對不上。

### 7. 可疑的錯字或多餘文字
- 沒有明顯錯字。「the kernel decodes the stream itself」語意含糊。

---

## 第 13 張：What Is Designed, What Is Open

### 1. 人物與機器
- 沒有人物。左邊勾選清單「In the current design」五項；右邊「Open」表格八列，欄位 question / why it matters / needs。
- 不需要角色，這張是總表。

### 2. 看不懂的線、表格、數字或物件
- **a page that does not fit in 7 chunks**：7 從哪來？前面沒講 chunk 的大小與一個 page 最多幾個 chunk。「it pins a frame forever」是說這個 page 只能一直不壓縮留在 frame 裡？
- **who records that a page was used → the CPU manual**：為什麼要查 CPU 手冊？要知道 CPU 有沒有 hardware accessed bit，圖上沒講。
- **the clock needs it**：clock（演算法）沒有介紹。
- **after the LZ4 HW is switched off**：為什麼會被關掉？應該是第 12 張「three wrong answers in a row, stop using the HW」，但沒有接起來。「read-write pages can no longer leave」的 leave 是離開 frame（被壓縮）的意思，要猜。
- **needs 欄**：「a decision」與「a product decision」差別是什麼（工程決定 vs 產品決定？），沒說。
- **左邊「the kernel's own decoder as a second opinion」**：和第 12 張「the kernel decodes the stream itself」用語不同，second opinion 讀成「驗證」，第 12 張讀起來像「取代」。
- 第 11 張 OPEN 的「fault on a page being compressed; two fixes are still open」**不在**這張的 Open 表格裡。

### 3. 新手卡住的地方
- 7 chunks 的來源。
- clock 演算法。
- 為什麼記錄 page 有沒有被用過要看 CPU 手冊（硬體 accessed bit）。
- LZ4 HW 為什麼會被關掉。
- HRT（第 12 張也沒解釋）。

### 4. 圖說的一句話
目前的設計定了五件事（水位、背景壓縮、在 fault 的 core 解壓縮、一把短鎖、kernel 自己的解碼器），還有八個問題要等產品決定、CPU 手冊或實測資料。

### 5. Key point 與畫面
**一致（小保留）。** 「What is open is mostly policy: what to do when memory runs out, which pages to pick, how long a fault may take」對應 frames and chunks both full、how to pick cold pages、direct reclaim / sleep or poll。保留：「checked in simulation」在左欄沒有任何標示；「who records that a page was used」需要的是 CPU 手冊，是平台事實，不是 policy。

### 6. 困惑指數：3
表格結構清楚，但八列中有四列的詞（7 chunks、clock、CPU manual、switched off / leave）前面沒鋪陳。

### 7. 可疑的錯字或多餘文字
- 「a decision」與「a product decision」並列但沒說差別。
- 漏列第 11 張的 OPEN 項。

---

## 跨圖觀察

### 故事線順不順
大致順：第 9 張「壓縮不要放在 fault 裡」→ 第 10 張「fault 裡等 HW 的方式」→ 第 11 張「好幾個 core 一起 fault」→ 第 12 張「容易出錯的地方」→ 第 13 張「總結：定了什麼、還開著什麼」。從單一 fault 的時間，到多 core 並行，再到正確性與總表，層次清楚。

斷掉的地方：
1. **第 9 與第 10 張的數字沒接起來**：第 9 張 normal load 的 99% 是 6.98 µs，第 10 張 median 是 6.20 µs（sleep 方案）。讀者會想第 9 張的模擬用的是 sleep 還是 poll，圖上沒說。
2. **第 11 張的 slowest case 突然冒出來**：時間線畫的是解壓縮的並行，下面卻講「page 正在被壓縮」的情境，而且這個 OPEN 到第 13 張就不見了。
3. **第 12 張「stop using the HW」與第 13 張「after the LZ4 HW is switched off」沒有明連**。
4. **第 12 張是純文字**，和前面三張有圖、有時間線的風格差很多，節奏在這裡掉下來。
5. engine 的數量在第 9 張以小字出現（four LZ4 engines），第 11 張只畫兩條；讀者可能以為只有兩個 engine。

### 用我自己的話說這 5 張的結論
fault 只做解壓縮，壓縮全部交給背景的 reclaimer，靠一批預留的 free frame 讓 fault 不用等；負載太重時 fault 還是會等 frame，要不要讓 fault 自己壓縮還沒決定。一次 fault 裡最花時間的是「HW 做完之後通知並叫醒 thread」，不是 HW 本身，用 polling 可以快一倍但比較耗 CPU，也還沒決定。好幾個 core 同時 fault 時，只有改表那一小段要輪流拿那一把鎖，HW 做事時不拿鎖，不同 page 的 job 可以在不同 engine 上同時跑，同一個 page 只送一個 job。kernel 要負責 cache、TLB、不能等的程式、HW 出錯等正確性問題，HW 本身不檢查。結構已經定了，剩下的多半是策略：記憶體真的滿了怎麼辦、挑哪些 page 壓、fault 最久可以多久。

### 哪些 OPEN 看得懂為什麼還沒決定
- **看得懂**：
  - direct reclaim or not（第 9 張左右對比清楚：平均快但 worst case 難界定 vs. fault 不壓縮但要等 reclaimer）。
  - sleep or poll（第 10 張有數字：時間 vs CPU，而且叫醒時間是假設值）。
  - frames and chunks both full（要決定哪個程式收到錯誤，是產品問題）。
  - how to pick cold pages（需要真實的存取 trace）。
  - where the reclaimer runs, at what priority（不能干擾 HRT，雖然 HRT 沒解釋）。
- **看不懂**：
  - 第 11 張 slowest case 的「two fixes」：不知道是哪兩個 fix。
  - a page that does not fit in 7 chunks：不知道 7 怎麼來，也不知道有哪些選項。
  - who records that a page was used：不知道為什麼答案在 CPU 手冊裡。
  - after the LZ4 HW is switched off：不知道為什麼會關掉、關掉後有哪些選項。

### 總表

| 張 | 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|---|
| 9 Keep Compression Off the Fault | 3 | 是 | 一致 |
| 10 How to Wait for the LZ4 HW | 2 | 是（notify / wake 的發起者與對象沒畫） | 一致 |
| 11 Many Cores Fault at Once | 2 | 是 | 一致 |
| 12 Where It Goes Wrong | 3 | 否 | 部分一致 |
| 13 Designed and Open | 3 | 是 | 一致（小保留） |

### 建議重生
- **第 9 張**（困惑指數 3）：表格要說明 load 是什麼的倍數、faults that waited 的分母（或改成比例）、slowest one in a hundred 量的是 fault 從哪裡到哪裡；左右兩邊 page / frame、above / up to 統一；去掉中上方的多餘小點。
- **第 12 張**（困惑指數 3、角色不清、部分一致）：每條 Rule 寫出是誰做的（kernel / reclaimer / fault 路徑）；補上 page pushed out too soon 的因果、HW 答錯時 kernel 怎麼發現；展開 HRT、pin；Key point 改成和六框分布相符（例如「一半是 HW 與 CPU 看到不同副本，另一半是 reclaim 的順序與不能等的程式」），並提到 HW 可能答錯。可以考慮每框加一個小圖，與前幾張的視覺節奏一致。
- **第 13 張**（困惑指數 3）：7 chunks、clock、CPU manual、switched off / leave 要嘛加一句說明、要嘛改用前面圖已經講過的詞；把第 11 張的「fault on a page being compressed」加進 Open 表；說明 a decision 與 a product decision 的差別；「second opinion」與第 12 張的說法統一。

不必重生但建議小修：
- **第 10 張**：長條三段加總 6.04 對不上 6.20，把「locks and the job ring」畫成一段或改標題數字；註明長條不是時間順序（或改成時間順序：LZ4 HW → notify and wake up → kernel instructions）；說明 kernel CPU time 的百分比基準。
- **第 11 張**：鎖頭標 mm_lock；UI 與 MEDIA 的叫醒延遲畫法一致；slowest case 寫出兩個 fix 或指向別處。

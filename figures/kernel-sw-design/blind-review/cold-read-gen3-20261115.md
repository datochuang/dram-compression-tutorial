# 冷讀驗收報告：kernel-sw-design 第三輪

- 日期：2026-11-15
- 方法：只給圖、不給提示詞的冷讀
- 範圍：kernel-sw-design 第三輪的第 3、9、12、13 張。第 2 張只當脈絡，不打分。

讀圖順序：02-pages-and-frames.png（脈絡）、gen3/03-page-swap.r2.png、gen3/09-keeping-faults-short.png、gen3/12-where-it-goes-wrong.png、gen3/13-designed-and-open.png。

---

## 第 2 張（只當脈絡）

讀完知道：程式看到 page，DRAM 放 frame；TLB miss 一律進 kernel SW 的 TLB miss handler，由它讀 PTE 並填 TLB；PTE 無效就是 page fault，kernel 把 page 搬進 frame 後重跑 load。紫色虛線框代表 kernel SW。這個慣例帶到後面幾張。

---

## 第 3 張：Page Swap, and the Case We Build

註：讀 Key point 之前，眼睛掃到底部的位置時已經看到一部分，以下第 1 到第 4 項盡量照只看畫面的理解寫。

### 1. 人物與機器

- NET：戴天線的小人，坐在筆電前。是一支程式（「網路」那支）。左右兩邊各一個，代表同一支程式在兩種做法裡。
- kernel SW（紫色虛線框）：左邊「挑冷的 page，搬出去再搬回來」；右邊「挑冷的 page，交給 LZ4 HW 一個 job」。
- DRAM: frames：放 page 的格子。
- disk：左邊的圓柱，標「the usual destination」，一般 swap 的去處。
- LZ4 HW（綠色、有齒輪）：照要求壓縮與解壓縮。
- DRAM: compressed space：斜線格子，大小不一，代表壓縮後的 page。

角色全部有標籤，看得懂。

### 2. 看不懂的線、箭頭、表格、數字或物件

- 右邊四條綠色箭頭只有兩條有字：上左「page out: COMPRESS」、下右「page back in: DECOMPRESS」。另外兩條（下左、上右）沒字，要自己推它們是同一趟的後半段。推得出來，但第一眼會停一下。
- 「a job」只有一支箭頭，從 kernel SW 指向 LZ4 HW。看不出這個 job 是 fault 引發的 DECOMPRESS，還是 kernel 平常挑冷 page 時發的 COMPRESS，或兩種都有。
- 斜線格子的意思（壓縮過）圖上沒有圖例。格子大小不一，配合「at a size nobody knows in advance」可以猜到。
- 左邊 page out / page back in 的箭頭沒有標是誰在搬（kernel 自己、還是 DMA）。不影響理解。
- 「DRAM: frames」與「DRAM: compressed space」畫成兩個分開的框，新手可能以為是兩塊不同的記憶體；副標題有說都在 DRAM 裡，可以化解。

### 3. 新手卡住的地方

- fault 之後到 NET 繼續跑之間的順序沒有畫出來。NET 的 fault 箭頭指向 kernel SW 之後就斷了，沒有「解壓縮回 frame、改 PTE、NET 的 load 重跑」這一段。要靠第 2 張的「then MEDIA's load runs again」補。

### 4. 圖說的一句話

一般的 page swap 把冷 page 搬到 disk；我們改成由 kernel 指揮 LZ4 HW，把冷 page 壓縮後放在同一塊 DRAM 的另一個區域，碰到時再解壓縮回來。

### 5. 畫面與 Key point

一致。Key point 說「compression 就是換了目的地的 page swap：目的地是同一塊 DRAM 裡的 compressed space，由 LZ4 HW 照 kernel 的要求放進與取出」，左右對照的畫面正是這件事。

### 6. 困惑指數：2

左右對照很清楚；只有「fault 之後依序發生什麼」與兩條沒字的綠箭頭要自己補。

### 7. 可疑的錯字或多餘文字

- 「the PTE of a page that left says not valid」：「a page that left」讀起來有點怪，意思是「被搬出去的 page」。
- 沒有看到錯字。

### 第 3 張專題：NET 能不能直接讀到壓縮過的資料？碰到之後依序發生什麼？

- 不能。NET 唯一的箭頭是「touches a compressed page: page fault」，指向 kernel SW；NET 和 compressed space 之間沒有任何線。圖上沒有一句話直接說「程式不能讀壓縮過的資料」，是從「碰到就 fault」推出來的。
- 從圖上讀出的順序：
  1. NET 碰到一個壓縮過的 page，發生 page fault。
  2. 進到 kernel SW。
  3. kernel SW 交給 LZ4 HW 一個 job（應該是 DECOMPRESS，但「a job」箭頭沒寫是哪種）。
  4. LZ4 HW 從 compressed space 讀壓縮的資料，解壓縮後寫回 DRAM 的一個 frame（下排兩條綠色箭頭，往左）。
  5. （圖上沒畫）PTE 改成 valid、NET 的那次存取重跑。這一步要靠第 2 張補。

---

## 第 9 張：Design Choice: Keep Compression Off the Fault

### 1. 人物與機器

- 沒有人物、沒有機器。全部是文字方塊與表格。
- 左「A common general-purpose kernel」：background reclaim thread（虛線紫框）、direct reclaim（虛線紫框）。
- 右「Ours」：reclaimer thread（虛線紫框）、no direct reclaim（實線黑框）。
- 「OPEN」標籤，下面寫「direct reclaim or not」。
- 下方表格：Simulated: the four programs at five loads。
- 右下「Two knobs」。

方塊的角色大致清楚。疑點：「no direct reclaim」是唯一的實線黑框，和其他紫色虛線框不同，看不出這個差別是刻意的（「這不是一段 kernel 程式」？）還是隨手。

### 2. 看不懂的線、箭頭、表格、數字或物件

- 「no direct reclaim」旁邊掛「OPEN: direct reclaim or not」。標題是「Design Choice」，框裡寫「no direct reclaim」，旁邊又說還沒決定。到底選了沒有，看不出來。
- 表格沒有寫是哪一種設計的數字。照位置猜是「Ours」，但左邊的 general-purpose kernel 沒有任何數字可以對照，所以「Keep Compression Off the Fault 比較好」在數字上看不出來。
- 「faults that waited for a frame」：0、0、10、178、716，沒有分母。不知道總共有幾次 fault、模擬跑了多久，716 是多還是少無法判斷。
- 「fault time, slowest in a hundred」：要想一下才知道是 p99。
- 「most-stalled program: share of time waiting」：等的是什麼（等 frame？等整個 fault？），是哪一支程式，都沒寫。
- load 的定義「each program does 20 µs of its own work between page accesses」：「page accesses」是每一次存取 page，還是每一次 fault（碰到壓縮過的 page）？照字面是前者，那 20 µs 才存取一次記憶體很不合理，所以應該是後者，但字面沒說。
- 10 倍負載時有 10 次 fault 等了 frame，但最慢的 fault 只有 14.94 µs，和 4 倍的 12.05 µs 差不多。讀者會疑惑「等 frame」為什麼這麼短。
- 「Two knobs」和表格沒有連結：表格裡兩個 knob 都沒有變，看不到轉它們會怎樣。
- 「high watermark」在這張沒有定義（前面的圖介紹過，可接受）。

### 3. 新手卡住的地方

- 「no direct reclaim」與「OPEN: direct reclaim or not」互相矛盾，不知道這是已經決定的設計還是還沒決定。
- 表格不知道是哪一個設計的結果，也沒有左邊設計的對照，讀者無法從數字確認這個 design choice 比較好。
- load 定義的「page accesses」意思不明，讀者無法把「4 times、10 times」對應到真實情況。

### 4. 圖說的一句話

一般 kernel 在 reclaim 跟不上時會讓 fault 的那個 thread 自己壓縮 page，我們改成所有壓縮都交給背景的 reclaimer，fault 只解壓縮；模擬顯示正常與 4 倍負載下沒有 fault 等 frame，10 倍以上開始等，最慢的時間也跟著變長。

### 5. 畫面與 Key point

部分一致。

- 一致：Key point「正常負載下 fault 從不等 frame，重負載時會」與表格（normal 和 4 times 都是 0，之後增加）相符。
- 不一致：Key point 說還沒決定的是「how to bound that wait」，畫面上的 OPEN 標籤寫的是「direct reclaim or not」。兩者有關（direct reclaim 是限制等待的一種方法），但畫面沒有把這層關係講出來；同時畫面的「no direct reclaim」框又像是已經決定，與 Key point「still open」的語氣衝突。

### 6. 困惑指數：3

左右對照本身清楚，但「已選 / 還沒決定」互相矛盾，表格不知道屬於哪個設計、沒有分母、load 定義模糊。

### 7. 可疑的錯字或多餘文字

- 「OPEN / direct reclaim or not」放在「no direct reclaim」旁邊，像是互相打架的文字。
- 「fault time, slowest in a hundred」用語彆扭（p99）。
- 副標題「until the  load」中間像有多一個空格（只是排版，不確定）。
- 沒有看到錯字。

---

## 第 12 張：Where It Goes Wrong If You Are Careless

### 1. 人物與機器

- 沒有人物。六張卡片，每張有一個小圖示、標題、Risk、Rule，底部一行藍字。
  - cache 疊在 DRAM 上的圖示：Stale cache lines。清楚。
  - 四格方格、右上一格打叉：A TLB that still points at the frame。打叉的那格是「失效的 entry」還是「要清掉的 entry」，看不出來。
  - page 加箭頭：A page pushed out too soon。清楚。
  - 被劃掉的時鐘：A fault where nobody may wait。清楚。
  - 齒輪加問號：A wrong answer from the LZ4 HW。清楚。
  - 兩支箭頭指向一個方塊：Two jobs on one frame。清楚。
- 每張卡底部的藍字（「the kernel」、「the kernel, and whoever writes that code」）沒有欄位名稱。猜得出是「誰負責遵守這條規則」，但圖上沒說。

### 2. 看不懂的線、箭頭、表格、數字或物件

- 卡片底部藍字的意思（負責人？發生在哪裡？）沒有標。
- 卡 2 的圖示打叉的格子意義不明。
- 卡 3「the page leaves before the instruction that needed it runs」：為什麼 page 會在指令重跑前就被趕走？需要知道「一條指令可能碰到兩個 page，free frame 很少時剛搬回的 page 會被下一次 fault 擠掉」，圖上沒講。「each thread's last faulted-in pages」是最後幾個？
- 卡 5 標題是「A wrong answer from the LZ4 HW」，但 Risk 只寫「HW 把好的 stream 報成壞的」（誤報）。HW 把壞的報成好的、或解出錯的資料而沒報錯，這兩種「wrong answer」沒有提。標題比內容寬。
- 卡 5「after three wrong answers in a row, stop using the HW」：停用之後怎麼辦？推得出是改用 kernel 自己的 decoder，但壓縮怎麼辦沒說（第 13 張才回答）。
- 卡 4「code holding a lock」：任何 lock 嗎？fault 路徑本身也拿 mm_lock，新手可能想問兩者的關係，但不至於卡住。

### 3. 新手卡住的地方

- 卡 3：看不懂 page 為什麼會在需要它的指令跑之前就被推出去，所以也看不懂規則為什麼是「跳過最近 fault 進來的 page」。

### 4. 圖說的一句話

kernel 不小心時會在六個地方弄壞資料（cache 不一致、舊的 TLB、剛搬回的 page 又被趕走、不能睡的程式碰到壓縮的 page、HW 誤報、兩個 job 寫同一格），每一個都有便宜的規則可以防，而且幾乎都是 kernel 的責任。

### 5. 畫面與 Key point

部分一致。

- 一致：「keeps the CPU and the HW from seeing different copies」對卡 1；「protects pages that just came back」對卡 3；「double-checks the HW's failures」對卡 5；「code that must not wait stays away from compressed memory」對卡 4；「The LZ4 HW checks nothing」對卡 6 的「the HW does not check」。
- 不一致：
  - 「The LZ4 HW checks nothing」和卡 5「the HW reports that a good stream is broken」放在一起讀會打架：HW 會回報 stream 壞掉，表示它至少檢查了 stream。應該是「HW 不檢查 kernel 給的 frame 與 chunk 的範圍」，但 Key point 說成了全部。
  - 卡 2（TLB 還指著舊 frame）在 Key point 裡沒有對應的句子。

### 6. 困惑指數：2

六張卡片格式一致、各自獨立，大部分一讀就懂；卡 3 的「為什麼」與卡 5 的標題範圍要多想。

### 7. 可疑的錯字或多餘文字

- 卡 5 標題「A wrong answer from the LZ4 HW」與內容（只有誤報）不符。
- 沒有看到錯字。

---

## 第 13 張：What Is Designed, What Is Open

### 1. 人物與機器

- 沒有人物、沒有機器。左邊是勾選清單「In the current design」（五項），右邊是表格「Open」（question / why it matters / needs，九列），底部有 design decision 與 product decision 的說明。角色清楚。

### 2. 看不懂的線、箭頭、表格、數字或物件

- 「a page that needs more than 7 chunks — today it keeps its frame forever」：「forever」很重。之後內容變了、變得壓縮得動，也不會再試嗎？讀者會懷疑字面。
- 「frames and chunks both full — which program gets the error」：什麼 error？應該是記憶體不夠時有程式要被拒絕或殺掉，沒有寫。
- 「sleep or poll for the LZ4 HW — time against CPU」：太簡短，看過第 10 張才懂（等的時間 vs. 佔用的 CPU）。
- 「after the kernel stops using a faulty LZ4 HW — read-write pages can no longer be compressed」：為什麼只說 read-write？read-only 的 page 怎麼辦？也要先知道「kernel 只有 decoder、沒有 encoder」才能懂這列，這件事圖上沒說。
- 左邊「decompressing on the core that faulted, several at once」的「several at once」是幾個 core 同時解壓縮，看過第 11 張才懂。

### 3. 新手卡住的地方

- 最後一列：不知道為什麼停用 LZ4 HW 之後「read-write」的 page 就不能壓縮，因為圖上沒交代 kernel 只有解壓縮的軟體備援、沒有壓縮的。

### 4. 圖說的一句話

五項機制已經在模擬中做好並檢查過但還沒簽核，另外有九個問題還沒決定，分別需要設計決定、產品決定、真實的存取 trace、CPU 手冊或實際量測。

### 5. 畫面與 Key point

一致。Key point「structure 在模擬中做好、檢查過，但還沒簽核」對應左邊的藍字；「open 的大多是 policy：記憶體用完怎麼辦、挑哪些 page、fault 可以多久」分別對應「frames and chunks both full」、「how to pick cold pages / who sets the used mark」、「sleep or poll / direct reclaim / a fault on a page being compressed」。7 chunks、reclaimer 的 priority、faulty HW 三列不算 policy，但 Key point 用的是「mostly」，不衝突。

### 6. 困惑指數：2

表格清楚，欄位有說明；少數幾列的「why it matters」太簡短，要靠前面的圖。

### 7. 可疑的錯字或多餘文字

- 「time against CPU」過於簡略。
- 「keeps its frame forever」可能說過頭。
- 沒有看到錯字。

---

## 總表

| 張 | 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|---|
| 3 | 2 | 清楚 | 一致 |
| 9 | 3 | 大致清楚；「no direct reclaim」實線框與 OPEN 標籤互相矛盾 | 部分一致 |
| 12 | 2 | 清楚；卡片底部藍字沒有欄位名稱 | 部分一致 |
| 13 | 2 | 清楚 | 一致 |

## 我用自己的話講的結論

這個設計把很久沒用的 page 用 LZ4 HW 壓縮後留在同一塊 DRAM 裡，本質上是一種 page swap，只是目的地換了。程式碰不到壓縮的資料，一碰就 page fault，由 kernel 叫 LZ4 HW 解壓縮回 frame。為了讓 fault 短，所有壓縮都交給背景的 reclaimer，fault 只做解壓縮；在模擬裡正常到 4 倍負載時沒有 fault 需要等 frame，10 倍以上開始等，要不要讓 fault 自己壓縮（direct reclaim）來限制等待還沒決定。LZ4 HW 只照指示做事、不檢查範圍，所以 cache 一致性、TLB 清除、剛搬回的 page 不被趕走、不能睡的程式碼遠離壓縮的記憶體、HW 誤報、同一格不能有兩個 job，全都要 kernel 守住。結構已經在模擬裡做好，還沒簽核；剩下的大多是 policy 問題，例如記憶體用完怎麼辦、怎麼挑冷 page、fault 最多可以多久。

## 建議重生

- **第 9 張（必要）**：困惑指數 3、畫面與結論部分一致。要處理：
  - 「no direct reclaim」與「OPEN: direct reclaim or not」二擇一，或寫成「目前：no direct reclaim（暫定）」。
  - 表格標明是「Ours」的數字。
  - 「faults that waited」給分母（總 fault 數），或改成比例。
  - load 定義的「page accesses」改成明確的事件（例如每次碰到壓縮的 page）。
  - 讓 OPEN 標籤與 Key point 講同一個未決問題。
- **第 12 張（輕修，可只改文字）**：畫面與結論部分一致。要處理：
  - Key point 的「The LZ4 HW checks nothing」改成限定範圍的說法（例如不檢查 frame 與 chunk 的範圍），避免和卡 5 的「HW reports a broken stream」打架。
  - 卡 5 的標題縮小到「false broken-stream report」，或在 Risk 補上另一種錯法。
  - 卡 3 補半句「為什麼」。
  - 卡片底部藍字加上「who:」之類的欄位名稱。

第 3、13 張不需要重生。

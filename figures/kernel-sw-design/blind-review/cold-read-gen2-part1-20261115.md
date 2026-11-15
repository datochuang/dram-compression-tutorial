# kernel-sw-design 第二輪冷讀驗收（第 2 到 5 張）

- 日期：2026-11-15
- 方法：只給圖、不給提示詞的冷讀。讀者只讀了 PNG，沒有讀任何 prompts、說明文字或其他資料夾。
- 範圍：kernel-sw-design 第二輪的第 2 到 5 張。第 1 張只當脈絡，不打分。
  - `gen2/02-pages-and-frames.r3.png`
  - `gen2/03-page-swap.png`
  - `gen2/04-how-a-page-is-stored.r3.png`
  - `gen2/05-parts-of-the-kernel-sw.png`

## 第 1 張的脈絡（不打分）

四個程式（UI、MEDIA、NET、LOG）各自要記憶體。DRAM 容量固定，沒壓縮時每個 page 都佔一整個 frame，DRAM 就滿了。大部分 page 是 cold，壓縮後放進 DRAM 裡的 compressed space，大小不一（1.3 KB、2.9 KB、2.1 KB），空出位置。cold page 再被碰到時解壓縮回 frame。HRT thread 的記憶體與 kernel 自己的 code 和表永遠不壓縮。讀完知道：page 是 4 KB、frame 是放 page 的位置、壓縮換來容量但碰到 cold page 時要等一下。

---

## 第 2 張：Pages, Frames and the CPU MMU

### 1. 人物與機器

- **MEDIA**（戴耳機的人）：一個程式。左邊三張紙是「MEDIA 看到的 page A、B、C，並排」。它在意的是 load 能拿到資料。
- **Core 0** 大框：一顆 CPU core。裡面有：
  - **CPU MMU and TLB**（藍色實線框）：硬體。收到 MEDIA 的 load，TLB hit 時直接去 DRAM 的 frame 5。
  - **TLB miss handler**（紫色虛線框，「kernel SW, runs on this core」）：軟體，TLB miss 時被叫起來，去 DRAM 讀 PTE，再把結果填回 TLB。
- **DRAM** 大框：上面一排 frame（frame 2 放一個 page、frame 5 放一個 page，其餘空），下面是 page table，每個 page 一個 PTE：A 在 frame 5、B 在 frame 2、C not valid。
- **page fault**（紫色虛線框）：PTE not valid 時發生的事，「kernel 把 page C 帶進一個 frame，再讓 MEDIA 的 load 重跑」。框的樣式和 TLB miss handler 一樣，讀起來像也是一段 kernel SW，但沒寫在哪裡跑。
- **On this chip**：說明這顆 chip 的 CPU MMU 自己不讀 page table，每次 TLB miss 都進 kernel SW。
- **New words**：page、frame、PTE、TLB 的定義。

角色清楚。唯一稍弱的是 page fault 框：它是事件還是一段程式，以及「the kernel」是不是同一個 TLB miss handler，圖上沒交代。

### 2. 看不懂的線或物件

- 「every core has」「its own TLB」這句被往下的紫色箭頭（PTE not valid）從中間切開，左右兩半像兩個標籤，第一眼會以為是箭頭的說明。
- 頁首副標題右端有一條孤立的藍色直線，看不出意義。
- 往 page fault 的箭頭從 TLB miss handler 出來，邏輯通，但沒有畫出 page fault 處理完之後回到哪裡（文字有說 load 重跑，畫面沒有）。

### 3. 新手卡住的地方

- **CPU MMU** 這個詞在標題和主框都出現，但 New words 沒有它，全圖也沒說 MMU 是什麼的縮寫或它整體負責什麼。讀者只能從「finds the frame」推測。
- **page C「in no frame」那它在哪裡？** 圖說 kernel 會把它帶進 frame，但沒說從哪裡帶來。新手會卡在「page 不在 DRAM 裡，那資料存在哪」。第 3 張才回答，這裡沒有往前指。

### 4. 圖說的一句話

程式只看到自己的 page，每次 load 由 CPU MMU 的 TLB 找到 frame；TLB 沒有時 kernel SW 去讀 DRAM 裡的 page table 補上，page 不在任何 frame 時就是 page fault，要 kernel 處理。

### 5. 和 Key point 是否一致

**一致。** Key point 的四件事（程式看 page、DRAM 放 frame、page table 對應、TLB cache 它、不在 frame 就 page fault）畫面都有。

### 6. 困惑指數

**2**。主線很清楚，只有 CPU MMU 未定義、page C 去哪了沒交代。

### 7. 可疑的錯字或多餘文字

- 副標題右端的孤立直線。
- 「every core has / its own TLB」被箭頭切成兩段。

---

## 第 3 張：Page Swap, and the Case We Build

### 1. 人物與機器

- 左格「Page swap as it is usually done」：
  - **NET**（頭上有天線的人）：程式，碰到一個已經被 page out 的 page。
  - **kernel SW**（紫色虛線框）：挑 cold page，搬出去再搬回來。框沒有連到任何箭頭。
  - **DRAM: frames** 與 **disk**（圓柱）：page out 從 frames 到 disk，page back in 在 page fault 時從 disk 回來。
- 右格「What we build」：
  - **NET**：碰到一個 compressed page。
  - **kernel SW**：挑 cold page，交給 LZ4 HW 一個 job。
  - **DRAM**：左半 frames（hot pages），右半 compressed space（cold pages，斜線、大小不一）。
  - **LZ4 HW**（綠框、齒輪）：照要求壓縮與解壓縮。
- 下方三張便條：What stays the same、What is new、New words。

角色都有標籤，看得出誰是誰。

### 2. 看不懂的線或物件

- **右格 NET 的橘色箭頭直接指到 compressed space 裡的斜線 page。** 讀起來像程式直接去讀壓縮後的資料。這和第 2 張「page 不在 frame 就 page fault，kernel 處理」的邏輯不合，也和第 1 張「cold page 被碰到會先解壓縮回 frame」不合。左格的 NET 箭頭反而指向 frames。兩格的同一個動作指向不同地方，新手會以為兩種做法的存取方式不同。
- **兩支綠色箭頭都從 LZ4 HW 往上**：「page back in: DECOMPRESS」指到 frames，「page out: COMPRESS」指到 compressed space。只畫了輸出那一端，沒畫資料從哪裡進 LZ4 HW。新手會問：COMPRESS 的資料是從 frame 來的嗎？DECOMPRESS 的資料是從 compressed space 來的嗎？畫面沒說。
- 右格的 page fault 沒出現。「What stays the same」說 page fault 還在，但畫面上看不到 NET 碰到 compressed page 之後經過 page fault、kernel 才派 job 的這一段。
- 左格 kernel SW 框沒有連線，page out 與 page back in 的箭頭看不出是誰做的。

### 3. 新手卡住的地方

- **NET 能不能直接讀 compressed space？** 畫面的箭頭說能，便條說 page fault 還在。新手會在這裡建立錯的模型。
- **job** 只在右格出現一次，New words 說 COMPRESS、DECOMPRESS 是「the two jobs」，勉強夠用，不算卡住。

### 4. 圖說的一句話

一般的 page swap 把 cold page 搬到 disk，我們做的是讓 kernel 叫 LZ4 HW 把 cold page 壓縮後留在同一塊 DRAM 的另一區。

### 5. 和 Key point 是否一致

**部分一致。** Key point 說 compressed space 由 LZ4 HW 照 kernel 的要求填入與取出，這和 kernel SW → a job → LZ4 HW 一致。但畫面上 NET 的箭頭直接進 compressed space，看起來程式自己碰壓縮資料，沒有經過 kernel；綠色箭頭也沒畫出「取出」是從 compressed space 出來。

### 6. 困惑指數

**3**。大意懂，但 NET 的箭頭和只畫一半的綠箭頭會讓新手建立錯的資料流。

### 7. 可疑的錯字或多餘文字

沒看到錯字。

---

## 第 4 張：How a Compressed Page Is Stored

### 1. 人物與機器

- 沒有人物。上方三個 page：
  - **page P**：4 KB 壓到 1.3 KB，用 3 個 chunk。
  - **page Q**：4 KB 壓到 2.9 KB，用 6 個 chunk。
  - **page R**：壓到 3.9 KB，要 8 個 chunk，標 **OPEN**，「today it stays in its frame」。
- **chunk pool, in DRAM**：16 個 512 B 的 chunk。P 在 1、2、7，Q 在 3、4、5、6、9、10，7 與 10 只用了一部分，8 與 11 到 16 空著（虛線）。
- 綠色 COMPRESS 箭頭從 page P 分到 chunk 1、2、7。
- **COT（compressed object table）**：每個 page 一列，記 chunks、length、check（CRC）。
- **chunk bitmap**：每個 chunk 一個 bit，表上只列 1（yes）與 8（no）兩列當例子。
- **LZ4 HW**（綠框）：COMPRESS 把一個 frame 寫進給它的 chunks；DECOMPRESS 把給它的 chunks 寫回一個 frame。下方小字：kernel 挑 chunk、寫 COT，HW 不讀 COT。
- **Rules of the pool** 與 **New words**（stream、CRC、OPEN）。

角色清楚：誰挑 chunk（kernel）、誰搬 byte（LZ4 HW）有寫。

### 2. 看不懂的線或物件

- COMPRESS 箭頭從 page P 直接畫到 chunk，沒經過右下的 LZ4 HW。和 LZ4 HW 框裡的說明一起看能懂，但畫面上 LZ4 HW 是孤立的。
- chunk 7 與 10 左半斜線、右半白底寫字母，字母落在白色那一半，一瞬間像是「P 在沒用到的那一半」。
- chunk bitmap 只列兩列，讀者可能以為 bitmap 只記這兩個 chunk。可接受，但沒寫「節錄」。
- page Q 沒有箭頭，只有 P 有。可接受。

### 3. 新手卡住的地方

- **「read-only pages never change: their chunks always stay」**：stay 在哪裡、什麼時候？如果 read-only page 已經回到 frame，它的 chunks 還留著嗎？為什麼要留？圖上沒有解釋 read-only 與 read-write 的處理為什麼不同，這一條沒有背景的讀者會卡住。
- **OPEN 的定義與用法有點衝突**：New words 說 OPEN 是「not decided yet」，但 page R 旁邊又寫「today it stays in its frame」，看起來已經決定了。讀者會不確定 R 到底怎麼處理。

### 4. 圖說的一句話

壓縮後的 page 長度不一，kernel 把它切進幾個 512 B 的 chunk（不必相鄰），用 COT 記每個 page 在哪些 chunk、多長、CRC，用 bitmap 記哪些 chunk 空著；壓不下來的 page 留在 frame。

### 5. 和 Key point 是否一致

**一致。**

### 6. 困惑指數

**2**。資訊多但每一塊都有標籤，算術也對得上（1.3 KB 三個 chunk、2.9 KB 六個、3.9 KB 八個）。

### 7. 可疑的錯字或多餘文字

沒看到錯字。New words 的「stream」在畫面上沒用到，只在 Key point 出現，稍微多餘但無害。

---

## 第 5 張：The Parts of the LZ4 Kernel SW

### 1. 人物與機器

- **UI**：碰到一個 compressed page，橘色箭頭往下進 fault path。
- **MEDIA**：沒有箭頭，旁邊寫「大部分存取不會到 kernel，TLB 會 hit」。
- **fault path**（三層疊起來的紫色虛線框）：把 compressed page 拿回來；在 fault 的那個 core 上跑；由 TLB miss handler 呼叫；很多 core 可以同時在裡面。
- **kernel tables**（中間實線框）：page state、COT、free frames、chunk bitmap，上面一把鎖 **mm_lock**，「one lock guards all four」，下方「the lock is held for short steps only」。
- **reclaimer**（右邊紫色虛線框）：把 cold page 推出去；背景的 kernel thread；free frame 少時醒來；所有壓縮都由它做。
- **LZ4 HW**（綠框）：「several engines, shared by every core」；下方「no lock is held while the LZ4 HW works」。

角色清楚。

### 2. 看不懂的線或物件

- 「wake up: free frames are low」這條弧線從 fault path 出發到 reclaimer。看得懂是 fault path 叫醒 reclaimer，但為什麼是 fault path 發現 free frame 少（因為它要用一個 frame）沒寫，可以推得出來。
- 「lock, look up, unlock」與「lock, pick a page, unlock」箭頭都指向 kernel tables，像是去找一個服務。配上單一一個帶鎖的框，第一眼會以為 kernel tables 是一個會回應的東西，而不是一份資料。
- LZ4 HW 寫 several engines，但畫成一個框，沒有畫出幾個 engine。

### 3. 新手卡住的地方

- **page state**：前面四張沒出現過這張表。前面講的是 page table 與 PTE。新手會問 page state 是不是 page table？page table 為什麼不在 mm_lock 保護的四張表裡？fault path 把 page 拿回來之後要改 PTE，這件事在這張圖上找不到。
- **mm_lock / lock**：對一般軟體工程師大概不是障礙，不列為卡住。

### 4. 圖說的一句話

kernel SW 分成兩條路：在 fault 的 core 上把 page 拿回來（叫 LZ4 HW 做 DECOMPRESS），和一個背景 thread 把 cold page 推出去（叫 LZ4 HW 做 COMPRESS）；兩者共用一把鎖保護的四張表，鎖只在短步驟裡握著，LZ4 HW 工作時不握。

### 5. 和 Key point 是否一致

**一致。** Key point 的「在 fault 的 core 上拿回來」「一個背景 thread 推出去」「共用一組表一把鎖」「LZ4 HW 工作時不握鎖」畫面都有。

### 6. 困惑指數

**2**。結構清楚，主要問題是 page state 這個新名字和 page table 的關係沒交代。

### 7. 可疑的錯字或多餘文字

沒看到錯字。標題用「LZ4 Kernel SW」，前幾張都叫「kernel SW」，名字換了，但不至於誤會。

---

## 另外一題：拿回壓縮 page 的 kernel SW 在哪裡執行、同時幾份、有沒有像「只有一份、大家排隊」的畫法

- **在哪裡執行**：在發生 fault 的那個 core 上，由那個 core 的 TLB miss handler 呼叫（框內寫「runs on the core that faulted」「called from the TLB miss handler」）。
- **同時幾份**：圖上寫「many cores can be in it at once」，框畫成三層疊起來，所以是好幾份，最多大約每個 core 一份。同一個 core 上的兩個 hardware thread 能不能同時在裡面，圖沒有說（前面幾張也沒提過 hardware thread）。
- **會讓人以為只有一份、大家排隊的畫法**：
  - 疊起來的框只有一支往外的箭頭、一個名字「fault path」，副標題又說「two paths」，「path」這個詞本身容易被讀成一個東西。疊框有幫助，但不是很強烈。
  - 中間 kernel tables 只有一個框加一把鎖，兩邊箭頭都指向它，寫著 lock、unlock。第一眼像「大家輪流去找它」。這其實是對的（表的存取確實排隊），但新手可能把「表要排隊」誤讀成「整個 fault path 要排隊」。「the lock is held for short steps only」與「no lock is held while the LZ4 HW works」兩句小字有在修正這個印象，但字小。
  - LZ4 HW 畫成一個框，雖然寫 several engines，畫面上仍像一台機器大家排隊用。

整體來說：文字說得清楚是多份，畫面只有疊框一個視覺線索支持它，鎖與單一 LZ4 HW 框的畫法有一點點「單一窗口」的味道，但我不會因此誤讀成 fault path 只有一份。

---

## 總表

| 張 | 困惑指數 | 角色是否清楚 | 畫面與 Key point |
|---|---|---|---|
| 2 Pages, Frames and the CPU MMU | 2 | 是 | 一致 |
| 3 Page Swap, and the Case We Build | 3 | 是 | 部分一致 |
| 4 How a Compressed Page Is Stored | 2 | 是 | 一致 |
| 5 The Parts of the LZ4 Kernel SW | 2 | 是 | 一致 |

## 我的結論

這四張整體能讓沒有背景的工程師走完「page 與 frame → page fault → 壓縮就是換個目的地的 page swap → 壓縮後怎麼存 → kernel SW 分成哪幾塊」這條線，標籤齊全、每張都有 New words，數字算得通。最大的問題在第 3 張：右格 NET 的箭頭直接進 compressed space，綠色箭頭只畫輸出端，會讓讀者以為程式能直接碰壓縮資料，和第 2 張剛建立的 page fault 觀念打架。其次是名詞銜接：第 2 張沒定義 CPU MMU、page C 不在 frame 時在哪裡沒往後指；第 4 張 read-only page 的 chunks「always stay」沒有理由、OPEN 的定義與「today it stays in its frame」有衝突；第 5 張突然出現 page state，和 page table 的關係沒說。第 5 張對「fault path 有很多份、在 fault 的 core 上跑」的表達靠文字與疊框，夠用，但鎖與單一 LZ4 HW 框略帶「單一窗口」的味道。

## 建議重生

- **第 3 張**：困惑指數 3，畫面與 Key point 部分一致。要改的是右格 NET 的箭頭（應該先到 page fault／kernel，而不是直接進 compressed space），以及 COMPRESS、DECOMPRESS 的箭頭要畫出資料從哪裡進、到哪裡出。

第 2、4、5 張不需要重生，但建議小修文字：
- 第 2 張：New words 加 CPU MMU；page fault 框補一句 page C 現在在哪（或往第 3 張指）；把「every core has its own TLB」移開箭頭；去掉副標題右端的直線。
- 第 4 張：read-only 那條補一句為什麼 chunks 留著；OPEN 與「today it stays in its frame」二擇一或改寫成「暫時留在 frame，最終做法未定」。
- 第 5 張：說明 page state 與 page table／PTE 的關係。

# 冷讀驗收報告：system-overview gen3 第 3、4 張

- 日期：2026-11-13
- 方法：只給圖、不給提示詞的冷讀。讀者只拿到兩張 PNG 與幾句背景，沒有讀提示詞、規格或既有報告。
- 讀的是 gen3 的第 3、4 張：
  - `gen3/03-one-kernel-many-instances.png`
  - `gen3/04-one-lz4-hw-for-every-core.png`
- 每一張的第 1 到 3 題是在讀 Key point 之前回答的。

## 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|
| 3 One Kernel, Many Instances | 2 | 是 | 一致 |
| 4 One LZ4 HW, N Engines, Every Core | 3 | 是，`L1 and L2 caches` 那一角除外 | 一致，但「完成順序不定」只有文字，畫面沒有演出來 |

圖 4 的 3 是邊界值。主流程本身是 2，拉到 3 的是三個會讓人讀錯的地方：interrupt 只回到 Core 1、`page` 箭頭的上端指在一行註記上、左下角 cache 那一塊要自己推理由。

---

## 圖 3：One Kernel, Many Instances

### 1. 人物與機器

這張沒有人物，全部是方塊。

| 物件 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 紫色實線大方塊 | `kernel SW code: one copy in DRAM` | 一份程式碼，往下分出三條虛線，第一條標 `same code` | 程式碼只有一份 |
| 紫色虛線方塊，左 | `kernel SW instance`，Core 0, thread T0，own stack | 粗箭頭進到 `shared tables` 裡，標 `holds mm_lock: inside` | 它現在握著 lock |
| 紫色虛線方塊，中 | `kernel SW instance`，Core 0, thread T1，own stack | 虛線箭頭往下，停在一條橫槓，標 `waits outside for mm_lock` | 它被擋在外面 |
| 紫色虛線方塊，右 | `kernel SW instance`，Core 1, thread T0，own stack | 細箭頭指到 `LZ4 HW`，標 `waits for its job: holds no lock` | 它在等硬體，不占 lock |
| 灰色圓角框 | `shared tables`，右上角紅色鎖頭 `mm_lock` | 包住三張表 | 一次只能進一個 |
| 框內方塊 | `page table`：where each page is now | 被保護的資料 | |
| 框內方塊 | `kernel tables`：page states, free frames, free chunks | 被保護的資料 | |
| 框內方塊 | `COT: compressed object table`：where each compressed page is stored | 被保護的資料 | |
| 綠色方塊，有齒輪 | `LZ4 HW`：N engines, up to N jobs at once | 被右邊的 instance 等待 | 可以同時做 N 件 |
| 黃色便條 | `Bringing back a compressed page: mm_lock is taken twice`，三步 | 說明一次解壓縮的三段 | lock 在中間那段放開 |

沒有無標籤的物件。角色都看得出來。

### 2. 看不懂的線或物件

1. **便條的三步沒有對到三個 instance。** 便條說 1 握 lock 查表拿 frame、2 不握 lock 讓 LZ4 HW 解壓、3 再握 lock 做 map。畫面上三個 instance 看起來正好各在某一步，但圖上沒有編號。讀者要自己猜：Core 1 T0 是在第 2 步，Core 0 T0 是第 1 或第 3 步，Core 0 T1 是正要進第 1 步或第 3 步。
2. **右邊那條箭頭的方向與文字不合。** 箭頭從 instance 指向 `LZ4 HW`，像是送東西過去，文字卻是 `waits for its job`。另外「its job」第一眼可能被讀成「等別人派工作給它」，而不是「等它交出去的那件工作做完」。
3. **鎖頭、入口、被擋的位置三者不在一起。** 鎖頭在灰框右上角，握 lock 的粗箭頭從最左邊進去，被擋住的橫槓停在框的中間上方。看得懂意思，但第一眼不會把橫槓和鎖頭連起來。
4. **鎖頭是關著的，沒說關著代表什麼。** 是「現在被 T0 拿走」還是單純代表「這裡有一把 lock」，分不出來。
5. **`kernel tables` 這個名字太泛。** page table 與 COT 也是 kernel 的表，三格並排時中間這格像是「其他」。`free chunks` 的 chunk 在這張圖裡沒有解釋，要到圖 4 的 `chunk pool` 才知道是什麼。
6. **等待的 thread 此時在做什麼沒有說。** 等 `mm_lock` 的是 spin 還是 sleep，等 job 的那個 hardware thread 是停著還是去跑別的，圖上都沒有。
7. **接著前兩張讀會有的疑問。** 背景說 TLB miss 由 kernel SW 處理，那麼 TLB miss handler 讀 `page table` 時要不要拿 `mm_lock`？這張圖把 `page table` 放在 lock 裡面，會讓人以為每一次 TLB miss 都要搶這把 lock。圖沒有回答。
8. **Core 1 只畫了 T0。** 可以猜 Core 1 的 T1 不在 kernel 裡所以沒有 instance，但畫面上沒有任何一個「不在 kernel 裡」的 thread 可以對照。
9. **虛線有兩個意思。** 虛線框是 instance，虛線箭頭一處是 `same code`，一處是等待。

### 3. 圖說的一句話（讀 Key point 之前）

同一份 kernel code 被好幾個 hardware thread 各用自己的 stack 同時執行；共用的表由一把 `mm_lock` 管，一次只放一個 instance 進去；正在等 LZ4 HW 的那個 instance 不握 lock。

### 4. 與 Key point 是否一致

Key point：「The code exists once and an instance exists per thread inside the kernel. One instance at a time holds mm_lock. An instance that waits for its LZ4 HW job holds no lock.」

**一致。** 三句話各對到畫面上的一塊：最上面的大方塊、左邊與中間兩個 instance、右邊的 instance。便條的「拿兩次」是 Key point 沒有提的額外內容，但不衝突。

### 5. 困惑指數

**2。** 主結構由上到下一看就懂，只有便條的三步與三個 instance 的對應要讀者自己補。

### 6. 可疑的錯字或多餘文字

- 沒有看到錯字。
- `COT: compressed object table` 這一行的字被壓窄，和其他格的字體寬度不同。
- 副標「Shared tables are entered one instance at a time」的 entered 用在表上有點怪，但意思讀得出來。
- `mm_lock` 在鎖頭旁是紅字，在箭頭標籤裡是紫字。不是錯，只是同一個名字兩種顏色。

---

## 圖 4：One LZ4 HW, N Engines, Every Core

### 1. 人物與機器

這張也沒有人物。

| 物件 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 紫色虛線方塊，上 | `kernel SW instance` on Core 0 | 紫色箭頭到 `job ring`，標 `write a descriptor` | 把工作排進去 |
| 紫色虛線方塊，下 | `kernel SW instance` on Core 1 | 紫色箭頭到 `job ring`；另外收到一條綠色箭頭 `interrupt: match by tag` | 排工作，也收結果 |
| 灰色圓角框，8 個空格 | `job ring`，上方紅色鎖頭 `ring_lock` | 收 descriptor，交給 LZ4 HW | 排隊要上 lock |
| 8 個空格，沒有外框 | `completion ring` | 收 LZ4 HW 的結果，往左送 interrupt | 沒有 lock |
| 綠色大方塊，有齒輪 | `LZ4 HW`：up to N jobs at once；`engine 0`、`engine 1`、…、`engine N-1`；engines share no data | 從 job ring 取工作，寫 completion，對 DRAM 讀寫 | 同時做 N 件，engine 之間互不相干 |
| 藍色小字 | `N is a hardware parameter, not decided yet` | 註記 | N 還沒定 |
| 長條 | `DRAM`：斜線區 `chunk pool: compressed streams`；白色區 `frame region: 4096 B pages`，4 個空格 | 被 LZ4 HW 用兩條雙向綠色箭頭 `stream`、`page` 讀寫 | 壓縮後的資料與原始 page 分兩區 |
| 藍色方塊 | `L1 and L2 caches` | 沒有任何線接到它，下面三行藍字：not on this path、cache_clean before COMPRESS、cache_invalidate after DECOMPRESS | 資料不經過它 |

沒有無標籤的物件。`L1 and L2 caches` 的角色是「不在這條路上的東西」，用孤立來表達，讀得出來，但它下面那兩行動作是誰做的看不出來。

### 2. 看不懂的線或物件

1. **interrupt 只回到 Core 1。** 兩個 core 都寫 descriptor，但 `interrupt: match by tag` 的箭頭只指到 Core 1 的 instance。讀者會得到兩種讀法之一：completion 的 interrupt 固定送 Core 1，或者只是少畫一條。這是最可能讓人讀出錯誤結論的地方。
2. **`page` 箭頭的上端沒有接到 LZ4 HW。** 它的箭頭尖端停在藍色那行「N is a hardware parameter, not decided yet」上，看起來像在指那行字。`stream` 那條則有碰到 LZ4 HW 的左下角。
3. **`match by tag` 沒有畫出 tag。** ring 的格子全是空的，descriptor 上也沒有 tag。誰拿什麼去對什麼，要靠猜。
4. **「finish order」沒有演出來。** 兩個 ring 的格子都是空的，看不到「A 先排、B 先完成」這種對照。完成順序可以和排入順序不同，這件事只存在於一行文字裡。
5. **`ring_lock` 的範圍。** 鎖頭只掛在 `job ring` 上，`job ring` 有灰框而 `completion ring` 沒有。可以猜是「只有排入要 lock」，但名字叫 `ring_lock`，讀者會問 completion ring 是誰在讀、為什麼不用 lock。
6. **`ring_lock` 和圖 3 的 `mm_lock` 的關係沒有交代。** 寫 descriptor 是在握著 `mm_lock` 的時候做，還是放開之後做？兩張圖各講一把 lock，沒有一處把兩把放在一起。
7. **cache 那一角的理由要自己推。** 副標說 page data 不經過 L1、L2，左下角卻又說 COMPRESS 之前要 `cache_clean`、DECOMPRESS 之後要 `cache_invalidate`。懂 cache 的人推得出來：CPU 的 cache 裡可能有還沒寫回 DRAM 的內容，LZ4 HW 直接讀 DRAM 會讀到舊的；解壓後 DRAM 變了，cache 裡的舊內容要丟掉。但圖上沒有寫這個理由，也沒有說是誰做、對哪一個 core 的 L1 做。
8. **L1 與 L2 合成一格。** 如果前面的圖有分「每個 core 一個 L1、共用一個 L2」，這裡合成一個藍色方塊會讓 `cache_clean` 的對象變得不明確。
9. **ring 放在哪裡沒有說。** `job ring` 與 `completion ring` 是在 DRAM 裡還是在 LZ4 HW 的 register 裡，圖上看不出來。DRAM 長條裡只有 chunk pool 與 frame region。
10. **雙向箭頭沒有說哪個方向是哪個動作。** 可以推出 COMPRESS 是讀 page 寫 stream、DECOMPRESS 相反，但圖上沒有標。
11. **斜線的意思沒有圖例。** 可以猜斜線代表壓縮過的資料。
12. **ring 畫成一排格子。** 沒有 head、tail，也不是環狀。對主旨影響不大。

### 3. 圖說的一句話（讀 Key point 之前）

每個 core 的 kernel 把 job descriptor 寫進同一個有 `ring_lock` 的 job ring，LZ4 HW 裡 N 個 engine 誰空誰拿下一件，做完照完成的順序寫進 completion ring 並用 interrupt 通知 kernel；資料由 LZ4 HW 直接在 DRAM 的 frame region 與 chunk pool 之間搬，不經過 CPU 的 cache。

### 4. 與 Key point 是否一致

Key point：「ring_lock covers only queuing a job. Up to N jobs run at once and may finish in any order. Their data moves straight between the LZ4 HW and DRAM.」

**一致，有一處畫面偏弱。**

- 「ring_lock covers only queuing a job」：畫面上鎖頭只在 job ring，對得上。
- 「Up to N jobs run at once」：engine 0 到 engine N-1 的方塊，對得上。
- 「may finish in any order」：畫面只有 `completions, in finish order` 這幾個字，沒有任何格子內容可以看出順序不同。結論沒有錯，但這一句是靠文字撐起來的，不是靠畫面。
- 「data moves straight between the LZ4 HW and DRAM」：兩條綠色雙向箭頭加上孤立的 cache 方塊，對得上。

Key point 沒有提 interrupt 送到哪裡，所以 interrupt 只畫到 Core 1 不算和結論衝突，但畫面比結論多說了一件事。

### 5. 困惑指數

**3。** 主流程（ring 進、engine 取、completion 回、資料直通 DRAM）十秒內看得懂；但 interrupt 只回 Core 1、`page` 箭頭指到註記、cache 那一角缺理由，這三處會讓人停下來，其中第一處可能讀出錯的結論。

### 6. 可疑的錯字或多餘文字

- 沒有看到錯字。
- 標題「One LZ4 HW, N Engines, Every Core」的 Every Core 懸著，沒有動詞。讀者要自己補成「serves every core」。
- 副標「Page data never passes L1 or L2」的 passes 可以讀成「經過」也可以讀成「超過」，寫成 passes through 比較不會誤會。
- 「N is a hardware parameter, not decided yet」比較像專案狀態，不像這張圖要教的東西。它又剛好擋在 `page` 箭頭的終點。
- `engine N-1` 的字被壓窄。
- `4096 B pages` 的 B 是 byte，讀得懂。

---

## 跨圖的觀察

### 命名物件在兩張裡長得一不一樣

| 物件 | 圖 3 | 圖 4 | 一致嗎 |
|---|---|---|---|
| `kernel SW instance` | 紫色虛線框，寫 Core、thread、own stack | 紫色虛線框，只寫 on Core 0、on Core 1 | 外形一致，內容不一致。圖 3 強調 instance 是 per thread，圖 4 退回 per core |
| `LZ4 HW` | 綠色方塊加齒輪，N engines, up to N jobs at once | 綠色方塊加齒輪，裡面展開 engine 0 到 N-1 | 一致，圖 4 是圖 3 的放大 |
| 鎖頭 | 實心紅色鎖頭，掛在灰框右上角的邊線上 | 空心紅色線條鎖頭，比較大，放在灰框正上方 | **不一致**，兩把 lock 畫法不同 |
| 被 lock 保護的東西 | 灰色圓角框 `shared tables` | 灰色圓角框 `job ring` | 一致 |
| kernel 發出的箭頭 | 紫色 | 紫色 | 一致 |
| HW 發出的箭頭 | 沒有 | 綠色 | 圖 4 才出現，不衝突 |
| kernel 到 LZ4 HW 的路 | instance 直接一條箭頭指到 LZ4 HW | instance 只接到 job ring，不直接接 LZ4 HW | **不一致**。圖 3 那條直通的箭頭看了圖 4 才知道是簡寫 |
| 補充說明 | 黃色便條 | 藍色散字，沒有便條 | 不一致 |
| Key point 長條、編號方框、橘色標題底線、藍色副標 | 有 | 有 | 一致 |

### 分類顏色兩張一致嗎

大致一致：紫色是 kernel SW，綠色是 LZ4 HW，紅色是 lock，灰色是被 lock 保護的共用結構。

有一處不乾淨：藍色在圖 3 只用在副標，在圖 4 同時用在副標、`L1 and L2 caches` 方塊、cache 的三行字、以及「N is a hardware parameter」。藍色於是同時代表「說明文字」與「cache 這一類東西」。

### 用自己的話說這兩張圖的結論

- 圖 3：kernel 的程式碼只有一份，但每一個進到 kernel 的 hardware thread 都是一個獨立的執行中的 instance，各有自己的 stack。它們共用 page table、kernel 的管理表與 COT，這些表用一把 `mm_lock` 管，一次只讓一個 instance 進去。把一個壓縮過的 page 帶回來時，lock 分兩段拿：先握 lock 查表拿 frame，放開 lock 等 LZ4 HW 解壓，再握 lock 做 map。所以等硬體的時間不會擋住別人。
- 圖 4：LZ4 HW 只有一個，所有 core 共用。每個 core 的 kernel 把 job descriptor 寫進同一個 job ring，`ring_lock` 只管寫進去那一下。LZ4 HW 裡有 N 個 engine，誰空誰拿下一件，所以最多 N 件同時做，做完的順序不一定等於排入的順序，kernel 收到 interrupt 之後用 tag 找回是哪一件。資料由 LZ4 HW 直接在 DRAM 的 frame region 與 chunk pool 之間搬，不經過 CPU 的 L1、L2，所以 kernel 要在 COMPRESS 之前把 cache 寫回、在 DECOMPRESS 之後把 cache 作廢。

兩張合起來的意思：kernel 這邊的並行靠兩把範圍很小的 lock，硬體這邊的並行靠 N 個 engine；慢的那一段（硬體壓縮、解壓）不握任何 lock。

兩張之間缺的一塊：`mm_lock` 與 `ring_lock` 的先後關係，以及圖 3 便條的第 2 步對到圖 4 的哪幾條箭頭。

### 建議重生

| 圖 | 理由 | 要改什麼 |
|---|---|---|
| 圖 4 | 困惑指數 3 | 1. interrupt 的箭頭要嘛兩個 core 都畫，要嘛明寫送到哪一個，或者明寫「還沒決定」。2. `page` 箭頭的上端接到 LZ4 HW 的方塊上，把「N is a hardware parameter」那行移開。3. ring 的格子裡放兩三個有 tag 的 job，讓 job ring 的順序與 completion ring 的順序不同，把「any order」與「match by tag」演出來。4. cache 那一角加一句理由，並寫出是 kernel SW 做的。5. 鎖頭畫法改成和圖 3 一樣。 |

圖 3 不在重生清單裡。如果順手要修，值得做的只有兩件：在三個 instance 旁標上便條的步驟編號，以及把指向 LZ4 HW 的那條箭頭的文字改成不會讀成「等人派工作」的說法。

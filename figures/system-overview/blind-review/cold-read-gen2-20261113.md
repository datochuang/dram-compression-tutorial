# System overview 白板圖：冷讀驗收報告

- 日期：2026-11-13
- 方法：只給圖、不給提示詞的冷讀。讀者只知道「這是一顆 multi-core SoC，DRAM 裡一部分 page 會被 LZ4 HW 壓縮」，沒有讀任何文件或提示詞。
- 讀的圖：gen1 的第 1、2 張，gen2 的第 3、4 張。
  - `gen1/01-per-core-and-shared.png`
  - `gen1/02-tlb-miss-enters-kernel.png`
  - `gen2/03-one-kernel-many-instances.png`
  - `gen2/04-one-lz4-hw-for-every-core.png`
- 每張圖都是先遮住底部 Key point 回答第 1 到 3 題，再讀 Key point 回答第 4 題。

---

## 圖 1：The Processor: Per Core and Shared

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 清不清楚 |
|---|---|---|---|
| 火柴人加筆電 | `user SW` | 坐在 Core 0 的 T0 裡，往下送出一個 `VA` | 清楚 |
| 三個大框 | `Core 0`、`Core 1`、`Core N` | 各自包住兩個 thread、一個 MMU、一個 L1 | 清楚 |
| 小框 | `T0`、`T1` | hardware thread。除了 Core 0 的 T0，其餘五格是空的 | 標籤清楚，空格的意思不清楚（閒置？還是省略沒畫？） |
| 藍色方塊 | `CPU MMU: one TLB / VA to PA` | 把 VA 轉成 PA | 清楚 |
| 藍色方塊 | `L1 cache` | 每個 core 一個 | 清楚 |
| 藍色長條 | `L2 cache: one, shared by all cores / sees physical addresses only` | 所有 core 共用 | 清楚 |
| 白色長條 | `DRAM` | 最底層，裡面是空的 | 清楚 |
| 黃色便利貼 | `Platform assumptions`：P1、P2、P3，加一句 `core and thread counts are examples` | 列前提 | 清楚 |

圖裡沒有 kernel，也沒有 LZ4 HW。

### 2. 看不懂的線或物件

- Core 0 用橘色箭頭一路畫到 DRAM（`VA`、`PA`、`L1 miss`、`L2 miss`），Core 1 與 Core N 只有一條沒有箭頭的黑線接到 L2。我猜橘色是「一次存取的例子」，黑線是「同樣接法」，但圖上沒說。
- Core 0 的 `T1` 沒有任何線接到 MMU。便利貼的 P3 說 TLB 由同一個 core 的 thread 共用，可是畫面上只有 T0 在用。
- 便利貼的 P1「no hardware page table walk」在這張圖裡找不到對應的畫面。它像是下一張的預告。
- MMU 方塊上沒有「hit」或「miss」的字樣。L1、L2 的箭頭有寫 miss，MMU 那一格沒有，所以看不出這條橘色路徑是 TLB hit 的情況。
- L2 寫「sees physical addresses only」。PA 箭頭是先進 L1 的，L1 看到的也是 PA，為什麼只在 L2 強調「only」，不確定。
- `Core N` 與中間的 `...`：N 是最後一個 core 的編號。後面第 3、4 張的 N 又是 engine 的數目，見跨圖觀察。

### 3. 圖說的一句話

每個 core 有自己的 MMU（含 TLB）與 L1，所有 core 共用一個 L2 與 DRAM，user SW 的一次存取依序經過 MMU、L1、L2、DRAM。

### 4. 畫面和結論一不一致

Key point：「On a TLB hit the access goes TLB, L1, L2, DRAM in hardware only. The kernel is not involved.」

**部分一致。** 路徑的順序和畫面一致。但 Key point 的兩個重點在畫面上都沒有：

- 「On a TLB hit」：畫面沒有標 hit。
- 「The kernel is not involved」：畫面裡根本沒有 kernel，讀者不知道 kernel 原本可能在哪裡介入，這句話像是憑空出現。

畫面講的是「誰是每個 core 自己的、誰是共用的」（標題也是這個），Key point 講的是「TLB hit 時 kernel 不介入」。兩者是兩件事。

### 5. 困惑指數

**2。** 結構一看就懂，但 Key point 講的事不是畫面的主題。

### 6. 可疑的錯字或多餘文字

- 沒有看到拼錯的字。
- 便利貼右下角有一小撇，像是沒畫完的摺角（圖 2、3 的便利貼有完整摺角）。
- 副標題最後的「and the DRAM.」字比前面小一號，像是擠進去的。

---

## 圖 2：TLB Miss: The Kernel Walks the Page Table

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 清不清楚 |
|---|---|---|---|
| 火柴人加筆電 | `user SW` | 在 Core 0 的 T1 裡，送出 `1 VA` | 清楚 |
| 紫色虛線框 | `kernel SW instance / running on T1` | 收到 `2 miss: exception`，做 `3 read pte[h]`，再做 `4 write the entry` | 角色清楚。「instance」這個詞沒解釋，要到圖 3 才懂 |
| 小框 | `T0`：`busy with other work` | 沒參與 | 清楚 |
| 藍色大方塊 | `TLB of Core 0 / shared by T0 and T1` | 被查、miss、被填 | 清楚 |
| 白色方塊 | `page table: pte[h] / in DRAM, read only by the kernel` | 被 kernel 讀 | 大致清楚，見下 |
| 白色圓角框 | `One access, three outcomes` | 三行文字列出三種結果 | 清楚，但是純文字 |
| 黃色便利貼 | `TLBs are private copies` | 補充說明 | 見下 |

### 2. 看不懂的線或物件

- **步驟 5 沒有箭頭。**「5 rerun the access: TLB hit」是 T1 框頂端的一行藍字，位置在步驟 1 的上方。照視線順序會先讀到 5 再讀到 1。步驟 1 到 4 都有箭頭，只有 5 沒有。
- 步驟的顏色有三種：1、2 是橘色，3、4 是紫色，5 是藍色。橘色我猜是硬體的動作，紫色是 kernel 的動作，藍色的 5 不知道算哪一類。
- 步驟在畫面上的左右順序是 1、2、4、3（3 在最右邊往外指），要靠數字才排得出順序。
- `pte[h]` 的 `h` 沒有定義。
- 「read only by the kernel」有兩種讀法：「只有 kernel 會讀」或「對 kernel 是 read-only」。照標題應該是前者。
- 圖 1 的那一格叫 `CPU MMU: one TLB`，這裡叫 `TLB of Core 0`，MMU 這個詞不見了。L1、L2、DRAM 也都不在畫面上。page table 寫「in DRAM」，但沒有畫 DRAM。
- 圖 1 的 user SW 在 T0，這裡搬到 T1，T0 變成「busy with other work」。我猜是要表達「只有 miss 的那個 thread 進 kernel」，但換位置本身會讓人停一下。
- 便利貼「TLBs are private copies」：是誰的 copy？應該是 page table 內容的 copy，但沒寫。「the kernel clears it from every core's TLB」講的是好幾個 core，畫面只有一個 core。這一段和左邊的五步流程沒有線連起來，是另一個主題。
- 「One access, three outcomes」的第三種（page compressed，kernel calls the LZ4 HW）畫面上沒有畫，LZ4 HW 沒有出現。
- 「page in a frame」的 frame 沒有解釋。知道 page frame 的人猜得到。

### 3. 圖說的一句話

TLB miss 時，硬體不會自己查 page table，而是在 miss 的那個 thread 上進 exception，由 kernel 讀 page table、把 entry 寫回 TLB，然後重跑那次存取。

### 4. 畫面和結論一不一致

Key point：「The CPU never reads the page table. Every decompression fault starts as a TLB miss, so the kernel is already on this path.」

**部分一致。**

- 第一句的意思和畫面一致，但用詞會讓人卡住：畫面上讀 page table 的 kernel SW instance 就是「running on T1」，也就是在 CPU 上跑。說「The CPU never reads」字面上和畫面衝突。應該是指 CPU 的硬體（MMU）不讀。
- 第二句「Every decompression fault starts as a TLB miss」只有右邊文字框的第三行在支撐，畫面的五步流程畫的是「page in a frame」的情況。decompression 與 LZ4 HW 都沒有畫出來。

### 5. 困惑指數

**2。** 五步流程靠數字讀得懂，卡住的是步驟 5 沒箭頭與 Key point 的「The CPU」。

### 6. 可疑的錯字或多餘文字

- 沒有看到拼錯的字。
- 標題底線在「Page」下方斷了一小段、有高低差。
- 便利貼與左邊的主流程是兩個主題，對這張圖的一句話來說偏多餘。

---

## 圖 3：One Kernel, Many Instances

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 清不清楚 |
|---|---|---|---|
| 紫色實線長框 | `kernel SW code: one copy in DRAM` | 一份程式碼 | 清楚 |
| 紫色虛線框（左） | `kernel SW instance / Core 0, thread T0 / own stack` | `holds mm_lock: inside`，箭頭指向灰框 | 清楚 |
| 紫色虛線框（中） | `kernel SW instance / Core 0, thread T1 / own stack` | `waits for mm_lock`，箭頭也指向灰框 | 標籤清楚，畫面看不出在等，見下 |
| 紫色虛線框（右） | `kernel SW instance / Core N, thread T0 / own stack` | `its job is running: holds no lock`，箭頭指向 LZ4 HW | 清楚 |
| 紅色掛鎖 | `mm_lock` | 掛在灰框的上緣 | 清楚 |
| 灰色粗框 | 無標籤 | 包住三張表 | 沒標籤，從副標題猜是「shared tables」 |
| 白色方塊 | `page table / where each page is now` | 被鎖保護 | 清楚 |
| 白色方塊 | `kernel tables / page states, free frames, free chunks` | 被鎖保護 | 「chunks」沒解釋 |
| 白色方塊 | `COT / where each compressed page is stored` | 被鎖保護 | **COT 是縮寫，沒有展開** |
| 綠色方塊加齒輪 | `LZ4 HW / N engines, up to N jobs at once` | 執行 job | 清楚 |
| 黃色便利貼 | `A compressed page takes mm_lock twice`，三步 | 說明加鎖的時機 | 見下 |

沒有 user SW，沒有 core 的框，沒有 TLB。

### 2. 看不懂的線或物件

- **拿到鎖的和在等鎖的畫得一模一樣。** 左邊（holds）與中間（waits）兩條箭頭一樣粗、一樣長，都停在灰框的上緣。只有文字不同。不讀字的話會以為兩個 instance 都進去了。「inside」只是字，箭頭沒有真的畫進框裡。
- 掛鎖畫成鎖上的樣子，夾在兩條箭頭中間，看不出是誰拿著。
- 程式碼框往下的三條虛線沒有箭頭，只有第一條標「same code」。
- 右邊的「its job is running」：job 這個詞第一次出現，沒有解釋。這個 instance 是自己在跑 job，還是在等 LZ4 HW 跑完？從「holds no lock」猜是後者，但它是在睡、在忙等、還是去做別的事，看不出來。
- **N 有兩個意思。** `Core N` 的 N 是 core 的編號，`N engines` 的 N 是 engine 的數目，兩個放在同一張圖、相鄰的位置。讀者會猜「engine 的數目等於 core 的數目」。
- 便利貼的標題「A compressed page takes mm_lock twice」：拿鎖的主詞寫成 page。應該是「對一個 compressed page 的 fault」。
- 便利貼的三步是同一個 instance 先後做的事，畫面上的三個 instance 是同一時刻的三個不同 instance。兩者怎麼對應沒有說明。我猜右邊那個 instance 正在便利貼的第 2 步。
- 圖 2 的 page table 是獨立的白框，kernel 讀它時沒有畫任何鎖。這張圖的 page table 在 `mm_lock` 的灰框裡。那麼圖 2 那種每次 TLB miss 的讀取要不要拿 `mm_lock`？兩張圖合起來看會有這個疑問。
- 三張表在哪裡沒有寫（程式碼框有寫「in DRAM」）。
- 灰框與 LZ4 HW 下方有一大片空白。

### 3. 圖說的一句話

kernel 的程式碼只有一份，每個進 kernel 的 hardware thread 各有一個 instance 與自己的 stack；共用的表由 `mm_lock` 保護，一次只有一個 instance 能進去，在等 LZ4 HW 的 instance 不拿鎖。

### 4. 畫面和結論一不一致

Key point：「The code exists once and an instance exists per thread inside the kernel. One instance at a time holds mm_lock, and nobody holds it while the LZ4 HW works.」

**部分一致。**

- 前一句與「One instance at a time holds mm_lock」和畫面一致。
- **「nobody holds it while the LZ4 HW works」字面上和畫面衝突。** 畫面是同一時刻：左邊的 instance 拿著 `mm_lock`，右邊的 instance 的 job 正在 LZ4 HW 裡跑。也就是 LZ4 HW 在工作的同時，有人拿著 `mm_lock`。Key point 想說的應該是「在等自己的 job 的那個 instance 不拿鎖」（便利貼的第 2 步），但寫成「nobody」就變成另一個意思。

### 5. 困惑指數

**3。** 主旨抓得到，但「拿到」與「在等」畫得一樣、Key point 的「nobody」和畫面相反、COT 與 N 要用猜的。

### 6. 可疑的錯字或多餘文字

- 沒有看到拼錯的字。
- `COT` 沒有展開。
- 這張的 Key point 標籤格是淺藍底，圖 1、2、4 是白底。
- 便利貼標題的主詞（page 拿鎖）不對。

---

## 圖 4：One LZ4 HW, N Engines, Every Core

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 清不清楚 |
|---|---|---|---|
| 紫色虛線框（上） | `kernel SW instance / on Core 0` | `write a descriptor` 到 job ring | 清楚 |
| 紫色虛線框（下） | `kernel SW instance / on Core 1` | 也寫 job ring（箭頭沒標字），並收到 `interrupt: match by tag` | 清楚，但為什麼只有它收 interrupt 不清楚 |
| 灰色圓角框，內有 8 個空格 | `job ring` | 接 descriptor | 清楚 |
| 紅色掛鎖 | `ring_lock` | 掛在 job ring 上緣 | 清楚 |
| 8 個空格，沒有外框 | `completion ring` | 接 LZ4 HW 的 completion | 清楚 |
| 綠色方塊加齒輪 | `LZ4 HW / up to N jobs at once`，內有 `engine 0`、`engine 1`、`...`、`engine N-1`，`engines share no data` | 取 job、執行、回報 | 清楚 |
| 藍色小字 | `N is a hardware parameter, not decided yet` | 註記 | 清楚 |
| 白色長條 | `DRAM`，分成：只寫「DRAM」的一格、斜線的 `chunk pool: compressed streams`、`frame region: 4096 B pages`（內有 4 個小方格） | 資料所在 | 最左邊只寫「DRAM」的那一格是什麼區域不清楚 |
| 藍色方塊 | `L1 and L2 caches`，下方藍字 `not on this path / cache_clean before COMPRESS / cache_invalidate after DECOMPRESS` | 不在路徑上 | 見下 |

沒有 user SW。

### 2. 看不懂的線或物件

- **「a free engine takes the next job」這條箭頭是紫色。** 圖 2、3 與這張的其他地方，紫色是 kernel 的動作，綠色是 LZ4 HW 的動作。這個動作是 engine 做的，卻畫成紫色。
- **interrupt 只畫給 Core 1 的 instance。** Core 0 的 instance 也送了 job，它的 completion 誰來收？是 interrupt 固定送到某一個 core，還是只是舉例？看不出來。
- 「interrupt: match by tag」的箭頭從 completion ring 出發。interrupt 應該是 LZ4 HW 發的，ring 是被讀的。把「interrupt」和「讀 ring、用 tag 找」畫成同一條箭頭。
- `tag` 沒有畫出來。兩個 ring 的格子都是空的，descriptor 與 completion 上看不到 tag，也看不出「finish order」和送出的順序不同。
- job ring 有灰色外框加掛鎖，completion ring 沒有外框也沒有鎖。completion ring 需不需要鎖，看不出是刻意沒有還是沒畫。
- **`page` 那條綠色雙向箭頭的上端指在藍色小字「N is a hardware parameter, not decided yet」上，沒有碰到 LZ4 HW 的框。** 看起來像在指那行註記。`stream` 箭頭的上端也只碰到 LZ4 HW 的左下角外側。
- `stream` 與 `page` 兩條都是雙向箭頭，看不出 COMPRESS 與 DECOMPRESS 各是哪個方向。知道壓縮的人推得出來。
- `L1 and L2 caches` 寫「not on this path」，下面卻接著兩個 cache 動作。誰做（應該是 kernel）、為什麼需要（因為 LZ4 HW 繞過 cache 直接讀寫 DRAM）都沒寫，要自己推。這個方塊沒有任何線連到別的物件。
- 圖 3 的 `mm_lock` 在這張沒有出現。`ring_lock` 和 `mm_lock` 的關係（寫 ring 的時候還拿著 `mm_lock` 嗎？）看不出來。
- 圖 3 的 instance 標「Core 0, thread T0 / own stack」，這張只標「on Core 0」。同一個 core 的兩個 thread 能不能各有一個 instance 在寫 ring，這張看不出來。
- 標題寫「Every Core」，畫面只有 Core 0 與 Core 1，沒有圖 1、3 的 Core N。
- N 的雙重意思延續圖 3：engine 編到 `N-1`，core 在圖 1、3 編到 `N`。標題把「N Engines」與「Every Core」並列，更容易讓人以為兩個數目有關。

### 3. 圖說的一句話

各個 core 上的 kernel instance 把 job 的 descriptor 寫進同一個有鎖的 job ring，LZ4 HW 裡空著的 engine 取走執行，完成後照做完的順序寫進 completion ring 並發 interrupt；page 與壓縮後的 stream 直接在 LZ4 HW 與 DRAM 之間搬，不經過 L1、L2。

### 4. 畫面和結論一不一致

Key point：「ring_lock covers only queuing a job. Up to N jobs run at once and may finish in any order. Their data moves straight between the LZ4 HW and DRAM.」

**一致。** 三句都找得到對應的畫面：鎖只掛在 job ring 上，LZ4 HW 寫 up to N jobs，綠色箭頭直接接 DRAM。小落差只有一個：「may finish in any order」在畫面上只有「in finish order」這幾個字，ring 的格子是空的，沒有任何東西畫出順序不同。

### 5. 困惑指數

**2。** 主流程順著箭頭就讀得完，疑問都在邊緣（interrupt 給誰、紫色的那條箭頭、箭頭尖端指到註記上）。

### 6. 可疑的錯字或多餘文字

- 沒有看到拼錯的字。
- `chunk pool` 斜線區塊裡，文字上方有一小塊斜線變淡，像是塗改的痕跡。
- 標題「One LZ4 HW, N Engines, Every Core」的「Every Core」是懸空的片語，讀起來不成句。
- 藍色註記「N is a hardware parameter, not decided yet」的位置剛好在 `page` 箭頭的尖端。

---

## 跨圖觀察

### 命名物件長得一不一樣

| 物件 | 出現在 | 一致性 |
|---|---|---|
| `kernel SW instance`（紫色虛線圓角框） | 圖 2、3、4 | 外形一致。第二行的寫法三張都不同：「running on T1」、「Core 0, thread T0 / own stack」、「on Core 0」 |
| `user SW`（火柴人加筆電） | 圖 1、2 | 外形一致，圖 2 比較大。位置從 Core 0 的 T0 換到 T1。**圖 3、4 完全消失** |
| 掛鎖（紅色，掛在灰色粗框的上緣） | 圖 3 `mm_lock`、圖 4 `ring_lock` | 一致。「灰色粗框加紅色掛鎖等於被鎖保護的共用結構」這個畫法兩張相同，圖 4 的掛鎖線條稍粗 |
| `LZ4 HW`（綠色方塊加齒輪） | 圖 3、4 | 一致。圖 4 多畫了裡面的 engine |
| TLB／MMU（藍色方塊） | 圖 1、2 | 顏色一致，名字不同：圖 1 是 `CPU MMU: one TLB`，圖 2 是 `TLB of Core 0` |
| `page table`（白色方塊） | 圖 2、3 | 走樣。圖 2 是獨立的框，說明是「in DRAM, read only by the kernel」；圖 3 在 `mm_lock` 的灰框裡，說明是「where each page is now」 |
| `DRAM`（白色長條） | 圖 1、4 | 外形一致。圖 1 是空的，圖 4 分了區。圖 2 的 page table 與圖 3 的 kernel code 都寫「in DRAM」，但圖 4 的 DRAM 裡沒有它們的位置 |
| L1、L2 | 圖 1、4 | 顏色一致。圖 1 分開畫，圖 4 合成一個方塊 |
| 黃色便利貼 | 圖 1、2、3 | 圖 2、3 有摺角，圖 1 沒有。圖 4 沒有便利貼，改用藍色小字 |
| Key point 那一條 | 四張 | 圖 3 的標籤格是淺藍底，其餘三張是白底 |
| 橘色的步驟箭頭 | 圖 1、2 | 圖 3、4 沒有橘色箭頭 |

gen1（圖 1、2）與 gen2（圖 3、4）的筆跡、標題底線、副標題的顏色是同一套，看不出明顯的世代差異。gen2 的字稍微細一點、小一點。

### 分類顏色

| 顏色 | 我讀到的意思 | 一致嗎 |
|---|---|---|
| 藍色填滿 | CPU 這一側的硬體：MMU／TLB、L1、L2 | 圖 1、2、4 一致 |
| 藍色文字 | 副標題，也用在註記 | **負擔太多。** 同時是副標題、圖 2 的步驟 5、圖 4 的 N 註記與 cache 註記、圖 3 的 Key point 底色 |
| 橘色 | user SW 的存取路徑與硬體的反應 | 圖 1、2 一致，圖 3、4 沒用到（標題底線除外） |
| 紫色 | kernel SW 與它的動作 | 圖 2、3、4 一致。**例外：圖 4 的「a free engine takes the next job」是 engine 的動作卻畫紫色** |
| 綠色 | LZ4 HW 與它的資料、回報 | 圖 3、4 一致 |
| 紅色 | lock | 圖 3、4 一致 |
| 灰色粗框 | 被鎖保護的共用結構 | 圖 3、4 一致 |
| 黃色 | 便利貼 | 一致 |
| 斜線 | 壓縮過的資料 | 只出現在圖 4 |

硬體有兩種顏色：CPU 側的是藍色，LZ4 HW 是綠色。看過兩張就懂，但沒有圖例。

### 故事線

順序是：圖 1 硬體的配置，圖 2 TLB miss 進 kernel，圖 3 好幾個 kernel instance 與 `mm_lock`，圖 4 LZ4 HW 與兩個 ring。方向是順的，一張比一張往裡走。斷掉的地方：

1. **圖 2 到圖 3。** 圖 2 的「page compressed: the kernel calls the LZ4 HW」只是文字框裡的一行，沒有畫。圖 3 直接從鎖講起，沒有畫出「是 user SW 碰到 compressed page 才走到這裡」。兩張之間少了一個「decompression fault 的全程」。
2. **page table 要不要鎖。** 圖 2 讀 page table 沒有鎖，圖 3 的 page table 在 `mm_lock` 裡。
3. **圖 3 到圖 4。** 圖 3 的 instance 一條箭頭直接指到 LZ4 HW，圖 4 才出現中間的 ring。當成放大來看可以接受，但 `mm_lock` 在圖 4 不見了，兩個鎖的先後關係沒有交代。
4. **user SW 在後半消失。** 圖 1、2 有 user SW，圖 3、4 沒有。讀者看不到「這些事都是為了讓那個在等的 user SW 繼續跑」。
5. **結尾沒有收回來。** 圖 4 停在 interrupt 回到 kernel instance。之後 map page、填 TLB、重跑存取（圖 2 的步驟 4、5）沒有接回去。
6. **COMPRESS 沒有人發起。** 四張圖畫的都是 fault 與 decompress 這一邊。COMPRESS 只在圖 2 的便利貼（before compressing a page）與圖 4 的 cache 註記裡以文字出現。誰決定要壓縮、什麼時候壓縮，整組圖沒有講。
7. **N 的兩個意思**（core 的編號與 engine 的數目）跨圖 1、3、4。

### 我用自己的話說這組圖的結論

這顆 SoC 的每個 core 有自己的 MMU／TLB 與 L1，所有 core 共用 L2 與 DRAM。CPU 硬體不會自己查 page table，所以每一次 TLB miss 都在當下那個 thread 上進 kernel，由 kernel 查表、填 TLB；如果那個 page 是壓縮的，kernel 就在這條路上順便請 LZ4 HW 解壓縮。因為好幾個 thread 會同時在 kernel 裡，共用的表用一把 `mm_lock` 保護，一次只進一個，而且等 LZ4 HW 的那段時間不拿這把鎖。LZ4 HW 整顆 SoC 只有一個，裡面有 N 個 engine，所有 core 透過同一個 job ring 送 job（`ring_lock` 只管排進去那一下），結果照做完的順序回來、用 tag 對回去；資料由 LZ4 HW 直接讀寫 DRAM，不經過 L1、L2，所以 kernel 要自己在前後處理 cache。

我講不出來的部分：誰發起 COMPRESS，以及 N 和 core 的數目有沒有關係。

### 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|
| 1 The Processor: Per Core and Shared | 2 | 是 | 部分一致：Key point 講 TLB hit 與 kernel，畫面兩者都沒有 |
| 2 TLB Miss: The Kernel Walks the Page Table | 2 | 是 | 部分一致：「The CPU never reads」的用詞；decompression 沒有畫 |
| 3 One Kernel, Many Instances | 3 | 否：拿到鎖與在等鎖畫得一樣，COT 沒展開，灰框沒標籤 | 部分一致：「nobody holds it while the LZ4 HW works」字面上和畫面相反 |
| 4 One LZ4 HW, N Engines, Every Core | 2 | 是（誰收 interrupt 除外） | 一致 |

### 建議重生

照「困惑指數 3 以上、或角色不清、或畫面與結論不一致」的標準：

**圖 3：建議重生。** 三個條件都碰到。

- 拿到鎖的 instance 與在等的 instance 要畫得不一樣：拿到的箭頭畫進灰框裡，在等的停在框外，例如用虛線或加一個等待的記號。
- Key point 的「nobody holds it while the LZ4 HW works」改成講「在等自己的 job 的那個 instance」。現在的畫面正好是有人拿著鎖、同時 LZ4 HW 在工作。
- `COT` 展開或加一句說明。灰框加標籤（例如 shared tables）。
- `Core N` 與 `N engines` 換掉其中一個字母。
- 便利貼標題的主詞改掉（拿鎖的不是 page）。
- Key point 標籤格的底色改回白色，和其他三張一致。

**圖 1、圖 2：畫面與結論是「部分一致」，可以只改字，不一定要重生。**

- 圖 1：在 MMU 那一格標出這條路徑是 TLB hit，或把 Key point 改成講「誰是 per core、誰是共用」。現在的 Key point 提到的 kernel 不在畫面上。
- 圖 2：Key point 的「The CPU never reads the page table」改成指硬體（例如 the CPU hardware 或 the MMU）。步驟 5 補一條箭頭，顏色歸到橘色或紫色其中一類。

**圖 4：不在重生標準內。** 如果要順手修，優先順序是：

1. 「a free engine takes the next job」的箭頭改成綠色。
2. `page` 箭頭的上端接到 LZ4 HW 的框，藍色的 N 註記移開。
3. interrupt 給哪個 core 講清楚，或兩個 instance 都畫。
4. DRAM 最左邊那一格標出是什麼區域。
5. cache 的兩行註記加上是誰做的。

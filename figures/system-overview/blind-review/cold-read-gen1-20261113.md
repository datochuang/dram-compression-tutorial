# system-overview gen1 冷讀驗收報告

- 日期：2026-11-13
- 方法：只給圖、不給提示詞的冷讀。讀者只讀下列四張 PNG，沒有讀提示詞、規格文件或其他資料夾。
- 讀的是 `figures/system-overview/gen1/` 這一組的四張：
  1. `01-per-core-and-shared.png`
  2. `02-tlb-miss-enters-kernel.png`
  3. `03-one-kernel-many-instances.png`
  4. `04-one-lz4-hw-for-every-core.png`
- 讀法：每張先不看底部 Key point，回答第 1 到 3 項，再讀 Key point 回答第 4 到 6 項。一張寫完才讀下一張。

---

## 圖 1：The Processor: Per Core and Shared

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 角色清不清楚 |
|---|---|---|---|
| 火柴人加一台 laptop | `user SW` | 坐在 Core 0 的 T0 格子裡，往下送出一個 VA | 清楚。是發出存取的人 |
| 三個大框 | `Core 0`、`Core 1`、`Core N` | 每個框裡有兩個小格、一個 MMU、一個 L1 | 清楚 |
| 每個 core 裡的兩個白色小格 | `T0`、`T1` | 沒有動作。只有 Core 0 的 T0 有人，其他五格是空的 | **不夠清楚**。圖上沒有寫 T 是什麼。要靠右邊便利貼的「shared by its threads」才猜得到是 hardware thread |
| 藍色方塊 | `CPU MMU: one TLB / VA to PA` | 收 VA、送出 PA | 清楚 |
| 藍色方塊 | `L1 cache` | 收 PA，miss 時往下 | 清楚 |
| 藍色長條 | `L2 cache: one, shared by all cores / sees physical addresses only` | 三個 core 的 L1 都接到它 | 清楚 |
| 白色長條 | `DRAM` | L2 miss 時到這裡 | 清楚，但裡面是空的 |
| 黃色便利貼 | `Platform assumptions`，列 P1、P2、P3，還有一行 `core and thread counts are examples` | 說明前提 | 清楚 |

沒有 kernel，也沒有任何標成 kernel 的東西。

### 2. 看不懂的線或物件

- **Core 0 用橘色箭頭，Core 1 與 Core N 用黑色、沒有箭頭的直線**接到 L2。我猜橘色是「這一次存取走的路」、黑線是「有接線」，但圖上沒有說。
- **T1 沒有線接到 CPU MMU**。只有 T0 往下有一個 VA 箭頭。便利貼的 P3 說 TLB 是 thread 共用的，但畫面上看不出 T1 也用同一個 MMU。
- **T0、T1 沒有展開**。
- **副標題寫「one CPU MMU, one TLB」像是兩樣東西，方塊卻寫「CPU MMU: one TLB」像是一樣東西裡面有另一樣**。TLB 在 MMU 裡面還是旁邊，兩處說法不同。
- **便利貼的 P1「no hardware page table walk」在畫面裡沒有對應的東西**。這張圖沒有畫 page table，也沒有畫 TLB miss，P1 掛在這裡不知道要對到哪裡。
- **藍色代表什麼不確定**。每個 core 自己的 MMU 與 L1 是藍色，共用的 L2 也是同一個藍色。標題講的是「per core 與 shared」，顏色卻沒有分這兩類。DRAM 是白色，thread 格子也是白色。
- 橘色同時用在標題底線與存取路徑的箭頭。

### 3. 圖說的一句話（不看 Key point）

每個 core 有自己的 MMU、TLB 與 L1 cache，所有 core 共用一個 L2 cache 與 DRAM；user SW 的一次存取依序走 VA、PA、L1 miss、L2 miss 到 DRAM。

### 4. 畫面和 Key point 一不一致

Key point：`On a TLB hit the access goes TLB, L1, L2, DRAM in hardware only. The kernel is not involved.`

**部分一致。**

- 一致的部分：橘色箭頭的順序確實是 TLB、L1、L2、DRAM。
- 不一致的部分一：畫面上沒有「TLB hit」這幾個字，也沒有 hit 與 miss 的分岔。讀者看畫面不會知道這條路是「hit 的情況」。
- 不一致的部分二：畫面上沒有 kernel。Key point 說「kernel 不介入」，但這張圖從頭到尾沒有出現 kernel，讀者不知道 kernel 本來會在哪裡介入。
- 不一致的部分三：標題與副標題講的是「誰是每個 core 自己的、誰是共用的」，Key point 講的是「TLB hit 時 kernel 不介入」。這是兩個不同的結論。
- 小地方：Key point 的「goes TLB, L1, L2, DRAM」讀起來像每次存取都走到 DRAM。畫面的箭頭標了 `L1 miss`、`L2 miss`，比 Key point 準確。

### 5. 困惑指數

**2。** 結構一看就懂；扣分在 Key point 講的 TLB hit 與 kernel 兩件事畫面上都沒有。

### 6. 可疑的錯字或多餘文字

- 沒有看到錯字。
- 副標題最後的「and the DRAM.」字距明顯比前面擠，像是後來塞進去的。
- 便利貼的 P3 那一行字體比 P1、P2 窄。
- 便利貼右下角有一個小撇，應該是紙角翹起的筆畫，不是文字。

---

## 圖 2：TLB Miss: The Kernel Walks the Page Table

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 角色清不清楚 |
|---|---|---|---|
| 火柴人加 laptop | `user SW` | 坐在 Core 0 的 T1 裡，送出 `1 VA`，最後 `5 rerun the access: TLB hit` | 清楚。是發出存取、被服務的人 |
| 紫色虛線框 | `kernel SW instance / running on T1` | 收到 `2 miss: exception`，做 `3 read pte[h]`，再做 `4 write the entry` | 做的事清楚。**「instance」這個字在這張沒有解釋**，讀者不知道為什麼不直接叫 kernel |
| 白色格子 | `T0`，裡面寫 `busy with other work` | 沒有參與 | 清楚。看得出是要說「只有 miss 的那個 thread 進 exception」 |
| 白色格子 | `T1` | 裝著 user SW 與 kernel SW instance | 清楚 |
| 藍色大方塊 | `TLB of Core 0 / shared by T0 and T1` | 收 VA、發出 miss、被寫入 entry | 清楚。但方塊裡沒有畫任何 entry |
| 白色方塊（Core 0 外面） | `page table: pte[h] / in DRAM, read only by the kernel` | 被 kernel 讀 | 清楚 |
| 白色圓角框 | `One access, three outcomes`，三行 | 文字說明，不是機器 | 清楚 |
| 黃色便利貼 | `TLBs are private copies`，兩行說明 | 文字說明 | **不夠清楚**，見下 |

`LZ4 HW` 只在文字框裡出現一次，畫面上沒有這個機器。

### 2. 看不懂的線或物件

- **步驟 5 沒有箭頭**。1 到 4 都有箭頭，5 只是 T1 左上角的一行藍字。讀者要自己想像 user SW 再走一次箭頭 1。
- **步驟編號的顏色有三種**：1、2 是橘色，3、4 是紫色，5 是藍色。我猜橘色是存取與硬體發出的事、紫色是 kernel 做的事，但藍色的 5 與副標題同色，不知道算哪一類。圖上沒有圖例。
- **`pte[h]` 的 h 是什麼沒有說**。可能是 index、hash 或 handle。
- **`read only by the kernel` 有兩種讀法**：「只有 kernel 會讀」或「對 kernel 是 read-only」。前一種才合理，但寫法會讓人停一下。
- **便利貼 `TLBs are private copies`**：是什麼的 copy 沒有寫（我猜是 page table entry 的 copy）。下一行「the kernel clears **it** from every core's TLB」的 it 指的應該是那個 page 的 entry。更大的問題是這張圖只畫了 Core 0，沒有其他 core，便利貼講的「every core's TLB」畫面上看不到。
- **「private」與「shared」同時出現**：便利貼說 TLB 是 private，藍色方塊說 TLB 是 shared by T0 and T1。意思應該是「每個 core 私有、core 內的 thread 共用」，但讀者要自己拼起來。
- **標題說 kernel「walks」the page table，畫面只有一個 `read pte[h]` 箭頭**。是走好幾層還是讀一格，看不出來。
- **`One access, three outcomes` 的三種結果，畫面只畫了第二種**（TLB miss、page in a frame）。第三種提到的 LZ4 HW 與 compressed page 完全沒有畫。
- **user SW 換了位置**：圖 1 在 T0，這張在 T1。這張的 T0 變成 `busy with other work`。
- 圖 1 的 `CPU MMU` 方塊在這張不見了，只剩 `TLB of Core 0`。L1、L2 也沒有畫。對這張的重點來說可以接受，但讀者會找一下。

### 3. 圖說的一句話（不看 Key point）

Core 0 的 T1 發生 TLB miss 時，exception 讓 kernel SW 在同一個 thread 上跑起來，它去 DRAM 讀 page table、把 entry 寫進 TLB，然後 user SW 重做那次存取就 hit 了；同一個 core 的另一個 thread 不受影響。

### 4. 畫面和 Key point 一不一致

Key point：`The CPU never reads the page table. Every decompression fault starts as a TLB miss, so the kernel is already on this path.`

**部分一致。**

- 第一句一致：讀 page table 的箭頭只從 kernel SW instance 出發，page table 方塊也寫了 only by the kernel。
- 第二句畫面沒有畫：「decompression fault」這個詞在畫面上沒有出現過。最接近的是文字框第三行 `TLB miss, page compressed: the kernel calls the LZ4 HW, then refills`。讀者要從那一行文字推出第二句，畫面本身沒有畫解壓縮。
- 小地方：kernel 也是在 CPU 上跑的，「The CPU never reads the page table」嚴格說不對。副標題的「No hardware page table walk」比較準確。

### 5. 困惑指數

**2。** 編號 1 到 5 讓流程很好跟；扣分在步驟 5 沒箭頭、`pte[h]` 沒解釋、Key point 的後半句只靠一行文字支撐。

### 6. 可疑的錯字或多餘文字

- 沒有看到錯字。
- `2 miss: exception` 字體被壓窄，而且緊貼著步驟 4 的紫色箭頭，遠看像是同一條線的標籤。
- 標題的橘色底線在「Page」底下斷開並往下彎，穿過 g 的尾巴。
- 文字框第三行的 `then refills` 單獨掉到下一行並且靠右，看起來像另一項。

---

## 圖 3：One Kernel, Many Instances

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 角色清不清楚 |
|---|---|---|---|
| 紫色實線長框 | `kernel SW code: one copy in DRAM` | 往下用紫色虛線連到三個 instance，第一條標 `same code` | 清楚 |
| 三個黑框 | `Core 0`、`Core 1`、`Core N` | 各裝一個 kernel SW instance | 清楚。但**這張的 core 裡沒有 T0、T1**，也沒有 TLB |
| 三個紫色虛線框 | `kernel SW instance / own stack` | Core 0 的那個 `inside: holds mm_lock`，箭頭伸進灰框；Core 1 的那個 `waits for mm_lock`，箭頭停在灰框邊上；Core N 的那個 `waits for its job, holds no lock`，箭頭指到 LZ4 HW | 前兩個清楚。第三個在等什麼不夠清楚，見下 |
| 紅色鎖頭 | `mm_lock` | 掛在灰色粗框的上緣 | 清楚 |
| 灰色粗圓角框 | 無標籤（鎖頭掛在上面） | 把三個表圍起來 | 清楚，看得出是「要拿鎖才能進來的範圍」 |
| 白色方塊 | `page table` | 被 Core 0 的 instance 碰 | 清楚 |
| 白色方塊 | `kernel tables / state, bitmap, free_stack` | 沒有箭頭碰它 | **不清楚**。三個名字都沒有解釋 |
| 白色方塊 | `COT` | 沒有箭頭碰它 | **不清楚**。縮寫沒有展開，完全猜不到 |
| 綠色方塊加齒輪 | `LZ4 HW / one engine` | 被 Core N 的 instance 指著 | 是誰清楚（壓縮硬體，只有一個）。在做什麼沒有畫 |
| 藍色外框的長條 | `One page fault takes mm_lock twice`，三格 | 文字說明：拿鎖查表拿 frame、不拿鎖讓 LZ4 HW 解壓縮、拿鎖 map | 清楚 |

這張沒有 user SW，沒有任何人物。

### 2. 看不懂的線或物件

- **`COT` 是什麼完全不知道**。
- **`kernel tables: state, bitmap, free_stack`**：是誰的 state、什麼的 bitmap、free 的是什麼，都沒有說。而且 page table 也是 kernel 的表，為什麼和 `kernel tables` 分成兩格，看不出來。
- **`waits for its job` 有兩種讀法**：在排隊等 LZ4 HW 有空，或是工作已經交給 LZ4 HW、在等它做完。這兩種對「LZ4 HW 是不是瓶頸」的意思差很多。
- **Core 0 的箭頭只落在 `page table` 上**。拿到 mm_lock 之後是三個表都能碰，還是只碰 page table？
- **底部三格和上面三個 core 的位置剛好上下對齊，但內容對不上**。第二格 `no lock: the LZ4 HW decompresses` 在 Core 1 正下方，而 Core 1 是在等鎖；第三格 `mm_lock: map the page` 在 Core N 與 LZ4 HW 正下方，而 Core N 是沒拿鎖在等 LZ4 HW。讀者容易把三格當成三個 core 各自的狀態。其實三格是一次 fault 的三個階段，沒有箭頭或編號說明這是時間順序。
- **「page fault」是新出現的詞**。圖 2 用的是 TLB miss，圖 2 的 Key point 用的是 decompression fault，這張用 page fault。三個詞是不是同一件事，圖上沒有交代。
- **`own stack` 與 `free_stack` 兩個 stack 同時出現**，意思不同。
- **紫色虛線有兩種用法**：虛線框是 instance，虛線直線是「same code」。可以接受，但 `same code` 只標在第一條線上。
- 圖 2 的 `page table` 在 Core 0 的外面、標了 `in DRAM`；這張的三個表在哪裡沒有寫。

### 3. 圖說的一句話（不看 Key point）

kernel 的程式碼只有一份，每個 core 上各跑一個 instance、各用自己的 stack；要碰共用的表（page table、kernel tables、COT）得先拿 mm_lock，一次只進一個，而等 LZ4 HW 的時候不拿鎖。

### 4. 畫面和 Key point 一不一致

Key point：`Up to one instance per hardware thread runs at the same time. They meet only at the locks and at the one LZ4 HW.`

**部分一致。**

- 一致的部分：很多個 instance 同時存在、會在 mm_lock 碰頭，畫面有畫。
- 不一致一：**Key point 說「每個 hardware thread 一個 instance」，畫面畫的是每個 core 一個 instance**。這張的 core 裡沒有 T0、T1。只看畫面會算成 3 個，照 Key point 是 core 數乘 thread 數。
- 不一致二：**Key point 說「the locks」複數，畫面只有一把 mm_lock**。
- 不一致三：**Key point 說它們在 LZ4 HW 碰頭，畫面上只有一個 instance 指著 LZ4 HW**，沒有畫出兩個 instance 搶同一個 engine。
- 底部藍框「One page fault takes mm_lock twice」是另一個結論，Key point 沒有提到它。這張圖其實有兩個重點。

### 5. 困惑指數

**3。** 大意（同一份 code、很多 instance、一把鎖、LZ4 HW 在鎖外面）十秒內看得出來；但 `COT` 猜不到、core 與 thread 的數量和 Key point 對不上、Core N 在等什麼有兩種讀法，這三件事光靠畫面解不開。

### 6. 可疑的錯字或多餘文字

- 沒有看到錯字。
- `COT` 是沒有展開的縮寫。
- `waits for its job, holds no lock` 字體被壓窄，而且一路寫到圖的右邊界，最後的 `lock` 幾乎貼邊。
- `same code` 只出現一次，另外兩條虛線沒有標。

---

## 圖 4：One LZ4 HW Serves Every Core

### 1. 人物與機器

| 物件 | 標籤 | 在做什麼 | 角色清不清楚 |
|---|---|---|---|
| 兩個紫色虛線框 | `kernel SW instance / on Core 0`、`kernel SW instance / on Core 1` | 各有一條紫色箭頭指到 job ring，第一條標 `write a descriptor`。Core 1 的那個另外收到一條綠色的 `interrupt to one core` | 清楚。是送工作的人。這張沒有畫 core 的外框 |
| 灰色粗圓角框，裡面一排格子 | `job ring, 16 slots` | 收 descriptor，再用 `JOB_TAIL: doorbell` 通知 LZ4 HW | 清楚 |
| 紅色鎖頭 | `ring_lock` | 掛在 job ring 的灰框上緣 | 清楚 |
| 一排格子，沒有外框、沒有鎖 | `completion ring, 16 entries` | 收 LZ4 HW 的 `completion`，再發 interrupt | 清楚 |
| 綠色方塊加齒輪 | `LZ4 HW`，三行：`one engine, one job at a time`、`keeps no state between jobs`、`computes and checks CRC-32` | 收 doorbell、送 completion，和 DRAM 之間有 `stream` 與 `page` 兩條雙向箭頭 | 清楚 |
| 白色長條分三段 | `DRAM`；斜線段 `chunk pool: compressed streams`；右段 `frame region: 4096 B pages`，裡面四個小方格 | 被 LZ4 HW 讀寫 | 清楚。斜線代表壓縮過的資料，靠標籤看得出來 |
| 藍色方塊，孤立在左下角 | `L1 and L2 caches`，底下三行藍字 | 沒有任何線接它。藍字說 `not on this path` | 是誰清楚。底下後兩行在說什麼不夠清楚，見下 |

這張沒有 user SW，沒有任何人物。

### 2. 看不懂的線或物件

- **ring 的格子數和標籤對不上**。job ring 與 completion ring 我各數到大約 10 格，標籤寫 16 slots 與 16 entries。
- **`interrupt to one core` 是哪一個 core**。箭頭只指到 Core 1 的 instance。是送工作的那個 core 收，還是固定某一個 core 收？Core 0 送的工作做完了誰通知它？
- **`JOB_TAIL: doorbell` 的箭頭從 job ring 出發**，看起來像 ring 自己去通知 LZ4 HW。箭頭是紫色（前面幾張紫色是 kernel），所以我猜是 kernel 寫 JOB_TAIL，但畫面上起點不是 kernel。`JOB_TAIL` 是什麼（暫存器？指標？）也沒有說。
- **job ring 有鎖、completion ring 沒有鎖**，為什麼不一樣沒有說。
- **`stream` 與 `page` 是雙向箭頭**。壓縮與解壓縮時各往哪邊走沒有分開畫。懂的人推得出來，但畫面沒有講。
- **`cache_clean before COMPRESS`、`cache_invalidate after DECOMPRESS`**：上一行才說 cache `not on this path`，下兩行卻說要對 cache 做事。誰做（kernel？）、為什麼要做，沒有說。讀者會問：既然不在這條路上，為什麼還要 clean 與 invalidate？
- **「L1 and L2 caches」方塊用「沒有線」來表示不在路上**。遠看只是一個擺在角落、和其他東西無關的方塊。
- **標題說 Serves Every Core，畫面只有 Core 0 與 Core 1**。圖 1 與圖 3 有 `Core N` 與省略號，這張沒有。
- **ring 放在哪裡沒有說**（DRAM 裡？LZ4 HW 的暫存器？）。
- **`computes and checks CRC-32` 是算什麼的 CRC** 沒有說。
- **`ring_lock` 與圖 3 的 `mm_lock` 是什麼關係**沒有交代。圖 3 說解壓縮那一段是 `no lock`，這張又多一把 ring_lock。

### 3. 圖說的一句話（不看 Key point）

各個 core 上的 kernel instance 把工作的 descriptor 排進同一個有鎖的 job ring，唯一的 LZ4 HW 一次做一件，直接和 DRAM 裡的 chunk pool 與 frame region 交換資料，做完經 completion ring 發 interrupt 回來；L1 與 L2 不在這條資料路徑上。

### 4. 畫面和 Key point 一不一致

Key point：`ring_lock covers only queuing a job. The LZ4 HW reads and writes DRAM with physical addresses, so L1 and L2 never see that data.`

**部分一致。** 兩個主要說法畫面都有畫，差在下面三點。

- 一致：鎖頭只掛在 job ring 上，completion ring、LZ4 HW、DRAM 都沒有鎖。LZ4 HW 的資料箭頭直接到 DRAM，cache 方塊孤立在旁邊。
- 落差一：**「with physical addresses」畫面上沒有**。`stream` 與 `page` 兩條箭頭沒有標 PA。
- 落差二：**「用 physical address，所以 L1 與 L2 看不到」這個因果讀起來不通**。圖 1 明明寫 L2 `sees physical addresses only`。cache 看不到的原因應該是 LZ4 HW 直接接 DRAM、不經過 cache，和用哪一種位址無關。
- 落差三：**「never see that data」和畫面的 `cache_clean`、`cache_invalidate` 兩行互相拉扯**。如果 cache 從來沒有那份資料，就不需要 clean 與 invalidate。比較準確的說法應該是「LZ4 HW 的讀寫不經過 cache，所以 kernel 要自己讓 cache 與 DRAM 一致」。

### 5. 困惑指數

**2。** 從 descriptor、ring、doorbell、LZ4 HW、DRAM、completion 到 interrupt 可以一路跟完；扣分在格子數與標籤不合、interrupt 給誰不明、cache 那三行自己打架。

### 6. 可疑的錯字或多餘文字

- 沒有看到錯字。
- **ring 畫 10 格左右，標籤寫 16**。兩個 ring 都是。
- `JOB_TAIL`、`COMPRESS`、`DECOMPRESS`、`cache_clean`、`cache_invalidate` 是沒有解釋的識別字。應該是刻意保留的名字，但對冷讀者是五個生字。
- Key point 那一行字很長，字體被壓窄，是四張裡最擠的一條。

---

## 跨圖的觀察

### 命名物件每張長得一不一樣

| 物件 | 出現在 | 長相 | 有沒有走樣 |
|---|---|---|---|
| `kernel SW instance` 紫色虛線圓角框 | 圖 2、3、4 | 三張都是紫色虛線、粗體名稱加一行小字 | 外觀一致。**容器走樣**：圖 2 在 thread 裡（`running on T1`），圖 3 在 core 裡、沒有 thread（`own stack`），圖 4 沒有 core 外框（`on Core 0`） |
| 紅色鎖頭 | 圖 3、4 | 紅色、鎖著、名字用紅字寫在右邊、掛在灰色粗框上緣 | 一致 |
| 灰色粗圓角框（要拿鎖才能進的範圍） | 圖 3、4 | 一致 | 一致 |
| `LZ4 HW` 綠色方塊加齒輪 | 圖 3、4 | 綠底、粗黑框、右上角齒輪 | 一致 |
| `Core` 黑色圓角框 | 圖 1、2、3 | 一致 | 圖 4 沒有 core 框 |
| `T0`、`T1` 白色小格 | 圖 1、2 | 一致 | **圖 3 不見了**，而圖 3 的 Key point 正好在講 hardware thread |
| `user SW` 火柴人加 laptop | 圖 1、2 | 圖 1 很小、站姿、在 T0；圖 2 大很多、坐姿、在 T1 | **走樣**：大小、姿勢、所在的 thread 都不同。圖 3、4 完全沒有 |
| TLB | 圖 1、2 | 圖 1 是 `CPU MMU: one TLB / VA to PA`；圖 2 是 `TLB of Core 0` | 顏色一致，名稱與範圍不同（MMU 方塊在圖 2 不見了） |
| `page table` 白色方塊 | 圖 2、3 | 圖 2 在 core 外面、寫 `pte[h]` 與 `in DRAM`；圖 3 在鎖的範圍裡、只有名字 | 可以認得是同一個東西 |
| `DRAM` 白色長條 | 圖 1、4 | 圖 1 是空的；圖 4 分成 chunk pool 與 frame region | 可以接受，圖 4 是放大 |
| L1、L2 藍色方塊 | 圖 1、4 | 圖 1 分開；圖 4 併成一塊 | 一致 |
| 黃色便利貼 | 圖 1、2 | 圖 1 有陰影沒有折角；圖 2 有折角 | 小差異。圖 3、4 沒有便利貼 |
| 說明用的文字框 | 圖 2、3 | 圖 2 是黑框黑字標題；圖 3 是藍框藍字標題 | **走樣**：同一種東西兩種畫法 |
| 標題列（編號方格、橘色底線、藍色副標題）與 Key point 列 | 四張 | 一致 | 圖 3 的 Key point 標籤是圓角，其他三張是直角。很小 |

### 分類顏色每張一致嗎

- **紫色＝kernel SW**：圖 2、3、4 一致。
- **綠色＝LZ4 HW**：圖 3、4 一致。圖 4 的綠色箭頭都是 LZ4 HW 發出的。
- **紅色＝鎖**：圖 3、4 一致。
- **藍色填滿＝CPU 這邊的硬體（MMU、TLB、L1、L2）**：圖 1、2、4 一致。
- **橘色＝user SW 的存取路徑**：圖 1、2 一致。圖 3、4 沒有橘色的路徑，只剩標題底線是橘色。
- **藍色的字用得太多種**：四張的副標題、圖 2 的步驟 5、圖 3 說明框的外框與標題、圖 4 cache 底下的三行註解。藍字沒有固定的意思。
- **斜線＝壓縮過的資料**：只在圖 4 出現，靠標籤看得懂。
- **四張都沒有圖例**。顏色的意思都是我連著看四張猜出來的。只看單張的人猜不到。

### 故事線順不順

順序是合理的：圖 1 硬體長什麼樣、hit 時怎麼走；圖 2 miss 時 kernel 怎麼進來；圖 3 很多個 kernel 同時進來時在哪裡碰頭；圖 4 其中一個碰頭點 LZ4 HW 怎麼排隊、資料怎麼走。每一張的 Key point 都有替下一張鋪路。

斷掉的地方：

1. **沒有一張說為什麼要壓縮**。「記憶體壓縮」的目的、page 什麼時候被壓起來、誰決定壓，四張都沒有畫。壓縮這個方向只出現在圖 2 便利貼的一行字與圖 4 的 `cache_clean before COMPRESS`。整組圖畫的其實只有解壓縮這一邊。
2. **圖 2 到圖 3 換了詞**。圖 2 畫面是 TLB miss，圖 2 的 Key point 是 decompression fault，圖 3 是 page fault。讀者不確定這三個是不是同一條路。
3. **圖 2 到圖 3 從 thread 換成 core**。圖 2 很仔細地畫了「instance 跑在 T1、T0 不受影響」，圖 3 的 core 裡卻沒有 thread，Key point 又回頭講 hardware thread。
4. **user SW 在圖 2 之後消失**。圖 1、2 的主角是發出存取的 user SW，圖 3、4 沒有它。故事停在圖 4 的 `interrupt to one core`，沒有回到「user SW 重做存取、拿到資料」。讀者看不到一次完整的來回。
5. **圖 3 的 `COT`、`kernel tables` 沒有前後文**。前後三張都沒有再提到。
6. **兩把鎖的關係沒有交代**。圖 3 是 mm_lock，圖 4 是 ring_lock。圖 3 的三格說解壓縮那一段是 `no lock`，圖 4 卻有 ring_lock。要讀到圖 4 的 Key point「covers only queuing a job」才拼得起來。
7. **user SW 在圖 1 是 T0、圖 2 是 T1**。不影響理解，但連著看會以為是故意的而去找原因。

### 我用自己的話講這組圖的結論

這個 processor 沒有硬體 page table walk，所以每一次 TLB miss 本來就要進 kernel；page 被壓縮時的解壓縮只是在這條本來就有的路上多做一段。kernel 的程式碼只有一份，但每個 hardware thread 都可能同時跑一個 instance；這些 instance 平常各做各的，只會在三個地方互相等：碰共用的表要拿的 mm_lock、把工作排進 job ring 要拿的 ring_lock、以及只有一個、一次只做一件的 LZ4 HW。LZ4 HW 直接讀寫 DRAM、不經過 L1 與 L2，所以 kernel 要自己負責讓 cache 和 DRAM 對得上。

我講不出來的部分：這組圖沒有告訴我壓縮是為了什麼、要花多少時間、mm_lock 或那一個 LZ4 HW 會不會是瓶頸。圖一再強調「one」（one L2、one kernel、one lock、one engine、one ring），像是在指出共用的資源在哪裡，但沒有下「所以會怎樣」的結論。

### 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與 Key point |
|---|---|---|---|
| 1 The Processor: Per Core and Shared | 2 | 是（T0、T1 沒有展開） | 部分一致：TLB hit 與 kernel 畫面上都沒有 |
| 2 TLB Miss: The Kernel Walks the Page Table | 2 | 是（`instance` 一詞要到圖 3 才懂） | 部分一致：decompression fault 沒有畫，只有一行字 |
| 3 One Kernel, Many Instances | 3 | **否**（`COT`、`kernel tables` 不明；Core N 在等什麼不明） | 部分一致：畫每 core 一個，Key point 說每 hardware thread 一個；鎖畫一把說複數；LZ4 HW 沒有畫出碰頭 |
| 4 One LZ4 HW Serves Every Core | 2 | 是 | 部分一致：physical addresses 沒畫，「所以 cache 看不到」因果不通，和 cache_clean 兩行互相拉扯 |

四張沒有一張是「不一致」，也沒有一張是完全「一致」。

### 建議重生哪幾張

依照「困惑指數 3 以上、或角色不清、或畫面與結論不一致」的條件：

**建議重生：圖 3。** 三個條件中了兩個（困惑指數 3、角色不清），而且畫面與 Key point 的落差是四張裡最大的。重生時要處理：

- core 裡畫出 T0、T1，讓 instance 落在 thread 上，和圖 2 接得起來，也和 Key point 的「per hardware thread」對得上。
- `COT` 展開或加一行說明。`kernel tables` 的三個名字也要有一句話，或者乾脆不列。
- Core N 的那個 instance 是「排隊等 LZ4 HW」還是「等 LZ4 HW 做完」，寫清楚。如果 Key point 要說「在 LZ4 HW 碰頭」，就畫兩個 instance 都指向它。
- 底部三格加上 1、2、3 或箭頭表示時間順序，並且不要和上面三個 core 上下對齊。
- 「page fault」和圖 2 的用詞對齊。
- Key point 的「the locks」如果指的是 mm_lock 加上圖 4 的 ring_lock，這張要嘛只說 mm_lock，要嘛把 ring_lock 也畫出來。

**不必重生、但畫面與 Key point 只有部分一致，改字或小修就夠的：**

- **圖 1**：在 PA 箭頭旁加 `TLB hit`，或把 Key point 改成和標題一致的結論（誰是 per core、誰是 shared）。現在 Key point 講的 kernel 在畫面上不存在。如果這一組的出圖方式沒辦法只改字，圖 1 是第二個該重生的。
- **圖 2**：步驟 5 補箭頭；`pte[h]` 的 h 加說明；`read only by the kernel` 改成不會讀成 read-only 的寫法；user SW 的 thread 位置和圖 1 對齊。
- **圖 4**：ring 的格子數和 16 對齊（畫 16 格，或畫幾格加省略號）；`interrupt to one core` 說明是哪一個 core；Key point 的因果改成「不經過 cache」而不是「用 physical address」；cache 底下三行說明是誰做、為什麼做。

**整組的問題（不是哪一張重生就能解決的）：**

- 四張都沒有圖例。
- user SW 在圖 3、4 消失，故事沒有回到被服務的人。
- 沒有一張說為什麼要壓縮、page 什麼時候被壓。

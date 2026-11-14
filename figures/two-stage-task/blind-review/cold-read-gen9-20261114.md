# gen9/02 冷讀驗收報告

- 日期：2026-11-14
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：two-stage-task 的 `gen9/02-apart-in-space-and-time.r3.png`

## 第一眼兩秒鐘

最先讀到的是兩組最大的字：左邊藍色的「ON THE ACCESS PATH」與右邊綠色的「OFF THE ACCESS PATH」，接著是左下的「DENSE」與右下的「SPARSE」。標題「CPU MMU and Compression Layer: Apart in Space and Time」在最上面，也很快讀到。主視覺很清楚：左右兩個虛線框對照，上面是「在不在存取路徑上」，下面是「多常發生」。

## 遮住 Key point 之後

### 1. 機器與方塊

左邊藍框（CPU MMU domain）：

| 方塊 | 我的理解 |
|---|---|
| processor | 外框，裡面有 Core 0、Core 1 與共用的 L2 |
| Core 0、Core 1 | 各有兩個 hw thread、一個「CPU MMU and TLB」、一個 L1 |
| hw thread | 發出 load 與 store 的執行單位 |
| CPU MMU and TLB | 每個 core 一個，每次存取都經過 |
| L1 | 每個 core 自己的 cache |
| L2 | 兩個 core 共用的 cache |
| kernel SW: TLB miss（紫色虛線） | TLB miss 時被叫起來的 kernel 程式：讀一個 PTE、填 TLB |
| page table, in DRAM | kernel SW 讀的表 |

中間：

| 方塊 | 我的理解 |
|---|---|
| frame region | 三個空格，「hot pages, used by both」。存放沒壓縮、正在用的 page。L2 miss 時去讀它，LZ4 HW 的 DECOMPRESS 寫進它 |
| 「one kernel SW, two separate jobs and tables」 | 說明左右兩個紫色虛線框是同一份 kernel SW，只是兩件不同的工作 |

右邊綠框（compression domain）：

| 方塊 | 我的理解 |
|---|---|
| LZ4 HW（綠底、齒輪） | 壓縮與解壓縮的硬體，標明在 processor 外面 |
| kernel SW: page swap（紫色虛線） | 查 COT，把 job 交給 LZ4 HW |
| COT, in DRAM | 記錄每個壓縮過的 page 在哪裡的表 |
| chunk pool（斜線方塊） | 壓縮過的冷 page，放在 DRAM |
| 黃色框「Rare, but each one counts」 | 說明 page swap 何時發生、每次有多少成本、要算 WCET |

角色看不出來或沒標籤的：

- **kernel SW 在哪裡跑沒有畫出來。** 兩個紫色虛線框都畫在 processor 外面，沒有背景的讀者可能以為 kernel SW 是另一台機器或另一塊硬體。虛線大概代表「軟體」，但圖上沒有圖例說明虛線的意思。
- **COT 沒有展開全名。** 只寫「where each compressed page is」，功能看得懂，縮寫是什麼看不出來。PTE 也沒展開，不過懂 MMU 的人大多認得。
- **frame region 沒有標「in DRAM」。** page table、COT、chunk pool 都標了 in DRAM，唯獨 frame region 沒標，讀者要從「on an L2 miss」自己推它在 DRAM。圖上也沒有一個 DRAM 方塊，所以副標題說 compression layer「stands beside DRAM」時，畫面上找不到那個 DRAM。

### 2. 看不懂的線或物件

- **LZ4 HW 的箭頭只畫輸出。** COMPRESS 只畫 LZ4 HW 到 chunk pool，DECOMPRESS 只畫 LZ4 HW 到 frame region。COMPRESS 從哪裡讀（frame region）、DECOMPRESS 從哪裡讀（chunk pool）都沒畫，讀者可能以為資料本來就在 LZ4 HW 裡面。這不妨礙主旨，但資料流是半條。
- **「which chunks」與「one PTE」兩條箭頭的方向。** 箭頭從 kernel SW 指向表，標籤卻是讀回來的東西（一個 PTE、哪些 chunk）。圖內兩邊用同一個慣例，所以不算矛盾，但第一次看會遲疑一下：是寫進表，還是從表讀出？
- **「hot pages, used by both」的「both」**：指兩個 domain，還是兩個 core？我猜是兩個 domain（CPU 讀、LZ4 HW 寫），但不確定。
- **只有 Core 1 畫了存取路徑與 TLB miss 箭頭**，Core 0 沒有。看得出是舉例，不算問題。
- **page swap 是怎麼被觸發的沒有畫。** 左邊的存取找不到 page 時，怎麼變成右邊的 page swap，圖上沒有線。這大概是刻意的（強調兩邊分開），黃色框也有一句「when the pages in use outgrow the frame region」，所以只是小缺口。

### 3. 圖說的一句話

CPU MMU 在每個 core 裡、每次存取都在路上，常常叫 kernel SW；壓縮層在 processor 外面，只在 page swap 時才動，很少，但每次都很重。

### 4. 架構上的差異（只看上半部）

最本質的差異是**位置：CPU MMU 在 processor 的每個 core 裡、在每次 load/store 的路徑上；LZ4 HW 在 processor 外面、不在存取路徑上，只碰 DRAM 裡的資料**。讀出來的依據：大字「ON THE ACCESS PATH」與「OFF THE ACCESS PATH」、「every load and store goes through the TLB of its core」、「CPU MMU and TLB」畫在每個 core 方塊裡、LZ4 HW 標「outside the processor」、橘色存取線從 hw thread 一路到 L2 再到 frame region 而完全不經過右邊。另外兩邊各有自己的表（page table 與 COT），中間那句「two separate jobs and tables」把它點明。

### 5. 時間上的差異（只看下半部）

- TLB lookup：幾乎連成一片的橘色細線，數不清，看起來是幾百次。
- kernel SW: TLB miss：大約 17 根紫色短線。
- page swap：同一段時間只有 2 次。

所以 TLB lookup 與 page swap 差了兩個數量級以上；TLB miss 與 page swap 看起來只差約 8 倍。圖上註明「spacing not measured」，所以我不把這些比例當成數字，只讀成「很密」對「很稀」。有一點要提醒：如果實際上 TLB miss 比 page swap 多出好幾個數量級，畫面上 17 比 2 的比例可能讓讀者低估兩者的差距。

## 6. 讀 Key point 之後：畫面與結論一致嗎

**一致。** Key point 說：CPU MMU 在每個 core 裡、每次存取都經過、常常叫醒 kernel SW；壓縮層在外面、在 DRAM 旁、只在 page swap 時工作，很少但每次都算進 worst case。這四點畫面都有：core 裡的「CPU MMU and TLB」、ON THE ACCESS PATH、DENSE 的紫色線、「outside the processor」、OFF THE ACCESS PATH、SPARSE、黃色框的「budget the WCET」。唯一對不太上的是「beside DRAM」：畫面沒有 DRAM 方塊，只有「in DRAM」的標籤，所以「旁邊」這個空間關係要靠讀者自己想像。

## 7. 困惑指數

**2 / 5。** 主旨一眼就懂，對照結構清楚；扣分在 kernel SW 畫在 processor 外面、COT 沒展開、LZ4 HW 的資料流只畫一半、沒有 DRAM 方塊。

## 8. 可疑的錯字或多餘文字

- 沒看到拼錯的字。
- 「only when a page swaps」這個意思出現四次（副標題、OFF THE ACCESS PATH 下方、SPARSE 旁、Key point），稍微重複，但對冷讀者其實有幫助，不算錯。
- 「a page swaps」把 swap 當不及物動詞用，略為口語，意思仍清楚。
- 「Rare, but each one counts」與 Key point 的最後一句意思重複，可以接受。

## 結論

**用我自己的話說：** 這顆 processor 的 CPU MMU 和壓縮層是兩件分開的事。CPU MMU 長在每個 core 裡，每一次讀寫都要過它，TLB 沒中就叫 kernel SW 來補，所以很頻繁。壓縮層（LZ4 HW 加上 kernel SW 的 page swap 與 COT）在 processor 外面，平常不在存取路徑上，只有正在用的 page 多到放不下、要換 page 時才出手。它很少發生，但每次都要拿 lock、查 COT、跑一個 LZ4 HW job，所以要用 worst case 來估。

## 總表

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 / 5 |
| 角色是否清楚 | 是（kernel SW 的執行位置與 COT 全名是小缺口） |
| 畫面與結論是否一致 | 一致 |

## 是否建議重生

**不建議重生。** 困惑指數低於 3、角色清楚、箭頭方向沒有和故事矛盾、畫面與 Key point 一致。如果之後要再修，可以考慮的小改動（都不是必要）：

1. 在紫色虛線框附近註明 kernel SW 跑在 core 上，或加一個「dashed = software」的圖例。
2. COT 第一次出現時寫全名。
3. frame region 補上「in DRAM」，或把 page table、frame region、chunk pool、COT 收進一個 DRAM 框，讓「beside DRAM」在畫面上看得到。
4. LZ4 HW 補上讀的那一半（frame region 到 LZ4 HW 的 COMPRESS 輸入、chunk pool 到 LZ4 HW 的 DECOMPRESS 輸入）。

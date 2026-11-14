# 冷讀報告：Apart Even in Software

- 日期：2026-11-14
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：two-stage-task 的 `gen6/03-apart-even-in-software.r2.png`

## 第一眼兩秒鐘

左右兩個大虛線框，左邊藍色，右邊綠色，中間一條紫色箭頭穿過一個三格的小佇列把兩邊接起來。兩個框底下各有一行很大的字：左邊「ONE PER CORE」，右邊「ONE SHARED SET」。最先抓到的是這兩行大字的對比：左邊每個 core 一份，右邊大家共用一份。下半部是一張三列的表和一張黃色便利貼。

## 遮住 Key point 之後

### 1. 機器與方塊

| 方塊 | 標籤 | 我讀到的角色 |
|---|---|---|
| 左邊藍色虛線大框 | CPU MMU domain | 一個範圍，涵蓋 CPU 這邊的記憶體管理 |
| 框內實線框 | processor | 處理器本體，裡面有兩個 core |
| 兩個 core 框 | Core 0、Core 1 | 兩個 core，內容一模一樣 |
| 淺藍實心框（每個 core 一個） | CPU MMU and TLB | 每個 core 自己的硬體 MMU 與 TLB |
| 紫色虛線框（每個 core 一個） | TLB miss handler / runs on this core | TLB miss 時跑的軟體，在發生 miss 的那個 core 上跑。紫色虛線我猜代表「軟體」，但圖上沒有圖例 |
| 中間三格小方塊 | request queue | 兩邊之間的請求佇列，三格是空的 |
| 右邊綠色虛線大框 | compression domain，右上角掛「PROPOSAL」 | 壓縮這一層的範圍。PROPOSAL 只掛在右邊，我讀成「右邊是提案，左邊是現況」 |
| 紫色虛線框 | kernel SW: one manager / takes every request, owns the tables | 一個集中的軟體管理者，收所有請求，擁有「表」。是哪些表沒有說 |
| 綠色實心框，有齒輪 | LZ4 HW / shared by all cores | 壓縮硬體，所有 core 共用 |
| 綠色虛線框 | future HW assists / one shared set, beside the LZ4 HW / CRC, headers, chunk lists | 未來可能加的硬體輔助，虛線表示還不存在 |
| 黃色便利貼 | Why not co-design them | 三條理由 |
| 表格 | Where each one grows | 兩個 domain 在三個面向上的對比 |

沒有無標籤的方塊。角色大致都看得出來。看不出來或有疑問的：

- 「kernel SW: one manager」實際在哪裡跑？它是軟體，軟體總要在某個 core 上執行，但圖把它畫在 processor 框外面、和 core 沒有任何關係。有硬體背景的讀者會問：這個 manager 跑在哪個 core？會不會跟 TLB miss handler 搶同一個 core？
- 「owns the tables」的 tables 是哪些。如果包含 page table，那左邊的 TLB miss handler 也要讀 page table，兩邊其實共用資料結構，這和「分開設計」的主張有點衝突。
- 整張圖沒有 DRAM。題目是 DRAM 壓縮，但 LZ4 HW 壓的資料從哪來、放到哪去，圖上看不到。對這張圖的論點不是必要，但第一次看的人會找。

### 2. 看不懂的線或物件

- **「a narrow link: requests in, PTE updates and TLB clears back」**：文字說有兩個方向（請求進去、PTE 更新與 TLB 清除回來），但圖上只畫了一個方向的箭頭（左到右）。「回來」的那條沒有畫。而且 TLB clear 要回到「每一個 core 的 TLB」，這正是兩邊的接觸點，圖上反而沒有表現。
- **「page fault from any core」箭頭**：起點是 processor 框的右邊緣，不是某個 core，也不是 TLB miss handler。看不出是誰送出 page fault：是 MMU 硬體？還是 TLB miss handler 查表發現 page 不在之後轉送？
- **「one at a time」與「may dispatch to parallel workers, for throughput, not per core」**：一句說一次一個，下一句說可以分派給平行的 worker。讀者會不確定是「從佇列取請求一次一個，但之後可以平行處理」，還是兩者矛盾。「one at a time」也讓人擔心所有 core 的 fault 被這裡序列化，成為瓶頸。
- **「a sub-action, once verified in SW」**：意思大概是「某個小動作先在軟體裡驗證過，才搬到硬體」，但第一次看會以為是執行時每次都要先在 SW 驗證。
- **虛線的意思不一致**：藍/綠大框的虛線代表「範圍」，紫色虛線代表「軟體」，綠色小框的虛線代表「未來的、還沒有的硬體」。同一種線型三種意思。
- **黃色便利貼的空核取方塊**：核取方塊通常代表待辦或可勾選的選項，放在「理由」前面會讓人以為這些是還沒確認的項目。
- **「tied」底下的底線**：像是強調，也像是手寫時多劃的一筆。

### 3. 圖說的一句話（不看 Key point）

CPU 的記憶體管理是每個 core 各一份（TLB 和 TLB miss handler 都在自己的 core 上），壓縮層則是一個所有 core 共用的集中管理者加上共用的 LZ4 HW，兩邊只透過一個請求佇列相接，所以應該分開設計。

### 4. 論點

- **主張**：分開設計。
- **理由**：兩邊「長大的地方」不一樣。CPU MMU 這邊的工作在發生 miss 的 core 上跑，硬體幫手（TLB）放在每個 core 裡，擴充方式是每個 core 一份；壓縮這邊的工作集中在一個 manager，硬體幫手放在 LZ4 HW 旁邊共用，擴充方式是加 worker 和 engine。一起設計會把每個 core 的路徑綁到共用的那條上。
- **有沒有被說服**：大致被說服，尤其是「硬體幫手要放在哪裡」這一點很清楚：一個在 core 裡面，一個在 core 外面共用。
- **讓我懷疑的地方**：
  1. 「長大的地方不同」是硬體擺放的論點，但標題說的是「即使在軟體裡也要分開」。軟體這一層兩邊都是 kernel SW、都在同樣的 core 上跑，圖沒有說明為什麼軟體也要分開，只是把 manager 畫在 processor 外面，看起來像繞過了這個問題。
  2. 「narrow link」是用文字宣稱的，畫面上沒有證明它窄。回程的 PTE 更新與 TLB 清除要碰到每一個 core 的 TLB，這是兩邊最密切的接觸，圖上沒畫。
  3. 「owns the tables」如果包含 page table，TLB miss handler 就要讀壓縮這邊擁有的表，兩邊的資料結構其實重疊。
  4. 「one at a time」讓集中式 manager 看起來是瓶頸，反而可能讓主張一起設計的人覺得：fault 的延遲取決於兩邊，所以要一起看。

### 5. 讀 Key point 之後

Key point：即使是純 kernel SW，壓縮層也和 CPU MMU 的 kernel SW 分開設計；它未來的硬體幫手是放在 LZ4 HW 旁邊的一套共用的東西，不是放在每個 core 裡；兩邊只在一個窄介面相接。

**一致。** 畫面上的「ONE PER CORE / ONE SHARED SET」、future HW assists 的位置、request queue 都對應到 Key point 的每一句。唯一的小落差是「narrow interface」在畫面上只畫了單向的箭頭，回程沒有畫。

### 6. 困惑指數

**2**。主訊息（每個 core 一份 vs 共用一份，所以分開設計）兩秒內就讀得出來；扣分在單向箭頭與「回程」文字不符、「one at a time」與「parallel workers」並列、manager 跑在哪裡沒交代。

### 7. 可疑的錯字或多餘文字

- 沒有看到拼字錯誤。
- 「tied」下面的底線像是多餘的筆畫。
- 黃色便利貼前面的空核取方塊是多餘的符號，容易被讀成待辦清單。
- 「PROPOSAL」只標在右邊，意思合理，但沒有對應「左邊是現況」的標示，是否刻意不確定。

## 顏色

| 顏色 | 我讀到的意思 | 一致嗎 |
|---|---|---|
| 藍色（大框、大字、淺藍實心） | CPU MMU / 每個 core 的硬體 | 一致。但 request queue 底下的說明文字「a narrow link...」也用藍色，和 CPU MMU 的顏色撞在一起，容易誤以為那段話屬於左邊 |
| 綠色（大框、大字、LZ4 HW、future HW assists） | 壓縮這一層、共用的硬體 | 一致 |
| 紫色（虛線框、箭頭、箭頭上的字） | kernel SW 以及請求的流動 | 大致一致：軟體方塊和軟體送出的請求都是紫色。沒有圖例，要自己猜 |
| 橘色 | 標題底線 | 只是裝飾 |
| 黃色 | 結論便利貼 | 一致 |

線型（虛線）的意思不一致，見第 2 點。

## 用我自己的話說結論

CPU 管記憶體的那套東西是「每個 core 各帶一份」，壓縮層是「全部 core 共用一份」。兩者擴充的方向不同，就算現在壓縮層只是軟體，也不要和 CPU MMU 的軟體綁在一起設計；兩邊只透過一個請求佇列交換請求和結果，未來要加硬體也是加在 LZ4 HW 旁邊，不是加進 core 裡。

## 總表

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 |
| 角色是否清楚 | 是（manager 跑在哪個 core、tables 指哪些表，未交代） |
| 畫面與結論是否一致 | 一致（回程箭頭缺漏是小落差） |

## 是否建議重生

**不建議重生。** 困惑指數 2、角色清楚、箭頭方向和故事沒有矛盾、畫面與 Key point 一致，都沒有達到重生門檻。

若要小修（不必重生整張），建議：

1. 在 request queue 補一條右到左的回程箭頭，標「PTE updates, TLB clears」，讓「narrow link」的雙向在畫面上成立。
2. 交代 kernel SW manager 在哪裡跑（例如「runs on some core, not tied to the faulting one」），回應「軟體也是在 core 上跑」的疑問。
3. 把「owns the tables」改成具體的表名，讓讀者判斷兩邊有沒有共用資料結構。
4. 拿掉便利貼的空核取方塊與「tied」底下的線。

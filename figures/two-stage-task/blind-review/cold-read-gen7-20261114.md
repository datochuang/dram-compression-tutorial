# 冷讀報告：two-stage-task gen7 第 3 張

- 日期：2026-11-14
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：two-stage-task 的 `gen7/03-apart-even-in-software.png`
- 立場：站在「CPU 的記憶體管理和壓縮層是同一件事、應該一起設計」的團隊成員立場讀

## 第一眼兩秒鐘

左右兩個虛線大框：左邊藍色 `CPU MMU domain`，右邊綠色 `compression domain`。兩邊各有一行超大字：左邊 `ONE PER CORE`，右邊 `ONE SHARED SET`。中間有一個三格的 `request queue`，紫色箭頭一去一回。第一眼得到的訊息是「左邊是每個 core 一份，右邊是全部共用一份，兩邊不一樣」。下方的表格和黃色便條看起來是在重複同一件事。

## 遮住 Key point 後的閱讀

### 1. 機器與方塊

| 方塊 | 標籤 | 我的理解 |
|---|---|---|
| 左邊藍色虛線大框 | `CPU MMU domain` | CPU 記憶體管理的範圍 |
| 黑框 | `processor` | 整顆 processor |
| 兩個黑框 | `Core 0`、`Core 1` | 兩個 core |
| 藍底實線方塊（每個 core 一個） | `CPU MMU and TLB` | 每個 core 自己的 MMU 硬體與 TLB |
| 紫色虛線方塊（每個 core 一個） | `TLB miss handler runs on this core` | TLB miss 時在該 core 上跑的 kernel SW |
| 右邊綠色虛線大框 | `compression domain`，右上角 `PROPOSAL` | 壓縮層的範圍；`PROPOSAL` 看起來表示右邊是提案，左邊是現況，但沒有明說 |
| 紫色虛線方塊 | `kernel SW: one manager`，「takes every request, owns the COT and the chunk pool」 | 一個集中的 kernel SW 管理者。`COT` 沒有解釋，冷讀者不知道是什麼 |
| 綠底實線方塊，有齒輪 | `LZ4 HW`，「shared by all cores」 | 壓縮硬體，全部 core 共用 |
| 綠色虛線方塊 | `future HW assists`，「one shared set, beside the LZ4 HW / CRC, headers, chunk lists」 | 以後可能從 SW 移到 HW 的輔助功能。虛線看起來表示「還不存在」 |
| 三格方塊 | `request queue` | 兩個 domain 之間的佇列 |

角色看不清楚的地方：

- 「may dispatch to parallel workers」的 workers 沒有畫出來。
- 顏色與線型的意思沒有圖例。我是猜的：紫色虛線是 kernel SW，實線色塊是 HW，綠色虛線是未來的 HW。猜得出來，但要猜。
- 頁面上沒有 page table。返回箭頭說「PTE updates」，但看不到 PTE 在哪裡、誰還會讀它。

### 2. 看不懂的線或物件

1. **`page fault from any core` 的箭頭從 processor 框的邊緣出發**，不是從某個 `TLB miss handler` 出發。讀者不知道 fault 是 MMU 硬體丟出來的、還是 TLB miss handler 查表後發現的。這個差別對「要不要一起設計」很關鍵。
2. **返回箭頭 `PTE updates, TLB clears on every core` 繞過 request queue**，直接從 manager 回到 processor。queue 下面的小字說「a narrow link: requests in, PTE updates and TLB clears back」，所以返回也算 narrow link 的一部分，但畫面上 queue 只有一個方向，返回的路線看起來是另一條獨立的線。
3. **manager 畫在 processor 外面**，但小字說它「runs on a core like any kernel SW」。畫面的空間位置與文字矛盾：它實際上跑在左邊那兩個 core 裡。讀者需要自己理解「這裡分的是邏輯上的職責，不是實體位置」。
4. **`a sub-action, once verified in SW`**：意思大概是「一個子動作先在 SW 裡驗證過，才搬到 HW」，但句子很省略，第一次讀會卡住。
5. **`kernel SW can override everything they write`**：they 指 future HW assists，懂了之後合理，但位置在框外，容易誤讀成在講 LZ4 HW。
6. **`PROPOSAL` 標籤**：只蓋在右邊，不確定是指整個右邊、還是指「one manager」這種組織方式。

### 3. 圖說的一句話（不看 Key point）

CPU MMU 那一邊的工作和硬體輔助是每個 core 一份（TLB、TLB miss handler），壓縮層是一個 manager 加上 LZ4 HW 旁邊的一組共用硬體，兩者成長的位置不同，所以即使壓縮層一開始全是 kernel SW，也不該和 MMU 的 kernel SW 一起設計，兩邊只靠一個 request queue 連起來。

### 4. 論點

- **主張**：分開設計。
- **理由**：兩邊「長大的地方」不同。MMU 的硬體輔助長在每個 core 裡（TLB），按 core 數複製；壓縮層的硬體輔助長在 LZ4 HW 旁邊，是一組共用的，靠增加 workers 與 engines 擴充。黃色便條補一句：一起設計的話，per-core 的路徑會被綁到 shared 的路徑上。
- **被說服了嗎**：部分被說服。「硬體輔助放在不同地方、擴充方式不同」這一點講得清楚，我接受兩邊的 HW 不必一起設計。但圖的標題是「Apart Even in Software」，在 SW 這一層我沒有被完全說服。

**還剩的反駁（站在「應該一起設計」的立場）**：

1. **兩邊的 kernel SW 跑在同一批 core 上。** 圖自己也寫了「runs on a core like any kernel SW」。「長在不同地方」講的是 HW 輔助的位置，不是 SW 的位置。SW 本身並沒有分開。
2. **兩邊共用 page table。** 返回箭頭寫著壓縮層要改 PTE。TLB miss handler 也讀同一份 page table。PTE 的格式（例如怎麼標記「這頁被壓縮了」）是兩邊都要懂的東西，圖上完全沒畫 page table，也沒說它歸誰。這正是應該一起設計的地方。
3. **壓縮層要清每個 core 的 TLB。** `TLB clears on every core` 表示壓縮層要伸手到每一個 core 的 MMU 狀態裡。這不像「narrow」，反而是對 per-core 資源的廣播動作。誰負責 cross-core 的 TLB 清除、用什麼機制，圖沒有交代。
4. **fault 的起點不清楚。** 如果 fault 是 TLB miss handler 查表後才發現的，那 TLB miss handler 的快速路徑裡就有壓縮層的判斷，兩者的程式碼是串在一起的。
5. **「narrow interface」只是宣稱。** queue 裡放什麼、回來的訊息有幾種，沒有列出來，讀者無法判斷它真的窄。
6. **「per-core path gets tied to a shared one」的代價沒畫。** 綁在一起會怎樣（等 lock？排隊？）沒有視覺化，便條只是斷言。

### 5. 讀 Key point 之後：畫面與結論一致嗎

**部分一致。**

- 一致的：「future hardware help is one shared set beside the LZ4 HW, not something inside each core」和右下的綠色虛線方塊、大字 `ONE SHARED SET`、表格第二列完全對得上。「designed apart」和兩個分開的大框對得上。
- 不一致的：「The two meet only at a narrow interface」。畫面上除了 queue 之外，還有一條繞過 queue、對每個 core 改 PTE 和清 TLB 的返回箭頭，看起來不只一個交會點，也不窄。另外 Key point 說「Even as pure kernel SW ... designed apart」，但畫面上真正分開的是 HW 輔助的位置，SW 分開的理由沒有獨立畫出來。

### 6. 困惑指數

**2 / 5**。主訊息（每個 core 一份 vs 全部共用一份）兩秒就讀得到；扣分在返回箭頭繞過 queue、manager 畫在 processor 外卻說跑在 core 上、page table 沒畫。

### 7. 可疑的錯字或多餘文字

- 沒有看到明顯的錯字。
- `a sub-action, once verified in SW`：句子太省略，像是筆記而不是說明。
- 重複：同一個「per core vs shared」的對比出現四次（兩行大字、大字下的小字、表格、黃色便條）。表格與便條幾乎說同一件事，可以擇一。
- `LZ4 HW` 方塊寫「shared by all cores」，下面大字又寫「used by every core」，重複。
- `COT` 沒有展開，冷讀者不知道是什麼。

## 結論

**用我自己的話說**：CPU 的記憶體管理是每個 core 各自處理自己的 TLB miss，硬體幫手（TLB）長在每個 core 裡；壓縮層是一個集中的管理者，硬體幫手（LZ4 HW 與以後加的輔助）是全部 core 共用的一組。兩者擴充的方向不同，所以即使壓縮層現在全是 kernel SW，也不要和 MMU 的 kernel SW 綁在一起設計，只用一個請求佇列加上「改 PTE、清 TLB」的回報來銜接。

**總表**

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 / 5 |
| 角色是否清楚 | 是（workers 沒畫、COT 沒解釋、沒有圖例，屬小問題） |
| 畫面與結論是否一致 | 部分一致（「only at a narrow interface」與繞過 queue、對每個 core 廣播的返回箭頭有落差） |

**是否建議重生**：不強制重生。困惑指數低於 3，角色大致清楚，箭頭方向沒有和故事矛盾。但畫面與結論只是部分一致，若要說服「應該一起設計」的人，建議下一版考慮：

1. 讓返回的 `PTE updates, TLB clears` 也明顯經過 narrow link（例如 queue 畫成雙向），讓「只在一個窄介面交會」在畫面上成立。
2. 把 page table 畫出來，並標明誰寫、誰讀；這是對方最強的反駁點。
3. 在 manager 旁邊用畫面（不只是小字）表示它跑在同一批 core 上，說清楚這裡分的是職責，不是實體位置。
4. 標出 page fault 是由誰丟出的（MMU HW 還是 TLB miss handler）。
5. 加一個小圖例：紫色虛線是 kernel SW、實線色塊是 HW、綠色虛線是未來的 HW。

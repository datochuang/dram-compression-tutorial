# 冷讀驗收報告：page-states gen1

- 日期：2026-11-11
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：page-states 這一組的 `gen1/00-page-states.png`
- 限制說明：圖檔是一次整張讀入的，無法實體遮住底部。第 1 到 3 題只根據 Key takeaway 以上的畫面作答，第 4 題才把 Key takeaway 納入比對。

## 結論先講

這張圖一看大致就懂：一個 page 在 kernel 眼中有六個狀態，在 MMU 眼中只有 valid 和 invalid 兩種。困惑指數 2。畫面與 Key takeaway 一致。

有三處會讓冷讀者停下來：

1. 下方表格的前兩欄沒有對齊上方的狀態方塊，表格本身也沒有欄標題。
2. 上方兩條弧線在 present 上緣幾乎從同一點出入，中間那個標籤要靠距離判斷屬於哪一條。
3. LZ4 HW 在圖裡出現六次，卻沒有圖像，只存在於文字標籤。

不必為了看懂而重生；若要修，優先修第 1 點。

## 1. 人物與機器

| 角色 | 標籤 | 在做什麼 | 看起來在意什麼 | 清楚嗎 |
|---|---|---|---|---|
| 火柴人（左上） | `kernel` | 手指著一塊寫字板 | 寫字板上的 `page state table`，也就是它自己記的狀態 | 清楚 |
| 寫字板 | `page state table` | 被 kernel 指著 | 無（物件） | 清楚，但板上只有橫線，看不出表裡記什麼欄位 |
| 機器人（左中） | `MMU in the CPU`，對話框寫 `I only see two values` | 兩手各舉一張卡片 | 只分得出兩種值 | 清楚。兩張卡片上沒有字，要靠對話框和右邊的 valid、invalid 膠囊才推得出卡片代表這兩種值 |
| 火柴人加筆電（左下） | `user SW` | 在打字，位置在 `On access` 那一列 | 存取 page 時會發生什麼事 | 清楚 |
| LZ4 HW | 無圖像，只出現在文字裡 | 送回 COMPRESS OK、INCOMPRESSIBLE、DECOMPRESS OK、BAD_STREAM，讀 frame、寫 frame | 不適用 | 角色看得出來，但沒有畫出來。它是四個狀態轉移的發動者，卻是唯一沒有形象的參與者 |
| CPU | 無圖像，只出現在 `CPU waits for the job` 和 `MMU in the CPU` | 等 job 做完 | 不適用 | 勉強。`On access` 那一列左邊畫的是 user SW，格子裡等待的卻寫 CPU，冷讀者要自己把兩者接起來 |

沒有任何人物是無標籤的。

## 2. 看不懂的線或物件

### 我看到的每一個箭頭

橘色的狀態轉移箭頭共八條：

| 編號 | 從 | 到 | 標籤 | 形狀 |
|---|---|---|---|---|
| A1 | untouched | present | `kernel: first touch` | 直線向右 |
| A2 | present | compressing | `kernel: reclaim RW, send COMPRESS` | 直線向右 |
| A3 | compressing | compressed | `LZ4 HW: COMPRESS OK` | 直線向右 |
| A4 | compressed | decompressing | `kernel: page fault, send DECOMPRESS` | 直線向右 |
| A5 | decompressing | lost | `LZ4 HW: BAD_STREAM` | 直線向右 |
| A6 | compressing | present | `LZ4 HW: INCOMPRESSIBLE` | 下方弧線，往左回去 |
| A7 | present | compressed | `kernel: reclaim RO, no job` | 上方內側弧線，往右，跳過 compressing |
| A8 | decompressing | present | `LZ4 HW: DECOMPRESS OK` | 上方外側弧線，往左回去 |

藍色的註記箭頭共兩條：

| 編號 | 從 | 到 | 意思 |
|---|---|---|---|
| B1 | 文字 `RW pages start here` | untouched | RW page 的起點 |
| B2 | 文字 `RO pages start here` | compressed | RO page 的起點 |

另有一條不是箭頭的線：kernel 的手臂伸向寫字板。

### 不確定的地方

- **A7 和 A8 的標籤歸屬**。兩條上方弧線在 present 上緣幾乎從同一點出入，一條的箭頭和另一條的起點疊在一起。`kernel: reclaim RO, no job` 夾在兩條弧線之間，我是靠「比較貼近內側弧線」加上語意（reclaim 應該通往 compressed）才判定它屬於 A7。只看位置的話，也可以讀成外側弧線的標籤。
- **A8 的箭頭方向**。外側弧線很長，箭頭落在 present 上緣，和 A7 的起點擠在一起。我第一眼要沿著線追一次才確定是 decompressing 回到 present，不是反過來。
- **A3 的標籤很擠**。`LZ4 HW: COMPRESS OK` 被塞在 compressing 和 compressed 兩個方塊中間的窄縫，字比別的標籤小，分成兩行。
- **`RO pages start here` 指向 compressed**。看得懂字面，但不知道為什麼 RO page 一開始就是壓縮好的，圖裡沒說壓縮資料從哪來。
- **`no job`**。推測是「不必叫 LZ4 HW 做事，因為壓縮版還在」，但圖上沒有寫原因，`job` 這個詞也沒有在圖裡定義。
- **`chunks`**。斜線小方塊配上這個字，推測是壓縮後的資料塊。圖上沒有圖例說明斜線代表壓縮資料。
- **decompressing 那一格的圖示**。文字寫 `chunks, LZ4 HW writes a frame`，圖示只有斜線方塊，沒有畫正在被寫入的 frame。compressing 那一格則只畫 frame。兩格的畫法不對稱。
- **lost 是紅框**。看得出是壞結局，也沒有往外的箭頭，意思清楚。
- **compressing 和 decompressing 被存取之後**。兩格都寫 `CPU waits for the job`，等完之後接到哪個狀態沒有畫。compressing 等完會落在 compressed，那還要再解壓縮一次嗎？圖沒有回答。
- **標題前的圈號 1**。不知道是圖號、章節號還是步驟號。

## 3. 圖說的一句話

加了 LZ4 之後，一個 page 在 kernel 的 page state table 裡有六個狀態，但 MMU 仍然只看得到 valid 和 invalid，其中只有 present 是 valid，其他五個都靠 page fault 交給 kernel 處理。

## 4. 畫面和結論一不一致

**一致。**

Key takeaway 寫的是：`LZ4 adds states in the kernel, not in the MMU: only present is valid, and the page state table tells the other five apart.`

逐項比對：

- 「states 加在 kernel，不在 MMU」：kernel 拿著 page state table，MMU 說 `I only see two values`，相符。
- 「only present is valid」：`MMU sees` 那一列只有一格是綠色的 valid 加打勾，其餘五格是灰色的 invalid，相符。
- 「the other five」：六個狀態扣掉 present 剩五個，數字相符。

一個小問題：標題下方的藍色副標 `The MMU still sees only valid or invalid; the kernel's page state table tells the invalid ones apart` 和 Key takeaway 幾乎是同一句話，同一個結論在圖上講了兩次。

## 5. 困惑指數

**2（滿分 5）。**

主線一眼就懂，扣分在於表格前兩欄沒有對齊狀態方塊，以及上方兩條弧線要追一下才分得清。

## 6. 可疑的錯字或多餘文字

- 沒有看到拼錯的字。
- `zeroes`（untouched 的 `On access`）和 `zeros`（untouched 的 `Data is in`）兩種拼法同時出現。前者是動詞，後者是名詞，文法上都對，但並排看起來像不一致。
- 副標和 Key takeaway 內容重複，見第 4 題。
- `Without LZ4` 那一條的 `Two states. The PTE says it all.`：PTE 這個詞只在這裡出現一次，下半張圖改說 `MMU sees`，兩邊用詞沒有接起來。
- 標題前的圈號 1 用途不明。

## 7. 表格每一格對應到哪個狀態

表格沒有欄標題，只能靠由左到右的順序和垂直位置對應。我的對應如下：

| 欄 | 對應狀態 | MMU sees | Data is in | On access |
|---|---|---|---|---|
| 1 | untouched | invalid | nowhere, reads as zeros | page fault: kernel zeroes a frame |
| 2 | present | valid（綠色打勾） | a frame（空白方塊） | direct, kernel not involved |
| 3 | compressing | invalid | a frame, LZ4 HW reads it（空白方塊） | page fault: CPU waits for the job |
| 4 | compressed | invalid | chunks（三個斜線方塊） | page fault: kernel sends DECOMPRESS |
| 5 | decompressing | invalid | chunks, LZ4 HW writes a frame（三個斜線方塊） | page fault: CPU waits for the job |
| 6 | lost | invalid | no good copy | page fault: kernel kills this user SW |

六欄對六個狀態，內容上每一格都對得起來，沒有哪一格語意對不上。

### 會看錯欄的地方

以下偏移量是我目視估計的，以圖寬約 1536 像素為準：

- **第 1 欄偏右最多**，中心比 untouched 方塊偏右約 80 像素，落在 untouched 和 present 之間，正好在 `kernel: first touch` 那條箭頭的下方。中間還隔著 `RW pages start here` 這行藍字。冷讀者可能把這一欄讀成「first touch 這個轉移」的說明，而不是 untouched 這個狀態。
- **第 2 欄偏右約 50 像素**，落在 present 方塊的右緣下方。因為綠色 valid 很醒目，而且 `direct, kernel not involved` 語意上只可能是 present，所以還救得回來。
- **第 3、4、5 欄大致對齊**，偏移在 20 像素以內。
- **第 6 欄偏左約 25 像素**，但 lost 是最後一欄，不會看錯。

整體來看，上方狀態方塊的間距不均勻（untouched 到 present 比較寬），下方表格卻是等距排列，所以越往左越對不上。沒有垂直分隔線或欄標題可以補救。

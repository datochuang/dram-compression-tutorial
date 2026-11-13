# cpu-mmu-basics 冷讀驗收報告：gen3 的 C

- 日期：2026-11-13
- 方法：只給圖、不給提示詞的冷讀。讀者沒有看過提示詞、規格或其他文件，只讀了三張 PNG。
- 範圍：完整驗收的是 cpu-mmu-basics 這一組 gen3 的 C（`gen3/03-clear-every-tlb-first.png`）。A（`gen2/01-why-translate.png`）與 B（`gen2/02-page-table-tlb-mmu.png`）只當前後文，沒有逐題記錄。

## 結論摘要

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2（1 一看就懂，5 看不懂） |
| 角色是否清楚 | 清楚。每個人與機器都有標籤，沒有無標籤的角色 |
| 畫面與 Key point | 一致 |
| 是否建議重生 | 不建議整張重生。有 4 處值得局部修，見最後一節 |

## C 的逐題記錄

以下第 1 到 3 題是遮住 Key point 時寫的。

### 1. 人物與機器

| 角色 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 坐在筆電前的火柴人 | `user SW`，在 `Core 0` 的框裡 | 存取 `page 0x416`，橘色箭頭往下進 TLB | 只想讀寫自己的 page，不知道 kernel 在做什麼 |
| 藍色方塊 | `TLB of Core 0`，內容 `page 0x416: frame 0x80024000` | 回答 page 0x416 在哪個 frame，然後存取直接進 DRAM | 沒有意圖，是一份還沒被清掉的舊記錄 |
| 藍色方塊 | `TLB of Core 1`，內容同上 | 沒有人在用它，等著被清 | 同上 |
| 紫色虛線框 | `kernel SW instance`，`running on Core 1` | 唯一主動的角色。往下改 page table，往上清自己 core 的 TLB，往左清 Core 0 的 TLB | 順序：先 1，再 2，最後才 3 |
| 表格 | `page table`，在 `DRAM` 裡，內容 `page 0x416: invalid` | 被 kernel 改寫 | 無 |
| 空白方格 | `frame 0x80024000`，在 `DRAM` 裡 | 被 Core 0 的 user SW 存取，之後會被 kernel 清空再利用 | 無 |
| 外框 | `Core 0`、`Core 1`、`DRAM` | 容器 | 無 |

沒有無標籤的人或機器。角色上有三個讀者會問、圖沒有回答的問題：

- `Core 0` 的框裡沒有 kernel。讀者不確定 Core 0 上有沒有 kernel SW，也不確定 Core 0 的 TLB 是由誰實際動手清的。
- `kernel SW instance` 的 instance 是新詞。B 只寫 `kernel SW`。讀者可以猜到「每個 core 上可以各跑一份」，但圖上只畫了一份。
- user SW 只在 Core 0，但 `TLB of Core 1` 也有 page 0x416 的記錄。圖沒有說這筆是怎麼來的。

### 2. 看不懂的線或物件

每一支箭頭的讀法：

| 箭頭 | 我認為的意思 | 正常或要避免 | 確定程度 |
|---|---|---|---|
| 橘色，user SW 往下到 `TLB of Core 0`，標 `page 0x416` | user SW 存取 page 0x416，先查 TLB | 正常的存取路徑 | 確定 |
| 橘色，`TLB of Core 0` 往下到 `frame 0x80024000`，標 `until step 2 clears it: TLB hit, straight to the frame, no kernel` | TLB 裡還有舊記錄，所以存取直接到 frame，kernel 完全不知道 | 介於兩者之間，見下方第一點 | 不完全確定 |
| 紫色，kernel 往下到 `page table`，標 `1 set the PTE invalid` | 第 1 步，把 page table 裡 page 0x416 那一筆改成 invalid | 正常，該做的事 | 確定 |
| 紫色，kernel 往上到 `TLB of Core 1`，標 `2 clear the entry in its own TLB` | 第 2 步的一半，清自己這個 core 的 TLB 記錄 | 正常，該做的事 | 確定 |
| 紫色，kernel 往左跨過框線到 `TLB of Core 0`，標 `2 clear it on every other core too` | 第 2 步的另一半，把其他 core 的 TLB 記錄也清掉 | 正常，該做的事 | 意思確定，怎麼做到不知道 |

不確定或會讓人停下來的地方：

1. **橘色往 frame 的那支箭頭是好是壞，圖上沒有標。** 它和 A、B 裡正常存取用的橘色一樣，文字也是中性的敘述。我要讀完右上角 `If step 2 skips Core 0` 那個框才知道這條路就是危險的來源。再想一層：在第 1 步與第 2 步之間這條路其實還沒有害，因為 frame 還沒被動；有害的是第 3 步搶在第 2 步之前。這一層圖上沒有直接說，要讀者自己推。右上角的框和這支箭頭之間也沒有連線。
2. **frame 畫成空白方格。** 圖下方寫 `drawn after step 1, before step 2`，這時 frame 裡應該還有 page 0x416 的資料，但方格是空的，看起來像已經清空了。A 的 frame 裡有 `offset 0xC80` 的黑點，這裡沒有。
3. **`drawn after step 1, before step 2` 放在 page table 正下方。** 我一開始以為它只在說 page table。其實整張圖都是這個時間點：兩個 TLB 都還留著記錄。這句話是讀懂全圖的關鍵，但位置和藍色小字讓它像是 page table 的註腳。
4. **有兩個 `2`。** 兩支箭頭都標 2。讀者能猜到是同一步的兩個部分，但會想一下兩者有沒有先後。
5. **第 3 步沒有箭頭。** `3 kernel SW: only after step 2, empty this frame and reuse it` 只是 frame 旁邊的紫色文字，沒有從 kernel 畫過來的線。1 與 2 都有箭頭，3 沒有，視覺上比較弱。考慮到這張圖畫的是第 3 步之前的時間點，不畫箭頭說得通，但圖沒有說明這一點。
6. **跨 core 的那支紫色箭頭怎麼做到。** B 說 TLB 在 CPU 裡面。Core 1 上的軟體怎麼清到 Core 0 裡面的 TLB，圖沒有說。入門讀者很可能在這裡發問。
7. **`empty this frame` 的資料去哪裡。** 圖沒有說。A 寫過 `the kernel can even take the frame away for a while`，所以讀者知道會拿走，但不知道內容怎麼處理。這可能是刻意留給後面的圖。
8. **page table 第二列是空的。** 猜是「還有其他列」的意思。B 的 page table 有 0x415、0x416、0x417 三列，這裡只剩一列加一列空白。
9. **黃色便條 `Changing a PTE: two directions`。** direction 指的是 valid 與 invalid 的變化方向，不是箭頭方向，讀第二行就懂。但 `invalid to valid: other cores need nothing` 沒有給理由，入門讀者要自己想：TLB 裡本來就沒有那一筆，所以沒有舊記錄要清。
10. **步驟編號是沒有圈起來的數字。** `2 clear the entry` 第一眼有可能讀成數量。

### 3. 圖說的一句話（沒看 Key point）

kernel 要收回一個 frame 時，先把 page table 裡那一筆 PTE 改成 invalid，再把每一個 core 的 TLB 裡那一筆清掉，自己的 core 和其他 core 都要清，然後才能清空並重用那個 frame；少清一個 core，那個 core 上的 user SW 會繼續 TLB hit、直接讀寫舊的 frame，而且不會有 exception，kernel 攔不到。

### 4. 畫面與 Key point 是否一致

Key point：`Order: set the PTE invalid, clear the entry from every core's TLB, and only then touch the frame.`

**一致。** 畫面的 1、2、3 與 Key point 的三段一一對應，順序相同。我在第 3 題寫的一句話和 Key point 說的是同一件事。

兩個用字上的小落差，不影響判定：

- Key point 與標題用 `touch the frame`，畫面第 3 步用 `empty this frame and reuse it`。`touch` 比較模糊，而且畫面裡 user SW 也一直在「碰」這個 frame。讀者要自己補上「這裡說的是 kernel 去動它」。
- 標題寫 `Clear Every TLB`，容易讀成把整個 TLB 清空。畫面與 Key point 說的是清掉那一筆 entry。

Key point 只講順序，沒有講原因。原因在右上角的框裡，兩者合起來才完整。

### 5. 困惑指數

**2。** 三個步驟有編號，後果有一個框講明白，主線看一遍就懂；扣分在橘色箭頭沒有標示是危險來源、frame 畫成空的、時間點的說明放在容易被當成註腳的位置。

### 6. 可疑的錯字或多餘文字

- 沒有發現拼錯的字或亂碼。address 的數字 `0x416`、`0x80024000` 在圖內各處一致。
- 標題 `Clear Every TLB` 與內文 `clear the entry` 的範圍不一致，見第 4 題。
- 黃色便條右下角有摺角，B 的黃色便條沒有。Key point 的分隔在 C 是一條短直線，A 與 B 是完整的格線。都是畫風上的小差異。
- 沒有多餘的文字。黃色便條是補充，不在主線上，但內容和主題相關。

## 跨圖觀察

### 接得上的地方

- **例子完全相同。** 三張都用 page `0x416` 與 frame `0x80024000`。B 的 page table 寫 `page 0x416: valid, frame 0x80024000`，C 寫 `page 0x416: invalid`，剛好是同一筆的前後狀態。B 的 TLB 內容 `page 0x416: frame 0x80024000` 在 C 的兩個 TLB 裡原樣出現。
- **命名一致。** `user SW`、`kernel SW`、`TLB`、`page table`、`PTE`、`frame`、`DRAM`、`valid`、`invalid` 的寫法三張都相同。
- **顏色一致。** 橘色是 user SW 的存取，紫色是 kernel SW 的動作，kernel 是紫色虛線框，TLB 是藍色方塊，藍色小字是說明，黃色是補充便條。C 沒有引入新的顏色意義。
- **版面一致。** 左上角的字母方塊、橘色底線的標題、藍色的副標、底部的 Key point。
- **鋪陳有接到。** A 的 `the kernel can even take the frame away for a while` 對到 C 的標題 `Taking a Frame Away`。B 的 `Hardware never reads the page table` 對到 C 副標的 `no TLB finds out by itself`。B 的黃色便條先講了 valid 與 invalid，C 直接用。

### 接不上或有落差的地方

1. **`exception` 與 `TLB hit` 在 C 才第一次出現。** A 與 B 都沒有講 TLB 裡找不到時會發生什麼。C 右上角的 `no exception happens, so the kernel cannot stop it` 要成立，讀者得先知道「TLB 找不到會產生 exception，kernel 才有機會介入」。只看這三張的話，這個前提沒有人教過。這是三張連著看時最大的一個洞。B 只說了 `kernel SW runs on the CPU when it is needed` 與 `fills the entries`，沒有說什麼時候 needed。
2. **`Core` 是 C 才出現的。** B 畫的是一個 `CPU` 的框，裡面一個 TLB。C 直接變成 `Core 0` 與 `Core 1` 各一個 TLB，沒有外層的 CPU 框，也沒有一句話說一個 CPU 有好幾個 core。副標的 `Each core's TLB is a private copy` 補了一部分。
3. **`CPU MMU` 的方塊在 C 不見了。** B 是 user SW 到 `CPU MMU` 再到 `TLB`。C 是 user SW 直接到 TLB，再直接到 frame。B 的 Key point 之一是 CPU MMU 只看 TLB，C 沒有把這個角色帶過來。讀者不會因此看不懂，但 B 剛建立的角色在下一張就消失了。
4. **橘色箭頭的標籤換了。** B 的第一支橘色箭頭標 `logical address`，C 標 `page 0x416`。意思相通，是小落差。
5. **B 的 kernel 只會 `fills the entries`，C 的 kernel 改成 `clear`。** 這個轉換本身很自然，但 B 沒有預告 TLB 的記錄可以被清掉。

### 故事線

A 講為什麼要轉換，B 講轉換的資料放在哪裡、誰在讀，C 講改這份資料時要守的順序。主線是順的，例子一路沿用，讀者不需要重新認物件。

從 B 到 C 一次多了三件事：多個 core、清掉 TLB 記錄、沒有 exception 就攔不到。前兩件 C 自己交代得過去，第三件缺一個前提。如果這一組之後還會有一張講 TLB 找不到時的流程，放在 C 之前會讓 C 右上角的框更站得住。

## 是否建議重生

**不建議整張重生。** 主線清楚，畫面和 Key point 一致，例子、命名與顏色都接得上前兩張。

如果可以局部修改，依影響大小排序：

1. 讓橘色往 frame 的箭頭看得出是危險的來源，例如加上警示的標記，或把右上角的框用線連到這支箭頭。
2. frame 的方格裡畫出還有資料的樣子，避免在「第 1 步之後、第 2 步之前」的時間點看起來已經是空的。
3. 把 `drawn after step 1, before step 2` 移到一看就知道是指整張圖的位置。
4. 標題的 `Clear Every TLB` 改成和內文一致的說法，講清楚是清掉那一筆 entry。

跨圖的那個洞，也就是 `exception` 沒有先教，不是改 C 能解決的，要在前面的圖或另一張圖補。

# 冷讀驗收報告：gen4 第 4 張

- 日期：2026-11-13
- 方法：只給圖、不給提示詞的冷讀
- 讀的是 gen4 的第 4 張：`figures/system-overview/gen4/04-one-lz4-hw-for-every-core.png`
- 讀者拿到的背景：multi-core SoC；DRAM 裡一部分 page 由 LZ4 HW 壓縮；kernel SW 只有一份程式碼，每個進 kernel 的 hardware thread 是一個 instance
- 方法上的限制：圖是一次整張讀進來的，沒辦法真的把底部 Key point 遮住。第 1 到第 3 題只根據 Key point 以上的畫面作答，第 4 題才拿 Key point 來對。另外，圖的副標題本身就寫了大半個結論，所以「只看畫面」的一句話有一部分是副標題給的，不完全是圖形給的。

圖的標題是「One LZ4 HW With N Engines Serves Every Core」，副標題是「Jobs enter through one ring and a free engine takes the next one. Page data never passes through L1 or L2.」

## 1. 人物與機器

圖裡沒有人物，全部是方塊。

| 物件 | 標籤 | 在做什麼 | 看起來在意什麼 | 角色清不清楚 |
|---|---|---|---|---|
| 左上紫色虛線框 | `kernel SW instance`、`Core 0, thread T0` | 往 job ring 寫東西，箭頭上寫「write a descriptor with a tag」 | 把 job 交出去，並且帶一個 tag | 清楚 |
| 左中紫色虛線框 | `kernel SW instance`、`Core 1, thread T0` | 也往 job ring 寫（這條箭頭沒有標籤）；另外收到 completion ring 來的 interrupt | 交 job，以及用 tag 認出做完的是哪一個 | 清楚，但它為什麼是收 interrupt 的那一個不清楚，見第 2 節 |
| 中上圓角框 | `job ring`，格子裡是 A、B、C 加五個空格 | 排隊放 job | 順序 | 清楚 |
| 紅色鎖頭 | `ring_lock` | 掛在 job ring 的框上 | 兩個 instance 不要同時寫 job ring | 清楚。誰拿、拿多久沒畫，但兩條紫色箭頭匯到同一個框，看得出用途 |
| 右上綠色大框 | `LZ4 HW`、`up to N jobs at once`，裡面有 `engine 0`、`engine 1`、`...`、`engine N-1`，底下寫 `engines share no data` | 從 job ring 取 job，和 DRAM 之間搬資料，把結果寫到 completion ring | 有空的 engine 就取下一個；engine 之間互不相干 | 清楚 |
| 齒輪圖示 | 無標籤 | 在 LZ4 HW 框的右上角 | 看起來只是「這是硬體」的裝飾 | 不影響理解 |
| 中間一排格子 | `completion ring`，格子裡是 B、A 加六個空格 | 放做完的結果 | 做完的順序，B 排在 A 前面 | 清楚。它沒有外框也沒有鎖，和 job ring 的畫法不同 |
| 下方長條 | `DRAM`，分成 `chunk pool: compressed streams`（斜線）與 `frame region: 4096 B pages`（四個小方格） | 放壓縮過的資料與沒壓縮的 page | 兩種資料分開放 | 清楚。四個小方格沒有標籤，猜是 page |
| 左下藍色框 | `L1 and L2 caches` | 沒有任何箭頭接到它 | 圖要說資料不經過它 | 角色靠底下的藍字才懂，見第 2 節 |

藍色小字有三處：`N is a hardware parameter, not decided yet`、`which core takes the interrupt: not decided`、cache 框下面的三行說明。讀起來藍色是「註記與還沒決定的事」。

## 2. 看不懂的線或物件

1. **interrupt 的箭頭只指到 Core 1。** 箭頭畫得很肯定，底下的藍字卻說「which core takes the interrupt: not decided」。沒有背景的讀者會先相信箭頭，以為 interrupt 固定送 Core 1，或以為 Core 1 是送出 job 的那一個。圖上也沒有畫 A、B、C 各是哪一個 instance 送的，所以「Core 0 送的 job 做完了，Core 0 怎麼知道」這個問題圖沒有回答。
2. **interrupt 箭頭是從 completion ring 出發，不是從 LZ4 HW 出發。** 我的讀法是「HW 發 interrupt，kernel SW 再去讀 completion ring」，但圖把兩件事合成一條線，誰發 interrupt 要用猜的。
3. **`L1 and L2 caches` 是一個孤立的框。** 「資料繞過 cache」是用「沒有線」加上文字來表達的。圖沒有畫 cache 在 core 與 DRAM 之間的位置，所以看不出「繞過」是繞過哪一條路。知道 cache 的工程師可以從 `cache_clean before COMPRESS`、`cache_invalidate after DECOMPRESS` 推回原因，但圖本身沒有說為什麼要做這兩件事。另外背景說每個 core 有自己的 L1、L2 共用，這裡合成一個框，看不出這個差別，不過這張圖的重點不在那裡。
4. **`stream` 與 `page` 兩條雙向箭頭。** 雙向合理，因為 COMPRESS 與 DECOMPRESS 方向相反，但圖沒有寫哪個方向是哪一種 job。兩條線都從 LZ4 HW 的外框出發，不是從個別 engine 出發，所以看不出 N 個 engine 怎麼接到 DRAM。
5. **job ring 裡還有 A、B、C，completion ring 裡已經有 B、A。** 我的讀法是同一批 job 的前後兩個時間點，C 還在做。但也可以讀成同一瞬間，那 A 與 B 為什麼還留在 job ring 裡就會困惑。圖上沒有 head、tail 或「已取走」的記號。
6. **A、B、C 是什麼沒有明講。** 從「descriptor with a tag」與「matches by tag」推得出字母就是 tag，但沒有一處直接標出來。
7. **`engines share no data` 的範圍。** 我讀成 engine 彼此之間沒有共用的狀態。可是它們顯然都讀寫同一塊 DRAM，初看會頓一下。
8. **DRAM 長條最左邊寫著 `DRAM` 的那一格。** 不確定它只是標籤格，還是 DRAM 裡另一塊沒分類的區域。
9. **標題說「Every Core」，圖上只有 Core 0 與 Core 1，兩個都是 thread T0。** 沒有省略號表示還有更多 core 或更多 thread。

## 3. 圖說的一句話（不看 Key point）

好幾個 core 上的 kernel SW instance 在 `ring_lock` 之下把帶 tag 的 job 寫進同一個 job ring，一個有 N 個 engine 的 LZ4 HW 有空就取下一個，直接在 DRAM 的 chunk pool 與 frame region 之間搬資料而不經過 L1、L2，做完的照完成順序寫回 completion ring，kernel SW 用 tag 對回去。

## 4. 畫面和結論一不一致

Key point 的原文：「ring_lock covers only queuing a job. Up to N jobs run at once and may finish in any order. Their data moves straight between the LZ4 HW and DRAM.」

判定：**一致。**

| Key point 的說法 | 畫面上的對應 | 對得上嗎 |
|---|---|---|
| ring_lock covers only queuing a job | 鎖頭只掛在 job ring 上，completion ring 與 LZ4 HW 都沒有鎖 | 對得上。「only」這個字畫面是用「別處沒有鎖」間接表達的，沒有正面畫出來 |
| Up to N jobs run at once | LZ4 HW 框裡的 `up to N jobs at once` 與 engine 0 到 engine N-1 | 對得上 |
| may finish in any order | job ring 是 A、B、C，completion ring 是 B、A；箭頭寫「completions, in finish order」 | 對得上，而且是整張圖最好懂的一處 |
| data moves straight between the LZ4 HW and DRAM | `stream`、`page` 兩條箭頭直接接 DRAM；cache 框放在旁邊沒有接線 | 對得上 |

Key point 沒有提到 tag 與 cache 維護那兩件事，但那是畫面比結論多，不是矛盾。

## 5. 困惑指數

**2**（1 一看就懂，5 看不懂）。

理由：主線由左到右、再由右回左，一眼就跟得上，亂序完成用 B、A 兩格就講清楚了；扣分在 interrupt 箭頭指定了 Core 1 卻又說還沒決定，以及 cache 那一塊要靠讀字才懂。

## 6. 可疑的錯字或多餘文字

- 沒有看到拼錯或變形的字。`ring_lock`、`cache_clean`、`cache_invalidate`、`COMPRESS`、`DECOMPRESS`、`engine N-1`、`4096 B` 都完整。
- 副標題與 Key point 的內容重疊很多：兩邊都講「一個 ring、空的 engine 取下一個」與「資料不經過 cache」。不算錯，但 Key point 多出來的資訊其實只有「ring_lock 只管排隊」與「完成順序不定」兩件。
- 齒輪圖示沒有意義，也不礙事。
- `not decided` 出現兩次（N、interrupt 送到哪個 core），用語一致，沒有問題。

## 7. 用自己的話講這張圖的結論

整顆 SoC 只有一個 LZ4 HW，所有 core 的 kernel SW 都把工作丟進同一個排隊的 ring。丟的時候要搶一把鎖，但那把鎖只管「排進去」這一下。排進去之後 HW 裡有 N 個 engine 可以同時做，誰先做完誰先回報，所以回報的順序會和排隊的順序不一樣，kernel SW 得靠 tag 認領。page 的資料是 HW 直接對 DRAM 讀寫，不走 CPU 的 cache，所以 kernel SW 要在壓縮前把 cache 裡的內容清到 DRAM，解壓縮後把 cache 裡的舊內容作廢。

## 8. 要不要重生

**不需要重生。** 困惑指數是 2，角色都有標籤而且看得出在做什麼，畫面與 Key point 一致，三個重生條件都不成立。

如果之後有機會小修，依影響大小排：

1. interrupt 的箭頭不要只指 Core 1。改成指向兩個 instance 之間，或用虛線，讓「還沒決定」是畫出來的而不是只寫在旁邊。
2. 給 `L1 and L2 caches` 一個位置：例如畫在 kernel SW instance 與 DRAM 之間，再讓 LZ4 HW 的兩條箭頭明顯從它旁邊過去。
3. 在 A、B、C 旁邊標一次「tag」，並且表示 C 還在 engine 裡做。

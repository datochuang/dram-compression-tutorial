# kernel-sw-design gen1 冷讀報告（第 1 到 4 張）

- 日期：2026-11-15
- 方法：只給圖、不給提示詞的冷讀
- 範圍：kernel-sw-design 的第 1 到 4 張
  - `gen1/01-why-compress.png`
  - `gen1/02-pages-and-frames.r2.png`
  - `gen1/03-page-swap.r2.png`
  - `gen1/04-how-a-page-is-stored.png`
- 讀者設定：沒碰過 CPU MMU、page swap、壓縮的工程師。每張先遮住 Key point 再讀畫面。

---

## 圖 1：Why Compress DRAM

### 1. 人物與機器

| 標籤 | 樣子 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| UI | 戴棒球帽的人，筆電 | 坐著用筆電 | 自己的 memory（上方註「four programs, each wants its own memory」） |
| MEDIA | 戴耳機的人，筆電 | 同上 | 同上 |
| NET | 頭上有天線的人，筆電 | 同上 | 同上 |
| LOG | 拿筆的人，筆電 | 同上 | 同上 |
| DRAM（左、右兩個框） | 方框，裡面是一格格的 page | 左邊塞滿 8 個 page，標 FULL；右邊分成 frames 與 compressed space | 容量 |

沒有畫出「誰在壓縮」。沒有 kernel、沒有 LZ4 HW。四個人和下方 DRAM 之間沒有任何線，看不出哪個 page 屬於誰。

### 2. 看不懂的線或物件

- 「FULL」畫成像按鈕的圓角框，第一眼會以為是可以按的東西，其實是狀態。
- 右邊 DRAM 中間的虛線：猜得出是把 DRAM 分成兩區，但分界是固定的還是會移動，看不出來。
- 中間「Hot and cold」有 5 個 cold page，右邊卻只畫 3 個壓縮過的方塊。另外 2 個 cold page 去哪了？讀者會懷疑是不是數錯了。
- 壓縮過的方塊有斜線，但畫面上沒寫「斜線 = 壓縮」。看大小標示（1.3 KB、2.9 KB、2.1 KB）才猜得出來。
- 「each page is 4 KB before compression」浮在中間空白處，不屬於任何一格，像是補上去的。
- 四個人和三個 panel 的關係沒有畫出來。

### 3. 新手卡住的地方

- **page** 與 **frame**：「every page takes a whole frame」第一次出現 frame，沒有解釋 page 和 frame 有什麼不同（下一張才講）。
- **touched**：「a cold page touched again」，touch 是讀、寫，還是執行？
- **HRT threads**：hard real-time 有寫全名，但為什麼它們「must never wait」、為什麼壓縮會讓人等，這張沒說。
- **the kernel's own code and tables**：kernel 是誰、有哪些 tables，在這裡第一次出現。
- **decompressed back into a frame**：誰來解壓縮？要多久？

### 4. 圖說的一句話

DRAM 容量固定，大部分 page 一段時間沒人用，把這些冷的 page 壓縮起來就能空出位置給更多 page，但有些記憶體永遠不壓縮。

### 5. Key point 對照

Key point：「Compression trades a short wait on the rare touch of a cold page for more room in a fixed DRAM. Hot pages stay as they are.」

**部分一致。** 「more room」與「Hot pages stay as they are」畫面都有。但「short wait」是這句的一半重點，畫面上完全沒有「等」：沒有時鐘、沒有人在等的表情、沒有時間軸。唯一的線索是右下「HRT threads: they must never wait」，要讀者自己倒推出「碰到 cold page 會等」。

### 6. 困惑指數：2

三個 panel 的對比很直觀，左滿右有空位一看就懂；扣分在 cold page 數量對不上，以及「等」沒有畫出來。

### 7. 可疑的錯字或多餘文字

- 沒有錯字。
- 標題下的藍色副標與 Key point 內容重複度高。
- 「each page is 4 KB before compression」位置孤立，像多餘的浮動文字；可以併到 Hot and cold panel。

---

## 圖 2：Pages, Frames and the CPU MMU

### 1. 人物與機器

| 標籤 | 樣子 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| MEDIA | 戴耳機的人，筆電（與圖 1 同一人） | 對自己的 page A、B、C 做 load 與 store | 拿到自己的資料 |
| page A / B / C | 三張紙 | MEDIA 看到的、排在一起的 pages | — |
| Core 0 | 大框 | 裝著 CPU MMU 與 TLB miss handler | — |
| CPU MMU and TLB | 淺藍色實線框 | 接 MEDIA 的每一次 load 與 store；TLB 是「a small cache of recent PTEs」 | 找到 page 在哪個 frame |
| TLB miss handler | 紫色虛線框，註「kernel SW, runs on this core」 | TLB miss 時被叫起來，讀 PTE、填 TLB | 把翻譯補上 |
| DRAM | 大框 | 裝 page table 與 6 個 frame | — |
| page table | 表格 page / PTE | A → frame 5，B → frame 2，C → not valid | — |

kernel SW 是一個虛線框，不是人，也沒有名字。

### 2. 看不懂的線或物件

- **橘色箭頭的起點**：「every load and store」從 MEDIA 的筆電出發，剛好經過 page B 的左邊再往右上。讀者會以為 MEDIA 現在存取的是 page B。
- **「TLB hit: straight to the frame」的橘色箭頭落在 frame 5**。如果上一點的讀法成立（存取 page B），page table 說 B 在 frame 2，箭頭應該到 frame 2 才對。畫面像是畫錯了。就算不是 page B，箭頭沒有標是哪一個 page，讀者對不起來。
- 同一條橘色線從 MMU 出來後穿過 page table 的區域才往下到 frame。這和「TLB hit 不用讀 page table」的意思相反，看起來像 hit 也要經過 page table。
- 紫色「reads the PTE」箭頭指向 page table 的左下角，不是指向某一列。可以接受，但如果指到 C 那一列，就能和下方 page fault 的說明接起來。
- page C「in no frame」：那它在哪裡？畫面沒有交代，只寫「the kernel must bring it into a frame first」。從哪裡帶進來，要到圖 3 才知道。
- page fault 的路徑沒有畫成箭頭，只寫在右下的文字框裡。

### 3. 新手卡住的地方

- **PTE**：從頭到尾沒有展開成 page table entry。
- **load and store**：硬體工程師懂，軟體以外的讀者不一定懂。
- **cache**：「TLB: a small cache of recent PTEs」，cache 沒有解釋。
- **hardware page table walk**：「On this chip: no hardware page table walk」。沒說 walk 是什麼，也沒說別的晶片有 walk 會怎樣，所以讀者不知道這句為什麼重要。
- **core**：「every core has its own TLB」，但只畫一個 core，core 是什麼沒說。
- **kernel SW**：第一次以「會跑的程式」身分出現，和 MEDIA 這種 program 有什麼不同沒說。
- **instruction runs again**：重跑是誰觸發的？

### 4. 圖說的一句話

MEDIA 的每一次存取都經過 CPU MMU 的 TLB；TLB 查不到時由 kernel SW 去 DRAM 讀 page table 再填回 TLB；如果 page table 說這個 page 不在任何 frame，就是 page fault，kernel 要先把它搬進 frame。

### 5. Key point 對照

Key point：「Programs see pages; DRAM holds frames. The page table says which frame holds each page, the TLB caches it, and a page in no frame causes a page fault that the kernel must handle.」

**部分一致。** 結論的每一個名詞畫面上都有。不一致的地方：
- page fault 是結論的最後一個重點，畫面只用文字框交代，沒有畫出路徑。
- 「the TLB caches it」與 TLB hit 箭頭的落點（frame 5 對 page B 的疑慮）互相打架。

### 6. 困惑指數：3

一張圖一次丟出 MMU、TLB、PTE、page table、kernel SW、page fault、page table walk 七個新詞，再加上 TLB hit 箭頭的落點和 page table 對不上。

### 7. 可疑的錯字或多餘文字

- 沒有錯字。
- 「every core has its own TLB」在只畫一個 core 的圖裡沒有作用，像多餘的。
- 「On this chip」框的兩行沒有和畫面上的任何東西連起來（只是重述「TLB miss → kernel SW」）。

---

## 圖 3：Page Swap, and the Case We Build

### 1. 人物與機器

| 標籤 | 樣子 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| NET（左） | 有天線的人（與圖 1 同一人） | 「touches a page that was paged out」 | 要被換出去的 page 回來 |
| NET（右） | 同一人 | 「touches a compressed page」 | 同上 |
| DRAM: frames（左） | 4 個空框 | — | — |
| disk | 圓柱 | 存放被 page out 的 page | — |
| DRAM（右） | frames: hot pages ＋ 虛線 ＋ compressed space: cold pages | — | — |
| LZ4 HW | 綠色框、齒輪 | 「compresses and decompresses on request」 | 照請求做事 |

**kernel 沒有畫出來。** 「What stays the same」與「What is new」都說 kernel 選 page、kernel 決定一切，畫面上卻沒有 kernel，也看不出 LZ4 HW 的「request」是誰送的。

### 2. 看不懂的線或物件

- **右邊兩條綠色箭頭都從 LZ4 HW 往上指進 DRAM**。「page out: COMPRESS」應該是「frame 裡的資料 → 壓縮 → compressed space」，畫面只畫了 LZ4 HW 寫進 compressed space，沒有畫它從 frame 讀。「page back in: DECOMPRESS」同樣只畫寫進 frame，沒有從 compressed space 讀。看起來像 LZ4 HW 憑空產生兩邊的資料。
- 右邊 NET 的橘色箭頭寫「touches a compressed page」，卻落在 frames 那一側，不是 compressed space。讀者不確定 NET 是碰到 frame 還是碰到壓縮區。（如果意思是「NET 以為 page 在 frame 裡」，畫面沒有說清楚。）
- 左邊紫色箭頭（page out / page back in）是誰在做？圖 2 的紫色是 kernel，這裡沒標。
- 右邊 compressed space 的 4 個斜線方塊大小一樣，和下方「at a size nobody knows in advance」以及圖 1 大小不一的方塊不一致。
- 左右兩邊的 frames 全是空框，沒有任何 page，看不出 hot page 在哪。

### 3. 新手卡住的地方

- **page swap / paged out / page out / page back in**：副標有一句解釋，但「paged out」在 NET 的對話裡先出現。
- **disk**：讀者以為主角是 SoC，SoC 有 disk 嗎？只是舉例還是這顆晶片有？
- **LZ4**：第一次出現，沒說它是一種壓縮演算法。
- **COMPRESS / DECOMPRESS 全大寫**：像是命令名稱，但沒說是命令。
- **on request**：誰的 request？
- **kernel**：這是第三張圖，kernel 仍然只有名字沒有形象。

### 4. 圖說的一句話

一般的 page swap 把冷的 page 搬到 disk、page fault 時再搬回來；我們做的是同一件事，只是目的地換成 DRAM 裡的壓縮區，搬運由 LZ4 HW 壓縮與解壓縮。

### 5. Key point 對照

Key point：「Compression is page swap with a different destination: compressed space in the same DRAM, filled and emptied by the LZ4 HW on the kernel's request.」

**部分一致。** 左右對照把「換目的地」講得很清楚。但：
- 「on the kernel's request」：畫面沒有 kernel。
- 「filled and emptied」：箭頭只畫了「寫進」兩邊，沒有「從 compressed space 取出」的方向，看不出 emptied。

### 6. 困惑指數：2

左右對照的構圖一看就懂主旨；扣分在 LZ4 HW 箭頭方向與 kernel 缺席。

### 7. 可疑的錯字或多餘文字

- 沒有錯字。
- 「What stays the same」第三行「the PTE of a page that left says not valid」：「left」讀起來像「左邊」，可以改成「a page that was moved out」。

---

## 圖 4：How a Compressed Page Is Stored

### 1. 人物與機器

| 標籤 | 樣子 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| page P / Q / R | 三張紙 | 各自壓縮成 1.3 KB、2.9 KB、3.9 KB | — |
| chunk pool, in DRAM | 16 格，編號 1 到 16 | P 佔 1、2、7；Q 佔 3、4、5、6、9、10；其他是虛線空格 | — |
| COT | 表格 page / chunks / length / check | P: 1,2,7 / 1.3 KB / CRC；Q: 3,4,5,6,9,10 / 2.9 KB / CRC | 每個 page 的 chunk 在哪 |
| chunk bitmap | 表格 chunk / in use | 1 yes，8 no | 哪些 chunk 空著 |
| LZ4 HW | 綠色框、齒輪 | COMPRESS：一個 frame → 給定的 chunks；DECOMPRESS：給定的 chunks → 一個 frame | 照給它的 chunk 做 |

這張沒有人物。kernel 只出現在副標與 LZ4 HW 下方的藍字（「the kernel picks the chunks and writes the COT; the HW never reads the COT」）。

數字我驗算過，彼此一致：1.3 KB 要 3 個 512 B chunk，2.9 KB 要 6 個，3.9 KB 要 8 個（超過 7）。COT 列的 chunk 編號與 pool 上的 P、Q 字樣相符，bitmap 的 1 與 8 也相符。

### 2. 看不懂的線或物件

- **「OPEN」**：page R 下面有一個和圖 1「FULL」一樣樣式的框寫 OPEN。讀者會以為 OPEN 是 page 的狀態（打開？開放？），猜不到它可能是「還沒決定的問題」。旁邊「today it stays in its frame」的「today」也讓人懷疑是不是暫時的做法。
- COMPRESS 的綠色箭頭只從 page P 指向 pool 的左端（chunk 1 附近），沒有分叉到 chunk 7。「chunks need not be next to each other」只靠文字說。
- 「the last chunk of a page is only partly used」：pool 上 P 的 chunk 7、Q 的 chunk 10 畫得和其他 chunk 一樣滿，看不出「部分使用」。
- P 的斜線比 Q 淡，猜是用來區分兩個 page，但沒有圖例。
- 為什麼上限是 7 個 chunk？畫面沒說（讀者要自己算 7 × 512 B = 3.5 KB 才能猜到是「省不夠就不壓」）。
- 三張 page 是在 frame 裡嗎？LZ4 HW 的說明寫「one frame」，但上方的 page 沒有畫在 frame 裡。

### 3. 新手卡住的地方

- **COT**：縮寫從頭到尾沒有展開。
- **CRC**：「check」欄寫 CRC，沒有解釋，也沒說誰算、誰驗。
- **read-only / read-write pages**：「Rules of the pool」第一次提到，前三張都沒有。為什麼 read-only 的 page 要「keep their chunks forever」更是看不懂，「forever」聽起來不合理（程式結束也不還嗎？）。
- **bitmap**：一般工程師懂，但這裡只列 2 列，讀者可能以為只有 2 個 chunk 有記錄。
- **stream**：Key point 說「a short stream of uneven length」，stream 這個詞畫面上沒有。
- **OPEN** 的意思（見上）。

### 4. 圖說的一句話

一個 4 KB 的 page 壓縮後大小不定，kernel 把它切到幾個不一定相鄰的 512 B chunk 裡，用 COT 記每個 page 用了哪些 chunk、用 bitmap 記哪些 chunk 空著；壓不到 7 個 chunk 以內的 page 就不壓。

### 5. Key point 對照

Key point：「Every compressed page is a short stream of uneven length, spread over a few 512 B chunks. The COT says where each page's stream is; the bitmap says which chunks are free.」

**一致。** 結論的每一點畫面都有，而且數字前後一致。只有「stream」這個詞是 Key point 新加的。

### 6. 困惑指數：3

數字與表格做得很仔細，但資訊密度高，COT、CRC、OPEN、read-only/read-write、7 chunk 上限都沒有解釋。

### 7. 可疑的錯字或多餘文字

- 「COT : one entry per page」冒號前多一個空格。
- 「OPEN」與「today it stays in its frame」：意思不明，像是內部工作筆記漏進圖裡。
- 「read-only pages keep their chunks forever」：「forever」可疑，可能想說的是「回到 frame 後仍保留」。

---

## 跨圖觀察

### 反覆出現的物件與人物

- **人物一致**：MEDIA（耳機）在圖 1、2 長得一樣；NET（天線）在圖 1、3 長得一樣。UI 與 LOG 只出現在圖 1，之後沒再出現，不影響理解。
- **kernel 沒有固定形象**：圖 1 只有文字；圖 2 是紫色虛線框「TLB miss handler」；圖 3 完全沒畫；圖 4 只在藍字裡。kernel 是這組圖（主題叫 kernel-sw-design）實際的主角，卻是四張圖裡最看不見的角色。
- **LZ4 HW 一致**：圖 3、4 都是綠色框加齒輪。
- **壓縮資料一致用斜線**（圖 1、3、4），但沒有圖例說「斜線 = 壓縮」。
- **壓縮資料的大小不一致**：圖 1 的壓縮方塊寬度不同（1.3、2.9、2.1 KB）；圖 3 四個一樣大；圖 4 改成一格格固定 512 B 的 chunk。圖 1 讓人以為一個壓縮 page 是一整塊連續的空間，圖 4 才說是分散的 chunk，兩張之間沒有交代「圖 1 是簡化」。好處是圖 1 的 1.3 KB 與 2.9 KB 和圖 4 的 P、Q 對得上。
- **DRAM 的分區**：圖 1、3 都是 frames ｜虛線｜ compressed space，一致。圖 4 的 chunk pool 應該就是 compressed space，但名稱換了，沒有說兩者是同一個東西。圖 2 的 DRAM 放 page table 與 frames，沒有 compressed space。
- **顏色意思**：
  - 橘色：程式的存取（圖 2、3），同時也是標題底線。大致一致。
  - 紫色：圖 2 是 kernel（TLB miss、handler）；圖 3 是 disk 的 page out / page back in，沒有標是 kernel 做的。讀者可以猜成「紫色 = kernel 的動作」，但沒有確認。
  - 綠色：LZ4 HW 與 COMPRESS / DECOMPRESS（圖 3、4），一致。
  - 藍色：副標與註解文字；但圖 2 的 CPU MMU 框也是淺藍底，藍色同時代表「註解」與「硬體」。
  - 黃色便利貼：補充說明（圖 1 Never compressed、圖 3 兩張、圖 4 Rules），一致。
- **按鈕樣式的狀態字**：圖 1 的「FULL」與圖 4 的「OPEN」用同一種框，但一個是狀態、一個意思不明。

### 故事線

順序是「為什麼要壓縮 → CPU 怎麼找到 page → 壓縮其實是 page swap → 壓縮後怎麼存」，大方向順。斷掉的地方：

1. **圖 1 → 圖 2 的密度跳太大**。圖 1 只有 page、frame、hot/cold；圖 2 一次加上 MMU、TLB、PTE、page table、kernel SW、page fault、page table walk。
2. **圖 2 的「no hardware page table walk」沒有接到任何後果**。讀者知道這是重點（特別框起來），但看完四張都不知道它和壓縮有什麼關係。
3. **frame 在圖 1 先用了才在圖 2 定義**。
4. **圖 2 的 page C「in no frame」懸著**，要到圖 3 才知道它可能在 disk 或壓縮區。圖 2 沒有預告。
5. **kernel 一直沒有現身**。圖 3、4 的文字都說 kernel 決定一切，但畫面裡只有 LZ4 HW 在動。新手讀完會以為 LZ4 HW 才是主角。
6. **圖 4 突然出現 read-only / read-write、CRC、OPEN**，前面都沒有鋪陳。
7. 圖 1 的 Key point 講的「short wait」到第 4 張都還沒畫出來。

### 用自己的話說這 4 張的結論

DRAM 大小固定，但程式大部分的 page 一段時間沒有被用到。CPU 每次存取都要透過 MMU 把程式看到的 page 對到 DRAM 裡實際的 frame，這張對照表叫 page table，最近用過的對照放在 TLB；這顆晶片查不到 TLB 時要由 kernel 軟體自己去查表。如果表上說某個 page 不在任何 frame，就發生 page fault，kernel 要先把它搬回 frame。我們的做法就是傳統的 page swap，只是把冷的 page 搬到 DRAM 裡的壓縮區而不是 disk，搬的時候由 LZ4 HW 壓縮與解壓縮，kernel 決定搬哪一個。壓縮後的 page 大小不定，所以切成幾個 512 B 的 chunk 存，chunk 不必相鄰；kernel 用 COT 記每個 page 用了哪些 chunk，用 bitmap 記哪些 chunk 空著；壓不到 7 個 chunk 的 page 就不壓。代價是程式碰到冷的 page 時要等它解壓縮回來，所以 hard real-time 的記憶體與 kernel 自己不壓縮。

### 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 | 主要問題 |
|---|---|---|---|---|
| 1 Why Compress DRAM | 2 | 是 | 部分一致 | 「short wait」沒畫；5 個 cold page 只壓出 3 塊 |
| 2 Pages, Frames and the CPU MMU | 3 | 是 | 部分一致 | 新詞太多；TLB hit 箭頭落在 frame 5，起點卻像 page B（表上 B 在 frame 2）；page fault 沒畫路徑 |
| 3 Page Swap, and the Case We Build | 2 | 否 | 部分一致 | kernel 沒畫出來；LZ4 HW 兩條箭頭都只指進 DRAM，看不出讀哪裡、寫哪裡 |
| 4 How a Compressed Page Is Stored | 3 | 是 | 一致 | COT、CRC、OPEN、read-only/read-write、7 chunk 上限沒解釋 |

### 建議重生

1. **圖 2**（困惑指數 3）
   - 讓「every load and store」的箭頭明確從某一個 page 出發（例如 page A），TLB hit 的箭頭落到表上對應的 frame（A → frame 5），並且不要穿過 page table。
   - page fault 畫成一條路徑（page C → not valid → kernel），不要只靠文字框。
   - 「no hardware page table walk」加一句它對讀者的意義，或把 PTE 展開成 page table entry。
2. **圖 3**（角色不清）
   - 把 kernel 畫成一個看得見的角色，並畫出它對 LZ4 HW 送 request。
   - LZ4 HW 的箭頭改成兩條完整的路徑：frame → LZ4 HW → compressed space（COMPRESS），compressed space → LZ4 HW → frame（DECOMPRESS）。
   - NET 的箭頭要指向 compressed space 裡的那一個 page，或註明「NET 以為它在 frame」。
   - compressed space 的方塊改成大小不一，和圖 1 一致。
3. **圖 4**（困惑指數 3）
   - 「OPEN」改成讀者看得懂的字（例如「not decided yet」），或拿掉。
   - COT 展開全名；CRC 加一句「用來檢查資料有沒有壞」。
   - read-only / read-write 的兩條規則要嘛加一句原因，要嘛移到後面的圖；「forever」要改寫。
   - 加一句 7 chunk 上限的理由（7 × 512 B = 3.5 KB，再大就省不到空間）。
   - COMPRESS 箭頭分叉到 chunk 1、2、7，畫出「不必相鄰」。

圖 1 不在重生條件內（指數 2、角色清楚、部分一致），但若重生其他張時順便修，建議把「碰到 cold page 要等」畫出來，並讓壓縮方塊的數量和 cold page 對上。

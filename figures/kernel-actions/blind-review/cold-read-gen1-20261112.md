# kernel-actions gen1 冷讀驗收報告

- 日期：2026-11-12
- 方法：只給圖、不給提示詞的冷讀。讀者只拿到 7 張 PNG 和一句背景（SoC 上用 LZ4 硬體壓縮 DRAM 內容，這組圖說明 kernel 軟體在各場景做了哪些動作），沒有讀任何提示詞、文字檔或其他資料夾。
- 讀的是：`figures/kernel-actions/gen1/` 這一組的 7 張（01-scenario-map、02-first-touch、03-fault-decompress、04-fault-hw-fails.r2、05-evict-ro、06-evict-rw、07-evict-incompressible）。
- 方法上的限制：圖是整張讀進來的，底部 Key takeaway 沒辦法真的遮住；每張的第 1 到 4 題只根據標題、橫帶和資料列作答，第 5 題才拿 Key takeaway 對照。另外每張標題下方的藍色副標本身就幾乎是結論，所以「只看畫面的一句話」多少受副標影響。

本報告用到的幾個稱呼：

- 橫帶：圖上由水平線分開的三條區域，由上到下是 `user SW`、kernel、`LZ4 HW`。
- 資料列：Key takeaway 上面那條 `The page's data`，畫 before 和 after。
- 橘圈：橘色實心圓加數字。
- 斜線方塊、空白方塊：資料列裡的小方塊，圖上分別標 `chunks` 和 `a frame`。

---

## 第 1 張：01-scenario-map（Two Triggers, Eight Scenarios）

### 1. 人物與機器

| 誰 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 左欄火柴人 | `user SW` | 坐在 laptop 前，嘴巴張開、頭上有驚訝線 | 被 page fault 嚇到 |
| 右欄火柴人 | `kernel: reclaimer thread` | 微笑站著，一手掃把、一手夾板 | 打掃（回收 frame） |
| 夾板 | `page state table` | 被 reclaimer 拿著 | 無 |
| 綠色方塊兩個 | `LZ4 HW: DECOMPRESS job`、`LZ4 HW: COMPRESS job` | 流程中的一站 | 無 |

角色不清楚的地方：

- 左欄沒有 kernel 的人物，只有文字方塊 `kernel: read the page state`。右欄有 reclaimer 人物，左欄的 kernel 是誰沒有畫。
- 兩個火柴人都沒有箭頭連到下方流程的第一個方塊，只靠擺放位置暗示「這個人引發這條流程」。

### 2. 看不懂的線或物件

- 標題左邊的橘圈 1 和各終點旁的橘圈長得一樣。圖左下的藍字說橘圈是「逐步說明這個場景的那一張」，那標題的橘圈 1 是指這張自己，要想一下才懂。
- `chunks` 沒有定義，卻出現在四個終點方塊裡。
- `clock scan`、`victim page` 沒解釋。
- `frame` 和 `page` 交替出現，冷讀者不知道差別。
- 右欄的 COMPRESS job 只有 `OK` 和 `INCOMPRESSIBLE` 兩個出口，沒有 `HW fails`；左欄的 DECOMPRESS job 有。讀者會問：壓縮時硬體壞了怎麼辦。
- `decoded → page is back` 這個終點沒寫 chunks 是留著還是歸還，上面兩個 ③ 的終點有寫。
- `INCOMPRESSIBLE` 全大寫，`OK`、`HW fails` 不是，看起來像一個是狀態碼、其他是口語。

### 3. 分支路徑與終點號碼

左欄（Trigger: page fault），起點 `kernel: read the page state`：

1. `untouched` → `first touch: a frame of zeros`，終點 ②，旁註 `no LZ4 job`
2. `compressed` → `LZ4 HW: DECOMPRESS job` → `OK, RO page` → `page is back, chunks stay`，終點 ③
3. `compressed` → `LZ4 HW: DECOMPRESS job` → `OK, RW page` → `page is back, chunks given back`，終點 ③
4. `compressed` → `LZ4 HW: DECOMPRESS job` → `HW fails` → `kernel: decode the stream itself` → `decoded` → `page is back`，終點 ④
5. 同上到 `kernel: decode the stream itself` → `stream damaged` → `page is lost, user program ended`（紅框），終點 ④

右欄（Trigger: few free frames），起點 `kernel: clock scan picks a victim page`：

6. `RO page` → `drop the frame, the chunks already hold it`，終點 ⑤，旁註 `no LZ4 job`
7. `RW page` → `LZ4 HW: COMPRESS job` → `OK` → `chunks hold the page, frame freed`，終點 ⑥
8. `RW page` → `LZ4 HW: COMPRESS job` → `INCOMPRESSIBLE` → `page stays in its frame`，終點 ⑦

共 8 個終點，和標題的 Eight Scenarios 對得上。

### 4. 圖說的一句話

kernel 只在兩種時候動手（user SW 發生 page fault、free frame 不夠），之後走到哪個結局要看 page 的狀態、RO 或 RW、以及 LZ4 HW 有沒有成功。

### 5. 與 Key takeaway 是否一致：部分一致

Key takeaway 說「page 的 state 和 RO 或 RW 決定場景」。畫面上還有第三種分岔條件：LZ4 HW 的結果（`OK`、`HW fails`、`INCOMPRESSIBLE`）以及 `decoded` 或 `stream damaged`。8 個場景裡有 4 個是靠硬體結果分出來的，結論沒提。

### 6. 困惑指數：2

樹狀分支清楚，但 `chunks`、`frame`、`clock scan` 沒定義，人物和流程起點之間沒有線。

### 7. 可疑的錯字或多餘文字

沒看到錯字。`no LZ4 job` 出現兩次（②、⑤旁），是有用的；無多餘文字。

---

## 第 2 張：02-first-touch（First Touch of an RW Page）

### 1. 人物與機器

| 誰 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 上帶火柴人 | `user SW` | 微笑，在桌前用 laptop | 正常工作 |
| 中帶火柴人 | `kernel: page fault handler` | 微笑，拿夾板 | 查表辦事 |
| 夾板 | `page state table` | 被 kernel 拿著 | 無 |
| 下帶機箱（齒輪） | `LZ4 HW` | 沒事做，旁邊寫 `no job in this scenario` | 無 |

角色不清楚的地方：`CPU` 和 `CPU MMU` 出現在步驟 1、3 的文字裡，但沒有自己的人物或橫帶，被放在 `user SW` 那一帶。冷讀者會把「CPU 丟出 exception」算成 user SW 做的事。

### 2. 看不懂的線或物件

- 步驟的橘圈 1、2、3 和 sheet 號碼的橘圈是同一個樣子。這張標題是橘圈 2，步驟也有橘圈 2。第 1 張剛說過橘圈代表「哪一張」，翻到這張會愣一下。
- 藍字 `no free frame? wake the reclaimer and wait`：等的時候 `mm_lock` 是拿著還是放掉，圖上看不出來。它掛在持鎖的灰框正下方，容易讀成「拿著鎖等」。
- `keep the page safe from the reclaimer`：沒說怎麼保護、保護多久。
- 標題寫 `RW Page`，第 1 張的 `untouched` 分支沒有限定 RW。RO page 的 first touch 是不是另一回事，圖上沒交代。
- 資料列 after 的空白方塊標 `a frame of zeros`，和後面幾張「有資料的 frame」是同一個圖形，分不出零和有內容。

### 3. 步驟順序

| 步驟 | 橫帶 | 誰做的 | 鎖 | 內容 |
|---|---|---|---|---|
| 1 | user SW | user SW、CPU MMU、CPU | 無標記 | user SW touches the page / PTE is invalid / page fault exception |
| 2 | kernel | page fault handler | `mm_lock held` | page state is untouched / take a free frame / fill the frame with zeros / state = present, make PTE valid / keep the page safe from the reclaimer / few free frames left? wake the reclaimer |
| 3 | user SW | CPU | 無標記 | return from exception / the instruction runs again |

箭頭：1 → 2（向下）、2 → 3（向右上）。LZ4 HW 帶沒有步驟。

資料列：before `nowhere, it reads as zeros` → after 空白方塊 `a frame of zeros`。

### 4. 圖說的一句話

page 第一次被碰時，kernel 在一次持鎖內拿一個 free frame、填零、把 PTE 設成有效，LZ4 HW 完全沒參與。

### 5. 與 Key takeaway 是否一致：一致

結論「kernel work only、一次 mm_lock、一個全零 frame、沒有 LZ4 job」每一項都在畫面上找得到。

### 6. 困惑指數：2

流程本身一看就懂，扣分在步驟橘圈和 sheet 橘圈撞號，以及 CPU 被放在 user SW 帶。

### 7. 可疑的錯字或多餘文字

沒看到錯字。步驟 2 的最後一行 `few free frames left? wake the reclaimer` 和框外藍字 `no free frame? wake the reclaimer and wait` 很像，第一眼會以為重複，其實是「剩很少」和「一個都沒有」兩種情況，建議寫得更有區別。

---

## 第 3 張：03-fault-decompress（Page Fault on a Compressed Page）

### 1. 人物與機器

| 誰 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 上帶火柴人 | `user SW` | 微笑，坐椅子用 laptop | 正常工作 |
| 中帶火柴人 | `kernel: page fault handler` | 微笑，拿夾板 | 查表辦事 |
| 夾板 | `page state table` | 被 kernel 拿著 | 無 |
| 下帶機箱（齒輪、動作線） | `LZ4 HW` | 正在運轉 | 無 |

角色都有標籤。步驟 5 讀 completion 的是誰（page fault handler 本人，還是另一個處理 interrupt 的角色）圖上沒區分，都算在同一個火柴人身上。

### 2. 看不懂的線或物件

- 步驟 3 到步驟 5 有兩條路：一條水平箭頭直接 3 → 5，一條 3 → 4（向下）再 4 → 5（向上）。冷讀者不確定 kernel 是「送出工作後等硬體回來」還是「不等、直接做 5」。
- `COT entry`：COT 沒解釋。
- `check the tag`：什麼 tag、對什麼。
- `job descriptor`、`job ring`、`doorbell`、`completion`：一串硬體介面用語，沒有圖示。
- `cache invalidate the frame`：為什麼解壓後要做這件事，沒說。
- 灰框是持鎖、白框是沒鎖、綠框是硬體、藍框是 user SW 帶，這套顏色沒有圖例，是我對照鎖頭圖示猜出來的。
- 步驟 6 下方藍字 `RO page: its chunks stay` 是 RO 的結局，但資料列的 after 只畫一個 frame，沒畫出 RO 時 chunks 還在。

### 3. 步驟順序

| 步驟 | 橫帶 | 誰做的 | 鎖 | 內容 |
|---|---|---|---|---|
| 1 | user SW | user SW、CPU MMU、CPU | 無標記 | touches the page / PTE is invalid / page fault exception |
| 2 | kernel | page fault handler | `mm_lock held` | page state is compressed / take a free frame / read the COT entry / state = decompressing |
| 3 | kernel | page fault handler | `no lock` | build the job descriptor / write the job ring / ring the doorbell |
| 4 | LZ4 HW | LZ4 HW | 無標記（綠框、齒輪） | DECOMPRESS: chunks into the frame / write the completion / raise the interrupt |
| 5 | kernel | page fault handler | `no lock` | read the completion, check the tag / cache invalidate the frame |
| 6 | kernel | page fault handler | `mm_lock held` | RW page: clear the COT entry, give the chunks back / state = present, make PTE valid / wake other threads waiting for this page / keep the page safe from the reclaimer |
| 7 | user SW | CPU | 無標記 | return from exception / the instruction runs again |

資料列：before 三個斜線方塊 `chunks` → after 一個空白方塊 `a frame`。

### 4. 圖說的一句話

碰到已壓縮的 page 時，kernel 先持鎖登記、放掉鎖把工作交給 LZ4 HW 解壓、硬體做完後再持鎖收尾，讓 user SW 重跑那道指令。

### 5. 與 Key takeaway 是否一致：一致

「一個 DECOMPRESS job 夾在兩次 mm_lock 之間，硬體工作時不持鎖」和步驟 2、3、4、5、6 的鎖頭標記完全對得上。結論說兩次持鎖是 short，畫面沒有任何時間長短的表示，這個字是結論自己加的。

### 6. 困惑指數：2

主線清楚，鎖的節奏一眼看得出來；扣分在 3 → 5 的雙重箭頭和一串沒解釋的縮寫。

### 7. 可疑的錯字或多餘文字

沒看到錯字。3 → 5 的水平箭頭疑似多餘（第 6 張同樣的結構就沒有這條）。

---

## 第 4 張：04-fault-hw-fails.r2（When the LZ4 HW Does Not Deliver the Page）

### 1. 人物與機器

| 誰 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 上帶火柴人 | `user SW` | 愁眉苦臉，想法泡泡寫 `where is my page?` | 等不到 page |
| 中帶火柴人 | `kernel: page fault handler` | 皺眉生氣，雙手抓夾板 | 硬體出包，要自己處理 |
| 夾板 | `page state table` | 被 kernel 拿著 | 無 |
| 下帶機箱（齒輪、冒煙、紅叉） | `LZ4 HW` | 壞了 | 無 |

角色不清楚的地方：

- 機箱側面有一個被紅叉蓋住的東西，看不出是什麼（像一條紙帶或出口）。
- 步驟 5b `end the user program` 放在 kernel 帶、紅框，是 kernel 做的；但沒有箭頭回到 user SW 帶，user SW 的結局只能靠紅叉推測。

### 2. 看不懂的線或物件

- 這張沒有資料列（`The page's data`）。第 2、3、5、6、7 張都有，這張缺了，而這張正好是「資料會不會丟」的一張，最需要 before 和 after。
- 步驟 1 是白框、沒有任何鎖標記，裡面卻寫 `state = decompressing`。第 3 張同一件事在步驟 2，是灰框加 `mm_lock held`。照前一張學到的顏色規則，這裡會被讀成「沒持鎖就改了 state」。
- 步驟 2 的 `or no completion at all`：硬體根本沒回應時，kernel 怎麼知道該接手？箭頭照樣從 2 往上連到 3，沒有畫 timeout 或任何偵測方式。
- 步驟 3 已經寫 `decode with the kernel's own decoder`，步驟 4a 又寫 `CPU writes the page into the frame`。兩句像同一件事，或者 3 是解到別處、4a 才寫進 frame，圖上分不出來。
- `cache invalidate the frame`（步驟 3）和 `cache clean the frame`（步驟 4a）各出現一次，差別和原因都沒說。
- `count a strike against the LZ4 HW` 只出現在 yes 分支的 5a。no 分支算不算 strike 沒寫。
- 藍字 `three strikes in a row, or one missing completion: the kernel stops using the LZ4 HW` 掛在 5b 下方，位置上像是 no 分支的註解，內容卻是在講 5a 的 strike。而且「kernel 不再用 LZ4 HW」之後其他場景怎麼辦，整組圖沒有交代。
- 菱形 `decoded?` 的 no 沒寫原因。第 1 張在同一個位置寫的是 `stream damaged`。
- `BAD_STREAM` 是硬體自己回報 stream 壞了，kernel 還是再解一次；為什麼還要試，圖上沒說（從 `check the CRC` 可以猜是要自己確認）。
- user SW 帶只有終點 6a，沒有起點；起點被收進步驟 1 的 `same start as a normal page fault`。
- 步驟 5a 沒有第 3 張步驟 6 的 `keep the page safe from the reclaimer`，不知道是省略還是真的不做。

### 3. 步驟順序

| 步驟 | 橫帶 | 誰做的 | 鎖 | 內容 |
|---|---|---|---|---|
| 1 | kernel | page fault handler | 無標記（白框） | same start as a normal page fault / state = decompressing / DECOMPRESS job sent |
| 2 | LZ4 HW | LZ4 HW | 無標記（綠框、齒輪） | status BAD_STREAM or BUS_ERROR / or no completion at all |
| 3 | kernel | page fault handler | `no lock` | cache invalidate the frame / read the chunks, check the CRC / decode with the kernel's own decoder |
| 菱形 | kernel | page fault handler | 無 | `decoded?` |
| 4a（yes） | kernel | page fault handler | `no lock` | CPU writes the page into the frame / cache clean the frame |
| 5a | kernel | page fault handler | `mm_lock held` | count a strike against the LZ4 HW / RW page: clear the COT entry, give the chunks back / state = present, make PTE valid / wake other threads waiting for this page |
| 6a | user SW | CPU | 無標記，綠勾 | return from exception / the instruction runs again |
| 4b（no） | kernel | page fault handler | `mm_lock held` | frame back to the free list / state = lost / wake other threads waiting for this page |
| 5b | kernel | page fault handler | 無標記，紅框、紅叉 | end the user program |

### 4. 圖說的一句話

LZ4 HW 解壓失敗或沒回應時，kernel 自己用軟體把 chunks 解開；解得出來 page 就回來，解不出來 page 就丟了、user 程式被結束。

### 5. 與 Key takeaway 是否一致：部分一致

- 「page 只有在 stream 本身壞掉時才會丟」：畫面的 no 分支只寫 `decoded? no`，沒有寫 `stream damaged`，要靠步驟 3 的 `check the CRC` 自己連起來。
- 「硬體失敗賠的是時間，不是資料」：畫面沒有任何東西在表示時間（沒有時間軸、沒有「比較慢」的標記），這半句是結論獨有的。
- 少了資料列，「資料沒丟」這件事在畫面上沒有對應的圖。

### 6. 困惑指數：3

兩條結局分得清楚，但步驟 1 的鎖、硬體沒回應時怎麼發現、3 和 4a 的分工三個地方都要猜，又缺了資料列。

### 7. 可疑的錯字或多餘文字

沒看到錯字。想法泡泡 `where is my page?` 是擬人裝飾，可留。機箱上紅叉底下的物件畫糊了。

---

## 第 5 張：05-evict-ro（Reclaimer Evicts an RO Page）

### 1. 人物與機器

| 誰 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 上帶火柴人 | `user SW` | 微笑用 laptop | 正常工作 |
| 中帶火柴人 | `kernel: reclaimer thread` | 微笑，一手掃把、一手夾板 | 清出 frame |
| 夾板 | `page state table` | 被 reclaimer 拿著 | 無 |
| 下帶機箱（灰底、齒輪） | `LZ4 HW` | 沒事做，旁邊寫 `no job: the chunks already hold this page` | 無 |

角色不清楚的地方：步驟 1 放在 user SW 帶，內容是 `a page fault leaves few free frames` 和 `it wakes the reclaimer`。`it` 指誰不清楚；照橫帶讀會以為是 user SW 叫醒 reclaimer，但第 2 張步驟 2 寫的是 kernel 的 page fault handler 在叫。

### 2. 看不懂的線或物件

- 步驟 3 `a free frame is ready for the next page fault` 放在 user SW 帶，是一個結果，不是 user SW 的動作。
- user SW 帶中間的藍字 `user SW touches this page again? page fault, DECOMPRESS from the same chunks` 沒有箭頭、沒有框，飄在步驟 1 和 3 之間。它其實是指回第 3 張，但沒標號。
- 副標的 `chunk pool` 是新詞，前面幾張只說 chunks。
- RO page 的 chunks 最初是什麼時候壓好的，整組圖沒有一張畫。這張的前提「chunks already hold this page」只能從第 3 張的 `RO page: its chunks stay` 往回推，再往前就斷了。
- 繞著步驟 2 的回頭箭頭（`more frames needed? next victim, same lock hold`）方向看得懂，從右下繞到左下回到框內。

### 3. 步驟順序

| 步驟 | 橫帶 | 誰做的 | 鎖 | 內容 |
|---|---|---|---|---|
| 1 | user SW | 不明（寫 `it`） | 無標記 | a page fault leaves few free frames / it wakes the reclaimer |
| 2 | kernel | reclaimer thread | `mm_lock held` | clock scan: pick a victim page / the victim is an RO page / make PTE invalid / TLB invalidate on all cores / frame back to the free list / state = compressed |
| 2 回圈 | kernel | reclaimer thread | 同一次持鎖 | more frames needed? next victim, same lock hold |
| 3 | user SW | 無（是狀態） | 無標記 | a free frame is ready for the next page fault |

LZ4 HW 帶沒有步驟。

資料列：before 一個空白方塊加三個斜線方塊 `a frame and chunks` → after 三個斜線方塊 `chunks only`。

### 4. 圖說的一句話

回收 RO page 時壓縮好的那份本來就在，kernel 在一次持鎖內把 PTE 設成無效、把 frame 還回去就結束，不需要 LZ4 HW。

### 5. 與 Key takeaway 是否一致：一致

「只是記帳、chunks 已經有、不用 LZ4 job 就能釋放 frame」和步驟 2、LZ4 HW 帶的藍字、資料列三處都對得上。

### 6. 困惑指數：2

核心意思很清楚，資料列在這張最有說服力；扣分在步驟 1、3 掛在 user SW 帶，以及 RO chunks 的來源沒交代。

### 7. 可疑的錯字或多餘文字

沒看到錯字。`Key takeaway` 標籤這張是淡藍底，其他張是白底，像是走樣。

---

## 第 6 張：06-evict-rw（Reclaimer Evicts an RW Page）

### 1. 人物與機器

| 誰 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 上帶火柴人 | `user SW` | 微笑用 laptop | 正常工作 |
| 中帶火柴人 | `kernel: reclaimer thread` | 微笑，掃把加夾板 | 清出 frame |
| 夾板 | `page state table` | 被 reclaimer 拿著 | 無 |
| 下帶機箱（齒輪、動作線） | `LZ4 HW` | 正在運轉 | 無 |

角色不清楚的地方：和第 5 張一樣，步驟 1 的 `it wakes the reclaimer` 放在 user SW 帶，主詞不明。

### 2. 看不懂的線或物件

- `reserve 7 chunks, the worst case`：為什麼是 7、一個 chunk 多大，沒說。資料列 after 只畫 3 個斜線方塊，要讀到步驟 6 的 `give the unused chunks back` 才接得起來。
- 步驟 3 和 5 之間這張沒有水平箭頭，只有 3 → 4 → 5。第 3 張同樣結構卻多一條 3 → 5 的水平箭頭。兩張擺在一起會懷疑其中一張畫錯。
- 第 5 張有「下一個 victim」的回圈，這張沒有。reclaimer 在硬體壓縮時是等著，還是去挑下一個，看不出來。
- user SW 帶的藍字 `user SW touches this page during the job? page fault, then it waits`：等誰、等到哪一步，要自己對到步驟 6 的 `wake other threads waiting for this page`。
- 步驟 3 的 `cache clean the frame` 沒解釋（和第 3 張解壓後的 `cache invalidate` 是一對，但圖上沒講為什麼一個 clean 一個 invalidate）。
- 步驟 5 的框和旁邊一樣大，裡面只有一行，下半是空的。

### 3. 步驟順序

| 步驟 | 橫帶 | 誰做的 | 鎖 | 內容 |
|---|---|---|---|---|
| 1 | user SW | 不明（寫 `it`） | 無標記 | a page fault leaves few free frames / it wakes the reclaimer |
| 2 | kernel | reclaimer thread | `mm_lock held` | clock scan: pick a victim page / the victim is an RW page / reserve 7 chunks, the worst case / make PTE invalid / TLB invalidate on all cores / state = compressing |
| 3 | kernel | reclaimer thread | `no lock` | cache clean the frame / build the job descriptor / write the job ring, ring the doorbell |
| 4 | LZ4 HW | LZ4 HW | 無標記（綠框、齒輪） | COMPRESS: the frame into chunks / write the completion / raise the interrupt |
| 5 | kernel | reclaimer thread | `no lock` | read the completion, check the tag |
| 6 | kernel | reclaimer thread | `mm_lock held` | write the COT entry / give the unused chunks back / frame back to the free list / state = compressed / wake other threads waiting for this page |
| 7 | user SW | 無（是狀態） | 無標記 | a free frame is ready for the next page fault |

資料列：before 一個空白方塊 `a frame` → after 三個斜線方塊 `chunks`。

### 4. 圖說的一句話

回收 RW page 時 frame 是唯一的一份，所以 kernel 先持鎖預留 chunks 並擋住存取，放掉鎖讓 LZ4 HW 壓縮，再持鎖把結果記進 COT、歸還多的 chunks、釋放 frame。

### 5. 與 Key takeaway 是否一致：一致

「chunks 存好、COT entry 記好之後才釋放 frame」對應步驟 6 裡三行的先後順序（write the COT entry 在 frame back to the free list 前面）。這個先後只靠框內的行序表達，沒有特別強調，匆忙的讀者可能看不出「順序」才是重點。

### 6. 困惑指數：2

和第 3 張是鏡像結構，看過第 3 張就讀得很快；扣分在 7 chunks 的由來和步驟 1 的主詞。

### 7. 可疑的錯字或多餘文字

沒看到錯字。Key takeaway 那一列這張外面多一層外框，標籤是框中框，和其他張略不同。

---

## 第 7 張：07-evict-incompressible（An RW Page That Does Not Compress）

### 1. 人物與機器

| 誰 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 上帶火柴人 | `user SW` | 微笑用 laptop | 沒受影響 |
| 中帶火柴人 | `kernel: reclaimer thread` | 皺眉、頭旁一滴藍色汗，掃把加夾板 | 白忙一場 |
| 夾板 | `page state table`（這張多一個小箭頭指著夾板） | 被 reclaimer 拿著 | 無 |
| 下帶機箱（齒輪），頭上一個橘色問號 | `LZ4 HW` | 壓不下去 | 困惑 |

角色都有標籤。機箱上的橘色問號容易被讀成「硬體出問題」，但這張的硬體其實是正常回報結果；和第 4 張真的壞掉（冒煙、紅叉）要分清楚。

### 2. 看不懂的線或物件

- 步驟 2 寫 `the page does not fit in 7 chunks`，第 6 張步驟 2 寫 `reserve 7 chunks, the worst case`。既然 7 是最壞情況，怎麼還會放不下？兩張擺在一起是矛盾的，冷讀者解不開。
- 步驟 1 是白框、沒有鎖標記，裡面寫 `state = compressing`；第 6 張同一件事在灰框、`mm_lock held`。和第 4 張步驟 1 是同一個問題。
- 步驟 2 沒有 `write the completion`，步驟 3 卻在 `read the completion`。第 6 張的步驟 4 有寫這一行。
- 沒有釋放任何 frame，reclaimer 接下來做什麼（挑下一個 victim？）沒畫。
- 步驟 5 放在 user SW 帶，內容 `user SW keeps its page`、`no frame was freed` 是結果，不是動作。
- 步驟 4 的 `mm_lock held` 鎖頭是空心的，第 3、4、6 張是實心黑的。
- 1 → 2 和 2 → 3 的箭頭是斜的，其他張是直上直下，不影響理解。

### 3. 步驟順序

| 步驟 | 橫帶 | 誰做的 | 鎖 | 內容 |
|---|---|---|---|---|
| 1 | kernel | reclaimer thread | 無標記（白框） | same start as an RW eviction / 7 chunks reserved, state = compressing / COMPRESS job sent |
| 2 | LZ4 HW | LZ4 HW | 無標記（綠框、齒輪） | COMPRESS: the page does not fit in 7 chunks / status INCOMPRESSIBLE / raise the interrupt |
| 3 | kernel | reclaimer thread | `no lock` | read the completion, check the tag |
| 4 | kernel | reclaimer thread | `mm_lock held` | give all 7 chunks back / remember: this page is incompressible / state = present, make PTE valid again / wake other threads waiting for this page |
| 5 | user SW | 無（是狀態） | 無標記 | user SW keeps its page / no frame was freed |

步驟 4 下方藍字：`the clock scan skips this page from now on`。

資料列：before 一個空白方塊 `a frame` → after 一個空白方塊 `the same frame`。

### 4. 圖說的一句話

LZ4 HW 回報這個 page 壓不下去時，kernel 把預留的 chunks 全部還回去、把 page 恢復成可用、記下它壓不了，以後不再挑它。

### 5. 與 Key takeaway 是否一致：一致

「白做一個 job、全部復原、之後不再挑這個 page」對應步驟 4 和它下面的藍字，資料列的 `the same frame` 也對得上。

### 6. 困惑指數：2

單看這張很好懂；扣分在步驟 1 的鎖沒標，以及和第 6 張的「7 chunks 是最壞情況」互相打架。

### 7. 可疑的錯字或多餘文字

沒看到錯字。機箱上的橘色問號語意不準，建議換掉或拿掉。

---

## 跨圖觀察

### 命名物件有沒有走樣

| 物件 | 出現在 | 一致性 |
|---|---|---|
| LZ4 HW 機箱 | 2 到 7 | 每張畫法不同：第 2 張立體、投入口在上；第 3、6 張正面、有腳、有動作線；第 5 張灰底；第 7 張白底加問號；第 4 張冒煙加紅叉。靠齒輪和標籤還認得出是同一台，但外形沒有固定。 |
| 持鎖的鎖頭 | 2 到 7 | 第 3、4、6 張是實心黑鎖，第 2、5、7 張是空心鎖。文字都是 `mm_lock held`。 |
| 開著的鎖頭 | 3、4、6、7 | 一致，都是空心開鎖加 `no lock`。 |
| 斜線方塊（chunks） | 3、5、6 | 都是 3 個一排。第 5 張斜線較密、偏灰，第 3、6 張較疏、較黑。數量永遠是 3，和文字裡的 7 chunks 沒有對應。 |
| 空白方塊（frame） | 2、3、5、6、7 | 一致。但「全零的 frame」（第 2 張）和「有資料的 frame」（其他張）是同一個圖形。 |
| 夾板 | 1 到 7 | 一致，每張都標 `page state table`。第 7 張多一個小箭頭。 |
| 掃把 | 1、5、6、7 | 一致：reclaimer thread 一定有掃把，page fault handler（2、3、4）一定沒有。這是分辨兩個 kernel 角色的唯一圖形線索，有效。 |
| user SW 火柴人 | 1 到 7 | 都在 laptop 前。有時有椅子、有時沒有。表情跟著劇情變（第 1 張驚訝、第 4 張發愁），算是有意義的變化。 |
| 資料列 | 2、3、5、6、7 | 第 4 張沒有。 |
| Key takeaway 列 | 1 到 7 | 第 5 張標籤是淡藍底，第 6 張多一層外框，其餘一致。 |

### 分類顏色一致嗎

從第 2 到 7 張歸納出來的規則（圖上沒有圖例）：

- 藍框：user SW 帶的框
- 灰框：kernel 持 `mm_lock` 時做的事
- 白框：kernel 沒持鎖時做的事
- 綠框：LZ4 HW 做的事
- 紅框：壞結局（第 1 張、第 4 張的 5b）
- 橘色：箭頭和編號圓圈
- 藍字：旁註

破例的地方：

1. 第 4 張步驟 1、第 7 張步驟 1 是白框、沒鎖標記，內容卻包含前一張在持鎖下做的事（`state = decompressing`、`state = compressing`）。這兩個「前情提要」框讓灰白規則失效。
2. 第 4 張的 5b 是白底紅框、沒有鎖標記，不知道結束 user 程式時有沒有持鎖。
3. 橘圈一物兩用：第 1 張代表「哪一張」，第 2 到 7 張代表「第幾步」。
4. 第 1 張的 kernel 方塊全部是白的。在第 1 張沒有鎖的概念，可以接受，但翻到後面才知道白色另有意思。

### 第 1 張的號碼對不對得上

| 第 1 張終點 | 號碼 | 對應的那一張 | 對得上嗎 |
|---|---|---|---|
| first touch: a frame of zeros，no LZ4 job | ② | 第 2 張 | 對得上。第 2 張標題多了 `RW Page` 這個限定，第 1 張沒有。 |
| page is back, chunks stay（RO） | ③ | 第 3 張 | 對得上，但 RO 在第 3 張只是步驟 6 下面一行藍字，資料列也沒畫 chunks 留著。 |
| page is back, chunks given back（RW） | ③ | 第 3 張 | 對得上，是第 3 張的主線。 |
| decoded → page is back | ④ | 第 4 張的 4a、5a、6a | 對得上。 |
| stream damaged → page is lost, user program ended | ④ | 第 4 張的 4b、5b | 對得上，但第 4 張的分岔寫 `decoded? no`，沒有用 `stream damaged` 這個詞。 |
| drop the frame, the chunks already hold it，no LZ4 job | ⑤ | 第 5 張 | 對得上。 |
| chunks hold the page, frame freed | ⑥ | 第 6 張 | 對得上。 |
| page stays in its frame | ⑦ | 第 7 張 | 對得上。 |

號碼全部對得上。第 1 張沒有收進去的內容：第 4 張的「三次 strike 或一次沒回應就停用 LZ4 HW」，以及第 2、5、6 張透露的「page fault 會叫醒 reclaimer」。後者表示第 1 張的兩個 trigger 其實有因果關係，但第 1 張把它們畫成兩個互不相干的欄。

### 故事線順不順

順的地方：

- 順序是「地圖 → 最簡單的 fault → 正常解壓 → 解壓出錯 → 回收 RO → 回收 RW → 壓不下去」，由簡到繁，每一張都只比上一張多一件事。
- 第 3 張和第 6 張是鏡像（持鎖、放鎖交給硬體、持鎖收尾），看懂一張就看懂另一張。
- 第 4、7 張用 `same start as …` 接在第 3、6 張後面，省掉重複。

斷掉的地方：

1. page 的一生和張數順序是反的。一個 RW page 要先被回收壓縮（第 6 張）之後才可能發生「碰到已壓縮的 page」（第 3 張），但第 3 張排在前面。第 3 張一開頭的 chunks 從哪來，要到第 6 張才知道。
2. RO page 的 chunks 最初從哪來，七張都沒畫。第 5 張說 `never left the chunk pool`，第 3 張說 `chunks stay`，兩張互相指，源頭不在這組圖裡。
3. 第 4 張沒有資料列，連續翻的時候這裡會掉一拍。
4. 第 6 張說 7 chunks 是最壞情況，第 7 張說 7 chunks 放不下，兩張相鄰而互相矛盾。
5. 第 4 張的「kernel 停用 LZ4 HW」之後，第 3、6 張的流程怎麼走，沒有下文。壓縮時硬體失敗（不是 INCOMPRESSIBLE，是真的壞）也沒有對應的圖。
6. 第 2 張的「沒有 free frame 就叫醒 reclaimer 然後等」和第 5、6 張的步驟 1 是同一件事，但三張之間沒有互相標號。

### 我用自己的話說這組圖的結論

kernel 只在兩種時候出手：user SW 碰到一個不在記憶體裡的 page，或者 free frame 快用完。出手時它的工作幾乎都是記帳：查表、改 page 的狀態、改 PTE、配或還 frame 和 chunks，這些都在短暫持有 `mm_lock` 的時候做。真正搬資料的壓縮和解壓交給 LZ4 HW，而且硬體工作的那段時間 kernel 不持鎖，所以一個 job 總是夾在兩次持鎖之間。RO page 壓好的那份永遠留著，所以回收它不花硬體；RW page 的 frame 是唯一的一份，一定要壓完、記好才能放掉 frame。出狀況時都有退路：硬體解壓失敗，kernel 自己用軟體解；page 壓不下去，就全部復原、以後跳過它。只有儲存的壓縮資料本身壞掉，page 才真的會丟。

### 總表

| 張 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|
| 1 scenario-map | 2 | 是（但人物和流程起點之間沒有線，左欄沒有 kernel 人物） | 部分一致 |
| 2 first-touch | 2 | 是（CPU、MMU 沒有自己的位置） | 一致 |
| 3 fault-decompress | 2 | 是 | 一致 |
| 4 fault-hw-fails.r2 | 3 | 是（但硬體沒回應時誰發現，沒畫） | 部分一致 |
| 5 evict-ro | 2 | 否（步驟 1 的 `it` 掛在 user SW 帶，主詞不明） | 一致 |
| 6 evict-rw | 2 | 否（同第 5 張） | 一致 |
| 7 evict-incompressible | 2 | 是（機箱上的問號語意不準） | 一致 |

### 建議重生

依優先順序：

1. **第 4 張（必須）**。困惑指數 3，畫面與結論部分一致。要補的：
   - 加回資料列（before：chunks；after 兩種：frame，或什麼都沒有）。
   - 步驟 1 的「前情提要」框標清楚鎖的狀態，或改成和第 3 張一樣的灰白兩格。
   - 硬體沒回應時 kernel 怎麼發現（timeout）畫出來。
   - 步驟 3 和 4a 的分工寫清楚，或合併。
   - 菱形的 no 分支寫上 `stream damaged`，和第 1 張用同一個詞。
   - 藍字的 strike 規則移到 5a 旁邊。
   - 結論裡的「costs time」在畫面上要有對應，否則從結論拿掉。
2. **第 5 張、第 6 張（角色不清）**。步驟 1 改成講清楚誰叫醒 reclaimer（例如寫 `kernel page fault handler wakes the reclaimer`，或把這一格移到 kernel 帶）；最後一格是狀態，不要放在 user SW 帶當成一步。第 6 張順便處理：`7 chunks` 的說法要和第 7 張講得通，3 → 5 的箭頭畫法要和第 3 張統一。第 5 張把 Key takeaway 標籤改回白底。
3. **第 1 張（結論文字小修即可，不一定要重生）**。Key takeaway 補上「硬體的結果」也是分岔條件；若重生，加上人物到流程起點的箭頭，並把標題的橘圈和終點的橘圈做出區別。

不在重生清單、但建議順手修的：

- 第 3 張：拿掉 3 → 5 的水平箭頭；資料列補上 RO 時 chunks 還在。
- 第 7 張：步驟 1 補鎖的狀態；機箱上的問號換掉；`does not fit in 7 chunks` 和第 6 張的 `worst case` 對齊說法；步驟 2 補 `write the completion`。
- 整組：鎖頭統一成實心或空心；LZ4 HW 機箱固定一個畫法；步驟編號和 sheet 編號用不同的圖形；加一個小圖例說明灰框是持鎖、白框是沒鎖。

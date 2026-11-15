# 冷讀報告：two-stage-task 第 3 張（gen13）

- 日期：2026-11-15
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：two-stage-task 的第 3 張（gen13），`gen13/03-apart-even-in-software.png`
- 讀者立場：原本認為「壓縮層的 kernel SW 應該和 CPU MMU 的 kernel SW 一起設計」的工程師

## 1. 第一眼

前三秒讀到的字依序是：

1. 標題 "Apart Even in Software"
2. 兩欄的大字 "HW HELP: INSIDE EACH CORE"（藍）與 "HW HELP: BESIDE THE LZ4 HW"（綠）
3. "CPU MMU domain" 與 "compression domain"
4. 底部黃框的 "Why not co-design them"

第一印象：這張圖在主張 CPU MMU 與壓縮兩塊即使都是軟體也要分開設計，理由是兩邊的硬體輔助放在不同地方。

## 2. 最大的字

**藍欄 "HW HELP: INSIDE EACH CORE"**
- 主詞：CPU MMU 這一邊的硬體輔助，也就是小字說的 TLB。
- 性質：位置。它在每個 core 裡面，每個 core 一份。
- 「只有一份」的誤讀：沒有。"EACH CORE" 已經說了每個 core 都有。

**綠欄 "HW HELP: BESIDE THE LZ4 HW"**
- 主詞：壓縮這一邊的硬體輔助。
- 性質：位置。它在 core 外面、在 LZ4 HW 旁邊，所有 core 共用（小字 "outside the cores, used by every core"）。
- 「只有一份」的誤讀：有兩個可能。
  - "THE LZ4 HW" 是單數，讀起來 LZ4 HW 只有一台。下面的方塊寫了 "several engines"，看到的話可以修正成「一台 LZ4 HW，裡面有好幾個 engine」，所以這個讀法應該就是作者的意思，不算錯。
  - 比較要注意的是：大字放在 compression domain 框裡，而這個框畫在 processor 外面。只看大字與框的位置，讀者可能以為「整個壓縮層，包括它的 kernel SW，都在 core 外面、在 LZ4 HW 旁邊，只有一份」。上方 Core 0 與 Core 1 各畫了一個 compression kernel SW，可以把這個讀法擋回來，但大字本身沒有幫忙擋。
- 另一個小歧義：HW help 是指 LZ4 HW 本身，還是指標著 PROPOSAL 的 "future HW assists"？"BESIDE THE LZ4 HW" 字面上指的是 LZ4 HW 旁邊的東西，那就是 future HW assists；可是 LZ4 HW 本身也是硬體輔助。兩種讀法都說得通。
- 全大寫的 "HW HELP:" 第一眼有一點像「求救」或「徵求幫手」，第二眼才讀成「硬體輔助」。

## 3. 人物與機器

| 物件 | 我的理解 | 清楚嗎 |
|---|---|---|
| processor 框 | 整顆 processor，裡面有 Core 0 與 Core 1 | 清楚 |
| CPU MMU and TLB（淺藍實底） | 每個 core 裡的 MMU 硬體與 TLB | 清楚 |
| TLB miss handler（藍色虛線） | CPU MMU 那一方設計的 kernel SW，在 TLB miss 時跑 | 清楚 |
| compression kernel SW（綠色虛線） | 壓縮那一方設計的 kernel SW，由 TLB miss handler 在需要時呼叫 | 清楚 |
| "a call"（紫色箭頭） | TLB miss handler 呼叫 compression kernel SW | 清楚 |
| page table, in DRAM | MMU 的表，有一把 lock 保護 | 清楚 |
| interface, agreed together | 雙方要一起談定的 4 件事 | 清楚 |
| COT, in DRAM | 壓縮那一方的表，有一把 lock 保護 | COT 沒展開，不知道縮寫是什麼，只能從位置猜是壓縮的對照表 |
| chunk pool, in DRAM（四個斜線方塊） | 放壓縮後資料的地方 | 斜線方塊沒有圖例，猜是「壓縮過的資料」 |
| LZ4 HW, several engines（淺綠實底，齒輪圖示） | 壓縮引擎，有好幾個 engine | 清楚；齒輪的意思不確定 |
| future HW assists（PROPOSAL） | 提案中的輔助硬體：CRC、header、chunk list；kernel SW 可以覆寫它們寫的一切 | 清楚 |

看不出來的角色：
- **誰觸發 fault**：畫面上沒有 user SW 或任何程式，不知道是誰在存取、為什麼 fault。
- **thread**：沒畫 hardware thread，看不出一個 core 有幾個執行者。
- **reclaim 或趕 page 的人**：沒畫，看不出壓縮（COMPRESS）是誰、在哪裡發起的。畫面只看得出 fault 時讀 COT 並交 job。
- **LZ4 HW 的結果怎麼回來**：沒有回傳或 completion 的線。

## 4. 看不懂的線或物件

1. **兩條橘色箭頭的起點**："reads PTEs" 從 processor 框的左下（Core 0 下方）往下，"reads the COT, hands LZ4 HW a job" 從右下（Core 1 下方）往下。第一次看很容易讀成「Core 0 負責 MMU、Core 1 負責壓縮」這種 core 分工。框下方的小字 "both run on the core that faulted, on several cores at once" 才把它擋回來。箭頭從 processor 框整體出發、或兩個 core 各有兩條，比較不會誤讀。
2. **誰讀 PTE**：箭頭從 processor 框出發，看不出讀 PTE 的是 CPU MMU 硬體還是 TLB miss handler。
3. **虛線與實線**：圖例只說了顏色（藍是 CPU MMU 這方設計的、綠是壓縮這方設計的），沒說虛線的意思。看起來虛線是軟體、實底是硬體，但兩個 domain 的大框也是虛線，PROPOSAL 框也是虛線，所以虛線可能是「軟體」也可能是「設計範圍」或「還沒定」。
4. **填色**：CPU MMU and TLB 與 LZ4 HW 有填色，其他沒有。猜是硬體，沒有圖例。
5. **interface 框沒有任何線**：只靠框下方 "the call in each core follows it" 連到上面的紫色箭頭。
6. **"a request: which page, which core"**：為什麼 request 要帶 core？是要知道結果回給誰，還是要指定在哪個 core 做？看不出來。
7. **"a TLB clear for every core"**：是指趕 page 時要清掉所有 core 的 TLB，還是每個 core 各有一個清 TLB 的介面？看得懂大意，細節不確定。
8. **"a lock guards it" 與 "a lock guards them"**：是同一把還是兩把？畫成各自的，猜是兩把。如果是兩把，fault path 會不會兩把都拿、順序是什麼，圖沒說。
9. **齒輪圖示**：在 LZ4 HW 右上角，不知道是「正在工作」、「可設定」還是裝飾。
10. **interface 框下方有一個小黑點**，看起來是雜點。

## 5. 執行方式

- **在哪裡跑**：在發生 fault 的那個 core 上。Core 0 與 Core 1 各畫了一份 compression kernel SW，由同一個 core 的 TLB miss handler 呼叫。
- **同一時間有幾份**：最多每個 core 一份，可以好幾份同時在跑（"on several cores at once"）。一個 core 裡能不能同時有兩份，因為沒畫 thread，看不出來。
- **兩個 core 同時 page fault**：兩個 core 各自跑自己的 TLB miss handler，各自呼叫自己的 compression kernel SW。兩份都讀 COT，COT 與 chunk pool 有 lock 保護，所以碰到共用表時要排隊拿 lock。LZ4 HW 有好幾個 engine，兩個 job 可能可以同時做。兩個 core 碰到同一個 page 會怎樣、job 怎麼排隊、結果怎麼回到對的 core，畫面沒有說。

## 6. 圖說的一句話

壓縮的 kernel SW 和 TLB miss handler 一樣在 fault 的那個 core 上跑，但它的表與硬體輔助放在 core 外面的 LZ4 HW 那一邊，而 MMU 的硬體輔助（TLB）在每個 core 裡面，所以兩邊只需要談定一個小介面，其他分開設計。

## 7. Key point 對照

**部分一致。** 大部分一致：在 fault 的 core 上跑、好幾個 core 同時、從 fault path 呼叫、硬體輔助在 LZ4 HW 旁邊不在 core 裡、只有小介面一起談，畫面都有。

不一致或對不上的地方：
1. **"its tables ... sit beside the LZ4 HW"**：畫面上 COT 與 chunk pool 標的是 "in DRAM"，page table 也標 "in DRAM"。兩邊的表在實體上是同一個地方。表「在不同地方」只在圖上的分欄成立，不是實體位置。標題副標也說 "their tables ... live in different places"，對一個硬體背景的讀者這句話站不住，會被抓。
2. **"called from the CPU MMU's fault path"**：畫面上呼叫者是 "TLB miss handler"。Key point 說 fault path，畫面說 TLB miss handler，讀者會停下來想：fault 等於 TLB miss 嗎？如果這個平台 TLB miss 本來就進 kernel，這兩個是同一條路，但圖上沒說。
3. **"Only a small interface"**：畫面上介面有 4 項，數量確實小。但其中 PTE format、TLB clear、lock rules 是最難的幾項，"small" 的說法讀者會懷疑。

## 8. 站在原本立場的反駁

被圖擋住的：
- 「兩者在同一個 core、同一條 fault path 上跑，所以要一起設計」：圖正面承認同一個 core、同一條路，然後把分開的理由放在表與硬體輔助的位置上。這一招擋住了「執行位置相同所以要合併」的論點。
- 「壓縮會用到 TLB 那種 core 內的硬體」：圖把壓縮的硬體輔助明確放在 core 外，所以不需要動 core 內的 MMU 硬體。
- 「要不要每個 core 一台 LZ4」：圖說 LZ4 HW 在外面、所有 core 共用、有好幾個 engine。

沒擋住的，我還會這樣反駁：
1. **PTE format 是共有的**：TLB miss handler 要從 PTE 判斷「這次需要壓縮層」，壓縮層要把 PTE 改成 compressed 或 present。PTE format 由誰擁有、編碼怎麼留空間，本來就是兩方的核心設計，圖把它放進「介面」，但介面裡這一項就是整個耦合。
2. **lock 的順序**：page table 一把 lock、COT 一把 lock。fault path 兩把都可能要拿，趕 page 也是。lock 順序與死結只能一起設計，圖上 "the lock rules for the page table" 只提 page table 這一把。
3. **時間預算**：壓縮的 kernel SW 跑在 TLB miss handler 後面，在同一個 exception 裡。最壞情況的 fault 時間是兩者加起來，誰負責這個預算？圖沒碰。
4. **TLB 清除與趕 page**：趕 page 是壓縮那一邊發起，但要清每個 core 的 TLB，這是 MMU 的機制。發起者與機制分屬兩方，跨 core 的同步要一起設計。
5. **兩邊的表都在 DRAM、都經過共用的 cache**：「表在不同地方」在實體上不成立，兩方的表會互相搶 cache 與 DRAM 頻寬。
6. **reclaim 沒畫**：誰、在哪個 core、什麼時候壓縮，會影響 MMU 那一方的 TLB clear 與 lock，圖完全沒碰。

我的結論：圖成功把「在同一個 core 跑」與「要合併設計」拆開，但只要我把耦合的焦點移到 PTE format、lock 順序與最壞時間，圖就擋不住，只能回答「這些就是介面」。

## 9. 困惑指數

**2 / 5**。主要訊息與角色都讀得出來；扣分在兩條橘色箭頭像是 core 分工、COT 與斜線方塊沒有說明、虛線的意思沒有圖例。

## 10. 可疑的錯字或多餘文字

- interface 框下方的小黑點，像是雜點。
- 同一個訊息講了三次：標題下的副標、黃框 "Why not co-design them"、Key point。副標與黃框幾乎逐句相同，黃框可以省，或改寫成反駁的回應。
- "Both kernel SWs"：SW 加複數 s 讀起來有點彆扭，但意思清楚。
- "a request: which page, which core"：不確定 "which core" 是否必要，若不必要就是多餘文字。
- "HW HELP:" 全大寫第一眼像求救，可考慮 "HW ASSIST:"。

## 總表

| 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|
| 2 / 5 | 大致清楚；缺 user SW、thread、reclaim；COT 與斜線方塊沒說明 | 部分一致：Key point 說表在 LZ4 HW 旁邊，畫面兩邊的表都在 DRAM；fault path 與 TLB miss handler 用詞不同 |

## 我用自己的話講的結論

這張圖承認壓縮層的 kernel SW 不是獨立的服務：它是 TLB miss handler 在 fault 的那個 core 上呼叫的一段程式，好幾個 core 可以同時各跑一份。它主張分開設計的理由不是「跑在不同地方」，而是「兩邊依賴的硬體在不同地方」：MMU 靠每個 core 裡的 TLB，壓縮靠 core 外共用的 LZ4 HW 和將來的輔助硬體。所以兩方只要談定 PTE format、TLB 清除、page table 的 lock 規則與 request 格式，其他各做各的。這個論點對「同一個 core 所以要合併」很有效，但對 PTE format、lock 順序、最壞時間這幾個真正耦合的地方，只是把它們歸到介面裡，沒有證明介面真的小。

## 建議重生與否

**不建議重生。** 困惑指數 2，角色大致清楚，最大的字沒有把 compression kernel SW 讀成只有一份（上方每個 core 各一份擋住了），畫面與 Key point 只有用詞層級的落差。建議小修，下次重生時順便處理：

1. 兩條橘色箭頭改從 processor 框中間出發，或兩個 core 各出兩條，避免讀成 Core 0 管 MMU、Core 1 管壓縮。
2. 副標與 Key point 的 "tables live in different places / sit beside the LZ4 HW" 改成「表由不同一方擁有」之類的說法，避免和畫面上的 "in DRAM" 衝突。
3. 圖例補上虛線與填色的意思，COT 第一次出現時展開。
4. Key point 的 "fault path" 與畫面的 "TLB miss handler" 統一用詞。
5. 去掉 interface 框下方的雜點。

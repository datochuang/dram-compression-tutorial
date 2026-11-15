# 冷讀驗收：two-stage-task 第 3 張（gen12）

- 日期：2026-11-15
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：two-stage-task 的第 3 張（gen12），`gen12/03-apart-even-in-software.png`
- 讀者立場：一位原本認為「壓縮層的 kernel SW 應該和 CPU MMU 的 kernel SW 一起設計」的工程師

## 1. 第一眼

前三秒讀到的是標題「Apart Even in Software」，再來是兩欄最大的字「TLB: INSIDE EACH CORE」和「LZ4 HW: SHARED BY ALL CORES」，以及兩個框的名字「CPU MMU domain」和「compression domain」。

第一印象：這張圖要說 CPU MMU 和壓縮層是分開的兩塊，分開的理由是「hardware 放在不同地方」：一個在每個 core 裡，一個在 core 外面大家共用。標題說的是 software 要分開，但最先跳出來的大字講的是 hardware 的位置。第一眼我會以為這張圖在比較兩種 hardware 的擺法，要再讀一層小字才會知道它在講 kernel SW 的設計分工。

## 2. 最大的字

**左欄「TLB: INSIDE EACH CORE」**
- 主詞：TLB。
- 性質：位置與份數。每個 core 裡面各有一個。
- 「只有一份」的讀法：沒有。這組字明白表示有很多份、每個 core 一份。

**右欄「LZ4 HW: SHARED BY ALL CORES」**
- 主詞：LZ4 HW。
- 性質：位置與共用關係。在 core 外面，所有 core 共用。
- 「只有一份」的讀法：有，而且有兩層。
  1. **LZ4 HW 只有一個、一次只做一件事。**「shared by all cores」很自然讀成「一台機器大家輪流用」。畫面上的 LZ4 HW 方塊也只有一個、沒有疊層。要讀到底部表格最後一列「more engines, still shared by all cores」才知道它可以有多個 engine。只看大字的人會以為 LZ4 HW 是單一 engine。
  2. **壓縮那一邊的 kernel SW 也是共用的單一服務。**這組大字放在 compression domain 欄的底部，位置和寫法都像整欄的總結。快速掃過的讀者會把整欄歸納成「compression = 共用、集中；CPU MMU = 每個 core 各自」，進而以為壓縮的 kernel SW 也是一個集中的、所有 core 呼叫的東西（像一個 server 或 manager）。這和欄內小字「runs on the core that faulted, many at once」相反。原本主張一起設計的工程師正好會抓這個讀法來反駁：「既然壓縮是集中的服務，為什麼不和 MMU 一起設計」。

另外，兩欄大字都在講 hardware，沒有一組大字在講 software。標題卻說「Even in Software」。主張與最醒目的證據之間有落差。

## 3. 人物與機器

| 方塊 | 我讀到的角色 | 是否清楚 |
|---|---|---|
| processor（含 Core 0、Core 1） | 處理器，畫兩個 core | 清楚 |
| CPU MMU and TLB（藍色實線） | 每個 core 裡的 hardware | 清楚 |
| TLB miss handler（紫色虛線）, runs on this core | 每個 core 上跑的 kernel SW | 大致清楚。紫色虛線代表 SW 是我猜的，圖上沒有圖例 |
| page table, in DRAM | DRAM 裡的 page table，CPU MMU 那邊擁有 | 清楚 |
| interface, agreed together | 兩邊一起約定的介面：request、PTE format、TLB clear、lock rules | 內容清楚，但它是「約定」不是會執行的東西，卻被畫成箭頭的起點與終點 |
| kernel SW: one module（紫色虛線、三層疊） | 壓縮層的 kernel SW，在發生 fault 的 core 上跑，可以同時多份 | 文字清楚；但方塊畫在 processor 外面、compression domain 裡，空間上像是在別處執行 |
| LZ4 HW（綠色實線、齒輪） | 壓縮 hardware，所有 core 共用 | 清楚；份數不清楚（見第 2 題） |
| future HW assists（綠色虛線） | 將來會加的 hardware 輔助：CRC、headers、chunk lists | 大致清楚；虛線代表「未來」是猜的 |
| PROPOSAL 標籤 | 整個 compression domain 是提案？還是只有 future HW assists？ | 不清楚 |

看不出來的角色：
- 沒有 user SW。page fault 是誰觸發的、被服務的是誰，畫面上沒有。
- CPU MMU 那邊除了 TLB miss handler 之外，處理 page fault、寫 page table 的 kernel SW 沒有畫出來。「applied by the CPU MMU side」的執行者是誰看不出來。
- COT 與 chunk pool 只在文字裡出現（「owns the COT and the chunk pool」），沒有畫，也看不出放在哪裡。COT 這個縮寫沒有解釋。

## 4. 看不懂的線或物件

1. **「page fault: a call on the same core」**：箭頭從 processor 外框出發，不是從某個 core 或 TLB miss handler 出發。page fault 是 exception，為什麼叫「a call」？是 TLB miss handler 呼叫壓縮層嗎？
2. **箭頭打進 interface 方塊**：interface 是一份約定，箭頭穿過它到 kernel SW，把執行流程和設計文件畫在同一條線上。讀者分不清 interface 是一段程式還是一份規格。
3. **「PTE update, TLB clear」回到 interface，再「applied by the CPU MMU side」到 page table**：到底是壓縮層自己寫 PTE，還是請 CPU MMU 那邊寫？TLB clear 誰執行、怎麼清其他 core？
4. **「a sub-action, once verified in SW」**：意思像是「某個子動作先用 SW 做、驗證過後才搬到 HW」，但也可以讀成「每次執行時先在 SW 驗證再交給 HW」。不確定。
5. **kernel SW 的三層疊框**：我猜代表多份同時執行。但只畫了 2 個 core，卻有 3 層，份數對不上。
6. **LZ4 HW 沒有回來的箭頭**：job 送出去之後，完成怎麼通知、通知到哪個 core，沒有畫。
7. **page table 的空白格子**：只是示意，沒問題。
8. **齒輪圖示**：代表 hardware 在運轉，無害。

## 5. 執行方式（只從畫面判斷）

- **在哪裡跑**：文字說「runs on the core that faulted」，所以是在發生 page fault 的那個 core 上跑，和 TLB miss handler 在同一個 core。但方塊畫在 processor 外面、compression domain 裡，空間上會讓人以為它在 processor 之外的某處執行。文字與位置互相矛盾，要靠文字才得到正確答案。
- **同一時間有幾份**：文字說「many at once」，疊框畫了 3 層。所以可以同時多份，最多大概是正在 fault 的 core 數。畫面沒說 hardware thread 會不會讓份數更多。
- **兩個 core 同時 page fault**：兩個 core 各自跑一份壓縮層 kernel SW，平行執行。碰到共用的 COT 與 chunk pool 時，由 lock 一次只讓一個通過（「a lock keeps only the shared steps one at a time」）。兩份都會送 job 給同一個共用的 LZ4 HW。LZ4 HW 能不能同時做兩個 job，畫面主體沒說，只有表格「more engines」暗示可以。兩邊的 PTE 更新與 TLB clear 要照 interface 裡的 lock rules，但規則本身沒畫。

## 6. 圖說的一句話

壓縮層雖然和 TLB miss handler 一樣是在發生 fault 的 core 上跑的 kernel SW，但它的共用狀態（COT、chunk pool）和將來的 hardware 輔助都放在 core 外面、跟著共用的 LZ4 HW，而 CPU MMU 的 hardware 輔助是每個 core 裡的 TLB，所以兩邊只需要一起約定一個小介面，其餘分開設計。

## 7. Key point 與畫面是否一致

**判定：一致（有一處措辭偏差）**

Key point 的每一句都能在畫面上找到：hardware 輔助在 LZ4 HW 旁邊、所有 core 共用；lock 只讓共用的步驟一次一個；只有小介面一起約定。

偏差：Key point 寫「Its code runs on every core at once」，畫面寫的是「runs on the core that faulted, many at once」。「every core at once」可以讀成「所有 core 同時都在跑它」，像是廣播或常駐，比畫面的意思強，也不精確。

說服力上的落差（不算不一致，但會影響那位工程師）：
- 標題主張「software 也要分開」，但畫面最醒目的證據是 hardware 擺在哪裡。hardware 擺在哪裡不直接決定 SW 要不要一起設計。真正支持 SW 分開的論點是「state 放在不同地方」（COT、chunk pool vs page table），這只出現在表格第一列和黃框的小字裡。
- interface 方塊被稱為「small」，但裡面列的是 PTE format、每個 core 的 TLB clear、page table 的 lock rules，正是兩邊最難、最容易出錯的部分。主張一起設計的工程師會說：「最難的部分本來就要一起設計，你只是把它叫做 interface。」圖沒有回應這一點。

## 8. 困惑指數

**3 / 5**。主訊息讀得出來，但最大的字講的是 hardware 而不是 software，而且「LZ4 HW: SHARED BY ALL CORES」放在欄底像整欄總結，容易被讀成「壓縮這一側是單一、集中的東西」；壓縮 kernel SW 的方塊畫在 processor 外面，與「runs on the core that faulted」矛盾。

## 9. 可疑的錯字或多餘文字

- 「page fault: a call on the same core」：page fault 是 exception，不是 call。用詞可疑。
- 「a lock keeps only the shared steps one at a time」：「one at a time」字擠在一起（看起來像 one at atime）；整句文法略彆扭。
- 「a sub-action, once verified in SW」：意思有兩種讀法。
- 「PROPOSAL」標籤：不知道作用範圍。
- Key point 的「runs on every core at once」與畫面「the core that faulted」不一致。
- 重複：「LZ4 HW 在 core 外、所有 core 共用」在大字、大字下的小字、表格、黃框、Key point 共出現五次；而支持 SW 分開的「state 在不同地方」只出現兩次且字小。
- COT 縮寫沒有解釋。
- 沒發現英文拼字錯誤。

## 總表

| 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|
| 3 / 5 | 大致清楚；缺 user SW、缺 CPU MMU 側寫 page table 的 SW、COT 與 chunk pool 沒畫；PROPOSAL 範圍不明 | 一致（Key point「every core at once」措辭偏差） |

## 我的結論

這張圖要說：壓縮層即使全部是 kernel SW、而且和 TLB miss handler 一樣在 fault 的那個 core 上跑，也不該和 CPU MMU 的 kernel SW 一起設計，因為兩邊保護的共用狀態不同（page table vs COT 與 chunk pool），將來的 hardware 輔助也長在不同地方（每個 core 裡的 TLB vs core 外共用的 LZ4 HW），所以只要約定一個小介面。訊息讀得出來，但對一位原本主張一起設計的工程師，它不夠有說服力：最大的字只講 hardware 的位置，沒講 software；「SHARED BY ALL CORES」放在壓縮欄的底部，容易讓人以為壓縮那一側（連同 kernel SW）是單一、集中的東西；壓縮 kernel SW 畫在 processor 外，與「在 fault 的 core 上跑」矛盾；而被稱為「small」的 interface 裝的正是 PTE、TLB clear、lock rules 這些最難的部分。

## 建議重生與否

**建議重生（小幅修改即可）。** 理由：困惑指數 3，且最大的字有誤導讀法（LZ4 HW 只有一個；壓縮側是集中的單一服務）。建議方向：
1. 讓一組大字講 software 本身，例如兩欄都加一行「kernel SW: runs on the faulting core, many at once」，或把大字改成「state」的對比（page table vs COT 與 chunk pool）。
2. 把壓縮 kernel SW 的多份實例畫在 Core 0 與 Core 1 裡面（或用虛線把它連回各 core），疊框份數與 core 數一致。
3. LZ4 HW 方塊畫成內含多個 engine，或在大字旁註明「N engines」。
4. Key point 改成「runs on whichever core faulted, several at once」。
5. 把 page fault 的箭頭從 core（或 TLB miss handler）出發，避免叫它「a call」；interface 不要當執行流程的中繼站。
6. 正面回應「interface 裡正是最難的部分」：例如註明 interface 的規則由哪一邊擁有、另一邊只照用。

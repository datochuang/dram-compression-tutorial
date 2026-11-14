# 冷讀報告：gen10/03-apart-even-in-software.png

- 日期：2026-11-14
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：two-stage-task 的 gen10/03-apart-even-in-software.png
- 讀者立場：認為「CPU 的記憶體管理」和「壓縮層」是同一件事、應該一起設計的團隊成員

## 第一眼兩秒鐘

左右兩個大虛線框對立：左邊藍色「CPU MMU domain」，右邊綠色「compression domain」，中間夾一個小的白色方塊「interface, agreed once」。兩個框底下各有一句大字：左邊「ONE PER CORE」，右邊「ONE SHARED SET」。第一眼的訊息很清楚：兩塊分開，中間只有一個小介面。下方有一張對照表和一個黃色的「Why not co-design them」。

## 遮住 Key point 後的閱讀

### 1. 機器與方塊

| 方塊 | 我讀到的角色 | 清楚嗎 |
|---|---|---|
| CPU MMU domain（藍色虛線大框） | CPU 這一側管位址轉換的範圍 | 清楚 |
| processor | 一顆 processor，裡面畫兩個 core | 清楚 |
| Core 0、Core 1 | 兩個 core，各自一份相同的內容 | 清楚 |
| CPU MMU and TLB（藍色實心） | 每個 core 內建的硬體：MMU 和 TLB | 清楚 |
| TLB miss handler, runs on this core（紫色虛線） | TLB miss 時在該 core 上跑的 kernel SW。紫色虛線和右邊的 kernel SW 同一種畫法，我推測紫色虛線代表 kernel SW、藍色實心代表硬體。圖上沒有圖例說明這個配色 | 大致清楚，配色要自己推 |
| page table, in DRAM | 放在 DRAM 的 page table，標「owned by the CPU MMU side」 | 清楚 |
| interface, agreed once | 兩邊唯一共同設計的東西，內容是三項：request（哪個 page、哪個 core）、PTE format、對每個 core 的 TLB clear | 清楚 |
| compression domain（綠色虛線大框），右上角 PROPOSAL | 壓縮層的範圍。PROPOSAL 是指整個右框都是提案，還是只有「one manager」這種組法是提案，看不出來 | 部分不清楚 |
| kernel SW: one manager | 壓縮層的 kernel SW，接所有 request，擁有 COT 和 chunk pool。COT 是什麼圖上沒有解釋；chunk pool 可以猜是放壓縮後資料的地方 | 角色清楚，COT 不懂 |
| LZ4 HW（齒輪），shared by all cores | 壓縮硬體，所有 core 共用 | 清楚 |
| future HW assists（綠色虛線），CRC, headers, chunk lists | 未來可能加的硬體輔助，與 LZ4 HW 放在一起、一套共用。虛線表示「還沒有」 | 清楚 |

沒有標籤的方塊：沒有。但「may dispatch to parallel workers」提到的 workers 沒有畫出來。

### 2. 看不懂的線或物件

1. **「page fault from any core」這條箭頭從 processor 框的邊緣出發**，不是從 TLB miss handler 出發。圖上已經畫了每個 core 有一個 TLB miss handler（kernel SW），那 page fault 是誰發出來的？是 CPU MMU 硬體、還是 TLB miss handler 查完 page table 發現 page 不在之後轉交的？對「應該一起設計」的人來說，這正是邊界最該說清楚的地方，圖上卻是模糊的。
2. **「PTE update, TLB clear」回到 interface 之後，只有一條「applied by the CPU MMU side」箭頭指到 page table**。PTE update 有去處，但 TLB clear 沒有任何箭頭回到 Core 0、Core 1 的 TLB。誰去清、怎麼清到另一個 core，看不出來。
3. **「ONE PER CORE」大字放在 page table 正下方**，第一眼像在說「page table 一個 core 一份」。要讀到下一行小字「its hardware help is the TLB, built into each core」才知道指的是硬體輔助。
4. 「a sub-action, once verified in SW」：意思大概是「某個子動作先在 SW 裡驗證過，才搬進 HW」，但讀第一遍不容易懂。
5. 「kernel SW can override everything they write」：可以理解（HW assists 寫的東西 SW 可以蓋掉），但為什麼這對「要不要一起設計」重要，圖上沒有連起來。
6. 「runs on a core like any kernel SW」：kernel SW manager 畫在 processor 框外面、右邊的綠框裡。文字說它跑在某個 core 上，畫面卻把它放在 processor 外面。我理解這是「設計上的歸屬」而不是「實體位置」，但沒有寫出來。

### 3. 圖說的一句話（只看畫面）

CPU MMU 的東西每個 core 一份、長在 core 裡面；壓縮層的東西全部 core 共用一份、長在 LZ4 HW 旁邊；兩邊只共同訂一個小介面（request、PTE 格式、TLB clear），其餘分開設計。

### 4. 論點

**主張**：即使壓縮層一開始全部是 kernel SW，也不該和 CPU MMU 的 kernel SW 一起設計。

**理由**（圖上給的）：
- 兩邊「長大的地方」不同。CPU MMU 這邊的工作在 miss 的那個 core 上做，硬體輔助是每個 core 內建的 TLB，擴充方式是一個 core 一份。
- 壓縮這邊的工作集中在一個 manager，硬體輔助是 LZ4 HW 旁邊的一套共用 assists，擴充方式是加 worker 和 engine，不跟 core 數走。
- 所以兩邊之間只需要一個小介面。

**站在「應該一起設計」的立場，有沒有被說服**：部分被說服。

被說服的部分：「硬體輔助將來放在哪裡」這一點很有力。我原本可能想把壓縮相關的硬體塞進每個 core 的 MMU 裡，這張圖讓我看到那樣會變成一個 core 一份，而壓縮的工作本質上是共用的。對照表把「where the work runs / where hardware help goes / how it scales」三行並排，很容易對照。

還剩的反駁：

1. **page table 是共用的資料，圖上只說「owned by the CPU MMU side」。** 壓縮層要改 PTE（把 page 標成不在、再標回來），CPU 那邊的 TLB miss handler 同時在讀同一張表。誰拿什麼 lock、更新的順序，必須兩邊一起決定。圖把它塞進「the PTE format」一行，只談格式、沒談同時存取。我會說：這不是「agreed once」的小介面，是持續要一起維護的共用狀態。
2. **TLB clear 的機制在 CPU 那一側，但正確性和延遲由壓縮層承擔。** 圖把「a TLB clear for every core」列為介面的一項，卻沒畫誰執行、怎麼到達另一個 core。清 TLB 的成本會直接進壓縮層趕出 page 的時間。這一項我不接受只用一行帶過。
3. **TLB miss handler 是 kernel SW，而且是 fault 第一個被看到的地方。** 圖上每個 core 都有一個 TLB miss handler，跟壓縮層的 manager 一樣是 kernel SW。如果是 handler 查表發現 page 被壓縮了、再轉給 manager，那邊界就在同一段 exception 程式裡面，兩邊的 code 緊緊相連。圖的「page fault from any core」箭頭從 processor 框出發，正好把這個問題遮掉了。
4. **效能是串在一起的。** 一次 fault 的總時間是 TLB miss handler + 介面 + manager + LZ4 HW + PTE update + TLB clear。分開設計時，誰負責整條路徑的最壞情況？圖上沒有回答。
5. **「grow in different places」不等於「可以分開設計」。** 擴充方式不同是事實，但兩邊共用 page table、共用 DRAM、（我猜）共用 cache。不同的長法也可能正是需要一起協調的理由。
6. **論點有一部分靠「future HW assists」與 PROPOSAL。** 右邊的「ONE SHARED SET」依賴一個還不存在的東西。如果那套 assists 最後沒有做，右邊的「硬體輔助長在共用的地方」就只剩 LZ4 HW 一個。

**共用的東西（page table、清 TLB）圖上怎麼處理，接不接受**：圖的處理是把它們放進中間的「interface, agreed once」，並標上「the only part designed together」。我接受「這幾項要一起訂」的方向，但不接受「agreed once」的說法：page table 的同時存取規則、TLB clear 跨 core 的機制與成本，看起來是會一直一起演進的東西，不是訂一次就結束。而且 TLB clear 在圖上沒有箭頭回到任何 TLB，等於畫了名字、沒畫路徑。

### 5. 讀 Key point 之後：畫面和結論一致嗎

Key point：「Even as pure kernel SW, the compression layer is designed apart from the CPU MMU's kernel SW: its future hardware help is one shared set beside the LZ4 HW, not inside each core. Only a small interface is agreed together.」

**一致。** 畫面左右分開、中間小介面、左「ONE PER CORE」右「ONE SHARED SET」，都和 Key point 對得上。Key point 的理由集中在「硬體輔助的位置」，畫面也把這點放得最大。

小落差：Key point 說「only a small interface」，但畫面上介面裡的 TLB clear 沒有路徑可追，讀者無法從畫面確認它真的「small」。

### 6. 困惑指數

**2 / 5**。主結構一眼就懂，對照表把理由講清楚；扣分在 page fault 從哪裡發出、TLB clear 沒有路徑、「ONE PER CORE」放在 page table 下方容易誤讀、COT 沒有解釋。

### 7. 可疑的錯字或多餘文字

- 沒有看到錯字。
- 重複：同一個結論在副標、對照表、「Why not co-design them」黃框、「ONE PER CORE / ONE SHARED SET」大字、Key point 共出現五次。黃框和 Key point 幾乎是同一段話，可以考慮只留一個。
- 「ONE SHARED SET」下面的小字「its hardware help sits beside the LZ4 HW, used by every core」與上方 future HW assists 框裡的「one shared set, beside the LZ4 HW」重複。
- 「COT」沒有展開，第一次接觸的讀者不知道是什麼。

## 結論

**用自己的話說**：CPU MMU 的工作和硬體幫手都長在每個 core 裡（TLB、TLB miss handler），壓縮層的工作和硬體幫手都長在一個所有 core 共用的地方（一個 manager、LZ4 HW 與它旁邊的 assists）。既然兩邊擴充的位置不同，就各自設計，只共同訂一個小介面：fault 怎麼送過去、PTE 長什麼樣、TLB 怎麼清。

**總表**

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 / 5 |
| 角色是否清楚 | 是（COT 未解釋、kernel SW 與 HW 的配色沒有圖例，屬小問題） |
| 畫面與結論是否一致 | 一致 |

**是否建議重生**：不建議。困惑指數低於 3、角色清楚、箭頭方向沒有和故事矛盾、畫面與結論一致，不符合重生的條件。

若要小修（不必重生），建議的方向：
1. 「page fault from any core」箭頭改從 TLB miss handler 出發，或註明誰發出。
2. 給 TLB clear 畫一條回到各 core TLB 的路徑，並標出機制未定。
3. 「ONE PER CORE」與 page table 拉開，避免誤讀成 page table 一個 core 一份。
4. 介面裡的 PTE format 補一句同時存取（lock）也屬於共同訂的部分，回應「agreed once」太樂觀的質疑。

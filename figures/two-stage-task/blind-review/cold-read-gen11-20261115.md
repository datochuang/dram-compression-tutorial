# 冷讀報告：two-stage-task 第 3 張（gen11）

- 日期：2026-11-15
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：`figures/two-stage-task/gen11/03-apart-even-in-software.png`（標題「3 Apart Even in Software」）
- 讀者立場：原本認為「壓縮層的 kernel SW 應該和 CPU MMU 的 kernel SW 一起設計」的工程師

---

## 1. 人物與機器

圖上沒有人物，全部是方塊。我從畫法讀出一套沒有圖例的慣例：藍色實線框是 CPU 裡的硬體，紫色虛線框是 kernel SW，綠色實線框是現有的硬體，綠色虛線框是未來的硬體。這套慣例可以猜出來，但圖上沒有寫。

**左邊：CPU MMU domain（藍色虛線大框）**

| 方塊 | 標籤 | 在做什麼／在意什麼 |
|---|---|---|
| 外框 | processor | 裝兩個 core |
| Core 0、Core 1 | Core 0、Core I | 每個 core 一份。「Core I」看起來像字母 I，但讀得出來是 1 |
| 藍色實線框（每個 core 一個） | CPU MMU and TLB | 每個 core 自己的硬體。在意的是「每個 core 各一份」 |
| 紫色虛線框（每個 core 一個） | TLB miss handler, runs on this core | 每個 core 自己跑的 kernel SW |
| 白框 | page table, in DRAM | 下面寫「owned by the CPU MMU side」 |
| 大字 | ONE PER CORE | 「its hardware help is the TLB, built into each core」 |

**中間**

| 方塊 | 標籤 | 在做什麼 |
|---|---|---|
| 黑色粗框 | interface, agreed together | 列出四項：a request: which page, which core；the PTE format；a TLB clear for every core；the lock rules for the page table。下面寫「the only part designed together」 |

**右邊：compression domain（綠色虛線大框，右上角貼了「PROPOSAL」）**

| 方塊 | 標籤 | 在做什麼／在意什麼 |
|---|---|---|
| 紫色虛線框，疊成三張卡片 | kernel SW: one module, runs on the core that faulted, many at once | 壓縮層的 kernel SW。下面寫「owns the COT and the chunk pool; a lock keeps only the shared steps one at a time」 |
| 綠色實線框，有齒輪 | LZ4 HW, shared by all cores | 從 kernel SW 收「a job」 |
| 綠色虛線框 | future HW assists: one shared set, beside the LZ4 HW, CRC, headers, chunk lists | 從 kernel SW 收「a sub-action, once verified in SW」。下面寫「kernel SW can override everything they write」 |
| 大字 | ONE SHARED SET | 「its hardware help sits beside the LZ4 HW, used by every core」 |

**下方**：「Where each one grows」三列對照表，右邊黃色便條「Why not co-design them」。

**角色看不清楚的地方**

- **「the CPU MMU side」到底是誰。**「applied by the CPU MMU side」、「owned by the CPU MMU side」裡的 side 是團隊、硬體，還是某一段 kernel SW？左邊唯一的 kernel SW 是 TLB miss handler。如果 PTE 是由它以外的 kernel SW 去改，圖上沒有畫那段程式。
- **page fault 是誰發出的。** 箭頭從 processor 外框出發，不是從某個 core 或 TLB miss handler 出發。觸發 fault 的 user SW 沒有畫出來。
- **COT 與 chunk pool 只有文字，沒有畫成物件。**COT 這個縮寫圖上沒有解釋。
- **「PROPOSAL」貼紙管到哪裡**：是整個 compression domain，還是只有 future HW assists？

## 2. 看不懂的線或物件

1. **「page fault: a call on the same core」**：文字說是同一個 core 上的 function call，但箭頭跨過 domain 的邊界，射向很遠的地方。畫面給人「送到別處」的印象，和「same core」互相拉扯。
2. **interface 方塊當成中繼站**：箭頭從 processor 進 interface，再從 interface 出到 compression 的 kernel SW；回程「PTE update, TLB clear」進 interface，再由「applied by the CPU MMU side」射到 page table。interface 是一份約定，不是一個會動的東西，但畫面上它像一個轉送訊息的元件。
3. **「a TLB clear for every core」沒有落點**：沒有任何箭頭從 interface 回到 Core 0 或 Core 1 的 TLB，只有一條線去 page table。TLB clear 怎麼送到每個 core，畫面沒有交代。
4. **「a sub-action, once verified in SW」**：這個 once 可以讀成「在 SW 驗證過之後，才移到 HW」（開發階段的意思），也可以讀成「執行時，SW 每次驗證過才送」（runtime 的意思）。我傾向前者，但不確定。
5. **右上角的三張疊卡**：我讀成同時有好幾份在跑。但旁邊緊貼著「PROPOSAL」，也可能被誤讀成「好幾個提案版本」，或「一排等著做的 job」。
6. **沒有回程線**：LZ4 HW 做完之後怎麼通知 kernel SW，圖上沒有畫。這張圖的重點不在這裡，不算錯，但第一次看會想問。
7. **表格「more engines」**：圖上的 LZ4 HW 只畫成一個方塊，engine 這個字在表格裡第一次出現，沒有對應的物件。

## 3. 圖說的一句話（不看 Key point）

CPU MMU 那一邊的硬體幫手（TLB）每個 core 一份，表格放在 DRAM 的 page table；壓縮那一邊的 kernel SW 雖然也在發生 fault 的 core 上跑，但狀態（COT、chunk pool）和硬體幫手（LZ4 HW 與未來的 assists）是所有 core 共用的一套。所以兩邊只需要一起約定一個小 interface，其餘分開設計。

## 4. 執行方式

- **在哪裡跑**：在發生 page fault 的那個 core 上跑，是被呼叫進去的（「page fault: a call on the same core」、「runs on the core that faulted」）。不是專用的 core，也不是另一個 processor。
- **同一時間有幾份**：可以有好幾份，同一份程式（one module）在不同的 core 上同時執行（「many at once」，加上三張疊卡）。
- **兩個 core 同時 page fault**：Core 0 和 Core 1 各自跑一份壓縮層的 kernel SW，彼此不等，直到碰到共用的步驟（改 COT、拿 chunk pool）。那幾步由一個 lock 一次只放一份過去。兩份都可以各自把 job 交給同一個 LZ4 HW。改 PTE 與清 TLB 經過 interface，照「the lock rules for the page table」由 CPU MMU 那邊處理。
- **讓我這樣想的元素**：「runs on the core that faulted, many at once」、疊卡、「a lock keeps only the shared steps one at a time」、「LZ4 HW shared by all cores」，以及黃色便條「both run on the core that faulted」。
- **右上角那疊卡片**：我讀成同一個 module 的多份同時執行（一個 core 一份）。
- **畫面上和這個讀法衝突的地方**：壓縮層的 kernel SW 被畫在離 processor 很遠的另一個 domain 裡，疊卡也沒有連到 Core 0 或 Core 1。光看空間位置，會以為它在別的地方跑。「它在 faulting core 上跑」完全是靠文字撐起來的，畫面沒有幫忙。另外，「one module」配上一疊卡片也有點矛盾：一份程式，多份執行。要讀過文字才會懂。
- **圖沒有回答的**：兩個 core 對同一個 page 同時 fault 怎麼辦；壓縮層握著自己的 lock 去改 PTE 時，和 page table 的 lock 誰先誰後。

## 5. Key point 與畫面是否一致

**一致**，有兩處小落差：

- Key point 說「Its code runs on every core at once」，畫面說的是「runs on the core that faulted, many at once」。every core 比 the core that faulted 強，可能被讀成每個 core 永遠都在跑。
- Key point 開頭強調「Even as pure kernel SW」，但畫面裡最有份量的論據，也就是 ONE SHARED SET 與 future HW assists，是未來的硬體，而且貼著 PROPOSAL。「現在純 SW 時為何也要分開」這件事，畫面上的論據只有「state 在不同的地方」（表格第一列與黃色便條第二行），比較單薄。

## 6. 站在原本立場的反駁

**被圖擋住的反駁**

- 「兩個都是在同一個 core 上跑的 kernel SW，當然一起設計。」→ 圖承認兩者都在 faulting core 上跑，但指出 state 和硬體幫手在不同的地方（page table 對 COT、chunk pool；TLB 對 LZ4 HW 旁邊）。
- 「將來的硬體幫手會像 TLB 一樣放進每個 core，所以要一起規劃。」→ 圖直接說是 one shared set，放在 LZ4 HW 旁邊。
- 「PTE 格式、TLB 清除、lock 都要兩邊一起決定。」→ 這些就列在 interface 方塊裡，圖說這部分一起做。

**沒被擋住的反駁**

- **interface「小」是宣稱，不是證明。**「a TLB clear for every core」是跨 core 的 TLB shootdown 機制，「the lock rules for the page table」是 lock 順序與持有時間。這兩項各自都是大題目，而且正是最容易出錯的地方。把它們寫成四行，不代表它們小。
- **兩把 lock 的關係。** 壓縮層有自己的 lock（COT、chunk pool），還要改 page table（page table 的 lock）。巢狀的順序、會不會 deadlock、握多久，正好需要兩邊一起設計。圖沒有交代。
- **TLB miss handler 是 hot path。** TLB miss handler 讀 PTE 時，壓縮層可能正在改同一個 PTE。handler 要不要拿 lock？PTE 裡「被壓縮」的標記怎麼編，才不會拖慢每一次 TLB miss？這些都會影響 CPU MMU 那邊的設計，不只是 interface。
- **reclaim（把 page 趕出去壓縮）整條沒畫。** 圖只畫 fault 進來的方向。誰挑要壓的 page、accessed 的資訊由誰記錄、趕出時怎麼讓 PTE 失效並清掉每個 core 的 TLB，都不在 interface 的四項裡。這是最可能需要和 CPU MMU 一起設計的部分。
- **時序。** CPU MMU 還沒 bring up。如果分開設計，PTE 格式會不會在壓縮層的需求進來之前就定下來？圖說 interface「agreed together」，但沒說什麼時候。
- **共用的 L2 與 cache 維護**：兩邊的表都在同一個 L2 裡競爭，圖沒有提。

## 7. 困惑指數

**2**。角色和左右對照很清楚，表格與黃色便條把結論重複了好幾次。扣分的地方：壓縮層的 kernel SW 在空間上被畫在 processor 外面，和「runs on the core that faulted」打架；「the CPU MMU side」是誰不明；「once verified in SW」有兩種讀法。

## 8. 可疑的錯字或多餘文字

- 「Core I」：手寫的 1 像字母 I。
- 「COT」沒有展開，第一次看的人不知道是什麼。
- 表格的「more engines」：圖上沒有畫 engine，這個字沒有前文。
- 「PROPOSAL」貼紙的範圍不明，又緊貼著疊卡，容易誤讀。
- 重複：「one shared set／ONE SHARED SET」在圖上出現了四到五次（方塊內、大字、表格兩格、Key point）。副標題與黃色便條也重述了 Key point。不算錯，但有點擠。
- 「CPU MMU and TLB」：TLB 本來就是 CPU MMU 的一部分，這樣寫有點多餘，不過對新手反而清楚。
- 「Where each one grows」的 grows 是比喻，意思是「往哪裡長大」，要讀完表格才懂。

---

## 總表

| 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|
| 2 | 是（「the CPU MMU side」略不明） | 一致（Key point 的「every core」比畫面強，「Even as pure kernel SW」的論據在畫面上偏弱） |

## 我用自己的話講的結論

壓縮層一開始雖然只是 kernel SW，而且和 TLB miss handler 一樣是在發生 fault 的那個 core 上跑、可以好幾個 core 同時跑，但它管的東西（COT、chunk pool）與將來的硬體幫手（LZ4 HW 旁邊的一套共用 assists）都是所有 core 共用一份；CPU MMU 的硬體幫手（TLB）則是每個 core 一份，它的表在 page table。兩邊長大的方向不同，所以只把「request、PTE 格式、TLB clear、page table 的 lock 規則」這個小 interface 一起約定，其餘分開設計。

## 建議重生與否

**不建議重生。** 困惑指數 2，角色清楚，畫面與結論一致，不符合重生條件。如果日後要改，可以考慮這幾處小修，但都不急：

1. 從 Core 0、Core 1 各拉一條細線到疊卡，或在疊卡旁畫小的 core 標記，讓「runs on the core that faulted」在畫面上也成立。
2. 把「the CPU MMU side」改成具體的角色。
3. 把「once verified in SW」改成不會有兩種讀法的說法。
4. 補上 COT 的全名，或在表格裡把 engines 改成和圖上一致的字。

另外要注意：這張圖沒有擋住的反駁（兩把 lock 的順序、TLB miss handler 的 hot path、reclaim 路徑）是內容的問題，重生解決不了。應該在文件或下一張圖裡回應。

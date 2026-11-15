# 冷讀驗收報告：kernel-sw-design gen4 第 9、12 張

- 日期：2026-11-15
- 方法：只給圖、不給提示詞的冷讀
- 讀的圖：kernel-sw-design 第四輪（gen4）的第 9 張 `09-keeping-faults-short.png` 與第 12 張 `12-where-it-goes-wrong.png`
- 讀者設定：第一次看這組圖的工程師，只知道前八張介紹過的名詞（page、frame、TLB、page fault、chunk、COT、mm_lock、reclaimer、watermark、UI/MEDIA/NET/LOG、kernel 自己的 decoder）

---

## 第 9 張：Design Choice: Keep Compression Off the Fault

### 1. 人物與機器

- 左上「A common general-purpose kernel」：一般 kernel 的兩種做法。
  - background reclaim thread：在背景把記憶體釋放到某個 watermark。
  - direct reclaim：背景跟不上時，需要記憶體的那個 thread 自己動手壓縮 page。底下藍字說平均快，但最壞情況長，因為那次 fault 可能要先壓好幾個 page。
- 右上「Ours」：我們的設計。
  - reclaimer thread：把 free frame 補到 high watermark。
  - 虛線框加 OPEN 標籤：「keep it this way, or add direct reclaim?」。框內寫 today: no direct reclaim，reclaimer 跟不上時 fault 就睡著，等到有 free frame。
  - 藍字：今天 fault 從不壓縮；最壞情況取決於 reclaimer 釋放 frame 的速度。
- 中間大框「Ours, simulated: the four programs at five loads」：模擬表，五種負載（normal、4、10、20、40 倍）。
- 右側「Two knobs」：可調的兩個旋鈕，watermark 多高、reclaimer 同時跑幾個 COMPRESS job。
- 表下藍字：負載的定義（normal 指每支程式在兩次記憶體存取之間自己工作 20 µs，4 倍是 5 µs），以及模擬條件（小型模擬機器、LZ4 HW 有四個 engine、每個 engine 一次跑一個 job、reclaimer 同時維持兩個 COMPRESS job）。

### 2. 看不懂的線、表格、數字或物件

- 「faults that waited for a frame, in one run」：一次 run 有多長、總共有幾次 fault，圖上沒有。716 次占多少比例無從判斷。
- 「most-stalled program: share of time waiting」：等的是什麼？normal 負載下等 frame 的 fault 是 0，但這欄仍是 1.9%。我推測這欄算的是所有 fault 的等待（包含解壓縮本身），不只是等 frame。圖上沒有說清楚，新手容易以為和第一欄矛盾。
- 「most-stalled program」是四支程式裡的哪一支？每一列是不是同一支？沒有標。
- 負載定義「between two memory accesses」：真實程式每幾個 ns 就碰一次記憶體，20 µs 才一次存取聽起來很怪。我猜是指會 fault 的那種存取，或模擬裡對共用區域的存取，但圖上沒說。
- 「slowest in a hundred」我讀作 p99，「slowest of all」讀作最大值。讀得懂，但「in a hundred」這種說法第一眼要想一下。
- Two knobs 與表格的關係：表格裡兩個旋鈕都固定（watermark 的值沒寫，COMPRESS 是 2），所以表沒有展示轉旋鈕的效果。新手不知道這兩個旋鈕是「直接解決 OPEN 問題的替代方案」，還是只是附帶說明。

### 3. 新手卡住的地方

- 第一欄是 0、最後一欄卻不是 0：會停下來想「不是沒等嗎？」。這是唯一真的會卡住的地方。
- 左右兩邊各自說了「worst case」，但左邊沒有數字，無法比較哪個最壞情況比較短。這不會讓人卡住，只是比較停在文字上。

### 4. 圖說的一句話（只看畫面）

我們不讓 fault 做壓縮，靠 reclaimer 在背景維持一批 free frame；模擬顯示負載 4 倍以內沒有 fault 等 frame，10 倍以上開始等，而且越來越多；要不要像一般 kernel 那樣加 direct reclaim 還沒決定。

### 5. Key point 與畫面是否一致

Key point：有 free frame 的存量、所有壓縮都在背景時，normal 負載的 fault 從不等 frame；重負載下會等，怎麼限制這個等待還沒決定。

判定：**一致**。normal（以及 4 倍）是 0，10 倍以上不是 0，「still open」對應 OPEN 框。小提醒：「never」來自一次模擬，畫面上也只有一次 run，用詞比證據強一點，但不算不一致。

### 6. 困惑指數

**2**。結構與對照清楚，唯一的絆腳石是最後一欄的「waiting」與第一欄「waited for a frame」看起來指不同東西卻沒說明。

### 7. 可疑的錯字或多餘文字

- 沒有看到錯字。
- 左邊說「up to a watermark」、右邊說「up to the high watermark」，用詞不一致，但可以理解為刻意（一般 kernel 泛稱、我們的設計具體）。

### 第 9 張另外的問題

- **direct reclaim 在 Ours 這邊**：還沒決定。畫面用 OPEN 標籤與「keep it this way, or add direct reclaim?」明講是未決問題，「today: no direct reclaim」是現在的狀態，不是定案。
- **表格的數字**：是 Ours 的數字，標題寫「Ours, simulated」。而且是「今天」的 Ours：沒有 direct reclaim、LZ4 HW 四個 engine、reclaimer 同時維持兩個 COMPRESS job。左邊一般 kernel 沒有任何數字。

---

## 第 12 張：Where It Goes Wrong If You Are Careless

### 1. 人物與機器

六張卡片，每張都是一個風險、一條規則、一個負責人。

1. Stale cache lines（圖示：cache 與 DRAM 兩個方塊）：LZ4 HW 直接讀寫 DRAM，CPU 的 cache 可能有新或舊的副本。規則：COMPRESS 前把 frame 寫回 DRAM，DECOMPRESS 後丟掉 cache 的舊副本。負責：kernel。
2. A TLB that still points at the frame（圖示：四格表、一格打叉）：某個 core 繼續用一個已經裝了別的 page 的 frame。規則：frame 重用前，把該 page 從每個 core 的 TLB 清掉。負責：kernel。
3. A page pushed out too soon（圖示：一張紙往外的箭頭）：reclaimer 選中剛被拿回來的 page，需要它的那條指令還沒跑，於是一直 fault。規則：reclaimer 跳過每個 thread 最近 fault 進來的 page。負責：kernel。
4. A fault where nobody may wait（圖示：被劃掉的時鐘）：不能睡的程式碼（interrupt handler、持有 lock 的程式碼、hard real-time thread）碰到壓縮過的 page。規則：這種程式碼永遠不碰：把 page 釘在 frame 裡，或那塊記憶體不參加壓縮。負責：kernel 以及寫那段程式碼的人。
5. A wrong answer from the LZ4 HW（圖示：齒輪加問號）：HW 把好的壓縮串流報成壞的，或根本不回答，page 會被丟掉。規則：HW 失敗時用 kernel 自己的 decoder 再解一次；連續三次錯誤答案或一次沒回答，就停用 HW。負責：kernel。
6. Two jobs on one frame（圖示：兩個箭頭指向一個方塊）：LZ4 HW 的兩個 engine 同時寫同一個 frame 或 chunk。規則：frame 與 chunk 在 mm_lock 下分配；HW 不檢查。負責：kernel。

### 2. 看不懂的線、表格、數字或物件

- 卡片 3「each thread's last faulted-in pages」：最近幾個？是每個 thread 一個，還是一小批？沒有數字也沒說要問誰。
- 卡片 4「pin the page in its frame」：pin 這個詞在前面的介紹裡沒出現（至少背景沒提到），新手要猜是「不准被 reclaimer 選走」。
- 卡片 5「three wrong answers in a row」：「wrong」怎麼判定？我推測是 HW 說壞、kernel decoder 卻解成功，就算一次錯誤答案。圖上沒說。「never answers」等多久算沒回答，也沒說。
- 卡片 5 只談 HW 把好串流報成壞的。HW 報「成功」但結果其實錯的情況，卡片沒提。新手會問：那種錯誤誰抓？
- 卡片 5「stop using the HW」之後 COMPRESS 怎麼辦？kernel 只有 decoder，有沒有 encoder 沒說。
- 圖示 2（四格、一格打叉）若不讀文字看不出是 TLB；圖示 3 看起來像「匯出檔案」。不影響理解，因為標題緊鄰。

### 3. 新手卡住的地方

- 副標題說「skipping one breaks data」，但卡片 3（反覆 fault，是卡死不是資料錯）與卡片 4（等待不能等的程式碼，是時序問題）都不是資料損壞。認真讀的人會覺得副標題不完全對。
- 卡片 5 的計數規則（三次錯誤、一次沒回答）需要停下來想「wrong 是怎麼知道的」。

其他卡片都可以獨立讀懂。

### 4. 圖說的一句話（只看畫面）

LZ4 HW 自己不做保護，六種會出錯的地方幾乎全靠 kernel 的紀律：清 cache、清 TLB、不要馬上把剛拿回來的 page 又趕出去、不能等的程式碼別碰壓縮記憶體、HW 說壞時自己再解一次、同一個 frame 或 chunk 一次只給一個 job。

### 5. Key point 與畫面是否一致

Key point：LZ4 HW 不檢查讀寫的位置。kernel 讓 cache 與 TLB 不留舊副本、保護剛回來的 page、一次只把一個 frame 交給一個 job、再次檢查 HW 的失敗；不能等的程式碼遠離壓縮記憶體。

判定：**一致**。Key point 的五句話一對一對應六張卡（cache 與 TLB 合為一句）。小差異：

- Key point 說「hands each frame to one job」，卡片 6 說 frame 與 chunk 都要；Key point 漏了 chunk。
- Key point 說「code that must not wait stays away」，卡片 4 的規則還包括「把 page 釘在 frame 裡」。釘住也等於讓 page 不被壓縮，所以算一致，只是說法不同。

### 6. 困惑指數

**2**。六張卡格式一致、每張都有 Risk、Rule、who，好讀。扣分在卡片 5 的判定細節與副標題「breaks data」不完全涵蓋六張。

### 7. 可疑的錯字或多餘文字

- 沒有看到錯字。
- 副標題「skipping one breaks data in ways tests rarely show」對卡片 3、4 不準確（見上）。
- 「Each of these was found or confirmed in the simulations」：卡片 4（hard real-time thread 碰到壓縮 page）是否真的在模擬裡出現，畫面上無從驗證；這句話是宣稱，不是圖上可看到的內容。不算錯，提出來讓作者確認。

### 第 12 張另外的問題

- **LZ4 HW 檢查什麼**：從畫面能讀到的只有一件：解壓縮時它會判斷串流是不是壞的（所以才會「報成 broken」）。這是對資料格式的檢查。
- **LZ4 HW 不檢查什麼**：
  - 讀寫的位址（Key point 第一句）。
  - 兩個 engine 是否寫同一個 frame 或 chunk（卡片 6「the HW does not check」）。
  - CPU cache 與 DRAM 是否一致（卡片 1，由 kernel 處理）。
  - 自己的判斷對不對（卡片 5，由 kernel decoder 複查）。
- **Key point 與六張卡片有沒有互相矛盾**：沒有矛盾。只有兩處不完全對齊：Key point 漏了 chunk；Key point 的「double-checks the HW's failures」只涵蓋 HW 報失敗的情況，HW 報成功但結果錯的情況卡片與 Key point 都沒提，兩者一致地沒提，不算矛盾。

---

## 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論是否一致 |
|---|---|---|---|
| 09 Keeping faults short | 2 | 清楚 | 一致 |
| 12 Where it goes wrong | 2 | 清楚 | 一致（Key point 漏了 chunk，屬小差異） |

## 我自己的話講的結論

- 第 9 張：我們讓 fault 只做解壓縮，壓縮全交給背景的 reclaimer，靠 watermark 留一批 free frame。模擬顯示一般負載與 4 倍負載都沒有 fault 等 frame，10 倍以上開始等、而且快速變多。要不要像一般 kernel 一樣加 direct reclaim 來壓住最壞情況，還沒決定；另外有兩個旋鈕可以調。
- 第 12 張：LZ4 HW 是個不設防的工人，不看位址、不管衝突，只會說「這串解不開」。正確性全靠 kernel：搬資料前後處理 cache、重用 frame 前清所有 core 的 TLB、不馬上趕走剛拿回來的 page、frame 與 chunk 在 mm_lock 下一次只給一個 job、HW 說失敗時用自己的 decoder 再試，而不能等的程式碼根本不該碰壓縮記憶體。

## 建議重生與否

兩張都**不需要重生**：困惑指數都是 2，角色清楚，畫面與 Key point 一致。

若要小修（不必重生，可在下一輪順手處理）：

- 第 9 張：最後一欄標題改成能看出等的是什麼，例如「share of time waiting on faults」，避免和「waited for a frame」的 0 看起來矛盾；或在表下加一句說明。
- 第 12 張：副標題「breaks data」改成涵蓋卡死與時序的說法；Key point 的「each frame」補上 chunk。

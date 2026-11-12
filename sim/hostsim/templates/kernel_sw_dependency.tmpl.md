# Kernel SW 的動作拆解與相依圖，第 0 版

> 這份文件由 `python3 sim/run_host.py gen-deps` 產生。表格與圖來自 `sim/hostsim/deps.py`，需要執行才有的數字存在 `kernel-sw-dependency-v0.json`。
> 第 0 節的結論、第 6 到 8 節的建議是對這一版數字手寫的。重跑之後數字有變的話，這幾處要重讀一次。
> 所有以 ns 表示的步驟成本都是假設，不是晶片的量測。它們只用來比較輕重，不能當作規格。
> 這份文件只有分析與提案。`kernel.py` 沒有為了效能做任何修改。

## 0. 結論

問題是：所有動作都要 kernel 控制，而且一次只做一件事，kernel 會不會卡住系統。把 kernel 的動作拆成 {{n_steps}} 個步驟、{{n_cases}} 個動作之後，答案分成五點。

1. **「一次只做一件事」只對了一部分。** kernel 不是一個單獨的 thread。每個發生 page fault 的 thread 在自己的 core 上跑 fault 的程序，LZ4 job 進行期間它不握 lock。真正一次只能一個的有四樣：`mm_lock` 保護的區段、LZ4 引擎和它的 ring、reclaimer thread、在 lock 裡面做的 clock 掃描。
2. **單一個動作的相依圖幾乎是一條鏈。** 一次 RO page 的 fault，一步接一步是 {{serial:fault_ro}} ns，圖上最長的路徑是 {{span:fault_ro}} ns。趕出一個 RW page 是 {{serial:evict_rw}} ns 對 {{span:evict_rw}} ns。所以在一個動作裡面把步驟排成平行，最多省幾百 ns。
3. **時間花在少數幾個重的步驟上。** 一次 RO fault 的 {{fault_ro_serial}} ns 裡，等 interrupt 和叫醒 thread 佔 {{notify_ns}} ns，約 {{notify_share}}。LZ4 HW 的 DECOMPRESS 佔 {{hw_dec}} ns，約 {{hw_dec_share}}。CPU 進出 exception 佔 {{exc_ns}} ns，約 {{exc_share}}。kernel 自己查表改表的部分加起來不到 700 ns。要快，是把重的步驟縮短，不是把步驟並排。
4. **塞車的位置在動作和動作之間。** 不同 page 的兩個動作之間沒有先後關係，它們只在共用的東西上相遇。在基準負載下，`mm_lock` 有 {{lock_share}} 的時間有人握著，LZ4 引擎忙 {{engine_share}}，reclaimer 忙 {{reclaimer_share}}。負載加重時先撐不住的順序是 reclaimer、LZ4 引擎、`mm_lock`。
5. **有兩處會讓個別的 fault 等很久，平均值看不出來。** reclaimer 握一次 lock 最多連續趕出 {{full_victims_max}} 個 page。clock 掃描最長的一次看了 {{full_scan_max}} 個 frame，全程握著 lock。這兩件事在控制程序文件裡是 F6 和 D3，這裡補上了數字。

建議的順序如下，理由在第 6 節和第 7 節。

| 順序 | 做法 | 屬於 | 解決什麼 | 證據 |
|---|---|---|---|---|
| 1 | 每握一次 lock 只趕出一個 page，而且掃描的 frame 數有上限 | kernel SW | 個別 fault 等 lock 的最長時間 | 5.3 的握 lock 統計 |
| 2 | reclaimer 同時送出 2 個 COMPRESS | kernel SW | 負載重時等不到 free frame | 6.1 的掃描 |
| 3 | fault 的 DECOMPRESS 不排在 COMPRESS 後面 | LZ4 HW 介面 | fault 被一個 COMPRESS 擋住約 4 µs | 5.4 的圖，時間模型的 F4 |
| 4 | TLB invalidate 和填 0 移到 lock 外面 | kernel SW | 握 lock 的總時間 | 6.3 的試算，尚未執行驗證 |
| 5 | fault 的 thread 用 polling 等 completion | kernel SW | 一次 fault 少約 3 µs，代價是 CPU | 6.2，取決於用哪顆 CPU |
| 6 | LZ4 HW 的 master port 接成 coherent | 整合 | 每個 job 少兩次 cache 操作 | 成本未知，見第 8 節 |

不建議現在做的：把 `mm_lock` 拆成幾個 lock、讓硬體管 chunk 或 COT、讓硬體選要趕出的 page、用硬體填 0。理由在 6.4 和 7.2。

## 1. 這些圖是怎麼來的

### 1.1 做法

1. 每個步驟只宣告一次：誰做、讀什麼、寫什麼、成本取自哪個參數。全部在 `sim/hostsim/deps.py` 的 `STEPS`。
2. 每個動作是一串步驟，順序就是 `kernel.py` 執行的順序，中間標出 lock 與 unlock。
3. 先後關係不是手畫的。兩個步驟碰到同一樣東西，而且至少一方是寫，後面那一步就必須排在前面那一步之後。
4. 有些先後關係從讀寫看不出來，例如 LZ4 HW 什麼時候會去讀 frame。這些另外列成 {{n_rules}} 條規則，每一條寫明理由，其中 {{n_witness}} 條有 mutant 見證：把那一步拿掉，並行測試會抓到。
5. 一條先後關係如果可以由其他關係推得，圖上就不畫。

步驟宣告裡沒有索引的名字，例如 `f`、`e`、`cpl`，是只有正在跑的那個 thread 自己有的值。有索引的名字，例如 `state[h]`、`cot[h]`，是 kernel 的表。`[*]` 代表整張表。

### 1.2 和執行對過的部分

宣告有可能寫錯，所以做了四種核對，全部在 `sim/tests/test_hostsim_deps.py` 裡，每次跑測試都會重做。

**步驟順序。** 由宣告推出每個動作應該留下的 step log，和真實執行留下的 log 逐筆比對。

{{occurrences}}

**讀寫。** 在三次執行中，記錄 `kernel.py` 每一行對 kernel 的表與對外呼叫的每一次讀寫，共 {{trace_accesses}} 次，再和宣告比對。{{n_groups}} 組步驟中，執行有而宣告沒有的 {{n_undeclared}} 項，宣告有而執行沒出現的 {{n_unseen}} 項，不屬於任何步驟的 {{n_stray}} 項。宣告為罕見、這三次執行也確實沒遇到的：{{rare}}。

{{trace_runs}}

**規則的方向。** 每條規則的先後和程式碼的順序一致，否則產生器會直接報錯。

**時間的算術。** 單獨跑一個動作時，把各步驟排上時間軸得到的結束時間，等於各步驟成本的總和。

### 1.3 沒有對過的部分

- thread 自己的區域值是讀程式碼宣告的，追蹤工具看不到它們。
- 對外呼叫各自碰了什麼，例如 `pte_unmap` 會寫 PTE 和 TLB，也是宣告。
- 步驟成本全部是假設。下表列出用到的成本。只有 LZ4 HW 的兩個時間來自時間模型的執行結果，而那個模型的 HW 速度本身也是假設。

{{weights}}

沒有成本的步驟有兩種。只是幾道指令的，成本記 0。模型根本沒有數字的，表裡寫「？」，圖上寫 `? ns`：兩個 cache 操作和 kernel 自己的 LZ4 decoder 屬於這一種。

## 2. 每個動作的步驟與相依圖

### 2.1 總表

{{summary}}

「差」是把所有可以並排的步驟都並排之後，理論上最多能省的時間。它假設有無限多個 CPU 同時做同一個動作，實際上做不到，所以是上限。

### 2.2 圖怎麼讀

- 每一欄是一個執行者：CPU、握著 `mm_lock` 的 kernel、沒握 lock 的 kernel、LZ4 HW。
- 由上往下是時間。同一列的步驟彼此沒有先後關係。
- 實線是資料上的先後：下面那一步要用上面那一步產生的東西。虛線是規則上的先後。
- 粗線是最長的路徑，它決定這個動作最快能多快。粗框的步驟在這條路徑上。
- 橘色的框是一段 critical section。
- 步驟右下角是假設的成本。

### 2.3 四個主要的動作

{{case:first_touch}}

{{case:fault_rw}}

RO page 的 fault 少了兩步：清 COT entry、還 chunk。它的圖在附錄 A。

{{case:evict_ro}}

{{case:evict_rw}}

## 3. 一個動作裡面，能並排的有多少

### 3.1 時間花在哪裡

![Where the time of one operation goes]({{fig}}timeline.svg)

{{timeline}}

這張表是上圖的數字版。兩個 cache 操作的成本未知，沒有算進去，圖上用三角形標出它們發生的位置。

### 3.2 讀法

1. **不在最長路徑上的步驟都很小。** 2.3 的每張步驟表最後一欄寫著每一步可以晚多少。fault 的程序裡，能和別的步驟並排的只有改 state、清 COT entry 這類 100 到 250 ns 的步驟。趕出 RW page 的程序裡，保留 chunk、查 frame、改 state 可以和改 PTE、TLB invalidate 並排，合計約 500 ns。
2. **這些並排在一個 thread 上沒有意義。** 一個 thread 本來就是一步接一步做。要真的並排，得把一個動作拆給兩個 core，光是叫醒另一個 core 就要 2000 ns 左右，比省下的還多。
3. **LZ4 HW 工作的那段時間，kernel 沒有可以先做的事。** job 結束後要做的每一步都要先看到 completion：清 COT entry 要等 page 確定回來，還 chunk 要等 COT entry 清掉，把 PTE 改成 valid 要等 cache 處理完。圖上唯一和 HW job 無關的步驟是「要不要叫醒 reclaimer」，它幾乎不花時間。
4. **HW 工作時 core 並沒有閒著。** 用 interrupt 等的時候，這個 thread 睡著，core 去跑別的 thread。這已經是平行，只是發生在動作和動作之間，不在一個動作裡面。

所以單一個動作的結構沒有平行化的空間。該看的是兩件事：重的步驟能不能變短，以及很多個動作同時發生時在哪裡互相擋住。第 5 節到第 7 節談這兩件事。

## 4. 動作和動作之間

### 4.1 兩個動作會在哪裡相遇

兩個動作如果處理的是不同的 page，它們各自的 page、frame、chunk 都不同，沒有任何先後關係。它們只在全系統只有一份的東西上相遇。下表由步驟的讀寫宣告算出。

{{pairs}}

### 4.2 共用的東西，誰讀誰寫

{{shared}}

### 4.3 `mm_lock` 實際上保護了什麼

下表是 1.2 那三次執行的紀錄：每一樣東西被碰到時，當時有沒有握著 lock。

{{lock_table}}

讀法有三點。

1. 所有 kernel 的表都只在握著 lock 時被碰。目前只有一個 lock，它保護全部。
2. `tag`、job ring、completion ring、chunk 的內容從不靠 `mm_lock`。chunk 在 job 期間只屬於那個 job。取 tag 和寫 job ring 在 host simulation 裡是不可分割的一步；介面規格用另一個 `ring_lock` 保護這一步。時間模型的基準執行中，`ring_lock` 被拿了 {{ring_grants}} 次，其中要等的 {{ring_waited}} 次，有人握著的時間佔 {{ring_busy}}。它不是塞車的地方。
3. frame 的內容和它的 cache 兩種都有。握著 lock 的那些全部來自 `first_touch` 的填 0。這是把填 0 移到 lock 外面的依據，見 6.3。

### 4.4 哪些步驟一定要在同一段裡

lock 可以縮短，但下面每一組步驟必須留在同一段 critical section 裡，否則並行測試會抓到錯誤。這張表是之後動 lock 時的底線。

{{atomic}}

第三組和第四組把 TLB invalidate 列在裡面，是因為現在的程式這樣寫，而且並行測試的檢查規定任何 core 都不能使用 kernel 已經拿走的 translation。這條檢查比實際需要的嚴，6.3 會回來談。

## 5. 哪裡真的是一次一件

### 5.1 每個動作佔用多少

{{demand}}

握 lock 的時間有 {{lock_evict_share}} 花在趕 page 出去，{{lock_first_share}} 花在第一次碰 page 時的填 0。解壓縮的 fault 本身握 lock 的時間很短。

### 5.2 基準負載下各自多忙

基準是時間模型的那次執行：4 個 core，每秒 {{faults_per_s}} 次 fault。把各動作的次數乘上 5.1 的佔用時間，除以總時間，就是忙碌比例。

{{capacity}}

`mm_lock` 和 LZ4 引擎兩列，由步驟成本算出的數字和時間模型直接量到的數字相符，表示這份拆解沒有漏掉握 lock 或佔引擎的步驟。「還能撐幾倍」只是照比例放大，沒有考慮排隊，真實的極限會更早到。

負載加重時實際發生的事，時間模型掃過一次，用的是小機器：

{{load}}

負載到 40 倍時，LZ4 引擎忙 {{worst_engine}}，`mm_lock` 忙 {{worst_lock}}，都還沒滿。但一次 RO fault 平均要等 {{worst_frame}} ns 才拿得到 free frame。先撐不住的是 reclaimer：它一次只送一個 COMPRESS，等它做完才處理下一個 page。這和時間模型文件的 F5 是同一件事，這裡從拆解的角度再看到一次。

### 5.3 一次握 lock 握多久

上面都是平均。個別的 fault 會不會等很久，要看一次握 lock 最長多久。下表來自 host simulation，統計每一次從 lock 到 unlock 之間做了什麼。

{{holds}}

1. **fault 路徑握 lock 很短，而且有上限。** 最長 600 ns，就是第一次碰 page 時的填 0。
2. **reclaimer 握 lock 沒有上限。** `kernel.py` 的 `reclaim` 握著 lock 一路做到 free frame 夠了為止。RO page 不需要 LZ4 job，所以連續幾個 RO page 會在同一次握 lock 裡被趕出去。大機器上最多一次 {{full_victims_max}} 個 page，照假設的成本是 {{full_hold_max}} ns。
3. **clock 掃描的長度沒有算進上面的時間。** 模型把選一個 page 記成固定的 {{pick_ns}} ns。大機器上共選了 {{full_picks}} 次，共看了 {{full_steps}} 個 frame，平均每次 {{full_scan_mean}} 個。但最長的一次看了 {{full_scan_max}} 個，也就是整整一圈再多一格。那是第 {{full_scan_at}} 次選 page：開機後每個 page 的 accessed bit 都是 1，要先整圈清過才選得出來。除了那一次，最長的是 {{full_scan_rest}} 個。小機器也一樣：第 {{small_scan_at}} 次看了 {{small_scan_max}} 個，其餘最長 {{small_scan_rest}} 個。每看一個 frame 要多久沒有數字。如果是 2 ns，那一次是 {{scan_2}} µs。如果是 10 ns，是 {{scan_10}} µs。這段時間所有的 fault 都進不了 lock。
4. 時間模型的 reclaimer 每趕出一個 page 就放一次 lock，host simulation 沒有。兩個模型在這一點不一致，要以控制程序為準訂下來，見第 8 節。

### 5.4 三件事同時發生的例子

![Two page faults and one eviction at the same time]({{fig}}three-at-once.svg)

{{together}}

這是刻意安排的例子：reclaimer 剛送出一個 COMPRESS，兩個 fault 緊接著進來。它是步驟成本的算術，不是時間模型的執行結果。

兩個 fault 幾乎沒有等 lock，卻都等了 LZ4 引擎 4 到 5 µs，因為引擎一次只做一個 job，而 COMPRESS 排在前面。RO fault 從 {{serial:fault_ro}} ns 變成 {{tog_ro}} ns。在基準負載下引擎只忙 {{engine_share}}，所以這種情形不常見，但它決定最慢的那些 fault 有多慢。時間模型量到最慢的 fault 也是這個原因，見時間模型文件的 F4。

## 6. Kernel SW 可以怎麼改

每一項都標明證據來自哪裡。沒有執行過的會明說。

### 6.1 reclaimer 同時送出不只一個 COMPRESS

時間模型已經有這個選項，掃過一次，負載是基準的 10 倍：

{{inflight}}

2 個最好。再多的話，fault 的 DECOMPRESS 要排在更多 COMPRESS 後面，在 ring 裡排隊的時間變長，p99 反而變差。

從相依圖看，這個改法不違反任何先後關係。兩個 `evict_rw` 處理不同的 page，4.1 的表列出它們共用的東西，全部只在握 lock 時碰到，而且每個 job 有自己的 tag 與自己的 chunk。要做的是把 reclaimer 改成：握 lock 選兩個 page 並送出，放 lock，等任一個完成，再握 lock 收尾。

`kernel.py` 目前一次一個。改了之後 20 個 mutant 要全部重跑，另外要加一個 mutant：兩個 job 的 completion 對調。

### 6.2 fault 的 thread 怎麼等 completion

{{parts}}

用 polling 等，RO fault 的 p50 從 {{irq_p50}} ns 降到 {{poll_p50}} ns，kernel 佔的 CPU 從 {{irq_kcpu}} 升到 {{poll_kcpu}}。DECOMPRESS 只要約 {{hw_dec}} ns，比叫醒一個 thread 還短，所以 fault 路徑用 polling 是合理的。reclaimer 等的是 COMPRESS，不急，繼續用 interrupt。

這一項取決於實際的 CPU 與 kernel 或 RTOS：interrupt 延遲與叫醒時間是模型裡最大的假設，而 polling 期間這個 core 不能做別的事。

### 6.3 把步驟移到 lock 外面

由 5.1 的數字試算，只算握 lock 的時間：

{{what_if}}

**填 0。** 第一次碰 page 時，填 0 佔握 lock 時間的三分之二。4.3 的紀錄顯示它是唯一在 lock 裡碰 frame 內容的步驟。移出去的做法和解壓縮一樣：握 lock 時把 page 標成進行中，放 lock，填 0，再握 lock 把 state 改成 PRESENT、PTE 改成 valid、叫醒等的 thread。代價是多握一次 lock，以及多一個狀態要驗證。

**趕出 RW page 時的 TLB invalidate。** 相依圖上，TLB invalidate 之後只有一條規則：它要在 cache clean 之前完成，因為 clean 之後不能再有 core 寫這個 frame。cache clean 本來就在 lock 外面。所以 TLB invalidate 可以放在 unlock 之後、cache clean 之前。這段期間 page 的 state 是 COMPRESSING，會 fault 的 thread 都在等，還留著舊 translation 的 core 讀寫的仍然是這個 page 自己的 frame。

**趕出 RO page 時的 TLB invalidate。** 這個不能直接移。frame 一還回 free list 就可能被別的 page 拿走，舊的 translation 會碰到別人的資料。要移的話，frame 必須等 TLB invalidate 做完才還回去。

這三項都是由圖推理，還沒有執行驗證。並行測試現在的檢查是「任何 core 都不能使用已經被拿走的 translation」，照這條規則，後兩項一定會被判錯。要驗證就得先把規則改寫成真正的需求：frame 換主人之前、以及 cache clean 之前，所有 core 的舊 translation 都要清掉。

TLB invalidate 的實際成本要看 CPU。模型假設 {{tlb_ns}} ns。如果 CPU 沒有能一次通知所有 core 的指令，就得逐一中斷其他 core，成本會高一個數量級，這一項的價值也跟著變大。

### 6.4 現在不建議的

| 做法 | 為什麼現在不做 |
|---|---|
| 把 `mm_lock` 依資源拆成幾個 lock | 基準負載下 lock 只忙 {{lock_share}}，照比例放大到 10 倍也還有餘。4.4 的每一組步驟都跨了不只一類資源，例如讀 state、拿 frame、改 state 要一氣呵成。拆開之後 20 個 mutant 與等待和叫醒的不可分割性都要重新證明 |
| 增加 reclaimer thread | LZ4 引擎只有一個。多個 reclaimer 只是在 ring 前面排隊，效果等同 6.1，卻多了 reclaimer 之間的競爭 |
| 發生 fault 的 thread 自己趕 page 出去 | fault 的延遲會多出一整個 COMPRESS。只在 reclaimer 完全跟不上時才有意義，而那時該先做 6.1 |

## 7. 硬體可以幫什麼

判斷的準則是先前定下的：複雜而容易出錯的部分留在軟體，硬體對每個 job 不保留狀態，只做協助。

### 7.1 值得評估的

| 編號 | 做法 | 省下什麼 | 證據 | 硬體是否仍然對每個 job 不保留狀態 |
|---|---|---|---|---|
| H1a | 排隊的 job 裡，DECOMPRESS 先做。第二個 ring，或 descriptor 帶優先權 | fault 最多只等正在做的那一個 COMPRESS 做完，不再等排在前面的。6.1 因此可以開到 2 個以上 | 6.1 的掃描：同時送 8 個時 fault 在 ring 裡平均排 5 304 ns。這個做法本身還沒有在時間模型裡跑過 | 是。只改取 job 的順序。介面規格的 O4 就是這一項 |
| H1b | DECOMPRESS 有自己的 datapath，可以和 COMPRESS 同時進行 | fault 完全不等 COMPRESS，最慢的 fault 少約 {{hw_comp}} ns | 5.4 的例子，時間模型的 F4 | 是。但硬體要多一份 datapath，見下文 |
| H2 | LZ4 HW 的 master port 和 CPU cache 接成 coherent | 每個 job 少一次 cache clean 或 cache invalidate，一個 page 是 64 條 cache line。程序也少兩條容易做錯的規則 | 成本未知，模型裡是「？」。兩個步驟都在最長路徑上 | 是。這是整合方式，不是 LZ4 HW 內部的功能。控制程序的 D8 |
| H3 | 第二個 COMPRESS 的 datapath | LZ4 引擎的容量加倍 | 基準負載下引擎只忙 {{engine_share}}，40 倍負載時 {{worst_engine}}。在那之前 reclaimer 先撐不住 | 是。但只有在做完 6.1 之後引擎成為瓶頸時才值得 |

H1a 和 H1b 差在硬體的代價。硬體設計規格第 0 版的第 5 節裡，encoder 和 decoder 是分開的 block，但 page buffer、兩個 FIFO、CRC-32、packer、讀寫 DRAM 的兩個 block 和 job FSM 只有一份，一次只能服務一個 job。H1b 要把這些再做一份，只有 encoder 和 hash table 不用。照那份規格 5.4 的表，page buffer 加兩個 FIFO 是 49 152 bit，約佔全部記憶體 62 656 bit 的八成。H1a 只動取 job 的邏輯，但正在做的那個 COMPRESS 還是擋得住 fault，最多 {{hw_comp}} ns 左右。

建議先在時間模型裡加上 H1a 跑一次，看 p99 剩多少，再決定要不要 H1b。

### 7.2 評估過、不建議的

| 做法 | 為什麼不做 |
|---|---|
| 硬體填 0 | CPU 填一個 page 假設是 {{zero_ns}} ns。交給硬體要送 job、等 completion，光通知就超過這個數字 |
| 硬體管 chunk 的 bitmap 或自己讀寫 COT | 這些步驟各只有 100 到 250 ns，而且是最容易出錯、最需要 mutant 驗證的部分。交給硬體等於讓硬體持有跨 job 的狀態，違反準則 |
| 硬體選要趕出的 page | 掃描要讀 PTE 的 accessed bit、page 的 state、pin 與 fresh 名單，全是 kernel 的表。5.3 的問題用軟體設上限就能解決 |
| 硬體收到 page 編號後自己查 COT | 省下讀 COT 與組 descriptor 共約 250 ns，卻讓硬體依賴 COT 的格式與位置 |
| completion 專用的喚醒訊號 | 6.2 的 polling 不需要新硬體就拿到大部分的好處 |

TLB invalidate 能不能一道指令通知所有 core，是 CPU 的特性，不是 LZ4 HW 能幫的。

## 8. 還缺的數字，和要請你決定的事

### 8.1 還缺的數字

| 缺什麼 | 影響哪個判斷 | 怎麼取得 |
|---|---|---|
| cache clean 與 cache invalidate 一個 page 要多久 | H2 值不值得 | 選定 CPU 後查手冊或實測 |
| TLB invalidate 通知所有 core 要多久 | 6.3 的後兩項值不值得 | 同上 |
| clock 掃描每看一個 frame 要多久 | 5.3 的第 3 點有多嚴重，上限該設多少 | 實作後量，或用 cache miss 的成本估 |
| interrupt 延遲與叫醒 thread 的時間 | 6.2，以及一次 fault 的一半時間 | 取決於 kernel 或 RTOS |
| kernel 自己的 LZ4 decoder 解一個 page 要多久 | LZ4 HW 停用後的延遲 | 在目標 CPU 上跑 |
| 真實負載每秒幾次 fault、RO 與 RW 的比例 | 第 5 節全部。基準是合成負載 | 真實的 access 紀錄 |

### 8.2 要請你決定的事

| 編號 | 問題 | 我的建議 |
|---|---|---|
| K1 | 用哪顆 CPU、哪個 kernel 或 RTOS | 這決定 TLB、interrupt、polling 三件事的成本，先定下來，其餘的才算得準 |
| K2 | 目標是平均延遲，還是最慢的那些 fault | 建議以最慢的為準。平均已經由通知時間決定，結構上的問題都出在尾端 |
| K3 | 是否開始為效能修改 `kernel.py` | 建議先做順序 1 和順序 2。兩者都要加 mutant 並重跑全部並行測試。在你同意之前程式不動 |
| K4 | reclaimer 每趕出一個 page 要不要放一次 lock | 建議要，並採用控制程序 D3 的選項 B：掃描有上限。這也讓兩個模型一致 |
| K5 | H1 要不要列入 LZ4 HW 的設計規格 | 建議把 H1a 列為需求，這會把介面規格的 O4 定案。H1b 等時間模型跑過 H1a 再決定 |

## 附錄 A. 其餘四個動作

{{appendix}}

## 附錄 B. 步驟總表

{{glossary}}

## 附錄 C. 全部的先後規則

{{rules}}

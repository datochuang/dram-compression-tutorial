# lz4sim：LZ4 DRAM compression 系統模擬器

用來探索整套設計、比較兩個軟硬體分工版本，並產生系統行為的 trace 給後續的硬體驗證環境。
它同時是兩份最終文件的可執行參考：

| 最終產出 | 對應的程式 |
|---|---|
| LZ4 硬體加速器設計規格 | `lz4sim/engine.py`（兩個版本共用的 LZ4 engine）、`lz4sim/accel.py`（兩個版本各自的外層）、`lz4sim/formats.py`（descriptor、completion、COT entry、list chunk 的位元配置）、`lz4sim/alloc_stack.py`（基準版的 free-chunk stack） |
| LZ4 控制 kernel 的設計規格與 pseudo code | `lz4sim/kernel.py`（page 狀態機、reclaim、fault 路徑）、`lz4sim/alloc_bitmap.py`（軟體版的 chunk bitmap） |

程式刻意寫成可以直接讀成 pseudo code：每個 kernel 步驟就是一個方法，每個硬體動作就是 `_run()` 裡的一段，trace 裡的每個事件都標明是 kernel 還是 hw 做的。

## 安裝與執行

```
pip install -r sim/requirements.txt        # lz4（官方 liblz4 的綁定）、pytest
cd sim && python3 -m pytest                 # 29 個測試，約 2 秒
python3 sim/run.py --help
python3 sim/run.py --variant both --accesses 200000 --trace out/trace.jsonl --json out/stats.json
python3 sim/run.py --small --variant software --accesses 5000   # 1/64 大小的機器，秒級
```

三種跑法用同一支程式，只差 `--variant`：

| 要跑的方案 | 命令 |
|---|---|
| 偏硬體方案（baseline） | `python3 sim/run.py --variant baseline ...` |
| 偏軟體方案（software） | `python3 sim/run.py --variant software ...` |
| 兩個一起，並排比較（預設） | `python3 sim/run.py --variant both ...` |

`--variant both` 用同一個 seed 跑兩個版本：同一份 RO image、同一條存取序列，差別只在誰持有狀態、誰寫表、trace 裡出現什麼。全尺寸（512 MiB 機器、148,480 個 page）跑 200,000 次 page touch 約 6 秒。

常用參數：

| 參數 | 意思 |
|---|---|
| `--hot-ro N` / `--hot-rw N` | hot set 的 page 數，預設 7,680（30 MiB）與 20,480（80 MiB） |
| `--p-hot` | 落在 hot set 的機率，預設 0.9；其餘均勻分布在整個可壓縮範圍 |
| `--write-frac` | RW page 被寫的比例，預設 0.3；heap page 第一次碰到一定是寫（程式初始化它） |
| `--clients NAME:SHARE,...` | 擁有 page 的 user SW 與各自的份額，預設 `UI:40,MEDIA:27,NET:20,LOG:13`，最多 8 個；名字只是例子 |
| `--phase-len N --phase-frac f` | 每 N 次存取換掉 hot set 的 f，用來做 phase change |
| `--ro-ratio --ro-sd --rw-ratio --rw-sd` | 頁面壓縮比的常態分布，預設 0.55±0.18 與 0.45±0.20 |
| `--raw-store` | 壓不動的 RW page 以 RAW 存 8 個 chunk，而不是留在 frame 裡 |
| `--limit` | COMPRESS 放棄門檻，預設 3584 |
| `--fc-low --fc-high` | frame cache 的 reclaim 水位，預設 512 / 1024 個 frame |
| `--pool-mib --fc-mib` | 改 pool 與 frame cache 的大小 |
| `--corrupt-every N` | 每 N 次存取在一個壓縮物件裡翻一個 byte，測 BAD_STREAM 路徑 |
| `--sample-every N --timeline x.csv` | 每 N 次存取抽樣 frame、pool、fault 數，輸出 CSV |
| `--dump DIR` | 結束時把 COT 與 pool 的記憶體映像寫成 cot.bin、pool.bin |
| `--trace-level all` | 除了工作與狀態，也記每次 access、PTE 變化、kernel 讀表 |

## 模擬的機器

幾何與 `docs/lz4-verify/plan512.py` 相同，`lz4sim/config.py` 裡的 `SystemConfig` 是唯一來源：

| 區域 | 大小 | PA |
|---|---|---|
| Pinned（image 34 + run time 22） | 56 MiB | 0x8000_0000 |
| HRT carve-out | 36 MiB | 0x8380_0000 |
| COT，148,480 entries × 32 B | 5 MiB | 0x85C0_0000 |
| Chunk pool，563,200 × 512 B | 275 MiB | 0x8610_0000 |
| Frame cache，35,840 × 4 KiB | 140 MiB | 0x9740_0000 |

可壓縮範圍 580 MiB：handle 0 到 0x14BFF 是 RW（.data 26 MiB 開機就在 frame 裡，heap 306 MiB 一開始是 untouched），0x14C00 起是 RO。

### 兩個方案共用的部分

偏硬體與偏軟體是同一個模擬器的兩種組裝方式，不是兩份程式。共用的部分各只有一份：

| 共用的東西 | 檔案 | 內容 |
|---|---|---|
| LZ4 engine（LZ4 HW 的 datapath） | `lz4sim/engine.py` | 讀 frame 並壓縮、判斷 raw 或 incompressible、把 stream 散寫到 chunk、從 chunk 收回、CRC-32 檢查、解壓並寫回 frame、streaming 時間 |
| Job 外框 | `lz4sim/accel.py` 的 `AccelBase` | 收 descriptor、執行、寫 completion、計數與計時 |
| 格式與狀態碼 | `lz4sim/formats.py` | COT entry、completion、opcode、status |
| Kernel 的共同流程 | `lz4sim/kernel.py` 的 `KernelBase` | page 狀態機、frame cache、LRU reclaim、fault 路徑、資料驗證 |
| 其餘 | `codec.py`、`dram.py`、`workload.py`、`trace.py`、`sim.py`、`replay.py` 與 viewer | LZ4 codec、DRAM、workload、trace、audit 與報表、3D replay |

各自獨有的只有「誰持有 metadata」那一層：

| | 偏硬體方案 | 偏軟體方案 |
|---|---|---|
| 加速器外層 | `BaselineAccel`：CTLB、讀寫 COT、INVALIDATE、INIT | `SoftwareAccel`：descriptor 的範圍檢查 |
| 空 chunk 配置器 | `alloc_stack.py`（硬體） | `alloc_bitmap.py`（kernel） |
| Kernel 外層 | `BaselineKernel` | `SoftwareKernel`：reserve、寫 entry、trim、release |

`Lz4Engine` 不看 descriptor、COT、stack 或 bitmap，chunk 號碼、stream 長度與 checksum 都由外層給它。所以改 datapath 只改 `engine.py` 一處，兩個方案同時生效。`tests/test_engine.py` 會檢查兩個加速器拿到的是同一個 class，而且外層沒有自己的 datapath 副本。

兩個版本：

| | baseline（偏硬體） | software（偏軟體） |
|---|---|---|
| COT entry 誰寫 | RO 由 build tool，RW 由硬體在 COMPRESS 結尾寫 | 全部 kernel 寫 |
| 空 chunk 誰管 | 硬體的 free-chunk stack：SRAM 512 個，其餘串成 list chunk（next 3 B + 169 個號碼），低於 64 refill、高於 448 spill | kernel 的 bitmap，563,200 bits = 68.75 KiB，開機從 COT 建；word-at-a-time 加 ctz，next-fit cursor |
| descriptor | 16 B：opcode、handle、frame_pa、limit、tag | 48 B：opcode、frame_pa、chunk[0..7] + count、limit、comp_len、flags、checksum、tag |
| opcode | COMPRESS、DECOMPRESS、INVALIDATE、INIT | COMPRESS、DECOMPRESS |
| 硬體狀態 | stack top、LIST_HEAD、1 個 entry 的 CTLB | 工作之間沒有 |
| 狀態碼 | OK、INCOMPRESSIBLE、POOL_FULL、BAD_STREAM、BAD_HANDLE | OK、INCOMPRESSIBLE、BAD_STREAM、BAD_DESC |

Page 狀態：`compressed`、`present`、`untouched`（RW）、`compressing`、`decompressing`、`lost`。RO 只有 frame 來去，RW 整個物件來去；兩個版本的狀態機與 reclaim 政策完全相同（LRU，RO 直接丟 frame，RW 走 COMPRESS，pool 滿時只挑 RO）。

## User SW：page 的主人

壓縮層服務的對象是 user SW。模擬器裡每個 page 屬於一個 user program：`.data`、heap、RO 三段各自依份額切給每個 client，所以每個 client 都有 RW 與 RO 的 page。預設四個，份額刻意不平均：

| client | 份額 | SMALL 機器的 page 數 |
|---|---|---|
| UI | 40 | 717 |
| MEDIA | 27 | 484 |
| NET | 20 | 358 |
| LOG | 13 | 233 |

- 名字是例子，不是教材裡的角色；用 `--clients` 換成自己的。
- **擁有者只是標籤。** 存取序列仍由同一個 hot set 模型產生，加上或換掉 client 不會改變任何 fault、job 或 chunk 的結果；`tests/test_clients.py` 會比對整條 trace。要讓不同 client 有不同的存取行為，是之後 workload 的事。
- `access` event 多一個 `client` 欄位（client 的序號），`boot` event 與 replay 的 `meta` 帶 `clients` 清單（名字、份額、三段的 handle 範圍）。
- 報表多一組 USER SOFTWARE：每個 client 的 page 數、access 數、fault 數與平均等待時間。兩個方案在這裡可以直接比「同一個 user SW 等多久」。

## 模型假設，以及沒有模的東西

- **沒有真實 workload。** 頁面依目標壓縮比合成：r×4096 個亂數 byte 加重複的 4-byte pattern，分四段。真實資料的 match 結構不同，但壓縮比的分布可以調。要接真實映像，只要換掉 `Workload.ro_page / rw_page / fill`。
- **LZ4 用官方 liblz4。** 硬體的 match finder 找到的 match 不會一樣，所以 COMPRESS 的 oracle 是「解回原頁且不超過 limit」；DECOMPRESS 才逐 byte 比。每一次 fault 模擬器都會用頁面的 CRC 驗證還原內容。
- **時間是解析式的，沒有競爭。** 每個相依的 DRAM 存取 100 ns、解壓 4 B/cycle、壓縮 1 B/cycle、每次 fault kernel 3 µs、每次 evict 2 µs、軟體版每個工作多 300 ns；page touch 之間 20 µs。Reclaim 當成背景工作：CPU 時間算進 `kernel_bg`，不拉長 fault latency。加速器只有一個，但沒有排隊模型；這是下一步 SimPy 的事。
- **壓不動的 RW page 留在 frame 裡**（兩份投影片的設計），除非 `--raw-store`。它們會一直占 frame，報表裡的 `incompressible_pinned_end` 就是這個數。
- **BAD_STREAM 的 page 標成 lost**，物件留在 pool 裡不釋放（kernel 不信任它），audit 會把它算成 used。
- **INIT 與 bitmap 建表** 在開機時做，時間不計入報表。

## 輸出

### 報表

`format_report` 把兩個版本並排。欄位分組：BUILD（RO image 的實際 chunk 數、RAW 頁數、chunk 取整的浪費）、BOOT、RUN（hit、first touch、fault 與 fault rate）、RECLAIM（RO drop、RW compress、INCOMPRESSIBLE、POOL_FULL、OOM）、JOBS（每個 opcode 與狀態碼的次數）、POOL（用量、峰值、RW 物件平均大小與 chunk 浪費）、FRAMES、DRAM（在用量、加速器與 kernel 的 DRAM 存取）、ALLOCATOR（stack 的 pop/push/refill/spill 與 CTLB 命中；bitmap 的 reserve/release 與每次掃的 word 數）、TIME（fault latency、加速器與 CPU 占用）、AUDIT。`--json` 把同樣的數字存成 JSON。

### Trace（JSON Lines）

一行一個事件，`n` 是序號、`t` 是模擬時間（ns）、`who` 是誰做的（kernel、hw、build、sim）。等級 `jobs` 記所有硬體看得到或碰到的東西加上 page 狀態；`all` 再加每次 access、PTE 與 kernel 讀表。

| ev | 欄位 | 意思 |
|---|---|---|
| `build` / `boot` | ro_chunks、free_chunks… | 開機前後的摘要 |
| `job` | op、desc（解開的欄位）、hex（descriptor 的 bytes） | kernel 送出一個工作 |
| `done` | status、len、csum、flags、tag、lat_ns、hex | 硬體寫回 completion |
| `cot` | who、h、entry、hex | 有人寫了一筆 COT entry（基準版 RW 是 hw，軟體版是 kernel，build 是 build tool） |
| `chunk` | who、op = pop / push / reserve / trim / release、chunks、words | chunk 的配置與歸還；軟體版的 reserve 附掃了幾個 word |
| `stack` | op = init / refill / spill、list_chunk、list_head、sram | 基準版 free-chunk stack 碰 DRAM 的時刻 |
| `bitmap` | op = build、entries、used、free | 軟體版開機建表 |
| `state` | h、from、to | page 狀態轉換 |
| `frame` | op = alloc / free、h、pa | frame 的來去 |
| `access`、`pte`、`cot_read` | `access` 有 h、w、res、lat_ns、client | 只在 `--trace-level all`；`client` 是發出這次存取的 user SW |
| `inject` | h、chunk、offset | 注入的損壞 |

軟體版一次 RW eviction 在 trace 裡長這樣（handle 1，1,125 B，保留 7 個 bit、用 3 個、還 4 個）：

```
{"n":98344,"t":1432744272,"ev":"chunk","who":"kernel","op":"reserve","chunks":[313413,...,313419],"words":1}
{"n":98345,"t":1432744272,"ev":"state","h":1,"from":"present","to":"compressing"}
{"n":98346,"t":1432744272,"ev":"job","who":"kernel","op":"COMPRESS","desc":{"opcode":"COMPRESS","frame_pa":2537558016,"chunks":[313413,...,313419],"limit":3584,...,"tag":1},"hex":"0107000e0010409700000000..."}
{"n":98347,"t":1432744272,"ev":"done","who":"hw","status":"OK","len":1125,"csum":1357256878,"flags":0,"tag":1,"lat_ns":4396,"hex":"00006504ae18e6500100000000000000"}
{"n":98348,"t":1432748968,"ev":"cot","who":"kernel","h":1,"entry":{"flags":1,"count":3,"comp_len":1125,"checksum":1357256878,"chunks":[313413,313414,313415]},"hex":"01036504ae18e65045c80446c80447c804..."}
{"n":98349,"t":1432748968,"ev":"chunk","who":"kernel","op":"trim","chunks":[313416,313417,313418,313419]}
{"n":98350,"t":1432748968,"ev":"frame","who":"kernel","op":"free","h":1,"pa":2537558016}
{"n":98351,"t":1432748968,"ev":"state","h":1,"from":"compressing","to":"compressed"}
```

同一個 page 在基準版裡：descriptor 只有 handle，硬體自己 refill、pop、寫 entry：

```
{"n":98347,"t":1431045772,"ev":"job","who":"kernel","op":"COMPRESS","desc":{"opcode":"COMPRESS","handle":1,"frame_pa":2537558016,"limit":3584,"tag":1},"hex":"0100000e010000000010409701000000"}
{"n":98348,"t":1431045772,"ev":"stack","who":"hw","op":"refill","list_chunk":313413,"list_head":313583,"sram":227,"list_chunks":1468}
{"n":98349,"t":1431045772,"ev":"chunk","who":"hw","op":"pop","chunks":[313413,313582,313581]}
{"n":98350,"t":1431045772,"ev":"cot","who":"hw","h":1,"entry":{"flags":1,"count":3,"comp_len":1125,...,"chunks":[313413,313582,313581]},"hex":"01036504ae18e65045c804eec804edc804..."}
{"n":98351,"t":1431045772,"ev":"done","who":"hw","status":"OK","len":1125,"csum":1357256878,"flags":0,"tag":1,"lat_ns":4596,"hex":"00006504ae18e6500100000000000000"}
```

### Audit

每次跑完會走一遍 COT 與配置器：每個 chunk 恰好屬於一個 valid entry 或在 free set 裡（stack 版會從 LIST_HEAD 把 linked list 走完，bitmap 版列出所有 0 bit）、entry 的 count 與 comp_len 一致、present 的 page 數等於用掉的 frame 數。任何 double free、double allocation 或漏掉的 chunk 都會讓它失敗。

### 3D replay（`--replay`）

把一次模擬變成一頁可以播放的 3D 場景，用來看 user SW 碰一個 page 之後，kernel 與加速器實際上怎麼替它把 page 搬回來。

```
python3 run.py --small --accesses 3000 --replay out/replay.html
```

- **一頁、兩個方案**：`--variant both`（預設）時，兩個方案放在同一頁。左上角的 `DESIGN` 切換鈕有 `HW-leaning` 與 `SW-leaning` 兩顆，選中的一顆用該方案主角的顏色（紫色是 LZ4 HW，黃色是 KERNEL SW），下面一行字說明這個方案誰持有什麼。切換後停在同一次 access。
- **直接開在某個方案**：網址加 `?design=software` 或 `?design=hw`（也接受 `?variant=`、`#software`）；或匯出時加 `--replay-start software`，頁面一開就是偏軟體方案。只要單一方案的頁面就用 `--variant software --replay out/replay-sw.html`，檔案約一半大。
- **viewer 只有一份**：場景、所有角色、user SW 的請求與交付、kernel 向 LZ4 HW 交代工作的演出、LZ4 HW 的動作編排兩個方案共用，差別只有基準版畫 SRAM stack 的塔、軟體版畫 chunk bitmap 的帳本，以及帳本由誰去寫。
- **場景**：由記憶體這一側看過去，高的東西都不站在前景。由近而遠依序是：平躺在地上的帳本 COT（每個 entry 一格），軟體版在右邊多一本 chunk bitmap；左邊的 frame cache（每個 frame 一塊 slab）與右邊的 chunk pool（每個 chunk 一格，有斜線的方塊是壓縮資料），兩者之間的走道上有 LZ4 engine 與 job ring，kernel SW 與 LZ4 HW 在這裡工作；再過去是 `ACCESS GATE`（MMU 加 page table）；最遠端一整排是 `USER SW` 的走道。基準版在 chunk pool 近側多一根 SRAM stack 的塔。`Overview` 把機器放在畫面下方，多出來的高度留在遠端上方給 speech bubble；bubble 不會蓋住說話的角色本身，也盡量不蓋住 gate 與正在等的 user SW。
- **User SW 是被服務的一方**：每個 client 一個角色，站在最遠端的走道上，造型與顏色都不同：螢幕頭（粉紅）、戴耳機的圓身（橘）、頂著碟形天線的錐身（白）、一疊圓盤（萊姆綠）；超過四個時造型循環、顏色再換。每一個 scene 都由 user SW 開場：它往前一步說出 `read page 0x…` 或 `write page 0x…`。整段 kernel 與 LZ4 HW 的工作期間它都停在那裡等，bubble 寫著 `stopped: waiting for page 0x…`；拿到 page 之後說 `read page 0x… done, waited N.NN us`。
- **所有存取送到同一個窗口**：不管哪個 user SW，存取都送到 `ACCESS GATE`，也就是 MMU 加 page table。窗口是一座拱門，站在走道正中央，user SW 分站它的左右兩側；鏡頭拉遠時拱門跟著放大。拱門上方有一顆燈，門面的玻璃跟著變色（綠是放行、紅是擋下），並有自己的 bubble（`MMU · PAGE TABLE`）。Kernel 平常不在窗口，被叫到才走過來，服務完就離開。

  | 情況 | 窗口的反應 | kernel 要不要出面 |
  |---|---|---|
  | PTE valid（hit） | 綠燈，`PTE valid: pass to frame N`，光束由 user SW 經窗口連到 frame | 不用，`no kernel needed` |
  | PTE 不 valid，page 被壓縮（fault） | 紅燈，`PTE of 0x… is not valid`，請求單留在櫃台上 | 要。Kernel 走到窗口，說 `PAGE FAULT`、`it is compressed in the pool: unpack it` |
  | PTE 不 valid，page 沒用過（first touch） | 同上 | 要。Kernel 說 `FIRST TOUCH`、`never used: a zero-filled frame will do` |
  | 上面兩種再加上 free frame 不夠 | 同上 | Kernel 多說一句 `free frames are low: compress cold pages too` |

  Kernel 改 PTE 也在窗口做：`map PTE 0x… to frame N` 時一道黃色光束由窗口連到那個 frame，`unmap PTE` 時是紅色光束，並說明下一次存取會被擋在窗口。Page 回到 frame 之後窗口轉綠燈說 `PTE valid now: pass to frame N`，櫃台上的請求單變成綠單飛回 user SW，kernel 隨後走回自己的位置。
- **交代工作**：kernel 送 job 不再只是丟一張卡。`job` event 演成一次交接：kernel 與 LZ4 HW 都走到 job ring 面對面，一張 descriptor 從 kernel 手上飛到 LZ4 HW，kernel 的 bubble 用 descriptor 的實際欄位把事情講清楚，LZ4 HW 回 `job taken: <OP>, tag 0x…`，並把那張 descriptor 掛在肩上直到回報。兩個方案交代的內容不同，這正是兩個設計的差別：

  | job | HW-leaning 的交代 | SW-leaning 的交代 |
  |---|---|---|
  | COMPRESS | frame、page 與主人；`you pop the chunks, you write the COT`；give up over 3584 B | frame、page 與主人；`store into my 7 reserved chunks`；give up over 3584 B |
  | DECOMPRESS | page、目的 frame；`you look up its chunks in the COT` | page、目的 frame；chunk 數、長度、checksum 都寫在 descriptor 裡 |
  | INVALIDATE | `you clear its COT entry`、`you push its chunks on your stack` | 沒有這個 job，kernel 自己改 COT 與 bitmap |

  `done` event 演成回報：LZ4 HW 回到 job ring，說 `Report to KERNEL: <STATUS>` 加上結果（長度、checksum、用了幾個 chunk、COT 是不是它寫的，或失敗原因），一張綠色或紅色的 completion 飛回 kernel，kernel 說 `completion read: …`，肩上的 descriptor 消失。同一個 scene 裡同一種 job 的第二次起（reclaim 一次有 25 到 34 個 job）改用一行的短版，LZ4 HW 不再走回 job ring，免得 scene 拖太長。
- **kernel 與加速器**：全身黃色、戴黃帽的是 kernel（標示 `KERNEL SW`），紫色機器人是加速器（標示 `LZ4 HW`），腳下各有一圈同色的光環。鏡頭拉遠時角色會放大，手上搬的東西維持原尺寸。每個角色正在做的事用 speech bubble 顯示，bubble 是疊在畫面上的 DOM 元素，所以字級固定（16 px），不隨鏡頭距離縮小；沒在說話的角色只留名牌，剛說話的那一個在最上層，bubble 互相讓位；名牌不會被推離角色太遠。窄畫面（寬度小於 700 px，例如手機直立）只有最近說話的兩個角色顯示文字，其餘收成名牌。資料搬移一律由加速器演；帳本由擁有它的一方演：基準版是機器人去 COT 牆與 stack 塔，軟體版是 kernel 走去 COT 牆與 bitmap 牆。兩個版本的 HW/SW 分工差異因此直接看得到。
- **一格一步**：一次 page access 是一個 scene。Scene 裡每一個 trace event 是一步，右側清單每一步都標 KERNEL、HW 或 user SW 的名字，標題寫出是哪個 user SW 的存取，計數區有每個 user SW 的 access 數，並顯示該 event 的欄位（descriptor、completion、COT entry）與原始 bytes。
- **操作**：播放、單步（一次一個 event）、前後一次 access、跳到上一個或下一個非 hit 的 access、0.5x 到 16x、略過單純的 hit、時間軸拖曳。拖曳旋轉、滾輪或雙指縮放、shift 拖曳或雙指平移；預設是 `Overview`，自動把整台機器放進面板以外的畫面；`Follow` 跟著正在動的角色。1x 的步調是第一版的七成。
- **限制**：每個 chunk 與 frame 都是一個物件，所以只接受小機器（上限 40,000 chunks、60,000 次 access），請搭配 `--small`。完整大小的機器需要 level-of-detail 的畫法，目前沒有。頁面本身自足（trace 內嵌），只從 cdnjs 載入 three.js r128，所以要有網路。
- **正確性**：viewer 不重跑模擬，它只照 trace 重建狀態（`replay_assets/model.js`）。3,000 次 access 的兩個版本全部 event 走完後，viewer 的 fault、hit、job 數、free chunk 數與每個 user SW 的 access 數和模擬器的統計一致。
- **線上版**：<https://datochuang.github.io/dram-compression-tutorial/replay/>，檔案是 `docs/replay/index.html`。偏軟體方案的入口是 <https://datochuang.github.io/dram-compression-tutorial/replay/software/>，偏硬體方案是 <https://datochuang.github.io/dram-compression-tutorial/replay/hardware/>；這兩個是轉址頁，資料只有 `docs/replay/index.html` 一份。更新方式：`cd sim && python3 run.py --small --accesses 3000 --replay ../docs/replay/index.html`，再 commit 並 push。
- `--replay-fragment`：輸出不含 html / head / body 外殼的版本，給會自己加外殼的宿主頁面用。

### 3D lesson（`--lesson`）

Replay 是從遠處看整次模擬；lesson 相反，只看**一個 job**，貼近到每個 byte，給第一次接觸這個主題的人用。兩者是不同的頁面，只共用角色造型（`replay_assets/chars.js`）。

```
python3 run.py --small --accesses 3000 --variant baseline --lesson out/lesson-compress-hw.html
```

- **資料是真的**：匯出時重跑一次模擬，在每次 RW eviction 前後拍下 frame、COT entry、SRAM stack 與 trace，再挑一個最適合教學的 job（數字不整齊、chunk 號碼不相鄰、最後一個 chunk 沒寫滿、handle 不等於 frame 號碼、要 frame 的程式與被壓縮的 page 分屬不同 user SW）。頁面上每個 byte 都來自那個 job。預設參數挑到的是第 2997 次 access：UI 要一個 frame，LOG 的 page 0x4F5 被壓成 1938 B、4 個 chunk。
- **目前的 scene**：四個，用 `--lesson-scene` 選。`compress-hw`（預設）與 `decompress-hw` 是偏硬體方案，`compress-sw` 與 `decompress-sw` 是偏軟體方案。四課講的是同一個 page 0x4F5 的去與回：同一個 seed 下兩種方案的 access 序列相同，所以偏軟體的兩課挑到的是同一次 access（2997 與 11519）、同一份 1938 B 的 stream，可以逐步對照。`--variant` 不影響 lesson，每個 scene 自己決定用哪個方案重跑。

  `compress-hw`，COMPRESS，共 25 步：

  | 步 | 誰 | 內容 |
  |---|---|---|
  | 1 | 說明 | 舞台與角色、名詞表 |
  | 2 到 4 | user SW、kernel | UI 被擋在 access gate、kernel 挑 victim、把 PTE 改成 invalid |
  | 5 到 8 | kernel | 一次寫一組欄位，把 16 B 的 descriptor 填滿 |
  | 9 | kernel | 向 LZ4 HW 口頭交代工作，寫 DOORBELL |
  | 10 到 12 | LZ4 HW | 讀 descriptor 並檢查、讀 frame 進 engine、比對 give-up 門檻 |
  | 13 到 16 | LZ4 HW | 一步一個 chunk：從 SRAM stack pop 一個號碼，寫入一段 stream |
  | 17 到 21 | LZ4 HW | 算 checksum，再一組一組欄位寫 COT entry |
  | 22 | LZ4 HW | 寫 completion、發 IRQ |
  | 23 到 24 | kernel | 讀 completion 對 tag，釋放 frame |
  | 25 | 說明 | 前後對照，以及誰從來沒碰過什麼 |

  `decompress-hw`，PTE invalid 觸發的 DECOMPRESS，共 33 步。模擬會在 `--accesses` 之後多跑一段，直到 compress 課的那個 page 被它的主人再碰一次；預設參數是第 11519 次 access，LOG 讀 page 0x4F5，離它被壓縮隔了 8522 次 access。挑選條件：同一次 access 裡沒有 reclaim、COT entry 要從 DRAM 讀（CTLB miss）、stack 沒有 spill、拿到的 frame 與當初不同。

  ```
  python3 run.py --small --accesses 3000 --variant baseline --lesson out/lesson-decompress-hw.html --lesson-scene decompress-hw
  ```

  | 步 | 誰 | 內容 |
  |---|---|---|
  | 1 | 說明 | 舞台與角色、page 0x4F5 現在的樣子 |
  | 2 到 4 | user SW、kernel | LOG 的讀取被 access gate 擋下、kernel 認出是「被壓縮的 page」、拿一個空 frame |
  | 5 到 9 | kernel | 填 DECOMPRESS descriptor，口頭交代，寫 DOORBELL |
  | 10 到 12 | LZ4 HW | 讀 descriptor、從 DRAM 讀 COT entry、解出 count、comp_len 與 chunk 清單 |
  | 13 到 16 | LZ4 HW | 一步一個 chunk：照 COT 的順序讀進 engine，接成 1938 B 的 stream |
  | 17 到 19 | LZ4 HW | 驗 checksum、LZ4 解碼寫進 frame、寫 completion 1 並發 IRQ |
  | 20 到 22 | kernel | 讀 completion 1，決定丟掉壓縮的那一份（RW page），填 INVALIDATE descriptor 並交代 |
  | 23 到 29 | LZ4 HW | 讀 descriptor 2、COT 這次在 CTLB 裡、一步一個把 chunk 號碼 push 回 stack、把 COT entry 清成 0、寫 completion 2 |
  | 30 到 32 | kernel、user SW | 讀 completion 2、最後才把 PTE 寫成 valid、LOG 重試成功 |
  | 33 | 說明 | 前後對照，以及等待時間 3000 + 1424 + 300 = 4724 ns 的來源 |

  `compress-sw`，偏軟體方案的 COMPRESS，共 32 步。和 `compress-hw` 是同一次 access、同一個 victim；chunk 號碼不同，因為這裡是 kernel 從 bitmap 找的（0xD5B 起連續 7 個），不是硬體從 stack pop 的。

  ```
  python3 run.py --small --accesses 3000 --variant baseline --lesson out/lesson-compress-sw.html --lesson-scene compress-sw
  ```

  | 步 | 誰 | 內容 |
  |---|---|---|
  | 1 | 說明 | 舞台與角色、名詞表 |
  | 2 到 3 | user SW、kernel | UI 被擋在 access gate、kernel 挑 victim |
  | 4 到 6 | kernel | 在 bitmap 的 word 53 找 7 個 0 的 bit、寫成 1、對應的 7 個 chunk 變成 reserved |
  | 7 | kernel | 把 PTE 改成 invalid |
  | 8 到 13 | kernel | 一次寫一組欄位，把 48 B 的 descriptor 填滿，最後是 7 個 chunk 號碼 |
  | 14 | kernel | 向 LZ4 HW 口頭交代工作，寫 DOORBELL |
  | 15 到 17 | LZ4 HW | 讀 descriptor 並檢查號碼範圍、讀 frame 進 engine、比對 give-up 門檻 |
  | 18 到 21 | LZ4 HW | 一步一個 chunk：照 descriptor 的順序寫入一段 stream，只用了 4 個 |
  | 22 到 23 | LZ4 HW | 算 checksum，寫 completion（length 與 checksum 交給 kernel）、發 IRQ |
  | 24 到 28 | kernel | 讀 completion，再一組一組欄位自己寫 COT entry |
  | 29 到 31 | kernel | 把沒用到的 3 個 bit 寫回 0、看 chunk pool 的結果、釋放 frame |
  | 32 | 說明 | 前後對照、誰碰了什麼，以及和 `compress-hw` 同一個 job 的差別 |

  `decompress-sw`，偏軟體方案下 PTE invalid 觸發的 DECOMPRESS，共 29 步。和 `decompress-hw` 是同一次 access（11519）；拿到的 frame 都是 169。

  ```
  python3 run.py --small --accesses 3000 --variant baseline --lesson out/lesson-decompress-sw.html --lesson-scene decompress-sw
  ```

  | 步 | 誰 | 內容 |
  |---|---|---|
  | 1 | 說明 | 舞台與角色、page 0x4F5 現在的樣子（COT 是 kernel 寫的、bitmap 的 4 個 bit 是 1） |
  | 2 到 4 | user SW、kernel | LOG 的讀取被 access gate 擋下、kernel 認出是「被壓縮的 page」、拿一個空 frame |
  | 5 到 6 | kernel | 自己讀 COT entry：VALID、count、comp_len、chunk 清單、checksum |
  | 7 到 13 | kernel | 填 48 B 的 DECOMPRESS descriptor，comp_len、checksum 與 4 個 chunk 號碼都從 COT 抄過去 |
  | 14 | kernel | 口頭交代，寫 DOORBELL |
  | 15 | LZ4 HW | 讀 descriptor 並檢查，不讀 COT |
  | 16 到 19 | LZ4 HW | 一步一個 chunk：照 descriptor 的順序讀進 engine，接成 1938 B 的 stream |
  | 20 到 22 | LZ4 HW | 拿 descriptor 上的 checksum 來驗、LZ4 解碼寫進 frame、寫 completion 並發 IRQ |
  | 23 到 26 | kernel | 讀 completion；沒有第二個 job，自己把 COT entry 清成 0、把 bitmap 的 4 個 bit 寫回 0 |
  | 27 到 28 | kernel、user SW | 最後才把 PTE 寫成 valid、LOG 重試成功，等待時間 3000 + 1324 + 300 = 4624 ns |
  | 29 | 說明 | 前後對照、誰碰了什麼，以及和 `decompress-hw` 同一次 access 的差別 |

- **畫面**：左邊是 3D 舞台，鏡頭每一步自動移到正在被讀寫的結構。Descriptor、completion 與 COT entry 是平躺的大板子，每個 byte 一格，還沒寫的格子是暗的 `--`。格子的顏色是**寫的人**（黃是 KERNEL SW、紫是 LZ4 HW），右上角的小三角是**對方讀過**。斜線是壓縮資料，藍色是 RW page 的原始資料。角色說的話是英文 speech bubble，內容直接引用當步寫進去的值。
- **右側面板**：這一步的中文說明；正在動的結構的欄位表（offset、欄位、DRAM 裡的 bytes、值、W、R）；`WHO TOUCHED WHAT` 總表，逐步累積 kernel 與 LZ4 HW 各自讀寫過哪些結構；LZ4 HW 的 job 時間累計（4 次 DRAM 存取 × 100 ns + 4096 ns = 4496 ns）。最後一步總表上的 `never` 就是重點：偏硬體方案裡 kernel 沒碰過 frame 資料、stack、chunk 與 COT；偏軟體方案裡反過來，LZ4 HW 沒碰過 PTE、COT 與 bitmap，只讀寫 descriptor 點名的東西。偏軟體兩課的時間列另外標出 kernel 記帳的固定 300 ns。
- **操作**：`Prev`、`Next`、`Play`、下方每步一格的進度點、左右方向鍵與空白鍵；舞台可拖曳旋轉、滾輪縮放，`Reset view` 回到這一步的預設鏡頭。
- **沒有畫的東西**：模擬器不模擬 ring 的 head 與 tail index，所以 lesson 把 descriptor 與 completion 各畫成 ring 的一格，不編造 index。
- `--lesson-fragment`：輸出不含 html / head / body 外殼的版本。
- **檔案的共用關係**：`kit.js`（stepper、板子、bubble、鏡頭）四課共用。`stage_base.js` 是兩種方案都有的舞台：access gate 與 user SW、frame、LZ4 engine、chunk pool、descriptor、completion 與 COT entry 的板子、角色的站位。`stage_hw.js` 在它上面加偏硬體方案才有的東西（16 B 的 descriptor 格式、硬體 SRAM 裡的 free-chunk stack），兩個 HW scene 共用；`stage_sw.js` 加偏軟體方案才有的東西（48 B 的 descriptor 格式、kernel 的 free-chunk bitmap，COT 標成 kernel 的帳），兩個 SW scene 共用。每個 scene 另有自己的 `*_steps.js`。新增 scene 時在 `lesson.py` 的 `SCENES` 加一筆並寫一份步驟的 js。

## 第一次跑的結果（seed 1，200,000 次 page touch）

| | baseline | software |
|---|---|---|
| RO image 實際 chunk 數 | 313,413（153.0 MiB） | 同 |
| 解析式估計（248 MiB × 0.55） | 279,347（136.4 MiB） | 同 |
| chunk 取整的浪費 | 9.5% | 同 |
| RO RAW 頁 | 2,979（4.7%） | 同 |
| fault rate | 8.8% | 同 |
| RW 物件平均 | 1,827 B，4.08 chunks，浪費 12.6% | 同 |
| DRAM 在用峰值 | 405.9 MiB | 同 |
| 工作數 | 31,238（含 2,282 個 INVALIDATE） | 28,955 |
| fault latency 平均 | 4.46 µs | 4.62 µs |
| 配置器 | 47,040 pop、239 refill、25 spill；CTLB 17,592 miss / 2,282 hit | 每次 reserve 平均掃 1.06 個 word，最多 2 |
| audit | ok | ok |

已經看得到的設計發現：

1. **512 B chunk 的取整讓 RO image 比投影片的估計多 16.6 MiB。** 投影片與網頁用 248 × 0.55 算 136.4 MiB，沒算每個物件最後一個 chunk 的空位。這直接吃掉 512 MiB 設計約三分之一的餘裕，sizing 要重算，或考慮 256 B chunk。
2. **1 個 entry 的 CTLB 在 DECOMPRESS 上幾乎每次 miss**，只有緊接著的 INVALIDATE 命中。它省的是一次 32 B 的讀，不是 fault 的瓶頸。
3. **軟體版的 bitmap 搜尋成本可以忽略**：pool 用到 62% 時每次保留 7 個 bit 平均掃 1.06 個 64-bit word。
4. **兩個版本的功能行為完全一致**（同樣的 fault、同樣的物件、同樣的 pool 用量）；差別只在 trace 裡誰做了什麼、DRAM 存取數、和每個工作多幾百 ns。這是預期的：分工不改變政策。
5. 壓不動的 RW page 留在 frame 裡會慢慢累積（200k 次後 229 個）；長時間跑要看 `--raw-store` 是否值得。

## 程式結構

| 檔案 | 內容 |
|---|---|
| `lz4sim/config.py` | `SystemConfig`：幾何、政策、時間常數；`SMALL` 是 1/64 的測試機器 |
| `lz4sim/formats.py` | COT entry、list chunk、兩種 descriptor、completion 的 pack / unpack；opcode 與狀態碼 |
| `lz4sim/codec.py` | liblz4 raw block 的壓縮與解壓、CRC-32 |
| `lz4sim/dram.py` | 一整塊 bytearray 當 DRAM，用 PA 存取，計次 |
| `lz4sim/workload.py` | 合成頁面與存取序列 |
| `lz4sim/alloc_stack.py` | 基準版硬體 free-chunk stack：SRAM top、list chunk、refill / spill、INIT |
| `lz4sim/alloc_bitmap.py` | 軟體版 kernel bitmap：build、reserve（ctz）、release、double free / alloc 檢查 |
| `lz4sim/engine.py` | `Lz4Engine`：兩個方案共用的 LZ4 datapath（壓縮、scatter、gather、CRC、解壓、streaming 時間） |
| `lz4sim/accel.py` | `AccelBase`（共用的 job 外框）、`BaselineAccel`（CTLB、stack、寫 entry、INVALIDATE、INIT）與 `SoftwareAccel`（stateless、range check） |
| `lz4sim/kernel.py` | `KernelBase`（狀態機、frame cache、LRU reclaim、fault 路徑）、`BaselineKernel`、`SoftwareKernel` |
| `lz4sim/sim.py` | build → boot → run → audit → stats；fault injection；報表 |
| `lz4sim/replay.py` | 3D replay 匯出：把 level `all` 的 trace 切成 boot 與每次 access 一個 scene，組成單一 HTML |
| `lz4sim/replay_assets/` | viewer 原始碼：`model.js`（由 trace 重建狀態）、`chars.js`（kernel、加速器與 user SW 的角色造型，replay 與 lesson 共用）、`scene.js`（three.js 場景、speech bubble）、`stage.js`（每種 event 的動作編排）、`ui.js`（播放器、HUD、鏡頭）、`shell.html`（版面） |
| `lz4sim/lesson.py` | 3D lesson 匯出：重跑模擬、挑一個教學用的 job、記下前後的 bytes，組成單一 HTML |
| `lz4sim/lesson_assets/` | lesson 原始碼：`kit.js`（stepper、byte 板子、bubble、鏡頭，各 scene 共用）、`stage_base.js`（兩種方案共用的舞台）、`stage_hw.js`（偏硬體方案才有的部分，兩個 HW scene 共用）、`stage_sw.js`（偏軟體方案才有的部分，兩個 SW scene 共用）、`compress_hw_steps.js`（25 步）、`decompress_hw_steps.js`（33 步）、`compress_sw_steps.js`（32 步）、`decompress_sw_steps.js`（29 步）、`shell.html`（版面） |
| `lz4sim/__main__.py`、`run.py` | 命令列 |
| `tests/` | 格式、配置器、共用 engine、端到端（含損壞注入與 raw store）、user SW 的 page 歸屬、replay 匯出、lesson 匯出 |

## 下一步

1. 用 SimPy 把加速器與 DRAM 做成有排隊的資源，看 COMPRESS 與 DECOMPRESS 互相等待、以及 display 的 QoS 對 fault latency 的影響。
2. 更多政策可以掛進 `KernelBase`：RO 優先 eviction、proactive compression、compressibility 先驗。
3. 從 `engine.py`、`accel.py` 與 `formats.py` 整理出加速器規格；從 `kernel.py` 與 `alloc_*.py` 整理出 kernel 規格與 pseudo code。

# hostsim：kernel 控制程序的 host simulation

用來先把算法與控制程序順過一遍。沒有時間，LZ4 HW 是一個函式。偏 SW 控制的方案。

`kernel.py` 是控制程序的參考寫法，之後 kernel 設計規格的 pseudo code 從它來。它對外只透過 `port` 的十幾個呼叫，碰不到 DRAM、LZ4 HW 或 workload。

同一份 `kernel.py` 有兩種跑法：

| 跑法 | 程式 | 用來回答什麼 |
|---|---|---|
| 一個 thread | `machine.py` | 每個程序裡各步驟的順序，以及不含時間的數字 |
| 多個 thread 交錯執行 | `conc.py` | 等待與叫醒、TLB、CPU cache、pin、不能等的 context 是否正確 |

DRAM、bitmap、workload、memory map 沿用 `lz4sim`。descriptor、completion、COT entry 的 byte 格式沿用 `ifsim/interface.json`。job ring、doorbell、interrupt 不在這裡，在 `ifsim`。

## 執行

```
python3 sim/run_host.py run                          # 小機器，20000 次 access，不到 1 秒，結束時 audit
python3 sim/run_host.py run --cfg full               # 正式大小，400000 次 access，約 8 秒
python3 sim/run_host.py run --policy lru             # 理想的 LRU，只用來比較
python3 sim/run_host.py run --codec cli --n 2000     # 壓縮與解壓縮改呼叫本機的 lz4 工具，每個 page 約 3 ms
python3 sim/run_host.py run --corrupt-every 200      # 每 200 次 access 弄壞一個存放中的 stream
python3 sim/run_host.py run --check-every 1000       # 每 1000 次 access 做一次 audit
python3 sim/run_host.py run --no-accessed            # 新的 PTE 不設 accessed bit
python3 sim/run_host.py run --json                   # 數字以 JSON 輸出
python3 sim/run_host.py walk                         # 每種情況印出一次真實執行的逐步紀錄
python3 sim/run_host.py walk evict_rw_ok             # 只印一種
python3 sim/run_host.py conc                         # 多個 thread：300 個隨機 schedule，約 3 秒
python3 sim/run_host.py conc --damage 0.05           # 另外弄壞存放中的 stream
python3 sim/run_host.py conc --explore 1 --users 2 --length 8   # 列舉最多打斷一次的所有 schedule
python3 sim/run_host.py conc --mutants               # 每次拿掉控制程序的一樣東西，看哪一項檢查擋下來
python3 sim/run_host.py gen-doc                      # 重跑並產生 spec/control-procedures-v0.md 與 .json，約 50 秒
python3 sim/run_host.py gen-doc --reuse              # 只改了文字或程式註解時，用存好的數字重建文件
cd sim && python3 -m pytest tests/test_hostsim.py tests/test_hostsim_conc.py    # 這個模擬的測試，約 10 秒
```

`walk` 的情況名稱：`first_touch`、`fault_ro`、`fault_rw`、`evict_ro`、`evict_rw_ok`、`evict_rw_incompressible`、`reclaim`、`lost`。

`conc` 的每次執行都是決定性的：同一個 seed 得到同一個 schedule。出錯時訊息裡附最後 40 步，用同一個 seed 可以重跑。

## 檔案

| 檔案 | 內容 |
|---|---|
| `kernel.py` | 控制程序：`boot`、`page_fault`、`first_touch`、`fault_in`、`reclaim`、`pick_victim`、`evict_ro`、`evict_rw`、`pin_page`、`unpin_page`、`thread_gone`，以及 kernel 擁有的表格 |
| `hw.py` | LZ4 HW：一個 descriptor 進，一個 completion 出。自己檢查 descriptor，兩次呼叫之間不留任何狀態 |
| `codec.py` | LZ4 block 的兩種來源：`lib` 是 liblz4，`cli` 是本機的 `lz4` 工具。兩者產生的 byte 相同 |
| `cache.py` | CPU cache 的模型：每個 frame 幾個 flag，檢查 C1 到 C4。兩種跑法都用 |
| `machine.py` | 一個 thread 的跑法。kernel 以外的一切：DRAM、CPU 與 CPU MMU、build tool、boot loader、user SW、逐步紀錄。`Port` 是 kernel 能呼叫的全部 |
| `conc.py` | 多個 thread 的跑法。scheduler、每個 core 的 TLB、執行中的檢查、拿掉一樣東西的 `MUTANTS` |
| `check.py` | audit：只看 DRAM、PTE 與 kernel 的表格，檢查 A0 到 A6 |
| `report.py` | 一次執行的數字，全部是次數與大小，沒有時間 |
| `walk.py` | 從逐步紀錄裡挑出每種情況的第一次，排成表格 |
| `doc.py`、`templates/` | 產生 `spec/control-procedures-v0.md`。程式碼區塊取自 `kernel.py` 原文，數字取自執行結果 |

## 這個模擬能回答與不能回答的

| 能 | 不能 |
|---|---|
| 每個程序裡各步驟的順序對不對 | 任何與時間有關的事：latency、throughput、lock 握多久 |
| 表格、COT、bitmap、PTE 彼此是否一致 | 真實負載下的 job 數。workload 是合成的 |
| 多個 thread 交錯時等待與叫醒對不對，在試過的 schedule 範圍內 | 兩個 core 真的同時執行握著 lock 的區段。模型裡這些區段不可分割 |
| LZ4 HW 與 CPU cache 會不會看到不同的內容 | cache 的實際行為。模型採最悲觀的假設，每個 frame 一份 |
| 不能等的 context 會不會 page fault，pin 住的 page 會不會被搬走 | job ring、interrupt、timeout、reset 的行為 |
| 選 page 的方法造成多少 LZ4 job | 打斷三次以上才出現的錯。列舉只做到兩次 |
| chunk pool 用掉多少、bitmap 要掃多遠 | |
| 記憶體用完時控制程序怎麼結束 | |

## 規則

改了 `kernel.py` 之後跑 `gen-doc --reuse`，文件裡的程式碼才會跟上。改到行為的話跑 `gen-doc`，再重讀文件第 1 節、7.3 與 7.4 的讀法、8.4 的讀法與第 10 節，因為這幾處的文字是對著數字手寫的。`tests/test_hostsim.py` 會擋下過期的文件。

在控制程序裡加一個步驟時，也在 `conc.py` 的 `MUTANTS` 加一項把它拿掉，確認有檢查擋得下來。`tests/test_hostsim_conc.py` 會要求每一項都被擋下，而且是被預期的那一項檢查。

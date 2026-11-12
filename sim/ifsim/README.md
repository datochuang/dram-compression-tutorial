# ifsim：LZ4 HW/FW 介面模擬器

用來驗證偏 SW 控制方案的 HW/FW 介面與控制方式，並估效能與 budget。transaction level，discrete event，時間單位是整數 ns，不是 cycle based。

codec、DRAM、bitmap、workload、memory map 與 boot 都沿用 `lz4sim`，這裡只有介面兩側的 model 與驗證用的東西。

## 執行

```
python3 sim/run_if.py run --cfg small                       # 一次模擬，約 1 秒
python3 sim/run_if.py run --cfg full --set wait_mode=poll   # full-size，約 25 秒
python3 sim/run_if.py sweep --axis think_ns=20000,2000 --axis reclaim_inflight=1,2 --set wait_mode=irq
python3 sim/run_if.py run --cfg small --trace out/if.jsonl  # 邊界事件，JSON Lines
python3 sim/run_if.py gen-spec                              # 產生 spec/hw-fw-interface.md 與 spec/lz4_hwif.h
python3 sim/run_if.py results                               # 跑固定的實驗組，約 4 分鐘，產生 spec/sim-results-v0.*
python3 sim/run_if.py results --reuse                       # 只改了文字時，用存好的 JSON 重建文件
cd sim && python3 -m pytest tests                           # 全部測試，約 12 秒
```

可以用 `--set` 與 `--axis` 改的參數都在 `params.py` 的 `Params`。

## 檔案

| 檔案 | 內容 |
|---|---|
| `interface.json` | 介面的唯一定義：register、struct、enum、常數、規則。規格、C header、HW model、FW model、checker 都讀它 |
| `spec.py` | 讀 `interface.json`，提供 pack、unpack、欄位存取 |
| `des.py` | discrete-event 核心：process、resource、signal |
| `params.py` | 時間參數與暫定 budget。每個值都標明來源，目前全部是假設 |
| `platform.py` | FW 能用的窄介面：register 讀寫、記憶體讀寫、bus、interrupt line、監看用的 monitor |
| `hw.py` | LZ4 HW 的 model：ring、descriptor 檢查、bus burst、completion、halt 與 soft reset |
| `driver.py` | FW 的 driver：ring 管理、doorbell、interrupt 或 polling、timeout 與恢復 |
| `mm.py` | FW 的 page 管理：fault 路徑、reclaimer、COT、bitmap、PTE |
| `env.py` | user SW 的 thread 與故障注入 |
| `checkers.py` | 只看邊界事件與 DRAM，逐條檢查 `interface.json` 的規則；結束時 audit |
| `system.py` | 把以上接起來 |
| `report.py` | 統計與 Markdown 表格 |
| `experiments.py` | 結果文件用的固定實驗組 |
| `gen.py`、`templates/` | 產生規格、C header 與結果文件 |

## 改介面的流程

1. 改 `interface.json`。
2. `python3 sim/run_if.py gen-spec`。
3. `cd sim && python3 -m pytest tests`。`test_ifsim_gen.py` 會擋下沒有重新產生的文件，`test_ifsim_mutations.py` 會擋下沒有反例的新規則。
4. 行為有變的話再跑 `python3 sim/run_if.py results`，並重讀結果文件第 1 節。

HW model 與 FW model 裡的 `mut` 是故意放 bug 的開關，只給 `test_ifsim_mutations.py` 用。

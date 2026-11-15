# figures/kernel-sw-design

十三張白板圖，說明 LZ4 kernel SW 的設計概念與設計上的考量。讀者是完全不知道這個主題的工程師，所以前 4 張先講前提。十三張合成的 PDF 是 `kernel-sw-design.pdf`。

這組圖是負責人 2026-11-15 要的：「對於LZ4 kernel SW產出一連串的白板工程圖說明其設計概念和各種設計的考量, 必須假設讀者根本不知道這個主題, 所以該有的前提介紹都要做」。

| # | 檔案 | 回答的問題 |
|---|---|---|
| 1 | `01-why-compress.png` | 為什麼要壓縮 DRAM |
| 2 | `02-pages-and-frames.png` | page、frame、CPU MMU、page fault 是什麼 |
| 3 | `03-page-swap.png` | page swap 是什麼，我們做的是哪一種 |
| 4 | `04-how-a-page-is-stored.png` | 壓過的 page 怎麼放：chunk、COT、bitmap |
| 5 | `05-parts-of-the-kernel-sw.png` | kernel SW 有哪些部分 |
| 6 | `06-page-states.png` | 一個 page 的六個 state |
| 7 | `07-fault-path.png` | fault 路徑的九步 |
| 8 | `08-reclaimer.png` | reclaimer 怎麼挑 page、怎麼壓走 |
| 9 | `09-keeping-faults-short.png` | 設計選擇：壓縮不在 fault 路徑上 |
| 10 | `10-where-the-time-goes.png` | 設計選擇：等 LZ4 HW 用 sleep 還是 poll |
| 11 | `11-many-cores-at-once.png` | 很多 core 同時 fault |
| 12 | `12-where-it-goes-wrong.png` | 六個容易出錯的地方與規則 |
| 13 | `13-designed-and-open.png` | 已經設計的與還沒決定的 |

## 內容的依據

- 程序與順序：`sim/hostsim/kernel.py`，`spec/control-procedures-v0.md`。
- 數字：`spec/sim-results-v0.md` 的 1.2、1.8、5.1。圖上標明是模擬，通知、叫醒與指令的時間是假設。
- 平台前提 P1 到 P4：專案的 `CLAUDE.md`。第 8、13 張的「used mark 可能只有 kernel 能設」是從 P1 推出來的，不是平台資料。
- 待決定的事：`spec/control-procedures-v0.md` 第 10 節。第 13 張左欄寫「目前的設計」，不寫「已決定」，因為 D13 等幾項是先替負責人選的，還沒確認。

第 7、8 張是概念層級。逐步的資料結構、bytes 與 cycle 在 `figures/kernel-actions/`。

## 畫法

- 每張第一次用到的詞，在「New words on this sheet」卡片裡各一句定義。第一輪冷讀發現新手最常卡在沒定義的詞，第三版起加上。
- 第 5 張的 fault path 畫成疊起來的幾張，表示好幾個 core 可以同時在裡面。單一方框會被讀成只有一份、大家排隊。
- 第 11 張把時間切成十二格，每個 lock 方塊各佔一格，不重疊。

## 來歷

| 檔案或資料夾 | 內容 |
|---|---|
| `prompts.md` | 目前的提示詞，第五版 |
| `prompts-v1.md` 到 `prompts-v4.md` | 前四版 |
| `gen1/` 到 `gen4/` | 每一輪生成的 PNG、組好的提示詞、meta |
| `generation-log.jsonl` | 每一次 generate、edit、accept 與像素修補各一行 |
| `review-gen1-to-gen4-20261115.md` | 驗收紀錄 |
| `blind-review/` | 只給圖、不給提示詞的冷讀報告 |

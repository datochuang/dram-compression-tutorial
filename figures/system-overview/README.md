# figures/system-overview

整顆 processor 與壓縮層的系統圖。讀者是知道 cache、TLB、CPU MMU 的工程師，沒讀過壓縮層的規格。

內容照專案 `CLAUDE.md` 的平台前提 P1 到 P4。N 的值未定，圖上都寫 N。

## 兩種圖

| 檔案 | 是什麼 | 怎麼產生 |
|---|---|---|
| `processor-overview.svg`、`processor-overview.png` | 一張總覽：core、hardware thread、CPU MMU 與 TLB、L1、L2、kernel SW instance、共用的表、lock、LZ4 HW | `python3 gen_processor_overview.py`，再用 headless Chrome 轉 PNG |
| `01-per-core-and-shared.png` | 白板圖 1：哪些是每個 core 一份，哪些是共用的 | 圖像模型，提示詞在 `prompts.md` |
| `02-tlb-miss-enters-kernel.png` | 白板圖 2：TLB miss 進 kernel，kernel SW 查 page table、填 TLB | 同上 |
| `03-one-kernel-many-instances.png` | 白板圖 3：kernel SW 一份程式碼、多個 instance，`mm_lock` | 同上 |
| `04-one-lz4-hw-for-every-core.png` | 白板圖 4：一個 LZ4 HW、N 個 engine、一個 job ring、`ring_lock` | 同上 |

## 白板圖的來歷

| 檔案或資料夾 | 內容 |
|---|---|
| `prompts.md` | 目前的提示詞，第四版。圖上文字以它為準 |
| `prompts-v1.md` 到 `prompts-v3.md` | 舊版提示詞。每一版改了什麼寫在 `prompts.md` 的開頭 |
| `gen1/` 到 `gen4/` | 每一次生成的 PNG、組好的提示詞、meta |
| `generation-log.jsonl` | 每一次 generate 與 accept 一行 |
| `blind-review/` | 只給圖、不給提示詞的冷讀報告，每一輪一份 |
| `review-gen4-20261113.md` | 驗收紀錄：哪一張採用哪一輪、每一輪為什麼重生、記錄不改的小瑕疵 |

第 1、2 張採用 gen1，第 3 張採用 gen3，第 4 張採用 gen4。

## 還沒有被別的文件引用

這一組圖目前沒有嵌進 `spec/` 或 `docs/` 的任何文件。

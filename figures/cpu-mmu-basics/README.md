# figures/cpu-mmu-basics

三張白板圖，給沒有接觸過 CPU MMU 的 team member 與主管。它們補在 `figures/system-overview/` 那一組的前面與後面。

內容照專案 `CLAUDE.md` 的平台前提 P1 與 P3。address 是 repo 的 `README.md` 用的例子。這三張沒有 LZ4 HW，也沒有 lock。

## 三張圖

| badge | 檔案 | 回答的問題 | `README.md` 的哪一層 |
|---|---|---|---|
| A | `01-why-translate.png` | user SW 用的 address 為什麼不是 DRAM 上的位置 | 第 1 層 |
| B | `02-page-table-tlb-mmu.png` | 轉換靠哪些東西，各在哪裡，誰讀誰寫 | 第 2 層 |
| C | `03-clear-every-tlb-first.png` | kernel 把一個 page 的 frame 拿走時，各個 core 的 TLB 怎麼辦 | 第 6 層 |

badge 用字母，避免和 `figures/system-overview/` 的 1 到 4 混在一起。

## 閱讀順序

這三張不能單獨成一組。C 用到 TLB miss、exception、每個 core 一張 TLB，這些是 `figures/system-overview/` 的白板圖 2 與 1 教的。

| 順序 | 圖 |
|---|---|
| 1 | A |
| 2 | B |
| 3 | `figures/system-overview/02-tlb-miss-enters-kernel.png` |
| 4 | `figures/system-overview/01-per-core-and-shared.png` |
| 5 | `figures/system-overview/03-one-kernel-many-instances.png` |
| 6 | C |

## C 畫的規則從哪裡來

- 順序來自 `sim/hostsim/deps.py`：`pte_clear` 在 `tlb_inval` 之前，`tlb_inval` 在 `put_frame` 之前。
- 「少清一個 core」的後果來自 `sim/hostsim` 的測試。故意改壞的版本 `local_tlb_flush` 只清自己這個 core 的 TLB，測試抓到 `StaleTlb`。
- Core 1 上的 kernel 用什麼機制清 Core 0 的 TLB，目前不知道。圖上只畫「要清」，不畫怎麼清。

## 來歷

| 檔案或資料夾 | 內容 |
|---|---|
| `prompts.md` | 提示詞。圖上文字以它為準。Prompt 3 是第二版，改了什麼寫在那一節的開頭 |
| `gen1/` 到 `gen3/` | 每一次生成的 PNG、組好的提示詞、meta |
| `generation-log.jsonl` | 每一次 generate 與 accept 一行 |
| `blind-review/` | 只給圖、不給提示詞的冷讀報告，兩輪各一份 |
| `review-gen3-20261113.md` | 驗收紀錄：哪一張採用哪一輪、為什麼重生、記錄不改的小瑕疵 |

A 與 B 採用 gen2，C 採用 gen3。

## 被誰引用

repo 的 `README.md` 第 2、3、7 節。同一個題目的動畫在 `addrspace/` 的 CPU MMU 那一頁。

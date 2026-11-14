# figures/two-stage-task

一張白板圖。讀者是第一次碰這顆 processor 的團隊，用途是說明這次工作的性質。

| badge | 檔案 | 回答的問題 |
|---|---|---|
| 1 | `01-two-stages.png` | 這次的工作是什麼，難在哪裡 |

## 圖的主張

工作分成兩段。

1. 第一段：processor 本來就有 CPU MMU，但團隊沒有裝上、也沒有開啟過。這一段把它整合進來、打通、驗證。CPU MMU 是成熟的設計，困難在團隊不熟，不在硬體。
2. 第二段：在 page swap 的框架裡加上 LZ4 HW。page 不 swap 到 disk，而是 swap 到 DRAM 裡壓縮過的空間。

這個分法是負責人 2026-11-14 說明的。

第二版照負責人的意見，左邊畫出 multi-core、multi-thread 的 processor，以及 kernel SW 裡記憶體管理的六個已知部分，page swap 是其中之一。右邊用放大線畫成 page swap 的特例。

## 內容的依據

- 照 P1 沒有 hardware page table walk，TLB miss handler 由 kernel SW 寫。所以它列在第一段，不管有沒有壓縮都要做。
- 這個平台有沒有 disk 不知道。disk 只是一般 swap 的對照，沒有箭頭接到它。

## 來歷

| 檔案或資料夾 | 內容 |
|---|---|
| `prompts.md` | 提示詞第二版。圖上的文字以它為準 |
| `prompts-v1.md` | 提示詞第一版 |
| `gen1/`、`gen2/` | 兩版生成的 PNG、組好的提示詞、meta |
| `generation-log.jsonl` | 每一次 generate 與 accept 各一行 |
| `blind-review/` | 只給圖、不給提示詞的冷讀報告，每版一份 |
| `review-gen1-20261114.md` | 第一版的驗收紀錄 |
| `review-gen2-20261114.md` | 第二版的驗收紀錄，採用的是這一版 |

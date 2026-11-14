# figures/two-stage-task

三張白板圖。讀者是第一次碰這顆 processor 的團隊。三張合成的 PDF 是 `two-stage-task.pdf`。

| badge | 檔案 | 回答的問題 |
|---|---|---|
| 1 | `01-two-stages.png` | 這次的工作是什麼，難在哪裡 |
| 2 | `02-apart-in-space-and-time.png` | 第二段既然是第一段的延伸，CPU MMU 與壓縮層會不會綁在一起 |
| 3 | `03-apart-even-in-software.png` | 壓縮層現在是純 kernel SW，為什麼不和 CPU MMU 的 kernel SW 一起設計 |

第 3 張的論點：兩邊將來長到不同的地方。CPU MMU 這邊的硬體幫手是每個 core 裡的 TLB。壓縮這邊要加速時，是所有 core 共用一套，放在 LZ4 HW 旁邊，由一個總管使用。圖上標 proposal。採用的是第二版，冷讀時還有兩個反駁沒有回答：兩邊共用 page table，以及清每個 core 的 TLB。第三版的提議寫在 `review-gen7-20261114.md`。

第 1 張說兩者在工作上有延伸關係。第 2 張說兩者在硬體位置與軟體行為上是分開的：CPU MMU 在每個 core 裡、在每一次 access 的路上；壓縮層在 processor 外、DRAM 旁，只在 page swap 時動作。時間與頻率的部分和 `figures/cpu-mmu-basics/` 的第 D 張重疊，這一張多了空間。同一件事的動畫在 `docs/rhythm/`。

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
| `prompts.md` | 目前的提示詞。圖上的文字以它為準 |
| `prompts-v1.md` | 第 1 張的第一版 |
| `prompts-v2.md` | 第 1 張的第二版與第 2 張的第一版 |
| `prompts-v3.md` | 第 2 張的第二版 |
| `gen1/` 到 `gen5/` | 每一次生成的 PNG、組好的提示詞、meta。第 2 張採用 `gen5/` 修過兩次的 `.r3` |
| `review-gen4-20261114.md` | 第 2 張第一版與第二版的驗收紀錄 |
| `review-gen5-20261114.md` | 第 2 張第三版的驗收紀錄，採用的是這一版：兩個 domain frame |
| `prompts-v4.md` | 第 3 張的第一版 |
| `gen6/`、`gen7/` | 第 3 張的兩版 |
| `review-gen7-20261114.md` | 第 3 張的驗收紀錄與還沒解決的反駁 |
| `prompts-v5.md` | 第 1 張的第二版 |
| `gen8/` | 第 1 張的第三版 |
| `review-gen8-20261114.md` | 第 1 張第三版的驗收紀錄，採用的是這一版：兩欄各加一行大字點出工作性質 |
| `prompts-v6.md` | 第 2 張的第三版 |
| `gen9/` | 第 2 張的第四版。採用的 `.r3` 是拼接的，見驗收紀錄 |
| `review-gen9-20261114.md` | 第 2 張第四版的驗收紀錄，採用的是這一版：架構也用大字，ON 與 OFF THE ACCESS PATH |
| `generation-log.jsonl` | 每一次 generate 與 accept 各一行 |
| `blind-review/` | 只給圖、不給提示詞的冷讀報告，每版一份 |
| `review-gen1-20261114.md` | 第一版的驗收紀錄 |
| `review-gen2-20261114.md` | 第二版的驗收紀錄，採用的是這一版 |

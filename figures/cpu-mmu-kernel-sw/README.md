# figures/cpu-mmu-kernel-sw

十四張白板圖，說明 CPU MMU kernel SW 的設計概念與設計上的考量。讀者是完全不知道這個主題的工程師，所以前 4 張先講前提。十四張合成的 PDF 是 `cpu-mmu-kernel-sw.pdf`。

這組圖是負責人 2026-11-16 要的：「接下來幫CPU kernel SW也做一個一樣的文件」。「一樣」指 `figures/kernel-sw-design/` 那一組 LZ4 kernel SW 的圖，兩組的畫法相同，可以接著讀。

| # | 檔案 | 回答的問題 |
|---|---|---|
| 1 | `01-why-translate.png` | address 為什麼要轉換 |
| 2 | `02-page-table-tlb-cpu-mmu.png` | 誰記著對應，誰在查；這顆晶片的 CPU MMU 不讀 page table |
| 3 | `03-three-outcomes.png` | 一次 access 的三種結果 |
| 4 | `04-the-processor.png` | 每個 core 自己的與共用的；好幾個 hw thread 可以同時在 kernel 裡 |
| 5 | `05-parts-of-the-cpu-mmu-kernel-sw.png` | CPU MMU kernel SW 有哪些部分 |
| 6 | `06-the-pte-is-ours.png` | PTE 的格式與 page table 的形狀由 kernel 決定 |
| 7 | `07-tlb-miss-handler.png` | TLB miss handler 的八步 |
| 8 | `08-page-fault-handler.png` | page fault handler 怎麼分原因；page swap 是其中一種 |
| 9 | `09-changing-a-mapping.png` | 改 PTE 的方向決定要不要清每個 core 的 TLB |
| 10 | `10-many-programs.png` | 好幾支程式共用一個 TLB 時，清掉或加 tag |
| 11 | `11-refill-against-clear.png` | 不拿 lock 的 TLB miss handler 和清 TLB 之間的 race |
| 12 | `12-what-held-in-the-model.png` | 模型裡沒出錯的兩種做法，和與做法無關的 deadlock |
| 13 | `13-where-it-goes-wrong.png` | 六個容易出錯的地方 |
| 14 | `14-modeled-and-open.png` | 模型裡有的與還沒決定的 |

## 內容的依據

- 平台前提 P1 到 P4、推論、還不知道的事：專案的 `CLAUDE.md`。
- 概念與說法：`README.md` 的第 1 到 7 層，`figures/cpu-mmu-basics/`。
- page fault handler：`sim/hostsim/kernel.py` 的 `page_fault` 與 `first_touch`。
- 第 11、12 張：`sim/hostsim/conc.py` 的 `SplitTlb`，`sim/hostsim/tlbsplit.py`，`sim/tests/test_hostsim_tlbsplit.py`。這組圖做的時候跑了三次，輸出存在這個資料夾：
  - `tlbsplit-quick-20261116.txt`：`python3 -m hostsim.tlbsplit --quick`。
  - `tlbsplit-full-20261116.txt`：`python3 -m hostsim.tlbsplit`。每種組合跑 100 個隨機順序，加上搜尋最多一次插隊的所有順序。
  - `tlbsplit-recheck-irqoff-20261116.txt`：完整版沒有試過「寫完再讀一次 PTE」加上「關著 interrupt 等 mm_lock」。補跑之後 200 次全部 deadlock，第 12 張「四種做法都 deadlock」的說法以此為據。
- 清別的 core 的 TLB 用的 clear request 是模型裡的一個例子，不是平台的機制。圖上寫明。

**CPU MMU kernel SW 大部分還沒有設計。** 圖上分三種寫法：模型裡跑過的寫 in the model；一般的做法寫 a common way，不寫廠商或 CPU 名稱；還沒決定或要看 CPU 手冊的標 OPEN。

## 和現有內容的關係

- 第 5、8 張說 compression kernel SW 由 page fault handler 用 function call 叫起來，在同一個 hw thread 上跑。這和 `figures/two-stage-task/` 第 3 張、`figures/kernel-sw-design/` 第 5、7 張一致。
- 第 6、10 張的 page table 形狀、address space tag，第 11、12 張的兩種做法，都還沒有負責人的決定。第 14 張的 Open 表列出來。
- `sim/hostsim/conc.py` 預設仍然把 refill 當成一步，不拿 lock。`SplitTlb` 是另外開的實驗，預設關閉。

## 畫法

- 每張有一張「New words on this sheet」卡片。
- TLB miss handler 與 page fault handler 畫成疊起來的幾張，表示好幾個 hw thread 可以同時在裡面。
- 第 11 張的時間軸把 handler 的兩步畫成紫色虛線，其他步驟黑框。

## 來歷

| 檔案或資料夾 | 內容 |
|---|---|
| `prompts.md` | 目前的提示詞，第四版 |
| `gen1/` 到 `gen4/` | 每一輪生成的 PNG、組好的提示詞、meta。第一版的提示詞只留在 `gen1/` 的 `.prompt.txt` |
| `generation-log.jsonl` | 每一次 generate、edit、accept 與像素修補各一行 |
| `review-gen1-to-gen4-20261116.md` | 驗收紀錄 |
| `blind-review/` | 只給圖、不給提示詞的冷讀報告 |

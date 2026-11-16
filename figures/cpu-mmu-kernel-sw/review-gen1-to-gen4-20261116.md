# 驗收紀錄：cpu-mmu-kernel-sw，gen1 到 gen4

14 張全部採用，最後一輪冷讀每張的困惑指數都在 2 以下。

日期 2026-11-16。OpenAI `gpt-image-2.5-sunburst`，high，1536x1024。負責人要的是和 `figures/kernel-sw-design/` 一樣的一組圖，十四張一次做。

## 每張的經過

| # | 採用 | 回合 | 主要修改 |
|---|---|---|---|
| 1 | `gen1/01-why-translate.png` | 1 | 無 |
| 2 | `gen1/02-page-table-tlb-cpu-mmu.png` | 1 | 無 |
| 3 | `gen1/03-three-outcomes.png` | 1 | 無 |
| 4 | `gen2/04-the-processor.png` | gen1；gen2 | gen1 同時進 kernel 的兩個例子都在 Core 1，兩條線畫法不同。gen2 改成兩個 core 各一個 hw thread 同時 TLB miss，兩條線都穿過自己的 TLB、L1、L2 到 page table；兩個 TLB 各畫一格不同的 entry |
| 5 | `gen2/05-parts-of-the-cpu-mmu-kernel-sw.png` | gen1；gen2 | 拿掉沒有動作的 NET；reads the PTE 的箭頭寫明拿不拿 mm_lock 是 OPEN；padlock 移到表的下緣，寫 taken by the services；疊起來的框加註意思 |
| 6 | `gen1/06-the-pte-is-ours.png` | 1 | 無 |
| 7 | `gen1/07-tlb-miss-handler.r2.png` | gen1 加 edit | 模型多畫一個清單外的藍框「CPU executes instructions」，edit 拿掉 |
| 8 | `gen2/08-page-fault-handler.r2.png` | gen1；gen2；像素修補 | 兩個錯誤分支接到 finish: refused；compression 那格寫 to decompress it；便條說 sleep 時放開 mm_lock、哪些地方的 fault 會被拒絕。gen2 的副標題把 acts on 畫成 ads ant，從 gen1 貼回同一句 |
| 9 | `gen1/09-changing-a-mapping.png` | 1 | 無 |
| 10 | `gen1/10-many-programs.png` | 1 | 無 |
| 11 | `gen2/11-refill-against-clear.r2.png` | gen1；gen2 加 edit | NET 與 kernel 的 handler 分開；handler 的步驟畫成紫色虛線；加上 clear request 的箭頭；STALE ENTRY 移到寫入的那一步；Key point 指向第 12 張。第 12 張定稿後，edit 把 Key point 的 had no failure 改成 left no stale entry，避免和第 12 張的 deadlock 衝突 |
| 12 | `gen4/12-what-held-in-the-model.r2.png` | gen1 加像素修補；gen2；gen3；gen3 .r2；gen4 加像素修補 | 見下 |
| 13 | `gen2/13-where-it-goes-wrong.png` | gen1；gen2 | Key point 涵蓋六個陷阱；卡片下方的藍字不加 Where |
| 14 | `gen2/14-modeled-and-open.png` | gen1；gen2 | 打勾清單加上 deadlock 那條規則 |

第 12 張的經過：
- gen1 把 deadlock 塞進表格的第五列。冷讀困惑指數 3。
- gen2 把 deadlock 拿出表格，但結果欄寫 no failure、deadlock 那格寫每種做法都發生，被讀成互相矛盾。冷讀困惑指數 3。
- gen3 改寫成兩部分：上半是 TLB miss handler 的四種做法，下半是和做法無關的 deadlock。冷讀困惑指數 3：四列沒有編號，Key point 的 way two 對不到；no failure 仍和 deadlock 衝突。
- gen3 .r2 只改文字：四列編號 way 1 到 way 4；結果欄改成 stale entry in the model?，答案是 yes 或 none found；way 3 寫出 drops the entry if the PTE changed。冷讀困惑指數 3：way 2 關 interrupt 和必守規則看起來衝突；way 4 等 mm_lock 時若在 interrupt handler 裡，自己就成了 deadlock 的一方，圖上沒說。
- gen4 表格縮成三欄，每種做法的條件寫進說明；way 4 寫明開著 interrupt 等 mm_lock，在 interrupt handler 裡也一樣；加一行說明 way 2 不等 lock。New words 的 interrupts 畫成 interrrupts，用像素修補拿掉多的那個字形。冷讀困惑指數 2，通過。
- gen4 裡的 `12-what-held-in-the-model.unused-v3-prompt.png` 是改提示詞的程式失敗、仍用第三版提示詞生成的一張，沒有驗收，也沒有用。

## 依據的補跑

`tlbsplit` 的完整版沒有試過 way 3 加上關著 interrupt 等 mm_lock。為了第 12 張「四種做法都 deadlock」這句話，補跑 core、thread 兩種送法乘上 handler 中途能不能接請求，各 200 次，全部 deadlock。輸出在 `tlbsplit-recheck-irqoff-20261116.txt`。

## 冷讀

| 輪 | 讀了哪幾張 | 報告 | 結果 |
|---|---|---|---|
| 1 | 全部 14 張，分三批 | `blind-review/cold-read-gen1-part1` 到 `part3` | 1、3 困惑指數 1；2、5、6、7、9、10、11、13 為 2；4、8、12 為 3。4、5、11、12 角色不清 |
| 2 | 4、5、8、11、12、13、14 | `cold-read-gen2-part1`、`part2` | 4、5、8、11、13、14 通過。12 困惑指數 3 |
| 3 | 12 | `cold-read-gen3` | 困惑指數 3，只差文字 |
| 4 | 12 | `cold-read-gen3-r2` | 困惑指數 3，內容上的兩個缺口 |
| 5 | 12 | `cold-read-gen4` | 困惑指數 2，通過。指出第 11 張 Key point 的 no failure 要改，已用 edit 改掉 |

## 記錄不改的小瑕疵

| # | 說明 |
|---|---|
| 4 | 紫色箭頭穿過 TLB 裡現有的那一格，可能被讀成 MEDIA miss 的就是 0x416；寫回 TLB 的回程沒畫 |
| 5 | OPEN 標籤是黃底；畫面沒有 exception；Key point 說兩個 handler 都用 service，畫面上只有 page fault handler 呼叫 |
| 6 | 寫「used mark: see sheet 7」，第 7 張只在 New words 定義，流程裡沒有設 used mark 的一步 |
| 7 | 第 4 步的語序容易讀錯；hardware walk 的用詞和第 6 張不統一 |
| 8 | LOG 的人物多戴了一頂帽子；便條的 in the model 沒說是哪個 model；page swap 在這張沒有定義 |
| 9 | 左欄只有一步卻編了 1；other hardware 沒說是什麼 |
| 10 | 左下有一個多出來的小點；MEDIA 沒介紹就出現 |
| 11 | 步驟 3、5 也是 kernel 在做，卻是黑框；步驟 4 回到 5 的 answer 沒畫 |
| 13 | 第一格打叉的方格意思不明；副標說多半是讀錯 frame，但 deadlock 與 handler 內 miss 不是 |
| 14 | deadlock 那一項打勾，第一眼像是核可；副標沒提到 measurement 那一類 |
| 全組 | 紫色虛線框的意思隨張而變：handler、kernel 的動作、選項、PTE。黃色一下用在注意事項，一下用在 OPEN |

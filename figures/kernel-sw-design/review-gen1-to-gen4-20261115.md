# 驗收紀錄：kernel-sw-design，gen1 到 gen4

13 張全部採用，最後一輪冷讀每張的困惑指數都是 2。

日期 2026-11-15。OpenAI `gpt-image-2.5-sunburst`，high，1536x1024。負責人選擇 13 張一次做完。

## 每張的經過

| # | 採用 | 回合 | 主要修改 |
|---|---|---|---|
| 1 | `gen1/01-why-compress.png` | 1 | 無 |
| 2 | `gen2/02-pages-and-frames.r3.png` | gen1 加 edit；gen2 重生；像素修補兩次 | gen1 少了 C、TLB hit 箭頭穿過表格。gen2 改版面：frame 在上、page table 在下，加 New words 與 page fault 方框。副標題的 thle 用像素修補 |
| 3 | `gen3/03-page-swap.r2.png` | gen1 加 edit；gen2；gen3 加 edit | gen1 的 DECOMPRESS 箭頭指向壓縮區。gen2 的 NET 箭頭直接進壓縮區。gen3 改成兩欄同一個版面：NET 指向 kernel SW，kernel 交 job，LZ4 HW 夾在 frame 與壓縮區中間。edit 把 a job 改指 LZ4 HW |
| 4 | `gen2/04-how-a-page-is-stored.r3.png` | gen1；gen2；像素修補 | 加 COT 全名、CRC、OPEN、7 個 chunk 的理由、COMPRESS 分三支。多出的第四支用像素修補擦掉 |
| 5 | `gen2/05-parts-of-the-kernel-sw.png` | gen1；gen2 | gen1 困惑指數 2 但 fault path 被讀成只有一份。gen2 畫成疊起來的三張 |
| 6 | `gen2/06-page-states.png` | gen1；gen2 | 加起點標記、RW 回來時放 chunk、kernel 的 decoder、New words |
| 7 | `gen1/07-fault-path.png` | 1 | 無 |
| 8 | `gen2/08-reclaimer.png` | gen1；gen2 | 水位改成溫度計，標 free frames；兩欄都有 lock 與箭頭；接上 state；New words |
| 9 | `gen4/09-keeping-faults-short.png` | gen1 加 edit；gen2 加像素修補；gen3；gen4 | load 的定義、表格改成不需要分母的欄位、direct reclaim 寫成目前沒有但還沒決定 |
| 10 | `gen1/10-where-the-time-goes.png` | 1 | 無 |
| 11 | `gen1/11-many-cores-at-once.r2.png` | gen1；改提示詞重生 | 第一次 lock 方塊重疊。改成十二格，每個 lock 一格 |
| 12 | `gen4/12-where-it-goes-wrong.png` | gen1；gen2；gen3；gen4 | 每條規則寫出由誰做、加小圖示、Key point 只說 HW 不檢查讀寫位置 |
| 13 | `gen3/13-designed-and-open.png` | gen1；gen2；gen3 | 左欄寫目前的設計而不是已決定；加 F16 那一列；needs 欄改成 a design decision 等 |

像素修補都記在 `generation-log.jsonl` 的 composite 行。edit 修單一字母的錯字三次都沒有成功，所以改用像素修補。

## 冷讀

| 輪 | 讀了哪幾張 | 報告 | 結果 |
|---|---|---|---|
| 1 | 全部 13 張，分三批 | `blind-review/cold-read-gen1-part1` 到 `part3` | 1、5、7、10、11 困惑指數 2。其餘 3 或角色不清。最常見的原因：詞沒有定義、kernel 在前 4 張看不到 |
| 2 | 2 到 6、8、9、12、13 | `cold-read-gen2-part1`、`part2` | 2、4、5、6、8 通過。3 的 NET 箭頭直接進壓縮區；9、12 困惑指數 3；13 的 Key point 與左欄不一致 |
| 3 | 3、9、12、13 | `cold-read-gen3` | 3、13 通過。9 的 no direct reclaim 與 OPEN 矛盾；12 的 Key point 說 HW 什麼都不檢查，與卡片矛盾 |
| 4 | 9、12 | `cold-read-gen4` | 兩張困惑指數 2，畫面與結論一致，通過 |

## 記錄不改的小瑕疵

| # | 說明 |
|---|---|
| 1 | Key point 說碰到 cold page 要短暫等待，畫面沒畫；五個 cold page 只壓出三塊 |
| 2 | 「every core has its own TLB」被往下的箭頭切成兩段；New words 沒有收 CPU MMU |
| 3 | 四條綠色箭頭只有兩條有字；a job 沒說是哪一種 job；fault 之後 PTE 與重跑沒畫 |
| 4 | 模型自己在 chunk 下面加了 1 到 16 的編號，第二版起寫進提示詞 |
| 5 | page state 和 page table 的關係沒說；LZ4 HW 仍是一個方框 |
| 7 | 模型多畫了步驟 3 到 5、5 到 6 的箭頭，和流程相符；PTE、completion 沒定義 |
| 8 | 「used mark 由 CPU MMU 設不設」和第 13 張的說法措辭不同，第 13 張已改成推論的寫法 |
| 10 | 長條三段相加 6.04 µs，標題 6.20 µs，差的是右邊小字寫的 lock 與 job ring；長條不是時間順序 |
| 11 | 時間軸是橘色；鎖頭只寫 lock 沒寫 mm_lock；two fixes 沒說是哪兩個 |
| 9 | 最後一欄沒說等的是什麼：normal 負載 1.9% 是等 fault，不是等 frame |
| 12 | 副標題說 skipping one breaks data，但第 3、4 格的後果不是資料損壞；Key point 只寫 frame，漏了 chunk |
| 13 | needs 欄混了人與資料來源 |

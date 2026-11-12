# 驗收紀錄：Kernel SW actions, step by step，gen1 到 gen7（prompts.md 第一版到第八版）

> 補記：這份紀錄裡說的「README」，內容在 2026-11-12 併進上一層的 `figures/README.md`（十三張圖的整合文件）。本資料夾的 README 只留檔案說明。

日期 2026-11-12。模型 OpenAI `gpt-image-2.5-sunburst`，quality high，size 1536x1024。每張一次生一張，讀圖後對文字清單與 checklist，再派一個只拿圖的 subagent 冷讀。冷讀報告在 `blind-review/`。

這一份涵蓋整組圖從頭到尾的七批，因為同一張圖常跨兩三批才定稿，分成七份會讀不出每張的來歷。

## 批次與提示詞版本

| 批 | 提示詞 | 內容 | 冷讀報告 |
|---|---|---|---|
| gen1 | 第一、二版 | 總覽層級的 7 張，一個場景一張，沒有資料結構與數字 | `cold-read-gen1-20261112.md` |
| gen2 | 第三版 | 改成步驟層級的 11 張：每一步的資料結構、位置、運算、指令數、cycle、相依 | `cold-read-gen2-20261112.md` |
| gen3 | 第四版 | 重畫 4、6、10、11 | `cold-read-gen3-20261112.md` |
| gen4 | 第五版 | 第 6 張拆成 6A 與 6B；重畫 7、10 | `cold-read-gen4-20261112.md` |
| gen5 | 第六版 | 重畫 6A，6B 改文字 | `cold-read-gen5-20261112.md` |
| gen6 | 第七版 | `deps.py` 補上 `note_hw` 讀解碼結果之後，重畫 6A、6B | `cold-read-gen6-20261112.md` |
| gen7 | 第八版 | 重畫 6A | `cold-read-gen7-20261112.md` |

**gen1 整批作廢，沒有任何一張驗收。** 使用者看過後要求細到資料結構、位置、運算、cycle 與真正的相依，總覽層級的圖答不了這些問題。gen1 的 7 次生成與 2 次 edit 留在 `gen1/` 當紀錄。

## 逐張（定稿的十二張）

回合數只算產生定稿那一版提示詞之下的次數；前面幾版的嘗試寫在備註。

| # | 檔案 | 定稿來源 | 回合 | 結果 | 備註 |
|---|------|------|------|------|------|
| 1 | `01-where-tables-live` | `gen2/…r2` | 2 | accept r2 | 第一版文字與版面都對。gen4 的冷讀之後用 `edit` 改底部那一句，寫明七張以 h 索引的表是哪七張 |
| 2 | `02-fault-lock-a` | `gen2/…r4` | 4 | accept r4 | 第一版把 kernel 的四步塗成綠色加齒輪，`edit` 改回白色並補 lock 標示的 "kernel,"；r3 改底部句子、擦掉一個多餘的藍色小記號；r4 在 `take_frame` 補第二面旗 "free_top, to step 18"。超過三回合：後兩次是冷讀之後補內容，不是修同一個錯 |
| 3 | `03-fault-job` | `gen2/…r2` | 2 | accept r2 | 第一版全對。`cpl_read` 的模型規則改了（completion 那條 line 一定 miss），`edit` 改三處數字與旗標 |
| 4 | `04-fault-lock-b` | `gen3/…r2` | 2 | accept r2 | 第三版畫了兩次，gen2 的冷讀是 3。第四版重畫，gen3 的冷讀還是 3；`edit` 改兩面旗的 "after" 為 "from"，並把返回的箭頭起點移到灰框右緣，gen4 的冷讀是 2 |
| 5 | `05-first-touch` | `gen2/…r2` | 2 | accept r2 | 第一版文字全對，徽章是白底，`edit` 塗成橘色 |
| 6A | `06a-fault-rescue` | `gen7/` | 1 | accept | 見下面「第 6 張的來歷」 |
| 6B | `06b-fault-lost` | `gen6/` | 1 | accept | 見下面「第 6 張的來歷」 |
| 7 | `07-clock-scan` | `gen4/` | 1 | accept | 第三版的圖經過兩次 `edit` 仍在 gen3 的冷讀拿到 3。第五版重畫一次過 |
| 8 | `08-evict-rw-lock-a` | `gen2/` | 1 | accept | 一次過。bitmap 找空位的運算（找 0 的 bit、設 7 個 bit）與 111 道指令都在 |
| 9 | `09-evict-rw-job` | `gen2/…r2` | 2 | accept r2 | 第一版全對。`edit` 改 `cpl_read` 的 cycle 與底部的範圍，理由同第 3 張 |
| 10 | `10-evict-rw-lock-b` | `gen4/` | 1 | accept | 第三、四版各畫一次，冷讀都是 3。第五版重畫一次過 |
| 11 | `11-totals` | `gen3/…r2` | 2 | accept r2 | 第三版的圖 `edit` 過一次。第四版重畫，`edit` 把第一行藍字改成完整的 cycle 公式 |

### 第 6 張的來歷

| 批 | 檔案 | 冷讀 | 為什麼沒用 |
|---|---|---|---|
| gen2 | `06-fault-rescue`、`.r2` | 4 | rescue 與 lost 兩個結局擠在一張，讀的人分不出哪些步驟屬於哪個結局 |
| gen3 | `06-fault-rescue`、`.r2` | 4 | 同上，版面換了還是一樣 |
| gen4 | `06a-fault-rescue` | 3 | 拆成兩張。6A 的步驟編號和第 4 張撞號，握 lock 的八步只畫四步，加總驗不出來 |
| gen4 | `06b-fault-lost`、`.r2`、`.r3`、`.r4` | 2 | 冷讀通過，但之後發現 `note_hw` 少一條相依，作廢 |
| gen5 | `06a-fault-rescue` | 2 | 冷讀通過，同一個原因作廢 |
| gen6 | `06a-fault-rescue` | 3 | `note_hw` 的箭頭畫上去了，但箭頭、灰框下方的藍字、副標三處互相打架 |
| gen6 | `06b-fault-lost` | 2 | **定稿** |
| gen7 | `06a-fault-rescue` | 2 | **定稿** |

第八版對 6A 改了什麼：副標與旗標改成「bus error or bad stream」，這一張涵蓋兩種回答；13 到 16 的箭頭標籤自己寫明條件 "read if the answer was bad stream"；兩支規則箭頭改用 `deps.py` 那條規則的說法；12 到 14 的標籤補上 "old lines dropped first"；lock 的標示移進灰框左下角，不再被箭頭穿過；藍字改成算 strike 的規則。

## 冷讀找出的內容錯誤

冷讀不只抓到畫錯的地方，也抓到來源本身的錯。

1. **`cpl_read` 的 cycle 下限。** gen2 的冷讀指出第 3、9 張自相矛盾：方塊寫「always from DRAM」，便條的下限 62 卻等於沒有 miss。LZ4 HW 剛寫的 completion 不可能已經在 CPU 的 cache 裡，所以模型改成那條 line 一定 miss，`cpl_read` 從 62 到 162 變成 162，文件、第 3、9、11 張都跟著改。
2. **`note_hw` 少一條相依。** gen5 的冷讀的人問：6B 的 `note_hw` 寫「the LZ4 HW was right」，但沒有線從 `sw_decode` 來，它怎麼知道。對過 `kernel.py`：`wrong = status == BUS_ERROR or (ok and status == BAD_STREAM)`，確實讀了軟體解碼的結果。`sim/hostsim/deps.py` 的 `note_hw` 少宣告這個讀取，已補上，兩份文件重新產生，231 個測試通過。這條漏掉的相依測試抓不到，因為 thread 自己的變數不在執行紀錄的核對範圍裡。
3. **README 的兩處錯。** `fresh[t]` 的說明第一版寫錯，對過 `sim/kstep/kstep.h` 後改正。`fault_rescue` 第一版寫成 bad stream 的例子，模擬跑的其實是 bus error，已改正並加上六種組合的表。

## 冷讀結果

### gen2（11 張）

困惑指數：01 = 2，02 = 2，03 = 2，04 = 3，05 = 2，06 = 4，07 = 2，08 = 2，09 = 2，10 = 3，11 = 2。

冷讀者的結論：

> 每頁的帳分散在七張以 h 索引的表，所以 kernel 每個場景要碰 5 到 10 條新的 cache line。kernel 自己的表格工作很少，約 59 到 2112 cycles，主要取決於這些 line 有沒有 miss，再加上填零或抄 4 KiB。mm_lock 只在很短的兩段（鎖 A、鎖 B）裡拿著，LZ4 HW 工作夾在中間、不拿鎖。每段鎖內的相依幾乎都是「第一步讀出 state 或挑出 victim，其餘幾步互不相干」。真正長的時間在 kernel 以外：例外進出、interrupt 加 wake-up（假設 3150 ns）、LZ4 HW（解壓 1253 ns、壓縮 4260 ns），合計 500 到 7910 ns。

### gen3（11 張，其中 4、6、10、11 是重畫的）

困惑指數：01 = 2，02 = 2，03 = 2，04 = 3，05 = 2，06 = 4，07 = 3，08 = 2，09 = 2，10 = 3，11 = 2。

> kernel 自己的記帳工作很小。每個情境是幾十到一千個 instr，換成 59 到 2112 cycles；大頭不是運算，而是分散在好幾張表上的 cache miss（一個情境 5 到 10 條新 line，每條最多 100 cycles），以及少數整頁的動作（填零 341、軟體救回複製 791、bitmap 找 7 個空位 111）。真正在等的是別人：例外進出、interrupt 加喚醒（3150 ns）和 LZ4 HW（解壓 1253 ns、壓縮 4260 ns），合計 500 到 7910 ns，比 kernel 自己的步驟大好幾倍。鎖只在頭尾各拿一小段（A 與 B），LZ4 job 那段不拿鎖。鎖內多數步驟彼此沒有先後，真正的相依只有少數幾個值（`free_top`、`state[h]`、`f`、victim、completion）和幾條順序規則（先標狀態再送 job、先清 cache 再寫 register、先寫 COT 再放 frame、先設 PRESENT 再叫醒）。還沒量的有兩樣：一個 frame 64 條 line 的 cache 維護、軟體解碼。

### gen4（12 張）

困惑指數：01 到 05 = 2，06A = 3，06B = 2，07 到 10 = 2，11 = 1。

> kernel 為一次事件做的記帳工作很小：幾十到幾百個指令、最多十條新的 cache line，合計 59 到 2112 cycles，而且分成一到兩次很短的 mm_lock 握鎖；中間 LZ4 HW 的工作不握鎖。握鎖期間大多數步驟彼此不相依，真正要排順序的只有少數幾條規則：先標狀態才能送 job、cache 寫回 DRAM 才能敲暫存器、COT entry 寫好才能還 frame、frame 內容到位才能把 PTE 設成有效、狀態改好才能叫醒等待的 thread。真正花時間的是等待：例外進出、interrupt 與喚醒（假設 0.5 到 4.15 µs）和 LZ4 HW（解壓 1.25 µs、壓縮 4.26 µs）。kernel 自己變重的只有三處：first touch 握著鎖填零（397 個指令裡的 341 個）、軟體救援抄一整頁（791 個指令）、clock 掃描一次可能經過很多 frame。另外 frame 的 cache 維護（每次 64 個操作）和軟體解壓都還沒量，沒有算進任何一個總數。

這一次之後驗收 01、04、07、10。加上先前的 02、03、05、08、09、11，十張定稿。

### gen5（只驗 06A、06B）

06A = 2，06B = 2，都一致。兩張後來因為 `note_hw` 的相依作廢。

> 06A：LZ4 HW 回報失敗後，faulting thread 不握 lock 先 invalidate frame 的 cache、用軟體把 chunks 解到 kernel buffer、把 4096 B 抄進 frame 再寫回 DRAM，然後握一次 mm_lock 做和 sheet 4 的 RW page 幾乎一樣的收尾，只差 note_hw 改成記一次 strike。

> 06B：LZ4 HW 回報 bad stream 後，faulting thread 不握 lock 用軟體再解一次，確認 stream 真的壞了，接著握一次 mm_lock 把 frame 還回 free stack、不記 strike、把頁面標成 LOST、叫醒等這一頁的 thread，放掉 lock 後由 OS 終止這個 user SW。

### gen6（只驗 06A、06B）

06A = 3，06B = 2。06B 驗收，06A 重畫。

> 06A：主線一看就懂：LZ4 HW 回報 failed 後，faulting thread 不持鎖做軟體解壓、把 4096 B 抄進 frame、整理 cache，再進一次 mm_lock 做和 04 的 RW page 相同的八步收尾，只是 note_hw 改成 strikes + 1。問題出在相依關係，而那正是這組圖的重點。

> 06B：清楚。sw_decode 一條 data 線到 note_hw、兩條 rule 線到 put_frame 與 set_lost，set_lost 再到 wake_page，解鎖後 kill；驚慌的 user SW 火柴人把結局講完了。五支箭頭我都懂它為什麼存在。

### gen7（只驗 06A）

06A = 2，一致，加總全部驗得過。驗收。

> 06A 講的是：LZ4 HW 在 step 11 回報 bus error 或 bad stream 之後，kernel 的 faulting thread 先不拿鎖，丟掉 frame 的舊 cache lines、用軟體把 chunks 解出來、複製 4096 B 進 frame、再寫回 DRAM。接著第二次拿 mm_lock，記一次 strike、清 COT entry 並釋放 chunks、把狀態設成 PRESENT、填 page table、更新 fresh 紀錄、叫醒等待的 thread，最後 eret 回 user SW。主線一看就順，十支箭頭的方向都和故事一致。

## 記錄不改的小瑕疵

| 張 | 瑕疵 |
|---|---|
| 2 | `take_frame` 的旗 "free_top, to step 18" 用的是 `fault_ro` 的編號；在 `fault_rescue` 那一步是 23。README 有寫編號是每個場景各自編的 |
| 3 | 步驟 11 沒有標出回答有幾種，也沒有指向 6A、6B 的旗。README 有寫 |
| 3 | 副標只寫 `fault_ro`，`fault_rw` 也走這一張。README 有寫 |
| 6A | 沒有人物；lock 的標示在灰框內左下角，和別張的位置不同；沒有畫開鎖後的出口箭頭，改用一行藍字 |
| 6A | `sw_decode` 往下的四支線有兩支從便條的位置出發；框內上排的編號順序是 16、17、19、22、20 |
| 6A | `note_hw` 的便條是沒有 strike 那條路量到的 5 道指令，沒有 cycle；加總 119 沿用這 5 道 |
| 6A、6B | `sw_decode` 沒有「COT entry, from step 5」的旗 |
| 6A | `frame_write` 的 "64 lines written" 沒有說明為什麼不算 new line。README 有寫模型沒處理 |
| 6B | 掛在 `kill` 上的旗「step 12, cache_invalidate, sheet 3, must be done too」像一條沒畫出來的規則；"must" 多了底線；兩個箭頭標籤斜著寫；下半部留白偏多 |
| 6B | 被標成 LOST 的 page，它的 chunks 與 COT entry 去哪裡，圖上沒有交代 |
| 全組 | "answer" 與 "completion" 混用 |

## 沒有畫的

bus error 而軟體也解不開、LZ4 HW 沒有回答、`lz4_off` 已經是 1，這三條路沒有圖。README 的組合表列了它們和 6A、6B 差在哪。

## 總計

十二張定稿。32 次生成、18 次 edit、12 次 accept，全部在 OpenAI `gpt-image-2.5-sunburst`。其中 gen1 的 7 次生成與 2 次 edit 屬於作廢的總覽版。七次冷讀。

# 冷讀驗收報告：第七批 06A

- 日期：2026-11-12
- 方法：只給圖、不給提示詞的冷讀
- 驗收對象：第七批的 06A.png；其餘十一張（01 到 05、06B、07 到 11）只當上下文，依序讀過但不逐張記錄
- 讀圖限制：只用圖檔原本的解析度讀，沒有放大。小字的抄錄可能有個別字元的誤差，下面凡是我不確定的地方都會寫「看起來像」

## 結論先講

06A 不需要重生。困惑指數 2，故事讀得出來，箭頭方向都和故事一致，Cost 那一條的加總全部驗算得過。

有一支箭頭的型別值得對照原始資料確認：step 12 到 step 14 畫成橘色實線（data），但標籤寫的是先後順序（"old lines dropped first"），而同一組圖其他地方的 cache 先後關係都畫成黑色虛線（rule）。這不到重生門檻，但這組圖的重點就是「哪些相依是資料、哪些是規則」，所以列在小問題的第一條。

## 06A 逐題紀錄

### 1. 人物與機器

06A 上沒有畫任何人或機器的圖像：沒有火柴人，沒有齒輪圖示，沒有綠色的硬體方塊。角色全靠文字標籤交代。

| 角色 | 圖上的標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| kernel 的 faulting thread，沒拿鎖 | 左上藍字 "kernel, the faulting thread, no lock held" | step 12 到 15：丟掉 frame[f] 的舊 cache lines、用軟體把 chunks 解碼到 kernel buffer、把 4096 B 複製進 frame、再把 cache lines 寫回 DRAM | 在不拿鎖的情況下把頁面內容正確放進 frame |
| kernel，拿著 mm_lock | 灰框左下角的掛鎖加文字 "kernel, mm_lock held, lock hold B: lock 4 instr, unlock 2 instr" | step 16 到 23：記一次 strike、清 COT entry、釋放 chunks、把狀態設成 PRESENT、填 page table、更新 fresh 紀錄、叫醒等待的 thread、檢查 free_top | 先後順序：解碼成功才能 PRESENT、COT entry 先清才釋放 chunks、frame 內容到位才讓 pte 有效 |
| OS | 只出現在 step 21 的內文 "OS: wake threads waiting for page h"，沒有圖示 | 叫醒等同一頁的其他 thread | 看不出來 |
| LZ4 HW | 只出現在標題、副標題與底下的藍字註解，圖上沒有它的方塊 | 在 step 11 回答 bus error 或 bad stream（在別張發生） | 不在這張畫面裡 |
| user SW | 這張完全沒出現，只能從藍字 "24 eret and 25 rerun" 推出它最後被送回去 | 無 | 無 |

沒有「無標籤」的圖像。角色看不出來的地方只有一個：step 16 到 23 是不是同一條 faulting thread 在做，圖上沒有明講，只能從「lock hold B」和 04 的畫法推出來。

### 2. 看不懂的線或物件

**每一支箭頭**

| # | 從 | 到 | 種類 | 標籤 | 懂不懂它為什麼存在 |
|---|---|---|---|---|---|
| 1 | 12 cache_invalidate | 14 frame_write | 橘色實線，data | "cache[f]: old lines dropped first" | 半懂。意思懂（先丟舊的 cache lines 再寫入），但標籤講的是先後順序，不是一個值；依圖例它應該是 rule。03、05、09 的 cache 先後關係都畫虛線 |
| 2 | 13 sw_decode | 14 frame_write | 橘色實線，data | "page" | 懂。解出來的頁面內容要複製進 frame |
| 3 | 14 frame_write | 15 sw_clean | 橘色實線，data | "frame[f]" | 懂。寫完的 frame 才能寫回 DRAM |
| 4 | 13 sw_decode | 16 note_hw | 橘色實線，data | "decode result: read if the answer was bad stream" | 懂，配合底下藍字才懂：bad stream 要看軟體解不解得開才算 strike |
| 5 | 13 sw_decode | 17 cot_clear | 黑色虛線，rule | "rule: stored copy needed until decoded" | 懂。解碼完成之前不能清掉壓縮資料的紀錄 |
| 6 | 13 sw_decode | 19 set_present | 黑色虛線，rule | "rule: PRESENT only after a good decode" | 懂 |
| 7 | 13 sw_decode | 22 note_fresh | 橘色實線，data | "decode result" | 不懂。note_fresh 的內文只有 fresh[t]、fresh_n 的加減，看不出它拿解碼結果做什麼。04 的 note_fresh 是掛 "completion, from step 11" 的旗標，同樣沒說原因 |
| 8 | 15 sw_clean | 20 pte_map | 黑色虛線，rule | "rule: frame content before valid" | 懂。和 05 的 "zeros before valid" 同一個道理 |
| 9 | 17 cot_clear | 18 release_chunks | 黑色虛線，rule | "rule: entry first" | 半懂。順序懂，但 COT entry 清成 0 之後，要釋放的 5 個 chunk 編號從哪裡來，圖上沒交代 |
| 10 | 19 set_present | 21 wake_page | 黑色虛線，rule | "rule: PRESENT first" | 懂 |

**旗標（跨張的箭頭）**

| 旗標 | 掛在哪 | 懂不懂 |
|---|---|---|
| "rule, from step 11" | 12 左邊 | 懂，03 的 11 到 12 確實是一支 rule 虛線 |
| "completion: bus error or bad stream, from step 11" | 13 左邊 | 懂 |
| "free_top, from step 4" | 23 右邊 | 懂，和 04 的 wake_check 同一面旗 |

**不確定的物件與畫法**

- 箭頭 4 穿過灰框上緣的地方，看起來像多了一個小菱形或重複的箭頭頭。不確定是「有條件」的記號還是畫的時候留下的。
- 箭頭 6 和箭頭 7 看起來是從 13 的黃色便條 "not measured yet" 出發，不是從方塊本身。乍看會以為是便條在指東西。
- 13 一口氣放出五支箭頭（往 14、16、17、19、22），13 下方那一帶線很擠，要一支一支順著看才分得開。
- "cache[f]" 這個寫法只在這張出現，01 的表格清單裡沒有它，容易被當成一張 kernel 的表。
- "stored copy" 指的是 chunk pool 裡的壓縮資料還是 cot[h]，沒有明講。箭頭指向 cot_clear，所以我猜兩者都算。
- 灰框是鎖的範圍，但掛鎖和標籤放在框內左下角。其他張都放在框的上緣，所以我是看到左下角才確定整個灰框是 lock hold B。
- 框內的編號順序是 16、17、19、22、20（上排），18、21、23（下排）。22 排在 20 左邊，從左讀到右時編號會跳。
- 沒有畫開鎖的掛鎖，也沒有 "all done, unlock" 的出口箭頭（04 和 06B 都有），改用一行藍字交代。

**圖上兩處文字互相打架的地方**

- step 16 的內文是有 strike 的路徑（"strikes + 1; at 3 strikes: lz4_off = 1"），便條卻寫 "5 instr, 0 lines; measured on the no-strike path"。便條自己有交代，不算錯，但讀者會問這 5 個指令在這條路徑上還準不準。這張便條也是整張唯一沒寫 cycles 的指令便條。
- step 14 的便條寫 "64 lines written"，但這 64 條沒有算進任何 new lines，cycles 也只有 791，沒有範圍。05 的 zero_frame 有寫原因（"64 lines zeroed without reading DRAM"），06A 沒寫。
- 箭頭 4 的標籤暗示 note_hw 知道 LZ4 HW 的回答是哪一種，但 16 上沒有掛 "completion, from step 11" 的旗標，那面旗只掛在 13 上。
- 副標題用 "answer"，旗標用 "completion"，指的是同一個東西。

沒有找到真正互相矛盾（兩處說相反的事）的文字。

### 3. 圖說的一句話

LZ4 HW 在 step 11 回報失敗之後，kernel 的 faulting thread 不拿鎖先用軟體把頁面解出來、寫進 frame 並寫回 DRAM，然後在第二次拿 mm_lock 的期間記一次 strike、清掉壓縮紀錄、把頁面標成 PRESENT 並接上 page table，使用者的程式照常繼續跑。

### 4. 畫面和 Cost 那一條一不一致

**一致。** Cost 那一條的每個數字都和畫面對得上，沒有說相反的事。

驗算：

| Cost 那一條的說法 | 驗算 | 結果 |
|---|---|---|
| 791 instr copy | step 14 的便條 791 | 對 |
| 119 instr in lock hold B | 5 + 4 + 3 + 19 + 6 + 80 + 2 = 119（wake_page 不計） | 對 |
| 4 new lines in lock hold B | 0 + 0 + 0 + 2 + 1 + 1 + 0 = 4 | 對 |
| 1012 instr = 39 + 51 + 791 + 119 + 12 | 加總 1012 | 對 |
| 12 for two lock holds | (4 + 2) × 2 = 12 | 對 |
| Decode and cache maintenance are not measured | 13 "not measured yet"，12 和 15 "time unknown" | 對 |

只靠 06A 這一張驗不出來的數字：

- 39（lock hold A）：要看 02，14 + 12 + 6 + 7 = 39，對。
- 51（job）：要看 03，26 + 13 + 12 = 51，對。
- 1212 to 2112 cycles：要用 11 的公式和 03 的兩次 register write。1012 + 2 × 50 + 100 = 1212，1012 + 100 + 10 × 100 = 2112，對。10 條 new lines 是 02 的 4 加 03 的 2 加這張的 4，和 11 的表一致。
- 791 本身：只有一張便條，沒有可以交叉驗的來源。

兩個不算不一致、但 Cost 那一條沒帶到的但書：

- 119 裡的 5 來自 note_hw，是在 no-strike 路徑上量的，Cost 那一條沒有重提。
- Cost 那一條沒有給這一張自己的 cycles 範圍，只給整個 scenario 的。

### 5. 困惑指數

**2。** 主線（HW 失敗、軟體解碼、寫進 frame、拿鎖做收尾）一看就順；扣一分是因為 13 放出的五支箭頭擠在一起，而且箭頭 1 和箭頭 7 的型別或理由要想一下。

### 6. 可疑的錯字或多餘文字

沒有看到亂碼或拼錯的字。可疑的只有格式和用語：

- 標題 "LZ4 HW Says Failed" 英文不太順，但意思清楚。
- 副標題 "steps 1 to 11  as on sheets" 中間看起來像多一個空格。
- step 16 的便條用分號，且沒有 cycles，和其他便條的 "N instr, N lines, N cycles" 格式不同。
- step 14 的便條 "64 lines written" 是別張沒有的寫法。
- "lz4_off" 只在這張出現，01 的表格清單裡沒有。

## 跨圖的觀察

### 樣式一不一致

大致一致，沒有走樣到認不出是同一組：

- 方塊（白底粗黑框圓角）、橘色圓形步驟編號、黃色成本便條、藍框旗標、右上角圖例、底部帶藍色標籤的結論條，都和其他張相同。
- 橘色實線和黑色虛線的畫法與圖例一致。

和其他張不同的地方：

- 鎖的標示位置。02、04、05、06B、07、08、10 都把掛鎖和 "kernel, mm_lock held" 放在框或括號的上緣；06A 放在灰框內左下角，掛鎖也比較大、是灰底的。
- 沒有開鎖的掛鎖和出口箭頭（04、06B 有）。
- 沒有任何人物。02、04、05、06B 都有 user SW 的火柴人；姊妹場景 06B 畫了一個崩潰的 user SW，06A 這個「救回來」的結局卻只有一行字。
- 13 的箭頭從黃色便條出發，其他張的箭頭都從方塊邊緣出發。

### 06A 指到別張的步驟編號

06A 自己寫出來的指向全部找得到、對得起來：

| 06A 的說法 | 在哪一張 | 對不對 |
|---|---|---|
| "steps 1 to 11 as on sheets 2 and 3" | 02 有 1 到 6，03 有 7 到 12 | 對 |
| "rule, from step 11" | 03 的 11 cpl_read 到 12 是 rule 虛線 | 對 |
| "completion: bus error or bad stream, from step 11" | 03 的 11 cpl_read 讀 cpl_ring 16 B | 對得上步驟，但 03 上完全沒提 bus error 或 bad stream，11 的旗標也只寫 "to sheet 4" |
| "free_top, from step 4" | 02 的 4 take_frame，有一面 "free_top" 的旗 | 對 |
| "24 eret and 25 rerun, drawn as steps 19 and 20 on sheet 4" | 04 的 19 eret、20 rerun | 對 |
| Cost 的 39、51、119 | 02、03、04（RW page 119 instr、4 new lines） | 對 |
| 整個 scenario 的 1012、10 lines、1212 to 2112 | 11 的 fault_rescue 那一列 | 對 |

反方向會撞號：02 和 03 的旗標用的是 fault_ro 的編號。02 寫 "free_top, to step 18"，在 06A 上 18 是 release_chunks，wake_check 是 23。03 寫 "rule, to step 15"，在 06A 上 15 是 sw_clean，pte_map 是 20。06A 自己只引用 11 以前的共用編號，所以沒出錯，但從 02、03 順著旗標找過來的讀者會對不上。這是 02、03 的事，不是 06A 畫錯。

### 06A 與 06B 之間

同名步驟沒有互相矛盾，兩張合起來是一套講得通的規則：

- sw_decode：06A 是 "decode into a kernel buffer"（成功），06B 是 "decode: the stream is damaged"（失敗）。兩張都掛 "not measured yet"。
- note_hw：06A 是 "strikes + 1"，06B 是 "strikes = 0, the LZ4 HW was right, no strike"。這和 06A 底下那行藍字完全對得上，也和 04、10 成功時的 "strikes = 0" 一致。
- step 12：06A 把它重畫一次（因為它接到 frame_write），06B 用一面旗寫 "step 12, cache_invalidate, sheet 3, must be done too"。處理方式不同，但不矛盾。

各種組合落在哪一張：

| LZ4 HW 的回答 | 軟體解碼 | 落在哪一張 | strike |
|---|---|---|---|
| 成功 | 不需要 | 03 加 04 | strikes = 0 |
| bus error | 成功 | 06A | + 1（藍字："always counts"） |
| bad stream | 成功 | 06A | + 1（要讀 decode result） |
| bad stream | 失敗 | 06B | strikes = 0，頁面 LOST，kill |
| bus error | 失敗 | **找不到** | 依 06A 的藍字推測是 + 1，頁面大概也是 LOST，但沒有任何一張這樣寫 |

前四種我讀得出來。第五種（bus error 而且軟體也解不開）兩張都沒涵蓋，11 的八個 scenario 裡也沒有它。

### 連著看 02、03、06A

故事線順。02 的 lock hold A 拿到 f 和 COT entry，03 送出 job 並讀回 completion，06A 從 12 接下去。兩個小顛簸：

- 03 的 step 9 畫的是成功的樣子（"check CRC-32, write frame[f]"），step 11 也沒提回答有幾種。讀者要靠 06A 的副標題自己把 03 的結果換成失敗。分岔點在 03 上沒有任何記號。
- 02 和 03 的副標題只寫 fault_ro 和 fault_rw，沒有提 fault_rescue 也用這兩張。

另外，依 03 的旗標慣例，06A 的 sw_decode 應該需要 step 5 的 COT entry（chunk 編號、length、CRC-32）才能讀 chunks 和檢查 CRC，但 13 上沒有掛 "COT entry, from step 5" 的旗。06B 也沒掛，兩張姊妹圖彼此一致，但和 03 的 desc 不一致。

## 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與 Cost 那一條是否一致 |
|---|---|---|---|
| 06A | 2 | 是（全靠文字標籤，圖上沒有畫人或機器） | 一致（加總全部驗算得過） |

## 要不要重生 06A

**不用重生。** 四個門檻都沒碰到：

- 困惑指數 2，低於 3。
- 角色清楚：每一步是誰做的、有沒有拿鎖，文字標籤都交代了。
- 十支箭頭的方向都是從先做的步驟指向後做的步驟，和故事一致。
- Cost 那一條與畫面一致，加總全對。

## 不到重生程度的小問題

依我認為的重要程度排列。

1. **箭頭 12 到 14 的型別。** 畫成橘色 data，標籤卻是先後順序的說法（"old lines dropped first"）。同一組圖的 cache 先後關係（03 的 11 到 12、05 的 zero_frame 到 pte_map、09 的 "clean before doorbell"）都是黑色虛線 rule。我沒有原始資料可對，請對照確認它該是哪一種；若該是 rule，這一支就是型別畫錯，值得單獨修。
2. **箭頭 13 到 22（"decode result" 到 note_fresh）沒說理由。** 看不出 note_fresh 拿解碼結果做什麼。另外 cot_clear 在 04 掛的是 "completion, from step 11"（data），在 06A 變成 rule，兩張的型別不同。
3. **note_hw 的便條。** 寫 "measured on the no-strike path"，但方塊內容是有 strike 的路徑；便條沒寫 cycles；Cost 那一條把這 5 個指令加進 119 時沒有重提這個但書。
4. **frame_write 的 "64 lines written"。** 沒有算進 new lines，也沒說為什麼。05 的 zero_frame 有寫 "without reading DRAM"，這張可以比照補一句。
5. **少了兩面旗。** note_hw 沒有 "completion, from step 11"（箭頭標籤卻暗示它知道回答是哪一種）；sw_decode 沒有 "COT entry, from step 5"。
6. **cot_clear 先於 release_chunks。** COT entry 清成 0 之後，要釋放的 5 個 chunk 編號從哪裡來，圖上沒交代。04 也有同樣的問題。
7. **鎖的標示位置和其他張不同。** 掛鎖與標籤在灰框內左下角，不在上緣；沒有開鎖的掛鎖和出口箭頭。
8. **沒有任何人物。** user SW 和 LZ4 HW 都只存在於文字裡；06B 有畫 user SW 的下場，06A 的好結局沒有畫面。
9. **13 的箭頭太擠。** 五支箭頭從同一個方塊放出，其中兩支看起來是從黃色便條出發。
10. **框內編號的排列。** 上排是 16、17、19、22、20，22 排在 20 前面。
11. **bus error 加上軟體解碼失敗的組合沒有任何一張涵蓋。** 這是 06A 與 06B 合起來的缺口，不是 06A 單張的錯。
12. **用語。** "answer" 和 "completion" 混用；"cache[f]"、"lz4_off"、"stored copy" 是這張才出現的新詞。
13. **Cost 那一條沒有給這一張自己的 cycles 範圍。**
14. **標題 "Says Failed" 的英文略不順；副標題疑似多一個空格。**

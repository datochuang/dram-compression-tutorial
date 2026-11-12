# 冷讀驗收報告：第六批（06A、06B）

- 日期：2026-11-12
- 方法：只給圖、不給提示詞的冷讀（只讀十二張 PNG，沒有讀任何提示詞、規格或其他文字檔）
- 驗收範圍：第六批的 06A 與 06B。其餘十張（01 到 05、07 到 11）為已定稿的上下文，只用來對照，不逐張記錄。

---

## 一、06A：LZ4 HW Says Failed, the Software Rescue Works

以下第 1 到 3 題是遮住底部 Cost 那一條時的讀法。

### 1. 人物與機器

這一張沒有畫任何人物或機器圖示。

| 角色 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| kernel 的 faulting thread（不持鎖段） | 左上藍字 "kernel, the faulting thread, no lock held" | 做 12 cache_invalidate、13 sw_decode、14 frame_write、15 sw_clean | 把壓縮資料用軟體解回來、抄進 frame、把 cache 整理乾淨 |
| kernel（持鎖段） | 鎖頭加 "kernel, mm_lock held for both rows: lock 4 instr, unlock 2 instr" | 做 16 到 23 八個步驟 | 更新各張表、喚醒等待者 |
| OS | 只出現在 21 wake_page 的內文 "OS: wake threads waiting for page h" | 喚醒 thread | 無標籤的獨立角色，沒有自己的顏色或圖示 |
| LZ4 HW | 只出現在標題與 16 note_hw 的 "lz4_off" | 圖上沒畫 | 它的「回答」只以左側藍色旗標 "completion: failed, from step 11" 出現 |
| user SW | 圖上沒畫，只在底部藍字 "24 eret and 25 rerun" 間接提到 | 無 | 無 |

角色不清楚的地方：沒有。全張都是 kernel 的步驟（白底方塊），和 07、08、10 那幾張沒畫人物的做法一樣。

### 2. 看不懂的線或物件

逐支箭頭：

| # | 從 | 到 | 種類 | 標籤 | 懂不懂它為什麼存在 |
|---|---|---|---|---|---|
| 1 | 12 cache_invalidate | 14 frame_write | data（橘實線） | cache[f] | **不懂**。invalidate 不產生任何值；"cache[f]" 這個名字在 01 的表格清單裡不存在，其他張也沒出現過。看起來是「先 invalidate 才能寫」的順序，照圖例應該是 rule。 |
| 2 | 13 sw_decode | 14 frame_write | data | page | 懂。解出來的 4096 B 要抄進 frame。 |
| 3 | 14 frame_write | 15 sw_clean | data | frame[f] | 懂。寫完才能 write back 到 DRAM。 |
| 4 | 13 sw_decode | 16 note_hw | data | decode result | **半懂**。strikes 要不要加一取決於軟體解不解得出來，這說得通；但底部藍字寫 "note_hw needs the decode result only if the answer was bad stream"，而這一張副標寫 "the answer at step 11 is failed"。照字面讀，這支箭頭在這個場景不該存在。 |
| 5 | 13 sw_decode | 17 cot_clear | rule（黑虛線） | rule: good decode first | 懂。解成功才能把 COT entry 清掉。但疑問：同樣是「解成功才做」，為什麼這支是 rule，而第 7 支是 data？ |
| 6 | 13 sw_decode | 19 set_present | rule | rule: page back first | **半懂**。"page back" 讀起來像「頁面已經回到 frame」，那是 14 或 15 的事，但箭頭起點是 13。照圖，set_present 可以在 frame_write 之前做。對照 04 的 14 set_present 是 "rule, from step 11"，起點落在 13 說得通，問題在標籤用字。 |
| 7 | 13 sw_decode | 22 note_fresh | data | decode result ok | **半懂**。note_fresh 的內文沒有用到 decode 的值；和第 4 支同一個來源卻叫不同名字（"decode result" 對 "decode result ok"），不確定是不是兩個不同的值。 |
| 8 | 15 sw_clean | 20 pte_map | rule | rule: frame content before valid | 懂。frame 內容落到 DRAM 之後才能把 pte 設成 valid。 |
| 9 | 17 cot_clear | 18 release_chunks | rule | rule: entry first | 懂（猜 "entry" 是 COT entry）。 |
| 10 | 19 set_present | 21 wake_page | rule | rule: PRESENT first | 懂。 |

旗標：

- "rule, from step 11" 掛在 12：懂，對得上 03 的 11 到 12 那支 rule 箭頭。
- "completion: failed, from step 11" 掛在 13：懂。
- "free_top, from step 4" 掛在 23 wake_check：懂。

其他讓我停下來的地方：

- **13 sw_decode 一口氣射出六支箭頭**（兩支往 14 與 22 的橘線、往 16 的橘線、兩支虛線、加上往 14 的 "page"），其中三支從方塊右下角幾乎同一點出發。"rule: good decode first" 這個標籤夾在兩支虛線中間，要靠位置猜它屬於往 17 的那一支。
- 往 22 的橘色長弧線與往 19 的虛線，都穿過鎖頭那一行文字（"kernel, mm_lock held for both rows..."）附近，那一帶很擠。
- 16 note_hw 的便條 "5 instr, 0 lines: measured for strikes = 0"：不確定是「strikes 原本是 0 時量的」還是「量的是 04 那種 strikes = 0 的寫法，這裡借用」。這一步明明是 strikes + 1。
- 14 frame_write 的便條 "791 instr, 791 cycles, 64 lines written"：格式和其他便條（N instr, N lines, cycles 範圍）不同。"64 lines written" 會不會算成 64 條 new cache line？05 的 zero_frame 有寫 "64 lines zeroed without reading DRAM" 交代，這裡沒有。
- 持鎖區上排的編號順序是 16、17、19、22、20，22 排在 20 前面。04 也是不照編號排，所以不算走樣，但眼睛要跳。
- "failed" 與 "bad stream" 是兩種不同的回答，還是 "failed" 是總稱？只看這一張分不出來，要到 06B 才知道有 "bad stream" 這個回答。

### 3. 圖說的一句話

LZ4 HW 回報 failed 之後，faulting thread 在不持鎖的情況下用軟體重新解壓、把 4096 B 抄進 frame 並整理 cache，然後進一次 mm_lock 做和正常 RW page fault 一樣的八步收尾，只是 note_hw 改成給 LZ4 HW 記一次 strike。

### 4. 畫面與 Cost 那一條

Cost 寫："This sheet: 791 instr copy + 119 instr and 4 new lines in lock hold B. Whole scenario: 1012 instr = 39 lock hold A + 51 job + 791 + 119 + 12 for two lock holds; 1212 to 2112 cycles. Decode and cache maintenance are not measured."

判定：**一致**（數字全部對得起來），但有兩處用字落差。

驗算：

- 持鎖段便條加總：5 + 4 + 80 + 3 + 6 + 19 + 2 = 119 instr（wake_page 不計）。對。
- 持鎖段 new lines：release_chunks 1 + pte_map 1 + note_fresh 2 = 4。對。
- 791 instr copy：等於 14 frame_write 的便條。對。
- 39 + 51 + 791 + 119 + 12 = 1012。對。
- "Decode and cache maintenance are not measured"：對得上 13 的 "not measured yet" 與 12、15 的 "time unknown"。

只靠這一張驗不出來的：

- 39（lock hold A）要看 02；51（job）要看 03（26 + 13 + 12）。
- 12 = 兩次 lock hold 各 6 instr：這一張只看得到一次 lock 4 + unlock 2，另一次在 02。
- 1212 到 2112 cycles：要用 11 的公式（instr + 每次 register write 50 + 每條 miss 的 line 100）以及整個場景 10 條 new lines、2 次 register write 才算得出來。用 11 的公式驗算：1012 + 100 + 100 = 1212，1012 + 100 + 1000 = 2112，與 11 的 fault_rescue 那一列相符。

用字落差：

- Cost 說 "lock hold B"，但畫面上那一區只寫 "mm_lock held for both rows"，沒有 "B" 這個名字，要從 04 推。
- 119 裡面的 5 instr（note_hw）便條自己說是 "measured for strikes = 0"，Cost 那一條沒有帶這個但書。

### 5. 困惑指數

**3**。主線一看就懂，但這組圖的重點是「哪些步驟真的相依」，而 sw_decode 射出的那幾支箭頭種類不一致、標籤擠在一起，底部藍字又和其中一支箭頭互相打架。

### 6. 可疑的錯字或多餘文字

- 副標 "Scenario" 的前半（"Sce"）與第一個 "steps" 底下有多出來的底線，像超連結；其他十張的副標都沒有。
- 鎖頭那一行 "mm_lock" 的 "mm" 底下有多出來的底線。
- "cache[f]"：疑似用錯名字，或應改成 rule。
- "decode result" 與 "decode result ok"：同一來源兩種寫法。
- "5 instr, 0 lines: measured for strikes = 0"：語意不明。
- 底部 "Cost" 標籤格看起來是白底，其他張（含 06B）同位置的標籤格是淺藍底。

---

## 二、06B：LZ4 HW Says Bad Stream and It Is Right: A Lost Page

### 1. 人物與機器

| 角色 | 標籤 | 在做什麼 | 看起來在意什麼 |
|---|---|---|---|
| 火柴人 | "user SW"（右下） | 坐在桌前、雙手舉高、表情驚慌 | 自己要被結束掉了；位置緊貼 18 kill 下方，讀得出因果 |
| kernel 的 faulting thread（不持鎖） | 左側藍字 "kernel, the faulting thread, no lock held" | 做 13 sw_decode | 用軟體再解一次，確認 stream 真的壞了 |
| kernel（持鎖） | 鎖頭加 "kernel, mm_lock held: lock 4 instr, unlock 2 instr" | 做 14 note_hw、15 put_frame、16 set_lost、17 wake_page | 記錄 HW 沒有錯、把 frame 還回去、把頁面標成 LOST |
| OS | 只在 17 與 18 的內文（"OS: wake threads..."、"OS: end this user SW"） | 喚醒等待者、結束 user SW | 沒有獨立圖示 |
| LZ4 HW | 只在標題與 14 的內文 "the LZ4 HW was right, no strike" | 圖上沒畫 | 它的回答以旗標 "completion: bad stream, from step 11" 出現 |

角色不清楚的地方：沒有。

### 2. 看不懂的線或物件

逐支箭頭：

| # | 從 | 到 | 種類 | 標籤 | 懂不懂 |
|---|---|---|---|---|---|
| 1 | 13 sw_decode | 14 note_hw | data（橘實線） | decode result | 懂。軟體也解不出來，才知道 HW 說對了。 |
| 2 | 13 sw_decode | 15 put_frame | rule（黑虛線） | rule: no decoder can fill the frame | 懂。兩種解法都失敗，frame 才可以還回去。 |
| 3 | 13 sw_decode | 16 set_lost | rule | rule: both decoders failed first | 懂。"both decoders" 猜是 LZ4 HW 與軟體 decoder。 |
| 4 | 16 set_lost | 17 wake_page | rule | rule: LOST first | 懂。 |
| 5 | 開鎖圖示 | 18 kill | 虛線 | all done, unlock | 懂，和 04 的 "all done, unlock, return" 同一種畫法。 |

旗標：

- "completion: bad stream, from step 11" 掛在 13：懂。
- "step 12, cache_invalidate, sheet 3, must be done too" 掛在 18 kill 上方，尖角指著 kill：**不確定**。是說 kill 之前必須先做完 step 12，還是只是提醒這個場景也有 step 12？副標已經寫 "steps 1 to 12 as on sheets 2 and 3"，這一格看起來重複；掛在 kill 上又像在暗示一條順序規則，但沒有用箭頭畫出來。

其他讓我停下來的地方：

- 第 1 支橘色箭頭的下半段筆畫有重疊，看起來像實線旁邊疊了一小段斷續線，第一眼會懷疑它是不是半支虛線。
- 第 1 與第 3 支的標籤是沿著箭頭斜著寫的（"decode result"、"rule: both decoders failed first"），其他十張的箭頭標籤大多是水平的。
- 14、15、16 之間沒有箭頭，照圖例是任意順序，讀得懂。
- 沒有 cot_clear 與 release_chunks：頁面標成 LOST 之後，chunks 與 COT entry 留著不放嗎？圖上沒說。這是讀者會問的問題，不是畫錯。
- 17 wake_page 喚醒的 thread 和 18 被 kill 的 user SW 是什麼關係，圖上沒說。
- 畫面下半部（17 以下到 Cost 之間）有一大片空白。

### 3. 圖說的一句話

LZ4 HW 回報 bad stream、軟體再解一次也確認 stream 壞了，kernel 在一次持鎖內把 strikes 歸零、把 frame 還回 free stack、把頁面標成 LOST 並喚醒等待者，解鎖後由 OS 結束這個 user SW。

### 4. 畫面與 Cost 那一條

Cost 寫："123 instr and 6 new lines, 323 to 823 cycles: 39 lock hold A + 51 job + 21 lock hold B + 12 for two lock holds; the decode is not measured. The frame goes back to the free stack; the page is now LOST."

判定：**一致**。

驗算：

- 持鎖段便條加總：5 + 13 + 3 = 21 instr（wake_page、kill 不計）。對。
- 39 + 51 + 21 + 12 = 123。對。
- 這一張的 new lines 是 0（三張便條都寫 0 lines），所以 6 條全部來自前面：02 的 4 條加 03 的 2 條。對。
- 後半句 "The frame goes back to the free stack; the page is now LOST" 對得上 15 put_frame 與 16 set_lost。
- "the decode is not measured" 對得上 13 的 "not measured yet"。

只靠這一張驗不出來的：

- 39、51、12 與 6 new lines 的來源（要看 02、03）。
- 323 到 823 cycles：用 11 的公式驗算，123 + 100 + 100 = 323，123 + 100 + 600 = 823，與 11 的 fault_lost 那一列相符。

用字落差：Cost 說 "lock hold B"，畫面上那一區沒有寫 "B"。

### 5. 困惑指數

**2**。一條線從 sw_decode 分到三個持鎖步驟再到 kill，火柴人的反應把結局講完了；只有掛在 kill 上的那一格 step 12 旗標要停下來想。

### 6. 可疑的錯字或多餘文字

- 旗標裡 "must" 底下有底線，其他張沒有這種強調寫法。
- "step 12, cache_invalidate, sheet 3, must be done too" 與副標 "steps 1 to 12 as on sheets 2 and 3" 重複，掛的位置又容易誤導。
- 沒有發現拼字錯誤。

---

## 三、跨圖觀察

### 樣式是否和其餘十張一致

大致一致，沒有走樣到認不出是同一組：

- 左上橘色編號方塊（6A、6B）、橘色標題底線、藍色副標、右上圖例三行，與其他張相同。
- 步驟方塊（白底圓角、橘色圓形編號、粗體步驟名）、黃色便條、藍色旗標、橘實線與黑虛線，與其他張相同。
- 06B 的火柴人與 "user SW" 標籤，和 02、04、05 同一種畫法；表情換成驚慌，符合情節。

小走樣：

- 06A 的持鎖區是「外層灰色圓角框，裡面再一條灰色括號」雙層；04 是括號在框外，07 是標籤嵌在框線上。06B 的持鎖標示是細線加兩端短豎線，比其他張的粗灰括號細。
- 06A 底部 "Cost" 標籤格看起來是白底，06B 與其他張是淺藍底。06A 的 Cost 文字是兩行小字，比其他張的結論條擠。
- 06A 有三處多出來的底線（"Scenario"、"steps"、"mm"），06B 有一處（"must"）。
- 06B 有斜著寫的箭頭標籤。

### 指到別張的步驟編號對不對得起來

| 06A / 06B 上寫的 | 在別張找到的 | 結果 |
|---|---|---|
| 06A "steps 1 to 11 as on sheets 2 and 3" | 02 有 1 到 6，03 有 7 到 12 | 對 |
| 06A 的 12 cache_invalidate，"rule, from step 11" | 03 的 12 cache_invalidate，11 到 12 有一支 rule 箭頭 | 對，名稱、內文、便條都相同 |
| 06A、06B "completion: ..., from step 11" | 03 的 11 cpl_read | 對得上步驟；但 03 的 cpl_read 只寫 "compare the tag"，沒有提到會有 ok、failed、bad stream 這種回答，03 的旗標也只寫 "to sheet 4" |
| 06A "free_top, from step 4" | 02 的 4 take_frame，旗標 "free_top, to step 18" | 來源對；02 那一頭寫的 18 是 04 的編號，06A 的 wake_check 是 23 |
| 06A "24 eret and 25 rerun, drawn as steps 19 and 20 on sheet 4" | 04 的 19 eret、20 rerun | 對 |
| 06B "steps 1 to 12 as on sheets 2 and 3" | 02、03 | 對 |
| 06B "step 12, cache_invalidate, sheet 3" | 03 的 12 cache_invalidate | 對 |
| 06A、06B Cost 的 "39 lock hold A"、"51 job" | 02 的結論條 39 instr；03 的 26 + 13 + 12 = 51 | 對 |
| 06A Cost 的 "119 instr and 4 new lines in lock hold B" | 04 的結論條 "RW page: 119 instr and 4 new lines" | 對，八個步驟與便條數字逐一相同 |
| 06A、06B 的整場景數字 | 11 的 fault_rescue（1012、10、1212 to 2112）與 fault_lost（123、6、323 to 823） | 對 |
| 06B 的 15 put_frame "13 instr, 0 lines" | 10 的 17 put_frame 相同；07 的 5 put_frame 是 "1 line" | 可接受，10 有藍字說明已在 lock hold A 碰過的 line 不再算 |

另外一處種類不一致：04 的 cot_clear 用的是 "completion, from step 11"（data 性質的旗標），06A 的 cot_clear 用的是 "rule: good decode first"。同一個步驟、類似的前提，一張當 data、一張當 rule。

### 06A 與 06B 之間同名步驟有沒有矛盾

- **sw_decode（兩張都是 13）**：06A "decode into a kernel buffer"（成功），06B "decode: the stream is damaged"（失敗）。同一個步驟的兩種結果，不矛盾。便條都是 "not measured yet"，一致。
- **note_hw**：06A 是 "strikes + 1; at 3 strikes: lz4_off = 1"，06B 是 "strikes = 0, the LZ4 HW was right, no strike"，04 與 10 是 "strikes = 0"。合起來讀是：HW 說失敗但軟體解得出來，HW 記一次 strike；其餘歸零。不矛盾，三處互相補完。
- **wake_page**：內文與便條相同，一致。
- **真正的疑點在 "failed" 與 "bad stream"**：06A 的回答是 "failed"，06B 的回答是 "bad stream"，06A 底部藍字又說 note_hw 只有在回答是 bad stream 時才需要 decode result。照這三句話，06A 這個場景（回答是 failed）裡 13 到 16 的 data 箭頭不該存在；或者 06A 其實同時涵蓋「HW 說 bad stream 但說錯了」這個情況，只是副標沒有講。兩張合起來只明講了四種組合裡的兩種，剩下兩種（failed 而軟體也解不出來、bad stream 而軟體解得出來）落在哪一張，讀者要自己猜。

### 連著看故事線順不順

- **02、03、06A**：順。02 做完 1 到 6，03 做 7 到 12，06A 從 12 接手、把 12 重畫一次並加上 13 到 23，編號沒有斷。唯一的顛簸是 03 完全沒有預告 step 11 會有不同的回答，分岔是到 06A 的副標才第一次出現；03 的旗標只指向 sheet 4。
- **02、03、06B**：順，而且比 06A 更直接，13 接在 12 後面，只有一段持鎖。掛在 kill 上的 step 12 旗標是唯一不順的地方。
- 06A 重畫了 12，06B 沒有重畫而是用旗標帶過，兩張處理同一個步驟的方式不同，但不造成誤讀。

### 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與 Cost 那一條是否一致 |
|---|---|---|---|
| 06A | 3 | 是 | 一致（加總全部驗得過；"lock hold B" 這個名字畫面上沒有） |
| 06B | 2 | 是 | 一致 |

### 建議重生

**06A**（困惑指數 3，且有一支箭頭與圖上自己的文字矛盾）：

1. 13 到 16 的 data 箭頭 "decode result"，與底部藍字 "only if the answer was bad stream"、副標 "the answer at step 11 is failed" 三者互相打架。要嘛改藍字，要嘛把箭頭畫成有條件的，要嘛在副標講清楚這一張涵蓋哪幾種回答。
2. 12 到 14 的 "cache[f]" 畫成 data，但 invalidate 不產生值，名字也不在 01 的表裡；讀起來應該是 rule。
3. 13 往下的四支線（16、17、19、22）種類不一致：17 是 rule、22 是 data，兩者的前提看起來一樣；"decode result" 與 "decode result ok" 兩種寫法。
4. 13 到 19 的標籤 "page back first" 與起點不搭。
5. sw_decode 右下角三支線擠在一起，標籤歸屬要猜，兩支線穿過鎖頭那一行字。
6. 順手處理：三處多餘底線、Cost 標籤格底色、note_hw 便條的用字。

06B 不需要重生。

### 不到重生程度的小問題

06A（若不重生，也建議改）：

- 14 frame_write 便條 "64 lines written" 沒有交代為什麼不算 new lines（05 有 "without reading DRAM"）。
- 16 note_hw 便條 "measured for strikes = 0" 語意不明，Cost 的 119 也沒有帶這個但書。
- Cost 用了 "lock hold B"，畫面的持鎖區沒有這個名字。
- 持鎖區上排編號順序 16、17、19、22、20。

06B：

- "step 12, cache_invalidate, sheet 3, must be done too" 這格旗標掛在 18 kill 上，像一條沒畫出來的順序規則；與副標重複。建議移到副標旁邊，或改畫成一支 rule 箭頭。
- "must" 的底線是其他張沒有的強調寫法。
- 13 到 14 的橘色箭頭下半段筆畫重疊，像疊了一小段虛線。
- 兩個斜著寫的箭頭標籤，和其他張的水平標籤不一樣。
- 持鎖區上方的標示線比其他張的灰括號細。
- Cost 用了 "lock hold B"，畫面上沒有這個名字。
- 沒有交代 LOST 頁面的 chunks 與 COT entry 去向（讀者會問，不一定要畫）。
- 畫面下半部留白偏多。

跨圖（不屬於 06A、06B 本身，僅記錄）：

- 03 的 11 cpl_read 沒有提到「回答」有 ok、failed、bad stream 之分，旗標也只指向 sheet 4；06A、06B 的分岔在 03 上沒有路標。
- 02 的 4 take_frame 旗標 "free_top, to step 18" 用的是 04 的編號，對 06A（wake_check 是 23）不成立。
- 04 的 cot_clear 以 completion（data）為前提，06A 的 cot_clear 以 rule 為前提，種類不一致。

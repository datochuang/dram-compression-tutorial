# Kernel actions 白板圖冷讀驗收報告（gen3）

- 日期：2026-11-12
- 方法：只給圖、不給提示詞的冷讀。只用 Read 讀十一張 PNG，沒有讀任何 .md、.txt、.json 或提示詞。
- 讀的是第二次冷讀的十一張（01 到 11），位置在 scratchpad 的 `coldread-gen3/01.png` 到 `11.png`。
- 限制說明：圖是整張一次載入的，沒辦法真的把底部結論遮起來。每張的第 3 項「圖說的一句話」只根據標題、方塊、箭頭寫，寫完才拿底部結論來比對。
- 成本換算依第 1 張的 cost model：1 instr = 1 cycle，1 條新 cache line 最多 100 cycles，1 次 register write = 50 cycles。

---

## 第 1 張：Where the Kernel's Tables Live

1. **人物與機器**
   - 沒有人物。
   - 左側一條記憶體地圖（無標籤說它是 DRAM，只有位址 0x80000000 到 0xA0000000），分五段：pinned area 56 MiB、HRT area 36 MiB not compressed、COT area 5 MiB、chunk pool 275 MiB（斜線）、frame area 140 MiB。
   - 綠色方塊加齒輪：「LZ4 HW registers：JOB_TAIL, CPL_HEAD」。它是機器，但沒有畫出它在哪裡、和記憶體地圖的關係。
   - 黃色便利貼：「Cost model on the next sheets」。
2. **看不懂的線或物件**
   - pinned area 拉一條線到「kernel mem, in the pinned area」方塊，COT area 拉一條線到「COT area」方塊，兩條都沒有箭頭，讀成「放大說明」沒問題。
   - LZ4 HW registers 方塊懸空，沒有線接到任何東西，看不出 register 的位址或它和 job ring、completion ring 的關係。
   - HRT、COT 兩個縮寫沒有展開。
   - chunk pool 的斜線沒有圖例（要到第 9 張才猜得出斜線代表壓縮資料）。
   - 「incompressible, 1 bit」沒有寫成 `incompressible[h]`，和同一組其他五列的寫法不同。
3. **圖說的一句話**：kernel 的每頁、每 frame 表格都放在 pinned area，COT 另放一區，另外有 chunk pool 和 frame area，後面幾張用這裡的成本模型算 cycle。
4. **畫面與結論**：部分一致。結論說「seven tables indexed by h, each on its own cache line」。畫面上「indexed by page h」只列六項，要把另一個方塊的 `cot[h]` 也算進去才湊得到七；「each on its own cache line」畫面完全沒有畫或寫。
5. **困惑指數**：2。地圖和欄位清單一看就懂，但結論的「七」要自己跨兩個方塊去數。
6. **可疑的錯字或多餘文字**：沒有拼字錯誤。HRT、COT 未展開。
7. **數字核對**
   - 沒有步驟方塊，沒有成本貼紙，沒有箭頭。
   - 位址差：0x80000000 到 0x83800000 = 56 MiB，對；到 0x85C00000 = 36 MiB，對；到 0x86100000 = 5 MiB，對；到 0x97400000 = 275 MiB，對；到 0xA0000000 = 140 MiB，對。合計 512 MiB。
   - 563200 chunks × 512 B = 275 MiB，對。35840 frames × 4096 B = 140 MiB，對。8800 words × 64 bits = 563200 bits，對。148480 × 32 B = 約 4.53 MiB，放得進 5 MiB。
   - 連線兩條：pinned area 到 kernel mem 方塊、COT area 到 COT area 方塊，黑色細實線，無箭頭、無標籤。

---

## 第 2 張：Page Fault, Part 1: Entry and Lock Hold A

1. **人物與機器**
   - 火柴人加筆電，標籤「user SW」，表情驚訝，是觸發 page fault 的程式。沒有箭頭從它連到步驟 1。
   - 步驟 1、2 是藍底方塊（貼紙寫「CPU hardware, not counted」、「assumed 600 ns」），看起來是 CPU 硬體與例外進入。藍底的意思圖例沒有解釋。
   - 步驟 3 到 6 是白底方塊，在灰色括號「kernel, mm_lock held: lock 4 instr, unlock 2 instr」底下，是 kernel。
2. **看不懂的線或物件**
   - 3→5 標「state」，3→6 標「state[h]」，同一個值兩種寫法，不確定是不是兩件事。
   - 步驟 3 讀 `state[h]` 和 `free_top` 兩個地方，貼紙只算 1 line；步驟 4 碰 `free_stack`、`frame_of[h]`、`owner[f]` 三個地方，貼紙只算 2 lines。哪一條被當成「已經在 cache」沒有標。
   - 藍色小旗「free_top, to step 18」掛在步驟 4，但 `free_top` 是步驟 3 讀的；要自己推論步驟 4 的 pop 改了它。
   - 步驟 2 的成本單位是 ns，其他是 cycles（要到第 11 張才說 1 cycle 當 1 ns）。
   - 括號上的 lock 4 instr、unlock 2 instr 有沒有算進底部的 39，這張看不出來。
3. **圖說的一句話**：user SW 碰到不在的頁，CPU 進 kernel，kernel 拿著 mm_lock 先查狀態，再做三件互不相依的事：拿 frame、讀 COT entry、把狀態標成 DECOMPRESSING。
4. **畫面與結論**：一致。
5. **困惑指數**：2。流程清楚，只有 cache line 的算法和 state 兩種寫法要猜。
6. **可疑的錯字或多餘文字**：無錯字。「state」與「state[h]」寫法不統一。
7. **數字核對**
   - 貼紙：步驟 1「CPU hardware, not counted」；步驟 2「assumed 600 ns」；步驟 3「14 instr, 1 line, 14 to 114 cycles」；步驟 4「12 instr, 2 lines, 12 to 212 cycles」；步驟 5「6 instr, 1 line, 6 to 106 cycles」；步驟 6「7 instr, 0 lines, 7 cycles」。
   - 加總：instr 14+12+6+7 = 39；lines 1+2+1+0 = 4；cycles 低 39、高 114+212+106+7 = 439。和結論「39 instr and 4 new cache lines: 39 to 439 cycles」對得上。lock 與 unlock 的 6 instr 不在 39 裡。
   - 「Three of the lines are indexed by h, one by f」：推得出是 `state[h]`、`frame_of[h]`、`cot[h]` 加 `owner[f]`，但貼紙沒有逐條標。
   - 箭頭：
     - 1→2，黑色虛線，「rule」
     - 2→括號（步驟 3 一帶），黑色虛線，「rule」
     - 3→4，橘色實線，「free_top」
     - 3→5，橘色實線，「state」
     - 3→6，橘色實線，「state[h]」
   - 藍色小旗：步驟 4「f, to step 7」、「free_top, to step 18」；步驟 5「COT entry, to step 7」；步驟 6「rule, to step 8」。
   - 藍字註記：「4, 5, 6 do not need each other」。

---

## 第 3 張：Page Fault, Part 2: The DECOMPRESS Job, No Lock Held

1. **人物與機器**
   - 沒有人物。
   - 步驟 9 `hw_decompress` 是綠底加齒輪，是 LZ4 HW。
   - 步驟 7、8、10、11、12 白底，方塊上沒有寫是誰做的。步驟 10 內文寫「OS wakes the sleeping thread」，「OS」和「kernel」是不是同一個角色沒有交代。要讀到底部結論才知道 7、8、11 是 kernel。
2. **看不懂的線或物件**
   - 9→10「interrupt」、10→11「wake-up」用橘色實線（圖例說橘色是「data: needs the value」）。interrupt 和 wake-up 比較像「等待」而不是「要那個值」，顏色的意思在這裡被拉寬了。
   - 步驟 8 寫「job_ring[tail], write 48 B」，第 1 張寫 job ring 一格 64 B，差的 16 B 沒有說明。
   - 步驟 11 下方的藍色小旗「to sheet 4: completion for steps 13 and 17, rule for step 14」一面旗塞三個去向，形狀也和其他旗不同。
   - 副標題寫「Scenario fault_ro」，第 2 張寫「fault_ro and fault_rw」，RW 頁走不走這一張沒有講。
3. **圖說的一句話**：不拿鎖的一條鏈：填 descriptor、送進 job ring 並寫 register、LZ4 HW 解壓到 frame、interrupt 喚醒、讀 completion，最後把那個 frame 的 64 條 cache line 作廢。
4. **畫面與結論**：一致。小落差：步驟 12「64 cache operations, time unknown」結論沒有提，讀者會以為這一段成本只有 251 到 351 cycles 加 4403 ns。
5. **困惑指數**：2。一條鏈很好讀，只是執行者沒標、橘色的意思被拉寬。
6. **可疑的錯字或多餘文字**：無錯字。
7. **數字核對**
   - 貼紙：步驟 7「26 instr, 0 lines, 26 cycles」；步驟 8「13 instr, 1 line, 1 register write, 63 to 163 cycles」；步驟 9「LZ4 HW model: 1253 ns」；步驟 10「assumed 3150 ns」；步驟 11「12 instr, 1 line, 1 register write, 162 cycles」；步驟 12「64 cache operations, time unknown」。
   - 步驟 8 自驗：13 + 50 = 63，再加 100 = 163，對。步驟 11 自驗：12 + 100 + 50 = 162，對（「always from DRAM」所以沒有低標）。
   - 加總：kernel 三個有算的步驟 26+63+162 = 251，26+163+162 = 351，和結論對得上。1253 + 3150 = 4403 ns，對得上。instr 26+13+12 = 51，lines 0+1+1 = 2（結論沒寫，第 11 張會用到）。
   - 箭頭：
     - 7→8，橘色實線，「descriptor」
     - 8→9，橘色實線，「job ring」
     - 9→10，橘色實線（繞一大圈折回左下），「interrupt」
     - 10→11，橘色實線，「wake-up」
     - 11→12，黑色虛線，「rule」
   - 藍色小旗：步驟 7「f, from step 4」、「COT entry, from step 5」；步驟 8「rule, from step 6」；步驟 11「to sheet 4: completion for steps 13 and 17, rule for step 14」；步驟 12「rule, to step 15」。

---

## 第 4 張：Page Fault, Part 3: Lock Hold B and Return

1. **人物與機器**
   - 右下火柴人加筆電，標籤「user SW」，表情開心，表示程式回來繼續跑。
   - 步驟 19 `eret`、20 `rerun` 藍底（「assumed 400 ns」、「CPU hardware, not counted」），是 CPU。
   - 灰框內八個白底方塊，括號寫「kernel, mm_lock held for both rows」，是 kernel。步驟 16 內文寫「OS: wake threads…」，OS 角色同樣沒有另外交代。
2. **看不懂的線或物件**
   - 方塊排列不照編號：上排 13、14、15、17，下排 18、16、a、b。眼睛會照位置讀成 13、14、15、17、18、16。
   - 「all done, unlock, return」這條虛線從灰框右緣（步驟 17 旁邊）出發，乍看像是 17→19。
   - `strikes`、`fresh[t]`、`low mark` 在第 1 張的表格清單裡找不到。
   - 步驟 b「bitmap, clear 5 bits」的 5 從哪來，這張沒講（到第 10 張才看到「5 of 7 chunks used」）。
   - 步驟 15 `pte_map` 寫入 frame address，卻沒有「f, from step 4」的小旗，只有 rule。
   - 13、15、17、18、a 之間沒有箭頭，依圖例是「any order」，但這張沒有像第 2 張那樣寫一句「do not need each other」。
3. **圖說的一句話**：解壓完成後 kernel 再拿一次 mm_lock，把狀態設成 PRESENT、寫 pte、更新 fresh 記錄、檢查要不要叫醒回收者，RW 頁多做清 COT 和釋放 chunks，然後 eret 回 user SW 重跑那道指令。
4. **畫面與結論**：一致。
5. **困惑指數**：3。數字都對，但編號和位置不一致，加上「all done」箭頭起點不明，要來回看幾次。
6. **可疑的錯字或多餘文字**：無錯字。小旗用詞不統一：這張寫「rule, after step 11」、「rule, after step 12」，其他張寫「from step N」。
7. **數字核對**
   - 貼紙：13「5 instr, 0 lines, 5 cycles」；14「3 instr, 0 lines, 3 cycles」；15「6 instr, 1 line, 6 to 106 cycles」；17「19 instr, 2 lines, 19 to 219 cycles」；18「2 instr, 0 lines, 2 cycles」；16「OS call, not counted」；a「4 instr, 0 lines, 4 cycles」；b「80 instr, 1 line, 80 to 180 cycles」；19「assumed 400 ns」；20「CPU hardware, not counted」。
   - RO 加總：instr 5+3+6+19+2 = 35；lines 0+0+1+2+0 = 3；cycles 35 到 5+3+106+219+2 = 335。對得上。
   - RW 加總：35+4+80 = 119；lines 3+0+1 = 4；cycles 119 到 335+4+180 = 519。對得上。
   - 箭頭：
     - 14→16，黑色虛線，「rule」
     - a→b，黑色虛線，「rule」
     - 灰框→19，黑色虛線，「all done, unlock, return」
     - 19→20，橘色實線，「PC」
   - 藍色小旗：13「completion, from step 11」；14「rule, after step 11」；15「rule, after step 12」；17「completion, from step 11」；18「free_top, from step 4」；a「completion, from step 11」。

---

## 第 5 張：First Touch: A Frame of Zeros in One Lock Hold

1. **人物與機器**
   - 左上火柴人加筆電「user SW」，驚訝表情，旁邊藍旗「steps 1 and 2 as on sheet 2: access, exception」。
   - 七個白底方塊在「kernel, mm_lock held」括號下，是 kernel。
   - 沒有 LZ4 HW。右上藍旗「then eret and rerun as on sheet 4」。
2. **看不懂的線或物件**
   - 4→9「free_top」這條橘線從步驟 4 的右下出發，穿過步驟 5 的貼紙下方再到步驟 9，起點容易看成步驟 5。
   - 3→6「state[h]」和 3→8「state」又是兩種寫法；步驟 8 `note_fresh` 為什麼需要 state 看不出來（第 4 張的 `note_fresh` 需要的是 completion）。
   - 步驟 7 `pte_map` 寫 frame address，只收到 5→7 的 rule，沒有 `f` 的橘線。
   - 步驟編號 3 到 9 和第 2、3 張的 3 到 9 是不同的動作（這裡步驟 5 是 `zero_frame`，那邊是 `cot_read`）。
   - 方塊排列：上排 4、5、7，下排 6、8、9。
3. **圖說的一句話**：第一次碰的頁不需要 LZ4，一次鎖內拿 frame、填零、設 PRESENT、寫 pte、記 fresh、檢查低水位就結束。
4. **畫面與結論**：一致。
5. **困惑指數**：2。故事單純，只有一條穿越的橘線和編號重用要留意。
6. **可疑的錯字或多餘文字**：無錯字。步驟 5 貼紙「341 instr, 341 cycles」少了「0 lines」這一欄，格式和其他貼紙不同。
7. **數字核對**
   - 貼紙：3「14 instr, 1 line, 14 to 114 cycles」；4「12 instr, 2 lines, 12 to 212 cycles」；5「341 instr, 341 cycles」；7「6 instr, 1 line, 6 to 106 cycles」；6「3 instr, 0 lines, 3 cycles」；8「19 instr, 2 lines, 19 to 219 cycles」；9「2 instr, 0 lines, 2 cycles」。
   - 加總：instr 14+12+341+6+3+19+2 = 397；lines 1+2+0+1+0+2+0 = 6；cycles 397 到 114+212+341+106+3+219+2 = 997。和結論「397 instr and 6 new lines: 397 to 997 cycles」對得上；「341 of the instructions fill the frame with zeros」也對。
   - 箭頭：
     - 3→4，橘色實線，「free_top」
     - 4→5，橘色實線，「f」
     - 5→7，黑色虛線，「rule: zeros before valid」
     - 3→6，橘色實線，「state[h]」
     - 3→8，橘色實線（從步驟 3 底部繞一個弧），「state」
     - 4→9，橘色實線，「free_top」

---

## 第 6 張：When the LZ4 HW Fails: Software Rescue, or a Lost Page

1. **人物與機器**
   - 右下火柴人「user SW」，雙手舉高、驚慌，表示程式被終止。
   - 步驟 13 `sw_decode`、上框的 14 `frame_write`、15 `sw_clean`：白底，沒有標是誰做的、在哪個 thread、拿不拿鎖（沒有括號，推測是不拿鎖的 kernel）。
   - 下框灰色括號「kernel, mm_lock held」蓋住 15、16、17、14 四格，是 kernel。17 `wake_page` 和 18 `kill` 寫「OS:」。
   - LZ4 HW 是這張的主角（它失敗了），但畫面上沒有出現。
2. **看不懂的線或物件**
   - 同一張有兩個步驟 14、兩個步驟 15（上框 14 `frame_write`、15 `sw_clean`；下框 14 `note_hw`、15 `put_frame`），而且步驟 13 和第 4 張的步驟 13（`note_hw`）撞號。
   - 下框的排列是 15、16、17、14、18，步驟 14 排在 17 後面。
   - 13 往下的虛線「rule: decode first, then steps 15 and 16」：這張有兩個步驟 15，要靠箭頭落點才知道指下框。
   - 上框標題「an RW page」：為什麼救回來的頁要當 RW 頁處理，沒有說。
   - 右上藍旗「then lock hold B of an RW page, sheet 4: pte_map waits for this step」：第 4 張的 lock hold B 第一步是 `note_hw: strikes = 0`，但這裡 HW 剛失敗，下框的 `note_hw` 是「strikes + 1」。救回成功那條路 strikes 到底歸零還是加一，圖上互相矛盾或至少沒講。
   - 13→14 的橘線標「page」，14→15 標「frame[f]」，可以理解。
   - 「all done, unlock」虛線從下框步驟 14 指到 18 `kill`。
3. **圖說的一句話**：LZ4 HW 回報失敗後 kernel 用軟體解碼；解得出來就把 4096 B 複製進 frame、把 cache 寫回，接回正常流程；解不出來就在鎖內歸還 frame、把頁標成 LOST、記一次 strike，然後 OS 把這個 user SW 結束掉。
4. **畫面與結論**：部分一致。「Lost page: 21 instr under the lock」從畫面加得出來。「the copy alone is 791 of the scenario's 1012 instr」的 1012 在這張完全加不出來，要回頭拿第 2、3、4 張的數字加上鎖的 12 instr 才湊得到。
5. **困惑指數**：4。兩個情境共用一張、編號重複又亂序，再加上一個本張算不出來的 1012。
6. **可疑的錯字或多餘文字**
   - 右上藍旗「then lock hold B」的 lock 和 hold 之間疑似多一個小點（像「lock.hold」），可能是繪圖雜點。
   - 步驟 14 貼紙「791 instr, 791 cycles, 64 lines written」欄位順序和其他貼紙不同，「lines written」又和別處的「new lines」不是同一個概念。
7. **數字核對**
   - 貼紙：13「not measured yet」；上框 14「791 instr, 791 cycles, 64 lines written」；上框 15「64 cache operations, time unknown」；下框 15「13 instr, 0 lines, 13 cycles」；16「3 instr, 0 lines, 3 cycles」；17「OS call, not counted」；下框 14「5 instr, 0 lines, 5 cycles」；18「OS call, not counted」。
   - Lost page 加總：13+3+5 = 21，對得上。
   - Rescue：本張只有 791。1012 = 第 2 張 39 + 第 3 張 51 + 791 + 第 4 張 RW 119 + 兩次鎖 12，跨圖才對得上。
   - 箭頭：
     - 13→上框 14，橘色實線，「page」
     - 上框 14→上框 15，橘色實線，「frame[f]」
     - 13→下框括號（落在步驟 15 上方），黑色虛線，「rule: decode first, then steps 15 and 16」
     - 16→17，黑色虛線，「rule」
     - 下框 14→18，黑色虛線，「all done, unlock」
   - 藍色小旗：13「completion says failed, from step 11」；上框 14「after cache_invalidate, step 12 on sheet 3」；上框 15 右側「then lock hold B of an RW page, sheet 4: pte_map waits for this step」；下框 14「completion, from step 11」。

---

## 第 7 張：Evicting an RO Page: The Clock Scan and One Lock Hold

1. **人物與機器**
   - 沒有人物。
   - 括號寫「kernel reclaimer thread, mm_lock held」，執行者是 kernel 的 reclaimer thread。
   - 步驟 4 `tlb_inval` 內文寫「CPU MMU」，是 CPU 硬體動作，但方塊是白底（第 2、4 張的 CPU 步驟是藍底）。
   - 右側面板畫六個方格和一支「clock hand」。
2. **看不懂的線或物件**
   - 灰色括號只蓋住上排（1、2、6），下排（3、4、5）看起來在括號外。`tlb_inval` 的 500 ns 是不是在鎖內，光看圖不確定；要看底部寫「One lock hold」才推得出全部都在鎖內。
   - 排列：上排 1、2、6，下排 3、4、5。步驟 6 和 3、4、5 之間沒有箭頭。
   - 步驟 2 貼紙「33 instr, 4 lines」和右側面板的四列（10、20、33、40 instr）是什麼關係不清楚：33 是「選中那一格」的成本，還是剛好等於「incompressible RW page: 33 instr, 3 lines」那一列？
   - 「test bit 10」沒有說 bit 10 是什麼。
   - 左側藍旗「woken when free_top is at the low mark」不是「from step N」格式，也沒說是哪一張的哪一步叫醒它。
3. **圖說的一句話**：reclaimer 被叫醒後在一次鎖內用 clock hand 挑一個受害頁，清 pte、作廢 TLB、歸還 frame、把狀態改成 COMPRESSED，因為 RO 頁的壓縮資料本來就還在 chunks 裡。
4. **畫面與結論**：一致。「Every frame passed adds up to 4 more lines」對得上右側面板最貴的一列。
5. **困惑指數**：3。主流程清楚，但括號沒蓋到下排，加上貼紙和右側面板的關係要猜。
6. **可疑的錯字或多餘文字**：「longest 35841 frames」比第 1 張的總數 35840 多 1，可能是繞一整圈再加一格，也可能是筆誤，圖上沒解釋。
7. **數字核對**
   - 貼紙：1「2 instr, 0 lines, 2 cycles」；2「33 instr, 4 lines, 33 to 433 cycles」；6「3 instr, 0 lines, 3 cycles」；3「2 instr, 0 lines, 2 cycles」；4「assumed 500 ns」；5「13 instr, 1 line, 13 to 113 cycles」。
   - 加總：instr 2+33+3+2+13 = 53；lines 0+4+0+0+1 = 5；cycles 53 到 2+433+3+2+113 = 553。和結論「53 instr and 5 new lines: 53 to 553 cycles, plus the assumed 500 ns」對得上。
   - 右側面板：free frame 10 instr；fresh page 20 instr, 3 lines；incompressible RW page 33 instr, 3 lines；accessed page, flag cleared 40 instr, 4 lines；measured run 4.9 frames per pick, longest 35841 frames。
   - 箭頭：
     - 1→2，黑色虛線，「rule」
     - 2→6，橘色實線，「state[h]」
     - 2→3，橘色實線（往下折），「victim」
     - 3→4，黑色虛線，「rule」
     - 4→5，黑色虛線，「rule」
   - 藍色小旗：步驟 1 左側「woken when free_top is at the low mark」。

---

## 第 8 張：Evicting an RW Page, Part 1: Lock Hold A and the Bitmap Search

1. **人物與機器**
   - 沒有人物。括號「kernel reclaimer thread, mm_lock held: lock 4 instr, unlock 2 instr」，執行者是 reclaimer thread。
   - 步驟 6 `tlb_inval`「CPU MMU」白底。
   - 右側面板「inside reserve: find a free bit」，一條十格的色帶（灰與白），其中一格被橘圈圈住。
2. **看不懂的線或物件**
   - 右側色帶：灰與白沒有圖例（推測灰是已用）。橘圈圈在左起第五格，但左起第四格看起來也是白的；「the lowest free bit」為什麼不是第一個白格，不確定。
   - `pick_victim` 這張是 44 instr，第 7 張是 33 instr，動作文字幾乎一樣，差的 11 instr 沒有解釋。
   - `free_chunks` 在第 1 張的 scalars（free_top, hand, cursor）裡沒有。
   - 右側寫「about 14 instr per chunk, 7 per word passed」：14 × 7 + 7 = 105，貼紙是 111，差 6 沒說明（可接受，寫的是 about）。
3. **圖說的一句話**：reclaimer 在鎖內挑出受害的 RW 頁，從 bitmap 預留 7 個 chunks、查出 frame、清 pte 並作廢 TLB、把狀態標成 COMPRESSING。
4. **畫面與結論**：一致。
5. **困惑指數**：2。扇形展開的四條橘線一眼看得出 3、4、5、7 都只依賴 2。
6. **可疑的錯字或多餘文字**：無錯字。
7. **數字核對**
   - 貼紙：1「2 instr, 0 lines, 2 cycles」；2「44 instr, 4 lines, 44 to 444 cycles」；3「111 instr, 1 line, 111 to 211 cycles」；4「5 instr, 1 line, 5 to 105 cycles」；5「2 instr, 0 lines, 2 cycles」；6「assumed 500 ns」；7「3 instr, 0 lines, 3 cycles」。
   - 加總：instr 2+44+111+5+2+3 = 167；lines 0+4+1+1+0+0 = 6；cycles 167 到 2+444+211+105+2+3 = 767。和結論「167 instr and 6 new lines: 167 to 767 cycles, plus the assumed 500 ns」對得上。
   - 箭頭：
     - 1→2，黑色虛線，「rule」
     - 2→3，橘色實線，「victim」
     - 2→4，橘色實線，「victim」
     - 2→5，橘色實線，「victim」
     - 2→7，橘色實線，「state[h]」
     - 5→6，黑色虛線，「rule」
   - 藍色小旗：3「chunk numbers, to step 9」；4「f, to steps 8 and 9」；6「rule, to step 8」；7「rule, to step 10」。

---

## 第 9 張：Evicting an RW Page, Part 2: The COMPRESS Job, No Lock Held

1. **人物與機器**
   - 沒有人物。
   - 步驟 11 `hw_compress` 綠底加齒輪，是 LZ4 HW。上方有一個小圖：一個白方格→三個斜線方格，沒有標籤（推測是一頁變成壓縮 chunks）。
   - 步驟 8、9、10、12、13 白底，方塊上沒有寫執行者；步驟 12 寫「OS wakes the reclaimer thread」，可推回是 reclaimer。
2. **看不懂的線或物件**
   - 副標題的「doorbell」在方塊裡沒有出現，要猜是步驟 10 的「HW register: write JOB_TAIL」。
   - 「three things must be ready」要自己數：8 的 rule、9 的 descriptor、步驟 7 的 rule 小旗。
   - 小圖畫三個斜線方格，內文是 7 個 chunk numbers、第 10 張是 5 of 7，三個數字不一樣。
   - 11→12「interrupt」、12→13「wake-up」同樣用橘色。
   - 步驟 13 少了第 3 張同名步驟的「compare the tag」那一行。
3. **圖說的一句話**：不拿鎖，先把 frame 的髒 cache line 寫回、同時填 descriptor，兩者加上前一張的狀態標記都好了才能送 job；LZ4 HW 壓縮寫進 chunk pool，interrupt 叫醒 reclaimer 讀 completion。
4. **畫面與結論**：一致。步驟 8「time unknown」結論同樣沒提。
5. **困惑指數**：2。和第 3 張同一個骨架，看過第 3 張就會讀。
6. **可疑的錯字或多餘文字**：無錯字。「doorbell」未定義。
7. **數字核對**
   - 貼紙：8「64 cache operations, time unknown」；9「55 instr, 0 lines, 55 cycles」；10「13 instr, 1 line, 1 register write, 63 to 163 cycles」；11「LZ4 HW model: 4260 ns」；12「assumed 3150 ns」；13「12 instr, 1 line, 1 register write, 162 cycles」。
   - 加總：55+63+162 = 280，55+163+162 = 380，和結論「280 to 380 cycles」對得上；4260 ns、3150 ns 對得上。instr 55+13+12 = 80，lines 2。
   - 箭頭：
     - 8→10，黑色虛線（上方弧線），「rule: clean before doorbell」
     - 9→10，橘色實線，「descriptor」
     - 10→11，橘色實線（繞回左下），「job ring」
     - 11→12，橘色實線，「interrupt」
     - 12→13，橘色實線，「wake-up」
   - 藍色小旗：8「f, from step 4」、「rule, from step 6」；9「chunk numbers, from step 3」、「f, from step 4」；10「rule, from step 7」；13「completion, to steps 14 to 18」。
   - 藍字註記：「8 and 9 do not need each other」。

---

## 第 10 張：Evicting an RW Page, Part 3: Lock Hold B, Two Outcomes

1. **人物與機器**
   - 沒有人物。
   - 左框括號「kernel reclaimer thread, mm_lock held」，右框括號「same thread, mm_lock held」，執行者清楚。
   - 兩框的步驟 19 `wake_page` 寫「OS:」。
2. **看不懂的線或物件**
   - 整張沒有任何橘色箭頭，也沒有任何藍色小旗。第 9 張步驟 13 的旗寫「completion, to steps 14 to 18」，這張沒有一格標「completion, from step 13」，看不出哪幾步真的需要 completion（`cot_store` 的 length 和 CRC-32、`trim` 的 2 個多餘 bits 應該都需要）。
   - 左框排列：上排 14、15、17，下排 16、18、19。
   - 兩框的步驟編號都是 14 到 19，動作不同。
   - 括號沒有寫「lock 4 instr, unlock 2 instr」（其他張都有）。
   - 清 bitmap 的單價差很多：第 4 張清 5 bits 要 80 instr，這張清 2 bits 要 18 instr、清 7 bits 要 51 instr，沒有解釋。
   - 做完之後去哪裡沒有畫（回到 `reclaim_check` 再挑下一頁？還是 thread 去睡？）。
3. **圖說的一句話**：壓縮完成後 reclaimer 再拿一次鎖：壓得進去就寫 COT entry、退掉多拿的 2 個 chunks、歸還 frame、狀態改 COMPRESSED；壓不進去就把 7 個 chunks 全退、標 incompressible、把頁恢復成 PRESENT 並重新 map。
4. **畫面與結論**：一致。
5. **困惑指數**：3。數字都對，但沒有任何跨圖小旗和資料箭頭，步驟之間誰等誰幾乎沒有資訊。
6. **可疑的錯字或多餘文字**：無錯字。貼紙格式不統一：右框 14「5 instr, 5 cycles」、17「3 instr, 3 cycles」少了 lines 欄；右框 19 只寫「OS call」，左框 19 寫「OS call, not counted」。
7. **數字核對**
   - 左框貼紙：14「5 instr, 0 lines, 5 cycles」；15「44 instr, 1 line, 44 to 144 cycles」；17「13 instr, 0 lines, 13 cycles」；16「18 instr, 0 lines, 18 cycles」；18「3 instr, 0 lines, 3 cycles」；19「OS call, not counted」。
   - 左框加總：5+44+13+18+3 = 83；lines 1；cycles 83 到 183。和結論「Fits: 83 instr and 1 new line, 83 to 183 cycles」對得上。
   - 右框貼紙：14「5 instr, 5 cycles」；15「51 instr, 0 lines, 51 cycles」；16「8 instr, 0 lines, 8 cycles」；17「3 instr, 3 cycles」；18「6 instr, 0 lines, 6 cycles」；19「OS call」。
   - 右框加總：5+51+8+3+6 = 73；lines 0；cycles 73。和結論「Does not fit: 73 instr and 0 new lines, 73 cycles」對得上。
   - 箭頭：
     - 左框 15→17，黑色虛線，「rule: COT entry before the frame is free」
     - 左框 18→19，黑色虛線，「rule」
     - 右框 17→19，黑色虛線，「rule: PRESENT first」
   - 藍色小旗：無。
   - 藍字註記：「0 lines: that bitmap word, frame_of[h] and pte[h] were already touched in lock hold A, sheet 8」。

---

## 第 11 張：Eight Scenarios: What the Kernel's Own Steps Cost

1. **人物與機器**：沒有人物、沒有機器，是一張八列六欄的表。
2. **看不懂的線或物件**
   - 表頭只有 instr 和 new lines 兩格是黃底，推測是呼應黃色貼紙，但沒說。
   - 「assumed CPU and OS, ns」沒有拆開，要自己回頭湊（600 exception、3150 notify、400 eret、500 tlb_inval）。
   - 「Low end: only the completion line misses」對沒有 completion 的情境（first_touch、evict_ro）是什麼意思要自己想（就是沒有任何 miss）。
3. **圖說的一句話**：八個情境裡 kernel 自己的步驟各要幾個 instr、幾條新 cache line、幾個 cycles，旁邊列出 CPU 與 OS 的假設開銷和 LZ4 HW 的時間。
4. **畫面與結論**：一致。59 是 evict_ro 的低標，2112 是 fault_rescue 的高標；500 是 evict_ro，7910 = 3650 + 4260 是 evict_rw。用詞小落差：結論說「table work」，但 2112 裡有 791 instr 是複製 frame，不是查表。
5. **困惑指數**：2。表本身一看就懂，但要驗算得翻回前面九張，ns 那一欄沒有給組成。
6. **可疑的錯字或多餘文字**：無錯字。底部標籤「Reading:」帶冒號，其他張的標籤不帶。
7. **數字核對**：表格每一列的試算放在下面「跨圖觀察」第 4 點，八列全部加得出來。沒有步驟方塊、沒有箭頭。

---

## 跨圖觀察

### 1. 命名物件長得一不一樣

| 物件 | 一致程度 | 走樣的地方 |
|---|---|---|
| 步驟方塊（圓角白框、左上橘色圓形編號、粗體名稱、「放在哪: 做什麼」內文） | 第 2 到 10 張一致 | 無明顯走樣 |
| 黃色成本貼紙 | 位置與顏色一致 | 格式走樣：第 5 張步驟 5「341 instr, 341 cycles」、第 6 張「791 instr, 791 cycles, 64 lines written」、第 10 張右框「5 instr, 5 cycles」「3 instr, 3 cycles」「OS call」 |
| 藍色小旗 | 都是藍框藍字，認得出來 | 形狀每張不同：第 2、8 張是右側缺角的三角旗；第 3、9 張是兩端尖角的小牌；第 4 張是貼在方塊上緣、帶小尾巴的對話框；第 5、6 張是大型旗。用詞也不同：「from step N」、「after step N」、「to sheet 4: …」、「then … as on sheet 4」 |
| 灰色括號（鎖） | 都有鎖頭圖示 | 第 4 張另外加了一個封閉的灰色圓角框；第 7 張括號只蓋上排；第 10 張括號沒有「lock 4 instr, unlock 2 instr」；文字有「kernel」、「kernel reclaimer thread」、「same thread」三種 |
| 右上圖例 | 第 2 到 10 張一致 | 無 |
| 底部結論列（左藍格標籤加右邊一句話） | 一致 | 第 11 張標籤多一個冒號；第 4、7、10 張的藍格多一層圓角內框 |
| 左上張號（橘色方塊） | 一致 | 第 7 張沒有黑色外框 |
| user SW 火柴人 | 第 2、4、5、6 張長相一致，表情跟著劇情變 | 第 3、7、8、9、10 張沒有出現，evict 三張完全看不到是為了誰在做 |
| LZ4 HW（綠底加齒輪） | 第 1、3、9 張一致 | 第 6 張講 HW 失敗卻沒有畫 HW |

### 2. 分類顏色

- 橘色（編號、data 箭頭、標題底線）：一致。但 interrupt 與 wake-up 也畫成橘色實線，把「需要那個值」拉寬成「等那件事發生」。
- 黃色（成本貼紙）：一致。
- 綠色（LZ4 HW）：一致。
- 藍字（副標題、小旗、旁註）：一致。
- 斜線（壓縮資料）：第 1 張 chunk pool、第 9 張小圖一致。
- 藍底方塊：不一致，而且圖例沒有解釋。第 2 張步驟 1、2 和第 4 張步驟 19、20 是藍底（CPU 硬體、例外進出）；但第 7、8 張的 `tlb_inval`（CPU MMU，assumed 500 ns）和第 3、9 張的 `notify`（interrupt entry，assumed 3150 ns）同樣是「CPU 或 OS 的假設值」卻是白底。

### 3. 藍色小旗的對應

對得上的：

| 出發 | 到達 | 結果 |
|---|---|---|
| 第 2 張步驟 4「f, to step 7」 | 第 3 張步驟 7「f, from step 4」 | 對 |
| 第 2 張步驟 5「COT entry, to step 7」 | 第 3 張步驟 7「COT entry, from step 5」 | 對 |
| 第 2 張步驟 6「rule, to step 8」 | 第 3 張步驟 8「rule, from step 6」 | 對 |
| 第 2 張步驟 4「free_top, to step 18」 | 第 4 張步驟 18「free_top, from step 4」 | 對 |
| 第 3 張步驟 11「completion for steps 13 and 17, rule for step 14」 | 第 4 張步驟 13、17「completion, from step 11」，步驟 14「rule, after step 11」 | 對（用詞 after 與 from 不同） |
| 第 3 張步驟 12「rule, to step 15」 | 第 4 張步驟 15「rule, after step 12」 | 對（用詞不同） |
| 第 8 張步驟 3「chunk numbers, to step 9」 | 第 9 張步驟 9「chunk numbers, from step 3」 | 對 |
| 第 8 張步驟 4「f, to steps 8 and 9」 | 第 9 張步驟 8、9 各有「f, from step 4」 | 對 |
| 第 8 張步驟 6「rule, to step 8」 | 第 9 張步驟 8「rule, from step 6」 | 對 |
| 第 8 張步驟 7「rule, to step 10」 | 第 9 張步驟 10「rule, from step 7」 | 對 |
| 第 5 張「steps 1 and 2 as on sheet 2」、「then eret and rerun as on sheet 4」 | 第 2 張步驟 1、2；第 4 張步驟 19、20 | 對 |
| 第 6 張副標題「both follow step 11, cpl_read, on sheet 3」 | 第 3 張步驟 11 | 對 |

對不上的：

1. 第 4 張步驟 a「completion, from step 11」：第 3 張步驟 11 的旗只列了步驟 13、17、14，沒有 a。
2. 第 6 張步驟 13「completion says failed, from step 11」：第 3 張步驟 11 的旗只寫「to sheet 4」，沒有提第 6 張。
3. 第 6 張下框步驟 14「completion, from step 11」：同上，第 3 張沒有對應的去向。
4. 第 6 張上框步驟 14「after cache_invalidate, step 12 on sheet 3」：第 3 張步驟 12 的旗只寫「rule, to step 15」，沒有提第 6 張的 `frame_write`。
5. 第 6 張上框步驟 15「then lock hold B of an RW page, sheet 4: pte_map waits for this step」：第 4 張 `pte_map` 的旗只寫「rule, after step 12」，沒有提 `sw_clean`。另外第 4 張 lock hold B 的 `note_hw` 是「strikes = 0」，和 HW 剛失敗的情境對不起來。
6. 第 7 張「woken when free_top is at the low mark」：第 4 張步驟 18 和第 5 張步驟 9 的 `wake_check`「compare with the low mark」都沒有往外的旗，叫醒 reclaimer 這件事只有單向標示。
7. 第 9 張步驟 13「completion, to steps 14 to 18」：第 10 張沒有任何一格有「from step 13」的旗；第 10 張有兩套 14 到 19，旗上也沒有寫是哪一張、哪一套。
8. 疑似漏掉的資料相依：`pte_map` 寫 frame address 需要 `f`，但第 4 張步驟 15、第 5 張步驟 7、第 10 張右框步驟 18 都沒有 `f` 的旗或橘線。
9. 步驟編號撞號讓「to step N」不唯一：第 5 張的 3 到 9、第 6 張的 13 到 18（而且同張有兩個 14、兩個 15）、第 10 張兩套 14 到 19。

### 4. 第 11 張逐列試算

規則（第 11 張藍字）：每次 lock hold 加 6 instr；cycles = instr + 50 × register write + 100 × miss 的 line；低標只有 completion 那條 line miss，高標是所有 new line 都 miss。

| 情境 | instr 試算 | new lines 試算 | cycles 試算 | CPU and OS ns 試算 | LZ4 ns | 結果 |
|---|---|---|---|---|---|---|
| first_touch | 第 5 張 397 + 鎖 6 = 403 | 6 | 403 到 403 + 600 = 1003 | 600 + 400 = 1000 | none | 全對 |
| fault_ro | 39 + 51 + 35 + 鎖 12 = 137 | 4 + 2 + 3 = 9 | 低 137 + 100 + 100 = 337；高 137 + 100 + 900 = 1137 | 600 + 3150 + 400 = 4150 | 1253 | 全對 |
| fault_rw | 39 + 51 + 119 + 12 = 221 | 4 + 2 + 4 = 10 | 低 221 + 100 + 100 = 421；高 221 + 100 + 1000 = 1321 | 4150 | 1253 | 全對 |
| fault_rescue | 221 + 791 = 1012 | 10（64 lines written 不算） | 421 + 791 = 1212；1321 + 791 = 2112 | 4150 | 1253 | 全對 |
| fault_lost | 39 + 51 + 21 + 12 = 123 | 4 + 2 + 0 = 6 | 低 123 + 100 + 100 = 323；高 123 + 100 + 600 = 823 | 600 + 3150 = 3750（沒有 eret） | 1253 | 全對 |
| evict_ro | 第 7 張 53 + 6 = 59 | 5 | 59 到 59 + 500 = 559 | 500 | none | 全對 |
| evict_rw | 167 + 80 + 83 + 12 = 342 | 6 + 2 + 1 = 9 | 低 342 + 100 + 100 = 542；高 342 + 100 + 900 = 1342 | 500 + 3150 = 3650 | 4260 | 全對 |
| evict_rw_incompressible | 167 + 80 + 73 + 12 = 332 | 6 + 2 + 0 = 8 | 低 332 + 100 + 100 = 532；高 332 + 100 + 800 = 1232 | 3650 | 4260 | 全對 |

也用各張底部結論的 cycles 範圍直接相加再驗一次：

- fault_ro：39 + 251 + 35 + 12 = 337；439 + 351 + 335 + 12 = 1137。對。
- fault_rw：39 + 251 + 119 + 12 = 421；439 + 351 + 519 + 12 = 1321。對。
- evict_rw：167 + 280 + 83 + 12 = 542；767 + 380 + 183 + 12 = 1342。對。
- evict_rw_incompressible：167 + 280 + 73 + 12 = 532；767 + 380 + 73 + 12 = 1232。對。

結論列：59（evict_ro 低標）、2112（fault_rescue 高標）、500（evict_ro）、7910 = 3650 + 4260（evict_rw）。全對。

八列全部加得出來。要注意的是：這些加法需要「每次 lock hold 加 6 instr」這條規則，它只寫在第 11 張；第 2 到 10 張的底部結論都不含這 6 instr，讀者單看第 6 張的 1012 會加不出來。

### 5. 故事線

- 順序是：地圖（1）→ page fault 三段（2、3、4）→ first touch（5）→ HW 失敗（6）→ 回收 RO 頁（7）→ 回收 RW 頁三段（8、9、10）→ 總表（11）。每一組內部順，「Lock hold A、Part 2 不拿鎖、Lock hold B」這個三段骨架在 fault 和 evict 兩邊重複出現，看過一次就會讀第二次。
- 斷掉或卡住的地方：
  1. 最簡單的 first touch 排在最複雜的 page fault 之後；一頁的生命順序其實是先 first touch、被回收、再 fault 回來，現在的順序是倒著講。
  2. 第 2 張說涵蓋 fault_ro 和 fault_rw，第 3 張副標題只寫 fault_ro，第 4 張才說 RW 頁多 a、b 兩步。RW 頁走不走第 3 張要自己推。
  3. 第 6 張接在第 3 張步驟 11 後面，但第 3 張沒有任何指向第 6 張的旗；救回成功後再接回第 4 張，strikes 的處理說不通。
  4. 第 7 張的 reclaimer 是被第 4、5 張的 `wake_check` 叫醒的，這條連結只有第 7 張單向寫。
  5. 第 10 張做完就沒了，沒有交代 reclaimer 接著做什麼。
  6. 步驟編號是每個情境各編各的，但小旗只寫「step N」不寫張號（第 3 張步驟 11 的旗和第 6 張的旗除外），跨情境時會指錯。
  7. 第 2 到 10 張的白底方塊靠括號文字才知道是 kernel；第 3、9 張沒有括號，執行者要從底部結論回推。
- 我用自己的話說這組圖的結論：
  - kernel 自己的記帳工作很小。每個情境是幾十到一千個 instr，換成 59 到 2112 cycles；大頭不是運算，而是分散在好幾張表上的 cache miss（一個情境 5 到 10 條新 line，每條最多 100 cycles），以及少數整頁的動作（填零 341、軟體救回複製 791、bitmap 找 7 個空位 111）。
  - 真正在等的是別人：例外進出、interrupt 加喚醒（3150 ns）和 LZ4 HW（解壓 1253 ns、壓縮 4260 ns），合計 500 到 7910 ns，比 kernel 自己的步驟大好幾倍。
  - 鎖只在頭尾各拿一小段（A 與 B），LZ4 job 那段不拿鎖。鎖內多數步驟彼此沒有先後，真正的相依只有少數幾個值（`free_top`、`state[h]`、`f`、victim、completion）和幾條順序規則（先標狀態再送 job、先清 cache 再寫 register、先寫 COT 再放 frame、先設 PRESENT 再叫醒）。
  - 還沒量的有兩樣：一個 frame 64 條 line 的 cache 維護、軟體解碼。

### 6. 總表

| 張 | 標題 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|---|
| 01 | Where the Kernel's Tables Live | 2 | 是 | 部分一致 |
| 02 | Page Fault, Part 1 | 2 | 是 | 一致 |
| 03 | Page Fault, Part 2 | 2 | 是（執行者要從結論回推，OS 未交代） | 一致 |
| 04 | Page Fault, Part 3 | 3 | 是 | 一致 |
| 05 | First Touch | 2 | 是 | 一致 |
| 06 | When the LZ4 HW Fails | 4 | 否 | 部分一致 |
| 07 | Evicting an RO Page | 3 | 是 | 一致 |
| 08 | Evicting an RW Page, Part 1 | 2 | 是 | 一致 |
| 09 | Evicting an RW Page, Part 2 | 2 | 是（執行者要回推） | 一致 |
| 10 | Evicting an RW Page, Part 3 | 3 | 是 | 一致 |
| 11 | Eight Scenarios | 2 | 是（無角色） | 一致 |

### 7. 建議重生

1. **第 6 張（最優先）**：困惑指數 4、角色不清、畫面與結論部分一致。
   - 兩個情境擠一張，同張出現兩個步驟 14、兩個步驟 15，下框還把 14 排在 17 後面。
   - 1012 在本張加不出來；要嘛在本張寫出「221 + 791」，要嘛結論只講本張加得出來的數字。
   - `sw_decode`、`frame_write`、`sw_clean` 沒有標執行者與是否拿鎖；LZ4 HW 沒有出現。
   - 救回成功後接第 4 張的「strikes = 0」和本張的「strikes + 1」要講清楚。
   - 建議拆成兩張，或至少兩框用不撞號的編號（例如 R1、R2 與 L1 到 L5）。
2. **第 4 張**：困惑指數 3。
   - 方塊位置不照編號（13、14、15、17 / 18、16、a、b）。
   - 「all done, unlock, return」箭頭起點要明確從整個灰框出發。
   - 小旗用詞改成和其他張一樣的「from step N」，並補上 `pte_map` 的 `f` 來源。
3. **第 7 張**：困惑指數 3。
   - 灰色括號要蓋住全部六格（或明確畫出哪些在鎖外）。
   - 步驟 2 的 33 instr 和右側面板四列的關係要寫一句。
   - 「35841」要說明或更正；步驟 6 放回 5 之後。
4. **第 10 張**：困惑指數 3。
   - 補上「completion, from step 13」小旗和資料箭頭，讓人看得出哪幾步真的在等 completion。
   - 貼紙格式補齊；括號補上 lock 與 unlock 的 instr；交代做完之後 reclaimer 去哪。
5. **第 1 張（小修即可，不必整張重生）**：畫面與結論部分一致。
   - 結論的「seven tables」請在畫面上數得出來（例如把 `cot[h]` 也標成 indexed by h，或在七項旁邊編 1 到 7）；「each on its own cache line」要嘛畫出來，要嘛從結論拿掉。

不在重生門檻內、但建議順手補的：

- 第 3 張：步驟 11 的旗補上步驟 a 與第 6 張的去向；步驟 12 的旗補上第 6 張 `frame_write`；副標題補上 fault_rw。
- 第 9 張：定義 doorbell；小圖的三個斜線方格改成和內文一致的數量；步驟 13 的旗寫清楚是第 10 張哪一套。
- 第 2 到 10 張：圖例加一行說明藍底方塊；`tlb_inval` 與 `notify` 的底色和其他「assumed ns」步驟統一。
- 全組：`state` 與 `state[h]` 統一寫法；`pick_victim` 33 與 44 instr 的差別、清 bitmap 的單價差（5 bits 80 instr、2 bits 18 instr、7 bits 51 instr）各補一句說明；第 1 張清單補上後面用到的 `strikes`、`lz4_off`、`fresh[t]`、`free_chunks`、`tag`、low mark 與 high mark。

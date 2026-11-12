# kernel-actions 第二組（gen2）冷讀驗收報告

- 日期：2026-11-12
- 方法：只給圖、不給提示詞的冷讀（讀者只看 PNG，沒看任何提示詞、規格或其他文件）
- 範圍：kernel-actions 第二組（gen2）的 01 到 11，共 11 張
- 讀圖順序：依序一張一張讀，每張先遮住底部橫條記錄，再讀橫條核對
- 限制：小字是從圖面辨讀的，個別數字可能有辨讀誤差；凡是我加總核對過的數字都在文中列出算式

---

## 圖 01　Where the Kernel's Tables Live

**1. 人物與機器**
沒有人物。機器只有一個：右上角淺綠色方塊「LZ4 HW registers」（帶齒輪圖示），內容是 JOB_TAIL、CPL_HEAD。它沒有連到任何東西，只是擺在那裡。
方塊顏色的理解：白色方塊是 kernel 自己的記憶體區與表格；斜線填滿的「chunk pool, 275 MiB」是放壓縮資料的地方；淺綠是 LZ4 硬體；黃色便條是代價模型。

**2. 相依關係**
- 沒有步驟、沒有帶箭頭的箭頭。
- 兩條沒有箭頭的引線：「pinned area, 56 MiB」到「kernel mem, in the pinned area」方塊；「COT area, 5 MiB」到「COT area」方塊。意思是「放大看這一區」。
- 沒有藍色小旗子。
- 位址由上到下：0x80000000 pinned area 56 MiB、0x83800000 HRT area 36 MiB（not compressed）、0x85C00000 COT area 5 MiB、0x86100000 chunk pool 275 MiB、0x97400000 frame area 140 MiB、0xA0000000 結束。

**3. 資料與代價**（這張沒有步驟，改挑三個資料結構）
- state[h]：1 B，放在 pinned area 的 kernel mem，以 page h 為索引。運算與代價：這張沒寫（它只是地圖）。
- cot[h]：32 B，放在 COT area，內容是 flags、length、CRC-32、8 個 chunk number。運算與代價：沒寫。
- bitmap：8800 個 64-bit word，每個 chunk 1 bit，放在 kernel mem。運算與代價：沒寫。
- 代價模型在黃色便條：instr 數是量測值；1 instr = 1 cycle（假設）；一條新的 64 B cache line 最多 100 cycles；一次 register 寫入 50 cycles。

**4. 看不懂的線或物件**
- 「HRT area」沒有解釋 HRT 是什麼。
- 「COT」沒有展開全名。
- 「fresh_n[h]」「pins[h]」只有名字和大小，不知道用途（後面圖才用到）。
- LZ4 HW registers 方塊沒有說它在位址圖的哪裡。
- 「free_stack 4 B」放在「indexed by frame f」底下，但 stack 通常是用 top 索引，不是用 f。

**5. 圖說的一句話**
這張是位址地圖：512 MiB 的 DRAM 切成五區，kernel 的每頁、每 frame 表格都放在 pinned area，COT 另外一區，並預告後面各張的代價怎麼算。

**6. 畫面與結論**
橫條：「One page's bookkeeping is spread over seven tables indexed by h, each on its own cache line.」
部分一致。「indexed by page h」底下只列了六項（state、frame_of、fresh_n、pins、incompressible、pte），要再把另一個方塊的 cot[h] 算進去才湊到七。「each on its own cache line」畫面沒有畫 cache line，只能從「是不同陣列」推論。
數字核對：56+36+5+275+140 = 512 MiB，位址差也都對（0x3800000、0x2400000、0x500000、0x11300000、0x8C00000）；563200 × 512 B = 275 MiB；35840 × 4 KiB = 140 MiB；8800 × 64 = 563200 bit；148480 × 32 B 約 4.53 MiB，放得進 5 MiB。全部一致。

**7. 困惑指數**：2。地圖清楚，但「七張表」要讀者自己跨兩個方塊數。

**8. 可疑錯字或矛盾數字**：沒有錯字。沒有互相矛盾的數字。

---

## 圖 02　Page Fault, Part 1: Entry and Lock Hold A

**1. 人物與機器**
- 左上火柴人，坐在筆電前，頭上有驚訝線，標籤「user SW」。看起來是被 page fault 嚇到的使用者程式。它和步驟 1 之間沒有箭頭，只靠位置相鄰。
- 沒有機器圖示。步驟 1、2 是淺藍方塊（我理解為 CPU 硬體與例外進入），步驟 3 到 6 是白色方塊（kernel 軟體）。
- 灰色括號加鎖頭：「kernel, mm_lock held: lock 4 instr, unlock 2 instr」，罩住步驟 3 到 6。

**2. 相依關係**
- 步驟 1 到步驟 2，虛線黑色，標籤「rule」。
- 步驟 2 到鎖的括號（往下），虛線黑色，標籤「rule」。
- 步驟 3 到步驟 4，實線橘色，標籤「free_top」。
- 步驟 3 到步驟 5，實線橘色，標籤「state」。
- 步驟 3 到步驟 6，實線橘色，標籤「state[h]」。
- 藍色文字（不是旗子）：「4, 5, 6 do not need each other」。
- 藍色小旗子：步驟 4 貼「f, to step 7」；步驟 5 貼「COT entry, to step 7」；步驟 6 貼「rule, to step 8」。
- 沒有箭頭的：4、5、6 彼此之間。依圖例「no arrow: any order」加上藍字，我理解為三者可任意順序，都只等步驟 3。

**3. 資料與代價**
- 步驟 3 check_state：讀 kernel mem 的 state[h]（1 B）和 free_top（4 B），依 state 分支；14 instr、1 line、14 到 114 cycles。
- 步驟 4 take_frame：kernel mem，pop free_stack 得到 f，寫 frame_of[h] = f、owner[f] = h；12 instr、2 lines、12 到 212 cycles。
- 步驟 5 cot_read：COT area 的 cot[h]，讀 32 B，測 valid flag；6 instr、1 line、6 到 106 cycles。
- 都讀得出來。

**4. 看不懂的線或物件**
- 3 到 5 標「state」、3 到 6 標「state[h]」，同一個值兩種寫法，不確定是不是同一樣東西。
- 步驟 3 讀 state[h] 和 free_top 兩個地方（照圖 01 它們不在同一條 cache line），卻只算 1 line；步驟 4 碰 free_stack、frame_of[h]、owner[f] 三處卻算 2 lines。哪些算「新的 line」的規則圖上沒寫。
- 步驟 2 的代價是「assumed 600 ns」，其他是 cycles，單位不同，也沒有換算。
- 步驟 2 是淺藍，但第二行寫「kernel: h = (va - base) / 4096」，CPU 和 kernel 混在同一個方塊。
- 方塊顏色（淺藍、白）圖例沒解釋。

**5. 圖說的一句話**
使用者程式碰到不在的 page，CPU 進 kernel，kernel 拿著 mm_lock 先看 state，然後三件互不相干的事（拿 frame、讀 COT、標成 DECOMPRESSING）各自做。

**6. 畫面與結論**
橫條：「39 instr and 4 new cache lines: 39 to 439 cycles. Three of the lines are indexed by h, one by f.」
一致。加總：14+12+6+7 = 39 instr；1+2+1+0 = 4 lines；39 到 39+400 = 439 cycles。「三條以 h 索引、一條以 f」對得上 state[h]、frame_of[h]、cot[h] 與 owner[f]（代表 free_top、free_stack 不算新 line，但圖上沒說）。
注意：鎖的 lock 4 instr、unlock 2 instr 沒算進 39。

**7. 困惑指數**：2。扇出結構一眼可懂；line 的計法要猜。

**8. 可疑錯字或矛盾數字**：沒有錯字。「state」與「state[h]」標籤不一致。步驟 3 讀兩處卻算 1 line，沒有說明。

---

## 圖 03　Page Fault, Part 2: The DECOMPRESS Job, No Lock Held

**1. 人物與機器**
沒有人物。步驟 9 是淺綠方塊帶齒輪，便條寫「LZ4 HW model: 1253 ns」，我理解為 LZ4 硬體在做事。其餘白色方塊是 kernel（步驟 10 寫「interrupt entry and handler; OS wakes the sleeping thread」，是 OS 與中斷路徑，但也是白色）。沒有畫鎖，和標題「No Lock Held」相符。

**2. 相依關係**
- 步驟 7 到步驟 8，實線橘色，「descriptor」。
- 步驟 8 到步驟 9，實線橘色，「job ring」。
- 步驟 9 到步驟 10，實線橘色，「interrupt」（從 9 右側繞下來橫跨整張到 10 上方）。
- 步驟 10 到步驟 11，實線橘色，「wake-up」。
- 步驟 11 到步驟 12，虛線黑色，「rule」。
- 藍色小旗子：步驟 7 貼「f, from step 4」和「COT entry, from step 5」；步驟 8 貼「rule, from step 6」；步驟 11 貼「completion, to steps 13, 14 and 17」；步驟 12 貼「rule, to step 15」。
- 沒有箭頭的：沒有，六步是一條鏈。

**3. 資料與代價**
- 步驟 7 desc：kernel mem 的 tag 做 atomic add 1；在 stack 上填 48 B 的 descriptor；26 instr、0 lines、26 cycles。（tag 放在 kernel mem 的哪裡沒寫。）
- 步驟 8 submit：寫 job_ring[tail] 48 B；寫 HW register JOB_TAIL；13 instr、1 line、1 register write、63 到 163 cycles。
- 步驟 9 hw_decompress：讀 chunk pool 的 chunks、檢查 CRC-32；寫 frame area 的 frame[f] 4096 B；寫 cpl_ring、發 interrupt；LZ4 HW model 1253 ns。
- 步驟 12 cache_invalidate：frame[f] 的 64 條 cache line 各 invalidate 一次；「64 cache operations, time unknown」，代價缺。

**4. 看不懂的線或物件**
- 「interrupt」「wake-up」畫成橘色實線，圖例說橘色是「data: needs the value」，但這兩個是事件不是值。
- 「OS wakes the sleeping thread」：圖上沒有任何一步說這個 thread 什麼時候睡下去（推測是 submit 之後）。
- 步驟 11 寫「always from DRAM」，但便條是「1 line, 62 to 162 cycles」，下限 62 等於沒有 miss，和「always from DRAM」矛盾。
- cycles 與 ns 混用，沒有換算頻率。

**5. 圖說的一句話**
不拿鎖的一條鏈：kernel 組 descriptor、丟進 job ring、敲 register，LZ4 HW 解壓到 frame，再靠 interrupt 和 wake-up 回到 kernel 讀 completion 並清 cache。

**6. 畫面與結論**
橫條：「One chain. The kernel's three counted steps cost 151 to 351 cycles; the interrupt, the wake-up and the LZ4 HW cost 4403 ns.」
一致。26+63+62 = 151；26+163+162 = 351；1253+3150 = 4403 ns。步驟 12 沒算（time unknown），橫條說「three counted steps」，說得通。

**7. 困惑指數**：2。一條鏈很好讀；睡著的 thread 與「always from DRAM」要猜。

**8. 可疑錯字或矛盾數字**：沒有錯字。矛盾：步驟 11「always from DRAM」對上「62 to 162」。

---

## 圖 04　Page Fault, Part 3: Lock Hold B and Return

**1. 人物與機器**
- 右下火柴人坐在筆電前，表情平靜，標籤「user SW」。步驟 20 和它之間沒有箭頭。
- 步驟 19、20 是淺藍方塊（回到使用者、CPU 硬體重跑）。其餘白色是 kernel；步驟 16 寫「OS: wake threads waiting for page h」，是 OS 呼叫但也是白色。
- 鎖：「kernel, mm_lock held: lock 4 instr, unlock 2 instr」，括號只畫在上排 13、14、15、17 的上方。

**2. 相依關係**
- 步驟 14 到步驟 16，虛線黑色，「rule」。
- 步驟 a 到步驟 b，虛線黑色，「rule」。
- 步驟 17 右緣到步驟 19，虛線黑色，「all done, unlock, return」。
- 步驟 19 到步驟 20，實線橘色，「PC」。
- 藍色小旗子：步驟 13 貼「completion, from step 11」；步驟 14 貼「rule, from step 11」；步驟 15 貼「rule, from step 12」；步驟 17 貼「completion, from step 11」；步驟 18 貼「free_top, from step 4」。
- 沒有箭頭的：13、14、15、17、18、a 彼此之間都沒有。我理解為拿到鎖之後任意順序。版面順序是上排 13、14、15、17，下排 18、16、a、b，編號不是照位置排。

**3. 資料與代價**
- 步驟 15 pte_map：page table 的 pte[h] = frame address + flags，寫 8 B；6 instr、1 line、6 到 106 cycles。
- 步驟 17 note_fresh：kernel mem 的 fresh[t] 放進 h、取出 old；fresh_n[h] + 1、fresh_n[old] - 1；19 instr、2 lines、19 到 219 cycles。（fresh[t] 在圖 01 沒出現過，不知道放哪。）
- 步驟 b release_chunks：RW page only；kernel mem 的 bitmap 清 5 bits；80 instr、1 line、80 到 180 cycles。（要清哪 5 個 bit 的 chunk number 從哪來，圖上沒有箭頭或旗子。）

**4. 看不懂的線或物件**
- 鎖的括號只蓋上排，下排 18、16、a、b 算不算在鎖內，要靠橫條的數字反推（算在內）。
- 「all done, unlock, return」那條線從步驟 17 出發，看起來像只有 17 接到 19，實際意思應該是整個鎖區做完。
- 步驟 14 的旗子寫「rule, from step 11」，圖 03 的步驟 11 旗子卻是「completion, to steps 13, 14 and 17」，種類不同。
- 步驟 a 先把 cot[h] 清成 0，步驟 b 才清 bitmap；b 需要的 chunk number 應該在清掉前就留著，但沒有標示來源。
- 「strikes」「low mark」「fresh[t]」都是新名詞，圖 01 沒有。
- 步驟 16 wake_page（OS call）畫在鎖區下方，看不出是否在鎖內做。

**5. 圖說的一句話**
解壓完成後 kernel 再拿一次 mm_lock，做五件互不相干的收尾（RW page 多兩件），放鎖後 eret，CPU 重跑那道指令。

**6. 畫面與結論**
橫條：「RO page: 35 instr and 3 new lines, 35 to 335 cycles. RW page: 119 instr and 4 new lines, 119 to 519 cycles.」
一致。RO：5+3+6+19+2 = 35 instr；0+0+1+2+0 = 3 lines；35 到 335。RW：35+4+80 = 119；3+0+1 = 4 lines；119 到 519。步驟 16、19、20 與鎖的 6 instr 沒算。

**7. 困惑指數**：3。數字對得上，但鎖的範圍、出口箭頭的起點、編號與版面順序三件事都要猜。

**8. 可疑錯字或矛盾數字**：沒有錯字。步驟 14 旗子種類與圖 03 不符。沒有互相矛盾的數字。

---

## 圖 05　First Touch: A Frame of Zeros in One Lock Hold

**1. 人物與機器**
- 左上火柴人，驚訝，標籤「user SW」。旁邊藍旗「steps 1 and 2 as on sheet 2: access, exception」。
- 沒有機器。步驟 3 到 9 全是白色（kernel）。
- 鎖：「kernel, mm_lock held: lock 4 instr, unlock 2 instr」，括號罩住全部步驟；右端被藍旗「then eret and rerun as on sheet 4」蓋住一點。

**2. 相依關係**
- 步驟 3 到步驟 4，實線橘色，「free_top」。
- 步驟 3 到步驟 6，實線橘色，「state[h]」。
- 步驟 3 到步驟 8，實線橘色（從步驟 3 底部的便條彎出去的長弧線），「state」。
- 步驟 4 到步驟 5，實線橘色，「f」。
- 步驟 5 到步驟 7，虛線黑色，「rule: zeros before valid」。
- 步驟 4 到步驟 9，實線橘色，「free_top」（從步驟 4 右下出發，貼著步驟 5 的左下角穿過去）。
- 藍色小旗子：user SW 旁「steps 1 and 2 as on sheet 2: access, exception」；右上「then eret and rerun as on sheet 4」。沒有貼在單一步驟上的 from/to 旗子。
- 沒有箭頭的：6、7、8、9 彼此之間；4 與 6、8 之間。理解為任意順序。

**3. 資料與代價**
- 步驟 5 zero_frame：frame area 的 frame[f]，寫 4096 B 的零，64 條 line 不讀 DRAM 直接清零；341 instr、341 cycles。
- 步驟 7 pte_map：pte[h] = frame address + flags，寫 8 B；6 instr、1 line、6 到 106 cycles。
- 步驟 9 wake_check：kernel mem 的 free_top，和 low mark 比較；2 instr、0 lines、2 cycles。

**4. 看不懂的線或物件**
- 步驟 4 到 9 的橘線擦過步驟 5 的角落，乍看像從步驟 5 出發。
- 步驟 7 pte_map 要寫 frame address，卻沒有從步驟 4 來的「f」箭頭，只有從 5 來的 rule。
- 步驟 8 note_fresh 為什麼需要「state」，看不出來。
- 3 到 6 標「state[h]」、3 到 8 標「state」，又是兩種寫法。
- 這張的步驟 5、6、7、8、9 和圖 02、03 的同號步驟是完全不同的事（見跨圖觀察）。

**5. 圖說的一句話**
第一次碰的 page 不需要 LZ4：kernel 在一次鎖內拿 frame、填零、掛上 page table，就結束。

**6. 畫面與結論**
橫條：「397 instr and 6 new lines: 397 to 997 cycles. 341 of the instructions fill the frame with zeros.」
一致。14+12+341+3+6+19+2 = 397；1+2+0+0+1+2+0 = 6 lines；397 到 997。

**7. 困惑指數**：2。整體清楚；一條穿過別人方塊的箭頭和缺的「f」箭頭扣分。

**8. 可疑錯字或矛盾數字**：沒有錯字。沒有矛盾數字。

---

## 圖 06　When the LZ4 HW Fails: Software Rescue, or a Lost Page

**1. 人物與機器**
- 右下火柴人，雙手舉起、哭臉，小字標籤「user SW」，站在步驟 18 kill 旁邊。看起來是被 OS 結束掉的使用者程式。
- 沒有機器圖示（LZ4 HW 只出現在標題）。全部白色方塊（kernel；17、18 是 OS call）。
- 兩個大框：「decode good: fault_rescue」與「stream damaged: fault_lost」。後者裡面有鎖：「kernel, mm_lock held」（沒有寫 lock、unlock 的 instr），括號蓋住 put_frame、set_lost、wake_page。

**2. 相依關係**
- 步驟 13 到步驟 14，實線橘色，「page」。
- 步驟 14 到步驟 15（sw_clean），實線橘色，「frame[f]」。
- 步驟 13（從它的便條下方）到 fault_lost 框內鎖括號的左上角，虛線黑色，旁邊黑字「rule, to steps 15 and 16」。
- 步驟 16 到步驟 17，虛線黑色，「rule」。
- 步驟 17（鎖區右端）到步驟 18，虛線黑色，「all done, unlock」。
- 藍色小旗子：步驟 13 貼「completion says failed, from step 11」；步驟 14 貼「cache[f], from step 12」；步驟 15（sw_clean）貼「rule, to pte_map in lock hold B, as on sheet 4」。
- 藍色文字（不是旗子）：「step 14, note_hw: 5 instr, also under this lock」。
- 沒有箭頭的：15（put_frame）和 16（set_lost）之間，理解為任意順序。

**3. 資料與代價**
- 步驟 13 sw_decode：讀 chunk pool 裡 page h 的 chunks，檢查 CRC-32，解到 kernel buffer；「not measured yet」，代價缺。
- 步驟 14 frame_write：frame area 的 frame[f]，copy 4096 B 進去；「791 instr, 64 lines written」，沒有給 cycles 範圍（格式和別張的便條不同）。
- 步驟 15 put_frame：kernel mem 的 frame_of[h] = -1、owner[f] = -1，push f 到 free_stack；13 instr、0 lines、13 cycles。

**4. 看不懂的線或物件**
- 同一張圖有兩個步驟 15（sw_clean 和 put_frame）。黑字「rule, to steps 15 and 16」到底指哪個 15，要看箭頭落點才知道。
- 藍字說「step 14, note_hw」，但同一張圖的步驟 14 是 frame_write；圖 04 的 note_hw 是步驟 13。編號對不起來。
- 步驟 13 在這張是 sw_decode，圖 04 的步驟 13 是 note_hw。
- 旗子「cache[f], from step 12」：「cache[f]」是什麼沒定義；圖 03 的步驟 12 旗子只寫「rule, to step 15」，沒有提到 14。
- rescue 框沒有鎖，推測 frame_write 不在鎖內，但沒明說。
- rescue 之後接「lock hold B, as on sheet 4」是走 RO 還是 RW 的版本，圖上沒說（圖 11 的數字顯示是 RW 版，見跨圖觀察）。
- 「rule, to steps 15 and 16」是黑色純文字，不是藍旗也不像箭頭標籤，物件類型不明。

**5. 圖說的一句話**
LZ4 HW 回報失敗時，kernel 自己用軟體解一次：解得出來就把 page 抄進 frame 繼續走正常收尾，解不出來就還 frame、標 LOST、把使用者程式結束掉。

**6. 畫面與結論**
橫條：「Rescue: the copy alone is 791 instr and the software decode is not measured. Lost page: 21 instr under the lock.」
一致（要把藍字算進去）。791 與「not measured yet」對上。Lost：13+3 = 16，再加藍字的 note_hw 5 instr = 21。

**7. 困惑指數**：4。故事懂，但重複的步驟 15、對不上的「step 14, note_hw」、來源不明的「cache[f]」，讓人無法把這張接回圖 03、04。

**8. 可疑錯字或矛盾數字**：「cache[f]」疑為用詞錯誤。步驟編號 15 重複；「step 14, note_hw」與本圖的步驟 14 衝突。frame_write 的便條缺 cycles。

---

## 圖 07　Evicting an RO Page: The Clock Scan and One Lock Hold

**1. 人物與機器**
沒有人物。鎖的標籤點名「kernel reclaimer thread」，所以做事的是 kernel 的回收執行緒。全部白色方塊；步驟 4 tlb_inval 寫「CPU MMU」、代價「assumed 500 ns」，也是白色。右側有一個說明框，畫一排六個方格和「clock hand」向下的黑箭頭。

**2. 相依關係**
- 步驟 1 到步驟 2，虛線黑色，「rule」。
- 步驟 2 到步驟 6，實線橘色，「state[h]」。
- 步驟 2 到步驟 3，實線橘色，「victim」。
- 步驟 3 到步驟 4，虛線黑色，「rule」。
- 步驟 4 到步驟 5，虛線黑色，「rule」。
- 藍色小旗子：步驟 1 貼「woken when free_top is at the low mark」（不是 from/to 旗子）。
- 沒有箭頭的：步驟 6 和 3、4、5 之間。理解為 set_compressed 在 pick_victim 之後任何時候做都行。

**3. 資料與代價**
- 步驟 2 pick_victim：kernel mem 的 owner[hand]，然後 hand + 1；state[h]、pins[h]、fresh_n[h]；page table 的 pte[h]，測 bit 10；33 instr、4 lines、33 到 433 cycles。
- 步驟 3 pte_clear：pte[h] = 0，寫 8 B；2 instr、0 lines、2 cycles。
- 步驟 5 put_frame：frame_of[h] = -1、owner[f] = -1，push f 到 free_stack；13 instr、1 line、13 到 113 cycles。

**4. 看不懂的線或物件**
- 步驟 2 列了五個陣列（owner、state、pins、fresh_n、pte）卻算 4 lines，哪一個不算沒說。
- 「test bit 10」是什麼旗標沒說（右框有「accessed page, flag cleared」，推測是 accessed bit）。
- 右框「incompressible RW page: 33 instr, 3 lines」和步驟 2 的「33 instr, 4 lines」同樣是 33，容易以為是同一筆，但 line 數不同。
- 右框「measured run: 4.9 frames per pick, longest 35841」：35841 沒有單位，而且比圖 01 的 35840 frames 多 1。
- 步驟 1 和「high mark」比，旗子卻說在「low mark」被叫醒，兩個門檻的關係沒說明。
- tlb_inval 的 500 ns 是不是在鎖內等，括號只畫在上排，看不出來。

**5. 圖說的一句話**
回收執行緒在一次鎖內用 clock hand 挑一個 RO page，清 pte、清 TLB、還 frame、標成 COMPRESSED；因為 chunk 裡本來就有內容，不必叫 LZ4。

**6. 畫面與結論**
橫條：「53 instr and 5 new lines: 53 to 553 cycles, plus the assumed 500 ns. Every frame passed adds up to 4 more lines.」
一致。2+33+3+2+13 = 53；0+4+0+0+1 = 5 lines；53 到 553；500 ns 對上步驟 4；「up to 4 more lines」對上右框最大的 4 lines。

**7. 困惑指數**：2。流程清楚；右框的數字和步驟 2 的關係要想一下。

**8. 可疑錯字或矛盾數字**：沒有錯字。「longest 35841」缺單位且與 35840 差 1。五個陣列對 4 lines。

---

## 圖 08　Evicting an RW Page, Part 1: Lock Hold A and the Bitmap Search

**1. 人物與機器**
沒有人物。鎖標籤「kernel reclaimer thread, mm_lock held: lock 4 instr, unlock 2 instr」。全部白色方塊。右側說明框「inside reserve: find a free bit」，畫一條十格的長條（灰色是已用、白色是空的），其中一格白的被橘色圓圈圈起來。

**2. 相依關係**
- 步驟 1 到步驟 2，虛線黑色，「rule」。
- 步驟 2 到步驟 3，實線橘色，「victim」。
- 步驟 2 到步驟 4，實線橘色，「victim」。
- 步驟 2 到步驟 5，實線橘色，「victim」。
- 步驟 2 到步驟 7，實線橘色，「state[h]」。
- 步驟 5 到步驟 6，虛線黑色，「rule」。
- 藍色小旗子：步驟 3 貼「chunk numbers, to step 9」；步驟 4 貼「f, to steps 8 and 9」；步驟 6 貼「rule, to step 8」；步驟 7 貼「rule, to step 10」。
- 沒有箭頭的：3、4、5、7 彼此之間，理解為任意順序。

**3. 資料與代價**
- 步驟 2 pick_victim：owner[hand]、state[h]、pins[h]、fresh_n[h]；pte[h] 測 bit 10；44 instr、4 lines、44 到 444 cycles。
- 步驟 3 reserve：kernel mem 的 bitmap[cursor] 設 7 bits；free_chunks - 7；111 instr、1 line、111 到 211 cycles。
- 步驟 4 find_frame：kernel mem 的 frame_of[h]，讀 4 B；5 instr、1 line、5 到 105 cycles。

**4. 看不懂的線或物件**
- pick_victim 在圖 07 是 33 instr，這裡是 44 instr，文字幾乎一樣，差別原因沒寫。
- 為什麼是 reserve 7 個 chunk（圖 01 的 cot 可放 8 個 chunk number）沒說明。
- 「free_chunks」是新的 scalar，圖 01 沒列。
- pick_victim 已經用 owner[hand] 找到 h（f 就是 hand），為什麼還要 find_frame 讀 frame_of[h]，看不懂。
- 右框「about 14 instr per chunk, 7 per word passed」：14 × 7 + 7 × 1.06 約 105，和步驟 3 的 111 差 6，沒交代。

**5. 圖說的一句話**
回收執行緒在第一次鎖內挑一個 RW page，在 bitmap 裡先訂 7 個 chunk，查出 frame，拔掉 pte 與 TLB，標成 COMPRESSING。

**6. 畫面與結論**
橫條：「167 instr and 6 new lines: 167 to 767 cycles, plus the assumed 500 ns.」
一致。2+44+111+5+2+3 = 167；0+4+1+1+0+0 = 6 lines；167 到 767；500 ns 對上步驟 6。

**7. 困惑指數**：2。扇出清楚，右框把 bitmap 搜尋講得明白。

**8. 可疑錯字或矛盾數字**：沒有錯字。pick_victim 33 對 44（跨圖）；reserve 111 對右框推得的約 105。

---

## 圖 09　Evicting an RW Page, Part 2: The COMPRESS Job, No Lock Held

**1. 人物與機器**
沒有人物。步驟 11 淺綠帶齒輪，「LZ4 HW model: 4260 ns」，是 LZ4 硬體。它上方有個小圖：一個白方格、黑箭頭、三個斜線方格（一頁壓成幾塊）。其餘白色是 kernel；步驟 12 寫「OS wakes the reclaimer thread」。沒有鎖。

**2. 相依關係**
- 步驟 8 到步驟 10，虛線黑色（上方長弧線），「rule: clean before doorbell」。
- 步驟 9 到步驟 10，實線橘色，「descriptor」。
- 步驟 10 到步驟 11，實線橘色，「job ring」。
- 步驟 11 到步驟 12，實線橘色，「interrupt」。
- 步驟 12 到步驟 13，實線橘色，「wake-up」。
- 藍色文字：「8 and 9 do not need each other」。
- 藍色小旗子：步驟 8 貼「f, from step 4」和「rule, from step 6」；步驟 9 貼「chunk numbers, from step 3」；步驟 10 貼「rule, from step 7」；步驟 13 貼「completion, to steps 14 to 18」。
- 沒有箭頭的：8 和 9 之間，藍字明說互不需要。

**3. 資料與代價**
- 步驟 8 cache_clean：frame area 的 frame[f]，64 條 cache line，把 dirty line 寫回 DRAM；「64 cache operations, time unknown」，代價缺。
- 步驟 9 desc：kernel mem 的 tag 做 atomic add 1；stack 上填 48 B descriptor，含 7 個 chunk number；55 instr、0 lines、55 cycles。
- 步驟 11 hw_compress：讀 frame[f] 4096 B；把 stream 寫進 chunk pool、算 CRC-32；寫 cpl_ring、發 interrupt；4260 ns。

**4. 看不懂的線或物件**
- 「doorbell」沒有定義，推測是步驟 10 的「write JOB_TAIL」。
- 副標「three things must be ready」：兩條箭頭加一面「rule, from step 7」旗子才湊成三件，要自己數。
- 圖 08 的步驟 4 旗子寫「f, to steps 8 and 9」，但這張的步驟 9 沒有「f, from step 4」旗子。
- 步驟 13「always from DRAM」對「62 to 162 cycles」，和圖 03 同樣的矛盾。
- 「interrupt」「wake-up」用資料色（橘色）畫事件，同圖 03。

**5. 圖說的一句話**
不拿鎖的壓縮工作：先把 frame 的 cache 寫回、組好 descriptor、狀態已標好，三件齊了才敲 doorbell，LZ4 HW 壓完用 interrupt 叫醒回收執行緒。

**6. 畫面與結論**
橫條：「The kernel's three counted steps cost 180 to 380 cycles; the LZ4 HW takes 4260 ns, the interrupt and wake-up 3150 ns.」
一致。55+63+62 = 180；55+163+162 = 380；4260 與 3150 對上。

**7. 困惑指數**：2。和圖 03 同一個版型，很好讀。

**8. 可疑錯字或矛盾數字**：沒有錯字。「always from DRAM」對「62 to 162」。

---

## 圖 10　Evicting an RW Page, Part 3: Lock Hold B, Two Outcomes

**1. 人物與機器**
沒有人物、沒有機器。全部白色方塊。左框「the page fits: 5 of 7 chunks used」，鎖標籤「kernel reclaimer thread, mm_lock held」；右框「the page does not fit: undo」，鎖標籤「mm_lock held, undo」（沒寫是誰拿鎖）。兩個鎖都沒寫 lock、unlock 的 instr。

**2. 相依關係**
- 左框：步驟 15 到步驟 17，虛線黑色，「rule: COT entry before the frame is free」。
- 左框：步驟 18 到步驟 19，虛線黑色，「rule」。
- 右框：沒有任何箭頭。
- 藍色小旗子：左框頂「every step here needs the completion from step 13」；右框底藍框「step 14 as on the left; then wake_page after step 17」。
- 沒有箭頭的：左框 14、15、16、18 彼此之間；右框 15、16、17、18 全部。理解為任意順序。右框的 wake_page 只用文字交代，沒有方塊。

**3. 資料與代價**
- 左 15 cot_store：COT area 的 cot[h]，寫 32 B（flags、length、CRC-32、5 個 chunk number）；44 instr、1 line、44 到 144 cycles。
- 左 16 trim：kernel mem 的 bitmap，清掉 2 個多訂的 bit；18 instr、0 lines、18 cycles。
- 右 15 release_all：kernel mem 的 bitmap，清掉全部 7 個 bit；51 instr、0 lines、51 cycles。

**4. 看不懂的線或物件**
- 同一張圖裡 15、16、17、18 各出現兩次，左右意思完全不同（左 17 是 put_frame，右 17 是 set_present）。右框藍字「after step 17」指的是右邊的 17，但要想一下。
- 「does not fit」是放不進什麼（推測是 7 個 chunk，3584 B），沒寫。
- 清 bitmap 的單價不一致：圖 04 release_chunks 清 5 bit 要 80 instr，這裡 release_all 清 7 bit 只要 51 instr，trim 清 2 bit 要 18 instr。
- 右 16 mark_incompressible 設 incompressible 的 bit，算 0 lines，但前面沒有任何一步讀過那張表。
- 右框沒有從步驟 13 來的旗子（左框有）。

**5. 圖說的一句話**
壓縮完成後第二次拿鎖：壓得進去就寫 COT、退回多訂的 chunk、還 frame、標 COMPRESSED；壓不進去就全部退回、標記不可壓、把 page 掛回去。

**6. 畫面與結論**
橫條：「Fits: 83 instr and 1 new line, 83 to 183 cycles. Does not fit: 73 instr and 0 new lines, 73 cycles.」
一致。Fits：5+44+13+18+3 = 83，1 line，83 到 183。Does not fit：51+8+3+6 = 68，加藍字說的步驟 14（5 instr）= 73，0 lines。

**7. 困惑指數**：3。兩個結果並排很好，但一張圖裡四個編號各用兩次，右框又靠文字補步驟。

**8. 可疑錯字或矛盾數字**：沒有錯字。步驟編號 15 到 18 重複。清 bitmap 單價與圖 04 不成比例。

---

## 圖 11　Eight Scenarios: What the Kernel's Own Steps Cost

**1. 人物與機器**
沒有人物。這是一張表，沒有方塊顏色分類；只有「instr」「new lines」兩個欄頭塗黃。

**2. 相依關係**
沒有箭頭、沒有旗子、沒有步驟。

**3. 資料與代價**（挑三列）
- first_touch：403 instr、6 new lines、403 到 1003 kernel cycles；assumed CPU and OS 1000 ns；LZ4 HW none。
- fault_ro：137 instr、9 lines、237 到 1137 cycles；4150 ns；1253 ns。
- evict_rw：342 instr、9 lines、442 到 1342 cycles；3650 ns；4260 ns。
完整表：fault_rw 221／10／321 到 1321／4150／1253；fault_rescue 1012／10／1112 到 2112／4150／1253；fault_lost 123／6／223 到 823／3750／1253；evict_ro 59／5／59 到 559／500／none；evict_rw_incompressible 332／8／432 到 1232／3650／4260。
表下藍字：「Not in these sums: cache maintenance of a frame, 64 operations, and the software decode.」

**4. 看不懂的線或物件**
- 表裡的 instr 比前面各張橫條的加總多（例如 first_touch 403 對圖 05 的 397），表上沒說多的是什麼。
- cycles 和 ns 並列，沒有換算，讀者無法比較兩欄誰大。
- fault_rescue 的 1012 怎麼來，圖 06 的資訊不夠算。

**5. 圖說的一句話**
八個場景裡 kernel 自己的表格工作各花多少指令、幾條新 cache line、多少 cycles，旁邊列出假設的 CPU、OS 開銷與 LZ4 HW 的時間。

**6. 畫面與結論**
橫條：「The kernel's table work is 59 to 2112 cycles - waiting for the CPU, the OS and the LZ4 HW is 500 to 7910 ns.」
一致。最小 59（evict_ro）、最大 2112（fault_rescue）；最小 500（evict_ro）、最大 3650+4260 = 7910（evict_rw）。

**7. 困惑指數**：2。表本身清楚；和前面橫條的差額要自己推。

**8. 可疑錯字或矛盾數字**：橫條中間用「 - 」當連接號，其他張沒有這種寫法。表內沒有互相矛盾的數字。

---

## 跨圖觀察

### 命名物件長得一不一樣

- **步驟方塊**：02 到 10 都是白色圓角方塊、左上橘色圓形編號、粗體名稱、底部壓著一張黃色便條。一致，沒有走樣。
- **黃色代價便條**：外觀一致。文字格式大多是「N instr, N lines, a to b cycles」，例外有：「assumed N ns」「LZ4 HW model: N ns」「OS call, not counted」「CPU hardware, not counted」「64 cache operations, time unknown」「not measured yet」，以及圖 06 的「791 instr, 64 lines written」（沒有 cycles，是唯一不合格式的）。
- **鎖的括號**：鎖頭加灰色上括號，外觀一致。文字有五種寫法：「kernel, mm_lock held: lock 4 instr, unlock 2 instr」（02、04、05）、「kernel reclaimer thread, mm_lock held: lock 4 instr, unlock 2 instr」（07、08）、「kernel, mm_lock held」（06）、「kernel reclaimer thread, mm_lock held」（10 左）、「mm_lock held, undo」（10 右）。括號都只有上緣，圖 04、07 有兩排步驟時看不出下排在不在鎖內。
- **藍色小旗子**：都是藍框藍字，但形狀不固定：缺角緞帶（02、04、08、09）、對話框尖角（03 的步驟 8、06 的步驟 14）、箭頭形（10 左）、圓角方框（10 右）。另外有三處用沒有框的藍字（02「4, 5, 6 do not need each other」、09「8 and 9 do not need each other」、06「step 14, note_hw…」），以及一處黑色純文字當旗子用（06「rule, to steps 15 and 16」）。
- **圖例**：02 到 10 右上角都有，內容相同（橘色實線 data、黑色虛線 rule、no arrow any order）。01、11 沒有圖例（也不需要）。圖例都沒有解釋方塊顏色。
- **底部橫條**：外觀一致，左格標籤每張不同（Key point、Lock hold A、Part 2、Lock hold B、One lock hold、Cost、Reading）。左格底色多數是淺藍，圖 11 是白底藍框，圖 07 是橫條內再包一個藍框。
- **圖號方塊**：都是左上橘色方塊，深淺與有無黑框略有出入（07 最飽和、沒有黑框）。

### 分類顏色

- **白色**：kernel 軟體的步驟。但 OS call（wake_page、kill）、interrupt 與 wake-up（notify）、CPU MMU（tlb_inval）也都是白色。
- **淺藍**：只在 02（步驟 1、2）和 04（步驟 19、20）出現，代表 CPU 硬體與例外進出。不一致之處：同樣是「assumed N ns」的非 kernel 開銷，exception 和 eret 是淺藍，notify（3150 ns）和 tlb_inval（500 ns）卻是白色。
- **淺綠**：LZ4 HW（01 的 registers、03 的步驟 9、09 的步驟 11），每張一致，都帶齒輪。
- **黃色**：代價便條與代價模型，一致。圖 11 用黃色塗兩個欄頭，意思略有不同。
- **斜線**：壓縮資料（01 的 chunk pool、09 的小圖），一致。

### 跨圖小旗子對不對得起來

對得起來的：
- 02 步驟 4「f, to step 7」對 03 步驟 7「f, from step 4」。
- 02 步驟 5「COT entry, to step 7」對 03 步驟 7「COT entry, from step 5」。
- 02 步驟 6「rule, to step 8」對 03 步驟 8「rule, from step 6」。
- 03 步驟 12「rule, to step 15」對 04 步驟 15「rule, from step 12」。
- 03 步驟 11「completion, to steps 13, 14 and 17」對 04 步驟 13、17「completion, from step 11」。
- 08 步驟 3「chunk numbers, to step 9」對 09 步驟 9「chunk numbers, from step 3」。
- 08 步驟 6「rule, to step 8」對 09 步驟 8「rule, from step 6」。
- 08 步驟 7「rule, to step 10」對 09 步驟 10「rule, from step 7」。
- 08 步驟 4「f, to steps 8 and 9」對 09 步驟 8「f, from step 4」。
- 09 步驟 13「completion, to steps 14 to 18」對 10 左框「every step here needs the completion from step 13」。

對不起來的：
- 03 步驟 11 說給 14 的是「completion」，04 步驟 14 的旗子卻寫「rule, from step 11」。
- 04 步驟 18「free_top, from step 4」，02 的步驟 4 沒有對應的「to step 18」。
- 08 步驟 4 說 f 也給步驟 9，09 的步驟 9 沒有「f, from step 4」。
- 06 步驟 14「cache[f], from step 12」，03 的步驟 12 只有「rule, to step 15」，沒有給 14 的旗子，名稱也不同。
- 06 藍字「step 14, note_hw」，04 的 note_hw 是步驟 13。
- 09 說 completion 給 14 到 18，10 左框有步驟 19（靠 rule 接在 18 後面，勉強說得通），10 右框沒有任何 from 旗子。
- 04 的步驟 a、b 需要步驟 5 讀到的 COT entry（chunk number），兩邊都沒有旗子。

步驟編號的衝突：
- 編號是每個場景各自從頭編的，旗子只寫「step N」不寫哪一張。fault 系列用 1 到 20；first_touch 重用 3 到 9（步驟 5 在 02 是 cot_read，在 05 是 zero_frame）；evict 系列又從 1 開始（09 的「f, from step 4」指 find_frame，03 的「f, from step 4」指 take_frame）。
- 06、10 在同一張圖內就有重複編號（06 兩個 15；10 的 15、16、17、18 各兩個）。
- 06 的步驟 13、14 和 04 的步驟 13、14 是不同的事。

### 圖 11 的表和前面各圖的數字

全部對得起來，但要先猜出兩條沒寫在表上的規則：每一次拿鎖要加 6 instr（lock 4、unlock 2），每一次 register 寫入要加 50 cycles。

- first_touch：397（圖 05）+ 6 = 403；6 lines；403 到 1003。assumed 1000 = 600（exception）+ 400（eret）。
- fault_ro：39（02）+ 51（03 的 26+13+12）+ 35（04）+ 12（兩次鎖）= 137；lines 4+2+3 = 9；137 + 100（兩次 register write）= 237，到 1137。assumed 600+3150+400 = 4150。LZ4 1253。
- fault_rw：39+51+119+12 = 221；lines 4+2+4 = 10；321 到 1321。
- fault_rescue：39+51+791+119+12 = 1012；lines 10；1112 到 2112。只有把 lock hold B 當成 RW 版（119 instr、4 lines）才對得上；若用 RO 版會得到 928。圖 06 沒有說 rescue 走 RW 版。
- fault_lost：39+51+21+12 = 123；lines 4+2+0 = 6；223 到 823。assumed 600+3150 = 3750（沒有 eret）。
- evict_ro：53（07）+ 6 = 59；5 lines；59 到 559。assumed 500。
- evict_rw：167（08）+ 80（09 的 55+13+12）+ 83（10 左）+ 12 = 342；lines 6+2+1 = 9；442 到 1342。assumed 500+3150 = 3650。LZ4 4260。
- evict_rw_incompressible：167+80+73+12 = 332；lines 6+2+0 = 8；432 到 1232。
- 橫條的 59 到 2112 cycles 與 500 到 7910 ns 都對。

### 數字不一致與可疑數字（彙整）

1. 各張橫條的 instr 不含 lock、unlock 的 6 instr，圖 11 含。例如 397 對 403、53 對 59。可以對起來，但兩邊都沒寫明。
2. 圖 03 步驟 11、圖 09 步驟 13：「always from DRAM」對「62 to 162 cycles」，下限代表沒有 miss，自相矛盾。
3. 新 cache line 的計法沒有規則：圖 02 步驟 3 讀 state[h] 和 free_top 算 1 line；步驟 4 碰三處算 2 lines；圖 07、08 步驟 2 列五個陣列算 4 lines。
4. pick_victim 在圖 07 是 33 instr，在圖 08 是 44 instr，方塊文字幾乎相同。圖 07 右框另有一筆「33 instr, 3 lines」。
5. 清 bitmap 的單價：80 instr 清 5 bit（圖 04）、51 instr 清 7 bit、18 instr 清 2 bit（圖 10）。reserve 111 instr 對右框推得的約 105（圖 08）。
6. 同名步驟不同 line 數：put_frame 是 1 line（圖 07）或 0 lines（圖 06、10）；pte_map 是 1 line（圖 04、05）或 0 lines（圖 10 右）。可能有理由，但沒寫。
7. fault_rescue 的 1012 需要假設 lock hold B 是 RW 版，圖 06 沒交代。
8. 圖 07「longest 35841」沒有單位，比圖 01 的 35840 frames 多 1。
9. 圖 10 右 mark_incompressible 算 0 lines，但前面沒有步驟讀過 incompressible 那張表。
10. cycles 和 ns 全組都沒有換算（沒有給 CPU 頻率），圖 11 的結論無法把兩邊放在同一把尺上比。

### 故事線

順的部分：01 給地圖與代價模型；02、03、04 是一次解壓 page fault 的三段（鎖 A、不拿鎖的 HW 工作、鎖 B 與返回）；05 是不需要 HW 的簡單版；06 是 HW 失敗的兩條岔路；07 是不需要 HW 的回收；08、09、10 是回收 RW page 的三段，和 02 到 04 同一個「鎖 A、HW、鎖 B」節奏；11 收總帳。兩個三段式互相呼應，讀到 08 時已經知道會發生什麼。

斷掉的地方：
- 「誰要等誰」沒有被畫出來。圖上只看得到單一 thread 的步驟順序；別的 thread 在等 mm_lock、或在等 page h，只在「wake threads waiting for page h」一句話裡出現，沒有任何一張畫出等待者。
- 發出 job 的 thread 什麼時候睡下去，沒有步驟。
- 圖 06 接不回圖 03、04（編號與旗子對不上），也沒說 rescue 走哪一版的鎖 B。
- 圖 04 的 wake_check 與圖 07 的「woken when free_top is at the low mark」應該是同一件事的兩端，但兩邊沒有互指的旗子。
- cycles 與 ns 沒有換算，結論的兩個範圍無法直接比大小。

我用自己的話說這組圖的結論：
每頁的帳分散在七張以 h 索引的表，所以 kernel 每個場景要碰 5 到 10 條新的 cache line；kernel 自己的表格工作其實很少，約 59 到 2112 cycles，多數場景的代價主要取決於這些 cache line 有沒有 miss，再加上填零或抄 4 KiB。mm_lock 只在很短的兩段（鎖 A、鎖 B）裡拿著，LZ4 HW 工作在兩段之間不拿鎖。每段鎖內的相依關係幾乎都是「第一步讀出 state 或挑出 victim，之後的幾步互不相干」。真正長的時間是 kernel 以外的東西：例外進出、interrupt 加 wake-up（假設 3150 ns）、以及 LZ4 HW（解壓 1253 ns、壓縮 4260 ns），合計 500 到 7910 ns。

### 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|
| 01 | 2 | 是（沒有人物；LZ4 HW registers 有標籤） | 部分一致（七張表要跨兩個方塊數；cache line 沒畫） |
| 02 | 2 | 是 | 一致（39、4、39 到 439） |
| 03 | 2 | 是 | 一致（151 到 351、4403） |
| 04 | 3 | 是 | 一致（35 與 119） |
| 05 | 2 | 是 | 一致（397、6、397 到 997） |
| 06 | 4 | 是（但步驟對不回前圖） | 一致（791；21 要加藍字的 5） |
| 07 | 2 | 是（沒有人物；鎖標籤點名 reclaimer thread） | 一致（53、5、53 到 553） |
| 08 | 2 | 是 | 一致（167、6、167 到 767） |
| 09 | 2 | 是 | 一致（180 到 380、4260、3150） |
| 10 | 3 | 部分（右框的鎖沒寫誰拿） | 一致（83 與 73，73 要加藍字的 5） |
| 11 | 2 | 是（沒有人物） | 一致（59 到 2112、500 到 7910） |

### 建議重生

1. **圖 06**（困惑指數 4）：同一張圖兩個步驟 15；藍字「step 14, note_hw」與本圖步驟 14、與圖 04 的步驟 13 都衝突；旗子「cache[f], from step 12」名稱不明且圖 03 沒有對應；「rule, to steps 15 and 16」是黑色純文字；frame_write 便條缺 cycles；沒說 rescue 接 RW 版的鎖 B（圖 11 的 1012 靠這個）。
2. **圖 04**（困惑指數 3）：鎖的括號只蓋上排；「all done, unlock, return」從步驟 17 出發，看起來像單一步驟的相依；步驟 14 旗子種類與圖 03 不符；a、b 缺 chunk number 的來源；版面順序 13、14、15、17／18、16、a、b 和編號不對應。
3. **圖 10**（困惑指數 3）：15 到 18 在左右框各用一次；右框靠藍字補步驟 14 與 wake_page，沒有箭頭也沒有 from 旗子；右框的鎖沒寫誰拿。
4. **圖 03 與圖 09**（同一張圖內數字矛盾）：cpl_read 的「always from DRAM」對「62 to 162 cycles」。只要改這一張便條或那一句話；如果圖是整張生成、不能局部改，就要重生。

不需要重生、但值得補一筆的：
- 圖 02：步驟 4 補「free_top, to step 18」；「state」與「state[h]」統一。
- 圖 05：步驟 4 到 9 的箭頭改道，不要擦過步驟 5；補步驟 4 到 7 的「f」。
- 圖 09：步驟 9 補「f, from step 4」。
- 圖 07：「longest 35841」補單位。
- 圖 11：加一行註明「每次拿鎖加 6 instr、每次 register 寫入加 50 cycles」，並註明 fault_rescue 用的是 RW 版鎖 B。
- 全組：圖例加一行方塊顏色的說明；旗子若跨圖，寫上是哪一張的步驟。

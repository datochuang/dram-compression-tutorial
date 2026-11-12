# kernel-actions 白板圖冷讀驗收報告（gen4）

- 日期：2026-11-12
- 方法：只給圖、不給提示詞的冷讀。讀者只拿到一段兩三句的背景，沒有看過任何提示詞、規格或其他文件。
- 範圍：kernel-actions 這一組的十二張圖（01 到 11，其中 06 分成 06A 與 06B）。
- 讀法：每張先遮住底部結論，只看畫面記錄，再讀結論比對；底部有加總的，都用圖上方塊的數字重新加過一次。

---

## 01　Where the Kernel's Tables Live

**1. 人物與機器**

- 沒有人物，也沒有步驟方塊。這張是位址地圖。
- 左邊一條記憶體地圖，0x80000000 到 0xA0000000，由上到下五段：pinned area 56 MiB、HRT area 36 MiB（not compressed）、COT area 5 MiB、chunk pool 275 MiB（斜線）、frame area 140 MiB。
- 中間兩個白框：「kernel mem, in the pinned area」列出依 page h 索引的六項（state[h]、frame_of[h]、fresh_n[h]、pins[h]、incompressible、pte[h]）、依 frame f 索引的兩項（owner[f]、free_stack）、others（bitmap、scalars、job ring、completion ring）；「COT area」列出 cot[h] 32 B。
- 右上綠框（齒輪圖示）：「LZ4 HW registers」JOB_TAIL、CPL_HEAD。這是唯一的機器，看得出是硬體。
- 右下黃色便利貼：「Cost model on the next sheets」四條計價規則。
- 這張沒有步驟，所以沒有「誰做」和 lock 的問題。

**2. 看不懂的線或物件**

- LZ4 HW registers 沒有連到位址地圖，看不出暫存器在哪個位址，也看不出為什麼和記憶體地圖放在同一張。
- pinned area 有 56 MiB，但列出來的表加起來只有幾 MiB，其餘放什麼沒有說。
- 縮寫沒有解釋：HRT、COT、h、f、hand、cursor、fresh_n、pins。
- chunk pool 的斜線沒有圖例，要到 09 才猜得出斜線是「壓縮過的資料」。

**3. 圖說的一句話**

kernel 的每一張表放在 512 MiB 位址空間的哪一段、每筆多大、用 page 還是 frame 索引，以及後面幾張圖怎麼計價。

**4. 畫面與結論**

一致。結論說「七張以 h 索引的表：kernel mem 六張加 cot[h]」，照圖數是 6 + 1 = 7，對。「each in a different cache line」是結論自己說的，畫面沒有畫出來，只能相信。
另外自行核對：五段大小與位址差全部吻合；563200 × 512 B = 275 MiB、35840 × 4 KiB = 140 MiB、8800 × 64 = 563200 bit，都對。

**5. 困惑指數**：2。地圖本身一看就懂，但縮寫全沒解釋，暫存器框是孤島。

**6. 可疑的錯字或多餘文字**

- 「incompressible, 1 bit」沒有寫 [h]，和同一組其他五項格式不一致。
- 「free_stack 4 B」放在「indexed by frame f」底下，但它看起來不是用 f 索引。
- 沒有錯字。

---

## 02　Page Fault, Part 1: Entry and Lock Hold A

**1. 人物與機器**

- 左上火柴人，標籤「user SW」，坐在筆電前，表情驚訝。沒有箭頭連到任何步驟，只能靠位置猜他是步驟 1 的發起者。
- 步驟 1 access（藍底）：黃色便條寫「CPU hardware, not counted」，看得出是 CPU。
- 步驟 2 exception（藍底）：內文寫「CPU saves the PC, enters the kernel」和「kernel: h = ...」，一格裡有兩個執行者。
- 步驟 3 到 6（白底）：在灰色括號底下，括號寫「kernel, mm_lock held: lock 4 instr, unlock 2 instr」，看得出是 kernel 握著 mm_lock 做的。
- 每一步誰做、有沒有握 lock：看得出來。

**2. 看不懂的線或物件**

- 步驟 3 出來三條橘線，標籤分別是 free_top、state、state[h]。同一個值為什麼一條叫 state、一條叫 state[h]，看不出差別。
- 「pte[h], bit 0 is 0」沒說 bit 0 是什麼意思（猜是 present bit）。
- 步驟 2 的成本是「600 ns」，其他步驟是 cycles，這張沒有說怎麼換算。
- 藍色旗標對照：「f, to step 7」「COT entry, to step 7」「rule, to step 8」在 03 都有對應的 from 旗標；「free_top, to step 18」在 04 的步驟 18 有對應。全部對得上。
- 步驟 3 讀 state[h] 和 free_top 兩樣東西卻只算 1 line；步驟 4 碰 free_stack、frame_of[h]、owner[f] 三樣卻只算 2 lines。哪一樣不算新的 cache line，方塊裡看不出來。

**3. 圖說的一句話**

user SW 碰到不在的 page，CPU 進 kernel，kernel 握著 mm_lock 先查狀態，再做三件互不相干的事：拿 frame、讀 COT entry、把狀態標成 DECOMPRESSING。

**4. 畫面與結論**

一致。自己加：指令 14 + 12 + 6 + 7 = 39，對；cache line 1 + 2 + 1 + 0 = 4，對；cycles 39 到 39 + 400 = 439，對。
「三條以 h 索引、一條以 f 索引」要回頭推（state[h]、frame_of[h]、cot[h] 加 owner[f]），推得出來，也順便解開了上面 line 數的疑問。
要注意：括號上寫的 lock 4 instr、unlock 2 instr 沒有算進 39，結論沒有交代。

**5. 困惑指數**：2。流程清楚，只有 line 數怎麼算和 lock 的 6 個指令算不算要猜。

**6. 可疑的錯字或多餘文字**

- 「state」和「state[h]」兩種寫法。
- 沒有錯字。

---

## 03　Page Fault, Part 2: The DECOMPRESS Job, No Lock Held

**1. 人物與機器**

- 沒有人物。
- 步驟 9 hw_decompress（綠底、齒輪）：便條「LZ4 HW model: 1253 ns」，清楚是 LZ4 HW。
- 步驟 10 notify（白底）：內文「interrupt entry and handler」「OS wakes the sleeping thread」，執行者是 OS。
- 步驟 7 desc、8 submit、11 cpl_read、12 cache_invalidate（白底）：方塊上沒有寫誰做。只能從「kernel mem」「stack」和底部結論的「the kernel's three counted steps」推回去是 kernel。
- lock：只有標題寫「No Lock Held」，畫面上沒有任何標記，是靠「沒有括號」來表示。
- 「OS」和「kernel」是不是同一個東西，這張第一次出現這個疑問，整組都沒有說明。

**2. 看不懂的線或物件**

- 橘線在圖例裡是「data: needs the value」，但標籤是「interrupt」「wake-up」，這兩個是事件，不是值。
- 步驟 12 為什麼要 invalidate 64 條 cache line，圖上沒說原因（猜是 HW 繞過 CPU cache 直接寫 DRAM）。
- thread 什麼時候睡著沒有畫，只在步驟 10 出現「the sleeping thread」。
- 步驟 7 的「tag」在 01 的表裡找不到。
- 藍色旗標對照：「f, from step 4」「COT entry, from step 5」「rule, from step 6」與 02 吻合；「rule, to step 15」與 04 吻合。步驟 11 下方的「to sheet 4: completion for steps 13 and 17, rule for step 14」與 04 的 13、14、17 吻合，但 04 的步驟 a 也掛著「completion, from step 11」，這裡沒有列到 a。

**3. 圖說的一句話**

不握 lock 的一條單鏈：kernel 填 descriptor、寫進 job ring 並敲暫存器，LZ4 HW 解壓寫入 frame，interrupt 叫醒 thread，kernel 讀 completion 再把 frame 的 cache 清掉。

**4. 畫面與結論**

一致。自己加：26 + (63 到 163) + 162 = 251 到 351，對；1253 + 3150 = 4403 ns，對。
結論只說「three counted steps」，沒有提步驟 12 是「64 cache operations, time unknown」。字面上沒錯，但有一筆未知成本沒在結論露面。

**5. 困惑指數**：2。單鏈很好讀，只是執行者要推論、no lock 沒有視覺標記。

**6. 可疑的錯字或多餘文字**：沒有發現。

---

## 04　Page Fault, Part 3: Lock Hold B and Return

**1. 人物與機器**

- 右下火柴人「user SW」，坐在筆電前微笑。沒有箭頭連到他。
- 灰框裡八個白底步驟（13、14、15、17、18、16、a、b），上方括號寫「kernel, mm_lock held for both rows」，看得出是 kernel 握 lock。
- 步驟 16 wake_page 內文寫「OS: wake threads waiting for page h」，便條「OS call, not counted」，是 OS。
- 步驟 19 eret、20 rerun（藍底）在灰框外；20 的便條寫「CPU hardware, not counted」，19 沒有寫誰做（猜是 kernel 下指令、CPU 執行）。
- 灰框右緣有開鎖圖示，虛線「all done, unlock, return」指向 19。
- 每一步誰做、有沒有握 lock：看得出來。

**2. 看不懂的線或物件**

- 編號不照位置排：上排是 13、14、15、17，下排是 18、16、a、b。要找 16 得跳到下排第二格。
- a、b 用字母不用數字，靠內文的「RW page only」才知道是 RW 專用；外觀和其他步驟一樣。
- 步驟 13「strikes = 0」是什麼意思，這張看不出來（到 06A 才猜到是 LZ4 HW 的失敗計數）。
- 步驟 17 的 fresh[t]、步驟 18 的 low mark、步驟 13 的 strikes，都不在 01 的表裡。
- 步驟 b「clear 5 bits」的 5 從哪來，這張沒說（到 10 才看到「5 of 7 chunks used」）。
- 藍色旗標對照：13、14、15、17、18 的 from 旗標在 02、03 都找得到來源。步驟 a 的「completion, from step 11」在 03 那張旗標裡沒有被列到。

**3. 圖說的一句話**

解壓完成後 kernel 再握一次 mm_lock，把 page 標成 PRESENT、接回 page table、更新幾張記帳表，放鎖後回到 user SW 重跑那道指令；RW page 多做清 COT 和還 chunk 兩步。

**4. 畫面與結論**

一致。自己加 RO：5 + 3 + 6 + 19 + 2 = 35，lines 0 + 0 + 1 + 2 + 0 = 3，35 到 335，對。RW：35 + 4 + 80 = 119，lines 3 + 0 + 1 = 4，119 到 519，對。步驟 16 不計，符合便條。

**5. 困惑指數**：2。內容清楚，編號跳來跳去要多找一下。

**6. 可疑的錯字或多餘文字**：沒有錯字。副標題說這張是 fault_ro，但 02 說 fault_ro 和 fault_rw 共用步驟 1 到 6，03 只寫 fault_ro，fault_rw 到底走不走 03 的步驟，要到 11 的總表才確定。

---

## 05　First Touch: A Frame of Zeros in One Lock Hold

**1. 人物與機器**

- 左上火柴人「user SW」，驚訝表情，旁邊藍色旗標「steps 1 and 2 as on sheet 2: access, exception」。
- 步驟 3 到 9 全是白底，在括號「kernel, mm_lock held」底下，看得出是 kernel 握 lock 做的。
- 沒有硬體、沒有 OS 步驟。

**2. 看不懂的線或物件**

- 步驟 4 到步驟 9 的橘線「free_top」從步驟 5 的黃色便條後面穿過去，斜跨半張圖，要順著看才知道起點是 4。
- 步驟 3 到步驟 8 的橘線「state」從步驟 3 的黃色便條下緣出發，繞到底下再上來。note_fresh 為什麼需要 state，看不出來。
- 步驟 3 到 6 標「state[h]」、到 8 標「state」，又是兩種寫法。
- 步驟 7 pte_map 要寫 frame address，卻沒有來自步驟 4 的橘線 f，只有來自步驟 5 的虛線規則。
- 04 的 set_present 後面有 wake_page，這張沒有，原因沒說。
- 右上旗標「then eret and rerun as on sheet 4」壓在括號右端上，括號的右端被遮住一截。
- 藍色旗標對照：sheet 2 有步驟 1 access、2 exception；sheet 4 有 19 eret、20 rerun。都對得上。

**3. 圖說的一句話**

第一次碰的 page 不用 LZ4 HW，kernel 在一次握鎖裡拿 frame、填零、接上 page table 就結束，其中填零佔了絕大部分指令。

**4. 畫面與結論**

一致。自己加：14 + 12 + 341 + 3 + 6 + 19 + 2 = 397，對；lines 1 + 2 + 0 + 0 + 1 + 2 + 0 = 6，對；397 到 997，對；341 是步驟 5 的數字，對。同樣沒有把 lock 的 6 個指令算進去（11 的總表是 403）。

**5. 困惑指數**：2。主線清楚，兩條長橘線穿過別的方塊，稍亂。

**6. 可疑的錯字或多餘文字**：沒有錯字。步驟 5 的便條「341 instr, 341 cycles」沒有 lines 欄，格式和別格不同，但內文有解釋（不讀 DRAM）。

---

## 06A　LZ4 HW Says Failed, the Software Rescue Works

**1. 人物與機器**

- 沒有人物，也沒有綠色的 LZ4 HW 方塊（標題主角是 LZ4 HW，但它不在畫面上）。
- 上半部四步（12 cache_invalidate、13 sw_decode、14 frame_write、15 sw_clean）：上方藍字「kernel, the faulting thread, no lock held」，看得出是 kernel、沒握 lock。
- 下半部灰框四步（16 note_hw、17 cot_clear、19 set_present、20 pte_map）：括號「kernel, mm_lock held」，看得出是 kernel 握 lock。
- 每一步誰做、有沒有握 lock：看得出來，而且這張是整組標得最明白的。

**2. 看不懂的線或物件**

- 步驟 12 到 14 的橘線標「no old lines of frame[f]」。橘線照圖例是「需要那個值」，但這句話是一個條件，不是值，比較像虛線規則。
- 灰框裡的藍字「Also in this lock hold, drawn on sheet 4: 18 release_chunks, 21 wake_page, 22 note_fresh, 23 wake_check.」這四個號碼是這個場景自己的編號。拿去對 sheet 4：那裡 18 是 wake_check，release_chunks 是 b，wake_page 是 16，note_fresh 是 17。名字找得到，號碼全部對不上；尤其 18 在兩張圖上是兩個不同的步驟。
- 這四步沒畫，所以 17 cot_clear 到 release_chunks、19 set_present 到 wake_page 的規則線（sheet 4 有）在這張看不到。
- 步驟 16 的便條「5 instr measured on the no-strike path, 0 lines」：這張走的是加 strike 的路，成本卻是另一條路量的。寫得誠實，但讀者不知道該不該信 5。
- 步驟 12 為什麼在 HW 失敗後還要先 invalidate，只能從橘線標籤猜（HW 可能寫了一半）。
- 藍色旗標對照：「rule, from step 11」「completion: failed, from step 11」「completion, from step 11」在 sheet 3 的步驟 11 找得到來源；「then eret and rerun, as on sheet 4」對得上。

**3. 圖說的一句話**

LZ4 HW 回報失敗時，kernel 不握鎖自己用軟體解壓、把 4096 B 抄進 frame 並寫回 DRAM，然後握鎖記一次 strike、清 COT、把 page 接回去。

**4. 畫面與結論**

部分一致。算式本身對：39 + 51 + 791 + 119 + 12 = 1012。但五個加數裡只有 791 能在這張圖上直接看到。
- 39 來自 sheet 2，51 來自 sheet 3（26 + 13 + 12），要翻回去才能驗。
- 119 是 lock hold B：這張只畫了其中 5 + 4 + 3 + 6 = 18，其餘 101（80 + 19 + 2）在 sheet 4。
- 12 是兩次握鎖各 6 個指令，這是整組第一次把 lock 的指令明講出來。
- 結論只給指令數，沒有給 cycles 範圍，和 02、04、05 的結論格式不同。
- 「The decode and the cache maintenance are not measured」與畫面的三張「time unknown / not measured yet」便條一致。

**5. 困惑指數**：3。畫出來的部分好懂，但有四步不在圖上、引用 sheet 4 的號碼對不起來、結論的加數大半要靠別張圖，冷讀者無法只憑這張驗算。

**6. 可疑的錯字或多餘文字**

- 副標題一行塞了三件事，字比其他張小。
- 底部「Cost」標籤是白底，其他張的底部標籤都是淺藍底。
- 「no old lines of frame[f]」語意不順。

---

## 06B　LZ4 HW Says Bad Stream and It Is Right: A Lost Page

**1. 人物與機器**

- 右下火柴人「user SW」，雙手舉起、表情崩潰，旁邊是關著的筆電。沒有箭頭，但緊貼在步驟 18 kill 下面，意思很清楚：這個程式被結束了。
- 步驟 13 sw_decode：上方藍字「kernel, the faulting thread, no lock held」。
- 灰框四步（15 put_frame、14 note_hw、16 set_lost、17 wake_page）：上方鎖頭加「kernel, mm_lock held」。17 內文寫 OS。
- 步驟 18 kill 在灰框外，開鎖圖示之後，內文「OS: end this user SW」，是 OS。
- 沒有綠色 LZ4 HW 方塊。
- 每一步誰做、有沒有握 lock：看得出來。

**2. 看不懂的線或物件**

- 步驟 18 上方的旗標「also after step 12, cache_invalidate, sheet 3.」看不懂。是說 kill 還要等步驟 12 嗎？為什麼殺掉程式要等 cache invalidate？或者它其實想講的是 put_frame？這面旗標的對象和理由都不明。
- 上排的順序是 13、15、14，編號不是由左到右。
- 副標題說「steps 1 to 12 as on sheets 2 and 3」，06A 卻是「steps 1 to 11」並且把 12 重畫一次，兩張的切法不同。
- 中下方有一大片空白。
- 藍色旗標對照：「completion: bad stream, from step 11」「completion, from step 11」來源在 sheet 3 的步驟 11；sheet 3 的步驟 12 確實是 cache_invalidate。

**3. 圖說的一句話**

LZ4 HW 說資料流壞了，kernel 自己再解一次確認真的壞了，於是握鎖把 frame 還回去、把 page 標成 LOST，放鎖後由 OS 結束這個 user SW。

**4. 畫面與結論**

部分一致。算式對：39 + 51 + 21 + 12 = 123，其中 21 = 13 + 5 + 3 可在本圖驗算。後半句「frame 回到 free stack、page 保持 LOST」與步驟 15、16 一致。
不足的地方：步驟 13 sw_decode 是「not measured yet」，結論的 123 不含它，但這張的結論沒有像 06A 那樣說明。

**5. 困惑指數**：2。故事一看就懂，只有 kill 上面那面旗標讀不通。

**6. 可疑的錯字或多餘文字**

- 旗標「... sheet 3.」句尾多一個句點，其他旗標都沒有。
- 藍色標題裡「kernel」特別粗，06A 同一句沒有加粗。

---

## 07　Evicting an RO Page: The Clock Scan and One Lock Hold

**1. 人物與機器**

- 沒有人物。
- 灰框裡六步，框上標籤「kernel reclaimer thread, mm_lock held for all six steps」，清楚是 kernel 的 reclaimer thread 握 lock。
- 步驟 4 tlb_inval 內文寫「CPU MMU: drop the TLB entry on all cores」，是 CPU；它是白底，不像 02、04 的 CPU 步驟是藍底。
- 右邊白框「inside pick_victim: what the clock hand looks at」：六個空白方格，一支標「clock hand」的箭頭指著第三格，下面七行文字。
- 每一步誰做、有沒有握 lock：看得出來。

**2. 看不懂的線或物件**

- 六個空白方格沒有標籤，要靠下面的文字才猜到每格是一個 frame。
- 旗標「then back to step 1」：迴圈什麼時候停、每圈之間放不放鎖，都沒有說。標籤說「held for all six steps」，讀起來像整個迴圈都握著。
- 步驟 2 pick_victim 列了 owner[hand]、state[h]、pins[h]、fresh_n[h]、pte[h] 五樣，卻算 4 lines。
- 步驟 5 put_frame 這裡是 1 line，06B 和 10 的 put_frame 是 0 lines。猜得出原因（這裡 frame_of[h] 還沒碰過），但圖上沒說。
- 藍色旗標對照：「woken by wake_check, sheets 4 and 5」，sheet 4 的步驟 18 和 sheet 5 的步驟 9 都是 wake_check，對得上。

**3. 圖說的一句話**

reclaimer thread 握一次鎖，用 clock hand 掃 frame 找一個可以丟的 RO page，清掉它的 page table 與 TLB、把 frame 還回 free stack、把狀態標成 COMPRESSED，不需要 LZ4 HW。

**4. 畫面與結論**

一致。自己加：2 + 33 + 2 + 13 + 3 = 53，對；lines 0 + 4 + 0 + 1 + 0 = 5，對；53 到 553，對；500 ns 是步驟 4，對。「每經過一個 frame 最多再加 4 lines」對得上右框的「accessed page ... 4 lines」。
提醒：53 是「第一個 frame 就能丟」的情況；右框寫實測每次平均看 4.9 個 frame、最長 35841 個，這些都在握鎖期間，結論只用一句帶過。

**5. 困惑指數**：2。左邊流程清楚，右框資訊密，要讀兩次。

**6. 可疑的錯字或多餘文字**：沒有錯字。結論列下面留了一整條空白，結論不在圖的最底。

---

## 08　Evicting an RW Page, Part 1: Lock Hold A and the Bitmap Search

**1. 人物與機器**

- 沒有人物。
- 七步都在括號「kernel reclaimer thread, mm_lock held」底下，白底。步驟 6 tlb_inval 內文寫 CPU MMU。
- 右邊白框「inside reserve: find a free bit」：一條十格的長條，灰格與白格交錯，一個橘色圓圈框住其中一個白格，下面七行文字。
- 每一步誰做、有沒有握 lock：看得出來。

**2. 看不懂的線或物件**

- 長條沒有標哪一端是低位，灰色與白色也沒有圖例（猜灰色是已用）。橘圈圈住的不是最左邊的白格，和文字「the lowest free bit」對不上，除非低位在右邊。
- 為什麼預留 7 個 chunk，圖上沒說（猜是 8 個就等於沒壓縮）。
- 步驟 2 pick_victim 這裡是 44 instr，sheet 7 是 33 instr，差在哪沒說。
- 「free_chunks」不在 01 的 scalars 清單裡。
- 藍色旗標對照：「chunk numbers, to step 9」「f, to steps 8 and 9」「rule, to step 8」「rule, to step 10」在 09 全部有對應的 from 旗標。

**3. 圖說的一句話**

要丟一個 RW page 時，reclaimer thread 握鎖選出受害者，在 bitmap 裡預留 7 個 chunk、查出 frame、拆掉對映、把狀態標成 COMPRESSING。

**4. 畫面與結論**

一致。自己加：2 + 44 + 111 + 5 + 2 + 3 = 167，對；lines 0 + 4 + 1 + 1 + 0 + 0 = 6，對；167 到 767，對；500 ns 是步驟 6，對。

**5. 困惑指數**：2。三條「victim」橘線扇形展開很好讀；右框的長條方向不明。

**6. 可疑的錯字或多餘文字**：沒有發現。

---

## 09　Evicting an RW Page, Part 2: The COMPRESS Job, No Lock Held

**1. 人物與機器**

- 沒有人物。
- 步驟 11 hw_compress（綠底、齒輪），便條「LZ4 HW model: 4260 ns」，是 LZ4 HW。上方有小圖：一個白方格箭頭指向三個斜線方格，無標籤，猜是「一頁壓成幾個 chunk」。
- 步驟 12 notify：「OS wakes the reclaimer thread」，是 OS。
- 步驟 8 cache_clean、9 desc、10 submit、13 cpl_read：白底，方塊上沒寫誰做；只能從步驟 12 的「reclaimer thread」推回去。
- lock：只有標題「No Lock Held」，畫面沒有標記。06A、06B 有一行藍字「kernel, ... no lock held」，這張沒有。

**2. 看不懂的線或物件**

- 「doorbell」只出現在副標題和虛線標籤「rule: clean before doorbell」，步驟 10 的方塊裡沒有這個字。要猜它就是「write JOB_TAIL」。
- 副標題說「three things must be ready」，數得出來：虛線弧（8）、橘線 descriptor（9）、旗標「rule, from step 7」。第三樣是一面旗標而不是線，稍微要找。
- 步驟 13 cpl_read 沒有 sheet 3 那一行「compare the tag」。
- 藍色旗標對照：四面 from 旗標都和 sheet 8 吻合。「completion, to steps 14 to 18」對到 sheet 10：那裡 14、15、16 掛「completion, from step 13」，但 17、18 掛的是「rule, from step 13」或沒有旗標，用字不完全一致。

**3. 圖說的一句話**

不握 lock：kernel 先把 frame 的髒 cache 寫回 DRAM 並填好 descriptor，三個前提到齊才敲暫存器，LZ4 HW 壓縮寫進 chunk pool，interrupt 叫醒 reclaimer thread 來讀 completion。

**4. 畫面與結論**

一致。自己加：55 + (63 到 163) + 162 = 280 到 380，對；4260 與 3150 直接抄自便條，對。結論沒有提步驟 8 的「time unknown」。

**5. 困惑指數**：2。和 03 同構，看過 03 就很順。

**6. 可疑的錯字或多餘文字**：沒有發現。

---

## 10　Evicting an RW Page, Part 3: Lock Hold B, Two Outcomes

**1. 人物與機器**

- 沒有人物。
- 左右兩個黑框，各有自己的括號「kernel reclaimer thread, mm_lock held」。左框「the page fits: scenario evict_rw, 5 of 7 chunks used」，右框「the page does not fit: scenario evict_rw_incompressible, undo」。
- 兩邊的步驟 19 wake_page 內文寫 OS；其他都是 kernel 握 lock。
- 每一步誰做、有沒有握 lock：看得出來。

**2. 看不懂的線或物件**

- 右框步驟 16 mark_incompressible 是 0 lines。下方藍字解釋 0 lines 的理由只列了「bitmap word、frame_of[h]、pte[h]」，沒有列 incompressible 這個 bit，所以這個 0 無從確認。
- 清 bit 的成本跨圖對不起來：這張清 2 bit 是 18 instr、清 7 bit 是 51 instr；sheet 4 的 release_chunks 清 5 bit 卻是 80 instr、還多 1 line。也許 sheet 4 那一步還做了別的事，但圖上只寫「clear 5 bits」。
- 右框的虛線弧「rule: PRESENT first」從 17 繞過 18 底下到 19，位置有點擠但讀得出來。
- 藍色旗標對照：全部指向 sheet 9 的步驟 13，那裡確實是 cpl_read。下方藍字「loops back to step 1, reclaim_check, sheet 8」對得上。

**3. 圖說的一句話**

壓縮回來後 reclaimer thread 再握一次鎖，分兩種結局：壓得進去就記 COT、退掉多留的 2 個 chunk、還 frame、標 COMPRESSED；壓不進去就全部復原，把 page 接回去並記成 incompressible。

**4. 畫面與結論**

一致。自己加，Fits：5 + 44 + 18 + 13 + 3 = 83，1 line，83 到 183，對。Does not fit：5 + 51 + 8 + 3 + 6 = 73，0 lines，73，對。

**5. 困惑指數**：2。左右對照的版面很清楚，是整組裡最好比較的一張。

**6. 可疑的錯字或多餘文字**：沒有錯字。標題底線在冒號處斷成兩段，無礙。

---

## 11　Eight Scenarios: What the Kernel's Own Steps Cost

**1. 人物與機器**

- 沒有人物、沒有步驟。一張八列六欄的表，下面三行藍字說明、一條結論。

**2. 看不懂的線或物件**

- 只有「instr」和「new lines」兩個表頭是黃底，其他表頭白底。猜是「這兩欄是量出來的」，但沒有說明。
- 「The model takes 1 cycle as 1 ns」到這張才出現；前面十張 ns 和 cycles 混著寫，一直沒有換算。

**3. 圖說的一句話**

八個場景裡 kernel 自己的步驟各花多少指令、cache line 與 cycles，旁邊列出假設的 CPU 與 OS 開銷和 LZ4 HW 的時間。

**4. 畫面與結論**

一致。結論的兩個範圍：59 到 2112 是表中「kernel cycles」的最小（evict_ro）與最大（fault_rescue）；500 到 7910 是後兩欄相加的最小（evict_ro 500）與最大（evict_rw 3650 + 4260），都對。
另外用前面各張的數字把八列全部重算過，全部吻合：

| 場景 | 指令重算 | lines 重算 | cycles 重算 | 假設 ns 重算 |
|---|---|---|---|---|
| first_touch | 397 + 6 = 403 | 6 | 403 到 1003 | 600 + 400 = 1000 |
| fault_ro | 39 + 51 + 35 + 12 = 137 | 4 + 2 + 3 = 9 | 337 到 1137 | 600 + 3150 + 400 = 4150 |
| fault_rw | 39 + 51 + 119 + 12 = 221 | 4 + 2 + 4 = 10 | 421 到 1321 | 4150 |
| fault_rescue | 1012 | 10 | 1212 到 2112 | 4150 |
| fault_lost | 123 | 4 + 2 + 0 = 6 | 323 到 823 | 600 + 3150 = 3750 |
| evict_ro | 53 + 6 = 59 | 5 | 59 到 559 | 500 |
| evict_rw | 167 + 80 + 83 + 12 = 342 | 6 + 2 + 1 = 9 | 542 到 1342 | 500 + 3150 = 3650 |
| evict_rw_incompressible | 167 + 80 + 73 + 12 = 332 | 6 + 2 + 0 = 8 | 532 到 1232 | 3650 |

（cycles 的算法照圖上藍字：指令數 + 每次暫存器寫入 50 + 每條 miss 的 line 100；低端只有 completion 那條 miss。）

小地方：結論說「the kernel's table work」，但 fault_rescue 的 1012 裡有 791 是抄一整頁，不算查表。

**5. 困惑指數**：1。表格一看就懂，數字全部對得回去。

**6. 可疑的錯字或多餘文字**

- 底部標籤「Reading:」帶冒號，其他張的標籤都不帶。
- 標題底線偏紅，其他張是橘色。

---

## 跨圖觀察

### 命名物件有沒有走樣

**步驟方塊**：02 到 10 一致。白底圓角框、左上橘色圓形編號、粗體名稱、內文「在哪裡: 做什麼」。沒有走樣。

**黃色成本便條**：位置與顏色一致，都壓在方塊下緣。文字格式大致是「N instr, N lines, X to Y cycles」，另有幾種變體：「assumed N ns」「CPU hardware, not counted」「OS call, not counted」「LZ4 HW model: N ns」「64 cache operations, time unknown」「not measured yet」。變體讀得懂，不算走樣。01 的成本模型是有摺角的大便利貼，形狀不同但用途不同，可以接受。11 把黃色拿去塗表頭，意思不明。

**lock 的括號與灰框**：這是走樣最明顯的物件，共有五種畫法。

| 畫法 | 出現在 |
|---|---|
| 只有灰色括號 | 02、05、08 |
| 灰色括號加灰色圓角框 | 04、06A |
| 只有灰色圓角框，鎖頭與文字浮在框上方 | 06B |
| 灰色圓角框，標籤嵌在上緣 | 07 |
| 括號放在黑色面板框裡 | 10 |

開鎖圖示只在 04 和 06B 出現。因為每一處都寫了「mm_lock held」，意思不會讀錯，但外觀不統一。

**沒握 lock 的區段**：03、09 只靠標題；06A、06B 另有一行藍字「kernel, the faulting thread, no lock held」。後者清楚得多。

**藍色旗標**：藍框藍字一致，文字格式「X, to step N」「X, from step N」一致。外形不統一：有缺口緞帶（02、08）、五角箭頭（03、06A）、帶尾巴的對話框（04、10）幾種。不影響閱讀。

跨圖對照結果：

- 對得上：02 與 03、02 與 04、03 與 04（13、14、15、17）、05 與 02 和 04、07 與 04 和 05、08 與 09、10 與 09。
- 對不上或不完整：
  1. 03 步驟 11 的旗標沒有列到 04 的步驟 a，但 a 掛著「completion, from step 11」。
  2. 06A 用自己的編號去指 sheet 4 的圖（18 release_chunks、21、22、23），在 sheet 4 上號碼完全不同，18 還撞到另一個步驟。
  3. 06B 步驟 18 的「also after step 12, cache_invalidate, sheet 3.」讀不出對象與理由。
  4. 09 說「completion, to steps 14 to 18」，10 上只有 14 到 16 掛 completion，17、18 掛的是 rule。

### 分類顏色一致嗎

- 橘色：編號圓、資料箭頭、標題底線。一致（11 的底線偏紅）。
- 黑色虛線：順序規則。一致。
- 黃色：成本。一致（11 的表頭除外）。
- 綠色加齒輪：LZ4 HW。一致（01、03、09）。
- 灰色：lock。顏色一致，形狀不一致。
- 斜線：壓縮資料。01 的 chunk pool 與 09 的小圖一致，但沒有圖例。
- 藍底步驟方塊：不一致。02 的 access、exception 與 04 的 eret、rerun 是藍底，看起來代表「CPU 或進出 kernel」。但 07、08 的 tlb_inval（CPU MMU、assumed 500 ns）和 03、09 的 notify（assumed 3150 ns）是白底。同樣是「非 kernel、假設值」的步驟，有的藍有的白。
- 底部標籤：都是淺藍底，只有 06A 的「Cost」是白底。
- 每張的圖例只解釋箭頭，方塊底色從頭到尾沒有圖例。

### 故事線順不順

順序是：01 地圖 → 02 到 04 page fault 三段 → 05 first touch → 06A、06B 兩種失敗 → 07 丟 RO page → 08 到 10 丟 RW page 三段兩結局 → 11 總表。段落之間靠旗標接得起來，02 到 04 與 08 到 10 兩組結構對稱，讀過前一組，後一組就很快。

斷掉或要猜的地方：

1. **先 fault 後 evict**：page 要先被壓過才會 fault。02 一開始就讀 COT entry、03 就讀 chunk，但這些東西怎麼產生要到 08 到 10 才出現。照因果順序讀會比較順。
2. **fault_rw 的路徑**：02 說兩個場景共用，03 只寫 fault_ro，04 說 RW 多兩步。fault_rw 走不走 03，要到 11 才確認。
3. **換算與計法太晚才講**：「1 cycle = 1 ns」到 11 才出現；「每次握鎖另加 6 instr」到 06A 才明講，02、04、05、07、08、10 的結論都沒說自己不含這 6 個。這兩條應該在 01 的成本便利貼就講。
4. **cache line 數無法從方塊驗算**：指令數每一張都加得起來；但一個步驟碰了幾樣東西、為什麼只算幾條 line，方塊上看不出來（02 步驟 3、4，04 步驟 17，07 步驟 2）。10 用一行藍字解釋 0 lines，這個做法其他張沒有。
5. **01 沒收錄的名字**：fresh[t]、strikes、tag、lz4_off、free_chunks、low mark、high mark 都在後面出現，01 的表裡找不到。
6. **「OS」與「kernel」的分界**：整組都把兩者當不同角色，但沒有任何一張說明誰是誰。
7. **「哪些步驟真的要等」沒有收尾**：每張用箭頭各自交代，11 只總結成本，沒有一張把順序規則收攏。
8. **跨圖數字的疑點**：清 5 bit 要 80 instr（04），清 7 bit 只要 51 instr（10）。

### 我用自己的話講這組圖的結論

kernel 為一次事件做的記帳工作很小：幾十到幾百個指令、最多十條新的 cache line，合計 59 到 2112 cycles，而且分成一到兩次很短的 mm_lock 握鎖；中間 LZ4 HW 的工作不握鎖。握鎖期間大多數步驟彼此不相依，真正要排順序的只有少數幾條規則：先標狀態才能送 job、cache 寫回 DRAM 才能敲暫存器、COT entry 寫好才能還 frame、frame 內容到位才能把 PTE 設成有效、狀態改好才能叫醒等待的 thread。真正花時間的是等待：例外進出、interrupt 與喚醒（假設 0.5 到 4.15 µs）和 LZ4 HW（解壓 1.25 µs、壓縮 4.26 µs）。kernel 自己變重的只有三處：first touch 握著鎖填零（397 個指令裡的 341 個）、軟體救援抄一整頁（791 個指令）、clock 掃描一次可能經過很多 frame。另外 frame 的 cache 維護（每次 64 個操作）和軟體解壓都還沒量，沒有算進任何一個總數。

### 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|
| 01 | 2 | 是（無步驟；LZ4 HW registers 清楚） | 一致 |
| 02 | 2 | 是 | 一致 |
| 03 | 2 | 是（白底步驟的執行者要推論，no lock 只在標題） | 一致 |
| 04 | 2 | 是 | 一致 |
| 05 | 2 | 是 | 一致 |
| 06A | 3 | 是 | 部分一致 |
| 06B | 2 | 是 | 部分一致 |
| 07 | 2 | 是 | 一致 |
| 08 | 2 | 是 | 一致 |
| 09 | 2 | 是（白底步驟的執行者要推論，no lock 只在標題） | 一致 |
| 10 | 2 | 是 | 一致 |
| 11 | 1 | 是（無步驟） | 一致 |

所有底部加總與 11 的八列數字都重算過，算術沒有任何一處錯。

### 建議重生

只列困惑指數 3 以上、角色不清、或畫面與結論不一致的：

1. **06A（困惑指數 3，部分一致）**
   - lock hold B 有四步沒畫，卻用本場景的號碼（18、21、22、23）去指 sheet 4，而 sheet 4 上是 b、16、17、18，18 還撞號。建議把這四步畫出來，或改成用名稱加 sheet 4 的號碼引用。
   - 結論的 1012 有四個加數不在本圖，119 只看得到 18。建議在圖上標出各加數的出處，或補上沒畫的步驟。
   - 橘線「no old lines of frame[f]」不是值，改成虛線規則較符合圖例。
   - 結論補上 cycles 範圍；底部標籤改回淺藍底。

2. **06B（部分一致）**
   - 結論的 123 不含「not measured yet」的 sw_decode，卻沒有像 06A 那樣註明。補一句即可。
   - 步驟 18 的旗標「also after step 12, cache_invalidate, sheet 3.」讀不通，需要改寫成明確的對象與理由，並去掉句尾句點。
   - 這張的問題都是文字層級，如果可以只改字就不必整張重生。

不在重生清單、但值得一併處理的小修（都不到重生的程度）：

- 01 的成本便利貼補上「1 cycle = 1 ns」與「每次握鎖另加 6 instr」。
- 03 步驟 11 的旗標補上步驟 a；09 步驟 13 的旗標用字與 10 對齊。
- 03、09 加上和 06A 一樣的藍字「kernel, ... no lock held」。
- lock 的畫法統一成一種；藍底方塊的規則統一（tlb_inval、notify 要不要藍底）並加圖例。
- 04 的清 5 bit 80 instr 與 10 的清 7 bit 51 instr，請確認或在方塊內說明差在哪。

# 冷讀驗收報告 gen5：06A 與 06B

- 日期：2026-11-12
- 方法：只給圖、不給提示詞的冷讀
- 範圍：十二張圖（01 到 05、06A、06B、07 到 11）全部依序讀過當上下文，這次只驗收 06A 與 06B
- 讀者設定：第一次看到這組圖、沒有背景的讀者。以下的疑問都是「從圖上看不出來」，不代表設計本身有錯

## 結論先講

兩張都不需要重生。主線、角色、握不握 lock 都看得出來，底部結論的加總全部驗算得過。

有三個地方建議對照原始資料再確認，因為它們碰到這組圖的主題「哪一步真的要等哪一步」：

1. 06A 從 13 sw_decode 拉到 22 note_fresh 的橘色箭頭標「page」，看不出 note_fresh 需要的是哪個值。
2. 06B 的 14 note_hw 寫「the LZ4 HW was right」，但圖上它只等 step 11，沒有等 13 sw_decode 的判定。
3. 06A 從 12 cache_invalidate 到 14 frame_write 的橘色箭頭標「cache[f]」，cache_invalidate 並不產生值，比較像順序規則。

## 06A：LZ4 HW Says Failed, the Software Rescue Works

### 1. 人物與機器

- 這張沒有畫任何人或機器。沒有 user SW 小人，也沒有帶齒輪的 LZ4 HW 方塊。標題說「LZ4 HW Says Failed」，但 LZ4 HW 只出現在文字與藍色標籤「completion: failed, from step 11」裡。
- 上排四步（12 cache_invalidate、13 sw_decode、14 frame_write、15 sw_clean）：左上藍字「kernel, the faulting thread, no lock held」說明是 kernel 的 faulting thread 做的，不握 lock。這行字沒有框線把四步圈起來，靠位置對應，看得懂。
- 下方大框八步（17 cot_clear、19 set_present、22 note_fresh、20 pte_map、18 release_chunks、21 wake_page、16 note_hw、23 wake_check）：框上方有鎖頭與「kernel, mm_lock held for both rows: lock 4 instr, unlock 2 instr」，看得出兩排都握 mm_lock。
- 21 wake_page 的內文以「OS:」開頭，看得出是 OS 做的，黃色標籤「OS call, not counted」。
- 框內沒有再寫一次「the faulting thread」，讀者要自己推論握 lock 的還是同一個 thread。sheet 4 也是這樣寫，所以不算這張獨有的問題。
- 每一步誰做、有沒有握 lock：看得出來。

### 2. 看不懂的線或物件

- **13 到 22 的橘色箭頭「page」**：圖例說橘色是「data: needs the value」。同一個「page」標籤也拉到 14 frame_write，那一條很合理（解出來的 4096 B 內容）。但 22 note_fresh 只動 fresh[t]、fresh_n[h]、fresh_n[old] 這些計數，看不出它需要頁面內容。是指頁號 h，還是「解碼成功」這個結果？另外同一個 note_fresh 在 sheet 4 的輸入是「completion, from step 11」，在 sheet 5 是從 check_state 來的「state」，三張三種來源。
- **12 到 14 的橘色箭頭「cache[f]」**：cache_invalidate 是一個動作，不產生值。「cache[f]」也不在 sheet 1 的表格清單裡。讀起來比較像「先 invalidate 才能寫」的順序規則，卻畫成資料箭頭。
- **13 到 19 的虛線只寫「rule」**：這張其他四條虛線都有寫理由（good decode first、entry first、PRESENT first、frame content before valid），只有這一條沒有。
- **穿過 lock 框標籤的箭頭**：13 到 22 的橘線與 13 到 19 的虛線都斜穿過「kernel, mm_lock held…」那一塊，線在框頂附近看起來斷掉，箭頭在框內重新出現，要追一下才接得起來。
- **編號與位置不一致**：框內從左到右、從上到下讀到的是 17、19、22、20、18、21、16、23。16 note_hw 編號最小卻在下排第三格。圖例說「no arrow: any order」，所以編號不是嚴格順序，但讀者會先找 16 找不到。sheet 4 也是這種排法（13、14、15、17 / 18、16、a、b）。
- **15 sw_clean 為什麼需要**：sheet 5 的 zero_frame 也是軟體寫滿一個 frame，寫完沒有 clean 這一步；這張寫完要把 64 條 cache line 寫回 DRAM 才能 pte_map。圖上只給「rule: frame content before valid」，沒說為什麼一定要進 DRAM。
- **16 note_hw 的黃色標籤「5 instr, 0 lines: measured for strikes = 0」**：內文寫的是「strikes + 1」，成本卻註明是量「strikes = 0」那條路。讀得出是借用別條路徑的數字，但第一眼會以為寫錯。這個標籤也沒有 cycles，其他標籤都有。
- **引用別張圖，逐條對照**：
  - 12 的「rule, from step 11」：sheet 3 有 11 cpl_read 到 12 cache_invalidate 的虛線 rule。對得上。12 的內文與黃色標籤也和 sheet 3 的 12 一字不差。
  - 13 的「completion: failed, from step 11」：sheet 3 的 11 是 cpl_read。對得上。不過 sheet 3 的 11 下方標籤只寫「to sheet 4」，沒提到 6A、6B，引用是單向的。
  - 16 的「completion, from step 11」：對得上。
  - 23 的「free_top, from step 4」：sheet 2 的 4 take_frame 有「free_top, to step 18」。來源對得上；sheet 2 寫的目的地是 18，那是 fault_ro 的編號，在這張是 23。
  - 「After the unlock: 24 eret and 25 rerun, drawn as steps 19 and 20 on sheet 4」：sheet 4 的 19 是 eret、20 是 rerun。對得上。
  - 副標「steps 1 to 11 as on sheets 2 and 3」：sheet 2 是 1 到 6，sheet 3 是 7 到 12。對得上。

### 3. 圖說的一句話（不看底部結論）

LZ4 HW 回報失敗後，faulting thread 不握 lock 先 invalidate frame 的 cache、用軟體把 chunks 解到 kernel buffer、把 4096 B 抄進 frame 再寫回 DRAM，然後握一次 mm_lock 做和 sheet 4 的 RW page 幾乎一樣的收尾，只差 note_hw 改成記一次 strike。

### 4. 畫面與結論：一致

底部結論：「This sheet: 791 instr copy + 119 instr in lock hold B. Whole scenario: 1012 instr = 39 lock hold A + 51 job + 791 + 119 + 12 for two lock holds; 1212 to 2112 cycles. Decode and cache maintenance are not measured.」

驗算：

| 項目 | 算式 | 結果 |
|---|---|---|
| lock hold B，這張圖上 | 4 + 3 + 19 + 6 + 80 + 5 + 2（wake_page 不計） | 119，相符 |
| frame_write | 圖上直接寫 791 | 相符 |
| lock hold A，sheet 2 | 14 + 12 + 6 + 7 | 39，相符 |
| job，sheet 3 | 26 + 13 + 12 | 51，相符 |
| 兩次 lock hold | 2 ×（4 + 2） | 12，相符 |
| 整個場景 | 39 + 51 + 791 + 119 + 12 | 1012，相符 |
| cycles 下限 | 1012 + 2 次 register write × 50 + 1 條 line × 100 | 1212，相符 |
| cycles 上限 | 1012 + 100 + 10 條 line × 100 | 2112，相符 |

- cycles 範圍只靠這張圖驗不出來，需要 sheet 3 的兩次 register write 與 sheet 11 的公式。new lines 共 10 條 = lock hold A 4 條 + job 2 條 + 這張 4 條（note_fresh 2、pte_map 1、release_chunks 1），和 sheet 11 的 fault_rescue 那一列相符。
- 「Decode and cache maintenance are not measured」對應圖上 13 的「not measured yet」與 12、15 的「time unknown」。相符。
- 圖上的框沒有寫「lock hold B」這個名字，結論直接用了，讀者要自己對上。

### 5. 困惑指數：2

主線一看就懂，角色與 lock 清楚；扣分在這是整組最擠的一張（12 個方塊、4 條線穿進 lock 框、編號不照位置），再加上「page」與「cache[f]」兩個標籤要猜。

### 6. 可疑的錯字或多餘文字

- 沒有發現拼錯的字。
- 同一個動作兩個名字：這張叫 sw_clean（「write them back to DRAM」），sheet 9 叫 cache_clean（「write dirty lines back to DRAM」）。
- 14 的黃色標籤「791 instr, 791 cycles, 64 lines written」格式和其他標籤（instr、lines、cycles）不同，「64 lines written」也不算進 new lines。sheet 5 的 zero_frame 也是這樣處理，讀者可能會問一次。
- 右側「rule: frame content before valid」貼到圖的右邊緣，沒被切到，但很緊。
- 底部結論的字比其他張的結論小。

## 06B：LZ4 HW Says Bad Stream and It Is Right: A Lost Page

### 1. 人物與機器

- **user SW**（右下，有標籤）：舉起雙手、表情驚慌的小人，筆電推在一邊。看起來是被終止的那一方，在意的是自己的程式沒了。它和 18 kill 之間沒有線，靠位置相鄰與 kill 內文「OS: end this user SW」對應，看得懂。
- 沒有畫 LZ4 HW 方塊，只出現在標題與藍色標籤「completion: bad stream, from step 11」。
- 13 sw_decode：左上藍字「kernel, the faulting thread, no lock held」，看得出是 kernel 的 faulting thread，不握 lock。
- 中間大框四步（15 put_frame、14 note_hw、16 set_lost、17 wake_page）：框上方有鎖頭與「kernel, mm_lock held: lock 4 instr, unlock 2 instr」，握 mm_lock。17 的內文以「OS:」開頭。
- 18 kill：在框外，框右緣有打開的鎖頭與虛線「all done, unlock」，看得出是放掉 lock 之後由 OS 做的。
- 每一步誰做、有沒有握 lock：看得出來。

### 2. 看不懂的線或物件

- **14 note_hw 只等 step 11**：內文寫「strikes = 0, the LZ4 HW was right, no strike」，標題也說「and It Is Right」。要知道 LZ4 HW 說對了，得先有 13 sw_decode 的判定，但圖上 14 只有「completion, from step 11」的標籤，沒有從 13 來的線。照圖例「no arrow: any order」，會讀成 14 可以在軟體解碼之前做。15 與 16 都有從 13 來的虛線，只有 14 沒有。
- **18 kill 的標籤「also waits for step 12, cache_invalidate, on sheet 3」**：看不出為什麼是 kill 在等 cache_invalidate。直覺上比較像 15 put_frame 該等（frame 要還回 free stack 之前先把 cache 清乾淨）。
- **13 到 16、16 到 17 的虛線只寫「rule」**：13 到 15 有寫「rule: decode verdict first」，另外兩條沒寫理由。06A 的同一條 16 到 17 對應線寫了「rule: PRESENT first」。
- **編號與位置**：框內上排從左到右是 15、14，14 在右邊。
- **引用別張圖，逐條對照**：
  - 13 的「completion: bad stream, from step 11」、14 的「completion, from step 11」：sheet 3 的 11 是 cpl_read。對得上。
  - 18 的「step 12, cache_invalidate, on sheet 3」：sheet 3 的 12 是 cache_invalidate。對得上。
  - 副標「steps 1 to 12 as on sheets 2 and 3」：對得上。06A 寫的是「1 to 11」並把 12 重畫，06B 寫「1 to 12」不重畫，各自前後一致，兩張的 13 都是 sw_decode。
  - 「all done, unlock」：和 sheet 4 的「all done, unlock, return」同一種畫法。

### 3. 圖說的一句話（不看底部結論）

LZ4 HW 回報 bad stream 後，faulting thread 不握 lock 用軟體再解一次，確認 stream 真的壞了，接著握一次 mm_lock 把 frame 還回 free stack、不記 strike、把頁面標成 LOST、叫醒等這一頁的 thread，放掉 lock 後由 OS 終止這個 user SW。

### 4. 畫面與結論：一致

底部結論：「123 instr = 39 lock hold A + 51 job + 21 lock hold B + 12 for two lock holds; the decode is not measured. The frame goes back to the free stack; the page stays LOST.」

驗算：

| 項目 | 算式 | 結果 |
|---|---|---|
| lock hold B，這張圖上 | 13 + 5 + 3（wake_page 不計） | 21，相符 |
| lock hold A，sheet 2 | 14 + 12 + 6 + 7 | 39，相符 |
| job，sheet 3 | 26 + 13 + 12 | 51，相符 |
| 兩次 lock hold | 2 ×（4 + 2） | 12，相符 |
| 整個場景 | 39 + 51 + 21 + 12 | 123，相符 |

- 這張結論沒有給 cycles 也沒有給 new lines，其他張（含 06A）都有。對照 sheet 11 的 fault_lost 那一列：new lines 6 = 4 + 2 + 這張 0 條，相符；cycles 123 + 100 + 100 = 323、123 + 100 + 600 = 823，相符。
- sheet 11 的 fault_lost「assumed CPU and OS」是 3750 ns，比其他 fault 場景少 400 ns，剛好是 eret 的 400 ns。這張沒有 eret，相符。
- 「The frame goes back to the free stack」對應 15 put_frame。「the page stays LOST」對應 16 set_lost；圖上畫的是「變成 LOST」，「stays」的意思是之後一直是 LOST，第一眼可能讀成本來就是 LOST。
- 圖上的框沒有寫「lock hold B」這個名字。

### 5. 困惑指數：2

方塊少、主線與角色一看就懂；扣分在 note_hw 少一條依賴線，以及 kill 等 cache_invalidate 的標籤，這兩處要停下來想。

### 6. 可疑的錯字或多餘文字

- 沒有發現拼錯的字。
- 左上藍字的「kernel,」比同一行其他字粗、也大一點，06A 的同一行字是一致的粗細。
- 圖的下方三分之一是空白，版面重心偏上。

## 這兩張與其餘十張連著看

**一致的地方**

- 橘色圓形編號、黃色成本標籤、藍色折角標籤、右上圖例、橘色底線標題、藍色副標、底部一條結論，都和其餘十張相同。
- 成本標籤的寫法（「N instr, M lines, a to b cycles」「OS call, not counted」「time unknown」）相同。
- 各步驟的數字與別張一致：cot_clear 4、release_chunks 80、set_present 3、pte_map 6、note_fresh 19、wake_check 2、note_hw 5，和 sheet 4 相同；06B 的 put_frame「13 instr, 0 lines」和 sheet 10 相同。06A 的 lock hold B 是 119，和 sheet 4 的 RW page 119 相同。
- sheet 11 的 fault_rescue 與 fault_lost 兩列，和這兩張的結論相符。
- 06B 的 user SW 小人與 sheet 2、4、5 是同一種畫法，表情配合情境。

**不一致的地方**

- 底部結論的標籤：這兩張用「Cost」，其他張用 Key point、Lock hold A、Part 2、Lock hold B、One lock hold、Reading。
- 06A 的鎖頭是實心黑色、看不到鑰匙孔；06B 與其他張是有鑰匙孔的鎖頭。
- lock 區域的框法：06A 是上方括號加中間凸起的標籤再加圓角框；06B 只有粗灰圓角框；其他張多半是括號線，sheet 4 是括號加圓角框。
- 「kernel, the faulting thread, no lock held」這行藍字是這兩張才有的寫法，sheet 3 把同一件事放在標題裡。
- sw_clean 與 sheet 9 的 cache_clean 是同一個動作、兩個名字。
- 06B 的結論沒有 cycles 與 new lines，06A 沒有 new lines，其他張的結論都兩個都給。

## 總表

| 圖 | 困惑指數 | 角色是否清楚 | 畫面與結論 |
|---|---|---|---|
| 06A | 2 | 是 | 一致 |
| 06B | 2 | 是 | 一致 |

## 建議重生

沒有。兩張都沒有達到困惑指數 3、角色不清、或畫面與結論不一致的任何一項。

## 不到重生程度的小問題

先列三個碰到依賴關係、建議對照原始資料確認的：

1. **06A**：13 sw_decode 到 22 note_fresh 的橘色箭頭「page」，看不出 note_fresh 需要哪個值；同一步在 sheet 4 的輸入是「completion, from step 11」，在 sheet 5 是「state」。
2. **06B**：14 note_hw 寫「the LZ4 HW was right」卻沒有從 13 sw_decode 來的線，照圖例會讀成不必等軟體解碼。如果這個依賴是真的，圖上少一條線。
3. **06A**：12 到 14 的橘色箭頭「cache[f]」，比較像順序規則卻畫成資料箭頭。

其餘是畫法與用字：

4. 06A：13 到 19 的虛線只寫「rule」，沒寫理由。06B：13 到 16、16 到 17 也是。
5. 06A：兩條線斜穿過 lock 框的標籤，線看起來在框頂斷掉。
6. 06A：框內編號不照位置（16 在下排第三格）；06B：上排是 15、14。
7. 06A：16 note_hw 的標籤「5 instr, 0 lines: measured for strikes = 0」和內文「strikes + 1」對不上，也沒有 cycles。
8. 06A：看不出 15 sw_clean 為什麼必要，sheet 5 的 zero_frame 寫完沒有這一步。
9. 06A：sw_clean 與 sheet 9 的 cache_clean 名字不同。
10. 06B：18 kill 的標籤「also waits for step 12, cache_invalidate」，看不出為什麼是 kill 在等。
11. 06B：結論沒有 cycles 與 new lines；「the page stays LOST」的「stays」可能被讀成本來就是 LOST。
12. 06B：藍字的「kernel,」比同一行粗；下方三分之一空白。
13. 兩張：結論標籤用「Cost」、圖上的框沒寫「lock hold B」；06A 的鎖頭是實心黑色。
14. 上下文（不在這次驗收範圍）：sheet 3 的 11 cpl_read 下方標籤只寫「to sheet 4」，沒有提到 6A、6B。

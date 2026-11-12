# 圖像生成提示詞（第六版）：Kernel SW actions, step by step

**對象**：用 `sketchnote-gen` skill 生成這組圖的人，以及讀圖驗收的 agent。
**目的**：讓要寫或審 kernel SW 的工程師，在每個場景看到每一個步驟讀寫哪個資料結構、資料結構放在哪、做什麼運算、要幾道指令與幾個 cycle，以及哪些步驟真的要等別的步驟。
**風格**：`whiteboard`（和 `figures/page-states/` 同一種）。
**數字的來源**：每一個數字都抄自 `spec/kernel-step-detail-v0.md`（由 `python3 sim/run_host.py gen-steps` 產生）。指令數是量測，cache line 是計數，cycle 是模型（1 instr = 1 cycle，1 條新的 line 最多 100 cycle，LZ4 HW 剛寫的 completion 那條 line 一定是 100 cycle，1 次 register 寫入 50 cycle），ns 是假設或 LZ4 HW 模型。文件重新產生後數字有變，這份提示詞要跟著改。
**箭頭的來源**：`sim/hostsim/deps.py` 的 `reduced()`。橘色實線是資料相依，黑色虛線是規則要求的順序，沒有箭頭就是沒有先後關係。
**約束**：圖上文字全部英文；步驟編號用文件第 4 節該場景的編號；CPU 的步驟淺藍、LZ4 HW 的步驟淺綠、kernel 的步驟白色；壓縮資料畫斜線；不出現廠商或產品名稱；數字只有雙引號裡的。
**怎麼用**：skill 一張一張生，OpenAI 預設模型與 high 品質，`--size 1536x1024`；全部生完後做一次只給圖的冷讀；通過的存成本資料夾 `NN-<name>.png`。文字清單由雙引號字串自動產生。建立日期 2026-11-12。第五版留在 `prompts-v5.md`：第三次冷讀之後重畫 6A（握 lock B 的八步全部畫出來，底部的加總能只用這一張驗算），6B 改兩處文字。第四版留在 `prompts-v4.md`：第二次冷讀之後把第 6 張拆成 6A 與 6B（各一個場景），重畫第 7、10 張，小改第 1、4 張；`fault_lost` 的 `note_hw` 改成 `strikes = 0`（LZ4 HW 回報 bad stream 而軟體也解不開，代表它答對了）。第三版留在 `prompts-v3.md`：冷讀之後改了第 2、3、4、6、7、9、10、11 張，`cpl_read` 的下限也改成含那條一定從 DRAM 讀的 line。第二版（總覽層級，沒有資料結構與數字）留在 `prompts-v2.md`，第一版在 `prompts-v1.md`。

## 脊椎

| # | 檔名 | 讀者的問題 | 主張 | 對應 `deps.CASES` |
|---|------|------|------|------|
| 1 | `01-where-tables-live.png` | kernel 的表放在 DRAM 的哪裡？一筆多大？ | 每個 page 的資訊分在七張以 h 為索引的表，各在自己的 cache line 上。 | 全部 |
| 2 | `02-fault-lock-a.png` | page fault 進來後，第一次握 lock 做了什麼？ | 四個步驟，39 道指令與 4 條 line；`check_state` 之後的三步互不相依。 | `fault_ro`、`fault_rw` 的 1 到 6 |
| 3 | `03-fault-job.png` | 不握 lock 的那一段怎麼把工作交給 LZ4 HW？ | 一條直鏈；kernel 的三步 251 到 351 cycle，等待是 4403 ns。 | `fault_ro` 的 7 到 12 |
| 4 | `04-fault-lock-b.png` | 第二次握 lock 做了什麼？RW page 多做什麼？ | 都只等 completion；RO 是 35 道指令，RW 多還 chunk 變成 119 道。 | `fault_ro` 的 13 到 20、`fault_rw` |
| 5 | `05-first-touch.png` | 第一次碰一個 page 要多少？ | 一次握 lock、沒有 LZ4 job；397 道指令裡 341 道在填 0。 | `first_touch` |
| 6A | `06a-fault-rescue.png` | LZ4 HW 說失敗而 stream 其實是好的，kernel 多做什麼？ | 不握 lock 做軟體解壓縮、複製 4096 B（791 道指令）、清 cache；整個場景 1012 道。 | `fault_rescue` 的 12 到 23 |
| 6B | `06b-fault-lost.png` | stream 真的壞了呢？ | 還 frame、標成 LOST、結束 user SW；握 lock 21 道指令，LZ4 HW 不記 strike。 | `fault_lost` 的 13 到 18 |
| 7 | `07-clock-scan.png` | 選要趕出的 page 要看哪些表？趕出 RO page 要多少？ | 每看一個 frame 最多 4 條新的 line；RO page 一次握 lock 53 道指令。 | `evict_ro` |
| 8 | `08-evict-rw-lock-a.png` | 趕出 RW page 的第一次握 lock 做了什麼？bitmap 怎麼找空位？ | 取反、bit reverse、count leading zeros；保留 7 個 chunk 是 111 道指令與 1 條 line。 | `evict_rw` 的 1 到 7 |
| 9 | `09-evict-rw-job.png` | COMPRESS job 怎麼交出去？ | 送出之前要等三件事；LZ4 HW 的 4260 ns 是最長的一段。 | `evict_rw` 的 8 到 13 |
| 10 | `10-evict-rw-lock-b.png` | 壓完之後記什麼帳？壓不進去呢？ | 壓得進去：寫 COT、還多的 chunk、還 frame，83 道指令。壓不進去：全部還原，73 道。 | `evict_rw`、`evict_rw_incompressible` 的 14 起 |
| 11 | `11-totals.png` | 八個場景各要多少？ | kernel 自己的步驟是 59 到 2112 cycle，等待是 500 到 7910 ns。 | 全部 |

---

## Style block（每張都先貼這段）

```
Hand-drawn engineering whiteboard sheet, the kind an engineer draws to walk a colleague
through a design, dense but tidy. Aspect ratio 3:2, landscape. Plain white background.
Black marker line art with slightly wobbly strokes. Hand-lettered English text, small but
clean and fully legible. Identifiers such as state[h] or free_top are lettered exactly as
quoted, keeping their square brackets and underscores.

Named objects: whenever the prompt says 'the <object>', draw the same object every time.
- a step box: a rounded rectangle with a black outline. An orange circle holding the step
  number sits on its top-left corner. The first line inside is the step
  name in bold lettering. Under it come the quoted lines, one per row, in the order given.
  Nothing else is inside.
- a cost tab: a small pale yellow sticky note stuck on the bottom edge of a step box,
  holding exactly one quoted line, the cost of that step. Every step box has exactly one.
- a kernel step box: a step box with a plain white fill and no icon. Most boxes are
  kernel step boxes; a box is a kernel step box unless the prompt says otherwise.
- a CPU step box: a step box with a light blue fill and no icon.
- a hardware step box: a step box with a light green fill and a small gear icon on its
  top-right corner. Only steps the prompt calls hardware step boxes get green or a gear.
- the lock bracket: a thick grey square bracket lying above a group of step boxes and
  spanning exactly the boxes the prompt names, with a small closed padlock icon and the
  quoted label written on it.
- a data arrow: a solid orange arrow with one arrowhead and a short orange label written
  along it.
- a rule arrow: a dashed black arrow with one arrowhead and the black label written
  along it.
- a sheet tag: a small flag-shaped label with a blue outline and blue text, used where a
  dependency comes from or goes to another sheet. It touches the step box it belongs to.
- the legend: a small boxed legend in the top-right corner of the sheet with exactly
  three rows: a short solid orange arrow with its text, a short dashed black arrow with
  its text, and a third row of text only.
- the user SW figure: a round-headed stick figure sitting at a small laptop.
- a frame icon: one small plain white square with a black outline, never hatched.
- a chunk icon: three small rectangles side by side, each filled with diagonal hatching.
  Hatching always means compressed data and appears nowhere else.

Color rules: orange for data arrows, step number circles and the title underline; blue for
the subtitle line, sheet tags and small notes; light blue and light green fills only for
the step boxes as defined; pale yellow only for cost tabs; grey only for the lock bracket;
all other lines and text black. No gradients, no photo textures, no logos, no watermarks.

Fixed layout: a numbered square badge at the top-left; the title to its right, underlined
in orange; one blue subtitle line under the title; the legend at the top-right; the step
boxes as the prompt places them; a bottom bar across the full width with its label in a
small box at its left.

Hard limits:
- Render every double-quoted string exactly as written, character for character, digits
  included. Correct spelling. No extra words, labels, captions, numbers or examples.
- Draw only the boxes, arrows, tags and figures listed. Do not add boxes, rows or charts.
- Arrows connect only the boxes the prompt names. No other arrows. Two boxes with no
  arrow between them must stay unconnected.
- No digits anywhere unless the prompt quotes them. No vendor or product names.
- Keep the sheet uncrowded enough that every line of text can be read.
```

## Prompt 1：01-where-tables-live

```
Badge: "1"
Title: "Where the Kernel's Tables Live"
Subtitle (blue): "Full configuration: 148480 pages, 35840 frames, 563200 chunks of 512 B"

This sheet has no legend, no step boxes, no arrows with labels and no figure.

Layout: at the left, the DRAM map; to its right, three cards joined to the map by thin
black leader lines; at the bottom right a pale yellow sticky note; then the bottom bar.

The DRAM map: one tall vertical bar with a black outline, split into five stacked regions,
the lowest address at the top. Each region has its name and size lettered inside it and
its start address lettered just outside its top-left corner. From top to bottom:
- address "0x80000000", region "pinned area, 56 MiB"
- address "0x83800000", region "HRT area, 36 MiB, not compressed"
- address "0x85C00000", region "COT area, 5 MiB"
- address "0x86100000", region "chunk pool, 275 MiB", filled with light diagonal hatching
- address "0x97400000", region "frame area, 140 MiB"
At the bottom edge of the bar, outside it: "0xA0000000". The chunk pool and the frame area
are the two tallest regions; every region is tall enough for its lettering.

Card one, the largest, joined to the pinned area. Heading: "kernel mem, in the pinned area".
Three groups inside, each a small heading and a list:
- "indexed by page h": "state[h] 1 B", "frame_of[h] 4 B", "fresh_n[h] 2 B", "pins[h] 2 B", "incompressible, 1 bit", "pte[h] 8 B, the page table"
- "indexed by frame f": "owner[f] 4 B", "free_stack 4 B"
- "others": "bitmap: 8800 words of 64 bits, 1 bit per chunk", "scalars: free_top, hand, cursor, in one cache line", "job ring 16 x 64 B, completion ring 16 x 16 B"

Card two, joined to the COT area. Heading: "COT area". One line: "cot[h] 32 B: flags, length, CRC-32, 8 chunk numbers".

Card three, drawn as a small light green box with a gear icon, standing apart from the
DRAM map and not joined to it. Heading: "LZ4 HW registers". One line: "JOB_TAIL, CPL_HEAD".

The sticky note. Heading: "Cost model on the next sheets". Four lines: "instr counts: measured", "1 instr = 1 cycle, assumed", "1 new cache line of 64 B = up to 100 cycles", "1 register write = 50 cycles".

Bottom bar, label "Key point": "One page's bookkeeping is spread over seven tables indexed by h: six in kernel mem plus cot[h], each in a different cache line."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a region, a card or a table row;
hatch anything except the chunk pool; draw a person; join the LZ4 HW registers card to the
DRAM map; write any vendor or product name; rewrite the subtitle or the bottom bar; write
any non-English text.
```

## Prompt 2：02-fault-lock-a

```
Badge: "2"
Title: "Page Fault, Part 1: Entry and Lock Hold A"
Subtitle (blue): "Scenarios fault_ro and fault_rw, steps 1 to 6: what each step reads, writes and costs"

The legend, three rows: orange arrow "data: needs the value"; dashed arrow "rule: order required"; text only "no arrow: any order".

Layout: a short top row, then a large group under the lock bracket, then the bottom bar.

Top row, from left to right: the user SW figure, labeled "user SW", typing, mildly
surprised; then two CPU step boxes side by side.
- step "1", name "access": "page table: pte[h], bit 0 is 0". Cost tab: "CPU hardware, not counted".
- step "2", name "exception": "CPU saves the PC, enters the kernel", "kernel: h = (va - base) / 4096". Cost tab: "assumed 600 ns".
A rule arrow from step 1 to step 2, label "rule". A rule arrow from step 2 down to step 3, label "rule".

The lock bracket, label "kernel, mm_lock held: lock 4 instr, unlock 2 instr", spans steps
3, 4, 5 and 6, which are four kernel step boxes: white fill, no gear. Under it: step 3 alone at the left, vertically centered; steps 4, 5 and 6 stacked
in one column to its right, with clear gaps between them.
- step "3", name "check_state": "kernel mem: state[h], read 1 B", "kernel mem: free_top, read 4 B", "branch on the state". Cost tab: "14 instr, 1 line, 14 to 114 cycles".
- step "4", name "take_frame": "kernel mem: pop free_stack, get f", "kernel mem: frame_of[h] = f", "kernel mem: owner[f] = h". Cost tab: "12 instr, 2 lines, 12 to 212 cycles".
- step "5", name "cot_read": "COT area: cot[h], read 32 B", "test the valid flag". Cost tab: "6 instr, 1 line, 6 to 106 cycles".
- step "6", name "mark_decompressing": "kernel mem: state[h] = DECOMPRESSING, write 1 B". Cost tab: "7 instr, 0 lines, 7 cycles".

Exactly three data arrows, all starting at step 3: to step 4 with the label "free_top";
to step 5 with the label "state"; to step 6 with the label "state[h]". There is no arrow
between step 4, step 5 and step 6. One small blue note to the left of that column, between
the arrows: "4, 5, 6 do not need each other".

Four sheet tags at the right edge, each touching its box: on step 4 two tags, one above
the other, "f, to step 7" and "free_top, to step 18"; on step 5 "COT entry, to step 7"; on
step 6 "rule, to step 8".

Bottom bar, label "Lock hold A": "39 instr and 4 new cache lines: 39 to 439 cycles. Three of the lines are indexed by h, one by f."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a step box; fill any box green
or draw a gear on this sheet; connect step 4,
step 5 and step 6 to each other; draw a padlock anywhere except on the lock bracket; put
the lock bracket over step 1 or step 2; add a second figure; add a chart or a table; write
any vendor or product name; rewrite the subtitle or the bottom bar; write any non-English
text.
```

## Prompt 3：03-fault-job

```
Badge: "3"
Title: "Page Fault, Part 2: The DECOMPRESS Job, No Lock Held"
Subtitle (blue): "Scenario fault_ro, steps 7 to 12: a chain from the descriptor to a clean frame"

The legend, three rows: orange arrow "data: needs the value"; dashed arrow "rule: order required"; text only "no arrow: any order".

Layout: six step boxes in two rows of three, read left to right along the top row, then
left to right along the bottom row; then the bottom bar. There is no lock bracket and no
padlock on this sheet. Steps 7, 8, 10, 11 and 12 are kernel step boxes: white fill, no
gear. Step 9 is the only hardware step box.

Top row:
- step "7", name "desc": "kernel mem: tag, atomic add 1", "stack: fill the 48 B descriptor". Cost tab: "26 instr, 0 lines, 26 cycles". Two sheet tags touching its left side: "f, from step 4" and "COT entry, from step 5".
- step "8", name "submit": "ring: job_ring[tail], write 48 B", "HW register: write JOB_TAIL". Cost tab: "13 instr, 1 line, 1 register write, 63 to 163 cycles". One sheet tag touching its top side: "rule, from step 6".
- step "9", a hardware step box, name "hw_decompress": "chunk pool: read the chunks, check CRC-32", "frame area: write frame[f], 4096 B", "ring: write cpl_ring, raise the interrupt". Cost tab: "LZ4 HW model: 1253 ns".

Bottom row:
- step "10", name "notify": "interrupt entry and handler", "OS wakes the sleeping thread". Cost tab: "assumed 3150 ns".
- step "11", name "cpl_read": "ring: cpl_ring[head], read 16 B, always from DRAM", "HW register: write CPL_HEAD", "compare the tag". Cost tab: "12 instr, 1 line, 1 register write, 162 cycles". One sheet tag touching its bottom side: "to sheet 4: completion for steps 13 and 17, rule for step 14".
- step "12", name "cache_invalidate": "frame area: frame[f], 64 cache lines", "one invalidate per line". Cost tab: "64 cache operations, time unknown". One sheet tag touching its right side: "rule, to step 15".

Exactly four data arrows: step 7 to step 8, label "descriptor"; step 8 to step 9, label
"job ring"; step 9 to step 10, label "interrupt", running from the right end of the top
row down to the left end of the bottom row; step 10 to step 11, label "wake-up". Exactly
one rule arrow: step 11 to step 12, label "rule".

Bottom bar, label "Part 2": "One chain. The kernel's three counted steps cost 251 to 351 cycles; the interrupt, the wake-up and the LZ4 HW cost 4403 ns."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a step box; add an arrow that is not listed; write any vendor or product name; rewrite the subtitle or the bottom bar; write any non-English text; draw a padlock or a lock bracket; fill any box other than step 9 green;
draw a gear on any box other than step 9; draw a person.
```

## Prompt 4：04-fault-lock-b

```
Badge: "4"
Title: "Page Fault, Part 3: Lock Hold B and Return"
Subtitle (blue): "Scenario fault_ro, steps 13 to 20; an RW page adds steps a and b"

The legend, three rows: orange arrow "data: needs the value"; dashed arrow "rule: order required"; text only "no arrow: any order".

Layout: at the left and centre one large thin grey rounded frame that holds eight kernel
step boxes in two rows of four; two CPU step boxes and the user SW figure in a column at
the right, outside the grey frame; then the bottom bar. Every box inside the grey frame
is a kernel step box: white fill, no gear.

The grey frame encloses both rows, all eight boxes. The lock bracket lies along the top
edge of the grey frame and is exactly as wide as the frame, label
"kernel, mm_lock held for both rows: lock 4 instr, unlock 2 instr".

Upper row, left to right:
- step "13", name "note_hw": "kernel mem: strikes = 0". Cost tab: "5 instr, 0 lines, 5 cycles". Sheet tag on its top side: "completion, from step 11".
- step "14", name "set_present": "kernel mem: state[h] = PRESENT, write 1 B". Cost tab: "3 instr, 0 lines, 3 cycles". Sheet tag on its top side: "rule, from step 11".
- step "15", name "pte_map": "page table: pte[h] = frame address + flags, write 8 B". Cost tab: "6 instr, 1 line, 6 to 106 cycles". Sheet tag on its top side: "rule, from step 12".
- step "17", name "note_fresh": "kernel mem: fresh[t], put h in, take old out", "kernel mem: fresh_n[h] + 1, fresh_n[old] - 1". Cost tab: "19 instr, 2 lines, 19 to 219 cycles". Sheet tag on its top side: "completion, from step 11".

Lower row, left to right, each box directly under the box named:
- under step 13: step "18", name "wake_check": "kernel mem: free_top, compare with the low mark". Cost tab: "2 instr, 0 lines, 2 cycles". Sheet tag on its left side: "free_top, from step 4".
- under step 14: step "16", name "wake_page": "OS: wake threads waiting for page h". Cost tab: "OS call, not counted".
- under step 15: step "a", name "cot_clear": "RW page only", "COT area: cot[h] = 0, write 32 B". Cost tab: "4 instr, 0 lines, 4 cycles". Sheet tag on its left side: "completion, from step 11".
- under step 17: step "b", name "release_chunks": "RW page only", "kernel mem: bitmap, clear 5 bits". Cost tab: "80 instr, 1 line, 80 to 180 cycles".

Exactly two rule arrows inside the grey frame: a short vertical one from step 14 straight
down to step 16, label "rule"; a short horizontal one from step a to step b, label "rule".
No other arrow inside the grey frame: nothing points at step a, nothing points at step 18,
and nothing leaves step 13, step 15 or step 17.

Right column, top to bottom:
- a CPU step box, step "19", name "eret": "restore registers, return to user SW". Cost tab: "assumed 400 ns".
- a CPU step box, step "20", name "rerun": "page table: pte[h] is valid now". Cost tab: "CPU hardware, not counted".
- the user SW figure, labeled "user SW", relaxed, typing again.
One small open padlock icon sits on the right edge of the grey frame itself, at mid height
between the two rows. One rule arrow starts at this open padlock and ends at step 19,
label "all done, unlock, return". It does not start at any step box.
One data arrow from step 19 to step 20, label "PC".

Bottom bar, label "Lock hold B": "RO page: 35 instr and 3 new lines, 35 to 335 cycles. RW page: 119 instr and 4 new lines, 119 to 519 cycles."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a step box; add an arrow that is not listed; write any vendor or product name; rewrite the subtitle or the bottom bar; write any non-English text; fill any box green or draw a gear on this sheet; draw a padlock anywhere
except on the lock bracket and the one open padlock; put the grey frame or the lock bracket around step 19 or step
20; leave the lower row outside the grey frame; connect the boxes in the grey frame to
each other except for the two rule arrows listed; draw an arrow into step b from above;
start the return arrow at step 17 or at step b; leave the badge white.
```

## Prompt 5：05-first-touch

```
Badge: "5"
Title: "First Touch: A Frame of Zeros in One Lock Hold"
Subtitle (blue): "Scenario first_touch, steps 3 to 9: no LZ4 job, no second lock hold"

The legend, three rows: orange arrow "data: needs the value"; dashed arrow "rule: order required"; text only "no arrow: any order".

Layout: at the top-left the user SW figure with one sheet tag; under them a large group
under the lock bracket; then the bottom bar. Every step box on this sheet is a kernel
step box: white fill, no gear.

Top-left: the user SW figure, labeled "user SW", typing, mildly surprised. To its right
one sheet tag: "steps 1 and 2 as on sheet 2: access, exception".

The lock bracket, label "kernel, mm_lock held: lock 4 instr, unlock 2 instr", spans all
seven step boxes. Step 3 stands alone at the left, vertically centred. To its right the
other six boxes form two rows of three.
Upper row, left to right:
- step "4", name "take_frame": "kernel mem: pop free_stack, get f", "kernel mem: frame_of[h] = f, owner[f] = h". Cost tab: "12 instr, 2 lines, 12 to 212 cycles".
- step "5", name "zero_frame": "frame area: frame[f], write 4096 B of zeros", "64 lines zeroed without reading DRAM". Cost tab: "341 instr, 341 cycles".
- step "7", name "pte_map": "page table: pte[h] = frame address + flags, write 8 B". Cost tab: "6 instr, 1 line, 6 to 106 cycles".
Lower row, left to right:
- step "6", name "set_present": "kernel mem: state[h] = PRESENT, write 1 B". Cost tab: "3 instr, 0 lines, 3 cycles".
- step "8", name "note_fresh": "kernel mem: fresh[t], fresh_n[h] + 1, fresh_n[old] - 1". Cost tab: "19 instr, 2 lines, 19 to 219 cycles".
- step "9", name "wake_check": "kernel mem: free_top, compare with the low mark". Cost tab: "2 instr, 0 lines, 2 cycles".
The step at the left:
- step "3", name "check_state": "kernel mem: state[h], read 1 B: UNTOUCHED", "kernel mem: free_top, read 4 B". Cost tab: "14 instr, 1 line, 14 to 114 cycles".

Exactly five data arrows: step 3 to step 4, label "free_top"; step 4 to step 5, label "f";
step 3 to step 6, label "state[h]"; step 3 to step 8, label "state", curving under step 6;
step 4 to step 9, label "free_top", running diagonally down. Exactly one rule arrow: step
5 to step 7, label "rule: zeros before valid".

One sheet tag at the right edge of the bracket: "then eret and rerun as on sheet 4".

Bottom bar, label "One lock hold": "397 instr and 6 new lines: 397 to 997 cycles. 341 of the instructions fill the frame with zeros."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a step box; add an arrow that is not listed; write any vendor or product name; rewrite the subtitle or the bottom bar; write any non-English text; fill any box green or blue; draw a gear; draw a padlock anywhere except
on the lock bracket; connect step 6, step 8 and step 9 to each other.
```

## Prompt 6：06a-fault-rescue

```
Badge: "6A"
Title: "LZ4 HW Says Failed, the Software Rescue Works"
Subtitle (blue): "Scenario fault_rescue, an RW page, steps 12 to 23; steps 1 to 11 as on sheets 2 and 3, but the answer at step 11 is failed"

The legend, three rows: orange arrow "data: needs the value"; dashed arrow "rule: order required"; text only "no arrow: any order".

Layout: an upper band of four step boxes with one blue heading line above it; under it a
lower band, one large thin grey rounded frame that holds eight step boxes in two rows of
four; one blue note line under the frame; then the bottom bar. Twelve step boxes in all.
Every step box on this sheet is a kernel step box: white fill, no gear. There is no
person on this sheet. The badge is filled orange. Keep the boxes compact so that all
twelve fit with clear gaps.

Blue heading line above the upper band: "kernel, the faulting thread, no lock held"

Upper band: at the far left, steps 12 and 13 one above the other, step 12 on top; to
their right, in the middle of the band, step 14; at the far right step 15.
- step "12", name "cache_invalidate": "frame area: frame[f], 64 cache lines", "one invalidate per line". Cost tab: "64 cache operations, time unknown". Sheet tag on its left side: "rule, from step 11".
- step "13", name "sw_decode": "chunk pool: read the chunks of page h", "check CRC-32, decode into a kernel buffer". Cost tab: "not measured yet". Sheet tag on its left side: "completion: failed, from step 11".
- step "14", name "frame_write": "frame area: frame[f], copy 4096 B in". Cost tab: "791 instr, 791 cycles, 64 lines written".
- step "15", name "sw_clean": "frame area: frame[f], 64 cache lines", "write them back to DRAM". Cost tab: "64 cache operations, time unknown".
Exactly three data arrows inside the upper band: step 12 to step 14, label "cache[f]";
step 13 to step 14, label "page"; step 14 to step 15, label "frame[f]". There is no arrow
between step 12 and step 13.

Lower band: the grey frame. The lock bracket lies along the top edge of the grey frame and
is exactly as wide as the frame, label "kernel, mm_lock held for both rows: lock 4 instr, unlock 2 instr".
Upper row inside the frame, left to right, four boxes:
- step "17", name "cot_clear": "COT area: cot[h] = 0, write 32 B". Cost tab: "4 instr, 0 lines, 4 cycles".
- step "19", name "set_present": "kernel mem: state[h] = PRESENT, write 1 B". Cost tab: "3 instr, 0 lines, 3 cycles".
- step "22", name "note_fresh": "kernel mem: fresh[t], fresh_n[h] + 1, fresh_n[old] - 1". Cost tab: "19 instr, 2 lines, 19 to 219 cycles".
- step "20", name "pte_map": "page table: pte[h] = frame address + flags, write 8 B". Cost tab: "6 instr, 1 line, 6 to 106 cycles".
Lower row inside the frame, left to right, each box directly under the box named:
- under step 17: step "18", name "release_chunks": "kernel mem: bitmap, clear 5 bits". Cost tab: "80 instr, 1 line, 80 to 180 cycles".
- under step 19: step "21", name "wake_page": "OS: wake threads waiting for page h". Cost tab: "OS call, not counted".
- under step 22: step "16", name "note_hw": "kernel mem: strikes + 1", "at 3 strikes: lz4_off = 1". Cost tab: "5 instr, 0 lines: measured for strikes = 0". Sheet tag on its left side: "completion, from step 11".
- under step 20: step "23", name "wake_check": "kernel mem: free_top, compare with the low mark". Cost tab: "2 instr, 0 lines, 2 cycles". Sheet tag on its right side: "free_top, from step 4".

Arrows between the bands, each running from the upper band down into the upper row of
the grey frame. Exactly three rule arrows: step 13 to step 17, label "rule: good decode first";
step 13 to step 19, label "rule"; step 15 straight down to step 20, label
"rule: frame content before valid". Exactly one data arrow: step 13 to step 22, label
"page", solid orange.
Arrows inside the grey frame, exactly two rule arrows, both short and vertical: step 17
straight down to step 18, label "rule: entry first"; step 19 straight down to step 21,
label "rule: PRESENT first". No other arrow inside the grey frame: nothing touches step
16 or step 23, and no arrow runs sideways between boxes of the frame.

Blue note line under the grey frame, right aligned: "After the unlock: 24 eret and 25 rerun, drawn as steps 19 and 20 on sheet 4."

Bottom bar, label "Cost": "This sheet: 791 instr copy + 119 instr in lock hold B. Whole scenario: 1012 instr = 39 lock hold A + 51 job + 791 + 119 + 12 for two lock holds; 1212 to 2112 cycles. Decode and cache maintenance are not measured."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a step box; add an arrow that is not listed; write any vendor or product name; rewrite the subtitle or the bottom bar; write any non-English text; fill any box green or blue; draw a gear; draw a person; draw a padlock anywhere except on
the lock bracket; put the grey frame or the lock bracket around the upper band; leave
the lower row outside the grey frame; draw an arrow between step 12 and step 13; draw
an arrow to or from step 16 or step 23; draw a sideways arrow inside the grey frame;
leave the badge white.
```

## Prompt 7：07-clock-scan

```
Badge: "7"
Title: "Evicting an RO Page: The Clock Scan and One Lock Hold"
Subtitle (blue): "Scenario evict_ro, steps 1 to 6: the chunks already hold the page, so there is no LZ4 job"

The legend, three rows: orange arrow "data: needs the value"; dashed arrow "rule: order required"; text only "no arrow: any order".

Layout: at the left and centre one large thin grey rounded frame that holds six kernel
step boxes; at the right one panel with a rounded black frame; then the bottom bar. Every
step box on this sheet is a kernel step box: white fill, no gear. There is no person on
this sheet. The badge is filled orange.

The grey frame encloses all six boxes. The lock bracket lies along the top edge of the
grey frame and is exactly as wide as the frame, label
"kernel reclaimer thread, mm_lock held for all six steps: lock 4 instr, unlock 2 instr".

Inside the grey frame: steps 1 and 2 stand one above the other in a column at the left,
step 1 on top. To the right of that column there is an upper row of three boxes, steps 3,
4 and 5 from left to right, and directly under step 3 one single box, step 6.
- step "1", name "reclaim_check": "kernel mem: free_top, compare with the high mark". Cost tab: "2 instr, 0 lines, 2 cycles". One sheet tag on its left side: "woken by wake_check, sheets 4 and 5".
- step "2", name "pick_victim": "kernel mem: owner[hand], then hand + 1", "kernel mem: state[h], pins[h], fresh_n[h]", "page table: pte[h], test bit 10, the accessed flag". Cost tab: "33 instr, 4 lines, 33 to 433 cycles".
- step "3", name "pte_clear": "page table: pte[h] = 0, write 8 B". Cost tab: "2 instr, 0 lines, 2 cycles".
- step "4", name "tlb_inval": "CPU MMU: drop the TLB entry on all cores". Cost tab: "assumed 500 ns".
- step "5", name "put_frame": "kernel mem: frame_of[h] = -1, owner[f] = -1", "kernel mem: push f on free_stack". Cost tab: "13 instr, 1 line, 13 to 113 cycles".
- step "6", name "set_compressed": "kernel mem: state[h] = COMPRESSED, write 1 B". Cost tab: "3 instr, 0 lines, 3 cycles".

Exactly two data arrows, both starting at step 2: to step 3, label "victim"; to step 6,
label "state[h]". Exactly three rule arrows, each with the label "rule": step 1 down to
step 2; step 3 to step 4; step 4 to step 5. There is no arrow between step 6 and steps 3,
4 and 5. One small blue note beside step 6: "6 does not need 3, 4 or 5".
One sheet tag on the right edge of the grey frame: "then back to step 1".

Right panel, heading "inside pick_victim: what the clock hand looks at". At its top a small
drawing: a row of six frame icons with a short black arrow pointing down at one of them,
labeled "clock hand". Under it eight lines of text, one per row:
"first frame can go, RO page: 33 instr, 4 lines"
"each frame passed first adds:"
"free frame: 10 instr"
"fresh page: 20 instr, 3 lines"
"incompressible RW page: 33 instr, 3 lines"
"accessed page, flag cleared: 40 instr, 4 lines"
"measured run: 4.9 frames looked at per pick"
"longest pick: 35841, one lap of 35840 clearing flags, then 1"

Bottom bar, label "One lock hold": "53 instr and 5 new lines: 53 to 553 cycles, plus the assumed 500 ns. Every frame passed adds up to 4 more lines."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a step box; add an arrow that is not listed; write any vendor or product name; rewrite the subtitle or the bottom bar; write any non-English text; fill any box green or blue; draw a gear; draw a person; draw a padlock
anywhere except on the lock bracket; hatch a frame icon; write numbers on the clock hand
drawing; leave any step box outside the grey frame; put the right panel inside the grey
frame; draw an arrow from step 6 to step 3, 4 or 5; leave the badge white.
```

## Prompt 8：08-evict-rw-lock-a

```
Badge: "8"
Title: "Evicting an RW Page, Part 1: Lock Hold A and the Bitmap Search"
Subtitle (blue): "Scenario evict_rw, steps 1 to 7: pick the page, reserve 7 chunks, unmap the page"

The legend, three rows: orange arrow "data: needs the value"; dashed arrow "rule: order required"; text only "no arrow: any order".

Layout: at the left and centre a group under the lock bracket; at the right one panel
with a rounded frame; then the bottom bar. Every step box on this sheet is a kernel step
box: white fill, no gear. There is no person on this sheet.

The lock bracket, label "kernel reclaimer thread, mm_lock held: lock 4 instr, unlock 2 instr",
spans seven step boxes. Steps 1 and 2 stand one above the other at the left. To their
right a column of four boxes: steps 3, 4, 5 and 7 from top to bottom. Step 6 stands to
the right of step 5.
- step "1", name "reclaim_check": "kernel mem: free_top, compare with the high mark". Cost tab: "2 instr, 0 lines, 2 cycles".
- step "2", name "pick_victim": "kernel mem: owner[hand], state[h], pins[h], fresh_n[h]", "page table: pte[h], test bit 10". Cost tab: "44 instr, 4 lines, 44 to 444 cycles".
- step "3", name "reserve": "kernel mem: bitmap[cursor], set 7 bits", "kernel mem: free_chunks - 7". Cost tab: "111 instr, 1 line, 111 to 211 cycles". Sheet tag on its right side: "chunk numbers, to step 9".
- step "4", name "find_frame": "kernel mem: frame_of[h], read 4 B". Cost tab: "5 instr, 1 line, 5 to 105 cycles". Sheet tag on its right side: "f, to steps 8 and 9".
- step "5", name "pte_clear": "page table: pte[h] = 0, write 8 B". Cost tab: "2 instr, 0 lines, 2 cycles".
- step "6", name "tlb_inval": "CPU MMU: drop the TLB entry on all cores". Cost tab: "assumed 500 ns". Sheet tag on its right side: "rule, to step 8".
- step "7", name "mark_compressing": "kernel mem: state[h] = COMPRESSING, write 1 B". Cost tab: "3 instr, 0 lines, 3 cycles". Sheet tag on its right side: "rule, to step 10".

Exactly four data arrows, all starting at step 2: to step 3, label "victim"; to step 4,
label "victim"; to step 5, label "victim"; to step 7, label "state[h]". Exactly two rule
arrows, each with the label "rule": step 1 down to step 2; step 5 to step 6. There is no
arrow between steps 3, 4, 5 and 7.

Right panel, heading "inside reserve: find a free bit". At its top a small drawing: one
long strip of small square cells, some shaded solid grey and some empty, with one empty
cell circled in orange. Under it seven lines of text, one per row, with no numbering:
"read the 64-bit word at cursor"
"invert it: free bits become ones"
"bit reverse, count leading zeros: the lowest free bit"
"clear that one, repeat until 7 are taken"
"write the word back once"
"about 14 instr per chunk, 7 per word passed"
"measured run: 1.06 words per reserve, at most 2"

Bottom bar, label "Lock hold A": "167 instr and 6 new lines: 167 to 767 cycles, plus the assumed 500 ns."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a step box; add an arrow that is not listed; write any vendor or product name; rewrite the subtitle or the bottom bar; write any non-English text; fill any box green or blue; draw a gear; draw a person; draw a padlock
anywhere except on the lock bracket; use diagonal hatching anywhere; write digits inside
the strip of cells; connect steps 3, 4, 5 and 7 to each other.
```

## Prompt 9：09-evict-rw-job

```
Badge: "9"
Title: "Evicting an RW Page, Part 2: The COMPRESS Job, No Lock Held"
Subtitle (blue): "Scenario evict_rw, steps 8 to 13: three things must be ready before the doorbell"

The legend, three rows: orange arrow "data: needs the value"; dashed arrow "rule: order required"; text only "no arrow: any order".

Layout: six step boxes in two rows of three, read left to right along the top row, then
left to right along the bottom row; then the bottom bar. There is no lock bracket, no
padlock and no person on this sheet. Steps 8, 9, 10, 12 and 13 are kernel step boxes:
white fill, no gear. Step 11 is the only hardware step box.

Top row:
- step "8", name "cache_clean": "frame area: frame[f], 64 cache lines", "write dirty lines back to DRAM". Cost tab: "64 cache operations, time unknown". Two sheet tags on its left side: "f, from step 4" and "rule, from step 6".
- step "9", name "desc": "kernel mem: tag, atomic add 1", "stack: fill the 48 B descriptor, 7 chunk numbers". Cost tab: "55 instr, 0 lines, 55 cycles". Two sheet tags on its top side, side by side: "chunk numbers, from step 3" and "f, from step 4".
- step "10", name "submit": "ring: job_ring[tail], write 48 B", "HW register: write JOB_TAIL". Cost tab: "13 instr, 1 line, 1 register write, 63 to 163 cycles". One sheet tag on its top side: "rule, from step 7".

Bottom row:
- step "11", a hardware step box, name "hw_compress": "frame area: read frame[f], 4096 B", "chunk pool: write the stream, compute CRC-32", "ring: write cpl_ring, raise the interrupt". Cost tab: "LZ4 HW model: 4260 ns". Just above this box a tiny drawing: a frame icon, a short black arrow, a chunk icon.
- step "12", name "notify": "interrupt entry and handler", "OS wakes the reclaimer thread". Cost tab: "assumed 3150 ns".
- step "13", name "cpl_read": "ring: cpl_ring[head], read 16 B, always from DRAM", "HW register: write CPL_HEAD". Cost tab: "12 instr, 1 line, 1 register write, 162 cycles". One sheet tag on its right side: "completion, to steps 14 to 18".

Exactly one rule arrow: step 8 to step 10, label "rule: clean before doorbell", arching
over step 9 without touching it. Exactly four data arrows: step 9 to step 10, label
"descriptor"; step 10 to step 11, label "job ring", running from the right end of the top
row down to the left end of the bottom row; step 11 to step 12, label "interrupt"; step
12 to step 13, label "wake-up". There is no arrow between step 8 and step 9. One small
blue note between step 8 and step 9: "8 and 9 do not need each other".

Bottom bar, label "Part 2": "The kernel's three counted steps cost 280 to 380 cycles; the LZ4 HW takes 4260 ns, the interrupt and wake-up 3150 ns."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a step box; add an arrow that is not listed; write any vendor or product name; rewrite the subtitle or the bottom bar; write any non-English text; draw a padlock or a lock bracket; fill any box other than step 11 green;
draw a gear on any box other than step 11; draw a person; hatch anything except the
chunk icon.
```

## Prompt 10：10-evict-rw-lock-b

```
Badge: "10"
Title: "Evicting an RW Page, Part 3: Lock Hold B, Two Outcomes"
Subtitle (blue): "Two scenarios, each with its own steps 14 to 19; both follow step 13, cpl_read, on sheet 9"

The legend, three rows: orange arrow "data: needs the value"; dashed arrow "rule: order required"; text only "no arrow: any order".

Layout: two panels of equal width side by side, each a rounded black frame with a heading
inside its top; then two small blue note lines; then the bottom bar. Every step box on
this sheet is a kernel step box: white fill, no gear. There is no person on this sheet.
The badge is filled orange. Each panel has its own lock bracket lying along the top edge
of the panel, as wide as the panel. Each panel holds six step boxes in two rows of three,
with a clear gap between the rows. Every sheet tag on this sheet sits on the top side of
its box.

Left panel, heading "the page fits: scenario evict_rw, 5 of 7 chunks used". Lock bracket
label "kernel reclaimer thread, mm_lock held: lock 4 instr, unlock 2 instr".
Upper row, left to right:
- step "14", name "note_hw": "kernel mem: strikes = 0". Cost tab: "5 instr, 0 lines, 5 cycles". Sheet tag: "completion, from step 13".
- step "15", name "cot_store": "COT area: cot[h], write 32 B", "flags, length, CRC-32, 5 chunk numbers". Cost tab: "44 instr, 1 line, 44 to 144 cycles". Sheet tag: "completion, from step 13".
- step "16", name "trim": "kernel mem: bitmap, clear the 2 spare bits". Cost tab: "18 instr, 0 lines, 18 cycles". Sheet tag: "completion, from step 13".
Lower row, left to right:
- step "17", name "put_frame": "kernel mem: frame_of[h] = -1, owner[f] = -1", "kernel mem: push f on free_stack". Cost tab: "13 instr, 0 lines, 13 cycles". No sheet tag.
- step "18", name "set_compressed": "kernel mem: state[h] = COMPRESSED, write 1 B". Cost tab: "3 instr, 0 lines, 3 cycles". Sheet tag: "rule, from step 13".
- step "19", name "wake_page": "OS: wake threads waiting for page h". Cost tab: "OS call, not counted". No sheet tag.
Exactly two rule arrows in the left panel: from step 15 diagonally down to step 17, label
"rule: COT entry before the frame is free"; from step 18 to step 19, label "rule". No
other arrow in the left panel.

Right panel, heading "the page does not fit: scenario evict_rw_incompressible, undo". Lock
bracket label "kernel reclaimer thread, mm_lock held: lock 4 instr, unlock 2 instr".
Upper row, left to right:
- step "14", name "note_hw": "kernel mem: strikes = 0". Cost tab: "5 instr, 0 lines, 5 cycles". Sheet tag: "completion, from step 13".
- step "15", name "release_all": "kernel mem: bitmap, clear all 7 bits". Cost tab: "51 instr, 0 lines, 51 cycles". Sheet tag: "completion, from step 13".
- step "16", name "mark_incompressible": "kernel mem: incompressible, set the bit of page h". Cost tab: "8 instr, 0 lines, 8 cycles". Sheet tag: "completion, from step 13".
Lower row, left to right:
- step "17", name "set_present": "kernel mem: state[h] = PRESENT, write 1 B". Cost tab: "3 instr, 0 lines, 3 cycles". Sheet tag: "rule, from step 13".
- step "18", name "pte_map": "page table: pte[h] = frame address + flags, write 8 B". Cost tab: "6 instr, 0 lines, 6 cycles". Sheet tag: "rule, from step 13".
- step "19", name "wake_page": "OS: wake threads waiting for page h". Cost tab: "OS call, not counted". No sheet tag.
Exactly one rule arrow in the right panel: from step 17 to step 19, curving under step 18
without touching it, label "rule: PRESENT first". No other arrow in the right panel.

Two small blue note lines under the two panels, above the bottom bar, one per row:
"0 lines: that bitmap word, frame_of[h] and pte[h] were already touched in lock hold A, sheet 8"
"After step 19 the reclaimer thread loops back to step 1, reclaim_check, sheet 8"

Bottom bar, label "Lock hold B": "Fits: 83 instr and 1 new line, 83 to 183 cycles. Does not fit: 73 instr and 0 new lines, 73 cycles."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a step box; add an arrow that is not listed; write any vendor or product name; rewrite the subtitle or the bottom bar; write any non-English text; fill any box green or blue; draw a gear; draw a person; draw a padlock
anywhere except on the two lock brackets; use diagonal hatching; connect the two panels
to each other; draw any orange arrow on this sheet; leave the badge white.
```

## Prompt 11：11-totals

```
Badge: "11"
Title: "Eight Scenarios: What the Kernel's Own Steps Cost"
Subtitle (blue): "Sums of the counted kernel steps, beside the assumed overheads and the LZ4 HW model"

This sheet has no legend, no step boxes, no arrows and no figure. It is one hand-ruled
table that fills most of the sheet, then three short blue note lines, then the bottom
bar. The badge is filled orange.

The table has six columns and eight rows under a header row. Rule it with straight black
marker lines; letter every cell clearly; right-align the numbers.
Header row: "scenario", "instr", "new lines", "kernel cycles", "assumed CPU and OS, ns", "LZ4 HW model, ns".
Row one: "first_touch", "403", "6", "403 to 1003", "1000", "none".
Row two: "fault_ro", "137", "9", "337 to 1137", "4150", "1253".
Row three: "fault_rw", "221", "10", "421 to 1321", "4150", "1253".
Row four: "fault_rescue", "1012", "10", "1212 to 2112", "4150", "1253".
Row five: "fault_lost", "123", "6", "323 to 823", "3750", "1253".
Row six: "evict_ro", "59", "5", "59 to 559", "500", "none".
Row seven: "evict_rw", "342", "9", "542 to 1342", "3650", "4260".
Row eight: "evict_rw_incompressible", "332", "8", "532 to 1232", "3650", "4260".
The header cells of the columns "instr" and "new lines" carry a small pale yellow tint;
no other cell is coloured.

Three blue note lines under the table, one per row, small:
"Each sum adds 6 instr per lock hold to the step boxes. Cycles = instr + 50 per register write + 100 per line that misses."
"Low end: only the completion line misses. High end: every new line misses. The model takes 1 cycle as 1 ns."
"Not in these sums: cache maintenance of a frame, 64 operations, and the software decode."

Bottom bar, label "Reading": "The kernel's table work is 59 to 2112 cycles. Waiting for the CPU, the OS and the LZ4 HW is 500 to 7910 ns."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a row or a column; add a total
row; draw a chart, a bar or a person; write any vendor or product name; rewrite the
subtitle or the bottom bar; write any non-English text; leave the badge white.
```

## Prompt 12：06b-fault-lost

```
Badge: "6B"
Title: "LZ4 HW Says Bad Stream and It Is Right: A Lost Page"
Subtitle (blue): "Scenario fault_lost, steps 13 to 18; steps 1 to 12 as on sheets 2 and 3, but the answer at step 11 is bad stream"

The legend, three rows: orange arrow "data: needs the value"; dashed arrow "rule: order required"; text only "no arrow: any order".

Layout: three parts side by side, then the bottom bar. At the left one step box under a
blue heading line. In the centre one large thin grey rounded frame that holds four step
boxes in two rows of two. At the right one step box and the user SW figure. Every step
box on this sheet is a kernel step box: white fill, no gear. The badge is filled orange.

Left part. Blue heading line: "kernel, the faulting thread, no lock held". Under it:
- step "13", name "sw_decode": "chunk pool: read the chunks of page h", "check CRC-32, decode: the stream is damaged". Cost tab: "not measured yet". Sheet tag on its top side: "completion: bad stream, from step 11".

Centre part: the grey frame. The lock bracket lies along the top edge of the grey frame
and is exactly as wide as the frame, label "kernel, mm_lock held: lock 4 instr, unlock 2 instr".
The left column holds the two boxes that wait for step 13; step 14 stands at the top right.
Upper row, left to right, in this order: step 15 first, then step 14.
- step "15", name "put_frame": "kernel mem: frame_of[h] = -1, owner[f] = -1", "kernel mem: push f on free_stack". Cost tab: "13 instr, 0 lines, 13 cycles".
- step "14", name "note_hw": "kernel mem: strikes = 0", "the LZ4 HW was right, no strike". Cost tab: "5 instr, 0 lines, 5 cycles". Sheet tag on its top side: "completion, from step 11".
Lower row, left to right:
- step "16", name "set_lost": "kernel mem: state[h] = LOST, write 1 B". Cost tab: "3 instr, 0 lines, 3 cycles".
- step "17", name "wake_page": "OS: wake threads waiting for page h". Cost tab: "OS call, not counted".

Right part, top to bottom:
- step "18", name "kill": "OS: end this user SW". Cost tab: "OS call, not counted". Sheet tag on its top side: "also waits for step 12, cache_invalidate, on sheet 3".
- the user SW figure, labeled "user SW", dismayed, hands up.

Arrows. Exactly two rule arrows from step 13 into the grey frame, each ending at the
nearest box of the left column: to step 15, put_frame, label "rule: decode verdict first";
to step 16, set_lost, label "rule". One rule arrow from step 16 to
step 17, label "rule". One small open padlock icon sits on the right edge of the grey
frame; one rule arrow starts at this open padlock and ends at step 18, label
"all done, unlock". No arrow touches step 14. There is no orange arrow on this sheet.

Bottom bar, label "Cost": "123 instr = 39 lock hold A + 51 job + 21 lock hold B + 12 for two lock holds; the decode is not measured. The frame goes back to the free stack; the page stays LOST."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a step box; add an arrow that is not listed; write any vendor or product name; rewrite the subtitle or the bottom bar; write any non-English text; fill any box green or blue; draw a gear; draw a padlock anywhere except on the lock
bracket and the one open padlock; put step 13 or step 18 inside the grey frame; draw an
arrow to or from step 14; draw a second person; leave the badge white.
```

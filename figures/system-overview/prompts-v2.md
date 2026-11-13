# 圖像生成提示詞（第二版）：The processor and the compression layer

**對象**：用 `sketchnote-gen` skill 生成這組圖的人，以及讀圖驗收的 agent。
**目的**：讓第一次接觸這個系統的工程師看懂：processor 裡哪些東西每個 core 一份、哪些全部共用；TLB miss 由誰處理；kernel SW 為什麼只有一份卻能同時有多個 instance；共用的表與 LZ4 HW 在哪裡要先拿 lock。
**風格**：`whiteboard`（和 `figures/kernel-actions/`、`figures/page-states/` 同一種）。
**內容的來源**：平台前提 P1 到 P4 在專案的 `CLAUDE.md`。第 3、4 張照 2026-11-13 指定的 P4 畫成 N 個 engine，N 的值未定。`mm_lock` 與握 lock 兩次的順序來自 `spec/control-procedures-v0.md`。`ring_lock`、job ring、completion ring、`JOB_TAIL` 來自 `spec/hw-fw-interface.md`。`cache_clean` 與 `cache_invalidate` 來自 `spec/control-procedures-v0.md` 的 F12。第 2 張的五個步驟是從 P1 推出來的，現有的模擬裡沒有 TLB miss handler。
**約束**：圖上文字全部英文；CPU 的硬體淺藍、LZ4 HW 淺綠、kernel SW 紫色虛線框；壓縮資料畫斜線；永遠寫 CPU MMU，不單寫 MMU；不出現廠商或產品名稱；core 與 thread 的數量是示意；數字只有雙引號裡的。
**怎麼用**：skill 一張一張生，OpenAI 預設模型與 high 品質，`--size 1536x1024`；全部生完後做一次只給圖的冷讀；通過的存成本資料夾 `NN-<name>.png`。文字清單由雙引號字串自動產生。建立日期 2026-11-13。
**第二版改了什麼**：第一版在 `prompts-v1.md`。Prompt 1、2 沒有改。Prompt 3 照冷讀的結果重寫：三張表各加一行說明、instance 標明在哪個 core 的哪個 hardware thread、握兩次 lock 的順序改成右側的編號清單、不再出現沒介紹過的詞。Prompt 3、4 的 LZ4 HW 從一個 engine 改成 N 個 engine。Prompt 4 的 ring 不再寫格數。
**同一資料夾的另一張圖**：`processor-overview.svg` 是同一個主題的方塊圖，由 `gen_processor_overview.py` 產生，一張畫完全部。這組白板圖把它拆成四個問題。

## 脊椎

| # | 檔名 | 讀者的問題 | 主張 |
|---|------|------|------|
| 1 | `01-per-core-and-shared.png` | processor 長什麼樣子？哪些每個 core 一份，哪些共用？ | 每個 core 有自己的 CPU MMU、TLB 與 L1。L2 與 DRAM 只有一份。TLB hit 時整條路都是硬體。 |
| 2 | `02-tlb-miss-enters-kernel.png` | TLB miss 的時候誰去查 page table？ | CPU 不讀 page table。發生 miss 的那個 thread 進 kernel SW，查表、填回該 core 的 TLB。 |
| 3 | `03-one-kernel-many-instances.png` | kernel SW 只有一份，為什麼可以同時有好幾個在跑？它們怎麼不互相踩？ | 程式碼一份，每個進 kernel 的 hardware thread 有自己的 instance 與 stack。共用的表用 `mm_lock` 一次只進一個；LZ4 HW 工作的時候沒有人握 lock。 |
| 4 | `04-one-lz4-hw-for-every-core.png` | 所有 core 怎麼共用一個 LZ4 HW？它同時能做幾個 job？資料走哪條路？ | job 從同一個 ring 進去，放進去之前拿 `ring_lock`。有 engine 空著就取下一個 job，最多 N 個同時做，completion 照做完的順序回來。LZ4 HW 用 PA 直接讀寫 DRAM，不經過 L1 與 L2。 |

---

## Style block（每張都先貼這段）

```
Hand-drawn engineering whiteboard sheet, the kind an engineer draws to walk a colleague
through a design, dense but tidy. Aspect ratio 3:2, landscape. Plain white background.
Black marker line art with slightly wobbly strokes. Hand-lettered English text, small but
clean and fully legible. Identifiers such as pte[h] or mm_lock are lettered exactly as
quoted, keeping their square brackets and underscores.

Named objects: whenever the prompt says 'the <object>', draw the same object every time.
- a core box: a large rounded rectangle with a black outline and a plain white fill. Its
  quoted name is lettered in bold at its top-left corner, inside.
- a thread slot: a smaller rounded rectangle with a thin black outline, inside a core box,
  with its quoted name lettered at its top-left corner. It holds only what the prompt lists.
- a CPU hardware box: a rectangle with a light blue fill and a black outline, holding only
  its quoted lines, the first line in bold.
- a kernel instance: a small rounded rectangle with a dashed purple outline and a plain
  white fill, holding only its quoted lines, the first line in bold.
- a DRAM box: a rectangle with a plain white fill and a black outline, holding only its
  quoted lines, the first line in bold.
- the LZ4 HW box: a rounded rectangle with a light green fill, a black outline and a small
  gear icon on its top-right corner, holding only its quoted lines, the first line in bold.
- a padlock: a small closed padlock icon drawn in red, with its quoted name lettered in
  red right beside it.
- the lock fence: a thick grey rounded outline drawn around a group of boxes, with a
  padlock sitting on its top edge. Only what the prompt lists is inside it.
- an access arrow: a solid orange arrow with one arrowhead and a short orange label
  written along it.
- a kernel arrow: a solid purple arrow with one arrowhead and a short purple label
  written along it.
- a hardware arrow: a solid green arrow and a short green label written along it.
- a sticky note: a pale yellow sticky note with a bold heading and the quoted lines under
  it, one per row.
- the user SW figure: a round-headed stick figure sitting at a small laptop.
- a frame icon: one small plain white square with a black outline, never hatched.
- Hatching: light diagonal hatching always means compressed data and appears nowhere else.

Color rules: orange for access arrows and the title underline; purple for kernel instances
and kernel arrows; green for hardware arrows; light blue fill only for CPU hardware boxes;
light green fill only for the LZ4 HW box; red only for padlocks; grey only for the lock
fence; pale yellow only for sticky notes; blue for the subtitle line and small notes; all
other lines and text black. No gradients, no photo textures, no logos, no watermarks.

Fixed layout: a numbered square badge at the top-left; the title to its right, underlined
in orange; one blue subtitle line under the title; the boxes as the prompt places them; a
bottom bar across the full width with its label in a small box at its left.

Hard limits:
- Render every double-quoted string exactly as written, character for character, digits
  included. Correct spelling. No extra words, labels, captions, numbers or examples.
- Draw only the boxes, arrows, notes and figures listed. Do not add boxes, rows or charts.
- Arrows connect only the boxes the prompt names. No other arrows. Two boxes with no
  arrow between them must stay unconnected.
- No digits anywhere unless the prompt quotes them. No vendor or product names.
- Keep the sheet uncrowded enough that every line of text can be read.
```

## Prompt 1：01-per-core-and-shared

```
Badge: "1"
Title: "The Processor: Per Core and Shared"
Subtitle (blue): "Each core owns one CPU MMU, one TLB and one L1 cache. All cores share one L2 cache and the DRAM."

This sheet has no padlock, no lock fence, no kernel instance, no LZ4 HW box, no green
arrow, no purple arrow and no hatching.

Layout: three rows stacked in the left four fifths of the sheet; one sticky note in the
right fifth; then the bottom bar.

Row one: three core boxes side by side, all the same size, named "Core 0", "Core 1" and
"Core N". Between Core 1 and Core N there are three small black dots in a row.
Inside every one of the three core boxes, the same content from top to bottom:
- two thread slots side by side, named "T0" and "T1"
- one CPU hardware box: "CPU MMU: one TLB", "VA to PA"
- one CPU hardware box: "L1 cache"

Row two: one wide CPU hardware box lying under all three core boxes and exactly as wide as
the three together: "L2 cache: one, shared by all cores", "sees physical addresses only".

Row three: one wide DRAM box of the same width, under the L2 cache box: "DRAM".

The user SW figure, drawn small, sits inside thread slot T0 of Core 0 and is labeled
"user SW". The other five thread slots are empty. There is no other figure on the sheet.

Access arrows, in Core 0 only, forming one path from top to bottom:
- from the user SW figure down to the CPU MMU box of Core 0, label "VA"
- from the CPU MMU box of Core 0 down to the L1 cache box of Core 0, label "PA"
- from the L1 cache box of Core 0 down to the L2 cache box, label "L1 miss"
- from the L2 cache box down to the DRAM box, label "L2 miss"
In Core 1 and in Core N: one plain thin black line from the L1 cache box down to the L2
cache box, with no label and no arrowhead.

The sticky note, in the right fifth beside row one. Heading: "Platform assumptions".
Four lines: "P1: no hardware page table walk", "P2: one L1 per core, one shared L2", "P3: one TLB per core, shared by its threads", "core and thread counts are examples".

Bottom bar, label "Key point": "On a TLB hit the access goes TLB, L1, L2, DRAM in hardware only. The kernel is not involved."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a fourth core box, a third
thread slot or another cache; draw more than one figure; put orange arrows in Core 1 or
Core N; draw a padlock; hatch anything; write any vendor or product name; rewrite the
subtitle or the bottom bar; write any non-English text.
```

## Prompt 2：02-tlb-miss-enters-kernel

```
Badge: "2"
Title: "TLB Miss: The Kernel Walks the Page Table"
Subtitle (blue): "No hardware page table walk: every TLB miss is an exception on the thread that missed"

This sheet has no padlock, no lock fence, no LZ4 HW box, no green arrow and no hatching.

Layout: the left three fifths hold one large core box. The right two fifths hold, from top
to bottom, a DRAM box, a card and a sticky note. Then the bottom bar.

The core box, named "Core 0". Inside it:
- top: two thread slots side by side. The left one is narrow, named "T0", and holds only
  the line "busy with other work". The right one is wide, named "T1".
- inside thread slot T1, side by side: at the left the user SW figure, labeled "user SW";
  at the right a kernel instance: "kernel SW instance", "running on T1".
- bottom, across the full width of the core box: one CPU hardware box: "TLB of Core 0", "shared by T0 and T1".

The DRAM box, at the top of the right part, level with thread slot T1: "page table: pte[h]", "in DRAM, read only by the kernel".

Exactly four arrows. Each label begins with its step number:
- an access arrow from the user SW figure straight down to the TLB box, label "1 VA"
- an access arrow from the TLB box straight up to the kernel instance, label "2 miss: exception"
- a kernel arrow from the kernel instance to the right, to the page table box, label "3 read pte[h]"
- a kernel arrow from the kernel instance straight down to the TLB box, drawn to the right
  of arrow 2, label "4 write the entry"
A small blue note just above the user SW figure, with no arrow: "5 rerun the access: TLB hit".

The card, under the DRAM box: a rounded rectangle with a black outline. Heading: "One access, three outcomes".
Three lines: "TLB hit: hardware only", "TLB miss, page in a frame: the kernel refills the TLB", "TLB miss, page compressed: the kernel calls the LZ4 HW, then refills".

The sticky note, under the card. Heading: "TLBs are private copies".
Two lines: "hardware does not keep them in sync", "before compressing a page, the kernel clears it from every core's TLB".

Bottom bar, label "Key point": "The CPU never reads the page table. Every decompression fault starts as a TLB miss, so the kernel is already on this path."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a second core box or a third
thread slot; draw an arrow from the CPU hardware box to the page table box; draw more
than four arrows; draw more than one figure; draw a padlock; hatch anything; write any
vendor or product name; rewrite the subtitle or the bottom bar; write any non-English text.
```

## Prompt 3：03-one-kernel-many-instances

```
Badge: "3"
Title: "One Kernel, Many Instances"
Subtitle (blue): "Every hardware thread that enters the kernel runs the same code on its own stack. Shared tables are entered one instance at a time."

This sheet has no user SW figure, no core box, no thread slot, no CPU hardware box, no
orange arrow and no hatching.

Layout: the left three quarters of the sheet hold three rows, A, B and C, from top to
bottom. The right quarter holds one sticky note, level with rows B and C. Then the bottom
bar across the full width.

Row A: one wide DRAM box with a thick purple outline, across the left three quarters: "kernel SW code: one copy in DRAM".

Row B: three kernel instances side by side, the same size, evenly spaced.
- the left one: "kernel SW instance", "Core 0, thread T0", "own stack"
- the middle one: "kernel SW instance", "Core 0, thread T1", "own stack"
- the right one: "kernel SW instance", "Core N, thread T0", "own stack"
From the box in row A, three thin dashed purple lines without arrowheads run down, one to
each kernel instance. Only the line to the left instance has a label: "same code".

Row C, under the left and the middle instance: the lock fence, with a padlock named
"mm_lock" on its top edge. Inside the fence, three DRAM boxes side by side, each with two
lines:
- "page table", "where each page is now"
- "kernel tables", "page states, free frames, free chunks"
- "COT", "where each compressed page is stored"
Row C, under the right instance and outside the fence: the LZ4 HW box: "LZ4 HW", "N engines, up to N jobs at once".

Exactly three kernel arrows:
- from the left instance down into the lock fence, its arrowhead inside the fence, label "holds mm_lock: inside"
- from the middle instance down to the top edge of the lock fence, its arrowhead stopping
  outside the fence, label "waits for mm_lock"
- from the right instance down to the LZ4 HW box, label "its job is running: holds no lock"

The sticky note, in the right quarter. Heading: "A compressed page takes mm_lock twice".
Three lines, one per row, from top to bottom: "1 with mm_lock: check the tables, take a frame", "2 with no lock: the LZ4 HW decompresses", "3 with mm_lock again: map the page".
No arrow touches the sticky note.

Bottom bar, label "Key point": "The code exists once and an instance exists per thread inside the kernel. One instance at a time holds mm_lock, and nobody holds it while the LZ4 HW works."

Text manifest: auto

Do not: write any digit or number that is not quoted; draw a core box or a thread slot;
add a fourth kernel instance; draw a second padlock; draw a person; put the LZ4 HW box
inside the lock fence; draw an arrow from the lock fence to the LZ4 HW box; draw an arrow
to or from the sticky note; hatch anything; write any vendor or product name; rewrite the
subtitle or the bottom bar; write any non-English text.
```

## Prompt 4：04-one-lz4-hw-for-every-core

```
Badge: "4"
Title: "One LZ4 HW, N Engines, Every Core"
Subtitle (blue): "Jobs enter through one ring and a free engine takes the next one. Page data never passes L1 or L2."

This sheet has no user SW figure, no core box, no thread slot and no orange arrow.

Layout: an upper band and a lower band, then the bottom bar.

Upper band, from left to right:
- at the left, two kernel instances, one above the other. The upper one: "kernel SW instance", "on Core 0". The lower one: "kernel SW instance", "on Core 1".
- in the centre, the lock fence with a padlock named "ring_lock" on its top edge. Inside
  the fence: one row of eight small empty square cells, with the label "job ring" under the row.
- under the lock fence and outside it: a second row of eight small empty square cells,
  with the label "completion ring" under the row. No fence and no padlock around it.
- at the right, the LZ4 HW box, large. Its lines: "LZ4 HW", "up to N jobs at once". Under
  those lines, still inside the LZ4 HW box, three small white rounded boxes in a row, the
  same size, lettered "engine 0", "engine 1" and "engine N-1", with three small black dots
  between the second and the third. Under the three small boxes one more line: "engines share no data".
- under the LZ4 HW box, a small blue note: "N is a hardware parameter, not decided yet".

Arrows in the upper band, exactly four:
- two kernel arrows, one from each kernel instance, to the job ring. Only the upper one
  has a label: "write a descriptor"
- a kernel arrow from the job ring to the LZ4 HW box, label "a free engine takes the next job"
- a hardware arrow with one arrowhead from the LZ4 HW box to the completion ring, label "completions, in finish order"
- a hardware arrow with one arrowhead from the completion ring to the left, to the lower
  kernel instance, label "interrupt: match by tag"

Lower band, from left to right:
- at the left, one CPU hardware box: "L1 and L2 caches". Under it a small blue note of
  three lines: "not on this path", "cache_clean before COMPRESS", "cache_invalidate after DECOMPRESS".
  No arrow touches this box.
- to its right, one long horizontal bar with a black outline, with the label "DRAM" at its
  left end, split into two cells. The left cell is filled with light diagonal hatching
  and holds, on a small white patch, "chunk pool: compressed streams". The right cell is
  not hatched and holds "frame region: 4096 B pages" and four frame icons in a row.

Two more hardware arrows, each with an arrowhead at both ends, from the LZ4 HW box down
to the bar: one to the chunk pool cell, label "stream"; one to the frame region cell,
label "page".

Bottom bar, label "Key point": "ring_lock covers only queuing a job. Up to N jobs run at once and may finish in any order. Their data moves straight between the LZ4 HW and DRAM."

Text manifest: auto

Do not: write any digit or number that is not quoted; draw a padlock on the completion
ring or a second padlock anywhere; draw any arrow to or from the L1 and L2 caches box;
hatch anything except the chunk pool cell; draw a person; add a second LZ4 HW box; draw a
fourth engine box; write a slot count on either ring; write any vendor or product name;
rewrite the subtitle or the bottom bar; write any non-English text.
```

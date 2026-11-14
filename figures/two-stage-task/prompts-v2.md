# 圖像生成提示詞：two-stage task

**版本**：第二版，2026-11-14。第一版存在 `prompts-v1.md`，它的圖在 `gen1/`。

第二版照負責人的兩點意見修改：
1. 左邊要畫出既有、成熟的記憶體管理框架有很多部分，page swap 是其中一個。右邊再畫成這個部分的特例，讓讀者相信第二段是第一段的延伸。
2. 左邊要看得出是 multi-core、multi-thread 的 processor。工作清單要有相關的項目，不要畫得太簡單。

另外採用第一版冷讀者的兩點：
- CPU MMU 到 kernel SW 補上 TLB miss 的箭頭。
- 右邊的便條分開寫「不變的」與「新的」，不低估第二段的設計工作。

**對象**：用 `sketchnote-gen` skill 生成這張圖的人，以及讀圖驗收的 agent。

**目的**：讓第一次碰這顆 processor 的團隊看懂這次工作的性質。工作分兩段：
1. 第一段：processor 本來就有 CPU MMU，但團隊沒有裝上、也沒有開啟過。這一段把 CPU MMU 與它上面的記憶體管理框架整合進來、打通，並在多個 core 與 thread 上驗證。這是成熟的設計，困難只在團隊不熟。
2. 第二段：框架裡的 page swap 這一部分加上 LZ4 HW。page 不 swap 到 disk，而是 swap 到 DRAM 裡壓縮過的空間。

**風格**：`whiteboard`。style block 從 `figures/system-overview/` 改來，顏色的意思相同。

**內容的來源**：
- 負責人 2026-11-14 的說明。
- 平台前提 P1 到 P3 在專案的 `CLAUDE.md`：
  - P1：TLB miss 一律進 kernel SW。
  - P2：每個 core 有自己的 L1，所有 core 共用 L2。
  - P3：每個 core 一個 TLB，由該 core 的 hardware thread 共用。
- 圖上畫兩個 core、每個 core 兩個 thread，只是範例，圖上註明。

**約束**：
- 圖上文字全部英文。
- 永遠寫 CPU MMU，不單寫 MMU。
- 不出現廠商或產品名稱。
- 斜線只代表壓縮過的資料。
- 數字只有雙引號裡的。
- disk 只當作一般 swap 的對照，不畫任何箭頭連到它。這個平台有沒有 disk 不知道。

**怎麼用**：OpenAI 預設模型，high 品質，`--size 1536x1024`。文字清單由雙引號字串自動產生。

## 脊椎

| # | 檔名 | 讀者的問題 | 主張 |
|---|------|------|------|
| 1 | `01-two-stages.png` | 這次的工作到底是什麼，難在哪裡？ | 第一段：在 multi-core、multi-thread 的 processor 上，把成熟但我們沒用過的 CPU MMU 與記憶體管理框架打通並驗證。第二段：框架裡的 page swap 是其中一部分，我們只做它的一個特例，把 swap 的目的地換成 DRAM 裡壓縮過的空間，由 LZ4 HW 搬。 |
| 2 | `02-apart-in-space-and-time.png` | 既然第二段是第一段的延伸，CPU MMU 與壓縮層會不會綁在一起？ | 不會。空間上，CPU MMU 在每個 core 裡、在每一次 access 的路上；LZ4 HW 在 processor 外、DRAM 旁，不在 access 的路上。兩邊查的表也不同。時間上，CPU MMU 每次 access 都動，kernel SW 常因 TLB miss 被叫起來；壓縮層只在 page swap 時動，很稀疏。frame region 比 L2 大很多倍，page swap 只在 working set 超過 frame region 時發生；少但每一次都算進 WCET。 |

第 2 張是負責人 2026-11-14 要的。內容和 `figures/cpu-mmu-basics/` 的第 D 張重疊在時間軸與頻率的部分。這一張多了空間：兩邊在架構上的位置與各自查的表。比例的論點照負責人的意思放上 L2 與 frame region，但條件寫成 working set 超過 frame region，因為 page swap 的次數由 frame region 對 working set 決定，L2 只改變每一次 access 的代價。時間軸的間距不是量測。

---

## Style block（每張都先貼這段）

```
Hand-drawn engineering whiteboard sheet, the kind an engineer draws to walk a colleague
through a plan, dense but tidy. Aspect ratio 3:2, landscape. Plain white background.
Black marker line art with slightly wobbly strokes. Hand-lettered English text, small but
clean and fully legible.

Named objects: whenever the prompt says 'the <object>', draw the same object every time.
- a panel: a large rounded rectangle with a black outline and a plain white fill. Its
  quoted name is lettered in bold at its top-left corner, inside.
- a core box: a rounded rectangle with a black outline and a plain white fill. Its quoted
  name is lettered in bold at its top-left corner, inside.
- a thread slot: a small rounded rectangle with a thin black outline inside a core box,
  holding only its quoted label.
- a CPU hardware box: a rectangle with a light blue fill and a black outline, holding only
  its quoted lines, the first line in bold.
- a kernel instance: a small rounded rectangle with a dashed purple outline and a plain
  white fill, holding only its quoted lines, the first line in bold.
- a part tile: a small rounded rectangle with a solid purple outline and a plain white
  fill, holding only its quoted label. Tiles in one group are all the same size.
- a DRAM box: a rectangle with a plain white fill and a black outline. Its quoted name is
  lettered in bold at its top-left corner, inside. It holds only what the prompt lists.
- the LZ4 HW box: a rounded rectangle with a light green fill, a black outline and a small
  gear icon on its top-right corner, holding only its quoted lines, the first line in bold.
- a frame icon: one small plain white square with a black outline, never hatched.
- a chunk icon: one small square with a black outline filled with light diagonal hatching.
- the disk icon: a small cylinder drawn with a thin black outline and a plain white fill.
- an access arrow: a solid orange arrow with one arrowhead and a short orange label
  written along it.
- a kernel arrow: a solid purple arrow with one arrowhead and a short purple label
  written along it.
- a hardware arrow: a solid green arrow with one arrowhead and a short green label written
  along it.
- the zoom lines: two thin straight black lines with no arrowheads, like the lines from a
  magnifying glass, joining the two corners of one small tile to the two corners of a
  large box, so the large box reads as an enlarged view of the tile.
- a card: a rounded rectangle with a black outline and a plain white fill, a bold heading
  and the quoted lines under it, one per row, each row starting with a small check box.
- a sticky note: a pale yellow sticky note with a bold heading and the quoted lines under
  it, one per row.
- a tag: a small rounded label with a thick black outline, its quoted text in bold capitals.
- Hatching: light diagonal hatching always means compressed data and appears nowhere else.

Color rules: orange for access arrows and the title underline; purple for kernel
instances, part tiles and kernel arrows; green for hardware arrows; light blue fill only
for CPU hardware boxes; light green fill only for the LZ4 HW box; pale yellow only for
sticky notes; blue for the subtitle line and small notes; all other lines and text black.
No gradients, no photo textures, no logos, no watermarks.

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

## Prompt 1：01-two-stages

```
Badge: "1"
Title: "The Task in Two Stages"
Subtitle (blue): "The CPU MMU and the memory management built on it are mature but new to us. Compression is a special case of one of its parts: page swap."

This sheet has no person and no stick figure.

Layout: two panels side by side. The left panel takes about three fifths of the width, the
right panel about two fifths, with a narrow gap between them. Then the bottom bar across
the full width.

THE LEFT PANEL, named "Stage 1: bring up the CPU MMU and memory management". At its
top-right corner, inside, a tag: "MATURE DESIGN, NEW TO US". The panel has an upper half
and a lower half.

Upper half of the left panel, two blocks side by side.

Upper-left block: one large box with a black outline named "processor". Inside it, two core
boxes of the same size side by side, named "Core 0" and "Core 1". Each core box holds, from
top to bottom:
- two thread slots side by side, labeled "hw thread" and "hw thread";
- one CPU hardware box: "CPU MMU and TLB", "one TLB, shared by both threads";
- one CPU hardware box: "L1".
Under the two core boxes, still inside the processor box, one wide CPU hardware box
spanning both cores: "L2", "shared by all cores". Under the processor box, in small blue
letters: "two cores, two threads each: an example". Under that, one DRAM box named "DRAM"
holding two small labels side by side: "page tables" and "frames", with three frame icons
under the word frames.

Upper-right block: one group box with a dashed purple outline, its bold purple heading
"memory management in kernel SW: known parts". Inside it, six part tiles in two columns and
three rows, all the same size, labeled:
"page tables", "TLB miss handler",
"page fault", "frame allocator",
"clear a page from every core's TLB", "page swap".
The "page swap" tile, bottom-right, has a thick black outline over its purple outline so it
stands out. All other tiles look the same as each other.

Arrows in the left panel, exactly two:
- an access arrow from the left thread slot of Core 0 down to the CPU MMU and TLB box of
  Core 0, label "every access"
- a kernel arrow from the CPU MMU and TLB box of Core 1 to the right, to the "TLB miss handler"
  tile, label "TLB miss enters kernel SW"

Lower half of the left panel: a card on the left two thirds and a sticky note on the right
third.

The card. Heading: "Our work". Seven lines:
"integrate the CPU MMU and the caches into our system",
"bring up each known part on this processor",
"page tables shared by all cores, kept consistent with locks",
"two threads of one core can miss on the same TLB at once",
"clear a page from every core's TLB before reusing its frame",
"keep L1 and L2 correct when a frame changes owner",
"tests on every core and thread, not just one".

The sticky note. Heading: "Why we can expect it to work".
Two lines: "the CPU MMU and these parts are a proven, mature design",
"the hard part is that it is new to us, not the hardware".

THE ZOOM LINES join the two right-hand corners of the "page swap" tile to the two left-hand
corners of the right panel, so the whole right panel reads as an enlarged view of the page
swap tile. Along the upper zoom line, in small black letters: "zoom in on page swap".
No other line crosses the gap between the panels.

THE RIGHT PANEL, named "Stage 2: compression inside page swap". At its top-right corner,
inside, a tag: "A SPECIAL CASE OF PAGE SWAP". The panel has three parts from top to bottom.

Top part of the right panel, a small sketch:
- at the top-left, a kernel instance: "page swap", "page out, page back in".
- at the top-right, the disk icon with the small blue label under it:
  "the usual destination". No arrow touches the disk icon.
- under the kernel instance, the LZ4 HW box: "LZ4 HW", "outside the processor".
- under the LZ4 HW box, one DRAM box named "DRAM" with two areas side by side. The left
  area holds three frame icons in a row with the label "frames: hot pages". The right area
  holds four chunk icons in a row with the label "compressed space: cold pages".
- exactly three arrows in this sketch:
  - a kernel arrow from the kernel instance down to the LZ4 HW box, label "hands it a job"
  - a hardware arrow from the LZ4 HW box down to the compressed space, label "page out: COMPRESS"
  - a hardware arrow from the LZ4 HW box down to the frames, label "page back in: DECOMPRESS"

Middle part of the right panel, a card. Heading: "Our work". Four lines:
"LZ4 HW and the kernel SW that drives it",
"manage the compressed space in DRAM",
"choose which pages go cold",
"tests: every page comes back unchanged".

Bottom part of the right panel, a sticky note. Heading: "What stays, what is new".
Two lines: "stays: the page swap flow of page fault, page out, page back in",
"new: the destination, compressed DRAM, and how it is managed".

Bottom bar, label "Key point": "Stage 1 brings up a mature CPU MMU and its memory management on many cores and threads. Stage 2 takes one of those parts, page swap, and gives it a new destination: compressed space in DRAM, moved by LZ4 HW."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the core
names; draw any person or stick figure; draw any arrow to or from the disk icon; draw the
LZ4 HW box in the left panel; hatch anything in the left panel; hatch a frame icon; add a
seventh part tile; give any tile other than page swap a thick outline; add a third core
box or a third thread slot in a core; draw a thick arrow between the panels; draw more
than five arrows in total, not counting the zoom lines; write MMU without CPU in front of
it; write any vendor or product name; rewrite the subtitle or the bottom bar; write any
non-English text.
```

## Prompt 2：02-apart-in-space-and-time

```
Badge: "2"
Title: "CPU MMU and Compression Layer: Apart in Space and Time"
Subtitle (blue): "The CPU MMU stands on every access inside each core. The compression layer stands beside DRAM and works only when a page swaps."

This sheet has no person and no stick figure, and no zoom lines.

Layout: an upper band about three fifths of the sheet height, a lower band, then the
bottom bar across the full width.

THE UPPER BAND is one panel named "Space: where each one sits". Inside it, three columns
side by side, and under all three columns one wide DRAM box.

Left column: one box with a black outline named "processor". Inside it, two core boxes of
the same size side by side, named "Core 0" and "Core 1". Each core box holds, from top to
bottom: two thread slots side by side, labeled "hw thread" and "hw thread"; one CPU
hardware box "CPU MMU and TLB"; one CPU hardware box "L1". Under the two core boxes, still
inside the processor box, one wide CPU hardware box spanning both cores: "L2". Just above
the processor box, a tag: "ON EVERY ACCESS".

Middle column: two kernel instances stacked, one above the other, with a gap between.
- upper one, level with the CPU MMU and TLB boxes: "kernel SW: TLB miss", "read one PTE, fill the TLB"
- lower one: "kernel SW: page swap", "read the COT, hand LZ4 HW a job"

Right column: the LZ4 HW box: "LZ4 HW", "outside the processor". It is level with the lower
kernel instance. Just above the LZ4 HW box, a tag: "OFF THE ACCESS PATH".

The DRAM box, named "DRAM", across the full width under the three columns. Inside it, four
areas side by side, separated by thin dashed vertical lines:
- under the processor: "frame region: hot pages" with four frame icons in a row
- under the LZ4 HW box's left edge: "chunk pool: cold pages" with four chunk icons in a row
- under the middle column, left: a small table outline labeled "page table"
- under the middle column, right: a small table outline labeled "COT: where each compressed page is"
Arrange the four areas so that each arrow below can run straight down or diagonally
without crossing another arrow: frame region at the far left, then page table, then COT,
then chunk pool at the far right.

Exactly seven arrows in the upper band:
- an access arrow that starts at the left hw thread of Core 0 and runs straight down
  through the CPU MMU and TLB box, the L1 box and the L2 box of the processor into the
  frame region, label "every load and store"
- a kernel arrow from the upper kernel instance to the left, to the CPU MMU and TLB box of
  Core 1, label "fills the TLB"
- a kernel arrow from the upper kernel instance down to the page table, label "one PTE"
- a kernel arrow from the lower kernel instance down to the COT, label "which chunks"
- a kernel arrow from the lower kernel instance to the right, to the LZ4 HW box, label "a job"
- a hardware arrow from the LZ4 HW box straight down to the chunk pool, label "COMPRESS"
- a hardware arrow from the LZ4 HW box down and to the left to the frame region, passing
  under the page table and the COT inside the DRAM box, label "DECOMPRESS"
No arrow touches the LZ4 HW box except these three. No arrow joins the processor to the
LZ4 HW box.

THE LOWER BAND holds a timeline panel across the left three fifths and, in the right two
fifths, a rate panel above a sticky note.

The timeline panel, named "Time: how often each one works". Three horizontal lanes stacked,
all the same length, each with its bold label at its left end. Under the lowest lane, one
thin black horizontal axis line with one arrowhead at its right end, labeled "time".
Under the axis, in small blue letters: "spacing drawn to show the contrast, not measured".
- top lane, label "CPU MMU: TLB lookup": a dense row of very thin orange ticks packed so
  close together that the lane looks almost solid along its whole length.
- middle lane, label "kernel SW: TLB miss": short purple ticks, all the same height, many
  of them, spread unevenly along the whole lane, with small gaps between them.
- bottom lane, label "kernel SW and LZ4 HW: page swap": a thin empty line along the whole
  lane with exactly two short blocks on it, each a kernel instance with a light green
  inner stripe, holding only the word "page swap". One block sits near the left third, the
  other near the right end. Nothing else is on this lane.

The rate panel, in the upper part of the right two fifths. A bold heading at its top:
"Why page swap is rare". Under it, one long thin horizontal bar with a black outline and a
plain white fill, labeled inside in small letters: "pages user SW touches". Directly above
the bar, two brackets that both start at the bar's left end and open downward toward it,
stacked so they do not overlap: a short one labeled "L2: where most accesses end", and a
long one labeled "frame region: hot pages" that ends a little before the bar's right end.
The small part of the bar past the end of the long bracket has light diagonal hatching.
Under the bar, two small blue lines: "the frame region is many times the L2",
"page swap happens only when the working set outgrows the frame region".

The sticky note, under the rate panel. Heading: "Rare is not free".
Two lines: "each page swap: locks, a COT lookup, an LZ4 HW job",
"the user SW waiting on it feels the worst case: budget the WCET".

Bottom bar, label "Key point": "The CPU MMU sits inside every core, on every access, and wakes kernel SW often. The compression layer sits outside, beside DRAM, and works only on page swap: rarely, but each time counts toward the worst case."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the core
names; draw any person or stick figure; draw an arrow between the processor and the LZ4
HW box; draw the LZ4 HW box inside the processor; put more than two blocks on the page
swap lane; draw a clock, a ruler or numbers on the time axis; draw a chart or percentages;
hatch anything except the chunk icons and the end of the rate bar; hatch a frame icon;
add a third core box or a third thread slot in a core; draw more than seven arrows in the
upper band; draw any arrow in the lower band; let two arrows cross; write MMU without CPU
in front of it; write any vendor or product name; rewrite the subtitle or the bottom bar;
write any non-English text.
```

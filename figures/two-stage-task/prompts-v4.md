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
| 3 | `03-apart-even-in-software.png` | 壓縮層現在是純 kernel SW，為什麼不乾脆和 CPU MMU 的 kernel SW 一起設計？ | 因為兩邊將來長到不同的地方。CPU MMU 這邊的加速就是 TLB，在每個 core 裡，每個 core 一份。壓縮這邊要加速時，是所有 core 共用的一套，放在 LZ4 HW 旁邊，由一個總管使用。一起設計會把每個 core 一份的東西和共用一套的東西綁在一起。所以兩邊分開設計、分開開發，只用一條 request queue 相接。 |

第 3 張是負責人 2026-11-14 要的，主題仍是「兩邊要分開」，補的論點是：即使壓縮層是純 kernel SW，將來的硬體加速也是共用一套、放在 LZ4 HW 旁邊，和 CPU MMU 每個 core 一份的性質不同。一個總管可以分給平行的 worker，只是補充，用一行小字帶過。硬體加速的原則照負責人的說法：先用 kernel SW，針對特定子動作，kernel SW 能接手硬體寫的任何東西。這些都是方向，還沒有定案，圖上標 proposal。

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
- a domain frame: a very large rectangle drawn with a very thick dashed outline in the
  color the prompt gives, plain white inside, its quoted name in large bold letters of
  that same color at its top-left corner, inside. It encloses only what the prompt lists.
- Hatching: light diagonal hatching always means compressed data and appears nowhere else.

Color rules: orange for access arrows and the title underline; purple for kernel
instances, part tiles and kernel arrows; green for hardware arrows; light blue fill only
for CPU hardware boxes; light green fill only for the LZ4 HW box; pale yellow only for
sticky notes; blue for the subtitle line and small notes; dark blue and dark green only
for the two domain frames and their names and big words; all other lines and text black.
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

第三版，2026-11-14。第二版的圖在 `gen4/`，採用過 `.r4`，冷讀困惑指數 2，提示詞在 `prompts-v3.md`。

負責人看過第二版，說內容準確，但視覺上不夠突出「兩個獨立的工作範圍」。這一版照負責人的建議修改：
- 用兩個粗虛線大框框出兩塊範圍：藍框是 CPU MMU 與它的 kernel SW，綠框是 LZ4 HW 與它的 kernel SW。
- 時間軸分進各自的框，兩條等長、代表同一段時間，旁邊用大字標 DENSE 與 SPARSE。

為了騰出空間，比例長條拿掉，條件改寫成便條裡的一行。L2 改放在 access 箭頭的標籤上，只說大部分 access 停在 L1 或 L2。這樣冷讀者兩次指出的「L2 和 page swap 的關係不清楚」不會再出現。

同時修掉第二版冷讀者指出的幾點：
- access、TLB miss、fills the TLB 都畫在同一個 core。
- 補上 CPU MMU 到 kernel SW 的 TLB miss 箭頭。
- 箭頭不交叉。

```
Badge: "2"
Title: "CPU MMU and Compression Layer: Apart in Space and Time"
Subtitle (blue): "Two separate domains. The CPU MMU stands on every access inside each core. The compression layer stands beside DRAM and works only when a page swaps."

This sheet has no person, no stick figure, no zoom lines, no card and no chart.

Layout: two domain frames side by side fill most of the sheet, the left one and the right
one, the same size and the same height, with a gap between them about one sixth of the
sheet width. The gap holds a few shared items described below. Then the bottom bar across
the full width. Each domain frame has an upper part, the space sketch, and a lower part,
the timeline. The two timelines sit at the same height and have the same length.

THE LEFT DOMAIN FRAME, dark blue, named "CPU MMU domain". Just right of its name, a tag:
"ON EVERY ACCESS".

Upper part of the left frame:
- left two thirds: one box with a black outline named "processor". Inside it, two core
  boxes of the same size side by side, named "Core 0" and "Core 1". Each core box holds,
  from top to bottom: two thread slots side by side, labeled "hw thread" and "hw thread";
  one CPU hardware box "CPU MMU and TLB"; one CPU hardware box "L1". Under the two core
  boxes, still inside the processor box, one wide CPU hardware box spanning both cores:
  "L2".
- right third, at the top, level with the CPU MMU and TLB boxes: a kernel instance:
  "kernel SW: TLB miss", "read one PTE, fill the TLB".
- right third, under the kernel instance, level with the L1 boxes: a small table outline
  labeled "page table, in DRAM".

Arrows in the left frame, exactly five, all on Core 1, none crossing:
- an access arrow, solid, from the right hw thread of Core 1 straight down through the
  CPU MMU and TLB box and the L1 box, ending on the L2 box, label
  "every load and store; most end in L1 or L2"
- a kernel arrow from the CPU MMU and TLB box of Core 1 to the right, to the kernel
  instance, label "TLB miss"
- a kernel arrow from the kernel instance back to the left, to the CPU MMU and TLB box of
  Core 1, drawn just below the first one and parallel to it, label "fills the TLB"
- a kernel arrow from the kernel instance straight down to the page table, label "one PTE"
- an access arrow drawn as a dashed orange line with one arrowhead, from the right end of
  the L2 box to the right, passing under the page table, out through the right side of
  the left frame, into the frame region in the gap, label "on an L2 miss"

Lower part of the left frame, the timeline. Two horizontal lanes stacked, the same length,
each with its bold label at its left end, and under them one thin black axis line with one
arrowhead at its right end, labeled "time".
- upper lane, label "TLB lookup": a dense row of very thin orange ticks packed so close
  together that the lane looks almost solid along its whole length.
- lower lane, label "kernel SW: TLB miss": many short purple ticks, all the same height,
  spread unevenly along the whole lane.
Above the two lanes, in very large bold dark blue capitals: "DENSE", with beside it in
smaller dark blue letters: "every access; kernel SW on every TLB miss".

THE RIGHT DOMAIN FRAME, dark green, named "compression domain". Just right of its name, a
tag: "OFF THE ACCESS PATH".

Upper part of the right frame:
- top row, left: the LZ4 HW box: "LZ4 HW", "outside the processor".
- top row, right: a kernel instance: "kernel SW: page swap", "read the COT, hand LZ4 HW a job".
- second row, left, under the LZ4 HW box: four chunk icons in a row with the label
  "chunk pool: cold pages, in DRAM".
- second row, right, under the kernel instance: a small table outline labeled
  "COT, in DRAM: where each compressed page is".
- third row, across the right frame: a sticky note. Heading: "Rare, but each one counts".
  Two lines: "page swap happens only when the pages in use outgrow the frame region",
  "each one takes locks, a COT lookup and an LZ4 HW job: budget the WCET".

Arrows in the right frame, exactly four, none crossing:
- a kernel arrow from the kernel instance to the left, to the LZ4 HW box, label "a job"
- a kernel arrow from the kernel instance straight down to the COT, label "which chunks"
- a hardware arrow from the LZ4 HW box straight down to the chunk pool, label "COMPRESS"
- a hardware arrow from the left side of the LZ4 HW box to the left, out through the left
  side of the right frame, into the frame region in the gap, label "DECOMPRESS"

Lower part of the right frame, the timeline, at the same height and the same length as
the left one. One horizontal lane with its bold label at its left end,
"kernel SW and LZ4 HW: page swap", and under it one thin black axis line with one
arrowhead at its right end, labeled "time". The lane is a thin empty line with exactly two
short blocks on it, one near the left third and one near the right end. Each block is a
kernel instance, dashed purple outline and white fill, holding only the word "page swap",
with one tiny light green box with a gear icon touching its right end. Nothing else is on
the lane.
Above the lane, in very large bold dark green capitals: "SPARSE", with beside it in
smaller dark green letters: "only when a page swaps".

THE GAP between the two frames, from top to bottom:
- in small blue letters: "one kernel SW, two separate jobs and tables"
- a DRAM box named "frame region" holding three frame icons stacked or in a small grid,
  with under them the small label "hot pages, used by both". The dashed orange arrow from
  the left and the DECOMPRESS arrow from the right both end on this box.
- level with the two timelines, in small blue letters: "both timelines: the same stretch of time, spacing not measured"

Bottom bar, label "Key point": "The CPU MMU sits inside every core, on every access, and wakes kernel SW often. The compression layer sits outside, beside DRAM, and works only on page swap: rarely, but each time counts toward the worst case."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the core
names; draw any person or stick figure; draw any arrow between the processor and the LZ4
HW box; draw the LZ4 HW box inside the left frame; put the frame region inside either
domain frame; let any two arrows cross; draw the solid orange arrow past the L2 box; put
more than two blocks on the page swap lane; draw a clock, a ruler or numbers on a time
axis; draw a chart, a bar or percentages; hatch anything except the chunk icons; hatch a
frame icon; add a third core box or a third thread slot in a core; draw more than nine
arrows in total; write MMU without CPU in front of it; write any vendor or product name;
rewrite the subtitle or the bottom bar; write any non-English text.
```

## Prompt 3：03-apart-even-in-software

第一版，2026-11-14。生成後發現「the only link」與「meet only at a request queue」不準：總管還要改 PTE、清每個 core 的 TLB，這兩件屬於 CPU MMU 那邊。改成窄的介面，用 edit 修圖。

```
Badge: "3"
Title: "Apart Even in Software"
Subtitle (blue): "The compression layer starts as pure kernel SW. That is no reason to design it together with the CPU MMU's kernel SW: the two grow in different places."

This sheet has no person, no stick figure, no zoom lines, no timeline and no chart.

Layout: an upper band about three fifths of the sheet height holding two domain frames
side by side, the same size, with a gap between them about one sixth of the sheet width.
Under them, across the full width, a table on the left two thirds and a sticky note on the
right third. Then the bottom bar.

THE LEFT DOMAIN FRAME, dark blue, named "CPU MMU domain".
Inside it, one box with a black outline named "processor". Inside the processor, two core
boxes of the same size side by side, named "Core 0" and "Core 1". Each core box holds,
from top to bottom:
- one CPU hardware box: "CPU MMU and TLB"
- one kernel instance: "TLB miss handler", "runs on this core"
Under the processor, in very large bold dark blue capitals: "ONE PER CORE".
Under that, in smaller dark blue letters: "its hardware help is the TLB, built into each core".

THE RIGHT DOMAIN FRAME, dark green, named "compression domain". At its top-right corner,
inside, a tag: "PROPOSAL".
Inside it, from top to bottom:
- at the top, one kernel instance drawn a little larger than the others:
  "kernel SW: one manager", "takes every request, owns the tables".
  Under it, in small blue letters: "may dispatch to parallel workers, for throughput, not per core".
- under that, side by side: at the left, the LZ4 HW box: "LZ4 HW", "shared by all cores";
  at the right, touching the LZ4 HW box, one rounded box with a thick dashed dark green
  outline and a light green fill holding: "future HW assists", "one shared set, beside the LZ4 HW",
  "CRC, headers, chunk lists". Under the dashed box, in small blue letters:
  "kernel SW can override everything they write".
- under them, in very large bold dark green capitals: "ONE SHARED SET".
- under that, in smaller dark green letters: "its hardware help sits beside the LZ4 HW, used by every core".

THE GAP between the two frames, level with the cores: one small box with a black outline
and a plain white fill, shaped like a short horizontal queue of three empty slots, labeled
above it: "request queue". Under it, in small blue letters: "a narrow link: requests in, PTE updates and TLB clears back".

Exactly four arrows, none crossing:
- a kernel arrow from the right edge of the processor box to the request queue, label
  "page fault from any core"
- a kernel arrow from the request queue to the manager, label "one at a time"
- a kernel arrow from the manager down to the LZ4 HW box, label "a job"
- a kernel arrow from the manager down to the future HW assists box, label
  "a sub-action, once verified in SW"

The table, under the two frames on the left two thirds. Heading: "Where each one grows".
Three columns. Column headings: "", "CPU MMU domain", "compression domain". Three rows:
- "where the work runs" | "on the core that missed" | "in one manager, for all cores"
- "where hardware help goes" | "inside each core: the TLB" | "one shared set beside the LZ4 HW"
- "how it scales" | "one copy per core" | "more workers and engines, not per core"

The sticky note, on the right third. Heading: "Why not co-design them".
Three lines: "the CPU MMU side grows inside each core",
"the compression side grows in one shared place",
"design them together and a per-core path gets tied to a shared one".

Bottom bar, label "Key point": "Even as pure kernel SW, the compression layer is designed apart from the CPU MMU's kernel SW: its future hardware help is one shared set beside the LZ4 HW, not something inside each core. The two meet only at a narrow interface."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the core
names; draw any person or stick figure; draw a timeline, a clock or a chart; draw the LZ4
HW box or the future HW assists box inside the processor or inside the left frame; put
the request queue inside either frame; draw any arrow between a core and the LZ4 HW box;
draw more than four arrows; let two arrows cross; add a third core box; add a fourth row
or a fourth column to the table; hatch anything; write MMU without CPU in front of it;
write any vendor or product name; rewrite the subtitle or the bottom bar; write any
non-English text.
```

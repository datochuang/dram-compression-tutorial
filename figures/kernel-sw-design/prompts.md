# 圖像生成提示詞：kernel-sw-design

**版本**：第五版，2026-11-15。第四版在 `prompts-v4.md`，圖在 `gen3/`。第五版照第三輪冷讀改了第 9、12 張：第 9 張的 direct reclaim 寫成目前沒有、還沒決定，表格標明是我們的設計；第 12 張的 Key point 只說 HW 不檢查讀寫的位置。以下是第四版的說明：第三版在 `prompts-v3.md`，圖在 `gen2/`。第四版照第二輪冷讀改了第 3、9、12、13 張。以下是第三版的說明：第一版在 `prompts-v1.md`，第二版在 `prompts-v2.md`，圖都在 `gen1/`。第三版照三份冷讀改了第 2、3、4、5、6、8、9、12、13 張：每張加一張 New words 卡片，定義這張第一次用到的詞；第 5 張的 fault path 畫成疊起來的幾張；其他逐張的修改見 `review-gen1-20261115.md`。

**對象**：用 `sketchnote-gen` skill 生成這組圖的人，以及讀圖驗收的 agent。

**讀者**：完全不知道這個主題的工程師。沒碰過 CPU MMU、page swap、壓縮。所以前 4 張先講前提，第 5 到 8 張講 LZ4 kernel SW 的設計，第 9 到 13 張講設計的考量與還沒決定的事。

**負責人的要求**，2026-11-15：「對於LZ4 kernel SW產出一連串的白板工程圖說明其設計概念和各種設計的考量, 必須假設讀者根本不知道這個主題, 所以該有的前提介紹都要做」。負責人選擇 13 張一次做完。

**風格**：`whiteboard`，和 `figures/two-stage-task/`、`figures/system-overview/` 相同。

**內容的來源**：
- 程序與順序：`sim/hostsim/kernel.py`，`spec/control-procedures-v0.md`。
- 數字：`spec/sim-results-v0.md` 的 1.1、1.2、1.8。圖上標明是模擬，通知與指令的時間是假設。
- 平台前提 P1 到 P4：專案的 `CLAUDE.md`。
- 待決定的事：`spec/control-procedures-v0.md` 第 10 節的 D1 到 D15。

**約束**：
- 圖上文字全部英文。永遠寫 CPU MMU，不單寫 MMU。不出現廠商或產品名稱，包括作業系統的名稱。
- 斜線只代表壓縮過的資料。例子的大小故意不整齊。
- 每一步標明是 kernel 還是 HW 做的。user SW 是被服務的一方，四支程式 UI、MEDIA、NET、LOG 各有不同的樣子。
- 數字只有雙引號裡的。沒有定案的事標 OPEN。
- 第 7、8 張是概念層級。逐步的資料結構、bytes 與 cycle 在 `figures/kernel-actions/`。

**怎麼用**：OpenAI 預設模型，high 品質，`--size 1536x1024`。文字清單由雙引號字串自動產生。

## 脊椎

| # | 檔名 | 讀者的問題 | 主張 |
|---|------|------|------|
| 1 | `01-why-compress.png` | 為什麼要壓縮 DRAM？ | DRAM 是固定的。很久沒用的 page 壓起來放，同樣的 DRAM 放得下更多。HRT 的記憶體與 kernel 自己的東西不壓 |
| 2 | `02-pages-and-frames.png` | page、frame、CPU MMU 是什麼？ | user SW 只看到自己的 page。CPU MMU 透過 page table 與 TLB 把 page 對到 frame。這顆晶片 TLB miss 一律進 kernel。page 不在任何 frame 時是 page fault，kernel 接手 |
| 3 | `03-page-swap.png` | page swap 是什麼，我們做的是什麼？ | page swap 把冷的 page 搬出去、碰到時搬回來。一般搬到 disk。我們搬到 DRAM 裡壓縮過的空間，由 LZ4 HW 搬 |
| 4 | `04-how-a-page-is-stored.png` | 壓過的 page 怎麼放？ | 一個例子：page 壓成大小不一的 stream，放進幾個 512 B 的 chunk，COT 記住在哪裡，bitmap 記住哪些 chunk 在用。最多 7 個 chunk。LZ4 HW 只照 job 做，不讀 COT |
| 5 | `05-parts-of-the-kernel-sw.png` | kernel SW 有哪些部分？ | 一組表，一把 mm_lock。fault 路徑在 fault 的 core 上把 page 拿回來。reclaimer thread 在背景壓縮。LZ4 HW 做的時候不握 lock |
| 6 | `06-page-states.png` | 一個 page 會經過哪些 state？ | 六個 state，八種變化。job 進行時 page 屬於那個 job |
| 7 | `07-fault-path.png` | 碰到壓縮過的 page 時發生什麼？ | fault 路徑九步，標 kernel、HW、lock |
| 8 | `08-reclaimer.png` | 冷的 page 怎麼被壓走？ | 水位叫醒 reclaimer，clock 挑 page，RO 直接丟 frame，RW 送 COMPRESS |
| 9 | `09-keeping-faults-short.png` | 怎麼讓 fault 不被壓縮拖慢？ | 預留 free frame，壓縮不在 fault 路徑。模擬數字。和一般 kernel 的 direct reclaim 對照 |
| 10 | `10-where-the-time-goes.png` | 一次解壓縮的時間花在哪？ | 通知與叫醒佔一半，HW 兩成。polling 與 interrupt 的取捨 |
| 11 | `11-many-cores-at-once.png` | 很多 core 同時 fault 會怎樣？ | lock 很短，job 重疊，同一個 page 只做一次，用 tag 找 completion，最慢的是碰到正在 COMPRESS 的 page |
| 12 | `12-where-it-goes-wrong.png` | 哪裡容易出錯？ | 六個陷阱與規則，都是模擬抓到的 |
| 13 | `13-designed-and-open.png` | 什麼已經設計了，什麼還沒？ | 目前設計的五項，待定八項，各自要等什麼。左欄不寫「已決定」：D13 等是我先替負責人選的，還沒確認 |

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
- the user SW figures: small round-headed stick figures, each sitting at a small laptop,
  each with its quoted name in bold right under it. They differ so they can be told
  apart: the one named UI wears a baseball cap, the one named MEDIA wears big headphones,
  the one named NET has a small antenna on its head, the one named LOG holds a pencil.
  Draw only the figures the prompt names.
- a core box: a rounded rectangle with a black outline and a plain white fill. Its quoted
  name is lettered in bold at its top-left corner, inside.
- a CPU hardware box: a rectangle with a light blue fill and a black outline, holding only
  its quoted lines, the first line in bold.
- a kernel box: a rounded rectangle with a dashed purple outline and a plain white fill,
  holding only its quoted lines, the first line in bold.
- a DRAM box: a rectangle with a plain white fill and a black outline. Its quoted name is
  lettered in bold at its top-left corner, inside. It holds only what the prompt lists.
- the LZ4 HW box: a rounded rectangle with a light green fill, a black outline and a small
  gear icon on its top-right corner, holding only its quoted lines, the first line in bold.
- a page tile: one small plain white square with a black outline and a folded top-right
  corner, like a sheet of paper, with its quoted name under it.
- a frame icon: one small plain white square with a black outline, never hatched.
- a chunk icon: one small square with a black outline filled with light diagonal hatching.
- a free chunk icon: one small square with a dotted black outline and a plain white fill.
- a small table: a hand-drawn grid with a bold header row, holding only the quoted cells.
- the padlock: a small black padlock icon, always with its quoted label beside it.
- an access arrow: a solid orange arrow with one arrowhead and a short orange label
  written along it.
- a kernel arrow: a solid purple arrow with one arrowhead and a short purple label
  written along it.
- a hardware arrow: a solid green arrow with one arrowhead and a short green label written
  along it.
- a card: a rounded rectangle with a black outline and a plain white fill, a bold heading
  and the quoted lines under it, one per row.
- a sticky note: a pale yellow sticky note with a bold heading and the quoted lines under
  it, one per row.
- a tag: a small rounded label with a thick black outline, its quoted text in bold capitals.
- Hatching: light diagonal hatching always means compressed data and appears nowhere else.

Color rules: orange for access arrows and the title underline; purple for kernel boxes and
kernel arrows; green for hardware arrows; light blue fill only for CPU hardware boxes;
light green fill only for the LZ4 HW box; pale yellow only for sticky notes; blue for the
subtitle line and small notes; all other lines and text black. No red. No gradients, no
photo textures, no logos, no watermarks.

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

## Prompt 1：01-why-compress

```
Badge: "1"
Title: "Why Compress DRAM"
Subtitle (blue): "The chip has a fixed amount of DRAM. Pages nobody has used for a while can be kept compressed, so the same DRAM holds more."

Along the top, under the subtitle, the four user SW figures in a row: "UI", "MEDIA", "NET",
"LOG". Above them one small blue note: "four programs, each wants its own memory".

Three panels side by side, the same size, under the figures.

Panel one, named "Without compression". Inside: a DRAM box named "DRAM" holding two rows
of four frame icons, every frame icon holding one page tile drawn small. Under the DRAM
box in small blue letters: "every page takes a whole frame, used or not".
Under that, a tag: "FULL".

Panel two, named "Hot and cold". Inside: one row of eight frame icons. Above the first
three, one bracket labeled "hot: used right now". Above the other five, one bracket
labeled "cold: not used for a while". Under the row, in small blue letters, two lines:
"most programs touch only a few of their pages at a time",
"the rest just sit there".

Panel three, named "With compression". Inside: a DRAM box named "DRAM" split by one
vertical dashed line. Left side labeled "frames: hot pages", holding three frame icons.
Right side labeled "compressed space: cold pages", holding three hatched blocks of clearly
different widths side by side, labeled under them "1.3 KB", "2.9 KB", "2.1 KB". Under the
hatched blocks, two dotted empty squares labeled "room for more pages".
Under the DRAM box, in small blue letters: "a cold page touched again is decompressed back into a frame".

Under the three panels, at the right, a sticky note with heading "Never compressed" and two
lines: "memory of hard real-time (HRT) threads: they must never wait",
"the kernel's own code and tables".
At the left of the sticky note, a small blue note: "each page is 4 KB before compression".

Bottom bar, label "Key point": "Compression trades a short wait on the rare touch of a cold page for more room in a fixed DRAM. Hot pages stay as they are."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw a chart,
a bar or percentages; hatch anything except the three blocks in panel three; hatch a frame
icon; add a fourth panel; draw any arrow; draw any figure other than the four user SW
figures; write MMU without CPU in front of it; write any vendor or product name; rewrite
the subtitle or the bottom bar; write any non-English text.
```

## Prompt 2：02-pages-and-frames

```
Badge: "2"
Title: "Pages, Frames and the CPU MMU"
Subtitle (blue): "A program sees only its own pages. The CPU MMU finds the frame in DRAM that holds each page, on every load and store."

Layout: three columns left to right in the upper two thirds, then a strip of three boxes
across the bottom above the bottom bar.

LEFT COLUMN: the user SW figure "MEDIA". Next to it, three page tiles stacked in one
neat column, touching each other: "page A", "page B", "page C". Above the stack, a small
blue note: "what MEDIA sees: its pages, side by side".

MIDDLE COLUMN: one core box named "Core 0" holding, from top to bottom:
- one CPU hardware box: "CPU MMU and TLB"
- one kernel box: "TLB miss handler", "kernel SW, runs on this core"
Under the core box, a small blue note: "every core has its own TLB".

RIGHT COLUMN: one DRAM box named "DRAM" holding, from top to bottom:
- at the top, one row of six frame icons, level with the CPU MMU and TLB box. The second
  is labeled under it "frame 2" and holds a small page tile with no name; the fifth is
  labeled under it "frame 5" and holds a small page tile with no name; the other four are
  empty and unlabeled.
- under the frames, level with the TLB miss handler, a small table labeled above it
  "page table: one PTE per page", with header cells "page", "PTE" and three rows: "A",
  "valid: frame 5"; "B", "valid: frame 2"; "C", "not valid: in no frame".

Exactly six arrows, none crossing:
- an access arrow from page A to the CPU MMU and TLB box, label "MEDIA loads from page A"
- an access arrow straight across from the CPU MMU and TLB box to the frame labeled
  frame 5, passing above the page table, label "TLB hit: straight to frame 5"
- a kernel arrow from the CPU MMU and TLB box down to the TLB miss handler, label "TLB miss"
- a kernel arrow straight across from the TLB miss handler to the page table, label "reads the PTE"
- a kernel arrow from the TLB miss handler back up to the CPU MMU and TLB box, drawn
  beside the TLB miss arrow, label "fills the TLB"
- a kernel arrow from the bottom of the TLB miss handler down to the page fault box in the
  bottom strip, label "PTE not valid"

BOTTOM STRIP, three boxes side by side:
- a card, heading "On this chip", lines: "the CPU MMU never reads the page table by itself",
  "every TLB miss enters the kernel SW, which reads the PTE".
- a kernel box: "page fault", "page C is in no frame: the kernel brings it into one",
  "then MEDIA's load runs again".
- a card, heading "New words on this sheet", lines:
  "page: a 4 KB piece of a program's memory",
  "frame: a 4 KB slot in DRAM that holds one page",
  "PTE: page table entry, says where one page is",
  "TLB: a small cache of PTEs inside each core".

Bottom bar, label "Key point": "Programs see pages; DRAM holds frames. The page table says which frame holds each page, the TLB caches it, and a page in no frame causes a page fault that the kernel must handle."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the core
name; draw more than six arrows; let two arrows cross; let an arrow pass over the page
table; draw a second core; draw any figure other than MEDIA; hatch anything; write MMU
without CPU in front of it; write any vendor or product name; rewrite the subtitle or the
bottom bar; write any non-English text.
```

## Prompt 3：03-page-swap

```
Badge: "3"
Title: "Page Swap, and the Case We Build"
Subtitle (blue): "Page swap keeps hot pages in frames and moves cold pages elsewhere. We move them to compressed space inside DRAM."

Two panels side by side, the same size, in the upper part; under them a strip with two
sticky notes and one card; then the bottom bar. Both panels use the same layout: the user
SW figure at the top-left, a kernel box at the top-right, and one row across the middle
with the frames at the left and the destination at the right.

Panel one, named "Page swap as it is usually done". Inside:
- at the top-left, the user SW figure "NET".
- at the top-right, one kernel box: "kernel SW", "picks cold pages, moves them out and back".
- middle row, left: a DRAM box named "DRAM: frames" holding one row of three frame icons.
- middle row, right: a small cylinder with a thin black outline and a plain white fill,
  labeled "disk: the usual destination".
- an access arrow from NET to the kernel box, label "touches a paged-out page: page fault"
- a kernel arrow, straight and horizontal, from the frames to the disk, label "page out"
- a kernel arrow, straight and horizontal, from the disk to the frames, drawn under the
  first, label "page back in"

Panel two, named "What we build". Inside:
- at the top-left, the user SW figure "NET".
- at the top-right, one kernel box: "kernel SW", "picks cold pages, hands the LZ4 HW a job".
- middle row, left: a DRAM box named "DRAM: frames" holding one row of three frame icons.
- middle row, center: the LZ4 HW box: "LZ4 HW", "compresses and decompresses on request".
- middle row, right: a DRAM box named "DRAM: compressed space" holding four hatched blocks
  of clearly different widths.
- an access arrow from NET to the kernel box, label "touches a compressed page: page fault"
- a kernel arrow from the kernel box straight down to the LZ4 HW box, label "a job"
- four short straight horizontal hardware arrows in two lanes:
  upper lane, left to right: from the frames to the LZ4 HW box, label "page out: COMPRESS";
  then from the LZ4 HW box to the compressed space, no label.
  lower lane, right to left: from the compressed space to the LZ4 HW box, label
  "page back in: DECOMPRESS"; then from the LZ4 HW box to the frames, no label.

Under the two panels, three boxes side by side.
Sticky one, heading "What stays the same", lines: "a page fault when a page is in no frame",
"the kernel chooses which pages are cold",
"the PTE of a page that left says not valid".
Sticky two, heading "What is new", lines: "the destination is DRAM itself",
"the page is stored compressed, at a size nobody knows in advance",
"the LZ4 HW moves the bytes; the kernel decides everything".
A card, heading "New words on this sheet", lines:
"page out: move a page out of its frame",
"page back in: bring it back into a frame",
"LZ4: a fast, simple compression method",
"COMPRESS, DECOMPRESS: the two jobs the LZ4 HW does".

Bottom bar, label "Key point": "Compression is page swap with a different destination: compressed space in the same DRAM, filled and emptied by the LZ4 HW on the kernel's request."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw a disk
in panel two; let any arrow from NET touch the frames, the disk or the compressed space;
hatch anything except the four blocks in panel two; hatch a frame icon; draw any figure
other than the two NET figures; let two arrows cross; add a third panel; write MMU without
CPU in front of it; write any vendor or product name; rewrite the subtitle or the bottom
bar; write any non-English text.
```

## Prompt 4：04-how-a-page-is-stored

```
Badge: "4"
Title: "How a Compressed Page Is Stored"
Subtitle (blue): "A 4 KB page shrinks to a size nobody can predict. The kernel stores it in fixed 512 B chunks and writes down where they are."

Layout: three page tiles across the top, the chunk pool across the middle, two tables
under it at the left and the LZ4 HW box at the right, then a strip of a sticky note and a
card, then the bottom bar.

TOP ROW, three page tiles side by side, each with a line under it:
- "page P", then "4 KB, compresses to 1.3 KB: 3 chunks"
- "page Q", then "4 KB, compresses to 2.9 KB: 6 chunks"
- "page R", then "4 KB, compresses to 3.9 KB: would need 8 chunks"
Under page R, a tag "OPEN" and a small blue note: "today it stays in its frame".

MIDDLE: one long DRAM box named "chunk pool, in DRAM" holding one row of sixteen small
squares, each with its number under it, from "1" to "16" in order. Squares one, two and
seven are chunk icons with a small letter P on them; squares three to six, nine and ten
are chunk icons with a small letter Q on them; all other squares are free chunk icons.
Square seven and square ten are hatched only in their left half, the right half plain
white. Under the row, in small blue letters:
"each chunk is 512 B; the last chunk of a page is only partly used".
From page P, one hardware arrow labeled "COMPRESS" goes down and splits into three
branches that end at squares one, two and seven.

UNDER THE CHUNK POOL, at the left, two small tables side by side.
Left table, labeled above it "COT (compressed object table): one entry per page, in DRAM",
header cells "page", "chunks", "length", "check"; two rows: "P", "1, 2, 7", "1.3 KB",
"CRC"; "Q", "3, 4, 5, 6, 9, 10", "2.9 KB", "CRC".
Right table, labeled above it "chunk bitmap: one bit per chunk", one header row
"chunk", "in use", and two rows: "1", "yes"; "8", "no".

UNDER THE CHUNK POOL, at the right: the LZ4 HW box: "LZ4 HW",
"COMPRESS: one frame into the chunks it is given",
"DECOMPRESS: the given chunks into one frame". Under it in small blue letters:
"the kernel picks the chunks and writes the COT; the HW never reads the COT".

BOTTOM STRIP, two boxes side by side.
A sticky note with heading "Rules of the pool" and lines:
"a page uses at most 7 chunks: 8 would be the whole 4 KB, nothing saved",
"its chunks need not be next to each other",
"read-only pages (code, constants) never change: their chunks always stay",
"a read-write page (data) gives its chunks back when it returns to a frame".
A card with heading "New words on this sheet" and lines:
"stream: the compressed bytes of one page",
"CRC: a checksum that catches a damaged stream",
"OPEN: not decided yet".

Bottom bar, label "Key point": "Every compressed page is a stream of uneven length, spread over a few 512 B chunks. The COT says where each page's stream is; the bitmap says which chunks are free."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw the
sixteen squares in a different count; hatch a free chunk icon or a page tile; draw any
figure; draw any arrow other than the one COMPRESS arrow and its three branches; write MMU
without CPU in front of it; write any vendor or product name; rewrite the subtitle or the
bottom bar; write any non-English text.
```

## Prompt 5：05-parts-of-the-kernel-sw

```
Badge: "5"
Title: "The Parts of the LZ4 Kernel SW"
Subtitle (blue): "One set of tables under one lock, two paths that use them, and the LZ4 HW that does the heavy lifting."

Layout: user SW figures across the top, three columns in the middle, the LZ4 HW box across
the bottom, then the bottom bar.

TOP: the user SW figures "UI" and "MEDIA" at the top-left, side by side. Under MEDIA, a
small blue note: "most accesses never reach the kernel: the TLB hits".

LEFT COLUMN: a stack of three kernel boxes of the same size, overlapping like a fanned
deck, each offset a little down and to the right of the one behind it. Only the front box
has text: "fault path", "brings a compressed page back", "runs on the core that faulted",
"called from the TLB miss handler", "many cores can be in it at once". The two boxes
behind it are empty.

MIDDLE COLUMN: one DRAM box named "kernel tables" holding four small rounded tiles of the
same size, two by two: "page state", "COT", "free frames", "chunk bitmap". At its top
edge, the padlock with the label "mm_lock: one lock guards all four".
Under the box, in small blue letters: "the lock is held for short steps only".

RIGHT COLUMN: one kernel box, large: "reclaimer", "pushes cold pages out",
"a kernel thread in the background", "wakes when free frames run low",
"does all the compressing".

BOTTOM: the LZ4 HW box, wide, centered: "LZ4 HW", "several engines, shared by every core".
Under it, in small blue letters: "no lock is held while the LZ4 HW works".

Exactly six arrows, none crossing:
- an access arrow from UI to the fault path, label "touches a compressed page"
- a kernel arrow from the fault path to the kernel tables, label "lock, look up, unlock"
- a kernel arrow from the reclaimer to the kernel tables, label "lock, pick a page, unlock"
- a hardware arrow from the fault path down to the LZ4 HW box, label "DECOMPRESS"
- a hardware arrow from the reclaimer down to the LZ4 HW box, label "COMPRESS"
- a kernel arrow from the fault path to the reclaimer, drawn above the kernel tables and
  curving over them, label "wake up: free frames are low"

Bottom bar, label "Key point": "Bringing pages back happens on the core that faulted; pushing pages out happens in one background thread. Both share one set of tables under one lock, and neither holds the lock while the LZ4 HW works."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw a queue,
an inbox or a waiting line; draw more than six arrows; let two arrows cross; draw any
figure other than UI and MEDIA; hatch anything; write the words manager or instance;
write MMU without CPU in front of it; write any vendor or product name; rewrite the
subtitle or the bottom bar; write any non-English text.
```

## Prompt 6：06-page-states

```
Badge: "6"
Title: "The Six States of a Page"
Subtitle (blue): "The kernel keeps one state per page. It tells where the data is, and whether a job is working on it."

Layout: six state boxes in two rows of three, arrows between them, a strip of three cards
under them, then the bottom bar.

Each state box is a rounded rectangle with a thick black outline and a plain white fill,
holding a bold name in capitals and one line under it.

TOP ROW, left to right:
- "UNTOUCHED", "read-write page nobody has written yet"
- "PRESENT", "in a frame: programs use it directly"
- "COMPRESSING", "the LZ4 HW is compressing it"
BOTTOM ROW, left to right:
- "LOST", "no good copy left anywhere"
- "DECOMPRESSING", "the LZ4 HW is bringing it back"
- "COMPRESSED", "only in the chunk pool"
The COMPRESSED box has light diagonal hatching inside, behind its text. No other box is
hatched.

Two start markers, each a small solid black dot with a short black arrow:
- one at the far left of UNTOUCHED, pointing into it, label "read-write pages start here"
- one at the far right of COMPRESSED, pointing into it, label "read-only pages start here: compressed before boot"

Exactly eight kernel arrows, each with its label:
- UNTOUCHED to PRESENT: "first touch: a frame of zeros, no job"
- PRESENT to COMPRESSING: "reclaimer, read-write page"
- COMPRESSING to COMPRESSED: "stored: the frame is freed"
- COMPRESSING back to PRESENT, drawn under the previous arrow: "needs more than 7 chunks, or the HW failed"
- PRESENT down to COMPRESSED, a long diagonal: "reclaimer, read-only page: just drop the frame"
- COMPRESSED to DECOMPRESSING: "page fault"
- DECOMPRESSING up to PRESENT: "back in a frame; a read-write page frees its chunks"
- DECOMPRESSING to LOST: "the HW and the kernel's own decoder both fail"

STRIP under the boxes: three cards side by side.
Card one, heading "Read-only pages (code, constants)", lines:
"they never change, so their compressed copy always stays",
"leaving a frame needs no job".
Card two, heading "While a job runs", lines:
"the page belongs to that job",
"another thread that touches it sleeps until the job ends",
"no second job is started for the same page".
Card three, heading "New words on this sheet", lines:
"job: one request to the LZ4 HW for one page",
"the kernel's own decoder: software that decompresses when the HW gives a wrong answer".

Bottom bar, label "Key point": "Every page is in exactly one of six states. Read-only pages always keep their compressed copy, even while in a frame; a read-write page has exactly one copy, in a frame or in the chunk pool."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; add a seventh
state box; draw more than eight kernel arrows and two start markers; let two arrows cross;
hatch any box except COMPRESSED; draw any figure; write MMU without CPU in front of it;
write any vendor or product name; rewrite the subtitle or the bottom bar; write any
non-English text.
```

## Prompt 7：07-fault-path

```
Badge: "7"
Title: "Bringing a Page Back: the Fault Path"
Subtitle (blue): "LOG touches page Q, which is compressed. Everything below runs on LOG's own core, and other cores can do the same at the same time."

Layout: three horizontal lanes across the full width, separated by thin horizontal lines,
each lane name in bold at its left edge: top lane "user SW", middle lane
"kernel SW, on LOG's core", bottom lane "LZ4 HW". Nine numbered step boxes run left to
right along the lanes, in time order. Each step box is a small rounded rectangle with a
black outline and a small round number badge at its top-left.

Top lane: at its left edge, the user SW figure "LOG".

Steps, each in the lane named:
- step "1", user SW lane: "LOG loads from page Q"
- step "2", kernel lane: "TLB miss handler: Q's PTE is not valid"
- step "3", kernel lane, with the padlock labeled "mm_lock": "take a frame from the free frames, read Q's COT entry, mark Q DECOMPRESSING"
- step "4", LZ4 HW lane, drawn as the LZ4 HW box: "DECOMPRESS", "Q's chunks into the frame"
- step "5", kernel lane, a long dotted bar drawn above step four: "wait for the completion: sleep, or poll"
- step "6", kernel lane: "drop the frame's old lines from every core's cache"
- step "7", kernel lane, with the padlock labeled "mm_lock": "free Q's chunks, mark Q PRESENT, set Q's PTE valid"
- step "8", kernel lane: "fill the TLB, return from the exception"
- step "9", user SW lane: "LOG's load runs again and gets its data"

Arrows: thin black arrows join step 1 to 2, 2 to 3, 3 to 4, 4 to 6, 6 to 7, 7 to 8, 8 to 9,
in that order, with no labels. No other arrows.

Under the lanes, two sticky notes side by side.
Sticky one, heading "Why it stays short", lines:
"the frame comes from a reserve: no compressing here",
"mm_lock is held only in steps three and seven",
"while the LZ4 HW works, other cores can take the lock".
Sticky two, heading "For more detail", lines:
"each step's tables, bytes and costs: figures/kernel-actions",
"a read-only page keeps its chunks in step seven".

Bottom bar, label "Key point": "A fault takes a reserved frame, hands one DECOMPRESS job to the LZ4 HW, and holds the lock only for two short steps. The program's instruction then simply runs again."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw more than
nine step boxes; draw the padlock on any step other than three and seven; draw more than
seven arrows; hatch anything; draw any figure other than LOG; write MMU without CPU in
front of it; write any vendor or product name; rewrite the subtitle or the bottom bar;
write any non-English text.
```

## Prompt 8：08-reclaimer

```
Badge: "8"
Title: "Pushing a Cold Page Out: the Reclaimer"
Subtitle (blue): "A background kernel thread keeps a reserve of free frames. It wakes when the reserve runs low and refills it."

Layout: three panels side by side, the same size, in the upper three quarters; one card
across the full width under them; then the bottom bar.

Panel one, named "When it wakes". Inside:
- at the top, one kernel box: "reclaimer", "one kernel thread, asleep most of the time".
- under it, one tall narrow upright rectangle like a thermometer, labeled above it
  "free frames", filled with light gray from the bottom up to about one third of its
  height. Two horizontal marks across it, each with a label at its right: near the top,
  "high watermark: stop here"; at about one quarter of the height, "low watermark: wake the reclaimer".
- at the left of the rectangle, one short black arrow pointing down, label "faults take frames";
  at the right side, under the labels, one short black arrow pointing up, label "the reclaimer frees frames".

Panel two, named "Which page: the clock". Inside: eight frame icons arranged in a circle,
with one clock hand from the center pointing at one of them. Under the circle, a card with
heading "At each frame the hand passes" and lines:
"used since the last pass? clear its used mark, skip it",
"not used? pick this page",
"just faulted in, or pinned? always skip".
Under the card, a tag "OPEN" and a small blue note:
"the CPU MMU sets no used mark here: who sets it is not designed yet".

Panel three, named "Push it out". Inside, two columns of black-outlined rounded step
boxes, each column joined top to bottom by short thin black arrows.
Left column heading "read-only page", two boxes:
- with the padlock labeled "mm_lock": "set its PTE not valid, clear every core's TLB"
- with the padlock labeled "mm_lock": "free the frame, mark COMPRESSED: no job"
Right column heading "read-write page", four boxes:
- with the padlock labeled "mm_lock": "reserve 7 free chunks, set its PTE not valid, clear every core's TLB, mark COMPRESSING"
- "write the frame's cached lines back to DRAM"
- the LZ4 HW box: "COMPRESS", "frame into the chunks"
- with the padlock labeled "mm_lock": "write the COT entry, give back unused chunks, free the frame, mark COMPRESSED"
Under the right column, small blue letters: "needs more than 7 chunks, or the HW failed: mark PRESENT, keep the frame".

CARD across the full width, heading "New words on this sheet", four lines in two columns:
"watermark: a level that starts or stops an action",
"used mark: a flag saying the page was touched lately",
"pinned: held in its frame on purpose by the kernel",
"cached lines: bytes the CPU wrote that may still sit only in its cache".

Bottom bar, label "Key point": "The reclaimer, not the fault, does all the compressing. It picks pages that were not used lately, and never the page a thread has just faulted in."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw any
figure; hatch anything; draw arrows other than the two short arrows in panel one and the
short arrows joining the step boxes; write the Key point in blue; write MMU without CPU in
front of it; write any vendor or product name; rewrite the subtitle or the bottom bar;
write any non-English text.
```

## Prompt 9：09-keeping-faults-short

```
Badge: "9"
Title: "Design Choice: Keep Compression Off the Fault"
Subtitle (blue): "A fault should only decompress. Keeping a reserve of free frames and a background compressor makes that true, until the load gets too heavy."

Layout: two panels in the upper part, side by side, the same size; a table panel across
the lower part; then the bottom bar.

Panel one, named "A common general-purpose kernel". Inside, two kernel boxes stacked:
- "background reclaim thread", "frees memory up to a watermark"
- "direct reclaim", "when it falls behind, the thread that needs memory compresses pages itself"
Under them a small blue note: "fast on average; the worst case is long: that fault may have to compress several pages first".

Panel two, named "Ours". Inside, stacked:
- one kernel box: "reclaimer thread", "frees frames up to the high watermark"
- one plain rounded box with a thin dotted black outline: "today: no direct reclaim",
  "when the reclaimer falls behind, the fault sleeps until a frame is free"
A tag "OPEN" on the top edge of the dotted box, with a small blue note beside it:
"keep it this way, or add direct reclaim?"
Under them a small blue note: "today a fault never compresses; its worst case depends on how fast the reclaimer frees frames".

Lower panel, named "Ours, simulated: the four programs at five loads". Inside, a small table
with header cells "load", "faults that waited for a frame, in one run", "fault time, slowest in a hundred",
"fault time, slowest of all", "most-stalled program: share of time waiting";
rows:
"normal", "0", "6.98 µs", "11.50 µs", "1.9%";
"4 times", "0", "7.81 µs", "12.05 µs", "7.2%";
"10 times", "10", "8.24 µs", "14.94 µs", "16.4%";
"20 times", "178", "15.15 µs", "22.23 µs", "29.3%";
"40 times", "716", "20.42 µs", "25.69 µs", "49.3%".
Under the table, small blue letters, two lines:
"load: normal means each program works 20 µs on its own between two memory accesses; 4 times means 5 µs, and so on",
"small simulated machine; the LZ4 HW has four engines, units that each run one job; the reclaimer keeps two COMPRESS jobs running".
At the right of the table, a card with heading "Two knobs" and lines:
"how high the watermarks are",
"how many COMPRESS jobs the reclaimer keeps running".

Bottom bar, label "Key point": "With a reserve of free frames and all compression in the background, a fault at normal load never waits for a frame. Under heavy load it does, and how to bound that wait is still open."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw a chart
or bars; draw any arrow; draw any figure; draw any stray dot or mark; hatch anything; write
any operating system, vendor or product name; write MMU without CPU in front of it;
rewrite the subtitle or the bottom bar; write any non-English text.
```

## Prompt 10：10-where-the-time-goes

```
Badge: "10"
Title: "Design Choice: How to Wait for the LZ4 HW"
Subtitle (blue): "In a decompress fault, the LZ4 HW is the short part. Telling the kernel it is done takes longer."

Layout: one wide panel across the upper half, two panels side by side in the lower half,
then the bottom bar.

Upper panel, named "One decompress fault, simulated: about 6.20 µs". Inside: one long
horizontal bar drawn as three boxes joined end to end, their widths in the ratio of about
five to two to two:
- first box, white fill: "notify and wake up: 3.32 µs"
- second box, white fill with a dashed purple outline: "kernel instructions: 1.45 µs"
- third box, light green fill: "LZ4 HW: 1.27 µs"
Under the first box, a small blue note: "interrupt and wake-up times are assumed".
Under the second box, a small blue note: "instruction counts are assumed".
At the right end of the bar, a small blue note: "locks and the job ring: under 0.2 µs".

Lower left panel, named "Sleep until the interrupt". Inside, three lines:
"the core runs other work meanwhile",
"median fault: 6.20 µs",
"kernel CPU time: 1.29%".

Lower right panel, named "Poll the completion". Inside, three lines:
"the core spins until the job is done",
"median fault: 3.23 µs",
"kernel CPU time: 2.27%".
A tag "OPEN" on the line between the two lower panels, with a small blue note under it:
"which one, or poll briefly then sleep".

Bottom bar, label "Key point": "Waking a sleeping thread costs more than the decompression itself. Polling halves a typical fault but spends more CPU; the choice is still open and needs real interrupt times."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw any
other bar, chart or axis; draw any arrow; draw any figure; hatch anything; write MMU
without CPU in front of it; write any vendor or product name; rewrite the subtitle or the
bottom bar; write any non-English text.
```

## Prompt 11：11-many-cores-at-once

```
Badge: "11"
Title: "Many Cores Fault at Once"
Subtitle (blue): "Three programs on three cores fault at nearly the same moment. Two want page P, one wants page Q."

Layout: a timeline across the upper two thirds with four lanes, a strip of three cards
under it, then the bottom bar. Time runs left to right; one arrow under the lanes is
labeled "time".

Lanes, each with its name in bold at its left edge, separated by thin horizontal lines:
- lane "Core 0: UI", with the user SW figure UI drawn small at its left
- lane "Core 1: MEDIA", with the user SW figure MEDIA drawn small at its left
- lane "Core 2: NET", with the user SW figure NET drawn small at its left
- lane "LZ4 HW engines", with the LZ4 HW box drawn small at its left: "LZ4 HW"

Positions: to the right of the lane names, divide the width into twelve equal invisible
columns, numbered from left to right. Every box below sits exactly in the columns given.
The lock boxes are narrow, one column wide each, and no two lock boxes share a column, so
the lock is never held by two cores at the same time.

Lane Core 0: a lock box with the padlock labeled "lock" in column one; a long dotted bar
labeled "waits for job P" in columns two to eight; a lock box with the padlock labeled
"lock" in column nine; a box "UI runs again" in columns ten and eleven.
Lane Core 1: a lock box with the padlock labeled "lock" in column two; a dotted bar labeled
"waits for job Q" in columns three to six; a lock box with the padlock labeled "lock" in
column seven; a box "MEDIA runs again" in columns eight and nine.
Lane Core 2: a lock box with the padlock labeled "lock" in column three; a long dotted bar
in columns four to nine holding two lines: "P is already DECOMPRESSING",
"waits on page P, no second job"; a lock box with the padlock labeled "lock" in column
ten; a box "NET runs again" in columns eleven and twelve.
Lane LZ4 HW engines: two light green bars on two rows: "engine: job P" in columns two to
eight; "engine: job Q" in columns three to six.

Under the timeline, three cards side by side.
Card one, heading "The lock is short", lines: "taken only to read and change tables",
"never held while an engine works".
Card two, heading "Completions in any order", lines: "job Q finished first",
"each thread finds its own completion by its tag".
Card three, heading "The slowest case seen", lines:
"a fault on a page that is being compressed",
"it waits for that COMPRESS; more engines do not help",
"rare in simulation; two fixes are still open".
A tag "OPEN" at the top-right corner of card three.

Bottom bar, label "Key point": "Faults on different pages run side by side and share the LZ4 HW's engines. Faults on the same page share one job. Only the short table updates take turns."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the core
names; draw a fourth core lane; draw more than two engine bars; draw any arrow except the
one time arrow; hatch anything; draw any figure other than UI, MEDIA and NET; write MMU
without CPU in front of it; write any vendor or product name; rewrite the subtitle or the
bottom bar; write any non-English text.
```

## Prompt 12：12-where-it-goes-wrong

```
Badge: "12"
Title: "Where It Goes Wrong If You Are Careless"
Subtitle (blue): "Each of these was found or confirmed in the simulations. Each rule is cheap; skipping one breaks data in ways tests rarely show."

Layout: six cards in two rows of three, all the same size, then the bottom bar. Each card
has, at its top-left, one small simple black line icon described below, then a bold
heading beside the icon, one line starting with "Risk:" and one line starting with "Rule:".
Under each card's rule, in small blue letters, one line starting with "who:".

Row one:
- icon: two small stacked rectangles, the top one labeled "cache", the bottom one labeled "DRAM".
  Heading "Stale cache lines".
  "Risk: the LZ4 HW reads and writes DRAM directly; the CPU may hold newer or older copies in its cache",
  "Rule: write the frame back to DRAM before COMPRESS; after DECOMPRESS, drop the cache's old copy so the CPU reads what the HW wrote".
  Who: "who: the kernel".
- icon: a small grid of four squares with one square crossed out.
  Heading "A TLB that still points at the frame".
  "Risk: a core keeps using a frame that now holds another page",
  "Rule: clear the page from every core's TLB before the frame is reused".
  Who: "who: the kernel".
- icon: a small page tile with a short arrow leaving it.
  Heading "A page pushed out too soon".
  "Risk: the reclaimer picks a page that was just brought back, before the instruction that needed it has run, so it faults again and again",
  "Rule: the reclaimer skips each thread's last faulted-in pages".
  Who: "who: the kernel".
Row two:
- icon: a small clock with a line through it.
  Heading "A fault where nobody may wait".
  "Risk: code that must not sleep (interrupt handlers, code holding a lock, hard real-time threads) touches a compressed page",
  "Rule: such code never touches one: pin the page in its frame, or keep that memory out of compression".
  Who: "who: the kernel, and whoever writes that code".
- icon: a small gear with a question mark beside it.
  Heading "A wrong answer from the LZ4 HW".
  "Risk: the HW reports a good stream (the compressed bytes) as broken, or never answers, and the page would be thrown away",
  "Rule: when the HW fails, decode the stream again with the kernel's own decoder; after three wrong answers in a row, or one missing answer, stop using the HW".
  Who: "who: the kernel".
- icon: two small arrows pointing at the same small square.
  Heading "Two jobs on one frame".
  "Risk: two of the LZ4 HW's engines write the same frame or chunk at once",
  "Rule: frames and chunks are handed out under mm_lock; the HW does not check".
  Who: "who: the kernel".

Bottom bar, label "Key point": "The LZ4 HW does not check where it reads and writes. The kernel keeps caches and TLBs from holding stale copies, protects pages that just came back, hands each frame to one job at a time, and double-checks the HW's failures; code that must not wait stays away from compressed memory."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; add a seventh
card; draw any arrow other than the small icons; draw any figure; hatch anything; fill the
Key point label box with a color; write MMU without CPU in front of it; write any vendor
or product name; rewrite the subtitle or the bottom bar; write any non-English text.
```

## Prompt 13：13-designed-and-open

```
Badge: "13"
Title: "What Is Designed, What Is Open"
Subtitle (blue): "The design so far, and the questions that still need a decision, the CPU manual, or real measurements."

Layout: a narrow panel at the left, about one third of the width; a wide panel at the
right, about two thirds of the width; then the bottom bar.

Left panel, named "In the current design". Inside, five lines, each starting with a small check mark:
"a reserve of free frames with two watermarks",
"all compressing in one background thread",
"decompressing on the core that faulted, several at once",
"one lock, never held while the LZ4 HW works",
"the kernel's own decoder as a backup".
Under the lines, a small blue note: "built and checked in simulation; not yet signed off".

Right panel, named "Open". Inside, a small table with header cells "question",
"why it matters", "needs"; nine rows:
"a page that needs more than 7 chunks", "today it keeps its frame forever", "a design decision";
"frames and chunks both full", "which program gets the error", "a product decision";
"how to pick cold pages", "wrong picks mean more jobs", "real access traces";
"who sets the used mark", "the clock needs it; with no hardware page table walk, likely only the kernel can", "the CPU manual";
"sleep or poll for the LZ4 HW", "time against CPU", "real interrupt times";
"direct reclaim or not", "the worst-case fault", "a design decision";
"a fault on a page being compressed", "the slowest faults seen", "a design decision";
"where the reclaimer runs, at what priority", "it must not disturb hard real-time threads", "a design decision";
"after the kernel stops using a faulty LZ4 HW", "read-write pages can no longer be compressed", "a product decision".
Under the table, a small blue note: "design decision: by the kernel team; product decision: how the product should behave".

Bottom bar, label "Key point": "The structure is built and checked in simulation but not yet signed off. What is open is mostly policy: what to do when memory runs out, which pages to pick, and how long a fault may take."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; add or drop
a row; draw any arrow; draw any figure; hatch anything; write MMU without CPU in front of
it; write any vendor or product name; rewrite the subtitle or the bottom bar; write any
non-English text.
```


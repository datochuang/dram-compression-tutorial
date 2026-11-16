# 圖像生成提示詞：cpu-mmu-kernel-sw

**版本**：第四版，2026-11-16。第四版只改第 12 張：表格只剩三欄，每種做法的條件寫進說明；加一行說明 way 2 不等 lock、way 4 要開著 interrupt 等 lock。以下是第三版的說明：第一版逐張組好的提示詞在 `gen1/` 每張圖旁的 `.prompt.txt`，第二版的在 `gen2/`。第二版照第一輪冷讀改了第 4、5、8、11、12、13、14 張。第三版照第二輪冷讀改寫第 12 張：表格只放 TLB miss handler 的四種做法，deadlock 另外一格，說明它和選哪種做法無關。見 `review-gen1-to-gen4-20261116.md`。

**對象**：用 `sketchnote-gen` skill 生成這組圖的人，以及讀圖驗收的 agent。

**讀者**：完全不知道這個主題的工程師。沒碰過 CPU MMU、page table、TLB。所以前 4 張先講前提，第 5 到 10 張講 CPU MMU kernel SW 的各個部分，第 11 到 14 張講多個 core 時的考量、容易出錯的地方與還沒決定的事。

**負責人的要求**，2026-11-16：「接下來幫CPU kernel SW也做一個一樣的文件」。「一樣的文件」指 `figures/kernel-sw-design/` 那一組：一連串白板工程圖，說明設計概念與設計的考量，假設讀者完全不知道這個主題，前提都要介紹。

**風格**：`whiteboard`，和 `figures/kernel-sw-design/` 相同，兩組可以接著讀。

**內容的來源**：
- 平台前提 P1 到 P4、推論、還不知道的事：專案的 `CLAUDE.md`。
- 概念與說法：`README.md` 的第 1 到 7 層，`figures/cpu-mmu-basics/` 的 A 到 C。
- page fault 的處理：`sim/hostsim/kernel.py` 的 `page_fault` 與 `first_touch`。
- refill 與清 TLB 的 race：`sim/hostsim/conc.py` 的 `SplitTlb`，`sim/hostsim/tlbsplit.py`，`sim/tests/test_hostsim_tlbsplit.py`。2026-11-16 跑了 `tlbsplit --quick`，輸出存在 `tlbsplit-quick-20261116.txt`。清 TLB 的方式是模型裡的一個例子，不是平台的機制。

**CPU MMU kernel SW 大部分還沒有設計。** 圖上分三種寫法：
- 模型裡跑過的：寫 `in the model`。
- 一般的做法：寫 `a common way`，不寫廠商或 CPU 名稱。
- 還沒決定或要看 CPU 手冊的：標 OPEN。

**約束**：
- 圖上文字全部英文。永遠寫 CPU MMU，不單寫 MMU。不出現廠商、CPU、作業系統的名稱。
- 斜線只代表壓縮過的資料。這組圖沒有壓縮過的資料，所以不畫斜線。
- 每一步標明是 kernel、CPU 硬體還是 user SW 做的。user SW 是被服務的一方，四支程式 UI、MEDIA、NET、LOG 各有不同的樣子。
- 數字只有雙引號裡的。沒有量過的時間一律不寫數字。
- 不把 kernel SW 畫成只有一份在跑：handler 畫成疊起來的幾張。
- 每張有一張「New words on this sheet」卡片。

**怎麼用**：OpenAI 預設模型，high 品質，`--size 1536x1024`。文字清單由雙引號字串自動產生。

## 脊椎

| # | 檔名 | 讀者的問題 | 主張 |
|---|------|------|------|
| 1 | `01-why-translate.png` | address 為什麼要轉換？ | 程式用 logical address，DRAM 用 physical address。轉換只回答一個問題：這個 page 現在在哪個 frame。kernel 因此可以搬 page，程式不用改 |
| 2 | `02-page-table-tlb-cpu-mmu.png` | 誰記著對應，誰在查？ | page table 在 DRAM，完整；TLB 在每個 core，很小；CPU MMU 只查 TLB。這顆晶片的 CPU MMU 從不讀 page table，TLB 由 kernel 填 |
| 3 | `03-three-outcomes.png` | 一次 access 會發生什麼？ | 三種結果：TLB hit 只有硬體；TLB miss 而 PTE valid，kernel 填 TLB；PTE invalid 是 page fault，kernel 先給 page 一個 frame。每次 page fault 都先是 TLB miss |
| 4 | `04-the-processor.png` | 有很多 core 與 thread 時，哪些是各自的，哪些是共用的？ | 每個 core 一個 CPU MMU、一個 TLB、一個 L1，TLB 由該 core 的 thread 共用；L2、DRAM、page table 共用。kernel 的程式只有一份，好幾個 thread 可以同時在跑 |
| 5 | `05-parts-of-the-cpu-mmu-kernel-sw.png` | CPU MMU kernel SW 有哪些部分？ | 兩個入口：TLB miss handler 與 page fault handler，都在發生的那個 thread 上跑。幾個服務：改對應、清每個 core 的 TLB、frame allocator、切換程式。共用的表在 mm_lock 下。壓縮層從 page fault handler 接進來 |
| 6 | `06-the-pte-is-ours.png` | PTE 長什麼樣子，誰決定？ | TLB entry 的格式由 CPU 決定，要看手冊。PTE 的格式由 kernel 決定，因為只有 kernel 讀。page table 的形狀是 refill 速度與記憶體的取捨，OPEN |
| 7 | `07-tlb-miss-handler.png` | TLB miss 時 kernel 做什麼？ | 八步。很常跑，所以要短，不能 sleep，自己不能再 TLB miss。要不要拿 lock 還沒決定。page 有沒有被用過只有這裡看得到 |
| 8 | `08-page-fault-handler.png` | page fault 時 kernel 做什麼？ | 拿 lock 再查一次，然後分原因：第一次碰、壓縮過、不允許、不屬於任何東西。page swap 是其中一種原因。這裡可以 sleep |
| 9 | `09-changing-a-mapping.png` | kernel 改 PTE 時要注意什麼？ | 給 frame 不用清別人的 TLB。拿走 frame 或減少權限要先改 PTE、清每個 core 的 TLB，再動 frame。怎麼清別的 core 的 TLB 要看 CPU |
| 10 | `10-many-programs.png` | 有好幾支程式時，TLB 怎麼分？ | 如果每支程式有自己的 page table，切換程式時 TLB 裡是舊程式的對應：清掉，或每筆加上 address space tag。同一個 core 的兩個 thread 共用 TLB，同時跑不同程式就一定要分得出來 |
| 11 | `11-refill-against-clear.png` | 不拿 lock 的 TLB miss handler 會出什麼事？ | 模型找到的交錯：handler 讀到舊的 PTE，別人改 PTE、清完 TLB，handler 才把舊的對應寫進 TLB |
| 12 | `12-what-held-in-the-model.png` | 怎麼避免？ | 模型裡沒出錯的兩種做法，以及一定 deadlock 的一種。清 TLB 的方式是例子 |
| 13 | `13-where-it-goes-wrong.png` | 哪裡容易出錯？ | 六個陷阱與規則 |
| 14 | `14-modeled-and-open.png` | 什麼已經在模型裡，什麼還沒？ | 模型裡的四項，待定九項，大多要等 CPU 手冊 |

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
- a thread slot: a small rounded rectangle with a thin black outline inside a core box,
  holding only its quoted label.
- a CPU hardware box: a rectangle with a light blue fill and a black outline, holding only
  its quoted lines, the first line in bold.
- a kernel box: a rounded rectangle with a dashed purple outline and a plain white fill,
  holding only its quoted lines, the first line in bold.
- a DRAM box: a rectangle with a plain white fill and a black outline. Its quoted name is
  lettered in bold at its top-left corner, inside. It holds only what the prompt lists.
- a page tile: one small plain white square with a black outline and a folded top-right
  corner, like a sheet of paper, with its quoted name under it.
- a frame icon: one small plain white square with a black outline.
- a small table: a hand-drawn grid with a bold header row, holding only the quoted cells.
- the padlock: a small black padlock icon, always with its quoted label beside it.
- a step box: a small rounded rectangle with a black outline and a small round number
  badge at its top-left, holding only its quoted line.
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
- No hatching anywhere on this sheet.

Color rules: orange for access arrows and the title underline; purple for kernel boxes and
kernel arrows; green for hardware arrows; light blue fill only for CPU hardware boxes;
pale yellow only for sticky notes; blue for the subtitle line and small notes; all other
lines and text black. No red. No gradients, no photo textures, no logos, no watermarks.

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

## Prompt 1：01-why-translate

```
Badge: "1"
Title: "Why an Address Is Translated"
Subtitle (blue): "A program uses its own addresses. DRAM has its own. On every load and store, one is turned into the other."

Layout: three columns of equal height in the upper part, a strip of two cards under them,
then the bottom bar. The left column is what the program sees. The middle column is the
translation. The right column is DRAM.

LEFT COLUMN. A bold heading at its top: "What MEDIA sees". Under it, in small blue letters:
"logical addresses". The user SW figure "MEDIA" sits at the left of one strip of five
cells stacked top to bottom. The third cell has a thick black outline and holds the label
"page 0x416". Inside that same cell, near its lower edge, one small black dot with the
label "offset 0xC80" beside it. The other four cells are empty.

RIGHT COLUMN. A bold heading at its top: "DRAM". Under it, in small blue letters:
"physical addresses". One strip of five cells, the same size as the left strip. The second
cell has a thick black outline and holds the label "frame at 0x80024000". Inside that same
cell, near its lower edge, one small black dot with the label "offset 0xC80" beside it.
The other four cells are empty.

MIDDLE COLUMN, from top to bottom:
- one CPU hardware box: "translation", "which frame holds this page right now?"
- a small card, heading "The arithmetic", lines:
  "0x00416C80 is page 0x416, offset 0xC80",
  "page 0x416 is in the frame at 0x80024000",
  "0x80024000 + 0xC80 = 0x80024C80".
- one kernel box: "kernel SW", "decides which frame holds each page".

Exactly four arrows, none crossing:
- an access arrow from MEDIA to the thick-outlined cell of the left strip, label "MEDIA reads 0x00416C80"
- an access arrow from the thick-outlined cell of the left strip to the translation box, label "page 0x416"
- an access arrow from the translation box to the thick-outlined cell of the right strip,
  label "its frame". Its arrowhead touches that cell and no other.
- a kernel arrow from the kernel box up to the translation box, label "keeps the answer up to date"

STRIP under the columns, two cards side by side.
Card one, heading "What this buys", lines:
"MEDIA never needs to know where its data is",
"the kernel can move a page to another frame",
"the kernel can even take the frame away for a while".
Card two, heading "New words on this sheet", lines:
"page: a 4 KB piece of a program's memory",
"frame: a 4 KB slot in DRAM that holds one page",
"offset: the place inside the page; translation never changes it".

Bottom bar, label "Key point": "Translation answers one question: which frame holds this page right now? Because the kernel keeps that answer, it can move pages without the program noticing."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; label the
empty cells; add a sixth cell to a strip; draw more than four arrows; let two arrows cross;
draw any figure other than MEDIA; draw a core box; hatch anything; write MMU without CPU
in front of it; write any vendor or product name; rewrite the subtitle or the bottom bar;
write any non-English text.
```

## Prompt 2：02-page-table-tlb-cpu-mmu

```
Badge: "2"
Title: "Page Table, TLB, CPU MMU: Who Holds the Mapping"
Subtitle (blue): "The page table is the full list, in DRAM. The TLB is a small copy inside each core. The CPU MMU looks only at the TLB."

Layout: the left half holds one large core box. The right half holds one DRAM box at the
top and, under it, two cards side by side. Then the bottom bar.

The core box, named "Core 0". Inside it:
- top-left: the user SW figure "MEDIA".
- top-right: one kernel box: "TLB miss handler", "kernel SW, runs on this core when the TLB has no entry".
- middle-left, under MEDIA: one CPU hardware box: "CPU MMU", "checks the TLB on every load and store".
- bottom, across the full width of the core box: one CPU hardware box: "TLB", "a few recent entries only".
  Inside this TLB box, under its two lines, one ruled row: "page 0x416: frame 0x80024000".

The DRAM box, named "DRAM". Inside it, one small table labeled above it
"page table: one PTE per page", with header cells "page", "PTE" and three rows:
"0x415", "not valid: in no frame";
"0x416", "valid: frame 0x80024000";
"0x417", "valid: frame 0x8003A000".
Under the table, in small blue letters: "the full list, far too big to fit in a core".

Exactly four arrows, none crossing:
- an access arrow from MEDIA straight down to the CPU MMU box, label "MEDIA's address"
- an access arrow from the CPU MMU box straight down to the TLB box, label "look up the page"
- a kernel arrow from the TLB miss handler to the right, to the page table, label "reads the PTE"
- a kernel arrow from the TLB miss handler straight down to the TLB box, label "fills the entry"
There is no arrow between the CPU MMU box and the page table. In the gap between the core
box and the DRAM box, level with the CPU MMU box, one small blue note with no arrow:
"no arrow here: on this chip the CPU MMU never reads the page table".

Card one, under the DRAM box at the left. Heading "Why two tables", lines:
"page table: complete, but in DRAM, too slow to read on every access",
"TLB: inside the core and fast, but holds only a few entries".

Card two, under the DRAM box at the right. Heading "New words on this sheet", lines:
"page table: the kernel's full list of where each page is",
"PTE: page table entry, one line of it: valid with a frame, or not valid",
"TLB: a small copy of recent PTEs inside each core",
"CPU MMU: the hardware that translates, using the TLB only".

Bottom bar, label "Key point": "The TLB is a small copy of the page table. Many chips have hardware that refills the TLB from the page table by itself; ours does not, so the kernel SW fills every TLB entry."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the core
name; add a fourth row to the page table or a second row to the TLB; draw an arrow from
the CPU MMU box to the page table or to the DRAM box; draw more than four arrows; let two
arrows cross; draw any figure other than MEDIA; draw a second core box; hatch anything;
write MMU without CPU in front of it; write any vendor or product name; rewrite the
subtitle or the bottom bar; write any non-English text.
```

## Prompt 3：03-three-outcomes

```
Badge: "3"
Title: "One Access, Three Outcomes"
Subtitle (blue): "Most accesses never reach the kernel. When the TLB has no entry, the kernel steps in, and how much it must do depends on the PTE."

Layout: three panels side by side, the same size, in the upper part; a strip of two cards
under them; then the bottom bar. Each panel has the same layout from top to bottom: one
user SW figure, one CPU hardware box, then what happens next.

Panel one, named "TLB hit". Inside, from top to bottom:
- the user SW figure "UI".
- one CPU hardware box: "CPU MMU and TLB", "the entry is there".
- one DRAM box named "frame" holding one frame icon.
- under it, in small blue letters: "UI notices nothing".
Arrows: an access arrow from UI down to the CPU hardware box, label "UI loads";
an access arrow from the CPU hardware box down to the frame box, label "straight to the frame".

Panel two, named "TLB miss, PTE valid". Inside, from top to bottom:
- the user SW figure "MEDIA".
- one CPU hardware box: "CPU MMU and TLB", "no entry: exception".
- one kernel box: "TLB miss handler", "reads the PTE: valid", "writes the entry into the TLB".
- one plain box with a thin black outline: "the load runs again: TLB hit".
- under it, in small blue letters: "MEDIA is a little slower".
Arrows: an access arrow from MEDIA down to the CPU hardware box, label "MEDIA loads";
a kernel arrow from the CPU hardware box down to the kernel box, label "TLB miss";
a kernel arrow from the kernel box down to the plain box, label "return".

Panel three, named "TLB miss, PTE not valid: page fault". Inside, from top to bottom:
- the user SW figure "NET".
- one CPU hardware box: "CPU MMU and TLB", "no entry: exception".
- one kernel box: "TLB miss handler", "reads the PTE: not valid".
- one kernel box: "page fault handler", "gives the page a frame", "sets the PTE valid, writes the TLB entry".
- one plain box with a thin black outline: "the load runs again: TLB hit".
- under it, in small blue letters: "NET is much slower".
Arrows: an access arrow from NET down to the CPU hardware box, label "NET loads";
a kernel arrow from the CPU hardware box down to the TLB miss handler, label "TLB miss";
a kernel arrow from the TLB miss handler down to the page fault handler, label "PTE not valid";
a kernel arrow from the page fault handler down to the plain box, label "return".

No arrow crosses from one panel into another.

STRIP under the panels, two cards side by side.
Card one, heading "What follows on this chip", lines:
"the kernel steps in on every TLB miss, not only on page faults",
"every page fault starts as a TLB miss",
"this cost exists with or without compression".
Card two, heading "New words on this sheet", lines:
"exception: the core stops at the instruction and runs kernel SW, then runs the instruction again",
"TLB miss handler: the kernel code that runs on a TLB miss",
"page fault: a TLB miss whose PTE says the page is in no frame".

Bottom bar, label "Key point": "A TLB hit is hardware only. A TLB miss always enters the kernel; if the PTE is valid the kernel only refills the TLB, and if not, it must first give the page a frame."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw a fourth
panel; draw any arrow between panels; draw any figure other than UI, MEDIA and NET; draw a
clock, a timer or any time scale; hatch anything; write MMU without CPU in front of it;
write any vendor or product name; rewrite the subtitle or the bottom bar; write any
non-English text.
```

## Prompt 4：04-the-processor

```
Badge: "4"
Title: "The Processor: What Each Core Has, What Is Shared"
Subtitle (blue): "Each core has its own CPU MMU, TLB and L1 cache. The L2 cache, DRAM and the page table are shared by every core."

Layout: the left two thirds hold one large box with a black outline named "processor"
and, under it, one wide DRAM box. The right third holds two cards stacked. Then the bottom
bar.

Inside the processor box, two core boxes of the same size side by side, named "Core 0"
and "Core 1". Each core box holds, from top to bottom:
- two thread slots side by side. In Core 0 they are labeled "hw thread: UI" and
  "hw thread: MEDIA"; in Core 1 they are labeled "hw thread: NET" and "hw thread: LOG".
  Above each thread slot, the matching user SW figure drawn small: UI, MEDIA, NET, LOG.
- one CPU hardware box: "CPU MMU and TLB", "one TLB, shared by both hw threads",
  with one ruled entry row inside it. In Core 0 the row reads "page 0x416: frame 0x80024000";
  in Core 1 the row reads "page 0x2A7: frame 0x8003A000".
- one CPU hardware box: "L1 cache".
Under the two core boxes, still inside the processor box, one wide CPU hardware box
spanning both cores: "L2 cache", "shared by every core".
Under the processor box, in small blue letters: "two cores, two hw threads each: an example".

The DRAM box, named "DRAM", under the processor box. Inside it, three small labeled areas
side by side: "kernel code: exists once", "page table: shared by every core", and
"frames", with four frame icons under the word frames. The page table area sits in the
middle, under the gap between the two cores.

Exactly two arrows, both kernel arrows drawn the same way, not crossing each other. Each
starts at a thread slot, runs straight down through its own core's CPU MMU and TLB box,
its own L1 cache box and the L2 cache box, and ends on the page table area, because the
kernel's read of the page table goes through the caches:
- from the thread slot "hw thread: MEDIA" of Core 0, label "MEDIA misses in Core 0's TLB: the kernel reads the PTE"
- from the thread slot "hw thread: NET" of Core 1, label "NET misses in Core 1's TLB at the same moment"

Card one, at the top of the right third. Heading "Two things to take away", lines:
"each core's TLB is its own copy: Core 1 has no entry for page 0x416",
"no hardware keeps the TLBs in step with the page table: the kernel must".
Under the card, in small blue letters: "one TLB per core, shared by its hw threads: assumed, not yet checked in the CPU manual".

Card two, under card one. Heading "New words on this sheet", lines:
"core: one processor inside the chip; there are several",
"hw thread: a core can run two programs at once, one on each hw thread",
"L1, L2 cache: fast copies of DRAM lines; L1 per core, L2 shared",
"kernel code exists once, but several hw threads can run it at the same time".

Bottom bar, label "Key point": "The page table is shared; the TLBs are private copies in each core. Several hw threads can be in the kernel at the same moment, each on its own core's TLB."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the core
names; draw a third core; draw more than two arrows; let two arrows cross; draw any
figure other than UI, MEDIA, NET and LOG; draw a padlock; add a second entry row to a TLB; hatch anything; write MMU
without CPU in front of it; write any vendor or product name; rewrite the subtitle or the
bottom bar; write any non-English text.
```

## Prompt 5：05-parts-of-the-cpu-mmu-kernel-sw

```
Badge: "5"
Title: "The Parts of the CPU MMU Kernel SW"
Subtitle (blue): "Two entry points run on whichever hw thread hit the problem. A few services change the tables. One lock guards what is shared."

Layout: user SW figures across the top-left, three columns in the middle, a strip of two
cards across the bottom, then the bottom bar.

TOP-LEFT: the user SW figure "UI".

LEFT COLUMN, entry points. Two stacks, one above the other. Each stack is three kernel
boxes of the same size, overlapping like a fanned deck, each offset a little down and to
the right of the one behind it. Only the front box of each stack has text; the boxes
behind it are empty.
- upper stack, front box: "TLB miss handler", "runs on every TLB miss", "very short, never sleeps",
  "many hw threads can be in it at once".
- lower stack, front box: "page fault handler", "runs when the PTE is not valid",
  "may sleep", "finds out why, then fixes it".
Beside the two stacks, in small blue letters: "drawn stacked: several hw threads can run the same handler at once".

MIDDLE COLUMN, services. One kernel box named "services the handlers call" holding four
small rounded tiles of the same size, stacked:
"map or unmap a page: write its PTE",
"clear a page from every core's TLB",
"frame allocator: hand out and take back frames",
"switch programs: change which page table is used, see sheet 10".

RIGHT COLUMN. One DRAM box named "kernel tables" holding three small rounded tiles of the
same size, stacked: "page table", "free frames", "which page belongs to whom".
At its bottom edge, the padlock with the label "mm_lock: taken by the services".
Under the DRAM box, one kernel box: "compression kernel SW", "a separate set of sheets",
"called for a page whose data is compressed".

Exactly six arrows, none crossing:
- an access arrow from UI down to the upper stack, label "UI's access misses in the TLB"
- a kernel arrow from the upper stack straight across to the "page table" tile, passing
  above the services box, label "reads the PTE: with or without mm_lock is OPEN"
- a kernel arrow from the upper stack down to the lower stack, label "PTE not valid"
- a kernel arrow from the lower stack to the services box, label "calls"
- a kernel arrow from the services box to the kernel tables, label "lock, change, unlock"
- a kernel arrow from the lower stack along the bottom to the compression kernel SW box,
  passing under the services box, label "page is compressed: a function call"

STRIP across the bottom, two cards side by side.
Card one, heading "Who runs it", lines:
"no part has its own thread: each runs on the hw thread that needed it",
"so several copies of the same code can run at once, one per hw thread",
"does the TLB miss handler take mm_lock? not decided yet".
A tag "OPEN" at the top-right corner of card one.
Card two, heading "New words on this sheet", lines:
"map: give a page a frame; unmap: take it away",
"frame allocator: keeps the list of free frames",
"mm_lock: the lock taken before changing the shared tables".

Bottom bar, label "Key point": "The TLB miss handler, entered by an exception, and the page fault handler it hands over to both run on the hw thread that missed. They use a few services that change the shared tables under mm_lock. Compression is reached from the page fault handler by a plain function call."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw a queue,
an inbox or a waiting line; draw more than six arrows; let two arrows cross; draw any
figure other than UI; draw the LZ4 HW; hatch anything; write the words manager
or instance; write MMU without CPU in front of it; write any vendor or product name;
rewrite the subtitle or the bottom bar; write any non-English text.
```

## Prompt 6：06-the-pte-is-ours

```
Badge: "6"
Title: "The PTE Is Ours to Design"
Subtitle (blue): "The CPU fixes what a TLB entry looks like. Only the kernel reads the page table, so the kernel decides what a PTE looks like and how the table is shaped."

Layout: two panels side by side in the upper half, the left one about two fifths of the
width, the right one about three fifths; a panel across the lower part; then the bottom
bar.

Left panel, named "Fixed by the CPU". Inside: one CPU hardware box drawn as a wide strip
divided into four cells: "TLB entry", "page", "frame", "allowed: read, write, run".
Under it, a tag "OPEN" with a small blue note beside it: "exact fields: the CPU manual".

Right panel, named "Decided by the kernel". Inside: one kernel box drawn as a wide strip
divided into six cells: "PTE", "valid", "frame", "may read, write, run", "user or kernel only",
"spare bits for the kernel".
Under it, in small blue letters, two lines:
"a common way: when not valid, the spare bits say where the data is",
"the kernel may also keep a used mark here: see sheet 7".

One kernel arrow from the PTE strip in the right panel to the TLB entry strip in the left
panel, curving above both panels, label "the TLB miss handler converts and writes".

Lower panel, named "Shapes of the page table: a trade-off". Inside, a small table with
header cells "shape", "TLB miss handler reads", "memory for the table", "good when";
three rows:
"one flat list: one PTE per page", "one PTE", "large, even for unused pages", "memory is small and dense";
"a two-level tree", "two entries", "small when memory is sparse", "programs use scattered regions";
"a hash table", "one bucket, sometimes more", "set by how many pages are mapped", "many address spaces share it".
At the right of the table, a tag "OPEN" with a small blue note: "which shape: not decided".

Under the lower panel, a card, heading "New words on this sheet", lines:
"TLB entry: one line in the TLB, in the CPU's own format",
"two-level tree: a small top table points to small second tables",
"hash table: the page number picks a bucket that holds its PTE".

Bottom bar, label "Key point": "With no hardware reading the page table, its format is the kernel's choice. A faster TLB miss handler usually costs more memory for the table; the choice is still open."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw more
than one arrow; draw any figure; add a row to the table; hatch anything; write MMU
without CPU in front of it; write any vendor, CPU or operating system name; rewrite the
subtitle or the bottom bar; write any non-English text.
```

## Prompt 7：07-tlb-miss-handler

```
Badge: "7"
Title: "The TLB Miss Handler, Step by Step"
Subtitle (blue): "NET loads from page R and the TLB has no entry for it. Everything below runs on NET's own hw thread, and other hw threads can do the same at once."

Layout: three horizontal lanes across the full width, separated by thin horizontal lines,
each lane name in bold at its left edge: top lane "user SW", middle lane "CPU",
bottom lane "kernel SW, on NET's hw thread". Eight step boxes run left to right along the
lanes, in time order. Under the lanes, two sticky notes and one card side by side. Then
the bottom bar.

Top lane: at its left edge, the user SW figure "NET".

Steps, each a step box in the lane named:
- step "1", user SW lane: "NET loads from page R"
- step "2", CPU lane: "no entry for R in the TLB: exception"
- step "3", kernel lane: "save a few registers"
- step "4", kernel lane: "find where R's PTE is from R's page number"
- step "5", kernel lane: "read R's PTE, often found in the L1 or L2 cache"
- step "6", kernel lane: "valid: write R's entry into this core's TLB"
- step "7", kernel lane: "restore the registers, return from the exception"
- step "8", user SW lane: "NET's load runs again: TLB hit"
Under step 6, a small kernel box: "not valid: go to the page fault handler", joined to
step 6 by a short purple kernel arrow with the label "not valid".

Arrows: thin black arrows join step 1 to 2, 2 to 3, 3 to 4, 4 to 5, 5 to 6, 6 to 7, 7 to 8,
in that order, with no labels. Plus the one purple kernel arrow from step 6 described
above. No other arrows.

Sticky one, heading "Why it must be tiny", lines:
"it runs on every TLB miss, far more often than page faults",
"it must never sleep or wait long",
"it must not miss in the TLB itself: its code, its stack and the page table must be reachable without the TLB".
Sticky two, heading "Still to decide", lines:
"how the handler reaches the page table without the TLB: the CPU manual",
"which TLB entry to replace when the TLB is full: the CPU manual",
"whether the handler takes mm_lock: sheets 11 and 12".
A tag "OPEN" at the top-right corner of sticky two.
The card, heading "New words on this sheet", lines:
"register: a value the core is working with; the handler must put them back",
"used mark: a note that a page was touched recently; with no hardware walk, likely only this handler can set it".

Bottom bar, label "Key point": "The TLB miss handler reads one PTE and writes one TLB entry. It runs so often that every instruction in it counts, and it must never itself miss in the TLB."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw more than
eight step boxes; draw more than eight arrows; draw the padlock; draw a clock or any time
scale; hatch anything; draw any figure other than NET; write MMU without CPU in front of
it; write any vendor or product name; rewrite the subtitle or the bottom bar; write any
non-English text.
```

## Prompt 8：08-page-fault-handler

```
Badge: "8"
Title: "The Page Fault Handler: Find the Cause, Then Fix It"
Subtitle (blue): "LOG touches page S and its PTE is not valid. The handler takes the lock, looks again, and acts on the reason."

Layout: a flow from left to right in the upper two thirds, a strip of three boxes under it,
then the bottom bar.

FLOW, left to right:
- at the far left, the user SW figure "LOG".
- next, one kernel box: "TLB miss handler", "S's PTE is not valid".
- next, one kernel box with the padlock labeled "mm_lock" at its top edge:
  "page fault handler", "take mm_lock, read S's PTE again",
  "another hw thread may have fixed it meanwhile".
- to the right of it, five outcome boxes stacked in one column, all the same size, each a
  kernel box:
  "already valid now", "just write the TLB entry";
  "first touch: no data yet", "take a free frame, fill it with zeros";
  "the data is compressed", "call the compression kernel SW to decompress it";
  "the access is not allowed", "for example a write to a read-only page";
  "the address belongs to nothing", "no page is there".
- at the far right, two kernel boxes stacked, the upper one level with the first three
  outcome boxes, the lower one level with the last two:
  upper: "finish: fixed", "set S's PTE valid if needed, write the TLB entry",
  "release mm_lock, return", "LOG's instruction runs again";
  lower: "finish: refused", "release mm_lock", "report an error to LOG".

Arrows:
- an access arrow from LOG to the TLB miss handler box, label "LOG loads from page S"
- a kernel arrow from the TLB miss handler box to the page fault handler box, label "PTE not valid"
- five short kernel arrows from the page fault handler box, one to each outcome box, no labels
- three kernel arrows from the outcome boxes "already valid now", "first touch: no data yet"
  and "the data is compressed" to the "finish: fixed" box, no labels
- two kernel arrows from the outcome boxes "the access is not allowed" and
  "the address belongs to nothing" to the "finish: refused" box, no labels
No other arrows.

STRIP under the flow, three boxes side by side.
A sticky note, heading "Unlike the TLB miss handler", lines:
"it may sleep, for example while the data is decompressed; it lets go of mm_lock while it sleeps",
"so the code that faulted must be code that is allowed to wait",
"in the model: a page fault is refused if it happens in an interrupt handler, in code that holds a lock, or in a hard real-time thread".
A card, heading "Where page swap fits", lines:
"page swap is one of the causes above: the compressed one",
"the compression kernel SW runs on LOG's hw thread too, as a function call".
A card, heading "New words on this sheet", lines:
"first touch: a page nobody has written yet; it reads as zeros",
"interrupt handler: kernel code started by a device, not by a program",
"hard real-time thread: a thread that must finish within a fixed time".

Bottom bar, label "Key point": "The page fault handler checks the PTE again under the lock, then acts on the cause: three causes end with the page in a frame, two end with an error for the program. Bringing back a compressed page is just one of the causes."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw a sixth
outcome box; let two arrows cross; fill the Key point label box with a color; draw the LZ4 HW;
hatch anything; draw any figure other than LOG; write MMU without CPU in front of it;
write any vendor or product name; rewrite the subtitle or the bottom bar; write any
non-English text.
```

## Prompt 9：09-changing-a-mapping

```
Badge: "9"
Title: "Changing a Mapping: Which Way Matters"
Subtitle (blue): "Giving a page a frame needs nothing from other cores. Taking a frame away, or allowing less, needs every core's TLB cleared first."

Layout: three panels side by side in the upper part, the same size; a strip of two cards
under them; then the bottom bar.

Panel one, named "Give a page a frame". Inside, a tag "NOT VALID TO VALID" at its top.
Under it, one kernel box: "kernel SW", "write the PTE: valid, frame F".
Under it, in small blue letters: "other cores have no entry for this page yet",
"their next access misses and reads the new PTE".
One kernel arrow from the kernel box down to a small table "page table" with one row:
"page P: valid, frame F", label "1 write the PTE". No other arrow in this panel.

Panel two, named "Take a frame away". Inside, a tag "VALID TO NOT VALID" at its top.
Under it, three step boxes stacked top to bottom:
- step "1": "set the PTE not valid"
- step "2": "clear page P from every core's TLB and wait until all are done"
- step "3": "only now reuse frame F or hand it to other hardware"
Thin black arrows join step 1 to 2 and 2 to 3.
Under the steps, in small blue letters: "the reverse order lets a core refill the old entry from a PTE that is still valid".

Panel three, named "Allow less". Inside, a tag "READ-WRITE TO READ-ONLY" at its top.
Under it, one kernel box: "kernel SW", "write the PTE: read-only",
"clear page P from every core's TLB".
Under it, in small blue letters: "an old entry would still let a core write the page".

STRIP under the panels, two cards side by side.
Card one, heading "If one core is skipped", lines:
"that core still gets a TLB hit on page P",
"it keeps reading and writing frame F, which now holds another page",
"no exception happens, so the kernel never finds out",
"in the model, a test that skips one core fails at once".
Card two, heading "Still to learn from the CPU manual", lines:
"how one core clears an entry in another core's TLB",
"how long that takes",
"whether the TLB remembers that a PTE was not valid".
A tag "OPEN" at the top-right corner of card two.

Bottom bar, label "Key point": "Order for taking a frame away: set the PTE not valid, clear the entry from every core's TLB, and only then touch the frame. The same clearing is needed when a page loses a permission."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the step
badges; draw more than four arrows; draw an arrow between panels; draw any figure; draw a
core box; hatch anything; write MMU without CPU in front of it; write any vendor or
product name; rewrite the subtitle or the bottom bar; write any non-English text.
```

## Prompt 10：10-many-programs

```
Badge: "10"
Title: "Many Programs, One TLB per Core"
Subtitle (blue): "If each program has its own page table, the same page number means different frames in different programs, and the TLB must not mix them up."

Layout: three panels side by side in the upper two thirds; a card under them across the
full width; then the bottom bar.

Panel one, named "Two programs, two page tables". Inside:
- the user SW figure "UI" at the top-left and the user SW figure "NET" at the top-right.
- under UI, a small table labeled "UI's page table" with one row: "page 0x416: frame 0x80024000".
- under NET, a small table labeled "NET's page table" with one row: "page 0x416: frame 0x8003A000".
- under both, in small blue letters: "same page number, different frames".

Panel two, named "Switching programs on a core". Inside:
- one CPU hardware box: "TLB of Core 0", with one ruled row: "page 0x416: frame 0x80024000",
  and under the row, in small letters: "left over from UI".
- at the top of the panel, the user SW figure NET drawn a second time, small, and one
  access arrow from it down to the TLB box, label "NET now runs on Core 0 and reads page 0x416".
- under the TLB box, two option boxes side by side:
  a kernel box "option A: clear the TLB at every switch", "simple; then many TLB misses";
  a kernel box "option B: tag each entry with its address space", "no clearing; the CPU must support tags".

Panel three, named "Two hw threads, one TLB". Inside:
- one core box named "Core 1" holding two thread slots side by side, labeled
  "hw thread: MEDIA" and "hw thread: LOG", and under them one CPU hardware box:
  "TLB of Core 1", "shared by both hw threads".
- under the core box, in small blue letters, two lines:
  "if MEDIA and LOG run in different address spaces at the same time,",
  "the TLB must tell their entries apart: tags are needed, not just clearing".

Card across the full width, under the panels, heading "Open questions", lines:
"does the CPU support address space tags in the TLB? the CPU manual",
"do our programs get separate address spaces, or share one? a product decision",
"the kernel's own pages: mapped the same way in every program? a design decision".
A tag "OPEN" at the top-right corner of the card. At its right end, in small letters:
"New word: address space: one program's whole set of pages and its page table".

Bottom bar, label "Key point": "Separate address spaces make the TLB carry entries from several programs. The kernel must clear it at each switch or tag the entries, and two hw threads sharing one TLB need tags."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the core
names; draw more than one arrow; draw any figure other than UI and NET; draw a figure in
panel three; hatch anything; write MMU without CPU in front of it; write any vendor or product
name; rewrite the subtitle or the bottom bar; write any non-English text.
```

## Prompt 11：11-refill-against-clear

```
Badge: "11"
Title: "A TLB Miss Handler Without a Lock Can Undo a Clear"
Subtitle (blue): "Found in the model: the handler reads a PTE, the kernel takes the frame away and clears every TLB, and then the handler writes the old entry."

Layout: a timeline across the upper two thirds with three lanes, a strip of three cards
under it, then the bottom bar. Time runs left to right; one arrow under the lanes is
labeled "time".

Lanes, each with its name in bold at its left edge, separated by thin horizontal lines:
- lane "Core 1, hw thread A", with the user SW figure NET drawn small at its left and,
  under the lane name, in small letters: "NET runs here; on a TLB miss the kernel's handler runs here too"
- lane "Core 1, hw thread B", with under the lane name, in small letters: "the kernel, taking frame F away"
- lane "Core 0"

Positions: to the right of the lane names, divide the width into six equal invisible
columns. Every step box sits exactly in the column given. Each step box holds a small
round number badge and its line. Step boxes in lane A after step 1 have a dashed purple
outline, because the kernel's handler is running.
- column one, lane A, a plain black outline: step "1": "NET touches page P: TLB miss"
- column two, lane A, dashed purple: step "2": "handler reads P's PTE: valid, frame F"
- column two, lane B: step "3": "sets P's PTE not valid, clears P from Core 1's TLB"
- column three, lane Core 0: step "4": "takes the clear request, clears P from Core 0's TLB, answers"
- column four, lane B: step "5": "all answers in: frame F now gets another page"
- column five, lane A, dashed purple, with a thick outline: step "6": "handler writes what it read in step 2: P is in frame F"
- column six, lane A, a plain black outline: step "7": "NET reads frame F and gets another page's data"
A tag "STALE ENTRY" sits directly above step 6.

Exactly two arrows besides the time arrow:
- one kernel arrow from step 3 down to step 4, label "clear request"
- one thin dotted black line with no arrowheads, above lane A, from step 2 to step 6, with
  the label above it: "read and write happen at two moments; the whole clear fits in between"

Under the timeline, three cards side by side.
Card one, heading "Why the clear missed it", lines:
"in step 3 Core 1's TLB had no entry for P yet",
"step 6 wrote one after the clear had finished".
Card two, heading "What the model is", lines:
"a model of the kernel on a host computer, not this CPU",
"the clear request is one example: this CPU's real mechanism is not known",
"the same failure appeared in several orders of steps".
Card three, heading "New words on this sheet", lines:
"stale entry: a TLB entry that no longer matches the PTE",
"clear request: one hw thread asks another to clear an entry; the other takes it like an interrupt",
"race: a result that depends on the exact order of steps on different hw threads".

Bottom bar, label "Key point": "A TLB miss handler that takes no lock can write an entry the kernel has just cleared. Sheet 12 shows the two ways that left no stale entry in the model."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge, the core
names and the step badges; draw more arrows than the time arrow, the one kernel arrow and
the one dotted line; draw a fourth lane; draw a padlock; hatch anything; draw any figure
other than NET; write MMU without CPU in front of it; write any vendor or product name;
rewrite the subtitle or the bottom bar; write any non-English text.
```

## Prompt 12：12-what-held-in-the-model

```
Badge: "12"
Title: "Two Ways With No Stale Entry, and a Separate Deadlock"
Subtitle (blue): "Part one: four ways to write the TLB miss handler, tried against the example clear request. Part two: a deadlock that has nothing to do with which way is picked."

Layout: a panel across the upper half, then two panels side by side in the lower half,
then the bottom bar.

Upper panel, named "Part one: the TLB miss handler, four ways". Inside, a small table with
header cells "way", "how the TLB miss handler works", "stale entry in the model?";
four rows:
"way 1", "takes no lock; clear requests go to each core", "yes";
"way 2", "takes no lock; keeps interrupts off for its few steps, so it finishes before it takes a clear request; clear requests go to each hw thread", "none found";
"way 3", "takes no lock; writes the entry, then reads the PTE again and drops the entry if the PTE changed", "yes: before the drop, the other hw thread of the core can use the entry";
"way 4", "holds mm_lock while it reads the PTE and writes the entry; waits for mm_lock with interrupts on, even when the miss happens inside an interrupt handler", "none found".
The words "none found" in the two rows are in bold.
Under the table, in small blue letters, three lines:
"none found: no stale entry in any order the model tried; that is evidence, not proof",
"why each hw thread: the two hw threads of a core share one TLB, and the other one may be in the middle of a handler",
"way 2 turns interrupts off but never waits for a lock; way 4 waits for the lock, so it must wait with interrupts on".

Lower-left panel, named "Part two: a deadlock, in the model". Inside, two kernel boxes side by side:
- left: "Core 1: kernel taking frame F away", "holds mm_lock",
  "waits for Core 0 to answer the clear request", with the padlock labeled "mm_lock" beside it.
- right: "Core 0: any kernel code that wants mm_lock", "for example a page fault handler",
  "waits for mm_lock with interrupts off, so it never takes the request".
Two kernel arrows between them, one above the other: the upper from left to right labeled
"clear request", the lower from right to left labeled "wants mm_lock". Under the boxes, in
small blue letters: "each waits for the other, forever; it happened with all four ways, so picking a way does not avoid it".

Lower-right panel, named "Rules this suggests". Inside, four lines:
"always: no kernel code waits for mm_lock with interrupts off",
"and pick one of two: way 2, or way 4",
"way 2: no lock, interrupts off for the handler's few steps, clear requests to every hw thread",
"way 4: the handler holds mm_lock and waits for it with interrupts on, also inside interrupt handlers".
A tag "OPEN" at the top-right corner of the panel, with a small blue note: "which one to pick: not decided".
Under the three lines, a card, heading "New words on this sheet", lines:
"deadlock: two parts each wait for the other, so neither moves",
"interrupts off: the hw thread takes no requests until they are on again",
"interrupt handler: kernel code that runs when a request or a device interrupts".

Bottom bar, label "Key point": "In the model only way 2 and way 4 never left a stale entry; which one to use is not decided. Separately, no kernel code may wait for mm_lock with interrupts off: other kernel code doing that deadlocked with all four ways."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge and the core
names; add a row to the table; put the deadlock in the table; draw more than two arrows;
draw any figure; hatch anything; fill a tag or the Key point label with a color; write MMU
without CPU in front of it; write any vendor or product name; rewrite the subtitle or the
bottom bar; write any non-English text.
```

## Prompt 13：13-where-it-goes-wrong

```
Badge: "13"
Title: "Where It Goes Wrong If You Are Careless"
Subtitle (blue): "Six traps of a kernel that fills the TLB itself on many cores. Most of them do not crash at once; they quietly read the wrong frame."

Layout: six cards in two rows of three, all the same size, then the bottom bar. Each card
has, at its top-left, one small simple black line icon described below, then a bold
heading beside the icon, one line starting with "Risk:" and one line starting with "Rule:".
At the bottom of each card, one small blue line, exactly as quoted, with no prefix word
in front of it.

Row one:
- icon: a small grid of four squares with one square crossed out.
  Heading "A TLB entry left behind".
  "Risk: a frame is reused while one core still has an entry for the old page",
  "Rule: set the PTE not valid, clear every core's TLB, then touch the frame".
  Blue line: "sheet 9; checked in the model".
- icon: a small clock with two hands and a short arrow.
  Heading "An old entry written late".
  "Risk: a TLB miss handler writes an entry after the kernel cleared it",
  "Rule: pick one of the two ways that had no failure in the model".
  Blue line: "sheets 11 and 12; which way is not decided".
- icon: two small circles with arrows chasing each other.
  Heading "Waiting for the lock with interrupts off".
  "Risk: the kernel holding mm_lock waits for an answer that never comes",
  "Rule: never wait for mm_lock with interrupts off".
  Blue line: "sheet 12; found in the model".
Row two:
- icon: a small loop arrow.
  Heading "A miss inside the TLB miss handler".
  "Risk: the handler's own code, stack or page table is not in the TLB, so it misses again inside itself",
  "Rule: keep them where the handler reaches them without the TLB".
  Blue line: "how to do that: the CPU manual".
- icon: two small page tiles side by side with an equals sign between them.
  Heading "Another program's entry".
  "Risk: after a program switch the TLB still holds the old program's entries",
  "Rule: clear the TLB at the switch, or tag every entry with its address space".
  Blue line: "sheet 10; tags depend on the CPU manual".
- icon: two small arrows pointing at the same small square.
  Heading "Two entries for one page".
  "Risk: both hw threads of a core miss on the same page and both write an entry",
  "Rule: find out what the CPU does with two matching entries before relying on it".
  Blue line: "the CPU manual".

Bottom bar, label "Key point": "Every TLB entry is written by the kernel, so stale, duplicate and wrong-program entries are the kernel's to prevent. Keep the order of steps, never wait for the lock with interrupts off, and keep the handler's own memory reachable; three answers wait for the CPU manual."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; add a seventh
card; draw any arrow other than the small icons; draw any figure; hatch anything; write a
word such as Where or See before the blue lines; fill the Key point label box with a
color; write MMU without CPU in front of it; write any vendor or product name; rewrite
the subtitle or the bottom bar; write any non-English text.
```

## Prompt 14：14-modeled-and-open

```
Badge: "14"
Title: "What Is in the Model, What Is Open"
Subtitle (blue): "The model checks the order of steps. Most of what is open needs the CPU manual; the rest are design and product decisions."

Layout: a narrow panel at the left, about one third of the width; a wide panel at the
right, about two thirds of the width; then the bottom bar.

Left panel, named "In the model so far". Inside, five lines, each starting with a small check mark:
"take a frame away: PTE not valid, clear every core's TLB, then reuse",
"the page fault handler checks the PTE again under mm_lock",
"a first touch gets a frame of zeros",
"two ways for the TLB miss handler that had no failure against the example clear request",
"waiting for mm_lock with interrupts off deadlocks: a rule".
Under the lines, a small blue note: "a model on a host computer: not yet run on this processor".

Right panel, named "Open". Inside, a small table with header cells "question",
"why it matters", "needs"; nine rows:
"the CPU's instruction set and model", "every handler is written for it", "the CPU manual";
"how many TLB entries, and are there address space tags", "how often TLB misses happen; whether a switch clears the TLB", "the CPU manual";
"how one core clears another core's TLB, and how long it takes", "every frame taken away waits for it", "the CPU manual";
"how the TLB miss handler reaches the page table without the TLB", "a miss inside the handler", "the CPU manual";
"two hw threads of one core writing the TLB at once", "two entries for one page", "the CPU manual";
"does the TLB miss handler take mm_lock", "the race with clearing", "a design decision";
"the shape of the page table and the PTE format", "handler speed against memory", "a design decision";
"separate address spaces for our programs", "isolation against the cost of switching", "a product decision";
"how long one TLB miss takes", "every program pays it on every TLB miss", "measurement on the chip".
Under the table, a small blue note: "design decision: by the kernel team; product decision: how the product should behave".

Bottom bar, label "Key point": "The rules for the order of steps are checked in the model. What is open is mostly what this CPU provides; until the manual answers, the handlers cannot be written."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; add or drop
a row; draw any arrow; draw any figure; hatch anything; write MMU without CPU in front of
it; write any vendor or product name; rewrite the subtitle or the bottom bar; write any
non-English text.
```

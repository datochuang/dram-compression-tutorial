# 圖像生成提示詞：CPU MMU basics

**版本**：Prompt 1 與 Prompt 2 是第一版。Prompt 3 是第二版，改了什麼寫在那一節的開頭。三張都已驗收，紀錄在 `review-gen3-20261113.md`。

**對象**：用 `sketchnote-gen` skill 生成這組圖的人，以及讀圖驗收的 agent。
**目的**：讓沒有接觸過 CPU MMU 的 team member 與主管看懂三件事：address 為什麼要轉換；page table、TLB、CPU MMU 各是什麼；kernel 把一個 page 的 frame 拿走時，為什麼要先清掉每個 core 的 TLB。
**風格**：`whiteboard`（和 `figures/system-overview/` 同一種，顏色的意思也相同）。
**內容的來源**：repo 的 `README.md` 第 1、2、6 層。平台前提 P1 與 P3 在專案的 `CLAUDE.md`。第 C 張的順序來自 `sim/hostsim/deps.py` 的規則：`pte_clear` 在 `tlb_inval` 之前，`tlb_inval` 在 `put_frame` 之前。address 都是 `README.md` 用的例子。
**約束**：圖上文字全部英文；CPU 的硬體淺藍、kernel SW 紫色虛線框；永遠寫 CPU MMU，不單寫 MMU；不出現廠商或產品名稱；這三張沒有 LZ4 HW、沒有 lock、沒有斜線；數字只有雙引號裡的。
**怎麼用**：skill 一張一張生，OpenAI 預設模型與 high 品質，`--size 1536x1024`；全部生完後做一次只給圖的冷讀；通過的存成本資料夾 `NN-<name>.png`。文字清單由雙引號字串自動產生。建立日期 2026-11-13。
**和 `figures/system-overview/` 的關係**：那一組的讀者已經知道 CPU MMU。這一組補在它前面與後面。badge 用字母，避免和那一組的 1 到 4 混在一起。`README.md` 的閱讀順序是 A、B、那一組的 2、1、3、然後 C。

## 脊椎

| # | 檔名 | 讀者的問題 | 主張 |
|---|------|------|------|
| A | `01-why-translate.png` | user SW 用的 address 為什麼不是 DRAM 上的位置？ | 轉換只回答一件事：這個 page 現在在哪個 frame。page 裡面的位置不變。 |
| B | `02-page-table-tlb-mmu.png` | 轉換靠哪些東西，各在哪裡，誰讀誰寫？ | page table 是 DRAM 裡的完整對照表，只有 kernel SW 讀寫。TLB 是 CPU 裡的一小份抄本，由 kernel SW 填。CPU MMU 只查 TLB。 |
| C | `03-clear-every-tlb-first.png` | kernel 改了 PTE，別的 core 的 TLB 還留著舊的，怎麼辦？ | 順序固定：PTE 改成 invalid，把這一筆從每個 core 的 TLB 清掉，之後才能動那個 frame。 |

---

## Style block（每張都先貼這段）

```
Hand-drawn engineering whiteboard sheet, the kind an engineer draws to walk a colleague
through a design, tidy and uncrowded. Aspect ratio 3:2, landscape. Plain white background.
Black marker line art with slightly wobbly strokes. Hand-lettered English text, small but
clean and fully legible. Addresses such as 0x416 are lettered exactly as quoted, digit for
digit, with a lower-case x and upper-case hex letters.

Named objects: whenever the prompt says 'the <object>', draw the same object every time.
- a core box: a large rounded rectangle with a black outline and a plain white fill. Its
  quoted name is lettered in bold at its top-left corner, inside.
- a CPU hardware box: a rectangle with a light blue fill and a black outline, holding only
  its quoted lines, the first line in bold.
- a kernel instance: a small rounded rectangle with a dashed purple outline and a plain
  white fill, holding only its quoted lines, the first line in bold.
- a DRAM box: a rectangle with a plain white fill and a black outline. Its quoted name is
  lettered in bold at its top-left corner, inside. It holds only what the prompt lists.
- a table: a rectangle with a black outline and a plain white fill, its quoted heading in
  bold across the top, and under it the quoted rows, one per ruled row.
- a strip: a tall narrow rectangle with a black outline, cut by horizontal lines into equal
  cells stacked from top to bottom. Cells are empty unless the prompt puts a label in one.
- a card: a rounded rectangle with a black outline and a plain white fill, a bold heading
  and the quoted lines under it, one per row.
- an access arrow: a solid orange arrow with one arrowhead and a short orange label
  written along it.
- a kernel arrow: a solid purple arrow with one arrowhead and a short purple label
  written along it.
- a sticky note: a pale yellow sticky note with a bold heading and the quoted lines under
  it, one per row.
- the user SW figure: a round-headed stick figure sitting at a small laptop.
- a frame icon: one small plain white square with a black outline, never hatched.

Color rules: orange for access arrows and the title underline; purple for kernel instances
and kernel arrows; light blue fill only for CPU hardware boxes; pale yellow only for sticky
notes; blue for the subtitle line and small notes; all other lines and text black. No
hatching anywhere. No gradients, no photo textures, no logos, no watermarks.

Fixed layout: a square badge with one letter at the top-left; the title to its right,
underlined in orange; one blue subtitle line under the title; the boxes as the prompt
places them; a bottom bar across the full width with its label in a small box at its left.

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
Badge: "A"
Title: "Why an Address Is Translated"
Subtitle (blue): "User SW uses logical addresses. DRAM is reached by physical addresses. Every access turns one into the other."

This sheet has no core box, no kernel instance, no purple arrow and no hatching.

Layout: three columns of equal height, then the bottom bar. The left column is the logical
side. The middle column is the translation. The right column is the DRAM side.

Left column. A bold heading at its top: "Logical address space". Under the heading, in
small letters: "what user SW sees". Under that, one strip with five cells. The third cell
from the top has a thick black outline and holds the label "page 0x416". Inside that same
cell, near its lower edge, one small black dot with the label "offset 0xC80" beside it.
The other four cells are empty. Under the strip, in small blue letters: "one page = 4096 B".
The user SW figure sits to the left of the strip, level with its top, labeled "user SW".

Right column. A bold heading at its top: "DRAM". Under the heading, in small letters:
"physical addresses". Under that, one strip with five cells, the same size as the left
strip. The second cell from the top has a thick black outline and holds the label
"frame at 0x80024000". Inside that same cell, near its lower edge, one small black dot
with the label "offset 0xC80" beside it. The other four cells are empty. Under the strip,
in small blue letters: "one frame = 4096 B".

Middle column, from top to bottom:
- one CPU hardware box: "Translation", "which frame holds this page?"
- a card. Heading: "The arithmetic". Three lines: "0x00416C80 = page 0x416 + offset 0xC80",
  "page 0x416 is in the frame at 0x80024000", "0x80024000 + 0xC80 = 0x80024C80".
- a sticky note. Heading: "What this buys". Three lines: "user SW never needs to know where its data is",
  "the kernel can move a page to another frame", "the kernel can even take the frame away for a while".

Exactly three arrows, all access arrows:
- from the user SW figure to the thick-outlined cell of the left strip, label "read 0x00416C80"
- from the thick-outlined cell of the left strip to the Translation box, label "page 0x416"
- from the Translation box to the thick-outlined cell of the right strip, label "its frame".
  The arrowhead touches the thick-outlined cell and no other cell.

Bottom bar, label "Key point": "Translation answers one question: which frame holds this page right now? The offset inside the page never changes."

Text manifest: auto

Do not: write any digit or number that is not quoted; label the empty cells; add a sixth
cell to a strip; draw more than three arrows; draw more than one figure; draw a purple
arrow; hatch anything; write any vendor or product name; rewrite the subtitle or the
bottom bar; write any non-English text.
```

## Prompt 2：02-page-table-tlb-mmu

```
Badge: "B"
Title: "Page Table, TLB, CPU MMU: Who Holds the Mapping"
Subtitle (blue): "The page table is the full list, in DRAM. The TLB is a small copy inside the CPU. The CPU MMU looks only at the TLB."

This sheet has no strip, no frame icon and no hatching.

Layout: the left half holds one large core box. The right half holds one large DRAM box
at the top and, under it, a card and a sticky note side by side. Then the bottom bar.

The core box, named "CPU". Inside it:
- top-left: the user SW figure, labeled "user SW".
- top-right: a kernel instance: "kernel SW", "runs on the CPU when it is needed".
- middle-left, under the user SW figure: one CPU hardware box: "CPU MMU", "checks the TLB on every access".
- bottom, across the full width of the core box: one CPU hardware box: "TLB", "a few recent entries only".
  Inside this TLB box, under its two lines, one ruled row holding: "page 0x416: frame 0x80024000".

The DRAM box, named "DRAM". Inside it, one table and nothing else. Heading of the table:
"page table: one PTE per page". Three rows: "page 0x415: invalid",
"page 0x416: valid, frame 0x80024000", "page 0x417: valid, frame 0x8003A000".
Under the table, still inside the DRAM box, in small blue letters: "the full list, far too big to fit in the CPU".

Exactly four arrows:
- an access arrow from the user SW figure straight down to the CPU MMU box, label "logical address"
- an access arrow from the CPU MMU box straight down to the TLB box, label "look up the page"
- a kernel arrow from the kernel instance to the right, to the page table, label "reads and writes the PTEs"
- a kernel arrow from the kernel instance straight down to the TLB box, label "fills the entries"
There is no arrow between the CPU MMU box and the page table. In the gap between the core
box and the DRAM box, level with the CPU MMU box, one small blue note with no arrow:
"no arrow here: the CPU MMU never reads the page table".

The card, under the DRAM box at the left. Heading: "Why two tables".
Two lines: "page table: complete, but in DRAM, too slow to read on every access",
"TLB: inside the CPU and fast, but holds only a few entries".

The sticky note, under the DRAM box at the right. Heading: "A PTE says one of two things".
Two lines: "valid: this page is in that frame", "invalid: this page has no frame right now".

Bottom bar, label "Key point": "The TLB is a small copy of the page table. The kernel SW fills the copy. Hardware never reads the page table."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a fourth row to the page table
or a second row to the TLB; draw an arrow from the CPU MMU box to the page table or to
the DRAM box; draw more than four arrows; draw more than one figure; add a second core
box; hatch anything; write any vendor or product name; rewrite the subtitle or the
bottom bar; write any non-English text.
```

## Prompt 3：03-clear-every-tlb-first

第二版，2026-11-13。第一版在冷讀得到困惑指數 3：TLB hit 的橘色箭頭看不出是正常情況還是出錯情況，箭頭橫穿 Core 1，畫面沒有時間點，page 編號和前兩張不同，第 3 步沒有主詞。這一版把 DRAM 放到兩個 core 的下面，箭頭都不交叉；畫面固定在第 1 步做完、第 2 步之前；page 改成和前兩張相同的 0x416；第 3 步用 kernel 的紫色並寫出主詞。第一版的圖在 `gen2/03-clear-every-tlb-first.png`。

```
Badge: "C"
Title: "Taking a Frame Away: Clear Every TLB Before Touching the Frame"
Subtitle (blue): "Each core's TLB is a private copy. When the kernel changes a PTE, no TLB finds out by itself."

This sheet has no strip and no hatching.

Layout: the left two thirds of the sheet hold three boxes. In the upper part, two core
boxes of the same size side by side. Directly under them, one wide DRAM box as wide as
the two core boxes together. The right third of the sheet holds a card at the top and a
sticky note under it. Then the bottom bar across the full width.

The left core box, named "Core 0". Inside it:
- top: the user SW figure, labeled "user SW".
- bottom: one CPU hardware box: "TLB of Core 0", "page 0x416: frame 0x80024000".

The right core box, named "Core 1". Inside it:
- top: one CPU hardware box: "TLB of Core 1", "page 0x416: frame 0x80024000".
- bottom: a kernel instance: "kernel SW instance", "running on Core 1".

The DRAM box, named "DRAM", under both core boxes. Inside it:
- left half, directly under the Core 0 box: one frame icon, drawn large, with the label
  "frame 0x80024000" under it. To the right of the frame icon, in small purple letters,
  with no arrow: "3 kernel SW: only after step 2, empty this frame and reuse it".
- right half, directly under the Core 1 box: a table. Heading: "page table".
  One row: "page 0x416: invalid". Under the table, in small blue letters:
  "drawn after step 1, before step 2".

Exactly five arrows. No arrow crosses another arrow or passes over a box it does not touch.
Each kernel arrow label begins with its step number:
- a kernel arrow from the kernel instance straight down into the DRAM box, to the page table, label "1 set the PTE invalid"
- a kernel arrow from the kernel instance straight up to the TLB of Core 1 box, label "2 clear the entry in its own TLB"
- a kernel arrow from the kernel instance to the left, to the TLB of Core 0 box, label "2 clear it on every other core too"
- an access arrow from the user SW figure straight down to the TLB of Core 0 box, label "page 0x416"
- an access arrow from the TLB of Core 0 box straight down into the DRAM box, to the frame
  icon, label "until step 2 clears it: TLB hit, straight to the frame, no kernel"

The card, at the top of the right third. Heading: "If step 2 skips Core 0".
Three lines: "Core 0 still gets a TLB hit", "it keeps reading and writing the old frame",
"no exception happens, so the kernel cannot stop it".

The sticky note, under the card. Heading: "Changing a PTE: two directions".
Two lines: "invalid to valid: other cores need nothing",
"valid to invalid: clear the entry on every core".

Bottom bar, label "Key point": "Order: set the PTE invalid, clear the entry from every core's TLB, and only then touch the frame."

Text manifest: auto

Do not: write any digit or number that is not quoted; add a third core box; draw a kernel
instance in Core 0 or a figure in Core 1; draw an arrow from a TLB box to the page table;
draw a purple arrow to the frame icon; draw more than five arrows; let two arrows cross;
draw more than one figure; draw a padlock; hatch anything; write any vendor or product
name; rewrite the subtitle or the bottom bar; write any non-English text.
```

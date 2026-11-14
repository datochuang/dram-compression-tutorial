# 圖像生成提示詞：two-stage task

**版本**：第一版，2026-11-14。

**對象**：用 `sketchnote-gen` skill 生成這張圖的人，以及讀圖驗收的 agent。

**目的**：讓第一次碰這顆 processor 的團隊看懂這次工作的性質。工作分兩段：
1. 第一段：processor 本來就有 CPU MMU，但團隊沒有裝上、也沒有開啟過。這一段是把 CPU MMU 整合進來、打通、驗證。這是成熟的設計，困難只在團隊不熟。
2. 第二段：有了 CPU MMU 之後，在 page swap 的框架裡加上 LZ4 HW。page 不是 swap 到 disk，而是 swap 到 DRAM 裡壓縮過的空間。

**風格**：`whiteboard`。style block 和 `figures/system-overview/` 相同，顏色的意思也相同。

**內容的來源**：
- 負責人 2026-11-14 的說明。
- 平台前提 P1 到 P4 在專案的 `CLAUDE.md`。照 P1，TLB miss handler 是 kernel SW 的工作，所以列在第一段。
- 「壓縮層是 swap 的變形」對照的是 Linux zram 的做法，見 `reference/` 的研究紀錄。圖上不寫產品名稱。

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
| 1 | `01-two-stages.png` | 這次的工作到底是什麼，難在哪裡？ | 分兩段。第一段把成熟但我們沒用過的 CPU MMU 打通並驗證。第二段沿用 page swap 的框架，只換 swap 的目的地：DRAM 裡壓縮過的空間，由 LZ4 HW 搬。 |

---

## Style block（每張都先貼這段）

```
Hand-drawn engineering whiteboard sheet, the kind an engineer draws to walk a colleague
through a plan, tidy and uncrowded. Aspect ratio 3:2, landscape. Plain white background.
Black marker line art with slightly wobbly strokes. Hand-lettered English text, small but
clean and fully legible.

Named objects: whenever the prompt says 'the <object>', draw the same object every time.
- a panel: a large rounded rectangle with a black outline and a plain white fill. Its
  quoted name is lettered in bold at its top-left corner, inside.
- a core box: a rounded rectangle with a black outline and a plain white fill. Its quoted
  name is lettered in bold at its top-left corner, inside.
- a CPU hardware box: a rectangle with a light blue fill and a black outline, holding only
  its quoted lines, the first line in bold.
- a kernel instance: a small rounded rectangle with a dashed purple outline and a plain
  white fill, holding only its quoted lines, the first line in bold.
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
- a card: a rounded rectangle with a black outline and a plain white fill, a bold heading
  and the quoted lines under it, one per row, each row starting with a small check box.
- a sticky note: a pale yellow sticky note with a bold heading and the quoted lines under
  it, one per row.
- a tag: a small rounded label with a thick black outline, its quoted text in bold capitals.
- the user SW figure: a round-headed stick figure sitting at a small laptop.
- Hatching: light diagonal hatching always means compressed data and appears nowhere else.

Color rules: orange for access arrows and the title underline; purple for kernel instances
and kernel arrows; green for hardware arrows; light blue fill only for CPU hardware boxes;
light green fill only for the LZ4 HW box; pale yellow only for sticky notes; blue for the
subtitle line and small notes; all other lines and text black. No gradients, no photo
textures, no logos, no watermarks.

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
Subtitle (blue): "First bring up the CPU MMU this processor already has. Then add compression inside page swap."

Layout: two panels of the same size side by side, the left one and the right one, with a
gap between them. In the gap, one thick black arrow pointing from the left panel to the
right panel, labeled in small black letters above it: "builds on". Then the bottom bar
across the full width.

The left panel, named "Stage 1: bring up the CPU MMU". At its top-right corner, inside, a
tag: "MATURE DESIGN, NEW TO US". The panel has three parts from top to bottom.

Top part of the left panel, a small sketch:
- one core box named "processor". Inside it: at the left, the user SW figure labeled
  "user SW"; at the right, a kernel instance: "kernel SW", "TLB miss handler, page fault";
  in the middle under them, one CPU hardware box: "CPU MMU and TLB", "in the chip, never turned on yet".
- under the core box, one DRAM box named "DRAM" holding three frame icons in a row and,
  to their right, a small table outline with the label "page table".
- exactly three arrows in this sketch:
  - an access arrow from the user SW figure to the CPU MMU and TLB box, label "every access"
  - a kernel arrow from the kernel instance to the CPU MMU and TLB box, label "fills the TLB"
  - a kernel arrow from the kernel instance down to the page table, label "reads and writes PTEs"

Middle part of the left panel, a card. Heading: "Our work". Four lines:
"integrate the CPU MMU hardware into our system",
"kernel SW: page table, TLB miss handler, page fault",
"clear a page from every core's TLB",
"tests: every access reaches the right frame".

Bottom part of the left panel, a sticky note. Heading: "Why we can expect it to work".
Two lines: "the CPU MMU is a proven, mature design",
"the hard part is that it is new to us, not the hardware".

The right panel, named "Stage 2: add compression to page swap". At its top-right corner,
inside, a tag: "KNOWN FRAMEWORK, NEW DESTINATION". The panel has three parts from top to
bottom.

Top part of the right panel, a small sketch:
- at the top-left, a kernel instance: "kernel SW", "page swap: page out, page back in".
- at the top-right, the disk icon with the small blue label under it:
  "classic page swap sends pages here". No arrow touches the disk icon.
- under the kernel instance, the LZ4 HW box: "LZ4 HW", "compresses and decompresses pages".
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

Bottom part of the right panel, a sticky note. Heading: "What stays the same".
Two lines: "page fault, page out, page back in: the page swap flow",
"only the destination changes: compressed DRAM, not disk".

Bottom bar, label "Key point": "Stage 1 turns on a mature CPU MMU that we have not used before. Stage 2 keeps the page swap framework and changes only where pages go: compressed space in DRAM, moved by LZ4 HW."

Text manifest: auto

Do not: write any digit or number that is not quoted, apart from the badge; draw any arrow
to or from the disk icon; draw the LZ4 HW box in the left panel; hatch anything in the
left panel; hatch a frame icon; add a third panel; draw more than one figure; draw more
than seven arrows in total, counting the thick arrow between the panels; write MMU without
CPU in front of it; write any vendor or product name; rewrite the subtitle or the bottom
bar; write any non-English text.
```

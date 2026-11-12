# 圖像生成提示詞（第二版）：Kernel SW actions, scenario by scenario

**對象**：用 `sketchnote-gen` skill 生成這組圖的人，以及讀圖驗收的 agent。
**目的**：讓要寫或審 kernel SW 的工程師，一個場景一張圖，看到 kernel 依序做了什麼、哪幾步拿著 `mm_lock`、哪一段交給 LZ4 HW、page 的資料最後在哪裡。
**風格**：`whiteboard`（和 `figures/page-states/` 同一種；範例 /Users/sherrachen/.claude/skills/sketch-style-pick/assets/samples/whiteboard.png）。
**約束**：圖上文字全部英文；步驟的內容與順序照 `sim/hostsim/deps.py` 的 `CASES`（和 `kernel.py` 的執行紀錄對過）；每一步標明是 CPU、kernel 還是 LZ4 HW；壓縮資料畫斜線；不寫時間數字（那些是假設值）；數字只有徽章、步驟編號與 7 個 chunk；不出現廠商或產品名稱。
**怎麼用**：skill 一張一張生，用預設模型與 high 品質；全部生完後做一次只給圖的冷讀，不過的重生；通過的存成本資料夾 `NN-<name>.png`。文字清單由雙引號字串自動產生。建立日期 2026-11-12。第一版留在 `prompts-v1.md`；第二版照 gen1 的冷讀改了第 1、2、4、5、6、7 張的文字，第 3 張沒有改。

## 脊椎

| # | 檔名 | 讀者的問題 | 主張 | 對應 `deps.CASES` |
|---|------|------|------|------|
| 1 | `01-scenario-map.png` | kernel 什麼時候會動？一共有哪些場景？ | 只有兩個起因：page fault，或 free frame 太少。page 的狀態與 RO、RW 決定走哪一個場景，一共八個。 | 全部 |
| 2 | `02-first-touch.png` | 第一次碰一個 RW page 時 kernel 做什麼？ | 全部是 kernel 的事：拿一次 `mm_lock`，給一個填零的 frame，沒有 LZ4 job。 | `first_touch` |
| 3 | `03-fault-decompress.png` | 碰到已壓縮的 page 時 kernel 做什麼？ | 一個 DECOMPRESS job 夾在兩段短的 `mm_lock` 之間；LZ4 HW 工作時不拿 lock。 | `fault_rw`、`fault_ro` |
| 4 | `04-fault-hw-fails.png` | LZ4 HW 沒把 page 交出來怎麼辦？ | kernel 用自己的 decoder 再解一次；只有存放的 stream 本身壞了，page 才遺失。 | `fault_rescue`、`fault_lost` |
| 5 | `05-evict-ro.png` | reclaimer 怎麼趕出一個 RO page？ | 只是記帳：chunk 裡本來就有這個 page，frame 直接還回去，沒有 LZ4 job。 | `evict_ro` |
| 6 | `06-evict-rw.png` | reclaimer 怎麼趕出一個 RW page？ | 要等 chunk 存好、COT entry 記好，frame 才還回去。 | `evict_rw` |
| 7 | `07-evict-incompressible.png` | 壓不進去的 page 怎麼辦？ | 白做一個 job；kernel 把一切還原，之後不再選這個 page。 | `evict_rw_incompressible` |

---

## Style block（每張都先貼這段）

```
Hand-drawn engineering whiteboard sketchnote. Aspect ratio 16:9, landscape. Plain white
background. Black marker line art with slightly wobbly strokes. Hand-lettered English text,
clean and legible.

People: round-headed stick figures with simple faces. EVERY figure in the prompt has a
label naming its role, a pose, an expression and usually a prop; draw exactly those. A
figure with no label in the prompt must not appear. Emotion marks are part of the drawing:
sweat drops, a tight spiral scribble over a head for stress, short rays for energy, orange
question marks for doubt, a lit light bulb for an idea. Thought bubbles are cloud-shaped
with small circles as a tail; speech bubbles have a pointed tail aimed at the speaker.
Machines are larger boxy cabinets with one gear drawn on the front and a slot.

Named objects: whenever the prompt says 'the <object>', draw the same object every time.
- the three lanes: three horizontal bands stacked top to bottom, separated by thin grey
  horizontal rules that span the full width. Each lane has exactly one character at its
  far left with its label under it. Time runs from left to right in every lane.
- a step box: a rounded rectangle with a black outline. One orange circle holding the step
  number sits on its top-left corner. Inside is a short list, one line of lettering per
  item, each line starting with a small dash. Nothing else is inside.
- a CPU step box: a step box with a light blue fill.
- a locked step box: a step box with a light grey fill. A small closed padlock icon and
  the tag words given in the prompt sit just above its top edge at the right.
- an unlocked step box: a step box with a white fill. A small open padlock icon and the
  tag words given in the prompt sit just above its top edge at the right.
- a hardware step box: a step box with a light green fill and a small gear icon on its
  top-right corner.
- a recap box: a step box with a white fill and a dashed black outline, no padlock. It
  sums up steps that another sheet shows in full.
- a frame icon: one small plain white square with a black outline, empty, never hatched.
- a chunk icon: three small rectangles side by side, each filled with diagonal hatching.
  Hatching always means compressed data and appears nowhere else.
- the user SW figure: a stick figure sitting at a small laptop.
- the kernel figure: a standing stick figure holding the page state table.
- the page state table: a clipboard with a few ruled lines on it.
- the LZ4 HW machine: a boxy cabinet with one gear on its front and a slot.
- the data strip: one thin full-width strip just above the bottom bar. A bold label at its
  left, then a before cell, one orange arrow pointing right, then an after cell.

Color rules: orange for flow arrows, step number circles and the title underline; blue for
the subtitle line and small annotations; light blue, light grey and light green fills only
for the step boxes as defined above; green only for a check mark the prompt asks for; red
only where the prompt says red; all other lines and text black. No gradients, no photo
textures, no logos, no watermarks.

Fixed layout: a numbered circle badge at the top-left; the title to its right, underlined
in orange; one blue subtitle line under the title; the panels or lanes described in the
prompt; a bottom bar across the full width as described, with its label in a small box at
its left.

Hard limits:
- Render every double-quoted string exactly as written. Correct spelling. No extra words,
  labels, captions or examples anywhere.
- Draw only the panels, lanes, figures and objects listed. Do not add panels, rows, step
  boxes or charts.
- Copy the subtitle and the bottom-bar sentences word for word. Never rewrite them.
- No digits anywhere unless the prompt quotes them. No file names, no code, no vendor,
  product or standard names.
- Flow arrows are orange, each with one clear arrowhead, and connect only the step boxes
  the prompt names, in the order given. No other arrows.
- Keep every scene uncrowded: fewer, larger elements and generous white space. Icons are
  simple line icons with no text inside.
```

## Prompt 1：01-scenario-map

```
Badge: "1"
Title: "Two Triggers, Eight Scenarios"
Subtitle (blue): "The kernel acts when user SW takes a page fault, or when free frames run low"

Layout: two panels side by side, the left one wider, then the bottom bar. Each panel holds
one decision tree that grows from left to right: one root box at the left, branches drawn
as orange arrows with a small black label written on each arrow, and the end boxes stacked
in one column at the right edge of the panel. There are no lanes and no step boxes in this
image. Tree boxes are plain rounded rectangles: white fill for kernel work, light green
fill for a job of the LZ4 HW. Every end box carries a small orange circle with one number
at its right end.

Left panel "Trigger: page fault". At the top-left of the panel the user SW figure, labeled
"user SW", one hand on the laptop, mildly surprised. Root box: "kernel: read the page state".
Two arrows leave the root:
- arrow labeled "untouched" to the end box "first touch: a frame of zeros", circle "2".
  Beside this end box a small blue annotation: "no LZ4 job".
- arrow labeled "compressed" to a light green box "LZ4 HW: DECOMPRESS job".
Three arrows leave the light green box:
- arrow labeled "OK, RO page" to the end box "page is back, chunks stay", circle "3"
- arrow labeled "OK, RW page" to the end box "page is back, chunks given back", circle "3"
- arrow labeled "HW fails" to a white box "kernel: decode the stream itself".
Two arrows leave that white box:
- arrow labeled "decoded" to the end box "page is back", circle "4"
- arrow labeled "stream damaged" to an end box with a red outline: "page is lost, user program ended", circle "4"
The left panel therefore has exactly five end boxes, top to bottom: first touch, chunks
stay, chunks given back, page is back, page is lost.

Right panel "Trigger: few free frames". At the top-left of the panel the kernel figure,
labeled "kernel: reclaimer thread", calm, holding the page state table, which is labeled "page state table", in one hand and a
small broom in the other. Root box: "kernel: clock scan picks a victim page".
Two arrows leave the root:
- arrow labeled "RO page" to the end box "drop the frame, the chunks already hold it",
  circle "5". Beside this end box a small blue annotation: "no LZ4 job".
- arrow labeled "RW page" to a light green box "LZ4 HW: COMPRESS job".
Two arrows leave the light green box:
- arrow labeled "OK" to the end box "chunks hold the page, frame freed", circle "6"
- arrow labeled "INCOMPRESSIBLE" to the end box "page stays in its frame", circle "7"
The right panel therefore has exactly three end boxes.

One small blue annotation at the bottom of the left panel: "orange circle: the sheet that shows this scenario step by step".

One small blue annotation under the title of the right panel: "woken by a page fault that leaves few free frames".

Bottom bar, label "Key takeaway": "Two triggers only: a page fault, or too few free frames. The page's state, its RO or RW kind and the answer of the LZ4 HW pick the scenario."

Text manifest: auto

Do not: write any digit other than the quoted ones; draw any figure other than the user SW
and the kernel reclaimer thread; draw the LZ4 HW as a machine in this image; add a ninth
end box; add a branch that is not listed; draw an arrow between the two panels; add a
legend or a chart; write any vendor or product name; rewrite the subtitle or the
takeaway; write any non-English text.
```

## Prompt 2：02-first-touch

```
Badge: "2"
Title: "First Touch of an RW Page"
Subtitle (blue): "Nobody has written this page yet, so there is nothing to decompress"

Layout: the three lanes take most of the image; under them the data strip; then the bottom
bar. The middle lane is the tallest.

Top lane. At the far left the user SW figure, labeled "user SW", relaxed, typing. Two CPU
step boxes in this lane:
- step "1", left of center: "user SW touches the page", "CPU MMU: PTE is invalid", "CPU: page fault exception"
- step "3", at the far right: "CPU: return from exception", "CPU: the instruction runs again"

Middle lane. At the far left the kernel figure, labeled "kernel: page fault handler", calm,
holding the page state table, which is labeled "page state table". One wide locked step
box in the center of the lane, step "2", with the tag words "mm_lock held":
"page state is untouched", "take a free frame", "fill the frame with zeros",
"state = present, make PTE valid", "keep the page safe from the reclaimer",
"few free frames left? wake the reclaimer".
One small blue annotation under this box: "no free frame? wake the reclaimer, let the lock go and wait".

Bottom lane. At the far left the LZ4 HW machine, labeled "LZ4 HW", idle, drawn with a grey
outline. There is no step box in this lane. One blue annotation in the middle of the lane:
"no job in this scenario".

Flow arrows: exactly two. From step 1 down to step 2; from step 2 up to step 3.

The data strip, label "The page's data": before cell: the word "before:" then the text
"nowhere, it reads as zeros". After cell: the word "after:" then a frame icon and the text
"a frame of zeros".

Bottom bar, label "Key takeaway": "A first touch is kernel work only: one mm_lock hold, a frame of zeros, no LZ4 job."

Text manifest: auto

Do not: write any digit other than the quoted ones; draw any figure other than the user
SW, the kernel page fault handler and the LZ4 HW machine; put a step box in the bottom
lane; add a fourth step box; draw a chunk icon; add an arrow to or from the LZ4 HW
machine; add a legend or a chart; write any vendor or product name; rewrite the subtitle
or the takeaway; write any non-English text.
```

## Prompt 3：03-fault-decompress

```
Badge: "3"
Title: "Page Fault on a Compressed Page"
Subtitle (blue): "The kernel holds mm_lock twice and lets it go while the LZ4 HW decompresses"

Layout: the three lanes take most of the image; under them the data strip; then the bottom
bar. The middle lane is the tallest.

Top lane. At the far left the user SW figure, labeled "user SW", relaxed, typing. Two CPU
step boxes in this lane:
- step "1", near the left: "user SW touches the page", "CPU MMU: PTE is invalid", "CPU: page fault exception"
- step "7", at the far right: "CPU: return from exception", "CPU: the instruction runs again"

Middle lane. At the far left the kernel figure, labeled "kernel: page fault handler", calm,
holding the page state table, which is labeled "page state table". Four step boxes on one
horizontal line, in this order from left to right:
- step "2", a locked step box with the tag words "mm_lock held": "page state is compressed", "take a free frame", "read the COT entry", "state = decompressing"
- step "3", an unlocked step box with the tag words "no lock": "build the job descriptor", "write the job ring", "ring the doorbell"
- step "5", an unlocked step box with the tag words "no lock": "read the completion, check the tag", "cache invalidate the frame"
- step "6", a locked step box with the tag words "mm_lock held": "RW page: clear the COT entry, give the chunks back", "state = present, make PTE valid", "wake other threads waiting for this page", "keep the page safe from the reclaimer"
One small blue annotation under step 6: "RO page: its chunks stay".

Bottom lane. At the far left the LZ4 HW machine, labeled "LZ4 HW", busy, its gear turning
with short rays. One hardware step box, step "4", placed under the gap between step 3 and
step 5: "DECOMPRESS: chunks into the frame", "write the completion", "raise the interrupt".

Flow arrows: exactly six. Step 1 down to step 2; step 2 right to step 3; step 3 down to
step 4; step 4 up to step 5; step 5 right to step 6; step 6 up to step 7.

The data strip, label "The page's data": before cell: the word "before:" then a chunk icon
and the text "chunks". After cell: the word "after:" then a frame icon and the text
"a frame".

Bottom bar, label "Key takeaway": "One DECOMPRESS job sits between two short mm_lock holds; the lock is not held while the LZ4 HW works."

Text manifest: auto

Do not: write any digit other than the quoted ones; draw any figure other than the user
SW, the kernel page fault handler and the LZ4 HW machine; add an eighth step box; put a
padlock on step 1, step 4 or step 7; hatch a frame icon; add an arrow beyond the six
listed; add a legend or a chart; write any vendor or product name; rewrite the subtitle
or the takeaway; write any non-English text.
```

## Prompt 4：04-fault-hw-fails

```
Badge: "4"
Title: "When the LZ4 HW Does Not Deliver the Page"
Subtitle (blue): "The kernel decodes the stored stream itself; the page is lost only if that fails too"

Layout: the three lanes take most of the image, then the bottom bar. There is no data
strip in this image. The middle lane is the tallest: its right half splits into an upper
row and a lower row.

Top lane. At the far left the user SW figure, labeled "user SW", waiting, worried, with a
thought bubble: "where is my page?". One CPU step box at the far right of this lane,
step "6a": "CPU: return from exception", "CPU: the instruction runs again". A green check
mark beside it.

Middle lane. At the far left the kernel figure, labeled "kernel: page fault handler",
focused, with a calm serious face, holding the page state table, which is labeled "page state table". From left to right:
- step "1", a recap box: "same start as sheet 3", "lock held: state = decompressing", "lock dropped: DECOMPRESS job sent"
- step "3", an unlocked step box with the tag words "no lock": "cache invalidate the frame", "read the chunks, check the CRC", "run the kernel's own decoder"
- right after step 3 a small orange diamond holding the word "decoded?". Two orange arrows
  leave the diamond: one labeled "yes" to the upper row, one labeled "no: stream damaged" to the lower row.
Upper row, left to right:
- step "4a", an unlocked step box with the tag words "no lock": "CPU writes the decoded page into the frame", "cache clean the frame"
- step "5a", a locked step box with the tag words "mm_lock held": "count a strike against the LZ4 HW", "RW page: clear the COT entry, give the chunks back", "state = present, make PTE valid", "wake other threads waiting for this page"
Lower row, left to right:
- step "4b", a locked step box with the tag words "mm_lock held": "frame back to the free list", "state = lost", "wake other threads waiting for this page"
- step "5b", a step box with a white fill and a red outline, no padlock: "end the user program". A red cross beside it.
One small blue annotation at the right end of the lower row: "three strikes in a row, or one missing completion: the kernel stops using the LZ4 HW".

Bottom lane. At the far left the LZ4 HW machine, labeled "LZ4 HW", with a red cross over
its slot and a small puff of smoke. One hardware step box, step "2", placed under the gap
between step 1 and step 3: "status BAD_STREAM or BUS_ERROR", "or no completion before the timeout".

Flow arrows: step 1 down to step 2; step 2 up to step 3; step 3 right to the diamond; the
diamond's yes arrow to step 4a; step 4a right to step 5a; step 5a up to step 6a; the
diamond's no arrow to step 4b; step 4b right to step 5b. No other arrows.

Bottom bar, label "Key takeaway": "A failing LZ4 HW alone loses no data: the page is lost only when the stored stream itself is damaged."

Text manifest: auto

Do not: write any digit other than the quoted ones; draw any figure other than the user
SW, the kernel page fault handler and the LZ4 HW machine; add a step box that is not
listed; draw an arrow from step 5b to the top lane; draw an arrow straight from step 1 to step 3; draw a frame icon or a chunk icon;
draw more than one diamond; add a legend or a chart; write any vendor or product name;
rewrite the subtitle or the takeaway; write any non-English text.
```

## Prompt 5：05-evict-ro

```
Badge: "5"
Title: "Reclaimer Evicts an RO Page"
Subtitle (blue): "The compressed copy never left the chunk pool, so the kernel just drops the frame"

Layout: the three lanes take most of the image; under them the data strip; then the bottom
bar. The middle lane is the tallest.

Top lane. At the far left the user SW figure, labeled "user SW", relaxed, typing, not
looking at the kernel. Two CPU step boxes in this lane:
- step "1", near the left: "user SW takes a page fault", "the kernel's page fault handler sees few free frames", "the handler wakes the reclaimer"
- step "3", at the far right: "the next page fault of user SW finds a free frame"
One small blue annotation in the middle of the top lane, between the two boxes:
"user SW touches this page again? page fault, DECOMPRESS from the same chunks".

Middle lane. At the far left the kernel figure, labeled "kernel: reclaimer thread", calm,
holding the page state table, which is labeled "page state table", in one hand and a small
broom in the other. One wide locked
step box in the center of the lane, step "2", with the tag words "mm_lock held":
"clock scan: pick a victim page", "the victim is an RO page", "make PTE invalid",
"TLB invalidate on all cores", "frame back to the free list", "state = compressed".
Under this box one curved orange loop arrow that leaves the box at its right end and
comes back into it at its left end, with the label: "more frames needed? next victim, same lock hold".

Bottom lane. At the far left the LZ4 HW machine, labeled "LZ4 HW", idle, drawn with a grey
outline. There is no step box in this lane. One blue annotation in the middle of the lane:
"no job: the chunks already hold this page".

Flow arrows: exactly two straight ones, plus the loop arrow. From step 1 down to step 2;
from step 2 up to step 3.

The data strip, label "The page's data": before cell: the word "before:" then a frame icon,
a chunk icon and the text "a frame and chunks". After cell: the word "after:" then a chunk
icon and the text "chunks only".

Bottom bar, label "Key takeaway": "Evicting an RO page is bookkeeping only: the chunks already hold it, so the frame is freed without any LZ4 job."

Text manifest: auto

Do not: write any digit other than the quoted ones; draw any figure other than the user
SW, the kernel reclaimer thread and the LZ4 HW machine; put a step box in the bottom lane;
add a fourth step box; add an arrow to or from the LZ4 HW machine; hatch a frame icon;
add a legend or a chart; write any vendor or product name; rewrite the subtitle or the
takeaway; write any non-English text.
```

## Prompt 6：06-evict-rw

```
Badge: "6"
Title: "Reclaimer Evicts an RW Page"
Subtitle (blue): "The frame is the only copy, so the LZ4 HW must compress it into chunks before the frame is freed"

Layout: the three lanes take most of the image; under them the data strip; then the bottom
bar. The middle lane is the tallest.

Top lane. At the far left the user SW figure, labeled "user SW", relaxed, typing, not
looking at the kernel. Two CPU step boxes in this lane:
- step "1", near the left: "user SW takes a page fault", "the kernel's page fault handler sees few free frames", "the handler wakes the reclaimer"
- step "7", at the far right: "the next page fault of user SW finds a free frame"
One small blue annotation in the middle of the top lane, between the two boxes:
"user SW touches this page during the job? page fault, then it waits".

Middle lane. At the far left the kernel figure, labeled "kernel: reclaimer thread", calm,
holding the page state table, which is labeled "page state table", in one hand and a small
broom in the other. Four step boxes
on one horizontal line, in this order from left to right:
- step "2", a locked step box with the tag words "mm_lock held": "clock scan: pick a victim page", "the victim is an RW page", "reserve 7 chunks, the most a stored page may use", "make PTE invalid", "TLB invalidate on all cores", "state = compressing"
- step "3", an unlocked step box with the tag words "no lock": "cache clean the frame", "build the job descriptor", "write the job ring, ring the doorbell"
- step "5", an unlocked step box with the tag words "no lock": "read the completion, check the tag"
- step "6", a locked step box with the tag words "mm_lock held": "write the COT entry", "give the unused chunks back", "frame back to the free list", "state = compressed", "wake other threads waiting for this page"

Bottom lane. At the far left the LZ4 HW machine, labeled "LZ4 HW", busy, its gear turning
with short rays. One hardware step box, step "4", placed under the gap between step 3 and
step 5: "COMPRESS: the frame into chunks", "write the completion", "raise the interrupt".

Flow arrows: exactly six. Step 1 down to step 2; step 2 right to step 3; step 3 down to
step 4; step 4 up to step 5; step 5 right to step 6; step 6 up to step 7.

The data strip, label "The page's data": before cell: the word "before:" then a frame icon
and the text "a frame". After cell: the word "after:" then a chunk icon and the text
"chunks".

Bottom bar, label "Key takeaway": "An RW frame is freed only after the chunks hold the page and the COT entry records them."

Text manifest: auto

Do not: write any digit other than the quoted ones; draw any figure other than the user
SW, the kernel reclaimer thread and the LZ4 HW machine; add an eighth step box; put a
padlock on step 1, step 4 or step 7; hatch a frame icon; add an arrow beyond the six
listed; draw an arrow straight from step 3 to step 5; add a legend or a chart; write any
vendor or product name; rewrite the subtitle or the takeaway; write any non-English text.
```

## Prompt 7：07-evict-incompressible

```
Badge: "7"
Title: "An RW Page That Does Not Compress"
Subtitle (blue): "The LZ4 HW answers INCOMPRESSIBLE and the kernel undoes the eviction"

Layout: the three lanes take most of the image; under them the data strip; then the bottom
bar. The middle lane is the tallest.

Top lane. At the far left the user SW figure, labeled "user SW", relaxed, typing, not
looking at the kernel. One CPU step box at the far right of this lane, step "5":
"user SW keeps its page", "no frame was freed".

Middle lane. At the far left the kernel figure, labeled "kernel: reclaimer thread",
slightly annoyed, one sweat drop, holding the page state table, which is labeled
"page state table", in one hand and a small broom in the other. Three step boxes on one horizontal line, in this order from left to
right:
- step "1", a recap box: "same start as sheet 6", "lock held: 7 chunks reserved, state = compressing", "lock dropped: COMPRESS job sent"
- step "3", an unlocked step box with the tag words "no lock": "read the completion, check the tag"
- step "4", a locked step box with the tag words "mm_lock held": "give all 7 chunks back", "remember: this page is incompressible", "state = present, make PTE valid again", "wake other threads waiting for this page"
One small blue annotation under step 4: "the clock scan skips this page from now on".

Bottom lane. At the far left the LZ4 HW machine, labeled "LZ4 HW", working normally, its gear
turning with short rays. One hardware step box, step "2", placed under the gap between
step 1 and step 3: "COMPRESS: the page does not fit in 7 chunks", "status INCOMPRESSIBLE", "raise the interrupt".

Flow arrows: exactly four. Step 1 down to step 2; step 2 up to step 3; step 3 right to
step 4; step 4 up to step 5.

The data strip, label "The page's data": before cell: the word "before:" then a frame icon
and the text "a frame". After cell: the word "after:" then a frame icon and the text
"the same frame".

Bottom bar, label "Key takeaway": "A page that does not fit costs one wasted job: the kernel puts everything back and does not pick that page again."

Text manifest: auto

Do not: write any digit other than the quoted ones; draw any figure other than the user
SW, the kernel reclaimer thread and the LZ4 HW machine; add a sixth step box; put a
padlock on step 1, step 2 or step 5; draw a chunk icon; hatch a frame icon; add an arrow
beyond the four listed; add a legend or a chart; write any vendor or product name;
rewrite the subtitle or the takeaway; write any non-English text.
```

---

## 驗收 checklist

1. 圖上每個字都在文字清單裡，清單裡的每個字都在圖上；拼字正確。
2. 徽章、標題、橘色底線、藍色副標、底部結論都在；副標與結論逐字一致。
3. 數字只有徽章、步驟編號與 7 個 chunk；沒有時間數字；沒有廠商或產品名稱。
4. 步驟編號的順序與 prompt 一致，每個 step box 在正確的 lane：CPU 的在上、kernel 的在中、LZ4 HW 的在下。
5. 拿著 `mm_lock` 的 step box 是灰底加關著的鎖與 `mm_lock held`；沒拿的是白底加開著的鎖與 `no lock`；CPU 與 LZ4 HW 的 step box 沒有鎖。
6. 橘色箭頭照編號一個接一個，方向正確，沒有多的箭頭。
7. chunk icon 有斜線，frame icon 沒有；data strip 的 before 與 after 內容正確。
8. 每個人物與機器都有標籤：`user SW`、`kernel: page fault handler` 或 `kernel: reclaimer thread`、`LZ4 HW`；kernel 拿著 page state table。
9. 畫面的意思和結論一致：先遮住結論看圖，說出圖講的一句，再對結論。
10. 冷讀驗收：全部生完後派一個只拿圖的 subagent 冷讀；困惑指數 3 以上、角色不清、箭頭方向與故事相反的張重生。
11. 整組風格一致；第 1 張的橘色圓圈號碼對得到第 2 到第 7 張的徽章。

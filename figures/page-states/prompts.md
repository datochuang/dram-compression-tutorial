# 圖像生成提示詞（第一版）：Page states with LZ4

**對象**：用 `sketchnote-gen` skill 生成這張圖的人，以及讀圖驗收的 agent。
**目的**：讓第一次看這個 proposal 的工程師知道，加了 LZ4 之後一個 page 有六種狀態，而 CPU 的 MMU 看到的仍然只有 valid 與 invalid。
**風格**：`whiteboard`（使用者指定白板工程圖；範例 /Users/sherrachen/.claude/skills/sketch-style-pick/assets/samples/whiteboard.png）。
**約束**：圖上文字全部英文；狀態名稱、status 名稱照 `sim/lz4sim/kernel.py` 與介面規格的用字；每個轉換標明是 kernel 還是 LZ4 HW；壓縮資料畫斜線；除了徽章不寫數字；不出現廠商或產品名稱。
**怎麼用**：skill 一張一張生，用預設模型與 high 品質；生完後做一次只給圖的冷讀，不過的重生；通過的存成本資料夾 `NN-<name>.png`。文字清單由雙引號字串自動產生。建立日期 2026-11-11。

## 脊椎

| # | 檔名 | 讀者的問題 | 主張 |
|---|------|------|------|
| 0 | `00-page-states.png` | 沒有 LZ4 時 page 只有 valid 與 invalid，加了 LZ4 之後有哪些狀態？ | 狀態多在 kernel 這一邊：MMU 仍然只看到兩種值，只有 present 是 valid，其餘五種靠 kernel 的 page state table 分辨。 |

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
Robots are small, boxy, friendly, with a short antenna. Machines are larger boxy cabinets
with one gear drawn on the front and a slot.

Named objects: whenever the prompt says 'the <object>', draw the same object every time.
- a state box: a rounded rectangle with a black outline holding exactly one state name in
  bold and nothing else. All state boxes are the same size.
- a valid tag: a small pill shape with a green outline, a light green fill, one word and a
  small green check mark.
- an invalid tag: a small pill shape with a grey outline, a light grey fill and one word.
- a frame icon: one small plain white square with a black outline, empty, never hatched.
- a chunk icon: three small rectangles side by side, each filled with diagonal hatching.
  Hatching always means compressed data and appears nowhere else.
- the page state table: a clipboard held by the kernel figure, with a few ruled lines on it.

Color rules: orange for flow arrows, rays and the title underline; blue for the subtitle
line and small annotations; green only for a valid tag; red only where the prompt says red;
grey tints only where named; all other lines and text black. No gradients, no photo
textures, no logos, no watermarks.

Fixed layout: a numbered circle badge at the top-left; the title to its right, underlined
in orange; one blue subtitle line under the title; the panels described in the prompt; a
bottom bar across the full width as described, with its label in a small box at its left.

Hard limits:
- Render every double-quoted string exactly as written. Correct spelling. No extra words,
  labels, captions or examples anywhere.
- Draw only the panels, figures and objects listed. Do not add panels, rows or charts.
- Copy the subtitle and the bottom-bar sentences word for word. Never rewrite them.
- No digits anywhere unless the prompt quotes them. No file names, no code, no vendor,
  product or standard names.
- Keep every scene uncrowded: fewer, larger elements and generous white space. Icons are
  simple line icons with no text inside.
```

## Prompt 0：00-page-states

```
Badge: "1"
Title: "One Page, Six States"
Subtitle (blue): "The MMU still sees only valid or invalid; the kernel's page state table tells the invalid ones apart"

Layout: one thin full-width panel on top, one tall full-width panel under it that takes most
of the image, then the bottom bar.

Top panel "Without LZ4", a single thin strip. At its left two state boxes side by side: "valid"
then "invalid", with no arrow between them. To their right one blue annotation: "Two states. The PTE says it all."

Main panel "With LZ4". It is a grid: one narrow label column at the left, then six equal
columns. The grid has four rows. Everything in a column is about the state box at the top of
that column, and each cell is centered under that state box.

Row one, the state row. In the label column: a stick figure labeled "kernel", standing calm,
holding the page state table, which is labeled "page state table", and pointing at the row
with the other hand. In the six columns, six state boxes on one horizontal line, in this
order from left to right: "untouched", "present", "compressing", "compressed",
"decompressing", "lost". The box "lost" has a red outline.

Arrows of the state row. There are exactly eight arrows, all orange, each with one clear
arrowhead and one label in small black lettering placed beside its own arrow.
Five short straight arrows, each from one state box to its right neighbour, labels written
just above the arrow:
- from "untouched" to "present": "kernel: first touch"
- from "present" to "compressing": "kernel: reclaim RW, send COMPRESS"
- from "compressing" to "compressed": "LZ4 HW: COMPRESS OK"
- from "compressed" to "decompressing": "kernel: page fault, send DECOMPRESS"
- from "decompressing" to "lost": "LZ4 HW: BAD_STREAM"
Two curved arrows above the state row, clear of the labels of the straight arrows:
- a lower arc that leaves the top of "present", passes over "compressing" and lands on the top
  of "compressed", pointing right: "kernel: reclaim RO, no job"
- a higher arc that leaves the top of "decompressing", passes over "compressed" and
  "compressing", and lands on the top of "present", pointing left: "LZ4 HW: DECOMPRESS OK"
One curved arrow below the state row, from the bottom of "compressing" back to the bottom of
"present", pointing left: "LZ4 HW: INCOMPRESSIBLE"
Two small blue annotations just under the state row, each with a short blue tick pointing up
at its box: under "untouched": "RW pages start here"; under "compressed": "RO pages start here".

Row two. In the label column: a robot labeled "MMU in the CPU", holding a tiny card in each
hand, with a speech bubble "I only see two values", and the bold row label "MMU sees". In
the six columns, one tag per column: under "present" a valid tag with the word "valid"; under
each of the other five state boxes an invalid tag with the word "invalid".

Row three. In the label column only the bold row label "Data is in", no figure. In the six
columns, one short text per cell:
- under "untouched": "nowhere, reads as zeros"
- under "present": a frame icon and "a frame"
- under "compressing": a frame icon and "a frame, LZ4 HW reads it"
- under "compressed": a chunk icon and "chunks"
- under "decompressing": a chunk icon and "chunks, LZ4 HW writes a frame"
- under "lost": "no good copy"

Row four. In the label column: a stick figure labeled "user SW", sitting at a small laptop,
relaxed, one hand reaching toward the row, and the bold row label "On access". In the six
columns, one short text per cell:
- under "untouched": "page fault: kernel zeroes a frame"
- under "present": "direct, kernel not involved"
- under "compressing": "page fault: CPU waits for the job"
- under "compressed": "page fault: kernel sends DECOMPRESS"
- under "decompressing": "page fault: CPU waits for the job"
- under "lost": "page fault: kernel kills this user SW"

Thin grey horizontal rules separate the four rows. No vertical rules.

Bottom bar, label "Key takeaway": "LZ4 adds states in the kernel, not in the MMU: only present is valid, and the page state table tells the other five apart."

Text manifest: auto

Do not: write any digit other than the quoted ones; draw any figure other than the kernel,
the MMU robot and the user SW; add a seventh state box; add any arrow beyond the eight listed;
draw any arrow that leaves "lost" or enters "untouched"; draw more than one valid tag; hatch a
frame icon; add a legend, a chart or a next-cloud; write any vendor or product name; rewrite
the subtitle or the takeaway; write any non-English text.
```

---

## 驗收 checklist

1. 圖上每個字都在文字清單裡，清單裡的每個字都在圖上；拼字正確。
2. 徽章、標題、橘色底線、藍色副標、底部結論都在；副標與結論逐字一致。
3. 除了徽章與 LZ4 的 4 沒有數字；沒有廠商或產品名稱。
4. 六個 state box 順序正確：untouched、present、compressing、compressed、decompressing、lost；lost 是紅框。
5. 剛好八個箭頭，方向正確：五個向右的直線、present 到 compressed 的弧線向右、decompressing 到 present 的弧線向左、compressing 到 present 的弧線向左。沒有箭頭離開 lost 或進入 untouched。
6. 每個箭頭的標籤以 kernel 或 LZ4 HW 開頭，且貼在自己的箭頭旁。
7. MMU sees 那一列只有 present 底下是 valid，其餘五個是 invalid。
8. Data is in 與 On access 兩列的六格內容對到正確的 state；chunk icon 有斜線，frame icon 沒有。
9. 三個角色都有標籤：kernel 拿著 page state table，MMU in the CPU 是機器人，user SW 在 On access 那一列。
10. 畫面的意思和結論一致：先遮住結論看圖，說出圖講的一句，再對結論。
11. 冷讀驗收：派一個只拿圖的 subagent 冷讀；困惑指數 3 以上或角色不清就重生。

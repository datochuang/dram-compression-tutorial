# 圖像生成提示詞（第三版，英文圖）：SoC DRAM compression for capacity

**第三版修改**：使用者要求圖上文字全部改成英文（中文版留在 `prompts-v2-zh.md`）。內容沿用第二版的修正：結論改為「差別在資料變大時由誰處理，實體用完時都要 OS 參與」；流程列加列標籤；做法 C 的流程接回壓縮層；圖例註明指格子底色；補縮寫說明。

**對象**：用 `sketchnote-gen` skill 生成這組圖的人，以及讀圖驗收的 agent。
**目的**：讓 SoC 架構師比較「省容量、共用單一壓縮層、HRT 不壓縮」前提下的三種做法，並用這張圖確認之後要呈現的技術細節程度。
**風格**：`flat-editorial`（使用者指定；範例 /Users/sherrachen/.claude/skills/sketch-style-pick/assets/samples/flat-editorial.png）。
**約束**：圖上文字全部英文；不出現廠商、產品或論文名稱；不寫程式碼與欄位名；除了徽章與 "512B" 不寫數字；不寫效能數據。
**怎麼用**：skill 一張一張生，用預設模型與 high 品質；全部生完後做一次只給圖的冷讀，不過的重生；通過的存成本資料夾 `NN-<name>.png`。文字清單由雙引號字串自動產生。建立日期 2026-11-06。

## 脊椎

| # | 檔名 | 讀者的問題 | 主張 |
|---|------|------|------|
| 0 | `00-capacity-approaches.png` | HRT 不壓縮、其他資料要省容量時，有哪些做法，差在哪裡？ | HRT 走固定對應；三種做法的差別在資料變大時由誰處理，實體用完時都要 OS 參與。 |
| 1 | `01-how-space-is-saved.png` | 第一次學習的讀者：這三種做法到底怎麼省到空間？ | 空間來自把 page 存得更小，再把空出來的 DRAM 當成額外 page 給 OS；差別在哪些 page 變小、由誰挑選。 |

---

## Style block（每張都先貼這段）

```
Clean editorial flat infographic, the kind used in an annual report or a board deck.
Aspect ratio 16:9, landscape. Plain white background. Crisp geometric shapes with straight
edges and uniform thin dark-navy outlines; no hand-drawn wobble, no sketch texture.
Lettering is a clean humanist sans-serif, dark navy, perfectly legible. All text is English.

People: a figure described as a stick figure is drawn as a simple solid dark-navy human
silhouette (head and shoulders or full body, no face); a figure described as a robot is
drawn as a small square chip icon with four pins on each side and a single dot inside.
EVERY figure in the prompt has a label naming its role; a figure with no label must not
appear. Speech bubbles are rounded rectangles with a small straight tail. Machines are
plain rectangles with one small gear glyph in a corner and a thin slot line.

Named objects: whenever the prompt says 'the <object>', draw the same object every time.
- the compression layer: one wide muted-green rectangle standing between the clients and the
  memory regions; every arrow from a client enters it; no arrow goes around it.
- the uncompressed region: a white rectangle with a navy outline, filled with a neat grid of
  equal-size small squares; never any green inside.
- the compressed region: a muted-green-tinted rectangle with a navy outline, filled with small
  blocks of visibly uneven widths.
- a comparison cell: a flat rectangle holding one short text line. Hardware cells are muted
  green, software cells are light grey, neutral cells are white.
- a memory bar: a horizontal row exactly four equal slots wide, drawn the same size everywhere.
- a full page block: a white rectangle with a solid navy outline, exactly one slot wide.
- a compressed page block: a muted-green rectangle with a solid navy outline, exactly half a
  slot wide.
- a free block: a white rectangle with a dashed mid-grey outline, never any fill.

Categories are always the same tints: light grey for a software thing, muted green for a
hardware thing, in every image.

Color rules: dark navy for all outlines and text; one accent color, muted green, for key
concepts, highlighted boxes, flow arrows, check marks and the title rule; mid grey for
small annotations; no orange, no red, no other hues. Flat fills only: no gradients, no
shadows, no photo textures, no logos, no watermarks.

Fixed layout: a numbered circle badge at the top-left; the title to its right with a thin
green rule under it; one grey subtitle line under the title; the panels described in the
prompt as thin-outlined rectangles with a small panel title at the top-left of each; a
bottom bar across the full width as described, with its label in a small box at its left.

Hard limits:
- Render every double-quoted string exactly as written. Correct spelling. No extra words,
  labels, captions or examples anywhere.
- Draw only the panels, figures and objects listed. Do not add panels, rows or charts.
- Copy the subtitle and the bottom-bar sentence word for word. Never rewrite them.
- No digits anywhere unless the prompt quotes them. No file names, no code, no vendor,
  company or product names.
- Generous white space; fewer, larger elements; icons are simple glyphs with no text inside.
```

## Prompt 0：00-capacity-approaches

```
Badge: "1"
Title: "One Compression Layer, Three Ways to Save Capacity"
Subtitle: "HRT ranges stay uncompressed; the options differ in address mapping and capacity handling"

Layout: one full-width panel on top, three equal-width panels side by side below it, a small
legend line under the three panels, then the bottom bar.

Top panel "Common path", reading left to right in three columns.
Left column, two stacked white boxes: upper box "HRT clients" with a smaller line
"Display, Modem, ISP"; lower box "Other clients" with a smaller line "CPU, GPU, NPU".
Middle column: the compression layer, labeled "Shared compression layer", with a smaller line
inside it "Address range check". One solid dark-navy arrow from the upper client box into it,
one muted-green arrow from the lower client box into it.
Right column, two stacked objects: upper is the uncompressed region, labeled "Uncompressed
region", with a smaller line "Fixed mapping, no metadata lookup"; lower is the compressed
region, labeled "Compressed region", with a smaller line "Managed by one option below".
One solid dark-navy arrow from the compression layer to the uncompressed region, with the
label "HRT range: pass through" on the arrow. One muted-green arrow from the compression layer
to the compressed region, with the label "Other ranges: compress" on the arrow.
One small mid-grey annotation under the middle column: "HRT still needs DRAM QoS: compression
traffic also uses bandwidth".

Each of the three lower panels has the same structure, top to bottom: a panel title; then five
rows, each row having a short bold row label at the left. The first row, labeled "Address
mapping", holds three small white boxes (white fill only, never green or grey) joined left to
right by two green arrows. The other four rows each hold one comparison cell at the right. The
rows line up horizontally across all three panels and are in the same order in each panel.

Panel "Option A: Transparent hardware overcommit"
Flow boxes: "OSPA" then "metadata" then "512B chunks".
Row "Data grows": hardware cell "Use inflation room, then add a chunk"
Row "Physical memory full": software cell "Balloon driver reclaims pages from OS"
Row "OS changes": neutral cell "Small: add balloon driver"
Row "Main cost": neutral cell "Possible extra metadata lookups"

Panel "Option B: Hardware hot/cold tiering"
Flow boxes: "OSPA" then "CTE" then "Hot or cold area".
Row "Data grows": hardware cell "Decompress cold page to hot area on access"
Row "Physical memory full": software cell "Compress more cold pages, then OS reclaims"
Row "OS changes": neutral cell "Small: add reclaim driver"
Row "Main cost": neutral cell "Migration and decompression latency"

Panel "Option C: OS-managed compressed tier"
Flow boxes: "PTE" then "Compressed NUMA node" then "Layer's internal mapping".
Row "Data grows": software cell "Read-only tier; writes move page to DRAM first"
Row "Physical memory full": software cell "Stop demotion, evict aggressively"
Row "OS changes": neutral cell "Large: tiering, faults, reclaim"
Row "Main cost": neutral cell "Less benefit under heavy writes"

Legend line under the three panels, small: at the left a muted-green square followed by
"Green cell: handled by hardware", a light-grey square followed by "Grey cell: handled by OS";
at the right, in mid grey, "OSPA: physical address seen by OS; CTE: compression translation entry".

Bottom bar, label "Key takeaway": "HRT keeps a fixed mapping; the options differ in who handles data growth, and all need the OS when physical memory runs out"

Text manifest: auto

Do not: write any digit other than the quoted ones; draw any person, robot, gear glyph or chart;
draw any arrow that goes around the compression layer; add percentages or performance numbers;
write any paper, vendor or product name; add a recommendation or a winner mark; rewrite the
subtitle or the takeaway; write any non-English text.
```

## Prompt 1：01-how-space-is-saved

```
Badge: "2"
Title: "Where the Saved Space Comes From"
Subtitle: "A smaller page leaves DRAM free, and that free DRAM can hold more pages"

Layout: one full-width panel on top, three equal-width panels side by side below it, a small
legend line under the three panels, then the bottom bar.

Top panel "Basic idea", one row reading left to right:
a full page block labeled "4KB page"; a green arrow labeled "Compress"; a compressed page block
labeled "2KB stored" touching a free block of the same width labeled "2KB free"; a green arrow;
a white box "Free DRAM stores more pages"; a green arrow; a white box "OS sees more memory than
is installed".
One small mid-grey annotation under the row: "Example ratio 2:1. Worse compression leaves less free space."

Each of the three lower panels has the same structure, top to bottom: a panel title, then four
rows, each row having a short bold row label at the left. The rows line up horizontally across
all three panels and are in the same order in each panel. The first two rows, "Before" and
"After", each hold one memory bar. The last two rows, "Who picks" and "OS sees", each hold one
comparison cell.

Panel "Option A: Transparent hardware overcommit"
Row "Before": a memory bar of four full page blocks, each labeled "Page".
Row "After": a memory bar holding four compressed page blocks side by side, each labeled
"Page", filling the left two slots, then one free block two slots wide labeled "Free".
Row "Who picks": hardware cell "Hardware: every page"
Row "OS sees": neutral cell "More pages than installed DRAM"

Panel "Option B: Hardware hot/cold tiering"
Row "Before": a memory bar of four full page blocks labeled, in order, "Hot", "Hot", "Cold", "Cold".
Row "After": a memory bar holding two full page blocks labeled "Hot" and "Hot", then two compressed
page blocks side by side labeled "Cold" and "Cold", filling one slot, then one free block one
slot wide labeled "Free".
Row "Who picks": hardware cell "Hardware: cold pages only"
Row "OS sees": neutral cell "More pages than installed DRAM"

Panel "Option C: OS-managed compressed tier"
Row "Before": a memory bar of four full page blocks labeled, in order, "Hot", "Hot", "Cold", "Cold".
Row "After": a memory bar identical to the After bar of Option B, but with one thick vertical
navy divider at the middle of the bar, a small label "Normal DRAM" above the left half and a small
label "Compressed tier" above the right half.
Row "Who picks": software cell "OS: cold pages only"
Row "OS sees": neutral cell "Extra capacity in a NUMA node"

Legend line under the three panels, small: at the left a small full page block followed by
"Uncompressed page", a small compressed page block followed by "Compressed page", a small free
block followed by "Free DRAM"; at the right, in mid grey, "HRT range not shown: its pages stay full size".

Bottom bar, label "Key takeaway": "Saved space comes from storing pages smaller; the options differ in which pages shrink and who picks them"

Text manifest: auto

Do not: write any digit other than the quoted ones; draw any person, robot, gear glyph or chart;
add arrows inside the lower panels; change the number of slots in a memory bar; add percentages
or performance numbers; write any paper, vendor or product name; add a recommendation or a winner
mark; rewrite the subtitle or the takeaway; write any non-English text.
```

---

## 驗收 checklist

1. 圖上每個字都在文字清單裡，清單裡的每個字都在圖上；拼字正確，沒有非英文文字。
2. 徽章、標題、綠色底線、灰色副標、底部結論都在；副標與結論逐字一致。
3. 除了徽章與 "512B" 沒有數字；沒有廠商、產品或論文名稱；沒有效能數據。
4. 上方一張 panel、下方三張等寬；三張 panel 的五列橫向對齊且順序相同；流程小方塊全為白底。
5. 所有 client 的箭頭都進入同一個壓縮層，沒有箭頭繞過；HRT 路徑是深藍，其他路徑是綠色。
6. 格子顏色正確：A、B 的 "Data grows" 是綠色；C 的 "Data grows" 與三張的 "Physical memory full" 是灰色；其餘白色。
7. 箭頭方向：client → 壓縮層 → 記憶體區；流程小方塊由左到右。
8. 畫面的意思和結論一致：先遮住結論看圖，說出圖講的一句，再對結論。
9. 冷讀驗收：派一個只拿圖的 subagent 冷讀；困惑指數 3 以上或角色不清就重生。

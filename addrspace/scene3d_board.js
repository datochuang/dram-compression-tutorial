/* ---------- the board at the back: symbols, then one PTE, one kernel state and one COT entry per page ---------- */
const board = plate(BW, BH, BPX);
board.mesh.position.copy(B2W(BW / 2, BH / 2)); board.mesh.rotation.x = -(Math.PI / 2 - TILT); scene.add(board.mesh);
const bx = u => u * BPX;
const fnt = (w, u, fam) => w + ' ' + Math.round(u * BPX) + 'px ' + fam;
function txt(g, s, x, y, font, color, align = 'left') { g.font = font; g.fillStyle = color; g.textAlign = align; g.textBaseline = 'alphabetic'; g.fillText(s, x, y); }
function box(g, x, y, w, h, fill, stroke, lw = 2, dash = null) {
  if (fill) { g.fillStyle = fill; g.fillRect(x, y, w, h); }
  if (stroke) { g.strokeStyle = stroke; g.lineWidth = lw; g.setLineDash(dash || []); g.strokeRect(x, y, w, h); g.setLineDash([]); }
}
const symU = s => pageU(SEG[s.seg].first) + (s.addr - SEG[s.seg].base) / PAGE * U;
const tileMid = (p, row) => B2W(pageU(p) + U / 2, (ROW[row + '0'] + ROW[row + '1']) / 2, 0.15);
let boardChanged = [];                           // tiles rewritten in the step on screen: [{ p, row }]

function drawBoard(step, prev) {
  const g = board.g, st = step.st, hl = step.hl || {}, sel = SYM[step.sym], selPages = new Set(sel.slices.map(s => s.p));
  g.fillStyle = P.paper; g.fillRect(0, 0, board.cv.width, board.cv.height);
  box(g, 3, 3, board.cv.width - 6, board.cv.height - 6, null, P.line, 6);
  const head = (v, a, b) => { txt(g, a, bx(3), bx(v), fnt(700, 1.2, DISP), P.ink); const w = g.measureText(a).width; txt(g, b, bx(3) + w + 18, bx(v), fnt(400, 1.05, MONO), P.muted); };

  head(ROW.title, 'LOGICAL ADDRESS SPACE', 'what user SW sees: each symbol is one unbroken range');
  D.symbols.forEach(s => {
    const x = bx(symU(s)), w = bx(s.size / PAGE * U), y = bx(ROW.sym0), h = bx(ROW.sym1 - ROW.sym0), on = s.id === step.sym;
    box(g, x, y, w, h, on ? P[s.kind] : P[s.kind + '_bg'], P[s.kind], 3);
    txt(g, s.id, x + w / 2, y + h * 0.48, fnt(600, 1.35, MONO), on ? P.paper : P.ink, 'center');
    txt(g, (s.size / 1024).toFixed(1) + ' KB', x + w / 2, y + h * 0.82, fnt(400, 1.05, MONO), on ? P.paper : P.muted, 'center');
  });
  txt(g, '···', bx(pageU(SEG.rw.first) - 3), bx(ROW.sym0 + 2.6), fnt(700, 1.4, MONO), P.muted, 'center');
  D.pages.forEach((pg, p) => {
    const x = bx(pageU(p));
    g.strokeStyle = P.muted; g.lineWidth = 2; g.setLineDash([5, 7]);
    [0, U].forEach(d => { g.beginPath(); g.moveTo(x + bx(d), bx(ROW.sym0 - 0.3)); g.lineTo(x + bx(d), bx(ROW.sym1 + 0.35)); g.stroke(); });
    g.setLineDash([]);
    txt(g, 'page ' + pgNo(p) + ' ' + pg.kind.toUpperCase(), x + bx(U / 2), bx(ROW.pg), fnt(selPages.has(p) ? 600 : 400, 1.12, MONO), selPages.has(p) ? P.ink : P.muted, 'center');
  });

  // the pin: where this access lands in the logical view
  if (step.pin) {
    const fault = step.pin.fault, col = fault ? P.warn : P.ink, x = bx(pageU(step.pin.p) + step.pin.po / PAGE * U), y = bx(ROW.sym0);
    g.fillStyle = col; g.beginPath(); g.moveTo(x - 11, y - 20); g.lineTo(x + 11, y - 20); g.lineTo(x, y); g.fill();
    g.fillRect(x - 1.5, y, 3, bx(ROW.sym1 - ROW.sym0));
    const label = step.pin.kind + (fault ? ', waiting' : ''), f = fnt(700, 1.1, MONO); g.font = f; const w = g.measureText(label).width;
    const lx = Math.min(board.cv.width - w / 2 - 20, Math.max(w / 2 + 20, x));
    g.fillStyle = P.paper; g.fillRect(lx - w / 2 - 6, bx(ROW.pin) - bx(1.0) - 16, w + 12, bx(1.0) + 6);
    txt(g, label, lx, bx(ROW.pin) - 16, f, col, 'center');
  }

  head(ROW.pteH, 'PAGE TABLE', 'one PTE per page · the CPU MMU reads it, the kernel writes it');
  head(ROW.stH, 'KERNEL state[ ]', 'the kernel’s own note per page · the CPU MMU never sees it');
  head(ROW.cotH, 'COT', 'one entry per page · where the compressed stream is, for LZ4 HW');
  boardChanged = [];
  D.pages.forEach((pg, p) => {
    const now = tabOf(st, p), was = prev ? tabOf(prev.st, p) : now, x = bx(pageU(p) + 0.3), w = bx(U - 0.6), cx = x + w / 2;
    const tile = (row, changed, fill, stroke, lw) => {
      const y = bx(ROW[row + '0']), h = bx(ROW[row + '1'] - ROW[row + '0']);
      if (changed) boardChanged.push({ p, row });
      box(g, x, y, w, h, changed ? P.flash : fill, changed ? P.ink : stroke, changed ? 5 : lw);
      return y;
    };
    const cell = (hl.cells || []).includes(p), warn = hl.warn === p;
    const hp = bx(ROW.pte1 - ROW.pte0), hs = bx(ROW.st1 - ROW.st0), hc = bx(ROW.cot1 - ROW.cot0);
    let y = tile('pte', now.pte !== was.pte, warn ? P.warn_tint : P.paper, warn ? P.warn : cell ? P.ink : P.line, warn || cell ? 4 : 2);
    if (now.pte) { txt(g, 'V=1  frame', cx, y + hp * 0.3, fnt(400, 1.12, MONO), P.muted, 'center'); txt(g, now.pte, cx, y + hp * 0.8, fnt(600, 2.0, MONO), P[pg.kind], 'center'); }
    else { txt(g, 'V=0', cx, y + hp * 0.3, fnt(600, 1.12, MONO), P.warn, 'center'); txt(g, 'invalid', cx, y + hp * 0.76, fnt(600, 1.5, MONO), P.warn, 'center'); }
    y = tile('st', now.state !== was.state, P.paper, P.line, 2);
    const busy = now.state.endsWith('ing');
    txt(g, now.state, cx, y + hs * 0.66, fnt(busy ? 700 : 500, 1.12, MONO), busy ? P.accent : P.ink, 'center');
    y = tile('cot', !sameCot(now.cot, was.cot), P.paper, P.line, 2);
    if (now.cot) { txt(g, now.cot.len + ' B', cx, y + hc * 0.47, fnt(600, 1.6, MONO), P[pg.kind], 'center'); txt(g, 'in ' + now.cot.n + ' chunks', cx, y + hc * 0.84, fnt(400, 1.12, MONO), P.muted, 'center'); }
    else txt(g, 'empty', cx, y + hc * 0.6, fnt(400, 1.2, MONO), P.muted, 'center');
  });
  board.tex.needsUpdate = true;
}

// Which symbol and which byte of it a point of the board (in board units) falls on.
function symbolAt(u, v) {
  if (v < ROW.sym0 || v > ROW.sym1) return null;
  for (const s of D.symbols) { const a = symU(s), w = s.size / PAGE * U; if (u >= a && u <= a + w) return { sym: s, off: Math.max(0, Math.min(s.size - 1, Math.floor((u - a) / w * s.size))) }; }
  return null;
}

/* ---------- the CPU-MMU page: the processor on the board, DRAM on the floor ----------
   Board, at the back: one panel per core. From the top: the core's two hardware threads (each runs user SW, or a
   kernel SW instance after an exception), the CPU MMU, this core's TLB, this core's L1. Under both panels: the L2
   that all cores share. Floor, nearest: the frames, then the page table with mm_lock beside it, then what the
   compression layer keeps. The frames are the row next to the processor on purpose: a line from a TLB entry to its
   frame never passes over the page table, because the CPU MMU never reads it.
   Everything is drawn from one step of mmu_sim.js. The layout is written for two cores with two threads each. */
const PANU = c => 2 + c * 45, PANW = 43;                                             // a core's panel, in board units
const BOX0 = c => PANU(c) + (c ? 2.8 : 2.6), BOX1 = c => PANU(c) + (c ? 40.4 : 40.2);  // the boxes inside a panel
const V = { head: 2.1, th0: 3.0, th1: 8.1, rowA: 8.5, rowK: 8.9, mmu0: 9.3, mmu1: 11.7, tlbH: 12.85, slot0: 13.3, slotH: 2.3, slotGap: 0.2,
  l10: 21.2, l11: 23.4, pan1: 23.9, l20: 24.5, l21: 26.8 };
const slotV = s => V.slot0 + s * (V.slotH + V.slotGap), slotMid = s => slotV(s) + V.slotH / 2;
const TW = 18.4, thU = (c, t) => BOX0(c) + t * (TW + 0.8), thMid = (c, t) => thU(c, t) + TW / 2;   // a hardware thread's box
// The lines of a core's TLB slots run in lanes on the side that faces the other core, so they all leave the board in the middle.
const laneU = (c, s) => c ? PANU(c) + 0.7 + s * 0.65 : PANU(c) + PANW - 0.7 - s * 0.65;
const laneEdge = c => c ? BOX0(c) : BOX1(c);
// The kernel's way to its own core's TLB and down to the page table runs on the other side of the boxes.
const fillU = c => c ? PANU(c) + 41.7 : PANU(c) + 1.3, fillEdge = c => c ? BOX1(c) : BOX0(c);
// One chip per frame in every cache: does this cache hold data of that frame, and is it newer than DRAM.
const CHW = 4.9, chipU1 = (c, f) => BOX1(c) - 21.3 + f * 5.3, L2U0 = 4.6, L2U1 = 87.4, CH2W = 6.4, chipU2 = f => 56.6 + f * 7.2;
const frS = f => '…' + FRAME_ADDR[f].toString(16).toUpperCase().slice(-5);
const COLX = -37.3, GRIDX = -25.5;                                    // floor: a column of row names on the left, tiles from GRIDX on
const FRX = f => GRIDX + 15.6 * f, FRW = 14, FRZ0 = 0.4, FRZ1 = 8.4;  // frames
const PTX = p => GRIDX + 9.0 * p, PTW = 8.6, PTZ0 = 12.2, PTZ1 = 17.0; // PTE tiles
const STZ0 = 21.2, STZ1 = 26.4;                                       // what the compression layer keeps, one place per page
const LKX = 29.4, LKW = 7.9;                                          // mm_lock, beside the tables it guards
const PACK = [0.47, 0.61, 0.38, 0.55, 0.66, 0.43];                    // how wide each page's compressed data is drawn. A picture of "smaller", not a measured size.
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
const runs = st => st.run.flatMap((r, c) => r.map((a, t) => a && Object.assign({ core: c, thr: t }, a))).filter(Boolean);

const board = plate(BW, BH, BPX);
board.mesh.position.copy(B2W(BW / 2, BH / 2)); board.mesh.rotation.x = -(Math.PI / 2 - TILT); scene.add(board.mesh);
const floor = plate(2 * FLX, FLZ1 - FLZ0, FPX);
floor.mesh.rotation.x = -Math.PI / 2; floor.mesh.position.set(0, 0, (FLZ0 + FLZ1) / 2); scene.add(floor.mesh);
const fx = x => (x + FLX) * FPX, fz = z => (z - FLZ0) * FPX;
let CHANGED = [];                                // what this step rewrote: [{ at, w, h, onBoard }], for the pulse rings

/* ---------- board ---------- */
function chip(g, u, v, w, state, label, was, hot) {
  const x = bx(u), y = bx(v), W = bx(w), H = bx(1.4), chg = state !== was;
  box(g, x, y, W, H, state === 'dirty' ? P.rw : state ? P.rw_bg : P.paper, hot ? P.accent : chg ? P.ink : state ? P.rw : P.line, hot || chg ? 4 : 2, state || hot || chg ? null : [7, 6]);
  txt(g, label, x + W / 2, y + H * 0.7, fnt(state ? 600 : 400, 0.9, MONO), state === 'dirty' ? P.paper : state ? P.ink : P.muted, 'center');
}
function drawBoard(step, prev) {
  const g = board.g, st = step.st, hl = step.hl || {}, was = prev ? prev.st : st;
  const hot = (c, f) => (hl.cop && hl.cop.f === f) || (hl.cache && hl.cache.f === f && (c === null ? hl.cache.via === 'l2' : hl.cache.via === 'l1' && hl.cache.core === c));
  g.fillStyle = P.paper; g.fillRect(0, 0, board.cv.width, board.cv.height);
  for (let c = 0; c < NCORE; c++) {
    const u0 = PANU(c), x0 = bx(BOX0(c)), w = bx(BOX1(c) - BOX0(c)), x1 = x0 + w, lit = step.core === c || step.core === null;
    box(g, bx(u0), bx(0.4), bx(PANW), bx(V.pan1 - 0.4), null, lit ? P.ink : P.line, lit ? 5 : 3);
    txt(g, 'CORE ' + c, x0, bx(V.head), fnt(800, 1.5, DISP), P.ink);
    txt(g, 'two hardware threads · one CPU MMU, TLB and L1', x1, bx(V.head), fnt(400, 1.0, MONO), P.muted, 'right');

    // the two hardware threads: each runs user SW, or a kernel SW instance after an exception
    for (let t = 0; t < NTHR; t++) {
      const r = st.run[c][t], k = st.kern[c][t], back = !k && !!prev && !!prev.st.kern[c][t], bad = !!r && r.stage === 'stale';
      const x = bx(thU(c, t)), y = bx(V.th0), tw = bx(TW), acc = r ? r.kind + ' ' + laNo(r.p, r.off) : '';
      box(g, x, y, tw, bx(V.th1 - V.th0), k ? P.accent_tint : P.paper, bad ? P.warn : k ? P.accent : r ? P.ink : P.line, k || r ? 4 : 2);
      txt(g, 'THREAD ' + t, x + bx(0.6), y + bx(1.3), fnt(700, 0.95, DISP), k || r ? P.ink : P.muted);
      txt(g, k ? 'KERNEL SW' : 'USER SW', x + tw - bx(0.6), y + bx(1.3), fnt(700, 0.95, DISP), k ? P.accent : r ? P.ink : P.muted, 'right');
      if (k) {
        txt(g, k, x + bx(0.6), y + bx(2.95), fnt(700, 1.0, MONO), P.accent);
        txt(g, r ? 'stopped: ' + acc : 'no user access involved', x + bx(0.6), y + bx(4.3), fnt(400, 0.9, MONO), r ? P.warn : P.muted);
      } else if (r) {
        const note = { ask: 'issued', hit: 'goes through', done: 'continues', back: 'runs again', stale: 'wrong · no error' }[r.stage];
        txt(g, acc, x + bx(0.6), y + bx(2.95), fnt(600, 1.25, MONO), P.ink);
        txt(g, 'page ' + pgNo(r.p) + ' · ' + note, x + bx(0.6), y + bx(4.3), fnt(r.stage === 'back' || bad ? 600 : 400, 0.9, MONO), bad ? P.warn : r.stage === 'back' ? P.accent : P.muted);
      } else txt(g, back ? 'kernel SW returned' : 'running · no access now', x + bx(0.6), y + bx(2.95), fnt(400, 0.95, MONO), back ? P.accent : P.muted);
    }

    // the CPU MMU: hardware, looks only in this core's TLB
    const rs = st.run[c].filter(Boolean), r = rs.find(a => a.stage !== 'wait' && a.stage !== 'back') || rs[0], stage = r ? r.stage : null, bad = stage === 'stale';
    const e = r ? st.tlb[c].find(e => e && e.p === r.p) : null;
    const mm = !r ? ['idle', P.muted] : stage === 'ask' ? ['looks up page ' + pgNo(r.p) + ' in this TLB', P.ink]
      : stage === 'miss' ? ['TLB miss: exception to kernel SW', P.warn]
      : stage === 'wait' ? ['exception taken · kernel SW runs', P.muted]
      : stage === 'back' ? ['kernel SW returned · runs again', P.muted]
      : bad ? ['TLB hit on a stale entry · no exception', P.warn] : ['TLB hit · physical ' + (e ? paNo(e.f, r.off) : ''), P.ink];
    const loud = stage === 'miss' || bad, live = !!r && stage !== 'wait' && stage !== 'back';
    box(g, x0, bx(V.mmu0), w, bx(V.mmu1 - V.mmu0), loud ? P.warn_tint : P.soft, loud ? P.warn : live ? P.ink : P.line, live ? 4 : 2);
    txt(g, 'CPU MMU', x0 + bx(0.7), bx(V.mmu0 + 1.1), fnt(700, 1.05, DISP), P.ink);
    txt(g, 'hardware', x0 + bx(0.7), bx(V.mmu0 + 2.0), fnt(400, 0.85, MONO), P.muted);
    txt(g, mm[0], x0 + bx(8.5), bx(V.mmu0 + 1.15), fnt(live ? 600 : 400, 1.1, MONO), mm[1]);
    txt(g, 'never reads the page table', x0 + bx(8.5), bx(V.mmu0 + 2.05), fnt(400, 0.85, MONO), P.muted);

    // this core's TLB: one for both threads
    txt(g, 'TLB of Core ' + c, x0, bx(V.tlbH), fnt(700, 1.1, DISP), P.ink);
    txt(g, 'for both threads · filled by kernel SW · example size', x1, bx(V.tlbH), fnt(400, 0.85, MONO), P.muted, 'right');
    for (let s = 0; s < NTLB; s++) {
      const e = st.tlb[c][s], chg = !same(e, was.tlb[c][s]), old = stale(st, e);
      const tgt = (hl.tlb || []).some(([cc, ss]) => cc === c && ss === s), y = bx(slotV(s)), h = bx(V.slotH), ty = y + h * 0.68;
      if (chg) CHANGED.push({ at: B2W((BOX0(c) + BOX1(c)) / 2, slotMid(s), 0.12), w: BOX1(c) - BOX0(c), h: V.slotH, onBoard: true });
      box(g, x0, y, w, h, chg ? P.flash : old ? P.warn_tint : P.paper, old ? P.warn : tgt || chg ? P.ink : P.line, old || tgt || chg ? 4 : 2, e ? null : [10, 8]);
      if (e) {
        txt(g, 'page ' + pgNo(e.p), x0 + bx(0.8), ty, fnt(600, 1.35, MONO), P.ink);
        txt(g, '▶', x0 + bx(10.8), ty - 2, fnt(400, 0.9, MONO), P.muted, 'center');
        txt(g, 'frame ' + frNo(e.f), x0 + bx(12.2), ty, fnt(600, 1.35, MONO), old ? P.warn : P.rw);
        if (old) txt(g, 'STALE', x1 - bx(0.8), ty, fnt(800, 1.2, DISP), P.warn, 'right');
      } else txt(g, chg ? 'empty · cleared in this step' : 'empty', x0 + bx(0.8), ty, fnt(chg ? 600 : 400, 1.1, MONO), chg ? P.ink : P.muted);
    }

    // this core's L1: after the CPU MMU, so it is asked with a physical address
    const any = st.l1[c].some(Boolean);
    box(g, x0, bx(V.l10), w, bx(V.l11 - V.l10), P.soft, P.line, 2);
    txt(g, 'L1 of Core ' + c, x0 + bx(0.7), bx(V.l10 + 1.0), fnt(700, 1.05, DISP), P.ink);
    txt(g, 'cache · both threads', x0 + bx(0.7), bx(V.l10 + 1.85), fnt(400, 0.8, MONO), P.muted);
    txt(g, any ? 'frame' : 'empty', bx(chipU1(c, 0) - 0.5), bx(V.l10 + 1.4), fnt(400, 0.85, MONO), P.muted, 'right');
    for (let f = 0; f < NF; f++) chip(g, chipU1(c, f), V.l10 + 0.4, CHW, st.l1[c][f], frS(f), was.l1[c][f], hot(c, f));
  }
  // the L2: one for all cores, sees only physical addresses
  box(g, bx(L2U0), bx(V.l20), bx(L2U1 - L2U0), bx(V.l21 - V.l20), P.soft, P.line, 3);
  txt(g, 'L2', bx(L2U0 + 0.8), bx(V.l20 + 1.55), fnt(800, 1.5, DISP), P.ink);
  txt(g, 'cache shared by all cores', bx(L2U0 + 4.4), bx(V.l20 + 1.0), fnt(600, 0.9, MONO), P.ink);
  txt(g, 'hardware · sees only physical addresses', bx(L2U0 + 4.4), bx(V.l20 + 1.9), fnt(400, 0.85, MONO), P.muted);
  txt(g, st.l2.some(Boolean) ? 'frame' : 'empty', bx(chipU2(0) - 0.5), bx(V.l20 + 1.45), fnt(400, 0.85, MONO), P.muted, 'right');
  for (let f = 0; f < NF; f++) chip(g, chipU2(f), V.l20 + 0.45, CH2W, st.l2[f], frS(f), was.l2[f], hot(null, f));
  board.tex.needsUpdate = true;
}

/* ---------- floor ---------- */
let MAT = {};
function buildMaterials() {
  Object.values(MAT).forEach(m => { if (m.map) m.map.dispose(); m.dispose(); });
  const L = o => new THREE.MeshLambertMaterial(o), B = k => new THREE.MeshBasicMaterial({ color: new THREE.Color(P[k]) }), t = hatchTexture(P.rw_bg, P.rw); t.repeat.set(0.5, 3);
  MAT = { edge: L({ color: new THREE.Color(P.rw) }), hz: L({ map: t }), bit: L({ map: hatchTexture(P.rw_bg, P.rw) }), ink: B('ink'), warn: B('warn'), accent: B('accent'), rw: B('rw') };
}

// frames: a slab with a drawn top
const SLABW = FRW - 0.5, SLABZ = FRZ1 - FRZ0 - 0.4, FRAMES = [];
for (let f = 0; f < NF; f++) {
  const grp = new THREE.Group(), slab = new THREE.Mesh(new THREE.BoxGeometry(SLABW, 0.7, SLABZ)), top = plate(SLABW, SLABZ, 40);
  slab.position.y = 0.35; top.mesh.rotation.x = -Math.PI / 2; top.mesh.position.y = 0.715;
  grp.add(slab, top.mesh); grp.position.set(FRX(f) + FRW / 2, 0, (FRZ0 + FRZ1) / 2); scene.add(grp);
  FRAMES.push({ grp, slab, top });
}
function drawFrameTop(F, step, f) {
  const g = F.top.g, W = F.top.cv.width, H = F.top.cv.height, st = step.st, p = st.frames[f], a = runs(st).find(r => r.stage === 'stale'), nw = newest(st, f);
  const wrong = !!(step.hl || {}).warn && (step.hl.frames || []).includes(f);
  g.fillStyle = wrong ? P.warn_tint : P.paper; g.fillRect(0, 0, W, H);
  txt(g, 'frame ' + frNo(f), 24, 62, '600 38px ' + MONO, P.ink);
  txt(g, 'holds', 24, 124, '400 34px ' + MONO, P.muted);
  txt(g, 'page ' + pgNo(p), 24, 200, '600 76px ' + MONO, P.rw);
  if (wrong && a && a.p !== p) txt(g, 'Core ' + a.core + ' expects page ' + pgNo(a.p), 24, 264, '600 34px ' + MONO, P.warn);
  else if (nw) txt(g, 'older than ' + nw, 24, 264, '600 34px ' + MONO, P.ink);
  box(g, 3, 3, W - 6, H - 6, null, wrong ? P.warn : P.rw, 6);
  F.top.tex.needsUpdate = true;
}
// what the compression layer keeps: a thin slab per page, hatched because it is compressed
const STORE = [];
for (let p = 0; p < NP; p++) {
  const w = (PTW - 1) * PACK[p], m = new THREE.Mesh(new THREE.BoxGeometry(w, 0.5, STZ1 - STZ0 - 1.2));
  m.position.set(PTX(p) + 0.5 + w / 2, 0.25, (STZ0 + STZ1) / 2); scene.add(m); STORE.push(m);
}
const storePt = p => V3(PTX(p) + 0.5 + (PTW - 1) * PACK[p] / 2, 0.8, STZ0 + 1.2);
const NOTE = { in: 'coming back', out: 'going out' }, who = ct => 'Core ' + ct[0] + ' T' + ct[1];

function drawFloor(step, prev) {
  const g = floor.g, st = step.st, hl = step.hl || {}, was = prev ? prev.st : st;
  g.fillStyle = P.paper; g.fillRect(0, 0, floor.cv.width, floor.cv.height);
  // a row's name and what to know about it, in the column on the left
  const side = (z, title, lines) => {
    let y = fz(z); title.forEach(t => { txt(g, t, fx(COLX), y, '700 38px ' + DISP, P.ink); y += 40; }); y -= 6;
    lines.forEach(([t, strong]) => { txt(g, t, fx(COLX), y, (strong ? '600' : '400') + ' 24px ' + MONO, strong ? P.ink : P.muted); y += 31; });
  };
  const mark = (x, z, w, h) => CHANGED.push({ at: V3(x + w / 2, 0.1, z + h / 2), w, h, onBoard: false });

  side(FRZ0 + 1.7, ['FRAMES'], [['in DRAM'], ['4096 B each'], ['not compressed'], [st.frames.filter(o => o === null).length + ' of ' + NF + ' free', true]]);
  for (let f = 0; f < NF; f++) {
    const tgt = (hl.frames || []).includes(f), bad = tgt && hl.warn, free = st.frames[f] === null, h = st.hold[f];
    const chg = was.frames[f] !== st.frames[f] || was.hold[f] !== h;
    if (chg) mark(FRX(f), FRZ0, FRW, FRZ1 - FRZ0);
    box(g, fx(FRX(f)) + 4, fz(FRZ0) + 4, FRW * FPX - 8, (FRZ1 - FRZ0) * FPX - 8, chg && free ? P.flash : null, bad ? P.warn : tgt || chg ? P.ink : P.line, tgt || chg ? 7 : 3, tgt || chg ? null : [12, 9]);
    if (free) {
      const cx = fx(FRX(f) + FRW / 2), cy = fz((FRZ0 + FRZ1) / 2);
      txt(g, 'frame ' + frNo(f), fx(FRX(f)) + 24, fz(FRZ0) + 46, '400 24px ' + MONO, P.muted);
      if (h === null) txt(g, 'free', cx, cy + 20, '400 34px ' + MONO, P.muted, 'center');
      else { txt(g, 'taken for', cx, cy + 4, '400 28px ' + MONO, P.accent, 'center'); txt(g, 'page ' + pgNo(h), cx, cy + 50, '600 40px ' + MONO, P.accent, 'center'); }
    }
  }

  side(PTZ0 - 0.1, ['PAGE TABLE'], [['in DRAM'], ['one PTE per page'], ['kernel SW only']]);
  txt(g, 'kernel’s note', fx(COLX), fz(PTZ1) + 38, '400 24px ' + MONO, P.muted);
  for (let p = 0; p < NP; p++) {
    const f = st.pte[p], chg = was.pte[p] !== f, tgt = (hl.pte || []).includes(p), warn = hl.warnPte === p || (f === null && tgt);
    const x = fx(PTX(p)), y = fz(PTZ0), w = PTW * FPX, h = (PTZ1 - PTZ0) * FPX, cx = x + w / 2, b = st.busy[p];
    if (chg) mark(PTX(p), PTZ0, PTW, PTZ1 - PTZ0);
    txt(g, 'page ' + pgNo(p), x + 4, y - 9, (tgt ? '600' : '400') + ' 25px ' + MONO, tgt ? P.ink : P.muted);
    box(g, x, y, w, h, chg ? P.flash : warn ? P.warn_tint : P.paper, chg || tgt ? P.ink : P.line, chg || tgt ? 5 : 2);
    if (f !== null) { txt(g, 'V=1  frame', cx, y + 40, '400 24px ' + MONO, P.muted, 'center'); txt(g, frNo(f), cx, y + 86, '600 29px ' + MONO, P.rw, 'center'); }
    else { txt(g, 'V=0', cx, y + 40, '600 24px ' + MONO, P.warn, 'center'); txt(g, 'invalid', cx, y + 86, '600 31px ' + MONO, P.warn, 'center'); }
    // what the kernel has written down about this page in its own table. The CPU MMU never sees it.
    if (b !== was.busy[p]) box(g, x, y + h + 10, w, 40, P.flash, P.ink, 3);
    txt(g, b ? NOTE[b] : f !== null ? 'in a frame' : 'compressed', cx, y + h + 38, (b ? '700' : '400') + ' 23px ' + MONO, b ? P.accent : P.muted, 'center');
  }

  side(STZ0 + 0.6, ['COMPRESSION', 'LAYER'], [['holds the pages'], ['without a frame,'], ['compressed'], ['detail: LZ4 pages']]);
  for (let p = 0; p < NP; p++) {
    const on = st.stored[p], chg = was.stored[p] !== on, tgt = (hl.store || []).includes(p);
    if (chg) mark(PTX(p), STZ0, PTW, STZ1 - STZ0);
    box(g, fx(PTX(p)), fz(STZ0), PTW * FPX, (STZ1 - STZ0) * FPX, chg && !on ? P.flash : null, tgt || chg ? P.ink : P.line, tgt || chg ? 5 : 2, on || tgt || chg ? null : [10, 8]);
    if (!on) txt(g, 'nothing kept', fx(PTX(p) + PTW / 2), fz((STZ0 + STZ1) / 2) + 10, '400 22px ' + MONO, P.muted, 'center');
    txt(g, 'page ' + pgNo(p), fx(PTX(p) + PTW / 2), fz(STZ1) + 36, (on ? '600' : '400') + ' 25px ' + MONO, on ? P.ink : P.muted, 'center');
  }

  // mm_lock: one kernel SW instance at a time may change the tables on this floor
  const lk = st.lock, chg = !same(lk, was.lock), x = fx(LKX), y = fz(PTZ0), w = LKW * FPX, h = (STZ1 - PTZ0) * FPX, cx = x + w / 2;
  if (chg) mark(LKX, PTZ0, LKW, STZ1 - PTZ0);
  box(g, x, y, w, h, chg ? P.flash : lk.by ? P.accent_tint : P.paper, lk.by || chg || hl.lock ? P.accent : P.line, lk.by || chg || hl.lock ? 6 : 3);
  txt(g, 'mm_lock', cx, y + 46, '800 36px ' + DISP, P.ink, 'center');
  txt(g, 'kernel SW’s lock', cx, y + 80, '400 17px ' + MONO, P.muted, 'center');
  txt(g, 'for these tables', cx, y + 106, '400 17px ' + MONO, P.muted, 'center');
  txt(g, lk.by ? 'HELD' : 'FREE', cx, y + 168, '800 46px ' + DISP, lk.by ? P.accent : P.muted, 'center');
  if (lk.by) txt(g, 'by ' + who(lk.by), cx, y + 206, '600 24px ' + MONO, P.accent, 'center');
  if (lk.wait.length) {
    txt(g, 'waiting:', cx, y + 258, '400 22px ' + MONO, P.warn, 'center');
    lk.wait.forEach((ct, i) => txt(g, who(ct), cx, y + 290 + 30 * i, '600 24px ' + MONO, P.warn, 'center'));
  } else txt(g, 'nobody waits', cx, y + 258, '400 22px ' + MONO, P.muted, 'center');
  floor.tex.needsUpdate = true;
}

// Put every slab in the state of this step. Returns what is still arriving, so the animation can grow it in.
function updateSlabs(step) {
  const st = step.st, lz = step.links.filter(l => l.t === 'lz');
  FRAMES.forEach((F, f) => {
    F.grp.visible = st.frames[f] !== null; F.grp.scale.x = 1; F.grp.position.x = FRX(f) + FRW / 2; F.slab.material = MAT.edge;
    if (st.frames[f] !== null) drawFrameTop(F, step, f);
  });
  STORE.forEach((m, p) => { m.material = MAT.hz; m.visible = st.stored[p]; });
  return { frames: lz.filter(l => l.dir === 'out').map(l => l.f), stores: lz.filter(l => l.dir === 'in').map(l => l.p) };
}

/* ---------- what changes with every step: mapping lines, the access path, the kernel's reads and writes, flowing data ---------- */
const dyn = new THREE.Group(); scene.add(dyn);
const bitGeo = new THREE.BoxGeometry(1, 1, 1), dotGeo = new THREE.SphereGeometry(0.45, 14, 10);
let FLOWS = [], PULSES = [], ARRIVE = { frames: [], stores: [] }, stepT0 = 0;

// A train of pieces that keeps running along a curve. `look(t)` says how a piece looks at position t.
function addFlow(curve, n, look, phase = 0, speed = 0.3) {
  const bits = [];
  for (let i = 0; i < n; i++) { const m = new THREE.Mesh(look(0).dot ? dotGeo : bitGeo, look(0).mat); dyn.add(m); bits.push(m); }
  FLOWS.push({ curve, bits, look, phase, speed });
}
const dots = k => () => ({ mat: MAT[k], s: [1, 1, 1], dot: true });
const plainBit = () => ({ mat: MAT.edge, s: [1.5, 0.6, 1.0] }), packedBit = () => ({ mat: MAT.bit, s: [0.85, 0.6, 1.0] });
// A line made of straight pieces and arcs: drawn as tubes, and usable as one path for the dots.
function route(curves, r, color, opacity = 1) {
  const path = new THREE.CurvePath();
  curves.forEach(c => { path.add(c); dyn.add(tube(c, r, color, opacity, c.type === 'LineCurve3' ? 1 : 28)); });
  return path;
}
const poly = (pts, r, color) => route(pts.slice(1).map((b, i) => seg3(pts[i], b)), r, color);
// A rectangle around a tile, on the board or on the floor. It pulses once when the step starts.
function ring(o) {
  const grp = new THREE.Group(), w = o.w - 0.3, h = o.h - 0.3;
  grp.position.copy(o.at); grp.rotation.x = o.onBoard ? -(Math.PI / 2 - TILT) : -Math.PI / 2;
  const c = [V3(-w / 2, -h / 2, 0), V3(w / 2, -h / 2, 0), V3(w / 2, h / 2, 0), V3(-w / 2, h / 2, 0)];
  c.forEach((a, i) => grp.add(tube(seg3(a, c[(i + 1) % 4]), 0.13, P.ink, 1, 1)));
  grp.userData.group = true; dyn.add(grp); PULSES.push(grp);
}
function tag(text, at, color) { const s = sprite(text, P.paper, color, 1.25); s.position.copy(at); s.userData.ownMap = true; dyn.add(s); }
function clearDyn() {
  dyn.children.slice().forEach(o => { if (o.userData.group) { clearGroup(o); dyn.remove(o); } });
  dyn.children.slice().forEach(o => { dyn.remove(o); if (o.geometry !== bitGeo && o.geometry !== dotGeo) { if (o.userData.ownMap) o.material.map.dispose(); else o.geometry.dispose(); o.material.dispose(); } });
  FLOWS = []; PULSES = [];
}

const bp = (u, v) => B2W(u, v, 0.15), L1V = (V.l10 + V.l11) / 2, L2V = (V.l20 + V.l21) / 2;
// Every TLB slot of every core has its own place to end on a frame and its own strip of floor between the board and the frames.
const lane = (c, s) => c * NTLB + s, landX = (c, s, f) => FRX(f) + FRW * (0.14 + 0.13 * lane(c, s)), bandZ = (c, s) => -3.15 + 0.42 * lane(c, s);
// Down a slot's lane, off the board, along the floor, onto the frame.
const laneToFrame = (c, s, f) => { const u = laneU(c, s), z = bandZ(c, s), x = landX(c, s, f); return [bp(u, BH), V3(u - BW / 2, 0.12, z), V3(x, 0.12, z), V3(x, 0.9, FRZ0 + 0.8)]; };
const slotStub = (c, s) => seg3(bp(laneEdge(c), slotMid(s)), bp(laneU(c, s), slotMid(s)));
// From a thread's box into a lane: user SW's access uses row A to the inner lane, the kernel uses row K to the outer one.
const fromThread = (c, t, u, row) => [bp(thMid(c, t), V.th1), bp(thMid(c, t), row), bp(u, row)];
const kernDown = (c, t, v) => fromThread(c, t, fillU(c), V.rowK).concat([bp(fillU(c), v)]);

function buildDynamic(step) {
  clearDyn();
  const st = step.st; let unknownTag = false;
  // where every mapping points right now: each valid PTE, and each TLB entry of each core
  st.pte.forEach((f, p) => { if (f !== null) dyn.add(tube(seg3(V3(PTX(p) + PTW * 0.9, 0.08, PTZ0), V3(FRX(f) + FRW * (0.2 + 0.12 * p), 0.75, FRZ1 - 0.25)), 0.055, P.rw, 0.6, 1)); });
  st.tlb.forEach((t, c) => t.forEach((e, s) => { if (e) {
    const old = stale(st, e), r = old ? 0.09 : 0.045, col = old ? P.warn : P.rw, o = old ? 0.95 : 0.5;
    route([slotStub(c, s)], r, col, o); const pts = [bp(laneU(c, s), slotMid(s))].concat(laneToFrame(c, s, e.f));
    route(pts.slice(1).map((b, i) => seg3(pts[i], b)), r, col, o);
  } }));
  CHANGED.forEach(ring);

  const lz = step.links.filter(l => l.t === 'lz'), mids = [];
  step.links.forEach(l => {
    const c = l.core, t = l.thr;
    if (l.t === 'xlate') {            // the access reaches a TLB entry: the CPU MMU has a physical address
      const u = laneU(c, l.slot), col = l.warn ? P.warn : P.ink;
      const path = poly(fromThread(c, t, u, V.rowA).concat([bp(u, slotMid(l.slot)), bp(laneEdge(c), slotMid(l.slot))]), 0.14, col);
      addFlow({ getPoint: x => path.getPointAt(x) }, 5, dots(l.warn ? 'warn' : 'ink'), 0, 0.4);
    }
    if (l.t === 'data') {             // the access: past the TLB entry, then L1, then L2, then the frame. It ends where the data is.
      const u = laneU(c, l.slot), col = l.warn ? P.warn : P.ink;
      const end = l.via === 'l1' ? [bp(u, L1V), bp(laneEdge(c), L1V)] : l.via === 'l2' ? [bp(u, L2V)] : laneToFrame(c, l.slot, l.f);
      const path = poly(fromThread(c, t, u, V.rowA).concat([bp(u, slotMid(l.slot))], end), 0.14, col);
      dyn.add(tube(slotStub(c, l.slot), 0.14, col, 1, 1));
      const back = l.kind === 'read';          // read data comes back; written data goes in
      addFlow({ getPoint: x => path.getPointAt(back ? 1 - x : x) }, 8, dots(l.warn ? 'warn' : 'ink'), 0, 0.24);
      if (l.via === 'l1') tag('served by L1', B2W(laneEdge(c) + (c ? 5 : -5), V.l11 + 0.55, 0.6), col);
      if (l.via === 'l2') tag('served by L2', B2W(36.5, L2V, 0.6), col);
    }
    if (l.t === 'pte') {              // the kernel reads or writes one PTE
      // Down the outer lane, off the board, along the floor, between two frames, then to the PTE. It passes no frame's label.
      const xt = PTX(l.p) + PTW * (0.7 + 0.14 * c), zk = -0.55 + 0.3 * c, zm = 9.5 + 0.4 * c, y = 0.15, x0 = Math.max(-37, Math.min(37, fillU(c) - BW / 2));
      const xg = [...Array(NF + 1)].map((_, i) => FRX(i) - 0.95 + 0.35 * c).reduce((a, b) => Math.abs(b - xt) < Math.abs(a - xt) ? b : a);
      const path = poly(kernDown(c, t, BH).concat([V3(x0, y, zk), V3(xg, y, zk), V3(xg, y, zm), V3(xt, y, zm), V3(xt, y, PTZ0 + 0.7)]), 0.12, P.accent);
      addFlow({ getPoint: x => path.getPointAt(x) }, 8, dots('accent'), 0, 0.3);
    }
    if (l.t === 'fill') {             // the kernel writes one entry of its own core's TLB
      const path = poly(kernDown(c, t, slotMid(l.slot)).concat([bp(fillEdge(c), slotMid(l.slot))]), 0.12, P.accent);
      addFlow({ getPoint: x => path.getPointAt(x) }, 4, dots('accent'), 0, 0.45);
    }
    if (l.t === 'clear') {            // the kernel on one core has an entry of another core's TLB cleared
      const curve = arc(bp(thMid(c, t), V.th1 - 0.4), bp(laneEdge(l.to), slotMid(l.slot)), 3.2), path = route([curve], 0.12, P.accent);
      addFlow({ getPoint: x => path.getPointAt(x) }, 4, dots('accent'), 0, 0.4);
      if (!unknownTag) tag('how: not known for this platform', curve.getPoint(0.5).add(V3(0, 1.5, 0)), P.accent); unknownTag = true;
    }
    if (l.t === 'cop') {              // the kernel has every cache write back (clean) or drop (invalidate) what it holds of one frame
      const own = poly(kernDown(c, t, L1V).concat([bp(fillEdge(c), L1V)]), 0.12, P.accent);
      poly([bp(fillU(c), L1V), bp(fillU(c), L2V), bp(c ? L2U1 : L2U0, L2V)], 0.12, P.accent);
      addFlow({ getPoint: x => own.getPointAt(x) }, 4, dots('accent'), 0, 0.45);
      for (let k = 0; k < NCORE; k++) if (k !== c) {
        const curve = arc(bp(thMid(c, t), V.th1 - 0.4), bp(laneEdge(k), L1V), 3.2), path = route([curve], 0.12, P.accent);
        addFlow({ getPoint: x => path.getPointAt(x) }, 4, dots('accent'), 0, 0.4);
        if (!unknownTag) tag('how: not known for this platform', curve.getPoint(0.5).add(V3(0, 1.5, 0)), P.accent); unknownTag = true;
      }
      if (l.op === 'clean' && l.from) {        // the data that was newer than DRAM goes to the frame
        const m = /Core (\d)/.exec(l.from), u = m ? chipU1(+m[1], l.f) + CHW / 2 : chipU2(l.f) + CH2W / 2, x = FRX(l.f) + FRW * 0.9;
        const path = poly([bp(u, m ? V.l11 - 0.4 : V.l21 - 0.4), bp(u, BH), V3(u - BW / 2, 0.12, -0.9), V3(x, 0.12, -0.9), V3(x, 0.9, FRZ0 + 0.8)], 0.13, P.rw);
        addFlow({ getPoint: x => path.getPointAt(x) }, 7, dots('rw'), 0, 0.3);
        tag('written back to DRAM', V3((u - BW / 2 + x) / 2, 1.6, -0.9), P.rw);
      }
    }
    if (l.t === 'lz') {               // the compression layer: one step here
      const fr = V3(FRX(l.f) + FRW / 2, 1.0, FRZ1 - 0.9), sp = storePt(l.p), inward = l.dir === 'in', curve = inward ? arc(fr, sp, 3.6) : arc(sp, fr, 3.6);
      addFlow(curve, 9, x => (x < 0.5) === inward ? plainBit() : packedBit(), 0, 0.2);
      mids.push(curve.getPoint(0.5));
    }
  });
  if (lz.length) {
    const at = mids.reduce((a, b) => a.add(b), V3(0, 0, 0)).multiplyScalar(1 / mids.length).add(V3(0, 2.5, 0)), what = lz[0].dir === 'in' ? 'compress' : 'decompress';
    tag(lz.length > 1 ? lz.length + ' ' + what + ' jobs at once: kernel SW + LZ4 HW' : what + ': kernel SW + LZ4 HW', at, P.ink);
  }

  // an access that has not reached a TLB entry: it goes as far as the CPU MMU
  runs(st).forEach(a => { if (a.stage === 'ask' || a.stage === 'miss') {
    const c = a.core, u = laneU(c, 0), mmuV = (V.mmu0 + V.mmu1) / 2, miss = a.stage === 'miss';
    const path = poly(fromThread(c, a.thr, u, V.rowA).concat([bp(u, mmuV), bp(laneEdge(c), mmuV)]), 0.14, miss ? P.warn : P.ink);
    if (!miss) addFlow({ getPoint: x => path.getPointAt(x) }, 3, dots('ink'), 0, 0.5);
  } });
}

const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
function animate(now) {
  requestAnimationFrame(animate);
  if (!renderer || document.hidden) return;
  const el = REDUCE ? 9 : (now - stepT0) / 1000, clock = REDUCE ? 0.4 : now / 1000;
  FLOWS.forEach(F => F.bits.forEach((m, i) => {
    const t = (clock * F.speed + i / F.bits.length + F.phase) % 1, lk = F.look(t), e = Math.min(1, t * 7, (1 - t) * 7);
    m.position.copy(F.curve.getPoint(t)); m.material = lk.mat; m.scale.set(lk.s[0] * e, lk.s[1] * e, lk.s[2] * e);
  }));
  const k = ease(Math.min(1, el / 1.8));
  ARRIVE.frames.forEach(f => { const F = FRAMES[f], s = Math.max(0.02, k); F.grp.scale.x = s; F.grp.position.x = FRX(f) + 0.25 + SLABW * s / 2; });
  ARRIVE.stores.forEach(p => { STORE[p].visible = el > 1.1; });
  PULSES.forEach(g => { const s = 1 + 0.3 * Math.max(0, 1 - el / 0.7); g.scale.set(s, s, 1); });
  renderer.render(scene, camera);
}

/* ---------- steps, table, controls ---------- */
let cur = { scene: 0, plan: null, i: 0 }, timer = 0, freeKind = 'read', freeCore = 0, freeThr = 0;

function table(step, prev) {
  const cells = (st, p) => {
    const f = st.pte[p], at = st.frames.indexOf(p), hf = st.hold.indexOf(p), b = st.busy[p];
    const t = c => { const e = st.tlb[c].find(e => e && e.p === p); return e ? 'frame ' + frNo(e.f) + (stale(st, e) ? ' · STALE' : '') : 'none'; };
    const where = b === 'in' ? (at >= 0 ? 'frame ' + frNo(at) + ', restored, PTE not valid yet' : 'compression layer, coming back to frame ' + frNo(hf))
      : b === 'out' ? 'frame ' + frNo(at) + ', going out to the compression layer'
      : at >= 0 ? 'frame ' + frNo(at) + ', not compressed' : 'compression layer, compressed';
    const nw = at >= 0 ? newest(st, at) : null, cs = at >= 0 ? cached(st, at) : [];
    return [f !== null ? 'V=1, frame ' + frNo(f) : 'V=0, invalid', t(0), t(1), where, at < 0 ? '—' : cs.length ? cs.map(n => n === nw ? n + ' (newer than DRAM)' : n).join(', ') : 'none'];
  };
  $('rows').innerHTML = PAGES.map((_, p) => {
    const now = cells(step.st, p), was = prev ? cells(prev.st, p) : now;
    return `<tr class="${runs(step.st).some(r => r.p === p) ? 'selrow' : ''}"><td>${pgNo(p)}</td>` +
      now.map((v, i) => `<td class="${(v !== was[i] ? 'chg ' : '') + (i === 0 && step.st.pte[p] === null ? 'inv ' : '') + (v.endsWith('STALE') ? 'stale' : '')}">${v}</td>`).join('') + '</tr>';
  }).join('');
}
function show(animateIn) {
  const steps = cur.plan.steps, step = steps[cur.i], prev = cur.i ? steps[cur.i - 1] : null, last = cur.i === steps.length - 1;
  CHANGED = [];
  drawBoard(step, prev); drawFloor(step, prev); ARRIVE = updateSlabs(step); buildDynamic(step);
  stepT0 = performance.now() - (animateIn ? 0 : 9000);
  table(step, prev);
  $('count').textContent = (cur.scene === null ? '自己發的 access' : '場景 ' + (cur.scene + 1) + ' / ' + SCENES.length + '：' + SCENES[cur.scene].t) + ' · 第 ' + (cur.i + 1) + ' 步，共 ' + steps.length + ' 步';
  $('who').textContent = (step.core === null ? 'Core 0 與 Core 1' : 'Core ' + step.core) + ' · ' + WHO[step.who]; $('who').className = 'who ' + step.who;
  $('text').innerHTML = step.text;
  $('back').disabled = cur.i === 0;
  const more = cur.scene !== null && cur.scene < SCENES.length - 1;
  $('next').disabled = last && !more; $('next').textContent = last && more ? '下一個場景' : '下一步';
  [...$('scenes').children].forEach((b, k) => b.setAttribute('aria-pressed', String(k === cur.scene)));
}
function loadScene(k) { cur = { scene: k, plan: planScene(k), i: 0 }; show(false); }
function next() {
  if (cur.i < cur.plan.steps.length - 1) { cur.i++; show(true); return true; }
  if (cur.scene !== null && cur.scene < SCENES.length - 1) { loadScene(cur.scene + 1); return true; }
  return false;
}
function stop() { clearInterval(timer); timer = 0; $('play').textContent = '自動播放'; }
$('scenes').innerHTML = SCENES.map((s, k) => `<button type="button" data-k="${k}" aria-pressed="false"><b>${k + 1}</b>${s.t}</button>`).join('');
// Bring the whole stage into view when it does not fit under the page header (tablet landscape).
const STAGE = document.querySelector('.stage');
function fit() { const r = STAGE.getBoundingClientRect(); if (r.bottom > innerHeight + 4 && r.top > 12) STAGE.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
$('scenes').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { stop(); loadScene(+b.dataset.k); fit(); } });
$('next').addEventListener('click', () => { stop(); next(); fit(); });
$('back').addEventListener('click', () => { stop(); if (cur.i) { cur.i--; show(false); } });
$('play').addEventListener('click', () => {
  if (timer) return stop();
  $('play').textContent = '暫停';
  fit();
  if (!next()) return stop();
  timer = setInterval(() => { if (!next()) stop(); }, 4200);
});
// An access of your own: pick the core, the thread and the kind, then a page. It starts from the state the plan on screen ends in.
const press = (ids, on) => ids.forEach(id => $(id).setAttribute('aria-pressed', String(id === on)));
['c0', 'c1'].forEach((id, c) => $(id).addEventListener('click', () => { freeCore = c; press(['c0', 'c1'], id); }));
['t0', 't1'].forEach((id, t) => $(id).addEventListener('click', () => { freeThr = t; press(['t0', 't1'], id); }));
['kread', 'kwrite'].forEach(id => $(id).addEventListener('click', () => { freeKind = id.slice(1); press(['kread', 'kwrite'], id); }));
$('pages').innerHTML = PAGES.map((_, p) => `<button type="button" data-p="${p}">${pgNo(p)}</button>`).join('');
$('pages').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  stop(); cur = { scene: null, plan: planAccess(cur.plan.final, freeCore, freeThr, +b.dataset.p, freeKind), i: 0 }; show(false); fit();
});
document.addEventListener('keydown', e => {
  if (e.target.closest('input, textarea')) return;
  if (e.key === 'ArrowRight') { stop(); next(); } else if (e.key === 'ArrowLeft') $('back').click();
});

/* theme and fonts: everything drawn on a canvas has to be redrawn when either changes */
function restyle() {
  readPalette(); scene.background = new THREE.Color(P.bg); buildMaterials();
  if (cur.plan) show(false);
}
restyle();
if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', restyle);
new MutationObserver(restyle).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
const START = new URLSearchParams(location.search);          // ?scene=5&step=3 opens on that step: used to check the page
loadScene(Math.min(SCENES.length, Math.max(1, +START.get('scene') || 1)) - 1);
cur.i = Math.min(cur.plan.steps.length, Math.max(1, +START.get('step') || 1)) - 1; show(false);
if (document.fonts && document.fonts.load) Promise.all(['400 20px "IBM Plex Mono"', '600 20px "IBM Plex Mono"', '700 20px Archivo', '800 20px Archivo'].map(f => document.fonts.load(f))).then(() => show(false), () => {});
resize(); requestAnimationFrame(animate);

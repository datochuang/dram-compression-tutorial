/* ---------- two rhythms: the tables at "now" ----------
   The model runs ahead of the picture, so the panel keeps its own copy of the tables and applies each
   recorded read or write only when "now" reaches its time. Who touches what (P1, interface spec):
   TLB: read by the CPU MMU hardware, written by kernel SW. Page table and COT: kernel SW only.
   Frames: the user SW's data; the LZ4 HW reads them for COMPRESS and writes them for DECOMPRESS.
   Chunk pool: one cell per compressed page; which cell a page gets is the picture's own choice.
   The tables sit inside a simplified architecture: user SW, cores with their TLB and kernel SW, the shared L2,
   the LZ4 HW beside DRAM. Lamps light from the model's events at "now". */
const ST = { cv: $('statecv'), log: $('slog') };
ST.g = ST.cv.getContext('2d');
const FLASH = 0.9;                                     // seconds a touch stays visible on the panel

function stateInit(s) {
  const sn = s.snap();
  ST.fr = Int32Array.from(sn.frames); ST.frSt = new Uint8Array(ST.fr.length);   // 0 free, 1 in use, 2 DECOMPRESS writes it, 3 COMPRESS reads it
  ST.pf = new Map();                                   // page -> { f, st }: V valid, D decompressing, K compressing. Missing: compressed, COT entry valid
  ST.fr.forEach((p, f) => { if (p >= 0) { ST.frSt[f] = 1; ST.pf.set(p, { f, st: 'V' }); } });
  ST.tlb = sn.tlb.map(a => { const r = a.slice(); while (r.length < s.prm.tlb) r.push(-1); return r; });
  ST.tlbAge = ST.tlb.map(r => r.map((_, i) => i));
  ST.win = sn.win; ST.hand = sn.hand; ST.jobs = []; ST.heap = []; ST.fl = new Map(); ST.lines = []; ST.logKey = ''; ST.seq = 0; ST.seqIn = 0;
  ST.ck = new Map(); ST.ckFree = []; ST.ckN = 0;          // chunk pool: page -> cell
  for (const w of ST.win) for (let o = 0; o < s.prm.ws; o++) { const p = w.off + ((w.base + o) & RHY.MASK); if (!ST.pf.has(p)) ckAlloc(p); }
  s.tr.length = 0;
}

/* a small binary heap on time: records arrive nearly in order, but a reclaim's later steps arrive early */
const before = (a, b) => a.t < b.t || (a.t === b.t && a._n < b._n);
function hpush(r) { const h = ST.heap; r._n = ++ST.seqIn; h.push(r); let i = h.length - 1; while (i > 0) { const j = (i - 1) >> 1; if (!before(h[i], h[j])) break; [h[i], h[j]] = [h[j], h[i]]; i = j; } }
function hpop() {
  const h = ST.heap, top = h[0], last = h.pop(); if (h.length) { h[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < h.length && before(h[l], h[m])) m = l; if (r < h.length && before(h[r], h[m])) m = r; if (m === i) break; [h[i], h[m]] = [h[m], h[i]]; i = m; } }
  return top;
}

// a touch: who did it (hw, kern, lz, ua, ub) and whether it read or wrote
const touch = (key, who, w) => ST.fl.set(key, { who, w, at: performance.now() / 1000 });
const slotOf = (c, p) => ST.tlb[c].indexOf(p);
const frameNo = f => 'frame ' + f;
function ckAlloc(p) { if (!ST.ck.has(p)) ST.ck.set(p, ST.ckFree.length ? ST.ckFree.pop() : ST.ckN++); return ST.ck.get(p); }
function ckFree(p) { if (ST.ck.has(p)) { ST.ckFree.push(ST.ck.get(p)); ST.ck.delete(p); } }
function logLine(who, text) { ST.lines.push({ who, text, n: ++ST.seq }); if (ST.lines.length > 6) ST.lines.shift(); }

function apply(r) {
  const P = hex(r.p !== undefined ? r.p : 0);
  switch (r.k) {
    case 'a': {                                        // one access by the user SW: the CPU MMU looks in the TLB, the data is in a frame
      const e = ST.pf.get(r.p); if (e) touch('F' + e.f, r.i ? 'ub' : 'ua', false);
      if (r.hit) { const sl = slotOf(r.c, r.p); if (sl >= 0) touch('T' + r.c + '_' + sl, 'hw', false); }
      break;
    }
    case 'm':                                          // TLB miss: kernel SW reads the PTE
      touch('P' + r.p, 'kern', false);
      if (r.f) logLine('kern', `Core ${r.c} · TLB miss on page ${P}: read its PTE, it is invalid → page fault`);
      break;
    case 'tf': {                                       // kernel SW writes one TLB entry, pushing out the oldest
      const T = ST.tlb[r.c], A = ST.tlbAge[r.c]; let sl = T.indexOf(r.p);
      if (sl < 0 && r.out >= 0) sl = T.indexOf(r.out);
      if (sl < 0) sl = T.indexOf(-1);
      if (sl < 0) { sl = 0; for (let i = 1; i < A.length; i++) if (A[i] < A[sl]) sl = i; }
      T[sl] = r.p; A[sl] = ++ST.seq; touch('T' + r.c + '_' + sl, 'kern', true);
      break;
    }
    case 'tc': {                                       // reclaim: the page leaves this core's TLB
      const sl = slotOf(r.c, r.p); if (sl >= 0) { ST.tlb[r.c][sl] = -1; touch('T' + r.c + '_' + sl, 'kern', true); }
      logLine('kern', `clear page ${P} from Core ${r.c}'s TLB (mechanism unknown on this platform)`);
      break;
    }
    case 'tn': {                                       // the TLB size control moved
      for (let c = 0; c < ST.tlb.length; c++) {
        const keep = ST.tlb[c].map((p, i) => [p, ST.tlbAge[c][i]]).filter(([p]) => p >= 0).sort((a, b) => a[1] - b[1]).slice(-r.n);
        ST.tlb[c] = keep.map(x => x[0]); ST.tlbAge[c] = keep.map(x => x[1]);
        while (ST.tlb[c].length < r.n) { ST.tlb[c].push(-1); ST.tlbAge[c].push(0); }
      }
      break;
    }
    case 'pf':                                         // under mm_lock: take a free frame, read the COT entry, mark the page decompressing
      ST.pf.set(r.p, { f: r.f, st: 'D' }); ST.fr[r.f] = r.p; ST.frSt[r.f] = 2;
      touch('C' + r.p, 'kern', false); touch('F' + r.f, 'kern', true); ckAlloc(r.p);
      logLine('kern', `take free ${frameNo(r.f)}, read the COT entry of ${P}, hand DECOMPRESS to the LZ4 HW`);
      break;
    case 'dj': ST.jobs.push(r); touch('K' + ckAlloc(r.p), 'lz', false); logLine('lz', `DECOMPRESS: read the chunks of ${P}, write ${frameNo(r.f)}`); break;
    case 'pd': {
      const e = ST.pf.get(r.p); if (e) e.st = 'V'; ST.frSt[r.f] = 1;
      touch('C' + r.p, 'kern', true); touch('P' + r.p, 'kern', true); ckFree(r.p);
      logLine('kern', `clear the COT entry of ${P}, write its PTE valid → ${frameNo(r.f)}, fill Core ${r.c}'s TLB`);
      break;
    }
    case 'ev':                                         // reclaim: the clock picks a frame, the PTE goes invalid
      ST.hand = r.f; ST.pf.set(r.p, { f: r.f, st: 'K' }); if (r.f < ST.frSt.length) ST.frSt[r.f] = 3;
      touch('P' + r.p, 'kern', true);
      logLine('kern', `reclaim: the clock picks ${frameNo(r.f)} (page ${P}), write its PTE invalid`);
      break;
    case 'cj': ST.jobs.push(r); touch('K' + ckAlloc(r.p), 'lz', true); logLine('lz', `COMPRESS: read ${frameNo(r.f)}, write the chunks of ${P}`); break;
    case 'cd':
      if (ST.pf.get(r.p) && ST.pf.get(r.p).st === 'K') ST.pf.delete(r.p);
      if (ST.fr[r.f] === r.p) { ST.fr[r.f] = -1; ST.frSt[r.f] = 0; touch('F' + r.f, 'kern', true); }
      touch('C' + r.p, 'kern', true);
      logLine('kern', `write the COT entry of ${P}, put ${frameNo(r.f)} back on the free list`);
      break;
    case 'w': ST.win[r.i] = { c: r.c, base: r.base, off: ST.win[r.i].off }; break;
  }
}

function stateStep(s, now) {
  if (s.tr.length) { for (const r of s.tr) hpush(r); s.tr.length = 0; }
  while (ST.heap.length && ST.heap[0].t <= now) apply(hpop());
  ST.jobs = ST.jobs.filter(j => j.t1 > now);
}

/* ---------- drawing ---------- */
let SC = {};
function stateColors() {
  const mix = (a, b, t) => '#' + C(a).lerp(C(b), t).getHexString();
  SC = { ink: P.ink, mut: P.muted, line: P.line, paper: P.paper, bg: P.bg, kern: P.kern, lz: P.lz, ua: P.ua, ub: P.ub, hw: P.ink,
    uaT: mix(P.ua, P.paper, 0.55), ubT: mix(P.ub, P.paper, 0.55), uaL: mix(P.ua, P.paper, 0.8), ubL: mix(P.ub, P.paper, 0.8), lzT: mix(P.lz, P.paper, 0.72), lzP: mix(P.lz, P.paper, 0.9), kernT: mix(P.kern, P.paper, 0.8), dim: mix(P.paper, P.ink, 0.05), warn: P.warn };
  const pc = document.createElement('canvas'); pc.width = pc.height = 8; const g = pc.getContext('2d');
  g.fillStyle = SC.lzT; g.fillRect(0, 0, 8, 8); g.strokeStyle = SC.lz; g.lineWidth = 1.3; g.beginPath(); g.moveTo(0, 8); g.lineTo(8, 0); g.moveTo(-2, 2); g.lineTo(2, -2); g.moveTo(6, 10); g.lineTo(10, 6); g.stroke();
  SC.hatch = ST.g.createPattern(pc, 'repeat');
}
// the most cells of the given shape (w / h = asp) that fit n into a box
function grid(n, w, h, asp, maxW) {
  let best = { cols: 1, cw: 0, ch: 0 };
  for (let cols = 1; cols <= n; cols++) {
    const rows = Math.ceil(n / cols), cw = Math.min(w / cols, h / rows * asp, maxW || 1e9);
    if (cw > best.cw) best = { cols, cw, ch: cw / asp };
  }
  return best;
}
const progOf = p => p >= 0x40000 ? 1 : 0;
function ring(g, x, y, w, h, col, lw) { g.strokeStyle = col; g.lineWidth = lw; g.strokeRect(x + lw / 2, y + lw / 2, w - lw, h - lw); }
function fl(key, tNow) { const f = ST.fl.get(key); if (!f) return null; const a = 1 - (tNow - f.at) / FLASH; if (a <= 0) { ST.fl.delete(key); return null; } return { who: f.who, w: f.w, a }; }
function drawTouch(g, key, x, y, w, h, tNow) {
  const f = fl(key, tNow); if (!f) return;
  const col = SC[f.who];
  if (f.w) { g.globalAlpha = 0.85 * f.a; g.fillStyle = col; g.fillRect(x, y, w, h); g.globalAlpha = 1; }
  else { g.globalAlpha = Math.min(1, 0.4 + f.a); ring(g, x - 1.5, y - 1.5, w + 3, h + 3, col, 2.5); g.globalAlpha = 1; }
}
function head(g, x, y, title, sub) {
  g.textBaseline = 'alphabetic'; g.textAlign = 'left';
  g.font = '700 13.5px ' + DISP; g.fillStyle = SC.ink; g.fillText(title, x, y);
  if (sub) { g.font = '400 11.5px ' + MONO; g.fillStyle = SC.mut; g.fillText(sub, x, y + 15); }
}


/* ---------- where each part sits: boxes for a wide and a narrow panel ---------- */
function layout(W) {
  const pad = 14, L = { wide: W >= 880 };
  if (L.wide) {
    const Wp = Math.round(W * 0.63) - pad, cw = (Wp - 36) / 2;
    L.H = 610; L.user = [0, 1].map(c => ({ x: pad + 12 + c * (cw + 12) + 20, y: 8, w: cw - 40, h: 42 }));
    L.proc = { x: pad, y: 66, w: Wp, h: 300 };
    L.core = [0, 1].map(c => { const x = pad + 12 + c * (cw + 12), y = 92; return { x, y, w: cw, h: 186,
      mmu: { x: x + 8, y: y + 26, w: cw * 0.6 - 8, h: 152 }, km: { x: x + cw * 0.6 + 8, y: y + 26, w: cw * 0.4 - 16, h: 70 }, kf: { x: x + cw * 0.6 + 8, y: y + 104, w: cw * 0.4 - 16, h: 74 } }; });
    L.rec = { x: pad + 12, y: 286, w: Wp - 24, h: 38 };
    L.l2 = { x: pad + 12, y: 332, w: Wp - 24, h: 24 };
    L.lz = { x: pad + Wp + 40, y: 66, w: W - 2 * pad - Wp - 40, h: 236 };
    L.dram = { x: pad, y: 390, w: W - 2 * pad, h: L.H - 398 };
    const iw = L.dram.w - 40, ry = L.dram.y + 26, rh = L.dram.h - 36;
    L.pt = { x: pad + 10, y: ry, w: iw * 0.42, h: rh }; L.fr = { x: L.pt.x + L.pt.w + 10, y: ry, w: iw * 0.28, h: rh };
    L.ch = { x: L.fr.x + L.fr.w + 10, y: ry, w: L.dram.x + L.dram.w - 10 - (L.fr.x + L.fr.w + 10), h: rh };
  } else {
    const Wp = W - 2 * pad, cw = (Wp - 36) / 2;
    L.H = 1150; L.user = [0, 1].map(c => ({ x: pad + 12 + c * (cw + 12) + 6, y: 8, w: cw - 12, h: 42 }));
    L.proc = { x: pad, y: 66, w: Wp, h: 368 };
    L.core = [0, 1].map(c => { const x = pad + 12 + c * (cw + 12), y = 92, kw = (cw - 24) / 2; return { x, y, w: cw, h: 238,
      mmu: { x: x + 8, y: y + 26, w: cw - 16, h: 128 }, km: { x: x + 8, y: y + 162, w: kw, h: 68 }, kf: { x: x + 16 + kw, y: y + 162, w: kw, h: 68 } }; });
    L.rec = { x: pad + 12, y: 340, w: Wp - 24, h: 46 };
    L.l2 = { x: pad + 12, y: 396, w: Wp - 24, h: 26 };
    L.lz = { x: pad + Wp * 0.42, y: 452, w: Wp * 0.58, h: 206 };
    L.dram = { x: pad, y: 690, w: Wp, h: L.H - 698 };
    // narrow: frames and chunk pool right under the LZ4 HW, the kernel's tables below them
    const ry = L.dram.y + 26, iw = L.dram.w - 34;
    L.fr = { x: pad + 24, y: ry, w: (iw - 10) / 2, h: 210 };
    L.ch = { x: L.fr.x + L.fr.w + 10, y: ry, w: L.fr.w, h: 210 };
    L.pt = { x: pad + 24, y: ry + 220, w: iw, h: L.dram.y + L.dram.h - 10 - (ry + 220) };
  }
  return L;
}

/* ---------- lamps: how busy each part is at "now" ----------
   Close in (lens under 20) a lamp lights while its event runs and fades just after. Farther out its brightness is the
   share of the last ~1.2 s of screen time that part was busy, and the lamp prints that share. */
function lampLevels(s, now, lens) {
  const ev = s.ev, rate = SPEED * pace * Math.max(0.3, slow) * lens * BASE, far = lens >= 20;
  const FT = 0.45 * rate, Wt = 1.2 * rate, t0 = now - (far ? Wt : FT), acc = new Map();
  const add = (key, a, b) => {
    if (b < t0 || a > now) return;
    if (far) acc.set(key, (acc.get(key) || 0) + (Math.min(b, now) - Math.max(a, t0)) / Wt);
    else { const v = a <= now && now < b ? 1 : Math.max(0, 1 - (now - b) / FT); if (v > (acc.get(key) || 0)) acc.set(key, v); }
  };
  for (let i = ev.tick.length - 1; i >= 0; i--) {
    const e = ev.tick[i]; if (e.t > now) continue; if (e.t + e.d < t0 - 50) break;
    add('m' + e.core, e.t, e.t + e.d); add('l2', e.t, e.t + e.d); if (!e.l2) add('pd' + e.core, e.t, e.t + e.d);
  }
  for (const e of ev.fault) add('f' + e.core, e.t0, e.t1);
  for (const e of ev.wait) add('w' + e.prog, e.t0, e.t1);
  for (const e of ev.rec) add('r' + e.slot, e.t0, e.t1);
  const tick = far ? 0.02 * Wt : 1;                        // a short event: wide enough to see at every lens
  for (const e of ev.job) { add('e' + e.eng, e.t0, e.t0 + e.d); add(e.op === 'D' ? 'jd' : 'jc', e.t0, e.t0 + e.d); add('bell', e.t0, e.t0 + tick); }
  for (const e of ev.clr) add('clr', e.t, e.t + tick);
  return { far, v: k => acc.get(k) || 0 };
}

/* ---------- drawing ---------- */
function rr(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
function panel(g, b, fill, stroke, lw) { rr(g, b.x, b.y, b.w, b.h, 8); g.fillStyle = fill; g.fill(); g.strokeStyle = stroke; g.lineWidth = lw || 1.2; g.stroke(); }
function txt(g, s, x, y, font, col, al) { g.font = font; g.fillStyle = col; g.textAlign = al || 'left'; g.textBaseline = 'alphabetic'; g.fillText(s, x, y); g.textAlign = 'left'; }
const mixc = (a, b, t) => '#' + C(a).lerp(C(b), Math.max(0, Math.min(1, t))).getHexString();
// a wire: thin and grey when idle, thick, coloured and glowing when lit; the arrowhead only when lit
function wire(g, pts, col, lv, dash) {
  const on = lv > 0.04;
  g.save(); g.lineJoin = 'round'; g.setLineDash(dash || []);
  g.strokeStyle = on ? mixc(SC.line, col, 0.35 + 0.65 * lv) : SC.line; g.lineWidth = on ? 1.5 + 3 * lv : 1.2;
  if (on) { g.shadowColor = col; g.shadowBlur = 10 * lv; }
  g.beginPath(); g.moveTo(pts[0], pts[1]); for (let i = 2; i < pts.length; i += 2) g.lineTo(pts[i], pts[i + 1]); g.stroke();
  if (on) {
    const n = pts.length, x = pts[n - 2], y = pts[n - 1], a = Math.atan2(y - pts[n - 3], x - pts[n - 4]), s = 6 + 3 * lv;
    g.setLineDash([]); g.fillStyle = g.strokeStyle; g.beginPath(); g.moveTo(x, y); g.lineTo(x - s * Math.cos(a - 0.45), y - s * Math.sin(a - 0.45)); g.lineTo(x - s * Math.cos(a + 0.45), y - s * Math.sin(a + 0.45)); g.closePath(); g.fill();
  }
  g.restore();
}
// a lamp: its tint when dark, its colour when lit; far out it also prints how busy it was
function lamp(g, b, col, tint, lv, far, frac, l1, l2, dash) {
  g.save();
  if (lv > 0.04) { g.shadowColor = col; g.shadowBlur = 16 * lv; }
  rr(g, b.x, b.y, b.w, b.h, 7); g.fillStyle = mixc(tint, col, lv); g.fill(); g.restore();
  g.save(); g.setLineDash(dash || []); rr(g, b.x, b.y, b.w, b.h, 7); g.strokeStyle = col; g.lineWidth = lv > 0.5 ? 2.2 : 1.2; g.stroke(); g.restore();
  const ink = lv > 0.5 ? SC.paper : col, sub = lv > 0.5 ? SC.paper : SC.mut, cx = b.x + b.w / 2, small = b.w < 96;
  txt(g, l1, cx, b.y + b.h / 2 - (l2 || far ? 4 : -4), '700 ' + (small ? 11.5 : 12.5) + 'px ' + DISP, ink, 'center');
  const s2 = far ? `busy ${frac < 0.001 ? '0' : frac < 0.01 ? '<1' : Math.round(100 * Math.min(1, frac))}%` : l2;
  if (s2) txt(g, s2, cx, b.y + b.h / 2 + 13, (far ? '700 ' : '400 ') + (small ? 10 : 11) + 'px ' + MONO, sub, 'center');
}
function cellsTLB(g, c, b, tNow) {
  const n = ST.tlb[c].length, G = grid(n, b.w, b.h, 2.4, 64);
  for (let i = 0; i < n; i++) {
    const x = b.x + (i % G.cols) * G.cw, y = b.y + Math.floor(i / G.cols) * G.ch, w = G.cw - 3, h = G.ch - 3, p = ST.tlb[c][i];
    if (p < 0) { g.setLineDash([3, 3]); ring(g, x, y, w, h, SC.line, 1); g.setLineDash([]); }
    else { g.fillStyle = progOf(p) ? SC.ubL : SC.uaL; g.fillRect(x, y, w, h); ring(g, x, y, w, h, progOf(p) ? SC.ub : SC.ua, 1); }
    drawTouch(g, 'T' + c + '_' + i, x, y, w, h, tNow);
    if (p >= 0 && w >= 46) { g.font = '600 ' + (w >= 56 ? 11 : 10) + 'px ' + MONO; g.fillStyle = SC.ink; g.textAlign = 'center'; g.fillText(hex(p), x + w / 2, y + h / 2 + 4); g.textAlign = 'left'; }
  }
}
function cellsPT(g, s, b, tNow) {
  const ws = s.prm.ws, hP = b.h / 2;
  for (let i = 0; i < ST.win.length; i++) {
    const wn = ST.win[i], oy = b.y + i * hP, col = i ? SC.ub : SC.ua, colT = i ? SC.ubT : SC.uaT;
    txt(g, `user SW ${i ? 'B' : 'A'}: its ${ws} pages`, b.x, oy + 10, '700 11px ' + MONO, col);
    const G = grid(ws, b.w, hP - 22, 0.62, 22), y0 = oy + 18, hh = G.ch - 2;
    const inUse = o => ((o - wn.c) % ws + ws) % ws < RHY.SHORT;
    for (let o = 0; o < ws; o++) {
      const p = wn.off + ((wn.base + o) & RHY.MASK), x = b.x + (o % G.cols) * G.cw, y = y0 + Math.floor(o / G.cols) * G.ch, w = G.cw - 2;
      const e = ST.pf.get(p), hp = Math.round(hh * 0.52), hc = hh - hp - 1;
      if (e && e.st === 'V') { g.fillStyle = colT; g.fillRect(x, y, w, hp); } else ring(g, x, y, w, hp, SC.line, 1);
      if (e && e.st !== 'V') { g.fillStyle = SC.kern; g.beginPath(); g.arc(x + w / 2, y + hp / 2, Math.max(1.5, w / 5), 0, 7); g.fill(); }
      drawTouch(g, 'P' + p, x, y, w, hp, tNow);
      if (!e || e.st === 'D') { g.fillStyle = SC.hatch; g.fillRect(x, y + hp + 1, w, hc); }
      else { g.strokeStyle = SC.line; g.lineWidth = 1; g.beginPath(); g.moveTo(x, y + hp + hc); g.lineTo(x + w, y + hp + hc); g.stroke(); }
      drawTouch(g, 'C' + p, x, y + hp + 1, w, hc, tNow);
      if (inUse(o)) { g.fillStyle = col; g.fillRect(x, y - 3, G.cw, 2); }
    }
  }
}
function cellsFrames(g, s, b, now, tNow) {
  const F = s.prm.frames, GF = grid(F, b.w, b.h, 1, 18), jobAt = new Map();
  for (const j of ST.jobs) if (j.t <= now) jobAt.set(j.f, j.k);
  for (let f = 0; f < F; f++) {
    const x = b.x + (f % GF.cols) * GF.cw, y = b.y + Math.floor(f / GF.cols) * GF.ch, w = GF.cw - 2, h = GF.ch - 2, p = ST.fr[f], st = ST.frSt[f];
    if (p >= 0 && st) { g.fillStyle = progOf(p) ? SC.ubT : SC.uaT; g.fillRect(x, y, w, h); } else ring(g, x, y, w, h, SC.line, 1);
    const jk = jobAt.get(f);
    if (jk === 'dj') { g.fillStyle = SC.lz; g.globalAlpha = 0.8 + 0.2 * Math.sin(tNow * 9); g.fillRect(x - 1, y - 1, w + 2, h + 2); g.globalAlpha = 1; }
    else if (jk === 'cj') ring(g, x - 1.5, y - 1.5, w + 3, h + 3, SC.lz, 2.5);
    else if (st === 2 || st === 3) { g.fillStyle = SC.kern; g.beginPath(); g.arc(x + w / 2, y + h / 2, Math.max(1.5, w / 5), 0, 7); g.fill(); }
    drawTouch(g, 'F' + f, x, y, w, h, tNow);
    if (f === ST.hand) { g.fillStyle = SC.kern; g.beginPath(); g.moveTo(x + w / 2, y + h + 1); g.lineTo(x + w / 2 - 4, y + h + 7); g.lineTo(x + w / 2 + 4, y + h + 7); g.fill(); }
  }
}
function cellsChunks(g, b, tNow) {
  const n = Math.max(96, ST.ckN), G = grid(n, b.w, b.h, 0.5, 14), used = new Set(ST.ck.values());
  for (let i = 0; i < n; i++) {
    const x = b.x + (i % G.cols) * G.cw, y = b.y + Math.floor(i / G.cols) * G.ch, w = G.cw - 2, h = G.ch - 2;
    if (used.has(i)) { g.fillStyle = SC.hatch; g.fillRect(x, y, w, h); } else ring(g, x, y, w, h, SC.line, 1);
    drawTouch(g, 'K' + i, x, y, w, h, tNow);
  }
}

function stateDraw(s, now, lens) {
  const cv = ST.cv, W = cv.clientWidth; if (!W) return;
  const L = layout(W), H = L.H, dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (cv.height !== Math.round(H * dpr) || cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); cv.style.height = H + 'px'; }
  const g = ST.g, tNow = performance.now() / 1000; g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.fillStyle = SC.paper; g.fillRect(0, 0, W, H);
  const lv = lampLevels(s, now, lens), far = lv.far, b01 = v => far ? Math.min(1, v * 2) : v;
  const U = [SC.ua, SC.ub];

  /* boxes first, wires over the gaps, lamps and cells last */
  panel(g, L.proc, SC.bg, SC.line); txt(g, 'PROCESSOR', L.proc.x + 12, L.proc.y + 17, '700 11.5px ' + MONO, SC.mut);
  panel(g, L.dram, SC.bg, SC.line); txt(g, 'DRAM · physical address space', L.dram.x + 12, L.dram.y + 17, '700 11.5px ' + MONO, SC.mut);
  panel(g, L.lz, SC.lzP, SC.lz, 2);
  L.core.forEach((c, i) => { panel(g, c, SC.paper, SC.line); txt(g, 'Core ' + i, c.x + 10, c.y + 18, '700 13.5px ' + DISP, SC.ink); panel(g, c.mmu, SC.dim, SC.mut); });
  [L.pt, L.fr, L.ch].forEach(b => panel(g, { x: b.x, y: b.y, w: b.w, h: b.h }, SC.paper, SC.line));

  // wires: each access, each PTE read, the doorbell, the LZ4 HW's traffic, the TLB clear
  const busL = L.l2.y + L.l2.h, frTop = L.fr.y, ptTop = L.pt.y;
  L.core.forEach((c, i) => {
    const run = far ? 1 - Math.min(1, lv.v('w' + i)) : (lv.v('w' + i) > 0.5 ? 0 : 1), ux = c.mmu.x + c.mmu.w * 0.5, u = L.user[i];
    wire(g, [ux, u.y + u.h, ux, c.mmu.y], U[i], 0.75 * run);
    wire(g, [ux, c.mmu.y + c.mmu.h, ux, L.l2.y], U[i], 0.75 * run);
    const fx = L.fr.x + L.fr.w * (0.3 + 0.35 * i), bx = L.wide ? fx : L.fr.x + 20 + 30 * i, by = busL + 10 + 6 * i;
    wire(g, L.wide ? [ux, busL, ux, by, fx, by, fx, frTop] : [L.l2.x + 30 + 26 * i, busL, L.l2.x + 30 + 26 * i, frTop], U[i], 0.75 * run);
    const kx = c.km.x + c.km.w * 0.3, m = b01(lv.v('m' + i)), pdl = b01(lv.v('pd' + i));
    wire(g, L.wide ? [kx, c.km.y + c.km.h, kx, L.core[i].y + L.core[i].h] : [kx, c.km.y + c.km.h, kx, c.y + c.h], SC.kern, m);
    wire(g, [kx, c.y + c.h, kx, L.l2.y], SC.kern, m);
    const px = L.pt.x + L.pt.w * (0.3 + 0.3 * i), py = busL + 18 + 6 * i;
    const ex = L.l2.x + 4 + 6 * i;                        // narrow: down the left edge, past the frames, into the tables
    wire(g, L.wide ? [kx, busL, kx, py, px, py, px, ptTop] : [ex, busL, ex, ptTop + 14 + 8 * i, L.pt.x, ptTop + 14 + 8 * i], SC.kern, pdl);
  });
  // the doorbell: from the page fault lamps and the reclaimer to the LZ4 HW
  const bell = far ? Math.min(1, lv.v('bell') * 8) : lv.v('bell');
  const tx = L.wide ? L.proc.x + L.proc.w + 18 : L.lz.x + 30, tyIn = L.wide ? L.lz.y + L.lz.h - 50 : L.lz.y;
  if (L.wide) {
    const busY = L.core[0].y + L.core[0].h + 4;
    L.core.forEach((c, i) => { const x = c.kf.x + c.kf.w * 0.75; wire(g, [x, c.kf.y + c.kf.h, x, busY, tx, busY], SC.kern, Math.min(bell, b01(lv.v('f' + i))), [6, 4]); });
    wire(g, [L.rec.x + L.rec.w, L.rec.y + L.rec.h / 2, tx, L.rec.y + L.rec.h / 2], SC.kern, Math.min(bell, b01(Math.max(lv.v('r0'), lv.v('r1')))), [6, 4]);
    wire(g, [tx, L.rec.y + L.rec.h / 2, tx, tyIn, L.lz.x, tyIn], SC.kern, bell, [6, 4]);
    txt(g, '◀ doorbell: kernel SW hands a job', L.lz.x + 14, tyIn + 4, '400 11px ' + MONO, SC.kern);
  } else {
    wire(g, [tx, L.proc.y + L.proc.h, tx, L.lz.y], SC.kern, bell, [6, 4]);
    txt(g, 'doorbell from kernel SW', tx + 8, L.proc.y + L.proc.h + 14, '400 10.5px ' + MONO, SC.mut);
  }
  // the LZ4 HW reads and writes DRAM only: frames and the chunk pool
  const jd = b01(Math.min(1, lv.v('jd'))), jc = b01(Math.min(1, lv.v('jc')));
  const lzB = L.lz.y + L.lz.h, fX = L.fr.x + L.fr.w * (L.wide ? 0.85 : 0.75), cX = L.ch.x + L.ch.w * 0.5;
  const dX1 = L.lz.x + L.lz.w * 0.12, dX2 = L.lz.x + L.lz.w * 0.6, gy = L.wide ? lzB + 22 : lzB + 10;
  if (L.wide) {
    wire(g, [dX1, lzB, dX1, gy, fX, gy, fX, frTop], SC.lz, jd);                              // DECOMPRESS writes a frame
    wire(g, [fX - 18, frTop, fX - 18, gy + 12, dX1 + 22, gy + 12, dX1 + 22, lzB], SC.lz, jc);   // COMPRESS reads a frame
    wire(g, [cX + 10, L.ch.y, cX + 10, lzB], SC.lz, jd);                                        // DECOMPRESS reads chunks
    wire(g, [cX + 34, lzB, cX + 34, L.ch.y], SC.lz, jc);                                        // COMPRESS writes chunks
  } else {
    wire(g, [dX1, lzB, dX1, lzB + 8, fX, lzB + 8, fX, frTop], SC.lz, jd);
    wire(g, [fX - 18, frTop, fX - 18, lzB + 18, dX1 + 22, lzB + 18, dX1 + 22, lzB], SC.lz, jc);
    wire(g, [cX + 10, L.ch.y, cX + 10, lzB], SC.lz, jd); wire(g, [cX + 34, lzB, cX + 34, L.ch.y], SC.lz, jc);
  }
  if (jd > 0.04 || jc > 0.04) txt(g, jd >= jc ? 'DECOMPRESS: chunks → frame' : 'COMPRESS: frame → chunks', L.lz.x + 14, lzB - 12, '700 11.5px ' + MONO, SC.lz);
  // reclaim clears a page from every core's TLB: one dashed wire into each core's CPU MMU
  const clr = far ? Math.min(1, lv.v('clr') * 8) : lv.v('clr');
  const rx = L.rec.x + L.rec.w - RHY.INFLIGHT * ((L.wide ? 120 : 104) + 8) + 20;   // from the reclaim lamps
  if (clr > 0.04) L.core.forEach(c => wire(g, [rx, L.rec.y + 2, c.mmu.x + c.mmu.w * 0.85, c.y + c.h], SC.kern, clr, [4, 3]));

  /* user SW at the far end: running, or waiting for a page */
  L.user.forEach((u, i) => {
    const w = lv.v('w' + i), waiting = far ? w > 0.5 : w > 0.5, nm = 'user SW ' + (i ? 'B' : 'A');
    g.save(); if (!waiting) { g.shadowColor = U[i]; g.shadowBlur = 8; } rr(g, u.x, u.y, u.w, u.h, 8); g.fillStyle = waiting ? SC.paper : U[i]; g.fill(); g.restore();
    rr(g, u.x, u.y, u.w, u.h, 8); g.strokeStyle = U[i]; g.lineWidth = 2; g.stroke();
    txt(g, nm, u.x + u.w / 2, u.y + 18, '700 13px ' + DISP, waiting ? U[i] : SC.paper, 'center');
    const sub = far ? (w > 0.005 ? `runs on Core ${i} · waits ${Math.round(100 * Math.min(1, w))}%` : `runs on Core ${i} · every access → TLB`) : waiting ? 'waiting for a page' : `runs on Core ${i} · every access → TLB`;
    txt(g, sub, u.x + u.w / 2, u.y + 34, '400 11px ' + MONO, waiting ? SC.warn || U[i] : SC.paper, 'center');
  });

  /* each core: the CPU MMU with its TLB, and the kernel SW running on that core */
  L.core.forEach((c, i) => {
    txt(g, 'CPU MMU · hardware', c.mmu.x + 8, c.mmu.y + 15, '700 11px ' + MONO, SC.mut);
    txt(g, `TLB · ${ST.tlb[i].length} entries`, c.mmu.x + 8, c.mmu.y + c.mmu.h - 8, '400 10.5px ' + MONO, SC.mut);
    cellsTLB(g, i, { x: c.mmu.x + 8, y: c.mmu.y + 22, w: c.mmu.w - 16, h: c.mmu.h - 44 }, tNow);
    const m = lv.v('m' + i), f = lv.v('f' + i);
    lamp(g, c.km, SC.kern, SC.kernT, b01(m), far, m, 'TLB miss', 'refill the TLB');
    lamp(g, c.kf, SC.kern, SC.kernT, b01(f), far, f, 'page fault', 'job → LZ4 HW', [5, 3]);
  });
  // the reclaimer: kernel SW too, on some core; which one is not designed
  txt(g, 'kernel SW · reclaim', L.rec.x + 2, L.rec.y + 15, '700 11.5px ' + DISP, SC.kern);
  txt(g, `runs on some core · up to ${RHY.INFLIGHT} COMPRESS in flight`, L.rec.x + 2, L.rec.y + 30, '400 10.5px ' + MONO, SC.mut);
  for (let k = 0; k < RHY.INFLIGHT; k++) {
    const w = L.wide ? 120 : 104, b = { x: L.rec.x + L.rec.w - (RHY.INFLIGHT - k) * (w + 8), y: L.rec.y + 2, w, h: L.rec.h - 4 }, r = lv.v('r' + k);
    lamp(g, b, SC.kern, SC.kernT, b01(r), far, r, 'reclaim ' + (k + 1), null, [5, 3]);
  }
  // the shared L2: lights on each PTE read; a miss goes on to DRAM
  { const l = b01(Math.min(1, lv.v('l2'))); g.save(); if (l > 0.04) { g.shadowColor = SC.kern; g.shadowBlur = 8 * l; } panel(g, L.l2, mixc(SC.paper, SC.kernT, l), l > 0.04 ? SC.kern : SC.line); g.restore();
    txt(g, 'L2 cache · shared by all cores · PTE reads stop here on a hit', L.l2.x + L.l2.w / 2, L.l2.y + L.l2.h / 2 + 4, '700 11.5px ' + MONO, SC.ink, 'center'); }

  /* the LZ4 HW, beside DRAM and off the access path */
  txt(g, 'LZ4 HW', L.lz.x + 14, L.lz.y + 24, '700 17px ' + DISP, SC.lz);
  txt(g, 'compression layer hardware · shared', L.lz.x + 14, L.lz.y + 42, '400 11px ' + MONO, SC.mut);
  const ew = (L.lz.w - 28 - 3 * 8) / 4;
  for (let e = 0; e < RHY.ENGINES; e++) { const v = lv.v('e' + e); lamp(g, { x: L.lz.x + 14 + e * (ew + 8), y: L.lz.y + 54, w: ew, h: 46 }, SC.lz, SC.paper, b01(v), far, v, 'engine ' + e, null); }
  const ly = L.lz.y + 122;
  txt(g, 'not on the access path', L.lz.x + 14, ly, '700 12.5px ' + DISP, SC.ink);
  txt(g, 'works only when a page turns', L.lz.x + 14, ly + 18, '400 11px ' + MONO, SC.mut);
  txt(g, 'hot → cold (COMPRESS) or cold → hot', L.lz.x + 14, ly + 33, '400 11px ' + MONO, SC.mut);
  txt(g, '(DECOMPRESS) · P4: N = 4 for now', L.lz.x + 14, ly + 48, '400 11px ' + MONO, SC.mut);

  /* DRAM: the kernel's tables, the hot frames, the cold chunk pool */
  head(g, L.pt.x + 10, L.pt.y + 18, 'Page table + COT', 'kernel SW reads and writes · HW never · PTE above, COT below');
  cellsPT(g, s, { x: L.pt.x + 10, y: L.pt.y + 42, w: L.pt.w - 20, h: L.pt.h - 48 }, tNow);
  head(g, L.fr.x + 10, L.fr.y + 18, `Frame region · hot · ${s.prm.frames}`, 'uncompressed · a TLB entry points here');
  cellsFrames(g, s, { x: L.fr.x + 10, y: L.fr.y + 42, w: L.fr.w - 20, h: L.fr.h - 52 }, now, tNow);
  head(g, L.ch.x + 10, L.ch.y + 18, 'Chunk pool · cold', 'compressed · one cell per page here');
  cellsChunks(g, { x: L.ch.x + 10, y: L.ch.y + 42, w: L.ch.w - 20, h: L.ch.h - 50 }, tNow);

  // the step log: only while the lens is close enough to follow single events
  const key = lens < 30 ? ST.lines.map(l => l.n).join(',') : 'far';
  if (key !== ST.logKey) {
    ST.logKey = key;
    if (lens >= 30) ST.log.innerHTML = '<p class="far">At this time lens there are too many events to list one by one. The lamps show how busy each part was; the tables still update.</p>';
    else ST.log.innerHTML = ST.lines.length ? ST.lines.map((l, i) => `<p class="${i === ST.lines.length - 1 ? 'new' : ''}"><b class="${l.who}">${l.who === 'lz' ? 'LZ4 HW' : 'kernel SW'}</b>${l.text}</p>`).join('') : '<p class="far">Page faults and reclaims are listed here step by step.</p>';
  }
}

/* ---------- two rhythms: the tables at "now" ----------
   The model runs ahead of the picture, so the panel keeps its own copy of the tables and applies each
   recorded read or write only when "now" reaches its time. Who touches what (P1, interface spec):
   TLB: read by the CPU MMU hardware, written by kernel SW. Page table and COT: kernel SW only.
   Frames: the user SW's data; the LZ4 HW reads them for COMPRESS and writes them for DECOMPRESS.
   The chunk pool that holds the compressed data is not drawn. */
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
      touch('C' + r.p, 'kern', false); touch('F' + r.f, 'kern', true);
      logLine('kern', `take free ${frameNo(r.f)}, read the COT entry of ${P}, hand DECOMPRESS to the LZ4 HW`);
      break;
    case 'dj': ST.jobs.push(r); logLine('lz', `DECOMPRESS: read the chunks of ${P}, write ${frameNo(r.f)}`); break;
    case 'pd': {
      const e = ST.pf.get(r.p); if (e) e.st = 'V'; ST.frSt[r.f] = 1;
      touch('C' + r.p, 'kern', true); touch('P' + r.p, 'kern', true);
      logLine('kern', `clear the COT entry of ${P}, write its PTE valid → ${frameNo(r.f)}, fill Core ${r.c}'s TLB`);
      break;
    }
    case 'ev':                                         // reclaim: the clock picks a frame, the PTE goes invalid
      ST.hand = r.f; ST.pf.set(r.p, { f: r.f, st: 'K' }); if (r.f < ST.frSt.length) ST.frSt[r.f] = 3;
      touch('P' + r.p, 'kern', true);
      logLine('kern', `reclaim: the clock picks ${frameNo(r.f)} (page ${P}), write its PTE invalid`);
      break;
    case 'cj': ST.jobs.push(r); logLine('lz', `COMPRESS: read ${frameNo(r.f)}, write the chunks of ${P}`); break;
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
    uaT: mix(P.ua, P.paper, 0.55), ubT: mix(P.ub, P.paper, 0.55), uaL: mix(P.ua, P.paper, 0.8), ubL: mix(P.ub, P.paper, 0.8), lzT: mix(P.lz, P.paper, 0.72), kernT: mix(P.kern, P.paper, 0.8) };
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

function stateDraw(s, now, lens) {
  const cv = ST.cv, W = cv.clientWidth; if (!W) return;
  const wide = W >= 880, pad = 14, gap = 26;
  const H = wide ? 272 : 660;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (cv.height !== Math.round(H * dpr) || cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); cv.style.height = H + 'px'; }
  const g = ST.g, tNow = performance.now() / 1000; g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.fillStyle = SC.paper; g.fillRect(0, 0, W, H);
  // three blocks: TLBs, page table with COT, frames
  let bT, bP, bF;
  if (wide) {
    const wT = Math.max(230, Math.min(290, W * 0.23)), wF = Math.max(240, W * 0.26), wP = W - 2 * pad - wT - wF - 2 * gap;
    bT = { x: pad, y: 10, w: wT, h: H - 20 }; bP = { x: pad + wT + gap, y: 10, w: wP, h: H - 20 }; bF = { x: pad + wT + wP + 2 * gap, y: 10, w: wF, h: H - 20 };
  } else {
    bT = { x: pad, y: 10, w: W - 2 * pad, h: 170 }; bP = { x: pad, y: 196, w: W - 2 * pad, h: 260 }; bF = { x: pad, y: 476, w: W - 2 * pad, h: 176 };
  }
  // dividers
  g.strokeStyle = SC.line; g.lineWidth = 1;
  if (wide) [bP.x - gap / 2, bF.x - gap / 2].forEach(x => { g.beginPath(); g.moveTo(x, 12); g.lineTo(x, H - 12); g.stroke(); });

  /* TLBs: one per core, read by the CPU MMU hardware, written by kernel SW */
  head(g, bT.x, bT.y + 13, 'TLB · per core', 'read: CPU MMU HW · write: kernel SW');
  const n = ST.tlb[0].length, twoCol = !wide, tw = twoCol ? (bT.w - gap) / 2 : bT.w, th = twoCol ? bT.h - 40 : (bT.h - 40) / 2 - 6;
  for (let c = 0; c < ST.tlb.length; c++) {
    const ox = bT.x + (twoCol ? c * (tw + gap) : 0), oy = bT.y + 40 + (twoCol ? 0 : c * (th + 12));
    g.font = '700 11.5px ' + MONO; g.fillStyle = SC.mut; g.fillText('Core', ox, oy + 12); g.fillText(String(c), ox, oy + 26);
    const G = grid(n, tw - 40, th, 2.4, 64), x0 = ox + 40, y0 = oy;
    for (let i = 0; i < n; i++) {
      const x = x0 + (i % G.cols) * G.cw, y = y0 + Math.floor(i / G.cols) * G.ch, w = G.cw - 3, h = G.ch - 3, p = ST.tlb[c][i];
      if (p < 0) { g.setLineDash([3, 3]); ring(g, x, y, w, h, SC.line, 1); g.setLineDash([]); }
      else { g.fillStyle = progOf(p) ? SC.ubL : SC.uaL; g.fillRect(x, y, w, h); ring(g, x, y, w, h, progOf(p) ? SC.ub : SC.ua, 1); }
      drawTouch(g, 'T' + c + '_' + i, x, y, w, h, tNow);
      if (p >= 0 && w >= 46) { g.font = '600 ' + (w >= 56 ? 11 : 10) + 'px ' + MONO; g.fillStyle = SC.ink; g.textAlign = 'center'; g.fillText(hex(p), x + w / 2, y + h / 2 + 4); g.textAlign = 'left'; }
    }
  }

  /* page table and COT: one PTE and one COT entry per page, kernel SW only */
  head(g, bP.x, bP.y + 13, 'Page table + COT · kernel memory', 'read and write: kernel SW only · each page: PTE above, COT entry below');
  const ws = s.prm.ws, hP = (bP.h - 40) / 2;
  for (let i = 0; i < ST.win.length; i++) {
    const wn = ST.win[i], oy = bP.y + 42 + i * hP, col = i ? SC.ub : SC.ua, colT = i ? SC.ubT : SC.uaT;
    g.font = '700 11.5px ' + MONO; g.fillStyle = col; g.fillText(`user SW ${i ? 'B' : 'A'}: its ${ws} pages`, bP.x, oy + 9);
    const G = grid(ws, bP.w, hP - 26, 0.62, 22), y0 = oy + 20, hh = G.ch - 2;
    const inUse = o => ((o - wn.c) % ws + ws) % ws < RHY.SHORT;
    for (let o = 0; o < ws; o++) {
      const p = wn.off + ((wn.base + o) & RHY.MASK), x = bP.x + (o % G.cols) * G.cw, y = y0 + Math.floor(o / G.cols) * G.ch, w = G.cw - 2;
      const e = ST.pf.get(p), hp = Math.round(hh * 0.52), hc = hh - hp - 1;
      // PTE: valid, filled; invalid, empty outline; a purple dot while the page is moving
      if (e && e.st === 'V') { g.fillStyle = colT; g.fillRect(x, y, w, hp); } else ring(g, x, y, w, hp, SC.line, 1);
      if (e && e.st !== 'V') { g.fillStyle = SC.kern; g.beginPath(); g.arc(x + w / 2, y + hp / 2, Math.max(1.5, w / 5), 0, 7); g.fill(); }
      drawTouch(g, 'P' + p, x, y, w, hp, tNow);
      // COT entry: valid while the page is compressed, hatched
      const cotValid = !e || e.st === 'D';
      if (cotValid) { g.fillStyle = SC.hatch; g.fillRect(x, y + hp + 1, w, hc); }
      else { g.strokeStyle = SC.line; g.lineWidth = 1; g.beginPath(); g.moveTo(x, y + hp + hc); g.lineTo(x + w, y + hp + hc); g.stroke(); }
      drawTouch(g, 'C' + p, x, y + hp + 1, w, hc, tNow);
      // the pages in use right now: a bar above
      if (inUse(o)) { g.fillStyle = col; g.fillRect(x, y - 3, G.cw, 2); }
    }
  }

  /* frames: the user SW's data; the LZ4 HW writes them for DECOMPRESS and reads them for COMPRESS */
  const F = s.prm.frames;
  head(g, bF.x, bF.y + 13, `Frames · DRAM · ${F}`, 'user SW data · LZ4 HW reads and writes');
  const GF = grid(F, bF.w, bF.h - 44, 1, 18), fy0 = bF.y + 40, jobAt = new Map();
  for (const j of ST.jobs) if (j.t <= now) jobAt.set(j.f, j.k);
  for (let f = 0; f < F; f++) {
    const x = bF.x + (f % GF.cols) * GF.cw, y = fy0 + Math.floor(f / GF.cols) * GF.ch, w = GF.cw - 2, h = GF.ch - 2, p = ST.fr[f], st = ST.frSt[f];
    if (p >= 0 && st) { g.fillStyle = progOf(p) ? SC.ubT : SC.uaT; g.fillRect(x, y, w, h); } else ring(g, x, y, w, h, SC.line, 1);
    const jk = jobAt.get(f);
    if (jk === 'dj') { g.fillStyle = SC.lz; g.globalAlpha = 0.8 + 0.2 * Math.sin(tNow * 9); g.fillRect(x - 1, y - 1, w + 2, h + 2); g.globalAlpha = 1; }
    else if (jk === 'cj') ring(g, x - 1.5, y - 1.5, w + 3, h + 3, SC.lz, 2.5);
    else if (st === 2 || st === 3) { g.fillStyle = SC.kern; g.beginPath(); g.arc(x + w / 2, y + h / 2, Math.max(1.5, w / 5), 0, 7); g.fill(); }
    drawTouch(g, 'F' + f, x, y, w, h, tNow);
    if (f === ST.hand) { g.fillStyle = SC.kern; g.beginPath(); g.moveTo(x + w / 2, y + h + 1); g.lineTo(x + w / 2 - 4, y + h + 7); g.lineTo(x + w / 2 + 4, y + h + 7); g.fill(); }
  }

  // the step log: only while the lens is close enough to follow single events
  const key = lens < 30 ? ST.lines.map(l => l.n).join(',') : 'far';
  if (key !== ST.logKey) {
    ST.logKey = key;
    if (lens >= 30) ST.log.innerHTML = '<p class="far">At this time lens there are too many events to list one by one. The tables above still update.</p>';
    else ST.log.innerHTML = ST.lines.length ? ST.lines.map((l, i) => `<p class="${i === ST.lines.length - 1 ? 'new' : ''}"><b class="${l.who}">${l.who === 'lz' ? 'LZ4 HW' : 'kernel SW'}</b>${l.text}</p>`).join('') : '<p class="far">Page faults and reclaims are listed here step by step.</p>';
  }
}

/* ---------- two rhythms: the model behind the two-sides animation ----------
   One user SW program per core. Every access goes to the core's TLB. A TLB hit needs no kernel.
   A TLB miss is an exception: kernel SW reads the PTE (P1). A valid PTE: fill the TLB, done.
   An invalid PTE: page fault, kernel SW takes a frame and hands a DECOMPRESS job to the LZ4 HW.
   When free frames run low, a reclaimer picks a cold page with a clock, sets its PTE invalid,
   clears it from every core's TLB and hands a COMPRESS job to the LZ4 HW.
   Every size, cost and the access pattern are examples chosen to show the contrast. Nothing here
   is measured on the platform. Works in the page (global RHY) and in node (module.exports). */
(function (root) {
'use strict';
const NCORE = 2;               // one user SW program per core
const SHORT = 24;              // pages one program uses within a short stretch of time
const STEP = 40;               // accesses before that short stretch moves on by one page
const ENGINES = 4;             // P4: the LZ4 HW takes N jobs at once, N = 4 for now
const INFLIGHT = 2;            // COMPRESS jobs the reclaimer keeps in flight
const PTE_PER_LINE = 8;        // PTEs in one cache line of the page table
const LPP = 64;                // cache lines in one page, like a 4 KB page with 64-byte lines; the platform's sizes are not known
const MASK = 0x3FFFF, NPG = 0x80000, FMAX = 2048;
// relative time units; one access that hits the TLB takes 1
const COST = { access: 1, refillL2: 2, refillDram: 6, lockA: 6, decomp: 30, lockB: 6, recA: 4, comp: 60, recB: 4 };
// l2: cache lines, data or PTE alike. lines: how many of a page's LPP lines a program actually uses
const DEF = { ws: 160, drift: 5, tlb: 16, frames: 360, l2: 1024, lines: 8 };
const RANGE = { ws: [32, 1024], drift: [0, 120], tlb: [4, 128], frames: [64, 1024], l2: [8, 4096], lines: [1, LPP] };

function rng32(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

function create(opt) {
  opt = opt || {};
  const prm = Object.assign({}, DEF, opt.prm || {});
  const nprog = opt.progs || NCORE;
  const frameOf = new Int32Array(NPG).fill(-1), ref = new Uint8Array(NPG), compT = new Float64Array(NPG);
  const frames = new Int32Array(FMAX).fill(-1);
  const tlb = [], l2 = new Map(), engFree = new Array(ENGINES).fill(0), slotEnd = new Array(INFLIGHT).fill(0);
  let free = [], pending = [], hand = 0, rt = 0;
  const ev = { acc: [], tick: [], fault: [], wait: [], rec: [], clr: [], job: [] };
  const cnt = { acc: 0, refill: [0, 0], fault: 0, evict: 0, waitFrame: 0, waitComp: 0, refillDram: 0, missDataL2: 0 };
  const progs = [];
  // lr picks the line inside a page from its own stream, so the pages a program touches do not depend on lines
  for (let i = 0; i < nprog; i++) { tlb.push(new Map()); progs.push({ i, core: i, off: i * 0x40000, base: 0x2A0 + i * 0x150, c: 0, k: 0, dacc: 0, t: i * 0.5, rng: rng32((opt.seed || 7) * 31 + i), lr: rng32((opt.seed || 7) * 31 + i + 977) }); }
  // tr: what each step reads or writes, with its time, for the table panel. Recording it changes nothing in the model.
  const s = { prm, ev, cnt, progs, recAcc: false, nprog, tr: [] };
  let booted = false;
  const tr = r => { if (booted) s.tr.push(r); };

  const l2touch = key => { if (l2.has(key)) l2.delete(key); l2.set(key, 1); while (l2.size > prm.l2) l2.delete(l2.keys().next().value); };
  const pteKey = p => -1 - Math.floor(p / PTE_PER_LINE);
  const dropPage = p => { for (let l = 0; l < LPP; l++) l2.delete(p * LPP + l); };   // the frame's data changed: its lines leave the L2
  const tlbFill = (core, p) => { const m = tlb[core]; let out = -1; if (m.has(p)) m.delete(p); m.set(p, 1); while (m.size > prm.tlb) { out = m.keys().next().value; m.delete(out); } return out; };
  const pageAt = (P, off) => P.off + ((P.base + (P.c + off) % prm.ws) & MASK);

  // boot: each program's long-term working set is in frames, its short-term pages are in its TLB
  function boot(plant) {
    for (let f = prm.frames - 1; f >= 0; f--) free.push(f);
    for (let o = 0; o < prm.ws; o++) for (const P of progs) {
      const p = pageAt(P, o);
      if (plant && P.i === 0 && o === SHORT) continue;      // one page that was pushed out before the story starts
      if (!free.length) break;
      const f = free.pop(); frames[f] = p; frameOf[p] = f; ref[p] = 1;
    }
    for (const P of progs) for (let o = Math.min(prm.tlb, SHORT) - 1; o >= 0; o--) { const p = pageAt(P, o); if (frameOf[p] >= 0) tlbFill(P.core, p); }
  }
  boot(opt.plant);
  // the state the panel starts from
  s.snap = () => ({ frames: Array.from(frames), tlb: tlb.map(m => [...m.keys()]), win: progs.map(P => ({ c: P.c, base: P.base, off: P.off })), hand });
  booted = true;
  s.planted = opt.plant ? pageAt(progs[0], SHORT) : -1;

  function nextPage(P) {
    if (++P.k >= STEP) { P.k = 0; P.c = (P.c + 1) % prm.ws; tr({ k: 'w', t: P.t, i: P.i, c: P.c, base: P.base }); }
    P.dacc += prm.drift / 10000;
    if (P.dacc >= 1) { P.dacc -= 1; P.base = (P.base + 1) & MASK; tr({ k: 'w', t: P.t, i: P.i, c: P.c, base: P.base }); return P.off + ((P.base + prm.ws - 1) & MASK); }   // the newest page is used at once
    return pageAt(P, Math.floor(P.rng() * Math.min(SHORT, prm.ws)));
  }
  const engine = t => { let e = 0; for (let i = 1; i < ENGINES; i++) if (engFree[i] < engFree[e]) e = i; return { e, start: Math.max(t, engFree[e]) }; };

  // the clock: skip pages used since the hand last passed, and pages whose job is still running
  function pick() {
    for (let n = 0; n < 2 * FMAX; n++) {
      const f = hand; hand = (hand + 1) % FMAX; const p = frames[f];
      if (p < 0) continue;
      if (ref[p]) { ref[p] = 0; continue; }
      return f;
    }
    return -1;
  }
  function reclaim(t) {
    const low = Math.max(2, Math.round(prm.frames / 32)), high = 2 * low;
    let avail = free.length + pending.length;
    if (avail >= low) return;
    while (avail < high) {
      const f = pick(); if (f < 0) return;
      if (evict(f, t)) avail++;
    }
  }
  // push one page out of frame f: PTE invalid, cleared from every TLB, COMPRESS; true if f is a frame that stays in use
  function evict(f, t) {
      const p = frames[f]; let sl = 0; for (let i = 1; i < INFLIGHT; i++) if (slotEnd[i] < slotEnd[sl]) sl = i;
      const t0 = Math.max(t, rt, slotEnd[sl]);
      frameOf[p] = -1; const had = []; tlb.forEach((m, c) => { if (m.has(p)) had.push(c); m.delete(p); });  // PTE invalid, then cleared from every core's TLB
      ev.clr.push({ t: t0 + COST.recA / 2, p });
      const j = engine(t0 + COST.recA); engFree[j.e] = j.start + COST.comp;
      ev.job.push({ eng: j.e, t0: j.start, d: COST.comp, op: 'C', p });
      const rel = j.start + COST.comp + COST.recB;
      tr({ k: 'ev', t: t0, p, f }); had.forEach(c => tr({ k: 'tc', t: t0 + COST.recA / 2, c, p }));
      tr({ k: 'cj', t: j.start, t1: j.start + COST.comp, p, f, e: j.e }); tr({ k: 'cd', t: rel, p, f });
      ev.rec.push({ t0, t1: rel, p, slot: sl });
      slotEnd[sl] = rel; rt = t0 + COST.recA; compT[p] = rel;
      frames[f] = -1; dropPage(p); cnt.evict++;
      if (f >= prm.frames) return false;
      let i = pending.length; while (i > 0 && pending[i - 1].t > rel) i--; pending.splice(i, 0, { t: rel, f });
      return true;
  }
  function takeFrame(t) {
    while (pending.length && pending[0].t <= t) free.push(pending.shift().f);
    if (free.length) return { f: free.pop(), at: t };
    if (!pending.length) reclaim(t);
    if (!pending.length) return null;
    const r = pending.shift(); return { f: r.f, at: r.t };
  }

  function stepProg(P) {
    const t = P.t, p = nextPage(P), core = P.core, m = tlb[core];
    // one line of the page; whether it was already in the L2 does not change the access time in this model, it is only counted
    const dk = p * LPP + Math.floor(P.lr() * prm.lines), dIn = frameOf[p] >= 0 && l2.has(dk);
    cnt.acc++; l2touch(dk); ref[p] = 1;
    if (s.recAcc) { ev.acc.push({ t, prog: P.i }); tr({ k: 'a', t, i: P.i, c: core, p, hit: m.has(p) }); }
    if (m.has(p)) { m.delete(p); m.set(p, 1); P.t = t + COST.access; return; }
    // TLB miss: an exception, the kernel reads the PTE. Its cache line may or may not be in the L2.
    const k = pteKey(p), inL2 = l2.has(k); l2touch(k);
    const d = inL2 ? COST.refillL2 : COST.refillDram; if (!inL2) cnt.refillDram++;
    cnt.refill[core]++; if (dIn) cnt.missDataL2++;
    tr({ k: 'm', t, d, c: core, p, l2: inL2, f: frameOf[p] < 0 });
    if (frameOf[p] >= 0) { ev.tick.push({ t, d, core, l2: inL2, dl2: dIn }); tr({ k: 'tf', t: t + d, c: core, p, out: tlbFill(core, p) }); P.t = t + d + COST.access; return; }
    // the PTE is invalid: page fault
    ev.tick.push({ t, d, core, l2: inL2, fault: true });
    const t1 = t + d, t2 = t1 + COST.lockA;
    const fr = takeFrame(t2); if (!fr) { P.t = t + d + COST.access; return; }
    let tF = Math.max(t2, fr.at); if (fr.at > t2) cnt.waitFrame++;
    if (compT[p] > tF) { tF = compT[p]; cnt.waitComp++; }    // its own COMPRESS is still running
    tr({ k: 'pf', t: Math.max(t2, fr.at), c: core, p, f: fr.f });
    const j = engine(tF); engFree[j.e] = j.start + COST.decomp;
    ev.job.push({ eng: j.e, t0: j.start, d: COST.decomp, op: 'D', p });
    const tB = j.start + COST.decomp + COST.lockB;
    tr({ k: 'dj', t: j.start, t1: j.start + COST.decomp, p, f: fr.f, e: j.e });
    frames[fr.f] = p; frameOf[p] = fr.f; dropPage(p);
    tr({ k: 'pd', t: tB, c: core, p, f: fr.f }); tr({ k: 'tf', t: tB, c: core, p, out: tlbFill(core, p) });
    ev.fault.push({ t0: t1, t1: tB, core, prog: P.i, p, tw: tF > t2 ? [t2, tF] : null });
    ev.wait.push({ prog: P.i, t0: t, t1: tB, p });
    cnt.fault++;
    P.t = tB + COST.access;
    reclaim(t1);
  }

  s.advance = function (tEnd, maxSteps) {
    let n = 0; maxSteps = maxSteps || 3e6;
    for (;;) {
      let P = progs[0]; for (const q of progs) if (q.t < P.t) P = q;
      if (P.t >= tEnd || n++ > maxSteps) return n;
      stepProg(P);
    }
  };
  s.steps = function (n) { const a = cnt.acc + n; while (cnt.acc < a) { let P = progs[0]; for (const q of progs) if (q.t < P.t) P = q; stepProg(P); } };
  s.minT = () => Math.min(...progs.map(P => P.t));
  s.set = function (k, v) {
    const old = prm[k]; prm[k] = v;
    const t = s.minT();
    if (k === 'ws') for (const P of progs) { P.c %= v; tr({ k: 'w', t, i: P.i, c: P.c, base: P.base }); }
    if (k === 'tlb') { tlb.forEach((m, c) => { while (m.size > v) { const q = m.keys().next().value; m.delete(q); tr({ k: 'tc', t, c, p: q }); } }); tr({ k: 'tn', t, n: v }); }
    if (k === 'l2') while (l2.size > v) l2.delete(l2.keys().next().value);
    if (k === 'frames') {
      if (v > old) for (let f = old; f < v; f++) if (frames[f] < 0) free.push(f);
      free = free.filter(f => f < v); pending = pending.filter(r => r.f < v);
      if (v < old) { for (let f = v; f < old; f++) if (frames[f] >= 0) evict(f, t); }   // pages in frames that no longer exist must go
    }
  };
  // drop what has scrolled out of view
  s.prune = function (tMin) {
    for (const key of Object.keys(ev)) {
      const a = ev[key]; let i = 0;
      const end = e => e.t1 !== undefined ? e.t1 : e.d !== undefined ? e.t0 !== undefined ? e.t0 + e.d : e.t + e.d : e.t;
      while (i < a.length && end(a[i]) < tMin) i++;
      if (i > 2000 || i > a.length / 2) ev[key] = a.slice(i);
    }
  };
  s.frameStats = () => { let used = 0; for (let f = 0; f < FMAX; f++) if (frames[f] >= 0) used++; return { used, free: free.length, pending: pending.length }; };
  return s;
}

const RHY = { create, DEF, RANGE, COST, SHORT, STEP, ENGINES, NCORE, INFLIGHT, MASK, FMAX, LPP, PTE_PER_LINE };
if (typeof module !== 'undefined' && module.exports) module.exports = RHY; else root.RHY = RHY;
})(typeof window !== 'undefined' ? window : this);

/* ---------- two rhythms: what the model has produced, laid on the tracks ----------
   lens = time units per world unit. Everything is placed again every frame from the model's events. */
const COL = {};
function colors() {
  COL.kern = C(P.kern); COL.kernL = C(P.kern).lerp(C(P.paper), 0.4); COL.lz = C(P.lz); COL.lzD = C(P.lz).lerp(C(P.ink), 0.35);
  COL.ua = C(P.ua); COL.ub = C(P.ub); COL.warn = C(P.warn); COL.paper = C(P.paper); COL.lit = C(P.flash).lerp(C(P.lz), 0.25);
}
const BIN = 0.4, BASE = 2;                              // at lens ×1 one world unit is BASE time units
function draw(s, now, lens) {
  const tpw = lens * BASE, k = 1 / tpw, tMin = now - XB * tpw, X = t => (t - now) * k, ev = s.ev;
  const out = { tick: [0, 0], refillTime: [0, 0], fault: 0, rec: 0, last: [null, null], faultNow: [], recNow: [], jobNow: [], waitNow: [], clrRecent: null, faultTick: null };
  begin();
  // TLB misses: one tick each while they can be told apart, a band whose height is the busy share once they cannot
  const band = lens >= 60, NB = Math.ceil(XB / BIN) + 1, busy = band ? [new Float32Array(NB), new Float32Array(NB)] : null;
  for (let i = ev.tick.length - 1; i >= 0; i--) {
    const e = ev.tick[i];
    if (e.t > now) continue;
    if (e.t + e.d < tMin) break;
    out.tick[e.core]++; out.refillTime[e.core] += e.d;
    if (!out.last[e.core]) out.last[e.core] = e;
    if (e.fault) {                                         // meeting point one: this TLB miss finds the PTE invalid
      const x = X(e.t), z0 = LANE.cpu[e.core], z1 = LANE.comp[e.core];
      put(MK.link, x, 0.1, (z0 + z1) / 2, 0.16, 0.08, Math.abs(z1 - z0));
      put(MK.diam, x, 2.2, z0, 0.6, 0.6, 0.6, COL.warn);
      if (!out.faultTick || e.t > out.faultTick.t) out.faultTick = e;
    }
    if (band) { const b = Math.floor(-X(e.t) / BIN); if (b >= 0 && b < NB) busy[e.core][b] += e.d; }
    else put(MK.tick, X(e.t + e.d / 2), e.fault ? 1.0 : 0.7, LANE.cpu[e.core], Math.max(e.d * k, 0.12), e.fault ? 2.0 : 1.4, 1.5);
  }
  if (band) for (let c = 0; c < 2; c++) for (let b = 0; b < NB; b++) {
    const f = busy[c][b] / (BIN * tpw); if (f <= 0) continue;
    const h = 0.15 + 1.6 * Math.min(1, f);
    put(MK.band, -(b + 0.5) * BIN, h / 2, LANE.cpu[c], BIN * 1.02, h, 1.5);
  }
  // big work on the compression layer side: page faults on the faulting core's lane, reclaim on its own two lanes
  const blk = (e, z, col) => {
    const a = Math.max(e.t0, tMin), b = Math.min(e.t1, now), x0 = X(a), x1 = X(b);
    put(MK.block, (x0 + x1) / 2, 0.45, z, Math.max(x1 - x0, 0.3), 0.9, 1.15, col);
  };
  for (const e of ev.fault) {
    if (e.t0 > now || e.t1 < tMin) continue;
    out.fault++; blk(e, LANE.comp[e.core], COL.kern);
    if (e.tw && e.tw[0] < now) { const a = X(Math.max(e.tw[0], tMin)), b = X(Math.min(e.tw[1], now)); put(MK.wait, (a + b) / 2, 0.95, LANE.comp[e.core], Math.max(b - a, 0.2), 0.12, 1.2); }
    if (e.t1 > now) out.faultNow.push(e);
  }
  for (const e of ev.rec) {
    if (e.t0 > now || e.t1 < tMin) continue;
    out.rec++; blk(e, LANE.comp[2 + e.slot], COL.kernL);
    if (e.t1 > now) out.recNow.push(e);
  }
  for (const e of ev.clr) {                                // meeting point two: cleared from every core's TLB
    if (e.t > now || e.t < tMin) continue;
    const x = X(e.t), z0 = LANE.cpu[0], z1 = LANE.comp[2];
    put(MK.diam, x, 2.2, LANE.cpu[0], 1, 1, 1, COL.kern); put(MK.diam, x, 2.2, LANE.cpu[1], 1, 1, 1, COL.kern);
    put(MK.link, x, 0.1, (z0 + z1) / 2, 0.16, 0.08, Math.abs(z1 - z0));
    if (!out.clrRecent || e.t > out.clrRecent.t) out.clrRecent = e;
  }
  for (const e of ev.job) {
    if (e.t0 > now || e.t0 + e.d < tMin) continue;
    const a = X(Math.max(e.t0, tMin)), b = X(Math.min(e.t0 + e.d, now));
    put(MK.job, (a + b) / 2, 0.35, LANE.lz[e.eng], Math.max(b - a, 0.25), 0.7, 0.95, e.op === 'D' ? COL.lz : COL.lzD);
    if (e.t0 + e.d > now) out.jobNow.push(e);
  }
  // user SW: a bar while it runs, a gap with a low red mark while it waits for a page
  for (let p = 0; p < s.nprog; p++) {
    const z = LANE.user[p], col = p ? COL.ub : COL.ua;
    const ws = ev.wait.filter(w => w.prog === p && w.t1 > tMin && w.t0 <= now);
    let cur = tMin;
    const seg = (a, b) => { if (b - a <= 0) return; put(MK.user, X((a + b) / 2), 0.25, z, (b - a) * k, 0.5, 1.7, col); };
    for (const w of ws) {
      seg(cur, Math.min(w.t0, now)); cur = Math.max(cur, w.t1);
      const a = X(Math.max(w.t0, tMin)), b = X(Math.min(w.t1, now));
      put(MK.wait, (a + b) / 2, 0.08, z, Math.max(b - a, 0.2), 0.16, 2.0);
      if (w.t1 > now) out.waitNow.push(w);
    }
    if (cur < now) seg(cur, now);
  }
  // each access as a dot, only while the lens is close enough to tell them apart
  if (lens < 3) for (let i = ev.acc.length - 1; i >= 0; i--) {
    const e = ev.acc[i]; if (e.t > now) continue; if (e.t < tMin) break;
    put(MK.dot, X(e.t), 0.78, LANE.user[e.prog], 1, 1, 1, e.prog ? COL.ub : COL.ua);
  }
  finish();
  // the LZ4 HW's four lights: lit while that engine has a job
  CH.lz.userData.lights.forEach((l, i) => l.material.color.copy(out.jobNow.some(j => j.eng === i) ? COL.lit : COL.paper));
  return out;
}

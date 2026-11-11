/* ---------- DRAM on the floor: hot frames at the back, LZ4 HW in the middle, cold chunks nearest ---------- */
const floor = plate(2 * FLX, FLZ1 - FLZ0, FPX);
floor.mesh.rotation.x = -Math.PI / 2; floor.mesh.position.set(0, 0, (FLZ0 + FLZ1) / 2); scene.add(floor.mesh);
const fx = x => (x + FLX) * FPX, fz = z => (z - FLZ0) * FPX;
const SLABW = U - 0.5, SLABZ = SLABD - 0.4, CKW = CWU - 0.2;

let MAT = {};
function buildMaterials() {
  Object.values(MAT).forEach(m => { if (m.map) m.map.dispose(); m.dispose(); });
  MAT = {};
  const L = o => new THREE.MeshLambertMaterial(o);
  ['ro', 'rw'].forEach(k => {
    MAT[k] = L({ color: new THREE.Color(P[k + '_bg']) }); MAT[k + '_edge'] = L({ color: new THREE.Color(P[k]) });
    const t = hatchTexture(P[k + '_bg'], P[k]); t.repeat.set(0.5, 3); MAT[k + '_hz'] = L({ map: t });
    MAT[k + '_bit'] = L({ map: hatchTexture(P[k + '_bg'], P[k]) });
  });
  const t = hatchTexture(P.soft, P.muted); t.repeat.set(0.5, 3);
  MAT.other_hz = L({ map: t }); MAT.other = L({ color: new THREE.Color(P.soft) }); MAT.hw = L({ color: new THREE.Color(P.warn) });
}

/* frames: a slab with a drawn top */
const FRAMES = [];
for (let f = 0; f < NF; f++) {
  const grp = new THREE.Group(), slab = new THREE.Mesh(new THREE.BoxGeometry(SLABW, 0.7, SLABZ)), top = plate(SLABW, SLABZ, 40);
  slab.position.y = 0.35; top.mesh.rotation.x = -Math.PI / 2; top.mesh.position.y = 0.715;
  grp.add(slab, top.mesh); grp.position.set(frameX0(f) + U / 2, 0, HOTZ + SLABD / 2); scene.add(grp);
  FRAMES.push({ grp, slab, top, key: '' });
}
function drawFrameTop(F, st, f, step) {
  const o = st.frames[f], g = F.top.g, W = F.top.cv.width, H = F.top.cv.height;
  if (o === 'o') { g.fillStyle = P.soft; g.fillRect(0, 0, W, H); txt(g, 'other pages', W / 2, H / 2 + 12, '400 40px ' + MONO, P.muted, 'center'); F.top.tex.needsUpdate = true; return; }
  const k = D.pages[o].kind, held = st.pages[o].frame === null && st.fill !== f;
  g.fillStyle = P.paper; g.fillRect(0, 0, W, H);
  txt(g, 'page ' + pgNo(o), 12, 48, '600 ' + (held ? 42 : 50) + 'px ' + MONO, P[k]);
  if (held) txt(g, 'V=0', W - 12, 46, '600 42px ' + MONO, P.warn, 'right');
  ONPAGE[o].forEach(sl => {
    const x = sl.a / PAGE * W, w = (sl.b - sl.a) / PAGE * W, on = sl.sym === step.sym;
    box(g, x + 2, 62, w - 4, H - 66, on ? P[k] : P[k + '_bg'], P[k], 3);
    const col = on ? P.paper : P.ink, px = [46, 38].find(s => sl.sym.length * s * 0.62 < w - 14);
    if (px) txt(g, sl.sym, x + w / 2, 62 + (H - 66) / 2 + px * 0.35, '600 ' + px + 'px ' + MONO, col, 'center');
    else if (w > 44) { g.save(); g.translate(x + w / 2 + 13, 62 + (H - 66) / 2); g.rotate(-Math.PI / 2); txt(g, sl.sym, 0, 0, '600 38px ' + MONO, col, 'center'); g.restore(); }
  });
  box(g, 2, 2, W - 4, H - 4, null, P[k], 4);
  F.top.tex.needsUpdate = true;
}

/* chunks: one thin slab each, hatched because what they hold is compressed */
const CHUNKS = [];
for (let c = 0; c < NCK; c++) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(CKW, 0.5, SLABZ)); m.position.x = chunkX0(c) + CWU / 2; scene.add(m); CHUNKS.push(m);
}
function setChunk(c, kind, frac, lifted) {
  const m = CHUNKS[c]; m.visible = !!kind; if (!kind) return;
  m.material = MAT[kind + '_hz']; m.scale.set(1, lifted ? 2.2 : 1, frac);
  m.position.y = 0.25 * (lifted ? 2.2 : 1) + (lifted ? 0.3 : 0); m.position.z = COLDZ + 0.2 + SLABZ * frac / 2;
}
const lastFrac = (size, n) => (size - (n - 1) * CHUNK) / CHUNK;

/* LZ4 HW: a low block with a status plate on top */
const hwBox = new THREE.Mesh(new THREE.BoxGeometry(2 * HWX, HWH, HWZ1 - HWZ0)); hwBox.position.set(0, HWH / 2, (HWZ0 + HWZ1) / 2); scene.add(hwBox);
const hwTop = plate(2 * HWX, HWZ1 - HWZ0, 40); hwTop.mesh.rotation.x = -Math.PI / 2; hwTop.mesh.position.set(0, HWH + 0.02, (HWZ0 + HWZ1) / 2); scene.add(hwTop.mesh);
function drawHW(step) {
  const g = hwTop.g, W = hwTop.cv.width, H = hwTop.cv.height, fl = step.flow;
  g.fillStyle = P.paper; g.fillRect(0, 0, W, H); box(g, 4, 4, W - 8, H - 8, null, P.warn, 8);
  txt(g, 'LZ4 HW', 28, 100, '800 66px ' + DISP, P.warn);
  txt(g, fl ? 'working' : 'idle', 30, 166, '400 44px ' + MONO, P.muted);
  txt(g, step.lane || 'holds no data', 310, 60, '600 46px ' + MONO, P.ink);
  if (!fl) return hwTop.tex.needsUpdate = true;
  const k = fl.k, PGW = 400, y = 80, h = 92;
  const pageBar = (x, faded) => { g.globalAlpha = faded ? 0.45 : 1; box(g, x, y, PGW, h, P[k + '_bg'], P[k], 4); txt(g, '4096 B', x + PGW / 2, y + 62, '600 46px ' + MONO, P.ink, 'center'); g.globalAlpha = 1; };
  const streamBar = (x, faded, cut) => {
    const w = fl.size / PAGE * PGW; g.globalAlpha = faded ? 0.45 : 1;
    g.fillStyle = g.createPattern(MAT[k + '_bit'].map.image, 'repeat'); g.fillRect(x, y, w, h); box(g, x, y, w, h, null, P[k], 4);
    if (cut) for (let i = 1; i * CHUNK < fl.size; i++) { g.fillStyle = P.ink; g.fillRect(x + i * CHUNK / PAGE * PGW - 2, y - 8, 4, h + 16); }
    g.globalAlpha = 1;
    txt(g, fl.size + ' B', x + w + 14, y + 62, '600 46px ' + MONO, P.ink);
  };
  const arrow = x => txt(g, '▶', x, y + 64, '700 50px ' + MONO, P.warn, 'center');
  const sw = fl.size / PAGE * PGW;
  if (fl.t === 'rd' || fl.t === 'wr') pageBar(310);
  else if (fl.t === 'comp') { pageBar(310, true); arrow(750); streamBar(790, false, false); }
  else if (fl.t === 'decomp') { streamBar(310, true, false); arrow(310 + sw + 205); pageBar(310 + sw + 245); }
  else streamBar(310, false, true);
  hwTop.tex.needsUpdate = true;
}

function drawFloor(step) {
  const g = floor.g, st = step.st, hl = step.hl || {};
  g.fillStyle = P.paper; g.fillRect(0, 0, floor.cv.width, floor.cv.height);
  const head = (x, z, a, b) => { txt(g, a, fx(x), fz(z), '700 38px ' + DISP, P.ink); const w = g.measureText(a).width; txt(g, b, fx(x) + w + 22, fz(z), '400 32px ' + MONO, P.muted); };
  head(frameX0(0), HOTZ - 1.3, 'HOT REGION', 'page frames · 4096 B each · not compressed');
  txt(g, st.frames.filter(o => o === null).length + ' of ' + NF + ' frames free', fx(frameX0(NF)), fz(HOTZ - 1.3), '600 32px ' + MONO, P.ink, 'right');
  for (let f = 0; f < NF; f++) {
    const tgt = (hl.frames || []).includes(f);
    box(g, fx(frameX0(f)) + 4, fz(HOTZ) + 4, U * FPX - 8, SLABD * FPX - 8, null, tgt ? P.ink : P.line, tgt ? 7 : 3, tgt ? null : [12, 9]);
    if (st.frames[f] === null) txt(g, 'free', fx(frameX0(f) + U / 2), fz(HOTZ + SLABD / 2) + 12, '400 34px ' + MONO, P.muted, 'center');
    txt(g, 'frame ' + frNo(f), fx(frameX0(f) + U / 2), fz(HOTZ + SLABD) + 42, (tgt ? '700' : '400') + ' 28px ' + MONO, tgt ? P.ink : P.muted, 'center');
  }
  head(chunkX0(0), COLDZ - 1.1, 'COLD REGION', 'chunk pool · 512 B each · compressed, so hatched');
  for (let c = 0; c < NCK; c++) box(g, fx(chunkX0(c)) + 1, fz(COLDZ) + 2, CWU * FPX - 2, SLABD * FPX - 4, null, P.line, 2);
  const freeRW = st.chunks.slice(NRO).filter(o => o === null).length;
  txt(g, ckNo(0) + ' RO, fixed at build', fx(chunkX0(0)), fz(COLDZ + SLABD) + 42, '400 30px ' + MONO, P.muted);
  txt(g, ckNo(NRO) + ' RW, ' + freeRW + ' of ' + NRW + ' chunks free', fx(chunkX0(NRO)), fz(COLDZ + SLABD) + 42, '400 30px ' + MONO, P.muted);
  floor.tex.needsUpdate = true;
}

// Put every slab in the state of this step. Returns what is still arriving, so the flow code can grow it in.
function updateDram(step) {
  const st = step.st, hl = step.hl || {}, selPages = new Set(SYM[step.sym].slices.map(s => s.p));
  FRAMES.forEach((F, f) => {
    const o = st.frames[f]; F.grp.visible = o !== null; F.grp.scale.x = 1; F.grp.position.x = frameX0(f) + U / 2;
    if (o === null) return;
    F.slab.material = o === 'o' ? MAT.other : MAT[D.pages[o].kind + '_edge'];
    drawFrameTop(F, st, f, step);
  });
  const lift = new Set(hl.chunks || []);
  for (let c = 0; c < NCK; c++) setChunk(c, null);
  st.chunks.forEach((o, c) => { if (o === 'o') setChunk(c, 'other', 1, false); });
  st.pages.forEach((ps, q) => { if (ps.chunks) ps.chunks.forEach((c, i) => setChunk(c, D.pages[q].kind, i === ps.chunks.length - 1 ? lastFrac(ps.csize, ps.chunks.length) : 1, lift.has(c))); });
  const fl = step.flow, arriving = { frame: null, chunks: [] };
  if (fl && fl.t === 'store') { fl.cs.forEach((c, i) => setChunk(c, fl.k, i === fl.cs.length - 1 ? lastFrac(fl.size, fl.cs.length) : 1, false)); arriving.chunks = fl.cs.slice(); }
  if (fl && fl.t === 'wr') arriving.frame = fl.f;
  return arriving;
}

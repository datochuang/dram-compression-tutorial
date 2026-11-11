/* ---------- what changes with every step: mapping lines, the access path, flowing data ---------- */
const dyn = new THREE.Group(); scene.add(dyn);
const bitGeo = new THREE.BoxGeometry(1, 1, 1), dotGeo = new THREE.SphereGeometry(0.45, 14, 10);
let FLOWS = [], PULSES = [], ARRIVE = { frame: null, chunks: [] }, stepT0 = 0;
const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
const runsOf = cs => { const a = cs.slice().sort((x, y) => x - y), out = []; a.forEach(c => { const r = out[out.length - 1]; if (r && r[1] === c - 1 && c !== NRO) r[1] = c; else out.push([c, c]); }); return out; };
const framePt = (f, frac, z) => V3(frameX0(f) + 0.25 + frac * SLABW, 0.9, HOTZ + z);
const chunkPt = c => V3(chunkX0(c) + CWU / 2, 0.8, COLDZ + 1.6);
const gut = (p, v, lift = 0.1) => B2W(pageU(p) + 0.15, v, lift);        // the gap left of page p's tiles on the board
const port = (side, x) => V3(x, HWH + 0.5, side === 'back' ? HWZ0 - 0.4 : HWZ1 - 0.8);
const belt = px => V3(px / 40 - HWX, HWH + 0.5, HWZ1 - 0.8);          // the empty strip along the front of the LZ4 HW plate, given in plate pixels

// A train of pieces that keeps running along a curve. `look(t)` says how a piece looks at position t.
function addFlow(curve, n, look, phase = 0, speed = 0.3) {
  const bits = [];
  for (let i = 0; i < n; i++) { const m = new THREE.Mesh(look(0).dot ? dotGeo : bitGeo, look(0).mat); dyn.add(m); bits.push(m); }
  FLOWS.push({ curve, bits, look, phase, speed });
}
const plainBit = k => () => ({ mat: MAT[k + '_edge'], s: [1.5, 0.6, 1.0] });
const packedBit = k => () => ({ mat: MAT[k + '_bit'], s: [0.85, 0.6, 1.0] });
let dotMat = null;

// A rectangle drawn around one tile of the board. It pulses once when the step starts.
function tileRing(p, row, color, r, pulse) {
  const grp = new THREE.Group(), w = U - 0.6, h = ROW[row + '1'] - ROW[row + '0'];
  grp.position.copy(B2W(pageU(p) + U / 2, (ROW[row + '0'] + ROW[row + '1']) / 2, 0.12)); grp.rotation.x = -(Math.PI / 2 - TILT);
  const c = [V3(-w / 2, -h / 2, 0), V3(w / 2, -h / 2, 0), V3(w / 2, h / 2, 0), V3(-w / 2, h / 2, 0)];
  c.forEach((a, i) => grp.add(tube(seg3(a, c[(i + 1) % 4]), r, color, 1, 1)));
  grp.userData.group = true; dyn.add(grp); if (pulse) PULSES.push(grp);
}
function clearDyn() {
  dyn.children.slice().forEach(o => { if (o.userData.group) { clearGroup(o); dyn.remove(o); } });
  dyn.children.slice().forEach(o => { dyn.remove(o); if (o.geometry !== bitGeo && o.geometry !== dotGeo) { if (o.userData.ownMap) o.material.map.dispose(); else o.geometry.dispose(); o.material.dispose(); } });
  FLOWS = []; PULSES = [];
}

function buildDynamic(step) {
  clearDyn();
  const st = step.st, selPages = new Set(SYM[step.sym].slices.map(s => s.p)), pin = step.pin, fl = step.flow;
  if (!dotMat) dotMat = new THREE.MeshBasicMaterial(); dotMat.color.set(P.ink);

  // where every page is right now: PTE to its frame, COT entry to its chunks
  const focus = new Set([...((step.hl || {}).chunks || []), ...((fl && fl.cs) || [])]);
  D.pages.forEach((pg, p) => {
    const t = tabOf(st, p), on = selPages.has(p), col = P[pg.kind];
    if (st.pages[p].frame !== null) { const r = on ? 0.1 : 0.05, op = on ? 1 : 0.55;
      dyn.add(tube(seg3(gut(p, ROW.pte1), gut(p, BH)), r, col, op, 1)); dyn.add(tube(arc(gut(p, BH), framePt(st.pages[p].frame, 0.5, 0.3), 0.6), r, col, op)); }
    if (t.cot) runsOf(t.cot.cs).forEach(r => {
      const end = V3((chunkX0(r[0]) + chunkX0(r[1]) + CWU) / 2, 0.75, COLDZ + 0.4);
      const hot = t.cot.cs.some(c => focus.has(c));      // bold only while this step is about these chunks
      dyn.add(tube(arc(B2W(pageU(p) + U / 2, ROW.cot1, 0.1), end, 7), hot ? 0.085 : on ? 0.045 : 0.03, col, hot ? 0.9 : on ? 0.5 : 0.24));
    });
  });
  boardChanged.forEach(c => tileRing(c.p, c.row, P.ink, 0.13, true));

  // the access: from the symbol to the PTE, and on to the frame once the CPU MMU has a valid PTE
  if (pin) {
    const p = pin.p, col = pin.fault ? P.warn : P.ink, f = st.pages[p].frame;
    const a = B2W(pageU(p) + pin.po / PAGE * U, ROW.sym1, 0.2), b = gut(p, ROW.pte0, 0.2), b2 = gut(p, BH, 0.2);
    const path = new THREE.CurvePath(); path.add(seg3(a, b));
    dyn.add(tube(seg3(a, b), 0.14, col, 1, 1));
    if (pin.fault) tileRing(p, 'pte', P.warn, 0.16, step.who === 'mmu');
    const through = f !== null && !pin.fault && (pin.phys || step.who === 'mmu');
    if (through) {
      const end = framePt(f, pin.po / PAGE, SLABD / 2), leg = arc(b2, end, 1.5);
      dyn.add(tube(seg3(b, b2), 0.14, col, 1, 1)); dyn.add(tube(leg, 0.14, col));
      const stem = tube(seg3(end, V3(end.x, 0.72, end.z)), 0.2, col, 1, 1); dyn.add(stem);
      path.add(seg3(b, b2)); path.add(leg);
    }
    if (!pin.fault) {
      const back = pin.phys && pin.kind === 'read';          // read data comes back from the frame; an address or written data goes forward
      const curve = back ? { getPointAt: t => path.getPointAt(1 - t) } : path;
      addFlow({ getPoint: t => curve.getPointAt(t) }, through ? 6 : 3, () => ({ mat: dotMat, s: [1, 1, 1], dot: true }), 0, through ? 0.28 : 0.5);
    }
  }

  // data on the move: DMA by LZ4 HW, and the change of size inside it
  if (fl) {
    const k = fl.k, n = fl.cs ? fl.cs.length : 0, px = i => (i - (n - 1) / 2) * 1.6;
    const morph = (firstPacked, at) => t => (t < at) === firstPacked ? packedBit(k)() : plainBit(k)();
    const sw = (fl.size || 0) / PAGE * 400, B0 = 310, B1 = 1200;          // same pixels as the bars drawn on the plate
    if (fl.t === 'rd') addFlow(arc(framePt(fl.f, 0.5, SLABD - 0.6), port('back', 0), 3), 8, plainBit(k));
    if (fl.t === 'wr') addFlow(arc(port('back', 0), framePt(fl.f, 0.5, SLABD - 0.6), 3), 8, plainBit(k));
    if (fl.t === 'comp') addFlow(seg3(belt(B0), belt(B1)), 9, morph(false, (750 - B0) / (B1 - B0)), 0, 0.2);
    if (fl.t === 'decomp') addFlow(seg3(belt(B0), belt(B1)), 9, morph(true, (sw + 205) / (B1 - B0)), 0, 0.2);
    if (fl.t === 'store' || fl.t === 'gather') fl.cs.forEach((c, i) => {
      const a = port('front', px(i)), b = chunkPt(c);
      addFlow(fl.t === 'store' ? arc(a, b, 2.6) : arc(b, a, 2.6), 3, packedBit(k), i * 0.11);
      const tag = sprite(String(i + 1), P.paper, P.ink, 1.15); tag.position.set(b.x, 2.5, COLDZ + SLABD - 1.4); tag.userData.ownMap = true; dyn.add(tag);
    });
  }
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
  if (ARRIVE.frame !== null) { const F = FRAMES[ARRIVE.frame], s = Math.max(0.02, k); F.grp.scale.x = s; F.grp.position.x = frameX0(ARRIVE.frame) + 0.25 + SLABW * s / 2; }
  ARRIVE.chunks.forEach((c, i) => { CHUNKS[c].visible = el / 1.8 > (i + 0.6) / ARRIVE.chunks.length; });
  PULSES.forEach(g => { const s = 1 + 0.45 * Math.max(0, 1 - el / 0.7); g.scale.set(s, s, 1); });
  renderer.render(scene, camera);
}

/* tap on a symbol of the board */
const ray = new THREE.Raycaster();
function boardHit(e) {
  const r = canvas.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1), camera);
  const hit = ray.intersectObject(board.mesh)[0];
  return hit ? symbolAt(hit.uv.x * BW, (1 - hit.uv.y) * BH) : null;
}

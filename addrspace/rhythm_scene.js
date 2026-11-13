/* ---------- two rhythms: the stage ----------
   Time runs along x. "Now" sits at x = 0 and the camera rides with it; what happened earlier lies to the
   left and slides away. Tracks lie flat on the floor, far to near: user SW, kernel SW on the CPU MMU side,
   kernel SW on the compression layer side, LZ4 HW. The served party is at the far end, nothing tall in front. */
const XB = 104, XF = 30;                                   // world x of the oldest thing shown, and of the right edge
const LANE = { user: [-16.4, -13.6], cpu: [-7.2, -4.4], comp: [1.6, 3.0, 4.4, 5.8], lz: [10.6, 11.8, 13.0, 14.2] };
const TRACK = [
  { key: 'user', z0: -18, z1: -12, name: 'user SW', sub: 'A on Core 0 · B on Core 1' },
  { key: 'cpu', z0: -8.6, z1: -3, name: 'kernel SW: CPU MMU side', sub: 'TLB misses · Core 0 · Core 1' },
  { key: 'comp', z0: 0.4, z1: 7, name: 'kernel SW: compression layer side', sub: 'page faults · reclaim' },
  { key: 'lz', z0: 9.6, z1: 15.2, name: 'LZ4 HW', sub: '4 engines (P4, N = 4 for now)' },
];
['kern', 'kern-tint', 'lz', 'lz-tint', 'ua', 'ub'].forEach(k => { P[k.replace('-', '_')] = getComputedStyle(document.documentElement).getPropertyValue('--' + k).trim(); });

// what the camera has to fit: the whole stretch of tracks
FIT.length = 0;
[-XB, XF].forEach(x => [-19, 16].forEach(z => [0, 3].forEach(y => FIT.push(new THREE.Vector3(x, y, z)))));
HOME.t.set(-30, 0, -1); HOME.ph = 0.62;

const C = c => new THREE.Color(c);
const lam = c => new THREE.MeshLambertMaterial({ color: C(c) });
const floorM = new THREE.Mesh(new THREE.PlaneGeometry(XB + XF + 40, 44), new THREE.MeshBasicMaterial({ color: C(P.bg) }));
floorM.rotation.x = -Math.PI / 2; floorM.position.set((XF - XB) / 2, -0.02, -1.5); scene.add(floorM);
const STATIC = new THREE.Group(); scene.add(STATIC);
function buildStatic() {
  clearGroup(STATIC); floorM.material.color = C(P.bg);
  for (const T of TRACK) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(XB + XF, T.z1 - T.z0), new THREE.MeshBasicMaterial({ color: C(P.paper) }));
    m.rotation.x = -Math.PI / 2; m.position.set((XF - XB) / 2, 0, (T.z0 + T.z1) / 2); STATIC.add(m);
    for (const z of LANE[T.key]) {                       // one thin line per lane
      const l = new THREE.Mesh(new THREE.BoxGeometry(XB + XF, 0.02, 0.06), new THREE.MeshBasicMaterial({ color: C(P.line) }));
      l.position.set((XF - XB) / 2, 0.01, z); STATIC.add(l);
    }
  }
  // the future has not happened yet: a pale cover to the right of now
  const fut = new THREE.Mesh(new THREE.PlaneGeometry(XF, 36), new THREE.MeshBasicMaterial({ color: C(P.soft), transparent: true, opacity: 0.55 }));
  fut.rotation.x = -Math.PI / 2; fut.position.set(XF / 2, 0.03, -1.5); STATIC.add(fut);
  const now = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.06, 36), new THREE.MeshBasicMaterial({ color: C(P.ink) }));
  now.position.set(0, 0.04, -1.5); STATIC.add(now);
}

/* instanced marks, one mesh per kind */
const BOX = new THREE.BoxGeometry(1, 1, 1);
function inst(geo, n, color, opacity) {
  const mat = new THREE.MeshLambertMaterial({ color: 0xffffff, transparent: opacity < 1, opacity: opacity || 1 });
  const m = new THREE.InstancedMesh(geo, mat, n); m.frustumCulled = false;
  const c = C(color); for (let i = 0; i < n; i++) m.setColorAt(i, c);   // before count drops to 0: the colour buffer is sized from count
  m.count = 0;
  m.userData.base = color; scene.add(m); return m;
}
const MK = {};
function buildMarks() {
  Object.values(MK).forEach(m => { scene.remove(m); m.material.dispose(); m.dispose && m.dispose(); });
  MK.tick = inst(BOX, 9000, P.kern); MK.band = inst(BOX, 1400, P.kern, 0.9);
  MK.block = inst(BOX, 700, P.kern); MK.job = inst(BOX, 700, P.lz);
  MK.user = inst(BOX, 1500, P.ua); MK.wait = inst(BOX, 700, P.warn);
  MK.dot = inst(new THREE.SphereGeometry(0.24, 10, 8), 2400, P.ua);
  MK.diam = inst(new THREE.OctahedronGeometry(0.55), 500, P.kern); MK.link = inst(BOX, 900, P.kern, 0.75);
}
const M4 = new THREE.Matrix4(), Q = new THREE.Quaternion(), V = new THREE.Vector3(), S3 = new THREE.Vector3();
function put(m, x, y, z, sx, sy, sz, color) {
  const i = m.count; if (i >= m.instanceMatrix.count) return;
  M4.compose(V.set(x, y, z), Q, S3.set(sx, sy, sz)); m.setMatrixAt(i, M4);
  if (color) m.setColorAt(i, color);
  m.count = i + 1;
}
function begin() { Object.values(MK).forEach(m => { m.count = 0; }); }
function finish() { Object.values(MK).forEach(m => { m.instanceMatrix.needsUpdate = true; if (m.instanceColor) m.instanceColor.needsUpdate = true; }); }

/* characters: each user SW program its own shape and colour; kernel SW purple; LZ4 HW squat and amber */
const CH = {};
function figure(body, head, color, scale) {
  const g = new THREE.Group(), m = lam(color);
  const b = new THREE.Mesh(body, m), h = new THREE.Mesh(head, m);
  b.position.y = 1.0; h.position.y = 2.35; g.add(b, h); g.scale.setScalar(scale || 1); scene.add(g); return g;
}
function buildChars() {
  Object.values(CH).forEach(g => scene.remove(g));
  CH.ua = figure(new THREE.CylinderGeometry(0.7, 0.8, 2, 14), new THREE.BoxGeometry(1.2, 1.2, 1.2), P.ua, 1.15);
  CH.ub = figure(new THREE.ConeGeometry(0.95, 2.1, 14), new THREE.SphereGeometry(0.62, 16, 12), P.ub, 1.15);
  CH.k0 = figure(new THREE.CylinderGeometry(0.5, 0.62, 1.7, 12), new THREE.SphereGeometry(0.5, 14, 10), P.kern, 0.9);
  CH.k1 = figure(new THREE.CylinderGeometry(0.5, 0.62, 1.7, 12), new THREE.SphereGeometry(0.5, 14, 10), P.kern, 0.9);
  CH.kc = figure(new THREE.CylinderGeometry(0.6, 0.75, 1.9, 12), new THREE.SphereGeometry(0.58, 14, 10), P.kern, 1);
  const r = new THREE.Group(), body = new THREE.Mesh(new THREE.BoxGeometry(2.6, 1.1, 2.2), lam(P.lz));
  body.position.y = 0.55; r.add(body); r.userData.lights = [];
  for (let e = 0; e < 4; e++) {
    const l = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.3, 0.42), lam(P.paper));
    l.position.set(-0.9 + e * 0.6, 1.25, 0); r.add(l); r.userData.lights.push(l);
  }
  scene.add(r); CH.lz = r;
  CH.ua.position.set(2.6, 0, LANE.user[0]); CH.ub.position.set(2.6, 0, LANE.user[1]);
  CH.k0.position.set(2.4, 0, LANE.cpu[0]); CH.k1.position.set(2.4, 0, LANE.cpu[1]);
  CH.kc.position.set(2.6, 0, 3.7); CH.lz.position.set(2.8, 0, 12.4);
}
function buildAll() { readPalette(); ['kern', 'kern-tint', 'lz', 'lz-tint', 'ua', 'ub'].forEach(k => { P[k.replace('-', '_')] = getComputedStyle(document.documentElement).getPropertyValue('--' + k).trim(); }); buildStatic(); buildMarks(); buildChars(); scene.background = C(P.bg); }

/* overlays: track names over the stage; speech bubbles in their own column beside it, joined to the speaker by a thin line,
   so no bubble covers a track. On a narrow screen the bubbles sit in a grid under the stage, without lines. */
const OV = $('ov'), VO = $('voices'), LEADS = $('leads'), BUB = {}, TRK = [];
const NARROW = window.matchMedia ? window.matchMedia('(max-width: 900px)') : { matches: false };
function bubble(key, cls) { const d = document.createElement('div'); d.className = 'bub ' + cls; d.style.display = 'none'; VO.appendChild(d); BUB[key] = d; }
[['ua', 'user-a'], ['ub', 'user-b'], ['k0', 'kern'], ['k1', 'kern'], ['kc', 'kern'], ['lz', 'lz']].forEach(([k, c]) => bubble(k, c));
TRACK.forEach(T => { const d = document.createElement('div'); d.className = 'trk'; d.innerHTML = T.name + '<small>' + T.sub + '</small>'; OV.appendChild(d); TRK.push(d); });
const nowTag = document.createElement('div'); nowTag.className = 'trk'; nowTag.textContent = 'now'; OV.appendChild(nowTag);
const LCOL = { ua: '--ua', ub: '--ub', k0: '--kern', k1: '--kern', kc: '--kern', lz: '--lz' };
function screenOf(x, y, z) {
  V.set(x, y, z).project(camera);
  return { x: (V.x + 1) / 2 * canvas.clientWidth, y: (1 - V.y) / 2 * canvas.clientHeight, ok: V.z < 1 };
}
function placeOverlays(say) {
  const shown = [], narrow = NARROW.matches;
  for (const k of Object.keys(BUB)) {
    const d = BUB[k], t = say[k];
    if (!t) { d.style.display = 'none'; continue; }
    const g = CH[k], p = screenOf(g.position.x, g.position.y + 2.2 * g.scale.y, g.position.z);
    d.style.display = 'block';
    if (d._t !== t.html) { d.innerHTML = t.html; d._t = t.html; }
    d.classList.toggle('hot', !!t.hot);
    shown.push({ d, k, x: p.x, y: p.y, ok: p.ok, h: d.offsetHeight });
  }
  let lines = '';
  if (!narrow) {
    // each bubble centred on its speaker's height, then pushed apart: down from the top, up from the bottom
    const H = VO.clientHeight, cw = canvas.clientWidth;
    shown.sort((a, b) => a.y - b.y);
    let floorY = 6; for (const s of shown) { s.top = Math.max(s.y - s.h / 2, floorY); floorY = s.top + s.h + 6; }
    let ceil = H - 6; for (let i = shown.length - 1; i >= 0; i--) { const s = shown[i]; s.top = Math.min(s.top, ceil - s.h); ceil = s.top - 6; }
    for (const s of shown) {
      s.d.style.top = s.top + 'px';
      if (s.ok) lines += `<path d="M${s.x + 12} ${s.y} C${cw - 20} ${s.y}, ${cw - 30} ${s.top + 16}, ${cw + 8} ${s.top + 16}" stroke="var(${LCOL[s.k]})" />`;
    }
  } else for (const s of shown) s.d.style.top = '';
  if (LEADS._l !== lines) { LEADS.innerHTML = lines; LEADS._l = lines; }
  TRACK.forEach((T, i) => {
    const p = screenOf(-XB + 1, 0, (T.z0 + T.z1) / 2), q = screenOf(-XB + 1, 0, T.z1);
    TRK[i].style.left = Math.max(6, p.x) + 'px'; TRK[i].style.top = (p.y + q.y) / 2 + 'px';
  });
  const n = screenOf(0, 0, 16.4); nowTag.style.left = (n.x - 16) + 'px'; nowTag.style.top = (n.y + 10) + 'px';
}

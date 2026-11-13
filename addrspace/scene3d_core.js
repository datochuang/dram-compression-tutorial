/* ---------- 3D stage: palette, renderer, camera, small builders ---------- */
const $ = id => document.getElementById(id);
const REDUCE = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const MONO = '"IBM Plex Mono", ui-monospace, Menlo, monospace', DISP = 'Archivo, "Noto Sans TC", system-ui, sans-serif';

// World units: one page frame is U wide. Board = the tilted plate at the back, floor = DRAM.
// This file is shared by every 3D page. What a page puts on the board and the floor is in its own files.
const U = 10;
const BW = 92, BH = 27.3, BPX = 24, TILT = 52 * Math.PI / 180, BZ = -4.6, BY = 0.3;      // board size, px per unit, tilt from the floor, bottom edge
const FLX = 38, FLZ0 = -3.6, FLZ1 = 31.4, FPX = 24;                                    // floor plate: x in [-38, 38], z in [-3.6, 31.4]

// A point of the board, given in board units (u from the left, v from the top), lifted off its surface.
function B2W(u, v, lift = 0) {
  const d = BH - v;
  return new THREE.Vector3(u - BW / 2, BY + d * Math.sin(TILT) + lift * Math.cos(TILT), BZ - d * Math.cos(TILT) + lift * Math.sin(TILT));
}

const P = {};
function readPalette() {
  const cs = getComputedStyle(document.documentElement);
  ['bg', 'paper', 'ink', 'muted', 'line', 'soft', 'accent', 'accent-tint', 'warn', 'warn-tint', 'rw', 'rw-bg', 'ro', 'ro-bg', 'hatch', 'flash']
    .forEach(k => P[k.replace('-', '_')] = cs.getPropertyValue('--' + k).trim());
}
readPalette();

const canvas = $('gl');
let renderer = null;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true }); renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); }
catch (e) { $('nogl').style.display = 'flex'; }
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(26, 1.75, 1, 1600);
const hemi = new THREE.HemisphereLight(0xffffff, 0x8894a4, 0.95), sun = new THREE.DirectionalLight(0xffffff, 0.35);
sun.position.set(-30, 80, 60); scene.add(hemi, sun);

/* orbit camera: th turns around the vertical axis, ph is the height angle */
const HOME = { t: new THREE.Vector3(0, 5.2, 5.5), th: 0, ph: 0.72, r: 112 };
const cam = { t: HOME.t.clone(), r: 90, th: HOME.th, ph: HOME.ph };
function placeCamera() {
  const c = Math.cos(cam.ph);
  camera.position.set(cam.t.x + cam.r * Math.sin(cam.th) * c, cam.t.y + cam.r * Math.sin(cam.ph), cam.t.z + cam.r * Math.cos(cam.th) * c);
  camera.lookAt(cam.t);
}
function resetView() { cam.t.copy(HOME.t); cam.th = HOME.th; cam.ph = HOME.ph; cam.r = HOME.r; placeCamera(); }
// Find the distance and the target height at which the board and the floor just fill the canvas, whatever its shape.
const FIT = [[0, 0], [BW, 0], [0, BH], [BW, BH]].map(([u, v]) => B2W(u, v)).concat([[-FLX, FLZ0], [FLX, FLZ0], [-FLX, FLZ1], [FLX, FLZ1]].map(([x, z]) => new THREE.Vector3(x, 0, z)));
function fitHome() {
  const keep = { t: cam.t.clone(), r: cam.r, th: cam.th, ph: cam.ph }, k = Math.tan(camera.fov * Math.PI / 360) / Math.cos(HOME.ph), v = new THREE.Vector3();
  cam.t.copy(HOME.t); cam.th = HOME.th; cam.ph = HOME.ph;
  const fits = r => {
    cam.r = r; let half = 0, wide = 0;
    for (let i = 0; i < 4; i++) {
      placeCamera(); camera.updateMatrixWorld();
      let lo = 9, hi = -9; wide = 0;
      FIT.forEach(p => { v.copy(p).project(camera); lo = Math.min(lo, v.y); hi = Math.max(hi, v.y); wide = Math.max(wide, Math.abs(v.x)); });
      cam.t.y += (lo + hi) / 2 * r * k; half = (hi - lo) / 2;
    }
    return half <= 0.955 && wide <= 0.975;
  };
  let a = 40, b = 420;
  for (let i = 0; i < 16; i++) { const m = (a + b) / 2; if (fits(m)) b = m; else a = m; }
  fits(b); HOME.t.copy(cam.t); HOME.r = b;
  cam.t.copy(keep.t); cam.r = keep.r; cam.th = keep.th; cam.ph = keep.ph;
}
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight; if (!w || !h) return;
  const atHome = !resize.done || (Math.abs(cam.r - HOME.r) < 0.01 && cam.t.distanceTo(HOME.t) < 0.01 && cam.th === HOME.th && cam.ph === HOME.ph);
  camera.aspect = w / h; camera.updateProjectionMatrix(); fitHome();
  if (renderer) renderer.setSize(w, h, false);
  resize.done = true; if (atHome) resetView(); else placeCamera();
}
if (window.ResizeObserver) new ResizeObserver(resize).observe($('view')); else addEventListener('resize', resize);

const ptrs = new Map(); let pinch = 0, moved = 0, onTap = null;
canvas.addEventListener('pointerdown', e => { try { canvas.setPointerCapture(e.pointerId); } catch (x) {} ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY }); moved = 0; pinch = 0; canvas.classList.add('drag'); });
canvas.addEventListener('pointermove', e => {
  const p = ptrs.get(e.pointerId); if (!p) return;
  const dx = e.clientX - p.x, dy = e.clientY - p.y; p.x = e.clientX; p.y = e.clientY; moved += Math.abs(dx) + Math.abs(dy);
  if (ptrs.size === 2) {
    const [a, b] = [...ptrs.values()], d = Math.hypot(a.x - b.x, a.y - b.y);
    if (pinch) cam.r = Math.min(420, Math.max(28, cam.r * pinch / d));
    pinch = d;
  } else if (e.shiftKey || e.buttons === 2) {
    const k = cam.r / 700, right = new THREE.Vector3(Math.cos(cam.th), 0, -Math.sin(cam.th));
    cam.t.addScaledVector(right, -dx * k); cam.t.y = Math.max(0, cam.t.y + dy * k);
  } else { cam.th -= dx * 0.006; cam.ph = Math.min(1.45, Math.max(0.1, cam.ph + dy * 0.006)); }
  placeCamera();
});
const drop = e => { const tap = ptrs.size === 1 && moved < 6; ptrs.delete(e.pointerId); pinch = 0; if (!ptrs.size) canvas.classList.remove('drag'); if (tap && e.type === 'pointerup' && onTap) onTap(e); };
canvas.addEventListener('pointerup', drop); canvas.addEventListener('pointercancel', drop);
canvas.addEventListener('contextmenu', e => e.preventDefault());
canvas.addEventListener('wheel', e => { if (!e.ctrlKey && !e.metaKey) return; e.preventDefault(); cam.r = Math.min(420, Math.max(28, cam.r * Math.exp(e.deltaY * 0.004))); placeCamera(); }, { passive: false });
$('reset').addEventListener('click', resetView);

/* builders */
function plate(w, h, px) {                       // a canvas you can draw on, shown as a flat rectangle
  const cv = document.createElement('canvas'); cv.width = Math.round(w * px); cv.height = Math.round(h * px);
  const tex = new THREE.CanvasTexture(cv); tex.anisotropy = 8;
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex }));
  return { cv, g: cv.getContext('2d'), tex, mesh, px, w, h };
}
function hatchTexture(fill, line) {
  const cv = document.createElement('canvas'); cv.width = cv.height = 64; const g = cv.getContext('2d');
  g.fillStyle = fill; g.fillRect(0, 0, 64, 64); g.strokeStyle = line; g.lineWidth = 5;
  for (let i = -64; i < 128; i += 16) { g.beginPath(); g.moveTo(i, 64); g.lineTo(i + 64, 0); g.stroke(); }
  const t = new THREE.CanvasTexture(cv); t.wrapS = t.wrapT = THREE.RepeatWrapping; return t;
}
function sprite(text, color, bg, size) {
  const cv = document.createElement('canvas'), g = cv.getContext('2d'), font = '700 44px ' + DISP;
  g.font = font; const w = Math.ceil(g.measureText(text).width) + 36; cv.width = w; cv.height = 64;
  g.fillStyle = bg; g.beginPath(); g.roundRect ? g.roundRect(0, 0, w, 64, 12) : g.rect(0, 0, w, 64); g.fill();
  g.font = font; g.fillStyle = color; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, w / 2, 34);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cv), depthTest: false, transparent: true }));
  s.scale.set(size * w / 64, size, 1); s.renderOrder = 10; return s;
}
function tube(curve, r, color, opacity = 1, seg = 28) {
  return new THREE.Mesh(new THREE.TubeGeometry(curve, seg, r, 6), new THREE.MeshBasicMaterial({ color: new THREE.Color(color), transparent: opacity < 1, opacity }));
}
const arc = (a, b, lift) => new THREE.QuadraticBezierCurve3(a, new THREE.Vector3((a.x + b.x) / 2, Math.max(a.y, b.y) + lift, (a.z + b.z) / 2), b);
const seg3 = (a, b) => new THREE.LineCurve3(a, b);
function clearGroup(grp) {
  while (grp.children.length) { const o = grp.children.pop(); if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map && o.userData.ownMap) o.material.map.dispose(); o.material.dispose(); } }
}

/* drawing on a plate: board units to pixels, fonts, text, boxes */
const bx = u => u * BPX;
const fnt = (w, u, fam) => w + ' ' + Math.round(u * BPX) + 'px ' + fam;
function txt(g, s, x, y, font, color, align = 'left') { g.font = font; g.fillStyle = color; g.textAlign = align; g.textBaseline = 'alphabetic'; g.fillText(s, x, y); }
function box(g, x, y, w, h, fill, stroke, lw = 2, dash = null) {
  if (fill) { g.fillStyle = fill; g.fillRect(x, y, w, h); }
  if (stroke) { g.strokeStyle = stroke; g.lineWidth = lw; g.setLineDash(dash || []); g.strokeRect(x, y, w, h); g.setLineDash([]); }
}

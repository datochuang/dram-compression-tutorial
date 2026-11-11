/* The look that the replay and the lessons share: colours, text sprites, the hatch that marks
   compressed data, and the characters. KERNEL SW, LZ4 HW and the user programs are built here
   once, so they are the same figures on every page. A builder returns the figure only; the page
   that uses it puts it in its scene and adds what it needs (halo, bubble, places to stand). */
var R = (typeof R === 'object' && R) || {};

R.COL = { ro: 0x35b56f, rw: 0x3d8bff, zero: 0xe8edf2, bg: 0x0b1118, floor: 0x101923,
          free: 0x1b2632, sram: 0x1f6670, listed: 0x232f3d, list: 0xd9a23a, reserved: 0x36d6e7,
          under: 0x121a23, slot: 0x18222d, kernel: 0xf4d35e, hw: 0xb48cff, bad: 0xff5d5d, ok: 0x7ee2a8 };
/* the lamp on the access gate: nothing asked, let through, stopped */
R.GATE = { idle: 0x5a6b7c, pass: 0x7ee2a8, stop: 0xff5d5d };
/* user software: one look per program. The shape tells them apart first, the colour second;
   none of these colours means anything else in the scene. */
R.USER_LOOK = [['screen', 0xff8fb1], ['phones', 0xff9950], ['dish', 0xeef2f6], ['stack', 0xb9e04f],
               ['screen', 0xe36bd6], ['phones', 0x9ad0ff], ['dish', 0xffd0a8], ['stack', 0xc9b8ff]];
R.userCss = function (i) { return '#' + R.USER_LOOK[i % R.USER_LOOK.length][1].toString(16).padStart(6, '0'); };

R.makeText = function (text, o) {
  o = o || {};
  var cv = document.createElement('canvas'), ctx = cv.getContext('2d');
  var tex = new THREE.CanvasTexture(cv);
  tex.generateMipmaps = false; tex.minFilter = THREE.LinearFilter;
  var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: o.depthTest !== false, depthWrite: false }));
  var h = o.h || 2.2, px = 44, font = '600 ' + px + 'px "IBM Plex Mono", ui-monospace, Menlo, monospace';
  sp.setText = function (t) {
    sp.visible = !!t; if (!t) return;
    ctx.font = font;
    var w = Math.ceil(ctx.measureText(t).width) + 36;
    cv.width = w; cv.height = px + 28;
    ctx.font = font;
    if (o.bg) { ctx.fillStyle = o.bg; ctx.beginPath(); ctx.rect(0, 0, w, cv.height); ctx.fill(); }
    ctx.fillStyle = o.color || '#dfe8f1'; ctx.textBaseline = 'middle';
    ctx.fillText(t, 18, cv.height / 2 + 2);
    tex.needsUpdate = true;
    sp.scale.set(h * w / cv.height, h, 1);
  };
  sp.setText(text);
  return sp;
};

R.hatchTexture = function () {
  var cv = document.createElement('canvas'); cv.width = cv.height = 64;
  var c = cv.getContext('2d');
  c.fillStyle = '#ffffff'; c.fillRect(0, 0, 64, 64);
  c.strokeStyle = '#5b6672'; c.lineWidth = 9;
  for (var i = -64; i < 128; i += 21) { c.beginPath(); c.moveTo(i, 64); c.lineTo(i + 64, 0); c.stroke(); }
  var t = new THREE.CanvasTexture(cv); t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
};

/* ---- characters */
R.chars = {};
R.chars.kernel = function () {
  var g = new THREE.Group(), L = THREE.MeshLambertMaterial, a = {};
  var body = new THREE.Mesh(new THREE.CylinderGeometry(1.25, 1.7, 3.6, 16), new L({ color: R.COL.kernel })); body.position.y = 3.4; g.add(body);
  var vest = new THREE.Mesh(new THREE.CylinderGeometry(1.45, 1.52, 0.42, 16), new L({ color: 0xffffff })); vest.position.y = 3.6; g.add(vest);
  var head = new THREE.Mesh(new THREE.SphereGeometry(1.2, 18, 14), new L({ color: 0xf6dcc0 })); head.position.y = 6.3; g.add(head);
  var hat = new THREE.Mesh(new THREE.SphereGeometry(1.32, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2), new L({ color: R.COL.kernel })); hat.position.y = 6.55; g.add(hat);
  var brim = new THREE.Mesh(new THREE.CylinderGeometry(1.75, 1.75, 0.14, 18), new L({ color: R.COL.kernel })); brim.position.y = 6.6; g.add(brim);
  [-0.45, 0.45].forEach(function (x) { var e = new THREE.Mesh(new THREE.SphereGeometry(0.16, 8, 8), new THREE.MeshBasicMaterial({ color: 0x1a1a1a })); e.position.set(x, 6.2, 1.08); g.add(e); });
  a.legs = [-0.6, 0.6].map(function (x) { var l = new THREE.Mesh(new THREE.BoxGeometry(0.7, 1.7, 0.8), new L({ color: 0x3b4758 })); l.position.set(x, 0.85, 0); g.add(l); return l; });
  var board = new THREE.Mesh(new THREE.BoxGeometry(1.3, 1.7, 0.14), new L({ color: 0x8b6b43 })); board.position.set(1.7, 3.6, 0.9); board.rotation.x = -0.5; g.add(board);
  a.hands = new THREE.Object3D(); a.hands.position.set(0, 4.2, 2.3); g.add(a.hands);
  a.group = g; a.pos = g.position; a.walk = 0; a.baseY = 0; a.s = 1;
  a.top = function () { return 7.9 * a.s; };
  return a;
};

R.chars.robot = function () {
  var g = new THREE.Group(), L = THREE.MeshLambertMaterial, a = {}, inner = new THREE.Group();
  g.add(inner);
  var body = new THREE.Mesh(new THREE.BoxGeometry(3.2, 2.6, 2.6), new L({ color: 0x8d74d6 })); body.position.y = 1.6; inner.add(body);
  var chest = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.9, 0.2), new THREE.MeshBasicMaterial({ color: 0xefe8ff })); chest.position.set(0, 1.7, 1.35); inner.add(chest);
  var head = new THREE.Mesh(new THREE.BoxGeometry(2.3, 1.6, 2), new L({ color: R.COL.hw })); head.position.y = 3.9; inner.add(head);
  var visor = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.5, 0.2), new THREE.MeshBasicMaterial({ color: 0x5ff1ff })); visor.position.set(0, 4.0, 1.0); inner.add(visor);
  var ant = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 1.2, 6), new L({ color: 0xc3cad8 })); ant.position.y = 5.3; inner.add(ant);
  var tip = new THREE.Mesh(new THREE.SphereGeometry(0.24, 8, 8), new THREE.MeshBasicMaterial({ color: R.COL.hw })); tip.position.y = 5.95; inner.add(tip);
  [-2, 2].forEach(function (x) { var arm = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.6, 2.6), new L({ color: 0x6a55b0 })); arm.position.set(x, 1.4, 1.2); inner.add(arm); });
  a.flame = new THREE.Mesh(new THREE.ConeGeometry(0.9, 2.2, 12), new THREE.MeshBasicMaterial({ color: 0x8d74ff, transparent: true, opacity: 0.75 }));
  a.flame.rotation.x = Math.PI; a.flame.position.y = -0.8; inner.add(a.flame);
  a.hands = new THREE.Object3D(); a.hands.position.set(0, 1.2, 3.0); inner.add(a.hands);
  /* the descriptor of the job in hand, shown as a sheet on the shoulder until the completion is reported */
  a.order = new THREE.Mesh(new THREE.BoxGeometry(1.7, 2.1, 0.14), new THREE.MeshBasicMaterial({ color: R.COL.kernel }));
  a.order.position.set(2.3, 4.6, 0.4); a.order.rotation.z = -0.25; a.order.visible = false; inner.add(a.order);
  a.group = g; a.inner = inner; a.pos = g.position; a.baseY = 4.2; a.walk = 0; a.s = 1; a.lift = a.baseY;
  a.top = function () { return a.lift + 6.4 * a.s; };
  return a;
};

/* A user program. Four shapes: a monitor for a head, headphones, a dish antenna, a pile of discs. */
R.chars.user = function (i, name) {
  var look = R.USER_LOOK[i % R.USER_LOOK.length], shape = look[0], color = look[1], T = THREE;
  var g = new T.Group(), L = T.MeshLambertMaterial, B = T.MeshBasicMaterial, a = {}, hgt, o;
  var add = function (geo, mat, x, y, z) { var m = new T.Mesh(geo, mat); m.position.set(x || 0, y || 0, z || 0); g.add(m); return m; };
  var main = new L({ color: color }), ink = new L({ color: 0x2a3644 }), eye = new B({ color: 0x10161d }), skin = new L({ color: 0xf6dcc0 });
  var eyes = function (dx, y, z, r) { [-dx, dx].forEach(function (x) { add(new T.SphereGeometry(r || 0.16, 8, 8), eye, x, y, z); }); };
  if (shape === 'screen') {
    [-0.65, 0.65].forEach(function (x) { add(new T.BoxGeometry(0.75, 1.5, 0.85), ink, x, 0.75, 0); });
    add(new T.BoxGeometry(2.5, 2.5, 1.5), main, 0, 2.75, 0);
    add(new T.BoxGeometry(0.55, 0.6, 0.55), ink, 0, 4.2, 0);
    add(new T.BoxGeometry(4.2, 2.9, 0.7), ink, 0, 5.9, 0);
    add(new T.BoxGeometry(3.7, 2.4, 0.12), new B({ color: color }), 0, 5.9, 0.38);
    [-0.85, 0.85].forEach(function (x) { add(new T.BoxGeometry(0.5, 0.8, 0.1), eye, x, 6.1, 0.46); });
    hgt = 7.6;
  } else if (shape === 'phones') {
    add(new T.SphereGeometry(1.95, 18, 14), main, 0, 2.3, 0);
    add(new T.SphereGeometry(1.25, 18, 14), skin, 0, 5.2, 0);
    add(new T.TorusGeometry(1.45, 0.22, 8, 20, Math.PI), ink, 0, 5.25, 0);
    [-1.5, 1.5].forEach(function (x) { o = add(new T.CylinderGeometry(0.68, 0.68, 0.55, 14), main, x, 5.1, 0); o.rotation.z = Math.PI / 2; });
    eyes(0.42, 5.3, 1.14);
    o = add(new T.ConeGeometry(0.7, 1.05, 3), new B({ color: 0xffffff }), 0.1, 2.5, 1.9); o.rotation.z = -Math.PI / 2; o.scale.z = 0.2;
    hgt = 7.2;
  } else if (shape === 'dish') {
    add(new T.CylinderGeometry(0.55, 1.95, 4.2, 16), main, 0, 2.1, 0);
    add(new T.SphereGeometry(1.05, 16, 12), main, 0, 4.9, 0);
    eyes(0.38, 5.0, 0.95);
    add(new T.CylinderGeometry(0.1, 0.1, 1.5, 6), ink, 0, 6.5, 0);
    o = add(new T.SphereGeometry(1.5, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), new L({ color: color, side: T.DoubleSide }), 0, 8.5, 0); o.rotation.x = Math.PI - 0.55;
    add(new T.SphereGeometry(0.24, 8, 8), new B({ color: 0x10161d }), 0, 8.3, 0.5);
    hgt = 8.9;
  } else {
    [0.7, 1.95, 3.2].forEach(function (y, k) { add(new T.CylinderGeometry(2.05, 2.05, 0.95, 20), k === 1 ? new L({ color: 0xffffff }) : main, 0, y, 0); });
    add(new T.CylinderGeometry(1.15, 1.15, 1.6, 18), skin, 0, 4.6, 0);
    eyes(0.4, 4.75, 1.08);
    add(new T.CylinderGeometry(1.55, 1.55, 0.2, 18), main, 0, 5.5, 0);
    o = add(new T.CylinderGeometry(0.16, 0.16, 3.4, 6), new L({ color: 0xffffff }), 2.3, 4.4, 0); o.rotation.z = -0.3;
    hgt = 6.3;
  }
  a.hands = new T.Object3D(); a.hands.position.set(0, 3.6, 2.4); g.add(a.hands);
  a.group = g; a.pos = g.position; a.walk = 0; a.k = 0.95; a.active = false; a.idx = i; a.name = name; a.color = color; a.css = R.userCss(i);
  a.top = function () { return hgt * a.k; };
  return a;
};

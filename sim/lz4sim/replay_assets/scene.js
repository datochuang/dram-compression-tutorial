/* Replay scene: the machine as a place, seen from the memory side. Nothing tall stands in the
   foreground. From near to far: the two ledgers lying on the floor (COT on the left, chunk
   bitmap on the right in the software variant), the memory itself (frame cache left, chunk pool
   right) with the LZ4 press and the SRAM stack tower (baseline) in the aisle between them, the
   job ring where KERNEL SW and LZ4 HW meet, the access gate, and at the far end the user
   programs that all of it works for.
   Units: one chunk slot = 1. */

R.Scene = function (model, canvas) {
  var m = model.meta, self = this, C = R.COL;
  this.model = model;
  this.renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, powerPreference: 'high-performance' });
  this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  this.scene = new THREE.Scene();
  this.scene.background = new THREE.Color(C.bg);
  this.scene.fog = new THREE.Fog(C.bg, 260, 720);
  this.camera = new THREE.PerspectiveCamera(42, 1, 1, 5000);
  this.scene.add(new THREE.HemisphereLight(0xcfe3ff, 0x0b1118, 0.95));
  var sun = new THREE.DirectionalLight(0xffffff, 0.75); sun.position.set(-60, 160, 120); this.scene.add(sun);

  /* layout */
  this.poolCols = 128; this.poolRows = Math.ceil(m.pool_chunks / 128);
  this.frameCols = 32; this.frameRows = Math.ceil(m.frames / 32);
  this.cotCols = 128; this.cotRows = Math.ceil(m.pages / 128);
  /* far edge of the two ledgers on the floor, in front of the frame cache and the chunk pool */
  this.zCot = this.frameRows * 2 + 14;
  this.zBit = this.poolRows / 2 + 14;
  this.zRing = 18; this.zTower = this.poolRows / 2 + 13; this.xTower = 40;
  this.hatch = R.hatchTexture();
  this.effects = [];
  this.temps = [];

  var floor = new THREE.Mesh(new THREE.PlaneGeometry(6000, 6000), new THREE.MeshLambertMaterial({ color: C.floor }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -0.08; this.scene.add(floor);

  /* frame cache */
  var I = THREE.InstancedMesh, L = THREE.MeshLambertMaterial;
  this.slots = new I(new THREE.BoxGeometry(3.6, 0.12, 3.6), new L({ color: 0xffffff }), m.frames);
  this.slabs = new I(new THREE.BoxGeometry(3.3, 1, 3.3), new L({ color: 0xffffff }), m.frames);
  /* chunk pool */
  this.tiles = new I(new THREE.BoxGeometry(0.86, 0.1, 0.86), new L({ color: 0xffffff }), m.pool_chunks);
  this.bricks = new I(new THREE.BoxGeometry(0.86, 0.62, 0.86), new L({ color: 0xffffff, map: this.hatch }), m.pool_chunks);
  [this.slots, this.slabs, this.tiles, this.bricks].forEach(function (x) { x.frustumCulled = false; self.scene.add(x); });
  var d = new THREE.Object3D(), col = new THREE.Color(C.slot), i;
  for (i = 0; i < m.frames; i++) { d.position.copy(this.framePos(i)); d.scale.set(1, 1, 1); d.updateMatrix(); this.slots.setMatrixAt(i, d.matrix); this.slots.setColorAt(i, col); }
  for (i = 0; i < m.pool_chunks; i++) { d.position.copy(this.chunkPos(i)); d.updateMatrix(); this.tiles.setMatrixAt(i, d.matrix); }

  /* COT ledger: flat on the floor, entry 0 at the far left corner */
  this.cotCv = document.createElement('canvas'); this.cotCv.width = this.cotCols * 8; this.cotCv.height = this.cotRows * 8;
  this.cotTex = new THREE.CanvasTexture(this.cotCv); this.cotTex.generateMipmaps = false; this.cotTex.minFilter = THREE.LinearFilter; this.cotTex.magFilter = THREE.NearestFilter;
  var wall = new THREE.Mesh(new THREE.PlaneGeometry(this.cotCols, this.cotRows), new THREE.MeshBasicMaterial({ map: this.cotTex }));
  wall.rotation.x = -Math.PI / 2; wall.position.set(-76, 0.24, this.zCot + this.cotRows / 2); this.scene.add(wall);
  var back = new THREE.Mesh(new THREE.BoxGeometry(this.cotCols + 3, 0.3, this.cotRows + 3), new L({ color: 0x1a2531 }));
  back.position.set(-76, 0.02, this.zCot + this.cotRows / 2); this.scene.add(back);

  /* chunk bitmap ledger (software variant): flat on the floor, half a unit per row */
  if (model.variant === 'software') {
    this.bitCv = document.createElement('canvas'); this.bitCv.width = this.poolCols * 4; this.bitCv.height = this.poolRows * 4;
    this.bitTex = new THREE.CanvasTexture(this.bitCv); this.bitTex.generateMipmaps = false; this.bitTex.minFilter = THREE.LinearFilter; this.bitTex.magFilter = THREE.NearestFilter;
    var bw = new THREE.Mesh(new THREE.PlaneGeometry(this.poolCols, this.poolRows / 2), new THREE.MeshBasicMaterial({ map: this.bitTex }));
    bw.rotation.x = -Math.PI / 2; bw.position.set(76, 0.24, this.zBit + this.poolRows / 4); this.scene.add(bw);
    var bb = new THREE.Mesh(new THREE.BoxGeometry(this.poolCols + 3, 0.3, this.poolRows / 2 + 3), new L({ color: 0x1a2531 }));
    bb.position.set(76, 0.02, this.zBit + this.poolRows / 4); this.scene.add(bb);
  } else {
    /* SRAM stack tower (baseline) */
    this.towerH = 26; var zt = this.zTower, xt = this.xTower;
    var tube = new THREE.Mesh(new THREE.CylinderGeometry(2.6, 2.6, this.towerH, 24, 1, true),
      new THREE.MeshBasicMaterial({ color: 0x9fb4c8, transparent: true, opacity: 0.16, side: THREE.DoubleSide, depthWrite: false }));
    tube.position.set(xt, this.towerH / 2, zt); this.scene.add(tube);
    this.towerFill = new THREE.Mesh(new THREE.CylinderGeometry(2.3, 2.3, 1, 24), new L({ color: C.sram, emissive: 0x0d3a40 }));
    this.towerFill.position.set(xt, 0, zt); this.scene.add(this.towerFill);
    [m.refill_below, m.spill_above].forEach(function (v) {
      var ring = new THREE.Mesh(new THREE.TorusGeometry(2.75, 0.09, 8, 32), new THREE.MeshBasicMaterial({ color: C.list }));
      ring.rotation.x = Math.PI / 2; ring.position.set(xt, self.towerH * v / m.sram_cap, zt); self.scene.add(ring);
      var t = R.makeText(String(v), { h: 1.5, color: '#d9a23a' }); t.position.set(xt + 4.6, self.towerH * v / m.sram_cap, zt); self.scene.add(t);
    });
    this.towerText = R.makeText('', { h: 1.9, color: '#8fe3ee' }); this.towerText.position.set(xt, this.towerH + 2.2, zt); this.scene.add(this.towerText);
    this.listText = R.makeText('', { h: 1.6, color: '#d9a23a' }); this.listText.position.set(xt, this.towerH + 4.4, zt); this.scene.add(this.listText);
  }

  /* job ring and press */
  var desk = new THREE.Mesh(new THREE.CylinderGeometry(3.4, 3.8, 1.6, 28), new L({ color: 0x2a3848 }));
  desk.position.set(0, 0.8, this.zRing); this.scene.add(desk);
  var ringM = new THREE.Mesh(new THREE.TorusGeometry(2.6, 0.22, 8, 32), new THREE.MeshBasicMaterial({ color: C.kernel }));
  ringM.rotation.x = Math.PI / 2; ringM.position.set(0, 1.7, this.zRing); this.scene.add(ringM);
  var base = new THREE.Mesh(new THREE.BoxGeometry(6, 1, 6), new L({ color: 0x3a3350 })); base.position.set(0, 0.5, 0); this.scene.add(base);
  [-2.7, 2.7].forEach(function (x) { var p = new THREE.Mesh(new THREE.BoxGeometry(0.5, 7, 0.5), new L({ color: 0x4a4266 })); p.position.set(x, 3.5, -2.7); self.scene.add(p); });
  this.plate = new THREE.Mesh(new THREE.BoxGeometry(5.4, 0.6, 5.4), new L({ color: 0x8d74d6, emissive: 0x241a44 }));
  this.plate.position.set(0, 6.4, 0); this.scene.add(this.plate);
  this.pressPos = new THREE.Vector3(0, 1.0, 0);

  /* station labels */
  this.labels = [];
  var lab = function (t, x, y, z, h, color) { var s = R.makeText(t, { h: h || 2.6, color: color || '#8ea2b6', depthTest: y > 1 }); s.position.set(x, y, z); self.scene.add(s); self.labels.push({ o: s, x: s.scale.x, y: s.scale.y }); return s; };
  lab('FRAME CACHE  ' + m.frames + ' frames x 4096 B  (uncompressed)', -76, 0.4, this.frameRows * 2 + 6.5);
  lab('CHUNK POOL  ' + m.pool_chunks.toLocaleString() + ' chunks x 512 B  (hatched = compressed)', 76, 0.4, this.poolRows / 2 + 6.5);
  lab('COT  ' + m.pages.toLocaleString() + ' entries x 32 B   written by: ' + (model.variant === 'software' ? 'KERNEL' : 'HARDWARE (RW) / build tool (RO)'), -76, 0.4, this.zCot + this.cotRows + 5.5);
  if (model.variant === 'software') lab('CHUNK BITMAP  1 bit per chunk  (kernel)', 76, 0.4, this.zBit + this.poolRows / 2 + 5.5, 2.6, '#f4d35e');
  else lab('FREE STACK  SRAM top (hardware)', this.xTower, this.towerH + 6.8, this.zTower, 1.8, '#b48cff');
  lab('JOB RING  descriptors and completions', 0, 0.4, this.zRing + 6.5, 1.5); lab('LZ4 ENGINE', 0, 9, -3, 1.7, '#b48cff');

  /* user SW lane: the programs that everything else works for stand at the far end, where they
     cover nothing; they look over the gate at the machine */
  this.zUser = -(Math.max(this.frameRows * 2, this.poolRows / 2, 24) + 30);
  var lane = new THREE.Mesh(new THREE.PlaneGeometry(290, 22), new L({ color: 0x172432 }));
  lane.rotation.x = -Math.PI / 2; lane.position.set(0, 0.06, this.zUser + 1); this.scene.add(lane);
  lab('USER SW  the programs that use the memory  (KERNEL SW and LZ4 HW work for them)', 0, 0.4, this.zUser - 13, 2.2, '#c9d6e2');
  this.users = (model.clients || []).map(function (c, i, all) { return self.makeUser(i, c, all.length); });

  /* the access gate: MMU and page table. Every access of every user program arrives at this one
     place. A valid PTE lets it through to its frame without the kernel; an invalid one stops it
     here, the request stays on the counter and KERNEL SW is called. */
  var gz = this.zGate = this.zUser + 17, GM = new L({ color: 0x9fb4cc, emissive: 0x1c2733 }), G = this.gateG = new THREE.Group(), part;
  G.position.set(0, 0, gz); this.scene.add(G);
  part = new THREE.Mesh(new THREE.BoxGeometry(28, 2.2, 3.4), new L({ color: 0x4a6078 })); part.position.set(0, 1.1, 0); G.add(part);
  [-14.6, 14.6].forEach(function (x) { var p = new THREE.Mesh(new THREE.BoxGeometry(1.3, 14, 1.3), GM); p.position.set(x, 7, 0); G.add(p); });
  part = new THREE.Mesh(new THREE.BoxGeometry(30.5, 1.8, 1.8), GM); part.position.set(0, 14.6, 0); G.add(part);
  /* the pane in the arch and the lamp on top show the gate's answer: grey, green or red */
  this.pane = new THREE.Mesh(new THREE.PlaneGeometry(27.9, 11.5), new THREE.MeshBasicMaterial({ color: R.GATE.idle, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false }));
  this.pane.position.set(0, 7.95, 0); G.add(this.pane);
  this.lamp = new THREE.Mesh(new THREE.SphereGeometry(1.9, 20, 14), new THREE.MeshBasicMaterial({ color: R.GATE.idle }));
  this.lamp.position.set(0, 17.4, 0); G.add(this.lamp);
  this.ticket = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.22, 2.6), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  this.ticket.position.set(0, 2.45, -0.2); this.ticket.visible = false; G.add(this.ticket);
  lab('ACCESS GATE  MMU + page table: every access of every user SW arrives here', 0, 0.4, gz + 9, 1.5);
  this.gate = { pos: new THREE.Vector3(0, 0, gz), tray: new THREE.Vector3(0, 2.6, gz), mid: new THREE.Vector3(0, 8, gz), css: '#9fb4cc', k: 1, wr: 0.78,
                top: function () { return 20 * this.k; } };

  this.kernel = this.makeKernel(); this.robot = this.makeRobot();
  this.kernel.pos.set(-6, 0, this.zRing); this.robot.pos.set(5, 0, 5);
  /* what Overview has to keep in view */
  var soft = model.variant === 'software', top = soft ? 12 : this.towerH + 8;
  this.box = { x0: -143, x1: 143.5, y0: 0, y1: top, z0: this.zUser - 14, z1: Math.max(this.zCot + this.cotRows, soft ? this.zBit + this.poolRows / 2 : 0) + 9 };
  this._ov = new THREE.Vector3((this.box.x0 + this.box.x1) / 2, 0, (this.box.z0 + this.box.z1) / 2);
  var bx = this.box, zc = this.zCot + this.cotRows + 9, zp = soft ? this.zBit + this.poolRows / 2 + 9 : this.poolRows / 2 + 7;
  this.fitPts = [bx.x0, 0, bx.z0, bx.x1, 0, bx.z0, bx.x0, bx.y1, bx.z0, bx.x1, bx.y1, bx.z0,
                 bx.x0, 0, zc, -10, 0, zc, 10, 0, zp, bx.x1, 0, zp, bx.x0, 6, this.frameRows * 2, bx.x1, 2, this.poolRows / 2];
  if (!soft) this.fitPts.push(this.xTower, this.towerH + 8, this.zTower, this.xTower, 0, this.zTower + 6);
  /* the memory itself: speech bubbles try to stay off it */
  this.mem = [{ x0: -140, x1: -12, z0: -this.frameRows * 2, z1: this.frameRows * 2, wt: 0.055 }, { x0: 12, x1: 140, z0: -this.poolRows / 2, z1: this.poolRows / 2, wt: 0.03 }];
  this.bubbles = []; this.spoke = null; this._seq = 0;
  Array.prototype.slice.call(document.querySelectorAll('#bubbles .dyn')).forEach(function (e) { e.parentNode.removeChild(e); });
  this.kernel.bubble = this.makeBubble(this.kernel, 'bubKernel', 'tailKernel');
  this.robot.bubble = this.makeBubble(this.robot, 'bubHw', 'tailHw');
  this.users.forEach(function (u) { u.bubble = self.makeUserBubble(u); });
  this.gate.bubble = this.makeNamedBubble(this.gate, this.gate.css, ['MMU \u00b7 PAGE TABLE', 'MMU']);
  this.focus = new THREE.Vector3(0, 2, 0);
  this.cam = { target: new THREE.Vector3(0, 0, 4), r: 330, th: 0, ph: 0.92, mode: 'overview' };
  this.syncAll();
};

R.Scene.prototype.framePos = function (f) { return new THREE.Vector3(-140 + 2 + (f % this.frameCols) * 4, 0, -this.frameRows * 2 + 2 + Math.floor(f / this.frameCols) * 4); };
R.Scene.prototype.chunkPos = function (c) { return new THREE.Vector3(12.5 + (c % this.poolCols), 0, -this.poolRows / 2 + 0.5 + Math.floor(c / this.poolCols)); };
R.Scene.prototype.cotPos = function (h) { return new THREE.Vector3(-140 + 0.5 + (h % this.cotCols), 0.4, this.zCot + 0.5 + Math.floor(h / this.cotCols)); };
R.Scene.prototype.bitPos = function (c) { return new THREE.Vector3(12.5 + (c % this.poolCols), 0.4, this.zBit + (0.5 + Math.floor(c / this.poolCols)) / 2); };
R.Scene.prototype.centroid = function (chunks) { var v = new THREE.Vector3(); for (var i = 0; i < chunks.length; i++) v.add(this.chunkPos(chunks[i])); return chunks.length ? v.multiplyScalar(1 / chunks.length) : v; };
R.Scene.prototype.pageColor = function (h) { return this.model.isRO(h) ? R.COL.ro : R.COL.rw; };

/* ---- characters */
R.Scene.prototype.makeKernel = function () {
  var a = R.chars.kernel(); a.halo = this.makeHalo(R.COL.kernel); this.scene.add(a.group); return a;
};

R.Scene.prototype.makeRobot = function () {
  var a = R.chars.robot(); a.halo = this.makeHalo(R.COL.hw); this.scene.add(a.group); return a;
};

/* A user program: the figure comes from chars.js, the place to stand is set here. */
R.Scene.prototype.makeUser = function (i, client, n) {
  var a = R.chars.user(i, client.name), T = THREE;
  /* half of the programs stand left of the access gate, half right; the middle stays free */
  var nl = Math.ceil(n / 2), lf = i < nl, nm = lf ? nl : n - nl, ni = lf ? i : i - nl;
  a.home = new T.Vector3((lf ? -140 : 46) + 94 * (ni + 0.5) / nm, 0, this.zUser); a.front = a.home.clone(); a.front.z += 7; a.goal = a.home;
  a.pos.copy(a.home);
  a.halo = this.makeHalo(a.color); this.scene.add(a.group);
  return a;
};
/* the user program whose access is being served steps forward and grows; the others go home */
R.Scene.prototype.activate = function (u, step, snap) {
  this.users.forEach(function (x) { x.active = x === u; x.goal = x === u && step ? x.front : x.home; if (snap) x.pos.copy(x.goal); });
};
/* every bubble empty, no job in hand */
R.Scene.prototype.hush = function () {
  this.bubbles.forEach(function (b) { b.setText(''); });
  this.setOrder(null); this.setGate('idle'); this.setTicket(null);
};
/* the gate's lamp: 'idle', 'pass' (PTE valid) or 'stop' (PTE not valid, the kernel is called) */
R.Scene.prototype.setGate = function (st) {
  var c = R.GATE[st] || R.GATE.idle; this.gateState = st;
  this.lamp.material.color.setHex(c); this.pane.material.color.setHex(c); this.pane.material.opacity = st === 'pass' || st === 'stop' ? 0.5 : 0.22;
};
/* the request that waits on the gate's counter while the kernel works on it */
R.Scene.prototype.setTicket = function (color) {
  var o = this.ticket; o.visible = color !== null && color !== undefined;
  if (o.visible) o.material.color.setHex(color);
};
R.Scene.prototype.setOrder = function (color) {
  var o = this.robot.order; o.visible = color !== null && color !== undefined;
  if (o.visible) o.material.color.setHex(color);
};

/* the camera distance at which the whole machine fits the part of the view the panels leave free */
R.Scene.prototype.fitR = function () {
  var c = this.cam, w = this.vw, h = this.vh, fr = this.free, b = this.box;
  if (!w || !fr || fr.r - fr.l < 60 || fr.b - fr.t < 60) return 330;
  var key = [c.th.toFixed(3), c.ph.toFixed(3), w, h, fr.l, fr.t, fr.r, fr.b].join();
  if (key === this._fitKey) return this._fitR;
  var cam = this.camera.clone(), v = new THREE.Vector3(), t = this._ov, gz = this.zGate, uz = this.zUser, sp = Math.sin(c.ph), cp = Math.cos(c.ph), lo = 40, hi = 3000, i, mid;
  var vo = this.vo || { x: 0, y: 0 }, top, bot, H = fr.b - fr.t, self = this;
  cam.setViewOffset(w, h, vo.x, vo.y, w, h);
  var fits = function (r) {
    cam.position.set(t.x + r * sp * Math.sin(c.th), t.y + r * cp, t.z + r * sp * Math.cos(c.th)); cam.lookAt(t); cam.updateMatrixWorld();
    top = 1e9; bot = -1e9;
    for (var k = 0, P = self.fitPts; k < P.length; k += 3) {
      v.set(P[k], P[k + 1], P[k + 2]).project(cam);
      var px = (v.x + 1) / 2 * w, py = (1 - v.y) / 2 * h;
      if (v.z > 1 || px < fr.l + 10 || px > fr.r - 10) return false;
      top = Math.min(top, py - 16); bot = Math.max(bot, py + 12);
    }
    /* the gate and the user programs stand at the far end, so they come out near the top of the
       view: keep room above them for what they say */
    var cs = Math.max(1, Math.min(4.5, r / 150)), room = Math.min(92, H * 0.2);
    v.set(0, 20 * Math.max(1, Math.min(2.4, cs * 0.75)), gz).project(cam); top = Math.min(top, (1 - v.y) / 2 * h - room);
    v.set(b.x1 - 26, 9 * cs, uz).project(cam); top = Math.min(top, (1 - v.y) / 2 * h - room);
    /* only the height counts here: the picture is moved down afterwards */
    return bot - top <= H;
  };
  for (i = 0; i < 20; i++) { mid = (lo + hi) / 2; if (fits(mid)) hi = mid; else lo = mid; }
  /* height that is left over goes mostly above the far end, where the bubbles are */
  fits(hi); this._fitDy = Math.round(fr.b - (H - (bot - top)) * 0.15 - bot);
  this._fitKey = key; this._fitR = hi;
  return hi;
};

/* a ring on the floor under each character, in the character's colour */
R.Scene.prototype.makeHalo = function (color) {
  var ring = new THREE.Mesh(new THREE.RingGeometry(2.3, 3.1, 36), new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.9, side: THREE.DoubleSide }));
  ring.rotation.x = -Math.PI / 2; this.scene.add(ring); return ring;
};

/* ---- speech bubbles. They are DOM elements placed over the canvas, so the text keeps one
   readable size at every camera distance. Each bubble carries the character's name. */
R.Scene.prototype.makeBubble = function (a, id, tailId) {
  return this.addBubble(a, document.getElementById(id), document.getElementById(tailId), tailId === 'tailHw' ? 'tail-hw' : 'tail-kernel');
};
/* a user program's bubble is made here, in the program's colour. names: [full, short] */
R.Scene.prototype.makeUserBubble = function (u) { return this.makeNamedBubble(u, u.css, ['USER SW \u00b7 ' + u.name, u.name]); };
R.Scene.prototype.makeNamedBubble = function (a, css, names) {
  var box = document.getElementById('bubbles'), NS = 'http://www.w3.org/2000/svg';
  var el = document.createElement('div'), svg = document.createElementNS(NS, 'svg'), tail = document.createElementNS(NS, 'path');
  el.className = 'bub bub-user dyn'; el.style.setProperty('--c', css);
  el.innerHTML = '<b class="bname"></b><span class="btext"></span>';
  svg.setAttribute('class', 'tails dyn'); tail.setAttribute('class', 'tail tail-user'); tail.setAttribute('d', 'M0 0'); tail.style.setProperty('--c', css);
  svg.appendChild(tail); box.appendChild(el); box.appendChild(svg);
  return this.addBubble(a, el, tail, 'tail-user', names);
};
R.Scene.prototype.addBubble = function (a, el, tail, tcls, names) {
  var self = this;
  var b = { el: el, tail: tail, svg: tail && tail.parentNode, text: el && el.querySelector('.btext'), nameEl: el && el.querySelector('.bname'), names: names || null,
            cls: el ? el.className.replace(/ quiet/g, '') : '', tcls: tcls, i: this.bubbles.length, seq: 0,
            actor: a, t: '', dirty: true, w: 0, h: 0, px: 0, py: 0, x: 0, y: 0, side: 0, on: false, last: '' };
  b.setText = function (t) { t = t || ''; if (t) { self.spoke = b; b.seq = ++self._seq; } if (t === b.t) return; b.t = t; b.dirty = true; };
  this.bubbles.push(b);
  return b;
};
R.Scene.prototype.layoutBubbles = function () {
  var bs = this.bubbles, N = bs.length, w = this.vw, h = this.vh, i, j, b, q, o, v = this._bv || (this._bv = new THREE.Vector3());
  if (N < 2 || !bs[0].el || !bs[1].el || !w) return;
  var fr = this.free || { l: 8, t: 8, r: w - 8, b: h - 8 }, g = 8, wide = w >= 700;
  var cl = function (x, lo, hi) { return hi < lo ? lo : Math.max(lo, Math.min(hi, x)); };
  /* b.t is what the character says, b.s what the bubble shows. A narrow view has room for two
     texts only, so there the older speakers fold back to their name chips. */
  var s1 = 0, s2 = 0;
  if (!wide) for (i = 0; i < N; i++) { q = bs[i].t ? bs[i].seq : 0; if (q > s1) { s2 = s1; s1 = q; } else if (q > s2) s2 = q; }
  for (i = 0; i < N; i++) {
    b = bs[i];
    q = b.t && (wide || b.seq >= s2) ? b.t : ''; if (q !== b.s) { b.s = q; b.dirty = true; }
    if (b.dirty) {
      b.text.textContent = b.s; b.el.className = b.cls + (b.s ? '' : ' quiet');
      if (b.names) b.nameEl.textContent = b.s || wide ? b.names[0] : b.names[1];
      b.tail.setAttribute('class', 'tail ' + b.tcls + (b.s ? '' : ' quiet'));
      b.w = b.el.offsetWidth; b.h = b.el.offsetHeight; b.dirty = false; b.keep = false;
    }
    v.set(b.actor.pos.x, b.actor.top(), b.actor.pos.z).project(this.camera);
    b.on = v.z > -1 && v.z < 1; b.px = (v.x + 1) / 2 * w; b.py = (1 - v.y) / 2 * h;
    /* the place the character itself takes on screen: from its top down to its feet */
    v.set(b.actor.pos.x, 0, b.actor.pos.z).project(this.camera);
    b.fy = (1 - v.y) / 2 * h; b.hw = Math.max(12, (b.fy - b.py) * (b.actor.wr || 0.36));
    b.wt = b.t || b.actor.active || (b.actor === this.gate && this.gateState && this.gateState !== 'idle') ? 0.6 : 0.25;
  }
  /* where the frame cache and the chunk pool are on screen */
  var mem = this.mem, M = mem.length, m;
  for (i = 0; i < M; i++) {
    m = mem[i]; m.l = 1e9; m.t = 1e9; m.r = -1e9; m.b = -1e9;
    for (j = 0; j < 4; j++) {
      v.set(j & 1 ? m.x1 : m.x0, 1, j & 2 ? m.z1 : m.z0).project(this.camera);
      m.l = Math.min(m.l, (v.x + 1) / 2 * w); m.r = Math.max(m.r, (v.x + 1) / 2 * w); m.t = Math.min(m.t, (1 - v.y) / 2 * h); m.b = Math.max(m.b, (1 - v.y) / 2 * h);
    }
  }
  /* of the kernel and the accelerator, the one further left gets a bubble that grows to the left.
     A user program's bubble grows towards the middle of the view. */
  var d = bs[0].px - bs[1].px, mid = (fr.l + fr.r) / 2;
  if (!this._side) this._side = d <= 0 ? -1 : 1; else if (d < -50) this._side = -1; else if (d > 50) this._side = 1;
  bs[0].side = this._side; bs[1].side = -this._side;
  for (i = 2; i < N; i++) { b = bs[i]; if (!b.side || Math.abs(b.px - mid) > 40) b.side = b.px < mid ? 1 : -1; }
  for (i = 0; i < N; i++) {
    b = bs[i];
    b.x = cl(!b.s ? b.px - b.w / 2 : b.side < 0 ? b.px + 26 - b.w : b.px - 26, fr.l, fr.r - b.w);
    b.y = cl(b.py - (b.s ? 30 : 16) - b.h, fr.t, fr.b - b.h);
  }
  /* placing order: bubbles with text first, the latest speaker before the others. A bubble
     that would cover one placed before it moves aside, or above, or below. */
  var ord = this._ord || (this._ord = []), key = '';
  ord.length = 0; for (i = 0; i < N; i++) ord.push(bs[i]);
  ord.sort(function (p, r) { return (r.s ? 1 : 0) - (p.s ? 1 : 0) || r.seq - p.seq || p.i - r.i; });
  /* how much of a bubble at (x, y) would lie over the ones placed before it; a name chip counts less */
  var over = function (p, x, y, upto) {
    for (var k = 0, a = 0; k < upto; k++) {
      var r = ord[k]; if (!r.on) continue;
      var ox = Math.min(x + p.w, r.x + r.w + g) - Math.max(x, r.x - g), oy = Math.min(y + p.h, r.y + r.h + g) - Math.max(y, r.y - g);
      if (ox > 0 && oy > 0) a += ox * oy * (r.s ? 1 : 0.3);
    }
    return a;
  };
  /* how much of it would lie over the characters and the gate: the ones in the story count most */
  var hide = function (p, x, y) {
    for (var k = 0, a = 0; k < N; k++) {
      var r = bs[k]; if (!r.on) continue;
      var ox = Math.min(x + p.w, r.px + r.hw) - Math.max(x, r.px - r.hw), oy = Math.min(y + p.h, r.fy) - Math.max(y, r.py - 4);
      if (ox > 0 && oy > 0) a += ox * oy * r.wt;
    }
    for (k = 0; k < M; k++) {
      r = mem[k]; ox = Math.min(x + p.w, r.r) - Math.max(x, r.l); oy = Math.min(y + p.h, r.b) - Math.max(y, r.t);
      if (ox > 0 && oy > 0) a += ox * oy * r.wt;
    }
    return a;
  };
  /* a place costs: far more than anything else if it covers a bubble, then what it hides of the
     characters, then how far it is from the usual place above the speaker */
  var cost = function (p, x, y, upto, x0, y0) {
    var o = over(p, x, y, upto), far = Math.hypot(x - x0, y - y0);
    /* a long tail across the scene is worse than its length alone */
    return (o ? 1e6 + o * 10 : 0) + (p.s ? hide(p, x, y) * 0.2 : 0) + far + Math.max(0, far - 170);
  };
  var cs = this._cs || (this._cs = []);
  for (i = 0; i < N; i++) {
    b = ord[i]; if (!b.on) continue;
    var x0 = b.x, y0 = b.y, cx, cy, best = -1, bs0 = 0, sc, kc = -1;
    if (b.keep) { b.x = cl(b.px + b.kx, fr.l, fr.r - b.w); b.y = cl(b.py + b.ky, fr.t, fr.b - b.h); kc = cost(b, b.x, b.y, i, x0, y0); }
    if (cost(b, x0, y0, i, x0, y0) < 1) { if (kc < 0 || kc >= 1e6) { b.keep = false; b.x = x0; b.y = y0; } continue; }
    /* candidates: the usual place, the other side of the character, under it, and around every
       bubble already placed and every character */
    cs.length = 0;
    cs.push(x0, y0, b.side < 0 ? b.px - 26 : b.px + 26 - b.w, y0, x0, b.fy + 16, b.px - b.hw - 14 - b.w, b.py, b.px + b.hw + 14, b.py);
    for (j = 0; j < i; j++) {
      q = ord[j]; if (!q.on) continue;
      cs.push(q.x - g - b.w, y0, q.x + q.w + g, y0, x0, q.y - g - b.h, x0, q.y + q.h + g, q.x - g - b.w, q.y, q.x + q.w + g, q.y);
    }
    if (b.s) for (j = 0; j < N; j++) {
      q = bs[j]; if (!q.on) continue;
      cs.push(q.px - q.hw - g - b.w, y0, q.px + q.hw + g, y0, x0, q.py - 4 - g - b.h, x0, q.fy + g);
    }
    if (b.s) for (j = 0; j < M; j++) { m = mem[j]; cs.push(x0, m.t - g - b.h, x0, m.b + g, m.l - g - b.w, y0, m.r + g, y0, b.px + b.hw + 14, m.b + g, b.px - b.hw - 14 - b.w, m.b + g, m.r + g, b.fy + 16); }
    for (j = 0; j < cs.length; j += 2) {
      cx = cl(cs[j], fr.l, fr.r - b.w); cy = cl(cs[j + 1], fr.t, fr.b - b.h);
      /* a quiet name chip stays near its character: better half covered than far away on a long tail */
      if (!b.s && Math.hypot(cx - x0, cy - y0) > 56) continue;
      sc = cost(b, cx, cy, i, x0, y0);
      if (best < 0 || sc < bs0) { best = j; bs0 = sc; b.x = cx; b.y = cy; }
    }
    /* a bubble that had to move stays where it went until another place is clearly better */
    if (kc >= 0 && kc <= bs0 + 60) { b.x = cl(b.px + b.kx, fr.l, fr.r - b.w); b.y = cl(b.py + b.ky, fr.t, fr.b - b.h); }
    else { b.keep = true; b.kx = b.x - b.px; b.ky = b.y - b.py; }
  }
  /* the later a bubble spoke, the further in front it is drawn; each tail sits over its own bubble */
  for (i = 0; i < N; i++) key += ord[i].i;
  if (key !== this._zkey) { this._zkey = key; for (i = 0; i < N; i++) { ord[i].el.style.zIndex = 2 * (N - i) - 1; ord[i].svg.style.zIndex = 2 * (N - i); } }
  for (i = 0; i < N; i++) {
    b = bs[i];
    var tx = cl(b.px, fr.l - 4, fr.r + 4), ty = cl(b.py - 3, fr.t - 30, fr.b + 4), x = Math.round(b.x), y = Math.round(b.y), m = Math.min(24, b.w / 2), hw = b.s ? 9 : 6, ins = 3.5, bx, by, path = '';
    if (ty > y + b.h) { bx = cl(tx, x + m, x + b.w - m); by = y + b.h - ins; path = 'M' + (bx - hw) + ' ' + by + 'L' + tx.toFixed(1) + ' ' + ty.toFixed(1) + 'L' + (bx + hw) + ' ' + by; }
    else if (ty < y) { bx = cl(tx, x + m, x + b.w - m); by = y + ins; path = 'M' + (bx - hw) + ' ' + by + 'L' + tx.toFixed(1) + ' ' + ty.toFixed(1) + 'L' + (bx + hw) + ' ' + by; }
    else if (tx < x) { by = cl(ty, y + m, y + b.h - m); bx = x + ins; path = 'M' + bx + ' ' + (by - hw) + 'L' + tx.toFixed(1) + ' ' + ty.toFixed(1) + 'L' + bx + ' ' + (by + hw); }
    else if (tx > x + b.w) { by = cl(ty, y + m, y + b.h - m); bx = x + b.w - ins; path = 'M' + bx + ' ' + (by - hw) + 'L' + tx.toFixed(1) + ' ' + ty.toFixed(1) + 'L' + bx + ' ' + (by + hw); }
    var op = !b.on ? 0 : (b.s && this.spoke && this.spoke !== b) ? 0.9 : 1;
    o = x + ',' + y + ',' + op + ',' + path;
    if (o !== b.last) {
      b.last = o;
      b.el.style.transform = 'translate(' + x + 'px,' + y + 'px)'; b.el.style.opacity = op; b.el.style.visibility = op ? 'visible' : 'hidden';
      b.tail.setAttribute('d', path || 'M0 0'); b.tail.style.opacity = path ? op : 0;
    }
  }
};

/* ---- temp objects that fly around */
R.Scene.prototype.temp = function (kind, color, hatched) {
  var geo = kind === 'slab' ? new THREE.BoxGeometry(3.3, 1, 3.3) : kind === 'brick' ? new THREE.BoxGeometry(0.86, 0.62, 0.86) : new THREE.BoxGeometry(2.6, 0.16, 1.9);
  var mat = new THREE.MeshLambertMaterial({ color: color, map: hatched ? this.hatch : null, emissive: kind === 'sheet' ? color : 0x000000, emissiveIntensity: 0.6 });
  var o = new THREE.Mesh(geo, mat); this.scene.add(o); this.temps.push(o); return o;
};
R.Scene.prototype.drop = function (o) {
  if (!o) return; if (o.parent) o.parent.remove(o);
  var i = this.temps.indexOf(o); if (i >= 0) this.temps.splice(i, 1);
  o.geometry.dispose(); o.material.dispose();
};
/* a ring that spreads and fades; onLedger: the spot is an entry of a ledger lying on the floor */
R.Scene.prototype.pulse = function (pos, color, onLedger, size) {
  var ring = new THREE.Mesh(new THREE.RingGeometry(0.55, 0.8, 24), new THREE.MeshBasicMaterial({ color: color, transparent: true, side: THREE.DoubleSide, depthTest: false }));
  ring.position.copy(pos); ring.rotation.x = -Math.PI / 2; if (!onLedger) ring.position.y += 1.3;
  this.scene.add(ring); this.effects.push({ o: ring, t: 0, d: 0.55, s: size || 4 });
};

/* a line that fades: who is touching what */
R.Scene.prototype.beam = function (a, b, color) {
  var t = Math.max(0.3, this.cam.r / 560), o = new THREE.Mesh(new THREE.BoxGeometry(t, t, a.distanceTo(b)), new THREE.MeshBasicMaterial({ color: color, transparent: true, depthTest: false }));
  o.position.copy(a).add(b).multiplyScalar(0.5); o.lookAt(b);
  this.scene.add(o); this.effects.push({ o: o, t: 0, d: 0.7, s: 0 });
};

/* ---- state to visuals */
R.Scene.prototype.syncChunk = function (c) {
  var md = this.model, K = R.K, C = R.COL, k = md.chunkKind[c], d = this._d || (this._d = new THREE.Object3D()), col = this._c || (this._c = new THREE.Color());
  var used = k === K.RO || k === K.RW;
  d.position.copy(this.chunkPos(c)); d.position.y = 0.4; d.scale.setScalar(used ? 1 : 0.0001); d.updateMatrix();
  this.bricks.setMatrixAt(c, d.matrix);
  this.bricks.setColorAt(c, col.setHex(k === K.RO ? C.ro : C.rw));
  this.tiles.setColorAt(c, col.setHex(used ? C.under : k === K.SRAM ? C.sram : k === K.LIST ? C.list : k === K.RESERVED ? C.reserved : k === K.LISTED ? C.listed : C.free));
  if (this.bitCv) {
    var x = this.bitCv.getContext('2d'), bit = used || k === K.RESERVED;
    x.fillStyle = k === K.RESERVED ? '#36d6e7' : bit ? (k === K.RO ? '#2c8f58' : '#3d8bff') : '#131c26';
    x.fillRect((c % this.poolCols) * 4, Math.floor(c / this.poolCols) * 4, 3, 3);
    this.bitTex.needsUpdate = true;
  }
};
R.Scene.prototype.syncFrame = function (f) {
  var md = this.model, h = md.frameOwner[f], d = this._d || (this._d = new THREE.Object3D()), col = this._c || (this._c = new THREE.Color());
  var p = this.framePos(f), filled = h >= 0 && md.filled[f];
  d.position.set(p.x, h < 0 ? 0 : filled ? 0.62 : 0.2, p.z);
  d.scale.set(h < 0 ? 0.0001 : 1, h < 0 ? 0.0001 : filled ? 1 : 0.12, h < 0 ? 0.0001 : 1); d.updateMatrix();
  this.slabs.setMatrixAt(f, d.matrix);
  if (h >= 0) {
    col.setHex(filled ? this.pageColor(h) : 0x71808f);
    var st = md.pageState[h];
    if (filled && !md.mapped[h]) col.multiplyScalar(st === R.S.compressing ? 0.7 : 0.5);
    this.slabs.setColorAt(f, col);
  }
};
R.Scene.prototype.syncCot = function (h) {
  var e = this.model.cot[h], x = this.cotCv.getContext('2d'), px = (h % this.cotCols) * 8, py = Math.floor(h / this.cotCols) * 8;
  var ro = this.model.isRO(h), st = this.model.pageState[h];
  x.fillStyle = '#0e151d'; x.fillRect(px, py, 8, 8);
  x.fillStyle = e ? (ro ? '#35b56f' : '#3d8bff') : (st === R.S.present ? '#2a3a4c' : '#172029');
  x.fillRect(px + 1, py + 1, 6, 6);
  if (e && ro && st === R.S.present) { x.fillStyle = '#d9ffe9'; x.fillRect(px + 3, py + 3, 2, 2); }
  if (e && (e.flags & 4)) { x.fillStyle = '#0e151d'; x.fillRect(px + 1, py + 1, 3, 3); }
  this.cotTex.needsUpdate = true;
};
R.Scene.prototype.sync = function () {
  var dd = this.model.dirty, i;
  if (dd.all) { this.syncAll(); return; }
  for (i = 0; i < dd.chunks.length; i++) this.syncChunk(dd.chunks[i]);
  for (i = 0; i < dd.frames.length; i++) this.syncFrame(dd.frames[i]);
  for (i = 0; i < dd.cot.length; i++) this.syncCot(dd.cot[i]);
  if (dd.chunks.length) { this.bricks.instanceMatrix.needsUpdate = true; this.bricks.instanceColor.needsUpdate = true; this.tiles.instanceColor.needsUpdate = true; }
  if (dd.frames.length) { this.slabs.instanceMatrix.needsUpdate = true; if (this.slabs.instanceColor) this.slabs.instanceColor.needsUpdate = true; }
  dd.chunks.length = dd.frames.length = dd.cot.length = 0;
  this.syncGauges();
};
R.Scene.prototype.syncAll = function () {
  var m = this.model.meta, i, dd = this.model.dirty, col = new THREE.Color(0x71808f);
  for (i = 0; i < m.frames; i++) this.slabs.setColorAt(i, col);
  for (i = 0; i < m.pool_chunks; i++) this.syncChunk(i);
  for (i = 0; i < m.frames; i++) this.syncFrame(i);
  for (i = 0; i < m.pages; i++) this.syncCot(i);
  this.bricks.instanceMatrix.needsUpdate = true; this.bricks.instanceColor.needsUpdate = true; this.tiles.instanceColor.needsUpdate = true;
  this.tiles.instanceMatrix.needsUpdate = true; this.slabs.instanceMatrix.needsUpdate = true; this.slabs.instanceColor.needsUpdate = true;
  dd.all = false; dd.chunks.length = dd.frames.length = dd.cot.length = 0;
  this.syncGauges();
};
R.Scene.prototype.syncGauges = function () {
  if (!this.towerFill) return;
  var md = this.model, n = md.sram.size, hgt = Math.max(0.05, this.towerH * n / md.meta.sram_cap);
  this.towerFill.scale.y = hgt; this.towerFill.position.y = hgt / 2;
  if (this._tw !== n) { this._tw = n; this.towerText.setText('SRAM ' + n + ' / ' + md.meta.sram_cap); }
  if (this._lc !== md.listCount) { this._lc = md.listCount; this.listText.setText('list chunks in DRAM: ' + md.listCount + '  head ' + (md.listHead >= 0 && md.listHead !== 0xFFFFFF ? R.hex(md.listHead) : 'none')); }
};

/* ---- per-frame */
R.Scene.prototype.update = function (dt, time) {
  var i, e, k, a;
  for (i = this.effects.length - 1; i >= 0; i--) {
    e = this.effects[i]; e.t += dt; k = Math.min(1, e.t / e.d);
    e.o.scale.setScalar(1 + k * e.s); e.o.material.opacity = 1 - k;
    if (k >= 1) { this.scene.remove(e.o); e.o.geometry.dispose(); e.o.material.dispose(); this.effects.splice(i, 1); }
  }
  a = this.kernel; a.walk = Math.max(0, a.walk - dt * 4);
  a.legs[0].position.z = Math.sin(time * 16) * 0.7 * Math.min(1, a.walk); a.legs[1].position.z = -a.legs[0].position.z;
  a.group.position.y = Math.abs(Math.sin(time * 16)) * 0.25 * Math.min(1, a.walk);
  var c = this.cam;
  /* the further the camera, the larger the characters, so they stay findable in Overview.
     What they carry keeps its true size. */
  var s = Math.max(1, Math.min(4.5, c.r / 150)), ls = Math.max(1, Math.min(2.4, c.r / 150));
  for (i = 0; i < this.labels.length; i++) { e = this.labels[i]; e.o.scale.set(e.x * ls, e.y * ls, 1); }
  this.scene.fog.near = Math.max(260, c.r * 0.9); this.scene.fog.far = Math.max(720, c.r * 2.6);
  a.s = s; a.group.scale.setScalar(s); a.hands.scale.setScalar(1 / s);
  a.halo.position.set(a.pos.x, 1.3, a.pos.z); a.halo.scale.setScalar(s);
  a = this.robot; a.s = s; a.lift = a.baseY + (s - 1) * 1.6;
  a.inner.scale.setScalar(s); a.hands.scale.setScalar(1 / s);
  a.inner.position.y = a.lift + Math.sin(time * 3.1) * 0.35;
  a.flame.scale.y = 0.8 + Math.sin(time * 31) * 0.2;
  a.halo.position.set(a.pos.x, 1.3, a.pos.z); a.halo.scale.setScalar(s);
  /* the gate grows with the camera distance too, a little less than the characters */
  var gk = Math.max(1, Math.min(2.4, s * 0.75)), gt = this.gate;
  gt.k = gk; this.gateG.scale.setScalar(gk); gt.tray.y = 2.8 * gk; gt.mid.y = 8 * gk;
  this.lamp.scale.setScalar(this.gateState && this.gateState !== 'idle' ? 1.15 + Math.abs(Math.sin(time * 6)) * 0.2 : 1);
  /* user programs walk to where they are sent; the one being served is larger and cannot stand still */
  for (i = 0; i < this.users.length; i++) {
    a = this.users[i];
    var dx = a.goal.x - a.pos.x, dz = a.goal.z - a.pos.z, dist = Math.hypot(dx, dz), go = Math.min(dist, dt * 24 * Math.max(1, s * 0.6));
    if (dist > 0.05) { a.pos.x += dx / dist * go; a.pos.z += dz / dist * go; a.walk = 1; } else a.walk = Math.max(0, a.walk - dt * 4);
    a.k += (s * (a.active ? 1.2 : 0.95) - a.k) * Math.min(1, dt * 7);
    a.group.scale.setScalar(a.k); a.hands.scale.setScalar(1 / a.k);
    a.pos.y = (Math.abs(Math.sin(time * 14 + i)) * 0.45 * Math.min(1, a.walk) + (a.active ? Math.abs(Math.sin(time * 5.5)) * 0.22 : 0)) * a.k;
    a.halo.position.set(a.pos.x, 1.3, a.pos.z); a.halo.scale.setScalar(a.k * (a.active ? 1.2 : 0.85)); a.halo.material.opacity = a.active ? 0.95 : 0.4;
  }
  if (c.mode === 'follow') { c.target.lerp(this.focus, Math.min(1, dt * 4.2)); c.r += (c.followR - c.r) * Math.min(1, dt * 2); }
  if (c.mode === 'overview') { c.target.lerp(this._ov, Math.min(1, dt * 3)); c.r += (this.fitR() - c.r) * Math.min(1, dt * 3); }
  /* Overview moves the picture down by what fitR found; the other views keep the plain centre */
  var wantDy = c.mode === 'overview' ? this._fitDy || 0 : 0, vo = this.vo;
  if (this._dy === undefined || this._dy === null) this._dy = wantDy;
  this._dy += (wantDy - this._dy) * Math.min(1, dt * 3); if (Math.abs(wantDy - this._dy) < 0.5) this._dy = wantDy;
  if (vo && this.vw && Math.round(this._dy) !== this._dyOn) { this._dyOn = Math.round(this._dy); this.camera.setViewOffset(this.vw, this.vh, vo.x, vo.y - this._dyOn, this.vw, this.vh); }
  var sp = Math.sin(c.ph), cp = Math.cos(c.ph);
  this.camera.position.set(c.target.x + c.r * sp * Math.sin(c.th), c.target.y + c.r * cp, c.target.z + c.r * sp * Math.cos(c.th));
  this.camera.lookAt(c.target);
  this.camera.updateMatrixWorld();
  this.renderer.render(this.scene, this.camera);
  this.layoutBubbles();
};
R.Scene.prototype.resize = function (w, h) {
  this.renderer.setSize(w, h, false); this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  this.cam.followR = w < 700 ? 150 : 105;
  this.vw = w; this.vh = h;
  if (this.bubbles) this.bubbles.forEach(function (b) { b.dirty = true; });
};
R.Scene.prototype.dispose = function () {
  this.renderer.dispose();
};

/* Lesson kit: what every lesson scene is built from.

   A lesson shows one job close up. The kit gives the scene a small 3D stage, the shared
   characters with speech bubbles, "byte slabs" (a structure drawn byte by byte, every byte
   coloured by who wrote it and marked when the other side has read it), and a stepper.
   The scene file supplies the places, the steps and the state after each step. */
(function () {
'use strict';
var T = THREE;
var WHO = { k: '#f4d35e', h: '#b48cff' };
var MONO = '"IBM Plex Mono", ui-monospace, Menlo, monospace';

R.hx = function (v, w) { var s = (v >>> 0).toString(16).toUpperCase(); while (s.length < (w || 0)) s = '0' + s; return '0x' + s; };
R.b2 = function (v) { return (v < 16 ? '0' : '') + v.toString(16).toUpperCase(); };
R.bytes = function (hex) { var o = [], i; for (i = 0; i < hex.length; i += 2) o.push(parseInt(hex.substr(i, 2), 16)); return o; };
R.clone = function (o) { return JSON.parse(JSON.stringify(o)); };
function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

/* ------------------------------------------------------------------ stage */
R.Kit = function (stage) {
  this.stage = stage; this.cv = stage.querySelector('canvas');
  this.bubBox = stage.querySelector('#bubbles'); this.tails = stage.querySelector('#tails');
  this.renderer = new T.WebGLRenderer({ canvas: this.cv, antialias: true });
  this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  this.scene = new T.Scene(); this.scene.background = new T.Color(R.COL.bg);
  this.fov = 36; this.camera = new T.PerspectiveCamera(this.fov, 1, 1, 1200);
  this.scene.add(new T.HemisphereLight(0xffffff, 0x2a3848, 1.0));
  var sun = new T.DirectionalLight(0xffffff, 0.5); sun.position.set(40, 90, 60); this.scene.add(sun);
  var floor = new T.Mesh(new T.PlaneGeometry(600, 600), new T.MeshLambertMaterial({ color: R.COL.floor }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -0.03; this.scene.add(floor);
  this.cam = { t: new T.Vector3(), r: 130, th: 0, ph: 0.8 };
  this.goal = null; this.view = null;
  this.actors = []; this.fx = []; this.slabs = []; this.timers = [];
  this.w = 1; this.h = 1; this.hatch = R.hatchTexture();
  this.reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  this._controls();
};
var K = R.Kit.prototype;

K.resize = function () {
  var w = this.stage.clientWidth, h = this.stage.clientHeight; if (!w || !h) return;
  this.w = w; this.h = h; this.renderer.setSize(w, h, false);
  this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  if (this.goal && this.view) this.goal.r = this._fit(this.view);
  this.actors.forEach(function (a) { a.bub.dirty = true; });
};
/* a view is { t: [x, y, z], w: world width to show, v: apparent height to show, th, ph } */
K._fit = function (f) {
  var tv = Math.tan(this.fov * Math.PI / 360), th = tv * this.w / this.h;
  return Math.max(f.w / (2 * th), f.v / (2 * tv)) * 1.05;
};
K.focus = function (f, instant) {
  this.view = f;
  this.goal = { t: new T.Vector3(f.t[0], f.t[1], f.t[2]), r: this._fit(f), th: f.th || 0, ph: f.ph || 0.8 };
  if (instant || this.reduced) { var c = this.cam, g = this.goal; c.t.copy(g.t); c.r = g.r; c.th = g.th; c.ph = g.ph; }
};
K._controls = function () {
  var self = this, st = this.stage, ptrs = {}, gest = null;
  var count = function () { return Object.keys(ptrs).length; };
  var two = function () { var k = Object.keys(ptrs), a = ptrs[k[0]], b = ptrs[k[1]]; return { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; };
  var pan = function (dx, dy) {
    var c = self.cam, k = c.r * 0.0016, sx = Math.cos(c.th), sz = Math.sin(c.th);
    c.t.x -= (dx * sx + dy * sz) * k; c.t.z -= (-dx * sz + dy * sx) * k;
  };
  st.addEventListener('pointerdown', function (e) {
    if (e.target.closest && e.target.closest('button')) return;
    ptrs[e.pointerId] = { x: e.clientX, y: e.clientY }; try { st.setPointerCapture(e.pointerId); } catch (x) {}
    gest = count() === 2 ? two() : null;
  });
  st.addEventListener('pointermove', function (e) {
    var p = ptrs[e.pointerId]; if (!p) return;
    var dx = e.clientX - p.x, dy = e.clientY - p.y, c = self.cam; p.x = e.clientX; p.y = e.clientY;
    self.goal = null;
    if (count() === 1) {
      if (e.shiftKey || e.buttons === 2) pan(dx, dy);
      else { c.th -= dx * 0.005; c.ph = clamp(c.ph - dy * 0.005, 0.1, 1.45); }
    } else if (count() === 2 && gest) { var g = two(); c.r = clamp(c.r * gest.d / g.d, 14, 420); pan(g.x - gest.x, g.y - gest.y); gest = g; }
  });
  var up = function (e) { delete ptrs[e.pointerId]; gest = null; };
  st.addEventListener('pointerup', up); st.addEventListener('pointercancel', up);
  st.addEventListener('wheel', function (e) { e.preventDefault(); self.goal = null; self.cam.r = clamp(self.cam.r * Math.exp(e.deltaY * 0.0012), 14, 420); }, { passive: false });
  st.addEventListener('contextmenu', function (e) { e.preventDefault(); });
};

/* ---- timers and effects that belong to the step on show; leaving the step cancels them */
K.after = function (ms, fn) { var self = this, id = setTimeout(function () { self.timers.splice(self.timers.indexOf(id), 1); fn(); }, ms); this.timers.push(id); };
K.cancel = function () {
  var i; this.timers.forEach(clearTimeout); this.timers = [];
  for (i = 0; i < this.fx.length; i++) this._drop(this.fx[i]);
  this.fx = [];
};
K._drop = function (e) { this.scene.remove(e.o); e.o.geometry.dispose(); e.o.material.dispose(); };
K.fly = function (from, to, o) {
  o = o || {};
  var s = o.size || [2.4, 0.7, 2.4];
  var m = new T.Mesh(new T.BoxGeometry(s[0], s[1], s[2]), new T.MeshBasicMaterial({ color: o.color || 0xffffff, map: o.hatch ? this.hatch : null }));
  m.position.copy(from); this.scene.add(m);
  this.fx.push({ kind: 'fly', o: m, a: from.clone(), b: to.clone(), t: 0, d: (o.ms || 700) / 1000, up: o.up === undefined ? 5 : o.up, done: o.done });
};
K.ping = function (pos, color, big) {
  var m = new T.Mesh(new T.RingGeometry(1.6, 2.2, 40), new T.MeshBasicMaterial({ color: color, transparent: true, opacity: 1, side: T.DoubleSide, depthTest: false }));
  m.rotation.x = -Math.PI / 2; m.position.copy(pos); m.position.y += 0.4; this.scene.add(m);
  this.fx.push({ kind: 'ping', o: m, t: 0, d: 0.9, s: big || 2.2 });
};

/* ---- things on the stage */
K.box = function (w, h, d, color, x, y, z, basic) {
  var m = new T.Mesh(new T.BoxGeometry(w, h, d), basic ? new T.MeshBasicMaterial({ color: color }) : new T.MeshLambertMaterial({ color: color }));
  m.position.set(x, y, z); this.scene.add(m); return m;
};
K.label = function (text, x, y, z, h, color) {
  var sp = R.makeText(text, { h: h || 1.6, color: color || '#8ea2b6', depthTest: false });
  sp.position.set(x, y, z); sp.renderOrder = 5; this.scene.add(sp); return sp;
};
/* a canvas you draw on, lying flat (text reads from the near side) or standing up */
K.plate = function (o) {
  var cv = document.createElement('canvas'); cv.width = o.pw; cv.height = o.ph;
  var tex = new T.CanvasTexture(cv); tex.anisotropy = 8; tex.minFilter = T.LinearFilter; tex.generateMipmaps = false;
  var d = o.w * o.ph / o.pw, g = new T.Group();
  var face = new T.Mesh(new T.PlaneGeometry(o.w, d), new T.MeshBasicMaterial({ map: tex }));
  if (!o.upright) { face.rotation.x = -Math.PI / 2; face.position.y = 0.26; } else face.position.z = 0.16;
  var base = new T.Mesh(o.upright ? new T.BoxGeometry(o.w + 0.5, d + 0.5, 0.3) : new T.BoxGeometry(o.w + 0.5, 0.5, d + 0.5), new T.MeshLambertMaterial({ color: 0x2a3a4c }));
  g.add(base); g.add(face); g.position.set(o.x, o.y === undefined ? 0.25 : o.y, o.z); if (o.tilt) g.rotation.x = o.tilt;
  this.scene.add(g);
  return { group: g, cv: cv, ctx: cv.getContext('2d'), W: o.pw, H: o.ph, w: o.w, d: d, done: function () { tex.needsUpdate = true; } };
};

/* ---- byte slab. rows: [[{ n: name, off, len }, ...], ...]; state: { b, w, r, vals, hot } */
K.slab = function (o) {
  var self = this, W = 1024, cell = o.cell, M = 30, GAP = 14, TH = 62, NAME = 36, CH = 78, VAL = 38, RG = 10;
  var RH = NAME + CH + VAL + RG, H = TH + o.rows.length * RH + 8;
  var p = this.plate({ w: o.w, pw: W, ph: H, x: o.x, y: o.y, z: o.z, tilt: o.tilt });
  var fields = [], ctx = p.ctx;
  o.rows.forEach(function (row, ri) {
    var x = M; row.forEach(function (f) { fields.push({ n: f.n, off: f.off, len: f.len, x: x, y: TH + ri * RH + NAME, wpx: f.len * cell }); x += f.len * cell + GAP; });
  });
  var s = { b: [], w: [], r: [], vals: {}, hot: [], title: o.title }, last = null, flash = {}, flashing = false;
  function fit(text, max, px, weight) {
    ctx.font = weight + ' ' + px + 'px ' + MONO;
    var w = ctx.measureText(text).width; if (w > max) { px = Math.max(15, Math.floor(px * max / w)); ctx.font = weight + ' ' + px + 'px ' + MONO; }
  }
  function rr(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function draw(now) {
    var live = false;
    ctx.fillStyle = '#0f1822'; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#3a5068'; ctx.lineWidth = 6; ctx.strokeRect(3, 3, W - 6, H - 6);
    ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
    fit(s.title || '', W - 2 * M, 30, 600); ctx.fillStyle = '#9fb4cc'; ctx.fillText(s.title || '', M, 44);
    fields.forEach(function (f) {
      var hot = s.hot.indexOf(f.n) >= 0, i, idx, bx, wr, v, rd, k, a;
      fit(f.n, f.wpx + GAP - 6, 26, 600); ctx.fillStyle = hot ? '#ffffff' : '#8ea2b6'; ctx.fillText(f.n, f.x + 3, f.y - 10);
      for (i = 0; i < f.len; i++) {
        idx = f.off + i; bx = f.x + i * cell; wr = s.w[idx]; v = s.b[idx]; rd = s.r[idx] || '';
        rr(bx + 2, f.y, cell - 4, CH, 7); ctx.fillStyle = wr ? WHO[wr] : '#18222d'; ctx.fill();
        if (!wr) { ctx.strokeStyle = '#2a3a4c'; ctx.lineWidth = 2; ctx.stroke(); }
        ctx.font = '600 ' + Math.round(cell * 0.44) + 'px ' + MONO; ctx.textAlign = 'center';
        ctx.fillStyle = wr ? '#10161d' : '#5d6f82'; ctx.fillText(v === null || v === undefined ? '--' : R.b2(v), bx + cell / 2, f.y + CH / 2 + cell * 0.16);
        ctx.textAlign = 'left';
        for (k = 0; k < rd.length; k++) {
          ctx.beginPath(); ctx.moveTo(bx + cell - 2, f.y); ctx.lineTo(bx + cell - 2, f.y + 24); ctx.lineTo(bx + cell - 26, f.y); ctx.closePath();
          ctx.fillStyle = WHO[rd[k]]; ctx.fill(); ctx.strokeStyle = '#10161d'; ctx.lineWidth = 2; ctx.stroke();
        }
        if (flash[idx] !== undefined) {
          a = 1 - (now - flash[idx]) / 1100;
          if (a > 0) { live = true; rr(bx + 2, f.y, cell - 4, CH, 7); ctx.fillStyle = 'rgba(255,255,255,' + (a * 0.85).toFixed(3) + ')'; ctx.fill(); } else delete flash[idx];
        }
      }
      if (hot) { ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 5; rr(f.x - 2, f.y - 4, f.wpx + 4, CH + 8, 9); ctx.stroke(); }
      v = s.vals[f.n];
      if (v) { fit(v, f.wpx + GAP - 6, 27, 500); ctx.fillStyle = hot ? '#ffffff' : '#dfe8f1'; ctx.fillText(v, f.x + 3, f.y + CH + 29); }
    });
    flashing = live; p.done();
  }
  var slab = {
    group: p.group, w: p.w, d: p.d,
    set: function (ns, doFlash) {
      var i, now = performance.now();
      if (last && doFlash && !self.reduced) for (i = 0; i < ns.b.length; i++) if (last.b[i] !== ns.b[i] || last.w[i] !== ns.w[i] || (last.r[i] || '') !== (ns.r[i] || '')) flash[i] = now;
      if (!doFlash) flash = {};
      s = { b: ns.b, w: ns.w, r: ns.r, vals: ns.vals || {}, hot: ns.hot || [], title: ns.title || o.title };
      last = { b: ns.b.slice(), w: ns.w.slice(), r: ns.r.slice() };
      draw(now);
    },
    tick: function (now) { if (flashing) draw(now); },
    /* where a field is in the world, for pointing at it */
    at: function (name) {
      var f = null, i; for (i = 0; i < fields.length; i++) if (fields[i].n === name) f = fields[i];
      var cx = f ? f.x + f.wpx / 2 : W / 2, cy = f ? f.y + CH / 2 : H / 2;
      p.group.updateMatrixWorld();
      return p.group.localToWorld(new T.Vector3((cx / W - 0.5) * p.w, 0.5, (cy / H - 0.5) * p.d));
    }
  };
  this.slabs.push(slab);
  return slab;
};

/* ---- characters */
K.addActor = function (a, o) {
  var self = this;
  a.kind = o.kind; a.name = o.name; a.css = o.css; a.sc = o.scale || 1.4; a.goal = a.pos.clone(); a.chip = o.chip !== false; a.fixed = !!o.fixed;
  a.s = a.sc; a.k = a.sc;
  if (a.group) { a.group.scale.setScalar(a.sc); this.scene.add(a.group); }
  if (!a.fixed) {
    a.halo = new T.Mesh(new T.RingGeometry(2.3, 3.0, 36), new T.MeshBasicMaterial({ color: new T.Color(o.css), transparent: true, opacity: 0.85, side: T.DoubleSide }));
    a.halo.rotation.x = -Math.PI / 2; a.halo.scale.setScalar(a.sc); this.scene.add(a.halo);
  }
  var el = document.createElement('div'), NS = 'http://www.w3.org/2000/svg', tail = document.createElementNS(NS, 'path');
  el.className = 'bub quiet'; el.style.setProperty('--c', o.css);
  el.innerHTML = '<b class="bname"></b><span class="btext"></span>'; el.firstChild.textContent = o.name;
  tail.setAttribute('stroke', o.css); tail.setAttribute('d', 'M0 0');
  this.bubBox.appendChild(el); this.tails.appendChild(tail);
  a.bub = { el: el, tail: tail, text: el.lastChild, t: '', dirty: true, w: 0, h: 0, x: null, y: null, pick: 0 };
  a.say = function (t) { t = t || ''; if (t === a.bub.t) return; a.bub.t = t; a.bub.text.textContent = t; el.className = 'bub' + (t ? '' : ' quiet'); a.bub.dirty = true; a.bub.x = null; };
  a.go = function (x, z, snap) { a.goal.set(x, 0, z); if (snap || self.reduced) { a.pos.x = x; a.pos.z = z; } };
  this.actors.push(a);
  return a;
};
K._project = function (x, y, z) {
  var v = new T.Vector3(x, y, z).project(this.camera);
  return { x: (v.x * 0.5 + 0.5) * this.w, y: (-v.y * 0.5 + 0.5) * this.h, ok: v.z < 1 };
};
/* bubbles: DOM boxes over the canvas. A bubble sits near its speaker's head and may not cover
   a character or another bubble if any of five places avoids it. */
K._bubbles = function (dt) {
  var self = this, W = this.w, H = this.h, placed = [], bodies = [], order;
  this.actors.forEach(function (a) {
    var top = a.pos.y + a.top(), hd = self._project(a.pos.x, top, a.pos.z), ft = self._project(a.pos.x, a.pos.y, a.pos.z);
    a._hd = hd; a._ft = ft;
    if (!a.fixed) { var hw = Math.max(14, (ft.y - hd.y) * 0.3); bodies.push({ a: a, x0: hd.x - hw, x1: hd.x + hw, y0: hd.y, y1: ft.y }); }
  });
  /* keep: what the current step is about, as groups of world points; a bubble stays off their screen box */
  var keeps = (this.keep || []).map(function (pts) {
    var r = { x0: 1e9, x1: -1e9, y0: 1e9, y1: -1e9 };
    pts.forEach(function (q) { var s = self._project(q[0], q[1], q[2]); r.x0 = Math.min(r.x0, s.x); r.x1 = Math.max(r.x1, s.x); r.y0 = Math.min(r.y0, s.y); r.y1 = Math.max(r.y1, s.y); });
    return r;
  });
  order = this.actors.slice().sort(function (a, b) { return (b.bub.t ? 1 : 0) - (a.bub.t ? 1 : 0); });
  function over(x, y, w, h, r) { var ox = Math.min(x + w, r.x1) - Math.max(x, r.x0), oy = Math.min(y + h, r.y1) - Math.max(y, r.y0); return ox > 0 && oy > 0 ? ox * oy : 0; }
  order.forEach(function (a) {
    var b = a.bub, hd = a._hd, show = hd.ok && hd.x > -40 && hd.x < W + 40 && hd.y > -40 && hd.y < H + 60 && (b.t || a.chip);
    if (!show) { b.el.style.visibility = 'hidden'; b.tail.setAttribute('d', 'M0 0'); return; }
    if (b.dirty) { b.w = b.el.offsetWidth; b.h = b.el.offsetHeight; b.dirty = false; }
    var w = b.w, h = b.h, c, best = null, i, x, y, cost, k;
    if (!b.t) {   /* a name chip: above the head, moved up past chips and bubbles already there */
      x = clamp(hd.x - w / 2, 4, W - w - 4); b.tail.setAttribute('d', 'M0 0');
      for (i = 0; i < 4; i++) {
        y = clamp(hd.y - h - 6 - i * (h + 3), 4, H - h - 4); cost = i;
        for (k = 0; k < placed.length; k++) cost += over(x, y, w, h, placed[k]);
        if (!best || cost < best.cost) best = { cost: cost, y: y };
      }
      y = best.y; placed.push({ x0: x, x1: x + w, y0: y, y1: y + h });
    } else {
      var fy = a._ft.y;
      c = [[hd.x - w / 2, hd.y - h - 18], [hd.x + 16, hd.y - h - 8], [hd.x - w - 16, hd.y - h - 8], [hd.x + 34, hd.y - h * 0.3], [hd.x - w - 34, hd.y - h * 0.3],
           [hd.x - w / 2, hd.y - h - 90], [hd.x + 70, hd.y - h - 50], [hd.x - w - 70, hd.y - h - 50], [hd.x - w / 2, fy + 18]];
      for (i = 0; i < c.length; i++) {
        x = clamp(c[i][0], 6, W - w - 6); y = clamp(c[i][1], 6, H - h - 6);
        cost = Math.abs(x - c[i][0]) * 30 + Math.abs(y - c[i][1]) * 30 + i * 60 - (i === b.pick ? 900 : 0);
        for (k = 0; k < placed.length; k++) cost += over(x, y, w, h, placed[k]) * 4;
        for (k = 0; k < bodies.length; k++) cost += over(x, y, w, h, bodies[k]) * (bodies[k].a.bub.t || bodies[k].a === a ? 3 : 1);
        for (k = 0; k < keeps.length; k++) cost += over(x, y, w, h, keeps[k]) * 2.5;
        if (!best || cost < best.cost) best = { cost: cost, x: x, y: y, i: i };
      }
      b.pick = best.i; x = best.x; y = best.y;
      placed.push({ x0: x, x1: x + w, y0: y, y1: y + h });
    }
    if (b.x === null || self.reduced) { b.x = x; b.y = y; } else { var q = Math.min(1, dt * 10); b.x += (x - b.x) * q; b.y += (y - b.y) * q; }
    b.el.style.transform = 'translate(' + Math.round(b.x) + 'px,' + Math.round(b.y) + 'px)'; b.el.style.visibility = 'visible';
    b.el.style.zIndex = b.t ? 2 : 1;
    if (b.t) {
      var qx = clamp(hd.x, b.x + 14, b.x + w - 14), qy = clamp(hd.y - 4, b.y + 10, b.y + h - 10), horiz = !(hd.y - 4 > b.y + h || hd.y - 4 < b.y);
      var dist = Math.hypot(hd.x - qx, hd.y - 4 - qy);
      if (dist < 8) b.tail.setAttribute('d', 'M0 0');
      else if (horiz) b.tail.setAttribute('d', 'M' + qx + ' ' + (qy - 8) + 'L' + hd.x + ' ' + (hd.y - 4) + 'L' + qx + ' ' + (qy + 8) + 'Z');
      else b.tail.setAttribute('d', 'M' + (qx - 9) + ' ' + qy + 'L' + hd.x + ' ' + (hd.y - 4) + 'L' + (qx + 9) + ' ' + qy + 'Z');
    }
  });
};

K.update = function (dt, time) {
  var i, e, k, a, c = this.cam, g = this.goal, now = performance.now();
  if (g) { k = 1 - Math.exp(-dt * 3.0); c.t.lerp(g.t, k); c.r += (g.r - c.r) * k; c.th += (g.th - c.th) * k; c.ph += (g.ph - c.ph) * k; }
  for (i = 0; i < this.actors.length; i++) {
    a = this.actors[i]; if (a.fixed) continue;
    var dx = a.goal.x - a.pos.x, dz = a.goal.z - a.pos.z, dist = Math.hypot(dx, dz), go = Math.min(dist, dt * 24);
    if (dist > 0.05) { a.pos.x += dx / dist * go; a.pos.z += dz / dist * go; a.walk = 1; } else a.walk = Math.max(0, a.walk - dt * 4);
    if (a.kind === 'hw') {
      a.inner.position.y = 2.4 + Math.sin(time * 3.1) * 0.3; a.lift = a.inner.position.y * a.sc; a.flame.scale.y = 0.8 + Math.sin(time * 31) * 0.2;
    } else if (a.kind === 'kernel') {
      a.legs[0].position.z = Math.sin(time * 16) * 0.7 * Math.min(1, a.walk); a.legs[1].position.z = -a.legs[0].position.z;
      a.pos.y = Math.abs(Math.sin(time * 16)) * 0.3 * Math.min(1, a.walk);
    } else a.pos.y = Math.abs(Math.sin(time * 14 + i)) * 0.5 * Math.min(1, a.walk) + (a.bub.t ? Math.abs(Math.sin(time * 5.5)) * 0.3 : 0);
    a.halo.position.set(a.pos.x, 0.12, a.pos.z);
    a.halo.material.opacity = a.bub.t ? 0.95 : 0.4;
  }
  for (i = this.fx.length - 1; i >= 0; i--) {
    e = this.fx[i]; e.t += dt; k = Math.min(1, e.t / e.d);
    if (e.kind === 'fly') { var q = k * k * (3 - 2 * k); e.o.position.lerpVectors(e.a, e.b, q); e.o.position.y += Math.sin(q * Math.PI) * e.up; }
    else { e.o.scale.setScalar(1 + k * e.s); e.o.material.opacity = 1 - k; }
    if (k >= 1) { this._drop(e); this.fx.splice(i, 1); if (e.done) e.done(); }
  }
  for (i = 0; i < this.slabs.length; i++) this.slabs[i].tick(now);
  var sp = Math.sin(c.ph), cp = Math.cos(c.ph);
  this.camera.position.set(c.t.x + c.r * sp * Math.sin(c.th), c.t.y + c.r * cp, c.t.z + c.r * sp * Math.cos(c.th));
  this.camera.lookAt(c.t); this.camera.updateMatrixWorld();
  this.renderer.render(this.scene, this.camera);
  this._bubbles(dt);
};

/* ------------------------------------------------------------------ stepper
   o: { kit, steps, init, pose(S, snap), show(S, flash), card(S, step), ledger: [[id, label]], who: { key: [label, css] } }
   A step: { who, title, text, cam, apply(S), fx(done), delay }. The state after step i is
   init with apply of steps 0..i; going to a step shows the state before it, lets the
   characters move, then shows the state after it. */
R.Lesson = function (o) {
  var kit = o.kit, steps = o.steps, n = steps.length, states = [], S = R.clone(o.init), i;
  for (i = 0; i < n; i++) { S = R.clone(S); S.say = {}; steps[i].apply(S); states.push(S); }
  var $ = function (id) { return document.getElementById(id); };
  var cur = -1, playing = false, seen = [], autoT = null, dots = $('dots'), self = this;
  steps.forEach(function (st, k) {
    var b = document.createElement('button'); b.type = 'button'; b.style.setProperty('--c', o.who[st.who][1]);
    b.setAttribute('aria-label', 'Step ' + (k + 1) + ': ' + st.title); b.title = (k + 1) + '. ' + st.title;
    b.addEventListener('click', function () { setPlaying(false); go(k); }); dots.appendChild(b);
  });
  function ledger(Sn, Sp) {
    var h = '<tr><th>structure</th><th class="c">KERNEL SW</th><th class="c">LZ4 HW</th></tr>';
    o.ledger.forEach(function (r) {
      var a = Sn.led[r[0]] || {}, p = (Sp && Sp.led[r[0]]) || {}, fresh = (a.k || '') !== (p.k || '') || (a.h || '') !== (p.h || '');
      var cell = function (v, w) { return '<td class="c">' + (v ? '<span class="wr ' + w + '">' + v + '</span>' : '<span class="wr n">' + (Sn.final ? 'never' : '·') + '</span>') + '</td>'; };
      h += '<tr' + (fresh && Sp ? ' class="new"' : '') + '><td>' + r[1] + '</td>' + cell(a.k, 'k') + cell(a.h, 'h') + '</tr>';
    });
    $('ledger').innerHTML = h;
  }
  function panel(k) {
    var st = steps[k], Sn = states[k], Sp = k ? states[k - 1] : null, w = o.who[st.who];
    $('stepNo').textContent = 'STEP ' + (k + 1) + ' / ' + n;
    $('who').textContent = w[0]; $('who').style.setProperty('--c', w[1]);
    $('stepTitle').textContent = st.title; $('text').innerHTML = st.text;
    $('focus').innerHTML = o.card(Sn, st, Sp) || '';
    ledger(Sn, Sp); $('clock').innerHTML = o.clock(Sn);
    $('pos').textContent = (k + 1) + ' / ' + n;
    $('prev').disabled = k === 0; $('next').disabled = k === n - 1;
    Array.prototype.forEach.call(dots.children, function (b, j) { b.className = (j === k ? 'on ' : '') + (seen[j] ? 'seen' : ''); if (j === k) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current'); });
    $('panel').scrollTop = 0;
  }
  function go(k, instant) {
    k = clamp(k, 0, n - 1); kit.cancel(); clearTimeout(autoT);
    var st = steps[k], Sn = states[k], Sp = k ? states[k - 1] : o.init, quick = instant || kit.reduced;
    cur = k; seen[k] = true;
    kit.keep = st.keep || [];
    o.show(Sp, false); o.pose(Sp, true);
    panel(k); kit.focus(st.cam, quick);
    o.pose(Sn, quick);
    var done = function () { o.show(Sn, !quick); };
    if (quick) done(); else if (st.fx) st.fx(done); else kit.after(st.delay === undefined ? 900 : st.delay, done);
    if (playing) arm();
  }
  function arm() {
    clearTimeout(autoT); if (cur >= n - 1) { setPlaying(false); return; }
    var len = steps[cur].text.replace(/<[^>]+>/g, '').length;
    autoT = setTimeout(function () { go(cur + 1); }, clamp(3200 + len * 95, 5000, 22000));
  }
  function setPlaying(p) {
    playing = p; $('play').innerHTML = p ? '&#10074;&#10074; Pause' : '&#9654; Play'; $('play').setAttribute('aria-pressed', p ? 'true' : 'false');
    if (p) { if (cur >= n - 1) go(0); else arm(); } else clearTimeout(autoT);
  }
  $('prev').addEventListener('click', function () { setPlaying(false); go(cur - 1); });
  $('next').addEventListener('click', function () { setPlaying(false); go(cur + 1); });
  $('play').addEventListener('click', function () { setPlaying(!playing); });
  $('camReset').addEventListener('click', function () { kit.focus(steps[cur].cam); });
  document.addEventListener('keydown', function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'ArrowRight') { setPlaying(false); go(cur + 1); e.preventDefault(); }
    else if (e.key === 'ArrowLeft') { setPlaying(false); go(cur - 1); e.preventDefault(); }
    else if (e.key === ' ' && !(e.target && e.target.tagName === 'BUTTON')) { setPlaying(!playing); e.preventDefault(); }
  });
  var resize = function () { kit.resize(); };
  if (window.ResizeObserver) new ResizeObserver(resize).observe(kit.stage); else window.addEventListener('resize', resize);
  kit.resize(); go(0, true);
  var lastT = performance.now();
  (function frame(t) { var dt = Math.min(0.05, (t - lastT) / 1000); lastT = t; kit.update(dt * 0.7, t / 1000); requestAnimationFrame(frame); })(lastT);
  this.go = go; this.states = states; this.at = function () { return cur; }; this.setPlaying = setPlaying;
};
})();

/* The part of the stage that every lesson scene has, whichever design it shows: the access gate,
   the PTE and the user programs at the far end; the two ring slots (job descriptor, completion)
   with DOORBELL, IRQ, KERNEL SW and LZ4 HW; the frame, the LZ4 engine, the stream and the chunk
   tiles; the COT entry nearest to the viewer. It also draws the panel cards.

   What differs between the designs is added by the stage file of the design: stage_hw.js puts
   the free-chunk stack of LZ4 HW on it, stage_sw.js the free-chunk bitmap of KERNEL SW. A stage
   file calls R.stage(o) with its formats and, where its structures need other room, places.
   Every number comes from lesson-data, which the exporter took from one real simulator job. */
(function () {
'use strict';
var T = THREE, hx = R.hx;
var MONO = '"IBM Plex Mono", ui-monospace, Menlo, monospace';
var D = JSON.parse(document.getElementById('lesson-data').textContent), V = D.victim || D.pg;
R.LD = { D: D, M: D.meta, V: V, H: hx(V.h) };

/* o: { F: { desc } and, to replace the common ones, cot and done; each { title, cell, rows: [[[name, off, len], ...], ...] },
        tiles: chunks drawn as tiles (default D.chunks), tileW, zcot,
        desc / done / cot: { x, w, y, tilt } of the slabs, bellX, irqX,
        P, VIEW: places and views added to or replacing the defaults (functions of the layout),
        chunkTaken: [line 1, line 2, colour] of a chunk tile in state 1, freeText: text of state 0 } */
R.stage = function (o) {
  var M = D.meta, H = R.LD.H;
  /* the COT entry and the completion have one format in both designs; the descriptor does not */
  var F = {
    desc: o.F.desc,
    cot: o.F.cot || { title: 'COT[' + H + '] @' + hx(V.entry_pa) + ' · 32 B · the entry of page ' + H, cell: 74,
           rows: [[['flags', 0, 1], ['count', 1, 1], ['comp_len', 2, 2], ['checksum', 4, 4]],
                  [0, 1, 2, 3].map(function (i) { return ['chunk[' + i + ']', 8 + 3 * i, 3]; }),
                  [4, 5, 6, 7].map(function (i) { return ['chunk[' + i + ']', 8 + 3 * i, 3]; })] },
    done: o.F.done || { title: 'COMPLETION · 16 B · one slot of the completion ring', cell: 104,
            rows: [[['status', 0, 1], ['flags', 1, 1], ['length', 2, 2], ['checksum', 4, 4]], [['tag', 8, 4], ['aux', 12, 4]]] }
  };
  var kit = new R.Kit(document.getElementById('stage'));
  var TILES = o.tiles || D.chunks, NT = TILES.length, NCH = D.chunks.length, TW = o.tileW || 7.6;
  var dsc = o.desc || { x: -16, w: 26, y: 3.5, tilt: 0.7 }, dne = o.done || { x: 16, w: 26, y: 3.5, tilt: 0.7 }, ct = o.cot || { x: 0, w: 34 };
  var BX = o.bellX === undefined ? -4 : o.bellX, IX = o.irqX === undefined ? 4 : o.irqX;
  var TAKEN = o.chunkTaken || ['taken by LZ4 HW', '', '#b48cff'];

  /* ---- formats */
  Object.keys(F).forEach(function (k) {
    var f = F[k]; f.fields = []; f.n = 0;
    f.rows.forEach(function (r) { r.forEach(function (x) { f.fields.push(x); f.n = Math.max(f.n, x[1] + x[2]); }); });
  });
  function slabOf(k, s) {
    s.title = F[k].title; s.cell = F[k].cell;
    s.rows = F[k].rows.map(function (r) { return r.map(function (x) { return { n: x[0], off: x[1], len: x[2] }; }); });
    return kit.slab(s);
  }

  /* ---- places */
  var CX = [], x0 = 5;
  TILES.forEach(function (c, i) { if (i) x0 += TW + 1 + (c.n === TILES[i - 1].n + 1 ? 0 : 2.6); CX.push(x0); });
  var ZROW = 7, ZDESK = -15, ZGATE = -36, ZCOT = o.zcot || 30, XS = CX[NT - 1] + 9.5;
  var P = {
    k_home: [-35, -11], k_call: [-17, -33], k_gate: [28.5, -31], k_frame: [-27, -3.5], k_desc: [-33, ZDESK], k_bell: [-9, -22], k_done: [-1.5, ZDESK],
    h_home: [XS - 8, -12.5], h_desc: [1.5, ZDESK], h_frame: [-27, -3.5], h_engine: [-9, -2.5], h_cot: [ct.x, ZCOT - 15], h_done: [33, ZDESK],
    ui_home: [-11, -45], ui_gate: [-4.5, -40.5], log: [16, -45.5], media: [-25, -47], net: [36, -47]
  };
  TILES.forEach(function (c, i) { P['h_ch' + i] = [CX[i], ZROW - 7.5]; });
  var VIEW = {
    all: { t: [4, 0, -3], w: 94, v: 86, ph: 0.72 },
    far: { t: [3, 3, -33], w: 62, v: 36, ph: 0.98 },
    pte: { t: [14, 4, -36], w: 42, v: 26, ph: 1.0 },
    frame: { t: [-18, 1, -6], w: 50, v: 42, ph: 0.8 },
    desc: { t: [-18.5, 3, ZDESK - 1], w: 37, v: 27, ph: 0.74 },
    desk: { t: [0, 3, ZDESK - 2], w: 78, v: 36, ph: 0.8 },
    read: { t: [-13, 3, ZDESK - 1], w: 40, v: 27, ph: 0.74 },
    kread: { t: [13, 3, ZDESK - 1], w: 40, v: 27, ph: 0.74 },
    engine: { t: [-13, 1, 4], w: 50, v: 32, ph: 0.7 },
    work: { t: [2, 0, 4], w: 80, v: 40, ph: 0.68 },
    chunks: { t: [(CX[0] + XS) / 2, 1, 1], w: XS - CX[0] + 18, v: 40, ph: 0.72 },
    gather: { t: [(CX[NCH - 1] - 16) / 2, 1, ZROW], w: CX[NCH - 1] + 16 + 14, v: 36, ph: 0.72 },
    cot: { t: [ct.x, 1, ZCOT - 3.5], w: 40, v: 37, ph: 0.5 },
    done: { t: [17.5, 3, ZDESK - 1], w: 40, v: 27, ph: 0.74 }
  };
  var lay = { CX: CX, XS: XS, ZROW: ZROW, ZDESK: ZDESK, ZGATE: ZGATE, ZCOT: ZCOT }, k, more;
  more = o.P ? o.P(lay) : {}; for (k in more) P[k] = more[k];
  more = o.VIEW ? o.VIEW(lay) : {}; for (k in more) VIEW[k] = more[k];

  /* ---- far end: the gate, the PTE, the user programs */
  var GM = new T.MeshLambertMaterial({ color: 0x9fb4cc, emissive: 0x1c2733 }), G = new T.Group(), part;
  G.position.set(0, 0, ZGATE); kit.scene.add(G);
  part = new T.Mesh(new T.BoxGeometry(13, 1.2, 2.4), new T.MeshLambertMaterial({ color: 0x4a6078 })); part.position.y = 0.6; G.add(part);
  [-6.4, 6.4].forEach(function (x) { var p = new T.Mesh(new T.BoxGeometry(1, 9, 1), GM); p.position.set(x, 4.5, 0); G.add(p); });
  part = new T.Mesh(new T.BoxGeometry(13.8, 1.2, 1.2), GM); part.position.y = 9.4; G.add(part);
  var pane = new T.Mesh(new T.PlaneGeometry(11.8, 7.6), new T.MeshBasicMaterial({ color: R.GATE.idle, transparent: true, opacity: 0.22, side: T.DoubleSide, depthWrite: false }));
  pane.position.y = 5; G.add(pane);
  var lamp = new T.Mesh(new T.SphereGeometry(1.2, 18, 12), new T.MeshBasicMaterial({ color: R.GATE.idle })); lamp.position.y = 11.1; G.add(lamp);
  kit.label('ACCESS GATE', 0, 0.7, ZGATE + 3.2, 1.3);
  var A = {};
  A.gate = kit.addActor({ pos: new T.Vector3(0, 0, ZGATE), top: function () { return 12.6; } }, { kind: 'gate', name: 'MMU · PAGE TABLE', css: '#9fb4cc', fixed: true });
  var pte = kit.plate({ w: 17, pw: 624, ph: 250, x: 16, y: 4.2, z: ZGATE + 0.5, upright: true, tilt: -0.12 });

  var names = M.clients, uKeys = {};
  (function () {
    var free = ['media', 'net', 'ui_home', 'log'], used = {}, i;
    used[D.req.client] = 'ui_home'; if (V.client !== D.req.client) used[V.client] = 'log';
    for (i = 0; i < names.length; i++) {
      var place = used[i] || free.filter(function (p) { return Object.keys(used).every(function (k) { return used[k] !== p; }); })[0];
      used[i] = place;
      var key = i === D.req.client ? 'req' : i === V.client ? 'own' : 'u' + i;
      var a = R.chars.user(i, names[i]); a.pos.set(P[place][0], 0, P[place][1]);
      A[key] = kit.addActor(a, { kind: 'user', name: 'USER SW · ' + names[i], css: a.css, scale: 1.15 });
      uKeys[key] = place;
    }
  })();

  /* ---- middle: the two ring slots, doorbell and IRQ, the two characters */
  var S_desc = slabOf('desc', { w: dsc.w, x: dsc.x, y: dsc.y, z: ZDESK, tilt: dsc.tilt });
  var S_done = slabOf('done', { w: dne.w, x: dne.x, y: dne.y, z: ZDESK, tilt: dne.tilt });
  function post(x, text) {
    kit.box(0.9, 5, 0.9, 0x51657c, x, 2.5, -25);
    var m = new T.Mesh(new T.SphereGeometry(1.25, 18, 12), new T.MeshBasicMaterial({ color: 0x33404e })); m.position.set(x, 6, -25); kit.scene.add(m);
    kit.label(text, x, 8.3, -25, 1.25, '#c5d2df');
    return m;
  }
  var bell = post(BX, 'DOORBELL'), irq = post(IX, 'IRQ');
  A.kernel = kit.addActor(R.chars.kernel(), { kind: 'kernel', name: 'KERNEL SW', css: '#f4d35e' });
  A.hw = kit.addActor(R.chars.robot(), { kind: 'hw', name: 'LZ4 HW', css: '#b48cff' });

  /* ---- near: frame, engine, stream, chunks */
  var frameP = kit.plate({ w: 12, pw: 512, ph: 560, x: -27, z: ZROW });
  kit.label('frame ' + V.frame + '  @' + hx(V.frame_pa), -27, 0.7, ZROW + 8.1, 1.25);
  var freeLab = kit.label('', -27, 0.7, ZROW + 10.4, 1.25, '#f4d35e');
  kit.box(9, 3, 7, 0x4a3c7a, -9, 1.5, ZROW - 1);
  var engLamp = kit.box(7.4, 0.5, 1.2, 0x2a2244, -9, 3.2, ZROW + 1.4, true);
  kit.label('LZ4 ENGINE', -9, 4.6, ZROW - 1, 1.3, '#d9c8ff');
  var SEG = 3.3, segs = [], sx = -15.6;
  D.stream.sizes.forEach(function (b) {
    var w = SEG * b / M.chunk, m = new T.Mesh(new T.BoxGeometry(w - 0.14, 0.8, 2.4), new T.MeshBasicMaterial({ map: kit.hatch }));
    m.position.set(sx + w / 2, 0.5, ZROW + 6.3); kit.scene.add(m); segs.push(m); sx += w;
  });
  var streamLab = kit.label('', -9, 0.7, ZROW + 8.7, 1.25, '#dfe8f1');
  var tiles = TILES.map(function (c, i) { return kit.plate({ w: TW, pw: 300, ph: 300, x: CX[i], z: ZROW }); });
  kit.label('CHUNK POOL  ' + M.chunk + ' B per chunk', (CX[0] + CX[NT - 1]) / 2, 0.7, ZROW + TW / 2 + 1.8, 1.25);

  /* ---- nearest: the COT entry */
  var S_cot = slabOf('cot', { w: ct.w, x: ct.x, z: ZCOT });

  /* ---- drawing the plates */
  function txt(p, s, x, y, px, color, weight, align) { p.ctx.font = (weight || 600) + ' ' + px + 'px ' + MONO; p.ctx.fillStyle = color; p.ctx.textAlign = align || 'left'; p.ctx.fillText(s, x, y); }
  function hatchFill(c, x, y, w, h) {
    c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); c.fillStyle = '#f2f5f8'; c.fillRect(x, y, w, h);
    c.strokeStyle = '#5b6672'; c.lineWidth = 5; var i; for (i = -h; i < w + h; i += 13) { c.beginPath(); c.moveTo(x + i, y + h); c.lineTo(x + i + h, y); c.stroke(); }
    c.restore();
  }
  function drawPte(S) {
    var p = pte, c = p.ctx, ok = S.pte.valid;
    c.fillStyle = '#0f1822'; c.fillRect(0, 0, p.W, p.H);
    c.strokeStyle = S.pte.hot ? '#ffffff' : '#3a5068'; c.lineWidth = 6; c.strokeRect(3, 3, p.W - 6, p.H - 6);
    txt(p, 'PTE of page ' + H + '  (' + V.name + ')', 22, 44, 28, '#9fb4cc');
    c.fillStyle = S.pte.w ? '#f4d35e' : '#18222d'; c.fillRect(22, 62, 250, 76);
    txt(p, 'valid = ' + ok, 36, 116, 44, S.pte.w ? '#10161d' : '#dfe8f1', 700);
    txt(p, ok ? 'access goes on' : 'access stops here,', 290, 96, 25, ok ? '#7ee2a8' : '#ff8a8a');
    txt(p, ok ? 'to frame ' + V.frame : 'KERNEL SW is called', 290, 130, 25, ok ? '#7ee2a8' : '#ff8a8a');
    txt(p, "kernel's note: page is", 22, 190, 25, '#8ea2b6', 500);
    txt(p, S.pte.st, 22, 228, 30, '#f4d35e', 700);
    p.done();
  }
  function drawFrame(S) {
    /* st: 'free', 'taken' (the kernel set it aside for the page, nothing written yet) or 'present' */
    var p = frameP, c = p.ctx, st = S.frame.st, i, j, free = st === 'free', taken = st === 'taken', busy = S.frame.hot === 'read' || S.frame.hot === 'write';
    c.fillStyle = '#0f1822'; c.fillRect(0, 0, p.W, p.H);
    c.strokeStyle = S.frame.hot ? '#ffffff' : taken ? '#f4d35e' : '#3a5068'; c.lineWidth = 8; c.strokeRect(4, 4, p.W - 8, p.H - 8);
    txt(p, free ? 'FREE FRAME' : taken ? 'taken for page ' + H : 'page ' + H + ' of ' + V.name, 24, 52, 34, free ? '#7ee2a8' : taken ? '#f4d35e' : '#dfe8f1');
    txt(p, free ? 'ready for the next page' : taken ? 'nothing written yet' : M.page + ' B, not compressed', 24, 92, 26, '#8ea2b6', 500);
    for (i = 0; i < 8; i++) for (j = 0; j < 8; j++) {
      c.fillStyle = free || taken ? '#18222d' : (busy ? '#7db2ff' : '#3d8bff'); c.fillRect(24 + j * 58.5, 116 + i * 53, 53, 47);
    }
    p.done();
  }
  function drawChunk(i, S) {
    /* st: 0 free, 1 taken for this job (by whoever hands out chunks in this design), 2 holds stream bytes,
       3 holds stream bytes that LZ4 HW has read back, 4 given back during this lesson */
    var p = tiles[i], c = p.ctx, st = S.ch[i], ch = TILES[i], bw = 256 * ch.bytes / M.chunk, full = st === 2 || st === 3;
    c.fillStyle = '#0f1822'; c.fillRect(0, 0, p.W, p.H);
    c.strokeStyle = st === 1 ? TAKEN[2] : S.chHot === i ? '#ffffff' : '#3a5068'; c.lineWidth = 8; c.strokeRect(4, 4, p.W - 8, p.H - 8);
    txt(p, 'chunk ' + hx(ch.n), 22, 54, 38, st && st !== 4 ? '#ffffff' : '#8ea2b6');
    txt(p, '@' + hx(ch.pa), 22, 92, 27, '#8ea2b6', 500);
    c.fillStyle = '#18222d'; c.fillRect(22, 116, 256, 80);
    if (full) hatchFill(c, 22, 116, bw, 80);
    txt(p, st === 0 ? (o.freeText || 'free') : st === 4 ? 'free again' : st === 1 ? TAKEN[0] : st === 3 ? ch.bytes + ' B read by HW' : ch.bytes + ' B stored', 22, 236, 27,
        st === 1 ? TAKEN[2] : st === 3 ? '#b48cff' : st === 2 ? '#dfe8f1' : '#5d6f82');
    if (full && ch.bytes < M.chunk) txt(p, (M.chunk - ch.bytes) + ' B unused', 22, 272, 25, '#8ea2b6', 500);
    else if (st === 1 && TAKEN[1]) txt(p, TAKEN[1], 22, 272, 27, TAKEN[2]);
    p.done();
  }

  /* ---- state to picture */
  var L;
  function pose(S, snap) {
    Object.keys(A).forEach(function (k) {
      var pl = S.pos[k] ? P[S.pos[k]] : uKeys[k] ? P[uKeys[k]] : null;
      if (pl && !A[k].fixed) A[k].go(pl[0], pl[1], snap);
      A[k].say(S.say[k] || '');
    });
  }
  function show(S, flash) {
    S_desc.set(S.desc, flash); S_cot.set(S.cot, flash); S_done.set(S.done, flash);
    drawPte(S); drawFrame(S);
    var i; for (i = 0; i < NT; i++) drawChunk(i, S);
    for (i = 0; i < segs.length; i++) segs[i].visible = S.eng.vis ? !!S.eng.vis[i] : i < S.eng.segs && S.ch[i] < 2;
    freeLab.setText('free frames: ' + S.free + ' of ' + D.frames.total);
    streamLab.setText(S.eng.lab !== undefined ? S.eng.lab : S.eng.segs ? 'stream: ' + D.stream.len + ' B' : '');
    engLamp.material.color.setHex(S.eng.on ? 0x5ff1ff : 0x2a2244);
    bell.material.color.setHex(S.bell ? 0xf4d35e : 0x33404e); irq.material.color.setHex(S.irq ? 0xb48cff : 0x33404e);
    var gc = R.GATE[S.gate] || R.GATE.idle; lamp.material.color.setHex(gc); pane.material.color.setHex(gc);
    if (L.more) L.more(S, flash);
  }

  /* ---- the panel: a structure as a table, one row per field. A state may carry `long`,
     a map of field name to the text of its value column, for a slot that is used a second time. */
  var LONG = { opcode: D.desc.opcode + ' = ' + D.desc.op_name, status: D.done.status + ' = ' + D.done.status_name };
  function structCard(key, S, head, note) {
    var f = F[key], s = S[key], h = '<div class="card"><h3>' + head + '</h3><table><tr><th>off</th><th>field</th><th>bytes in DRAM</th><th>value</th><th>W</th><th>R</th></tr>';
    f.fields.forEach(function (x) {
      var n = x[0], i, by = '', w = s.w[x[1]], r = s.r[x[1]] || '', hot = s.hot.indexOf(n) >= 0;
      for (i = 0; i < x[2]; i++) by += '<span class="by ' + (s.w[x[1] + i] || '') + '">' + (s.b[x[1] + i] === null ? '--' : R.b2(s.b[x[1] + i])) + '</span>';
      var val = w ? ((s.long && s.long[n]) || (key === 'cot' && n === 'flags' ? hx(D.cot.flags, 2) + ' = VALID' : LONG[n] && key !== 'cot' ? LONG[n] : s.vals[n] || '0')) : '·';
      h += '<tr class="' + (hot ? 'hot' : w ? '' : 'off') + '"><td>+' + x[1] + '</td><td>' + n + '</td><td>' + by + '</td><td>' + val + '</td><td>'
        + (w ? '<span class="wr ' + w + '">' + (w === 'k' ? 'K' : 'HW') + '</span>' : '') + '</td><td>' + (r ? '<span class="wr ' + r + '">' + (r === 'k' ? 'K' : 'HW') + '</span>' : '') + '</td></tr>';
    });
    return h + '</table>' + (note ? '<p style="margin:8px 0 0;font-size:12.5px;color:var(--dim)">' + note + '</p>' : '') + '</div>';
  }
  function tableCard(head, rows, note) {
    var h = '<div class="card"><h3>' + head + '</h3><table>';
    rows.forEach(function (r) { h += '<tr' + (r.hot ? ' class="hot"' : '') + '><td class="t">' + r[0] + '</td><td>' + r[1] + '</td></tr>'; });
    return h + '</table>' + (note ? '<p style="margin:8px 0 0;font-size:12.5px;color:var(--dim)">' + note + '</p>' : '') + '</div>';
  }

  /* ---- what a step is about, as world points: bubbles keep off these */
  function rect(x, z, w, d, y0, y1) { return [[x - w / 2, y0, z - d / 2], [x + w / 2, y0, z - d / 2], [x - w / 2, y1 === undefined ? y0 : y1, z + d / 2], [x + w / 2, y1 === undefined ? y0 : y1, z + d / 2]]; }
  function slabPts(s, x, y, z, tilt) { var dy = s.d / 2 * Math.sin(tilt || 0), dz = s.d / 2 * Math.cos(tilt || 0); return [[x - s.w / 2, y + dy, z - dz], [x + s.w / 2, y + dy, z - dz], [x - s.w / 2, y - dy, z + dz], [x + s.w / 2, y - dy, z + dz]]; }
  var KEEP = {
    desc: slabPts(S_desc, dsc.x, dsc.y, ZDESK, dsc.tilt), done: slabPts(S_done, dne.x, dne.y, ZDESK, dne.tilt), cot: slabPts(S_cot, ct.x, 0.3, ZCOT, 0),
    bell: [[BX - 1.5, 4.5, -25], [BX + 1.5, 9, -25]], irq: [[IX - 1.5, 4.5, -25], [IX + 1.5, 9, -25]],
    pte: [[7.5, 0.8, ZGATE], [24.5, 0.8, ZGATE], [7.5, 7.6, ZGATE], [24.5, 7.6, ZGATE]],
    gate: [[-7, 0, ZGATE], [7, 0, ZGATE], [-7, 11, ZGATE], [7, 11, ZGATE]],
    frame: rect(-27, ZROW + 1, 13, 17, 0.4), engine: rect(-9, ZROW + 2, 14, 12, 0.4, 0.4).concat([[-13.5, 4.5, ZROW - 4], [-4.5, 4.5, ZROW - 4]])
  };
  TILES.forEach(function (c, i) { KEEP['ch' + i] = rect(CX[i], ZROW, TW + 0.6, TW + 0.6, 0.4); });

  L = { KEEP: KEEP, D: D, M: M, V: V, H: H, kit: kit, SEG: SEG, A: A, F: F, P: P, VIEW: VIEW, CX: CX, ZROW: ZROW, ZCOT: ZCOT, XS: XS, NCH: NCH, NT: NT,
        BELL: new T.Vector3(BX, 5.6, -25), IRQ: new T.Vector3(IX, 5.6, -25), MONO: MONO, txt: txt, rect: rect,
        slabs: { desc: S_desc, cot: S_cot, done: S_done }, segs: segs, more: null,
        pose: pose, show: show, structCard: structCard, tableCard: tableCard };
  return L;
};
})();

/* Replay player: main loop, transport, HUD and camera controls.
   A scene is one page access. Events are staged one at a time, so staging always sees the
   model as it is after every earlier event. */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var hx = R.hex, clamp = function (v, a, b) { return Math.max(a, Math.min(b, v)); };
  var DATA = JSON.parse($('replay-data').textContent), runs = DATA.runs;
  var A = { vi: 0, si: 0, ei: 0, intro: false, playing: true, speed: 1, skip: true, stepMode: false, stepDone: false, ended: false, cam: 'overview' };
  var run, kinds, model, scene, stage, dir = new R.Director(), stepEls = [];
  var NAMES = { baseline: 'HW-leaning', software: 'SW-leaning' };
  var NOTES = {
    baseline: ['HW-leaning design: ', 'LZ4 HW keeps the free-chunk stack and writes the COT entries of RW pages. The kernel only submits handles.'],
    software: ['SW-leaning design: ', 'KERNEL SW keeps the COT and the chunk bitmap. LZ4 HW is stateless: every address comes in the descriptor.'] };
  var ALIAS = { baseline: 'baseline', hw: 'baseline', hardware: 'baseline', software: 'software', sw: 'software' };
  /* which design to open: ?design=software (or ?variant=, or #software) in the URL, else the exporter's choice */
  function startIndex() {
    var want = DATA.start || '', q = '';
    try { q = (location.search || '') + '&' + (location.hash || '').replace(/^#/, ''); } catch (e) {}
    q.replace(/^\?/, '').split('&').forEach(function (kv) {
      var p = kv.split('='), k = decodeURIComponent(p[0] || '').toLowerCase(), v = decodeURIComponent(p[1] || '').toLowerCase();
      if ((k === 'design' || k === 'variant') && ALIAS[v]) want = ALIAS[v]; else if (p.length === 1 && ALIAS[k]) want = ALIAS[k];
    });
    for (var i = 0; i < runs.length; i++) if (runs[i].meta.variant === want) return i;
    return 0;
  }
  var SHAPE = { screen: 'screen head', phones: 'headphones', dish: 'dish antenna', stack: 'disc stack' };
  var userName = function (i) { var c = model && model.clients[i]; return c ? c.name : ''; };
  var el = function (tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  var num = function (v) { return Number(v).toLocaleString('en-US'); };

  /* ---- what each trace event means, in words */
  function whoOf(ev) { return ev.ev === 'access' ? 'app' : ev.who === 'hw' ? 'hw' : 'kernel'; }
  function line(ev) {
    var h = ev.h;
    switch (ev.ev) {
      case 'pte': return (ev.valid ? 'map' : 'unmap') + ' the PTE of page ' + hx(h);
      case 'frame': return (ev.op === 'alloc' ? 'take a free frame at ' : 'free the frame at ') + hx(ev.pa, 8);
      case 'state': return 'page ' + hx(h) + ' state: ' + ev.from + ' to ' + ev.to;
      case 'job': return 'hand LZ4 HW a ' + ev.op + ' job (' + ev.hex.length / 2 + ' B descriptor)';
      case 'done': return 'report to the kernel: ' + ev.status + (ev.len ? ', ' + ev.len + ' B' : '');
      case 'chunk':
        if (ev.op === 'pop') return 'pop ' + ev.chunks.length + ' chunk numbers, scatter the data';
        if (ev.op === 'push') return 'push ' + ev.chunks.length + ' chunk numbers back';
        return ev.op + ' ' + ev.chunks.length + ' chunks in the bitmap';
      case 'stack': return ev.op === 'init' ? 'build the free list' : ev.op + ' the SRAM stack top, list chunk ' + hx(ev.list_chunk);
      case 'cot': return ((ev.entry.flags & 1) ? 'write' : 'clear') + ' COT[' + hx(h) + ']';
      case 'cot_read': return 'read COT[' + hx(h) + ']';
      case 'access': return ev.res === 'hit' ? 'passes the gate: PTE valid, no kernel needed' : ev.res === 'lost' ? 'gets an error: the page is lost' : 'passes the gate now: the page is in a frame';
      case 'inject': return 'test: corrupt one stored chunk';
    }
    return ev.ev;
  }
  function fields(ev) {
    var r = [], d, e, add = function (k, v) { r.push([k, v]); }, list = function (a) { return a.map(function (c) { return hx(c); }).join(' '); };
    switch (ev.ev) {
      case 'job':
        d = ev.desc; add('opcode', ev.op);
        if (d.handle !== undefined) add(ev.op === 'INIT' ? 'first_free' : 'handle', hx(d.handle));
        if (d.frame_pa) add('frame_pa', hx(d.frame_pa, 8));
        if (d.chunks) add('chunks[' + d.chunks.length + ']', list(d.chunks));
        if (d.limit) add('limit', d.limit + ' B');
        if (d.chunks) { add('comp_len', d.comp_len + ' B'); add('checksum', hx(d.checksum, 8)); }
        add('tag', hx(d.tag)); break;
      case 'done':
        add('status', ev.status); add('len', ev.len + ' B'); add('checksum', hx(ev.csum, 8)); add('flags', hx(ev.flags, 2)); add('tag', hx(ev.tag));
        add('latency', (ev.lat_ns / 1000).toFixed(2) + ' us'); break;
      case 'cot': case 'cot_read':
        e = ev.entry; add('entry', 'COT[' + hx(ev.h) + ']'); add('flags', hx(e.flags, 2) + ((e.flags & 1) ? ' valid' : ' empty') + ((e.flags & 2) ? ' RO' : '') + ((e.flags & 4) ? ' raw' : ''));
        add('count', e.count); add('comp_len', e.comp_len + ' B'); add('checksum', hx(e.checksum, 8)); add('chunks', e.chunks.length ? list(e.chunks) : 'none'); break;
      case 'chunk':
        add('op', ev.op); add('chunks[' + ev.chunks.length + ']', list(ev.chunks)); if (ev.words) add('bitmap words scanned', ev.words); break;
      case 'stack':
        add('op', ev.op); if (ev.list_chunk !== undefined) add('list chunk', hx(ev.list_chunk));
        if (ev.op === 'spill') add('next', ev.next === 0xFFFFFF ? 'none' : hx(ev.next));
        if (ev.list_head !== undefined) add('list head', ev.list_head === 0xFFFFFF ? 'none' : hx(ev.list_head));
        add('SRAM depth', ev.sram); add('list chunks', ev.list_chunks); break;
      case 'frame': add('op', ev.op); add('frame', model.frameIndex(ev.pa)); add('pa', hx(ev.pa, 8)); add('page', hx(ev.h)); break;
      case 'pte': add('page', hx(ev.h)); add('valid', ev.valid); add('pa', hx(ev.pa, 8)); break;
      case 'state': add('page', hx(ev.h)); add('from', ev.from); add('to', ev.to); break;
      case 'access': if (userName(ev.client)) add('user SW', userName(ev.client)); add('page', hx(ev.h) + (model.isRO(ev.h) ? ' RO' : ' RW')); add('type', ev.w ? 'write' : 'read'); add('result', ev.res);
        if (ev.lat_ns) add('waited', (ev.lat_ns / 1000).toFixed(2) + ' us'); break;
    }
    return r;
  }

  function classify(r) {
    return r.scenes.map(function (evs) {
      var k = { res: 'hit', evict: false, acc: null };
      evs.forEach(function (e) {
        if (e.ev === 'access') { k.res = e.res; k.acc = e; }
        if ((e.ev === 'job' && e.op === 'COMPRESS') || (e.ev === 'frame' && e.op === 'free')) k.evict = true;
      });
      return k;
    });
  }

  /* ---- HUD */
  function hudScene() {
    var k = kinds[A.si], a = k.acc, evs = run.scenes[A.si], ol = $('steps');
    var res = { hit: 'HIT', first: 'FIRST TOUCH', fault: 'PAGE FAULT', lost: 'LOST' }[k.res];
    var un = a ? userName(a.client) : '', st = $('sceneTitle');
    $('sceneNo').textContent = 'Access ' + num(A.si + 1) + ' of ' + num(run.scenes.length) + (un ? ', by user SW' : '');
    st.textContent = '';
    if (un) { var chip = el('b', 'uchip', un); chip.style.background = R.userCss(a.client); st.appendChild(chip); }
    st.appendChild(document.createTextNode(a ? (a.w ? 'write' : 'read') + ' page ' + hx(a.h) + (model.isRO(a.h) ? ' (RO)' : ' (RW)') : 'trailing events'));
    $('sceneRes').textContent = res + (k.evict ? ' + RECLAIM' : ''); $('sceneRes').className = 'res res-' + k.res;
    ol.textContent = ''; stepEls = [];
    evs.forEach(function (ev) {
      var li = el('li'), w = whoOf(ev), tag = el('b', 'who who-' + w, w === 'hw' ? 'HW' : w === 'app' ? userName(ev.client) || 'APP' : 'KERNEL');
      if (w === 'app' && userName(ev.client)) tag.style.background = R.userCss(ev.client);
      li.appendChild(tag);
      li.appendChild(el('span', '', line(ev)));
      ol.appendChild(li); stepEls.push(li);
    });
    $('detail').textContent = '';
    $('scrub').value = A.si; $('pos').textContent = num(A.si + 1) + ' / ' + num(run.scenes.length);
  }
  function hudStep(i) {
    var ev = run.scenes[A.si][i], box = $('detail');
    stepEls.forEach(function (li, j) { li.className = j < i ? 'done' : j === i ? 'on' : ''; });
    if (stepEls[i] && stepEls[i].scrollIntoView) { var ol = $('steps'); ol.scrollTop = Math.max(0, stepEls[i].offsetTop - ol.clientHeight / 2); }
    box.textContent = '';
    box.appendChild(el('div', 'dhead', ev.ev + (ev.op ? ' ' + ev.op : '') + '  by ' + (whoOf(ev) === 'hw' ? 'hardware' : whoOf(ev) === 'app' ? 'user SW ' + (userName(ev.client) || '') : 'the kernel')));
    var dl = el('dl');
    fields(ev).forEach(function (f) { dl.appendChild(el('dt', '', f[0])); dl.appendChild(el('dd', '', String(f[1]))); });
    box.appendChild(dl);
    if (ev.hex) {
      box.appendChild(el('div', 'dhead', 'raw ' + ev.hex.length / 2 + ' bytes, each byte in hex'));
      box.appendChild(el('pre', '', ev.hex.match(/.{1,2}/g).join(' ').replace(/((?:\S+ ){8})/g, '$1\n').trim()));
    }
  }
  function hudCounters() {
    var m = model.meta, n = model.n, box = $('counters'), rows = [
      ['sim time', (model.t / 1e6).toFixed(3) + ' ms'],
      ['free frames', num(model.freeFrames) + ' / ' + num(m.frames)],
      ['free chunks', num(model.freeChunks()) + ' / ' + num(m.pool_chunks)],
      model.variant === 'software' ? ['bitmap cursor', 'word ' + Math.max(0, model.cursorWord)] : ['SRAM stack', model.sram.size + ' / ' + m.sram_cap + ', ' + model.listCount + ' list chunks'],
      ['hit / first / fault', num(n.hit) + ' / ' + num(n.first) + ' / ' + num(n.fault)],
      ['jobs C / D / INV', num(n.compress) + ' / ' + num(n.decompress) + ' / ' + num(n.invalidate)],
      ['COT writes', 'HW ' + num(n.cotHw) + ', kernel ' + num(n.cotKernel)],
      model.variant === 'software' ? ['RO drops', num(n.roDrop)] : ['refill / spill', n.refill + ' / ' + n.spill]];
    if (model.clients.length) rows.push(['accesses by ' + model.clients.map(function (c) { return c.name; }).join(' / '), model.served.map(num).join(' / '), 'wide']);
    box.textContent = '';
    rows.forEach(function (r) { var d = el('div', r[2] || ''); d.appendChild(el('span', '', r[0])); d.appendChild(el('b', '', r[1])); box.appendChild(d); });
  }
  function drawTimeline() {
    var cv = $('tl'), w = cv.clientWidth || 300, dpr = Math.min(2, window.devicePixelRatio || 1), c = cv.getContext('2d'), N = kinds.length;
    cv.width = Math.round(w * dpr); cv.height = Math.round(20 * dpr); c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.fillStyle = '#131c26'; c.fillRect(0, 0, w, 20);
    kinds.forEach(function (k, s) {
      var x = s / N * w, bw = Math.max(1.2, w / N);
      if (k.res !== 'hit') { c.fillStyle = k.res === 'first' ? '#aab6c2' : k.res === 'lost' ? '#ff5d5d' : model.isRO(k.acc.h) ? '#35b56f' : '#3d8bff'; c.fillRect(x, 7, bw, 13); }
      if (k.evict) { c.fillStyle = '#d9a23a'; c.fillRect(x, 0, bw, 5); }
    });
  }
  function setPlaying(p) { A.playing = p; $('play').textContent = p ? 'Pause' : 'Play'; $('play').setAttribute('aria-pressed', p ? 'true' : 'false'); }
  function setCam(mode) {
    A.cam = mode; if (scene) scene.cam.mode = mode;
    $('camFollow').className = mode === 'follow' ? 'on' : ''; $('camOverview').className = mode === 'overview' ? 'on' : '';
  }

  /* ---- playback */
  function applyScene(s) { var evs = run.scenes[s]; for (var i = 0; i < evs.length; i++) model.apply(evs[i]); }
  function advance() {
    var evs = run.scenes[A.si], last = run.scenes.length - 1;
    if (!A.intro) { A.intro = true; hudScene(); stage.intro(kinds[A.si].acc, kinds[A.si]).forEach(function (c) { dir.q.push(c); }); return true; }
    if (A.ei < evs.length) {
      if (A.stepMode) { if (A.stepDone) { A.stepMode = false; setPlaying(false); return false; } A.stepDone = true; }
      var i = A.ei++, ev = evs[i], applied = false;
      var apply = function () { if (applied) return; applied = true; model.apply(ev); scene.sync(); hudCounters(); };
      hudStep(i);
      stage.stage(ev, i, evs, apply).forEach(function (c) { dir.q.push(c); });
      dir.q.push({ dur: 0, done: apply });
      return true;
    }
    if (A.si >= last) { A.ended = true; A.stepMode = false; setPlaying(false); return false; }
    A.si++; A.ei = 0; A.intro = false;
    if (A.skip) {
      while (A.si < last && kinds[A.si].res === 'hit' && !kinds[A.si].evict) { applyScene(A.si); A.si++; }
      scene.sync(); hudCounters();
    }
    return true;
  }
  function seek(t) {
    var s, evs, i;
    t = clamp(Math.round(Number(t)) || 0, 0, run.scenes.length - 1);
    dir.flush();
    if (t > A.si) {
      evs = run.scenes[A.si]; for (i = A.ei; i < evs.length; i++) model.apply(evs[i]);
      for (s = A.si + 1; s < t; s++) applyScene(s);
    } else {
      model.reset(); run.boot.forEach(function (e) { model.apply(e); });
      for (s = 0; s < t; s++) applyScene(s);
    }
    A.si = t; A.ei = 0; A.intro = false; A.ended = false; A.stepMode = false;
    model.dirty.all = true; scene.sync();
    scene.hush(); scene.activate(null, false, true);
    hudScene(); hudCounters();
  }
  function nextFault(dirn) {
    for (var s = A.si + dirn; s >= 0 && s < kinds.length; s += dirn) if (kinds[s].res !== 'hit') { seek(s); return; }
  }

  function resize() {
    var st = $('stage'), w = st.clientWidth || 800, h = st.clientHeight || 600;
    if (scene) {
      var keep = scene.cam.followR; scene.resize(w, h); if (keep && A.zoomed) scene.cam.followR = keep;
      /* centre the action in the part of the view the panels leave free */
      var pr = $('panel').getBoundingClientRect(), br = $('bar').getBoundingClientRect(), tr = $('top').getBoundingClientRect();
      var side = pr.left > w * 0.4, ox = side ? (w - pr.left) / 2 : 0, oy = ((h - (side ? br.top : pr.top)) - tr.bottom) / 2;
      scene.vo = { x: Math.round(ox), y: Math.round(oy) }; scene._dyOn = null; scene._fitKey = null;
      scene.camera.setViewOffset(w, h, scene.vo.x, scene.vo.y, w, h);
      /* the speech bubbles stay inside the same free area */
      var sr = st.getBoundingClientRect();
      scene.free = { l: 8, t: tr.bottom - sr.top + 6, r: (side ? pr.left - sr.left : w) - 8, b: (side ? br.top : pr.top) - sr.top - 8 };
    }
    if (kinds) drawTimeline();
  }
  function load(vi, si) {
    var th = scene ? scene.cam.th : -0.35, ph = scene ? scene.cam.ph : 0.92;
    if (scene) { dir.flush(); scene.dispose(); try { scene.renderer.forceContextLoss(); } catch (e) {} scene = null; }
    run = runs[vi]; A.vi = vi; kinds = classify(run);
    model = new R.Model(run); run.boot.forEach(function (e) { model.apply(e); });
    var old = $('cv'), cv = el('canvas'); cv.id = 'cv'; old.parentNode.replaceChild(cv, old);
    try { scene = new R.Scene(model, cv); } catch (e) { $('err').hidden = false; $('err').textContent = 'This page needs WebGL, which is not available here. ' + e.message; return; }
    stage = new R.Stage(scene, model); dir = new R.Director();
    scene.cam.th = th; scene.cam.ph = ph; A.zoomed = false; resize(); setCam(A.cam);
    var snap = function () { if (A.cam === 'overview') { scene.cam.r = scene.fitR(); scene.cam.target.copy(scene._ov); scene._dy = scene._fitDy; } };
    A.si = 0; A.ei = 0; A.intro = false; A.ended = false;
    $('scrub').max = run.scenes.length - 1;
    Array.prototype.forEach.call($('variants').children, function (b, i) {
      b.className = 'v-' + runs[i].meta.variant + (i === vi ? ' on' : ''); b.setAttribute('aria-pressed', i === vi ? 'true' : 'false'); });
    var note = NOTES[run.meta.variant] || ['', ''], dn = $('designNote');
    dn.textContent = ''; dn.appendChild(el('b', '', note[0])); dn.appendChild(document.createTextNode(note[1]));
    resize(); snap();   /* open with the whole machine in view, no zoom-out on the way */
    $('machine').textContent = num(model.meta.frames) + ' frames, ' + num(model.meta.pool_chunks) + ' chunks, ' + num(model.meta.pages) + ' pages, seed ' + model.meta.seed;
    document.body.setAttribute('data-variant', run.meta.variant);
    /* one legend entry per user program: its colour and its shape */
    var lg = $('legend');
    Array.prototype.slice.call(lg.querySelectorAll('.dyn')).forEach(function (e) { lg.removeChild(e); });
    model.clients.forEach(function (c, i) {
      var sp = el('span', 'dyn'), sw = el('i'); sw.style.background = R.userCss(i); sp.appendChild(sw);
      sp.appendChild(document.createTextNode('user SW ' + c.name + ': ' + SHAPE[R.USER_LOOK[i % R.USER_LOOK.length][0]]));
      lg.appendChild(sp);
    });
    var gs = el('span', 'dyn'), gi = el('i'); gi.style.background = scene.gate.css; gs.appendChild(gi);
    gs.appendChild(document.createTextNode('access gate: MMU + page table, lamp green = pass, red = stopped')); lg.appendChild(gs);
    drawTimeline();
    if (si) seek(si); else { hudScene(); hudCounters(); }
  }

  /* ---- controls */
  runs.forEach(function (r, i) {
    var b = el('button', '', NAMES[r.meta.variant] || r.meta.variant); b.type = 'button'; b.title = (NOTES[r.meta.variant] || ['', ''])[1];
    b.onclick = function () { if (i !== A.vi) load(i, A.si); };
    $('variants').appendChild(b);
  });
  if (runs.length < 2) $('variants').className += ' single';
  $('play').onclick = function () { if (A.ended) seek(0); A.stepMode = false; setPlaying(!A.playing); };
  $('stepEv').onclick = function () { if (A.ended) return; A.stepMode = true; A.stepDone = dir.busy() && A.ei > 0; setPlaying(true); };
  $('prev').onclick = function () { seek(A.ei > 0 ? A.si : A.si - 1); };
  $('next').onclick = function () { seek(A.si + 1); };
  $('nextFault').onclick = function () { nextFault(1); };
  $('prevFault').onclick = function () { nextFault(-1); };
  $('speed').onchange = function () { A.speed = parseFloat(this.value) || 1; };
  $('skip').onchange = function () { A.skip = this.checked; };
  $('scrub').oninput = function () { seek(parseInt(this.value, 10) || 0); };
  $('camFollow').onclick = function () { setCam('follow'); };
  $('camOverview').onclick = function () { setCam('overview'); };
  $('panelToggle').onclick = function () { var p = $('panel'), open = p.className.indexOf('open') < 0; p.className = open ? 'open' : ''; this.textContent = open ? 'Hide details' : 'Details'; resize(); };
  window.addEventListener('keydown', function (e) {
    if (e.target && /INPUT|SELECT|BUTTON/.test(e.target.tagName) && e.key === ' ') return;
    if (e.key === ' ') { e.preventDefault(); $('play').onclick(); }
    else if (e.key === 'ArrowRight') $('stepEv').onclick();
    else if (e.key === 'ArrowLeft') $('prev').onclick();
    else if (e.key === 'n') $('next').onclick();
    else if (e.key === 'f') nextFault(1);
  });

  /* camera: drag orbits, wheel or pinch zooms, shift-drag or two fingers pan */
  var st = $('stage'), ptrs = {}, gest = null;
  var count = function () { return Object.keys(ptrs).length; };
  function zoom(f) {
    var c = scene.cam;
    if (c.mode === 'follow') { c.followR = clamp(c.followR * f, 22, 620); A.zoomed = true; }
    else { setCam('free'); c.r = clamp(c.r * f, 22, 2400); }
  }
  function pan(dx, dy) {
    var c = scene.cam, s = c.r * 0.0016; setCam('free');
    c.target.x += (-Math.cos(c.th) * dx - Math.sin(c.th) * dy) * s;
    c.target.z += (Math.sin(c.th) * dx - Math.cos(c.th) * dy) * s;
  }
  function two() { var k = Object.keys(ptrs), a = ptrs[k[0]], b = ptrs[k[1]]; return { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; }
  st.addEventListener('pointerdown', function (e) { ptrs[e.pointerId] = { x: e.clientX, y: e.clientY }; try { st.setPointerCapture(e.pointerId); } catch (x) {} gest = count() === 2 ? two() : null; });
  st.addEventListener('pointermove', function (e) {
    var p = ptrs[e.pointerId]; if (!p || !scene) return;
    var dx = e.clientX - p.x, dy = e.clientY - p.y, c = scene.cam; p.x = e.clientX; p.y = e.clientY;
    if (count() === 1) {
      if (e.shiftKey || e.buttons === 2) pan(dx, dy);
      else { c.th -= dx * 0.005; c.ph = clamp(c.ph - dy * 0.005, 0.12, 1.5); }
    } else if (count() === 2 && gest) { var g = two(); zoom(gest.d / g.d); pan(g.x - gest.x, g.y - gest.y); gest = g; }
  });
  var up = function (e) { delete ptrs[e.pointerId]; gest = null; };
  st.addEventListener('pointerup', up); st.addEventListener('pointercancel', up);
  st.addEventListener('wheel', function (e) { e.preventDefault(); if (scene) zoom(Math.exp(e.deltaY * 0.0012)); }, { passive: false });
  st.addEventListener('contextmenu', function (e) { e.preventDefault(); });

  /* ---- go */
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) A.playing = false;
  load(startIndex(), 0); setPlaying(A.playing);
  if (window.ResizeObserver) new ResizeObserver(resize).observe(st); else window.addEventListener('resize', resize);
  var lastT = performance.now(), PACE = 0.7;   /* 1x is 70% of the first version's pace */
  (function frame(now) {
    requestAnimationFrame(frame);
    var dt = Math.min(0.05, Math.max(0, ((now || lastT) - lastT) / 1000)); lastT = now || lastT;
    if (scene) {
      if (A.playing) { var left = dt * A.speed * PACE, g = 0; while (left > 0 && g++ < 80) { if (!dir.busy() && !advance()) break; left = dir.tick(left); } }
      scene.update(dt, lastT / 1000);
    }
  })();
  /* test hook: plays every remaining event through its full staging with no waiting */
  function runAll() { var g = 0; A.stepMode = false; while (g++ < 5e6) { if (!dir.busy() && !advance()) break; dir.tick(1e6); } return g; }
  R.app = { A: A, seek: seek, load: load, runAll: runAll, setPlaying: setPlaying, nextFault: nextFault, state: function () { return { model: model, scene: scene, dir: dir, kinds: kinds }; } };
})();

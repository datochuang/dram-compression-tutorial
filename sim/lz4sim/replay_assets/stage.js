/* Replay staging: turns each trace event into clips acted by the user programs, the kernel and
   the accelerator. A clip is {dur, init(), fn(k), done()}; the director plays them in order.
   Every staging calls apply() exactly once, at the moment the trace event takes effect.

   The story of every scene: a user program touches a page. Every access of every program goes
   to the same place, the access gate (MMU and page table). A valid PTE lets it through to its
   frame and nobody else is involved. An invalid PTE stops it there: the request stays on the
   counter, KERNEL SW comes over, says what the situation is (never used, or compressed and to be
   unpacked, or frames running low as well), hands LZ4 HW its jobs as descriptors (a briefing at
   the job ring, a report back when the job is done), makes the PTE valid and the access passes. */
R.Director = function () { this.q = []; this.cur = null; };
R.Director.prototype.busy = function () { return !!(this.cur || this.q.length); };
R.Director.prototype.tick = function (dt) {
  while (dt > 0) {
    if (!this.cur) {
      this.cur = this.q.shift(); if (!this.cur) return dt;
      if (this.cur.init) this.cur.init();
      this.cur.t = 0; if (!this.cur.dur) this.cur.dur = 0;
    }
    var c = this.cur, use = Math.min(c.dur - c.t, dt);
    c.t += use; dt -= use;
    if (c.fn) c.fn(c.dur ? Math.min(1, c.t / c.dur) : 1);
    if (c.t >= c.dur - 1e-9) { if (c.done) c.done(); this.cur = null; } else return 0;
  }
  return 0;
};
R.Director.prototype.flush = function () {
  var guard = 0;
  while (this.busy() && guard++ < 10000) this.tick(1e6);
};

R.Stage = function (scene, model) {
  var S = scene, M = model, KN = S.kernel, RB = S.robot, C = R.COL, V = THREE.Vector3, hx = R.hex;
  var ease = function (k) { return k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; };
  var clamp = function (v, a, b) { return Math.max(a, Math.min(b, v)); };
  var call = function (f) { return { dur: 0, done: f }; };
  var wait = function (d) { return { dur: d }; };
  var say = function (a, t) { return call(function () { if (a) a.bubble.setText(t); }); };
  var par = function (clips) {
    return {
      init: function () { var mx = 0; clips.forEach(function (c) { if (c.init) c.init(); c.dur = c.dur || 0; mx = Math.max(mx, c.dur); }); this.dur = mx; },
      fn: function (k) { var t = k * this.dur; clips.forEach(function (c) { var kk = c.dur ? Math.min(1, t / c.dur) : 1; if (c._d) return; if (c.fn) c.fn(kk); if (kk >= 1) { c._d = 1; if (c.done) c.done(); } }); }
    };
  };
  var move = function (a, to) {
    return {
      init: function () {
        var t = this.to = typeof to === 'function' ? to() : to; this.from = a.pos.clone();
        var d = Math.hypot(t.x - this.from.x, t.z - this.from.z); this.dur = d < 0.3 ? 0 : clamp(d / (a === RB ? 190 : 150), 0.22, 0.85);
        if (d > 0.5 && a === KN) a.group.rotation.y = Math.atan2(t.x - this.from.x, t.z - this.from.z);
      },
      fn: function (k) { var e = ease(k), t = this.to; a.pos.x = this.from.x + (t.x - this.from.x) * e; a.pos.z = this.from.z + (t.z - this.from.z) * e; a.walk = 1; S.focus.set(a.pos.x, 2, a.pos.z); }
    };
  };
  var fly = function (get, to, dur, arc) {
    return {
      dur: dur || 0.3,
      init: function () { this.o = get(); this.from = this.o.position.clone(); this.to = typeof to === 'function' ? to() : to; },
      fn: function (k) { var e = ease(k); this.o.position.lerpVectors(this.from, this.to, e); this.o.position.y += Math.sin(Math.PI * k) * (arc || 0); }
    };
  };
  var hold = function (a, o) { a.hands.add(o); o.position.set(0, 0, 0); };
  var release = function (o, at) { var w = new V(); o.getWorldPosition(w); S.scene.add(o); o.position.copy(at || w); o.rotation.set(0, 0, 0); };
  var handsPos = function (a) { var w = new V(); a.hands.getWorldPosition(w); return w; };
  var nearFrame = function (f) { var p = S.framePos(f); return new V(p.x, 0, p.z + 2.6); };
  var overFrame = function (f) { var p = S.framePos(f); return new V(p.x, 0, p.z - 3.0); };
  var overChunks = function (ch) { var p = S.centroid(ch); return new V(p.x, 0, p.z - 3.0); };
  var cotStand = function (h) { return new V(S.cotPos(h).x, 0, S.zCot - 3.4); };   /* at the far edge of the ledger, which stays in view */
  var bitStand = function (c) { return new V(S.bitPos(c).x, 0, S.zBit - 3.4); };
  var PRESS = new V(0, 0, -3.0);
  /* where the two stand at the job ring: further apart the larger they are drawn */
  var kStand = function () { return new V(-5 - 2.6 * (KN.s - 1), 0, S.zRing); };
  var rStand = function () { return new V(5.5 + 2.6 * (KN.s - 1), 0, S.zRing); };
  /* the kernel's place beside the access gate, and points on the gate */
  var GT = S.gate, gTray = function () { return GT.tray.clone(); };
  var gStand = function () { return new V(-(17.5 * GT.k + 3.2 * KN.s), 0, S.zGate + 2); };
  var kHome = function () { return new V(-6 - 2.6 * (KN.s - 1), 0, S.zRing); };
  var kHands = function () { return new V(KN.pos.x + 1.2 * KN.s, 4.6 * KN.s, KN.pos.z); };
  var uHands = function (u) { return function () { return new V(u.pos.x, u.top() * 0.6, u.pos.z + 1.5 * u.k); }; };
  var userOf = function (h) { return S.users[M.clientOf(h)] || null; };
  var nameOf = function (h) { var u = userOf(h); return u ? u.name : ''; };
  var rw = function (ev) { return (ev.w ? 'write' : 'read') + ' page ' + pg(ev.h); };
  var lines = function (L) { return L[0] + L.slice(1).map(function (t) { return '\n\u00b7 ' + t; }).join(''); };
  var towerTop = function () { return new V(S.xTower, Math.max(1, S.towerH * M.sram.size / M.meta.sram_cap), S.zTower); };
  var pg = function (h) { return hx(h) + (M.isRO(h) ? ' (RO)' : ' (RW)'); };
  var SW = M.variant === 'software';

  /* what the kernel tells the accelerator: the descriptor, field by field, as an instruction */
  function brief(ev, again) {
    var d = ev.desc, h = d.handle !== undefined ? d.handle : d.tag, f = d.frame_pa ? M.frameIndex(d.frame_pa) : -1, o = nameOf(h), L;
    if (again) {
      return 'To LZ4 HW, next job: ' + ev.op + (ev.op === 'COMPRESS' ? ' frame ' + f + ', page ' + hx(h) + (o ? ' of ' + o : '')
        : ev.op === 'DECOMPRESS' ? ' page ' + hx(h) + ' into frame ' + f : ' page ' + hx(h));
    }
    L = ['To LZ4 HW, your job: ' + ev.op];
    if (ev.op === 'COMPRESS') {
      L.push('frame ' + f + ', page ' + hx(h) + (o ? ' of ' + o : ''));
      L.push(SW ? 'store into my ' + d.chunks.length + ' reserved chunks' : 'you pop the chunks, you write the COT');
      L.push('give up over ' + d.limit + ' B');
    } else if (ev.op === 'DECOMPRESS') {
      L.push('page ' + hx(h) + (o ? ' for ' + o : '') + ', into frame ' + f);
      if (SW) L.push(d.chunks.length + ' chunks, ' + d.comp_len + ' B', 'checksum ' + hx(d.checksum, 8));
      else L.push('you look up its chunks in the COT');
    } else if (ev.op === 'INVALIDATE') L.push('page ' + hx(h) + (o ? ' of ' + o : ''), 'you clear its COT entry', 'you push its chunks on your stack');
    else if (ev.op === 'INIT') L.push('first free chunk ' + hx(d.handle), 'you build the free list');
    return lines(L);
  }
  /* what the accelerator reports back: the completion record */
  function report(ev, job) {
    var op = job ? job.op : '', h = job ? job.h : 0, d = job ? job.desc : {}, L = ['Report to KERNEL: ' + ev.status], n;
    if (ev.status === 'OK') {
      if (op === 'COMPRESS') {
        n = Math.ceil(ev.len / M.meta.chunk);
        if (SW) L.push(ev.len + ' B, checksum ' + hx(ev.csum, 8), 'used ' + n + ' of your ' + d.chunks.length + ' chunks');
        else L.push(ev.len + ' B in ' + n + ' chunks', 'I wrote COT[' + hx(h) + ']');
      } else if (op === 'DECOMPRESS') L.push('frame ' + M.frameIndex(d.frame_pa) + ' holds page ' + hx(h), 'checksum matched');
      else if (op === 'INVALIDATE') L.push('COT[' + hx(h) + '] cleared', 'its chunks are on my stack');
      else if (op === 'INIT') L.push('free list built');
    } else if (ev.status === 'INCOMPRESSIBLE') L.push('over ' + d.limit + ' B, nothing stored', SW ? 'none of your chunks was written' : 'I pushed the chunks back');
    else if (ev.status === 'BAD_STREAM') L.push('checksum mismatch', 'the frame holds no valid page');
    else if (ev.status === 'POOL_FULL') L.push('no free chunk left, nothing stored');
    else if (ev.status === 'BAD_DESC') L.push('descriptor rejected, nothing done');
    return lines(L);
  }
  /* is this the first job with this opcode in the scene? The first gets the full briefing. */
  function firstOf(evs, i, op) {
    for (var j = 0; j < i; j++) if (evs[j].ev === 'job' && evs[j].op === op) return false;
    return true;
  }

  /* the accelerator carries a page to the press, squeezes it and scatters the chunks */
  function compressAct(h, f, chunks, ok, apply, failText) {
    var x = {}, n = chunks.length, ratio = ok ? Math.max(0.12, n / 8) : 0.94, col = S.pageColor(h);
    var out = [say(RB, 'read frame ' + f + ' (4096 B)'), move(RB, overFrame(f)),
      call(function () { x.slab = S.temp('slab', col, false); hold(RB, x.slab); }),
      move(RB, PRESS),
      call(function () { release(x.slab, new V(0, 1.5, 0)); RB.bubble.setText('LZ4 encode'); }),
      { dur: 0.45, fn: function (k) { var r = 1 + (ratio - 1) * ease(k); x.slab.scale.y = r; x.slab.position.y = 1 + r / 2; S.plate.position.y = 1.3 + r + (1 - ease(k)) * 4.8; } },
      call(function () {
        if (ok) { x.slab.material.map = S.hatch; x.slab.material.needsUpdate = true; }
        else { S.pulse(new V(0, 1, 0), C.bad, false, 8); RB.bubble.setText(failText || 'over the limit: give up'); }
      }),
      { dur: 0.22, fn: function (k) { S.plate.position.y = 1.3 + ratio + ease(k) * (5.1 - ratio); } }];
    if (!ok) { out.push(wait(0.25), call(function () { S.drop(x.slab); apply(); })); return out; }
    out.push(call(function () {
      S.drop(x.slab); x.br = [];
      for (var i = 0; i < n; i++) { var b = S.temp('brick', col, true); hold(RB, b); b.position.set((i - (n - 1) / 2) * 0.95, 0, 0); x.br.push(b); }
      RB.bubble.setText('scatter into ' + n + ' chunks');
    }), move(RB, overChunks(chunks)),
    call(function () { x.br.forEach(function (b) { release(b); }); }),
    par(chunks.map(function (c, i) { var p = S.chunkPos(c); p.y = 0.4; return fly(function () { return x.br[i]; }, p, 0.26 + i * 0.05, 2.5); })),
    call(function () { x.br.forEach(function (b) { S.drop(b); }); apply(); S.pulse(S.centroid(chunks), col, false, 5); }));
    return out;
  }

  /* the accelerator gathers the chunks, inflates them on the press and puts the page in the frame */
  function decompressAct(h, f, chunks, ok, apply, viaCot) {
    var x = {}, n = chunks.length, col = S.pageColor(h), out = [];
    if (viaCot === 'miss') out.push(say(RB, 'CTLB miss: read COT[' + hx(h) + ']'), move(RB, cotStand(h)), call(function () { S.pulse(S.cotPos(h), C.hw, true, 3); }), wait(0.12));
    if (viaCot === 'hit') out.push(say(RB, 'CTLB hit'));
    out.push(say(RB, 'gather ' + n + ' chunks'), move(RB, overChunks(chunks)),
      call(function () { x.br = chunks.map(function (c) { var b = S.temp('brick', col, true); b.position.copy(S.chunkPos(c)); b.position.y = 0.4; return b; }); }),
      par(chunks.map(function (c, i) { return fly(function () { return x.br[i]; }, function () { var w = handsPos(RB); w.x += (i - (n - 1) / 2) * 0.95; return w; }, 0.22 + i * 0.04, 2); })),
      call(function () { x.br.forEach(function (b, i) { hold(RB, b); b.position.set((i - (n - 1) / 2) * 0.95, 0, 0); }); }),
      move(RB, PRESS),
      call(function () {
        x.br.forEach(function (b) { S.drop(b); });
        x.slab = S.temp('slab', col, true); x.slab.scale.y = n / 8; x.slab.position.set(0, 1 + n / 16, 0);
        RB.bubble.setText('checksum, then LZ4 decode');
      }));
    if (!ok) {
      out.push(wait(0.2), call(function () { S.pulse(new V(0, 1, 0), C.bad, false, 9); RB.bubble.setText('BAD_STREAM: checksum mismatch'); S.drop(x.slab); apply(); }), wait(0.3));
      return out;
    }
    out.push({ dur: 0.35, fn: function (k) { var r = n / 8 + (1 - n / 8) * ease(k); x.slab.scale.y = r; x.slab.position.y = 1 + r / 2; } },
      call(function () { x.slab.material.map = null; x.slab.material.needsUpdate = true; hold(RB, x.slab); RB.bubble.setText('write 4096 B to frame ' + f); }),
      move(RB, overFrame(f)),
      call(function () { var p = S.framePos(f); p.y = 2; release(x.slab, p); }),
      fly(function () { return x.slab; }, function () { var p = S.framePos(f); p.y = 0.62; return p; }, 0.14),
      call(function () { S.drop(x.slab); apply(); }));
    return out;
  }

  /* a sheet of paper thrown from one character to another: a request, a descriptor, a completion */
  function sheet(color, from, to) {
    var x = {};
    return [{
      init: function () {
        x.a = from(); x.b = to(); x.d = x.a.distanceTo(x.b);
        x.c = S.temp('sheet', color, false); x.c.scale.setScalar(Math.max(1, KN.s * 0.8)); x.c.position.copy(x.a);
        this.dur = clamp(x.d / 230, 0.3, 0.6);
      },
      fn: function (k) { x.c.position.lerpVectors(x.a, x.b, ease(k)); x.c.position.y += Math.sin(Math.PI * k) * (2 + x.d * 0.13); x.c.rotation.z = Math.sin(Math.PI * k) * 0.5; },
      done: function () { S.drop(x.c); }
    }];
  }
  var robotTop = function () { return new V(RB.pos.x, RB.lift + 3.2 * RB.s, RB.pos.z); };

  /* user program -> gate -> frame, drawn as two fading lines in the program's colour */
  function through(u, fp, color) {
    if (!u || !fp) return;
    S.beam(new V(u.pos.x, u.top() * 0.6, u.pos.z), GT.mid, color); S.beam(GT.mid, new V(fp.x, 1, fp.z), color);
  }
  /* scene start: the user program sends its access to the gate. A page that is not in a frame
     is stopped there, and the kernel comes over and says what this case needs. */
  this.intro = function (last, kind) {
    S.hush();
    var u = last && last.ev === 'access' ? S.users[last.client] || null : null;
    if (!u || last.res === 'hit') { S.activate(u, false); return []; }
    var h = last.h, first = last.res === 'first', L;
    L = [(first ? 'FIRST TOUCH ' : 'PAGE FAULT ') + pg(h),
         first ? 'never used: a zero-filled frame will do' : 'it is compressed in the pool: unpack it'];
    if (kind && kind.evict) L.push('free frames are low: compress cold pages too');
    L.push(u.name + ' stops until the page is in a frame');
    return [call(function () { S.activate(u, true); u.bubble.setText(rw(last)); S.focus.set(u.pos.x * 0.4, 2, S.zGate); }), wait(0.45)]
      .concat(sheet(u.color, uHands(u), gTray),
      [call(function () {
        S.setTicket(u.color); S.setGate('stop'); S.pulse(GT.tray, C.bad, false, 7);
        GT.bubble.setText(lines(['PTE of ' + hx(h) + ' is not valid', 'access stopped, KERNEL SW is called']));
        u.bubble.setText('stopped: waiting for page ' + hx(h));
      }), wait(0.55), move(KN, gStand),
      call(function () {
        KN.group.rotation.y = 0.9; GT.bubble.setText(''); KN.bubble.setText(lines(L));
        S.pulse(S.cotPos(h), C.bad, true, 5); S.focus.copy(KN.pos);
      }), wait(0.7), call(function () { KN.group.rotation.y = 0; })]);
  };

  this.stage = function (ev, i, evs, apply) {
    var h = ev.h, f, job = M.lastJob, out = [], chunks, n, who = ev.who === 'hw' ? RB : KN;
    switch (ev.ev) {
      case 'pte':
        f = M.frameOf[h]; if (f < 0) return [call(apply)];
        /* the page table is at the gate: that is where the kernel makes a PTE valid or not */
        return [say(KN, ev.valid ? 'map PTE ' + pg(h) + ' to frame ' + f : 'unmap PTE ' + pg(h) + ': its next access stops at the gate'), move(KN, gStand),
          call(function () {
            var p = S.framePos(f); apply(); S.pulse(GT.tray, C.kernel, false, 5); S.pulse(p, C.kernel, false, 3);
            S.beam(GT.mid, new V(p.x, 1, p.z), ev.valid ? C.kernel : C.bad);
          }), wait(0.14)];
      case 'frame':
        f = M.frameIndex(ev.pa);
        if (ev.op === 'alloc') return [say(KN, 'take free frame ' + f + ' for ' + pg(h)), move(KN, nearFrame(f)), call(function () { apply(); S.pulse(S.framePos(f), C.kernel, false, 3); }), wait(0.1)];
        var x = {}, ro = M.isRO(h) && M.pageState[h] === R.S.present, e = M.cot[h];
        out = [say(KN, ro ? 'drop RO page ' + hx(h) + ': compressed copy stays in the pool' : 'free frame ' + f), move(KN, nearFrame(f)),
          call(function () {
            x.s = S.temp('slab', S.pageColor(h), false); x.s.position.copy(S.framePos(f)); x.s.position.y = 0.62; apply();
            if (ro && e) S.pulse(S.centroid(e.chunks), C.ro, false, 6);
          }),
          { dur: 0.28, fn: function (k) { x.s.scale.setScalar(1 - 0.97 * ease(k)); x.s.position.y = 0.62 + 4 * ease(k); } },
          call(function () { S.drop(x.s); })];
        return out;
      case 'state':
        if (ev.from === 'untouched' && ev.to === 'present') {
          f = M.frameOf[h]; var z = {};
          return [say(KN, 'zero-fill a new page for ' + pg(h)),
            call(function () { z.s = S.temp('slab', C.zero, false); var p = S.framePos(f); z.s.position.set(p.x, 6, p.z); }),
            fly(function () { return z.s; }, function () { var p = S.framePos(f); p.y = 0.62; return p; }, 0.22),
            call(function () { S.drop(z.s); apply(); })];
        }
        return [say(KN, 'page ' + hx(h) + ': ' + ev.from + ' -> ' + ev.to), call(apply), wait(0.1)];
      case 'job':
        /* a briefing: both come to the job ring, the kernel hands the descriptor over and says
           what it wants; the accelerator takes it and keeps it until it reports back */
        var full = firstOf(evs, i, ev.op);
        out = [say(KN, brief(ev, !full)), move(KN, kStand)];
        if (full) out.push(move(RB, rStand), call(function () { KN.group.rotation.y = 0.95; }));
        return out.concat(sheet(C.kernel, kHands, robotTop),
          [call(function () {
            apply(); S.setOrder(C.kernel);
            RB.bubble.setText('job taken: ' + ev.op + ', tag ' + hx(ev.desc.tag));
            S.pulse(new V(RB.pos.x, RB.lift + 2 * RB.s, RB.pos.z), C.hw, false, 3);
          }), wait(full ? 0.8 : 0.22)]);
      case 'chunk':
        chunks = ev.chunks; n = chunks.length;
        if (ev.op === 'pop') {
          var nx = evs[i + 1], fail = nx && nx.ev === 'chunk' && nx.op === 'push' && job && job.op === 'COMPRESS';
          f = M.frameIndex(job.desc.frame_pa);
          if (fail) return [say(RB, 'pop ' + n + ' chunks while encoding')].concat(compressAct(job.h, f, chunks, false, apply));
          return [say(RB, 'pop ' + n + ' free chunks from the stack'), call(function () { S.pulse(towerTop(), C.hw, false, 4); }), wait(0.12)].concat(compressAct(job.h, f, chunks, true, apply));
        }
        if (ev.op === 'push') {
          var pv = evs[i - 1];
          if (pv && pv.ev === 'chunk' && pv.op === 'pop') return [say(RB, 'push the ' + n + ' chunks back'), call(apply), wait(0.15)];
          var y = {};
          return [say(RB, 'push ' + n + ' chunk numbers onto the stack'), move(RB, overChunks(chunks)),
            call(function () { y.br = chunks.map(function (c) { var b = S.temp('brick', C.sram, false); b.position.copy(S.chunkPos(c)); b.position.y = 0.4; return b; }); apply(); }),
            par(chunks.map(function (c, j) { return fly(function () { return y.br[j]; }, towerTop, 0.3 + j * 0.03, 9); })),
            call(function () { y.br.forEach(function (b) { S.drop(b); }); })];
        }
        var label = ev.op === 'reserve' ? 'bitmap: reserve ' + n + ' chunks (' + ev.words + ' word' + (ev.words > 1 ? 's' : '') + ' scanned)'
          : ev.op === 'trim' ? 'bitmap: trim ' + n + ' unused chunks' : 'bitmap: release ' + n + ' chunks';
        return [say(KN, label), move(KN, bitStand(chunks[0])),
          call(function () { apply(); S.pulse(S.bitPos(chunks[0]), ev.op === 'reserve' ? C.reserved : C.kernel, true, 4); S.pulse(S.centroid(chunks), ev.op === 'reserve' ? C.reserved : C.kernel, false, 4); }), wait(0.22)];
      case 'stack':
        if (ev.op === 'init') return [say(RB, 'INIT: ' + ev.list_chunks + ' list chunks, ' + ev.sram + ' numbers in SRAM'), call(apply), wait(0.3)];
        var w = {}, lp = S.chunkPos(ev.list_chunk), refill = ev.op === 'refill';
        return [say(RB, refill ? 'refill: +170 numbers from list chunk ' + hx(ev.list_chunk) : 'spill: 170 numbers out to list chunk ' + hx(ev.list_chunk)),
          call(function () { S.pulse(lp, C.list, false, 9); w.b = S.temp('brick', C.list, false); w.b.scale.setScalar(2.2); w.b.position.copy(refill ? lp : towerTop()); S.focus.set(lp.x / 2, 2, lp.z / 2); }),
          fly(function () { return w.b; }, refill ? towerTop : function () { return lp; }, 0.5, 14),
          call(function () { S.drop(w.b); apply(); }), wait(0.15)];
      case 'cot':
        if (ev.who === 'build') return [call(apply)];
        var valid = ev.entry.flags & 1;
        return [say(who, valid ? 'write COT[' + hx(h) + ']: ' + ev.entry.comp_len + ' B in ' + ev.entry.count + ' chunks' : 'clear COT[' + hx(h) + ']'),
          move(who, cotStand(h)), call(function () { apply(); S.pulse(S.cotPos(h), ev.who === 'hw' ? C.hw : C.kernel, true, 4); }), wait(0.16)];
      case 'cot_read':
        return [say(KN, 'read COT[' + hx(h) + ']: ' + ev.entry.comp_len + ' B in ' + ev.entry.count + ' chunks'), move(KN, cotStand(h)),
          call(function () { apply(); S.pulse(S.cotPos(h), C.kernel, true, 4); }), wait(0.16)];
      case 'done':
        if (job && job.op === 'COMPRESS' && job.desc.chunks) {
          f = M.frameIndex(job.desc.frame_pa);
          if (ev.status === 'OK') out = compressAct(job.h, f, job.desc.chunks.slice(0, Math.ceil(ev.len / M.meta.chunk)), true, apply);
          else out = compressAct(job.h, f, job.desc.chunks, false, apply, ev.status);
        } else if (job && job.op === 'DECOMPRESS' && (ev.status === 'OK' || ev.status === 'BAD_STREAM')) {
          f = M.frameIndex(job.desc.frame_pa);
          out = decompressAct(job.h, f, M.jobChunks(job), ev.status === 'OK', apply, job.desc.chunks ? null : (M.ctlb === job.h ? 'hit' : 'miss'));
        }
        /* the report: back at the job ring, the completion record goes to the kernel */
        var good = ev.status === 'OK', op = job ? job.op : '', ji = i - 1, whole;
        while (ji > 0 && evs[ji].ev !== 'job') ji--;
        whole = !job || !good || firstOf(evs, ji, op);
        if (whole) out.push(move(RB, rStand));
        return out.concat([say(RB, whole ? report(ev, job) : 'Report to KERNEL: ' + ev.status + (op === 'COMPRESS' && good ? ', ' + ev.len + ' B' : ''))],
          sheet(good ? C.ok : C.bad, robotTop, kHands),
          [call(function () {
            apply(); S.setOrder(null); KN.group.rotation.y = 0;
            KN.bubble.setText('completion read: ' + op + ' ' + ev.status);
            S.pulse(kHands(), good ? C.ok : C.bad, false, 3);
          }), wait(whole ? 0.7 : 0.2)]);
      case 'access':
        /* the gate lets the access through: the user program gets what it asked for */
        f = M.frameOf[h]; var u = S.users[ev.client] || null, fp = f >= 0 ? S.framePos(f) : null, who2 = u ? u.name : 'the program';
        if (ev.res === 'hit') {
          return [call(function () {
            apply(); S.setGate('pass'); GT.bubble.setText(lines(['PTE valid: pass to frame ' + f, 'no kernel needed']));
            if (u) u.bubble.setText(rw(ev) + ' done, no fault');
            if (fp) { S.pulse(fp, u ? u.color : 0xffffff, false, 3); through(u, fp, u ? u.color : 0xffffff); S.focus.lerp(new V(fp.x, 2, fp.z), 0.25); }
          }), wait(0.16)];
        }
        if (ev.res === 'lost') {
          return [say(KN, lines(['page ' + hx(h) + ' is LOST', who2 + ' gets an error'])), call(function () { RB.bubble.setText(''); S.setTicket(null); })]
            .concat(u ? sheet(C.bad, gTray, uHands(u)) : [],
            [call(function () { apply(); if (u) u.bubble.setText(rw(ev) + ' failed: the data is lost'); if (fp) S.pulse(fp, C.bad, false, 5); }), wait(0.7)]);
        }
        return [say(KN, lines(['page ' + hx(h) + ' is in frame ' + f, who2 + ' may run again'])),
          call(function () {
            RB.bubble.setText(''); S.setTicket(null); S.setGate('pass'); S.pulse(GT.tray, C.ok, false, 7);
            GT.bubble.setText('PTE valid now: pass to frame ' + f); S.focus.set(u ? u.pos.x * 0.4 : 0, 2, S.zGate);
          })]
          .concat(u ? sheet(C.ok, gTray, uHands(u)) : [],
          [call(function () {
            apply(); if (fp) S.pulse(fp, u ? u.color : C.ok, false, 5);
            if (u) { through(u, fp, u.color); u.bubble.setText(rw(ev) + ' done' + (ev.lat_ns ? ', waited ' + (ev.lat_ns / 1000).toFixed(2) + ' us' : '')); }
          }), wait(0.55), move(KN, kHome), wait(0.25)]);   /* its work is done: the kernel leaves the gate */
      case 'inject':
        return [call(function () { apply(); S.pulse(S.chunkPos(ev.chunk), C.bad, false, 8); }), wait(0.3)];
    }
    return [call(apply)];
  };
};

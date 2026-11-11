/* Replay model: rebuilds the machine state from trace events.
   Every mutation goes through R.apply(ev); the scene only reads this state. */
var R = {};

R.K = { FREE: 0, SRAM: 1, LISTED: 2, LIST: 3, RESERVED: 4, RO: 5, RW: 6 };
R.S = { compressed: 0, present: 1, untouched: 2, compressing: 3, decompressing: 4, lost: 5 };
R.S_NAME = ['compressed', 'present', 'untouched', 'compressing', 'decompressing', 'lost'];

R.hex = function (v, w) { return '0x' + (v >>> 0).toString(16).toUpperCase().padStart(w || 0, '0'); };

R.Model = function (run) {
  var m = run.meta;
  this.meta = m;
  this.variant = m.variant;
  /* user programs: each owns a slice of the .data, heap and RO page ranges */
  this.clients = m.clients || [];
  this.owner = new Int8Array(m.pages).fill(-1);
  for (var i = 0; i < this.clients.length; i++) {
    var c = this.clients[i], rs = [c.data, c.heap, c.ro];
    for (var j = 0; j < rs.length; j++) if (rs[j]) this.owner.fill(i, rs[j][0], rs[j][1]);
  }
  this.reset();
};

R.Model.prototype.reset = function () {
  var m = this.meta, K = R.K;
  this.pageState = new Uint8Array(m.pages);
  for (var h = 0; h < m.rw_pages; h++) this.pageState[h] = R.S.untouched;
  this.frameOf = new Int32Array(m.pages).fill(-1);
  this.frameOwner = new Int32Array(m.frames).fill(-1);
  this.mapped = new Uint8Array(m.pages);
  this.filled = new Uint8Array(m.frames);
  this.chunkKind = new Uint8Array(m.pool_chunks);
  this.chunkOwner = new Int32Array(m.pool_chunks).fill(-1);
  this.kindCount = [m.pool_chunks, 0, 0, 0, 0, 0, 0];
  this.cot = new Array(m.pages).fill(null);
  this.sram = new Set();
  this.listed = new Map();
  this.pendingSpill = new Set();
  this.listHead = -1;
  this.listCount = 0;
  this.cursorWord = -1;
  this.freeFrames = m.frames;
  this.lastJob = null;
  this.lastDone = null;
  this.ctlb = -1;
  this.t = 0;
  this.n = { access: 0, hit: 0, first: 0, fault: 0, lost: 0, jobs: 0, compress: 0, decompress: 0,
             invalidate: 0, incompressible: 0, roDrop: 0, refill: 0, spill: 0, cotHw: 0, cotKernel: 0 };
  this.served = this.clients.map(function () { return 0; });
  this.dirty = { chunks: [], frames: [], cot: [], all: true };
};

R.Model.prototype.setKind = function (c, k, owner) {
  var old = this.chunkKind[c];
  if (old !== k) { this.kindCount[old]--; this.kindCount[k]++; this.chunkKind[c] = k; }
  this.chunkOwner[c] = owner === undefined ? -1 : owner;
  this.dirty.chunks.push(c);
};

R.Model.prototype.freeChunks = function () {
  var k = this.kindCount, K = R.K;
  return k[K.FREE] + k[K.SRAM] + k[K.LISTED] + k[K.LIST];
};

R.Model.prototype.frameIndex = function (pa) { return (pa - this.meta.fc_base) / this.meta.page; };
R.Model.prototype.isRO = function (h) { return h >= this.meta.ro_first; };
R.Model.prototype.clientOf = function (h) { return h >= 0 && h < this.owner.length ? this.owner[h] : -1; };

/* The chunks a DECOMPRESS job reads: from the descriptor (software) or the COT entry (baseline). */
R.Model.prototype.jobChunks = function (job) {
  if (job.desc.chunks) return job.desc.chunks;
  var e = this.cot[job.h];
  return e ? e.chunks : [];
};

R.Model.prototype.apply = function (ev) {
  var m = this.meta, K = R.K, S = R.S, i, c, h, f, n = this.n;
  this.t = ev.t;
  switch (ev.ev) {
    case 'cot':
      h = ev.h;
      if (ev.entry.flags & 1) {
        this.cot[h] = ev.entry;
        if (ev.who === 'build') for (i = 0; i < ev.entry.chunks.length; i++) this.setKind(ev.entry.chunks[i], K.RO, h);
      } else {
        this.cot[h] = null;
      }
      if (ev.who === 'hw') { n.cotHw++; this.ctlb = (ev.entry.flags & 1) ? h : -1; }
      if (ev.who === 'kernel') n.cotKernel++;
      this.dirty.cot.push(h);
      break;
    case 'stack':
      if (ev.op === 'init') {
        var g = m.list_group, total = m.pool_chunks, rest = ev.free % g;
        for (c = total - rest; c < total; c++) { this.sram.add(c); this.setKind(c, K.SRAM); }
        for (i = 0; i < ev.list_chunks; i++) {
          var lc = ev.first_free + i * g, nums = [];
          this.setKind(lc, K.LIST);
          for (c = lc + 1; c < lc + g; c++) { nums.push(c); this.setKind(c, K.LISTED); }
          this.listed.set(lc, nums);
        }
        this.listHead = ev.list_head; this.listCount = ev.list_chunks;
      } else if (ev.op === 'refill') {
        var nums2 = this.listed.get(ev.list_chunk) || [];
        for (i = 0; i < nums2.length; i++) { this.sram.add(nums2[i]); this.setKind(nums2[i], K.SRAM); }
        this.sram.add(ev.list_chunk); this.setKind(ev.list_chunk, K.SRAM);
        this.listed.delete(ev.list_chunk);
        this.listHead = ev.list_head; this.listCount = ev.list_chunks; n.refill++;
      } else if (ev.op === 'spill') {
        var all = [ev.list_chunk].concat(ev.numbers || []);
        for (i = 0; i < all.length; i++) {
          c = all[i];
          if (this.sram.has(c)) this.sram.delete(c); else this.pendingSpill.add(c);
          this.setKind(c, i === 0 ? K.LIST : K.LISTED);
        }
        this.listed.set(ev.list_chunk, ev.numbers || []);
        this.listHead = ev.list_chunk; this.listCount = ev.list_chunks; n.spill++;
      }
      break;
    case 'bitmap':
      this.cursorWord = Math.floor((m.pool_chunks - ev.free) / 64);
      break;
    case 'frame':
      f = this.frameIndex(ev.pa); h = ev.h;
      if (ev.op === 'alloc') { this.frameOf[h] = f; this.frameOwner[f] = h; this.filled[f] = 0; this.freeFrames--; }
      else { this.frameOf[h] = -1; this.frameOwner[f] = -1; this.filled[f] = 0; this.freeFrames++; }
      this.dirty.frames.push(f);
      break;
    case 'state':
      h = ev.h;
      this.pageState[h] = S[ev.to];
      f = this.frameOf[h];
      if (ev.from === 'untouched' && ev.to === 'present' && f >= 0) this.filled[f] = 1;
      if (ev.from === 'present' && ev.to === 'compressed' && this.isRO(h)) n.roDrop++;
      if (f >= 0) this.dirty.frames.push(f);
      this.dirty.cot.push(h);
      break;
    case 'pte':
      this.mapped[ev.h] = ev.valid;
      f = this.frameOf[ev.h];
      if (f >= 0) this.dirty.frames.push(f);
      break;
    case 'job':
      h = ev.desc.handle !== undefined ? ev.desc.handle : ev.desc.tag;
      this.lastJob = { op: ev.op, desc: ev.desc, h: h, hex: ev.hex, n: ev.n };
      n.jobs++;
      if (ev.op === 'COMPRESS') n.compress++;
      if (ev.op === 'DECOMPRESS') n.decompress++;
      if (ev.op === 'INVALIDATE') n.invalidate++;
      break;
    case 'chunk':
      if (ev.op === 'pop') {
        for (i = 0; i < ev.chunks.length; i++) { c = ev.chunks[i]; this.sram.delete(c); this.setKind(c, K.RW, this.lastJob ? this.lastJob.h : -1); }
      } else if (ev.op === 'push') {
        for (i = 0; i < ev.chunks.length; i++) {
          c = ev.chunks[i];
          if (this.pendingSpill.has(c)) { this.pendingSpill.delete(c); this.chunkOwner[c] = -1; }
          else { this.sram.add(c); this.setKind(c, K.SRAM); }
        }
      } else if (ev.op === 'reserve') {
        for (i = 0; i < ev.chunks.length; i++) this.setKind(ev.chunks[i], K.RESERVED);
        this.cursorWord = ev.chunks[ev.chunks.length - 1] >> 6;
      } else {  /* trim, release */
        for (i = 0; i < ev.chunks.length; i++) this.setKind(ev.chunks[i], K.FREE);
      }
      break;
    case 'done':
      this.lastDone = ev;
      var job = this.lastJob;
      if (ev.status === 'INCOMPRESSIBLE') n.incompressible++;
      if (job && ev.status === 'OK') {
        if (job.op === 'COMPRESS' && job.desc.chunks) {
          var used = Math.ceil(ev.len / m.chunk);
          for (i = 0; i < used; i++) this.setKind(job.desc.chunks[i], K.RW, job.h);
        }
        if (job.op === 'DECOMPRESS') {
          f = this.frameIndex(job.desc.frame_pa);
          this.filled[f] = 1; this.dirty.frames.push(f);
          if (!job.desc.chunks) this.ctlb = job.h;
        }
      }
      break;
    case 'access':
      n.access++;
      n[ev.res] = (n[ev.res] || 0) + 1;
      if (this.served[ev.client] !== undefined) this.served[ev.client]++;
      break;
  }
};

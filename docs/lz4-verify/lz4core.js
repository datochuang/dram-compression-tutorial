/* LZ4 block codec with trace, ported from the reference byU16 path (inputs under 64 KB). */
var LZ4Core = (function () {
  var MINMATCH = 4, MFLIMIT = 12, LASTLITERALS = 5, HASHLOG = 13, SKIP = 6;

  function read32(b, i) { return (b[i] | (b[i + 1] << 8) | (b[i + 2] << 16) | (b[i + 3] << 24)) >>> 0; }
  function hash4(v) { return (Math.imul(v, 2654435761 | 0) >>> 0) >>> (32 - HASHLOG); }

  function compress(src, wantTrace) {
    var n = src.length, out = [], seqs = [], ev = [];
    var table = new Uint16Array(1 << HASHLOG);
    var anchor = 0, ip = 0;
    var mflimitPlusOne = n - MFLIMIT + 1, matchlimit = n - LASTLITERALS;

    function emitLen(extra) {
      while (extra >= 255) { out.push(255); extra -= 255; }
      out.push(extra);
    }
    function lastLiterals() {
      var run = n - anchor, tokPos = out.length;
      if (run >= 15) { out.push(0xF0); emitLen(run - 15); } else { out.push(run << 4); }
      var litPos = out.length;
      for (var i = anchor; i < n; i++) out.push(src[i]);
      seqs.push({ tokPos: tokPos, litPos: litPos, litLen: run, litSrc: anchor, last: true, end: out.length });
      if (wantTrace) ev.push({ t: 'last', anchor: anchor, run: run, outLen: out.length });
    }

    if (n >= MFLIMIT + 1) {
      var h0 = hash4(read32(src, 0));
      table[h0] = 0;
      if (wantTrace) ev.push({ t: 'put', pos: 0, h: h0, why: 'first' });
      ip = 1;
      var forwardH = hash4(read32(src, ip));
      var done = false;
      main: for (;;) {
        var forwardIp = ip, step = 1, searchMatchNb = 1 << SKIP, match, h;
        for (;;) {
          h = forwardH;
          var current = forwardIp, matchIndex = table[h];
          ip = forwardIp;
          var usedStep = step;
          forwardIp += step;
          step = searchMatchNb++ >> SKIP;
          if (forwardIp > mflimitPlusOne) { done = true; break main; }
          match = matchIndex;
          forwardH = hash4(read32(src, forwardIp));
          table[h] = current;
          var hit = read32(src, match) === read32(src, ip);
          if (wantTrace) ev.push({ t: 'probe', ip: ip, h: h, cand: matchIndex, hit: hit, step: usedStep, next: forwardIp });
          if (hit) break;
        }
        var ipBefore = ip;
        while (ip > anchor && match > 0 && src[ip - 1] === src[match - 1]) { ip--; match--; }
        if (wantTrace && ip !== ipBefore) ev.push({ t: 'catchup', from: ipBefore, ip: ip, match: match });
        if (wantTrace) ev.push({ t: 'back0', ip: ip, match: match, anchor: anchor, why: ip <= anchor ? 'anchor' : (match <= 0 ? 'start' : 'diff') });

        var pendingLit = ip - anchor, litStart = anchor;
        for (;;) {
          var tokPos = out.length;
          out.push(0);
          var tokHi = 0;
          if (pendingLit >= 15) { tokHi = 15; emitLen(pendingLit - 15); } else { tokHi = pendingLit; }
          var litPos = out.length;
          for (var i = 0; i < pendingLit; i++) out.push(src[litStart + i]);
          if (wantTrace) ev.push({ t: 'tok', tokPos: tokPos, tokHi: tokHi, litLen: pendingLit, litStart: litStart, ip: ip, match: match, outLen: out.length });
          var offPos = out.length, offset = ip - match;
          out.push(offset & 255, offset >> 8);
          if (wantTrace) ev.push({ t: 'off', offPos: offPos, offset: offset, ip: ip, match: match, outLen: out.length });
          var c = ip + MINMATCH, m = match + MINMATCH;
          for (;;) {
            if (c >= matchlimit) { if (wantTrace) ev.push({ t: 'ext', ip: ip, match: match, c: c, m: m, eq: false, limit: true }); break; }
            var same = src[c] === src[m];
            if (wantTrace) ev.push({ t: 'ext', ip: ip, match: match, c: c, m: m, eq: same, limit: false });
            if (!same) break;
            c++; m++;
          }
          var matchLen = c - ip, code = matchLen - MINMATCH, mlPos = out.length, tokLo;
          if (code >= 15) { tokLo = 15; emitLen(code - 15); } else { tokLo = code; }
          out[tokPos] = (tokHi << 4) | tokLo;
          seqs.push({ tokPos: tokPos, litPos: litPos, litLen: pendingLit, litSrc: litStart, offPos: offPos, offset: offset, mlPos: mlPos, matchLen: matchLen, matchSrc: match, matchDst: ip, end: out.length, last: false });
          if (wantTrace) ev.push({ t: 'emit', seq: seqs.length - 1, ip: ip, match: match, matchLen: matchLen, litLen: pendingLit, litStart: litStart, outLen: out.length });
          ip += matchLen;
          anchor = ip;
          if (ip >= mflimitPlusOne) break main;
          var hp = hash4(read32(src, ip - 2));
          table[hp] = ip - 2;
          if (wantTrace) ev.push({ t: 'put', pos: ip - 2, h: hp, why: 'fill' });
          var hn = hash4(read32(src, ip));
          var cand = table[hn];
          table[hn] = ip;
          var again = read32(src, cand) === read32(src, ip);
          if (wantTrace) ev.push({ t: 'probe', ip: ip, h: hn, cand: cand, hit: again, step: 0 });
          if (again) { match = cand; pendingLit = 0; litStart = ip; continue; }
          break;
        }
        ip++;
        forwardH = hash4(read32(src, ip));
      }
    }
    lastLiterals();
    return { out: Uint8Array.from(out), seqs: seqs, events: ev };
  }

  function decompress(buf, maxOut, wantTrace) {
    var out = [], ev = [], ip = 0, limit = maxOut === undefined ? 1 << 24 : maxOut;
    function fail(msg) { var e = new Error(msg); e.at = ip; throw e; }
    if (buf.length === 0) fail('empty block');
    for (;;) {
      var tokPos = ip, token = buf[ip++], lit = token >> 4, b;
      if (lit === 15) { do { if (ip >= buf.length) fail('literal length runs past the input'); b = buf[ip++]; lit += b; } while (b === 255); }
      if (ip + lit > buf.length) fail('literals run past the input');
      if (out.length + lit > limit) fail('output buffer overflow');
      var litPos = ip, opLit = out.length;
      for (var i = 0; i < lit; i++) out.push(buf[ip++]);
      if (wantTrace) ev.push({ t: 'lit', tokPos: tokPos, token: token, litPos: litPos, litLen: lit, op: opLit });
      if (ip === buf.length) break;
      if (ip + 2 > buf.length) fail('offset runs past the input');
      var offPos = ip, offset = buf[ip] | (buf[ip + 1] << 8);
      ip += 2;
      if (offset === 0) fail('offset 0 is invalid');
      if (offset > out.length) fail('offset points before the start of the output');
      var ml = token & 15, mlPos = ip;
      if (ml === 15) { do { if (ip >= buf.length) fail('match length runs past the input'); b = buf[ip++]; ml += b; } while (b === 255); }
      ml += MINMATCH;
      if (out.length + ml > limit) fail('output buffer overflow');
      var op = out.length, from = op - offset;
      for (var j = 0; j < ml; j++) out.push(out[from + j]);
      if (wantTrace) ev.push({ t: 'match', tokPos: tokPos, token: token, offPos: offPos, offset: offset, mlPos: mlPos, matchLen: ml, op: op, from: from, end: ip });
    }
    return { out: Uint8Array.from(out), events: ev };
  }

  function encodeLengthExample(n, isMatch) {
    var v = isMatch ? n - MINMATCH : n, ext = [], nib;
    if (v < 15) { nib = v; } else { nib = 15; v -= 15; while (v >= 255) { ext.push(255); v -= 255; } ext.push(v); }
    return { nibble: nib, ext: ext };
  }

  function bound(n) { return n + Math.floor(n / 255) + 16; }

  function rng(seed) { var s = seed >>> 0; return function () { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s; }; }

  var WORDS = 'memory page cache line store load read write frame table entry pointer buffer kernel process thread queue block index value count state lock free list node data size next prev flag map hash the and for with from into when this that each must will'.split(' ');

  function samples(size) {
    var i, r, z = new Uint8Array(size);
    var t = [], rr = rng(12345);
    while (t.length < size) { var w = WORDS[rr() % WORDS.length]; for (i = 0; i < w.length; i++) t.push(w.charCodeAt(i)); t.push(rr() % 11 === 0 ? 10 : 32); }
    var text = Uint8Array.from(t.slice(0, size));
    var p = new Uint8Array(size); r = rng(777);
    var base = 0x7f12340000, a = base;
    for (i = 0; i + 8 <= size; i += 8) {
      a += 16 * ((r() % 6) + 1);
      var lo = a % 4294967296, hi = Math.floor(a / 4294967296);
      p[i] = lo & 255; p[i + 1] = (lo >>> 8) & 255; p[i + 2] = (lo >>> 16) & 255; p[i + 3] = (lo >>> 24) & 255;
      p[i + 4] = hi & 255; p[i + 5] = (hi >>> 8) & 255;
    }
    var rand = new Uint8Array(size); r = rng(424242);
    for (i = 0; i < size; i++) rand[i] = r() & 255;
    return { zero: z, text: text, pointers: p, random: rand };
  }

  return { compress: compress, decompress: decompress, encodeLengthExample: encodeLengthExample, bound: bound, samples: samples, hash4: hash4, read32: read32 };
})();
if (typeof module !== 'undefined') module.exports = LZ4Core;

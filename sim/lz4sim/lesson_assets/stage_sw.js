/* The stage of the software-leaning lessons, shared by the scenes "compress-sw" (COMPRESS of
   one RW page) and "decompress-sw" (the same page coming back: one DECOMPRESS job).
   A scene's steps file decides what happens on it.

   stage_base.js builds what both designs have. This file gives it the format of this design's
   descriptor (48 B, the chunk numbers are in it) and adds what only this design has on stage:
   the free-chunk bitmap of KERNEL SW. It lies in the nearest row beside the COT entry, because
   here both are the kernel's books: LZ4 HW has no stack and never goes to that row. */
(function () {
'use strict';
var hx = R.hx, D = R.LD.D, M = R.LD.M, BM = D.bitmap, B0 = BM.first_chunk;
var TILES = D.tiles || D.chunks, WIDE = TILES.length > 4;
var DSC = { x: -20, w: 30, y: 4.6, tilt: 0.55 }, DNE = { x: 21, w: 24, y: 3.5, tilt: 0.7 }, COT = { x: 20, w: 34 };
var BMX = -20, BMW = 30;

var L = R.stage({
  F: {
    desc: { title: 'JOB DESCRIPTOR · 48 B · one slot of the job ring', cell: 55,
            rows: [[['opcode', 0, 1], ['count', 1, 1], ['limit', 2, 2], ['frame_pa', 4, 4], ['comp_len', 8, 2], ['flags', 10, 2], ['checksum', 12, 4]],
                   [['tag', 16, 4]].concat([0, 1, 2, 3].map(function (i) { return ['chunk[' + i + ']', 20 + 3 * i, 3]; })),
                   [4, 5, 6, 7].map(function (i) { return ['chunk[' + i + ']', 20 + 3 * i, 3]; }).concat([['pad', 44, 4]])] }
  },
  tiles: TILES, tileW: WIDE ? 6.4 : 7.6, zcot: 32,
  desc: DSC, done: DNE, cot: COT, bellX: -2, irqX: 6,
  chunkTaken: ['reserved', 'by KERNEL SW', '#f4d35e'],
  P: function (g) {
    return {
      k_home: [-41, -4], k_frame: [-35.5, 1], k_desc: [DSC.x - DSC.w / 2 - 3.5, g.ZDESK], k_bell: [-7, -22], k_done: [DNE.x - DNE.w / 2 - 3.5, g.ZDESK],
      k_bm: [BMX + 9, g.ZCOT - 11.5], k_cot: [COT.x, g.ZCOT - 14.5], k_tiles: [(g.CX[0] + g.CX[g.CX.length - 1]) / 2, g.ZROW - 7.5],
      h_home: [44, -9], h_desc: [DSC.x + DSC.w / 2 + 3.5, g.ZDESK], h_done: [DNE.x + DNE.w / 2 + 3.5, g.ZDESK]
    };
  },
  VIEW: function (g) {
    var c0 = g.CX[0], c1 = g.CX[g.CX.length - 1];
    return {
      all: { t: [WIDE ? 6 : 2, 0, -1], w: WIDE ? 104 : 92, v: 94, ph: 0.72 },
      desc: { t: [DSC.x - 2, 4, g.ZDESK - 1], w: 42, v: 30, ph: 0.74 },
      desk: { t: [0, 3, g.ZDESK - 2], w: 86, v: 38, ph: 0.8 },
      read: { t: [DSC.x + 2.5, 4, g.ZDESK - 1], w: 42, v: 30, ph: 0.74 },
      kread: { t: [DNE.x - 3, 3, g.ZDESK - 1], w: 40, v: 27, ph: 0.74 },
      done: { t: [DNE.x + 2, 3, g.ZDESK - 1], w: 40, v: 27, ph: 0.74 },
      work: { t: [(c1 - 14) / 2, 1, 5], w: c1 + 14 + 12, v: 34, ph: 0.7 },
      chunks: { t: [(c0 + c1) / 2, 1, 2], w: c1 - c0 + 20, v: 34, ph: 0.72 },
      bitmap: { t: [BMX + 5, 1, g.ZCOT - 3], w: 46, v: 30, ph: 0.5 },
      cot: { t: [COT.x - 4, 1, g.ZCOT - 3.5], w: 46, v: 37, ph: 0.5 },
      books: { t: [0, 1, g.ZCOT - 4], w: 82, v: 38, ph: 0.52 },
      near: { t: [WIDE ? 9 : 4, 0, 19], w: WIDE ? 98 : 82, v: 56, ph: 0.6 }
    };
  }
});
var kit = L.kit, txt = L.txt, ZB = L.ZCOT - 2.6;

/* ---- the free-chunk bitmap: one 64-bit word of it, the word this job changes */
var PW = 1024, PH = 452, bmP = kit.plate({ w: BMW, pw: PW, ph: PH, x: BMX, z: ZB });
kit.label('kernel memory · ' + BM.nwords + ' words · LZ4 HW never sees it', BMX, 0.7, ZB + BMW * PH / PW / 2 + 1.6, 1.2, '#f4d35e');
kit.label('in DRAM · written and read by KERNEL SW only', COT.x, 0.7, L.ZCOT + 11.2, 1.2, '#f4d35e');
function bitsOf(hex) { var o = [], i; for (i = 0; i < 64; i++) o.push((parseInt(hex.charAt(15 - (i >> 2)), 16) >> (i & 3)) & 1); return o; }
function drawBitmap(S) {
  /* S.bm: { word: 16 hex digits, mark: { bit: 's' set by the kernel in this lesson | 'c' cleared by it }, hot: [bits], free } */
  var p = bmP, c = p.ctx, s = S.bm, bits = bitsOf(s.word), i, x, y, m, hot, X0 = 152, CW = 52, Y0 = 136, RH = 62;
  c.fillStyle = '#0f1822'; c.fillRect(0, 0, PW, PH);
  c.strokeStyle = s.hot.length ? '#ffffff' : '#3a5068'; c.lineWidth = 6; c.strokeRect(3, 3, PW - 6, PH - 6);
  txt(p, 'FREE-CHUNK BITMAP of KERNEL SW · 1 bit per chunk', 30, 44, 30, '#9fb4cc');
  txt(p, 'word ' + BM.word + ' of ' + BM.nwords + ' · chunks ' + hx(B0) + ' to ' + hx(B0 + 63) + ' · 1 = in use, 0 = free', 30, 82, 24, '#8ea2b6', 500);
  for (i = 0; i < 16; i++) txt(p, '+' + i.toString(16).toUpperCase(), X0 + i * CW + CW / 2, 122, 21, '#8ea2b6', 500, 'center');
  for (i = 0; i < 64; i++) {
    x = X0 + (i & 15) * CW; y = Y0 + (i >> 4) * RH; m = s.mark[i]; hot = s.hot.indexOf(i) >= 0;
    if (!(i & 15)) txt(p, hx(B0 + i), 30, y + 40, 27, '#8ea2b6');
    c.fillStyle = m === 's' ? '#f4d35e' : bits[i] ? '#3a5068' : '#18222d'; c.fillRect(x + 3, y + 3, CW - 6, RH - 8);
    if (m === 'c') { c.strokeStyle = '#f4d35e'; c.lineWidth = 4; c.strokeRect(x + 5, y + 5, CW - 10, RH - 12); }
    if (hot) { c.strokeStyle = '#ffffff'; c.lineWidth = 4; c.strokeRect(x + 2, y + 2, CW - 4, RH - 6); }
    txt(p, '' + bits[i], x + CW / 2, y + 42, 32, m === 's' ? '#10161d' : m === 'c' ? '#f4d35e' : bits[i] ? '#dfe8f1' : '#5d6f82', 700, 'center');
  }
  txt(p, 'word ' + BM.word + ' = 0x' + s.word.toUpperCase(), 30, PH - 28, 27, '#dfe8f1');
  txt(p, 'free chunks: ' + s.free + ' of ' + M.pool_chunks, PW - 30, PH - 28, 27, '#f4d35e', 600, 'right');
  p.done();
}
L.more = function (S) { drawBitmap(S); };
L.KEEP.bitmap = L.rect(BMX, ZB, BMW + 1, BMW * PH / PW + 1, 0.4);
L.bitAt = function (n) {           /* where the bit of chunk n is in the world */
  var i = n - B0, cx = 152 + (i & 15) * 52 + 26, cy = 136 + (i >> 4) * 62 + 30;
  return new THREE.Vector3(BMX + (cx / PW - 0.5) * BMW, 1, ZB + (cy / PH - 0.5) * BMW * PH / PW);
};
L.B0 = B0;
L.descAt = new THREE.Vector3(DSC.x, DSC.y + 1.5, -15);   /* above the descriptor slab */
R.L = L;
})();

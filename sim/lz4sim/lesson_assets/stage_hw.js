/* The stage of the hardware-leaning lessons, shared by the scenes "compress-hw" (COMPRESS of
   one RW page) and "decompress-hw" (the same page coming back: DECOMPRESS, then INVALIDATE).
   A scene's steps file decides what happens on it.

   stage_base.js builds what both designs have. This file gives it the formats of this design
   (16 B descriptor that names the page by its handle) and adds the one thing only this design
   has on stage: the free-chunk stack in the SRAM of LZ4 HW. */
(function () {
'use strict';
var hx = R.hx, D = R.LD.D;
var DEC = D.scene === 'decompress-hw', STOP = DEC ? D.stack.size_after : D.stack.size_before;

var L = R.stage({
  F: {
    desc: { title: 'JOB DESCRIPTOR · 16 B · one slot of the job ring', cell: 104,
            rows: [[['opcode', 0, 1], ['flags', 1, 1], ['limit', 2, 2], ['handle', 4, 4]], [['frame_pa', 8, 4], ['tag', 12, 4]]] }
  },
  freeText: DEC ? 'free again' : 'free',
  P: function (g) { return { h_stack: [g.XS - 8, -9] }; }
});
var kit = L.kit, XS = L.XS;

/* ---- the free-chunk stack */
var plates = D.stack.top.map(function (n, i) {
  var y = 0.5 + (D.stack.top.length - 1 - i) * 1.0, m = kit.box(7, 0.86, 3.2, R.COL.sram, XS, y, -9);
  var t = kit.label(hx(n), XS, y, -7.2, 0.9, '#e9fbff'); return { m: m, t: t, y: y };
});
kit.label('FREE-CHUNK STACK', XS + 1, 0.7, -5.4, 1.2);
kit.label('in the SRAM of LZ4 HW', XS + 1, 0.7, -3.6, 1.1);
var stackLab = kit.label('', XS + 1, 0.7, -1.8, 1.2, '#b48cff');
L.KEEP.stack = [[XS - 4, 0, -9], [XS + 4, 0, -7], [XS - 4, 9, -9], [XS + 4, 9, -9], [XS - 6, 0.5, -1], [XS + 8, 0.5, -1]];
L.plates = plates;
L.more = function (S) {
  plates.forEach(function (p, k) { p.m.visible = p.t.visible = k >= S.stack.pop; p.m.material.color.setHex(k === S.stack.pop && S.stack.hot ? 0x36d6e7 : R.COL.sram); });
  stackLab.setText((STOP - S.stack.pop) + (DEC ? ' numbers' : ' numbers left'));
};
R.L = L;
})();

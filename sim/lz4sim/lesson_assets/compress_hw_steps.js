/* Lesson scene "compress-hw": the steps. Each step names who acts (user SW, kernel, hardware),
   says in the panel what happens and why, and changes the state: bytes written, bytes read,
   who stands where and says what. Prose is zh-TW; what is drawn on the stage is English. */
(function () {
'use strict';
var L = R.L, D = L.D, M = L.M, V = L.V, H = L.H, hx = R.hx, kit = L.kit, A = L.A, T = THREE, NCH = L.NCH;
var K = L.KEEP, RQ = D.req, RH = hx(RQ.h), SL = D.stream.len, LAST = D.stream.sizes[NCH - 1], CK = hx(D.cot.checksum, 8);
var bDesc = R.bytes(D.desc.hex), bCot = R.bytes(D.cot.after), bDone = R.bytes(D.done.hex);
var c = function (s) { return '<code>' + s + '</code>'; };
var hexOf = function (arr, a, n) { return arr.slice(a, a + n).map(R.b2).join(' '); };
var fill = function (n, v) { var a = [], i; for (i = 0; i < n; i++) a.push(v); return a; };

var init = {
  pos: { kernel: 'k_home', hw: 'h_home', req: 'ui_home' }, say: {}, gate: 'idle', card: null, final: false,
  pte: { valid: 1, st: 'present', hot: false, w: false }, free: D.frames.free_before,
  frame: { st: 'present', hot: false },
  desc: { b: fill(16, null), w: fill(16, null), r: fill(16, ''), vals: {}, hot: [] },
  cot: { b: R.bytes(D.cot.before), w: fill(32, null), r: fill(32, ''), vals: {}, hot: [] },
  done: { b: fill(16, null), w: fill(16, null), r: fill(16, ''), vals: {}, hot: [] },
  bell: 0, irq: 0, eng: { on: 0, segs: 0 }, stack: { pop: 0, hot: false }, ch: fill(NCH, 0), chHot: -1,
  led: {}, clk: { on: false, dram: 0, lz: 0 }
};
var SRC = { desc: bDesc, cot: bCot, done: bDone };
function put(S, key, vals, who) {
  var s = S[key]; s.hot = Object.keys(vals);
  L.F[key].fields.forEach(function (f) {
    if (!(f[0] in vals)) return;
    var i; for (i = 0; i < f[2]; i++) { s.b[f[1] + i] = SRC[key][f[1] + i]; s.w[f[1] + i] = who; }
    s.vals[f[0]] = vals[f[0]];
  });
}
function readAll(S, key, who) { S[key].r = S[key].r.map(function () { return who; }); }
function led(S, id, who, mark) { var r = S.led[id] = S.led[id] || {}, v = r[who] || ''; if (v.indexOf(mark) < 0) r[who] = v ? v + ' ' + mark : mark; }
function calm(S) { S.desc.hot = []; S.cot.hot = []; S.done.hot = []; S.pte.hot = false; S.frame.hot = false; S.stack.hot = false; S.chHot = -1; S.eng.on = 0; }
function at(p, y) { return new T.Vector3(L.P[p][0], y || 2, L.P[p][1]); }

var descCard = function (S) { return L.structCard('desc', S, 'Job descriptor <span>(16 B in DRAM, job ring)</span>'); };
var cotCard = function (S) { return L.structCard('cot', S, 'COT[' + H + '] <span>(32 B in DRAM @' + hx(V.entry_pa) + ')</span>'); };
var doneCard = function (S) { return L.structCard('done', S, 'Completion <span>(16 B in DRAM, completion ring)</span>'); };
var steps = [];
function step(o) { var ap = o.apply; o.apply = function (S) { calm(S); S.card = steps.indexOf(o); ap(S); }; steps.push(o); }

/* ---- 0: why this job exists */
var glossary = function () { return L.tableCard('Words used in this lesson', [
    ['page', '軟體看到的 ' + M.page + ' B 記憶體單位，用編號（handle）稱呼'],
    ['frame', 'DRAM 裡一塊 ' + M.page + ' B 的空間，放一個未壓縮的 page'],
    ['chunk', 'DRAM 裡 ' + M.chunk + ' B 的小塊，放壓縮後的資料'],
    ['PTE', 'page table entry，決定 user SW 的存取能不能直接通過'],
    ['COT', 'compressed object table，每個 page 一筆 32 B，記壓縮後的資料在哪些 chunk'],
    ['descriptor', 'kernel 寫給 LZ4 HW 的工作單，16 B'],
    ['completion', 'LZ4 HW 回報結果的單子，16 B']]); };
step({ who: 'note', title: '\u821e\u53f0\u4e0a\u6709\u8ab0\u3001\u6709\u4ec0\u9ebc', cam: L.VIEW.all, card: glossary,
  text: '<p>\u9019\u4e00\u8ab2\u7528\u4e00\u500b\u771f\u5be6\u7684\u4f8b\u5b50\uff0c\u770b\u300c\u58d3\u7e2e\u4e00\u500b page\u300d\u5f9e\u982d\u5230\u5c3e\u767c\u751f\u7684\u4e8b\u3002\u6240\u6709\u6578\u5b57\u90fd\u4f86\u81ea simulator \u7684\u540c\u4e00\u6b21\u57f7\u884c\u3002</p>'
    + '<p>\u4e09\u7a2e\u89d2\u8272\uff1a<b>USER SW</b>\uff08\u9060\u7aef\u7684 ' + M.clients.join('\u3001') + '\uff09\u662f\u88ab\u670d\u52d9\u7684\u7a0b\u5f0f\uff0c\u53ea\u7ba1\u8b80\u5beb\u81ea\u5df1\u7684 page\u3002<b class="k">KERNEL SW</b>\uff08\u9ec3\u8272\uff09\u7ba1\u7406\u8a18\u61b6\u9ad4\u3002<b class="h">LZ4 HW</b>\uff08\u7d2b\u8272\u6a5f\u5668\u4eba\uff09\u662f\u786c\u9ad4\u52a0\u901f\u5668\uff0c\u8ca0\u8cac\u58d3\u7e2e\u8207\u89e3\u58d3\u7e2e\u3002</p>'
    + '<p>\u821e\u53f0\u7531\u9060\u5230\u8fd1\uff1a\u6700\u9060\u662f user SW \u548c\u5b83\u5011\u5171\u7528\u7684 access gate\uff1b\u4e2d\u9593\u662f kernel \u548c\u786c\u9ad4\u4e92\u76f8\u7559\u8a00\u7684\u5169\u5f35\u55ae\u5b50\uff0cdescriptor \u548c completion\uff1b\u518d\u4f86\u662f DRAM \u88e1\u7684 frame \u548c chunk\uff1b\u6700\u9760\u8fd1\u4f60\u7684\u662f COT \u7684\u4e00\u7b46\u3002</p>'
    + '<p>\u9019\u4e00\u8ab2\u53ea\u8ddf\u8457<b>\u4e00\u500b page \u7684\u58d3\u7e2e</b>\u8d70\u5b8c\uff0c\u770b\u6bcf\u4e00\u500b byte \u662f\u8ab0\u5beb\u7684\u3001\u8ab0\u8b80\u7684\u3002\u6309 Next \u4e00\u6b65\u4e00\u6b65\u770b\uff0c\u756b\u9762\u53ef\u4ee5\u62d6\u66f3\u65cb\u8f49\u3001\u6efe\u8f2a\u7e2e\u653e\u3002</p>',
  apply: function (S) { S.say.kernel = 'I am the kernel.\nI manage the memory.'; S.say.hw = 'I am the LZ4 accelerator.\nI compress and decompress pages.'; S.say.req = 'We are the programs.\nWe just read and write our pages.'; } });

var freed = D.frames.free_before - M.fc_low;
step({ who: 'user', title: RQ.name + ' 需要一個空的 frame', cam: L.VIEW.far, keep: [K.gate],
  text: '<p><b>' + RQ.name + '</b> 要' + (RQ.w ? '寫' : '讀') + ' page ' + c(RH) + '。' + (RQ.kind === 'first' ? '這個 page 第一次被用到' : '這個 page 現在不在 DRAM 的 frame 裡')
    + '，所以 access gate 把它攔下來，交給 <b class="k">KERNEL SW</b>：先找一個空的 frame 給它。</p>'
    + '<p>可是 ' + D.frames.total + ' 個 frame 只剩 ' + D.frames.free_before + ' 個是空的。空 frame 降到 ' + M.fc_low + ' 個時 kernel 就開始「回收」：把最久沒用的 page 壓縮後搬走，直到空 frame 回到 ' + M.fc_high + ' 個。'
    + (freed > 0 ? '這一輪已經回收了 ' + freed + ' 個，現在輪到下一個 page。' : '現在輪到第一個 page。') + '</p>',
  apply: function (S) {
    S.pos.req = 'ui_gate'; S.gate = 'stop'; S.pos.kernel = 'k_call';
    S.say.req = (RQ.w ? 'write' : 'read') + ' page ' + RH; S.say.gate = 'Page ' + RH + ' has no frame yet.\nKERNEL SW is called.';
    S.say.kernel = 'Free frames: ' + D.frames.free_before + ' of ' + D.frames.total + '.\nReclaim goes on until ' + M.fc_high + '.';
  },
  card: function () { return L.tableCard('Free frames', [['free now', D.frames.free_before + ' of ' + D.frames.total], ['reclaim starts at', M.fc_low + ' free frames'], ['reclaim stops at', M.fc_high + ' free frames'], ['waiting for a frame', 'USER SW ' + RQ.name + ', page ' + RH]]); } });

/* ---- 1: the victim */
step({ who: 'kernel', title: '挑出要搬走的 page', cam: L.VIEW.frame, keep: [K.frame],
  text: '<p>kernel 有一份 LRU 清單，記著每個在 frame 裡的 page 多久沒被用。排最前面、最久沒用的是 <b>page ' + H + '</b>，屬於 <b>' + V.name + '</b>。它是 RW page，內容只存在 DRAM 裡，不能直接丟掉，所以要壓縮保存。</p>'
    + '<p>注意兩個不同的號碼：' + c(H) + ' 是 page 的編號，kernel 和硬體之間叫它 <b>handle</b>；它的資料目前放在 <b>frame ' + V.frame + '</b>，實體位址 ' + c(hx(V.frame_pa)) + '。壓縮完之後，這個 frame 就可以讓給別人。</p>',
  apply: function (S) { S.pos.kernel = 'k_frame'; S.frame.hot = true; S.say.kernel = 'Victim: page ' + H + ' of ' + V.name + '.\nIt was used longest ago.'; },
  card: function () { return L.tableCard('The page to compress', [
    ['page number (handle)', H + ' = ' + V.h], ['owner', 'USER SW ' + V.name], ['kind', 'RW (blue)'],
    ['frame', V.frame], ['frame_pa', M.fc_base + V.frame * M.page === V.frame_pa ? hx(M.fc_base) + ' + ' + V.frame + ' × ' + M.page + ' = ' + hx(V.frame_pa) : hx(V.frame_pa)]]); } });

/* ---- 2: PTE */
step({ who: 'kernel', title: '先把 PTE 設成 invalid', cam: L.VIEW.pte, keep: [K.pte],
  text: '<p>動手之前，kernel 先把 page ' + H + ' 的 <b>PTE</b> 的 valid bit 從 1 寫成 0，並在自己的筆記裡把這個 page 標成 ' + c('compressing') + '。</p>'
    + '<p>為什麼？如果壓縮到一半 ' + V.name + ' 又寫了這個 page，壓出來的資料就和 frame 的內容對不上。valid = 0 之後，' + V.name + ' 對這個 page 的任何存取都會在 access gate 被攔下、交給 kernel 處理。</p>'
    + '<p>PTE 只有 kernel 會寫。LZ4 HW 從頭到尾不碰 page table。</p>',
  apply: function (S) { S.pos.kernel = 'k_gate'; S.pte.valid = 0; S.pte.st = 'compressing'; S.pte.hot = true; S.pte.w = true; led(S, 'pte', 'k', 'W');
    S.say.kernel = 'PTE of page ' + H + ': valid = 0.\nNobody gets to this page\nwhile it is compressed.'; },
  card: function () { return L.tableCard('What KERNEL SW changed', [['PTE valid bit', '1, now <span class="by k">0</span>'], ["kernel's page state", 'present, now <span class="by k">compressing</span>']]); } });

/* ---- 3..6: descriptor, field by field */
var over = Math.ceil((M.limit + 1) / M.chunk);
step({ who: 'kernel', title: '寫 descriptor：要做什麼', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>kernel 用一張 16 B 的「工作單」把事情交代給硬體，這就是 <b>job descriptor</b>。它放在 DRAM 裡 job ring 的一格，kernel 寫、LZ4 HW 讀。</p>'
    + '<p>先寫前 2 個 byte：' + c('opcode = ' + D.desc.opcode) + ' 代表 ' + D.desc.op_name + '（2 是 DECOMPRESS），' + c('flags = 0') + '。</p>'
    + '<p>stage 上黃色的格子就是 kernel 寫的 byte，' + c('--') + ' 是還沒寫的。</p>',
  apply: function (S) { S.pos.kernel = 'k_desc'; put(S, 'desc', { opcode: D.desc.op_name, flags: '' }, 'k'); led(S, 'desc', 'k', 'W'); S.say.kernel = 'I write the job descriptor.\nopcode ' + D.desc.opcode + ': ' + D.desc.op_name + '.'; } });
step({ who: 'kernel', title: '寫 descriptor：放棄門檻', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>' + c('limit = ' + M.limit) + '：壓縮後如果超過 ' + M.limit + ' B，就要用到 ' + over + ' 個 chunk，也就是 ' + over * M.chunk + ' B，' + (over * M.chunk >= M.page ? '等於沒省' : '省得太少') + '。這時硬體要直接放棄，回報 INCOMPRESSIBLE。</p>'
    + '<p>' + M.limit + ' 寫成 16 進位是 ' + c(hx(M.limit, 4)) + '。DRAM 裡是 little-endian，低位的 byte 放前面，所以看到的是 ' + c(hexOf(bDesc, 2, 2)) + '。後面所有多 byte 的欄位都是這個規則。</p>',
  apply: function (S) { put(S, 'desc', { limit: '' + M.limit }, 'k'); S.say.kernel = 'limit ' + M.limit + ':\nabove that, give up.'; } });
step({ who: 'kernel', title: '寫 descriptor：哪一個 page、資料在哪裡', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>' + c('handle = ' + H) + '：要壓的是哪一個 page。4 個 byte，little-endian 寫成 ' + c(hexOf(bDesc, 4, 4)) + '。</p>'
    + '<p>' + c('frame_pa = ' + hx(V.frame_pa)) + '：這個 page 未壓縮的資料目前在 DRAM 的哪個實體位址，寫成 ' + c(hexOf(bDesc, 8, 4)) + '。</p>',
  apply: function (S) { put(S, 'desc', { handle: H, frame_pa: hx(V.frame_pa) }, 'k'); S.say.kernel = 'handle ' + H + ',\ndata at ' + hx(V.frame_pa) + '.'; } });
step({ who: 'kernel', title: '寫 descriptor：tag，還有沒寫的東西', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>' + c('tag = ' + hx(D.desc.tag)) + '：kernel 自己取的編號，硬體做完會原封不動抄回來，kernel 靠它認出是哪一個 job。這個設計直接拿 handle 當 tag。</p>'
    + '<p>16 B 寫完了。留意<b>裡面沒有的東西</b>：沒有說壓縮後的資料要放哪些 chunk，也沒有 COT 的位址。在這個偏硬體的設計裡，那些全部由 LZ4 HW 自己決定、自己記。</p>',
  apply: function (S) { put(S, 'desc', { tag: hx(D.desc.tag) }, 'k'); S.say.kernel = 'tag ' + hx(D.desc.tag) + ': so I know\nthe answer when it comes back.'; } });

/* ---- 7: the briefing and the doorbell */
step({ who: 'kernel', title: '交代工作，按 doorbell', cam: L.VIEW.desk, keep: [K.desc, K.bell], card: descCard,
  text: '<p>descriptor 只是躺在 DRAM 裡，硬體還不知道。kernel 對 <b>DOORBELL</b> register 做一次 MMIO 寫入，告訴 LZ4 HW「job ring 有新工作」。</p>'
    + '<p>注意 kernel 交代的方式：只說「壓哪一個 page、資料在哪」，其餘的事情全權交給硬體。之後 kernel 不用盯著，等硬體用 IRQ 通知就好。</p>',
  apply: function (S) { S.pos.kernel = 'k_bell'; S.bell = 1; led(S, 'bell', 'k', 'W');
    S.say.kernel = 'LZ4 HW, a job for you:\n' + D.desc.op_name + ' page ' + H + '.\nIts data is at ' + hx(V.frame_pa) + '.\nGive up above ' + M.limit + ' B.\nYou pick the chunks, you fill the COT.\nReport back with tag ' + hx(D.desc.tag) + '.';
    S.say.hw = 'Understood.'; },
  fx: function (done) { kit.after(700, function () { kit.ping(new T.Vector3(-4, 5.6, -25), 0xf4d35e, 3); done(); }); } });

/* ---- 8: hardware reads the descriptor */
step({ who: 'hw', title: '讀 descriptor，檢查', cam: L.VIEW.read, keep: [K.desc],
  text: '<p>LZ4 HW 從 job ring 讀出這 16 B（第 1 次 DRAM 存取）。格子右上角的紫色小角代表「LZ4 HW 讀過」。</p>'
    + '<p>它先檢查：opcode 是認得的；handle ' + c(H) + ' 小於 page 總數 ' + M.pages + '。不合格就直接回報 BAD_DESC 或 BAD_HANDLE，什麼都不動。</p>'
    + '<p>它也自己算出這個 page 的 COT entry 在哪：' + c('cot_base + handle × 32') + ' = ' + c(hx(M.cot_base) + ' + ' + H + ' × 32') + ' = ' + c(hx(V.entry_pa)) + '。</p>',
  apply: function (S) { S.pos.kernel = 'k_home'; S.pos.hw = 'h_desc'; S.bell = 0; readAll(S, 'desc', 'h'); led(S, 'desc', 'h', 'R'); S.clk.on = true; S.clk.dram = 1;
    S.say.hw = 'Descriptor read: ' + D.desc.op_name + '.\nHandle ' + H + ' is in range.'; },
  card: function (S) { return descCard(S) + L.tableCard('Checks by LZ4 HW', [['opcode known', D.desc.opcode + ' = ' + D.desc.op_name + ': yes'], ['handle in range', V.h + ' &lt; ' + M.pages + ': yes'], ['COT entry address', hx(V.entry_pa)]]); } });

/* ---- 9: frame into the engine */
var pg = R.bytes(D.page.head), sh = R.bytes(D.stream.head), lit = sh[0] >> 4, li = 1, ext = [], litText = '';
if (lit === 15) { while (li < sh.length && sh[li] === 255) { ext.push(255); lit += 255; li++; } if (li < sh.length) { ext.push(sh[li]); lit += sh[li]; li++; } else li = 99; }
if (li < sh.length - 3 && sh.slice(li, li + 4).join() === pg.slice(0, 4).join()) {
  litText = '<p>對照 LZ4 格式：stream 的第 1 個 byte ' + c(R.b2(sh[0])) + ' 是 token，高 4 bit 是 literal 長度 ' + (sh[0] >> 4)
    + (ext.length ? '，15 表示還要加上後面的 ' + c(ext.map(R.b2).join(' ')) + '：15 + ' + ext.join(' + ') + ' = ' + lit : '')
    + '。接下來 ' + lit + ' 個 byte 是從 frame 開頭原樣搬過來的 literal，所以兩邊都看得到 ' + c(hexOf(pg, 0, 4)) + '。</p>';
}
step({ who: 'hw', title: '讀 frame，送進 LZ4 engine', cam: L.VIEW.engine, keep: [K.frame, K.engine],
  text: '<p>LZ4 HW 從 ' + c(hx(V.frame_pa)) + ' 把 ' + M.page + ' B 讀出來（第 2 次 DRAM 存取），一路送進 LZ4 engine。engine 每個 cycle 處理 1 B，' + M.page + ' B 要 ' + M.comp_ns + ' ns。</p>'
    + '<p>出來的是 <b>' + SL + ' B</b> 的 LZ4 stream。斜線代表壓縮過的資料。</p>' + litText,
  apply: function (S) { S.pos.hw = 'h_engine'; S.frame.hot = 'read'; S.eng.on = 1; S.eng.segs = NCH; led(S, 'frame', 'h', 'R'); S.clk.dram = 2; S.clk.lz = 1;
    S.say.hw = 'I read ' + M.page + ' B from the frame\nand LZ4-encode them.'; },
  fx: function (done) {
    var a = new T.Vector3(-27, 1.2, L.ZROW), b = new T.Vector3(-9, 3.4, L.ZROW - 1), i;
    for (i = 0; i < 4; i++) (function (i) { kit.after(500 + i * 320, function () { kit.fly(a, b, { color: R.COL.rw, ms: 800, size: [2.6, 0.8, 2.6] }); }); })(i);
    kit.after(2400, done);
  },
  card: function () { return L.tableCard('Frame in, stream out', [
    ['frame, first 16 B', '<span style="color:var(--rw)">' + hexOf(pg, 0, 16) + '</span>'], ['stream, first 16 B', hexOf(sh, 0, 16)],
    ['size', M.page + ' B in, ' + SL + ' B out'], ['time in the engine', M.comp_ns + ' ns']]); } });

/* ---- 10: size check */
step({ who: 'hw', title: '值得存嗎？要幾個 chunk？', cam: L.VIEW.work, keep: [K.engine],
  text: '<p>' + SL + ' B 不超過 limit ' + M.limit + ' B，值得存。</p>'
    + '<p>壓縮後的資料存在 <b>chunk</b> 裡，每個 chunk ' + M.chunk + ' B。需要 ' + c('ceil(' + SL + ' / ' + M.chunk + ') = ' + NCH) + ' 個' + (LAST < M.chunk ? '：前 ' + (NCH - 1) + ' 個裝滿 ' + M.chunk + ' B，最後一個只裝 ' + LAST + ' B' : '') + '。</p>'
    + '<p>原本佔 ' + M.page + ' B，之後佔 ' + NCH + ' × ' + M.chunk + ' = ' + NCH * M.chunk + ' B。</p>',
  apply: function (S) { S.say.hw = SL + ' B is under the limit.\nI need ' + NCH + ' chunks.'; },
  card: function () { return L.tableCard('Size check by LZ4 HW', [['stream length', SL + ' B'], ['limit from the descriptor', M.limit + ' B: passed'], ['chunks needed', 'ceil(' + SL + ' / ' + M.chunk + ') = ' + NCH], ['bytes per chunk', D.stream.sizes.join(', ')]]); } });

/* ---- 11..: one chunk per step */
D.chunks.forEach(function (ch, i) {
  var a = i * M.chunk, b = a + ch.bytes - 1, prev = i ? D.chunks[i - 1] : null, pa = M.pool_base + ch.n * M.chunk === ch.pa, idx = steps.length;
  var t = i === 0
    ? '<p>哪些 chunk 是空的？LZ4 HW 自己有一個 <b>free-chunk stack</b>，放在它的 SRAM 裡，現在有 ' + D.stack.size_before + ' 個空 chunk 的號碼（更多的存在 DRAM 的 ' + D.stack.list_chunks + ' 個 list chunk 裡，SRAM 快空了才去補）。kernel 完全不知道哪些 chunk 是空的。</p>'
      + '<p>它從 stack 頂端 pop 出 ' + c(hx(ch.n)) + '，位址是 ' + (pa ? c('pool_base + ' + hx(ch.n) + ' × ' + M.chunk) + ' = ' : '') + c(hx(ch.pa)) + '，把 stream 的第 ' + a + ' 到 ' + b + ' B 寫進去。pop 只動 SRAM，不需要 DRAM 存取。</p>'
    : '<p>再 pop 一個：' + c(hx(ch.n)) + '（位址 ' + c(hx(ch.pa)) + '），寫入 stream 的第 ' + a + ' 到 ' + b + ' B。</p>';
  if (prev && ch.n !== prev.n + 1) t += '<p>注意 ' + c(hx(ch.n)) + ' 和前一個 ' + c(hx(prev.n)) + ' 不相鄰。stack 頂端是什麼號碼就拿什麼，所以一個 page 的資料會散在不連續的 chunk 上，COT 必須一個一個記下來。</p>';
  if (ch.bytes < M.chunk) t += '<p>這個 chunk 只寫了 ' + ch.bytes + ' B，剩下 ' + (M.chunk - ch.bytes) + ' B 空著不用。</p>';
  step({ who: 'hw', title: '拿第 ' + (i + 1) + ' 個 chunk，寫入 ' + ch.bytes + ' B', cam: L.VIEW.chunks, keep: [K['ch' + i], K.stack], text: t,
    apply: function (S) { S.pos.hw = 'h_ch' + i; S.stack.pop = i + 1; S.ch[i] = 2; S.chHot = i; led(S, 'stack', 'h', 'R'); led(S, 'stack', 'h', 'W'); led(S, 'chunk', 'h', 'W');
      S.say.hw = 'pop ' + hx(ch.n) + ' from my stack,\nwrite ' + ch.bytes + ' B into it.'; },
    fx: function (done) {
      var mid = R.clone(lesson.states[idx - 1]), pl = L.plates[i];
      mid.stack.hot = true; L.show(mid, false);
      var tile = new T.Vector3(L.CX[i], 1, L.ZROW);
      kit.after(600, function () { kit.fly(new T.Vector3(L.XS, pl.y, -9), tile, { color: 0x36d6e7, ms: 850, size: [7, 0.86, 3.2], up: 7, done: function () {
        mid.stack.pop = i + 1; mid.stack.hot = false; mid.ch[i] = 1; L.show(mid, false); kit.ping(tile, 0xb48cff);
        kit.after(450, function () { L.segs[i].visible = false; kit.fly(L.segs[i].position.clone(), tile, { color: 0xffffff, hatch: true, ms: 850, size: [3.2 * ch.bytes / M.chunk, 0.8, 2.4], up: 4, done: done }); });
      } }); });
    },
    card: function (S) {
      var rows = D.stack.top.map(function (n, k) { var r = [k === 0 ? 'top of stack' : k < NCH ? '' : k === D.stack.top.length - 1 ? '… ' + (D.stack.size_before - k - 1) + ' more below' : '', hx(n) + (k <= i ? '  popped, now chunk[' + k + ']' : '')]; r.hot = k === i; return r; });
      return L.tableCard('Free-chunk stack <span>(SRAM of LZ4 HW, ' + (D.stack.size_before - i - 1) + ' numbers left)</span>', rows);
    } });
});

/* ---- checksum */
step({ who: 'hw', title: '算 checksum', cam: L.VIEW.engine, keep: [K.engine],
  text: '<p>LZ4 HW 對這 ' + SL + ' B 的 stream 算 CRC-32，得到 ' + c(CK) + '。之後解壓縮時會重算一次，對不上就代表 chunk 裡的資料壞了。</p>'
    + '<p>stream 經過 engine 的時候順便算，不用再讀一次 DRAM。</p>',
  apply: function (S) { S.pos.hw = 'h_engine'; S.say.hw = 'CRC-32 of the stream:\n' + CK; },
  card: function () { return L.tableCard('Checksum', [['over', 'the ' + SL + ' B stream (compressed bytes)'], ['CRC-32', CK], ['used again', 'when the page is decompressed']]); } });

/* ---- COT entry, field by field */
var cotVals = {}; D.cot.chunks.forEach(function (n, i) { cotVals['chunk[' + i + ']'] = hx(n); });
step({ who: 'hw', title: '寫 COT：flags 和 count', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>現在要把「page ' + H + ' 壓縮後在哪裡」記下來。這張表叫 <b>COT</b>，每個 page 一筆 32 B。page ' + H + ' 這一筆在 ' + c(hx(V.entry_pa)) + '，壓縮前 32 B 全是 0，VALID bit 是 0，意思是「這個 page 沒有壓縮資料」。</p>'
    + '<p>LZ4 HW 寫入 ' + c('flags = ' + hx(D.cot.flags, 2)) + '（bit0 VALID；bit1 RO 和 bit2 RAW 都是 0）以及 ' + c('count = ' + NCH) + '（用了 ' + NCH + ' 個 chunk）。</p>'
    + '<p>實際硬體是一次把 32 B 寫出去（第 3 次 DRAM 存取），這裡拆成 4 步慢慢看。紫色代表 LZ4 HW 寫的。</p>',
  apply: function (S) { S.pos.hw = 'h_cot'; put(S, 'cot', { flags: 'VALID', count: '' + NCH }, 'h'); led(S, 'cot', 'h', 'W'); S.say.hw = 'COT[' + H + ']:\nVALID, ' + NCH + ' chunks.'; } });
step({ who: 'hw', title: '寫 COT：comp_len', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>' + c('comp_len = ' + SL) + '，就是 stream 的長度，16 進位 ' + c(hx(SL, 4)) + '，little-endian 寫成 ' + c(hexOf(bCot, 2, 2)) + '。</p>'
    + '<p>解壓縮時靠它知道最後一個 chunk 只有 ' + LAST + ' B 是有效的。</p>',
  apply: function (S) { put(S, 'cot', { comp_len: '' + SL }, 'h'); S.say.hw = 'comp_len ' + SL; } });
step({ who: 'hw', title: '寫 COT：checksum', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>' + c('checksum = ' + CK) + '，剛才算的 CRC-32，寫成 ' + c(hexOf(bCot, 4, 4)) + '。</p>',
  apply: function (S) { put(S, 'cot', { checksum: CK }, 'h'); S.say.hw = 'checksum ' + CK; } });
step({ who: 'hw', title: '寫 COT：chunk 號碼', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>最後是 ' + NCH + ' 個 chunk 號碼，照 stream 的順序排。每個號碼 3 B（24 bit）：' + c(hx(D.cot.chunks[0])) + ' 寫成 ' + c(hexOf(bCot, 8, 3)) + '。</p>'
    + '<p>一筆最多記 8 個 chunk（8 × ' + M.chunk + ' = ' + 8 * M.chunk + ' B）。' + (NCH < 8 ? '這次只用 ' + NCH + ' 個，' + c('chunk[' + NCH + ']') + ' 之後維持 0。' : '') + '</p>'
    + '<p>到這裡 COT entry 完成。整筆都是 LZ4 HW 寫的，kernel 沒有碰。</p>',
  apply: function (S) { put(S, 'cot', cotVals, 'h'); S.clk.dram = 3; S.say.hw = 'chunks ' + D.cot.chunks.map(function (n) { return hx(n); }).join(', '); } });

/* ---- completion */
var total = D.done.dram_accesses * M.dram_ns + M.comp_ns;
step({ who: 'hw', title: '寫 completion，發 IRQ', cam: L.VIEW.done, keep: [K.done, K.irq], card: doneCard,
  text: '<p>LZ4 HW 把結果寫進 completion ring 的一格（第 4 次 DRAM 存取），也是 16 B：' + c('status = ' + D.done.status) + '（' + D.done.status_name + '）、' + c('length = ' + D.done.length) + '、' + c('checksum') + '，以及從 descriptor 抄回來的 ' + c('tag = ' + hx(D.done.tag)) + '。然後拉 IRQ 通知 kernel。</p>'
    + '<p>completion 裡同樣沒有 chunk 號碼：kernel 不需要知道。</p>'
    + (total === D.done.lat_ns ? '<p>整個 job 花了 ' + D.done.dram_accesses + ' × ' + M.dram_ns + ' ns + ' + M.comp_ns + ' ns = ' + D.done.lat_ns + ' ns。</p>' : ''),
  apply: function (S) { S.pos.hw = 'h_done'; put(S, 'done', { status: D.done.status_name, flags: '' + D.done.flags, length: '' + D.done.length, checksum: hx(D.done.checksum, 8), tag: hx(D.done.tag), aux: '' + D.done.aux }, 'h');
    S.done.hot = []; S.irq = 1; led(S, 'done', 'h', 'W'); S.clk.dram = 4;
    S.say.hw = 'KERNEL SW, job done.\nTag ' + hx(D.done.tag) + ': ' + D.done.status_name + ', ' + D.done.length + ' B,\nchecksum ' + hx(D.done.checksum, 8) + '.'; },
  fx: function (done) { kit.after(900, function () { done(); kit.ping(new T.Vector3(4, 5.6, -25), 0xb48cff, 3); }); } });

/* ---- kernel finishes */
step({ who: 'kernel', title: '讀 completion，認出是哪個 job', cam: L.VIEW.kread, keep: [K.done], card: doneCard,
  text: '<p>IRQ 進來，kernel 讀 completion。格子右上角的黃色小角代表「kernel 讀過」。</p>'
    + '<p>' + c('tag = ' + hx(D.done.tag)) + ' 對到剛才那個 job，' + c('status = ' + D.done.status) + ' 代表成功。</p>'
    + '<p>kernel 只讀這 16 B。它沒有去讀 COT，也不知道資料在哪 ' + NCH + ' 個 chunk。</p>',
  apply: function (S) { S.pos.kernel = 'k_done'; S.irq = 0; readAll(S, 'done', 'k'); S.done.hot = ['status', 'tag']; led(S, 'done', 'k', 'R');
    S.say.kernel = 'Tag ' + hx(D.done.tag) + ': that is my job.\nStatus ' + D.done.status_name + '.'; } });
step({ who: 'kernel', title: '放掉 frame', cam: L.VIEW.frame, keep: [K.frame],
  text: '<p>資料已經安全地存在 chunk 裡，kernel 把 <b>frame ' + V.frame + '</b> 放回空 frame 清單，空 frame 從 ' + D.frames.free_before + ' 變 ' + D.frames.free_after + '。</p>'
    + '<p>它也把 page ' + H + ' 的狀態從 ' + c('compressing') + ' 改成 ' + c('compressed') + '。PTE 維持 valid = 0：' + V.name + ' 下次碰這個 page 時會被 access gate 攔下。</p>',
  apply: function (S) { S.pos.kernel = 'k_frame'; S.frame.st = 'free'; S.frame.hot = true; S.free = D.frames.free_after; S.pte.st = 'compressed';
    S.say.kernel = 'Frame ' + V.frame + ' is free again:\n' + D.frames.free_after + ' free frames.'; },
  card: function () { return L.tableCard('What KERNEL SW changed', [['free frames', D.frames.free_before + ', now <span class="by k">' + D.frames.free_after + '</span>'], ["kernel's page state", 'compressing, now <span class="by k">compressed</span>'], ['PTE valid bit', 'stays 0']]); } });

/* ---- result */
step({ who: 'note', title: '結果：誰碰了什麼', cam: L.VIEW.all,
  text: '<p>一個 ' + M.page + ' B 的 frame 空出來了，代價是 ' + NCH + ' 個 chunk 共 ' + NCH * M.chunk + ' B，外加 COT 裡本來就預留的 32 B。</p>'
    + '<p>看下面的表：<b class="k">KERNEL SW</b> 只寫了 PTE、descriptor 和 DOORBELL，只讀了 completion。frame 的資料、free-chunk stack、chunk 和 COT 全部是 <b class="h">LZ4 HW</b> 在碰。這就是「偏硬體」的意思：記帳的工作都在硬體裡。</p>'
    + '<p>回收會繼續，直到空 frame 回到 ' + M.fc_high + ' 個，然後 ' + RQ.name + ' 才拿到它要的 frame。</p>'
    + '<p>下一課：' + V.name + ' 之後再碰 page ' + H + ' 時，PTE 是 invalid，access gate 會攔下來，觸發<b>解壓縮</b>。</p>',
  apply: function (S) { S.final = true; S.pos.kernel = 'k_home'; S.pos.hw = 'h_home'; S.say.req = 'Still waiting for my frame.'; S.say.kernel = 'Next victim, until\n' + M.fc_high + ' frames are free.'; },
  card: function () { return L.tableCard('Before and after, page ' + H, [['DRAM used by the page', M.page + ' B frame, now ' + NCH + ' × ' + M.chunk + ' = ' + NCH * M.chunk + ' B of chunks'], ['free frames', D.frames.free_before + ', now ' + D.frames.free_after],
    ['PTE', 'valid 1, now 0'], ['COT[' + H + ']', 'all zero, now VALID with ' + NCH + ' chunks'], ['free-chunk stack', D.stack.size_before + ' numbers, now ' + D.stack.size_after]]); } });

var reqCss = A.req ? A.req.css : '#ff8fb1';
var lesson = new R.Lesson({
  kit: kit, steps: steps, init: init, pose: L.pose,
  show: L.show,
  card: function (S, st) { return st.card ? st.card(S) : ''; },
  clock: function (S) {
    if (!S.clk.on) return 'LZ4 HW job time: not started';
    var ns = S.clk.dram * M.dram_ns + S.clk.lz * M.comp_ns;
    return 'LZ4 HW job time so far: <b>' + S.clk.dram + ' × ' + M.dram_ns + ' ns</b> DRAM' + (S.clk.lz ? ' + <b>' + M.comp_ns + ' ns</b> LZ4' : '') + ' = <b>' + ns + ' ns</b>';
  },
  ledger: [['pte', 'PTE of page ' + H], ['desc', 'job descriptor'], ['bell', 'DOORBELL register'], ['frame', 'frame data (' + M.page + ' B)'],
           ['stack', 'free-chunk stack'], ['chunk', 'chunks (compressed data)'], ['cot', 'COT[' + H + ']'], ['done', 'completion']],
  who: { user: ['USER SW', reqCss], kernel: ['KERNEL SW', '#f4d35e'], hw: ['LZ4 HW · HARDWARE', '#b48cff'], note: ['SUMMARY', '#7ee2a8'] }
});
document.getElementById('title').textContent = 'LZ4 DRAM compression lesson';
document.getElementById('design').textContent = 'HW-LEANING DESIGN';
document.getElementById('scene').textContent = 'Scene: COMPRESS one RW page · real job from simulator run seed ' + M.seed + ', access ' + RQ.access_no;
R.lesson = lesson;
})();

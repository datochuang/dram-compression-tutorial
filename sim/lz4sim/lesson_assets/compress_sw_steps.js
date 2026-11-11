/* Lesson scene "compress-sw": the steps of the software-leaning design. Each step names who acts
   (user SW, kernel, hardware), says in the panel what happens and why, and changes the state:
   bytes written, bytes read, bits set, who stands where and says what.
   Prose is zh-TW; what is drawn on the stage is English. */
(function () {
'use strict';
var L = R.L, D = L.D, M = L.M, V = L.V, H = L.H, hx = R.hx, kit = L.kit, A = L.A, T = THREE, NCH = L.NCH, NT = L.NT;
var K = L.KEEP, RQ = D.req, RH = hx(RQ.h), SL = D.stream.len, LAST = D.stream.sizes[NCH - 1], CK = hx(D.cot.checksum, 8);
var BM = D.bitmap, RES = BM.reserved_chunks, TRIM = BM.trimmed, B0 = BM.first_chunk, HW = D.hw;
var bDesc = R.bytes(D.desc.hex), bCot = R.bytes(D.cot.after), bDone = R.bytes(D.done.hex);
var c = function (s) { return '<code>' + s + '</code>'; };
var hexOf = function (arr, a, n) { return arr.slice(a, a + n).map(R.b2).join(' '); };
var fill = function (n, v) { var a = [], i; for (i = 0; i < n; i++) a.push(v); return a; };
var list = function (a) { return a.map(function (n) { return hx(n); }).join(', '); };
var run = function (a) { var i; for (i = 1; i < a.length; i++) if (a[i] !== a[i - 1] + 1) return false; return a.length > 2; };
var span = function (a) { return run(a) ? hx(a[0]) + ' to ' + hx(a[a.length - 1]) : list(a); };
var spanZh = function (a) { return run(a) ? c(hx(a[0])) + ' 到 ' + c(hx(a[a.length - 1])) : a.map(function (n) { return c(hx(n)); }).join('、'); };
var bit = function (n) { return n - B0; };
var ns = function (x) { return Math.round(x * 10) / 10; };

var init = {
  pos: { kernel: 'k_home', hw: 'h_home', req: 'ui_home' }, say: {}, gate: 'idle', card: null, final: false,
  pte: { valid: 1, st: 'present', hot: false, w: false }, free: D.frames.free_before,
  frame: { st: 'present', hot: false },
  desc: { b: fill(48, null), w: fill(48, null), r: fill(48, ''), vals: {}, hot: [] },
  cot: { b: R.bytes(D.cot.before), w: fill(32, null), r: fill(32, ''), vals: {}, hot: [] },
  done: { b: fill(16, null), w: fill(16, null), r: fill(16, ''), vals: {}, hot: [] },
  bm: { word: BM.before, mark: {}, hot: [], free: BM.free_before },
  bell: 0, irq: 0, eng: { on: 0, segs: 0 }, ch: fill(NT, 0), chHot: -1,
  led: {}, clk: { on: false, dram: 0, lz: 0, k: 0 }
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
function calm(S) { S.desc.hot = []; S.cot.hot = []; S.done.hot = []; S.bm.hot = []; S.pte.hot = false; S.frame.hot = false; S.chHot = -1; S.eng.on = 0; }

var descCard = function (S) { return L.structCard('desc', S, 'Job descriptor <span>(48 B in DRAM, job ring)</span>'); };
var cotCard = function (S) { return L.structCard('cot', S, 'COT[' + H + '] <span>(32 B in DRAM @' + hx(V.entry_pa) + ')</span>'); };
var doneCard = function (S) { return L.structCard('done', S, 'Completion <span>(16 B in DRAM, completion ring)</span>'); };
var bmCard = function (S, extra) {
  var rows = [['kept in', 'kernel memory, ' + BM.nwords + ' words of 64 bit = ' + M.bitmap_bytes + ' B'], ['one bit', '1 = chunk in use, 0 = chunk free'],
              ['word ' + BM.word, 'chunks ' + hx(B0) + ' to ' + hx(B0 + 63)], ['value of word ' + BM.word, '0x' + S.bm.word.toUpperCase()],
              ['free chunks in the pool', S.bm.free + ' of ' + M.pool_chunks]];
  return L.tableCard('Free-chunk bitmap <span>(of KERNEL SW)</span>', rows.concat(extra || []));
};
var steps = [];
function step(o) { var ap = o.apply; o.apply = function (S) { calm(S); S.card = steps.indexOf(o); ap(S); }; steps.push(o); }

/* ---- why this job exists */
var glossary = function () { return L.tableCard('Words used in this lesson', [
    ['page', '軟體看到的 ' + M.page + ' B 記憶體單位，用編號稱呼'],
    ['frame', 'DRAM 裡一塊 ' + M.page + ' B 的空間，放一個未壓縮的 page'],
    ['chunk', 'DRAM 裡 ' + M.chunk + ' B 的小塊，放壓縮後的資料，共 ' + M.pool_chunks + ' 個'],
    ['PTE', 'page table entry，決定 user SW 的存取能不能直接通過'],
    ['COT', 'compressed object table，每個 page 一筆 32 B，記壓縮後的資料在哪些 chunk'],
    ['bitmap', 'kernel 自己的帳本，每個 chunk 1 個 bit，記它是空的還是用掉了'],
    ['descriptor', 'kernel 寫給 LZ4 HW 的工作單，48 B'],
    ['completion', 'LZ4 HW 回報結果的單子，16 B']]); };
step({ who: 'note', title: '舞台上有誰、有什麼', cam: L.VIEW.all, card: glossary,
  text: '<p>這一課用一個真實的例子，看「壓縮一個 page」從頭到尾發生的事。所有數字都來自 simulator 的同一次執行。</p>'
    + '<p>三種角色：<b>USER SW</b>（遠端的 ' + M.clients.join('、') + '）是被服務的程式，只管讀寫自己的 page。<b class="k">KERNEL SW</b>（黃色）管理記憶體。<b class="h">LZ4 HW</b>（紫色機器人）是硬體加速器，負責壓縮與解壓縮。</p>'
    + '<p>這是<b>偏軟體</b>的設計：哪些 chunk 是空的、每個 page 壓縮後放在哪裡，這兩本帳都由 kernel 自己記。LZ4 HW 做完一個 job 之後什麼都不記得。</p>'
    + '<p>舞台由遠到近：最遠是 user SW 和它們共用的 access gate；中間是 kernel 和硬體互相留言的兩張單子，descriptor 和 completion；再來是 DRAM 裡的 frame 和 chunk；最靠近你的是 kernel 的兩本帳：左邊 <b>free-chunk bitmap</b>，右邊 <b>COT</b> 的一筆。</p>'
    + '<p>按 Next 一步一步看，畫面可以拖曳旋轉、滾輪縮放。</p>',
  apply: function (S) { S.say.kernel = 'I am the kernel.\nI manage the memory and,\nin this design, I keep the books.'; S.say.hw = 'I am the LZ4 accelerator.\nI compress and decompress pages.\nI remember nothing between jobs.'; S.say.req = 'We are the programs.\nWe just read and write our pages.'; } });

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

step({ who: 'kernel', title: '挑出要搬走的 page', cam: L.VIEW.frame, keep: [K.frame],
  text: '<p>kernel 有一份 LRU 清單，記著每個在 frame 裡的 page 多久沒被用。排最前面、最久沒用的是 <b>page ' + H + '</b>，屬於 <b>' + V.name + '</b>。它是 RW page，內容只存在 DRAM 裡，不能直接丟掉，所以要壓縮保存。</p>'
    + '<p>' + c(H) + ' 是 page 的編號；它的資料目前放在 <b>frame ' + V.frame + '</b>，實體位址 ' + c(hx(V.frame_pa)) + '。壓縮完之後，這個 frame 就可以讓給別人。</p>',
  apply: function (S) { S.pos.kernel = 'k_frame'; S.frame.hot = true; S.say.kernel = 'Victim: page ' + H + ' of ' + V.name + '.\nIt was used longest ago.'; },
  card: function () { return L.tableCard('The page to compress', [
    ['page number', H + ' = ' + V.h], ['owner', 'USER SW ' + V.name], ['kind', 'RW (blue)'],
    ['frame', V.frame], ['frame_pa', M.fc_base + V.frame * M.page === V.frame_pa ? hx(M.fc_base) + ' + ' + V.frame + ' × ' + M.page + ' = ' + hx(V.frame_pa) : hx(V.frame_pa)]]); } });

/* ---- the kernel's bitmap: reserve */
var need = BM.need, first = bit(RES[0]), oneRun = run(RES);
step({ who: 'kernel', title: '先決定：壓縮後的資料要放哪裡', cam: L.VIEW.bitmap, keep: [K.bitmap],
  text: '<p>在這個設計裡，LZ4 HW 不知道哪些 chunk 是空的。<b>kernel 必須在交代工作之前，先把要用的 chunk 挑好。</b></p>'
    + '<p>問題是還沒壓，不知道會壓成多大。kernel 用最壞的情況來準備：超過 ' + M.limit + ' B 就不值得存（後面會解釋），所以最多需要 ' + c('ceil(' + M.limit + ' / ' + M.chunk + ') = ' + need) + ' 個 chunk。多拿的之後再還。</p>'
    + '<p>kernel 的帳本是一張 <b>bitmap</b>：' + M.pool_chunks + ' 個 chunk 每個 1 bit，1 是用掉、0 是空的，共 ' + BM.nwords + ' 個 64-bit word，' + M.bitmap_bytes + ' B，放在 kernel 自己的記憶體裡。</p>'
    + '<p>kernel 記得上次找到空位的地方（cursor = word ' + BM.cursor_before + '），從那裡開始找。' + (BM.scanned === 1 ? '這個 word 裡的 0 就夠 ' + need + ' 個，只看了 1 個 word。' : '一共看了 ' + BM.scanned + ' 個 word。')
    + '白框是它找到的 ' + need + ' 個 0：' + (oneRun ? '從 bit ' + first + ' 開始。' : '') + '</p>',
  apply: function (S) { S.pos.kernel = 'k_bm'; S.bm.hot = RES.map(bit); led(S, 'bitmap', 'k', 'R');
    S.say.kernel = 'Where will the result go?\nI do not know its size yet, so I look\nfor ' + need + ' free chunks: the most a page\nworth storing can need.'; },
  card: function (S) { return bmCard(S, [['chunks to reserve', 'ceil(' + M.limit + ' / ' + M.chunk + ') = ' + need], ['search starts at', 'cursor = word ' + BM.cursor_before], ['words looked at', '' + BM.scanned]]); } });
step({ who: 'kernel', title: '在 bitmap 裡把 ' + need + ' 個 bit 寫成 1', cam: L.VIEW.bitmap, keep: [K.bitmap],
  text: '<p>kernel 把這 ' + need + ' 個 bit 從 0 寫成 1（黃色）。word ' + BM.word + ' 的值從 ' + c('0x' + BM.before.toUpperCase()) + ' 變成 ' + c('0x' + BM.reserved.toUpperCase()) + '，空 chunk 從 ' + BM.free_before + ' 個變 ' + BM.free_reserved + ' 個。</p>'
    + '<p>bit 的位置就是 chunk 的號碼：' + c('word × 64 + bit') + ' = ' + c(BM.word + ' × 64 + ' + first) + ' = ' + RES[0] + ' = ' + c(hx(RES[0])) + '。所以預留的是 chunk ' + spanZh(RES) + '。</p>'
    + '<p>這一步只動 kernel 自己的記憶體。LZ4 HW 看不到這張 bitmap，也不需要看。</p>',
  apply: function (S) { S.pos.kernel = 'k_bm'; S.bm.word = BM.reserved; S.bm.free = BM.free_reserved; RES.forEach(function (n) { S.bm.mark[bit(n)] = 's'; S.ch[RES.indexOf(n)] = 1; }); S.bm.hot = RES.map(bit); led(S, 'bitmap', 'k', 'W');
    S.say.kernel = need + ' bits set to 1: chunks\n' + span(RES) + '\nare mine now.'; },
  fx: function (done) { kit.after(500, function () { RES.forEach(function (n, i) { kit.after(i * 110, function () { kit.ping(L.bitAt(n), 0xf4d35e, 1.2); }); }); kit.after(RES.length * 110 + 300, done); }); },
  card: function (S) { return bmCard(S, [['bits set by KERNEL SW', '<span class="by k">' + need + ' bits</span>, bit ' + first + ' to ' + bit(RES[need - 1])], ['chunk number of a bit', BM.word + ' × 64 + bit'], ['reserved chunks', span(RES)]]); } });
var pa0 = M.pool_base + RES[0] * M.chunk === D.tiles[0].pa;
step({ who: 'kernel', title: '預留的 ' + need + ' 個 chunk', cam: L.VIEW.chunks, keep: D.tiles.map(function (t, i) { return K['ch' + i]; }),
  text: '<p>這就是 bitmap 上那 ' + need + ' 個 bit 對應的 chunk，現在標成「reserved by KERNEL SW」。裡面還沒有資料。</p>'
    + '<p>chunk 的實體位址由號碼算出來：' + (pa0 ? c('pool_base + 號碼 × ' + M.chunk) + '，第一個是 ' + c(hx(M.pool_base) + ' + ' + hx(RES[0]) + ' × ' + M.chunk) + ' = ' : '第一個是 ') + c(hx(D.tiles[0].pa)) + '。</p>'
    + (oneRun ? '<p>它們剛好是連續的號碼，因為 bitmap 是從低位往高位找 0。</p>' : ''),
  apply: function (S) { S.pos.kernel = 'k_tiles'; S.say.kernel = 'These ' + need + ' chunks are reserved.\nNobody else gets them.'; },
  card: function () { return L.tableCard('Reserved chunks <span>(nothing stored yet)</span>', D.tiles.map(function (t, i) { return ['chunk ' + hx(t.n), '@' + hx(t.pa) + ' · bit ' + bit(t.n) + ' of word ' + BM.word]; })); } });

/* ---- PTE */
step({ who: 'kernel', title: '把 PTE 設成 invalid', cam: L.VIEW.pte, keep: [K.pte],
  text: '<p>動手之前，kernel 把 page ' + H + ' 的 <b>PTE</b> 的 valid bit 從 1 寫成 0，並在自己的筆記裡把這個 page 標成 ' + c('compressing') + '。</p>'
    + '<p>為什麼？如果壓縮到一半 ' + V.name + ' 又寫了這個 page，壓出來的資料就和 frame 的內容對不上。valid = 0 之後，' + V.name + ' 對這個 page 的任何存取都會在 access gate 被攔下、交給 kernel 處理。</p>'
    + '<p>PTE 只有 kernel 會寫。LZ4 HW 從頭到尾不碰 page table。</p>',
  apply: function (S) { S.pos.kernel = 'k_gate'; S.pte.valid = 0; S.pte.st = 'compressing'; S.pte.hot = true; S.pte.w = true; led(S, 'pte', 'k', 'W');
    S.say.kernel = 'PTE of page ' + H + ': valid = 0.\nNobody gets to this page\nwhile it is compressed.'; },
  card: function () { return L.tableCard('What KERNEL SW changed', [['PTE valid bit', '1, now <span class="by k">0</span>'], ["kernel's page state", 'present, now <span class="by k">compressing</span>']]); } });

/* ---- descriptor, field by field */
var over = Math.ceil((M.limit + 1) / M.chunk), dv = {}, unused = [];
D.desc.chunks.forEach(function (n, i) { dv['chunk[' + i + ']'] = hx(n); });
for (var q = D.desc.chunks.length; q < 8; q++) { dv['chunk[' + q + ']'] = '0'; unused.push('chunk[' + q + ']'); }
dv.pad = '0';
step({ who: 'kernel', title: '寫 descriptor：要做什麼、給幾個 chunk', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>kernel 用一張 48 B 的「工作單」把事情交代給硬體，這就是 <b>job descriptor</b>。它放在 DRAM 裡 job ring 的一格，kernel 寫、LZ4 HW 讀。</p>'
    + '<p>先寫前 2 個 byte：' + c('opcode = ' + D.desc.opcode) + ' 代表 ' + D.desc.op_name + '（2 是 DECOMPRESS），' + c('count = ' + D.desc.count) + ' 是這張單子後面列了幾個 chunk 號碼。</p>'
    + '<p>stage 上黃色的格子就是 kernel 寫的 byte，' + c('--') + ' 是還沒寫的。</p>',
  apply: function (S) { S.pos.kernel = 'k_desc'; put(S, 'desc', { opcode: D.desc.op_name.slice(0, 4), count: '' + D.desc.count }, 'k'); led(S, 'desc', 'k', 'W'); S.say.kernel = 'I write the job descriptor.\nopcode ' + D.desc.opcode + ': ' + D.desc.op_name + ',\n' + D.desc.count + ' chunk numbers follow.'; } });
step({ who: 'kernel', title: '寫 descriptor：放棄門檻', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>' + c('limit = ' + M.limit) + '：壓縮後如果超過 ' + M.limit + ' B，就要用到 ' + over + ' 個 chunk，也就是 ' + over * M.chunk + ' B，' + (over * M.chunk >= M.page ? '等於沒省' : '省得太少') + '。這時硬體要直接放棄，回報 INCOMPRESSIBLE。剛才預留 ' + need + ' 個 chunk 就是從這個數字來的。</p>'
    + '<p>' + M.limit + ' 寫成 16 進位是 ' + c(hx(M.limit, 4)) + '。DRAM 裡是 little-endian，低位的 byte 放前面，所以看到的是 ' + c(hexOf(bDesc, 2, 2)) + '。後面所有多 byte 的欄位都是這個規則。</p>',
  apply: function (S) { put(S, 'desc', { limit: '' + M.limit }, 'k'); S.say.kernel = 'limit ' + M.limit + ':\nabove that, give up.'; } });
step({ who: 'kernel', title: '寫 descriptor：資料在哪裡', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>' + c('frame_pa = ' + hx(V.frame_pa)) + '：要壓的 ' + M.page + ' B 目前在 DRAM 的哪個實體位址，little-endian 寫成 ' + c(hexOf(bDesc, 4, 4)) + '。</p>'
    + '<p>留意這張單子<b>沒有 page 編號的欄位</b>。硬體只需要知道「從哪裡讀 ' + M.page + ' B」，這些資料屬於哪個 page、之後記在哪一筆 COT，都是 kernel 的事。</p>',
  apply: function (S) { put(S, 'desc', { frame_pa: hx(V.frame_pa) }, 'k'); S.say.kernel = 'The data is at\n' + hx(V.frame_pa) + '.'; } });
step({ who: 'kernel', title: '寫 descriptor：這次用不到的三個欄位', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>' + c('comp_len') + '、' + c('flags') + '、' + c('checksum') + ' 這三個欄位在 COMPRESS 用不到，kernel 寫 0，共 8 個 byte。</p>'
    + '<p>它們是給 DECOMPRESS 用的：解壓縮時硬體沒有 COT 可以查，壓縮資料有多長、checksum 應該是多少，都要由 kernel 寫在 descriptor 裡告訴它。同一個 48 B 格式兩種工作共用。</p>',
  apply: function (S) { put(S, 'desc', { comp_len: '0', flags: '0', checksum: '0' }, 'k'); S.say.kernel = 'comp_len, flags, checksum:\n0, not used for COMPRESS.'; } });
step({ who: 'kernel', title: '寫 descriptor：tag', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>' + c('tag = ' + hx(D.desc.tag)) + '：kernel 自己取的編號，硬體做完會原封不動抄回來，kernel 靠它認出是哪一個 job。</p>'
    + '<p>kernel 在這裡填的是 page 編號 ' + c(H) + '。對硬體來說它只是一個要抄回去的數字，沒有別的意義。</p>',
  apply: function (S) { put(S, 'desc', { tag: hx(D.desc.tag) }, 'k'); S.say.kernel = 'tag ' + hx(D.desc.tag) + ': so I know\nthe answer when it comes back.'; } });
step({ who: 'kernel', title: '寫 descriptor：' + D.desc.count + ' 個 chunk 號碼', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>最後是剛才預留的 ' + D.desc.count + ' 個 chunk 號碼，照「先用哪一個」的順序排。每個號碼 3 B（24 bit）：' + c(hx(D.desc.chunks[0])) + ' 寫成 ' + c(hexOf(bDesc, 20, 3)) + '。</p>'
    + '<p>一張單子最多列 8 個。' + (unused.length ? '這次只列 ' + D.desc.count + ' 個，' + unused.map(c).join('、') + ' 和最後 4 B 的 pad 寫 0。' : '') + '</p>'
    + '<p>48 B 寫完了。<b>壓縮後的資料要放哪些 chunk，是 kernel 在這裡指定的</b>；硬體沒有自己的空 chunk 清單。</p>',
  apply: function (S) { put(S, 'desc', dv, 'k'); S.say.kernel = 'chunks ' + span(D.desc.chunks) + ',\nin the order to fill them.'; } });

/* ---- the briefing and the doorbell */
step({ who: 'kernel', title: '交代工作，按 doorbell', cam: L.VIEW.desk, keep: [K.desc, K.bell], card: descCard,
  text: '<p>descriptor 只是躺在 DRAM 裡，硬體還不知道。kernel 對 <b>DOORBELL</b> register 做一次 MMIO 寫入，告訴 LZ4 HW「job ring 有新工作」。</p>'
    + '<p>注意 kernel 交代的方式：不只說「壓哪裡的資料」，連「結果寫到哪幾個 chunk」都講明。硬體只照單子做，做完回報長度和 checksum，其餘的帳由 kernel 自己記。</p>',
  apply: function (S) { S.pos.kernel = 'k_bell'; S.bell = 1; led(S, 'bell', 'k', 'W');
    S.say.kernel = 'LZ4 HW, a job for you:\n' + D.desc.op_name + ' the ' + M.page + ' B at ' + hx(V.frame_pa) + '.\nWrite the result into chunks\n' + span(D.desc.chunks) + ', in that order.\nUse only as many as you need.\nAbove ' + M.limit + ' B, give up.\nTell me length and checksum, tag ' + hx(D.desc.tag) + '.';
    S.say.hw = 'Understood. I use only\nthe chunks you name.'; },
  fx: function (done) { kit.after(700, function () { kit.ping(L.BELL.clone(), 0xf4d35e, 3); done(); }); } });

/* ---- hardware reads the descriptor */
var maxChunk = Math.max.apply(null, D.desc.chunks);
step({ who: 'hw', title: '讀 descriptor，檢查', cam: L.VIEW.read, keep: [K.desc],
  text: '<p>LZ4 HW 從 job ring 讀出這 48 B（第 1 次 DRAM 存取）。格子右上角的紫色小角代表「LZ4 HW 讀過」。</p>'
    + '<p>硬體不相信單子上的數字，先檢查：opcode 是認得的；' + c('count') + ' 不超過 8；每個 chunk 號碼都小於 chunk 總數 ' + M.pool_chunks + '；' + c('frame_pa') + ' 落在 frame 區而且對齊 ' + M.page + ' B。任何一項不合格就回報 BAD_DESC，什麼都不動。</p>'
    + '<p>這些檢查只用到固定的範圍，不需要查任何表。硬體不知道、也不檢查這些 chunk 是不是真的空的：那是 kernel 的責任。</p>',
  apply: function (S) { S.pos.kernel = 'k_home'; S.pos.hw = 'h_desc'; S.bell = 0; readAll(S, 'desc', 'h'); led(S, 'desc', 'h', 'R'); S.clk.on = true; S.clk.dram = 1;
    S.say.hw = 'Descriptor read: ' + D.desc.op_name + '.\n' + D.desc.count + ' chunk numbers, all in range.\nframe_pa is aligned.'; },
  card: function (S) { return descCard(S) + L.tableCard('Checks by LZ4 HW', [['opcode known', D.desc.opcode + ' = ' + D.desc.op_name + ': yes'], ['count', D.desc.count + ' ≤ 8: yes'],
    ['every chunk number in range', 'largest ' + hx(maxChunk) + ' = ' + maxChunk + ' &lt; ' + M.pool_chunks + ': yes'], ['frame_pa', hx(V.frame_pa) + ': in the frame area, multiple of ' + M.page + ': yes']]); } });

/* ---- frame into the engine */
var pg = R.bytes(D.page.head), sh = R.bytes(D.stream.head), lit = sh[0] >> 4, li = 1, ext = [], litText = '';
if (lit === 15) { while (li < sh.length && sh[li] === 255) { ext.push(255); lit += 255; li++; } if (li < sh.length) { ext.push(sh[li]); lit += sh[li]; li++; } else li = 99; }
if (li < sh.length - 3 && sh.slice(li, li + 4).join() === pg.slice(0, 4).join()) {
  litText = '<p>對照 LZ4 格式：stream 的第 1 個 byte ' + c(R.b2(sh[0])) + ' 是 token，高 4 bit 是 literal 長度 ' + (sh[0] >> 4)
    + (ext.length ? '，15 表示還要加上後面的 ' + c(ext.map(R.b2).join(' ')) + '：15 + ' + ext.join(' + ') + ' = ' + lit : '')
    + '。接下來 ' + lit + ' 個 byte 是從 frame 開頭原樣搬過來的 literal，所以兩邊都看得到 ' + c(hexOf(pg, 0, 4)) + '。</p>';
}
step({ who: 'hw', title: '讀 frame，送進 LZ4 engine', cam: L.VIEW.engine, keep: [K.frame, K.engine],
  text: '<p>LZ4 HW 從 ' + c(hx(V.frame_pa)) + ' 把 ' + M.page + ' B 讀出來（第 2 次 DRAM 存取），一路送進 LZ4 engine。engine 每個 cycle 處理 1 B，' + M.page + ' B 要 ' + ns(M.comp_ns) + ' ns。</p>'
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
    ['size', M.page + ' B in, ' + SL + ' B out'], ['time in the engine', ns(M.comp_ns) + ' ns']]); } });

/* ---- size check */
step({ who: 'hw', title: '值得存嗎？要用幾個 chunk？', cam: L.VIEW.work, keep: [K.engine],
  text: '<p>' + SL + ' B 不超過 limit ' + M.limit + ' B，值得存。</p>'
    + '<p>每個 chunk ' + M.chunk + ' B，需要 ' + c('ceil(' + SL + ' / ' + M.chunk + ') = ' + NCH) + ' 個' + (LAST < M.chunk ? '：前 ' + (NCH - 1) + ' 個裝滿 ' + M.chunk + ' B，最後一個只裝 ' + LAST + ' B' : '') + '。</p>'
    + '<p>單子上列了 ' + D.desc.count + ' 個，夠用。硬體只會用前 ' + NCH + ' 個' + (NCH < D.desc.count ? '，後面 ' + (D.desc.count - NCH) + ' 個它不會碰' : '') + '。（如果需要的比單子上列的多，它會回報 BAD_DESC；kernel 照 limit 預留，所以不會發生。）</p>',
  apply: function (S) { S.say.hw = SL + ' B is under the limit.\nI need ' + NCH + ' of the ' + D.desc.count + ' chunks\non the descriptor.'; },
  card: function () { return L.tableCard('Size check by LZ4 HW', [['stream length', SL + ' B'], ['limit from the descriptor', M.limit + ' B: passed'], ['chunks needed', 'ceil(' + SL + ' / ' + M.chunk + ') = ' + NCH],
    ['chunks offered by KERNEL SW', D.desc.count + ': enough'], ['bytes per chunk', D.stream.sizes.join(', ')]]); } });

/* ---- one chunk per step */
D.chunks.forEach(function (ch, i) {
  var a = i * M.chunk, b = a + ch.bytes - 1, idx = steps.length, f = 'chunk[' + i + ']';
  var t = i === 0
    ? '<p>要寫到哪裡？LZ4 HW 沒有自己的清單，它看 descriptor 的 ' + c(f) + '：' + c(hx(ch.n)) + '，位址是 ' + c('pool_base + ' + hx(ch.n) + ' × ' + M.chunk) + ' = ' + c(hx(ch.pa)) + '。它把 stream 的第 ' + a + ' 到 ' + b + ' B 寫進去。</p>'
      + '<p>descriptor 一開始就整張讀進來了，所以查號碼不需要再存取 DRAM。</p>'
    : '<p>下一個照單子上的 ' + c(f) + '：' + c(hx(ch.n)) + '（位址 ' + c(hx(ch.pa)) + '），寫入 stream 的第 ' + a + ' 到 ' + b + ' B。</p>';
  if (ch.bytes < M.chunk) t += '<p>這個 chunk 只寫了 ' + ch.bytes + ' B，剩下 ' + (M.chunk - ch.bytes) + ' B 空著不用。</p>';
  if (i === NCH - 1 && NCH < NT) t += '<p>stream 寫完了。單子上剩下的 ' + D.tiles.slice(NCH).map(function (x) { return c(hx(x.n)); }).join('、') + ' 硬體沒有碰，它們還標著 reserved。</p>';
  step({ who: 'hw', title: '第 ' + (i + 1) + ' 個 chunk：照單子寫入 ' + ch.bytes + ' B', cam: L.VIEW.chunks, keep: [K['ch' + i]], text: t,
    apply: function (S) { S.pos.hw = 'h_ch' + i; S.ch[i] = 2; S.chHot = i; S.desc.hot = [f]; led(S, 'chunk', 'h', 'W');
      S.say.hw = f + ' on the descriptor\nsays ' + hx(ch.n) + '.\nI write ' + ch.bytes + ' B into it.'; },
    fx: function (done) {
      var tile = new T.Vector3(L.CX[i], 1, L.ZROW);
      kit.after(500, function () { kit.fly(L.descAt.clone(), tile, { color: 0xf4d35e, ms: 800, size: [2.4, 0.5, 1.2], up: 5, done: function () {
        kit.ping(tile, 0xb48cff);
        kit.after(350, function () { L.segs[i].visible = false; kit.fly(L.segs[i].position.clone(), tile, { color: 0xffffff, hatch: true, ms: 850, size: [3.2 * ch.bytes / M.chunk, 0.8, 2.4], up: 4, done: done }); });
      } }); });
    },
    card: function () {
      var rows = D.desc.chunks.map(function (n, k) { var r = ['chunk[' + k + '] on the descriptor', hx(n) + (k <= i ? '  holds ' + D.chunks[k].bytes + ' B' : k < NCH ? '  next' : '  not needed')]; r.hot = k === i; return r; });
      return L.tableCard('Where the stream goes <span>(numbers written by KERNEL SW)</span>', rows);
    } });
});

/* ---- checksum */
step({ who: 'hw', title: '算 checksum', cam: L.VIEW.engine, keep: [K.engine],
  text: '<p>LZ4 HW 對這 ' + SL + ' B 的 stream 算 CRC-32，得到 ' + c(CK) + '。之後解壓縮時會重算一次，對不上就代表 chunk 裡的資料壞了。</p>'
    + '<p>stream 經過 engine 的時候順便算，不用再讀一次 DRAM。</p>'
    + '<p>硬體算出來之後沒有地方可以自己記：它要把這個數字交回給 kernel。</p>',
  apply: function (S) { S.pos.hw = 'h_engine'; S.say.hw = 'CRC-32 of the stream:\n' + CK; },
  card: function () { return L.tableCard('Checksum', [['over', 'the ' + SL + ' B stream (compressed bytes)'], ['CRC-32', CK], ['kept by', 'KERNEL SW, once it is reported'], ['used again', 'when the page is decompressed']]); } });

/* ---- completion */
var total = D.done.dram_accesses * M.dram_ns + M.comp_ns;
step({ who: 'hw', title: '寫 completion，發 IRQ', cam: L.VIEW.done, keep: [K.done, K.irq], card: doneCard,
  text: '<p>LZ4 HW 把結果寫進 completion ring 的一格（第 3 次 DRAM 存取），16 B：' + c('status = ' + D.done.status) + '（' + D.done.status_name + '）、' + c('length = ' + D.done.length) + '、' + c('checksum = ' + CK) + '，以及從 descriptor 抄回來的 ' + c('tag = ' + hx(D.done.tag)) + '。然後拉 IRQ 通知 kernel。</p>'
    + '<p>completion 裡沒有 chunk 號碼：號碼本來就是 kernel 給的。kernel 需要的新資訊只有兩個，<b>length</b> 和 <b>checksum</b>。</p>'
    + (total === D.done.lat_ns ? '<p>整個 job 花了 ' + D.done.dram_accesses + ' × ' + ns(M.dram_ns) + ' ns + ' + ns(M.comp_ns) + ' ns = ' + D.done.lat_ns + ' ns。硬體的工作到此結束，它不留下任何紀錄。</p>' : ''),
  apply: function (S) { S.pos.hw = 'h_done'; put(S, 'done', { status: D.done.status_name, flags: '' + D.done.flags, length: '' + D.done.length, checksum: hx(D.done.checksum, 8), tag: hx(D.done.tag), aux: '' + D.done.aux }, 'h');
    S.done.hot = []; S.irq = 1; led(S, 'done', 'h', 'W'); S.clk.dram = 3;
    S.say.hw = 'KERNEL SW, job done.\nTag ' + hx(D.done.tag) + ': ' + D.done.status_name + '.\nLength ' + D.done.length + ' B,\nchecksum ' + hx(D.done.checksum, 8) + '.\nThe rest is yours.'; },
  fx: function (done) { kit.after(900, function () { done(); kit.ping(L.IRQ.clone(), 0xb48cff, 3); }); } });

/* ---- kernel does the books */
step({ who: 'kernel', title: '讀 completion，認出是哪個 job', cam: L.VIEW.kread, keep: [K.done], card: doneCard,
  text: '<p>IRQ 進來，kernel 讀 completion。格子右上角的黃色小角代表「kernel 讀過」。</p>'
    + '<p>' + c('tag = ' + hx(D.done.tag)) + ' 對到剛才那個 job，' + c('status = ' + D.done.status) + ' 代表成功。kernel 記下 ' + c('length = ' + D.done.length) + ' 和 ' + c('checksum = ' + CK) + '。</p>'
    + '<p>接下來記帳的事全部是 kernel 自己做。</p>',
  apply: function (S) { S.pos.kernel = 'k_done'; S.pos.hw = 'h_home'; S.irq = 0; readAll(S, 'done', 'k'); S.done.hot = ['status', 'length', 'checksum', 'tag']; led(S, 'done', 'k', 'R');
    S.say.kernel = 'Tag ' + hx(D.done.tag) + ': that is my job.\nStatus ' + D.done.status_name + ', ' + D.done.length + ' B.\nNow I do the books.'; } });

var cotVals = {}; D.cot.chunks.forEach(function (n, i) { cotVals['chunk[' + i + ']'] = hx(n); });
step({ who: 'kernel', title: '寫 COT：flags 和 count', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>現在要把「page ' + H + ' 壓縮後在哪裡」記下來。這張表叫 <b>COT</b>，每個 page 一筆 32 B，放在 DRAM。page ' + H + ' 這一筆在 ' + c('cot_base + ' + H + ' × 32') + ' = ' + c(hx(V.entry_pa)) + '，壓縮前 32 B 全是 0，意思是「這個 page 沒有壓縮資料」。</p>'
    + '<p>kernel 先算用了幾個 chunk：' + c('ceil(' + D.done.length + ' / ' + M.chunk + ') = ' + NCH) + '。然後寫入 ' + c('flags = ' + hx(D.cot.flags, 2)) + '（bit0 VALID；bit1 RO 和 bit2 RAW 都是 0）以及 ' + c('count = ' + NCH) + '。</p>'
    + '<p>kernel 實際上是一次把 32 B 寫出去，這裡拆成 4 步慢慢看。<b>黃色代表 kernel 寫的</b>：在這個設計裡，COT 從頭到尾只有 kernel 在讀寫。</p>',
  apply: function (S) { S.pos.kernel = 'k_cot'; put(S, 'cot', { flags: 'VALID', count: '' + NCH }, 'k'); led(S, 'cot', 'k', 'W'); S.say.kernel = 'I write COT[' + H + '] myself:\nVALID, ' + NCH + ' chunks.'; } });
step({ who: 'kernel', title: '寫 COT：comp_len', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>' + c('comp_len = ' + SL) + '，從 completion 的 ' + c('length') + ' 抄過來，16 進位 ' + c(hx(SL, 4)) + '，little-endian 寫成 ' + c(hexOf(bCot, 2, 2)) + '。</p>'
    + '<p>解壓縮時靠它知道最後一個 chunk 只有 ' + LAST + ' B 是有效的。</p>',
  apply: function (S) { put(S, 'cot', { comp_len: '' + SL }, 'k'); S.say.kernel = 'comp_len ' + SL + ',\nfrom the completion.'; } });
step({ who: 'kernel', title: '寫 COT：checksum', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>' + c('checksum = ' + CK) + '，也是從 completion 抄過來的，寫成 ' + c(hexOf(bCot, 4, 4)) + '。</p>'
    + '<p>CRC 是硬體算的，但保存它的是 kernel。解壓縮時 kernel 會把它寫進 descriptor 交給硬體核對。</p>',
  apply: function (S) { put(S, 'cot', { checksum: CK }, 'k'); S.say.kernel = 'checksum ' + CK + ',\nfrom the completion.'; } });
step({ who: 'kernel', title: '寫 COT：chunk 號碼', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>最後是 ' + NCH + ' 個 chunk 號碼。kernel 不用問硬體：它知道自己在 descriptor 上列的順序，也知道硬體照順序用了前 ' + NCH + ' 個，所以就是 ' + spanZh(D.cot.chunks) + '。每個號碼 3 B：' + c(hx(D.cot.chunks[0])) + ' 寫成 ' + c(hexOf(bCot, 8, 3)) + '。</p>'
    + '<p>一筆最多記 8 個 chunk。' + (NCH < 8 ? '這次只用 ' + NCH + ' 個，' + c('chunk[' + NCH + ']') + ' 之後維持 0。' : '') + '</p>'
    + '<p>到這裡 COT entry 完成。整筆都是 kernel 寫的，LZ4 HW 沒有碰。</p>',
  apply: function (S) { put(S, 'cot', cotVals, 'k'); S.say.kernel = 'chunks ' + span(D.cot.chunks) + ':\nthe first ' + NCH + ' I put on the descriptor.'; } });

/* ---- trim */
if (TRIM.length) step({ who: 'kernel', title: '把沒用到的 ' + TRIM.length + ' 個 chunk 還回去', cam: L.VIEW.bitmap, keep: [K.bitmap],
  text: '<p>預留了 ' + need + ' 個，實際只用 ' + NCH + ' 個。kernel 把多拿的 ' + spanZh(TRIM) + ' 在 bitmap 裡從 1 寫回 0（黃框）。</p>'
    + '<p>word ' + BM.word + ' 的值從 ' + c('0x' + BM.reserved.toUpperCase()) + ' 變成 ' + c('0x' + BM.after.toUpperCase()) + '，空 chunk 從 ' + BM.free_reserved + ' 個變 ' + BM.free_after + ' 個。和開始前的 ' + BM.free_before + ' 個相比，這個 page 淨用掉 ' + (BM.free_before - BM.free_after) + ' 個。</p>'
    + '<p>現在兩本帳是一致的：bitmap 上標成 1 的那 ' + NCH + ' 個 bit，正好是 COT[' + H + '] 列的 ' + NCH + ' 個 chunk。</p>'
    + '<p>simulator 把 kernel 為這個 job 做的記帳（bitmap、COT entry）算成固定的 ' + ns(M.kernel_job_ns) + ' ns。</p>',
  apply: function (S) { S.pos.kernel = 'k_bm'; S.bm.word = BM.after; S.bm.free = BM.free_after; TRIM.forEach(function (n) { S.bm.mark[bit(n)] = 'c'; S.ch[RES.indexOf(n)] = 4; }); S.bm.hot = TRIM.map(bit); S.clk.k = 1;
    S.say.kernel = 'I reserved ' + need + ', the page needed ' + NCH + '.\n' + TRIM.length + ' bits back to 0: chunks\n' + span(TRIM) + ' are free again.'; },
  fx: function (done) { kit.after(500, function () { TRIM.forEach(function (n, i) { kit.after(i * 140, function () { kit.ping(L.bitAt(n), 0xf4d35e, 1.2); }); }); kit.after(TRIM.length * 140 + 300, done); }); },
  card: function (S) { return bmCard(S, [['bits cleared by KERNEL SW', '<span class="by k">' + TRIM.length + ' bits</span>: chunks ' + span(TRIM)], ['bits that stay 1', NCH + ': chunks ' + span(D.cot.chunks)], ['free chunks', BM.free_before + ' at the start, ' + BM.free_reserved + ' while reserved, now ' + BM.free_after]]); } });

if (TRIM.length) step({ who: 'kernel', title: 'chunk pool 的結果', cam: L.VIEW.chunks, keep: D.tiles.map(function (t, i) { return K['ch' + i]; }),
  text: '<p>回頭看這 ' + need + ' 個 chunk：前 ' + NCH + ' 個裝著 page ' + H + ' 的壓縮資料，' + NCH + ' × ' + M.chunk + ' = ' + NCH * M.chunk + ' B 裝了 ' + SL + ' B' + (LAST < M.chunk ? '，最後一個有 ' + (M.chunk - LAST) + ' B 沒用到' : '') + '。</p>'
    + '<p>後 ' + TRIM.length + ' 個又是空的，下一個要壓縮的 page 會從 bitmap 再找到它們。這 ' + TRIM.length + ' 個 chunk 從預留到歸還，裡面的內容沒有人動過。</p>',
  apply: function (S) { S.pos.kernel = 'k_tiles'; S.clk.k = 1; S.say.kernel = NCH + ' chunks hold the page,\n' + TRIM.length + ' are free again.'; },
  card: function () { return L.tableCard('The ' + need + ' chunks after the job', D.tiles.map(function (t, i) { return ['chunk ' + hx(t.n), i < NCH ? t.bytes + ' B of page ' + H + (t.bytes < M.chunk ? ', ' + (M.chunk - t.bytes) + ' B unused' : '') + ' · bit = 1' : 'free again · bit = 0']; })); } });

step({ who: 'kernel', title: '放掉 frame', cam: L.VIEW.frame, keep: [K.frame],
  text: '<p>資料已經安全地存在 chunk 裡，帳也記好了。kernel 把 <b>frame ' + V.frame + '</b> 放回空 frame 清單，空 frame 從 ' + D.frames.free_before + ' 變 ' + D.frames.free_after + '。</p>'
    + '<p>它也把 page ' + H + ' 的狀態從 ' + c('compressing') + ' 改成 ' + c('compressed') + '。PTE 維持 valid = 0：' + V.name + ' 下次碰這個 page 時會被 access gate 攔下。</p>',
  apply: function (S) { S.pos.kernel = 'k_frame'; S.frame.st = 'free'; S.frame.hot = true; S.free = D.frames.free_after; S.pte.st = 'compressed'; S.clk.k = 1;
    S.say.kernel = 'Frame ' + V.frame + ' is free again:\n' + D.frames.free_after + ' free frames.'; },
  card: function () { return L.tableCard('What KERNEL SW changed', [['free frames', D.frames.free_before + ', now <span class="by k">' + D.frames.free_after + '</span>'], ["kernel's page state", 'compressing, now <span class="by k">compressed</span>'], ['PTE valid bit', 'stays 0']]); } });

/* ---- result, and the same job in the hardware-leaning lesson */
var same = HW && HW.same, swNs = D.done.lat_ns + M.kernel_job_ns;
var cmpText = same
  ? '<p><b>和偏硬體那一課對照</b>（同一次存取、同一個 page ' + H + '）：</p><ul style="margin:6px 0 0 18px;padding:0">'
    + '<li>空 chunk 的帳：那邊是 LZ4 HW 的 SRAM 裡的 stack，這邊是 kernel 記憶體裡的 bitmap。所以那邊拿到 ' + list(HW.chunks) + '（stack 頂端有什麼拿什麼），這邊拿到 ' + list(D.cot.chunks) + '（bitmap 從低位找）。</li>'
    + '<li>COT：那邊硬體寫，這邊 kernel 寫。內容的格式完全一樣。</li>'
    + '<li>descriptor：那邊 ' + HW.desc_bytes + ' B，只給 page 編號；這邊 48 B，直接列出 chunk 號碼。</li>'
    + '<li>硬體的 DRAM 存取：那邊 ' + HW.dram_accesses + ' 次（多一次寫 COT），這邊 ' + D.done.dram_accesses + ' 次。job 時間 ' + HW.lat_ns + ' ns 對 ' + D.done.lat_ns + ' ns，但這邊 kernel 多做 ' + ns(M.kernel_job_ns) + ' ns 的記帳，合計 ' + ns(swNs) + ' ns。</li>'
    + '<li>多出來的步驟：先預留 ' + need + ' 個、事後還 ' + TRIM.length + ' 個。那邊硬體壓完才拿 chunk，不需要預留。</li></ul>'
  : '<p>偏硬體那一課用的是另一個 page' + (HW ? '（page ' + hx(HW.h) + '，第 ' + HW.access_no + ' 次存取）' : '') + '，數字不能直接對照，但分工的差別一樣：那邊空 chunk 的清單和 COT 都在硬體手上，這邊都在 kernel 手上。</p>';
step({ who: 'note', title: '結果：誰碰了什麼', cam: L.VIEW.all,
  text: '<p>一個 ' + M.page + ' B 的 frame 空出來了，代價是 ' + NCH + ' 個 chunk 共 ' + NCH * M.chunk + ' B，外加 COT 裡本來就預留的 32 B。</p>'
    + '<p>看下面的表：<b class="h">LZ4 HW</b> 只讀了 descriptor 和 frame，只寫了 chunk 和 completion。bitmap 和 COT 它從來沒碰過。<b class="k">KERNEL SW</b> 則多了兩本帳要記。這就是「偏軟體」的意思：容易出錯的記帳留在軟體，硬體每個 job 都從零開始。</p>'
    + cmpText
    + '<p>回收會繼續，直到空 frame 回到 ' + M.fc_high + ' 個，然後 ' + RQ.name + ' 才拿到它要的 frame。下一課：' + V.name + ' 之後再碰 page ' + H + ' 時，PTE 是 invalid，觸發<b>解壓縮</b>。</p>',
  apply: function (S) { S.final = true; S.clk.k = 1; S.pos.kernel = 'k_home'; S.pos.hw = 'h_home'; S.say.req = 'Still waiting for my frame.'; S.say.kernel = 'Next victim, until\n' + M.fc_high + ' frames are free.'; S.say.hw = 'I have forgotten\nthis job already.'; },
  card: function () {
    var h = L.tableCard('Before and after, page ' + H, [['DRAM used by the page', M.page + ' B frame, now ' + NCH + ' × ' + M.chunk + ' = ' + NCH * M.chunk + ' B of chunks'], ['free frames', D.frames.free_before + ', now ' + D.frames.free_after],
      ['PTE', 'valid 1, now 0'], ['COT[' + H + ']', 'all zero, now VALID with ' + NCH + ' chunks'], ['free chunks in the bitmap', BM.free_before + ', now ' + BM.free_after]]);
    if (same) h += L.tableCard('Same page, same access, two designs', [
      ['', '<b class="h">HW-leaning</b> · <b class="k">SW-leaning (this lesson)</b>'],
      ['who knows the free chunks', 'LZ4 HW (stack in SRAM) · KERNEL SW (bitmap)'],
      ['chunks the page got', list(HW.chunks) + ' · ' + list(D.cot.chunks)],
      ['who writes COT[' + H + ']', 'LZ4 HW · KERNEL SW'],
      ['job descriptor', HW.desc_bytes + ' B · 48 B'],
      ['DRAM accesses of the job', HW.dram_accesses + ' · ' + D.done.dram_accesses],
      ['job time', HW.lat_ns + ' ns · ' + D.done.lat_ns + ' ns + ' + ns(M.kernel_job_ns) + ' ns kernel work = ' + ns(swNs) + ' ns']]);
    return h;
  } });

var reqCss = A.req ? A.req.css : '#ff8fb1';
var lesson = new R.Lesson({
  kit: kit, steps: steps, init: init, pose: L.pose,
  show: L.show,
  card: function (S, st) { return st.card ? st.card(S) : ''; },
  clock: function (S) {
    if (!S.clk.on) return 'LZ4 HW job time: not started';
    var t = S.clk.dram * M.dram_ns + S.clk.lz * M.comp_ns;
    return 'LZ4 HW job time so far: <b>' + S.clk.dram + ' × ' + ns(M.dram_ns) + ' ns</b> DRAM' + (S.clk.lz ? ' + <b>' + ns(M.comp_ns) + ' ns</b> LZ4' : '') + ' = <b>' + ns(t) + ' ns</b>'
      + (S.clk.k ? ' · KERNEL SW bookkeeping: <b>+ ' + ns(M.kernel_job_ns) + ' ns</b>' : '');
  },
  ledger: [['pte', 'PTE of page ' + H], ['bitmap', 'free-chunk bitmap'], ['desc', 'job descriptor'], ['bell', 'DOORBELL register'], ['frame', 'frame data (' + M.page + ' B)'],
           ['chunk', 'chunks (compressed data)'], ['done', 'completion'], ['cot', 'COT[' + H + ']']],
  who: { user: ['USER SW', reqCss], kernel: ['KERNEL SW', '#f4d35e'], hw: ['LZ4 HW · HARDWARE', '#b48cff'], note: ['SUMMARY', '#7ee2a8'] }
});
var chip = document.getElementById('design');
document.getElementById('title').textContent = 'LZ4 DRAM compression lesson';
chip.textContent = 'SW-LEANING DESIGN'; chip.style.background = '#f4d35e'; chip.style.color = '#10161d';
document.getElementById('scene').textContent = 'Scene: COMPRESS one RW page · real job from simulator run seed ' + M.seed + ', access ' + RQ.access_no;
R.lesson = lesson;
})();

/* Lesson scene "decompress-sw": the steps of the software-leaning design. A user program touches a
   page whose PTE is invalid, the kernel names the case, reads its own COT entry and copies what
   LZ4 HW needs onto the 48 B descriptor. One job follows (DECOMPRESS); the clean-up afterwards
   (COT entry, bitmap) is the kernel's own work, not a second job.
   Prose is zh-TW; what is drawn on the stage is English. */
(function () {
'use strict';
var L = R.L, D = L.D, M = L.M, V = L.V, H = L.H, hx = R.hx, kit = L.kit, A = L.A, T = THREE, NCH = L.NCH, K = L.KEEP;
var RQ = D.req, J = D.desc, C = D.done, B4 = D.before, BM = D.bitmap, REL = BM.released, B0 = BM.first_chunk, HW = D.hw;
var SL = D.stream.len, LAST = D.stream.sizes[NCH - 1], CK = hx(D.cot.checksum, 8), FPA = hx(V.frame_pa), TAG = hx(J.tag);
var bJ = R.bytes(J.hex), bC = R.bytes(C.hex), bCot = R.bytes(D.cot.before);
var c = function (s) { return '<code>' + s + '</code>'; };
var hexOf = function (arr, a, n) { return arr.slice(a, a + n).map(R.b2).join(' '); };
var fill = function (n, v) { var a = [], i; for (i = 0; i < n; i++) a.push(v); return a; };
var list = function (a) { return a.map(function (n) { return hx(n); }).join(', '); };
var run = function (a) { var i; for (i = 1; i < a.length; i++) if (a[i] !== a[i - 1] + 1) return false; return a.length > 2; };
var span = function (a) { return run(a) ? hx(a[0]) + ' to ' + hx(a[a.length - 1]) : list(a); };
var spanZh = function (a) { return run(a) ? c(hx(a[0])) + ' 到 ' + c(hx(a[a.length - 1])) : a.map(function (n) { return c(hx(n)); }).join('、'); };
var bit = function (n) { return n - B0; };
var ns = function (x) { return Math.round(x * 10) / 10; };
var RW = RQ.w ? 'write' : 'read', RWZ = RQ.w ? '寫' : '讀';
var CHF = D.cot.chunks.map(function (n, i) { return 'chunk[' + i + ']'; });

var cotVals = { flags: 'VALID', count: '' + NCH, comp_len: '' + SL, checksum: CK };
D.cot.chunks.forEach(function (n, i) { cotVals['chunk[' + i + ']'] = hx(n); });
var init = {
  pos: { kernel: 'k_home', hw: 'h_home', req: 'ui_home' }, say: {}, gate: 'idle', card: null, final: false,
  pte: { valid: 0, st: 'compressed', hot: false, w: false }, free: D.frames.free_before,
  frame: { st: 'free', hot: false },
  desc: { b: fill(48, null), w: fill(48, null), r: fill(48, ''), vals: {}, hot: [] },
  cot: { b: bCot.slice(), w: fill(32, 'k'), r: fill(32, ''), vals: cotVals, hot: [] },
  done: { b: fill(16, null), w: fill(16, null), r: fill(16, ''), vals: {}, hot: [] },
  bm: { word: BM.before, mark: {}, hot: [], free: BM.free_before },
  bell: 0, irq: 0, eng: { on: 0, vis: fill(NCH, false), lab: '' }, ch: fill(NCH, 2), chHot: -1,
  led: {}, clk: { on: false, dram: 0, lz: 0, k: 0 }
};
var SRC = { desc: bJ, done: bC };
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
var steps = [], lesson;
function step(o) { var ap = o.apply; o.apply = function (S) { calm(S); S.card = steps.indexOf(o); ap(S); }; steps.push(o); }

/* ---- the stage and where the page is right now */
var nowCard = function () { return L.tableCard('Page ' + H + ' of ' + V.name + ' right now', [
    ['compressed at', 'access ' + B4.access_no + ', ' + B4.accesses_ago + ' accesses ago'],
    ['frame', 'none (it had frame ' + B4.frame + ', given away since)'],
    ['data', SL + ' B of LZ4 stream in ' + NCH + ' chunks: ' + list(D.cot.chunks)],
    ['COT[' + H + ']', 'VALID, written by KERNEL SW when the page was compressed'],
    ['bitmap', 'bits ' + bit(REL[0]) + ' to ' + bit(REL[REL.length - 1]) + ' of word ' + BM.word + ' are 1'],
    ['PTE', 'valid = 0'], ["kernel's note", 'compressed']]); };
var glossary = function () { return L.tableCard('Words used in this lesson', [
    ['page', '軟體看到的 ' + M.page + ' B 記憶體單位，用編號稱呼'],
    ['frame', 'DRAM 裡一塊 ' + M.page + ' B 的空間，放一個未壓縮的 page'],
    ['chunk', 'DRAM 裡 ' + M.chunk + ' B 的小塊，放壓縮後的資料'],
    ['PTE', 'page table entry，決定 user SW 的存取能不能直接通過'],
    ['COT', 'compressed object table，每個 page 一筆 32 B，記壓縮後的資料在哪些 chunk'],
    ['bitmap', 'kernel 自己的帳本，每個 chunk 1 個 bit，記它是空的還是用掉了'],
    ['descriptor', 'kernel 寫給 LZ4 HW 的工作單，48 B'],
    ['completion', 'LZ4 HW 回報結果的單子，16 B']]); };
step({ who: 'note', title: '舞台，以及這個 page 現在的樣子', cam: L.VIEW.all, card: function () { return nowCard() + glossary(); },
  text: '<p>這一課用一個真實的例子，看「解壓縮一個 page」從頭到尾發生的事。所有數字都來自 simulator 的同一次執行，而且就是上一課被壓縮的那個 page。</p>'
    + '<p>三種角色：<b>USER SW</b>（遠端的 ' + M.clients.join('、') + '）是被服務的程式，只管讀寫自己的 page。<b class="k">KERNEL SW</b>（黃色）管理記憶體，在這個<b>偏軟體</b>的設計裡也自己記兩本帳。<b class="h">LZ4 HW</b>（紫色機器人）是硬體加速器，兩個 job 之間什麼都不記得。</p>'
    + '<p>先看現況。<b>page ' + H + '</b> 屬於 ' + V.name + '，在第 ' + B4.access_no + ' 次存取時被壓縮，之後 ' + B4.accesses_ago + ' 次存取都沒有人碰它。它現在<b>沒有 frame</b>：左邊那塊 frame 是空的。它的內容是 ' + SL + ' B 的 LZ4 stream，躺在 ' + NCH + ' 個畫斜線的 chunk 裡。PTE 的 valid 是 0。</p>'
    + '<p>最靠近你的是 kernel 的兩本帳。右邊 COT[' + H + '] 是上一課 kernel 自己寫的（黃色）。左邊 bitmap 的 word ' + BM.word + ' 和上一課結尾時不一樣了，因為這段期間別的 page 也拿過、還過 chunk；但 bit ' + bit(REL[0]) + ' 到 ' + bit(REL[REL.length - 1]) + ' 還是 1，它們就是這 ' + NCH + ' 個 chunk。</p>'
    + '<p>按 Next 一步一步看，畫面可以拖曳旋轉、滾輪縮放。</p>',
  apply: function (S) { S.say.kernel = 'I am the kernel.\nI manage the memory and,\nin this design, I keep the books.'; S.say.hw = 'I am the LZ4 accelerator.\nI remember nothing between jobs.'; S.say.req = 'I am ' + RQ.name + ', a program.\nI just read and write my pages.'; } });

/* ---- the access that starts everything */
step({ who: 'user', title: RQ.name + ' ' + RWZ + ' page ' + H + '，被 access gate 攔下', cam: L.VIEW.far, keep: [K.gate, K.pte],
  text: '<p><b>' + RQ.name + '</b> 要' + RWZ + '自己的 page ' + c(H) + '。它不知道這個 page 被壓縮過，也不需要知道，它只是照常存取。</p>'
    + '<p>所有 user SW 的存取都經過同一個 <b>access gate</b>（MMU 查 page table）。gate 查到 page ' + H + ' 的 PTE：' + c('valid = 0') + '。這次存取就停在這裡，CPU 進入 page fault，把 <b class="k">KERNEL SW</b> 叫來。</p>'
    + '<p>注意：<b>沒有人下令「解壓縮」</b>。解壓縮是被這次停下來的存取觸發的。這一段和偏硬體的設計完全一樣：user SW 和 gate 看不出背後是哪一種設計。</p>',
  apply: function (S) { S.pos.req = 'ui_gate'; S.gate = 'stop'; S.pte.hot = true; S.pos.kernel = 'k_call';
    S.say.req = RW + ' page ' + H; S.say.gate = 'PTE of page ' + H + ': valid = 0.\nThis access stops here.\nKERNEL SW is called.'; },
  card: function () { return L.tableCard('The access', [['who', 'USER SW ' + RQ.name], ['what', RW + ' page ' + H + ' (access ' + RQ.access_no + ' of the run)'], ['PTE valid bit', '0'], ['result', 'page fault: KERNEL SW is called']]); } });

step({ who: 'kernel', title: '為什麼 invalid？kernel 認出是哪一種情況', cam: L.VIEW.pte, keep: [K.pte, K.gate],
  text: '<p>PTE invalid 有好幾種原因，gate 分不出來，只有 kernel 知道。kernel 查自己的筆記：page ' + H + ' 的狀態是 ' + c('compressed') + '。所以這次的情況是「要解壓縮」。</p>'
    + '<p>在這個偏軟體的設計裡，kernel 知道的不只這個詞。壓縮後的資料在哪幾個 chunk、有多長、checksum 是多少，都記在 COT，而 <b>COT 是 kernel 自己的帳</b>。等一下它會自己去讀。</p>',
  apply: function (S) { S.pos.kernel = 'k_gate'; S.pte.hot = true;
    S.say.kernel = 'Page fault on page ' + H + '.\nMy note says: compressed.\nThis case: decompress it.'; S.say.req = 'waiting…'; },
  card: function () { var rows = [['untouched', 'first use: give it a zeroed frame, no LZ4 HW'], ['compressed', 'this case: get a frame, read the COT entry, ask LZ4 HW to DECOMPRESS'], ['compressing / decompressing', 'a job is under way: wait for it'], ['lost', 'the data failed its check: report the error']];
    rows[1].hot = true; return L.tableCard("Why a PTE can be invalid <span>(kernel's note about the page)</span>", rows); } });

step({ who: 'kernel', title: '拿一個空的 frame', cam: L.VIEW.frame, keep: [K.frame],
  text: '<p>解壓縮後的 ' + M.page + ' B 要有地方放。kernel 從空 frame 清單拿出 <b>frame ' + V.frame + '</b>，實體位址 ' + c(hx(M.fc_base) + ' + ' + V.frame + ' × ' + M.page) + ' = ' + c(FPA) + '。空 frame 從 ' + D.frames.free_before + ' 變 ' + D.frames.free_after + '。</p>'
    + '<p>' + D.frames.free_before + ' 個還高於門檻 ' + M.fc_low + ' 個，所以這次不用先回收別的 page。如果不夠，kernel 要先做上一課的壓縮，' + RQ.name + ' 就得等更久。</p>'
    + '<p>這個 page 上次住在 frame ' + B4.frame + '，這次是 frame ' + V.frame + '。page 編號不變，frame 每次都可能不同，這就是 PTE 要重寫的原因。</p>',
  apply: function (S) { S.pos.kernel = 'k_frame'; S.frame.st = 'taken'; S.frame.hot = true; S.free = D.frames.free_after;
    S.say.kernel = 'I take free frame ' + V.frame + '\nfor page ' + H + '.\n' + D.frames.free_after + ' free frames left.'; },
  card: function () { return L.tableCard('What KERNEL SW changed', [['free frames', D.frames.free_before + ', now <span class="by k">' + D.frames.free_after + '</span>'], ['frame for page ' + H, 'frame ' + V.frame + ' @' + FPA], ['reclaim needed', 'no: ' + D.frames.free_before + ' is above ' + M.fc_low]]); } });

/* ---- the kernel reads its own COT entry */
function kc(o) { var ap = o.apply; o.who = 'kernel'; o.cam = L.VIEW.cot; o.keep = [K.cot]; o.apply = function (S) { S.pos.kernel = 'k_cot'; ap(S); }; step(o); }
kc({ title: 'kernel 自己讀 COT[' + H + ']', card: cotCard,
  text: '<p>資料在哪裡？kernel 自己去查。COT entry 的位址是 ' + c('cot_base + ' + H + ' × 32') + ' = ' + c(hx(M.cot_base) + ' + ' + V.h + ' × 32') + ' = ' + c(hx(V.entry_pa)) + '，kernel 從那裡讀出 32 B。</p>'
    + '<p>這 32 B 是上一課 kernel 自己寫的，所以整片是黃色；現在右上角多了黃色小角，代表「kernel 讀過」。</p>'
    + '<p>先看 ' + c('flags = ' + hx(D.cot.flags, 2)) + '：bit0 VALID 是 1，代表這個 page 確實有壓縮資料。bit2 RAW 是 0，代表存的是 LZ4 stream，需要解碼。</p>'
    + '<p>在偏硬體的設計裡，讀這一筆的是 LZ4 HW。這裡硬體根本不知道有 COT 這張表。</p>',
  apply: function (S) { readAll(S, 'cot', 'k'); S.cot.hot = ['flags']; led(S, 'cot', 'k', 'R');
    S.say.kernel = 'I read COT[' + H + '] myself.\nVALID: this page has\ncompressed data.'; } });
kc({ title: '從 COT 讀出：幾個 chunk、多長、哪幾個、checksum',
  text: '<p>' + c('count = ' + NCH) + '：資料在 ' + NCH + ' 個 chunk 裡。</p>'
    + '<p>' + c('comp_len') + ' 的 2 個 byte 是 ' + c(hexOf(bCot, 2, 2)) + '，little-endian 讀回來是 ' + c(hx(SL, 4)) + ' = ' + SL + ' B。前 ' + (NCH - 1) + ' 個 chunk 各 ' + M.chunk + ' B，最後一個只有 ' + c(SL + ' − ' + (NCH - 1) + ' × ' + M.chunk + ' = ' + LAST) + ' B 是資料。</p>'
    + '<p>' + c('chunk[0..' + (NCH - 1) + ']') + ' 每個 3 B：' + c(hexOf(bCot, 8, 3)) + ' 是 ' + c(hx(D.cot.chunks[0])) + '。排列順序就是 stream 的順序。</p>'
    + '<p>' + c('checksum = ' + CK) + '：壓縮時硬體算出來、交給 kernel 保管的 CRC-32。</p>'
    + '<p>kernel 把筆記裡這個 page 的狀態改成 ' + c('decompressing') + '。這四樣東西接下來要全部抄給硬體。</p>',
  apply: function (S) { S.cot.hot = ['count', 'comp_len', 'checksum'].concat(CHF); S.pte.st = 'decompressing';
    S.say.kernel = NCH + ' chunks, ' + SL + ' B in all:\n' + span(D.cot.chunks) + '.\nChecksum ' + CK + '.'; },
  card: function (S) { var a = 0; return cotCard(S) + L.tableCard('What KERNEL SW now knows', D.chunks.map(function (ch, i) { var r = ['chunk[' + i + '] = ' + hx(ch.n), '@' + hx(ch.pa) + ', ' + ch.bytes + ' B: stream bytes ' + a + ' to ' + (a + ch.bytes - 1)]; a += ch.bytes; return r; })
    .concat([["kernel's page state", 'compressed, now <span class="by k">decompressing</span>']])); } });

/* ---- descriptor, field by field */
var dv = {}, unused = [];
J.chunks.forEach(function (n, i) { dv['chunk[' + i + ']'] = hx(n); });
for (var q = J.chunks.length; q < 8; q++) { dv['chunk[' + q + ']'] = '0'; unused.push('chunk[' + q + ']'); }
dv.pad = '0';
function kd(o) { var ap = o.apply; o.who = 'kernel'; o.cam = L.VIEW.desc; o.keep = [K.desc]; o.card = descCard; o.apply = function (S) { S.pos.kernel = 'k_desc'; ap(S); }; step(o); }
kd({ title: '寫 descriptor：要做什麼、列幾個 chunk',
  text: '<p>kernel 用一張 48 B 的工作單把事情交代給硬體，這就是 <b>job descriptor</b>，放在 DRAM 裡 job ring 的一格。格式和壓縮時完全一樣，只是這次每個欄位都用得到。</p>'
    + '<p>先寫前 2 個 byte：' + c('opcode = ' + J.opcode) + ' 代表 ' + J.op_name + '（1 是 COMPRESS），' + c('count = ' + J.count) + ' 是後面列了幾個 chunk 號碼，就是剛從 COT 讀到的 ' + NCH + '。</p>'
    + '<p>黃色的格子是 kernel 寫的 byte，' + c('--') + ' 是還沒寫的。</p>',
  apply: function (S) { put(S, 'desc', { opcode: 'DEC', count: '' + J.count }, 'k'); led(S, 'desc', 'k', 'W'); S.say.kernel = 'I write the job descriptor.\nopcode ' + J.opcode + ': ' + J.op_name + ',\n' + J.count + ' chunk numbers follow.'; } });
kd({ title: '寫 descriptor：輸出多大',
  text: '<p>' + c('limit = ' + J.limit) + '：解出來的資料是一個 page，' + J.limit + ' B。壓縮時同一個欄位的意思是「超過就放棄」。</p>'
    + '<p>' + J.limit + ' 寫成 16 進位是 ' + c(hx(J.limit, 4)) + '。DRAM 裡是 little-endian，低位的 byte 放前面，所以看到的是 ' + c(hexOf(bJ, 2, 2)) + '。</p>',
  apply: function (S) { put(S, 'desc', { limit: '' + J.limit }, 'k'); S.say.kernel = 'limit ' + J.limit + ':\none page comes out.'; } });
kd({ title: '寫 descriptor：解到哪裡',
  text: '<p>' + c('frame_pa = ' + FPA) + '：寫成 ' + c(hexOf(bJ, 4, 4)) + '。壓縮時這個欄位是「資料從哪裡讀」，這次是「解出來的資料<b>寫到哪裡</b>」，就是剛拿到的 frame ' + V.frame + '。</p>'
    + '<p>和壓縮時一樣，單子上沒有 page 編號的欄位。硬體不需要知道這是哪個 page。</p>',
  apply: function (S) { put(S, 'desc', { frame_pa: FPA }, 'k'); S.say.kernel = 'Output goes to\n' + FPA + '.'; } });
kd({ title: '寫 descriptor：壓縮資料有多長',
  text: '<p>' + c('comp_len = ' + J.comp_len) + '：從 COT 抄過來，寫成 ' + c(hexOf(bJ, 8, 2)) + '。硬體靠它知道最後一個 chunk 只取 ' + LAST + ' B。</p>'
    + '<p>' + c('flags = ' + J.flags) + '：只帶 COT 的 RAW bit。0 代表資料是 LZ4 stream，要解碼；1 代表當初壓不小、原樣存放，直接搬就好。</p>'
    + '<p>上一課壓縮時這兩個欄位填 0。它們就是為了這一刻留的：硬體沒有表可以查，kernel 不講它就不知道。</p>',
  apply: function (S) { put(S, 'desc', { comp_len: '' + J.comp_len, flags: '' + J.flags }, 'k'); S.say.kernel = 'comp_len ' + J.comp_len + ', not RAW:\ncopied from my COT entry.'; } });
kd({ title: '寫 descriptor：應該對得上的 checksum',
  text: '<p>' + c('checksum = ' + CK) + '：也是從 COT 抄過來的，寫成 ' + c(hexOf(bJ, 12, 4)) + '。</p>'
    + '<p>意思是「這 ' + SL + ' B 的 CRC-32 <b>應該</b>是這個值」。硬體收齊資料後會自己再算一次來比。kernel 只負責保管和轉交這個數字，不自己算。</p>',
  apply: function (S) { put(S, 'desc', { checksum: CK }, 'k'); S.say.kernel = 'checksum ' + CK + ':\nwhat the data must add up to.'; } });
kd({ title: '寫 descriptor：tag',
  text: '<p>' + c('tag = ' + TAG) + '：kernel 自己取的編號，硬體做完會原封不動抄回來。kernel 填的是 page 編號，對硬體來說只是一個要抄回去的數字。</p>',
  apply: function (S) { put(S, 'desc', { tag: TAG }, 'k'); S.say.kernel = 'tag ' + TAG + ': so I know\nthe answer when it comes back.'; } });
kd({ title: '寫 descriptor：' + J.count + ' 個 chunk 號碼',
  text: '<p>最後是 COT 裡那 ' + J.count + ' 個 chunk 號碼，<b>照 COT 的順序</b>抄：' + spanZh(J.chunks) + '。每個號碼 3 B：' + c(hx(J.chunks[0])) + ' 寫成 ' + c(hexOf(bJ, 20, 3)) + '。順序錯了，接起來的 stream 就是錯的。</p>'
    + (unused.length ? '<p>' + unused.map(c).join('、') + ' 和最後 4 B 的 pad 寫 0。</p>' : '')
    + '<p>48 B 寫完了。對照 COT entry：' + c('comp_len') + '、' + c('checksum') + '、chunk 號碼全部抄了一份到單子上。<b>硬體解這個 page 需要知道的一切，都在這 48 B 裡。</b></p>',
  apply: function (S) { put(S, 'desc', dv, 'k'); S.desc.hot = CHF; S.say.kernel = 'chunks ' + span(J.chunks) + ',\nin the order of the stream.'; },
  card: function (S) { return descCard(S) + L.tableCard('Copied from COT[' + H + '] to the descriptor', [['count', '' + NCH], ['comp_len', SL + ' B'], ['flags', 'RAW bit only: ' + J.flags], ['checksum', CK], ['chunk[0..' + (NCH - 1) + ']', list(J.chunks)]]); } });

/* ---- the briefing and the doorbell */
step({ who: 'kernel', title: '交代工作，按 doorbell', cam: L.VIEW.desk, keep: [K.desc, K.bell], card: descCard,
  text: '<p>descriptor 只是躺在 DRAM 裡，硬體還不知道。kernel 對 <b>DOORBELL</b> register 做一次 MMIO 寫入，告訴 LZ4 HW「job ring 有新工作」。</p>'
    + '<p>聽 kernel 怎麼交代：資料在哪幾個 chunk、多長、checksum 應該是多少、解到哪裡，全部講明。硬體不用查任何東西，照做再回報就好。之後 kernel 等 IRQ，' + RQ.name + ' 還停在 gate 前面。</p>',
  apply: function (S) { S.pos.kernel = 'k_bell'; S.bell = 1; led(S, 'bell', 'k', 'W');
    S.say.kernel = 'LZ4 HW, a job for you:\n' + J.op_name + ' to ' + FPA + '.\nThe data is ' + SL + ' B in chunks\n' + span(J.chunks) + ', in that order.\nIts CRC-32 must be ' + CK + ':\nif it is not, write nothing.\nReport back with tag ' + TAG + '.';
    S.say.hw = 'Understood. I read only\nthe chunks you name.'; },
  fx: function (done) { kit.after(700, function () { kit.ping(L.BELL.clone(), 0xf4d35e, 3); done(); }); } });

/* ---- the job: the hardware */
function hw(o) { var ap = o.apply; o.who = 'hw'; o.apply = function (S) { S.pos.kernel = 'k_home'; S.bell = 0; ap(S); }; step(o); }
var maxChunk = Math.max.apply(null, J.chunks);
hw({ title: '讀 descriptor，檢查', cam: L.VIEW.read, keep: [K.desc],
  text: '<p>LZ4 HW 從 job ring 讀出這 48 B（第 1 次 DRAM 存取）。格子右上角的紫色小角代表「LZ4 HW 讀過」。</p>'
    + '<p>硬體不相信單子上的數字，先檢查：opcode 是認得的；' + c('count') + ' 不超過 8；每個 chunk 號碼都小於 chunk 總數 ' + M.pool_chunks + '；' + c('frame_pa') + ' 落在 frame 區而且對齊 ' + M.page + ' B。任何一項不合格就回報 BAD_DESC，什麼都不動。</p>'
    + '<p>接下來它<b>不用讀 COT</b>。偏硬體的設計在這裡要多一次 DRAM 存取去讀 COT；這裡需要的東西已經在單子上了。</p>',
  apply: function (S) { S.pos.hw = 'h_desc'; readAll(S, 'desc', 'h'); led(S, 'desc', 'h', 'R'); S.clk.on = true; S.clk.dram = 1;
    S.say.hw = 'Descriptor read: ' + J.op_name + '.\n' + J.count + ' chunk numbers, all in range.\nI need no table: it is all here.'; },
  card: function (S) { return descCard(S) + L.tableCard('Checks by LZ4 HW', [['opcode known', J.opcode + ' = ' + J.op_name + ': yes'], ['count', J.count + ' ≤ 8: yes'],
    ['every chunk number in range', 'largest ' + hx(maxChunk) + ' = ' + maxChunk + ' &lt; ' + M.pool_chunks + ': yes'], ['frame_pa', FPA + ': in the frame area, multiple of ' + M.page + ': yes'], ['COT read by LZ4 HW', 'none']]); } });

/* ---- gather the chunks, one per step, in the order of the descriptor */
D.chunks.forEach(function (ch, i) {
  var a = i * M.chunk, b = a + ch.bytes - 1, got = a + ch.bytes, f = 'chunk[' + i + ']';
  var t = i === 0
    ? '<p>LZ4 HW 照單子的順序去讀 chunk。descriptor 的 ' + c(f) + ' 是 ' + c(hx(ch.n)) + '，位址 ' + c('pool_base + ' + hx(ch.n) + ' × ' + M.chunk) + ' = ' + c(hx(ch.pa)) + '。讀出 ' + ch.bytes + ' B，是 stream 的第 ' + a + ' 到 ' + b + ' B，接到左邊的 stream 上。</p>'
      + '<p>chunk 本身沒有被改動，斜線還在；紫色的字只是標示硬體讀過。時間模型把讀 chunk 算在 engine 的串流時間裡，所以上面的 DRAM 次數不加。</p>'
    : '<p>下一個照單子上的 ' + c(f) + '：' + c(hx(ch.n)) + '（位址 ' + c(hx(ch.pa)) + '），讀出 ' + ch.bytes + ' B，是 stream 的第 ' + a + ' 到 ' + b + ' B。</p>';
  if (ch.bytes < M.chunk) t += '<p>這個 chunk 只取前 ' + ch.bytes + ' B，後面 ' + (M.chunk - ch.bytes) + ' B 是沒用到的空間，不能送進 engine。能切得這麼準，靠的是單子上的 ' + c('comp_len = ' + SL) + '：' + c(SL + ' − ' + i + ' × ' + M.chunk + ' = ' + ch.bytes) + '。</p>';
  hw({ title: '讀第 ' + (i + 1) + ' 個 chunk，取 ' + ch.bytes + ' B', cam: L.VIEW.work, keep: [K['ch' + i], K.engine], text: t,
    apply: function (S) { S.pos.hw = 'h_ch' + i; S.ch[i] = 3; S.chHot = i; S.eng.vis[i] = true; S.eng.lab = 'stream: ' + got + ' of ' + SL + ' B'; S.desc.hot = [f]; led(S, 'chunk', 'h', 'R');
      S.say.hw = f + ' on the descriptor\nsays ' + hx(ch.n) + '.\nI read ' + ch.bytes + ' B from it.'; },
    fx: function (done) {
      var tile = new T.Vector3(L.CX[i], 1, L.ZROW);
      kit.after(500, function () { kit.fly(L.descAt.clone(), tile, { color: 0xf4d35e, ms: 800, size: [2.4, 0.5, 1.2], up: 5, done: function () {
        kit.ping(tile, 0xb48cff);
        kit.after(350, function () { kit.fly(tile, L.segs[i].position.clone(), { color: 0xffffff, hatch: true, ms: 900, size: [L.SEG * ch.bytes / M.chunk, 0.8, 2.4], up: 5, done: done }); });
      } }); });
    },
    card: function () { return L.tableCard('Chunks named on the descriptor <span>(' + got + ' of ' + SL + ' B gathered)</span>', D.chunks.map(function (x, k) {
      var r = ['chunk[' + k + '] = ' + hx(x.n), (k <= i ? x.bytes + ' B read, starts ' : x.bytes + ' B to read, starts ') + hexOf(R.bytes(x.head), 0, 8)]; r.hot = k === i; return r; })); } });
});

/* ---- CRC against the descriptor */
hw({ title: '先驗 checksum，再動 frame', cam: L.VIEW.engine, keep: [K.engine],
  text: '<p>' + SL + ' B 到齊了。LZ4 HW 對這 ' + SL + ' B 算 CRC-32，得到 ' + c(CK) + '，和 <b>descriptor 上寫的</b> ' + c(CK) + ' 一樣。</p>'
    + '<p>如果不一樣呢？硬體回報 BAD_STREAM，<b>frame 一個 byte 都不寫</b>。kernel 把這個 page 標成 ' + c('lost') + '，再回報錯誤。</p>'
    + '<p>這個檢查在偏軟體的設計裡多擋一種錯：不只是 chunk 裡的資料壞掉，<b>kernel 的帳記錯</b>（例如號碼列錯、順序錯、長度錯）也會讓 CRC 對不上。硬體沒辦法知道 kernel 給的號碼對不對，但它能確定「照這些號碼收到的資料」是不是當初壓出來的那一份。</p>',
  apply: function (S) { S.pos.hw = 'h_engine'; S.desc.hot = ['checksum']; S.say.hw = 'CRC-32 of the ' + SL + ' B: ' + CK + '.\nThe descriptor says ' + CK + '.\nThe data is intact.'; },
  card: function () { return L.tableCard('Checksum check by LZ4 HW', [['CRC-32 over', 'the ' + SL + ' B just gathered'], ['computed now', CK], ['expected, from the descriptor', CK + ': equal'], ['where KERNEL SW got it', 'COT[' + H + '], stored when the page was compressed'], ['if not equal', 'status BAD_STREAM, the frame is not written']]); } });

/* ---- decode into the frame */
var pg = R.bytes(D.page.head), sh = R.bytes(D.stream.head), lit = sh[0] >> 4, li = 1, ext = [], litText = '';
if (lit === 15) { while (li < sh.length && sh[li] === 255) { ext.push(255); lit += 255; li++; } if (li < sh.length) { ext.push(sh[li]); lit += sh[li]; li++; } else li = 99; }
if (li < sh.length - 3 && sh.slice(li, li + 4).join() === pg.slice(0, 4).join()) {
  litText = '<p>看 stream 的開頭怎麼變回 page：第 1 個 byte ' + c(R.b2(sh[0])) + ' 是 token，高 4 bit 是 literal 長度 ' + (sh[0] >> 4)
    + (ext.length ? '，15 表示還要加上後面的 ' + c(ext.map(R.b2).join(' ')) + '：15 + ' + ext.join(' + ') + ' = ' + lit : '')
    + '。所以接下來 ' + lit + ' 個 byte 原樣搬到 frame 開頭，frame 的前 4 B 就是 ' + c(hexOf(pg, 0, 4)) + '。之後遇到 match，就從 frame 裡已經寫好的地方複製。</p>';
}
var ratio = Math.round(M.comp_ns / M.decomp_ns);
hw({ title: 'LZ4 解碼，寫進 frame', cam: L.VIEW.engine, keep: [K.frame, K.engine],
  text: '<p>stream 送進 LZ4 engine 解碼，解出來的 ' + M.page + ' B 寫到 ' + c(FPA) + '（第 2 次 DRAM 存取）。frame ' + V.frame + ' 變成藍色：裡面是 page ' + H + ' 的 RW 資料，和壓縮前一模一樣。</p>'
    + '<p>解碼比編碼簡單，不用找重複的字串，只要照 token 搬資料。engine 每個 cycle 輸出 ' + M.decomp_bytes_per_cycle + ' B，' + M.page + ' B 只要 ' + ns(M.decomp_ns) + ' ns；壓縮時是 ' + ns(M.comp_ns) + ' ns，差 ' + ratio + ' 倍。LZ4 engine 本身在兩種設計裡是同一個。</p>' + litText,
  apply: function (S) { S.pos.hw = 'h_engine'; S.frame.st = 'present'; S.frame.hot = 'write'; S.eng.on = 1; S.eng.vis = fill(NCH, false); S.eng.lab = ''; led(S, 'frame', 'h', 'W'); S.clk.dram = 2; S.clk.lz = 1;
    S.say.hw = 'I LZ4-decode the stream\nand write ' + M.page + ' B\ninto frame ' + V.frame + '.'; },
  fx: function (done) {
    var a = new T.Vector3(-9, 3.4, L.ZROW - 1), b = new T.Vector3(-27, 1.2, L.ZROW), i;
    for (i = 0; i < 4; i++) (function (i) { kit.after(500 + i * 320, function () { kit.fly(a, b, { color: R.COL.rw, ms: 800, size: [2.6, 0.8, 2.6] }); }); })(i);
    kit.after(2400, done);
  },
  card: function () { return L.tableCard('Stream in, frame out', [
    ['stream, first 16 B', hexOf(sh, 0, 16)], ['frame, first 16 B', '<span style="color:var(--rw)">' + hexOf(pg, 0, 16) + '</span>'],
    ['size', SL + ' B in, ' + M.page + ' B out'], ['time in the engine', ns(M.decomp_ns) + ' ns (compress: ' + ns(M.comp_ns) + ' ns)']]); } });

/* ---- completion */
var total = C.dram_accesses * M.dram_ns + M.decomp_ns;
hw({ title: '寫 completion，發 IRQ', cam: L.VIEW.done, keep: [K.done, K.irq], card: doneCard,
  text: '<p>LZ4 HW 把結果寫進 completion ring 的一格（第 3 次 DRAM 存取），16 B：' + c('status = ' + C.status) + '（' + C.status_name + '）、' + c('length = ' + C.length) + '（寫進 frame 的 byte 數）、' + c('checksum = ' + hx(C.checksum, 8)) + '，以及抄回來的 ' + c('tag = ' + hx(C.tag)) + '。然後拉 IRQ。</p>'
    + (total === C.lat_ns ? '<p>這個 job 花了 ' + C.dram_accesses + ' × ' + ns(M.dram_ns) + ' ns + ' + ns(M.decomp_ns) + ' ns = <b>' + C.lat_ns + ' ns</b>。</p>' : '')
    + '<p>硬體的工作到此<b>全部結束</b>。留意現在的狀態：frame 裡有一份未壓縮的資料，' + NCH + ' 個 chunk 裡的壓縮資料還在，COT 還是 VALID，bitmap 那 ' + NCH + ' 個 bit 還是 1。這些收尾硬體不會做，也做不到：兩本帳都不在它手上。</p>',
  apply: function (S) { S.pos.hw = 'h_done'; put(S, 'done', { status: C.status_name, flags: '' + C.flags, length: '' + C.length, checksum: hx(C.checksum, 8), tag: hx(C.tag), aux: '' + C.aux }, 'h');
    S.done.hot = []; S.irq = 1; led(S, 'done', 'h', 'W'); S.clk.dram = 3;
    S.say.hw = 'KERNEL SW, job done.\nTag ' + hx(C.tag) + ': ' + C.status_name + ',\n' + C.length + ' B written to the frame.\nThe chunks are yours to sort out.'; },
  fx: function (done) { kit.after(900, function () { done(); kit.ping(L.IRQ.clone(), 0xb48cff, 3); }); } });

/* ---- the kernel does the clean-up itself */
function kn(o) { var ap = o.apply; o.who = 'kernel'; o.apply = function (S) { S.pos.hw = 'h_home'; ap(S); }; step(o); }
kn({ title: '讀 completion：解好了，收尾自己來', cam: L.VIEW.kread, keep: [K.done],
  text: '<p>IRQ 進來，kernel 讀 completion。格子右上角的黃色小角代表「kernel 讀過」。' + c('tag = ' + hx(C.tag)) + ' 對到剛才的 job，' + c('status = ' + C.status) + ' 代表成功。</p>'
    + '<p>kernel 還不能放行。page ' + H + ' 是 <b>RW page</b>：一旦 ' + V.name + ' 寫了它，chunk 裡那份壓縮資料就過期了。所以 RW page 解回來之後，壓縮的那一份直接作廢，把 ' + NCH + ' 個 chunk 還回去。（RO page 的內容不會變，壓縮的那一份一直留著，沒有接下來這一段。）</p>'
    + '<p>偏硬體的設計在這裡要再交代硬體一個 job（INVALIDATE）。這裡<b>沒有第二個 job</b>：COT 和 bitmap 都是 kernel 的帳，kernel 自己改就好。</p>',
  apply: function (S) { S.pos.kernel = 'k_done'; S.irq = 0; readAll(S, 'done', 'k'); S.done.hot = ['status', 'tag']; led(S, 'done', 'k', 'R');
    S.say.kernel = 'Tag ' + hx(C.tag) + ': ' + C.status_name + '.\nPage ' + H + ' is RW: its compressed\ncopy must go. That is my own work.'; },
  card: function (S) { return doneCard(S) + L.tableCard('After DECOMPRESS, what about the compressed copy?', [['RW page (this one)', 'drop it: KERNEL SW clears COT[' + H + '] and ' + NCH + ' bitmap bits, no job'], ['RO page', 'keep it: the content never changes']]); } });

kn({ title: '把 COT[' + H + '] 清成 0', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>kernel 對 ' + c(hx(V.entry_pa)) + ' 寫入 32 個 ' + c('00') + '。' + c('flags') + ' 的 VALID bit 變 0，意思是「page ' + H + ' 沒有壓縮資料」，和上一課壓縮之前一模一樣。</p>'
    + '<p>先清 COT、再動 bitmap，是有原因的。bitmap 只存在 kernel 的記憶體裡，開機時是從 COT 重建的，所以 COT 才是正本。先改正本，就不會出現「bitmap 說 chunk 是空的、COT 卻還指著它」的時刻。</p>'
    + '<p>看這一筆 COT 的一生：壓縮時 kernel 寫、解壓縮時 kernel 讀、作廢時 kernel 清。<b>LZ4 HW 一次都沒有碰過</b>，和偏硬體的設計剛好相反。</p>',
  apply: function (S) { S.pos.kernel = 'k_cot'; S.cot = { b: fill(32, 0), w: fill(32, 'k'), r: fill(32, ''), vals: {}, hot: ['flags'], long: { flags: '0x00 = not VALID' } }; led(S, 'cot', 'k', 'W');
    S.say.kernel = 'COT[' + H + ']: 32 zero bytes.\nNot VALID any more.'; } });

kn({ title: '在 bitmap 裡把 ' + REL.length + ' 個 bit 寫回 0', cam: L.VIEW.bitmap, keep: [K.bitmap],
  text: '<p>剛才讀 COT 時 kernel 已經知道是哪 ' + REL.length + ' 個 chunk：' + spanZh(REL) + '。它在 bitmap 裡把對應的 bit ' + bit(REL[0]) + ' 到 ' + bit(REL[REL.length - 1]) + ' 從 1 寫回 0（黃框）。</p>'
    + '<p>word ' + BM.word + ' 的值從 ' + c('0x' + BM.before.toUpperCase()) + ' 變成 ' + c('0x' + BM.after.toUpperCase()) + '，空 chunk 從 ' + BM.free_before + ' 個變 ' + BM.free_after + ' 個。</p>'
    + '<p>這一步只動 kernel 自己的記憶體，不需要 DRAM 存取，也不需要硬體。simulator 把 kernel 為這個 job 做的記帳（讀 COT、清 COT、改 bitmap）算成固定的 ' + ns(M.kernel_job_ns) + ' ns。</p>',
  apply: function (S) { S.pos.kernel = 'k_bm'; S.bm.word = BM.after; S.bm.free = BM.free_after; REL.forEach(function (n, i) { S.bm.mark[bit(n)] = 'c'; S.ch[i] = 4; }); S.bm.hot = REL.map(bit); S.clk.k = 1; led(S, 'bitmap', 'k', 'W');
    S.say.kernel = REL.length + ' bits back to 0: chunks\n' + span(REL) + '\nare free again.'; },
  fx: function (done) { kit.after(500, function () { REL.forEach(function (n, i) { kit.after(i * 140, function () { kit.ping(L.bitAt(n), 0xf4d35e, 1.2); }); }); kit.after(REL.length * 140 + 300, done); }); },
  card: function (S) { return bmCard(S, [['bits cleared by KERNEL SW', '<span class="by k">' + REL.length + ' bits</span>, bit ' + bit(REL[0]) + ' to ' + bit(REL[REL.length - 1])], ['chunks free again', span(REL)], ['free chunks', BM.free_before + ', now ' + BM.free_after]]); } });

kn({ title: '這 ' + NCH + ' 個 chunk 現在是空的', cam: L.VIEW.chunks, keep: D.chunks.map(function (x, i) { return K['ch' + i]; }),
  text: '<p>回頭看 chunk pool：' + NCH + ' 個 chunk 都標成 free again。裡面的 byte 沒有被清掉，只是 COT 不再指向它們、bitmap 也說它們是空的。下次有 page 要壓縮時，kernel 從 bitmap 找到它們，硬體直接蓋過去。</p>'
    + '<p>從頭到尾，硬體只<b>讀</b>過這些 chunk。把它們「還回去」這件事沒有動到 chunk 本身，只改了 kernel 的兩本帳。</p>',
  apply: function (S) { S.pos.kernel = 'k_tiles'; S.say.kernel = 'These ' + NCH + ' chunks are free.\nOnly my books changed.'; },
  card: function () { return L.tableCard('The ' + NCH + ' chunks after the clean-up', D.chunks.map(function (x) { return ['chunk ' + hx(x.n), 'free again · bit ' + bit(x.n) + ' of word ' + BM.word + ' = 0']; })); } });

kn({ title: '最後才把 PTE 設回 valid', cam: L.VIEW.pte, keep: [K.pte, K.gate],
  text: '<p>kernel 把筆記裡 page ' + H + ' 的狀態從 ' + c('decompressing') + ' 改成 ' + c('present') + '，再把 PTE 寫成 ' + c('valid = 1') + '，指向 <b>frame ' + V.frame + '</b>。</p>'
    + '<p>這一步<b>故意排在最後</b>。如果 frame 還沒寫完就 valid，' + RQ.name + ' 會讀到半成品。順序是：資料到位、帳記完，才開門。</p>'
    + '<p>PTE 在兩種設計裡都只有 kernel 寫。LZ4 HW 不碰 page table。</p>',
  apply: function (S) { S.pos.kernel = 'k_gate'; S.pte.valid = 1; S.pte.st = 'present'; S.pte.hot = true; S.pte.w = true; led(S, 'pte', 'k', 'W');
    S.say.kernel = 'PTE of page ' + H + ': valid = 1,\nit points to frame ' + V.frame + '.\n' + RQ.name + ', go on.'; },
  card: function () { return L.tableCard('What KERNEL SW changed', [['PTE valid bit', '0, now <span class="by k">1</span>'], ['PTE points to', 'frame ' + V.frame + ' @' + FPA], ["kernel's page state", 'decompressing, now <span class="by k">present</span>']]); } });

var kns = RQ.kernel_ns, kj = M.kernel_job_ns, sum = kns + C.lat_ns + kj, same = HW && HW.same;
step({ who: 'user', title: RQ.name + ' 重試，這次通過', cam: L.VIEW.far, keep: [K.gate, K.pte],
  text: '<p>kernel 從 page fault 返回，CPU 把 ' + RQ.name + ' 剛才那個' + RWZ + '的動作<b>重做一次</b>。這次 gate 查到 ' + c('valid = 1') + '，直接通過，' + RQ.name + ' 拿到 frame ' + V.frame + ' 裡的資料。</p>'
    + '<p>對 ' + RQ.name + ' 來說，什麼事都沒發生，只是這一次' + RWZ + '比平常慢。它等了 ' + c(ns(kns) + ' + ' + C.lat_ns + ' + ' + ns(kj)) + ' = <b>' + ns(sum) + ' ns</b>' + (sum === RQ.lat_ns ? '，和 simulator 記錄的這次存取的 latency 相同' : '') + '。其中 kernel 處理 page fault 的固定成本佔了大半。</p>'
    + (same ? '<p>偏硬體那一課的同一次存取等了 ' + ns(HW.access_ns) + ' ns。' + RQ.name + ' 分不出兩種設計，只感覺得到這個數字。</p>' : ''),
  apply: function (S) { S.pos.kernel = 'k_home'; S.pos.hw = 'h_home'; S.gate = 'pass'; S.pte.w = false; S.pte.hot = true;
    S.say.gate = 'PTE of page ' + H + ': valid = 1.\nGo on to frame ' + V.frame + '.'; S.say.req = 'Got my data from page ' + H + '.\nI never knew it was compressed.'; },
  card: function () { var rows = [['KERNEL SW, page-fault handling', ns(kns) + ' ns'], ['LZ4 HW, ' + J.op_name, C.dram_accesses + ' × ' + ns(M.dram_ns) + ' + ' + ns(M.decomp_ns) + ' = ' + C.lat_ns + ' ns'], ['KERNEL SW, COT and bitmap', ns(kj) + ' ns'], ['total', ns(sum) + ' ns']];
    rows[3].hot = true; return L.tableCard('What ' + RQ.name + ' waited for', rows); } });

/* ---- result, and the same fault in the hardware-leaning lesson */
var cmpText = same
  ? '<p><b>和偏硬體那一課對照</b>（同一次存取、同一個 page ' + H + '）：</p><ul style="margin:6px 0 0 18px;padding:0">'
    + '<li>誰去查資料在哪：那邊 LZ4 HW 自己讀 COT（硬體多一次 DRAM 存取），這邊 kernel 讀 COT，把號碼、長度、checksum 抄到 descriptor 上。</li>'
    + '<li>descriptor：那邊 ' + HW.desc_bytes + ' B，只說「哪個 page、放哪裡」；這邊 48 B，COT 的內容幾乎整筆帶過去。</li>'
    + '<li>job 數：那邊 ' + HW.jobs + ' 個（DECOMPRESS ' + HW.lat_ns + ' ns，再 INVALIDATE ' + HW.lat2_ns + ' ns）；這邊 1 個（' + C.lat_ns + ' ns），收尾是 kernel 自己的 ' + ns(kj) + ' ns。</li>'
    + '<li>checksum：那邊硬體自己存、自己對；這邊 kernel 保管、硬體核對，順便擋下 kernel 記錯帳的情況。</li>'
    + '<li>還 chunk：那邊硬體把 ' + list(HW.chunks) + ' push 回 SRAM 裡的 stack；這邊 kernel 把 ' + list(REL) + ' 的 bit 清成 0。</li>'
    + '<li>' + RQ.name + ' 等的時間：' + ns(HW.access_ns) + ' ns 對 ' + ns(sum) + ' ns。差別來自 simulator 的時間模型，不是量測值。</li></ul>'
  : '<p>偏硬體那一課用的是另一次存取，數字不能直接對照，但分工的差別一樣：那邊 COT 和空 chunk 的清單在硬體手上，這邊都在 kernel 手上。</p>';
step({ who: 'note', title: '結果：誰碰了什麼', cam: L.VIEW.all, keep: [K.gate, K.pte],
  text: '<p>page ' + H + ' 回到 frame 裡，' + NCH + ' 個 chunk 在 bitmap 上又是空的，COT[' + H + '] 回到全 0。和上一課的壓縮合起來，剛好是一個完整的來回。</p>'
    + '<p>看下面的表：<b class="h">LZ4 HW</b> 只讀了 descriptor 和 chunk，只寫了 frame 和 completion。PTE、COT、bitmap 全部只有 <b class="k">KERNEL SW</b> 在碰。硬體連這是哪個 page 都不知道。</p>'
    + '<p>分工：<b>要不要做、資料在哪、做完怎麼記</b>都是 kernel 的事；硬體只負責<b>搬資料、驗 checksum、解碼</b>，每個 job 從零開始。</p>'
    + cmpText,
  apply: function (S) { S.final = true; S.gate = 'idle'; S.pos.req = 'ui_home'; S.pos.kernel = 'k_home'; S.pos.hw = 'h_home'; S.pte.w = false;
    S.say.req = 'Back to work.'; S.say.kernel = 'One job, and my two books\nagree again.'; S.say.hw = 'I touched only what\nthe descriptor named.'; },
  card: function () {
    var h = L.tableCard('Before and after, page ' + H, [['where the page is', NCH + ' chunks (' + SL + ' B), now frame ' + V.frame + ' (' + M.page + ' B)'], ['free frames', D.frames.free_before + ', now ' + D.frames.free_after],
      ['PTE', 'valid 0, now 1'], ['COT[' + H + ']', 'VALID with ' + NCH + ' chunks, now all zero'], ['free chunks in the bitmap', BM.free_before + ', now ' + BM.free_after],
      ['LZ4 HW jobs', '1: ' + J.op_name + ' ' + C.lat_ns + ' ns']]);
    if (same) h += L.tableCard('Same page, same access, two designs', [
      ['', '<b class="h">HW-leaning</b> · <b class="k">SW-leaning (this lesson)</b>'],
      ['who reads COT[' + H + ']', 'LZ4 HW · KERNEL SW'],
      ['job descriptor', HW.desc_bytes + ' B · 48 B'],
      ['LZ4 HW jobs', HW.jobs + ' · 1'],
      ['DRAM accesses by LZ4 HW', HW.dram_accesses + ' + ' + HW.dram2_accesses + ' · ' + C.dram_accesses],
      ['who clears COT[' + H + ']', 'LZ4 HW · KERNEL SW'],
      ['chunks given back', list(HW.chunks) + ' to the stack · ' + list(REL) + ' in the bitmap'],
      [RQ.name + ' waited', ns(HW.access_ns) + ' ns · ' + ns(sum) + ' ns']]);
    return h;
  } });

var reqCss = A.req ? A.req.css : '#ff8fb1';
lesson = new R.Lesson({
  kit: kit, steps: steps, init: init, pose: L.pose, show: L.show,
  card: function (S, st) { return st.card ? st.card(S) : ''; },
  clock: function (S) {
    if (!S.clk.on) return 'LZ4 HW job time: not started';
    var t = S.clk.dram * M.dram_ns + S.clk.lz * M.decomp_ns;
    return 'LZ4 HW job time so far: <b>' + S.clk.dram + ' × ' + ns(M.dram_ns) + ' ns</b> DRAM' + (S.clk.lz ? ' + <b>' + ns(M.decomp_ns) + ' ns</b> LZ4' : '') + ' = <b>' + ns(t) + ' ns</b>'
      + (S.clk.k ? ' · KERNEL SW bookkeeping: <b>+ ' + ns(kj) + ' ns</b>' : '');
  },
  ledger: [['pte', 'PTE of page ' + H], ['cot', 'COT[' + H + ']'], ['desc', 'job descriptor'], ['bell', 'DOORBELL register'], ['chunk', 'chunks (compressed data)'],
           ['frame', 'frame data (' + M.page + ' B)'], ['done', 'completion'], ['bitmap', 'free-chunk bitmap']],
  who: { user: ['USER SW', reqCss], kernel: ['KERNEL SW', '#f4d35e'], hw: ['LZ4 HW · HARDWARE', '#b48cff'], note: ['SUMMARY', '#7ee2a8'] }
});
var chip = document.getElementById('design');
document.getElementById('title').textContent = 'LZ4 DRAM compression lesson';
chip.textContent = 'SW-LEANING DESIGN'; chip.style.background = '#f4d35e'; chip.style.color = '#10161d';
document.getElementById('scene').textContent = 'Scene: DECOMPRESS on an invalid PTE · real job from simulator run seed ' + M.seed + ', access ' + RQ.access_no;
R.lesson = lesson;
})();

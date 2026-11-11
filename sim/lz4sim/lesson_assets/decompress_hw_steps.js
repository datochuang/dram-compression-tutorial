/* Lesson scene "decompress-hw": the steps. A user program touches a page whose PTE is invalid,
   the kernel names the case, and two jobs follow: DECOMPRESS (the hardware finds the chunks through
   the COT, checks the CRC, writes the frame) and INVALIDATE (the hardware takes the chunks back and
   zeroes the COT entry). Prose is zh-TW; what is drawn on the stage is English. */
(function () {
'use strict';
var L = R.L, D = L.D, M = L.M, V = L.V, H = L.H, hx = R.hx, kit = L.kit, A = L.A, T = THREE, NCH = L.NCH, K = L.KEEP;
var RQ = D.req, J1 = D.desc, C1 = D.done, J2 = D.desc2, C2 = D.done2, B4 = D.before;
var SL = D.stream.len, LAST = D.stream.sizes[NCH - 1], CK = hx(D.cot.checksum, 8), FPA = hx(V.frame_pa), TAG = hx(J1.tag);
var bJ1 = R.bytes(J1.hex), bC1 = R.bytes(C1.hex), bJ2 = R.bytes(J2.hex), bC2 = R.bytes(C2.hex), bCot = R.bytes(D.cot.before);
var c = function (s) { return '<code>' + s + '</code>'; };
var hexOf = function (arr, a, n) { return arr.slice(a, a + n).map(R.b2).join(' '); };
var fill = function (n, v) { var a = [], i; for (i = 0; i < n; i++) a.push(v); return a; };
var blank = function (n, title, long) { var s = { b: fill(n, null), w: fill(n, null), r: fill(n, ''), vals: {}, hot: [] }; if (title) s.title = title; if (long) s.long = long; return s; };
var RW = RQ.w ? 'write' : 'read', RWZ = RQ.w ? '寫' : '讀';

var cotVals = { flags: 'VALID', count: '' + NCH, comp_len: '' + SL, checksum: CK };
D.cot.chunks.forEach(function (n, i) { cotVals['chunk[' + i + ']'] = hx(n); });
var init = {
  pos: { kernel: 'k_home', hw: 'h_home', req: 'ui_home' }, say: {}, gate: 'idle', card: null, final: false,
  pte: { valid: 0, st: 'compressed', hot: false, w: false }, free: D.frames.free_before,
  frame: { st: 'free', hot: false },
  desc: blank(16),
  cot: { b: bCot.slice(), w: fill(32, 'h'), r: fill(32, ''), vals: cotVals, hot: [] },
  done: blank(16),
  bell: 0, irq: 0, eng: { on: 0, vis: fill(NCH, false), lab: '' }, stack: { pop: NCH, hot: false }, ch: fill(NCH, 2), chHot: -1,
  led: {}, clk: { job: 0, d1: 0, lz: 0, d2: 0 }
};
function put(S, key, vals, who, src) {
  var s = S[key]; s.hot = Object.keys(vals);
  L.F[key].fields.forEach(function (f) {
    if (!(f[0] in vals)) return;
    var i; for (i = 0; i < f[2]; i++) { s.b[f[1] + i] = src[f[1] + i]; s.w[f[1] + i] = who; }
    s.vals[f[0]] = vals[f[0]];
  });
}
function readAll(S, key, who) { S[key].r = S[key].r.map(function () { return who; }); }
function led(S, id, who, mark) { var r = S.led[id] = S.led[id] || {}, v = r[who] || ''; if (v.indexOf(mark) < 0) r[who] = v ? v + ' ' + mark : mark; }
function calm(S) { S.desc.hot = []; S.cot.hot = []; S.done.hot = []; S.pte.hot = false; S.frame.hot = false; S.stack.hot = false; S.chHot = -1; S.eng.on = 0; }

var descCard = function (S) { return L.structCard('desc', S, 'Job descriptor <span>(16 B in DRAM, job ring)</span>'); };
var cotCard = function (S) { return L.structCard('cot', S, 'COT[' + H + '] <span>(32 B in DRAM @' + hx(V.entry_pa) + ')</span>'); };
var doneCard = function (S) { return L.structCard('done', S, 'Completion <span>(16 B in DRAM, completion ring)</span>'); };
var steps = [], lesson;
function step(o) { var ap = o.apply; o.apply = function (S) { calm(S); S.card = steps.indexOf(o); ap(S); }; steps.push(o); }

/* ---- the stage and where the page is right now */
var nowCard = function () { return L.tableCard('Page ' + H + ' of ' + V.name + ' right now', [
    ['compressed at', 'access ' + B4.access_no + ', ' + B4.accesses_ago + ' accesses ago'],
    ['frame', 'none (it had frame ' + B4.frame + ', given away since)'],
    ['data', SL + ' B of LZ4 stream in ' + NCH + ' chunks: ' + D.cot.chunks.map(function (n) { return hx(n); }).join(', ')],
    ['COT[' + H + ']', 'VALID, written by LZ4 HW when it compressed the page'],
    ['PTE', 'valid = 0'], ["kernel's note", 'compressed']]); };
var glossary = function () { return L.tableCard('Words used in this lesson', [
    ['page', '軟體看到的 ' + M.page + ' B 記憶體單位，用編號（handle）稱呼'],
    ['frame', 'DRAM 裡一塊 ' + M.page + ' B 的空間，放一個未壓縮的 page'],
    ['chunk', 'DRAM 裡 ' + M.chunk + ' B 的小塊，放壓縮後的資料'],
    ['PTE', 'page table entry，決定 user SW 的存取能不能直接通過'],
    ['COT', 'compressed object table，每個 page 一筆 32 B，記壓縮後的資料在哪些 chunk'],
    ['descriptor', 'kernel 寫給 LZ4 HW 的工作單，16 B'],
    ['completion', 'LZ4 HW 回報結果的單子，16 B']]); };
step({ who: 'note', title: '舞台，以及這個 page 現在的樣子', cam: L.VIEW.all, card: function () { return nowCard() + glossary(); },
  text: '<p>這一課用一個真實的例子，看「解壓縮一個 page」從頭到尾發生的事。所有數字都來自 simulator 的同一次執行，而且就是上一課被壓縮的那個 page。</p>'
    + '<p>三種角色：<b>USER SW</b>（遠端的 ' + M.clients.join('、') + '）是被服務的程式，只管讀寫自己的 page。<b class="k">KERNEL SW</b>（黃色）管理記憶體。<b class="h">LZ4 HW</b>（紫色機器人）是硬體加速器。</p>'
    + '<p>先看現況。<b>page ' + H + '</b> 屬於 ' + V.name + '，在第 ' + B4.access_no + ' 次存取時被壓縮，之後 ' + B4.accesses_ago + ' 次存取都沒有人碰它。它現在<b>沒有 frame</b>：左邊那塊 frame 是空的。它的內容是 ' + SL + ' B 的 LZ4 stream，躺在 ' + NCH + ' 個畫斜線的 chunk 裡。最靠近你的 COT[' + H + '] 已經填好，是上一課 LZ4 HW 寫的。PTE 的 valid 是 0。</p>'
    + '<p>按 Next 一步一步看，畫面可以拖曳旋轉、滾輪縮放。</p>',
  apply: function (S) { S.say.kernel = 'I am the kernel.\nI manage the memory.'; S.say.hw = 'I am the LZ4 accelerator.\nI compress and decompress pages.'; S.say.req = 'I am ' + RQ.name + ', a program.\nI just read and write my pages.'; } });

/* ---- the access that starts everything */
step({ who: 'user', title: RQ.name + ' ' + RWZ + ' page ' + H + '，被 access gate 攔下', cam: L.VIEW.far, keep: [K.gate, K.pte],
  text: '<p><b>' + RQ.name + '</b> 要' + RWZ + '自己的 page ' + c(H) + '。它不知道這個 page 被壓縮過，也不需要知道，它只是照常存取。</p>'
    + '<p>所有 user SW 的存取都經過同一個 <b>access gate</b>（MMU 查 page table）。gate 查到 page ' + H + ' 的 PTE：' + c('valid = 0') + '。這次存取就停在這裡，CPU 進入 page fault，把 <b class="k">KERNEL SW</b> 叫來。</p>'
    + '<p>注意：<b>沒有人下令「解壓縮」</b>。解壓縮是被這次停下來的存取觸發的。上一課 kernel 把 valid 寫成 0，就是為了這一刻。</p>',
  apply: function (S) { S.pos.req = 'ui_gate'; S.gate = 'stop'; S.pte.hot = true; S.pos.kernel = 'k_call';
    S.say.req = RW + ' page ' + H; S.say.gate = 'PTE of page ' + H + ': valid = 0.\nThis access stops here.\nKERNEL SW is called.'; },
  card: function () { return L.tableCard('The access', [['who', 'USER SW ' + RQ.name], ['what', RW + ' page ' + H + ' (access ' + RQ.access_no + ' of the run)'], ['PTE valid bit', '0'], ['result', 'page fault: KERNEL SW is called']]); } });

step({ who: 'kernel', title: '為什麼 invalid？kernel 認出是哪一種情況', cam: L.VIEW.pte, keep: [K.pte, K.gate],
  text: '<p>PTE invalid 有好幾種原因，gate 分不出來，只有 kernel 知道。kernel 查自己的筆記：page ' + H + ' 的狀態是 ' + c('compressed') + '。所以這次的情況是「要解壓縮」。</p>'
    + '<p>kernel 的筆記只有這一個詞。它<b>不知道</b>壓縮後的資料在哪幾個 chunk、有多長、checksum 是多少。在這個偏硬體的設計裡，那些全記在 COT，而 COT 只有 LZ4 HW 會讀寫。</p>',
  apply: function (S) { S.pos.req = 'ui_gate'; S.gate = 'stop'; S.pos.kernel = 'k_gate'; S.pte.hot = true;
    S.say.kernel = 'Page fault on page ' + H + '.\nMy note says: compressed.\nThis case: decompress it.'; S.say.req = 'waiting…'; },
  card: function () { var rows = [['untouched', 'first use: give it a zeroed frame, no LZ4 HW'], ['compressed', 'this case: get a frame, ask LZ4 HW to DECOMPRESS'], ['compressing / decompressing', 'a job is under way: wait for it'], ['lost', 'the data failed its check: report the error']];
    rows[1].hot = true; return L.tableCard("Why a PTE can be invalid <span>(kernel's note about the page)</span>", rows); } });

step({ who: 'kernel', title: '拿一個空的 frame', cam: L.VIEW.frame, keep: [K.frame],
  text: '<p>解壓縮後的 ' + M.page + ' B 要有地方放。kernel 從空 frame 清單拿出 <b>frame ' + V.frame + '</b>，實體位址 ' + c(hx(M.fc_base) + ' + ' + V.frame + ' × ' + M.page) + ' = ' + c(FPA) + '。空 frame 從 ' + D.frames.free_before + ' 變 ' + D.frames.free_after + '。</p>'
    + '<p>' + D.frames.free_before + ' 個還高於門檻 ' + M.fc_low + ' 個，所以這次不用先回收別的 page。如果不夠，kernel 要先做上一課的壓縮，' + RQ.name + ' 就得等更久。</p>'
    + '<p>這個 page 上次住在 frame ' + B4.frame + '，這次是 frame ' + V.frame + '。page 編號不變，frame 每次都可能不同，這就是 PTE 要重寫的原因。kernel 也把筆記改成 ' + c('decompressing') + '。</p>',
  apply: function (S) { S.pos.req = 'ui_gate'; S.gate = 'stop'; S.pos.kernel = 'k_frame'; S.frame.st = 'taken'; S.frame.hot = true; S.free = D.frames.free_after; S.pte.st = 'decompressing';
    S.say.kernel = 'I take free frame ' + V.frame + '\nfor page ' + H + '.\n' + D.frames.free_after + ' free frames left.'; },
  card: function () { return L.tableCard('What KERNEL SW changed', [['free frames', D.frames.free_before + ', now <span class="by k">' + D.frames.free_after + '</span>'], ['frame for page ' + H, 'frame ' + V.frame + ' @' + FPA], ['reclaim needed', 'no: ' + D.frames.free_before + ' is above ' + M.fc_low], ["kernel's page state", 'compressed, now <span class="by k">decompressing</span>']]); } });

/* ---- descriptor 1, field by field */
function kd(o) { var ap = o.apply; o.who = 'kernel'; o.cam = L.VIEW.desc; o.keep = [K.desc]; o.card = descCard; o.apply = function (S) { S.pos.req = 'ui_gate'; S.gate = 'stop'; S.pos.kernel = 'k_desc'; ap(S); }; step(o); }
kd({ title: '寫 descriptor：要做什麼',
  text: '<p>kernel 用一張 16 B 的工作單把事情交代給硬體，這就是 <b>job descriptor</b>，放在 DRAM 裡 job ring 的一格。格式和壓縮時完全一樣，只是填的值不同。</p>'
    + '<p>先寫前 2 個 byte：' + c('opcode = ' + J1.opcode) + ' 代表 ' + J1.op_name + '（1 是 COMPRESS），' + c('flags = 0') + '。</p>'
    + '<p>黃色的格子是 kernel 寫的 byte，' + c('--') + ' 是還沒寫的。</p>',
  apply: function (S) { put(S, 'desc', { opcode: J1.op_name, flags: '' }, 'k', bJ1); led(S, 'desc', 'k', 'W'); S.say.kernel = 'I write the job descriptor.\nopcode ' + J1.opcode + ': ' + J1.op_name + '.'; } });
kd({ title: '寫 descriptor：最多寫出多少',
  text: '<p>' + c('limit = ' + J1.limit) + '：硬體最多可以往 frame 寫 ' + J1.limit + ' B，也就是剛好一個 page。壓縮時同一個欄位的意思是「超過就放棄」，解壓縮時是「輸出不能超過這個大小」，壞掉的 stream 才不會寫到別人的 frame。</p>'
    + '<p>' + J1.limit + ' 寫成 16 進位是 ' + c(hx(J1.limit, 4)) + '。DRAM 裡是 little-endian，低位的 byte 放前面，所以看到的是 ' + c(hexOf(bJ1, 2, 2)) + '。</p>',
  apply: function (S) { put(S, 'desc', { limit: '' + J1.limit }, 'k', bJ1); S.say.kernel = 'limit ' + J1.limit + ':\nwrite one page, not more.'; } });
kd({ title: '寫 descriptor：哪一個 page、解到哪裡',
  text: '<p>' + c('handle = ' + H) + '：要解的是哪一個 page，寫成 ' + c(hexOf(bJ1, 4, 4)) + '。</p>'
    + '<p>' + c('frame_pa = ' + FPA) + '：寫成 ' + c(hexOf(bJ1, 8, 4)) + '。壓縮時這個欄位是「資料從哪裡讀」，這次是「解出來的資料<b>寫到哪裡</b>」，就是剛拿到的 frame ' + V.frame + '。</p>',
  apply: function (S) { put(S, 'desc', { handle: H, frame_pa: FPA }, 'k', bJ1); S.say.kernel = 'handle ' + H + ',\noutput goes to ' + FPA + '.'; } });
kd({ title: '寫 descriptor：tag，還有沒寫的東西',
  text: '<p>' + c('tag = ' + TAG) + '：kernel 自己取的編號，硬體做完會原封不動抄回來。</p>'
    + '<p>16 B 寫完了。看看<b>裡面沒有的東西</b>：沒有 chunk 號碼、沒有壓縮後的長度、沒有 checksum。kernel 寫不出來，因為它根本不知道。它只說「哪個 page、放哪裡」，其餘由 LZ4 HW 自己從 COT 查。</p>',
  apply: function (S) { put(S, 'desc', { tag: TAG }, 'k', bJ1); S.say.kernel = 'tag ' + TAG + ': so I know\nthe answer when it comes back.'; } });

/* ---- briefing 1 */
step({ who: 'kernel', title: '交代工作，按 doorbell', cam: L.VIEW.desk, keep: [K.desc, K.bell], card: descCard,
  text: '<p>descriptor 只是躺在 DRAM 裡，硬體還不知道。kernel 對 <b>DOORBELL</b> register 做一次 MMIO 寫入，告訴 LZ4 HW「job ring 有新工作」。</p>'
    + '<p>聽 kernel 怎麼交代：只說解哪一個 page、放到哪裡。chunk 在哪、資料對不對，都是硬體的事。之後 kernel 等 IRQ 就好，' + RQ.name + ' 還停在 gate 前面。</p>',
  apply: function (S) { S.pos.req = 'ui_gate'; S.gate = 'stop'; S.pos.kernel = 'k_bell'; S.bell = 1; led(S, 'bell', 'k', 'W');
    S.say.kernel = 'LZ4 HW, a job for you:\n' + J1.op_name + ' page ' + H + '.\nPut its ' + M.page + ' B at ' + FPA + '.\nYou know where its chunks are,\nyou check the data.\nReport back with tag ' + TAG + '.';
    S.say.hw = 'Understood.'; },
  fx: function (done) { kit.after(700, function () { kit.ping(new T.Vector3(-4, 5.6, -25), 0xf4d35e, 3); done(); }); } });

/* ---- job 1: the hardware */
function hw(o) { var ap = o.apply; o.who = 'hw'; o.apply = function (S) { S.pos.req = 'ui_gate'; S.gate = 'stop'; S.pos.kernel = 'k_home'; S.bell = 0; ap(S); }; step(o); }
hw({ title: '讀 descriptor，檢查', cam: L.VIEW.read, keep: [K.desc],
  text: '<p>LZ4 HW 從 job ring 讀出這 16 B（第 1 次 DRAM 存取）。格子右上角的紫色小角代表「LZ4 HW 讀過」。</p>'
    + '<p>它先檢查：opcode 認得；handle ' + c(H) + ' 小於 page 總數 ' + M.pages + '。不合格就回報 BAD_DESC 或 BAD_HANDLE，什麼都不動。</p>'
    + '<p>接著算出 COT entry 的位址：' + c('cot_base + handle × 32') + ' = ' + c(hx(M.cot_base) + ' + ' + H + ' × 32') + ' = ' + c(hx(V.entry_pa)) + '。descriptor 裡沒有這個位址，硬體自己算。</p>',
  apply: function (S) { S.pos.hw = 'h_desc'; readAll(S, 'desc', 'h'); led(S, 'desc', 'h', 'R'); S.clk.job = 1; S.clk.d1 = 1;
    S.say.hw = 'Descriptor read: ' + J1.op_name + '.\nHandle ' + H + ' is in range.\nIts COT entry is at ' + hx(V.entry_pa) + '.'; },
  card: function (S) { return descCard(S) + L.tableCard('Checks by LZ4 HW', [['opcode known', J1.opcode + ' = ' + J1.op_name + ': yes'], ['handle in range', V.h + ' &lt; ' + M.pages + ': yes'], ['COT entry address', hx(V.entry_pa)]]); } });
hw({ title: '讀 COT[' + H + ']', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>LZ4 HW 從 ' + c(hx(V.entry_pa)) + ' 讀出 32 B（第 2 次 DRAM 存取）。這 32 B 是它自己在壓縮時寫的，所以整片是紫色；現在右上角多了紫色小角，表示它又讀了一次。</p>'
    + '<p>硬體裡有一格小快取叫 CTLB，記著最近用過的一筆 COT。這個 page 已經 ' + B4.accesses_ago + ' 次存取沒被碰，快取裡早就是別人，所以這次要真的讀 DRAM。</p>'
    + '<p>先看 ' + c('flags = ' + hx(D.cot.flags, 2)) + '：bit0 VALID 是 1，代表這個 page 確實有壓縮資料。如果是 0，硬體回報 BAD_HANDLE。bit2 RAW 是 0，代表存的是 LZ4 stream，需要解碼。</p>',
  apply: function (S) { S.pos.hw = 'h_cot'; readAll(S, 'cot', 'h'); S.cot.hot = ['flags']; led(S, 'cot', 'h', 'R'); S.clk.d1 = 2;
    S.say.hw = 'COT[' + H + '] read.\nVALID: this page has\ncompressed data.'; } });
hw({ title: '從 COT 讀出：幾個 chunk、多長、哪幾個', cam: L.VIEW.cot, keep: [K.cot],
  text: '<p>' + c('count = ' + NCH) + '：資料在 ' + NCH + ' 個 chunk 裡。</p>'
    + '<p>' + c('comp_len') + ' 的 2 個 byte 是 ' + c(hexOf(bCot, 2, 2)) + '，little-endian 讀回來是 ' + c(hx(SL, 4)) + ' = ' + SL + ' B。前 ' + (NCH - 1) + ' 個 chunk 各取 ' + M.chunk + ' B，最後一個只取 ' + c(SL + ' − ' + (NCH - 1) + ' × ' + M.chunk + ' = ' + LAST) + ' B。</p>'
    + '<p>' + c('chunk[0..' + (NCH - 1) + ']') + ' 每個 3 B：' + c(hexOf(bCot, 8, 3)) + ' 是 ' + c(hx(D.cot.chunks[0])) + '。排列順序就是 stream 的順序，一定要照這個順序讀。</p>'
    + '<p>' + c('checksum = ' + CK) + ' 先記著，等一下要對。</p>',
  apply: function (S) { S.pos.hw = 'h_cot'; S.cot.hot = ['count', 'comp_len'].concat(D.cot.chunks.map(function (n, i) { return 'chunk[' + i + ']'; }));
    S.say.hw = NCH + ' chunks, ' + SL + ' B in all.\nI read them in this order:\n' + D.cot.chunks.map(function (n) { return hx(n); }).join(', ') + '.'; },
  card: function (S) { var a = 0; return cotCard(S) + L.tableCard('Read plan made from the COT entry', D.chunks.map(function (ch, i) { var r = ['chunk[' + i + '] = ' + hx(ch.n), '@' + hx(ch.pa) + ', take ' + ch.bytes + ' B: stream bytes ' + a + ' to ' + (a + ch.bytes - 1)]; a += ch.bytes; return r; })); } });

/* ---- gather the chunks, one per step */
D.chunks.forEach(function (ch, i) {
  var a = i * M.chunk, b = a + ch.bytes - 1, prev = i ? D.chunks[i - 1] : null, got = a + ch.bytes;
  var t = i === 0
    ? '<p>LZ4 HW 照 COT 的順序去讀 chunk。第 1 個是 ' + c(hx(ch.n)) + '，位址 ' + c('pool_base + ' + hx(ch.n) + ' × ' + M.chunk) + ' = ' + c(hx(ch.pa)) + '。讀出 ' + ch.bytes + ' B，是 stream 的第 ' + a + ' 到 ' + b + ' B，接到左邊的 stream 上。</p>'
      + '<p>chunk 本身沒有被改動，斜線還在；紫色的字只是標示硬體讀過。時間模型把讀 chunk 算在 engine 的串流時間裡，所以上面的 DRAM 次數不加。</p>'
    : '<p>第 ' + (i + 1) + ' 個：' + c(hx(ch.n)) + '（位址 ' + c(hx(ch.pa)) + '），讀出 ' + ch.bytes + ' B，是 stream 的第 ' + a + ' 到 ' + b + ' B。</p>';
  if (prev && ch.n !== prev.n + 1) t += '<p>' + c(hx(ch.n)) + ' 和前一個 ' + c(hx(prev.n)) + ' 不相鄰。資料散在哪裡，只有 COT 知道，這就是為什麼一定要先讀 COT。</p>';
  if (ch.bytes < M.chunk) t += '<p>這個 chunk 只取前 ' + ch.bytes + ' B，後面 ' + (M.chunk - ch.bytes) + ' B 是沒用到的空間，不能送進 engine。能切得這麼準，靠的是 COT 的 comp_len。</p>';
  hw({ title: '讀第 ' + (i + 1) + ' 個 chunk，取 ' + ch.bytes + ' B', cam: L.VIEW.gather, keep: [K['ch' + i], K.engine], text: t,
    apply: function (S) { S.pos.hw = 'h_ch' + i; S.ch[i] = 3; S.chHot = i; S.eng.vis[i] = true; S.eng.lab = 'stream: ' + got + ' of ' + SL + ' B'; S.cot.hot = ['chunk[' + i + ']']; led(S, 'chunk', 'h', 'R');
      S.say.hw = 'read ' + ch.bytes + ' B from chunk ' + hx(ch.n) + ':\nstream bytes ' + a + ' to ' + b + '.'; },
    fx: function (done) {
      var tile = new T.Vector3(L.CX[i], 1, L.ZROW);
      kit.after(500, function () { kit.ping(tile, 0xb48cff);
        kit.after(350, function () { kit.fly(tile, L.segs[i].position.clone(), { color: 0xffffff, hatch: true, ms: 950, size: [L.SEG * ch.bytes / M.chunk, 0.8, 2.4], up: 5, done: done }); }); });
    },
    card: function () { return L.tableCard('Chunks of page ' + H + ' <span>(in COT order; ' + got + ' of ' + SL + ' B gathered)</span>', D.chunks.map(function (x, k) {
      var r = ['chunk[' + k + '] = ' + hx(x.n), (k <= i ? x.bytes + ' B read, starts ' : x.bytes + ' B to read, starts ') + hexOf(R.bytes(x.head), 0, 8)]; r.hot = k === i; return r; })); } });
});

/* ---- CRC */
hw({ title: '先驗 checksum，再動 frame', cam: L.VIEW.engine, keep: [K.engine],
  text: '<p>' + SL + ' B 到齊了。LZ4 HW 對這 ' + SL + ' B 算 CRC-32，得到 ' + c(CK) + '，和 COT 裡記的 ' + c(CK) + ' 一樣。資料在 chunk 裡躺了 ' + B4.accesses_ago + ' 次存取，沒有壞。</p>'
    + '<p>如果不一樣呢？硬體回報 BAD_STREAM，<b>frame 一個 byte 都不寫</b>。kernel 把這個 page 標成 ' + c('lost') + '，再回報錯誤。壞資料不會被悄悄交給 ' + RQ.name + '。</p>'
    + '<p>注意是誰在驗：checksum 是硬體壓縮時自己算、自己存進 COT 的，現在也是硬體自己對。kernel 從頭到尾沒看過這 ' + SL + ' B。</p>',
  apply: function (S) { S.pos.hw = 'h_engine'; S.cot.hot = ['checksum']; S.say.hw = 'CRC-32 of the ' + SL + ' B: ' + CK + '.\nCOT says ' + CK + '.\nThe data is intact.'; },
  card: function () { return L.tableCard('Checksum check by LZ4 HW', [['CRC-32 over', 'the ' + SL + ' B just gathered'], ['computed now', CK], ['stored in COT[' + H + ']', CK + ': equal'], ['if not equal', 'status BAD_STREAM, the frame is not written']]); } });

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
  text: '<p>stream 送進 LZ4 engine 解碼，解出來的 ' + M.page + ' B 寫到 ' + c(FPA) + '（第 3 次 DRAM 存取）。frame ' + V.frame + ' 變成藍色：裡面是 page ' + H + ' 的 RW 資料，和壓縮前一模一樣。</p>'
    + '<p>解碼比編碼簡單，不用找重複的字串，只要照 token 搬資料。engine 每個 cycle 輸出 ' + M.decomp_bytes_per_cycle + ' B，' + M.page + ' B 只要 ' + M.decomp_ns + ' ns；壓縮時是 ' + M.comp_ns + ' ns，差 ' + ratio + ' 倍。</p>' + litText,
  apply: function (S) { S.pos.hw = 'h_engine'; S.frame.st = 'present'; S.frame.hot = 'write'; S.eng.on = 1; S.eng.vis = fill(NCH, false); S.eng.lab = ''; led(S, 'frame', 'h', 'W'); S.clk.d1 = 3; S.clk.lz = 1;
    S.say.hw = 'I LZ4-decode the stream\nand write ' + M.page + ' B\ninto frame ' + V.frame + '.'; },
  fx: function (done) {
    var a = new T.Vector3(-9, 3.4, L.ZROW - 1), b = new T.Vector3(-27, 1.2, L.ZROW), i;
    for (i = 0; i < 4; i++) (function (i) { kit.after(500 + i * 320, function () { kit.fly(a, b, { color: R.COL.rw, ms: 800, size: [2.6, 0.8, 2.6] }); }); })(i);
    kit.after(2400, done);
  },
  card: function () { return L.tableCard('Stream in, frame out', [
    ['stream, first 16 B', hexOf(sh, 0, 16)], ['frame, first 16 B', '<span style="color:var(--rw)">' + hexOf(pg, 0, 16) + '</span>'],
    ['size', SL + ' B in, ' + M.page + ' B out'], ['time in the engine', M.decomp_ns + ' ns (compress: ' + M.comp_ns + ' ns)']]); } });

/* ---- completion 1 */
var doneVals = function (C) { return { status: C.status_name, flags: '' + C.flags, length: '' + C.length, checksum: hx(C.checksum, 8), tag: hx(C.tag), aux: '' + C.aux }; };
hw({ title: '寫 completion，發 IRQ', cam: L.VIEW.done, keep: [K.done, K.irq], card: doneCard,
  text: '<p>LZ4 HW 把結果寫進 completion ring 的一格（第 4 次 DRAM 存取）：' + c('status = ' + C1.status) + '（' + C1.status_name + '）、' + c('length = ' + C1.length) + '（寫進 frame 的 byte 數）、' + c('checksum = ' + hx(C1.checksum, 8)) + '，以及抄回來的 ' + c('tag = ' + hx(C1.tag)) + '。然後拉 IRQ。</p>'
    + '<p>這個 job 花了 ' + C1.dram_accesses + ' × ' + M.dram_ns + ' ns + ' + M.decomp_ns + ' ns = <b>' + C1.lat_ns + ' ns</b>。</p>'
    + '<p>留意現在的狀態：frame 裡有一份未壓縮的資料，' + NCH + ' 個 chunk 裡的壓縮資料也<b>還在</b>，COT 也還是 VALID。DECOMPRESS 這個 job 只管解，不管收。</p>',
  apply: function (S) { S.pos.hw = 'h_done'; put(S, 'done', doneVals(C1), 'h', bC1); S.done.hot = []; S.irq = 1; led(S, 'done', 'h', 'W'); S.clk.d1 = 4;
    S.say.hw = 'KERNEL SW, job done.\nTag ' + hx(C1.tag) + ': ' + C1.status_name + ',\n' + C1.length + ' B written to the frame.'; },
  fx: function (done) { kit.after(900, function () { done(); kit.ping(new T.Vector3(4, 5.6, -25), 0xb48cff, 3); }); } });

/* ---- kernel: read completion 1, order the clean-up */
function kn(o) { var ap = o.apply; o.who = 'kernel'; o.apply = function (S) { S.pos.hw = 'h_home'; ap(S); }; step(o); }
kn({ title: '讀 completion：解好了，但還沒收尾', cam: L.VIEW.kread, keep: [K.done], card: doneCard,
  text: '<p>IRQ 進來，kernel 讀 completion。格子右上角的黃色小角代表「kernel 讀過」。' + c('tag = ' + hx(C1.tag)) + ' 對到剛才的 job，' + c('status = ' + C1.status) + ' 代表成功。</p>'
    + '<p>kernel 還不能放行。page ' + H + ' 是 <b>RW page</b>：一旦 ' + V.name + ' 寫了它，chunk 裡那份壓縮資料就過期了。這個設計的做法很簡單：RW page 解回來之後，壓縮的那一份直接作廢，把 ' + NCH + ' 個 chunk 還回去。</p>'
    + '<p>RO page 不一樣。它的內容不會變，壓縮的那一份一直留著，下次要騰空間時只要放掉 frame 就好，不用再壓一次。所以 RO page 沒有接下來這一段。</p>',
  apply: function (S) { S.pos.kernel = 'k_done'; S.irq = 0; readAll(S, 'done', 'k'); S.done.hot = ['status', 'tag']; led(S, 'done', 'k', 'R');
    S.say.kernel = 'Tag ' + hx(C1.tag) + ': ' + C1.status_name + '.\nPage ' + H + ' is RW: its\ncompressed copy must go.'; },
  card: function (S) { return doneCard(S) + L.tableCard('After DECOMPRESS, what about the compressed copy?', [['RW page (this one)', 'drop it: one more job, INVALIDATE'], ['RO page', 'keep it: the content never changes']]); } });

var T2 = 'JOB DESCRIPTOR · 16 B · the next slot of the job ring', T2D = 'COMPLETION · 16 B · the next slot of the completion ring';
kn({ title: '寫第二張 descriptor：INVALIDATE', cam: L.VIEW.desc, keep: [K.desc], card: descCard,
  text: '<p>kernel 在 job ring 的<b>下一格</b>寫第二張工作單。同樣 16 B、同樣的欄位。</p>'
    + '<p>' + c('opcode = ' + J2.opcode) + ' 代表 ' + J2.op_name + '：「這個 page 的壓縮資料作廢」。' + c('handle = ' + H) + ' 和 ' + c('tag = ' + hx(J2.tag)) + ' 照舊。' + c('limit') + ' 和 ' + c('frame_pa') + ' 這次用不到，填 0。</p>'
    + '<p>再看一次沒寫的東西：kernel 還是<b>沒有寫 chunk 號碼</b>。它要硬體還 chunk，卻不知道是哪幾個。這在偏硬體的設計裡沒問題，因為號碼在 COT 裡，硬體自己看得到。</p>',
  apply: function (S) { S.pos.kernel = 'k_desc'; S.desc = blank(16, T2, { opcode: J2.opcode + ' = ' + J2.op_name });
    put(S, 'desc', { opcode: J2.op_name, flags: '', limit: '0', handle: H, frame_pa: '0', tag: hx(J2.tag) }, 'k', bJ2); S.desc.hot = ['opcode', 'handle', 'tag']; led(S, 'desc', 'k', 'W');
    S.say.kernel = 'Second job descriptor,\nin the next slot.\nopcode ' + J2.opcode + ': ' + J2.op_name + '.'; } });
kn({ title: '再交代一次，按 doorbell', cam: L.VIEW.desk, keep: [K.desc, K.bell], card: descCard,
  text: '<p>kernel 再按一次 <b>DOORBELL</b>，交代第二件事。</p>'
    + '<p>為什麼不讓硬體解完順手收掉？因為「壓縮的那一份要不要留」是<b>政策</b>：RW 要丟、RO 要留，將來也可能想改成「等第一次寫入才丟」。政策放在軟體比較好改。硬體每個 job 只做一件說得清楚的事，做完就忘，兩個 job 之間不用記任何進行中的狀態。</p>',
  apply: function (S) { S.pos.kernel = 'k_bell'; S.bell = 1;
    S.say.kernel = 'LZ4 HW, one more job:\n' + J2.op_name + ' page ' + H + '.\nIts compressed copy is not needed.\nTake the chunks back,\nclear its COT entry.\nReport back with tag ' + hx(J2.tag) + '.';
    S.say.hw = 'Understood.'; },
  fx: function (done) { kit.after(700, function () { kit.ping(new T.Vector3(-4, 5.6, -25), 0xf4d35e, 3); done(); }); } });

/* ---- job 2: the hardware */
hw({ title: '讀第二張 descriptor，COT 不用再讀', cam: L.VIEW.read, keep: [K.desc],
  text: '<p>LZ4 HW 讀出第二張 descriptor（這個 job 的第 1 次 DRAM 存取），opcode ' + J2.opcode + '，handle ' + c(H) + '。</p>'
    + '<p>它需要 COT[' + H + '] 才知道要還哪些 chunk。這一筆剛剛才讀過，還在 CTLB 那格快取裡，所以<b>這次不用讀 DRAM</b>。</p>'
    + '<p>檢查兩件事：entry 是 VALID；entry 不是 RO。RO page 的壓縮資料是唯一的一份，硬體拒絕作廢，回報 BAD_HANDLE。這是硬體替軟體擋下的一種錯誤。</p>',
  apply: function (S) { S.pos.hw = 'h_desc'; readAll(S, 'desc', 'h'); led(S, 'desc', 'h', 'R'); S.clk.job = 2; S.clk.d2 = 1;
    S.say.hw = 'Descriptor read: ' + J2.op_name + '.\nCOT[' + H + '] is still in my CTLB:\nno DRAM read needed.'; },
  card: function (S) { return descCard(S) + L.tableCard('Checks by LZ4 HW', [['opcode known', J2.opcode + ' = ' + J2.op_name + ': yes'], ['COT[' + H + ']', 'from the CTLB, 0 DRAM accesses'], ['entry is VALID', 'yes'], ['entry is not RO', 'yes: RW page, may be dropped']]); } });

D.chunks.forEach(function (ch, i) {
  var k = NCH - 1 - i, prevIdx, n0 = D.stack.size_before + i, last = i === NCH - 1;
  var t = i === 0
    ? '<p>LZ4 HW 照 COT 的順序，把 chunk 號碼一個一個 <b>push</b> 回自己的 free-chunk stack。第 1 個是 ' + c(hx(ch.n)) + '，stack 從 ' + n0 + ' 個號碼變 ' + (n0 + 1) + ' 個。</p>'
      + '<p>stack 在硬體的 SRAM 裡，push 不需要 DRAM 存取。只有 SRAM 裡超過 ' + M.spill_above + ' 個時才會把一批號碼搬到 DRAM，現在離那個數字還很遠。</p>'
      + '<p>chunk 裡的 ' + ch.bytes + ' B 沒有被清掉，只是不再有人指向它。下次有 page 要壓縮時，直接蓋過去。</p>'
    : '<p>push ' + c(hx(ch.n)) + '，stack 變 ' + (n0 + 1) + ' 個號碼。</p>';
  if (last) t += '<p>' + NCH + ' 個都還了。' + c(hx(ch.n)) + ' 最後進去，所以在最上面，下次壓縮會最先被 pop 出來用。kernel 始終不知道哪些 chunk 是空的。</p>';
  hw({ title: '還第 ' + (i + 1) + ' 個 chunk：push ' + hx(ch.n), cam: L.VIEW.chunks, keep: [K['ch' + i], K.stack], text: t,
    apply: function (S) { S.pos.hw = 'h_ch' + i; S.ch[i] = 0; S.stack.pop = k; S.stack.hot = true; S.cot.hot = ['chunk[' + i + ']']; led(S, 'stack', 'h', 'W');
      S.say.hw = 'push ' + hx(ch.n) + ' back on my stack:\n' + (n0 + 1) + ' numbers.'; },
    fx: function (done) {
      var mid = R.clone(lesson.states[prevIdx]), tile = new T.Vector3(L.CX[i], 1, L.ZROW);
      mid.chHot = i; mid.stack.hot = false; L.show(mid, false);
      kit.after(600, function () { kit.ping(tile, 0xb48cff); mid.ch[i] = 0; mid.chHot = -1; L.show(mid, false);
        kit.fly(tile, new T.Vector3(L.XS, L.plates[k].y, -9), { color: 0x36d6e7, ms: 900, size: [7, 0.86, 3.2], up: 7, done: done }); });
    },
    card: function () {
      var rows = [], j; for (j = k; j < D.stack.top.length; j++) { var r = [j === k ? 'top of stack' : '', hx(D.stack.top[j]) + (j < NCH ? '  pushed, was chunk[' + (NCH - 1 - j) + ']' : '')]; r.hot = j === k; rows.push(r); }
      rows.push(['', '… ' + (D.stack.size_after - D.stack.top.length) + ' more below']);
      return L.tableCard('Free-chunk stack <span>(SRAM of LZ4 HW, ' + (n0 + 1) + ' numbers)</span>', rows);
    } });
  prevIdx = steps.length - 2;
});

var zeroCot = function () { var s = { b: fill(32, 0), w: fill(32, 'h'), r: fill(32, ''), vals: {}, hot: ['flags'], long: { flags: '0x00 = not VALID' } }; return s; };
hw({ title: '把 COT[' + H + '] 清成 0', cam: L.VIEW.cot, keep: [K.cot], card: cotCard,
  text: '<p>LZ4 HW 對 ' + c(hx(V.entry_pa)) + ' 寫入 32 個 ' + c('00') + '（這個 job 的第 2 次 DRAM 存取）。' + c('flags') + ' 的 VALID bit 變 0，意思是「page ' + H + ' 沒有壓縮資料」，和上一課壓縮之前一模一樣。</p>'
    + '<p>CTLB 裡的那一格也一起丟掉，免得之後拿到過期的內容。</p>'
    + '<p>看這一筆 COT 的一生：壓縮時硬體寫、解壓縮時硬體讀、作廢時硬體清。<b>kernel 一次都沒有碰過</b>。</p>',
  apply: function (S) { S.pos.hw = 'h_cot'; S.cot = zeroCot(); led(S, 'cot', 'h', 'W'); S.clk.d2 = 2;
    S.say.hw = 'COT[' + H + ']: 32 zero bytes.\nNot VALID any more.'; } });
hw({ title: '寫第二張 completion，發 IRQ', cam: L.VIEW.done, keep: [K.done, K.irq], card: doneCard,
  text: '<p>LZ4 HW 在 completion ring 的下一格寫結果（這個 job 的第 3 次 DRAM 存取）：' + c('status = ' + C2.status) + '（' + C2.status_name + '）、' + c('tag = ' + hx(C2.tag)) + '，其餘欄位是 0，因為沒有資料要回報。然後拉 IRQ。</p>'
    + '<p>這個 job 完全沒用到 LZ4 engine：' + C2.dram_accesses + ' × ' + M.dram_ns + ' ns = <b>' + C2.lat_ns + ' ns</b>。</p>',
  apply: function (S) { S.pos.hw = 'h_done'; S.done = blank(16, T2D); put(S, 'done', doneVals(C2), 'h', bC2); S.done.hot = []; S.irq = 1; led(S, 'done', 'h', 'W'); S.clk.d2 = 3;
    S.say.hw = 'KERNEL SW, job done.\nTag ' + hx(C2.tag) + ': ' + C2.status_name + '.\nChunks are back, COT is cleared.'; },
  fx: function (done) { kit.after(900, function () { done(); kit.ping(new T.Vector3(4, 5.6, -25), 0xb48cff, 3); }); } });

/* ---- kernel finishes, the user program goes on */
kn({ title: '讀第二張 completion', cam: L.VIEW.kread, keep: [K.done], card: doneCard,
  text: '<p>kernel 讀第二張 completion：' + c('tag = ' + hx(C2.tag)) + '、' + c('status = ' + C2.status) + '。兩個 job 都成功了。</p>'
    + '<p>kernel 把筆記裡 page ' + H + ' 的狀態從 ' + c('decompressing') + ' 改成 ' + c('present') + '，並把它排進 LRU 清單的最後面（剛被用到）。</p>',
  apply: function (S) { S.pos.kernel = 'k_done'; S.irq = 0; readAll(S, 'done', 'k'); S.done.hot = ['status', 'tag']; S.pte.st = 'present';
    S.say.kernel = 'Tag ' + hx(C2.tag) + ': ' + C2.status_name + '.\nPage ' + H + ' is present again.'; } });
kn({ title: '最後才把 PTE 設回 valid', cam: L.VIEW.pte, keep: [K.pte, K.gate],
  text: '<p>kernel 把 page ' + H + ' 的 PTE 寫成 ' + c('valid = 1') + '，指向 <b>frame ' + V.frame + '</b>。</p>'
    + '<p>這一步<b>故意排在最後</b>。如果 frame 還沒寫完就 valid，' + RQ.name + ' 會讀到半成品。順序是：資料到位、收尾完成，才開門。</p>'
    + '<p>整個過程 PTE 只有 kernel 寫。LZ4 HW 不碰 page table，就像 kernel 不碰 COT。</p>',
  apply: function (S) { S.pos.kernel = 'k_gate'; S.pte.valid = 1; S.pte.hot = true; S.pte.w = true; led(S, 'pte', 'k', 'W');
    S.say.kernel = 'PTE of page ' + H + ': valid = 1,\nit points to frame ' + V.frame + '.\n' + RQ.name + ', go on.'; },
  card: function () { return L.tableCard('What KERNEL SW changed', [['PTE valid bit', '0, now <span class="by k">1</span>'], ['PTE points to', 'frame ' + V.frame + ' @' + FPA], ["kernel's page state", 'decompressing, now <span class="by k">present</span>']]); } });

var kns = RQ.kernel_ns, sum = kns + C1.lat_ns + C2.lat_ns;
step({ who: 'user', title: RQ.name + ' 重試，這次通過', cam: L.VIEW.far, keep: [K.gate, K.pte],
  text: '<p>kernel 從 page fault 返回，CPU 把 ' + RQ.name + ' 剛才那個' + RWZ + '的動作<b>重做一次</b>。這次 gate 查到 ' + c('valid = 1') + '，直接通過，' + RQ.name + ' 拿到 frame ' + V.frame + ' 裡的資料。</p>'
    + '<p>對 ' + RQ.name + ' 來說，什麼事都沒發生，只是這一次' + RWZ + '比平常慢。它等了 ' + c(kns + ' + ' + C1.lat_ns + ' + ' + C2.lat_ns) + ' = <b>' + sum + ' ns</b>' + (sum === RQ.lat_ns ? '，和 simulator 記錄的這次存取的 latency 相同' : '') + '。其中 kernel 處理 page fault 的固定成本佔了大半。</p>',
  apply: function (S) { S.pos.kernel = 'k_home'; S.pos.hw = 'h_home'; S.gate = 'pass'; S.pte.w = false; S.pte.hot = true;
    S.say.gate = 'PTE of page ' + H + ': valid = 1.\nGo on to frame ' + V.frame + '.'; S.say.req = 'Got my data from page ' + H + '.\nI never knew it was compressed.'; },
  card: function () { var rows = [['KERNEL SW, page-fault handling', kns + ' ns'], ['LZ4 HW, ' + J1.op_name, C1.dram_accesses + ' × ' + M.dram_ns + ' + ' + M.decomp_ns + ' = ' + C1.lat_ns + ' ns'], ['LZ4 HW, ' + J2.op_name, C2.dram_accesses + ' × ' + M.dram_ns + ' = ' + C2.lat_ns + ' ns'], ['total', sum + ' ns']];
    rows[3].hot = true; return L.tableCard('What ' + RQ.name + ' waited for', rows); } });

step({ who: 'note', title: '結果：誰碰了什麼', cam: L.VIEW.all, keep: [K.gate, K.pte],
  text: '<p>page ' + H + ' 回到 frame 裡，' + NCH + ' 個 chunk 還給了 stack，COT[' + H + '] 回到全 0。和上一課的壓縮合起來，剛好是一個完整的來回。</p>'
    + '<p>看下面的表：<b class="k">KERNEL SW</b> 寫了 PTE、兩張 descriptor 和 DOORBELL，讀了兩張 completion。COT、chunk、frame 的資料、free-chunk stack 全部只有 <b class="h">LZ4 HW</b> 在碰。kernel 連這個 page 用了幾個 chunk 都不知道。</p>'
    + '<p>分工也很清楚：<b>要不要做、什麼時候做</b>是 kernel 決定的（認出情況、拿 frame、決定丟掉壓縮的那一份、最後開門）；<b>怎麼做</b>是硬體的事（查 COT、收 chunk、驗 checksum、解碼）。</p>'
    + '<p>接下來的課是偏軟體的設計：chunk 號碼改由 kernel 自己記，直接寫在 descriptor 裡，硬體不再有 COT 和 stack。到時可以對照這一課，看同一件事換人記帳之後哪裡變了。</p>',
  apply: function (S) { S.final = true; S.gate = 'idle'; S.pos.req = 'ui_home'; S.pos.kernel = 'k_home'; S.pos.hw = 'h_home'; S.pte.w = false;
    S.say.req = 'Back to work.'; S.say.kernel = 'Two jobs, one page back.'; S.say.hw = 'I kept the books:\nCOT, chunks, stack.'; },
  card: function () { return L.tableCard('Before and after, page ' + H, [['where the page is', NCH + ' chunks (' + SL + ' B), now frame ' + V.frame + ' (' + M.page + ' B)'], ['free frames', D.frames.free_before + ', now ' + D.frames.free_after],
    ['PTE', 'valid 0, now 1'], ['COT[' + H + ']', 'VALID with ' + NCH + ' chunks, now all zero'], ['free-chunk stack', D.stack.size_before + ' numbers, now ' + D.stack.size_after],
    ['LZ4 HW jobs', J1.op_name + ' ' + C1.lat_ns + ' ns, ' + J2.op_name + ' ' + C2.lat_ns + ' ns']]); } });

var reqCss = A.req ? A.req.css : '#ff8fb1';
lesson = new R.Lesson({
  kit: kit, steps: steps, init: init, pose: L.pose, show: L.show,
  card: function (S, st) { return st.card ? st.card(S) : ''; },
  clock: function (S) {
    var k = S.clk; if (!k.job) return 'LZ4 HW job time: not started';
    var t1 = k.d1 * M.dram_ns + k.lz * M.decomp_ns;
    if (k.job === 1) return 'LZ4 HW · ' + J1.op_name + ' so far: <b>' + k.d1 + ' × ' + M.dram_ns + ' ns</b> DRAM' + (k.lz ? ' + <b>' + M.decomp_ns + ' ns</b> LZ4' : '') + ' = <b>' + t1 + ' ns</b>';
    return 'LZ4 HW · ' + J1.op_name + ' <b>' + t1 + ' ns</b>, then ' + J2.op_name + ': <b>' + k.d2 + ' × ' + M.dram_ns + ' ns</b> DRAM = <b>' + k.d2 * M.dram_ns + ' ns</b>';
  },
  ledger: [['pte', 'PTE of page ' + H], ['desc', 'job descriptors'], ['bell', 'DOORBELL register'], ['cot', 'COT[' + H + ']'], ['chunk', 'chunks (compressed data)'],
           ['frame', 'frame data (' + M.page + ' B)'], ['stack', 'free-chunk stack'], ['done', 'completions']],
  who: { user: ['USER SW', reqCss], kernel: ['KERNEL SW', '#f4d35e'], hw: ['LZ4 HW · HARDWARE', '#b48cff'], note: ['SUMMARY', '#7ee2a8'] }
});
document.getElementById('title').textContent = 'LZ4 DRAM compression lesson';
document.getElementById('design').textContent = 'HW-LEANING DESIGN';
document.getElementById('scene').textContent = 'Scene: DECOMPRESS on an invalid PTE · real job from simulator run seed ' + M.seed + ', access ' + RQ.access_no;
R.lesson = lesson;
})();

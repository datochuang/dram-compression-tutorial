/* ---------- the CPU-MMU view: two cores with one TLB each, one page table, a few frames ----------
   The model follows the platform premises in CLAUDE.md: the CPU MMU looks only in its own core's TLB (P3),
   it never reads the page table, and a TLB miss is an exception that the kernel SW handles (P1).
   What the platform has not settled is an example here and says so on screen: the TLB size, which entry is
   replaced, and how one core gets another core's TLB cleared.
   Each core has two hardware threads that share its TLB (P3) and its L1; the L2 is shared by all cores (P2).
   The kernel SW instances share one lock, mm_lock, for the tables they all write.
   The compression layer is one step. Its detail is in sim.js and the pages built from it. */
const PAGE = 4096, NCORE = 2, NTHR = 2, NTLB = 3;
const PAGES = [0x414, 0x415, 0x416, 0x417, 0x418, 0x419], NP = PAGES.length;
const FRAME_ADDR = [0x80024000, 0x80025000, 0x8003A000, 0x8003B000], NF = FRAME_ADDR.length;
const OFFS = [0x7B4, 0x230, 0xC80, 0xA14, 0x5E8, 0x09C];           // the offset used when a scene or a button touches each page
const HX = (n, w) => '0x' + n.toString(16).toUpperCase().padStart(w, '0');
const pgNo = p => HX(PAGES[p], 3), frNo = f => HX(FRAME_ADDR[f], 8), offNo = o => HX(o, 3);
const laNo = (p, o) => HX(PAGES[p] * PAGE + o, 8), paNo = (f, o) => HX(FRAME_ADDR[f] + o, 8);
const C = s => `<code>${s}</code>`;
const WHO = { user: 'USER SW', mmu: 'CPU MMU · 硬體', kernel: 'KERNEL SW', both: 'KERNEL SW / LZ4 HW' };

/* state
   pte[p]      frame index, or null when the PTE is invalid
   tlb[c][s]   { p, f } or null: what core c's TLB holds in slot s. One TLB per core, used by both of its threads
   hand[c]     the slot core c replaces next when its TLB is full (an example policy)
   frames[f]   the page whose contents are in frame f, or null
   hold[f]     the page frame f has been taken for while its contents are still on the way, or null
   stored[p]   true when the compression layer keeps page p's contents
   busy[p]     the kernel's own note about a page with a job running: 'in' coming back, 'out' going out, or null
   run[c][t]   the access hardware thread t of core c has issued: { p, off, kind, stage }, or null
   kern[c][t]  what the kernel SW instance on that thread is doing, or null when the thread runs user SW
   lock        mm_lock: { by: [c, t] or null, wait: [[c, t], ...] }
   l1[c][f]    whether core c's L1 holds data of frame f: null, 'clean', or 'dirty' when it is newer than DRAM
   l2[f]       the same for the shared L2
   order       pages that have a frame, oldest first: the example's way of picking which page gives up its frame */
const none = n => Array(n).fill(null);
function initState() {
  return {
    pte: [1, null, 0, 2, null, null],
    tlb: [[{ p: 2, f: 0 }, null, null], [null, null, null]],
    hand: [0, 0],
    frames: [2, 0, 3, null], hold: none(NF),
    stored: [false, true, false, false, true, true], busy: none(NP),
    run: [none(NTHR), none(NTHR)], kern: [none(NTHR), none(NTHR)],
    lock: { by: null, wait: [] },
    l1: [none(NF), none(NF)], l2: none(NF),
    order: [2, 0, 3],
  };
}
const clone = st => JSON.parse(JSON.stringify(st));
const slotOf = (st, c, p) => st.tlb[c].findIndex(e => e && e.p === p);
const holders = (st, p) => st.tlb.map((t, c) => slotOf(st, c, p) >= 0 ? c : -1).filter(c => c >= 0);
// An entry is stale when the page table no longer says what the entry says.
const stale = (st, e) => !!e && st.pte[e.p] !== e.f;
const coreList = cs => cs.map(c => 'Core ' + c).join(' 與 ');
const freeFrame = st => st.frames.findIndex((o, f) => o === null && st.hold[f] === null);
const thr = (c, t) => `Core ${c} 的 thread ${t}`;
// Where a frame's newest data is when DRAM does not have it: 'L1 of Core 0', 'L2', or null.
const newest = (st, f) => { const c = st.l1.findIndex(l => l[f] === 'dirty'); return c >= 0 ? 'L1 of Core ' + c : st.l2[f] === 'dirty' ? 'L2' : null; };
const zhCache = s => s.replace(/^L1 of Core (\d)$/, 'Core $1 的 L1').replace(/^L2$/, '共用的 L2');
const cached = (st, f) => st.l1.map((l, c) => l[f] ? 'L1 of Core ' + c : '').concat(st.l2[f] ? 'L2' : '').filter(Boolean);

function Plan(st0) {
  const P = { st: clone(st0), steps: [] };
  P.st.run = [none(NTHR), none(NTHR)]; P.st.kern = [none(NTHR), none(NTHR)];
  P.push = (who, core, text, x = {}) => P.steps.push(Object.assign({ who, core, text, st: clone(P.st), hl: {}, links: [] }, x));
  return P;
}

/* mm_lock. One kernel SW instance holds it at a time; the others wait in line. */
function lockTake(st, c, t) { if (st.lock.by === null) { st.lock.by = [c, t]; return true; } st.lock.wait.push([c, t]); return false; }
function lockGive(st) { st.lock.by = st.lock.wait.shift() || null; return st.lock.by; }

// Put page p's mapping into core c's TLB. Returns the slot and the page that was replaced, if any.
function fillTlb(st, c, p) {
  let s = st.tlb[c].findIndex(e => !e), out = null;
  if (s < 0) { s = st.hand[c]; out = st.tlb[c][s].p; st.hand[c] = (s + 1) % NTLB; }
  st.tlb[c][s] = { p, f: st.pte[p] };
  return { s, out };
}

/* The caches, after the CPU MMU has produced a physical address in frame f. L1 of this core first, then the shared L2,
   then DRAM. The page tracks only whether a cache holds data of a frame and whether that data is newer than DRAM.
   Which cache keeps a copy afterwards, and how the hardware keeps the cores' caches consistent, are drawn as an example. */
function cacheUse(st, c, f, kind) {
  let via = 'l1', moved = null;
  if (!st.l1[c][f]) {
    const o = st.l1.findIndex((l, k) => k !== c && l[f] === 'dirty');
    if (o >= 0) { st.l1[o][f] = 'clean'; st.l2[f] = 'dirty'; moved = o; }     // the newest copy was in another core's L1
    via = st.l2[f] ? 'l2' : 'dram';
    if (!st.l2[f]) st.l2[f] = 'clean';
    st.l1[c][f] = 'clean';
  }
  const dropped = [];
  if (kind === 'write') { st.l1.forEach((l, k) => { if (k !== c && l[f]) { l[f] = null; dropped.push(k); } }); st.l1[c][f] = 'dirty'; }
  return { via, moved, dropped };
}
function cacheText(c, kind, r, brief) {
  const rd = kind === 'read';
  let s = r.via === 'l1' ? `Physical address 先問 Core ${c} 的 L1：有。${rd ? '資料直接從 L1 回來' : '資料寫進 L1'}，沒有碰到 L2，也沒有碰到 DRAM。`
    : r.via === 'l2' ? `Core ${c} 的 L1 沒有這筆資料，往下問共用的 L2：有。` + (r.moved !== null ? `最新的那一份原本在 Core ${r.moved} 的 L1，硬體先把它交給 L2。` : '') + `資料由 L2 給，Core ${c} 的 L1 也留一份。沒有碰到 DRAM。`
    : `Core ${c} 的 L1 沒有這筆資料，共用的 L2 也沒有，所以到 DRAM 的 frame 去拿。L2 與 Core ${c} 的 L1 各留一份。`;
  if (brief) s = r.via === 'l1' ? `這次資料由 Core ${c} 的 L1 給。` : r.via === 'l2' ? `這次資料由共用的 L2 給。` : `L1 與 L2 都還沒有這筆資料，所以到 DRAM 的 frame 去拿。`;
  if (!rd) s += `寫進去的資料先留在 Core ${c} 的 L1。DRAM 裡的 frame 這時候比 L1 舊。`;
  if (r.dropped.length) s += `${coreList(r.dropped)} 的 L1 裡同一筆資料由硬體作廢，兩個 core 才不會看到不同的內容。`;
  return s;
}
// What the kernel does to the caches of every core for one frame. clean: dirty data goes back to DRAM. inval: all of it is dropped.
function cacheOp(st, f, op) {
  const from = newest(st, f), had = cached(st, f);
  st.l1.forEach(l => { if (l[f]) l[f] = op === 'clean' ? 'clean' : null; });
  if (st.l2[f]) st.l2[f] = op === 'clean' ? 'clean' : null;
  return { from, had };
}

/* The kernel SW instance on thread t of core c takes page v's frame away.
   Right order: 1 PTE invalid, 2 clear the entry from every core's TLB, 3 only then touch the frame.
   Before the LZ4 HW reads the frame, the caches of every core write what they hold of it back to DRAM.
   wrong = true leaves out the other cores in step 2. held = true when the caller already has mm_lock and keeps it. */
function takeFrame(P, c, t, v, wrong, held) {
  const st = P.st, f = st.pte[v], others = [...Array(NCORE).keys()].filter(k => k !== c), had = holders(st, v);
  if (!held) lockTake(st, c, t);
  st.kern[c][t] = 'frame out · has mm_lock';
  P.push('kernel', c, (held ? `空的 frame 用完了。握著 mm_lock 的這個 kernel SW instance ` : `${thr(c, t)} 上的 kernel SW instance 先拿 mm_lock，然後`) +
    `選 page ${C(pgNo(v))} 讓出 frame ${C(frNo(f))}。` +
    (had.length ? `從圖上看，${coreList(had)} 的 TLB 裡有這個 page 的對應。` : `從圖上看，現在沒有哪個 core 的 TLB 裡有這個 page 的對應。`) +
    `Kernel 沒有記哪個 core 的 TLB 裡有什麼。選哪一個 page 是範例的做法：最早拿到 frame 的那一個。`,
    { hl: { pte: [v], frames: [f], lock: !held } });

  st.pte[v] = null; st.busy[v] = 'out';
  P.push('kernel', c, `第 1 步：kernel 把 page ${C(pgNo(v))} 的 PTE 改成 invalid，並在自己的表裡記下這個 page 正要送去壓縮。從現在起，TLB miss 之後 kernel 讀到的都是 invalid。` +
    (had.length ? `但是 TLB 裡的舊對應還在。照舊對應走的 access 是 TLB hit，不會進 kernel。圖上把這種過期的 entry 標成 stale。` : ''),
    { hl: { pte: [v] }, links: [{ t: 'pte', core: c, thr: t, p: v }] });

  const own = slotOf(st, c, v);
  if (own >= 0) st.tlb[c][own] = null;
  P.push('kernel', c, `第 2 步：kernel 把這一筆從 Core ${c} 自己的 TLB 清掉。` + (own < 0 ? `Core ${c} 的 TLB 本來就沒有這一筆，清的動作照做。` : '') +
    (wrong ? `<b>錯誤示範從這裡開始</b>：kernel 只清了自己這個 core，沒有去清其他 core 的 TLB。` : ''),
    { hl: { tlb: own >= 0 ? [[c, own]] : [] }, links: own >= 0 ? [{ t: 'fill', core: c, thr: t, slot: own }] : [] });

  if (!wrong) {
    const cleared = [];
    others.forEach(k => { const s = slotOf(st, k, v); if (s >= 0) { st.tlb[k][s] = null; cleared.push([k, s]); } });
    P.push('kernel', c, `第 2 步還沒完：其他每一個 core 的 TLB 也要清掉這一筆，kernel 要等它們都清完。` +
      (cleared.length ? '' : `這一次其他 core 的 TLB 沒有這一筆，但是 kernel 不知道，所以照樣要清。`) +
      `用什麼機制清掉另一個 core 的 TLB，這個平台還不知道，圖上只畫出結果。`,
      { hl: { tlb: cleared }, links: cleared.map(([k, s]) => ({ t: 'clear', core: c, thr: t, to: k, slot: s })) });
  }

  lockGive(st); st.kern[c][t] = 'cache clean · no lock';
  const r = cacheOp(st, f, 'clean');
  P.push('kernel', c, (wrong ? `Kernel 以為沒有人碰得到 frame ${C(frNo(f))} 了。` : `每個 core 的 TLB 都清完了，沒有人碰得到 frame ${C(frNo(f))}。`) +
    `Kernel 放開 mm_lock，接著做 cache clean：這份設計假設 LZ4 HW 直接讀 DRAM，不經過 CPU 的 cache，所以每個 core 的 cache 裡比 DRAM 新的資料要先寫回 DRAM。` +
    (r.from ? `這一次${r.from === 'L2' ? '' : ' '}${zhCache(r.from)} 裡有還沒寫回的資料。不做這一步，LZ4 HW 壓縮到的就是舊的內容。` : `這一次沒有還沒寫回的資料，但是 kernel 不知道，照樣要做。`) +
    `用什麼指令、怎麼讓其他 core 也做，這個平台還不知道。`,
    { hl: { frames: [f], pte: [v], cop: { f, op: 'clean' } }, links: [{ t: 'cop', op: 'clean', core: c, thr: t, f, from: r.from }] });

  st.frames[f] = null; st.stored[v] = true; st.busy[v] = null; st.order = st.order.filter(q => q !== v);
  if (held) { lockTake(st, c, t); st.kern[c][t] = 'page fault · has mm_lock'; } else st.kern[c][t] = null;
  P.push('both', c, (wrong ? `然後 kernel 就開始動這個 frame。` : `第 3 步：到這裡才可以動 frame。`) +
    `壓縮層把 page ${C(pgNo(v))} 的內容壓縮後收起來。這一步由 kernel SW 與 LZ4 HW 完成，等 LZ4 HW 的時候不握 lock，細節在 LZ4 那一條線，這裡只算一步。做完之後 kernel 再拿 mm_lock，記下 frame ${C(frNo(f))} 空出來了` +
    (held ? `，lock 繼續握著。` : `，然後放開 lock。`),
    { hl: { frames: [f], store: [v], pte: [v] }, links: [{ t: 'lz', dir: 'in', f, p: v }] });
  return f;
}

/* One access from thread t of core c to page p. Three outcomes: TLB hit; TLB miss with a valid PTE; TLB miss with an invalid PTE. */
function access(P, c, t, p, off, kind, opt = {}) {
  const st = P.st, la = laNo(p, off), me = thr(c, t), rd = kind === 'read';
  const run = stage => { st.run[c][t] = { p, off, kind, stage }; };
  const data = (s, old, r) => ({ hl: { tlb: [[c, s]], frames: old || r.via === 'dram' ? [st.tlb[c][s].f] : [], warn: old, cache: { core: c, f: st.tlb[c][s].f, via: r.via } },
    links: [{ t: 'data', core: c, thr: t, slot: s, f: st.tlb[c][s].f, off, kind, warn: old, via: r.via }] });

  run('ask');
  P.push('user', c, `${me} 上的 user SW 對 logical address ${C(la)} 做 ${kind}。這個 address 是 page ${C(pgNo(p))}、offset ${C(offNo(off))}。`);

  let s = slotOf(st, c, p);
  if (s >= 0) {
    const e = st.tlb[c][s], old = stale(st, e);
    run(old ? 'stale' : 'hit');
    P.push('mmu', c, old
      ? `Core ${c} 的 CPU MMU 在自己的 TLB 找到 page ${C(pgNo(p))}：frame ${C(frNo(e.f))}。這一筆已經過期，但是 CPU MMU 分不出來。它照常轉換成 physical address ${C(paNo(e.f, off))}，沒有 exception，kernel 沒有被叫起來。`
      : `Core ${c} 的 CPU MMU 在自己的 TLB 找到 page ${C(pgNo(p))}：frame ${C(frNo(e.f))}。Physical address 是 ${C(frNo(e.f))} 加 ${C(offNo(off))}，等於 ${C(paNo(e.f, off))}。這是 TLB hit：整個過程只有硬體，kernel SW 沒有被叫起來。` + (opt.hitNote || ''),
      { hl: { tlb: [[c, s]], warn: old }, links: [{ t: 'xlate', core: c, thr: t, slot: s, warn: old }] });
    const r = cacheUse(st, c, e.f, kind), holds = st.frames[e.f];
    if (old) {
      P.push('user', c, `User SW ${rd ? '讀到' : '寫進'}的是 frame ${C(frNo(e.f))} 現在的內容，` +
        (holds === null ? `而這個 frame 已經是空的，隨時會交給別的 page。` : `也就是 page ${C(pgNo(holds))} 的資料。`) +
        `沒有任何錯誤訊息，kernel 不知道這件事發生過。${rd ? '如果這是 write，別的 page 的資料就被蓋掉了。' : '別的 page 的資料被蓋掉了。'}`, data(s, true, r));
    } else {
      run('done');
      P.push('mmu', c, (opt.cacheIntro || '') + cacheText(c, kind, r, opt.brief) + `User SW 繼續往下跑，它不知道中間有過轉換。`, data(s, false, r));
    }
    st.run[c][t] = null;
    return;
  }

  st.kern[c][t] = 'TLB miss handler'; run('miss');
  P.push('mmu', c, `Core ${c} 的 CPU MMU 在自己的 TLB 找不到 page ${C(pgNo(p))}。` +
    (opt.missNote || '') + `CPU MMU 不會去讀 page table。它發出 TLB miss exception：user SW 停在這個指令上，${me} 改跑 kernel SW。`,
    { hl: { miss: [c] } });

  run('wait');
  if (st.pte[p] !== null) {
    P.push('kernel', c, `Kernel 讀 page table 裡 page ${C(pgNo(p))} 的 PTE：valid，frame ${C(frNo(st.pte[p]))}。Page 就在 frame 裡，只是這個 core 的 TLB 沒有這一筆。這不是 page fault，壓縮層不參與。`,
      { hl: { pte: [p] }, links: [{ t: 'pte', core: c, thr: t, p }] });
  } else {
    st.kern[c][t] = 'page fault';
    P.push('kernel', c, `Kernel 讀 page table 裡 page ${C(pgNo(p))} 的 PTE：invalid。這個 page 現在沒有 frame。這種情況叫 page fault。`,
      { hl: { pte: [p], warnPte: p }, links: [{ t: 'pte', core: c, thr: t, p }] });
    lockTake(st, c, t); st.kern[c][t] = 'page fault · has mm_lock';
    let f = freeFrame(st), intro = `接下來要改好幾個 instance 共用的表，所以 kernel 先拿 mm_lock。握著 lock，它先確認沒有別的 instance 正在處理這個 page。`;
    if (f < 0) {
      P.push('kernel', c, intro + `然後一看，沒有空的 frame，要先讓別的 page 讓出一個。`, { hl: { lock: true } });
      f = takeFrame(P, c, t, opt.victim !== undefined ? opt.victim : st.order[0], opt.wrong, true);
      intro = `握著 mm_lock，kernel `;
    } else intro += `然後`;
    st.hold[f] = p; st.busy[p] = 'in';
    P.push('kernel', c, intro +
      `拿空的 frame ${C(frNo(f))}，記下「page ${C(pgNo(p))} 正在還原」。這樣別的 instance 就不會再拿這個 frame，也不會替同一個 page 再還原一次。`,
      { hl: { frames: [f], pte: [p], lock: true } });
    lockGive(st); st.kern[c][t] = 'waits for LZ4 HW'; st.frames[f] = p; st.hold[f] = null;
    P.push('both', c, `Kernel 放開 mm_lock，然後才請壓縮層把 page ${C(pgNo(p))} 的內容還原到 frame ${C(frNo(f))}：kernel SW 查自己的表找到壓縮後的資料，LZ4 HW 解壓縮。等 LZ4 HW 的時間比較長，這段時間不握 lock。細節在 LZ4 那一條線，這裡只算一步。`,
      { hl: { frames: [f], store: [p] }, links: [{ t: 'lz', dir: 'out', f, p }] });
    st.kern[c][t] = 'cache invalidate';
    const r = cacheOp(st, f, 'inval');
    P.push('kernel', c, `這份設計假設 LZ4 HW 直接寫 DRAM，不經過 CPU 的 cache。Cache 裡如果留著這個 frame 以前的資料，就比 DRAM 舊。Kernel 讓每個 core 的 L1 與共用的 L2 把這個 frame 的資料作廢。` +
      (r.had.length ? `這一次 cache 裡確實留著舊資料。` : `這一次 cache 裡沒有，但是 kernel 不知道，照樣要做。`) + `用什麼指令、怎麼讓其他 core 也做，這個平台還不知道。`,
      { hl: { frames: [f], cop: { f, op: 'inval' } }, links: [{ t: 'cop', op: 'inval', core: c, thr: t, f, from: null }] });
    lockTake(st, c, t); st.kern[c][t] = 'page fault · has mm_lock';
    st.pte[p] = f; st.stored[p] = false; st.busy[p] = null; st.order.push(p);
    P.push('kernel', c, `Kernel 再拿一次 mm_lock，把 page ${C(pgNo(p))} 的 PTE 改成 valid，指向 frame ${C(frNo(f))}。壓縮層那一份不再需要。其他 core 的 TLB 不需要動：它們沒有這個 page 的舊對應。`,
      { hl: { pte: [p], store: [p], lock: true }, links: [{ t: 'pte', core: c, thr: t, p }] });
  }

  const locked = !!st.lock.by, r = fillTlb(st, c, p); s = r.s; st.kern[c][t] = null; run('back');
  if (locked) lockGive(st);
  P.push('kernel', c, `Kernel 把「page ${C(pgNo(p))}：frame ${C(frNo(st.pte[p]))}」填進 Core ${c} 的 TLB，${locked ? '放開 mm_lock，' : ''}然後返回 user SW。` +
    (r.out !== null ? `TLB 滿了，page ${C(pgNo(r.out))} 那一筆被蓋掉。TLB 有 ${NTLB} 格、輪流蓋掉都是範例，平台的 TLB 大小與取代方式還不知道。` : '') +
    (opt.fillNote || ''),
    { hl: { tlb: [[c, s]], lock: locked }, links: [{ t: 'fill', core: c, thr: t, slot: s }] });
  const e = st.tlb[c][s], cr = cacheUse(st, c, e.f, kind);
  run('hit');
  P.push('mmu', c, `CPU 重跑同一個指令。這次 Core ${c} 的 TLB 裡有這一筆，CPU MMU 直接轉換成 physical address ${C(paNo(e.f, off))}。` + cacheText(c, kind, cr, true) + `User SW 只覺得這個指令慢了一點。`, data(s, false, cr));
  st.run[c][t] = null;
}

// The kernel takes n frames away before a scene starts, in the right order. The scene's first step says so.
function quietEvict(st, n) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const v = st.order.shift(), f = st.pte[v];
    st.pte[v] = null; st.tlb.forEach(t => t.forEach((e, s) => { if (e && e.p === v) t[s] = null; }));
    cacheOp(st, f, 'clean'); st.frames[f] = null; st.stored[v] = true; out.push(v);
  }
  return out;
}
const dataLink = (st, c, t, s, off, kind, r) => ({ t: 'data', core: c, thr: t, slot: s, f: st.tlb[c][s].f, off, kind, warn: false, via: r.via });

/* Two kernel SW instances page-fault at the same time on two different pages. They take turns at mm_lock;
   the two decompress jobs run in the LZ4 HW at the same time (P4). */
function twoFaults(P) {
  const st = P.st, out = quietEvict(st, 2), A = 4, B = 5, oa = OFFS[A], ob = OFFS[B];
  const run = (c, p, off, kind, stage) => { st.run[c][0] = { p, off, kind, stage }; };
  const both = stage => { run(0, A, oa, 'write', stage); run(1, B, ob, 'read', stage); };
  both('ask');
  P.push('user', null, `場景開始前，kernel 已經照場景 7 的順序讓 page ${C(pgNo(out[0]))} 與 ${C(pgNo(out[1]))} 讓出 frame，所以現在有兩個空的 frame。` +
    `兩個 core 上的 user SW 幾乎同時發出 access：Core 0 寫 page ${C(pgNo(A))}，Core 1 讀 page ${C(pgNo(B))}。兩個 page 都收在壓縮層。`, { hl: { frames: out.map((v, i) => freeAt(st, i)) } });

  both('miss'); st.kern[0][0] = st.kern[1][0] = 'TLB miss handler';
  P.push('mmu', null, `兩個 core 的 CPU MMU 各查自己的 TLB，都找不到。兩邊各發出一個 TLB miss exception，兩個 thread 都改跑 kernel SW。Kernel 的程式只有一份，現在有兩個 instance 同時在跑，各用各的 stack。`, { hl: { miss: [0, 1] } });

  both('wait'); st.kern[0][0] = st.kern[1][0] = 'page fault';
  P.push('kernel', null, `兩個 instance 各讀自己要的 PTE：都是 invalid。兩邊都是 page fault，兩邊都需要一個空的 frame。`,
    { hl: { pte: [A, B] }, links: [{ t: 'pte', core: 0, thr: 0, p: A }, { t: 'pte', core: 1, thr: 0, p: B }] });

  lockTake(st, 0, 0); lockTake(st, 1, 0); st.kern[0][0] = 'page fault · has mm_lock'; st.kern[1][0] = 'waits for mm_lock';
  P.push('kernel', null, `哪個 frame 是空的，記在兩個 instance 共用的表裡。要改共用的表，先拿 mm_lock。Lock 一次只給一個 instance：Core 0 的先拿到，Core 1 的排隊等。等的是 kernel SW instance，不是硬體。`, { hl: { lock: true } });

  const fa = freeFrame(st); st.hold[fa] = A; st.busy[A] = 'in';
  P.push('kernel', 0, `Core 0 的 instance 握著 lock，確認沒有別人正在處理 page ${C(pgNo(A))}，拿空的 frame ${C(frNo(fa))}，記下「這個 frame 給 page ${C(pgNo(A))}，正在還原」。`, { hl: { frames: [fa], pte: [A] } });

  lockGive(st); st.kern[0][0] = 'waits for LZ4 HW'; st.kern[1][0] = 'page fault · has mm_lock';
  P.push('kernel', null, `Core 0 的 instance 放開 lock，把還原的工作交給壓縮層。握 lock 的時間只有查表與記帳那幾步。Lock 一放開，排隊的 Core 1 instance 就拿到。`, { hl: { lock: true } });

  const fb = freeFrame(st); st.hold[fb] = B; st.busy[B] = 'in';
  P.push('kernel', 1, `Core 1 的 instance 握著 lock 看同一張表：frame ${C(frNo(fa))} 已經記給別人了，所以它拿下一個空的 frame ${C(frNo(fb))}，記下「正在還原 page ${C(pgNo(B))}」。兩個 instance 沒有拿到同一個 frame，靠的就是輪流看、輪流記。`, { hl: { frames: [fb], pte: [B] } });

  lockGive(st); st.kern[1][0] = 'waits for LZ4 HW';
  st.frames[fa] = A; st.hold[fa] = null; st.frames[fb] = B; st.hold[fb] = null;
  P.push('both', null, `Core 1 的 instance 也放開 lock，交出還原的工作。現在沒有人握 lock，兩個還原同時在 LZ4 HW 裡進行：照平台前提，LZ4 HW 可以同時接受好幾個工作。Lock 保護的是共用的表，不是 LZ4 HW。`,
    { hl: { frames: [fa, fb], store: [A, B], lock: true }, links: [{ t: 'lz', dir: 'out', f: fa, p: A }, { t: 'lz', dir: 'out', f: fb, p: B }] });

  st.kern[0][0] = st.kern[1][0] = 'cache invalidate'; cacheOp(st, fa, 'inval'); cacheOp(st, fb, 'inval');
  P.push('kernel', null, `兩邊的資料都回到 frame 了。兩個 instance 各自讓每個 core 的 cache 把自己那個 frame 的舊資料作廢。這一步也不握 lock。`,
    { hl: { frames: [fa, fb], cop: { f: fa, op: 'inval' } }, links: [{ t: 'cop', op: 'inval', core: 0, thr: 0, f: fa, from: null }, { t: 'cop', op: 'inval', core: 1, thr: 0, f: fb, from: null }] });

  lockTake(st, 0, 0); lockTake(st, 1, 0); st.kern[0][0] = 'page fault · has mm_lock'; st.kern[1][0] = 'waits for mm_lock';
  st.pte[A] = fa; st.stored[A] = false; st.busy[A] = null; st.order.push(A);
  const sa = fillTlb(st, 0, A).s;
  P.push('kernel', null, `最後要改 PTE，又是共用的表，兩邊再排一次隊。Core 0 的 instance 先拿到 lock：把 page ${C(pgNo(A))} 的 PTE 改成 valid，再把這一筆填進 Core 0 的 TLB。Core 1 的 instance 等。`,
    { hl: { pte: [A], store: [A], tlb: [[0, sa]], lock: true }, links: [{ t: 'pte', core: 0, thr: 0, p: A }, { t: 'fill', core: 0, thr: 0, slot: sa }] });

  lockGive(st); st.kern[0][0] = null; run(0, A, oa, 'write', 'back'); st.kern[1][0] = 'page fault · has mm_lock';
  st.pte[B] = fb; st.stored[B] = false; st.busy[B] = null; st.order.push(B);
  const sb = fillTlb(st, 1, B).s;
  P.push('kernel', null, `Core 0 的 instance 放開 lock，返回 user SW。Core 1 的 instance 拿到 lock，對 page ${C(pgNo(B))} 做同樣的事：PTE 改成 valid，填進 Core 1 的 TLB。`,
    { hl: { pte: [B], store: [B], tlb: [[1, sb]], lock: true }, links: [{ t: 'pte', core: 1, thr: 0, p: B }, { t: 'fill', core: 1, thr: 0, slot: sb }] });

  lockGive(st); st.kern[1][0] = null; both('hit');
  const ra = cacheUse(st, 0, fa, 'write'), rb = cacheUse(st, 1, fb, 'read');
  P.push('mmu', null, `Core 1 的 instance 也放開 lock 並返回。兩個 core 各自重跑原來的指令，這次都是 TLB hit。兩個 user SW 都只覺得這個指令慢了一點。`,
    { hl: { tlb: [[0, sa], [1, sb]], frames: [fa, fb], lock: true }, links: [dataLink(st, 0, 0, sa, oa, 'write', ra), dataLink(st, 1, 0, sb, ob, 'read', rb)] });
  st.run[0][0] = st.run[1][0] = null;

  P.push('kernel', null, `如果沒有 mm_lock：兩個 instance 可能在同一瞬間都看到 frame ${C(frNo(fa))} 是空的，各自拿走，兩個 page 還原到同一個 frame，後寫的蓋掉先寫的。Lock 讓「看表」到「記下來」之間沒有別人插進來。至於只填 TLB、不改表的 TLB miss handler 要不要拿 mm_lock，目前的設計還沒有決定。`, {});
}
const freeAt = (st, i) => st.frames.map((o, f) => o === null ? f : -1).filter(f => f >= 0)[i];

/* Two cores touch the same compressed page at the same time. One instance brings it back; the other finds the
   kernel's note under the lock, starts nothing, and sleeps until the page is there. */
function samePage(P) {
  const st = P.st, out = quietEvict(st, 1), A = 0, o0 = OFFS[A], o1 = 0x2C0;
  const run = (c, off, stage) => { st.run[c][0] = { p: A, off, kind: 'read', stage }; };
  const both = stage => { run(0, o0, stage); run(1, o1, stage); };
  both('ask');
  P.push('user', null, `場景開始前，kernel 已經讓 page ${C(pgNo(out[0]))} 讓出 frame，所以有一個空的 frame。兩個 core 上的 user SW 幾乎同時讀同一個 page ${C(pgNo(A))}，它收在壓縮層。兩個 thread 屬於同一個程式，用同一個 page table。`, { hl: { frames: [freeAt(st, 0)], store: [A] } });

  both('miss'); st.kern[0][0] = st.kern[1][0] = 'TLB miss handler';
  P.push('mmu', null, `兩個 core 的 TLB 都沒有 page ${C(pgNo(A))}。兩邊各發出一個 TLB miss exception，兩個 kernel SW instance 同時開始跑。`, { hl: { miss: [0, 1] } });

  both('wait'); lockTake(st, 1, 0); lockTake(st, 0, 0); st.kern[1][0] = 'page fault · has mm_lock'; st.kern[0][0] = 'waits for mm_lock';
  P.push('kernel', null, `兩個 instance 讀到同一個 PTE：invalid。兩邊都是 page fault，都去拿 mm_lock。這一次 Core 1 的先拿到，Core 0 的排隊等。`,
    { hl: { pte: [A], lock: true }, links: [{ t: 'pte', core: 0, thr: 0, p: A }, { t: 'pte', core: 1, thr: 0, p: A }] });

  const f = freeFrame(st); st.hold[f] = A; st.busy[A] = 'in';
  P.push('kernel', 1, `Core 1 的 instance 握著 lock，確認沒有別人正在處理 page ${C(pgNo(A))}，拿空的 frame ${C(frNo(f))}，在自己的表裡記下「page ${C(pgNo(A))} 正在還原」。這個記號是 kernel 自己的，CPU MMU 看不到。`, { hl: { frames: [f], pte: [A] } });

  lockGive(st); st.kern[1][0] = 'waits for LZ4 HW'; st.kern[0][0] = 'page fault · has mm_lock'; st.frames[f] = A; st.hold[f] = null;
  P.push('both', null, `Core 1 的 instance 放開 lock，請壓縮層把內容還原到 frame ${C(frNo(f))}。Lock 一放開，Core 0 的 instance 拿到。`,
    { hl: { frames: [f], store: [A], lock: true }, links: [{ t: 'lz', dir: 'out', f, p: A }] });

  lockGive(st); st.kern[0][0] = 'waits for page ' + pgNo(A);
  P.push('kernel', 0, `Core 0 的 instance 握著 lock 看同一個 page：記號寫著「正在還原」，已經有人在處理。它不拿第二個 frame，也不送第二個還原的工作。它放開 lock 去睡，等的是這個 page，不是 lock。`, { hl: { pte: [A], lock: true } });

  st.kern[1][0] = 'cache invalidate'; cacheOp(st, f, 'inval');
  P.push('kernel', 1, `LZ4 HW 做完了。Core 1 的 instance 讓每個 core 的 cache 把 frame ${C(frNo(f))} 的舊資料作廢。Core 0 的 instance 還在睡，Core 0 上的 user SW 還停在原來的指令上。`,
    { hl: { frames: [f], cop: { f, op: 'inval' } }, links: [{ t: 'cop', op: 'inval', core: 1, thr: 0, f, from: null }] });

  lockTake(st, 1, 0); st.kern[1][0] = 'page fault · has mm_lock';
  st.pte[A] = f; st.stored[A] = false; st.busy[A] = null; st.order.push(A);
  const s1 = fillTlb(st, 1, A).s;
  P.push('kernel', 1, `Core 1 的 instance 再拿 lock：PTE 改成 valid，擦掉「正在還原」的記號，把這一筆填進 Core 1 的 TLB，然後叫醒等這個 page 的 instance。`,
    { hl: { pte: [A], store: [A], tlb: [[1, s1]], lock: true }, links: [{ t: 'pte', core: 1, thr: 0, p: A }, { t: 'fill', core: 1, thr: 0, slot: s1 }] });

  lockGive(st); st.kern[1][0] = null; run(1, o1, 'back'); lockTake(st, 0, 0); st.kern[0][0] = 'page fault · has mm_lock';
  P.push('kernel', null, `Core 1 的 instance 放開 lock，返回 user SW。Core 0 的 instance 被叫醒，拿到 lock，重新看 page ${C(pgNo(A))}：PTE 已經是 valid，page 已經在 frame 裡。`,
    { hl: { pte: [A], lock: true }, links: [{ t: 'pte', core: 0, thr: 0, p: A }] });

  const s0 = fillTlb(st, 0, A).s; lockGive(st); st.kern[0][0] = null; run(0, o0, 'back');
  P.push('kernel', 0, `所以 Core 0 的 instance 要做的只剩一件事：把這一筆填進 Core 0 自己的 TLB。它放開 lock，返回 user SW。它沒有碰壓縮層。`,
    { hl: { tlb: [[0, s0]], lock: true }, links: [{ t: 'fill', core: 0, thr: 0, slot: s0 }] });

  both('hit');
  const r1 = cacheUse(st, 1, f, 'read'), r0 = cacheUse(st, 0, f, 'read');
  P.push('mmu', null, `兩個 core 各自重跑原來的指令，都是 TLB hit，讀到的是同一個 frame。Core 1 先到，資料從 DRAM 來。Core 0 後到，資料由共用的 L2 給。`,
    { hl: { tlb: [[0, s0], [1, s1]], frames: [f] }, links: [dataLink(st, 1, 0, s1, o1, 'read', r1), dataLink(st, 0, 0, s0, o0, 'read', r0)] });
  st.run[0][0] = st.run[1][0] = null;

  P.push('kernel', null, `一個 page，只還原一次，只佔一個 frame。沒有那個記號的話，兩個 instance 會各拿一個 frame、各還原一次，同一個 page 出現兩份，兩個 core 各寫各的。一個 page 正在被壓縮的時候被碰到，也是同樣的等法：那個 instance 等的是 kernel 自己送出去的壓縮做完。LZ4 HW 能同時做再多工作，這種等待也不會變短。`, {});
}

/* scenes: each is a list of things that happen, played on the state the earlier scenes left */
const SCENES = [
  { t: 'TLB hit', run: P => access(P, 0, 0, 2, OFFS[2], 'read', {
      cacheIntro: `有了 physical address，接下來找資料，還是只有硬體。` }) },
  { t: 'TLB miss，PTE valid', run: P => access(P, 0, 0, 3, OFFS[3], 'read') },
  { t: 'TLB miss，PTE invalid：page fault', run: P => access(P, 0, 0, 1, OFFS[1], 'write') },
  { t: '另一個 core 有自己的 TLB', run: P => access(P, 1, 0, 2, 0x044, 'read', {
      missNote: `Core 0 的 TLB 裡有這一筆，但是那是 Core 0 的。每個 core 只查自己的 TLB。`,
      fillNote: `現在兩個 core 的 TLB 各有一份 page ${C(pgNo(2))} 的對應，兩份互不相干。` }) },
  { t: '同一個 core 的兩個 thread 共用 TLB', run: P => {
      access(P, 0, 1, 1, 0x1F8, 'read', {
        hitNote: `這一筆是 thread 0 在場景 3 的 page fault 之後填的。TLB 是 core 的，不是 thread 的，所以 thread 1 直接用得到。`, brief: true });
      P.push('mmu', 0, `同一個 core 的兩個 hardware thread 共用一個 TLB，也共用 L1。反過來也一樣：kernel 在一個 thread 上清掉一筆，另一個 thread 也就沒有這一筆。` +
        `這是專案目前的假設，還沒有對過 CPU 手冊。兩個 thread 同時改同一個 TLB 時 CPU 有什麼限制，目前不知道。`, {});
    } },
  { t: 'L1 與 L2 cache', run: P => {
      access(P, 0, 0, 2, OFFS[2], 'read');
      access(P, 0, 0, 2, 0x7B8, 'write');
      access(P, 1, 0, 2, 0x7B8, 'read');
      P.push('mmu', null, `到這裡，frame ${C(frNo(0))} 最新的資料在共用的 L2 裡，DRAM 裡的還是舊的。CPU 這邊沒有問題：每個 core 的 access 都先經過 cache。` +
        `但是這份設計假設 LZ4 HW 直接讀寫 DRAM，不經過 CPU 的 cache。所以 kernel 把 frame 交給 LZ4 HW 之前要先處理 cache，下一個場景會看到。` +
        `L1 與 L2 各有多大、哪些資料會留在裡面，這一頁沒有模擬，只畫「有沒有」與「是不是比 DRAM 新」。`, { hl: { frames: [0], cache: { core: null, f: 0, via: 'l2' } } });
    } },
  { t: 'Kernel 把 frame 拿走：正確的順序', run: P => {
      takeFrame(P, 1, 1, 2, false, false);
      access(P, 0, 0, 2, OFFS[2], 'read', { missNote: `因為第 2 步把它清掉了。` });
    } },
  { t: '錯誤示範：只清自己那個 core 的 TLB', whatIf: true, from: 6, run: P => {
      access(P, 1, 0, 4, OFFS[4], 'write', { wrong: true });
      access(P, 0, 0, 2, OFFS[2], 'read');
      P.push('kernel', 1, `這就是為什麼順序是：PTE 改 invalid，每個 core 的 TLB 都清掉，然後才動 frame。這個場景和場景 7 從同一個狀態開始，差別只在第 2 步。這個錯誤示範的狀態不會帶到後面：之後的場景與自己發的 access，從場景 7 結束時的狀態接下去。`, {});
    } },
  { t: '兩個 core 同時 page fault：mm_lock', run: twoFaults },
  { t: '兩個 core 同時碰同一個 page', run: samePage },
];

// The state after the first n scenes, what-if scenes left out: they change nothing that is carried on.
function chain(n) {
  let st = initState();
  for (let j = 0; j < n; j++) if (!SCENES[j].whatIf) { const P = Plan(st); SCENES[j].run(P); st = P.st; }
  return st;
}
// The state scene k starts from. `from` lets a what-if scene start where an earlier scene started:
// the wrong-order scene replays scene 7's situation.
const startOf = k => chain(SCENES[k].from !== undefined ? SCENES[k].from : k);
function planScene(k) {
  const P = Plan(startOf(k)); SCENES[k].run(P);
  return { steps: P.steps, final: SCENES[k].whatIf ? chain(k) : P.st };
}
function planAccess(st0, c, t, p, kind) {
  const P = Plan(st0); access(P, c, t, p, OFFS[p], kind);
  return { steps: P.steps, final: P.st };
}
if (typeof module !== 'undefined') module.exports = { SCENES, planScene, planAccess, initState, startOf, pgNo, frNo, stale, newest, cached, NCORE, NTHR, NTLB, NP, NF };

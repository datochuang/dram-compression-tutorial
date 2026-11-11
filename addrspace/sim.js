/* Shared by the 2D and the 3D address-space pages: example data helpers, the page-level simulator and the scenes.
   Expects `D` (the data from example_data.py) to be defined. Steps carry no drawing coordinates; `flow` says what data moves. */
const PAGE = D.page, CHUNK = D.chunk, I = D.init;
const NF = I.frames.length, NRO = I.n_ro, NCK = I.chunks.length, NRW = NCK - NRO;

const hx = (n, w) => '0x' + n.toString(16).toUpperCase().padStart(w, '0');
const SEG = {}; D.segments.forEach(s => SEG[s.id] = s);
const SYM = {}; const ONPAGE = D.pages.map(() => []);
D.symbols.forEach(s => {
  const seg = SEG[s.seg], a = s.addr - seg.base, b = a + s.size;
  s.slices = [];
  for (let i = Math.floor(a / PAGE); i * PAGE < b; i++) {
    const sl = { sym: s.id, p: seg.first + i, a: Math.max(a, i * PAGE) - i * PAGE, b: Math.min(b, (i + 1) * PAGE) - i * PAGE };
    s.slices.push(sl); ONPAGE[sl.p].push(sl);
  }
  SYM[s.id] = s;
});
const ckNo = c => hx(c < NRO ? I.ro_chunk0 + c : I.rw_chunk0 + c - NRO, 3);
const frNo = f => hx(I.frame0 + f, 3);
const pgNo = p => hx(D.pages[p].vpn, 3);
const nChunks = size => Math.ceil(size / CHUNK);
const clone = o => JSON.parse(JSON.stringify(o));

function initState() {
  const st = { pages: D.pages.map((pg, p) => ({ frame: null, chunks: I.cot[p] ? I.cot[p].slice() : null, csize: I.cot[p] ? pg.size : null, dirty: false, busy: null })),
    frames: I.frames.slice(), chunks: I.chunks.slice(), stack: I.stack.slice(), lru: I.lru.slice(), fill: null, cfill: [] };
  st.frames.forEach((o, f) => { if (typeof o === 'number') st.pages[o].frame = f; });
  return st;
}
const freeFrames = st => st.frames.filter(o => o === null).length;

/* ---------- one access, turned into steps ---------- */
function plan(st0, symId, off, kind) {
  const st = clone(st0), steps = [], sym = SYM[symId], seg = SEG[sym.seg];
  if (sym.kind === 'ro') kind = 'read';
  const segOff = sym.addr - seg.base + off, p = seg.first + Math.floor(segOff / PAGE), po = segOff % PAGE;
  const verb = kind === 'write' ? '寫入' : '讀取', kindK = sym.kind.toUpperCase();
  const C = t => '<code>' + t + '</code>';
  const names = q => ONPAGE[q].map(s => C(s.sym)).join('、');
  const cklist = cs => cs.map(c => C(ckNo(c))).join('、');
  const push = (who, text, o = {}) => steps.push(Object.assign({ who, text, st: clone(st), sym: symId, pin: { p, po, kind, phys: false, fault: false } }, o));

  const hot = sym.slices.filter(s => st.pages[s.p].frame !== null).length, cold = sym.slices.length - hot;
  push('user', `User SW ${verb} ${C(sym.id + ' + ' + hx(off, 4))}，logical address 是 ${C(hx(sym.addr + off, 8))}。${C(sym.id)} 是連續的 ${sym.size} B，跨 ${sym.slices.length} 個 page：目前 ${hot} 個在 hot region，${cold} 個在 cold region。這個 byte 落在 page ${C(pgNo(p))}。`, { hl: { cells: [p] } });

  if (st.pages[p].frame === null) {
    push('mmu', `CPU MMU 查 page ${C(pgNo(p))} 的 PTE，結果是 invalid。CPU MMU 不知道資料在哪裡，發出 page fault，由 kernel 接手。User SW 停在這個指令上等。`,
      { hl: { warn: p }, pin: { p, po, kind, phys: false, fault: true } });
    const fault = { p, po, kind, phys: false, fault: true };
    if (freeFrames(st) === 0) {
      const v = st.lru[0], vf = st.pages[v].frame, vk = D.pages[v].kind;
      push('kernel', `這個 page 被壓縮在 cold region，解壓縮需要一個空 frame，但 hot region 已經滿了。Kernel 挑最久沒被用到的 page ${C(pgNo(v))}，它在 frame ${C(frNo(vf))}，上面有 ${names(v)}。`,
        { hl: { cells: [v], frames: [vf] }, pin: fault });
      if (vk === 'ro') {
        st.pages[v].frame = null; st.frames[vf] = null; st.lru.shift();
        push('kernel', `Page ${C(pgNo(v))} 是 RO，內容從來不會變，壓縮副本一直留在 cold region 的 ${st.pages[v].chunks.length} 個 chunk 裡。所以不需要壓縮：kernel 把 PTE 改成 invalid，frame ${C(frNo(vf))} 就空出來了。`,
          { hl: { cells: [v], frames: [vf], chunks: st.pages[v].chunks }, pin: fault });
      } else {
        const size = st.pages[v].dirty ? D.pages[v].size_w : D.pages[v].size, n = nChunks(size);
        st.pages[v].frame = null; st.pages[v].busy = 'COMPRESSING'; st.lru.shift();
        push('kernel', `Page ${C(pgNo(v))} 是 RW，cold region 裡沒有它的副本，必須先壓縮。Kernel 先把 PTE 改成 invalid，從這一刻起任何 access 都會被擋下。`,
          { hl: { cells: [v], frames: [vf] }, pin: fault });
        push('hw', `LZ4 HW 從 frame ${C(frNo(vf))} 讀出 4096 B。`,
          { hl: { frames: [vf] }, pin: fault, lane: 'page ' + pgNo(v) + ': 4096 B', flow: { t: 'rd', k: vk, f: vf, p: v } });
        push('hw', `LZ4 HW 把 4096 B 壓縮成 ${size} B 的 stream。`,
          { pin: fault, lane: 'stream: ' + size + ' B', flow: { t: 'comp', k: vk, size, p: v } });
        const cs = []; for (let i = 0; i < n; i++) cs.push(st.stack.pop());
        st.cfill = cs.slice();
        push('hw', `Stream 切成 ${n} 段，每段最多 512 B，寫進 ${n} 個空 chunk：${cklist(cs)}。空 chunk 是別的 page 先前釋放的，所以位置不相鄰，順序也不是由小到大。`,
          { pin: fault, lane: 'stream: ' + size + ' B, cut into ' + n + ' chunks', flow: { t: 'store', k: vk, cs: cs.slice(), size, p: v } });
        st.cfill = []; cs.forEach(c => st.chunks[c] = v);
        st.pages[v].chunks = cs; st.pages[v].csize = size; st.pages[v].busy = null; st.pages[v].dirty = false; st.frames[vf] = null;
        push('both', `COT 記下 page ${C(pgNo(v))} 的 stream 長度和這 ${n} 個 chunk 的順序。Frame ${C(frNo(vf))} 釋放。這個 page 上的 ${names(v)} 現在在 cold region。`,
          { hl: { cells: [v], chunks: cs, frames: [vf] }, pin: fault });
      }
    }
    const f = st.frames.indexOf(null), pgst = st.pages[p], cs = pgst.chunks.slice(), size = pgst.csize, n = cs.length, k = sym.kind;
    push('kernel', `Kernel 拿 frame ${C(frNo(f))} 來放解壓縮後的 4096 B。`, { hl: { cells: [p], frames: [f] }, pin: fault });
    push('both', `COT 記錄 page ${C(pgNo(p))} 的 stream 有 ${size} B，放在 ${n} 個 chunk：${cklist(cs)}。這是 stream 的順序。`, { hl: { cells: [p], chunks: cs }, pin: fault });
    st.pages[p].busy = 'DECOMPRESSING';
    push('hw', `LZ4 HW 照 COT 的順序把 ${n} 個 chunk 讀出來，接成一條連續的 stream。分散在各處的碎片到這裡才重新排好。`,
      { hl: { chunks: cs }, pin: fault, lane: 'stream: ' + size + ' B from ' + n + ' chunks', flow: { t: 'gather', k, cs: cs.slice(), size, p } });
    push('hw', `LZ4 HW 解壓縮：${size} B 還原成 4096 B。`,
      { pin: fault, lane: 'page ' + pgNo(p) + ': 4096 B', flow: { t: 'decomp', k, size, p } });
    st.fill = f; st.frames[f] = p;
    push('hw', `LZ4 HW 把 4096 B 寫進 frame ${C(frNo(f))}。`,
      { hl: { frames: [f] }, pin: fault, lane: 'page ' + pgNo(p) + ': 4096 B', flow: { t: 'wr', k, f, p } });
    st.fill = null;
    if (k === 'rw') {
      cs.forEach(c => { st.chunks[c] = null; st.stack.push(c); });
      st.pages[p].chunks = null; st.pages[p].csize = null;
      push('both', `RW page 回到 hot region 後，壓縮副本就作廢，因為 frame 裡的內容隨時會被改寫。${n} 個 chunk 釋放，COT 的這一筆清空。`, { hl: { cells: [p], chunks: cs }, pin: fault });
    } else {
      push('both', `RO page 的內容不會變，壓縮副本留在原地。之後這個 page 要讓出 frame 時，不需要再壓縮一次。`, { hl: { cells: [p], chunks: cs }, pin: fault });
    }
    st.pages[p].frame = f; st.pages[p].busy = null;
    push('kernel', `Kernel 把 PTE 改成 valid，指向 frame ${C(frNo(f))}，然後返回 user SW。`, { hl: { cells: [p], frames: [f] }, pin: fault });
    st.lru = st.lru.filter(q => q !== p); st.lru.push(p);
    if (kind === 'write') st.pages[p].dirty = true;
    const others = ONPAGE[p].filter(s => s.sym !== symId).map(s => C(s.sym));
    push('user', `Kernel 返回後，CPU 重新執行同一個指令。這次 CPU MMU 直接轉換，${verb}落在 frame ${C(frNo(f))}。Access 最後還是發生在 hot region。User SW 不知道發生過 fault，只感覺到這次比較久。` +
      (others.length ? `同一個 page 上的 ${others.join('、')} 也跟著回到 hot region。` : ''), { hl: { frames: [f] }, pin: { p, po, kind, phys: true, fault: false } });
  } else {
    const f = st.pages[p].frame;
    push('mmu', `CPU MMU 查 page ${C(pgNo(p))} 的 PTE，是 valid，指向 frame ${C(frNo(f))}。轉換由 CPU MMU 完成，kernel 和 LZ4 HW 都沒有參與。`, { hl: { cells: [p], frames: [f] } });
    st.lru = st.lru.filter(q => q !== p); st.lru.push(p);
    if (kind === 'write') st.pages[p].dirty = true;
    const fs = sym.slices.filter(s => st.pages[s.p].frame !== null).map(s => st.pages[s.p].frame);
    const scattered = fs.length > 1 && fs.some((x, i) => i && x !== fs[i - 1] + 1);
    push('user', `${verb}落在 frame ${C(frNo(f))} 裡。這次 access 只碰到 hot region${kind === 'write' ? '，寫入只改 frame 裡的 byte' : ''}。` +
      (scattered ? `注意 ${C(sym.id)} 在 logical 是連續的，在 hot region 的部分卻依序放在 frame ${fs.map(x => C(frNo(x))).join('、')}，並不相鄰。` : ''),
      { hl: { frames: [f] }, pin: { p, po, kind, phys: true, fault: false } });
  }
  return { steps, final: st };
}

const SCENES = [
  { t: '已經在 hot region', sym: 'rx_queue', off: 0x0A40, kind: 'read' },
  { t: '在 cold region', sym: 'log_ring', off: 0x1200, kind: 'read' },
  { t: '同一個 symbol，一半 hot 一半 cold', sym: 'log_ring', off: 0x1C80, kind: 'write' },
  { t: 'RO 的 symbol', sym: 'parse_cfg', off: 0x0800, kind: 'read' },
  { t: 'Hot region 滿了，RO page 讓位', sym: 'ui_state', off: 0x0900, kind: 'read' },
  { t: 'Hot region 滿了，RW page 讓位', sym: 'fir_taps', off: 0x0400, kind: 'read' },
];
const WHO = { user: 'USER SW', mmu: 'CPU MMU', kernel: 'KERNEL', hw: 'LZ4 HW', both: 'KERNEL / LZ4 HW' };

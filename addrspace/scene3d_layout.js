/* ---------- the address-space view's own layout: rows of its board, places on its floor, what its tables say ---------- */
const CWU = U * CHUNK / PAGE;
const ROW = { title: 1.25, pin: 3.55, sym0: 4, sym1: 8.4, pg: 9.65, pteH: 11.15, pte0: 11.55, pte1: 16.15, stH: 17.45, st0: 17.8, st1: 20.4, cotH: 21.7, cot0: 22.05, cot1: 26.65 };
const pageU = p => p < SEG.rw.first ? 3 + p * U : 3 + SEG.rw.first * U + 6 + (p - SEG.rw.first) * U;
const HOTZ = 0, SLABD = 8, COLDZ = 20.6, HWX = 16, HWZ0 = 11.4, HWZ1 = 17.4, HWH = 1.0;
const frameX0 = f => -NF * U / 2 + f * U;
const chunkX0 = c => c < NRO ? -31.5 + c * CWU : -8.5 + (c - NRO) * CWU;

// What the three tables say about page p in state st.
function tabOf(st, p) {
  const ps = st.pages[p];
  return {
    pte: ps.frame !== null ? frNo(ps.frame) : null,
    state: ps.busy ? ps.busy.toLowerCase() : (ps.frame !== null ? 'present' : 'compressed'),
    cot: ps.chunks ? { len: ps.csize, n: ps.chunks.length, cs: ps.chunks } : null,
  };
}
const sameCot = (a, b) => (!a && !b) || (a && b && a.len === b.len && a.cs.join() === b.cs.join());

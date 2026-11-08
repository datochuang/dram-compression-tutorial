// Match length distribution on 4KB pages, used by the table in section 4 ("4 bytes 只是起點").
// Usage: node matchlen.js   (expects lz4core.js beside it; reads /bin/ls, /bin/zsh, /usr/share/dict/words)
const L = require('./lz4core.js'), fs = require('fs');
function pages(buf) { const out = []; for (let o = 0; o + 4096 <= buf.length; o += 4096) out.push(new Uint8Array(buf.subarray(o, o + 4096))); return out; }
const S = L.samples(4096);
const sets = { text: [S.text], words: pages(fs.readFileSync('/usr/share/dict/words')), pointers: [S.pointers],
  zsh: pages(fs.readFileSync('/bin/zsh')), ls: pages(fs.readFileSync('/bin/ls')), zero: [S.zero] };
for (const [k, ps] of Object.entries(sets)) {
  const ms = [];
  for (const p of ps) for (const q of L.compress(p, false).seqs) if (q.matchLen) ms.push(q.matchLen);
  ms.sort((a, b) => a - b);
  const tot = ms.reduce((a, b) => a + b, 0), long = ms.filter(x => x >= 16).reduce((a, b) => a + b, 0);
  console.log(k.padEnd(9), 'matches', ms.length, 'mean', (tot / ms.length).toFixed(1), 'median', ms[ms.length >> 1], 'max', ms[ms.length - 1], 'long share', (long / tot * 100).toFixed(1) + '%');
}

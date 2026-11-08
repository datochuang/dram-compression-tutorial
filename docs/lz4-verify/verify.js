// Cross-checks lz4core.js against the real lz4 CLI, both directions, and prints values used in the page.
const fs = require('fs'), os = require('os'), path = require('path'), cp = require('child_process');
const L = require('./lz4core.js');
const dir = fs.mkdtempSync(path.join(process.env.TMPDIR || '/tmp', 'lz4v-'));
const CLI = ['-1', '-B4', '-BI', '--no-frame-crc', '--no-content-size', '-f', '-q'];

function cliCompress(buf) {
  const a = path.join(dir, 'in'), b = path.join(dir, 'in.lz4');
  fs.writeFileSync(a, buf);
  cp.execFileSync('lz4', [...CLI, a, b]);
  const f = fs.readFileSync(b);
  const hdr = f.subarray(0, 7);
  const sz = f.readUInt32LE(7);
  const raw = (sz >>> 31) === 1, len = sz & 0x7fffffff;
  return { hdr, raw, block: f.subarray(11, 11 + len), total: f.length };
}
function cliDecompress(hdr, block) {
  const a = path.join(dir, 'x.lz4'), b = path.join(dir, 'x.out');
  const s = Buffer.alloc(4); s.writeUInt32LE(block.length);
  fs.writeFileSync(a, Buffer.concat([hdr, s, Buffer.from(block), Buffer.alloc(4)]));
  cp.execFileSync('lz4', ['-d', '-f', '-q', a, b]);
  return fs.readFileSync(b);
}
const eq = (x, y) => x.length === y.length && Buffer.compare(Buffer.from(x), Buffer.from(y)) === 0;

const cases = [];
const s4k = L.samples(4096);
for (const k of Object.keys(s4k)) cases.push(['4K ' + k, s4k[k]]);
const STEP = 'abcabcabcabcabc-the-cat-sat-on-the-mat-the-cat-ran-end-of-page!';
cases.push(['stepper', Buffer.from(STEP)]);
const SHORT = 'say:hello-bob-hello,again!';
const SHORT_HEX = 'e17361793a68656c6c6f2d626f622d0a00702c616761696e21';
cases.push(['section 2 example', Buffer.from(SHORT)]);
if (Buffer.from(L.compress(Buffer.from(SHORT), false).out).toString('hex') !== SHORT_HEX) throw new Error('section 2 example changed');
if (L.compress(Buffer.from('say:hello-bob-hello'), false).out.length !== 21) throw new Error('19-byte claim in Block end section changed');
const REPEAT = 'go:' + 'ab'.repeat(10) + ',done!';
cases.push(['section 1 repeat example', Buffer.from(REPEAT)]);
const THIRD = 'a:owl,blue,owl,red,blue,blue,end-now';
cases.push(['section 1 third example', Buffer.from(THIRD)]);
if (Buffer.from(L.compress(Buffer.from(THIRD), false).out).toString('hex') !== 'b0613a6f776c2c626c75652c0900327265640d0001120070656e642d6e6f77') throw new Error('section 1 third example changed');
if (Buffer.from(L.compress(Buffer.from(REPEAT), false).out).toString('hex') !== '5e676f3a61620200602c646f6e6521') throw new Error('section 1 repeat example changed');
if (Buffer.from(L.compress(new Uint8Array(4096), false).out).toString('hex') !== '1f000100fffffffffffffffffffffffffffffff6500000000000') throw new Error('all-zero page claim changed');
for (const n of [13, 14, 16, 20, 31, 64, 100, 255, 300, 1000, 2047, 60000]) {
  const sm = L.samples(n);
  for (const k of Object.keys(sm)) cases.push([`${n} ${k}`, sm[k]]);
}
// Random mixes that exercise runs, long matches and offset overlap.
let seed = 99;
const rnd = (m) => { seed = (seed * 1664525 + 1013904223) >>> 0; return (seed >>> 8) % m; };
for (let t = 0; t < 400; t++) {
  const a = [];
  const target = 13 + rnd(5000);
  while (a.length < target) {
    const mode = rnd(4);
    if (mode === 0) { const c = rnd(256), l = 1 + rnd(400); for (let i = 0; i < l; i++) a.push(c); }
    else if (mode === 1) { const l = 1 + rnd(60); for (let i = 0; i < l; i++) a.push(rnd(256)); }
    else if (mode === 2 && a.length > 8) { const off = 1 + rnd(a.length), l = 4 + rnd(300), st = a.length - off; for (let i = 0; i < l; i++) a.push(a[st + i]); }
    else { const p = 1 + rnd(5), l = 8 + rnd(120); for (let i = 0; i < l; i++) a.push((i % p) * 17); }
  }
  cases.push(['mix' + t, Uint8Array.from(a.slice(0, target))]);
}

// Walks a block using only the size formulas printed in section 2, without copying any data.
function seqSizes(block) {
  const out = []; let p = 0;
  while (p < block.length) {
    const start = p, token = block[p++];
    let lit = token >> 4, b;
    if (lit === 15) do { b = block[p++]; lit += b; } while (b === 255);
    const litExt = p - start - 1;
    p += lit;
    if (p === block.length) { out.push({ used: p - start, restored: lit, last: true }); break; }
    p += 2;
    let ml = (token & 15) + 4;
    const mlStart = p;
    if ((token & 15) === 15) do { b = block[p++]; ml += b; } while (b === 255);
    if ((lit + ml) - (p - start) !== ml - 3 - litExt - (p - mlStart)) throw new Error('savings formula failed');
    out.push({ used: p - start, restored: lit + ml, last: false });
  }
  return out;
}
function checkSizes(name, block, inputLen) {
  const s = seqSizes(block);
  const restored = s.reduce((a, x) => a + x.restored, 0), used = s.reduce((a, x) => a + x.used, 0);
  if (restored !== inputLen || used !== block.length) throw new Error(`size formula failed ${name}: ${restored}/${inputLen} ${used}/${block.length}`);
  sizeChecks++;
  return s;
}
let sizeChecks = 0;

let identical = 0, rawCli = 0, jsDecCli = 0, cliDecJs = 0, jsRound = 0, diff = [];
let hdrGlobal;
for (const [name, data] of cases) {
  const js = L.compress(data, false);
  checkSizes('js ' + name, js.out, data.length);
  if (!eq(L.decompress(js.out).out, data)) throw new Error('JS round trip failed ' + name);
  jsRound++;
  const c = cliCompress(data);
  hdrGlobal = hdrGlobal || c.hdr;
  if (c.raw) { rawCli++; }
  else {
    if (!eq(L.decompress(c.block).out, data)) throw new Error('JS failed to decode CLI block ' + name);
    jsDecCli++;
    checkSizes('cli ' + name, c.block, data.length);
    if (eq(js.out, c.block)) identical++; else diff.push(name);
  }
  if (!eq(cliDecompress(c.hdr, js.out), data)) throw new Error('CLI failed to decode JS block ' + name);
  cliDecJs++;
}
console.log(cp.execFileSync('lz4', ['--version']).toString().trim());
console.log({ cases: cases.length, jsRound, cliDecJs, jsDecCli, rawCli, identical, notIdentical: diff.length, sampleDiff: diff.slice(0, 8), sizeChecks });

// The size table in section 2, including the hand-made sequence whose match length uses an extension byte.
const shortSizes = seqSizes(L.compress(Buffer.from(SHORT), false).out);
const stepSizes = seqSizes(L.compress(Buffer.from(STEP), false).out);
const handMade = Buffer.concat([Buffer.from([0x3F]), Buffer.from('abc'), Buffer.from([3, 0, 4, 0x50]), Buffer.from(',stop')]);
const handSizes = seqSizes(handMade);
const handOut = Buffer.from(L.decompress(handMade).out).toString();
const hdrForHand = cliCompress(Buffer.from(SHORT)).hdr;
const handCli = cliDecompress(hdrForHand, handMade).toString();
console.log('short', JSON.stringify(shortSizes));
console.log('step', JSON.stringify(stepSizes), 'second seq hex', Buffer.from(L.compress(Buffer.from(STEP), false).out).subarray(6, 8).toString('hex'));
console.log('hand-made', JSON.stringify(handSizes), JSON.stringify(handOut), handOut.length, 'cli same:', handCli === handOut);

// Rejection of corrupted blocks.
const bad = [
  ['offset 0', [0x10, 0x41, 0x00, 0x00, 0x00]],
  ['offset too far', [0x10, 0x41, 0x05, 0x00, 0x00]],
  ['literals overrun', [0x50, 0x41]],
];
for (const [n, b] of bad) { try { L.decompress(Uint8Array.from(b)); console.log('NOT REJECTED', n); } catch (e) { console.log('rejected', n, '->', e.message); } }
try { L.decompress(L.compress(s4k.zero).out, 100); console.log('NOT REJECTED overflow'); } catch (e) { console.log('rejected overflow ->', e.message); }

// Measured table for the page.
for (const k of Object.keys(s4k)) {
  const js = L.compress(s4k[k], false), c = cliCompress(s4k[k]);
  console.log(k, 'js', js.out.length, 'cli', c.raw ? 'raw ' + c.block.length : c.block.length, 'seqs', js.seqs.length, 'chunks', Math.ceil(js.out.length / 512));
}
console.log('bound(4096)=', L.bound(4096));

// Stepper example.
const st = L.compress(Buffer.from(STEP), true);
console.log('stepper len', STEP.length, '->', st.out.length, 'hex', Buffer.from(st.out).toString('hex'));
console.log(JSON.stringify(st.seqs.map(s => ({ lit: s.litLen, off: s.offset, ml: s.matchLen, last: s.last }))));
console.log('probe counts', st.events.filter(e => e.t === 'probe').length, 'hits', st.events.filter(e => e.t === 'probe' && e.hit).length, 'events', st.events.length);
for (const [n, m] of [[48, false], [280, false], [15, false], [19, true], [18, true], [4, true]]) console.log(n, m ? 'match' : 'lit', L.encodeLengthExample(n, m));

// Address examples.
const va = 0x00007F1234567ABCn;
const parts = { L0: (va >> 39n) & 511n, L1: (va >> 30n) & 511n, L2: (va >> 21n) & 511n, L3: (va >> 12n) & 511n, off: va & 4095n };
console.log(Object.fromEntries(Object.entries(parts).map(([k, v]) => [k, Number(v) + ' / 0x' + v.toString(16)])));
const poolBase = 0xC0000000, chunk = 0x1F002, byteOff = 1100;
const idx = byteOff >> 9, within = byteOff & 511, pa = poolBase + chunk * 512 + within;
console.log({ idx, within, pa: '0x' + pa.toString(16) });
fs.rmSync(dir, { recursive: true, force: true });

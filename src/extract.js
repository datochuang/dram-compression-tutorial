// Extracts Part C (the whole SoC, Sections 9 to 15) and the appendix from the built English edition into a
// page of its own:
//   docs/lz4-soc-partc-en.html (artifact version, no <html> shell) and docs/en/soc/index.html (GitHub Pages)
// Nothing is rewritten. The text, figures and demos of Part C are copied as they are; only the header, the
// section lists and the demo index are trimmed, and the page script is made tolerant of the elements that
// are no longer on the page (the lookups of Parts A and B return a detached element instead of null).
// Run by build.js after the English edition, or on its own: cd src && node extract.js
const fs = require('fs'), vm = require('vm'), path = require('path');
const SRC = path.join(__dirname, '../docs/lz4-soc-explainer-en.html');
const ART = path.join(__dirname, '../docs/lz4-soc-partc-en.html');
const PAGES = path.join(__dirname, '../docs/en/soc/index.html');
const FULL = 'https://datochuang.github.io/dram-compression-tutorial/en/';
const ZH = 'https://datochuang.github.io/dram-compression-tutorial/';
const CJK = /[一-鿿　-〿＀-￯]/;

// Every edit must match exactly once (or `times` times), so a change to the source page fails loudly here
// instead of silently leaving a stale section list or a broken script behind.
function must(html, from, to, what, times) {
  const g = typeof from === 'string' ? null : new RegExp(from.source, from.flags.includes('g') ? from.flags : from.flags + 'g');
  const n = g ? (html.match(g) || []).length : html.split(from).length - 1;
  if (n !== (times || 1)) throw new Error('extract: expected ' + (times || 1) + ' match(es) for ' + what + ', found ' + n);
  return html.replace(g || from, to);
}

function extract(html) {
  // 1. Body: everything from the Part A label up to the Part C label goes.
  const a = html.indexOf('<div class="part">A. The LZ4 algorithm</div>'), c = html.indexOf('<div class="part">C. The whole SoC</div>');
  if (a < 0 || c < a) throw new Error('extract: part labels not found');
  html = html.slice(0, a) + html.slice(c);
  // 2. Section rail: the Part A and Part B groups.
  html = must(html, /  <p>A\. The LZ4 algorithm<\/p>\n.*\n  <p>B\. The hardware accelerator<\/p>\n.*\n/, '', 'rail groups A and B');
  // 3. Mobile section list: the links to Sections 1 to 8.
  html = must(html, /<a href="#s[1-8]">[^<]*<\/a>/g, '', 'mobile links to Sections 1 to 8', 8);
  // 4. Demo index: the two Part A demos and the two Part A calculators.
  html = must(html, /    <li><a href="#decTool">.*\n    <li><a href="#encTool">.*\n/, '', 'Part A demos in the index');
  html = must(html, '<a href="#lenTool">length encoding</a> (Section 2), <a href="#labTool">the Lab</a> (Section 5, type your own text), ', '', 'Part A calculators in the index');
  // 5. Header: title, language line and lede; the byte tape under the title belongs to Part A.
  html = must(html, '<title>LZ4 on a Simple SoC</title>', '<title>LZ4 on a Simple SoC: The whole SoC</title>', 'title');
  html = must(html, '<p class="lang"><a href="' + ZH + '">中文版 (Traditional Chinese)</a></p>',
    '<p class="lang"><a href="' + FULL + '">Full explainer (Parts A to C)</a> · <a href="' + ZH + '">中文版 (Traditional Chinese)</a></p>', 'language line');
  html = must(html, /  <p class="lede">.*\n/,
    '  <p class="lede">Part C of the full explainer as a page of its own: the system architecture, the two MMUs, the states of a page, the end-to-end flows from boot to run time, latency and capacity, HRT and QoS, and the error cases. Part A, the LZ4 algorithm (Sections 1 to 6), and Part B, the accelerator (Sections 7 and 8), are on the <a href="' + FULL + '">full page</a>; the section numbers are kept here so that cross-references still match.</p>\n', 'lede');
  html = must(html, /  <div id="heroTape".*\n  <div class="legend" id="roleLegend"><\/div>\n  <p class="count" id="heroCap"><\/p>\n/, '', 'hero tape');
  // 6. Script: the elements of Parts A and B are gone, so their lookups return a detached element instead of null.
  html = must(html, "function $(id) { return document.getElementById(id); }", "function $(id) { return document.getElementById(id) || document.createElement('div'); }", '$ helper');
  html = must(html, "var f = document.getElementById(g);", "var f = $(g);", 'cells lookup');
  html = must(html, "var g = document.getElementById('f4eq');", "var g = $('f4eq');", 'f4eq lookup');
  html = must(html, "var tb = document.querySelector('#seqTable tbody'),", "var tb = document.querySelector('#seqTable tbody') || document.createElement('tbody'),", 'seqTable lookup');
  return html;
}

// The same DOM stub as build.js, except that an unknown id returns null as a browser would, so the page
// script is exercised exactly as it will run on the trimmed page.
function check(html) {
  const tag = '[soc]';
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map(m => m[1]);
  const dup = ids.filter((x, i) => ids.indexOf(x) !== i);
  const dangling = [...new Set([...html.matchAll(/href="#([^"]+)"/g)].map(m => m[1]).filter(i => !ids.includes(i)))];
  console.log(tag, 'ids', ids.length, 'duplicates', dup, 'dangling anchors', dangling);
  if (dup.length || dangling.length) throw new Error('extract: duplicate ids or dangling anchors');
  for (const k of ['s9', 's10', 's11', 's12', 's13', 's14', 's15', 's16', 's17', 'btTool', 'evTool', 'fiTool', 'flowTool', 'lifeTool', 'xlTool', 'latTool', 'capTool']) if (!ids.includes(k)) throw new Error('extract: missing ' + k);
  for (const k of ['s1', 's8', 'decTool', 'encTool', 'labTool', 'lenTool', 'heroTape']) if (ids.includes(k)) throw new Error('extract: still present ' + k);

  function el(id) {
    const e = { id, children: [], style: {}, value: '', innerHTML: '', textContent: '', attrs: {}, disabled: false,
      classList: { toggle() {}, add() {}, remove() {} },
      setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
      appendChild(c) { this.children.push(c); return c; }, addEventListener() {},
      querySelector() { return el('q'); }, querySelectorAll() { return []; } };
    return e;
  }
  const reg = {}; let detached = 0;
  const defaults = { latKernel: '3', latRate: '4', latDram: '100', latFaults: '5000', capDram: '512', capPin: '56', capHrt: '36', capRo: '248', capRw: '332', capHotRo: '30', capHotRw: '80', capRoR: '55', capRwR: '45', xlOff: '1100' };
  const document = {
    getElementById(i) { if (!ids.includes(i)) return null; if (!reg[i]) { reg[i] = el(i); if (defaults[i]) reg[i].value = defaults[i]; } return reg[i]; },
    querySelector(sel) { const m = /^#(\S+)/.exec(sel); return m && !ids.includes(m[1]) ? null : el('q'); },
    querySelectorAll() { return []; }, createElementNS() { return el('n'); }, createElement() { detached++; return el('b'); }
  };
  const ctx = vm.createContext({ document, TextEncoder, TextDecoder, Uint8Array, Uint16Array, JSON, Math, Array, Object, String, console });
  for (const s of scripts) vm.runInContext(s, ctx);
  console.log(tag, 'detached elements created for removed parts:', detached);
  console.log(tag, 'xl:', reg.xlRes.textContent);
  console.log(tag, 'lat:', reg.latRes.innerHTML.replace(/<[^>]+>/g, ' | ').slice(0, 200));
  console.log(tag, 'cap:', reg.capRes.innerHTML.replace(/<[^>]+>/g, ' | ').slice(0, 200));
  const strip = h => h.replace(/<br>/g, ' / ').replace(/<[^>]+>/g, '');
  let c = 0;
  for (const p of ['bt', 'ev', 'fi']) { while (!reg[p + 'Next'].disabled) { reg[p + 'Next'].onclick(); c++; } console.log(tag, p, reg[p + 'Count'].textContent, strip(reg[p + 'Exp'].innerHTML).slice(0, 80)); }
  for (const f of ['fA', 'fB', 'fC']) { reg[f].onclick(); while (!reg.flowNext.disabled) { reg.flowNext.onclick(); c++; } console.log(tag, f, strip(reg.flowExp.innerHTML).slice(0, 90)); }
  while (!reg.lifeNext.disabled) { reg.lifeNext.onclick(); c++; }
  console.log(tag, 'life', reg.lifeCount.textContent, strip(reg.lifeExp.innerHTML).slice(0, 90));
  console.log(tag, 'walked', c, 'steps; size', Math.round(html.length / 1024), 'KB');
  const left = html.split('\n').map((l, i) => CJK.test(l) ? (i + 1) + ': ' + l.trim().slice(0, 100) : null).filter(Boolean);
  console.log(tag, 'lines with CJK:', left.length); for (const l of left.slice(0, 5)) console.log('   ', l);
}

const html = extract(fs.readFileSync(SRC, 'utf8'));
fs.writeFileSync(ART, html);
const cut = html.indexOf('</style>') + '</style>'.length;
if (cut < 8) throw new Error('style block missing');
fs.mkdirSync(path.dirname(PAGES), { recursive: true });
fs.writeFileSync(PAGES, '<!doctype html>\n<html lang="en">\n<head>\n<meta name="viewport" content="width=device-width, initial-scale=1">\n' + html.slice(0, cut) + '\n</head>\n<body>' + html.slice(cut) + '\n</body>\n</html>\n');
check(html);

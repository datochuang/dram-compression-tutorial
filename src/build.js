// Builds both editions of the page from page.html:
//   zh-Hant: docs/lz4-soc-explainer.html (artifact version, no <html> shell) and docs/index.html (GitHub Pages)
//   en:      docs/lz4-soc-explainer-en.html and docs/en/index.html
// The English edition is page.html with every line that has an entry in en.json replaced by that entry
// (key = the exact source line). Lines with Chinese text and no entry are reported as MISSING and kept as-is.
// Each edition gets the tested codec inlined, a hatch pattern per figure, and its scripts are run in a minimal
// DOM stub that walks every stepper to catch runtime errors.
const fs = require('fs'), vm = require('vm');
const core = fs.readFileSync('../docs/lz4-verify/lz4core.js', 'utf8').replace("if (typeof module !== 'undefined') module.exports = LZ4Core;", '');
const zh = fs.readFileSync('page.html', 'utf8');
if (!zh.includes('/*__CORE__*/')) throw new Error('placeholder missing');
const CJK = /[一-鿿　-〿＀-￯]/;

function translate(src) {
  if (!fs.existsSync('en.json')) { console.log('en.json missing, English edition skipped'); return null; }
  const en = JSON.parse(fs.readFileSync('en.json', 'utf8'));
  const missing = [], used = new Set();
  const out = src.split('\n').map(l => {
    if (Object.prototype.hasOwnProperty.call(en, l)) { used.add(l); return en[l]; }
    if (CJK.test(l)) missing.push(l);
    return l;
  }).join('\n');
  const stale = Object.keys(en).filter(k => !used.has(k));
  const left = out.split('\n').filter(l => CJK.test(l)).length;
  console.log('en: translated', used.size, 'lines; MISSING', missing.length, '; stale entries', stale.length, '; lines with CJK left', left);
  for (const m of missing.slice(0, 30)) console.log('  MISSING:', m.trim().slice(0, 140));
  for (const s of stale.slice(0, 10)) console.log('  STALE:', s.trim().slice(0, 140));
  return out;
}

function build(html, lang, artifactPath, pagesPath) {
  html = html.replace('/*__CORE__*/', () => core);
  // Give every figure that marks compressed data its own hatch pattern (a pattern defined in another SVG is not reliable).
  let zn = 0;
  html = html.replace(/<svg\b([^>]*)>([\s\S]*?)<\/svg>/g, (m, attrs, body) => {
    if (!body.includes('class="zc"')) return m;
    const id = 'hz' + (++zn);
    body = body.replace(/class="zc"/g, 'class="zc" fill="url(#' + id + ')"');
    return '<svg' + attrs + '><defs><pattern id="' + id + '" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line class="hzl" x1="0" y1="0" x2="0" y2="7"/></pattern></defs>' + body + '</svg>';
  });
  console.log('[' + lang + '] hatched figures', zn);
  fs.writeFileSync(artifactPath, html);
  // GitHub Pages serves the file as-is, so the Pages copy is the same page wrapped in a full document (standards mode, viewport meta).
  const cut = html.indexOf('</style>') + '</style>'.length;
  if (cut < 8) throw new Error('style block missing');
  const page = '<!doctype html>\n<html lang="' + lang + '">\n<head>\n<meta name="viewport" content="width=device-width, initial-scale=1">\n' + html.slice(0, cut) + '\n</head>\n<body>' + html.slice(cut) + '\n</body>\n</html>\n';
  fs.mkdirSync(require('path').dirname(pagesPath), { recursive: true });
  fs.writeFileSync(pagesPath, page);
  check(html, lang);
}

function check(html, lang) {
  const tag = '[' + lang + ']';
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map(m => m[1]);
  const dup = ids.filter((x, i) => ids.indexOf(x) !== i);
  console.log(tag, 'ids', ids.length, 'duplicates', dup);
  const refs = [...scripts[1].matchAll(/\$\('([^']+)'\)/g)].map(m => m[1]);
  console.log(tag, 'missing ids referenced by script:', [...new Set(refs)].filter(r => !ids.includes(r)));
  for (const k of ['fA', 'fB', 'flowSvg']) if (!ids.includes(k)) console.log(tag, 'missing', k);

  function el(id) {
    const e = { id, children: [], style: {}, value: '', innerHTML: '', textContent: '', attrs: {}, disabled: false,
      classList: { toggle() {}, add() {}, remove() {} },
      setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
      appendChild(c) { this.children.push(c); return c; }, addEventListener() {},
      querySelector() { return el('q'); }, querySelectorAll() { return []; } };
    return e;
  }
  const reg = {};
  const defaults = { lenN: '280', lenK: 'lit', latKernel: '3', latRate: '4', latDram: '100', latFaults: '5000', capDram: '512', capPin: '56', capHrt: '36', capRo: '248', capRw: '332', capHotRo: '30', capHotRw: '80', capRoR: '55', capRwR: '45', xlOff: '1100' };
  const document = {
    getElementById(i) { if (!reg[i]) { if (!ids.includes(i)) throw new Error('no element ' + i); reg[i] = el(i); if (defaults[i]) reg[i].value = defaults[i]; } return reg[i]; },
    querySelector() { return el('q'); }, querySelectorAll() { return []; }, createElementNS() { return el('n'); }, createElement() { return el('b'); }
  };
  const ctx = vm.createContext({ document, TextEncoder, TextDecoder, Uint8Array, Uint16Array, JSON, Math, Array, Object, String, console });
  for (const s of scripts) vm.runInContext(s, ctx);
  console.log(tag, 'hero:', reg.heroCap.textContent);
  console.log(tag, 'len:', reg.lenOut.textContent);
  console.log(tag, 'xl:', reg.xlRes.textContent);
  console.log(tag, 'lab:', reg.labRes.innerHTML.replace(/<[^>]+>/g, ' | ').slice(0, 220));
  console.log(tag, 'lat:', reg.latRes.innerHTML.replace(/<[^>]+>/g, ' | ').slice(0, 260));
  console.log(tag, 'cap:', reg.capRes.innerHTML.replace(/<[^>]+>/g, ' | ').slice(0, 300));
  console.log(tag, 'dec:', reg.decExp.innerHTML, reg.decCount.textContent);
  console.log(tag, 'enc:', reg.encExp.innerHTML, reg.encCount.textContent);
  // Walk every stepper state to surface runtime errors.
  let c = 0;
  while (!reg.decNext.disabled) { reg.decNext.onclick(); c++; }
  console.log(tag, 'dec last:', reg.decExp.innerHTML, reg.decCount.textContent);
  { const strip = h => h.replace(/<[^>]+>/g, ''); const ed = () => { if (process.env.ENC) console.log('E', reg.encCount.textContent, strip(reg.encExp.innerHTML), '\n   vars:', strip(reg.encVars.innerHTML.replace(/<\/span>/g, ' | ')), '\n   out:', strip(reg.encOut.innerHTML.replace(/<\/span>/g, ' ')), '\n   tab:', strip(reg.encTable.innerHTML.replace(/<\/span>/g, ' | ')).slice(0, 160)); }; ed(); while (!reg.encNext.disabled) { reg.encNext.onclick(); c++; ed(); } }
  console.log(tag, 'enc last:', reg.encExp.innerHTML, reg.encCount.textContent);
  for (const p of ['bt', 'ev', 'fi']) { const strip = h => h.replace(/<br>/g, ' / ').replace(/<[^>]+>/g, ''); const d = () => { if (process.env.STEP) console.log(p, reg[p + 'Count'].textContent, strip(reg[p + 'Exp'].innerHTML), '\n   ', strip(reg[p + 'Body'].innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | ')).slice(0, 4000)); }; d(); while (!reg[p + 'Next'].disabled) { reg[p + 'Next'].onclick(); c++; d(); } console.log(tag, p, reg[p + 'Count'].textContent, strip(reg[p + 'Exp'].innerHTML).slice(0, 80)); }
  for (const f of ['fA', 'fB', 'fC']) { reg[f].onclick(); while (!reg.flowNext.disabled) { reg.flowNext.onclick(); c++; } console.log(tag, f, reg.flowExp.innerHTML.slice(0, 90)); }
  { const strip = h => h.replace(/<[^>]+>/g, '');
    const dump = () => { console.log('L', reg.lifeCount.textContent, strip(reg.lifeExp.innerHTML)); console.log('   sum:', reg.lifeSum.textContent); console.log('   pages:', strip(reg.lifePages.innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | '))); console.log('   cot:', strip(reg.lifeCot.innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | '))); console.log('   pool:', strip(reg.lifePool.innerHTML.replace(/<\/div>/g, ' '))); console.log('   stack:', strip(reg.lifeStack.innerHTML.replace(/<\/span>/g, ' ')), reg.lifeStack.className); console.log('   frames:', strip(reg.lifeFrames.innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | '))); console.log('   misc:', strip(reg.lifeMisc.innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | '))); };
    console.log(tag, 'sizes:', strip(reg.lifeSizes.innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | ')));
    dump(); while (!reg.lifeNext.disabled) { reg.lifeNext.onclick(); c++; if (process.env.LIFE) dump(); } if (!process.env.LIFE) dump(); }
  console.log(tag, 'walked', c, 'steps; size', Math.round(html.length / 1024), 'KB');
  if (lang !== 'zh-Hant') {
    // Nothing the reader sees in the English edition may still be Chinese: check the visible text after the walkers ran.
    const left = html.split('\n').map((l, i) => CJK.test(l) ? (i + 1) + ': ' + l.trim().slice(0, 100) : null).filter(Boolean);
    console.log(tag, 'lines with CJK:', left.length); for (const l of left.slice(0, 20)) console.log('   ', l);
  }
}

build(zh, 'zh-Hant', '../docs/lz4-soc-explainer.html', '../docs/index.html');
const en = translate(zh);
if (en) build(en, 'en', '../docs/lz4-soc-explainer-en.html', '../docs/en/index.html');

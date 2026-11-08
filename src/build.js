// Inlines the tested codec into the page, then runs the page's scripts in a minimal DOM stub to catch runtime errors.
const fs = require('fs'), vm = require('vm');
const core = fs.readFileSync('../docs/lz4-verify/lz4core.js', 'utf8').replace("if (typeof module !== 'undefined') module.exports = LZ4Core;", '');
let html = fs.readFileSync('page.html', 'utf8');
if (!html.includes('/*__CORE__*/')) throw new Error('placeholder missing');
html = html.replace('/*__CORE__*/', () => core);
// Give every figure that marks compressed data its own hatch pattern (a pattern defined in another SVG is not reliable).
let zn = 0;
html = html.replace(/<svg\b([^>]*)>([\s\S]*?)<\/svg>/g, (m, attrs, body) => {
  if (!body.includes('class="zc"')) return m;
  const id = 'hz' + (++zn);
  body = body.replace(/class="zc"/g, 'class="zc" fill="url(#' + id + ')"');
  return '<svg' + attrs + '><defs><pattern id="' + id + '" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line class="hzl" x1="0" y1="0" x2="0" y2="7"/></pattern></defs>' + body + '</svg>';
});
console.log('hatched figures', zn);
fs.writeFileSync('../docs/lz4-soc-explainer.html', html);
// GitHub Pages serves the file as-is, so docs/index.html is the same page wrapped in a full document (standards mode, viewport meta).
{
  const cut = html.indexOf('</style>') + '</style>'.length;
  if (cut < 8) throw new Error('style block missing');
  const page = '<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta name="viewport" content="width=device-width, initial-scale=1">\n' + html.slice(0, cut) + '\n</head>\n<body>' + html.slice(cut) + '\n</body>\n</html>\n';
  fs.writeFileSync('../docs/index.html', page);
}

const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map(m => m[1]);
const dup = ids.filter((x, i) => ids.indexOf(x) !== i);
console.log('ids', ids.length, 'duplicates', dup);
const refs = [...scripts[1].matchAll(/\$\('([^']+)'\)/g)].map(m => m[1]);
console.log('missing ids referenced by script:', [...new Set(refs)].filter(r => !ids.includes(r)));
for (const k of ['fA', 'fB', 'flowSvg']) if (!ids.includes(k)) console.log('missing', k);

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
console.log('hero:', reg.heroCap.textContent);
console.log('len:', reg.lenOut.textContent);
console.log('xl:', reg.xlRes.textContent);
console.log('lab:', reg.labRes.innerHTML.replace(/<[^>]+>/g, ' | ').slice(0, 220));
console.log('lat:', reg.latRes.innerHTML.replace(/<[^>]+>/g, ' | ').slice(0, 260));
console.log('cap:', reg.capRes.innerHTML.replace(/<[^>]+>/g, ' | ').slice(0, 300));
console.log('dec:', reg.decExp.innerHTML, reg.decCount.textContent);
console.log('enc:', reg.encExp.innerHTML, reg.encCount.textContent);
// Walk every stepper state to surface runtime errors.
let c = 0;
while (!reg.decNext.disabled) { reg.decNext.onclick(); c++; }
console.log('dec last:', reg.decExp.innerHTML, reg.decCount.textContent);
{ const strip = h => h.replace(/<[^>]+>/g, ''); const ed = () => { if (process.env.ENC) console.log('E', reg.encCount.textContent, strip(reg.encExp.innerHTML), '\n   vars:', strip(reg.encVars.innerHTML.replace(/<\/span>/g, ' | ')), '\n   out:', strip(reg.encOut.innerHTML.replace(/<\/span>/g, ' ')), '\n   tab:', strip(reg.encTable.innerHTML.replace(/<\/span>/g, ' | ')).slice(0, 160)); }; ed(); while (!reg.encNext.disabled) { reg.encNext.onclick(); c++; ed(); } }
console.log('enc last:', reg.encExp.innerHTML, reg.encCount.textContent);
for (const p of ['bt', 'ev', 'fi']) { const strip = h => h.replace(/<br>/g, ' / ').replace(/<[^>]+>/g, ''); const d = () => { if (process.env.STEP) console.log(p, reg[p + 'Count'].textContent, strip(reg[p + 'Exp'].innerHTML), '\n   ', strip(reg[p + 'Body'].innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | ')).slice(0, 4000)); }; d(); while (!reg[p + 'Next'].disabled) { reg[p + 'Next'].onclick(); c++; d(); } console.log(p, reg[p + 'Count'].textContent, strip(reg[p + 'Exp'].innerHTML).slice(0, 80)); }
for (const f of ['fA', 'fB', 'fC']) { reg[f].onclick(); while (!reg.flowNext.disabled) { reg.flowNext.onclick(); c++; } console.log(f, reg.flowExp.innerHTML.slice(0, 90)); }
{ const strip = h => h.replace(/<[^>]+>/g, '');
  const dump = () => { console.log('L', reg.lifeCount.textContent, strip(reg.lifeExp.innerHTML)); console.log('   sum:', reg.lifeSum.textContent); console.log('   pages:', strip(reg.lifePages.innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | '))); console.log('   cot:', strip(reg.lifeCot.innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | '))); console.log('   pool:', strip(reg.lifePool.innerHTML.replace(/<\/div>/g, ' '))); console.log('   stack:', strip(reg.lifeStack.innerHTML.replace(/<\/span>/g, ' ')), reg.lifeStack.className); console.log('   frames:', strip(reg.lifeFrames.innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | '))); console.log('   misc:', strip(reg.lifeMisc.innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | '))); };
  console.log('sizes:', strip(reg.lifeSizes.innerHTML.replace(/<\/tr>/g, ' || ').replace(/<\/td>/g, ' | ')));
  dump(); while (!reg.lifeNext.disabled) { reg.lifeNext.onclick(); c++; if (process.env.LIFE) dump(); } if (!process.env.LIFE) dump(); }
console.log('walked', c, 'steps; size', Math.round(html.length / 1024), 'KB');

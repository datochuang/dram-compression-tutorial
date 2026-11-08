// Maintains en.json, the line-for-line English translation table used by build.js.
//   node i18n.js missing              list lines of page.html with Chinese text and no entry, and stale entries
//   node i18n.js show <lineno>        print the source line and its current translation
//   node i18n.js set <lineno> <text>  set the translation of that source line (text is one line, same markup)
//   node i18n.js prune                drop entries whose source line no longer exists in page.html
// Entries are kept in page order so diffs stay readable.
const fs = require('fs');
const CJK = /[一-鿿　-〿＀-￯]/;
const lines = fs.readFileSync('page.html', 'utf8').split('\n');
const en = fs.existsSync('en.json') ? JSON.parse(fs.readFileSync('en.json', 'utf8')) : {};
const has = k => Object.prototype.hasOwnProperty.call(en, k);
const [cmd, arg, ...rest] = process.argv.slice(2);

function save() {
  const order = new Map(lines.map((l, i) => [l, i]));
  const keys = Object.keys(en).sort((a, b) => (order.has(a) ? order.get(a) : 1e9) - (order.has(b) ? order.get(b) : 1e9));
  const out = {}; for (const k of keys) out[k] = en[k];
  fs.writeFileSync('en.json', JSON.stringify(out, null, 1) + '\n');
}
function skeleton(l, js) {
  if (js) return l.replace(/'(?:[^'\\]|\\.)*'/g, "''");
  return (l.match(/<[^>]+>/g) || []).map(t => t.replace(/\b(aria-label|title|alt|placeholder)="[^"]*"/g, '$1=""')).join('');
}
const scriptStart = lines.findIndex((l, i) => l.startsWith('<script>') && i > 100 && !lines[i + 1].includes('__CORE__'));

if (cmd === 'missing') {
  const miss = lines.map((l, i) => (CJK.test(l) && !has(l)) ? (i + 1) + ': ' + l.trim().slice(0, 120) : null).filter(Boolean);
  const stale = Object.keys(en).filter(k => !lines.includes(k));
  console.log('missing', miss.length); miss.forEach(m => console.log('  ' + m));
  console.log('stale', stale.length); stale.forEach(s => console.log('  ' + s.trim().slice(0, 120)));
} else if (cmd === 'show') {
  const l = lines[+arg - 1]; console.log('zh:', l); console.log('en:', has(l) ? en[l] : '(none)');
} else if (cmd === 'set') {
  const n = +arg, l = lines[n - 1], text = rest.join(' ');
  if (!l) throw new Error('no such line');
  if (/\n/.test(text)) throw new Error('translation must be one line');
  if (CJK.test(text)) console.log('warning: translation still contains CJK');
  const js = n - 1 > scriptStart;
  if (skeleton(l, js) !== skeleton(text, js)) console.log('warning: markup/code skeleton differs from the source line');
  en[l] = text; save(); console.log('set line', n);
} else if (cmd === 'prune') {
  let n = 0; for (const k of Object.keys(en)) if (!lines.includes(k)) { delete en[k]; n++; }
  save(); console.log('pruned', n);
} else {
  console.log('usage: node i18n.js missing | show <lineno> | set <lineno> <text> | prune');
}

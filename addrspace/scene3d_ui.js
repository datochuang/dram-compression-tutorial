/* ---------- steps, table, controls ---------- */
let cur = { scene: 0, plan: null, i: 0 }, timer = 0, freeKind = 'read';

function table(step, prev) {
  const selPages = new Set(SYM[step.sym].slices.map(s => s.p));
  const cells = t => [t.pte ? 'V=1, frame ' + t.pte : 'V=0, invalid', t.state, t.cot ? t.cot.cs.map(ckNo).join(' ') : 'empty', t.cot ? t.cot.len + ' B in ' + t.cot.n + ' chunks' : 'none'];
  $('rows').innerHTML = D.pages.map((pg, p) => {
    const t = tabOf(step.st, p), now = cells(t), was = prev ? cells(tabOf(prev.st, p)) : now;
    return `<tr class="${selPages.has(p) ? 'selrow' : ''}"><td>${pgNo(p)} ${pg.kind.toUpperCase()}</td><td>${ONPAGE[p].map(s => s.sym).join(', ')}</td>` +
      now.map((v, i) => `<td class="${(v !== was[i] ? 'chg ' : '') + (i === 0 ? 'pte' + (t.pte ? '' : ' inv') : '')}">${i === 1 ? '<span class="st">' + v + '</span>' : v}</td>`).join('') + '</tr>';
  }).join('');
}
function show(animateIn) {
  const steps = cur.plan.steps, step = steps[cur.i], prev = cur.i ? steps[cur.i - 1] : null, last = cur.i === steps.length - 1;
  drawBoard(step, prev); drawFloor(step); drawHW(step); ARRIVE = updateDram(step); buildDynamic(step);
  stepT0 = performance.now() - (animateIn ? 0 : 9000);
  table(step, prev);
  $('count').textContent = (cur.scene === null ? '自己發的 access' : '場景 ' + (cur.scene + 1) + ' / ' + SCENES.length + '：' + SCENES[cur.scene].t) + ' · 第 ' + (cur.i + 1) + ' 步，共 ' + steps.length + ' 步';
  $('who').textContent = WHO[step.who]; $('who').className = 'who ' + step.who;
  $('text').innerHTML = step.text;
  $('back').disabled = cur.i === 0;
  const more = cur.scene !== null && cur.scene < SCENES.length - 1;
  $('next').disabled = last && !more; $('next').textContent = last && more ? '下一個場景' : '下一步';
  [...$('scenes').children].forEach((b, k) => b.setAttribute('aria-pressed', String(k === cur.scene)));
}
function loadScene(k) {
  let st = initState();
  for (let j = 0; j < k; j++) st = plan(st, SCENES[j].sym, SCENES[j].off, SCENES[j].kind).final;
  cur = { scene: k, plan: plan(st, SCENES[k].sym, SCENES[k].off, SCENES[k].kind), i: 0 };
  show(false);
}
function next() {
  if (cur.i < cur.plan.steps.length - 1) { cur.i++; show(true); return true; }
  if (cur.scene !== null && cur.scene < SCENES.length - 1) { loadScene(cur.scene + 1); return true; }
  return false;
}
function stop() { clearInterval(timer); timer = 0; $('play').textContent = '自動播放'; }
$('scenes').innerHTML = SCENES.map((s, k) => `<button type="button" data-k="${k}" aria-pressed="false"><b>${k + 1}</b>${s.t}</button>`).join('');
// Bring the whole stage into view when it does not fit under the page header (tablet landscape).
const STAGE = document.querySelector('.stage');
function fit() { const r = STAGE.getBoundingClientRect(); if (r.bottom > innerHeight + 4 && r.top > 12) STAGE.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
$('scenes').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { stop(); loadScene(+b.dataset.k); fit(); } });
$('next').addEventListener('click', () => { stop(); next(); fit(); });
$('back').addEventListener('click', () => { stop(); if (cur.i) { cur.i--; show(false); } });
$('play').addEventListener('click', () => {
  if (timer) return stop();
  $('play').textContent = '暫停';
  fit();
  if (!next()) return stop();
  timer = setInterval(() => { if (!next()) stop(); }, 4200);
});
const setKind = k => { freeKind = k; $('kread').setAttribute('aria-pressed', String(k === 'read')); $('kwrite').setAttribute('aria-pressed', String(k === 'write')); };
$('kread').addEventListener('click', () => setKind('read')); $('kwrite').addEventListener('click', () => setKind('write'));
onTap = e => {
  const h = boardHit(e); if (!h) return;
  stop(); cur = { scene: null, plan: plan(cur.plan.final, h.sym.id, h.off, freeKind), i: 0 }; show(false);
};
document.addEventListener('keydown', e => {
  if (e.target.closest('input, textarea')) return;
  if (e.key === 'ArrowRight') { stop(); next(); } else if (e.key === 'ArrowLeft') $('back').click();
});

/* theme and fonts: everything drawn on a canvas has to be redrawn when either changes */
function restyle() {
  readPalette(); scene.background = new THREE.Color(P.bg); buildMaterials(); hwBox.material = MAT.hw;
  if (cur.plan) show(false);
}
restyle();
if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', restyle);
new MutationObserver(restyle).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
loadScene(0);
if (document.fonts && document.fonts.load) Promise.all(['400 20px "IBM Plex Mono"', '600 20px "IBM Plex Mono"', '700 20px Archivo', '800 20px Archivo'].map(f => document.fonts.load(f))).then(() => show(false), () => {});
resize(); requestAnimationFrame(animate);

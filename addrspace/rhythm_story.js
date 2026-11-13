/* ---------- two rhythms: acts, camera, controls, sound, the loop ---------- */
const SPEED = 7;                                         // world units per second at 100%: the speed of the train
const KEEP = XB * 1000 * 1.2 * BASE;                            // history kept, enough for the widest lens
const hex = p => '0x' + p.toString(16).toUpperCase();
const fmt = n => Math.round(n).toLocaleString('en-US');
let sim = null, now = 0, lens = 1, lensT = 1, pace = 0.7, playing = true, auto = true, slow = 1, slowT = 1;
let act = 0, actT = 0, beat = '', beatT = 0, lastOut = null, pruneT = 0, demoOn = true;

/* ---------- the controls under the stage ---------- */
const SL = [
  ['ws', '長期 working set', '每個程式，page'], ['drift', 'working set 漂移', '每 10 000 次 access 換進的新 page'],
  ['tlb', 'TLB entries', '每個 core'], ['frames', 'frame 區', '兩個程式共用，page'], ['l2', 'L2', '放得下的 page 或 PTE 行'],
];
const IN = {}, OUT = {};
SL.forEach(([k, name, sub]) => {
  const row = document.createElement('div'); row.style.display = 'contents'; row.id = 'row-' + k;
  const [lo, hi] = RHY.RANGE[k];
  row.innerHTML = `<label for="in-${k}">${name}<small>${sub}</small></label><input type="range" id="in-${k}" min="${lo}" max="${hi}" step="1"><output id="out-${k}"></output>`;
  $('sliders').appendChild(row); IN[k] = $('in-' + k); OUT[k] = $('out-' + k);
  IN[k].addEventListener('input', () => { demoOn = false; setParam(k, +IN[k].value, false); if (act === 2) say('你在調整控制。只有之後駛來的事件會改變，已經走過的留在軌道上。', 'YOU'); });
});
const tweens = {};
function setParam(k, v, animate) {
  if (animate) { tweens[k] = { from: sim.prm[k], to: v, t: 0 }; return; }
  sim.set(k, v); IN[k].value = v; OUT[k].textContent = fmt(v); drawRate();
}
function stepTweens(dt) {
  for (const k of Object.keys(tweens)) {
    const w = tweens[k]; w.t = Math.min(1, w.t + dt / 1.4);
    const e = w.t < 0.5 ? 2 * w.t * w.t : 1 - Math.pow(-2 * w.t + 2, 2) / 2;
    setParam(k, Math.round(w.from + (w.to - w.from) * e), false);
    $('row-' + k).classList.add('moved'); if (w.t >= 1) { delete tweens[k]; setTimeout(() => $('row-' + k).classList.remove('moved'), 1500); }
  }
}
$('defaults').addEventListener('click', () => { demoOn = false; Object.keys(RHY.DEF).forEach(k => setParam(k, RHY.DEF[k], true)); });

/* what sets the rate: the working sets against the three capacities, on a log scale of pages */
function drawRate() {
  if (!sim) return;
  const p = sim.prm, L = v => 30 + 500 * Math.log2(Math.max(1, v)) / 11, svg = $('ratesvg');
  const longWS = p.ws * sim.nprog, ink = 'var(--ink)', mut = 'var(--muted)';
  let h = '';
  [1, 4, 16, 64, 256, 1024].forEach(v => { h += `<line x1="${L(v)}" y1="186" x2="${L(v)}" y2="191" stroke="${mut}"/><text x="${L(v)}" y="204" font-size="11" text-anchor="middle" fill="${mut}" font-family="var(--mono)">${v}</text>`; });
  h += `<line x1="${L(1)}" y1="186" x2="${L(2048)}" y2="186" stroke="${mut}"/><text x="${L(2048)}" y="178" font-size="11" text-anchor="end" fill="${mut}" font-family="var(--mono)">pages, log scale</text>`;
  const bar = (y, v, label, col) => { h += `<rect x="${L(1)}" y="${y}" width="${L(v) - L(1)}" height="14" fill="${col}" opacity=".85" rx="2"/><text x="${L(1) + 4}" y="${y - 4}" font-size="12" fill="${ink}" font-family="var(--mono)">${label}: ${v}</text>`; };
  const brk = (y, v, label, col) => { const x = L(v); h += `<path d="M${L(1)} ${y + 7} V${y} H${x} V${y + 7}" fill="none" stroke="${col}" stroke-width="2"/><text x="${x + 4}" y="${y + 6}" font-size="12" fill="${col}" font-family="var(--mono)">${label}: ${v}</text>`; };
  brk(14, p.tlb, 'TLB reach (entries per core)', 'var(--kern)');
  bar(44, RHY.SHORT, 'short-term working set, per program', 'var(--ua)');
  brk(88, p.l2, 'L2: cost, not count', mut);
  brk(114, p.frames, 'frames', 'var(--lz)');
  bar(146, longWS, 'long-term working set, both programs', 'var(--ub)');
  svg.innerHTML = h;
  const s1 = RHY.SHORT > p.tlb ? `短時間用到的 ${RHY.SHORT} 個 page 多於 TLB 的 ${p.tlb} 格：<b>TLB miss 一直發生</b>。` : `短時間用到的 ${RHY.SHORT} 個 page 放得進 TLB：只有 working set 往前移時才 TLB miss。`;
  const s2 = longWS > p.frames ? `兩個程式的長期 working set 共 ${longWS} 個 page，多於 ${p.frames} 個 frame：<b>thrashing</b>，page fault 一直發生。` : `長期 working set 共 ${longWS} 個 page，放得進 ${p.frames} 個 frame：只有 working set 漂移時才 page fault。`;
  $('say').innerHTML = s1 + '<br>' + s2 + '<br>L2 只改變每一次的長短，不改變次數。';
}

/* ---------- acts ---------- */
const ACTS = [
  { name: '一次 access 的三條路', who: 'ONE ACCESS' }, { name: '兩種節奏', who: 'TIME LENS' },
  { name: '頻率由什麼決定', who: 'WHAT SETS THE RATE' }, { name: '兩邊碰到的地方', who: 'WHERE THEY MEET' },
];
ACTS.forEach((a, i) => { const b = document.createElement('button'); b.type = 'button'; b.innerHTML = `<b>${i + 1}</b>${a.name}`; b.addEventListener('click', () => enter(i)); $('acts').appendChild(b); a.btn = b; });
function say(text, who) { $('text').textContent = text; if (who) $('who').textContent = who; }
function enter(i) {
  act = i; actT = 0; beat = ''; beatT = 0; demoOn = true;
  ACTS.forEach((a, j) => a.btn.setAttribute('aria-pressed', j === i ? 'true' : 'false'));
  $('count').textContent = `第 ${i + 1} 幕，共 4 幕：${ACTS[i].name}`; $('who').textContent = ACTS[i].who;
  Object.keys(tweens).forEach(k => delete tweens[k]);
  if (i === 0) {                                        // the story starts over: one page was pushed out before it begins
    sim = RHY.create({ plant: true, seed: 3 }); sim.recAcc = true; now = -10; lens = lensT = 1;
    Object.keys(RHY.DEF).forEach(k => setParam(k, RHY.DEF[k], false));
    stateInit(sim);
  }
  if (i === 2) lensT = 100;
  if (i === 3) { lensT = 10; setParam('drift', 40, true); }
  runAct(0);
}
const upcoming = (arr, key, a, b) => { for (let j = arr.length - 1; j >= 0; j--) { const t = arr[j][key]; if (t >= a && t <= b) return arr[j]; if (t < a - 5000) break; } return null; };
function runAct(dt) {
  actT += dt; beatT += dt; const o = lastOut, next = () => { if (auto) enter(act + 1); };
  const setBeat = (b, text) => { if (beat !== b) { beat = b; beatT = 0; say(text); } };
  slowT = 1;
  if (act === 0) {
    const pf = sim.ev.fault.find(f => f.p === sim.planted);
    if (pf && now >= pf.t0 - 3 && now < pf.t1 + 2) { slowT = 0.35; setBeat('fault', '這一次 TLB miss 讀到的 PTE 是 invalid，所以是 page fault。壓縮層這邊的 kernel SW 接手：拿一個 frame，請 LZ4 HW 做 DECOMPRESS。user SW A 停下來等這一頁，它的軌道上留下紅色的缺口。下面的表格依序亮起：PTE 被讀、COT entry 被讀、一個 frame 被拿走、LZ4 HW 寫那個 frame，最後 COT entry 清掉、PTE 寫成 valid、TLB 填一格。'); }
    else if (pf && now >= pf.t1 + 2) { setBeat('after', 'user SW A 拿到它的 page，繼續跑。同一次 access 可能沒事、可能是小事，也可能是大事。接下來把時間鏡頭拉遠。'); if (beatT > 8) next(); }
    else if (actT > 6 && beat !== 'miss') setBeat('miss', '紫色的細刻度是一次 TLB miss。這個平台沒有 hardware page table walk，每一次都進 exception，由 kernel SW 讀 PTE、填 TLB，很快就回去。刻度的寬度是它花的時間：PTE 那一行在 L2 裡就短一點。表格裡，被讀的 PTE 亮紫框，被寫的 TLB entry 填紫色。');
    else if (!beat) setBeat('hit', '每一個小點是 user SW 的一次 access。大多數是 TLB hit：CPU MMU 在自己 core 的 TLB 裡找到對應，硬體直接完成，kernel SW 不用起來。下面的表格同步更新：CPU MMU 查到的 TLB entry 亮灰框，被讀寫的 frame 亮程式的顏色。');
  } else if (act === 1) {
    const plan = [[0, 1], [4, 10], [16, 100], [30, 1000]];
    let L = 1; plan.forEach(([t, v]) => { if (actT >= t) L = v; }); lensT = L;
    const T = { 1: '接下來每隔幾秒把時間鏡頭拉遠十倍：火車加速，攝影機升高，畫面不停。', 10: '×10：CPU MMU 這邊的刻度越來越密，壓縮層這邊大多還是空的。', 100: '×100：TLB miss 已經分不開，糊成一條帶子，帶子的高度是 kernel SW 花在 TLB miss 上的時間比例。page fault 的大框這時才看得清楚。', 1000: '×1000：畫面裡有上萬次 TLB miss，page fault 只有幾十次。兩邊被叫起來的次數差了好幾個數量級。時間尺度是範例模型的，不是這個平台量出來的。' };
    setBeat('L' + L, T[L]);
    if (actT > 46) next();
  } else if (act === 2) {
    const steps = [
      [0, null, '下面的長條和白板圖 D 一樣：working set 和三個容量比。控制只改變之後駛來的事件。先看自動示範。'],
      [8, { tlb: 64 }, 'TLB entries 16 → 64：短時間用到的 24 個 page 放得進 TLB 了。只有 CPU MMU 那條變薄，壓縮層那條不變。'],
      [21, { tlb: 16, l2: 8 }, 'TLB 回到 16，L2 縮到 8：TLB miss 的次數不變，但 PTE 那一行常常不在 L2，每一次都變長，帶子變高。對照左上角的次數。'],
      [34, { l2: 64, frames: 240 }, `L2 回到 64，frame 區從 ${RHY.DEF.frames} 縮到 240，比兩個程式的長期 working set 320 小：page fault 突然變密，壓縮層這邊幾乎沒停過，user SW 一直在等。這就是 thrashing。`],
      [56, { frames: RHY.DEF.frames, drift: 60 }, `frame 區回到 ${RHY.DEF.frames}，working set 漂移變快：新的 page 不斷進來，兩邊都變多。`],
      [70, { drift: 5 }, '全部回到預設值。你也可以自己拖動下面的控制。'],
    ];
    if (demoOn) steps.forEach(([t, ch, text], j) => { if (actT >= t && beat !== 'd' + j && (j === steps.length - 1 || actT < steps[j + 1][0])) { if (ch) Object.keys(ch).forEach(k => setParam(k, ch[k], true)); setBeat('d' + j, text); } });
    if (demoOn && actT > 80) next();
  } else if (act === 3) {
    const w = 14 * lens * BASE;
    const ft = upcoming(sim.ev.fault, 't0', now - 2 * lens, now + w), cl = upcoming(sim.ev.clr, 't', now - 2 * lens, now + w);
    if (ft || cl) slowT = 0.3;
    if (beatT > 7 || !beat) {
      if (ft && beat !== 'm1') setBeat('m1', '交會點一：這一次 TLB miss 讀到的 PTE 是 invalid，紅色菱形標的就是它。CPU MMU 這邊的 kernel SW 把工作交給壓縮層這邊，變成 page fault。');
      else if (cl && beat !== 'm2') setBeat('m2', '交會點二：reclaim 要拿走一個 frame，先把 PTE 設成 invalid，再把這一頁從每一個 core 的 TLB 清掉，紫色菱形標的就是它。怎麼清到別的 core，這個平台還不知道。表格裡那一頁的 TLB entry 被清空，PTE 寫成 invalid，紫色三角形是 clock 的指針。');
      else if (!beat) setBeat('m0', '兩邊只在兩個地方碰到。碰到的時候，畫面會放慢。working set 漂移調快了，交會點會比較常出現。');
    }
  }
}

/* ---------- camera: rides with now; the viewer's own turn, tilt and zoom are kept on top ---------- */
const camS = { r: 0.4, ph: 1.0, tx: -15, tz: 1.5 }, off = { th: 0, ph: 0, rk: 1, t: new THREE.Vector3() };
let last = null, skip = true;
new ResizeObserver(() => { skip = true; }).observe($('view'));
$('reset').addEventListener('click', () => { off.th = 0; off.ph = 0; off.rk = 1; off.t.set(0, 0, 0); skip = true; });
function preset() {
  const g = Math.min(1, Math.log10(Math.max(1, lens)) / 3);
  if (act === 0) return { r: 0.4, ph: 1.0, tx: -15, tz: 1.5 };
  if (act === 1) return { r: 0.4 + 0.42 * g, ph: 1.0 + 0.12 * g, tx: -15 - 19 * g, tz: 1.5 - g };
  if (act === 2) return { r: 0.8, ph: 1.08, tx: -32, tz: 0.5 };
  return { r: 0.62, ph: 1.0, tx: -22, tz: 1.5 };
}
function camFrame(dt) {
  if (last && !skip) { off.th += cam.th - last.th; off.ph += cam.ph - last.ph; off.rk *= cam.r / last.r; off.t.add(V.copy(cam.t).sub(last.t)); }
  skip = false;
  const p = preset(), a = 1 - Math.exp(-dt * 1.4);
  camS.r += (p.r - camS.r) * a; camS.ph += (p.ph - camS.ph) * a; camS.tx += (p.tx - camS.tx) * a; camS.tz += (p.tz - camS.tz) * a;
  cam.th = off.th; cam.ph = Math.min(1.45, Math.max(0.1, camS.ph + off.ph)); cam.r = HOME.r * camS.r * off.rk;
  cam.t.set(camS.tx, HOME.t.y, HOME.t.z + camS.tz).add(off.t); placeCamera();
  last = { th: cam.th, ph: cam.ph, r: cam.r, t: cam.t.clone() };
}

/* ---------- sound, off until asked for ---------- */
let AC = null, hum = null, humG = null, soundOn = false;
$('sound').addEventListener('click', () => {
  soundOn = !soundOn; $('sound').setAttribute('aria-pressed', soundOn); $('sound').textContent = soundOn ? '聲音：開' : '聲音：關';
  if (soundOn && !AC) { const A = window.AudioContext || window.webkitAudioContext; if (!A) return; AC = new A(); hum = AC.createOscillator(); humG = AC.createGain(); hum.type = 'sawtooth'; hum.frequency.value = 110; humG.gain.value = 0; hum.connect(humG).connect(AC.destination); hum.start(); }
  if (AC) { if (soundOn) AC.resume(); else humG.gain.value = 0; }
});
function blip(freq, len, gain, type) {
  const o = AC.createOscillator(), g = AC.createGain(), t = AC.currentTime;
  o.type = type || 'square'; o.frequency.value = freq; g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + len);
  o.connect(g).connect(AC.destination); o.start(t); o.stop(t + len + 0.02);
}
function sound(prev, dt) {
  if (!soundOn || !AC || dt <= 0) return;
  let n = 0; for (let j = sim.ev.tick.length - 1; j >= 0 && sim.ev.tick[j].t > prev; j--) if (sim.ev.tick[j].t <= now) n++;
  const rate = n / dt;
  if (rate < 25) { for (let j = 0; j < Math.min(n, 4); j++) blip(2200, 0.02, 0.04); humG.gain.value = 0; }
  else humG.gain.value = Math.min(0.05, rate / 6000);
  for (const f of sim.ev.fault) if (f.t0 > prev && f.t0 <= now) blip(70, 0.35, 0.3, 'sine');
  for (const c of sim.ev.clr) if (c.t > prev && c.t <= now) blip(880, 0.12, 0.06, 'triangle');
}

/* ---------- speech bubbles and the counter ---------- */
function bubbles(o) {
  const b = {}, name = (k, t) => `<b>${k}</b>${t}`, close = lens < 20;
  for (let p = 0; p < 2; p++) {
    const w = o.waitNow.find(x => x.prog === p), nm = p ? 'USER SW B' : 'USER SW A';
    if (w) b[p ? 'ub' : 'ua'] = { html: name(nm, 'waiting for page ' + hex(w.p)), hot: true };
    else if (act === 0) b[p ? 'ub' : 'ua'] = { html: name(nm, 'running · TLB hits need no kernel') };
  }
  for (let c = 0; c < 2; c++) {
    const e = o.last[c], k = c ? 'k1' : 'k0', nm = 'KERNEL SW · CORE ' + c;
    if (close && e && now - e.t < 1.6 * SPEED * pace * slow * lens * BASE) b[k] = { html: name(nm, e.fault ? 'TLB miss: the PTE is invalid' : 'TLB miss: read the PTE, fill the TLB'), hot: !!e.fault };
    else if (!close) b[k] = { html: name(nm, fmt(o.tick[c]) + ' TLB misses in view') };
  }
  if (o.faultNow.length) { const f = o.faultNow[0]; b.kc = { html: name('KERNEL SW', `page fault on Core ${f.core}: DECOMPRESS page ${hex(f.p)}` + (f.tw && now < f.tw[1] ? ' · waiting for a free frame' : '')), hot: true }; }
  else if (o.recNow.length) b.kc = { html: name('KERNEL SW', `reclaim: COMPRESS page ${hex(o.recNow[0].p)}` + (o.recNow.length > 1 ? ` and ${o.recNow.length - 1} more` : '')) };
  else b.kc = { html: name('KERNEL SW', close ? 'nothing to do' : `${fmt(o.fault)} page faults · ${fmt(o.rec)} reclaims in view`) };
  if (o.jobNow.length) { const j = o.jobNow; b.lz = { html: name('LZ4 HW', j.slice(0, 2).map(x => (x.op === 'D' ? 'DECOMPRESS ' : 'COMPRESS ') + hex(x.p)).join(' · ') + (j.length > 2 ? ` · +${j.length - 2}` : '')) }; }
  else b.lz = { html: name('LZ4 HW', 'idle') };
  return b;
}
function hud(o) {
  const L = lens < 1.5 ? '×1' : '×' + fmt(lens);
  const m = o.tick[0] + o.tick[1];
  $('hud').innerHTML = `<div><span class="lens">time lens ${L}</span> <span class="why">example model time, not measured</span></div>` +
    `<div>in view: ${fmt(m)} TLB misses · ${fmt(o.fault)} page faults · ${fmt(o.rec)} reclaims` + (o.fault >= 5 && lens >= 10 ? ` <span class="why">· ${fmt(m / o.fault)} per fault</span>` : '') + '</div>';
}

/* ---------- the loop ---------- */
$('play').addEventListener('click', () => { playing = !playing; $('play').textContent = playing ? '暫停' : '播放'; });
$('auto').addEventListener('click', () => { auto = !auto; $('auto').setAttribute('aria-pressed', auto); });
document.querySelectorAll('[data-pace]').forEach(b => b.addEventListener('click', () => { pace = +b.dataset.pace; document.querySelectorAll('[data-pace]').forEach(x => x.setAttribute('aria-pressed', x === b)); }));
const mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
if (mq && mq.addEventListener) mq.addEventListener('change', () => { buildAll(); colors(); stateColors(); });
buildAll(); colors(); stateColors(); enter(0);
// ?act=K starts at act K, ?skip=S runs S seconds of the story at once (for a quick look or a screenshot)
const QS = new URLSearchParams(location.search);
if (+QS.get('act') > 1) enter(Math.min(4, +QS.get('act')) - 1);
function step(dt) {
  runAct(playing ? dt : 0); stepTweens(dt);
  slow += (slowT - slow) * (1 - Math.exp(-dt * 3));
  lens *= Math.pow(lensT / lens, 1 - Math.exp(-dt * 0.9)); if (Math.abs(lens / lensT - 1) < 0.002) lens = lensT;
  sim.recAcc = lens < 3;
  if (playing) now += dt * SPEED * pace * slow * lens * BASE * (REDUCE ? 0.5 : 1);
  sim.advance(now + 20 * lens * BASE + 50);
  if ((pruneT += dt) > 1) { pruneT = 0; sim.prune(now - KEEP); }
  stateStep(sim, now);
}
for (let w = +QS.get('skip') || 0; w > 0; w -= 0.05) { step(0.05); if (w < 0.1) lastOut = draw(sim, now, lens); }
let tPrev = performance.now();
function frame(tNow) {
  const dt = Math.max(0, Math.min(0.05, (tNow - tPrev) / 1000)); tPrev = Math.max(tPrev, tNow);
  const prev = now;
  step(dt);
  lastOut = draw(sim, now, lens);
  sound(prev, dt);
  // characters: kernel SW on the CPU MMU side hops at each TLB miss
  for (let c = 0; c < 2; c++) { const e = lastOut.last[c], g = CH['k' + c], age = e ? (now - e.t) / (lens * BASE) : 99; g.position.y = lens < 20 ? Math.max(0, 0.8 * (1 - age / 0.8)) : 0.25 * Math.abs(Math.sin(tNow / 90 + c)); }
  CH.kc.position.y = lastOut.faultNow.length || lastOut.recNow.length ? 0.3 * Math.abs(Math.sin(tNow / 160)) : 0;
  CH.ua.position.y = lastOut.waitNow.some(w => w.prog === 0) ? 0 : 0.15 * Math.abs(Math.sin(tNow / 200));
  CH.ub.position.y = lastOut.waitNow.some(w => w.prog === 1) ? 0 : 0.15 * Math.abs(Math.sin(tNow / 230 + 1));
  camFrame(dt);
  if (renderer) renderer.render(scene, camera);
  const say = bubbles(lastOut); placeOverlays(say);
  hud(lastOut);
  stateDraw(sim, now, lens);
  requestAnimationFrame(frame);
}
drawRate();
requestAnimationFrame(frame);

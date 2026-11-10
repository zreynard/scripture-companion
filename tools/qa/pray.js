// Pray, every scenario: navigation and memory, Be Led, Meditate, the Lord's Prayer, Stillness, and Pray against the
// other players (sermons, lock screen, background). A generated test recording stands in where a test needs exact times.
//   SITE=http://localhost:8765/ [BROWSER=webkit] node tools/qa/pray.js
const { chromium, webkit } = require('playwright');
const ENGINE = process.env.BROWSER === 'webkit' ? webkit : chromium;
const SITE = process.env.SITE || 'http://localhost:8765/';
const R = []; const wait = ms => new Promise(r => setTimeout(r, ms));
let b; const OPEN = [];
async function T(n, f) {
  if (process.env.ONLY && !new RegExp(process.env.ONLY).test(n)) return;
  let to; const limit = new Promise((_, no) => { to = setTimeout(() => no(new Error('took over 3 minutes')), 180000); });
  try { const r = await Promise.race([f(), limit]); R.push([n, r === true ? 'PASS' : 'FAIL ' + JSON.stringify(r).slice(0, 600)]); }
  catch (e) { R.push([n, 'FAIL ' + String(e).slice(0, 300)]); }
  clearTimeout(to); while (OPEN.length) { try { await OPEN.pop().close() } catch (e) { } } console.log(R[R.length - 1][1].startsWith('PASS') ? 'PASS' : 'FAIL', n, R[R.length - 1][1].startsWith('PASS') ? '' : R[R.length - 1][1].slice(5));
}
// a page with the lock-screen handlers recorded (so a test can press them) and its page errors kept
async function page(vp, ctxOpt) {
  const c = await b.newContext({ viewport: vp || { width: 390, height: 760 }, ...(ctxOpt || {}) }); OPEN.push(c);
  await c.addInitScript(() => { window.playing = () => ['audio', 'audiofx', 'praym', 'ledm', 'medm'].map(i => document.getElementById(i)).filter(a => a && !a.paused).map(a => a.id); window.__MS = {};
    try { const P = window.MediaSession && MediaSession.prototype, o = P && P.setActionHandler; if (o) P.setActionHandler = function (k, f) { window.__MS[k] = f; try { return o.call(this, k, f) } catch (e) { } }; } catch (e) { } });
  const p = await c.newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(String(e)));
  await p.goto(SITE + '?x=' + Date.now()); await p.waitForTimeout(1500); return p;
}
const pray = async p => { await p.evaluate(() => { $('#tabs [data-tab2=pray]').click(); }); await wait(400); };
const guided = async (p, m) => { await p.click('[data-prtop=g]'); await wait(250); if (m) { await p.click(`[data-prm=${m}]`); await wait(300); } };
// a 30 s test recording (a quiet tone), then every Be Led prayer and Meditate reading points at it
async function testAudio(p, opt) {
  await p.evaluate(o => {
    const sr = 8000, n = sr * 30, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf); const w = (q, s) => [...s].forEach((c, i) => v.setUint8(q + i, c.charCodeAt(0)));
    w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVEfmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, n * 2, true);
    for (let i = 0; i < n; i++) v.setInt16(44 + i * 2, Math.sin(i / 8) * 2000, true);
    window.TESTWAV = URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
    (PRAY.led || []).forEach(x => { x.audio = TESTWAV; x.sb = o.sb || 20; x.e = o.e || 10; x.L = 30; x.dur = 30; });
    (PRAY.med || []).forEach(x => { x.audio = TESTWAV; x.a = o.a || 5; x.b = o.b || 6.5; });
    window.MED_FAST = o.fast || 0.05;
  }, opt || {});
}
async function music(p) {   // two pieces of music kept on the phone, as the user's own
  await p.evaluate(async () => {
    const bl = new Blob([await (await fetch(TESTWAV)).arrayBuffer()], { type: 'audio/wav' });
    const meta = ['m1', 'm2'].map((id, k) => ({ id, f: id + '.wav', sz: bl.size, t: 'Test ' + id, a: 'A', al: 'Al', n: k + 1 }));
    try { for (const m of meta) await pdbDo(['meta', 'blob'], 'readwrite', t => { t.objectStore('blob').put(bl, m.id); return t.objectStore('meta').put(m) }); }
    catch (e) {   // an engine whose local database cannot keep audio (WebKit on Linux): hand the app the same files directly
      const o = pdbDo; window.pdbDo = (st, mode, f) => st === 'blob' && mode === 'readonly' ? Promise.resolve(bl) : st === 'meta' && mode === 'readonly' ? Promise.resolve(meta) : o(st, mode, f);
    }
    PL.list = null; await plLoad(); render(); });
  await wait(300);
}
const until = async (p, f, ms, arg) => { const t = Date.now(); while (Date.now() - t < (ms || 8000)) { if (await p.evaluate(f, arg)) return true; await wait(80); } return false; };
const playing = () => { const els = ['#audio', '#audiofx', '#praym', '#ledm', '#medm'].map(s => $(s)).filter(Boolean); return els.filter(a => !a.paused).map(a => a.id); };

(async () => {
  b = await ENGINE.launch(ENGINE === chromium ? { args: ['--autoplay-policy=no-user-gesture-required'] } : {});

  // ── Navigation and memory ───────────────────────────────────────────────────────────────────────────────────────
  await T('P1 Pray opens on Stillness the first time; Guided opens on Be Led the first time', async () => {
    const p = await pray_(await page());
    const a = await p.evaluate(() => ({ mode: PR.mode, top: document.querySelector('[data-prtop].on').dataset.prtop, sub: document.querySelectorAll('[data-prm]').length }));
    await guided(p); const g = await p.evaluate(() => ({ mode: PR.mode, sub: (document.querySelector('[data-prm].on') || {}).dataset.prm, txt: [...document.querySelectorAll('.pr-sub button')].map(x => x.textContent) }));
    return (a.mode === 'still' && a.top === 'still' && a.sub === 0 && g.mode === 'led' && g.sub === 'led' && g.txt.join('|') === "Be Led|Lord's Prayer|Meditate" && !p.errs.length) || { a, g, e: p.errs };
  });
  async function pray_(p) { await pray(p); return p; }
  await T('P2 sub-tab, Be Led place, both speeds and Music on/off are remembered after a reload, and they are backed up', async () => {
    const p = await pray_(await page()); await guided(p, 'med');
    await p.click('[data-medsp]'); await p.click('[data-medsp]');                    // 0.8×
    await guided(p, 'led'); await p.click('[data-ledsp]');                            // 1.1×
    await p.click('[data-ledgo="1"]'); await wait(200);
    const before = await p.evaluate(() => { BED.led = false; S.set('bedled', false); S.set('prsub', 'med'); S.set('prm', 'med'); return { p: ledOrd().p, id: ledCur().id } });
    await p.reload(); await wait(1500); await pray(p);
    const a = await p.evaluate(() => ({ mode: PR.mode, sub: (document.querySelector('[data-prm].on') || {}).dataset.prm, ledp: ledOrd().p, id: ledCur().id, ledsp: LED.sp, medsp: MED.sp, bed: BED.led, keys: ['prm', 'prsub', 'ledord', 'ledsp', 'medsp', 'bedled'].filter(k => !BK_KEYS.includes(k)) }));
    return (a.mode === 'med' && a.sub === 'med' && a.ledp === before.p && a.id === before.id && a.ledsp === 1.1 && a.medsp === 0.8 && a.bed === false && !a.keys.length && !p.errs.length) || { a, before };
  });
  await T('P3 switching Stillness, Guided and the sub-tabs fast 20 times: no errors, never two players at once, a consistent screen', async () => {
    const p = await pray_(await page()); await testAudio(p);
    const seq = ['g', 'led', 'med', 'still', 'g', 'guided', 'led', 'still', 'g', 'med', 'led', 'guided', 'still', 'g', 'led', 'med', 'g', 'guided', 'still', 'g'];
    await guided(p, 'led'); await p.click('[data-ledpp]'); await wait(300);
    for (const s of seq) { const sel = ['g', 'still'].includes(s) ? `[data-prtop=${s}]` : `[data-prm=${s}]`; if (await p.$(sel)) await p.click(sel); await wait(60); }
    await wait(500);
    const a = await p.evaluate(playing), st = await p.evaluate(() => ({ mode: PR.mode, onTop: document.querySelectorAll('[data-prtop].on').length, onSub: document.querySelectorAll('[data-prm].on').length }));
    return (a.length <= 1 && st.onTop === 1 && (st.mode === 'still' ? st.onSub === 0 : st.onSub === 1) && !p.errs.length) || { a, st, e: p.errs };
  });
  await T('P4 a mode saved by the four-tab version opens on the right tab and sub-tab', async () => {
    const out = {};
    for (const m of ['led', 'med', 'guided', 'still']) {
      const p = await page(); await p.evaluate(m => { S.set('prm', m) }, m); await p.reload(); await wait(1500); await pray(p);
      out[m] = await p.evaluate(() => [document.querySelector('[data-prtop].on').dataset.prtop, (document.querySelector('[data-prm].on') || {}).dataset ? document.querySelector('[data-prm].on') && document.querySelector('[data-prm].on').dataset.prm : '']);
      await p.context().close();
    }
    return (out.led.join() === 'g,led' && out.med.join() === 'g,med' && out.guided.join() === 'g,guided' && out.still[0] === 'still') || out;
  });

  // ── Be Led ──────────────────────────────────────────────────────────────────────────────────────────────────────
  await T('P5 Be Led plays from the prayer\'s first word, never muted; the ring advances; pause and play go on from there', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'led');
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing');
    const a = await p.evaluate(() => ({ t: LED.c.a.currentTime, t0: LED.c.t0, muted: LED.c.a.muted, icon: document.querySelector('[data-ledpp]').getAttribute('aria-label') }));
    await wait(900); const r1 = await p.evaluate(() => parseFloat($('#ledfg').getAttribute('stroke-dasharray')));
    await p.click('[data-ledpp]'); await wait(300); const ps = await p.evaluate(() => ({ st: LED.c.state, t: LED.c.a.currentTime, icon: document.querySelector('[data-ledpp]').getAttribute('aria-label') }));
    await wait(600); await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing'); const rs = await p.evaluate(() => LED.c.a.currentTime);
    return (Math.abs(a.t - a.t0) < 0.4 && a.t0 === 10 && !a.muted && a.icon === 'Pause' && r1 > 0 && ps.st === 'paused' && ps.icon === 'Pray' && rs >= ps.t - 0.3 && rs < ps.t + 1 && !p.errs.length) || { a, r1, ps, rs };
  });
  await T('P6 back and forward 15 s stay inside the prayer, at both edges', async () => {
    const p = await pray_(await page()); await testAudio(p, { sb: 25, e: 2 }); await guided(p, 'led');   // prayer 5 s → 28 s
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing');
    await p.click('[data-ledsk="-15"]'); await wait(200); const lo = await p.evaluate(() => LED.c.a.currentTime);
    await p.click('[data-ledsk="15"]'); await wait(200); const mid = await p.evaluate(() => LED.c.a.currentTime);
    await p.click('[data-ledsk="15"]'); await wait(200); const hi = await p.evaluate(() => LED.c.a.currentTime);
    return (lo >= 4.95 && lo < 5.6 && mid > 19 && mid < 21 && hi <= 27.8 && hi > 27 && !p.errs.length) || { lo, mid, hi };
  });
  await T('P7 the arrows go to the previous or next prayer (playing on if it was playing, not if it was paused); first has no previous; past the last starts a new shuffle', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'led');
    const d0 = await p.evaluate(() => document.querySelector('[data-ledgo="-1"]').disabled);
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing'); const id0 = await p.evaluate(() => ledCur().id);
    await p.click('[data-ledgo="1"]'); const on = await until(p, () => LED.c.state === 'playing'); const id1 = await p.evaluate(() => ({ id: ledCur().id, playing: LED.id }));
    await p.click('[data-ledpp]'); await wait(200); await p.click('[data-ledgo="-1"]'); await wait(400); const back = await p.evaluate(() => ({ id: ledCur().id, busy: LED.c.busy() }));
    const wrap = await p.evaluate(() => { const o = ledOrd(); o.p = o.o.length - 1; S.set('ledord', o); ledGo(1); const n = ledOrd(); return { p: n.p, uniq: new Set(n.o).size === n.o.length && n.o.length === ledList().length } });
    return (d0 && on && id1.id !== id0 && id1.playing === id1.id && back.id === id0 && !back.busy && wrap.p === 0 && wrap.uniq && !p.errs.length) || { d0, on, id0, id1, back, wrap };
  });
  await T('P8 the prayer stops within 0.15 s of its end, the ring full; the next tap prays it again from its start', async () => {
    const p = await pray_(await page()); await testAudio(p, { sb: 12, e: 10 }); await guided(p, 'led');   // 18 s → 20 s
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing');
    await until(p, () => LED.c.state === 'ended', 6000); const a = await p.evaluate(() => ({ t: LED.c.a.currentTime, end: LED.c.end, ring: $('#ledfg').getAttribute('stroke-dasharray'), done: LED.done, icon: document.querySelector('[data-ledpp]').getAttribute('aria-label') }));
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing'); const r = await p.evaluate(() => LED.c.a.currentTime);
    return (Math.abs(a.t - a.end) <= 0.15 && a.ring.startsWith('100') && a.done && a.icon === 'Pray' && r >= 18 && r < 18.6 && !p.errs.length) || { a, r };
  });
  await T('P9 speed steps 1× → 1.1× → 1.25× → 0.9× → 1× and applies at once, mid-prayer', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'led');
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing'); const seen = [];
    for (let i = 0; i < 4; i++) { await p.click('[data-ledsp]'); seen.push(await p.evaluate(() => [LED.sp, LED.c.a.playbackRate, document.querySelector('[data-ledsp]').textContent].join('/'))); }
    return seen.join(' ') === '1.1/1.1/1.1× 1.25/1.25/1.25× 0.9/0.9/0.9× 1/1/1×' || seen;
  });
  await T('P10 the soaking music plays under every prayer while Music is on (it really plays, at the Pray level), carries on ~7 s after the amen, and stops when Music is off', async () => {
    const p = await pray_(await page()); await testAudio(p, { sb: 12, e: 10 }); await guided(p, 'led');
    const none = await p.evaluate(() => document.querySelector('[data-prmu]').textContent);
    await music(p); await guided(p, 'led');
    const res = [];
    for (const own of [true, false]) {      // a prayer measured with and without music of its own: the music plays under both
      await p.evaluate(o => { ledList().forEach(x => x.music = o); BED.led = true; }, own);
      await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing');
      const on = await until(p, () => !BED.el.paused && BED.g && Math.abs(BED.g.gain.value - BED.plv) < 0.02, 6000);
      await p.evaluate(() => { LED.c.a.currentTime = LED.c.end - 0.3 }); await until(p, () => LED.c.state === 'ended', 4000);
      const tail = await p.evaluate(() => [bedWanted(), LED.tail, !BED.el.paused]);
      await p.evaluate(() => { LED.tail = false; clearTimeout(LED.tt); bedSync(); });
      res.push({ own, on, tail });
    }
    await p.evaluate(() => { BED.led = false; }); await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing');
    const off = await until(p, () => BED.el.paused, 6000);
    return (none.trim() === '♪ Music' && res.every(r => r.on && r.tail[0] && r.tail[1] && r.tail[2]) && off && !p.errs.length) || { none, res, off, e: p.errs };
  });
  await T('P27 the ♪ Music panel: opens and closes, switches the music on and off, and its level changes the music at once and is remembered (Be Led and Meditate)', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 20 }); await music(p); await guided(p, 'led');
    const shut = await p.evaluate(() => $('#prmu').hidden);
    await p.click('[data-prmu]'); const open = await p.evaluate(() => !$('#prmu').hidden && document.querySelector('[data-prmu]').getAttribute('aria-expanded') === 'true');
    await p.click('[data-ledpp]'); await until(p, () => !BED.el.paused && BED.g && BED.g.gain.value > 0.05, 6000);
    await p.evaluate(() => { const r = $('#prmulv'); r.value = 50; r.dispatchEvent(new Event('input')); }); await wait(400);
    const loud = await p.evaluate(() => [BED.plv, +BED.g.gain.value.toFixed(2), S.get('bedlvp')]);
    await p.click('#prmuon'); await until(p, () => BED.el.paused, 6000); const offTxt = await p.evaluate(() => [BED.led, document.querySelector('[data-prmu]').textContent, $('#prmulv').disabled]);
    await p.click('#prmuon'); const back = await until(p, () => !BED.el.paused, 6000);
    await p.click('[data-prmu]'); const closed = await p.evaluate(() => $('#prmu').hidden);
    await guided(p, 'med'); const medBtn = await p.evaluate(() => !!document.querySelector('[data-prmu]'));
    await p.click('[data-medgo]'); const medMusic = await until(p, () => MED.on && !BED.el.paused && Math.abs(BED.g.gain.value - 0.5) < 0.03, 8000);
    await p.reload(); await wait(1500); const kept = await p.evaluate(() => [BED.plv, BED.led]);
    return (shut && open && loud[0] === 0.5 && Math.abs(loud[1] - 0.5) < 0.03 && loud[2] === 0.5 && offTxt[0] === false && offTxt[1] === '♪ Music off' && offTxt[2] && back && closed && medBtn && medMusic && kept[0] === 0.5 && kept[1] === true && !p.errs.length) || { shut, open, loud, offTxt, back, closed, medBtn, medMusic, kept, e: p.errs };
  });
  await T('P11 a new day opens on a new prayer; a reload the same day keeps it; none repeats until all are prayed', async () => {
    const p = await pray_(await page()); await guided(p, 'led');
    const a = await p.evaluate(() => { const id = ledCur().id; const o = ledOrd(); const p0 = o.p; return { id, p0 } });
    await p.reload(); await wait(1500); await pray(p); const same = await p.evaluate(() => ledCur().id);
    const next = await p.evaluate(() => { const o = S.get('ledord'); o.d = dayNo() - 1; S.set('ledord', o); return { id: ledCur().id, p: ledOrd().p } });
    const all = await p.evaluate(() => { const o = ledOrd(); return new Set(o.o).size === ledList().length && o.o.length === ledList().length });
    return (same === a.id && next.id !== a.id && next.p === a.p0 + 1 && all) || { a, same, next, all };
  });

  // ── Meditate ────────────────────────────────────────────────────────────────────────────────────────────────────
  await T('P12 Begin → Listen → a breath → Again → Be still → Amen, each on screen', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'med');
    await p.click('[data-medgo]'); const seen = [];
    for (let k = 0; k < 120; k++) { const s = await p.evaluate(() => MED.step + ':' + $('#medeb').textContent); if (seen[seen.length - 1] !== s) seen.push(s); if (s.startsWith('still')) break; await wait(50); }
    const amen = await p.evaluate(() => !!document.querySelector('[data-medamen]')); await p.click('[data-medamen]'); await wait(200);
    const end = await p.evaluate(() => ({ step: MED.step, eb: $('#medeb').textContent, on: MED.on, begin: !!document.querySelector('[data-medgo]') }));
    const want = ['listen:Listen', 'pause:', 'again:Again', 'still:Be still'];
    return (want.every(w => seen.includes(w)) && amen && end.step === 'done' && end.eb === 'Amen' && !end.on && end.begin && !p.errs.length) || { seen, amen, end };
  });
  await T('P13 pause and go on during a reading; pause is off during the breath and the second reading still comes', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 9, fast: 0.3 }); await guided(p, 'med');
    await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing');
    await p.click('[data-medpp]'); await wait(200); const ps = await p.evaluate(() => ({ paused: MED.paused, st: MED.c.state, t: MED.c.a.currentTime }));
    await wait(500); await p.click('[data-medpp]'); await until(p, () => MED.c.state === 'playing'); const go = await p.evaluate(() => MED.c.a.currentTime);
    await until(p, () => MED.step === 'pause', 8000); const dis = await p.evaluate(() => document.querySelector('[data-medpp]').disabled);
    const again = await until(p, () => MED.step === 'again' && MED.c.state === 'playing', 8000);
    return (ps.paused && ps.st === 'paused' && go >= ps.t - 0.3 && go < ps.t + 1 && dis && again && !p.errs.length) || { ps, go, dis, again };
  });
  await T('P14 the arrows mid-reading stop it cleanly; the next saying starts fresh', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 12 }); await guided(p, 'med');
    const k0 = await p.evaluate(() => medIdx() === medList().length - 1 ? (MED.pick = medList()[0].ref, render(), medIdx()) : medIdx());
    await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing');
    await p.click('[data-medgo2="1"]'); await wait(300);
    const a = await p.evaluate(() => ({ k: medIdx(), on: MED.on, step: MED.step, paused: MED.c.a.paused, begin: !!document.querySelector('[data-medgo]') }));
    await p.click('[data-medgo]'); const fresh = await until(p, () => MED.step === 'listen' && MED.c.state === 'playing');
    return (a.k === k0 + 1 && !a.on && a.step === '' && a.paused && a.begin && fresh && !p.errs.length) || { k0, a, fresh };
  });
  await T('P15 each reading stops within 0.15 s of its end (no next words)', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 7.3, fast: 0.05 }); await guided(p, 'med');
    await p.click('[data-medgo]'); await until(p, () => MED.step === 'pause', 6000); const t1 = await p.evaluate(() => MED.c.a.currentTime);
    await until(p, () => MED.step === 'still', 8000); const t2 = await p.evaluate(() => MED.c.a.currentTime);
    return (Math.abs(t1 - 7.3) <= 0.15 && Math.abs(t2 - 7.3) <= 0.15) || { t1, t2 };
  });
  await T('P16 Meditate speed steps 1× → 0.9× → 0.8× → 1.1× → 1.25× → 1×, applies to both readings at once, and is remembered', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 14 }); await guided(p, 'med');
    await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing'); const seen = [];
    for (let i = 0; i < 5; i++) { await p.click('[data-medsp]'); seen.push(await p.evaluate(() => [MED.sp, MED.c.a.playbackRate].join('/'))); }
    await p.click('[data-medsp]'); await p.evaluate(() => medStop(false)); await p.reload(); await wait(1500);
    const kept = await p.evaluate(() => MED.sp);
    return (seen.join(' ') === '0.9/0.9 0.8/0.8 1.1/1.1 1.25/1.25 1/1' && kept === 0.9) || { seen, kept };
  });
  await T('P17 a reading that will not load retries once, then says so, and Begin works again; a slow one shows Loading… then plays', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'med');
    await p.evaluate(() => { medCur().audio = 'https://no-such-host.invalid/reading.mp3'; });
    await p.click('[data-medgo]'); const err = await until(p, () => MED.step === 'err', 40000);
    const say = await p.evaluate(() => ({ eb: $('#medeb').textContent, on: MED.on, begin: !!document.querySelector('[data-medgo]') }));
    await p.evaluate(() => { medCur().audio = TESTWAV; }); await p.click('[data-medgo]'); const ok = await until(p, () => MED.c.state === 'playing');
    // slow: the recording answers after 5 s
    await p.evaluate(() => medStop(false));
    const body = Buffer.from(await p.evaluate(async () => [...new Uint8Array(await (await fetch(TESTWAV)).arrayBuffer())]));
    const srv = require('http').createServer((q, r) => setTimeout(() => { r.writeHead(200, { 'Content-Type': 'audio/wav', 'Content-Length': body.length, 'Access-Control-Allow-Origin': '*' }); r.end(body); }, 5000));
    await new Promise(ok => srv.listen(8799, ok));
    await p.evaluate(() => { medCur().audio = 'http://localhost:8799/slow-reading.wav'; });
    await p.click('[data-medgo]'); const loading = await until(p, () => $('#medeb').textContent === 'Loading…', 6000); const played = await until(p, () => MED.c.state === 'playing', 15000);
    srv.close(); return (err && /didn't load/.test(say.eb) && !say.on && say.begin && ok && loading && played && !p.errs.length) || { err, say, ok, loading, played, e: p.errs };
  });
  await T('P18 every saying: Begin is in view and not covered at 390×760 (no scrolling), reachable at 375×600; the arrows walk all of them', async () => {
    const bad = [];
    for (const vp of [{ width: 390, height: 760 }, { width: 375, height: 600 }]) {
      const p = await pray_(await page(vp)); await guided(p, 'med');
      const n = await p.evaluate(() => medList().length);
      await p.evaluate(() => { MED.pick = medList()[0].ref; render(); });
      for (let k = 0; k < n; k++) {
        const r = await p.evaluate(small => { const g = document.querySelector('[data-medgo]'); if (small) g.scrollIntoView({ block: 'center' }); const q = g.getBoundingClientRect(), t = document.querySelector('#tabs').getBoundingClientRect();
          const top = document.elementFromPoint(q.x + q.width / 2, q.y + q.height / 2); return { k: medIdx(), ref: medCur().ref, bottom: Math.round(q.bottom), tabs: Math.round(t.top), mine: top === g || g.contains(top) }; }, vp.height < 700);
        if (r.k !== k || !r.mine || r.bottom > r.tabs || (vp.height >= 700 && r.bottom > r.tabs)) bad.push({ vp: vp.height, ...r });
        if (k < n - 1) { await p.click('[data-medgo2="1"]'); await wait(80); }
      }
      await p.context().close();
    }
    return !bad.length || bad.slice(0, 6);
  });

  // ── The Lord's Prayer and Stillness ─────────────────────────────────────────────────────────────────────────────
  await T('P19 the Lord\'s Prayer: the arrows (and a swipe) move through the movements; another passage turns; Skip Heitzig\'s line is there', async () => {
    const p = await pray_(await page(null, { hasTouch: true })); await guided(p, 'guided');
    const n = await p.evaluate(() => PRAY.moves.length); const mv = [];
    for (let i = 0; i < n - 1; i++) { await p.click('[data-prmv="1"]'); await wait(120); mv.push(await p.evaluate(() => PR.mv)); }
    const lastOff = await p.evaluate(() => document.querySelector('[data-prmv="1"]').disabled);
    await p.click('[data-prmv="-1"]'); await wait(120); const backOne = await p.evaluate(() => PR.mv);
    let swipe = 'skipped';
    try {
      swipe = await p.evaluate(async () => { const g = $('#pray'), k = PR.mv, mk = (x) => new Touch({ identifier: 1, target: g, clientX: x, clientY: 400 });
        g.dispatchEvent(new TouchEvent('touchstart', { touches: [mk(300)], bubbles: true })); g.dispatchEvent(new TouchEvent('touchmove', { touches: [mk(150)], bubbles: true })); g.dispatchEvent(new TouchEvent('touchend', { touches: [], bubbles: true }));
        await new Promise(r => setTimeout(r, 200)); return PR.mv === k + 1 || PR.mv === k; });
    } catch (e) { swipe = 'skipped'; }
    const t0 = await p.evaluate(() => $('#prst').textContent); await p.click('#prsr'); await until(p, t => $('#prst').textContent !== t, 3000, t0); const t1 = await p.evaluate(() => $('#prst').textContent);
    const lp = await p.evaluate(() => /^Pray it with Skip Heitzig$/.test((document.querySelector('[data-lpp]') || {}).textContent || ''));
    return (mv.join() === [...Array(n - 1).keys()].map(i => i + 1).join() && lastOff && backOne === n - 2 && swipe !== false && (t1 !== t0 || (await p.evaluate(() => PRAY.moves[PR.mv].sup.length)) < 2) && lp && !p.errs.length) || { mv, lastOff, backOne, swipe, t0, t1, lp };
  });
  await T('P20 Stillness: with no music on the phone it says how to get it; with music it plays, pauses and skips', async () => {
    const p = await pray_(await page());
    const none = await p.evaluate(() => (document.querySelector('[data-mbst]') || {}).textContent || '');
    await testAudio(p); await music(p);
    await until(p, () => !!document.querySelector('[data-pms]'), 5000); await wait(500); await p.click('[data-pm]'); const on = await until(p, () => !pmEl().paused);
    await p.click('[data-pms="1"]'); await wait(400); const k = await p.evaluate(() => PM.k);
    await p.click('[data-pm]'); await wait(200); const off = await p.evaluate(() => pmEl().paused);
    return (/Backup|music/i.test(none) && on && k === 1 && off && !p.errs.length) || { none, on, k, off, e: p.errs };
  });

  // ── Pray against the other players ──────────────────────────────────────────────────────────────────────────────
  await T('P21 a sermon and a prayer never play together: Be Led pauses the sermon and a sermon pauses Be Led; the same for Meditate and Stillness', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'led');
    await p.evaluate(() => { audio.src = TESTWAV; audio.play() }); await until(p, () => !audio.paused);
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing'); const a = await p.evaluate(playing);
    await p.evaluate(() => audio.play()); await until(p, () => !audio.paused); await wait(300); const b1 = await p.evaluate(() => ({ pl: playing(), led: LED.c.state }));
    await guided(p, 'med'); await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing'); const c = await p.evaluate(playing);
    await p.evaluate(() => audio.play()); await wait(400); const d = await p.evaluate(() => ({ pl: playing(), on: MED.on }));
    return (a.join() === 'ledm' && b1.pl.join() === 'audio' && b1.led === 'paused' && c.join() === 'medm' && d.pl.join() === 'audio' && !d.on && !p.errs.length) || { a, b1, c, d };
  });
  await T('P22 Be Led then Begin in Meditate stops Be Led; Meditate then the ring in Be Led stops Meditate', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 15 }); await guided(p, 'led');
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing');
    await guided(p, 'med'); await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing'); const a = await p.evaluate(() => ({ pl: playing(), led: LED.c.state }));
    await guided(p, 'led'); await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing'); await wait(200); const b2 = await p.evaluate(() => ({ pl: playing(), med: MED.on }));
    return (a.pl.join() === 'medm' && a.led === 'paused' && b2.pl.join() === 'ledm' && !b2.med && !p.errs.length) || { a, b2 };
  });
  await T('P23 leaving Pray mid-prayer keeps it playing; coming back shows the pause icon and the ring where it is', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'led');
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing'); await wait(600);
    await p.evaluate(() => { $('#tabs [data-tab2=journey]').click(); }); await wait(700); const away = await p.evaluate(() => LED.c.state);
    await pray(p); await wait(300); const back = await p.evaluate(() => ({ icon: document.querySelector('[data-ledpp]').getAttribute('aria-label'), ring: parseFloat($('#ledfg').getAttribute('stroke-dasharray')) }));
    return (away === 'playing' && back.icon === 'Pause' && back.ring > 0 && !p.errs.length) || { away, back };
  });
  await T('P24 the lock screen and earbuds: pause, play, back and on 15 s, previous and next for Be Led; pause and play for Meditate', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'led');
    if (!(await p.evaluate(() => 'mediaSession' in navigator && !!window.MediaSession))) return true;   // an engine without lock-screen controls
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing');
    await p.evaluate(() => __MS.pause()); await wait(200); const ps = await p.evaluate(() => LED.c.state);
    await p.evaluate(() => __MS.play()); await until(p, () => LED.c.state === 'playing'); await wait(400); const t = await p.evaluate(() => LED.c.a.currentTime);
    await p.evaluate(() => __MS.seekforward()); await wait(400); const f = await p.evaluate(() => LED.c.a.currentTime);
    await p.evaluate(() => __MS.seekbackward()); await wait(400); const bk = await p.evaluate(() => LED.c.a.currentTime);
    const id0 = await p.evaluate(() => ledCur().id); await p.evaluate(() => __MS.nexttrack()); await until(p, () => LED.c.state === 'playing'); const id1 = await p.evaluate(() => ledCur().id);
    await p.evaluate(() => __MS.previoustrack()); await wait(300); const id2 = await p.evaluate(() => ledCur().id);
    await guided(p, 'med'); await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing');
    await p.evaluate(() => __MS.pause()); await wait(200); const mp = await p.evaluate(() => MED.paused);
    await p.evaluate(() => __MS.play()); const mg = await until(p, () => MED.c.state === 'playing');
    return (ps === 'paused' && f > t + 5 && bk < f - 5 && id1 !== id0 && id2 === id0 && mp && mg && !p.errs.length) || { ps, t, f, bk, id0, id1, id2, mp, mg };
  });
  await T('P25 the app going to the background and back mid-prayer: it plays on and the screen catches up', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'led');
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing');
    await p.evaluate(() => { Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
    await wait(800); await p.evaluate(() => { Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
    await wait(300); const a = await p.evaluate(() => ({ st: LED.c.state, icon: document.querySelector('[data-ledpp]').getAttribute('aria-label') }));
    return (a.st === 'playing' && a.icon === 'Pause' && !p.errs.length) || { a, e: p.errs };
  });
  await T('P26 Be Led at a small screen (375×600): the ring and its buttons are reachable and not covered by the arrows', async () => {
    const p = await pray_(await page({ width: 375, height: 600 })); await guided(p, 'led');
    const r = await p.evaluate(() => { const g = document.querySelector('[data-ledpp]'); g.scrollIntoView({ block: 'center' }); const q = g.getBoundingClientRect(); const top = document.elementFromPoint(q.x + q.width / 2, q.y + q.height / 2); return g === top || g.contains(top); });
    return r;
  });

  await T('P28 swiping left or right goes to the next or previous in every part of Pray; a swipe from the screen\'s edge or on the music panel does nothing', async () => {
    const p = await pray_(await page(null, { hasTouch: true })); await testAudio(p); await music(p);
    const sw = (x0, x1, sel) => p.evaluate(([x0, x1, sel]) => { const g = sel ? document.querySelector(sel) : $('#pray'); const mk = x => new Touch({ identifier: 1, target: g, clientX: x, clientY: 420 });
      g.dispatchEvent(new TouchEvent('touchstart', { touches: [mk(x0)], bubbles: true })); g.dispatchEvent(new TouchEvent('touchmove', { touches: [mk(x1)], bubbles: true })); g.dispatchEvent(new TouchEvent('touchend', { touches: [], bubbles: true })); }, [x0, x1, sel || null]);
    try { await p.evaluate(() => new Touch({ identifier: 1, target: document.body, clientX: 1, clientY: 1 })); } catch (e) { return true; }   // an engine without touch events here
    const out = {};
    await guided(p, 'led'); const l0 = await p.evaluate(() => ledOrd().p); await sw(300, 120); await wait(250); const l1 = await p.evaluate(() => ledOrd().p); await sw(120, 300); await wait(250); const l2 = await p.evaluate(() => ledOrd().p);
    await sw(10, 200); await wait(200); const edge = await p.evaluate(() => ledOrd().p);
    await p.click('[data-prmu]'); await sw(300, 120, '#prmu'); await wait(200); const panel = await p.evaluate(() => ledOrd().p);
    out.led = [l0, l1, l2, edge, panel];
    await guided(p, 'med'); await p.evaluate(() => { MED.pick = medList()[0].ref; render(); }); await sw(300, 120); await wait(250); const m1 = await p.evaluate(() => medIdx()); await sw(120, 300); await wait(250); out.med = [m1, await p.evaluate(() => medIdx())];
    await guided(p, 'guided'); await p.evaluate(() => { PR.mv = 0; render(); }); await sw(300, 120); await wait(250); const g1 = await p.evaluate(() => PR.mv); await sw(120, 300); await wait(250); out.lp = [g1, await p.evaluate(() => PR.mv)];
    await p.click('[data-prtop=still]'); await wait(300); const k0 = await p.evaluate(() => PM.k); await sw(300, 120); await wait(500); out.still = [k0, await p.evaluate(() => PM.k)];
    return (out.led.join() === [l0, l0 + 1, l0, l0, l0].join() && out.med.join() === '1,0' && out.lp.join() === '1,0' && out.still[1] === (out.still[0] + 1) % 2 && !p.errs.length) || out;
  });
  await T('P29 Meditate\'s music plays through Listen, the breath, Again and Be still; if something pauses it mid-reading it comes back; with Music off it stays silent', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 8, fast: 0.4 }); await music(p); await guided(p, 'med');
    await p.click('[data-medgo]'); const seen = {};
    for (let k = 0; k < 200; k++) { const r = await p.evaluate(() => [MED.step, !BED.el.paused && BED.g && BED.g.gain.value > 0.05]); if (r[1]) seen[r[0]] = true; if (r[0] === 'still' && seen.still) break; await wait(50); }
    await p.click('[data-medamen]'); await wait(300);
    await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing' && !BED.el.paused, 6000);
    await p.evaluate(() => BED.el.pause()); const back = await until(p, () => !BED.el.paused, 2500);
    await p.evaluate(() => medStop(false)); await p.evaluate(() => { BED.led = false; }); await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing');
    const off = await until(p, () => BED.el.paused, 5000);
    const why = await p.evaluate(() => ({ src: (BED.el.getAttribute('src') || '').slice(0, 30), paused: BED.el.paused, gain: BED.g && BED.g.gain.value, ctx: BED.ctx && BED.ctx.state, led: BED.led, list: (PL.list || []).length, rts: BED.rts, err: BED.el.error && BED.el.error.code }));
    return (seen.listen && seen.again && seen.still && back && off && !p.errs.length) || { seen, back, off, why, e: p.errs };
  });
  await T('P30 the Lord\'s Prayer with Skip Heitzig: "Pray it with" plays him here; the movements follow; the arrows go to a movement in his prayer; pause, music and a clean end', async () => {
    const p = await pray_(await page()); await testAudio(p); await music(p);
    await p.evaluate(() => { PRAY.lp.audio = TESTWAV; PRAY.lp.a = 2; PRAY.lp.b = 26; PRAY.lp.at = [2, 4, 6, 14, 18, 22]; PR.mv = 0; });
    await guided(p, 'guided');
    const line = await p.evaluate(() => document.querySelector('[data-lpp]').textContent);
    const step = { at: 'start' }; const click = async (sel, name) => { step.at = name; await p.click(sel, { timeout: 8000 }); };
    try {
    await click('[data-lpp]', 'play'); await until(p, () => LP.c.state === 'playing'); const t0 = await p.evaluate(() => LP.c.a.currentTime);
    const follow = await until(p, () => PR.mv >= 2, 8000); const music_ = await p.evaluate(() => !BED.el.paused && BED.g.gain.value > 0.05);
    await click('[data-prmv="1"]', 'next movement'); await wait(300); const seek = await p.evaluate(() => [PR.mv, LP.c.a.currentTime]);   // to the next movement: 14 s
    await click('[data-lpp]', 'pause'); await wait(200); const paused = await p.evaluate(() => [LP.c.state, document.querySelector('[data-lpp]').getAttribute('aria-label')]);
    await click('[data-lpp]', 'play again'); await until(p, () => LP.c.state === 'playing');
    await p.evaluate(() => { LP.c.a.currentTime = 24.5 }); const ended = await until(p, () => LP.c.state === 'ended', 10000); const end = await p.evaluate(() => [LP.c.a.currentTime, PR.mv, LP.done]);
    return (line === 'Pray it with Skip Heitzig' && Math.abs(t0 - 2) < 0.5 && follow && music_ && seek[1] >= 13.9 && seek[0] === 3 && paused[0] === 'paused' && ended && Math.abs(end[0] - 26) <= 0.2 && end[1] === 5 && end[2] && !p.errs.length) || { line, t0, follow, music_, seek, paused, ended, end, e: p.errs };
    } catch (e) { return { failedAt: step.at, error: String(e).slice(0, 160), state: await p.evaluate(() => ({ lp: LP.c && LP.c.state, t: LP.c && LP.c.a.currentTime, mv: PR.mv, mode: PR.mode, btn: !!document.querySelector('[data-lpp]') })) }; }
  });
  await T('P31 the ‹ › arrows are in view without scrolling at 390×760: Be Led with the music panel open, every Meditate saying, and the Lord\'s Prayer', async () => {
    const p = await pray_(await page()); await testAudio(p); await music(p); const bad = [];
    const vis = (sel) => p.evaluate(sel => [...document.querySelectorAll(sel)].map(b => { const r = b.getBoundingClientRect(), t = document.querySelector('#tabs').getBoundingClientRect(), top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return r.top >= 0 && r.bottom <= t.top && (top === b || b.contains(top)); }), sel);
    await guided(p, 'led'); await p.click('[data-prmu]'); if ((await vis('[data-ledgo]')).some(v => !v)) bad.push('led');
    await guided(p, 'med'); const n = await p.evaluate(() => medList().length);
    for (let k = 0; k < n; k++) { await p.evaluate(k => { MED.pick = medList()[k].ref; MED.step = ''; render(); window.scrollTo(0, 0) }, k); if ((await vis('[data-medgo2]')).some(v => !v)) bad.push('med ' + k); }
    await guided(p, 'guided'); if ((await vis('[data-prmv]')).some(v => !v)) bad.push('lp');
    return !bad.length || bad;
  });
  const f = R.filter(r => !r[1].startsWith('PASS')).length; console.log(`\n${R.length - f}/${R.length} passed`); await b.close(); process.exit(f ? 1 : 0);
})().catch(e => { console.log(R.map(r => r.join(' ')).join('\n')); console.error(e); process.exit(1); });

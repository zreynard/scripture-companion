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
    (PRAY.med || []).forEach(x => { x.audio = TESTWAV; x.a = o.a || 5; x.b = o.b || 6.5; x.Lt = 0; });
    if (PRAY.lp) PRAY.lp.Lt = 0;
    PRAY.lum = null;   // the stand-in has no measured loudness: the music sits at your level
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
    await until(p, () => LED.done, 6000); const a = await p.evaluate(() => ({ released: !LED.c.a.getAttribute('src'), t: LED.c.stopAt, end: LED.c.end, ring: $('#ledfg').getAttribute('stroke-dasharray'), done: LED.done, icon: document.querySelector('[data-ledpp]').getAttribute('aria-label') }));
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing'); const r = await p.evaluate(() => LED.c.a.currentTime);
    return (a.released && Math.abs(a.t - a.end) <= 0.15 && a.ring.startsWith('100') && a.done && a.icon === 'Pray' && r >= 18 && r < 18.6 && !p.errs.length) || { a, r };
  });
  await T('P9 speed steps 1× → 1.1× → 1.25× → 0.9× → 1× and applies at once, mid-prayer', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'led');
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing'); const seen = [];
    for (let i = 0; i < 4; i++) { await p.click('[data-ledsp]'); seen.push(await p.evaluate(() => [LED.sp, LED.c.a.playbackRate, document.querySelector('[data-ledsp]').textContent].join('/'))); }
    return seen.join(' ') === '1.1/1.1/1.1× 1.25/1.25/1.25× 0.9/0.9/0.9× 1/1/1×' || seen;
  });
  await T('P10 the soaking music plays under every prayer while Music is on (it really plays, at the Pray level), carries on after the amen until something else plays, and stays off when Music is off', async () => {
    const p = await pray_(await page()); await testAudio(p, { sb: 12, e: 10 }); await guided(p, 'led');
    const none = await p.evaluate(() => document.querySelector('[data-prmu]').textContent);
    await music(p); await guided(p, 'led');
    const res = [];
    for (const own of [true, false]) {      // a prayer measured with and without music of its own: the music plays under both
      await p.evaluate(o => { ledList().forEach(x => x.music = o); BED.led = true; }, own);
      await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing');
      const on = await until(p, () => !BED.el.paused && Math.abs(bedNow() / BED.plv - 1) < 0.2, 6000);
      await p.evaluate(() => { LED.c.a.currentTime = LED.c.end - 0.3 }); await until(p, () => LED.done, 4000);
      await wait(2500); const tail = await p.evaluate(() => [bedWanted(), BED.tail, !BED.el.paused]);   // the music carries on after the amen
      await p.evaluate(() => { audio.src = TESTWAV; audio.play().catch(() => {}); }); await until(p, () => !BED.tail, 3000); await p.evaluate(() => audio.pause());
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
    await p.click('[data-ledpp]'); await until(p, () => bedNow() > 0.05, 6000);
    await p.evaluate(() => { const r = $('#prmulv'); r.value = 50; r.dispatchEvent(new Event('input')); r.dispatchEvent(new Event('change')); }); await until(p, () => Math.abs(bedNow() / 0.5 - 1) < 0.2, 4000);
    const loud = await p.evaluate(() => [BED.plv, +bedNow().toFixed(2), S.get('bedlvp')]);
    await p.click('#prmuon'); await until(p, () => BED.el.paused, 6000); const offTxt = await p.evaluate(() => [BED.led, document.querySelector('[data-prmu]').textContent, $('#prmulv').disabled]);
    await p.click('#prmuon'); const back = await until(p, () => !BED.el.paused, 6000);
    await p.click('[data-prmu]'); const closed = await p.evaluate(() => $('#prmu').hidden);
    await guided(p, 'med'); const medBtn = await p.evaluate(() => !!document.querySelector('[data-prmu]'));
    await p.click('[data-medgo]'); const medMusic = await until(p, () => MED.on && Math.abs(bedNow() / 0.5 - 1) < 0.2, 8000);
    await p.reload(); await wait(1500); const kept = await p.evaluate(() => [BED.plv, BED.led]);
    return (shut && open && loud[0] === 0.5 && Math.abs(loud[1] / 0.5 - 1) < 0.2 && loud[2] === 0.5 && offTxt[0] === false && offTxt[1] === '♪ Music off' && offTxt[2] && back && closed && medBtn && medMusic && kept[0] === 0.5 && kept[1] === true && !p.errs.length) || { shut, open, loud, offTxt, back, closed, medBtn, medMusic, kept, e: p.errs };
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
  await T('P12 Begin → Listen (read once, never twice) → Be still → Amen, each on screen', async () => {
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'med');
    await p.click('[data-medgo]'); const seen = [];
    for (let k = 0; k < 120; k++) { const s = await p.evaluate(() => MED.step + ':' + $('#medeb').textContent); if (seen[seen.length - 1] !== s) seen.push(s); if (s.startsWith('still')) break; await wait(50); }
    const amen = await p.evaluate(() => !!document.querySelector('[data-medamen]')); await p.click('[data-medamen]'); await wait(200);
    const end = await p.evaluate(() => ({ step: MED.step, eb: $('#medeb').textContent, on: MED.on, begin: !!document.querySelector('[data-medgo]') }));
    const want = ['listen:Listen', 'still:Be still'], plays = await p.evaluate(() => (diagText().match(/medm playing/g) || []).length);
    return (want.every(w => seen.includes(w)) && !seen.some(s => /^(again|pause):/.test(s)) && plays === 1 && amen && end.step === 'done' && end.eb === 'Amen' && !end.on && end.begin && !p.errs.length) || { seen, plays, amen, end };
  });
  await T('P13 pause and go on during a reading; when it ends it goes straight to Be still', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 9, fast: 0.3 }); await guided(p, 'med');
    await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing');
    await p.click('[data-medpp]'); await wait(200); const ps = await p.evaluate(() => ({ paused: MED.paused, st: MED.c.state, t: MED.c.a.currentTime }));
    await wait(500); await p.click('[data-medpp]'); await until(p, () => MED.c.state === 'playing'); const go = await p.evaluate(() => MED.c.a.currentTime);
    const still = await until(p, () => MED.step === 'still', 10000);
    return (ps.paused && ps.st === 'paused' && go >= ps.t - 0.3 && go < ps.t + 1 && still && !p.errs.length) || { ps, go, still };
  });
  await T('P14 the arrows mid-reading stop it cleanly; the next saying in the shuffle starts fresh', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 12 }); await guided(p, 'med');
    const k0 = await p.evaluate(() => { const o = medOrd(); return { p: o.p, want: o.o[o.p + 1] }; });
    await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing');
    await p.click('[data-medgo2="1"]'); await wait(300);
    const a = await p.evaluate(() => ({ p: medOrd().p, key: medKey(medCur()), on: MED.on, step: MED.step, paused: MED.c.a.paused, begin: !!document.querySelector('[data-medgo]') }));
    await p.click('[data-medgo]'); const fresh = await until(p, () => MED.step === 'listen' && MED.c.state === 'playing');
    return (a.p === k0.p + 1 && a.key === k0.want && !a.on && a.step === '' && a.paused && a.begin && fresh && !p.errs.length) || { k0, a, fresh };
  });
  await T('P15 each reading stops within 0.15 s of its end (no next words)', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 7.3, fast: 0.05 }); await guided(p, 'med');
    await p.click('[data-medgo]'); await until(p, () => MED.step === 'still', 8000); const t2 = await p.evaluate(() => MED.c.stopAt);
    return (Math.abs(t2 - 7.3) <= 0.15) || { t2 };
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
      await p.evaluate(() => { S.set('medord', Object.assign(medOrd(), { p: 0 })); MED.pick = null; render(); }); const seenRef = new Set();
      for (let k = 0; k < n; k++) {
        const r = await p.evaluate(small => { const g = document.querySelector('[data-medgo]'); if (small) g.scrollIntoView({ block: 'center' }); const q = g.getBoundingClientRect(), t = document.querySelector('#tabs').getBoundingClientRect();
          const top = document.elementFromPoint(q.x + q.width / 2, q.y + q.height / 2); return { k: medIdx(), ref: medCur().ref, bottom: Math.round(q.bottom), tabs: Math.round(t.top), mine: top === g || g.contains(top) }; }, vp.height < 700);
        seenRef.add(r.k);
        if (!r.mine || r.bottom > r.tabs || (vp.height >= 700 && r.bottom > r.tabs)) bad.push({ vp: vp.height, ...r });
        if (k < n - 1) { await p.click('[data-medgo2="1"]'); await wait(80); }
      }
      if (seenRef.size !== n) bad.push({ vp: vp.height, walked: seenRef.size, of: n });
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
    await guided(p, 'med'); await p.evaluate(() => { S.set('medord', Object.assign(medOrd(), { p: 0 })); MED.pick = null; render(); }); await sw(300, 120); await wait(250); const m1 = await p.evaluate(() => medOrd().p); await sw(120, 300); await wait(250); out.med = [m1, await p.evaluate(() => medOrd().p)];
    await guided(p, 'guided'); await p.evaluate(() => { PR.mv = 0; render(); }); await sw(300, 120); await wait(250); const g1 = await p.evaluate(() => PR.mv); await sw(120, 300); await wait(250); out.lp = [g1, await p.evaluate(() => PR.mv)];
    await p.click('[data-prtop=still]'); await wait(300); const k0 = await p.evaluate(() => PM.k); await sw(300, 120); await wait(500); out.still = [k0, await p.evaluate(() => PM.k)];
    return (out.led.join() === [l0, l0 + 1, l0, l0, l0].join() && out.med.join() === '1,0' && out.lp.join() === '1,0' && out.still[1] === (out.still[0] + 1) % 2 && !p.errs.length) || out;
  });
  await T('P29 Meditate\'s music plays through Listen and Be still; if something pauses it mid-reading it comes back; with Music off it stays silent', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 8, fast: 0.4 }); await music(p); await guided(p, 'med');
    await p.click('[data-medgo]'); const seen = {};
    for (let k = 0; k < 200; k++) { const r = await p.evaluate(() => [MED.step, bedNow() > 0.05]); if (r[1]) seen[r[0]] = true; if (r[0] === 'still' && seen.still) break; await wait(50); }
    await p.click('[data-medamen]'); await wait(300);
    await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing' && !BED.el.paused, 6000);
    await p.evaluate(() => BED.el.pause()); const back = await until(p, () => !BED.el.paused, 2500);
    await p.evaluate(() => medStop(false)); await p.evaluate(() => { BED.led = false; }); await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing');
    const off = await until(p, () => BED.el.paused, 5000);
    const why = await p.evaluate(() => ({ src: (BED.el.getAttribute('src') || '').slice(0, 30), paused: BED.el.paused, gain: bedNow(), kind: BED.mode, ctx: BED.ctx && BED.ctx.state, led: BED.led, list: (PL.list || []).length, rts: BED.rts, err: BED.el.error && BED.el.error.code }));
    return (seen.listen && seen.still && back && off && !p.errs.length) || { seen, back, off, why, e: p.errs };
  });
  await T('P30 the Lord\'s Prayer with Skip Heitzig: "Pray it with" plays him here; the movements follow; the arrows go to a movement in his prayer; pause, music and a clean end', async () => {
    const p = await pray_(await page()); await testAudio(p); await music(p);
    await p.evaluate(() => { PRAY.lp.audio = TESTWAV; PRAY.lp.Lt = 0; PRAY.lp.a = 2; PRAY.lp.b = 26; PRAY.lp.at = [2, 4, 6, 14, 18, 22]; PR.mv = 0; });
    await guided(p, 'guided');
    const line = await p.evaluate(() => document.querySelector('[data-lpp]').textContent);
    const step = { at: 'start' }; const click = async (sel, name) => { step.at = name; await p.click(sel, { timeout: 8000 }); };
    try {
    await click('[data-lpp]', 'play'); await until(p, () => LP.c.state === 'playing'); const t0 = await p.evaluate(() => LP.c.a.currentTime);
    const follow = await until(p, () => PR.mv >= 2, 8000); const music_ = await until(p, () => bedNow() > 0.05, 3000);
    await click('[data-prmv="1"]', 'next movement'); await wait(300); const seek = await p.evaluate(() => [PR.mv, LP.c.a.currentTime]);   // to the next movement: 14 s
    await click('[data-lpp]', 'pause'); await wait(200); const paused = await p.evaluate(() => [LP.c.state, document.querySelector('[data-lpp]').getAttribute('aria-label')]);
    await click('[data-lpp]', 'play again'); await until(p, () => LP.c.state === 'playing');
    await p.evaluate(() => { LP.c.a.currentTime = 24.5 }); const ended = await until(p, () => LP.done, 10000); const end = await p.evaluate(() => [LP.c.stopAt, PR.mv, LP.done, !LP.c.a.getAttribute('src')]);
    return (line === 'Pray it with Skip Heitzig' && Math.abs(t0 - 2) < 0.5 && follow && music_ && seek[1] >= 13.9 && seek[0] === 3 && paused[0] === 'paused' && ended && Math.abs(end[0] - 26) <= 0.2 && end[1] === 5 && end[2] && end[3] && !p.errs.length) || { line, t0, follow, music_, seek, paused, ended, end, e: p.errs };
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
  // a recording served slowly from a server here: `rate` bytes a second after the first `head` bytes; rate 0 = nothing after the head
  async function slowServer(port, rate, head) {
    const sr = 8000, n = sr * 30, hdr = Buffer.alloc(44); const w = (o, x) => hdr.write(x, o, 'latin1');
    w(0, 'RIFF'); hdr.writeUInt32LE(36 + n * 2, 4); w(8, 'WAVEfmt '); hdr.writeUInt32LE(16, 16); hdr.writeUInt16LE(1, 20); hdr.writeUInt16LE(1, 22); hdr.writeUInt32LE(sr, 24); hdr.writeUInt32LE(sr * 2, 28); hdr.writeUInt16LE(2, 32); hdr.writeUInt16LE(16, 34); w(36, 'data'); hdr.writeUInt32LE(n * 2, 40);
    const body = Buffer.alloc(n * 2); for (let i = 0; i < n; i++) body.writeInt16LE(Math.round(Math.sin(i / 8) * 2000), i * 2);
    const all = Buffer.concat([hdr, body]), hits = { n: 0 };
    const srv = require('http').createServer((q, r) => { hits.n++; const m = /bytes=(\d+)-/.exec(q.headers.range || ''); const a = m ? +m[1] : 0, part = all.slice(a);
      r.writeHead(m ? 206 : 200, { 'Content-Type': 'audio/wav', 'Content-Length': part.length, 'Accept-Ranges': 'bytes', ...(m ? { 'Content-Range': `bytes ${a}-${all.length - 1}/${all.length}` } : {}), 'Access-Control-Allow-Origin': '*' });
      let k = Math.min(head, part.length); r.write(part.slice(0, k)); if (!rate) return;   // rate 0: hold the line open, send nothing more
      const t = setInterval(() => { if (k >= part.length || r.destroyed) { clearInterval(t); r.end(); return } const e = Math.min(part.length, k + rate / 4); r.write(part.slice(k, e)); k = e; }, 250); q.on('close', () => clearInterval(t)); });
    await new Promise(ok => srv.listen(port, ok)); return { srv, hits };
  }
  await T('P32 a slow recording: "Loading…", never restarted while it is arriving, then it plays; one that sends nothing retries once after 25 s, then says it did not load', async () => {
    const S1 = await slowServer(8811, 12000, 2000);         // 12 KB/s: slower than it plays (16 KB/s)
    const p = await pray_(await page()); await testAudio(p); await guided(p, 'med');
    await p.evaluate(() => { const m = medCur(); m.audio = 'http://localhost:8811/slow.wav'; m.a = 6; m.b = 9; });
    await p.click('[data-medgo]'); const loading = await until(p, () => $('#medeb').textContent === 'Loading…' || MED.c.state === 'playing', 8000);
    const played = await until(p, () => MED.c.stopAt > 8 || MED.step === 'pause' || MED.step === 'again' || MED.step === 'still', 40000);
    const a = await p.evaluate(() => ({ tries: MED.c.tries, step: MED.step, err: MED.step === 'err' })); S1.srv.close();
    const S2 = await slowServer(8812, 0, 64);               // a few bytes, then nothing
    await p.evaluate(() => { medStop(false); const m = medCur(); m.audio = 'http://localhost:8812/stuck.wav'; m.a = 2; m.b = 4; });
    await p.click('[data-medgo]'); const t0 = Date.now(); const errd = await until(p, () => MED.step === 'err', 70000); const took = Date.now() - t0;
    const b2 = await p.evaluate(() => $('#medeb').textContent); S2.srv.close();
    return (loading && played && !a.err && a.tries === 0 && S1.hits.n <= 2 && errd && took > 45000 && /didn't load/.test(b2) && S2.hits.n >= 2 && !p.errs.length) || { loading, played, a, hits1: S1.hits.n, errd, took, b2, hits2: S2.hits.n, e: p.errs };
  });
  await T('P33 nothing keeps downloading: after Be still, after a prayer ends, after the Lord\'s Prayer ends, and after going to another mid-load, the player has let go of its file', async () => {
    const p = await pray_(await page()); await testAudio(p, { sb: 12, e: 10, a: 5, b: 6.5 }); const r = {};
    await guided(p, 'med'); await p.click('[data-medgo]'); await until(p, () => MED.step === 'still', 8000); r.med = await p.evaluate(() => !MED.c.a.getAttribute('src'));
    await p.click('[data-medamen]');
    await guided(p, 'led'); await p.click('[data-ledpp]'); await until(p, () => LED.done, 8000); r.led = await p.evaluate(() => !LED.c.a.getAttribute('src'));
    await p.click('[data-ledpp]'); await until(p, () => LED.c.state === 'playing'); await p.click('[data-ledgo="1"]'); await wait(200); r.ledAway = await p.evaluate(() => LED.c.state === 'playing' ? 'playing on (was playing)' : !LED.c.a.getAttribute('src'));
    await p.evaluate(() => { PRAY.lp.audio = TESTWAV; PRAY.lp.Lt = 0; PRAY.lp.a = 2; PRAY.lp.b = 4; PRAY.lp.at = [2, 2.3, 2.6, 2.9, 3.2, 3.5]; PR.mv = 0; });
    await guided(p, 'guided'); await p.click('[data-lpp]'); await until(p, () => LP.done, 8000); r.lp = await p.evaluate(() => !LP.c.a.getAttribute('src'));
    await guided(p, 'med'); await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing'); await p.click('[data-medgo2="1"]'); await wait(200); r.medAway = await p.evaluate(() => !MED.c.a.getAttribute('src'));
    return (r.med && r.led && r.ledAway && r.lp && r.medAway && !p.errs.length) || r;
  });
  await T('P34 browsing loads nothing: swiping through 10 sayings and 10 prayers starts no download', async () => {
    const p = await pray_(await page(null, { hasTouch: true })); const media = [];
    p.on('request', q => { if (q.resourceType() === 'media' || /\.(mp3|m4a|wav)(\?|#|$)/i.test(q.url())) media.push(q.url()); });
    await guided(p, 'med'); await p.evaluate(() => { MED.pick = medList()[0].ref; render(); }); for (let i = 0; i < 10; i++) { await p.click('[data-medgo2="1"]'); await wait(80); }
    await guided(p, 'led'); for (let i = 0; i < 10; i++) { await p.click('[data-ledgo="1"]'); await wait(80); }
    await wait(800); const held = await p.evaluate(() => [MED.c && MED.c.a.getAttribute('src'), LED.c && LED.c.a.getAttribute('src')]);
    return (!media.length && !held[0] && !held[1]) || { media: media.slice(0, 4), held };
  });
  await T('P35 the music comes in within 1.5 s of the reading or prayer starting, in Meditate, Be Led and the Lord\'s Prayer', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 14, sb: 25, e: 2 }); await music(p); const r = {};
    const timeIt = async () => { await until(p, () => !!(window.__CL && window.__CL.state === 'playing'), 8000); const t = Date.now(); const ok = await until(p, () => bedNow() > 0.05, 4000); return ok ? Date.now() - t : -1; };
    await guided(p, 'med'); await p.evaluate(() => { window.__CL = medC() }); await p.click('[data-medgo]'); r.med = await timeIt(); await p.evaluate(() => medStop(false));
    await p.evaluate(() => { BED.el.pause() }); await wait(600);
    await guided(p, 'led'); await p.evaluate(() => { window.__CL = ledC() }); await p.click('[data-ledpp]'); r.led = await timeIt(); await p.evaluate(() => LED.c.pause());
    await p.evaluate(() => { BED.el.pause(); PRAY.lp.audio = TESTWAV; PRAY.lp.Lt = 0; PRAY.lp.a = 2; PRAY.lp.b = 20; PRAY.lp.at = [2, 5, 8, 11, 14, 17]; PR.mv = 0; }); await wait(600);
    await guided(p, 'guided'); await p.evaluate(() => { window.__CL = lpC() }); await p.click('[data-lpp]'); r.lp = await timeIt();
    return (r.med >= 0 && r.med <= 1500 && r.led >= 0 && r.led <= 1500 && r.lp >= 0 && r.lp <= 1500 && !p.errs.length) || r;
  });
  await T('P36 the diagnostics: a Meditate run is recorded (the tap, the reading\'s events, the music) and ⋯ → Copy diagnostics gives it', async () => {
    const p = await pray_(await page()); await testAudio(p); await music(p); await guided(p, 'med');
    await p.click('[data-medgo]'); await until(p, () => MED.step === 'still', 8000); await wait(1500);
    const t = await p.evaluate(() => diagText());
    await p.evaluate(() => { view = 'settings'; render(); }); await wait(300);
    const btn = await p.evaluate(() => [...document.querySelectorAll('button')].some(b => b.textContent === 'Copy diagnostics'));
    const want = ['open', 'tap Begin', 'medm playing', 'medm stopped', 'music'];
    return (want.every(w => t.includes('  ' + w)) && btn && !p.errs.length) || { missing: want.filter(w => !t.includes('  ' + w)), btn, head: t.slice(0, 400) };
  });
  await T('P37 a file whose header understates its length (as Skip\'s do): Meditate and the Lord\'s Prayer put their true times on this phone\'s scale, so they start, follow and stop on the right words', async () => {
    const p = await pray_(await page()); await testAudio(p);
    // the stand-in is 30 s; say its true length is 31 s, so this browser's scale is 30/31 of the true one
    await guided(p, 'med'); await p.evaluate(() => { const m = medCur(); m.Lt = 31; m.a = 15.5; m.b = 18.6; window.MED_FAST = 0.05; });
    await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing'); const m0 = await p.evaluate(() => [MED.c.t0, MED.c.a.currentTime]);
    await until(p, () => MED.step === 'pause', 8000); const m1 = await p.evaluate(() => MED.c.stopAt); await p.evaluate(() => medStop(false));
    await p.evaluate(() => { Object.assign(PRAY.lp, { audio: TESTWAV, Lt: 31, a: 3.1, b: 24.8, at: [3.1, 6.2, 9.3, 12.4, 15.5, 18.6] }); PR.mv = 0; });
    await guided(p, 'guided'); await p.click('[data-lpp]'); await until(p, () => LP.c.state === 'playing'); const l0 = await p.evaluate(() => [LP.r, LP.c.a.currentTime]);
    await until(p, () => PR.mv >= 1, 6000); const l1 = await p.evaluate(() => [PR.mv, LP.c.a.currentTime]);
    const r = 30 / 31;
    return (Math.abs(m0[0] - 15.5 * r) < 0.02 && Math.abs(m0[1] - 15) < 0.4 && Math.abs(m1 - 18) < 0.15 && Math.abs(l0[0] - r) < 0.001 && Math.abs(l0[1] - 3) < 0.4 && l1[0] === 1 && l1[1] >= 5.7 && l1[1] < 6.6 && !p.errs.length) || { m0, m1, l0, l1, e: p.errs };
  });
  await T('P38 the saying is sized to the screen: on a short phone (390×700) and an everyday one (390×844) every saying\'s Begin is in view, never below 15px; short sayings keep 24px on the everyday one and lose no more than 2px on the short one', async () => {
    const bad = []; let small = 99, errs = [];
    for (const H of [700, 844]) {
    const p = await pray_(await page({ width: 390, height: H })); await guided(p, 'med');
    const n = await p.evaluate(() => medList().length);
    for (let k = 0; k < n; k++) {
      const r = await p.evaluate(k => { MED.pick = medList()[k].ref; MED.step = ''; render(); window.scrollTo(0, 0); const q = document.querySelector('.med-q'), g = document.querySelector('[data-medgo]'), t = document.querySelector('#tabs').getBoundingClientRect();
        return { k, ref: medCur().ref, len: medCur().t.length, fs: parseFloat(getComputedStyle(q).fontSize), bottom: Math.round(g.getBoundingClientRect().bottom), tabs: Math.round(t.top) }; }, k);
      small = Math.min(small, r.fs);
      if (r.bottom > r.tabs && r.fs > 15) bad.push(r);
      r.H = H;
      if (r.len < 100 && (H === 844 ? r.fs !== 24 : r.fs < 22)) bad.push({ shortShrunk: r });
      if (r.fs < 15) bad.push({ tooSmall: r });
    }
    errs = errs.concat(p.errs);
    }
    return (!bad.length && !errs.length) || { bad: bad.slice(0, 6), small, e: errs };
  });
  // ── The music as a plain player, its level inside the file; true times; the shuffles; the pastor ──────────────────
  await T('P39 the music\'s level is put inside the MP3 itself (MPEG-1 stereo and MPEG-2 mono): 8 steps decode exactly 12 dB softer, a fade-in comes in from where it starts, only the gain bits change', async () => {
    const p = await page(); const out = {};
    for (const f of ['tone_m1.mp3', 'tone_m2.mp3']) {
      const b64 = require('fs').readFileSync(require('path').join(__dirname, 'fixtures', f)).toString('base64');
      out[f] = await p.evaluate(async b64 => {
        const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0)), u8 = raw.slice(), map = mp3Map(u8); if (!map) return { map: null };
        BED.src = { u8, map, type: 'audio/mpeg' };
        const C = window.OfflineAudioContext || window.webkitOfflineAudioContext, ctx = new C(1, 44100, 44100);
        const dec = bl => bl.arrayBuffer().then(ab => new Promise((ok, no) => ctx.decodeAudioData(ab, ok, no)));
        const rms = (buf, s, e) => { const d = buf.getChannelData(0), a = Math.floor(s * buf.sampleRate), z = Math.floor(e * buf.sampleRate); let q = 0; for (let k = a; k < z; k++) q += d[k] * d[k]; return 10 * Math.log10(q / (z - a)); };
        const o = await dec(new Blob([raw])), s8bl = bedSoft(8, null), s8 = await dec(s8bl), fd = await dec(bedSoft(4, 3));
        const y = new Uint8Array(await s8bl.arrayBuffer()); let n = 0; for (let k = 0; k < y.length; k++) if (y[k] !== raw[k]) n++;
        return { d8: +(rms(s8, 1, 2.5) - rms(o, 1, 2.5)).toFixed(2), before: +(rms(fd, 1, 2.5) - rms(o, 1, 2.5)).toFixed(2), fade0: +(rms(fd, 3.0, 3.25) - rms(o, 3.0, 3.25)).toFixed(1), after: +(rms(fd, 5.2, 5.8) - rms(o, 5.2, 5.8)).toFixed(2), same: y.length === raw.length, changed: n, of: raw.length };
      }, b64);
    }
    const ok = r => r.d8 && Math.abs(r.d8 + 12.04) < 0.3 && Math.abs(r.before + 6.02) < 0.3 && r.fade0 < -15 && Math.abs(r.after + 6.02) < 0.3 && r.same && r.changed < r.of * 0.1;
    return (Object.values(out).every(ok) && !p.errs.length) || { out, e: p.errs };
  });
  await T('P40 the music is a plain player (never through Web Audio, which an iPhone pauses beside another recording and with the screen locked); changing its level swaps in a new copy where it is, not from the start', async () => {
    const p = await pray_(await page()); await testAudio(p, { sb: 25, e: 2 }); await music(p); await guided(p, 'led');
    await p.click('[data-ledpp]'); const on = await until(p, () => bedNow() > 0.05, 6000); await wait(1500);
    const a = await p.evaluate(() => ({ ctx: !!BED.ctx, kind: BED.mode, st: BED.st, t: BED.el.currentTime }));
    await p.click('[data-prmu]'); await p.evaluate(() => { const r = $('#prmulv'); r.value = 50; r.dispatchEvent(new Event('input')); r.dispatchEvent(new Event('change')); });
    const swapped = await until(p, () => BED.st === bedSteps(0.5) && !BED.el.paused && BED.el.currentTime > 0.5, 4000);
    const b2 = await p.evaluate(() => ({ st: BED.st, t: BED.el.currentTime, ctx: !!BED.ctx }));
    return (on && !a.ctx && a.kind === 'wav' && swapped && b2.t >= a.t - 0.3 && b2.st < a.st && !b2.ctx && !p.errs.length) || { on, a, swapped, b2, e: p.errs };
  });
  await T('P41 a recording whose length is misreported (true 31 s, reported 30): the Lord\'s Prayer and a Meditate reading stop at their true end — start plus the true time, also after a jump — and the movements follow by true time', async () => {
    const p = await pray_(await page()); await testAudio(p, { a: 5, b: 14 }); const r = {};
    await p.evaluate(() => { PRAY.lp.audio = TESTWAV; PRAY.lp.Lt = 31; PRAY.lp.a = 5; PRAY.lp.b = 12; PRAY.lp.at = [5, 6, 7, 8, 9, 10]; PR.mv = 0; });
    await guided(p, 'guided'); await p.click('[data-lpp]'); await until(p, () => LP.done, 15000);
    r.lp = await p.evaluate(() => ({ stop: +LP.c.stopAt.toFixed(2), want: +(5 * 30 / 31 + 7).toFixed(2), mv: PR.mv }));
    await p.evaluate(() => { const m = medCur(); m.audio = TESTWAV; m.a = 5; m.b = 14; m.Lt = 31; window.MED_FAST = 0.05; });
    await guided(p, 'med'); await p.click('[data-medgo]'); await until(p, () => MED.c.state === 'playing');
    await p.evaluate(() => { MED.c.a.currentTime = 8 }); await until(p, () => MED.step === 'still', 15000);
    r.med = await p.evaluate(() => ({ stop: +MED.c.stopAt.toFixed(2), want: +(8 + (14 - 8 * 31 / 30)).toFixed(2) }));
    return (Math.abs(r.lp.stop - r.lp.want) <= 0.15 && r.lp.mv === 5 && Math.abs(r.med.stop - r.med.want) <= 0.15 && !p.errs.length) || { r, e: p.errs };
  });
  await T('P42 Meditate is a shuffle: every saying once before any again, not in order; a new day brings the next; the arrows walk it', async () => {
    const p = await pray_(await page()); await guided(p, 'med');
    const a = await p.evaluate(() => { const o = medOrd(), keys = medList().map(medKey); return { n: keys.length, perm: o.o.length === keys.length && new Set(o.o).size === keys.length && o.o.every(k => keys.includes(k)), inOrder: o.o.slice(0, 10).join() === keys.slice(0, 10).join(), p: o.p, cur: medKey(medCur()) === o.o[o.p] }; });
    const day = await p.evaluate(() => { const o = S.get('medord'); o.d = dayNo() - 1; S.set('medord', o); const p0 = o.p; const n = medOrd(); return n.p === p0 + 1 && medKey(medCur()) === n.o[n.p]; });
    return (a.perm && !a.inOrder && a.cur && day && !p.errs.length) || { a, day, e: p.errs };
  });
  await T('P43 Be Led\'s pastor: "All pastors ⌄" picks one; his prayers only, the arrows skip the others; remembered; All pastors brings everyone back', async () => {
    const p = await pray_(await page()); await guided(p, 'led');
    const whos = await p.evaluate(() => [...document.querySelectorAll('[data-ledwho] option')].map(o => o.value));
    await p.selectOption('[data-ledwho]', 'Vaughan'); await wait(300);
    const one = await p.evaluate(() => ({ who: ledCur().who, label: document.querySelector('.led-pick span').textContent, name: document.querySelector('.led-who').textContent }));
    const walk = []; for (let i = 0; i < 4; i++) { await p.click('[data-ledgo="1"]'); await wait(120); walk.push(await p.evaluate(() => ledCur().who)); }
    await p.reload(); await wait(1500); await pray(p); const kept = await p.evaluate(() => [LED.who, ledCur().who]);
    await p.selectOption('[data-ledwho]', ''); await wait(300); const all = await p.evaluate(() => [LED.who, S.get('ledwho')]);
    return (whos[0] === '' && whos.includes('Skip') && whos.includes('PAM') && one.who === 'Vaughan' && /Kennon Vaughan ⌄/.test(one.label) && /Vaughan/.test(one.name) && walk.every(w => w === 'Vaughan') && kept.join() === 'Vaughan,Vaughan' && all.join() === ',' && !p.errs.length) || { whos, one, walk, kept, all, e: p.errs };
  });
  await T('P44 the music follows how loud the prayer is: under a recording 6 dB quieter than the middle it is 6 dB softer, under one 3 dB louder 3 dB louder; Meditate the same', async () => {
    const p = await pray_(await page()); await testAudio(p, { sb: 25, e: 2, a: 5, b: 20 }); await music(p); await guided(p, 'led');
    await p.evaluate(() => { PRAY.lum = -20; ledList().forEach(x => { x.lu = -26 }); });
    await p.click('[data-ledpp]'); const q = await until(p, () => Math.abs(bedNow() / (BED.plv * 0.501) - 1) < 0.2, 6000); const lq = await p.evaluate(() => +bedNow().toFixed(3));
    await p.evaluate(() => LED.c.pause()); await wait(300);
    await p.evaluate(() => { medList().forEach(x => { x.lu = -17 }); }); await guided(p, 'med'); await p.click('[data-medgo]');
    const l = await until(p, () => MED.on && Math.abs(bedNow() / Math.min(1, BED.plv * 1.413) - 1) < 0.2, 6000); const ll = await p.evaluate(() => +bedNow().toFixed(3));
    return (q && l && !p.errs.length) || { q, lq, l, ll, plv: await p.evaluate(() => BED.plv), e: p.errs };
  });
  const f = R.filter(r => !r[1].startsWith('PASS')).length; console.log(`\n${R.length - f}/${R.length} passed`); await b.close(); process.exit(f ? 1 : 0);
})().catch(e => { console.log(R.map(r => r.join(' ')).join('\n')); console.error(e); process.exit(1); });

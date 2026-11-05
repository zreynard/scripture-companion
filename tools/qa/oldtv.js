// QA layer 4: the TV page in OLD Chrome (TV browsers lag years behind: LG webOS 4-6 run Chrome 53-79).
// Runs on GitHub's servers with an old Puppeteer, which brings its own old Chromium. Made-up lyrics only.
// node tools/qa/oldtv.js   (SITE defaults to the published site)
const puppeteer = require('puppeteer');
delete globalThis.BroadcastChannel; require('../../site_extra/live.js'); const L = globalThis.Live;
const SITE = process.env.SITE || 'https://zreynard.github.io/scripture-companion/';
const wait = ms => new Promise(r => setTimeout(r, ms)); const R = []; let fails = 0;
const T = async (n, f) => { let r; try { r = await f(); } catch (e) { r = 'threw ' + String(e.message).split('\n')[0]; } const ok = r === true; if (!ok) fails++; R.push((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(r).slice(0, 300))); console.log(R[R.length - 1]); };
const until = async (fn, ms) => { const t0 = Date.now(); for (;;) { try { if (await fn()) return Date.now() - t0; } catch (e) {} if (Date.now() - t0 > ms) return -1; await wait(200); } };
(async () => {
  const b = await puppeteer.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  console.log('Browser:', await b.version());
  const ses = L.newSession(), lead = new L.Session({ sid: ses.sid, key: ses.key, role: 'lead' });
  const long = 'We will sing forever and ever of the One who rose again and reigns';
  const deck = { name: 'Old TV', set: [0], songs: [{ id: 'a', t: 'Alpha', key: 'G', capo: 0, short: ['C'], slides: [{ s: 'Chorus', sec: 0, occ: 0, l: [long, 'Praise for He rose, now He reigns', '', 'We will sing forever'] }, { s: 'Verse', sec: 1, occ: 1, l: ['Short line', 'Amen'] }] }] };
  await wait(3000); lead.publishDeck(deck); lead.set({ song: 0, slide: 0, blank: false });
  const errs = []; const p = await b.newPage(); p.on('pageerror', e => errs.push(e.message)); await p.setViewport({ width: 1920, height: 1080 });
  await p.goto(SITE + 'tv/?t=' + Date.now() + '#s=' + ses.sid + '&k=' + ses.key);
  const ms = await until(() => p.evaluate(() => { const e = document.querySelectorAll('.slide.on .tx'); return e.length && /rose/.test(e[e.length - 1].innerText); }), 30000);
  await T('O1 the lyrics arrive on an old TV browser', async () => ms >= 0 || (await p.evaluate(() => document.body.innerText.slice(0, 200))));
  const geo = () => p.evaluate(() => { const e = document.querySelectorAll('.slide.on .tx'), t = e[e.length - 1]; if (!t) return null; const r = t.getBoundingClientRect(); let lo = 1e9, hi = 0, l = 1e9, rr = 0; Array.prototype.forEach.call(t.querySelectorAll('div'), function (d) { if (!d.textContent) return; const q = d.getBoundingClientRect(); lo = Math.min(lo, q.top); hi = Math.max(hi, q.bottom); });
    const rg = document.createRange(); rg.selectNodeContents(t); const tr = rg.getBoundingClientRect(); return { w: Math.round(r.width), fs: parseFloat(t.style.fontSize), top: Math.round(lo), bottom: Math.round(hi), left: Math.round(tr.left), right: Math.round(tr.right), vw: innerWidth, vh: innerHeight }; });
  const ok = g => g && g.w > g.vw * 0.7 && g.fs >= 40 && g.top > 0 && g.bottom < g.vh && Math.abs((g.top + g.bottom) / 2 - g.vh / 2) < g.vh * 0.1 && Math.abs((g.left + g.right) / 2 - g.vw / 2) < g.vw * 0.05;
  await T('O2 long lyrics: big, centred, nothing off screen (1080p)', async () => { const g = await geo(); return ok(g) || g; });
  lead.set({ slide: 1 }); await until(() => p.evaluate(() => { const e = document.querySelectorAll('.slide.on .tx'); return e.length && /Amen/.test(e[e.length - 1].innerText); }), 15000); await wait(600);
  await T('O3 short lyrics: big and centred', async () => { const g = await geo(); return (ok(g) && g.fs >= 80) || g; });
  for (const [w, h] of [[1280, 720], [3840, 2160], [1366, 768]]) { await p.setViewport({ width: w, height: h }); await wait(800); await T('O4 centred at ' + w + 'x' + h, async () => { const g = await geo(); return ok(g) || g; }); }
  await T('O5 the TV tells the phone its version and that its layout is right', async () => { const ms2 = await until(() => Object.values(lead.peers).some(x => x.role === 'screen' && x.ok === true && /^\d+$/.test(String(x.ver))), 15000); return ms2 >= 0 || lead.peers; });
  await T('O6 Refresh TV from the phone reloads the TV, which comes straight back to the lyrics', async () => { await p.evaluate(() => { window.__mark = 1; }); lead.cmd({ reload: true }); const r1 = await until(() => p.evaluate(() => !window.__mark && /\?v=/.test(location.href)), 15000); const r2 = await until(() => p.evaluate(() => { const e = document.querySelectorAll('.slide.on .tx'); return e.length && /Amen/.test(e[e.length - 1].innerText); }), 20000); return (r1 >= 0 && r2 >= 0) || { r1, r2 }; });
  const q = await b.newPage(); q.on('pageerror', e => errs.push('pair:' + e.message)); await q.setViewport({ width: 1920, height: 1080 }); await q.goto(SITE + 'tv/?p=' + Date.now()); await wait(3000);
  await T('O7 the pairing code shows large in the middle', async () => { const g = await q.evaluate(() => { const c = document.querySelector('#code'), r = c.getBoundingClientRect(); return { txt: c.textContent, cx: Math.round(r.left + r.width / 2), cy: Math.round(r.top + r.height / 2), h: Math.round(r.height) }; }); return (/^[A-Z0-9]{6}$/.test(g.txt) && Math.abs(g.cx - 960) < 80 && Math.abs(g.cy - 540) < 200 && g.h > 100) || g; });
  await T('O8 no script errors on the old browser', async () => errs.length === 0 || errs.slice(0, 4));
  lead.close(); await b.close(); console.log(`\n${R.length - fails}/${R.length} passed`); process.exit(fails ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });

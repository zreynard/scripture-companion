// End-to-end Worship test on the published site and the real relays: phone (leader), TV, and a friend's phone,
// each its own browser. Lyrics are made up for the test.
const { chromium, webkit, devices } = require('playwright');
const ENGINE = process.env.BROWSER === 'webkit' ? webkit : chromium;   // BROWSER=webkit runs everything in Safari's engine
const SITE = process.env.SITE || 'https://zreynard.github.io/scripture-companion/';
const CHART = ['Intro: G D Em C', '', 'Verse 1', 'G            D', 'Walking on a quiet road,', 'Em               C', 'morning light is breaking through.', '',
  'Chorus', 'C          G', 'You are near, You are near,', 'Em            D', 'we will rest in You.', '', 'Verse 2', 'G              D', 'Every valley, every hill,', '',
  'Chorus', '', 'Bridge', 'C        D        Em', 'Here we stand, here we stand,'].join('\n');
const R = {}, wait = ms => new Promise(r => setTimeout(r, ms)); let fails = 0;
const check = (name, ok, extra) => { R[name] = ok ? 'PASS' : 'FAIL ' + JSON.stringify(extra || ''); if (!ok) fails++; };
async function until(fn, ms = 15000) { const t0 = Date.now(); for (;;) { try { const v = await fn(); if (v) return Date.now() - t0; } catch (e) {} if (Date.now() - t0 > ms) return -1; await wait(100); } }
const CUT = () => { const W = window.WebSocket; window.__ws = []; window.__down = false;
  window.WebSocket = function (u, p) { if (window.__down) throw new Error('offline'); const w = new W(u, p); window.__ws.push(w); return w; };
  window.WebSocket.prototype = W.prototype; window.__cut = on => { window.__down = on; if (on) window.__ws.forEach(w => { try { w.close(); } catch (e) {} }); }; };
async function outage(ctx, page, on) { await ctx.setOffline(on); await page.evaluate(o => { window.__cut(o); window.dispatchEvent(new Event(o ? 'offline' : 'online')); if (!o) document.dispatchEvent(new Event('visibilitychange')); }, on); }
(async () => {
  const b = await ENGINE.launch(); const errs = [];
  const phoneC = await b.newContext({ ...devices['iPhone 14'] }); await phoneC.addInitScript(CUT); const phone = await phoneC.newPage(); phone.on('pageerror', e => errs.push('phone:' + e.message)); phone.on('dialog', d => d.accept());
  const tvC = await b.newContext({ viewport: { width: 1920, height: 1080 } }); await tvC.addInitScript(CUT); const tv = await tvC.newPage(); tv.on('pageerror', e => errs.push('tv:' + e.message));
  await phone.goto(SITE + '?t=' + Date.now()); await wait(1500);
  await phone.evaluate(chart => { S.set('wsongs', { q1: { id: 'q1', t: 'Quiet Road', a: 'Test Artist', key: 'G', src: chart }, q2: { id: 'q2', t: 'Second Song', key: 'D', src: 'Verse 1\nD   A\nsecond song line one,\nsecond song line two.' } });
    S.set('wsets', [{ id: 's1', name: 'Test Night', items: [{ id: 'q1', key: 'A' }, { id: 'q2' }] }]); }, CHART);
  await phone.click('#tabs [data-tab2=worship]'); await phone.click('[data-wp=sets]'); await phone.click('[data-wset=s1]'); await phone.click('[data-wpresentset]');
  await phone.waitForURL(/live\//); const hash = phone.url().split('#')[1];
  check('A1 phone reaches the live relays', (await until(() => phone.evaluate(() => /screen/i.test(document.querySelector('#pill').textContent)), 20000)) >= 0);
  // TV: open /tv, read the code, phone types it
  await tv.goto(SITE + 'tv/'); const ready = await until(() => tv.evaluate(() => /Ready/.test(document.querySelector('#pst').textContent)), 20000);
  const code = await tv.textContent('#code'); check('A2 TV shows a pairing code and is ready', ready >= 0 && /^[A-Z0-9]{6}$/.test(code), { code, ready });
  await phone.click('#bScreen'); await phone.fill('#cin', code); await phone.click('#cgo');
  const paired = await until(() => phone.evaluate(() => /Screen on|screens/.test(document.querySelector('#pill').textContent)), 25000);
  check('A3 phone pairs with the TV by code', paired >= 0, paired);
  await phone.evaluate(() => { const s = document.querySelector('#sh'); if (s) s.hidden = true; });
  const tvLine = () => tv.evaluate(() => { const e = document.querySelectorAll('.slide.on .tx'); return e.length ? e[e.length - 1].innerText.split('\n')[0] : '(blank)'; });
  await wait(800); const diag = await phone.evaluate(() => ({ w: document.documentElement.scrollWidth, vw: innerWidth })); console.log('DIAG', JSON.stringify(await phone.evaluate(() => { const r = document.querySelector('#bNext').getBoundingClientRect(), e = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2), bar = document.querySelector('#bar');
    return { hit: e && (e.id || e.className), r: [r.x, r.y, r.width, r.height], bar: getComputedStyle(bar).display + ' ' + getComputedStyle(bar).position + ' ' + bar.getBoundingClientRect().top, y: scrollY, ih: innerHeight, sh: getComputedStyle(document.querySelector('#sh')).display, zoom: visualViewport.scale }; })));
  await phone.screenshot({ path: 'diag_phone.png' });
  check('A3b nothing is wider than the phone', diag.w <= diag.vw, diag);
  await phone.click('#bNext', { timeout: 8000 }); const lat = await until(async () => (await tvLine()) === 'Walking on a quiet road,');
  check('A4 Next on the phone shows Verse 1 on the TV', lat >= 0, { lat, tv: await tvLine() }); R.A4_ms = lat;
  check('A5 TV shows lyrics only (no chords, no controls)', await tv.evaluate(() => !document.body.innerText.match(/\b(Em|Next|Blank)\b/) && document.querySelectorAll('button').length === 0));
  // friend opens the shared remote link: no account, no songbook
  const frC = await b.newContext({ ...devices['Pixel 7'] }), fr = await frC.newPage(); fr.on('pageerror', e => errs.push('friend:' + e.message));
  await fr.goto(SITE + 'live/#' + hash.replace('&lead=1', ''));
  const asked = await until(() => fr.evaluate(() => !!document.querySelector('#nm')), 8000); if (asked >= 0) { await fr.fill('#nm', 'Sam'); await fr.click('#nmok'); }
  check('B0 friend is asked their first name once', asked >= 0 && await fr.evaluate(() => localStorage.getItem('scwp:name') === 'Sam'));
  const frDeck = await until(() => fr.evaluate(() => document.querySelectorAll('.chip').length > 2), 20000);
  check('B1 friend joins from the link with no account', frDeck >= 0);
  check('B2 friend link does not expose the songbook', await fr.evaluate(() => !localStorage.getItem('sc:wsongs')));
  await fr.click('.chip:has-text("Chorus")'); const c1 = await until(async () => (await tvLine()) === 'You are near, You are near,');
  check('B3 friend jumps to the Chorus; TV follows', c1 >= 0, await tvLine());
  check('B4 phone follows the friend', (await until(() => phone.evaluate(() => document.querySelector('.mon .lab').textContent === 'Chorus'))) >= 0);
  // spontaneous: go to the Bridge, then sing the Chorus again
  await phone.click('.chip:has-text("Bridge")'); await until(async () => (await tvLine()) === 'Here we stand, here we stand,');
  await phone.click('.chip:has-text("Chorus")'); const c2 = await until(async () => (await tvLine()) === 'You are near, You are near,');
  check('C1 Bridge then Chorus again on one tap', c2 >= 0, await tvLine());
  await phone.click('#bBlank'); check('C2 Blank clears the TV', (await until(async () => (await tvLine()) === '(blank)')) >= 0);
  await phone.click('#bBlank'); check('C3 Show brings the lyrics back', (await until(async () => (await tvLine()) === 'You are near, You are near,')) >= 0);
  // E: the phone loses its connection; the TV keeps its lyrics; the friend keeps leading; the phone catches up
  await outage(phoneC, phone, true);
  const shows = await until(() => phone.evaluate(() => /Reconnecting/.test(document.querySelector('#pill').textContent)), 10000);
  check('E0 phone shows it is offline (not a false connected state)', shows >= 0);
  await wait(1500); check('E1 TV keeps the lyrics while the phone is offline', (await tvLine()) === 'You are near, You are near,', await tvLine());
  await phone.click('#bNext').catch(() => {});   // a tap while offline
  await fr.click('.chip:has-text("Bridge")'); check('E2 friend still moves the TV', (await until(async () => (await tvLine()) === 'Here we stand, here we stand,')) >= 0);
  check('E2b the phone, offline, is not following yet', await phone.evaluate(() => document.querySelector('.mon .lab').textContent) === 'Verse 2', await phone.evaluate(() => document.querySelector('.mon .lab').textContent));
  await wait(5000); await outage(phoneC, phone, false);
  const back = await until(() => phone.evaluate(() => document.querySelector('.mon .lab').textContent === 'Bridge'), 30000);
  check('E3 phone resyncs after reconnecting (song kept)', back >= 0, await phone.evaluate(() => document.querySelector('.mon .lab').textContent)); R.E3_ms = back;
  await wait(2500); check('E4 the offline tap did not override newer changes', (await tvLine()) === 'Here we stand, here we stand,', await tvLine());
  // the TV loses its connection, then catches up
  await outage(tvC, tv, true); await wait(3000); await phone.click('#bNext'); await wait(1500);
  check('E5 TV keeps the last lyrics while offline', (await tvLine()) === 'Here we stand, here we stand,');
  await wait(4000); check('E5b TV still showing its lyrics after 5 s offline', (await tvLine()) === 'Here we stand, here we stand,'); await outage(tvC, tv, false);
  const tvBack = await until(async () => (await tvLine()) === 'second song line one,', 40000);
  check('E6 TV catches up after reconnecting', tvBack >= 0, await tvLine()); R.E6_ms = tvBack;
  // next song from the end of the first
  check('S1 Next at the end of a song goes on to the next song', (await phone.evaluate(() => document.querySelector('.song b').textContent)) === 'Second Song');
  // the TV's own keys (laptop on HDMI)
  await tv.keyboard.press('ArrowLeft'); check('K1 laptop keys move everyone', (await until(() => phone.evaluate(() => document.querySelector('.song b').textContent === 'Quiet Road'))) >= 0);
  // end
  await phone.click('#bEnd'); await phone.click('#eok');
  check('Z1 ending blanks the TV and it goes back to a pairing code', (await until(() => tv.evaluate(() => !document.querySelector('#pair').hidden), 20000)) >= 0);
  check('Z2 the friend sees the session has ended', (await until(() => fr.evaluate(() => /ended/.test(document.body.innerText)), 15000)) >= 0);
  // F: Apple Music search finds the exact recording (artist matters), and links open music.apple.com
  const appC = await b.newContext({ ...devices['iPhone 14'] }), app = await appC.newPage(); app.on('pageerror', e => errs.push('app:' + e.message));
  await app.goto(SITE + '?t=' + Date.now()); await wait(1500);
  const am = await app.evaluate(() => new Promise(r => wAmSearch('How Great Is Our God Chris Tomlin', x => r(x && x.slice(0, 5).map(y => [y.trackName, y.artistName, y.trackViewUrl])))));
  // Apple's edge refuses automated browsers from datacenter networks, so this is reported, not required (it answers from phones)
  R['F1 Apple Music search from this test browser (info)'] = am && am.length ? 'answered: ' + am.slice(0, 2).map(x => x[1]).join(', ') : 'refused here (datacenter browser)';
  // G: the rest of the app still opens
  const tabs = {};
  for (const t of ['journey', 'bible', 'library', 'pray', 'worship']) { await app.click('#tabs [data-tab2=' + t + ']'); await wait(700); tabs[t] = await app.evaluate(() => document.querySelector('#main').innerText.length > 40); }
  check('G1 Journey, Bible, Library, Pray and Worship all open', Object.values(tabs).every(Boolean), tabs);
  // Apple's search refuses GitHub's servers (a datacenter); on a phone it answers. Those refusals are noted, not failures.
  const apple = errs.filter(x => /itunes\.apple\.com|Cross-origin script load denied/.test(x)); if (apple.length) R.Z3_note = 'Apple search refused this server: ' + apple.length;
  const real = errs.filter(x => apple.indexOf(x) < 0); check('Z3 no page errors', real.length === 0, real);
  console.log(JSON.stringify(R, null, 1)); console.log(fails ? fails + ' FAILED' : 'ALL PASSED'); await b.close(); process.exit(fails ? 1 : 0);
})().catch(e => { console.log(JSON.stringify(R, null, 1)); console.error(e); process.exit(1); });

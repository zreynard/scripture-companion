// How fast the app opens, on a phone-like processor (4× slower) and a slow connection — and that it opens from the
// phone's copy, picks up a new build without a blank screen, and never reloads mid-prayer.
//   SITE=http://localhost:8765/ node tools/qa/perf.js        (Chromium; times are printed, and checked against budgets)
const { chromium } = require('playwright');
const SITE = process.env.SITE || 'http://localhost:8765/';
const R = []; const wait = ms => new Promise(r => setTimeout(r, ms));
async function T(n, f) { try { const r = await f(); R.push([n, r === true ? 'PASS' : 'FAIL ' + JSON.stringify(r).slice(0, 500)]); } catch (e) { R.push([n, 'FAIL ' + String(e).slice(0, 300)]); } console.log(R[R.length - 1][1].startsWith('PASS') ? 'PASS' : 'FAIL', n, R[R.length - 1][1].startsWith('PASS') ? '' : R[R.length - 1][1].slice(5)); }
const NET = { fast3g: { offline: false, latency: 150, downloadThroughput: 1.6e6 / 8, uploadThroughput: 750e3 / 8 }, slow3g: { offline: false, latency: 400, downloadThroughput: 400e3 / 8, uploadThroughput: 400e3 / 8 } };
// the time from asking for the page to the Journey being on screen
async function open(p, url) {
  const t0 = Date.now(); await p.goto(url, { waitUntil: 'commit', timeout: 90000 });
  await p.waitForFunction(() => { const m = document.querySelector('#main'); return !!(m && m.children.length && typeof render === 'function' && render.boot); }, null, { timeout: 90000, polling: 50 });
  return Date.now() - t0;
}
const show = (k, v) => console.log(`   ${k}: ${v}`);

(async () => {
  const b = await chromium.launch();
  const ctx = async () => { const c = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await c.newPage(); const cdp = await c.newCDPSession(p);
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 }); await cdp.send('Network.enable'); return { c, p, cdp }; };

  await T('F1 first open on a slow phone connection (Fast 3G, 4× slower processor): the Journey is on screen in under 8 s', async () => {
    const { c, p, cdp } = await ctx(); await cdp.send('Network.emulateNetworkConditions', NET.fast3g);
    const ms = await open(p, SITE + '?f1=' + Date.now()); show('first open, Fast 3G', ms + ' ms'); await c.close();
    return ms < 8000 || { ms };
  });
  await T('F2 every later open comes from the phone\'s copy: on Slow 3G and with no connection, the Journey is on screen in under 2.5 s', async () => {
    const { c, p, cdp } = await ctx();
    await open(p, SITE); await p.evaluate(() => navigator.serviceWorker.ready); await wait(2500);
    await p.reload(); await p.waitForFunction(() => !!navigator.serviceWorker.controller, null, { timeout: 20000 }); await wait(1500);
    await cdp.send('Network.emulateNetworkConditions', NET.slow3g);
    const slow = await open(p, SITE); const from = await p.evaluate(() => (diagText().match(/open\s+\{"from":"([^"]+)"/g) || []).pop() || '');
    await c.setOffline(true); const off = await open(p, SITE); await c.setOffline(false);
    show('later open, Slow 3G', slow + ' ms'); show('later open, offline', off + ' ms'); show('came from', from);
    await c.close();
    return (slow < 2500 && off < 2500 && /service worker/.test(from)) || { slow, off, from };
  });
  await T('F3 a newer build: fetched behind the scenes, never reloads mid-prayer, and takes over when the app is put away', async () => {
    const { c, p } = await ctx();
    await open(p, SITE); await p.evaluate(() => navigator.serviceWorker.ready); await p.reload(); await p.waitForFunction(() => !!navigator.serviceWorker.controller, null, { timeout: 20000 }); await wait(5000);
    const v = await p.evaluate(() => APPV);
    await p.route('**/version.txt*', r => r.fulfill({ status: 200, body: String(v + 1) }));
    let navs = 0; p.on('framenavigated', f => { if (f === p.mainFrame()) navs++; });
    // a prayer is playing (a stand-in on the Be Led player)
    await p.evaluate(() => { const sr = 8000, n = sr * 30, buf = new ArrayBuffer(44 + n * 2), d = new DataView(buf); const w = (q, s) => [...s].forEach((ch, i) => d.setUint8(q + i, ch.charCodeAt(0)));
      w(0, 'RIFF'); d.setUint32(4, 36 + n * 2, true); w(8, 'WAVEfmt '); d.setUint32(16, 16, true); d.setUint16(20, 1, true); d.setUint16(22, 1, true); d.setUint32(24, sr, true); d.setUint32(28, sr * 2, true); d.setUint16(32, 2, true); d.setUint16(34, 16, true); w(36, 'data'); d.setUint32(40, n * 2, true);
      const a = document.getElementById('ledm'); a.src = URL.createObjectURL(new Blob([buf], { type: 'audio/wav' })); a.play(); });
    await p.evaluate(() => checkV()); const ready = await p.waitForFunction(() => !!UPD.ready, null, { timeout: 30000 }).then(() => true).catch(() => false);
    await wait(3000); const midPrayer = navs;
    await p.evaluate(() => { document.getElementById('ledm').pause(); Object.defineProperty(document, 'hidden', { value: true, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
    await p.waitForEvent('framenavigated', { timeout: 10000 }).catch(() => null); await wait(1000);
    const after = navs; await c.close();
    return (ready && midPrayer === 0 && after >= 1) || { ready, midPrayer, after };
  });
  await T('F4 starting the page on a phone-like processor (the data read as JSON): under 900 ms', async () => {
    const out = [];
    for (let i = 0; i < 3; i++) { const { c, p } = await ctx(); await p.goto(SITE + '?f4=' + Date.now() + i, { waitUntil: 'load' });
      out.push(await p.evaluate(() => { const n = performance.getEntriesByType('navigation')[0]; return Math.round(n.domContentLoadedEventEnd - n.responseEnd) })); await c.close(); }
    out.sort((a, b) => a - b); show('page start at 4× slower processor (ms, 3 runs)', out.join(', '));
    return out[1] < 900 || { out };
  });
  const f = R.filter(r => !r[1].startsWith('PASS')).length; console.log(`\n${R.length - f}/${R.length} passed`); await b.close(); process.exit(f ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });

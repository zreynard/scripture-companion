// Diagnosis in WebKit (Safari's engine): does the map data (atlas.json, fetched in the background a moment after the
// Journey opens) ever raise a page error — when it finishes, when the page reloads mid-download, when the page closes?
const { webkit, devices } = require('playwright'); const SITE = process.env.SITE || 'https://zreynard.github.io/scripture-companion/'; const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => { const b = await webkit.launch();
  for (const how of ['finishes', 'reload mid-download', 'close mid-download', 'goto another page mid-download']) {
    const c = await b.newContext(devices['iPhone 14']); const p = await c.newPage(); const errs = [], net = [];
    p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') net.push('console: ' + m.text().slice(0, 140)); });
    p.on('request', r => { if (/atlas\.json/.test(r.url())) net.push('request ' + (Date.now() % 100000)); }); p.on('requestfinished', r => { if (/atlas\.json/.test(r.url())) net.push('finished ' + (Date.now() % 100000)); }); p.on('requestfailed', r => { if (/atlas\.json/.test(r.url())) net.push('failed: ' + (r.failure() || {}).errorText); });
    await p.goto(SITE + '?d=' + Date.now()); 
    const t0 = Date.now(); while (!net.some(x => x.startsWith('request')) && Date.now() - t0 < 6000) await wait(50);
    if (how === 'finishes') await wait(4000);
    else if (how === 'reload mid-download') { await p.reload(); await wait(1500); }
    else if (how === 'goto another page mid-download') { await p.goto(SITE + 'tv/'); await wait(1500); }
    const loaded = await p.evaluate(() => typeof ATL_D !== 'undefined' && !!ATL_D).catch(() => 'n/a');
    if (how === 'close mid-download') { await c.close(); await wait(500); } else await c.close();
    console.log(JSON.stringify({ how, pageerrors: errs, net, loaded }));
  }
  await b.close(); })();

// Diagnosis in WebKit (Safari's engine): how the chord chart is measured, and what covers the editor's Save button.
const { webkit, devices } = require('playwright'); const SITE = process.env.SITE || 'https://zreynard.github.io/scripture-companion/'; const wait = ms => new Promise(r => setTimeout(r, ms));
const verse = (n, k) => Array.from({ length: n }, (_, i) => `G        D\nline ${k} ${i} of this song,\nEm       C\nanother line ${i} here.`).join('\n');
const LONG = 'Verse 1\n' + verse(14, 'L') + '\n\nChorus\n' + verse(6, 'C') + '\n\nBridge\n' + verse(6, 'B') + '\n\nOutro\nG D';
(async () => { const b = await webkit.launch();
  for (const dev of ['iPhone 14', 'iPad Mini']) { const c = await b.newContext(devices[dev]); const p = await c.newPage(); p.on('pageerror', e => console.log('pageerror', e.message)); await p.goto(SITE); await wait(1500);
    await p.evaluate(src => { S.set('wsongs', { a: { id: 'a', t: 'Long', key: 'G', src } }); WS.song = 'a'; $('#tabs [data-tab2=worship]').click(); }, LONG); await wait(3000); console.log(dev, 'fitRanBefore', await p.evaluate(() => !!($('#wfit') && $('#wfit')._fit))); await p.evaluate(() => wFitSong()); await wait(500);
    const m = await p.evaluate(() => { const box = $('#wfit'), inner = box.firstElementChild, cs = getComputedStyle(inner), r = inner.getBoundingClientRect(); let R = 0, B = 0, n = 0; for (const k of inner.children) for (const q of k.getClientRects()) { n++; R = Math.max(R, q.right - r.left); B = Math.max(B, q.bottom - r.top); }
      return { fit: box._fit, W: box.clientWidth, H: box.clientHeight, boxH: box.style.height, inner: { sw: inner.scrollWidth, sh: inner.scrollHeight, cw: inner.clientWidth, ch: inner.clientHeight, h: inner.style.height, cc: cs.columnCount, cf: cs.columnFill, colw: cs.columnWidth, disp: cs.display, ov: cs.overflow }, rects: n, R: Math.round(R), B: Math.round(B), boxSW: box.scrollWidth, docH: document.scrollingElement.scrollHeight, vh: innerHeight, sections: inner.children.length }; });
    console.log(dev, 'CHART', JSON.stringify(m));
    // editor: what sits on the Save button
    await p.evaluate(() => { WS.song = null; WS.edit = 'new'; render(); }); await wait(800);
    const e = await p.evaluate(() => { const s = $('#wf-save'); if (!s) return 'no save button'; s.scrollIntoView({ block: 'center' }); const r = s.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, top = document.elementFromPoint(x, y);
      return { r: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)], vh: innerHeight, hit: top ? (top.id || top.className || top.tagName) : null, same: top === s || s.contains(top), tabs: getComputedStyle($('#tabs')).display, body: document.body.className }; });
    console.log(dev, 'SAVE', JSON.stringify(e));
    // the editor flow from test U9: fill the fields with harmless injected HTML and save
    let dlg = ''; p.on('dialog', x => { dlg = x.message(); x.accept(); });
    try { await p.fill('#wf-t', '<img src=x onerror="window.__pwn=1">'); await p.fill('#wf-a', 'A'); await p.fill('#wf-src', 'Verse 1\nG\nwords'); await p.click('#wf-save', { timeout: 8000 }); await wait(600);
      console.log(dev, 'EDITOR saved', JSON.stringify(await p.evaluate(() => ({ edit: WS.edit, song: WS.song, n: Object.keys(S.get('wsongs', {})).length, pwn: window.__pwn || 0 }))), 'dialog:', dlg); }
    catch (er) { console.log(dev, 'EDITOR stuck', er.message.split('\n').slice(0, 12).join(' | ').slice(0, 900)); }
    await c.close(); }
  // test U35: an iPad turned sideways; what is taller than the screen afterwards?
  { const c = await b.newContext(devices['iPad (gen 7)']); const p = await c.newPage(); await p.goto(SITE); await wait(1200);
    const SONG = 'Intro: G D Em C\n\nVerse 1\n' + verse(2, 'v1') + '\n\nChorus\nC      G\nsing it out,\nEm     D\nlift it high.\n\nVerse 2\n' + verse(2, 'v2') + '\n\nChorus\n\nBridge\nC   D   Em\nhere we stand';
    await p.evaluate(src => { S.set('wsongs', { L: { id: 'L', t: 'Long', key: 'G', src } }); $('#tabs [data-tab2=worship]').click(); WS.song = 'L'; render(); }, SONG); await wait(800);
    const snap = () => p.evaluate(() => { const box = $('#wfit'), r = box.getBoundingClientRect(), tall = [...document.querySelectorAll('body *')].filter(e => { const q = e.getBoundingClientRect(); return q.bottom > innerHeight + 2 && q.height > 0 && getComputedStyle(e).position !== 'fixed'; }).slice(0, 6).map(e => (e.id || e.className || e.tagName).toString().slice(0, 30) + ':' + Math.round(e.getBoundingClientRect().bottom));
      return { vw: innerWidth, vh: innerHeight, docH: document.scrollingElement.scrollHeight, bodyH: document.body.scrollHeight, boxTop: Math.round(r.top), boxBottom: Math.round(r.bottom), boxStyleH: box.style.height, fit: box._fit, body: document.body.className, tabs: getComputedStyle($('#tabs')).display, scrollY, tall }; });
    console.log('U35 before', JSON.stringify(await snap())); await p.setViewportSize({ width: 1080, height: 810 }); await wait(700); console.log('U35 after', JSON.stringify(await snap())); await wait(1500); console.log('U35 later', JSON.stringify(await snap())); await c.close(); }
  await b.close(); })();

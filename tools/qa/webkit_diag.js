// Diagnosis in WebKit (Safari's engine): how the chord chart is measured, and what covers the editor's Save button.
const { webkit, devices } = require('playwright'); const SITE = process.env.SITE || 'https://zreynard.github.io/scripture-companion/'; const wait = ms => new Promise(r => setTimeout(r, ms));
const verse = (n, k) => Array.from({ length: n }, (_, i) => `G        D\nline ${k} ${i} of this song,\nEm       C\nanother line ${i} here.`).join('\n');
const LONG = 'Verse 1\n' + verse(14, 'L') + '\n\nChorus\n' + verse(6, 'C') + '\n\nBridge\n' + verse(6, 'B') + '\n\nOutro\nG D';
(async () => { const b = await webkit.launch();
  for (const dev of ['iPhone 14', 'iPad Mini']) { const c = await b.newContext(devices[dev]); const p = await c.newPage(); p.on('pageerror', e => console.log('pageerror', e.message)); await p.goto(SITE); await wait(1500);
    await p.evaluate(src => { S.set('wsongs', { a: { id: 'a', t: 'Long', key: 'G', src } }); WS.song = 'a'; $('#tabs [data-tab2=worship]').click(); }, LONG); await wait(1500);
    const m = await p.evaluate(() => { const box = $('#wfit'), inner = box.firstElementChild, cs = getComputedStyle(inner), r = inner.getBoundingClientRect(); let R = 0, B = 0, n = 0; for (const k of inner.children) for (const q of k.getClientRects()) { n++; R = Math.max(R, q.right - r.left); B = Math.max(B, q.bottom - r.top); }
      return { fit: box._fit, W: box.clientWidth, H: box.clientHeight, boxH: box.style.height, inner: { sw: inner.scrollWidth, sh: inner.scrollHeight, cw: inner.clientWidth, ch: inner.clientHeight, h: inner.style.height, cc: cs.columnCount, cf: cs.columnFill, colw: cs.columnWidth, disp: cs.display, ov: cs.overflow }, rects: n, R: Math.round(R), B: Math.round(B), boxSW: box.scrollWidth, docH: document.scrollingElement.scrollHeight, vh: innerHeight, sections: inner.children.length }; });
    console.log(dev, 'CHART', JSON.stringify(m));
    // editor: what sits on the Save button
    await p.evaluate(() => { WS.song = null; WS.edit = 'new'; render(); }); await wait(800);
    const e = await p.evaluate(() => { const s = $('#wf-save'); if (!s) return 'no save button'; s.scrollIntoView({ block: 'center' }); const r = s.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, top = document.elementFromPoint(x, y);
      return { r: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)], vh: innerHeight, hit: top ? (top.id || top.className || top.tagName) : null, same: top === s || s.contains(top), tabs: getComputedStyle($('#tabs')).display, body: document.body.className }; });
    console.log(dev, 'SAVE', JSON.stringify(e)); await c.close(); }
  await b.close(); })();

// QA: the Worship chart file ("File" view), everywhere it shows: phone, small phone, iPad, computer; portrait and
// landscape; turned while open; inline on the song, full screen (open, zoom, Done, Esc, the back button), and on the
// leader's Present page. Made-up charts only (a generated 40-page PDF, a landscape PDF, a tall and a wide photo).
//   SITE=http://localhost:8765/ [BROWSER=webkit] [SHOTS=dir] node tools/qa/fileview.js
const { chromium, webkit, devices } = require('playwright');
const ENGINE = process.env.BROWSER === 'webkit' ? webkit : chromium, WK = ENGINE === webkit;
const SITE = process.env.SITE || 'http://localhost:8765/', SHOTS = process.env.SHOTS || '';
const R = [], wait = ms => new Promise(r => setTimeout(r, ms));
async function T(n, f) { let r; try { r = await Promise.race([f(), new Promise((_, no) => setTimeout(() => no(new Error('took over 4 minutes')), 240000))]); } catch (e) { r = 'threw ' + String(e).slice(0, 400); }
  R.push([n, r === true ? 'PASS' : 'FAIL ' + (typeof r === 'string' ? r : JSON.stringify(r)).slice(0, 2500)]); const x = R[R.length - 1]; console.log(x[1].startsWith('PASS') ? 'PASS' : 'FAIL', n, x[1].startsWith('PASS') ? '' : x[1].slice(5)); }
/* a hand-made PDF: pages of made-up lines; size [w,h] in points */
function mkpdf(pages, size) { const [W, H] = size || [612, 792], objs = [], add = s => { objs.push(s); return objs.length; }, font = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
  const cs = pages.map(lines => { const body = 'BT /F1 22 Tf 50 ' + (H - 60) + ' Td 28 TL ' + lines.map(l => '(' + l + ') Tj T*').join(' ') + ' ET'; return add(`<< /Length ${body.length} >>\nstream\n${body}\nendstream`); });
  const pagesId = objs.length + pages.length + 1, kids = cs.map(c => add(`<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${W} ${H}] /Resources << /Font << /F1 ${font} 0 R >> >> /Contents ${c} 0 R >>`));
  add(`<< /Type /Pages /Kids [${kids.map(k => k + ' 0 R').join(' ')}] /Count ${kids.length} >>`); const cat = add(`<< /Type /Catalog /Pages ${pagesId} 0 R >>`);
  let out = '%PDF-1.4\n'; const offs = []; objs.forEach((o, i) => { offs.push(out.length); out += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const x = out.length; out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offs.map(o => String(o).padStart(10, '0') + ' 00000 n \n').join('') + `trailer\n<< /Size ${objs.length + 1} /Root ${cat} 0 R >>\nstartxref\n${x}\n%%EOF\n`; return Buffer.from(out, 'latin1'); }
const LONG = { name: 'Long Chart.pdf', mimeType: 'application/pdf', buffer: mkpdf(Array.from({ length: 40 }, (_, i) => ['Page ' + (i + 1) + ' of 40', 'Verse ' + (i % 4 + 1), 'G      C      D', 'a made-up line ' + (i + 1)])) };
const WIDE = { name: 'Landscape Chart.pdf', mimeType: 'application/pdf', buffer: mkpdf([['Landscape page', 'Chorus', 'C   G   Am   F', 'another made-up line']], [792, 612]) };
const CONFIGS = [
  ['iPhone 14', devices['iPhone 14'], devices['iPhone 14 landscape']],
  ['iPhone SE', devices['iPhone SE'], devices['iPhone SE landscape']],
  ['iPad Pro 11', devices['iPad Pro 11'], devices['iPad Pro 11 landscape']],
  ['iPad Mini', devices['iPad Mini'], devices['iPad Mini landscape']],
  ['Computer 1440', { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 }, { viewport: { width: 900, height: 1200 }, deviceScaleFactor: 2 }],
  ['Computer 1024', { viewport: { width: 1024, height: 700 }, deviceScaleFactor: 1 }, { viewport: { width: 700, height: 1024 }, deviceScaleFactor: 1 }],
];
const ONLY = process.env.ONLY ? new RegExp(process.env.ONLY) : null;

(async () => {
  const b = await ENGINE.launch();
  for (const [name, dev, rot] of CONFIGS) {
    if (ONLY && !ONLY.test(name)) continue;
    const touch = !!dev.hasTouch, shot = async (p, k) => { if (SHOTS) await p.screenshot({ path: `${SHOTS}/${(WK ? 'wk' : 'cr')}-${name.replace(/\s+/g, '')}-${k}.png` }); };
    await T(`F ${name}: the File view on the song, full screen and Present, portrait and landscape, turned while open`, async () => {
      const c = await b.newContext({ ...dev }); const p = await c.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); await p.goto(SITE + '?f=' + Date.now()); await wait(1500);
      const o = {}, bad = [], need = (ok, what, v) => { if (!ok) bad.push(what + (v === undefined ? '' : ' ' + JSON.stringify(v))); };
      const vp = () => p.evaluate(() => ({ w: innerWidth, h: innerHeight, dpr: Math.min(3, devicePixelRatio || 1) }));
      const pagesReady = async (sel, n) => { for (let i = 0; i < 100; i++) { const k = await p.evaluate(([s, n]) => { const pg = document.querySelectorAll(s + ' .wfv-page'); return pg.length >= n && [...pg].slice(0, 1).every(e => e.classList.contains('drawn') && (e.querySelector('canvas,img'))); }, [sel, n]); if (k) return true; await wait(100); } return false; };
      /* every page showing in the box is drawn (after scrolling, turning or the next slide) */
      const allDrawn = async (box, ms) => { let r; for (let i = 0; i < (ms || 2500) / 100; i++) { r = await p.evaluate(sel => { const b = sel ? document.querySelector(sel) : null, br = b ? b.getBoundingClientRect() : { top: 0, bottom: innerHeight }, top = Math.max(0, br.top), bot = Math.min(innerHeight, br.bottom);
          const vis = [...document.querySelectorAll((sel || '#wfpages') + ' .wfv-page')].filter(e => { const q = e.getBoundingClientRect(); return q.bottom > top + 2 && q.top < bot - 2; }); return { n: vis.length, undrawn: vis.filter(e => !e.querySelector('canvas,img')).map(e => e.dataset.page) }; }, box);
          if (r.n && !r.undrawn.length) return true; await wait(100); } return r; };
      /* a page is fitted: as wide as its box (never wider than the screen), the right shape, drawn sharp for this screen */
      const fit = (sel, k) => p.evaluate(([sel, k]) => { const box = document.querySelector(sel), pg = box && box.querySelector('.wfv-page.drawn'); if (!pg) return { none: true };
        const cv = pg.querySelector('canvas'), r = pg.getBoundingClientRect(), dpr = Math.min(3, devicePixelRatio || 1), cap = cv ? Math.min(4096, 4096 * cv.width / cv.height, Math.floor(Math.sqrt(16.7e6 * cv.width / cv.height))) : 0;   /* the most a phone's canvas allows */
        return { pw: Math.round(r.width), bw: Math.round(box.clientWidth), ratio: +(r.height / r.width).toFixed(3), sharp: cv ? cv.width >= Math.min(cap, r.width * dpr * (k || 1)) * 0.9 : true, cw: cv && cv.width, docOver: document.documentElement.scrollWidth - innerWidth }; }, [sel, k]);
      // the song: a 40-page PDF, attached as a person would
      await p.evaluate(() => { $('#tabs [data-tab2=worship]').click(); WS.pane = 'songs'; WS.song = null; WS.set = null; WS.edit = null; render(); }); await wait(300); await p.click('[data-wnew]'); await wait(300);
      const [fc] = await Promise.all([p.waitForEvent('filechooser'), p.click('#wf-attach')]); await fc.setFiles(LONG); for (let i = 0; i < 60 && !(await p.evaluate(() => (WS.efile || []).length)); i++) await wait(100);
      await p.click('#wf-save'); await wait(300); const id = await p.evaluate(() => WS.song);
      need(await pagesReady('#wfpages', 40), 'inline pages never drew');
      o.in = await fit('#wfpages'); const v0 = await vp();
      need(o.in.pw === o.in.bw && o.in.pw <= 902, 'inline page not fitted to its box', o.in); need(Math.abs(o.in.ratio - 792 / 612) < 0.02, 'inline page wrong shape', o.in.ratio); need(o.in.sharp, 'inline page blurry', o.in); need(o.in.docOver <= 1, 'page wider than the screen', o.in.docOver);
      await p.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight / 3)); o.midIn = await allDrawn(null, 1500); need(o.midIn === true, 'inline: pages in view drawn after scrolling', o.midIn); await p.evaluate(() => window.scrollTo(0, 0)); await wait(300);
      o.acts = await p.evaluate(() => { const a = document.querySelector('[data-wffull]').getBoundingClientRect(), t = ($('#tabs') || document.body).getBoundingClientRect(); return a.top >= 0 && a.bottom <= Math.min(innerHeight, t.top || innerHeight); }); need(o.acts, 'Full screen button not in view without scrolling');
      o.backTop = await allDrawn(null, 2500); need(o.backTop === true, 'inline: back at the top, its pages drawn again', o.backTop); o.lazy = await p.evaluate(() => document.querySelectorAll('#wfpages canvas').length); need(o.lazy < 40 && o.lazy >= 1, 'every page drawn at once (or none)', o.lazy);
      await shot(p, '1-inline');
      // turned on the song screen
      await p.setViewportSize(rot.viewport); await wait(1200); o.inRot = await fit('#wfpages');
      need(o.inRot.pw === o.inRot.bw && o.inRot.sharp && o.inRot.docOver <= 1, 'inline page not refitted after turning', o.inRot); await shot(p, '2-inline-turned');
      await p.setViewportSize(dev.viewport); await wait(1000);
      // the browser's own full screen where it has one: taken on open, given back by Done
      if (await p.evaluate(() => document.fullscreenEnabled)) { await p.click('[data-wffull]'); await wait(900); o.fs = await p.evaluate(() => document.fullscreenElement && document.fullscreenElement.id);
        await p.click('#wfview .wfv-x'); await wait(700); o.fsOut = await p.evaluate(() => !document.fullscreenElement && !$('#wfview')); need(o.fs === 'wfview' && o.fsOut, 'real full screen in and out', [o.fs, o.fsOut]); }
      await p.evaluate(() => { WFile.fs = false; });   // the rest in the page's own full-screen view (what an iPhone always uses), so the test can turn the screen
      // full screen
      await p.click('[data-wffull]'); for (let i = 0; i < 80 && !(await p.evaluate(() => { const v = $('#wfview'); return v && v.dataset.ready; })); i++) await wait(100); await pagesReady('#wfview', 40);
      o.full = await p.evaluate(() => { const v = $('#wfview'), r = v.getBoundingClientRect(), bar = v.querySelector('.wfv-bar'), x = v.querySelector('.wfv-x').getBoundingClientRect(), mid = document.elementFromPoint(innerWidth / 2, innerHeight - 4);
        return { cover: Math.abs(r.left) < 1 && Math.abs(r.top) < 1 && Math.abs(r.width - innerWidth) < 1 && Math.abs(r.height - innerHeight) < 1, barFits: bar.scrollWidth <= bar.clientWidth + 1, done: x.top >= 0 && x.left >= 0 && x.right <= innerWidth && x.height >= 36 && x.width >= 36,
          above: v.contains(mid), n: v.querySelector('.wfv-n').textContent, locked: document.documentElement.classList.contains('wfv-open'), title: v.querySelector('.wfv-t').textContent, hist: !!(history.state && history.state.wfv) }; });
      need(o.full.cover && o.full.barFits && o.full.done && o.full.above && o.full.locked && o.full.hist, 'full screen layout', o.full); need(o.full.n === '1 / 40' || (await vp()).w <= 380, 'page counter', o.full.n);
      o.ffit = await fit('#wfview .wfv-z'); need(o.ffit.sharp && o.ffit.pw <= 982, 'full screen page fit', o.ffit);
      await shot(p, '3-full');
      // the last page: the counter follows, and pages far away are let go
      await p.evaluate(() => { const s = $('#wfview .wfv-sc'); s.scrollTop = s.scrollHeight; }); await wait(1200);
      o.end = await p.evaluate(() => ({ n: $('#wfview .wfv-n').textContent, drawn: document.querySelectorAll('#wfview canvas').length, last: !!document.querySelector('#wfview .wfv-page[data-page="40"].drawn') }));
      need(o.end.last && o.end.drawn < 40, 'far pages not let go / last page not drawn', o.end); if ((await vp()).w > 380) need(o.end.n === '40 / 40', 'counter at the end', o.end.n);
      await p.evaluate(() => { const s = $('#wfview .wfv-sc'); s.scrollTop = s.scrollHeight / 2; }); o.midFull = await allDrawn('#wfview .wfv-sc', 1500); need(o.midFull === true, 'full screen: pages in view drawn soon after a jump', o.midFull);
      await p.evaluate(() => { $('#wfview .wfv-sc').scrollTop = 0; }); await wait(500);
      // zoom: the buttons (or keys), double-tap / double-click, pinch on touch screens, Ctrl+scroll on computers
      const zoomOf = () => p.evaluate(() => +($('#wfview').dataset.zoom || 1));
      if (await p.evaluate(() => getComputedStyle(document.querySelector('#wfview .wfv-zi')).display !== 'none')) { await p.click('#wfview .wfv-zi'); } else await p.keyboard.press('+');
      await wait(900); o.z1 = { z: await zoomOf(), f: await fit('#wfview .wfv-z', await zoomOf()), h: await p.evaluate(() => { const s = $('#wfview .wfv-sc'); return s.scrollWidth > s.clientWidth + 2; }) };
      need(o.z1.z === 1.5 && o.z1.f.sharp && o.z1.h, 'zoom in: bigger, sharp, scrolls sideways', o.z1);
      await p.keyboard.press('0'); await wait(400); need(await zoomOf() === 1, 'fit again');
      await p.dblclick('#wfview .wfv-page[data-page="1"]'); await wait(300); o.dbl = await zoomOf(); await p.dblclick('#wfview .wfv-page[data-page="1"]'); await wait(300); need(o.dbl > 2 && (await zoomOf()) === 1, 'double-tap zoom and back', o.dbl);
      if (touch && !WK) { o.pinch = await p.evaluate(async () => { const s = $('#wfview .wfv-sc'), r = s.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + 200; const T = (id, x, y) => new Touch({ identifier: id, target: s, clientX: x, clientY: y });
          s.dispatchEvent(new TouchEvent('touchstart', { touches: [T(1, cx - 40, cy), T(2, cx + 40, cy)], bubbles: true, cancelable: true }));
          s.dispatchEvent(new TouchEvent('touchmove', { touches: [T(1, cx - 100, cy), T(2, cx + 100, cy)], bubbles: true, cancelable: true }));
          s.dispatchEvent(new TouchEvent('touchend', { touches: [], bubbles: true })); await new Promise(r => setTimeout(r, 200)); return +$('#wfview').dataset.zoom; }); need(o.pinch > 2, 'pinch zoom', o.pinch); await p.keyboard.press('0'); }
      if (!touch) { await p.mouse.move(400, 400); await p.keyboard.down('Control'); await p.mouse.wheel(0, -300); await p.keyboard.up('Control'); await wait(300); o.wheel = await zoomOf(); need(o.wheel > 1.5, 'Ctrl+scroll zoom', o.wheel); await p.keyboard.press('0'); }
      // turned while open
      await p.setViewportSize(rot.viewport); await wait(1300);
      o.rot = await p.evaluate(() => { const v = $('#wfview'), r = v.getBoundingClientRect(), bar = v.querySelector('.wfv-bar'), x = v.querySelector('.wfv-x').getBoundingClientRect(); return { cover: Math.abs(r.width - innerWidth) < 1 && Math.abs(r.height - innerHeight) < 1, barFits: bar.scrollWidth <= bar.clientWidth + 1, done: x.right <= innerWidth && x.bottom <= innerHeight }; });
      o.rotFit = await fit('#wfview .wfv-z'); need(o.rot.cover && o.rot.barFits && o.rot.done && o.rotFit.sharp && o.rotFit.pw <= 982, 'turned while open', [o.rot, o.rotFit]);
      await shot(p, '4-full-turned'); await p.setViewportSize(dev.viewport); await wait(900);
      // Done collapses it back to the song, with focus back on Full screen
      await p.click('#wfview .wfv-x'); await wait(400);
      o.done = await p.evaluate(id => ({ gone: !$('#wfview'), unlocked: !document.documentElement.classList.contains('wfv-open'), song: WS.song === id && view === 'worship', focus: document.activeElement && document.activeElement.hasAttribute('data-wffull'), hist: !(history.state && history.state.wfv) }), id);
      need(o.done.gone && o.done.unlocked && o.done.song && o.done.focus && o.done.hist, 'Done', o.done);
      // Esc, and the back button, collapse it too, and never leave the song
      await p.click('[data-wffull]'); await wait(500); await p.keyboard.press('Escape'); await wait(400); o.esc = await p.evaluate(id => !$('#wfview') && WS.song === id, id); need(o.esc, 'Esc');
      const url = p.url(); await p.click('[data-wffull]'); await wait(500); await p.goBack(); await wait(600);
      o.back = await p.evaluate(id => ({ gone: !$('#wfview'), song: WS.song === id && view === 'worship' }), id); need(o.back.gone && o.back.song && p.url() === url, 'back button', [o.back, p.url() === url]);
      // a tap on page 3 opens full screen at page 3
      await p.evaluate(() => document.querySelector('#wfpages .wfv-page[data-page="3"]').scrollIntoView({ block: 'center' })); await wait(500); await p.click('#wfpages .wfv-page[data-page="3"]'); await wait(1200);
      o.tap = await p.evaluate(() => { const v = $('#wfview'); if (!v) return null; const pg = v.querySelector('.wfv-page[data-page="3"]').getBoundingClientRect(), sc = v.querySelector('.wfv-sc').getBoundingClientRect(); return Math.abs(pg.top - sc.top) < 30; });
      need(o.tap, 'tap a page: full screen at that page', o.tap); await p.keyboard.press('Escape'); await wait(300);
      // photos: a tall and a wide one, each its own page and shape
      o.photos = await p.evaluate(async () => { const mk = (w, h, col) => new Promise(r => { const c = document.createElement('canvas'); c.width = w; c.height = h; const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, w, h); x.fillStyle = col; x.font = '60px sans-serif'; x.fillText('made-up chart', 40, 120); c.toBlob(b => r(new File([b], w + 'x' + h + '.png', { type: 'image/png' })), 'image/png'); });
        const refs = await WFile.add([await mk(600, 1600, '#246'), await mk(1600, 600, '#642')]); const all = wSongs(), id = wId(); all[id] = { id, t: 'Two photos', a: '', src: '', file: refs }; S.set('wsongs', all); WS.song = id; render();
        for (let i = 0; i < 50; i++) { const pg = document.querySelectorAll('#wfpages .wfv-page.drawn img'); if (pg.length === 2 && pg[1].complete) break; await new Promise(r => setTimeout(r, 100)); }
        return [...document.querySelectorAll('#wfpages .wfv-page')].map(e => { const r = e.getBoundingClientRect(); return +(r.height / r.width).toFixed(2); }); });
      need(o.photos.length === 2 && Math.abs(o.photos[0] - 1600 / 600) < 0.03 && Math.abs(o.photos[1] - 600 / 1600) < 0.03, 'photos as pages, right shapes', o.photos); await shot(p, '5-photos');
      // a landscape PDF page keeps its shape
      o.wide = await p.evaluate(async b64 => { const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0)); const refs = await WFile.add([new File([bin], 'wide.pdf', { type: 'application/pdf' })]); const all = wSongs(), id = wId(); all[id] = { id, t: 'Wide', a: '', src: '', file: refs }; S.set('wsongs', all); WS.song = id; render();
        for (let i = 0; i < 80; i++) { const pg = document.querySelector('#wfpages .wfv-page.drawn'); if (pg) { const r = pg.getBoundingClientRect(); return +(r.height / r.width).toFixed(3); } await new Promise(r => setTimeout(r, 100)); } return null; }, WIDE.buffer.toString('base64'));
      need(o.wide && Math.abs(o.wide - 612 / 792) < 0.02, 'landscape PDF page shape', o.wide);
      // Present on the leader's screen: File draws, keeps your place through Next, opens full screen, Done returns to it
      await p.evaluate(id => { S.set('wsets', [{ id: 'fv', name: 'File test', items: [{ id }] }]); WS.song = null; WS.set = 'fv'; render(); }, id); await wait(200);
      await p.click('[data-wpresentset]'); await p.waitForURL(/live\//, { timeout: 10000 }); await wait(1800);
      for (let i = 0; i < 40 && !(await p.$('.seg [data-v=file]')); i++) await wait(150);
      if (await p.evaluate(() => getComputedStyle(document.querySelector('.seg')).display !== 'none')) {
        await p.click('.seg [data-v=file]'); await pagesReady('#fileview', 40);
        o.pres = await p.evaluate(() => { const f = document.querySelector('#fileview'), r = f.getBoundingClientRect(), bar = document.querySelector('#bar').getBoundingClientRect(), pg = f.querySelector('.wfv-page.drawn'); return { inView: r.top >= 0 && r.bottom <= bar.top + 1 && r.height > 120, fits: pg && Math.abs(pg.getBoundingClientRect().width - f.clientWidth) < 8, over: document.documentElement.scrollWidth - innerWidth }; });
        need(o.pres.inView && o.pres.fits && o.pres.over <= 1, 'Present File view layout', o.pres); await shot(p, '6-present');
        await p.evaluate(() => { document.querySelector('#fileview').scrollTop = 1500; document.querySelector('#fileview').dispatchEvent(new Event('scroll')); }); await wait(200); await p.click('#bNext'); await wait(500);
        o.keep = await p.evaluate(() => document.querySelector('#fileview') ? document.querySelector('#fileview').scrollTop : -1); need(o.keep >= 1400, 'Present keeps your place through Next', o.keep);
        o.keepDrawn = await allDrawn('#fileview', 1500); need(o.keepDrawn === true, 'Present: pages in view drawn after Next', o.keepDrawn);
        await p.click('#fileview .fsbtn'); await wait(900); o.pfull = await p.evaluate(() => !!document.querySelector('#wfview')); await p.click('#wfview .wfv-x'); await wait(500);
        o.pback = await p.evaluate(() => !document.querySelector('#wfview') && !!document.querySelector('#fileview') && /live\//.test(location.href)); need(o.pfull && o.pback, 'Present full screen and Done', [o.pfull, o.pback]);
        await p.setViewportSize(rot.viewport); await wait(1200); o.prot = await p.evaluate(() => { const f = document.querySelector('#fileview'); if (!f) return 'wide layout'; const pg = f.querySelector('.wfv-page.drawn'), bar = document.querySelector('#bar').getBoundingClientRect(), r = f.getBoundingClientRect(); return { fits: !pg || Math.abs(pg.getBoundingClientRect().width - f.clientWidth) < 8, inView: r.bottom <= bar.top + 1, over: document.documentElement.scrollWidth - innerWidth }; });
        need(o.prot === 'wide layout' || (o.prot.fits && o.prot.over <= 1), 'Present turned', o.prot);
        if (o.prot !== 'wide layout') { o.protDrawn = await allDrawn('#fileview', 2500); need(o.protDrawn === true, 'Present turned: pages in view drawn', o.protDrawn); } await shot(p, '7-present-turned');
      } else o.pres = 'wide presenter layout';
      await p.evaluate(() => { try { localStorage.setItem('scwp:view', 'lyrics'); } catch (e) { } });
      need(!errs.length, 'page errors', errs.slice(0, 3)); await c.close();
      return !bad.length || { bad, o };
    });
  }
  if (!ONLY || ONLY.test("offline")) await T('F offline: with no connection at all, a song\'s PDF still opens (pdf.js comes from the phone\'s offline copy)', async () => {
    const c = await b.newContext({ ...devices['iPhone 14'] }); const p = await c.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); await p.goto(SITE + '?o=' + Date.now()); await wait(1500);
    const sw = await p.evaluate(async () => { if (!navigator.serviceWorker) return 'none'; const r = await Promise.race([navigator.serviceWorker.ready, new Promise(ok => setTimeout(() => ok(null), 8000))]); return r ? 'ready' : 'none'; });
    if (sw !== 'ready') { await c.close(); return true; }   // an engine without the offline helper here: nothing to test
    await p.reload(); await wait(1500);
    for (let i = 0; i < 60 && !(await p.evaluate(() => caches.open('sc-pdf-4.10.38').then(c => c.keys()).then(k => k.length >= 2))); i++) await wait(150);
    await p.evaluate(async b64 => { const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0)); const refs = await WFile.add([new File([bin], 'off.pdf', { type: 'application/pdf' })]); const all = wSongs(), id = wId(); all[id] = { id, t: 'Offline', a: '', src: '', file: refs }; S.set('wsongs', all); window.__id = id; }, WIDE.buffer.toString('base64'));
    if (WK) {   /* Playwright's WebKit offline mode stops every request before the offline helper can answer (even the app's own worship.js), so here: pdf.js is in the phone's offline copy, whole */
      const kept = await p.evaluate(async () => { const c = await caches.open('sc-pdf-4.10.38'); const out = []; for (const f of ['pdf/pdf.min.mjs?v=4.10.38', 'pdf/pdf.worker.min.mjs?v=4.10.38']) { const r = await c.match(f); out.push(r && r.ok ? (await r.arrayBuffer()).byteLength : 0); } return out; });
      await c.close(); return (kept[0] > 300000 && kept[1] > 1000000) || { kept }; }
    const id = await p.evaluate(() => __id); await c.setOffline(true); await wait(300);   // no connection from here (pdf.js not yet loaded on this page)
    await p.evaluate(id => { $('#tabs [data-tab2=worship]').click(); WS.song = id; WS.edit = null; render(); }, id);
    let ok = false; for (let i = 0; i < 80 && !ok; i++) { ok = await p.evaluate(() => !!document.querySelector('#wfpages .wfv-page canvas')); if (!ok) await wait(100); }
    const msg = await p.evaluate(() => (document.querySelector('#wfpages .wfv-msg') || {}).textContent || ''); await c.close();
    return (ok && !errs.filter(e => !/access control checks/.test(e)).length) || { ok, msg, errs }; });
  const f = R.filter(r => !r[1].startsWith('PASS')).length; console.log(`\n${R.length - f}/${R.length} passed`); await b.close(); process.exit(f ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });

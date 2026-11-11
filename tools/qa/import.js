// QA: importing a song, all the way through, in the app — for every chart format: paste into Add a song (a whole
// chord-site page too), Save, the song screen (every section in order, repeats in full, every chord drawn), change
// the key, reload, Edit → Save unchanged, put it in a setlist and Present. Made-up songs only.
//   SITE=http://localhost:8765/ [BROWSER=webkit] node tools/qa/import.js
const { chromium, webkit, devices } = require('playwright');
const ENGINE = process.env.BROWSER === 'webkit' ? webkit : chromium;
const SITE = process.env.SITE || 'http://localhost:8765/';
require('../../site_extra/worship.js'); const W = globalThis.Worship;
const F = require('./chart_fixtures.js');
const R = []; const wait = ms => new Promise(r => setTimeout(r, ms));
async function T(n, f) { let r; try { r = await Promise.race([f(), new Promise((_, no) => setTimeout(() => no(new Error('took over 3 minutes')), 180000))]); } catch (e) { r = 'threw ' + String(e).slice(0, 300); }
  R.push([n, r === true ? 'PASS' : 'FAIL ' + (typeof r === 'string' ? r : JSON.stringify(r)).slice(0, 900)]); console.log(R[R.length - 1][1].startsWith('PASS') ? 'PASS' : 'FAIL', n, R[R.length - 1][1].startsWith('PASS') ? '' : R[R.length - 1][1].slice(5)); }
// a whole chord-site page around a made-up chart, as a person would copy it
const PAGE = `Search
Lantern Road Chords by Test Band
1,204 views, added to favorites 31 times
Rating: ★ 4.9 / 5 (12)
Difficulty: Beginner
Tuning: E A D G B E
Key: G
CHORDS
G
2 1   3
PLAY
VIEW IN APP
TRANSPOSE
LISTEN
PDF

[Verse 1]
G              C      G
Walking down a lantern road
C              G/B    Am7
Carrying a borrowed load
ADVERTISEMENT
OPEN IN APP

[Chorus]
G             Em
Sing it softly, sing it slowly
C             D
Every step a place to go

[Verse 2]
G              C      G
Morning comes across the field

[Chorus]

[Bridge]
Am7      G/B      C    D
Home is near, home is near

Print
Report Bad Tab
Please rate this tab
★★★★★ 12`;
const CASES = [
  ['ChordPro, every feature', F.chordproFull.src, F.chordproFull.labels, { t: 'Lantern Road', a: 'Test Band', k: 'G' }],
  ['ChordPro short forms', F.chordproShort.src, F.chordproShort.labels, { t: 'Harbor Light', a: 'Test Band', k: 'D' }],
  ['chords over the words', F.chordsOverLyrics.src, F.chordsOverLyrics.labels, null],
  ['[bracketed] headings', F.bracketed.src, F.bracketed.labels, null],
  ['ALL-CAPS headings with counts', F.allCaps.src, F.allCaps.labels, null],
  ['bars, N.C. and x2 marks', F.barsAndMarks.src, F.barsAndMarks.labels, null],
  ['a whole chord-site page', PAGE, ['Verse 1', 'Chorus', 'Verse 2', 'Chorus*', 'Bridge'], { t: 'Lantern Road', a: 'Test Band', k: 'G' }],
];
const heading = l => { const m = /^(.*?)(?: x(\d+))?(\*)?$/.exec(l); return m[1] + (m[2] ? ' ×' + m[2] : '') + (m[3] ? ' (repeat)' : ''); };

(async () => {
  const b = await ENGINE.launch(); const errs = [];
  const page = async () => { const c = await b.newContext(devices['iPhone 14']); const p = await c.newPage(); p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept()); await p.goto(SITE + '?i=' + Date.now()); await wait(900); return p; };
  for (const [name, src, labels, fields] of CASES) {
    await T(`I ${name}: pasted, saved, shown in full (every section in order, repeats in full, every chord), the key changes every chord, a reload and an unchanged Edit → Save keep it exactly, and Present carries every sung part`, async () => {
      const p = await page(), out = {};
      await p.evaluate(() => { $('#tabs [data-tab2=worship]').click(); }); await wait(300);
      await p.evaluate(() => { WS.pane = 'songs'; WS.song = null; WS.set = null; WS.edit = null; render(); }); await p.click('[data-wnew]'); await wait(250);
      await p.focus('#wf-src');
      await p.evaluate(t => { const dt = new DataTransfer(); dt.setData('text/plain', t); const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }); const box = $('#wf-src'); if (box.dispatchEvent(ev)) { box.value = t; box.dispatchEvent(new Event('input')); } }, src);
      out.fields = await p.evaluate(() => ({ t: $('#wf-t').value, a: $('#wf-a').value, k: $('#wf-k').value }));
      if (!out.fields.t) await p.fill('#wf-t', 'Test ' + name);
      const saved0 = await p.evaluate(() => $('#wf-src').value);
      await p.click('#wf-save'); await wait(500);
      const id = await p.evaluate(() => WS.song);
      const song = await p.evaluate(id => S.get('wsongs')[id], id);
      const parsed = W.parse(song.src), wantChords = parsed.sections.reduce((a, s) => a + s.lines.reduce((x, l) => x + (l ? l.chords.length : 0), 0), 0);
      const view = async () => p.evaluate(() => ({ h: [...document.querySelectorAll('#wfit .wc-h')].map(x => x.textContent), c: [...document.querySelectorAll('#wfit .wc-c')].map(x => x.textContent).filter(Boolean) }));
      const v1 = await view();
      // the key, a step up
      if (!(await p.$('.w-tools'))) { await p.click('[data-wtools]'); await wait(150); }
      const k0 = await p.evaluate(id => wKeyOf(S.get('wsongs')[id]), id);
      let v2 = null, kOk = true;
      if (k0) { await p.click('[data-wk="1"]'); await wait(300); v2 = await view(); const k1 = W.transposeKey(k0, 1), flats = W.useFlats(k1);
        kOk = v2.c.length === v1.c.length && v2.c.every((c, i) => c === W.transposeChord(v1.c[i], 1, flats)); await p.click('[data-wk="-1"]'); await wait(200); }
      // reload, then Edit → Save with no change
      await p.reload(); await wait(900); await p.evaluate(id => { $('#tabs [data-tab2=worship]').click(); WS.song = id; WS.edit = null; render(); }, id); await wait(300);
      const v3 = await view();
      await p.evaluate(id => { WS.edit = id; render(); }, id); await wait(200); await p.click('#wf-save'); await wait(300);
      const kept = await p.evaluate(([id, s]) => S.get('wsongs')[id].src === s, [id, song.src]);
      // a setlist with it, presented
      await p.evaluate(id => { S.set('wsets', [{ id: 'imp', name: 'Import test', items: [{ id }] }]); WS.song = null; WS.set = 'imp'; WS.edit = null; render(); }, id); await wait(200);
      await p.click('[data-wpresentset]'); await p.waitForURL(/live\//, { timeout: 10000 }); await wait(1500);
      const deck = await p.evaluate(() => JSON.parse(localStorage.getItem('sc:wlive')).deck);
      const live = await p.evaluate(() => [...document.querySelectorAll('.wc-h')].map(x => x.textContent));
      const wantSlides = W.slides({ parsed }).length, gotSlides = (deck.songs[0] || {}).slides ? deck.songs[0].slides.length : -1;
      await p.context().close();
      const wantH = labels.map(heading);
      const ok = JSON.stringify(v1.h) === JSON.stringify(wantH) && v1.c.length === wantChords && kOk && JSON.stringify(v3) === JSON.stringify(v1) && kept
        && (!fields || (out.fields.t === fields.t && out.fields.a === fields.a && out.fields.k === fields.k)) && (name !== 'a whole chord-site page' || !/ADVERTISEMENT|Report Bad Tab|Rating|PLAY|VIEW IN APP/.test(saved0))
        && deck.songs[0] && deck.songs[0].id === id && deck.set.join() === '0' && gotSlides === wantSlides && wantH.filter(h => / \(repeat\)$/.test(h)).every(h => live.includes(h));
      return ok || { h: v1.h, wantH, chords: [v1.c.length, wantChords], kOk, reload: JSON.stringify(v3) === JSON.stringify(v1), kept, fields: out.fields, slides: [gotSlides, wantSlides], live: live.slice(0, 12) };
    });
  }
  await T('I no page errors anywhere in the import runs', async () => errs.length === 0 || errs.slice(0, 5));
  const f = R.filter(r => !r[1].startsWith('PASS')).length; console.log(`\n${R.length - f}/${R.length} passed`); await b.close(); process.exit(f ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });

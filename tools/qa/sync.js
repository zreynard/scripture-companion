// QA: sync between devices, against a fake private repo (no real GitHub, no real backup touched). SITE=... node tools/qa/sync.js
const { chromium, devices } = require('playwright'); const wait = ms => new Promise(r => setTimeout(r, ms));
const SITE = process.env.SITE || 'http://localhost:8765/';
(async () => { const b = await chromium.launch(); const store = { file: null, sha: 0, puts: 0 }; const R = [];
  // a fake private repo: GET/PUT progress.json with sha checks, like GitHub
  const fake = async route => { const req = route.request(), u = req.url();
    if (/\/contents\/progress\.json/.test(u)) {
      if (req.method() === 'GET') return store.file ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ sha: 's' + store.sha, encoding: 'base64', content: store.file }) }) : route.fulfill({ status: 404, body: '{}' });
      const body = JSON.parse(req.postData()); if (store.file && body.sha !== 's' + store.sha) return route.fulfill({ status: 409, body: '{}' });
      store.file = body.content; store.sha++; store.puts++; return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ content: { sha: 's' + store.sha } }) }); }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ private: true, permissions: { push: true } }) }); };
  const dev = async name => { const c = await b.newContext(devices['iPhone 14']); await c.route(/api\.github\.com/, fake); await c.addInitScript(() => { try { localStorage.setItem('sc:bkkey', JSON.stringify('fake-key')); localStorage.setItem('sc:bkrepo', JSON.stringify('me/backup')); } catch (e) {} });
    const p = await c.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); await p.goto(SITE); await wait(2500); return { c, p, errs }; };
  const T = (n, ok, why) => { R.push((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + JSON.stringify(why).slice(0, 300))); };
  const sync = (D, why = 'pull') => D.p.evaluate(w => bkSync(w), why);
  const A = await dev('A');
  await A.p.evaluate(() => { read['Gen1'] = true; S.set('read', read); S.set('fav', { x1: Date.now() }); prog['ep1'] = { pos: 100, dur: 600, at: Date.now() - 60000 }; prog['ep2'] = { pos: 50, done: true, at: Date.now() - 60000 }; S.set('prog', prog); S.set('wsongs', { s1: { id: 's1', t: 'Alpha', src: 'Verse\nG\nla' } }); S.set('speed', 1.25); S.set('camp', 5); S.set('bedlv', 0.33); });
  await sync(A); const B = await dev('B');
  await B.p.evaluate(() => { read['Exo1'] = true; S.set('read', read); const f = S.get('fav', {}); f.y1 = Date.now(); S.set('fav', f); prog['ep1'] = { pos: 200, dur: 600, at: Date.now() }; prog['ep2'] = Object.assign(prog['ep2'] || {}, { pos: 10, at: Date.now() }); delete prog['ep2'].done; S.set('prog', prog); });
  await sync(B); await sync(A);
  const a1 = await A.p.evaluate(() => ({ read: Object.keys(S.get('read', {})).sort(), fav: Object.keys(S.get('fav', {})).sort(), ep1: S.get('prog', {}).ep1, ep2done: !!(S.get('prog', {}).ep2 || {}).done, songs: Object.keys(S.get('wsongs', {})), speed: S.get('speed'), lv: S.get('bedlv'), memRead: Object.keys(read).sort() }));
  const b1 = await B.p.evaluate(() => ({ read: Object.keys(S.get('read', {})).sort(), fav: Object.keys(S.get('fav', {})).sort(), songs: Object.keys(S.get('wsongs', {})), speed: S.get('speed'), lv: S.get('bedlv'), memSpeed: speed }));
  T('S1 progress from both devices adds together (chapters read, favorites)', a1.read.join() === 'Exo1,Gen1' && b1.read.join() === 'Exo1,Gen1' && a1.fav.join() === 'x1,y1' && b1.fav.join() === 'x1,y1', { a1, b1 });
  T('S2 listening position: the newest wins; finished on either device stays finished', a1.ep1 && a1.ep1.pos === 200 && a1.ep2done, a1);
  T('S3 songs and settings reach the other device (and its memory, not only storage)', b1.songs.join() === 's1' && b1.speed === 1.25 && b1.lv === 0.33 && b1.memSpeed === 1.25, b1);
  T('S4 the app on screen updates its own copy too', a1.memRead.join() === 'Exo1,Gen1', a1);
  // removal on B reaches A; a song deleted on A stays deleted on B
  await B.p.evaluate(() => { const f = S.get('fav', {}); delete f.x1; S.set('fav', f); }); await sync(B); await sync(A);
  await A.p.evaluate(() => { S.set('wsongs', {}); }); await sync(A); await sync(B);
  const a2 = await A.p.evaluate(() => Object.keys(S.get('fav', {}))), b2 = await B.p.evaluate(() => Object.keys(S.get('wsongs', {})));
  T('S5 a favorite removed on one device is removed on the other', a2.join() === 'y1', a2);
  T('S6 a song deleted on one device does not come back from the other', b2.length === 0, b2);
  // where you are: while in use, each device keeps its own place; opening takes the newest
  await B.p.evaluate(() => S.set('camp', 9)); await sync(B); await sync(A, 'pull'); const keep = await A.p.evaluate(() => S.get('camp')); await sync(A, 'open'); const open = await A.p.evaluate(() => S.get('camp'));
  T('S7 while in use a device keeps its own place; opening it picks up where you left off on the other', keep === 5 && open === 9, { keep, open });
  // both save at the same moment: nothing is lost (a stale save is retried after merging)
  await A.p.evaluate(() => { read['Lev1'] = true; S.set('read', read); }); await B.p.evaluate(() => { read['Num1'] = true; S.set('read', read); });
  await Promise.all([sync(A), sync(B)]); await sync(A); await sync(B);
  const a3 = await A.p.evaluate(() => Object.keys(S.get('read', {})).sort()), b3 = await B.p.evaluate(() => Object.keys(S.get('read', {})).sort());
  T('S8 two devices saving at once lose nothing', a3.join() === b3.join() && ['Lev1', 'Num1', 'Gen1', 'Exo1'].every(x => a3.includes(x)), { a3, b3 });
  // an old v1 backup (no change times) merges without losing this device's newer data
  const C = await dev('C'); await C.p.evaluate(() => { read['Deu1'] = true; S.set('read', read); }); await sync(C); const c1 = await C.p.evaluate(() => Object.keys(S.get('read', {})).sort());
  T('S9 a new device joins: it gets everything and adds its own', ['Gen1', 'Exo1', 'Lev1', 'Num1', 'Deu1'].every(x => c1.includes(x)), c1);
  T('S10 no page errors', [A, B, C].every(d => d.errs.length === 0), [A, B, C].map(d => d.errs));
  console.log(R.join('\n')); const f = R.filter(x => x.startsWith('FAIL')).length; console.log(`\n${R.length - f}/${R.length} passed`); await b.close(); process.exit(f ? 1 : 0); })();

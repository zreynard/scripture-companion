// Every Be Led prayer and Meditate reading, played for real in a browser engine: does the recording load, open at the
// stretch's start (a time fragment, as the app does) and play on past it? Also the file's length as the engine reports it
// (Be Led's start counts back from it) and whether the MP3 is variable bitrate (an iPhone jumps inside those inexactly).
//   SITE=http://localhost:8765/ BROWSER=webkit|chromium node tools/qa/pray_audio.js  -> one JSON line per recording, then a summary
const { chromium, webkit } = require('playwright');
const ENGINE = process.env.BROWSER === 'webkit' ? webkit : chromium;
const SITE = process.env.SITE || 'http://localhost:8765/';
const UA = 'scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)';

async function vbr(url) {   // the first frame of the MP3: a Xing or VBRI header means variable bitrate ("Info" is constant)
  try {
    const r = await fetch(url, { headers: { Range: 'bytes=0-200000', 'User-Agent': UA }, redirect: 'follow' });
    const b = Buffer.from(await r.arrayBuffer());
    let p = 0;
    if (b.slice(0, 3).toString() === 'ID3') p = 10 + ((b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9]);
    while (p < b.length - 4 && !(b[p] === 0xff && (b[p + 1] & 0xe0) === 0xe0)) p++;
    const head = b.slice(p, p + 200).toString('latin1');
    if (/Xing|VBRI/.test(head)) return 'vbr';
    if (/Info/.test(head)) return 'cbr';
    return /\.m4a|\.mp4/i.test(url) ? 'mp4' : 'cbr?';
  } catch (e) { return 'unknown'; }
}

(async () => {
  const b = await ENGINE.launch(ENGINE === chromium ? { args: ['--autoplay-policy=no-user-gesture-required'] } : {});
  const p = await (await b.newContext()).newPage();
  await p.goto(SITE + '?x=' + Date.now()); await p.waitForTimeout(1500);
  const L = await p.evaluate(() => [...(PRAY.led || []).map(x => ({ kind: 'led', id: x.id, who: x.who, url: x.audio, sb: x.sb, e: x.e })),
                                     ...(PRAY.med || []).filter(x => x.audio).map(x => ({ kind: 'med', id: x.ref, who: x.who, url: x.audio, a: x.a, b: x.b }))]);
  const out = []; let k = 0;
  async function one(x) {
    if (/buzzsprout\.com/.test(x.url)) { return { ...x, ok: null, note: 'Buzzsprout refuses GitHub servers: not checked here' }; }
    const r = await p.evaluate(async x => {
      const a = new Audio(); a.muted = true; a.preload = 'metadata';
      const wait = (ev, ms) => new Promise(ok => { const t = setTimeout(() => ok(false), ms); a.addEventListener(ev, () => { clearTimeout(t); ok(true) }, { once: true }); });
      a.src = x.url; if (!await wait('loadedmetadata', 30000)) return { ok: false, note: 'no metadata in 30 s', err: a.error && a.error.code };
      const L = a.duration, t0 = x.kind === 'led' ? L - x.sb : x.a, end = x.kind === 'led' ? L - x.e : x.b;
      a.src = x.url + '#t=' + t0.toFixed(2);
      const pl = wait('playing', 25000); a.play().catch(() => {});
      if (!await pl) return { ok: false, L, note: 'did not start playing in 25 s', err: a.error && a.error.code };
      const at = a.currentTime; const t1 = Date.now();
      while (a.currentTime < t0 + 1 && Date.now() - t1 < 20000) await new Promise(r => setTimeout(r, 200));
      const moved = a.currentTime >= t0 + 1;
      a.currentTime = Math.max(t0, end - 1.5); const sk = await wait('seeked', 15000);
      a.pause(); a.removeAttribute('src'); a.load();
      return { ok: moved && Math.abs(at - t0) < 1.5 && sk, L: +L.toFixed(2), t0: +t0.toFixed(2), opened_at: +at.toFixed(2), moved, seek_end: sk };
    }, x).catch(e => ({ ok: false, note: String(e).slice(0, 120) }));
    return { ...x, ...r, mp3: await vbr(x.url) };
  }
  const q = [...L];
  await Promise.all([...Array(4)].map(async () => { while (q.length) { const x = q.shift(); const r = await one(x); out.push(r); console.log(JSON.stringify({ n: ++k, of: L.length, ...r })); } }));
  const bad = out.filter(r => r.ok === false), vb = out.filter(r => r.mp3 === 'vbr');
  console.log(`\n${process.env.BROWSER || 'chromium'}: ${out.filter(r => r.ok).length} play, ${bad.length} fail, ${out.filter(r => r.ok === null).length} not checked, ${vb.length} variable bitrate, of ${out.length}`);
  for (const r of bad) console.log('FAIL', r.kind, r.id, r.who, r.note || '', r.err || '');
  await b.close();
})();

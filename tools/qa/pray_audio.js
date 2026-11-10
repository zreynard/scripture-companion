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
  const SLOW = process.env.THROTTLE === 'fast3g';   // a phone on a weak connection: 1.6 Mbps, 150 ms (Chromium)
  if (SLOW) { const cdp = await p.context().newCDPSession(p); await cdp.send('Network.enable'); await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: 1.6e6 / 8, uploadThroughput: 750e3 / 8 }); }
  await p.goto(SITE + '?x=' + Date.now()); await p.waitForTimeout(1500);
  const L = await p.evaluate(() => [...(PRAY.led || []).map(x => ({ kind: 'led', id: x.id, who: x.who, url: x.audio, audio: x.audio, sb: x.sb, e: x.e, L: x.L, dur: x.dur })),
                                     ...(PRAY.med || []).filter(x => x.audio).map(x => ({ kind: 'med', id: x.ref, who: x.who, url: x.audio, a: x.a, b: x.b })),
                                     ...(PRAY.lp ? [{ kind: 'med', id: "Lord's Prayer", who: PRAY.lp.who, url: PRAY.lp.audio, a: PRAY.lp.a, b: PRAY.lp.b }] : [])]);
  const out = []; let k = 0;
  async function one(x) {
    if (/buzzsprout\.com/.test(x.url)) { return { ...x, ok: null, note: 'Buzzsprout refuses GitHub servers: not checked here' }; }
    const r = await p.evaluate(async x => {
      // the app's own player (clipper), exactly as Be Led and Meditate use it
      const c = clipper(new Audio(), {}); c.rate = 1;
      let t0, end, fix = null;
      if (x.kind === 'med') { t0 = x.a; end = x.b; }
      else { [t0, end] = ledSpan(x); fix = d => { if (isFinite(d) && d > 0) { const [s, e] = ledSpan(x, d); c.t0 = s; c.end = e } }; }
      const tap = Date.now(); c.go(x.url, t0, end, fix);
      const t = Date.now(); while (c.state !== 'playing' && c.state !== 'error' && Date.now() - t < 30000) await new Promise(r => setTimeout(r, 100));
      if (c.state !== 'playing') { const st = c.state; c.clear(); return { ok: false, note: 'state ' + st + ' after 30 s', err: c.a.error && c.a.error.code }; }
      const ms = Date.now() - tap;
      await new Promise(r => setTimeout(r, 1500));
      const at = c.a.currentTime, T0 = c.t0, L = c.a.duration;
      const near = at >= T0 - 0.3 && at <= T0 + 4;              // playing from the stretch's start
      let stop = null;
      if (x.kind === 'med') {                                      // and stopping at its end
        c.a.currentTime = Math.max(c.t0, c.end - 1.2);
        const t2 = Date.now(); while (c.state !== 'ended' && Date.now() - t2 < 15000) await new Promise(r => setTimeout(r, 50));
        stop = c.state === 'ended' ? +(c.a.currentTime - c.end).toFixed(2) : null;
      }
      c.clear();
      return { ok: near && (x.kind !== 'med' || (stop !== null && Math.abs(stop) <= 0.3)), ms, L: isFinite(L) ? +L.toFixed(2) : null, t0: +T0.toFixed(2), at: +at.toFixed(2), stop };
    }, x).catch(e => ({ ok: false, note: String(e).slice(0, 120) }));
    return { ...x, ...r, mp3: await vbr(x.url) };
  }
  const q = [...L];
  await Promise.all([...Array(SLOW ? 1 : 4)].map(async () => { while (q.length) { const x = q.shift(); const r = await one(x); out.push(r); console.log(JSON.stringify({ n: ++k, of: L.length, ...r })); } }));
  const bad = out.filter(r => r.ok === false), vb = out.filter(r => r.mp3 === 'vbr');
  console.log(`\n${process.env.BROWSER || 'chromium'}: ${out.filter(r => r.ok).length} play, ${bad.length} fail, ${out.filter(r => r.ok === null).length} not checked, ${vb.length} variable bitrate, of ${out.length}`);
  for (const r of bad) console.log('FAIL', r.kind, r.id, r.who, r.note || '', r.err || '');
  const by = {}; out.filter(r => r.ms).forEach(r => { const h = new URL(r.url).host; (by[h] = by[h] || []).push(r.ms); });
  for (const [h, v] of Object.entries(by)) { v.sort((a, b) => a - b); console.log(`tap to sound${SLOW ? ' on Fast 3G' : ''}  ${h}: median ${v[v.length >> 1]} ms, slowest ${v[v.length - 1]} ms (${v.length})`); }
  await b.close();
})();

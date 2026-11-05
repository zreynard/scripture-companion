// Diagnosis: do big songbooks survive each relay? Publishes retained pieces of several sizes on each broker
// separately, then a fresh listener counts what it receives. node tools/qa/bigdeck.js (needs internet)
delete globalThis.BroadcastChannel; require('../../site_extra/live.js'); const L = globalThis.Live; const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  for (const br of L.BROKERS) {
    for (const size of [20000, 48000, 64000, 120000, 250000]) {
      const topic = 'scwp1/diag' + Math.random().toString(36).slice(2) + '/d/0', body = new Uint8Array(size).fill(65);
      let up = false; const pub = new L._Relay(br, () => {}, () => { up = pub.up; }); await wait(3000);
      const ok = pub.pub(topic, body, true); await wait(2500);
      let got = -1; const sub = new L._Relay(br, (t, b) => { if (t === topic) got = b.length; }, () => {}); sub.sub(topic); await wait(4000);
      console.log(br.n, 'size', size, '| publisher up', up, 'sent', ok, '| late listener got', got, got === size ? 'OK' : 'MISSING'); pub.pub(topic, new Uint8Array(0), true); await wait(300); pub.close(); sub.close();
    }
    // burst: 10 pieces of 48 KB back to back, retained
    const base = 'scwp1/diag' + Math.random().toString(36).slice(2); let up2 = false; const pub = new L._Relay(br, () => {}, () => { up2 = pub.up; }); await wait(3000);
    for (let i = 0; i < 10; i++) pub.pub(base + '/d/' + i, new Uint8Array(48000).fill(66), true); await wait(3000);
    const seen = new Set(); const sub = new L._Relay(br, (t, b) => { if (b.length) seen.add(t); }, () => {}); sub.sub(base + '/#'); await wait(5000);
    console.log(br.n, 'burst of 10 x 48 KB: late listener got', seen.size, 'of 10'); for (let i = 0; i < 10; i++) pub.pub(base + '/d/' + i, new Uint8Array(0), true); await wait(300); pub.close(); sub.close();
  }
  process.exit(0);
})();

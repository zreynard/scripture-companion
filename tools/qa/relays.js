// Which free public MQTT-over-WebSocket relays work, and how big a message survives? node tools/qa/relays.js
delete globalThis.BroadcastChannel; require('../../site_extra/live.js'); const L = globalThis.Live; const wait = ms => new Promise(r => setTimeout(r, ms));
const CANDS = [
  { n: 'hivemq', u: 'wss://broker.hivemq.com:8884/mqtt' }, { n: 'emqx', u: 'wss://broker.emqx.io:8084/mqtt' },
  { n: 'mosquitto', u: 'wss://test.mosquitto.org:8081/mqtt' }, { n: 'eclipse', u: 'wss://mqtt.eclipseprojects.io:443/mqtt' },
  { n: 'emqx-cn', u: 'wss://broker-cn.emqx.io:8084/mqtt' }, { n: 'mqttdashboard', u: 'wss://broker.mqttdashboard.com:8884/mqtt' }];
(async () => {
  for (const br of CANDS) {
    const t0 = Date.now(); let upAt = 0; const pub = new L._Relay(br, () => {}, () => { if (pub.up && !upAt) upAt = Date.now() - t0; });
    for (let i = 0; i < 80 && !upAt; i++) await wait(100);
    if (!upAt) { console.log(br.n, '| could not connect in 8 s'); pub.close(); continue; }
    const res = [];
    for (const size of [200, 14000, 30000]) {
      const topic = 'scwp1/probe' + Math.random().toString(36).slice(2) + '/s'; const ok = pub.pub(topic, new Uint8Array(size).fill(67), true); await wait(1500);
      let got = -1, t1 = Date.now(), ms = -1; const sub = new L._Relay(br, (t, b) => { if (t === topic && got < 0) { got = b.length; ms = Date.now() - t1; } }, () => {}); sub.sub(topic);
      for (let i = 0; i < 60 && got < 0; i++) await wait(100); res.push(size + (got === size ? ' ok ' + ms + 'ms' : ' MISSING')); pub.pub(topic, new Uint8Array(0), true); sub.close();
    }
    const burst = 'scwp1/probe' + Math.random().toString(36).slice(2); let sent = 0; for (let i = 0; i < 30; i++) if (pub.pub(burst + '/d/' + i, new Uint8Array(14000).fill(68), true)) sent++; await wait(3000);
    const seen = new Set(); const sub = new L._Relay(br, (t, b) => { if (b.length) seen.add(t); }, () => {}); sub.sub(burst + '/#'); await wait(6000); for (let i = 0; i < 30; i++) pub.pub(burst + '/d/' + i, new Uint8Array(0), true);
    console.log(br.n, '| connect', upAt + 'ms |', res.join(' | '), '| burst 30x14KB:', seen.size + '/30'); await wait(300); pub.close(); sub.close();
  }
  process.exit(0);
})();

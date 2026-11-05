// Real-relay check for site_extra/live.js (Node 22: WebSocket and WebCrypto built in).
delete globalThis.BroadcastChannel; require('../site_extra/live.js'); const L = globalThis.Live, wait = ms => new Promise(r => setTimeout(r, ms));
const out = {};
(async () => {
  // each relay on its own: connect time
  for (const b of L.BROKERS) {
    const t0 = Date.now(); let up = false;
    const r = new L._Relay(b, () => {}, () => { if (r.up && !up) { up = true; out['connect_' + b.n + '_ms'] = Date.now() - t0; } });
    await wait(6000); r.close(); if (!up) out['connect_' + b.n + '_ms'] = 'FAILED';
  }
  const s = L.newSession(); const got = [];
  const lead = new L.Session({ ...s, role: 'lead', onState: () => {} });
  const screen = new L.Session({ ...s, role: 'screen', onState: (st, via) => got.push({ v: st.v, slide: st.slide, via, t: Date.now() }) });
  await wait(4000);
  const lat = [];
  for (let i = 1; i <= 10; i++) { const t0 = Date.now(); lead.set({ slide: i }); for (let k = 0; k < 60 && !got.find(g => g.slide === i); k++) await wait(25); const g = got.find(g => g.slide === i); lat.push(g ? g.t - t0 : null); await wait(150); }
  out.latency_ms = lat; out.screen_final_slide = screen.state && screen.state.slide;
  // one relay goes down on the screen: the other carries on
  screen.relays[0].close(); const lat2 = [];
  for (let i = 101; i <= 105; i++) { const t0 = Date.now(); lead.set({ slide: i }); for (let k = 0; k < 120 && !got.find(g => g.slide === i); k++) await wait(25); const g = got.find(g => g.slide === i); lat2.push(g ? g.t - t0 : null); await wait(150); }
  out.latency_one_relay_ms = lat2;
  await lead.publishDeck({ songs: [{ t: 'Amazing Grace', slides: [{ s: 'Verse 1', l: ['Amazing grace how sweet the sound'] }] }] });
  await wait(1500);
  // a phone that joins late gets the current state and deck from the relay
  let lateState = null, lateDeck = null; const t0 = Date.now();
  const late = new L.Session({ ...s, role: 'remote', onState: st => { if (!lateState) lateState = { slide: st.slide, ms: Date.now() - t0 }; }, onDeck: d => { lateDeck = d.songs[0].t; } });
  await wait(5000); out.late_join = { lateState, lateDeck };
  // two people tap at once: everyone ends on the same state
  late.set({ slide: 20 }); lead.set({ slide: 30 }); await wait(2500);
  out.simultaneous = { lead: lead.state.slide, screen: screen.state.slide, late: late.state.slide };
  out.status = { lead_relays: lead.up(), screens_seen_by_lead: lead.screens() };
  // pairing by code
  const c = L.code(6); let paired = null; const tp = Date.now();
  const lp = L.listenPair(c, m => { paired = { sid_ok: m.sid === s.sid, ms: Date.now() - tp }; });
  await wait(3000); const sent = await L.sendPair(c, { sid: s.sid, key: s.key }); await wait(3000);
  out.pair = { code: c, sent_to_relays: sent, paired }; lp.stop();
  await lead.end(); await wait(1500); out.screen_sees_end = !!(screen.state && screen.state.ended);
  [screen, late].forEach(x => x.close());
  console.log(JSON.stringify(out, null, 1)); setTimeout(() => process.exit(0), 500);
})();

/* Scripture Companion · Worship live sync.
   One small engine shared by the phone, a friend's phone, the laptop and the TV:
   - MQTT 3.1.1 over secure WebSockets to two free public relays at once (no accounts, no keys); any one is enough
   - everything sent is AES-GCM encrypted with a key that lives only in the link (#k=...), never on the relay
   - the relay keeps the last state and deck ("retained"), so a screen or phone that reconnects catches up at once
   - state, not commands: each change carries a version (v) and the sender's id; the highest (v, id) wins everywhere
   - windows on the same computer also talk over BroadcastChannel, so a laptop keeps working with no internet */
(function (G) {
  'use strict';
  var BROKERS = [
    { n: 'hivemq', u: 'wss://broker.hivemq.com:8884/mqtt' },
    { n: 'emqx', u: 'wss://broker.emqx.io:8084/mqtt' },
    { n: 'emqx-cn', u: 'wss://broker-cn.emqx.io:8084/mqtt' }   // a separate deployment: measured 5 Nov 2026 as reliable as the others, and it takes bursts
  ];
  /* UTF-8 by hand where an old TV browser has no TextEncoder */
  var TE = G.TextEncoder ? new TextEncoder() : { encode: function (s) { var u = unescape(encodeURIComponent(s)), o = new Uint8Array(u.length); for (var i = 0; i < u.length; i++) o[i] = u.charCodeAt(i); return o; } };
  var TD = G.TextDecoder ? new TextDecoder() : { decode: function (b) { var s = ''; b = new Uint8Array(b.buffer || b, b.byteOffset || 0, b.byteLength); for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); try { return decodeURIComponent(escape(s)); } catch (e) { return s; } } };
  function cut(b, a, z) { return new Uint8Array(b.subarray(a, z)); }   // a copy of part of the bytes (typed-array slice is newer than some TVs)
  function b64u(b) { var s = ''; b = new Uint8Array(b); for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
  function unb64u(s) { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; var r = atob(s), o = new Uint8Array(r.length); for (var i = 0; i < r.length; i++) o[i] = r.charCodeAt(i); return o; }
  function rnd(n) { var a = new Uint8Array(n); crypto.getRandomValues(a); return a; }
  var ALPHA = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';   // no 0/O, 1/I/L
  function code(n) { var a = rnd(n), s = ''; for (var i = 0; i < n; i++) s += ALPHA[a[i] % ALPHA.length]; return s; }
  function sha(s) { return crypto.subtle.digest('SHA-256', TE.encode(s)).then(function (h) { return new Uint8Array(h); }); }
  function hex(b) { var s = ''; for (var i = 0; i < b.length; i++) s += (b[i] < 16 ? '0' : '') + b[i].toString(16); return s; }

  /* ---- MQTT over WebSocket (only what is needed: connect, subscribe, publish QoS 0 with retain, ping) ---- */
  function remLen(n) { var o = []; do { var d = n % 128; n = Math.floor(n / 128); if (n > 0) d |= 128; o.push(d); } while (n > 0); return o; }
  function strB(s) { var b = TE.encode(s); return [b.length >> 8, b.length & 255].concat(Array.prototype.slice.call(b)); }
  function packet(type, flags, body) { var h = [(type << 4) | flags].concat(remLen(body.length)); var o = new Uint8Array(h.length + body.length); o.set(h, 0); o.set(body, h.length); return o; }
  function Relay(def, onMsg, onUp) {
    this.def = def; this.onMsg = onMsg; this.onUp = onUp; this.subs = []; this.up = false; this.ws = null; this.buf = new Uint8Array(0);
    this.wait = 1000; this.pid = 1; this.closed = false; this.last = 0; this.open();
  }
  Relay.prototype.open = function () {
    var self = this; if (this.closed) return;
    var ws; try { ws = new WebSocket(this.def.u, ['mqtt']); } catch (e) { return this.retry(); }
    ws.binaryType = 'arraybuffer'; this.ws = ws; this.buf = new Uint8Array(0);
    ws.onopen = function () {
      var id = 'sc' + hex(rnd(6));
      var body = strB('MQTT').concat([4, 2, 0, 40]).concat(strB(id));
      ws.send(packet(1, 0, body));
    };
    ws.onmessage = function (e) { self.last = Date.now(); self.feed(new Uint8Array(e.data)); };
    ws.onclose = function () { var was = self.up; self.up = false; clearInterval(self.ping); if (was) self.onUp(); self.retry(); };
    ws.onerror = function () { try { ws.close(); } catch (e) {} };
  };
  Relay.prototype.retry = function () {
    var self = this; if (this.closed) return; clearTimeout(this.rt);
    this.rt = setTimeout(function () { self.open(); }, this.wait); this.wait = Math.min(this.wait * 2, 8000);
  };
  Relay.prototype.kick = function () { if (this.closed || this.up) return; clearTimeout(this.rt); this.wait = 1000; try { if (this.ws) this.ws.close(); } catch (e) {} this.open(); };
  Relay.prototype.feed = function (chunk) {
    var b = new Uint8Array(this.buf.length + chunk.length); b.set(this.buf, 0); b.set(chunk, this.buf.length);
    var p = 0;
    for (;;) {
      if (b.length - p < 2) break;
      var mul = 1, len = 0, i = p + 1, d, ok = false;
      for (var k = 0; k < 4 && i < b.length; k++) { d = b[i++]; len += (d & 127) * mul; mul *= 128; if (!(d & 128)) { ok = true; break; } }
      if (!ok || b.length - i < len) break;
      this.handle(b[p] >> 4, b[p] & 15, b.subarray(i, i + len)); p = i + len;
    }
    this.buf = cut(b, p);
  };
  Relay.prototype.handle = function (type, flags, body) {
    var self = this;
    if (type === 2) {   // CONNACK
      if (body[1] !== 0) { try { this.ws.close(); } catch (e) {} return; }
      this.up = true; this.wait = 1000;
      this.subs.forEach(function (t) { self.sendSub(t); });
      clearInterval(this.ping);
      this.ping = setInterval(function () {
        if (Date.now() - self.last > 45000) { try { self.ws.close(); } catch (e) {} return; }
        try { self.ws.send(packet(12, 0, new Uint8Array(0))); } catch (e) {}
      }, 15000);
      this.onUp();
    } else if (type === 3) {   // PUBLISH (QoS 0)
      var tl = (body[0] << 8) | body[1], topic = TD.decode(body.subarray(2, 2 + tl)), q = (flags >> 1) & 3, at = 2 + tl + (q ? 2 : 0);
      this.onMsg(topic, cut(body, at), !!(flags & 1), this.def.n);
    }
  };
  Relay.prototype.sendSub = function (t) {
    var id = this.pid++ & 0xffff || 1, body = [id >> 8, id & 255].concat(strB(t)).concat([0]);
    try { this.ws.send(packet(8, 2, new Uint8Array(body))); } catch (e) {}
  };
  Relay.prototype.sub = function (t) { if (this.subs.indexOf(t) < 0) this.subs.push(t); if (this.up) this.sendSub(t); };
  Relay.prototype.pub = function (t, payload, retain) {
    if (!this.up) return false;
    var tb = strB(t), body = new Uint8Array(tb.length + payload.length); body.set(tb, 0); body.set(payload, tb.length);
    try { this.ws.send(packet(3, retain ? 1 : 0, body)); return true; } catch (e) { return false; }
  };
  Relay.prototype.close = function () { this.closed = true; clearInterval(this.ping); clearTimeout(this.rt); try { if (this.ws) { this.ws.send(packet(14, 0, new Uint8Array(0))); this.ws.close(); } } catch (e) {} };

  /* ---- encryption ---- */
  function importKey(raw) { return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']); }
  function seal(key, obj) {
    var iv = rnd(12);
    return crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, key, TE.encode(JSON.stringify(obj))).then(function (c) {
      var o = new Uint8Array(12 + c.byteLength); o.set(iv, 0); o.set(new Uint8Array(c), 12); return o;
    });
  }
  function open(key, bytes) {
    if (!bytes || bytes.length < 13) return Promise.resolve(null);
    return crypto.subtle.decrypt({ name: 'AES-GCM', iv: bytes.subarray(0, 12) }, key, bytes.subarray(12))
      .then(function (p) { return JSON.parse(TD.decode(p)); }).catch(function () { return null; });
  }
  function newer(a, b) { if (!b) return true; if (a.v !== b.v) return a.v > b.v; return String(a.by) > String(b.by); }

  /* ---- a live session ---- */
  function Session(o) {
    var self = this;
    this.sid = o.sid; this.role = o.role || 'remote'; this.name = o.name || ''; this.id = o.id || (this.role[0] + hex(rnd(4)));
    this.state = null; this.deck = null; this.peers = {}; this.cb = o; this.pending = false; this.relays = []; this.ended = false;
    this.base = 'scwp1/' + this.sid;
    var raw; try { raw = unb64u(String(o.key || '')); } catch (e) { raw = null; }
    if (!raw || raw.length !== 16 || !/^[\w-]{8,40}$/.test(String(o.sid || ''))) throw new Error('bad link');
    this.ready = importKey(raw).then(function (k) { self.key = k; });
    if (G.BroadcastChannel) {
      try {
        this.bc = new BroadcastChannel('scwp-' + this.sid);
        this.bc.onmessage = function (e) {
          var m = e.data || {};
          if (m.k === 's') self.gotState(m.d, 'local'); else if (m.k === 'd') self.gotDeck(m.d, 'local'); else if (m.k === 'p') self.gotPeer(m.d); else if (m.k === 'c' && self.cb.onCmd) self.cb.onCmd(m.d);
          else if (m.k === 'q') {   // a window that just opened on this computer asks for the songs and the current slide
            try { if (self.deck) self.bc.postMessage({ k: 'd', d: self.deck }); if (self.state) self.bc.postMessage({ k: 's', d: self.state }); } catch (x) {}
          }
        };
        try { this.bc.postMessage({ k: 'q' }); } catch (e) {}
      } catch (e) { this.bc = null; }
    }
    this.ready.then(function () {
      self.relays = BROKERS.map(function (d) {
        var r = new Relay(d, function (t, b, ret, n) { self.onRelay(t, b, ret, n); }, function () { self.status(); if (r.up) self.flush(); });
        r.sub(self.base + '/#'); return r;
      });
      self.status();
    });
    this.beat = setInterval(function () { self.hello(); self.status(); }, 6000);
    setTimeout(function () { self.hello(); }, 400);
    this.onVis = function () { if (document.visibilityState === 'visible') { self.relays.forEach(function (r) { r.kick(); }); self.hello(); } };
    if (G.document) { document.addEventListener('visibilitychange', this.onVis); G.addEventListener('online', this.onVis); }
  }
  Session.prototype.onRelay = function (t, bytes, retained, n) {
    var self = this, kind = t.slice(this.base.length + 1);
    if (/^d\/\d+$/.test(kind)) { if (bytes.length) open(this.key, bytes).then(function (m) { if (m) self.gotPart(m); }); return; }
    if (kind === 'c') { if (bytes.length) open(this.key, bytes).then(function (m) { if (m && self.cb.onCmd) self.cb.onCmd(m); }); return; }
    if (kind !== 's' && kind !== 'd' && kind !== 'p') return;
    if (!bytes.length) { if (kind === 'd' && this.cb.onDeckCleared) this.cb.onDeckCleared(); return; }
    open(this.key, bytes).then(function (m) {
      if (!m) return;
      if (kind === 's') self.gotState(m, n); else if (kind === 'd') self.gotDeck(m, n); else self.gotPeer(m);
    });
  };
  Session.prototype.gotState = function (s, via) {
    if (!s || !newer(s, this.state)) return;
    this.state = s; this.lastFrom = via;
    if (s.ended) this.ended = true;
    if (this.cb.onState) this.cb.onState(s, via);
  };
  /* a big songbook travels in pieces: a short note on /d says how many, the pieces sit on /d/0, /d/1, … */
  Session.prototype.gotPart = function (m) {
    if (!m || !m.dv || m.i == null || !m.n) return;
    var p = this.parts = this.parts || {}, g = p[m.dv] = p[m.dv] || { n: m.n, c: {} }; g.c[m.i] = m.c; this.tryParts(m.dv);
  };
  Session.prototype.tryParts = function (dv) {
    var g = this.parts && this.parts[dv]; if (!g) return; var all = '';
    for (var i = 0; i < g.n; i++) { if (g.c[i] == null) return; all += g.c[i]; }
    delete this.parts[dv]; var d = null; try { d = JSON.parse(all); } catch (e) { return; } this.gotDeck(d);
  };
  Session.prototype.gotDeck = function (d) {
    if (d && d.parts && !d.songs) { var p = this.parts = this.parts || {}; if (!p[d.dv]) p[d.dv] = { n: d.parts, c: {} }; p[d.dv].n = d.parts; this.tryParts(d.dv); return; }
    if (!d || (this.deck && (d.dv || 0) <= (this.deck.dv || 0))) return;
    this.deck = d; if (this.cb.onDeck) this.cb.onDeck(d);
  };
  Session.prototype.gotPeer = function (p) {
    if (!p || p.id === this.id) return;
    p.seen = Date.now(); this.peers[p.id] = p; if (p.bye) delete this.peers[p.id]; this.status();
    /* someone is still missing the songs (a piece got lost on the relays): the leader sends them again */
    if (p.want && this.role === 'lead' && this.deck && Date.now() - (this.resent || 0) > 4000) { this.resent = Date.now(); this.send('d', this.deck, true); }
  };
  Session.prototype.up = function () { return this.relays.filter(function (r) { return r.up; }).length; };
  Session.prototype.screens = function () { var n = Date.now(), c = 0; for (var k in this.peers) if (this.peers[k].role === 'screen' && n - this.peers[k].seen < 20000) c++; return c; };
  Session.prototype.status = function () { if (this.cb.onStatus) this.cb.onStatus({ relays: this.up(), of: BROKERS.length, screens: this.screens(), peers: this.peers, local: !!this.bc }); };
  var PART = 12000;   // characters per piece of a big songbook: measured 5 Nov 2026, HiveMQ drops messages from about 48 KB and EMQX from about 100 KB, both pass bursts of 14 KB
  Session.prototype.send = function (kind, obj, retain) {
    var self = this;
    if (this.bc) try { this.bc.postMessage({ k: kind, d: obj }); } catch (e) {}
    var msgs = [[kind, obj]];
    if (kind === 'd' && obj) {
      var js = JSON.stringify(obj);
      if (js.length > PART) {
        var n = Math.ceil(js.length / PART); msgs = [];
        for (var i = 0; i < n; i++) msgs.push(['d/' + i, { dv: obj.dv, i: i, n: n, c: js.slice(i * PART, (i + 1) * PART) }]);
        msgs.push(['d', { dv: obj.dv, parts: n }]);   // the note goes last, after every piece
        this.lastParts = n;
      }
    }
    return this.ready.then(function () { return Promise.all(msgs.map(function (m) { return seal(self.key, m[1]); })); }).then(function (all) {
      if (all.length < 3) { var sent = 0; self.relays.forEach(function (r) { var ok = true; all.forEach(function (bytes, j) { if (!r.pub(self.base + '/' + msgs[j][0], bytes, retain)) ok = false; }); if (ok) sent++; }); return sent; }
      /* many pieces: 40 ms apart, which relays that drop fast bursts (HiveMQ) keep up with */
      return new Promise(function (done) {
        var ok = self.relays.map(function () { return true; }), j = 0;
        (function next() {
          if (j >= all.length) return done(ok.filter(function (x, i) { return x && self.relays[i].up; }).length);
          self.relays.forEach(function (r, i) { if (!r.pub(self.base + '/' + msgs[j][0], all[j], retain)) ok[i] = false; }); j++; setTimeout(next, 40);
        })();
      });
    });
  };
  Session.prototype.hello = function () { if (this.ended) return; var p = { id: this.id, role: this.role, name: this.name || '', at: Date.now(), want: this.deck ? 0 : 1 }, x = this.cb.info && this.cb.info(); if (x) for (var k in x) p[k] = x[k]; this.send('p', p, false); };
  /* a one-off instruction to the screens (refresh), never kept on the relay */
  Session.prototype.cmd = function (m) { m.at = Date.now(); m.by = this.id; return this.send('c', m, false); };
  Session.prototype.setName = function (n) { this.name = String(n || '').slice(0, 30); this.hello(); };
  /* change what is shown: merge into the current state, bump the version, show it here at once, send it everywhere */
  Session.prototype.set = function (patch) {
    if (this.ended) return null;
    var cur = this.state || { v: 0, song: 0, slide: 0, blank: false }, s = {};
    for (var k in cur) s[k] = cur[k]; for (k in patch) s[k] = patch[k];
    s.v = (cur.v || 0) + 1; s.by = this.id; s.who = this.name || (this.role === 'lead' ? 'Leader' : ''); s.at = Date.now();
    this.state = s; if (this.cb.onState) this.cb.onState(s, 'me');
    var self = this; this.pending = true;
    this.send('s', s, true).then(function (n) { if (n) self.pending = false; });
    return s;
  };
  /* back online: send this device's last change only if nobody has changed the screen since */
  Session.prototype.flush = function () {
    var self = this;
    setTimeout(function () { if (self.pending && self.state && self.state.by === self.id) self.send('s', self.state, true).then(function (n) { if (n) self.pending = false; }); }, 1500);
    this.hello();
  };
  Session.prototype.publishDeck = function (deck) { deck.dv = Math.max(Date.now(), ((this.deck && this.deck.dv) || 0) + 1); this.deck = deck; if (this.cb.onDeck) this.cb.onDeck(deck); return this.send('d', deck, true); };
  Session.prototype.end = function () {
    var self = this;
    var s = this.set({ ended: true, blank: true }); this.ended = true;
    return this.ready.then(function () {
      self.relays.forEach(function (r) { r.pub(self.base + '/d', new Uint8Array(0), true); for (var i = 0; i < (self.lastParts || 0); i++) r.pub(self.base + '/d/' + i, new Uint8Array(0), true); });
      self.send('p', { id: self.id, role: self.role, bye: 1 }, false);
      return new Promise(function (r) { setTimeout(r, 600); });
    }).then(function () { self.close(); return s; });
  };
  Session.prototype.close = function () {
    clearInterval(this.beat); this.relays.forEach(function (r) { r.close(); }); if (this.bc) try { this.bc.close(); } catch (e) {}
    if (G.document) { document.removeEventListener('visibilitychange', this.onVis); G.removeEventListener('online', this.onVis); }
  };

  /* ---- pairing a screen by a short code: the screen shows the code, the phone types it ---- */
  function pairTopic(c) { return sha('scwp-pair-topic:' + c).then(function (h) { return 'scwp1/pair/' + hex(h).slice(0, 24); }); }
  function pairKey(c) { return sha('scwp-pair-key:' + c).then(function (h) { return importKey(cut(h, 0, 16)); }); }
  /* screen side: listen for a session on this code; calls got({sid,key}) once */
  function listenPair(c, got, onStatus) {
    var done = false, relays = [];
    Promise.all([pairTopic(c), pairKey(c)]).then(function (tk) {
      relays = BROKERS.map(function (d) {
        var r = new Relay(d, function (t, b) {
          if (done || t !== tk[0] || !b.length) return;
          open(tk[1], b).then(function (m) {
            if (!m || !m.sid || done) return; done = true;
            relays.forEach(function (x) { x.pub(tk[0], new Uint8Array(0), true); });
            setTimeout(function () { relays.forEach(function (x) { x.close(); }); }, 800);
            got(m);
          });
        }, function () { if (onStatus) onStatus(relays.filter(function (x) { return x.up; }).length); });
        r.sub(tk[0]); return r;
      });
    });
    return { stop: function () { done = true; relays.forEach(function (x) { x.close(); }); } };
  }
  /* phone side: hand the session to the screen showing this code */
  function sendPair(c, info) {
    c = String(c || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
    return Promise.all([pairTopic(c), pairKey(c)]).then(function (tk) {
      return seal(tk[1], info).then(function (bytes) {
        return new Promise(function (res) {
          var sent = 0, left = BROKERS.length, relays = [];
          relays = BROKERS.map(function (d) {
            var r = new Relay(d, function () {}, function () {
              if (!r.up || r.didSend) return; r.didSend = true;
              if (r.pub(tk[0], bytes, true)) sent++;
              setTimeout(function () { r.close(); }, 400);
              if (--left === 0) res(sent);
            });
            return r;
          });
          setTimeout(function () { relays.forEach(function (r) { r.close(); }); res(sent); }, 8000);
        });
      });
    });
  }
  /* moving through the songs: the set the leader chose comes first; a song picked from the songbook returns to the set after it */
  function setOf(deck) { return deck.set && deck.set.length ? deck.set : deck.songs.map(function (x, i) { return i; }); }
  function step(deck, st, d) {
    if (!deck || !deck.songs.length) return null;
    var s = st.song || 0, sg = deck.songs[s], i = (st.slide || 0) + d, set = setOf(deck), pos = set.indexOf(s);
    if (sg && i >= 0 && i < sg.slides.length) return { song: s, slide: i, blank: false };
    var to = d > 0 ? (pos >= 0 ? set[pos + 1] : (st.ret != null ? set[st.ret + 1] : null)) : (pos > 0 ? set[pos - 1] : (pos < 0 && st.ret != null ? set[st.ret] : null));
    if (to == null || !deck.songs[to]) return null;
    return { song: to, slide: d > 0 ? 0 : Math.max(0, deck.songs[to].slides.length - 1), blank: false, ret: null };
  }
  function songStep(deck, st, d) {
    var set = setOf(deck), pos = set.indexOf(st.song || 0), to = pos >= 0 ? set[pos + d] : (st.ret != null ? set[d > 0 ? st.ret + 1 : st.ret] : null);
    return to == null || !deck.songs[to] ? null : { song: to, slide: 0, blank: false, ret: null };
  }
  function newSession() { return { sid: b64u(rnd(12)), key: b64u(rnd(16)) }; }
  G.Live = { setOf: setOf, step: step, songStep: songStep, Session: Session, listenPair: listenPair, sendPair: sendPair, newSession: newSession, code: code, BROKERS: BROKERS, _Relay: Relay };
})(typeof window !== 'undefined' ? window : globalThis);

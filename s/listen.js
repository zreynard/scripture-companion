/* A sermon someone shared with you: one page, one player. Plays from where the sermon starts (or where they shared
   it from), streams from the church's own host, remembers your place on this phone. Nothing else is loaded. */
(function () {
  'use strict';
  var d = JSON.parse(document.getElementById('sd').textContent), A = window.SC_ART || {}, $ = function (s) { return document.querySelector(s); };
  var q = /[?&]t=(\d+)/.exec(location.search), from = q ? +q[1] : 0, key = 'sc-listen:' + d.id, saved = 0;
  try { saved = +localStorage.getItem(key) || 0; } catch (e) { }
  var start = from || saved || d.s || 0;
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function clock(s) { s = Math.max(0, Math.floor(s || 0)); var h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ':' + (m < 10 ? '0' : '') + m : m) + ':' + (x < 10 ? '0' : '') + x; }
  var c = (A.colors || {})[d.who] || ['#1b2440', '#a8812a'], icon = (A.icons || {})[(A.medal || {})[d.who]] || '';
  var PLAY = '<svg width="30" height="30" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.2v13.6c0 .6.7 1 1.2.6l10.4-6.8a.75.75 0 0 0 0-1.2L9.2 4.6C8.7 4.2 8 4.6 8 5.2z" fill="#fff"/></svg>',
    PAUSE = '<svg width="30" height="30" viewBox="0 0 24 24" aria-hidden="true"><rect x="6.5" y="5" width="4" height="14" rx="1.2" fill="#fff"/><rect x="13.5" y="5" width="4" height="14" rx="1.2" fill="#fff"/></svg>';
  document.body.innerHTML = '<main class="ls">' +
    '<div class="ls-k">Shared with you</div>' +
    '<div class="ls-art" style="background:linear-gradient(150deg,' + c[1] + ',' + c[0] + ')"><svg class="a-m" viewBox="0 0 48 48" aria-hidden="true"><path d="' + icon + '" fill="none" stroke="#fff" stroke-width="2"/></svg>' +
    '<div class="a-w">' + esc(d.teacher) + '</div><div class="a-p">' + esc(d.where || d.teacher) + '</div>' + (d.show ? '<div class="a-s">' + esc(d.show) + '</div>' : '') + '</div>' +
    '<h1 class="ls-t">' + esc(d.t) + '</h1><p class="ls-by">' + esc([d.teacher, d.pass].filter(Boolean).join(' · ')) + '</p>' +
    (from ? '<p class="ls-from">Starts at ' + clock(from) + ' · <button id="ls-begin">Play from the beginning</button></p>' : '') +
    '<input type="range" id="ls-seek" min="0" max="1000" value="0" aria-label="Position"><div class="ls-tm"><span id="ls-cur">0:00</span><span id="ls-rem"></span></div>' +
    '<div class="ls-ctl"><button class="ls-sk" id="ls-bk" aria-label="Back 15 seconds">↺ 15</button><button class="ls-pp" id="ls-pp" aria-label="Play">' + PLAY + '</button><button class="ls-sk" id="ls-fw" aria-label="Forward 15 seconds">15 ↻</button></div>' +
    '<button class="ls-sp" id="ls-sp">1× speed</button>' +
    (d.url ? '<a class="ls-src" href="' + esc(d.url) + '" rel="noopener">Listen on the original site ›</a>' : '') +
    '<p class="ls-err" id="ls-err" hidden>This recording did not load. Check your connection and tap play again.</p></main>';
  var a = new Audio(); a.preload = 'metadata'; a.src = d.audio + '#t=' + start; var dur = +d.dur || 0, seeking = false, began = false, sv = 0;
  var SP = [1, 1.25, 1.5, 0.75], sp = 0;
  function paint() { var t = a.currentTime || start, L = isFinite(a.duration) && a.duration > 0 ? a.duration : dur;
    $('#ls-cur').textContent = clock(t); $('#ls-rem').textContent = L ? '-' + clock(L - t) : '';
    if (!seeking && L) { $('#ls-seek').value = Math.round(t / L * 1000); $('#ls-seek').style.setProperty('--p', (t / L * 100).toFixed(2) + '%'); }
    var on = !a.paused; $('#ls-pp').innerHTML = on ? PAUSE : PLAY; $('#ls-pp').setAttribute('aria-label', on ? 'Pause' : 'Play'); }
  function go() { $('#ls-err').hidden = true; if (!began) { began = true; if (Math.abs((a.currentTime || 0) - start) > 1) try { a.currentTime = start; } catch (e) { } } var p = a.play(); if (p && p.catch) p.catch(function () { }); }
  a.addEventListener('loadedmetadata', function () { if (Math.abs(a.currentTime - start) > 1) try { a.currentTime = start; } catch (e) { } paint(); });
  a.addEventListener('timeupdate', function () { paint(); var n = Date.now(); if (n - sv > 5000 && a.currentTime > 5) { sv = n; try { localStorage.setItem(key, String(Math.floor(a.currentTime))); } catch (e) { } } });
  ['play', 'pause', 'ended', 'durationchange'].forEach(function (e) { a.addEventListener(e, paint); });
  a.addEventListener('error', function () { if (began) $('#ls-err').hidden = false; paint(); });
  $('#ls-pp').onclick = function () { if (a.paused) go(); else a.pause(); };
  $('#ls-bk').onclick = function () { a.currentTime = Math.max(0, (a.currentTime || start) - 15); paint(); };
  $('#ls-fw').onclick = function () { a.currentTime = (a.currentTime || start) + 15; paint(); };
  $('#ls-sp').onclick = function () { sp = (sp + 1) % SP.length; a.playbackRate = a.defaultPlaybackRate = SP[sp]; $('#ls-sp').textContent = SP[sp] + '× speed'; };
  var sk = $('#ls-seek'); sk.oninput = function () { seeking = true; var L = isFinite(a.duration) && a.duration > 0 ? a.duration : dur; $('#ls-cur').textContent = clock(sk.value / 1000 * L); sk.style.setProperty('--p', sk.value / 10 + '%'); };
  sk.onchange = function () { var L = isFinite(a.duration) && a.duration > 0 ? a.duration : dur; seeking = false; began = true; try { a.currentTime = sk.value / 1000 * L; } catch (e) { } paint(); };
  var b0 = $('#ls-begin'); if (b0) b0.onclick = function () { start = d.s || 0; began = false; b0.parentNode.hidden = true; go(); };
  if ('mediaSession' in navigator) { try { navigator.mediaSession.metadata = new MediaMetadata({ title: d.t, artist: d.teacher, album: d.pass || '' }); } catch (e) { }
    [['play', go], ['pause', function () { a.pause(); }], ['seekbackward', function () { $('#ls-bk').onclick(); }], ['seekforward', function () { $('#ls-fw').onclick(); }]].forEach(function (h) { try { navigator.mediaSession.setActionHandler(h[0], h[1]); } catch (e) { } }); }
  window.LS = { a: a, d: d, start: function () { return start; } };   /* for the app's own tests */
  paint();
})();

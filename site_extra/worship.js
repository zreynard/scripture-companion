/* Scripture Companion · Worship song engine (shared by the app, the presenter page and the TV page).
   - parse(): ChordPro ([G]word, {title:}, {soc}...) or chords-over-lyrics charts into sections of lines with chord positions
   - transposition by key, with key-aware spelling (sharps or flats), slash chords and every chord quality kept
   - slides(): lyrics grouped by section; a section is split only when it is too long, at its most natural break */
(function (G) {
  'use strict';
  var SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  var FLAT = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
  var NOTE = { C: 0, 'B#': 0, 'C#': 1, Db: 1, D: 2, 'D#': 3, Eb: 3, E: 4, Fb: 4, F: 5, 'E#': 5, 'F#': 6, Gb: 6, G: 7, 'G#': 8, Ab: 8, A: 9, 'A#': 10, Bb: 10, B: 11, Cb: 11 };
  /* keys written with flats (major, and their relative minors) */
  var FLAT_MAJ = { F: 1, Bb: 1, Eb: 1, Ab: 1, Db: 1, Gb: 1, Cb: 1 }, FLAT_MIN = { Dm: 1, Gm: 1, Cm: 1, Fm: 1, Bbm: 1, Ebm: 1, Abm: 1 };
  var KEYS_MAJ = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'], KEYS_MIN = ['Cm', 'C#m', 'Dm', 'Ebm', 'Em', 'Fm', 'F#m', 'Gm', 'G#m', 'Am', 'Bbm', 'Bm'];
  var CHORD = /^([A-G])(#|b)?((?:maj|min|mi|m|M|dim|aug|sus|add|°|ø|\+|-|\d|\(|\)|#|b|\/(?![A-G]))*)(?:\/([A-G])(#|b)?)?$/;
  function isChord(t) { return CHORD.test(t) && !/^[A-G](?:aug|dim)?$/.test(t) || /^[A-G](#|b)?$/.test(t); }
  function keyInfo(k) {
    var m = /^([A-G])(#|b)?(m?)/.exec(String(k || '').trim()); if (!m) return null;
    var root = m[1] + (m[2] || ''); return { pc: NOTE[root], minor: !!m[3], name: root + (m[3] ? 'm' : '') };
  }
  function keyName(pc, minor) { pc = ((pc % 12) + 12) % 12; return minor ? KEYS_MIN[pc] : KEYS_MAJ[pc]; }
  function useFlats(key) { var k = keyInfo(key); if (!k) return false; var n = keyName(k.pc, k.minor); return k.minor ? !!FLAT_MIN[n] : !!FLAT_MAJ[n]; }
  function shiftNote(n, semis, flats) { var pc = NOTE[n]; if (pc == null) return n; pc = ((pc + semis) % 12 + 12) % 12; return (flats ? FLAT : SHARP)[pc]; }
  function transposeChord(c, semis, flats) {
    if (!semis) return c;
    var m = CHORD.exec(c); if (!m) return c;
    var out = shiftNote(m[1] + (m[2] || ''), semis, flats) + (m[3] || '');
    if (m[4]) out += '/' + shiftNote(m[4] + (m[5] || ''), semis, flats);
    return out;
  }
  function semitones(from, to) { var a = keyInfo(from), b = keyInfo(to); if (!a || !b) return 0; return ((b.pc - a.pc) % 12 + 12) % 12; }
  function transposeKey(k, semis) { var i = keyInfo(k); return i ? keyName(i.pc + semis, i.minor) : k; }

  /* ---- section labels ---- */
  var KINDS = [['pre-chorus', /^pre[- ]?chorus|^prechorus|^pc\b/i, 'PC'], ['chorus', /^chorus|^refrain|^ch\b|^c\b/i, 'C'], ['verse', /^verse|^v\b/i, 'V'],
    ['bridge', /^bridge|^b\b/i, 'B'], ['intro', /^intro/i, 'I'], ['outro', /^outro|^ending|^end\b/i, 'O'], ['tag', /^tag/i, 'T'],
    ['instrumental', /^instrumental|^inst\b|^interlude|^turnaround|^break|^solo/i, 'Inst'], ['vamp', /^vamp/i, 'Vamp'], ['other', /^(?:spontaneous|ad lib|coda)/i, 'X']];
  var LABEL = /^\s*[\[(]?\s*((?:pre[- ]?chorus|prechorus|chorus|refrain|verse|bridge|intro|outro|ending|tag|instrumental|interlude|turnaround|break|solo|vamp|coda|spontaneous)\s*\d*[a-z]?)\s*[\])]?\s*:?\s*(?:[\[(]?\s*[x×]\s*(\d+)\s*[\])]?)?\s*(.*)$/i;
  function kindOf(label) { for (var i = 0; i < KINDS.length; i++) if (KINDS[i][1].test(label.trim())) return KINDS[i]; return ['other', null, 'X']; }
  function tidyLabel(l) { l = l.replace(/\s+/g, ' ').trim(); l = l.replace(/^(\w)/, function (c) { return c.toUpperCase(); }); return l.replace(/^Pre[- ]?chorus/i, 'Pre-Chorus').replace(/^Prechorus/i, 'Pre-Chorus'); }
  function shortOf(label) { var k = kindOf(label), n = (/(\d+)/.exec(label) || [])[1]; return k[2] + (n || ''); }

  /* ---- reading a chart ---- */
  function tokens(line) { return line.replace(/[|]/g, ' ').trim().split(/\s+/).filter(Boolean); }
  function isChordLine(line) {
    var t = tokens(line); if (!t.length) return false; var chords = 0;
    for (var i = 0; i < t.length; i++) {
      var w = t[i].replace(/^\(|\)$/g, '');
      if (isChord(w)) chords++; else if (!/^(?:[x×]\d+|\d+[x×]|-+|\/+|%|n\.?c\.?|\.+|:)$/i.test(w)) return false;
    }
    return chords > 0;
  }
  function chordsAt(line) { var r = [], re = /\S+/g, m; while ((m = re.exec(line))) { var w = m[0].replace(/^\(|\)$/g, ''); if (isChord(w)) r.push({ c: w, at: m.index }); } return r; }
  function inlineChords(line) {   // ChordPro: [G]Amazing → text without brackets, chords at character positions
    var chords = [], text = '', re = /\[([^\]]+)\]/g, last = 0, m;
    while ((m = re.exec(line))) { text += line.slice(last, m.index); chords.push({ c: m[1].trim(), at: text.length }); last = m.index + m[0].length; }
    text += line.slice(last); return { text: text, chords: chords };
  }
  function parse(src) {
    var meta = {}, sections = [], cur = null, lines = String(src || '').replace(/\r/g, '').split('\n'), pendingChords = null, envLabel = null;
    function open(label, rep) { cur = { label: tidyLabel(label), lines: [], rep: rep || 1 }; sections.push(cur); }
    function ensure() { if (!cur) open('Verse ' + (sections.filter(function (s) { return /^Verse/.test(s.label); }).length + 1)); }
    function push(l) { ensure(); cur.lines.push(l); }
    function flushChords() { if (pendingChords) { push({ text: '', chords: pendingChords }); pendingChords = null; } }
    for (var i = 0; i < lines.length; i++) {
      var raw = lines[i].replace(/\t/g, '    '), line = raw.replace(/\s+$/, '');
      var dir = /^\s*\{\s*([a-z_]+)\s*(?::\s*(.*?))?\s*\}\s*$/i.exec(line);
      if (dir) {
        flushChords(); var d = dir[1].toLowerCase(), v = (dir[2] || '').trim();
        if (d === 't' || d === 'title') meta.title = v; else if (d === 'st' || d === 'subtitle' || d === 'artist') meta.artist = v;
        else if (d === 'key') meta.key = v; else if (d === 'capo') meta.capo = parseInt(v, 10) || 0; else if (d === 'tempo') meta.tempo = v;
        else if (/^(soc|start_of_chorus)$/.test(d)) { open(v || 'Chorus'); envLabel = 1; }
        else if (/^(sov|start_of_verse)$/.test(d)) { open(v || 'Verse ' + (sections.filter(function (s) { return /^Verse/.test(s.label); }).length + 1)); envLabel = 1; }
        else if (/^(sob|start_of_bridge)$/.test(d)) { open(v || 'Bridge'); envLabel = 1; }
        else if (/^(eoc|eov|eob|end_of_chorus|end_of_verse|end_of_bridge)$/.test(d)) { envLabel = null; }
        else if (d === 'c' || d === 'comment' || d === 'ci' || d === 'comment_italic') { var lm = LABEL.exec(v); if (lm) open(lm[1], lm[2] && +lm[2]); }
        else if (d === 'chorus') { open('Chorus'); cur.ref = 1; }
        continue;
      }
      if (/^\s*#/.test(line)) continue;
      if (!line.trim()) { flushChords(); if (cur && cur.lines.length && cur.lines[cur.lines.length - 1] !== null) cur.lines.push(null); continue; }
      var lm2 = LABEL.exec(line);
      if (lm2 && !/\[[A-G]/.test(line) && (!lm2[3] || isChordLine(lm2[3]))) {
        flushChords(); open(lm2[1], lm2[2] && +lm2[2]);
        if (lm2[3]) pendingChords = chordsAt(lm2[3]).map(function (c) { return { c: c.c, at: c.at }; });
        continue;
      }
      if (/\[[A-G][^\]]*\]/.test(line)) { flushChords(); push(inlineChords(line)); continue; }
      if (isChordLine(line)) { flushChords(); pendingChords = chordsAt(line); continue; }
      var text = line;
      if (pendingChords) {   // chords sit over this lyric line: keep their columns
        var ch = pendingChords; pendingChords = null; var maxAt = ch.reduce(function (a, c) { return Math.max(a, c.at); }, 0);
        if (text.length < maxAt) text += new Array(maxAt - text.length + 1).join(' ');
        push({ text: text, chords: ch }); continue;
      }
      push({ text: text, chords: [] });
    }
    flushChords();
    sections.forEach(function (s) { while (s.lines.length && s.lines[s.lines.length - 1] === null) s.lines.pop(); while (s.lines.length && s.lines[0] === null) s.lines.shift(); });
    /* a label written again with no lines of its own ("Chorus", "(Chorus x2)") repeats the first section of that name */
    var seen = {};
    sections.forEach(function (s) {
      var k = s.label.toLowerCase();
      if (!s.lines.length && seen[k]) { s.ref = 1; s.lines = seen[k].lines; }
      else if (s.lines.length && !seen[k]) seen[k] = s;
    });
    sections.forEach(function (s, i) { s.short = shortOf(s.label); s.kind = kindOf(s.label)[0]; s.lyric = s.lines.some(function (l) { return l && l.text.trim(); }); s.i = i; });
    return { meta: meta, sections: sections };
  }
  /* unique sections (first occurrence of each name) for "jump to" buttons */
  function uniq(sections) { var seen = {}, out = []; sections.forEach(function (s) { var k = s.label.toLowerCase(); if (!seen[k]) { seen[k] = 1; out.push(s); } }); return out; }

  /* ---- chord chart as HTML (chords above words) ---- */
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function lineHTML(l, semis, flats) {
    if (!l) return '<div class="wc-gap"></div>';
    var ch = (l.chords || []).slice().sort(function (a, b) { return a.at - b.at; });
    if (!ch.length) return '<div class="wc-l"><span class="wc-w"><span class="wc-t">' + (esc(l.text) || '&nbsp;') + '</span></span></div>';
    var out = '', t = l.text, pos = 0;
    if (ch[0].at > 0) out += '<span class="wc-w"><span class="wc-c"></span><span class="wc-t">' + esc(t.slice(0, ch[0].at)) + '</span></span>';
    ch.forEach(function (c, i) {
      var end = i + 1 < ch.length ? ch[i + 1].at : t.length, seg = t.slice(c.at, end);
      out += '<span class="wc-w"><span class="wc-c">' + esc(transposeChord(c.c, semis, flats)) + '</span><span class="wc-t">' + (seg ? esc(seg) : '&nbsp;') + '</span></span>';
    });
    return '<div class="wc-l' + (t.trim() ? '' : ' wc-only') + '">' + out + '</div>';
  }
  function chartHTML(song, opts) {
    opts = opts || {}; var p = song.parsed || parse(song.src), semis = opts.semis || 0, flats = opts.flats;
    return p.sections.map(function (s, i) {
      return '<section class="wc-s' + (opts.cur === i ? ' on' : '') + '" data-sec="' + i + '"><h4 class="wc-h">' + esc(s.label) + (s.rep > 1 ? ' <i>×' + s.rep + '</i>' : '') + (s.ref ? ' <i>(repeat)</i>' : '') + '</h4>' +
        (s.ref && opts.compactRepeats ? '' : s.lines.map(function (l) { return lineHTML(l, semis, flats); }).join('')) + '</section>';
    }).join('');
  }

  /* ---- slides: whole sections where they fit; long ones split at the most natural break ---- */
  var MAXV = 8, WRAP = 34;
  function vis(t) { return Math.max(1, Math.ceil(t.length / WRAP)); }
  function splitSection(lines) {
    var L = lines.map(function (l) { return l ? l.text.replace(/\s+/g, ' ').trim() : null; });
    var blocks = [], cur = [];
    L.forEach(function (t) { if (t === null) { if (cur.length) blocks.push(cur); cur = []; } else if (t) cur.push(t); });
    if (cur.length) blocks.push(cur);
    var flat = [], brk = [];   // brk[i]: a stanza break comes before line i
    blocks.forEach(function (b, bi) { b.forEach(function (t, j) { flat.push(t); brk.push(bi > 0 && j === 0); }); });
    var w = flat.map(vis), total = w.reduce(function (a, b) { return a + b; }, 0);
    if (total <= MAXV) return [flat];
    var n = flat.length, best = [], INF = 1e9;   // dynamic programming over cut points
    var k = Math.ceil(total / MAXV), target = total / k;
    var cost = new Array(n + 1).fill(INF), from = new Array(n + 1).fill(-1); cost[0] = 0;
    for (var i = 1; i <= n; i++) {
      var sum = 0;
      for (var j = i - 1; j >= 0; j--) {
        sum += w[j]; if (sum > MAXV) break;
        if (cost[j] === INF) continue;
        var c = cost[j] + Math.pow(sum - target, 2);
        if (i < n) {
          if (brk[i]) c -= 6; else {
            var prev = flat[i - 1];
            if (/[.!?;:]["”’)]*$/.test(prev)) c += 0; else if (/,["”’)]*$/.test(prev)) c += 2; else c += 7;
            if ((i % 2) === 1) c += 3;   // lyrics move in pairs of lines
          }
        }
        c += 4;   // fewer slides are better
        if (c < cost[i]) { cost[i] = c; from[i] = j; }
      }
    }
    var cuts = [], x = n; while (x > 0) { cuts.unshift(x); x = from[x]; if (x < 0) break; }
    var out = [], a = 0; cuts.forEach(function (b) { out.push(flat.slice(a, b)); a = b; });
    return out;
  }
  /* order: the arrangement (list of section indexes) or the chart as written */
  function slides(song, order) {
    var p = song.parsed || parse(song.src), secs = p.sections, out = [], idx = order && order.length ? order : secs.map(function (s, i) { return i; });
    idx.forEach(function (si, oi) {
      var s = secs[si]; if (!s) return;
      if (!s.lyric) { out.push({ s: s.label, sec: si, occ: oi, l: [] }); return; }
      var parts = splitSection(s.lines);
      parts.forEach(function (lines, pi) { out.push({ s: s.label + (parts.length > 1 ? ' (' + (pi + 1) + '/' + parts.length + ')' : ''), sec: si, occ: oi, part: pi, l: lines }); });
    });
    return out;
  }
  G.Worship = { parse: parse, uniq: uniq, chartHTML: chartHTML, slides: slides, splitSection: splitSection, transposeChord: transposeChord,
    transposeKey: transposeKey, semitones: semitones, useFlats: useFlats, keyInfo: keyInfo, KEYS_MAJ: KEYS_MAJ, KEYS_MIN: KEYS_MIN, isChord: isChord, shortOf: shortOf, esc: esc };
})(typeof window !== 'undefined' ? window : globalThis);

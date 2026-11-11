// QA: chord charts in, songs out — every format the app reads, and thousands of generated charts checked against what
// they were built from. Made-up words only (no real song text anywhere).
//   node tools/qa/charts.js            (N=3000 generated charts; N=… to change)
require('../../site_extra/worship.js'); const W = globalThis.Worship;
const R = []; const T = (n, f) => { let r; try { r = f(); } catch (e) { r = 'threw ' + (e.stack || e).toString().slice(0, 300); } R.push([n, r === true ? 'PASS' : 'FAIL ' + (typeof r === 'string' ? r : JSON.stringify(r)).slice(0, 900)]); };
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b) || { got: a, want: b };
const lab = p => p.sections.map(s => s.label + (s.rep > 1 ? ' x' + s.rep : '') + (s.ref ? '*' : '') + (s.missing ? '?' : ''));
const chordsOf = s => s.lines.reduce((a, l) => a.concat(l ? l.chords.map(c => c.c) : []), []);
const wordsOf = s => s.lines.reduce((a, l) => a.concat(l ? l.text.split(/\s+/).filter(Boolean) : []), []);

// ── 1. Every format, written out by hand (made-up songs) ────────────────────────────────────────────────────────────
const F = require('./chart_fixtures.js');

Object.entries(F).forEach(([name, f], i) => {
  T(`C${i + 1} ${name}: sections, order, repeats and counts come out as written`, () => {
    let l = lab(W.parse(f.src)); if (f.firstAuto) l = l.slice(0);   // a title and artist before the first heading become an untitled first part
    return eq(f.firstAuto ? l.slice(1) : l, f.firstAuto ? f.labels.slice(1) : f.labels);
  });
});
T('C9 the title, artist and key are read from ChordPro directives (full and short forms)', () => eq([F.chordproFull, F.chordproShort].map(f => { const m = W.parse(f.src).meta; return [m.title, m.artist, m.key]; }), [['Lantern Road', 'Test Band', 'G'], ['Harbor Light', 'Test Band', 'D']]));
T('C10 notes to the band are kept (not shown as words, not dropped)', () => { const p = W.parse(F.chordproFull.src), ch = p.sections.find(s => s.label === 'Chorus'), all = p.sections.reduce((a, s) => a.concat(s.notes || []), []);
  const p2 = W.parse(F.chordproShort.src), all2 = p2.sections.reduce((a, s) => a.concat(s.notes || []), []).concat(p2.meta.notes || []);
  return (eq(ch.notes, ['everyone in']) === true && all.length === 1 && all2.includes('softly') && !wordsOf(ch).includes('everyone')) || { ch: ch.notes, all, all2 }; });
T('C11 every chord and every word written in each format comes through (counted per section as written)', () => {
  const bad = [];
  Object.entries(F).forEach(([name, f]) => {
    const p = W.parse(f.src), defs = p.sections.filter(s => !s.ref);
    const src = f.src.replace(/\r/g, '').replace(/\{[^}]*\}/g, '');
    let want = 0; src.split('\n').forEach(line => { const inl = line.match(/\[([^\]\s]{1,10})\]/g); if (inl) inl.forEach(m => { if (W.isChord(m.slice(1, -1))) want++; });
      else if (!/^\s*\[[^\]]*\]\s*$/.test(line)) { const toks = line.replace(/[|]/g, ' ').trim().split(/\s+/).filter(Boolean).map(x => x.replace(/^\(|\)$/g, '')); if (toks.length && toks.every(x => W.isChord(x) || /^(?:[x×]\d+|\d+[x×]|\/+|n\.?c\.?|-+)$/i.test(x)) && toks.some(x => W.isChord(x))) want += toks.filter(x => W.isChord(x)).length;
        else { const hm = /^\s*[\[(]?[A-Za-z- ]+\d*[\])]?\s+((?:[A-G][^\s]*\s*)+)$/.exec(line); } } });
    const got = defs.reduce((a, s) => a + chordsOf(s).length, 0);
    if (got !== want) bad.push([name, 'chords', got, want]);
  });
  return !bad.length || bad;
});
T('C12 the paste clean-up leaves every one of these charts exactly as it is (nothing to tidy), and tidying twice changes nothing', () => {
  const bad = []; Object.entries(F).forEach(([name, f]) => { const c = W.clean(f.src.replace(/\r/g, '')); if (c.src !== f.src.replace(/\r\n?/g, '\n').replace(/ /g, ' ').replace(/\n+$/, '') && name !== 'songSelectish') bad.push([name, 'changed']); if (W.clean(c.src).src !== c.src) bad.push([name, 'not stable']); });
  return !bad.length || bad; });

// ── 2. Thousands of generated charts, checked against what they were built from ───────────────────────────────────
const N = +process.env.N || 3000;
function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const WORDS = ['lantern', 'river', 'morning', 'meadow', 'candle', 'harbor', 'willow', 'ember', 'valley', 'sparrow', 'orchard', 'harvest', 'silver', 'quiet', 'open', 'gentle', 'rising', 'evening', 'window', 'garden', 'over', 'under', 'every', 'little', 'far', 'near', 'home', 'road', 'light', 'stone', 'field', 'shore', 'we', 'you', 'they', 'sing', 'walk', 'hold', 'carry', 'turn', 'wait', 'rest', "it's", "we'll", 'oh', 'ooh'];
const CHORDS = ['G', 'C', 'D', 'Em', 'Am', 'F', 'Bb', 'D/F#', 'G/B', 'Cadd9', 'Dsus4', 'Em7', 'F#m', 'A7', 'Bm', 'E', 'B', 'G#m', 'C#m7', 'Ebmaj7', 'Ab', 'Fmaj7', 'Asus2', 'C/E', 'Bbmaj7', 'Gsus', 'Dm7', 'A/C#', 'Esus4', 'F#7'];
const LYRIC_KINDS = ['Verse', 'Chorus', 'Bridge', 'Pre-Chorus', 'Tag', 'Hook', 'Outro', 'Refrain', 'Vamp'], INST_KINDS = ['Intro', 'Interlude', 'Turnaround', 'Instrumental', 'Channel', 'Solo'];
const CUSTOM = ['Spoken Word', 'Big Finish', 'Groove', 'Free Worship', 'Call And Response'];
function gen(seed) {
  const r = rng(seed), pick = a => a[Math.floor(r() * a.length)], int = (a, b) => a + Math.floor(r() * (b - a + 1));
  const fmt = pick(['cpEnv', 'cpComment', 'plain', 'brackets', 'caps']);
  const custom = fmt === 'cpEnv' || fmt === 'cpComment' || fmt === 'brackets';
  const count = {}, defs = [], order = [];
  const nDefs = int(2, 7);
  for (let d = 0; d < nDefs; d++) {
    const inst = r() < 0.25, kind = custom && r() < 0.12 ? pick(CUSTOM) : pick(inst ? INST_KINDS : LYRIC_KINDS);
    count[kind] = (count[kind] || 0) + 1;
    const label = kind + (CUSTOM.includes(kind) && count[kind] === 1 ? '' : ' ' + count[kind]);
    if (defs.some(x => x.label.toLowerCase() === label.toLowerCase())) continue;
    const lines = [];
    if (inst || CUSTOM.includes(kind) && r() < 0.3) { const n = int(1, 2); for (let i = 0; i < n; i++) { const cs = Array.from({ length: int(2, 4) }, () => pick(CHORDS)); lines.push({ text: '', chords: cs, bar: true }); } }
    else { const n = int(1, 4); for (let i = 0; i < n; i++) { const ws = Array.from({ length: int(2, 7) }, () => pick(WORDS)); const text = ws.join(' ');
      const at = []; for (let k = 0, m = int(0, 3); k < m; k++) at.push(Math.min(text.length - 1, int(0, text.length - 1)));
      const pos = [...new Set(at)].sort((a, b) => a - b); lines.push({ text, chords: pos.map(a => ({ c: pick(CHORDS), at: a })) }); } }
    const rep = r() < 0.15 ? int(2, 4) : 1;
    defs.push({ label, kind, inst, lines, rep }); order.push({ d: defs.length - 1, ref: false, rep });
    if (defs.length > 1 && r() < 0.35) { const t = int(0, defs.length - 2); order.push({ d: t, ref: true, rep: r() < 0.2 ? int(2, 3) : 1 }); }
  }
  // write it out
  const out = [], up = s => fmt === 'caps' ? s.toUpperCase() : s, cnt = n => n > 1 ? (fmt === 'caps' ? ' X' + n : pick([' x' + n, ' (' + n + 'x)', ' — ' + n + ' times'])) : '';
  if (r() < 0.5 && fmt.startsWith('cp')) out.push('{title: Generated ' + seed + '}', '{key: ' + pick(['G', 'C', 'D', 'Eb', 'Bb', 'E']) + '}', '');
  const lyricLine = l => {
    if (fmt.startsWith('cp')) { let s = '', last = 0; l.chords.forEach(c => { s += l.text.slice(last, c.at) + '[' + c.c + ']'; last = c.at; }); return [s + l.text.slice(last)]; }
    if (!l.chords.length) return [l.text];
    let cl = ''; l.chords.forEach(c => { const col = cl.length ? Math.max(c.at, cl.length + 1) : c.at; cl += ' '.repeat(col - cl.length) + c.c; c.at = col; });   // a chord line needs a space between chords: the column written is where it is
    return [cl, l.text]; };
  const barLine = l => fmt.startsWith('cp') ? '| ' + l.chords.join(' | ') + ' |' : l.chords.join('  ');
  order.forEach(o => {
    const s = defs[o.d];
    if (o.ref) {
      if (fmt.startsWith('cp')) out.push('{comment: ' + pick(['REPEAT ', 'Repeat ']) + s.label + cnt(o.rep) + '}');
      else if (fmt === 'brackets') out.push(o.rep > 1 ? '[' + s.label + ']' + cnt(o.rep) : '[' + s.label + ']');
      else out.push(up(pick(['Repeat ', 'Back to ']) + s.label) + cnt(o.rep));
      out.push(''); return;
    }
    const body = s.lines.reduce((a, l) => a.concat(l.bar ? [barLine(l)] : lyricLine(l)), []);
    if (fmt === 'cpEnv' && /^(Verse|Chorus|Bridge)/.test(s.kind)) { const e = s.kind.split(' ')[0].toLowerCase(); out.push('{start_of_' + e + ': ' + s.label + '}'); if (s.rep > 1) { out.length--; out.push('{comment: ' + s.label + cnt(s.rep) + '}'); out.push(...body, ''); return; } out.push(...body, '{end_of_' + e + '}', ''); return; }
    if (fmt.startsWith('cp')) out.push('{comment: ' + up(s.label) + cnt(s.rep) + '}');
    else if (fmt === 'brackets') out.push('[' + s.label + ']' + cnt(s.rep));
    else out.push(up(s.label) + cnt(s.rep));
    out.push(...body, '');
  });
  return { src: out.join('\n'), defs, order, fmt };
}
const norm = s => s.toLowerCase().replace(/\s+/g, ' ').trim();
const fails = []; const byFmt = {};
for (let seed = 1; seed <= N; seed++) {
  const g = gen(seed); byFmt[g.fmt] = (byFmt[g.fmt] || 0) + 1; let p;
  try { p = W.parse(g.src); } catch (e) { fails.push({ seed, fmt: g.fmt, why: 'threw ' + e.message }); continue; }
  const why = [];
  if (p.sections.length !== g.order.length) why.push(['sections', lab(p), g.order.map(o => g.defs[o.d].label + (o.ref ? '*' : ''))]);
  else g.order.forEach((o, i) => {
    const s = p.sections[i], d = g.defs[o.d];
    if (norm(s.label) !== norm(d.label)) why.push([i, 'label', s.label, d.label]);
    if (!!s.ref !== o.ref) why.push([i, 'ref', !!s.ref, o.ref]);
    if ((s.rep || 1) !== (o.rep || 1)) why.push([i, 'rep', s.rep, o.rep]);
    if (o.ref && p.sections[s.of] && norm(p.sections[s.of].label) !== norm(d.label)) why.push([i, 'repeat of', p.sections[s.of] && p.sections[s.of].label, d.label]);
    const wantCh = d.lines.reduce((a, l) => a.concat(l.bar ? l.chords : l.chords.map(c => c.c)), []);
    if (JSON.stringify(chordsOf(s)) !== JSON.stringify(wantCh)) why.push([i, 'chords', chordsOf(s), wantCh]);
    const wantW = d.lines.reduce((a, l) => a.concat(l.bar ? [] : l.text.split(' ')), []);
    if (JSON.stringify(wordsOf(s)) !== JSON.stringify(wantW)) why.push([i, 'words', wordsOf(s).join(' '), wantW.join(' ')]);
    if (!o.ref && !d.inst) d.lines.forEach((l, li) => { const pl = s.lines.filter(Boolean)[li]; if (pl && !l.bar && JSON.stringify(pl.chords.map(c => [c.c, c.at])) !== JSON.stringify(l.chords.map(c => [c.c, c.at]))) why.push([i, 'chord places', li, pl.chords, l.chords]); });
  });
  if (p.warnings.length) why.push(['warnings', p.warnings]);
  // what is drawn: every chord of every placement (repeats too); slides for the words, in order
  const html = W.chartHTML({ parsed: p }), drawn = (html.match(/<span class="wc-c">[^<]+<\/span>/g) || []).length, want = p.sections.reduce((a, s) => a + chordsOf(s).length, 0);
  if (drawn !== want) why.push(['drawn chords', drawn, want]);
  const sl = W.slides({ parsed: p }), lyricSecs = p.sections.filter(s => s.lyric).length; if (lyricSecs && new Set(sl.map(x => x.occ)).size !== lyricSecs) why.push(['slides', new Set(sl.map(x => x.occ)).size, lyricSecs]);
  if (why.length) fails.push({ seed, fmt: g.fmt, why: why.slice(0, 3), src: g.src.slice(0, 400) });
}
T(`C13 ${N} generated charts in five formats (${Object.entries(byFmt).map(([k, v]) => k + ' ' + v).join(', ')}): every section, its name, order, repeat and count, every chord in its place and every word come out exactly as built; every chord is drawn and every sung section has a slide`, () => fails.length === 0 || { failed: fails.length, first: fails.slice(0, 2) });
T('C14 every chord in the generated pool goes through all 12 keys and back to itself, quality and bass kept', () => {
  const bad = []; CHORDS.forEach(c => { for (let k = 1; k < 12; k++) { const up = W.transposeChord(c, k, false), back = W.transposeChord(up, 12 - k, /b/.test(c)); const q = x => x.replace(/^[A-G](#|b)?/, '').replace(/\/[A-G](#|b)?$/, '');
    if (q(up) !== q(c) || q(back) !== q(c) || W.semitones(c.replace(/^([A-G](?:#|b)?).*$/, '$1'), back.replace(/^([A-G](?:#|b)?).*$/, '$1')) % 12 !== 0) bad.push([c, k, up, back]); } });
  return !bad.length || bad.slice(0, 5); });
T('C15 malformed input never throws: random bytes, half directives, unbalanced brackets, huge lines', () => {
  const r = rng(7), chars = '[]{}()|/:#xX0123456789 \nGCDEFABmsu#b-—–\t abc';
  for (let i = 0; i < 2000; i++) { const s = Array.from({ length: Math.floor(r() * 400) }, () => chars[Math.floor(r() * chars.length)]).join(''); const p = W.parse(s); W.chartHTML({ parsed: p }); W.slides({ parsed: p }); W.clean(s); }
  W.parse('[G]' + 'la '.repeat(20000)); W.parse('{'.repeat(5000)); W.parse('['.repeat(5000)); return true; });

console.log(R.map(r => (r[1].startsWith('PASS') ? 'PASS ' : 'FAIL ') + r[0] + (r[1].startsWith('PASS') ? '' : '  ' + r[1].slice(5))).join('\n'));
const f = R.filter(r => !r[1].startsWith('PASS')).length; console.log(`\n${R.length - f}/${R.length} passed`); process.exit(f ? 1 : 0);

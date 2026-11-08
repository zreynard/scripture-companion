// QA layer 1: the song engine (site_extra/worship.js). Made-up lyrics only. node tools/qa/engine.js
require('../../site_extra/worship.js'); const W = globalThis.Worship;
const R = []; const T = (n, f) => { try { const r = f(); R.push([n, r === true ? 'PASS' : 'FAIL ' + JSON.stringify(r)]); } catch (e) { R.push([n, 'FAIL threw ' + e.message]); } };
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b) || { got: a, want: b };
const tr = (c, from, to) => W.transposeChord(c, W.semitones(from, to), to);
// --- transposition
T('E1 major chords G→A', () => eq(['G', 'C', 'D', 'Em'].map(c => tr(c, 'G', 'A')), ['A', 'D', 'E', 'F#m']));
T('E2 slash chords keep both notes', () => eq(['D/F#', 'G/B', 'C/E', 'Am/G'].map(c => tr(c, 'G', 'A')), ['E/G#', 'A/C#', 'D/F#', 'Bm/A']));
T('E3 qualities survive', () => eq(['Cmaj7', 'Dm7', 'Esus4', 'Fadd9', 'G7', 'Am7b5', 'Bdim', 'C+', 'Dsus2', 'E7(b9)', 'C6', 'Dm9', 'G13'].map(c => tr(c, 'C', 'D')), ['Dmaj7', 'Em7', 'F#sus4', 'Gadd9', 'A7', 'Bm7b5', 'C#dim', 'D+', 'Esus2', 'F#7(b9)', 'D6', 'Em9', 'A13']));
T('E4 flat keys spell with flats', () => eq(['C', 'G', 'D/F#', 'Am', 'E'].map(c => tr(c, 'C', 'Eb')), ['Eb', 'Bb', 'F/A', 'Cm', 'G']));
T('E5 sharp keys spell with sharps', () => eq(['C', 'F', 'G', 'Dm', 'Bb'].map(c => tr(c, 'C', 'E')), ['E', 'A', 'B', 'F#m', 'D']));
T('E6 F major uses Bb not A#', () => eq(tr('G', 'C', 'F').concat ? [tr('F', 'C', 'F'), tr('F', 'G', 'C')] : 0, ['Bb', 'Bb']));
T('E7 twelve semitones round trip', () => { const cs = ['G', 'D/F#', 'Em7', 'Cadd9', 'Bbmaj7', 'F#m7b5']; return eq(cs.map(c => W.transposeChord(c, 12, W.useFlats('G'))).map((c, i) => W.semitones(c.replace(/[^A-G#b].*$/, ''), cs[i].replace(/[^A-G#b].*$/, ''))), [0, 0, 0, 0, 0, 0]); });
T('E8 up then down returns the chord', () => { const cs = ['G', 'D/F#', 'Em7', 'Cadd9', 'A7sus4']; return eq(cs.map(c => W.transposeChord(W.transposeChord(c, 5, false), -5, false)), cs); });
T('E9 every key: transposeKey', () => eq(['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'].map(k => W.transposeKey(k, 1)), ['Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B', 'C']));
T('E10 minor keys', () => eq([W.transposeKey('Am', 2), W.transposeKey('Em', -2), W.transposeKey('F#m', 1), W.useFlats('Dm'), W.useFlats('Em')], ['Bm', 'Dm', 'Gm', true, false]));
T('E11 semitones both ways', () => eq([W.semitones('G', 'A'), W.semitones('A', 'G'), W.semitones('C', 'C'), W.semitones('B', 'C')], [2, 10, 0, 1]));
T('E12 unknown text is left alone', () => eq(['N.C.', 'x2', '|', 'Hello'].map(c => W.transposeChord(c, 3, false)), ['N.C.', 'x2', '|', 'Hello']));
T('E13 enharmonic input', () => eq(['Gb', 'F#', 'Cb', 'B#'].map(c => tr(c, 'C', 'D')), ['G#', 'G#', 'C#', 'D']));
T('E14 isChord rejects words', () => eq(['A', 'Am', 'Bb', 'C#m7', 'D/F#', 'Esus', 'Go', 'And', 'Am I', 'Be', 'Each', 'Dad', 'Add'].map(W.isChord), [true, true, true, true, true, true, false, false, false, false, false, false, false]));
// --- reading charts
const P = t => W.parse(t), labels = t => P(t).sections.map(s => s.label);
T('E15 plain section names', () => eq(labels('Verse 1\nwords\n\nChorus\nwords\n\nBridge\nwords'), ['Verse 1', 'Chorus', 'Bridge']));
T('E16 bracketed and colon names', () => eq(labels('[Verse 1]\na\n\n[Chorus]\nb\n\nPre-Chorus:\nc\n\n(Bridge)\nd\n\nTag:\ne'), ['Verse 1', 'Chorus', 'Pre-Chorus', 'Bridge', 'Tag']));
T('E17 lower and upper case names', () => eq(labels('VERSE 1\na\n\nchorus\nb\n\nPRE CHORUS\nc'), ['VERSE 1', 'Chorus', 'Pre-Chorus']));
T('E18 [Chorus] is not a C chord', () => eq(P('[Chorus]\nG   D\nwords here').sections[0].lines[0].text, 'words here'));
T('E19 [Bridge] and [Bb] told apart', () => { const p = P('[Bridge]\n[Bb]words [F]more'); return eq([p.sections[0].label, p.sections[0].lines[0].chords.map(c => c.c)], ['Bridge', ['Bb', 'F']]); });
T('E20 chords over words keep columns', () => eq(P('Verse\nG      D/F#   Em\nAmazing words go here').sections[0].lines[0].chords, [{ c: 'G', at: 0 }, { c: 'D/F#', at: 7 }, { c: 'Em', at: 14 }]));
T('E21 chord past the end of the words', () => { const l = P('Verse\nG               D\nshort').sections[0].lines[0]; return eq([l.chords[1].at <= l.text.length, l.chords.length], [true, 2]); });
T('E22 chord-only line (instrumental)', () => { const s = P('Intro\nG  D  Em  C').sections[0]; return eq([s.lyric, s.lines[0].chords.length], [false, 4]); });
T('E23 Intro: G D on one line', () => eq(P('Intro: G D Em C').sections[0].lines[0].chords.map(c => c.c), ['G', 'D', 'Em', 'C']));
T('E24 repeat marker x2', () => eq(P('Chorus x2\nwords').sections[0].rep, 2));
T('E25 (Chorus x2) with no words repeats the chorus', () => { const p = P('Chorus\nhello there\n\nVerse 2\nmore\n\n(Chorus x2)'); return eq([p.sections[2].ref, p.sections[2].lines[0].text, p.sections[2].rep], [1, 'hello there', 2]); });
T('E26 bar lines and dashes in chord lines', () => eq(P('Intro\n| G - - - | D / / / | Em |').sections[0].lines[0].chords.map(c => c.c), ['G', 'D', 'Em']));
T('E27 ChordPro directives', () => { const p = P('{title: T}\n{artist: A}\n{key: Bb}\n{capo: 3}\n{start_of_verse: Verse 1}\n[Bb]a [F]b\n{end_of_verse}\n{soc}\n[Eb]c\n{eoc}'); return eq([p.meta.title, p.meta.artist, p.meta.key, p.meta.capo, labels('{sov}\na\n{eov}\n{soc}\nb\n{eoc}')], ['T', 'A', 'Bb', 3, ['Verse 1', 'Chorus']]); });
T('E28 ChordPro {c: Chorus} as a section', () => eq(labels('{c: Chorus}\n[G]a'), ['Chorus']));
T('E29 no names at all: still one section', () => eq(P('just words\nmore words').sections.length, 1));
T('E30 empty and junk input do not throw', () => eq([P('').sections.length, P('\n\n\n').sections.length, P(null).sections.length, P('{}').sections.length], [0, 0, 0, 0]));
T('E31 Windows line endings and tabs', () => eq(labels('Verse 1\r\nG\tD\r\nwords\r\n\r\nChorus\r\nmore'), ['Verse 1', 'Chorus']));
T('E32 a word starting with A is not a chord line', () => eq(P('Verse\nA mighty word here').sections[0].lines[0].chords.length, 0));
T('E33 lyric line "A" (single letter) beside chords', () => eq(P('Verse\nG\nA long line of words').sections[0].lines.length, 1));
T('E34 duplicate names number themselves in order', () => eq(P('Verse\na\n\nVerse\nb').sections.map(s => s.lines[0].text), ['a', 'b']));
T('E35 short codes', () => eq(['Verse 1', 'Chorus', 'Pre-Chorus', 'Bridge 2', 'Intro', 'Outro', 'Tag', 'Instrumental', 'Interlude'].map(W.shortOf), ['V1', 'C', 'PC', 'B2', 'I', 'O', 'T', 'Inst', 'Inst']));
// --- slides for the TV
const S = t => W.slides({ src: t });
T('E36 whole section on one slide when it fits', () => eq(S('Chorus\n' + 'line,\n'.repeat(8)).length, 1));
T('E37 long section splits, never one-line leftovers', () => { const sl = S('Verse 1\n' + Array.from({ length: 13 }, (_, i) => 'line ' + i + (i % 2 ? '.' : ',')).join('\n')); return sl.every(x => x.l.length >= 3) || sl.map(x => x.l.length); });
T('E38 split prefers the stanza break', () => eq(S('Verse\na,\nb.\nc,\nd.\ne,\nf.\n\ng,\nh,\ni,\nj.').map(x => x.l.length), [6, 4]));
T('E39 no slide over 8 screen lines', () => { const sl = S('Verse\n' + Array.from({ length: 40 }, (_, i) => 'this is a fairly long lyric line number ' + i).join('\n')); return sl.every(x => x.l.reduce((a, t) => a + Math.ceil(t.length / 34), 0) <= 8) || sl.map(x => x.l.length); });
T('E40 instrumental parts get no slide; a song with no words keeps one blank slide', () => eq([S('Intro\nG D\n\nVerse\nwords').map(x => x.l.length), S('Intro\nG D\n\nInterlude\nC G').map(x => x.l.length)], [[1], [0]]));
T('E41 arrangement order with repeats', () => { const p = P('Verse 1\na\n\nChorus\nb\n\nVerse 2\nc'); return eq(W.slides({ parsed: p }, [0, 1, 2, 1, 1]).map(x => x.s), ['Verse 1', 'Chorus', 'Verse 2', 'Chorus', 'Chorus']); });
T('E42 slides carry section and occurrence', () => { const sl = W.slides({ parsed: P('Verse 1\na\n\nChorus\nb') }, [0, 1, 1]); return eq(sl.map(x => [x.sec, x.occ]), [[0, 0], [1, 1], [1, 2]]); });
T('E43 slides hold no chords or brackets', () => S('Verse\n[G]a [D]b\nC  G\nwords here').every(x => x.l.every(t => !/\[|\]/.test(t) && !/^\s*[A-G]\s+[A-G]\s*$/.test(t))));
// --- chart HTML is escaped (no injection from a pasted chart)
T('E44 chart HTML escapes tags', () => { const h = W.chartHTML({ src: 'Verse <img src=x onerror=alert(1)>\n<script>alert(1)</script>\n[G]<b>bold</b>' }); return !/<script|<img|<b>/.test(h) || h; });
T('E45 chart HTML transposes', () => /F#m/.test(W.chartHTML({ src: 'Verse\nEm\nwords' }, { semis: 2, flats: false })));
T('E46 compact repeats print the label only', () => { const h = W.chartHTML({ src: 'Chorus\nhello\n\nVerse\nx\n\nChorus' }, { compactRepeats: true }); return (h.match(/hello/g) || []).length === 1 || h; });
T('E47 huge chart (2,000 lines) is fast', () => { const t0 = Date.now(); const big = Array.from({ length: 250 }, (_, i) => 'Verse ' + i + '\nG   D\nwords and more words\nEm  C\nanother line here\n').join('\n'); const p = P(big); W.slides({ parsed: p }); W.chartHTML({ parsed: p }); return (Date.now() - t0 < 1500 && p.sections.length === 250) || { ms: Date.now() - t0, n: p.sections.length }; });
T('E48 unicode and smart quotes kept', () => eq(P('Verse\nG\n’Tis grace – “holy” é').sections[0].lines[0].text, '’Tis grace – “holy” é'));
T('E49 borrowed chords spelled with flats in sharp keys', () => eq([tr('Bb', 'C', 'G'), tr('Eb', 'C', 'D'), tr('Ab', 'C', 'A'), tr('Bb', 'C', 'E')], ['F', 'F', 'F', 'D']));
T('E50 secondary dominants keep sharps', () => eq([tr('E/G#', 'C', 'G'), tr('A7', 'C', 'D'), tr('D/F#', 'C', 'A')], ['B/D#', 'B7', 'B/D#']));
T('E51 flat keys stay flat', () => eq(['C', 'Dm', 'Em', 'F', 'G', 'Am'].map(c => tr(c, 'C', 'Bb')), ['Bb', 'Cm', 'Dm', 'Eb', 'F', 'Gm']));
T('E52 minor key relative spelling', () => eq(['Am', 'C', 'Dm', 'E', 'G'].map(c => tr(c, 'Am', 'Gm')), ['Gm', 'Bb', 'Cm', 'D', 'F']));
T('E53 slash basses follow their chord', () => eq([tr('C/E', 'C', 'Db'), tr('G/B', 'G', 'Ab'), tr('F/A', 'F', 'E'), tr('D/A', 'D', 'Eb'), tr('Am/G', 'C', 'Bb')], ['Db/F', 'Ab/C', 'E/G#', 'Eb/Bb', 'Gm/F']));
// --- chords never split words
T('E54 a chord inside a word moves to the start of that word', () => eq(W.snapChords('walk the town', [{ c: 'G', at: 11 }, { c: 'D', at: 2 }]), [{ c: 'D', at: 0 }, { c: 'G', at: 9 }]));
T('E55 a chord on the space before a word sits on the word; chords after the words stay put', () => eq(W.snapChords('if you go', [{ c: 'C', at: 6 }, { c: 'D', at: 12 }, { c: 'G', at: 0 }]), [{ c: 'G', at: 0 }, { c: 'C', at: 7 }, { c: 'D', at: 9 }]));
T('E56 rendered chart never cuts a word between two chord pieces, and keeps every chord', () => {
  const src = 'Verse 1\n  G     D        Em    C\nwalking slowly across the river\n   C        G   D/F#\nsinging all the way along home  \n\nChorus\nEm  D   C   G\n  carry me further up the hill  G  D';
  const html = W.chartHTML({ parsed: W.parse(src) }, {}); const bad = [];
  for (const line of html.split('<div class="wc-l').slice(1)) { const segs = [...line.matchAll(/<span class="wc-t">([^<]*)<\/span>/g)].map(m => m[1].replace(/&nbsp;/g, ' '));
    for (let i = 1; i < segs.length; i++) if (/\w$/.test(segs[i - 1]) && /^\w/.test(segs[i])) bad.push(segs[i - 1].slice(-4) + '|' + segs[i].slice(0, 4)); }
  const n = (html.match(/<span class="wc-c">[^<]+<\/span>/g) || []).length;
  return (bad.length === 0 && n === 11) || { bad, n }; });
// --- words split into syllables are put back together
T('E57 syllable splits join: spaced, unspaced, many parts', () => eq(['for - ev - er and ev - er', 'Ho-ly, ho-ly', 'Hal-le-lu-jah', 'A - men', 'a - bove'].map(x => W.desyl({ text: x, chords: [] }).text), ['forever and ever', 'Holy, holy', 'Hallelujah', 'Amen', 'above']));
T('E58 real dashes and compound words stay', () => eq(['Jesus - Lord of all', 'God - the One', 'never-ending love', 'yes - and amen'].map(x => W.desyl({ text: x, chords: [] }).text), ['Jesus - Lord of all', 'God - the One', 'never-ending love', 'yes - and amen']));
T('E59 chords keep their syllable after joining', () => eq(W.desyl({ text: 'for - ev - er more', chords: [{ c: 'G', at: 0 }, { c: 'D', at: 6 }, { c: 'C', at: 14 }] }).chords, [{ c: 'G', at: 0 }, { c: 'D', at: 3 }, { c: 'C', at: 8 }]));
T('E60 the TV slides show whole words', () => { const sl = W.slides({ parsed: W.parse('Chorus\nG          D\nwe sing for - ev - er\nC        G\nHal-le-lu-jah') }); const txt = JSON.stringify(sl); return (!/ - [a-z]|[a-z]-[a-z]/.test(txt) && /forever/.test(txt) && /Hallelujah/.test(txt)) || txt.slice(0, 200); });
console.log(R.map(r => (r[1].startsWith('PASS') ? 'PASS ' : 'FAIL ') + r[0] + (r[1].startsWith('PASS') ? '' : '  ' + r[1].slice(5, 300))).join('\n'));
const f = R.filter(r => !r[1].startsWith('PASS')).length; console.log(`\n${R.length - f}/${R.length} passed`); process.exit(f ? 1 : 0);

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
T('E17 lower and upper case names (an ALL-CAPS name shows in title case)', () => eq(labels('VERSE 1\na\n\nchorus\nb\n\nPRE CHORUS\nc'), ['Verse 1', 'Chorus', 'Pre-Chorus']));
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
T('E46 a repeated section is shown in full where it is sung, marked (repeat)', () => { const h = W.chartHTML({ src: 'Chorus\nhello\n\nVerse\nx\n\nChorus' }, { compactRepeats: true }); return ((h.match(/hello/g) || []).length === 2 && /Chorus <i>\(repeat\)<\/i>/.test(h)) || h; });
T('E47 huge chart (2,000 lines) is fast', () => { const t0 = Date.now(); const big = Array.from({ length: 250 }, (_, i) => 'Verse ' + i + '\nG   D\nwords and more words\nEm  C\nanother line here\n').join('\n'); const p = P(big); W.slides({ parsed: p }); W.chartHTML({ parsed: p }); return (Date.now() - t0 < 1500 && p.sections.length === 250) || { ms: Date.now() - t0, n: p.sections.length }; });
T('E48 unicode and smart quotes kept', () => eq(P('Verse\nG\n’Tis grace – “holy” é').sections[0].lines[0].text, '’Tis grace – “holy” é'));
T('E49 borrowed chords spelled with flats in sharp keys', () => eq([tr('Bb', 'C', 'G'), tr('Eb', 'C', 'D'), tr('Ab', 'C', 'A'), tr('Bb', 'C', 'E')], ['F', 'F', 'F', 'D']));
T('E50 secondary dominants keep sharps', () => eq([tr('E/G#', 'C', 'G'), tr('A7', 'C', 'D'), tr('D/F#', 'C', 'A')], ['B/D#', 'B7', 'B/D#']));
T('E51 flat keys stay flat', () => eq(['C', 'Dm', 'Em', 'F', 'G', 'Am'].map(c => tr(c, 'C', 'Bb')), ['Bb', 'Cm', 'Dm', 'Eb', 'F', 'Gm']));
T('E52 minor key relative spelling', () => eq(['Am', 'C', 'Dm', 'E', 'G'].map(c => tr(c, 'Am', 'Gm')), ['Gm', 'Bb', 'Cm', 'D', 'F']));
T('E53 slash basses follow their chord', () => eq([tr('C/E', 'C', 'Db'), tr('G/B', 'G', 'Ab'), tr('F/A', 'F', 'E'), tr('D/A', 'D', 'Eb'), tr('Am/G', 'C', 'Bb')], ['Db/F', 'Ab/C', 'E/G#', 'Eb/Bb', 'Gm/F']));
// --- chords never split words
T('E54 a chord inside a word stays on its letter; one written over a space moves on to the next word', () => eq(W.snapChords('walk the town', [{ c: 'G', at: 11 }, { c: 'D', at: 2 }, { c: 'C', at: 4 }]), [{ c: 'D', at: 2 }, { c: 'C', at: 5 }, { c: 'G', at: 11 }]));
T('E55 a chord on the space before a word sits on the word; chords after the words stay put', () => eq(W.snapChords('if you go', [{ c: 'C', at: 6 }, { c: 'D', at: 12 }, { c: 'G', at: 0 }]), [{ c: 'G', at: 0 }, { c: 'C', at: 7 }, { c: 'D', at: 9 }]));
T('E56 where a chord falls inside a word, the piece after it is drawn floating (so the word reads whole), and every chord is kept', () => {
  const src = 'Verse 1\n  G     D        Em    C\nwalking slowly across the river\n   C        G   D/F#\nsinging all the way along home  \n\nChorus\nEm  D   C   G\n  carry me further up the hill  G  D';
  const html = W.chartHTML({ parsed: W.parse(src) }, {}); const bad = []; let cuts = 0;
  for (const line of html.split('<div class="wc-l').slice(1)) { const segs = [...line.matchAll(/<span class="wc-w( wc-in)?">(?:<span class="wc-c">[^<]*<\/span>)?<span class="wc-t">([^<]*)<\/span>/g)].map(m => ({ fl: !!m[1], t: m[2].replace(/&nbsp;/g, ' ') }));
    for (let i = 1; i < segs.length; i++) if (/\w$/.test(segs[i - 1].t) && /^\w/.test(segs[i].t)) { cuts++; if (!segs[i].fl) bad.push(segs[i - 1].t.slice(-4) + '|' + segs[i].t.slice(0, 4)); } }
  const n = (html.match(/<span class="wc-c">[^<]+<\/span>/g) || []).length;
  return (bad.length === 0 && cuts > 0 && n === 11) || { bad, cuts, n }; });
// --- words split into syllables are put back together
T('E57 syllable splits join: spaced, unspaced, many parts', () => eq(['for - ev - er and ev - er', 'Ho-ly, ho-ly', 'Hal-le-lu-jah', 'A - men', 'a - bove'].map(x => W.desyl({ text: x, chords: [] }).text), ['forever and ever', 'Holy, holy', 'Hallelujah', 'Amen', 'above']));
T('E58 real dashes and compound words stay', () => eq(['Jesus - Lord of all', 'God - the One', 'never-ending love', 'yes - and amen'].map(x => W.desyl({ text: x, chords: [] }).text), ['Jesus - Lord of all', 'God - the One', 'never-ending love', 'yes - and amen']));
T('E59 chords keep their syllable after joining', () => eq(W.desyl({ text: 'for - ev - er more', chords: [{ c: 'G', at: 0 }, { c: 'D', at: 6 }, { c: 'C', at: 14 }] }).chords, [{ c: 'G', at: 0 }, { c: 'D', at: 3 }, { c: 'C', at: 8 }]));
T('E60 the TV slides show whole words', () => { const sl = W.slides({ parsed: W.parse('Chorus\nG          D\nwe sing for - ev - er\nC        G\nHal-le-lu-jah') }); const txt = JSON.stringify(sl); return (!/ - [a-z]|[a-z]-[a-z]/.test(txt) && /forever/.test(txt) && /Hallelujah/.test(txt)) || txt.slice(0, 200); });
// --- a whole chord-site page pasted in (made-up song and words)
const UG = `tabs.example.com
Search
Lantern Road Chords by Test Band
30,892 views, added to favorites 2,907 times
Rating: ★ 4.9 / 5 (126)
Difficulty: Beginner
Tuning: E A D G B E
Author: someone
Last edit: Feb 12, 2026
Add to favorites
CHORDS
GUITAR
G
2 1   3
PLAY
C
3 2   1
PLAY
VIEW IN APP
TRANSPOSE
LISTEN
PDF
G C G/B C

[Verse 1]
G              C      G
Walking down a lantern road
C              G/B    Am7
Carrying a borrowed load

ADVERTISEMENT
OPEN IN APP
Skip Ad
Ad : (0:27)

[Pre-Chorus]
                    D
Ooo ooo, the evening light
Em              G/B
x2

[Chorus]
G
Sing it softly
Em
Sing it slowly

[Verse 2]
G              C      G
Morning comes across the field
C              G/B    Am7
Print

[Chorus]

[Bridge]
G          D
Home is near, home is near

[Ending]
G
Home is near

Print
Report Bad Tab
Please rate this tab
★★★★★ 126
VERSIONS
Official 11`;
T('E61 a pasted chord-site page keeps only the chart: header, chord diagrams, buttons, ads and footer gone', () => {
  const c = W.clean(UG), p = W.parse(c.src), labels = p.sections.map(s => s.label + (s.ref ? '*' : ''));
  const bad = ['Search', 'views', 'Rating', 'Tuning', 'Author', 'PLAY', 'VIEW IN APP', 'TRANSPOSE', 'ADVERTISEMENT', 'OPEN IN APP', 'Skip Ad', 'Ad :', 'Report Bad Tab', 'VERSIONS', '★', '2 1'].filter(x => c.src.includes(x));
  return (eq(labels, ['Intro', 'Verse 1', 'Pre-Chorus', 'Chorus', 'Verse 2', 'Chorus*', 'Bridge', 'Ending']) === true && !bad.length && c.title === 'Lantern Road' && c.artist === 'Test Band'
    && /^Intro\nG C G\/B C/.test(c.src) && c.dropped >= 25) || { labels, bad, title: c.title, artist: c.artist, head: c.src.slice(0, 40), dropped: c.dropped };
});
T('E62 the paste clean-up never drops a chart line: a sung "Ooo", a lone "x2" and a line that just says "Print" inside a verse stay, untouched', () => {
  const c = W.clean(UG);
  return (/\nOoo ooo, the evening light\n/.test(c.src) && /\nx2\n/.test(c.src) && /G\/B    Am7\nPrint\n/.test(c.src) && c.src.includes('G              C      G\nWalking down a lantern road')) || c.src;
});
const EW = `ESSENTIAL
WORSHIP
Transpose:
Eb

INTRO
Cm   Eb   Ab   Eb

VERSE 1
Cm Bb Ab Eb
A made-up first line goes here
Cm Bb
A made-up second line goes here

CHORUS
Bb Cm Ab Eb
Placeholder chorus words

TURNAROUND X2
Bb Cm Ab Eb

VERSE 2
Cm Bb Ab Eb
More invented words here

CHORUS

VAMP 2 X3
Ab Eb/G Ab Eb/G
Invented vamp line

ADD TO PLANNING CENTER
SAVE TO MY SONGS
RESOURCES`;
T('E63 an Essential Worship-style page: key from "Transpose", ALL-CAPS headings with their counts, a bare CHORUS repeats it, the footer is gone', () => {
  const c = W.clean(EW), p = W.parse(c.src), s = p.sections.map(x => x.label + (x.rep > 1 ? ' x' + x.rep : '') + (x.ref ? '*' : ''));
  return (c.key === 'Eb' && eq(s, ['Intro', 'Verse 1', 'Chorus', 'Turnaround x2', 'Verse 2', 'Chorus*', 'Vamp 2 x3']) === true && !/PLANNING|SAVE TO|RESOURCES|ESSENTIAL|Transpose/.test(c.src))
    || { key: c.key, s, src: c.src };
});
T('E64 a chart pasted on its own (no page around it) comes through exactly as it was', () => {
  const plain = '[Verse 1]\nG        C\nAn ordinary invented line\n\n[Chorus]\nD        G\nAnother invented line';
  const c = W.clean(plain); return (c.src === plain && c.dropped === 0 && !c.title) || c;
});
// --- a ChordPro chart with comment headings, "N times", repeats and a final tag (a made-up song)
const CP = `{title: Lantern Road}
{artist: Test Band}
{key: C}

{comment: INTRO}
| Am / F6 / | C / / / |

{start_of_verse: Verse 1}
[Am]Walking down the [F6]lantern road to[C]night
[Am]Carrying a [F6]borrowed light[C]
{end_of_verse}

{start_of_chorus: Chorus 1}
Sing it [Am]softly [F6]sing it [C]slow
Every [G/C]step a place to go
{end_of_chorus}

{comment: INTERLUDE}
| Am / F6 / | C / / / |

{start_of_verse: Verse 2}
[Am]Morning comes [F6]across the [C]field
{end_of_verse}

{start_of_chorus: Chorus 2}
Hold it [Am]gently [F6] [C]
{end_of_chorus}

{comment: TAG — 3 TIMES}
Hold it [Am]gently [F6] [C]

{start_of_bridge: Bridge}
I can see the [Am]lamps a[F]long the [C/E]way [G]
{end_of_bridge}

{comment: INTERLUDE}
| Am / F6 / | C / / / |

{start_of_verse: Verse 3}
[Am]Home is near and [F6]so is [Em7]rest
{end_of_verse}

{start_of_chorus: Chorus 3}
Walk it [Am]slowly [F6]home with [C]me
{end_of_chorus}

{comment: REPEAT BRIDGE}

{comment: REPEAT CHORUS 3}

{comment: FINAL TAG — 4 TIMES}
Walk it [Am]slowly [F6]home with [C]me`;
T('E65 a ChordPro chart with comment headings: repeats ("REPEAT BRIDGE"), counts ("— 3 TIMES") and a "FINAL TAG" all come through, in order', () => {
  const p = W.parse(CP), s = p.sections.map(x => x.label + (x.rep > 1 ? ' x' + x.rep : '') + (x.ref ? '*' : ''));
  return eq(s, ['Intro', 'Verse 1', 'Chorus 1', 'Interlude', 'Verse 2', 'Chorus 2', 'Tag x3', 'Bridge', 'Interlude', 'Verse 3', 'Chorus 3', 'Bridge*', 'Chorus 3*', 'Final Tag x4']);
});
T('E66 the same ChordPro chart: title, artist and key read; the Final Tag keeps its own lines (not glued to the chorus before); chords sit on their syllables, at line ends too', () => {
  const p = W.parse(CP), ft = p.sections.find(x => x.label === 'Final Tag'), c3 = p.sections.find(x => x.label === 'Chorus 3' && !x.ref);
  const v1 = p.sections.find(x => x.label === 'Verse 1').lines[0], v2 = p.sections.find(x => x.label === 'Verse 1').lines[1], end = v2.chords[v2.chords.length - 1], mid = v1.chords[v1.chords.length - 1];
  const kind = ft && W.parse('{comment: FINAL TAG}\nx').sections[0].kind;
  return (p.meta.title === 'Lantern Road' && p.meta.artist === 'Test Band' && p.meta.key === 'C' && ft && ft.lines.length === 1 && c3.lines.length === 1 && kind === 'tag'
    && v1.chords[0].c === 'Am' && v1.chords[0].at === 0 && v1.text.slice(v1.chords[1].at, v1.chords[1].at + 7) === 'lantern' && mid.c === 'C' && v1.text.slice(mid.at, mid.at + 5) === 'night' && end.c === 'C' && end.at >= v2.text.replace(/\s+$/, '').length - 1)
    || { meta: p.meta, ft: ft && ft.lines.length, c3: c3 && c3.lines.length, kind, v1: v1.text, ch: v1.chords, v2: v2.text, ch2: v2.chords };
});
T('E67 F6, G/C, C/E and Em7 move up a step from C to D', () => eq(['F6', 'G/C', 'C/E', 'Em7'].map(c => tr(c, 'C', 'D')), ['G6', 'A/D', 'D/F#', 'F#m7']));
T('E68 pasting a ChordPro chart: clean keeps every line (directives too) and reads the title, artist and key from it', () => { const c = W.clean(CP); return (c.src === CP && c.title === 'Lantern Road' && c.artist === 'Test Band' && c.key === 'C' && c.dropped === 0) || { t: c.title, a: c.artist, k: c.key, d: c.dropped, same: c.src === CP }; });
T('E69 headings written other ways: "Chorus (3x)", "Back to Chorus", "Last Chorus", "TAG X5" — and a lyric that merely starts with "Sing" is not a heading', () => {
  const s = W.parse('Chorus\nG\nan invented line\n\nVerse\nC\nanother one\n\nChorus (3x)\n\nBack to Chorus\n\nLast Chorus\nD\nthe end line\n\nTAG X5\nG\nlast\n\nVerse 2\nG\nSing a new song to the test\n').sections.map(x => x.label + (x.rep > 1 ? ' x' + x.rep : '') + (x.ref ? '*' : ''));
  return eq(s, ['Chorus', 'Verse', 'Chorus x3*', 'Chorus*', 'Last Chorus', 'Tag x5', 'Verse 2']);
});
// --- the whole pipeline on made-up songs shaped like real charts (no real lyrics anywhere in these tests)
// shaped like a chart with a chorus repeat by instruction, two custom-named instrumental passages and an alternate chorus
const SHAPE_A = `{title: Morning Field}
{artist: Test Band}
{key: B}

{comment: INTRO}
| B | B | G#m | G#m |
| F# | F# | E | E |

{start_of_verse: Verse 1}
All the li[B]ght comes in
Over e[G#m]very hill
Where the [F#]river bends
On the qu[E]iet sill
{end_of_verse}

{start_of_verse: Verse 2}
I could w[B]alk this road
As I o[G#m]ften do
{end_of_verse}

{start_of_chorus: Chorus}
So we r[B]aise a sound
Over all the [F#]ground
And the morning is a can[E]delight
[G#m]Hey - la - [F#]hey

And we k[B]now the way
And we sing a [F#]song
[G#m]Hey - la - [F#]hey - l[B]a
{end_of_chorus}

{start_of_verse: Verse 3}
There's a [B]brand new day
There's a [G#m]road to take
With the [F#]lanterns lit
For the [E]morning's sake
{end_of_verse}

{comment: REPEAT CHORUS}

{comment: CHANNEL 1}
| B | B | B | B |
| B | B | B | B |

{start_of_bridge: Bridge}
[B]Come along the road
[F#]Lift a lantern high
Get up and walk the [B]road [F#]
{end_of_bridge}

{comment: CHANNEL 2}
| E | E | G#m | F# |

{start_of_chorus: Alternate Chorus}
So we r[B]aise a sound
Over all the [F#m]ground
[Em]Hey - la - h[B]ey
{end_of_chorus}`;
const kinds = p => p.sections.map(s => s.label + (s.rep > 1 ? ' x' + s.rep : '') + (s.ref ? '*' : '') + (s.missing ? '?' : ''));
T('E70 a chorus repeated by instruction is placed where it is sung; custom-named passages (CHANNEL 1, CHANNEL 2) are sections of their own; an alternate chorus keeps its own words', () => {
  const p = W.parse(SHAPE_A), k = kinds(p);
  const v3 = p.sections.find(s => s.label === 'Verse 3'), rep = p.sections[5], ch1 = p.sections.find(s => s.label === 'Channel 1'), alt = p.sections.find(s => s.label === 'Alternate Chorus'), cho = p.sections.find(s => s.label === 'Chorus' && !s.ref);
  return (eq(k, ['Intro', 'Verse 1', 'Verse 2', 'Chorus', 'Verse 3', 'Chorus*', 'Channel 1', 'Bridge', 'Channel 2', 'Alternate Chorus']) === true
    && v3.lines.length === 4 && rep.of === 3 && rep.lines === cho.lines && ch1.kind === 'instrumental' && !ch1.lyric && ch1.lines.length === 2 && !alt.ref && alt.kind === 'chorus' && alt.short === 'AC' && alt.lines.length === 3 && !p.warnings.length)
    || { k, v3: v3 && v3.lines.length, of: rep.of, ch1: ch1 && [ch1.kind, ch1.lines.length], alt: alt && [alt.ref, alt.kind, alt.short, alt.lines.length], w: p.warnings };
});
T('E71 how a repeat finds its section: the same name; else the same kind and number; with no number the nearest one before; "Verse 2" never stands in for "Verse 1"; an asked-for repeat of something not in the chart stays in place, marked, and is reported', () => {
  const p = W.parse('Chorus 1\nG\naaa\n\nChorus 2\nC\nbbb\n\nVerse 1\nD\nccc\n\nRepeat Chorus\n\nRepeat Chorus 1\n\n{comment: Repeat CHORUS 2 x2}\n\nVerse 2\n\n{comment: Repeat Hook}\n\n[Hook]\nE\nddd\n\n[Hook]');
  const k = kinds(p), of = p.sections.map(s => s.of == null ? '' : s.of).join(',');
  return (eq(k, ['Chorus 1', 'Chorus 2', 'Verse 1', 'Chorus 2*', 'Chorus 1*', 'Chorus 2 x2*', 'Verse 2', 'Hook*', 'Hook', 'Hook*']) === true && of === ',,,1,0,1,,8,,8' && p.warnings.length === 0)
    || { k, of, w: p.warnings };
});
T('E72 a repeat that matches nothing: kept in place with its name, marked, reported in plain words; nothing invented', () => {
  const p = W.parse('[Verse]\nG\nan invented line\n\n{comment: REPEAT HOOK}'), s = p.sections[1];
  return (s && s.missing && !s.lines.length && s.label === 'Hook' && /REPEAT HOOK.*no Hook in this chart/.test(p.warnings[0] || '')) || { s, w: p.warnings };
});
T('E73 nothing meaningful is dropped: a {comment} inside a section is a note to the band; a sentence-like comment is a note; an unknown directive is reported (and kept in the chart text)', () => {
  const src = '{start_of_verse: Verse 1}\n{comment: softly, guitar only}\n[G]An invented [C]line\n{end_of_verse}\n{comment: everyone in, build to the end}\n{start_of_chorus}\n[D]Another one\n{end_of_chorus}\n{flavour: spicy}\n{tempo: 72}';
  const p = W.parse(src), v = p.sections[0], c = p.sections[1];
  return (eq(kinds(p), ['Verse 1', 'Chorus']) === true && eq(v.notes, ['softly, guitar only']) === true && eq(c.notes, ['everyone in, build to the end']) === true && eq(v.lines.length, 1) === true && eq(c.label, 'Chorus') === true
    && (v.notes.length + (c.notes || []).length + (p.meta.notes || []).length) === 2 && p.meta.tempo === '72' && p.warnings.length === 1 && /flavour/.test(p.warnings[0]))
    || { k: kinds(p), vn: v.notes, cn: c.notes, mn: p.meta.notes, w: p.warnings };
});
T('E74 section names are not a fixed list: {comment: SPOKEN WORD}, [Groove], {start_of_grid: Turn 2}, {comment: Post-Chorus} all become sections; ALL-CAPS names read in title case', () => {
  const p = W.parse('{comment: SPOKEN WORD}\nan invented spoken line\n\n[Groove]\n| G | C |\n\n{start_of_grid: Turn 2}\n| D | D |\n{end_of_grid}\n\n{comment: Post-Chorus}\n[G]oh oh');
  return eq(kinds(p), ['Spoken Word', 'Groove', 'Turn 2', 'Post-Chorus']);
});
T('E75 every chord quality and slash chord survives a trip through all 12 keys and back, and each key spells with its own sharps or flats', () => {
  const CH = ['G', 'Em7', 'Cadd9', 'Dsus4', 'D/F#', 'Am7b5', 'Bbmaj7', 'F#m', 'C#dim', 'Ebsus2', 'Ab6', 'B7(b9)', 'G#m', 'Esus', 'A2', 'F/A', 'Csus2/G', 'Dm(maj7)'];
  const bad = [];
  for (let k = 0; k < 12; k++) {
    const to = W.KEYS_MAJ[(7 + k) % 12], flats = W.useFlats ? W.useFlats(to) : /b/.test(to);
    CH.forEach(c => { const up = W.transposeChord(c, k, flats), back = W.transposeChord(up, (12 - k) % 12, /b/.test(c));
      const pc = x => { const m = /^([A-G](?:#|b)?)/.exec(x); return m && W.NOTE ? W.NOTE[m[1]] : m && m[1]; };
      if (W.NOTE ? pc(back) !== pc(c) : !back) bad.push([c, k, up, back]);
      if (up.replace(/^[A-G](#|b)?/, '').replace(/\/[A-G](#|b)?$/, '') !== c.replace(/^[A-G](#|b)?/, '').replace(/\/[A-G](#|b)?$/, '')) bad.push(['quality', c, k, up]);
      const root = up.replace(/\/.*$/, '').slice(0, 2);   // the root follows the key; a slash bass is spelled as the chord's own note (B/D#)
      if (flats && /#/.test(root) || !flats && /^[A-G]b/.test(root) && k) bad.push(['spelling', c, k, to, up]); });
  }
  return !bad.length || bad.slice(0, 6);
});
T('E76 malformed or odd input never throws and never loses words: an unclosed [G, a stray ], CRLF line ends, tabs, an empty chart, chords only', () => {
  const srcs = ['', '   \n\n', 'Verse 1\r\n[G an unclosed bracket line\r\nstray ] in a line\r\n\tTabbed\tline', '| G | C |\n| D | D |', '{c: }\n{}\n{start_of_chorus}\nno end marker here'];
  const lost = [];
  srcs.forEach(s => { const p = W.parse(s), txt = p.sections.map(x => x.lines.map(l => l ? l.text : '').join(' ')).join(' ');
    ['unclosed', 'bracket', 'stray', 'Tabbed', 'no end marker'].forEach(w => { if (s.includes(w) && !txt.includes(w)) lost.push([w, s.slice(0, 20)]); }); });
  return !lost.length || lost;
});
T('E77 a chord inside a word floats above its letter (the word stays whole); at a word\'s start it keeps its own room; two chords too close inside a word do not overlap', () => {
  const h = W.chartHTML({ src: 'Chorus\nAll that I have is a hal[E]lelujah\n[G#m]Hey - la - [F#]hey\nlan[A]te[B]rn' });
  const lines = h.split('<div class="wc-l').slice(1);
  const whole = l => l.replace(/^[^>]*>/, '').replace(/<span class="wc-c">[^<]*<\/span>/g, '').replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim();
  return (/wc-hasin/.test(lines[0]) && /class="wc-w wc-in"><span class="wc-c">E</.test(lines[0]) && whole(lines[0]) === 'All that I have is a hallelujah'
    && /class="wc-w"><span class="wc-c">G#m/.test(lines[1]) && /wc-in"><span class="wc-c">A</.test(lines[2]) && /class="wc-w"><span class="wc-c">B</.test(lines[2]) && whole(lines[2]) === 'lantern')
    || lines.map(whole);
});
T('E78 nothing is lost between the chart and what is read: every chord and every word of every section written in both test charts is in the result, once per section written', () => {
  const bad = [];
  [SHAPE_A, CP].forEach((src, si) => {
    const p = W.parse(src), defs = p.sections.filter(s => !s.ref);
    const wantChords = (src.match(/\[([^\]\s]{1,8})\]/g) || []).length + src.split('\n').filter(l => /^\s*\|/.test(l)).reduce((a, l) => a + l.split(/[|\s]+/).filter(x => x && W.isChord(x)).length, 0);
    const got = defs.reduce((a, s) => a + s.lines.reduce((b, l) => b + (l ? l.chords.length : 0), 0), 0);
    if (got !== wantChords) bad.push(['chords', si, got, wantChords]);
    const words = src.replace(/\{[^}]*\}/g, '').replace(/\[[^\]]*\]/g, '').replace(/\|[^\n]*/g, '').replace(/ - /g, '').split(/\s+/).filter(w => /[a-z]/i.test(w)).length;
    const gotW = defs.reduce((a, s) => a + s.lines.reduce((b, l) => b + (l ? l.text.split(/\s+/).filter(w => /[a-z]/i.test(w)).length : 0), 0), 0);
    if (gotW !== words) bad.push(['words', si, gotW, words]);
  });
  return !bad.length || bad;
});
console.log(R.map(r => (r[1].startsWith('PASS') ? 'PASS ' : 'FAIL ') + r[0] + (r[1].startsWith('PASS') ? '' : '  ' + r[1].slice(5, 300))).join('\n'));
const f = R.filter(r => !r[1].startsWith('PASS')).length; console.log(`\n${R.length - f}/${R.length} passed`); process.exit(f ? 1 : 0);

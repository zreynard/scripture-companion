// Made-up chord charts, one per format the app reads (no real song text). Shared by charts.js and import.js.
const F = {};
F.chordproFull = { src: `{title: Lantern Road}
{artist: Test Band}
{key: G}
{tempo: 72}

{comment: INTRO}
| G / / / | C / D / |

{start_of_verse: Verse 1}
[G]Walking down the [C]lantern road to[D]night
Carrying a [Em]borrowed li[C]ght
{end_of_verse}

{start_of_chorus: Chorus}
{comment: everyone in}
Sing it [C]softly, [G/B]sing it [D]slow[Em]
Every [Cadd9]step a [Dsus4]place to [G]go
{end_of_chorus}

{comment: TURNAROUND — 2 TIMES}
| Em7 / D/F# / | G / / / |

{start_of_verse: Verse 2}
Morning [G]comes a[C]cross the [D]field
{end_of_verse}

{comment: REPEAT CHORUS}

{start_of_bridge: Bridge}
[Am7]Home is [G/B]near, [C]home is [D]near
{end_of_bridge}

{comment: CHANNEL 1}
| C | C | G | D |

{start_of_chorus: Alternate Chorus}
Sing it [C]softly [Bb]sing it [F]slow
{end_of_chorus}

{comment: REPEAT BRIDGE X2}
{comment: FINAL TAG — 3 TIMES}
Every [Cadd9]step a [Dsus4]place to [G]go`,
  labels: ['Intro', 'Verse 1', 'Chorus', 'Turnaround x2', 'Verse 2', 'Chorus*', 'Bridge', 'Channel 1', 'Alternate Chorus', 'Bridge x2*', 'Final Tag x3'],
  meta: { title: 'Lantern Road', artist: 'Test Band', key: 'G' }, notes: 1 };
F.chordproShort = { src: `{t: Harbor Light}
{st: Test Band}
{key: D}
{sov}
[D]Over the [G]water the [A]harbor light
{eov}
{soc}
[Bm]Steady and [G]bright through the [D]night
{eoc}
{sov: Verse 2}
[D]Every [G]sailor a [A]lantern brings
{eov}
{chorus}
{c: Tag}
[G]Steady and [A]bright
{ci: softly}`,
  labels: ['Verse 1', 'Chorus', 'Verse 2', 'Chorus*', 'Tag'], meta: { title: 'Harbor Light', artist: 'Test Band', key: 'D' } };
F.chordsOverLyrics = { src: `Verse 1
G              C          D
Walking down the lantern road
Em             C
Carrying a borrowed light

Chorus
C        G/B      D    Em
Sing it softly, sing it slow
Cadd9    Dsus4    G
Every step a place to go

Verse 2
G           C
Morning comes across the field

Chorus

Bridge
Am7      G/B      C    D
Home is near, home is near

Tag (2x)
Cadd9    Dsus4    G
Every step a place to go`,
  labels: ['Verse 1', 'Chorus', 'Verse 2', 'Chorus*', 'Bridge', 'Tag x2'] };
F.bracketed = { src: `[Intro]
G C G/B C

[Verse 1]
G              C      G
Walking down a lantern road
C              G/B    Am7
Carrying a borrowed load

[Pre-Chorus]
                    D
Ooo ooo, the evening light

[Chorus]
G
Sing it softly
Em
Sing it slowly

[Verse 2]
G              C      G
Morning comes across the field

[Chorus]

[Hook]
G         D
Ooh, ooh, oh

[Outro]
G  C  G`,
  labels: ['Intro', 'Verse 1', 'Pre-Chorus', 'Chorus', 'Verse 2', 'Chorus*', 'Hook', 'Outro'] };
F.allCaps = { src: `INTRO
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

TAG X5
Ab Eb/G
Invented tag line`,
  labels: ['Intro', 'Verse 1', 'Chorus', 'Turnaround x2', 'Verse 2', 'Chorus*', 'Vamp 2 x3', 'Tag x5'] };
F.songSelectish = { src: `Morning Field
Test Band

Verse 1
     G                  C         G
The light comes over every hill
     Em              D
And the river bends again

Chorus 1
  C            G         D/F#   Em
So we raise a sound over all the ground
  C           D          G
And the morning comes again

Verse 2
     G                  C         G
The road is long and the night is still

(Repeat Chorus 1)

Bridge
Am7          G/B       C
Lift the lantern, lift it high
Am7          G/B       D
Lift the lantern, lift it high

Chorus 2
  C            G         D/F#   Em
So we raise a sound over all the ground

Ending
G  C/G  G`,
  labels: ['Verse 1', 'Verse 1', 'Chorus 1', 'Verse 2', 'Chorus 1*', 'Bridge', 'Chorus 2', 'Ending'], firstAuto: true };
F.windows = { src: 'Verse 1\r\nG\t\tC\r\nAn invented line with odd spaces\r\n\r\nChorus\r\nD  G\r\nAnother “quoted” line ’here’\r\n', labels: ['Verse 1', 'Chorus'] };
F.barsAndMarks = { src: `Intro
| G / / / | C / / / | (x2)
N.C.

Verse
G        D/F#      Em7      C
An invented line for the bars
(G)        D
Another one here

Interlude
| Em7 / D/F# / | G / / / |
x2`, labels: ['Intro', 'Verse', 'Interlude'] };

module.exports = F;

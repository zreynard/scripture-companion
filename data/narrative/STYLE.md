# The Bible Narrative: style guide

One narrator (Alistair) guides the listener through the whole Bible: 66 book introductions (about five
minutes each) and 1,189 chapter introductions (about one minute each). Each one plays first in its Journey
stop, before the overview teaching, the Scripture reading and the sermons.

Narrator = who, what, where, when, and how we got here.
Scripture = what God's Word says.
The teachers (Platt, Mitchell, Davey, Heitzig) = exposition, theology and application.

## The job

Orient the listener in the story, so that when the chapter is read they know who everyone is, where they
are, what has just happened and why this passage matters next. Like a superb historical documentary
narrator: informed, clear, warm, reverent, never preachy.

## Voice

- Natural, flowing, written for the ear. Mostly medium-length sentences; vary the rhythm.
- Historically informed and biblically accurate. Reverent without sermonising.
- Present the biblical narrative as the narrative: "Abram leaves Harran", not "the text claims".
- Plain words. A scholar's knowledge, a storyteller's delivery.

## Never

- Lists of themes, outlines read aloud, "five lessons from this chapter".
- Application, exhortation, devotional asides ("we too must..."), mini sermons.
- Forced links to Jesus in every chapter. Make a connection only where the Bible itself plainly makes it,
  or where the storyline genuinely runs on into the New Testament, and sparingly.
- Speculation presented as fact. If something is uncertain (authorship, a date, where Paul was imprisoned),
  say so in a short phrase, or leave it out.
- Long treatment of controversies.
- Rhetorical questions (one, very rarely, at most).
- Drama and hype: "shocking", "incredible", "little did they know", "buckle up".
- Formulaic AI phrasing: "In this chapter we", "Let's dive in", "a testament to", "tapestry", "journey"
  as a metaphor, "it's worth noting", "delve", "pivotal moment", "sets the stage", "unfolds" in every
  paragraph, triplets of adjectives.
- Retelling the whole chapter. Set it up; let Scripture tell it. Some anticipation is good ("before the
  day is over, ..."), a full plot summary is not.
- Repeating what the listener already heard. Assume they remember the book introduction and the previous
  chapters. Re-introduce a person only after a long absence, and then in a clause.

## Book introductions (about 5 minutes: 650 to 900 words; shorter for small books)

Answer, in flowing prose and in whatever order serves the book:
- Where are we? Period, setting, circumstances.
- Who are these people? Author where known (with honest uncertainty), audience, central figures.
- What has happened to bring us here? Preceding events, from earlier books or from history.
- Why this book? Epistles: the writer's circumstances and relationship with the readers. Histories: the
  events and people at the centre. Prophets: what was happening in Israel, Judah and the nations.
  Poetry and wisdom: the literary setting and shape, never an invented history.
- How does it unfold? A cohesive sense of the movement and turning points, not an outline.
- How does it fit the larger story? What came before, what follows. Canonical order is not chronological
  order; say so where it matters (a prophet who belongs inside the years of Kings, for example).

## Chapter introductions (about 1 minute: 110 to 190 words; 70 to 240 when the chapter calls for it)

Where are we now, what led here, what is about to happen.
- Narrative: connect to the previous chapter, place and people, set up the next development.
- Letters: where the argument has got to, what question or subject comes next.
- Psalms: the kind of psalm, its superscription and circumstances only where Scripture gives them, the tone
  and movement. Never invent an occasion.
- Prophets: the historical moment, the shift between messages, the people and nations. Consecutive
  chapters are not necessarily consecutive events.
- Wisdom: the movement of the discussion, the speakers. Do not force narrative where there is none.
- Genealogies and lists: say briefly why the list is here and what it is doing; keep it short.
Chapter 1 follows the book introduction directly: do not repeat it; take the listener into the opening.

## Written for listening (the text is read aloud exactly as written)

- Numbers and dates in words ("about four hundred years", "in the fifth century before Christ"). Avoid
  precise dates unless they matter; never "c." or "BC" abbreviations: write "before Christ".
- No headings, no bullet points, no parentheses, no brackets, no verse numbers, no citations. Refer to a
  place in the book by chapter only if needed ("back in chapter twelve").
- Paragraphs: separate with a blank line (the narrator pauses there). One to four paragraphs for a
  chapter; five to nine for a book.
- Spell names as the Berean Standard Bible does (the app's text): Abram, Sarai, Harran, Beersheba,
  Nebuchadnezzar, Artaxerxes. Avoid diacritics.
- Use plain ASCII punctuation plus curly or straight apostrophes; no em-dash chains. Commas and full
  stops carry the rhythm.

## Accuracy

- The biblical text (data/bible/<Book>.json, Berean Standard Bible) is the primary source. Read the chapter
  before writing its introduction.
- Background from reliable, mainstream reference knowledge (geography, empires, customs, chronology). All
  writing original: never copy or closely paraphrase a commentary or article.
- Check names, relationships, places, who is speaking, and what precedes and follows each chapter.
- Stay close to what the passage says when interpretation is needed for basic context.

## Data

data/narrative/<abbr>.txt (abbr as in canon.py: Gen, Exo, ... Rev), plain text, UTF-8:

    === intro
    The book introduction. Paragraphs separated by one blank line.

    === 1
    Chapter one's introduction.

    === 2
    ...every chapter, in order...

A long book may be split across files: <abbr>.txt holds the intro and the first chapters, <abbr>.2.txt the
rest (same format, no intro). Check a file with: python3 tools/narrative_check.py <abbr>

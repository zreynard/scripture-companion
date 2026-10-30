"""Canonical books, chapter counts, EPUB abbreviations, reference aliases."""
from __future__ import annotations

# (name, epub_abbr, chapters, testament, aliases)
BOOKS = [
 ("Genesis","Gen",50,"OT",["Genesis","Gen","Gn"]),
 ("Exodus","Exo",40,"OT",["Exodus","Exod","Ex"]),
 ("Leviticus","Lev",27,"OT",["Leviticus","Lev","Lv"]),
 ("Numbers","Num",36,"OT",["Numbers","Num","Nm","Nb"]),
 ("Deuteronomy","Deu",34,"OT",["Deuteronomy","Deut","Dt"]),
 ("Joshua","Jos",24,"OT",["Joshua","Josh","Jos"]),
 ("Judges","Jdg",21,"OT",["Judges","Judg","Jdg","Jgs"]),
 ("Ruth","Rut",4,"OT",["Ruth","Ru"]),
 ("1 Samuel","1Sa",31,"OT",["1 Samuel","1 Sam","1Sam","1Sa","I Samuel","First Samuel"]),
 ("2 Samuel","2Sa",24,"OT",["2 Samuel","2 Sam","2Sam","2Sa","II Samuel","Second Samuel"]),
 ("1 Kings","1Ki",22,"OT",["1 Kings","1 Kgs","1Kgs","1Ki","I Kings","First Kings"]),
 ("2 Kings","2Ki",25,"OT",["2 Kings","2 Kgs","2Kgs","2Ki","II Kings","Second Kings"]),
 ("1 Chronicles","1Ch",29,"OT",["1 Chronicles","1 Chron","1 Chr","1Chr","1Ch","I Chronicles","First Chronicles"]),
 ("2 Chronicles","2Ch",36,"OT",["2 Chronicles","2 Chron","2 Chr","2Chr","2Ch","II Chronicles","Second Chronicles"]),
 ("Ezra","Ezr",10,"OT",["Ezra","Ezr"]),
 ("Nehemiah","Neh",13,"OT",["Nehemiah","Neh"]),
 ("Esther","Est",10,"OT",["Esther","Esth","Est"]),
 ("Job","Job",42,"OT",["Job"]),
 ("Psalms","Psa",150,"OT",["Psalms","Psalm","Pss","Psa","Ps"]),
 ("Proverbs","Pro",31,"OT",["Proverbs","Prov","Prv","Pr"]),
 ("Ecclesiastes","Ecc",12,"OT",["Ecclesiastes","Eccles","Eccl","Ecc","Qoheleth"]),
 ("Song of Solomon","Sol",8,"OT",["Song of Solomon","Song of Songs","Canticles","Song","SoS","Sg"]),
 ("Isaiah","Isa",66,"OT",["Isaiah","Isa","Is"]),
 ("Jeremiah","Jer",52,"OT",["Jeremiah","Jer"]),
 ("Lamentations","Lam",5,"OT",["Lamentations","Lam"]),
 ("Ezekiel","Eze",48,"OT",["Ezekiel","Ezek","Ezk"]),
 ("Daniel","Dan",12,"OT",["Daniel","Dan","Dn"]),
 ("Hosea","Hos",14,"OT",["Hosea","Hos"]),
 ("Joel","Joe",3,"OT",["Joel","Jl"]),
 ("Amos","Amo",9,"OT",["Amos","Am"]),
 ("Obadiah","Oba",1,"OT",["Obadiah","Obad","Ob"]),
 ("Jonah","Jon",4,"OT",["Jonah","Jnh"]),
 ("Micah","Mic",7,"OT",["Micah","Mic"]),
 ("Nahum","Nah",3,"OT",["Nahum","Nah","Na"]),
 ("Habakkuk","Hab",3,"OT",["Habakkuk","Hab"]),
 ("Zephaniah","Zep",3,"OT",["Zephaniah","Zeph","Zep"]),
 ("Haggai","Hag",2,"OT",["Haggai","Hag"]),
 ("Zechariah","Zec",14,"OT",["Zechariah","Zech","Zec"]),
 ("Malachi","Mal",4,"OT",["Malachi","Mal"]),
 ("Matthew","Mat",28,"NT",["Matthew","Matt","Mt"]),
 ("Mark","Mar",16,"NT",["Mark","Mrk","Mk"]),
 ("Luke","Luk",24,"NT",["Luke","Lk"]),
 ("John","Joh",21,"NT",["John","Jhn","Jn"]),
 ("Acts","Act",28,"NT",["Acts","Ac"]),
 ("Romans","Rom",16,"NT",["Romans","Rom","Rm"]),
 ("1 Corinthians","1Co",16,"NT",["1 Corinthians","1 Cor","1Cor","1Co","I Corinthians","First Corinthians"]),
 ("2 Corinthians","2Co",13,"NT",["2 Corinthians","2 Cor","2Cor","2Co","II Corinthians","Second Corinthians"]),
 ("Galatians","Gal",6,"NT",["Galatians","Gal"]),
 ("Ephesians","Eph",6,"NT",["Ephesians","Eph"]),
 ("Philippians","Phi",4,"NT",["Philippians","Phil","Php"]),
 ("Colossians","Col",4,"NT",["Colossians","Col"]),
 ("1 Thessalonians","1Th",5,"NT",["1 Thessalonians","1 Thess","1Thess","1 Th","1Th","I Thessalonians","First Thessalonians"]),
 ("2 Thessalonians","2Th",3,"NT",["2 Thessalonians","2 Thess","2Thess","2 Th","2Th","II Thessalonians","Second Thessalonians"]),
 ("1 Timothy","1Ti",6,"NT",["1 Timothy","1 Tim","1Tim","1Ti","I Timothy","First Timothy"]),
 ("2 Timothy","2Ti",4,"NT",["2 Timothy","2 Tim","2Tim","2Ti","II Timothy","Second Timothy"]),
 ("Titus","Tit",3,"NT",["Titus","Tit"]),
 ("Philemon","Phm",1,"NT",["Philemon","Philem","Phlm","Phm"]),
 ("Hebrews","Heb",13,"NT",["Hebrews","Heb"]),
 ("James","Jam",5,"NT",["James","Jas"]),
 ("1 Peter","1Pe",5,"NT",["1 Peter","1 Pet","1Pet","1 Pt","1Pe","I Peter","First Peter"]),
 ("2 Peter","2Pe",3,"NT",["2 Peter","2 Pet","2Pet","2 Pt","2Pe","II Peter","Second Peter"]),
 ("1 John","1Jo",5,"NT",["1 John","1 Jn","1Jn","1Jo","I John","First John"]),
 ("2 John","2Jo",1,"NT",["2 John","2 Jn","2Jn","2Jo","II John","Second John"]),
 ("3 John","3Jo",1,"NT",["3 John","3 Jn","3Jn","3Jo","III John","Third John"]),
 ("Jude","Jud",1,"NT",["Jude"]),
 ("Revelation","Rev",22,"NT",["Revelation","Revelations","Apocalypse","Rev"]),
]

NAME_TO_INDEX = {b[0]: i for i, b in enumerate(BOOKS)}
ABBR_TO_NAME = {b[1]: b[0] for b in BOOKS}
CHAPTERS = {b[0]: b[2] for b in BOOKS}
TESTAMENT = {b[0]: b[3] for b in BOOKS}
TOTAL_CHAPTERS = sum(b[2] for b in BOOKS)
assert TOTAL_CHAPTERS == 1189, TOTAL_CHAPTERS

def canonical_chapters():
    """Yield (book_index, book_name, chapter) in canonical order."""
    for i, (name, _abbr, n, _t, _a) in enumerate(BOOKS):
        for c in range(1, n + 1):
            yield i, name, c

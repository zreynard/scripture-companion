"""Topics: what Scripture teaches about a subject, across books and teachers.

Each topic is reviewed by hand: a title pattern (a sermon must be *about* the subject by its title, not just
mention it), exclusions for the false hits found in review, the key passages, the Secret Church night on it,
and a few essential teachings picked by title. Recordings stay one item each; a topic only points at them.
"""
import re

# (id, name, blurb, key passages [(book, chapter, label, note)], title pattern, exclusions, Secret Church nights, essentials)
TOPICS = [
    ("kingdom", "Kingdom of God",
     "Jesus came announcing that the kingdom of God was at hand: God's rule breaking into the world in the King himself, growing quietly now and coming in full when he returns.",
     [("Mark", 1, "Mark 1:14–15", "The kingdom of God is at hand"),
      ("Matthew", 5, "Matthew 5–7", "The Sermon on the Mount: life in the kingdom"),
      ("Matthew", 13, "Matthew 13", "The parables of the kingdom"),
      ("Revelation", 21, "Revelation 21–22", "The kingdom come: all things made new")],
     r"\bkingdom\b", r"kingdom of me|kingmaker", [13],
     [r"^Parables of the Kingdom", r"^Consummation of the Kingdom", r"Kingdom Advancement", r"Pulling Back the Kingdom Curtain", r"KINGDOM GEMS \| Blessed Are They"]),
    ("prayer", "Prayer",
     "Prayer is talking with God as Father: praise, confession, asking and waiting. Scripture teaches it, models it, and promises that God hears.",
     [("Matthew", 6, "Matthew 6:5–15", "Jesus teaches the Lord's Prayer"),
      ("Luke", 11, "Luke 11:1–13", "Lord, teach us to pray"),
      ("John", 17, "John 17", "Jesus prays for his people"),
      ("Nehemiah", 1, "Nehemiah 1", "A leader on his knees"),
      ("Exodus", 32, "Exodus 32–33", "Moses intercedes for Israel")],
     r"\bpray|prayer", r"^Pray$", [19],
     [r"^The Astounding Privilege And Promises Of Prayer$", r"^Prayer: Our Wartime Walkie-Talkie$", r"^Prayer that Amazes Jesus$", r"^PRAY and FAST", r"^Relenting Wrath: The Role of Desperate Prayer in the Mystery of Divine Providence$"]),
    ("spirit", "The Holy Spirit",
     "The Spirit of God gives new birth, lives in every believer, makes us more like Christ, and gives gifts to build up the church and send it into the world.",
     [("John", 14, "John 14–16", "Jesus promises the Helper"),
      ("Acts", 2, "Acts 2", "The Spirit comes at Pentecost"),
      ("Romans", 8, "Romans 8", "Life in the Spirit"),
      ("Galatians", 5, "Galatians 5:16–26", "Walk by the Spirit; the fruit of the Spirit"),
      ("1 Corinthians", 12, "1 Corinthians 12", "Gifts of the Spirit for the body")],
     r"holy spirit|\bthe spirit\b|spirit[- ]filled|filled with the spirit|gifts? of the spirit|spiritual gifts|pentecost|\bspirit'?s\b", r"sword of the spirit", [5],
     [r"^5\.1 ", r"^5\.3 ", r"^Introducing \. \. \. The Holy Spirit", r"^5\.9 ", r"^One Power: The Holy Spirit"]),
    ("marriage", "Marriage & Family",
     "God designed marriage as one man and one woman for life, a picture of Christ and the church, and gave the family as the first place faith is taught.",
     [("Genesis", 2, "Genesis 2:18–25", "The creation of woman and marriage"),
      ("Deuteronomy", 6, "Deuteronomy 6:4–9", "Teach them diligently to your children"),
      ("1 Corinthians", 7, "1 Corinthians 7", "Marriage and singleness"),
      ("Ephesians", 5, "Ephesians 5:21–6:4", "Marriage and Christ's love for the church"),
      ("Colossians", 3, "Colossians 3:18–21", "Husbands, wives, children, parents")],
     r"marriage|married|husbands?|wives|\bwife\b|parent|children|famil|singleness|sexual", r"church family|family of god|a family that|special needs|unborn|culture of death|little children|next generation|children of the night|family tree|true family|new marriage", [11],
     [r"^God.s Good Design for Marriage and Singleness . Part 1$", r"^God.s Good Design for Marriage and Singleness - Part 2$", r"^The Difference Jesus Makes in Marriage$", r"^The Difference Jesus Makes in Children and Parents$", r"^Beauty in Both Singleness and Marriage$", r"^A Parent's Bill of Rights"]),
    ("manhood", "Manhood",
     "God calls men to be strong and gentle: to know him, love their wives as Christ loved the church, bring up their children in the Lord, and lead by serving.",
     [("Genesis", 2, "Genesis 2:15–24", "Called to work, keep and love"),
      ("Joshua", 24, "Joshua 24:14–15", "As for me and my house"),
      ("1 Corinthians", 16, "1 Corinthians 16:13–14", "Act like men; let all be done in love"),
      ("Ephesians", 5, "Ephesians 5:25–6:4", "Love your wife; bring up your children in the Lord"),
      ("1 Timothy", 3, "1 Timothy 3:1–7", "He must manage his own household well"),
      ("Titus", 2, "Titus 2:1–8", "Older men and younger men")],
     r"\bmanhood|masculin|young men|old men|men and women|servant leader|leadership|when leaders fall|shepherd the flock", "", [],
     []),
    ("disciple", "Discipleship",
     "A disciple follows Jesus: hears his call, trusts him, obeys him, and helps others follow him too. It costs everything, and it is worth it.",
     [("Matthew", 4, "Matthew 4:18–22", "Follow me, and I will make you fishers of men"),
      ("Mark", 8, "Mark 8:31–38", "Take up your cross"),
      ("Luke", 14, "Luke 14:25–35", "Count the cost"),
      ("Matthew", 28, "Matthew 28:16–20", "Go and make disciples")],
     r"disciple|follow me|follow(ing)? jesus|cost of following|take up (his|your) cross", r"secret disciple|cost of spiritual carelessness", [14],
     [r"^Two Simple Words: Follow Me$", r"^Two Simple Words: Make Disciples$", r"^Realizing What It Really Means to Follow Jesus$", r"^Mission Precision: Defining Disciple$", r"^You Need Biblical Discipleship$"]),
    ("holiness", "Holiness",
     "God is holy, and he calls his people to be holy as he is: set apart from sin and to him, made clean by Christ and growing in purity by his Spirit.",
     [("Isaiah", 6, "Isaiah 6", "Holy, holy, holy is the Lord"),
      ("Leviticus", 19, "Leviticus 19", "You shall be holy, for I am holy"),
      ("Romans", 6, "Romans 6", "Dead to sin, alive to God"),
      ("1 Peter", 1, "1 Peter 1:13–25", "Be holy in all your conduct")],
     r"\bholy\b(?! spirit| week| night)|holiness|purity|\bpure\b|sanctif|\bsin\b|temptation", r"blasphemy|unrepentant|holy day or holiday", [14],
     [r"^Holy Preoccupation", r"^The Cross and Christian Sanctification$", r"^10\.7 ", r"^Triumph Through Temptation$", r"^The Danger of Hidden Sin$"]),
    ("repent", "Repentance",
     "Repentance is turning from sin to God: agreeing with him about our sin, grieving it, and coming back to him in faith. It is the shape of the whole Christian life, and God runs to meet every sinner who returns.",
     [("Psalms", 51, "Psalm 51", "Create in me a clean heart, O God"),
      ("Luke", 15, "Luke 15", "The lost sheep, the lost coin, the lost son"),
      ("Jonah", 3, "Jonah 3", "Nineveh turns from its evil way"),
      ("Acts", 2, "Acts 2:37–41", "Repent and be baptized"),
      ("2 Corinthians", 7, "2 Corinthians 7:8–11", "Godly grief produces repentance"),
      ("1 John", 1, "1 John 1:5–10", "If we confess our sins, he is faithful to forgive")],
     r"repent|returning to god|confession of man|telling the truth to god|^true confession$|^see jonah preach$|^the king is here \| prepare the way$|^acts i & ii \| on this day$",
     r"unrepentant", [],
     [r"Repenting Of Sin And Returning To God$", r"^The Confession of Man and the Compassion of God$", r"^Evidence of Repentance$", r"^Telling The Truth To God$", r"^Repentance and Resolutions$"]),
    ("faith", "Faith & Trust",
     "Faith is trusting God and taking him at his word, even when we cannot see the way. It rests on his character and shows itself in obedience.",
     [("Hebrews", 11, "Hebrews 11", "By faith: the great cloud of witnesses"),
      ("Genesis", 15, "Genesis 15", "Abraham believed God"),
      ("Psalms", 56, "Psalm 56", "When I am afraid, I put my trust in you"),
      ("James", 2, "James 2:14–26", "Faith that works")],
     r"\bfaith\b|\btrust|believ|anxiety|anxious|\bfear\b", r"trust (the|the) bible|trust the bible|sharing your faith|faith and freedom|statement of faith|ticket of faith|for moms|holy fear|fear god, not", [],
     [r"^Faith from the Unlikely", r"^From Fear to Faith$", r"^Chapter 1: Believing in God$", r"^The Beauty of Faith that Works$", r"^Jesus and Anxiety$"]),
    ("grace", "Salvation & Grace",
     "We are saved by grace through faith in Christ alone: sinners made right with God because Jesus died in our place and rose again.",
     [("John", 3, "John 3", "You must be born again"),
      ("Romans", 3, "Romans 3:21–26", "Justified freely by his grace"),
      ("Romans", 5, "Romans 5", "Peace with God"),
      ("Ephesians", 2, "Ephesians 2:1–10", "By grace you have been saved")],
     r"\bgrace\b|salvation|saved|justif|redemption|born again|forgive|the gospel:|^gospel|recovering the gospel|introducing the gospel|gripped by the gospel",
     r"for the giver|materialism|manhood|womanhood|homosexuality|singleness|parents|divorce|marriage|religious liberty|sports|baptism", [10, 6],
     [r"^The Gospel: What We Believe$", r"^The Gospel: What We Need$", r"^10\.5 ", r"^Governed by Grace", r"^Forgiven \. \. \. Forgotten$"]),
    ("suffering", "Suffering",
     "Scripture never hides from pain. God is sovereign over suffering, present in it, and uses it for our good, and Christ suffered first and will wipe every tear away.",
     [("Job", 1, "Job 1–2", "The Lord gave, and the Lord has taken away"),
      ("Genesis", 50, "Genesis 50:20", "You meant evil; God meant it for good"),
      ("Romans", 8, "Romans 8:18–39", "Present sufferings and future glory"),
      ("2 Corinthians", 4, "2 Corinthians 4", "Treasure in jars of clay"),
      ("1 Peter", 4, "1 Peter 4:12–19", "Do not be surprised at the fiery trial")],
     r"suffer|\bpain|grief|griev|\btrials\b|in the middle of trials|affliction|persecut|sorrow", r"suffering king|death of christ", [12],
     [r"^Our Suffering and God.s Sovereignty: The Life of Joseph$", r"^Our Suffering and God's Sovereignty: The Life of Job$", r"^The Plan of God in the Suffering We Experience$", r"^Sin, Suffering, and the Sovereignty of God$", r"^Pain$"]),
    ("enemy", "The Enemy",
     "Scripture is honest that we have a real enemy: Satan, who lies, accuses and tempts. But Christ has already crushed him at the cross, and in Christ we stand firm in the armor of God.",
     [("Genesis", 3, "Genesis 3", "The serpent, the fall, and the promise that he will be crushed"),
      ("Job", 1, "Job 1–2", "Satan can go no further than God allows"),
      ("Matthew", 4, "Matthew 4:1–11", "Jesus is tempted and answers with the Word"),
      ("Ephesians", 6, "Ephesians 6:10–20", "Put on the whole armor of God"),
      ("1 Peter", 5, "1 Peter 5:8–11", "Your adversary prowls; resist him, firm in faith"),
      ("Revelation", 12, "Revelation 12", "The dragon is thrown down")],
     r"satan|devil|\bdemons?\b|spiritual (warfare|battle)|fight in the dark|fighting from|belt of truth|sword of the spirit|armou?r of god|\btempter\b|crushing of the serpent|\bthe enemy\b",
     r"\| how to fight in the dark", [7],
     [r"^Six Foundations for Spiritual Battle", r"^He Came To Destroy The Devil$", r"^Dealing with the Devil", r"^Fighting from \(not for\) Victory$", r"Overcoming The Tempter"]),
    ("church", "Church & Worship",
     "The church is God's family and Christ's body, gathered to worship, hear the Word, pray, love one another and be sent out with the gospel.",
     [("Acts", 2, "Acts 2:42–47", "Devoted to teaching, fellowship, the breaking of bread and prayer"),
      ("Ephesians", 4, "Ephesians 4", "One body, built up in love"),
      ("1 Corinthians", 12, "1 Corinthians 12", "Many members, one body"),
      ("Hebrews", 10, "Hebrews 10:19–25", "Do not neglect meeting together"),
      ("John", 4, "John 4:1–26", "Worship in spirit and truth")],
     r"\bchurch\b|worship|community|body of christ|fellowship", r"secret church|brook hills|mclean bible|sbc|commissioning", [9],
     [r"^Biblical Church$", r"^12 Traits of a Biblical Church: Worship$", r"^What Makes the Body of Christ Beautiful$", r"^Members of a New Community$", r"^God-Centered Worship$"]),
    ("missions", "Missions",
     "God's glory among all nations runs from Genesis to Revelation. Jesus sends his church to make disciples of every people, especially those who have never heard.",
     [("Psalms", 67, "Psalm 67", "Let all the peoples praise you"),
      ("Matthew", 28, "Matthew 28:16–20", "The Great Commission"),
      ("Acts", 1, "Acts 1:8", "My witnesses to the end of the earth"),
      ("Romans", 10, "Romans 10:14–17", "How will they hear?"),
      ("Revelation", 7, "Revelation 7:9–12", "Every nation, tribe, people and language")],
     r"mission|nations|unreached|great commission|evangel", r"mission trip|cross to commission|sbc missions|state of missions|commissioning", [16, 21],
     [r"^Our Obligation to the Unreached – Part 1$", r"^Unreached People: Not a Missions Problem$", r"^The Song of Heaven and the Sound of All Nations$", r"^Why the Great Commission is Great$", r"^Divine Sovereignty: The Fuel of Death-Defying Missions$"]),
]

# Sections inside a topic: (label, short label for the switch, title pattern, exclusions). A section takes from every sermon in the app, not only
# the topic's own title matches, so one sermon can sit in two topics (a father's sermon in Marriage & Family and Manhood).
SECTIONS = {
    "marriage": [
        ("Marriage", "Marriage", r"marriage|married|husbands?|wives|\bwife\b", r"^beauty in both singleness|new marriage|sexual"),
        ("Parenting & Fatherhood", "Parenting", r"parent|children and parents|father-son|fatherhood|raising (children|kids)", r"orphan|fatherhood of god"),
        ("Singleness", "Singleness", r"singleness|\bsingle\b", r""),
    ],
    "manhood": [
        ("A Man of God", "Man of God", r"\bmanhood|masculin|young men|old men|men and women", r""),
        ("Leading Your Home", "Home", r"^(attachment: )?the gospel and (marriage|parents)$|^the difference jesus makes in (marriage|children and parents)|father-son|^a parent's bill of rights|^god's design for marriage", r""),
        ("Leading Others", "Leading", r"servant leader|leadership|when leaders fall|shepherd the flock", r""),
    ],
}
TEACHER_ORDER = {"Platt": 0, "PAM": 1, "Davey": 2, "Skip": 3, "Vaughan": 4, "Fearless": 5}
_SPEAKER = re.compile(r"\s*\|\s*(David Platt|Philip Anthony Mitchell|[A-Z][a-z]+ [A-Z][a-z]+|Elder [A-Z][a-z]+ [A-Z][a-z]+)\s*(\||$)")


def _title(t):
    """The words of a title that say what it is about: no "(Romans 6:14)" or "| Speaker | Passage" tails."""
    t = re.sub(r"\s*\([^)]*\d[^)]*\)\s*", " ", t or "")
    segs = [s.strip() for s in t.split("|")]
    if len(segs) > 2:  # 2819: "SERIES | Name | Passage | Speaker" -> "SERIES | Name"
        segs = segs[:2]
    elif len(segs) == 2 and re.search(r"David Platt|^[A-Z][a-z]+ [A-Z][a-z]+$|Image Of|Kingmaker|Let Down|How To Fight|Here As It Is", segs[1]):
        segs = segs[:1]
    return " | ".join(segs).strip()


def _key(t):
    return re.sub(r"[^a-z0-9]+", " ", _title(t).lower().replace("’", "'")).strip()


def _to(ref, c):
    """The last chapter a key passage reaches: "Matthew 5–7" -> 7, "Ephesians 5:21–6:4" -> 6, "Romans 8:18–39" -> 8."""
    m = re.search(r"–(\d+):", ref) or (None if ":" in ref else re.search(r"–(\d+)$", ref))
    return int(m.group(1)) if m else c


def build(items, chapters, on_road):
    """items: the app's items; chapters: {id: {book: set(chapters)}}; on_road: ids that sit on the Journey road."""
    out = []
    for tid, name, blurb, keys, rx, nx, nights, ess in TOPICS:
        R, N = re.compile(rx, re.I), re.compile(nx, re.I) if nx else None
        best = {}
        for i in items.values():
            if i["tr"] == "devotional" or not i.get("audio"):
                continue
            t = _title(i["t"])
            if not R.search(t) or (N and N.search(t)) or re.match(r"^\s*Secret Church\b", t):
                continue
            k = (i["who"], _key(i["t"]))
            have = best.get(k)
            rank = (i["id"] in on_road, bool(i.get("dur")), i.get("date") or "")
            if not have or rank > have[0]:
                best[k] = (rank, i["id"])
        ids = [v[1] for v in best.values()]
        essential = []
        for pat in ess:
            P = re.compile(pat, re.I)
            hit = sorted((x for x in ids if P.search(_title(items[x]["t"])) and x not in essential),
                         key=lambda x: (x not in on_road, items[x].get("date") or ""), reverse=False)
            if hit:
                essential.append(hit[0])
        # with sections, the essentials lead their own section instead of a list of their own
        secs = SECTIONS.get(tid, [])
        bks, taken = [], set() if secs else set(essential)
        def same(x):   # one sermon, whatever feed it came through: "(Part 2)" stays, "(Titus 2:6-8)" and a series prefix go
            t = re.sub(r"\s*\([^)]*\d:\d[^)]*\)", "", items[x]["t"]).split("|")[0]
            return (items[x]["who"], re.sub(r"^attachment ", "", re.sub(r"[^a-z0-9]+", " ", t.lower().replace("’", "'")).strip()))
        whole = lambda k: (k[0], re.sub(r" (part|pt) ?\d+[ab]?$", "", k[1]))
        for label, short, pat, ex in secs:
            P, X = re.compile(pat, re.I), re.compile(ex, re.I) if ex else None
            pick = {}
            for i in items.values():
                if i["tr"] == "devotional" or not i.get("audio") or i["id"] in taken or (i.get("sc") and i["sc"][0] in nights):
                    continue
                t = _title(i["t"])
                if not P.search(t) or (X and X.search(t)) or re.match(r"^\s*Secret Church\b", t) or same(i["id"]) in {same(x) for x in taken}:
                    continue
                k, rank = same(i["id"]), (i["id"] in on_road, bool(i.get("dur")), i.get("date") or "")
                if k not in pick or rank > pick[k][0]:
                    pick[k] = (rank, i["id"])
            # a radio show's "Part 1"/"Part 2" of a sermon the archive also has whole: the whole one only
            got = [v[1] for k, v in pick.items() if not (whole(k) != k and whole(k) in pick)]
            got.sort(key=lambda x: (x not in essential, essential.index(x) if x in essential else 0, TEACHER_ORDER.get(items[x]["who"], 9), _key(items[x]["t"]), items[x]["t"]))
            if got:
                bks.append({"label": label, "short": short, "ids": got}); taken |= set(got)
        if secs:
            essential = [x for x in essential if x not in taken]
            gone = {same(y) for y in taken} | {whole(same(y)) for y in taken}
            ids = [x for x in ids if x not in taken and same(x) not in gone and whole(same(x)) not in gone]
        more = sorted((x for x in ids if x not in essential and not (items[x].get("sc") and items[x]["sc"][0] in nights)),
                      key=lambda x: (TEACHER_ORDER.get(items[x]["who"], 9), _key(items[x]["t"])))
        out.append({"id": tid, "name": name, "blurb": blurb,
                    "keys": [{"b": b, "c": c, "to": _to(ref, c), "ref": ref, "note": note} for b, c, ref, note in keys],
                    "sc": nights, "ess": essential, "more": more, **({"bks": bks} if bks else {})})
    return out

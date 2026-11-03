"""Publisher catalogs. Every URL here was located from the publishers' own pages/feeds.
Nothing is a search page. Add sources here, never ad-hoc URLs in the ledger."""

# ---- David Platt ----
PTW_FEED = "https://feeds.buzzsprout.com/112848.rss"            # Pray the Word (Buzzsprout 112848, 3,000+ episodes)
PLATT_MESSAGES_FEED = "https://feeds.buzzsprout.com/107460.rss" # David Platt Messages (Buzzsprout 107460, ~490 sermons)
RADICAL_BASE = "https://radical.net"
RADICAL_SCRIPTURE_INDEX = "https://radical.net/scriptures/"      # per-book pages: https://radical.net/scripture/<book-slug>
RADICAL_SITEMAP_CANDIDATES = [
    "https://radical.net/sitemap_index.xml",      # Yoast
    "https://radical.net/wp-sitemap.xml",         # WP core
    "https://radical.net/sitemap.xml",
]
RADICAL_REST_TYPES = "https://radical.net/wp-json/wp/v2/types"  # discover custom post types (message, secret_church, podcast...)
RADICAL_PATH_PREFIXES = ("/message/", "/podcasts/radical-podcast/", "/podcasts/pray-the-word/",
                         "/secret_church/", "/series/", "/video/")
SECRET_CHURCH_PAGES = [  # from https://radical.net/scriptures/ footer menu, 2026-10-29
    "https://radical.net/secret_church/elijah/",
    "https://radical.net/secret_church/matthew/",
    "https://radical.net/secret_church/ruth/",
    "https://radical.net/secret_church/jonah/",
    "https://radical.net/secret_church/22-who-am-i/",
    "https://radical.net/secret_church/secret-church-21-the-great-imbalance/",
    "https://radical.net/secret_church/secret-church-20-god-government-and-the-gospel/",
    "https://radical.net/secret_church/secret-church-19-prayer-fasting-and-the-pursuit-of-god/",
    "https://radical.net/secret_church/secret-church-18-cults-and-counterfeit-gospels/",
    "https://radical.net/secret_church/secret-church-17-scripture-and-authority-in-an-age-of-skepticism/",
    "https://radical.net/secret_church/secret-church-16-a-global-gospel-in-a-world-of-religions/",
    "https://radical.net/secret_church/secret-church-15-christ-culture-and-a-call-to-action/",
    "https://radical.net/secret_church/secret-church-14-the-cross-and-everyday-life/",
    "https://radical.net/secret_church/secret-church-13-heaven-hell-and-the-end-of-the-world/",
    "https://radical.net/secret_church/secret-church-12-the-cross-and-suffering/",
    "https://radical.net/secret_church/secret-church-11-family-marriage-sex-and-the-gospel/",
    "https://radical.net/secret_church/secret-church-10-crucifixion-salvation-and-the-glory-of-god/",
    "https://radical.net/secret_church/secret-church-9-the-body-of-christ/",
    "https://radical.net/secret_church/secret-church-8-the-gospel-possessions-and-prosperity/",
    "https://radical.net/secret_church/secret-church-7-angels-demons-and-spiritual-warfare/",
    "https://radical.net/secret_church/secret-church-6-the-cross-of-christ/",
    "https://radical.net/secret_church/secret-church-5-exploring-the-holy-spirit/",
    "https://radical.net/secret_church/secret-church-4-who-is-god/",
    "https://radical.net/secret_church/secret-church-3-how-to-study-the-bible/",
    "https://radical.net/secret_church/secret-church-2-survey-of-the-new-testament/",
    "https://radical.net/secret_church/secret-church-1-survey-of-the-old-testament/",
]
# iTunes Search resolves official podcast feeds without guessing URLs
ITUNES_SEARCH = "https://itunes.apple.com/search?media=podcast&limit=25&term="
ITUNES_LOOKUP = "https://itunes.apple.com/lookup?id="
PODCAST_SEARCH_TERMS = {
    "mclean": "McLean Bible Church",          # Platt's church; Sunday sermons (mixed speakers)
    "2819": "2819 Church",                    # PAM's church podcast (Spotify for Creators)
    "victory": "Victory World Church",        # PAM's pre-2019 church (gap-fill)
    "pam": "Philip Anthony Mitchell",
    "secret_church": "Secret Church",       # Radical's Secret Church podcast: ~198 episodes numbered "N.M – Title" (event N, session M); confirmed 2026-10-30
}

# ---- Philip Anthony Mitchell ----
YOUTUBE_CHANNELS = {
    # key: (url, era, speaker_default)
    "2819": ("https://www.youtube.com/@2819Church/videos", "2819", None),              # speaker from title
    "pam":  ("https://www.youtube.com/@PhilipAnthonyMitchell/videos", "pam-channel", "PAM"),  # confirm handle on first run
    "victory": ("https://www.youtube.com/@VictoryWorldChurch/videos", "victory", None), # confirm handle on first run
    "radical": ("https://www.youtube.com/channel/UCTP7mGxH9LFTaMO2Kw9nZ7g/videos", "platt", "Platt"),  # Radical: Secret Church sessions, Platt sermons (confirmed 2026-10-30)
}
PAM_NAME_RE = r"philip\s+anthony\s+mitchell|pastor\s+pam\b|\bPAM\b"

# ---- behaviour ----
REQUEST_SLEEP = 0.4       # seconds between page fetches (be polite)
VERIFY_TTL_DAYS = 30      # re-verify links older than this
TITLE_MATCH_MIN = 0.72    # fuzzy ratio for fetched-title vs claimed-title

# Secret Church events in order (titles/URLs from radical.net's own menu). Sessions are filled per event
# from Radical's YouTube channel ("Secret Church N – Session M: ...") by the harvester; scope = books covered.
SECRET_CHURCH_EVENTS = [
 (1,"Survey of the Old Testament","https://radical.net/secret_church/secret-church-1-survey-of-the-old-testament/","OT"),
 (2,"Survey of the New Testament","https://radical.net/secret_church/secret-church-2-survey-of-the-new-testament/","NT"),
 (3,"How to Study the Bible","https://radical.net/secret_church/secret-church-3-how-to-study-the-bible/","topical"),
 (4,"Who Is God?","https://radical.net/secret_church/secret-church-4-who-is-god/","topical"),
 (5,"Exploring the Holy Spirit","https://radical.net/secret_church/secret-church-5-exploring-the-holy-spirit/","topical"),
 (6,"The Cross of Christ","https://radical.net/secret_church/secret-church-6-the-cross-of-christ/","topical"),
 (7,"Angels, Demons, and Spiritual Warfare","https://radical.net/secret_church/secret-church-7-angels-demons-and-spiritual-warfare/","topical"),
 (8,"The Gospel, Possessions, and Prosperity","https://radical.net/secret_church/secret-church-8-the-gospel-possessions-and-prosperity/","topical"),
 (9,"The Body of Christ","https://radical.net/secret_church/secret-church-9-the-body-of-christ/","topical"),
 (10,"Crucifixion, Salvation, and the Glory of God","https://radical.net/secret_church/secret-church-10-crucifixion-salvation-and-the-glory-of-god/","topical"),
 (11,"Family, Marriage, Sex, and the Gospel","https://radical.net/secret_church/secret-church-11-family-marriage-sex-and-the-gospel/","topical"),
 (12,"The Cross and Suffering","https://radical.net/secret_church/secret-church-12-the-cross-and-suffering/","topical"),
 (13,"Heaven, Hell, and the End of the World","https://radical.net/secret_church/secret-church-13-heaven-hell-and-the-end-of-the-world/","topical"),
 (14,"The Cross and Everyday Life","https://radical.net/secret_church/secret-church-14-the-cross-and-everyday-life/","topical"),
 (15,"Christ, Culture, and a Call to Action","https://radical.net/secret_church/secret-church-15-christ-culture-and-a-call-to-action/","topical"),
 (16,"A Global Gospel in a World of Religions","https://radical.net/secret_church/secret-church-16-a-global-gospel-in-a-world-of-religions/","topical"),
 (17,"Scripture and Authority in an Age of Skepticism","https://radical.net/secret_church/secret-church-17-scripture-and-authority-in-an-age-of-skepticism/","topical"),
 (18,"Cults and Counterfeit Gospels","https://radical.net/secret_church/secret-church-18-cults-and-counterfeit-gospels/","topical"),
 (19,"Prayer, Fasting, and the Pursuit of God","https://radical.net/secret_church/secret-church-19-prayer-fasting-and-the-pursuit-of-god/","topical"),
 (20,"God, Government, and the Gospel","https://radical.net/secret_church/secret-church-20-god-government-and-the-gospel/","topical"),
 (21,"The Great Imbalance","https://radical.net/secret_church/secret-church-21-the-great-imbalance/","topical"),
 (22,"Who Am I?","https://radical.net/secret_church/22-who-am-i/","topical"),
 (23,"The Book of Jonah","https://radical.net/secret_church/jonah/","Jonah"),
 (24,"The Book of Ruth","https://radical.net/secret_church/ruth/","Ruth"),
 (25,"The Gospel of Matthew","https://radical.net/secret_church/matthew/","Matthew"),
 (26,"Elijah (1 Kings 17–2 Kings 2)","https://radical.net/secret_church/elijah/","1 Kings 17–2 Kings 2"),
]


# ---- what belongs on the road (app_build.py) ----
# The road is teaching that works through the passage. These titles mark one-off topical or occasional
# messages; they stay on the road only inside a series through that book.
TOPICAL_TITLE_RE = (r"\bwom[ae]n|womanhood|manhood|\bmoms?\b|mother|ladies|election|conference|\bgather \d|"
                    r"baptism|membership|\belders?\b|deacons?|christmas|thanksgiving|new year|generosity|giving|\bmoney\b|"
                    r"abortion|justice|racializ|sexuality|special needs|\bvision\b|south by southwest|panel|q ?& ?a|interview")
# Never on the road, series or not.
# (narratives about women in Scripture - the woman at the well, the women at the tomb - stay on the road)
NEVER_ON_ROAD_RE = (r"womanhood|\bmoms?\b|mother'?s day|\bladies\b|godly wom[ae]n|married wom[ae]n|rare wom[ae]n|"
                    r"wom[ae]n who (?:fear|are)|wom[ae]n in the church|men and women|word of god to women|about women|"
                    r"\bfor women\b|\bwomen'?s\b|legacies of light")

# 2819 Church preachers who teach inside PAM's series; they ride the road with PAM's voices, under their own name.
PAM_CHURCH_PREACHERS = ["Arik Hayes", "Milton James", "Lonnell Williams", "Kenneth McFarland", "Brandon Freeman", "Marquavious Walker",
                        "Courtney McClendon", "Tyonna Lewis"]

# ---- Stephen Davey (Wisdom for the Heart / The Shepherd's Church) ----
# Every feed he publishes on Buzzsprout (wisdomonline.org itself sits behind a bot check and is not crawled).
DAVEY_FEEDS = {
    "davey_sermons": (2353448, "https://rss.buzzsprout.com/2353448.rss"),   # Stephen Davey Sermons (full Sunday sermons)
    "davey_wfth": (2545810, "https://rss.buzzsprout.com/2545810.rss"),      # Wisdom for the Heart (sermons broadcast in parts)
    "davey_journey": (2545807, "https://rss.buzzsprout.com/2545807.rss"),   # The Wisdom Journey (daily walk through the Bible)
}
# Secret Church podcast sessions that teach a stretch of books or a passage, though their titles do not say so
# (from each session's own description). (event, session) -> whole books, or a passage
SC_BOOKS = {
    (2, 4): ["1 Corinthians", "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians"],
    (2, 5): ["1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James", "1 Peter"],
    (2, 6): ["2 Peter", "1 John", "2 John", "3 John", "Jude", "Revelation"],
    (2, 7): ["Matthew", "Mark", "Luke", "John"], (2, 8): ["Matthew", "Mark", "Luke", "John"], (2, 9): ["Matthew", "Mark", "Luke", "John"],
    (2, 10): ["Acts", "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians", "1 Thessalonians",
              "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John",
              "3 John", "Jude", "Revelation"],
}
SC_BOOKS[(2, 11)] = SC_BOOKS[(2, 10)]
SC_PASSAGES = {
    (6, 5): "Matthew 26:17-30; Mark 14:12-26; Luke 22:7-23",     # The Last Supper
    (6, 6): "Matthew 26:36-46; Mark 14:32-42; Luke 22:39-46",    # The Garden of Gethsemane
    (6, 7): "Matthew 27:45-46; Mark 15:33-34; Psalm 22:1",       # The Cry of Dereliction
    (6, 8): "John 19:28-30",                                     # The Declaration of Triumph
}

# Every other Secret Church session sits at the passage it is most anchored in (read from each session's title and
# description): the text the teaching turns on, or the classic passage for its topic.
SC_PASSAGES.update({
    # 3 How to Study the Bible
    (3, 1): "2 Timothy 3:14-17", (3, 2): "2 Timothy 2:15", (3, 3): "Nehemiah 8:1-8", (3, 4): "Psalm 119:17-24",
    (3, 5): "Acts 8:26-35", (3, 6): "Luke 24:25-27", (3, 7): "James 1:22-25", (3, 8): "Matthew 13:1-23",
    (3, 9): "Romans 15:4-6", (3, 10): "Psalm 1:1-6",
    # 4 Who Is God?
    (4, 1): "Jeremiah 9:23-24", (4, 2): "1 John 2:3-6", (4, 3): "Exodus 3:13-15", (4, 4): "Genesis 17:1-2",
    (4, 5): "Isaiah 40:12-31", (4, 6): "Psalm 90:1-2", (4, 7): "Psalm 139:1-12", (4, 8): "Exodus 34:6-7",
    (4, 9): "Matthew 3:16-17", (4, 10): "Isaiah 46:8-11", (4, 11): "Genesis 50:15-21",
    # 5 Exploring the Holy Spirit
    (5, 1): "John 14:15-26", (5, 2): "John 3:5-8", (5, 3): "John 16:7-15", (5, 5): "Acts 2:1-21",
    (5, 6): "1 Corinthians 12:4-13", (5, 7): "Romans 8:12-17", (5, 8): "Matthew 12:22-32", (5, 9): "Ephesians 5:18-21",
    (5, 10): "Acts 1:8",
    # 6 The Cross of Christ
    (6, 1): "1 Corinthians 1:18-25", (6, 2): "Isaiah 52:13-53:12", (6, 3): "Romans 3:21-26", (6, 4): "2 Corinthians 5:21",
    (6, 9): "John 10:11-18", (6, 10): "Galatians 6:14",
    # 7 Angels, Demons, and Spiritual Warfare
    (7, 1): "Ephesians 6:10-12", (7, 2): "Hebrews 1:4-14", (7, 3): "Revelation 12:7-12", (7, 5): "Colossians 2:13-15",
    (7, 6): "Matthew 16:13-20", (7, 7): "Ephesians 6:13-17", (7, 8): "James 4:7-10", (7, 9): "Mark 5:1-20",
    (7, 10): "Romans 16:20",
    # 8 The Gospel, Possessions, and Prosperity
    (8, 1): "Luke 16:10-15", (8, 2): "2 Corinthians 8:9", (8, 3): "Deuteronomy 8:11-18", (8, 4): "Proverbs 30:7-9",
    (8, 5): "Matthew 6:19-24", (8, 6): "Mark 10:17-31", (8, 7): "Acts 4:32-37", (8, 8): "1 Timothy 6:17-19",
    (8, 9): "Matthew 13:44-46", (8, 10): "James 5:1-6",
    # 9 The Body of Christ
    (9, 1): "Ephesians 5:25-27", (9, 2): "1 Peter 2:4-10", (9, 3): "Ephesians 2:19-22", (9, 4): "Matthew 28:18-20",
    (9, 5): "2 Timothy 2:1-2", (9, 6): "Hebrews 10:23-25", (9, 7): "Colossians 3:16-17", (9, 8): "Acts 2:42-47",
    (9, 9): "1 Peter 5:1-4",
    # 10 Crucifixion, Salvation, and the Glory of God
    (10, 1): "Titus 3:3-7", (10, 2): "Mark 15:21-39", (10, 3): "Ephesians 2:1-10", (10, 4): "Mark 1:14-15",
    (10, 5): "Romans 4:1-8", (10, 6): "Galatians 4:4-7", (10, 7): "Romans 6:1-14", (10, 8): "Romans 8:28-39",
    (10, 9): "Ephesians 1:3-14", (10, 10): "Revelation 7:9-12",
    # 11 Family, Marriage, Sex, and the Gospel
    (11, 1): "Genesis 1:26-28", (11, 2): "Romans 5:6-11", (11, 3): "Genesis 2:18-25", (11, 4): "Deuteronomy 6:4-9",
    (11, 5): "1 Corinthians 7:25-35", (11, 6): "Matthew 19:3-9", (11, 7): "Romans 1:18-32", (11, 8): "Psalm 139:13-16",
    (11, 9): "Matthew 5:27-30", (11, 10): "Proverbs 5:15-19",
    # 12 The Cross and Suffering
    (12, 1): "Romans 8:18-25", (12, 8): "2 Corinthians 4:16-18",
    # 13 Heaven, Hell, and the End of the World
    (13, 1): "Colossians 3:1-4", (13, 2): "James 4:13-17", (13, 3): "2 Corinthians 5:1-8", (13, 4): "1 Thessalonians 4:13-5:11",
    (13, 5): "1 Corinthians 15:35-58", (13, 6): "Revelation 20:11-15", (13, 7): "Luke 16:19-31", (13, 8): "Revelation 21:1-8",
    # 14 The Cross and Everyday Life (built on the two great commandments)
    (14, 1): "Matthew 22:34-40", (14, 2): "Galatians 2:20", (14, 3): "Mark 12:28-34", (14, 4): "1 Timothy 4:7-8",
    (14, 5): "Ephesians 5:22-6:4", (14, 6): "Luke 10:25-37", (14, 7): "Colossians 3:22-24", (14, 8): "1 Corinthians 10:31",
    (14, 9): "Philippians 4:8", (14, 10): "Hebrews 4:1-11",
    # 15 Christ, Culture, and a Call to Action
    (15, 1): "Romans 12:1-2", (15, 2): "1 Corinthians 15:1-8", (15, 3): "Proverbs 24:11-12", (15, 4): "James 1:27",
    (15, 5): "Isaiah 58:6-12", (15, 6): "Philemon 1:8-21", (15, 7): "1 Corinthians 6:9-20", (15, 8): "Leviticus 19:33-34",
    (15, 9): "1 Peter 4:12-19", (15, 10): "Matthew 24:14",
    # 16 A Global Gospel in a World of Religions
    (16, 1): "Acts 17:22-31", (16, 2): "John 14:1-7", (16, 3): "Acts 16:25-34", (16, 4): "Acts 14:8-18",
    (16, 5): "Isaiah 44:6-20", (16, 6): "Matthew 11:25-30", (16, 7): "1 John 2:18-25", (16, 8): "Psalm 14:1-3",
    (16, 9): "Revelation 5:9-10",
    # 17 Scripture and Authority in an Age of Skepticism
    (17, 1): "Amos 8:11-12", (17, 2): "2 Peter 1:16-21", (17, 3): "Matthew 5:17-18", (17, 4): "John 17:13-19",
    (17, 5): "Psalm 119:105-112", (17, 6): "Psalm 19:7-11", (17, 7): "Psalm 119:65-72", (17, 8): "Isaiah 40:6-8",
    # 18 Cults and Counterfeit Gospels
    (18, 1): "Matthew 7:15-23", (18, 2): "Galatians 1:6-9", (18, 3): "2 Peter 2:1-3", (18, 4): "Isaiah 43:10-11",
    (18, 5): "John 1:1-18", (18, 6): "Hebrews 10:10-18", (18, 7): "1 Timothy 6:3-10", (18, 8): "2 Timothy 4:1-5",
    (18, 9): "Jude 1:3-4",
    # 19 Prayer, Fasting, and the Pursuit of God (its other sessions walk the Bible book by book)
    (19, 1): "Matthew 6:5-18",
    # 20 God, Government, and the Gospel
    (20, 1): "Romans 13:1-7", (20, 2): "Colossians 1:13-20", (20, 5): "Mark 12:13-17", (20, 6): "1 Timothy 2:1-4",
    # 21 The Great Imbalance
    (21, 1): "Genesis 12:1-3", (21, 2): "Psalm 67:1-7", (21, 3): "Romans 15:18-24", (21, 4): "Matthew 9:35-38",
    (21, 5): "Acts 20:22-24", (21, 6): "Philippians 3:7-14", (21, 7): "Luke 24:45-49", (21, 8): "Romans 10:13-17",
    (21, 9): "Habakkuk 2:14",
})
SC_NO_PLACE = set()
# shows kept in the catalog but left off the road (Pray the Word: short prayers, not teaching)
OFF_ROAD_SOURCES = {"ptw"}
# Fearless Church (Spring Hill, TN): Sunday sermons, published on praise.global (the archive fearlesstn.org embeds).
FEARLESS_FEED = "https://praise.global/feed/fearlesstn"
SHOWS = {"fearless": "Fearless Church", "davey_archive": "Sermon archive", "ptw": "Pray the Word", "davey_wfth": "Wisdom for the Heart", "davey_journey": "The Wisdom Journey"}
# Skip Heitzig (Calvary Church, Albuquerque): public podcast feeds. Each episode's itunes:author names its speaker.
SKIP_FEEDS = {
    "skip_church": "http://feeds.calvaryabq.org/calvaryabqaudio",     # Sunday + Wednesday (Expound) messages, full length
    "skip_connect": "http://feeds.feedburner.com/ConnectionRadio",    # Connect with Skip Heitzig radio (messages in parts; Bible from 30,000 Feet)
}
# "Bible from 30,000 Feet" episodes are titled "Flight GEN01 - Part A": the code names the book(s) the overview covers
SKIP_FLIGHT_BOOKS = {"JAO": ["Joel", "Amos", "Obadiah"], "MNH": ["Micah", "Nahum", "Habakkuk"],
                     "ZHA": ["Zephaniah", "Haggai"], "ZMA": ["Zechariah", "Malachi"],
                     "JUD": ["Judges"],  # in this series JUD sits between Joshua and Ruth; Jude flies with 2-3 John (JJU)
                     "JJU": ["2 John", "3 John", "Jude"], "TPH": ["Titus", "Philemon"], "JLA": ["Jeremiah", "Lamentations"],
                     "MML": ["Matthew", "Mark", "Luke"], "THE": ["1 Thessalonians", "2 Thessalonians"],
                     "TIM": ["1 Timothy", "2 Timothy"], "PET": ["1 Peter", "2 Peter"], "SON": ["Song of Solomon"],
                     "1SAM": ["1 Samuel"], "2SAM": ["2 Samuel"], "1KIN": ["1 Kings"], "2KIN": ["2 Kings"],
                     "1CHR": ["1 Chronicles"], "2CHR": ["2 Chronicles"], "1COR": ["1 Corinthians"], "2COR": ["2 Corinthians"],
                     "1JOH": ["1 John"], "PHI": ["Philippians"],
                     "INT": ["Matthew"]}  # the 400 years between the Testaments: the bridge into Matthew

# ---- skip the intro music: seconds to start at when an episode is played fresh (resume ignores this) ----
INTRO_SKIP = {
    "skip_connect": 47,           # Connect with Skip Heitzig radio: 47 s intro
    "davey_journey": 13,          # The Wisdom Journey: fallback; each episode's own intro end is in data/intro_skip/
    "ptw": 0,                     # Pray the Word
    "platt_messages": 0,          # David Platt Messages
    "secret_church_podcast": 0,   # Secret Church podcast
    "twr360_secret_church": 0,    # Secret Church sessions (TWR360)
    "mclean_podcast": 0,          # McLean Bible Church
    "brookhills": 0,              # The Church at Brook Hills (Platt 2013-2014)
    "2819_podcast": 0,            # 2819 Church (PAM)
    "street_preachers": 0,        # Street Preachers (PAM)
    "davey_sermons": 6,           # Stephen Davey Sermons
    "davey_wfth": 53,             # Wisdom for the Heart: fallback (end of the fixed announcer intro); each episode's own is in data/intro_skip/
    "davey_journey": 6,           # The Wisdom Journey
}

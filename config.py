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
                    r"\bfor women\b|\bwomen'?s\b")

# 2819 Church preachers who teach inside PAM's series; they ride the road with PAM's voices, under their own name.
PAM_CHURCH_PREACHERS = ["Arik Hayes", "Milton James"]

# ---- Stephen Davey (Wisdom for the Heart / The Shepherd's Church) ----
# Every feed he publishes on Buzzsprout (wisdomonline.org itself sits behind a bot check and is not crawled).
DAVEY_FEEDS = {
    "davey_sermons": (2353448, "https://rss.buzzsprout.com/2353448.rss"),   # Stephen Davey Sermons (full Sunday sermons)
    "davey_wfth": (2545810, "https://rss.buzzsprout.com/2545810.rss"),      # Wisdom for the Heart (sermons broadcast in parts)
    "davey_journey": (2545807, "https://rss.buzzsprout.com/2545807.rss"),   # The Wisdom Journey (daily walk through the Bible)
}
SHOWS = {"ptw": "Pray the Word", "davey_wfth": "Wisdom for the Heart", "davey_journey": "The Wisdom Journey"}

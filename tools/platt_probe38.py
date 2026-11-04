"""The Story of Scripture transcripts and discussion questions Radical publishes for the parts whose audio came from its
server (3, 9, 13, 20, 21, 22), as text, so the recordings can be checked against what was preached. Saves probe3/sos_text/."""
import json, os, subprocess, requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
os.makedirs("probe3/sos_text", exist_ok=True)
d = json.load(open("probe3_in.json")) if os.path.exists("probe3_in.json") else None
C = "https://cdn.radical.net/images/"
DOCS = {"p3_t": C + "20190221125139/021719-Story-of-Scripture-Part-3-Transcript.pdf",
        "p9_q": C + "20190517135937/2019-03-31-Why-We-Need-Leviticus-Discussion-Questions.pdf",
        "p9_t": C + "20190517155109/033019_StoryofScripture9_WhyWeNeedLeviticus_Transcript.pdf",
        "p13_q": C + "20190517154758/2019-05-05-The-Lord-is-My-Shepherd-Discussion-Questions.pdf",
        "p13_t": C + "20190513142515/050519_StoryofScripturePart13-TheLordisMyShepherd_Transcript.pdf",
        "p20_t": C + "20190711100315/070719_StoryofScripturePart20-TheBlessingoftheFaithfulProvider_Transcript.pdf",
        "p21_t": C + "20190722090854/071419_StoryofScripturePart21_ShouldWeGiveUpontheChurch_Transcript.pdf",
        "p22_t": C + "20190725155539/072119_StoryofScripturePart22-AreYouWillingtoFullyCommitYourLifetoJesus_Transcript.pdf"}
for k, u in DOCS.items():
    r = requests.get(u, headers=H, timeout=90)
    print(k, r.status_code, len(r.content))
    if not r.ok: continue
    open(f"probe3/sos_text/{k}.pdf", "wb").write(r.content)
    subprocess.run(["pdftotext", f"probe3/sos_text/{k}.pdf", f"probe3/sos_text/{k}.txt"])
    os.remove(f"probe3/sos_text/{k}.pdf")
    print("   ", open(f"probe3/sos_text/{k}.txt").read()[:600].replace("\n", " "))

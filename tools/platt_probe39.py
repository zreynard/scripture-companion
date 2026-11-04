"""What the live app serves right now (version and a few features), as a phone would get it."""
import requests
H = {"User-Agent": "scripture-companion (personal Bible app; github.com/zreynard/scripture-companion)"}
B = "https://zreynard.github.io/scripture-companion/"
v = requests.get(B + "version.txt", headers=H, timeout=60, params={"x": "1"})
print("version.txt", v.status_code, v.text.strip(), v.headers.get("cache-control"), v.headers.get("age"))
h = requests.get(B, headers=H, timeout=60).text
import re
print("APPV", re.findall(r"const APPV=(\d+)", h)[:1])
for k in ("a step with one thing to do opens it", "function openSearch", "body{min-height:100%}", "the stop's whole list: introduction, scripture"):
    print(k, k in h)

"""List what Chinese Wikisource holds for the Shennong Bencao Jing (神農本草經), via its official API.

Usage:  python3 historical_texts/shennong/find_wikisource.py
Prints: pages whose title matches, their subpages (chapters), and the start of each main page's text.
Writes nothing.
"""
import json
import ssl
import urllib.parse
import urllib.request

API = "https://zh.wikisource.org/w/api.php"
UA = {"User-Agent": "EthnoHack-OverSlept/0.3 (research; non-commercial)"}


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def q(**p):
    url = API + "?" + urllib.parse.urlencode(dict(p, format="json", formatversion=2))
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=ctx()) as r:
        return json.loads(r.read())


titles = []
for term in ["神農本草經", "神农本草经", "本草經"]:
    for h in q(action="query", list="search", srsearch=term, srnamespace=0, srlimit=20)["query"]["search"]:
        if h["title"] not in titles and "本草" in h["title"]:
            titles.append(h["title"])
print("Pages with 本草 in the title:")
for t in titles:
    print("  ", t)

for t in [t for t in titles if "神農本草" in t or "神农本草" in t][:4]:
    print(f"\n== {t}")
    subs = q(action="query", list="prefixsearch", pssearch=t + "/", pslimit=50)["query"]["prefixsearch"]
    print(f"   subpages: {len(subs)}", " | ".join(s["title"] for s in subs[:30]))
    page = q(action="query", prop="revisions", rvprop="content", rvslots="main", titles=t)["query"]["pages"][0]
    text = page.get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("content", "")
    print(f"   page text: {len(text)} characters")
    print("   " + text[:900].replace("\n", "\n   "))

"""Fetch the Shennong Bencao Jing (神農本草經) from Chinese Wikisource, via its official API.

Usage:  python3 historical_texts/shennong/fetch_wikisource.py

Fetches two versions, with their subpages if any:
  神農本草經            the whole classic on one page (上經/中經/下經); Wikisource quality 50%
                        (complete, not proofread); no source edition named on the page
  神農本草經 (孫星衍)   Sun Xingyan's reconstruction (1799), a named, dated edition
Writes historical_texts/shennong/source/wikisource/<title>.json   wikitext + revision id + timestamp
       (one file per page; a page already saved is not fetched again)
Licence: Wikisource text CC BY-SA 4.0; the underlying texts are public domain.
"""
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "source" / "wikisource"
API = "https://zh.wikisource.org/w/api.php"
UA = {"User-Agent": "EthnoHack-OverSlept/0.3 (research; non-commercial; one-off fetch)"}
PAUSE = 3
ROOTS = ["神農本草經", "神農本草經 (孫星衍)"]


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def q(**p):
    url = API + "?" + urllib.parse.urlencode(dict(p, format="json", formatversion=2, maxlag=5))
    for attempt in range(6):
        time.sleep(PAUSE)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=ctx()) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            wait = int(e.headers.get("Retry-After") or 0) or 30 * (attempt + 1)
            print(f"    HTTP {e.code}; waiting {wait} s (try {attempt + 1}/6)", flush=True)
            time.sleep(wait)
    raise SystemExit("Wikisource kept refusing; run the same command again later (saved pages are kept).")


def save(title):
    path = OUT / (title.replace("/", "__") + ".json")
    if path.exists():
        return json.loads(path.read_text())
    page = q(action="query", prop="revisions|info", rvprop="content|ids|timestamp", rvslots="main",
             inprop="url", titles=title)["query"]["pages"][0]
    if page.get("missing"):
        print(f"  missing: {title}")
        return None
    rev = page["revisions"][0]
    rec = {"title": title, "url": page.get("fullurl"), "revid": rev["revid"], "timestamp": rev["timestamp"],
           "licence": "CC BY-SA 4.0 (Wikisource); underlying text public domain",
           "wikitext": rev["slots"]["main"]["content"]}
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    print(f"  saved {title}: {len(rec['wikitext'])} characters (revision {rec['revid']})", flush=True)
    return rec


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for root in ROOTS:
        print(f"\n== {root}")
        rec = save(root)
        if not rec:
            continue
        subs = [s["title"] for s in q(action="query", list="prefixsearch", pssearch=root + "/", pslimit=100)
                ["query"]["prefixsearch"] if s["title"].startswith(root + "/")]
        print(f"  subpages: {len(subs)}")
        for t in subs:
            save(t)
        print("  start of text:\n   " + rec["wikitext"][:700].replace("\n", "\n   "))
    print(f"\nSaved in {OUT}")


if __name__ == "__main__":
    main()

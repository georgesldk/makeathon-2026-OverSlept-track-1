"""Fetch the Shennong Bencao Jing (神農本草經) from the Chinese Text Project (ctext.org) API.

Usage:  python3 historical_texts/shennong/fetch_ctext.py
        python3 historical_texts/shennong/fetch_ctext.py --urn ctp:XXXX   # if the book's URN is known

Reads  .env  CTEXT_API_KEY (optional; without it ctext gives limited data. Never written anywhere)
Writes historical_texts/shennong/source/ctext_cache/   one file per API reply (errors are not cached)
       historical_texts/shennong/source/ctext_raw.json  every section: URN, title, path, paragraphs
and prints a report: which text ctext holds, its sections, how many paragraphs look like
drug entries ("X：味Y…主Z…"), and any API errors (e.g. a section that needs a key).

Source: Chinese Text Project, https://ctext.org (Donald Sturgeon), listed in the hackathon dataset
list. The original Shennong Bencao Jing (Eastern Han, 1st-2nd c. AD) is lost; every text is a later
reconstruction, so the edition ctext uses is recorded as given by its gettextinfo reply.
Bulk reuse is subject to ctext's terms: the book is fetched once, slowly, and cached.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CACHE = HERE / "source" / "ctext_cache"
OUT = HERE / "source" / "ctext_raw.json"
API = "https://api.ctext.org/"
PAUSE = 1.5                     # seconds between live calls: be gentle with a free service
TRIES = 3
CANDIDATE_PAGES = ["https://ctext.org/shen-nong-ben-cao-jing", "https://ctext.org/shennong-bencao-jing",
                   "https://ctext.org/shen-nong-ben-cao-jing/zh"]
TITLE = "神農本草經"
CALLS = {"live": 0, "cached": 0}


def env(name):
    if os.environ.get(name):
        return os.environ[name]
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.strip().startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def ctx():
    try:
        import truststore, ssl
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        import ssl
        return ssl.create_default_context()


def call(func, **params):
    """One API call, cached by its parameters (the key is never part of the cache name or file)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    name = func + "?" + urllib.parse.urlencode(sorted(params.items()))
    path = CACHE / (hashlib.sha256(name.encode()).hexdigest()[:32] + ".json")
    if path.exists():
        CALLS["cached"] += 1
        return json.loads(path.read_text())["reply"]
    key = env("CTEXT_API_KEY")
    q = dict(params, **({"apikey": key} if key else {}))
    url = API + func + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "EthnoHack-OverSlept/0.3 (research; non-commercial)"})
    for attempt in range(TRIES):
        try:
            time.sleep(PAUSE)
            with urllib.request.urlopen(req, timeout=60, context=ctx()) as r:
                reply = json.loads(r.read().decode("utf-8"))
            CALLS["live"] += 1
            break
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}"
        except Exception as e:
            err = str(e)[:100]
        print(f"    {func} failed ({err}), try {attempt + 1}/{TRIES}", flush=True)
        time.sleep(5 * (attempt + 1))
    else:
        return {"error": {"code": "NETWORK", "description": err}}
    if not (isinstance(reply, dict) and "error" in reply):
        path.write_text(json.dumps({"call": name, "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "reply": reply}, ensure_ascii=False))
    return reply


def find_urn():
    for page in CANDIDATE_PAGES:
        r = call("readlink", url=page)
        print(f"  readlink {page}: {json.dumps(r, ensure_ascii=False)[:200]}")
        if isinstance(r, dict) and r.get("urn"):
            return r["urn"]
    r = call("searchtexts", title=TITLE)
    print(f"  searchtexts {TITLE}: {json.dumps(r, ensure_ascii=False)[:600]}")
    books = r.get("books", []) if isinstance(r, dict) else []
    for b in books:
        if TITLE in b.get("title", ""):
            return b.get("urn")
    return None


def walk(urn, path, sections, errors):
    r = call("gettext", urn=urn)
    if not isinstance(r, dict) or "error" in r:
        errors.append({"urn": urn, "path": path, "error": r.get("error") if isinstance(r, dict) else r})
        print(f"  ! {urn}: {json.dumps(r, ensure_ascii=False)[:200]}")
        return
    title = r.get("title", "")
    here = path + [title]
    if r.get("fulltext"):
        sections.append({"urn": urn, "title": title, "path": here, "paragraphs": r["fulltext"]})
        print(f"  {' / '.join(here)}: {len(r['fulltext'])} paragraphs", flush=True)
    for sub in r.get("subsections", []) or []:
        walk(sub, here, sections, errors)


ENTRY = re.compile(r"^(?P<name>[^：:，。]{1,8})[：:]\s*味")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urn")
    a = ap.parse_args()
    print("API key:", "yes (from .env)" if env("CTEXT_API_KEY") else "none (ctext may limit what it returns)")
    print("status:", json.dumps(call("getstatus"), ensure_ascii=False)[:300])
    urn = a.urn or find_urn()
    if not urn:
        sys.exit("Could not find the book's URN. Open the book on ctext.org and pass its URN with --urn "
                 "(or tell Claude the page address).")
    print("URN:", urn)
    info = call("gettextinfo", urn=urn)
    print("text info:", json.dumps(info, ensure_ascii=False)[:800])
    sections, errors = [], []
    walk(urn, [], sections, errors)
    if not sections and any((e.get("error") or {}).get("code") == "ERR_REQUIRES_AUTHENTICATION" for e in errors):
        print("\nctext gives this book through its API only with a subscriber key (CTEXT_API_KEY in .env).\n"
              "Its web pages must not be scraped (ctext terms of service), so this script does not try.")
    paras = [p for s in sections for p in s["paragraphs"]]
    entries = [p for p in paras if ENTRY.match(p)]
    OUT.write_text(json.dumps({"source": "Chinese Text Project, https://ctext.org", "urn": urn, "info": info,
                               "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "sections": sections, "errors": errors}, ensure_ascii=False, indent=1))
    print(f"\n== Report\nsections with text: {len(sections)}   paragraphs: {len(paras)}   "
          f"look like drug entries (name：味…): {len(entries)}   errors: {len(errors)}")
    print(f"API calls: {CALLS['live']} live, {CALLS['cached']} from cache")
    print("paragraphs with 一名 (other names):", sum("一名" in p for p in paras),
          "  with 主 (indications):", sum("主" in p for p in paras),
          "  with 生 (habitat):", sum(bool(re.search(r"生[^。]{0,6}(山|川|谷|澤|池|田|野|水|海)", p)) for p in paras))
    print("\nfirst 3 entries:")
    for p in entries[:3]:
        print("  ", p[:160])
    print("\nfirst 3 paragraphs that are NOT entries:")
    for p in [p for p in paras if not ENTRY.match(p)][:3]:
        print("  ", p[:160])
    print(f"\nWrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

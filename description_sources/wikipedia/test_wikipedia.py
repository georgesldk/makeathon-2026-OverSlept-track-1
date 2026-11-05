"""Test: what plant descriptions does Wikipedia give? (WEAK evidence, rule D7)

Usage:  python3 description_sources/wikipedia/test_wikipedia.py

Uses the official MediaWiki API (free, no key). For the same 5 test plants as the
BHL test, it fetches the article's plain text (redirects followed, so a synonym or
the scientific name finds the article) and cuts out the description section
("Description", "Botany", "Morphology", "Characteristics" ...). If there is none,
it keeps the lead paragraph and says so.
Wikipedia is marked weak: it can lower confidence in a candidate but never lifts
one to tier A on its own.
Writes description_sources/wikipedia/test_results.json; replies cached in cache/.
"""
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUT = HERE / "test_results.json"
API = "https://en.wikipedia.org/w/api.php"
PLANTS = ["Solanum dulcamara", "Stellaria media", "Inula helenium", "Mandragora officinarum", "Iris pseudacorus"]
HEADINGS = ["description", "botany", "botanical description", "morphology", "characteristics",
            "identification", "appearance", "biology"]
CALLS = [0]
PAUSE = 1.0
# Wikimedia asks automated clients for a descriptive User-Agent with a way to reach the operator
USER_AGENT = "EthnoHack-OverSlept/0.1 (hackathon research on historical herbals; python-urllib)"


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ctx()


def article(title: str) -> dict:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / (re.sub(r"\W+", "_", title) + ".json")
    if path.exists():
        return json.load(open(path, encoding="utf-8"))
    q = urllib.parse.urlencode({"action": "query", "prop": "extracts|info", "inprop": "url",
                                "explaintext": 1, "exsectionformat": "wiki", "redirects": 1,
                                "titles": title, "format": "json", "formatversion": 2})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": USER_AGENT})
    for attempt in range(5):
        time.sleep(PAUSE)                 # one request at a time, spaced out, as Wikimedia asks
        try:
            with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 4:
                ra = e.headers.get("Retry-After")
                wait = int(ra) + 1 if ra and ra.isdigit() else 30 * (attempt + 1)
                print(f"    Wikipedia {e.code} (too many requests), waiting {wait}s")
                time.sleep(wait)
                continue
            raise
    page = data["query"]["pages"][0]
    path.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
    CALLS[0] += 1
    return page


def sections(text: str) -> list[tuple[int, str, str]]:
    """(level, heading, body) for each section; the lead has level 1 and heading ''."""
    parts = re.split(r"\n(={2,6}) (.+?) \1\n", "\n" + text)
    out = [(1, "", parts[0].strip())]
    for i in range(1, len(parts) - 2, 3):
        out.append((len(parts[i]), parts[i + 1].strip(), parts[i + 2].strip()))
    return out


def description(text: str) -> tuple[str, str]:
    """(heading used, text). A matching section includes its subsections."""
    secs = sections(text)
    for i, (level, head, body) in enumerate(secs):
        if head.lower() in HEADINGS:
            parts = [body]
            for lv, h, b in secs[i + 1:]:
                if lv <= level:
                    break
                parts.append(f"[{h}] {b}")
            joined = "\n".join(p for p in parts if p)
            if len(joined) > 80:
                return head, joined
    return "lead (no description section)", secs[0][2]


def main() -> None:
    results = {}
    for name in PLANTS:
        try:
            page = article(name)
        except Exception as e:
            print(f"\n{name}: ! {e}")
            continue
        if page.get("missing"):
            print(f"\n{name}: no article")
            results[name] = {"evidence": "weak", "found": False}
            continue
        head, text = description(page.get("extract") or "")
        results[name] = {"evidence": "weak", "found": True, "article": page["title"], "url": page.get("fullurl"),
                         "section": head, "text": text}
        print(f"\n{'=' * 90}\n{name} → article '{page['title']}', section: {head}, {len(text)} characters  [WEAK]\n{'=' * 90}")
        print(text[:900] + (" ..." if len(text) > 900 else ""))
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{CALLS[0]} new Wikipedia calls. Saved to description_sources/wikipedia/{OUT.name}\n")


if __name__ == "__main__":
    main()

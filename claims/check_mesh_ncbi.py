"""Check 6: an independent second opinion on each claim's MeSH concepts, from PubMed itself.

Usage:  python3 claims/check_mesh_ncbi.py --book culpeper     (run on your own computer: needs NCBI)

For every claim that has a MeSH concept, the claim's plain-English wording ("expels intestinal
worms") is sent to PubMed's search (NCBI E-utilities, esearch, db=pubmed, retmax=0). PubMed's
Automatic Term Mapping translates the words into MeSH terms, the same way it does for any user;
we read that translation and compare it with the concepts the model chose.
  agree    PubMed maps the wording to at least one of the model's MeSH concepts
  differ   PubMed maps it to other MeSH terms (listed, for a person to judge)
  none     PubMed finds no MeSH term in the wording (no opinion)
No AI, no key (NCBI allows 3 requests a second without one; we send fewer). Replies are cached.
Output: claims/<book>/mesh_crosscheck.json and the agreement rate on screen.
"""
import argparse
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache" / "ncbi"
API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PAUSE = 0.4


def ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ctx()
CALLS = [0]
LAST_ERROR = [""]


def pubmed_mesh(text: str) -> list:
    """The MeSH terms PubMed's Automatic Term Mapping finds in `text`."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (re.sub(r"\W+", "_", text.lower())[:120] + ".json")
    if path.exists():
        data = json.load(open(path, encoding="utf-8"))
    else:
        q = urllib.parse.urlencode({"db": "pubmed", "term": text, "retmax": 0, "retmode": "json",
                                    "tool": "ethnohack-overslept"})
        req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "EthnoHack-OverSlept/0.1"})
        data = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                    data = json.load(r)
            except Exception as e:
                data = {"esearchresult": {"ERROR": str(e)}}
            if not (data.get("esearchresult") or {}).get("ERROR"):
                break
            time.sleep(5 * (attempt + 1))
        if (data.get("esearchresult") or {}).get("ERROR"):
            LAST_ERROR[0] = str(data["esearchresult"]["ERROR"])[:200]
            return None                       # not cached: NCBI was down, the next run asks again
        path.write_text(json.dumps(data), encoding="utf-8")
        CALLS[0] += 1
        time.sleep(PAUSE)
    tr = (data.get("esearchresult") or {}).get("querytranslation", "")
    return sorted({m.lower() for m in re.findall(r'"([^"]+)"\[MeSH Terms\]', tr)})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="culpeper", choices=["culpeper", "dioscorides"])
    book = ap.parse_args().book
    entries = json.load(open(HERE / book / "claims.json", encoding="utf-8"))["entries"]
    results, verdicts = [], Counter()
    claims = [c for e in entries.values() for c in e["claims"] if c["mesh"]]
    print(f"{book}: {len(claims)} claims to check (progress every 25)")
    fails_in_a_row = 0
    for n, c in enumerate(claims, 1):
        pm = pubmed_mesh(c["claim"])
        if pm is None:
            verdicts["error"] += 1
            fails_in_a_row += 1
            if fails_in_a_row >= 5:
                print(f"  NCBI is not answering (5 failures in a row). Its last error: {LAST_ERROR[0]}\n"
                      "  Stopped; rerun later, finished claims are cached.")
                break
            continue
        fails_in_a_row = 0
        mine = {m["name"].lower() for m in c["mesh"]}
        v = "none" if not pm else "agree" if mine & set(pm) else "differ"
        verdicts[v] += 1
        results.append({"claim_id": c["claim_id"], "claim": c["claim"], "model_mesh": sorted(mine),
                        "pubmed_mesh": pm, "verdict": v})
        if n % 25 == 0:
            print(f"  {n}/{len(claims)} · {dict(verdicts)}")
    if not results:
        print("No answers from NCBI yet: nothing saved.")
        return
    out = HERE / book / "mesh_crosscheck.json"
    judged = verdicts["agree"] + verdicts["differ"]
    rate = verdicts["agree"] / judged if judged else 0
    out.write_text(json.dumps({"book": book, "method": "PubMed Automatic Term Mapping (NCBI esearch)",
                               "verdicts": dict(verdicts), "agreement_where_pubmed_has_an_opinion": round(rate, 3),
                               "claims": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{book}: {len(claims)} claims with MeSH · {dict(verdicts)}")
    print(f"Agreement with PubMed where PubMed maps the wording to MeSH: {verdicts['agree']}/{judged} ({rate:.0%})")
    for r in [r for r in results if r["verdict"] == "differ"][:10]:
        print(f"  differ: {r['claim']}  model: {', '.join(r['model_mesh'])}  PubMed: {', '.join(r['pubmed_mesh'][:4])}")
    print(f"{CALLS[0]} new NCBI calls. Saved to claims/{book}/mesh_crosscheck.json")


if __name__ == "__main__":
    main()

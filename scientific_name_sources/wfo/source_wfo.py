"""Look up every scientific name from the Culpeper aggregate in World Flora Online (WFO).

Usage:  python3 scientific_name_sources/wfo/source_wfo.py            # plant, mixed, unknown names
        add --book dioscorides to run it for Dioscorides (default: culpeper)
        python3 scientific_name_sources/wfo/source_wfo.py --all      # also names flagged non-plant
        python3 scientific_name_sources/wfo/source_wfo.py --limit 20 # first 20 names, for a test

Reads matching/<book>/scientific_name_queries.jsonl (written by aggregate.py),
writes scientific_name_sources/wfo/<book>/wfo.json.
Raw replies are cached in scientific_name_sources/wfo/cache/ (shared by both books).

Uses WFO's own Plant List service (list.worldfloraonline.org), not the hackathon copy:
  1. name matching (matching_rest.php): each name is sent without author, so WFO
     returns every name spelled that way (homonyms by different authors included):
       match       WFO's single unambiguous match, or none
       candidates  the other names WFO considers, all kept
     plus WFO's own explanation of what it did (narrative) and the data release.
     When WFO finds no name spelled like ours it lists its alphabetical neighbours
     (the first 50 names of the genus); each WFO name is therefore flagged
       spelling   same | close (1-2 letters) | different
  2. details (GraphQL, gql.php) for every WFO name returned: full name with authors,
     rank, role (accepted / synonym / unplaced / deprecated), nomenclatural status,
     and the accepted name it currently points to.

No ranking and no picking: the original forms of each name (with the authors the
common-name sources gave) are kept next to WFO's names, so the author can be used
to choose later. Names flagged non-plant by the aggregate are skipped by default,
because WFO only covers plants (--all sends them anyway).
"""
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BOOK = sys.argv[sys.argv.index("--book") + 1] if "--book" in sys.argv else "culpeper"
QUERIES = ROOT / "matching" / BOOK / "scientific_name_queries.jsonl"
OUT = HERE / BOOK / "wfo.json"
CACHE_DIR = HERE / "cache"
MATCH_CACHE = CACHE_DIR / "match.json"      # name -> matching_rest reply
NAME_CACHE = CACHE_DIR / "names.json"       # wfo_id -> GraphQL details

MATCH_API = "https://list.worldfloraonline.org/matching_rest.php"
GQL_API = "https://list.worldfloraonline.org/gql.php"
USER_AGENT = ("EthnoHack-OverSlept/0.1 "
              "(https://github.com/georgesldk/makeathon-2026-OverSlept-track-1)")
PAUSE = 0.3
RETRY_WAITS = [5, 15, 30, 60]
GIVE_UP_AFTER = 10
GQL_BATCH = 25                              # names per GraphQL request


def ssl_context():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


CTX = ssl_context()


def get_json(url: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
        return json.load(r)


def with_retries(fn, arg):
    for wait in [*RETRY_WAITS, None]:
        try:
            return fn(arg)
        except Exception as e:
            code = getattr(e, "code", 500)
            if wait is None or not (code >= 500 or code == 429 or "timed out" in str(e)):
                raise
            time.sleep(wait)


# --- 1. name matching ---------------------------------------------------------
def match(name: str) -> dict:
    return get_json(MATCH_API + "?" + urllib.parse.urlencode({"input_string": name}))


# --- 2. details via GraphQL -----------------------------------------------------
def gql(query: str) -> dict:
    out = get_json(GQL_API, {"query": query})
    if out.get("errors"):
        raise RuntimeError(f"WFO GraphQL error: {out['errors'][:2]}")
    return out["data"]


def scalar_fields(type_name: str) -> tuple[list[str], dict[str, str]]:
    """Plain fields of a GraphQL type, and object fields with their type name."""
    t = gql('{ __type(name: "%s") { fields { name args { name type { kind } } type { kind name ofType '
            '{ kind name ofType { kind name ofType { kind name } } } } } } }' % type_name)["__type"]
    plain, objects = [], {}
    for f in t["fields"]:
        if any(a["type"]["kind"] == "NON_NULL" for a in f["args"]):
            continue                       # needs an argument we cannot give
        ty = f["type"]
        while ty.get("ofType"):
            ty = ty["ofType"]
        if ty["kind"] in ("SCALAR", "ENUM"):
            plain.append(f["name"])
        elif ty["kind"] == "OBJECT":
            objects[f["name"]] = ty["name"]
    return plain, objects


def build_selection() -> str:
    """TaxonName fields + its current accepted usage (taxon concept) and that taxon's name."""
    name_plain, name_obj = scalar_fields("TaxonName")
    sel = " ".join(name_plain)
    for f in ("role", "rank", "nomenclaturalStatus"):       # in case WFO returns these as objects
        if f in name_obj:
            sel += f" {f} {{ " + " ".join(scalar_fields(name_obj[f])[0]) + " }"
    usage_type = name_obj.get("currentPreferredUsage")
    if usage_type:
        con_plain, con_obj = scalar_fields(usage_type)
        inner = " ".join(con_plain)
        if "hasName" in con_obj:
            inner += " hasName { " + " ".join(name_plain) + " }"
        sel += " currentPreferredUsage { " + inner + " }"
    return sel


def details(ids: list[str], selection: str) -> dict[str, dict]:
    parts = [f'n{i}: taxonNameById(nameId: "{w}") {{ {selection} }}' for i, w in enumerate(ids)]
    data = gql("{ " + " ".join(parts) + " }")
    return {w: data.get(f"n{i}") for i, w in enumerate(ids)}


# --- run ----------------------------------------------------------------------
def load(p: Path) -> dict:
    return json.load(open(p, encoding="utf-8")) if p.exists() else {}


def save(p: Path, d: dict) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def fetch_all(label, todo, batch, fn, store, path):
    failed, done = 0, 0
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        try:
            got = with_retries(fn, chunk if batch > 1 else chunk[0])
            store.update(got if batch > 1 else {chunk[0]: got})
            failed = 0
        except Exception as e:
            failed += 1
            print(f"  ! {chunk[0]}: {e} (will retry on the next run)")
            if failed >= GIVE_UP_AFTER:
                save(path, store)
                sys.exit("\nWFO seems to be down. Progress is saved; run again later.")
            continue
        done += len(chunk)
        if done % 100 < batch or done == len(todo):
            save(path, store)
            print(f"  {label}: {done} of {len(todo)}")
        time.sleep(PAUSE)
    save(path, store)


def plain(v):
    """A field WFO may give as text or as an object with a name."""
    if isinstance(v, dict):
        return v.get("name") or v.get("id") or v.get("label") or json.dumps(v)
    return v


def squash(s: str | None) -> str:
    """Name without case, spaces, hyphens or hybrid sign: "Atropa bella-donna" = "Atropa belladonna"."""
    return re.sub(r"[\s\-×.]|(?<=\s)x(?=\s)", "", (s or "").lower())


def spelling(wfo_name: str | None, asked: str) -> str | None:
    """How WFO's name compares with the name we asked for (text only):
         same       identical apart from case, spaces, hyphens, hybrid sign
         close      1-2 letters differ, same number of words (silvestris / sylvestris)
         different  anything else: WFO's alphabetical neighbours when it found no such name"""
    if not wfo_name:
        return None
    a, b = squash(wfo_name), squash(asked)
    if a == b:
        return "same"
    if len(wfo_name.split()) == len(asked.split()) and a[:1] == b[:1] and edits(a, b) <= 2:
        return "close"
    return "different"


def edits(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    rows = [json.loads(l) for l in open(QUERIES, encoding="utf-8")]
    keep_all = "--all" in sys.argv
    skipped = [r for r in rows if r["kingdom_flag"] == "non-plant" and not keep_all]
    rows = [r for r in rows if keep_all or r["kingdom_flag"] != "non-plant"][:limit]
    CACHE_DIR.mkdir(exist_ok=True)
    matches, names = load(MATCH_CACHE), load(NAME_CACHE)

    print(f"\nLooking up {len(rows)} scientific names in World Flora Online "
          f"({len(skipped)} flagged non-plant skipped; --all to include them)\n")
    todo = [r["name"] for r in rows if r["name"] not in matches]
    stale = [w for w, d in names.items() if d and "currentPreferredUsage" not in d and "role" not in d]
    for w in stale:
        del names[w]                           # fetched before role/accepted name were included
    need_ids = [x["wfo_id"] for r in rows for m in [matches.get(r["name"]) or {}]
                for x in ([m["match"]] if m.get("match") else []) + (m.get("candidates") or [])]
    selection = None
    try:  # one test call first, so a network or certificate problem is obvious
        if todo or any(w not in names for w in need_ids):
            selection = build_selection()
            match("Solanum dulcamara")
    except Exception as e:
        sys.exit(f"Cannot use WFO ({e}).\nIf this is a certificate error, run:  pip install truststore")

    print(f"Step 1: name matching ({len(todo)} to ask, {len(matches)} cached)")
    fetch_all("names asked", todo, 1, match, matches, MATCH_CACHE)

    ids = []
    for r in rows:
        m = matches.get(r["name"]) or {}
        ids += [x["wfo_id"] for x in ([m["match"]] if m.get("match") else []) + (m.get("candidates") or [])]
    ids = sorted(set(ids))
    # accepted names that are not themselves among the results also get their details
    for _ in range(2):
        todo = [w for w in ids if w not in names]
        if todo and selection is None:
            selection = build_selection()
        print(f"\nStep 2: details of each WFO name ({len(todo)} to ask, {len(names)} cached)")
        fetch_all("names detailed", todo, GQL_BATCH, lambda c: details(c, selection), names, NAME_CACHE)
        acc = {(((names.get(w) or {}).get("currentPreferredUsage") or {}).get("hasName") or {}).get("id")
               for w in ids}
        new = sorted(a for a in acc if a and a not in ids)
        if not new:
            break
        ids += new

    def describe(x: dict, asked: str) -> dict:
        d = names.get(x["wfo_id"]) or {}
        usage = d.get("currentPreferredUsage") or {}
        acc = usage.get("hasName") or {}
        return {"wfo_id": x["wfo_id"], "full_name": x.get("full_name_plain"),
                "name_without_authors": d.get("fullNameStringNoAuthorsPlain"),
                "authors": d.get("authorsString"), "rank": plain(d.get("rank")), "role": plain(d.get("role")),
                "nomenclatural_status": d.get("nomenclaturalStatus"), "placement": x.get("placement"),
                "accepted_wfo_id": acc.get("id"), "accepted_name": acc.get("fullNameStringPlain"),
                "accepted_name_without_authors": acc.get("fullNameStringNoAuthorsPlain"),
                "spelling": spelling(d.get("fullNameStringNoAuthorsPlain"), asked)}

    out, release = {}, None
    for r in rows:
        m = matches.get(r["name"]) or {}
        release = release or (m.get("params") or {}).get("classificationVersion")
        out[r["name"]] = {
            "query_id": r["query_id"], "level": r["level"], "kingdom_flag": r["kingdom_flag"],
            "original_forms": r["original_forms"], "herbs": r["herbs"],
            "match": describe(m["match"], r["name"]) if m.get("match") else None,
            "candidates": [describe(c, r["name"]) for c in m.get("candidates") or []],
            "wfo_parsed_as": m.get("parsedName"), "wfo_method": (m.get("params") or {}).get("method"),
            "wfo_narrative": m.get("narrative"), "error": m.get("errorMessage"),
            "asked": r["name"] in matches}

    OUT.write_text(json.dumps({
        "source": "World Flora Online Plant List: name matching (matching_rest.php) and GraphQL (gql.php)",
        "wfo_release": release, "retrieved": date.today().isoformat(),
        "licence": "WFO Plant List data: CC0", "names": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    vals = list(out.values())
    matched = [v for v in vals if v["match"]]
    cands = [v for v in vals if not v["match"] and v["candidates"]]
    none = [v for v in vals if not v["match"] and not v["candidates"]]
    roles = {}
    for v in matched:
        roles[str(v["match"]["role"])] = roles.get(str(v["match"]["role"]), 0) + 1
    print(f"\n{len(vals)} names looked up in WFO (release {release})\n")
    print(f"  {len(matched):>5} matched one WFO name   roles: " +
          ", ".join(f"{k} {n}" for k, n in sorted(roles.items(), key=lambda kv: -kv[1])))
    same = [v for v in cands if any(x["spelling"] == "same" for x in v["candidates"])]
    close = [v for v in cands if v not in same and any(x["spelling"] == "close" for x in v["candidates"])]
    print(f"  {len(cands):>5} have candidates but no single match:")
    print(f"  {len(same):>9} with the same spelling (same name, different authors / deprecated entries)")
    print(f"  {len(close):>9} only with a close spelling (1-2 letters differ)")
    print(f"  {len(cands) - len(same) - len(close):>9} only WFO's alphabetical neighbours (not really found)")
    print(f"  {len(none):>5} not found in WFO")
    print(f"\nSaved to scientific_name_sources/wfo/{BOOK}/{OUT.name} ({OUT.stat().st_size / 1e6:.1f} MB)\n")


if __name__ == "__main__":
    main()

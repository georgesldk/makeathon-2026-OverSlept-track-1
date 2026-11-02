"""Looks historical plant names up in the hosted WFO API.

    uv run python -m ethnohack.resolve --limit 5

Phase 0 asks a specific question: of five historical names, how many give one
candidate taxon, how many give several, and how many give none? The answer
decides whether identification is tractable on this corpus.

Note the hosted wrapper answers on HTTPS, not HTTP, despite the PDF listing
http:// — plain HTTP returns 400.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from ethnohack.config import REPO_ROOT

WFO_BASE = "https://wfo.ethcstwin.di.uoa.gr:65000"
PASSAGES_PATH = REPO_ROOT / "data" / "passages" / "culpeper_1653.jsonl"
OUT_PATH = REPO_ROOT / "data" / "cache" / "resolution" / "wfo_candidates.json"


@dataclass
class Resolution:
    query: str
    exact: list[str]
    similar: list[str]
    verdict: str  # one | several | none


def client() -> httpx.Client:
    # The wrapper serves TLS on 65000 with a certificate that does not match the
    # host, so verification is off for this one host only.
    return httpx.Client(base_url=WFO_BASE, timeout=30.0, verify=False, follow_redirects=True)


def names_of(payload) -> list[str]:
    """Pull readable names out of whatever shape the endpoint returns."""
    if payload is None:
        return []
    if isinstance(payload, dict):
        for key in ("results", "items", "data", "names"):
            if key in payload:
                return names_of(payload[key])
        payload = [payload]
    out = []
    for row in payload:
        if isinstance(row, str):
            out.append(row)
        elif isinstance(row, dict):
            for key in ("full_name_plain", "full_name_no_authors", "full_name", "name"):
                if row.get(key):
                    out.append(str(row[key]))
                    break
    return out


def lookup(http: httpx.Client, name: str) -> Resolution:
    exact: list[str] = []
    similar: list[str] = []

    try:
        reply = http.get("/name/first_hit/", params={"names": name, "only_if_valid": "true"})
        if reply.status_code == 200:
            exact = names_of(reply.json())
    except Exception as error:  # noqa: BLE001
        print(f"  first_hit failed for {name!r}: {type(error).__name__}")

    if not exact:
        try:
            reply = http.get(
                "/names/find_similar",
                params={"search_for_name": name, "first_x_letters": 4},
            )
            if reply.status_code == 200:
                similar = names_of(reply.json())[:8]
        except Exception as error:  # noqa: BLE001
            print(f"  find_similar failed for {name!r}: {type(error).__name__}")

    if len(exact) == 1:
        verdict = "one"
    elif len(exact) > 1 or len(similar) > 1:
        verdict = "several"
    elif similar:
        verdict = "several"
    else:
        verdict = "none"
    return Resolution(query=name, exact=exact, similar=similar, verdict=verdict)


def headings(limit: int) -> list[str]:
    if not PASSAGES_PATH.exists():
        sys.exit(f"No passages at {PASSAGES_PATH}. Run: uv run python -m ethnohack.corpus")
    seen: list[str] = []
    with PASSAGES_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            heading = json.loads(line)["heading"]
            if heading not in seen:
                seen.append(heading)
            if len(seen) >= limit:
                break
    return seen


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve historical names via WFO.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--name", help="Look up one name instead of reading the corpus")
    args = parser.parse_args()

    queries = [args.name] if args.name else headings(args.limit)
    print(f"{WFO_BASE}\n")

    results: list[Resolution] = []
    with client() as http:
        for query in queries:
            result = lookup(http, query)
            results.append(result)
            print(f"{query}  ->  {result.verdict}")
            for hit in result.exact:
                print(f"    exact:   {hit}")
            for hit in result.similar:
                print(f"    similar: {hit}")
            print()

    tally = {v: sum(1 for r in results if r.verdict == v) for v in ("one", "several", "none")}
    print(f"one: {tally['one']}   several: {tally['several']}   none: {tally['none']}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSaved {OUT_PATH}")

    if tally["none"] >= len(results) - 1:
        print(
            "\nMostly 'none' is the expected Phase 0 finding: Culpeper's headings are English\n"
            "vernacular names and WFO indexes scientific ones. The gap is a vernacular-to-\n"
            "scientific step, which WFO does not provide. That is a result, not a failure."
        )


if __name__ == "__main__":
    main()

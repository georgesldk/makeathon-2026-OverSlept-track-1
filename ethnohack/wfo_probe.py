"""Asks the hackathon-hosted WFO API what endpoints it offers.

    uv run python -m ethnohack.wfo_probe

The organisers advertise these wrappers but publish no schema in the PDF, and
they may be HTTP rather than HTTPS. This fetches the OpenAPI document and lists
the paths, so the resolver can be written against what is actually there.
"""

from __future__ import annotations

import json

import httpx

HOSTS = [
    "http://wfo.ethcstwin.di.uoa.gr:65000",
    "https://wfo.ethcstwin.di.uoa.gr:65000",
]


def probe(base: str) -> dict | None:
    for path in ("/openapi.json", "/docs/openapi.json"):
        url = base + path
        try:
            response = httpx.get(url, timeout=20.0, follow_redirects=True, verify=False)
        except Exception as error:  # noqa: BLE001
            print(f"  {url} -> {type(error).__name__}: {error}")
            continue
        if response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError:
                print(f"  {url} -> 200 but not JSON")
        else:
            print(f"  {url} -> HTTP {response.status_code}")
    return None


def main() -> None:
    for base in HOSTS:
        print(f"\nTrying {base}")
        spec = probe(base)
        if not spec:
            continue

        title = spec.get("info", {}).get("title", "untitled")
        print(f"\n  Reachable: {title}\n")
        for path, methods in sorted(spec.get("paths", {}).items()):
            for method, detail in methods.items():
                summary = detail.get("summary", "")
                params = [p.get("name") for p in detail.get("parameters", [])]
                arg_list = f"  ({', '.join(p for p in params if p)})" if params else ""
                print(f"  {method.upper():6} {path}{arg_list}")
                if summary:
                    print(f"         {summary}")
        print("\nPaste this back to Claude to write the resolver.")
        return

    print("\nNeither host answered. Options:")
    print("  - the wrappers may be up only during the event, or need the venue network")
    print("  - ask the Track 1 lead whether they are live")
    print("  - fall back to the public WFO API at https://list.worldfloraonline.org")


if __name__ == "__main__":
    main()

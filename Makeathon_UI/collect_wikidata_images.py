#!/usr/bin/env python3
"""Second pass for candidate photos: Wikidata / Wikimedia Commons (2026-11-07).

Run after collect_candidate_images.py. Only names GBIF left without a photo ("unmatched" or
"no_eligible_image") are tried. The same rules as the GBIF pass:
  - the Wikidata item's taxon name (P225) must equal the candidate's name without authorship;
  - the image is the item's main image (P18) on Wikimedia Commons;
  - licence CC0, public domain, CC BY or CC BY-SA only, and a named creator.
Each record keeps the Wikidata item, the Commons page, the creator and the licence. A picture
illustrates a proposed modern taxon, not an ancient identification.

Usage:  python3 collect_wikidata_images.py            (all missing names)
        python3 collect_wikidata_images.py --limit 20 (a short test)
"""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / 'data' / 'candidate_images.json'
USER_AGENT = 'EthnoTrace/1.0 (botanical research; candidate image metadata)'
LICENCE_OK = re.compile(r'^(CC0|Public domain|PD|CC BY(-SA)? \d(\.\d)?)', re.I)
RANKS = ('subsp.', 'var.', 'f.', 'subvar.')


def bare_name(name):
    """'Agrimonia pilosa var. pilosa Ledeb.' -> 'Agrimonia pilosa var. pilosa' (drops authorship)."""
    words = name.replace('×', '× ').split()
    out = words[:2]
    i = 2
    while i + 1 < len(words) and words[i] in RANKS:
        out += words[i:i + 2]
        i += 2
    return ' '.join(w for w in out if w)


def fetch(url, params):
    """GET JSON; on HTTP 429 wait as long as the server asks (Retry-After, else 10 s, 20 s, 40 s …) and retry."""
    from urllib.error import HTTPError
    params = {**params, 'maxlag': 5} if 'wikidata.org/w/api.php' in url or 'commons.wikimedia.org' in url else params
    req = Request(url + '?' + urlencode(params), headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    wait = 10
    for attempt in range(6):
        try:
            with urlopen(req, timeout=40) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in (429, 503) or attempt == 5:
                raise
            delay = int(exc.headers.get('Retry-After') or wait)
            print(f'    asked to slow down; waiting {delay} s', flush=True)
            time.sleep(delay)
            wait *= 2


def wikidata_images(names):
    """{taxon name: (QID, Commons file name)} for names whose Wikidata item has a main image.

    Uses the regular Wikidata API (not the query service, which is rate-limited during outages):
    a search for items whose taxon name (P225) is exactly the name, then the items' claims."""
    from urllib.error import HTTPError
    api = 'https://www.wikidata.org/w/api.php'
    found = {}
    for name in names:
        hits = fetch(api, {'action': 'query', 'list': 'search', 'format': 'json', 'srlimit': 5,
                           'srsearch': f'haswbstatement:"P225={name}"'}).get('query', {}).get('search', [])
        qids = [h['title'] for h in hits]
        time.sleep(1)
        if not qids:
            continue
        entities = fetch(api, {'action': 'wbgetentities', 'format': 'json', 'ids': '|'.join(qids), 'props': 'claims'})['entities']
        matches = []
        for qid, ent in entities.items():
            claims = ent.get('claims', {})
            taxon = [c['mainsnak'].get('datavalue', {}).get('value') for c in claims.get('P225', [])]
            images = [c['mainsnak'].get('datavalue', {}).get('value') for c in claims.get('P18', [])]
            if name in taxon and images and images[0]:
                matches.append((qid, images[0].replace(' ', '_')))
        if len(matches) == 1:        # two items with the same name and an image: ambiguous, skip it
            found[name] = matches[0]
        time.sleep(1)
    return found


def commons_info(files):
    """{file name: imageinfo} with licence, creator and a resized URL."""
    from urllib.parse import unquote
    titles = '|'.join('File:' + unquote(f) for f in files)
    data = fetch('https://commons.wikimedia.org/w/api.php', {
        'action': 'query', 'format': 'json', 'prop': 'imageinfo', 'titles': titles,
        'iiprop': 'url|extmetadata', 'iiurlwidth': 800})
    out = {}
    for page in data.get('query', {}).get('pages', {}).values():
        info = (page.get('imageinfo') or [None])[0]
        if info:
            out[page['title'][5:].replace(' ', '_')] = info
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='try only this many names (0 = all)')
    args = ap.parse_args()
    existing = json.load(open(OUTPUT, encoding='utf-8'))
    records = existing['images']
    todo = [k for k, v in records.items() if v.get('status') in ('unmatched', 'no_eligible_image')]
    if args.limit:
        todo = todo[:args.limit]
    print(f'{len(todo)} names without a GBIF photo')
    found = skipped = 0
    for i in range(0, len(todo), 40):
        chunk = todo[i:i + 40]
        by_bare = {}
        for full in chunk:
            by_bare.setdefault(bare_name(full), []).append(full)
        try:
            hits = wikidata_images(list(by_bare))
            infos = commons_info([f for _, f in hits.values()]) if hits else {}
        except Exception as exc:     # network trouble: keep what we have, try again next run
            print(f'  batch {i // 40 + 1}: {exc}')
            time.sleep(3)
            continue
        for bare, (qid, file) in hits.items():
            from urllib.parse import unquote
            info = infos.get(unquote(file).replace(' ', '_'))
            meta = (info or {}).get('extmetadata', {})
            licence = meta.get('LicenseShortName', {}).get('value', '')
            creator = html.unescape(re.sub(r'<[^>]+>', '', meta.get('Artist', {}).get('value', ''))).strip()
            if not info or not LICENCE_OK.match(licence) or not creator or creator.lower() in ('unknown', 'unknown author', 'anonymous'):
                skipped += 1
                continue
            licence_url = meta.get('LicenseUrl', {}).get('value') or info.get('descriptionurl')
            for full in by_bare[bare]:
                records[full] = {
                    'status': 'available', 'scientific_name': full, 'source': 'wikidata',
                    'wikidata_id': qid, 'wikidata_url': f'https://www.wikidata.org/wiki/{qid}',
                    'image_url': info.get('thumburl') or info['url'], 'image_source_url': info.get('descriptionurl'),
                    'occurrence_url': f'https://www.wikidata.org/wiki/{qid}',
                    'creator': creator[:200], 'license': licence, 'license_url': licence_url,
                    'publisher': 'Wikimedia Commons', 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                }
                found += 1
        print(f'  batch {i // 40 + 1} done ({found} photos so far)', flush=True)
    OUTPUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Added {found} photos from Wikimedia Commons; {skipped} images skipped (licence or creator missing).')
    print(f'Saved to {OUTPUT.relative_to(HERE.parent)}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Collect traceable GBIF image candidates without changing scientific outputs.

Defaults to a small pilot. Use --limit 0 to check every distinct A/B name.
Only exact, accepted GBIF name matches and directly matching occurrence taxon
keys are used. A picture illustrates a proposed modern taxon, not an ancient ID.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT = HERE / 'data' / 'candidate_images.json'
USER_AGENT = 'EthnoTrace/1.0 (botanical research; image metadata pilot)'


def get(path, params):
    req = Request('https://api.gbif.org/v1/' + path + '?' + urlencode(params), headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urlopen(req, timeout=25) as response:
        return json.load(response)


def normalize(name):
    return ' '.join(unicodedata.normalize('NFC', name or '').split()).casefold()


def allowed_license(value):
    value = (value or '').lower().replace('http://', 'https://').rstrip('/')
    match = re.fullmatch(r'https://creativecommons\.org/(licenses/(by|by-sa)/(3\.0|4\.0)|publicdomain/zero/1\.0)', value)
    return value + '/' if match else None


def https(value):
    return isinstance(value, str) and urlparse(value).scheme == 'https' and bool(urlparse(value).netloc)


def find_image(name):
    try:
        match = get('species/match', {'name': name, 'strict': 'true'})
        if (match.get('matchType') != 'EXACT' or match.get('status') != 'ACCEPTED'
                or match.get('confidence') != 100 or not match.get('usageKey')
                or normalize(match.get('scientificName')) != normalize(name)):
            return {'status': 'unmatched', 'gbif_match_type': match.get('matchType'), 'gbif_name': match.get('scientificName')}
        taxon = match['usageKey']
        occurrences = get('occurrence/search', {'taxonKey': taxon, 'mediaType': 'StillImage', 'limit': 40})
        for occurrence in occurrences.get('results', []):
            if occurrence.get('taxonKey') != taxon:
                continue
            for media in occurrence.get('media', []):
                licence = allowed_license(media.get('license'))
                creator = media.get('creator') or media.get('rightsHolder')
                url = media.get('identifier')
                if media.get('type') != 'StillImage' or not licence or not creator or not https(url):
                    continue
                return {'status': 'available', 'scientific_name': name, 'gbif_taxon_id': taxon,
                        'gbif_taxon_url': 'https://www.gbif.org/species/' + str(taxon),
                        'occurrence_id': occurrence.get('key'),
                        'occurrence_url': 'https://www.gbif.org/occurrence/' + str(occurrence.get('key')),
                        'image_url': url, 'image_source_url': media.get('references') if https(media.get('references')) else None,
                        'creator': creator, 'license_url': licence, 'publisher': media.get('publisher'),
                        'retrieved_at': datetime.now(timezone.utc).isoformat()}
        return {'status': 'no_eligible_image', 'gbif_taxon_id': taxon}
    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}


def names():
    result = set()
    for book in ('culpeper', 'dioscorides'):
        with (ROOT / 'matching' / book / 'eligibility.json').open(encoding='utf-8') as f:
            entries = json.load(f)['herbs']
        for entry in entries.values():
            for section in ('shown', 'possible'):
                result.update(row['accepted_name'] for row in entry[section] if row.get('accepted_name') and not row['accepted_name'].startswith('(unresolved:'))
    return sorted(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=20, help='Distinct names to check (default 20; 0 = all)')
    parser.add_argument('--workers', type=int, default=3, choices=range(1, 5))
    parser.add_argument('--refresh', action='store_true', help='Recheck names even when a previous lookup completed')
    args = parser.parse_args()
    if args.limit < 0:
        parser.error('--limit must be non-negative')
    all_names = names()
    if args.limit and args.limit < len(all_names):
        seeds = ['Agrimonia eupatoria L.', 'Daucus carota L.', 'Beta vulgaris L.']
        sample = [n for n in seeds if n in all_names][:args.limit]
        for i in range(len(all_names)):
            candidate = all_names[(i * len(all_names)) // max(1, args.limit)] if i < args.limit else all_names[i]
            if candidate not in sample:
                sample.append(candidate)
            if len(sample) == args.limit:
                break
    else:
        sample = all_names
    existing = json.loads(OUTPUT.read_text(encoding='utf-8')) if OUTPUT.exists() else {'schema_version': 1, 'images': {}}
    records = existing['images']
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    def save():
        temp = OUTPUT.with_suffix('.tmp')
        temp.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(OUTPUT)

    pending = [name for name in sample if args.refresh or records.get(name, {}).get('status') not in ('available', 'unmatched', 'no_eligible_image')]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(find_image, name): name for name in pending}
        for completed, future in enumerate(as_completed(futures), start=1):
            name = futures[future]
            row = future.result()
            # Never overwrite a previously usable image with a transient failure.
            if row['status'] == 'available' or records.get(name, {}).get('status') != 'available':
                records[name] = row
            print(f"{name}: {row['status']}", flush=True)
            if completed % 20 == 0:
                save()
    save()
    totals = {state: sum(records.get(n, {}).get('status') == state for n in sample) for state in ('available','unmatched','no_eligible_image','error')}
    print(f'Checked {len(sample)} of {len(all_names)} distinct A/B scientific-name strings: {totals}')
    print(f'Saved {OUTPUT}')


if __name__ == '__main__':
    main()

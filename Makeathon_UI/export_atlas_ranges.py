#!/usr/bin/env python3
"""Export each candidate plant's native regions (WCVP, WGSRPD level 2) for the Atlas page.

Reads matching/<book>/geography.json (already computed by the pipeline) and writes
data/plant_ranges.json: {accepted scientific name: [region names]}. Offline, no database needed.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / 'public' / 'atlas' / 'plant_ranges.json'
ALIASES = {'Central Asia': 'Middle Asia'}   # pipeline name -> WGSRPD level-2 name used by the map

ranges, families = {}, {}
for book in ('culpeper', 'dioscorides', 'shennong'):   # plant family of each candidate (for grouping bubbles)
    path = ROOT / 'matching' / book / 'eligibility.json'
    if path.exists():
        herbs = json.load(open(path, encoding='utf-8'))['herbs']
        for herb in (herbs.values() if isinstance(herbs, dict) else herbs):
            for c in herb.get('shown', []) + herb.get('possible', []):
                if isinstance(c, dict) and c.get('accepted_name') and c.get('family'):
                    families.setdefault(c['accepted_name'], c['family'])
for book in ('culpeper', 'dioscorides', 'shennong'):
    path = ROOT / 'matching' / book / 'geography.json'
    if not path.exists():
        continue
    herbs = json.load(open(path, encoding='utf-8'))['herbs']
    for _, herb in (herbs.items() if isinstance(herbs, dict) else enumerate(herbs)):
        for c in herb.get('candidates', []):
            name, regions = c.get('accepted_name'), c.get('native_regions') or []
            if name and regions:
                ranges[name] = sorted({ALIASES.get(r, r) for r in regions})
OUT.write_text(json.dumps({'schema_version': 1, 'source': 'WCVP native distribution via matching/<book>/geography.json',
                           'ranges': ranges, 'families': families}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
print(f'{len(ranges)} plants with a native range, {len(families)} with a family -> {OUT.relative_to(ROOT)}')

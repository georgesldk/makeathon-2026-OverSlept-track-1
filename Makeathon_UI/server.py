#!/usr/bin/env python3
"""Local read-only API for the existing EthnoTrace Neo4j graph."""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from neo4j import GraphDatabase, READ_ACCESS

URI = os.environ.get('NEO4J_URI', 'neo4j://127.0.0.1:7687')
DATABASE = os.environ.get('NEO4J_DATABASE', 'ethnotrace-clean')
USER = os.environ.get('NEO4J_USER', 'neo4j')
PASSWORD = os.environ.get('NEO4J_PASSWORD')
if not PASSWORD:
    raise SystemExit('Set NEO4J_PASSWORD in your environment before starting the API.')
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))


def query(cypher, **parameters):
    with driver.session(database=DATABASE, default_access_mode=READ_ACCESS) as session:
        return [row.data() for row in session.run(cypher, **parameters)]


def context():
    rows = query('''MATCH (b:StructuredBuild {status:'complete'})
        MATCH (d:DatasetImport {snapshot_id:b.snapshot_id, kind:'claims_and_stage3_shared'})
        MATCH (f:DatasetImport {snapshot_id:b.snapshot_id, kind:'full_unit_source_records'})-[:USES_CLAIMS_FROM]->(d)
        RETURN b.snapshot_id AS snapshot, d.id AS dataset, f.id AS full_dataset''')
    requested = os.environ.get('ETHNOTRACE_SNAPSHOT')
    if requested:
        rows = [row for row in rows if row['snapshot'] == requested]
    if len(rows) != 1:
        raise RuntimeError('Expected one completed snapshot and shared dataset; configure ETHNOTRACE_SNAPSHOT if necessary.')
    return rows[0]


def number(params, name, default, maximum):
    try:
        return min(max(int(params.get(name, [str(default)])[0]), 0), maximum)
    except ValueError:
        raise ValueError(f'Invalid {name}')


def identifier(value):
    if not re.fullmatch(r'[a-f0-9]{64}', value):
        raise ValueError('Invalid record identifier')
    return value


def entries(ctx, params):
    term = params.get('q', [''])[0].strip().lower()[:120]
    entry_id = params.get('entry_id', [''])[0]
    if entry_id:
        identifier(entry_id)
    book = params.get('book', [''])[0]
    if book not in ('', 'culpeper', 'dioscorides'):
        raise ValueError('Invalid book')
    tier = params.get('tier', [''])[0]
    if tier not in ('', 'A', 'B', 'X'):
        raise ValueError('Invalid tier')
    family = params.get('family', [''])[0].strip().lower()[:100]
    concept = params.get('concept', [''])[0].strip().lower()[:100]
    research = params.get('research', [''])[0] == '1'
    identified = params.get('identified', [''])[0] == '1'
    offset = number(params, 'offset', 0, 100000)
    limit = max(1, number(params, 'limit', 24, 50))
    # grouped=1: entries whose preferred scientific name is the same (e.g. agrimony in Culpeper and in
    # Dioscorides) come back as one item with `members`; pagination counts groups, not entries.
    grouped = params.get('grouped', [''])[0] == '1'
    page_offset, page_limit = offset, limit
    if grouped:
        offset, limit = 0, 100000
    rows = query('''MATCH (e:HistoricalEntry {snapshot_id:$snapshot})
      WHERE ($entry_id = '' OR e.id = $entry_id) AND ($book = '' OR e.book=$book) AND ($term = '' OR
        toLower(coalesce(e.name,'')) CONTAINS $term OR toLower(coalesce(e.label,'')) CONTAINS $term OR
        EXISTS { MATCH (e)-[:HAS_HISTORICAL_NAME]->(n:HistoricalName {snapshot_id:$snapshot}) WHERE toLower(coalesce(n.name,'')) CONTAINS $term } OR
        EXISTS { MATCH (e)-[:HAS_HYPOTHESIS]->(h:IdentificationHypothesis {snapshot_id:$snapshot}) WHERE toLower(coalesce(h.accepted_name,'')) CONTAINS $term OR
          EXISTS { MATCH (h)-[:HAS_NAME_RESOLUTION]->(r:TaxonomicResolution {snapshot_id:$snapshot}) WHERE toLower(coalesce(r.original_name,'')) CONTAINS $term } })
      AND ($tier='' OR EXISTS { MATCH (e)-[:HAS_DECISION]->(d:EligibilityDecision {snapshot_id:$snapshot}) WHERE d.tier=$tier })
      AND (NOT $identified OR EXISTS { MATCH (e)-[:HAS_DECISION]->(d:EligibilityDecision {snapshot_id:$snapshot}) WHERE d.tier IN ['A','B'] AND trim(coalesce(d.accepted_name,'')) <> '' })
      AND ($family='' OR EXISTS { MATCH (e)-[:HAS_HYPOTHESIS]->(h:IdentificationHypothesis {snapshot_id:$snapshot}) WHERE toLower(coalesce(h.family,'')) CONTAINS $family })
      AND ($concept='' OR EXISTS { MATCH (e)-[:HAS_CLAIM]->(:HistoricalClaim {dataset_id:$dataset})-[:HAS_MAPPING]->(:ConceptMapping {dataset_id:$dataset})-[:MAPS_TO]->(m:MedicalConcept) WHERE toLower(coalesce(m.name,'')) CONTAINS $concept })
      AND (NOT $research OR EXISTS { MATCH (e)-[:HAS_CLAIM]->(:HistoricalClaim {dataset_id:$dataset})<-[:ABOUT_CLAIM]-(:ClaimPlantUnit {dataset_id:$dataset})<-[:ASSESSES_UNIT]-(:EvidenceAssessment {dataset_id:$dataset}) })
      WITH e ORDER BY e.book, coalesce(e.name,''), e.entry_key SKIP $offset LIMIT $take
      OPTIONAL MATCH (e)-[:HAS_DECISION]->(d:EligibilityDecision {snapshot_id:$snapshot})
      OPTIONAL MATCH (d)-[:HAS_SOURCE_VALUE {field:'raw'}]->(decision_raw:SourceValue)
      WITH e, d, decision_raw
      ORDER BY e.id, CASE d.tier WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END,
        size(coalesce(d.lineages_strong, [])) DESC,
        CASE WHEN coalesce(decision_raw.p_description_congruence, 0) = 0 THEN -99 ELSE decision_raw.p_description_congruence END DESC,
        d.accepted_name
      WITH e, collect(DISTINCT d.tier) AS tiers,
        collect(DISTINCT CASE WHEN d.tier IN ['A','B'] AND trim(coalesce(d.accepted_name,'')) <> '' THEN d.accepted_name END) AS scientific_names
      RETURN e.id AS id, e.name AS name, e.book AS book, e.label AS chapter, e.entry_key AS entry_key, tiers, scientific_names,
        head(scientific_names) AS preferred_scientific_name
      ORDER BY e.book, coalesce(e.name,''), e.entry_key''',
      snapshot=ctx['snapshot'], dataset=ctx['dataset'], entry_id=entry_id, book=book, term=term, tier=tier, family=family, concept=concept, research=research, identified=identified, offset=offset, take=limit+1)
    image_path = Path(__file__).resolve().parent / 'data' / 'candidate_images.json'
    try:
        images = json.loads(image_path.read_text(encoding='utf-8')).get('images', {})
    except (OSError, ValueError):
        images = {}
    if grouped:
        groups = {}
        for row in rows:
            key = row.get('preferred_scientific_name') or row['id']
            groups.setdefault(key, []).append(row)
        ordered = list(groups.values())            # in the usual order: by each group's first entry
        page = ordered[page_offset:page_offset + page_limit]
        items = []
        for members in page:
            item = dict(members[0])
            item['members'] = [{k: m.get(k) for k in ('id', 'name', 'book', 'chapter')} for m in members] if len(members) > 1 else None
            items.append(item)
        for row in items:
            image = images.get(row.get('preferred_scientific_name'), {})
            row['image'] = image if image.get('status') == 'available' else None
        return {'items': items, 'has_more': len(ordered) > page_offset + page_limit, 'offset': page_offset, 'limit': page_limit,
                'total': len(ordered)}
    for row in rows[:limit]:
        image = images.get(row.get('preferred_scientific_name'), {})
        row['image'] = image if image.get('status') == 'available' else None
    return {'items': rows[:limit], 'has_more': len(rows) > limit, 'offset': offset, 'limit': limit}


_facets_cache = {}


def facets(ctx):
    """The families and MeSH concepts most often found among identified entries, for the Explore filters,
    plus per-book counts for the sources page. Cached per snapshot (the database is read-only)."""
    key = (ctx['snapshot'], ctx['dataset'])
    if key not in _facets_cache:
        families = query('''MATCH (e:HistoricalEntry {snapshot_id:$snapshot})-[:HAS_HYPOTHESIS]->(h:IdentificationHypothesis {snapshot_id:$snapshot})
          MATCH (h)-[:HAS_DECISION]->(d:EligibilityDecision {snapshot_id:$snapshot})
          WHERE d.tier IN ['A','B'] AND trim(coalesce(h.family,'')) <> ''
          RETURN h.family AS name, count(DISTINCT e) AS count ORDER BY count DESC, name LIMIT 300''', **ctx)
        concepts = query('''MATCH (e:HistoricalEntry {snapshot_id:$snapshot})-[:HAS_CLAIM]->(:HistoricalClaim {dataset_id:$dataset})
          -[:HAS_MAPPING]->(:ConceptMapping {dataset_id:$dataset})-[:MAPS_TO]->(m:MedicalConcept)
          WHERE trim(coalesce(m.name,'')) <> ''
          RETURN m.name AS name, count(DISTINCT e) AS count ORDER BY count DESC, name LIMIT 500''', **ctx)
        books = query('''MATCH (e:HistoricalEntry {snapshot_id:$snapshot})
          OPTIONAL MATCH (e)-[:HAS_DECISION]->(d:EligibilityDecision {snapshot_id:$snapshot}) WHERE d.tier IN ['A','B']
          WITH e, count(d) > 0 AS identified
          OPTIONAL MATCH (e)-[:HAS_CLAIM]->(c:HistoricalClaim {dataset_id:$dataset})
          RETURN e.book AS book, count(DISTINCT e) AS entries, count(DISTINCT CASE WHEN identified THEN e END) AS identified,
                 count(DISTINCT c) AS claims''', **ctx)
        _facets_cache[key] = {'families': families, 'concepts': concepts,
                              'books': {b['book']: {k: b[k] for k in ('entries', 'identified', 'claims')} for b in books}}
    return _facets_cache[key]


def entry(ctx, eid):
    rows = query('''MATCH (e:HistoricalEntry {id:$id, snapshot_id:$snapshot})-[:IN_BOOK]->(b:Book)
      OPTIONAL MATCH (e)-[:HAS_SOURCE_VALUE {field:'raw'}]->(raw:SourceValue)
      OPTIONAL MATCH (raw)-[:HAS_VALUE {field:'sections'}]->(sections:SourceValue)
      RETURN properties(e) AS entry, properties(b) AS book, raw.p_text AS historical_text,
             raw.p_intro AS introduction, raw.p_opening AS opening, raw.p_page AS page,
             sections.p_description AS description, sections.p_place AS place,
             sections.p_time AS season, sections.p_government_and_virtues AS virtues''', id=eid, **ctx)
    if not rows:
        return None
    result = rows[0]
    catalogue = entries(ctx, {'entry_id': [eid], 'identified': ['1'], 'limit': ['1']})['items']
    result['image'] = catalogue[0]['image'] if catalogue else None
    result['preferred_scientific_name'] = catalogue[0]['preferred_scientific_name'] if catalogue else None
    result['names'] = query('''MATCH (:HistoricalEntry {id:$id, snapshot_id:$snapshot})-[:HAS_HISTORICAL_NAME]->(n:HistoricalName {snapshot_id:$snapshot})
      RETURN n.name AS name, n.layer AS layer, n.quote AS quote ORDER BY layer,name''', id=eid, **ctx)
    result['candidates'] = query('''MATCH (:HistoricalEntry {id:$id, snapshot_id:$snapshot})-[:HAS_HYPOTHESIS]->(h:IdentificationHypothesis {snapshot_id:$snapshot})
      OPTIONAL MATCH (h)-[:HAS_DECISION]->(d:EligibilityDecision {snapshot_id:$snapshot})
      WITH h,d ORDER BY CASE d.tier WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END, h.accepted_name
      RETURN properties(h) AS hypothesis, properties(d) AS decision LIMIT 200''', id=eid, **ctx)
    result['claims'] = query('''MATCH (:HistoricalEntry {id:$id, snapshot_id:$snapshot})-[:HAS_CLAIM]->(c:HistoricalClaim {dataset_id:$dataset})
      OPTIONAL MATCH (c)-[:HAS_MAPPING]->(m:ConceptMapping {dataset_id:$dataset})-[:MAPS_TO]->(term:MedicalConcept)
      WITH c,collect(CASE WHEN term IS NULL THEN null ELSE {name:term.name, id:term.source_id, node_id:term.id, mapping_id:m.id, match:m.match, proposed:m.proposed, via:m.via} END) AS concepts
      RETURN properties(c) AS claim, concepts ORDER BY c.source_claim_id LIMIT 200''', id=eid, **ctx)
    return result


def candidate(ctx, hid, params):
    offset = number(params, 'offset', 0, 100000)
    rows = query('''MATCH (h:IdentificationHypothesis {id:$id, snapshot_id:$snapshot})
      OPTIONAL MATCH (h)-[:HAS_NAME_RESOLUTION]->(r:TaxonomicResolution {snapshot_id:$snapshot})
      OPTIONAL MATCH (r)-[rel:RESOLVES_TO]->(t:Taxon)
      RETURN r.id AS resolution_id, t.id AS taxon_id, r.original_name AS original_name, r.agreement AS agreement,
       r.wfo_reason AS wfo_reason,r.wcvp_reason AS wcvp_reason,r.global_names_reason AS global_names_reason,
       rel.authority AS authority,rel.accepted_name AS accepted_name,rel.rule AS rule,t.source_id AS source_id,t.release AS release
      LIMIT 100''', id=hid, **ctx)
    evidence = query('''MATCH (v:EvidenceRecord {snapshot_id:$snapshot})-[:RELATES_TO_HYPOTHESIS]->(h:IdentificationHypothesis {id:$id})
      RETURN properties(v) AS evidence ORDER BY CASE v.grade WHEN 'strong' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, v.source, v.line_number SKIP $offset LIMIT 21''', id=hid, offset=offset, **ctx)
    descriptions = query('''MATCH (h:IdentificationHypothesis {id:$id, snapshot_id:$snapshot})<-[:COMPARES_HYPOTHESIS]-(c:CandidateDescription {snapshot_id:$snapshot})<-[:HAS_CANDIDATE_COMPARISON]-(parent:DescriptionComparison {snapshot_id:$snapshot})
      OPTIONAL MATCH (c)-[:HAS_SCORE]->(s:DescriptionScore {snapshot_id:$snapshot})
      RETURN properties(c) AS comparison, parent.quotes_not_in_text AS quotes_not_in_text, collect(properties(s)) AS scores LIMIT 10''', id=hid, **ctx)
    return {'resolutions': rows, 'evidence': [x['evidence'] for x in evidence[:20]], 'has_more': len(evidence)>20, 'descriptions': descriptions}


def entry_evidence(ctx, eid, params):
    offset = number(params, 'offset', 0, 100000)
    rows = query('''MATCH (:HistoricalEntry {id:$id,snapshot_id:$snapshot})-[:HAS_EVIDENCE]->(v:EvidenceRecord {snapshot_id:$snapshot})
      RETURN properties(v) AS evidence ORDER BY CASE v.grade WHEN 'strong' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, v.source, v.line_number SKIP $offset LIMIT 21''', id=eid, offset=offset, **ctx)
    return {'items':[r['evidence'] for r in rows[:20]], 'has_more':len(rows)>20}

def entry_studies(ctx, eid):
    rows = query('''MATCH (e:HistoricalEntry {id:$id, snapshot_id:$snapshot})-[:HAS_CLAIM]->(c:HistoricalClaim {dataset_id:$dataset})
      MATCH (c)<-[:ABOUT_CLAIM]-(u:ClaimPlantUnit {dataset_id:$dataset})<-[:ASSESSES_UNIT]-(a:EvidenceAssessment {dataset_id:$dataset})-[:ASSESSES_STUDY]->(s:Study {dataset_id:$dataset})
      OPTIONAL MATCH (s)-[:HAS_SOURCE_VALUE {field:'raw'}]->(:SourceValue)-[:HAS_VALUE {field:'ema'}]->(ema:SourceValue)
      WITH DISTINCT c,u,a,s,ema
      ORDER BY CASE a.applicability WHEN 'direct' THEN 0 WHEN 'partial' THEN 1 WHEN 'indirect' THEN 2 WHEN 'unassessable' THEN 3 ELSE 4 END,
        coalesce(a.review_flag,false), s.title, a.id
      LIMIT 51
      RETURN properties(c) AS claim, u.taxon_name AS candidate, properties(a) AS assessment,
             properties(s) AS study, ema.p_page AS source_url''', id=eid, **ctx)
    return {'items':rows[:50], 'has_more':len(rows)>50}


def claim(ctx, cid, params):
    offset = number(params, 'offset', 0, 100000)
    units = query('''MATCH (c:HistoricalClaim {id:$id,dataset_id:$dataset})<-[:ABOUT_CLAIM]-(f:FullUnitRecord {snapshot_id:$snapshot,dataset_id:$full_dataset})
      OPTIONAL MATCH (f)-[:CORRESPONDS_TO_SHARED_UNIT]->(u:ClaimPlantUnit {dataset_id:$dataset})
      OPTIONAL MATCH (u)<-[:ASSESSES_UNIT]-(a:EvidenceAssessment {dataset_id:$dataset})
      RETURN f.id AS id,f.taxon_name AS candidate,f.tier AS tier,f.hypothesis_link_status AS link_status,
             f.source_id_count AS source_id_count,u.id AS shared_unit_id,count(a) AS assessments ORDER BY candidate LIMIT 100''', id=cid, **ctx)
    studies = query('''MATCH (c:HistoricalClaim {id:$id,dataset_id:$dataset})<-[:ABOUT_CLAIM]-(u:ClaimPlantUnit {dataset_id:$dataset})
      MATCH (u)<-[:ASSESSES_UNIT]-(a:EvidenceAssessment {dataset_id:$dataset})-[:ASSESSES_STUDY]->(s:Study {dataset_id:$dataset})
      OPTIONAL MATCH (u)-[:USES_HYPOTHESIS]->(h:IdentificationHypothesis {snapshot_id:$snapshot})
      WITH u,a,s,h ORDER BY s.title SKIP $offset LIMIT 21
      OPTIONAL MATCH (a)-[:HAS_EXCERPT]->(x:EvidenceExcerpt {dataset_id:$dataset})
      OPTIONAL MATCH (s)-[:HAS_SOURCE_VALUE {field:'raw'}]->(:SourceValue)-[:HAS_VALUE {field:'ema'}]->(ema:SourceValue)
      RETURN properties(u) AS unit, h.accepted_name AS candidate, properties(a) AS assessment,
             properties(s) AS study, ema.p_page AS source_url, collect({field:x.field,text:x.text}) AS excerpts''', id=cid, offset=offset, **ctx)
    related = query('''MATCH (c:HistoricalClaim {id:$id,dataset_id:$dataset})<-[:GROUPS_CLAIM]-(g:ClaimLink {dataset_id:$dataset})-[:GROUPS_CLAIM]->(other:HistoricalClaim)
      WHERE other.book <> c.book AND other.dataset_id=$dataset
      MATCH (e:HistoricalEntry)-[:HAS_CLAIM]->(other)
      RETURN DISTINCT e.id AS entry_id,e.name AS name,e.book AS book,e.label AS chapter,
         other.quote AS quote,other.claim_text AS claim,g.species AS recorded_species,g.mesh_name AS recorded_concept LIMIT 30''', id=cid, **ctx)
    return {'studies': studies[:20], 'has_more':len(studies)>20, 'related':related, 'units':units}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            ctx = context()
            parts = parsed.path.strip('/').split('/')
            params = parse_qs(parsed.query)
            if parts == ['api','entries']:
                data = entries(ctx, params)
            elif len(parts) == 4 and parts[:2] == ['api','entries'] and parts[3] == 'studies':
                data = entry_studies(ctx, identifier(parts[2]))
            elif len(parts) == 4 and parts[:2] == ['api','entries'] and parts[3] == 'evidence':
                data = entry_evidence(ctx, identifier(parts[2]), params)
            elif len(parts) == 3 and parts[:2] == ['api','entries']:
                data = entry(ctx, identifier(parts[2]))
            elif len(parts) == 3 and parts[:2] == ['api','candidates']:
                data = candidate(ctx, identifier(parts[2]), params)
            elif len(parts) == 3 and parts[:2] == ['api','claims']:
                data = claim(ctx, identifier(parts[2]), params)
            elif parts == ['api','facets']:
                data = facets(ctx)
            elif parts == ['api','health']:
                data = {'status':'ok', 'snapshot':ctx['snapshot']}
            else:
                return self.send(404, {'error':'Not found'})
            return self.send(200 if data is not None else 404, data if data is not None else {'error':'Not found'})
        except ValueError as exc:
            return self.send(400, {'error':str(exc)})
        except Exception as exc:
            print(f'API error: {type(exc).__name__}: {exc}', flush=True)
            return self.send(503, {'error':'The research database is unavailable or its snapshot is ambiguous.'})

    def send(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    port = int(os.environ.get('API_PORT','8787'))
    print(f'EthnoTrace read-only API listening on http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1',port), Handler).serve_forever()

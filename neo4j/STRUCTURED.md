# Structured EthnoTrace graph

`ethnotrace-clean` is built separately from the earlier `ethnotrace` database. Its domain nodes expose the fields needed for scientific filtering and display; no serialized JSON is stored in the `raw_json`, `geography_json`, or similar properties. Historical identifications, model assessments and taxonomic assertions remain source-specific and are not upgraded to verified scientific facts.

## Recovering source details

`(entity)-[:HAS_SOURCE_VALUE {field}]->(v:SourceValue)` preserves each former JSON-valued property as a tree. Object nodes have `kind = 'object'`, `keys` in source order, `scalar_keys`, and native scalar properties named `p_<source key>`. Other fields are connected with `HAS_VALUE {field}`. Array nodes have `kind = 'array'`; homogeneous primitive arrays use the native `values` list, and other arrays use ordered `HAS_VALUE {position}` edges. Empty arrays and objects are explicit; null is a `SourceValue` with `kind = 'null'`. This preserves values, field names, types, order, and the distinction between null and missing. It preserves JSON data, not the original bytes or whitespace.

Scientific JSON, JSONL and derived CSV outputs are additionally represented as `SourceDocument` nodes with path and SHA-256, with one ordered `HAS_RECORD` per document/row. CSV headers are retained as an ordered `columns` list and rows as ordered string lists; values are not silently converted. Their records use the same source-value tree. This includes the other recorded Stage 3 runs without treating them as current findings. The original API caches, publisher texts and complete model conversations remain external files; their recorded file paths and hashes are retained where provided by the source data. A file path is a local reference, not a guarantee the file will exist on another machine.

## Query examples

```cypher
// Current project botanical identification candidates.
MATCH (e:HistoricalEntry {book: 'culpeper', entry_key: 'carrots'})-[:HAS_HYPOTHESIS]->(h)
OPTIONAL MATCH (h)-[:HAS_DECISION]->(d:EligibilityDecision)
RETURN e.name, h.accepted_name, h.family, h.decided_by, d.tier, d.rules, d.caveats;
```

```cypher
// Recorded compatibility, review flags and source provenance for an assessment.
MATCH (a:EvidenceAssessment)-[:ASSESSES_STUDY]->(s:Study)
WHERE a.review_flag = true
RETURN s.title, a.finding, a.applicability, a.species_match, a.condition_match,
       a.unknowns, a.review_status, a.raw_response_file LIMIT 25;
```

```cypher
// Find the source files imported to the structured value archive.
MATCH (d:SourceDocument) RETURN d.path, d.status, d.sha256 ORDER BY d.path;
```

## Recount the graph

The following read-only Neo4j Browser query reproduces the per-book counts in the main README for a selected snapshot and shared dataset. Replace the snapshot parameter when examining a different build. If multiple matching imports exist, select the intended dataset explicitly rather than combining versions.

```cypher
:param snapshot => 'cbb213486fd7894eb8a0c7e900136ded38e931854119c297690d1af7fd6e9cdc';

MATCH (d:DatasetImport {snapshot_id: $snapshot, kind: 'claims_and_stage3_shared'})
MATCH (:DatasetImport {snapshot_id: $snapshot, kind: 'full_unit_source_records'})-[:USES_CLAIMS_FROM]->(d)
MATCH (e:HistoricalEntry {snapshot_id: $snapshot})
OPTIONAL MATCH (e)-[:HAS_DECISION]->(decision:EligibilityDecision {snapshot_id: $snapshot})
WHERE decision.tier IN ['A', 'B']
WITH d, e, count(decision) > 0 AS has_candidate
OPTIONAL MATCH (e)-[:HAS_CLAIM]->(claim:HistoricalClaim {dataset_id: d.id})
RETURN e.book AS book, count(DISTINCT e) AS historical_entries,
       count(DISTINCT CASE WHEN has_candidate THEN e END) AS entries_with_A_or_B,
       count(DISTINCT claim) AS linked_claims
ORDER BY book;
```

The result counts distinct historical entries, entries with at least one A/B decision, and linked historical claims. It does not count verified identifications or clinically validated treatments.

## Rebuild

Prepare a fresh version 2 snapshot with `prepare.py`; this refuses to overwrite its output. Create a new, empty Neo4j database. With `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` set, run:

```sh
neo4j/.venv/bin/python -B neo4j/load_structured.py /path/to/snapshot.jsonl --database YOUR_NEW_DATABASE
neo4j/.venv/bin/python -B neo4j/archive_scientific_sources.py --database YOUR_NEW_DATABASE
```

To add a separate snapshot to an existing structured graph, prepare a new snapshot and add `--append-snapshot` to the first command. This duplicates snapshot-scoped data and can take substantial space and time. The existing build remains intact; an interrupted build stays marked `loading` and can be resumed with the same command and inputs. The API selects the most recently completed dated build by default; set `ETHNOTRACE_SNAPSHOT` and restart the API to choose a particular snapshot.

Without `--append-snapshot`, the first command refuses an unrelated or completed non-empty database and can resume the same interrupted build. The second records each file's import status; rerunning it uses deterministic IDs. Import is batched, so a failed or interrupted operation can leave a partial database; check the build and source-document statuses before using it. The input archive covers scientific `.json`, `.jsonl`, and derived `.csv` files under the pipeline directories and excludes API-cache directories and external downloaded CSV datasets. It does not ingest external archive files or every document.

The three-book snapshot includes Shennong source records, candidates, decisions, claims, MeSH mappings, full unit source rows, and the saved Shennong study subset. The original assessment data is preserved; where its top-level status incorrectly says a person corrected facts but the correction explicitly records Claude-only review, the display property says AI-only. This does not imply human validation.

Identification hypotheses and full-unit source records may overlap with shared units. Do not sum them as though each were an independent claim or study. Existing source limitations and validation flags remain relevant even after restructuring.

# EthnoTrace

EthnoTrace connects historical medicinal texts with proposed botanical identifications, historical claims and selected modern research. It preserves source evidence and uncertainty so the connections can be inspected. Plant identifications are hypotheses; historical claims and AI-assisted assessments are not proof of medical effectiveness.

## Start here

- [Run the website and local API](Makeathon_UI/README.md) — setup, database connection and frontend.
- [Prepare Vercel and Render deployment](DEPLOYMENT.md) — hosted configuration and limitations.
- [Understand the pipeline and files](#repository-guide) — follow the data through the project.
- [Run the offline tests](tests/README.md) — Python 3.10 or newer.
- [Inspect the graph and import process](neo4j/README.md) — schema, snapshots and Cypher.
- [Check missing downloads and caches](MISSING_FILES.md) — some inputs are distributed separately and not in Git.
- [Review data sources and licences](DATA_SOURCES.md).

## Repository guide

| Folder | Purpose |
| --- | --- |
| [historical_texts](historical_texts/README.md) | Source texts, extracted entries and historical reference lookups. |
| [common_name_sources](common_name_sources/README.md) | Common-name and historical-name candidate sources. |
| [scientific_name_sources](scientific_name_sources/README.md) | Taxonomic authority lookups and reconciliation inputs. |
| [reference_sources](reference_sources/README.md) | Dictionary, historical and medical terminology reference material. |
| [matching](matching/README.md) | Candidate aggregation, reconciliation, geography and eligibility results. |
| [description_sources](description_sources/README.md) | Modern descriptions and historical-to-modern comparisons. |
| [claims](claims/README.md) | Historical medicinal claims, quotations and MeSH mappings. |
| [stage3](stage3/README.md) | Selected modern study retrieval and claim–study assessments. |
| [neo4j](neo4j/README.md) | Versioned graph schema, importers and queries. |
| [Makeathon_UI](Makeathon_UI/README.md) | Website, local API and interface tests. |
| [tests](tests/README.md) | Offline pipeline and graph contract tests. |
| [reports](reports/README.md) | Space for local investigation reports. |

The main flow is **historical texts → candidate evidence → taxonomic reconciliation and eligibility → claims and selected research → Neo4j → website**. Description comparisons and individual source availability vary by book; the Shennong classic has no botanical description comparison in the current pipeline. An accepted taxonomic name does not prove a historical identification.

## Books
- Culpeper, *The Complete Herbal* (1653) · Dioscorides, *De materia medica* (1st c., Wellmann's Greek) ·
  the *Shennong Bencao Jing* (1st-2nd c., Sun Xingyan's reconstruction, classical Chinese; added 2026-11-06).
  The books share the broader workflow, with book-specific sources and limitations; see [eligibility rules](matching/ELIGIBILITY_RULES.md).

## Open issues
- **Shennong: 2 "direct" Stage 3 results need a person.** Grape juice for strength (an athletes' trial, result
  inconclusive) and red peony root for abdominal pain (a pancreatitis trial: a related condition, not the
  same). Left as the model answered.
- **Stage 3 pilot review is provisional.** It was done in haste and must be redone by a person
  before any Stage 3 result is reported. See `stage3/review/README.md`.
- **Stage 3 batch size and repeat runs.** Later sets use 32 pairs per prompt; this was not tested against
  the pilot's 8. Each prompt version was run once; repeated runs (ablation) were not done for time.
  See `stage3/EVIDENCE_RULES.md`.

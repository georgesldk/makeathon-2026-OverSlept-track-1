# EthnoTrace

EthnoTrace connects historical medicinal texts with proposed botanical identifications, historical claims and selected modern research. It preserves source evidence and uncertainty so the connections can be inspected. Plant identifications are hypotheses; historical claims and AI-assisted assessments are not proof of medical effectiveness.

**Explore the prototype:** [ethnotrace.vercel.app](https://ethnotrace.vercel.app) · [API health and selected snapshot](https://ethnotrace-api.onrender.com/api/health)

## Contents

- [Project and demo](#what-ethnotrace-does)
- [Limitations & availability](#limitations--availability)
- [Results and Neo4j graph](#current-graph-verified-snapshot-counts)
- [Pipeline and implementation](#pipeline-from-historical-texts-to-the-interface)
- [Setup and repository guide](#start-here)
- [Historical works and editions](#books-and-editions)
- [Generative AI](#use-of-generative-ai) · [Licence](#licence) · [Open issues](#open-issues)

## What EthnoTrace does

EthnoTrace brings historical medicinal texts, possible modern botanical identifications, medicinal claims, medical terminology and selected modern research into a connected research interface. Users can search a historical entry, read its source passage, inspect candidate plants and their evidence, explore claims and research assessments, and follow relationships in an interactive knowledge map. The atlas provides geographic context for proposed identifications.

The unit of exploration is a **historical entry**, not necessarily a uniquely identified plant. A single entry may have several candidates or none, and entries can describe non-plant material. A modern scientific name is a proposed identification; taxonomic acceptance does not establish that the historical author meant that species. A historical claim records an author's statement, not evidence of therapeutic benefit.

The expert-review feature is an explicitly labelled **interface demonstration**. Its sample comments are placeholders, not expert reviews. A visitor can preview a comment locally, but it is not submitted or saved and disappears on leaving the page or refreshing.

## Limitations & availability

**Expert review needed:** We are not domain experts in botany, historical medicine, or clinical research and are not in a position to independently validate these results. EthnoTrace is a research prototype designed to make sources and proposed connections traceable for qualified experts to examine. Its outputs should not be used as medical advice or treated as validated findings.

**Neo4j hosting:** The graph is hosted for two weeks starting **7 November 2026**, until **21 November 2026**. If access is needed afterwards, contact the project team to request a database dump. The dump is **over 1.2 GB**.

**Reproducibility and coverage:** Some inputs, API caches and model replies are distributed separately; see [MISSING_FILES.md](MISSING_FILES.md). Historical extraction, candidate identification and claim–study assessments can contain errors. The Stage 3 pilot review is provisional; see [open issues](#open-issues).

## Current graph: verified snapshot counts

The table below comes from the live application's read-only [`/api/facets`](https://ethnotrace-api.onrender.com/api/facets) response, checked on **8 November 2026**. The selected snapshot reported by `/api/health` was `cbb213486fd7894eb8a0c7e900136ded38e931854119c297690d1af7fd6e9cdc`. Counts are for this snapshot and the claims dataset selected by the API, not all snapshots in the database. They can change after a rebuild.

| Historical source | Historical entries | Entries with at least one A/B candidate | Linked historical claims |
| --- | ---: | ---: | ---: |
| Culpeper | 327 | 275 | 5,202 |
| Dioscorides | 823 | 401 | 3,832 |
| Shennong | 359 | 199 | 1,419 |
| **Total** | **1,509** | **875** | **10,453** |

These are counts of entries and extracted claim records, not counts of unique species, medically effective remedies or independently validated identifications. An entry can have multiple candidates and claims. An A/B candidate is a pipeline classification, not expert confirmation. Claims include historical interpretations, potentially including non-medical categories; they should not all be described as validated medicinal effects.

### What is represented in Neo4j

The structured graph contains domain records and the relationships needed to trace them, including:

| Graph record | What it represents |
| --- | --- |
| `Book`, `HistoricalEntry`, `HistoricalName` | Editions, historical entries, names and source context. |
| `IdentificationHypothesis`, `EligibilityDecision` | Proposed botanical candidates and their A/B/X decisions, reasons and caveats. |
| `EvidenceRecord`, `EvidenceSource` | Evidence rows, sources, lineages and links to candidates where they can be made unambiguously. |
| `TaxonomicResolution`, `Taxon` | Authority-specific name resolutions and qualified taxon identities; accepted taxonomy is not proof of historical identity. |
| `DescriptionComparison`, `CandidateDescription`, `DescriptionScore` | Recorded botanical-description comparisons, feature scores and supporting quotations where available. |
| `HistoricalClaim`, `ConceptMapping`, `MedicalConcept` | Extracted claims, their quotations and proposed medical terminology mappings, including MeSH. |
| `ClaimLink`, `ClaimPlantUnit`, `FullUnitRecord` | Inferred cross-book groupings and claim–plant source units; groupings do not prove remedies are equivalent. |
| `Study`, `EvidenceAssessment`, `EvidenceExcerpt` | Selected research records, claim–study assessments and recorded supporting excerpts. |
| `StructuredBuild`, `DatasetImport`, `SourceDocument`, `SourceValue` | Build and dataset provenance, source-file references and structured preservation of imported source values. |

Not every entry has every type of record. Unmatched or ambiguous evidence and hidden candidates are retained rather than arbitrarily assigned. The graph preserves structured source values, while raw API caches, complete conversations and publisher texts may remain in external files. See [the structured graph documentation](neo4j/STRUCTURED.md) for details and [the graph model](neo4j/MODEL.md) for relationships.

### Recount the graph

The website's [`/api/facets`](https://ethnotrace-api.onrender.com/api/facets) gives the per-book counts above, and [`/api/health`](https://ethnotrace-api.onrender.com/api/health) identifies the active snapshot. In Neo4j Browser, set `$snapshot` to the desired completed snapshot and run this read-only query to inspect its records by source:

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

If more than one matching dataset import exists, select the intended dataset explicitly rather than combining versions. Additional read-only examples and graph integrity checks are in [neo4j/STRUCTURED.md](neo4j/STRUCTURED.md) and [neo4j/verify_graph.py](neo4j/verify_graph.py). The graph contains more record types than these three counts; their totals are not asserted here without a snapshot-scoped query.

## Pipeline: from historical texts to the interface

```text
Historical sources and passages
  → historical entries and names
  → candidate discovery and source evidence
  → taxonomic reconciliation and geography
  → botanical description comparison, where available
  → rule-based A/B/X eligibility decisions
  → historical claims, quotations and medical-concept mappings
  → selected modern research and claim–study assessments
  → snapshot-scoped Neo4j graph → API and website
```

The exact inputs and coverage vary by book and stage. Later steps use the saved outputs of earlier steps; the diagram does not imply that every historical entry was assessed at every stage.

### 1. Historical sources and extraction

- **Culpeper:** [extract_herbs.py](historical_texts/culpeper/extract_herbs.py) processes Project Gutenberg eBook #49513, a transcription of an 1850 edition, into entries and recorded names; [validate_herbs.py](historical_texts/culpeper/validate_herbs.py) checks extraction.
- **Dioscorides:** [extract_wellmann.py](historical_texts/dioscorides/extract_wellmann.py) processes the First1KGreek encoding of Wellmann's 1906–1914 Greek edition into chapters; the extraction and [historical dictionary lookups](historical_texts/dioscorides/README.md) have separate checks and limitations.
- **Shennong:** [extract_sun.py](historical_texts/shennong/extract_sun.py) processes Sun Xingyan and Sun Fengyi's 1799 reconstruction, distinguishing its textual layers. This is a later reconstruction, not an untouched original; names and translations require expert interpretation.

The extracted records preserve historical text and source context. Extraction and validation checks do not guarantee that every headword or association is correct. See [historical_texts](historical_texts/README.md) and [DATA_SOURCES.md](DATA_SOURCES.md).

### 2. Discover and aggregate botanical candidates

Historical names are searched in common-name and historical reference sources, including GBIF, Wikidata, ChecklistBank, iNaturalist, Dr. Duke's and Greek and Latin dictionaries. Matches produce candidate names and evidence with source provenance. Matching and aggregation distinguish stronger exact or passage-specific evidence from weaker matches; see [matching rules](matching/MATCHING_RULES.md).

Related records may share an upstream lineage. The eligibility rules group certain sources to reduce double counting, but source independence and historical associations remain subject to review. Taxonomic authorities are used to check names, not counted as independent proof of historical identity.

### 3. Reconcile scientific names and geography

[resolve_scientific.py](matching/resolve_scientific.py) reconciles candidate names using available authority outputs, including World Flora Online, WCVP, Global Names and IPNI. Resolutions preserve source information and disagreements. Authority-qualified identifiers allow supported links between records; matching name strings alone do not establish shared taxon identity.

[geography.py](matching/geography.py) records whether available distribution information is compatible with the historical context. Modern distributions are context, not proof of historical presence or absence. See [eligibility and geography rules](matching/ELIGIBILITY_RULES.md).

### 4. Compare descriptions and classify candidates

Where historical and modern descriptions are available, [description_check.py](description_sources/check/description_check.py) prepares and imports AI-assisted comparisons of features such as leaves, flowers and habitat. Supporting quotations and scores are retained. Coverage varies, and the current Shennong pipeline has no botanical-description comparison; missing information should not be mistaken for a poor fit.

[eligibility.py](matching/eligibility.py) applies documented rules to evidence, taxonomy, geography and available description comparisons:

- **A:** meets the stronger pipeline criteria.
- **B:** remains a possible identification with recorded caveats.
- **X:** does not meet the current requirements for display as an A/B candidate; it is retained in the data.

These categories describe the pipeline's decisions, not independently verified scientific conclusions. See [ELIGIBILITY_RULES.md](matching/ELIGIBILITY_RULES.md).

### 5. Extract historical claims and map terminology

The [claims pipeline](claims/CLAIMS_METHOD.md) uses AI-assisted extraction to structure statements from the texts, with historical quotations and translations where recorded. It proposes modern medical concepts such as MeSH and applies checks to source quotations and terminology. Mappings can be approximate or absent; a MeSH mapping does not prove that an ancient and a modern medical concept are identical.

The [claim links](claims/links.json) connect selected claims across books using recorded plant and concept criteria. They are inferred groupings, not statements that the historical remedies or preparations are equivalent.

### 6. Retrieve and assess selected modern research

The [Stage 3 pipeline](stage3/README.md) builds selected claim–plant units, retrieves research from sources including PubMed, Europe PMC, ClinicalTrials.gov and EMA herbal monographs, and uses AI-assisted extraction plus predefined rules to record how a source relates to a claim. Assessments can include study type, applicability, findings, limitations and excerpts where present.

Research coverage is selected and incomplete. A registry entry, laboratory result, traditional-use monograph or related-condition study does not by itself establish clinical efficacy. The pilot review is provisional and requires human review; see [Stage 3 rules and limits](stage3/EVIDENCE_RULES.md) and [review status](stage3/review/README.md).

### 7. Import and explore

The [Neo4j importers](neo4j/STRUCTURED.md) create versioned graph records from pipeline outputs. `StructuredBuild` and `DatasetImport` records identify the selected snapshot and datasets, reducing the risk of mixing versions. The read-only Python API in [Makeathon_UI/server.py](Makeathon_UI/server.py) serves the React and TypeScript frontend.

The website provides a searchable catalogue, entry pages, historical passages, identification evidence, claims and research, a knowledge map and an atlas. Candidate images, when available, illustrate a proposed modern plant and include source and licence information; they do not prove the historical identification. See [the application guide](Makeathon_UI/README.md).

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

## Use of generative AI

Generative AI assisted the project. **OpenAI Codex and Anthropic Claude** were used during development, including work on code, documentation and reviews. **Google Gemini** was used in parts of the research pipeline, including extraction, translation and comparison tasks. AI-assisted reviews and outputs are not a substitute for independent domain-expert validation.

## Licence

The project's original software is available under the [MIT License](LICENSE). This does not change the rights or terms of third-party material, including historical texts and transcriptions, datasets and derived data, photographs, icons, or software dependencies. Their respective licences and attribution requirements continue to apply; see [DATA_SOURCES.md](DATA_SOURCES.md) and any notices provided with the material. Check the applicable source terms before redistributing data or assets.

## Books and editions

The historical period of a work and the edition processed by the pipeline are different:

| Historical work | Period of the work | Edition or transcription processed |
| --- | --- | --- |
| Nicholas Culpeper, *The Complete Herbal* | Seventeenth century; associated with 1653. | [Project Gutenberg eBook #49513](https://www.gutenberg.org/ebooks/49513), a digital transcription of the **1850 Thomas Kelly edition**. The processed text is not a direct transcription of the 1653 edition. |
| Dioscorides, *De materia medica* | First century CE. | The **First1KGreek TEI transcription of Max Wellmann's Greek edition**, published across 1906–1914. |
| *Shennong Bencao Jing* | Traditionally associated with the Han period, approximately first–second century CE. | The **1799 reconstruction by Sun Xingyan and Sun Fengyi**, from the specified Chinese Wikisource transcription; it is a later reconstruction rather than the original historical text. Added to this project on 6 November 2026. |

The books share the broader workflow, with book-specific sources and limitations; see [data sources](DATA_SOURCES.md) and [eligibility rules](matching/ELIGIBILITY_RULES.md).

## Open issues
- **Shennong: 2 "direct" Stage 3 results need a person.** Grape juice for strength (an athletes' trial, result
  inconclusive) and red peony root for abdominal pain (a pancreatitis trial: a related condition, not the
  same). Left as the model answered.
- **Stage 3 pilot review is provisional.** It was done in haste and must be redone by a person
  before any Stage 3 result is reported. See `stage3/review/README.md`.
- **Stage 3 batch size and repeat runs.** Later sets use 32 pairs per prompt; this was not tested against
  the pilot's 8. Each prompt version was run once; repeated runs (ablation) were not done for time.
  See `stage3/EVIDENCE_RULES.md`.

# Stage 3 data contract (draft v0.1, 5 Nov 2026)

The fixed record formats Stage 3 passes between steps, so retrieval
(StudyRecord) and assessment (EvidenceAssessment) can be built
separately and still fit together. It follows `OverSlept_Stage3_Plan_FINAL.md`.

**Status:** draft for agreement. Nothing here is implemented yet.
The examples use **real Stage 1 and Stage 2 records**. Study fields are
shown as `<placeholders>`: **no publication is invented**. They get filled
from real retrieval.


## 0. Conventions

- **Format:** JSON Lines (one record per line), UTF-8.
- **`"unknown"` vs `null`:**
  - `"unknown"` means "the source doesn't say".
  - `null` means "not applicable" or "not yet filled".
  - An empty string is never used to mean unknown.
- **Excerpts:**
  - Every non-`unknown` value the model extracts from a text carries an
    exact excerpt, checked by code against the stored text.
  - Values taken from structured metadata (e.g. PubMed publication
    types) cite the field instead (`"from_metadata": "PublicationType"`).
- **Times:** ISO 8601 with time zone (`2026-11-05T17:40:00+02:00`).
- **Stage 1 and Stage 2 files are read-only inputs.** Every Stage 3
  record stores the commit they came from.
- **Every record has `schema_version`** (`"0.1"` now). Changing a field's
  meaning means a new version, never a silent change.


## 1. IDs

| ID | Format | Example |
|---|---|---|
| `claim_id` | `<book>:<entry>:c<NN>` (exists, Stage 1) | `culpeper:carrots:c05` |
| `identification_id` | `<book>:<entry>:<wfo_id>`: one proposed plant for one entry. Uses the WFO ID, which every resolved candidate already has, so it survives a renamed species | `culpeper:carrots:wfo-0000638442` |
| `unit_id` | `<claim_id>|<wfo_id>` | `culpeper:carrots:c05|wfo-0000638442` |
| `study_id` | `pmid:<n>` · `pmcid:PMC<n>` · `doi:<doi>` · `nct:NCT<n>` · `ema:<monograph id>`. The first available identifier, in that order | `pmid:<PMID>` |
| `assessment_id` | `<unit_id>|<study_id>|v<assessment_version>` | `culpeper:carrots:c05|wfo-0000638442|pmid:<PMID>|v1` |


## 2. HistoricalClaimStudyUnit (one claim × one proposed plant)

Built by code from Stage 1 and Stage 2. No AI, nothing new is added.

| Field | Source | Notes |
|---|---|---|
| `unit_id`, `claim_id`, `identification_id` | §1 | |
| `book`, `edition`, `entry`, `entry_label` | claims.json | edition: "Gutenberg #49513" or "Wellmann 1906-14, First1KGreek" |
| `quote`, `quote_language`, `translation` | claims.json | translation only for Greek; it's the model's, flagged as such |
| `claim_text` | claims.json `claim` | the modern restatement |
| `relation`, `kind` | claims.json | |
| `condition_concepts`, `action_concepts` | claims.json `mesh`, split by MeSH branch: C/F = condition, D27/G = action | each `{ui, name, match}` |
| `use_groups` | MeSH → 21-group map (3.1) | list; may be empty, with `use_group_note` for unmapped cases |
| `plant_part`, `preparation`, `route` | claims.json | `"unknown"` if the book doesn't say |
| `taxon` | eligibility.json | `{accepted_name, wfo_id, wcvp_id, family}` |
| `identification` | eligibility.json | `{tier: "A"|"B", rules: [...], caveats: [...], description_check: "fits"|...}` |
| `shared_with` | links.json | the other books' claim_ids for the same plant + MeSH term (historical agreement only) |
| `inputs` | | `{stage1_commit, stage2_commit, built_at}` |

**Example 1** (real data, tier A):
```json
{"schema_version": "0.1",
 "unit_id": "culpeper:carrots:c05|wfo-0000638442",
 "claim_id": "culpeper:carrots:c05",
 "identification_id": "culpeper:carrots:wfo-0000638442",
 "book": "culpeper", "edition": "Project Gutenberg #49513", "entry": "carrots", "entry_label": "Carrots",
 "quote": "women’s courses", "quote_language": "en", "translation": null,
 "claim_text": "Promotes menstrual flow", "relation": "promotes", "kind": "medical",
 "condition_concepts": [],
 "action_concepts": [{"ui": "D008600", "name": "Menstruation-Inducing Agents", "match": "close"},
                     {"ui": "D008598", "name": "Menstruation", "match": "exact"}],
 "use_groups": ["<gynaecology group code, from the 3.1 map>"],
 "plant_part": "whole herb", "preparation": "unknown", "route": "internal",
 "taxon": {"accepted_name": "Daucus carota L.", "wfo_id": "wfo-0000638442", "wcvp_id": "2757936", "family": "Apiaceae"},
 "identification": {"tier": "A", "rules": ["A1","A2","A3","A4a","A5","A6"], "caveats": [], "description_check": "fits"},
 "shared_with": ["dioscorides:3.52:c01", "dioscorides:3.72:c02"],
 "inputs": {"stage1_commit": "144a289", "stage2_commit": "144a289", "built_at": "<time>"}}
```
Note: Stage 1 stored `preparation: ""` for this claim, and the unit turns
that into `"unknown"`. Culpeper's quote is very short, so this claim is a
good test of "the book is vague".

**Example 2** (real data, tier B; the uncertainty must travel):
```json
{"schema_version": "0.1",
 "unit_id": "dioscorides:3.72:c02|wfo-0000638442",
 "claim_id": "dioscorides:3.72:c02",
 "identification_id": "dioscorides:3.72:wfo-0000638442",
 "book": "dioscorides", "edition": "Wellmann 1906-14, First1KGreek TEI", "entry": "3.72", "entry_label": "δαῦκος",
 "quote": "πινόμενον δὲ ἐμμήνων ... ἀγωγὸν", "quote_language": "grc",
 "translation": "drunk it promotes menses",
 "claim_text": "promotes menstruation", "relation": "promotes", "kind": "medical",
 "condition_concepts": [],
 "action_concepts": [{"ui": "D008600", "name": "Menstruation-Inducing Agents", "match": "exact"}],
 "use_groups": ["<gynaecology group code>"],
 "plant_part": "seed", "preparation": "unknown", "route": "internal",
 "taxon": {"accepted_name": "Daucus carota L.", "wfo_id": "wfo-0000638442", "wcvp_id": "2757936", "family": "Apiaceae"},
 "identification": {"tier": "B", "rules": ["B5"], "caveats": ["identified by a dictionary only"], "description_check": "fits"},
 "shared_with": ["culpeper:carrots:c05"],
 "inputs": {"stage1_commit": "144a289", "stage2_commit": "144a289", "built_at": "<time>"}}
```
A third real unit to test routes: `dioscorides:3.52:c01` (σταφυλῖνος,
tier A), "Its fruit, taken as a drink **or applied as a pessary**".
There, part = fruit, and preparation and route cover two forms. The unit
should keep both: `route: ["internal", "vaginal"]`. So **route and
preparation are lists**.


## 3. StudyRecord (one source item; retrieval, no AI)

**Not a support classification:** it only records what was found and how.

| Field | Notes |
|---|---|
| `study_id`, `other_ids` | §1; `other_ids` = `{pmid, pmcid, doi, nct}` as available |
| `source` | `PubMed` · `EuropePMC` · `ClinicalTrials.gov` · `EMA` |
| `title`, `journal`, `publication_date` | from source metadata |
| `publication_types` | from source metadata (PubMed PublicationType), never inferred |
| `taxa_mentioned` | names found in title, abstract or MeSH by code, each with where it was found |
| `mesh_headings` | the source's own indexing |
| `text` | `{kind: "abstract"|"full_text"|"registry_record"|"monograph", locator, sha256, licence_note}`; the text itself is stored in `stage3/texts/<study_id>.txt` where permitted |
| `query` | `{string, database, run_at, result_count, rank_in_results}` |
| `found_for_units` | the unit_ids this search was run for |
| `screening` | `{decision: "kept"|"rejected", reason, by: "code"|"<person>", at}`: title/abstract screening, with the reason |
| `duplicates_merged` | IDs merged into this record |
| `retrieved_at`, `schema_version` | |

**Example** (structure only; the fields marked `<…>` come from a real search):
```json
{"schema_version": "0.1",
 "study_id": "pmid:<PMID>", "other_ids": {"pmid": "<PMID>", "pmcid": "<PMCID or null>", "doi": "<DOI or null>", "nct": null},
 "source": "PubMed", "title": "<title>", "journal": "<journal>", "publication_date": "<YYYY-MM-DD>",
 "publication_types": ["<from PubMed metadata>"],
 "taxa_mentioned": [{"name": "Daucus carota", "where": "title"}],
 "mesh_headings": ["<from PubMed>"],
 "text": {"kind": "abstract", "locator": "stage3/texts/pmid_<PMID>.txt", "sha256": "<hash>", "licence_note": "abstract, PubMed"},
 "query": {"string": "(\"Daucus carota\"[MeSH Terms] OR \"Daucus carota\"[tiab]) AND (\"Menstruation-Inducing Agents\"[MeSH Terms] OR menstruation[tiab])",
           "database": "pubmed", "run_at": "<time>", "result_count": "<n>", "rank_in_results": "<k>"},
 "found_for_units": ["culpeper:carrots:c05|wfo-0000638442", "dioscorides:3.52:c01|wfo-0000638442"],
 "screening": {"decision": "kept", "reason": "<why>", "by": "code", "at": "<time>"},
 "duplicates_merged": [], "retrieved_at": "<time>"}
```


## 4. EvidenceAssessment (one unit × one study; AI extraction + code rules)

### 4.1 Extracted by the model (fields only, never a verdict)

| Field | Values |
|---|---|
| `relevance` | `direct` · `related` · `different_question` · `not_about_the_plant` · `unclear` |
| `evidence_type` | `systematic_review` · `human_rct` · `human_other` · `animal` · `in_vitro` · `traditional_use_document` · `other` · `unknown` |
| `compatibility.{species, condition, therapeutic_action, plant_part, preparation, route}` | each `{value: same|related|different|unknown, study_says: "<what the study reports>"}` |
| `compatibility.{dose, population, model}` | optional, same shape |
| `outcome` | `{value: positive|negative|mixed|inconclusive|not_reported|unclear, endpoint, comparator, interpretable: yes|no|unknown}` |
| `excerpts` | one per non-unknown field: `{field, text, start, end}` |

**Rules for the model** (in the prompt):
- Never give an overall verdict.
- `unknown` is allowed and needs no excerpt.
- A finding must come from **reported results**, not from introduction
  or background sentences.

### 4.2 Checked and derived by code

| Field | Notes |
|---|---|
| `validation` | `{schema_ok, excerpts_checked: n, excerpts_failed: [field…], fields_voided: [field…]}`: a failed excerpt voids its field (set to `unknown`) |
| `applicability` | `direct` · `partial` · `indirect` · `not_relevant` · `unassessable` |
| `finding` | `positive` · `negative` · `mixed` · `inconclusive` · `not_reported` · `unclear` |
| `rules_applied` | every S3 rule that fired, in order, e.g. `["S3-3","S3-6","S3-7"]` |
| `modifiers` | e.g. `["preclinical_animal"]`, `["possible_historical_identification"]`, `["different_preparation"]` |
| `mismatches`, `unknowns` | lists of compatibility fields |
| `badge` | descriptive text built from the fields, e.g. `"Human RCT · Partial · Negative"`; no grades, no percentages |

### 4.3 Provenance and review

`{model, model_version, prompt_version, settings, input_hashes: {unit, study_text}, raw_response_file, created_at}`,
plus `review: {status: unreviewed|confirmed|corrected, by, at, corrections: [...]}`.

**Example** (shape only: the extracted values show an *indirect positive*
case, not a real study):
```json
{"schema_version": "0.1",
 "assessment_id": "culpeper:carrots:c05|wfo-0000638442|pmid:<PMID>|v1",
 "unit_id": "culpeper:carrots:c05|wfo-0000638442", "study_id": "pmid:<PMID>",
 "relevance": "related",
 "evidence_type": "animal",
 "compatibility": {
   "species": {"value": "same", "study_says": "<e.g. Daucus carota seed extract>"},
   "condition": {"value": "related", "study_says": "<what was measured>"},
   "therapeutic_action": {"value": "related", "study_says": "<…>"},
   "plant_part": {"value": "different", "study_says": "seed"},
   "preparation": {"value": "unknown", "study_says": "<…>"},
   "route": {"value": "unknown", "study_says": "<…>"}},
 "outcome": {"value": "positive", "endpoint": "<…>", "comparator": "<…>", "interpretable": "unknown"},
 "excerpts": [{"field": "relevance", "text": "<exact words>", "start": 0, "end": 0}],
 "validation": {"schema_ok": true, "excerpts_checked": 6, "excerpts_failed": [], "fields_voided": []},
 "applicability": "indirect", "finding": "positive",
 "rules_applied": ["S3-3", "S3-4", "S3-6", "S3-7"],
 "modifiers": ["preclinical_animal", "different_plant_part"],
 "mismatches": ["plant_part"], "unknowns": ["preparation", "route"],
 "badge": "Animal · Indirect · Positive",
 "provenance": {"model": "<model>", "prompt_version": "s3-extract-0.1", "settings": {"temperature": 0},
                "input_hashes": {"unit": "<hash>", "study_text": "<hash>"},
                "raw_response_file": "stage3/web/<batch>.answer.txt", "created_at": "<time>"},
 "review": {"status": "unreviewed"}}
```
Note for this claim: Culpeper's part is "whole herb", so a seed study is
`plant_part: different`, giving **indirect at most**, even with a
positive result.


## 5. EmaAssessment (one unit × one EMA monograph)

| Field | Notes |
|---|---|
| `ema_id`, `monograph_title`, `version`, `adopted_date`, `url` | from the document |
| `herbal_substance`, `herbal_preparation`, `route`, `indication` | as stated in the monograph, with excerpts |
| `category` | `well_established_use` · `traditional_use` |
| `matches_unit` | `{preparation, route, indication}`, each `same|related|different|unknown` |
| `applicable` | true only if all three are `same` or `related`; otherwise the mismatch is recorded (rule from the plan: not transferable) |


## 6. Files

```
stage3/
  STAGE3_DATA_CONTRACT.md
  units/<book>.jsonl            HistoricalClaimStudyUnit
  studies/studies.jsonl         StudyRecord
  texts/<study_id>.txt          abstracts / permitted text (outside git if licence requires)
  assessments/v<N>/*.jsonl      EvidenceAssessment
  ema/ema_assessments.jsonl     EmaAssessment
  web/                          prompts and raw replies (outside git, as claims/web/)
  tests/                        rule-engine fixtures and the human-labelled pilot
```


## 7. Validation checks (code, on every record)

1. **The record matches its schema** and `schema_version`.
2. **Every non-`unknown` extracted value** has an excerpt found in the
   stored text, or a metadata citation.
3. **`applicability = direct` only if:**
   - species, condition and action are all `same`
   - plant part, preparation and route are all `same`
   - no `unknown` among these
4. **`finding` is independent of `applicability`.** A negative
   direct study stays negative.
5. **`evidence_type` animal or in_vitro** always carries a preclinical
   modifier, never a clinical badge.
6. **Tier B** always carries `possible_historical_identification`.
7. **`not_found_in_search`** is a property of a unit's query, never a
   finding.


## 8. Open points to agree
1. **Lists for route and preparation** (because of claims like
   3.52's "drink or pessary"): a change from Stage 1's single string.
   The unit builder would split them, but only where the text clearly
   gives alternatives.
2. **Splitting condition from action by MeSH branch** (C/F vs D27/G):
   good enough, or should the assessment use the claim's `relation`
   too?
3. **Dose, population and model:** extract now (optional), or leave for
   a later version?
4. **Where abstract texts may be stored:** in git, or outside like the
   caches?
5. **The 21-group map:** the codes come from the paper's "Med use
   groups" sheet (data file 10). Agree on it before units are built.

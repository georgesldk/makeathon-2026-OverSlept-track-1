# Stage 3: how a historical claim is compared with modern evidence

## In short
- **The question:** for each historical claim (a plant, a use, the book's own words), what do modern
  sources say?
- **The model never gives the verdict.** Gemini only reads each source and fills in facts, each
  backed by an exact excerpt that code checks. Fixed rules in code (S3-0 to S3-9) then decide.
  The model's own opinion is stored, compared and never used.
- **Kinds of evidence are never merged.** Each claim shows separate lanes: regulatory, human,
  preclinical, traditional. Dr. Duke's folk use and compound activity are shown separately too,
  and safety signals sit beside all of them.
- **Every summary says how well the evidence fits.** "Positive (indirect only)" can never be read
  as "positive".
- **Nothing found ≠ not studied.** These are historical claims, not treatments, and not medical
  advice.

## What is compared
- **Unit:** one claim × one plant it may refer to (Stage 2 tier A or B). The tier and its caveats
  travel with every result.
- **Sets** (`stage3/sets.py`):

| Set | What | Status |
|---|---|---|
| pilot | 44 units, 8 plants, PubMed only (`retrieve_pubmed.py`, prompt 0.3, batches of 8) | frozen; provisional review |
| pilot2 | the same 44 units, retrieval v2 | for comparison with the pilot |
| shared | the 670 plant + MeSH groups both books share. One claim per book per group (the first tier-A claim, else the first claim): 1,239 units. A claim with several MeSH terms covers several groups | main run |

## Sources and lanes

| Lane | Sources | What it can show |
|---|---|---|
| Regulatory | EMA herbal monographs (HMPC), sections 4.1–4.3 | an official indication. **Traditional use** (it starts "Traditional herbal medicinal product") is labelled "not proof of efficacy"; **well-established use** is labelled as such |
| Human | PubMed and Europe PMC articles (reviews, trials, other human studies); ClinicalTrials.gov registered trials | clinical results; a registered trial without posted results counts as "no outcome evidence" |
| Preclinical | animal and in vitro studies | laboratory evidence only, never clinical efficacy |
| Traditional | traditional-use surveys found by the searches | documented use, not efficacy |
| Folk use (Dr. Duke's) | ETHNOBOT records for the species and the claim's concept | recorded folk use, not efficacy |
| Compound activity (Dr. Duke's) | compounds in the species with an activity matching the concept | plausibility only, not efficacy |
| Safety signals | harm reported in any source (with its excerpt), sorted by code into toxicity, allergy, EMA contraindication or adverse effect; a harm named as low or none ("low genotoxicity") is kept on record but not shown | a warning; never evidence for or against the claim |

## Retrieval (`stage3/retrieve.py`)
- **Plant:** accepted name, up to 6 WCVP synonyms, and a MeSH heading only if it is for this very
  species (MeSH often files a species under its genus).
- **Common names:**
  - Dr. Duke's common names, plus Culpeper's entry names where the identification is tier A.
  - Used only when unique to one species in Dr. Duke's table and at least 5 letters ("plantain" is
    shared with bananas, so it is not used).
- **Concept:** the MeSH heading plus up to 8 MeSH synonyms of at most 4 words. For example,
  Menstruation-Inducing Agents also searches "Emmenagogues".
- **Searches per plant × concept:**
  - PubMed: human and review studies, 10
  - PubMed: any study, 10
  - Europe PMC, which also searches open-access full text: 10
  - ClinicalTrials.gov, with the plant as the intervention: 10
- **Searches per plant:**
  - PubMed clinical studies with no concept, 200, as Lardos et al. 2024 did (200, not 40: the paper test
    found 11 of 44 expert studies within 40 results and 36 of 44 within 200). Code links a study to a
    claim when the claim's concept is named in the study, or the study's MeSH headings share one of
    the claim's use groups (not the residual group XY).
  - EMA: matched by botanical name in the HMPC table, then the final monograph PDF.
- **Full text:** for kept open-access human studies (trials, systematic reviews, meta-analyses,
  observational), the first 1,500 characters of the Results section, from PubMed Central, are added
  after the abstract. Lab and animal studies keep the abstract only. Any stored text is cut at 6,000
  characters, with a note where it was cut.
- **Screening (code):**
  - A source is kept only if it names the plant: scientific name, synonym, "G. species", or a common
    name.
  - A match on a common name only is marked, and the extraction must still confirm the species.

## Extraction (`stage3/extract_assessments.py`)
- **Prompt:** the model fills in relevance, evidence type, six compatibility fields (species,
  condition, action, plant part, preparation, route: same / related / different / unknown),
  outcome, harm, and last its own overall view. Every field needs an exact excerpt.
- **Prompt versions:**
  - 0.3: the pilot
  - 0.4: adds registered trials and EMA monographs
  - 0.5: every filled field must carry its own excerpt (a test of gemini-3.6-flash on 0.4 left
    relevance without one in half the pairs). Excerpts may also quote the source's header line
    (publication types from the PubMed record).
- **Each prompt version was run once.** Repeated runs, as an ablation, were not done for time.
- **Batches:**
  - 8 pairs per prompt for the pilot; 32 for later sets (a reply of about 24,000 tokens). 64 was
    tried and replies got cut off in the web chat.
  - **32 was not tested against 8;** long batches may lose quality in later pairs. A reply cut off
    before its end keeps its complete pairs; the missing ones are counted.
  - At most 3,200 pairs per set. When there are more pairs, they are chosen in rounds so that as many
    claims as possible get evidence: each claim's best source first, then its second best, at most 6.
  - Best source: EMA, then systematic review / meta-analysis, RCT / clinical trial, registered trial
    with results, review, any other.
  - Pairs left out are listed in `not_exported.jsonl`.

## Checks
- **The excerpt check:**
  - Every excerpt must be in the stored text (case and spacing ignored). Pieces joined by "..." must
    each be there, in order, as for the book quotes in Stage 1.
  - A field whose excerpt fails becomes **unknown**.
- **"Unknown" is never treated as a match.**

## Rules (`stage3/rules.py`, 30 tests in `stage3/tests/`)

| Rule | When | Result |
|---|---|---|
| S3-0 | another question; not about the plant; another genus; or another condition, with no shared action | **not relevant**, however much the topic overlaps |
| S3-1 | relevance not established, or the species can't be told | **unassessable** |
| S3-3 | another species of the genus, or a different part, preparation or route | at most **indirect** |
| S3-3 | condition or action only related | at most **partial**. A related condition is named in the badge: "Partial (related condition)" |
| S3-3 | part, preparation or route only related (an extract for the juice, leaf for herb) | at most **partial** |
| S3-4 | part, preparation, route, condition or action unknown | at most **partial** |
| S3-5 | everything the same | **direct** |
| S3-2 / S3-6 | outcome (from reported results) | positive / negative / mixed / inconclusive / not reported / unclear |
| S3-7 | animal or in vitro | labelled preclinical. In vitro has no route, so it's always indirect |
| S3-8 | tier B identification | labelled "possible historical identification" |
| S3-9 | claim level | one summary per lane, from its best-fitting sources only (direct, else partial, else indirect), with that level named. "· less direct studies differ" when the less direct ones disagree. All results stay listed |

- **Isolated compounds, mixed-herb products and homeopathic dilutions** count as a different
  preparation, so they're indirect.

## Measurements
- **The model's own verdict, compared with the rules** (pilot, prompt 0.3):
  - agree 54/74
  - on indirect studies, the model said "supports" 19 times and "insufficient" 18 times
  - the rules give the same answer every time
- **Pilot review, PROVISIONAL** (done in haste, must be redone; `stage3/review/README.md`):
  - the rules agreed with the review 28/30 times
  - the model's own verdict 10/30
- **Paper test** (`stage3/paper_test.py`, against the experts of Lardos et al. 2024, data file 7):
  1. **Recall:** how many of the experts' clinical studies our plant search finds, within our cap of
     200 and within 500. Studies that name the plant are counted apart from studies of other species
     of the genus, which the experts also counted.
  2. **Use groups by code:** the groups code gives a study from its MeSH headings, against the
     experts' groups.
  3. **Extraction:** each expert study, paired with the expert's use group, should come out relevant;
     paired with a random other group, it should come out not relevant.

  **Results** (Gemini 3.8 Flash, web chat, prompt 0.5, run once):
  - Recall: 41 of 52 expert studies naming the plant found within 200 results (11 within 40, the
    first setting); 0 of 58 on other species of the genus (out of scope by design).
  - Use groups by code: 74 of 83 comparable studies share a group with the experts.
  - Extraction: the experts' own use group judged relevant in **83 of 103** pairs (81%); a random
    other group judged not relevant in **102 of 106** (96%). Most misses are the broad metabolic and
    nutritional group (9 of 15), whose test wording is vague.

## Pilot result (prompt 0.3, 74 pairs, 22 claims with a source)
- No claim had a direct study. The best human evidence was "partial match only" (Plantago, ulcers).
- Safety signals:
  - Ruta graveolens poisoning (2)
  - licorice nephrotoxicity (2)
  - carrot hypervitaminosis A (1)

## Limits
- **Mostly abstracts:** results stated only in a full text are missed, except open-access Results
  sections of human studies, cut at 1,500 characters.
- **Retrieval recall is not known** until the paper test runs. "Not found" never means "not studied".
- **The batch size of 32 is untested; each prompt version was run once.**
- **Dr. Duke's:** common names may contain errors, and matching activities to concepts is word-based
  and approximate ("Antitussive" isn't matched to Cough). Only an action's exact name matches; never
  "anti-" + an action.
- **EMA:**
  - Column names are recognised automatically from the HMPC table.
  - The monograph text comes from a two-column PDF, so well-established and traditional use can be
    mixed in the text. The "Traditional herbal medicinal product" wording is what separates them.
- **ClinicalTrials.gov:** only the outcome titles and p-values posted in the registry.
- **The cap of 3,200 pairs** leaves some pairs unassessed; they're listed.
- **Historical identification stays uncertain, even at tier A.**

## How to run (order)
```
python3 stage3/build_units.py                                    # units, incl. shared.jsonl
python3 stage3/retrieve.py --set shared --dry-run                # check the searches
python3 stage3/retrieve.py --set shared                          # on your computer (network)
python3 stage3/duke.py --set shared
python3 stage3/extract_assessments.py --set shared --export-web  # paste batches, then:
python3 stage3/extract_assessments.py --set shared --import-web "Gemini 3.8 Flash, web chat, temp 0"
python3 stage3/export_graph.py --set shared
python3 -m unittest discover -s stage3/tests
```

## Sources
- Lardos, A. et al. (2024). J. Ethnopharmacology 322, 117622. doi:10.1016/j.jep.2023.117622
- MeSH 2026 (NLM); PubMed / E-utilities (NCBI); Europe PMC; ClinicalTrials.gov API v2
- EMA HMPC, EU herbal monographs
- USDA ARS, Dr. Duke's Phytochemical and Ethnobotanical Databases, doi:10.15482/USDA.ADC/1239279
- Full list with licences: `DATA_SOURCES.md`

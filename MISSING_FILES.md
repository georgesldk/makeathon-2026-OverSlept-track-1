# Files that are not in git

Some files are too big for GitHub, or are downloads and API caches, so
git ignores them. George sends them separately (WeTransfer). This page
says what they are, where they go, and what needs them.


## What you can do without them

- Read every result: matching/culpeper/ and matching/dioscorides/
  (candidates, resolved scientific names, geography check, and the
  final eligibility list eligibility.json), the description check
  (description_sources/check/<book>/description_check.json) and the
  AI test report (description_sources/paper_test/RESULTS.md), and the
  medicinal claims with their links and checks (claims/: claims.json,
  links.json, graph/, review samples, mesh_crosscheck.json; method in
  claims/CLAIMS_METHOD.md).
- Rerun the eligibility rules: python3 matching/eligibility.py --book culpeper
- Relink the claims: python3 claims/link_claims.py
- Rerun the Dioscorides extraction, validator and dictionary lookups
  (historical_texts/dioscorides/), and the Culpeper extraction.

Everything else (the source lookups, aggregate, resolve, geography)
needs the files below.


## How to install them

1. Download overslept_missing_files.zip from the WeTransfer link.
2. Put it next to the repo folder and unzip it from inside the repo:

       cd makeathon-2026-OverSlept-track-1
       git pull
       unzip -o ../overslept_missing_files.zip

   The zip keeps the folder structure, so every file lands in the
   right place. Nothing tracked by git is overwritten. -o replaces
   files from an earlier zip without asking about each one (if you
   unzipped an older version before, this updates it).
3. Check: these should run and print a summary, not an error:

       python3 matching/resolve_scientific.py
       python3 description_sources/check/description_check.py --book culpeper --import-web "Gemini 3.8 Flash, web chat, temp 0"

4. API keys are not in the zip. Copy .env.example to .env and add
   your own keys if you need them: BHL_API_KEY (free) for the BHL
   descriptions, GEMINI_API_KEY for the AI scripts' API route.


### Update zips

overslept_missing_files_3.zip (5 Nov, 22 MB) holds only what is new
since the second zip: the claim prompts and replies (claims/web/), the
NCBI and Wikidata caches (claims/cache/), the MeSH download and the
Disease Ontology file. Unzip it the same way, on top of the earlier
zip (unzip -o). Nothing in it replaces an earlier file.

overslept_missing_files_4.zip (6 Nov, 166 MB) holds only what is new or changed
since the third zip: Stage 3 (the abstracts in stage3/texts/, the search
caches in stage3/cache/, every Stage 3 prompt and pasted reply in
stage3/web/ and stage3/paper_test/web/, the full unit files), the
claims batch for the 4 Dioscorides chapters that gained a plant after
the Stage 2 fixes, and the paper's data file 7. Unzip it the same way,
on top of the earlier zips (unzip -o).


## What is in the zip, and where it goes

Downloaded datasets (about 470 MB):

    scientific_name_sources/wcvp/data/     WCVP v16, Kew (432 MB)
                                           needed by: WCVP lookup, geography
    common_name_sources/drduke/data/       Dr. Duke's databases, USDA (39 MB)
                                           needed by: Dr. Duke's lookup

Source outputs, the results of each lookup (about 400 MB):

    common_name_sources/<source>/culpeper/<source>.json
        gbif, wikidata, inaturalist, checklistbank, taxtree, drduke
    common_name_sources/wikidata/dioscorides/wikidata.json
    scientific_name_sources/<source>/<book>/<source>.json
        wfo, wcvp, globalnames, ipni, for culpeper and dioscorides
    needed by: aggregate.py (common-name outputs),
               resolve_scientific.py and geography.py (scientific outputs)

Description sources (about 125 MB, mostly the BHL cache):

    description_sources/bhl/<book>/bhl.json            old-flora descriptions per species
    description_sources/wikipedia/<book>/wikipedia.json Wikipedia descriptions per species
    description_sources/bhl/cache/, wikipedia/cache/   their raw replies (BHL: ~6,000 calls per book)
    description_sources/check/web/<book>/              the web-chat prompts AND the pasted replies:
                                                       the only copy of the description check's raw
                                                       answers; import_web rebuilds the results from them
    description_sources/paper_test/cache/              raw replies of every model in the AI test
    description_sources/paper_test/data/               the paper's data files 3, 6, 9 (or download them:
                                                       https://figshare.com/s/2e0f64b5794892ed4679)
    needed by: description_check.py (bhl.json, wikipedia.json, web/),
               test_models.py (data/, cache/)

Medicinal claims (about 30 MB):

    claims/web/<book>/                     the claim prompts AND the pasted Gemini replies: the only
                                           copy of the raw answers; --import-web rebuilds claims.json
    claims/cache/ncbi/                     PubMed's replies for the cross-check (check 6)
    claims/cache/wikidata/                 Wikidata's replies for the old-term table
    reference_sources/mesh/desc2026.gz     MeSH 2026 descriptors, NLM (17 MB); mesh_index.json.gz
                                           (in git) is built from it by build_mesh_index.py
    reference_sources/doid/doid.obo        Disease Ontology, release 2026-10-29 (7 MB)
    needed by: extract_claims.py --import-web (web/), check_mesh_ncbi.py (cache/ncbi),
               map_historical_terms.py (doid.obo, cache/wikidata), build_mesh_index.py (desc2026.gz)

Stage 3, modern evidence (about 650 MB unzipped, mostly the PubMed cache; zip 4):

    stage3/texts/                          the stored text of every source (abstract, Results
                                           section, trial record, EMA monograph sections): what the
                                           excerpt check reads. Publisher text, so not in git
    stage3/cache/ncbi, epmc, ctgov, ema/   the raw replies of every search: a rerun of retrieve.py
                                           asks nothing again
    stage3/web/                            the Stage 3 prompts AND the pasted Gemini replies (pilot,
                                           shared, the superseded prompt-0.2 run): the only copy of
                                           the raw answers; --import-web rebuilds every result
    stage3/paper_test/web/, expert_studies.jsonl
                                           the paper test's prompts, replies and the rows read from
                                           the paper's data file 7 (not redistributed)
    stage3/units/culpeper.jsonl, dioscorides.jsonl
                                           every claim × plant unit (build_units.py rebuilds them)
    description_sources/paper_test/data/Data file 7 - Clinical trial data PubMed .xlsx
    needed by: extract_assessments.py and paper_test.py --import-web (web/, texts/),
               retrieve.py (cache/), show.py and export_graph.py (texts/ only for the excerpts)

API caches, the raw replies (about 320 MB):

    common_name_sources/<source>/<book>/cache/
    scientific_name_sources/<source>/cache/
    needed by: rerunning a source script without asking the API again.
    Without them a rerun asks everything again (hours for GBIF,
    ChecklistBank and TaxTree).


## If you would rather download the datasets yourself

- WCVP: https://sftp.kew.org/pub/data-repositories/WCVP/
  (wcvp.zip; put wcvp_names.csv and wcvp_distribution.csv in
  scientific_name_sources/wcvp/data/)
- Dr. Duke's: https://doi.org/10.15482/USDA.ADC/1239279
  (put the CSV files in common_name_sources/drduke/data/)
- MeSH: https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2026.gz
  (put it in reference_sources/mesh/)
- Disease Ontology: https://raw.githubusercontent.com/DiseaseOntology/HumanDiseaseOntology/main/src/ontology/doid.obo
  (put it in reference_sources/doid/; a newer release may map differently)


## For George: making the zip

From inside the repo (the first line deletes the previous zip; without
it, zip would add to the old file and keep files that no longer exist):

    rm -f ../overslept_missing_files.zip
    git ls-files --others --ignored --exclude-standard \
      | grep -v -e '^\.env$' -e '__pycache__' -e '\.DS_Store' \
      | zip -@ ../overslept_missing_files.zip

This zips exactly the files git ignores, except .env (your keys)
and Python's cache files. About 1 GB before compression; JSON
compresses well, so the zip should be well under WeTransfer's 2 GB.

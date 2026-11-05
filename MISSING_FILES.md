# Files that are not in git

Some files are too big for GitHub, or are downloads and API caches, so
git ignores them. George sends them separately (WeTransfer). This page
says what they are, where they go, and what needs them.


## What you can do without them

- Read every result: matching/culpeper/ and matching/dioscorides/
  (candidates, resolved scientific names, geography check, and the
  final eligibility list eligibility.json), the description check
  (description_sources/check/<book>/description_check.json) and the
  AI test report (description_sources/paper_test/RESULTS.md).
- Rerun the eligibility rules: python3 matching/eligibility.py --book culpeper
- Rerun the Dioscorides extraction, validator and dictionary lookups
  (historical_texts/dioscorides/), and the Culpeper extraction.

Everything else (the source lookups, aggregate, resolve, geography)
needs the files below.


## How to install them

1. Download overslept_missing_files.zip from the WeTransfer link.
2. Put it next to the repo folder and unzip it from inside the repo:

       cd makeathon-2026-OverSlept-track-1
       unzip ../overslept_missing_files.zip

   The zip keeps the folder structure, so every file lands in the
   right place. Nothing tracked by git is overwritten.
3. Check: this should run and print the summary, not an error:

       python3 matching/resolve_scientific.py

4. API keys are not in the zip. Copy .env.example to .env and add
   your own keys if you need them: BHL_API_KEY (free) for the BHL
   descriptions, GEMINI_API_KEY for the AI scripts' API route.


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

API caches, the raw replies (about 320 MB):

    common_name_sources/<source>/<book>/cache/
    scientific_name_sources/<source>/cache/
    needed by: rerunning a source script without asking the API again.
    Without them a rerun asks everything again (hours for GBIF,
    ChecklistBank and TaxTree).


## If you would rather download the two datasets yourself

- WCVP: https://sftp.kew.org/pub/data-repositories/WCVP/
  (wcvp.zip; put wcvp_names.csv and wcvp_distribution.csv in
  scientific_name_sources/wcvp/data/)
- Dr. Duke's: https://doi.org/10.15482/USDA.ADC/1239279
  (put the CSV files in common_name_sources/drduke/data/)


## For George: making the zip

From inside the repo:

    git ls-files --others --ignored --exclude-standard \
      | grep -v -e '^\.env$' -e '__pycache__' -e '\.DS_Store' \
      | zip -@ ../overslept_missing_files.zip

This zips exactly the files git ignores, except .env (your keys)
and Python's cache files. About 1 GB before compression; JSON
compresses well, so the zip should be well under WeTransfer's 2 GB.

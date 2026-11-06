# EthnoTrace local application

This application uses the existing Figma visual language and the `ethnotrace-clean` Neo4j graph. It is a local research interface; historical identifications and model-assisted assessments remain hypotheses, not medical advice or proof of efficacy.

## Start locally

Start Neo4j and make sure the `ethnotrace-clean` database is online. From the repository root, use two terminals.

Terminal 1 — read-only API. The existing repository Neo4j Python environment contains the driver:

```sh
cd Makeathon_UI
export NEO4J_URI='neo4j://127.0.0.1:7687'
export NEO4J_USER='neo4j'
export NEO4J_DATABASE='ethnotrace-clean'
read -s 'NEO4J_PASSWORD?Neo4j password: '; export NEO4J_PASSWORD; echo
../neo4j/.venv/bin/python -B server.py
```

The `read` line is for macOS zsh; in bash use `read -s -p 'Neo4j password: ' NEO4J_PASSWORD; export NEO4J_PASSWORD; echo`. If the Python environment is missing, create it and install the official `neo4j` driver as documented in `../neo4j/README.md`. Never commit passwords. The API binds to localhost on port 8787, accepts only fixed read queries, uses query parameters, and uses a Neo4j read session. A database account restricted to read-only access is recommended.

Terminal 2 — frontend:

```sh
cd Makeathon_UI
npm install
npm run dev
```

Open http://127.0.0.1:8443. Vite proxies `/api` to the local API. If the API or database is unavailable the UI reports an error; it does not display mock evidence. The original Figma prototype remains in `src/App.tsx`, and the data-connected entry point is `src/LiveApp.tsx`.

## Explore

Search a historical name, Greek headword, scientific candidate or recorded original name. Catalogue filters operate at entry level and can match different candidates or claims within the same entry. Select an entry, then use **Identification** for A/B candidates, evidence and taxonomy. Enable Tier X explicitly to see hidden candidates. **Claims & Research** brings extracted interpretations and historical quotations together with MeSH mappings, shared research assessments and inferred cross-book groupings. Select a claim to view its related research. Hover, focus or tap the information icons to explain categories and scientific terms. In **Relationships**, select a candidate or claim and use **Expand related evidence in graph**; use the graph controls to pan, zoom and fit. Graph expansion is limited to keep the view usable; full result lists are in the tabs.

The API requires exactly one completed structured snapshot, one shared claims/studies dataset, and its matching full-unit dataset. If multiple snapshots exist, set `ETHNOTRACE_SNAPSHOT` to the desired snapshot ID; the API refuses ambiguous datasets instead of mixing them. Candidate evidence and study assessments are paginated. Entry details are limited to 200 candidates and 200 claims; the current graph's largest entries have 149 and 55 respectively. Unlinked entry evidence is available in the Identification tab and is not assigned to candidates.

## Candidate photographs

The catalogue can display a photo of its preferred modern candidate, alongside creator, licence and source links. Image metadata is stored locally in `data/candidate_images.json`, outside Neo4j and independently of the historical evidence. A photograph illustrates a candidate and does not establish the historical identification.

To check 20 example names or resume the full A/B lookup, respectively:

```sh
python3 collect_candidate_images.py --limit 20
python3 collect_candidate_images.py --limit 0
```

The collector requests GBIF only, requires an exact accepted scientific-name match and the same GBIF occurrence taxon key, and only records HTTPS images with an individual creator and a CC0, CC BY or CC BY-SA licence. It checks up to 40 occurrences per taxon, so a missing image means none met these checks in that sample. It records unmatched and unavailable cases, retries errors on the next run, and saves progress in batches. The user interface falls back to its placeholder when no usable image is recorded or an image fails to load. Media records and identifications can still be incorrect; review them and their licences before reuse.

## Verify

With the API and Neo4j running and `NEO4J_PASSWORD` set:

```sh
ETHNOTRACE_TEST_LIVE=1 ../neo4j/.venv/bin/python -B -m unittest discover -s tests -v
npm run build
npx tsc --noEmit
npx playwright test tests/ui.spec.ts
```

The browser checks require the local frontend and API to be running. On a new machine, install the browser with `npx playwright install chromium` first. The live integration checks use Carrots, Dioscorides chapters 1.1, 1.3 and 1.117, Bifoil, MeSH mapping, linked research and LSJ provenance. They use read-only queries and do not alter the database.

# Offline pipeline contract tests

Run from the repository root with Python 3.10 or newer:

```sh
python3.10 -B tests/run_tests.py
```

No packages, downloads, API keys or network calls are required for the default implementation. The tests create synthetic inputs and outputs in temporary directories. They do not run pipeline scripts against the real datasets or overwrite scientific outputs. The suite covers evidence joins and independence, eligibility decisions and missing data, taxonomic synonym handling, WFO/WCVP disagreements, and LSJ citation handling. It does not validate historical plant identifications or modern medical claims.

## Known defects and strict mode

The audit found existing defects. Their tests are labelled `expected failure` so the regular run makes the known failures visible while detecting additional regressions. An expected failure is **not a passing scientific requirement**. If a defect is fixed, its test becomes an `unexpected success`: remove the `@known_defect` decorator once the fix has been reviewed.

To treat all known defects as ordinary failures, run:

```sh
python3.10 -B tests/run_tests.py --strict
```

Strict mode exited nonzero until the defects were fixed. Since 2026-11-06 (Stage 2 fixes, round 2) the known-defect tests pass and are ordinary tests again; `test_neo4j_model` still needs `neo4j/prepare.py`, which is not in the repository yet. Both modes exit nonzero for new failures or errors.

## Testing another implementation

The test runner uses Python's standard library, but the programs under test can use any language. These are black-box tests: a program must consume the fixture files and produce the JSON output paths and fields used by the tests. An implementation with a different interface needs an adapter that translates the contract to its interface and back. The adapter is part of the implementation under test, not a change to the fixtures.

Set any of the following environment variables to a **JSON array of command arguments**. Commands are run without a shell, with the temporary fixture directory as their working directory and `ETHNOTRACE_ROOT` set to its absolute path. `{root}` and `{book}` placeholders in arguments are substituted by the test harness; `{book}` is `culpeper` for eligibility and resolution.

- `ETHNOTRACE_ELIGIBILITY_COMMAND`: reads `matching/culpeper/herb_candidates_resolved.json`, `geography.json`, and `evidence.jsonl`, plus the optional `description_sources/check/culpeper/description_check.json`; writes `matching/culpeper/eligibility.json`.
- `ETHNOTRACE_RESOLUTION_COMMAND`: reads `matching/culpeper/candidates.json` and `scientific_name_sources/{wfo,wcvp}/culpeper/*.json`; writes `matching/culpeper/scientific_names_resolved.json` and `herb_candidates_resolved.json`.
- `ETHNOTRACE_LEXICON_COMMAND`: reads `historical_texts/dioscorides/chapters.json` and `reference_sources/lsj/lsj_index.json.gz`; writes `historical_texts/dioscorides/lexicon_lsj.json`.

For example, use an absolute path to your own adapter:

```sh
export ETHNOTRACE_ELIGIBILITY_COMMAND='["/absolute/path/to/adapter", "--root", "{root}", "--book", "{book}"]'
python3.10 -B tests/run_tests.py
```

Only commands explicitly configured this way are invoked; unconfigured stages use the repository scripts. For a configured eligibility or lexicon implementation, the relevant known-defect tests run as ordinary requirements, not expected failures. The adapter must respect `ETHNOTRACE_ROOT` and never write to the real datasets. Commands are not network-sandboxed: ensure alternative implementations operate offline.

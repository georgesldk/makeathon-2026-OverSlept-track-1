# Stage 3 pilot review: PROVISIONAL, must be redone

**Status:** provisional. Done in haste on 5 Nov 2026 so the work could continue.
How the sheet was filled is not recorded. It is **not** a validated human review.
Before any Stage 3 result is reported, a person must redo it, reading each claim and abstract.

## What it is
- `pilot_review.csv`: 30 claim × study pairs from the pilot (prompt s3-extract-0.3)
  - rows 1–20: every pair where the rules and the model's own overall verdict disagree
  - rows 21–30: 10 random pairs where they agree (seed 42)
- `review_results.json`: the scores, from `python3 stage3/review_pilot.py --score`

## Provisional scores (not to be quoted as validated)
| Compared with the review | Agree |
|---|---|
| Rules' applicability | 28/30 |
| Finding | 30/30 |
| Rules' verdict | 28/30 |
| Model's own overall verdict | 10/30 |
| Harm | 21/30 (all 9 differences are "no" vs "not reported"; no disagreement on harm found) |

## To redo it
1. Empty the four `human_*` columns. Keep a copy of this version, renamed.
2. For each row, read the claim and the full abstract before looking at the machine's columns.
3. Fill the columns as described in `stage3/review_pilot.py`, then run `--score`.
4. Record who reviewed it, the date, and how, here. Then remove the PROVISIONAL status
   in `stage3/review_pilot.py`.

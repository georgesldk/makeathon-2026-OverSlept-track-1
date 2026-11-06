# makeathon-2026-OverSlept-track-1

## Books
- Culpeper, *The Complete Herbal* (1653) · Dioscorides, *De materia medica* (1st c., Wellmann's Greek) ·
  the *Shennong Bencao Jing* (1st-2nd c., Sun Xingyan's reconstruction, classical Chinese; added 2026-11-06).
  All three go through the same stages; Shennong's sources and rules are in `matching/ELIGIBILITY_RULES.md`.

## Open issues
- **Shennong: 2 "direct" Stage 3 results need a person.** Grape juice for strength (an athletes' trial, result
  inconclusive) and red peony root for abdominal pain (a pancreatitis trial: a related condition, not the
  same). Bretschneider's strong verdicts were proposed by Claude and checked by a person.
- **Stage 3 pilot review is provisional.** It was done in haste and must be redone by a person
  before any Stage 3 result is reported. See `stage3/review/README.md`.
- **Stage 3 batch size and repeat runs.** Later sets use 32 pairs per prompt; this was not tested against
  the pilot's 8. Each prompt version was run once; repeated runs (ablation) were not done for time.
  See `stage3/EVIDENCE_RULES.md`.

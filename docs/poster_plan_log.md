# Poster plan execution log

Short execution log for the poster Stage 1 preliminary-results sprint.

## Phase 1 — Estimate corpus distributions from Aptadiff Dataset A

- Implemented `scripts/estimate_corpus_distributions.py`.
- Output directory: `data/processed/corpus_distributions/`.
- Intended outputs:
  - `data/processed/corpus_distributions/aptadiff_datasetA_p6.json`
  - `data/processed/corpus_distributions/aptadiff_datasetA_p6_summary.md`
- Processing policy:
  - DNA sequences converted to RNA by `T -> U`.
  - Sequences outside `{A, U, C, G}` after conversion are excluded.
  - Distributions are unweighted; each sequence counted once (`p6` not used).

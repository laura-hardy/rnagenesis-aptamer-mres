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

## Phase 2 — Generate null model sequences from Aptadiff A distributions

- Implemented `scripts/generate_null_sequences.py`.
- Source distribution JSON: `data/processed/corpus_distributions/aptadiff_datasetA_p6.json`.
- Output directory: `results/null_model_30k/`.
- Seed: `42`.
- Sequences generated: `30,000`.
- Generation policy:
  - Lengths sampled from the empirical length histogram.
  - Bases sampled independently from corpus mononucleotide frequencies.
  - No structural, GC, MFE, motif, or homopolymer constraints applied.
  - Duplicate sequences are intentionally not removed at generation time.

## Phase 3 — Poster-specific Stage 1 config from Aptadiff A distributions

- Implemented `scripts/make_stage1_config_from_distributions.py`.
- Created `configs/stage1_hard_filter_aptadiffA_poster.json`.
- Length and GC thresholds are empirically derived from Aptadiff A reference distributions.
- MFE and near-dedup filters are intentionally deferred for poster Stage 1.

## Phase 4 — Lenient MFE hard filter from Aptadiff A reference

- Computed Aptadiff A MFE distribution with `--compute-mfe`:
  - `data/processed/corpus_distributions/aptadiff_datasetA_p6_with_mfe.json`
  - `data/processed/corpus_distributions/aptadiff_datasetA_p6_with_mfe_summary.md`
- Updated `scripts/make_stage1_config_from_distributions.py` with `--mfe-upper-quantile` (`q90|q95|q99`).
- Created MFE-enabled poster config:
  - `configs/stage1_hard_filter_aptadiffA_poster_with_mfe.json`
  - `configs/stage1_hard_filter_aptadiffA_poster_with_mfe_summary.md`
- MFE quantile used: **q95** (default).
- Normalised MFE cutoff (`max_normalised_mfe`): **0.0** (q95 and q99 both equal 0.0 for this corpus).
- Stage 1 reruns (MFE computed and applied as hard filter):
  - Null: `results/aim3_stage1_null_30k_with_mfe_filter/` — 12,602 / 30,000 passed (42.0%).
  - Unadapted: `results/aim3_stage1_unadapted_30k_poster_config_with_mfe_filter/` — 12,337 / 30,080 passed (41.0%).
- Comparison summary: `results/aim3_stage1_mfe_filter_comparison.md`.
- Incremental MFE rejections: **0** for both conditions at q95 cutoff (all sequences have normalised MFE ≤ 0).

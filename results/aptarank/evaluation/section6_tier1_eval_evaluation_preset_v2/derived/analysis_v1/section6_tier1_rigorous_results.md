# Section 6 Tier 1 EVAL rigorous rerun: provisional analysis

Status: `PROVISIONAL_SECTION6_EVALUATION_PRESET_ANALYSIS_AWAITING_INDEPENDENT_REVIEW_AND_EXPLICIT_RESULT_COMMITMENT`

## Run identity and technical accounting

- Named UI preset: Evaluation (paper rigorous mode)
- Frozen run-sheet settings: seed 42, 99 candidate shuffles and 200 sampled structures
- Input candidates: 308
- Evaluable scores: 306 (153 EVAL cores; 153 paired controls)
- Technical exclusions: 2; one complete matched pair, with no replacement
- Complete score pairs: 153
- Pre-rejection clusters represented among complete pairs: 79 of 79
- Cluster bootstrap: 10000 replicates; zero undefined or imputed replicates for every target

The candidate upload, private key, pair and cluster membership, controls, exclusions and estimands are unchanged from the historical Standard run. The runs are not pooled.

## Aptamer-likeness

| Group | n | Mean | Median | Q1 | Q3 | IQR |
|---|---:|---:|---:|---:|---:|---:|
| EVAL core | 153 | 0.513 | 0.512 | 0.395 | 0.641 | 0.246 |
| Paired uniform control | 153 | 0.429 | 0.409 | 0.301 | 0.563 | 0.262 |

- Median paired difference, EVAL minus control: 0.108 (cluster-bootstrap 95% CI 0.064 to 0.164).
- Mean paired difference: 0.083.
- Descriptive AUROC against the paired uniform null: 0.638 (cluster-bootstrap 95% CI 0.555 to 0.717).
- Secondary Wilcoxon signed-rank test: W+ = 7959, two-sided p = 0.000164702; zeros discarded, average ranks for ties, normal approximation without continuity correction.

## Candidate-specific shuffle checks

- EVAL cores passing: 15/153 (9.8%).
- Uniform controls passing: 9/153 (5.9%).
- Paired pass-rate difference, EVAL minus control: 3.9% (cluster-bootstrap 95% CI -3.2% to 11.1%).

## Interpretation boundary

This is a provisional calculation awaiting independent review and explicit scientific result commitment. The five-component table is unavailable because no verified component-level export was provided; no component was recomputed. AptaRank scores are computational prioritisation evidence and do not demonstrate binding, affinity, specificity, inhibition, target recognition or experimental function. Uniform RNA is a synthetic floor rather than an experimental non-binder.

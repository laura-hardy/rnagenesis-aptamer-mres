# Section 6 Tier 1 EVAL provisional analysis

Status: `PROVISIONAL_SECTION6_ANALYSIS_AWAITING_EXPLICIT_RESULT_COMMITMENT`

## Technical accounting

- Input candidates: 308
- Evaluable scores: 306 (153 EVAL cores; 153 paired controls)
- Technical exclusions: 2; one complete matched pair, with no replacement
- Complete score pairs: 153
- Pre-rejection clusters represented among complete pairs: 79 of 79
- Cluster bootstrap: 10000 replicates; zero undefined or imputed replicates for every target

## Aptamer-likeness

| Group | n | Mean | Median | Q1 | Q3 | IQR |
|---|---:|---:|---:|---:|---:|---:|
| EVAL core | 153 | 0.513 | 0.512 | 0.395 | 0.641 | 0.246 |
| Paired uniform control | 153 | 0.429 | 0.409 | 0.301 | 0.563 | 0.262 |

- Median paired difference, EVAL minus control: 0.108 (cluster-bootstrap 95% CI 0.064 to 0.164).
- Mean paired difference: 0.083.
- Descriptive AUROC against the paired uniform null: 0.638 (cluster-bootstrap 95% CI 0.555 to 0.717).
- Secondary Wilcoxon signed-rank test: W+ = 7959, two-sided p = 0.000164702; zeros discarded, average ranks for ties, normal approximation without continuity correction.

The frozen REF-calibrated Tier 1 score distinguishes EVAL cores from their exact-length uniform controls in this comparison. The effect is positive and moderate rather than near-perfect. AUROC is descriptive for this synthetic null and is not a universal aptamer classifier.

## Candidate-specific shuffle checks

- EVAL cores passing: 9/153 (5.9%).
- Uniform controls passing: 7/153 (4.6%).
- Paired pass-rate difference, EVAL minus control: 1.3% (cluster-bootstrap 95% CI -4.1% to 6.6%).

Shuffle-pass sensitivity is low in both groups, and the paired difference is uncertain and compatible with no difference. The positive composite-score separation must not be described as broad success against the stronger dinucleotide-preserving null.

## Availability and interpretation limits

The production five-component table is unavailable because the UI did not provide a verified component-level export. Component values were not recomputed locally.

AptaRank scores are computational prioritisation evidence. They do not demonstrate binding, affinity, specificity, inhibition, target recognition or experimental function. Uniform RNA is a synthetic floor rather than an experimental non-binder. Final result commitment remains subject to explicit approval.

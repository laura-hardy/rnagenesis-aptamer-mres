# Section 9 generated-condition comparison against NDM-1: exact Tier 2 update

Status: `PROVISIONAL_SECTION9_ANALYSIS_AWAITING_INDEPENDENT_REVIEW_AND_EXPLICIT_RESULT_COMMITMENT`

This v2 analysis preserves the validated 800-row accounting and all Tier 1 results from analysis v1, then joins a later-discovered untouched AptaRank exact-score export by opaque candidate ID. The control percentiles are scorer outputs and were not reconstructed locally. Tier 1 and Tier 2 remain separate.

## Exact target-control percentiles

| Condition | n | Mean | Median | IQR | Strong | Moderate | Weak |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 200 | 0.376 | 0.407 | 0.218–0.569 | 4 (2.0%) | 12 (6.0%) | 184 (92.0%) |
| B1 | 200 | 0.472 | 0.407 | 0.250–0.712 | 11 (5.5%) | 34 (17.0%) | 155 (77.5%) |
| B2 | 200 | 0.485 | 0.569 | 0.250–0.712 | 9 (4.5%) | 38 (19.0%) | 153 (76.5%) |
| D1 | 200 | 0.501 | 0.569 | 0.250–0.803 | 10 (5.0%) | 46 (23.0%) | 144 (72.0%) |

For the primary B1-versus-D1 comparison, D1 has a +0.029 mean and +0.162 median control-percentile difference. Its strong-band rate is 0.5 percentage points lower (10 versus 11 candidates), while its moderate-band rate is 6.0 points higher (46 versus 34). The favourable-band advantage is therefore carried by additional `moderate` annotations, not additional `strong` annotations.

Relative to B2, D1 has a +0.016 mean percentile difference, the same median percentile, a +0.5-point strong-band difference and a +4.0-point moderate-band difference. B0 remains an external descriptive comparator because its length regime differs.

## Seed and block descriptives

| Stratum | n | Mean | Median | Strong | Moderate | Weak |
|---|---:|---:|---:|---:|---:|---:|
| B1 block A | 100 | 0.461 | 0.488 | 3 | 17 | 80 |
| B1 block B | 100 | 0.482 | 0.407 | 8 | 17 | 75 |
| D1 seed 43 | 100 | 0.488 | 0.569 | 3 | 27 | 70 |
| D1 seed 44 | 100 | 0.513 | 0.569 | 7 | 19 | 74 |

## Relationship and limits

The exact export gives Spearman rho = -0.071884 for Tier 1 versus target-control percentile, matching the PDF's rounded -0.072 (PDF p = 0.0421, n = 800). The association is negligible in magnitude and weakly negative. It does not justify a combined score or a biological-dependence claim.

> This cavity is oddly shaped: its robust extent and equivalent-sphere diameter disagree by more than 2×. The geometric comparison assumes a roughly convex pocket.

The exact scores do not remove this geometric limitation. They distinguish where observations lie inside the target-specific control distribution, but they are not binding probabilities and do not demonstrate affinity, specificity, inhibition, target recognition or experimental function. Candidate rows, technical blocks and generation seeds are not independent training replicates; D1 still has only two training seeds. No Section 9 candidate enters the supervisor-review shortlist.

The quantitative update therefore sharpens but does not materially change the provisional interpretation. Independent review and explicit result commitment remain pending.

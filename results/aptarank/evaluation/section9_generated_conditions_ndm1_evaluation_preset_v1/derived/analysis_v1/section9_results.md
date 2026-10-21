# Section 9 generated-condition comparison against NDM-1

Status: `PROVISIONAL_SECTION9_ANALYSIS_AWAITING_INDEPENDENT_REVIEW_AND_EXPLICIT_RESULT_COMMITMENT`

## Validated accounting

The frozen 800-row upload reconciled exactly to the downloaded shortlist by opaque candidate ID. All 800 candidates were scored, with no technical exclusions and no replacement. Each condition contributes 200 scored memberships; D1 retains 100 candidates from training seed 43 and 100 from seed 44, and B1 retains 100 candidates from each technical block.

The run used AptaRank 0.1.0, schema 1.0.0, git revision `49a85609e352`, the Evaluation preset, seed 42, 99 candidate shuffles, 200 sampled structures, `corpus_weighted_mean`, and scoring signature `95a49467ef3c6186`. The prepared target was NDM-1/5ZGX chain A in pocket/groove mode, identifier `0fde4d5e4370`. The displayed ranking runtime was 29 seconds.

## Condition-level results

| Condition | n | Tier 1 mean | Tier 1 median | IQR | Shuffle pass | Strong | Moderate | Weak | Strong or moderate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 200 | 0.334 | 0.304 | 0.205–0.433 | 10/200 (5.0%) | 4 | 12 | 184 | 16/200 (8.0%) |
| B1 | 200 | 0.402 | 0.389 | 0.279–0.520 | 11/200 (5.5%) | 11 | 34 | 155 | 45/200 (22.5%) |
| B2 | 200 | 0.492 | 0.483 | 0.362–0.636 | 13/200 (6.5%) | 9 | 38 | 153 | 47/200 (23.5%) |
| D1 | 200 | 0.460 | 0.445 | 0.338–0.592 | 17/200 (8.5%) | 10 | 46 | 144 | 56/200 (28.0%) |

As a descriptive cross-tabulation of the separate outputs, shuffle `pass` coincided with a `strong` or `moderate` compatibility band for 1/200 B0, 1/200 B1, 3/200 B2 and 2/200 D1 candidates. This is not a combined score, a Section 9 selection threshold or a supervisor-shortlist rule.

B1 versus D1 is the primary controlled downstream comparison. Relative to B1, D1's Tier 1 mean and median differences were +0.058 and +0.056; its shuffle-pass rate differed by +3.0 percentage points and its strong-or-moderate compatibility rate by +5.5 points.

B2 is the secondary non-neural, data-scale comparator. Relative to B2, D1's Tier 1 mean and median differences were -0.033 and -0.038; its shuffle-pass rate differed by +2.0 percentage points and its strong-or-moderate compatibility rate by +4.5 points.

B0 remains an external descriptive baseline because its 36-nt length regime differs from the other conditions. No candidate-level hypothesis test or training-population confidence interval is reported: candidate rows, generation seeds and technical blocks are not independent training replicates, and D1 has only two training seeds.

## D1 seed and B1 block summaries

| Stratum | n | Tier 1 mean | Tier 1 median | Shuffle pass | Strong | Moderate | Weak |
|---|---:|---:|---:|---:|---:|---:|---:|
| B1 block A | 100 | 0.416 | 0.416 | 7/100 (7.0%) | 3 | 17 | 80 |
| B1 block B | 100 | 0.388 | 0.351 | 4/100 (4.0%) | 8 | 17 | 75 |
| D1 seed 43 | 100 | 0.454 | 0.444 | 6/100 (6.0%) | 3 | 27 | 70 |
| D1 seed 44 | 100 | 0.465 | 0.453 | 11/100 (11.0%) | 7 | 19 | 74 |

## Relationship between the separate tiers

The untouched AptaRank PDF reports Spearman rho = -0.072, p = 0.0421, n = 800 for Tier 1 aptamer-likeness versus the target-compatibility control percentile. The magnitude is negligible and weakly negative. The nominal p-value should not be overinterpreted: it does not establish biological dependence or independence, the candidate rows are not training replicates, and the numeric Tier 2 percentiles were not included in the CSV and therefore were not independently recomputed.

## Target-geometry warning and interpretation boundary

> This cavity is oddly shaped: its robust extent and equivalent-sphere diameter disagree by more than 2×. The geometric comparison assumes a roughly convex pocket.

This warning materially limits the Tier 2 interpretation. The selected NDM-1 cavity is non-convex enough that its robust extent and equivalent-sphere diameter disagree substantially, while the deployed geometric comparison assumes a roughly convex pocket. The strong/moderate/weak labels are therefore retained only as target-specific, REF-control-relative prioritisation categories from the frozen tool. They must not be treated as probabilities of binding or evidence of affinity, specificity, inhibition, target recognition or experimental function.

Section 6 showed moderate Tier 1 separation from uniform controls but low shuffle-pass sensitivity, while Section 8 gave weak-to-mixed cognate Tier 2 results with no shuffle passes. Those findings, together with the cavity warning here, mean that favourable Section 9 outputs are descriptive computational prioritisation signals only. Tier 1 and Tier 2 remain separate; no combined score was formed, and no candidate from this 800-member comparison enters the supervisor-review shortlist.

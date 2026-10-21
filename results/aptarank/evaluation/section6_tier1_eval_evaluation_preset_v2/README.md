# Section 6 Tier 1 EVAL rigorous rerun

Status: `SECTION6_RIGOROUS_SCIENTIFIC_RESULT_COMMITTED_AND_CLOSED`

This is the same-input rerun of Section 6 under AptaRank's named Evaluation preset. The raw files were moved unchanged from `/Users/laura/Downloads/` on 20 October 2026 and are retained under `raw/`.

The exact 308-row candidate upload and 113-row REF upload were reused. The export contains 306 scored rows and the exclusion register contains the same two length-121 candidates, so all 308 uploaded identifiers reconcile without replacement. The PDF displays seed 42, 99 shuffled controls, no target, AptaRank 0.1.0/schema 1.0.0/git `49a85609e352`, composite method `corpus_weighted_mean`, and scoring signature `95a49467ef3c6186`. The PDF does not independently display the 200 sampled-structure setting; that remains bound through the prepared Evaluation-preset run sheet and operator execution record.

The `publication_eligible: false` marker is ignored under the previously documented thesis-wide interface-bug decision.

## Provisional frozen-method analysis

The unchanged Section 6 calculations were applied to 153 complete EVAL/control pairs across all 79 pre-rejection clusters, using 10,000 cluster-bootstrap replicates with zero undefined or imputed replicates.

- Median paired EVAL-minus-control difference: 0.108; cluster-bootstrap 95% CI 0.064 to 0.164.
- Mean paired difference: 0.083.
- Descriptive AUROC: 0.638; cluster-bootstrap 95% CI 0.555 to 0.717.
- Wilcoxon signed-rank: W+ = 7,959; two-sided p = 0.000164702.
- Shuffle pass: 15/153 EVAL cores (9.8%) and 9/153 controls (5.9%).
- Paired shuffle-pass difference: 3.9 percentage points; cluster-bootstrap 95% CI -3.2 to 11.1 percentage points.

The aptamer-likeness scores and ranks are exactly identical to the historical Standard export for all 306 scored candidates. Shuffle outcomes changed for 14 candidates when the candidate-specific null increased from 20 to 99 shuffles: 11 changed from fail to pass and three from pass to fail. This is a technical descriptive comparison, not pooled inference and not a basis for selecting between runs.

The rigorous result supports moderate Tier 1 separation from exact-length uniform RNA. The shuffle-pass difference remains weak and uncertain because its confidence interval includes no difference. This does not establish binding, affinity, specificity, inhibition, target recognition or experimental function.

Derived outputs are under `derived/analysis_v1/` and remain the unchanged aggregate-only files that were independently reviewed. The closure record is under `closure/`. Laura explicitly approved and closed the rigorous Section 6 result on 20 October 2026. This scientific closure does not claim that the repository changes were Git-committed or pushed.

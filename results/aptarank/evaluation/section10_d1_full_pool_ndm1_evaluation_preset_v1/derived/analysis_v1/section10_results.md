# Section 10 D1 full-pool NDM-1 validation and supervisor-review pool

Status: `PROVISIONAL_SECTION10_VALIDATION_ANALYSIS_AND_REVIEW_POOL_AWAITING_INDEPENDENT_REVIEW_AND_EXPLICIT_RESULT_COMMITMENT`

## Validated accounting and attrition

| Stage | Records | Pass rate from previous stage | Retained from 30,000 uploads |
|---|---:|---:|---:|
| uploaded sequences | 30,000 | n.a. | 100.0000% |
| valid scored records | 29,583 | 98.6100% | 98.6100% |
| exact top 1000 target results | 1,000 | 3.3803% | 3.3333% |
| top 1000 shuffle pass | 558 | 55.8000% | 1.8600% |
| shuffle pass and favourable compatibility | 137 | 24.5520% | 0.4567% |
| tier1 ordered jointly eligible | 137 | 100.0000% | 0.4567% |
| supervisor review pool after cap | 100 | 72.9927% | 0.3333% |

The tool scored 29,583 of 30,000 uploads and recorded 417 technical exclusions: 11 below 20 nt and 406 above 100 nt. No row is otherwise missing, and no exclusion was replaced or replenished. Across all 29,583 scored candidates, 1,486 (5.0232%) have shuffle `pass`; candidates outside the Tier 1 top 1,000 have no Tier 2 compatibility evaluation and therefore cannot enter the frozen pool.

Within the exact top 1,000, 558 candidates (55.8000%) have shuffle `pass`. The compatibility distribution is 69 `strong`, 167 `moderate` and 764 `weak`; 236/1,000 (23.6000%) are in the pooled favourable class. Applying both mandatory gates leaves 137/1,000 jointly eligible candidates (13.7000%). Tier 1 ordering retains 100 and caps out 37.

## Deterministic supervisor-review pool

The retained pool contains 33 `strong` and 67 `moderate` candidates. It contains 58 candidates from D1 training seed 43 and 42 from seed 44. Tier 1 ranks span 2 to 616; the first capped-out jointly eligible candidate is rank 619.

`Strong` does not precede `moderate`. The bands are pooled only for eligibility; Tier 1 rank supplies the order, with ascending opaque ID already enforcing exact Tier 1 score ties in the validated tool export. No Tier 1/Tier 2 numerical composite was formed.

## Score analysis

| Population | n | Tier 1 mean | Tier 1 median | Tier 1 IQR |
|---|---:|---:|---:|---:|
| All scored | 29,583 | 0.436 | 0.423 | 0.310–0.558 |
| Exact top 1,000 | 1,000 | 0.793 | 0.782 | 0.763–0.816 |
| Jointly eligible | 137 | 0.804 | 0.796 | 0.770–0.832 |
| Supervisor-review pool | 100 | 0.820 | 0.816 | 0.791–0.841 |

Across the exact top 1,000, Spearman rho between Tier 1 and the exported control percentile is 0.007856, matching the PDF's rounded 0.008 (PDF p = 0.804). The association is negligible and is not used in selection.

## Required target limitation

> This cavity is oddly shaped: its robust extent and equivalent-sphere diameter disagree by more than 2×. The geometric comparison assumes a roughly convex pocket.

The warning applies to every retained candidate. The compatibility annotation remains a coarse target-specific eligibility gate rather than evidence of binding or a fine-grained ordering signal.

## Decision boundary

This is a supervisor-review pool of computationally prioritised D1 candidates. Manual review is still pending. Under v3.9, the biologist-supervisor assessment may remove candidates and retain at most 50 for future experimental consideration, but it cannot add a candidate outside this deterministic pool. Every retain/not-retain decision, reviewer, date and reason must be recorded.

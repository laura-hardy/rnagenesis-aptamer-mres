# M10 Section 5 generator evaluation results

**Status:** `section5_calculation_complete`  
**Published:** 19 October 2026, invocation `2026-10-19T02:02:55Z` to `2026-10-19T02:58:06Z`  
**Result directory:** `results/fine_tuning/m10_generator_evaluation/m10_section5_production_v1/`  
**Scope:** Section 5 of the active evaluation plan. B1 versus D1 is the primary comparison. AptaRank was not run.

The corrected authorized invocation called `generator_eval_m10.run_authorized_production` once. It exited 0. Function elapsed time was 3310.761914 seconds. EVAL was opened once. The sequence-free validation record reports `VALIDATION_OVERALL pass`. This note cites that published report and manifest. It does not recompute the metrics.

## Production provenance

| File | Mode | Bytes | SHA-256 |
|---|---:|---:|---|
| `m10_derived_evidence.json` | `0600` | 186484548 | `9ba39df6e9c24196d35958613f373f92bac6bf720acde6a07e3880d9d6dc42ee` |
| `m10_sequence_free_report.json` | `0644` | 1724287 | `20e8daf7b2decb92299a9c0274273fd764db94c63c46e603c204cc7b0f09547f` |
| `m10_run_manifest.json` | `0644` | 9709 | `5d828d918ff8d79e66d65181584175c87d125f69f59b76b2e3a48e78395803d0` |
| `SHA256SUMS` | `0644` | 276 | `95f096762d76026f643f245eefae8cbb540c0f36f8b7df50fefa4e1fe09576ee` |

The directory mode is `0700` and contains those four files. Report schema `generator-eval-m10-production-v1`, layer `sequence_free_aggregate_report`, `contains_sequences` false. Manifest schema `generator-eval-m10-production-manifest-v1`.

The runner is `scripts/modelling/generator_eval_m10.py`, SHA-256 `02735f84f264b3b0cfe7f9b5d2ab704846bb5840f9235707197e2999f9152c77`. The frozen metric specification is SHA-256 `2b0679b999235cc838298563448b01ef73f5fdd5132c5ddd3d9944f301f5c824`, `freeze_status` `frozen`, production-ready. The interpreter is `/home/laura/miniconda3/envs/rnagenesis-h200/bin/python`, Python 3.8.13. Folding is the recorded `RNA.fold(sequence)` call in ViennaRNA 2.7.0, build `py38pl5321hd78456e_0`, distinct from AptaRank ViennaRNA 2.7.2. The code set no model detail.

Invocation log SHA-256 `fe6fd9f617d89552159d56781fce6ce218316a0c0411c41d8ea602374a87d44c`. Sequence-free validation log SHA-256 `e9fff42849f027456c02bdc70e7659dd04531b8cb57ca742797b484dd4abc3c4`. Both remain at `/home/laura/m10_review_archives/m10_section5_production_v1_corrected_20261019T025806Z/`.

## EVAL counts and denominators

EVAL SHA-256 `ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015` matched the frozen digest. The single read supplied 181 scientific identities, 154 unique cores, and 79 clusters (89 short cores and 65 long cores). Each unique core has weight 1. The 79 clusters do not weight the formulas.

Generated closeness and diversity use valid attempt rows, with duplicate attempts retained. The reference denominator on every closeness metric below is the 154 unique cores.

| Condition | Raw attempts | Valid outputs | Unique valid | Invalid | Duplicate excess |
|---|---:|---:|---:|---:|---:|
| B0 | 30080 | 30080 | 30080 | 0 | 0 |
| B1 | 30000 | 30000 | 29983 | 0 | 17 |
| B2 | 30000 | 30000 | 30000 | 0 | 0 |
| D1 | 30000 | 30000 | 30000 | 0 | 0 |

`successfully_parsed_outputs` equals the raw-attempt count in every condition. Legacy `parsed_outputs` is the internal schema-valid-record audit field and has the same counts. No rows were dropped. D1 is 15,000 attempts from training seed 43 in matched block A and 15,000 from training seed 44 in matched block B. Block A uses generation seeds 800000–800162 (163 seeds). Block B uses generation seeds 900000–900163 (164 seeds). Each block has 15,000 paired rows. The blocks are descriptive. They are not training replicates and they are not significance-test units.

## Primary equal-seed B1–D1 comparison

The primary D1 figures are the equal-training-seed mixture. That mixture is a labelled descriptive pool of the two seed-specific valid-output distributions. It is not a confidence interval. B1 is the 30,000-attempt condition. Lower is closer. The three metric-level difference relations are `d1_closer`. The overall directional-consistency label is `d1_closer_or_tied`. That overall label does not replace the three metrics and is not a score, a test, a threshold, or a vote count.

| Metric | B1 | Equal-seed D1 | D1 minus B1 |
|---|---:|---:|---:|
| Nearest-EVAL longer-length-normalized edit distance, median | 0.4675324675324675 | 0.4647887323943662 | -0.002743735138101333 |
| Nucleotide total variation to EVAL | 0.055273039792155046 | 0.020334843347087753 | -0.03493819644506729 |
| Dinucleotide total variation to EVAL | 0.08219256648620037 | 0.05830663196664806 | -0.02388593451955231 |

D1 is closer than B1 on all three frozen EVAL closeness metrics. The nearest-edit improvement is small. The composition shifts are larger.

The attempt-pooled D1 condition has the same nearest-edit median, 0.4647887323943662. Its nucleotide total variation is 0.02032207940317897 and its dinucleotide total variation is 0.05829354874576137. Those pooled values are also closer to EVAL than B1.

Across the two D1 seeds the observed ranges, which are not confidence intervals, are 0.4634146341463415–0.4666666666666667 for nearest-edit median, 0.017300953771699018–0.0233687329224765 for nucleotide total variation, and 0.05614764392153879–0.062428493295797076 for dinucleotide total variation.

## Matched blocks A/seed 43 and B/seed 44

The training seed is coupled to the technical block and to its generation-seed range. Block A is seed 43. Block B is seed 44. D1 is closer than B1 on all three metrics in both blocks.

Block A, seed 43, 15,000 valid rows each. B1 has 14,995 unique valid outputs. D1 has 15,000.

| Metric | B1 | D1 | D1 minus B1 |
|---|---:|---:|---:|
| Nearest-EVAL edit distance, median | 0.4675324675324675 | 0.4666666666666667 | -0.0008658008658008476 |
| Nucleotide total variation | 0.05429435940043627 | 0.0233687329224765 | -0.030925626477959767 |
| Dinucleotide total variation | 0.08169678193262776 | 0.062428493295797076 | -0.019268288636830687 |

Block B, seed 44, 15,000 valid rows each. B1 has 14,996 unique valid outputs. D1 has 15,000.

| Metric | B1 | D1 | D1 minus B1 |
|---|---:|---:|---:|
| Nearest-EVAL edit distance, median | 0.4675324675324675 | 0.4634146341463415 | -0.004117833386126035 |
| Nucleotide total variation | 0.05625172969510181 | 0.017300953771699018 | -0.03895077592340279 |
| Dinucleotide total variation | 0.0826883559474437 | 0.05614764392153879 | -0.02654071202590491 |

## B2

B2 is the secondary non-neural data-scale comparator. It uses one empirical-null seed, 42, and 30,000 valid unique outputs. It is outside the matched blocks. Lower is closer.

| Metric | B2 | Equal-seed D1 |
|---|---:|---:|
| Nearest-EVAL edit distance, median | 0.4634146341463415 | 0.4647887323943662 |
| Nucleotide total variation | 0.011854080105028475 | 0.020334843347087753 |
| Dinucleotide total variation | 0.051472437960854336 | 0.05830663196664806 |

B2 is numerically closer than D1 on all three closeness metrics. The same order holds against the attempt-pooled D1 values. On the folding summaries below, the B2 medians also sit closer to the EVAL medians than the D1 medians do. That limits any claim of higher-order learned aptamer behaviour.

## B0

B0 stays on a separate historical length panel. It has 30,080 valid unique outputs, nominal maximum length 37, and observed cleaned length 36 for every row. The requested biological length is unavailable, so the exact-hit rate is not applicable. B0 is excluded from the matched B1–D1 blocks. Its generation seeds are the historical range 4201–4210, ten seeds, and those seeds are not training replicates.

| Metric | B0 |
|---|---:|
| Nearest-EVAL edit distance, median | 0.45098039215686275 |
| Nucleotide total variation | 0.3220596371247267 |
| Dinucleotide total variation | 0.44936490965465625 |

These are panel values for the historical 37-nt regime. They are not a matched-length B1–D1 estimate.

## Validity, exact diversity, length adherence, and frozen TRAIN

Every condition is 100% valid: `actual_attempt_level_validity_rate` is 1.0, invalid outputs are 0, and the valid non-empty A/C/G/U fraction is 1.0. Both D1 seeds are 15,000 valid outputs out of 15,000 attempts.

Exact-duplicate diversity is the only diversity result. D1, B2, and B0 have duplicate excess 0. D1 has no exact duplicates. B1 has 17 duplicate-excess attempts, 29,983 unique valid outputs, unique fraction 0.9994333333333333, and largest multiplicity 4. The B1 multiplicity histogram is 29,969 sequences at multiplicity 1, 12 at multiplicity 2, one at multiplicity 3, and one at multiplicity 4. Duplicate rows were retained. The unique-only count is a labelled sensitivity.

Length adherence uses raw attempts as the denominator. Length excess is 0 wherever a requested length applies.

| Condition | Exact-length hits | Rate | Shortfall attempts |
|---|---:|---:|---:|
| B1 | 28967 / 30000 | 0.9655666666666667 | 1033 |
| D1 | 28995 / 30000 | 0.9665 | 1005 |
| B2 | 30000 / 30000 | 1.0 | 0 |
| B0 | not applicable | requested length unavailable | not applicable |

The observed D1 exact-hit rates across the two seeds run from 0.9574 to 0.9756. That range is not a confidence interval.

Frozen M9A TRAIN summaries were cited and were not recomputed. TRAIN was not reopened. Exact TRAIN overlap is zero for every condition: row-leakage and distinct-sequence numerators are 0 for B0, B1, B2, and D1, and for D1 seeds 43 and 44. Median nearest-TRAIN normalized edit distance is 0.4444444444444444 for B1 and 0.44 for D1, so D1 is slightly closer to TRAIN than B1. The B2 median is 0.4411764705882353. The separate B0 median is 0.4166666666666667. The exact-summary SHA-256 is `f7d10f7f41777a091cc2b2bf3dfeec555d5e8d84b3b89850328be7cdcf15e0d3`. The nearest-summary SHA-256 is `c68fa997207a657a7049e53dd074e8d593333f84152008d631cae0d6565c1d66`.

## Mixed structural result

Each distinct valid sequence was folded once. Generated quantiles use valid attempt rows with duplicate-attempt weighting. The 154 EVAL cores were folded once each. The report records `distinct_fold_count` 120216, with row dispositions `computed_on_this_row` 120062, `reused_from_earlier_row` 18, and `not_folded` 0. No structure-distance metric is defined. The values below are medians.

| Summary | EVAL | B1 | D1 | B2 |
|---|---:|---:|---:|---:|
| MFE | -11.800000190734863 | -8.300000190734863 | -8.699999809265137 | -10.199999809265137 |
| MFE per nucleotide | -0.2267857108797346 | -0.16052631327980443 | -0.175 | -0.19874999523162842 |
| Paired fraction | 0.5052631578947369 | 0.4727272727272727 | 0.4675324675324675 | 0.49382716049382713 |

D1 moves toward EVAL for MFE and normalized MFE and slightly away for paired fraction, so the structural result is mixed. B2 is descriptively closer to EVAL than D1 on all three folding summaries. The separate B0 medians are MFE -3.5, MFE per nucleotide -0.09722222222222222, and paired fraction 0.3888888888888889. The observed D1 seed ranges for the three medians are MFE -8.899999618530273 to -8.600000381469727, MFE per nucleotide -0.17857142857142858 to -0.1716981204050892, and paired fraction 0.4675324675324675 to 0.4691358024691358.

## Limitations

- Two D1 training seeds were achieved. The absent third seed remains a resource and time limitation.
- The training seed is coupled to the technical block and the generation-seed range, so the pooled D1 condition does not support a clean replicate-level separation of seed and block.
- B2 has a single empirical-null seed.
- The 79 EVAL clusters are unweighted. They are a design fact and a limitation, and this run did not resample them.
- The report produces no confidence interval, bootstrap, hypothesis test, or EVAL-cluster resampling. Observed ranges are not confidence intervals.
- There is no aggregate generator-quality score. The three closeness metrics stay separate.
- These results support no binding, affinity, selectivity, or target-specific claim, including no NDM-1-specific generation claim.

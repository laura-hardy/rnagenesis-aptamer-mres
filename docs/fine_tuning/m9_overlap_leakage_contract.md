# M9A overlap and leakage contract

**Status: `FROZEN_DEFINITIONS_SYNTHETIC_ONLY_PRODUCTION_INPUTS_UNOPENED`.**

This stage freezes the cross-condition overlap and TRAIN-leakage definitions. It does not complete M9A, M9B, or M9C. The implementation accepts in-memory parsed rows and caller-supplied TRAIN cores. It does not open a production ledger, TRAIN, VALIDATION, REF, EVAL, a model, a checkpoint, a structure resource, or an AptaRank resource. A synthetic run is not production validation.

The contract file is `config/modelling/generator_eval_overlap_leakage_contract.json`, identity `m9a-overlap-leakage-definitions-v1`. Its SHA-256 is `6aeaa2338776cbe7aceffef63ee4ca7dfd7ed3643aa7d1e400fd54a02d113535`.

The in-memory implementation is `scripts/modelling/generator_eval_overlap_leakage.py`. It has no filesystem production entry point and no production TRAIN loader.

## Evidence referenced without reopening it

| Item | Value |
| --- | --- |
| Parser | `m9-biological-parser-v1` |
| Adapter | `m9-source-adapter-v2` |
| Runner commit | `378f574b1620a9ff999082262868bffbe647d063` |
| Hardening commit | `f703a8c721384e821337eba9a59093918f8decfe` |
| Evidence commit | `1c74fb9b3c92247b524dbe40a744f59525d18bd2` |
| Production manifest SHA-256 | `9aa5f60f939a8b25d031967ed3466a26d9d8e2d0610c76ec0b5db4cb43c2cc80` |
| Combined ledger SHA-256 | `d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e` |
| Valid canonical attempt rows | 120,080 |
| Governing plan SHA-256 | `fc6963f01f7d4ab311774865bda15626facdb753ffa0db06b01b338d88162b51` |

Within-condition duplicates occurred only in B1. Cross-condition overlap and TRAIN leakage remain uncomputed on those production rows. REF and EVAL remain closed.

The broader GEP-2 metric specification `config/modelling/generator_eval_metric_spec.json` (`generator-eval-metric-spec-gep2-draft-r4`) remains draft.

`overall.distinct_valid_sequences = 120063` stays labelled as the sum of the within-condition distinct counts. It is not global distinctness and is not reused as `|S_B0 ∪ S_B1 ∪ S_B2 ∪ S_D1|`.

## Cross-condition overlap

The input population is valid canonical parsed rows. Invalid attempts remain in attempt accounting and do not enter a valid-row denominator. A zero denominator makes the corresponding rate null. The numerator and denominator are still reported. The rate does not become zero.

Every unordered pair among B0, B1, B2, and D1 is reported in both directions. For source A and target B, the numerator is the number of valid rows in A whose parsed sequence occurs at least once among valid sequences in B. The denominator is the number of valid rows in A. A repeated sequence contributes once per source row and only membership when that condition is the target. Duplicate rows are not removed or downweighted.

Distinct-sequence sensitivity reports `|S_A ∩ S_B|`, each condition's distinct coverage, `|S_A ∪ S_B|`, and Jaccard overlap. Jaccard is null when the union is zero.

Global sequence-free accounting reports the true four-condition union, the counts of distinct sequences in exactly 1, 2, 3, or 4 conditions, and one count for each observed nonempty membership pattern. Those pattern counts sum to the union. Summaries do not emit sequence strings or sequence hashes.

B0 is calculated with the same formulas and marked `external_comparator`. It is not pooled into a B1/B2/D1 aggregate or causal comparison.

## Exact TRAIN leakage

TRAIN stays inaccessible. The caller supplies an in-memory collection of distinct canonical `^[ACGU]+$` cores. The collection must be nonempty. A duplicated supplied core fails closed instead of being silently removed. There is no partial match, substring match, identity threshold, or use of the historical 0.01 guardrail as a decision threshold.

The row numerator is the number of valid generated rows whose full parsed sequence belongs to that core set. The row denominator is the number of valid generated rows. Distinct-sequence sensitivity is the number of matching distinct generated sequences divided by the number of distinct valid generated sequences.

For D1, the report contains the seed-43 valid-conditional row rate, the seed-44 valid-conditional row rate, the unweighted arithmetic mean of those two rates, the observed minimum–maximum range, and the actual-attempt pooled numerator, denominator, and rate under a separate label. There is no confidence interval, bootstrap, or hypothesis test. A missing expected seed or a zero valid denominator fails closed and is not replaced with the pooled estimate.

## Nearest TRAIN distance

The existing nearest-TRAIN definition is retained for later execution on caller-supplied cores. No production TRAIN loader is added.

Global Levenshtein distance is divided by the longer sequence length. Maximum edit similarity is one minus that nearest normalized distance. Edit similarity is not sequence identity. The distance is computed once per distinct generated sequence and projected back to rows. Quantiles use the frozen row convention `int(round(p * (n - 1)))` on values sorted ascending.

D1 seed-specific distance summaries are reported. The pooled equal-mixture distance quantile reuses the existing weighted-quantile rule `inclusive_cumulative_weight_exact_v2`, with each valid row weighted by `1 / (participating seeds × valid rows for that seed)`. That pooled quantile is absent when a required D1 seed is missing or a seed has a zero valid-row count, because the existing weight is undefined at a zero count and dropping the seed would be a different rule.

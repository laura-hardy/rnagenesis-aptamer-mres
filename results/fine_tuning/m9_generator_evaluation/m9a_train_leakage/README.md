# M9A TRAIN leakage

Sealed production execution of `sealed_train_leakage` succeeded once and was not retried. The invocation recorded exit code 0, `sealed_invocation_attempts=1`, and `retry_performed=false`.

The runner commit is `532bbba34f3918b6f5fc3b4d09d48de0d92be54e`. The runner contract is `m9a-train-leakage-runner-v1` at `config/modelling/generator_eval_train_leakage_runner_contract.json`, SHA-256 `ef68b1575df4d770af2bdd622eeb84f647a18db9d4cbd115e0b8a60de5dce528`. The M9A contract is `m9a-overlap-leakage-definitions-v1` at `config/modelling/generator_eval_overlap_leakage_contract.json`, SHA-256 `6aeaa2338776cbe7aceffef63ee4ca7dfd7ed3643aa7d1e400fd54a02d113535`. The governing plan `docs/aptarank_full_mres_thesis_evaluation_plan.md` has SHA-256 `fc6963f01f7d4ab311774865bda15626facdb753ffa0db06b01b338d88162b51`.

## Input identities recorded in the manifest

This closeout did not reopen the combined ledger or the TRAIN sources. The identities below are the ones recorded in `m9_train_leakage_manifest.json`.

| Input | Identity |
| --- | --- |
| Combined ledger `m9_all_conditions_derived_attempt_ledger.jsonl` | SHA-256 `d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e`; 188,521,569 bytes; 120,080 rows (B0 30,080; B1, B2, and D1 30,000 each) |
| TRAIN CSV `ft_train.csv` | SHA-256 `84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0`; 1,201,524 bytes; 726 identity rows; 669 distinct cores |
| TRAIN text `corpus_final.txt` | SHA-256 `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d`; 37,700 bytes; 669 lines; equal to the CSV first-occurrence cores |

The comparison population is `corpus_final_text_equal_to_train_csv_first_occurrence_cores`. CSV rows were not silently deduplicated, and cores were not rewritten.

## Exact TRAIN leakage

Exact leakage is full parsed-string membership. Partial matches, substring matches, and an identity threshold are absent. Exact TRAIN leakage is zero for B0, B1, B2, and D1 at both the valid-row grain and the distinct-sequence grain.

| Condition | Row leakage | Distinct-sequence leakage |
| --- | ---: | ---: |
| B0 | 0/30,080 | 0/30,080 |
| B1 | 0/30,000 | 0/29,983 |
| B2 | 0/30,000 | 0/30,000 |
| D1 | 0/30,000 | 0/30,000 |

D1 seeds 43 and 44 each have zero exact leakage. Seed 43 is 0/15,000 at the row grain and 0/15,000 at the distinct-sequence grain. Seed 44 is 0/15,000 at both grains. The unweighted arithmetic mean of the seed-specific row rates is 0. The observed range across those seeds is 0 to 0. That range is an observed range. It is not a confidence interval.

## Nearest-TRAIN distance

Nearest-TRAIN distance is the global Levenshtein distance to the nearest supplied TRAIN core, divided by the length of the longer of the generated sequence and that core. The distance is computed once per globally distinct generated sequence and projected back to rows, conditions, and D1 seeds.

Maximum edit similarity is one minus the minimum nearest normalized distance. It is an edit-based similarity. It is not sequence identity.

B0 remains an external comparator. It is not pooled into a B1/B2/D1 aggregate and is not included in the causal comparison.

No threshold, bootstrap, confidence interval, or hypothesis test was introduced. The historical 0.01 guardrail was not used as a decision threshold.

## Access boundary

VALIDATION, REF, and EVAL were not accessed. Models, checkpoints, structure tools, and AptaRank were not accessed. The summaries emit no sequence strings, sequence hashes, attempt identifiers, nearest-neighbour identities, TRAIN identity ids, or target labels.

## Review

Independent local review passed. The review archive SHA-256 is `9af7253146647301fbbf5d0e765b4a104d1e5e263f1d27e451a069976720bc72`. Its inventory matches the three output hashes below.

## Hashes

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `m9_exact_train_leakage_summary.json` | 4,737 | `f7d10f7f41777a091cc2b2bf3dfeec555d5e8d84b3b89850328be7cdcf15e0d3` |
| `m9_nearest_train_distance_summary.json` | 8,889 | `c68fa997207a657a7049e53dd074e8d593333f84152008d631cae0d6565c1d66` |
| `m9_train_leakage_manifest.json` | 8,609 | `e2b97da3b1f39859c1d4fc3a652dd4abb6e4da5836e2a5e9c067ce1b87491d88` |

The manifest digest is the digest of the manifest file bytes. It is not embedded in the manifest.

## Completion

The generated JSON fields `m9a_complete=false` are intentionally immutable and do not self-certify the milestone. M9A became complete only when the exact-overlap evidence, TRAIN-leakage evidence, independent review, documentation, and this closure commit were all present.

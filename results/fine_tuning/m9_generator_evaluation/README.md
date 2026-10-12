# M9 production derived ledgers

Stage 4 parsed the sealed B0, B1, B2, and D1 generation attempts into derived attempt ledgers. It kept every row, counted exact duplicates only within each condition, and did not filter, drop, replenish, or compare conditions. It did not perform biological evaluation.

The biological parser is `m9-biological-parser-v1`. The source adapter is `m9-source-adapter-v2`.

The immutable pre-production freeze artifacts are:

- parser contract `config/modelling/generator_eval_parser_contract.json`, SHA-256 `a8cda86af2cd6aff52ed7929c1a8cdfe134394f9087c768a731e8597339fe872`
- source manifest `config/modelling/generator_eval_source_manifest.json`, SHA-256 `89be54f49b020027d58686ececfc1d743c16e58c0ed12d0b6bae269d36c4aa6c`

Production was executed by runner commit `378f574b1620a9ff999082262868bffbe647d063`. Closeout hardening is commit `f703a8c721384e821337eba9a59093918f8decfe`. The production manifest is the evidence of the execution. The manifest digest below was recomputed from the file bytes and is not embedded in the manifest.

## Outputs

| File | Rows | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `m9_b0_derived_attempt_ledger.jsonl` | 30080 | 41103236 | `4d35ea9e4980fa42e4dbefa08f80f49df39ca7517784ea1851ea20c3742fe6ef` |
| `m9_b1_derived_attempt_ledger.jsonl` | 30000 | 50998055 | `18d76af08e931dc46d59cba5c303a1824fced966337bb5cef06abcbb6bbaf935` |
| `m9_b2_derived_attempt_ledger.jsonl` | 30000 | 42878534 | `49ae765eef2aacb7ecc16a922cc663465a91f0e26f1abe8aff01eed7c6d86c06` |
| `m9_d1_derived_attempt_ledger.jsonl` | 30000 | 53541744 | `58cc3acb0e22d497521480d949ccb55237212bd8aec617f939471951c02deecd` |
| `m9_all_conditions_derived_attempt_ledger.jsonl` | 120080 | 188521569 | `d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e` |
| `m9_parsing_accounting_summary.json` | — | 4014 | `b06aaf5cf9d2938cf555c496990ba6d04ed4d385fc5c7a6d7071eb504df148d4` |
| `m9_production_manifest.json` | — | 7876 | `9aa5f60f939a8b25d031967ed3466a26d9d8e2d0610c76ec0b5db4cb43c2cc80` |

The five JSONL ledgers are ignored by Git and are retained as regenerable server-side artifacts. This README, the summary, and the manifest are the lightweight evidence.

## Accounting

| Condition | Attempts | Canonical-valid rows | Distinct valid sequences | Singleton rows | Duplicate-member rows | Repeated groups | Maximum multiplicity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | 30080 | 30080 | 30080 | 30080 | 0 | 0 | 1 |
| B1 | 30000 | 30000 | 29983 | 29969 | 31 | 14 | 4 |
| B2 | 30000 | 30000 | 30000 | 30000 | 0 | 0 | 1 |
| D1 | 30000 | 30000 | 30000 | 30000 | 0 | 0 | 1 |
| Overall | 120080 | 120080 | 120063 | 120049 | 31 | 14 | 4 |

D1 is 15,000 attempts from training seed 43 and 15,000 from training seed 44.

Every attempt was classified `valid_canonical_sequence`. Empty, unparseable, non-sequence, and parsed non-ACGU outcomes are zero in every condition. That canonical-valid result is syntactic validity only. It is not biological validity, binding, or structural quality.

`overall.distinct_valid_sequences = 120063` is the sum of the per-condition distinct counts, 30080 + 29983 + 30000 + 30000. It is not global distinctness. `overall.distinct_valid_sequences_are_within_condition_sums` is true. Within-condition duplicates occur only in B1. Cross-condition overlap was not computed.

The summary and manifest contain counts, digests, and provenance only. They contain no sequence strings. REF, EVAL, TRAIN, VALIDATION, models, and AptaRank were not accessed. Biological evaluation was not performed.

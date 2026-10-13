# M9C reference preparation

This directory is attempt 2. It is preserved superseded evidence. On 13 October 2026 the live AptaRank UI rejected the one-column file before Run because it was candidate-like. AptaRank did not accept the library, did not calibrate it, and did not score anything. No accepted count, dropped count, or control-bank fact was observed. Do not overwrite or delete this directory.

The corrected contract is schema `m9c-reference-upload-v3`. Publication attempt 3 is configured at `m9c_reference_preparation_attempt3` and has not been created. This record does not reopen REF. M9C is not complete, and EVAL remains locked.

The manifest digest below was recomputed from the file bytes and is not embedded in the manifest. Preparation was not run again for this record. The three file digests are unchanged.

## Attempts

Attempt 1 opened and verified REF, then failed before publication under the obsolete five-column assumption. That contract required `publication`. No output was published, and AptaRank was not run.

Attempt 2 published once. `publish_sealed_reference_preparation(invoke=True)` ran at HEAD `43ee64464b69952b57250cf9ebfcb91eb860c648`. The live UI later rejected that one-column file before Run. The directory remains the committed evidence of that superseded preparation.

## Source

The source REF SHA-256 is `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23`.

| Accounting | Count |
| --- | ---: |
| Source identity rows | 131 |
| Distinct sequence cores | 113 |
| Duplicate-core collapses | 18 |

The 18 later identity rows are duplicate-core collapses. They are not biological exclusions and they are not quality exclusions.

## Interface

The published upload is the superseded one-column CSV, `sequence`. The live UI requires `id,sequence,target_name,target_pdb_id` instead. This file does not carry `id`, `target_name`, `target_pdb_id`, or `source_reference`. The private provenance ledger is a project-only audit artifact and is not an AptaRank input.

## Outputs

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `reference_upload.csv` | 6281 | `4959bccf1e8ef535857ea451ceb83795ce09c2e6ad79a6ae10411d976d760f08` |
| `duplicate_provenance.jsonl` | 29214 | `ff3d7986029aeaf52f1ebfdceceba3d94d7136ca7d457c93f62398d01235a841` |
| `preparation_manifest.json` | 694 | `00c9479f5609cbe6f4bcc9388d1a2d9af74d46860333b680f6466384126e3b63` |

## Manifest

This manifest is historical attempt-2 evidence. It is not an attempt-3 manifest. Status is `REFERENCE_UPLOAD_PREPARED_APTARANK_NOT_RUN`. `publication_attempt` is 2. `production_ref_identity_verified` is true. `local_calibration` is false.

AptaRank was not run. The file was rejected before Run. `aptarank_ui_executed` is false. `observed_ui_accepted_count` and `observed_ui_dropped_count` remain null. No control-bank fact was observed.

## Review

The publication-evidence archive SHA-256 remains `4da503a1b4b9162da19f1c0862b285ae1e972e4d8c2f8196f38b2563b1d7cf57`. The upload, provenance ledger, and manifest bytes above are unchanged.

The upload CSV and the provenance ledger stay ignored. This README and the manifest are the committed evidence. This record does not complete M9C and does not unlock EVAL.

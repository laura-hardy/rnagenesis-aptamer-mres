# M9C reference preparation, attempt 3

This directory is publication attempt 3. The preparation manifest remains the reviewed publication record. The later UI acceptance is recorded here and in `results/fine_tuning/m9_generator_evaluation/m9c_live_deployment_validation/`. Do not overwrite or delete this directory. Attempt 2 stays the preserved superseded one-column preparation at `m9c_reference_preparation`.

The manifest digest below was recomputed from the file bytes and is not embedded in the manifest. Preparation was not run again for this record.

## Source

The source REF SHA-256 is `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23`.

| Accounting | Count |
| --- | ---: |
| Source identity rows | 131 |
| Distinct sequence cores | 113 |
| Duplicate-core collapses | 18 |
| Prepared upload rows | 113 |

The 18 later identity rows are duplicate-core collapses. They are not biological exclusions and they are not quality exclusions.

## Interface

The published upload is the four-column CSV `id,sequence,target_name,target_pdb_id`. The schema is `m9c-reference-upload-v3`. The private provenance ledger is a project-only audit artifact and is not an AptaRank input.

## Outputs

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `reference_upload.csv` | 17302 | `5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6` |
| `duplicate_provenance.jsonl` | 29214 | `ff3d7986029aeaf52f1ebfdceceba3d94d7136ca7d457c93f62398d01235a841` |
| `preparation_manifest.json` | 694 | `abaf33fa7dcebb853a8d3ce5c95f83139201fbbeed5c1a1269a1b8bbb1e382b7` |

## Manifest

Status is `REFERENCE_UPLOAD_PREPARED_APTARANK_NOT_RUN`. `publication_attempt` is 3. `production_ref_identity_verified` is true. `local_calibration` is false. Those fields are the preparation-time record. This note does not rewrite them.

## UI acceptance

The live AptaRank UI later accepted this upload. It accepted 113 reference aptamers and dropped 0. That observation belongs to the development run. Example-candidate scores from that run are not a scientific MRes result.

`publication_eligible` was false because no AptaRank provenance sidecar accompanied the REF upload. Laura decided that this implementation flag does not block M9C, because REF provenance is independently frozen in the project. No sidecar was added.

## Review

The upload CSV and the provenance ledger stay ignored. This README and the manifest are the files prepared for tracking. This record does not complete M9C and does not unlock EVAL.

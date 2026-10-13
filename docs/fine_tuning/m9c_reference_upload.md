# M9C-1 reference-upload policy

| Item | Value |
|---|---|
| Status | `POLICY_FROZEN_FOUR_COLUMN_REFERENCE_UPLOAD_ATTEMPT3_NOT_PUBLISHED`. This is the contract's pre-publication state for attempt 3. A preparation manifest does not copy it. |
| Manifest status | `REFERENCE_UPLOAD_PREPARED_APTARANK_NOT_RUN`, with `publication_attempt` 3 |
| Stage | M9C-1. The rest of M9C is not complete. |
| Schema | `m9c-reference-upload-v3` |
| Contract | `config/modelling/aptarank_reference_upload_contract.json`, SHA-256 `34912929e77a0a835a01e36ba0291160b49b60dcdfb12a2d2aeb57090c794d02` |
| Previous contract | SHA-256 `980e7d1b9ce8a8c4c86a88dc99df280f05485b7c4fb2fdfd600fdea7a0665f9e`, schema `m9c-reference-upload-v2` |
| Plan | `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md`, version 3.3, SHA-256 `b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe` |
| Finished-upload validator | `validate_reference_upload` in `scripts/modelling/aptarank_reference_upload.py` |
| Preserved source parser | `scripts/modelling/aptarank_io_preflight.py`, SHA-256 `eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01` |

This note records the user-observed live AptaRank UI of 13 October 2026 and freezes the reference-library upload to that interface. It does not reopen REF, create the attempt-3 directory, open EVAL, open a production candidate source, or run AptaRank. No detail below is a scientific result.

## Live UI observation, 13 October 2026

The reference-library header required by the UI is exactly `id,sequence,target_name,target_pdb_id`.

The one-column attempt-2 file was rejected before Run as candidate-like. AptaRank did not accept the library, did not calibrate it, and did not score anything. No observed accepted count, dropped count, or control-bank fact exists yet.

Candidate input accepts a CSV with `sequence` and an optional `id`, plain text, or FASTA. Candidate sequences must be 20–100 nt. The UI accepts `T` as `U`. The MRes policy continues to provide canonical uppercase A/C/G/U and does not rely on that conversion. This observation does not change candidate-upload or shortlist-export behavior.

## Reference-library header

`validate_reference_upload` accepts a finished CSV only when the header is exactly `id,sequence,target_name,target_pdb_id`. IDs are unique and nonempty. Sequences are unique canonical uppercase A/C/G/U. Target names are nonempty. The `target_pdb_id` column is required, and a blank cell is preserved when the source has no PDB. The validator does not invent a structure identifier, strip a cell, uppercase a cell, or convert `T` to `U`.

`source_reference`, `publication`, and any additional column are refused. A one-column `sequence` file is not a reference library.

The retained first identity row is mapped as follows:

| Upload column | Source column |
|---|---|
| `id` | `scientific_identity_id` |
| `sequence` | `sequence_core` |
| `target_name` | `canonical_target_name` |
| `target_pdb_id` | `pdb_id` |

A later identity does not replace any of those four fields.

## Upload grain

The frozen source is the 131-identity REF CSV, SHA-256 `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23`, at the repository-relative path `data/processed/ref.csv`. Its header is the 85-column S5E clustered-corpus schema. `ft_split` is not part of that header.

Preparation walks that file in its existing order and keeps one row for each distinct `sequence_core`. The procedure remains 131 source identity rows, 113 distinct cores, and 18 duplicate-core collapses. The expected AptaRank UI result is still 113 accepted rows and zero dropped rows. That figure is an expectation, not an observed UI count. `aptarank_ui_executed` stays false, and both observed UI counts stay null. The 18 later identity rows are duplicate-core collapses. They are not biological exclusions and they are not quality exclusions. Sealed preparation that does not match this REF identity stops M9C. Matching the REF digest verifies the production file. It does not record an AptaRank result.

The private duplicate-provenance ledger is a project-only audit artifact. It is never an AptaRank input. It has one JSON object per retained core, in first-occurrence order. Each object has a deterministic 1-based `upload_row_number`, the retained id, every contributing source identity in file order, and the later identities that collapsed into the core. The ledger does not contain sequence text.

No other row is removed. Case, whitespace, and alphabet are not normalized. `T` is not converted to `U`. No length filter is applied to the reference upload. A malformed schema, a noncanonical core, a conflicting row count, a duplicate identity, a missing scientific identity, a missing target name, or a digest mismatch fails closed.

## Attempt 2

Attempt 2 published the one-column file at `/home/laura/rnagenesis-mres-worktrees/generator-eval-prep/results/fine_tuning/m9_generator_evaluation/m9c_reference_preparation`. That directory and its committed evidence stay in place. The live UI rejected the file before Run. The directory is a superseded UI-rejected preparation. This correction does not overwrite or delete it.

`reference_upload.csv` remains 6281 bytes, SHA-256 `4959bccf1e8ef535857ea451ceb83795ce09c2e6ad79a6ae10411d976d760f08`. `duplicate_provenance.jsonl` remains 29214 bytes, SHA-256 `ff3d7986029aeaf52f1ebfdceceba3d94d7136ca7d457c93f62398d01235a841`. `preparation_manifest.json` remains 694 bytes, SHA-256 `00c9479f5609cbe6f4bcc9388d1a2d9af74d46860333b680f6466384126e3b63`. Its schema is `m9c-reference-upload-v2` and its `publication_attempt` is 2.

## Attempt 3

The corrected publication destination is `/home/laura/rnagenesis-mres-worktrees/generator-eval-prep/results/fine_tuning/m9_generator_evaluation/m9c_reference_preparation_attempt3`. A generated manifest records `publication_attempt` 3 and status `REFERENCE_UPLOAD_PREPARED_APTARANK_NOT_RUN`. That status means the file is prepared and has not been run in AptaRank. This correction has not created that directory and has not invoked publication.

## First failed publication attempt

`publish_sealed_reference_preparation(invoke=True)` was invoked once against commit `3d5a4beafc723ab154a2ff7d3a6d6835841b3b48` and contract SHA-256 `eb082923fbd79ccc05a9833e0f18e40094e8384bd2104392eee6cd46bc55f591`. REF was opened and verified. Preparation stopped because the obsolete five-column contract required `publication` (`missing_required_field`). No output was published. AptaRank was not run. That five-column publication was not retried. Attempt 2 was a separate one-column publication.

## Recordkeeping

`production_inputs_opened` and `ref_opened` are true because attempts 1 and 2 opened and verified REF. `scientific_result`, `eval_opened`, `production_candidates_opened`, `local_calibration`, `local_calibration_substitute`, `aptarank_execution`, and `deployment_verified` stay false.

`external_ref.locator` is `opened_and_verified_in_attempts_1_and_2_attempt3_not_invoked`.

The contract status is `POLICY_FROZEN_FOUR_COLUMN_REFERENCE_UPLOAD_ATTEMPT3_NOT_PUBLISHED`. A generated preparation manifest does not copy that status. Its status is `REFERENCE_UPLOAD_PREPARED_APTARANK_NOT_RUN`, and `publication_attempt` is 3. Both fields are validated before publication.

`outputs.publication_invoked`, `outputs.attempt3_directory_created`, and `outputs.sealed_entry_point_invoked` stay false. Those values are this revision's pre-publication state. They do not deny that attempts 1 and 2 opened REF, or that attempt 2 published the superseded directory.

## Supersession

Frozen M9B artifacts stay historical evidence, superseded for this reference upload by the 13 October 2026 live UI observation. ARP-1 still records the five reference columns in `config/modelling/aptarank_io_spec.json`, SHA-256 `46ba6c8be873dad4c086e9f6b889b51702ba31212fa502d00f26e267a22da732`, and `scripts/modelling/aptarank_io_preflight.py`, SHA-256 `eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01`. The evidence contract, SHA-256 `0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b`, is likewise unchanged. Historical M9B results are not rewritten. Candidate-upload and shortlist-export behavior is unchanged. The one-column attempt-2 interface is also superseded.

## Calibration and target mapping

AptaRank performs its own single pooled empirical REF calibration. The 13 October 2026 UI run did not accept or calibrate a library and did not score anything. This package does not implement that calibration and does not substitute a local one.

The frozen target mapping is recorded and was not reopened:

| Artifact | SHA-256 |
|---|---|
| Structure file | `2e185a205c9be0bf76484e8ffb96ae225880723ed68eaaf25dffbbccaf01ff51` |
| Selection record | `08f0c96af349ce4909d40c3004804317661777f72828cd807823341e0e4f0d04` |
| AptaRank target upload | `46471bb0643125ce86300ec050d6f0d3a09faa1d06dc325141c67cd1acdd5922` |

The target-upload digest is stored separately from the structure-file digest and the selection-record digest. Verifying it requires the caller to supply those bytes. The files themselves are not opened here.

## Boundary

`prepare_reference_upload` accepts in-memory bytes. A filesystem path is refused. Sealed review remains authorized for the verified REF file, 211,993 bytes, SHA-256 `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23`. `prepare_sealed_reference` remains uninvoked and returns before any external path is opened. `write_sealed_preparation_outputs` atomically writes caller-supplied preparation bytes and does not call that entry point.

The only production publication destination is `/home/laura/rnagenesis-mres-worktrees/generator-eval-prep/results/fine_tuning/m9_generator_evaluation/m9c_reference_preparation_attempt3`. The attempt-2 directory, any other `results/` path, every `data/` destination, a symlink, and any existing destination, including an empty directory, are refused. `publish_sealed_reference_preparation` runs only when its invocation flag is passed. It finishes the contract and destination preflight before opening REF, verifies the pinned REF bytes, prepares the four-column upload, private provenance ledger, and manifest, writes those three files into a temporary sibling, rereads and checks the bytes and digests, and publishes the directory with one `RENAME_NOREPLACE` rename. A failure removes only the temporary directory created by that invocation. The upload CSV and provenance JSONL stay ignored by Git. The manifest is not ignored, so it can be reviewed while untracked. This correction has not invoked this entry point and has not created the attempt-3 directory. The no-argument command checks the pins and prints the status. It does not publish the directory, and it does not run an end-to-end rehearsal.

Unit tests use synthetic fixtures and temporary directories only. This correction did not reopen REF, create attempt-3 outputs, open EVAL or production candidates, or invoke AptaRank.

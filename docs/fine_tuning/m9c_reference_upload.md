# M9C-1 reference-upload policy

| Item | Value |
|---|---|
| Status | `POLICY_FROZEN_ONE_COLUMN_REFERENCE_UPLOAD_PUBLICATION_NOT_RETRIED` |
| Stage | M9C-1. The rest of M9C is not complete. |
| Schema | `m9c-reference-upload-v2` |
| Contract | `config/modelling/aptarank_reference_upload_contract.json`, SHA-256 `732f53607231e9d61dccb5a6e625a6c1c1402e3e6ab1331ca6791aa1507684a3` |
| Previous contract | SHA-256 `eb082923fbd79ccc05a9833e0f18e40094e8384bd2104392eee6cd46bc55f591`, schema `m9c-reference-upload-v1` |
| Plan | `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md`, version 3.3, SHA-256 `b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe` |
| Finished-upload validator | `validate_reference_upload` in `scripts/modelling/aptarank_reference_upload.py` |
| Preserved source parser | `scripts/modelling/aptarank_io_preflight.py`, SHA-256 `eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01` |

This note corrects the AptaRank reference upload to the user-confirmed live interface. It does not reopen REF, retry publication, open EVAL, open a production candidate source, or run AptaRank. No detail below is a scientific result.

## Live upload interface

The AptaRank reference upload accepts exactly one CSV column named `sequence`. It does not accept `id`, `target_name`, `target_pdb_id`, or `source_reference`. Target configuration is supplied separately. The upload does not carry provenance fields, and this package does not invent any.

`validate_reference_upload` accepts a finished CSV only when the header is exactly `sequence`, every data row is one canonical uppercase A/C/G/U sequence, and the sequences are unique. A metadata column, a duplicate sequence, lowercase, `T`, or surrounding whitespace fails closed. The validator does not strip, uppercase, or rewrite a cell.

## Upload grain

The frozen source is the 131-identity REF CSV, SHA-256 `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23`, at the repository-relative path `data/processed/ref.csv`. Its header is the 85-column S5E clustered-corpus schema. `ft_split` is not part of that header.

Preparation walks that file in its existing order and keeps one row for each distinct `sequence_core`. The expected AptaRank UI result is 113 accepted rows and zero dropped rows. That figure is an expectation, not an observed UI count. `aptarank_ui_executed` stays false, and both observed UI counts stay null. The 18 later identity rows are duplicate-core collapses. They are not biological exclusions and they are not quality exclusions. Sealed preparation that does not match this REF identity stops M9C. Matching the REF digest verifies the production file. It does not record an AptaRank result.

The upload copies `sequence_core` from the first identity row. A later identity does not replace that sequence. Blank `publication`, `canonical_target_name`, or `pdb_id` cells are not exclusions, because those fields are not part of the upload.

The private duplicate-provenance ledger is a project-only audit artifact. It is never an AptaRank input. It has one JSON object per retained core, in first-occurrence order. Because the upload has no identifier column, each object has a deterministic 1-based `upload_row_number`. It also records the retained id, every contributing source identity in file order, and the later identities that collapsed into the core. The ledger does not contain sequence text.

No other row is removed. Case, whitespace, and alphabet are not normalized. `T` is not converted to `U`. No length filter is applied. A malformed schema, a noncanonical core, a conflicting row count, a duplicate identity, a missing scientific identity, or a digest mismatch fails closed.

## First failed publication attempt

`publish_sealed_reference_preparation(invoke=True)` was invoked once against commit `3d5a4beafc723ab154a2ff7d3a6d6835841b3b48` and contract SHA-256 `eb082923fbd79ccc05a9833e0f18e40094e8384bd2104392eee6cd46bc55f591`. REF was opened and verified. Preparation stopped because the obsolete five-column contract required `publication` (`missing_required_field`). No output was published. AptaRank was not run. The attempt was not retried, and this correction does not reopen REF.

## Supersession of the five-column assumption

Frozen M9B artifacts stay historical evidence. ARP-1 still records the five reference columns in `config/modelling/aptarank_io_spec.json`, SHA-256 `46ba6c8be873dad4c086e9f6b889b51702ba31212fa502d00f26e267a22da732`, and `scripts/modelling/aptarank_io_preflight.py`, SHA-256 `eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01`. The evidence contract, SHA-256 `0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b`, is likewise unchanged. That five-column reference-upload assumption is superseded for M9C by the user-confirmed live interface. The supersession covers only the reference upload. Historical M9B results are not rewritten. Candidate-upload and shortlist-export behavior is unchanged.

## Calibration and target mapping

AptaRank performs its own single pooled empirical REF calibration. This package does not implement that calibration and does not substitute a local one.

The frozen target mapping is recorded and was not reopened:

| Artifact | SHA-256 |
|---|---|
| Structure file | `2e185a205c9be0bf76484e8ffb96ae225880723ed68eaaf25dffbbccaf01ff51` |
| Selection record | `08f0c96af349ce4909d40c3004804317661777f72828cd807823341e0e4f0d04` |
| AptaRank target upload | `46471bb0643125ce86300ec050d6f0d3a09faa1d06dc325141c67cd1acdd5922` |

The target-upload digest is stored separately from the structure-file digest and the selection-record digest. Verifying it requires the caller to supply those bytes. The files themselves are not opened here.

## Boundary

`prepare_reference_upload` accepts in-memory bytes. A filesystem path is refused. Sealed review remains authorized for the verified REF file, 211,993 bytes, SHA-256 `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23`. `prepare_sealed_reference` remains uninvoked and returns before any external path is opened. `write_sealed_preparation_outputs` atomically writes caller-supplied preparation bytes and does not call that entry point.

The only production publication destination is `/home/laura/rnagenesis-mres-worktrees/generator-eval-prep/results/fine_tuning/m9_generator_evaluation/m9c_reference_preparation`. Any other `results/` path, every `data/` destination, a symlink, and any existing destination, including an empty directory, are refused. `publish_sealed_reference_preparation` runs only when its invocation flag is passed. It finishes the contract and destination preflight before opening REF, verifies the pinned REF bytes, prepares the one-column upload, private provenance ledger, and manifest, writes those three files into a temporary sibling, rereads and checks the bytes and digests, and publishes the directory with one `RENAME_NOREPLACE` rename. A failure removes only the temporary directory created by that invocation. The upload CSV and provenance JSONL stay ignored by Git. The manifest is not ignored, so it can be reviewed while untracked. The corrected contract has not invoked this entry point. The no-argument command checks the pins and prints the status. It does not publish the directory, and it does not run an end-to-end rehearsal.

Unit tests use synthetic fixtures and temporary directories only. This correction did not reopen REF, retry production publication, open EVAL or production candidates, or invoke AptaRank.

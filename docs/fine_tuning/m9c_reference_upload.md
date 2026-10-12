# M9C-1 reference-upload policy

| Item | Value |
|---|---|
| Status | `POLICY_FROZEN_SEALED_PREPARATION_AUTHORIZED` |
| Stage | M9C-1. The rest of M9C is not complete. |
| Contract | `config/modelling/aptarank_reference_upload_contract.json`, SHA-256 `4bba54b5d8080b15287ce37f8645bbfc3e07a149c53bb0f647dfa3e34042d46b` |
| Plan | `docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md`, version 3.3, SHA-256 `b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe` |
| Reused validator | `scripts/modelling/aptarank_io_preflight.py`, SHA-256 `eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01` |

This note freezes how the corrected REF CSV becomes the AptaRank reference upload. It does not open REF, EVAL, or a production candidate source. It does not calculate a REF distribution. No detail below is a scientific result.

## Upload grain

The frozen source is the 131-identity REF CSV, SHA-256 `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23`, at the repository-relative path `data/processed/ref.csv`. Its header is the 85-column S5E clustered-corpus schema. `ft_split` is not part of that header.

Preparation walks that file in its existing order and keeps one row for each distinct `sequence_core`. The expected AptaRank UI result is 113 accepted rows and zero dropped rows. That figure is an expectation, not an observed UI count. `aptarank_ui_executed` stays false, and both observed UI counts stay null. The 18 later identity rows are duplicate-core collapses. They are not biological exclusions and they are not quality exclusions. Sealed preparation that does not match this REF identity stops M9C. Matching the REF digest verifies the production file. It does not record an AptaRank result.

For each core, the upload copies the first identity row and does not replace those fields from a later row:

| Upload column | Source column |
|---|---|
| `id` | `scientific_identity_id` |
| `sequence` | `sequence_core` |
| `target_name` | `canonical_target_name` |
| `target_pdb_id` | `pdb_id` |
| `source_reference` | `publication` |

`pdb_id` may be blank. A blank cell stays blank. The upload order is the first-occurrence order of `sequence_core`. The reused ARP-1 validator checks the finished upload. This package does not keep a second copy of those column rules.

The restricted duplicate-provenance ledger has one JSON object per retained core, in that same order. Each object records the retained id, every contributing source identity in file order, and the later identities that collapsed into the core. The ledger does not contain sequence text.

No other row is removed. Case, whitespace, and alphabet are not normalized. `T` is not converted to `U`. No length filter is applied. A malformed schema, a noncanonical core, a conflicting row count, a duplicate identity, a missing required field, or a digest mismatch fails closed.

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

`prepare_reference_upload` accepts in-memory bytes. A filesystem path is refused. Sealed review is authorized for the verified REF file, 211,993 bytes, SHA-256 `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23`. `prepare_sealed_reference` remains uninvoked and returns before any external path is opened. `write_sealed_preparation_outputs` atomically writes caller-supplied preparation bytes and does not call that entry point. The no-argument command checks the pins and prints the status. It does not write a production directory, and it does not run an end-to-end rehearsal.

Unit tests use synthetic fixtures only. TRAIN, VALIDATION, REF, EVAL, production candidate sources, target-mapping files, and `results/` were not opened.

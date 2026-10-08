# ARP-1 interface reconciliation

ARP-1 is a draft upload and export contract for a later AptaRank run. It checks synthetic files only. This note records draft revision 3, schema `aptarank-io-arp1-draft-r3`. `status` remains `draft`. `deployment_verified` remains false.

## Provisional observations that were reused

The column contract reuses reviewer-supplied interface observations from a separately reviewed camera-ready workflow:

- Candidate upload columns, in order: `id`, `sequence`.
- Reference-library upload columns, in order: `id`, `sequence`, `target_name`, `target_pdb_id`, `source_reference`.
- Shortlist-export columns, in order: `rank`, `candidate`, `aptamer-likeness`, `compatibility`, `shuffle`, `len`, `sequence`.
- Upload ids were observed in the export `candidate` column.
- A target-free Rigorous-style export used the compatibility literal `not evaluated` and the shuffle literals `pass` and `fail`.
- Some essential settings were absent from the CSV export and had to be captured from the UI or provenance view.

Those literals are accepted only as observed export tokens for the explicitly selected synthetic profile `target_free_rigorous_style`. ARP-1 does not assign a scientific meaning, a shuffle threshold, or a preset value to them. The governing plan says the actual rigorous preset still has to be verified. This draft does not adopt a preset value from that historical description.

## What was not reused

Camera-ready VALIDATION outcomes and target decisions are not reused. The governing plan keeps VALIDATION as a quarantined development and camera-ready role. Those outcomes cannot tune this thesis evaluation, choose a target, or stand in for held-out EVAL. Target choices from that workflow are scientific decisions, not an interface schema. ARP-1 does not import their scores, ranks, structures, or selections.

## Why this contract remains draft

The observations above are provisional evidence. They are not authority that the current deployment is unchanged. Laura still has to complete a new synthetic UI preflight and record the deployment version, schema version, code revision, preset, and the settings that the CSV does not contain. Until that record exists, `deployment_verified` remains false and no later package should treat this schema as frozen.

## Raw Tier 2 score

The observed shortlist did not expose a raw Tier 2 geometric score. ARP-1 records that observation and leaves availability, equation, direction, and comparison scope unresolved. It does not treat the missing column as proof that the deployment cannot emit a raw score, and it does not invent an equation, a direction, or a control-bank identifier, hash, or provenance. Control-bank identity remains an unresolved deployment question.

## Fields Laura must capture

During the new synthetic UI preflight, capture these fields from the UI or provenance view when the CSV does not contain them:

- run id, operator, start time, and finish time
- deployment version, deployment schema version, and deployment code revision
- preset value and effective settings
- SHA-256 of the candidate upload, the reference upload, the shortlist export, the failure record, and the expected-cell manifest, stored in the provenance record. The provenance record does not contain its own SHA-256. That digest is computed externally from the original provenance bytes and retained in the generated report SHA-256 block. A digest stored inside the record would be self-referential, because it would depend on the bytes that contain it.
- raw Tier 2 score availability, equation, direction, and comparison scope
- control-bank identifier, hash, and provenance
- canonical target, structure or PDB file and its hash, chain or domain, binding mode, site or pocket, numbering, and preparation
- runtime and row accounting: expected, exported, and failed row counts, plus warnings and rerun lineage

For a target-free run, record explicitly that no target, mode, site, or configuration was entered. Do not fill those fields from the camera-ready workflow. Leave every unresolved field blank rather than substituting a guessed value. A failed candidate needs an explicit failure reason. Do not drop the row and do not store the missing result as zero.

## Nullable reference PDB identifier

The reference upload remains five columns: `id`, `sequence`, `target_name`, `target_pdb_id`, `source_reference`. Draft revision 2 changes `target_pdb_id` from a nonempty uninterpreted string to a nullable uninterpreted string. A blank cell is valid when an unambiguous PDB is unavailable. ARP-1 leaves that cell blank. It does not write a sentinel or an invented identifier in its place. A nonempty value is rejected when it has leading or trailing whitespace, including a whitespace-only cell. `id` stays nonempty and unique, `sequence` stays nonempty uppercase A, C, G and U, `source_reference` stays nonempty, and `target_name` stays nonempty in this corrected reference contract.

Nullable PDB provenance preserves the full unique-core REF calibration set without inventing structural evidence. A unique REF core that has no unambiguous PDB remains in the reference upload. The blank `target_pdb_id` cell records that absence. It does not manufacture a structure, a PDB code, or any other structural evidence for that core.

## Provenance record and hashing boundary

The declared UI capture fields and the validated provenance record now name the same applicable fields. `fixture_role` and `profile_id` remain synthetic-fixture selectors. They are not UI capture fields. Every other required provenance key is a declared capture field, and every declared capture field is present and validated.

The bundled synthetic run keeps deployment version, deployment schema version, deployment code revision, preset, effective settings, and the unresolved raw Tier 2 and control-bank fields unset. `deployment_verified` stays false. `ui_capture_complete` stays false. Textual target fields use the explicit sentinel `not_entered_target_free`. The structure hash is null because no target structure exists. Warnings and rerun lineage stay empty lists. The record stores the five SHA-256 digests of the other exact fixture byte streams, and it stores expected, exported, and failed counts that match those files.

The provenance record does not contain its own SHA-256. That would be self-referential: the digest would depend on the bytes that contain the digest. ARP-1 computes the provenance-record SHA-256 externally from the original bytes and retains it in the generated report SHA-256 block. Validation fails closed when a recorded fixture hash differs from the bytes supplied to validation, when an expected, exported, or failed count differs from the actual file accounting, when a required provenance key is absent or extra, when an unresolved field is populated without a later reviewed interface revision, or when a target-free field contains an invented target configuration.

## UTF-8 BOM

A candidate, reference, or shortlist CSV may begin with one UTF-8 BOM. ARP-1 strips that BOM only for decoding and logical header validation. The SHA-256 is the hash of the original bytes, including the BOM when it is present. A BOM anywhere except the beginning of the byte stream is rejected. Renamed, reordered, missing, and extra columns are still rejected. BOM handling is encoding normalization, not schema adaptation.

## Strict JSON types

`expected_row_count`, `exported_row_count`, and `failed_row_count` are nonnegative JSON integers. Booleans and floats are excluded, including a float that is mathematically integral, such as `1.0`. A boolean, a float, a string, or a negative integer is rejected with `invalid_row_count_type`. A nonnegative integer that does not equal the corresponding file count is rejected with `row_count_mismatch`.

Expected candidate ids, failure candidate ids, and `profile_id` values are nonempty strings. A JSON object, array, null, or boolean is rejected before it can reach a set, a sort, a dictionary key, or id reconciliation. Those controlled errors are `invalid_expected_candidate_id`, `invalid_failure_candidate_id`, and `invalid_profile_id`. The error text does not include sequence strings. An expected-id list or a failure record that contains a structurally invalid identifier is not reconciled.

## Schema differences

If an upload or download header differs in name, order, or membership from this draft, validation fails closed. ARP-1 does not rename, reorder, add, or drop columns to accept the file. A difference requires a reviewed specification revision. Silent adaptation is not a valid update path. The revision has to keep `deployment_verified` false until the new synthetic UI preflight agrees with the revised schema.

## Technical preflight versus a scientific result

A passing ARP-1 run means the synthetic fixtures satisfied this draft mechanical contract: schemas, opaque ids, sequence round-trip, length reconciliation, profile tokens, failure accounting, and byte hashes. It is not a scientific result. It is not Tier 1 calibration, not a biological score analysis, not Tier 2 target selection, and not a candidate ranking. It does not interpret binding, affinity, or selectivity, and it does not define a combined Tier 1 and Tier 2 score.

The no-argument command runs only the bundled synthetic fixtures. It rejects paths, unlock flags, and any other argument. It does not load EVAL, REF, VALIDATION, TRAIN, production pools, or checkpoints.

## Reviewer-supplied interface evidence

These SHA-256 values are reviewer-supplied interface observations and hashes. This document does not claim that Cursor inspected those local files. The source directory was not clean, so the enclosing Git commit is not the complete provenance of those worktree bytes. The hashes are interface evidence only.

| Worktree file | SHA-256 |
| --- | --- |
| README.md | `d583cd1710d8772b206e3ecb9308c0fb8fcd9bac6bcd02307766700eac56697a` |
| prepare_camera_ready_inputs.py | `e16caf8660b0b38fd97fe47d5d9f102b5575be2511694316a9050ae7c0e872d6` |
| artifacts/synthetic_preflight_checklist.md | `9b6a441f408ab850025bd8a275c3f5af5ec0968eb47471f595a899c1f30d7276` |
| artifacts/synthetic_preflight_report.md | `6cacefa67b418297af03b9ba83a4e86fa586ed7bbbe9ea800d483b448649d43b` |
| tests/test_rigorous_preflight.py | `3c2d02511a4876d30377aee682ea9ae60723317ac64e3c2881ecf4eff96590e3` |

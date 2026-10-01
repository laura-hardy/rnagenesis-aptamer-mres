# M4 run-manifest schema

**APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION**

This document must not be consumed by an executable workflow. It translates implementation-plan section 14 into a versioned schema description. It does not create a run directory, and this stage creates no evidence directory. M4 is not complete.

Schema version: `m4-stage1-draft-1`.

Approval status: `APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION`.

Human approval:

- approving person: Laura Hardy
- approval date: 29 September 2026
- approval-recorded timestamp: `2026-09-29T14:57:40+10:00`
- approval source: formal human approval in the M4 review chat
- approval scope: Stage 1 protocol package for M4 implementation only
- explicitly not approved: scientific execution, biological-data runs, B2 generation, validation-artifact creation, model loading, GPU use, B1 generation, D1 training, staging, committing, or pushing
- `consumable_by_executable_workflow: false`
- previous status: `DRAFT_PENDING_HUMAN_APPROVAL`

Written against MRes `b690f44a025a3790f1af1865856fc480dbec1079`.

## 1. One manifest per scientific result

Every later scientific result maps to one immutable experiment manifest. A manifest is written only when a separately approved stage actually runs. This schema is not that manifest.

Plan section 13.2 sketches repository-local `results/modelling/<run_id>/`. Completed M1 and M3 evidence, and this stage's instruction, use an external run root. This schema adopts the external root:

```text
/home/laura/rnagenesis-mres-runs/
```

Run outputs do not go into the git working tree.

## 2. Fail-closed directories

A run directory must be a new, unique directory under `/home/laura/rnagenesis-mres-runs/`.

The process must refuse to start if that path already exists, including when the existing directory is empty. It must refuse to overwrite files in an existing run directory. It must refuse to append records, logs, or sequences to an existing run directory. `exist_ok` creation is not compliance.

The directory name includes the experiment id, condition manifest label, and run id. Ambiguous names such as `final`, `final2`, `best`, `good_run`, and `new_model` are prohibited for both directories and checkpoints.

## 3. Required fields

A compliant manifest records every field below. Unknown values are explicit nulls with a reason. They are not omitted.

### Identity and status

- schema version. For a B2 manifest, `manifest_schema_version` identifies the JSON manifest structure and `schema_version` identifies the configuration/protocol schema supplied to the run;
- approval status of the schema and of the experiment configuration that was actually used;
- experiment identifier;
- condition identifier, using the manifest label in `config/modelling/condition_registry.yaml`;
- run identifier;
- attempt identifier when the result is one invocation or one sampled attempt;
- start timestamp and end timestamp, with timezone;
- hostname.

### Repository provenance

- MRes repository SHA;
- MRes upstream SHA;
- RNAGenesis repository SHA;
- upstream training-code SHA when training code is used;
- frozen corpus commit;
- working-tree dirty status for each repository that supplied code;
- patch or diff hash if a tree was dirty;
- the command's exit status, and a nonzero status is still recorded.

### Inputs and roles

- condition-registry version;
- configuration version and path hash;
- metric-set version and path hash;
- each input role that was opened;
- expected hash, actual hash, and count for each opened input;
- an access log of opened paths;
- explicit statement that REF was not opened, with the contract hash `531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23` recorded as metadata only;
- explicit statement that EVAL was not opened, with the contract hash `ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015` recorded as metadata only;
- chemistry policy;
- sequence count and length summary for any corpus role that was legitimately read.

TRAIN text expected hash, when TRAIN text is an authorised input: `d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d`.

VALIDATION CSV expected hash, when VALIDATION is an authorised input: `cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd`.

A fixed-draw metadata manifest records three hashes:

- the VALIDATION CSV hash;
- `validation_sequence_order_sha256`, the SHA-256 of the concatenation of each of the 95 ASCII sequence cores followed by exactly one LF byte, in frozen first-occurrence order;
- `validation_order_artifact_sha256`, the SHA-256 of the serialized no-sequence order artifact.

The order artifact contains only role, zero-based frozen index, SHA-256 of the sequence core, and biological length. It must not contain sequence text. Its approved serialization is UTF-8 CSV, LF line endings, no BOM, no carriage returns, exact header `role,zero_based_frozen_index,sequence_core_sha256,biological_length`, exactly 95 data rows in frozen order, minimal CSV quoting, and a required final LF. The artifact hash is the SHA-256 of those exact bytes. The VALIDATION CSV hash does not substitute for either ordering hash. The accepted CPU artifact records `validation_sequence_order_sha256` `eb18fd48e305e86f8000bdc82e9175437d478bd624ea57aef8094497534bda3a` and `validation_order_artifact_sha256` `df445b617adf5165f3361412bb5c7bc5d2a05b31a98eb6d2f6d17f4b329de248`. An executed fixed-draw validation must load those bytes and must not treat the CSV hash as a substitute or resample the tensors.

The same manifest records the evaluated weight variant. A comparison must not mix raw and EMA weight variants. Timestep-tensor, noise-tensor, and metadata hashes stay independent. This stage creates none of those artifacts.

A hash mismatch is a hard stop before sampling, training, or generation. REF or EVAL presented as an input is a hard stop during development.

### Environment and models

- Python version and executable path;
- package versions used by the process, including NumPy, PyTorch, diffusers, and ViennaRNA when those packages are imported;
- diffusers patch verification hash when the RNAGenesis model code runs;
- EncDec config and checkpoint identifiers and hashes;
- generic diffusion input checkpoint identifiers and hashes;
- B0 aptamer diffusion checkpoint hashes when B0 is the condition being described;
- tokenizer and config hashes;
- trainable parameter names and counts, and frozen parameter names and counts, when a training run loads models;
- seed and the full deterministic recipe, including generator class, device, and call order;
- full training parameters or full generation parameters, whichever applies.

### Device

When no GPU is used, record that fact and leave the GPU fields null.

When a GPU is used, record:

- physical GPU index and model;
- `CUDA_VISIBLE_DEVICES`;
- the visible logical device, such as `cuda:0`;
- an `nvidia-smi` snapshot taken before the run.

A later authorisation binds the physical GPU index, its UUID, and its PCI bus at authorisation time. The child process uses logical `cuda:0`. `CUDA_VISIBLE_DEVICES` is the authorised physical index, so that device is the only visible CUDA device. No CPU fallback and no other-GPU fallback is permitted. The development-pool runner does not hard-code physical GPU 0 or physical GPU 1.

### Commands, outputs, and accounting

- the exact command;
- exit status;
- raw output hash;
- cleaned output hash;
- cleaning-code version;
- metric-code SHA;
- accounting denominators: raw attempts, parsed outputs, valid outputs, unique valid outputs, duplicate outputs, invalid outputs, and the denominator used by each rate;
- warnings, retries, deviations, and the stopping reason.

Generated-sequence provenance, for every sample set, also includes condition id, checkpoint hash, generation seed, requested length or maximum length, DDIM steps, eta, top-p, top-k, raw attempt index, raw output string, cleaned sequence, and cleaning flags. Raw files are not rewritten by cleaning. Requested-length reporting always includes raw attempts, valid outputs, and exact hits together.

For the 1,000-attempt B1/D1 diagnostic schedule, the manifest contains the complete invocation table before generation begins. Each row records the zero-based invocation index, the invocation seed `44000 + that index`, the target length, the actual chunk size, `batch_num=1`, and the original attempt indexes in that chunk. Every generated record maps back to its original target-length attempt index. The target-length sampling seed remains 43000 and is recorded separately from the generation-seed base. The accepted schedule hash is `0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0`. The development-pool runner does not hardcode physical GPU 0 or physical GPU 1.

The checked-in stage-1 configuration is not executable. It records the accepted CPU schedule and VALIDATION artifacts and may keep a non-executable GPU proposal. That proposal is not the executable authorisation schema. An executable development-pool block is a later, separate authorization-only commit. That commit must not modify `scripts/b1_development_pool_runner.py`. Its block stores `authorization_parent_commit` and `executing_implementation_commit`, both equal to the accepted implementation commit. It does not store `authorization_commit`. The runner computes `authorization_commit` from live `HEAD` and records that computed value in the runtime manifest.

The executable block must contain exactly these keys: `authorisation_id`, `authorisation_active`, `activation_status`, `consumed`, `authorises_b1_development_pool`, `gpu_use_authorised`, `physical_gpu`, `gpu_uuid`, `pci_bus`, `authorization_parent_commit`, `executing_implementation_commit`, `mres_branch`, `condition`, `phase`, `output_directory`, `evidence_directory`, `schedule_sha256`, `success_claimed`, `m4_complete`, `b1_eligible`, `exact_length_accepted_pool_declared`, `final_production_mapping_declared`, and `final_m8_production_protocol_declared`. Before any GPU query or evidence-directory creation, the runner requires branch `main`, a clean worktree and index, local `HEAD` equal to `origin/main`, exactly one parent, that parent equal to both `authorization_parent_commit` and `executing_implementation_commit`, runner bytes equal to the runner blob in that parent, and the active block taken from live `HEAD`. Merge commits, the wrong parent, a commit after the authorization commit, runner drift, a dirty tree, and an inactive or consumed block are refused.

Phase A attempt records include `pairing_group`, equal to the target biological length, and `attempt_within_candidate`, from 0 through 15. The three candidate caps for one target are initialised with the same seed, `41000 + zero-based target index`.

Phase B records 16 raw attempts for each of the 89 ascending TRAIN lengths, with one invocation seed per length, `42000 + zero-based length index`.

### Selection

- validation-protocol version;
- the selected-checkpoint rule in force;
- the selected checkpoint identity and SHA-256;
- the selection justification, including the fixed-draw VALIDATION loss and the pass or fail result of every approved hard guardrail.

A checkpoint that fails an approved hard guardrail is not selected, including when its validation loss is the lowest.

### Human approvals

- the approving person;
- what was approved;
- the approval timestamp;
- the configuration hash that was approved.

A later edit to an approved protocol file after that timestamp invalidates the approval until a new approval is recorded.

## 4. Checkpoint names

Validation at optimizer update 0 references the immutable released B1 checkpoint and its recorded hash, `c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26`. The manifest records that reference. It does not require copying or saving another 7.4 GB initialization checkpoint.

Updates 7 and 14 are approved as learning-curve evidence only. They are not eligible for checkpoint selection based on validation loss alone, and they cannot become selectable unless the approved generated-sample guardrails are also evaluated for those exact weights. The currently proposed diagnostic-generation authorization covers only initialization/B1 and the final pilot state. The final pilot state is a technical and scientific pilot result, not the final D1 model.

Use a deterministic name. The proposed D1 pattern is:

```text
D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-42__update-<count>__git-<sha>
```

## 5. B2 manifest addition

B2 attempt 2 is completed accepted evidence at `/home/laura/rnagenesis-mres-runs/m4_b2_empirical_null_6f82878_attempt2`. Its raw SHA-256 is `bbe35f448db0d7fc02ad0156865798382b0b41e9ad047b4e52eddf7cff740c83` and its manifest SHA-256 is `31c07fb966c462263307569b383b112ecfb39725adb9b1b2fd2f93a95d3d8baa`. That evidence must not be rerun. This section describes the manifest of that completed run. It does not authorise another sample.

A B2 manifest also records the fields required by `config/experiments/B2_empirical_null.yaml`: input hashes, derived nucleotide probabilities, the full empirical length counts, NumPy version, RNG name, seed, raw count, unique count as a diagnostic only, output hash, command, repository SHA, timestamps, and exit status.

The raw-output SHA-256 is computed over the canonical file bytes: UTF-8; one JSON object per attempt; key order exactly the declared field order; compact separators `,` and `:`; `ensure_ascii=false`; no spaces outside string values; an LF after every record, including the final record; no BOM; and no carriage returns.

An implementation must reject an empty TRAIN stream, a non-A/C/G/U character, a count other than 669, a duplicate input sequence, a non-finite or negative probability, and any probability vector whose ordered A/C/U/G values fail `abs(sum(probabilities) - 1.0) <= 1e-12`. Probabilities are float64. Relative tolerance is zero. This stage does not compute nucleotide probabilities from biological TRAIN text.

B2 manifest JSON is deterministic: UTF-8; one JSON object; key order is the declared field order in `scripts/null_model.py`; compact separators `,` and `:`; `ensure_ascii` false; no spaces outside string values; no BOM; no carriage returns; one trailing LF. Float64 quantities are decimal strings from format `.17g`. The manifest does not contain its own hash. That hash may be computed externally after the file is closed.

The first field is `manifest_schema_version`, and its value is `m4-b2-run-manifest-2`. That field identifies this JSON manifest structure. `schema_version` remains the configuration/protocol schema version supplied to the run. The original run's legacy manifest predates `m4-b2-run-manifest-2` and is not rewritten.

A completed successful manifest records observed values for every field the run can observe, including seed, count, input path and role, expected and actual input hashes, counts, uniqueness, configuration path and SHA-256, frozen-contract path and SHA-256, timestamps with timezone, hostname, MRes HEAD, upstream SHA, branch, dirty state, patch hash when dirty, NumPy and Python versions, RNG type and consumption order, derived counts, probabilities, tolerance, histogram, output path, byte count, re-read SHA-256, access log, command, exit status, overwrite-refusal result, warnings, retries, deviations, stopping reason, and the two approval records below. `UNKNOWN_UNTIL_RUN` is not used for those observed fields. A field that B2 genuinely cannot observe, such as a model-checkpoint hash, is an explicit null with status `NOT_APPLICABLE` and a reason. The corrected implementation writes a manifest only after the execution gate passes. This schema does not pass that gate, and this document does not authorise a run.

### Approval provenance

The accepted B2 manifest keeps two approval records distinct. It must not be rewritten or rerun. A new B2 manifest keeps two approval records distinct. It does not contain a generic `human_approval` field. The configuration may still store the Stage 1 block under `human_approval`. The manifest copies that block only as `protocol_implementation_approval`.

`protocol_implementation_approval` is the Stage 1 protocol and implementation approval. Its `record_role` is `stage_1_protocol_implementation_approval`. `authorizes_scientific_execution` and `authorizes_this_invocation` are both false. `authorizes_this_invocation_meaning` states that this false value means the Stage 1 record did not itself authorize the invocation, and that `scientific_execution_authorisation` did. `explicitly_not_approved` remains the Stage 1 list. `explicitly_not_approved_scope` states that the list applies only to that Stage 1 approval, does not revoke `scientific_execution_authorisation`, and does not mean the invocation lacked scientific-execution approval. The record also keeps the approving person, date, recorded timestamp, source, scope, and `m4_complete`. It records the configuration observed at invocation as `configuration_document_status_at_invocation`, `configuration_consumable_by_executable_workflow_at_invocation`, and `source_configuration_sha256`. Those three values describe the configuration at invocation time. They are not assertions made by the Stage 1 approval. The separate scientific authorization and relationship record remain the authority for the invocation. Top-level `approval_status` and `consumable_by_executable_workflow` continue to record the executable configuration state, and they are derived from those invocation-state values.

`scientific_execution_authorisation` is a deterministic snapshot of the exact active block that passed validation. The active mapping must contain exactly the declared keys. A missing key and an unexpected key are both rejected with `execution_not_authorised` before frozen-contract access, TRAIN access, output creation, or writes. The YAML source mapping is not required to use a particular key order. After exact membership is validated, the snapshot is constructed in the declared order. It contains every field from that validated active block, reordered only for deterministic serialization. Copied values are immutable scalars from the block. The manifest builder inserts that validated object. It does not reconstruct authority from the sampler, the input block, or any other field. Declared key order is `authorisation_id`, `authorisation_active`, `activation_status`, `activation_recorded_timestamp`, `intended_scope_approval`, `approved_by`, `approval_date`, `approval_recorded_timestamp`, `approval_source`, `scope`, `executing_implementation_commit`, `branch`, `condition`, `output_directory`, `train_text_path`, `train_text_sha256`, `expected_records`, `expected_unique_records`, `alphabet`, `raw_attempt_count`, `seed`, `rng`, `device`, `gpu_use`, `model_loading`, `ref_access`, `eval_access`, `overwrite_or_append`, `single_run_only`, `revoke_after_completed_or_failed_invocation`, `second_attempt_requires_new_directory_and_new_human_authorisation`, `success_claimed`, and `m4_complete`. For a block that passes the gate, `authorisation_active` is true and `activation_status` is `active_single_run`. `success_claimed` and `m4_complete` remain false before execution. `output_directory` is the single authorised output path. The current revoked repository block may contain historical revocation-only keys. That is acceptable because its gates are closed and it cannot execute. A future active authorization block must be newly constructed with exactly this executable schema. It must not reactivate or reuse the consumed block.

`authorisation_relationship` states the connection. `scientific_execution_record_authorized_this_invocation` is true. `protocol_record_authorized_scientific_execution` is false. `explicitly_not_approved_does_not_revoke_scientific_execution_authorisation` is true. The `statement` says that this invocation was authorized by `scientific_execution_authorisation`, that `protocol_implementation_approval` approved protocol implementation only, and that the Stage 1 `explicitly_not_approved` list does not revoke the scientific-execution record. A reader or automated consumer of these fields cannot treat the Stage 1 list as a denial of the completed invocation.

If the active scientific-execution authorization is absent, inactive, incomplete, inconsistent with the canonical B2 configuration, or not an exact match for the executable key set, production fails before frozen-contract access, TRAIN access, output creation, or writes. An inactive record includes `authorisation_active` other than true and `activation_status` other than `active_single_run`. This schema correction does not rewrite a manifest that has already been written. The original run's legacy manifest predates `m4-b2-run-manifest-2` and remains unchanged.

### Expected and observed fields

Protocol requirements and runtime observations are different fields. A requirement is not recorded as though the run had observed it.

- `rows_dropped_expected` is the protocol value `0`. `rows_dropped_actual` is the count observed after generation.
- `ref_opened_expected` is false. `ref_opened_actual` is derived from the completed access log.
- `eval_opened_expected` is false. `eval_opened_actual` is derived from the completed access log.
- `gpu_used_expected` is false. `device_backend_actual` is the backend the sampling path used. `gpu_api_invoked_actual` is taken from that execution path, not from a GPU probe.

### Code-pinned production paths

Production does not accept a CLI selector for the repository root, the B2 configuration, the frozen contract, TRAIN_TEXT, or the run root. Those paths are pinned in `scripts/null_model.py`. The production CLI accepts only the required `--output-dir` argument and `--help`. A test-only synthetic executor may use a temporary surrogate root after it has refused the biological development root, the production TRAIN path, the production TRAIN hash, and the production run root. That executor is not reachable from the CLI and cannot be enabled by environment state.

### Re-read hashing and failure evidence

The raw JSONL SHA-256 is the hash of bytes re-read from disk after the file has been closed. The writer creates the file exclusively, writes every byte, treats a zero-byte `os.write` result as an error, calls `fsync`, and closes the descriptor before that re-read. Hashing only the in-memory buffer is not an observed file hash. The same exclusive, fsynced close applies to the success manifest. Its hash is not stored inside the manifest.

Before the run directory is created, a failure is reported on stderr and the process exits nonzero. No scientific evidence directory is expected. After the run directory has been created, the process attempts to write `failure_status.json` with exclusive, fsynced writing. That file records the original error code, a sanitized detail that does not contain sequence contents, and that the scientific run did not complete. An existing failure file is not overwritten. If writing the failure file itself fails, the original error is preserved and re-raised, and the secondary failure is reported separately. Partial files may remain inside a failed-attempt directory. They are not successful artifacts.

The unique count of the 30,000 sequences does not authorise dropping rows.

## 6. What this schema does not authorise

This schema does not authorise a run. A process that reads this file while its status is `APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION`, or while `consumable_by_executable_workflow` is false, must refuse to create `/home/laura/rnagenesis-mres-runs/` content from it.

Matters that may remain open after this implementation approval, and that must be resolved before final M4 `COMPLETE / GO`, are listed in `docs/fine_tuning/validation_protocol.md` and `config/experiments/generator_evaluation.yaml`. Microbatch, accumulation, mixed precision, and EMA remain deferred to M5. Their absence does not, by itself, block final M4 closure.

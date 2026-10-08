# M4 run-manifest schema

**APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION**

This document must not be consumed by an executable workflow. It translates implementation-plan section 14 into a versioned schema description. It does not create a run directory, and this stage creates no evidence directory. Formal M4 is COMPLETE / GO for M5 planning only. This schema does not authorise M5 execution or D1 training. Formal M5 is COMPLETE / GO — 3 October 2026, for M6 planning only. That acceptance does not authorise M6 execution, biological TRAIN or VALIDATION access, D1 training, GPU use, REF, EVAL, or a new run. Section 8 defines the inactive M6 manifest. It does not authorise execution.

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

The checked-in B1 configuration records the accepted CPU schedule and VALIDATION artifacts. The development-pool authorisation `m4_b1_development_pool_d2b2041520d1_gpu1_attempt1` is inactive, consumed, successful, and `consumed_complete`. The superseded GPU proposal is not the executable authorisation schema. The consumed block is `development_pool_scientific_execution_authorisation`. It stores `authorization_parent_commit` and `executing_implementation_commit`, both equal to `4de4246aa4a97eadaf30caf449e3046378832366`. It does not store `authorization_commit`. The runner computed `authorization_commit` `9c0624e9384e19930251355a6b1d61b2d4fdb153` from live HEAD and recorded that value in the runtime manifest. The block keeps physical GPU 1, UUID `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, and PCI `00000000:61:00.0`. That records the consumed scientific scope and does not claim that access to GPU 1 has been revoked. Phase A, Phase B, M5 execution, D1 training, REF, and EVAL stay closed. Formal M4 is COMPLETE / GO for M5 planning only.

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

Matters that may remain open after this implementation approval, and that must be resolved before final M4 `COMPLETE / GO`, are listed in `docs/fine_tuning/validation_protocol.md` and `config/experiments/generator_evaluation.yaml`. Microbatch, accumulation, mixed precision, and EMA were deferred to M5. Their absence does not, by itself, block final M4 closure. The M5 synthetic-smoke manifest in section 7 records smoke-only values. The accepted attempt-3 evidence does not settle those D1 decisions.

## 7. M5 synthetic-smoke manifest

Schema version for the JSON manifest: `m5-synthetic-smoke-manifest-1`. The configuration schema version is `m5-synthetic-smoke-config-1`. This section does not authorise M5 execution, GPU use, or D1 training. Formal M5 is COMPLETE / GO for M6 planning only. This section does not authorise M6 execution, biological TRAIN or VALIDATION access, D1 training, GPU use, REF, EVAL, or a new run. The checked-in smoke configuration stays inactive and non-consumable.

A passing manifest is written only after every required assertion passes. Its first field is `manifest_schema_version`. The field order is exactly the `MANIFEST_KEYS` tuple in `scripts/modelling/m5_smoke_contract.py`, and the worker writes those fields and no others. A failure writes `m5_smoke_failure_record.json` and does not write `m5_smoke_manifest.json`. The manifest does not contain its own hash. After the manifest file is closed, the worker rereads it and writes the external file `m5_smoke_manifest.sha256`. That external hash is not a manifest field.

```text
MANIFEST_FIELD_ORDER
manifest_schema_version
schema_version
experiment_id
run_id
synthetic_only
authorisation_id
authorisation_consumption_state
mres_implementation_commit
mres_authorization_commit
rnagenesis_commit
tracked_clean
untracked_state
file_hashes
permitted_input_paths
declared_scientific_data_inputs
validated_required_asset_paths
data_input_audit
train_not_accessed
validation_not_accessed
ref_not_accessed
eval_not_accessed
physical_gpu_index
gpu_uuid
pci_bus
gpu_model
logical_device_mapping
package_runtime
parameter_table
shapes_dtypes
optimizer_state
scheduler_state
requested_microbatch
measured_microbatch
actual_batch_shape
requested_accumulation
measured_accumulation
requested_effective_batch
measured_effective_batch
phase_records
precision_used
ema_enabled
starting_ema_inspection
generation_weight_variant
m5_milestone_complete
loss_finite
gradients_finite
gradient_norm
frozen_state
denoiser_update
checkpoint_reload
resume_proof
overfit_trajectory
overfit_pass_rule
overfit_passed
generation_reload
generation_output
peak_training_allocated_bytes
peak_training_reserved_bytes
peak_allocated_bytes
peak_reserved_bytes
memory_peak_accounting
timings
warnings
deviations
failure_state
completion_state
smoke_measurements_are_not_d1_decisions
END_MANIFEST_FIELD_ORDER
```

`completion_state` on a passing correctness-phase manifest is `correctness_phase_passed`. `failure_state` is null. `m5_milestone_complete` is false in the stored manifest. The authorized sequence collects the physical-microbatch, accumulation, precision, EMA, checkpoint, and generation evidence. M5 completion is the human gate after that evidence is reviewed. On 3 October 2026 the gate accepted attempt 3. `m5_milestone_complete` remains intentionally false in the immutable accepted manifest because the manifest records the automated correctness phase, while formal milestone completion occurred later through human review. The acceptance does not rewrite the manifest, so the field stays false and the manifest SHA-256 stays `e82ad082d7b66adce128cf6757e36be20bf3a0289d8aa2a9b5b10754b4f53532`. The manifest does not require another source-code implementation to collect those observations, and it does not settle the unresolved D1 decisions.

`file_hashes` has exactly these keys. Each value is an observed SHA-256, or a mapping of path to observed SHA-256. The manifest hash is absent.

```text
OBSERVED_FILE_HASH_KEYS
configuration
fixture
implementation_contract
implementation_harness
starting_assets
checkpoint_inventory
resume_sidecar
generation_output
END_OBSERVED_FILE_HASH_KEYS
```

`configuration`, `fixture`, `implementation_contract`, and `implementation_harness` are the hashes of the bytes the parent read. `starting_assets` maps each required B1, EncDec, biomap-encoder-config, decoder, and tokenizer path, plus the diffusers normalization patch path, to the SHA-256 observed while verifying that regular file. `checkpoint_inventory` is the complete saved Diffusers checkpoint, hashed from the closed files. `resume_sidecar` is the SHA-256 of the sidecar after it is closed and reread. `generation_output` is the SHA-256 of the generation file after it is closed and reread.

`permitted_input_paths` and `declared_scientific_data_inputs` contain only the tracked synthetic fixture. `validated_required_asset_paths` lists the hashed model files and the diffusers patch. `data_input_audit` records `declared_scientific_data_inputs`, `validated_required_asset_paths`, an empty `cli_scientific_data_arguments` list, `data_access_guard_basis`, and `dynamic_file_open_audit_performed: false`. The guard basis is the closed CLI, the pinned constant fixture path, the pinned call graph, the denied role names and hashes, and the exact repository commits. This is not an observed-open audit. An assembled list of expected paths is not called `opened_paths`. `train_not_accessed`, `validation_not_accessed`, `ref_not_accessed`, and `eval_not_accessed` mean those roles were unreachable through the authorized CLI and pinned worker path. They are copied from `derive_data_access` after that guard is accepted. They are not independent literals and they are not a claim that every file open was intercepted.

The evidence directory is a new direct child of `/home/laura/rnagenesis-mres-runs`. The root itself, a path outside that root, a trailing slash, a symlinked parent, and an existing target are refused. Creation is exclusive and does not overwrite.

Device fields are the physical index, UUID, PCI bus, GPU model, and the logical mapping. Logical `cuda:0` is the remapped view of the authorised physical device. `package_runtime` records the pinned Python executable `/home/laura/miniconda3/envs/rnagenesis-h200/bin/python` and the accepted M0 versions: Python `3.8.13`, torch `2.1.2+cu121`, diffusers `0.25.0`, accelerate `0.25.0`, and transformers `4.36.2`.

The parameter table has one row each for `encoder`, `qformer`, `query_tokens`, `latent_projection`, `decoder`, and `denoiser`. `qformer` is the Q-Former layers. `query_tokens` is only the query-token embedding table. A `qt.*` parameter that is not `query_embeddings` is a Q-Former parameter. Each row records total, trainable, and frozen counts and dtypes. Token, mask, latent, noise, timestep, and loss shapes and dtypes are recorded. `actual_batch_shape` is the collated token shape. Its batch dimension is the measured microbatch.

The authorized sequence uses one physical-microbatch candidate, microbatch 8, and does not sweep or fall back to 16 or 32. If that candidate fails, the run fails closed and preserves the failure record. The fixture contains 8 synthetic records. Accumulation executes four backward microsteps on those same eight records, divides each microstep loss by 4, and then takes one optimizer update, so the exercised effective batch is 32. The manifest records the deterministic reuse. A successful first optimizer step allocates AdamW moments before `peak_training_allocated_bytes` and `peak_training_reserved_bytes` are captured. `peak_allocated_bytes` and `peak_reserved_bytes` are the overall peaks, including checkpoint, reload, resume, and generation. `memory_peak_accounting` records that separation. `phase_records.fp32_observation` is the FP32 loss on the fixed latent, timestep, and noise. `phase_records.bf16_numerical_observation` is one bounded comparison on those same tensors. If BF16 autocast is unsupported, the record has no BF16 result. If autocast is supported and the forward returns, the record stores that returned loss and whether it is finite, plus the FP32 loss, the absolute difference, the relative difference, and a memory observation when one is available. If the forward raises, the run fails closed with `bf16_forward_failed` and does not write a passing manifest. An exception is not recorded as a non-finite BF16 result. It does not select production precision and it does not declare a pass tolerance. `starting_ema_inspection` records the exact accepted B1 diffusion inventory. That inventory has no EMA artifact, so compatibility is `not_applicable_absent`. An unexpected checkpoint or EMA member fails asset identity. The inspection does not select an EMA policy. `generation_weight_variant` is `raw`. `phase_records.generation_weight_state` records raw as `used` and EMA as `not_used`. These are smoke measurements. `smoke_measurements_are_not_d1_decisions` is true. They do not settle physical microbatch, accumulation, production precision, EMA policy, the M6 seed, or the M7 seeds.

`frozen_state` contains `after_backward`, `after_update`, and `after_generation`. A passing manifest requires all three. `after_generation.optimizer_membership_evidence_basis` is `live_adamw_parameter_identities`. That evidence is the parameter identities of the proof AdamW and the restored AdamW, recorded while both optimizers existed, and recomputed as disjoint from every EncDec parameter. A replacement optimizer does not satisfy the assertion. The overfit trajectory contains the loss before the configured optimizer updates and the loss after every configured update. Four updates produce five observations. The pass rule compares the first observation with the last, which is the loss after the fourth update.

Checkpoint reload records the expected Diffusers members and their saved file hashes, a successful fresh training load, selected original-versus-reloaded tensor digests, and configuration compatibility. Comparing a directory inventory with itself is not sufficient. The worker constructs `checkpoint_reload` by inserting keys in this order:

```text
CHECKPOINT_RELOAD_FIELD_ORDER
saved_file_hashes
fresh_load_succeeded
original_denoiser_id
reloaded_denoiser_id
tensor_digest_comparisons
original_config_sha256
reloaded_config_sha256
raw_config_sha256_equal
configuration_compatibility
configuration_compatible
END_CHECKPOINT_RELOAD_FIELD_ORDER
```

`original_config_sha256` and `reloaded_config_sha256` are the canonical raw SHA-256 digests of the complete original and reloaded in-memory denoiser configurations. Those raw digests stay recorded under those names. `raw_config_sha256_equal` records whether the two raw digests are equal. The raw digests may differ. `configuration_compatibility` is the nested compatibility record. The worker constructs that nested mapping by inserting keys in this order:

```text
CONFIGURATION_COMPATIBILITY_FIELD_ORDER
ignored_top_level_keys
original_ignored_values
reloaded_ignored_values
original_normalized_config_sha256
reloaded_normalized_config_sha256
normalized_config_sha256_equal
END_CONFIGURATION_COMPATIBILITY_FIELD_ORDER
```

`CHECKPOINT_RELOAD_FIELD_ORDER` and `CONFIGURATION_COMPATIBILITY_FIELD_ORDER` are the worker's field-construction order. They document the sequence in which the worker inserts keys before serialization. They do not decide whether a parsed mapping is valid. Canonical JSON then serializes every mapping with keys sorted lexicographically, compact separators, ASCII escaping, and a trailing newline. Parsing that document restores lexicographic key order, not worker insertion order. Validation of a parsed `checkpoint_reload` mapping, and of its nested `configuration_compatibility` mapping, is order-independent. Each mapping must contain exactly the documented key set: a missing key is rejected, and an unexpected key is rejected. The same keys and values in a different insertion order are accepted. A closed manifest can therefore be parsed and passed to manifest validation without reordering nested mappings.

`ignored_top_level_keys` is exactly `["_name_or_path"]`. The compatibility digest removes only that top-level key. The removal is not recursive and does not apply to every underscore-prefixed field. `_class_name`, `_diffusers_version`, architecture fields, unknown metadata, and every other field remain in the normalized digest. A nested `_name_or_path` remains covered. `original_ignored_values` and `reloaded_ignored_values` record the values observed for that key on the live original and reloaded configuration mappings. `original_normalized_config_sha256` and `reloaded_normalized_config_sha256` are the canonical SHA-256 digests after that single top-level exclusion. `normalized_config_sha256_equal` records whether those normalized digests are equal. `configuration_compatible` is true only when the allowlist is exactly that one key and the normalized digests are equal. Raw and normalized digests both use deterministic canonical JSON. This normalization does not weaken the accepted B1 raw config-file hash, B1 weight identity, or the saved checkpoint inventory hashes. Those remain hashes of the closed files. Tensor-digest comparisons, the fresh-object proof, and resume assertions are unchanged.

That training object is then resumed and overfit. Generation does not use it. Generation loads a new pipeline from the original one-update smoke checkpoint only after weak references taken while the original denoiser, the resumed denoiser, representative parameters, both optimizers, and the other GPU-bearing training objects were live are observed dead. `training_objects_released_before_generation_reload` is that observation. `released_training_object_names` lists only referents observed dead. Python object ids remain supplementary and are not the release proof. `generation_reload` records the selected checkpoint path, its inventory and hash set, the pre-generation reloaded tensor digests, the match to the on-disk checkpoint, and the separation from the mutated training object. Python object identity is not sufficient for that separation. Resume records fresh object identity, saved-versus-reloaded weight digests, optimizer state loaded against the fresh denoiser, optimizer moments, restored scheduler position and learning rate, restored global step, Python RNG restored with `random.setstate`, restored torch CPU, torch CUDA, and dedicated diffusion-generator states, and NumPy RNG as `not_applicable` when NumPy randomness is unused. Each restored RNG is verified with one draw and then set back to the saved state before the resumed optimizer step. The subsequent loss and gradients are finite, and a subsequent update changes a parameter of the fresh denoiser. `sidecar_fields` are the keys reread from the closed sidecar. Weight-only reload is not training resume.

Loss finiteness, gradient finiteness, gradient norm, the denoiser-update slice, peak allocated and reserved GPU memory, timings, warnings, and deviations are required. Critical model assets and the diffusers patch are regular, non-symlink files whose size and SHA-256 match the accepted M0 manifest. The pinned biomap encoder config is `models/autoencoder/encoder/biomap/config.json`, 1369 bytes, SHA-256 `bf7ef6843232f370f3f7fc37d608f85cb0ff0d75291eed35cef52213e34978f7`. The diffusers patch is `/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/site-packages/diffusers/models/normalization.py`, 9516 bytes, SHA-256 `09bc632069f1d6e1dc1b1cb7f5b9ca096c83e3010835f11b8dc6c58b45aa13a5`. B1 remains the starting diffusion checkpoint. B0 is not accepted in its place. Tracked RNAGenesis source remains the clean commit `e3b855bbf4d1af376f43747643fa30afd662828c`.

**Accepted M5 evidence — 3 October 2026.** Formal M5 is COMPLETE / GO for M6 planning only. This acceptance does not authorise M6 execution, biological TRAIN or VALIDATION access, D1 training, GPU use, REF, EVAL, or a new run. It does not make `config/experiments/D1_diffusion_smoke.yaml` executable, and it does not reintroduce a GPU identity, output directory, evidence directory, or active authorisation.

The sole accepted run is `/home/laura/rnagenesis-mres-runs/m5_synthetic_smoke_e8550e7_gpu1_attempt3`. It exited 0, emitted `m5_smoke_manifest.json`, and emitted no failure record. Attempts `/home/laura/rnagenesis-mres-runs/m5_synthetic_smoke_1266a9b_gpu1_attempt1` and `/home/laura/rnagenesis-mres-runs/m5_synthetic_smoke_a634673_gpu1_attempt2` remain preserved failed engineering attempts. Each exited 1, wrote a failure record, and wrote no final manifest. The manifest SHA-256 is `e82ad082d7b66adce128cf6757e36be20bf3a0289d8aa2a9b5b10754b4f53532` (64,245 bytes), matching `m5_smoke_manifest.sha256`. Execution used implementation commit `e8550e7da095cfc6f17dd001425734e4bea6a3cb` and single-use authorisation commit `d947d4eaef7cc1e7d85cdabbf83f7e02d4bfda72`. The manifest records the execution contract SHA-256 `4fcfb5607c064d97f40163529ad43c568f98b74e95e41188ece9c565ebde3738` and harness SHA-256 `52ee776d3adcddc58d474fddb507df705bae3926b9f893e4a5e2a77c3ee8d656`. Replay used the order-independent validator at `9d818e11c18e33e95b48dda8b5b2a72870ca30b0`, contract SHA-256 `cbb9ff275149315c6a7cb227fafe5c2a0cd3d9b0a5375b296861945f0666ce3a`. Canonical reconstruction was byte-identical and the manifest SHA was unchanged. The prior evidence-review archive SHA-256 is `5b101f6f963c77119e50ac2a84196ee4c5a05c45f76773aad1eadaf4cd359203`. RNAGenesis was not modified and remains `mres-d1-diffusion-finetune` at `e3b855bbf4d1af376f43747643fa30afd662828c`.

Closed manifest identities, used as recorded and not re-hashed for this acceptance: resume sidecar `bb22ab79dc04f56d10d8593a1c3cf317900173c59f4f58297ea329be217c0380`; checkpoint `model_index.json` `05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e`; `scheduler/scheduler_config.json` `6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396`; `unet/config.json` `42c864c81e35ef1a0c7964a3642492fba95c9e24a153407f9fd98855b20d9d70`; `unet/diffusion_pytorch_model.safetensors` `cc5be013fca86125292855e61af8be28a64c1f97f95499958363b4eda89b989e`.

Physical GPU 1 was `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, NVIDIA H200 NVL. Physical microbatch 8, gradient accumulation 4, and observed effective batch 32 were the FP32 correctness path. Physical microbatch 8, gradient accumulation 4, and FP32 are M5-supported observations. EMA was disabled and smoke generation used raw weights. Those observations were a conservative M6 proposal at M5 acceptance. The inactive M6 package now records them as bounded pilot decisions and does not authorise a run. Loss and gradients were finite. The gradient norm was 5.4995274281909055. The denoiser update max absolute delta was 3.0040740966796875e-05. The encoder, Q-Former, query tokens, latent projection, and decoder remained frozen after backward, update, and generation. Checkpoint fresh reload, AdamW state, scheduler, global step, RNG restoration, and the subsequent resumed update passed. The tiny overfit losses were 0.6921789050102234, 0.6151523590087891, 0.5786029696464539, 0.5625630617141724, and 0.5575369596481323. Generation reloaded the immutable one-update checkpoint after the training objects were released. Training peak allocated was 42,046,809,088 bytes and training peak reserved was 42,563,796,992 bytes. Overall peak allocated was 72,871,646,208 bytes and overall peak reserved was 73,614,229,504 bytes. Total wall time was 193.7824976965785 seconds. TRAIN, VALIDATION, REF, and EVAL were not accessed.

BF16 is an observation only: FP32 paired loss 0.8125295639038086, BF16 paired loss 0.8128108978271484, absolute difference 0.00028133392333984375, relative difference 0.0003462445378457017. It was finite. No acceptance tolerance was applied. It does not select production precision. The inactive M6 pilot now records FP32, physical microbatch 8, gradient accumulation 4, disabled EMA, and raw weights for that bounded pilot. The final D1 seed count and biological training authorisation remain unresolved. Both smoke generation strings contain a leading `1` followed by 32 A/C/G/U characters. That is a decoder and control-token format observation, not a biologically valid sequence claim. Production generation or biological interpretation requires the M6 exact-prefix rule in section 8. M5's single leading `1` does not broaden it.

## 8. M6 pilot manifest

Schema version for the JSON manifest: `m6-pilot-manifest-1`. The configuration schema version is `m6-pilot-config-1`. This section does not authorise M6 execution, GPU use, biological TRAIN or VALIDATION access, diagnostic generation, or D1 training. The checked-in pilot configuration stays inactive and non-consumable. `resume_supported` is false. An interrupted attempt is failed. Restart requires a new output directory and a new single-use authorisation. Weight reload is not training resume. Update 0 references immutable B1 and does not copy it.

A manifest is written only after a separately authorised run completes. This repository does not contain one. Canonical JSON uses sorted keys, compact separators, ASCII escaping, and one trailing LF. Validation rejects a missing key and an unexpected key. Sequence text is forbidden.

```text
MANIFEST_FIELD_ORDER
applied_learning_rate_trace
authorisation
b1_identity
completion_state
config_version
data_roles
denoiser_update_evidence
deviations
diagnostic_generation_status
environment
experiment_id
failure_state
frozen_state
gpu
manifest_schema_version
memory
microbatch_accounting
optimizer
post_update_21_scheduler_position
production_identities
ref_eval_access
repository
restart_policy
resume_supported
rng
run_id
schema_version
stop_conditions
timing
train_update_observations
validation_artifacts
validation_observations
validation_review
warnings
weight_checkpoints
END_MANIFEST_FIELD_ORDER
```

The applied learning-rate trace is the 21 nonzero values from `learning_rate_multiplier` in `scripts/modelling/m6_pilot_contract.py`, recorded before each optimizer step. The post-update-21 scheduler position is 22 and its multiplier is 0. That position is the next unapplied schedule position. It is not a PyTorch scheduler `last_epoch`, and it is not applied. `diagnostic_generation_status` is `not_performed_requires_separate_authorisation` until a later authorisation. `memory` records peak allocated bytes and peak reserved bytes separately. `stop_conditions` records whether each automatic technical failure fired. A finite pre-clip gradient norm above 1.0 is clipped and is not one of those failures. Finite validation worsening is a human-review signal in `validation_review`, with no numeric cutoff and no automatic learning-rate change.

`validate_success_manifest` accepts only the synthetic completion state `synthetic_control_flow_completed`. `validate_production_success_manifest` accepts only `pilot_completed` when `production_identities` is true. It validates every top-level section and every exact nested key. The required observations are the live authorisation commit, consumed single-use state, repository and GPU observations, opened TRAIN and VALIDATION identities, opened validation-artifact hashes and shapes, unopened REF and EVAL, package versions, distinct permutation and diffusion RNG streams, 21 update records with a denoiser-element change, four validation observations, three tensor-safe checkpoint reload proofs, frozen EncDec digests, and no failure state. A synthetic manifest does not satisfy the production validator. Numeric strings must be finite, and byte counts and timing strings must be nonnegative. The tracked configuration does not store `authorization_commit`; the success manifest records the runtime HEAD under that name.

The 5 October 2026 remediation keeps that schema and tightens the nested evidence. Model and environment assets, the Diffusers normalization patch, TRAIN, VALIDATION, and every physical validation-artifact file, including the hash-report file, carry a streamed SHA-256 and a measured byte size. The logical sequence-order hash is the value loaded from the artifact manifest, with source `loaded_manifest`. Expected pins and observed measurements are separate fields even when the hex strings are equal. Runtime versions are module attributes, so torch is `2.1.2+cu121`. `timing.training_update_seconds` has 21 durations whose sum is `training_seconds`. `timing.validation_update_seconds` covers updates 0, 7, 14, and 21 and sums to `validation_seconds`. Checkpoint save and reload time is recorded separately and is excluded from both aggregates. `frozen_state` stores EncDec parameter digests and EncDec persistent-buffer digests at initialization and after updates 7, 14, and 21. Rotary runtime caches are named and excluded from the buffer digest. A failure record identifies the authorisation and implementation commits when those values have been validated, plus the latest stage, update or microbatch when the failure has reached one, failure code, fired stop condition, non-resumable state, and whether retained checkpoints exist. An ordinary exception is `incomplete_evidence_or_manifest` with detail `authorized worker failed; exception_class=<ClassName>`. That detail names the Python exception class and omits the exception message, traceback, sequence text, and tensor contents. No traceback file is written. A precise `M6PilotError` keeps its code, detail, and context. A child failure record remains authoritative for the parent. A failure record and an accepted success manifest cannot both remain. The record does not claim `pilot_completed` and it does not contain sequence text.

Attempt 1, `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_4a2fd6f7e578_gpu1_attempt1`, is a consumed failed engineering attempt. `authorization_failure.json` SHA-256 is `857b5be2ebe3742c853cefb39acea097d8c8712cfcc344a0ba0c12af89136126`. `authorization_consumption.json` SHA-256 is `e6bcc942f39394f57b08afa1224bbb30d0cf58fb2fd5fd953677656027d83d2f`. `m6_pilot_manifest.json` is absent and no checkpoints are present. Completion is `consumed_failed`. The recorded stage, update, and microbatch are null, so the original failure stage and the underlying exception are unrecoverable. Whether biological inputs or model weights were opened is unknown. Attempt 1 may share the attempt 2 path-type cause, but its record cannot establish that.

Attempt 2, `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_97cbb77d1047_gpu0_attempt2`, is a consumed failed engineering attempt. `authorization_failure.json` is 723 bytes and its SHA-256 is `f0b3cf0b7e871b0db46d4c4633cfc15dfae5afdd0c4c1d8751d74802cd6d716d`. `authorization_consumption.json` is 560 bytes and its SHA-256 is `dd24bfb8a4db78c0060f826d75c6286cf2e1bfa4896e0dce103ab49eb3416b1b`. `m6_pilot_manifest.json` is absent and no checkpoints are present. Completion is `consumed_failed`. The failure code is `incomplete_evidence_or_manifest`. The recorded exception class is `AttributeError`. The recorded stage is `biological_inputs`. Update and microbatch are null. `scientific_run_completed` and `pilot_completed` are false. Runtime identity and asset identity completed. The required model assets were read for identity hashing. Model objects were not loaded. TRAIN was opened, hashed, decoded, and counted before the adapter failed. VALIDATION and the validation artifacts were not reached. No optimizer update, checkpoint, success manifest, or scientific result exists. Existing GPU 0 processes were authorized and were not implicated in this failure.

Attempt 3, `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_712ba1856854_gpu0_attempt3`, is a consumed failed engineering attempt. `authorization_failure.json` is 719 bytes and its SHA-256 is `8d2ed2687989eac3c165e0e158c2115435845bce3abf75e903fd8934371fe50d`. `authorization_consumption.json` is 560 bytes and its SHA-256 is `287f2b59f4efe2c3d170f2695e7dc250e14dc07f19a4f8068667c866f27d7c60`. `m6_pilot_manifest.json` is absent and no checkpoints are present. Completion is `consumed_failed`. The failure code is `incomplete_evidence_or_manifest`. The recorded exception class is `FileNotFoundError`. The recorded stage is `model_load`. Update and microbatch are null. `scientific_run_completed` and `pilot_completed` are false. Runtime, asset, TRAIN, VALIDATION, and validation-artifact stages completed. TRAIN and VALIDATION were opened and validated. Validation artifacts were opened and loaded. EncDec model loading began and failed on a runtime-relative file lookup. No optimizer update, checkpoint, success manifest, or scientific result exists. GPU 0 memory and its authorized concurrent processes were not implicated. The checked-in configuration is restored to the inactive document at `712ba18568548adc73013818630c4e4101417a9a`. This schema does not authorise attempt 4.

Attempt 4, `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_7387bb2e5f75_gpu0_attempt4`, is a consumed failed engineering attempt. `authorization_failure.json` is 660 bytes and its SHA-256 is `10896972516ca7e9781e0b3d1af2a214529b65692212ee3d3a8de4009209ab79`. `authorization_consumption.json` is 560 bytes and its SHA-256 is `4d2e962f104cbcc55bba79fbb0726ef36f918d4ca887d3d32f7e832a6971b04e`. `m6_pilot_manifest.json` is absent and no checkpoints are present. Completion is `consumed_failed`. The failure code is `identity_mismatch`. The failure detail is `logical device is not cuda:0`. The recorded stage is `model_load`. Update and microbatch are null. `scientific_run_completed` and `pilot_completed` are false. `authorization_commit` is `2262ba5840f92451a273ab766af3573fffa8382e`. `authorization_parent_commit` and `executing_implementation_commit` are `7387bb2e5f7510508f3b87b4ac228ef341b1b39b`. Model loading and `Accelerator.prepare` were reached. The logical-device check immediately after `prepare` failed before EncDec placement. No optimizer update, checkpoint, success manifest, or scientific result exists. The checked-in configuration is restored to the inactive document at `7387bb2e5f7510508f3b87b4ac228ef341b1b39b`. This schema does not authorise attempt 5.

Attempt 5, `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_8b6dc1f1be70_gpu1_attempt5`, is a consumed failed engineering attempt on physical GPU 1 (UUID `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, `CUDA_VISIBLE_DEVICES=1`, logical `cuda:0`). `authorization_failure.json` is 708 bytes and its SHA-256 is `d4a14b1231ce08fac2bebd6bbf80022fa6469e2da6ef886e3ecf2faee68d55dc`. `authorization_consumption.json` is 560 bytes and its SHA-256 is `c5e2f310c3260a6953107af68b9a07b17953dd9757e86f9d2fba83db8cc69d5a`. `m6_pilot_manifest.json` is absent. Completion is `consumed_failed`. The failure code is `incomplete_evidence_or_manifest` and the failure detail is `authorized worker failed; exception_class=TypeError`. The recorded stage is `checkpoint`, the update is 7, and the microbatch is null. `retained_checkpoint_updates` is empty, `retained_checkpoints_exist` is false, and `scientific_run_completed` and `pilot_completed` are false. `authorization_commit` is `afe29597147dc3740d5695bb17439b6266263031`. `authorization_parent_commit` and `executing_implementation_commit` are `8b6dc1f1be7005f05290405740939962a7c988b5`. Training updates 1 through 7 completed and the update-7 checkpoint files were written. A physical update-7 checkpoint directory exists. It is unverified, non-retained, non-resumable, and unsuitable for scientific interpretation or later training, and it must not be modified, deleted, renamed, resumed from, or reused. The cause is a `pathlib.Path` stored by Diffusers 0.25.0 in the reloaded configuration key `_name_or_path`, which `canonical_json` rejected. A fresh checkpoint reload itself succeeded in a read-only CPU diagnostic. No accepted scientific result exists. The checked-in configuration is restored to the inactive document at `8b6dc1f1be7005f05290405740939962a7c988b5`. This schema does not authorise attempt 6.

**Historical record of the attempt-6 training manifest, as written when it was accepted and before the diagnostic.** Attempt 6, `/home/laura/rnagenesis-mres-runs/m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6`, is the accepted successful training pilot on physical GPU 1 (UUID `GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f`, PCI `00000000:61:00.0`, `CUDA_VISIBLE_DEVICES=1`, logical `cuda:0`). `m6_pilot_manifest.json` is 159,013 bytes, SHA-256 `4b24d5bf5bc392a8f6ee4b8af91adb3582e3a17cac459559632494ec64f8ae52`, canonical JSON, `completion_state: pilot_completed`, authorisation `consumption_state: consumed_successfully`. `authorization_consumption.json` is 560 bytes, SHA-256 `ec822747cca4916331fd7a79dd504a54c425bc7699457ca6d85e9b0c446f0874`. No `authorization_failure.json` exists. `authorization_commit` is `15f49a17081f573970495891e9283a17fc5c3dc2`. `authorization_parent_commit` and `executing_implementation_commit` are `6fd611589d7a3365b793c2ca64cf13c29ef5bfc1`. `diagnostic_generation_status` is `not_performed_requires_separate_authorisation`. The retained weight SHA-256 values are update 7 `7f1cdbd854c1d26c5b8bfe68469bc7e59f5d7293c4a105d724c1c63c83a32f10`, update 14 `0a2fa065f962adaf54e63b797974367915a6552382a8db76c3fbd0c6a0078901`, and update 21 `47b2dc9b392ea766eee7e947f0f92f5a039c42ac714326104e719352d20b5924`. Updates 7 and 14 stay learning-curve evidence only. Update 21 was then the sole D1 pilot checkpoint for the pending diagnostic comparison. The evidence is immutable. At that stage, M6 was not complete. That record did not authorise diagnostic generation, M7, REF, or EVAL. The current closure is in section 9 below.

Checkpoint evidence after the attempt-5 remediation. The checkpoint stage is split into the substages `checkpoint_directory`, `checkpoint_save`, `checkpoint_inventory`, `checkpoint_hash`, `checkpoint_reload`, `checkpoint_config_proof`, and `checkpoint_state_proof`. A failure record carries the substage in `stage` and the checkpoint update in `update`. An unexpected exception inside a substage is `checkpoint_save_reload_incompatibility` with detail `checkpoint operation failed; exception_class=<ClassName>`, and a precise `M6PilotError` keeps its own code and detail. The record omits the exception message, traceback, tensor values, and filesystem paths. The checkpoint tree is the exact set `model_index.json`, `scheduler/scheduler_config.json`, `unet/config.json`, and `unet/diffusion_pytorch_model.safetensors`, checked with `lstat` before hashing and again after reload. Intermediate directories must be real directories. Extra entries, symlinks, and special files fail. In the configuration proof, a top-level `_name_or_path` implementing `os.PathLike` is converted with `os.fspath`, the result must be `str`, and no other key is converted. `ignored_top_level_keys` stays `["_name_or_path"]`. Raw hashes may differ between the original and the reload because the load locations differ. Normalized hashes must be equal. The proof order is structure and fresh-object identity, update and inventory, configuration, then the complete state comparison and entry digests. Entry digests are unchanged by the streaming implementation.

The parent reopens a claimed success manifest after a zero child exit and accepts it only as a regular non-symlink canonical JSON file that passes `validate_production_success_manifest`, with no failure record present. Final CUDA RNG observation fails closed at `rng_final_observation` and is not replaced by the initial CUDA state. Child failures before training keep their precise code and stage. `STOP_CONDITION_CODES` is the exhaustive active-path registry: a success manifest records every code with `fired: false`, and a failure's `fired_stop_condition` must be registered. `cli_argument_rejected` and `environment_injection_rejected` stay outside that registry because they fire before a directory is consumed. Nested validation evidence is cross-checked: update 0 has a null relative record; updates 7, 14, and 21 match the review-item schema and the aggregate MSE values; worsening flags equal `later > initial`; and `validation_review.observations` match those relative records. Checkpoint configuration and state digests are SHA-256, equality flags match the digests, `configuration_compatible` matches normalized equality, and the ordered state aggregate and parameter-name digest are recomputed from `entry_digests`.

REF and EVAL stay closed. Their contract hashes may appear as metadata. Their opened flags are false. The manifest does not contain an output directory until a future authorisation commit binds one, and this checked-in schema does not supply that path.

## 9. M6 update-21 diagnostic manifest

Schema version `m6-diagnostic-manifest-1`. The configuration schema version is `m6-diagnostic-config-1`. This section describes the manifest that a later, separately authorised update-21 diagnostic run would write. It does not authorise that run, a GPU, a checkpoint load, TRAIN access, M7, REF, or EVAL. The checked-in configuration `config/experiments/D1_update21_diagnostic_generation.yaml` is inactive and binds no GPU, output directory, timestamp, or authorisation.

The manifest is canonical JSON with an exact key set: `accounting`, `authorisation`, `b1_reference`, `checkpoint`, `closure`, `comparison`, `consequence`, `experiment_id`, `gpu`, `hard_guardrails`, `ledgers`, `manifest_schema_version`, `metrics`, `normalisation`, `provenance`, `report_only_diagnostics`, `roles`, `schedule`, `status`, and `training_evidence`. A missing key and an unexpected key are both rejected, including inside `accounting`. The manifest contains no sequence text.

- `accounting` reports raw attempts (1,000), parsed, valid, invalid, empty or unparseable, unique valid, duplicates, early-EOS observations, exact length hits, length mismatches (valid attempts whose normalised length differs from the request), generation invocations (112), and the counts of replacements, resampled attempts, and dropped attempts, which are zero. Exact hits, length mismatches, and invalid attempts sum to the raw attempts.
- `schedule` records SHA-256 `0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0`, the length-vector hash, the NumPy version, and that the rebuilt schedule equals the accepted file byte for byte.
- `checkpoint` records update 21, the raw weight variant, the four-member inventory, the weight SHA-256 before and after generation (equal), and that no other update and no B1 diffusion weight was loaded.
- `b1_reference` records the accepted pool files and hashes, that the B1 metrics were recomputed from the ledger and equal the accepted metrics file, and `regenerated: false` and `rerun: false`.
- `normalisation` names the approved M1 cleaner and its SHA-256, records that raw text is retained beside normalised text, that nothing further is trimmed, padded, rejected, replaced, or resampled, and that an independent reconciliation of the boundary-run rule passed.
- `hard_guardrails` holds the five approved decisions in order, their values, `checkpoint_eligible`, an `outcome` of `passed` or `failed`, and `exact_hit_rate_is_a_threshold: false`. Requested-length exact-hit rates are reported in `metrics` and are not thresholds.
- `report_only_diagnostics` carries the hash of the report file. `comparison` places the D1 update-21 and accepted B1 figures side by side.
- `roles` records TRAIN as opened for exact-copy and nearest-TRAIN diagnostics only, VALIDATION, REF, and EVAL as not opened, and the B1 pool as read-only evidence.
- `closure` records `m6_complete: false`, `m6_closed_by_this_run: false`, `human_review_required: true`, `m7_authorised: false`, `ref_authorised: false`, `eval_authorised: false`, and `checkpoint_selected: false`.

The run directory also holds `authorization_consumption.json`, the schedule copy, the raw ledger, the audited ledger, the invocation output manifest, the metrics file, the guardrail file, the report file, a manifest hash report, and the untouched `generation.py` outputs. A failure leaves `authorization_failure.json` and no manifest. The failure is not resumable.

`ledgers` lists the SHA-256 of the raw ledger, audited ledger, invocation output manifest, metrics, guardrails, schedule copy, and the consumption record. The writer reopens the manifest, requires canonical bytes, and verifies each of those files and the report and hash report against the manifest before it returns success. `report_only_diagnostics` includes `maximum_edit_similarity_to_train`, defined as one minus the minimum Levenshtein distance to TRAIN divided by the longer sequence length. It is an edit-based similarity and not a sequence identity. Reverification reruns the metrics and guardrails from the written audited ledger and requires exact equality with the metrics file, the guardrail file, the manifest, and the comparison, and binds provenance (implementation hashes, generation inputs, EncDec and patch assets, authorisation, GPU) to the validated authorisation and the pinned inventories.

`authorization_failure.json` has the exact keys `schema_version`, `status`, `code`, `detail`, `authorisation_id`, `authorization_commit`, `authorization_parent_commit`, `executing_implementation_commit`, `output_directory`, `consumption_state`, `gpu`, `stage`, `invocation_index`, `checkpoint_state`, `resumable`, `reuse_permitted`, `m6_complete`, and `m7_authorised`. It contains no sequence text, traceback, third-party exception message, or tensor contents. The output directory and the consumption record exist before TRAIN is opened or the checkpoint is read.

Accepted evidence. `/home/laura/rnagenesis-mres-runs/m6_d1_update21_diagnostic_6953687e2e9_gpu0_attempt1/m6_diagnostic_manifest.json` is 86,206 bytes, SHA-256 `95074f0d76ab11cf43146e672bc75399da56dd9b2ffeef8fa14a39c7f8acd959`, with `authorisation.consumption_state: consumed_successfully` and `hard_guardrails.outcome: passed`. The authorization commit is `0682185758eb62d9401706b1e37e02468c4c9fbb` and the single parent and implementation commit is `6953687e2e9e36bb1670a7b2b9faaa18849c3711`. The manifest's `closure` block is written by the run and stays `m6_complete: false` and `checkpoint_selected: false`. Those fields record the run's own scope, not the milestone state, and the immutable manifest is not rewritten. The M6 closure and the selection of the raw update-21 checkpoint were made later by the human gate and are recorded in the implementation plan and [M6 pilot implementation](m6_pilot_implementation.md) section 12. The configuration `config/experiments/D1_update21_diagnostic_generation.yaml` is restored to its inactive form, with its pre-execution design-time wording preserved. Neither that file nor the run-time `closure` block of the immutable manifest is the current milestone-status authority. The human-gate closure documents are authoritative for M6 completion and checkpoint selection.

## 10. M7 manifests (inactive package)

**Historical status, 6 October 2026: M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED.** This section describes the three manifests and the failure record that a later, separately authorised M7 would write. At that date it authorised no run, no GPU, no biological access, and no run directory. No M7 authorisation existed, seeds 43 and 44 had not run, and M7 was not complete. The schema of each manifest is unchanged by the 8 October 2026 closure. The accepted-evidence note at the end of this section is the closure record. The three schemas are kept separate on purpose; no one of them carries another's evidence. See [M7 final replicates implementation](m7_final_replicates_implementation.md).

**Authorisation entries.** Configuration schema `m7-replicate-config-1` (the replicate stage), `m7-candidate-guardrail-config-1`, and `m7-final-selection-config-2` (revision 4; the final-selection stage gained an authorisation schema). An authorisation-only commit may change only the stage's own configuration file. The replicate configuration may carry one or two entries, one per seed. Each entry holds exactly: `activation_status`, `applied_learning_rate_trace_sha256`, `authorisation_id`, `authorisation_timestamp`, `authorization_parent_commit`, `b1_relative_path`, `b1_unet_config_sha256`, `b1_weight_sha256`, `consumed`, `cuda_visible_devices`, `evidence_directory`, `executing_implementation_commit`, `expected_checkpoint_names`, `expected_epochs`, `expected_update_counts`, `forbidden_initialisation_weight_sha256`, `gpu_uuid`, `implementation_config_sha256`, `implementation_file_hashes`, `interpreter`, `ld_library_path`, `logical_device`, `output_directory`, `pci_bus`, `permitted_roles`, `phase`, `physical_gpu_index`, `reuse_permitted`, `scope`, `seed`, `session`, `single_use`, and the TRAIN, VALIDATION and validation-artifact identity fields. The id must contain `seed43` or `seed44` and equals the output directory name. The tracked file never stores `authorization_commit`. The launcher accepts an authorisation id only. `ld_library_path` is `null` or one exact absolute-path string (colon-separated, normalised, no empty, relative or `..` component). `interpreter` is `{path, resolved_path, sha256, size}`: the exact pinned RNAGenesis H200 interpreter path, and the resolved path (a `python3.8` file inside that environment), SHA-256 and size of the executable. The inactive documents bind neither. A candidate-guardrail entry carries the same `implementation_config_sha256`, `implementation_file_hashes` and `ld_library_path` fields, `interpreter`, plus `candidate_seed`, `candidate_epoch`, `candidate_update`, `checkpoint_directory`, `checkpoint_member_sha256`, `checkpoint_relative_name`, `checkpoint_training_implementation_commit`, `checkpoint_weight_sha256`, `ranking_position`, `preceding_candidates`, `replicate_manifest_path`, `replicate_manifest_bytes`, `replicate_manifest_sha256` and `validation_ranking_sha256`. `authorization_parent_commit` and `executing_implementation_commit` are the guardrail implementation being executed. `checkpoint_training_implementation_commit` is the sealed training commit named by the selected checkpoint and by the completed replicate manifest; it is not required to equal the guardrail execution commit, and it must be an ancestor of that commit. The candidate launcher reopens the bound replicate manifest and trusts no value of the entry that the manifest does not confirm. The candidate success manifest records the same training commit on `authorisation.checkpoint_training_implementation_commit`, and the checkpoint directory name is checked against that commit. Final selection, updated in the same migration, binds that recorded training commit to the replicate manifest's `authorisation.executing_implementation_commit` and does not treat the guardrail execution commit as checkpoint provenance. That binding is per seed. Sequential single-use authorisations give seed 43 and seed 44 different training commit ids, and the raw `implementation_config_sha256` of each replicate manifest hashes the parent YAML together with that authorisation state. Cross-seed selection does not require those commit ids or those configuration hashes to be equal, and it does not treat one commit being an ancestor of the other as scientific equality. It compares sealed implementation-file hashes, B1 identity, architecture, the learning-rate schedule and fixed protocol, TRAIN and VALIDATION identities, validation artifacts, and non-seed hyperparameters. Authorisation ids, authorisation commits, checkpoint names, output paths, timestamps and other per-seed values are not cross-seed drift.

**Final-selection entry** (`m7-final-selection-config-2`; exactly one entry, CPU only, no GPU, interpreter or `LD_LIBRARY_PATH` field). Exact keys: `activation_status`, `authorisation_id` (an `m7_..final_selection..` id that is neither a replicate nor a candidate id), `authorisation_timestamp`, `authorization_parent_commit`, `consumed`, `deviation`, `evidence_directory`, `executing_implementation_commit`, `guardrail_manifests`, `implementation_config_sha256`, `implementation_file_hashes`, `output_directory`, `permitted_roles` (`SEALED_GUARDRAIL_MANIFEST`, `SEALED_REPLICATE_MANIFEST`), `phase`, `replicate_manifests`, `reuse_permitted`, `scope`, `session`, `single_use`. `replicate_manifests` has one or two rows `{bytes, path, seed, sha256}` (seeds 43 and 44, or 43 alone); `guardrail_manifests` has one row `{bytes, epoch, path, seed, sha256}` per evaluated candidate, in `(seed, epoch)` order. Each path is exactly `<run root>/<run directory>/<manifest name>`. `deviation` is `null` for two seeds and the sealed `m7-operational-deviation-1` record for seed 43 alone. The authorisation commit may change only `authorisation_entries`, `consumable_by_executable_workflow`, `document_status` and `execution.authorised`; `gpu_identity_bound` and `biological_paths_permitted` stay false. The inactive document has `authorisation_entries: []` and binds none of these. The launcher writes `authorization_consumption.json` (`m7-final-selection-consumption-1`) and then `m7_final_selection_manifest.json` into the bound directory, or `authorization_failure.json` after consumption.

**Replicate manifest** (`m7-replicate-manifest-1`, file `m7_replicate_manifest.json`, canonical JSON). Exact keys: `accounting`, `applied_learning_rate_trace`, `authorisation`, `b1_identity`, `checkpoints`, `closure`, `completion_state`, `config_version`, `configuration`, `data_roles`, `deviations`, `environment`, `epoch_plan`, `experiment_id`, `free_space`, `frozen_state`, `gpu`, `initialisation_isolation`, `manifest_schema_version`, `memory`, `optimizer`, `post_schedule_position`, `ref_eval_access`, `repository`, `residual_limitations`, `restart_policy`, `resume_supported`, `rng`, `run_id`, `schedule`, `schema_version`, `seed`, `timing`, `train_update_observations`, `validation_artifacts`, `validation_observations`, `validation_ranking`, `warnings`.

- `applied_learning_rate_trace` is the 105 recorded values; `schedule.applied_learning_rate_trace_sha256` is `37013ac0a50290dbb476f4cdec806f058b8fb3347d967ac2d6e59b6e07aeae50`; update 1 is `0.1 x LR`; `post_schedule_position` is position 106, unapplied, and not a PyTorch `last_epoch`.
- `epoch_plan` has five rows (first and last update, 84 microbatches, 21 updates, final window `[8, 8, 8, 5]`, and a distinct permutation digest each).
- `train_update_observations` has 105 rows with the epoch, the recorded learning rate, loss, pre-clip norm, clip result and the denoiser-change evidence.
- `validation_observations` has six rows. Update 0 has `candidate: false` and `epoch: null`. The other five are candidates at epoch boundaries.
- `validation_ranking` holds the candidates in rank order with `excludes_update_0: true` and the rule `fixed_draw_validation_mse_ascending_then_earlier_epoch_on_exact_tie`. It is an ordering only.
- `checkpoints` has five proofs, each with the directory name, the four member hashes, the weight hash, an `inventory` block (exact members, regular non-symlink files, single link counts, symlink-free ancestry, one device, tree unchanged across hash and reload), the configuration proof, and a `state_comparison` over parameters and persistent buffers (`comparison_scope: complete`).
- `b1_identity` records the observed B1 assets and the aggregate digest, parameter-name digest and entry count of the freshly loaded state. `initialisation_isolation` records the three forbidden M6 weight hashes and that none was loaded or saved.
- `environment` records the allow-listed child environment (with the fixed `PATH` constant and no copied parent `PATH`) with zero stray names, offline and bytecode controls and the isolated locations. `gpu` records logical `cuda:0`, one device, the physical index, UUID, PCI bus and the identity source. `free_space` records the budget. `timing` records the end-to-end time (the quantity used by the human scheduling rule), the training, validation and checkpoint spans.
- `closure` is exactly `candidate_diagnostics_performed: false`, `cross_seed_claim: false`, `eval_opened: false`, `human_gate_required: true`, `m7_complete: false`, `m8_generation_performed: false`, `ref_opened: false`, and `scope: single_seed_training_evidence_only`.
- No key may contain a selection, guardrail, eligibility, ensemble, best-epoch or winner fragment. No sequence text or tensor content appears.

**Candidate-guardrail manifest** (`m7-candidate-guardrail-manifest-1`, file `m7_candidate_guardrail_manifest.json`). One seed, one epoch, one checkpoint. Exact keys: `accounting`, `authorisation`, `candidate`, `checkpoint`, `closure`, `completion_state`, `config_version`, `environment`, `experiment_id`, `gpu`, `guardrails`, `input_roles`, `ledgers`, `manifest_schema_version`, `preceding_candidates`, `provenance`, `ref_eval_access`, `replicate_binding`, `report_only`, `run_id`, `schema_version`. `environment.interpreter` is the observed (and bound) interpreter identity. `environment.ld_library_path` is `{bound, passed_to_child, sha256}`, where `sha256` is the digest of the exact UTF-8 value the authorisation bound (the value itself is never stored), or `{false, false, null}` when none was bound. The replicate manifest records the same block under `environment.ld_library_path`. `ledgers` holds the SHA-256 of the seven retained evidence files (raw and audited attempt ledgers, invocation-output manifest, metrics, guardrail values, report-only diagnostics, schedule copy); `report_only.diagnostics` points at the diagnostics file (`file`, `sha256`) with a `headline` and the flags `thresholds_defined: false`, `edit_similarity_is_sequence_identity: false` and `effect_on_ranking_or_thresholds: none`; the audited ledger keeps each raw string beside its normalised string and every one of the 1,000 attempts. `provenance` holds the approved-cleaner, metrics-module and metrics-configuration hashes, the generation-input and frozen-EncDec identities, the authorised implementation file hashes and the RNAGenesis pin, and must equal the pinned identities. `replicate_binding` holds the replicate manifest hash, the sealed ranking hash, the checkpoint weight hash and the validation MSE. `preceding_candidates` lists the failed manifests of every earlier-ranked candidate. `guardrails` holds the five values and decisions (recomputed on validation) and `passed`. `report_only` has no threshold. `closure` has `no_selection_claim: true` and `m7_complete: false`. `input_roles` never contains REF, EVAL, or VALIDATION_CSV.

**Final-selection manifest** (`m7-final-selection-manifest-2`, file `m7_final_selection_manifest.json`, CPU only; the version was bumped from `-1` because candidate rows gained `members_sha256`). Exact keys: `allowed_seed_plan`, `candidate_table`, `closure`, `completed_seeds`, `config_version`, `deviation`, `experiment_id`, `guardrail_manifests`, `lazy_evaluation_traces`, `m8_allocation`, `m8_boundary`, `manifest_schema_version`, `ref_eval_access`, `replicate_manifests`, `schema_version`, `seed_records`, `selected_set`, `selected_set_sha256`, `selection_outcome`, `validation_rankings`. The candidate table has five rows per completed seed (`checkpoint_name`, `epoch`, `guardrail`, `members_sha256` with all four checkpoint member digests, `rank`, `seed`, `update`, `validation_mse`, `weight_sha256`). Every nested record has an exact key set and every digest is a lowercase SHA-256. Each `validation_rankings[].ranking_sha256` is the SHA-256 of the replicate-style ranking record (`excludes_update_0`, `ranked_candidates`, `rule`) rebuilt from the candidate table, and the guardrail index equals exactly the evaluated candidate rows. `selected_set_sha256` is the SHA-256 of the canonical selected set sorted by seed (each row carries all four member hashes), is a deterministic content hash and not an authenticity mechanism, and is null with `selection_outcome: no_eligible_checkpoint`. `closure` is `human_gate_required: true`, `m7_complete: false`, and every REF, EVAL, VALIDATION and M8 flag false. Input order never changes the canonical bytes. The manifest does not gain a provenance field. Checkpoint names still end in the sealed training commit, taken from the replicate checkpoint and checked against the guardrail's `checkpoint_training_implementation_commit`. The guardrail execution commit remains only on the hashed guardrail manifest. Those two identities are not stored in one selection-manifest field. The selection entry's own `executing_implementation_commit` is the selection implementation and is separate from both.

**Operational deviation record** (`m7-operational-deviation-1`). Omitted seed 44, completed seed 43, the seed-43 replicate manifest hash, the measured end-to-end time equal to that manifest's `timing.end_to_end_seconds`, the decision time, the projection `decision time + 1.25 x time + 2 hours` (which must exceed the hard target `2026-10-08T17:00:00+11:00`), `depends_on_scientific_results: false`, `recorded_before_m8_generation: true`, `m8_generation_started: false`, `sealed: true`, and a self-hash over every other field.

**Failure record** (`authorization_failure.json`, schema `m7-failure-record-1`). Exact keys: `authorisation_id`, `authorization_commit`, `authorization_parent_commit`, `candidate`, `code`, `completion_state`, `consumption_state`, `detail`, `entry_kind`, `epoch`, `executing_implementation_commit`, `m7_complete`, `manifest_written`, `microbatch`, `output_directory`, `partial_checkpoint`, `resumable`, `retained_checkpoint_epochs`, `reuse_permitted`, `schema_version`, `scientific_run_completed`, `seed`, `stage`, `status`, `update`. `partial_checkpoint` records the directory name, the epoch and a state of `none`, `directory_created`, `saved_unverified` or `verified`. The detail carries a code and an exception class only; it never carries a library message, a sequence or a tensor. If this record cannot be written, the original error is kept and the secondary failure is reported on it.

REF and EVAL stay closed. Their contract hashes may appear as metadata only. No M7 manifest may contain a REF- or EVAL-derived value.

Accepted evidence, 8 October 2026. The final-selection manifest `/home/laura/rnagenesis-mres-runs/m7_d1_final_selection_b5de24327ed5_attempt1/m7_final_selection_manifest.json` is 13,124 bytes, SHA-256 `49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c`, `selection_outcome: selected_set_complete`, selected-set SHA-256 `af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f`. Its `closure` stays `human_gate_required: true`, `m7_complete: false`, and `m8_generation_performed: false`. The replicate and guardrail manifests keep the same run-time `m7_complete: false`. Those fields are not rewritten and are not the milestone-status authority. The human gate accepted the selected set afterwards. That acceptance is recorded in the implementation plan and in [M7 final replicates implementation](m7_final_replicates_implementation.md) section 14. `config/experiments/D1_candidate_guardrails.yaml` and `config/experiments/D1_final_selection.yaml` are restored to their inactive documents. `config/experiments/D1_final_replicates.yaml` remains the seed-44 authorisation document; the validators accept no consumed document status, and the tests require that live file. M8 generation is not authorised.

## 11. M8 manifests (inactive proposal)

**Status: M8_RAW_GENERATION_READY_FOR_REVIEW_NOT_AUTHORISED.** This section describes the manifests a later, separately authorised M8 arm or assembly would write. It authorises no run, no GPU, no biological access, and no output directory. The checked-in configuration is `config/experiments/M8_raw_generation.yaml`, schema `m8-raw-generation-config-1`. Its `authorisation_entries` and `assembly_authorisation_entries` are empty. An M7 configuration path, an M7 schema version, an `m7_` authorisation id, and the live seed-44 M7 authorisation are refused as M8 authority. Sealed M7 manifests are never rewritten. See [M8 raw generation](m8_raw_generation.md).

**Arm manifest** (`m8-arm-manifest-1`, file `m8_arm_manifest.json`). One of four single-use arms: B1 block A, B1 block B, D1 seed 43 block A, or D1 seed 44 block B. A success manifest binds the authorisation and repository identity, separate controller and child interpreter observations, the environment and library-path claim, the physical and logical GPU identity with a zero compute-process observation, the complete sampler configuration, both the arm and paired-block schedule hashes, the condition, the technical block, and the D1 training seed where applicable. `repository_identity.mres_commit` is the live authorization commit. `proposal_base_commit` is the proposal base and is not that observed commit. `authorization.active_configuration_raw_sha256` is the SHA-256 of the exact YAML bytes parsed at launch. `active_configuration_sha256` is the canonical projected identity. It binds the model or checkpoint assets, the invocation ledger, exactly 15,000 raw-attempt records, every raw-output hash in that ledger order, and the exact pre/post B1 or D1 asset inventory. `selected_set_evidence` is `{applicable: false}` for B1. For D1 it records the approved manifest path, byte count, manifest SHA-256, selected-set SHA-256, training seed, checkpoint name, epoch 5, update 105, and member hashes. It records timestamps and a nonnegative elapsed duration. The raw-attempt count is the only accounting total. `filtering_performed`, `cleaner_invoked`, and `replacement_or_replenishment_performed` are false. REF, EVAL, VALIDATION, and TRAIN sequence access are false. Later evaluation is required and reuse is prohibited. Assembly rejects a contradiction in any of those nested blocks even when the outer manifest hash was recomputed.

**Raw-attempt record** (`m8-raw-attempt-1`). The record id is `m8:{condition_id}:master:{master_index_as_five_digits}`. The record carries the condition, master attempt index, technical block, D1 training seed or null for B1, checkpoint or B1 identity, run and authorisation ids, generation seed, invocation index, batch number, within-batch position, requested biological length, `max_seq_len`, the source raw-file relative path and SHA-256, the line index, and `raw_decoded_text`. Exact raw bytes remain authoritative in the retained invocation file named by that path and hash. `raw_decoded_text` is the deterministic UTF-8-else-Latin-1 decoded representation of the corresponding line. The record carries no validity, acceptance, rejection, biological, or filtered claim.

**Assembly manifest** (`m8-assembly-manifest-1`, file `m8_assembly_manifest.json`). Assembly is a separate CPU-only authorisation. The presence of generation files does not make it runnable, and an active generation status does not activate assembly. For B1 and for D1 separately, it accepts exactly two arm manifests whose paths are `m8_arm_manifest.json` under canonical direct-child arm directories. It binds its own authorisation and provenance, each source path, byte count, hash, and run id, and the combined ledger byte count and hash, plus timestamps. It recomputes the pinned schedule, checks every record against that schedule and against the retained raw bytes, and emits one combined canonical ledger of exactly 30,000 rows sorted only by master attempt index. It performs no parsing, cleaning, filtering, validity classification, deduplication, or metric computation. `parsing_performed`, `filtering_performed`, `cleaner_invoked`, `deduplication_performed`, `metric_computation_performed`, and `replacement_or_replenishment_performed` stay false.

**Failure record** (`authorization_failure.json`, schema `m8-failure-record-1`). Generation and assembly share this single-use failure record. A consumed failure is not resumed and the output directory is not overwritten. A retry requires a new id, a new authorisation, and a new directory. The record stores the failing invocation index and the number of completed invocations for a generation failure, together with the live authorization commit, its parent, the executing implementation commit, `origin/main`, both `active_configuration_sha256` and `active_configuration_raw_sha256`, and the implementation-file hashes. The raw digest is the exact parsed YAML bytes and is not defaulted to the semantic digest. The detail is message-safe: no traceback, no stderr, no third-party exception text, no sequence content, no credentials, and no environment values. The same safe failure record is written when assembly fails after its consumption record.

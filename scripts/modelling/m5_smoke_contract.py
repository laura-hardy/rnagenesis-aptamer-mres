#!/usr/bin/env python3
"""Non-executable M5 synthetic-smoke contract.

This module validates configuration, authorization, repository state,
fixture identity, model-asset identity, and process isolation. Importing
it does not import torch, Accelerate, Diffusers, RNAGenesis, or
generation.py.

The authorization lifecycle is the accepted development-pool pattern.
The authorization commit stores authorization_parent_commit and
executing_implementation_commit. It does not store its own hash. The
parent gate computes that hash from live HEAD. The config hash stored in
a later authorization is the parent blob, because a file cannot contain
its own digest. M5 fields that the older block did not need are an
experiment-specific key set on that same lifecycle, not a second
authorization mechanism.

The checked-in document is inactive. It contains no physical GPU index,
UUID, or PCI bus, and it does not authorise execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

MRES_ROOT = Path("/home/laura/rnagenesis-aptamer-mres")
RNAGENESIS_ROOT = Path("/home/laura/RNAGenesis")
CONFIG_RELATIVE = "config/experiments/D1_diffusion_smoke.yaml"
CONFIG_PATH = MRES_ROOT / CONFIG_RELATIVE
CONTRACT_RELATIVE = "scripts/modelling/m5_smoke_contract.py"
HARNESS_RELATIVE = "scripts/modelling/m5_smoke_harness.py"
CONTRACT_PATH = MRES_ROOT / CONTRACT_RELATIVE
HARNESS_PATH = MRES_ROOT / HARNESS_RELATIVE
FIXTURE_RELATIVE = "tests/modelling/fixtures/m5_synthetic_smoke_sequences.txt"
FIXTURE_BASENAME = "m5_synthetic_smoke_sequences.txt"
FIXTURE_PATH = MRES_ROOT / FIXTURE_RELATIVE
FIXTURE_SHA256 = "123e0416257469f160f65c02ccf900109c0bfd52ee8c4b383893b40d28847558"
PINNED_PYTHON = "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"
RNAGENESIS_BRANCH = "mres-d1-diffusion-finetune"
RNAGENESIS_HEAD = "e3b855bbf4d1af376f43747643fa30afd662828c"
BASE_MRES_COMMIT = "7fbf79d530e528b6be78a22d89cb9cc991914a0b"
INACTIVE_DOCUMENT_STATUS = "APPROVED_FOR_M5_IMPLEMENTATION_NOT_EXECUTION"
EXECUTABLE_DOCUMENT_STATUS = "APPROVED_FOR_M5_SYNTHETIC_EXECUTION"
INACTIVE_SMOKE_STATUS = "IMPLEMENTATION_ONLY_NOT_AUTHORISED"
ACTIVE_SMOKE_STATUS = "AUTHORISED_FOR_EXECUTION"
ACTIVE_UNCONSUMED_STATUS = "active_unconsumed"
AUTHORISATION_NAME = "smoke_execution_authorisation"
LOGICAL_DEVICE = "cuda:0"
CUDA_DEVICE_ORDER = "PCI_BUS_ID"
MANIFEST_SCHEMA_VERSION = "m5-synthetic-smoke-manifest-1"
SCHEMA_VERSION = "m5-synthetic-smoke-config-1"
EXPERIMENT_ID = "m5_synthetic_diffusion_smoke"
PARTIAL_SUFFIX = ".partial"
RUN_ROOT = Path("/home/laura/rnagenesis-mres-runs")
PYCACHE_DIRECTORY_NAME = "python_pycache"
RUNTIME_CACHE_DIRECTORY_NAME = "isolated_runtime_cache"
LATENT_QUERIES = 32
LATENT_CHANNELS = 160

# Directory porcelain accepted by the B1 runners. The set must match exactly.
KNOWN_RNAGENESIS_UNTRACKED = (
    ".cache/",
    "__pycache__/",
    "checkpoints/",
    "configs/",
    "generation_sequences/",
    "models/autoencoder/__pycache__/",
    "models/autoencoder/decoder/checkpoints/",
    "models/autoencoder/decoder/progen/progen2/models/progen/__pycache__/",
    "models/autoencoder/encoder/biomap/__pycache__/",
    "models/autoencoder/encoder/esm/__pycache__/",
    "models/diffusion_models/__pycache__/",
    "tests/__pycache__/",
    "zenodo_downloads/",
)
# Configuration files observed in that untracked classification. Any other
# untracked YAML file is unexpected. Directory membership is not identity.
KNOWN_UNTRACKED_CONFIG_FILES = (
    "configs/rnagenesis/autoencoder/config.yaml",
    "configs/rnagenesis/classifier/mlp_160_32.yaml",
)

DENIED_BASENAMES = frozenset(
    [
        "corpus_final.txt",
        "ft_train.csv",
        "ft_validation.csv",
        "ref.csv",
        "eval.csv",
    ]
)
DENIED_PATH_COMPONENTS = frozenset(["TRAIN", "VALIDATION", "REF", "EVAL"])
DENIED_HASHES = {
    "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d": "TRAIN",
    "cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd": "VALIDATION",
    "531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23": "REF",
    "ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015": "EVAL",
}
B0_UNET_CONFIG_SHA256 = "fab9c517efba8269c0edf194b7d0379f317e93da0f849b5ce815e098088b4756"
B0_UNET_WEIGHT_SHA256 = "149f012287b1ae83865c25867d7c0bbe0952fa51bcc068e259725092d5dff0ca"
PROHIBITED_SUBSTITUTE_SHA256 = {
    "57035677145791f1789ef2ba01fa50d86b0487a4023cfc7bd4e860ea1f5b28bb": "checkpoint-15000",
    "666f501700055e79b4f4f469d357752a7f110430db1bc9273376ebc55e0259c5": "checkpoint-30000",
}
# Accepted M0/M1 identities. Each record is relative path, SHA-256, size, role.
# Sizes and hashes are copied from the accepted manifests. They are not re-invented.
REQUIRED_MODEL_FILES = (
    ("configs/rnagenesis/diffusion/model_index.json", "05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e", 217, "b1_pipeline_index"),
    ("configs/rnagenesis/diffusion/scheduler/scheduler_config.json", "6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396", 492, "b1_scheduler"),
    ("configs/rnagenesis/diffusion/unet/config.json", "3a9975ff165bbd5ca82923e6ed1c5ed7eb383a23f4f3f55db713c995031f8ee3", 531, "b1_unet_config"),
    ("configs/rnagenesis/diffusion/unet/diffusion_pytorch_model.safetensors", "c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26", 7847725416, "b1_unet_weights"),
    ("configs/rnagenesis/autoencoder/config.json", "ab309231b75405af3e2ef6fe49e4e74c1b96021ef2a4f61b46e5796b8799378a", 530, "encdec_config"),
    ("configs/rnagenesis/autoencoder/pytorch_model.bin", "3c4e34f7626c94416d504c16569b5f3f785fffe77889b9886344477b95e74c68", 3476049782, "encdec_weights"),
    ("models/autoencoder/encoder/biomap/config.json", "bf7ef6843232f370f3f7fc37d608f85cb0ff0d75291eed35cef52213e34978f7", 1369, "biomap_encoder_config"),
    ("models/autoencoder/decoder/progen_configs/config-progen2-small-rna_tokenizer_v2.json", "42f15517e05ce96d78337fbc1bf20ffc580424fe88cbfcb2c81550b17cc7283e", 915, "decoder_config"),
    ("models/autoencoder/decoder/progen_configs/tokenizer_rna_v2.json", "6d8a20879cec3544cf0f33b0d481fbd5ead6a2bead2dbf1649449172c8336921", 1317, "tokenizer"),
)
DIFFUSERS_PATCH_PATH = (
    "/home/laura/miniconda3/envs/rnagenesis-h200/lib/python3.8/"
    "site-packages/diffusers/models/normalization.py"
)
DIFFUSERS_PATCH_SHA256 = "09bc632069f1d6e1dc1b1cb7f5b9ca096c83e3010835f11b8dc6c58b45aa13a5"
DIFFUSERS_PATCH_SIZE = 9516
BIOMAP_CONFIG_RELATIVE = "models/autoencoder/encoder/biomap/config.json"
ACCEPTED_RUNTIME_VERSIONS = {
    "python": "3.8.13",
    "torch": "2.1.2+cu121",
    "diffusers": "0.25.0",
    "accelerate": "0.25.0",
    "transformers": "4.36.2",
}
CHECKPOINT_JSON_MEMBERS = (
    "model_index.json",
    "scheduler/scheduler_config.json",
    "unet/config.json",
)
CHECKPOINT_WEIGHT_MEMBERS = (
    "unet/diffusion_pytorch_model.safetensors",
    "unet/diffusion_pytorch_model.bin",
)
EXTERNAL_MANIFEST_HASH_NAME = "m5_smoke_manifest.sha256"
PHYSICAL_MICROBATCH_CANDIDATE = 8
ACCUMULATION_MICROSTEPS = 4
INTENDED_EFFECTIVE_BATCH = 32
LOSS_SCALE_NAME = "loss_divided_by_accumulation_count"
GENERATION_SEPARATION_BASIS = "on_disk_checkpoint_hash_and_tensor_digest"
OPTIMIZER_MEMBERSHIP_EVIDENCE_BASIS = "live_adamw_parameter_identities"
TRAINING_RELEASE_BASIS = "weakref_death_before_generation_reload"
TRAINING_RELEASE_LABELS = (
    "original_denoiser",
    "resumed_denoiser",
    "representative_original_parameter",
    "representative_resumed_parameter",
    "proof_optimizer",
    "restored_optimizer",
    "proof_scheduler",
    "restored_scheduler",
    "saved_pipeline",
    "resumed_pipeline",
    "in_memory_sidecar_tensor",
    "loaded_sidecar_tensor",
    "resume_loss",
    "step_loss",
    "microstep_loss",
    "fp32_loss_tensor",
    "fixed_latent",
    "fixed_noise",
    "fixed_timesteps",
    "batch_input_ids",
)
# Accepted B1 diffusion files. Directory entries are not members. An EMA
# filename is not a compatible starting state, and any extra member fails
# asset identity.
B1_DIFFUSION_DIRECTORY_INVENTORY = (
    "model_index.json",
    "scheduler/scheduler_config.json",
    "unet/config.json",
    "unet/diffusion_pytorch_model.safetensors",
)
PARAMETER_TABLE_COMPONENTS = (
    "encoder",
    "qformer",
    "query_tokens",
    "latent_projection",
    "decoder",
    "denoiser",
)
OBSERVED_FILE_HASH_KEYS = (
    "configuration",
    "fixture",
    "implementation_contract",
    "implementation_harness",
    "starting_assets",
    "checkpoint_inventory",
    "resume_sidecar",
    "generation_output",
)
B1_DISTINGUISHING_ROLES = frozenset(["b1_unet_config", "b1_unet_weights"])
SOURCE_SUFFIXES = frozenset([".py"])
CONFIG_SUFFIXES = frozenset([".yaml", ".yml"])

# Inactive block: no physical index, UUID, or PCI bus. The authorization
# commit is the only place those three keys may appear.
INACTIVE_AUTHORISATION_KEYS = (
    "authorisation_id",
    "authorisation_active",
    "activation_status",
    "consumed",
    "single_use_run_id",
    "authorization_parent_commit",
    "executing_implementation_commit",
    "rnagenesis_commit",
    "mres_branch",
    "implementation_contract_sha256",
    "implementation_harness_sha256",
    "implementation_config_sha256",
    "fixture_relative_path",
    "fixture_sha256",
    "output_directory",
    "evidence_directory",
    "allowed_smoke_settings_sha256",
    "authorisation_timestamp",
    "scope",
    "synthetic_only",
    "train_access",
    "validation_access",
    "ref_access",
    "eval_access",
    "gpu_use_authorised",
    "authorises_m5_synthetic_smoke",
    "success_claimed",
    "m5_complete",
    "d1_training_authorised",
)
ACTIVE_AUTHORISATION_KEYS = INACTIVE_AUTHORISATION_KEYS + (
    "physical_gpu",
    "gpu_uuid",
    "pci_bus",
)
PRESERVED_AUTHORISATION_FIELDS = (
    "rnagenesis_commit",
    "mres_branch",
    "implementation_contract_sha256",
    "implementation_harness_sha256",
    "fixture_relative_path",
    "fixture_sha256",
    "allowed_smoke_settings_sha256",
    "synthetic_only",
    "train_access",
    "validation_access",
    "ref_access",
    "eval_access",
    "success_claimed",
    "m5_complete",
    "d1_training_authorised",
)
PERMITTED_ACTIVATION_PATHS = frozenset(
    [
        "document_status",
        "consumable_by_executable_workflow",
        "execution.authorised",
        "execution.gpu_authorised_by_this_approval",
        "smoke_execution.executable_now",
        "smoke_execution.status",
        "smoke_execution_authorisation",
    ]
)
EXPECTED_SMOKE_ONLY = {
    "label": "software_behaviour_check",
    "not_biological_learning": True,
    "not_a_d1_hyperparameter_decision": True,
    "learning_rate": "3.0e-5",
    "learning_rate_source": "accepted_initial_project_value",
    "smoke_microbatch": 8,
    "smoke_gradient_accumulation": 4,
    "smoke_effective_batch": 32,
    "smoke_precision": "float32",
    "ema_enabled": False,
    "generation_weights": "raw",
    "overfit_optimizer_updates": 4,
    "overfit_fixed_timestep": 17,
    "overfit_noise_seed": 5,
    "loss_pass_rule": "final_loss_strictly_less_than_initial_loss",
    "loss_decrease_tolerance": "0",
    "generation_count": 2,
    "generation_ddim_steps": 4,
    "generation_eta": "0",
    "smoke_generation_seed": 11,
    "smoke_max_seq_len": 33,
    "decoding": "greedy",
    "does_not_set_m6_or_m7_seeds": True,
    "fixture_record_count": 8,
    "physical_microbatch_candidate": 8,
    "deterministic_fixture_reuse_across_accumulation": True,
    "m5_complete_from_correctness_phase": False,
    "phases": {
        "correctness": {
            "name": "synthetic_correctness",
            "microbatch": 8,
            "gradient_accumulation": 4,
            "effective_batch": 32,
            "precision": "float32",
            "collects_m5_milestone": False,
        },
        "physical_microbatch_feasibility": {
            "name": "bounded_physical_microbatch_feasibility",
            "candidate_microbatch": 8,
            "intended_effective_batch": 32,
            "accumulation_if_candidate_succeeds": 4,
            "attempted_microbatches": [8],
            "fallback_microbatches": [],
            "sweep": False,
            "fail_closed_on_candidate_failure": True,
            "status": "executed_under_the_single_smoke_authorisation",
        },
        "fp32_observation": {
            "precision": "float32",
            "status": "collected_by_the_authorized_sequence",
            "selects_production_precision": False,
        },
        "bf16_numerical_observation": {
            "status": "collected_by_the_authorized_sequence",
            "same_fixed_latent_timestep_and_noise": True,
            "selects_production_precision": False,
            "pass_tolerance": None,
        },
        "starting_ema_inspection": {
            "status": "collected_by_the_authorized_sequence",
            "selects_ema_policy": False,
            "accepted_inventory": "b1_diffusion_directory",
        },
        "generation_weight_state": {
            "record_raw_and_ema_separately": True,
            "smoke_generation_variant": "raw",
            "generation_checkpoint": "original_one_update_smoke_checkpoint",
        },
    },
}
EXPECTED_UNRESOLVED = {
    "physical_microbatch": None,
    "gradient_accumulation": None,
    "production_precision": None,
    "ema_policy": None,
    "m6_seed": None,
    "m7_seeds": None,
    "status": "UNRESOLVED_NOT_A_SMOKE_MEASUREMENT",
}
OFFLINE_CONTROLS = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}
MANIFEST_KEYS = (
    "manifest_schema_version",
    "schema_version",
    "experiment_id",
    "run_id",
    "synthetic_only",
    "authorisation_id",
    "authorisation_consumption_state",
    "mres_implementation_commit",
    "mres_authorization_commit",
    "rnagenesis_commit",
    "tracked_clean",
    "untracked_state",
    "file_hashes",
    "permitted_input_paths",
    "declared_scientific_data_inputs",
    "validated_required_asset_paths",
    "data_input_audit",
    "train_not_accessed",
    "validation_not_accessed",
    "ref_not_accessed",
    "eval_not_accessed",
    "physical_gpu_index",
    "gpu_uuid",
    "pci_bus",
    "gpu_model",
    "logical_device_mapping",
    "package_runtime",
    "parameter_table",
    "shapes_dtypes",
    "optimizer_state",
    "scheduler_state",
    "requested_microbatch",
    "measured_microbatch",
    "actual_batch_shape",
    "requested_accumulation",
    "measured_accumulation",
    "requested_effective_batch",
    "measured_effective_batch",
    "phase_records",
    "precision_used",
    "ema_enabled",
    "starting_ema_inspection",
    "generation_weight_variant",
    "m5_milestone_complete",
    "loss_finite",
    "gradients_finite",
    "gradient_norm",
    "frozen_state",
    "denoiser_update",
    "checkpoint_reload",
    "resume_proof",
    "overfit_trajectory",
    "overfit_pass_rule",
    "overfit_passed",
    "generation_reload",
    "generation_output",
    "peak_training_allocated_bytes",
    "peak_training_reserved_bytes",
    "peak_allocated_bytes",
    "peak_reserved_bytes",
    "memory_peak_accounting",
    "timings",
    "warnings",
    "deviations",
    "failure_state",
    "completion_state",
    "smoke_measurements_are_not_d1_decisions",
)
RESUME_STATE_FIELDS = (
    "optimizer_state",
    "scheduler_state",
    "global_optimizer_step",
    "phase",
    "python_rng",
    "numpy_rng",
    "torch_cpu_rng",
    "torch_cuda_rng",
    "diffusion_generator",
    "scaler_state",
    "ema_state",
    "configuration_identity",
    "implementation_identity",
)
FROZEN_SENTINEL_COMPONENTS = ("encoder", "qformer", "query_tokens", "latent_projection", "decoder")
ROTARY_CACHE_ATTRIBUTES = ("_cos_cached", "_sin_cached", "_seq_len_cached")


class M5SmokeError(Exception):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"


def smoke_settings_sha256(smoke_only):
    return sha256_bytes(canonical_json(smoke_only))


def _is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _is_sha40(value):
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def _require_mapping(value, code, detail):
    if not isinstance(value, dict):
        raise M5SmokeError(code, detail)
    return value


def load_config_bytes(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise M5SmokeError("config_encoding", "configuration bytes are required")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise M5SmokeError("config_encoding", "configuration must be UTF-8 without a BOM or carriage return")
    import yaml

    try:
        loaded = yaml.safe_load(bytes(raw).decode("utf-8"))
    except Exception:
        raise M5SmokeError("config_parse", "configuration could not be parsed")
    return _require_mapping(loaded, "config_shape", "configuration root must be a mapping")


def assert_smoke_only(smoke_only):
    if smoke_only != EXPECTED_SMOKE_ONLY:
        raise M5SmokeError("smoke_settings_invalid", "smoke-only settings drifted from the reviewed contract")
    if smoke_only["does_not_set_m6_or_m7_seeds"] is not True:
        raise M5SmokeError("smoke_settings_invalid", "smoke settings must not settle M6 or M7 seeds")
    if smoke_only["m5_complete_from_correctness_phase"] is not False:
        raise M5SmokeError("smoke_settings_invalid", "a correctness-phase run must not be recorded as M5 completion")
    if int(smoke_only["smoke_microbatch"]) * int(smoke_only["smoke_gradient_accumulation"]) != int(smoke_only["smoke_effective_batch"]):
        raise M5SmokeError("smoke_settings_invalid", "smoke effective batch is not microbatch times accumulation")
    phases = smoke_only["phases"]
    correctness = phases["correctness"]
    if int(correctness["microbatch"]) != int(smoke_only["smoke_microbatch"]):
        raise M5SmokeError("smoke_settings_invalid", "correctness microbatch drifted from the smoke microbatch")
    if int(correctness["effective_batch"]) != int(smoke_only["smoke_effective_batch"]):
        raise M5SmokeError("smoke_settings_invalid", "correctness effective batch drifted")
    if int(smoke_only["physical_microbatch_candidate"]) != PHYSICAL_MICROBATCH_CANDIDATE:
        raise M5SmokeError("smoke_settings_invalid", "the only physical-microbatch candidate is 8")
    if int(smoke_only["fixture_record_count"]) != PHYSICAL_MICROBATCH_CANDIDATE:
        raise M5SmokeError("smoke_settings_invalid", "the fixture does not contain one record per candidate microbatch row")
    if smoke_only["deterministic_fixture_reuse_across_accumulation"] is not True:
        raise M5SmokeError("smoke_settings_invalid", "accumulation must record deterministic fixture reuse")
    feasibility = phases["physical_microbatch_feasibility"]
    if int(feasibility["intended_effective_batch"]) != INTENDED_EFFECTIVE_BATCH:
        raise M5SmokeError("smoke_settings_invalid", "feasibility phase is not tied to effective batch 32")
    if int(feasibility["candidate_microbatch"]) != PHYSICAL_MICROBATCH_CANDIDATE:
        raise M5SmokeError("smoke_settings_invalid", "feasibility candidate is not microbatch 8")
    if feasibility["attempted_microbatches"] != [PHYSICAL_MICROBATCH_CANDIDATE] or feasibility["fallback_microbatches"] != []:
        raise M5SmokeError("smoke_settings_invalid", "feasibility must not sweep or fall back")
    if feasibility["sweep"] is not False or feasibility["fail_closed_on_candidate_failure"] is not True:
        raise M5SmokeError("smoke_settings_invalid", "a failed microbatch-8 candidate must fail closed")
    if int(feasibility["accumulation_if_candidate_succeeds"]) != ACCUMULATION_MICROSTEPS:
        raise M5SmokeError("smoke_settings_invalid", "successful microbatch 8 uses accumulation 4")
    bf16 = phases["bf16_numerical_observation"]
    if bf16["pass_tolerance"] is not None:
        raise M5SmokeError("smoke_settings_invalid", "BF16 observation must not invent a pass tolerance")
    if bf16["same_fixed_latent_timestep_and_noise"] is not True:
        raise M5SmokeError("smoke_settings_invalid", "BF16 observation must use the FP32 latent, timestep, and noise")
    if bf16["selects_production_precision"] is not False:
        raise M5SmokeError("smoke_settings_invalid", "BF16 observation must not select production precision")
    if phases["fp32_observation"]["selects_production_precision"] is not False:
        raise M5SmokeError("smoke_settings_invalid", "FP32 observation must not select production precision")
    if phases["starting_ema_inspection"]["selects_ema_policy"] is not False:
        raise M5SmokeError("smoke_settings_invalid", "EMA inspection must not select the EMA policy")
    return smoke_settings_sha256(smoke_only)


def assert_unresolved(unresolved):
    if unresolved != EXPECTED_UNRESOLVED:
        raise M5SmokeError("d1_decision_unresolved", "unresolved D1 decisions drifted or were silently filled")
    for key in ("physical_microbatch", "gradient_accumulation", "production_precision", "ema_policy", "m6_seed", "m7_seeds"):
        if unresolved[key] is not None:
            raise M5SmokeError("d1_decision_unresolved", key + " is not unresolved")
    return True


def assert_inactive_configuration(config, contract_bytes, harness_bytes):
    """Validate the checked-in document. This does not authorise a run."""
    _require_mapping(config, "configuration_not_consumable", "configuration root must be a mapping")
    if config.get("document_status") != INACTIVE_DOCUMENT_STATUS:
        raise M5SmokeError("configuration_not_consumable", "inactive document_status drifted")
    if config.get("consumable_by_executable_workflow") is not False:
        raise M5SmokeError("configuration_not_consumable", "checked-in configuration must not be consumable")
    if config.get("schema_version") != SCHEMA_VERSION or config.get("experiment_id") != EXPERIMENT_ID:
        raise M5SmokeError("configuration_not_consumable", "schema or experiment identity drifted")
    if config.get("created_against_mres_commit") != BASE_MRES_COMMIT:
        raise M5SmokeError("configuration_not_consumable", "base MRes commit drifted")
    execution = _require_mapping(config.get("execution"), "configuration_not_consumable", "execution block is missing")
    if execution.get("authorised") is not False or execution.get("gpu_authorised_by_this_approval") is not False:
        raise M5SmokeError("configuration_not_consumable", "checked-in execution flags must stay closed")
    smoke_execution = _require_mapping(config.get("smoke_execution"), "configuration_not_consumable", "smoke execution block is missing")
    if smoke_execution.get("executable_now") is not False or smoke_execution.get("status") != INACTIVE_SMOKE_STATUS:
        raise M5SmokeError("configuration_not_consumable", "checked-in smoke execution must stay closed")
    assert_unresolved(config.get("unresolved_d1_decisions"))
    digest = assert_smoke_only(config.get("smoke_only"))
    _assert_model_block(config.get("model"))
    _assert_fixture_block(config.get("fixture"))
    _assert_denied_block(config.get("denied_inputs"))
    block = _require_mapping(config.get(AUTHORISATION_NAME), "authorisation_missing", "inactive authorisation block is missing")
    if set(block) != set(INACTIVE_AUTHORISATION_KEYS):
        raise M5SmokeError("authorisation_shape_invalid", "inactive authorisation fields drifted")
    for forbidden in ("physical_gpu", "gpu_uuid", "pci_bus"):
        if forbidden in block:
            raise M5SmokeError("physical_gpu_hardcoded", "inactive configuration contains a physical GPU field")
    if block["authorisation_active"] is not False or block["gpu_use_authorised"] is not False:
        raise M5SmokeError("authorisation_inactive", "checked-in authorisation must be inactive")
    if block["authorises_m5_synthetic_smoke"] is not False or block["activation_status"] != "inactive_no_authorisation":
        raise M5SmokeError("authorisation_inactive", "checked-in authorisation must not grant the smoke")
    if block["synthetic_only"] is not True:
        raise M5SmokeError("synthetic_scope_invalid", "synthetic-only declaration is not true")
    for key in ("train_access", "validation_access", "ref_access", "eval_access", "success_claimed", "m5_complete", "d1_training_authorised", "consumed"):
        if block[key] is not False:
            raise M5SmokeError("authorisation_overbroad", key + " must be false")
    for key in (
        "authorisation_id",
        "single_use_run_id",
        "authorization_parent_commit",
        "executing_implementation_commit",
        "implementation_config_sha256",
        "output_directory",
        "evidence_directory",
        "authorisation_timestamp",
        "scope",
    ):
        if block[key] is not None:
            raise M5SmokeError("authorisation_inactive", key + " must be null until a separate authorisation commit")
    if block["rnagenesis_commit"] != RNAGENESIS_HEAD or block["mres_branch"] != "main":
        raise M5SmokeError("authorisation_scope_invalid", "inactive pin is not the reviewed RNAGenesis commit on main")
    if block["fixture_relative_path"] != FIXTURE_RELATIVE or block["fixture_sha256"] != FIXTURE_SHA256:
        raise M5SmokeError("fixture_rejected", "inactive authorisation does not pin the tracked fixture")
    if block["allowed_smoke_settings_sha256"] != digest:
        raise M5SmokeError("smoke_settings_invalid", "allowed smoke-settings digest does not match the smoke block")
    if sha256_bytes(contract_bytes) != block["implementation_contract_sha256"]:
        raise M5SmokeError("provenance_mismatch", "contract hash does not match the inactive authorisation")
    if sha256_bytes(harness_bytes) != block["implementation_harness_sha256"]:
        raise M5SmokeError("provenance_mismatch", "harness hash does not match the inactive authorisation")
    if not _is_sha256(block["implementation_contract_sha256"]) or not _is_sha256(block["implementation_harness_sha256"]):
        raise M5SmokeError("authorisation_field_missing", "implementation file hashes are missing")
    return True


def _assert_model_block(model):
    model = _require_mapping(model, "asset_identity_mismatch", "model block is missing")
    expected = {
        "starting_diffusion": "B1_generic_released_rnagenesis",
        "starting_diffusion_relative": "configs/rnagenesis/diffusion",
        "prohibited_initialisation": "checkpoints/Aptamer/diffusion",
        "encdec_relative": "configs/rnagenesis/autoencoder",
        "identity_is_hash_not_directory_trust": True,
        "biomap_encoder_config_relative": BIOMAP_CONFIG_RELATIVE,
        "biomap_encoder_config_sha256": "bf7ef6843232f370f3f7fc37d608f85cb0ff0d75291eed35cef52213e34978f7",
        "biomap_encoder_config_bytes": 1369,
        "diffusers_normalization_patch_path": DIFFUSERS_PATCH_PATH,
        "diffusers_normalization_patch_sha256": DIFFUSERS_PATCH_SHA256,
        "diffusers_normalization_patch_bytes": DIFFUSERS_PATCH_SIZE,
        "pinned_python": PINNED_PYTHON,
        "accepted_runtime_versions": dict(ACCEPTED_RUNTIME_VERSIONS),
    }
    for key, value in expected.items():
        if model.get(key) != value:
            raise M5SmokeError("asset_identity_mismatch", "model identity field drifted: " + key)
    by_role = {role: digest for _path, digest, _size, role in REQUIRED_MODEL_FILES}
    if model.get("b1_unet_config_sha256") != by_role["b1_unet_config"]:
        raise M5SmokeError("asset_identity_mismatch", "B1 unet config hash drifted")
    if model.get("b1_unet_weight_sha256") != by_role["b1_unet_weights"]:
        raise M5SmokeError("asset_identity_mismatch", "B1 weight hash drifted")
    if model.get("b0_unet_config_sha256") != B0_UNET_CONFIG_SHA256 or model.get("b0_unet_weight_sha256") != B0_UNET_WEIGHT_SHA256:
        raise M5SmokeError("asset_identity_mismatch", "B0 distinguishing hashes drifted")
    return True


def _assert_fixture_block(fixture):
    fixture = _require_mapping(fixture, "fixture_rejected", "fixture block is missing")
    if fixture.get("relative_path") != FIXTURE_RELATIVE or fixture.get("basename") != FIXTURE_BASENAME:
        raise M5SmokeError("fixture_rejected", "fixture path is not the tracked synthetic fixture")
    if fixture.get("sha256") != FIXTURE_SHA256 or fixture.get("arbitrary_paths_denied") is not True:
        raise M5SmokeError("fixture_rejected", "fixture hash pin or path denial drifted")
    if fixture.get("synthetic_only") is not True or fixture.get("derived_from_biological_corpus") is not False:
        raise M5SmokeError("synthetic_scope_invalid", "fixture is not declared synthetic")
    if fixture.get("alphabet") != "ACGU":
        raise M5SmokeError("fixture_rejected", "fixture alphabet is not ACGU")
    return True


def _assert_denied_block(denied):
    denied = _require_mapping(denied, "denied_input", "denied-input block is missing")
    if set(denied.get("basenames") or []) != DENIED_BASENAMES:
        raise M5SmokeError("denied_input", "denied basenames drifted")
    if set(denied.get("path_components") or []) != DENIED_PATH_COMPONENTS:
        raise M5SmokeError("denied_input", "denied path components drifted")
    hashes = denied.get("hashes")
    if not isinstance(hashes, dict) or hashes != DENIED_HASHES:
        raise M5SmokeError("denied_input", "denied hashes drifted")
    return True


def assert_configuration_executable(config):
    if config.get("consumable_by_executable_workflow") is not True:
        raise M5SmokeError("configuration_not_consumable", "consumable_by_executable_workflow is not true")
    if config.get("document_status") != EXECUTABLE_DOCUMENT_STATUS:
        raise M5SmokeError("configuration_not_consumable", "document_status is not the synthetic execution status")
    execution = config.get("execution")
    if not isinstance(execution, dict) or execution.get("authorised") is not True or execution.get("gpu_authorised_by_this_approval") is not True:
        raise M5SmokeError("configuration_not_consumable", "execution flags are not authorised")
    smoke_execution = config.get("smoke_execution")
    if not isinstance(smoke_execution, dict) or smoke_execution.get("executable_now") is not True or smoke_execution.get("status") != ACTIVE_SMOKE_STATUS:
        raise M5SmokeError("configuration_not_consumable", "smoke execution is not authorised")
    assert_unresolved(config.get("unresolved_d1_decisions"))
    assert_smoke_only(config.get("smoke_only"))
    return True


def assert_active_authorisation(config, physical_gpu, output_directory):
    assert_configuration_executable(config)
    block = config.get(AUTHORISATION_NAME)
    if not isinstance(block, dict):
        raise M5SmokeError("authorisation_missing", "smoke authorisation is missing")
    if set(block) != set(ACTIVE_AUTHORISATION_KEYS):
        missing = [key for key in ACTIVE_AUTHORISATION_KEYS if key not in block]
        if missing:
            raise M5SmokeError("authorisation_field_missing", missing[0] + " is missing")
        raise M5SmokeError("authorisation_shape_invalid", "smoke authorisation has unexpected fields")
    if block["authorisation_active"] is not True or block["activation_status"] != ACTIVE_UNCONSUMED_STATUS or block["consumed"] is not False:
        raise M5SmokeError("authorisation_inactive", "smoke authorisation is not active and unconsumed")
    if block["gpu_use_authorised"] is not True or block["authorises_m5_synthetic_smoke"] is not True:
        raise M5SmokeError("authorisation_inactive", "smoke GPU use is not authorised")
    if type(physical_gpu) is not int or type(block["physical_gpu"]) is not int or block["physical_gpu"] != physical_gpu:
        raise M5SmokeError("gpu_binding_mismatch", "authorisation physical GPU does not match the argument")
    if physical_gpu < 0:
        raise M5SmokeError("physical_gpu_argument_invalid", "physical GPU index is invalid")
    if not isinstance(block["gpu_uuid"], str) or block["gpu_uuid"].strip() == "" or block["gpu_uuid"].upper() == "N/A":
        raise M5SmokeError("gpu_binding_mismatch", "authorisation GPU UUID is missing")
    if not isinstance(block["pci_bus"], str) or block["pci_bus"].strip() == "" or block["pci_bus"].upper() == "N/A":
        raise M5SmokeError("gpu_binding_mismatch", "authorisation PCI bus is missing")
    if not _is_sha40(block["authorization_parent_commit"]) or not _is_sha40(block["executing_implementation_commit"]):
        raise M5SmokeError("authorisation_commit_invalid", "authorisation commits must be lowercase SHA-1")
    if block["authorization_parent_commit"] != block["executing_implementation_commit"]:
        raise M5SmokeError("authorisation_commit_invalid", "parent commit and implementation commit differ")
    if block["mres_branch"] != "main" or block["rnagenesis_commit"] != RNAGENESIS_HEAD:
        raise M5SmokeError("authorisation_scope_invalid", "authorisation repository scope drifted")
    if not _is_sha256(block["implementation_contract_sha256"]) or not _is_sha256(block["implementation_harness_sha256"]):
        raise M5SmokeError("authorisation_field_missing", "implementation file hashes are missing")
    if not _is_sha256(block["implementation_config_sha256"]):
        raise M5SmokeError("authorisation_field_missing", "implementation config hash is missing")
    if block["fixture_relative_path"] != FIXTURE_RELATIVE or block["fixture_sha256"] != FIXTURE_SHA256:
        raise M5SmokeError("fixture_rejected", "authorisation fixture pin drifted")
    if block["output_directory"] != output_directory or block["evidence_directory"] != output_directory:
        raise M5SmokeError("authorisation_evidence_mismatch", "authorisation output directory does not match")
    if block["allowed_smoke_settings_sha256"] != smoke_settings_sha256(config["smoke_only"]):
        raise M5SmokeError("smoke_settings_invalid", "authorised smoke-settings digest does not match the smoke block")
    if not isinstance(block["authorisation_timestamp"], str) or block["authorisation_timestamp"].strip() == "":
        raise M5SmokeError("authorisation_field_missing", "authorisation timestamp is missing")
    if not isinstance(block["scope"], str) or "synthetic" not in block["scope"]:
        raise M5SmokeError("authorisation_field_missing", "authorisation scope is missing")
    if not isinstance(block["authorisation_id"], str) or block["authorisation_id"].strip() == "":
        raise M5SmokeError("authorisation_field_missing", "authorisation_id is missing")
    if not isinstance(block["single_use_run_id"], str) or block["single_use_run_id"].strip() == "":
        raise M5SmokeError("authorisation_field_missing", "single_use_run_id is missing")
    if block["synthetic_only"] is not True:
        raise M5SmokeError("synthetic_scope_invalid", "synthetic-only declaration is not true")
    for key in ("train_access", "validation_access", "ref_access", "eval_access", "success_claimed", "m5_complete", "d1_training_authorised"):
        if block[key] is not False:
            raise M5SmokeError("authorisation_overbroad", key + " must be false")
    return {key: block[key] for key in ACTIVE_AUTHORISATION_KEYS}


def differing_paths(left, right, prefix=""):
    if type(left) is not type(right):
        return [prefix or "<root>"]
    if isinstance(left, dict):
        paths = []
        for key in sorted(set(left) | set(right)):
            path = key if prefix == "" else prefix + "." + key
            if key not in left or key not in right:
                paths.append(path)
            else:
                paths.extend(differing_paths(left[key], right[key], path))
        return paths
    if isinstance(left, list):
        if left != right:
            return [prefix or "<root>"]
        return []
    if left != right:
        return [prefix or "<root>"]
    return []


def _path_is_permitted_activation(path):
    if path in PERMITTED_ACTIVATION_PATHS:
        return True
    return path == "smoke_execution_authorisation" or path.startswith("smoke_execution_authorisation.")


def assert_authorisation_delta(implementation_config, authorization_config):
    """The authorization commit may change only the activation fields."""
    paths = differing_paths(implementation_config, authorization_config)
    unexpected = [path for path in paths if not _path_is_permitted_activation(path)]
    if unexpected:
        raise M5SmokeError("authorisation_delta_invalid", "authorization commit changes " + unexpected[0])
    implementation_block = implementation_config.get(AUTHORISATION_NAME)
    authorization_block = authorization_config.get(AUTHORISATION_NAME)
    if not isinstance(implementation_block, dict) or not isinstance(authorization_block, dict):
        raise M5SmokeError("authorisation_delta_invalid", "authorisation blocks are missing")
    for key in PRESERVED_AUTHORISATION_FIELDS:
        if implementation_block.get(key) != authorization_block.get(key):
            raise M5SmokeError("authorisation_delta_invalid", "authorization commit changes " + key)
    return True


def parse_physical_gpu_argument(value):
    if type(value) is not str or not value.isdigit():
        raise M5SmokeError("physical_gpu_argument_invalid", "physical GPU must be an explicit decimal index")
    if len(value) > 1 and value.startswith("0"):
        raise M5SmokeError("physical_gpu_argument_invalid", "physical GPU must not have leading zeros")
    return int(value)


def _porcelain_lines(porcelain):
    if not isinstance(porcelain, str):
        raise M5SmokeError("git_status_unreadable", "git status porcelain could not be read")
    return [line for line in porcelain.splitlines() if line != ""]


def _split_porcelain(line):
    if len(line) < 4 or line[2] != " ":
        raise M5SmokeError("git_status_unreadable", "git status porcelain could not be read")
    return line[0], line[1], line[3:]


def _normalise_untracked_path(path):
    normalised = path.replace("\\", "/").strip()
    if normalised.startswith("./"):
        normalised = normalised[2:]
    if len(normalised) >= 2 and normalised[0] == '"' and normalised[-1] == '"':
        normalised = normalised[1:-1]
    return normalised


def reviewed_rnagenesis_porcelain():
    return "".join("?? {}\n".format(path) for path in KNOWN_RNAGENESIS_UNTRACKED)


def assert_mres_clean(porcelain):
    if _porcelain_lines(porcelain):
        raise M5SmokeError("provenance_mismatch", "MRes worktree or index is not clean")
    return True


def assert_rnagenesis_directory_fingerprint(porcelain):
    observed = []
    for line in _porcelain_lines(porcelain):
        index_status, worktree_status, path = _split_porcelain(line)
        if index_status == "?" and worktree_status == "?":
            observed.append(_normalise_untracked_path(path))
            continue
        if index_status not in (" ", "?"):
            raise M5SmokeError("provenance_mismatch", "RNAGenesis staged changes are present")
        raise M5SmokeError("provenance_mismatch", "RNAGenesis tracked changes are present")
    if sorted(observed) != sorted(KNOWN_RNAGENESIS_UNTRACKED):
        raise M5SmokeError("provenance_mismatch", "untracked path is not the known RNAGenesis asset fingerprint")
    return True


def _under_known_prefix(path):
    for prefix in KNOWN_RNAGENESIS_UNTRACKED:
        if path == prefix or path.startswith(prefix):
            return True
    return False


def assert_no_unexpected_untracked_source(file_porcelain):
    """Reject source and configuration files outside the reviewed classification.

    Files inside the known untracked directories may remain. A loose Python
    file, or a YAML file that is not one of the two reviewed configuration
    files, is refused. This does not treat every file under configs/ or
    checkpoints/ as model identity.
    """
    for line in _porcelain_lines(file_porcelain):
        index_status, worktree_status, raw_path = _split_porcelain(line)
        if index_status == "?" and worktree_status == "?":
            path = _normalise_untracked_path(raw_path)
        elif index_status not in (" ", "?"):
            raise M5SmokeError("provenance_mismatch", "RNAGenesis staged changes are present")
        else:
            raise M5SmokeError("provenance_mismatch", "RNAGenesis tracked changes are present")
        if not _under_known_prefix(path):
            raise M5SmokeError("unexpected_untracked_source", "untracked path is outside the reviewed fingerprint")
        suffix = Path(path).suffix.lower()
        if suffix in SOURCE_SUFFIXES and "__pycache__/" not in path:
            raise M5SmokeError("unexpected_untracked_source", "unexpected untracked source file")
        if suffix in CONFIG_SUFFIXES and path not in KNOWN_UNTRACKED_CONFIG_FILES:
            raise M5SmokeError("unexpected_untracked_source", "unexpected untracked configuration file")
    return True


def assert_regular_hashed_file(path, expected_size, expected_hash, lstat, sha256_file, role):
    """Require a regular, non-symlink file whose size and SHA-256 match the accepted manifest."""
    if expected_size is None or not isinstance(expected_size, int) or isinstance(expected_size, bool):
        raise M5SmokeError("asset_identity_mismatch", role + " has no accepted size")
    if not _is_sha256(expected_hash):
        raise M5SmokeError("asset_identity_mismatch", role + " has no accepted SHA-256")
    try:
        observed = lstat(path)
    except FileNotFoundError:
        raise M5SmokeError("asset_identity_mismatch", role + " is missing")
    if stat.S_ISLNK(observed.st_mode):
        raise M5SmokeError("asset_identity_mismatch", role + " is a symlink")
    if not stat.S_ISREG(observed.st_mode):
        raise M5SmokeError("asset_identity_mismatch", role + " is not a regular file")
    if int(observed.st_size) != int(expected_size):
        raise M5SmokeError("asset_identity_mismatch", role + " size drifted")
    digest = sha256_file(path)
    if role == "b1_unet_weights" and digest == B0_UNET_WEIGHT_SHA256:
        raise M5SmokeError("b0_substituted_for_b1", "B0 weights were supplied as the B1 denoiser")
    if role == "b1_unet_config" and digest == B0_UNET_CONFIG_SHA256:
        raise M5SmokeError("b0_substituted_for_b1", "B0 denoiser config was supplied as B1")
    if digest in PROHIBITED_SUBSTITUTE_SHA256:
        raise M5SmokeError("asset_identity_mismatch", "prohibited checkpoint substitute")
    if digest != expected_hash:
        raise M5SmokeError("asset_identity_mismatch", role + " hash drifted")
    return digest


def assert_pinned_python(path, lstat):
    """The worker executable is the pinned path. Its symlink target must be a regular file."""
    if path != PINNED_PYTHON:
        raise M5SmokeError("runtime_identity_mismatch", "python executable is not the pinned interpreter")
    try:
        observed = lstat(path)
    except FileNotFoundError:
        raise M5SmokeError("runtime_identity_mismatch", "pinned python executable is missing")
    target = path
    if stat.S_ISLNK(observed.st_mode):
        target = os.path.realpath(path)
        try:
            observed = os.lstat(target)
        except FileNotFoundError:
            raise M5SmokeError("runtime_identity_mismatch", "pinned python target is missing")
    if not stat.S_ISREG(observed.st_mode):
        raise M5SmokeError("runtime_identity_mismatch", "pinned python target is not a regular file")
    return {"pinned_path": PINNED_PYTHON, "resolved_path": target}


def assert_package_runtime(runtime):
    if not isinstance(runtime, dict):
        raise M5SmokeError("runtime_identity_mismatch", "package runtime is missing")
    if runtime.get("executable") != PINNED_PYTHON:
        raise M5SmokeError("runtime_identity_mismatch", "runtime executable is not the pinned interpreter")
    for key, expected in ACCEPTED_RUNTIME_VERSIONS.items():
        if runtime.get(key) != expected:
            raise M5SmokeError("runtime_identity_mismatch", key + " version is not the accepted M0 version")
    return True


def assert_model_assets(digests):
    """Require the accepted identities. Extra paths are not identity evidence."""
    if not isinstance(digests, dict):
        raise M5SmokeError("asset_identity_mismatch", "model digest map is missing")
    expected = {relative: (digest, role) for relative, digest, _size, role in REQUIRED_MODEL_FILES}
    if set(digests) != set(expected):
        raise M5SmokeError("asset_identity_mismatch", "model identity paths drifted")
    for relative, (digest, role) in expected.items():
        observed = digests[relative]
        if observed in PROHIBITED_SUBSTITUTE_SHA256:
            raise M5SmokeError("asset_identity_mismatch", "prohibited checkpoint substitute")
        if role == "b1_unet_weights" and observed == B0_UNET_WEIGHT_SHA256:
            raise M5SmokeError("b0_substituted_for_b1", "B0 weights were supplied as the B1 denoiser")
        if role == "b1_unet_config" and observed == B0_UNET_CONFIG_SHA256:
            raise M5SmokeError("b0_substituted_for_b1", "B0 denoiser config was supplied as B1")
        if observed != digest:
            raise M5SmokeError("asset_identity_mismatch", "model input hash drifted: " + relative)
        if role in B1_DISTINGUISHING_ROLES and observed in (B0_UNET_CONFIG_SHA256, B0_UNET_WEIGHT_SHA256):
            raise M5SmokeError("b0_substituted_for_b1", "B0 identity matched a distinguishing B1 file")
    return True


def required_model_paths():
    return tuple(RNAGENESIS_ROOT / relative for relative, _digest, _size, _role in REQUIRED_MODEL_FILES)


def path_denied(path, digest=None):
    parts = Path(str(path)).parts
    basename = Path(str(path)).name
    if basename in DENIED_BASENAMES or any(part in DENIED_PATH_COMPONENTS for part in parts):
        return True
    if digest is not None and digest in DENIED_HASHES:
        return True
    return False


def assert_not_denied_input(path, digest):
    if path_denied(path, digest):
        role = DENIED_HASHES.get(digest, Path(str(path)).name)
        raise M5SmokeError("denied_input", "refusing TRAIN, VALIDATION, REF, or EVAL input " + str(role))
    return True


def assert_fixture_file(path, expected_relative, expected_hash, read_bytes, lstat):
    if not isinstance(path, str):
        path = str(path)
    if os.path.isabs(expected_relative) or expected_relative != FIXTURE_RELATIVE:
        raise M5SmokeError("fixture_rejected", "fixture path is not the tracked synthetic fixture")
    try:
        observed = lstat(path)
    except FileNotFoundError:
        raise M5SmokeError("fixture_rejected", "fixture is missing")
    if stat.S_ISLNK(observed.st_mode):
        raise M5SmokeError("fixture_rejected", "fixture is a symlink")
    if not stat.S_ISREG(observed.st_mode):
        raise M5SmokeError("fixture_rejected", "fixture is not a regular file")
    if os.path.basename(path) != FIXTURE_BASENAME:
        raise M5SmokeError("fixture_rejected", "fixture basename drifted")
    payload = read_bytes(path)
    digest = sha256_bytes(payload)
    assert_not_denied_input(path, digest)
    if digest != expected_hash or expected_hash != FIXTURE_SHA256:
        raise M5SmokeError("fixture_rejected", "fixture hash drifted")
    text = payload.decode("utf-8")
    records = [line for line in text.split("\n") if line != ""]
    if not records or any(any(character not in "ACGU" for character in record) for record in records):
        raise M5SmokeError("fixture_rejected", "fixture is not synthetic A/C/G/U records")
    return digest


def validated_required_asset_paths():
    paths = [relative for relative, _digest, _size, _role in REQUIRED_MODEL_FILES]
    paths.append(DIFFUSERS_PATCH_PATH)
    return paths


def _repository_commit_record(commits):
    if not isinstance(commits, dict):
        raise M5SmokeError("denied_input", "repository commits are missing from the data-access guard")
    expected_keys = ("mres_implementation_commit", "mres_authorization_commit", "rnagenesis_commit")
    if set(commits) != set(expected_keys):
        raise M5SmokeError("denied_input", "repository commit record drifted")
    if any(not _is_sha40(commits[key]) for key in expected_keys):
        raise M5SmokeError("denied_input", "repository commits are not exact SHA-1 values")
    if commits["rnagenesis_commit"] != RNAGENESIS_HEAD:
        raise M5SmokeError("denied_input", "RNAGenesis commit is not the pinned worker commit")
    return {key: commits[key] for key in expected_keys}


def derive_data_access(audit, repository_commits):
    """State the closed-CLI guard. This is not an observed-open audit.

    TRAIN, VALIDATION, REF, and EVAL are unreachable through the authorised
    CLI and the pinned worker path. An assembled list of expected paths is
    not evidence that those paths were the only files opened.
    """
    if not isinstance(audit, dict):
        raise M5SmokeError("denied_input", "data-access guard is missing")
    if "opened_paths" in audit or audit.get("dynamic_file_open_audit_performed") is not False:
        raise M5SmokeError("denied_input", "an assembled path list is not an observed-open audit")
    if audit.get("cli_scientific_data_arguments") != []:
        raise M5SmokeError("denied_input", "the smoke CLI accepts no scientific data arguments")
    if audit.get("declared_scientific_data_inputs") != [FIXTURE_RELATIVE]:
        raise M5SmokeError("denied_input", "the only declared scientific input is the tracked synthetic fixture")
    assets = validated_required_asset_paths()
    if audit.get("validated_required_asset_paths") != assets:
        raise M5SmokeError("denied_input", "validated asset paths are not the hashed model and environment assets")
    for path in assets:
        if path_denied(path):
            raise M5SmokeError("denied_input", "a validated asset path is TRAIN, VALIDATION, REF, or EVAL")
    basis = audit.get("data_access_guard_basis")
    if not isinstance(basis, dict):
        raise M5SmokeError("denied_input", "data-access guard basis is missing")
    expected_basis_keys = (
        "closed_cli",
        "pinned_constant_fixture_path",
        "pinned_call_graph",
        "denied_role_names",
        "denied_role_hashes",
        "repository_commits",
    )
    if set(basis) != set(expected_basis_keys):
        raise M5SmokeError("denied_input", "data-access guard basis drifted")
    if basis.get("closed_cli") is not True or basis.get("pinned_call_graph") is not True:
        raise M5SmokeError("denied_input", "the data-access guard is not a closed CLI and pinned call graph")
    if basis.get("pinned_constant_fixture_path") != FIXTURE_RELATIVE:
        raise M5SmokeError("denied_input", "the pinned fixture path drifted")
    if basis.get("denied_role_names") != sorted(DENIED_BASENAMES):
        raise M5SmokeError("denied_input", "denied role names drifted")
    if basis.get("denied_role_hashes") != DENIED_HASHES:
        raise M5SmokeError("denied_input", "denied role hashes drifted")
    commits = _repository_commit_record(basis.get("repository_commits"))
    if commits != _repository_commit_record(repository_commits):
        raise M5SmokeError("denied_input", "data-access guard commits do not match the manifest commits")
    return {
        "declared_scientific_data_inputs": [FIXTURE_RELATIVE],
        "validated_required_asset_paths": list(assets),
        "cli_scientific_data_arguments": [],
        "data_access_guard_basis": {
            "closed_cli": True,
            "pinned_constant_fixture_path": FIXTURE_RELATIVE,
            "pinned_call_graph": True,
            "denied_role_names": sorted(DENIED_BASENAMES),
            "denied_role_hashes": dict(DENIED_HASHES),
            "repository_commits": commits,
        },
        "dynamic_file_open_audit_performed": False,
        "train_not_accessed": True,
        "validation_not_accessed": True,
        "ref_not_accessed": True,
        "eval_not_accessed": True,
        "conclusion": "TRAIN_VALIDATION_REF_EVAL_unreachable_through_authorized_cli_and_pinned_worker",
    }


def assert_output_isolated(path):
    """Authorised evidence must be a new direct child of the run root.

    Reject the root itself, anything outside it, a trailing slash, a
    symlinked parent, and a path that resolves into a git repository.
    Existence is checked separately so a missing child can still be created.
    """
    if not isinstance(path, str) or path == "" or not path.startswith("/"):
        raise M5SmokeError("output_directory_invalid", "output directory must be an absolute path")
    if path.endswith("/"):
        raise M5SmokeError("output_directory_invalid", "output directory must not have a trailing slash")
    if os.path.normpath(path) != path:
        raise M5SmokeError("output_directory_invalid", "output directory is not in canonical lexical form")
    run_root = os.path.normpath(str(RUN_ROOT))
    if path == run_root:
        raise M5SmokeError("output_directory_invalid", "the run root itself is not an evidence directory")
    parent = os.path.dirname(path)
    if os.path.islink(parent) or os.path.islink(run_root):
        raise M5SmokeError("output_directory_symlink", "refusing a symlinked evidence parent")
    if parent != run_root:
        raise M5SmokeError("output_directory_invalid", "evidence directory must be a direct child of the run root")
    name = os.path.basename(path)
    if name in ("", ".", ".."):
        raise M5SmokeError("output_directory_invalid", "evidence directory name is empty")
    try:
        real_parent = os.path.realpath(parent)
    except OSError:
        raise M5SmokeError("output_directory_invalid", "evidence parent could not be resolved")
    if os.path.normpath(real_parent) != parent:
        raise M5SmokeError("output_directory_symlink", "refusing a symlinked evidence parent")
    if not os.path.isdir(real_parent):
        raise M5SmokeError("output_directory_invalid", "run root is not a directory")
    resolved = os.path.realpath(path)
    if os.path.dirname(resolved) != real_parent:
        raise M5SmokeError("output_directory_symlink", "evidence path does not stay under the run root")
    for root in (str(MRES_ROOT), str(RNAGENESIS_ROOT)):
        root_resolved = os.path.realpath(root)
        if resolved == root_resolved or resolved.startswith(root_resolved + os.sep):
            raise M5SmokeError("output_directory_invalid", "output directory resolves inside a git repository")
    return resolved


def assert_output_directory_absent(path, lstat):
    assert_output_isolated(path)
    try:
        observed = lstat(path)
    except FileNotFoundError:
        return True
    if stat.S_ISLNK(observed.st_mode):
        raise M5SmokeError("output_directory_symlink", "refusing a symlinked evidence directory")
    raise M5SmokeError("output_directory_exists", "refusing to overwrite or resume an evidence directory")


def physical_gpu_query_argv(physical_gpu):
    if type(physical_gpu) is not int or physical_gpu < 0:
        raise M5SmokeError("physical_gpu_argument_invalid", "physical GPU index is invalid")
    return ["nvidia-smi", "--query-gpu=index,uuid,pci.bus_id,name", "--format=csv,noheader", "-i", str(physical_gpu)]


def parse_gpu_probe(text, physical_gpu):
    if not isinstance(text, str):
        raise M5SmokeError("gpu_probe_invalid", "GPU probe text is missing")
    lines = [line for line in text.splitlines() if line.strip() != ""]
    if len(lines) != 1:
        raise M5SmokeError("unauthorized_gpu", "GPU query did not return one device")
    parts = [part.strip() for part in lines[0].split(",")]
    if len(parts) != 4:
        raise M5SmokeError("gpu_probe_invalid", "GPU query was incomplete")
    index_text, uuid, pci_bus, model_name = parts
    if index_text != str(physical_gpu) or uuid in ("", "N/A") or pci_bus in ("", "N/A") or model_name == "":
        raise M5SmokeError("unauthorized_gpu", "GPU query identity is incomplete")
    return {
        "physical_index": physical_gpu,
        "uuid": uuid,
        "pci_bus": pci_bus,
        "model_name": model_name,
        "logical_device": LOGICAL_DEVICE,
    }


def assert_gpu_probe(probe, physical_gpu, authorisation):
    if not isinstance(probe, dict):
        raise M5SmokeError("gpu_probe_invalid", "GPU probe is missing")
    if probe.get("physical_index") != physical_gpu or probe.get("physical_index") != authorisation["physical_gpu"]:
        raise M5SmokeError("gpu_identity_mismatch", "probe physical GPU does not match the authorisation")
    if probe.get("uuid") != authorisation["gpu_uuid"] or probe.get("pci_bus") != authorisation["pci_bus"]:
        raise M5SmokeError("gpu_identity_mismatch", "probe UUID or PCI bus does not match the authorisation")
    if probe.get("logical_device") != LOGICAL_DEVICE:
        raise M5SmokeError("logical_device_rejected", "logical device must be cuda:0 after remapping")
    return True


def assert_inherited_cuda(parent, physical_gpu):
    if not isinstance(parent, dict):
        raise M5SmokeError("cuda_environment_invalid", "parent environment is missing")
    if "CUDA_VISIBLE_DEVICES" in parent:
        visible = parent["CUDA_VISIBLE_DEVICES"]
        if type(visible) is not str or visible != str(physical_gpu):
            raise M5SmokeError("conflicting_cuda_visible_devices", "inherited CUDA_VISIBLE_DEVICES conflicts with the authorisation")
    if "CUDA_DEVICE_ORDER" in parent and parent["CUDA_DEVICE_ORDER"] != CUDA_DEVICE_ORDER:
        raise M5SmokeError("conflicting_cuda_visible_devices", "inherited CUDA_DEVICE_ORDER is not PCI_BUS_ID")
    return True


def _path_within(path, root):
    path = os.path.normpath(path)
    root = os.path.normpath(root)
    return path == root or path.startswith(root + os.sep)


def runtime_isolation_paths(evidence_dir):
    evidence = os.path.abspath(os.path.normpath(str(evidence_dir)))
    cache_root = os.path.join(evidence, RUNTIME_CACHE_DIRECTORY_NAME)
    huggingface = os.path.join(cache_root, "huggingface")
    hub = os.path.join(huggingface, "hub")
    return {
        "PYTHONPYCACHEPREFIX": os.path.join(evidence, PYCACHE_DIRECTORY_NAME),
        "HF_HOME": huggingface,
        "HUGGINGFACE_HUB_CACHE": hub,
        "HF_HUB_CACHE": hub,
        "HF_ASSETS_CACHE": os.path.join(huggingface, "assets"),
        "HF_MODULES_CACHE": os.path.join(huggingface, "modules"),
        "TRANSFORMERS_CACHE": hub,
        "TORCH_HOME": os.path.join(cache_root, "torch"),
        "XDG_CACHE_HOME": cache_root,
    }


def assert_runtime_isolation(evidence_dir, realpath=None):
    if realpath is None:
        realpath = os.path.realpath
    evidence = os.path.abspath(os.path.normpath(str(evidence_dir)))
    resolved_evidence = realpath(evidence)
    resolved_rna = realpath(str(RNAGENESIS_ROOT))
    if _path_within(resolved_evidence, resolved_rna) or _path_within(resolved_evidence, realpath(str(MRES_ROOT))):
        raise M5SmokeError("runtime_cache_not_isolated", "evidence directory resolves inside a git repository")
    paths = runtime_isolation_paths(evidence)
    for path in paths.values():
        resolved = realpath(path)
        if not _path_within(resolved, resolved_evidence) or _path_within(resolved, resolved_rna):
            raise M5SmokeError("runtime_cache_not_isolated", "runtime cache escaped the evidence directory")
    return paths


def build_child_environment(parent, physical_gpu, evidence_dir, realpath=None):
    assert_inherited_cuda(parent, physical_gpu)
    original_items = list(parent.items())
    child = dict(parent.items())
    child["PYTHONDONTWRITEBYTECODE"] = "1"
    child.update(OFFLINE_CONTROLS)
    child["CUDA_VISIBLE_DEVICES"] = str(physical_gpu)
    child["CUDA_DEVICE_ORDER"] = CUDA_DEVICE_ORDER
    child.update(assert_runtime_isolation(evidence_dir, realpath))
    if list(parent.items()) != original_items:
        raise M5SmokeError("parent_environment_mutated", "parent environment was modified")
    if child["CUDA_VISIBLE_DEVICES"] != str(physical_gpu) or child["CUDA_DEVICE_ORDER"] != CUDA_DEVICE_ORDER:
        raise M5SmokeError("logical_device_rejected", "child CUDA selection drifted")
    if child["PYTHONDONTWRITEBYTECODE"] != "1":
        raise M5SmokeError("runtime_cache_not_isolated", "bytecode writing is not disabled")
    return child


def worker_argv(output_directory, physical_gpu, authorization_sha256):
    if not _is_sha256(authorization_sha256):
        raise M5SmokeError("authorisation_field_missing", "worker authorization digest is missing")
    if type(physical_gpu) is not int:
        raise M5SmokeError("physical_gpu_argument_invalid", "physical GPU index is invalid")
    return [
        PINNED_PYTHON,
        "-B",
        str(HARNESS_PATH),
        "--output-dir",
        output_directory,
        "--physical-gpu",
        str(physical_gpu),
        "--worker",
        "--authorization-sha256",
        authorization_sha256,
    ]


def assert_logical_device(observation, physical_gpu):
    if not isinstance(observation, dict):
        raise M5SmokeError("logical_device_rejected", "logical-device observation is missing")
    if observation.get("cuda_device_count") != 1:
        raise M5SmokeError("logical_device_rejected", "the worker must see exactly one CUDA device")
    if observation.get("device") != LOGICAL_DEVICE or observation.get("logical_index") != 0:
        raise M5SmokeError("logical_device_rejected", "the worker must use logical cuda:0")
    if observation.get("cuda_visible_devices") != str(physical_gpu):
        raise M5SmokeError("logical_device_rejected", "visible devices are not the authorised physical GPU")
    if observation.get("cpu_fallback") is not False or observation.get("other_gpu_fallback") is not False:
        raise M5SmokeError("logical_device_rejected", "CPU and other-GPU fallback are prohibited")
    return True


def assert_loss_finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise M5SmokeError("loss_not_finite", "loss is not a real number")
    if value != value or value == float("inf") or value == float("-inf"):
        raise M5SmokeError("loss_not_finite", "loss is not finite")
    return True


def assert_gradient_summaries(rows):
    if not isinstance(rows, list) or not rows:
        raise M5SmokeError("gradient_missing", "no gradient summary was recorded")
    trainable = [row for row in rows if row.get("trainable") is True]
    if not trainable:
        raise M5SmokeError("gradient_missing", "no trainable gradient was recorded")
    if any(row.get("finite") is not True for row in trainable):
        raise M5SmokeError("gradient_not_finite", "a trainable gradient is not finite")
    if not any(row.get("nonzero") is True for row in trainable):
        raise M5SmokeError("gradient_all_zero", "every trainable gradient is zero")
    if any(row.get("has_gradient") is True for row in rows if row.get("encdec") is True):
        raise M5SmokeError("frozen_component_failed", "an EncDec parameter has a gradient")
    return True


def assert_frozen_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        raise M5SmokeError("frozen_component_failed", "frozen snapshot is missing")
    components = snapshot.get("sentinel_components")
    if not isinstance(components, dict) or any(name not in components for name in FROZEN_SENTINEL_COMPONENTS):
        raise M5SmokeError("frozen_component_failed", "a frozen sentinel component is missing")
    flags = (
        "eval_mode",
        "requires_grad_all_false",
        "optimizer_membership_empty",
        "parameter_gradients_absent",
        "versions_unchanged",
        "sentinels_bit_identical",
        "rotary_warmup_completed",
        "rotary_caches_excluded_from_sentinels",
    )
    for flag in flags:
        if snapshot.get(flag) is not True:
            raise M5SmokeError("frozen_component_failed", flag + " failed")
    if snapshot.get("baseline_taken_after_warmup") is not True:
        raise M5SmokeError("frozen_component_failed", "frozen baseline was not taken after rotary warm-up")
    return True


def _integer_ids(value, detail):
    if not isinstance(value, list) or not value or any(type(item) is not int for item in value):
        raise M5SmokeError("frozen_component_failed", detail)
    return value


def assert_optimizer_membership_evidence(evidence):
    """Recompute EncDec exclusion from the two AdamW parameter-identity sets.

    A later replacement optimizer, including a disjoint SGD, is not evidence.
    """
    if not isinstance(evidence, dict):
        raise M5SmokeError("frozen_component_failed", "optimizer membership evidence is missing")
    if evidence.get("evidence_basis") != OPTIMIZER_MEMBERSHIP_EVIDENCE_BASIS:
        raise M5SmokeError("frozen_component_failed", "optimizer membership evidence is not the live AdamW parameter identities")
    if evidence.get("replacement_optimizer_used") is not False:
        raise M5SmokeError("frozen_component_failed", "a replacement optimizer is not membership evidence")
    rows = evidence.get("optimizers")
    if not isinstance(rows, list) or len(rows) != 2:
        raise M5SmokeError("frozen_component_failed", "membership evidence must record both live AdamW optimizers")
    names = [row.get("name") if isinstance(row, dict) else None for row in rows]
    if names != ["proof_optimizer", "restored_optimizer"]:
        raise M5SmokeError("frozen_component_failed", "membership evidence must name the proof and restored AdamW optimizers")
    encdec_ids = _integer_ids(evidence.get("encdec_parameter_ids"), "EncDec parameter identities are missing")
    encdec_set = set(encdec_ids)
    all_disjoint = True
    for row in rows:
        if row.get("optimizer_class") != "AdamW":
            raise M5SmokeError("frozen_component_failed", "a fabricated replacement optimizer is not membership evidence")
        parameter_ids = _integer_ids(row.get("parameter_ids"), "AdamW parameter identities are missing")
        disjoint = set(parameter_ids).isdisjoint(encdec_set)
        if row.get("disjoint_from_encdec") is not disjoint:
            raise M5SmokeError("frozen_component_failed", "optimizer membership flag does not match the parameter identities")
        if disjoint is not True:
            all_disjoint = False
    if evidence.get("both_disjoint_from_every_encdec_parameter") is not all_disjoint:
        raise M5SmokeError("frozen_component_failed", "combined membership flag does not match the parameter identities")
    if all_disjoint is not True:
        raise M5SmokeError("frozen_component_failed", "an AdamW optimizer contains an EncDec parameter")
    return True


def assert_post_generation_frozen_snapshot(snapshot):
    """Accept the carried AdamW identity observation, not a replacement optimizer."""
    assert_frozen_snapshot(snapshot)
    evidence = snapshot.get("optimizer_membership_evidence")
    assert_optimizer_membership_evidence(evidence)
    if snapshot.get("optimizer_membership_evidence_basis") != OPTIMIZER_MEMBERSHIP_EVIDENCE_BASIS:
        raise M5SmokeError("frozen_component_failed", "post-generation membership basis is not the live AdamW parameter identities")
    if snapshot.get("optimizer_membership_empty") is not evidence.get("both_disjoint_from_every_encdec_parameter"):
        raise M5SmokeError("frozen_component_failed", "post-generation membership flag was not carried from the live AdamW observation")
    return True


def assert_denoiser_update(proof):
    if not isinstance(proof, dict):
        raise M5SmokeError("denoiser_not_updated", "denoiser update proof is missing")
    for key in ("parameter_name", "indices", "before_digest", "after_digest", "max_abs_delta"):
        if key not in proof:
            raise M5SmokeError("denoiser_not_updated", key + " is missing")
    if proof.get("used_version_as_sole_proof") is True:
        raise M5SmokeError("denoiser_not_updated", "parameter version is not sufficient evidence of an update")
    if not isinstance(proof["indices"], list) or not proof["indices"]:
        raise M5SmokeError("denoiser_not_updated", "update slice is missing")
    delta = proof["max_abs_delta"]
    if isinstance(delta, bool) or not isinstance(delta, (int, float)) or not delta > 0:
        raise M5SmokeError("denoiser_not_updated", "update slice delta is not a positive finite number")
    if proof["before_digest"] == proof["after_digest"] or not _is_sha256(proof["before_digest"]) or not _is_sha256(proof["after_digest"]):
        raise M5SmokeError("denoiser_not_updated", "update slice digest did not change")
    if proof.get("passed") is not True:
        raise M5SmokeError("denoiser_not_updated", "update assertion did not pass")
    return True


def assert_checkpoint_members(saved_hashes):
    if not isinstance(saved_hashes, dict) or not saved_hashes:
        raise M5SmokeError("checkpoint_reload_mismatch", "checkpoint inventory is missing")
    missing = [name for name in CHECKPOINT_JSON_MEMBERS if name not in saved_hashes]
    if missing:
        raise M5SmokeError("checkpoint_reload_mismatch", "checkpoint inventory is missing " + missing[0])
    weights = [name for name in CHECKPOINT_WEIGHT_MEMBERS if name in saved_hashes]
    if len(weights) != 1:
        raise M5SmokeError("checkpoint_reload_mismatch", "checkpoint inventory must contain exactly one weight file")
    expected = set(CHECKPOINT_JSON_MEMBERS) | set(weights)
    if set(saved_hashes) != expected:
        raise M5SmokeError("checkpoint_reload_mismatch", "checkpoint inventory does not match the expected Diffusers members")
    for digest in saved_hashes.values():
        if not _is_sha256(digest):
            raise M5SmokeError("checkpoint_reload_mismatch", "checkpoint inventory digest is invalid")
    return True


def assert_checkpoint_reload(proof):
    """A directory listing compared with itself is not evidence that weights reloaded."""
    if not isinstance(proof, dict):
        raise M5SmokeError("checkpoint_reload_mismatch", "checkpoint reload proof is missing")
    saved = proof.get("saved_file_hashes")
    assert_checkpoint_members(saved)
    if proof.get("fresh_load_succeeded") is not True:
        raise M5SmokeError("checkpoint_reload_mismatch", "fresh checkpoint load did not succeed")
    original_id = proof.get("original_denoiser_id")
    reloaded_id = proof.get("reloaded_denoiser_id")
    if type(original_id) is not int or type(reloaded_id) is not int or original_id == reloaded_id:
        raise M5SmokeError("checkpoint_reload_mismatch", "reloaded denoiser is not a fresh object")
    comparisons = proof.get("tensor_digest_comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        raise M5SmokeError("checkpoint_reload_mismatch", "original-versus-reloaded tensor digests are missing")
    for row in comparisons:
        if not isinstance(row, dict) or not row.get("name"):
            raise M5SmokeError("checkpoint_reload_mismatch", "tensor digest comparison is incomplete")
        if not _is_sha256(row.get("saved", "")) or row.get("saved") != row.get("reloaded") or row.get("match") is not True:
            raise M5SmokeError("checkpoint_reload_mismatch", "a reloaded tensor digest does not match the saved tensor")
    if proof.get("configuration_compatible") is not True:
        raise M5SmokeError("checkpoint_reload_mismatch", "reloaded configuration is not compatible")
    if not _is_sha256(proof.get("original_config_sha256", "")) or proof.get("original_config_sha256") != proof.get("reloaded_config_sha256"):
        raise M5SmokeError("checkpoint_reload_mismatch", "reloaded configuration digest does not match")
    if proof.get("generation_uses_reloaded_object") is True or proof.get("generation_object_id") == reloaded_id:
        raise M5SmokeError("checkpoint_reload_mismatch", "the training reload is not the generation checkpoint")
    return True


def _rng_block_restored(block):
    if not isinstance(block, dict):
        return False
    if block.get("setstate_called") is not True or block.get("disturbed_before_restore") is not True:
        return False
    if block.get("final_reset_after_verification") is not True:
        return False
    before = block.get("digest_before")
    after = block.get("digest_after")
    return _is_sha256(before) and before == after


def assert_resume_proof(proof):
    if not isinstance(proof, dict):
        raise M5SmokeError("resume_proof_failed", "resume proof is missing")
    if proof.get("weight_only_reload_counted_as_resume") is not False:
        raise M5SmokeError("resume_proof_failed", "weight-only reload is not training resume")
    original_id = proof.get("original_denoiser_id")
    reloaded_id = proof.get("reloaded_denoiser_id")
    if type(original_id) is not int or type(reloaded_id) is not int or original_id == reloaded_id:
        raise M5SmokeError("resume_proof_failed", "resume did not use a fresh denoiser")
    if proof.get("fresh_object_identity") is not True:
        raise M5SmokeError("resume_proof_failed", "fresh object identity was not established")
    comparisons = proof.get("weight_digest_comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        raise M5SmokeError("resume_proof_failed", "saved-versus-reloaded weight digests are missing")
    for row in comparisons:
        if not isinstance(row, dict) or not _is_sha256(row.get("saved", "")) or row.get("saved") != row.get("reloaded") or row.get("match") is not True:
            raise M5SmokeError("resume_proof_failed", "a reloaded weight digest does not match")
    optimizer_ids = proof.get("optimizer_parameter_ids")
    reloaded_parameter_ids = proof.get("reloaded_parameter_ids")
    original_parameter_ids = proof.get("original_parameter_ids")
    if not isinstance(optimizer_ids, list) or not optimizer_ids or any(type(value) is not int for value in optimizer_ids):
        raise M5SmokeError("resume_proof_failed", "optimizer parameter identity is missing")
    if not isinstance(reloaded_parameter_ids, list) or not isinstance(original_parameter_ids, list):
        raise M5SmokeError("resume_proof_failed", "denoiser parameter identities are missing")
    if set(optimizer_ids).isdisjoint(reloaded_parameter_ids) or not set(optimizer_ids).isdisjoint(original_parameter_ids):
        raise M5SmokeError("resume_proof_failed", "optimizer state is not bound to the fresh denoiser")
    if proof.get("optimizer_bound_to_reloaded_denoiser") is not True:
        raise M5SmokeError("resume_proof_failed", "optimizer binding flag does not match the parameter identities")
    moment_count = proof.get("optimizer_moment_count")
    if type(moment_count) is not int or moment_count < 1 or proof.get("optimizer_moments_present") is not True:
        raise M5SmokeError("resume_proof_failed", "optimizer moments are not present")
    saved_epoch = proof.get("scheduler_last_epoch_saved")
    restored_epoch = proof.get("scheduler_last_epoch_restored")
    if type(saved_epoch) is not int or saved_epoch != restored_epoch or proof.get("scheduler_position_restored") is not True:
        raise M5SmokeError("resume_proof_failed", "scheduler position was not restored")
    saved_lr = proof.get("learning_rate_saved")
    restored_lr = proof.get("learning_rate_restored_value")
    if isinstance(saved_lr, bool) or not isinstance(saved_lr, (int, float)) or saved_lr != restored_lr or proof.get("learning_rate_restored") is not True:
        raise M5SmokeError("resume_proof_failed", "learning rate was not restored")
    saved_step = proof.get("global_step_saved")
    reread_step = proof.get("global_step_reread")
    restored_step = proof.get("global_step_after_restore")
    if type(saved_step) is not int or saved_step < 1 or saved_step != reread_step or saved_step != restored_step:
        raise M5SmokeError("resume_proof_failed", "global step was not restored from the reread sidecar")
    if proof.get("next_update_index") != saved_step + 1 or proof.get("restored_global_step_is_next_step") is not True:
        raise M5SmokeError("resume_proof_failed", "restored global step is not the next update index")
    if not _rng_block_restored(proof.get("python_rng")) or proof.get("python_rng", {}).get("restored_with") != "random.setstate":
        raise M5SmokeError("resume_proof_failed", "Python RNG was not restored with random.setstate and reset after verification")
    if not _rng_block_restored(proof.get("torch_cpu_rng")) or proof.get("torch_cpu_rng", {}).get("restored_with") != "torch.set_rng_state":
        raise M5SmokeError("resume_proof_failed", "torch CPU RNG was not restored and reset after verification")
    if not _rng_block_restored(proof.get("torch_cuda_rng")) or proof.get("torch_cuda_rng", {}).get("restored_with") != "torch.cuda.set_rng_state":
        raise M5SmokeError("resume_proof_failed", "torch CUDA RNG was not restored and reset after verification")
    if not _rng_block_restored(proof.get("diffusion_generator")) or proof.get("diffusion_generator", {}).get("restored_with") != "generator.set_state":
        raise M5SmokeError("resume_proof_failed", "diffusion generator state was not restored and reset after verification")
    numpy_rng = proof.get("numpy_rng")
    if not isinstance(numpy_rng, dict) or numpy_rng.get("randomness_used") is not False or numpy_rng.get("status") != "not_applicable":
        raise M5SmokeError("resume_proof_failed", "NumPy RNG must be restored or recorded as not applicable")
    if proof.get("rng_restored") is not True:
        raise M5SmokeError("resume_proof_failed", "RNG restoration flag does not match the observations")
    subsequent_loss = proof.get("subsequent_loss")
    try:
        assert_loss_finite(subsequent_loss)
    except M5SmokeError:
        raise M5SmokeError("resume_proof_failed", "post-resume loss is not finite")
    if proof.get("subsequent_gradients_finite") is not True:
        raise M5SmokeError("resume_proof_failed", "post-resume gradients are not finite")
    delta = proof.get("subsequent_update_max_abs_delta")
    if isinstance(delta, bool) or not isinstance(delta, (int, float)) or not delta > 0:
        raise M5SmokeError("resume_proof_failed", "post-resume update did not change a fresh-denoiser parameter")
    if proof.get("subsequent_parameter_name") in (None, "") or proof.get("subsequent_update_succeeded") is not True:
        raise M5SmokeError("resume_proof_failed", "post-resume update was not observed")
    if proof.get("weights_reloaded") is not True or proof.get("resumed_checkpoint_generation_compatible") is not True:
        raise M5SmokeError("resume_proof_failed", "resume did not keep the reloaded checkpoint")
    generation_id = proof.get("generation_object_id")
    if type(generation_id) is not int or generation_id == reloaded_id or generation_id == original_id:
        raise M5SmokeError("resume_proof_failed", "generation used the mutated resumed or overfit object")
    if proof.get("generation_used_mutated_training_object") is not False:
        raise M5SmokeError("resume_proof_failed", "generation used the mutated resumed or overfit object")
    observed_keys = proof.get("observed_sidecar_keys")
    if not isinstance(observed_keys, list) or proof.get("sidecar_fields") != observed_keys:
        raise M5SmokeError("resume_proof_failed", "sidecar keys are not the keys reread from the sidecar")
    if proof.get("sidecar_fields_source") != "reread_sidecar_keys":
        raise M5SmokeError("resume_proof_failed", "sidecar keys were not taken from the reread sidecar")
    for field in RESUME_STATE_FIELDS:
        if field not in observed_keys:
            raise M5SmokeError("resume_proof_failed", "resume sidecar is missing " + field)
    return True


def assert_overfit(losses, rule, tolerance, expected_updates):
    if rule != "final_loss_strictly_less_than_initial_loss":
        raise M5SmokeError("overfit_failed", "overfit pass rule is not the configured rule")
    expected_length = int(expected_updates) + 1
    if not isinstance(losses, list) or len(losses) != expected_length or int(expected_updates) < 2:
        raise M5SmokeError("overfit_failed", "overfit trajectory must contain the initial loss and one loss after every update")
    for value in losses:
        assert_loss_finite(value)
    minimum_decrease = float(tolerance)
    if not (losses[0] - losses[-1]) > minimum_decrease:
        raise M5SmokeError("overfit_failed", "loss after the final update is not lower than the initial loss")
    return True


def _nonnegative_int(value, code, detail):
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise M5SmokeError(code, detail)
    return value


def assert_physical_microbatch_candidate(attempt):
    """Accept only a successful attempt at microbatch 8. Any other attempt fails closed."""
    if not isinstance(attempt, dict):
        raise M5SmokeError("physical_microbatch_candidate_failed", "physical-microbatch attempt is missing")
    if attempt.get("candidate_microbatch") != PHYSICAL_MICROBATCH_CANDIDATE:
        raise M5SmokeError("physical_microbatch_candidate_failed", "the only feasibility candidate is microbatch 8")
    if attempt.get("attempted_microbatches") != [PHYSICAL_MICROBATCH_CANDIDATE]:
        raise M5SmokeError("physical_microbatch_candidate_failed", "microbatch feasibility must not fall back or sweep")
    if attempt.get("fallback_attempted") is not False or attempt.get("sweep") is not False:
        raise M5SmokeError("physical_microbatch_candidate_failed", "microbatch feasibility must not fall back or sweep")
    if attempt.get("succeeded") is not True:
        raise M5SmokeError("physical_microbatch_candidate_failed", "microbatch 8 failed; evidence is preserved and 16 or 32 is not attempted")
    if attempt.get("measured_physical_microbatch") != PHYSICAL_MICROBATCH_CANDIDATE:
        raise M5SmokeError("physical_microbatch_candidate_failed", "measured physical microbatch is not 8")
    if attempt.get("derived_accumulation") != ACCUMULATION_MICROSTEPS:
        raise M5SmokeError("physical_microbatch_candidate_failed", "microbatch 8 did not use accumulation 4")
    return PHYSICAL_MICROBATCH_CANDIDATE


def assert_accumulation_exercise(proof):
    if not isinstance(proof, dict):
        raise M5SmokeError("microbatch_mismatch", "accumulation exercise is missing")
    if proof.get("backward_microsteps") != ACCUMULATION_MICROSTEPS:
        raise M5SmokeError("microbatch_mismatch", "accumulation did not execute four backward microsteps")
    if proof.get("optimizer_updates_in_window") != 1:
        raise M5SmokeError("microbatch_mismatch", "accumulation window did not end in one optimizer update")
    if proof.get("loss_scale") != LOSS_SCALE_NAME:
        raise M5SmokeError("microbatch_mismatch", "accumulation loss was not divided by the accumulation count")
    if proof.get("deterministic_record_reuse") is not True or proof.get("reused_records") != PHYSICAL_MICROBATCH_CANDIDATE:
        raise M5SmokeError("microbatch_mismatch", "accumulation did not record deterministic reuse of the eight synthetic records")
    if proof.get("effective_batch") != INTENDED_EFFECTIVE_BATCH:
        raise M5SmokeError("microbatch_mismatch", "accumulation effective batch is not 32")
    if proof.get("adamw_moments_allocated_before_training_memory_measurement") is not True:
        raise M5SmokeError("microbatch_mismatch", "AdamW moments were not allocated before the training-memory measurement")
    return True


def assert_bf16_observation(observation):
    """Record the paired numerical comparison. Do not select precision or apply a tolerance."""
    if not isinstance(observation, dict) or observation.get("status") != "observed":
        raise M5SmokeError("m5_completion_not_established", "BF16 observation was not collected")
    if observation.get("selects_production_precision") is not False or observation.get("production_precision_selected") is not None:
        raise M5SmokeError("m5_completion_not_established", "BF16 observation must not select production precision")
    if observation.get("pass_tolerance") is not None:
        raise M5SmokeError("m5_completion_not_established", "BF16 observation must not invent a pass tolerance")
    if observation.get("same_fixed_latent") is not True or observation.get("same_fixed_timestep") is not True or observation.get("same_fixed_noise") is not True:
        raise M5SmokeError("m5_completion_not_established", "BF16 observation did not use the FP32 latent, timestep, and noise")
    if type(observation.get("autocast_supported")) is not bool:
        raise M5SmokeError("m5_completion_not_established", "BF16 autocast support was not recorded")
    assert_loss_finite(observation.get("fp32_loss"))
    supported = observation["autocast_supported"]
    finite = observation.get("result_finite")
    if supported is False:
        if finite is not None or observation.get("bf16_loss") is not None:
            raise M5SmokeError("m5_completion_not_established", "unsupported BF16 autocast must not invent a BF16 loss")
        if observation.get("absolute_difference") is not None or observation.get("relative_difference") is not None:
            raise M5SmokeError("m5_completion_not_established", "unsupported BF16 autocast has no numeric difference")
    elif finite is True:
        assert_loss_finite(observation.get("bf16_loss"))
        absolute = observation.get("absolute_difference")
        if isinstance(absolute, bool) or not isinstance(absolute, (int, float)) or absolute < 0:
            raise M5SmokeError("m5_completion_not_established", "BF16 absolute difference was not recorded")
        if float(observation["fp32_loss"]) == 0:
            if observation.get("relative_difference") is not None:
                raise M5SmokeError("m5_completion_not_established", "relative difference is undefined for a zero FP32 loss")
        else:
            relative = observation.get("relative_difference")
            if isinstance(relative, bool) or not isinstance(relative, (int, float)) or relative < 0:
                raise M5SmokeError("m5_completion_not_established", "BF16 relative difference was not recorded")
    elif finite is False:
        if observation.get("absolute_difference") is not None or observation.get("relative_difference") is not None:
            raise M5SmokeError("m5_completion_not_established", "a non-finite BF16 result has no numeric difference")
    else:
        raise M5SmokeError("m5_completion_not_established", "BF16 finiteness was not recorded")
    memory = observation.get("memory_observation")
    if memory is not None:
        if not isinstance(memory, dict):
            raise M5SmokeError("m5_completion_not_established", "BF16 memory observation is not a record")
        for key in ("allocated_bytes", "reserved_bytes"):
            if key in memory and memory[key] is not None:
                _nonnegative_int(memory[key], "m5_completion_not_established", "BF16 memory observation is not a byte count")
    return True


def assert_memory_peak_accounting(report):
    training_allocated = _nonnegative_int(report.get("peak_training_allocated_bytes"), "memory_peak_accounting_invalid", "training allocated peak is missing")
    training_reserved = _nonnegative_int(report.get("peak_training_reserved_bytes"), "memory_peak_accounting_invalid", "training reserved peak is missing")
    overall_allocated = _nonnegative_int(report.get("peak_allocated_bytes"), "memory_peak_accounting_invalid", "overall allocated peak is missing")
    overall_reserved = _nonnegative_int(report.get("peak_reserved_bytes"), "memory_peak_accounting_invalid", "overall reserved peak is missing")
    if overall_allocated < training_allocated or overall_reserved < training_reserved:
        raise M5SmokeError("memory_peak_accounting_invalid", "overall peak is below the training peak")
    accounting = report.get("memory_peak_accounting")
    if not isinstance(accounting, dict):
        raise M5SmokeError("memory_peak_accounting_invalid", "memory peak accounting is missing")
    for key in (
        "adamw_moments_allocated_before_training_measurement",
        "training_peak_captured_before_checkpoint_reload_resume_generation",
        "overall_peak_includes_checkpoint_reload_resume_generation",
    ):
        if accounting.get(key) is not True:
            raise M5SmokeError("memory_peak_accounting_invalid", key + " is not established")
    if accounting.get("training_allocated_bytes") != training_allocated or accounting.get("training_reserved_bytes") != training_reserved:
        raise M5SmokeError("memory_peak_accounting_invalid", "training peak accounting does not match the manifest peaks")
    if accounting.get("overall_allocated_bytes") != overall_allocated or accounting.get("overall_reserved_bytes") != overall_reserved:
        raise M5SmokeError("memory_peak_accounting_invalid", "overall peak accounting does not match the manifest peaks")
    return True


def derive_training_release(referents):
    """Build the release record from observed weak-reference death. Ids are not consulted."""
    if not isinstance(referents, list):
        raise M5SmokeError("generation_proof_failed", "training release referents are missing")
    labels = [row.get("label") if isinstance(row, dict) else None for row in referents]
    if labels != list(TRAINING_RELEASE_LABELS):
        raise M5SmokeError("generation_proof_failed", "training release did not observe the required weak references")
    dead_labels = []
    live_labels = []
    normalized = []
    for row in referents:
        if row.get("dead") is True:
            dead_labels.append(row["label"])
            normalized.append({"label": row["label"], "dead": True})
        elif row.get("dead") is False:
            live_labels.append(row["label"])
            normalized.append({"label": row["label"], "dead": False})
        else:
            raise M5SmokeError("generation_proof_failed", "training release did not record whether a weak reference was dead")
    return {
        "basis": TRAINING_RELEASE_BASIS,
        "python_object_id_is_release_proof": False,
        "referents": normalized,
        "released_training_object_names": dead_labels,
        "live_training_object_names": live_labels,
        "training_objects_released_before_generation_reload": not live_labels,
    }


def assert_training_release_observation(observation):
    if not isinstance(observation, dict):
        raise M5SmokeError("generation_proof_failed", "training release was not observed from weak references")
    if observation.get("basis") != TRAINING_RELEASE_BASIS:
        raise M5SmokeError("generation_proof_failed", "training release basis is not weak-reference death")
    if observation.get("python_object_id_is_release_proof") is not False:
        raise M5SmokeError("generation_proof_failed", "Python object ids are not the training-release proof")
    derived = derive_training_release(observation.get("referents"))
    if observation.get("released_training_object_names") != derived["released_training_object_names"]:
        raise M5SmokeError("generation_proof_failed", "released training object names are not the weak references observed dead")
    if observation.get("live_training_object_names") != derived["live_training_object_names"]:
        raise M5SmokeError("generation_proof_failed", "live training object names are not the weak references still alive")
    if observation.get("training_objects_released_before_generation_reload") is not derived["training_objects_released_before_generation_reload"]:
        raise M5SmokeError("generation_proof_failed", "training-release flag was not derived from the weak-reference observation")
    if derived["training_objects_released_before_generation_reload"] is not True:
        raise M5SmokeError("generation_proof_failed", "training objects were not released before the generation reload")
    return derived


def assert_immutable_generation(proof, generation_count, checkpoint_inventory):
    if not isinstance(proof, dict) or proof.get("reloaded") is not True:
        raise M5SmokeError("generation_proof_failed", "generation checkpoint did not reload")
    if proof.get("count") != int(generation_count) or proof.get("loader") != "GuidedDDIMPipeline1D.from_pretrained":
        raise M5SmokeError("generation_proof_failed", "generation count or loader drifted")
    if proof.get("imported_generation_py") is not False:
        raise M5SmokeError("generation_proof_failed", "generation.py must not be imported")
    if not _is_sha256(proof.get("output_sha256", "")):
        raise M5SmokeError("generation_proof_failed", "generation output hash is missing")
    if proof.get("generation_checkpoint") != "original_one_update_smoke_checkpoint":
        raise M5SmokeError("generation_proof_failed", "generation did not name the original one-update smoke checkpoint")
    path = proof.get("selected_checkpoint_path")
    if not isinstance(path, str) or path == "" or not path.endswith("/smoke_generation_checkpoint"):
        raise M5SmokeError("generation_proof_failed", "selected checkpoint path is missing")
    inventory = proof.get("selected_checkpoint_inventory")
    assert_checkpoint_members(inventory)
    if proof.get("selected_checkpoint_hash_set") != inventory:
        raise M5SmokeError("generation_proof_failed", "selected checkpoint hash set does not match the inventory")
    if checkpoint_inventory != inventory:
        raise M5SmokeError("generation_proof_failed", "selected checkpoint hashes do not match the recorded inventory")
    if proof.get("on_disk_hashes_recorded_before_generation") is not True:
        raise M5SmokeError("generation_proof_failed", "checkpoint hashes were not recorded before generation")
    if proof.get("on_disk_hashes_at_generation_reload") != inventory:
        raise M5SmokeError("generation_proof_failed", "on-disk checkpoint hashes changed before generation reload")
    rows = proof.get("pre_generation_reloaded_tensor_digests")
    if not isinstance(rows, list) or not rows:
        raise M5SmokeError("generation_proof_failed", "pre-generation reloaded tensor digests are missing")
    for row in rows:
        if not isinstance(row, dict) or not row.get("name"):
            raise M5SmokeError("generation_proof_failed", "pre-generation tensor digest is incomplete")
        saved = row.get("saved_checkpoint_digest")
        reloaded = row.get("reloaded_digest")
        mutated = row.get("mutated_training_digest")
        if not _is_sha256(saved) or not _is_sha256(reloaded) or not _is_sha256(mutated):
            raise M5SmokeError("generation_proof_failed", "pre-generation tensor digest is not a SHA-256")
        if saved != reloaded or row.get("match_saved_checkpoint") is not True:
            raise M5SmokeError("generation_proof_failed", "generation tensor does not match the on-disk checkpoint")
        if mutated == reloaded or row.get("match_mutated_training_object") is not False:
            raise M5SmokeError("generation_proof_failed", "generation used the mutated resumed or overfit object")
    if proof.get("generation_object_matches_on_disk_checkpoint") is not True:
        raise M5SmokeError("generation_proof_failed", "generation object does not match the on-disk checkpoint")
    if proof.get("generation_used_mutated_training_object") is not False:
        raise M5SmokeError("generation_proof_failed", "generation used the mutated resumed or overfit object")
    derived = assert_training_release_observation(proof.get("training_release_observation"))
    if proof.get("training_objects_released_before_generation_reload") is not derived["training_objects_released_before_generation_reload"]:
        raise M5SmokeError("generation_proof_failed", "training-release flag was not derived from the weak-reference observation")
    if proof.get("released_training_object_names") != derived["released_training_object_names"]:
        raise M5SmokeError("generation_proof_failed", "released training object names were not copied from the weak-reference observation")
    if proof.get("separation_basis") != GENERATION_SEPARATION_BASIS or proof.get("python_object_id_is_sufficient") is not False:
        raise M5SmokeError("generation_proof_failed", "generation separation cannot rest on a Python object id")
    generation_id = proof.get("generation_object_id")
    mutated_id = proof.get("mutated_training_object_id")
    if type(generation_id) is not int or type(mutated_id) is not int or generation_id == mutated_id:
        raise M5SmokeError("generation_proof_failed", "generation used the mutated resumed or overfit object")
    return True


def assert_generation_proof(proof, generation_count, checkpoint_inventory):
    return assert_immutable_generation(proof, generation_count, checkpoint_inventory)


def assert_observed_file_hashes(file_hashes):
    if not isinstance(file_hashes, dict):
        raise M5SmokeError("provenance_mismatch", "observed file hashes are missing")
    if set(file_hashes) != set(OBSERVED_FILE_HASH_KEYS):
        raise M5SmokeError("provenance_mismatch", "observed file-hash keys drifted")
    if "manifest" in file_hashes:
        raise M5SmokeError("provenance_mismatch", "the manifest must not contain its own hash")
    for key in ("configuration", "fixture", "implementation_contract", "implementation_harness", "resume_sidecar", "generation_output"):
        if not _is_sha256(file_hashes.get(key, "")):
            raise M5SmokeError("provenance_mismatch", key + " hash was not observed")
    for key in ("starting_assets", "checkpoint_inventory"):
        mapping = file_hashes.get(key)
        if not isinstance(mapping, dict) or not mapping or any(not _is_sha256(value) for value in mapping.values()):
            raise M5SmokeError("provenance_mismatch", key + " hashes were not observed")
    assert_checkpoint_members(file_hashes["checkpoint_inventory"])
    return True


def assert_phase_records(records):
    if not isinstance(records, dict):
        raise M5SmokeError("m5_completion_not_established", "phase records are missing")
    correctness = records.get("correctness")
    feasibility = records.get("physical_microbatch_feasibility")
    accumulation = records.get("gradient_accumulation")
    fp32 = records.get("fp32_observation")
    bf16 = records.get("bf16_numerical_observation")
    weights = records.get("generation_weight_state")
    if not isinstance(correctness, dict) or correctness.get("status") != "observed":
        raise M5SmokeError("m5_completion_not_established", "correctness phase was not observed")
    if int(correctness.get("microbatch", 0)) != PHYSICAL_MICROBATCH_CANDIDATE or int(correctness.get("accumulation", 0)) != ACCUMULATION_MICROSTEPS:
        raise M5SmokeError("microbatch_mismatch", "correctness phase is not microbatch 8 times accumulation 4")
    if int(correctness.get("effective_batch", 0)) != INTENDED_EFFECTIVE_BATCH:
        raise M5SmokeError("microbatch_mismatch", "correctness effective batch drifted")
    if correctness.get("precision") != "float32":
        raise M5SmokeError("m5_completion_not_established", "correctness precision is not FP32")
    assert_physical_microbatch_candidate(feasibility)
    if not isinstance(feasibility, dict) or feasibility.get("status") != "observed" or feasibility.get("fail_closed") is not True:
        raise M5SmokeError("physical_microbatch_candidate_failed", "physical-microbatch feasibility was not observed as fail-closed")
    assert_accumulation_exercise(accumulation)
    if not isinstance(accumulation, dict) or accumulation.get("status") != "observed":
        raise M5SmokeError("microbatch_mismatch", "gradient accumulation was not observed")
    if not isinstance(fp32, dict) or fp32.get("status") != "observed" or fp32.get("precision") != "float32":
        raise M5SmokeError("m5_completion_not_established", "FP32 observation is missing")
    if fp32.get("selects_production_precision") is not False:
        raise M5SmokeError("m5_completion_not_established", "FP32 observation must not select production precision")
    assert_loss_finite(fp32.get("loss"))
    assert_bf16_observation(bf16)
    if fp32.get("loss") != bf16.get("fp32_loss"):
        raise M5SmokeError("m5_completion_not_established", "BF16 comparison did not use the recorded FP32 loss")
    if not isinstance(weights, dict) or weights.get("raw") != "used" or weights.get("ema") != "not_used":
        raise M5SmokeError("m5_completion_not_established", "raw and EMA generation states were not both recorded")
    return True


def assert_starting_ema_inspection(inspection):
    if not isinstance(inspection, dict):
        raise M5SmokeError("m5_completion_not_established", "starting EMA inspection is missing")
    if inspection.get("selects_ema_policy") is not False:
        raise M5SmokeError("m5_completion_not_established", "EMA inspection must not select the EMA policy")
    if "compatible_starting_ema_state_exists" in inspection or "ema_members_found" in inspection:
        raise M5SmokeError("asset_identity_mismatch", "an EMA filename is not a compatible starting state")
    if inspection.get("exact_inspected_inventory") != list(B1_DIFFUSION_DIRECTORY_INVENTORY):
        raise M5SmokeError("asset_identity_mismatch", "B1 diffusion directory inventory drifted")
    if inspection.get("ema_artifact_present") is not False:
        raise M5SmokeError("asset_identity_mismatch", "unexpected EMA artifact in the B1 diffusion directory")
    if inspection.get("ema_compatibility") != "not_applicable_absent":
        raise M5SmokeError("asset_identity_mismatch", "absent EMA state is not not_applicable_absent")
    if inspection.get("inspected_directory") != "configs/rnagenesis/diffusion":
        raise M5SmokeError("asset_identity_mismatch", "EMA inspection did not use the B1 diffusion directory")
    return True


def assert_microbatch_accounting(shapes, smoke_only, report):
    if not isinstance(shapes, dict) or not isinstance(report, dict):
        raise M5SmokeError("microbatch_mismatch", "microbatch observation is missing")
    actual_shape = shapes.get("input_ids_shape")
    if not isinstance(actual_shape, list) or not actual_shape:
        raise M5SmokeError("microbatch_mismatch", "actual batch shape is missing")
    actual = int(actual_shape[0])
    requested = int(smoke_only["smoke_microbatch"])
    if actual != requested or int(report.get("measured_microbatch", -1)) != actual or int(report.get("requested_microbatch", -1)) != requested:
        raise M5SmokeError("microbatch_mismatch", "actual batch does not equal the requested microbatch")
    if report.get("actual_batch_shape") != actual_shape:
        raise M5SmokeError("microbatch_mismatch", "recorded batch shape does not equal the observed batch")
    requested_accumulation = int(smoke_only["smoke_gradient_accumulation"])
    measured_accumulation = int(report.get("measured_accumulation", -1))
    if measured_accumulation != requested_accumulation or int(report.get("requested_accumulation", -1)) != requested_accumulation:
        raise M5SmokeError("microbatch_mismatch", "measured accumulation does not equal the requested accumulation")
    effective = actual * measured_accumulation
    if int(report.get("measured_effective_batch", -1)) != effective or int(report.get("requested_effective_batch", -1)) != int(smoke_only["smoke_effective_batch"]):
        raise M5SmokeError("microbatch_mismatch", "effective batch does not equal microbatch times accumulation")
    if effective != int(smoke_only["smoke_effective_batch"]):
        raise M5SmokeError("microbatch_mismatch", "measured effective batch drifted from the smoke plan")
    return True


def assert_data_access_claims(report):
    audit = report.get("data_input_audit")
    if not isinstance(audit, dict):
        raise M5SmokeError("denied_input", "data-access guard is missing")
    commits = {
        "mres_implementation_commit": report.get("mres_implementation_commit"),
        "mres_authorization_commit": report.get("mres_authorization_commit"),
        "rnagenesis_commit": report.get("rnagenesis_commit"),
    }
    derived = derive_data_access(audit, commits)
    for key in ("train_not_accessed", "validation_not_accessed", "ref_not_accessed", "eval_not_accessed"):
        if report.get(key) is not derived[key]:
            raise M5SmokeError("denied_input", key + " was not derived from the closed CLI and pinned worker path")
    if report.get("declared_scientific_data_inputs") != derived["declared_scientific_data_inputs"]:
        raise M5SmokeError("denied_input", "declared scientific inputs were not derived from the guard")
    if report.get("validated_required_asset_paths") != derived["validated_required_asset_paths"]:
        raise M5SmokeError("denied_input", "validated asset paths were not derived from the guard")
    if report.get("permitted_input_paths") != [FIXTURE_RELATIVE]:
        raise M5SmokeError("denied_input", "permitted scientific input is not the synthetic fixture")
    if derived["dynamic_file_open_audit_performed"] is not False or derived["conclusion"] != "TRAIN_VALIDATION_REF_EVAL_unreachable_through_authorized_cli_and_pinned_worker":
        raise M5SmokeError("denied_input", "data access was described as an observed-open audit")
    return derived


def assert_frozen_manifest(frozen_state):
    if not isinstance(frozen_state, dict):
        raise M5SmokeError("frozen_component_failed", "frozen-state manifest is missing")
    for key in ("after_backward", "after_update", "after_generation"):
        if key not in frozen_state:
            raise M5SmokeError("frozen_component_failed", "frozen snapshot is missing: " + key)
        assert_frozen_snapshot(frozen_state[key])
    assert_post_generation_frozen_snapshot(frozen_state["after_generation"])
    return True


def build_final_manifest(report):
    if not isinstance(report, dict):
        raise M5SmokeError("manifest_suppressed", "report is missing")
    if report.get("completion_state") != "correctness_phase_passed" or report.get("failure_state") is not None:
        raise M5SmokeError("manifest_suppressed", "final manifest is suppressed until every assertion passes")
    if report.get("m5_milestone_complete") is not False:
        raise M5SmokeError("m5_completion_not_established", "collected smoke evidence is not M5 completion")
    if report.get("smoke_measurements_are_not_d1_decisions") is not True:
        raise M5SmokeError("manifest_suppressed", "smoke measurements must not be recorded as D1 decisions")
    missing = [key for key in MANIFEST_KEYS if key not in report]
    if missing:
        raise M5SmokeError("manifest_suppressed", "manifest field is missing: " + missing[0])
    if report["manifest_schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise M5SmokeError("manifest_suppressed", "manifest schema drifted")
    if "manifest_sha256" in report or "manifest" in report.get("file_hashes", {}):
        raise M5SmokeError("provenance_mismatch", "the manifest must not contain its own hash")
    assert_observed_file_hashes(report["file_hashes"])
    assert_phase_records(report["phase_records"])
    assert_starting_ema_inspection(report["starting_ema_inspection"])
    assert_data_access_claims(report)
    assert_memory_peak_accounting(report)
    assert_frozen_manifest(report["frozen_state"])
    assert_package_runtime(report["package_runtime"])
    assert_checkpoint_reload(report["checkpoint_reload"])
    assert_resume_proof(report["resume_proof"])
    generation_count = report.get("generation_output", {}).get("count") if isinstance(report.get("generation_output"), dict) else None
    assert_generation_proof(report["generation_reload"], generation_count, report["file_hashes"]["checkpoint_inventory"])
    return {key: report[key] for key in MANIFEST_KEYS}


def failure_record(code, detail):
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "completion_state": "failed",
        "failure_state": code,
        "detail": detail,
        "final_manifest_emitted": False,
        "smoke_measurements_are_not_d1_decisions": True,
    }


def create_directory_exclusive(path):
    assert_output_isolated(path)
    try:
        os.mkdir(path)
    except FileExistsError:
        raise M5SmokeError("output_directory_exists", "refusing to overwrite an evidence directory")
    return path


def exclusive_write(path, data):
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(str(path), flags, 0o644)
    except FileExistsError:
        raise M5SmokeError("output_directory_exists", "refusing to overwrite " + os.path.basename(str(path)))
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written == 0:
                raise M5SmokeError("evidence_write_failed", "short write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_exclusive(path, data):
    """Write a partial file, then link it into place. Rename is not used because it replaces an existing path."""
    partial = str(path) + PARTIAL_SUFFIX
    exclusive_write(partial, data)
    try:
        os.link(partial, str(path))
    except FileExistsError:
        raise M5SmokeError("output_directory_exists", "refusing to overwrite " + os.path.basename(str(path)))
    os.unlink(partial)
    return path


def _git_line(git, repo, args):
    text = git(repo, args)
    if not isinstance(text, str):
        raise M5SmokeError("git_status_unreadable", "git output is not text")
    return text.strip()


def _implementation_paths():
    return (
        (CONTRACT_RELATIVE, CONTRACT_PATH, "implementation_contract_sha256"),
        (HARNESS_RELATIVE, HARNESS_PATH, "implementation_harness_sha256"),
    )


def evaluate_parent_gate(deps):
    """Run every check that must pass before a GPU query result is trusted.

    The GPU query itself is the last external command. Torch is not imported.
    """
    raw = deps.read_bytes(CONFIG_PATH)
    config = load_config_bytes(raw)
    assert_configuration_executable(config)
    authorisation = assert_active_authorisation(config, deps.physical_gpu, deps.output_directory)
    mres_head = _git_line(deps.git, MRES_ROOT, ["rev-parse", "HEAD"])
    mres_branch = _git_line(deps.git, MRES_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"])
    origin_main = _git_line(deps.git, MRES_ROOT, ["rev-parse", "origin/main"])
    assert_mres_clean(deps.git(MRES_ROOT, ["status", "--porcelain=v1"]))
    if mres_branch != "main" or not _is_sha40(mres_head) or mres_head != origin_main:
        raise M5SmokeError("provenance_mismatch", "MRes branch or commit is not the authorised main HEAD")
    parents = [line.strip() for line in deps.git(MRES_ROOT, ["rev-parse", "HEAD^@"]).splitlines() if line.strip()]
    if len(parents) != 1 or parents[0] != authorisation["authorization_parent_commit"]:
        raise M5SmokeError("provenance_mismatch", "authorization commit parent is not the reviewed implementation commit")
    parent = parents[0]
    if parent != authorisation["executing_implementation_commit"]:
        raise M5SmokeError("provenance_mismatch", "executing implementation commit is not the authorization parent")
    changed = [line.strip() for line in deps.git(MRES_ROOT, ["diff", "--name-only", parent, mres_head]).splitlines() if line.strip()]
    if changed != [CONFIG_RELATIVE]:
        raise M5SmokeError("authorisation_delta_invalid", "authorization commit changes more than the smoke configuration")
    parent_config_text = deps.git(MRES_ROOT, ["show", parent + ":" + CONFIG_RELATIVE])
    parent_config_bytes = parent_config_text.encode("utf-8")
    if sha256_bytes(parent_config_bytes) != authorisation["implementation_config_sha256"]:
        raise M5SmokeError("provenance_mismatch", "implementation config hash does not match the parent blob")
    parent_config = load_config_bytes(parent_config_bytes)
    assert_authorisation_delta(parent_config, config)
    for relative, path, field in _implementation_paths():
        blob = _git_line(deps.git, MRES_ROOT, ["rev-parse", parent + ":" + relative])
        worktree_blob = _git_line(deps.git, MRES_ROOT, ["hash-object", "--", str(path)])
        if blob != worktree_blob:
            raise M5SmokeError("provenance_mismatch", "implementation file does not match the parent commit")
        file_bytes = deps.read_bytes(path)
        if sha256_bytes(file_bytes) != authorisation[field]:
            raise M5SmokeError("provenance_mismatch", "implementation file hash drifted")
    head_config_text = deps.git(MRES_ROOT, ["show", "HEAD:" + CONFIG_RELATIVE])
    if head_config_text.encode("utf-8") != bytes(raw):
        raise M5SmokeError("provenance_mismatch", "active configuration is not the live HEAD blob")
    rna_head = _git_line(deps.git, RNAGENESIS_ROOT, ["rev-parse", "HEAD"])
    rna_branch = _git_line(deps.git, RNAGENESIS_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"])
    if rna_branch != RNAGENESIS_BRANCH or rna_head != RNAGENESIS_HEAD:
        raise M5SmokeError("provenance_mismatch", "RNAGenesis branch or commit drifted")
    assert_rnagenesis_directory_fingerprint(deps.git(RNAGENESIS_ROOT, ["status", "--porcelain=v1"]))
    assert_no_unexpected_untracked_source(deps.git(RNAGENESIS_ROOT, ["status", "--porcelain=v1", "-uall"]))
    digests = {}
    observed_model_paths = []
    for relative, digest, size, role in REQUIRED_MODEL_FILES:
        path = str(RNAGENESIS_ROOT / relative)
        digests[relative] = assert_regular_hashed_file(path, size, digest, deps.lstat, deps.sha256_file, role)
        observed_model_paths.append(relative)
    assert_model_assets(digests)
    patch_sha256 = assert_regular_hashed_file(
        DIFFUSERS_PATCH_PATH,
        DIFFUSERS_PATCH_SIZE,
        DIFFUSERS_PATCH_SHA256,
        deps.lstat,
        deps.sha256_file,
        "diffusers_normalization_patch",
    )
    assert_pinned_python(PINNED_PYTHON, deps.lstat)
    fixture_path = str(FIXTURE_PATH)
    fixture_sha256 = assert_fixture_file(fixture_path, FIXTURE_RELATIVE, FIXTURE_SHA256, deps.read_bytes, deps.lstat)
    if getattr(deps, "require_absent_output", True):
        assert_output_directory_absent(deps.output_directory, deps.lstat)
    else:
        assert_output_isolated(deps.output_directory)
    probe_argv = physical_gpu_query_argv(deps.physical_gpu)
    probe_text = deps.run_argv(probe_argv)
    probe = parse_gpu_probe(probe_text, deps.physical_gpu)
    assert_gpu_probe(probe, deps.physical_gpu, authorisation)
    assert_inherited_cuda(dict(deps.environ), deps.physical_gpu)
    child_env = build_child_environment(
        dict(deps.environ),
        deps.physical_gpu,
        deps.output_directory,
        getattr(deps, "realpath", None),
    )
    plan = {
        "authorisation": authorisation,
        "authorization_commit": mres_head,
        "implementation_commit": parent,
        "rnagenesis_commit": rna_head,
        "probe": probe,
        "argv": worker_argv(deps.output_directory, deps.physical_gpu, sha256_bytes(canonical_json(authorisation))),
        "env": child_env,
        "cwd": str(RNAGENESIS_ROOT),
        "shell": False,
        "evidence_directory": deps.output_directory,
        "config_sha256": sha256_bytes(bytes(raw)),
        "fixture_sha256": fixture_sha256,
        "model_digests": digests,
        "observed_model_paths": observed_model_paths,
        "observed_environment_paths": [DIFFUSERS_PATCH_PATH],
        "patch_sha256": patch_sha256,
        "fixture_relative": FIXTURE_RELATIVE,
        "implementation_hashes": {
            "implementation_contract": authorisation["implementation_contract_sha256"],
            "implementation_harness": authorisation["implementation_harness_sha256"],
        },
        "smoke_only": dict(config["smoke_only"]),
    }
    if plan["shell"] is not False or not isinstance(plan["argv"], list):
        raise M5SmokeError("worker_spawn_invalid", "worker command must be an argument array")
    return plan


def assert_shape_observation(observation):
    """Plain-data shape contract shared by the later worker and the CPU tests."""
    if not isinstance(observation, dict):
        raise M5SmokeError("shape_assertion_failed", "shape observation is missing")
    if observation.get("input_ids_dtype") != "int64" or observation.get("attention_mask_dtype") != "bool":
        raise M5SmokeError("shape_assertion_failed", "token or mask dtype drifted")
    input_shape = observation.get("input_ids_shape")
    mask_shape = observation.get("attention_mask_shape")
    if input_shape != mask_shape or not isinstance(input_shape, list) or len(input_shape) != 2 or input_shape[0] < 1:
        raise M5SmokeError("shape_assertion_failed", "token and mask shapes drifted")
    latent_shape = observation.get("latent_shape")
    if latent_shape != [input_shape[0], LATENT_QUERIES, LATENT_CHANNELS] or observation.get("latent_dtype") != "float32":
        raise M5SmokeError("shape_assertion_failed", "latent shape or dtype drifted")
    if observation.get("noise_shape") != latent_shape or observation.get("noise_dtype") != "float32":
        raise M5SmokeError("shape_assertion_failed", "noise shape or dtype drifted")
    if observation.get("timestep_shape") != [input_shape[0]] or observation.get("timestep_dtype") != "int64":
        raise M5SmokeError("shape_assertion_failed", "timestep shape or dtype drifted")
    if observation.get("loss_shape") != [] or observation.get("loss_dtype") != "float32":
        raise M5SmokeError("shape_assertion_failed", "loss shape or dtype drifted")
    return True


def component_parameter_table(rows):
    components = PARAMETER_TABLE_COMPONENTS
    table = {name: {"total": 0, "trainable": 0, "frozen": 0, "dtypes": []} for name in components}
    for row in rows:
        component = row["component"]
        if component not in table:
            raise M5SmokeError("parameter_table_invalid", "unexpected parameter component")
        count = int(row["numel"])
        table[component]["total"] += count
        if row["requires_grad"] is True:
            table[component]["trainable"] += count
        else:
            table[component]["frozen"] += count
        if row["dtype"] not in table[component]["dtypes"]:
            table[component]["dtypes"].append(row["dtype"])
    return table

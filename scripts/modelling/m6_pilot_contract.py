#!/usr/bin/env python3
"""M6 pilot contract.

Importing this module does not import torch, Accelerate, Diffusers, or
RNAGenesis, and it does not open biological data, model weights, or a run
directory. The checked-in pilot configuration is inactive and is not
executable. The active-authorisation schema below is what a later
authorisation-only commit can satisfy without changing this module.

The applied learning-rate schedule is the pure function
``learning_rate_multiplier``. It does not call the Diffusers cosine
constructor. That constructor, combined with LambdaLR's zero-based index,
makes the first applied multiplier zero. This schedule never applies that
position. Position 22 is the next unapplied schedule position. It is not a
PyTorch scheduler ``last_epoch``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
from fractions import Fraction

MRES_ROOT = "/home/laura/rnagenesis-aptamer-mres"
RNAGENESIS_ROOT = "/home/laura/RNAGenesis"
CONFIG_RELATIVE = "config/experiments/D1_diffusion_pilot.yaml"
CONTRACT_RELATIVE = "scripts/modelling/m6_pilot_contract.py"
RUNNER_RELATIVE = "scripts/modelling/m6_pilot_runner.py"
PINNED_PYTHON = "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"
RNAGENESIS_BRANCH = "mres-d1-diffusion-finetune"
RNAGENESIS_COMMIT = "e3b855bbf4d1af376f43747643fa30afd662828c"
MRES_BASE_COMMIT = "292b956757b6a99ecb67d3f4a623e828d19f5b3d"
DOCUMENT_STATUS = "M6_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED"
ACTIVE_DOCUMENT_STATUS = "M6_AUTHORISED_FOR_SINGLE_USE_EXECUTION"
SCHEMA_VERSION = "m6-pilot-config-1"
MANIFEST_SCHEMA_VERSION = "m6-pilot-manifest-1"
EXPERIMENT_ID = "D1_diffusion_pilot"

TRAIN_RECORD_COUNT = 669
PHYSICAL_MICROBATCH = 8
GRADIENT_ACCUMULATION = 4
INTENDED_EFFECTIVE_BATCH = 32
MICROBATCH_COUNT = 84
OPTIMIZER_UPDATES = 21
FINAL_WINDOW = (8, 8, 8, 5)
FINAL_WINDOW_EXAMPLES = 29
WARMUP_UPDATES = 2
POST_UPDATE_POSITION = OPTIMIZER_UPDATES + 1
BASE_LEARNING_RATE = 3e-5
ADAMW_BETA1 = 0.95
ADAMW_BETA2 = 0.999
ADAMW_WEIGHT_DECAY = 1e-6
ADAMW_EPSILON = 1e-8
GRADIENT_CLIP_NORM = 1.0
PILOT_SEED = 42
VALIDATION_DRAW_SEED = 1
VALIDATION_UPDATES = (0, 7, 14, 21)
RETAINED_WEIGHT_UPDATES = (7, 14, 21)
LEARNING_CURVE_ONLY_UPDATES = (7, 14)
VALIDATION_SEQUENCE_COUNT = 95
VALIDATION_DRAWS = 4
VALIDATION_PAIR_COUNT = 380
LATENT_QUERIES = 32
LATENT_CHANNELS = 160
VALIDATION_TIMESTEP_SHAPE = (VALIDATION_SEQUENCE_COUNT, VALIDATION_DRAWS)
VALIDATION_NOISE_SHAPE = (VALIDATION_SEQUENCE_COUNT, VALIDATION_DRAWS, LATENT_QUERIES, LATENT_CHANNELS)

TRAIN_TEXT_SHA256 = "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d"
VALIDATION_CSV_SHA256 = "cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd"
VALIDATION_SEQUENCE_ORDER_SHA256 = "eb18fd48e305e86f8000bdc82e9175437d478bd624ea57aef8094497534bda3a"
VALIDATION_ORDER_ARTIFACT_SHA256 = "df445b617adf5165f3361412bb5c7bc5d2a05b31a98eb6d2f6d17f4b329de248"
VALIDATION_DRAW_MANIFEST_SHA256 = "b4e8d6d7cf7298d201062986419797e7fc322f2e88066764d4332a432a0d0d49"
VALIDATION_TIMESTEPS_SHA256 = "9009b50b26ec126978236e6c86ed8d639634a8b211a3fb842ddf8ad9ea38fe07"
VALIDATION_NOISE_SHA256 = "6be13ab704ce4b3f21e6ab5787eb18e77943d52540b517de46f41b47b083ccdc"
VALIDATION_HASH_REPORT_SHA256 = "bc6c7587e4a22892d84d1e901939bf988304957da778d49afb00cdea552ea075"
B1_WEIGHT_SHA256 = "c268021b6cab37423e3bffd495b139bb69698d8d11c7b96477fbfb239b0cff26"
B1_UNET_CONFIG_SHA256 = "3a9975ff165bbd5ca82923e6ed1c5ed7eb383a23f4f3f55db713c995031f8ee3"
B1_WEIGHT_BYTES = 7847725416
B1_PARAMETER_COUNT = 1911589344
REF_HASH_METADATA = "531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23"
EVAL_HASH_METADATA = "ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015"
PAIRED_SCHEDULE_SHA256 = "0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0"
B0_UNET_WEIGHT_SHA256 = "149f012287b1ae83865c25867d7c0bbe0952fa51bcc068e259725092d5dff0ca"

DEVELOPMENT_DATA_ROOT = "/home/laura/rnagenesis-mres-data/development"
FUTURE_TRAIN_TEXT_PATH = DEVELOPMENT_DATA_ROOT + "/corpus_final.txt"
FUTURE_VALIDATION_CSV_PATH = DEVELOPMENT_DATA_ROOT + "/ft_validation.csv"
ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY = (
    "/home/laura/rnagenesis-mres-runs/m4_validation_draw_artifacts_d2b2041520d1"
)
RUN_ROOT = "/home/laura/rnagenesis-mres-runs"
B1_RELATIVE_PATH = "configs/rnagenesis/diffusion"
ENCDEC_RELATIVE_PATH = "configs/rnagenesis/autoencoder"
ACTIVE_PHASE = "M6_D1_diffusion_pilot"
ACTIVE_SCOPE = "single_use_m6_d1_pilot"
LOGICAL_CUDA_DEVICE = "cuda:0"
CONSUMPTION_EVENT = "bound_output_directory_creation"
SESSION_PATTERN = "m5_single_use_timestamp_and_scope"
CONSUMPTION_RECORD_NAME = "authorization_consumption.json"
FAILURE_RECORD_NAME = "authorization_failure.json"
SUCCESS_MANIFEST_NAME = "m6_pilot_manifest.json"
ACCUMULATION_MODE = "manual_microbatches_accelerator_accumulation_steps_1"
PRODUCTION_ACCELERATOR_GRADIENT_ACCUMULATION_STEPS = 1
PINNED_ACCELERATE_VERSION = "0.25.0"
ACTIVE_ROLES = (
    "B1_INITIALISATION",
    "FROZEN_ENCDEC",
    "TRAIN_TEXT",
    "VALIDATION_ARTIFACT",
    "VALIDATION_CSV",
)
IMPLEMENTATION_FILE_PATHS = (
    "scripts/modelling/build_validation_artifacts.py",
    "scripts/modelling/m6_pilot_contract.py",
    "scripts/modelling/m6_pilot_runner.py",
    "tests/modelling/test_m6_pilot_authorised.py",
    "tests/modelling/test_m6_pilot_contract.py",
    "tests/modelling/test_m6_pilot_runner_mocked.py",
)
ARTIFACT_LOADER_RELATIVE = "scripts/modelling/build_validation_artifacts.py"
ARTIFACT_LOADER_PATH = MRES_ROOT + "/" + ARTIFACT_LOADER_RELATIVE
PERMITTED_AUTHORIZATION_FILES = ("config/experiments/D1_diffusion_pilot.yaml",)
VALIDATION_ARTIFACT_FILES = (
    "validation_draw_manifest.json",
    "validation_draw_manifest_sha256.json",
    "validation_noise.float32",
    "validation_order_artifact.csv",
    "validation_timesteps.int64",
)
# RNAGenesis untracked acceptance is the reviewed M5 directory fingerprint
# plus the M5 source/configuration rejection. A blanket models/ prefix is not
# an identity check.
DOCUMENTED_DEVIATIONS = (
    "explicit_applied_lr_not_pytorch_last_epoch",
    "manual_accumulation_accelerator_steps_1",
    "pinned_artifact_loader_uses_numpy_frombuffer",
    "validation_draws_loaded_not_regenerated",
)

GENERATION_BOS_TOKEN = 1
GENERATION_EOS_TOKEN = 2
M6_REQUIRED_RAW_PREFIX = "11"
M5_DIRECT_GENERATE_PREFIX_OBSERVATION = "1"
PROHIBITED_CLEANER = "scripts/clean_generated_sequences.py"
DIAGNOSTIC_GENERATION_STATUS = "not_performed_requires_separate_authorisation"
NORMALIZATION_POLICY = "exact_leading_prefix_11_no_suffix_removal"
BODY_PATTERN = re.compile(r"^[ACGU]+$")
ENCDEC_COMPONENTS = ("encoder", "qformer", "query_tokens", "latent_projection", "decoder")
CHECKPOINT_MEMBERS = (
    "model_index.json",
    "scheduler/scheduler_config.json",
    "unet/config.json",
    "unet/diffusion_pytorch_model.safetensors",
)
CONFIGURATION_IGNORED_TOP_LEVEL_KEYS = ("_name_or_path",)
DENIED_BASENAMES = {"ref.csv": "REF", "eval.csv": "EVAL"}
DENIED_ROLES = {"REF", "EVAL"}
DENIED_HASHES = {REF_HASH_METADATA: "REF", EVAL_HASH_METADATA: "EVAL"}
OBSOLETE_PATH_MARKERS = (
    "/rnagenesis-aptamer-mres/data/processed/",
    "/rnagenesis-aptamer-mres/data/processed",
    "/rnagenesis-aptamer-mres/data/interim/",
    "/rnagenesis-aptamer-mres/data/interim",
)
SEQUENCE_TEXT_KEYS = {
    "sequence",
    "sequence_core",
    "sequence_text",
    "raw_string",
    "raw_output",
    "normalized_string",
    "cleaned_sequence",
}
# Authoritative registry for the active launch and worker path. A success
# manifest records every code with fired false. A consumed failure record's
# fired_stop_condition must be one of these codes. Literal M6PilotError codes
# in the contract and runner are classified here or in the CLI exclusion set.
STOP_CONDITION_CODES = (
    "authorisation_commit_invalid",
    "authorisation_delta_invalid",
    "authorisation_evidence_mismatch",
    "authorisation_field_missing",
    "authorisation_inactive",
    "authorisation_scope_invalid",
    "authorisation_shape_invalid",
    "authorization_reuse",
    "automatic_lr_change_rejected",
    "checkpoint_overwrite_risk",
    "checkpoint_save_reload_incompatibility",
    "config_encoding",
    "config_parse",
    "config_shape",
    "configuration_not_consumable",
    "cuda_rng_final_observation_failed",
    "diagnostic_generation_not_authorised",
    "execution_not_authorised",
    "identity_mismatch",
    "incomplete_evidence_or_manifest",
    "learning_rate_schedule_invalid",
    "learning_rate_zero_applied",
    "microbatch_arithmetic_invalid",
    "modified_or_trainable_encdec",
    "no_observed_denoiser_change",
    "non_finite_pre_clip_gradient_norm",
    "non_finite_trainable_gradient",
    "non_finite_training_loss",
    "non_finite_validation",
    "provenance_mismatch",
    "ref_or_eval_access",
    "training_stack_import_failed",
    "unexpected_biological_path_or_role",
    "unexpected_output_normalization",
    "validation_schedule_invalid",
)
# Inactive CLI and pre-consumption entry gate only. These fire before a bound
# directory exists, so they are not success-manifest rows and cannot be a
# consumed failure's fired_stop_condition.
INACTIVE_CLI_ONLY_STOP_CODES = (
    "cli_argument_rejected",
    "environment_injection_rejected",
)
MANIFEST_KEYS = (
    "applied_learning_rate_trace",
    "authorisation",
    "b1_identity",
    "completion_state",
    "config_version",
    "data_roles",
    "denoiser_update_evidence",
    "deviations",
    "diagnostic_generation_status",
    "environment",
    "experiment_id",
    "failure_state",
    "frozen_state",
    "gpu",
    "manifest_schema_version",
    "memory",
    "microbatch_accounting",
    "optimizer",
    "post_update_21_scheduler_position",
    "production_identities",
    "ref_eval_access",
    "repository",
    "restart_policy",
    "resume_supported",
    "rng",
    "run_id",
    "schema_version",
    "stop_conditions",
    "timing",
    "train_update_observations",
    "validation_artifacts",
    "validation_observations",
    "validation_review",
    "warnings",
    "weight_checkpoints",
)
COMPLETION_STATES = {"pilot_completed", "synthetic_control_flow_completed"}
GUARDRAILS = {
    "valid_nonempty_acgu_fraction_min": 0.99,
    "empty_or_unparseable_fraction_max": 0.01,
    "unique_fraction_min": 0.95,
    "exact_train_match_rate_max": 0.01,
    "largest_duplicate_share_max": 0.01,
}


class M6PilotError(Exception):
    def __init__(self, code, detail, stage=None, update=None, microbatch=None):
        self.code = code
        self.detail = detail
        self.stage = stage
        self.update = update
        self.microbatch = microbatch
        super().__init__(code + ": " + detail)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    """Stream a file through SHA-256. The whole file is never one bytes object."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_M5_CONTRACT = None


def m5_contract():
    """Load the accepted M5 contract by its tracked path. Constants are not copied."""
    global _M5_CONTRACT
    if _M5_CONTRACT is None:
        path = os.path.join(MRES_ROOT, "scripts/modelling/m5_smoke_contract.py")
        spec = importlib.util.spec_from_file_location("m5_smoke_contract_for_m6", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if os.path.realpath(module.__file__) != os.path.realpath(path):
            raise M6PilotError("identity_mismatch", "M5 contract did not resolve to the tracked file")
        _M5_CONTRACT = module
    return _M5_CONTRACT


def _translate_m5(exc):
    raise M6PilotError("identity_mismatch", exc.detail)


def observe_regular_hashed_file(path, expected_size, expected_hash, role, lstat=None, hash_file=None):
    """Measure a regular file. The returned hash and size come from that measurement."""
    if lstat is None:
        lstat = os.lstat
    if hash_file is None:
        hash_file = sha256_file
    m5 = m5_contract()
    try:
        digest = m5.assert_regular_hashed_file(path, expected_size, expected_hash, lstat, hash_file, role)
    except m5.M5SmokeError as exc:
        _translate_m5(exc)
    measured = lstat(path)
    return {
        "byte_size": int(measured.st_size),
        "evidence_origin": "observed",
        "expected_byte_size": int(expected_size),
        "expected_sha256": expected_hash,
        "observation_method": "streamed_sha256",
        "path": path,
        "regular_file": True,
        "role": role,
        "sha256": digest,
        "symlink": False,
    }


def observe_required_assets(root=None, lstat=None, hash_file=None):
    """Hash every accepted model asset and the Diffusers patch before biological access."""
    m5 = m5_contract()
    root = str(m5.RNAGENESIS_ROOT if root is None else root)
    records = {}
    for relative, digest, size, role in m5.REQUIRED_MODEL_FILES:
        path = os.path.join(root, relative)
        records[role] = observe_regular_hashed_file(path, size, digest, role, lstat=lstat, hash_file=hash_file)
    records["diffusers_normalization_patch"] = observe_regular_hashed_file(
        m5.DIFFUSERS_PATCH_PATH,
        m5.DIFFUSERS_PATCH_SIZE,
        m5.DIFFUSERS_PATCH_SHA256,
        "diffusers_normalization_patch",
        lstat=lstat,
        hash_file=hash_file,
    )
    return records


def assert_observed_runtime(runtime):
    """Fail closed unless the live module versions match the accepted runtime."""
    m5 = m5_contract()
    runtime = _exact_keys(
        runtime,
        ("accelerate", "diffusers", "evidence_origin", "executable", "observation_method", "python", "torch", "transformers"),
        "identity_mismatch",
    )
    if runtime["evidence_origin"] != "observed" or runtime["observation_method"] != "module_attribute":
        raise M6PilotError("identity_mismatch", "runtime versions were not read from the live modules")
    if runtime["executable"] != m5.PINNED_PYTHON:
        raise M6PilotError("identity_mismatch", "python executable is not the pinned interpreter")
    for key, expected in m5.ACCEPTED_RUNTIME_VERSIONS.items():
        if runtime[key] != expected:
            raise M6PilotError("identity_mismatch", key + " version is not the accepted runtime")
    return runtime


def assert_pinned_python_file(path, lstat=None):
    m5 = m5_contract()
    if lstat is None:
        lstat = os.lstat
    try:
        return m5.assert_pinned_python(path, lstat)
    except m5.M5SmokeError as exc:
        _translate_m5(exc)


def assert_rnagenesis_reviewed_tree(directory_porcelain, file_porcelain):
    """Exact M5 untracked-directory fingerprint, then M5 source and config rejection."""
    m5 = m5_contract()
    try:
        m5.assert_rnagenesis_directory_fingerprint(directory_porcelain)
        m5.assert_no_unexpected_untracked_source(file_porcelain)
    except m5.M5SmokeError as exc:
        raise M6PilotError("provenance_mismatch", exc.detail)
    return True


def isolation_environment(parent, physical_gpu, evidence_dir):
    """Bytecode off, the three Hugging Face offline controls, and caches under the evidence directory."""
    m5 = m5_contract()
    try:
        child = m5.build_child_environment(dict(parent), int(physical_gpu), evidence_dir)
    except m5.M5SmokeError as exc:
        raise M6PilotError("identity_mismatch", exc.detail)
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        if child.get(key) != "1":
            raise M6PilotError("identity_mismatch", "Hugging Face offline control is not set: " + key)
    if child.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise M6PilotError("identity_mismatch", "bytecode writing is not disabled")
    return child


def assert_isolation_environment(environ, evidence_dir):
    m5 = m5_contract()
    if environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise M6PilotError("identity_mismatch", "bytecode writing is not disabled")
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        if environ.get(key) != "1":
            raise M6PilotError("identity_mismatch", "Hugging Face offline control is not set: " + key)
    expected = m5.runtime_isolation_paths(evidence_dir)
    observed = {}
    for key, path in expected.items():
        if environ.get(key) != path:
            raise M6PilotError("identity_mismatch", "runtime cache is not isolated: " + key)
        observed[key] = environ.get(key)
    try:
        m5.assert_runtime_isolation(evidence_dir)
    except m5.M5SmokeError as exc:
        raise M6PilotError("identity_mismatch", exc.detail)
    return observed


def canonical_json(value):
    """UTF-8 JSON with sorted keys, compact separators, and one trailing LF."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"


def format_decimal(value):
    return format(float(value), ".17g")


def _is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _is_sha40(value):
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def _require_mapping(value, code, detail):
    if not isinstance(value, dict):
        raise M6PilotError(code, detail)
    return value


def _exact_keys(mapping, expected, code):
    mapping = _require_mapping(mapping, code, "expected a mapping")
    expected_set = set(expected)
    missing = sorted(expected_set - set(mapping))
    unexpected = sorted(set(mapping) - expected_set)
    if missing or unexpected:
        raise M6PilotError(code, "missing " + ",".join(missing) + " unexpected " + ",".join(unexpected))
    return mapping


def _finite_float(value, code):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise M6PilotError(code, "value is not a real number")
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise M6PilotError(code, "value is not finite")
    return number


def _walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)


def _contains_key(value, wanted):
    return any(key == wanted for key, _item in _walk(value))


def load_config_bytes(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise M6PilotError("config_encoding", "configuration bytes are required")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise M6PilotError("config_encoding", "configuration must be UTF-8 without a BOM or carriage return")
    import yaml

    try:
        loaded = yaml.safe_load(bytes(raw).decode("utf-8"))
    except Exception:
        raise M6PilotError("config_parse", "configuration could not be parsed")
    return _require_mapping(loaded, "config_shape", "configuration root must be a mapping")


def assert_inactive_text(text):
    """Reject GPU bindings, active flags, and an output path in the raw document."""
    if not isinstance(text, str):
        raise M6PilotError("configuration_not_consumable", "configuration text is required")
    forbidden_substrings = (
        "GPU-",
        "pci_bus",
        "physical_gpu",
        "cuda_visible_devices",
        "CUDA_VISIBLE_DEVICES",
        "authorised: true",
        "authorisation_active: true",
        "consumable_by_executable_workflow: true",
    )
    for token in forbidden_substrings:
        if token in text:
            raise M6PilotError("configuration_not_consumable", "inactive configuration contains " + token)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("output_directory:") and not stripped.endswith("null"):
            raise M6PilotError("configuration_not_consumable", "output_directory is not null")
        if stripped.startswith("evidence_directory:") and not stripped.endswith("null"):
            raise M6PilotError("configuration_not_consumable", "evidence_directory is not null")
        if stripped.startswith("authorisation_id:") and not stripped.endswith("null"):
            raise M6PilotError("configuration_not_consumable", "authorisation_id is not null")
        if stripped.startswith("authorization_parent_commit:") and not stripped.endswith("null"):
            raise M6PilotError("configuration_not_consumable", "authorization parent commit is not null")
        if stripped.startswith("executing_implementation_commit:") and not stripped.endswith("null"):
            raise M6PilotError("configuration_not_consumable", "implementation commit is not null")
        if stripped.startswith("authorization_commit:"):
            raise M6PilotError("configuration_not_consumable", "tracked configuration must not store an authorization commit key")
    return True


def _reject_forbidden_keys(value):
    for key, _item in _walk(value):
        if key in {"physical_gpu", "gpu_uuid", "pci_bus", "cuda_visible_devices"}:
            raise M6PilotError("configuration_not_consumable", "forbidden device key " + key)


def assert_inactive_configuration(config):
    """Validate the checked-in pilot document. This does not authorise a run."""
    config = _exact_keys(config, CONFIGURATION_ROOT_KEYS, "configuration_not_consumable")
    _reject_forbidden_keys(config)
    if config.get("document_status") != DOCUMENT_STATUS:
        raise M6PilotError("configuration_not_consumable", "document_status is not the inactive M6 status")
    if config.get("consumable_by_executable_workflow") is not False:
        raise M6PilotError("configuration_not_consumable", "configuration must not be consumable")
    if config.get("schema_version") != SCHEMA_VERSION or config.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        raise M6PilotError("configuration_not_consumable", "schema version drifted")
    if config.get("experiment_id") != EXPERIMENT_ID:
        raise M6PilotError("configuration_not_consumable", "experiment id drifted")
    if config.get("created_against_mres_commit") != MRES_BASE_COMMIT:
        raise M6PilotError("configuration_not_consumable", "MRes base commit drifted")
    if config.get("rnagenesis_commit") != RNAGENESIS_COMMIT or config.get("rnagenesis_branch") != RNAGENESIS_BRANCH:
        raise M6PilotError("configuration_not_consumable", "RNAGenesis pin drifted")
    execution = _exact_keys(config.get("execution"), EXECUTION_KEYS, "configuration_not_consumable")
    if execution.get("authorised") is not False or execution.get("biological_paths_permitted") is not False:
        raise M6PilotError("configuration_not_consumable", "execution flags must stay closed")
    if execution.get("gpu_identity_bound") is not False:
        raise M6PilotError("configuration_not_consumable", "GPU identity must stay unbound")
    if "authorization_commit" in execution or _contains_key(config, "authorization_commit"):
        raise M6PilotError("configuration_not_consumable", "tracked configuration must not store authorization_commit")
    for key in (
        "output_directory",
        "evidence_directory",
        "authorisation_id",
        "authorization_parent_commit",
        "executing_implementation_commit",
    ):
        if execution.get(key) is not None:
            raise M6PilotError("configuration_not_consumable", key + " must be null")
    assert_inactive_authorisation(config.get("pilot_execution_authorisation"))
    decisions = _require_mapping(config.get("pilot_decisions"), "configuration_not_consumable", "pilot decisions are missing")
    expected_decisions = {
        "initialization": "immutable_B1_generic_diffusion_checkpoint",
        "encdec_frozen": "complete",
        "trainable": "full_denoiser",
        "precision": "fp32",
        "physical_microbatch": PHYSICAL_MICROBATCH,
        "gradient_accumulation": GRADIENT_ACCUMULATION,
        "intended_effective_batch": INTENDED_EFFECTIVE_BATCH,
        "train_records": TRAIN_RECORD_COUNT,
        "microbatches": MICROBATCH_COUNT,
        "optimizer_updates": OPTIMIZER_UPDATES,
        "final_window_examples": FINAL_WINDOW_EXAMPLES,
        "final_window_microbatch_sizes": list(FINAL_WINDOW),
        "accumulation_weighting": "example_weighted_contributions_sum_to_one",
        "optimizer_name": "AdamW",
        "learning_rate": BASE_LEARNING_RATE,
        "beta1": ADAMW_BETA1,
        "beta2": ADAMW_BETA2,
        "weight_decay": ADAMW_WEIGHT_DECAY,
        "epsilon": ADAMW_EPSILON,
        "gradient_clip_norm": GRADIENT_CLIP_NORM,
        "gradient_clip_is_abort_threshold": False,
        "ema_enabled": False,
        "validation_and_diagnostics_use": "raw_denoiser_weights",
        "pilot_seed": PILOT_SEED,
        "validation_draw_seed": VALIDATION_DRAW_SEED,
        "validation_updates": list(VALIDATION_UPDATES),
        "retained_weight_updates": list(RETAINED_WEIGHT_UPDATES),
        "learning_curve_only_updates": list(LEARNING_CURVE_ONLY_UPDATES),
        "learning_curve_updates_selectable_from_validation_loss_alone": False,
        "update_0_copies_b1_checkpoint": False,
        "automatic_learning_rate_reduction_to_1e-5": False,
        "learning_rate_sweep": False,
        "diagnostic_generation_in_training_runner": False,
        "diagnostic_generation_status": DIAGNOSTIC_GENERATION_STATUS,
        "resume_supported": False,
        "warmup_updates": WARMUP_UPDATES,
        "total_applied_optimizer_updates": OPTIMIZER_UPDATES,
        "scheduler": "explicit_applied_update_cosine",
        "diffusers_scheduler_constructor_used": False,
    }
    for key, expected in expected_decisions.items():
        if decisions.get(key) != expected:
            raise M6PilotError("configuration_not_consumable", "pilot decision drifted: " + key)
    data = _require_mapping(config.get("data"), "configuration_not_consumable", "data block is missing")
    if data.get("open_permitted") is not False or data.get("ref_access") is not False or data.get("eval_access") is not False:
        raise M6PilotError("configuration_not_consumable", "biological access must stay closed")
    historical = _require_mapping(config.get("historical_m4_stage1_approval"), "configuration_not_consumable", "M4 history is missing")
    if historical.get("retained_as_history_only") is not True or historical.get("authorises_m6_execution") is not False:
        raise M6PilotError("configuration_not_consumable", "M4 history must not authorise M6")
    return True


def reject_inactive_before_execution(config):
    """Production gate. Raising here is the success path for the checked-in file."""
    assert_inactive_configuration(config)
    raise M6PilotError("execution_not_authorised", "the checked-in M6 pilot configuration is not executable")


def learning_rate_multiplier(position):
    """Return the multiplier for one explicit scheduler position.

    Positions 1 through 21 are the applied optimizer updates. Position 1 is
    half the base learning rate and position 2 is the base learning rate.
    Positions 3 through 21 are the cosine phase. Position 3 is progress 0,
    so its multiplier is 1. Position 22 is the scheduler position immediately
    after update 21 and is exactly 0. It is not an applied update.
    """
    if isinstance(position, bool) or not isinstance(position, int):
        raise M6PilotError("learning_rate_schedule_invalid", "scheduler position must be an integer")
    if position == POST_UPDATE_POSITION:
        return 0.0
    if position < 1 or position > OPTIMIZER_UPDATES:
        raise M6PilotError("learning_rate_schedule_invalid", "scheduler position is outside the pilot schedule")
    if position <= WARMUP_UPDATES:
        return position / float(WARMUP_UPDATES)
    cosine_span = OPTIMIZER_UPDATES - WARMUP_UPDATES
    progress = (position - WARMUP_UPDATES - 1) / float(cosine_span)
    return 0.5 * (1.0 + math.cos(math.pi * progress))


def applied_learning_rate(update_number):
    """Learning rate recorded before applied optimizer update ``update_number``."""
    if isinstance(update_number, bool) or not isinstance(update_number, int):
        raise M6PilotError("learning_rate_schedule_invalid", "applied update number must be an integer")
    if update_number < 1 or update_number > OPTIMIZER_UPDATES:
        raise M6PilotError("learning_rate_zero_applied", "only updates 1 through 21 have an applied learning rate")
    multiplier = learning_rate_multiplier(update_number)
    if multiplier == 0.0:
        raise M6PilotError("learning_rate_zero_applied", "an applied optimizer update would use learning rate zero")
    return BASE_LEARNING_RATE * multiplier


def applied_learning_rate_trace():
    return tuple(applied_learning_rate(update) for update in range(1, OPTIMIZER_UPDATES + 1))


def post_update_scheduler_position():
    multiplier = learning_rate_multiplier(POST_UPDATE_POSITION)
    if multiplier != 0.0:
        raise M6PilotError("learning_rate_schedule_invalid", "post-update-21 multiplier is not zero")
    return {"position": POST_UPDATE_POSITION, "multiplier": 0.0, "applied_to_optimizer": False}


def assert_applied_trace(trace):
    expected = applied_learning_rate_trace()
    if tuple(trace) != expected:
        raise M6PilotError("learning_rate_schedule_invalid", "applied learning-rate trace does not match the authority")
    if any(value == 0.0 or value < 0.0 for value in expected):
        raise M6PilotError("learning_rate_zero_applied", "an applied learning rate is zero or negative")
    if len(expected) != OPTIMIZER_UPDATES:
        raise M6PilotError("learning_rate_schedule_invalid", "the applied trace is not 21 values")
    return expected


def train_microbatch_sizes(record_count=TRAIN_RECORD_COUNT, microbatch=PHYSICAL_MICROBATCH):
    if record_count != TRAIN_RECORD_COUNT or microbatch != PHYSICAL_MICROBATCH:
        raise M6PilotError("microbatch_arithmetic_invalid", "the pilot arithmetic is fixed at 669 records and microbatch 8")
    full, remainder = divmod(record_count, microbatch)
    sizes = (microbatch,) * full
    if remainder:
        sizes = sizes + (remainder,)
    if len(sizes) != MICROBATCH_COUNT or sum(sizes) != TRAIN_RECORD_COUNT:
        raise M6PilotError("microbatch_arithmetic_invalid", "microbatch count is not 84")
    return sizes


def accumulation_windows(sizes=None, accumulation=GRADIENT_ACCUMULATION):
    if sizes is None:
        sizes = train_microbatch_sizes()
    if accumulation != GRADIENT_ACCUMULATION:
        raise M6PilotError("microbatch_arithmetic_invalid", "gradient accumulation is fixed at 4")
    if len(sizes) % accumulation != 0:
        raise M6PilotError("microbatch_arithmetic_invalid", "microbatches do not fill complete accumulation windows")
    windows = tuple(tuple(sizes[index:index + accumulation]) for index in range(0, len(sizes), accumulation))
    if len(windows) != OPTIMIZER_UPDATES:
        raise M6PilotError("microbatch_arithmetic_invalid", "optimizer updates are not 21")
    if windows[-1] != FINAL_WINDOW or sum(windows[-1]) != FINAL_WINDOW_EXAMPLES:
        raise M6PilotError("microbatch_arithmetic_invalid", "the final window is not [8, 8, 8, 5]")
    return windows


def example_weighted_contributions(window):
    """Exact rational weights. Their sum is 1 for every pilot window."""
    if not isinstance(window, (list, tuple)) or not window:
        raise M6PilotError("microbatch_arithmetic_invalid", "an accumulation window is required")
    total = 0
    for size in window:
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise M6PilotError("microbatch_arithmetic_invalid", "microbatch size must be a positive integer")
        total += size
    weights = tuple(Fraction(size, total) for size in window)
    if sum(weights, Fraction(0)) != 1:
        raise M6PilotError("microbatch_arithmetic_invalid", "example weights do not sum to one")
    return weights


def applied_float_scales(window):
    """Float64 scales whose last term is the residual, so the sum is exactly 1."""
    weights = example_weighted_contributions(window)
    if len(weights) == 1:
        return (1.0,)
    head = [float(weight) for weight in weights[:-1]]
    residual = 1.0 - math.fsum(head)
    if not math.isfinite(residual) or residual <= 0.0:
        raise M6PilotError("microbatch_arithmetic_invalid", "the residual accumulation scale is not positive")
    scales = tuple(head + [residual])
    if math.fsum(scales) != 1.0:
        raise M6PilotError("microbatch_arithmetic_invalid", "applied float scales do not sum to one")
    return scales


def assert_pilot_arithmetic():
    windows = accumulation_windows()
    for window in windows:
        weights = example_weighted_contributions(window)
        scales = applied_float_scales(window)
        if sum(weights, Fraction(0)) != 1 or math.fsum(scales) != 1.0:
            raise M6PilotError("microbatch_arithmetic_invalid", "a window does not sum to one")
    return {
        "microbatches": MICROBATCH_COUNT,
        "optimizer_updates": OPTIMIZER_UPDATES,
        "final_window": FINAL_WINDOW,
        "final_window_examples": FINAL_WINDOW_EXAMPLES,
        "final_weights": example_weighted_contributions(FINAL_WINDOW),
    }


def clip_pre_clip_norm(norm, threshold=GRADIENT_CLIP_NORM):
    """Clip a finite norm above 1.0. A finite norm is not an abort."""
    number = _finite_float(norm, "non_finite_pre_clip_gradient_norm")
    if number < 0.0:
        raise M6PilotError("non_finite_pre_clip_gradient_norm", "gradient norm is negative")
    clipped = number > threshold
    return {
        "pre_clip_gradient_norm": number,
        "applied_norm": threshold if clipped else number,
        "clipped": clipped,
        "abort": False,
        "threshold": threshold,
    }


def assert_finite_training_loss(value):
    return _finite_float(value, "non_finite_training_loss")


def assert_finite_gradients(finite):
    if finite is not True:
        raise M6PilotError("non_finite_trainable_gradient", "a trainable gradient is not finite")
    return True


def assert_finite_validation(pair_losses):
    values = [item for batch in pair_losses for item in batch] if pair_losses and isinstance(pair_losses[0], (list, tuple)) else list(pair_losses)
    if len(values) != VALIDATION_PAIR_COUNT:
        raise M6PilotError("non_finite_validation", "validation did not contain 380 pair losses")
    return [_finite_float(value, "non_finite_validation") for value in values]


def aggregate_pair_mse(pair_losses):
    """Equal weight per pair. Unequal batch sizes must not become equal batch weights."""
    flat = assert_finite_validation(pair_losses)
    return math.fsum(flat) / float(VALIDATION_PAIR_COUNT)


def equal_batch_mean(pair_batches):
    """The prohibited aggregator. Exposed so tests can show it differs."""
    if not pair_batches:
        raise M6PilotError("non_finite_validation", "validation batches are empty")
    means = []
    for batch in pair_batches:
        if not batch:
            raise M6PilotError("non_finite_validation", "a validation batch is empty")
        means.append(math.fsum(float(value) for value in batch) / float(len(batch)))
    return math.fsum(means) / float(len(means))


def assert_validation_source(source):
    source = _require_mapping(source, "identity_mismatch", "validation source is missing")
    if source.get("loaded_from_accepted_artifacts") is not True or source.get("regenerated") is not False:
        raise M6PilotError("identity_mismatch", "validation tensors must be loaded and must not be regenerated")
    if tuple(source.get("timestep_shape", ())) != VALIDATION_TIMESTEP_SHAPE:
        raise M6PilotError("identity_mismatch", "validation timestep shape drifted")
    if tuple(source.get("noise_shape", ())) != VALIDATION_NOISE_SHAPE:
        raise M6PilotError("identity_mismatch", "validation noise shape drifted")
    if source.get("timestep_sha256") != VALIDATION_TIMESTEPS_SHA256 or source.get("noise_sha256") != VALIDATION_NOISE_SHA256:
        raise M6PilotError("identity_mismatch", "validation tensor hash drifted")
    if source.get("seed") != VALIDATION_DRAW_SEED:
        raise M6PilotError("identity_mismatch", "validation draw seed drifted")
    return True


def validation_updates_for(update_number):
    if update_number not in VALIDATION_UPDATES:
        raise M6PilotError("validation_schedule_invalid", "validation is only defined at updates 0, 7, 14, and 21")
    return True


def classify_validation_change(initial, later, update):
    if update not in (7, 14, 21):
        raise M6PilotError("validation_schedule_invalid", "relative validation is recorded at updates 7, 14, and 21")
    start = _finite_float(initial, "non_finite_validation")
    value = _finite_float(later, "non_finite_validation")
    worsened = value > start
    return {
        "update": update,
        "initial": format_decimal(start),
        "later": format_decimal(value),
        "delta": format_decimal(value - start),
        "finite_worsening": worsened,
        "human_review_signal": worsened,
        "automatic_early_stop": False,
        "automatic_learning_rate_change": False,
        "numeric_cutoff": None,
    }


def resolve_learning_rate(request_reduction):
    if request_reduction:
        raise M6PilotError("automatic_lr_change_rejected", "there is no automatic reduction to 1e-5 and no learning-rate sweep")
    return BASE_LEARNING_RATE


def assert_encdec_frozen(snapshot):
    snapshot = _require_mapping(snapshot, "modified_or_trainable_encdec", "EncDec snapshot is missing")
    if set(snapshot) != set(ENCDEC_COMPONENTS):
        raise M6PilotError("modified_or_trainable_encdec", "EncDec snapshot does not cover the complete frozen model")
    for name in ENCDEC_COMPONENTS:
        component = _require_mapping(snapshot[name], "modified_or_trainable_encdec", name + " snapshot is missing")
        if component.get("requires_grad") is not False or component.get("trainable_count") != 0 or component.get("changed") is not False:
            raise M6PilotError("modified_or_trainable_encdec", name + " is trainable or changed")
    return True


def assert_optimizer_membership(members):
    members = _require_mapping(members, "modified_or_trainable_encdec", "optimizer membership is missing")
    denoiser = members.get("denoiser_parameter_names")
    encdec = members.get("encdec_parameter_names")
    optimizer = members.get("optimizer_parameter_names")
    if not isinstance(denoiser, (list, tuple)) or not isinstance(encdec, (list, tuple)) or not isinstance(optimizer, (list, tuple)):
        raise M6PilotError("modified_or_trainable_encdec", "parameter-name lists are required")
    if not denoiser or not encdec:
        raise M6PilotError("modified_or_trainable_encdec", "denoiser and EncDec parameter names are required")
    if set(optimizer) != set(denoiser):
        raise M6PilotError("modified_or_trainable_encdec", "the optimizer is not exactly the denoiser")
    if set(optimizer) & set(encdec):
        raise M6PilotError("modified_or_trainable_encdec", "an EncDec parameter is in the optimizer")
    return True


def assert_denoiser_changed(before_digest, after_digest, applied_lr):
    if applied_lr == 0.0:
        raise M6PilotError("learning_rate_zero_applied", "a zero learning rate is not an applied update")
    if not _is_sha256(before_digest) or not _is_sha256(after_digest):
        raise M6PilotError("no_observed_denoiser_change", "denoiser digests must be SHA-256")
    if before_digest == after_digest:
        raise M6PilotError("no_observed_denoiser_change", "the denoiser did not change after a nonzero learning-rate update")
    return True


def selection_eligibility(update):
    if update in LEARNING_CURVE_ONLY_UPDATES:
        return {
            "update": update,
            "eligible": False,
            "reason": "learning_curve_evidence_only_not_selectable_from_validation_loss_alone",
        }
    if update == 0:
        return {"update": 0, "eligible": False, "reason": "immutable_b1_reference_not_a_saved_pilot_checkpoint"}
    if update == OPTIMIZER_UPDATES:
        return {
            "update": update,
            "eligible": False,
            "reason": "final_pilot_state_is_not_selected_by_validation_loss_alone_and_diagnostics_are_not_authorised",
        }
    raise M6PilotError("validation_schedule_invalid", "update is outside the pilot retention schedule")


def diagnostic_guardrail_consequence(failed):
    """Guardrails apply only after a later diagnostic authorisation."""
    return {
        "applied_during_training": False,
        "requires_separate_authorisation": True,
        "failed": bool(failed),
        "eligible_for_m7": False if failed else None,
        "automatic_rerun": False,
        "automatic_learning_rate_fallback": False,
        "nearest_train_similarity": "report_only_no_approved_threshold",
        "status": DIAGNOSTIC_GENERATION_STATUS,
    }


def normalize_generated_output(raw):
    """Exact-``11`` normalizer. The raw string is always retained unchanged.

    M5's single leading ``1`` came from direct ``EncDec.generate`` defaults.
    That observation does not broaden this B1/M6 rule.
    """
    if not isinstance(raw, str):
        raise M6PilotError("unexpected_output_normalization", "raw output must be a string")
    record = {
        "policy": NORMALIZATION_POLICY,
        "raw_string": raw,
        "removed_prefix": None,
        "normalized_string": None,
        "raw_length": len(raw),
        "normalized_length": None,
        "failure_reason": None,
        "accepted": False,
    }
    if not raw.startswith(M6_REQUIRED_RAW_PREFIX):
        record["failure_reason"] = "leading_prefix_not_exact_11"
        return record
    body = raw[len(M6_REQUIRED_RAW_PREFIX):]
    record["removed_prefix"] = M6_REQUIRED_RAW_PREFIX
    if body == "":
        record["failure_reason"] = "empty_body"
        return record
    if BODY_PATTERN.fullmatch(body) is None:
        record["failure_reason"] = "body_not_exact_acgu"
        return record
    record["normalized_string"] = body
    record["normalized_length"] = len(body)
    record["accepted"] = True
    return record


def _normalise_path(path):
    return str(path).replace("\\", "/")


def path_is_ref_or_eval(path):
    text = _normalise_path(path)
    basename = text.rstrip("/").split("/")[-1]
    if basename in DENIED_BASENAMES:
        return True
    parts = [part for part in text.split("/") if part]
    return any(part in DENIED_ROLES for part in parts)


def path_is_obsolete_repository_local(path):
    text = _normalise_path(path)
    return any(marker in text for marker in OBSOLETE_PATH_MARKERS)


def consider_input_path(path, role, access_enabled, claimed_hash=None, opener=None):
    """Refuse forbidden inputs before ``opener`` is called."""
    if role in DENIED_ROLES or path_is_ref_or_eval(path):
        raise M6PilotError("ref_or_eval_access", "REF and EVAL are refused before open")
    if path_is_obsolete_repository_local(path):
        raise M6PilotError("unexpected_biological_path_or_role", "obsolete repository-local data is refused before open")
    if claimed_hash in DENIED_HASHES:
        raise M6PilotError("ref_or_eval_access", "a REF or EVAL hash is refused before open")
    if role not in {"TRAIN_TEXT", "VALIDATION_CSV", "VALIDATION_ARTIFACT"}:
        raise M6PilotError("unexpected_biological_path_or_role", "the role is not a pilot input")
    if access_enabled is not True:
        raise M6PilotError("execution_not_authorised", "biological and artifact paths are not enabled")
    allowed = {
        "TRAIN_TEXT": FUTURE_TRAIN_TEXT_PATH,
        "VALIDATION_CSV": FUTURE_VALIDATION_CSV_PATH,
        "VALIDATION_ARTIFACT": ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY,
    }
    if _normalise_path(path) != allowed[role]:
        raise M6PilotError("unexpected_biological_path_or_role", "the path is not the pinned pilot input")
    if opener is None:
        raise M6PilotError("execution_not_authorised", "no opener is available")
    return opener(path)


def permutation_digest(indices):
    if not isinstance(indices, (list, tuple)) or len(indices) != TRAIN_RECORD_COUNT:
        raise M6PilotError("identity_mismatch", "the TRAIN permutation must contain 669 indexes")
    if sorted(indices) != list(range(TRAIN_RECORD_COUNT)):
        raise M6PilotError("identity_mismatch", "the TRAIN permutation is not a permutation of 0..668")
    payload = ",".join(str(index) for index in indices).encode("ascii")
    return sha256_bytes(payload)


def interruption_policy():
    return {
        "resume_supported": False,
        "optimizer_moments_saved": False,
        "resumable_training_sidecar_saved": False,
        "interrupted_attempt_status": "failed",
        "interrupted_attempt_can_continue": False,
        "restart_requires_new_output_directory": True,
        "restart_requires_new_single_use_authorisation": True,
        "expected_retained_storage": "approximately_24_to_26_GB_without_optimizer_moments",
    }


def assert_restart_refused(same_output_directory, same_authorisation):
    if same_output_directory or same_authorisation:
        raise M6PilotError("authorization_reuse", "an interrupted attempt cannot continue; restart needs a new directory and a new single-use authorisation")
    return interruption_policy()


def refuse_existing_checkpoint_directory(exists):
    if exists:
        raise M6PilotError("checkpoint_overwrite_risk", "the checkpoint directory already exists")
    return True


def config_evidence_mapping(config):
    """Return the configuration mapping that is hashed as checkpoint evidence.

    Diffusers records the load location as top-level ``_name_or_path``. When the
    caller supplied a ``pathlib.Path``, Diffusers keeps that object, which JSON
    cannot encode. Only that one top-level key is converted, with ``os.fspath``,
    and the result must be ``str``. Every other value, including a nested
    ``_name_or_path``, is left unchanged, so an unencodable value elsewhere is
    still rejected when the mapping is hashed.
    """
    config = _require_mapping(config, "checkpoint_save_reload_incompatibility", "denoiser config must be a mapping")
    key = "_name_or_path"
    if key in config and isinstance(config[key], os.PathLike):
        try:
            text = os.fspath(config[key])
        except Exception:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "denoiser configuration load location cannot be converted to a string")
        if type(text) is not str:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "denoiser configuration load location is not a string")
        converted = dict(config)
        converted[key] = text
        return converted
    return config


def _config_sha256(config):
    try:
        return sha256_bytes(canonical_json(config))
    except (TypeError, ValueError, OverflowError):
        raise M6PilotError("checkpoint_save_reload_incompatibility", "denoiser configuration is not JSON-serializable evidence")


def normalized_config_sha256(config):
    config = config_evidence_mapping(config)
    copied = {key: value for key, value in config.items() if key not in CONFIGURATION_IGNORED_TOP_LEVEL_KEYS}
    return _config_sha256(copied)


STATE_DIGEST_CHUNK_BYTES = 64 * 1024 * 1024


def _is_tensor(value):
    """Recognise a torch tensor, including a subclass such as ``Parameter``.

    A subclass must not fall through to the ``repr`` digest, which summarises
    large tensors. Duck-typed objects named ``Tensor`` keep their earlier
    acceptance for the CPU stand-ins.
    """
    import sys

    torch = sys.modules.get("torch")
    tensor_class = getattr(torch, "Tensor", None)
    if isinstance(tensor_class, type) and isinstance(value, tensor_class):
        return True
    return type(value).__name__ == "Tensor" and hasattr(value, "dtype") and hasattr(value, "shape") and hasattr(value, "detach")


def _tensor_cpu_byte_chunks(value, chunk_bytes=STATE_DIGEST_CHUNK_BYTES):
    """Yield the logical row-major bytes of a tensor without copying its storage.

    This is the byte sequence the earlier ``bytes(untyped_storage())`` slice
    produced: the contiguous CPU tensor's storage, from its storage offset, for
    ``nbytes``. A uint8 view over that same storage is hashed in bounded chunks.
    Iterating ``bytes(untyped_storage())`` costs a Python-level step per byte,
    and it materialised the complete backing storage even for a small view.
    """
    import sys

    cpu = value.detach().to(device="cpu").contiguous()
    size = int(cpu.nbytes)
    if size == 0:
        return
    torch = sys.modules.get("torch")
    if torch is None or not hasattr(torch, "empty"):
        raise M6PilotError("checkpoint_save_reload_incompatibility", "tensor digest requires torch")
    offset = int(cpu.storage_offset()) * int(cpu.element_size())
    raw = torch.empty(0, dtype=torch.uint8).set_(cpu.untyped_storage(), offset, (size,), (1,))
    buffer = raw.numpy()
    for start in range(0, size, chunk_bytes):
        yield memoryview(buffer[start:start + chunk_bytes])


def state_entry_digest(name, value):
    """Digest one state entry from its name, kind, dtype, shape, and bytes."""
    if _is_tensor(value):
        payload = {
            "dtype": str(value.dtype),
            "kind": "tensor",
            "name": name,
            "shape": [int(dim) for dim in value.shape],
        }
        hasher = hashlib.sha256()
        hasher.update(canonical_json(payload))
        for chunk in _tensor_cpu_byte_chunks(value):
            hasher.update(chunk)
        return hasher.hexdigest()
    if isinstance(value, (str, int, float, bool)) or value is None:
        encoded = value
    else:
        encoded = repr(value)
    payload = {"kind": "value", "name": name, "type": type(value).__name__, "value": encoded}
    return sha256_bytes(canonical_json(payload))


def _tensors_equal(left, right):
    import sys

    torch = sys.modules.get("torch")
    if torch is None or not hasattr(torch, "equal"):
        raise M6PilotError("checkpoint_save_reload_incompatibility", "tensor comparison requires torch.equal")
    if str(getattr(left, "device", "")) != str(getattr(right, "device", "")):
        right = right.detach().to(device=left.device)
    return bool(torch.equal(left, right))


def _state_values_equal(left, right):
    left_tensor = _is_tensor(left)
    right_tensor = _is_tensor(right)
    if left_tensor != right_tensor:
        return False
    if not left_tensor:
        return left == right
    if str(left.dtype) != str(right.dtype) or tuple(int(dim) for dim in left.shape) != tuple(int(dim) for dim in right.shape):
        return False
    return _tensors_equal(left, right)


def state_inventory_digests(entry_digests):
    """Recompute the ordered aggregate and parameter-name digests from entry digests."""
    entry_digests = _require_mapping(entry_digests, "checkpoint_save_reload_incompatibility", "checkpoint entry digests are missing")
    if not entry_digests:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint entry digests are incomplete")
    for name in entry_digests:
        if not isinstance(name, str) or name == "":
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint entry name is missing")
    inventory = [{"digest": entry_digests[name], "name": name} for name in sorted(entry_digests)]
    names = "\n".join(sorted(entry_digests)).encode("utf-8")
    return {
        "aggregate_digest": sha256_bytes(canonical_json(inventory)),
        "parameter_names_sha256": sha256_bytes(names),
    }


def compare_complete_denoiser_state(original, reloaded, selection="complete"):
    if selection != "complete":
        raise M6PilotError("checkpoint_save_reload_incompatibility", "weight comparison must cover the complete denoiser state")
    original = _require_mapping(original, "checkpoint_save_reload_incompatibility", "original state is missing")
    reloaded = _require_mapping(reloaded, "checkpoint_save_reload_incompatibility", "reloaded state is missing")
    if len(original) < 4:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "refusing a comparison smaller than a complete synthetic state")
    if set(original) != set(reloaded):
        raise M6PilotError("checkpoint_save_reload_incompatibility", "original and reloaded parameter names differ")
    entry_digests = {}
    for name in sorted(original):
        left = original[name]
        right = reloaded[name]
        if _is_tensor(left) != _is_tensor(right):
            raise M6PilotError("checkpoint_save_reload_incompatibility", "tensor and non-tensor state entries differ: " + name)
        if _is_tensor(left):
            if str(left.dtype) != str(right.dtype):
                raise M6PilotError("checkpoint_save_reload_incompatibility", "state dtype mismatch: " + name)
            if tuple(int(dim) for dim in left.shape) != tuple(int(dim) for dim in right.shape):
                raise M6PilotError("checkpoint_save_reload_incompatibility", "state shape mismatch: " + name)
            if not _tensors_equal(left, right):
                raise M6PilotError("checkpoint_save_reload_incompatibility", "denoiser state mismatch: " + name)
        elif left != right:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "denoiser state mismatch: " + name)
        digest = state_entry_digest(name, left)
        if digest != state_entry_digest(name, right):
            raise M6PilotError("checkpoint_save_reload_incompatibility", "state digest mismatch: " + name)
        entry_digests[name] = digest
    inventory = state_inventory_digests(entry_digests)
    return {
        "aggregate_digest": inventory["aggregate_digest"],
        "compared_parameter_count": len(original),
        "comparison_selection": "complete",
        "complete_state_equal": True,
        "entry_digests": entry_digests,
        "mismatched_parameter_count": 0,
        "parameter_names_sha256": inventory["parameter_names_sha256"],
        "includes_persistent_buffers": True,
        "tensor_comparison": "torch.equal" if any(_is_tensor(value) for value in original.values()) else "exact_value",
        "weight_reload_is_training_resume": False,
    }


def observe_checkpoint_tree(checkpoint_dir):
    """Require the exact checkpoint tree with ``lstat`` and return leaf signatures.

    The root and each expected intermediate directory must be a real directory,
    not a symlink. Each expected leaf must be a regular non-symlink file. A
    missing member, an extra entry of any kind, or a special file fails. Messages
    do not name the offending entry. The signature of each leaf (size, mtime,
    inode, device) lets a later call detect a change.
    """
    import stat

    def kind(path):
        try:
            return os.lstat(path)
        except FileNotFoundError:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint tree is missing a member")

    root = kind(checkpoint_dir)
    if not stat.S_ISDIR(root.st_mode):
        raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint root is not a real directory")
    expected = {}
    for member in CHECKPOINT_MEMBERS:
        head, _, tail = member.rpartition("/")
        expected.setdefault(head, []).append(tail)
    top = set(expected.get("", [])) | {name for name in expected if name != ""}
    if set(os.listdir(checkpoint_dir)) != top:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint tree has an unexpected or missing entry")
    signatures = {}
    for head in sorted(expected):
        base = checkpoint_dir if head == "" else os.path.join(checkpoint_dir, head)
        if head != "":
            if not stat.S_ISDIR(kind(base).st_mode):
                raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint subdirectory is not a real directory")
            if set(os.listdir(base)) != set(expected[head]):
                raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint subdirectory has an unexpected or missing entry")
        for leaf in expected[head]:
            measured = kind(os.path.join(base, leaf))
            if not stat.S_ISREG(measured.st_mode):
                raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint member is not a regular file")
            member = leaf if head == "" else head + "/" + leaf
            signatures[member] = (int(measured.st_size), int(measured.st_mtime_ns), int(measured.st_ino), int(measured.st_dev))
    return signatures


def assert_checkpoint_inventory(saved_hashes):
    saved_hashes = _exact_keys(saved_hashes, CHECKPOINT_MEMBERS, "checkpoint_save_reload_incompatibility")
    for name in CHECKPOINT_MEMBERS:
        if not _is_sha256(saved_hashes[name]):
            raise M6PilotError("checkpoint_save_reload_incompatibility", "saved member hash is missing: " + name)
    return dict(saved_hashes)


def assert_configuration_compatible(original_config, reloaded_config):
    ignored = list(CONFIGURATION_IGNORED_TOP_LEVEL_KEYS)
    if ignored != ["_name_or_path"]:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "configuration allowlist drifted")
    original_config = config_evidence_mapping(original_config)
    reloaded_config = config_evidence_mapping(reloaded_config)
    original_raw = _config_sha256(original_config)
    reloaded_raw = _config_sha256(reloaded_config)
    original_norm = normalized_config_sha256(original_config)
    reloaded_norm = normalized_config_sha256(reloaded_config)
    compatible = original_norm == reloaded_norm
    record = {
        "ignored_top_level_keys": ignored,
        "original_raw_sha256": original_raw,
        "reloaded_raw_sha256": reloaded_raw,
        "raw_sha256_equal": original_raw == reloaded_raw,
        "original_normalized_sha256": original_norm,
        "reloaded_normalized_sha256": reloaded_norm,
        "normalized_sha256_equal": compatible,
        "configuration_compatible": compatible,
    }
    if not compatible:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "reloaded denoiser configuration is incompatible")
    return record


def prove_weight_reload(proof, stage_hook=None):
    """Validate a checkpoint reload proof, cheapest checks first.

    The order is proof structure and fresh-object identity, update and checkpoint
    inventory, configuration compatibility, then the complete state comparison
    and digests. A configuration failure therefore never pays for the state
    comparison. ``stage_hook``, when given, is called with the substage name
    before the configuration and state proofs.
    """
    proof = _require_mapping(proof, "checkpoint_save_reload_incompatibility", "reload proof is missing")
    if proof.get("fresh_object_constructed") is not True:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "reload did not construct a fresh object")
    if proof.get("original_object_id") == proof.get("reloaded_object_id"):
        raise M6PilotError("checkpoint_save_reload_incompatibility", "reload reused the training object")
    if proof.get("labelled_as_resume") is not False:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "weight reload must not be labelled as training resume")
    if proof.get("update") not in RETAINED_WEIGHT_UPDATES:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "weight checkpoints are only retained at updates 7, 14, and 21")
    if proof.get("update") == 0:
        raise M6PilotError("checkpoint_overwrite_risk", "update 0 must reference immutable B1 and must not copy it")
    inventory = assert_checkpoint_inventory(proof.get("saved_hashes"))
    if stage_hook is not None:
        stage_hook("checkpoint_config_proof")
    configuration = assert_configuration_compatible(proof.get("original_config"), proof.get("reloaded_config"))
    if stage_hook is not None:
        stage_hook("checkpoint_state_proof")
    comparison = compare_complete_denoiser_state(proof.get("original_state"), proof.get("reloaded_state"), proof.get("selection", "complete"))
    return {
        "configuration": configuration,
        "fresh_load_succeeded": True,
        "original_object_id": proof["original_object_id"],
        "reloaded_object_id": proof["reloaded_object_id"],
        "resume_supported": False,
        "saved_hashes": inventory,
        "state_comparison": comparison,
        "state_scope": "parameters_and_persistent_buffers",
        "update": proof["update"],
        "weight_reload_is_training_resume": False,
    }


def _stop_record(fired=None):
    fired = {} if fired is None else fired
    unknown = set(fired) - set(STOP_CONDITION_CODES)
    if unknown:
        raise M6PilotError("incomplete_evidence_or_manifest", "unknown stop condition")
    return {code: {"fired": bool(fired.get(code, False))} for code in STOP_CONDITION_CODES}


def _reject_sequence_text(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in SEQUENCE_TEXT_KEYS:
                raise M6PilotError("incomplete_evidence_or_manifest", "training manifest contains sequence text")
            _reject_sequence_text(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_sequence_text(item)
    elif isinstance(value, str) and BODY_PATTERN.fullmatch(value) is not None and len(value) >= 8:
        raise M6PilotError("incomplete_evidence_or_manifest", "training manifest contains sequence text")


def validate_success_manifest(manifest):
    manifest = _exact_keys(manifest, MANIFEST_KEYS, "incomplete_evidence_or_manifest")
    _reject_sequence_text(manifest)
    if manifest["manifest_schema_version"] != MANIFEST_SCHEMA_VERSION or manifest["schema_version"] != SCHEMA_VERSION:
        raise M6PilotError("incomplete_evidence_or_manifest", "manifest schema drifted")
    if manifest["experiment_id"] != EXPERIMENT_ID or manifest["config_version"] != SCHEMA_VERSION:
        raise M6PilotError("incomplete_evidence_or_manifest", "experiment identity drifted")
    if manifest["completion_state"] != "synthetic_control_flow_completed" or manifest["failure_state"] is not None:
        raise M6PilotError("incomplete_evidence_or_manifest", "the synthetic validator only accepts synthetic_control_flow_completed")
    if manifest["production_identities"] is not False:
        raise M6PilotError("incomplete_evidence_or_manifest", "a synthetic manifest cannot claim production identities")
    if manifest["resume_supported"] is not False:
        raise M6PilotError("incomplete_evidence_or_manifest", "resume_supported must be false")
    if manifest["diagnostic_generation_status"] != DIAGNOSTIC_GENERATION_STATUS:
        raise M6PilotError("diagnostic_generation_not_authorised", "diagnostic generation is separately gated")
    trace = manifest["applied_learning_rate_trace"]
    if trace != [format_decimal(value) for value in applied_learning_rate_trace()]:
        raise M6PilotError("incomplete_evidence_or_manifest", "manifest learning-rate trace drifted")
    post = _exact_keys(
        manifest["post_update_21_scheduler_position"],
        ("applied_to_optimizer", "multiplier", "position"),
        "incomplete_evidence_or_manifest",
    )
    if post["position"] != POST_UPDATE_POSITION or post["multiplier"] != "0" or post["applied_to_optimizer"] is not False:
        raise M6PilotError("incomplete_evidence_or_manifest", "post-update-21 scheduler position drifted")
    stops = _exact_keys(manifest["stop_conditions"], STOP_CONDITION_CODES, "incomplete_evidence_or_manifest")
    for code in STOP_CONDITION_CODES:
        _exact_keys(stops[code], ("fired",), "incomplete_evidence_or_manifest")
        if not isinstance(stops[code]["fired"], bool):
            raise M6PilotError("incomplete_evidence_or_manifest", "stop fired flag is not boolean")
    _require_closed_access(manifest)
    _validate_nested_manifest(manifest)
    return True


def _require_closed_access(manifest):
    roles = manifest["data_roles"]
    for role in ("train_text", "validation_csv", "validation_artifacts"):
        if roles[role]["opened"] is not False:
            raise M6PilotError("unexpected_biological_path_or_role", "synthetic manifest must not claim biological access")
    if roles["ref"]["opened"] is not False or roles["eval"]["opened"] is not False:
        raise M6PilotError("ref_or_eval_access", "REF or EVAL was opened")


def _validate_nested_manifest(manifest):
    _exact_keys(
        manifest["data_roles"],
        ("eval", "ref", "train_text", "validation_artifacts", "validation_csv"),
        "incomplete_evidence_or_manifest",
    )
    for role in manifest["data_roles"].values():
        _exact_keys(
            role,
            ("expected_count", "expected_sha256", "opened", "path_open_permitted", "role"),
            "incomplete_evidence_or_manifest",
        )
    _exact_keys(
        manifest["authorisation"],
        (
            "authorisation_id",
            "authorization_commit",
            "authorization_parent_commit",
            "consumption_state",
            "executing_implementation_commit",
            "reuse_permitted",
            "single_use",
        ),
        "incomplete_evidence_or_manifest",
    )
    if manifest["authorisation"]["reuse_permitted"] is not False or manifest["authorisation"]["single_use"] is not True:
        raise M6PilotError("authorization_reuse", "authorisation is not single-use")
    _exact_keys(
        manifest["gpu"],
        ("hardcoded_physical_index", "logical_device", "pci_bus", "physical_index", "uuid"),
        "incomplete_evidence_or_manifest",
    )
    if manifest["gpu"]["hardcoded_physical_index"] is not False:
        raise M6PilotError("identity_mismatch", "physical GPU must come from a later authorisation")
    if manifest["gpu"]["physical_index"] in (0, 1) and manifest["completion_state"] != "pilot_completed":
        raise M6PilotError("identity_mismatch", "an unbound manifest must not carry a physical GPU index")
    _exact_keys(
        manifest["ref_eval_access"],
        ("eval_hash_metadata_only", "eval_opened", "ref_hash_metadata_only", "ref_opened"),
        "incomplete_evidence_or_manifest",
    )
    if manifest["ref_eval_access"]["ref_opened"] is not False or manifest["ref_eval_access"]["eval_opened"] is not False:
        raise M6PilotError("ref_or_eval_access", "REF or EVAL access is recorded")
    _exact_keys(manifest["restart_policy"], tuple(interruption_policy().keys()), "incomplete_evidence_or_manifest")
    if manifest["restart_policy"]["resume_supported"] is not False:
        raise M6PilotError("incomplete_evidence_or_manifest", "restart policy drifted")
    observations = manifest["train_update_observations"]
    if not isinstance(observations, list) or [item["update"] for item in observations] != list(range(1, OPTIMIZER_UPDATES + 1)):
        raise M6PilotError("incomplete_evidence_or_manifest", "train observations are not updates 1 through 21")
    for item in observations:
        _exact_keys(
            item,
            (
                "applied_clip_norm",
                "clipped",
                "learning_rate",
                "learning_rate_recorded_before_optimizer_step",
                "pre_clip_gradient_norm",
                "stop_fired",
                "training_loss",
                "update",
            ),
            "incomplete_evidence_or_manifest",
        )
        if item["learning_rate_recorded_before_optimizer_step"] is not True or item["learning_rate"] == "0":
            raise M6PilotError("learning_rate_zero_applied", "an applied learning rate was not recorded before the step")
    validation = manifest["validation_observations"]
    if [item["update"] for item in validation] != list(VALIDATION_UPDATES):
        raise M6PilotError("validation_schedule_invalid", "validation observations are not updates 0, 7, 14, and 21")
    for item in validation:
        _exact_keys(
            item,
            (
                "aggregate_mse",
                "pair_count",
                "relative_to_update_0",
                "tensors_loaded",
                "tensors_regenerated",
                "update",
                "weight_variant",
            ),
            "incomplete_evidence_or_manifest",
        )
        if item["pair_count"] != VALIDATION_PAIR_COUNT or item["tensors_loaded"] is not True or item["tensors_regenerated"] is not False:
            raise M6PilotError("identity_mismatch", "validation observation did not load the fixed draws")
        if item["weight_variant"] != "raw":
            raise M6PilotError("identity_mismatch", "validation must use raw denoiser weights")
    checkpoints = manifest["weight_checkpoints"]
    if [item["update"] for item in checkpoints] != list(RETAINED_WEIGHT_UPDATES):
        raise M6PilotError("checkpoint_save_reload_incompatibility", "retained checkpoints are not updates 7, 14, and 21")
    if any(item["update"] == 0 for item in checkpoints):
        raise M6PilotError("checkpoint_overwrite_risk", "update 0 must not be copied")
    for item in checkpoints:
        if item["weight_reload_is_training_resume"] is not False or item["state_comparison"]["comparison_selection"] != "complete":
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint reload is not a complete non-resume proof")
        if item["state_comparison"]["compared_parameter_count"] < 4:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint comparison is not complete")
    review = manifest["validation_review"]
    if review["numeric_catastrophic_cutoff"] is not None or review["automatic_early_stop"] is not False:
        raise M6PilotError("automatic_lr_change_rejected", "validation worsening is not an automatic stop")
    if review["automatic_learning_rate_change"] is not False:
        raise M6PilotError("automatic_lr_change_rejected", "validation worsening must not change the learning rate")
    for item in review["observations"]:
        if item.get("automatic_early_stop") is not False or item.get("automatic_learning_rate_change") is not False:
            raise M6PilotError("automatic_lr_change_rejected", "a finite validation change must not stop or retune the run")
        if item.get("numeric_cutoff") is not None:
            raise M6PilotError("automatic_lr_change_rejected", "no numeric catastrophic validation cutoff is defined")
    return True


def directory_creation_allowed(path):
    """Inactive package: tests may use a temporary directory; repositories and the run root are closed."""
    real = os.path.realpath(path)
    for root in (RUN_ROOT, MRES_ROOT, RNAGENESIS_ROOT):
        root_real = os.path.realpath(root)
        if real == root_real or real.startswith(root_real + os.sep):
            raise M6PilotError("execution_not_authorised", "refusing to create a directory inside a repository or the run root")
    return True


def assert_checkpoint_child(path, bound_output):
    """A retained checkpoint directory is an exclusive direct child of the bound output."""
    child = os.path.abspath(path)
    parent = os.path.abspath(bound_output)
    if os.path.dirname(child) != parent:
        raise M6PilotError("checkpoint_overwrite_risk", "checkpoint directory is not a direct child of the bound output")
    if os.path.islink(child) or os.path.islink(parent):
        raise M6PilotError("checkpoint_overwrite_risk", "checkpoint path contains a symlink")
    if os.path.lexists(child):
        raise M6PilotError("checkpoint_overwrite_risk", "the checkpoint directory already exists")
    return child


def create_checkpoint_directory_exclusive(path, bound_output=None):
    if bound_output is None:
        directory_creation_allowed(path)
    else:
        assert_checkpoint_child(path, bound_output)
    if os.path.lexists(path):
        raise M6PilotError("checkpoint_overwrite_risk", "refusing to overwrite an existing checkpoint directory")
    os.mkdir(path)
    return path


def b1_reference_at_update_0():
    return {
        "update": 0,
        "copied": False,
        "identity": "immutable_B1_generic_diffusion_checkpoint",
        "relative_path": "configs/rnagenesis/diffusion",
        "weight_sha256": B1_WEIGHT_SHA256,
        "weight_bytes": B1_WEIGHT_BYTES,
    }


def _role(role, expected_sha256, expected_count, opened):
    return {
        "expected_count": expected_count,
        "expected_sha256": expected_sha256,
        "opened": opened,
        "path_open_permitted": False,
        "role": role,
    }


def build_control_flow_manifest(snapshot):
    """Assemble the synthetic control-flow manifest from runner observations.

    This is not a biological-run manifest. Production completion stays closed.
    """
    snapshot = _require_mapping(snapshot, "incomplete_evidence_or_manifest", "control-flow snapshot is missing")
    if snapshot.get("opened_biological_data") is not False:
        raise M6PilotError("unexpected_biological_path_or_role", "the inactive control flow must not open biological data")
    train_rows = []
    for item in snapshot["train_updates"]:
        train_rows.append(
            {
                "applied_clip_norm": format_decimal(item["applied_norm"]),
                "clipped": item["clipped"],
                "learning_rate": format_decimal(item["learning_rate"]),
                "learning_rate_recorded_before_optimizer_step": True,
                "pre_clip_gradient_norm": format_decimal(item["pre_clip_gradient_norm"]),
                "stop_fired": False,
                "training_loss": format_decimal(item["training_loss"]),
                "update": item["update"],
            }
        )
    manifest = {
        "applied_learning_rate_trace": [format_decimal(value) for value in applied_learning_rate_trace()],
        "authorisation": {
            "authorisation_id": None,
            "authorization_commit": None,
            "authorization_parent_commit": None,
            "consumption_state": "not_issued",
            "executing_implementation_commit": None,
            "reuse_permitted": False,
            "single_use": True,
        },
        "b1_identity": {
            "copied_at_update_0": False,
            "initialization": "immutable_B1_generic_diffusion_checkpoint",
            "unet_config_sha256": B1_UNET_CONFIG_SHA256,
            "weight_bytes": B1_WEIGHT_BYTES,
            "weight_sha256": B1_WEIGHT_SHA256,
        },
        "completion_state": "synthetic_control_flow_completed",
        "config_version": SCHEMA_VERSION,
        "data_roles": {
            "eval": _role("EVAL", EVAL_HASH_METADATA, None, False),
            "ref": _role("REF", REF_HASH_METADATA, None, False),
            "train_text": _role("TRAIN_TEXT", TRAIN_TEXT_SHA256, TRAIN_RECORD_COUNT, False),
            "validation_artifacts": _role("VALIDATION_ARTIFACT", VALIDATION_DRAW_MANIFEST_SHA256, VALIDATION_PAIR_COUNT, False),
            "validation_csv": _role("VALIDATION_CSV", VALIDATION_CSV_SHA256, VALIDATION_SEQUENCE_COUNT, False),
        },
        "denoiser_update_evidence": {
            "any_unchanged_after_nonzero_lr": False,
            "applied_updates_checked": OPTIMIZER_UPDATES,
            "checked_after_each_applied_update": True,
        },
        "deviations": [],
        "diagnostic_generation_status": DIAGNOSTIC_GENERATION_STATUS,
        "environment": {
            "bytecode_disabled": True,
            "datasets_offline": True,
            "expected_python": "3.8.13",
            "hub_offline": True,
            "package_versions_observed": None,
            "package_versions_observed_reason": "not_observed_because_execution_is_not_authorised",
            "pinned_python": PINNED_PYTHON,
            "transformers_offline": True,
        },
        "experiment_id": EXPERIMENT_ID,
        "failure_state": None,
        "frozen_state": {
            "all_frozen": True,
            "components": list(ENCDEC_COMPONENTS),
            "optimizer_contains_encdec": False,
            "optimizer_contains_only_denoiser": True,
        },
        "gpu": {
            "hardcoded_physical_index": False,
            "logical_device": None,
            "pci_bus": None,
            "physical_index": None,
            "uuid": None,
        },
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "memory": {
            "peak_allocated_bytes": snapshot["peak_allocated_bytes"],
            "peak_reserved_bytes": snapshot["peak_reserved_bytes"],
        },
        "microbatch_accounting": {
            "drop_last": False,
            "final_window_examples": FINAL_WINDOW_EXAMPLES,
            "final_window_microbatch_sizes": list(FINAL_WINDOW),
            "final_window_weight_denominator": FINAL_WINDOW_EXAMPLES,
            "final_window_weight_numerators": list(FINAL_WINDOW),
            "final_window_weights_sum_to_one": True,
            "full_window_examples": INTENDED_EFFECTIVE_BATCH,
            "gradient_accumulation": GRADIENT_ACCUMULATION,
            "intended_effective_batch": INTENDED_EFFECTIVE_BATCH,
            "microbatch_count": MICROBATCH_COUNT,
            "optimizer_updates": OPTIMIZER_UPDATES,
            "physical_microbatch": PHYSICAL_MICROBATCH,
            "train_records": TRAIN_RECORD_COUNT,
        },
        "optimizer": {
            "automatic_learning_rate_reduction_to_1e-5": False,
            "beta1": format_decimal(ADAMW_BETA1),
            "beta2": format_decimal(ADAMW_BETA2),
            "diffusers_cosine_constructor_used": False,
            "ema_enabled": False,
            "epsilon": format_decimal(ADAMW_EPSILON),
            "gradient_clip_norm": format_decimal(GRADIENT_CLIP_NORM),
            "learning_rate": format_decimal(BASE_LEARNING_RATE),
            "learning_rate_sweep": False,
            "name": "AdamW",
            "weight_decay": format_decimal(ADAMW_WEIGHT_DECAY),
            "weight_variant": "raw",
        },
        "post_update_21_scheduler_position": {
            "applied_to_optimizer": False,
            "multiplier": format_decimal(post_update_scheduler_position()["multiplier"]),
            "position": POST_UPDATE_POSITION,
        },
        "production_identities": False,
        "ref_eval_access": {
            "eval_hash_metadata_only": EVAL_HASH_METADATA,
            "eval_opened": False,
            "ref_hash_metadata_only": REF_HASH_METADATA,
            "ref_opened": False,
        },
        "repository": {
            "mres_base_commit": MRES_BASE_COMMIT,
            "mres_index_clean": True,
            "mres_tracked_clean": True,
            "rnagenesis_branch": RNAGENESIS_BRANCH,
            "rnagenesis_commit": RNAGENESIS_COMMIT,
            "rnagenesis_tracked_clean": True,
            "rnagenesis_untracked_preserved": True,
        },
        "restart_policy": interruption_policy(),
        "resume_supported": False,
        "rng": {
            "seeds_differ": PILOT_SEED != VALIDATION_DRAW_SEED,
            "train_permutation_device": "cpu",
            "train_permutation_digest": snapshot["train_permutation_digest"],
            "train_permutation_generator": "dedicated_cpu_generator",
            "train_permutation_seed": PILOT_SEED,
            "validation_artifacts_regenerated": False,
            "validation_draw_seed": VALIDATION_DRAW_SEED,
        },
        "run_id": None,
        "schema_version": SCHEMA_VERSION,
        "stop_conditions": _stop_record(),
        "timing": {
            "training_seconds": format_decimal(snapshot["training_seconds"]),
            "validation_seconds": format_decimal(snapshot["validation_seconds"]),
        },
        "train_update_observations": train_rows,
        "validation_artifacts": {
            "draw_manifest_sha256": VALIDATION_DRAW_MANIFEST_SHA256,
            "draws": VALIDATION_DRAWS,
            "noise_sha256": VALIDATION_NOISE_SHA256,
            "noise_shape": list(VALIDATION_NOISE_SHAPE),
            "order_artifact_sha256": VALIDATION_ORDER_ARTIFACT_SHA256,
            "sequence_count": VALIDATION_SEQUENCE_COUNT,
            "sequence_order_sha256": VALIDATION_SEQUENCE_ORDER_SHA256,
            "timestep_sha256": VALIDATION_TIMESTEPS_SHA256,
            "timestep_shape": list(VALIDATION_TIMESTEP_SHAPE),
            "validation_csv_sha256": VALIDATION_CSV_SHA256,
        },
        "validation_observations": snapshot["validation_observations"],
        "validation_review": {
            "automatic_early_stop": False,
            "automatic_learning_rate_change": False,
            "numeric_catastrophic_cutoff": None,
            "observations": snapshot["validation_review_observations"],
        },
        "warnings": ["synthetic_control_flow_did_not_open_biological_data_or_load_a_model"],
        "weight_checkpoints": snapshot["weight_checkpoints"],
    }
    validate_success_manifest(manifest)
    return manifest


CONFIGURATION_ROOT_KEYS = (
    "checkpoints",
    "condition_manifest_label",
    "consumable_by_executable_workflow",
    "created_against_mres_commit",
    "data",
    "diagnostic_generation",
    "document_status",
    "execution",
    "experiment_id",
    "historical_m4_stage1_approval",
    "manifest_schema_version",
    "model",
    "pilot_decisions",
    "pilot_execution_authorisation",
    "rnagenesis_branch",
    "rnagenesis_commit",
    "schedule",
    "schema_version",
)
EXECUTION_KEYS = (
    "authorisation_id",
    "authorised",
    "authorization_parent_commit",
    "biological_paths_permitted",
    "evidence_directory",
    "executing_implementation_commit",
    "gpu_identity_bound",
    "output_directory",
)
SESSION_KEYS = (
    "consumption_event",
    "pattern",
    "resume_permitted",
    "wall_clock_expiry",
)
INACTIVE_AUTHORISATION_KEYS = (
    "activation_status",
    "authorisation_id",
    "authorisation_timestamp",
    "authorization_parent_commit",
    "b1_relative_path",
    "b1_unet_config_sha256",
    "b1_weight_sha256",
    "consumed",
    "evidence_directory",
    "executing_implementation_commit",
    "implementation_file_hashes",
    "logical_device",
    "output_directory",
    "permitted_roles",
    "phase",
    "reuse_permitted",
    "scope",
    "session",
    "single_use",
    "train_record_count",
    "train_text_path",
    "train_text_sha256",
    "validation_artifact_directory",
    "validation_artifact_sha256",
    "validation_csv_path",
    "validation_csv_sha256",
    "validation_record_count",
)
ACTIVE_AUTHORISATION_KEYS = INACTIVE_AUTHORISATION_KEYS + (
    "cuda_visible_devices",
    "gpu_uuid",
    "pci_bus",
    "physical_gpu_index",
)
INACTIVE_NULL_AUTHORISATION_FIELDS = (
    "authorisation_id",
    "authorisation_timestamp",
    "authorization_parent_commit",
    "b1_relative_path",
    "b1_unet_config_sha256",
    "b1_weight_sha256",
    "evidence_directory",
    "executing_implementation_commit",
    "implementation_file_hashes",
    "logical_device",
    "output_directory",
    "phase",
    "scope",
    "train_record_count",
    "train_text_path",
    "train_text_sha256",
    "validation_artifact_directory",
    "validation_artifact_sha256",
    "validation_csv_path",
    "validation_csv_sha256",
    "validation_record_count",
)
PERMITTED_ACTIVATION_PREFIXES = (
    "consumable_by_executable_workflow",
    "document_status",
    "execution.authorisation_id",
    "execution.authorised",
    "execution.authorization_parent_commit",
    "execution.biological_paths_permitted",
    "execution.evidence_directory",
    "execution.executing_implementation_commit",
    "execution.gpu_identity_bound",
    "execution.output_directory",
    "pilot_execution_authorisation",
)
VALIDATION_ARTIFACT_HASH_KEYS = (
    "draw_manifest",
    "noise",
    "order_artifact",
    "sequence_order",
    "timesteps",
)
EXPECTED_RNAGENESIS_SIGNATURES = {
    "accelerator_backward_scale": ("example_weight", "gradient_accumulation"),
    "assert_optimizer_membership": ("optimizer", "denoiser", "encdec"),
    "build_adamw": ("denoiser", "learning_rate"),
    "collate_sequences": ("examples", "tokenizer"),
    "denoising_mse": ("model", "scheduler", "latents", "noise", "timesteps", "dtype"),
    "extract_latents": ("encdec", "input_ids", "attention_mask"),
    "load_b1_denoiser": ("path",),
    "load_frozen_encdec": ("path",),
    "load_scheduler": ("diffusion_dir",),
    "load_tokenizer": (),
    "read_train_sequences": ("path", "enforce_frozen_hash"),
    "read_validation_cores": ("path", "enforce_frozen_hash"),
    "sample_train_diffusion": ("batch_size", "generator", "num_train_timesteps", "device"),
    "save_diffusers_checkpoint": ("denoiser", "scheduler", "directory"),
}
_AUTH_TOKEN = object()


class ValidatedActiveAuthorisation(object):
    """Runtime authorisation produced only by ``validate_active_execution``."""

    def __init__(self, payload, token):
        if token is not _AUTH_TOKEN:
            raise M6PilotError("execution_not_authorised", "active authorisation cannot be constructed directly")
        self.payload = payload

    def __getitem__(self, key):
        return self.payload[key]

    def get(self, key, default=None):
        return self.payload.get(key, default)


def classify_configuration(config):
    config = _require_mapping(config, "configuration_not_consumable", "configuration root must be a mapping")
    status = config.get("document_status")
    consumable = config.get("consumable_by_executable_workflow")
    if status == DOCUMENT_STATUS and consumable is False:
        return "inactive"
    if status == ACTIVE_DOCUMENT_STATUS and consumable is True:
        return "active"
    raise M6PilotError("configuration_not_consumable", "configuration is neither inactive nor a single-use active authorisation")


def assert_inactive_authorisation(block):
    block = _exact_keys(block, INACTIVE_AUTHORISATION_KEYS, "configuration_not_consumable")
    if block["activation_status"] != "inactive_no_authorisation" or block["consumed"] is not False:
        raise M6PilotError("configuration_not_consumable", "inactive authorisation must be unconsumed and inactive")
    if block["single_use"] is not True or block["reuse_permitted"] is not False or block["permitted_roles"] != []:
        raise M6PilotError("configuration_not_consumable", "inactive authorisation must stay closed")
    for key in INACTIVE_NULL_AUTHORISATION_FIELDS:
        if block[key] is not None:
            raise M6PilotError("configuration_not_consumable", key + " must be null")
    session = _exact_keys(block["session"], SESSION_KEYS, "configuration_not_consumable")
    if session["pattern"] != SESSION_PATTERN or session["wall_clock_expiry"] is not None:
        raise M6PilotError("configuration_not_consumable", "inactive session conditions drifted")
    if session["resume_permitted"] is not False or session["consumption_event"] is not None:
        raise M6PilotError("configuration_not_consumable", "inactive session must not permit resume or consumption")
    return True


def _sha40_text(value, code):
    if not _is_sha40(value):
        raise M6PilotError(code, "expected a lowercase SHA-1 commit")
    return value


def _pci_bus(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{8}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]", value) is None:
        raise M6PilotError("identity_mismatch", "PCI bus is not an exact device address")
    return value


def _gpu_uuid(value):
    if not isinstance(value, str) or re.fullmatch(r"GPU-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value) is None:
        raise M6PilotError("identity_mismatch", "GPU UUID is not exact")
    return value


def assert_output_directory_shape(path, run_root=RUN_ROOT):
    if not isinstance(path, str) or path != os.path.normpath(path):
        raise M6PilotError("execution_not_authorised", "output directory is not a normalised absolute path")
    prefix = run_root.rstrip("/") + "/"
    if not path.startswith(prefix):
        raise M6PilotError("execution_not_authorised", "output directory is not under the run root")
    name = path[len(prefix):]
    if name == "" or "/" in name or name in (".", ".."):
        raise M6PilotError("execution_not_authorised", "output directory is not a direct child of the run root")
    return name


def _authorisation_identities(block):
    if block["train_text_path"] != FUTURE_TRAIN_TEXT_PATH or block["train_text_sha256"] != TRAIN_TEXT_SHA256:
        raise M6PilotError("identity_mismatch", "TRAIN identity is not the pinned corpus")
    if block["train_record_count"] != TRAIN_RECORD_COUNT:
        raise M6PilotError("identity_mismatch", "TRAIN count is not 669")
    if block["validation_csv_path"] != FUTURE_VALIDATION_CSV_PATH or block["validation_csv_sha256"] != VALIDATION_CSV_SHA256:
        raise M6PilotError("identity_mismatch", "VALIDATION identity is not the pinned CSV")
    if block["validation_record_count"] != VALIDATION_SEQUENCE_COUNT:
        raise M6PilotError("identity_mismatch", "VALIDATION count is not 95")
    if block["validation_artifact_directory"] != ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY:
        raise M6PilotError("identity_mismatch", "validation artifact directory drifted")
    hashes = _exact_keys(block["validation_artifact_sha256"], VALIDATION_ARTIFACT_HASH_KEYS, "identity_mismatch")
    expected = {
        "draw_manifest": VALIDATION_DRAW_MANIFEST_SHA256,
        "noise": VALIDATION_NOISE_SHA256,
        "order_artifact": VALIDATION_ORDER_ARTIFACT_SHA256,
        "sequence_order": VALIDATION_SEQUENCE_ORDER_SHA256,
        "timesteps": VALIDATION_TIMESTEPS_SHA256,
    }
    for key, digest in expected.items():
        if hashes[key] != digest:
            raise M6PilotError("identity_mismatch", "validation artifact hash drifted: " + key)
    if block["b1_relative_path"] != B1_RELATIVE_PATH or block["b1_weight_sha256"] != B1_WEIGHT_SHA256:
        raise M6PilotError("identity_mismatch", "B1 identity drifted")
    if block["b1_unet_config_sha256"] != B1_UNET_CONFIG_SHA256:
        raise M6PilotError("identity_mismatch", "B1 configuration hash drifted")
    return True


def assert_active_authorisation_block(block, run_root=RUN_ROOT):
    block = _exact_keys(block, ACTIVE_AUTHORISATION_KEYS, "authorisation_shape_invalid")
    if _contains_key(block, "authorization_commit"):
        raise M6PilotError("authorisation_commit_invalid", "tracked authorisation must not store its own commit")
    if block["activation_status"] != "active_unconsumed" or block["consumed"] is not False:
        raise M6PilotError("authorisation_inactive", "authorisation is not active and unconsumed")
    if block["single_use"] is not True or block["reuse_permitted"] is not False:
        raise M6PilotError("authorization_reuse", "authorisation is not single-use")
    if not isinstance(block["authorisation_id"], str) or re.fullmatch(r"m6_[a-z0-9_]+", block["authorisation_id"]) is None:
        raise M6PilotError("authorisation_field_missing", "authorisation id is not an m6 single-use id")
    parent = _sha40_text(block["authorization_parent_commit"], "authorisation_commit_invalid")
    executing = _sha40_text(block["executing_implementation_commit"], "authorisation_commit_invalid")
    if parent != executing:
        raise M6PilotError("authorisation_commit_invalid", "parent commit and executing implementation commit differ")
    if block["phase"] != ACTIVE_PHASE or block["scope"] != ACTIVE_SCOPE:
        raise M6PilotError("authorisation_scope_invalid", "phase or scope is not the M6 pilot")
    if list(block["permitted_roles"]) != list(ACTIVE_ROLES):
        raise M6PilotError("authorisation_scope_invalid", "permitted roles drifted")
    if "REF" in block["permitted_roles"] or "EVAL" in block["permitted_roles"]:
        raise M6PilotError("ref_or_eval_access", "REF and EVAL are not permitted roles")
    if isinstance(block["physical_gpu_index"], bool) or not isinstance(block["physical_gpu_index"], int) or block["physical_gpu_index"] < 0:
        raise M6PilotError("identity_mismatch", "physical GPU index must be a nonnegative integer")
    if str(block["physical_gpu_index"]) != block["cuda_visible_devices"]:
        raise M6PilotError("identity_mismatch", "CUDA_VISIBLE_DEVICES is not the physical GPU index")
    if block["logical_device"] != LOGICAL_CUDA_DEVICE:
        raise M6PilotError("identity_mismatch", "logical device is not cuda:0")
    _gpu_uuid(block["gpu_uuid"])
    _pci_bus(block["pci_bus"])
    if not isinstance(block["authorisation_timestamp"], str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+\d{2}:\d{2}", block["authorisation_timestamp"]) is None:
        raise M6PilotError("authorisation_field_missing", "authorisation timestamp is not an offset ISO timestamp")
    session = _exact_keys(block["session"], SESSION_KEYS, "authorisation_shape_invalid")
    if session["pattern"] != SESSION_PATTERN or session["wall_clock_expiry"] is not None or session["resume_permitted"] is not False:
        raise M6PilotError("authorisation_scope_invalid", "session conditions are not the M5 single-use pattern")
    if session["consumption_event"] != CONSUMPTION_EVENT:
        raise M6PilotError("authorisation_scope_invalid", "consumption event is not bound output creation")
    output = assert_output_directory_shape(block["output_directory"], run_root)
    if block["evidence_directory"] != block["output_directory"]:
        raise M6PilotError("execution_not_authorised", "evidence directory is not the bound output directory")
    del output
    _authorisation_identities(block)
    hashes = _exact_keys(block["implementation_file_hashes"], IMPLEMENTATION_FILE_PATHS, "provenance_mismatch")
    for path, digest in hashes.items():
        if not _is_sha256(digest):
            raise M6PilotError("provenance_mismatch", "implementation file hash is missing: " + path)
    return block


def assert_active_configuration(config, run_root=RUN_ROOT):
    config = _exact_keys(config, CONFIGURATION_ROOT_KEYS, "authorisation_shape_invalid")
    if _contains_key(config, "authorization_commit"):
        raise M6PilotError("authorisation_commit_invalid", "tracked configuration must not store authorization_commit")
    if config.get("document_status") != ACTIVE_DOCUMENT_STATUS or config.get("consumable_by_executable_workflow") is not True:
        raise M6PilotError("authorisation_inactive", "active document flags drifted")
    if config.get("schema_version") != SCHEMA_VERSION or config.get("experiment_id") != EXPERIMENT_ID:
        raise M6PilotError("authorisation_scope_invalid", "experiment identity drifted")
    if config.get("rnagenesis_commit") != RNAGENESIS_COMMIT or config.get("rnagenesis_branch") != RNAGENESIS_BRANCH:
        raise M6PilotError("provenance_mismatch", "RNAGenesis pin drifted")
    execution = _exact_keys(config.get("execution"), EXECUTION_KEYS, "authorisation_shape_invalid")
    if execution["authorised"] is not True or execution["biological_paths_permitted"] is not True or execution["gpu_identity_bound"] is not True:
        raise M6PilotError("authorisation_inactive", "execution flags are not active")
    block = assert_active_authorisation_block(config.get("pilot_execution_authorisation"), run_root)
    for key in ("authorisation_id", "authorization_parent_commit", "executing_implementation_commit", "output_directory", "evidence_directory"):
        if execution[key] != block[key]:
            raise M6PilotError("authorisation_evidence_mismatch", "execution." + key + " does not match the authorisation")
    return block


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
    for permitted in PERMITTED_ACTIVATION_PREFIXES:
        if path == permitted or path.startswith(permitted + "."):
            return True
    return False


def assert_authorisation_delta(implementation_config, authorization_config):
    paths = differing_paths(implementation_config, authorization_config)
    unexpected = [path for path in paths if not _path_is_permitted_activation(path)]
    if unexpected:
        raise M6PilotError("authorisation_delta_invalid", "authorization commit changes " + unexpected[0])
    if not paths:
        raise M6PilotError("authorisation_delta_invalid", "authorization commit does not activate the pilot")
    return paths


def _porcelain_entries(porcelain):
    if not isinstance(porcelain, str):
        raise M6PilotError("provenance_mismatch", "git status porcelain could not be read")
    entries = []
    for line in porcelain.splitlines():
        if line == "":
            continue
        if len(line) < 4 or line[2] != " ":
            raise M6PilotError("provenance_mismatch", "git status porcelain could not be read")
        path = line[3:]
        if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
            path = path[1:-1]
        entries.append((line[0], line[1], path.replace("\\", "/")))
    return entries


def assert_mres_repository_clean(porcelain):
    if _porcelain_entries(porcelain):
        raise M6PilotError("provenance_mismatch", "MRes tracked state, index, or untracked state is not clean")
    return True


def assert_rnagenesis_repository(directory_porcelain, file_porcelain=None):
    """Reviewed M5 fingerprint. File porcelain is required; there is no models/ blanket."""
    if file_porcelain is None:
        raise M6PilotError("provenance_mismatch", "RNAGenesis file porcelain is required")
    return assert_rnagenesis_reviewed_tree(directory_porcelain, file_porcelain)


def assert_repository_binding(config, observation):
    observation = _require_mapping(observation, "provenance_mismatch", "repository observation is missing")
    head = _sha40_text(observation.get("mres_head"), "authorisation_commit_invalid")
    parents = observation.get("mres_parents")
    if not isinstance(parents, (list, tuple)) or len(parents) != 1:
        raise M6PilotError("authorisation_commit_invalid", "live HEAD must have exactly one parent")
    parent = _sha40_text(parents[0], "authorisation_commit_invalid")
    block = config["pilot_execution_authorisation"]
    if parent != block["executing_implementation_commit"] or parent != block["authorization_parent_commit"]:
        raise M6PilotError("authorisation_commit_invalid", "live HEAD parent is not the executing implementation commit")
    if head == parent:
        raise M6PilotError("authorisation_commit_invalid", "authorization commit and implementation commit are the same")
    changed = observation.get("changed_files")
    if tuple(changed) != PERMITTED_AUTHORIZATION_FILES:
        raise M6PilotError("authorisation_delta_invalid", "authorization commit changes a file outside the pilot configuration")
    assert_authorisation_delta(observation.get("implementation_config"), config)
    assert_mres_repository_clean(observation.get("mres_porcelain"))
    if observation.get("rnagenesis_head") != RNAGENESIS_COMMIT or observation.get("rnagenesis_branch") != RNAGENESIS_BRANCH:
        raise M6PilotError("provenance_mismatch", "RNAGenesis HEAD drifted")
    assert_rnagenesis_repository(
        observation.get("rnagenesis_directory_porcelain"),
        observation.get("rnagenesis_file_porcelain"),
    )
    parent_hashes = _require_mapping(observation.get("file_sha256_at_parent"), "provenance_mismatch", "parent file hashes are missing")
    working_hashes = _require_mapping(observation.get("file_sha256_working_tree"), "provenance_mismatch", "working tree file hashes are missing")
    for path, digest in config["pilot_execution_authorisation"]["implementation_file_hashes"].items():
        if parent_hashes.get(path) != digest or working_hashes.get(path) != digest:
            raise M6PilotError("provenance_mismatch", "implementation file hash drifted: " + path)
    return head


def assert_no_self_referential_authorization_commit(config, live_head):
    if _contains_key(config, "authorization_commit"):
        raise M6PilotError("authorisation_commit_invalid", "tracked configuration stores authorization_commit")
    for _key, value in _walk(config):
        if value == live_head:
            raise M6PilotError("authorisation_commit_invalid", "tracked configuration contains the live authorization commit")
    return True


def assert_output_available(config, observation, run_root=RUN_ROOT):
    path = config["pilot_execution_authorisation"]["output_directory"]
    assert_output_directory_shape(path, run_root)
    if observation.get("output_exists") is not False or observation.get("output_symlink") is not False:
        raise M6PilotError("authorization_reuse", "the bound output directory already exists or is a symlink")
    if observation.get("component_symlink") is not False:
        raise M6PilotError("execution_not_authorised", "the bound output path contains a symlink")
    return path


def assert_gpu_binding(block, probe):
    probe = _exact_keys(
        probe,
        ("cuda_visible_devices", "logical_device", "pci_bus", "physical_index", "uuid"),
        "identity_mismatch",
    )
    if probe["physical_index"] != block["physical_gpu_index"] or probe["uuid"] != block["gpu_uuid"]:
        raise M6PilotError("identity_mismatch", "GPU observation does not match the authorisation")
    if probe["pci_bus"] != block["pci_bus"] or probe["logical_device"] != block["logical_device"]:
        raise M6PilotError("identity_mismatch", "GPU bus or logical device does not match the authorisation")
    if probe["cuda_visible_devices"] != block["cuda_visible_devices"] or probe["logical_device"] != LOGICAL_CUDA_DEVICE:
        raise M6PilotError("identity_mismatch", "CUDA_VISIBLE_DEVICES observation does not match the authorisation")
    return True


def validate_active_execution(config, observation, run_root=RUN_ROOT):
    """Stdlib gate. This does not import a training stack or create a directory."""
    block = assert_active_configuration(config, run_root)
    head = assert_repository_binding(config, observation)
    assert_no_self_referential_authorization_commit(config, head)
    assert_output_available(config, observation, run_root)
    assert_gpu_binding(block, observation.get("gpu_probe"))
    payload = {key: block[key] for key in ACTIVE_AUTHORISATION_KEYS}
    payload["authorization_commit"] = head
    payload["gpu_probe"] = dict(observation["gpu_probe"])
    payload["repository_observation"] = repository_observation_record(observation)
    return ValidatedActiveAuthorisation(payload, _AUTH_TOKEN)


def validate_consumed_worker(config, observation, directory):
    """Re-check a worker whose parent already created the bound directory."""
    run_root = os.path.dirname(directory)
    block = assert_active_configuration(config, run_root)
    if block["output_directory"] != directory:
        raise M6PilotError("authorization_reuse", "worker directory is not the bound output")
    head = assert_repository_binding(config, observation)
    assert_no_self_referential_authorization_commit(config, head)
    if observation.get("output_exists") is not True or observation.get("output_symlink") is not False:
        raise M6PilotError("authorization_reuse", "consumed worker requires the bound directory")
    if observation.get("component_symlink") is not False:
        raise M6PilotError("execution_not_authorised", "the bound output path contains a symlink")
    consumption_path = os.path.join(directory, CONSUMPTION_RECORD_NAME)
    if os.path.islink(consumption_path) or not os.path.isfile(consumption_path):
        raise M6PilotError("authorization_reuse", "consumption record is missing")
    with open(consumption_path, "rb") as handle:
        record = json.loads(handle.read().decode("utf-8"))
    if record.get("authorization_commit") != head or record.get("reuse_permitted") is not False:
        raise M6PilotError("authorization_reuse", "consumption record does not match the live authorisation")
    assert_gpu_binding(block, observation.get("gpu_probe"))
    payload = {key: block[key] for key in ACTIVE_AUTHORISATION_KEYS}
    payload["authorization_commit"] = head
    payload["gpu_probe"] = dict(observation["gpu_probe"])
    payload["repository_observation"] = repository_observation_record(observation)
    return ValidatedActiveAuthorisation(payload, _AUTH_TOKEN)


def repository_observation_record(observation):
    """Cleanliness flags from the porcelain that just passed the M5 gate."""
    mres_entries = _porcelain_entries(observation.get("mres_porcelain"))
    rna_entries = _porcelain_entries(observation.get("rnagenesis_file_porcelain"))
    mres_clean = len(mres_entries) == 0
    tracked_clean = all(index_status == "?" and worktree_status == "?" for index_status, worktree_status, _path in rna_entries)
    m5 = m5_contract()
    preserved = True
    for index_status, worktree_status, path in rna_entries:
        if index_status == "?" and worktree_status == "?":
            if not m5._under_known_prefix(path):
                preserved = False
        else:
            tracked_clean = False
    return {
        "mres_index_clean": mres_clean,
        "mres_tracked_clean": mres_clean,
        "mres_untracked_clean": mres_clean,
        "rnagenesis_branch": observation.get("rnagenesis_branch"),
        "rnagenesis_commit": observation.get("rnagenesis_head"),
        "rnagenesis_tracked_clean": tracked_clean,
        "rnagenesis_untracked_preserved": preserved and tracked_clean,
    }


def pinned_artifact_file_sha256():
    return {
        "validation_draw_manifest.json": VALIDATION_DRAW_MANIFEST_SHA256,
        "validation_draw_manifest_sha256.json": VALIDATION_HASH_REPORT_SHA256,
        "validation_noise.float32": VALIDATION_NOISE_SHA256,
        "validation_order_artifact.csv": VALIDATION_ORDER_ARTIFACT_SHA256,
        "validation_timesteps.int64": VALIDATION_TIMESTEPS_SHA256,
    }


def checkpoint_child_name(update, git_sha):
    """Direct child name from the checked-in naming pattern."""
    if update not in RETAINED_WEIGHT_UPDATES:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint update is not retained")
    if not isinstance(git_sha, str) or re.fullmatch(r"[0-9a-f]{40}", git_sha) is None:
        raise M6PilotError("provenance_mismatch", "checkpoint name requires the implementation commit")
    return (
        "D1_generic-diffusion__data-%s__lr-3e-5__ebs-32__seed-42__update-%d__git-%s"
        % (TRAIN_TEXT_SHA256[:8], update, git_sha)
    )


def production_loss_scale(example_weight):
    """Net backward coefficient for manual accumulation.

    Accelerate 0.25.0 divides a non-DeepSpeed loss by
    ``gradient_accumulation_steps`` inside ``Accelerator.backward``. Production
    sets that configuration value to 1 and multiplies by the example weight
    first. The net coefficient is the example weight. It is not multiplied by
    4 again.
    """
    if PRODUCTION_ACCELERATOR_GRADIENT_ACCUMULATION_STEPS != 1:
        raise M6PilotError("microbatch_arithmetic_invalid", "production Accelerate accumulation must stay 1")
    weight = _finite_float(example_weight, "microbatch_arithmetic_invalid")
    if weight <= 0.0:
        raise M6PilotError("microbatch_arithmetic_invalid", "example weight must be positive")
    return weight / float(PRODUCTION_ACCELERATOR_GRADIENT_ACCUMULATION_STEPS)


def assign_applied_learning_rate(optimizer, update_number):
    """Set every param-group learning rate to the applied schedule value."""
    learning_rate = applied_learning_rate(update_number)
    groups = getattr(optimizer, "param_groups", None)
    if not isinstance(groups, list) or not groups:
        raise M6PilotError("learning_rate_schedule_invalid", "optimizer param groups are missing")
    for group in groups:
        group["lr"] = learning_rate
    return learning_rate


def python_rng_digest(state):
    if not isinstance(state, tuple) or len(state) != 3:
        raise M6PilotError("identity_mismatch", "Python RNG state is not a triple")
    version, sequence, gauss = state
    payload = {"gauss": gauss, "sequence": list(sequence), "version": version}
    return sha256_bytes(canonical_json(payload))


def count_newline_records(raw):
    """Record count using the RNAGenesis newline rule. This does not repair bases."""
    if not isinstance(raw, (bytes, bytearray)):
        raise M6PilotError("identity_mismatch", "record bytes are required")
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        raise M6PilotError("identity_mismatch", "record file is not UTF-8")
    if text.startswith("\ufeff"):
        raise M6PilotError("identity_mismatch", "record file begins with a BOM")
    if text.endswith("\n"):
        text = text[:-1]
    if text.endswith("\r"):
        text = text[:-1]
    if text == "":
        raise M6PilotError("identity_mismatch", "record file contains no records")
    records = []
    for record in text.split("\n"):
        if record.endswith("\r"):
            record = record[:-1]
        records.append(record)
    return len(records)


def count_validation_cores(raw):
    import csv
    from io import StringIO

    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        raise M6PilotError("identity_mismatch", "VALIDATION file is not UTF-8")
    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None or "sequence_core" not in reader.fieldnames or "ft_split" not in reader.fieldnames:
        raise M6PilotError("identity_mismatch", "VALIDATION columns drifted")
    seen = []
    for row in reader:
        if row.get("ft_split") != "VALIDATION":
            raise M6PilotError("unexpected_biological_path_or_role", "VALIDATION row role drifted")
        core = row.get("sequence_core")
        if core in seen:
            continue
        seen.append(core)
    return len(seen)


def _reject_symlink_components(path):
    current = os.path.abspath(path)
    while True:
        if os.path.islink(current):
            raise M6PilotError("unexpected_biological_path_or_role", "refusing a symlink path")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent


def verify_bound_file(path, role, expected_sha256, expected_count, bound_path, reader):
    """Hash and count a bound file before the training reader is called."""
    if role in DENIED_ROLES or path_is_ref_or_eval(path) or path_is_ref_or_eval(bound_path):
        raise M6PilotError("ref_or_eval_access", "REF and EVAL are refused before open")
    if path_is_obsolete_repository_local(path) or path_is_obsolete_repository_local(bound_path):
        raise M6PilotError("unexpected_biological_path_or_role", "obsolete repository-local data is refused before open")
    if expected_sha256 in DENIED_HASHES or role not in {"TRAIN_TEXT", "VALIDATION_CSV"}:
        raise M6PilotError("unexpected_biological_path_or_role", "the file role or hash is not a pilot input")
    if os.path.realpath(path) != os.path.realpath(bound_path) or os.path.abspath(path) != os.path.abspath(bound_path):
        raise M6PilotError("unexpected_biological_path_or_role", "the path is not the bound input")
    _reject_symlink_components(path)
    if os.path.islink(path) or not os.path.isfile(path):
        raise M6PilotError("unexpected_biological_path_or_role", "input is not a regular file")
    observed_hash = sha256_file(path)
    measured = os.lstat(path)
    with open(path, "rb") as handle:
        raw = handle.read()
    if sha256_bytes(raw) != observed_hash:
        raise M6PilotError("identity_mismatch", "streamed file hash did not match the bytes read for the count")
    if observed_hash != expected_sha256:
        raise M6PilotError("identity_mismatch", "observed file hash does not match the binding")
    count = count_newline_records(raw) if role == "TRAIN_TEXT" else count_validation_cores(raw)
    if count != expected_count:
        raise M6PilotError("identity_mismatch", "observed record count does not match the binding")
    if reader is None:
        raise M6PilotError("execution_not_authorised", "no reader is available")
    return {
        "byte_size": int(measured.st_size),
        "count": count,
        "evidence_origin": "observed",
        "expected_count": expected_count,
        "expected_sha256": expected_sha256,
        "observation_method": "streamed_sha256",
        "opened": reader(path),
        "path": os.path.abspath(path),
        "role": role,
        "sha256": observed_hash,
    }


def verify_artifact_directory(path, bound_path, expected_hashes, loader):
    """Hash stored artifact files before ``load_verified_artifacts`` is called."""
    if path_is_ref_or_eval(path) or path_is_obsolete_repository_local(path):
        raise M6PilotError("unexpected_biological_path_or_role", "artifact path is refused before open")
    if os.path.realpath(path) != os.path.realpath(bound_path):
        raise M6PilotError("unexpected_biological_path_or_role", "artifact directory is not the bound directory")
    _reject_symlink_components(path)
    if os.path.islink(path) or not os.path.isdir(path):
        raise M6PilotError("unexpected_biological_path_or_role", "artifact path is not a real directory")
    expected_hashes = _exact_keys(expected_hashes, VALIDATION_ARTIFACT_FILES, "identity_mismatch")
    observed = {}
    for name in VALIDATION_ARTIFACT_FILES:
        file_path = os.path.join(path, name)
        if os.path.islink(file_path) or not os.path.isfile(file_path):
            raise M6PilotError("identity_mismatch", "artifact file is missing: " + name)
        digest = sha256_file(file_path)
        if digest != expected_hashes[name]:
            raise M6PilotError("identity_mismatch", "artifact hash drifted: " + name)
        measured = os.lstat(file_path)
        observed[name] = {
            "byte_size": int(measured.st_size),
            "evidence_origin": "observed",
            "expected_byte_size": int(measured.st_size),
            "expected_sha256": expected_hashes[name],
            "observation_method": "streamed_sha256",
            "path": file_path,
            "regular_file": True,
            "role": name,
            "sha256": digest,
            "symlink": False,
        }
    if loader is None:
        raise M6PilotError("execution_not_authorised", "artifact loader is unavailable")
    return {"loaded": loader(path), "observed_files": observed}


def write_atomic_json(directory, name, payload):
    """Write canonical JSON through an exclusive temporary file and one replace.

    ``os.write`` may write fewer bytes than requested, so the loop continues until
    every byte is written. If the write, ``fsync``, or replace fails, the
    temporary file is removed and the target is never left half written.
    """
    target = os.path.join(directory, name)
    temporary = target + ".partial"
    blob = canonical_json(payload)
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        try:
            view = memoryview(blob)
            while len(view) > 0:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short write made no progress")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, target)
    except BaseException:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise
    return target


def consumption_payload(authorisation):
    return {
        "activation_status_at_issue": "active_unconsumed",
        "authorisation_id": authorisation["authorisation_id"],
        "authorization_commit": authorisation["authorization_commit"],
        "authorization_parent_commit": authorisation["authorization_parent_commit"],
        "consumption_state": "consumed_output_created",
        "executing_implementation_commit": authorisation["executing_implementation_commit"],
        "output_directory": authorisation["output_directory"],
        "reuse_permitted": False,
        "schema_version": "m6-authorisation-consumption-1",
    }


def consume_bound_output_directory(authorisation, run_root=RUN_ROOT):
    """Create the one bound directory and consume the authorisation immediately."""
    if not isinstance(authorisation, ValidatedActiveAuthorisation):
        raise M6PilotError("execution_not_authorised", "output creation requires a validated active authorisation")
    path = authorisation["output_directory"]
    assert_output_directory_shape(path, run_root)
    if os.path.lexists(path) or os.path.islink(path):
        raise M6PilotError("authorization_reuse", "the bound output directory already exists")
    _reject_symlink_components(os.path.dirname(path))
    os.mkdir(path)
    try:
        write_atomic_json(path, CONSUMPTION_RECORD_NAME, consumption_payload(authorisation))
    except Exception:
        raise M6PilotError("authorization_reuse", "the bound directory was created but consumption could not be recorded")
    return path


def failure_payload(exc, authorisation=None, retained_checkpoints=None):
    if isinstance(exc, M6PilotError):
        code = exc.code
        detail = exc.detail
        stage = exc.stage
        update = exc.update
        microbatch = exc.microbatch
    else:
        code = "incomplete_evidence_or_manifest"
        detail = "authorized worker failed"
        stage = None
        update = None
        microbatch = None
    if code not in STOP_CONDITION_CODES:
        raise M6PilotError("incomplete_evidence_or_manifest", "fired stop condition is not registered")
    retained = [] if retained_checkpoints is None else list(retained_checkpoints)
    authorisation = {} if authorisation is None else authorisation
    payload = {
        "authorization_commit": authorisation.get("authorization_commit"),
        "authorization_parent_commit": authorisation.get("authorization_parent_commit"),
        "completion_state": "consumed_failed",
        "consumption_state": "consumed_failed",
        "detail": detail,
        "executing_implementation_commit": authorisation.get("executing_implementation_commit"),
        "failure_code": code,
        "fired_stop_condition": code,
        "manifest_written": False,
        "microbatch": microbatch,
        "non_resumable": True,
        "pilot_completed": False,
        "resume_supported": False,
        "retained_checkpoint_updates": retained,
        "retained_checkpoints_exist": bool(retained),
        "scientific_run_completed": False,
        "stage": stage,
        "update": update,
    }
    _reject_sequence_text(payload)
    if payload["pilot_completed"] is not False or payload["scientific_run_completed"] is not False:
        raise M6PilotError("incomplete_evidence_or_manifest", "a failure record must not claim pilot completion")
    return payload


def write_failure_record(directory, exc, authorisation=None, retained_checkpoints=None):
    return write_atomic_json(
        directory,
        FAILURE_RECORD_NAME,
        failure_payload(exc, authorisation=authorisation, retained_checkpoints=retained_checkpoints),
    )


def _finite_decimal_string(value):
    if isinstance(value, bool) or not isinstance(value, str) or value.strip() == "":
        raise M6PilotError("incomplete_evidence_or_manifest", "numeric evidence must be a decimal string")
    try:
        number = float(value)
    except ValueError:
        raise M6PilotError("incomplete_evidence_or_manifest", "numeric evidence is not a decimal string")
    if math.isnan(number) or math.isinf(number):
        raise M6PilotError("incomplete_evidence_or_manifest", "numeric evidence is not finite")
    return number


def _nonnegative_decimal_string(value):
    number = _finite_decimal_string(value)
    if number < 0.0:
        raise M6PilotError("incomplete_evidence_or_manifest", "numeric evidence is not finite and nonnegative")
    return number


def _nonnegative_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise M6PilotError("incomplete_evidence_or_manifest", "byte count is not a nonnegative integer")
    return value


def _reject_synthetic_sentinels(manifest):
    text = canonical_json(manifest).decode("ascii")
    for sentinel in (
        "not_observed_because_execution_is_not_authorised",
        "synthetic_control_flow",
        "synthetic_control_flow_did_not_open_biological_data_or_load_a_model",
        "\"hardcoded\"",
    ):
        if sentinel in text:
            raise M6PilotError("incomplete_evidence_or_manifest", "production manifest contains synthetic evidence")


ASSET_RECORD_KEYS = (
    "byte_size",
    "evidence_origin",
    "expected_byte_size",
    "expected_sha256",
    "observation_method",
    "path",
    "regular_file",
    "role",
    "sha256",
    "symlink",
)
RUNTIME_OBSERVATION_KEYS = (
    "accelerate",
    "diffusers",
    "evidence_origin",
    "executable",
    "observation_method",
    "python",
    "torch",
    "transformers",
)
PRODUCTION_B1_KEYS = (
    "copied_at_update_0",
    "evidence_origin",
    "initialization",
    "observed_assets",
    "unet_config_sha256",
    "weight_bytes",
    "weight_sha256",
)
PRODUCTION_ENVIRONMENT_KEYS = (
    "accelerate_version",
    "bytecode_disabled",
    "cache_isolation",
    "datasets_offline",
    "diffusers_version",
    "evidence_origin",
    "executable",
    "expected_python",
    "expected_versions",
    "hub_offline",
    "numpy_called_by_pilot",
    "numpy_used_by_pinned_artifact_loader",
    "package_versions_observed",
    "pinned_python",
    "python_version",
    "runtime_isolation_verified",
    "torch_version",
    "transformers_offline",
    "transformers_version",
)
PRODUCTION_TIMING_KEYS = (
    "checkpoint_save_reload_seconds",
    "checkpoint_time_excluded_from_training_and_validation",
    "evidence_origin",
    "synchronization",
    "training_seconds",
    "training_update_seconds",
    "validation_excluded_from_training_updates",
    "validation_seconds",
    "validation_update_seconds",
)
TIMING_SPAN_KEYS = ("seconds", "update")
PRODUCTION_FROZEN_KEYS = (
    "all_frozen",
    "components",
    "encdec_buffers_absent_from_optimizer",
    "encdec_eval_mode",
    "encdec_parameters_absent_from_optimizer",
    "encdec_parameter_digest_after_update_14",
    "encdec_parameter_digest_after_update_21",
    "encdec_parameter_digest_after_update_7",
    "encdec_parameter_digest_at_initialization",
    "encdec_persistent_buffer_digest_after_update_14",
    "encdec_persistent_buffer_digest_after_update_21",
    "encdec_persistent_buffer_digest_after_update_7",
    "encdec_persistent_buffer_digest_at_initialization",
    "encdec_requires_grad_false",
    "evidence_origin",
    "optimizer_contains_encdec",
    "optimizer_contains_only_denoiser",
    "optimizer_parameter_ids_equal_trainable_denoiser",
    "rotary_cache_names",
    "rotary_caches_excluded_from_persistent_buffer_digest",
)
PRODUCTION_ROLE_KEYS = (
    "evidence_origin",
    "expected_count",
    "expected_sha256",
    "observation_method",
    "observed_byte_size",
    "observed_count",
    "observed_sha256",
    "opened",
    "path",
    "role",
)
PRODUCTION_VALIDATION_ARTIFACT_KEYS = (
    "draw_manifest_sha256",
    "draws",
    "evidence_origin",
    "hash_report_sha256",
    "noise_sha256",
    "noise_shape",
    "observation_method",
    "observed_files",
    "order_artifact_sha256",
    "sequence_count",
    "sequence_order_sha256",
    "sequence_order_source",
    "timestep_sha256",
    "timestep_shape",
    "validation_csv_sha256",
)
PRODUCTION_OPTIMIZER_KEYS = (
    "automatic_learning_rate_reduction_to_1e-5",
    "beta1",
    "beta2",
    "diffusers_cosine_constructor_used",
    "ema_enabled",
    "epsilon",
    "evidence_origin",
    "gradient_clip_norm",
    "learning_rate",
    "learning_rate_sweep",
    "mixed_precision",
    "name",
    "precision",
    "weight_decay",
    "weight_variant",
)
PRODUCTION_DENOISER_EVIDENCE_KEYS = (
    "any_unchanged_after_nonzero_lr",
    "applied_updates_checked",
    "checked_after_each_applied_update",
    "evidence_origin",
)
REVIEW_ITEM_KEYS = (
    "automatic_early_stop",
    "automatic_learning_rate_change",
    "delta",
    "finite_worsening",
    "human_review_signal",
    "initial",
    "later",
    "numeric_cutoff",
    "update",
)
CHECKPOINT_PROOF_KEYS = (
    "configuration",
    "evidence_origin",
    "fresh_load_succeeded",
    "original_object_id",
    "reloaded_object_id",
    "resume_supported",
    "saved_hashes",
    "state_comparison",
    "state_scope",
    "update",
    "weight_reload_is_training_resume",
)
CONFIGURATION_PROOF_KEYS = (
    "configuration_compatible",
    "ignored_top_level_keys",
    "normalized_sha256_equal",
    "original_normalized_sha256",
    "original_raw_sha256",
    "raw_sha256_equal",
    "reloaded_normalized_sha256",
    "reloaded_raw_sha256",
)
STATE_COMPARISON_KEYS = (
    "aggregate_digest",
    "compared_parameter_count",
    "comparison_selection",
    "complete_state_equal",
    "entry_digests",
    "includes_persistent_buffers",
    "mismatched_parameter_count",
    "parameter_names_sha256",
    "tensor_comparison",
    "weight_reload_is_training_resume",
)
MICROBATCH_KEYS = (
    "drop_last",
    "final_window_examples",
    "final_window_microbatch_sizes",
    "final_window_weight_denominator",
    "final_window_weight_numerators",
    "final_window_weights_sum_to_one",
    "full_window_examples",
    "gradient_accumulation",
    "intended_effective_batch",
    "microbatch_count",
    "optimizer_updates",
    "physical_microbatch",
    "train_records",
)


def _accepted_asset_table():
    m5 = m5_contract()
    table = {}
    for relative, digest, size, role in m5.REQUIRED_MODEL_FILES:
        table[role] = {"byte_size": size, "path_suffix": relative, "sha256": digest}
    table["diffusers_normalization_patch"] = {
        "byte_size": m5.DIFFUSERS_PATCH_SIZE,
        "path_suffix": m5.DIFFUSERS_PATCH_PATH,
        "sha256": m5.DIFFUSERS_PATCH_SHA256,
    }
    return table


def _require_streamed_asset(record, role, accepted):
    record = _exact_keys(record, ASSET_RECORD_KEYS, "identity_mismatch")
    if record["role"] != role or record["evidence_origin"] != "observed":
        raise M6PilotError("identity_mismatch", "asset evidence is not an observation: " + role)
    if record["observation_method"] != "streamed_sha256":
        raise M6PilotError("identity_mismatch", "asset hash was not streamed from the file: " + role)
    if record["regular_file"] is not True or record["symlink"] is not False:
        raise M6PilotError("identity_mismatch", "asset is not a regular non-symlink file: " + role)
    if not isinstance(record["path"], str) or record["path"] == "":
        raise M6PilotError("identity_mismatch", "asset path was not observed: " + role)
    if isinstance(record["byte_size"], bool) or not isinstance(record["byte_size"], int):
        raise M6PilotError("identity_mismatch", "asset size was not observed: " + role)
    if record["byte_size"] != record["expected_byte_size"] or record["byte_size"] != accepted["byte_size"]:
        raise M6PilotError("identity_mismatch", "asset size drifted: " + role)
    if record["sha256"] != record["expected_sha256"] or record["sha256"] != accepted["sha256"] or not _is_sha256(record["sha256"]):
        raise M6PilotError("identity_mismatch", "asset hash drifted: " + role)
    suffix = accepted["path_suffix"]
    if role == "diffusers_normalization_patch":
        if record["path"] != suffix:
            raise M6PilotError("identity_mismatch", "Diffusers patch path drifted")
    elif not record["path"].endswith("/" + suffix) and record["path"] != suffix:
        raise M6PilotError("identity_mismatch", "asset path drifted: " + role)
    return record


def _require_decimal_sum(parts, total, detail):
    parsed = [_nonnegative_decimal_string(item) for item in parts]
    aggregate = _nonnegative_decimal_string(total)
    if abs(sum(parsed) - aggregate) > 1e-6:
        raise M6PilotError("incomplete_evidence_or_manifest", detail)
    return aggregate


def validate_production_success_manifest(manifest, binding):
    """Accept only a completed pilot whose every section was observed."""
    manifest = _exact_keys(manifest, MANIFEST_KEYS, "incomplete_evidence_or_manifest")
    _reject_sequence_text(manifest)
    _reject_synthetic_sentinels(manifest)
    binding = _require_mapping(binding, "incomplete_evidence_or_manifest", "production binding is missing")
    if manifest["completion_state"] != "pilot_completed" or manifest["production_identities"] is not True:
        raise M6PilotError("incomplete_evidence_or_manifest", "production completion requires observed production identities")
    if manifest["failure_state"] is not None or manifest["resume_supported"] is not False:
        raise M6PilotError("incomplete_evidence_or_manifest", "a completed pilot has no failure state and no resume")
    if manifest["diagnostic_generation_status"] != DIAGNOSTIC_GENERATION_STATUS:
        raise M6PilotError("diagnostic_generation_not_authorised", "diagnostic generation is separately gated")
    if manifest["manifest_schema_version"] != MANIFEST_SCHEMA_VERSION or manifest["schema_version"] != SCHEMA_VERSION:
        raise M6PilotError("incomplete_evidence_or_manifest", "manifest schema drifted")
    if manifest["config_version"] != SCHEMA_VERSION or manifest["experiment_id"] != EXPERIMENT_ID:
        raise M6PilotError("incomplete_evidence_or_manifest", "experiment identity drifted")
    _require_production_authorisation(manifest, binding)
    _require_production_gpu(manifest, binding)
    _require_production_repository(manifest)
    _require_production_assets(manifest)
    _require_production_runtime(manifest)
    _require_production_accounting(manifest)
    _require_production_optimizer(manifest)
    _require_production_roles(manifest)
    _require_production_validation_artifacts(manifest)
    _require_production_loop(manifest)
    _require_production_timing(manifest)
    _require_production_frozen(manifest)
    _require_production_review(manifest)
    _require_production_restart(manifest)
    _require_production_checkpoints(manifest)
    _require_production_stops(manifest)
    if manifest["warnings"] != []:
        raise M6PilotError("incomplete_evidence_or_manifest", "production warnings drifted")
    if [item.get("id") for item in manifest["deviations"]] != list(DOCUMENTED_DEVIATIONS):
        raise M6PilotError("incomplete_evidence_or_manifest", "documented deviations drifted")
    memory = _exact_keys(manifest["memory"], ("evidence_origin", "peak_allocated_bytes", "peak_reserved_bytes"), "incomplete_evidence_or_manifest")
    if memory["evidence_origin"] != "observed":
        raise M6PilotError("incomplete_evidence_or_manifest", "memory was not observed")
    _nonnegative_int(memory["peak_allocated_bytes"])
    _nonnegative_int(memory["peak_reserved_bytes"])
    return True


def _require_production_authorisation(manifest, binding):
    authorisation = _exact_keys(
        manifest["authorisation"],
        (
            "authorisation_id",
            "authorization_commit",
            "authorization_parent_commit",
            "consumption_state",
            "evidence_origin",
            "executing_implementation_commit",
            "reuse_permitted",
            "single_use",
        ),
        "incomplete_evidence_or_manifest",
    )
    if authorisation["evidence_origin"] != "observed" or authorisation["consumption_state"] != "consumed_successfully":
        raise M6PilotError("incomplete_evidence_or_manifest", "authorisation was not consumed successfully from observation")
    if authorisation["reuse_permitted"] is not False or authorisation["single_use"] is not True:
        raise M6PilotError("authorization_reuse", "authorisation is not single-use")
    if authorisation["authorization_commit"] != binding["authorization_commit"]:
        raise M6PilotError("authorisation_commit_invalid", "manifest authorization commit is not the live HEAD")
    if authorisation["authorization_parent_commit"] != binding["authorization_parent_commit"]:
        raise M6PilotError("authorisation_commit_invalid", "manifest parent commit drifted")
    if authorisation["executing_implementation_commit"] != binding["executing_implementation_commit"]:
        raise M6PilotError("authorisation_commit_invalid", "manifest implementation commit drifted")
    if authorisation["authorization_commit"] == authorisation["executing_implementation_commit"]:
        raise M6PilotError("authorisation_commit_invalid", "authorization commit aliases the implementation commit")
    if manifest["run_id"] != authorisation["authorisation_id"] or not isinstance(authorisation["authorisation_id"], str):
        raise M6PilotError("incomplete_evidence_or_manifest", "run id is not the consumed authorisation")
    return authorisation


def _require_production_gpu(manifest, binding):
    gpu = _exact_keys(
        manifest["gpu"],
        ("cuda_visible_devices", "evidence_origin", "hardcoded_physical_index", "logical_device", "pci_bus", "physical_index", "uuid"),
        "incomplete_evidence_or_manifest",
    )
    if gpu["evidence_origin"] != "observed" or gpu["hardcoded_physical_index"] is not False:
        raise M6PilotError("identity_mismatch", "GPU evidence is not an observation")
    if gpu["physical_index"] != binding["physical_gpu_index"] or gpu["uuid"] != binding["gpu_uuid"]:
        raise M6PilotError("identity_mismatch", "GPU observation does not match the authorisation")
    if gpu["pci_bus"] != binding["pci_bus"] or gpu["logical_device"] != LOGICAL_CUDA_DEVICE:
        raise M6PilotError("identity_mismatch", "GPU bus or logical device drifted")
    if gpu["cuda_visible_devices"] != binding["cuda_visible_devices"]:
        raise M6PilotError("identity_mismatch", "CUDA_VISIBLE_DEVICES observation drifted")
    return gpu


def _require_production_repository(manifest):
    repository = _exact_keys(
        manifest["repository"],
        (
            "authorization_commit",
            "evidence_origin",
            "executing_implementation_commit",
            "mres_index_clean",
            "mres_tracked_clean",
            "mres_untracked_clean",
            "rnagenesis_branch",
            "rnagenesis_commit",
            "rnagenesis_tracked_clean",
            "rnagenesis_untracked_preserved",
        ),
        "incomplete_evidence_or_manifest",
    )
    if repository["evidence_origin"] != "observed" or repository["rnagenesis_commit"] != RNAGENESIS_COMMIT:
        raise M6PilotError("provenance_mismatch", "repository observation drifted")
    if repository["rnagenesis_branch"] != RNAGENESIS_BRANCH:
        raise M6PilotError("provenance_mismatch", "RNAGenesis branch drifted")
    if repository["authorization_commit"] != manifest["authorisation"]["authorization_commit"]:
        raise M6PilotError("authorisation_commit_invalid", "repository authorization commit drifted")
    if repository["executing_implementation_commit"] != manifest["authorisation"]["executing_implementation_commit"]:
        raise M6PilotError("authorisation_commit_invalid", "repository implementation commit drifted")
    for key in ("mres_index_clean", "mres_tracked_clean", "mres_untracked_clean", "rnagenesis_tracked_clean", "rnagenesis_untracked_preserved"):
        if repository[key] is not True:
            raise M6PilotError("provenance_mismatch", "repository cleanliness drifted")
    return repository


def _require_production_assets(manifest):
    identity = _exact_keys(manifest["b1_identity"], PRODUCTION_B1_KEYS, "identity_mismatch")
    if identity["evidence_origin"] != "observed" or identity["copied_at_update_0"] is not False:
        raise M6PilotError("identity_mismatch", "B1 identity was not observed")
    if identity["initialization"] != "immutable_B1_generic_diffusion_checkpoint":
        raise M6PilotError("identity_mismatch", "initialisation is not immutable B1")
    accepted = _accepted_asset_table()
    assets = _exact_keys(identity["observed_assets"], tuple(accepted), "identity_mismatch")
    for role, spec in accepted.items():
        _require_streamed_asset(assets[role], role, spec)
    weights = assets["b1_unet_weights"]
    config = assets["b1_unet_config"]
    if identity["weight_sha256"] != weights["sha256"] or identity["weight_bytes"] != weights["byte_size"]:
        raise M6PilotError("identity_mismatch", "B1 weight evidence does not match the streamed file")
    if identity["unet_config_sha256"] != config["sha256"]:
        raise M6PilotError("identity_mismatch", "B1 config evidence does not match the streamed file")
    encdec_roles = ("biomap_encoder_config", "decoder_config", "encdec_config", "encdec_weights", "tokenizer")
    for role in encdec_roles:
        if assets[role]["sha256"] != accepted[role]["sha256"]:
            raise M6PilotError("identity_mismatch", "EncDec asset evidence drifted: " + role)
    return identity


def _require_production_runtime(manifest):
    environment = _exact_keys(manifest["environment"], PRODUCTION_ENVIRONMENT_KEYS, "incomplete_evidence_or_manifest")
    if environment["evidence_origin"] != "observed" or environment["runtime_isolation_verified"] is not True:
        raise M6PilotError("incomplete_evidence_or_manifest", "runtime evidence is not an observation")
    if environment["numpy_called_by_pilot"] is not False or environment["numpy_used_by_pinned_artifact_loader"] is not True:
        raise M6PilotError("incomplete_evidence_or_manifest", "NumPy use was not recorded")
    if environment["bytecode_disabled"] is not True:
        raise M6PilotError("incomplete_evidence_or_manifest", "bytecode writing was not disabled")
    for key in ("datasets_offline", "hub_offline", "transformers_offline"):
        if environment[key] is not True:
            raise M6PilotError("incomplete_evidence_or_manifest", "Hugging Face offline control was not observed")
    m5 = m5_contract()
    runtime = assert_observed_runtime(environment["package_versions_observed"])
    if environment["executable"] != runtime["executable"] or environment["pinned_python"] != m5.PINNED_PYTHON:
        raise M6PilotError("identity_mismatch", "observed executable drifted")
    if environment["python_version"] != runtime["python"] or environment["torch_version"] != runtime["torch"]:
        raise M6PilotError("identity_mismatch", "observed runtime version drifted")
    if environment["accelerate_version"] != runtime["accelerate"] or environment["diffusers_version"] != runtime["diffusers"]:
        raise M6PilotError("identity_mismatch", "observed runtime version drifted")
    if environment["transformers_version"] != runtime["transformers"] or environment["expected_python"] != m5.ACCEPTED_RUNTIME_VERSIONS["python"]:
        raise M6PilotError("identity_mismatch", "observed runtime version drifted")
    expected_versions = _exact_keys(environment["expected_versions"], tuple(m5.ACCEPTED_RUNTIME_VERSIONS), "identity_mismatch")
    for key, value in m5.ACCEPTED_RUNTIME_VERSIONS.items():
        if expected_versions[key] != value or runtime[key] != value:
            raise M6PilotError("identity_mismatch", key + " version is not the accepted runtime")
    caches = _exact_keys(environment["cache_isolation"], tuple(m5.runtime_isolation_paths("/tmp/m6-unused")), "identity_mismatch")
    evidence = os.path.dirname(caches["PYTHONPYCACHEPREFIX"])
    if os.path.basename(caches["PYTHONPYCACHEPREFIX"]) != m5.PYCACHE_DIRECTORY_NAME:
        raise M6PilotError("identity_mismatch", "Python cache prefix is not isolated")
    for path in caches.values():
        if not isinstance(path, str) or os.path.normpath(path) != path:
            raise M6PilotError("identity_mismatch", "runtime cache path is not canonical")
        if path != evidence and not path.startswith(evidence + os.sep):
            raise M6PilotError("identity_mismatch", "runtime cache escaped the evidence directory")
        for root in (MRES_ROOT, RNAGENESIS_ROOT):
            if path == root or path.startswith(root + os.sep):
                raise M6PilotError("identity_mismatch", "runtime cache is inside a git repository")
    _require_production_rng(manifest)
    return environment


def _require_production_rng(manifest):
    rng = _exact_keys(
        manifest["rng"],
        (
            "diffusion_generator_final_digest",
            "diffusion_generator_initial_digest",
            "diffusion_stream",
            "numpy_called_by_pilot",
            "permutation_generator_final_digest",
            "permutation_generator_initial_digest",
            "permutation_stream",
            "python_rng_final_digest",
            "python_rng_initial_digest",
            "streams_are_distinct",
            "torch_cpu_final_digest",
            "torch_cpu_initial_digest",
            "torch_cuda_final_digest",
            "torch_cuda_initial_digest",
            "train_permutation_digest",
            "train_permutation_seed",
            "validation_artifacts_regenerated",
            "validation_draw_seed",
        ),
        "incomplete_evidence_or_manifest",
    )
    for key, value in rng.items():
        if key.endswith("_digest") or key == "train_permutation_digest":
            if not _is_sha256(value):
                raise M6PilotError("incomplete_evidence_or_manifest", "RNG digest is not SHA-256: " + key)
    if rng["streams_are_distinct"] is not True or rng["permutation_stream"] == rng["diffusion_stream"]:
        raise M6PilotError("incomplete_evidence_or_manifest", "permutation and diffusion streams are not distinct")
    if rng["permutation_generator_final_digest"] == rng["diffusion_generator_final_digest"]:
        raise M6PilotError("incomplete_evidence_or_manifest", "dedicated generators did not diverge")
    if rng["numpy_called_by_pilot"] is not False or rng["validation_artifacts_regenerated"] is not False:
        raise M6PilotError("incomplete_evidence_or_manifest", "NumPy or regenerated validation draws were used")
    if rng["train_permutation_seed"] != PILOT_SEED or rng["validation_draw_seed"] != VALIDATION_DRAW_SEED:
        raise M6PilotError("identity_mismatch", "RNG seeds drifted")
    if rng["permutation_stream"] != "dedicated_cpu_train_permutation_generator":
        raise M6PilotError("identity_mismatch", "permutation stream drifted")
    if rng["diffusion_stream"] != "dedicated_cpu_diffusion_generator":
        raise M6PilotError("identity_mismatch", "diffusion stream drifted")
    return rng


def _require_production_accounting(manifest):
    accounting = _exact_keys(manifest["microbatch_accounting"], MICROBATCH_KEYS, "microbatch_arithmetic_invalid")
    if accounting["physical_microbatch"] != PHYSICAL_MICROBATCH or accounting["gradient_accumulation"] != GRADIENT_ACCUMULATION:
        raise M6PilotError("microbatch_arithmetic_invalid", "microbatch or accumulation drifted")
    if accounting["intended_effective_batch"] != INTENDED_EFFECTIVE_BATCH or accounting["microbatch_count"] != MICROBATCH_COUNT:
        raise M6PilotError("microbatch_arithmetic_invalid", "effective batch or microbatch count drifted")
    if accounting["optimizer_updates"] != OPTIMIZER_UPDATES or accounting["train_records"] != TRAIN_RECORD_COUNT:
        raise M6PilotError("microbatch_arithmetic_invalid", "update or record count drifted")
    if accounting["final_window_microbatch_sizes"] != list(FINAL_WINDOW) or accounting["final_window_examples"] != FINAL_WINDOW_EXAMPLES:
        raise M6PilotError("microbatch_arithmetic_invalid", "final window drifted")
    if accounting["final_window_weight_numerators"] != list(FINAL_WINDOW) or accounting["final_window_weight_denominator"] != FINAL_WINDOW_EXAMPLES:
        raise M6PilotError("microbatch_arithmetic_invalid", "final-window weights drifted")
    if accounting["drop_last"] is not False or accounting["final_window_weights_sum_to_one"] is not True:
        raise M6PilotError("microbatch_arithmetic_invalid", "final-window accounting drifted")
    if accounting["full_window_examples"] != INTENDED_EFFECTIVE_BATCH:
        raise M6PilotError("microbatch_arithmetic_invalid", "full window drifted")
    return accounting


def _require_production_optimizer(manifest):
    optimizer = _exact_keys(manifest["optimizer"], PRODUCTION_OPTIMIZER_KEYS, "incomplete_evidence_or_manifest")
    if optimizer["evidence_origin"] != "observed" or optimizer["name"] != "AdamW":
        raise M6PilotError("incomplete_evidence_or_manifest", "optimizer evidence drifted")
    if optimizer["precision"] != "fp32" or optimizer["mixed_precision"] != "no" or optimizer["weight_variant"] != "raw":
        raise M6PilotError("identity_mismatch", "precision or raw-weight policy drifted")
    if optimizer["ema_enabled"] is not False or optimizer["diffusers_cosine_constructor_used"] is not False:
        raise M6PilotError("incomplete_evidence_or_manifest", "EMA or the Diffusers cosine constructor was enabled")
    if optimizer["automatic_learning_rate_reduction_to_1e-5"] is not False or optimizer["learning_rate_sweep"] is not False:
        raise M6PilotError("automatic_lr_change_rejected", "an automatic learning-rate change is present")
    expected = {
        "beta1": ADAMW_BETA1,
        "beta2": ADAMW_BETA2,
        "epsilon": ADAMW_EPSILON,
        "gradient_clip_norm": GRADIENT_CLIP_NORM,
        "learning_rate": BASE_LEARNING_RATE,
        "weight_decay": ADAMW_WEIGHT_DECAY,
    }
    for key, value in expected.items():
        if optimizer[key] != format_decimal(value):
            raise M6PilotError("incomplete_evidence_or_manifest", "AdamW hyperparameter drifted: " + key)
    if manifest["applied_learning_rate_trace"] != [format_decimal(value) for value in applied_learning_rate_trace()]:
        raise M6PilotError("incomplete_evidence_or_manifest", "applied learning-rate trace is not the observed schedule")
    post = _exact_keys(
        manifest["post_update_21_scheduler_position"],
        ("applied_to_optimizer", "multiplier", "position", "pytorch_scheduler_last_epoch", "role"),
        "incomplete_evidence_or_manifest",
    )
    if post["position"] != POST_UPDATE_POSITION or post["multiplier"] != "0" or post["applied_to_optimizer"] is not False:
        raise M6PilotError("incomplete_evidence_or_manifest", "position 22 is not the unapplied schedule position")
    if post["role"] != "next_unapplied_schedule_position" or post["pytorch_scheduler_last_epoch"] is not None:
        raise M6PilotError("incomplete_evidence_or_manifest", "position 22 was recorded as a PyTorch last_epoch")
    evidence = _exact_keys(manifest["denoiser_update_evidence"], PRODUCTION_DENOISER_EVIDENCE_KEYS, "no_observed_denoiser_change")
    if evidence["evidence_origin"] != "observed" or evidence["any_unchanged_after_nonzero_lr"] is not False:
        raise M6PilotError("no_observed_denoiser_change", "denoiser-update evidence drifted")
    if evidence["applied_updates_checked"] != OPTIMIZER_UPDATES or evidence["checked_after_each_applied_update"] is not True:
        raise M6PilotError("no_observed_denoiser_change", "denoiser-update evidence did not cover 21 updates")
    return optimizer


def _require_production_roles(manifest):
    roles = _exact_keys(
        manifest["data_roles"],
        ("eval", "ref", "train_text", "validation_artifacts", "validation_csv"),
        "incomplete_evidence_or_manifest",
    )
    for role in roles.values():
        _exact_keys(role, PRODUCTION_ROLE_KEYS, "incomplete_evidence_or_manifest")
        if role["evidence_origin"] != "observed":
            raise M6PilotError("incomplete_evidence_or_manifest", "data role evidence is not observed")
    train = roles["train_text"]
    validation = roles["validation_csv"]
    artifacts = roles["validation_artifacts"]
    for role, expected_hash, expected_count, path in (
        (train, TRAIN_TEXT_SHA256, TRAIN_RECORD_COUNT, FUTURE_TRAIN_TEXT_PATH),
        (validation, VALIDATION_CSV_SHA256, VALIDATION_SEQUENCE_COUNT, FUTURE_VALIDATION_CSV_PATH),
    ):
        if role["opened"] is not True or role["observation_method"] != "streamed_sha256":
            raise M6PilotError("incomplete_evidence_or_manifest", role["role"] + " was not a streamed observation")
        if role["observed_sha256"] != expected_hash or role["expected_sha256"] != expected_hash:
            raise M6PilotError("identity_mismatch", role["role"] + " hash drifted")
        if role["observed_count"] != expected_count or role["expected_count"] != expected_count or role["path"] != path:
            raise M6PilotError("identity_mismatch", role["role"] + " count or path drifted")
        if isinstance(role["observed_byte_size"], bool) or not isinstance(role["observed_byte_size"], int) or role["observed_byte_size"] < 0:
            raise M6PilotError("identity_mismatch", role["role"] + " size was not observed")
    if artifacts["opened"] is not True or artifacts["observation_method"] != "streamed_sha256":
        raise M6PilotError("incomplete_evidence_or_manifest", "validation artifacts were not a streamed observation")
    if artifacts["observed_count"] != len(VALIDATION_ARTIFACT_FILES) or artifacts["expected_count"] != len(VALIDATION_ARTIFACT_FILES):
        raise M6PilotError("incomplete_evidence_or_manifest", "validation artifact count drifted")
    if artifacts["path"] != ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY:
        raise M6PilotError("identity_mismatch", "artifact directory drifted")
    expected_files = pinned_artifact_file_sha256()
    observed_files = _exact_keys(artifacts["observed_sha256"], VALIDATION_ARTIFACT_FILES, "incomplete_evidence_or_manifest")
    expected_role_files = _exact_keys(artifacts["expected_sha256"], VALIDATION_ARTIFACT_FILES, "incomplete_evidence_or_manifest")
    for name, digest in expected_files.items():
        if observed_files[name] != digest or expected_role_files[name] != digest or not _is_sha256(observed_files[name]):
            raise M6PilotError("identity_mismatch", "opened artifact hash drifted: " + name)
    if isinstance(artifacts["observed_byte_size"], bool) or not isinstance(artifacts["observed_byte_size"], int) or artifacts["observed_byte_size"] < 0:
        raise M6PilotError("identity_mismatch", "artifact byte size was not observed")
    for closed in (roles["ref"], roles["eval"]):
        if closed["opened"] is not False or closed["observation_method"] != "not_opened":
            raise M6PilotError("ref_or_eval_access", "REF or EVAL was opened")
        if closed["observed_sha256"] is not None or closed["observed_count"] != 0 or closed["path"] is not None:
            raise M6PilotError("ref_or_eval_access", "REF or EVAL observation is not closed")
        if closed["observed_byte_size"] is not None:
            raise M6PilotError("ref_or_eval_access", "REF or EVAL size was observed")
    access = _exact_keys(
        manifest["ref_eval_access"],
        ("eval_hash_metadata_only", "eval_opened", "ref_hash_metadata_only", "ref_opened"),
        "incomplete_evidence_or_manifest",
    )
    if access["ref_opened"] is not False or access["eval_opened"] is not False:
        raise M6PilotError("ref_or_eval_access", "REF or EVAL access is recorded")
    if access["ref_hash_metadata_only"] != REF_HASH_METADATA or access["eval_hash_metadata_only"] != EVAL_HASH_METADATA:
        raise M6PilotError("ref_or_eval_access", "REF or EVAL metadata drifted")
    if roles["ref"]["expected_sha256"] != REF_HASH_METADATA or roles["eval"]["expected_sha256"] != EVAL_HASH_METADATA:
        raise M6PilotError("ref_or_eval_access", "REF or EVAL expected hash drifted")
    return roles


def _require_production_validation_artifacts(manifest):
    artifacts = _exact_keys(manifest["validation_artifacts"], PRODUCTION_VALIDATION_ARTIFACT_KEYS, "identity_mismatch")
    if artifacts["evidence_origin"] != "observed" or artifacts["observation_method"] != "streamed_sha256":
        raise M6PilotError("identity_mismatch", "validation artifacts were not streamed observations")
    if artifacts["sequence_order_source"] != "loaded_manifest":
        raise M6PilotError("identity_mismatch", "sequence-order hash was not read from the loaded artifact")
    if artifacts["draws"] != VALIDATION_DRAWS or artifacts["sequence_count"] != VALIDATION_SEQUENCE_COUNT:
        raise M6PilotError("identity_mismatch", "validation draw shape drifted")
    if artifacts["timestep_shape"] != list(VALIDATION_TIMESTEP_SHAPE) or artifacts["noise_shape"] != list(VALIDATION_NOISE_SHAPE):
        raise M6PilotError("identity_mismatch", "validation tensor shape drifted")
    expected = {
        "draw_manifest_sha256": VALIDATION_DRAW_MANIFEST_SHA256,
        "hash_report_sha256": VALIDATION_HASH_REPORT_SHA256,
        "noise_sha256": VALIDATION_NOISE_SHA256,
        "order_artifact_sha256": VALIDATION_ORDER_ARTIFACT_SHA256,
        "sequence_order_sha256": VALIDATION_SEQUENCE_ORDER_SHA256,
        "timestep_sha256": VALIDATION_TIMESTEPS_SHA256,
        "validation_csv_sha256": VALIDATION_CSV_SHA256,
    }
    for key, digest in expected.items():
        if artifacts[key] != digest or not _is_sha256(artifacts[key]):
            raise M6PilotError("identity_mismatch", "validation artifact identity drifted: " + key)
    files = _exact_keys(artifacts["observed_files"], VALIDATION_ARTIFACT_FILES, "identity_mismatch")
    names = {
        "validation_draw_manifest.json": VALIDATION_DRAW_MANIFEST_SHA256,
        "validation_draw_manifest_sha256.json": VALIDATION_HASH_REPORT_SHA256,
        "validation_noise.float32": VALIDATION_NOISE_SHA256,
        "validation_order_artifact.csv": VALIDATION_ORDER_ARTIFACT_SHA256,
        "validation_timesteps.int64": VALIDATION_TIMESTEPS_SHA256,
    }
    total = 0
    for name, digest in names.items():
        record = _exact_keys(files[name], ASSET_RECORD_KEYS, "identity_mismatch")
        if record["observation_method"] != "streamed_sha256" or record["evidence_origin"] != "observed":
            raise M6PilotError("identity_mismatch", "artifact file was not streamed: " + name)
        if record["sha256"] != digest or record["expected_sha256"] != digest or record["role"] != name:
            raise M6PilotError("identity_mismatch", "artifact file hash drifted: " + name)
        if record["regular_file"] is not True or record["symlink"] is not False:
            raise M6PilotError("identity_mismatch", "artifact file is not a regular file: " + name)
        if isinstance(record["byte_size"], bool) or not isinstance(record["byte_size"], int) or record["byte_size"] < 0:
            raise M6PilotError("identity_mismatch", "artifact file size was not observed: " + name)
        if record["byte_size"] != record["expected_byte_size"]:
            raise M6PilotError("identity_mismatch", "artifact file size drifted: " + name)
        total += record["byte_size"]
    if manifest["data_roles"]["validation_artifacts"]["observed_byte_size"] != total:
        raise M6PilotError("identity_mismatch", "artifact byte size does not match the streamed files")
    role_hashes = manifest["data_roles"]["validation_artifacts"]["observed_sha256"]
    for name, record in files.items():
        if role_hashes[name] != record["sha256"]:
            raise M6PilotError("identity_mismatch", "artifact role hash was not the streamed file hash")
    return artifacts


def _require_production_loop(manifest):
    observations = manifest["train_update_observations"]
    if not isinstance(observations, list) or len(observations) != OPTIMIZER_UPDATES:
        raise M6PilotError("incomplete_evidence_or_manifest", "train observations are not 21 real updates")
    for index, item in enumerate(observations, start=1):
        _exact_keys(
            item,
            (
                "applied_clip_norm",
                "clipped",
                "denoiser_change",
                "evidence_origin",
                "learning_rate",
                "learning_rate_recorded_before_optimizer_step",
                "pre_clip_gradient_norm",
                "stop_fired",
                "training_loss",
                "update",
            ),
            "incomplete_evidence_or_manifest",
        )
        if item["update"] != index or item["evidence_origin"] != "observed" or item["learning_rate_recorded_before_optimizer_step"] is not True:
            raise M6PilotError("incomplete_evidence_or_manifest", "update evidence is not observed")
        if item["stop_fired"] is not False:
            raise M6PilotError("incomplete_evidence_or_manifest", "a training update records a fired stop")
        if item["learning_rate"] != format_decimal(applied_learning_rate(index)):
            raise M6PilotError("learning_rate_schedule_invalid", "update learning rate drifted")
        _nonnegative_decimal_string(item["training_loss"])
        _nonnegative_decimal_string(item["pre_clip_gradient_norm"])
        _nonnegative_decimal_string(item["applied_clip_norm"])
        change = _exact_keys(
            item["denoiser_change"],
            ("changed", "finite_nonzero_gradient", "flat_index", "gradient", "parameter_name", "value_after", "value_before"),
            "no_observed_denoiser_change",
        )
        if change["changed"] is not True or change["finite_nonzero_gradient"] is not True:
            raise M6PilotError("no_observed_denoiser_change", "denoiser change was not observed")
        if isinstance(change["flat_index"], bool) or not isinstance(change["flat_index"], int) or change["flat_index"] < 0:
            raise M6PilotError("no_observed_denoiser_change", "denoiser element index is missing")
        if not isinstance(change["parameter_name"], str) or change["parameter_name"] == "":
            raise M6PilotError("no_observed_denoiser_change", "denoiser parameter name is missing")
        before = _finite_decimal_string(change["value_before"])
        after = _finite_decimal_string(change["value_after"])
        gradient = _finite_decimal_string(change["gradient"])
        if before == after or gradient == 0.0 or not math.isfinite(gradient):
            raise M6PilotError("no_observed_denoiser_change", "denoiser element did not change under a nonzero gradient")
    validation = manifest["validation_observations"]
    if [item["update"] for item in validation] != list(VALIDATION_UPDATES):
        raise M6PilotError("validation_schedule_invalid", "validation observations are not updates 0, 7, 14, and 21")
    for item in validation:
        _exact_keys(
            item,
            (
                "aggregate_mse",
                "evidence_origin",
                "pair_count",
                "relative_to_update_0",
                "tensors_loaded",
                "tensors_regenerated",
                "update",
                "weight_variant",
            ),
            "incomplete_evidence_or_manifest",
        )
        if item["evidence_origin"] != "observed" or item["pair_count"] != VALIDATION_PAIR_COUNT:
            raise M6PilotError("incomplete_evidence_or_manifest", "validation pair count was not observed")
        if item["tensors_loaded"] is not True or item["tensors_regenerated"] is not False or item["weight_variant"] != "raw":
            raise M6PilotError("identity_mismatch", "validation tensors were not the stored raw-weight draws")
        _nonnegative_decimal_string(item["aggregate_mse"])
    aggregates = {item["update"]: item["aggregate_mse"] for item in validation}
    for item in validation:
        relative = item["relative_to_update_0"]
        if item["update"] == 0:
            if relative is not None:
                raise M6PilotError("validation_schedule_invalid", "update 0 relative evidence must be null")
            continue
        relative = _exact_keys(relative, REVIEW_ITEM_KEYS, "incomplete_evidence_or_manifest")
        _require_relative_validation_consistency(relative, aggregates[0], item["aggregate_mse"])
    return True


def _require_relative_validation_consistency(item, initial_mse, later_mse):
    """Reject a review item whose numbers or policy flags contradict the aggregates."""
    if item["update"] not in (7, 14, 21):
        raise M6PilotError("validation_schedule_invalid", "relative validation is recorded at updates 7, 14, and 21")
    if item["initial"] != initial_mse or item["later"] != later_mse:
        raise M6PilotError("incomplete_evidence_or_manifest", "validation review values do not match the aggregate MSE")
    initial = _finite_decimal_string(item["initial"])
    later = _finite_decimal_string(item["later"])
    if item["delta"] != format_decimal(later - initial):
        raise M6PilotError("incomplete_evidence_or_manifest", "validation delta is not later minus initial")
    worsened = later > initial
    if item["finite_worsening"] is not worsened or item["human_review_signal"] is not worsened:
        raise M6PilotError("incomplete_evidence_or_manifest", "validation worsening flags do not match later > initial")
    if item["automatic_early_stop"] is not False or item["automatic_learning_rate_change"] is not False or item["numeric_cutoff"] is not None:
        raise M6PilotError("automatic_lr_change_rejected", "a finite validation change must not stop or retune the run")
    return True


def _require_production_timing(manifest):
    timing = _exact_keys(manifest["timing"], PRODUCTION_TIMING_KEYS, "incomplete_evidence_or_manifest")
    if timing["evidence_origin"] != "observed" or timing["synchronization"] != "cuda_synchronize_before_and_after_each_region":
        raise M6PilotError("incomplete_evidence_or_manifest", "timing was not synchronized")
    if timing["checkpoint_time_excluded_from_training_and_validation"] is not True:
        raise M6PilotError("incomplete_evidence_or_manifest", "checkpoint time was folded into training or validation")
    if timing["validation_excluded_from_training_updates"] is not True:
        raise M6PilotError("incomplete_evidence_or_manifest", "validation time was folded into training updates")
    updates = timing["training_update_seconds"]
    if not isinstance(updates, list) or len(updates) != OPTIMIZER_UPDATES:
        raise M6PilotError("incomplete_evidence_or_manifest", "training timing is not 21 update durations")
    _require_decimal_sum(updates, timing["training_seconds"], "training-update time is not the sum of the 21 update durations")
    spans = timing["validation_update_seconds"]
    if not isinstance(spans, list) or [item.get("update") for item in spans] != list(VALIDATION_UPDATES):
        raise M6PilotError("incomplete_evidence_or_manifest", "validation timing is not updates 0, 7, 14, and 21")
    for item in spans:
        _exact_keys(item, TIMING_SPAN_KEYS, "incomplete_evidence_or_manifest")
        _nonnegative_decimal_string(item["seconds"])
    _require_decimal_sum(
        [item["seconds"] for item in spans],
        timing["validation_seconds"],
        "validation time is not the sum of the four validation durations",
    )
    checkpoints = timing["checkpoint_save_reload_seconds"]
    if not isinstance(checkpoints, list) or [item.get("update") for item in checkpoints] != list(RETAINED_WEIGHT_UPDATES):
        raise M6PilotError("incomplete_evidence_or_manifest", "checkpoint timing is not updates 7, 14, and 21")
    for item in checkpoints:
        _exact_keys(item, TIMING_SPAN_KEYS, "incomplete_evidence_or_manifest")
        _nonnegative_decimal_string(item["seconds"])
    return timing


def _require_production_frozen(manifest):
    frozen = _exact_keys(manifest["frozen_state"], PRODUCTION_FROZEN_KEYS, "modified_or_trainable_encdec")
    if frozen["evidence_origin"] != "observed" or frozen["all_frozen"] is not True:
        raise M6PilotError("modified_or_trainable_encdec", "frozen evidence is not observed")
    if frozen["components"] != list(ENCDEC_COMPONENTS):
        raise M6PilotError("modified_or_trainable_encdec", "frozen components drifted")
    if frozen["encdec_requires_grad_false"] is not True or frozen["encdec_eval_mode"] is not True:
        raise M6PilotError("modified_or_trainable_encdec", "EncDec was not frozen in eval mode")
    if frozen["encdec_parameters_absent_from_optimizer"] is not True or frozen["encdec_buffers_absent_from_optimizer"] is not True:
        raise M6PilotError("modified_or_trainable_encdec", "an EncDec parameter or buffer is in the optimizer")
    if frozen["optimizer_parameter_ids_equal_trainable_denoiser"] is not True or frozen["optimizer_contains_only_denoiser"] is not True:
        raise M6PilotError("modified_or_trainable_encdec", "optimizer membership was not the trainable denoiser")
    if frozen["optimizer_contains_encdec"] is not False:
        raise M6PilotError("modified_or_trainable_encdec", "optimizer contains EncDec")
    if frozen["rotary_caches_excluded_from_persistent_buffer_digest"] is not True or not isinstance(frozen["rotary_cache_names"], list):
        raise M6PilotError("modified_or_trainable_encdec", "rotary caches were not excluded from the EncDec buffer digest")
    parameter_digests = [
        frozen["encdec_parameter_digest_at_initialization"],
        frozen["encdec_parameter_digest_after_update_7"],
        frozen["encdec_parameter_digest_after_update_14"],
        frozen["encdec_parameter_digest_after_update_21"],
    ]
    buffer_digests = [
        frozen["encdec_persistent_buffer_digest_at_initialization"],
        frozen["encdec_persistent_buffer_digest_after_update_7"],
        frozen["encdec_persistent_buffer_digest_after_update_14"],
        frozen["encdec_persistent_buffer_digest_after_update_21"],
    ]
    if any(not _is_sha256(item) for item in parameter_digests + buffer_digests):
        raise M6PilotError("modified_or_trainable_encdec", "EncDec state digest is missing")
    if len(set(parameter_digests)) != 1 or len(set(buffer_digests)) != 1:
        raise M6PilotError("modified_or_trainable_encdec", "EncDec parameter or persistent-buffer digest changed")
    return frozen


def _require_production_review(manifest):
    review = _exact_keys(
        manifest["validation_review"],
        ("automatic_early_stop", "automatic_learning_rate_change", "numeric_catastrophic_cutoff", "observations"),
        "automatic_lr_change_rejected",
    )
    if review["numeric_catastrophic_cutoff"] is not None or review["automatic_early_stop"] is not False:
        raise M6PilotError("automatic_lr_change_rejected", "validation worsening is not an automatic stop")
    if review["automatic_learning_rate_change"] is not False:
        raise M6PilotError("automatic_lr_change_rejected", "validation worsening must not change the learning rate")
    observations = review["observations"]
    if [item.get("update") for item in observations] != [7, 14, 21]:
        raise M6PilotError("validation_schedule_invalid", "validation review is not updates 7, 14, and 21")
    relatives = {
        item["update"]: item["relative_to_update_0"]
        for item in manifest["validation_observations"]
        if item["update"] != 0
    }
    aggregates = {item["update"]: item["aggregate_mse"] for item in manifest["validation_observations"]}
    for item in observations:
        _exact_keys(item, REVIEW_ITEM_KEYS, "automatic_lr_change_rejected")
        _require_relative_validation_consistency(item, aggregates[0], aggregates[item["update"]])
        if item != relatives[item["update"]]:
            raise M6PilotError("incomplete_evidence_or_manifest", "validation review does not match the observation relative record")
    return review


def _require_production_restart(manifest):
    policy = _exact_keys(manifest["restart_policy"], tuple(interruption_policy()), "incomplete_evidence_or_manifest")
    if policy != interruption_policy() or manifest["resume_supported"] is not False:
        raise M6PilotError("incomplete_evidence_or_manifest", "restart policy drifted")
    return policy


def _require_production_checkpoints(manifest):
    checkpoints = manifest["weight_checkpoints"]
    if [item["update"] for item in checkpoints] != list(RETAINED_WEIGHT_UPDATES):
        raise M6PilotError("checkpoint_save_reload_incompatibility", "retained checkpoints are not updates 7, 14, and 21")
    for item in checkpoints:
        _exact_keys(item, CHECKPOINT_PROOF_KEYS, "checkpoint_save_reload_incompatibility")
        if item["evidence_origin"] != "observed" or item["fresh_load_succeeded"] is not True:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint reload was not observed")
        if item["original_object_id"] == item["reloaded_object_id"] or item["weight_reload_is_training_resume"] is not False:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "reload is not a distinct non-resume object")
        if item["resume_supported"] is not False or item["state_scope"] != "parameters_and_persistent_buffers":
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint scope is not the complete non-resume state")
        inventory = _exact_keys(item["saved_hashes"], CHECKPOINT_MEMBERS, "checkpoint_save_reload_incompatibility")
        for name in CHECKPOINT_MEMBERS:
            if not _is_sha256(inventory[name]):
                raise M6PilotError("checkpoint_save_reload_incompatibility", "saved member hash is missing: " + name)
        comparison = _exact_keys(item["state_comparison"], STATE_COMPARISON_KEYS, "checkpoint_save_reload_incompatibility")
        if comparison["comparison_selection"] != "complete" or comparison["complete_state_equal"] is not True:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint comparison is not complete")
        if comparison["includes_persistent_buffers"] is not True or comparison["weight_reload_is_training_resume"] is not False:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint comparison omitted persistent buffers")
        if comparison["compared_parameter_count"] < 4 or comparison["mismatched_parameter_count"] != 0:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint comparison is not complete")
        if not _is_sha256(comparison["aggregate_digest"]) or not _is_sha256(comparison["parameter_names_sha256"]):
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint aggregate digest is missing")
        if comparison["tensor_comparison"] not in ("torch.equal", "exact_value"):
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint comparison is not tensor-safe")
        if not isinstance(comparison["entry_digests"], dict) or len(comparison["entry_digests"]) != comparison["compared_parameter_count"]:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint entry digests are incomplete")
        for digest in comparison["entry_digests"].values():
            if not _is_sha256(digest):
                raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint entry digest is missing")
        configuration = _exact_keys(item["configuration"], CONFIGURATION_PROOF_KEYS, "checkpoint_save_reload_incompatibility")
        if configuration["ignored_top_level_keys"] != ["_name_or_path"] or configuration["configuration_compatible"] is not True:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "configuration allowlist drifted")
        if configuration["normalized_sha256_equal"] is not True:
            raise M6PilotError("checkpoint_save_reload_incompatibility", "reloaded denoiser configuration is incompatible")
        _require_checkpoint_digest_consistency(configuration, comparison)
    return checkpoints


def _require_checkpoint_digest_consistency(configuration, comparison):
    """Reject configuration and state digests that contradict the recorded entries."""
    for key in (
        "original_normalized_sha256",
        "original_raw_sha256",
        "reloaded_normalized_sha256",
        "reloaded_raw_sha256",
    ):
        if not _is_sha256(configuration[key]):
            raise M6PilotError("checkpoint_save_reload_incompatibility", "configuration digest is not SHA-256")
    raw_equal = configuration["original_raw_sha256"] == configuration["reloaded_raw_sha256"]
    normalized_equal = configuration["original_normalized_sha256"] == configuration["reloaded_normalized_sha256"]
    if configuration["raw_sha256_equal"] is not raw_equal or configuration["normalized_sha256_equal"] is not normalized_equal:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "configuration equality flags do not match the digests")
    if configuration["configuration_compatible"] is not normalized_equal:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "configuration compatibility does not match normalized equality")
    for digest in comparison["entry_digests"].values():
        if not _is_sha256(digest):
            raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint entry digest is missing")
    inventory = state_inventory_digests(comparison["entry_digests"])
    if comparison["aggregate_digest"] != inventory["aggregate_digest"]:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint aggregate digest does not match the ordered entry digests")
    if comparison["parameter_names_sha256"] != inventory["parameter_names_sha256"]:
        raise M6PilotError("checkpoint_save_reload_incompatibility", "checkpoint parameter-name digest does not match the entry names")
    return True


def _require_production_stops(manifest):
    stops = _exact_keys(manifest["stop_conditions"], STOP_CONDITION_CODES, "incomplete_evidence_or_manifest")
    for code in STOP_CONDITION_CODES:
        _exact_keys(stops[code], ("fired",), "incomplete_evidence_or_manifest")
        if stops[code] != {"fired": False}:
            raise M6PilotError("incomplete_evidence_or_manifest", "a stop condition fired or is incomplete: " + code)
    return stops

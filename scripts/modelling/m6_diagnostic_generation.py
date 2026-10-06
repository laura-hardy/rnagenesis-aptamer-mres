#!/usr/bin/env python3
"""M6 update-21 diagnostic generation (inactive).

The checked-in configuration is inactive and non-consumable. An inactive
document is refused before the length vector, the checkpoint, TRAIN, the
accepted B1 pool, a GPU, or the filesystem is touched. A later
authorisation-only commit may change only the configuration. It binds one
GPU, one new output directory, and the implementation file hashes. This
module defines the active schema that commit must satisfy. Nothing here is
reachable from the command line except ``--help``.

The stage reuses the accepted M4 machinery instead of copying it. The
B1 development-pool runner supplies the schedule builder, the generation
invocation contract, the output mapper, the attempt accounting and the
ledger serialisers. The M4 metrics module supplies the five hard
guardrails. The approved M1 cleaner supplies the only normalisation rule.
All three are loaded from hash-verified source bytes.

Exactly 1,000 raw attempts are generated from the raw update-21
checkpoint, on the accepted schedule. Nothing is padded, trimmed beyond the
approved cleaner, replaced, resampled, or dropped. The accepted B1 pool is
read as evidence and compared. It is never regenerated.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import types

MRES_ROOT = "/home/laura/rnagenesis-aptamer-mres"
RNAGENESIS_ROOT = "/home/laura/RNAGenesis"
RUN_ROOT = "/home/laura/rnagenesis-mres-runs"
CONFIG_RELATIVE = "config/experiments/D1_update21_diagnostic_generation.yaml"
CONFIG_PATH = os.path.join(MRES_ROOT, CONFIG_RELATIVE)
MODULE_RELATIVE = "scripts/modelling/m6_diagnostic_generation.py"
MODULE_PATH = os.path.join(MRES_ROOT, MODULE_RELATIVE)
B1_RUNNER_RELATIVE = "scripts/b1_development_pool_runner.py"
B1_RUNNER_SHA256 = "622684b254f911ca4d00db8af20d0d0c67eeebf46007e3fe84995e1e11db2341"
METRICS_RELATIVE = "scripts/modelling/m4_diagnostic_metrics.py"
METRICS_SHA256 = "eebb6c8faf0d909bd907cd1e1e09c75908676ffe3e4eb04842f09b943b9d9e56"
METRICS_CONFIG_RELATIVE = "config/modelling/validation_metrics_v1.yaml"
METRICS_CONFIG_SHA256 = "d30006c6f2b94be89ee2c7721b701e76e6835142a1af9f49997ba0d5baadf4bb"
CONTRACT_RELATIVE = "scripts/modelling/m6_pilot_contract.py"
M5_CONTRACT_RELATIVE = "scripts/modelling/m5_smoke_contract.py"
TEST_RELATIVE = "tests/modelling/test_m6_diagnostic_generation.py"
IMPLEMENTATION_FILE_PATHS = (
    B1_RUNNER_RELATIVE,
    METRICS_RELATIVE,
    METRICS_CONFIG_RELATIVE,
    CONTRACT_RELATIVE,
    M5_CONTRACT_RELATIVE,
    MODULE_RELATIVE,
    TEST_RELATIVE,
)
PERMITTED_AUTHORIZATION_FILES = (CONFIG_RELATIVE,)

INACTIVE_STATUS = "M6_UPDATE21_DIAGNOSTIC_READY_FOR_REVIEW_NOT_AUTHORISED"
ACTIVE_STATUS = "M6_UPDATE21_DIAGNOSTIC_AUTHORISED_FOR_SINGLE_USE_EXECUTION"
SCHEMA_VERSION = "m6-diagnostic-config-1"
MANIFEST_SCHEMA_VERSION = "m6-diagnostic-manifest-1"
EXPERIMENT_ID = "D1_update21_diagnostic_generation"
ACTIVE_PHASE = "M6_D1_update21_diagnostic_generation"
ACTIVE_SCOPE = "single_use_m6_d1_update21_diagnostic"
ACTIVE_ACTIVATION = "active_unconsumed"
INACTIVE_ACTIVATION = "inactive_no_authorisation"
SESSION_PATTERN = "m5_single_use_timestamp_and_scope"
CONSUMPTION_EVENT = "bound_output_directory_creation"
LOGICAL_DEVICE = "cuda:0"
RNAGENESIS_BRANCH = "mres-d1-diffusion-finetune"
RNAGENESIS_COMMIT = "e3b855bbf4d1af376f43747643fa30afd662828c"
PINNED_PYTHON = "/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"

# The roles an authorisation may grant. VALIDATION is not requested: no
# approved report-only diagnostic needs it. REF and EVAL are unreachable.
ACTIVE_ROLES = (
    "ACCEPTED_B1_POOL_EVIDENCE",
    "ACCEPTED_SCHEDULE",
    "FROZEN_ENCDEC",
    "TRAIN_TEXT_DIAGNOSTIC_ONLY",
    "UPDATE21_CHECKPOINT",
)
DENIED_ROLES = ("REF", "EVAL", "VALIDATION_CSV", "VALIDATION_ARTIFACT")

TRAINING_ATTEMPT_ID = "m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6"
TRAINING_EVIDENCE_DIRECTORY = RUN_ROOT + "/" + TRAINING_ATTEMPT_ID
TRAINING_MANIFEST_SHA256 = "4b24d5bf5bc392a8f6ee4b8af91adb3582e3a17cac459559632494ec64f8ae52"
TRAINING_MANIFEST_BYTES = 159013
TRAINING_CONSUMPTION_SHA256 = "ec822747cca4916331fd7a79dd504a54c425bc7699457ca6d85e9b0c446f0874"
TRAINING_CONSUMPTION_BYTES = 560
TRAINING_AUTHORIZATION_COMMIT = "15f49a17081f573970495891e9283a17fc5c3dc2"
TRAINING_IMPLEMENTATION_COMMIT = "6fd611589d7a3365b793c2ca64cf13c29ef5bfc1"
CHECKPOINT_UPDATE = 21
CHECKPOINT_DIRECTORY_NAME = (
    "D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-42__update-21__git-"
    + TRAINING_IMPLEMENTATION_COMMIT
)
CHECKPOINT_MEMBERS = {
    "model_index.json": ("05ac20f9fd3bd818ec88b37ff35e482ac80c5f5329666ecdfbe9227aa045b70e", 217),
    "scheduler/scheduler_config.json": ("6b470b030031daa7c812ef9a6dfe49f14fa695c17a939406f1c780bad6a91396", 492),
    "unet/config.json": ("42c864c81e35ef1a0c7964a3642492fba95c9e24a153407f9fd98855b20d9d70", 560),
    "unet/diffusion_pytorch_model.safetensors": (
        "47b2dc9b392ea766eee7e947f0f92f5a039c42ac714326104e719352d20b5924",
        7847725416,
    ),
}
WEIGHT_MEMBER = "unet/diffusion_pytorch_model.safetensors"
SCHEDULE_DIRECTORY = RUN_ROOT + "/m4_b1_development_pool_schedule_d2b2041520d1"
SCHEDULE_SHA256 = "0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0"
LENGTH_VECTOR_SHA256 = "7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c"
INVOCATION_COUNT = 112
ATTEMPT_COUNT = 1000
B1_POOL_DIRECTORY = RUN_ROOT + "/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1"
B1_POOL_FILES = {
    "development_pool_audited_attempts.jsonl": (
        "3aad5a0cd59405aca52a9800c47c1fe8f70e474d68b8a602e5fb1b8f5e14e150",
        530720,
    ),
    "development_pool_raw_attempts.jsonl": (
        "086d26458fc2363017c812dc65cb0440185ad6b4f8cfe4fc3377dfa74c5f292a",
        222388,
    ),
    "development_pool_metrics.json": (
        "5c927839c94d78d575d787392da137c28f1310ef637b57bbb8b500e7dbf9b3ea",
        76776,
    ),
    "development_pool_manifest.json": (
        "6a3e3be9d589443e82f2f8b0321c445e96f0f989b4984ec8c25ce10db48927c8",
        82416,
    ),
}
TRAIN_PATH = "/home/laura/rnagenesis-mres-data/development/corpus_final.txt"
TRAIN_SHA256 = "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d"
TRAIN_BYTES = 37700
TRAIN_COUNT = 669
CLEANER_SHA256 = "4d0c56a7d931a2c3c5c049cfeabd4937134b3d1125ef7a68b10472527d2fd2a2"
ENCDEC_ROLES = ("encdec_config", "encdec_weights", "biomap_encoder_config", "decoder_config", "tokenizer")

CONSUMPTION_RECORD_NAME = "authorization_consumption.json"
FAILURE_RECORD_NAME = "authorization_failure.json"
SCHEDULE_COPY_NAME = "m6_diagnostic_schedule.json"
RAW_LEDGER_NAME = "m6_diagnostic_raw_attempts.jsonl"
AUDITED_LEDGER_NAME = "m6_diagnostic_audited_attempts.jsonl"
INVOCATION_MANIFEST_NAME = "m6_diagnostic_invocation_outputs.json"
METRICS_NAME = "m6_diagnostic_metrics.json"
GUARDRAILS_NAME = "m6_diagnostic_guardrails.json"
REPORT_NAME = "m6_diagnostic_report.json"
MANIFEST_NAME = "m6_diagnostic_manifest.json"
HASH_REPORT_NAME = "m6_diagnostic_manifest_sha256.json"
GENERATION_OUTPUT_DIRECTORY = "rnagenesis_generation_output"

HARD_GUARDRAIL_RULES = (
    ("valid_nonempty_acgu_fraction", "minimum", 0.99, "raw_attempts"),
    ("empty_or_unparseable_fraction", "maximum", 0.01, "raw_attempts"),
    ("unique_fraction", "minimum", 0.95, "valid_outputs"),
    ("exact_train_match_rate", "maximum", 0.01, "valid_outputs"),
    ("largest_duplicate_share", "maximum", 0.01, "valid_outputs"),
)
REPORT_ONLY_ITEMS = (
    "requested_length_exact_hit_rate",
    "per_requested_length_exact_hit_rate",
    "nearest_train_normalized_edit_distance",
    "maximum_edit_similarity_to_train",
    "nucleotide_distribution",
    "dinucleotide_distribution",
    "mfe",
    "mfe_per_nucleotide",
    "paired_fraction",
    "full_length_stratified_results",
)
DEFERRED_ITEMS = (
    "clustering_identity_threshold",
    "clustering_dependent_claims",
    "frozen_representation_or_embedding_metrics",
)
BASES = "ACGU"
DINUCLEOTIDES = tuple(a + b for a in BASES for b in BASES)
BODY_PATTERN = re.compile(r"^[ACGU]+$")
TIMESTAMP_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+[0-9]{2}:[0-9]{2}$")
EDIT_SIMILARITY_DEFINITION = (
    "1 - minimum over TRAIN of (Levenshtein distance / length of the longer sequence); "
    "an edit-based similarity, not a sequence identity"
)
OTHER_UPDATE_PATTERN = re.compile(r"update-(?!21__)[0-9]+__")


class DiagnosticError(Exception):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        self.secondary_failure = None
        super().__init__(code + ": " + detail)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"


def _is_sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_sha40(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


# ---------------------------------------------------------------- reuse

_MODULES = {}


def _load_verified(name, path, expected_sha256, read_bytes=None):
    """Compile and execute preflight bytes. The file is not read again."""
    reader = read_bytes or _default_read_bytes
    payload = bytes(reader(path))
    if sha256_bytes(payload) != expected_sha256:
        raise DiagnosticError("provenance_mismatch", "reused source does not match its pinned hash: " + os.path.basename(path))
    if payload.startswith(b"\xef\xbb\xbf") or b"\x00" in payload:
        raise DiagnosticError("provenance_mismatch", "reused source is not accepted")
    module = types.ModuleType(name)
    module.__file__ = path
    module.__package__ = ""
    exec(compile(payload, path, "exec", dont_inherit=True), module.__dict__)
    return module


def b1_runner(read_bytes=None):
    if "b1" not in _MODULES:
        _MODULES["b1"] = _load_verified(
            "m6_diagnostic_b1_runner", os.path.join(MRES_ROOT, B1_RUNNER_RELATIVE), B1_RUNNER_SHA256, read_bytes
        )
    return _MODULES["b1"]


def m6_contract():
    """Reuse the M6 contract for path denial, tree observation and file hashing."""
    if "m6" not in _MODULES:
        path = os.path.join(MRES_ROOT, CONTRACT_RELATIVE)
        spec = importlib.util.spec_from_file_location("m6_diagnostic_m6_contract", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULES["m6"] = module
    return _MODULES["m6"]


def _translate(operation):
    contract = m6_contract()
    try:
        return operation()
    except contract.M6PilotError as exc:
        raise DiagnosticError(exc.code, exc.detail)


def _default_read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


# ---------------------------------------------------------------- pins

def production_pins():
    return {
        "training_evidence": {
            "directory": TRAINING_EVIDENCE_DIRECTORY,
            "run_id": TRAINING_ATTEMPT_ID,
            "authorization_commit": TRAINING_AUTHORIZATION_COMMIT,
            "executing_implementation_commit": TRAINING_IMPLEMENTATION_COMMIT,
            "manifest": {"name": "m6_pilot_manifest.json", "sha256": TRAINING_MANIFEST_SHA256, "bytes": TRAINING_MANIFEST_BYTES},
            "consumption": {
                "name": CONSUMPTION_RECORD_NAME,
                "sha256": TRAINING_CONSUMPTION_SHA256,
                "bytes": TRAINING_CONSUMPTION_BYTES,
            },
        },
        "checkpoint": {
            "update": CHECKPOINT_UPDATE,
            "directory": TRAINING_EVIDENCE_DIRECTORY + "/" + CHECKPOINT_DIRECTORY_NAME,
            "members": {name: {"sha256": digest, "bytes": size} for name, (digest, size) in CHECKPOINT_MEMBERS.items()},
        },
        "schedule": {
            "directory": SCHEDULE_DIRECTORY,
            "length_vector": {"name": "ordered_train_length_vector.json", "sha256": LENGTH_VECTOR_SHA256, "bytes": 2022},
            "schedule": {"name": "development_pool_schedule.json", "sha256": SCHEDULE_SHA256, "bytes": 30125},
            "attempts": ATTEMPT_COUNT,
            "invocations": INVOCATION_COUNT,
        },
        "b1_pool": {
            "directory": B1_POOL_DIRECTORY,
            "files": {name: {"sha256": digest, "bytes": size} for name, (digest, size) in B1_POOL_FILES.items()},
        },
        "train": {"path": TRAIN_PATH, "sha256": TRAIN_SHA256, "bytes": TRAIN_BYTES, "count": TRAIN_COUNT},
    }


def expected_static_sections(pins=None):
    """The configuration sections that never change between inactive and active."""
    pins = production_pins() if pins is None else pins
    sections = {
        "pinned_inputs": pins,
        "diagnostic_design": {
            "checkpoint_update": CHECKPOINT_UPDATE,
            "weight_variant": "raw",
            "ema_weights": False,
            "other_checkpoint_updates_loaded": False,
            "raw_attempts": ATTEMPT_COUNT,
            "invocation_count": INVOCATION_COUNT,
            "schedule_sha256": SCHEDULE_SHA256,
            "length_vector_sha256": LENGTH_VECTOR_SHA256,
            "target_length_sampling_seed": 43000,
            "generation_seed_base": 44000,
            "max_chunk_size": 16,
            "batch_num": 1,
            "max_seq_len_rule": "requested_length_plus_1",
            "ddim_steps": 50,
            "schedule_reused_not_regenerated": True,
            "b1_pool": "accepted_evidence_read_only_never_regenerated",
            "normalisation": {
                "authority": "approved_m1_cleaner",
                "cleaner_sha256": CLEANER_SHA256,
                "rule": "leading_and_trailing_runs_of_1_and_2_removed_then_nonempty_ACGU_required",
                "raw_text_retained_beside_normalised_text": True,
                "additional_trimming": False,
                "padding": False,
                "suffix_removal_beyond_the_approved_cleaner": False,
                "rejection": False,
                "replacement": False,
                "resampling": False,
                "dropping": False,
            },
            "denominators": {
                "valid_nonempty_acgu_fraction": "raw_attempts",
                "empty_or_unparseable_fraction": "raw_attempts",
                "unique_fraction": "valid_outputs",
                "exact_train_match_rate": "valid_outputs",
                "largest_duplicate_share": "valid_outputs",
                "requested_length_exact_hit_rate": "raw_attempts",
            },
            "invalid_empty_duplicate_early_eos_and_length_mismatched_attempts_remain_counted": True,
        },
        "hard_guardrails": {
            "rules": [
                {"id": rule_id, "comparison": comparison, "threshold": threshold, "denominator": denominator}
                for rule_id, comparison, threshold, denominator in HARD_GUARDRAIL_RULES
            ],
            "requested_length_exact_hit_rate_is_a_threshold": False,
            "historical_0_90_and_0_50_enforced": False,
            "any_failure_makes_the_checkpoint_ineligible_for_m7": True,
            "failure_triggers_automatic_rerun": False,
            "failure_triggers_automatic_learning_rate_fallback": False,
        },
        "report_only_diagnostics": {
            "items": list(REPORT_ONLY_ITEMS),
            "thresholds_defined": False,
            "optimised_against": False,
            "deferred": list(DEFERRED_ITEMS),
            "clustering_or_embedding_metrics_introduced": False,
        },
        "roles": {
            "permitted": list(ACTIVE_ROLES),
            "train_text": "exact_copy_and_nearest_train_diagnostics_only",
            "validation": "not_requested",
            "denied": list(DENIED_ROLES),
            "ref_eval_structurally_unreachable": True,
        },
        "closed_gates": {
            "m6_complete": False,
            "m6_closed_by_this_package": False,
            "m7_authorised": False,
            "ref_authorised": False,
            "eval_authorised": False,
            "updates_7_and_14_selectable_or_generated": False,
            "b1_regeneration_authorised": False,
            "human_review_of_generated_sample_required_before_m6_closure": True,
        },
    }
    return json.loads(json.dumps(sections))


# ---------------------------------------------------------------- config

EXECUTION_KEYS = (
    "authorised",
    "biological_paths_permitted",
    "gpu_identity_bound",
    "output_directory",
    "evidence_directory",
    "authorisation_id",
    "authorization_parent_commit",
    "executing_implementation_commit",
)
AUTHORISATION_KEYS = (
    "authorisation_id",
    "activation_status",
    "consumed",
    "single_use",
    "reuse_permitted",
    "authorization_parent_commit",
    "executing_implementation_commit",
    "phase",
    "permitted_roles",
    "logical_device",
    "physical_gpu_index",
    "gpu_uuid",
    "pci_bus",
    "cuda_visible_devices",
    "output_directory",
    "evidence_directory",
    "implementation_file_hashes",
    "authorisation_timestamp",
    "scope",
    "session",
)
STATIC_SECTION_KEYS = tuple(expected_static_sections())
CONFIG_KEYS = (
    "document_status",
    "consumable_by_executable_workflow",
    "schema_version",
    "manifest_schema_version",
    "experiment_id",
    "mres_branch",
    "rnagenesis_branch",
    "rnagenesis_commit",
    "execution",
    "diagnostic_generation_authorisation",
) + STATIC_SECTION_KEYS
FORBIDDEN_ENVIRONMENT = (
    "M6_DIAGNOSTIC_AUTHORISATION_ID",
    "M6_DIAGNOSTIC_ENABLE_EXECUTION",
    "M6_DIAGNOSTIC_OUTPUT_DIRECTORY",
    "M6_DIAGNOSTIC_CHECKPOINT",
)


def load_config_bytes(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise DiagnosticError("config_encoding", "configuration bytes are required")
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise DiagnosticError("config_encoding", "configuration must be UTF-8 without a BOM or carriage return")
    import yaml

    try:
        loaded = yaml.safe_load(bytes(raw).decode("utf-8"))
    except Exception:
        raise DiagnosticError("config_parse", "configuration could not be parsed")
    if not isinstance(loaded, dict):
        raise DiagnosticError("config_shape", "configuration root must be a mapping")
    return loaded


def classify_configuration(config):
    if config.get("document_status") == INACTIVE_STATUS and config.get("consumable_by_executable_workflow") is False:
        return "inactive"
    if config.get("document_status") == ACTIVE_STATUS and config.get("consumable_by_executable_workflow") is True:
        return "active"
    raise DiagnosticError("configuration_not_consumable", "document status and consumable flag are inconsistent")


def _assert_common(config, pins):
    if set(config) != set(CONFIG_KEYS):
        raise DiagnosticError("config_shape", "configuration keys drifted")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "mres_branch": "main",
        "rnagenesis_branch": RNAGENESIS_BRANCH,
        "rnagenesis_commit": RNAGENESIS_COMMIT,
    }
    for key, value in expected.items():
        if config[key] != value:
            raise DiagnosticError("config_shape", key + " drifted")
    sections = expected_static_sections(pins)
    for key in STATIC_SECTION_KEYS:
        if config[key] != sections[key]:
            raise DiagnosticError("config_shape", "static section drifted: " + key)
    if set(config["execution"]) != set(EXECUTION_KEYS):
        raise DiagnosticError("config_shape", "execution keys drifted")
    if set(config["diagnostic_generation_authorisation"]) != set(AUTHORISATION_KEYS):
        raise DiagnosticError("config_shape", "authorisation keys drifted")


def assert_inactive_configuration(config, pins=None):
    _assert_common(config, production_pins() if pins is None else pins)
    execution = config["execution"]
    if execution["authorised"] is not False or execution["biological_paths_permitted"] is not False:
        raise DiagnosticError("configuration_not_consumable", "execution is not closed")
    if execution["gpu_identity_bound"] is not False:
        raise DiagnosticError("configuration_not_consumable", "a GPU identity is bound")
    for key in EXECUTION_KEYS[3:]:
        if execution[key] is not None:
            raise DiagnosticError("configuration_not_consumable", "execution." + key + " is bound")
    block = config["diagnostic_generation_authorisation"]
    if block["activation_status"] != INACTIVE_ACTIVATION or block["consumed"] is not False:
        raise DiagnosticError("configuration_not_consumable", "authorisation is not inactive")
    if block["single_use"] is not True or block["reuse_permitted"] is not False:
        raise DiagnosticError("configuration_not_consumable", "authorisation use policy drifted")
    if block["permitted_roles"] != []:
        raise DiagnosticError("configuration_not_consumable", "roles are granted")
    for key in AUTHORISATION_KEYS:
        if key in ("activation_status", "consumed", "single_use", "reuse_permitted", "permitted_roles", "session"):
            continue
        if block[key] is not None:
            raise DiagnosticError("configuration_not_consumable", "authorisation." + key + " is bound")
    if block["session"] != {
        "pattern": SESSION_PATTERN,
        "wall_clock_expiry": None,
        "resume_permitted": False,
        "consumption_event": None,
    }:
        raise DiagnosticError("configuration_not_consumable", "session binds a consumption event")
    return True


def reject_inactive_before_execution(config):
    if classify_configuration(config) == "inactive":
        raise DiagnosticError("execution_not_authorised", "the diagnostic configuration is inactive")
    return True


def assert_output_directory_shape(path, run_root=RUN_ROOT):
    if not isinstance(path, str) or path != os.path.normpath(path):
        raise DiagnosticError("authorisation_scope_invalid", "output directory is not a normalised absolute path")
    prefix = run_root.rstrip("/") + "/"
    name = path[len(prefix):] if path.startswith(prefix) else ""
    if name == "" or "/" in name or name in (".", ".."):
        raise DiagnosticError("authorisation_scope_invalid", "output directory is not a direct child of the run root")
    if path.startswith(TRAINING_EVIDENCE_DIRECTORY) or path.startswith(B1_POOL_DIRECTORY) or path.startswith(SCHEDULE_DIRECTORY):
        raise DiagnosticError("authorisation_scope_invalid", "output directory is accepted evidence")
    return name


def assert_no_symlink_ancestry(path, lstat=None):
    """Every existing component before the final one must be a real directory.

    The final component may be absent (a new output leaf). If it exists it must
    not be a symlink; callers that need a directory check that themselves.
    """
    checker = os.lstat if lstat is None else lstat
    parts = [item for item in str(path).split("/") if item]
    current = "/"
    for position, part in enumerate(parts):
        current = os.path.join(current, part)
        try:
            observed = checker(current)
        except FileNotFoundError:
            return True
        if stat.S_ISLNK(observed.st_mode):
            raise DiagnosticError("output_directory_symlink", "a path component is a symlink")
        if position < len(parts) - 1 and not stat.S_ISDIR(observed.st_mode):
            raise DiagnosticError("output_ancestry_not_directory", "an output ancestor is not a real directory")
    return True


def assert_active_configuration(config, run_root=RUN_ROOT, pins=None, lstat=None):
    """Validate the schema an authorisation-only commit must satisfy."""
    if classify_configuration(config) != "active":
        raise DiagnosticError("configuration_not_consumable", "configuration is not active")
    _assert_common(config, production_pins() if pins is None else pins)
    execution = config["execution"]
    block = config["diagnostic_generation_authorisation"]
    if execution["authorised"] is not True or execution["biological_paths_permitted"] is not True:
        raise DiagnosticError("authorisation_inactive", "execution is not authorised")
    if execution["gpu_identity_bound"] is not True:
        raise DiagnosticError("authorisation_inactive", "no GPU identity is bound")
    if block["activation_status"] != ACTIVE_ACTIVATION or block["consumed"] is not False:
        raise DiagnosticError("authorisation_consumed", "authorisation is not active_unconsumed")
    if block["single_use"] is not True or block["reuse_permitted"] is not False:
        raise DiagnosticError("authorisation_overbroad", "authorisation use policy drifted")
    if block["phase"] != ACTIVE_PHASE or block["scope"] != ACTIVE_SCOPE:
        raise DiagnosticError("authorisation_scope_invalid", "phase or scope drifted")
    if tuple(block["permitted_roles"]) != ACTIVE_ROLES:
        raise DiagnosticError("authorisation_scope_invalid", "permitted roles are not the exact diagnostic set")
    if block["logical_device"] != LOGICAL_DEVICE:
        raise DiagnosticError("gpu_binding_mismatch", "logical device is not cuda:0")
    index = block["physical_gpu_index"]
    if type(index) is not int or index < 0:
        raise DiagnosticError("gpu_binding_mismatch", "physical GPU index is not an explicit index")
    if block["cuda_visible_devices"] != str(index):
        raise DiagnosticError("gpu_binding_mismatch", "CUDA_VISIBLE_DEVICES does not equal the physical index")
    for key in ("gpu_uuid", "pci_bus"):
        if not isinstance(block[key], str) or block[key].strip() == "":
            raise DiagnosticError("gpu_binding_mismatch", key + " is missing")
    for key in ("authorization_parent_commit", "executing_implementation_commit"):
        if not _is_sha40(block[key]):
            raise DiagnosticError("authorisation_commit_invalid", key + " is not a lowercase SHA-1")
    if block["authorization_parent_commit"] != block["executing_implementation_commit"]:
        raise DiagnosticError("authorisation_commit_invalid", "implementation commit is not the authorisation parent")
    if not isinstance(block["authorisation_id"], str) or block["authorisation_id"].strip() == "":
        raise DiagnosticError("authorisation_missing", "authorisation id is missing")
    if block["output_directory"] != block["evidence_directory"]:
        raise DiagnosticError("authorisation_evidence_mismatch", "output and evidence directories differ")
    name = assert_output_directory_shape(block["output_directory"], run_root)
    if name != block["authorisation_id"]:
        raise DiagnosticError("authorisation_evidence_mismatch", "output directory name is not the authorisation id")
    assert_no_symlink_ancestry(run_root, lstat)
    try:
        root_observed = (os.lstat if lstat is None else lstat)(run_root)
    except FileNotFoundError:
        root_observed = None
    if root_observed is not None and not stat.S_ISDIR(root_observed.st_mode):
        raise DiagnosticError("output_ancestry_not_directory", "the run root is not a real directory")
    assert_no_symlink_ancestry(block["output_directory"], lstat)
    hashes = block["implementation_file_hashes"]
    if not isinstance(hashes, dict) or set(hashes) != set(IMPLEMENTATION_FILE_PATHS):
        raise DiagnosticError("authorisation_scope_invalid", "implementation file hash set drifted")
    for digest in hashes.values():
        if not _is_sha256(digest):
            raise DiagnosticError("authorisation_scope_invalid", "implementation file hash is not SHA-256")
    if not isinstance(block["authorisation_timestamp"], str) or TIMESTAMP_PATTERN.fullmatch(block["authorisation_timestamp"]) is None:
        raise DiagnosticError("authorisation_missing", "authorisation timestamp is not YYYY-MM-DDTHH:MM:SS+HH:MM")
    if block["session"] != {
        "pattern": SESSION_PATTERN,
        "wall_clock_expiry": None,
        "resume_permitted": False,
        "consumption_event": CONSUMPTION_EVENT,
    }:
        raise DiagnosticError("authorisation_scope_invalid", "session drifted")
    for key in EXECUTION_KEYS[3:]:
        if execution[key] != block[key]:
            raise DiagnosticError("authorisation_evidence_mismatch", "execution." + key + " does not match the block")
    return {key: block[key] for key in AUTHORISATION_KEYS}


def assert_output_directory_absent(path, lstat=None):
    checker = os.lstat if lstat is None else lstat
    try:
        observed = checker(path)
    except FileNotFoundError:
        return True
    if stat.S_ISLNK(observed.st_mode):
        raise DiagnosticError("output_directory_symlink", "refusing a symlinked output directory")
    raise DiagnosticError("output_directory_exists", "refusing to overwrite or resume an output directory")


# ---------------------------------------------------------------- input roles

def consider_input_path(path, role, access_enabled, claimed_hash=None, opener=None, pins=None):
    """Refuse a forbidden input before ``opener`` is called."""
    contract = m6_contract()
    pins = production_pins() if pins is None else pins
    if role in ("REF", "EVAL") or contract.path_is_ref_or_eval(path):
        raise DiagnosticError("ref_or_eval_access", "REF and EVAL are refused before open")
    if claimed_hash in contract.DENIED_HASHES:
        raise DiagnosticError("ref_or_eval_access", "a REF or EVAL hash is refused before open")
    if role in DENIED_ROLES:
        raise DiagnosticError("validation_access_not_requested", "VALIDATION is not requested by this diagnostic")
    if contract.path_is_obsolete_repository_local(path):
        raise DiagnosticError("unexpected_biological_path_or_role", "obsolete repository-local data is refused")
    allowed = {
        "TRAIN_TEXT_DIAGNOSTIC_ONLY": pins["train"]["path"],
        "UPDATE21_CHECKPOINT": pins["checkpoint"]["directory"],
        "ACCEPTED_SCHEDULE": pins["schedule"]["directory"],
        "ACCEPTED_B1_POOL_EVIDENCE": pins["b1_pool"]["directory"],
    }
    if role not in allowed:
        raise DiagnosticError("unexpected_biological_path_or_role", "the role is not a diagnostic input")
    normalised = str(path).replace("\\", "/")
    if role in ("TRAIN_TEXT_DIAGNOSTIC_ONLY", "UPDATE21_CHECKPOINT"):
        inside = normalised == allowed[role] or normalised.startswith(allowed[role] + "/")
    else:
        inside = normalised.startswith(allowed[role] + "/")
    if not inside:
        raise DiagnosticError("unexpected_biological_path_or_role", "the path is not the pinned diagnostic input")
    if OTHER_UPDATE_PATTERN.search(normalised):
        raise DiagnosticError("unexpected_checkpoint_update", "only the update-21 checkpoint may be opened")
    if access_enabled is not True:
        raise DiagnosticError("execution_not_authorised", "diagnostic inputs are not enabled")
    if opener is None:
        raise DiagnosticError("execution_not_authorised", "no opener is available")
    return opener(path)


# ---------------------------------------------------------------- schedule

def rebuild_and_verify_schedule(length_vector_bytes, accepted_schedule_bytes=None, pins=None):
    pins = production_pins() if pins is None else pins
    pinned = pins["schedule"]
    b1 = b1_runner()
    if sha256_bytes(length_vector_bytes) != pinned["length_vector"]["sha256"]:
        raise DiagnosticError("schedule_hash_mismatch", "length vector hash does not match the accepted vector")
    ordered = b1.parse_length_vector(length_vector_bytes)
    schedule = b1.build_schedule(ordered, require_source_count=TRAIN_COUNT)
    body = b1.canonical_schedule_bytes(schedule)
    if sha256_bytes(body) != pinned["schedule"]["sha256"]:
        raise DiagnosticError("schedule_hash_mismatch", "rebuilt schedule hash does not match the accepted schedule")
    if accepted_schedule_bytes is not None and bytes(accepted_schedule_bytes) != body:
        raise DiagnosticError("schedule_hash_mismatch", "rebuilt schedule bytes differ from the accepted schedule file")
    if schedule["source_ordered_length_vector"]["sha256"] != pinned["length_vector"]["sha256"]:
        raise DiagnosticError("schedule_hash_mismatch", "schedule source vector hash drifted")
    if schedule["total_attempts"] != pinned["attempts"] or schedule["invocation_count"] != pinned["invocations"]:
        raise DiagnosticError("schedule_invalid", "schedule attempt or invocation count drifted")
    for flag in ("padding", "duplication", "replacement_of_attempts", "rejection", "resampling", "dropping"):
        if schedule[flag] is not False:
            raise DiagnosticError("schedule_invalid", "schedule permits " + flag)
    return schedule, body


# ---------------------------------------------------------------- evidence

def _read_pinned_regular_file(path, expected, deps, code):
    if m6_contract().path_is_ref_or_eval(path):
        raise DiagnosticError("ref_or_eval_access", "REF and EVAL are refused before open")
    try:
        observed = deps.lstat(path)
    except FileNotFoundError:
        raise DiagnosticError(code, "pinned file is missing: " + os.path.basename(path))
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise DiagnosticError(code, "pinned file is not a regular file: " + os.path.basename(path))
    if int(observed.st_size) != int(expected["bytes"]):
        raise DiagnosticError(code, "pinned file size drifted: " + os.path.basename(path))
    data = bytes(deps.read_bytes(path))
    if len(data) != int(expected["bytes"]) or sha256_bytes(data) != expected["sha256"]:
        raise DiagnosticError(code, "pinned file hash drifted: " + os.path.basename(path))
    return data


def verify_training_evidence(deps, pins=None):
    """Revalidate the two small closed JSON files. The weights are not opened here."""
    pins = production_pins() if pins is None else pins
    evidence = pins["training_evidence"]
    directory = evidence["directory"]
    failure = os.path.join(directory, FAILURE_RECORD_NAME)
    try:
        deps.lstat(failure)
    except FileNotFoundError:
        pass
    else:
        raise DiagnosticError("training_evidence_invalid", "a failure record exists beside the training evidence")
    raw = _read_pinned_regular_file(os.path.join(directory, evidence["manifest"]["name"]), evidence["manifest"], deps, "training_evidence_invalid")
    _read_pinned_regular_file(os.path.join(directory, evidence["consumption"]["name"]), evidence["consumption"], deps, "training_evidence_invalid")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DiagnosticError("training_evidence_invalid", "training manifest is not JSON")
    if canonical_json(manifest) != raw:
        raise DiagnosticError("training_evidence_invalid", "training manifest is not canonical JSON")
    authorisation = manifest.get("authorisation") or {}
    if manifest.get("completion_state") != "pilot_completed" or manifest.get("production_identities") is not True:
        raise DiagnosticError("training_evidence_invalid", "training manifest does not record a completed production pilot")
    if manifest.get("failure_state") is not None or manifest.get("warnings") != []:
        raise DiagnosticError("training_evidence_invalid", "training manifest records a failure or warning")
    if authorisation.get("consumption_state") != "consumed_successfully" or authorisation.get("authorisation_id") != evidence["run_id"]:
        raise DiagnosticError("training_evidence_invalid", "training authorisation is not the consumed successful attempt")
    if authorisation.get("authorization_commit") != evidence["authorization_commit"]:
        raise DiagnosticError("training_evidence_invalid", "training authorisation commit drifted")
    if authorisation.get("executing_implementation_commit") != evidence["executing_implementation_commit"]:
        raise DiagnosticError("training_evidence_invalid", "training implementation commit drifted")
    if manifest.get("diagnostic_generation_status") != "not_performed_requires_separate_authorisation":
        raise DiagnosticError("training_evidence_invalid", "diagnostic generation was already recorded")
    access = manifest.get("ref_eval_access") or {}
    if access.get("ref_opened") is not False or access.get("eval_opened") is not False:
        raise DiagnosticError("training_evidence_invalid", "training evidence records REF or EVAL access")
    matches = [item for item in manifest.get("weight_checkpoints", []) if item.get("update") == pins["checkpoint"]["update"]]
    if len(matches) != 1:
        raise DiagnosticError("training_evidence_invalid", "the update-21 checkpoint record is not unique")
    record = matches[0]
    expected_hashes = {name: member["sha256"] for name, member in pins["checkpoint"]["members"].items()}
    if record.get("saved_hashes") != expected_hashes:
        raise DiagnosticError("checkpoint_identity_mismatch", "manifest checkpoint hashes differ from the pinned identity")
    if (record.get("state_comparison") or {}).get("complete_state_equal") is not True or record.get("fresh_load_succeeded") is not True:
        raise DiagnosticError("training_evidence_invalid", "update-21 reload proof is not complete")
    return {
        "run_id": evidence["run_id"],
        "manifest_sha256": evidence["manifest"]["sha256"],
        "manifest_bytes": evidence["manifest"]["bytes"],
        "consumption_sha256": evidence["consumption"]["sha256"],
        "consumption_bytes": evidence["consumption"]["bytes"],
        "completion_state": manifest["completion_state"],
        "consumption_state": authorisation["consumption_state"],
        "authorization_commit": evidence["authorization_commit"],
        "executing_implementation_commit": evidence["executing_implementation_commit"],
    }


def verify_checkpoint(deps, pins=None, hash_weights=True):
    """Bind the update-21 directory by exact tree, size and streamed hash."""
    pins = production_pins() if pins is None else pins
    pinned = pins["checkpoint"]
    contract = m6_contract()
    directory = pinned["directory"]
    consider_input_path(directory, "UPDATE21_CHECKPOINT", True, opener=lambda path: True, pins=pins)
    signatures = deps.observe_checkpoint_tree(directory)
    if set(signatures) != set(pinned["members"]):
        raise DiagnosticError("checkpoint_identity_mismatch", "checkpoint member set drifted")
    members = {}
    for name in sorted(pinned["members"]):
        expected = pinned["members"][name]
        if name == WEIGHT_MEMBER and not hash_weights:
            continue
        path = os.path.join(directory, name)
        _translate(
            lambda: contract.observe_regular_hashed_file(
                path, expected["bytes"], expected["sha256"], "update21_" + name, lstat=deps.lstat, hash_file=deps.sha256_file
            )
        )
        members[name] = {"sha256": expected["sha256"], "bytes": expected["bytes"]}
    return {"directory": directory, "update": pinned["update"], "members": members, "signatures": signatures}


def load_b1_reference(deps, metrics, schedule, pins=None):
    """Read the accepted B1 pool as evidence. Nothing is generated."""
    pins = production_pins() if pins is None else pins
    b1 = b1_runner()
    pool = pins["b1_pool"]
    data = {}
    for name, expected in pool["files"].items():
        data[name] = _read_pinned_regular_file(os.path.join(pool["directory"], name), expected, deps, "b1_pool_evidence_invalid")
    attempts = parse_attempt_ledger(data["development_pool_audited_attempts.jsonl"], b1)
    b1.assert_attempt_accounting(attempts, schedule)
    accepted_metrics = json.loads(data["development_pool_metrics.json"].decode("utf-8"))
    recomputed = json.loads(canonical_json(metrics.summarise_attempts(attempts)).decode("utf-8"))
    if recomputed != accepted_metrics:
        raise DiagnosticError("b1_pool_evidence_invalid", "recomputed B1 metrics differ from the accepted metrics file")
    manifest = json.loads(data["development_pool_manifest.json"].decode("utf-8"))
    if manifest.get("schedule_sha256") != SCHEDULE_SHA256 or manifest.get("status") != "complete":
        raise DiagnosticError("b1_pool_evidence_invalid", "accepted B1 manifest does not record the accepted schedule")
    return {
        "attempts": attempts,
        "files": {name: {"sha256": item["sha256"], "bytes": item["bytes"]} for name, item in pool["files"].items()},
        "metrics_recomputed_equal_to_accepted": True,
        "regenerated": False,
        "rerun": False,
    }


def parse_attempt_ledger(payload, b1=None):
    b1 = b1 or b1_runner()
    rows = []
    for line in bytes(payload).decode("utf-8").split("\n"):
        if line == "":
            continue
        row = json.loads(line)
        if set(row) != set(b1.ATTEMPT_FIELDS):
            raise DiagnosticError("attempt_ledger_invalid", "attempt ledger fields drifted")
        rows.append({field: row[field] for field in b1.ATTEMPT_FIELDS})
    if len(rows) != ATTEMPT_COUNT:
        raise DiagnosticError("attempt_ledger_invalid", "attempt ledger does not have 1000 rows")
    return rows


def split_train_records(text):
    """Mirror the pinned trainer reader: newline delimiters only, nothing repaired."""
    if text.startswith("﻿"):
        raise DiagnosticError("train_identity_mismatch", "TRAIN text begins with a BOM")
    if text.endswith("\n"):
        text = text[:-1]
    if text.endswith("\r"):
        text = text[:-1]
    if text == "":
        raise DiagnosticError("train_identity_mismatch", "TRAIN text has no records")
    records = [record[:-1] if record.endswith("\r") else record for record in text.split("\n")]
    seen = set()
    for record in records:
        if BODY_PATTERN.fullmatch(record) is None or record in seen:
            raise DiagnosticError("train_identity_mismatch", "TRAIN text has a non-canonical or repeated record")
        seen.add(record)
    return records


def open_train_cores(deps, ordered_lengths, pins=None):
    """TRAIN is opened for exact-copy and nearest-TRAIN diagnostics only."""
    pins = production_pins() if pins is None else pins
    pinned = pins["train"]

    def opener(path):
        observed = deps.lstat(path)
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
            raise DiagnosticError("train_identity_mismatch", "TRAIN text is not a regular file")
        data = bytes(deps.read_bytes(path))
        if len(data) != pinned["bytes"] or sha256_bytes(data) != pinned["sha256"]:
            raise DiagnosticError("train_identity_mismatch", "TRAIN text is not the pinned corpus")
        return data

    data = consider_input_path(
        pinned["path"], "TRAIN_TEXT_DIAGNOSTIC_ONLY", True, claimed_hash=pinned["sha256"], opener=opener, pins=pins
    )
    cores = split_train_records(data.decode("utf-8"))
    if len(cores) != pinned["count"]:
        raise DiagnosticError("train_identity_mismatch", "TRAIN record count drifted")
    if [len(core) for core in cores] != list(ordered_lengths):
        raise DiagnosticError("train_identity_mismatch", "TRAIN lengths do not equal the accepted length vector")
    return cores


# ---------------------------------------------------------------- normalisation

def independent_normalisation(raw):
    """Independent restatement of the approved cleaner's run removal."""
    start = 0
    while start < len(raw) and raw[start] in "12":
        start += 1
    end = len(raw)
    while end > start and raw[end - 1] in "12":
        end -= 1
    return raw[:start], raw[start:end], raw[end:]


def assert_normalisation_reconciles(attempts):
    """The cleaner may only remove boundary runs. Anything else is a technical failure."""
    for attempt in attempts:
        raw = attempt["raw_decoded_text"]
        prefix, body, suffix = independent_normalisation(raw)
        if (attempt["leading_boundary_marker_run"], attempt["cleaned_sequence"], attempt["trailing_boundary_marker_run"]) != (
            prefix,
            body,
            suffix,
        ):
            raise DiagnosticError("unexpected_output_normalization", "normalisation differs from the approved boundary-run rule")
        if attempt["raw_length"] != len(raw) or attempt["cleaned_length"] != len(body):
            raise DiagnosticError("unexpected_output_normalization", "recorded lengths differ from the raw and normalised text")
        if attempt["validity"] is not (BODY_PATTERN.fullmatch(body) is not None):
            raise DiagnosticError("unexpected_output_normalization", "validity differs from the nonempty ACGU rule")
    return True


def strict_m6_rule_sensitivity(attempts):
    """Report-only. Count what the stricter exact-``11`` helper would have rejected."""
    contract = m6_contract()
    rejected = 0
    differs = 0
    for attempt in attempts:
        verdict = contract.normalize_generated_output(attempt["raw_decoded_text"])
        if verdict["accepted"] is not True:
            rejected += 1
        elif verdict["normalized_string"] != attempt["cleaned_sequence"]:
            differs += 1
    return {
        "role": "report_only_does_not_change_any_denominator",
        "policy": contract.NORMALIZATION_POLICY,
        "raw_attempts": len(attempts),
        "attempts_the_stricter_helper_would_reject": rejected,
        "accepted_attempts_whose_body_differs": differs,
    }


# ---------------------------------------------------------------- metrics

def assert_guardrail_thresholds(metrics):
    expected = {rule_id: {"comparison": comparison, "threshold": threshold} for rule_id, comparison, threshold, _d in HARD_GUARDRAIL_RULES}
    if dict(metrics.GUARDRAIL_THRESHOLDS) != expected or tuple(metrics.HARD_GUARDRAIL_IDS) != tuple(item[0] for item in HARD_GUARDRAIL_RULES):
        raise DiagnosticError("metrics_configuration_invalid", "hard guardrail thresholds differ from the approved set")
    return True


def evaluate_guardrails(metrics, attempts, train_cores):
    assert_guardrail_thresholds(metrics)
    evaluation = metrics.evaluate_hard_guardrails(attempts, train_cores)
    if evaluation["exact_hit_rate_is_an_eligibility_threshold"] is not False:
        raise DiagnosticError("metrics_configuration_invalid", "exact-hit rate was enforced as a threshold")
    return evaluation


def edit_distance(a, b):
    """Global Levenshtein distance by Myers' bit-parallel method."""
    if a == "":
        return len(b)
    if b == "":
        return len(a)
    if len(a) > len(b):
        a, b = b, a
    m = len(a)
    masks = {}
    for position, character in enumerate(a):
        masks[character] = masks.get(character, 0) | (1 << position)
    full = (1 << m) - 1
    high = 1 << (m - 1)
    pv = full
    mv = 0
    score = m
    for character in b:
        eq = masks.get(character, 0)
        xv = eq | mv
        xh = ((((eq & pv) + pv) & full) ^ pv) | eq
        ph = (mv | (~(xh | pv) & full)) & full
        mh = pv & xh
        if ph & high:
            score += 1
        elif mh & high:
            score -= 1
        ph = ((ph << 1) | 1) & full
        mh = (mh << 1) & full
        pv = (mh | (~(xv | ph) & full)) & full
        mv = ph & xv
    return score


def nearest_train(sequence, train_cores):
    best = None
    for core in train_cores:
        distance = edit_distance(sequence, core)
        normalised = distance / float(max(len(sequence), len(core)))
        if best is None or normalised < best:
            best = normalised
            if best == 0.0:
                break
    return best


def composition(sequences):
    counts = {base: 0 for base in BASES}
    pairs = {pair: 0 for pair in DINUCLEOTIDES}
    for sequence in sequences:
        for base in sequence:
            counts[base] += 1
        for index in range(len(sequence) - 1):
            pairs[sequence[index : index + 2]] += 1
    total = sum(counts.values())
    pair_total = sum(pairs.values())
    return {
        "sequence_count": len(sequences),
        "nucleotide_counts": counts,
        "nucleotide_fractions": {base: (counts[base] / total if total else None) for base in BASES},
        "dinucleotide_counts": pairs,
        "dinucleotide_fractions": {pair: (pairs[pair] / pair_total if pair_total else None) for pair in DINUCLEOTIDES},
    }


def total_variation(left, right):
    keys = sorted(left)
    if any(left[key] is None or right[key] is None for key in keys):
        return None
    return 0.5 * sum(abs(left[key] - right[key]) for key in keys)


def _quantiles(values):
    if not values:
        return None
    ordered = sorted(values)
    last = len(ordered) - 1
    return {
        "count": len(ordered),
        "minimum": ordered[0],
        "p25": ordered[int(round(0.25 * last))],
        "median": ordered[int(round(0.5 * last))],
        "p75": ordered[int(round(0.75 * last))],
        "maximum": ordered[-1],
        "mean": sum(ordered) / len(ordered),
    }


def structure_features(sequence, fold):
    structure, mfe = fold(sequence)
    if len(structure) != len(sequence):
        raise DiagnosticError("fold_invalid", "fold structure length differs from the sequence")
    paired = structure.count("(") + structure.count(")")
    return {"mfe": float(mfe), "mfe_per_nt": float(mfe) / len(sequence), "paired_fraction": paired / float(len(sequence))}


def report_only_diagnostics(attempts, train_cores, fold, nearest_fn=None):
    """Descriptive only. No threshold is defined and nothing is optimised."""
    valid = [attempt for attempt in attempts if attempt["validity"] is True]
    distinct = sorted({attempt["cleaned_sequence"] for attempt in valid})
    nearest_fn = nearest_train if nearest_fn is None else nearest_fn
    nearest = {sequence: nearest_fn(sequence, train_cores) for sequence in distinct}
    features = {sequence: structure_features(sequence, fold) for sequence in distinct}
    sequences = [attempt["cleaned_sequence"] for attempt in valid]
    sample = composition(sequences)
    reference = composition(list(train_cores))

    def block(rows):
        distances = [nearest[row["cleaned_sequence"]] for row in rows]
        return {
            "valid_outputs": len(rows),
            "nearest_train_normalized_edit_distance": _quantiles(distances),
            "maximum_edit_similarity_to_train": (1.0 - min(distances)) if distances else None,
            "mfe": _quantiles([features[row["cleaned_sequence"]]["mfe"] for row in rows]),
            "mfe_per_nt": _quantiles([features[row["cleaned_sequence"]]["mfe_per_nt"] for row in rows]),
            "paired_fraction": _quantiles([features[row["cleaned_sequence"]]["paired_fraction"] for row in rows]),
        }

    by_length = {}
    for attempt in attempts:
        by_length.setdefault(attempt["requested_target_length"], []).append(attempt)
    stratified = []
    for length in sorted(by_length):
        rows = by_length[length]
        valid_rows = [row for row in rows if row["validity"] is True]
        entry = block(valid_rows)
        entry.update(
            {
                "requested_target_length": length,
                "raw_attempts": len(rows),
                "exact_length_hits": sum(1 for row in rows if row["exact_length_hit"] is True),
                "exact_hit_rate": sum(1 for row in rows if row["exact_length_hit"] is True) / float(len(rows)),
            }
        )
        stratified.append(entry)
    result = block(valid)
    result.update(
        {
            "distinct_valid_sequences": len(distinct),
            "maximum_edit_similarity_definition": EDIT_SIMILARITY_DEFINITION,
            "composition": sample,
            "train_reference_composition": reference,
            "nucleotide_total_variation_to_train": total_variation(sample["nucleotide_fractions"], reference["nucleotide_fractions"]),
            "dinucleotide_total_variation_to_train": total_variation(
                sample["dinucleotide_fractions"], reference["dinucleotide_fractions"]
            ),
            "by_requested_length": stratified,
            "thresholds_defined": False,
            "clustering_or_embedding_metrics": False,
        }
    )
    return result


def assert_pairing(d1_attempts, b1_attempts):
    """The D1 and B1 ledgers must share every schedule field. Only text may differ."""
    keys = ("invocation_index", "batch_position", "requested_target_length", "max_seq_len", "invocation_seed")
    by_index = {attempt["original_attempt_index"]: attempt for attempt in b1_attempts}
    if len(by_index) != len(b1_attempts) or set(by_index) != {a["original_attempt_index"] for a in d1_attempts}:
        raise DiagnosticError("pairing_invalid", "D1 and B1 attempt identities differ")
    for attempt in d1_attempts:
        other = by_index[attempt["original_attempt_index"]]
        if any(attempt[key] != other[key] for key in keys):
            raise DiagnosticError("pairing_invalid", "D1 and B1 schedule fields differ")
    return True


def comparison_table(d1_metrics, d1_guardrails, b1_metrics, b1_guardrails):
    fields = (
        "raw_attempts",
        "valid_outputs",
        "invalid_outputs",
        "empty_or_unparseable_outputs",
        "exact_length_hits",
        "exact_hit_rate",
        "early_eos_observations",
        "unique_valid_outputs",
        "duplicates",
        "largest_duplicate_multiplicity",
        "largest_duplicate_share",
    )
    return {
        "role": "side_by_side_report_not_a_paired_significance_test",
        "d1_update21": {field: d1_metrics[field] for field in fields},
        "b1_accepted_pool": {field: b1_metrics[field] for field in fields},
        "d1_guardrail_values": d1_guardrails["values"],
        "b1_guardrail_values": b1_guardrails["values"],
        "b1_guardrails_are_an_eligibility_decision": False,
    }


# ---------------------------------------------------------------- generation

def checkpoint_directory():
    return TRAINING_EVIDENCE_DIRECTORY + "/" + CHECKPOINT_DIRECTORY_NAME


def build_diagnostic_argv(invocation, checkpoint_dir, pinned_dir=None):
    """The accepted B1 invocation contract with exactly one substitution: ``--dm_file``."""
    b1 = b1_runner()
    argv = b1.build_generation_argv(invocation)
    if argv.count("--dm_file") != 1:
        raise DiagnosticError("prohibited_generation_option", "generation argv must name one diffusion model")
    position = argv.index("--dm_file") + 1
    if argv[position] != b1.DIFFUSION_RELATIVE:
        raise DiagnosticError("prohibited_generation_option", "B1 invocation contract drifted")
    if checkpoint_dir != (checkpoint_directory() if pinned_dir is None else pinned_dir):
        raise DiagnosticError("unexpected_checkpoint_update", "generation may load only the pinned update-21 directory")
    argv[position] = checkpoint_dir
    if OTHER_UPDATE_PATTERN.search(" ".join(argv)):
        raise DiagnosticError("unexpected_checkpoint_update", "only the update-21 checkpoint may be loaded")
    return argv


def build_diagnostic_command(invocation, evidence_dir, parent, physical_gpu, checkpoint_dir, realpath=None, pinned_dir=None):
    b1 = b1_runner()
    argv = build_diagnostic_argv(invocation, checkpoint_dir, pinned_dir)
    argv.extend(["--superfolder", os.path.join(evidence_dir, GENERATION_OUTPUT_DIRECTORY), "--mid_folder", b1.invocation_folder(invocation)])
    return {
        "argv": argv,
        "cwd": b1.GENERATION_CWD,
        "env": b1.build_child_environment(parent, physical_gpu, evidence_dir, realpath),
        "shell": False,
    }


def _run_invocation(evidence_dir, invocation, physical_gpu, deps, cleaner, checkpoint_dir):
    b1 = b1_runner()
    command = build_diagnostic_command(
        invocation, evidence_dir, deps.environ, physical_gpu, checkpoint_dir, deps.realpath, pinned_dir=checkpoint_dir
    )
    predicted = b1.predicted_generation_path(evidence_dir, invocation)
    try:
        deps.lstat(predicted)
    except FileNotFoundError:
        pass
    else:
        raise DiagnosticError("output_directory_exists", "invocation output already exists")
    folder = os.path.join(evidence_dir, GENERATION_OUTPUT_DIRECTORY, b1.invocation_folder(invocation))
    deps.mkdir(folder)
    completed = deps.subprocess_run(command["argv"], cwd=command["cwd"], env=command["env"], shell=False)
    returncode = getattr(completed, "returncode", None)
    if type(returncode) is not int or returncode != 0:
        raise DiagnosticError("generation_process_failed", "generation.py exited {}".format(returncode))
    data = bytes(deps.read_bytes(predicted))
    records = b1.map_invocation_output(data, invocation, cleaner)
    metadata = b1._raw_invocation_record(predicted, data, invocation, cleaner)
    if metadata["line_count"] != invocation["actual_chunk_size"]:
        raise DiagnosticError("output_line_count_mismatch", "raw line count does not match the chunk")
    return records, metadata, data


# ---------------------------------------------------------------- provenance

def measure_provenance(authorisation, config_bytes, deps):
    """Hash and inspect live files. Caller-supplied hashes are not accepted."""
    b1 = b1_runner()
    git = deps.git
    head = b1._git_line(git, MRES_ROOT, ["rev-parse", "HEAD"])
    branch = b1._git_line(git, MRES_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"])
    origin = b1._git_line(git, MRES_ROOT, ["rev-parse", "origin/main"])
    if not _is_sha40(head) or not _is_sha40(origin) or branch != "main":
        raise DiagnosticError("provenance_mismatch", "MRes HEAD, origin or branch is not accepted")
    if b1._porcelain_lines(git(MRES_ROOT, ["status", "--porcelain=v1", "--untracked-files=all"])):
        raise DiagnosticError("provenance_mismatch", "MRes worktree or index is not clean")
    parents = [line.strip() for line in b1._git_text(git, MRES_ROOT, ["rev-parse", "HEAD^@"]).splitlines() if line.strip()]
    if len(parents) != 1 or parents[0] != authorisation["authorization_parent_commit"]:
        raise DiagnosticError("provenance_mismatch", "live HEAD does not have the authorised single parent")
    implementation = authorisation["executing_implementation_commit"]
    if implementation != parents[0]:
        raise DiagnosticError("provenance_mismatch", "executing implementation is not the authorisation parent")
    # The authorisation commit may stay local, as it did for the training pilot.
    if origin not in (implementation, head):
        raise DiagnosticError("provenance_mismatch", "origin/main is neither the implementation commit nor live HEAD")
    changed = [line for line in b1._git_text(git, MRES_ROOT, ["diff", "--name-only", implementation, head]).splitlines() if line]
    if sorted(changed) != sorted(PERMITTED_AUTHORIZATION_FILES):
        raise DiagnosticError("authorisation_delta_invalid", "the authorisation commit changed more than the configuration")
    shown = b1._git_text(git, MRES_ROOT, ["show", "HEAD:" + CONFIG_RELATIVE])
    if shown.encode("utf-8") != bytes(config_bytes):
        raise DiagnosticError("provenance_mismatch", "active authorisation is not the live HEAD blob")
    measured = {}
    for relative in IMPLEMENTATION_FILE_PATHS:
        path = os.path.join(MRES_ROOT, relative)
        digest = sha256_bytes(bytes(deps.read_bytes(path)))
        blob = b1._git_line(git, MRES_ROOT, ["rev-parse", "{}:{}".format(implementation, relative)])
        worktree = b1._git_line(git, MRES_ROOT, ["hash-object", "--", path])
        if not _is_sha40(blob) or blob != worktree:
            raise DiagnosticError("provenance_mismatch", "file does not match the implementation commit: " + relative)
        if digest != authorisation["implementation_file_hashes"][relative]:
            raise DiagnosticError("provenance_mismatch", "file does not match the authorised hash: " + relative)
        measured[relative] = digest
    rna_head = b1._git_line(git, RNAGENESIS_ROOT, ["rev-parse", "HEAD"])
    rna_branch = b1._git_line(git, RNAGENESIS_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"])
    if rna_head != RNAGENESIS_COMMIT or rna_branch != RNAGENESIS_BRANCH:
        raise DiagnosticError("provenance_mismatch", "RNAGenesis branch or commit drifted")
    try:
        b1._assert_rnagenesis_worktree(git(RNAGENESIS_ROOT, ["status", "--porcelain=v1"]))
    except b1.DevelopmentPoolError as exc:
        raise DiagnosticError(exc.code, exc.detail)
    cleaner_bytes = bytes(deps.read_bytes(b1.APPROVED_CLEANER))
    if sha256_bytes(cleaner_bytes) != CLEANER_SHA256:
        raise DiagnosticError("provenance_mismatch", "cleaner hash does not match the approved cleaner")
    metrics_bytes = bytes(deps.read_bytes(os.path.join(MRES_ROOT, METRICS_RELATIVE)))
    metrics_config = bytes(deps.read_bytes(os.path.join(MRES_ROOT, METRICS_CONFIG_RELATIVE)))
    if sha256_bytes(metrics_bytes) != METRICS_SHA256 or sha256_bytes(metrics_config) != METRICS_CONFIG_SHA256:
        raise DiagnosticError("provenance_mismatch", "metrics module or configuration drifted")
    inputs = []
    for relative, expected, _large in b1.MODEL_INPUTS:
        if relative.startswith("configs/rnagenesis/diffusion/"):
            continue
        digest = deps.sha256_file(os.path.join(RNAGENESIS_ROOT, relative))
        if digest != expected:
            raise DiagnosticError("provenance_mismatch", "generation input hash drifted: " + relative)
        inputs.append({"relative_path": relative, "sha256": digest})
    contract = m6_contract()
    m5 = contract.m5_contract()
    assets = {}
    for relative, digest, size, role in m5.REQUIRED_MODEL_FILES:
        if role in ENCDEC_ROLES:
            observed = _translate(
                lambda: contract.observe_regular_hashed_file(
                    os.path.join(RNAGENESIS_ROOT, relative), size, digest, role, lstat=deps.lstat, hash_file=deps.sha256_file
                )
            )
            assets[role] = {"sha256": observed["sha256"], "bytes": observed["byte_size"]}
    patch = _translate(
        lambda: contract.observe_regular_hashed_file(
            m5.DIFFUSERS_PATCH_PATH,
            m5.DIFFUSERS_PATCH_SIZE,
            m5.DIFFUSERS_PATCH_SHA256,
            "diffusers_normalization_patch",
            lstat=deps.lstat,
            hash_file=deps.sha256_file,
        )
    )
    assets["diffusers_normalization_patch"] = {"sha256": patch["sha256"], "bytes": patch["byte_size"]}
    return {
        "mres": {"branch": branch, "head": head, "origin_main": origin, "clean": True, "authorization_parent_commit": parents[0]},
        "implementation_file_hashes": measured,
        "rnagenesis": {"branch": rna_branch, "commit": rna_head, "tracked_and_staged_clean": True},
        "approved_cleaner": {"sha256": sha256_bytes(cleaner_bytes), "bytes": len(cleaner_bytes)},
        "cleaner_source_bytes": cleaner_bytes,
        "metrics_source_bytes": metrics_bytes,
        "metrics_configuration_bytes": metrics_config,
        "generation_inputs": inputs,
        "frozen_encdec_assets": assets,
        "diffusion_model": "update21_checkpoint_only_b1_diffusion_weights_not_loaded",
    }


# ---------------------------------------------------------------- manifest

MANIFEST_KEYS = (
    "accounting",
    "authorisation",
    "b1_reference",
    "checkpoint",
    "closure",
    "comparison",
    "consequence",
    "experiment_id",
    "gpu",
    "hard_guardrails",
    "ledgers",
    "manifest_schema_version",
    "metrics",
    "normalisation",
    "provenance",
    "report_only_diagnostics",
    "roles",
    "schedule",
    "status",
    "training_evidence",
)
ACCOUNTING_KEYS = (
    "raw_attempts",
    "parsed_outputs",
    "valid_outputs",
    "invalid_outputs",
    "empty_or_unparseable_outputs",
    "unique_valid_outputs",
    "duplicates",
    "early_eos_observations",
    "exact_length_hits",
    "length_mismatches",
    "generation_invocations",
    "replacements",
    "resampled_attempts",
    "dropped_attempts",
)
METRICS_KEYS = (
    "all_raw_attempts_remain_visible", "by_requested_length", "cleaned_length_distribution", "deferred_beyond_m4",
    "duplicates", "early_eos_observations", "empty_or_unparseable_outputs", "eos_marker_observations", "exact_hit_rate",
    "exact_hit_rate_computed_before_filtering", "exact_hit_rate_denominator",
    "exact_hit_rate_is_execution_success_requirement", "exact_hit_rate_valid_outputs_diagnostic", "exact_length_hits",
    "implemented_metric_ids", "independent_biological_replicates", "invalid_or_unparseable_attempts_are_non_hits",
    "invalid_outputs", "largest_duplicate_multiplicity", "largest_duplicate_share", "largest_duplicate_share_status",
    "length_excess_distribution", "length_shortfall_distribution",
    "low_exact_hit_rate_invalidates_or_reruns_the_diagnostic_pool", "parsed_outputs", "raw_attempts", "sample_description",
    "schema_version", "unique_valid_outputs", "valid_outputs",
)
COMPARISON_FIELDS = (
    "raw_attempts", "valid_outputs", "invalid_outputs", "empty_or_unparseable_outputs", "exact_length_hits",
    "exact_hit_rate", "early_eos_observations", "unique_valid_outputs", "duplicates", "largest_duplicate_multiplicity",
    "largest_duplicate_share",
)
LEDGER_FILES = {
    "raw_ledger_sha256": RAW_LEDGER_NAME,
    "audited_ledger_sha256": AUDITED_LEDGER_NAME,
    "invocation_output_manifest_sha256": INVOCATION_MANIFEST_NAME,
    "metrics_sha256": METRICS_NAME,
    "guardrails_sha256": GUARDRAILS_NAME,
    "schedule_copy_sha256": SCHEDULE_COPY_NAME,
    "consumption_record_sha256": CONSUMPTION_RECORD_NAME,
}
NORMALISATION_BLOCK = {
    "authority": "approved_m1_cleaner",
    "cleaner_sha256": CLEANER_SHA256,
    "raw_text_retained_beside_normalised_text": True,
    "additional_trimming": False,
    "padding": False,
    "rejection": False,
    "replacement": False,
    "resampling": False,
    "independent_reconciliation_passed": True,
}
ROLES_BLOCK = {
    "train_text": "opened_for_exact_copy_and_nearest_train_diagnostics_only",
    "validation": "not_opened",
    "ref": "not_opened",
    "eval": "not_opened",
    "b1_pool": "read_only_evidence_not_regenerated",
}
CLOSURE_BLOCK = {
    "m6_complete": False,
    "m6_closed_by_this_run": False,
    "human_review_required": True,
    "m7_authorised": False,
    "ref_authorised": False,
    "eval_authorised": False,
    "checkpoint_selected": False,
}
CHECKPOINT_STATES = (
    "not_read",
    "verified_before_generation",
    "verified_unchanged_after_generation",
    "changed_or_unverifiable_after_generation",
)


def pinned_generation_inputs():
    b1 = b1_runner()
    return [
        {"relative_path": relative, "sha256": digest}
        for relative, digest, _large in b1.MODEL_INPUTS
        if not relative.startswith("configs/rnagenesis/diffusion/")
    ]


def pinned_encdec_assets():
    m5 = m6_contract().m5_contract()
    assets = {role: {"sha256": digest, "bytes": size} for _path, digest, size, role in m5.REQUIRED_MODEL_FILES if role in ENCDEC_ROLES}
    assets["diffusers_normalization_patch"] = {"sha256": m5.DIFFUSERS_PATCH_SHA256, "bytes": m5.DIFFUSERS_PATCH_SIZE}
    return assets


def accounting_from(metrics, attempts, invocation_count):
    mismatches = sum(1 for attempt in attempts if attempt["validity"] is True and attempt["length_delta"] != 0)
    return {
        "raw_attempts": metrics["raw_attempts"],
        "parsed_outputs": metrics["parsed_outputs"],
        "valid_outputs": metrics["valid_outputs"],
        "invalid_outputs": metrics["invalid_outputs"],
        "empty_or_unparseable_outputs": metrics["empty_or_unparseable_outputs"],
        "unique_valid_outputs": metrics["unique_valid_outputs"],
        "duplicates": metrics["duplicates"],
        "early_eos_observations": metrics["early_eos_observations"],
        "exact_length_hits": metrics["exact_length_hits"],
        "length_mismatches": mismatches,
        "generation_invocations": invocation_count,
        "replacements": 0,
        "resampled_attempts": 0,
        "dropped_attempts": 0,
    }


def _bad(detail):
    raise DiagnosticError("manifest_incomplete", detail)


def _keys(section, value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        _bad("keys of " + section + " differ from the schema")


def _expect(section, value, expected):
    if value != expected:
        _bad(section + " differs from its required value")


def _sha(section, value):
    if not _is_sha256(value):
        _bad(section + " is not a SHA-256")


def _int(section, value):
    if type(value) is not int or value < 0:
        _bad(section + " is not a non-negative integer")


def _passes(comparison, value, threshold):
    return value >= threshold if comparison == "minimum" else value <= threshold


def validate_success_manifest(manifest, pins=None, expected=None):
    """Exact nested key sets and cross-field consistency for every section.

    ``expected`` carries the validated active authorisation and the measured
    provenance for this run. Values read back from the manifest are compared
    with it and are never trusted on their own.
    """
    pins = production_pins() if pins is None else pins
    if not isinstance(manifest, dict) or set(manifest) != set(MANIFEST_KEYS):
        _bad("manifest top-level keys differ from the schema")
    _expect("status", manifest["status"], "complete")
    _expect("manifest_schema_version", manifest["manifest_schema_version"], MANIFEST_SCHEMA_VERSION)
    _expect("experiment_id", manifest["experiment_id"], EXPERIMENT_ID)

    auth = manifest["authorisation"]
    _keys("authorisation", auth, ("authorisation_id", "authorization_commit", "authorization_parent_commit",
                                   "executing_implementation_commit", "consumption_state", "single_use", "reuse_permitted"))
    if not isinstance(auth["authorisation_id"], str) or auth["authorisation_id"] == "":
        _bad("authorisation id is missing")
    for key in ("authorization_commit", "authorization_parent_commit", "executing_implementation_commit"):
        if not _is_sha40(auth[key]):
            _bad("authorisation." + key + " is not a SHA-1")
    if auth["authorization_parent_commit"] != auth["executing_implementation_commit"]:
        _bad("authorisation parent is not the implementation commit")
    _expect("authorisation use", (auth["consumption_state"], auth["single_use"], auth["reuse_permitted"]),
            ("consumed_successfully", True, False))

    gpu = manifest["gpu"]
    _keys("gpu", gpu, ("physical_index", "uuid", "pci_bus", "cuda_visible_devices", "logical_device"))
    _int("gpu.physical_index", gpu["physical_index"])
    if gpu["cuda_visible_devices"] != str(gpu["physical_index"]) or gpu["logical_device"] != LOGICAL_DEVICE:
        _bad("GPU binding is inconsistent")
    if not isinstance(gpu["uuid"], str) or gpu["uuid"] == "" or not isinstance(gpu["pci_bus"], str) or gpu["pci_bus"] == "":
        _bad("GPU identity is missing")

    prov = manifest["provenance"]
    _keys("provenance", prov, ("mres", "implementation_file_hashes", "rnagenesis", "approved_cleaner", "generation_inputs",
                               "frozen_encdec_assets", "diffusion_model"))
    _keys("provenance.mres", prov["mres"], ("branch", "head", "origin_main", "clean", "authorization_parent_commit"))
    mres = prov["mres"]
    if mres["branch"] != "main" or mres["clean"] is not True or not _is_sha40(mres["head"]) or not _is_sha40(mres["origin_main"]):
        _bad("MRes provenance is inconsistent")
    if mres["head"] != auth["authorization_commit"] or mres["authorization_parent_commit"] != auth["authorization_parent_commit"]:
        _bad("MRes provenance does not match the authorisation")
    if mres["origin_main"] not in (mres["head"], auth["executing_implementation_commit"]):
        _bad("origin/main relationship is not accepted")
    _keys("provenance.implementation_file_hashes", prov["implementation_file_hashes"], IMPLEMENTATION_FILE_PATHS)
    for value in prov["implementation_file_hashes"].values():
        _sha("implementation file hash", value)
    _expect("provenance.rnagenesis", prov["rnagenesis"],
            {"branch": RNAGENESIS_BRANCH, "commit": RNAGENESIS_COMMIT, "tracked_and_staged_clean": True})
    _keys("provenance.approved_cleaner", prov["approved_cleaner"], ("sha256", "bytes"))
    _expect("cleaner hash", prov["approved_cleaner"]["sha256"], CLEANER_SHA256)
    _int("cleaner bytes", prov["approved_cleaner"]["bytes"])
    if prov["generation_inputs"] != pinned_generation_inputs():
        _bad("generation inputs differ from the pinned non-B1-diffusion inventory")
    if prov["frozen_encdec_assets"] != pinned_encdec_assets():
        _bad("frozen EncDec or Diffusers-patch evidence differs from the pinned M5 observations")
    if not isinstance(prov["generation_inputs"], list) or not prov["generation_inputs"]:
        _bad("generation inputs are missing")
    for item in prov["generation_inputs"]:
        _keys("generation input", item, ("relative_path", "sha256"))
        _sha("generation input hash", item["sha256"])
        if item["relative_path"].startswith("configs/rnagenesis/diffusion/"):
            _bad("a B1 diffusion file is listed as a generation input")
    _keys("provenance.frozen_encdec_assets", prov["frozen_encdec_assets"], tuple(ENCDEC_ROLES) + ("diffusers_normalization_patch",))
    for item in prov["frozen_encdec_assets"].values():
        _keys("encdec asset", item, ("sha256", "bytes"))
        _sha("encdec asset hash", item["sha256"])
        _int("encdec asset bytes", item["bytes"])
    _expect("diffusion model", prov["diffusion_model"], "update21_checkpoint_only_b1_diffusion_weights_not_loaded")
    if expected is not None:
        block = expected["authorisation"]
        measured = expected["provenance"]
        if auth["authorisation_id"] != block["authorisation_id"]:
            _bad("authorisation id differs from the validated authorisation")
        if auth["authorization_parent_commit"] != block["authorization_parent_commit"] or auth["executing_implementation_commit"] != block["executing_implementation_commit"]:
            _bad("authorisation commits differ from the validated authorisation")
        _expect("gpu", gpu, {
            "physical_index": block["physical_gpu_index"],
            "uuid": block["gpu_uuid"],
            "pci_bus": block["pci_bus"],
            "cuda_visible_devices": block["cuda_visible_devices"],
            "logical_device": block["logical_device"],
        })
        if prov["implementation_file_hashes"] != block["implementation_file_hashes"]:
            _bad("implementation hashes differ from the active authorisation")
        if prov["implementation_file_hashes"] != measured["implementation_file_hashes"]:
            _bad("implementation hashes differ from the measured provenance")
        if prov != measured or auth["authorization_commit"] != measured["mres"]["head"]:
            _bad("provenance differs from the measured provenance")

    train = manifest["training_evidence"]
    pinned_train = pins["training_evidence"]
    _keys("training_evidence", train, ("run_id", "manifest_sha256", "manifest_bytes", "consumption_sha256", "consumption_bytes",
                                       "completion_state", "consumption_state", "authorization_commit",
                                       "executing_implementation_commit"))
    _expect("training_evidence", train, {
        "run_id": pinned_train["run_id"],
        "manifest_sha256": pinned_train["manifest"]["sha256"],
        "manifest_bytes": pinned_train["manifest"]["bytes"],
        "consumption_sha256": pinned_train["consumption"]["sha256"],
        "consumption_bytes": pinned_train["consumption"]["bytes"],
        "completion_state": "pilot_completed",
        "consumption_state": "consumed_successfully",
        "authorization_commit": pinned_train["authorization_commit"],
        "executing_implementation_commit": pinned_train["executing_implementation_commit"],
    })

    checkpoint = manifest["checkpoint"]
    pinned_checkpoint = pins["checkpoint"]
    _keys("checkpoint", checkpoint, ("update", "weight_variant", "directory", "members", "weights_sha256_before_generation",
                                     "weights_sha256_after_generation", "other_updates_loaded", "b1_diffusion_weights_loaded"))
    _expect("checkpoint identity", (checkpoint["update"], checkpoint["weight_variant"], checkpoint["directory"],
                                    checkpoint["other_updates_loaded"], checkpoint["b1_diffusion_weights_loaded"]),
            (CHECKPOINT_UPDATE, "raw", pinned_checkpoint["directory"], False, False))
    _keys("checkpoint.members", checkpoint["members"], pinned_checkpoint["members"])
    _expect("checkpoint members", checkpoint["members"], pinned_checkpoint["members"])
    weights = pinned_checkpoint["members"][WEIGHT_MEMBER]["sha256"]
    if checkpoint["weights_sha256_before_generation"] != weights or checkpoint["weights_sha256_after_generation"] != weights:
        _bad("checkpoint weights changed or differ from the pinned identity")

    schedule = manifest["schedule"]
    _keys("schedule", schedule, ("sha256", "length_vector_sha256", "invocation_count", "raw_attempts", "numpy_version",
                                 "rebuilt_and_matched_accepted_bytes"))
    _expect("schedule", {k: schedule[k] for k in schedule if k != "numpy_version"}, {
        "sha256": pins["schedule"]["schedule"]["sha256"],
        "length_vector_sha256": pins["schedule"]["length_vector"]["sha256"],
        "invocation_count": INVOCATION_COUNT,
        "raw_attempts": ATTEMPT_COUNT,
        "rebuilt_and_matched_accepted_bytes": True,
    })
    if not isinstance(schedule["numpy_version"], str) or schedule["numpy_version"] == "":
        _bad("schedule numpy version is missing")

    b1ref = manifest["b1_reference"]
    _keys("b1_reference", b1ref, ("evidence_directory", "files", "metrics_recomputed_equal_to_accepted", "regenerated", "rerun"))
    _expect("b1_reference", b1ref, {
        "evidence_directory": pins["b1_pool"]["directory"],
        "files": pins["b1_pool"]["files"],
        "metrics_recomputed_equal_to_accepted": True,
        "regenerated": False,
        "rerun": False,
    })

    _expect("normalisation", manifest["normalisation"], NORMALISATION_BLOCK)

    accounting = manifest["accounting"]
    metrics = manifest["metrics"]
    _keys("accounting", accounting, ACCOUNTING_KEYS)
    _keys("metrics", metrics, METRICS_KEYS)
    for key in ACCOUNTING_KEYS:
        _int("accounting." + key, accounting[key])
    if accounting["raw_attempts"] != ATTEMPT_COUNT or accounting["generation_invocations"] != INVOCATION_COUNT:
        raise DiagnosticError("attempt_accounting_invalid", "attempt or invocation count is not the accepted schedule")
    if (accounting["replacements"], accounting["resampled_attempts"], accounting["dropped_attempts"]) != (0, 0, 0):
        raise DiagnosticError("attempt_accounting_invalid", "replacement, resampling or dropping was recorded")
    if accounting["valid_outputs"] + accounting["invalid_outputs"] != accounting["raw_attempts"]:
        raise DiagnosticError("attempt_accounting_invalid", "valid and invalid attempts do not sum to the raw attempts")
    if accounting["exact_length_hits"] + accounting["length_mismatches"] + accounting["invalid_outputs"] != accounting["raw_attempts"]:
        raise DiagnosticError("attempt_accounting_invalid", "exact hits, mismatches and invalid attempts do not sum to the raw attempts")
    if accounting["unique_valid_outputs"] + accounting["duplicates"] != accounting["valid_outputs"]:
        raise DiagnosticError("attempt_accounting_invalid", "unique and duplicate outputs do not sum to the valid outputs")
    if accounting["empty_or_unparseable_outputs"] > accounting["invalid_outputs"]:
        raise DiagnosticError("attempt_accounting_invalid", "empty outputs exceed invalid outputs")
    for key in ACCOUNTING_KEYS:
        if key in metrics and metrics[key] != accounting[key]:
            raise DiagnosticError("attempt_accounting_invalid", "metrics and accounting disagree on " + key)
    if metrics["exact_hit_rate_denominator"] != "raw_attempts" or metrics["exact_hit_rate_is_execution_success_requirement"] is not False:
        _bad("exact-hit rate is not a raw-attempt report")
    if metrics["exact_hit_rate"] != accounting["exact_length_hits"] / float(accounting["raw_attempts"]):
        _bad("exact-hit rate is inconsistent with its counts")

    guardrails = manifest["hard_guardrails"]
    _keys("hard_guardrails", guardrails, ("decisions", "values", "checkpoint_eligible", "outcome", "exact_hit_rate_is_a_threshold"))
    ids = [rule[0] for rule in HARD_GUARDRAIL_RULES]
    _keys("guardrail values", guardrails["values"], ids)
    if [item.get("id") for item in guardrails["decisions"]] != ids:
        _bad("guardrail decisions are not the five approved guardrails in order")
    raw, valid = accounting["raw_attempts"], accounting["valid_outputs"]
    values = guardrails["values"]
    expected_values = {
        "valid_nonempty_acgu_fraction": valid / float(raw),
        "empty_or_unparseable_fraction": accounting["empty_or_unparseable_outputs"] / float(raw),
        "unique_fraction": accounting["unique_valid_outputs"] / float(valid) if valid else 0.0,
        "largest_duplicate_share": metrics["largest_duplicate_share"],
    }
    for key, value in expected_values.items():
        if values[key] != value:
            _bad("guardrail value is inconsistent with the counts: " + key)
    all_passed = True
    for item, (rule_id, comparison, threshold, _denominator) in zip(guardrails["decisions"], HARD_GUARDRAIL_RULES):
        _keys("guardrail decision", item, ("comparison", "id", "passed", "status", "threshold", "value"))
        if (item["comparison"], item["threshold"], item["value"]) != (comparison, threshold, values[rule_id]):
            _bad("guardrail decision disagrees with its rule or value: " + rule_id)
        if item["status"] == "evaluated":
            if item["passed"] is not _passes(comparison, item["value"], threshold):
                _bad("guardrail decision contradicts its value: " + rule_id)
        elif item["passed"] is not False:
            _bad("an unevaluated guardrail cannot pass")
        all_passed = all_passed and item["passed"] is True
    _expect("guardrail outcome", (guardrails["checkpoint_eligible"], guardrails["outcome"], guardrails["exact_hit_rate_is_a_threshold"]),
            (all_passed, "passed" if all_passed else "failed", False))

    _expect("consequence", manifest["consequence"], {
        "eligible_for_m7": None if all_passed else False,
        "automatic_rerun": False,
        "automatic_learning_rate_fallback": False,
        "nearest_train_similarity": "report_only_no_approved_threshold",
    })
    _keys("report_only_diagnostics", manifest["report_only_diagnostics"], ("sha256", "thresholds_defined"))
    _sha("report hash", manifest["report_only_diagnostics"]["sha256"])
    _expect("report thresholds", manifest["report_only_diagnostics"]["thresholds_defined"], False)

    comparison = manifest["comparison"]
    _keys("comparison", comparison, ("role", "d1_update21", "b1_accepted_pool", "d1_guardrail_values", "b1_guardrail_values",
                                     "b1_guardrails_are_an_eligibility_decision"))
    _keys("comparison.d1_update21", comparison["d1_update21"], COMPARISON_FIELDS)
    _keys("comparison.b1_accepted_pool", comparison["b1_accepted_pool"], COMPARISON_FIELDS)
    _keys("comparison.b1_guardrail_values", comparison["b1_guardrail_values"], ids)
    if comparison["d1_update21"] != {field: metrics[field] for field in COMPARISON_FIELDS} or comparison["d1_guardrail_values"] != values:
        _bad("comparison disagrees with the D1 metrics and guardrails")
    if comparison["b1_guardrails_are_an_eligibility_decision"] is not False or comparison["b1_accepted_pool"]["raw_attempts"] != ATTEMPT_COUNT:
        _bad("comparison B1 side is inconsistent")

    _expect("roles", manifest["roles"], ROLES_BLOCK)
    ledgers = manifest["ledgers"]
    _keys("ledgers", ledgers, LEDGER_FILES)
    for key, value in ledgers.items():
        _sha("ledgers." + key, value)
    _expect("closure", manifest["closure"], CLOSURE_BLOCK)
    return True


def _read_evidence_file(path, deps):
    """A regular, non-symlink file whose size equals the bytes read."""
    try:
        observed = deps.lstat(path)
    except FileNotFoundError:
        raise DiagnosticError("evidence_verification_failed", "evidence file is missing: " + os.path.basename(path))
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise DiagnosticError("evidence_verification_failed", "evidence file is not a regular file: " + os.path.basename(path))
    data = bytes(deps.read_bytes(path))
    if int(observed.st_size) != len(data):
        raise DiagnosticError("evidence_verification_failed", "evidence file size drifted: " + os.path.basename(path))
    return data


def _normalised(value):
    return json.loads(canonical_json(value).decode("utf-8"))


def _verify_by_recomputation(manifest, contents, report_document, recompute):
    """Rerun the pinned metrics and five guardrails from the written audited ledger."""
    metrics = recompute["metrics"]
    attempts = parse_attempt_ledger(contents[AUDITED_LEDGER_NAME])
    assert_normalisation_reconciles(attempts)
    summary = _normalised(metrics.summarise_attempts(attempts))
    guardrails = _normalised(evaluate_guardrails(metrics, attempts, recompute["train_cores"]))
    if json.loads(contents[METRICS_NAME].decode("utf-8")) != summary or manifest["metrics"] != summary:
        raise DiagnosticError("evidence_verification_failed", "metrics differ from a rerun on the audited ledger")
    if json.loads(contents[GUARDRAILS_NAME].decode("utf-8")) != guardrails:
        raise DiagnosticError("evidence_verification_failed", "guardrail file differs from a rerun on the audited ledger")
    section = manifest["hard_guardrails"]
    if (section["decisions"], section["values"], section["checkpoint_eligible"]) != (
        guardrails["decisions"], guardrails["values"], guardrails["checkpoint_eligible"]
    ):
        raise DiagnosticError("evidence_verification_failed", "manifest guardrails differ from a rerun on the audited ledger")
    d1_side = {field: summary[field] for field in COMPARISON_FIELDS}
    b1_attempts = recompute["b1_attempts"]
    b1_summary = _normalised(metrics.summarise_attempts(b1_attempts))
    b1_guardrails = _normalised(evaluate_guardrails(metrics, b1_attempts, recompute["train_cores"]))
    b1_side = {field: b1_summary[field] for field in COMPARISON_FIELDS}
    for comparison in (manifest["comparison"], report_document["comparison"]):
        if comparison["d1_update21"] != d1_side or comparison["d1_guardrail_values"] != guardrails["values"]:
            raise DiagnosticError("evidence_verification_failed", "comparison D1 side differs from a rerun on the audited ledger")
        if comparison["b1_accepted_pool"] != b1_side or comparison["b1_guardrail_values"] != b1_guardrails["values"]:
            raise DiagnosticError("evidence_verification_failed", "comparison B1 side differs from the recomputed accepted B1 reference")


def verify_written_evidence(output, manifest_bytes, deps, pins=None, expected=None, recompute=None):
    """Reopen the manifest and every emitted file. Compare each with what the manifest claims.

    ``recompute`` carries the pinned metrics module, the already-opened TRAIN
    cores, and the recomputed accepted B1 attempts. When it is given, the
    metrics and the five guardrails are rerun from the written audited ledger.
    """
    b1 = b1_runner()
    path = os.path.join(output, MANIFEST_NAME)
    try:
        reread = b1.verify_bound_evidence_file(path, manifest_bytes, deps)
    except b1.DevelopmentPoolError as exc:
        raise DiagnosticError(exc.code, exc.detail)
    manifest = json.loads(reread.decode("utf-8"))
    if canonical_json(manifest) != reread:
        raise DiagnosticError("evidence_verification_failed", "written manifest is not canonical JSON")
    validate_success_manifest(manifest, pins, expected)
    contents = {}
    for key, name in LEDGER_FILES.items():
        data = _read_evidence_file(os.path.join(output, name), deps)
        if sha256_bytes(data) != manifest["ledgers"][key]:
            raise DiagnosticError("evidence_verification_failed", "evidence file hash differs from the manifest: " + name)
        contents[name] = data
    report = _read_evidence_file(os.path.join(output, REPORT_NAME), deps)
    if sha256_bytes(report) != manifest["report_only_diagnostics"]["sha256"]:
        raise DiagnosticError("evidence_verification_failed", "report hash differs from the manifest")
    if json.loads(contents[METRICS_NAME].decode("utf-8")) != manifest["metrics"]:
        raise DiagnosticError("evidence_verification_failed", "metrics file differs from the manifest")
    guardrail_file = json.loads(contents[GUARDRAILS_NAME].decode("utf-8"))
    if guardrail_file["decisions"] != manifest["hard_guardrails"]["decisions"] or guardrail_file["values"] != manifest["hard_guardrails"]["values"]:
        raise DiagnosticError("evidence_verification_failed", "guardrail file differs from the manifest")
    report_document = json.loads(report.decode("utf-8"))
    if set(report_document) != {"d1_update21", "b1_accepted_pool", "m6_strict_prefix_rule_sensitivity", "comparison"}:
        raise DiagnosticError("evidence_verification_failed", "report keys differ from the schema")
    if report_document["comparison"] != manifest["comparison"]:
        raise DiagnosticError("evidence_verification_failed", "report comparison differs from the manifest")
    for side in ("d1_update21", "b1_accepted_pool"):
        block = report_document[side]
        if block["thresholds_defined"] is not False or block["clustering_or_embedding_metrics"] is not False:
            raise DiagnosticError("evidence_verification_failed", "report defines a threshold or a deferred metric")
        if "maximum_edit_similarity_to_train" not in block or any("identity" in key for key in block):
            raise DiagnosticError("evidence_verification_failed", "report uses the wrong similarity field name")
    expected_hash_report = canonical_json({
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "raw_ledger_sha256": manifest["ledgers"]["raw_ledger_sha256"],
        "audited_ledger_sha256": manifest["ledgers"]["audited_ledger_sha256"],
    })
    if _read_evidence_file(os.path.join(output, HASH_REPORT_NAME), deps) != expected_hash_report:
        raise DiagnosticError("evidence_verification_failed", "manifest hash report differs from the manifest")
    if recompute is not None:
        _verify_by_recomputation(manifest, contents, report_document, recompute)
    schedule_copy = contents[SCHEDULE_COPY_NAME]
    if sha256_bytes(schedule_copy) != manifest["schedule"]["sha256"]:
        raise DiagnosticError("evidence_verification_failed", "schedule copy is not the accepted schedule")
    return manifest


# ---------------------------------------------------------------- run

class Dependencies(object):
    def __init__(
        self,
        read_bytes=None,
        lstat=None,
        realpath=None,
        sha256_file_fn=None,
        environ=None,
        git=None,
        gpu_preflight=None,
        mkdir=None,
        write_exclusive=None,
        subprocess_run=None,
        fold=None,
        observe_tree=None,
        nearest=None,
        unlink=None,
    ):
        self.read_bytes = read_bytes or _default_read_bytes
        self.lstat = lstat or os.lstat
        self.realpath = realpath or os.path.realpath
        self.sha256_file = sha256_file_fn or sha256_file
        self.environ = os.environ if environ is None else environ
        self.git = git or _default_git
        self.gpu_preflight = gpu_preflight or _default_gpu_preflight
        self.mkdir = mkdir or os.mkdir
        self.write_exclusive = write_exclusive or _exclusive_write
        self.subprocess_run = subprocess_run or _default_subprocess_run
        self.fold = fold or _default_fold
        self.nearest = nearest or nearest_train
        self.unlink = unlink or os.unlink
        self._observe_tree = observe_tree

    def observe_checkpoint_tree(self, directory):
        if self._observe_tree is not None:
            return self._observe_tree(directory)
        return _translate(lambda: m6_contract().observe_checkpoint_tree(directory))


def _default_git(repo, args):
    completed = subprocess.run(["git", "-C", str(repo)] + list(args), shell=False, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise DiagnosticError("git_status_unreadable", completed.stderr.strip() or "git command failed")
    return completed.stdout


def _default_gpu_preflight(parent, physical_gpu):
    b1 = b1_runner()
    try:
        return b1.default_gpu_preflight(parent, physical_gpu)
    except b1.DevelopmentPoolError as exc:
        raise DiagnosticError(exc.code, exc.detail)


def _default_subprocess_run(argv, cwd, env, shell=False):
    b1 = b1_runner()
    if shell is not False or not argv or argv[0] != PINNED_PYTHON or cwd != b1.GENERATION_CWD:
        raise DiagnosticError("python_interpreter_rejected", "generation must use the pinned interpreter and RNAGenesis directory")
    return subprocess.run(argv, cwd=cwd, env=env, shell=False, check=False, capture_output=True)


def _default_fold(sequence):
    import RNA

    return RNA.fold(sequence)


def _exclusive_write(path, data):
    b1 = b1_runner()
    try:
        b1._exclusive_write(path, data)
    except b1.DevelopmentPoolError as exc:
        raise DiagnosticError(exc.code, exc.detail)


def _exists(path, lstat):
    try:
        lstat(path)
    except FileNotFoundError:
        return False
    return True


def _looks_like_sequence(text):
    return re.search(r"[ACGUacgu]{8,}", str(text)) is not None


def _controlled_class_name(exc):
    name = type(exc).__name__
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name) is None or _looks_like_sequence(name):
        return "Exception"
    return name


def _normalise_error(exc):
    """Message-safe. Third-party exception text is never copied."""
    if isinstance(exc, DiagnosticError):
        return exc
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return DiagnosticError("interrupted", "run interrupted by " + type(exc).__name__)
    b1 = b1_runner()
    if isinstance(exc, b1.DevelopmentPoolError):
        return DiagnosticError(exc.code, exc.detail)
    if isinstance(exc, FileNotFoundError):
        return DiagnosticError("output_file_missing", "expected file is missing")
    if isinstance(exc, OSError):
        return DiagnosticError("filesystem_error", "filesystem operation failed")
    return DiagnosticError("unexpected_runtime_failure", "unexpected runtime failure; exception_class=" + _controlled_class_name(exc))


FAILURE_KEYS = (
    "schema_version", "status", "code", "detail", "authorisation_id", "authorization_commit", "authorization_parent_commit",
    "executing_implementation_commit", "output_directory", "consumption_state", "gpu", "stage", "invocation_index",
    "checkpoint_state", "resumable", "reuse_permitted", "m6_complete", "m7_authorised",
)


def failure_record(error, context, progress):
    detail = error.detail if not _looks_like_sequence(error.detail) else "failure detail omitted"
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": "failed",
        "code": error.code,
        "detail": detail,
        "authorisation_id": context["authorisation_id"],
        "authorization_commit": context["authorization_commit"],
        "authorization_parent_commit": context["authorization_parent_commit"],
        "executing_implementation_commit": context["executing_implementation_commit"],
        "output_directory": context["output_directory"],
        "consumption_state": "consumed_output_created",
        "gpu": dict(context["gpu"]),
        "stage": progress["stage"],
        "invocation_index": progress["invocation_index"],
        "checkpoint_state": progress["checkpoint_state"],
        "resumable": False,
        "reuse_permitted": False,
        "m6_complete": False,
        "m7_authorised": False,
    }


def _write_failure(output, error, deps, context, progress):
    path = os.path.join(output, FAILURE_RECORD_NAME)
    if _exists(os.path.join(output, MANIFEST_NAME), deps.lstat) or _exists(path, deps.lstat):
        raise DiagnosticError("manifest_collision", "success and failure records must be mutually exclusive")
    deps.write_exclusive(path, canonical_json(failure_record(error, context, progress)))


def run(deps=None, run_root=None, pins=None):
    """Refuse an inactive configuration first.

    Non-sensitive preflight happens before consumption. The output directory and
    consumption record come before TRAIN is opened and before the checkpoint is
    read, hashed, or loaded. After that boundary every failure stays consumed.
    """
    deps = Dependencies() if deps is None else deps
    run_root = RUN_ROOT if run_root is None else run_root
    pins = production_pins() if pins is None else pins
    config_bytes = bytes(deps.read_bytes(CONFIG_PATH))
    config = load_config_bytes(config_bytes)
    reject_inactive_before_execution(config)
    authorisation = assert_active_configuration(config, run_root, pins, deps.lstat)
    output = authorisation["output_directory"]
    physical_gpu = authorisation["physical_gpu_index"]
    assert_output_directory_absent(output, deps.lstat)
    b1 = b1_runner(deps.read_bytes)
    try:
        b1.assert_parent_cuda(deps.environ, physical_gpu)
    except b1.DevelopmentPoolError as exc:
        raise DiagnosticError(exc.code, exc.detail)
    provenance = measure_provenance(authorisation, config_bytes, deps)
    metrics = b1.load_metrics_from_verified_source(provenance.pop("metrics_source_bytes"))
    b1.assert_bound_metrics_configuration(metrics, provenance.pop("metrics_configuration_bytes"))
    cleaner = b1.load_cleaner_from_verified_source(provenance.pop("cleaner_source_bytes"))
    probe = deps.gpu_preflight(deps.environ, physical_gpu)
    try:
        b1.assert_gpu_probe(probe, physical_gpu, {"gpu_uuid": authorisation["gpu_uuid"], "pci_bus": authorisation["pci_bus"]})
    except b1.DevelopmentPoolError as exc:
        raise DiagnosticError(exc.code, exc.detail)
    try:
        structure_features("GGGGAAAACCCC", deps.fold)
    except Exception:
        raise DiagnosticError("fold_unavailable", "the RNA folding library is not usable, so the report-only MFE cannot be computed")
    training = verify_training_evidence(deps, pins)
    scheduled = pins["schedule"]
    vector_bytes = _read_pinned_regular_file(
        os.path.join(scheduled["directory"], scheduled["length_vector"]["name"]), scheduled["length_vector"], deps, "schedule_hash_mismatch"
    )
    accepted_schedule = _read_pinned_regular_file(
        os.path.join(scheduled["directory"], scheduled["schedule"]["name"]), scheduled["schedule"], deps, "schedule_hash_mismatch"
    )
    schedule, schedule_bytes = rebuild_and_verify_schedule(vector_bytes, accepted_schedule, pins)
    b1_reference = load_b1_reference(deps, metrics, schedule, pins)
    consumption = canonical_json(
        {
            "schema_version": "m6-diagnostic-authorisation-consumption-1",
            "authorisation_id": authorisation["authorisation_id"],
            "authorization_parent_commit": authorisation["authorization_parent_commit"],
            "executing_implementation_commit": authorisation["executing_implementation_commit"],
            "output_directory": output,
            "consumption_state": "consumed_output_created",
            "reuse_permitted": False,
        }
    )
    context = {
        "authorisation_id": authorisation["authorisation_id"],
        "authorization_commit": provenance["mres"]["head"],
        "authorization_parent_commit": authorisation["authorization_parent_commit"],
        "executing_implementation_commit": authorisation["executing_implementation_commit"],
        "output_directory": output,
        "gpu": {
            "physical_index": physical_gpu,
            "uuid": authorisation["gpu_uuid"],
            "pci_bus": authorisation["pci_bus"],
            "cuda_visible_devices": authorisation["cuda_visible_devices"],
            "logical_device": LOGICAL_DEVICE,
        },
    }
    progress = {"stage": "consumption", "invocation_index": None, "checkpoint_state": "not_read"}
    try:
        deps.mkdir(output)
    except FileExistsError:
        raise DiagnosticError("output_directory_exists", "refusing to overwrite or resume an output directory")
    # ---- consumed: nothing below may be retried or resumed.
    try:
        deps.write_exclusive(os.path.join(output, CONSUMPTION_RECORD_NAME), consumption)
        return _execute(
            deps, output, authorisation, provenance, training, schedule, schedule_bytes,
            b1_reference, metrics, cleaner, consumption, pins, progress, vector_bytes,
        )
    except BaseException as exc:
        error = _normalise_error(exc)
        if not _exists(os.path.join(output, MANIFEST_NAME), deps.lstat):
            try:
                _write_failure(output, error, deps, context, progress)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as secondary:
                error.secondary_failure = getattr(secondary, "code", None) or "failure_record_write_failed"
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise error


def _execute(deps, output, authorisation, provenance, training, schedule, schedule_bytes,
             b1_reference, metrics, cleaner, consumption, pins, progress, vector_bytes):
    b1 = b1_runner()
    write = deps.write_exclusive
    progress["stage"] = "checkpoint_verification"
    checkpoint_before = verify_checkpoint(deps, pins)
    progress["checkpoint_state"] = "verified_before_generation"
    progress["stage"] = "train_open"
    train_cores = open_train_cores(deps, b1.parse_length_vector(vector_bytes), pins)
    progress["stage"] = "schedule_copy"
    write(os.path.join(output, SCHEDULE_COPY_NAME), schedule_bytes)
    progress["stage"] = "cache_setup"
    b1._create_cache_directories(output)
    deps.mkdir(os.path.join(output, GENERATION_OUTPUT_DIRECTORY))
    checkpoint_dir = pins["checkpoint"]["directory"]
    attempts, raw_rows, invocation_rows, payloads = [], [], [], []
    progress["stage"] = "generation"
    for invocation in schedule["invocations"]:
        progress["invocation_index"] = invocation["invocation_index"]
        mapped, metadata, payload = _run_invocation(output, invocation, authorisation["physical_gpu_index"], deps, cleaner, checkpoint_dir)
        attempts.extend(mapped)
        raw_rows.extend(b1.raw_attempt_record(row) for row in mapped)
        invocation_rows.append({field: metadata[field] for field in b1.RAW_INVOCATION_FIELDS})
        payloads.append((metadata, payload))
    progress["invocation_index"] = None
    progress["stage"] = "accounting"
    b1.assert_attempt_accounting(attempts, schedule)
    if len(attempts) != ATTEMPT_COUNT:
        raise DiagnosticError("raw_output_count_mismatch", "generated attempt count is not 1000")
    progress["stage"] = "normalisation_reconciliation"
    assert_normalisation_reconciles(attempts)
    progress["stage"] = "post_generation_checkpoint_verification"
    progress["checkpoint_state"] = "changed_or_unverifiable_after_generation"
    checkpoint_after = verify_checkpoint(deps, pins)
    if checkpoint_after["signatures"] != checkpoint_before["signatures"]:
        raise DiagnosticError("checkpoint_identity_mismatch", "checkpoint files changed during generation")
    progress["checkpoint_state"] = "verified_unchanged_after_generation"
    progress["stage"] = "metrics"
    raw_ledger = b1.serialize_jsonl(raw_rows, b1.RAW_ATTEMPT_FIELDS, "original_attempt_index")
    audited = b1.serialize_jsonl(attempts, b1.ATTEMPT_FIELDS, "original_attempt_index")
    if raw_ledger == audited:
        raise DiagnosticError("ledger_not_distinct", "raw and audited ledgers must be distinct")
    d1_metrics = metrics.summarise_attempts(attempts)
    d1_guardrails = evaluate_guardrails(metrics, attempts, train_cores)
    b1_attempts = b1_reference["attempts"]
    assert_pairing(attempts, b1_attempts)
    b1_metrics = metrics.summarise_attempts(b1_attempts)
    b1_guardrails = evaluate_guardrails(metrics, b1_attempts, train_cores)
    progress["stage"] = "report_only_diagnostics"
    report = {
        "d1_update21": report_only_diagnostics(attempts, train_cores, deps.fold, deps.nearest),
        "b1_accepted_pool": report_only_diagnostics(b1_attempts, train_cores, deps.fold, deps.nearest),
        "m6_strict_prefix_rule_sensitivity": {
            "d1_update21": strict_m6_rule_sensitivity(attempts),
            "b1_accepted_pool": strict_m6_rule_sensitivity(b1_attempts),
        },
        "comparison": comparison_table(d1_metrics, d1_guardrails, b1_metrics, b1_guardrails),
    }
    progress["stage"] = "evidence_write"
    invocation_bytes = canonical_json(
        {"schema_version": MANIFEST_SCHEMA_VERSION, "role": "invocation_output_manifest", "invocation_count": len(invocation_rows), "invocations": invocation_rows}
    )
    metrics_bytes = canonical_json(d1_metrics)
    guardrail_bytes = canonical_json(d1_guardrails)
    report_bytes = canonical_json(report)
    for name, data in (
        (RAW_LEDGER_NAME, raw_ledger),
        (AUDITED_LEDGER_NAME, audited),
        (INVOCATION_MANIFEST_NAME, invocation_bytes),
        (METRICS_NAME, metrics_bytes),
        (GUARDRAILS_NAME, guardrail_bytes),
        (REPORT_NAME, report_bytes),
    ):
        write(os.path.join(output, name), data)
    weights = checkpoint_before["members"][WEIGHT_MEMBER]["sha256"]
    passed = bool(d1_guardrails["checkpoint_eligible"])
    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "status": "complete",
        "experiment_id": EXPERIMENT_ID,
        "authorisation": {
            "authorisation_id": authorisation["authorisation_id"],
            "authorization_commit": provenance["mres"]["head"],
            "authorization_parent_commit": authorisation["authorization_parent_commit"],
            "executing_implementation_commit": authorisation["executing_implementation_commit"],
            "consumption_state": "consumed_successfully",
            "single_use": True,
            "reuse_permitted": False,
        },
        "gpu": {
            "physical_index": authorisation["physical_gpu_index"],
            "uuid": authorisation["gpu_uuid"],
            "pci_bus": authorisation["pci_bus"],
            "cuda_visible_devices": authorisation["cuda_visible_devices"],
            "logical_device": LOGICAL_DEVICE,
        },
        "provenance": {key: value for key, value in provenance.items()},
        "training_evidence": training,
        "checkpoint": {
            "update": CHECKPOINT_UPDATE,
            "weight_variant": "raw",
            "directory": checkpoint_before["directory"],
            "members": checkpoint_before["members"],
            "weights_sha256_before_generation": weights,
            "weights_sha256_after_generation": checkpoint_after["members"][WEIGHT_MEMBER]["sha256"],
            "other_updates_loaded": False,
            "b1_diffusion_weights_loaded": False,
        },
        "schedule": {
            "sha256": SCHEDULE_SHA256,
            "length_vector_sha256": LENGTH_VECTOR_SHA256,
            "invocation_count": schedule["invocation_count"],
            "raw_attempts": schedule["total_attempts"],
            "numpy_version": schedule["numpy_version"],
            "rebuilt_and_matched_accepted_bytes": True,
        },
        "b1_reference": {
            "evidence_directory": pins["b1_pool"]["directory"],
            "files": b1_reference["files"],
            "metrics_recomputed_equal_to_accepted": b1_reference["metrics_recomputed_equal_to_accepted"],
            "regenerated": False,
            "rerun": False,
        },
        "normalisation": dict(NORMALISATION_BLOCK),
        "accounting": accounting_from(d1_metrics, attempts, len(invocation_rows)),
        "metrics": d1_metrics,
        "hard_guardrails": {
            "decisions": d1_guardrails["decisions"],
            "values": d1_guardrails["values"],
            "checkpoint_eligible": passed,
            "outcome": "passed" if passed else "failed",
            "exact_hit_rate_is_a_threshold": False,
        },
        "consequence": {
            "eligible_for_m7": False if not passed else None,
            "automatic_rerun": False,
            "automatic_learning_rate_fallback": False,
            "nearest_train_similarity": "report_only_no_approved_threshold",
        },
        "report_only_diagnostics": {"sha256": sha256_bytes(report_bytes), "thresholds_defined": False},
        "comparison": report["comparison"],
        "roles": dict(ROLES_BLOCK),
        "ledgers": {
            "raw_ledger_sha256": sha256_bytes(raw_ledger),
            "audited_ledger_sha256": sha256_bytes(audited),
            "invocation_output_manifest_sha256": sha256_bytes(invocation_bytes),
            "metrics_sha256": sha256_bytes(metrics_bytes),
            "guardrails_sha256": sha256_bytes(guardrail_bytes),
            "schedule_copy_sha256": sha256_bytes(schedule_bytes),
            "consumption_record_sha256": sha256_bytes(consumption),
        },
        "closure": dict(CLOSURE_BLOCK),
    }
    progress["stage"] = "manifest_validation"
    manifest = json.loads(canonical_json(manifest).decode("utf-8"))
    expected = {"authorisation": authorisation, "provenance": provenance}
    validate_success_manifest(manifest, pins, expected)
    manifest_bytes = canonical_json(manifest)
    write(
        os.path.join(output, HASH_REPORT_NAME),
        canonical_json({"manifest_sha256": sha256_bytes(manifest_bytes), "raw_ledger_sha256": sha256_bytes(raw_ledger), "audited_ledger_sha256": sha256_bytes(audited)}),
    )
    progress["stage"] = "evidence_reverification"
    for metadata, payload in payloads:
        b1.verify_regular_file(metadata["raw_file_path"], metadata, deps, cleaner, expected_bytes=payload)
    if _exists(os.path.join(output, FAILURE_RECORD_NAME), deps.lstat):
        raise DiagnosticError("manifest_collision", "success and failure records must be mutually exclusive")
    write(os.path.join(output, MANIFEST_NAME), manifest_bytes)
    try:
        verify_written_evidence(
            output, manifest_bytes, deps, pins, expected,
            {"metrics": metrics, "train_cores": train_cores, "b1_attempts": b1_attempts},
        )
    except BaseException:
        try:
            deps.unlink(os.path.join(output, MANIFEST_NAME))
        finally:
            pass
        raise
    progress["stage"] = "complete"
    return {"status": "success", "guardrail_outcome": manifest["hard_guardrails"]["outcome"], "manifest_sha256": sha256_bytes(manifest_bytes)}


HELP_TEXT = """\
M6 update-21 diagnostic generation.

The checked-in configuration is inactive and not executable. This entry point
accepts no arguments other than --help. It does not accept checkpoint, data,
schedule, configuration, GPU, or output paths.
"""


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        sys.stdout.write(HELP_TEXT)
        return 0
    if arguments:
        print("cli_argument_rejected: no path, data, model, configuration, GPU, or output override is accepted", file=sys.stderr)
        return 2
    for name in FORBIDDEN_ENVIRONMENT:
        if os.environ.get(name):
            print("environment_injection_rejected: environment variables cannot enable execution", file=sys.stderr)
            return 2
    try:
        run()
    except DiagnosticError as exc:
        message = exc.code + ": " + exc.detail
        if exc.secondary_failure:
            message += " secondary: " + exc.secondary_failure
        print(message, file=sys.stderr)
        return 2 if exc.code == "execution_not_authorised" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

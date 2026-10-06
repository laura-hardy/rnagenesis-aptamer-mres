#!/usr/bin/env python3
"""M7 replicate contract (inactive).

Importing this module imports only the standard library, ``m7_common`` and the
accepted M6 contract (loaded by its tracked path). It does not import torch,
Accelerate, Diffusers, or RNAGenesis, and it does not open biological data,
model weights, or a run directory. The checked-in configuration is inactive and
non-consumable.

An authorisation-only commit may later change only the replicate configuration.
It may carry one or two independently consumable entries, one for seed 43 and
one for seed 44. Each entry binds its own seed, GPU, output directory and
identities. Consuming one entry never consumes the other.

The applied learning-rate schedule is the pure function
``learning_rate_multiplier``. It generalises the accepted M6 explicit
applied-update convention to a 105-update schedule. Position 106 is the next
unapplied position. It is not a PyTorch scheduler ``last_epoch`` and is never
applied to the optimizer.
"""

from __future__ import annotations

import importlib.util
import math
import os
import re
import sys

MRES_ROOT = "/home/laura/rnagenesis-aptamer-mres"


def _load_sibling(name, relative):
    """Load one tracked sibling once and share it, so every module sees one ``M7Error``."""
    path = os.path.join(MRES_ROOT, relative)
    existing = sys.modules.get(name)
    if existing is not None and os.path.realpath(getattr(existing, "__file__", "")) == os.path.realpath(path):
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


common = _load_sibling("m7_common", "scripts/modelling/m7_common.py")
M7Error = common.M7Error

CONFIG_RELATIVE = "config/experiments/D1_final_replicates.yaml"
COMMON_RELATIVE = "scripts/modelling/m7_common.py"
CONTRACT_RELATIVE = "scripts/modelling/m7_replicate_contract.py"
RUNNER_RELATIVE = "scripts/modelling/m7_replicate_runner.py"
DOCUMENT_STATUS = "M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED"
ACTIVE_DOCUMENT_STATUS = "M7_REPLICATES_AUTHORISED_FOR_SINGLE_USE_EXECUTION"
SCHEMA_VERSION = "m7-replicate-config-1"
MANIFEST_SCHEMA_VERSION = "m7-replicate-manifest-1"
CONSUMPTION_SCHEMA_VERSION = "m7-replicate-consumption-1"
EXPERIMENT_ID = "D1_final_replicates"
CONDITION_LABEL = "D1_mres_curated_aptamer_diffusion_adapted"
ACTIVE_PHASE = "M7_D1_final_replicate"
ACTIVE_SCOPE_PREFIX = "single_use_m7_d1_replicate_seed_"
ACTIVE_ACTIVATION = "active_unconsumed"
INACTIVE_ACTIVATION = "inactive_no_authorisation"
SESSION_PATTERN = "m5_single_use_timestamp_and_scope"
CONSUMPTION_EVENT = "bound_output_directory_creation"
SUCCESS_MANIFEST_NAME = "m7_replicate_manifest.json"
AUTHORISATION_ID_PATTERN = re.compile(r"m7_[a-z0-9_]*seed(43|44)[a-z0-9_]*")
TIMESTAMP_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+[0-9]{2}:[0-9]{2}$")

TARGET_SEEDS = (43, 44)
EXCLUDED_SEEDS = (42,)
MINIMUM_COMPLETED_SEEDS = 1
VALIDATION_DRAW_SEED = 1
EPOCHS = 5
UPDATES_PER_EPOCH = 21
MICROBATCHES_PER_EPOCH = 84
TOTAL_UPDATES = EPOCHS * UPDATES_PER_EPOCH
TOTAL_MICROBATCHES = EPOCHS * MICROBATCHES_PER_EPOCH
WARMUP_UPDATES = 10
POST_SCHEDULE_POSITION = TOTAL_UPDATES + 1
BASE_LEARNING_RATE = 3e-5
VALIDATION_UPDATES = (0, 21, 42, 63, 84, 105)
CANDIDATE_EPOCHS = common.CANDIDATE_EPOCHS
CANDIDATE_UPDATES = (21, 42, 63, 84, 105)
FINAL_WINDOW = (8, 8, 8, 5)
APPLIED_LEARNING_RATE_TRACE_SHA256 = "37013ac0a50290dbb476f4cdec806f058b8fb3347d967ac2d6e59b6e07aeae50"
RETENTION_MINIMUM_DATE = "2026-11-01"
CHECKPOINT_NAME_FORMAT = (
    "D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-{seed}__epoch-{epoch}__update-{update}__git-{commit}"
)
OPERATIONAL_STRETCH_TARGET = "2026-10-07T18:00:00+11:00"
OPERATIONAL_HARD_TARGET = "2026-10-08T17:00:00+11:00"
OPERATIONAL_TIME_FACTOR = 1.25
OPERATIONAL_BUFFER_HOURS = 2
M8_TOTAL_RAW_ATTEMPTS = 30000
ACTIVE_ROLES = ("B1_INITIALISATION", "FROZEN_ENCDEC", "TRAIN_TEXT", "VALIDATION_ARTIFACT", "VALIDATION_CSV")
IMPLEMENTATION_FILE_PATHS = (
    "scripts/modelling/build_validation_artifacts.py",
    "scripts/modelling/m5_smoke_contract.py",
    "scripts/modelling/m6_pilot_contract.py",
    "scripts/modelling/m6_pilot_runner.py",
    "scripts/modelling/m7_common.py",
    "scripts/modelling/m7_replicate_contract.py",
    "scripts/modelling/m7_replicate_runner.py",
    "tests/modelling/test_m7_common.py",
    "tests/modelling/test_m7_replicate_contract.py",
    "tests/modelling/test_m7_replicate_runner.py",
)
PERMITTED_AUTHORIZATION_FILES = (CONFIG_RELATIVE,)
DOCUMENTED_DEVIATIONS = (
    "explicit_applied_lr_not_pytorch_last_epoch",
    "manual_accumulation_accelerator_steps_1",
    "pinned_artifact_loader_uses_numpy_frombuffer",
    "validation_draws_loaded_not_regenerated",
    "fresh_epoch_permutation_from_one_dedicated_generator",
)
RESIDUAL_LIMITATIONS = (
    "hash_to_open_toctou_not_closed",
    "gpu_identity_collector_not_exercised_without_a_gpu",
)
# Keys that would make a replicate manifest carry selection or guardrail evidence.
FORBIDDEN_MANIFEST_KEY_FRAGMENTS = ("select", "guardrail", "eligib", "ensemble", "best_epoch", "winner")


# ------------------------------------------------------------------ arithmetic


def learning_rate_multiplier(position):
    """Multiplier for one explicit scheduler position.

    Positions 1 through 105 are the applied optimizer updates. Positions 1
    through 10 are linear warm-up (position 1 is 0.1 of the base rate and
    position 10 is the base rate). Positions 11 through 105 are cosine decay
    over the rest of the 105-update schedule; position 11 has progress 0.
    Position 106 is the next unapplied position and is exactly 0.
    """
    if isinstance(position, bool) or not isinstance(position, int):
        raise M7Error("learning_rate_schedule_invalid", "scheduler position must be an integer")
    if position == POST_SCHEDULE_POSITION:
        return 0.0
    if position < 1 or position > TOTAL_UPDATES:
        raise M7Error("learning_rate_schedule_invalid", "scheduler position is outside the M7 schedule")
    if position <= WARMUP_UPDATES:
        return position / float(WARMUP_UPDATES)
    progress = (position - WARMUP_UPDATES - 1) / float(TOTAL_UPDATES - WARMUP_UPDATES)
    return 0.5 * (1.0 + math.cos(math.pi * progress))


def applied_learning_rate(update_number):
    if isinstance(update_number, bool) or not isinstance(update_number, int):
        raise M7Error("learning_rate_schedule_invalid", "applied update number must be an integer")
    if update_number < 1 or update_number > TOTAL_UPDATES:
        raise M7Error("learning_rate_zero_applied", "only updates 1 through 105 have an applied learning rate")
    multiplier = learning_rate_multiplier(update_number)
    if multiplier <= 0.0:
        raise M7Error("learning_rate_zero_applied", "an applied optimizer update would use learning rate zero")
    return BASE_LEARNING_RATE * multiplier


def applied_learning_rate_trace():
    return tuple(applied_learning_rate(update) for update in range(1, TOTAL_UPDATES + 1))


def trace_strings(trace=None):
    trace = applied_learning_rate_trace() if trace is None else trace
    return [common.format_decimal(value) for value in trace]


def trace_sha256(strings=None):
    strings = trace_strings() if strings is None else strings
    return common.sha256_bytes(common.canonical_json(list(strings)))


def assert_trace_hash():
    if len(applied_learning_rate_trace()) != TOTAL_UPDATES:
        raise M7Error("learning_rate_schedule_invalid", "the applied trace is not 105 values")
    if trace_sha256() != APPLIED_LEARNING_RATE_TRACE_SHA256:
        raise M7Error("learning_rate_schedule_invalid", "the applied learning-rate trace hash drifted")
    return True


def assign_applied_learning_rate(optimizer, update_number):
    """Set every param-group learning rate to the applied schedule value. Zero is refused."""
    learning_rate = applied_learning_rate(update_number)
    groups = getattr(optimizer, "param_groups", None)
    if not isinstance(groups, list) or not groups:
        raise M7Error("learning_rate_schedule_invalid", "optimizer param groups are missing")
    for group in groups:
        group["lr"] = learning_rate
    return learning_rate


def epoch_update_range(epoch):
    if not common.is_candidate_epoch(epoch):
        raise M7Error("validation_schedule_invalid", "epoch is not 1 through 5")
    first = (epoch - 1) * UPDATES_PER_EPOCH + 1
    return first, first + UPDATES_PER_EPOCH - 1


def epoch_of_update(update):
    if isinstance(update, bool) or not isinstance(update, int) or update < 1 or update > TOTAL_UPDATES:
        raise M7Error("validation_schedule_invalid", "update is outside 1 through 105")
    return (update - 1) // UPDATES_PER_EPOCH + 1


def epoch_windows():
    """The 21 accumulation windows of one epoch. Every epoch repeats them, ending in [8,8,8,5]."""
    m6 = common.m6_contract()
    windows = common.translate_m6(m6.accumulation_windows)
    if len(windows) != UPDATES_PER_EPOCH or windows[-1] != FINAL_WINDOW:
        raise M7Error("microbatch_arithmetic_invalid", "the epoch windows are not 21 ending in [8, 8, 8, 5]")
    if sum(len(window) for window in windows) != MICROBATCHES_PER_EPOCH:
        raise M7Error("microbatch_arithmetic_invalid", "an epoch is not 84 microbatches")
    if sum(sum(window) for window in windows) != m6.TRAIN_RECORD_COUNT:
        raise M7Error("microbatch_arithmetic_invalid", "an epoch does not cover every TRAIN record exactly once")
    return windows


def assert_seed(seed):
    """Seeds 43 and 44 only. Seeds 1 (validation draws), 42 (pilot) and every other value are refused."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise M7Error("unexpected_seed", "seed is not an integer")
    if seed == VALIDATION_DRAW_SEED:
        raise M7Error("unexpected_seed", "seed 1 is the validation-draw seed and is not a training seed")
    if seed in EXCLUDED_SEEDS:
        raise M7Error("unexpected_seed", "seed 42 is the excluded M6 pilot seed")
    if seed not in TARGET_SEEDS:
        raise M7Error("unexpected_seed", "seed is not a prespecified M7 training seed")
    return seed


def checkpoint_child_name(seed, epoch, commit):
    assert_seed(seed)
    first, last = epoch_update_range(epoch)
    if not common.is_sha40(commit):
        raise M7Error("provenance_mismatch", "checkpoint name requires the implementation commit")
    return CHECKPOINT_NAME_FORMAT.format(seed=seed, epoch=epoch, update=last, commit=commit)


def expected_checkpoint_names(seed, commit):
    return [checkpoint_child_name(seed, epoch, commit) for epoch in CANDIDATE_EPOCHS]


def permutation_digest(indices):
    return common.translate_m6(lambda: common.m6_contract().permutation_digest(indices))


def aggregate_validation(pair_losses):
    return common.translate_m6(lambda: common.m6_contract().aggregate_pair_mse(pair_losses))


def validation_schedule_for(update):
    if update not in VALIDATION_UPDATES:
        raise M7Error("validation_schedule_invalid", "validation is only defined at updates 0, 21, 42, 63, 84, and 105")
    return True


def identifies_candidate(update):
    """Update 0 is provenance only. Updates 21 through 105 are candidates."""
    validation_schedule_for(update)
    return update in CANDIDATE_UPDATES


# ------------------------------------------------------------------ static configuration sections


def expected_static_sections():
    """Every configuration section that never changes between inactive and active."""
    m6 = common.m6_contract()
    return {
        "seed_plan": {
            "target_seeds": list(TARGET_SEEDS),
            "excluded_seeds": list(EXCLUDED_SEEDS),
            "pilot_seed_42_excluded": True,
            "validation_draw_seed": VALIDATION_DRAW_SEED,
            "validation_draw_seed_is_separate": True,
            "minimum_permitted_completed_seeds": MINIMUM_COMPLETED_SEEDS,
            "one_seed_only_via_sealed_operational_deviation": True,
            "independent_b1_initialisation_per_seed": True,
            "fresh_model_optimizer_scheduler_rng_per_seed_and_subprocess": True,
            "m6_checkpoint_updates_forbidden_as_initialisation_or_resume": [7, 14, 21],
            "forbidden_initialisation_weight_sha256": {
                "update_7": "7f1cdbd854c1d26c5b8bfe68469bc7e59f5d7293c4a105d724c1c63c83a32f10",
                "update_14": "0a2fa065f962adaf54e63b797974367915a6552382a8db76c3fbd0c6a0078901",
                "update_21": "47b2dc9b392ea766eee7e947f0f92f5a039c42ac714326104e719352d20b5924",
            },
        },
        "replicate_decisions": {
            "initialization": "immutable_B1_generic_diffusion_checkpoint",
            "encdec_frozen": "complete",
            "trainable": "full_denoiser",
            "precision": "fp32",
            "epochs": EPOCHS,
            "fresh_permutation_each_epoch": True,
            "physical_microbatch": m6.PHYSICAL_MICROBATCH,
            "gradient_accumulation": m6.GRADIENT_ACCUMULATION,
            "intended_effective_batch": m6.INTENDED_EFFECTIVE_BATCH,
            "train_records": m6.TRAIN_RECORD_COUNT,
            "microbatches_per_epoch": MICROBATCHES_PER_EPOCH,
            "optimizer_updates_per_epoch": UPDATES_PER_EPOCH,
            "total_optimizer_updates_per_seed": TOTAL_UPDATES,
            "final_window_microbatch_sizes_every_epoch": list(FINAL_WINDOW),
            "accumulation_weighting": "example_weighted_contributions_sum_to_one",
            "optimizer_name": "AdamW",
            "learning_rate": BASE_LEARNING_RATE,
            "beta1": m6.ADAMW_BETA1,
            "beta2": m6.ADAMW_BETA2,
            "weight_decay": m6.ADAMW_WEIGHT_DECAY,
            "epsilon": m6.ADAMW_EPSILON,
            "gradient_clip_norm": m6.GRADIENT_CLIP_NORM,
            "ema_enabled": False,
            "validation_and_diagnostics_use": "raw_denoiser_weights",
            "automatic_learning_rate_change": False,
            "learning_rate_sweep": False,
            "resume_supported": False,
            "technical_retry": "same_seed_and_configuration_from_B1_new_immutable_attempt_directory_new_authorisation",
            "candidate_diagnostics_in_replicate_runner": False,
            "selection_in_replicate_runner": False,
        },
        "schedule": {
            "name": "explicit_applied_update_cosine",
            "diffusers_constructor_used": False,
            "base_learning_rate": BASE_LEARNING_RATE,
            "applied_optimizer_updates": TOTAL_UPDATES,
            "warmup_updates": WARMUP_UPDATES,
            "update_1_multiplier": 0.1,
            "post_schedule_position": POST_SCHEDULE_POSITION,
            "post_schedule_multiplier": 0.0,
            "applied_learning_rate_may_be_zero": False,
            "applied_learning_rate_trace_length": TOTAL_UPDATES,
            "applied_learning_rate_trace_sha256": APPLIED_LEARNING_RATE_TRACE_SHA256,
            "authority": CONTRACT_RELATIVE + ":learning_rate_multiplier",
        },
        "validation": {
            "validation_updates": list(VALIDATION_UPDATES),
            "update_0_provenance_only": True,
            "candidate_epochs": list(CANDIDATE_EPOCHS),
            "candidate_updates": list(CANDIDATE_UPDATES),
            "update_0_selectable": False,
            "artifacts": "accepted_m4_four_draw_artifacts_unchanged",
            "artifacts_regenerated": False,
            "ranking_rule": common.RANKING_RULE,
            "ranking_is_not_a_selection": True,
        },
        "checkpoints": {
            "saved_every_epoch": True,
            "retained_epochs": list(CANDIDATE_EPOCHS),
            "weight_variant": "raw",
            "reload_and_complete_state_dict_equality_required": True,
            "persistent_buffers_covered": True,
            "exact_inventory_members": list(common.CHECKPOINT_MEMBERS),
            "leaf_link_count": 1,
            "same_device_required_where_supported": True,
            "symlink_safe_ancestry_required": True,
            "save_optimizer_moments": False,
            "resumable_training_sidecar": False,
            "retention_minimum_date": RETENTION_MINIMUM_DATE,
            "deletion_implemented": False,
            "naming_pattern": CHECKPOINT_NAME_FORMAT,
        },
        "data": {
            "open_permitted": False,
            "ref_access": False,
            "eval_access": False,
            "fitting_role": "TRAIN_TEXT",
            "development_evaluation_role": "VALIDATION_fixed_draw",
            "train_text_sha256": m6.TRAIN_TEXT_SHA256,
            "train_core_count": m6.TRAIN_RECORD_COUNT,
            "validation_csv_sha256": m6.VALIDATION_CSV_SHA256,
            "validation_core_count": m6.VALIDATION_SEQUENCE_COUNT,
            "validation_sequence_order_sha256": m6.VALIDATION_SEQUENCE_ORDER_SHA256,
            "validation_order_artifact_sha256": m6.VALIDATION_ORDER_ARTIFACT_SHA256,
            "validation_draw_manifest_sha256": m6.VALIDATION_DRAW_MANIFEST_SHA256,
            "validation_hash_report_sha256": m6.VALIDATION_HASH_REPORT_SHA256,
            "validation_timesteps_sha256": m6.VALIDATION_TIMESTEPS_SHA256,
            "validation_noise_sha256": m6.VALIDATION_NOISE_SHA256,
            "accepted_validation_artifact_directory": m6.ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY,
            "future_train_text_path": m6.FUTURE_TRAIN_TEXT_PATH,
            "future_validation_csv_path": m6.FUTURE_VALIDATION_CSV_PATH,
            "ref_hash_metadata_only": m6.REF_HASH_METADATA,
            "eval_hash_metadata_only": m6.EVAL_HASH_METADATA,
            "ref_path": None,
            "eval_path": None,
        },
        "model": {
            "initialisation_relative_path": m6.B1_RELATIVE_PATH,
            "prohibited_initialisation": ["checkpoints/Aptamer/diffusion", "any_m6_attempt_checkpoint"],
            "b1_weight_sha256": m6.B1_WEIGHT_SHA256,
            "b1_unet_config_sha256": m6.B1_UNET_CONFIG_SHA256,
            "encdec_relative_path": m6.ENCDEC_RELATIVE_PATH,
            "evaluated_weight_variant": "raw",
        },
        "candidate_guardrail_boundary": {
            "configuration": "config/experiments/D1_candidate_guardrails.yaml",
            "candidate_order": "sealed_validation_ranking",
            "evaluation": "lazy_until_first_passing_candidate",
            "attempts_per_candidate": 1000,
            "schedule_sha256": m6.PAIRED_SCHEDULE_SHA256,
            "no_candidate_passes": "record_no_eligible_checkpoint_do_not_change_lr_thresholds_architecture_or_seed",
        },
        "m8_boundary": {
            "implemented_in_this_package": False,
            "total_raw_d1_attempts": M8_TOTAL_RAW_ATTEMPTS,
            "one_seed_attempts": M8_TOTAL_RAW_ATTEMPTS,
            "two_seed_attempts_each": M8_TOTAL_RAW_ATTEMPTS // 2,
            "two_seed_split": "deterministic_and_balanced_within_requested_length_strata",
        },
        "operational_cutoff": {
            "recorded_not_automated": True,
            "stretch_target": OPERATIONAL_STRETCH_TARGET,
            "hard_target": OPERATIONAL_HARD_TARGET,
            "seed_44_proceeds_only_if": "current_time + 1.25 x measured_seed_43_end_to_end_execution_time + 2_hours <= hard_target",
            "time_factor": OPERATIONAL_TIME_FACTOR,
            "buffer_hours": OPERATIONAL_BUFFER_HOURS,
            "decision_is_operational_only": True,
            "may_depend_on_seed_43_scientific_results": False,
            "one_seed_deviation_sealed_before_m8_generation": True,
        },
        "residual_limitations": list(RESIDUAL_LIMITATIONS),
    }


CONFIGURATION_ROOT_KEYS = (
    "authorisation_entries",
    "authorisation_schema",
    "candidate_guardrail_boundary",
    "checkpoints",
    "condition_manifest_label",
    "consumable_by_executable_workflow",
    "created_against_mres_commit",
    "data",
    "document_status",
    "execution",
    "experiment_id",
    "m8_boundary",
    "manifest_schema_version",
    "model",
    "operational_cutoff",
    "replicate_decisions",
    "residual_limitations",
    "rnagenesis_branch",
    "rnagenesis_commit",
    "schedule",
    "schema_version",
    "seed_plan",
    "validation",
)
EXECUTION_KEYS = ("authorised", "biological_paths_permitted", "gpu_identity_bound")
SESSION_KEYS = ("consumption_event", "pattern", "resume_permitted", "wall_clock_expiry")
VALIDATION_ARTIFACT_HASH_KEYS = ("draw_manifest", "noise", "order_artifact", "sequence_order", "timesteps")
ACTIVE_ENTRY_KEYS = (
    "activation_status",
    "applied_learning_rate_trace_sha256",
    "authorisation_id",
    "authorisation_timestamp",
    "authorization_parent_commit",
    "b1_relative_path",
    "b1_unet_config_sha256",
    "b1_weight_sha256",
    "consumed",
    "cuda_visible_devices",
    "evidence_directory",
    "executing_implementation_commit",
    "expected_checkpoint_names",
    "expected_epochs",
    "expected_update_counts",
    "forbidden_initialisation_weight_sha256",
    "gpu_uuid",
    "implementation_config_sha256",
    "implementation_file_hashes",
    "interpreter",
    "ld_library_path",
    "logical_device",
    "output_directory",
    "pci_bus",
    "permitted_roles",
    "phase",
    "physical_gpu_index",
    "reuse_permitted",
    "scope",
    "seed",
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


def authorisation_schema():
    return {
        "entries_min": 1,
        "entries_max": 2,
        "entry_seeds": list(TARGET_SEEDS),
        "one_entry_per_seed": True,
        "single_authorisation_only_commit": True,
        "independent_consumption": True,
        "consuming_one_entry_never_consumes_another": True,
        "launcher_accepts_only": "authorisation_id",
        "scientific_parameters_from_cli": False,
        "retry_requires_new_entry": True,
        "permitted_changed_files": list(PERMITTED_AUTHORIZATION_FILES),
        "entry_keys": list(ACTIVE_ENTRY_KEYS),
        "entry_binds": [
            "authorisation_id",
            "seed",
            "implementation_commit",
            "physical_and_logical_gpu_identity",
            "exact_output_directory",
            "configuration_and_artifact_hashes",
            "expected_epoch_and_checkpoint_universe",
            "exact_ld_library_path_value_or_none",
            "pinned_interpreter_path_and_executable_identity",
            "branch_remote_and_permitted_changed_file_set",
        ],
        "active_entries_present_in_this_package": False,
    }


# ------------------------------------------------------------------ configuration documents


def load_config_bytes(raw):
    return common.load_config_bytes(raw)


def classify_configuration(config):
    config = common.require_mapping(config, "configuration_not_consumable", "configuration root must be a mapping")
    status = config.get("document_status")
    consumable = config.get("consumable_by_executable_workflow")
    if status == DOCUMENT_STATUS and consumable is False:
        return "inactive"
    if status == ACTIVE_DOCUMENT_STATUS and consumable is True:
        return "active"
    raise M7Error("configuration_not_consumable", "configuration is neither inactive nor a single-use active authorisation")


def assert_inactive_text(text):
    """Reject GPU bindings, active flags, and a bound path in the raw document."""
    if not isinstance(text, str):
        raise M7Error("configuration_not_consumable", "configuration text is required")
    forbidden = (
        "GPU-",
        "CUDA_VISIBLE_DEVICES",
        "authorised: true",
        "biological_paths_permitted: true",
        "gpu_identity_bound: true",
        "consumable_by_executable_workflow: true",
        "authorization_commit:",
        "activation_status: active",
    )
    for token in forbidden:
        if token in text:
            raise M7Error("configuration_not_consumable", "inactive configuration contains " + token)
    for line in text.splitlines():
        stripped = line.strip()
        for key in ("output_directory:", "evidence_directory:", "authorisation_id:", "executing_implementation_commit:", "authorization_parent_commit:"):
            if stripped.startswith(key) and not stripped.endswith("null"):
                raise M7Error("configuration_not_consumable", key[:-1] + " is not null")
    return True


def _assert_static_sections(config):
    for name, expected in expected_static_sections().items():
        if config.get(name) != expected:
            raise M7Error("configuration_not_consumable", "static section drifted: " + name)
    if config.get("authorisation_schema") != authorisation_schema():
        raise M7Error("configuration_not_consumable", "authorisation schema drifted")


def assert_inactive_configuration(config):
    """Validate the checked-in document. This does not authorise a run."""
    config = common.exact_keys(config, CONFIGURATION_ROOT_KEYS, "configuration_not_consumable")
    if config.get("document_status") != DOCUMENT_STATUS or config.get("consumable_by_executable_workflow") is not False:
        raise M7Error("configuration_not_consumable", "document status is not the inactive M7 status")
    if config.get("schema_version") != SCHEMA_VERSION or config.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        raise M7Error("configuration_not_consumable", "schema version drifted")
    if config.get("experiment_id") != EXPERIMENT_ID or config.get("condition_manifest_label") != CONDITION_LABEL:
        raise M7Error("configuration_not_consumable", "experiment identity drifted")
    if config.get("created_against_mres_commit") != common.MRES_BASE_COMMIT:
        raise M7Error("configuration_not_consumable", "MRes base commit drifted")
    if config.get("rnagenesis_commit") != common.RNAGENESIS_COMMIT or config.get("rnagenesis_branch") != common.RNAGENESIS_BRANCH:
        raise M7Error("configuration_not_consumable", "RNAGenesis pin drifted")
    execution = common.exact_keys(config.get("execution"), EXECUTION_KEYS, "configuration_not_consumable")
    if any(execution[key] is not False for key in EXECUTION_KEYS):
        raise M7Error("configuration_not_consumable", "execution flags must stay closed")
    if config.get("authorisation_entries") != []:
        raise M7Error("configuration_not_consumable", "an inactive document holds no authorisation entry")
    if common.contains_key(config, "authorization_commit"):
        raise M7Error("configuration_not_consumable", "tracked configuration must not store authorization_commit")
    for key, _item in common.walk(config):
        if key in ("physical_gpu_index", "gpu_uuid", "pci_bus", "cuda_visible_devices", "output_directory", "evidence_directory", "ld_library_path", "interpreter"):
            raise M7Error("configuration_not_consumable", "inactive configuration carries a binding key: " + key)
    _assert_static_sections(config)
    return True


def reject_inactive_before_execution(config):
    """Production gate. Raising here is the success path for the checked-in file."""
    assert_inactive_configuration(config)
    raise M7Error("execution_not_authorised", "the checked-in M7 replicate configuration is not executable")


def _sha40(value, code):
    if not common.is_sha40(value):
        raise M7Error(code, "expected a lowercase SHA-1 commit")
    return value


def _pci_bus(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{8}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]", value) is None:
        raise M7Error("identity_mismatch", "PCI bus is not an exact device address")
    return value


def _gpu_uuid(value):
    if not isinstance(value, str) or re.fullmatch(r"GPU-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value) is None:
        raise M7Error("identity_mismatch", "GPU UUID is not exact")
    return value


def assert_active_entry(entry, run_root=None):
    """Schema for one independently consumable entry. It never changes between seeds except the bindings."""
    run_root = common.RUN_ROOT if run_root is None else run_root
    m6 = common.m6_contract()
    entry = common.exact_keys(entry, ACTIVE_ENTRY_KEYS, "authorisation_shape_invalid")
    if common.contains_key(entry, "authorization_commit"):
        raise M7Error("authorisation_commit_invalid", "tracked authorisation must not store its own commit")
    seed = assert_seed(entry["seed"])
    if entry["activation_status"] != ACTIVE_ACTIVATION or entry["consumed"] is not False:
        raise M7Error("authorisation_inactive", "authorisation is not active and unconsumed")
    if entry["single_use"] is not True or entry["reuse_permitted"] is not False:
        raise M7Error("authorization_reuse", "authorisation is not single-use")
    identifier = entry["authorisation_id"]
    matched = AUTHORISATION_ID_PATTERN.fullmatch(identifier) if isinstance(identifier, str) else None
    if matched is None or int(matched.group(1)) != seed:
        raise M7Error("authorisation_field_missing", "authorisation id is not an m7 single-use id for this seed")
    parent = _sha40(entry["authorization_parent_commit"], "authorisation_commit_invalid")
    executing = _sha40(entry["executing_implementation_commit"], "authorisation_commit_invalid")
    if parent != executing:
        raise M7Error("authorisation_commit_invalid", "parent commit and executing implementation commit differ")
    if entry["phase"] != ACTIVE_PHASE or entry["scope"] != ACTIVE_SCOPE_PREFIX + str(seed):
        raise M7Error("authorisation_scope_invalid", "phase or scope is not the M7 replicate for this seed")
    if list(entry["permitted_roles"]) != list(ACTIVE_ROLES) or "REF" in entry["permitted_roles"] or "EVAL" in entry["permitted_roles"]:
        raise M7Error("authorisation_scope_invalid", "permitted roles drifted")
    physical = entry["physical_gpu_index"]
    if isinstance(physical, bool) or not isinstance(physical, int) or physical < 0:
        raise M7Error("identity_mismatch", "physical GPU index must be a nonnegative integer")
    if str(physical) != entry["cuda_visible_devices"]:
        raise M7Error("identity_mismatch", "CUDA_VISIBLE_DEVICES is not the physical GPU index")
    if entry["logical_device"] != common.LOGICAL_CUDA_DEVICE:
        raise M7Error("identity_mismatch", "logical device is not cuda:0")
    _gpu_uuid(entry["gpu_uuid"])
    _pci_bus(entry["pci_bus"])
    common.assert_ld_library_path_binding(entry["ld_library_path"])
    common.assert_interpreter_binding(entry["interpreter"])
    if not isinstance(entry["authorisation_timestamp"], str) or TIMESTAMP_PATTERN.fullmatch(entry["authorisation_timestamp"]) is None:
        raise M7Error("authorisation_field_missing", "authorisation timestamp is not an offset ISO timestamp")
    session = common.exact_keys(entry["session"], SESSION_KEYS, "authorisation_shape_invalid")
    if session["pattern"] != SESSION_PATTERN or session["wall_clock_expiry"] is not None or session["resume_permitted"] is not False:
        raise M7Error("authorisation_scope_invalid", "session conditions are not the single-use pattern")
    if session["consumption_event"] != CONSUMPTION_EVENT:
        raise M7Error("authorisation_scope_invalid", "consumption event is not bound output creation")
    name = common.assert_output_directory_shape(entry["output_directory"], run_root)
    if name != identifier:
        raise M7Error("authorisation_scope_invalid", "output directory name is not the authorisation id")
    if entry["evidence_directory"] != entry["output_directory"]:
        raise M7Error("execution_not_authorised", "evidence directory is not the bound output directory")
    common.translate_m6(lambda: m6._authorisation_identities(entry))
    if entry["applied_learning_rate_trace_sha256"] != APPLIED_LEARNING_RATE_TRACE_SHA256:
        raise M7Error("identity_mismatch", "learning-rate trace hash drifted")
    if not common.is_sha256(entry["implementation_config_sha256"]):
        raise M7Error("provenance_mismatch", "implementation configuration hash is missing")
    if entry["forbidden_initialisation_weight_sha256"] != sorted(common.M6_FORBIDDEN_WEIGHT_SHA256):
        raise M7Error("m6_checkpoint_forbidden", "forbidden M6 weight hashes drifted")
    if entry["expected_epochs"] != list(CANDIDATE_EPOCHS) or entry["expected_update_counts"] != list(CANDIDATE_UPDATES):
        raise M7Error("authorisation_scope_invalid", "expected epoch universe drifted")
    if entry["expected_checkpoint_names"] != expected_checkpoint_names(seed, executing):
        raise M7Error("authorisation_scope_invalid", "expected checkpoint universe drifted")
    hashes = common.exact_keys(entry["implementation_file_hashes"], IMPLEMENTATION_FILE_PATHS, "provenance_mismatch")
    for path, digest in hashes.items():
        if not common.is_sha256(digest):
            raise M7Error("provenance_mismatch", "implementation file hash is missing: " + path)
    return entry


def assert_active_configuration(config, run_root=None):
    """Validate an active document and return its entries keyed by seed."""
    run_root = common.RUN_ROOT if run_root is None else run_root
    config = common.exact_keys(config, CONFIGURATION_ROOT_KEYS, "authorisation_shape_invalid")
    if common.contains_key(config, "authorization_commit"):
        raise M7Error("authorisation_commit_invalid", "tracked configuration must not store authorization_commit")
    if config.get("document_status") != ACTIVE_DOCUMENT_STATUS or config.get("consumable_by_executable_workflow") is not True:
        raise M7Error("authorisation_inactive", "active document flags drifted")
    if config.get("schema_version") != SCHEMA_VERSION or config.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        raise M7Error("authorisation_scope_invalid", "schema version drifted")
    if config.get("experiment_id") != EXPERIMENT_ID or config.get("condition_manifest_label") != CONDITION_LABEL:
        raise M7Error("authorisation_scope_invalid", "experiment identity drifted")
    if config.get("rnagenesis_commit") != common.RNAGENESIS_COMMIT or config.get("rnagenesis_branch") != common.RNAGENESIS_BRANCH:
        raise M7Error("provenance_mismatch", "RNAGenesis pin drifted")
    if config.get("created_against_mres_commit") != common.MRES_BASE_COMMIT:
        raise M7Error("provenance_mismatch", "MRes base commit drifted")
    execution = common.exact_keys(config.get("execution"), EXECUTION_KEYS, "authorisation_shape_invalid")
    if any(execution[key] is not True for key in EXECUTION_KEYS):
        raise M7Error("authorisation_inactive", "execution flags are not active")
    _assert_static_sections(config)
    entries = config.get("authorisation_entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 2:
        raise M7Error("authorisation_shape_invalid", "an active document carries one or two entries")
    by_seed = {}
    identifiers = set()
    outputs = set()
    for entry in entries:
        validated = assert_active_entry(entry, run_root)
        if validated["seed"] in by_seed:
            raise M7Error("authorisation_shape_invalid", "a seed has more than one entry")
        if validated["authorisation_id"] in identifiers or validated["output_directory"] in outputs:
            raise M7Error("authorization_reuse", "entries share an authorisation id or an output directory")
        identifiers.add(validated["authorisation_id"])
        outputs.add(validated["output_directory"])
        by_seed[validated["seed"]] = validated
    for key in ("authorization_parent_commit", "executing_implementation_commit", "implementation_config_sha256", "implementation_file_hashes"):
        if len({repr(entry[key]) for entry in by_seed.values()}) != 1:
            raise M7Error("authorisation_evidence_mismatch", "entries bind different " + key)
    return by_seed


def find_entry(entries_by_seed, authorisation_id):
    """Select exactly one entry by id. Consuming it never touches another entry."""
    if not isinstance(authorisation_id, str) or AUTHORISATION_ID_PATTERN.fullmatch(authorisation_id) is None:
        raise M7Error("cli_argument_rejected", "the authorisation id is not an m7 single-use id")
    matches = [entry for entry in entries_by_seed.values() if entry["authorisation_id"] == authorisation_id]
    if len(matches) != 1:
        raise M7Error("authorisation_field_missing", "no single entry carries that authorisation id")
    return matches[0]


def parse_launcher_argv(argv):
    """The later launcher accepts one authorisation id and nothing else.

    No seed, path, GPU, epoch, learning rate, or configuration reaches the
    launcher from the command line. This grammar is checked here; the checked-in
    entry points do not dispatch to a launcher.
    """
    arguments = list(argv)
    if len(arguments) == 2 and arguments[0] == "--authorisation-id":
        if not isinstance(arguments[1], str) or AUTHORISATION_ID_PATTERN.fullmatch(arguments[1]) is None:
            raise M7Error("cli_argument_rejected", "the authorisation id is not an m7 single-use id")
        return arguments[1]
    raise M7Error("cli_argument_rejected", "the launcher accepts --authorisation-id <id> and no other argument")


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
    if left != right:
        return [prefix or "<root>"]
    return []


PERMITTED_ACTIVATION_PATHS = (
    "authorisation_entries",
    "consumable_by_executable_workflow",
    "document_status",
    "execution.authorised",
    "execution.biological_paths_permitted",
    "execution.gpu_identity_bound",
)


def assert_authorisation_delta(implementation_config, authorization_config):
    paths = differing_paths(implementation_config, authorization_config)
    unexpected = [path for path in paths if path not in PERMITTED_ACTIVATION_PATHS]
    if unexpected:
        raise M7Error("authorisation_delta_invalid", "authorization commit changes " + unexpected[0])
    if not paths:
        raise M7Error("authorisation_delta_invalid", "authorization commit does not activate anything")
    return paths


def assert_repository_binding(config, entry, observation, permitted_files=None):
    """Repository, parent-commit, delta, and file-hash binding for one entry.

    ``permitted_files`` defaults to the replicate configuration. A sibling M7
    stage with its own configuration passes its own single permitted file.
    """
    permitted = PERMITTED_AUTHORIZATION_FILES if permitted_files is None else tuple(permitted_files)
    observation = common.require_mapping(observation, "provenance_mismatch", "repository observation is missing")
    head = _sha40(observation.get("mres_head"), "authorisation_commit_invalid")
    parents = observation.get("mres_parents")
    if not isinstance(parents, (list, tuple)) or len(parents) != 1:
        raise M7Error("authorisation_commit_invalid", "live HEAD must have exactly one parent")
    parent = _sha40(parents[0], "authorisation_commit_invalid")
    if parent != entry["executing_implementation_commit"] or parent != entry["authorization_parent_commit"]:
        raise M7Error("authorisation_commit_invalid", "live HEAD parent is not the executing implementation commit")
    if head == parent:
        raise M7Error("authorisation_commit_invalid", "authorization commit and implementation commit are the same")
    if observation.get("mres_branch") != "main":
        raise M7Error("provenance_mismatch", "the MRes branch is not main")
    origin = observation.get("mres_origin_main")
    if not common.is_sha40(origin) or origin not in (parent, head):
        raise M7Error("provenance_mismatch", "origin/main is neither the implementation commit nor the authorization commit")
    if tuple(observation.get("changed_files", ())) != permitted:
        raise M7Error("authorisation_delta_invalid", "authorization commit changes a file outside its own configuration")
    assert_authorisation_delta(observation.get("implementation_config"), config)
    if common.sha256_bytes(observation.get("implementation_config_bytes", b"")) != entry["implementation_config_sha256"]:
        raise M7Error("provenance_mismatch", "implementation configuration hash does not match the parent commit")
    common.translate_m6(lambda: common.m6_contract().assert_mres_repository_clean(observation.get("mres_porcelain")))
    if observation.get("rnagenesis_head") != common.RNAGENESIS_COMMIT or observation.get("rnagenesis_branch") != common.RNAGENESIS_BRANCH:
        raise M7Error("provenance_mismatch", "RNAGenesis HEAD drifted")
    common.translate_m6(
        lambda: common.m6_contract().assert_rnagenesis_repository(
            observation.get("rnagenesis_directory_porcelain"), observation.get("rnagenesis_file_porcelain")
        )
    )
    parent_hashes = common.require_mapping(observation.get("file_sha256_at_parent"), "provenance_mismatch", "parent file hashes are missing")
    working_hashes = common.require_mapping(observation.get("file_sha256_working_tree"), "provenance_mismatch", "working tree file hashes are missing")
    for path, digest in entry["implementation_file_hashes"].items():
        if parent_hashes.get(path) != digest or working_hashes.get(path) != digest:
            raise M7Error("provenance_mismatch", "implementation file hash drifted: " + path)
    for _key, value in common.walk(config):
        if value == head:
            raise M7Error("authorisation_commit_invalid", "tracked configuration contains the live authorization commit")
    return head


def assert_output_available(entry, observation, run_root=None):
    run_root = common.RUN_ROOT if run_root is None else run_root
    common.assert_output_directory_shape(entry["output_directory"], run_root)
    if observation.get("output_exists") is not False or observation.get("output_symlink") is not False:
        raise M7Error("authorization_reuse", "the bound output directory already exists or is a symlink")
    if observation.get("component_symlink") is not False:
        raise M7Error("execution_not_authorised", "the bound output path contains a symlink")
    return entry["output_directory"]


_ENTRY_TOKEN = object()


class ValidatedEntry(object):
    """Runtime authorisation for one seed, produced only by ``validate_active_execution``."""

    def __init__(self, payload, token):
        if token is not _ENTRY_TOKEN:
            raise M7Error("execution_not_authorised", "an active entry cannot be constructed directly")
        self.payload = payload

    def __getitem__(self, key):
        return self.payload[key]

    def get(self, key, default=None):
        return self.payload.get(key, default)


def validate_active_execution(config, authorisation_id, observation, run_root=None, consumed_worker=False):
    """Stdlib gate for one entry. It imports no training stack and creates no directory.

    ``consumed_worker`` is true only inside the child, where the parent has
    already created the bound directory; the output must then exist.
    """
    run_root = common.RUN_ROOT if run_root is None else run_root
    entries = assert_active_configuration(config, run_root)
    entry = find_entry(entries, authorisation_id)
    head = assert_repository_binding(config, entry, observation)
    if consumed_worker:
        if observation.get("output_exists") is not True or observation.get("output_symlink") is not False or observation.get("component_symlink") is not False:
            raise M7Error("authorization_reuse", "consumed worker requires the bound directory")
    else:
        assert_output_available(entry, observation, run_root)
    probe = common.exact_keys(
        observation.get("gpu_probe"), ("cuda_visible_devices", "logical_device", "pci_bus", "physical_index", "uuid"), "identity_mismatch"
    )
    if (
        probe["physical_index"] != entry["physical_gpu_index"]
        or probe["uuid"] != entry["gpu_uuid"]
        or probe["pci_bus"] != entry["pci_bus"]
        or probe["logical_device"] != entry["logical_device"]
        or probe["cuda_visible_devices"] != entry["cuda_visible_devices"]
    ):
        raise M7Error("identity_mismatch", "GPU observation does not match the authorisation")
    payload = {key: entry[key] for key in ACTIVE_ENTRY_KEYS}
    payload["authorization_commit"] = head
    payload["gpu_probe"] = dict(probe)
    payload["repository_observation"] = common.translate_m6(lambda: common.m6_contract().repository_observation_record(observation))
    return ValidatedEntry(payload, _ENTRY_TOKEN)


def consumption_payload(entry):
    return {
        "activation_status_at_issue": ACTIVE_ACTIVATION,
        "authorisation_id": entry["authorisation_id"],
        "authorization_commit": entry["authorization_commit"],
        "authorization_parent_commit": entry["authorization_parent_commit"],
        "consumption_state": "consumed_output_created",
        "executing_implementation_commit": entry["executing_implementation_commit"],
        "output_directory": entry["output_directory"],
        "reuse_permitted": False,
        "schema_version": CONSUMPTION_SCHEMA_VERSION,
        "seed": entry["seed"],
    }


def consume_entry(entry, run_root=None):
    """Create this entry's directory and consume it. No other entry is touched."""
    if not isinstance(entry, ValidatedEntry):
        raise M7Error("execution_not_authorised", "output creation requires a validated active entry")
    run_root = common.RUN_ROOT if run_root is None else run_root
    return common.consume_output_directory(entry["output_directory"], consumption_payload(entry), run_root)


# ------------------------------------------------------------------ per-epoch checkpoint proof


def prove_epoch_reload(proof, stage_hook=None):
    """Validate one epoch's save-and-reload proof, cheapest checks first.

    The order is proof structure and fresh-object identity, epoch and update,
    inventory, configuration compatibility, then the complete ``state_dict``
    comparison (parameters and persistent buffers). A configuration failure
    never pays for the state comparison. The M6 proof helper only accepts
    updates 7, 14 and 21, so M7 composes the same generic M6 comparators.
    """
    m6 = common.m6_contract()
    proof = common.require_mapping(proof, "checkpoint_save_reload_incompatibility", "reload proof is missing")
    if proof.get("fresh_object_constructed") is not True:
        raise M7Error("checkpoint_save_reload_incompatibility", "reload did not construct a fresh object")
    if proof.get("original_object_id") == proof.get("reloaded_object_id"):
        raise M7Error("checkpoint_save_reload_incompatibility", "reload reused the training object")
    if proof.get("labelled_as_resume") is not False:
        raise M7Error("checkpoint_save_reload_incompatibility", "weight reload must not be labelled as training resume")
    epoch = proof.get("epoch")
    if not common.is_candidate_epoch(epoch) or proof.get("update") != epoch_update_range(epoch)[1]:
        raise M7Error("checkpoint_save_reload_incompatibility", "checkpoints are only retained at epochs 1 through 5")
    inventory = common.translate_m6(lambda: m6.assert_checkpoint_inventory(proof.get("saved_hashes")))
    common.assert_not_m6_weight(inventory[common.WEIGHT_MEMBER])
    if stage_hook is not None:
        stage_hook("checkpoint_config_proof")
    configuration = common.translate_m6(lambda: m6.assert_configuration_compatible(proof.get("original_config"), proof.get("reloaded_config")))
    if stage_hook is not None:
        stage_hook("checkpoint_state_proof")
    comparison = common.translate_m6(
        lambda: m6.compare_complete_denoiser_state(proof.get("original_state"), proof.get("reloaded_state"), proof.get("selection", "complete"))
    )
    # The M6 key name contains the word "selection". A replicate manifest carries
    # no selection vocabulary, so the same field is recorded as the comparison scope.
    comparison = dict(comparison)
    comparison["comparison_scope"] = comparison.pop("comparison_selection")
    return {
        "configuration": configuration,
        "directory_name": proof.get("directory_name"),
        "epoch": epoch,
        "fresh_load_succeeded": True,
        "inventory": proof.get("inventory"),
        "original_object_id": proof["original_object_id"],
        "reloaded_object_id": proof["reloaded_object_id"],
        "resume_supported": False,
        "saved_hashes": inventory,
        "state_comparison": comparison,
        "state_scope": "parameters_and_persistent_buffers",
        "update": proof["update"],
        "weight_reload_is_training_resume": False,
        "weight_sha256": inventory[common.WEIGHT_MEMBER],
    }


# ------------------------------------------------------------------ replicate manifest

MANIFEST_KEYS = (
    "accounting",
    "applied_learning_rate_trace",
    "authorisation",
    "b1_identity",
    "checkpoints",
    "closure",
    "completion_state",
    "config_version",
    "configuration",
    "data_roles",
    "deviations",
    "environment",
    "epoch_plan",
    "experiment_id",
    "free_space",
    "frozen_state",
    "gpu",
    "initialisation_isolation",
    "manifest_schema_version",
    "memory",
    "optimizer",
    "post_schedule_position",
    "ref_eval_access",
    "repository",
    "residual_limitations",
    "restart_policy",
    "resume_supported",
    "rng",
    "run_id",
    "schedule",
    "schema_version",
    "seed",
    "timing",
    "train_update_observations",
    "validation_artifacts",
    "validation_observations",
    "validation_ranking",
    "warnings",
)
CLOSURE = {
    "candidate_diagnostics_performed": False,
    "cross_seed_claim": False,
    "eval_opened": False,
    "human_gate_required": True,
    "m7_complete": False,
    "m8_generation_performed": False,
    "ref_opened": False,
    "scope": "single_seed_training_evidence_only",
}
RESTART_POLICY = {
    "resume_supported": False,
    "optimizer_moments_saved": False,
    "interrupted_attempt_can_continue": False,
    "restart_requires_new_output_directory": True,
    "restart_requires_new_single_use_authorisation": True,
    "restart_initialises_from": "B1",
    "restart_keeps_same_seed_and_configuration": True,
}
TRAIN_ROW_KEYS = (
    "applied_clip_norm",
    "clipped",
    "denoiser_change",
    "epoch",
    "learning_rate",
    "learning_rate_recorded_before_optimizer_step",
    "pre_clip_gradient_norm",
    "training_loss",
    "update",
)
VALIDATION_ROW_KEYS = (
    "aggregate_mse",
    "candidate",
    "epoch",
    "pair_count",
    "tensors_loaded",
    "tensors_regenerated",
    "update",
    "weight_variant",
)
EPOCH_PLAN_KEYS = (
    "epoch",
    "final_window_microbatch_sizes",
    "first_update",
    "last_update",
    "microbatches",
    "optimizer_updates",
    "permutation_digest",
)
CHECKPOINT_PROOF_KEYS = (
    "configuration",
    "directory_name",
    "epoch",
    "fresh_load_succeeded",
    "inventory",
    "original_object_id",
    "reloaded_object_id",
    "resume_supported",
    "saved_hashes",
    "state_comparison",
    "state_scope",
    "update",
    "weight_reload_is_training_resume",
    "weight_sha256",
)
INVENTORY_KEYS = (
    "all_leaf_link_counts_one",
    "all_regular_non_symlink_files",
    "ancestry_symlink_free",
    "member_count",
    "same_device",
    "tree_unchanged_across_hash_and_reload",
)
B1_IDENTITY_KEYS = (
    "initial_state_aggregate_digest",
    "initial_state_entry_count",
    "initial_state_parameter_names_sha256",
    "observed_assets",
    "unet_config_sha256",
    "weight_bytes",
    "weight_sha256",
)
ISOLATION_KEYS = (
    "b1_loaded_fresh_for_this_seed",
    "cross_seed_state_reused",
    "forbidden_weight_sha256",
    "initialisation_relative_path",
    "m6_checkpoint_loaded",
    "saved_weights_equal_a_forbidden_m6_hash",
)
ENVIRONMENT_KEYS = (
    "allow_listed_child_environment",
    "bytecode_disabled",
    "cache_isolation",
    "datasets_offline",
    "hub_offline",
    "interpreter",
    "ld_library_path",
    "package_versions_observed",
    "stray_environment_names",
    "transformers_offline",
)
TIMING_KEYS = (
    "checkpoint_seconds",
    "end_to_end_seconds",
    "synchronization",
    "training_seconds",
    "training_update_seconds",
    "validation_seconds",
    "validation_update_seconds",
)
RNG_KEYS = (
    "diffusion_generator_final_digest",
    "diffusion_generator_initial_digest",
    "diffusion_stream",
    "numpy_called_by_replicate",
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
    "training_seed",
    "validation_artifacts_regenerated",
    "validation_draw_seed",
)
MICROBATCH_KEYS = (
    "drop_last",
    "epochs",
    "final_window_examples",
    "final_window_microbatch_sizes",
    "full_window_examples",
    "gradient_accumulation",
    "intended_effective_batch",
    "microbatches_per_epoch",
    "optimizer_updates_per_epoch",
    "physical_microbatch",
    "total_microbatches",
    "total_optimizer_updates",
    "train_records",
)


def _walk_forbidden_keys(manifest):
    for key, _item in common.walk(manifest):
        folded = str(key).casefold()
        if any(fragment in folded for fragment in FORBIDDEN_MANIFEST_KEY_FRAGMENTS):
            raise M7Error("incomplete_evidence_or_manifest", "a replicate manifest carries selection or candidate-diagnostic evidence")


def validate_replicate_manifest(manifest, binding=None):
    """Accept only a completed single-seed replicate. It carries no selection or guardrail evidence."""
    manifest = common.exact_keys(manifest, MANIFEST_KEYS, "incomplete_evidence_or_manifest")
    common.reject_sequence_text(manifest)
    _walk_forbidden_keys(manifest)
    if manifest["completion_state"] != "replicate_completed" or manifest["resume_supported"] is not False:
        raise M7Error("incomplete_evidence_or_manifest", "a replicate manifest is a completed, non-resumable seed")
    if manifest["manifest_schema_version"] != MANIFEST_SCHEMA_VERSION or manifest["schema_version"] != SCHEMA_VERSION or manifest["config_version"] != SCHEMA_VERSION:
        raise M7Error("incomplete_evidence_or_manifest", "manifest schema drifted")
    if manifest["experiment_id"] != EXPERIMENT_ID or manifest["warnings"] != []:
        raise M7Error("incomplete_evidence_or_manifest", "manifest identity or warnings drifted")
    seed = assert_seed(manifest["seed"])
    if manifest["closure"] != CLOSURE or manifest["restart_policy"] != RESTART_POLICY:
        raise M7Error("incomplete_evidence_or_manifest", "closure or restart policy drifted")
    if list(manifest["deviations"]) != [{"id": item} for item in DOCUMENTED_DEVIATIONS]:
        raise M7Error("incomplete_evidence_or_manifest", "documented deviations drifted")
    if manifest["residual_limitations"] != list(RESIDUAL_LIMITATIONS):
        raise M7Error("incomplete_evidence_or_manifest", "residual limitations drifted")
    authorisation = common.exact_keys(
        manifest["authorisation"],
        (
            "authorisation_id",
            "authorization_commit",
            "authorization_parent_commit",
            "consumption_state",
            "executing_implementation_commit",
            "reuse_permitted",
            "seed",
            "single_use",
        ),
        "incomplete_evidence_or_manifest",
    )
    if authorisation["consumption_state"] != "consumed_successfully" or authorisation["reuse_permitted"] is not False or authorisation["single_use"] is not True:
        raise M7Error("authorization_reuse", "authorisation was not consumed once successfully")
    if authorisation["seed"] != seed or manifest["run_id"] != authorisation["authorisation_id"]:
        raise M7Error("incomplete_evidence_or_manifest", "authorisation seed or run id drifted")
    if authorisation["authorization_commit"] == authorisation["executing_implementation_commit"]:
        raise M7Error("authorisation_commit_invalid", "authorization commit aliases the implementation commit")
    if binding is not None:
        for key in ("authorisation_id", "authorization_commit", "authorization_parent_commit", "executing_implementation_commit", "seed"):
            if authorisation[key] != binding[key]:
                raise M7Error("authorisation_evidence_mismatch", "manifest " + key + " does not match the entry")
    commit = authorisation["executing_implementation_commit"]
    _require_schedule(manifest)
    _require_accounting(manifest)
    _require_epoch_plan(manifest)
    _require_training_rows(manifest)
    _require_validation(manifest)
    _require_checkpoints(manifest, seed, commit)
    _require_identity(manifest)
    _require_roles_and_access(manifest)
    _require_environment_and_timing(manifest)
    if binding is not None and "ld_library_path_sha256" in binding:
        if manifest["environment"]["ld_library_path"]["sha256"] != binding["ld_library_path_sha256"]:
            raise M7Error("environment_rejected", "manifest LD_LIBRARY_PATH digest does not match the entry")
    if binding is not None and "interpreter" in binding:
        common.assert_interpreter_matches(manifest["environment"]["interpreter"], binding["interpreter"])
    _require_frozen_and_optimizer(manifest, seed)
    return True


def _require_schedule(manifest):
    expected_strings = trace_strings()
    if manifest["applied_learning_rate_trace"] != expected_strings:
        raise M7Error("learning_rate_schedule_invalid", "the applied learning-rate trace is not the 105-value authority")
    if any(float(value) <= 0.0 for value in manifest["applied_learning_rate_trace"]):
        raise M7Error("learning_rate_zero_applied", "an applied learning rate is zero")
    schedule = common.exact_keys(
        manifest["schedule"],
        (
            "applied_learning_rate_trace_sha256",
            "applied_optimizer_updates",
            "diffusers_constructor_used",
            "name",
            "update_1_multiplier",
            "warmup_updates",
        ),
        "incomplete_evidence_or_manifest",
    )
    if (
        schedule["applied_learning_rate_trace_sha256"] != trace_sha256(manifest["applied_learning_rate_trace"])
        or schedule["applied_learning_rate_trace_sha256"] != APPLIED_LEARNING_RATE_TRACE_SHA256
        or schedule["applied_optimizer_updates"] != TOTAL_UPDATES
        or schedule["warmup_updates"] != WARMUP_UPDATES
        or schedule["update_1_multiplier"] != "0.1"
        or schedule["diffusers_constructor_used"] is not False
        or schedule["name"] != "explicit_applied_update_cosine"
    ):
        raise M7Error("learning_rate_schedule_invalid", "the schedule record drifted")
    post = common.exact_keys(
        manifest["post_schedule_position"],
        ("applied_to_optimizer", "multiplier", "position", "pytorch_scheduler_last_epoch", "role"),
        "incomplete_evidence_or_manifest",
    )
    if (
        post["position"] != POST_SCHEDULE_POSITION
        or post["multiplier"] != "0"
        or post["applied_to_optimizer"] is not False
        or post["pytorch_scheduler_last_epoch"] is not None
        or post["role"] != "next_unapplied_schedule_position"
    ):
        raise M7Error("learning_rate_schedule_invalid", "position 106 was applied or recorded as last_epoch")


def _require_accounting(manifest):
    m6 = common.m6_contract()
    accounting = common.exact_keys(manifest["accounting"], MICROBATCH_KEYS, "microbatch_arithmetic_invalid")
    expected = {
        "drop_last": False,
        "epochs": EPOCHS,
        "final_window_examples": 29,
        "final_window_microbatch_sizes": list(FINAL_WINDOW),
        "full_window_examples": m6.INTENDED_EFFECTIVE_BATCH,
        "gradient_accumulation": m6.GRADIENT_ACCUMULATION,
        "intended_effective_batch": m6.INTENDED_EFFECTIVE_BATCH,
        "microbatches_per_epoch": MICROBATCHES_PER_EPOCH,
        "optimizer_updates_per_epoch": UPDATES_PER_EPOCH,
        "physical_microbatch": m6.PHYSICAL_MICROBATCH,
        "total_microbatches": TOTAL_MICROBATCHES,
        "total_optimizer_updates": TOTAL_UPDATES,
        "train_records": m6.TRAIN_RECORD_COUNT,
    }
    if accounting != expected:
        raise M7Error("microbatch_arithmetic_invalid", "microbatch accounting drifted")


def _require_epoch_plan(manifest):
    plan = manifest["epoch_plan"]
    if not isinstance(plan, list) or [item.get("epoch") for item in plan] != list(CANDIDATE_EPOCHS):
        raise M7Error("validation_schedule_invalid", "epoch plan is not epochs 1 through 5")
    digests = []
    for item in plan:
        common.exact_keys(item, EPOCH_PLAN_KEYS, "incomplete_evidence_or_manifest")
        first, last = epoch_update_range(item["epoch"])
        if (
            item["first_update"] != first
            or item["last_update"] != last
            or item["microbatches"] != MICROBATCHES_PER_EPOCH
            or item["optimizer_updates"] != UPDATES_PER_EPOCH
            or item["final_window_microbatch_sizes"] != list(FINAL_WINDOW)
        ):
            raise M7Error("microbatch_arithmetic_invalid", "an epoch boundary drifted")
        if not common.is_sha256(item["permutation_digest"]):
            raise M7Error("incomplete_evidence_or_manifest", "an epoch permutation digest is missing")
        digests.append(item["permutation_digest"])
    if len(set(digests)) != EPOCHS:
        raise M7Error("incomplete_evidence_or_manifest", "epoch permutations are not fresh and distinct")


def _require_training_rows(manifest):
    rows = manifest["train_update_observations"]
    if not isinstance(rows, list) or len(rows) != TOTAL_UPDATES:
        raise M7Error("incomplete_evidence_or_manifest", "train observations are not 105 updates")
    trace = manifest["applied_learning_rate_trace"]
    for index, row in enumerate(rows, start=1):
        common.exact_keys(row, TRAIN_ROW_KEYS, "incomplete_evidence_or_manifest")
        if row["update"] != index or row["epoch"] != epoch_of_update(index):
            raise M7Error("incomplete_evidence_or_manifest", "train observation update or epoch drifted")
        if row["learning_rate_recorded_before_optimizer_step"] is not True or row["learning_rate"] != trace[index - 1]:
            raise M7Error("learning_rate_schedule_invalid", "an applied learning rate was not the recorded trace value")
        common.finite_decimal_string(row["training_loss"])
        common.finite_decimal_string(row["pre_clip_gradient_norm"])
        common.finite_decimal_string(row["applied_clip_norm"])
        change = common.exact_keys(
            row["denoiser_change"],
            ("changed", "finite_nonzero_gradient", "flat_index", "gradient", "parameter_name", "value_after", "value_before"),
            "no_observed_denoiser_change",
        )
        if change["changed"] is not True or change["finite_nonzero_gradient"] is not True:
            raise M7Error("no_observed_denoiser_change", "denoiser change was not observed")
        if common.finite_decimal_string(change["value_before"]) == common.finite_decimal_string(change["value_after"]):
            raise M7Error("no_observed_denoiser_change", "denoiser element did not change")
        if common.finite_decimal_string(change["gradient"]) == 0.0:
            raise M7Error("no_observed_denoiser_change", "denoiser gradient was zero")


def _require_validation(manifest):
    rows = manifest["validation_observations"]
    if not isinstance(rows, list) or [row.get("update") for row in rows] != list(VALIDATION_UPDATES):
        raise M7Error("validation_schedule_invalid", "validation is not updates 0, 21, 42, 63, 84, and 105")
    values = {}
    for row in rows:
        common.exact_keys(row, VALIDATION_ROW_KEYS, "incomplete_evidence_or_manifest")
        if row["pair_count"] != common.m6_contract().VALIDATION_PAIR_COUNT or row["tensors_loaded"] is not True or row["tensors_regenerated"] is not False:
            raise M7Error("identity_mismatch", "validation did not load the fixed draws")
        if row["weight_variant"] != "raw":
            raise M7Error("identity_mismatch", "validation must use raw denoiser weights")
        common.finite_decimal_string(row["aggregate_mse"], "non_finite_validation")
        if row["update"] == 0:
            if row["candidate"] is not False or row["epoch"] is not None:
                raise M7Error("validation_schedule_invalid", "update 0 is provenance only and not a candidate")
        else:
            if row["candidate"] is not True or row["epoch"] != epoch_of_update(row["update"]) or row["update"] != epoch_update_range(row["epoch"])[1]:
                raise M7Error("validation_schedule_invalid", "a candidate validation row is not at an epoch boundary")
            values[row["epoch"]] = row["aggregate_mse"]
    ranking = common.exact_keys(
        manifest["validation_ranking"],
        ("excludes_update_0", "ranked_candidates", "rule"),
        "incomplete_evidence_or_manifest",
    )
    order = common.rank_validation_candidates(values)
    if ranking["rule"] != common.RANKING_RULE or ranking["excludes_update_0"] is not True:
        raise M7Error("incomplete_evidence_or_manifest", "ranking rule drifted")
    expected = [{"aggregate_mse": values[epoch], "epoch": epoch, "rank": position, "update": epoch_update_range(epoch)[1]} for position, epoch in enumerate(order, start=1)]
    if ranking["ranked_candidates"] != expected:
        raise M7Error("incomplete_evidence_or_manifest", "the sealed ranking does not match the validation observations")


def _require_checkpoints(manifest, seed, commit):
    checkpoints = manifest["checkpoints"]
    if not isinstance(checkpoints, list) or [item.get("epoch") for item in checkpoints] != list(CANDIDATE_EPOCHS):
        raise M7Error("checkpoint_save_reload_incompatibility", "retained checkpoints are not epochs 1 through 5")
    names = expected_checkpoint_names(seed, commit)
    m6 = common.m6_contract()
    seen_weights = set()
    for item, name in zip(checkpoints, names):
        common.exact_keys(item, CHECKPOINT_PROOF_KEYS, "checkpoint_save_reload_incompatibility")
        epoch = item["epoch"]
        if item["directory_name"] != name or item["update"] != epoch_update_range(epoch)[1]:
            raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint name or update drifted")
        if item["fresh_load_succeeded"] is not True or item["original_object_id"] == item["reloaded_object_id"]:
            raise M7Error("checkpoint_save_reload_incompatibility", "reload did not construct a distinct object")
        if item["resume_supported"] is not False or item["weight_reload_is_training_resume"] is not False or item["state_scope"] != "parameters_and_persistent_buffers":
            raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint scope is not the complete non-resume state")
        hashes = common.exact_keys(item["saved_hashes"], common.CHECKPOINT_MEMBERS, "checkpoint_save_reload_incompatibility")
        if any(not common.is_sha256(value) for value in hashes.values()):
            raise M7Error("checkpoint_save_reload_incompatibility", "a saved member hash is missing")
        weight = hashes[common.WEIGHT_MEMBER]
        if item["weight_sha256"] != weight:
            raise M7Error("checkpoint_save_reload_incompatibility", "weight hash is not the saved weight member")
        common.assert_not_m6_weight(weight)
        if weight in seen_weights:
            raise M7Error("checkpoint_save_reload_incompatibility", "two epochs saved identical weights")
        seen_weights.add(weight)
        inventory = common.exact_keys(item["inventory"], INVENTORY_KEYS, "checkpoint_save_reload_incompatibility")
        for key in INVENTORY_KEYS:
            expected = len(common.CHECKPOINT_MEMBERS) if key == "member_count" else True
            if inventory[key] != expected:
                raise M7Error("checkpoint_ancestry_unsafe", "checkpoint inventory evidence failed: " + key)
        comparison = common.exact_keys(
            item["state_comparison"],
            (
                "aggregate_digest",
                "compared_parameter_count",
                "comparison_scope",
                "complete_state_equal",
                "entry_digests",
                "includes_persistent_buffers",
                "mismatched_parameter_count",
                "parameter_names_sha256",
                "tensor_comparison",
                "weight_reload_is_training_resume",
            ),
            "checkpoint_save_reload_incompatibility",
        )
        if comparison["comparison_scope"] != "complete" or comparison["complete_state_equal"] is not True or comparison["includes_persistent_buffers"] is not True:
            raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint comparison is not complete")
        if comparison["mismatched_parameter_count"] != 0 or comparison["compared_parameter_count"] < 4 or comparison["weight_reload_is_training_resume"] is not False:
            raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint comparison is not complete")
        if not isinstance(comparison["entry_digests"], dict) or len(comparison["entry_digests"]) != comparison["compared_parameter_count"]:
            raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint entry digests are incomplete")
        configuration = common.exact_keys(
            item["configuration"],
            (
                "configuration_compatible",
                "ignored_top_level_keys",
                "normalized_sha256_equal",
                "original_normalized_sha256",
                "original_raw_sha256",
                "raw_sha256_equal",
                "reloaded_normalized_sha256",
                "reloaded_raw_sha256",
            ),
            "checkpoint_save_reload_incompatibility",
        )
        if configuration["ignored_top_level_keys"] != ["_name_or_path"] or configuration["configuration_compatible"] is not True:
            raise M7Error("checkpoint_save_reload_incompatibility", "configuration allowlist drifted")
        common.translate_m6(lambda: m6._require_checkpoint_digest_consistency(configuration, comparison))


def _require_identity(manifest):
    m6 = common.m6_contract()
    identity = common.exact_keys(manifest["b1_identity"], B1_IDENTITY_KEYS, "identity_mismatch")
    if identity["weight_sha256"] != m6.B1_WEIGHT_SHA256 or identity["unet_config_sha256"] != m6.B1_UNET_CONFIG_SHA256 or identity["weight_bytes"] != m6.B1_WEIGHT_BYTES:
        raise M7Error("identity_mismatch", "B1 identity drifted")
    common.assert_not_m6_weight(identity["weight_sha256"])
    for key in ("initial_state_aggregate_digest", "initial_state_parameter_names_sha256"):
        if not common.is_sha256(identity[key]):
            raise M7Error("identity_mismatch", "B1 initial-state digest is missing")
    if isinstance(identity["initial_state_entry_count"], bool) or not isinstance(identity["initial_state_entry_count"], int) or identity["initial_state_entry_count"] < 4:
        raise M7Error("identity_mismatch", "B1 initial-state entry count is missing")
    accepted = m6._accepted_asset_table()
    assets = common.exact_keys(identity["observed_assets"], tuple(accepted), "identity_mismatch")
    for role, spec in accepted.items():
        common.translate_m6(lambda: m6._require_streamed_asset(assets[role], role, spec))
    isolation = common.exact_keys(manifest["initialisation_isolation"], ISOLATION_KEYS, "m6_checkpoint_forbidden")
    if (
        isolation["forbidden_weight_sha256"] != sorted(common.M6_FORBIDDEN_WEIGHT_SHA256)
        or isolation["initialisation_relative_path"] != m6.B1_RELATIVE_PATH
        or isolation["m6_checkpoint_loaded"] is not False
        or isolation["saved_weights_equal_a_forbidden_m6_hash"] is not False
        or isolation["b1_loaded_fresh_for_this_seed"] is not True
        or isolation["cross_seed_state_reused"] is not False
    ):
        raise M7Error("m6_checkpoint_forbidden", "initialisation isolation evidence drifted")


def _require_roles_and_access(manifest):
    m6 = common.m6_contract()
    roles = common.exact_keys(manifest["data_roles"], ("eval", "ref", "train_text", "validation_artifacts", "validation_csv"), "incomplete_evidence_or_manifest")
    for role, expected_hash, count, path in (
        (roles["train_text"], m6.TRAIN_TEXT_SHA256, m6.TRAIN_RECORD_COUNT, m6.FUTURE_TRAIN_TEXT_PATH),
        (roles["validation_csv"], m6.VALIDATION_CSV_SHA256, m6.VALIDATION_SEQUENCE_COUNT, m6.FUTURE_VALIDATION_CSV_PATH),
    ):
        if role.get("opened") is not True or role.get("observed_sha256") != expected_hash or role.get("observed_count") != count or role.get("path") != path:
            raise M7Error("identity_mismatch", "a bound data role was not the pinned observation")
    artifacts = roles["validation_artifacts"]
    if artifacts.get("opened") is not True or artifacts.get("path") != m6.ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY:
        raise M7Error("identity_mismatch", "validation artifacts were not the accepted directory")
    for closed in (roles["ref"], roles["eval"]):
        if closed.get("opened") is not False or closed.get("observation_method") != "not_opened" or closed.get("path") is not None or closed.get("observed_sha256") is not None:
            raise M7Error("ref_or_eval_access", "REF or EVAL was opened")
    access = common.exact_keys(
        manifest["ref_eval_access"], ("eval_hash_metadata_only", "eval_opened", "ref_hash_metadata_only", "ref_opened"), "incomplete_evidence_or_manifest"
    )
    if access["ref_opened"] is not False or access["eval_opened"] is not False:
        raise M7Error("ref_or_eval_access", "REF or EVAL access is recorded")
    if access["ref_hash_metadata_only"] != m6.REF_HASH_METADATA or access["eval_hash_metadata_only"] != m6.EVAL_HASH_METADATA:
        raise M7Error("ref_or_eval_access", "REF or EVAL metadata drifted")
    artifacts_record = manifest["validation_artifacts"]
    pinned = {
        "draw_manifest_sha256": m6.VALIDATION_DRAW_MANIFEST_SHA256,
        "hash_report_sha256": m6.VALIDATION_HASH_REPORT_SHA256,
        "noise_sha256": m6.VALIDATION_NOISE_SHA256,
        "order_artifact_sha256": m6.VALIDATION_ORDER_ARTIFACT_SHA256,
        "sequence_order_sha256": m6.VALIDATION_SEQUENCE_ORDER_SHA256,
        "timestep_sha256": m6.VALIDATION_TIMESTEPS_SHA256,
        "validation_csv_sha256": m6.VALIDATION_CSV_SHA256,
    }
    for key, value in pinned.items():
        if artifacts_record.get(key) != value:
            raise M7Error("identity_mismatch", "validation artifact identity drifted: " + key)
    if artifacts_record.get("draws") != m6.VALIDATION_DRAWS or artifacts_record.get("sequence_count") != m6.VALIDATION_SEQUENCE_COUNT:
        raise M7Error("identity_mismatch", "validation draw shape drifted")
    repository = manifest["repository"]
    if repository.get("rnagenesis_commit") != common.RNAGENESIS_COMMIT or repository.get("rnagenesis_branch") != common.RNAGENESIS_BRANCH:
        raise M7Error("provenance_mismatch", "repository observation drifted")
    for key in ("mres_index_clean", "mres_tracked_clean", "mres_untracked_clean", "rnagenesis_tracked_clean", "rnagenesis_untracked_preserved"):
        if repository.get(key) is not True:
            raise M7Error("provenance_mismatch", "repository cleanliness drifted")
    configuration = common.exact_keys(
        manifest["configuration"],
        ("implementation_config_sha256", "implementation_file_hashes"),
        "incomplete_evidence_or_manifest",
    )
    if not common.is_sha256(configuration["implementation_config_sha256"]):
        raise M7Error("provenance_mismatch", "configuration hash is missing")
    common.exact_keys(configuration["implementation_file_hashes"], IMPLEMENTATION_FILE_PATHS, "provenance_mismatch")


def _require_environment_and_timing(manifest):
    environment = common.exact_keys(manifest["environment"], ENVIRONMENT_KEYS, "environment_rejected")
    if (
        environment["allow_listed_child_environment"] is not True
        or environment["stray_environment_names"] != 0
        or environment["bytecode_disabled"] is not True
        or environment["hub_offline"] is not True
        or environment["datasets_offline"] is not True
        or environment["transformers_offline"] is not True
    ):
        raise M7Error("environment_rejected", "child environment evidence drifted")
    common.assert_ld_library_path_record(environment["ld_library_path"])
    common.assert_interpreter_binding(environment["interpreter"])
    gpu = common.exact_keys(
        manifest["gpu"],
        ("cuda_visible_devices", "device_count", "logical_device", "pci_bus", "physical_index", "source", "uuid"),
        "identity_mismatch",
    )
    if gpu["logical_device"] != common.LOGICAL_CUDA_DEVICE or gpu["device_count"] != 1:
        raise M7Error("identity_mismatch", "GPU evidence drifted")
    free = common.exact_keys(
        manifest["free_space"],
        ("available_bytes", "checkpoint_count", "log_allowance_bytes", "per_checkpoint_bytes", "required_bytes", "reserve_bytes", "sufficient", "weight_bytes"),
        "insufficient_free_space",
    )
    if free["sufficient"] is not True or free["checkpoint_count"] != EPOCHS or free["available_bytes"] < free["required_bytes"]:
        raise M7Error("insufficient_free_space", "free-space budget evidence drifted")
    timing = common.exact_keys(manifest["timing"], TIMING_KEYS, "incomplete_evidence_or_manifest")
    if timing["synchronization"] != "cuda_synchronize_before_and_after_each_region":
        raise M7Error("incomplete_evidence_or_manifest", "timing was not synchronized")
    if not isinstance(timing["training_update_seconds"], list) or len(timing["training_update_seconds"]) != TOTAL_UPDATES:
        raise M7Error("incomplete_evidence_or_manifest", "training timing is not 105 update durations")
    if not isinstance(timing["validation_update_seconds"], list) or [item.get("update") for item in timing["validation_update_seconds"]] != list(VALIDATION_UPDATES):
        raise M7Error("incomplete_evidence_or_manifest", "validation timing is not six spans")
    if not isinstance(timing["checkpoint_seconds"], list) or [item.get("epoch") for item in timing["checkpoint_seconds"]] != list(CANDIDATE_EPOCHS):
        raise M7Error("incomplete_evidence_or_manifest", "checkpoint timing is not five spans")
    for key in ("end_to_end_seconds", "training_seconds", "validation_seconds"):
        if common.finite_decimal_string(timing[key]) < 0.0:
            raise M7Error("incomplete_evidence_or_manifest", "timing is negative")
    parts = (
        common.finite_decimal_string(timing["training_seconds"])
        + common.finite_decimal_string(timing["validation_seconds"])
        + math.fsum(common.finite_decimal_string(item["seconds"]) for item in timing["checkpoint_seconds"])
    )
    if parts > common.finite_decimal_string(timing["end_to_end_seconds"]) + 1e-6:
        raise M7Error("incomplete_evidence_or_manifest", "end-to-end time is shorter than its parts")
    memory = common.exact_keys(manifest["memory"], ("peak_allocated_bytes", "peak_reserved_bytes"), "incomplete_evidence_or_manifest")
    for value in memory.values():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise M7Error("incomplete_evidence_or_manifest", "memory evidence is not a nonnegative integer")


def _require_frozen_and_optimizer(manifest, seed):
    m6 = common.m6_contract()
    frozen = manifest["frozen_state"]
    for key in (
        "encdec_buffers_absent_from_optimizer",
        "encdec_eval_mode",
        "encdec_parameters_absent_from_optimizer",
        "encdec_requires_grad_false",
        "optimizer_contains_only_denoiser",
        "optimizer_parameter_ids_equal_trainable_denoiser",
    ):
        if frozen.get(key) is not True:
            raise M7Error("modified_or_trainable_encdec", "frozen-state evidence failed: " + key)
    digests = frozen.get("parameter_digests_by_update")
    buffers = frozen.get("persistent_buffer_digests_by_update")
    if (
        not isinstance(digests, dict)
        or not isinstance(buffers, dict)
        or sorted(int(key) for key in digests) != list(VALIDATION_UPDATES)
        or sorted(int(key) for key in buffers) != list(VALIDATION_UPDATES)
        or len(set(digests.values())) != 1
        or len(set(buffers.values())) != 1
    ):
        raise M7Error("modified_or_trainable_encdec", "EncDec digests changed or are incomplete")
    optimizer = manifest["optimizer"]
    expected = {
        "beta1": common.format_decimal(m6.ADAMW_BETA1),
        "beta2": common.format_decimal(m6.ADAMW_BETA2),
        "epsilon": common.format_decimal(m6.ADAMW_EPSILON),
        "gradient_clip_norm": common.format_decimal(m6.GRADIENT_CLIP_NORM),
        "learning_rate": common.format_decimal(BASE_LEARNING_RATE),
        "weight_decay": common.format_decimal(m6.ADAMW_WEIGHT_DECAY),
    }
    for key, value in expected.items():
        if optimizer.get(key) != value:
            raise M7Error("incomplete_evidence_or_manifest", "AdamW hyperparameter drifted: " + key)
    if optimizer.get("name") != "AdamW" or optimizer.get("precision") != "fp32" or optimizer.get("ema_enabled") is not False or optimizer.get("weight_variant") != "raw":
        raise M7Error("incomplete_evidence_or_manifest", "optimizer policy drifted")
    if optimizer.get("automatic_learning_rate_change") is not False or optimizer.get("learning_rate_sweep") is not False:
        raise M7Error("automatic_lr_change_rejected", "an automatic learning-rate change is present")
    rng = common.exact_keys(manifest["rng"], RNG_KEYS, "incomplete_evidence_or_manifest")
    if rng["training_seed"] != seed or rng["validation_draw_seed"] != VALIDATION_DRAW_SEED or rng["streams_are_distinct"] is not True:
        raise M7Error("identity_mismatch", "RNG seeds drifted")
    if rng["numpy_called_by_replicate"] is not False or rng["validation_artifacts_regenerated"] is not False:
        raise M7Error("incomplete_evidence_or_manifest", "NumPy or regenerated validation draws were used")
    for key, value in rng.items():
        if key.endswith("_digest") and not common.is_sha256(value):
            raise M7Error("incomplete_evidence_or_manifest", "RNG digest is not SHA-256: " + key)

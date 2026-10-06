#!/usr/bin/env python3
"""M7 candidate-guardrail stage (inactive).

Importing this module imports only the standard library, ``m7_common``, the M7
replicate contract and the accepted M6 contract. It does not import torch,
Accelerate, Diffusers, RNAGenesis, or the generation stack, and it opens no
biological data, checkpoint, or run directory. The checked-in configuration is
inactive and non-consumable, and the entry point accepts ``--help``,
``--schema`` and ``--authorisation-id <id>``; the last refuses while the
configuration is inactive.

Each candidate diagnostic is one checkpoint of one seed: the accepted 1,000
attempt M6 schedule, the approved M1 cleaner and the five numerical guardrails.
Requested-length matching, early EOS and gross length behaviour are
report-only. Candidates are evaluated lazily in the order of the sealed
validation ranking until the first passing checkpoint. An entry for the
candidate at rank ``k`` binds the failed manifests of ranks ``1..k-1``, so a
non-prefix evaluation cannot be authorised. If no candidate passes the outcome
is ``no_eligible_checkpoint``; the learning rate, thresholds, architecture and
seed are never changed automatically.

The production generation callable (``production_generate_and_measure``) is
the real default of ``run_candidate``: the 112-invocation loop through the
pinned generator, the approved M1 cleaner, the five numerical guardrails and
the retained raw/normalised ledgers. It reuses the accepted M6 diagnostic
module unchanged. Every dependency (file reads, the subprocess, git, the GPU
probe) can be injected for CPU/mock tests, but an active entry needs no
injected callable and no monkey-patching: ``launch_authorised_candidate`` wires
the real defaults. The checked-in configuration is inactive, so the launcher
and the entry point still refuse before any filesystem, TRAIN, checkpoint or
GPU access beyond reading the tracked configuration file.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import sys

MRES_ROOT = "/home/laura/rnagenesis-aptamer-mres"


def _load_sibling(name, relative):
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
replicate = _load_sibling("m7_replicate_contract", "scripts/modelling/m7_replicate_contract.py")
M7Error = common.M7Error

CONFIG_RELATIVE = "config/experiments/D1_candidate_guardrails.yaml"
CONFIG_PATH = os.path.join(MRES_ROOT, CONFIG_RELATIVE)
MODULE_RELATIVE = "scripts/modelling/m7_candidate_guardrails.py"
TEST_RELATIVE = "tests/modelling/test_m7_candidate_guardrails.py"
DOCUMENT_STATUS = "M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED"
ACTIVE_DOCUMENT_STATUS = "M7_CANDIDATE_GUARDRAILS_AUTHORISED_FOR_SINGLE_USE_EXECUTION"
SCHEMA_VERSION = "m7-candidate-guardrail-config-1"
MANIFEST_SCHEMA_VERSION = "m7-candidate-guardrail-manifest-1"
CONSUMPTION_SCHEMA_VERSION = "m7-candidate-guardrail-consumption-1"
EXPERIMENT_ID = "D1_candidate_guardrails"
ACTIVE_PHASE = "M7_D1_candidate_guardrail"
SUCCESS_MANIFEST_NAME = "m7_candidate_guardrail_manifest.json"
AUTHORISATION_ID_PATTERN = re.compile(r"m7_[a-z0-9_]*seed(43|44)[a-z0-9_]*epoch([1-5])[a-z0-9_]*")
ACTIVE_ROLES = ("ACCEPTED_SCHEDULE", "FROZEN_ENCDEC", "SEED_EPOCH_CHECKPOINT", "TRAIN_TEXT_DIAGNOSTIC_ONLY")
ATTEMPT_COUNT = 1000
INVOCATION_COUNT = 112
GENERATION_SEED_BASE = 44000
CLEANER_SHA256 = "4d0c56a7d931a2c3c5c049cfeabd4937134b3d1125ef7a68b10472527d2fd2a2"
DENIED_ROLES = ("REF", "EVAL", "VALIDATION_CSV", "VALIDATION_ARTIFACT")
GENERATION_OUTPUT_DIRECTORY = "rnagenesis_generation_output"
RAW_LEDGER_NAME = "m7_candidate_raw_attempts.jsonl"
AUDITED_LEDGER_NAME = "m7_candidate_audited_attempts.jsonl"
INVOCATION_MANIFEST_NAME = "m7_candidate_invocation_outputs.json"
METRICS_NAME = "m7_candidate_metrics.json"
GUARDRAIL_VALUES_NAME = "m7_candidate_guardrail_values.json"
REPORT_ONLY_DIAGNOSTICS_NAME = "m7_candidate_report_only_diagnostics.json"
SCHEDULE_COPY_NAME = "m7_candidate_schedule.json"
LEDGER_FILES = {
    "audited_ledger_sha256": AUDITED_LEDGER_NAME,
    "guardrail_values_sha256": GUARDRAIL_VALUES_NAME,
    "invocation_output_manifest_sha256": INVOCATION_MANIFEST_NAME,
    "metrics_sha256": METRICS_NAME,
    "raw_ledger_sha256": RAW_LEDGER_NAME,
    "report_only_diagnostics_sha256": REPORT_ONLY_DIAGNOSTICS_NAME,
    "schedule_copy_sha256": SCHEDULE_COPY_NAME,
}
IMPLEMENTATION_FILE_PATHS = (
    "config/modelling/validation_metrics_v1.yaml",
    "scripts/b1_development_pool_runner.py",
    "scripts/modelling/m4_diagnostic_metrics.py",
    "scripts/modelling/m5_smoke_contract.py",
    "scripts/modelling/m6_diagnostic_generation.py",
    "scripts/modelling/m6_pilot_contract.py",
    "scripts/modelling/m7_candidate_guardrails.py",
    "scripts/modelling/m7_common.py",
    "scripts/modelling/m7_replicate_contract.py",
    TEST_RELATIVE,
)
PERMITTED_AUTHORIZATION_FILES = (CONFIG_RELATIVE,)
HARD_GUARDRAIL_RULES = (
    ("valid_nonempty_acgu_fraction", "minimum", 0.99),
    ("empty_or_unparseable_fraction", "maximum", 0.01),
    ("unique_fraction", "minimum", 0.95),
    ("exact_train_match_rate", "maximum", 0.01),
    ("largest_duplicate_share", "maximum", 0.01),
)
REPORT_ONLY_KEYS = (
    "diagnostics",
    "early_eos_count",
    "gross_length_behaviour",
    "requested_length_exact_hit_rate",
    "requested_length_matching",
)
# The accepted M6 report-only diagnostics, reused unchanged. None is a threshold.
REPORT_ONLY_DIAGNOSTIC_ITEMS = (
    "requested_length_exact_hit_rate",
    "early_eos_and_length_mismatch_accounting",
    "nearest_train_normalized_edit_distance",
    "maximum_edit_similarity_to_train",
    "nucleotide_distribution_distance",
    "dinucleotide_distribution_distance",
    "mfe",
    "mfe_per_nucleotide",
    "paired_fraction",
    "length_stratified_summaries",
)
DIAGNOSTICS_KEYS = (
    "edit_similarity_definition",
    "edit_similarity_is_sequence_identity",
    "effect_on_ranking_or_thresholds",
    "file",
    "headline",
    "sha256",
    "thresholds_defined",
)
HEADLINE_KEYS = (
    "dinucleotide_total_variation_to_train",
    "maximum_edit_similarity_to_train",
    "mfe_median",
    "mfe_per_nt_median",
    "nearest_train_normalized_edit_distance_median",
    "nucleotide_total_variation_to_train",
    "paired_fraction_median",
)
OUTCOMES = ("passed", "failed")
PLAN_STATES = ("pending", "passed", "no_eligible_checkpoint")


# ------------------------------------------------------------------ guardrail evaluation


def guardrail_decision(guardrail_id, value, applicable=True):
    """One decision with the accepted M4 semantics: minimum is ``>=``, maximum is ``<=``."""
    rules = {rule[0]: rule for rule in HARD_GUARDRAIL_RULES}
    if guardrail_id not in rules:
        raise M7Error("guardrail_manifest_invalid", "unknown guardrail")
    _id, comparison, threshold = rules[guardrail_id]
    if not applicable or value is None:
        return {"comparison": comparison, "id": guardrail_id, "passed": False, "status": "undefined_empty_valid_denominator", "threshold": threshold, "value": value}
    number = common.finite_float(value, "guardrail_manifest_invalid")
    if number < 0.0 or number > 1.0:
        raise M7Error("guardrail_manifest_invalid", "a guardrail value is outside 0 through 1")
    passed = number >= threshold if comparison == "minimum" else number <= threshold
    return {"comparison": comparison, "id": guardrail_id, "passed": passed, "status": "evaluated", "threshold": threshold, "value": number}


def evaluate_guardrail_values(values):
    """The five numerical guardrails. A candidate passes only if every one passes."""
    values = common.exact_keys(values, tuple(rule[0] for rule in HARD_GUARDRAIL_RULES), "guardrail_manifest_invalid")
    decisions = [guardrail_decision(rule[0], values[rule[0]]) for rule in HARD_GUARDRAIL_RULES]
    return {
        "decisions": decisions,
        "exact_hit_rate_is_a_threshold": False,
        "passed": all(item["passed"] is True for item in decisions),
        "values": {rule[0]: values[rule[0]] for rule in HARD_GUARDRAIL_RULES},
    }


# ------------------------------------------------------------------ lazy evaluation


def lazy_plan(ranking, evaluated):
    """Where lazy evaluation stands.

    ``ranking`` is the sealed validation ranking (epochs, best first).
    ``evaluated`` lists ``(epoch, passed)`` in evaluation order. The evaluated
    epochs must be a prefix of the ranking, every earlier one must have failed,
    and nothing may be evaluated after the first pass.
    """
    ranking = list(ranking)
    if sorted(ranking) != list(common.CANDIDATE_EPOCHS):
        raise M7Error("selection_invalid", "the ranking is not a permutation of epochs 1 through 5")
    evaluated = [(epoch, passed) for epoch, passed in evaluated]
    if len(evaluated) > len(ranking):
        raise M7Error("selection_invalid", "more candidates were evaluated than exist")
    for position, (epoch, passed) in enumerate(evaluated):
        if epoch != ranking[position]:
            raise M7Error("selection_invalid", "evaluated candidates are not a prefix of the sealed ranking")
        if not isinstance(passed, bool):
            raise M7Error("selection_invalid", "a candidate outcome is not boolean")
        if passed and position != len(evaluated) - 1:
            raise M7Error("selection_invalid", "a candidate was evaluated after the first passing candidate")
    if evaluated and evaluated[-1][1] is True:
        return {"next_epoch": None, "selected_epoch": evaluated[-1][0], "state": "passed"}
    if len(evaluated) == len(ranking):
        return {"next_epoch": None, "selected_epoch": None, "state": "no_eligible_checkpoint"}
    return {"next_epoch": ranking[len(evaluated)], "selected_epoch": None, "state": "pending"}


# ------------------------------------------------------------------ configuration


def expected_static_sections():
    m6 = common.m6_contract()
    return {
        "candidate_plan": {
            "candidates_per_seed": len(common.CANDIDATE_EPOCHS),
            "candidate_epochs": list(common.CANDIDATE_EPOCHS),
            "update_0_is_a_candidate": False,
            "candidate_order": "sealed_validation_ranking_of_the_seed_replicate_manifest",
            "ranking_rule": common.RANKING_RULE,
            "evaluation": "lazy_until_first_passing_candidate",
            "evaluated_candidates_form_a_prefix_of_the_ranking": True,
            "select_first_passing_candidate": True,
            "no_candidate_passes": "record_no_eligible_checkpoint",
            "automatic_learning_rate_threshold_architecture_or_seed_change": False,
            "one_entry_per_candidate": True,
            "later_entry_binds_failed_earlier_manifests": True,
        },
        "diagnostic_design": {
            "raw_attempts": ATTEMPT_COUNT,
            "invocation_count": INVOCATION_COUNT,
            "schedule_sha256": m6.PAIRED_SCHEDULE_SHA256,
            "schedule_reused_not_regenerated": True,
            "weight_variant": "raw",
            "ema_weights": False,
            "cleaner": "approved_m1_cleaner",
            "cleaner_sha256": CLEANER_SHA256,
            "raw_text_retained_beside_normalised_text": True,
            "b1_pool": "accepted_evidence_read_only_never_regenerated",
            "production_generation_callable_implemented_in_this_package": True,
            "invocation_seed_base": GENERATION_SEED_BASE,
            "invalid_empty_duplicate_early_eos_and_length_mismatched_attempts_remain_counted": True,
            "resampling_replacement_truncation_padding_dropping_or_deduplication": False,
        },
        "hard_guardrails": [
            {"comparison": comparison, "id": guardrail_id, "threshold": threshold} for guardrail_id, comparison, threshold in HARD_GUARDRAIL_RULES
        ],
        "report_only": {
            "items": list(REPORT_ONLY_KEYS),
            "diagnostic_items": list(REPORT_ONLY_DIAGNOSTIC_ITEMS),
            "diagnostics_implementation": "accepted_m6_report_only_diagnostics_reused_unchanged",
            "diagnostics_affect_ranking_or_thresholds": False,
            "edit_similarity_is_sequence_identity": False,
            "requested_length_matching_is_a_threshold": False,
            "early_eos_is_a_threshold": False,
            "gross_length_behaviour_is_a_threshold": False,
            "exact_hit_rate_is_an_eligibility_threshold": False,
        },
        "data": {
            "open_permitted": False,
            "ref_access": False,
            "eval_access": False,
            "validation_csv_access": False,
            "train_text_use": "copying_and_novelty_diagnostic_only",
            "train_text_sha256": m6.TRAIN_TEXT_SHA256,
            "ref_hash_metadata_only": m6.REF_HASH_METADATA,
            "eval_hash_metadata_only": m6.EVAL_HASH_METADATA,
        },
        "retention": {
            "checkpoints_retained_through": replicate.RETENTION_MINIMUM_DATE,
            "deletion_implemented": False,
        },
    }


CONFIGURATION_ROOT_KEYS = (
    "authorisation_entries",
    "authorisation_schema",
    "candidate_plan",
    "consumable_by_executable_workflow",
    "created_against_mres_commit",
    "data",
    "diagnostic_design",
    "document_status",
    "execution",
    "experiment_id",
    "hard_guardrails",
    "manifest_schema_version",
    "report_only",
    "retention",
    "rnagenesis_branch",
    "rnagenesis_commit",
    "schema_version",
)
ACTIVE_ENTRY_KEYS = (
    "activation_status",
    "authorisation_id",
    "authorisation_timestamp",
    "authorization_parent_commit",
    "candidate_epoch",
    "candidate_seed",
    "candidate_update",
    "checkpoint_directory",
    "checkpoint_member_sha256",
    "checkpoint_relative_name",
    "checkpoint_weight_sha256",
    "consumed",
    "cuda_visible_devices",
    "evidence_directory",
    "executing_implementation_commit",
    "expected_schedule_sha256",
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
    "preceding_candidates",
    "ranking_position",
    "replicate_manifest_bytes",
    "replicate_manifest_path",
    "replicate_manifest_sha256",
    "reuse_permitted",
    "scope",
    "session",
    "single_use",
    "validation_ranking_sha256",
)


def authorisation_schema():
    return {
        "entries_per_authorisation_only_commit": "one_per_candidate_to_be_evaluated",
        "independent_consumption": True,
        "launcher_accepts_only": "authorisation_id",
        "scientific_parameters_from_cli": False,
        "retry_requires_new_entry": True,
        "permitted_changed_files": list(PERMITTED_AUTHORIZATION_FILES),
        "entry_keys": list(ACTIVE_ENTRY_KEYS),
        "entry_binds": [
            "authorisation_id",
            "seed_and_epoch",
            "ranking_position_and_failed_earlier_candidates",
            "checkpoint_directory_and_member_hashes",
            "replicate_manifest_hash",
            "physical_and_logical_gpu_identity",
            "exact_output_directory",
            "exact_ld_library_path_value_or_none",
            "pinned_interpreter_path_and_executable_identity",
            "replicate_manifest_path_bytes_and_sha256",
            "update_checkpoint_relative_name_and_weight_hash",
            "branch_remote_and_permitted_changed_file_set",
        ],
        "active_entries_present_in_this_package": False,
    }


def assert_inactive_configuration(config):
    config = common.exact_keys(config, CONFIGURATION_ROOT_KEYS, "configuration_not_consumable")
    if config.get("document_status") != DOCUMENT_STATUS or config.get("consumable_by_executable_workflow") is not False:
        raise M7Error("configuration_not_consumable", "document status is not the inactive M7 status")
    if config.get("schema_version") != SCHEMA_VERSION or config.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION or config.get("experiment_id") != EXPERIMENT_ID:
        raise M7Error("configuration_not_consumable", "schema or experiment identity drifted")
    if config.get("created_against_mres_commit") != common.MRES_BASE_COMMIT:
        raise M7Error("configuration_not_consumable", "MRes base commit drifted")
    if config.get("rnagenesis_commit") != common.RNAGENESIS_COMMIT or config.get("rnagenesis_branch") != common.RNAGENESIS_BRANCH:
        raise M7Error("configuration_not_consumable", "RNAGenesis pin drifted")
    execution = common.exact_keys(config.get("execution"), replicate.EXECUTION_KEYS, "configuration_not_consumable")
    if any(execution[key] is not False for key in replicate.EXECUTION_KEYS):
        raise M7Error("configuration_not_consumable", "execution flags must stay closed")
    if config.get("authorisation_entries") != []:
        raise M7Error("configuration_not_consumable", "an inactive document holds no authorisation entry")
    if common.contains_key(config, "authorization_commit"):
        raise M7Error("configuration_not_consumable", "tracked configuration must not store authorization_commit")
    for key, _item in common.walk(config):
        if key in ("physical_gpu_index", "gpu_uuid", "pci_bus", "cuda_visible_devices", "output_directory", "evidence_directory", "ld_library_path", "interpreter", "replicate_manifest_path"):
            raise M7Error("configuration_not_consumable", "inactive configuration carries a binding key: " + key)
    for name, expected in expected_static_sections().items():
        if config.get(name) != expected:
            raise M7Error("configuration_not_consumable", "static section drifted: " + name)
    if config.get("authorisation_schema") != authorisation_schema():
        raise M7Error("configuration_not_consumable", "authorisation schema drifted")
    return True


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
    replicate.assert_inactive_text(text)
    for line in text.splitlines():
        if line.strip().startswith(("ld_library_path:", "interpreter:", "replicate_manifest_path:")):
            raise M7Error("configuration_not_consumable", "inactive configuration binds an LD_LIBRARY_PATH, interpreter or predecessor value")
    return True


def reject_inactive_before_execution(config):
    assert_inactive_configuration(config)
    raise M7Error("execution_not_authorised", "the checked-in M7 candidate-guardrail configuration is not executable")


def assert_active_entry(entry, run_root=None):
    """Schema for one independently consumable candidate entry."""
    run_root = common.RUN_ROOT if run_root is None else run_root
    entry = common.exact_keys(entry, ACTIVE_ENTRY_KEYS, "authorisation_shape_invalid")
    if common.contains_key(entry, "authorization_commit"):
        raise M7Error("authorisation_commit_invalid", "tracked authorisation must not store its own commit")
    seed = replicate.assert_seed(entry["candidate_seed"])
    epoch = entry["candidate_epoch"]
    if not common.is_candidate_epoch(epoch):
        raise M7Error("selection_invalid", "the candidate epoch is not 1 through 5; update 0 is never a candidate")
    if entry["activation_status"] != replicate.ACTIVE_ACTIVATION or entry["consumed"] is not False:
        raise M7Error("authorisation_inactive", "authorisation is not active and unconsumed")
    if entry["single_use"] is not True or entry["reuse_permitted"] is not False:
        raise M7Error("authorization_reuse", "authorisation is not single-use")
    identifier = entry["authorisation_id"]
    matched = AUTHORISATION_ID_PATTERN.fullmatch(identifier) if isinstance(identifier, str) else None
    if matched is None or int(matched.group(1)) != seed or int(matched.group(2)) != epoch:
        raise M7Error("authorisation_field_missing", "authorisation id is not an m7 candidate id for this seed and epoch")
    parent = entry["authorization_parent_commit"]
    executing = entry["executing_implementation_commit"]
    if not common.is_sha40(parent) or parent != executing:
        raise M7Error("authorisation_commit_invalid", "parent commit and executing implementation commit differ")
    if entry["phase"] != ACTIVE_PHASE or entry["scope"] != "single_use_m7_d1_candidate_guardrail_seed_%d_epoch_%d" % (seed, epoch):
        raise M7Error("authorisation_scope_invalid", "phase or scope is not this candidate")
    if list(entry["permitted_roles"]) != list(ACTIVE_ROLES):
        raise M7Error("authorisation_scope_invalid", "permitted roles drifted")
    if str(entry["physical_gpu_index"]) != entry["cuda_visible_devices"] or entry["logical_device"] != common.LOGICAL_CUDA_DEVICE:
        raise M7Error("identity_mismatch", "GPU binding is not a physical index with logical cuda:0")
    replicate._gpu_uuid(entry["gpu_uuid"])
    replicate._pci_bus(entry["pci_bus"])
    common.assert_ld_library_path_binding(entry["ld_library_path"])
    common.assert_interpreter_binding(entry["interpreter"])
    if not common.is_sha256(entry["implementation_config_sha256"]):
        raise M7Error("provenance_mismatch", "implementation configuration hash is missing")
    if not isinstance(entry["authorisation_timestamp"], str) or replicate.TIMESTAMP_PATTERN.fullmatch(entry["authorisation_timestamp"]) is None:
        raise M7Error("authorisation_field_missing", "authorisation timestamp is not an offset ISO timestamp")
    session = common.exact_keys(entry["session"], replicate.SESSION_KEYS, "authorisation_shape_invalid")
    if session["pattern"] != replicate.SESSION_PATTERN or session["consumption_event"] != replicate.CONSUMPTION_EVENT:
        raise M7Error("authorisation_scope_invalid", "session conditions drifted")
    if session["wall_clock_expiry"] is not None or session["resume_permitted"] is not False:
        raise M7Error("authorisation_scope_invalid", "session conditions drifted")
    name = common.assert_output_directory_shape(entry["output_directory"], run_root)
    if name != identifier or entry["evidence_directory"] != entry["output_directory"]:
        raise M7Error("authorisation_scope_invalid", "output directory is not the authorisation id")
    expected_name = replicate.checkpoint_child_name(seed, epoch, executing)
    directory = entry["checkpoint_directory"]
    if (
        not isinstance(directory, str)
        or os.path.basename(directory) != expected_name
        or os.path.dirname(os.path.dirname(directory)) != run_root.rstrip("/")
        or common.path_is_ref_or_eval(directory)
        or common.M6_CHECKPOINT_NAME_PATTERN.search(directory) is not None
        or common.M6_EVIDENCE_NAME_PATTERN.search(directory) is not None
    ):
        raise M7Error("authorisation_scope_invalid", "checkpoint directory is not this seed and epoch checkpoint")
    members = common.exact_keys(entry["checkpoint_member_sha256"], common.CHECKPOINT_MEMBERS, "authorisation_shape_invalid")
    if any(not common.is_sha256(value) for value in members.values()):
        raise M7Error("authorisation_field_missing", "a checkpoint member hash is missing")
    common.assert_not_m6_weight(members[common.WEIGHT_MEMBER])
    update = entry["candidate_update"]
    if isinstance(update, bool) or not isinstance(update, int) or update == 0 or update != replicate.epoch_update_range(epoch)[1]:
        raise M7Error("selection_invalid", "the candidate update is not the update at the end of the candidate epoch; update 0 is never a candidate")
    if entry["checkpoint_relative_name"] != expected_name or entry["checkpoint_relative_name"] != os.path.basename(directory):
        raise M7Error("authorisation_scope_invalid", "the checkpoint relative name is not this seed, epoch and update")
    if entry["checkpoint_weight_sha256"] != members[common.WEIGHT_MEMBER]:
        raise M7Error("authorisation_scope_invalid", "the bound weight hash is not the checkpoint's weight member hash")
    if entry["replicate_manifest_path"] != os.path.join(os.path.dirname(directory), replicate.SUCCESS_MANIFEST_NAME):
        raise M7Error("sibling_evidence_access", "the replicate manifest is not the one beside this checkpoint")
    manifest_bytes = entry["replicate_manifest_bytes"]
    if isinstance(manifest_bytes, bool) or not isinstance(manifest_bytes, int) or manifest_bytes <= 0:
        raise M7Error("authorisation_field_missing", "the replicate manifest byte count is missing")
    if entry["expected_schedule_sha256"] != common.m6_contract().PAIRED_SCHEDULE_SHA256:
        raise M7Error("identity_mismatch", "diagnostic schedule hash drifted")
    for key in ("replicate_manifest_sha256", "validation_ranking_sha256"):
        if not common.is_sha256(entry[key]):
            raise M7Error("authorisation_field_missing", key + " is missing")
    position = entry["ranking_position"]
    preceding = entry["preceding_candidates"]
    if isinstance(position, bool) or position not in (1, 2, 3, 4, 5) or not isinstance(preceding, list) or len(preceding) != position - 1:
        raise M7Error("selection_invalid", "the entry does not bind every earlier ranked candidate")
    for item in preceding:
        common.exact_keys(item, ("epoch", "manifest_sha256", "outcome"), "selection_invalid")
        if item["outcome"] != "failed" or item["epoch"] not in common.CANDIDATE_EPOCHS or item["epoch"] == epoch or not common.is_sha256(item["manifest_sha256"]):
            raise M7Error("selection_invalid", "an earlier ranked candidate is not a failed, evaluated manifest")
    if len({item["epoch"] for item in preceding}) != len(preceding):
        raise M7Error("selection_invalid", "an earlier ranked candidate is duplicated")
    hashes = common.exact_keys(entry["implementation_file_hashes"], IMPLEMENTATION_FILE_PATHS, "provenance_mismatch")
    if any(not common.is_sha256(value) for value in hashes.values()):
        raise M7Error("provenance_mismatch", "an implementation file hash is missing")
    return entry


def assert_active_configuration(config, run_root=None):
    run_root = common.RUN_ROOT if run_root is None else run_root
    config = common.exact_keys(config, CONFIGURATION_ROOT_KEYS, "authorisation_shape_invalid")
    if config.get("document_status") != ACTIVE_DOCUMENT_STATUS or config.get("consumable_by_executable_workflow") is not True:
        raise M7Error("authorisation_inactive", "active document flags drifted")
    if common.contains_key(config, "authorization_commit"):
        raise M7Error("authorisation_commit_invalid", "tracked configuration must not store authorization_commit")
    execution = common.exact_keys(config.get("execution"), replicate.EXECUTION_KEYS, "authorisation_shape_invalid")
    if any(execution[key] is not True for key in replicate.EXECUTION_KEYS):
        raise M7Error("authorisation_inactive", "execution flags are not active")
    for name, expected in expected_static_sections().items():
        if config.get(name) != expected:
            raise M7Error("authorisation_scope_invalid", "static section drifted: " + name)
    entries = config.get("authorisation_entries")
    if not isinstance(entries, list) or not entries:
        raise M7Error("authorisation_shape_invalid", "an active document carries at least one entry")
    seen = set()
    for entry in entries:
        assert_active_entry(entry, run_root)
        key = (entry["candidate_seed"], entry["candidate_epoch"])
        if key in seen:
            raise M7Error("authorization_reuse", "a candidate has more than one entry")
        seen.add(key)
    return {(entry["candidate_seed"], entry["candidate_epoch"]): entry for entry in entries}


def build_candidate_argv(invocation, checkpoint_dir, entry, reader=None):
    """The accepted B1 invocation contract with exactly one substitution: ``--dm_file``.

    The diagnostic module's loader verifies the pinned B1 runner by hash. Only
    the one authorised M7 checkpoint directory may be named, never an M6 one.
    """
    diag = diagnostic()
    if checkpoint_dir != entry["checkpoint_directory"]:
        raise M7Error("authorisation_scope_invalid", "generation may load only the authorised candidate checkpoint")
    if common.M6_CHECKPOINT_NAME_PATTERN.search(checkpoint_dir) is not None or common.M6_EVIDENCE_NAME_PATTERN.search(checkpoint_dir) is not None:
        raise M7Error("m6_checkpoint_forbidden", "an M6 checkpoint cannot be a candidate")
    try:
        b1 = diag.b1_runner(reader)
        argv = b1.build_generation_argv(invocation)
    except diag.DiagnosticError as exc:
        raise M7Error(exc.code, exc.detail)
    if argv.count("--dm_file") != 1:
        raise M7Error("authorisation_scope_invalid", "generation argv must name one diffusion model")
    position = argv.index("--dm_file") + 1
    if argv[position] != b1.DIFFUSION_RELATIVE:
        raise M7Error("authorisation_scope_invalid", "B1 invocation contract drifted")
    argv[position] = checkpoint_dir
    return argv


# ------------------------------------------------------------------ candidate manifest

MANIFEST_KEYS = (
    "accounting",
    "authorisation",
    "candidate",
    "checkpoint",
    "closure",
    "completion_state",
    "config_version",
    "environment",
    "experiment_id",
    "gpu",
    "guardrails",
    "input_roles",
    "ledgers",
    "manifest_schema_version",
    "preceding_candidates",
    "provenance",
    "ref_eval_access",
    "replicate_binding",
    "report_only",
    "run_id",
    "schema_version",
)
PROVENANCE_KEYS = (
    "approved_cleaner_sha256",
    "frozen_encdec_assets",
    "generation_inputs",
    "implementation_file_hashes",
    "metrics_configuration_sha256",
    "metrics_module_sha256",
    "rnagenesis",
)
CLOSURE = {
    "m7_complete": False,
    "no_selection_claim": True,
    "ref_opened": False,
    "eval_opened": False,
    "validation_csv_opened": False,
    "scope": "one_seed_epoch_candidate_diagnostic_only",
    "human_gate_required": True,
}
ALLOWED_INPUT_ROLES = ("ACCEPTED_SCHEDULE", "FROZEN_ENCDEC", "SEED_EPOCH_CHECKPOINT", "TRAIN_TEXT_DIAGNOSTIC_ONLY")
ACCOUNTING_KEYS = ("cleaner_sha256", "invocation_count", "raw_attempts", "schedule_sha256", "valid_outputs")


def provenance_block(implementation_file_hashes):
    """The pinned tool and generation-input identities the diagnostic ran against.

    Every value is measured (and compared with its pin) before this block is
    written, so the block is the pinned form plus the authorised file hashes.
    """
    d = diagnostic()
    return {
        "approved_cleaner_sha256": CLEANER_SHA256,
        "frozen_encdec_assets": d.pinned_encdec_assets(),
        "generation_inputs": d.pinned_generation_inputs(),
        "implementation_file_hashes": dict(implementation_file_hashes),
        "metrics_configuration_sha256": d.METRICS_CONFIG_SHA256,
        "metrics_module_sha256": d.METRICS_SHA256,
        "rnagenesis": {"branch": common.RNAGENESIS_BRANCH, "commit": common.RNAGENESIS_COMMIT},
    }


def build_candidate_manifest(entry, replicate_binding, checkpoint, guardrails, report_only, accounting, gpu, environment, ledgers, provenance):
    manifest = {
        "accounting": dict(accounting),
        "authorisation": {
            "authorisation_id": entry["authorisation_id"],
            "authorization_commit": entry["authorization_commit"],
            "authorization_parent_commit": entry["authorization_parent_commit"],
            "candidate_epoch": entry["candidate_epoch"],
            "candidate_seed": entry["candidate_seed"],
            "consumption_state": "consumed_successfully",
            "executing_implementation_commit": entry["executing_implementation_commit"],
            "reuse_permitted": False,
            "single_use": True,
        },
        "candidate": {
            "epoch": entry["candidate_epoch"],
            "ranking_position": entry["ranking_position"],
            "seed": entry["candidate_seed"],
            "update": replicate.epoch_update_range(entry["candidate_epoch"])[1],
        },
        "checkpoint": dict(checkpoint),
        "closure": dict(CLOSURE),
        "completion_state": "candidate_evaluated",
        "config_version": SCHEMA_VERSION,
        "environment": json.loads(json.dumps(environment)),
        "experiment_id": EXPERIMENT_ID,
        "gpu": dict(gpu),
        "guardrails": dict(guardrails),
        "input_roles": list(ALLOWED_INPUT_ROLES),
        "ledgers": dict(ledgers),
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "preceding_candidates": [dict(item) for item in entry["preceding_candidates"]],
        "provenance": json.loads(json.dumps(provenance)),
        "ref_eval_access": {"eval_opened": False, "ref_opened": False},
        "replicate_binding": dict(replicate_binding),
        "report_only": dict(report_only),
        "run_id": entry["authorisation_id"],
        "schema_version": SCHEMA_VERSION,
    }
    validate_candidate_manifest(manifest)
    return manifest


def validate_candidate_manifest(manifest):
    """One seed, one epoch, one checkpoint. No cross-seed or final-selection claim."""
    manifest = common.exact_keys(manifest, MANIFEST_KEYS, "guardrail_manifest_invalid")
    common.reject_sequence_text(manifest)
    if manifest["manifest_schema_version"] != MANIFEST_SCHEMA_VERSION or manifest["schema_version"] != SCHEMA_VERSION or manifest["config_version"] != SCHEMA_VERSION:
        raise M7Error("guardrail_manifest_invalid", "manifest schema drifted")
    if manifest["experiment_id"] != EXPERIMENT_ID or manifest["completion_state"] != "candidate_evaluated":
        raise M7Error("guardrail_manifest_invalid", "manifest identity or completion drifted")
    if manifest["closure"] != CLOSURE or manifest["ref_eval_access"] != {"eval_opened": False, "ref_opened": False}:
        raise M7Error("ref_or_eval_access", "closure or REF/EVAL access drifted")
    if list(manifest["input_roles"]) != list(ALLOWED_INPUT_ROLES):
        raise M7Error("ref_or_eval_access", "input roles drifted")
    authorisation = common.exact_keys(
        manifest["authorisation"],
        (
            "authorisation_id",
            "authorization_commit",
            "authorization_parent_commit",
            "candidate_epoch",
            "candidate_seed",
            "consumption_state",
            "executing_implementation_commit",
            "reuse_permitted",
            "single_use",
        ),
        "guardrail_manifest_invalid",
    )
    if authorisation["consumption_state"] != "consumed_successfully" or authorisation["reuse_permitted"] is not False or authorisation["single_use"] is not True:
        raise M7Error("authorization_reuse", "authorisation was not consumed once successfully")
    seed = replicate.assert_seed(authorisation["candidate_seed"])
    epoch = authorisation["candidate_epoch"]
    if not common.is_candidate_epoch(epoch):
        raise M7Error("selection_invalid", "the candidate epoch is not 1 through 5")
    if manifest["run_id"] != authorisation["authorisation_id"]:
        raise M7Error("guardrail_manifest_invalid", "run id is not the consumed authorisation")
    candidate = common.exact_keys(manifest["candidate"], ("epoch", "ranking_position", "seed", "update"), "guardrail_manifest_invalid")
    if candidate["seed"] != seed or candidate["epoch"] != epoch or candidate["update"] != replicate.epoch_update_range(epoch)[1]:
        raise M7Error("guardrail_manifest_invalid", "candidate identity does not match the authorisation")
    if candidate["ranking_position"] not in (1, 2, 3, 4, 5) or isinstance(candidate["ranking_position"], bool):
        raise M7Error("guardrail_manifest_invalid", "ranking position is invalid")
    checkpoint = common.exact_keys(
        manifest["checkpoint"],
        ("directory_name", "members_sha256", "tree_unchanged_across_generation", "weight_sha256", "weights_sha256_after_generation", "weights_sha256_before_generation"),
        "guardrail_manifest_invalid",
    )
    members = common.exact_keys(checkpoint["members_sha256"], common.CHECKPOINT_MEMBERS, "guardrail_manifest_invalid")
    weight = members[common.WEIGHT_MEMBER]
    if not common.is_sha256(weight) or any(not common.is_sha256(value) for value in members.values()):
        raise M7Error("guardrail_manifest_invalid", "a checkpoint member hash is missing")
    common.assert_not_m6_weight(weight)
    if (
        checkpoint["weight_sha256"] != weight
        or checkpoint["weights_sha256_before_generation"] != weight
        or checkpoint["weights_sha256_after_generation"] != weight
        or checkpoint["tree_unchanged_across_generation"] is not True
    ):
        raise M7Error("checkpoint_save_reload_incompatibility", "the checkpoint changed or does not match the bound weight")
    if checkpoint["directory_name"] != replicate.checkpoint_child_name(seed, epoch, authorisation["executing_implementation_commit"]):
        raise M7Error("guardrail_manifest_invalid", "checkpoint directory name drifted")
    binding = common.exact_keys(
        manifest["replicate_binding"],
        ("replicate_manifest_sha256", "seed", "epoch", "validation_mse", "validation_ranking_sha256", "weight_sha256"),
        "guardrail_manifest_invalid",
    )
    if binding["seed"] != seed or binding["epoch"] != epoch or binding["weight_sha256"] != weight:
        raise M7Error("guardrail_manifest_invalid", "replicate binding does not match the candidate")
    for key in ("replicate_manifest_sha256", "validation_ranking_sha256"):
        if not common.is_sha256(binding[key]):
            raise M7Error("guardrail_manifest_invalid", key + " is missing")
    common.finite_decimal_string(binding["validation_mse"], "non_finite_validation")
    accounting = common.exact_keys(manifest["accounting"], ACCOUNTING_KEYS, "guardrail_manifest_invalid")
    if (
        accounting["raw_attempts"] != ATTEMPT_COUNT
        or accounting["invocation_count"] != INVOCATION_COUNT
        or accounting["schedule_sha256"] != common.m6_contract().PAIRED_SCHEDULE_SHA256
        or accounting["cleaner_sha256"] != CLEANER_SHA256
        or isinstance(accounting["valid_outputs"], bool)
        or not isinstance(accounting["valid_outputs"], int)
        or not 0 <= accounting["valid_outputs"] <= ATTEMPT_COUNT
    ):
        raise M7Error("guardrail_manifest_invalid", "diagnostic accounting is not the accepted 1,000-attempt schedule")
    guardrails = common.exact_keys(manifest["guardrails"], ("decisions", "exact_hit_rate_is_a_threshold", "passed", "values"), "guardrail_manifest_invalid")
    recomputed = evaluate_guardrail_values(guardrails["values"])
    if guardrails["decisions"] != recomputed["decisions"] or guardrails["passed"] is not recomputed["passed"] or guardrails["exact_hit_rate_is_a_threshold"] is not False:
        raise M7Error("guardrail_manifest_invalid", "recorded guardrail decisions do not match the recorded values")
    report = common.exact_keys(manifest["report_only"], REPORT_ONLY_KEYS + ("eligibility_effect", "thresholds_defined"), "guardrail_manifest_invalid")
    if report["eligibility_effect"] != "none" or report["thresholds_defined"] is not False:
        raise M7Error("guardrail_manifest_invalid", "report-only items acquired a threshold")
    diagnostics = common.exact_keys(report["diagnostics"], DIAGNOSTICS_KEYS, "guardrail_manifest_invalid")
    common.exact_keys(diagnostics["headline"], HEADLINE_KEYS, "guardrail_manifest_invalid")
    if (
        diagnostics["file"] != REPORT_ONLY_DIAGNOSTICS_NAME
        or diagnostics["thresholds_defined"] is not False
        or diagnostics["edit_similarity_is_sequence_identity"] is not False
        or diagnostics["effect_on_ranking_or_thresholds"] != "none"
        or diagnostics["edit_similarity_definition"] != diagnostic().EDIT_SIMILARITY_DEFINITION
    ):
        raise M7Error("guardrail_manifest_invalid", "report-only diagnostics acquired a threshold or were described as sequence identity")
    preceding = manifest["preceding_candidates"]
    if not isinstance(preceding, list) or len(preceding) != candidate["ranking_position"] - 1:
        raise M7Error("selection_invalid", "the preceding candidates do not match the ranking position")
    for item in preceding:
        common.exact_keys(item, ("epoch", "manifest_sha256", "outcome"), "selection_invalid")
        if item["outcome"] != "failed" or not common.is_sha256(item["manifest_sha256"]):
            raise M7Error("selection_invalid", "a preceding candidate is not a failed, evaluated manifest")
    gpu = common.exact_keys(manifest["gpu"], ("cuda_visible_devices", "logical_device", "pci_bus", "physical_index", "uuid"), "identity_mismatch")
    if gpu["logical_device"] != common.LOGICAL_CUDA_DEVICE:
        raise M7Error("identity_mismatch", "logical device is not cuda:0")
    environment = common.exact_keys(manifest["environment"], ("interpreter", "ld_library_path"), "environment_rejected")
    common.assert_ld_library_path_record(environment["ld_library_path"])
    common.assert_interpreter_binding(environment["interpreter"])
    ledgers = common.exact_keys(manifest["ledgers"], tuple(LEDGER_FILES), "guardrail_manifest_invalid")
    if any(not common.is_sha256(value) for value in ledgers.values()):
        raise M7Error("guardrail_manifest_invalid", "a retained ledger hash is missing")
    if diagnostics["sha256"] != ledgers["report_only_diagnostics_sha256"]:
        raise M7Error("guardrail_manifest_invalid", "the report-only diagnostics hash is not the retained ledger hash")
    provenance = common.exact_keys(manifest["provenance"], PROVENANCE_KEYS, "provenance_mismatch")
    implementation = common.exact_keys(provenance["implementation_file_hashes"], IMPLEMENTATION_FILE_PATHS, "provenance_mismatch")
    if any(not common.is_sha256(value) for value in implementation.values()):
        raise M7Error("provenance_mismatch", "an implementation file hash is missing")
    expected = provenance_block(implementation)
    if provenance != expected:
        raise M7Error("provenance_mismatch", "generation inputs, tools or the RNAGenesis pin differ from the pinned identities")
    return True


# ------------------------------------------------------------------ candidate lifecycle


def verify_candidate_checkpoint(entry, lstat=None):
    """Exact strict tree plus streamed member hashes. The path is checked before any open."""
    directory = entry["checkpoint_directory"]
    if common.path_is_ref_or_eval(directory) or common.M6_CHECKPOINT_NAME_PATTERN.search(directory) is not None:
        raise M7Error("m6_checkpoint_forbidden", "the checkpoint path is refused before open")
    tree = common.observe_checkpoint_tree_strict(directory, None, lstat)
    members = {}
    for name in common.CHECKPOINT_MEMBERS:
        members[name] = common.stream_sha256(os.path.join(directory, name), require_single_link=True)
    if members != dict(entry["checkpoint_member_sha256"]):
        raise M7Error("checkpoint_save_reload_incompatibility", "checkpoint member hashes do not match the authorisation")
    common.assert_not_m6_weight(members[common.WEIGHT_MEMBER])
    return {"members_sha256": members, "tree": tree}


def run_candidate(entry, generate_and_measure=None, run_root=None, progress=None, writer=None, deps=None):
    """Consume one candidate entry and evaluate it.

    ``generate_and_measure(entry, checkpoint_dir, output_directory)`` returns the
    five guardrail values, the accounting, the report-only block, the replicate
    binding, the environment record, the ledger hashes and the provenance block.
    When it is ``None`` the real ``production_generate_and_measure`` runs, with
    ``deps`` (or the real defaults). A test may inject its own callable. Every
    ``BaseException`` after consumption becomes a failure record that names the
    seed, epoch, candidate, stage and (during generation) invocation index.
    """
    run_root = common.RUN_ROOT if run_root is None else run_root
    directory = entry["output_directory"]
    progress = common.new_progress(entry["candidate_seed"], "candidate") if progress is None else progress
    if generate_and_measure is None:
        def generate_and_measure(candidate_entry, checkpoint_dir, output_directory):
            return production_generate_and_measure(candidate_entry, checkpoint_dir, output_directory, deps=deps, progress=progress, run_root=run_root)
    progress["candidate"] = {"epoch": entry["candidate_epoch"], "ranking_position": entry["ranking_position"], "seed": entry["candidate_seed"]}
    progress["epoch"] = entry["candidate_epoch"]
    payload = {
        "authorisation_id": entry["authorisation_id"],
        "authorization_commit": entry["authorization_commit"],
        "authorization_parent_commit": entry["authorization_parent_commit"],
        "candidate_epoch": entry["candidate_epoch"],
        "candidate_seed": entry["candidate_seed"],
        "consumption_state": "consumed_output_created",
        "executing_implementation_commit": entry["executing_implementation_commit"],
        "output_directory": directory,
        "reuse_permitted": False,
        "schema_version": CONSUMPTION_SCHEMA_VERSION,
    }
    context = {
        "authorisation_id": entry["authorisation_id"],
        "authorization_commit": entry["authorization_commit"],
        "authorization_parent_commit": entry["authorization_parent_commit"],
        "executing_implementation_commit": entry["executing_implementation_commit"],
        "output_directory": directory,
    }
    progress["stage"] = "consumption"
    try:
        common.consume_output_directory(directory, payload, run_root)
    except BaseException as exc:
        # An existing directory is never written into. A directory this call
        # created, whose consumption record failed, gets a failure record.
        if getattr(exc, "directory_created", False) is not True:
            raise
        error = common.record_consumed_failure(directory, exc, context, progress, SUCCESS_MANIFEST_NAME)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise error from None
    try:
        progress["stage"] = "checkpoint_verification_before"
        before = verify_candidate_checkpoint(entry)
        progress["stage"] = "generation"
        measured = generate_and_measure(entry, entry["checkpoint_directory"], directory)
        progress["stage"] = "checkpoint_verification_after"
        after = verify_candidate_checkpoint(entry)
        if after != before:
            raise M7Error("checkpoint_save_reload_incompatibility", "the checkpoint changed during generation")
        progress["stage"] = "manifest"
        weight = before["members_sha256"][common.WEIGHT_MEMBER]
        guardrails = evaluate_guardrail_values(measured["values"])
        manifest = build_candidate_manifest(
            entry,
            measured["replicate_binding"],
            {
                "directory_name": os.path.basename(entry["checkpoint_directory"]),
                "members_sha256": before["members_sha256"],
                "tree_unchanged_across_generation": True,
                "weight_sha256": weight,
                "weights_sha256_after_generation": after["members_sha256"][common.WEIGHT_MEMBER],
                "weights_sha256_before_generation": weight,
            },
            guardrails,
            measured["report_only"],
            measured["accounting"],
            measured["gpu"],
            measured["environment"],
            measured["ledgers"],
            measured["provenance"],
        )
        (writer or common.write_atomic_json)(directory, SUCCESS_MANIFEST_NAME, manifest)
        return manifest
    except BaseException as exc:
        error = common.record_consumed_failure(directory, exc, context, progress, SUCCESS_MANIFEST_NAME)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise error from None


# ------------------------------------------------------------------ production generation


def diagnostic():
    """The accepted M6 diagnostic module, loaded by its tracked path and never modified."""
    return _load_sibling("m6_diagnostic_generation_for_m7", "scripts/modelling/m6_diagnostic_generation.py")


def translated(operation):
    """Run an upstream operation and re-raise any coded upstream failure as an M7 error.

    The accepted B1 runner, M6 diagnostic, M4 metrics and M6 contract each carry
    their own error class with ``code`` and ``detail``. The text is already
    message-safe, so the code and detail are kept and nothing else is.
    """
    try:
        return operation()
    except M7Error:
        raise
    except Exception as exc:
        code = getattr(exc, "code", None)
        detail = getattr(exc, "detail", None)
        if isinstance(code, str) and isinstance(detail, str):
            raise M7Error(code, detail) from None
        raise


def _read_file_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _nofollow_sha256_file(path):
    """Streamed digest through ``O_NOFOLLOW`` with the size, mtime and inode compared across the read."""
    return common.stream_sha256(path)


def _default_fold(sequence):
    return diagnostic()._default_fold(sequence)


def _default_nearest(sequence, train_cores):
    return diagnostic().nearest_train(sequence, train_cores)


def _default_observe_interpreter(path):
    return common.observe_interpreter(path)


def _default_git(repo, args):
    """``git`` by its absolute, validated path in a fixed environment (not the accepted B1 ``git`` by name)."""
    return common.run_git(repo, args)


def _default_git_blob(spec):
    return common.run_git_bytes(MRES_ROOT, ["show", spec])


def _default_gpu_preflight(parent, physical_gpu, run=None, lstat=None):
    """The accepted B1 preflight with ``nvidia-smi`` replaced by its absolute, validated path.

    The accepted B1 parent-CUDA check, query arguments and probe parser are
    reused unchanged; only the executable and the environment it runs in differ.
    """
    b1 = diagnostic().b1_runner()
    translated(lambda: b1.assert_parent_cuda(parent, physical_gpu))
    argv = common.nvidia_smi_query_argv(physical_gpu)
    if argv[1:] != translated(lambda: b1.physical_gpu_query_argv(physical_gpu))[1:]:
        raise M7Error("gpu_probe_invalid", "the accepted B1 GPU query drifted from the fixed query")
    completed = common.run_trusted_tool(argv, None, run, lstat)
    if getattr(completed, "returncode", 1) != 0:
        raise M7Error("unauthorized_gpu", "GPU query failed")
    try:
        text = bytes(completed.stdout).decode("utf-8")
    except UnicodeDecodeError:
        raise M7Error("gpu_probe_invalid", "the GPU probe output is not UTF-8")
    return translated(lambda: b1.parse_gpu_probe(text, physical_gpu))


def _default_subprocess_run(argv, cwd, env, shell=False):
    return translated(lambda: diagnostic().b1_runner().default_subprocess_run(argv, cwd, env, shell))


class CandidateDependencies(object):
    """Every outside effect of the candidate stage, injectable for CPU/mock tests.

    The defaults are the real implementations, so production code never has to
    inject anything. ``pins`` defaults to the accepted M6 pins (schedule and
    TRAIN identities); a test supplies synthetic pins and never reads them.
    """

    def __init__(
        self,
        read_bytes=None,
        lstat=None,
        listdir=None,
        realpath=None,
        sha256_file_fn=None,
        environ=None,
        git=None,
        git_blob=None,
        gpu_preflight=None,
        mkdir=None,
        subprocess_run=None,
        write_bytes=None,
        pins=None,
        fold=None,
        nearest=None,
        observe_interpreter=None,
    ):
        self.read_bytes = read_bytes or _read_file_bytes
        self.lstat = lstat or os.lstat
        self.listdir = listdir or os.listdir
        self.realpath = realpath or os.path.realpath
        self.sha256_file = sha256_file_fn or _nofollow_sha256_file
        self.environ = os.environ if environ is None else environ
        self.git = git or _default_git
        self.git_blob = git_blob or _default_git_blob
        self.gpu_preflight = gpu_preflight or _default_gpu_preflight
        self.mkdir = mkdir or os.mkdir
        self.subprocess_run = subprocess_run or _default_subprocess_run
        self.write_bytes = write_bytes or common.write_atomic_bytes
        self.fold = fold or _default_fold
        self.nearest = nearest or _default_nearest
        self.observe_interpreter = observe_interpreter or _default_observe_interpreter
        self._pins = pins

    @property
    def pins(self):
        return diagnostic().production_pins() if self._pins is None else self._pins


# ------------------------------------------------------------------ input roles


def assert_input_permitted(path, role, entry=None, run_root=None, realpath=None, pins=None):
    """Refuse a forbidden input on its path text, before any filesystem access.

    REF and EVAL are refused by role and by path (case-insensitively, in the
    resolved form too). VALIDATION is not requested by this diagnostic. M6
    checkpoints and evidence, and any sibling replicate, are refused. Each
    permitted role maps to one location. TRAIN is permitted only for the
    exact-copy diagnostic and is never reachable from a candidate checkpoint.
    """
    run_root = common.RUN_ROOT if run_root is None else run_root
    if role in ("REF", "EVAL"):
        raise M7Error("ref_or_eval_access", "REF and EVAL are refused before open")
    texts = [common.normalise_path_text(path)]
    if realpath is not None:
        resolved = common.normalise_path_text(realpath(str(path)))
        if resolved not in texts:
            texts.append(resolved)
    for text in texts:
        if common.path_is_ref_or_eval(text):
            raise M7Error("ref_or_eval_access", "REF and EVAL are refused before open")
        if common.path_is_obsolete_repository_local(text):
            raise M7Error("unexpected_biological_path_or_role", "obsolete repository-local data is refused before open")
    if role in DENIED_ROLES:
        raise M7Error("unexpected_biological_path_or_role", "VALIDATION is not requested by the candidate diagnostic")
    if role not in ACTIVE_ROLES:
        raise M7Error("unexpected_biological_path_or_role", "the role is not a candidate-diagnostic input")
    d = diagnostic()
    for text in texts:
        if common.M6_EVIDENCE_NAME_PATTERN.search(text) is not None or common.M6_CHECKPOINT_NAME_PATTERN.search(text) is not None:
            raise M7Error("m6_checkpoint_forbidden", "an M6 checkpoint or evidence path is not a candidate input")
        normal = os.path.normpath(text)
        if role == "SEED_EPOCH_CHECKPOINT":
            if entry is None:
                raise M7Error("authorisation_scope_invalid", "a checkpoint role needs its authorisation entry")
            bound = entry["checkpoint_directory"]
            replicate_directory = os.path.dirname(bound)
            if common.path_is_sibling_evidence(normal, replicate_directory, (), run_root):
                raise M7Error("sibling_evidence_access", "a sibling replicate or evidence directory is refused before open")
            if not (common._within(normal, bound) or normal == os.path.join(replicate_directory, replicate.SUCCESS_MANIFEST_NAME)):
                raise M7Error("authorisation_scope_invalid", "the path is not the authorised checkpoint or its sealed replicate manifest")
        elif role == "ACCEPTED_SCHEDULE":
            if not common._within(normal, d.SCHEDULE_DIRECTORY):
                raise M7Error("unexpected_biological_path_or_role", "the path is not the accepted schedule")
        elif role == "TRAIN_TEXT_DIAGNOSTIC_ONLY":
            pinned = (diagnostic().production_pins() if pins is None else pins)["train"]["path"]
            if normal != pinned:
                raise M7Error("unexpected_biological_path_or_role", "the path is not the pinned TRAIN text")
        elif role == "FROZEN_ENCDEC":
            if not common._within(normal, common.RNAGENESIS_ROOT) or common._within(normal, os.path.join(common.RNAGENESIS_ROOT, ".cache")):
                raise M7Error("unexpected_biological_path_or_role", "the path is not a pinned RNAGenesis asset")
    return os.path.normpath(texts[0])


# ------------------------------------------------------------------ replicate binding


def ranking_sha256(ranking):
    return common.sha256_bytes(common.canonical_json(ranking))


def _evidence_mismatch(operation):
    """Predecessor-evidence inspection failures are all evidence mismatches."""
    try:
        return operation()
    except M7Error as exc:
        if exc.code in ("asset_inspection_unsafe", "checkpoint_ancestry_unsafe"):
            raise M7Error("authorisation_evidence_mismatch", "the sealed replicate manifest failed inspection: " + exc.detail) from None
        raise


def assert_predecessor_identity(parsed, entry):
    """Independent checks of the reopened replicate manifest, beyond the replicate validator.

    Nothing copied into the candidate entry is trusted unless it agrees with
    this manifest: the terminal state, seed, B1 initialisation, validation
    artifacts, and the one checkpoint (epoch, update, name, member hashes and
    weight hash) the entry names.
    """
    m6 = common.m6_contract()
    if (
        parsed["completion_state"] != "replicate_completed"
        or parsed["resume_supported"] is not False
        or parsed["warnings"] != []
        or parsed["closure"] != replicate.CLOSURE
        or parsed["authorisation"]["consumption_state"] != "consumed_successfully"
    ):
        raise M7Error("incomplete_evidence_or_manifest", "the predecessor replicate did not reach a successful terminal state")
    seed = entry["candidate_seed"]
    epoch = entry["candidate_epoch"]
    update = entry["candidate_update"]
    if parsed["seed"] != seed or parsed["authorisation"]["seed"] != seed:
        raise M7Error("sibling_evidence_access", "the sealed replicate manifest belongs to another seed")
    identity = parsed["b1_identity"]
    isolation = parsed["initialisation_isolation"]
    if (
        identity["weight_sha256"] != m6.B1_WEIGHT_SHA256
        or identity["unet_config_sha256"] != m6.B1_UNET_CONFIG_SHA256
        or isolation["initialisation_relative_path"] != m6.B1_RELATIVE_PATH
        or isolation["b1_loaded_fresh_for_this_seed"] is not True
        or isolation["m6_checkpoint_loaded"] is not False
        or isolation["saved_weights_equal_a_forbidden_m6_hash"] is not False
    ):
        raise M7Error("identity_mismatch", "the predecessor was not initialised from the accepted B1 checkpoint")
    artifacts = parsed["validation_artifacts"]
    pinned = {
        "draw_manifest_sha256": m6.VALIDATION_DRAW_MANIFEST_SHA256,
        "hash_report_sha256": m6.VALIDATION_HASH_REPORT_SHA256,
        "noise_sha256": m6.VALIDATION_NOISE_SHA256,
        "order_artifact_sha256": m6.VALIDATION_ORDER_ARTIFACT_SHA256,
        "sequence_order_sha256": m6.VALIDATION_SEQUENCE_ORDER_SHA256,
        "timestep_sha256": m6.VALIDATION_TIMESTEPS_SHA256,
        "validation_csv_sha256": m6.VALIDATION_CSV_SHA256,
    }
    if any(artifacts.get(key) != value for key, value in pinned.items()):
        raise M7Error("identity_mismatch", "the predecessor's validation artifacts are not the accepted ones")
    checkpoints = parsed["checkpoints"]
    if [item["epoch"] for item in checkpoints] != list(replicate.CANDIDATE_EPOCHS) or [item["update"] for item in checkpoints] != list(replicate.CANDIDATE_UPDATES):
        raise M7Error("authorisation_scope_invalid", "the predecessor does not list the five epoch checkpoints")
    if update == 0 or update not in replicate.CANDIDATE_UPDATES or update != replicate.epoch_update_range(epoch)[1]:
        raise M7Error("selection_invalid", "the candidate update is not an epoch-end update of the predecessor")
    listed = [item for item in checkpoints if item["epoch"] == epoch]
    if len(listed) != 1 or listed[0]["directory_name"] != entry["checkpoint_relative_name"] or listed[0]["update"] != update:
        raise M7Error("authorisation_scope_invalid", "the checkpoint is not listed in the sealed replicate manifest at this epoch and update")
    item = listed[0]
    if dict(item["saved_hashes"]) != dict(entry["checkpoint_member_sha256"]) or item["weight_sha256"] != entry["checkpoint_weight_sha256"]:
        raise M7Error("identity_mismatch", "the checkpoint identity differs from the sealed replicate manifest")
    common.assert_not_m6_weight(item["weight_sha256"])
    return item


def verify_replicate_binding(entry, deps, run_root=None):
    """Reopen and independently validate the successful replicate evidence of one candidate.

    The exact bound manifest is opened through a symlink-safe, single-link
    inspection (ancestry, ``lstat``, regular file, size and signature rechecked
    after the read). It must have the bound byte count and SHA-256, be canonical
    JSON with the exact replicate schema, pass the replicate manifest validator,
    reach a successful terminal state, and agree with every identity the entry
    carries. The entry's ranking position and failed earlier candidates must be
    the prefix of the sealed validation ranking. The return value is the replicate
    binding of the candidate manifest. No TRAIN, model asset or weight is opened.
    """
    run_root = common.RUN_ROOT if run_root is None else run_root
    directory = entry["checkpoint_directory"]
    replicate_directory = os.path.dirname(directory)
    path = os.path.join(replicate_directory, replicate.SUCCESS_MANIFEST_NAME)
    if entry["replicate_manifest_path"] != path:
        raise M7Error("sibling_evidence_access", "the bound replicate manifest is not the one beside the authorised checkpoint")
    assert_input_permitted(directory, "SEED_EPOCH_CHECKPOINT", entry, run_root, deps.realpath)
    assert_input_permitted(path, "SEED_EPOCH_CHECKPOINT", entry, run_root, deps.realpath)
    seed = entry["candidate_seed"]
    epoch = entry["candidate_epoch"]
    parent_name = os.path.basename(replicate_directory)
    matched = replicate.AUTHORISATION_ID_PATTERN.fullmatch(parent_name)
    if matched is None or int(matched.group(1)) != seed:
        raise M7Error("sibling_evidence_access", "the checkpoint is not in a replicate directory of this seed")
    blob, _signature = _evidence_mismatch(
        lambda: common.read_regular_file(path, deps.lstat, deps.read_bytes, True, entry["replicate_manifest_bytes"], entry["replicate_manifest_sha256"])
    )
    try:
        parsed = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise M7Error("authorisation_evidence_mismatch", "the sealed replicate manifest is not JSON")
    if not isinstance(parsed, dict) or common.canonical_json(parsed) != blob:
        raise M7Error("authorisation_evidence_mismatch", "the sealed replicate manifest is not canonical JSON")
    common.exact_keys(parsed, replicate.MANIFEST_KEYS, "authorisation_evidence_mismatch")
    replicate.validate_replicate_manifest(parsed)
    if parsed["run_id"] != parent_name:
        raise M7Error("sibling_evidence_access", "the sealed replicate manifest belongs to another directory")
    if parsed["authorisation"]["executing_implementation_commit"] != entry["executing_implementation_commit"]:
        raise M7Error("provenance_mismatch", "the replicate ran under another implementation commit")
    item = assert_predecessor_identity(parsed, entry)
    ranking = parsed["validation_ranking"]
    if ranking_sha256(ranking) != entry["validation_ranking_sha256"]:
        raise M7Error("authorisation_evidence_mismatch", "the validation ranking is not the one the authorisation binds")
    ranked = [record["epoch"] for record in ranking["ranked_candidates"]]
    position = ranked.index(epoch) + 1
    if position != entry["ranking_position"] or [record["epoch"] for record in entry["preceding_candidates"]] != ranked[: position - 1]:
        raise M7Error("selection_invalid", "the entry is not the next candidate of the sealed validation ranking")
    return {
        "epoch": epoch,
        "replicate_manifest_sha256": entry["replicate_manifest_sha256"],
        "seed": seed,
        "validation_mse": ranking["ranked_candidates"][position - 1]["aggregate_mse"],
        "validation_ranking_sha256": entry["validation_ranking_sha256"],
        "weight_sha256": item["weight_sha256"],
    }


def assert_candidate_not_already_evaluated(entry, run_root, deps):
    """Refuse a candidate whose seed and epoch already have a success manifest elsewhere."""
    seed = entry["candidate_seed"]
    epoch = entry["candidate_epoch"]
    try:
        names = sorted(deps.listdir(run_root))
    except FileNotFoundError:
        return True
    for name in names:
        matched = AUTHORISATION_ID_PATTERN.fullmatch(name)
        if matched is None or (int(matched.group(1)), int(matched.group(2))) != (seed, epoch):
            continue
        try:
            deps.lstat(os.path.join(run_root, name, SUCCESS_MANIFEST_NAME))
        except FileNotFoundError:
            continue
        raise M7Error("authorization_reuse", "this seed and epoch candidate has already been evaluated")
    return True


# ------------------------------------------------------------------ pinned tools and assets


def load_verified_tools(deps):
    """The approved M1 cleaner and the M4 metrics, executed from hash-verified source bytes."""
    d = diagnostic()
    b1 = d.b1_runner()
    cleaner_path = str(b1.APPROVED_CLEANER)
    assert_input_permitted(cleaner_path, "FROZEN_ENCDEC", realpath=deps.realpath)
    cleaner_bytes, _signature = common.read_regular_file(cleaner_path, deps.lstat, deps.read_bytes)
    if common.sha256_bytes(cleaner_bytes) != CLEANER_SHA256:
        raise M7Error("provenance_mismatch", "cleaner hash does not match the approved cleaner")
    metrics_bytes, _signature = common.read_regular_file(os.path.join(MRES_ROOT, d.METRICS_RELATIVE), deps.lstat, deps.read_bytes)
    metrics_config, _signature = common.read_regular_file(os.path.join(MRES_ROOT, d.METRICS_CONFIG_RELATIVE), deps.lstat, deps.read_bytes)
    if common.sha256_bytes(metrics_bytes) != d.METRICS_SHA256 or common.sha256_bytes(metrics_config) != d.METRICS_CONFIG_SHA256:
        raise M7Error("provenance_mismatch", "metrics module or configuration drifted")
    cleaner = translated(lambda: b1.load_cleaner_from_verified_source(cleaner_bytes))
    metrics = translated(lambda: b1.load_metrics_from_verified_source(metrics_bytes))
    translated(lambda: b1.assert_bound_metrics_configuration(metrics, metrics_config))
    translated(lambda: d.assert_guardrail_thresholds(metrics))
    return {"cleaner": cleaner, "metrics": metrics}


def inspect_asset(path, expected_size, expected_sha256, role, deps, require_single_link=False):
    """One pinned asset: path gate, ancestry, ``lstat``, regular non-symlink leaf, size, hash, recheck.

    The size and signature are taken before hashing and compared again after.
    External assets may be hard-linked (a conda environment's are); their link
    count is recorded in the signature and a change is a failure. The hash
    streams through ``O_NOFOLLOW``, so a link swapped in after the inspection
    is refused as well.
    """
    assert_input_permitted(path, role, realpath=deps.realpath)
    digest, signature = common.hash_regular_file(path, deps.lstat, deps.sha256_file, require_single_link, expected_size)
    if digest != expected_sha256:
        raise M7Error("provenance_mismatch", "a pinned asset does not have its pinned hash: " + os.path.basename(path))
    return signature


def measure_generation_assets(deps):
    """Inspect the generation inputs and the frozen EncDec assets against their pins, symlink-safely.

    The B1 diffusion weights are not an input: the diffusion model is the
    authorised candidate checkpoint only.
    """
    d = diagnostic()
    b1 = d.b1_runner()
    contract = d.m6_contract()
    m5 = contract.m5_contract()
    for relative, expected, _large in b1.MODEL_INPUTS:
        if relative.startswith("configs/rnagenesis/diffusion/"):
            continue
        inspect_asset(os.path.join(common.RNAGENESIS_ROOT, relative), None, expected, "FROZEN_ENCDEC", deps)
    for relative, digest, size, role in m5.REQUIRED_MODEL_FILES:
        if role in d.ENCDEC_ROLES:
            inspect_asset(os.path.join(common.RNAGENESIS_ROOT, relative), size, digest, "FROZEN_ENCDEC", deps)
    # The Diffusers normalisation patch lives in the pinned environment, outside RNAGenesis.
    patch_digest, _signature = common.hash_regular_file(m5.DIFFUSERS_PATCH_PATH, deps.lstat, deps.sha256_file, False, m5.DIFFUSERS_PATCH_SIZE)
    if patch_digest != m5.DIFFUSERS_PATCH_SHA256:
        raise M7Error("provenance_mismatch", "the Diffusers normalisation patch does not have its pinned hash")
    return True


def assert_schedule_contract(schedule, pins):
    """The accepted M4 schedule: 1,000 attempts in 112 invocations seeded 44000 + index."""
    pinned = pins["schedule"]
    if pinned["schedule"]["sha256"] != common.m6_contract().PAIRED_SCHEDULE_SHA256:
        raise M7Error("identity_mismatch", "the pinned schedule is not the accepted paired schedule")
    if pinned["attempts"] != ATTEMPT_COUNT or pinned["invocations"] != INVOCATION_COUNT:
        raise M7Error("schedule_invalid", "the pinned schedule counts are not 1000 attempts in 112 invocations")
    invocations = schedule["invocations"]
    if schedule["total_attempts"] != ATTEMPT_COUNT or schedule["invocation_count"] != INVOCATION_COUNT or len(invocations) != INVOCATION_COUNT:
        raise M7Error("schedule_invalid", "the schedule is not 1000 attempts in 112 invocations")
    seen = []
    for position, invocation in enumerate(invocations):
        chunk = invocation["actual_chunk_size"]
        if invocation["invocation_index"] != position or invocation["invocation_seed"] != GENERATION_SEED_BASE + position:
            raise M7Error("schedule_invalid", "invocation order or seed drifted")
        if invocation["max_seq_len"] != invocation["target_length"] + 1 or invocation["batch_num"] != 1 or not 1 <= chunk <= 16:
            raise M7Error("schedule_invalid", "invocation length, batch or chunk drifted")
        if len(invocation["original_attempt_indexes"]) != chunk or invocation["expected_batch_positions"] != list(range(chunk)):
            raise M7Error("schedule_invalid", "invocation attempt identities drifted")
        seen.extend(invocation["original_attempt_indexes"])
    if sorted(seen) != list(range(ATTEMPT_COUNT)):
        raise M7Error("schedule_invalid", "attempt identities are not a permutation of 0 through 999")
    return True


def read_pinned_file(path, expected, deps, role, pins=None):
    """A pinned data file, read through the symlink-safe inspection with its size and hash checked."""
    assert_input_permitted(path, role, realpath=deps.realpath, pins=pins)
    data, _signature = common.read_regular_file(path, deps.lstat, deps.read_bytes, False, expected["bytes"])
    if common.sha256_bytes(data) != expected["sha256"]:
        code = "train_identity_mismatch" if role == "TRAIN_TEXT_DIAGNOSTIC_ONLY" else "schedule_hash_mismatch"
        raise M7Error(code, "a pinned data file does not have its pinned hash: " + os.path.basename(path))
    return data


def load_accepted_schedule(deps):
    """Rebuild the accepted schedule from the accepted length vector and match it byte for byte."""
    d = diagnostic()
    pins = deps.pins
    pinned = pins["schedule"]
    vector = translated(
        lambda: read_pinned_file(os.path.join(pinned["directory"], pinned["length_vector"]["name"]), pinned["length_vector"], deps, "ACCEPTED_SCHEDULE")
    )
    accepted = translated(
        lambda: read_pinned_file(os.path.join(pinned["directory"], pinned["schedule"]["name"]), pinned["schedule"], deps, "ACCEPTED_SCHEDULE")
    )
    schedule, body = translated(lambda: d.rebuild_and_verify_schedule(vector, accepted, pins))
    assert_schedule_contract(schedule, pins)
    return schedule, body, vector


def open_train_cores(deps, vector_bytes):
    """TRAIN is opened for the exact-copy guardrail only, and only after consumption.

    It is read through the same symlink-safe inspection as every pinned file.
    """
    d = diagnostic()
    pins = deps.pins
    pinned = pins["train"]
    data = read_pinned_file(pinned["path"], pinned, deps, "TRAIN_TEXT_DIAGNOSTIC_ONLY", pins)
    ordered = translated(lambda: d.b1_runner().parse_length_vector(vector_bytes))
    cores = translated(lambda: d.split_train_records(data.decode("utf-8")))
    if len(cores) != pinned["count"]:
        raise M7Error("train_identity_mismatch", "TRAIN record count drifted")
    if [len(core) for core in cores] != list(ordered):
        raise M7Error("train_identity_mismatch", "TRAIN lengths do not equal the accepted length vector")
    return cores


# ------------------------------------------------------------------ invocations


def build_candidate_command(invocation, output_directory, parent, physical_gpu, checkpoint_dir, entry, ld_library_path=None, reader=None):
    """argv, working directory and the strict child environment for one invocation."""
    b1 = diagnostic().b1_runner()
    argv = build_candidate_argv(invocation, checkpoint_dir, entry, reader)
    common.assert_pinned_interpreter_argv(argv)
    argv.extend(["--superfolder", os.path.join(output_directory, GENERATION_OUTPUT_DIRECTORY), "--mid_folder", b1.invocation_folder(invocation)])
    return {
        "argv": argv,
        "cwd": b1.GENERATION_CWD,
        "env": common.build_child_environment(dict(parent), physical_gpu, output_directory, ld_library_path),
        "shell": False,
    }


def run_invocation(output_directory, invocation, entry, deps, cleaner, progress=None):
    """One generation.py call, its raw output, and the cleaner mapping of that output.

    ``progress`` receives the invocation index and the sub-stage before each
    step, so a failure record names exactly where the run stopped.
    """
    b1 = diagnostic().b1_runner()

    def mark(stage):
        if progress is not None:
            progress["stage"] = stage
            if isinstance(progress.get("candidate"), dict):
                progress["candidate"]["invocation_index"] = invocation["invocation_index"]

    mark("generation_invocation_command")
    command = build_candidate_command(
        invocation, output_directory, deps.environ, entry["physical_gpu_index"], entry["checkpoint_directory"], entry, entry["ld_library_path"]
    )
    predicted = b1.predicted_generation_path(output_directory, invocation)
    try:
        deps.lstat(predicted)
    except FileNotFoundError:
        pass
    else:
        raise M7Error("filesystem_error", "an invocation output already exists")
    deps.mkdir(os.path.join(output_directory, GENERATION_OUTPUT_DIRECTORY, b1.invocation_folder(invocation)))
    mark("generation_invocation_spawn")
    completed = deps.subprocess_run(command["argv"], cwd=command["cwd"], env=command["env"], shell=False)
    returncode = getattr(completed, "returncode", None)
    if type(returncode) is not int or returncode != 0:
        raise M7Error("generation_process_failed", "generation.py exited {}".format(returncode))
    mark("generation_invocation_output_read")
    data = bytes(deps.read_bytes(predicted))
    mark("generation_invocation_output_mapping")
    records = translated(lambda: b1.map_invocation_output(data, invocation, cleaner))
    metadata = translated(lambda: b1._raw_invocation_record(predicted, data, invocation, cleaner))
    if metadata["line_count"] != invocation["actual_chunk_size"]:
        raise M7Error("output_line_count_mismatch", "raw line count does not match the chunk")
    return records, metadata, data


def execute_schedule(schedule, output_directory, entry, deps, cleaner, progress=None):
    """Every scheduled invocation, in schedule order. Nothing is skipped, retried or replaced."""
    b1 = diagnostic().b1_runner()
    attempts, raw_rows, invocation_rows, payloads = [], [], [], []
    for invocation in schedule["invocations"]:
        mapped, metadata, payload = run_invocation(output_directory, invocation, entry, deps, cleaner, progress)
        attempts.extend(mapped)
        raw_rows.extend(b1.raw_attempt_record(row) for row in mapped)
        invocation_rows.append({field: metadata[field] for field in b1.RAW_INVOCATION_FIELDS})
        payloads.append((metadata, payload))
    if progress is not None and isinstance(progress.get("candidate"), dict):
        progress["candidate"].pop("invocation_index", None)
    return attempts, raw_rows, invocation_rows, payloads


def verify_attempt_ledger(attempts, schedule):
    """Exactly the 1,000 scheduled attempts: none malformed, missing, duplicated or in excess."""
    d = diagnostic()
    b1 = d.b1_runner()
    if not isinstance(attempts, list) or len(attempts) != ATTEMPT_COUNT:
        raise M7Error("attempt_ledger_invalid", "the attempt ledger does not hold exactly 1000 rows")
    expected = {}
    for invocation in schedule["invocations"]:
        for position, index in enumerate(invocation["original_attempt_indexes"]):
            expected[index] = (invocation["invocation_index"], position, invocation["target_length"], invocation["max_seq_len"], invocation["invocation_seed"])
    seen = set()
    for attempt in attempts:
        if not isinstance(attempt, dict) or tuple(attempt) != tuple(b1.ATTEMPT_FIELDS):
            raise M7Error("attempt_ledger_invalid", "an attempt row is malformed")
        index = attempt["original_attempt_index"]
        if isinstance(index, bool) or not isinstance(index, int) or index not in expected:
            raise M7Error("attempt_ledger_invalid", "an attempt row names an unscheduled attempt")
        if index in seen:
            raise M7Error("attempt_ledger_invalid", "an attempt row is duplicated")
        seen.add(index)
        row = (attempt["invocation_index"], attempt["batch_position"], attempt["requested_target_length"], attempt["max_seq_len"], attempt["invocation_seed"])
        if row != expected[index]:
            raise M7Error("attempt_ledger_invalid", "an attempt row departs from the accepted schedule")
        if not isinstance(attempt["raw_decoded_text"], str) or not isinstance(attempt["cleaned_sequence"], str) or not isinstance(attempt["validity"], bool):
            raise M7Error("attempt_ledger_invalid", "an attempt row has a malformed text or validity field")
    if len(seen) != ATTEMPT_COUNT:
        raise M7Error("attempt_ledger_invalid", "an attempt row is missing")
    translated(lambda: b1.assert_attempt_accounting(attempts, schedule))
    translated(lambda: d.assert_normalisation_reconciles(attempts))
    return True


def report_only_block(attempts, summary):
    """Requested-length matching, early EOS and gross length behaviour. Descriptive only."""
    valid = [attempt for attempt in attempts if attempt["validity"] is True]
    deltas = [attempt["length_delta"] for attempt in valid]
    below_half = sum(1 for attempt in valid if attempt["cleaned_length"] * 2 < attempt["requested_target_length"])
    return {
        "early_eos_count": summary["early_eos_observations"],
        "eligibility_effect": "none",
        "gross_length_behaviour": {
            "maximum_length_delta": max(deltas) if deltas else None,
            "mean_length_delta": common.format_decimal(sum(deltas) / float(len(deltas))) if deltas else None,
            "minimum_length_delta": min(deltas) if deltas else None,
            "valid_attempts": len(valid),
            "valid_attempts_below_half_the_requested_length": below_half,
        },
        "requested_length_exact_hit_rate": common.format_decimal(summary["exact_length_hits"] / float(len(attempts))),
        "requested_length_matching": {
            "exact_hits": summary["exact_length_hits"],
            "invalid_attempts": len(attempts) - len(valid),
            "length_mismatches": sum(1 for delta in deltas if delta != 0),
            "raw_attempts": len(attempts),
        },
        "thresholds_defined": False,
    }


def report_only_diagnostics(attempts, train_cores, deps):
    """The accepted M6 report-only diagnostics, reused unchanged on the full 1,000-attempt ledger.

    Nearest-TRAIN normalised edit distance, maximum edit similarity to TRAIN,
    nucleotide and dinucleotide total-variation distance to TRAIN, MFE, MFE per
    nucleotide, paired fraction, and the per-requested-length strata. Every raw
    attempt stays in its denominator. Edit similarity is ``1 - normalised edit
    distance``; it is not sequence identity. Nothing here is a threshold and
    nothing feeds the ranking or the five guardrails.
    """
    d = diagnostic()
    return translated(lambda: d.report_only_diagnostics(attempts, train_cores, deps.fold, deps.nearest))


def diagnostics_record(diagnostics, sha256):
    """The manifest's pointer to the retained diagnostics file, with a headline of each family."""

    def median(block):
        return None if not isinstance(block, dict) or block.get("median") is None else block["median"]

    headline = {
        "dinucleotide_total_variation_to_train": diagnostics["dinucleotide_total_variation_to_train"],
        "maximum_edit_similarity_to_train": diagnostics["maximum_edit_similarity_to_train"],
        "mfe_median": median(diagnostics["mfe"]),
        "mfe_per_nt_median": median(diagnostics["mfe_per_nt"]),
        "nearest_train_normalized_edit_distance_median": median(diagnostics["nearest_train_normalized_edit_distance"]),
        "nucleotide_total_variation_to_train": diagnostics["nucleotide_total_variation_to_train"],
        "paired_fraction_median": median(diagnostics["paired_fraction"]),
    }
    return {
        "edit_similarity_definition": diagnostic().EDIT_SIMILARITY_DEFINITION,
        "edit_similarity_is_sequence_identity": False,
        "effect_on_ranking_or_thresholds": "none",
        "file": REPORT_ONLY_DIAGNOSTICS_NAME,
        "headline": headline,
        "sha256": sha256,
        "thresholds_defined": False,
    }


def _gpu_block(entry):
    return {
        "cuda_visible_devices": entry["cuda_visible_devices"],
        "logical_device": entry["logical_device"],
        "pci_bus": entry["pci_bus"],
        "physical_index": entry["physical_gpu_index"],
        "uuid": entry["gpu_uuid"],
    }


def production_generate_and_measure(entry, checkpoint_dir, output_directory, deps=None, progress=None, run_root=None):
    """The real candidate diagnostic for one authorised seed and epoch.

    ``run_candidate`` calls this after the bound directory is consumed and the
    checkpoint is verified, and verifies the checkpoint again afterwards. The
    steps are: bind the replicate manifest, match ``LD_LIBRARY_PATH``, check
    the pinned assets and tools, rebuild the accepted schedule, open TRAIN for
    the exact-copy guardrail, run all 112 invocations, reconcile the 1,000
    attempt rows, compute the five guardrails and the report-only block, and
    retain the raw and normalised ledgers with their hashes. Nothing is
    resampled, replaced, truncated, padded, dropped or deduplicated.
    """
    deps = CandidateDependencies() if deps is None else deps
    run_root = common.RUN_ROOT if run_root is None else run_root
    progress = common.new_progress(entry["candidate_seed"], "candidate") if progress is None else progress
    if progress.get("candidate") is None:
        progress["candidate"] = {"epoch": entry["candidate_epoch"], "ranking_position": entry["ranking_position"], "seed": entry["candidate_seed"]}
    if checkpoint_dir != entry["checkpoint_directory"]:
        raise M7Error("authorisation_scope_invalid", "generation may load only the authorised candidate checkpoint")
    d = diagnostic()
    b1 = d.b1_runner()
    progress["stage"] = "replicate_binding"
    binding = verify_replicate_binding(entry, deps, run_root)
    progress["stage"] = "ld_library_path"
    ld_record = common.resolve_ld_library_path(deps.environ, entry["ld_library_path"])
    progress["stage"] = "interpreter_identity"
    interpreter = deps.observe_interpreter(common.PINNED_PYTHON)
    common.assert_interpreter_matches(interpreter, entry["interpreter"])
    progress["stage"] = "generation_assets"
    measure_generation_assets(deps)
    progress["stage"] = "tool_load"
    tools = load_verified_tools(deps)
    progress["stage"] = "schedule"
    schedule, schedule_bytes, vector_bytes = load_accepted_schedule(deps)
    progress["stage"] = "train_open"
    train_cores = open_train_cores(deps, vector_bytes)
    progress["stage"] = "isolation_setup"
    common.create_isolated_directories(output_directory)
    deps.mkdir(os.path.join(output_directory, GENERATION_OUTPUT_DIRECTORY))
    progress["stage"] = "generation"
    attempts, raw_rows, invocation_rows, payloads = execute_schedule(schedule, output_directory, entry, deps, tools["cleaner"], progress)
    progress["stage"] = "accounting"
    verify_attempt_ledger(attempts, schedule)
    progress["stage"] = "raw_output_reverification"
    for metadata, payload in payloads:
        if bytes(deps.read_bytes(metadata["raw_file_path"])) != payload:
            raise M7Error("incomplete_evidence_or_manifest", "a raw generation output changed after it was read")
    progress["stage"] = "metrics"
    metrics = tools["metrics"]
    summary = translated(lambda: metrics.summarise_attempts(attempts))
    evaluation = translated(lambda: d.evaluate_guardrails(metrics, attempts, train_cores))
    values = {rule[0]: evaluation["values"][rule[0]] for rule in HARD_GUARDRAIL_RULES}
    ours = evaluate_guardrail_values(values)
    if [(item["id"], item["passed"]) for item in ours["decisions"]] != [(item["id"], item["passed"]) for item in evaluation["decisions"]]:
        raise M7Error("guardrail_manifest_invalid", "the guardrail decisions differ from the accepted M4 evaluation")
    progress["stage"] = "report_only_diagnostics"
    diagnostics = report_only_diagnostics(attempts, train_cores, deps)
    progress["stage"] = "ledger_write"
    raw_ledger = translated(lambda: b1.serialize_jsonl(raw_rows, b1.RAW_ATTEMPT_FIELDS, "original_attempt_index"))
    audited = translated(lambda: b1.serialize_jsonl(attempts, b1.ATTEMPT_FIELDS, "original_attempt_index"))
    if raw_ledger == audited:
        raise M7Error("attempt_ledger_invalid", "the raw and normalised ledgers must be distinct")
    invocation_bytes = common.canonical_json(
        {"invocation_count": len(invocation_rows), "invocations": invocation_rows, "role": "invocation_output_manifest", "schema_version": MANIFEST_SCHEMA_VERSION}
    )
    files = {
        RAW_LEDGER_NAME: raw_ledger,
        AUDITED_LEDGER_NAME: audited,
        INVOCATION_MANIFEST_NAME: invocation_bytes,
        METRICS_NAME: common.canonical_json(summary),
        GUARDRAIL_VALUES_NAME: common.canonical_json(evaluation),
        REPORT_ONLY_DIAGNOSTICS_NAME: common.canonical_json(diagnostics),
        SCHEDULE_COPY_NAME: schedule_bytes,
    }
    for name, blob in files.items():
        deps.write_bytes(output_directory, name, blob)
    ledgers = {key: common.sha256_bytes(files[name]) for key, name in LEDGER_FILES.items()}
    progress["stage"] = "measurement"
    return {
        "accounting": {
            "cleaner_sha256": CLEANER_SHA256,
            "invocation_count": len(invocation_rows),
            "raw_attempts": len(attempts),
            "schedule_sha256": deps.pins["schedule"]["schedule"]["sha256"],
            "valid_outputs": summary["valid_outputs"],
        },
        "environment": {"interpreter": interpreter, "ld_library_path": ld_record},
        "gpu": _gpu_block(entry),
        "ledgers": ledgers,
        "provenance": provenance_block(entry["implementation_file_hashes"]),
        "replicate_binding": binding,
        "report_only": dict(
            report_only_block(attempts, summary),
            diagnostics=diagnostics_record(diagnostics, ledgers["report_only_diagnostics_sha256"]),
        ),
        "values": values,
    }


# ------------------------------------------------------------------ authorised launcher


def live_repository_observation(config, entry, deps):
    """Repository, parent-commit and file-hash observation for one entry (stdlib and git only)."""
    git = deps.git

    def text(repo, args):
        return git(repo, args)

    head = text(MRES_ROOT, ["rev-parse", "HEAD"]).strip()
    parents = [line.strip() for line in text(MRES_ROOT, ["rev-parse", "HEAD^@"]).splitlines() if line.strip()]
    observation = {
        "changed_files": [],
        "file_sha256_at_parent": {},
        "file_sha256_working_tree": {},
        "implementation_config": {},
        "implementation_config_bytes": b"",
        "mres_branch": text(MRES_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
        "mres_head": head,
        "mres_origin_main": text(MRES_ROOT, ["rev-parse", "origin/main"]).strip(),
        "mres_parents": parents,
        "mres_porcelain": text(MRES_ROOT, ["status", "--porcelain=v1", "--untracked-files=all"]),
        "rnagenesis_branch": text(common.RNAGENESIS_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
        "rnagenesis_directory_porcelain": text(common.RNAGENESIS_ROOT, ["status", "--porcelain=v1"]),
        "rnagenesis_file_porcelain": text(common.RNAGENESIS_ROOT, ["status", "--porcelain=v1", "--untracked-files=all"]),
        "rnagenesis_head": text(common.RNAGENESIS_ROOT, ["rev-parse", "HEAD"]).strip(),
    }
    if len(parents) != 1:
        return observation
    parent = parents[0]
    raw = bytes(deps.git_blob(parent + ":" + CONFIG_RELATIVE))
    observation["implementation_config_bytes"] = raw
    observation["implementation_config"] = common.load_config_bytes(raw)
    observation["changed_files"] = [line.strip() for line in text(MRES_ROOT, ["diff", "--name-only", parent, "HEAD"]).splitlines() if line.strip()]
    for relative in IMPLEMENTATION_FILE_PATHS:
        observation["file_sha256_at_parent"][relative] = common.sha256_bytes(bytes(deps.git_blob(parent + ":" + relative)))
        observation["file_sha256_working_tree"][relative] = common.sha256_bytes(bytes(deps.read_bytes(os.path.join(MRES_ROOT, relative))))
    return observation


def _find_entry(entries, authorisation_id):
    matches = [entry for entry in entries.values() if entry["authorisation_id"] == authorisation_id]
    if len(matches) != 1:
        raise M7Error("authorisation_field_missing", "no single entry carries that authorisation id")
    return matches[0]


def launch_authorised_candidate(authorisation_id, run_root=None, deps=None, config_bytes=None, observation=None):
    """Resolve one authorisation id to one entry, consume it, and run the real diagnostic.

    No seed, epoch, path, GPU or scientific parameter comes from the caller. An
    inactive configuration is refused before the environment, git, a GPU, the
    run root or any biological path is touched. This function needs no
    injected callable: ``run_candidate`` defaults to the production generator.
    """
    deps = CandidateDependencies() if deps is None else deps
    root = common.RUN_ROOT if run_root is None else run_root
    if not isinstance(authorisation_id, str) or AUTHORISATION_ID_PATTERN.fullmatch(authorisation_id) is None:
        raise M7Error("cli_argument_rejected", "the authorisation id is not an m7 candidate id")
    if config_bytes is None:
        config_bytes = bytes(deps.read_bytes(CONFIG_PATH))
    config = common.load_config_bytes(config_bytes)
    if classify_configuration(config) == "inactive":
        assert_inactive_text(bytes(config_bytes).decode("utf-8"))
        reject_inactive_before_execution(config)
    entries = assert_active_configuration(config, root)
    entry = _find_entry(entries, authorisation_id)
    parent = deps.environ
    common.assert_parent_environment(dict(parent), entry["physical_gpu_index"])
    common.pin_process_path(parent)
    if observation is None:
        observation = live_repository_observation(config, entry, deps)
    head = replicate.assert_repository_binding(config, entry, observation, PERMITTED_AUTHORIZATION_FILES)
    common.resolve_ld_library_path(parent, entry["ld_library_path"])
    common.assert_interpreter_matches(deps.observe_interpreter(common.PINNED_PYTHON), entry["interpreter"])
    b1 = diagnostic().b1_runner()
    translated(lambda: b1.assert_parent_cuda(parent, entry["physical_gpu_index"]))
    probe = deps.gpu_preflight(parent, entry["physical_gpu_index"])
    translated(lambda: b1.assert_gpu_probe(probe, entry["physical_gpu_index"], {"gpu_uuid": entry["gpu_uuid"], "pci_bus": entry["pci_bus"]}))
    try:
        diagnostic().structure_features("GGGGAAAACCCC", deps.fold)
    except Exception:
        raise M7Error("fold_unavailable", "the RNA folding library is not usable, so the report-only MFE cannot be computed")
    # Reopen and independently validate the successful replicate evidence before the entry is consumed.
    verify_replicate_binding(entry, deps, root)
    assert_candidate_not_already_evaluated(entry, root, deps)
    authorised = dict(entry)
    authorised["authorization_commit"] = head
    return run_candidate(authorised, None, run_root=root, deps=deps)


# ------------------------------------------------------------------ entry point

HELP_TEXT = """\
M7 candidate-guardrail stage (inactive).

The checked-in configuration is not executable. This entry point accepts
--help, --schema and --authorisation-id <id>. The last reads only the tracked
configuration and refuses while it is inactive. No seed, epoch, checkpoint,
data, GPU, environment or output argument is accepted, and nothing starts
generation unless a later authorisation-only commit activates an entry.
"""


def schema_document():
    return {
        "authorisation_schema": authorisation_schema(),
        "document_status": DOCUMENT_STATUS,
        "entry_keys": list(ACTIVE_ENTRY_KEYS),
        "guardrails": [list(rule) for rule in HARD_GUARDRAIL_RULES],
        "manifest_keys": list(MANIFEST_KEYS),
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "schema_version": SCHEMA_VERSION,
    }


def production_main(argv=None, stdout=None):
    stdout = sys.stdout if stdout is None else stdout
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--help"], ["-h"]):
        stdout.write(HELP_TEXT)
        return 0
    if arguments == ["--schema"]:
        stdout.write(common.canonical_json(schema_document()).decode("utf-8"))
        return 0
    if len(arguments) == 2 and arguments[0] == "--authorisation-id":
        launch_authorised_candidate(arguments[1])
        return 0
    raise M7Error("cli_argument_rejected", "the entry point accepts only --help, --schema and --authorisation-id <id>")


def main(argv=None):
    try:
        return production_main(argv)
    except M7Error as exc:
        common.print_error(exc)
        return 2 if exc.code in ("cli_argument_rejected", "execution_not_authorised") else 1


if __name__ == "__main__":
    sys.exit(main())

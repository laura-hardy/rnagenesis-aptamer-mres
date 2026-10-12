#!/usr/bin/env python3
"""M7 final-selection stage (CPU-only, standard library only).

Importing this module imports only the standard library and the M7 contracts.
It never imports torch, Accelerate, Diffusers, Transformers, NumPy, RNAGenesis
training code or any GPU tooling, and it opens no biological data, checkpoint,
weight, REF, EVAL or accepted run directory. It reads sealed manifests only.

Pure part. ``build_final_selection`` takes already-read, canonical-JSON
manifest bytes and returns one deterministic final-selection manifest.
A guardrail manifest's ``executing_implementation_commit`` is the guardrail
implementation that ran. Its ``checkpoint_training_implementation_commit`` is
the implementation that trained and sealed the checkpoint, and that value is
what selection compares with the replicate manifest's
``executing_implementation_commit`` (a replicate manifest describes training,
so that field remains its training implementation). The two guardrail commits
may differ. Each seed keeps its own training commit: selection does not require
the two replicates to share one commit id, and it does not invent a shared
one. Checkpoint names keep each replicate's sealed training commit, and the
guardrail execution commit stays on the hashed guardrail manifest.
``validate_final_selection_manifest`` re-derives every embedded selection claim
from the embedded tables (see its docstring). The stage accepts either seeds 43
and 44, or seed 43 alone together with a separately sealed operational
deviation record created before M8. It rejects seed 44 alone, a missing seed
without the record, duplicate or unexpected seeds, mismatched B1 initialisation
digests, inconsistent validation identities, an extra, missing or duplicate
epoch candidate, selection from update 0, selection from an unevaluated or
failed candidate, a non-prefix lazy evaluation, and any REF- or EVAL-derived
input. The manifest always records ``human_gate_required: true`` and
``m7_complete: false``. It makes no claim about EVAL, REF or M8 generation.

Launcher. ``launch_authorised_selection`` is the executable path behind
``--authorisation-id <id>``. The checked-in configuration is inactive and
non-consumable, so the launcher refuses with ``execution_not_authorised`` after
reading only that configuration file: no environment, git, run root, manifest,
RNAGenesis or output path is inspected first. A later authorisation-only commit
that changes nothing but ``config/experiments/D1_final_selection.yaml`` may bind
one single-use entry: the exact manifests to read (path, byte count, SHA-256),
the exact new output directory and, for a one-seed selection, the already
sealed human-approved operational deviation. The command line accepts only
``--help``, ``--schema`` and ``--authorisation-id``; no manifest path, seed,
epoch, checkpoint path, output path or scientific parameter can be supplied.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import re
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
guardrails = _load_sibling("m7_candidate_guardrails", "scripts/modelling/m7_candidate_guardrails.py")
M7Error = common.M7Error

CONFIG_RELATIVE = "config/experiments/D1_final_selection.yaml"
CONFIG_PATH = os.path.join(MRES_ROOT, CONFIG_RELATIVE)
MODULE_RELATIVE = "scripts/modelling/m7_selection.py"
TEST_RELATIVE = "tests/modelling/test_m7_selection.py"
LAUNCH_TEST_RELATIVE = "tests/modelling/test_m7_selection_launch.py"
DOCUMENT_STATUS = "M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED"
ACTIVE_DOCUMENT_STATUS = "M7_FINAL_SELECTION_AUTHORISED_FOR_SINGLE_USE_EXECUTION"
SCHEMA_VERSION = "m7-final-selection-config-2"
MANIFEST_SCHEMA_VERSION = "m7-final-selection-manifest-2"
CONSUMPTION_SCHEMA_VERSION = "m7-final-selection-consumption-1"
DEVIATION_SCHEMA_VERSION = "m7-operational-deviation-1"
EXPERIMENT_ID = "D1_final_selection"
ACTIVE_PHASE = "M7_D1_final_selection"
ACTIVE_SCOPE = "single_use_m7_d1_final_selection"
ACTIVE_ROLES = ("SEALED_GUARDRAIL_MANIFEST", "SEALED_REPLICATE_MANIFEST")
SUCCESS_MANIFEST_NAME = "m7_final_selection_manifest.json"
AUTHORISATION_ID_PATTERN = re.compile(r"m7_[a-z0-9_]*final_selection[a-z0-9_]*")
AUTHORISATION_ID_MAXIMUM_LENGTH = 128
DEVIATION_KIND = "seed_44_omitted_operational_time_limit"
OUTCOME_COMPLETE = "selected_set_complete"
OUTCOME_NONE = "no_eligible_checkpoint"
UNEVALUATED_OUTCOME = "not_evaluated_lazy_stop_after_first_passing_candidate"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
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
    MODULE_RELATIVE,
    TEST_RELATIVE,
    LAUNCH_TEST_RELATIVE,
)
PERMITTED_AUTHORIZATION_FILES = (CONFIG_RELATIVE,)
# An authorisation commit may flip these fields and nothing else. It never binds a GPU
# or opens a biological path, so the other two execution flags stay false.
PERMITTED_ACTIVATION_PATHS = (
    "authorisation_entries",
    "consumable_by_executable_workflow",
    "document_status",
    "execution.authorised",
)
ACTIVE_EXECUTION = {"authorised": True, "biological_paths_permitted": False, "gpu_identity_bound": False}
DEVIATION_KEYS = (
    "decision_time",
    "depends_on_scientific_results",
    "deviation_id",
    "deviation_sha256",
    "kind",
    "m8_generation_started",
    "measured_seed_43_end_to_end_seconds",
    "omitted_seed",
    "completed_seeds",
    "projected_completion_time",
    "projected_exceeds_hard_target",
    "recorded_before_m8_generation",
    "rule",
    "schema_version",
    "sealed",
    "sealed_at",
    "sealed_by",
    "seed_43_replicate_manifest_sha256",
)
RULE_RECORD = {
    "buffer_hours": replicate.OPERATIONAL_BUFFER_HOURS,
    "decision_is_operational_only": True,
    "hard_target": replicate.OPERATIONAL_HARD_TARGET,
    "stretch_target": replicate.OPERATIONAL_STRETCH_TARGET,
    "time_factor": replicate.OPERATIONAL_TIME_FACTOR,
}
ALLOWED_SEED_PLAN = {
    "excluded_seeds": list(replicate.EXCLUDED_SEEDS),
    "minimum_completed_seeds": replicate.MINIMUM_COMPLETED_SEEDS,
    "one_seed_requires_sealed_operational_deviation": True,
    "target_seeds": list(replicate.TARGET_SEEDS),
    "validation_draw_seed": replicate.VALIDATION_DRAW_SEED,
}
M8_BOUNDARY = {
    "implemented_in_this_package": False,
    "one_seed_attempts": replicate.M8_TOTAL_RAW_ATTEMPTS,
    "total_raw_d1_attempts": replicate.M8_TOTAL_RAW_ATTEMPTS,
    "two_seed_attempts_each": replicate.M8_TOTAL_RAW_ATTEMPTS // 2,
    "two_seed_split": "deterministic_and_balanced_within_requested_length_strata",
}
CLOSURE = {
    "eval_opened": False,
    "human_gate_required": True,
    "m7_complete": False,
    "m8_generation_performed": False,
    "ref_opened": False,
    "validation_csv_opened": False,
}
MANIFEST_KEYS = (
    "allowed_seed_plan",
    "candidate_table",
    "closure",
    "completed_seeds",
    "config_version",
    "deviation",
    "experiment_id",
    "guardrail_manifests",
    "lazy_evaluation_traces",
    "m8_allocation",
    "m8_boundary",
    "manifest_schema_version",
    "ref_eval_access",
    "replicate_manifests",
    "schema_version",
    "seed_records",
    "selected_set",
    "selected_set_sha256",
    "selection_outcome",
    "validation_rankings",
)
# Exact key sets of every nested record of the final manifest.
REPLICATE_INDEX_KEYS = ("seed", "sha256")
GUARDRAIL_INDEX_KEYS = ("epoch", "seed", "sha256")
CANDIDATE_ROW_KEYS = ("checkpoint_name", "epoch", "guardrail", "members_sha256", "rank", "seed", "update", "validation_mse", "weight_sha256")
CANDIDATE_GUARDRAIL_KEYS = ("evaluated", "manifest_sha256", "passed")
RANKING_ROW_KEYS = ("ranked_epochs", "ranking_sha256", "rule", "seed")
TRACE_CONTAINER_KEYS = ("seed", "trace")
TRACE_ROW_KEYS = ("epoch", "evaluated", "guardrail_manifest_sha256", "outcome", "rank")
SEED_RECORD_KEYS = ("lazy_state", "replicate_manifest_sha256", "seed", "selected_epoch", "status")
SELECTED_ROW_KEYS = ("checkpoint_name", "epoch", "members_sha256", "seed", "update", "validation_mse", "weight_sha256")
NESTED_KEY_SETS = {
    "candidate_guardrail": sorted(CANDIDATE_GUARDRAIL_KEYS),
    "candidate_row": sorted(CANDIDATE_ROW_KEYS),
    "guardrail_index_row": sorted(GUARDRAIL_INDEX_KEYS),
    "ranking_row": sorted(RANKING_ROW_KEYS),
    "replicate_index_row": sorted(REPLICATE_INDEX_KEYS),
    "seed_record": sorted(SEED_RECORD_KEYS),
    "selected_row": sorted(SELECTED_ROW_KEYS),
    "trace_container": sorted(TRACE_CONTAINER_KEYS),
    "trace_row": sorted(TRACE_ROW_KEYS),
}
# Authorisation entry.
REPLICATE_INPUT_KEYS = ("bytes", "path", "seed", "sha256")
GUARDRAIL_INPUT_KEYS = ("bytes", "epoch", "path", "seed", "sha256")
ACTIVE_ENTRY_KEYS = (
    "activation_status",
    "authorisation_id",
    "authorisation_timestamp",
    "authorization_parent_commit",
    "consumed",
    "deviation",
    "evidence_directory",
    "executing_implementation_commit",
    "guardrail_manifests",
    "implementation_config_sha256",
    "implementation_file_hashes",
    "output_directory",
    "permitted_roles",
    "phase",
    "replicate_manifests",
    "reuse_permitted",
    "scope",
    "session",
    "single_use",
)
CONFIGURATION_ROOT_KEYS = (
    "allowed_seed_plan",
    "authorisation_entries",
    "authorisation_schema",
    "consumable_by_executable_workflow",
    "created_against_mres_commit",
    "document_status",
    "execution",
    "experiment_id",
    "final_manifest",
    "m8_boundary",
    "manifest_schema_version",
    "operational_deviation",
    "rnagenesis_branch",
    "rnagenesis_commit",
    "schema_version",
    "selection_rules",
)


# ------------------------------------------------------------------ strict comparison


def _same(left, right):
    """Equal in value and in JSON type. ``True`` is not ``1`` and ``5.0`` is not ``5``."""
    try:
        return common.canonical_json(left) == common.canonical_json(right)
    except M7Error:
        return False


# ------------------------------------------------------------------ configuration


def authorisation_schema():
    return {
        "active_entries_present_in_this_package": False,
        "cpu_only": True,
        "entries_exactly": 1,
        "entry_binds": [
            "authorisation_id",
            "authorisation_parent_and_executing_implementation_commit",
            "implementation_file_and_parent_config_hashes",
            "exact_new_output_and_evidence_directory",
            "one_or_two_replicate_manifests_with_seed_path_bytes_and_sha256",
            "every_evaluated_guardrail_manifest_with_seed_epoch_path_bytes_and_sha256",
            "no_deviation_for_seeds_43_and_44_or_the_sealed_deviation_for_seed_43_alone",
            "single_use_session_and_non_resume_policy",
        ],
        "entry_keys": list(ACTIVE_ENTRY_KEYS),
        "guardrail_manifest_row_keys": list(GUARDRAIL_INPUT_KEYS),
        "independent_consumption": True,
        "launcher_accepts_only": "authorisation_id",
        "permitted_activation_paths": list(PERMITTED_ACTIVATION_PATHS),
        "permitted_changed_files": list(PERMITTED_AUTHORIZATION_FILES),
        "reads": "bound_sealed_manifests_only",
        "replicate_manifest_row_keys": list(REPLICATE_INPUT_KEYS),
        "retry_requires_new_entry": True,
        "scientific_parameters_from_cli": False,
    }


def expected_static_sections():
    return {
        "allowed_seed_plan": dict(ALLOWED_SEED_PLAN),
        "selection_rules": {
            "accepted_inputs": ["seeds_43_and_44", "seed_43_alone_with_sealed_operational_deviation"],
            "rejected_inputs": [
                "seed_44_alone",
                "missing_seed_without_deviation",
                "duplicate_seed",
                "unexpected_seed",
                "mismatched_b1_initial_state_digest",
                "inconsistent_validation_artifact_identity",
                "extra_missing_or_duplicate_epoch_candidate",
                "selection_from_update_0",
                "selection_from_unevaluated_or_failed_guardrail_candidate",
                "non_prefix_lazy_guardrail_evaluation",
                "ref_or_eval_derived_input",
            ],
            "ranking_rule": common.RANKING_RULE,
            "select_first_passing_candidate_of_the_sealed_ranking": True,
            "no_candidate_passes": "record_no_eligible_checkpoint",
            "automatic_learning_rate_threshold_architecture_or_seed_change": False,
            "selection_uses_ref_eval_or_downstream_results": False,
        },
        "operational_deviation": {
            "schema_version": DEVIATION_SCHEMA_VERSION,
            "kind": DEVIATION_KIND,
            "keys": sorted(DEVIATION_KEYS),
            "rule": dict(RULE_RECORD),
            "may_depend_on_scientific_results": False,
            "sealed_before_m8_generation": True,
            "automation": "none_human_scheduling_rule_recorded_only",
        },
        "final_manifest": {
            "keys": sorted(MANIFEST_KEYS),
            "nested_keys": {name: list(keys) for name, keys in NESTED_KEY_SETS.items()},
            "binds": [
                "one_or_two_successful_replicate_manifests",
                "allowed_seed_plan",
                "any_one_seed_operational_deviation",
                "complete_candidate_table_with_checkpoint_member_hashes",
                "validation_rankings_with_recomputed_ranking_hashes",
                "lazy_evaluation_traces",
                "selected_checkpoint_member_hashes",
                "deterministic_selected_set_hash",
            ],
            "closure": dict(CLOSURE),
            "canonical_bytes_independent_of_input_order": True,
            "selected_set_sha256_is_a_content_hash_not_an_authenticity_mechanism": True,
        },
        "m8_boundary": dict(M8_BOUNDARY),
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
        if key in ("authorisation_id", "output_directory", "evidence_directory", "replicate_manifests", "guardrail_manifests", "deviation", "path", "bytes", "sha256", "interpreter"):
            raise M7Error("configuration_not_consumable", "inactive configuration carries a binding key: " + str(key))
    for name, expected in expected_static_sections().items():
        if not _same(config.get(name), expected):
            raise M7Error("configuration_not_consumable", "static section drifted: " + name)
    if not _same(config.get("authorisation_schema"), authorisation_schema()):
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
        if line.strip().startswith(("replicate_manifests:", "guardrail_manifests:", "path:", "bytes:", "sha256:", "deviation:")):
            raise M7Error("configuration_not_consumable", "inactive configuration binds a manifest, path or deviation value")
    return True


def reject_inactive_before_execution(config):
    assert_inactive_configuration(config)
    raise M7Error("execution_not_authorised", "the checked-in M7 final-selection configuration is not executable")


# ------------------------------------------------------------------ operational deviation


def _parse_time(text, code="selection_invalid"):
    if not isinstance(text, str):
        raise M7Error(code, "a timestamp is not text")
    try:
        parsed = datetime.datetime.strptime(text, TIMESTAMP_FORMAT)
    except ValueError:
        raise M7Error(code, "a timestamp is not an offset ISO timestamp")
    if parsed.utcoffset() is None:
        raise M7Error(code, "a timestamp has no offset")
    return parsed


def project_completion(decision_time, measured_seconds):
    """``decision_time + 1.25 x measured seed-43 time + 2 hours``. Arithmetic only; nothing acts on it."""
    began = _parse_time(decision_time)
    seconds = common.finite_decimal_string(measured_seconds)
    if seconds <= 0.0:
        raise M7Error("selection_invalid", "the measured seed-43 time is not positive")
    return began + datetime.timedelta(seconds=replicate.OPERATIONAL_TIME_FACTOR * seconds + replicate.OPERATIONAL_BUFFER_HOURS * 3600)


def seal_deviation(record):
    """Return the record with its self-hash. The hash covers every other field."""
    body = {key: value for key, value in record.items() if key != "deviation_sha256"}
    sealed = dict(body)
    sealed["deviation_sha256"] = common.sha256_bytes(common.canonical_json(body))
    return sealed


def validate_deviation(record, seed_43_manifest=None, seed_43_sha256=None):
    """A schema-valid, sealed record for omitting seed 44 on operational grounds alone."""
    record = common.exact_keys(record, DEVIATION_KEYS, "selection_invalid")
    common.reject_sequence_text(record)
    body = {key: value for key, value in record.items() if key != "deviation_sha256"}
    if record["deviation_sha256"] != common.sha256_bytes(common.canonical_json(body)):
        raise M7Error("selection_invalid", "the deviation record is not sealed or was altered")
    if record["schema_version"] != DEVIATION_SCHEMA_VERSION or record["kind"] != DEVIATION_KIND or record["sealed"] is not True:
        raise M7Error("selection_invalid", "the deviation record schema or seal drifted")
    if not _same(record["omitted_seed"], 44) or not _same(record["completed_seeds"], [43]):
        raise M7Error("selection_invalid", "the deviation omits seed 44 and completes seed 43 only")
    if record["depends_on_scientific_results"] is not False:
        raise M7Error("selection_invalid", "an operational deviation may not depend on scientific results")
    if record["recorded_before_m8_generation"] is not True or record["m8_generation_started"] is not False:
        raise M7Error("selection_invalid", "the deviation was not sealed before M8 generation")
    if not _same(record["rule"], RULE_RECORD):
        raise M7Error("selection_invalid", "the operational rule drifted")
    if not isinstance(record["deviation_id"], str) or record["deviation_id"] == "" or record["sealed_by"] != "human_operator":
        raise M7Error("selection_invalid", "the deviation identity or sealer is missing")
    if not common.is_sha256(record["seed_43_replicate_manifest_sha256"]):
        raise M7Error("selection_invalid", "the seed-43 manifest binding is missing")
    sealed_at = _parse_time(record["sealed_at"])
    decision = _parse_time(record["decision_time"])
    if sealed_at < decision:
        raise M7Error("selection_invalid", "the record was sealed before the decision")
    hard_target = _parse_time(replicate.OPERATIONAL_HARD_TARGET)
    projected = project_completion(record["decision_time"], record["measured_seed_43_end_to_end_seconds"])
    recorded = _parse_time(record["projected_completion_time"])
    if abs((projected - recorded).total_seconds()) >= 1.0:
        raise M7Error("selection_invalid", "the recorded projection does not follow the rule")
    if record["projected_exceeds_hard_target"] is not True or not projected > hard_target:
        raise M7Error("selection_invalid", "the projection does not exceed the hard target, so seed 44 is not omitted on time grounds")
    if seed_43_sha256 is not None and record["seed_43_replicate_manifest_sha256"] != seed_43_sha256:
        raise M7Error("selection_invalid", "the deviation is bound to a different seed-43 manifest")
    if seed_43_manifest is not None and record["measured_seed_43_end_to_end_seconds"] != seed_43_manifest["timing"]["end_to_end_seconds"]:
        raise M7Error("selection_invalid", "the measured time is not the seed-43 manifest end-to-end time")
    return True


# ------------------------------------------------------------------ input parsing


def _parse_canonical(blob, what):
    if not isinstance(blob, (bytes, bytearray)):
        raise M7Error("selection_invalid", what + " must be canonical JSON bytes")
    blob = bytes(blob)
    try:
        parsed = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise M7Error("selection_invalid", what + " is not valid JSON")
    if not isinstance(parsed, dict) or common.canonical_json(parsed) != blob:
        raise M7Error("selection_invalid", what + " is not canonical JSON")
    return parsed, common.sha256_bytes(blob)


def reject_ref_eval_derived(document, what):
    """Refuse any REF- or EVAL-derived input: an opened flag, a role, or a path."""
    for key, value in common.walk(document):
        folded = str(key).casefold()
        if folded in ("ref_opened", "eval_opened") and value is not False:
            raise M7Error("ref_or_eval_access", what + " records REF or EVAL access")
        if folded in ("input_roles", "permitted_roles", "roles") and isinstance(value, list):
            if any(str(role).upper() in ("REF", "EVAL") for role in value):
                raise M7Error("ref_or_eval_access", what + " lists a REF or EVAL role")
        if folded in ("ref_path", "eval_path") and value is not None:
            raise M7Error("ref_or_eval_access", what + " carries a REF or EVAL path")
        if folded == "path" and isinstance(value, str) and common.path_is_ref_or_eval(value):
            raise M7Error("ref_or_eval_access", what + " carries a REF or EVAL path")
    return True


def _ranking_sha256(ranking_record):
    return common.sha256_bytes(common.canonical_json(ranking_record))


def _replicate_view(parsed, blob_sha):
    """What the final stage needs from one successful replicate manifest."""
    seed = parsed["seed"]
    mse = {row["epoch"]: row["aggregate_mse"] for row in parsed["validation_observations"] if row["candidate"] is True}
    ranking = [item["epoch"] for item in parsed["validation_ranking"]["ranked_candidates"]]
    checkpoints = {item["epoch"]: item for item in parsed["checkpoints"]}
    update_0 = [row for row in parsed["validation_observations"] if row["update"] == 0]
    if len(update_0) != 1 or update_0[0]["candidate"] is not False:
        raise M7Error("selection_invalid", "update 0 is not recorded as provenance only")
    return {
        "blob_sha256": blob_sha,
        "checkpoints": checkpoints,
        # A replicate manifest describes training. Its executing commit is the
        # implementation that trained and sealed the checkpoint, not a later
        # guardrail execution commit.
        "checkpoint_training_implementation_commit": parsed["authorisation"]["executing_implementation_commit"],
        "mse": mse,
        "parsed": parsed,
        "ranking": ranking,
        "ranking_sha256": _ranking_sha256(parsed["validation_ranking"]),
        "seed": seed,
    }


def _opened_corpus_identity(role):
    """TRAIN or VALIDATION content identity. Paths are not part of the comparison."""
    return {
        "observed_byte_size": role["observed_byte_size"],
        "observed_count": role["observed_count"],
        "observed_sha256": role["observed_sha256"],
        "role": role["role"],
    }


def _consistency_signature(view):
    """Sealed scientific content shared by comparable replicates.

    Sequential single-use authorisations leave each replicate with its own
    training commit, authorisation id, authorisation commit and raw
    configuration-file hash. Those values are provenance of that seed. They
    are not compared here. ``_bind_guardrail_manifest`` still requires each
    guardrail's ``checkpoint_training_implementation_commit`` to equal its
    own replicate's training commit. Ancestry of one commit to the other is
    not used: only the sealed content identities below are compared.
    """
    parsed = view["parsed"]
    identity = parsed["b1_identity"]
    artifacts = parsed["validation_artifacts"]
    frozen = parsed["frozen_state"]
    roles = parsed["data_roles"]
    repository = parsed["repository"]
    isolation = parsed["initialisation_isolation"]
    return {
        "accounting": dict(parsed["accounting"]),
        "b1_identity": {
            "initial_state_aggregate_digest": identity["initial_state_aggregate_digest"],
            "initial_state_entry_count": identity["initial_state_entry_count"],
            "initial_state_parameter_names_sha256": identity["initial_state_parameter_names_sha256"],
            "observed_assets": {
                name: {"byte_size": identity["observed_assets"][name]["byte_size"], "sha256": identity["observed_assets"][name]["sha256"]}
                for name in sorted(identity["observed_assets"])
            },
            "unet_config_sha256": identity["unet_config_sha256"],
            "weight_bytes": identity["weight_bytes"],
            "weight_sha256": identity["weight_sha256"],
        },
        "deviations": list(parsed["deviations"]),
        "experiment_id": parsed["experiment_id"],
        # The per-update parameter digest proves, within one run, that the frozen
        # encoder-decoder did not change. A CPU mock builds that module from the
        # training seed, so those digests differ by seed even when the sealed
        # asset hashes do not. Cross-seed architecture identity is the sealed
        # asset hashes in ``b1_identity`` together with this protocol.
        "frozen_encdec": {
            "encdec_buffers_absent_from_optimizer": frozen["encdec_buffers_absent_from_optimizer"],
            "encdec_eval_mode": frozen["encdec_eval_mode"],
            "encdec_parameters_absent_from_optimizer": frozen["encdec_parameters_absent_from_optimizer"],
            "encdec_requires_grad_false": frozen["encdec_requires_grad_false"],
            "optimizer_contains_only_denoiser": frozen["optimizer_contains_only_denoiser"],
            "optimizer_parameter_ids_equal_trainable_denoiser": frozen["optimizer_parameter_ids_equal_trainable_denoiser"],
            "persistent_buffer_digests_by_update": dict(frozen["persistent_buffer_digests_by_update"]),
            "rotary_cache_names": list(frozen["rotary_cache_names"]),
        },
        "implementation_file_hashes": dict(parsed["configuration"]["implementation_file_hashes"]),
        "initialisation_isolation": {
            "b1_loaded_fresh_for_this_seed": isolation["b1_loaded_fresh_for_this_seed"],
            "cross_seed_state_reused": isolation["cross_seed_state_reused"],
            "forbidden_weight_sha256": list(isolation["forbidden_weight_sha256"]),
            "initialisation_relative_path": isolation["initialisation_relative_path"],
            "m6_checkpoint_loaded": isolation["m6_checkpoint_loaded"],
            "saved_weights_equal_a_forbidden_m6_hash": isolation["saved_weights_equal_a_forbidden_m6_hash"],
        },
        "optimizer": dict(parsed["optimizer"]),
        "post_schedule_position": dict(parsed["post_schedule_position"]),
        "rnagenesis": {"branch": repository["rnagenesis_branch"], "commit": repository["rnagenesis_commit"]},
        "schedule": dict(parsed["schedule"]),
        "schema_version": parsed["schema_version"],
        "train_text": _opened_corpus_identity(roles["train_text"]),
        "validation_artifacts": {
            key: artifacts[key]
            for key in (
                "draw_manifest_sha256",
                "draws",
                "hash_report_sha256",
                "noise_sha256",
                "noise_shape",
                "order_artifact_sha256",
                "sequence_count",
                "sequence_order_sha256",
                "timestep_sha256",
                "timestep_shape",
                "validation_csv_sha256",
            )
        },
        "validation_csv": _opened_corpus_identity(roles["validation_csv"]),
        "validation_draw_seed": parsed["rng"]["validation_draw_seed"],
    }


def _assert_cross_seed_consistency(views):
    """Refuse scientific drift. Do not refuse sequential authorisation provenance.

    One completed seed has nothing to compare. Two seeds must share the sealed
    implementation-file hashes, B1 identity, architecture, schedule, fixed
    protocol, and TRAIN and VALIDATION identities. Checkpoint-training commit
    ids and raw authorisation-bearing configuration hashes are allowed to differ.
    """
    if len(views) < 2:
        return True
    signatures = {seed: _consistency_signature(view) for seed, view in views.items()}
    reference = signatures[min(signatures)]
    for signature in signatures.values():
        if signature == reference:
            continue
        b1 = signature["b1_identity"]
        reference_b1 = reference["b1_identity"]
        if b1["initial_state_aggregate_digest"] != reference_b1["initial_state_aggregate_digest"] or (
            b1["initial_state_parameter_names_sha256"] != reference_b1["initial_state_parameter_names_sha256"]
        ):
            raise M7Error("selection_invalid", "the B1 initial-state digests differ between seeds")
        if signature["validation_artifacts"] != reference["validation_artifacts"]:
            raise M7Error("selection_invalid", "the validation artifact identities differ between seeds")
        if signature["validation_csv"] != reference["validation_csv"]:
            raise M7Error("selection_invalid", "the VALIDATION identity differs between seeds")
        if signature["implementation_file_hashes"] != reference["implementation_file_hashes"]:
            raise M7Error("selection_invalid", "the sealed training implementation file hashes differ between seeds")
        if b1 != reference_b1 or signature["initialisation_isolation"] != reference["initialisation_isolation"]:
            raise M7Error("selection_invalid", "the B1 initialisation identity differs between seeds")
        if signature["frozen_encdec"] != reference["frozen_encdec"] or signature["rnagenesis"] != reference["rnagenesis"]:
            raise M7Error("selection_invalid", "the model architecture identity differs between seeds")
        if signature["schedule"] != reference["schedule"] or signature["post_schedule_position"] != reference["post_schedule_position"]:
            raise M7Error("selection_invalid", "the learning-rate schedule differs between seeds")
        if signature["optimizer"] != reference["optimizer"] or signature["accounting"] != reference["accounting"] or signature["deviations"] != reference["deviations"]:
            raise M7Error("selection_invalid", "the non-seed training protocol differs between seeds")
        if signature["train_text"] != reference["train_text"]:
            raise M7Error("selection_invalid", "the TRAIN identity differs between seeds")
        if signature["validation_draw_seed"] != reference["validation_draw_seed"]:
            raise M7Error("selection_invalid", "the validation draw seed differs between seeds")
        raise M7Error("selection_invalid", "the seeds do not share one sealed training implementation and protocol")
    return True


# ------------------------------------------------------------------ construction


def _plan_seeds(views, deviation_record):
    seeds = sorted(views)
    if seeds == [43, 44]:
        if deviation_record is not None:
            raise M7Error("selection_invalid", "a one-seed deviation record accompanies a two-seed selection")
        return seeds
    if seeds == [44]:
        raise M7Error("selection_invalid", "seed 44 alone is not an accepted plan")
    if seeds == [43]:
        if deviation_record is None:
            raise M7Error("selection_invalid", "seed 43 alone requires a sealed operational deviation record")
        return seeds
    raise M7Error("selection_invalid", "the completed seeds are not 43 and 44, or 43 with a deviation")


def _bind_guardrail_manifest(parsed, sha, view):
    guardrails.validate_candidate_manifest(parsed)
    reject_ref_eval_derived(parsed, "a guardrail manifest")
    seed = parsed["candidate"]["seed"]
    epoch = parsed["candidate"]["epoch"]
    binding = parsed["replicate_binding"]
    if binding["replicate_manifest_sha256"] != view["blob_sha256"] or binding["validation_ranking_sha256"] != view["ranking_sha256"]:
        raise M7Error("selection_invalid", "a guardrail manifest is bound to a different replicate or ranking")
    checkpoint = view["checkpoints"].get(epoch)
    if checkpoint is None or binding["weight_sha256"] != checkpoint["weight_sha256"] or parsed["checkpoint"]["members_sha256"] != checkpoint["saved_hashes"]:
        raise M7Error("selection_invalid", "a guardrail manifest does not evaluate the replicate's saved checkpoint")
    if binding["validation_mse"] != view["mse"][epoch]:
        raise M7Error("selection_invalid", "a guardrail manifest carries a different validation value")
    if parsed["candidate"]["ranking_position"] != view["ranking"].index(epoch) + 1:
        raise M7Error("selection_invalid", "a guardrail manifest carries the wrong ranking position")
    authorisation = parsed["authorisation"]
    # Checkpoint provenance is the sealed training commit. The guardrail
    # execution commit is a different identity and is not a fallback.
    training = authorisation["checkpoint_training_implementation_commit"]
    if training != view["checkpoint_training_implementation_commit"]:
        raise M7Error("selection_invalid", "a guardrail manifest is not bound to this replicate's sealed training implementation")
    if parsed["checkpoint"]["directory_name"] != checkpoint["directory_name"]:
        raise M7Error("selection_invalid", "a guardrail manifest does not name this replicate's saved checkpoint")
    return seed, epoch


def build_final_selection(replicate_blobs, guardrail_blobs, deviation_blob=None):
    """Build the final-selection manifest. Input order never changes the output bytes."""
    views = {}
    for blob in replicate_blobs:
        parsed, sha = _parse_canonical(blob, "a replicate manifest")
        seed = parsed.get("seed") if isinstance(parsed, dict) else None
        if seed in views:
            raise M7Error("selection_invalid", "a seed has more than one replicate manifest")
        replicate.validate_replicate_manifest(parsed)
        reject_ref_eval_derived(parsed, "a replicate manifest")
        views[replicate.assert_seed(parsed["seed"])] = _replicate_view(parsed, sha)
    if not views:
        raise M7Error("selection_invalid", "no replicate manifest was supplied")
    deviation_record = None
    if deviation_blob is not None:
        deviation_record, _blob_sha = _parse_canonical(deviation_blob, "the deviation record")
    seeds = _plan_seeds(views, deviation_record)
    _assert_cross_seed_consistency(views)
    if deviation_record is not None:
        validate_deviation(deviation_record, views[43]["parsed"], views[43]["blob_sha256"])

    evaluated = {seed: {} for seed in seeds}
    guardrail_index = []
    for blob in guardrail_blobs:
        parsed, sha = _parse_canonical(blob, "a guardrail manifest")
        try:
            seed = parsed["candidate"]["seed"]
        except (KeyError, TypeError):
            raise M7Error("selection_invalid", "a guardrail manifest has no candidate identity")
        if seed not in views:
            raise M7Error("selection_invalid", "a guardrail manifest is for a seed without a replicate manifest")
        seed, epoch = _bind_guardrail_manifest(parsed, sha, views[seed])
        if epoch in evaluated[seed]:
            raise M7Error("selection_invalid", "a candidate has more than one guardrail manifest")
        evaluated[seed][epoch] = {"manifest_sha256": sha, "parsed": parsed, "passed": parsed["guardrails"]["passed"]}
        guardrail_index.append({"epoch": epoch, "seed": seed, "sha256": sha})

    candidate_table = []
    traces = []
    rankings = []
    seed_records = []
    selected_set = []
    all_pass = True
    for seed in seeds:
        view = views[seed]
        ranking = view["ranking"]
        results = evaluated[seed]
        prefix = [(epoch, results[epoch]["passed"]) for epoch in ranking if epoch in results]
        if sorted(results) != sorted(ranking[: len(results)]):
            raise M7Error("selection_invalid", "the evaluated candidates are not a prefix of the sealed ranking")
        plan = guardrails.lazy_plan(ranking, prefix)
        if plan["state"] == "pending":
            raise M7Error("selection_invalid", "lazy evaluation is incomplete: a later ranked candidate must be evaluated")
        for position, epoch in enumerate(ranking[: len(results)]):
            preceding = [
                {"epoch": earlier, "manifest_sha256": results[earlier]["manifest_sha256"], "outcome": "failed"} for earlier in ranking[:position]
            ]
            if results[epoch]["parsed"]["preceding_candidates"] != preceding:
                raise M7Error("selection_invalid", "a guardrail manifest does not bind the failed earlier ranked candidates")
        trace = []
        for position, epoch in enumerate(ranking, start=1):
            if epoch in results:
                outcome = "passed" if results[epoch]["passed"] else "failed"
                trace.append(
                    {"epoch": epoch, "evaluated": True, "guardrail_manifest_sha256": results[epoch]["manifest_sha256"], "outcome": outcome, "rank": position}
                )
            else:
                trace.append({"epoch": epoch, "evaluated": False, "guardrail_manifest_sha256": None, "outcome": UNEVALUATED_OUTCOME, "rank": position})
        for epoch in common.CANDIDATE_EPOCHS:
            checkpoint = view["checkpoints"][epoch]
            candidate_table.append(
                {
                    "checkpoint_name": checkpoint["directory_name"],
                    "epoch": epoch,
                    "guardrail": (
                        {"evaluated": True, "manifest_sha256": results[epoch]["manifest_sha256"], "passed": results[epoch]["passed"]}
                        if epoch in results
                        else {"evaluated": False, "manifest_sha256": None, "passed": None}
                    ),
                    "members_sha256": dict(checkpoint["saved_hashes"]),
                    "rank": ranking.index(epoch) + 1,
                    "seed": seed,
                    "update": checkpoint["update"],
                    "validation_mse": view["mse"][epoch],
                    "weight_sha256": checkpoint["weight_sha256"],
                }
            )
        traces.append({"seed": seed, "trace": trace})
        rankings.append({"ranking_sha256": view["ranking_sha256"], "ranked_epochs": list(ranking), "rule": common.RANKING_RULE, "seed": seed})
        selected_epoch = plan["selected_epoch"]
        seed_records.append(
            {
                "lazy_state": plan["state"],
                "replicate_manifest_sha256": view["blob_sha256"],
                "seed": seed,
                "selected_epoch": selected_epoch,
                "status": "selected" if selected_epoch is not None else OUTCOME_NONE,
            }
        )
        if selected_epoch is None:
            all_pass = False
        else:
            checkpoint = view["checkpoints"][selected_epoch]
            selected_set.append(
                {
                    "checkpoint_name": checkpoint["directory_name"],
                    "epoch": selected_epoch,
                    "members_sha256": dict(checkpoint["saved_hashes"]),
                    "seed": seed,
                    "update": checkpoint["update"],
                    "validation_mse": view["mse"][selected_epoch],
                    "weight_sha256": checkpoint["weight_sha256"],
                }
            )
    candidate_table.sort(key=lambda row: (row["seed"], row["epoch"]))
    selected_set.sort(key=lambda row: row["seed"])
    guardrail_index.sort(key=lambda row: (row["seed"], row["epoch"]))
    manifest = {
        "allowed_seed_plan": dict(ALLOWED_SEED_PLAN),
        "candidate_table": candidate_table,
        "closure": dict(CLOSURE),
        "completed_seeds": seeds,
        "config_version": SCHEMA_VERSION,
        "deviation": deviation_record,
        "experiment_id": EXPERIMENT_ID,
        "guardrail_manifests": guardrail_index,
        "lazy_evaluation_traces": traces,
        "m8_allocation": _m8_allocation(seeds),
        "m8_boundary": dict(M8_BOUNDARY),
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "ref_eval_access": {"eval_opened": False, "ref_opened": False},
        "replicate_manifests": [{"seed": seed, "sha256": views[seed]["blob_sha256"]} for seed in seeds],
        "schema_version": SCHEMA_VERSION,
        "seed_records": seed_records,
        "selected_set": selected_set if all_pass else None,
        "selected_set_sha256": selected_set_sha256(selected_set) if all_pass else None,
        "selection_outcome": OUTCOME_COMPLETE if all_pass else OUTCOME_NONE,
        "validation_rankings": rankings,
    }
    validate_final_selection_manifest(manifest)
    return manifest


def _m8_allocation(seeds):
    """The frozen M8 boundary: 30,000 raw attempts in total. Recorded only; nothing generates."""
    if seeds == [43, 44]:
        return {"43": replicate.M8_TOTAL_RAW_ATTEMPTS // 2, "44": replicate.M8_TOTAL_RAW_ATTEMPTS // 2}
    return {"43": replicate.M8_TOTAL_RAW_ATTEMPTS}


def selected_set_sha256(selected_set):
    """A deterministic content hash of the selected set. It is not an authenticity mechanism."""
    return common.sha256_bytes(common.canonical_json(sorted(selected_set, key=lambda row: row["seed"])))


def final_selection_bytes(manifest):
    return common.canonical_json(manifest)


def rebuild_matches(manifest_bytes, replicate_blobs, guardrail_blobs, deviation_blob=None):
    """True when the bytes are exactly what the pure function builds from the sealed inputs.

    ``validate_final_selection_manifest`` proves internal consistency from the
    manifest alone. Only this comparison (against the sealed input bytes) shows a
    manifest is what those inputs produce.
    """
    return final_selection_bytes(build_final_selection(replicate_blobs, guardrail_blobs, deviation_blob)) == bytes(manifest_bytes)


# ------------------------------------------------------------------ validation of a final manifest


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _require_rows(value, keys, what):
    if not isinstance(value, list):
        raise M7Error("selection_invalid", what + " is not a list")
    for row in value:
        common.exact_keys(row, keys, "selection_invalid")
    return value


def _require_seed_order(rows, seeds, what):
    """One row per completed seed, in seed order, every seed a true integer (43.0 is not 43)."""
    if any(not _is_int(row["seed"]) for row in rows) or [row["seed"] for row in rows] != seeds:
        raise M7Error("selection_invalid", what + " has a duplicate, missing, extra, out-of-order or non-integer seed")
    return rows


def _require_sha(value, what, nullable=False):
    if value is None and nullable:
        return value
    if not common.is_sha256(value):
        raise M7Error("selection_invalid", what + " is not a SHA-256 digest")
    return value


def _require_int(value, what):
    if not _is_int(value):
        raise M7Error("selection_invalid", what + " is not an integer")
    return value


def _require_members(members, weight, what):
    """Every checkpoint member name and digest, with the weight member equal to the weight hash."""
    members = common.exact_keys(members, common.CHECKPOINT_MEMBERS, "selection_invalid")
    for name in common.CHECKPOINT_MEMBERS:
        _require_sha(members[name], what + " member " + name)
    if members[common.WEIGHT_MEMBER] != weight:
        raise M7Error("selection_invalid", what + " weight member does not match its weight hash")
    return members


def _ranking_record(rows, order):
    """The replicate-style ranking record, rebuilt from candidate rows. Its hash is the sealed ``ranking_sha256``."""
    return {
        "excludes_update_0": True,
        "ranked_candidates": [
            {"aggregate_mse": rows[epoch]["validation_mse"], "epoch": epoch, "rank": position, "update": rows[epoch]["update"]}
            for position, epoch in enumerate(order, start=1)
        ],
        "rule": common.RANKING_RULE,
    }


def _commit_of_checkpoint_name(name):
    if not isinstance(name, str) or len(name) <= 40 or not common.is_sha40(name[-40:]):
        raise M7Error("selection_invalid", "a checkpoint name does not end in an implementation commit")
    return name[-40:]


def validate_final_selection_manifest(manifest):
    """Re-derive every selection claim from the embedded tables. A tampered claim is refused.

    Exact key sets are enforced for the manifest and for every nested record
    (replicate and guardrail index rows, candidate-table rows and their guardrail
    blocks, ranking rows, lazy-trace containers and rows, seed records, and
    selected-set rows). Every recorded digest has the SHA-256 shape. Per seed,
    the validation ranking is recomputed from the candidate table (fixed-draw
    MSE, earlier epoch on an exact tie, update 0 excluded) and its
    ``ranking_sha256`` is recomputed over the rebuilt replicate-style ranking
    record; the lazy trace must be a prefix of that ranking that stops at the
    first pass or covers all five candidates; the seed record status and
    selected epoch follow from that trace; the guardrail index must equal
    exactly the evaluated candidate rows; and the selected-set rows (including
    every checkpoint member hash) must equal the first passing candidate's row.

    What this cannot show: the manifest alone does not contain the sealed
    replicate or guardrail manifest bytes, so it cannot prove those bytes say
    what the tables claim, and ``selected_set_sha256`` is a deterministic
    content hash, not an authenticity mechanism. ``rebuild_matches`` compares a
    manifest with the bytes the pure function builds from the sealed inputs.
    """
    manifest = common.exact_keys(manifest, MANIFEST_KEYS, "selection_invalid")
    common.reject_sequence_text(manifest)
    reject_ref_eval_derived(manifest, "the final selection manifest")
    if manifest["manifest_schema_version"] != MANIFEST_SCHEMA_VERSION or manifest["schema_version"] != SCHEMA_VERSION or manifest["config_version"] != SCHEMA_VERSION:
        raise M7Error("selection_invalid", "manifest schema drifted")
    if manifest["experiment_id"] != EXPERIMENT_ID or not _same(manifest["closure"], CLOSURE):
        raise M7Error("selection_invalid", "closure drifted: a human gate is required and M7 is not complete")
    if manifest["closure"]["human_gate_required"] is not True or manifest["closure"]["m7_complete"] is not False:
        raise M7Error("selection_invalid", "human gate or completion flag drifted")
    if not _same(manifest["ref_eval_access"], {"eval_opened": False, "ref_opened": False}):
        raise M7Error("ref_or_eval_access", "REF or EVAL access is recorded")
    if not _same(manifest["allowed_seed_plan"], ALLOWED_SEED_PLAN) or not _same(manifest["m8_boundary"], M8_BOUNDARY):
        raise M7Error("selection_invalid", "the seed plan or M8 boundary drifted")
    seeds = manifest["completed_seeds"]
    if seeds not in ([43, 44], [43]) or any(not _is_int(seed) for seed in seeds):
        raise M7Error("selection_invalid", "the completed seeds are not 43 and 44, or 43 alone")
    if (seeds == [43]) != (manifest["deviation"] is not None):
        raise M7Error("selection_invalid", "a one-seed selection requires exactly the sealed deviation record")
    if not _same(manifest["m8_allocation"], _m8_allocation(seeds)):
        raise M7Error("selection_invalid", "the M8 allocation does not follow the seed plan")

    # replicate index: exactly one row per completed seed, in seed order
    replicate_rows = _require_rows(manifest["replicate_manifests"], REPLICATE_INDEX_KEYS, "the replicate manifest index")
    _require_seed_order(replicate_rows, seeds, "the replicate manifest index")
    for row in replicate_rows:
        _require_sha(row["sha256"], "a replicate manifest digest")
    replicate_hashes = {row["seed"]: row["sha256"] for row in replicate_rows}
    if manifest["deviation"] is not None:
        validate_deviation(manifest["deviation"], None, replicate_hashes[43])

    # candidate table: exactly seeds x epochs 1..5, in order
    table = _require_rows(manifest["candidate_table"], CANDIDATE_ROW_KEYS, "the candidate table")
    for row in table:
        _require_int(row["seed"], "a candidate seed")
        _require_int(row["epoch"], "a candidate epoch")
    expected_rows = [(seed, epoch) for seed in seeds for epoch in common.CANDIDATE_EPOCHS]
    if [(row["seed"], row["epoch"]) for row in table] != expected_rows:
        raise M7Error("selection_invalid", "the candidate table has an extra, missing, duplicate or out-of-order epoch candidate")
    commits_by_seed = {}
    for row in table:
        if _require_int(row["update"], "a candidate update") != replicate.epoch_update_range(row["epoch"])[1] or row["update"] == 0:
            raise M7Error("selection_invalid", "a candidate row is not an epoch boundary; update 0 is never a candidate")
        _require_int(row["rank"], "a candidate rank")
        common.finite_decimal_string(row["validation_mse"], "selection_invalid")
        _require_sha(row["weight_sha256"], "a candidate weight hash")
        _require_members(row["members_sha256"], row["weight_sha256"], "a candidate row")
        common.assert_not_m6_weight(row["weight_sha256"])
        commit = _commit_of_checkpoint_name(row["checkpoint_name"])
        if row["checkpoint_name"] != replicate.checkpoint_child_name(row["seed"], row["epoch"], commit):
            raise M7Error("selection_invalid", "a checkpoint name is not the name of its seed, epoch and update")
        previous = commits_by_seed.setdefault(row["seed"], commit)
        if previous != commit:
            raise M7Error("selection_invalid", "a seed's checkpoints do not share that seed's training implementation commit")
        guardrail = common.exact_keys(row["guardrail"], CANDIDATE_GUARDRAIL_KEYS, "selection_invalid")
        if guardrail["evaluated"] is True:
            _require_sha(guardrail["manifest_sha256"], "a candidate guardrail manifest digest")
            if not isinstance(guardrail["passed"], bool):
                raise M7Error("selection_invalid", "an evaluated candidate has no boolean outcome")
        elif guardrail["evaluated"] is False:
            if guardrail["manifest_sha256"] is not None or guardrail["passed"] is not None:
                raise M7Error("selection_invalid", "an unevaluated candidate carries a guardrail record")
        else:
            raise M7Error("selection_invalid", "a candidate guardrail block has a non-boolean evaluated flag")
    for seed in seeds:
        seed_weights = [row["weight_sha256"] for row in table if row["seed"] == seed]
        if len(set(seed_weights)) != len(seed_weights):
            raise M7Error("selection_invalid", "two candidate epochs of one seed carry identical weights")

    rankings = _require_rows(manifest["validation_rankings"], RANKING_ROW_KEYS, "the validation rankings")
    _require_seed_order(rankings, seeds, "the validation rankings")
    containers = _require_rows(manifest["lazy_evaluation_traces"], TRACE_CONTAINER_KEYS, "the lazy traces")
    _require_seed_order(containers, seeds, "the lazy traces")
    records = _require_rows(manifest["seed_records"], SEED_RECORD_KEYS, "the seed records")
    _require_seed_order(records, seeds, "the seed records")

    # guardrail index: strictly ordered, unique, and equal to the evaluated candidate rows
    index_rows = _require_rows(manifest["guardrail_manifests"], GUARDRAIL_INDEX_KEYS, "the guardrail manifest index")
    for item in index_rows:
        _require_int(item["seed"], "a guardrail index seed")
        _require_int(item["epoch"], "a guardrail index epoch")
        _require_sha(item["sha256"], "a guardrail manifest digest")
    keys = [(item["seed"], item["epoch"]) for item in index_rows]
    if keys != sorted(set(keys)):
        raise M7Error("selection_invalid", "the guardrail manifest index has a duplicate or out-of-order entry")
    evaluated_rows = [
        {"epoch": row["epoch"], "seed": row["seed"], "sha256": row["guardrail"]["manifest_sha256"]} for row in table if row["guardrail"]["evaluated"] is True
    ]
    if index_rows != evaluated_rows:
        raise M7Error("selection_invalid", "the guardrail manifest index is not exactly the evaluated candidate rows")
    if len({item["sha256"] for item in index_rows}) != len(index_rows):
        raise M7Error("selection_invalid", "two evaluated candidates share one guardrail manifest digest")
    guardrail_hashes = {(item["seed"], item["epoch"]): item["sha256"] for item in index_rows}

    selected = []
    all_pass = True
    for ranking_row, container, record in zip(rankings, containers, records):
        seed = ranking_row["seed"]
        rows = {row["epoch"]: row for row in table if row["seed"] == seed}
        order = common.rank_validation_candidates({epoch: row["validation_mse"] for epoch, row in rows.items()})
        if not isinstance(ranking_row["ranked_epochs"], list) or any(not _is_int(epoch) for epoch in ranking_row["ranked_epochs"]):
            raise M7Error("selection_invalid", "a sealed ranking lists a non-integer epoch")
        if ranking_row["ranked_epochs"] != order or ranking_row["rule"] != common.RANKING_RULE:
            raise M7Error("selection_invalid", "a sealed ranking does not follow fixed-draw validation MSE then earlier epoch")
        _require_sha(ranking_row["ranking_sha256"], "a ranking digest")
        if ranking_row["ranking_sha256"] != _ranking_sha256(_ranking_record(rows, order)):
            raise M7Error("selection_invalid", "a ranking digest is not the digest of the ranking rebuilt from the candidate table")
        if [rows[epoch]["rank"] for epoch in order] != list(range(1, 6)):
            raise M7Error("selection_invalid", "candidate ranks do not follow the ranking")
        trace = _require_rows(container["trace"], TRACE_ROW_KEYS, "a lazy trace")
        for item in trace:
            _require_int(item["epoch"], "a lazy trace epoch")
            _require_int(item["rank"], "a lazy trace rank")
        if [item["epoch"] for item in trace] != order or [item["rank"] for item in trace] != list(range(1, 6)):
            raise M7Error("selection_invalid", "a lazy trace is not in ranking order")
        evaluated_pairs = []
        stop_seen = False
        for item in trace:
            row = rows[item["epoch"]]
            if item["evaluated"] is True:
                if stop_seen:
                    raise M7Error("selection_invalid", "a candidate was evaluated after the first passing candidate or a gap")
                _require_sha(item["guardrail_manifest_sha256"], "a lazy trace digest")
                if item["outcome"] not in ("passed", "failed") or row["guardrail"] != {
                    "evaluated": True,
                    "manifest_sha256": item["guardrail_manifest_sha256"],
                    "passed": item["outcome"] == "passed",
                }:
                    raise M7Error("selection_invalid", "a lazy trace row disagrees with the candidate table")
                if guardrail_hashes.get((seed, item["epoch"])) != item["guardrail_manifest_sha256"]:
                    raise M7Error("selection_invalid", "a lazy trace row names an unlisted guardrail manifest")
                evaluated_pairs.append((item["epoch"], item["outcome"] == "passed"))
            elif item["evaluated"] is False:
                stop_seen = True
                if (
                    item["guardrail_manifest_sha256"] is not None
                    or item["outcome"] != UNEVALUATED_OUTCOME
                    or row["guardrail"] != {"evaluated": False, "manifest_sha256": None, "passed": None}
                ):
                    raise M7Error("selection_invalid", "an unevaluated candidate carries a guardrail record")
            else:
                raise M7Error("selection_invalid", "a lazy trace row has a non-boolean evaluated flag")
        plan = guardrails.lazy_plan(order, evaluated_pairs)
        if plan["state"] == "pending":
            raise M7Error("selection_invalid", "lazy evaluation is incomplete")
        if record["lazy_state"] != plan["state"] or record["selected_epoch"] != plan["selected_epoch"]:
            raise M7Error("selection_invalid", "a seed record disagrees with its lazy trace")
        if record["selected_epoch"] is not None and (not _is_int(record["selected_epoch"]) or record["selected_epoch"] not in common.CANDIDATE_EPOCHS):
            raise M7Error("selection_invalid", "a seed record selects something other than candidate epochs 1 through 5")
        _require_sha(record["replicate_manifest_sha256"], "a seed record replicate digest")
        if record["replicate_manifest_sha256"] != replicate_hashes[seed]:
            raise M7Error("selection_invalid", "a seed record names another replicate manifest than the index")
        if plan["selected_epoch"] is None:
            # All five candidates were evaluated and every one failed.
            if len(evaluated_pairs) != len(common.CANDIDATE_EPOCHS) or any(passed for _epoch, passed in evaluated_pairs) or record["status"] != OUTCOME_NONE:
                raise M7Error("selection_invalid", "a seed has no eligible checkpoint only when all five candidates were evaluated and failed")
            all_pass = False
        else:
            # The first passing candidate: every earlier evaluated one failed and it passed.
            if record["status"] != "selected" or evaluated_pairs[-1] != (plan["selected_epoch"], True) or any(passed for _epoch, passed in evaluated_pairs[:-1]):
                raise M7Error("selection_invalid", "a seed record names a candidate that is not the first passing evaluated candidate")
            row = rows[plan["selected_epoch"]]
            if row["guardrail"]["evaluated"] is not True or row["guardrail"]["passed"] is not True:
                raise M7Error("selection_invalid", "the selected candidate is not an evaluated, passing candidate")
            selected.append({key: (dict(row[key]) if key == "members_sha256" else row[key]) for key in SELECTED_ROW_KEYS})
    if all_pass:
        if manifest["selection_outcome"] != OUTCOME_COMPLETE or manifest["selected_set"] is None:
            raise M7Error("selection_invalid", "the outcome must be a complete selected set")
        selected_rows = _require_rows(manifest["selected_set"], SELECTED_ROW_KEYS, "the selected set")
        for item in selected_rows:
            _require_members(item["members_sha256"], item["weight_sha256"], "a selected row")
        # The whole row, including every checkpoint member hash, must equal the candidate row.
        if not _same(selected_rows, selected):
            raise M7Error("selection_invalid", "the selected set is not the first passing candidate of each seed with its checkpoint member hashes")
        for item in selected_rows:
            common.assert_not_m6_weight(item["weight_sha256"])
        _require_sha(manifest["selected_set_sha256"], "the selected-set digest")
        if manifest["selected_set_sha256"] != selected_set_sha256(selected_rows):
            raise M7Error("selection_invalid", "the selected-set hash does not match the selected set")
    else:
        if manifest["selection_outcome"] != OUTCOME_NONE or manifest["selected_set"] is not None or manifest["selected_set_sha256"] is not None:
            raise M7Error("selection_invalid", "a seed with no eligible checkpoint leaves no selected set")
    return True


# ------------------------------------------------------------------ authorisation entry


def assert_authorisation_id(value):
    """A final-selection id. It never matches a replicate or candidate id, so ids cannot be confused."""
    if (
        not isinstance(value, str)
        or len(value) > AUTHORISATION_ID_MAXIMUM_LENGTH
        or AUTHORISATION_ID_PATTERN.fullmatch(value) is None
        or replicate.AUTHORISATION_ID_PATTERN.fullmatch(value) is not None
    ):
        raise M7Error("cli_argument_rejected", "the authorisation id is not an m7 final-selection id")
    return value


def assert_manifest_path(path, kind, seed, epoch, output_directory, run_root=None):
    """Judge one bound manifest path on its text alone. Nothing is opened.

    The only permitted location is ``<run root>/<one directory>/<manifest name>``,
    where the directory name is the sealed id of that seed (replicate) or that
    seed and epoch (guardrail). REF and EVAL, obsolete repository-local data, M6
    evidence and checkpoint paths, any deeper path (a checkpoint, a weight or a
    biological file), a non-normalised spelling and the output directory itself are refused.
    """
    run_root = common.RUN_ROOT if run_root is None else run_root
    if not isinstance(path, str) or path == "" or "\x00" in path:
        raise M7Error("authorisation_scope_invalid", "a bound manifest path is not text")
    if common.normalise_path_text(path) != path or os.path.normpath(path) != path or not path.startswith("/"):
        raise M7Error("authorisation_scope_invalid", "a bound manifest path is not an absolute normalised path")
    if common.path_is_ref_or_eval(path):
        raise M7Error("ref_or_eval_access", "a bound manifest path names REF or EVAL")
    if common.path_is_obsolete_repository_local(path):
        raise M7Error("unexpected_biological_path_or_role", "a bound manifest path is obsolete repository-local data")
    if common.M6_CHECKPOINT_NAME_PATTERN.search(path) is not None or common.M6_EVIDENCE_NAME_PATTERN.search(path) is not None:
        raise M7Error("m6_checkpoint_forbidden", "a bound manifest path is M6 evidence or an M6 checkpoint")
    prefix = run_root.rstrip("/") + "/"
    if not path.startswith(prefix):
        raise M7Error("sibling_evidence_access", "a bound manifest path is outside the M7 run root")
    parts = path[len(prefix):].split("/")
    expected = replicate.SUCCESS_MANIFEST_NAME if kind == "replicate" else guardrails.SUCCESS_MANIFEST_NAME
    if len(parts) != 2 or parts[1] != expected:
        raise M7Error("authorisation_scope_invalid", "a bound manifest path is not exactly one sealed manifest directly inside a run directory")
    name = parts[0]
    candidate = guardrails.AUTHORISATION_ID_PATTERN.fullmatch(name)
    if kind == "replicate":
        matched = replicate.AUTHORISATION_ID_PATTERN.fullmatch(name)
        if matched is None or candidate is not None or int(matched.group(1)) != seed:
            raise M7Error("sibling_evidence_access", "a bound replicate manifest is not in a replicate directory of its seed")
    else:
        if candidate is None or (int(candidate.group(1)), int(candidate.group(2))) != (seed, epoch):
            raise M7Error("sibling_evidence_access", "a bound guardrail manifest is not in the directory of its seed and epoch")
    if os.path.join(run_root, name) == output_directory:
        raise M7Error("authorisation_scope_invalid", "a bound manifest lies in the output directory")
    return path


def _assert_input_row(row, keys, kind, run_root, output_directory):
    row = common.exact_keys(row, keys, "authorisation_shape_invalid")
    seed = replicate.assert_seed(row["seed"])
    epoch = None
    if kind == "guardrail":
        epoch = row["epoch"]
        if not common.is_candidate_epoch(epoch):
            raise M7Error("selection_invalid", "a guardrail manifest epoch is not 1 through 5; update 0 is never a candidate")
    assert_manifest_path(row["path"], kind, seed, epoch, output_directory, run_root)
    if isinstance(row["bytes"], bool) or not isinstance(row["bytes"], int) or row["bytes"] <= 0:
        raise M7Error("authorisation_field_missing", "a bound manifest byte count is missing")
    if not common.is_sha256(row["sha256"]):
        raise M7Error("authorisation_field_missing", "a bound manifest SHA-256 is missing")
    return row


def assert_active_entry(entry, run_root=None):
    """Exact schema of the one single-use final-selection entry. Judged on text and structure alone."""
    run_root = common.RUN_ROOT if run_root is None else run_root
    entry = common.exact_keys(entry, ACTIVE_ENTRY_KEYS, "authorisation_shape_invalid")
    if common.contains_key(entry, "authorization_commit"):
        raise M7Error("authorisation_commit_invalid", "tracked authorisation must not store its own commit")
    if entry["activation_status"] != replicate.ACTIVE_ACTIVATION or entry["consumed"] is not False:
        raise M7Error("authorisation_inactive", "authorisation is not active and unconsumed")
    if entry["single_use"] is not True or entry["reuse_permitted"] is not False:
        raise M7Error("authorization_reuse", "authorisation is not single-use")
    identifier = assert_authorisation_id(entry["authorisation_id"])
    parent = entry["authorization_parent_commit"]
    executing = entry["executing_implementation_commit"]
    if not common.is_sha40(parent) or parent != executing:
        raise M7Error("authorisation_commit_invalid", "parent commit and executing implementation commit differ")
    if entry["phase"] != ACTIVE_PHASE or entry["scope"] != ACTIVE_SCOPE:
        raise M7Error("authorisation_scope_invalid", "phase or scope is not the final selection")
    if list(entry["permitted_roles"]) != list(ACTIVE_ROLES):
        raise M7Error("authorisation_scope_invalid", "permitted roles drifted")
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
    if not common.is_sha256(entry["implementation_config_sha256"]):
        raise M7Error("provenance_mismatch", "implementation configuration hash is missing")
    hashes = common.exact_keys(entry["implementation_file_hashes"], IMPLEMENTATION_FILE_PATHS, "provenance_mismatch")
    if any(not common.is_sha256(value) for value in hashes.values()):
        raise M7Error("provenance_mismatch", "an implementation file hash is missing")

    replicate_rows = entry["replicate_manifests"]
    if not isinstance(replicate_rows, list) or not 1 <= len(replicate_rows) <= 2:
        raise M7Error("authorisation_shape_invalid", "the entry binds one or two replicate manifests")
    for row in replicate_rows:
        _assert_input_row(row, REPLICATE_INPUT_KEYS, "replicate", run_root, entry["output_directory"])
    seeds = [row["seed"] for row in replicate_rows]
    if seeds not in ([43], [43, 44]):
        raise M7Error("selection_invalid", "the bound seeds are not 43 and 44, or 43 alone (seed 44 alone and duplicates are refused)")
    guardrail_rows = entry["guardrail_manifests"]
    if not isinstance(guardrail_rows, list) or not 1 <= len(guardrail_rows) <= 5 * len(seeds):
        raise M7Error("authorisation_shape_invalid", "the entry binds every evaluated guardrail manifest")
    for row in guardrail_rows:
        _assert_input_row(row, GUARDRAIL_INPUT_KEYS, "guardrail", run_root, entry["output_directory"])
        if row["seed"] not in seeds:
            raise M7Error("selection_invalid", "a guardrail manifest is bound for a seed without a bound replicate manifest")
    pairs = [(row["seed"], row["epoch"]) for row in guardrail_rows]
    if pairs != sorted(set(pairs)):
        raise M7Error("selection_invalid", "the guardrail manifests are duplicated or not in (seed, epoch) order")
    every = replicate_rows + guardrail_rows
    if len({row["path"] for row in every}) != len(every) or len({row["sha256"] for row in every}) != len(every):
        raise M7Error("selection_invalid", "two bound manifests share a path or a digest")

    deviation = entry["deviation"]
    if seeds == [43, 44]:
        if deviation is not None:
            raise M7Error("selection_invalid", "a two-seed selection carries no deviation record")
    else:
        if deviation is None:
            raise M7Error("selection_invalid", "seed 43 alone requires the sealed operational deviation record")
        validate_deviation(deviation, None, replicate_rows[0]["sha256"])
    return entry


def assert_active_configuration(config, run_root=None):
    """Validate an active document and return its single entry."""
    run_root = common.RUN_ROOT if run_root is None else run_root
    config = common.exact_keys(config, CONFIGURATION_ROOT_KEYS, "authorisation_shape_invalid")
    if config.get("document_status") != ACTIVE_DOCUMENT_STATUS or config.get("consumable_by_executable_workflow") is not True:
        raise M7Error("authorisation_inactive", "active document flags drifted")
    if common.contains_key(config, "authorization_commit"):
        raise M7Error("authorisation_commit_invalid", "tracked configuration must not store authorization_commit")
    if config.get("schema_version") != SCHEMA_VERSION or config.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION or config.get("experiment_id") != EXPERIMENT_ID:
        raise M7Error("authorisation_scope_invalid", "schema or experiment identity drifted")
    if config.get("rnagenesis_commit") != common.RNAGENESIS_COMMIT or config.get("rnagenesis_branch") != common.RNAGENESIS_BRANCH:
        raise M7Error("provenance_mismatch", "RNAGenesis pin drifted")
    if config.get("created_against_mres_commit") != common.MRES_BASE_COMMIT:
        raise M7Error("provenance_mismatch", "MRes base commit drifted")
    execution = common.exact_keys(config.get("execution"), replicate.EXECUTION_KEYS, "authorisation_shape_invalid")
    if not _same(execution, ACTIVE_EXECUTION):
        raise M7Error("authorisation_inactive", "execution flags are not exactly authorised, with no biological path and no GPU")
    for name, expected in expected_static_sections().items():
        if not _same(config.get(name), expected):
            raise M7Error("authorisation_scope_invalid", "static section drifted: " + name)
    if not _same(config.get("authorisation_schema"), authorisation_schema()):
        raise M7Error("authorisation_scope_invalid", "authorisation schema drifted")
    entries = config.get("authorisation_entries")
    if not isinstance(entries, list) or len(entries) != 1:
        raise M7Error("authorisation_shape_invalid", "an active document carries exactly one entry")
    return assert_active_entry(entries[0], run_root)


# ------------------------------------------------------------------ repository binding


def assert_selection_delta(implementation_config, authorization_config):
    """The authorisation commit may change exactly the permitted activation paths of this configuration."""
    paths = replicate.differing_paths(implementation_config, authorization_config)
    unexpected = [path for path in paths if path not in PERMITTED_ACTIVATION_PATHS]
    if unexpected:
        raise M7Error("authorisation_delta_invalid", "authorization commit changes " + unexpected[0])
    if not paths:
        raise M7Error("authorisation_delta_invalid", "authorization commit does not activate anything")
    return paths


def assert_repository_binding(config, entry, observation):
    """The replicate repository binding with this configuration as the only permitted changed file.

    The shared binding checks the branch, remote, clean tracked tree and index,
    the single parent, the implementation and configuration hashes, and the
    RNAGenesis pins. This stage then applies its own, stricter activation-path set.
    """
    head = replicate.assert_repository_binding(config, entry, observation, PERMITTED_AUTHORIZATION_FILES)
    assert_selection_delta(observation.get("implementation_config"), config)
    return head


def _default_read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _default_git(repo, args):
    return common.run_git(repo, args)


def _default_git_blob(spec):
    return common.run_git_bytes(MRES_ROOT, ["show", spec])


class SelectionDependencies(object):
    """Every outside effect of the launcher, injectable for CPU/mock tests.

    The defaults are the real implementations: file reads, ``lstat``, the
    absolute fixed ``git``, and the running interpreter. No GPU tool is
    reachable from this stage.
    """

    def __init__(self, read_bytes=None, lstat=None, listdir=None, realpath=None, environ=None, git=None, git_blob=None, executable=None):
        self.read_bytes = read_bytes or _default_read_bytes
        self.lstat = lstat or os.lstat
        self.listdir = listdir or os.listdir
        self.realpath = realpath or os.path.realpath
        self.environ = os.environ if environ is None else environ
        self.git = git or _default_git
        self.git_blob = git_blob or _default_git_blob
        self.executable = sys.executable if executable is None else executable


def live_repository_observation(config, entry, deps):
    """Repository, parent-commit and file-hash observation for the entry (standard library and git only)."""
    git = deps.git
    head = git(MRES_ROOT, ["rev-parse", "HEAD"]).strip()
    parents = [line.strip() for line in git(MRES_ROOT, ["rev-parse", "HEAD^@"]).splitlines() if line.strip()]
    observation = {
        "changed_files": [],
        "file_sha256_at_parent": {},
        "file_sha256_working_tree": {},
        "implementation_config": {},
        "implementation_config_bytes": b"",
        "mres_branch": git(MRES_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
        "mres_head": head,
        "mres_origin_main": git(MRES_ROOT, ["rev-parse", "origin/main"]).strip(),
        "mres_parents": parents,
        "mres_porcelain": git(MRES_ROOT, ["status", "--porcelain=v1", "--untracked-files=all"]),
        "rnagenesis_branch": git(common.RNAGENESIS_ROOT, ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
        "rnagenesis_directory_porcelain": git(common.RNAGENESIS_ROOT, ["status", "--porcelain=v1"]),
        "rnagenesis_file_porcelain": git(common.RNAGENESIS_ROOT, ["status", "--porcelain=v1", "--untracked-files=all"]),
        "rnagenesis_head": git(common.RNAGENESIS_ROOT, ["rev-parse", "HEAD"]).strip(),
    }
    if len(parents) != 1:
        return observation
    parent = parents[0]
    raw = bytes(deps.git_blob(parent + ":" + CONFIG_RELATIVE))
    observation["implementation_config_bytes"] = raw
    observation["implementation_config"] = common.load_config_bytes(raw)
    observation["changed_files"] = [line.strip() for line in git(MRES_ROOT, ["diff", "--name-only", parent, "HEAD"]).splitlines() if line.strip()]
    for relative in IMPLEMENTATION_FILE_PATHS:
        observation["file_sha256_at_parent"][relative] = common.sha256_bytes(bytes(deps.git_blob(parent + ":" + relative)))
        observation["file_sha256_working_tree"][relative] = common.sha256_bytes(bytes(deps.read_bytes(os.path.join(MRES_ROOT, relative))))
    return observation


def assert_launch_interpreter(deps):
    """The launcher must itself run under the pinned interpreter (compared by resolved path; nothing is executed)."""
    if deps.realpath(deps.executable) != deps.realpath(common.PINNED_PYTHON):
        raise M7Error("interpreter_rejected", "the final selection must run under the pinned interpreter")
    return True


# ------------------------------------------------------------------ bound inputs


def _evidence_mismatch(operation):
    """Inspection failures of a bound input are all evidence mismatches."""
    try:
        return operation()
    except M7Error as exc:
        if exc.code in ("asset_inspection_unsafe", "checkpoint_ancestry_unsafe", "filesystem_error"):
            raise M7Error("authorisation_evidence_mismatch", "a bound manifest failed inspection: " + exc.detail) from None
        raise


def _read_bound_manifest(row, kind, entry, deps, run_root):
    assert_manifest_path(row["path"], kind, row["seed"], row.get("epoch"), entry["output_directory"], run_root)
    blob, _signature = _evidence_mismatch(
        lambda: common.read_regular_file(row["path"], deps.lstat, deps.read_bytes, True, row["bytes"], row["sha256"])
    )
    try:
        parsed = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise M7Error("authorisation_evidence_mismatch", "a bound manifest is not JSON")
    if not isinstance(parsed, dict) or common.canonical_json(parsed) != blob:
        raise M7Error("authorisation_evidence_mismatch", "a bound manifest is not canonical JSON")
    directory = os.path.basename(os.path.dirname(row["path"]))
    if kind == "replicate":
        common.exact_keys(parsed, replicate.MANIFEST_KEYS, "authorisation_evidence_mismatch")
        if parsed["seed"] != row["seed"] or parsed["run_id"] != directory:
            raise M7Error("sibling_evidence_access", "a bound replicate manifest belongs to another seed or directory")
    else:
        common.exact_keys(parsed, guardrails.MANIFEST_KEYS, "authorisation_evidence_mismatch")
        candidate = parsed["candidate"]
        if not isinstance(candidate, dict) or (candidate.get("seed"), candidate.get("epoch")) != (row["seed"], row["epoch"]) or parsed["run_id"] != directory:
            raise M7Error("sibling_evidence_access", "a bound guardrail manifest belongs to another seed, epoch or directory")
    return blob


def read_bound_inputs(entry, deps, run_root=None):
    """Read exactly the bound manifests through the symlink-safe, single-link inspection.

    Every path is judged on its text before the first file is touched. Each file
    must be a regular, non-symlink, single-link file beneath real directories,
    unchanged across the read, with the bound byte count and SHA-256, canonical
    JSON, and the exact schema of its kind. Nothing else is opened.
    """
    run_root = common.RUN_ROOT if run_root is None else run_root
    for row in entry["replicate_manifests"]:
        assert_manifest_path(row["path"], "replicate", row["seed"], None, entry["output_directory"], run_root)
    for row in entry["guardrail_manifests"]:
        assert_manifest_path(row["path"], "guardrail", row["seed"], row["epoch"], entry["output_directory"], run_root)
    replicate_blobs = [_read_bound_manifest(row, "replicate", entry, deps, run_root) for row in entry["replicate_manifests"]]
    guardrail_blobs = [_read_bound_manifest(row, "guardrail", entry, deps, run_root) for row in entry["guardrail_manifests"]]
    deviation_blob = None if entry["deviation"] is None else common.canonical_json(entry["deviation"])
    return {"deviation": deviation_blob, "guardrails": guardrail_blobs, "replicates": replicate_blobs}


def build_from_inputs(inputs):
    return build_final_selection(inputs["replicates"], inputs["guardrails"], inputs["deviation"])


def assert_output_available(entry, deps, run_root=None):
    """The bound output must be a new direct child of the run root beneath real directories."""
    run_root = common.RUN_ROOT if run_root is None else run_root
    directory = entry["output_directory"]
    common.assert_output_directory_shape(directory, run_root)
    common.assert_no_symlink_ancestry(os.path.dirname(directory), deps.lstat, must_exist=True, code="execution_not_authorised")
    try:
        deps.lstat(directory)
    except FileNotFoundError:
        return True
    raise M7Error("authorization_reuse", "the bound output directory already exists")


def assert_no_prior_selection(entry, deps, run_root=None):
    """Refuse a second final selection while another sealed one exists under the run root."""
    run_root = common.RUN_ROOT if run_root is None else run_root
    try:
        names = sorted(deps.listdir(run_root))
    except FileNotFoundError:
        return True
    for name in names:
        if (
            AUTHORISATION_ID_PATTERN.fullmatch(name) is None
            or replicate.AUTHORISATION_ID_PATTERN.fullmatch(name) is not None
            or name == os.path.basename(entry["output_directory"])
        ):
            continue
        try:
            deps.lstat(os.path.join(run_root, name, SUCCESS_MANIFEST_NAME))
        except FileNotFoundError:
            continue
        raise M7Error("authorization_reuse", "a sealed final selection already exists; a retry needs a new id and no earlier success")
    return True


# ------------------------------------------------------------------ consumption and execution


def run_selection(entry, inputs, run_root=None, progress=None, writer=None):
    """Consume the bound directory, build, validate and atomically write the selection.

    Every ``BaseException`` after the directory exists becomes the message-safe
    failure record; ``KeyboardInterrupt`` and ``SystemExit`` are recorded and then
    re-raised unchanged.
    """
    run_root = common.RUN_ROOT if run_root is None else run_root
    directory = entry["output_directory"]
    progress = common.new_progress(None, "final_selection") if progress is None else progress
    payload = {
        "authorisation_id": entry["authorisation_id"],
        "authorization_commit": entry["authorization_commit"],
        "authorization_parent_commit": entry["authorization_parent_commit"],
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
        if getattr(exc, "directory_created", False) is not True:
            raise
        error = common.record_consumed_failure(directory, exc, context, progress, SUCCESS_MANIFEST_NAME)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise error from None
    try:
        progress["stage"] = "selection_build"
        manifest = build_from_inputs(inputs)
        progress["stage"] = "selection_validation"
        validate_final_selection_manifest(manifest)
        progress["stage"] = "manifest_write"
        (writer or common.write_atomic_json)(directory, SUCCESS_MANIFEST_NAME, manifest)
        return manifest
    except BaseException as exc:
        error = common.record_consumed_failure(directory, exc, context, progress, SUCCESS_MANIFEST_NAME)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise error from None


def launch_authorised_selection(authorisation_id, run_root=None, deps=None, config_bytes=None, observation=None, progress=None, writer=None):
    """Resolve one authorisation id to the one entry, validate everything, consume, and select.

    The id is the only input. With the checked-in inactive configuration this
    refuses with ``execution_not_authorised`` after reading only that file: the
    environment, git, the run root, any manifest, RNAGenesis and the output path
    are not touched. For an active entry the order is: exact schema (including
    every bound path's text), the environment, the fixed PATH, the interpreter,
    the repository (branch, clean tree and index, remote, single parent,
    configuration-only delta, file hashes), the bound manifests, a dry-run build
    of the selection, the output path and ancestry, and only then consumption.
    """
    deps = SelectionDependencies() if deps is None else deps
    root = common.RUN_ROOT if run_root is None else run_root
    assert_authorisation_id(authorisation_id)
    if config_bytes is None:
        config_bytes = bytes(deps.read_bytes(CONFIG_PATH))
    config = common.load_config_bytes(config_bytes)
    if classify_configuration(config) == "inactive":
        assert_inactive_text(bytes(config_bytes).decode("utf-8"))
        reject_inactive_before_execution(config)
    entry = assert_active_configuration(config, root)
    if entry["authorisation_id"] != authorisation_id:
        raise M7Error("authorisation_field_missing", "no single entry carries that authorisation id")
    parent = deps.environ
    common.assert_parent_environment(dict(parent))
    common.pin_process_path(parent)
    assert_launch_interpreter(deps)
    if observation is None:
        observation = live_repository_observation(config, entry, deps)
    head = assert_repository_binding(config, entry, observation)
    inputs = read_bound_inputs(entry, deps, root)
    build_from_inputs(inputs)
    assert_output_available(entry, deps, root)
    assert_no_prior_selection(entry, deps, root)
    authorised = dict(entry)
    authorised["authorization_commit"] = head
    return run_selection(authorised, inputs, root, progress, writer)


# ------------------------------------------------------------------ entry point

HELP_TEXT = """\
M7 final-selection stage (CPU-only).

The checked-in configuration is not executable. This entry point accepts only
--help, --schema and --authorisation-id <id>. The last reads only the tracked
configuration and refuses (execution_not_authorised) while it is inactive,
before the environment, git, the run root, any manifest, RNAGenesis or an
output path is inspected. It accepts no manifest path, seed, epoch, checkpoint,
output path or scientific parameter. A later authorisation-only commit that
changes nothing but the final-selection configuration may bind one single-use
entry; the bound sealed manifests are then the only files it reads.
"""


def schema_document():
    return {
        "allowed_seed_plan": dict(ALLOWED_SEED_PLAN),
        "authorisation_schema": authorisation_schema(),
        "deviation_keys": sorted(DEVIATION_KEYS),
        "document_status": DOCUMENT_STATUS,
        "entry_keys": list(ACTIVE_ENTRY_KEYS),
        "manifest_keys": sorted(MANIFEST_KEYS),
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "nested_keys": {name: list(keys) for name, keys in NESTED_KEY_SETS.items()},
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
        launch_authorised_selection(arguments[1])
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

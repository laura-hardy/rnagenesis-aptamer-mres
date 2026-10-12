#!/usr/bin/env python3
"""M9B-4 synthetic-only manual-run provenance and target-configuration checks.

The checkers accept a caller-supplied object or UTF-8 JSON bytes. They record
whether a target configuration and a manual AptaRank run are complete. They do
not open a structure file, a target-selection directory, a production ledger,
or AptaRank. Deployment identity, the effective preset, and live export
behaviour stay unresolved until M9C.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import sys

PACKAGE_ID = "M9B-4"
SCHEMA_VERSION = "m9b-aptarank-manual-run-provenance-v1"
STATUS = "DEFINED_SYNTHETIC_ONLY_MANUAL_RUN_UNRESOLVED"
STAGE = "M9B-4"
CONTRACT_RELATIVE = "config/modelling/aptarank_manual_run_contract.json"
CONTRACT_SHA256 = "f1ed83b155c787c51e3d23198db1e5bc4a72c28e0c2a0adc5675b294c0f93125"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
PREPARATION_CONTRACT_RELATIVE = "config/modelling/aptarank_candidate_preparation_contract.json"
PREPARATION_CONTRACT_SHA256 = "3bcfbdf14cd7e777a0b2746f91d0335ba4876195f5012610157e5aa23e083096"
PREPARATION_MODULE_RELATIVE = "scripts/modelling/aptarank_candidate_preparation.py"
PREPARATION_MODULE_SHA256 = "a4f5b047f2803e775d9521c226287487412495055446e192681957c3d42879ca"
PARSER_MODULE_RELATIVE = "scripts/modelling/generator_eval_parser.py"
PARSER_MODULE_SHA256 = "4a59ff8e557ee1948410c7f705a9c3772fe2570d4255b0d2185acee99137eaa2"
TARGET_SCHEMA = "m9b-target-configuration-v1"
RUN_SCHEMA = "m9b-manual-run-v1"
SELECTION_STATUS = "completed_independently_before_m9b"
SITE_METHODS = ("selected_residues", "frozen_site_rule")
RUN_STATES = ("prepared", "completed")
RESIDUE_PATTERN = r"^[1-9][0-9]{0,4}[A-Z]?$"
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
CHAIN_PATTERN = r"^[A-Za-z0-9]{1,4}$"
TIMESTAMP_PATTERN = (
    r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])"
    r"T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)
RESIDUE_TEXT = re.compile(RESIDUE_PATTERN)
IDENTIFIER_TEXT = re.compile(IDENTIFIER_PATTERN)
CHAIN_TEXT = re.compile(CHAIN_PATTERN)
TIMESTAMP_TEXT = re.compile(TIMESTAMP_PATTERN)
TARGET_KEYS = (
    "schema_version",
    "configuration_id",
    "target_id",
    "display_name",
    "selection_status",
    "structure_id",
    "chain_id",
    "binding_mode",
    "site_definition_method",
    "selected_site_residues",
    "frozen_site_rule",
    "structure_file_sha256",
    "target_selection_record_sha256",
    "notes",
)
PREPARED_KEYS = (
    "schema_version",
    "run_id",
    "state",
    "operator",
    "target_configuration_sha256",
    "preparation_manifest_sha256",
    "candidate_upload_sha256",
    "private_membership_key_sha256",
    "reference_file_sha256",
    "expected_candidate_count",
    "deployment_id",
    "requested_preset",
    "effective_settings",
    "warnings",
    "parent_run_id",
    "rerun_reason",
)
COMPLETED_EXTRA_KEYS = (
    "started_at",
    "completed_at",
    "exported_count",
    "missing_count",
    "rejected_count",
    "failed_count",
    "raw_export_sha256",
    "run_artefact_sha256",
)
COMPLETED_KEYS = PREPARED_KEYS + COMPLETED_EXTRA_KEYS
COUNT_FIELDS = ("exported_count", "missing_count", "rejected_count", "failed_count")
EFFECTIVE_SETTINGS_KEYS = ("effective_preset", "live_export_behavior")
PLAN_KEYS = ("path", "version", "revision_date", "sha256")
PREPARATION_PIN_KEYS = ("path", "package_id", "schema_version", "sha256")
MODULE_PIN_KEYS = ("role", "path", "sha256")
TARGET_CONTRACT_KEYS = (
    "schema_version",
    "keys",
    "selection_status",
    "site_definition_methods",
    "residue_pattern",
    "duplicate_residues",
    "structure_file_inspected",
    "biological_choice_judged",
    "filesystem_paths",
)
MANUAL_CONTRACT_KEYS = (
    "schema_version",
    "states",
    "prepared_keys",
    "completed_additional_keys",
    "completed_counts",
    "count_sum_equals_expected",
    "reasons_invented",
    "timestamp_pattern",
    "run_artefact_sha256",
    "raw_export_sha256",
    "rerun",
    "effective_settings",
    "deployment_inferred",
    "requested_preset_inferred",
    "live_export_behavior",
)
RERUN_KEYS = ("parent_requires_nonempty_reason", "first_run_reason")
EFFECTIVE_CONTRACT_KEYS = ("keys", "effective_preset", "live_export_behavior", "resolved_in_m9b")
BINDING_CONTRACT_KEYS = (
    "inputs",
    "candidate_upload_hash_matches_manifest",
    "private_membership_key_hash_matches_manifest",
    "manifest_pinned_to_corrected_m9b2_contract",
    "manual_run_contains_same_three_hashes",
    "target_record_bytes_match_manual_run_hash",
    "sampling_duplicated",
    "export_validation_duplicated",
    "filesystem_paths",
)
INPUT_KEYS = (
    "accepted_forms",
    "filesystem_paths",
    "production_uploads",
    "real_downloads",
    "target_selection_directory",
    "aptarank_ui_or_api",
)
TOP_LEVEL_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "stage",
    "deployment_verified",
    "effective_preset_resolved",
    "live_export_behavior",
    "scientific_result",
    "production_inputs_opened",
    "aptarank_execution",
    "target_selected_by_package",
    "structure_file_inspected",
    "scores_calculated",
    "overlap_or_leakage_calculated",
    "reasons_invented",
    "governing_plan",
    "candidate_preparation_contract",
    "reused_modules",
    "target_configuration",
    "manual_run",
    "binding",
    "inputs",
    "prohibited",
)
PIN_ROLES = (
    "manual_run_contract",
    "governing_plan",
    "candidate_preparation_contract",
    "candidate_preparation_module",
    "record_parser_module",
)
REUSED_MODULES = (
    ("candidate_preparation_module", PREPARATION_MODULE_RELATIVE, PREPARATION_MODULE_SHA256),
    ("record_parser_module", PARSER_MODULE_RELATIVE, PARSER_MODULE_SHA256),
)
PROHIBITED_PHRASES = (
    "TRAIN",
    "VALIDATION",
    "REF",
    "EVAL",
    "results/",
    "AptaRank",
    "overlap",
    "leakage",
    "Tier 1",
    "Tier 2",
    "target-selection directory",
)
RECEIPT_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "bound",
    "synthetic",
    "production_inputs_opened",
    "aptarank_executed",
    "scientific_result",
    "deployment_verified",
    "effective_preset_resolved",
    "live_export_behavior",
    "target_selected_by_package",
    "structure_file_inspected",
    "scores_calculated",
    "reasons_invented",
    "preparation_contract_sha256",
    "target_configuration_sha256",
    "preparation_manifest_sha256",
    "candidate_upload_sha256",
    "private_membership_key_sha256",
    "manual_run_state",
)
_MODULES = {}


class ManualRunError(ValueError):
    """The synthetic manual-run contract refused the record."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def contract_path():
    return os.path.join(repo_root(), CONTRACT_RELATIVE)


def _load_module(filename, module_name):
    if module_name in _MODULES:
        return _MODULES[module_name]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULES[module_name] = module
    return module


def _parser():
    return _load_module("generator_eval_parser.py", "generator_eval_parser_for_m9b4")


def _preparation():
    return _load_module("aptarank_candidate_preparation.py", "aptarank_candidate_preparation_for_m9b4")


def _require(condition, code, detail):
    if not condition:
        raise ManualRunError(code, detail)


def _exact_keys(document, expected, detail):
    _require(type(document) is dict and tuple(document) == tuple(expected), "spec_invalid", detail)


def _read_pinned_file(relative):
    if type(relative) is not str or relative == "" or os.path.isabs(relative) or ".." in relative.split("/"):
        raise ManualRunError("pin_invalid", "a pinned path is not a repository-relative file")
    path = os.path.join(repo_root(), relative)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise ManualRunError("pin_unreadable", "a pinned file cannot be read") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ManualRunError("pin_symlink", "a pinned file is not a regular file")
    with open(path, "rb") as handle:
        return handle.read()


def _recorded_modules(document):
    reused = []
    for item in document["reused_modules"]:
        _exact_keys(item, MODULE_PIN_KEYS, "a reused module record drifted")
        reused.append((item["role"], item["path"], item["sha256"]))
    return tuple(reused)


def validate_contract_document(document):
    """Refuse a contract that selects a target or resolves the live deployment."""
    _exact_keys(document, TOP_LEVEL_KEYS, "the manual-run contract keys changed")
    _require(document["package_id"] == PACKAGE_ID, "spec_invalid", "the package id is not M9B-4")
    _require(document["schema_version"] == SCHEMA_VERSION, "spec_invalid", "the schema version drifted")
    _require(document["status"] == STATUS, "spec_invalid", "the manual-run status drifted")
    _require(document["stage"] == STAGE, "spec_invalid", "the stage is not M9B-4")
    for key in (
        "deployment_verified",
        "effective_preset_resolved",
        "scientific_result",
        "production_inputs_opened",
        "aptarank_execution",
        "target_selected_by_package",
        "structure_file_inspected",
        "scores_calculated",
        "overlap_or_leakage_calculated",
        "reasons_invented",
    ):
        _require(document[key] is False, "spec_invalid", key + " must remain false")
    _require(document["live_export_behavior"] == "unresolved", "spec_invalid", "live export behavior must stay unresolved")
    plan = document["governing_plan"]
    _exact_keys(plan, PLAN_KEYS, "the governing plan record drifted")
    _require(plan["path"] == PLAN_RELATIVE, "spec_invalid", "the governing plan path drifted")
    _require(plan["version"] == "3.3", "spec_invalid", "the governing plan version drifted")
    _require(plan["revision_date"] == "12 October 2026", "spec_invalid", "the governing plan date drifted")
    _require(plan["sha256"] == PLAN_SHA256, "spec_invalid", "the governing plan hash drifted")
    preparation = document["candidate_preparation_contract"]
    _exact_keys(preparation, PREPARATION_PIN_KEYS, "the preparation-contract pin drifted")
    _require(preparation["path"] == PREPARATION_CONTRACT_RELATIVE, "spec_invalid", "the preparation-contract path drifted")
    _require(preparation["package_id"] == "M9B-2", "spec_invalid", "the preparation package is not M9B-2")
    _require(
        preparation["schema_version"] == "m9b-aptarank-candidate-preparation-v1",
        "spec_invalid",
        "the preparation schema drifted",
    )
    _require(preparation["sha256"] == PREPARATION_CONTRACT_SHA256, "spec_invalid", "the preparation-contract hash drifted")
    _require(_recorded_modules(document) == REUSED_MODULES, "spec_invalid", "the reused module pins drifted")
    target = document["target_configuration"]
    _exact_keys(target, TARGET_CONTRACT_KEYS, "the target-configuration section drifted")
    _require(target["schema_version"] == TARGET_SCHEMA, "spec_invalid", "the target schema drifted")
    _require(target["keys"] == list(TARGET_KEYS), "spec_invalid", "the target keys drifted")
    _require(target["selection_status"] == SELECTION_STATUS, "spec_invalid", "the selection status drifted")
    _require(target["site_definition_methods"] == list(SITE_METHODS), "spec_invalid", "the site methods drifted")
    _require(target["residue_pattern"] == RESIDUE_PATTERN, "spec_invalid", "the residue pattern drifted")
    _require(target["duplicate_residues"] == "fail_closed", "spec_invalid", "duplicate residues must fail closed")
    _require(target["structure_file_inspected"] is False, "spec_invalid", "a structure file must not be inspected")
    _require(target["biological_choice_judged"] is False, "spec_invalid", "the biological choice must not be judged")
    _require(target["filesystem_paths"] is False, "spec_invalid", "target records must not carry filesystem paths")
    manual = document["manual_run"]
    _exact_keys(manual, MANUAL_CONTRACT_KEYS, "the manual-run section drifted")
    _require(manual["schema_version"] == RUN_SCHEMA, "spec_invalid", "the manual-run schema drifted")
    _require(manual["states"] == list(RUN_STATES), "spec_invalid", "the run states drifted")
    _require(manual["prepared_keys"] == list(PREPARED_KEYS), "spec_invalid", "the prepared keys drifted")
    _require(manual["completed_additional_keys"] == list(COMPLETED_EXTRA_KEYS), "spec_invalid", "the completed keys drifted")
    _require(manual["completed_counts"] == list(COUNT_FIELDS), "spec_invalid", "the completed counts drifted")
    _require(manual["count_sum_equals_expected"] is True, "spec_invalid", "completed counts must sum to the expected count")
    _require(manual["reasons_invented"] is False, "spec_invalid", "missing and failed reasons must not be invented")
    _require(manual["timestamp_pattern"] == TIMESTAMP_PATTERN, "spec_invalid", "the timestamp pattern drifted")
    _require(manual["run_artefact_sha256"] == "sha256_or_null", "spec_invalid", "the run-artefact rule drifted")
    _require(manual["raw_export_sha256"] == "sha256_required", "spec_invalid", "the raw-export rule drifted")
    _exact_keys(manual["rerun"], RERUN_KEYS, "the rerun rule drifted")
    _require(manual["rerun"]["parent_requires_nonempty_reason"] is True, "spec_invalid", "a rerun must record a reason")
    _require(manual["rerun"]["first_run_reason"] is None, "spec_invalid", "a first run must not record a rerun reason")
    _exact_keys(manual["effective_settings"], EFFECTIVE_CONTRACT_KEYS, "the effective-settings rule drifted")
    _require(manual["effective_settings"]["keys"] == list(EFFECTIVE_SETTINGS_KEYS), "spec_invalid", "effective-settings keys drifted")
    _require(manual["effective_settings"]["effective_preset"] is None, "spec_invalid", "the effective preset must stay unresolved")
    _require(
        manual["effective_settings"]["live_export_behavior"] == "unresolved",
        "spec_invalid",
        "live export behavior must stay unresolved",
    )
    _require(manual["effective_settings"]["resolved_in_m9b"] is False, "spec_invalid", "effective settings are not resolved in M9B")
    _require(manual["deployment_inferred"] is False, "spec_invalid", "deployment identity must not be inferred")
    _require(manual["requested_preset_inferred"] is False, "spec_invalid", "the requested preset must not be inferred")
    _require(manual["live_export_behavior"] == "unresolved", "spec_invalid", "live export behavior must stay unresolved")
    binding = document["binding"]
    _exact_keys(binding, BINDING_CONTRACT_KEYS, "the binding section drifted")
    _require(binding["inputs"] == "caller_supplied_bytes", "spec_invalid", "binding inputs must be caller-supplied bytes")
    for key in (
        "candidate_upload_hash_matches_manifest",
        "private_membership_key_hash_matches_manifest",
        "manifest_pinned_to_corrected_m9b2_contract",
        "manual_run_contains_same_three_hashes",
        "target_record_bytes_match_manual_run_hash",
    ):
        _require(binding[key] is True, "spec_invalid", key + " must stay required")
    for key in ("sampling_duplicated", "export_validation_duplicated", "filesystem_paths"):
        _require(binding[key] is False, "spec_invalid", key + " must remain false")
    inputs = document["inputs"]
    _exact_keys(inputs, INPUT_KEYS, "the input section drifted")
    _require(
        inputs["accepted_forms"] == ["caller_supplied_object", "caller_supplied_bytes"],
        "spec_invalid",
        "the accepted input forms drifted",
    )
    for key in (
        "filesystem_paths",
        "production_uploads",
        "real_downloads",
        "target_selection_directory",
        "aptarank_ui_or_api",
    ):
        _require(inputs[key] is False, "spec_invalid", key + " must remain false")
    prohibited = document["prohibited"]
    _require(type(prohibited) is list and prohibited, "spec_invalid", "the prohibited list drifted")
    prohibited_text = "\n".join(prohibited)
    for phrase in PROHIBITED_PHRASES:
        _require(phrase in prohibited_text, "spec_invalid", "a prohibited action is missing")
    return document


def verify_external_pins(document, blobs):
    """Compare pinned hashes with caller-supplied file bytes."""
    validate_contract_document(document)
    _require(type(blobs) is dict and set(blobs) == set(PIN_ROLES), "pin_invalid", "the pin byte set is incomplete")
    expected = {
        "manual_run_contract": CONTRACT_SHA256,
        "governing_plan": PLAN_SHA256,
        "candidate_preparation_contract": PREPARATION_CONTRACT_SHA256,
        "candidate_preparation_module": PREPARATION_MODULE_SHA256,
        "record_parser_module": PARSER_MODULE_SHA256,
    }
    preparation = _preparation()
    for role, digest in expected.items():
        payload = blobs[role]
        _require(type(payload) is bytes, "pin_invalid", "a pinned payload is not bytes")
        if preparation.sha256_bytes(payload) != digest:
            raise ManualRunError("pin_mismatch", "the " + role + " pin does not match")
    return document


def load_pinned_contract():
    """Load the manual-run contract and fail closed on every recorded pin."""
    contract_bytes = _read_pinned_file(CONTRACT_RELATIVE)
    preparation = _preparation()
    parser = _parser()
    if preparation.sha256_bytes(contract_bytes) != CONTRACT_SHA256:
        raise ManualRunError("pin_mismatch", "the manual-run contract pin does not match")
    try:
        document = json.loads(contract_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManualRunError("spec_invalid", "the manual-run contract is not readable JSON") from exc
    blobs = {
        "manual_run_contract": contract_bytes,
        "governing_plan": _read_pinned_file(PLAN_RELATIVE),
        "candidate_preparation_contract": _read_pinned_file(PREPARATION_CONTRACT_RELATIVE),
        "candidate_preparation_module": _read_pinned_file(PREPARATION_MODULE_RELATIVE),
        "record_parser_module": _read_pinned_file(PARSER_MODULE_RELATIVE),
    }
    verify_external_pins(document, blobs)
    try:
        preparation_document = preparation.load_pinned_contract()
    except preparation.CandidatePreparationError as exc:
        raise ManualRunError(exc.code, exc.detail) from exc
    if preparation.CONTRACT_SHA256 != PREPARATION_CONTRACT_SHA256 or preparation.PACKAGE_ID != "M9B-2":
        raise ManualRunError("pin_mismatch", "the corrected M9B-2 contract pin does not match")
    if preparation.SCHEMA_VERSION != "m9b-aptarank-candidate-preparation-v1":
        raise ManualRunError("pin_mismatch", "the loaded preparation schema is not corrected M9B-2")
    if preparation_document.get("package_id") != "M9B-2":
        raise ManualRunError("pin_mismatch", "the loaded preparation contract is not M9B-2")
    if not callable(preparation.canonical_json_bytes) or not callable(preparation.sha256_bytes):
        raise ManualRunError("pin_mismatch", "the preparation serialization helpers are missing")
    if not callable(parser.sha256_text) or not callable(parser.reject_control_string) or not callable(parser.enforce_firewall):
        raise ManualRunError("pin_mismatch", "the parser helpers are missing")
    return document


def _firewall(controls):
    parser = _parser()
    try:
        parser.enforce_firewall(controls)
    except parser.ParserContractError as exc:
        raise ManualRunError(exc.code, exc.detail) from exc


def _path_object(value):
    if isinstance(value, (str, bytes, bytearray)):
        return False
    return callable(getattr(value, "__fspath__", None))


def _refuse_embedded_path(value):
    if _path_object(value):
        raise ManualRunError("filesystem_path_refused", "a filesystem path argument is refused")
    if type(value) is str:
        try:
            _parser().reject_control_string(value)
        except _parser().ParserContractError as exc:
            raise ManualRunError(exc.code, exc.detail) from exc


def _decode_object(value, label):
    if _path_object(value):
        raise ManualRunError("filesystem_path_refused", "a filesystem path argument is refused")
    if type(value) is str:
        _refuse_embedded_path(value)
        raise ManualRunError("input_type_invalid", label + " must be an object or bytes")
    if type(value) is bytes:
        try:
            parsed = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ManualRunError("malformed_input", label + " is not UTF-8 JSON") from exc
        if type(parsed) is not dict:
            raise ManualRunError("input_type_invalid", label + " JSON must be an object")
        return parsed
    if type(value) is not dict:
        raise ManualRunError("input_type_invalid", label + " must be an object or bytes")
    return value


def _require_bytes(value, label):
    if _path_object(value):
        raise ManualRunError("filesystem_path_refused", "a filesystem path argument is refused")
    if type(value) is str:
        _refuse_embedded_path(value)
        raise ManualRunError("input_type_invalid", label + " must be bytes")
    if type(value) is not bytes:
        raise ManualRunError("input_type_invalid", label + " must be bytes")
    return value


def _object_keys(document, expected, missing_code):
    if type(document) is not dict:
        raise ManualRunError("input_type_invalid", "the record must be an object")
    unknown = [key for key in document if key not in expected]
    if unknown:
        raise ManualRunError("unknown_field", "unknown field " + unknown[0])
    missing = [key for key in expected if key not in document]
    if missing:
        code = missing_code
        if missing_code == "completed_field_missing" and missing[0] in PREPARED_KEYS:
            code = "manual_field_missing"
        raise ManualRunError(code, "missing field " + missing[0])


def _identifier(value, label):
    _refuse_embedded_path(value)
    if type(value) is not str:
        raise ManualRunError("field_invalid", label + " must be text")
    if value == "":
        raise ManualRunError("empty_field", label + " is empty")
    if IDENTIFIER_TEXT.fullmatch(value) is None:
        raise ManualRunError("field_invalid", label + " is not a valid identifier")
    return value


def _free_text(value, label, limit):
    _refuse_embedded_path(value)
    if type(value) is not str:
        raise ManualRunError("field_invalid", label + " must be text")
    if value == "" or value.strip() == "":
        raise ManualRunError("empty_field", label + " is empty")
    if value != value.strip() or len(value) > limit or not value.isascii():
        raise ManualRunError("field_invalid", label + " is not valid text")
    if any(character.isspace() and character != " " for character in value):
        raise ManualRunError("field_invalid", label + " is not valid text")
    return value


def _chain(value):
    _refuse_embedded_path(value)
    if type(value) is not str:
        raise ManualRunError("field_invalid", "chain_id must be text")
    if value == "":
        raise ManualRunError("empty_field", "chain_id is empty")
    if CHAIN_TEXT.fullmatch(value) is None:
        raise ManualRunError("field_invalid", "chain_id is not a valid chain identifier")
    return value


def _sha256(value, label, allow_null=False):
    if allow_null and value is None:
        return None
    _refuse_embedded_path(value)
    if type(value) is str and value == "":
        raise ManualRunError("empty_field", label + " is empty")
    if type(value) is not str or not _parser().sha256_text(value):
        raise ManualRunError("hash_malformed", label + " is not a lowercase SHA-256 digest")
    return value


def _count(value, label):
    if type(value) is not int or value < 0:
        raise ManualRunError("count_invalid", label + " must be a nonnegative integer")
    return value


def _timestamp(value, label):
    if value is None:
        raise ManualRunError("completed_incomplete", label + " is required on a completed run")
    _refuse_embedded_path(value)
    if type(value) is str and value == "":
        raise ManualRunError("empty_field", label + " is empty")
    if type(value) is not str or TIMESTAMP_TEXT.fullmatch(value) is None:
        raise ManualRunError("timestamp_invalid", label + " is not a UTC timestamp")
    return value


def _notes(value):
    if value is None:
        return None
    return _free_text(value, "notes", 200)


def _residues(value):
    if type(value) is not list or len(value) == 0:
        raise ManualRunError("residue_invalid", "selected site residues must be a nonempty list")
    seen = set()
    cleaned = []
    for item in value:
        _refuse_embedded_path(item)
        if type(item) is not str or RESIDUE_TEXT.fullmatch(item) is None:
            raise ManualRunError("residue_invalid", "a selected site residue is not a residue token")
        if item in seen:
            raise ManualRunError("residue_duplicate", "a selected site residue is duplicated")
        seen.add(item)
        cleaned.append(item)
    return cleaned


def _site(method, residues, rule):
    if type(method) is not str or method not in SITE_METHODS:
        raise ManualRunError("site_invalid", "the site-definition method is not recorded")
    if method == "selected_residues":
        if rule is not None:
            raise ManualRunError("site_conflict", "a residue list and a frozen site rule cannot both be recorded")
        return _residues(residues), None
    if residues is not None:
        raise ManualRunError("site_conflict", "a residue list and a frozen site rule cannot both be recorded")
    if rule is None:
        raise ManualRunError("site_invalid", "the frozen site rule is missing")
    return None, _free_text(rule, "frozen_site_rule", 200)


def _schema_version(value, expected, label):
    if type(value) is str and value == "":
        raise ManualRunError("empty_field", label + " is empty")
    if value != expected:
        raise ManualRunError("schema_invalid", label + " is not the M9B-4 schema")
    return value


def _warnings(value):
    if type(value) is not list:
        raise ManualRunError("warnings_invalid", "warnings must be a list")
    return [_free_text(item, "warning", 200) for item in value]


def _effective_settings(value):
    if type(value) is not dict or set(value) != set(EFFECTIVE_SETTINGS_KEYS):
        raise ManualRunError("effective_settings_unresolved", "effective settings stay unresolved until M9C")
    if value["effective_preset"] is not None or value["live_export_behavior"] != "unresolved":
        raise ManualRunError("effective_settings_unresolved", "effective settings stay unresolved until M9C")
    return {"effective_preset": None, "live_export_behavior": "unresolved"}


def _lineage(run_id, parent, reason):
    if parent is None and reason is None:
        return None, None
    if parent is None:
        raise ManualRunError("rerun_lineage_invalid", "a first run must not record a rerun reason")
    if reason is None or (type(reason) is str and reason.strip() == ""):
        raise ManualRunError("rerun_lineage_invalid", "a rerun with a parent run must record a nonempty rerun reason")
    parent_id = _identifier(parent, "parent_run_id")
    if parent_id == run_id:
        raise ManualRunError("rerun_lineage_invalid", "a run cannot name itself as its parent")
    return parent_id, _free_text(reason, "rerun_reason", 200)


def _canonical_target(raw):
    _object_keys(raw, TARGET_KEYS, "target_field_missing")
    if raw["selection_status"] != SELECTION_STATUS:
        if raw["selection_status"] == "":
            raise ManualRunError("empty_field", "selection_status is empty")
        raise ManualRunError(
            "selection_status_invalid",
            "selection must already be completed independently before M9B",
        )
    residues, rule = _site(raw["site_definition_method"], raw["selected_site_residues"], raw["frozen_site_rule"])
    return {
        "schema_version": _schema_version(raw["schema_version"], TARGET_SCHEMA, "target schema"),
        "configuration_id": _identifier(raw["configuration_id"], "configuration_id"),
        "target_id": _identifier(raw["target_id"], "target_id"),
        "display_name": _free_text(raw["display_name"], "display_name", 80),
        "selection_status": SELECTION_STATUS,
        "structure_id": _identifier(raw["structure_id"], "structure_id"),
        "chain_id": _chain(raw["chain_id"]),
        "binding_mode": _free_text(raw["binding_mode"], "binding_mode", 80),
        "site_definition_method": raw["site_definition_method"],
        "selected_site_residues": residues,
        "frozen_site_rule": rule,
        "structure_file_sha256": _sha256(raw["structure_file_sha256"], "structure_file_sha256"),
        "target_selection_record_sha256": _sha256(raw["target_selection_record_sha256"], "target_selection_record_sha256"),
        "notes": _notes(raw["notes"]),
    }


def _canonical_manual(raw):
    if type(raw) is not dict:
        raise ManualRunError("input_type_invalid", "the record must be an object")
    if "state" not in raw:
        raise ManualRunError("manual_field_missing", "missing field state")
    state = raw["state"]
    if state not in RUN_STATES:
        raise ManualRunError("state_invalid", "the run state must be prepared or completed")
    expected = COMPLETED_KEYS if state == "completed" else PREPARED_KEYS
    missing_code = "completed_field_missing" if state == "completed" else "manual_field_missing"
    _object_keys(raw, expected, missing_code)
    run_id = _identifier(raw["run_id"], "run_id")
    parent, reason = _lineage(run_id, raw["parent_run_id"], raw["rerun_reason"])
    canonical = {
        "schema_version": _schema_version(raw["schema_version"], RUN_SCHEMA, "manual-run schema"),
        "run_id": run_id,
        "state": state,
        "operator": _free_text(raw["operator"], "operator", 80),
        "target_configuration_sha256": _sha256(raw["target_configuration_sha256"], "target_configuration_sha256"),
        "preparation_manifest_sha256": _sha256(raw["preparation_manifest_sha256"], "preparation_manifest_sha256"),
        "candidate_upload_sha256": _sha256(raw["candidate_upload_sha256"], "candidate_upload_sha256"),
        "private_membership_key_sha256": _sha256(raw["private_membership_key_sha256"], "private_membership_key_sha256"),
        "reference_file_sha256": _sha256(raw["reference_file_sha256"], "reference_file_sha256"),
        "expected_candidate_count": _count(raw["expected_candidate_count"], "expected_candidate_count"),
        "deployment_id": _identifier(raw["deployment_id"], "deployment_id"),
        "requested_preset": _identifier(raw["requested_preset"], "requested_preset"),
        "effective_settings": _effective_settings(raw["effective_settings"]),
        "warnings": _warnings(raw["warnings"]),
        "parent_run_id": parent,
        "rerun_reason": reason,
    }
    if state == "prepared":
        return canonical
    started = _timestamp(raw["started_at"], "started_at")
    completed = _timestamp(raw["completed_at"], "completed_at")
    if completed < started:
        raise ManualRunError("timestamp_invalid", "completion is earlier than the start")
    counts = [_count(raw[name], name) for name in COUNT_FIELDS]
    if sum(counts) != canonical["expected_candidate_count"]:
        raise ManualRunError("count_mismatch", "completed counts do not sum to the expected candidate count")
    if raw["raw_export_sha256"] is None:
        raise ManualRunError("completed_incomplete", "raw_export_sha256 is required on a completed run")
    canonical["started_at"] = started
    canonical["completed_at"] = completed
    for name, count in zip(COUNT_FIELDS, counts):
        canonical[name] = count
    canonical["raw_export_sha256"] = _sha256(raw["raw_export_sha256"], "raw_export_sha256")
    canonical["run_artefact_sha256"] = _sha256(raw["run_artefact_sha256"], "run_artefact_sha256", allow_null=True)
    return canonical


def _json_bytes(document):
    return _preparation().canonical_json_bytes(document) + b"\n"


def validate_target_configuration(document, **controls):
    """Return the canonical target-configuration object.

    The object must already say that selection was completed independently
    before this package. Residue tokens are checked for syntax and duplicates.
    The structure file is not opened, and the biological choice is not judged.
    """
    _firewall(controls)
    load_pinned_contract()
    return _canonical_target(_decode_object(document, "target configuration"))


def target_configuration_bytes(document, **controls):
    """Serialize a valid target configuration deterministically."""
    return _json_bytes(validate_target_configuration(document, **controls))


def validate_manual_run(document, **controls):
    """Return the canonical manual-run object for a prepared or completed state.

    Completed accounting counts must sum to the expected candidate count. No
    missing-row or failed-row reason is added. Deployment, the effective
    preset, and live export behaviour are not inferred.
    """
    _firewall(controls)
    load_pinned_contract()
    return _canonical_manual(_decode_object(document, "manual run"))


def manual_run_bytes(document, **controls):
    """Serialize a valid manual-run record deterministically."""
    return _json_bytes(validate_manual_run(document, **controls))


def _manifest_document(payload):
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManualRunError("malformed_input", "the preparation manifest is not UTF-8 JSON") from exc
    if type(document) is not dict:
        raise ManualRunError("binding_mismatch", "the preparation manifest is not an object")
    return document


def _require_corrected_manifest(document, preparation):
    if document.get("package_id") != preparation.PACKAGE_ID:
        raise ManualRunError("pin_mismatch", "the preparation manifest is not M9B-2")
    if document.get("schema_version") != preparation.SCHEMA_VERSION:
        raise ManualRunError("pin_mismatch", "the preparation manifest is not the corrected M9B-2 schema")
    pins = document.get("pins")
    if type(pins) is not list:
        raise ManualRunError("pin_mismatch", "the preparation manifest has no contract pin")
    matches = [pin for pin in pins if type(pin) is dict and pin.get("role") == "preparation_contract"]
    if len(matches) != 1:
        raise ManualRunError("pin_mismatch", "the preparation manifest must pin the M9B-2 contract once")
    pin = matches[0]
    if pin.get("path") != preparation.CONTRACT_RELATIVE or pin.get("sha256") != preparation.CONTRACT_SHA256:
        raise ManualRunError("pin_mismatch", "the preparation manifest is not pinned to the corrected M9B-2 contract")


def _binding_receipt(manual, target_sha, manifest_sha, upload_sha, private_sha):
    return {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "bound": True,
        "synthetic": True,
        "production_inputs_opened": False,
        "aptarank_executed": False,
        "scientific_result": False,
        "deployment_verified": False,
        "effective_preset_resolved": False,
        "live_export_behavior": "unresolved",
        "target_selected_by_package": False,
        "structure_file_inspected": False,
        "scores_calculated": False,
        "reasons_invented": False,
        "preparation_contract_sha256": PREPARATION_CONTRACT_SHA256,
        "target_configuration_sha256": target_sha,
        "preparation_manifest_sha256": manifest_sha,
        "candidate_upload_sha256": upload_sha,
        "private_membership_key_sha256": private_sha,
        "manual_run_state": manual["state"],
    }


def bind_existing_artifacts(
    *,
    manual_run,
    target_configuration,
    preparation_manifest,
    candidate_upload,
    private_membership_key,
    **controls,
):
    """Bind caller-supplied bytes to one manual-run record.

    The candidate upload and private membership key must match the supplied
    M9B-2 preparation manifest. That manifest must pin the corrected M9B-2
    contract. The manual-run record must contain those three hashes, and the
    target-record bytes must match the target-configuration hash. Upload and
    private-key bytes are hashed only.
    """
    _firewall(controls)
    manual_bytes = _require_bytes(manual_run, "manual run")
    target_bytes = _require_bytes(target_configuration, "target configuration")
    manifest_bytes = _require_bytes(preparation_manifest, "preparation manifest")
    upload_bytes = _require_bytes(candidate_upload, "candidate upload")
    private_bytes = _require_bytes(private_membership_key, "private membership key")
    load_pinned_contract()
    manual = validate_manual_run(manual_bytes)
    target = validate_target_configuration(target_bytes)
    _require(target["schema_version"] == TARGET_SCHEMA, "schema_invalid", "the target schema drifted")
    preparation = _preparation()
    manifest = _manifest_document(manifest_bytes)
    _require_corrected_manifest(manifest, preparation)
    upload_sha = preparation.sha256_bytes(upload_bytes)
    private_sha = preparation.sha256_bytes(private_bytes)
    manifest_sha = preparation.sha256_bytes(manifest_bytes)
    target_sha = preparation.sha256_bytes(target_bytes)
    if manifest.get("candidate_upload_sha256") != upload_sha:
        raise ManualRunError("binding_mismatch", "the candidate upload hash does not match the preparation manifest")
    if manifest.get("private_membership_key_sha256") != private_sha:
        raise ManualRunError(
            "binding_mismatch",
            "the private membership key hash does not match the preparation manifest",
        )
    if manual["preparation_manifest_sha256"] != manifest_sha:
        raise ManualRunError("binding_mismatch", "the manual run manifest hash does not match the preparation manifest")
    if manual["candidate_upload_sha256"] != upload_sha:
        raise ManualRunError("binding_mismatch", "the manual run upload hash does not match the candidate upload")
    if manual["private_membership_key_sha256"] != private_sha:
        raise ManualRunError("binding_mismatch", "the manual run private-key hash does not match the private membership key")
    if manual["target_configuration_sha256"] != target_sha:
        raise ManualRunError("binding_mismatch", "the target configuration hash does not match the target record")
    receipt = _binding_receipt(manual, target_sha, manifest_sha, upload_sha, private_sha)
    _exact_keys(receipt, RECEIPT_KEYS, "the binding receipt drifted")
    return receipt


def main(argv=None):
    """Check pins and print the status. There is no production runner."""
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        raise ManualRunError("production_runner_refused", "M9B-4 has no production runner")
    load_pinned_contract()
    sys.stdout.write(STATUS + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManualRunError as exc:
        sys.stderr.write(exc.code + ": " + exc.detail + "\n")
        raise SystemExit(1)

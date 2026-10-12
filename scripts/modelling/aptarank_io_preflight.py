#!/usr/bin/env python3
"""ARP-1 draft AptaRank I/O contract and fail-closed synthetic preflight.

The no-argument command validates bundled synthetic fixtures only. It does
not call the AptaRank UI, and it does not load EVAL, REF, VALIDATION, TRAIN,
production pools, or checkpoints. A passing report is a technical preflight,
not a scientific result.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys

PACKAGE_ID = "ARP-1"
SCHEMA_VERSION = "aptarank-io-arp1-draft-r3"
SPEC_RELATIVE = "config/modelling/aptarank_io_spec.json"
FIXTURE_RELATIVE = "tests/modelling/fixtures/aptarank_arp1"
GOVERNING_PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan.md"
PROFILE_ID = "target_free_rigorous_style"
TARGET_FREE_SENTINEL = "not_entered_target_free"
JOIN_KEY = "candidate_id"
JOIN_USES_ROW_POSITION = False
IMPUTE_MISSING_AS_ZERO = False

CANDIDATE_COLUMNS = ("id", "sequence")
REFERENCE_COLUMNS = (
    "id",
    "sequence",
    "target_name",
    "target_pdb_id",
    "source_reference",
)
SHORTLIST_COLUMNS = (
    "rank",
    "candidate",
    "aptamer-likeness",
    "compatibility",
    "shuffle",
    "len",
    "sequence",
)
COLUMN_TYPES = {
    "candidate_upload": {
        "id": "nonempty_opaque_id",
        "sequence": "uppercase_acgu",
    },
    "reference_upload": {
        "id": "nonempty_opaque_id",
        "sequence": "uppercase_acgu",
        "target_name": "nonempty_uninterpreted_string",
        "target_pdb_id": "nullable_uninterpreted_string",
        "source_reference": "nonempty_uninterpreted_string",
    },
    "shortlist_export": {
        "rank": "positive_integer",
        "candidate": "nonempty_opaque_id",
        "aptamer-likeness": "finite_decimal",
        "compatibility": "profile_token",
        "shuffle": "profile_token",
        "len": "nonnegative_integer",
        "sequence": "uppercase_acgu",
    },
}
RULE_KEYS = (
    "opaque_id_preservation",
    "sequence_alphabet",
    "unique_ids",
    "nullable_target_pdb_id",
    "id_set_reconciliation",
    "sequence_round_trip",
    "exported_length",
    "join",
    "duplicates_missing_extra",
    "nonfinite_tier1",
    "shuffle_profile",
    "target_free_compatibility",
    "failure_accounting",
    "sha256",
    "schema_change",
    "utf8_bom",
    "no_combined_score",
    "no_binding_interpretation",
)
COMPATIBILITY_TOKENS = ("not evaluated",)
SHUFFLE_TOKENS = ("pass", "fail")
UNRESOLVED_QUESTION_IDS = (
    "raw_tier2_score_availability",
    "raw_tier2_equation",
    "raw_tier2_direction",
    "raw_tier2_comparison_scope",
    "control_bank_identifier",
    "control_bank_hash",
    "control_bank_provenance",
    "deployment_version",
    "deployment_schema_version",
    "deployment_code_revision",
    "preset_value",
    "compatibility_token_meaning",
    "shuffle_token_meaning",
)
HASHED_BYTE_ROLES = (
    "candidate_upload",
    "reference_upload",
    "shortlist_export",
    "failure_accounting",
    "expected_cell_manifest",
    "provenance",
)
UI_CAPTURE_FIELDS = (
    "run_id",
    "operator",
    "started_at",
    "finished_at",
    "deployment_version",
    "deployment_schema_version",
    "deployment_code_revision",
    "preset_value",
    "effective_settings",
    "candidate_upload_sha256",
    "reference_upload_sha256",
    "shortlist_export_sha256",
    "failure_accounting_sha256",
    "expected_cell_manifest_sha256",
    "raw_tier2_score_availability",
    "raw_tier2_equation",
    "raw_tier2_direction",
    "raw_tier2_comparison_scope",
    "control_bank_identifier",
    "control_bank_hash",
    "control_bank_provenance",
    "canonical_target",
    "structure_or_pdb",
    "structure_sha256",
    "chain_or_domain",
    "binding_mode",
    "site_or_pocket",
    "numbering",
    "preparation",
    "runtime_seconds",
    "runtime_status",
    "expected_row_count",
    "exported_row_count",
    "failed_row_count",
    "warnings",
    "rerun_lineage",
    "ui_capture_complete",
    "deployment_verified",
)
PROVENANCE_SELECTOR_KEYS = (
    "fixture_role",
    "profile_id",
)
PROVENANCE_KEYS = PROVENANCE_SELECTOR_KEYS + UI_CAPTURE_FIELDS
NULL_PROVENANCE_FIELDS = (
    "deployment_version",
    "deployment_schema_version",
    "deployment_code_revision",
    "preset_value",
    "effective_settings",
    "raw_tier2_equation",
    "raw_tier2_direction",
    "control_bank_identifier",
    "control_bank_hash",
    "control_bank_provenance",
    "runtime_seconds",
)
UNRESOLVED_STRING_FIELDS = (
    "raw_tier2_score_availability",
    "raw_tier2_comparison_scope",
)
FALSE_PROVENANCE_FIELDS = (
    "ui_capture_complete",
    "deployment_verified",
)
TARGET_SENTINEL_FIELDS = (
    "canonical_target",
    "structure_or_pdb",
    "chain_or_domain",
    "binding_mode",
    "site_or_pocket",
    "numbering",
    "preparation",
)
RECORDED_HASH_FIELDS = (
    ("candidate_upload_sha256", "candidate_upload"),
    ("reference_upload_sha256", "reference_upload"),
    ("shortlist_export_sha256", "shortlist_export"),
    ("failure_accounting_sha256", "failure_accounting"),
    ("expected_cell_manifest_sha256", "expected_cell_manifest"),
)
COUNT_FIELDS = (
    "expected_row_count",
    "exported_row_count",
    "failed_row_count",
)
RECORDED_COUNT_TYPE = (
    "Recorded counts are nonnegative JSON integers. "
    "Booleans and floats are excluded, including floats that are mathematically integral."
)
NULL_STRUCTURE_HASH_FIELDS = ("structure_sha256",)
UTF8_BOM = b"\xef\xbb\xbf"
PROVENANCE_HASH_BOUNDARY = (
    "The provenance record does not contain its own SHA-256. "
    "That digest is computed externally from the original provenance bytes "
    "and retained in the generated report SHA-256 block."
)
ROW_ACCOUNTING_FIELDS = (
    "candidate_upload_rows",
    "reference_upload_rows",
    "expected_candidates",
    "exported_rows",
    "failed_rows",
    "duplicate_candidate_ids",
    "duplicate_reference_ids",
    "duplicate_exported_ids",
    "missing_candidate_ids",
    "extra_exported_ids",
    "unaccounted_candidates",
    "silent_drops",
    "rows_imputed_as_zero",
)
RUNTIME_FIELDS = ("runtime_seconds", "runtime_status")
TARGET_CONFIGURATION_FIELDS = (
    "canonical_target",
    "structure_or_pdb",
    "structure_sha256",
    "chain_or_domain",
    "binding_mode",
    "site_or_pocket",
    "numbering",
    "preparation",
)
TOP_LEVEL_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "deployment_verified",
    "scientific_result",
    "combined_tier1_tier2_score",
    "governing_plan",
    "candidate_upload_column_order",
    "reference_upload_column_order",
    "shortlist_export_column_order",
    "column_types",
    "rules",
    "synthetic_run_profiles",
    "failure_accounting",
    "sha256_requirements",
    "required_ui_provenance_capture_fields",
    "provenance_record_schema",
    "raw_tier2_geometric_score",
    "control_bank",
    "deployment_identity",
    "runtime_fields",
    "row_accounting_fields",
    "target_configuration_fields",
    "unresolved_interface_questions",
    "schema_change_policy",
    "interpretation_boundary",
    "provisional_interface_evidence",
)
BUNDLED_FIXTURES = {
    "candidate_upload": "valid_candidate_upload.csv",
    "reference_upload": "valid_reference_upload.csv",
    "shortlist_export": "valid_target_free_rigorous_shortlist.csv",
    "failure_accounting": "explicit_failure_accounting.json",
    "expected_cell_manifest": "expected_cell_manifest.json",
    "provenance": "synthetic_run_provenance.json",
}
EMPTY_FIXTURES = {
    "candidate_upload": "empty_candidate_upload.csv",
    "reference_upload": "empty_reference_upload.csv",
    "shortlist_export": "empty_shortlist.csv",
    "failure_accounting": "empty_failure_accounting.json",
    "expected_cell_manifest": "empty_expected_cell_manifest.json",
    "provenance": "empty_synthetic_run_provenance.json",
}
FORBIDDEN_FIXTURE_NAMES = frozenset(
    {
        "eval.csv",
        "ref.csv",
        "ft_validation.csv",
        "ft_train.csv",
        "corpus_final.csv",
        "corpus_final.txt",
        "evaluation_references.csv",
    }
)
MANIFEST_KEYS = (
    "fixture_role",
    "profile_id",
    "expected_candidate_ids",
    "expected_export_fields",
)
FAILURE_KEYS = ("fixture_role", "profile_id", "failures")
FAILURE_ITEM_KEYS = ("candidate_id", "reason")
ID_TEXT = re.compile(r"^\S+\Z")
SEQUENCE_TEXT = re.compile(r"^[ACGU]+\Z")
UNINTERPRETED_TEXT = re.compile(r"^\S(.*\S)?\Z")
POSITIVE_INT_TEXT = re.compile(r"^[1-9][0-9]*\Z")
NONNEGATIVE_INT_TEXT = re.compile(r"^(?:0|[1-9][0-9]*)\Z")
FINITE_DECIMAL_TEXT = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
NONFINITE_TOKENS = frozenset(
    {
        "nan",
        "+nan",
        "-nan",
        "inf",
        "+inf",
        "-inf",
        "infinity",
        "+infinity",
        "-infinity",
    }
)
NO_PROTECTED_STATEMENT = (
    "No EVAL, REF, VALIDATION, TRAIN, production pool, or checkpoint was loaded."
)
NO_PRODUCTION_STATEMENT = "No protected or production data were loaded."
TECHNICAL_NOT_SCIENTIFIC = (
    "This output is a technical preflight of synthetic fixtures. It is not a scientific result."
)
SCHEMA_MISMATCH_DETAIL = (
    "header does not match the draft schema; ARP-1 will not adapt the columns"
)


class AptaRankIOError(ValueError):
    """The draft interface contract refused the synthetic input."""

    def __init__(self, code, detail, errors=None):
        if errors is None:
            errors = [{"code": code, "detail": detail}]
        self.errors = list(errors)
        self.code = self.errors[0]["code"]
        self.detail = self.errors[0]["detail"]
        super().__init__(self.code + ": " + self.detail)


class ErrorList:
    def __init__(self):
        self.items = []

    def add(self, code, detail):
        self.items.append({"code": code, "detail": detail})

    def raise_if_any(self):
        if self.items:
            first = self.items[0]
            raise AptaRankIOError(first["code"], first["detail"], self.items)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def spec_path():
    return os.path.join(repo_root(), SPEC_RELATIVE)


def fixture_root():
    return os.path.join(repo_root(), FIXTURE_RELATIVE)


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _require(condition, code, detail):
    if not condition:
        raise AptaRankIOError(code, detail)


def _exact_keys(document, expected, code, detail):
    _require(isinstance(document, dict), code, detail)
    _require(set(document) == set(expected), code, detail)


def validate_spec_document(spec):
    """Refuse a spec that is no longer the ARP-1 draft or that resolves open questions."""
    _require(isinstance(spec, dict), "spec_invalid", "the interface spec is not an object")
    _require(set(spec) == set(TOP_LEVEL_KEYS), "spec_schema_drift", "the interface spec keys changed")
    _require(spec["package_id"] == PACKAGE_ID, "spec_invalid", "the package id is not ARP-1")
    _require(spec["schema_version"] == SCHEMA_VERSION, "spec_invalid", "the schema version is not the ARP-1 draft")
    _require(spec["status"] == "draft", "spec_invalid", "ARP-1 status must remain draft")
    if spec["deployment_verified"] is True:
        raise AptaRankIOError("deployment_verified_refused", "ARP-1 cannot mark the deployment verified")
    _require(spec["deployment_verified"] is False, "spec_invalid", "deployment_verified must remain false")
    _require(spec["scientific_result"] is False, "spec_invalid", "the interface spec is not a scientific result")
    if spec["combined_tier1_tier2_score"] is not False:
        raise AptaRankIOError("combined_score_refused", "ARP-1 defines no combined Tier 1 and Tier 2 score")
    plan = spec["governing_plan"]
    _require(isinstance(plan, dict), "spec_invalid", "the governing plan record is missing")
    _require(plan.get("path") == GOVERNING_PLAN_RELATIVE, "spec_invalid", "the governing plan path is not pinned")
    _require(plan.get("version") == "3.2", "spec_invalid", "the governing plan version is not pinned")
    _require(isinstance(plan.get("sha256"), str) and len(plan["sha256"]) == 64, "spec_invalid", "the governing plan hash is missing")
    _require(spec["candidate_upload_column_order"] == list(CANDIDATE_COLUMNS), "spec_schema_drift", "candidate columns drifted")
    _require(spec["reference_upload_column_order"] == list(REFERENCE_COLUMNS), "spec_schema_drift", "reference columns drifted")
    _require(spec["shortlist_export_column_order"] == list(SHORTLIST_COLUMNS), "spec_schema_drift", "shortlist columns drifted")
    _require(spec["column_types"] == COLUMN_TYPES, "spec_schema_drift", "column types drifted")
    _require(isinstance(spec["rules"], dict), "spec_invalid", "rules are missing")
    for key in RULE_KEYS:
        _require(isinstance(spec["rules"].get(key), str) and spec["rules"][key].strip(), "spec_invalid", "a rule is missing")
    profiles = spec["synthetic_run_profiles"]
    _require(isinstance(profiles, dict) and set(profiles) == {PROFILE_ID}, "spec_invalid", "the synthetic profile set changed")
    profile = profiles[PROFILE_ID]
    _require(profile.get("profile_id") == PROFILE_ID, "spec_invalid", "the profile id drifted")
    _require(profile.get("target_entry") == TARGET_FREE_SENTINEL, "spec_invalid", "the target-free sentinel drifted")
    _require(profile.get("compatibility_allowed_tokens") == list(COMPATIBILITY_TOKENS), "spec_invalid", "compatibility tokens drifted")
    _require(profile.get("shuffle_allowed_tokens") == list(SHUFFLE_TOKENS), "spec_invalid", "shuffle tokens drifted")
    _require(profile.get("compatibility_meaning") == "not_interpreted", "spec_invalid", "compatibility meaning must stay uninterpreted")
    _require(profile.get("shuffle_meaning") == "unresolved", "spec_invalid", "shuffle meaning must stay unresolved")
    _require(profile.get("shuffle_threshold") is None, "spec_invalid", "ARP-1 does not adopt a shuffle threshold")
    _require(profile.get("preset_value") is None, "spec_invalid", "ARP-1 does not adopt a preset value")
    _require(profile.get("raw_tier2_score_expected") == "unresolved", "spec_invalid", "raw Tier 2 expectation must stay unresolved")
    failure = spec["failure_accounting"]
    _require(failure.get("silent_drop_allowed") is False, "spec_invalid", "silent drops are not allowed")
    _require(failure.get("impute_missing_as_zero") is False, "spec_invalid", "missing rows are not stored as zero")
    _require(failure.get("reason_required") is True, "spec_invalid", "a failure reason is required")
    hashes = spec["sha256_requirements"]
    _require(hashes.get("algorithm") == "SHA-256", "spec_invalid", "SHA-256 is required")
    _require(hashes.get("hashed_byte_roles") == list(HASHED_BYTE_ROLES), "spec_invalid", "hash roles drifted")
    _require(hashes.get("provenance_record_includes_own_sha256") is False, "spec_invalid", "the provenance record must not contain its own SHA-256")
    _require(hashes.get("hashing_boundary") == PROVENANCE_HASH_BOUNDARY, "spec_invalid", "the provenance hashing boundary drifted")
    _require(spec["required_ui_provenance_capture_fields"] == list(UI_CAPTURE_FIELDS), "spec_invalid", "UI capture fields drifted")
    _require("provenance_record_sha256" not in UI_CAPTURE_FIELDS, "spec_invalid", "the provenance self-hash is not a capture field")
    _require(set(UI_CAPTURE_FIELDS).issubset(PROVENANCE_KEYS), "spec_invalid", "a declared UI field is absent from the provenance record")
    provenance = spec["provenance_record_schema"]
    _require(provenance.get("required_keys") == list(PROVENANCE_KEYS), "spec_invalid", "provenance keys drifted")
    _require(provenance.get("fixture_selector_keys") == list(PROVENANCE_SELECTOR_KEYS), "spec_invalid", "provenance selector keys drifted")
    _require(provenance.get("null_fields") == list(NULL_PROVENANCE_FIELDS), "spec_invalid", "provenance null fields drifted")
    _require(provenance.get("unresolved_string_fields") == list(UNRESOLVED_STRING_FIELDS), "spec_invalid", "unresolved provenance fields drifted")
    _require(provenance.get("false_fields") == list(FALSE_PROVENANCE_FIELDS), "spec_invalid", "provenance false fields drifted")
    _require(provenance.get("target_free_sentinel_fields") == list(TARGET_SENTINEL_FIELDS), "spec_invalid", "target sentinel fields drifted")
    _require(provenance.get("target_free_sentinel") == TARGET_FREE_SENTINEL, "spec_invalid", "the target-free sentinel drifted")
    _require(provenance.get("null_structure_hash_fields") == list(NULL_STRUCTURE_HASH_FIELDS), "spec_invalid", "the null structure-hash field drifted")
    _require(provenance.get("recorded_fixture_hash_fields") == {field: role for field, role in RECORDED_HASH_FIELDS}, "spec_invalid", "recorded fixture hash fields drifted")
    _require(provenance.get("recorded_count_fields") == list(COUNT_FIELDS), "spec_invalid", "recorded count fields drifted")
    _require(provenance.get("recorded_count_type") == RECORDED_COUNT_TYPE, "spec_invalid", "recorded count type drifted")
    _require(provenance.get("includes_own_sha256") is False, "spec_invalid", "the provenance record must not contain its own SHA-256")
    _require(provenance.get("hashing_boundary") == PROVENANCE_HASH_BOUNDARY, "spec_invalid", "the provenance hashing boundary drifted")
    _require(provenance.get("runtime_status_value") == "not_measured", "spec_invalid", "runtime status drifted")
    _require("provenance_record_sha256" not in PROVENANCE_KEYS, "spec_invalid", "the provenance self-hash is not a provenance key")
    _require("encoding normalization" in spec["rules"]["utf8_bom"], "spec_invalid", "BOM handling must stay encoding normalization")
    _require("not schema adaptation" in spec["rules"]["utf8_bom"], "spec_invalid", "BOM handling must not adapt the schema")
    _require("unique-core" in spec["rules"]["nullable_target_pdb_id"], "spec_invalid", "nullable PDB provenance must preserve the unique-core REF calibration set")
    _require("inventing structural evidence" in spec["rules"]["nullable_target_pdb_id"], "spec_invalid", "nullable PDB provenance must not invent structural evidence")
    raw_score = spec["raw_tier2_geometric_score"]
    _require(raw_score.get("observed_in_provisional_shortlist_export") is False, "spec_invalid", "the provisional shortlist observation drifted")
    _require(raw_score.get("availability") == "unresolved", "spec_invalid", "raw Tier 2 availability must stay unresolved")
    _require(raw_score.get("equation") is None, "spec_invalid", "ARP-1 does not supply a raw Tier 2 equation")
    _require(raw_score.get("direction") is None, "spec_invalid", "ARP-1 does not supply a raw Tier 2 direction")
    _require(raw_score.get("comparison_scope") == "unresolved", "spec_invalid", "raw Tier 2 comparison scope must stay unresolved")
    _require(raw_score.get("absence_from_provisional_shortlist_is_not_definitional") is True, "spec_invalid", "raw Tier 2 absence must not be definitional")
    bank = spec["control_bank"]
    _require(bank.get("identifier") is None and bank.get("sha256") is None and bank.get("provenance") is None, "spec_invalid", "control-bank identity must stay unresolved")
    _require(bank.get("status") == "unresolved", "spec_invalid", "control-bank status must stay unresolved")
    identity = spec["deployment_identity"]
    _require(identity.get("deployment_verified") is False, "deployment_verified_refused", "ARP-1 cannot mark the deployment verified")
    _require(identity.get("status") == "unresolved", "spec_invalid", "deployment identity must stay unresolved")
    _require(identity.get("deployment_version") is None, "spec_invalid", "deployment version must stay unresolved")
    _require(identity.get("deployment_schema_version") is None, "spec_invalid", "deployment schema version must stay unresolved")
    _require(identity.get("deployment_code_revision") is None, "spec_invalid", "deployment code revision must stay unresolved")
    _require(spec["runtime_fields"] == list(RUNTIME_FIELDS), "spec_invalid", "runtime fields drifted")
    _require(spec["row_accounting_fields"] == list(ROW_ACCOUNTING_FIELDS), "spec_invalid", "row-accounting fields drifted")
    target_fields = spec["target_configuration_fields"]
    _require(target_fields.get("fields") == list(TARGET_CONFIGURATION_FIELDS), "spec_invalid", "target configuration fields drifted")
    _require(target_fields.get("target_free_sentinel") == TARGET_FREE_SENTINEL, "spec_invalid", "the target-free sentinel drifted")
    questions = spec["unresolved_interface_questions"]
    _require(isinstance(questions, list), "spec_invalid", "unresolved questions are missing")
    question_ids = [item.get("id") for item in questions]
    _require(question_ids == list(UNRESOLVED_QUESTION_IDS), "spec_invalid", "unresolved question ids drifted")
    for item in questions:
        _require(item.get("status") == "unresolved" and item.get("value") is None, "spec_invalid", "an interface question was resolved in the draft")
    _require(isinstance(spec["schema_change_policy"], str) and "reviewed specification revision" in spec["schema_change_policy"], "spec_invalid", "the schema-change policy drifted")
    boundary = spec["interpretation_boundary"]
    _require(boundary.get("combined_tier1_tier2_score") is False, "combined_score_refused", "ARP-1 defines no combined Tier 1 and Tier 2 score")
    _require(boundary.get("binding_interpretation") is False, "spec_invalid", "binding interpretation is not allowed")
    _require(boundary.get("affinity_interpretation") is False, "spec_invalid", "affinity interpretation is not allowed")
    _require(boundary.get("selectivity_interpretation") is False, "spec_invalid", "selectivity interpretation is not allowed")
    evidence = spec["provisional_interface_evidence"]
    _require(evidence.get("deployment_verified") is False, "deployment_verified_refused", "provisional evidence is not deployment verification")
    _require(evidence.get("candidate_upload_column_order") == list(CANDIDATE_COLUMNS), "spec_schema_drift", "provisional candidate columns drifted")
    _require(evidence.get("reference_upload_column_order") == list(REFERENCE_COLUMNS), "spec_schema_drift", "provisional reference columns drifted")
    _require(evidence.get("shortlist_export_column_order") == list(SHORTLIST_COLUMNS), "spec_schema_drift", "provisional shortlist columns drifted")
    _require(evidence.get("upload_ids_observed_in_column") == "candidate", "spec_invalid", "the observed id column drifted")
    _require(evidence.get("target_free_compatibility_literal") == "not evaluated", "spec_invalid", "the compatibility literal drifted")
    _require(evidence.get("shuffle_literals") == list(SHUFFLE_TOKENS), "spec_invalid", "the shuffle literals drifted")
    _require(evidence.get("validation_outcomes_reused") is False, "spec_invalid", "VALIDATION outcomes must not be reused")
    _require(evidence.get("target_decisions_reused") is False, "spec_invalid", "target decisions must not be reused")
    _require(evidence.get("raw_tier2_geometric_score_observed_in_shortlist") is False, "spec_invalid", "the provisional raw-score observation drifted")
    _require(evidence.get("raw_tier2_absence_is_not_definitional") is True, "spec_invalid", "raw Tier 2 absence must not be definitional")
    _require(evidence.get("settings_absent_from_csv_captured_from_ui") is True, "spec_invalid", "UI capture of missing settings drifted")


def load_spec():
    spec_bytes = read_bytes(spec_path())
    try:
        spec = json.loads(spec_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AptaRankIOError("spec_invalid", "the interface spec is not readable JSON") from exc
    validate_spec_document(spec)
    plan_bytes = read_bytes(os.path.join(repo_root(), GOVERNING_PLAN_RELATIVE))
    actual = sha256_bytes(plan_bytes)
    if actual != spec["governing_plan"]["sha256"]:
        raise AptaRankIOError("governing_plan_hash_mismatch", "the governing plan hash does not match the draft spec")
    return spec, spec_bytes


def load_fixture_bytes(name):
    if not isinstance(name, str) or os.path.basename(name) != name or name in FORBIDDEN_FIXTURE_NAMES:
        raise AptaRankIOError("fixture_name_refused", "ARP-1 loads only bundled synthetic fixture names")
    path = os.path.join(fixture_root(), name)
    root = os.path.realpath(fixture_root())
    resolved = os.path.realpath(path)
    if os.path.dirname(resolved) != root:
        raise AptaRankIOError("fixture_name_refused", "ARP-1 loads only bundled synthetic fixture names")
    return read_bytes(resolved)


def load_bundled_parts(mapping=None):
    selected = BUNDLED_FIXTURES if mapping is None else mapping
    return {role: load_fixture_bytes(name) for role, name in selected.items()}


def classify_likeness(token):
    if not isinstance(token, str):
        return "malformed"
    if token.lower() in NONFINITE_TOKENS:
        return "nonfinite"
    if FINITE_DECIMAL_TEXT.fullmatch(token) is None:
        return "malformed"
    try:
        value = float(token)
    except ValueError:
        return "malformed"
    if not math.isfinite(value):
        return "nonfinite"
    return "finite"


def csv_logical_text(payload, errors, role):
    """Decode CSV text, stripping one leading UTF-8 BOM.

    The caller hashes the original bytes. Stripping the leading BOM is
    encoding normalization, not schema adaptation. A BOM anywhere else fails.
    """
    if payload.startswith(UTF8_BOM):
        if UTF8_BOM in payload[len(UTF8_BOM):]:
            errors.add("unexpected_bom", role + " has a UTF-8 BOM outside the first bytes")
            return None
        encoded = payload[len(UTF8_BOM):]
    else:
        if UTF8_BOM in payload:
            errors.add("unexpected_bom", role + " has a UTF-8 BOM outside the first bytes")
            return None
        encoded = payload
    try:
        return encoded.decode("utf-8")
    except UnicodeDecodeError:
        errors.add("malformed_bytes", role + " is not UTF-8")
        return None


def parse_csv_rows(payload, expected_columns, errors, role):
    text = csv_logical_text(payload, errors, role)
    if text is None:
        return None
    try:
        table = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error:
        errors.add("malformed_csv", role + " is not a readable CSV")
        return None
    if not table or table[0] != list(expected_columns):
        errors.add("schema_mismatch", role + " " + SCHEMA_MISMATCH_DETAIL)
        return None
    rows = []
    for index, raw in enumerate(table[1:], start=1):
        if len(raw) != len(expected_columns):
            errors.add("ragged_row", role + " row %d does not match the header width" % index)
            continue
        rows.append({column: raw[position] for position, column in enumerate(expected_columns)})
    return rows


def parse_json_object(payload, errors, role):
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        errors.add("malformed_bytes", role + " is not UTF-8")
        return None
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        errors.add("malformed_json", role + " is not a JSON object")
        return None
    if not isinstance(document, dict):
        errors.add("malformed_json", role + " is not a JSON object")
        return None
    return document


def _repeated_ids(values):
    seen = set()
    repeated = []
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    return repeated


def _label(candidate_id, index):
    if isinstance(candidate_id, str) and ID_TEXT.fullmatch(candidate_id):
        return candidate_id
    return "row %d" % index


def _check_id(value, errors, code_prefix, index):
    if not isinstance(value, str) or ID_TEXT.fullmatch(value) is None:
        errors.add("empty_id", "%s row %d has an empty id" % (code_prefix, index))
        return False
    return True


def _contract_profile_id(value):
    return isinstance(value, str) and ID_TEXT.fullmatch(value) is not None


def _empty_reconciliation():
    return {
        "upload_ids": [],
        "export_ids": [],
        "failure_ids": [],
        "expected_ids": [],
        "dispositions": [],
        "missing_count": 0,
        "extra_count": 0,
        "duplicate_upload_count": 0,
        "duplicate_export_count": 0,
    }


def _check_sequence(value, errors, label, role):
    if not isinstance(value, str) or SEQUENCE_TEXT.fullmatch(value) is None:
        errors.add("sequence_alphabet", "%s %s sequence is not uppercase A, C, G and U" % (role, label))
        return False
    return True


def _check_candidate_rows(rows, errors):
    if rows is None:
        return
    for index, row in enumerate(rows, start=1):
        valid_id = _check_id(row["id"], errors, "candidate upload", index)
        label = row["id"] if valid_id else "row %d" % index
        _check_sequence(row["sequence"], errors, label, "candidate")
    for candidate_id in _repeated_ids([row["id"] for row in rows]):
        errors.add("duplicate_candidate_id", "candidate id %s is duplicated in the upload" % candidate_id)


def _check_reference_rows(rows, errors):
    if rows is None:
        return
    for index, row in enumerate(rows, start=1):
        valid_id = _check_id(row["id"], errors, "reference upload", index)
        label = row["id"] if valid_id else "row %d" % index
        _check_sequence(row["sequence"], errors, label, "reference")
        for field in ("target_name", "source_reference"):
            if not isinstance(row[field], str) or UNINTERPRETED_TEXT.fullmatch(row[field]) is None:
                errors.add("empty_reference_field", "reference %s %s is empty" % (label, field))
        pdb_id = row["target_pdb_id"]
        # A blank cell stays blank. Do not substitute a sentinel or an invented PDB id.
        if not isinstance(pdb_id, str) or (pdb_id != "" and UNINTERPRETED_TEXT.fullmatch(pdb_id) is None):
            errors.add(
                "invalid_target_pdb_id",
                "reference %s target_pdb_id must be blank or free of leading and trailing whitespace" % label,
            )
    for reference_id in _repeated_ids([row["id"] for row in rows]):
        errors.add("duplicate_reference_id", "reference id %s is duplicated" % reference_id)


def _check_shortlist_rows(rows, errors, profile):
    parsed_lengths = []
    if rows is None:
        return parsed_lengths
    ranks = []
    for index, row in enumerate(rows, start=1):
        label = _label(row["candidate"], index)
        if not _check_id(row["candidate"], errors, "shortlist", index):
            label = "row %d" % index
        _check_sequence(row["sequence"], errors, label, "shortlist candidate")
        kind = classify_likeness(row["aptamer-likeness"])
        if kind == "malformed":
            errors.add("malformed_aptamer_likeness", "shortlist candidate %s aptamer-likeness is malformed" % label)
        elif kind == "nonfinite":
            errors.add("nonfinite_aptamer_likeness", "shortlist candidate %s aptamer-likeness is not finite" % label)
        if profile is not None:
            if row["compatibility"] not in profile["compatibility_allowed_tokens"]:
                errors.add(
                    "invalid_compatibility",
                    "shortlist candidate %s compatibility token is not allowed for the selected profile" % label,
                )
            if row["shuffle"] not in profile["shuffle_allowed_tokens"]:
                errors.add(
                    "invalid_shuffle",
                    "shortlist candidate %s shuffle token is not allowed for the selected profile" % label,
                )
        if POSITIVE_INT_TEXT.fullmatch(row["rank"]) is None:
            errors.add("malformed_rank", "shortlist candidate %s rank is not a positive integer" % label)
        else:
            ranks.append(row["rank"])
        if NONNEGATIVE_INT_TEXT.fullmatch(row["len"]) is None:
            errors.add("length_mismatch", "shortlist candidate %s len is not a nonnegative integer" % label)
            parsed_lengths.append(None)
        else:
            parsed_lengths.append(int(row["len"]))
    for rank in _repeated_ids(ranks):
        errors.add("duplicate_rank", "shortlist rank %s is duplicated" % rank)
    return parsed_lengths


def _check_manifest(document, errors):
    if document is None:
        return None
    if set(document) != set(MANIFEST_KEYS) or document.get("fixture_role") != "synthetic_expected_cell_manifest":
        errors.add("fixture_schema_mismatch", "the expected-cell manifest does not match the draft schema")
        return None
    if document.get("expected_export_fields") != list(SHORTLIST_COLUMNS):
        errors.add("schema_mismatch", "expected-cell manifest " + SCHEMA_MISMATCH_DETAIL)
        return None
    identifiers = document.get("expected_candidate_ids")
    if not isinstance(identifiers, list):
        errors.add("fixture_schema_mismatch", "expected candidate ids are missing")
        return None
    structurally_valid = True
    for index, candidate_id in enumerate(identifiers, start=1):
        if not isinstance(candidate_id, str):
            errors.add(
                "invalid_expected_candidate_id",
                "expected candidate id at position %d is not a nonempty string" % index,
            )
            structurally_valid = False
            continue
        _check_id(candidate_id, errors, "expected manifest", index)
    for candidate_id in _repeated_ids(identifiers):
        errors.add("duplicate_expected_id", "expected candidate id %s is duplicated" % candidate_id)
    if not structurally_valid:
        return None
    return document


def _check_failures(document, errors):
    if document is None:
        return None
    if set(document) != set(FAILURE_KEYS) or document.get("fixture_role") != "synthetic_failure_accounting":
        errors.add("fixture_schema_mismatch", "the failure-accounting record does not match the draft schema")
        return None
    failures = document.get("failures")
    if not isinstance(failures, list):
        errors.add("fixture_schema_mismatch", "failure records are missing")
        return None
    structurally_valid = True
    string_ids = []
    for index, item in enumerate(failures, start=1):
        if not isinstance(item, dict) or set(item) != set(FAILURE_ITEM_KEYS):
            errors.add("fixture_schema_mismatch", "failure record %d does not match the draft schema" % index)
            if isinstance(item, dict) and "candidate_id" in item and not isinstance(item["candidate_id"], str):
                errors.add(
                    "invalid_failure_candidate_id",
                    "failure candidate id at position %d is not a nonempty string" % index,
                )
                structurally_valid = False
            continue
        candidate_id = item["candidate_id"]
        if not isinstance(candidate_id, str):
            errors.add(
                "invalid_failure_candidate_id",
                "failure candidate id at position %d is not a nonempty string" % index,
            )
            structurally_valid = False
            reason = item["reason"]
            if not isinstance(reason, str) or not reason.strip():
                errors.add(
                    "missing_failure_reason",
                    "failure record at position %d is missing a nonempty reason" % index,
                )
            continue
        valid_id = _check_id(candidate_id, errors, "failure accounting", index)
        reason = item["reason"]
        if not isinstance(reason, str) or not reason.strip():
            label = candidate_id if valid_id else "row %d" % index
            errors.add("missing_failure_reason", "failure record for candidate %s is missing a nonempty reason" % label)
        string_ids.append(candidate_id)
    for candidate_id in _repeated_ids(string_ids):
        errors.add("duplicate_failure_id", "failure candidate id %s is duplicated" % candidate_id)
    if not structurally_valid:
        return None
    return document


def _check_provenance(document, errors, parts):
    if document is None:
        return None
    if not isinstance(document, dict):
        errors.add("fixture_schema_mismatch", "the provenance record does not match the draft schema")
        return None
    missing = [key for key in PROVENANCE_KEYS if key not in document]
    extra = sorted(key for key in document if key not in PROVENANCE_KEYS)
    if missing or extra:
        for key in missing:
            errors.add("missing_provenance_field", "provenance is missing required field %s" % key)
        for key in extra:
            errors.add("unexpected_provenance_field", "provenance contains unexpected field %s" % key)
        return None
    if document.get("fixture_role") != "synthetic_run_provenance":
        errors.add("fixture_schema_mismatch", "the provenance record does not match the draft schema")
        return None
    for field in ("run_id", "operator", "started_at", "finished_at"):
        if not isinstance(document.get(field), str) or not document[field].strip():
            errors.add("fixture_schema_mismatch", "provenance %s is empty" % field)
    for field in NULL_PROVENANCE_FIELDS:
        if document.get(field) is not None:
            errors.add("unresolved_field_must_stay_unresolved", "provenance %s must stay unresolved" % field)
    for field in UNRESOLVED_STRING_FIELDS:
        if document.get(field) != "unresolved":
            errors.add("unresolved_field_must_stay_unresolved", "provenance %s must stay unresolved" % field)
    if document.get("deployment_verified") is True:
        errors.add("deployment_verified_refused", "ARP-1 cannot mark the deployment verified")
    elif document.get("deployment_verified") is not False:
        errors.add("fixture_schema_mismatch", "provenance deployment_verified must remain false")
    if document.get("ui_capture_complete") is True:
        errors.add("ui_preflight_not_completed", "the new synthetic UI preflight is not recorded as complete")
    elif document.get("ui_capture_complete") is not False:
        errors.add("fixture_schema_mismatch", "provenance ui_capture_complete must remain false")
    if document.get("runtime_status") != "not_measured":
        errors.add("fixture_schema_mismatch", "synthetic runtime_status must stay not_measured")
    if document.get("warnings") != [] or document.get("rerun_lineage") != []:
        errors.add("fixture_schema_mismatch", "synthetic warnings and rerun lineage must be empty lists")
    for field in TARGET_SENTINEL_FIELDS:
        if document.get(field) != TARGET_FREE_SENTINEL:
            errors.add("target_value_not_allowed_in_profile", "target-free provenance %s must use the explicit sentinel" % field)
    for field in NULL_STRUCTURE_HASH_FIELDS:
        if document.get(field) is not None:
            errors.add("target_value_not_allowed_in_profile", "target-free provenance %s must stay null" % field)
    for field, role in RECORDED_HASH_FIELDS:
        if document.get(field) != sha256_bytes(parts[role]):
            errors.add("fixture_hash_mismatch", "provenance %s does not match the supplied %s bytes" % (field, role))
    return document


def _check_recorded_counts(provenance, candidates, exports, failures, manifest, errors):
    if None in (provenance, candidates, exports, failures, manifest):
        return
    actual = {
        "expected_row_count": len(manifest["expected_candidate_ids"]),
        "exported_row_count": len(exports),
        "failed_row_count": len(failures["failures"]),
    }
    for field, count in actual.items():
        recorded = provenance.get(field)
        # type() rejects bool, which is a subclass of int, and rejects every float.
        if type(recorded) is not int or recorded < 0:
            errors.add(
                "invalid_row_count_type",
                "provenance %s must be a nonnegative JSON integer" % field,
            )
        elif recorded != count:
            errors.add("row_count_mismatch", "provenance %s does not match the actual file accounting" % field)


def _selected_profile(manifest, failures, provenance, spec, errors):
    sources = (
        ("expected-cell manifest", manifest),
        ("failure accounting", failures),
        ("provenance", provenance),
    )
    names = []
    invalid = False
    for label, document in sources:
        if not isinstance(document, dict) or "profile_id" not in document:
            continue
        profile_id = document["profile_id"]
        if not _contract_profile_id(profile_id):
            errors.add("invalid_profile_id", "%s profile_id is not a nonempty string" % label)
            invalid = True
            continue
        names.append(profile_id)
    if invalid:
        return None
    if len(names) != 3 or len(set(names)) != 1 or names[0] not in spec["synthetic_run_profiles"]:
        errors.add("profile_not_selected", "a single synthetic run profile must be selected explicitly")
        return None
    return spec["synthetic_run_profiles"][names[0]]


def _upload_sequences(rows):
    sequences = {}
    repeated = set(_repeated_ids([row["id"] for row in rows]))
    for row in rows:
        if row["id"] in repeated or not row["id"]:
            continue
        sequences[row["id"]] = row["sequence"]
    return sequences


def sequence_matches_by_id(upload_rows, export_rows):
    """Return per-export sequence matches joined by candidate id.

    Row position is not a key. Callers that align the two lists by index are
    not using this function.
    """
    sequences = _upload_sequences(upload_rows)
    return [sequences[row["candidate"]] == row["sequence"] for row in export_rows]


def _reject_unhashable_join_ids(failure_items, expected_ids, errors):
    """Record malformed ids and stop before set, sort, or dict-key use."""
    rejected = False
    if isinstance(expected_ids, list):
        for index, candidate_id in enumerate(expected_ids, start=1):
            if not isinstance(candidate_id, str):
                errors.add(
                    "invalid_expected_candidate_id",
                    "expected candidate id at position %d is not a nonempty string" % index,
                )
                rejected = True
    else:
        errors.add("invalid_expected_candidate_id", "expected candidate ids are not a list of strings")
        rejected = True
    if isinstance(failure_items, list):
        for index, item in enumerate(failure_items, start=1):
            if not isinstance(item, dict) or "candidate_id" not in item:
                continue
            if not isinstance(item["candidate_id"], str):
                errors.add(
                    "invalid_failure_candidate_id",
                    "failure candidate id at position %d is not a nonempty string" % index,
                )
                rejected = True
    return rejected


def _reconcile(candidates, exports, failures, manifest, parsed_lengths, errors):
    upload_ids = [row["id"] for row in candidates]
    export_ids = [row["candidate"] for row in exports]
    failure_items = failures["failures"]
    expected_ids = list(manifest["expected_candidate_ids"])
    if _reject_unhashable_join_ids(failure_items, expected_ids, errors):
        return _empty_reconciliation()
    failure_ids = [
        item.get("candidate_id")
        for item in failure_items
        if isinstance(item, dict) and isinstance(item.get("candidate_id"), str)
    ]
    repeated_uploads = set(_repeated_ids(upload_ids))
    repeated_exports = set(_repeated_ids(export_ids))
    for candidate_id in _repeated_ids(export_ids):
        errors.add("duplicate_exported_id", "exported candidate id %s is duplicated" % candidate_id)
    if not repeated_uploads and set(upload_ids) != set(expected_ids):
        for candidate_id in sorted(set(expected_ids) - set(upload_ids)):
            errors.add("expected_manifest_mismatch", "expected candidate %s is absent from the upload" % candidate_id)
        for candidate_id in sorted(set(upload_ids) - set(expected_ids)):
            errors.add("expected_manifest_mismatch", "uploaded candidate %s is absent from the expected manifest" % candidate_id)
    exported = set(export_ids)
    failed = set(failure_ids)
    expected = set(expected_ids)
    for candidate_id in sorted(exported & failed):
        errors.add("candidate_accounted_twice", "candidate %s is both exported and failed" % candidate_id)
    missing = sorted(expected - exported - failed)
    for candidate_id in missing:
        errors.add("missing_candidate_id", "candidate %s is neither exported nor explicitly failed" % candidate_id)
    extra = sorted(exported - expected)
    for candidate_id in extra:
        errors.add("unexpected_candidate_id", "exported candidate %s is not in the expected set" % candidate_id)
    for candidate_id in sorted(failed - expected):
        errors.add("unexpected_failure_id", "failed candidate %s is not in the expected set" % candidate_id)
    upload_sequences = _upload_sequences(candidates)
    for index, row in enumerate(exports):
        candidate_id = row["candidate"]
        if candidate_id in repeated_exports or candidate_id not in upload_sequences:
            continue
        upload_sequence = upload_sequences[candidate_id]
        if row["sequence"] != upload_sequence:
            errors.add("sequence_changed", "candidate %s exported sequence does not match the upload" % candidate_id)
        parsed_len = parsed_lengths[index]
        if parsed_len is not None and (parsed_len != len(upload_sequence) or parsed_len != len(row["sequence"])):
            errors.add("length_mismatch", "candidate %s exported len does not match the sequence length" % candidate_id)
    dispositions = []
    reasons_present = {}
    for item in failure_items:
        if not isinstance(item, dict) or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            continue
        candidate_id = item.get("candidate_id")
        if isinstance(candidate_id, str):
            reasons_present[candidate_id] = True
    for candidate_id in expected_ids:
        if candidate_id in exported and candidate_id not in failed:
            dispositions.append(
                {"candidate_id": candidate_id, "disposition": "exported", "failure_reason_present": False}
            )
        elif candidate_id in failed and candidate_id not in exported:
            dispositions.append(
                {
                    "candidate_id": candidate_id,
                    "disposition": "technical_failure",
                    "failure_reason_present": bool(reasons_present.get(candidate_id)),
                }
            )
    return {
        "upload_ids": upload_ids,
        "export_ids": export_ids,
        "failure_ids": failure_ids,
        "expected_ids": expected_ids,
        "dispositions": dispositions,
        "missing_count": len(missing),
        "extra_count": len(extra),
        "duplicate_upload_count": len(repeated_uploads),
        "duplicate_export_count": len(repeated_exports),
    }


def _collect_sequences(*tables):
    found = []
    for rows in tables:
        if not rows:
            continue
        for row in rows:
            sequence = row.get("sequence")
            if isinstance(sequence, str) and sequence:
                found.append(sequence)
    return found


def ensure_sequence_free(report, sequences):
    encoded = json.dumps(report)
    for sequence in sequences:
        if sequence in encoded:
            raise AptaRankIOError("report_contained_sequence", "the preflight report contained a sequence")


def _question_view(spec):
    view = []
    for item in spec["unresolved_interface_questions"]:
        view.append(
            {
                "id": item["id"],
                "status": item["status"],
                "value": item["value"],
                "note": item.get("note"),
            }
        )
    return view


def build_report(spec, spec_bytes, parts, summary, reference_count, profile, revision):
    raw_score = spec["raw_tier2_geometric_score"]
    bank = spec["control_bank"]
    identity = spec["deployment_identity"]
    boundary = spec["interpretation_boundary"]
    dispositions = summary["dispositions"]
    failed_rows = sum(1 for item in dispositions if item["disposition"] == "technical_failure")
    exported_rows = sum(1 for item in dispositions if item["disposition"] == "exported")
    accounting = {
        "candidate_upload_rows": len(summary["upload_ids"]),
        "reference_upload_rows": reference_count,
        "expected_candidates": len(summary["expected_ids"]),
        "exported_rows": len(summary["export_ids"]),
        "failed_rows": len(summary["failure_ids"]),
        "duplicate_candidate_ids": summary["duplicate_upload_count"],
        "duplicate_reference_ids": 0,
        "duplicate_exported_ids": summary["duplicate_export_count"],
        "missing_candidate_ids": summary["missing_count"],
        "extra_exported_ids": summary["extra_count"],
        "unaccounted_candidates": summary["missing_count"],
        "silent_drops": 0,
        "rows_imputed_as_zero": 0,
    }
    report = {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "spec_status": spec["status"],
        "deployment_verified": False,
        "pass_fail": "pass",
        "technical_preflight": True,
        "scientific_result": False,
        "technical_versus_scientific": TECHNICAL_NOT_SCIENTIFIC,
        "profile_id": profile["profile_id"],
        "join_key": JOIN_KEY,
        "join_uses_row_position": JOIN_USES_ROW_POSITION,
        "impute_missing_as_zero": IMPUTE_MISSING_AS_ZERO,
        "combined_tier1_tier2_score": False,
        "binding_interpretation": boundary["binding_interpretation"],
        "affinity_interpretation": boundary["affinity_interpretation"],
        "selectivity_interpretation": boundary["selectivity_interpretation"],
        "schemas": {
            "candidate_upload": list(spec["candidate_upload_column_order"]),
            "reference_upload": list(spec["reference_upload_column_order"]),
            "shortlist_export": list(spec["shortlist_export_column_order"]),
        },
        "column_types": spec["column_types"],
        "schema_change_policy": spec["schema_change_policy"],
        "sha256": {role: sha256_bytes(parts[role]) for role in HASHED_BYTE_ROLES},
        "provenance_hash_boundary": PROVENANCE_HASH_BOUNDARY,
        "provenance_record_includes_own_sha256": False,
        "interface_spec_sha256": sha256_bytes(spec_bytes),
        "row_accounting": accounting,
        "candidate_dispositions": dispositions,
        "export_candidate_id_order": list(summary["export_ids"]),
        "upload_candidate_id_order": list(summary["upload_ids"]),
        "candidates_accounted_exactly_once": exported_rows + failed_rows == len(summary["expected_ids"]) and len(summary["expected_ids"]) == len({item["candidate_id"] for item in dispositions}),
        "raw_tier2_score_availability": raw_score["availability"],
        "raw_tier2_equation": raw_score["equation"],
        "raw_tier2_direction": raw_score["direction"],
        "raw_tier2_comparison_scope": raw_score["comparison_scope"],
        "raw_tier2_absence_from_provisional_shortlist_is_not_definitional": True,
        "control_bank_identifier": bank["identifier"],
        "control_bank_hash": bank["sha256"],
        "control_bank_provenance": bank["provenance"],
        "control_bank_status": bank["status"],
        "deployment_version": identity["deployment_version"],
        "deployment_schema_version": identity["deployment_schema_version"],
        "deployment_code_revision": identity["deployment_code_revision"],
        "preset_value": profile["preset_value"],
        "runtime": {"runtime_seconds": None, "runtime_status": "not_measured"},
        "unresolved_interface_questions": _question_view(spec),
        "data_access": {
            "eval_loaded": False,
            "ref_loaded": False,
            "validation_loaded": False,
            "train_loaded": False,
            "production_pools_loaded": False,
            "checkpoints_loaded": False,
            "statement": NO_PROTECTED_STATEMENT,
        },
        "protected_or_production_data_loaded": False,
        "protected_or_production_statement": NO_PRODUCTION_STATEMENT,
        "errors": [],
    }
    if revision is not None:
        report["package_revision"] = revision
    return report


def validate_interface(parts, spec, spec_bytes, revision=None):
    """Validate synthetic upload, export, and accounting bytes.

    This function does not open paths. Join is by candidate id.
    """
    validate_spec_document(spec)
    _require(isinstance(parts, dict) and set(parts) == set(HASHED_BYTE_ROLES), "parts_invalid", "the synthetic parts are incomplete")
    for role in HASHED_BYTE_ROLES:
        _require(isinstance(parts[role], bytes), "parts_invalid", "each synthetic part must be bytes")
    errors = ErrorList()
    manifest_document = parse_json_object(parts["expected_cell_manifest"], errors, "expected-cell manifest")
    failure_document = parse_json_object(parts["failure_accounting"], errors, "failure accounting")
    provenance_document = parse_json_object(parts["provenance"], errors, "provenance")
    manifest = _check_manifest(manifest_document, errors)
    failures = _check_failures(failure_document, errors)
    profile = _selected_profile(manifest_document, failure_document, provenance_document, spec, errors)
    provenance = _check_provenance(provenance_document, errors, parts)
    candidates = parse_csv_rows(parts["candidate_upload"], CANDIDATE_COLUMNS, errors, "candidate upload")
    references = parse_csv_rows(parts["reference_upload"], REFERENCE_COLUMNS, errors, "reference upload")
    exports = parse_csv_rows(parts["shortlist_export"], SHORTLIST_COLUMNS, errors, "shortlist export")
    _check_candidate_rows(candidates, errors)
    _check_reference_rows(references, errors)
    parsed_lengths = _check_shortlist_rows(exports, errors, profile)
    summary = None
    if None not in (candidates, references, exports, failures, manifest, provenance, profile):
        summary = _reconcile(candidates, exports, failures, manifest, parsed_lengths, errors)
    _check_recorded_counts(provenance, candidates, exports, failures, manifest, errors)
    errors.raise_if_any()
    report = build_report(
        spec,
        spec_bytes,
        parts,
        summary,
        0 if references is None else len(references),
        profile,
        revision,
    )
    ensure_sequence_free(report, _collect_sequences(candidates, references, exports))
    return report


def _git_text(args):
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def demonstration_revision(spec, spec_bytes):
    return {
        "git_head": _git_text(["rev-parse", "HEAD"]),
        "git_branch": _git_text(["rev-parse", "--abbrev-ref", "HEAD"]),
        "preflight_module_sha256": sha256_bytes(read_bytes(os.path.abspath(__file__))),
        "interface_spec_sha256": sha256_bytes(spec_bytes),
        "governing_plan_sha256": spec["governing_plan"]["sha256"],
    }


def run_demonstration():
    spec, spec_bytes = load_spec()
    parts = load_bundled_parts()
    revision = demonstration_revision(spec, spec_bytes)
    return validate_interface(parts, spec, spec_bytes, revision=revision)


def render_report(report):
    lines = [
        "ARP-1 synthetic AptaRank I/O preflight",
        "package_id: " + report["package_id"],
        "schema_version: " + report["schema_version"],
        "spec_status: " + report["spec_status"],
        "deployment_verified: " + json.dumps(report["deployment_verified"]),
        "pass_fail: " + report["pass_fail"],
        "status: " + report["status"],
        "technical_preflight: " + json.dumps(report["technical_preflight"]),
        "scientific_result: " + json.dumps(report["scientific_result"]),
        report["technical_versus_scientific"],
        "profile_id: " + report["profile_id"],
        "join_key: " + report["join_key"],
        "join_uses_row_position: " + json.dumps(report["join_uses_row_position"]),
        "combined_tier1_tier2_score: " + json.dumps(report["combined_tier1_tier2_score"]),
        "binding_interpretation: " + json.dumps(report["binding_interpretation"]),
        "affinity_interpretation: " + json.dumps(report["affinity_interpretation"]),
        "selectivity_interpretation: " + json.dumps(report["selectivity_interpretation"]),
        "candidate_upload_columns: " + json.dumps(report["schemas"]["candidate_upload"]),
        "reference_upload_columns: " + json.dumps(report["schemas"]["reference_upload"]),
        "shortlist_export_columns: " + json.dumps(report["schemas"]["shortlist_export"]),
        "raw_tier2_score_availability: " + report["raw_tier2_score_availability"],
        "raw_tier2_equation: " + json.dumps(report["raw_tier2_equation"]),
        "raw_tier2_direction: " + json.dumps(report["raw_tier2_direction"]),
        "raw_tier2_comparison_scope: " + report["raw_tier2_comparison_scope"],
        "control_bank_identifier: " + json.dumps(report["control_bank_identifier"]),
        "control_bank_hash: " + json.dumps(report["control_bank_hash"]),
        "control_bank_provenance: " + json.dumps(report["control_bank_provenance"]),
        "control_bank_status: " + report["control_bank_status"],
        "deployment_version: " + json.dumps(report["deployment_version"]),
        "deployment_schema_version: " + json.dumps(report["deployment_schema_version"]),
        "deployment_code_revision: " + json.dumps(report["deployment_code_revision"]),
        "preset_value: " + json.dumps(report["preset_value"]),
        "runtime_seconds: " + json.dumps(report["runtime"]["runtime_seconds"]),
        "runtime_status: " + report["runtime"]["runtime_status"],
        report["data_access"]["statement"],
        report["protected_or_production_statement"],
        "row_accounting:",
    ]
    for field in ROW_ACCOUNTING_FIELDS:
        lines.append("  %s: %s" % (field, report["row_accounting"][field]))
    lines.append("candidates_accounted_exactly_once: " + json.dumps(report["candidates_accounted_exactly_once"]))
    lines.append("sha256:")
    for role in HASHED_BYTE_ROLES:
        lines.append("  %s: %s" % (role, report["sha256"][role]))
    lines.append("provenance_record_includes_own_sha256: " + json.dumps(report["provenance_record_includes_own_sha256"]))
    lines.append("provenance_hash_boundary: " + report["provenance_hash_boundary"])
    lines.append("interface_spec_sha256: " + report["interface_spec_sha256"])
    lines.append("unresolved_interface_questions:")
    for item in report["unresolved_interface_questions"]:
        lines.append("  unresolved: " + item["id"])
    lines.append("candidate_dispositions:")
    for item in report["candidate_dispositions"]:
        lines.append("  %s: %s" % (item["candidate_id"], item["disposition"]))
    lines.append("export_candidate_id_order: " + json.dumps(report["export_candidate_id_order"]))
    lines.append("upload_candidate_id_order: " + json.dumps(report["upload_candidate_id_order"]))
    lines.append(report["schema_change_policy"])
    if "package_revision" in report:
        revision = report["package_revision"]
        lines.append("git_head: " + revision["git_head"])
        lines.append("git_branch: " + revision["git_branch"])
        lines.append("preflight_module_sha256: " + revision["preflight_module_sha256"])
        lines.append("governing_plan_sha256: " + revision["governing_plan_sha256"])
    lines.append("errors: %d" % len(report["errors"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        sys.stderr.write(
            "arp1_cli_rejected: ARP-1 does not accept paths, unlock flags, or other arguments\n"
        )
        return 2
    report = run_demonstration()
    sys.stdout.write(render_report(report))
    return 0 if report["pass_fail"] == "pass" and report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

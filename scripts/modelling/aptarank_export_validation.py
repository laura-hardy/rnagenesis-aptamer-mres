#!/usr/bin/env python3
"""M9B-3 synthetic-only AptaRank downloaded-export validator.

The validator accepts caller-supplied upload bytes, private-membership bytes,
and shortlist bytes. It joins on the opaque candidate id, checks the public
shortlist fields recorded in M9B-1, and returns restricted joined bytes plus a
sequence-free manifest. Exported aptamer-likeness must be a finite decimal in
the closed interval [0, 1]; the original token is kept. Each private membership
is checked by reconstructing the M9B-2 input record from the uploaded sequence
and delegating to the pinned candidate-preparation normalizer. A private key
that is not already in canonical M9B-2 form fails closed. The validator does
not read a path, a production upload, a real download, or AptaRank. It does not
recompute a score. Deployed omission of export rows stays unresolved until
M9C, so the caller must name the missing-row policy. A missing row is not
given a rejection reason.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
from decimal import Decimal, InvalidOperation

PACKAGE_ID = "M9B-3"
SCHEMA_VERSION = "m9b-aptarank-export-validation-v1"
STATUS = "DEFINED_SYNTHETIC_ONLY_EXPORT_BEHAVIOR_UNRESOLVED"
STAGE = "M9B-3"
CONTRACT_RELATIVE = "config/modelling/aptarank_export_validation_contract.json"
CONTRACT_SHA256 = "5c5831c0d9e7e86c8ad9c3de7c569ea2db347ddf9941e6e743491cddfd4a700d"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
EVIDENCE_CONTRACT_RELATIVE = "config/modelling/aptarank_evidence_contract.json"
EVIDENCE_CONTRACT_SHA256 = "0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b"
PREPARATION_CONTRACT_RELATIVE = "config/modelling/aptarank_candidate_preparation_contract.json"
PREPARATION_CONTRACT_SHA256 = "3bcfbdf14cd7e777a0b2746f91d0335ba4876195f5012610157e5aa23e083096"
EVIDENCE_MODULE_RELATIVE = "scripts/modelling/aptarank_evidence_contract.py"
EVIDENCE_MODULE_SHA256 = "08e780e03108c0008174a4559840ce59a56d567b99376d3ad0272eb29a69bbcb"
PREPARATION_MODULE_RELATIVE = "scripts/modelling/aptarank_candidate_preparation.py"
PREPARATION_MODULE_SHA256 = "a4f5b047f2803e775d9521c226287487412495055446e192681957c3d42879ca"
IO_MODULE_RELATIVE = "scripts/modelling/aptarank_io_preflight.py"
IO_MODULE_SHA256 = "eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01"
PARSER_MODULE_RELATIVE = "scripts/modelling/generator_eval_parser.py"
PARSER_MODULE_SHA256 = "4a59ff8e557ee1948410c7f705a9c3772fe2570d4255b0d2185acee99137eaa2"
MODULE_RELATIVE = "scripts/modelling/aptarank_export_validation.py"
EXPORT_COLUMNS = (
    "rank",
    "candidate",
    "aptamer-likeness",
    "compatibility",
    "shuffle",
    "len",
    "sequence",
)
COLUMN_PHRASE = ", ".join(EXPORT_COLUMNS)
COMPATIBILITY_TOKENS = ("strong", "moderate", "weak", "not evaluated")
SHUFFLE_TOKENS = ("pass", "fail", "\u2014")
TOKEN_PHRASES = ("strong, moderate, weak", "not evaluated", "pass, fail", "U+2014")
RANK_PHRASES = (
    "descending Tier 1 score",
    "ascending candidate ID",
    "consecutive 1-based ordinal",
    "statistical minimum rank",
)
MISSING_ROW_POLICIES = ("require_complete", "allow_partial")
DISPOSITIONS = ("exported", "missing", "rejected")
JOINED_KEYS = (
    "candidate_id",
    "disposition",
    "sequence",
    "length",
    "rank",
    "aptamer-likeness",
    "compatibility",
    "shuffle",
    "rejection_reason",
    "memberships",
)
MEMBERSHIP_KEYS = (
    "condition",
    "comparison_role",
    "length",
    "multiplicity",
    "source_occurrences",
)
REJECTION_KEYS = ("candidate_id", "reason")
RESULT_KEYS = (
    "joined_candidates",
    "validation_manifest",
    "joined_candidates_sha256",
    "validation_manifest_sha256",
)
MANIFEST_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "stage",
    "synthetic",
    "production_inputs_opened",
    "aptarank_executed",
    "scientific_result",
    "deployment_verified",
    "live_export_behavior",
    "scores_recomputed",
    "biological_summaries_calculated",
    "rejection_reasons_invented",
    "impute_missing_as_zero",
    "join_key",
    "join_uses_row_position",
    "missing_row_policy",
    "pins",
    "upload_row_count",
    "private_membership_count",
    "exported_row_count",
    "missing_row_count",
    "rejected_row_count",
    "private_membership_count_by_condition",
    "candidate_upload_sha256",
    "private_membership_key_sha256",
    "shortlist_export_sha256",
    "rejection_records_supplied",
    "rejection_records_sha256",
    "joined_candidates_sha256",
    "candidate_upload_byte_count",
    "private_membership_key_byte_count",
    "shortlist_export_byte_count",
    "rejection_records_byte_count",
    "joined_candidates_byte_count",
)
PIN_ROLES = (
    "export_validation_contract",
    "governing_plan",
    "evidence_contract",
    "candidate_preparation_contract",
    "evidence_contract_module",
    "candidate_preparation_module",
    "aptarank_io_module",
    "record_parser_module",
)
REUSED_MODULE_ROLES = (
    ("evidence_contract_module", EVIDENCE_MODULE_RELATIVE, EVIDENCE_MODULE_SHA256),
    ("candidate_preparation_module", PREPARATION_MODULE_RELATIVE, PREPARATION_MODULE_SHA256),
    ("aptarank_io_module", IO_MODULE_RELATIVE, IO_MODULE_SHA256),
    ("record_parser_module", PARSER_MODULE_RELATIVE, PARSER_MODULE_SHA256),
)
TOP_LEVEL_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "stage",
    "deployment_verified",
    "scientific_result",
    "production_inputs_opened",
    "aptarank_execution",
    "scores_recomputed",
    "overlap_or_leakage_calculated",
    "live_export_behavior",
    "governing_plan",
    "evidence_contract",
    "candidate_preparation_contract",
    "reused_modules",
    "export_schema",
    "field_validation",
    "private_membership_validation",
    "join",
    "missing_row_policy",
    "rejection_records",
    "outputs",
    "inputs",
    "prohibited",
)
EXPORT_SCHEMA_KEYS = (
    "source_fact_id",
    "columns",
    "header_adaptation",
    "compatibility_source_fact_id",
    "compatibility_tokens",
    "shuffle_source_fact_id",
    "shuffle_tokens",
    "shuffle_absent_boolean_spelling",
    "rank_source_fact_id",
    "rank_definition",
    "rank_sort",
    "rank_is_statistical_minimum_rank",
    "score_recomputed",
    "token_profile_inferred_from_file",
    "arp1_target_free_profile_is_the_public_token_set",
)
FIELD_KEYS = (
    "aptamer_likeness",
    "aptamer_likeness_interval",
    "compatibility",
    "shuffle",
    "length",
    "sequence",
    "silent_normalization",
    "thresholds_applied",
    "biological_summary_calculated",
)
JOIN_KEYS = (
    "key",
    "export_column",
    "upload_column",
    "private_key_field",
    "row_position_is_join_key",
    "sequence_is_join_key",
    "shared_condition_memberships",
    "dispositions",
    "invent_rejection_reasons",
)
POLICY_KEYS = (
    "caller_supplied",
    "default",
    "accepted",
    "reason",
    "evidence_item_id",
    "missing_disposition",
    "missing_rejection_reason",
    "impute_missing_as_zero",
    "require_complete",
    "allow_partial",
)
REJECTION_CONTRACT_KEYS = (
    "required",
    "form",
    "keys",
    "reason_invented_when_absent",
    "blank_reason",
)
JOINED_OUTPUT_KEYS = (
    "filename",
    "restricted",
    "contains_sequences",
    "analysis_ready",
    "grain",
    "order",
)
MANIFEST_OUTPUT_KEYS = (
    "filename",
    "sequence_free",
    "contains_candidate_identifiers",
    "contains_source_identifiers",
    "contains_exported_scores",
    "own_sha256_embedded",
    "includes_overlap_metrics",
)
INPUT_KEYS = (
    "accepted_forms",
    "filesystem_paths",
    "production_uploads",
    "real_downloads",
)
PRIVATE_MEMBERSHIP_KEYS = (
    "validator",
    "record_reconstruction",
    "scientific_rules_duplicated",
    "noncanonical_form",
    "error_conversion",
    "source_identity_syntax",
    "per_condition_provenance",
    "index_constraints",
    "sha256_fields",
    "b1_training_seed",
    "d1_seed_block",
    "invalid_or_mixed_d1_seeds",
    "multiplicity",
    "source_occurrence_order",
)
D1_SEED_BLOCK = (
    {"training_seed": 43, "technical_block": "A"},
    {"training_seed": 44, "technical_block": "B"},
)
PREPARATION_ERROR_CODES = {
    "length_invalid": "length_mismatch",
    "length_ineligible": "length_ineligible",
    "multiplicity_mismatch": "multiplicity_mismatch",
    "duplicate_source_identity": "duplicate_source_identity",
    "source_identity_invalid": "source_identity_invalid",
    "provenance_invalid": "provenance_invalid",
    "d1_training_seed_invalid": "d1_training_seed_invalid",
    "ambiguous_d1_provenance": "ambiguous_d1_provenance",
    "source_occurrence_invalid": "private_key_invalid",
    "condition_invalid": "private_key_invalid",
    "input_invalid": "private_key_invalid",
    "sequence_invalid": "sequence_alphabet",
    "malformed_input": "malformed_private_key",
}
PLAN_KEYS = ("path", "version", "revision_date", "sha256")
EVIDENCE_PIN_KEYS = ("path", "package_id", "sha256")
PREPARATION_PIN_KEYS = ("path", "package_id", "schema_version", "sha256")
MODULE_PIN_KEYS = ("role", "path", "sha256")
FORBIDDEN_MANIFEST_TOKENS = ("overlap", "jaccard", "leakage", "nearest")
_MODULES = {}


class ExportValidationError(ValueError):
    """The synthetic export contract refused the supplied bytes."""

    def __init__(self, code, detail, errors=None, disposition=None, rejection_reason=None):
        self.code = code
        self.detail = detail
        self.errors = [{"code": code, "detail": detail}] if errors is None else list(errors)
        self.disposition = disposition
        self.rejection_reason = rejection_reason
        super().__init__(code + ": " + detail)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def contract_path():
    return os.path.join(repo_root(), CONTRACT_RELATIVE)


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


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
    return _load_module("generator_eval_parser.py", "generator_eval_parser_for_m9b3")


def _evidence():
    return _load_module("aptarank_evidence_contract.py", "aptarank_evidence_contract_for_m9b3")


def _preparation():
    return _load_module("aptarank_candidate_preparation.py", "aptarank_candidate_preparation_for_m9b3")


def _arp1():
    return _load_module("aptarank_io_preflight.py", "aptarank_io_preflight_for_m9b3")


def _require(condition, code, detail):
    if not condition:
        raise ExportValidationError(code, detail)


def _exact_keys(document, expected, code, detail):
    _require(type(document) is dict and set(document) == set(expected), code, detail)


def _read_pinned_file(relative):
    if type(relative) is not str or relative == "" or os.path.isabs(relative) or ".." in relative.split("/"):
        raise ExportValidationError("pin_invalid", "a pinned path is not a repository-relative file")
    path = os.path.join(repo_root(), relative)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise ExportValidationError("pin_unreadable", "a pinned file cannot be read") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ExportValidationError("pin_symlink", "a pinned file is not a regular file")
    with open(path, "rb") as handle:
        return handle.read()


def _recorded_pins(document):
    reused = {}
    for item in document["reused_modules"]:
        _exact_keys(item, MODULE_PIN_KEYS, "spec_invalid", "a reused module record drifted")
        _require(item["role"] not in reused, "spec_invalid", "a reused module role is repeated")
        reused[item["role"]] = item
    return {
        "governing_plan": document["governing_plan"],
        "evidence_contract": document["evidence_contract"],
        "candidate_preparation_contract": document["candidate_preparation_contract"],
        **reused,
    }


def validate_contract_document(document):
    """Refuse a contract that resolves live export behavior or recomputes scores."""
    _exact_keys(document, TOP_LEVEL_KEYS, "spec_invalid", "the export-validation contract keys changed")
    _require(document["package_id"] == PACKAGE_ID, "spec_invalid", "the package id is not M9B-3")
    _require(document["schema_version"] == SCHEMA_VERSION, "spec_invalid", "the schema version drifted")
    _require(document["status"] == STATUS, "spec_invalid", "the export-validation status drifted")
    _require(document["stage"] == STAGE, "spec_invalid", "the stage is not M9B-3")
    for key in (
        "deployment_verified",
        "scientific_result",
        "production_inputs_opened",
        "aptarank_execution",
        "scores_recomputed",
        "overlap_or_leakage_calculated",
    ):
        _require(document[key] is False, "spec_invalid", key + " must remain false")
    _require(document["live_export_behavior"] == "unresolved", "spec_invalid", "live export behavior must stay unresolved")
    plan = document["governing_plan"]
    _exact_keys(plan, PLAN_KEYS, "spec_invalid", "the governing plan record drifted")
    _require(plan["path"] == PLAN_RELATIVE, "spec_invalid", "the governing plan path drifted")
    _require(plan["version"] == "3.3", "spec_invalid", "the governing plan version drifted")
    _require(plan["revision_date"] == "12 October 2026", "spec_invalid", "the governing plan date drifted")
    _require(plan["sha256"] == PLAN_SHA256, "spec_invalid", "the governing plan hash drifted")
    evidence = document["evidence_contract"]
    _exact_keys(evidence, EVIDENCE_PIN_KEYS, "spec_invalid", "the evidence-contract pin drifted")
    _require(evidence["path"] == EVIDENCE_CONTRACT_RELATIVE, "spec_invalid", "the evidence-contract path drifted")
    _require(evidence["package_id"] == "M9B-1", "spec_invalid", "the evidence package is not M9B-1")
    _require(evidence["sha256"] == EVIDENCE_CONTRACT_SHA256, "spec_invalid", "the evidence-contract hash drifted")
    preparation = document["candidate_preparation_contract"]
    _exact_keys(preparation, PREPARATION_PIN_KEYS, "spec_invalid", "the preparation-contract pin drifted")
    _require(preparation["path"] == PREPARATION_CONTRACT_RELATIVE, "spec_invalid", "the preparation-contract path drifted")
    _require(preparation["package_id"] == "M9B-2", "spec_invalid", "the preparation package is not M9B-2")
    _require(
        preparation["schema_version"] == "m9b-aptarank-candidate-preparation-v1",
        "spec_invalid",
        "the preparation schema drifted",
    )
    _require(preparation["sha256"] == PREPARATION_CONTRACT_SHA256, "spec_invalid", "the preparation-contract hash drifted")
    reused = document["reused_modules"]
    _require(type(reused) is list and len(reused) == len(REUSED_MODULE_ROLES), "spec_invalid", "the reused module list drifted")
    for item, expected in zip(reused, REUSED_MODULE_ROLES):
        _exact_keys(item, MODULE_PIN_KEYS, "spec_invalid", "a reused module record drifted")
        _require(tuple(item[key] for key in MODULE_PIN_KEYS) == expected, "spec_invalid", "a reused module pin drifted")
    schema = document["export_schema"]
    _exact_keys(schema, EXPORT_SCHEMA_KEYS, "spec_invalid", "the export schema record drifted")
    _require(schema["source_fact_id"] == "shortlist_export_columns", "spec_invalid", "the column fact id drifted")
    _require(schema["columns"] == list(EXPORT_COLUMNS), "spec_invalid", "the shortlist columns drifted")
    _require(schema["header_adaptation"] is False, "spec_invalid", "header adaptation must stay off")
    _require(schema["compatibility_source_fact_id"] == "export_tokens", "spec_invalid", "the compatibility fact id drifted")
    _require(schema["compatibility_tokens"] == list(COMPATIBILITY_TOKENS), "spec_invalid", "the compatibility tokens drifted")
    _require(schema["shuffle_source_fact_id"] == "export_tokens", "spec_invalid", "the shuffle fact id drifted")
    _require(schema["shuffle_tokens"] == list(SHUFFLE_TOKENS), "spec_invalid", "the shuffle tokens drifted")
    _require(schema["shuffle_absent_boolean_spelling"] == "U+2014", "spec_invalid", "the em-dash spelling drifted")
    _require(schema["rank_source_fact_id"] == "rank_direction", "spec_invalid", "the rank fact id drifted")
    _require(
        schema["rank_definition"] == "consecutive_1_based_ordinal_of_exported_rows",
        "spec_invalid",
        "the rank definition drifted",
    )
    _require(
        schema["rank_sort"] == ["descending_exported_aptamer_likeness", "ascending_candidate_id"],
        "spec_invalid",
        "the rank sort drifted",
    )
    _require(schema["rank_is_statistical_minimum_rank"] is False, "spec_invalid", "the exported rank must stay an ordinal")
    _require(schema["score_recomputed"] is False, "spec_invalid", "score recomputation must stay off")
    _require(schema["token_profile_inferred_from_file"] is False, "spec_invalid", "a token profile must not be inferred")
    _require(
        schema["arp1_target_free_profile_is_the_public_token_set"] is False,
        "spec_invalid",
        "the public token set is wider than the target-free profile",
    )
    fields = document["field_validation"]
    _exact_keys(fields, FIELD_KEYS, "spec_invalid", "the field-validation record drifted")
    _require(
        fields["aptamer_likeness"] == "finite_decimal_closed_unit_interval_original_token_preserved",
        "spec_invalid",
        "the likeness rule drifted",
    )
    _require(fields["aptamer_likeness_interval"] == [0, 1], "spec_invalid", "the likeness interval drifted")
    _require(fields["compatibility"] == "exact_public_token", "spec_invalid", "the compatibility rule drifted")
    _require(fields["shuffle"] == "exact_public_token", "spec_invalid", "the shuffle rule drifted")
    _require(
        fields["length"] == "exported_len_equals_uploaded_and_exported_sequence_length",
        "spec_invalid",
        "the length rule drifted",
    )
    _require(
        fields["sequence"] == "character_for_character_match_for_the_same_opaque_id",
        "spec_invalid",
        "the sequence rule drifted",
    )
    for key in ("silent_normalization", "thresholds_applied", "biological_summary_calculated"):
        _require(fields[key] is False, "spec_invalid", key + " must remain false")
    private_membership = document["private_membership_validation"]
    _exact_keys(private_membership, PRIVATE_MEMBERSHIP_KEYS, "spec_invalid", "the private-membership validation record drifted")
    _require(
        private_membership["validator"] == "pinned_candidate_preparation_normalizer",
        "spec_invalid",
        "private memberships must use the pinned preparation normalizer",
    )
    _require(
        private_membership["record_reconstruction"] == "uploaded_sequence_with_private_membership_fields",
        "spec_invalid",
        "the private-membership reconstruction drifted",
    )
    _require(
        private_membership["scientific_rules_duplicated"] is False,
        "spec_invalid",
        "M9B-2 scientific rules must not be duplicated",
    )
    _require(private_membership["noncanonical_form"] == "fail_closed", "spec_invalid", "a noncanonical private key must fail closed")
    _require(
        private_membership["error_conversion"] == "candidate_preparation_error_to_export_validation_error",
        "spec_invalid",
        "preparation errors must become export-validation errors",
    )
    _require(private_membership["source_identity_syntax"] is True, "spec_invalid", "source-identity syntax must be checked")
    _require(private_membership["per_condition_provenance"] is True, "spec_invalid", "per-condition provenance must be checked")
    _require(
        private_membership["index_constraints"] == "nonnegative_or_positive_where_defined",
        "spec_invalid",
        "the index constraints drifted",
    )
    _require(private_membership["sha256_fields"] is True, "spec_invalid", "SHA-256 provenance fields must be checked")
    _require(private_membership["b1_training_seed"] is None, "spec_invalid", "the B1 training seed must stay null")
    _require(private_membership["d1_seed_block"] == [dict(item) for item in D1_SEED_BLOCK], "spec_invalid", "the D1 seed block allocation drifted")
    _require(
        private_membership["invalid_or_mixed_d1_seeds"] == "fail_closed",
        "spec_invalid",
        "invalid or mixed D1 seeds must fail closed",
    )
    _require(
        private_membership["multiplicity"] == "must_equal_complete_source_occurrences",
        "spec_invalid",
        "the multiplicity rule drifted",
    )
    _require(
        private_membership["source_occurrence_order"] == "canonical_m9b2_order_required",
        "spec_invalid",
        "canonical source-occurrence order must be required",
    )
    join = document["join"]
    _exact_keys(join, JOIN_KEYS, "spec_invalid", "the join record drifted")
    _require(join["key"] == "opaque_candidate_id", "spec_invalid", "the join key drifted")
    _require(join["export_column"] == "candidate", "spec_invalid", "the export id column drifted")
    _require(join["upload_column"] == "id", "spec_invalid", "the upload id column drifted")
    _require(join["private_key_field"] == "candidate_id", "spec_invalid", "the private-key id field drifted")
    _require(join["row_position_is_join_key"] is False, "spec_invalid", "row position must not be a join key")
    _require(join["sequence_is_join_key"] is False, "spec_invalid", "sequence must not be a join key")
    _require(
        join["shared_condition_memberships"] == "all_private_key_memberships_retained",
        "spec_invalid",
        "shared memberships must all be retained",
    )
    _require(join["dispositions"] == list(DISPOSITIONS), "spec_invalid", "the disposition list drifted")
    _require(join["invent_rejection_reasons"] is False, "spec_invalid", "rejection reasons must not be invented")
    policy = document["missing_row_policy"]
    _exact_keys(policy, POLICY_KEYS, "spec_invalid", "the missing-row policy record drifted")
    _require(policy["caller_supplied"] is True, "spec_invalid", "the missing-row policy must be caller-supplied")
    _require(policy["default"] is None, "spec_invalid", "the missing-row policy has no default")
    _require(policy["accepted"] == list(MISSING_ROW_POLICIES), "spec_invalid", "the missing-row policies drifted")
    _require("M9C" in policy["reason"], "spec_invalid", "the missing-row policy must stay deferred to M9C")
    _require(policy["evidence_item_id"] == "live_export_behavior", "spec_invalid", "the live-export evidence id drifted")
    _require(policy["missing_disposition"] == "missing", "spec_invalid", "a missing row must stay missing")
    _require(policy["missing_rejection_reason"] is None, "spec_invalid", "a missing row has no rejection reason")
    _require(policy["impute_missing_as_zero"] is False, "spec_invalid", "a missing score must not be imputed")
    _require(type(policy["require_complete"]) is str and policy["require_complete"], "spec_invalid", "require_complete drifted")
    _require(type(policy["allow_partial"]) is str and policy["allow_partial"], "spec_invalid", "allow_partial drifted")
    rejection = document["rejection_records"]
    _exact_keys(rejection, REJECTION_CONTRACT_KEYS, "spec_invalid", "the rejection-record contract drifted")
    _require(rejection["required"] is False, "spec_invalid", "rejection records stay optional")
    _require(
        rejection["form"] == "caller_supplied_utf8_jsonl_bytes_or_null",
        "spec_invalid",
        "the rejection-record form drifted",
    )
    _require(rejection["keys"] == list(REJECTION_KEYS), "spec_invalid", "the rejection-record keys drifted")
    _require(rejection["reason_invented_when_absent"] is False, "spec_invalid", "an absent reason must not be filled")
    _require(rejection["blank_reason"] == "fail_closed", "spec_invalid", "a blank rejection reason must fail closed")
    outputs = document["outputs"]
    _exact_keys(outputs, ("joined_candidates", "validation_manifest"), "spec_invalid", "the output record drifted")
    joined = outputs["joined_candidates"]
    manifest = outputs["validation_manifest"]
    _exact_keys(joined, JOINED_OUTPUT_KEYS, "spec_invalid", "the joined-output record drifted")
    _exact_keys(manifest, MANIFEST_OUTPUT_KEYS, "spec_invalid", "the manifest-output record drifted")
    _require(joined["filename"] == "joined_candidates.jsonl", "spec_invalid", "the joined filename drifted")
    _require(joined["restricted"] is True, "spec_invalid", "joined bytes stay restricted")
    _require(joined["contains_sequences"] is True, "spec_invalid", "joined bytes keep sequences")
    _require(joined["analysis_ready"] is True, "spec_invalid", "joined bytes stay analysis-ready")
    _require(joined["grain"] == "one_row_per_uploaded_candidate", "spec_invalid", "the joined grain drifted")
    _require(
        joined["order"] == ["exported_by_rank", "missing_by_candidate_id", "rejected_by_candidate_id"],
        "spec_invalid",
        "the joined order drifted",
    )
    _require(manifest["filename"] == "validation_manifest.json", "spec_invalid", "the manifest filename drifted")
    _require(manifest["sequence_free"] is True, "spec_invalid", "the manifest must stay sequence-free")
    _require(manifest["contains_candidate_identifiers"] is False, "spec_invalid", "the manifest must omit candidate ids")
    _require(manifest["contains_source_identifiers"] is False, "spec_invalid", "the manifest must omit source ids")
    _require(manifest["contains_exported_scores"] is False, "spec_invalid", "the manifest must omit exported scores")
    _require(manifest["own_sha256_embedded"] is False, "spec_invalid", "the manifest must not embed its own hash")
    _require(manifest["includes_overlap_metrics"] is False, "spec_invalid", "the manifest must omit overlap metrics")
    inputs = document["inputs"]
    _exact_keys(inputs, INPUT_KEYS, "spec_invalid", "the input record drifted")
    _require(inputs["accepted_forms"] == ["caller_supplied_bytes"], "spec_invalid", "the accepted input form drifted")
    for key in ("filesystem_paths", "production_uploads", "real_downloads"):
        _require(inputs[key] is False, "spec_invalid", key + " must remain false")
    prohibited = document["prohibited"]
    _require(type(prohibited) is list and prohibited, "spec_invalid", "the prohibited list is missing")
    prohibited_text = "\n".join(prohibited)
    for phrase in ("TRAIN", "VALIDATION", "REF", "EVAL", "results/", "Tier 1", "Tier 2", "missing-row policy", "rejection reason"):
        _require(phrase in prohibited_text, "spec_invalid", "a prohibited action is missing")
    return document


def verify_external_pins(document, blobs):
    """Compare pinned hashes with caller-supplied file bytes."""
    validate_contract_document(document)
    _require(type(blobs) is dict and set(blobs) == set(PIN_ROLES), "pin_invalid", "the pin byte set is incomplete")
    expected = {
        "export_validation_contract": CONTRACT_SHA256,
        "governing_plan": PLAN_SHA256,
        "evidence_contract": EVIDENCE_CONTRACT_SHA256,
        "candidate_preparation_contract": PREPARATION_CONTRACT_SHA256,
        "evidence_contract_module": EVIDENCE_MODULE_SHA256,
        "candidate_preparation_module": PREPARATION_MODULE_SHA256,
        "aptarank_io_module": IO_MODULE_SHA256,
        "record_parser_module": PARSER_MODULE_SHA256,
    }
    recorded = _recorded_pins(document)
    for role, digest in expected.items():
        payload = blobs[role]
        _require(type(payload) is bytes, "pin_invalid", "a pinned payload is not bytes")
        if sha256_bytes(payload) != digest:
            raise ExportValidationError("pin_mismatch", "the " + role + " pin does not match")
        if role == "export_validation_contract":
            continue
        if recorded[role]["sha256"] != digest:
            raise ExportValidationError("pin_mismatch", "the " + role + " pin does not match")
    return document


def assert_reused_definitions(evidence_document, preparation_document):
    """Require the live M9B-1 facts and the corrected M9B-2 private-key schema."""
    arp1 = _arp1()
    preparation = _preparation()
    parser = _parser()
    if tuple(arp1.SHORTLIST_COLUMNS) != EXPORT_COLUMNS or tuple(arp1.CANDIDATE_COLUMNS) != ("id", "sequence"):
        raise ExportValidationError("pin_mismatch", "the reused shortlist columns drifted")
    if arp1.classify_likeness("0") != "finite" or arp1.classify_likeness("nan") != "nonfinite":
        raise ExportValidationError("pin_mismatch", "the reused likeness classifier drifted")
    if parser.split_raw_record_bytes(b"") != []:
        raise ExportValidationError("pin_mismatch", "the reused record splitter drifted")
    if type(evidence_document) is not dict or type(evidence_document.get("facts")) is not list:
        raise ExportValidationError("pin_mismatch", "the evidence facts are not the pinned list")
    facts = {}
    for fact in evidence_document["facts"]:
        if type(fact) is not dict or type(fact.get("id")) is not str or type(fact.get("statement")) is not str:
            raise ExportValidationError("pin_mismatch", "an evidence fact is not the pinned shape")
        facts[fact["id"]] = fact["statement"]
    columns = facts.get("shortlist_export_columns", "")
    if COLUMN_PHRASE not in columns:
        raise ExportValidationError("pin_mismatch", "the public shortlist columns are not the pinned evidence fact")
    tokens = facts.get("export_tokens", "")
    for phrase in TOKEN_PHRASES:
        if phrase not in tokens:
            raise ExportValidationError("pin_mismatch", "a public export token is not the pinned evidence fact")
    rank = facts.get("rank_direction", "")
    for phrase in RANK_PHRASES:
        if phrase not in rank:
            raise ExportValidationError("pin_mismatch", "the exported rank rule is not the pinned evidence fact")
    unresolved = evidence_document.get("unresolved_deployment_items")
    items = unresolved.get("items") if type(unresolved) is dict else None
    live = None
    if type(items) is list:
        for item in items:
            if type(item) is dict and item.get("id") == "live_export_behavior":
                live = item
                break
    if type(live) is not dict or live.get("status") != "unresolved" or live.get("value") is not None:
        raise ExportValidationError("pin_mismatch", "live export behavior is not the unresolved M9B-1 item")
    if type(preparation_document) is not dict:
        raise ExportValidationError("pin_mismatch", "the preparation contract is not the pinned document")
    if preparation_document.get("package_id") != "M9B-2":
        raise ExportValidationError("pin_mismatch", "the preparation package is not M9B-2")
    if preparation_document.get("schema_version") != preparation.SCHEMA_VERSION:
        raise ExportValidationError("pin_mismatch", "the preparation schema is not the corrected contract")
    if preparation_document.get("status") != preparation.STATUS:
        raise ExportValidationError("pin_mismatch", "the preparation status is not the corrected contract")
    outputs = preparation_document.get("outputs")
    private_key = outputs.get("private_membership_key") if type(outputs) is dict else None
    upload = outputs.get("candidate_upload") if type(outputs) is dict else None
    if type(private_key) is not dict or private_key.get("keys") != list(preparation.PRIVATE_KEY_KEYS):
        raise ExportValidationError("pin_mismatch", "the private-key fields are not the corrected M9B-2 contract")
    if type(upload) is not dict or upload.get("columns") != ["id", "sequence"]:
        raise ExportValidationError("pin_mismatch", "the candidate-upload columns are not the corrected M9B-2 contract")
    if preparation.PRIVATE_KEY_KEYS != (
        "candidate_id",
        "condition",
        "comparison_role",
        "length",
        "multiplicity",
        "source_occurrences",
    ):
        raise ExportValidationError("pin_mismatch", "the private-key constant drifted")
    return evidence_document


def load_pinned_contract():
    """Load the export contract and fail closed on every recorded pin."""
    contract_bytes = _read_pinned_file(CONTRACT_RELATIVE)
    if sha256_bytes(contract_bytes) != CONTRACT_SHA256:
        raise ExportValidationError("pin_mismatch", "the export-validation contract pin does not match")
    try:
        document = json.loads(contract_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExportValidationError("spec_invalid", "the export-validation contract is not readable JSON") from exc
    blobs = {
        "export_validation_contract": contract_bytes,
        "governing_plan": _read_pinned_file(PLAN_RELATIVE),
        "evidence_contract": _read_pinned_file(EVIDENCE_CONTRACT_RELATIVE),
        "candidate_preparation_contract": _read_pinned_file(PREPARATION_CONTRACT_RELATIVE),
        "evidence_contract_module": _read_pinned_file(EVIDENCE_MODULE_RELATIVE),
        "candidate_preparation_module": _read_pinned_file(PREPARATION_MODULE_RELATIVE),
        "aptarank_io_module": _read_pinned_file(IO_MODULE_RELATIVE),
        "record_parser_module": _read_pinned_file(PARSER_MODULE_RELATIVE),
    }
    verify_external_pins(document, blobs)
    evidence = _evidence()
    preparation = _preparation()
    try:
        evidence_document, evidence_payload = evidence.load_contract()
    except evidence.EvidenceContractError as exc:
        raise ExportValidationError(exc.code, exc.detail) from exc
    if sha256_bytes(evidence_payload) != EVIDENCE_CONTRACT_SHA256:
        raise ExportValidationError("pin_mismatch", "the evidence-contract pin does not match")
    try:
        preparation_document = preparation.load_pinned_contract()
    except preparation.CandidatePreparationError as exc:
        raise ExportValidationError(exc.code, exc.detail) from exc
    assert_reused_definitions(evidence_document, preparation_document)
    return document


def _firewall(controls):
    parser = _parser()
    try:
        parser.enforce_firewall(controls)
    except parser.ParserContractError as exc:
        raise ExportValidationError(exc.code, exc.detail) from exc


def _path_object(value):
    if isinstance(value, (str, bytes, bytearray)):
        return False
    return callable(getattr(value, "__fspath__", None))


def _require_bytes(value, label):
    parser = _parser()
    if _path_object(value):
        raise ExportValidationError("filesystem_path_refused", "a filesystem path argument is refused")
    if type(value) is str:
        try:
            parser.reject_control_string(value)
        except parser.ParserContractError as exc:
            raise ExportValidationError(exc.code, exc.detail) from exc
        raise ExportValidationError("input_type_invalid", label + " must be bytes")
    if type(value) is not bytes:
        raise ExportValidationError("input_type_invalid", label + " must be bytes")
    return value


def _require_policy(value):
    if value is None:
        raise ExportValidationError(
            "missing_row_policy_missing",
            "a missing-row policy is required because deployed export behavior is unresolved",
        )
    if type(value) is not str or value not in MISSING_ROW_POLICIES:
        raise ExportValidationError(
            "missing_row_policy_invalid",
            "the missing-row policy must be require_complete or allow_partial",
        )
    return value


def _raise_first(errors):
    if errors.items:
        first = errors.items[0]
        raise ExportValidationError(first["code"], first["detail"], errors.items)


def _parse_csv(payload, columns, role):
    arp1 = _arp1()
    errors = arp1.ErrorList()
    rows = arp1.parse_csv_rows(payload, columns, errors, role)
    _raise_first(errors)
    if rows is None:
        raise ExportValidationError("schema_mismatch", role + " header does not match the public shortlist schema")
    return rows


def _check_identifier(value):
    return type(value) is str and _arp1().ID_TEXT.fullmatch(value) is not None


def _upload_table(payload):
    arp1 = _arp1()
    rows = _parse_csv(payload, arp1.CANDIDATE_COLUMNS, "candidate upload")
    if not rows:
        raise ExportValidationError("upload_empty", "the candidate upload has no rows")
    errors = arp1.ErrorList()
    arp1._check_candidate_rows(rows, errors)
    if errors.items and errors.items[0]["code"] == "empty_id":
        raise ExportValidationError("malformed_candidate_id", errors.items[0]["detail"], errors.items)
    _raise_first(errors)
    sequences = {}
    for row in rows:
        candidate_id = row["id"]
        if not _check_identifier(candidate_id):
            raise ExportValidationError("malformed_candidate_id", "a candidate upload id is malformed")
        if candidate_id in sequences:
            raise ExportValidationError("duplicate_candidate_id", "candidate id " + candidate_id + " is duplicated in the upload")
        if arp1.SEQUENCE_TEXT.fullmatch(row["sequence"]) is None:
            raise ExportValidationError("sequence_alphabet", "candidate " + candidate_id + " sequence is not uppercase A, C, G and U")
        sequences[candidate_id] = row["sequence"]
    return rows, sequences


def _convert_preparation_error(exc):
    """Turn one pinned M9B-2 failure into an M9B-3 validation error.

    An unmapped preparation code fails closed. The scientific detail is kept
    and is not replaced with a repaired membership.
    """
    code = PREPARATION_ERROR_CODES.get(exc.code, "private_key_invalid")
    raise ExportValidationError(code, exc.detail) from exc


def _copy_membership(row, sequence):
    """Validate one private membership through the pinned M9B-2 normalizer.

    The uploaded sequence rebuilds the M9B-2 input record. The private key
    itself still has no sequence. A membership that the normalizer would
    rewrite into canonical form is refused.
    """
    preparation = _preparation()
    _exact_keys(row, preparation.PRIVATE_KEY_KEYS, "private_key_invalid", "a private-key row is not the recorded object")
    candidate_id = row["candidate_id"]
    if not _check_identifier(candidate_id):
        raise ExportValidationError("malformed_candidate_id", "a private-key candidate id is malformed")
    record = {
        "condition": row["condition"],
        "sequence": sequence,
        "length": row["length"],
        "multiplicity": row["multiplicity"],
        "source_occurrences": row["source_occurrences"],
    }
    try:
        normalized = preparation._normalize_one(record)
    except preparation.CandidatePreparationError as exc:
        _convert_preparation_error(exc)
    if (
        row["condition"] != normalized["condition"]
        or row["comparison_role"] != normalized["comparison_role"]
        or row["length"] != normalized["length"]
        or row["multiplicity"] != normalized["multiplicity"]
        or row["source_occurrences"] != normalized["source_occurrences"]
    ):
        raise ExportValidationError("private_key_invalid", "a private-key membership is not in canonical M9B-2 form")
    return {
        "condition": normalized["condition"],
        "comparison_role": normalized["comparison_role"],
        "length": normalized["length"],
        "multiplicity": normalized["multiplicity"],
        "source_occurrences": normalized["source_occurrences"],
    }


def _private_memberships(payload, sequences):
    parser = _parser()
    try:
        lines = parser.split_raw_record_bytes(payload)
    except parser.ParserContractError as exc:
        raise ExportValidationError(exc.code, exc.detail) from exc
    if not lines:
        raise ExportValidationError("private_key_invalid", "the private key has no memberships")
    grouped = {candidate_id: [] for candidate_id in sequences}
    seen = set()
    identities = set()
    for index, line in enumerate(lines, start=1):
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExportValidationError("malformed_private_key", "private-key JSONL is not UTF-8") from exc
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExportValidationError("malformed_private_key", "private-key JSONL row %d is not JSON" % index) from exc
        if type(value) is not dict:
            raise ExportValidationError("private_key_invalid", "private-key JSONL row %d is not an object" % index)
        candidate_id = value.get("candidate_id")
        if not _check_identifier(candidate_id):
            raise ExportValidationError("malformed_candidate_id", "a private-key candidate id is malformed")
        if candidate_id not in sequences:
            raise ExportValidationError("unknown_membership_id", "private-key candidate " + candidate_id + " is absent from the upload")
        condition = value.get("condition")
        marker = (candidate_id, condition)
        if marker in seen:
            raise ExportValidationError("duplicate_membership", "candidate " + candidate_id + " repeats condition membership")
        seen.add(marker)
        membership = _copy_membership(value, sequences[candidate_id])
        for occurrence in membership["source_occurrences"]:
            identity = occurrence["source_identity"]
            if identity in identities:
                raise ExportValidationError("duplicate_source_identity", "a source identity is duplicated")
            identities.add(identity)
        grouped[candidate_id].append(membership)
    preparation = _preparation()
    order = {condition: index for index, condition in enumerate(preparation.CONDITIONS)}
    for candidate_id, memberships in grouped.items():
        if not memberships:
            raise ExportValidationError("missing_membership", "candidate " + candidate_id + " has no private membership")
        memberships.sort(key=lambda item: order[item["condition"]])
    return grouped, identities


def _rejection_table(payload):
    if payload is None:
        return {}
    parser = _parser()
    try:
        lines = parser.split_raw_record_bytes(payload)
    except parser.ParserContractError as exc:
        raise ExportValidationError(exc.code, exc.detail) from exc
    reasons = {}
    for index, line in enumerate(lines, start=1):
        if line == b"":
            raise ExportValidationError("malformed_rejection_record", "rejection JSONL row %d is empty" % index)
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExportValidationError("malformed_rejection_record", "rejection JSONL is not UTF-8") from exc
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExportValidationError("malformed_rejection_record", "rejection JSONL row %d is not JSON" % index) from exc
        if type(value) is not dict or set(value) != set(REJECTION_KEYS):
            raise ExportValidationError("malformed_rejection_record", "rejection record %d is not the recorded object" % index)
        candidate_id = value["candidate_id"]
        if not _check_identifier(candidate_id):
            raise ExportValidationError("malformed_rejected_id", "a rejection candidate id is malformed")
        reason = value["reason"]
        if type(reason) is not str or reason.strip() == "":
            raise ExportValidationError(
                "missing_rejection_reason",
                "candidate " + candidate_id + " rejection record has no supplied reason",
                disposition="rejected",
                rejection_reason=None,
            )
        if candidate_id in reasons:
            raise ExportValidationError("duplicate_rejected_id", "rejected candidate " + candidate_id + " is duplicated")
        reasons[candidate_id] = reason
    return reasons


def _likeness(token, candidate_id):
    kind = _arp1().classify_likeness(token)
    if kind == "malformed":
        raise ExportValidationError("malformed_aptamer_likeness", "candidate " + candidate_id + " aptamer-likeness is malformed")
    if kind == "nonfinite":
        raise ExportValidationError("nonfinite_aptamer_likeness", "candidate " + candidate_id + " aptamer-likeness is not finite")
    try:
        score = Decimal(token)
    except InvalidOperation as exc:
        raise ExportValidationError("malformed_aptamer_likeness", "candidate " + candidate_id + " aptamer-likeness is malformed") from exc
    if not score.is_finite() or score < 0 or score > 1:
        raise ExportValidationError(
            "aptamer_likeness_out_of_range",
            "candidate " + candidate_id + " aptamer-likeness is outside the closed interval [0, 1]",
        )
    return score


def _check_export_row(row):
    arp1 = _arp1()
    candidate_id = row["candidate"]
    label = candidate_id if _check_identifier(candidate_id) else "row"
    if not _check_identifier(candidate_id):
        raise ExportValidationError("malformed_candidate_id", "an exported candidate id is malformed")
    if arp1.SEQUENCE_TEXT.fullmatch(row["sequence"]) is None:
        raise ExportValidationError("sequence_alphabet", "candidate " + candidate_id + " exported sequence is not uppercase A, C, G and U")
    score = _likeness(row["aptamer-likeness"], candidate_id)
    if row["compatibility"] not in COMPATIBILITY_TOKENS:
        raise ExportValidationError("invalid_compatibility", "candidate " + candidate_id + " compatibility token is not a public export token")
    if row["shuffle"] not in SHUFFLE_TOKENS:
        raise ExportValidationError("invalid_shuffle", "candidate " + candidate_id + " shuffle token is not a public export token")
    if arp1.POSITIVE_INT_TEXT.fullmatch(row["rank"]) is None:
        raise ExportValidationError("malformed_rank", "candidate " + candidate_id + " rank is not a positive integer")
    if arp1.NONNEGATIVE_INT_TEXT.fullmatch(row["len"]) is None:
        raise ExportValidationError("malformed_length", "candidate " + label + " len is not a nonnegative integer")
    if int(row["len"]) != len(row["sequence"]):
        raise ExportValidationError("length_mismatch", "candidate " + candidate_id + " exported len does not match the exported sequence length")
    return score


def _export_table(payload):
    rows = _parse_csv(payload, EXPORT_COLUMNS, "shortlist export")
    scores = {}
    seen = []
    for row in rows:
        candidate_id = row["candidate"]
        score = _check_export_row(row)
        if candidate_id in scores:
            raise ExportValidationError("duplicate_exported_id", "exported candidate id " + candidate_id + " is duplicated")
        scores[candidate_id] = score
        seen.append(row)
    return seen, scores


def _rank_order(rows, scores):
    seen = set()
    for row in rows:
        rank = row["rank"]
        if rank in seen:
            raise ExportValidationError("duplicate_rank", "exported rank " + rank + " is duplicated")
        seen.add(rank)
    ordered = sorted(rows, key=lambda row: (-scores[row["candidate"]], row["candidate"].encode("utf-8")))
    for position, row in enumerate(ordered, start=1):
        if int(row["rank"]) != position:
            raise ExportValidationError(
                "rank_order",
                "candidate " + row["candidate"] + " rank is not the exported ordinal of descending aptamer-likeness and ascending candidate id",
            )


def _sequence_identity(upload_rows, export_rows, sequences):
    flags = _arp1().sequence_matches_by_id(upload_rows, export_rows)
    if len(flags) != len(export_rows):
        raise ExportValidationError("pin_mismatch", "the reused id join did not cover the export")
    owners = {}
    for candidate_id, sequence in sequences.items():
        owners.setdefault(sequence, []).append(candidate_id)
    paired = sorted(zip(export_rows, flags), key=lambda item: item[0]["candidate"].encode("utf-8"))
    for row, matched in paired:
        if matched:
            continue
        candidate_id = row["candidate"]
        others = sorted(
            (other for other in owners.get(row["sequence"], []) if other != candidate_id),
            key=lambda item: item.encode("utf-8"),
        )
        if others:
            raise ExportValidationError(
                "sequence_substituted",
                "candidate " + candidate_id + " exported sequence matches opaque id " + others[0],
            )
        raise ExportValidationError(
            "sequence_mismatch",
            "candidate " + candidate_id + " exported sequence does not match the uploaded sequence for that id",
        )


def _condition_counts(grouped):
    preparation = _preparation()
    counts = {condition: 0 for condition in preparation.CONDITIONS}
    for memberships in grouped.values():
        for membership in memberships:
            counts[membership["condition"]] += 1
    return [
        {"condition": condition, "membership_count": counts[condition]}
        for condition in preparation.CONDITIONS
    ]


def _joined_row(candidate_id, disposition, sequence, memberships, export_row, reason):
    exported = export_row is not None
    return {
        "candidate_id": candidate_id,
        "disposition": disposition,
        "sequence": sequence,
        "length": len(sequence),
        "rank": int(export_row["rank"]) if exported else None,
        "aptamer-likeness": export_row["aptamer-likeness"] if exported else None,
        "compatibility": export_row["compatibility"] if exported else None,
        "shuffle": export_row["shuffle"] if exported else None,
        "rejection_reason": reason,
        "memberships": memberships,
    }


def _joined_bytes(sequences, grouped, export_rows, rejections):
    preparation = _preparation()
    exports = {row["candidate"]: row for row in export_rows}
    exported_ids = sorted(exports, key=lambda candidate_id: (int(exports[candidate_id]["rank"]), candidate_id.encode("utf-8")))
    missing_ids = sorted(
        (candidate_id for candidate_id in sequences if candidate_id not in exports and candidate_id not in rejections),
        key=lambda candidate_id: candidate_id.encode("utf-8"),
    )
    rejected_ids = sorted(
        (candidate_id for candidate_id in sequences if candidate_id in rejections),
        key=lambda candidate_id: candidate_id.encode("utf-8"),
    )
    rows = []
    for candidate_id in exported_ids:
        rows.append(_joined_row(candidate_id, "exported", sequences[candidate_id], grouped[candidate_id], exports[candidate_id], None))
    for candidate_id in missing_ids:
        rows.append(_joined_row(candidate_id, "missing", sequences[candidate_id], grouped[candidate_id], None, None))
    for candidate_id in rejected_ids:
        rows.append(_joined_row(candidate_id, "rejected", sequences[candidate_id], grouped[candidate_id], None, rejections[candidate_id]))
    for row in rows:
        _exact_keys(row, JOINED_KEYS, "joined_output_invalid", "a joined row drifted")
        if row["disposition"] not in DISPOSITIONS:
            raise ExportValidationError("joined_output_invalid", "a joined disposition drifted")
        if row["disposition"] != "rejected" and row["rejection_reason"] is not None:
            raise ExportValidationError("joined_output_invalid", "a rejection reason was attached without a caller-supplied rejection")
        if row["disposition"] == "missing" and (row["rank"] is not None or row["aptamer-likeness"] is not None):
            raise ExportValidationError("joined_output_invalid", "a missing row was given an exported score")
        for membership in row["memberships"]:
            _exact_keys(membership, MEMBERSHIP_KEYS, "joined_output_invalid", "a joined membership drifted")
    lines = [preparation.canonical_json_bytes(row) for row in rows]
    return b"\n".join(lines) + b"\n", exported_ids, missing_ids, rejected_ids


def _own_module_bytes():
    path = os.path.abspath(__file__)
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ExportValidationError("pin_symlink", "the export-validation module is not a regular file")
    with open(path, "rb") as handle:
        return handle.read()


def _manifest_document(policy, grouped, export_rows, missing_ids, rejected_ids, upload, private_key, shortlist, rejection, joined):
    pins = [
        {"role": "governing_plan", "path": PLAN_RELATIVE, "sha256": PLAN_SHA256},
        {"role": "evidence_contract", "path": EVIDENCE_CONTRACT_RELATIVE, "sha256": EVIDENCE_CONTRACT_SHA256},
        {
            "role": "candidate_preparation_contract",
            "path": PREPARATION_CONTRACT_RELATIVE,
            "sha256": PREPARATION_CONTRACT_SHA256,
        },
        {"role": "evidence_contract_module", "path": EVIDENCE_MODULE_RELATIVE, "sha256": EVIDENCE_MODULE_SHA256},
        {"role": "candidate_preparation_module", "path": PREPARATION_MODULE_RELATIVE, "sha256": PREPARATION_MODULE_SHA256},
        {"role": "aptarank_io_module", "path": IO_MODULE_RELATIVE, "sha256": IO_MODULE_SHA256},
        {"role": "record_parser_module", "path": PARSER_MODULE_RELATIVE, "sha256": PARSER_MODULE_SHA256},
        {"role": "export_validation_contract", "path": CONTRACT_RELATIVE, "sha256": CONTRACT_SHA256},
        {"role": "export_validation_module", "path": MODULE_RELATIVE, "sha256": sha256_bytes(_own_module_bytes())},
    ]
    supplied = rejection is not None
    return {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "stage": STAGE,
        "synthetic": True,
        "production_inputs_opened": False,
        "aptarank_executed": False,
        "scientific_result": False,
        "deployment_verified": False,
        "live_export_behavior": "unresolved",
        "scores_recomputed": False,
        "biological_summaries_calculated": False,
        "rejection_reasons_invented": False,
        "impute_missing_as_zero": False,
        "join_key": "opaque_candidate_id",
        "join_uses_row_position": False,
        "missing_row_policy": policy,
        "pins": pins,
        "upload_row_count": len(grouped),
        "private_membership_count": sum(len(memberships) for memberships in grouped.values()),
        "exported_row_count": len(export_rows),
        "missing_row_count": len(missing_ids),
        "rejected_row_count": len(rejected_ids),
        "private_membership_count_by_condition": _condition_counts(grouped),
        "candidate_upload_sha256": sha256_bytes(upload),
        "private_membership_key_sha256": sha256_bytes(private_key),
        "shortlist_export_sha256": sha256_bytes(shortlist),
        "rejection_records_supplied": supplied,
        "rejection_records_sha256": sha256_bytes(rejection) if supplied else None,
        "joined_candidates_sha256": sha256_bytes(joined),
        "candidate_upload_byte_count": len(upload),
        "private_membership_key_byte_count": len(private_key),
        "shortlist_export_byte_count": len(shortlist),
        "rejection_records_byte_count": len(rejection) if supplied else None,
        "joined_candidates_byte_count": len(joined),
    }


def _walk_strings(value):
    if type(value) is str:
        yield value
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is str:
                yield key
            yield from _walk_strings(item)
    elif type(value) is list:
        for item in value:
            yield from _walk_strings(item)


def _assert_manifest_closed(document, payload, sequences, candidate_ids, sources, scores, reasons):
    if b"cand_" in payload:
        raise ExportValidationError("manifest_firewall", "the validation manifest contains a candidate id")
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ExportValidationError("manifest_firewall", "the validation manifest is not sequence-free ASCII") from exc
    for token in FORBIDDEN_MANIFEST_TOKENS:
        if token in text:
            raise ExportValidationError("manifest_firewall", "the validation manifest contains a forbidden metric token")
    observed = set(_walk_strings(document))
    identifiers = set(sequences) | set(candidate_ids) | set(sources)
    if observed & identifiers or observed & set(scores) or observed & set(reasons):
        raise ExportValidationError("manifest_firewall", "the validation manifest contains a restricted value")
    for value in identifiers:
        if type(value) is str and value.encode("utf-8") in payload:
            raise ExportValidationError("manifest_firewall", "the validation manifest contains a restricted value")


def _account(sequences, export_rows, rejections, policy):
    exported = {row["candidate"] for row in export_rows}
    for candidate_id in sorted(exported - set(sequences), key=lambda item: item.encode("utf-8")):
        raise ExportValidationError("unknown_exported_id", "exported candidate " + candidate_id + " is absent from the upload")
    for candidate_id in sorted(set(rejections) - set(sequences), key=lambda item: item.encode("utf-8")):
        raise ExportValidationError("unknown_rejected_id", "rejected candidate " + candidate_id + " is absent from the upload")
    both = sorted(exported & set(rejections), key=lambda item: item.encode("utf-8"))
    if both:
        raise ExportValidationError(
            "candidate_accounted_twice",
            "candidate " + both[0] + " is both exported and rejected",
        )
    missing = sorted(
        (candidate_id for candidate_id in sequences if candidate_id not in exported and candidate_id not in rejections),
        key=lambda item: item.encode("utf-8"),
    )
    if missing and policy == "require_complete":
        raise ExportValidationError(
            "missing_candidate_id",
            "candidate " + missing[0] + " is absent from the export and no rejection record was supplied",
            disposition="missing",
            rejection_reason=None,
        )
    return missing


def validate_export(
    *,
    candidate_upload,
    private_membership_key,
    shortlist_export,
    missing_row_policy,
    rejection_records=None,
    **controls,
):
    """Join caller-supplied shortlist bytes to the upload by opaque candidate id.

    ``missing_row_policy`` is ``require_complete`` or ``allow_partial``. There
    is no default. ``rejection_records`` is optional JSONL bytes. A reason is
    copied only from those bytes. This function returns bytes and does not
    write them.
    """
    _firewall(controls)
    policy = _require_policy(missing_row_policy)
    upload = _require_bytes(candidate_upload, "candidate upload")
    private_key = _require_bytes(private_membership_key, "private membership key")
    shortlist = _require_bytes(shortlist_export, "shortlist export")
    rejection = None if rejection_records is None else _require_bytes(rejection_records, "rejection records")
    load_pinned_contract()
    upload_rows, sequences = _upload_table(upload)
    grouped, sources = _private_memberships(private_key, sequences)
    rejections = _rejection_table(rejection)
    export_rows, scores = _export_table(shortlist)
    _account(sequences, export_rows, rejections, policy)
    _sequence_identity(upload_rows, export_rows, sequences)
    _rank_order(export_rows, scores)
    joined, _exported_ids, missing_ids, rejected_ids = _joined_bytes(sequences, grouped, export_rows, rejections)
    manifest = _manifest_document(policy, grouped, export_rows, missing_ids, rejected_ids, upload, private_key, shortlist, rejection, joined)
    _exact_keys(manifest, MANIFEST_KEYS, "manifest_invalid", "the validation manifest drifted")
    preparation = _preparation()
    manifest_bytes = preparation.canonical_json_bytes(manifest) + b"\n"
    likeness = [row["aptamer-likeness"] for row in export_rows]
    _assert_manifest_closed(manifest, manifest_bytes, sequences.values(), sequences, sources, likeness, rejections.values())
    return {
        "joined_candidates": joined,
        "validation_manifest": manifest_bytes,
        "joined_candidates_sha256": sha256_bytes(joined),
        "validation_manifest_sha256": sha256_bytes(manifest_bytes),
    }


def main(argv=None):
    """Check pins and print the status. There is no production runner."""
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        raise ExportValidationError("production_runner_refused", "M9B-3 has no production runner")
    load_pinned_contract()
    sys.stdout.write(STATUS + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExportValidationError as exc:
        sys.stderr.write(exc.code + ": " + exc.detail + "\n")
        raise SystemExit(1)

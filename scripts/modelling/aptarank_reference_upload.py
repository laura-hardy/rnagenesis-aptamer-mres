#!/usr/bin/env python3
"""M9C-1 reference-upload preparation.

One upload row is retained for each distinct canonical REF sequence_core.
The AptaRank upload is a one-column CSV named sequence. The private ledger
is a project audit artifact and is not an AptaRank input. The no-argument
command checks pins only. It does not locate REF, EVAL, or a production
candidate source, and it does not calibrate AptaRank. The sealed publication
entry point stays idle unless its invocation flag is passed.
"""

from __future__ import annotations

import csv
import ctypes
import errno
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile

PACKAGE_ID = "M9C-1"
SCHEMA_VERSION = "m9c-reference-upload-v2"
STATUS = "POLICY_FROZEN_ONE_COLUMN_REFERENCE_UPLOAD_PUBLICATION_NOT_RETRIED"
STAGE = "M9C-1"
CONTRACT_RELATIVE = "config/modelling/aptarank_reference_upload_contract.json"
CONTRACT_SHA256 = "980e7d1b9ce8a8c4c86a88dc99df280f05485b7c4fb2fdfd600fdea7a0665f9e"
PRODUCTION_DESTINATION = "/home/laura/rnagenesis-mres-worktrees/generator-eval-prep/results/fine_tuning/m9_generator_evaluation/m9c_reference_preparation"
PRODUCTION_PUBLICATION_METHOD = "atomic_rename_of_verified_temporary_sibling"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
IO_SPEC_RELATIVE = "config/modelling/aptarank_io_spec.json"
IO_SPEC_SHA256 = "46ba6c8be873dad4c086e9f6b889b51702ba31212fa502d00f26e267a22da732"
IO_MODULE_RELATIVE = "scripts/modelling/aptarank_io_preflight.py"
IO_MODULE_SHA256 = "eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01"
REF_SHA256 = "531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23"
REF_BYTE_SIZE = 211993
EXTERNAL_REF_RELATIVE = "data/processed/ref.csv"
EXTERNAL_REF_LOCATOR = "opened_and_verified_in_attempt_1_corrected_retry_not_invoked"
MANIFEST_STATUS = "REFERENCE_UPLOAD_PREPARED_APTARANK_NOT_RUN"
PUBLICATION_ATTEMPT = 2
SEALED_REVIEW_AUTHORIZED = True
SEALED_ENTRY_POINT_INVOKED = False
OUTPUT_MEMBERS = (
    "reference_upload.csv",
    "duplicate_provenance.jsonl",
    "preparation_manifest.json",
)
SOURCE_COLUMN_COUNT = 85
SOURCE_IDENTITY_ROWS = 131
DISTINCT_SEQUENCE_CORES = 113
DUPLICATE_CORE_COLLAPSES = 18
EXPECTED_UI_ACCEPTED_COUNT = 113
EXPECTED_UI_DROPPED_COUNT = 0
STRUCTURE_FILE_SHA256 = "2e185a205c9be0bf76484e8ffb96ae225880723ed68eaaf25dffbbccaf01ff51"
SELECTION_RECORD_SHA256 = "08f0c96af349ce4909d40c3004804317661777f72828cd807823341e0e4f0d04"
TARGET_UPLOAD_SHA256 = "46471bb0643125ce86300ec050d6f0d3a09faa1d06dc325141c67cd1acdd5922"
UPLOAD_COLUMNS = ("sequence",)
REJECTED_UPLOAD_COLUMNS = ("id", "target_name", "target_pdb_id", "source_reference")
HISTORICAL_FIVE_COLUMN_REFERENCE_UPLOAD = (
    "id",
    "sequence",
    "target_name",
    "target_pdb_id",
    "source_reference",
)
FIELD_MAP = {"sequence": "sequence_core"}
LEDGER_KEYS = ("upload_row_number", "retained_id", "source_identities", "collapsed_source_identities")
INTERFACE_KEYS = (
    "authority",
    "columns",
    "rejected_columns",
    "target_configuration",
    "provenance_fields_in_upload",
    "header_exact",
    "sequence_pattern",
    "unique_sequences",
    "normalization",
    "sequence_rewriting",
    "private_ledger_is_aptarank_input",
    "supersedes_five_column_reference_upload",
    "supersession_scope",
    "historical_m9b_artifacts",
    "historical_m9b_results_rewritten",
    "candidate_and_export_behavior_changed",
)
ATTEMPT_KEYS = (
    "attempt",
    "parent_commit",
    "obsolete_contract_sha256",
    "ref_opened",
    "ref_verified",
    "preparation_stopped",
    "stop_reason",
    "observed_error_code",
    "observed_error_field",
    "output_published",
    "aptarank_run",
    "retried",
)
OBSOLETE_CONTRACT_SHA256 = "eb082923fbd79ccc05a9833e0f18e40094e8384bd2104392eee6cd46bc55f591"
FAILED_ATTEMPT_COMMIT = "3d5a4beafc723ab154a2ff7d3a6d6835841b3b48"
MANIFEST_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "publication_attempt",
    "source_sha256",
    "source_row_count",
    "distinct_sequence_cores",
    "duplicate_core_collapses",
    "prepared_upload_row_count",
    "reference_upload_sha256",
    "duplicate_provenance_sha256",
    "local_calibration",
    "production_ref_identity_verified",
    "aptarank_ui_executed",
    "observed_ui_accepted_count",
    "observed_ui_dropped_count",
)
TOP_LEVEL_KEYS = (
    "package_id",
    "schema_version",
    "status",
    "stage",
    "scientific_result",
    "production_inputs_opened",
    "ref_opened",
    "eval_opened",
    "production_candidates_opened",
    "local_calibration",
    "local_calibration_substitute",
    "aptarank_execution",
    "deployment_verified",
    "sealed_review_authorized",
    "governing_plan",
    "reused_modules",
    "calibration",
    "source_schema",
    "retention",
    "reference_upload_interface",
    "expected_live_ui_result",
    "external_ref",
    "frozen_target_mapping",
    "outputs",
    "first_failed_publication_attempt",
    "inputs",
    "prohibited",
)
_MODULES = {}


class ReferenceUploadError(ValueError):
    """The reference-upload policy refused the request."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=False).encode("utf-8")


def _load_module(filename, module_name):
    if module_name in _MODULES:
        return _MODULES[module_name]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULES[module_name] = module
    return module


def _arp1():
    return _load_module("aptarank_io_preflight.py", "aptarank_io_preflight_for_m9c")


def _require(condition, code, detail):
    if not condition:
        raise ReferenceUploadError(code, detail)


def _exact_keys(document, expected, code, detail):
    if type(document) is not dict or set(document) != set(expected):
        raise ReferenceUploadError(code, detail)


def _read_pinned_file(relative):
    if type(relative) is not str or relative == "" or os.path.isabs(relative) or ".." in relative.split("/"):
        raise ReferenceUploadError("pin_invalid", "a pinned path is not a repository-relative file")
    path = os.path.join(repo_root(), relative)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise ReferenceUploadError("pin_unreadable", "a pinned file cannot be read") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ReferenceUploadError("pin_symlink", "a pinned file is not a regular file")
    with open(path, "rb") as handle:
        return handle.read()


def _require_bytes(payload):
    if type(payload) is not bytes:
        raise ReferenceUploadError("filesystem_path_refused", "bytes must be supplied in memory")


def validate_contract_document(document, blobs):
    """Fail closed unless the contract still states this reference-upload policy."""
    _exact_keys(document, TOP_LEVEL_KEYS, "spec_invalid", "the reference-upload contract keys changed")
    _require(document["package_id"] == PACKAGE_ID, "spec_invalid", "the package id is not M9C-1")
    _require(document["schema_version"] == SCHEMA_VERSION, "spec_invalid", "the schema version changed")
    _require(document["status"] == STATUS, "spec_invalid", "the status changed")
    _require(document["stage"] == STAGE, "spec_invalid", "the stage changed")
    for key in (
        "scientific_result",
        "eval_opened",
        "production_candidates_opened",
        "local_calibration",
        "local_calibration_substitute",
        "aptarank_execution",
        "deployment_verified",
    ):
        _require(document[key] is False, "spec_invalid", "a closed policy flag is no longer false")
    _require(document["production_inputs_opened"] is True, "spec_invalid", "attempt 1 opened the production REF input")
    _require(document["ref_opened"] is True, "spec_invalid", "attempt 1 opened and verified REF")
    _require(document["sealed_review_authorized"] is True, "spec_invalid", "sealed review is not authorized")
    _require(SEALED_REVIEW_AUTHORIZED is True, "review_required", "sealed review is not authorized")
    _require(SEALED_ENTRY_POINT_INVOKED is False, "spec_invalid", "the sealed entry point stays uninvoked")
    plan = document["governing_plan"]
    _exact_keys(plan, ("path", "version", "revision_date", "sha256"), "spec_invalid", "the governing plan record changed")
    _require(plan["path"] == PLAN_RELATIVE, "spec_invalid", "the governing plan path changed")
    _require(plan["version"] == "3.3", "spec_invalid", "the governing plan version changed")
    _require(plan["sha256"] == PLAN_SHA256, "spec_invalid", "the governing plan pin changed")
    _require(sha256_bytes(blobs["governing_plan"]) == PLAN_SHA256, "pin_mismatch", "the governing plan bytes changed")
    reused = document["reused_modules"]
    _require(type(reused) is list and len(reused) == 2, "spec_invalid", "the reused module list changed")
    by_role = {}
    for item in reused:
        _exact_keys(item, ("role", "path", "sha256"), "spec_invalid", "a reused module record changed")
        by_role[item["role"]] = item
    _require(set(by_role) == {"aptarank_io_module", "aptarank_io_specification"}, "spec_invalid", "a reused role changed")
    _require(by_role["aptarank_io_module"]["path"] == IO_MODULE_RELATIVE, "spec_invalid", "the I/O module path changed")
    _require(by_role["aptarank_io_module"]["sha256"] == IO_MODULE_SHA256, "spec_invalid", "the I/O module pin changed")
    _require(by_role["aptarank_io_specification"]["path"] == IO_SPEC_RELATIVE, "spec_invalid", "the I/O specification path changed")
    _require(by_role["aptarank_io_specification"]["sha256"] == IO_SPEC_SHA256, "spec_invalid", "the I/O specification pin changed")
    _require(sha256_bytes(blobs["aptarank_io_module"]) == IO_MODULE_SHA256, "pin_mismatch", "the I/O module bytes changed")
    _require(sha256_bytes(blobs["aptarank_io_specification"]) == IO_SPEC_SHA256, "pin_mismatch", "the I/O specification bytes changed")
    calibration = document["calibration"]
    _exact_keys(
        calibration,
        ("performer", "method", "project_implementation", "local_substitute"),
        "spec_invalid",
        "the calibration record changed",
    )
    _require(calibration["performer"] == "aptarank", "spec_invalid", "AptaRank remains the calibration performer")
    _require(calibration["method"] == "single_pooled_empirical_ref", "spec_invalid", "the calibration method changed")
    _require(calibration["project_implementation"] is False, "spec_invalid", "local calibration must stay unimplemented")
    _require(calibration["local_substitute"] is False, "spec_invalid", "a local calibration substitute is refused")
    schema = document["source_schema"]
    _exact_keys(
        schema,
        (
            "header_source",
            "column_count",
            "columns",
            "partition_column",
            "partition_value",
            "identity_column",
            "core_column",
            "core_digest_column",
            "alphabet",
            "silent_normalization",
            "t_to_u",
            "length_filter",
            "other_row_exclusion",
        ),
        "spec_invalid",
        "the source schema record changed",
    )
    columns = schema["columns"]
    _require(schema["column_count"] == SOURCE_COLUMN_COUNT, "spec_invalid", "the source column count changed")
    _require(
        type(columns) is list and len(columns) == SOURCE_COLUMN_COUNT and len(set(columns)) == SOURCE_COLUMN_COUNT,
        "schema_mismatch",
        "the frozen REF header is malformed",
    )
    _require(all(type(column) is str and column != "" for column in columns), "schema_mismatch", "the frozen REF header is malformed")
    _require(schema["partition_column"] == "partition", "spec_invalid", "the partition column changed")
    _require(schema["partition_value"] == "REF", "spec_invalid", "the partition value changed")
    _require(schema["identity_column"] == "scientific_identity_id", "spec_invalid", "the identity column changed")
    _require(schema["core_column"] == "sequence_core", "spec_invalid", "the core column changed")
    _require(schema["core_digest_column"] == "sequence_core_sha256", "spec_invalid", "the core digest column changed")
    _require(schema["alphabet"] == "^[ACGU]+$", "spec_invalid", "the core alphabet changed")
    for key in ("silent_normalization", "t_to_u", "length_filter", "other_row_exclusion"):
        _require(schema[key] is False, "spec_invalid", "a source transformation is no longer refused")
    retention = document["retention"]
    _exact_keys(
        retention,
        (
            "grain",
            "traversal",
            "upload_order",
            "representative",
            "replacement",
            "upload_fields_from_first_identity",
            "later_identity_rows",
            "later_rows_are_biological_or_quality_exclusions",
            "provenance_ledger",
            "provenance_includes_sequence",
            "provenance_upload_row_number",
            "provenance_is_aptarank_input",
        ),
        "spec_invalid",
        "the retention record changed",
    )
    _require(retention["grain"] == "one_row_per_distinct_sequence_core", "spec_invalid", "the upload grain changed")
    _require(retention["traversal"] == "existing_source_order", "spec_invalid", "the traversal order changed")
    _require(retention["upload_order"] == "first_occurrence", "spec_invalid", "the upload order changed")
    _require(retention["representative"] == "first_identity_row", "spec_invalid", "the representative rule changed")
    _require(retention["replacement"] is False, "spec_invalid", "field replacement is refused")
    _require(retention["upload_fields_from_first_identity"] == FIELD_MAP, "spec_invalid", "the retained field map changed")
    _require(retention["later_identity_rows"] == "duplicate_core_collapses", "spec_invalid", "later rows are duplicate-core collapses")
    _require(retention["later_rows_are_biological_or_quality_exclusions"] is False, "spec_invalid", "a collapse is not an exclusion")
    _require(retention["provenance_ledger"] == "all_source_identities_in_source_order", "spec_invalid", "the provenance ledger changed")
    _require(retention["provenance_includes_sequence"] is False, "spec_invalid", "the provenance ledger must omit sequences")
    _require(retention["provenance_upload_row_number"] == "deterministic_1_based", "spec_invalid", "the provenance row number changed")
    _require(retention["provenance_is_aptarank_input"] is False, "spec_invalid", "the private ledger is not an AptaRank input")
    interface = document["reference_upload_interface"]
    _exact_keys(interface, INTERFACE_KEYS, "spec_invalid", "the reference-upload interface changed")
    _require(interface["authority"] == "user_confirmed_live_interface", "spec_invalid", "the live interface authority changed")
    _require(interface["columns"] == list(UPLOAD_COLUMNS), "spec_invalid", "the live reference upload is exactly the sequence column")
    _require(interface["rejected_columns"] == list(REJECTED_UPLOAD_COLUMNS), "spec_invalid", "a rejected reference-upload column changed")
    _require(interface["target_configuration"] == "supplied_separately", "spec_invalid", "target configuration stays separate from the upload")
    _require(interface["provenance_fields_in_upload"] is False, "spec_invalid", "the upload must not carry provenance fields")
    _require(interface["header_exact"] is True, "spec_invalid", "the upload header must be exact")
    _require(interface["sequence_pattern"] == "^[ACGU]+$", "spec_invalid", "the upload sequence pattern changed")
    _require(interface["unique_sequences"] is True, "spec_invalid", "upload sequences must be unique")
    _require(interface["normalization"] is False, "spec_invalid", "upload normalization is refused")
    _require(interface["sequence_rewriting"] is False, "spec_invalid", "sequence rewriting is refused")
    _require(interface["private_ledger_is_aptarank_input"] is False, "spec_invalid", "the private ledger is not an AptaRank input")
    _require(interface["supersedes_five_column_reference_upload"] is True, "spec_invalid", "the five-column reference upload is superseded for M9C")
    _require(interface["supersession_scope"] == "m9c_reference_upload_only", "spec_invalid", "the supersession scope changed")
    _require(interface["historical_m9b_artifacts"] == "preserved", "spec_invalid", "frozen M9B artifacts stay preserved")
    _require(interface["historical_m9b_results_rewritten"] is False, "spec_invalid", "historical M9B results stay unchanged")
    _require(interface["candidate_and_export_behavior_changed"] is False, "spec_invalid", "candidate and export behavior stays unchanged")
    attempt = document["first_failed_publication_attempt"]
    _exact_keys(attempt, ATTEMPT_KEYS, "spec_invalid", "the first failed publication attempt record changed")
    _require(attempt["attempt"] == 1, "spec_invalid", "the first failed attempt number changed")
    _require(attempt["parent_commit"] == FAILED_ATTEMPT_COMMIT, "spec_invalid", "the first failed attempt commit changed")
    _require(attempt["obsolete_contract_sha256"] == OBSOLETE_CONTRACT_SHA256, "spec_invalid", "the obsolete contract digest changed")
    _require(attempt["ref_opened"] is True, "spec_invalid", "the first attempt opened REF")
    _require(attempt["ref_verified"] is True, "spec_invalid", "the first attempt verified REF")
    _require(attempt["preparation_stopped"] is True, "spec_invalid", "the first attempt stopped during preparation")
    _require(
        attempt["stop_reason"] == "obsolete_five_column_contract_required_publication",
        "spec_invalid",
        "the first attempt stopped because the obsolete five-column contract required publication",
    )
    _require(attempt["observed_error_code"] == "missing_required_field", "spec_invalid", "the first attempt error code changed")
    _require(attempt["observed_error_field"] == "publication", "spec_invalid", "the first attempt required publication")
    _require(attempt["output_published"] is False, "spec_invalid", "the first attempt published no output")
    _require(attempt["aptarank_run"] is False, "spec_invalid", "the first attempt did not run AptaRank")
    # retried stays false because this revision has not invoked the corrected publication.
    _require(attempt["retried"] is False, "spec_invalid", "attempt 1 stays unretried in this pre-retry revision")
    for source_name in FIELD_MAP.values():
        _require(source_name in columns, "schema_mismatch", "a retained source field is absent from the header")
    _require("partition" in columns and "sequence_core_sha256" in columns, "schema_mismatch", "the frozen REF header is incomplete")
    expected = document["expected_live_ui_result"]
    _exact_keys(
        expected,
        (
            "label",
            "source_sha256",
            "source_identity_rows",
            "distinct_sequence_cores",
            "duplicate_core_collapses",
            "expected_ui_accepted_count",
            "expected_ui_dropped_count",
            "other_result",
            "aptarank_ui_executed",
            "observed_ui_accepted_count",
            "observed_ui_dropped_count",
        ),
        "spec_invalid",
        "the expected UI result record changed",
    )
    _require(expected["label"] == "expectation_not_observed_ui_result", "spec_invalid", "the UI counts are expectations")
    _require(expected["source_sha256"] == REF_SHA256, "spec_invalid", "the frozen REF digest changed")
    _require(expected["source_identity_rows"] == SOURCE_IDENTITY_ROWS, "spec_invalid", "the frozen identity-row count changed")
    _require(expected["distinct_sequence_cores"] == DISTINCT_SEQUENCE_CORES, "spec_invalid", "the frozen core count changed")
    _require(expected["duplicate_core_collapses"] == DUPLICATE_CORE_COLLAPSES, "spec_invalid", "the frozen collapse count changed")
    _require(expected["expected_ui_accepted_count"] == EXPECTED_UI_ACCEPTED_COUNT, "spec_invalid", "the expected UI accepted count changed")
    _require(expected["expected_ui_dropped_count"] == EXPECTED_UI_DROPPED_COUNT, "spec_invalid", "the expected UI dropped count changed")
    _require(expected["other_result"] == "stop_m9c", "spec_invalid", "a nonmatching sealed preparation must stop M9C")
    _require(expected["aptarank_ui_executed"] is False, "spec_invalid", "AptaRank UI execution stays unrecorded")
    _require(expected["observed_ui_accepted_count"] is None, "spec_invalid", "an observed UI accepted count cannot be stored")
    _require(expected["observed_ui_dropped_count"] is None, "spec_invalid", "an observed UI dropped count cannot be stored")
    _require(SOURCE_IDENTITY_ROWS - DISTINCT_SEQUENCE_CORES == DUPLICATE_CORE_COLLAPSES, "spec_invalid", "the collapse arithmetic changed")
    external = document["external_ref"]
    _exact_keys(
        external,
        ("relative_path", "sha256", "byte_size", "locator", "review_authorized"),
        "spec_invalid",
        "the external REF record changed",
    )
    _require(external["relative_path"] == EXTERNAL_REF_RELATIVE, "spec_invalid", "the external REF path changed")
    _require(external["sha256"] == REF_SHA256, "spec_invalid", "the external REF digest changed")
    _require(external["byte_size"] == REF_BYTE_SIZE, "spec_invalid", "the authorized REF byte size changed")
    _require(type(external["byte_size"]) is int, "spec_invalid", "the authorized REF byte size changed")
    _require(
        external["locator"] == EXTERNAL_REF_LOCATOR,
        "spec_invalid",
        "the external REF locator must record that attempt 1 opened and verified REF and that the corrected retry is not invoked",
    )
    _require(external["review_authorized"] is True, "spec_invalid", "sealed review is not authorized")
    mapping = document["frozen_target_mapping"]
    _exact_keys(
        mapping,
        (
            "structure_file_sha256",
            "selection_record_sha256",
            "aptarank_target_upload_sha256",
            "aptarank_target_upload_recorded_separately",
            "files_opened",
        ),
        "spec_invalid",
        "the target-mapping record changed",
    )
    _require(mapping["structure_file_sha256"] == STRUCTURE_FILE_SHA256, "spec_invalid", "the structure-file digest changed")
    _require(mapping["selection_record_sha256"] == SELECTION_RECORD_SHA256, "spec_invalid", "the selection-record digest changed")
    _require(mapping["aptarank_target_upload_sha256"] == TARGET_UPLOAD_SHA256, "spec_invalid", "the target-upload digest changed")
    _require(mapping["aptarank_target_upload_recorded_separately"] is True, "spec_invalid", "the target-upload digest is recorded separately")
    _require(mapping["files_opened"] is False, "spec_invalid", "target-mapping files stay unopened")
    _require(len({STRUCTURE_FILE_SHA256, SELECTION_RECORD_SHA256, TARGET_UPLOAD_SHA256, REF_SHA256}) == 4, "spec_invalid", "frozen digests are not distinct")
    outputs = document["outputs"]
    _exact_keys(
        outputs,
        (
            "reference_upload_columns",
            "duplicate_provenance",
            "duplicate_provenance_fields",
            "duplicate_provenance_is_aptarank_input",
            "written_by_default",
            "production_directory",
            "publication_method",
            "publication_invoked",
            "existing_destination_refused",
            "atomic_members",
            "sealed_entry_point_invoked",
        ),
        "spec_invalid",
        "the output record changed",
    )
    arp1 = _arp1()
    _require(outputs["reference_upload_columns"] == list(UPLOAD_COLUMNS), "spec_invalid", "the upload columns are exactly sequence")
    _require(outputs["reference_upload_columns"] != list(arp1.REFERENCE_COLUMNS), "spec_invalid", "M9C no longer uses the five-column reference upload")
    _require(
        list(arp1.REFERENCE_COLUMNS) == list(HISTORICAL_FIVE_COLUMN_REFERENCE_UPLOAD),
        "spec_invalid",
        "the historical five-column reference schema was rewritten",
    )
    _require(outputs["duplicate_provenance"] == "private_project_audit_ledger", "spec_invalid", "the provenance ledger kind changed")
    _require(outputs["duplicate_provenance_fields"] == list(LEDGER_KEYS), "spec_invalid", "the private ledger fields changed")
    _require(outputs["duplicate_provenance_is_aptarank_input"] is False, "spec_invalid", "the private ledger is not an AptaRank input")
    _require(outputs["written_by_default"] is False, "spec_invalid", "preparation must not write by default")
    _require(outputs["production_directory"] == PRODUCTION_DESTINATION, "spec_invalid", "the production publication path changed")
    _require(outputs["publication_method"] == PRODUCTION_PUBLICATION_METHOD, "spec_invalid", "the publication method changed")
    # False here is this corrected revision's pre-retry state. Attempt 1 already opened REF.
    _require(outputs["publication_invoked"] is False, "spec_invalid", "corrected publication stays uninvoked before retry")
    _require(outputs["existing_destination_refused"] is True, "spec_invalid", "an existing publication destination must stay refused")
    _require(outputs["atomic_members"] == list(OUTPUT_MEMBERS), "spec_invalid", "the atomic output members changed")
    _require(outputs["sealed_entry_point_invoked"] is False, "spec_invalid", "the sealed entry point stays uninvoked before retry")
    inputs = document["inputs"]
    _exact_keys(
        inputs,
        ("accepted_form", "filesystem_paths", "sealed_locator_requires_review", "sealed_publication_requires_invocation"),
        "spec_invalid",
        "the input record changed",
    )
    _require(inputs["accepted_form"] == "caller_supplied_bytes", "spec_invalid", "the accepted input form changed")
    _require(inputs["filesystem_paths"] is False, "spec_invalid", "filesystem paths stay refused")
    _require(inputs["sealed_locator_requires_review"] is True, "spec_invalid", "the sealed locator requires review")
    _require(inputs["sealed_publication_requires_invocation"] is True, "spec_invalid", "sealed publication requires an explicit invocation")
    _require(type(document["prohibited"]) is list and len(document["prohibited"]) >= 1, "spec_invalid", "the prohibited list is empty")
    try:
        spec, spec_bytes = arp1.load_spec()
    except arp1.AptaRankIOError as exc:
        raise ReferenceUploadError(exc.code, exc.detail) from exc
    _require(sha256_bytes(spec_bytes) == IO_SPEC_SHA256, "pin_mismatch", "the loaded I/O specification pin does not match")
    _require(
        spec["reference_upload_column_order"] == list(HISTORICAL_FIVE_COLUMN_REFERENCE_UPLOAD),
        "spec_schema_drift",
        "the preserved ARP-1 reference columns drifted",
    )
    _require(spec["candidate_upload_column_order"] == ["id", "sequence"], "spec_schema_drift", "candidate upload columns drifted")
    _require(spec["shortlist_export_column_order"] == list(arp1.SHORTLIST_COLUMNS), "spec_schema_drift", "shortlist export columns drifted")


def load_pinned_contract():
    """Load the M9C-1 contract and fail closed on every recorded pin."""
    contract_bytes = _read_pinned_file(CONTRACT_RELATIVE)
    if sha256_bytes(contract_bytes) != CONTRACT_SHA256:
        raise ReferenceUploadError("pin_mismatch", "the reference-upload contract pin does not match")
    try:
        document = json.loads(contract_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReferenceUploadError("spec_invalid", "the reference-upload contract is not readable JSON") from exc
    blobs = {
        "governing_plan": _read_pinned_file(PLAN_RELATIVE),
        "aptarank_io_module": _read_pinned_file(IO_MODULE_RELATIVE),
        "aptarank_io_specification": _read_pinned_file(IO_SPEC_RELATIVE),
    }
    validate_contract_document(document, blobs)
    return document


def _parse_source(payload, document):
    arp1 = _arp1()
    errors = arp1.ErrorList()
    rows = arp1.parse_csv_rows(payload, document["source_schema"]["columns"], errors, "REF source")
    try:
        errors.raise_if_any()
    except arp1.AptaRankIOError as exc:
        raise ReferenceUploadError("schema_mismatch", "the REF source schema is malformed") from exc
    if rows is None:
        raise ReferenceUploadError("schema_mismatch", "the REF source schema is malformed")
    return rows


def _check_source_row(row, document):
    arp1 = _arp1()
    schema = document["source_schema"]
    mapping = document["retention"]["upload_fields_from_first_identity"]
    _require(mapping["sequence"] == schema["core_column"], "spec_invalid", "the upload sequence does not come from sequence_core")
    identity = row[schema["identity_column"]]
    if type(identity) is not str or arp1.ID_TEXT.fullmatch(identity) is None:
        raise ReferenceUploadError("missing_required_field", "a required REF field is missing: scientific_identity_id")
    core = row[schema["core_column"]]
    if type(core) is not str or arp1.SEQUENCE_TEXT.fullmatch(core) is None:
        raise ReferenceUploadError("noncanonical_core", "a REF sequence_core is not canonical uppercase A, C, G and U")
    recorded = row[schema["core_digest_column"]]
    if type(recorded) is not str or recorded != sha256_bytes(core.encode("utf-8")):
        raise ReferenceUploadError("digest_mismatch", "a REF sequence_core digest does not match the core bytes")
    if row[schema["partition_column"]] != schema["partition_value"]:
        raise ReferenceUploadError("schema_mismatch", "a source row is not in the REF partition")
    return identity, core


def _retain_rows(rows, document):
    seen_identities = set()
    order = []
    groups = {}
    for row in rows:
        identity, core = _check_source_row(row, document)
        if identity in seen_identities:
            raise ReferenceUploadError("duplicate_identity", "a scientific identity is duplicated")
        seen_identities.add(identity)
        group = groups.get(core)
        if group is None:
            groups[core] = {
                "sequence": core,
                "retained_id": identity,
                "source_identities": [identity],
            }
            order.append(core)
        else:
            group["source_identities"].append(identity)
    retained = [groups[core] for core in order]
    collapses = sum(len(item["source_identities"]) - 1 for item in retained)
    if collapses != len(rows) - len(retained):
        raise ReferenceUploadError("conflicting_row_count", "duplicate-core accounting does not match the source rows")
    return retained, collapses


def _upload_bytes(retained):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(list(UPLOAD_COLUMNS))
    for item in retained:
        writer.writerow([item["sequence"]])
    return buffer.getvalue().encode("utf-8")


def validate_reference_upload(payload):
    """Accept a finished upload only when its header is exactly sequence.

    Each data row is one canonical uppercase A, C, G and U sequence. Sequences
    are unique. Metadata columns are refused. Nothing in the cell is rewritten.
    """
    _require_bytes(payload)
    if payload.startswith(b"\xef\xbb\xbf") or payload == b"":
        raise ReferenceUploadError("upload_header_invalid", "the reference upload header is not exactly sequence")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReferenceUploadError("upload_validation_failed", "the reference upload is not UTF-8") from exc
    try:
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as exc:
        raise ReferenceUploadError("upload_validation_failed", "the reference upload is not a one-column sequence CSV") from exc
    if not rows or rows[0] != list(UPLOAD_COLUMNS):
        raise ReferenceUploadError("upload_header_invalid", "the reference upload header is not exactly sequence")
    if set(REJECTED_UPLOAD_COLUMNS) & set(rows[0]):
        raise ReferenceUploadError("metadata_column_refused", "the reference upload accepts only the sequence column")
    arp1 = _arp1()
    sequences = []
    seen = set()
    for row in rows[1:]:
        if len(row) != 1:
            raise ReferenceUploadError("metadata_column_refused", "the reference upload accepts only the sequence column")
        sequence = row[0]
        if type(sequence) is not str or arp1.SEQUENCE_TEXT.fullmatch(sequence) is None:
            raise ReferenceUploadError("noncanonical_core", "a reference upload sequence is not canonical uppercase A, C, G and U")
        if sequence in seen:
            raise ReferenceUploadError("duplicate_sequence", "a reference upload sequence is duplicated")
        seen.add(sequence)
        sequences.append(sequence)
    return sequences


def _validate_upload(payload, retained):
    sequences = validate_reference_upload(payload)
    expected = [item["sequence"] for item in retained]
    if sequences != expected:
        raise ReferenceUploadError("upload_validation_failed", "a reference upload sequence was not preserved")
    return sequences


def _validate_private_ledger(payload, sequences):
    """Check the project-only ledger. It never contains sequence text."""
    _require_bytes(payload)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReferenceUploadError("provenance_invalid", "the private provenance ledger is not UTF-8") from exc
    lines = text.splitlines()
    if text not in ("",) and not text.endswith("\n"):
        raise ReferenceUploadError("provenance_invalid", "the private provenance ledger is incomplete")
    if len(lines) != len(sequences):
        raise ReferenceUploadError("provenance_invalid", "the private provenance ledger does not match the upload rows")
    for number, (line, sequence) in enumerate(zip(lines, sequences), start=1):
        try:
            document = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReferenceUploadError("provenance_invalid", "the private provenance ledger is not JSON") from exc
        _exact_keys(document, LEDGER_KEYS, "provenance_invalid", "the provenance ledger schema drifted")
        if type(document["upload_row_number"]) is not int or document["upload_row_number"] != number:
            raise ReferenceUploadError("provenance_invalid", "the upload row number is not the deterministic 1-based position")
        identities = document["source_identities"]
        if type(identities) is not list or not identities or identities[0] != document["retained_id"]:
            raise ReferenceUploadError("provenance_invalid", "the retained identity is not the first source identity")
        if document["collapsed_source_identities"] != identities[1:]:
            raise ReferenceUploadError("provenance_invalid", "collapsed identities are not the later source identities")
        if type(document["retained_id"]) is not str or document["retained_id"] == "":
            raise ReferenceUploadError("provenance_invalid", "the retained identity is missing")
        if sequence in line or "sequence" in document:
            raise ReferenceUploadError("provenance_invalid", "the provenance ledger must omit sequences")
    return lines


def _ledger_bytes(retained):
    lines = []
    for number, item in enumerate(retained, start=1):
        identities = list(item["source_identities"])
        document = {
            "upload_row_number": number,
            "retained_id": item["retained_id"],
            "source_identities": identities,
            "collapsed_source_identities": identities[1:],
        }
        encoded = canonical_json_bytes(document)
        if item["sequence"].encode("utf-8") in encoded:
            raise ReferenceUploadError("provenance_invalid", "the provenance ledger must omit sequences")
        lines.append(encoded)
    payload = b"" if not lines else b"\n".join(lines) + b"\n"
    _validate_private_ledger(payload, [item["sequence"] for item in retained])
    return payload


def _validate_manifest_record(document):
    """Reject a manifest that copies the pre-retry contract status."""
    _exact_keys(document, MANIFEST_KEYS, "manifest_invalid", "the preparation manifest schema drifted")
    if document["status"] == STATUS or document["status"] != MANIFEST_STATUS:
        raise ReferenceUploadError(
            "manifest_invalid",
            "a preparation manifest status is REFERENCE_UPLOAD_PREPARED_APTARANK_NOT_RUN and does not copy the pre-retry contract status",
        )
    if type(document["publication_attempt"]) is not int or document["publication_attempt"] != PUBLICATION_ATTEMPT:
        raise ReferenceUploadError("manifest_invalid", "a preparation manifest records publication attempt 2")


def _manifest_bytes(source_digest, source_rows, retained_count, collapses, upload_hash, ledger_hash):
    document = {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "status": MANIFEST_STATUS,
        "publication_attempt": PUBLICATION_ATTEMPT,
        "source_sha256": source_digest,
        "source_row_count": source_rows,
        "distinct_sequence_cores": retained_count,
        "duplicate_core_collapses": collapses,
        "prepared_upload_row_count": retained_count,
        "reference_upload_sha256": upload_hash,
        "duplicate_provenance_sha256": ledger_hash,
        "local_calibration": False,
        "production_ref_identity_verified": source_digest == REF_SHA256,
        "aptarank_ui_executed": False,
        "observed_ui_accepted_count": None,
        "observed_ui_dropped_count": None,
    }
    _validate_manifest_record(document)
    return canonical_json_bytes(document) + b"\n"


def _require_sealed_preparation_accounting(source_rows, prepared_rows, collapses):
    if (
        source_rows != SOURCE_IDENTITY_ROWS
        or prepared_rows != DISTINCT_SEQUENCE_CORES
        or collapses != DUPLICATE_CORE_COLLAPSES
    ):
        raise ReferenceUploadError(
            "conflicting_row_count",
            "sealed REF preparation accounting is %d identities, %d prepared upload rows, %d duplicate-core collapses; the expected UI result remains %d accepted and %d dropped; M9C stops"
            % (source_rows, prepared_rows, collapses, EXPECTED_UI_ACCEPTED_COUNT, EXPECTED_UI_DROPPED_COUNT),
        )


def prepare_reference_upload(payload, *, enforce_production_identity=False, **forbidden):
    """Collapse caller-supplied REF CSV bytes to one row per distinct core.

    ``enforce_production_identity=True`` requires the frozen REF digest. A
    matching digest verifies production REF bytes. It is not an AptaRank UI
    result. The expected UI result remains 113 accepted and zero dropped.
    Duplicate-core collapses are not drops. This function does not open a path
    and cannot record observed UI counts.
    """
    if forbidden:
        raise ReferenceUploadError("ui_observation_refused", "preparation cannot populate an observed AptaRank UI count")
    if enforce_production_identity is not True and enforce_production_identity is not False:
        raise ReferenceUploadError("input_type_invalid", "enforce_production_identity must be a boolean")
    _require_bytes(payload)
    document = load_pinned_contract()
    source_digest = sha256_bytes(payload)
    if enforce_production_identity is True and source_digest != REF_SHA256:
        raise ReferenceUploadError("digest_mismatch", "the REF bytes do not match the frozen digest")
    rows = _parse_source(payload, document)
    retained, collapses = _retain_rows(rows, document)
    upload = _upload_bytes(retained)
    _validate_upload(upload, retained)
    ledger = _ledger_bytes(retained)
    prepared_rows = len(retained)
    if prepared_rows != len(rows) - collapses or collapses < 0:
        raise ReferenceUploadError("conflicting_row_count", "duplicate-core accounting does not match the source rows")
    identity_verified = source_digest == REF_SHA256
    if identity_verified or enforce_production_identity is True:
        _require_sealed_preparation_accounting(len(rows), prepared_rows, collapses)
    manifest = _manifest_bytes(source_digest, len(rows), prepared_rows, collapses, sha256_bytes(upload), sha256_bytes(ledger))
    return {
        "reference_upload": upload,
        "duplicate_provenance": ledger,
        "preparation_manifest": manifest,
        "reference_upload_sha256": sha256_bytes(upload),
        "duplicate_provenance_sha256": sha256_bytes(ledger),
        "preparation_manifest_sha256": sha256_bytes(manifest),
        "source_sha256": source_digest,
        "source_row_count": len(rows),
        "prepared_upload_row_count": prepared_rows,
        "duplicate_core_collapses": collapses,
        "production_ref_identity_verified": identity_verified,
    }


def _refuse_protected_output_directory(directory):
    if type(directory) is not str or directory == "" or os.path.isabs(directory) is False:
        raise ReferenceUploadError("output_refused", "the output directory must be an absolute path")
    if "\x00" in directory:
        raise ReferenceUploadError("output_refused", "the output directory must be an absolute path")
    root = os.path.abspath(repo_root())
    absolute = os.path.abspath(directory)
    for relative in ("data", "results"):
        protected = os.path.abspath(os.path.join(root, relative))
        if absolute == protected or absolute.startswith(protected + os.sep):
            raise ReferenceUploadError("output_refused", "preparation outputs cannot be written under data or results")


def _write_atomic_bytes(directory, name, blob):
    """Write one file through an exclusive temporary, fsync, link, and directory fsync."""
    if type(name) is not str or name == "" or "/" in name or "\\" in name or name in (".", ".."):
        raise ReferenceUploadError("output_refused", "a preparation output name is not a single file name")
    target = os.path.join(directory, name)
    try:
        os.lstat(target)
    except FileNotFoundError:
        pass
    else:
        raise ReferenceUploadError("output_exists", "a preparation output already exists")
    temporary = target + ".partial"
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    linked = False
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | nofollow, 0o644)
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
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise ReferenceUploadError("output_exists", "a preparation output already exists") from exc
        linked = True
        os.unlink(temporary)
        directory_flags = os.O_RDONLY | nofollow
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        directory_descriptor = os.open(directory, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        if linked:
            try:
                os.unlink(target)
            except OSError:
                pass
        raise
    return target


def write_sealed_preparation_outputs(directory, prepared):
    """Atomically write caller-supplied preparation bytes.

    This wrapper does not locate REF and does not call the sealed entry point.
    """
    if SEALED_REVIEW_AUTHORIZED is not True:
        raise ReferenceUploadError("review_required", "the sealed preparation is not authorized to write outputs")
    if type(prepared) is not dict:
        raise ReferenceUploadError("input_type_invalid", "preparation outputs must be a mapping of byte strings")
    for key in ("observed_ui_accepted_count", "observed_ui_dropped_count", "accepted_count", "dropped_count"):
        if key in prepared:
            raise ReferenceUploadError("ui_observation_refused", "preparation outputs cannot record an observed AptaRank UI count")
    _refuse_protected_output_directory(directory)
    load_pinned_contract()
    try:
        info = os.lstat(directory)
    except OSError as exc:
        raise ReferenceUploadError("output_refused", "the output directory is not a regular directory") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ReferenceUploadError("output_refused", "the output directory is not a regular directory")
    members = (
        (OUTPUT_MEMBERS[0], prepared.get("reference_upload")),
        (OUTPUT_MEMBERS[1], prepared.get("duplicate_provenance")),
        (OUTPUT_MEMBERS[2], prepared.get("preparation_manifest")),
    )
    for _name, blob in members:
        _require_bytes(blob)
    written = {}
    try:
        for name, blob in members:
            written[name] = _write_atomic_bytes(directory, name, blob)
    except BaseException:
        for path in written.values():
            try:
                os.unlink(path)
            except OSError:
                pass
        raise
    return written


def _require_sealed_invocation():
    if SEALED_REVIEW_AUTHORIZED is not True:
        raise ReferenceUploadError("review_required", "the sealed preparation is not authorized to locate external REF bytes")
    if SEALED_ENTRY_POINT_INVOKED is not True:
        raise ReferenceUploadError("sealed_entry_point_not_invoked", "sealed preparation is authorized and the entry point has not been invoked")


def _read_pinned_ref_bytes():
    """Read the pinned REF file. The caller must already have passed its own gate.

    The byte size is checked before the file is opened. Symlinks are refused.
    """
    relative = EXTERNAL_REF_RELATIVE
    if type(relative) is not str or os.path.isabs(relative) or ".." in relative.split("/"):
        raise ReferenceUploadError("pin_invalid", "the external REF path is not repository-relative")
    path = os.path.join(repo_root(), relative)
    root = os.path.realpath(repo_root())
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise ReferenceUploadError("external_ref_unavailable", "the external REF bytes cannot be verified") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ReferenceUploadError("external_ref_unavailable", "the external REF bytes cannot be verified")
    if info.st_size != REF_BYTE_SIZE:
        raise ReferenceUploadError("external_ref_unavailable", "the external REF byte size does not match the authorized size")
    resolved = os.path.realpath(path)
    if os.path.commonpath([root, resolved]) != root:
        raise ReferenceUploadError("pin_invalid", "the external REF path leaves the repository")
    with open(path, "rb") as handle:
        return handle.read()


def _read_external_ref():
    """Read the frozen REF path after the sealed entry point is invoked. Symlinks are refused."""
    _require_sealed_invocation()
    return _read_pinned_ref_bytes()


def prepare_sealed_reference():
    """Locate and verify external REF bytes only when the entry point is invoked.

    Review is authorized. Invocation stays false, so this call returns before
    any external path is opened. The package entry point does not call it.
    """
    _require_sealed_invocation()
    payload = _read_external_ref()
    if sha256_bytes(payload) != REF_SHA256:
        raise ReferenceUploadError("digest_mismatch", "the external REF bytes do not match the frozen digest")
    return prepare_reference_upload(payload, enforce_production_identity=True)


def _absolute_publication_path(directory):
    if type(directory) is not str or directory == "" or "\x00" in directory or directory.startswith("/") is False:
        raise ReferenceUploadError("output_refused", "the output directory must be an absolute path")
    if directory != os.path.normpath(directory):
        raise ReferenceUploadError("output_refused", "the output directory must be an absolute path")
    return directory


def _is_within(path, root):
    prefix = root.rstrip(os.sep) + os.sep
    return path == root or path.startswith(prefix)


def _refuse_non_production_destination(path):
    root = os.path.abspath(repo_root())
    if _is_within(path, os.path.abspath(os.path.join(root, "data"))):
        raise ReferenceUploadError("output_refused", "preparation outputs cannot be written under data")
    if _is_within(path, os.path.abspath(os.path.join(root, "results"))):
        raise ReferenceUploadError("output_refused", "preparation outputs cannot be written under another results path")
    raise ReferenceUploadError("output_refused", "the output directory is not the production publication path")


def _require_absent_regular_destination(path):
    """Refuse symlinks and any existing destination, including an empty directory."""
    current = ""
    for part in path.split("/")[1:-1]:
        current = current + "/" + part
        try:
            info = os.lstat(current)
        except OSError as exc:
            raise ReferenceUploadError("output_refused", "the output directory is not a regular directory") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ReferenceUploadError("output_refused", "the output directory is not a regular directory")
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ReferenceUploadError("output_refused", "the output directory is not a regular directory") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ReferenceUploadError("output_refused", "the publication destination is a symlink")
    raise ReferenceUploadError("output_exists", "an existing publication destination is refused, including an empty directory")


def preflight_publication_destination(directory):
    """Allow only the exact production destination, and only when it is absent."""
    path = _absolute_publication_path(directory)
    derived = os.path.join(
        repo_root(),
        "results",
        "fine_tuning",
        "m9_generator_evaluation",
        "m9c_reference_preparation",
    )
    if path != PRODUCTION_DESTINATION or derived != PRODUCTION_DESTINATION:
        _refuse_non_production_destination(path)
    _require_absent_regular_destination(path)
    return path


def _prepared_members(prepared):
    if type(prepared) is not dict:
        raise ReferenceUploadError("input_type_invalid", "preparation outputs must be a mapping of byte strings")
    for key in ("observed_ui_accepted_count", "observed_ui_dropped_count", "accepted_count", "dropped_count"):
        if key in prepared:
            raise ReferenceUploadError("ui_observation_refused", "preparation outputs cannot record an observed AptaRank UI count")
    members = (
        (OUTPUT_MEMBERS[0], prepared.get("reference_upload"), "reference_upload_sha256"),
        (OUTPUT_MEMBERS[1], prepared.get("duplicate_provenance"), "duplicate_provenance_sha256"),
        (OUTPUT_MEMBERS[2], prepared.get("preparation_manifest"), "preparation_manifest_sha256"),
    )
    for _name, blob, digest_key in members:
        _require_bytes(blob)
        recorded = prepared.get(digest_key)
        if type(recorded) is not str or recorded != sha256_bytes(blob):
            raise ReferenceUploadError("publication_verify_failed", "a prepared digest does not match the prepared bytes")
    try:
        manifest = json.loads(prepared["preparation_manifest"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReferenceUploadError("manifest_invalid", "the preparation manifest is not readable JSON") from exc
    _validate_manifest_record(manifest)
    if manifest["reference_upload_sha256"] != sha256_bytes(prepared["reference_upload"]):
        raise ReferenceUploadError("publication_verify_failed", "the manifest upload digest does not match the prepared bytes")
    if manifest["duplicate_provenance_sha256"] != sha256_bytes(prepared["duplicate_provenance"]):
        raise ReferenceUploadError("publication_verify_failed", "the manifest provenance digest does not match the prepared bytes")
    if manifest["aptarank_ui_executed"] is not False or manifest["observed_ui_accepted_count"] is not None or manifest["observed_ui_dropped_count"] is not None:
        raise ReferenceUploadError("ui_observation_refused", "preparation outputs cannot record an observed AptaRank UI count")
    if manifest["local_calibration"] is not False:
        raise ReferenceUploadError("publication_verify_failed", "the preparation manifest records local calibration")
    sequences = validate_reference_upload(prepared["reference_upload"])
    if manifest["prepared_upload_row_count"] != len(sequences):
        raise ReferenceUploadError("publication_verify_failed", "the prepared upload row count does not match the one-column upload")
    _validate_private_ledger(prepared["duplicate_provenance"], sequences)
    return members


def _fsync_directory(directory):
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_RDONLY | nofollow
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reread_verified_members(directory, prepared):
    members = _prepared_members(prepared)
    found = []
    with os.scandir(directory) as entries:
        for entry in entries:
            found.append(entry.name)
    if sorted(found) != sorted(OUTPUT_MEMBERS):
        raise ReferenceUploadError("publication_verify_failed", "the publication directory does not contain exactly the three prepared members")
    for name, blob, _digest_key in members:
        path = os.path.join(directory, name)
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ReferenceUploadError("publication_verify_failed", "a publication member is not a regular file")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            chunks = []
            while True:
                piece = os.read(descriptor, 1024 * 1024)
                if piece == b"":
                    break
                chunks.append(piece)
        finally:
            os.close(descriptor)
        got = b"".join(chunks)
        if got != blob or sha256_bytes(got) != sha256_bytes(blob):
            raise ReferenceUploadError("publication_verify_failed", "a reread publication member does not match the prepared bytes")
    return members


def _rename_noreplace(source, destination):
    """Move a directory with renameat2(RENAME_NOREPLACE). An existing destination stays in place."""
    renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise ReferenceUploadError("output_exists", "an existing publication destination is refused, including an empty directory")
    raise OSError(error_number, os.strerror(error_number), destination)


def _remove_invocation_temp(directory):
    """Remove one invocation temporary directory. Do not follow symlinks or touch the destination."""
    if type(directory) is not str or directory == "" or directory == PRODUCTION_DESTINATION:
        raise ReferenceUploadError("output_refused", "cleanup refused the publication destination")
    if ".partial." not in os.path.basename(directory):
        raise ReferenceUploadError("output_refused", "cleanup refused a directory that is not an invocation temporary")
    try:
        info = os.lstat(directory)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        os.unlink(directory)
        return
    with os.scandir(directory) as entries:
        children = list(entries)
    for entry in children:
        child_info = os.lstat(entry.path)
        if stat.S_ISDIR(child_info.st_mode) and not stat.S_ISLNK(child_info.st_mode):
            raise ReferenceUploadError("output_refused", "the publication temporary directory contains a nested directory")
        os.unlink(entry.path)
    os.rmdir(directory)


def _publish_prepared_directory(directory, prepared):
    """Write three members to a temporary sibling, reread them, then rename the directory once."""
    path = _absolute_publication_path(directory)
    if path != PRODUCTION_DESTINATION:
        root = os.path.abspath(repo_root())
        if _is_within(path, os.path.join(root, "data")) or _is_within(path, os.path.join(root, "results")):
            _refuse_non_production_destination(path)
    _require_absent_regular_destination(path)
    members = _prepared_members(prepared)
    parent = os.path.dirname(path)
    temporary = None
    try:
        temporary = tempfile.mkdtemp(prefix="." + os.path.basename(path) + ".partial.", dir=parent)
        for name, blob, _digest_key in members:
            _write_atomic_bytes(temporary, name, blob)
        _reread_verified_members(temporary, prepared)
        _fsync_directory(temporary)
        _rename_noreplace(temporary, path)
        temporary = None
        _fsync_directory(parent)
    except BaseException as original:
        if temporary is not None:
            try:
                _remove_invocation_temp(temporary)
            except BaseException as cleanup_error:
                raise ReferenceUploadError(
                    "publication_cleanup_failed",
                    "the publication temporary directory could not be removed",
                ) from cleanup_error
        raise original
    return path


def publish_sealed_reference_preparation(*, invoke=False, **forbidden):
    """Publish the pinned REF preparation after an explicit invocation flag.

    Contract and destination preflight finish before REF is opened. This
    function does not call ``prepare_sealed_reference``. The no-argument
    command does not call this function.
    """
    if forbidden:
        raise ReferenceUploadError("ui_observation_refused", "preparation cannot populate an observed AptaRank UI count")
    if invoke is not True:
        raise ReferenceUploadError(
            "sealed_publication_not_invoked",
            "sealed publication is authorized and the entry point has not been invoked",
        )
    if SEALED_REVIEW_AUTHORIZED is not True:
        raise ReferenceUploadError("review_required", "the sealed publication is not authorized")
    if SEALED_ENTRY_POINT_INVOKED is not False:
        raise ReferenceUploadError("spec_invalid", "the sealed entry point stays uninvoked")
    document = load_pinned_contract()
    if document["outputs"]["production_directory"] != PRODUCTION_DESTINATION:
        raise ReferenceUploadError("spec_invalid", "the production publication path changed")
    if document["outputs"]["publication_invoked"] is not False:
        raise ReferenceUploadError("spec_invalid", "sealed publication stays uninvoked")
    destination = preflight_publication_destination(PRODUCTION_DESTINATION)
    payload = _read_pinned_ref_bytes()
    if len(payload) != REF_BYTE_SIZE:
        raise ReferenceUploadError("external_ref_unavailable", "the external REF byte size does not match the authorized size")
    if sha256_bytes(payload) != REF_SHA256:
        raise ReferenceUploadError("digest_mismatch", "the external REF bytes do not match the frozen digest")
    prepared = prepare_reference_upload(payload, enforce_production_identity=True)
    published = _publish_prepared_directory(destination, prepared)
    return {
        "published_directory": published,
        "reference_upload_sha256": prepared["reference_upload_sha256"],
        "duplicate_provenance_sha256": prepared["duplicate_provenance_sha256"],
        "preparation_manifest_sha256": prepared["preparation_manifest_sha256"],
        "source_sha256": prepared["source_sha256"],
        "source_row_count": prepared["source_row_count"],
        "prepared_upload_row_count": prepared["prepared_upload_row_count"],
        "duplicate_core_collapses": prepared["duplicate_core_collapses"],
        "production_ref_identity_verified": prepared["production_ref_identity_verified"],
    }


def verify_frozen_target_mapping(structure_bytes, selection_bytes, target_upload_bytes):
    """Compare three caller-supplied byte strings with the frozen target digests.

    The AptaRank target-upload digest is checked on its own. This function
    does not open a structure file, a selection record, or an upload file.
    """
    supplied = (
        ("structure_file", structure_bytes, STRUCTURE_FILE_SHA256),
        ("selection_record", selection_bytes, SELECTION_RECORD_SHA256),
        ("aptarank_target_upload", target_upload_bytes, TARGET_UPLOAD_SHA256),
    )
    for _label, payload, _expected in supplied:
        _require_bytes(payload)
    load_pinned_contract()
    for label, payload, expected in supplied:
        if sha256_bytes(payload) != expected:
            raise ReferenceUploadError("digest_mismatch", label + " digest does not match the frozen target mapping")
    return {
        "structure_file_sha256": STRUCTURE_FILE_SHA256,
        "selection_record_sha256": SELECTION_RECORD_SHA256,
        "aptarank_target_upload_sha256": TARGET_UPLOAD_SHA256,
        "aptarank_target_upload_recorded_separately": True,
    }


def main(argv=None):
    """Check pins and print the status. The sealed entry point is not called."""
    if argv is None:
        argv = sys.argv[1:]
    if argv:
        raise ReferenceUploadError("production_runner_refused", "M9C-1 has no production runner")
    load_pinned_contract()
    sys.stdout.write(STATUS + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReferenceUploadError as exc:
        sys.stderr.write(exc.code + ": " + exc.detail + "\n")
        raise SystemExit(1)

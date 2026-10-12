#!/usr/bin/env python3
"""M9C-1 reference-upload preparation.

One upload row is retained for each distinct canonical REF sequence_core.
The no-argument command checks pins only. It does not locate REF, EVAL, or a
production candidate source, and it does not calibrate AptaRank.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import os
import stat
import sys

PACKAGE_ID = "M9C-1"
SCHEMA_VERSION = "m9c-reference-upload-v1"
STATUS = "POLICY_FROZEN_REF_UNOPENED"
STAGE = "M9C-1"
CONTRACT_RELATIVE = "config/modelling/aptarank_reference_upload_contract.json"
CONTRACT_SHA256 = "b0387bc6d7c8d5328ccdbea05ad263b203b3405f80d7f359a6440751eb4e1b0f"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
IO_SPEC_RELATIVE = "config/modelling/aptarank_io_spec.json"
IO_SPEC_SHA256 = "46ba6c8be873dad4c086e9f6b889b51702ba31212fa502d00f26e267a22da732"
IO_MODULE_RELATIVE = "scripts/modelling/aptarank_io_preflight.py"
IO_MODULE_SHA256 = "eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01"
REF_SHA256 = "531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23"
EXTERNAL_REF_RELATIVE = "data/processed/ref.csv"
SEALED_REVIEW_AUTHORIZED = False
SOURCE_COLUMN_COUNT = 85
SOURCE_IDENTITY_ROWS = 131
DISTINCT_SEQUENCE_CORES = 113
DUPLICATE_CORE_COLLAPSES = 18
EXPECTED_UI_ACCEPTED_COUNT = 113
EXPECTED_UI_DROPPED_COUNT = 0
STRUCTURE_FILE_SHA256 = "2e185a205c9be0bf76484e8ffb96ae225880723ed68eaaf25dffbbccaf01ff51"
SELECTION_RECORD_SHA256 = "08f0c96af349ce4909d40c3004804317661777f72828cd807823341e0e4f0d04"
TARGET_UPLOAD_SHA256 = "46471bb0643125ce86300ec050d6f0d3a09faa1d06dc325141c67cd1acdd5922"
FIELD_MAP = {
    "id": "scientific_identity_id",
    "sequence": "sequence_core",
    "target_name": "canonical_target_name",
    "target_pdb_id": "pdb_id",
    "source_reference": "publication",
}
LEDGER_KEYS = ("retained_id", "source_identities", "collapsed_source_identities")
MANIFEST_KEYS = (
    "package_id",
    "schema_version",
    "status",
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
    "expected_live_ui_result",
    "external_ref",
    "frozen_target_mapping",
    "outputs",
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
        "production_inputs_opened",
        "ref_opened",
        "eval_opened",
        "production_candidates_opened",
        "local_calibration",
        "local_calibration_substitute",
        "aptarank_execution",
        "deployment_verified",
        "sealed_review_authorized",
    ):
        _require(document[key] is False, "spec_invalid", "a closed policy flag is no longer false")
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
        ("relative_path", "sha256", "locator", "review_authorized"),
        "spec_invalid",
        "the external REF record changed",
    )
    _require(external["relative_path"] == EXTERNAL_REF_RELATIVE, "spec_invalid", "the external REF path changed")
    _require(external["sha256"] == REF_SHA256, "spec_invalid", "the external REF digest changed")
    _require(external["locator"] == "inactive_until_review", "spec_invalid", "the sealed locator is not inactive")
    _require(external["review_authorized"] is False, "spec_invalid", "sealed review is not authorized")
    _require(SEALED_REVIEW_AUTHORIZED is False, "review_required", "sealed review is not authorized")
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
        ("reference_upload_columns", "duplicate_provenance", "written_by_default", "production_directory"),
        "spec_invalid",
        "the output record changed",
    )
    arp1 = _arp1()
    _require(outputs["reference_upload_columns"] == list(arp1.REFERENCE_COLUMNS), "spec_invalid", "the upload columns drifted from ARP-1")
    _require(outputs["duplicate_provenance"] == "restricted_identity_ledger", "spec_invalid", "the provenance ledger kind changed")
    _require(outputs["written_by_default"] is False, "spec_invalid", "preparation must not write by default")
    _require(outputs["production_directory"] is False, "spec_invalid", "preparation has no production directory")
    inputs = document["inputs"]
    _exact_keys(inputs, ("accepted_form", "filesystem_paths", "sealed_locator_requires_review"), "spec_invalid", "the input record changed")
    _require(inputs["accepted_form"] == "caller_supplied_bytes", "spec_invalid", "the accepted input form changed")
    _require(inputs["filesystem_paths"] is False, "spec_invalid", "filesystem paths stay refused")
    _require(inputs["sealed_locator_requires_review"] is True, "spec_invalid", "the sealed locator requires review")
    _require(type(document["prohibited"]) is list and len(document["prohibited"]) >= 1, "spec_invalid", "the prohibited list is empty")
    try:
        spec, spec_bytes = arp1.load_spec()
    except arp1.AptaRankIOError as exc:
        raise ReferenceUploadError(exc.code, exc.detail) from exc
    _require(sha256_bytes(spec_bytes) == IO_SPEC_SHA256, "pin_mismatch", "the loaded I/O specification pin does not match")
    _require(spec["reference_upload_column_order"] == list(arp1.REFERENCE_COLUMNS), "spec_schema_drift", "ARP-1 reference columns drifted")


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


def _required_text(value, label):
    arp1 = _arp1()
    if type(value) is not str or arp1.UNINTERPRETED_TEXT.fullmatch(value) is None:
        raise ReferenceUploadError("missing_required_field", "a required REF field is missing: " + label)


def _check_source_row(row, document):
    arp1 = _arp1()
    schema = document["source_schema"]
    mapping = document["retention"]["upload_fields_from_first_identity"]
    identity = row[mapping["id"]]
    if type(identity) is not str or arp1.ID_TEXT.fullmatch(identity) is None:
        raise ReferenceUploadError("missing_required_field", "a required REF field is missing: scientific_identity_id")
    core = row[mapping["sequence"]]
    if type(core) is not str or arp1.SEQUENCE_TEXT.fullmatch(core) is None:
        raise ReferenceUploadError("noncanonical_core", "a REF sequence_core is not canonical uppercase A, C, G and U")
    recorded = row[schema["core_digest_column"]]
    if type(recorded) is not str or recorded != sha256_bytes(core.encode("utf-8")):
        raise ReferenceUploadError("digest_mismatch", "a REF sequence_core digest does not match the core bytes")
    _required_text(row[mapping["target_name"]], "canonical_target_name")
    _required_text(row[mapping["source_reference"]], "publication")
    pdb_id = row[mapping["target_pdb_id"]]
    if type(pdb_id) is not str or (pdb_id != "" and arp1.UNINTERPRETED_TEXT.fullmatch(pdb_id) is None):
        raise ReferenceUploadError("invalid_target_pdb_id", "a REF pdb_id must be blank or free of surrounding whitespace")
    if row[schema["partition_column"]] != schema["partition_value"]:
        raise ReferenceUploadError("schema_mismatch", "a source row is not in the REF partition")
    return identity, core


def _retain_rows(rows, document):
    mapping = document["retention"]["upload_fields_from_first_identity"]
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
                "id": identity,
                "sequence": core,
                "target_name": row[mapping["target_name"]],
                "target_pdb_id": row[mapping["target_pdb_id"]],
                "source_reference": row[mapping["source_reference"]],
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
    arp1 = _arp1()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(list(arp1.REFERENCE_COLUMNS))
    for item in retained:
        writer.writerow([item["id"], item["sequence"], item["target_name"], item["target_pdb_id"], item["source_reference"]])
    return buffer.getvalue().encode("utf-8")


def _validate_upload(payload, retained):
    arp1 = _arp1()
    errors = arp1.ErrorList()
    parsed = arp1.parse_csv_rows(payload, arp1.REFERENCE_COLUMNS, errors, "reference upload")
    arp1._check_reference_rows(parsed, errors)
    try:
        errors.raise_if_any()
    except arp1.AptaRankIOError as exc:
        raise ReferenceUploadError("upload_validation_failed", "the reference upload failed the reused validator") from exc
    if parsed is None or len(parsed) != len(retained):
        raise ReferenceUploadError("upload_validation_failed", "the reference upload row count drifted")
    for item, actual in zip(retained, parsed):
        expected = {
            "id": item["id"],
            "sequence": item["sequence"],
            "target_name": item["target_name"],
            "target_pdb_id": item["target_pdb_id"],
            "source_reference": item["source_reference"],
        }
        if actual != expected:
            raise ReferenceUploadError("upload_validation_failed", "a reference upload field was not preserved")


def _ledger_bytes(retained):
    lines = []
    for item in retained:
        identities = list(item["source_identities"])
        document = {
            "retained_id": item["id"],
            "source_identities": identities,
            "collapsed_source_identities": identities[1:],
        }
        _exact_keys(document, LEDGER_KEYS, "provenance_invalid", "the provenance ledger schema drifted")
        if document["source_identities"][0] != document["retained_id"]:
            raise ReferenceUploadError("provenance_invalid", "the retained identity is not the first source identity")
        if item["sequence"] in document["source_identities"] or item["sequence"] in document["collapsed_source_identities"]:
            raise ReferenceUploadError("provenance_invalid", "the provenance ledger must omit sequences")
        lines.append(canonical_json_bytes(document))
    if not lines:
        return b""
    return b"\n".join(lines) + b"\n"


def _manifest_bytes(source_digest, source_rows, retained_count, collapses, upload_hash, ledger_hash):
    document = {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
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
    _exact_keys(document, MANIFEST_KEYS, "manifest_invalid", "the preparation manifest schema drifted")
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


def _read_external_ref():
    """Read the frozen REF path after review authorization. Symlinks are refused."""
    if SEALED_REVIEW_AUTHORIZED is not True:
        raise ReferenceUploadError("review_required", "the sealed preparation is not authorized to locate external REF bytes")
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
    resolved = os.path.realpath(path)
    if os.path.commonpath([root, resolved]) != root:
        raise ReferenceUploadError("pin_invalid", "the external REF path leaves the repository")
    with open(path, "rb") as handle:
        return handle.read()


def prepare_sealed_reference():
    """Locate and verify external REF bytes only after a reviewed authorization.

    This package leaves that authorization false. The call fails before any
    external path is opened.
    """
    if SEALED_REVIEW_AUTHORIZED is not True:
        raise ReferenceUploadError("review_required", "the sealed preparation is not authorized to locate external REF bytes")
    payload = _read_external_ref()
    if sha256_bytes(payload) != REF_SHA256:
        raise ReferenceUploadError("digest_mismatch", "the external REF bytes do not match the frozen digest")
    return prepare_reference_upload(payload, enforce_production_identity=True)


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
    """Check pins and print the status. There is no production runner."""
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

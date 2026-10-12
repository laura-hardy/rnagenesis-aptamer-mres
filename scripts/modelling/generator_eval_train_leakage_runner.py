#!/usr/bin/env python3
"""Synthetic-only M9A TRAIN leakage and nearest-TRAIN-distance preparation.

The public core accepts combined-ledger bytes, TRAIN CSV bytes, TRAIN text
bytes, and explicit expected identities. It checks those digests, then the
pinned M9A contract, governing plan, frozen data contract, and this runner
contract, before it parses a row or a TRAIN field.

``corpus_final.txt`` is the comparison population. ``ft_train.csv`` stays the
identity-grain provenance source. Identity rows are not replaced by a set.
TRAIN cores are not rewritten. The historical 0.01 guardrail is not a decision
threshold. Nearest-distance scalars are computed once per globally distinct
generated sequence and then read back by the frozen summary. That cache does
not replace ``nearest_train_distance_summaries``.

``run_sealed_train_leakage`` is the production entry. It remains unexecuted.
Before any sealed source is opened, it validates the invocation and production
identity bundle, validates the root and output paths, refuses an existing
output destination, verifies the pinned contracts, and verifies that the runner
commit is available. It then opens the combined ledger, the TRAIN CSV, and the
TRAIN text one at a time, verifying each production digest before the next
open, and only then parses. The in-memory core repeats those checks. Synthetic
tests must not call it. A synthetic run is not production validation and does
not complete M9A.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from generator_eval_derived_ledger import _contains_sequence_text
from generator_eval_overlap_leakage import (
    COMBINED_LEDGER_SHA256,
    CONTRACT_ID as M9A_CONTRACT_ID,
    GOVERNING_PLAN_SHA256,
    OverlapLeakageError,
    exact_train_leakage,
    nearest_train_distance_summaries,
)
from generator_eval_overlap_runner import OverlapRunnerError, _accept_rows, parse_combined_ledger
from generator_eval_parser import (
    CANONICAL_SEQUENCE,
    FORBIDDEN_BASENAMES,
    PARSER_VERSION,
    REFUSED_ROLES,
    enforce_firewall,
    reject_control_string,
)
from generator_eval_source_adapters import ADAPTER_VERSION

import generator_eval_overlap_leakage as _leakage

EXACT_SUMMARY_SCHEMA = "generator-eval-exact-train-leakage-summary-m9a-r1"
NEAREST_SUMMARY_SCHEMA = "generator-eval-nearest-train-distance-summary-m9a-r1"
MANIFEST_SCHEMA = "generator-eval-train-leakage-manifest-m9a-r1"
RUNNER_CONTRACT_ID = "m9a-train-leakage-runner-v1"
RUNNER_CONTRACT_SHA256 = "ef68b1575df4d770af2bdd622eeb84f647a18db9d4cbd115e0b8a60de5dce528"
FROZEN_DATA_CONTRACT_ID = "rnagenesis_corrected_669_core_m0"
FROZEN_DATA_CONTRACT_SHA256 = "396c83c3dbf9afc656ad5c60ec05c94fce3c5a684990c3cc1cebfb2411ccd5ff"
M9A_CONTRACT_SHA256 = "6aeaa2338776cbe7aceffef63ee4ca7dfd7ed3643aa7d1e400fd54a02d113535"
TRAIN_CSV_SHA256 = "84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0"
TRAIN_TEXT_SHA256 = "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d"
TRAIN_IDENTITY_SET_HASH = "be5d3c700534633fce62498ea0b5d69cf0bfab148ad6a07931bc3b875efc9d5d"
TRAIN_CLUSTER_SET_HASH = "07f6dac62f5a280b5f4204724d20a3a1448bc5be13c99d8b6eda63dfc491d02e"
PRODUCTION_MANIFEST_SHA256 = "9aa5f60f939a8b25d031967ed3466a26d9d8e2d0610c76ec0b5db4cb43c2cc80"
M9A_CONTRACT_RELATIVE = "config/modelling/generator_eval_overlap_leakage_contract.json"
GOVERNING_PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan.md"
FROZEN_DATA_CONTRACT_RELATIVE = "config/modelling/frozen_data_contract.json"
RUNNER_CONTRACT_RELATIVE = "config/modelling/generator_eval_train_leakage_runner_contract.json"
SEALED_COMBINED_LEDGER_RELATIVE = (
    "results/fine_tuning/m9_generator_evaluation/m9_all_conditions_derived_attempt_ledger.jsonl"
)
FUTURE_OUTPUT_RELATIVE = "results/fine_tuning/m9_generator_evaluation/m9a_train_leakage"
DEVELOPMENT_TRAIN_CSV = "/home/laura/rnagenesis-mres-data/development/ft_train.csv"
DEVELOPMENT_TRAIN_TEXT = "/home/laura/rnagenesis-mres-data/development/corpus_final.txt"
EXACT_SUMMARY_FILENAME = "m9_exact_train_leakage_summary.json"
NEAREST_SUMMARY_FILENAME = "m9_nearest_train_distance_summary.json"
MANIFEST_FILENAME = "m9_train_leakage_manifest.json"
OUTPUT_FILENAMES = (EXACT_SUMMARY_FILENAME, NEAREST_SUMMARY_FILENAME, MANIFEST_FILENAME)
PRODUCTION_ROW_COUNTS = {"B0": 30080, "B1": 30000, "B2": 30000, "D1": 30000, "combined": 120080}
PRODUCTION_TRAIN_IDENTITY_ROWS = 726
PRODUCTION_TRAIN_DISTINCT_CORES = 669
PRODUCTION_TRAIN_CLUSTERS = 569
PRODUCTION_TRAIN_TARGETS = 320
PRODUCTION_TRAIN_CSV_COLUMN_COUNT = 86
PRODUCTION_TRAIN_CSV_BYTE_COUNT = 1201524
PRODUCTION_TRAIN_TEXT_BYTE_COUNT = 37700
ROW_COUNT_FIELDS = ("B0", "B1", "B2", "D1", "combined")
REQUIRED_TRAIN_COLUMNS = (
    "scientific_identity_id",
    "sequence_core",
    "sequence_core_sha256",
    "sequence_length_core",
    "cluster_id",
    "canonical_target_name",
    "partition",
    "ft_split",
)
IDENTITY_FIELDS = (
    "m9a_contract_id",
    "m9a_contract_sha256",
    "governing_plan_sha256",
    "frozen_data_contract_sha256",
    "runner_contract_id",
    "runner_contract_sha256",
    "combined_ledger_sha256",
    "train_csv_sha256",
    "train_text_sha256",
    "parser_version",
    "adapter_version",
    "ledger_row_counts",
    "train_identity_rows",
    "train_distinct_cores",
    "synthetic_execution_is_production_validation",
)
DIGEST_FIELDS = (
    "m9a_contract_sha256",
    "governing_plan_sha256",
    "frozen_data_contract_sha256",
    "runner_contract_sha256",
    "combined_ledger_sha256",
    "train_csv_sha256",
    "train_text_sha256",
)
SEALED_BASENAMES = frozenset(
    ("ft_train.csv", "corpus_final.txt", "m9_all_conditions_derived_attempt_ledger.jsonl")
)
GENERIC_READ_BAN = FORBIDDEN_BASENAMES | frozenset(("m9_all_conditions_derived_attempt_ledger.jsonl",))
TEMP_PREFIX = ".m9-train-leakage-runner."
COMPARISON_POPULATION = "corpus_final_text_equal_to_train_csv_first_occurrence_cores"
SERIALIZATION = "UTF-8 JSON, trailing LF, indent 2, ensure_ascii, constructed key order, allow_nan false"
SEALED_SOURCE_OPENING_ORDER = {
    "before_any_sealed_source_is_opened": [
        "validate_invocation_and_production_identity_bundle",
        "validate_root_and_output_paths",
        "refuse_existing_output_destination_including_empty_directory_or_symlink",
        "verify_pinned_m9a_contract",
        "verify_pinned_governing_plan",
        "verify_pinned_frozen_data_contract",
        "verify_pinned_runner_contract",
        "verify_runner_commit_available",
    ],
    "then_open_and_verify_each_digest_before_the_next_open": [
        "combined_ledger",
        "train_csv",
        "train_text",
    ],
    "parsing_and_metric_computation_after_all_three_digests_match": True,
    "in_memory_core_rechecks_digests_schema_counts_provenance_and_output_destination": True,
    "source_parsed_before_its_digest_matches": False,
}
SEALED_SOURCE_LABELS = ("combined_ledger", "train_csv", "train_text")


class TrainLeakageRunnerError(ValueError):
    """The TRAIN leakage runner refused the request and wrote nothing."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _is_sha256(value):
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_bytes(value, label):
    if type(value) is bytes:
        return value
    if type(value) is str:
        reject_control_string(value)
    raise TrainLeakageRunnerError("payload_type_invalid", label + " must be in-memory bytes")


def _require_sha256(value, label):
    if not _is_sha256(value):
        raise TrainLeakageRunnerError("identity_invalid", label + " is not lowercase sha256")
    return value


def _nonnegative_int(value, label):
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise TrainLeakageRunnerError("identity_invalid", label + " is not a nonnegative integer")
    return value


def _row_count_identity(value):
    if type(value) is not dict or set(value) != set(ROW_COUNT_FIELDS):
        raise TrainLeakageRunnerError("identity_invalid", "ledger row-count identities are not B0, B1, B2, D1, and combined")
    counts = {name: _nonnegative_int(value[name], name + " row count") for name in ROW_COUNT_FIELDS}
    if counts["combined"] != counts["B0"] + counts["B1"] + counts["B2"] + counts["D1"]:
        raise TrainLeakageRunnerError("identity_invalid", "the combined row-count identity is not the sum of the conditions")
    return counts


def _production_bundle(checked):
    return (
        checked["combined_ledger_sha256"] == COMBINED_LEDGER_SHA256
        and checked["train_csv_sha256"] == TRAIN_CSV_SHA256
        and checked["train_text_sha256"] == TRAIN_TEXT_SHA256
        and checked["ledger_row_counts"] == PRODUCTION_ROW_COUNTS
        and checked["train_identity_rows"] == PRODUCTION_TRAIN_IDENTITY_ROWS
        and checked["train_distinct_cores"] == PRODUCTION_TRAIN_DISTINCT_CORES
    )


def validate_identities(identities, *, enforce_production_identities):
    """Check expected identities. Do not open the ledger or TRAIN."""
    if type(identities) is not dict or set(identities) != set(IDENTITY_FIELDS):
        raise TrainLeakageRunnerError("identity_invalid", "expected identities do not match the runner identity set")
    if type(enforce_production_identities) is not bool:
        raise TrainLeakageRunnerError("identity_invalid", "production-identity enforcement is not a boolean")
    for name in DIGEST_FIELDS:
        _require_sha256(identities[name], name)
    if identities["m9a_contract_id"] != M9A_CONTRACT_ID:
        raise TrainLeakageRunnerError("contract_identity_mismatch", "the M9A contract identity is not the frozen identity")
    if identities["runner_contract_id"] != RUNNER_CONTRACT_ID:
        raise TrainLeakageRunnerError("contract_identity_mismatch", "the runner contract identity is not the frozen identity")
    if identities["parser_version"] != PARSER_VERSION:
        raise TrainLeakageRunnerError("parser_version_mismatch", "the expected parser is not m9-biological-parser-v1")
    if identities["adapter_version"] != ADAPTER_VERSION:
        raise TrainLeakageRunnerError("adapter_version_mismatch", "the expected adapter is not m9-source-adapter-v2")
    if identities["synthetic_execution_is_production_validation"] is not False:
        raise TrainLeakageRunnerError(
            "production_validation_claim_refused",
            "synthetic execution is not production validation",
        )
    counts = _row_count_identity(identities["ledger_row_counts"])
    identity_rows = _nonnegative_int(identities["train_identity_rows"], "TRAIN identity rows")
    distinct_cores = _nonnegative_int(identities["train_distinct_cores"], "TRAIN distinct cores")
    if distinct_cores > identity_rows:
        raise TrainLeakageRunnerError("identity_invalid", "distinct TRAIN cores cannot exceed TRAIN identity rows")
    checked = {
        "m9a_contract_id": M9A_CONTRACT_ID,
        "m9a_contract_sha256": identities["m9a_contract_sha256"],
        "governing_plan_sha256": identities["governing_plan_sha256"],
        "frozen_data_contract_sha256": identities["frozen_data_contract_sha256"],
        "runner_contract_id": RUNNER_CONTRACT_ID,
        "runner_contract_sha256": identities["runner_contract_sha256"],
        "combined_ledger_sha256": identities["combined_ledger_sha256"],
        "train_csv_sha256": identities["train_csv_sha256"],
        "train_text_sha256": identities["train_text_sha256"],
        "parser_version": PARSER_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "ledger_row_counts": counts,
        "train_identity_rows": identity_rows,
        "train_distinct_cores": distinct_cores,
        "synthetic_execution_is_production_validation": False,
    }
    if checked["m9a_contract_sha256"] != M9A_CONTRACT_SHA256:
        raise TrainLeakageRunnerError("m9a_contract_digest_mismatch", "the expected M9A contract digest is not the frozen digest")
    if checked["governing_plan_sha256"] != GOVERNING_PLAN_SHA256:
        raise TrainLeakageRunnerError("governing_plan_digest_mismatch", "the expected governing-plan digest is not the frozen digest")
    if checked["frozen_data_contract_sha256"] != FROZEN_DATA_CONTRACT_SHA256:
        raise TrainLeakageRunnerError(
            "frozen_data_contract_digest_mismatch",
            "the expected frozen-data-contract digest is not the frozen digest",
        )
    if checked["runner_contract_sha256"] != RUNNER_CONTRACT_SHA256:
        raise TrainLeakageRunnerError(
            "runner_contract_digest_mismatch",
            "the expected runner-contract digest is not the frozen digest",
        )
    if enforce_production_identities:
        if not _production_bundle(checked):
            raise TrainLeakageRunnerError(
                "production_identity_mismatch",
                "production enforcement requires the sealed ledger, TRAIN, and count identities",
            )
    elif _production_bundle(checked):
        raise TrainLeakageRunnerError(
            "production_identity_claim_refused",
            "synthetic mode cannot claim the frozen production identities",
        )
    return checked


def sealed_identities():
    """Frozen production identities. This does not open the ledger or TRAIN."""
    return {
        "m9a_contract_id": M9A_CONTRACT_ID,
        "m9a_contract_sha256": M9A_CONTRACT_SHA256,
        "governing_plan_sha256": GOVERNING_PLAN_SHA256,
        "frozen_data_contract_sha256": FROZEN_DATA_CONTRACT_SHA256,
        "runner_contract_id": RUNNER_CONTRACT_ID,
        "runner_contract_sha256": RUNNER_CONTRACT_SHA256,
        "combined_ledger_sha256": COMBINED_LEDGER_SHA256,
        "train_csv_sha256": TRAIN_CSV_SHA256,
        "train_text_sha256": TRAIN_TEXT_SHA256,
        "parser_version": PARSER_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "ledger_row_counts": {name: PRODUCTION_ROW_COUNTS[name] for name in ROW_COUNT_FIELDS},
        "train_identity_rows": PRODUCTION_TRAIN_IDENTITY_ROWS,
        "train_distinct_cores": PRODUCTION_TRAIN_DISTINCT_CORES,
        "synthetic_execution_is_production_validation": False,
    }


def sealed_combined_ledger_path(root=REPO_ROOT):
    """Return the approved ledger locator. Do not open it."""
    return os.path.join(root, SEALED_COMBINED_LEDGER_RELATIVE)


def _refuse_protected_path(path):
    text = os.fspath(path)
    parts = text.replace("\\", "/").split("/")
    if any(part in REFUSED_ROLES for part in parts):
        raise TrainLeakageRunnerError("role_refused", "a protected data role is not an input or output")
    if parts[-1].lower() in GENERIC_READ_BAN:
        raise TrainLeakageRunnerError("filename_refused", "a protected corpus or ledger filename is refused")


def _read_regular_file(path):
    """Read one regular file. Do not follow a symlink at the final path."""
    _refuse_protected_path(path)
    text = os.fspath(path)
    try:
        descriptor = os.open(text, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise TrainLeakageRunnerError("input_missing", "a required input file is missing") from error
    except OSError as error:
        raise TrainLeakageRunnerError("input_unreadable", "a required input file could not be read") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise TrainLeakageRunnerError("input_unreadable", "a required input is not a regular file")
        chunks = []
        while True:
            blob = os.read(descriptor, 1024 * 1024)
            if blob == b"":
                break
            chunks.append(blob)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _sealed_allowlist(root):
    return frozenset(
        (
            os.path.abspath(sealed_combined_ledger_path(root)),
            os.path.abspath(DEVELOPMENT_TRAIN_CSV),
            os.path.abspath(DEVELOPMENT_TRAIN_TEXT),
        )
    )


def _read_allowlisted(path, allowlist):
    """Open one sealed input. The allowlist is the ledger and the two TRAIN files."""
    text = os.path.abspath(os.fspath(path))
    if text not in allowlist or os.path.basename(text) not in SEALED_BASENAMES:
        raise TrainLeakageRunnerError(
            "sealed_input_refused",
            "the sealed entry opens only the combined ledger and development TRAIN files",
        )
    parts = text.split("/")
    if any(part in ("VALIDATION", "REF", "EVAL") for part in parts):
        raise TrainLeakageRunnerError("sealed_input_refused", "the sealed entry does not open VALIDATION, REF, or EVAL")
    try:
        descriptor = os.open(text, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise TrainLeakageRunnerError("input_missing", "a required sealed input file is missing") from error
    except OSError as error:
        raise TrainLeakageRunnerError("input_unreadable", "a required sealed input file could not be read") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise TrainLeakageRunnerError("input_unreadable", "a required sealed input is not a regular file")
        chunks = []
        while True:
            blob = os.read(descriptor, 1024 * 1024)
            if blob == b"":
                break
            chunks.append(blob)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _git_head(root):
    completed = subprocess.run(
        ["git", "-C", root, "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise TrainLeakageRunnerError("runner_commit_unavailable", "the runner git commit could not be read")
    commit = completed.stdout.strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise TrainLeakageRunnerError("runner_commit_unavailable", "the runner git commit is not a full sha")
    return commit


def _json_document_bytes(value):
    try:
        text = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise TrainLeakageRunnerError("output_serialization_failed", "an output document is not deterministic JSON") from error
    return (text + "\n").encode("utf-8")


def _verify_pinned_digest(blob, frozen, code, label):
    recomputed = _sha256(blob)
    if recomputed != frozen:
        raise TrainLeakageRunnerError(code, label + " does not match the frozen digest")
    return recomputed


def _load_json(blob, code):
    try:
        document = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TrainLeakageRunnerError(code, "a pinned contract is not UTF-8 JSON") from error
    if type(document) is not dict:
        raise TrainLeakageRunnerError(code, "a pinned contract is not an object")
    return document


def _load_m9a_contract(root):
    blob = _read_regular_file(os.path.join(root, M9A_CONTRACT_RELATIVE))
    digest = _verify_pinned_digest(blob, M9A_CONTRACT_SHA256, "m9a_contract_digest_mismatch", "the M9A contract")
    document = _load_json(blob, "m9a_contract_digest_mismatch")
    if document.get("contract_id") != M9A_CONTRACT_ID:
        raise TrainLeakageRunnerError("contract_identity_mismatch", "the M9A contract identity is not the frozen identity")
    return blob, digest, document


def _load_governing_plan(root):
    blob = _read_regular_file(os.path.join(root, GOVERNING_PLAN_RELATIVE))
    digest = _verify_pinned_digest(blob, GOVERNING_PLAN_SHA256, "governing_plan_digest_mismatch", "the governing plan")
    return blob, digest


def _load_frozen_data_contract(root):
    blob = _read_regular_file(os.path.join(root, FROZEN_DATA_CONTRACT_RELATIVE))
    digest = _verify_pinned_digest(
        blob,
        FROZEN_DATA_CONTRACT_SHA256,
        "frozen_data_contract_digest_mismatch",
        "the frozen data contract",
    )
    document = _load_json(blob, "frozen_data_contract_digest_mismatch")
    roles = document.get("roles")
    train = roles.get("TRAIN") if type(roles) is dict else None
    text = roles.get("TRAIN_TEXT") if type(roles) is dict else None
    if (
        document.get("contract_id") != FROZEN_DATA_CONTRACT_ID
        or type(train) is not dict
        or type(text) is not dict
        or train.get("sha256") != TRAIN_CSV_SHA256
        or text.get("sha256") != TRAIN_TEXT_SHA256
        or train.get("counts") != {"identities": 726, "cores": 669, "clusters": 569, "targets": 320}
        or text.get("counts") != {"lines": 669, "unique_cores": 669}
        or train.get("identity_set_hash") != TRAIN_IDENTITY_SET_HASH
        or train.get("cluster_set_hash") != TRAIN_CLUSTER_SET_HASH
        or train.get("partition") != "FT"
        or train.get("ft_split") != "TRAIN"
        or text.get("order") != "first_occurrence_in_frozen_ft_train_csv"
    ):
        raise TrainLeakageRunnerError(
            "frozen_data_contract_identity_mismatch",
            "the frozen data contract does not record the sealed TRAIN identities",
        )
    policy = document.get("sequence_policy")
    if type(policy) is not dict or policy.get("silent_t_to_u") is not False or policy.get("whitespace_or_case_normalisation") is not False:
        raise TrainLeakageRunnerError(
            "frozen_data_contract_identity_mismatch",
            "the frozen data contract does not forbid TRAIN core rewriting",
        )
    return blob, digest, document


def _load_runner_contract(root):
    blob = _read_regular_file(os.path.join(root, RUNNER_CONTRACT_RELATIVE))
    digest = _verify_pinned_digest(blob, RUNNER_CONTRACT_SHA256, "runner_contract_digest_mismatch", "the runner contract")
    document = _load_json(blob, "runner_contract_digest_mismatch")
    formulas = document.get("formulas")
    references = document.get("references")
    train = document.get("train")
    outputs = document.get("outputs")
    boundary = document.get("protected_data_boundary")
    if (
        document.get("contract_id") != RUNNER_CONTRACT_ID
        or document.get("synthetic_execution_is_production_validation") is not False
        or document.get("sealed_production_entry_remains_unexecuted") is not True
        or type(formulas) is not dict
        or formulas.get("modified_by_this_runner") is not False
        or formulas.get("nearest_execution_replaces_frozen_implementation") is not False
        or formulas.get("historical_0_01_guardrail_used_as_decision_threshold") is not False
        or formulas.get("pooled_equal_mixture_rule") != "inclusive_cumulative_weight_exact_v2"
        or formulas.get("edit_similarity_is_sequence_identity") is not False
        or document.get("d1_training_seeds") != [43, 44]
        or type(references) is not dict
        or type(train) is not dict
        or type(outputs) is not dict
        or type(boundary) is not dict
    ):
        raise TrainLeakageRunnerError("runner_contract_identity_mismatch", "the runner contract is not the sealed runner identity")
    csv_role = train.get("csv")
    text_role = train.get("text")
    ledger = references.get("combined_ledger")
    if (
        type(csv_role) is not dict
        or type(text_role) is not dict
        or type(ledger) is not dict
        or csv_role.get("sha256") != TRAIN_CSV_SHA256
        or text_role.get("sha256") != TRAIN_TEXT_SHA256
        or csv_role.get("identity_rows") != PRODUCTION_TRAIN_IDENTITY_ROWS
        or csv_role.get("distinct_sequence_cores") != PRODUCTION_TRAIN_DISTINCT_CORES
        or text_role.get("lines") != PRODUCTION_TRAIN_DISTINCT_CORES
        or ledger.get("sha256") != COMBINED_LEDGER_SHA256
        or references.get("m9a_overlap_leakage_contract", {}).get("sha256") != M9A_CONTRACT_SHA256
        or references.get("governing_plan", {}).get("sha256") != GOVERNING_PLAN_SHA256
        or references.get("frozen_data_contract", {}).get("sha256") != FROZEN_DATA_CONTRACT_SHA256
        or outputs.get("exact_train_leakage_summary") != {"filename": EXACT_SUMMARY_FILENAME, "schema": EXACT_SUMMARY_SCHEMA}
        or outputs.get("nearest_train_distance_summary") != {"filename": NEAREST_SUMMARY_FILENAME, "schema": NEAREST_SUMMARY_SCHEMA}
        or outputs.get("manifest", {}).get("filename") != MANIFEST_FILENAME
        or outputs.get("manifest", {}).get("schema") != MANIFEST_SCHEMA
        or boundary.get("validation_opened") is not False
        or boundary.get("ref_opened") is not False
        or boundary.get("eval_opened") is not False
        or boundary.get("sealed_entry_opens_validation") is not False
        or boundary.get("synthetic_execution_is_production_validation") is not False
    ):
        raise TrainLeakageRunnerError("runner_contract_identity_mismatch", "the runner contract is not the sealed runner identity")
    order = document.get("sealed_source_opening_order")
    if (
        type(order) is not dict
        or set(order) != set(SEALED_SOURCE_OPENING_ORDER)
        or order.get("before_any_sealed_source_is_opened") != SEALED_SOURCE_OPENING_ORDER["before_any_sealed_source_is_opened"]
        or order.get("then_open_and_verify_each_digest_before_the_next_open")
        != SEALED_SOURCE_OPENING_ORDER["then_open_and_verify_each_digest_before_the_next_open"]
        or order.get("parsing_and_metric_computation_after_all_three_digests_match") is not True
        or order.get("in_memory_core_rechecks_digests_schema_counts_provenance_and_output_destination") is not True
        or order.get("source_parsed_before_its_digest_matches") is not False
    ):
        raise TrainLeakageRunnerError(
            "runner_contract_identity_mismatch",
            "the runner contract does not state the sealed source-opening order",
        )
    return blob, digest, document


def _assert_payload_digest(blob, expected, code, label):
    recomputed = _sha256(blob)
    if recomputed != expected:
        raise TrainLeakageRunnerError(code, label + " does not match the expected digest")
    return recomputed


def parse_train_csv(blob):
    """Parse identity-grain TRAIN CSV without rewriting a core or dropping a row."""
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TrainLeakageRunnerError("csv_malformed", "TRAIN CSV is not UTF-8") from error
    if "\x00" in text or text == "":
        raise TrainLeakageRunnerError("csv_malformed", "TRAIN CSV is empty or contains NUL")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames or any(type(name) is not str or name == "" for name in fieldnames):
            raise TrainLeakageRunnerError("csv_malformed", "TRAIN CSV header is missing")
        if len(set(fieldnames)) != len(fieldnames):
            raise TrainLeakageRunnerError("csv_malformed", "TRAIN CSV header repeats a column")
        if any(name not in fieldnames for name in REQUIRED_TRAIN_COLUMNS):
            raise TrainLeakageRunnerError("train_csv_columns_missing", "TRAIN CSV is missing a required column")
        rows = []
        seen_ids = set()
        for row in reader:
            if type(row) is not dict or None in row:
                raise TrainLeakageRunnerError("csv_malformed", "TRAIN CSV row does not match the header")
            for name in REQUIRED_TRAIN_COLUMNS:
                value = row.get(name)
                if type(value) is not str or value == "":
                    raise TrainLeakageRunnerError("train_csv_row_incomplete", "a TRAIN identity row is missing a required value")
            identity = row["scientific_identity_id"]
            if identity in seen_ids:
                raise TrainLeakageRunnerError("duplicate_scientific_identity", "a TRAIN scientific identity id is duplicated")
            seen_ids.add(identity)
            core = row["sequence_core"]
            if CANONICAL_SEQUENCE.fullmatch(core) is None:
                raise TrainLeakageRunnerError("train_core_invalid", "a TRAIN core is not canonical A/C/G/U")
            if row["sequence_core_sha256"] != _sha256(core.encode("utf-8")):
                raise TrainLeakageRunnerError("train_core_hash_mismatch", "a TRAIN core digest does not match the core bytes")
            if row["sequence_length_core"] != str(len(core)):
                raise TrainLeakageRunnerError("train_core_length_mismatch", "a TRAIN core length does not match the core bytes")
            if row["partition"] != "FT" or row["ft_split"] != "TRAIN":
                raise TrainLeakageRunnerError("train_role_mismatch", "a TRAIN row partition or ft_split is not the frozen TRAIN assignment")
            rows.append(row)
    except TrainLeakageRunnerError:
        raise
    except csv.Error as error:
        raise TrainLeakageRunnerError("csv_malformed", "TRAIN CSV is not parseable") from error
    return fieldnames, rows


def first_occurrence_cores(rows):
    """Preserve CSV order. The seen set does not replace the identity-row list."""
    ordered = []
    seen = set()
    for row in rows:
        core = row["sequence_core"]
        if core in seen:
            continue
        seen.add(core)
        ordered.append(core)
    return ordered


def parse_train_text(blob):
    """LF-only, trailing-LF TRAIN text. Do not rewrite or drop a repeated line."""
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TrainLeakageRunnerError("train_text_invalid", "TRAIN text is not UTF-8") from error
    if text == "":
        return []
    if "\r" in text or "\x00" in text or not text.endswith("\n"):
        raise TrainLeakageRunnerError("train_text_invalid", "TRAIN text is not LF-only and trailing-LF terminated")
    lines = text.split("\n")
    lines.pop()
    seen = set()
    for line in lines:
        if line == "" or CANONICAL_SEQUENCE.fullmatch(line) is None:
            raise TrainLeakageRunnerError("train_core_invalid", "a TRAIN text line is not a nonempty canonical core")
        if line in seen:
            raise TrainLeakageRunnerError("duplicate_train_cores", "a supplied TRAIN text core is duplicated")
        seen.add(line)
    return lines


def identity_set_hash(rows):
    """M0 identity fingerprint. This is not the leakage comparison population."""
    payload = "\n".join(
        row["scientific_identity_id"] + "\t" + row["cluster_id"] + "\t" + row["sequence_core_sha256"]
        for row in sorted(rows, key=lambda item: item["scientific_identity_id"])
    )
    return _sha256(payload.encode("utf-8"))


def cluster_set_hash(rows):
    """M0 cluster fingerprint. This is not the leakage comparison population."""
    payload = "\n".join(sorted({row["cluster_id"] for row in rows}))
    return _sha256(payload.encode("utf-8"))


def assert_production_train_profile(rows, ordered, fieldnames, csv_blob, text_blob):
    """Fail closed when parsed TRAIN bytes disagree with the sealed profile."""
    if (
        len(rows) != PRODUCTION_TRAIN_IDENTITY_ROWS
        or len(ordered) != PRODUCTION_TRAIN_DISTINCT_CORES
        or len({row["cluster_id"] for row in rows}) != PRODUCTION_TRAIN_CLUSTERS
        or len({row["canonical_target_name"] for row in rows}) != PRODUCTION_TRAIN_TARGETS
        or identity_set_hash(rows) != TRAIN_IDENTITY_SET_HASH
        or cluster_set_hash(rows) != TRAIN_CLUSTER_SET_HASH
        or len(fieldnames) != PRODUCTION_TRAIN_CSV_COLUMN_COUNT
        or len(csv_blob) != PRODUCTION_TRAIN_CSV_BYTE_COUNT
        or len(text_blob) != PRODUCTION_TRAIN_TEXT_BYTE_COUNT
    ):
        raise TrainLeakageRunnerError(
            "production_train_profile_mismatch",
            "parsed TRAIN bytes do not match the sealed TRAIN profile",
        )


def prepare_train_cores(csv_blob, text_blob, identities, *, enforce_production_identities):
    """Validate TRAIN bytes after their digests have already matched."""
    fieldnames, rows = parse_train_csv(csv_blob)
    lines = parse_train_text(text_blob)
    ordered = first_occurrence_cores(rows)
    if not rows or not ordered or not lines:
        raise TrainLeakageRunnerError("train_cores_empty", "TRAIN cores are empty")
    if lines != ordered:
        raise TrainLeakageRunnerError(
            "train_text_order_mismatch",
            "TRAIN text lines are not the CSV cores in first-occurrence order",
        )
    if len(rows) != identities["train_identity_rows"] or len(lines) != identities["train_distinct_cores"]:
        raise TrainLeakageRunnerError("train_count_mismatch", "TRAIN identity or distinct-core counts do not match the expected identities")
    if enforce_production_identities:
        assert_production_train_profile(rows, ordered, fieldnames, csv_blob, text_blob)
    return {
        "fieldnames": fieldnames,
        "rows": rows,
        "cores": lines,
        "identity_rows": len(rows),
        "distinct_cores": len(lines),
    }


def cached_nearest_train_distance_summaries(rows, train_cores, contract, **controls):
    """Project one frozen nearest-TRAIN scalar per globally distinct sequence.

    The frozen ``nearest_train_distance_summaries`` still builds every count,
    rate, and quantile. This wrapper only removes repeated scalar evaluations.
    """
    original = _leakage.nearest_train
    cache = {}
    bound_cores = None

    def cached(sequence, cores):
        nonlocal bound_cores
        if bound_cores is None:
            bound_cores = cores
        if cores is not bound_cores and list(cores) != list(bound_cores):
            return original(sequence, cores)
        if sequence not in cache:
            cache[sequence] = original(sequence, cores)
        return cache[sequence]

    _leakage.nearest_train = cached
    try:
        return nearest_train_distance_summaries(rows, train_cores, contract, **controls)
    finally:
        _leakage.nearest_train = original


def _call_metric(function, rows, cores, contract):
    try:
        return function(rows, cores, contract)
    except OverlapLeakageError as error:
        raise TrainLeakageRunnerError(error.code, error.detail) from error


def _string_values(value):
    if type(value) is str:
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _string_values(key)
            yield from _string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _string_values(item)


def _banned_strings(ledger_rows, train_rows):
    banned = set()
    for row in ledger_rows:
        for key in ("parsed_sequence", "record_id", "source_sequence_sha256"):
            item = row.get(key)
            if type(item) is str and item != "":
                banned.add(item)
                if key == "parsed_sequence":
                    banned.add(_sha256(item.encode("utf-8")))
    for row in train_rows:
        for key in ("sequence_core", "sequence_core_sha256", "scientific_identity_id", "canonical_target_name", "cluster_id"):
            item = row.get(key)
            if type(item) is str and item != "":
                banned.add(item)
        core = row.get("sequence_core")
        if type(core) is str and core != "":
            banned.add(_sha256(core.encode("utf-8")))
    return banned


def _assert_sequence_free(document, ledger_rows, train_rows):
    banned = _banned_strings(ledger_rows, train_rows)
    values = set(_string_values(document))
    if banned.intersection(values) or _contains_sequence_text(document):
        raise TrainLeakageRunnerError(
            "summary_sequence_leak",
            "an output contains a sequence, sequence hash, attempt identity, neighbour identity, TRAIN identity, or target label",
        )
    rendered = _json_document_bytes(document).decode("utf-8")
    for item in banned:
        if item in rendered:
            raise TrainLeakageRunnerError(
                "summary_sequence_leak",
                "an output contains a sequence, sequence hash, attempt identity, neighbour identity, TRAIN identity, or target label",
            )
    return document


def _common_flags(identities, train, *, enforce_production_identities):
    return {
        "runner_contract_id": RUNNER_CONTRACT_ID,
        "m9a_contract_id": M9A_CONTRACT_ID,
        "synthetic_execution_is_production_validation": False,
        "production_identities_enforced": enforce_production_identities,
        "m9a_complete": False,
        "m9b_complete": False,
        "m9c_complete": False,
        "comparison_population": COMPARISON_POPULATION,
        "train_identity_row_count": train["identity_rows"],
        "train_distinct_core_count": train["distinct_cores"],
        "train_text_line_count": train["distinct_cores"],
        "csv_rows_silently_deduplicated": False,
        "cores_rewritten": False,
        "historical_0_01_guardrail_used_as_decision_threshold": False,
        "b0_role": "external_comparator",
        "b0_pooled_into_b1_b2_d1_aggregate": False,
        "b0_included_in_causal_comparison": False,
        "validation_accessed": False,
        "ref_accessed": False,
        "eval_accessed": False,
        "sequence_strings_emitted": False,
        "sequence_hashes_emitted": False,
        "attempt_identifiers_emitted": False,
        "nearest_neighbour_identities_emitted": False,
        "train_identity_ids_emitted": False,
        "target_labels_emitted": False,
        "expected_ledger_row_counts": identities["ledger_row_counts"],
    }


def _exact_document(computed, identities, train, *, enforce_production_identities):
    document = {"schema": EXACT_SUMMARY_SCHEMA}
    document.update(_common_flags(identities, train, enforce_production_identities=enforce_production_identities))
    document.update(
        {
            "match": computed["match"],
            "partial_match": computed["partial_match"],
            "substring_match": computed["substring_match"],
            "identity_threshold": computed["identity_threshold"],
            "supplied_distinct_train_core_count": computed["supplied_distinct_train_core_count"],
            "by_condition": computed["by_condition"],
            "d1": computed["d1"],
        }
    )
    return document


def _nearest_document(computed, identities, train, *, enforce_production_identities):
    document = {"schema": NEAREST_SUMMARY_SCHEMA}
    document.update(_common_flags(identities, train, enforce_production_identities=enforce_production_identities))
    document.update(
        {
            "supplied_distinct_train_core_count": computed["supplied_distinct_train_core_count"],
            "distance": "global_levenshtein_divided_by_longer_length",
            "scalar_per_globally_distinct_generated_sequence": True,
            "projected_to_rows_conditions_and_seeds": True,
            "replaces_frozen_implementation": False,
            "pooled_equal_mixture_rule_name": "inclusive_cumulative_weight_exact_v2",
            "by_condition": computed["by_condition"],
            "d1": computed["d1"],
        }
    )
    return document


def _file_record(filename, blob):
    return {"filename": filename, "byte_count": len(blob), "sha256": _sha256(blob), "row_count": None}


def _manifest(
    identities,
    m9a_contract,
    pins,
    ledger_blob,
    ledger_sha,
    csv_blob,
    csv_sha,
    text_blob,
    text_sha,
    train,
    actual_counts,
    exact_blob,
    nearest_blob,
    *,
    enforce_production_identities,
    sealed_inputs_opened,
    invocation,
):
    return {
        "schema": MANIFEST_SCHEMA,
        "runner_git_commit": _git_head(REPO_ROOT),
        "runner_contract": {
            "contract_id": RUNNER_CONTRACT_ID,
            "relative_path": RUNNER_CONTRACT_RELATIVE,
            "expected_sha256": identities["runner_contract_sha256"],
            "recomputed_sha256": pins["runner_sha256"],
            "byte_count": len(pins["runner_bytes"]),
        },
        "m9a_contract": {
            "contract_id": M9A_CONTRACT_ID,
            "relative_path": M9A_CONTRACT_RELATIVE,
            "expected_sha256": identities["m9a_contract_sha256"],
            "recomputed_sha256": pins["m9a_sha256"],
            "byte_count": len(pins["m9a_bytes"]),
        },
        "governing_plan": {
            "relative_path": GOVERNING_PLAN_RELATIVE,
            "expected_sha256": identities["governing_plan_sha256"],
            "recomputed_sha256": pins["plan_sha256"],
            "byte_count": len(pins["plan_bytes"]),
        },
        "frozen_data_contract": {
            "contract_id": FROZEN_DATA_CONTRACT_ID,
            "relative_path": FROZEN_DATA_CONTRACT_RELATIVE,
            "expected_sha256": identities["frozen_data_contract_sha256"],
            "recomputed_sha256": pins["frozen_sha256"],
            "byte_count": len(pins["frozen_bytes"]),
        },
        "combined_ledger": {
            "filename": "m9_all_conditions_derived_attempt_ledger.jsonl",
            "supplied_as": "sealed_locator" if sealed_inputs_opened else "in_memory_bytes",
            "relative_path": SEALED_COMBINED_LEDGER_RELATIVE if sealed_inputs_opened else None,
            "expected_sha256": identities["combined_ledger_sha256"],
            "recomputed_sha256": ledger_sha,
            "byte_count": len(ledger_blob),
            "row_count": actual_counts["combined"],
            "row_counts": {name: actual_counts[name] for name in ROW_COUNT_FIELDS},
        },
        "train_csv": {
            "filename": "ft_train.csv",
            "supplied_as": "development_locator" if sealed_inputs_opened else "in_memory_bytes",
            "path": DEVELOPMENT_TRAIN_CSV if sealed_inputs_opened else None,
            "expected_sha256": identities["train_csv_sha256"],
            "recomputed_sha256": csv_sha,
            "byte_count": len(csv_blob),
            "identity_row_count": train["identity_rows"],
            "distinct_core_count": train["distinct_cores"],
            "csv_rows_silently_deduplicated": False,
            "cores_rewritten": False,
        },
        "train_text": {
            "filename": "corpus_final.txt",
            "supplied_as": "development_locator" if sealed_inputs_opened else "in_memory_bytes",
            "path": DEVELOPMENT_TRAIN_TEXT if sealed_inputs_opened else None,
            "expected_sha256": identities["train_text_sha256"],
            "recomputed_sha256": text_sha,
            "byte_count": len(text_blob),
            "line_count": train["distinct_cores"],
            "equals_csv_first_occurrence_order": True,
            "comparison_population": COMPARISON_POPULATION,
        },
        "outputs": [_file_record(EXACT_SUMMARY_FILENAME, exact_blob), _file_record(NEAREST_SUMMARY_FILENAME, nearest_blob)],
        "metric_grain_and_denominator_rules": {
            "exact_train_leakage": m9a_contract["definitions"]["exact_train_leakage"],
            "nearest_train_normalized_edit_distance": m9a_contract["definitions"]["nearest_train_normalized_edit_distance"],
        },
        "nearest_distance_execution": {
            "scalar_per_globally_distinct_generated_sequence": True,
            "projected_to_rows_conditions_and_seeds": True,
            "replaces_frozen_implementation": False,
            "frozen_function": "nearest_train_distance_summaries",
        },
        "serialization": SERIALIZATION,
        "deterministic_serialization": True,
        "access_boundary": {
            "train_files_opened": sealed_inputs_opened,
            "train_bytes_supplied": True,
            "validation_accessed": False,
            "ref_accessed": False,
            "eval_accessed": False,
            "models_accessed": False,
            "checkpoints_accessed": False,
            "structure_tools_accessed": False,
            "aptarank_accessed": False,
            "representation_analysis_accessed": False,
            "sealed_inputs_opened": sealed_inputs_opened,
            "validation_opened": False,
            "production_identities_enforced": enforce_production_identities,
            "rows_repaired": False,
            "rows_reordered": False,
            "rows_deduplicated": False,
            "rows_replenished": False,
            "rows_rewritten": False,
            "train_cores_rewritten": False,
            "csv_rows_silently_deduplicated": False,
            "historical_0_01_guardrail_used_as_decision_threshold": False,
            "b0_pooled_into_b1_b2_d1_aggregate": False,
            "synthetic_execution_is_production_validation": False,
            "sealed_production_entry_remains_unexecuted_by_definition": not sealed_inputs_opened,
        },
        "invocation": invocation,
        "future_output_relative_directory": FUTURE_OUTPUT_RELATIVE,
        "manifest_file": {
            "filename": MANIFEST_FILENAME,
            "schema": MANIFEST_SCHEMA,
            "sha256_embedded": False,
            "statement": "The SHA-256 of this manifest is the digest of these exact file bytes. It is not embedded, because embedding it would change the digest.",
        },
    }


def _refuse_existing_outputs(output_dir):
    if os.path.islink(output_dir):
        raise TrainLeakageRunnerError("output_symlink", "the output directory is a symlink")
    if os.path.lexists(output_dir):
        raise TrainLeakageRunnerError("output_exists", "the output directory already exists")


def validate_published_directory(directory, expected_files):
    """Re-read a finished temporary directory before it is promoted."""
    directory = os.fspath(directory)
    names = sorted(os.listdir(directory))
    if names != sorted(expected_files):
        raise TrainLeakageRunnerError("output_validation_failed", "the temporary output names drifted")
    for filename, record in expected_files.items():
        blob = _read_regular_file(os.path.join(directory, filename))
        if blob != record["blob"] or _sha256(blob) != record["sha256"] or len(blob) != record["byte_count"]:
            raise TrainLeakageRunnerError("output_validation_failed", filename + " did not match the prepared bytes")


def publish_output_directory(output_dir, blobs):
    """Write a temporary sibling directory and promote it by one rename after validation."""
    output_dir = os.path.abspath(output_dir)
    _refuse_existing_outputs(output_dir)
    parent = os.path.dirname(output_dir)
    os.makedirs(parent, exist_ok=True)
    _refuse_existing_outputs(output_dir)
    temp = tempfile.mkdtemp(prefix=TEMP_PREFIX, dir=parent)
    promoted = False
    try:
        expected = {}
        for filename, blob in blobs:
            target = os.path.join(temp, filename)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            try:
                view = blob
                while view:
                    written = os.write(descriptor, view)
                    view = view[written:]
            finally:
                os.close(descriptor)
            expected[filename] = {"blob": blob, "sha256": _sha256(blob), "byte_count": len(blob)}
        validate_published_directory(temp, expected)
        _refuse_existing_outputs(output_dir)
        os.rename(temp, output_dir)
        promoted = True
    finally:
        if not promoted and os.path.isdir(temp):
            shutil.rmtree(temp)
    return output_dir


def run_train_leakage(
    combined_ledger_bytes,
    train_csv_bytes,
    train_text_bytes,
    identities,
    output_dir,
    *,
    enforce_production_identities,
    root=REPO_ROOT,
    invocation=None,
    sealed_inputs_opened=False,
    **controls,
):
    """Validate in-memory bytes and publish sequence-free TRAIN leakage documents.

    ``enforce_production_identities`` is false for miniature synthetic inputs.
    The sealed production entry is the caller that sets it true.
    """
    ledger_blob = _require_bytes(combined_ledger_bytes, "the combined ledger")
    csv_blob = _require_bytes(train_csv_bytes, "the TRAIN CSV")
    text_blob = _require_bytes(train_text_bytes, "the TRAIN text")
    enforce_firewall(controls)
    if type(sealed_inputs_opened) is not bool:
        raise TrainLeakageRunnerError("identity_invalid", "the sealed-input flag is not a boolean")
    _refuse_protected_path(output_dir)
    _refuse_protected_path(root)
    output_dir = os.path.abspath(output_dir)
    checked = validate_identities(identities, enforce_production_identities=enforce_production_identities)
    if invocation is None:
        invocation = {
            "entrypoint": "in_memory_train_leakage",
            "production_identities_enforced": enforce_production_identities,
            "sealed_inputs_opened": sealed_inputs_opened,
        }
    elif type(invocation) is not dict:
        raise TrainLeakageRunnerError("identity_invalid", "the invocation record is not an object")
    ledger_sha = _assert_payload_digest(ledger_blob, checked["combined_ledger_sha256"], "combined_ledger_hash_mismatch", "the combined ledger")
    csv_sha = _assert_payload_digest(csv_blob, checked["train_csv_sha256"], "train_csv_hash_mismatch", "the TRAIN CSV")
    text_sha = _assert_payload_digest(text_blob, checked["train_text_sha256"], "train_text_hash_mismatch", "the TRAIN text")
    m9a_bytes, m9a_sha, m9a_contract = _load_m9a_contract(root)
    plan_bytes, plan_sha = _load_governing_plan(root)
    frozen_bytes, frozen_sha, _frozen_contract = _load_frozen_data_contract(root)
    runner_bytes, runner_sha, _runner_contract = _load_runner_contract(root)
    _refuse_existing_outputs(output_dir)
    train = prepare_train_cores(
        csv_blob,
        text_blob,
        checked,
        enforce_production_identities=enforce_production_identities,
    )
    try:
        ledger_rows = parse_combined_ledger(ledger_blob)
        _grouped, actual_counts = _accept_rows(ledger_rows, checked["ledger_row_counts"])
    except OverlapRunnerError as error:
        raise TrainLeakageRunnerError(error.code, error.detail) from error
    exact = _call_metric(exact_train_leakage, ledger_rows, train["cores"], m9a_contract)
    nearest = _call_metric(cached_nearest_train_distance_summaries, ledger_rows, train["cores"], m9a_contract)
    if exact["supplied_distinct_train_core_count"] != train["distinct_cores"] or nearest["supplied_distinct_train_core_count"] != train["distinct_cores"]:
        raise TrainLeakageRunnerError("train_count_mismatch", "the metric core count does not match the TRAIN text")
    exact_document = _assert_sequence_free(
        _exact_document(exact, checked, train, enforce_production_identities=enforce_production_identities),
        ledger_rows,
        train["rows"],
    )
    nearest_document = _assert_sequence_free(
        _nearest_document(nearest, checked, train, enforce_production_identities=enforce_production_identities),
        ledger_rows,
        train["rows"],
    )
    exact_blob = _json_document_bytes(exact_document)
    nearest_blob = _json_document_bytes(nearest_document)
    manifest = _manifest(
        checked,
        m9a_contract,
        {
            "m9a_bytes": m9a_bytes,
            "m9a_sha256": m9a_sha,
            "plan_bytes": plan_bytes,
            "plan_sha256": plan_sha,
            "frozen_bytes": frozen_bytes,
            "frozen_sha256": frozen_sha,
            "runner_bytes": runner_bytes,
            "runner_sha256": runner_sha,
        },
        ledger_blob,
        ledger_sha,
        csv_blob,
        csv_sha,
        text_blob,
        text_sha,
        train,
        actual_counts,
        exact_blob,
        nearest_blob,
        enforce_production_identities=enforce_production_identities,
        sealed_inputs_opened=sealed_inputs_opened,
        invocation=invocation,
    )
    _assert_sequence_free(manifest, ledger_rows, train["rows"])
    manifest_blob = _json_document_bytes(manifest)
    named = (
        (EXACT_SUMMARY_FILENAME, exact_blob),
        (NEAREST_SUMMARY_FILENAME, nearest_blob),
        (MANIFEST_FILENAME, manifest_blob),
    )
    if tuple(item[0] for item in named) != OUTPUT_FILENAMES:
        raise TrainLeakageRunnerError("output_validation_failed", "the output name order drifted")
    publish_output_directory(output_dir, named)
    return {
        "output_dir": output_dir,
        "exact_summary": exact_document,
        "nearest_summary": nearest_document,
        "manifest": manifest,
        "row_counts": actual_counts,
        "train_identity_rows": train["identity_rows"],
        "train_distinct_cores": train["distinct_cores"],
    }


def _validate_sealed_paths(output_dir, root):
    """Reject a protected root or output path. Do not open a sealed source."""
    _refuse_protected_path(output_dir)
    _refuse_protected_path(root)
    output_text = os.fspath(output_dir)
    root_text = os.fspath(root)
    if output_text == "" or root_text == "":
        raise TrainLeakageRunnerError("identity_invalid", "the output or root path is empty")
    output_dir = os.path.abspath(output_text)
    root = os.path.abspath(root_text)
    if not os.path.isdir(root) or os.path.islink(root):
        raise TrainLeakageRunnerError("input_unreadable", "the runner root is not a real directory")
    return output_dir, root


def preflight_sealed_train_leakage(output_dir, invocation, root=REPO_ROOT):
    """Check sealed invocation, identities, paths, destination, pins, and commit.

    Does not open the combined ledger or either TRAIN file.
    """
    if type(invocation) is not dict or invocation.get("production_identities") is not True:
        raise TrainLeakageRunnerError(
            "production_identity_mismatch",
            "the sealed entry always enforces production identities",
        )
    checked = validate_identities(sealed_identities(), enforce_production_identities=True)
    output_dir, root = _validate_sealed_paths(output_dir, root)
    _refuse_existing_outputs(output_dir)
    _load_m9a_contract(root)
    _load_governing_plan(root)
    _load_frozen_data_contract(root)
    _load_runner_contract(root)
    commit = _git_head(root)
    return {
        "output_dir": output_dir,
        "root": root,
        "identities": checked,
        "runner_git_commit": commit,
        "invocation": invocation,
    }


def open_verified_sealed_sources(source_paths, expected_digests, reader):
    """Open the ledger, then TRAIN CSV, then TRAIN text.

    Each digest is checked before the next source is opened. Nothing is parsed.
    The sealed caller passes only the validated production digests.
    """
    descriptions = {
        "combined_ledger": "the combined ledger",
        "train_csv": "the TRAIN CSV",
        "train_text": "the TRAIN text",
    }
    codes = {
        "combined_ledger": "combined_ledger_hash_mismatch",
        "train_csv": "train_csv_hash_mismatch",
        "train_text": "train_text_hash_mismatch",
    }
    if type(source_paths) is not tuple or len(source_paths) != 3:
        raise TrainLeakageRunnerError("sealed_input_refused", "sealed sources are the ledger, TRAIN CSV, and TRAIN text")
    if type(expected_digests) is not dict or set(expected_digests) != set(SEALED_SOURCE_LABELS):
        raise TrainLeakageRunnerError("identity_invalid", "sealed source digests are incomplete")
    if not callable(reader):
        raise TrainLeakageRunnerError("identity_invalid", "the sealed source reader is not callable")
    blobs = []
    for label, path in zip(SEALED_SOURCE_LABELS, source_paths):
        expected = _require_sha256(expected_digests[label], label)
        blob = _require_bytes(reader(path), descriptions[label])
        _assert_payload_digest(blob, expected, codes[label], descriptions[label])
        blobs.append(blob)
    return tuple(blobs)


def prepare_sealed_train_inputs(output_dir, invocation, root, source_paths, reader):
    """Preflight, then open sealed sources in ledger, TRAIN CSV, TRAIN text order.

    Digests come only from the validated production identity bundle. A mismatch
    stops before the next source is opened. This does not parse any source.
    """
    if type(source_paths) is not tuple or len(source_paths) != 3:
        raise TrainLeakageRunnerError("sealed_input_refused", "sealed sources are the ledger, TRAIN CSV, and TRAIN text")
    if not callable(reader):
        raise TrainLeakageRunnerError("identity_invalid", "the sealed source reader is not callable")
    prepared = preflight_sealed_train_leakage(output_dir, invocation, root)
    identities = prepared["identities"]
    blobs = open_verified_sealed_sources(
        source_paths,
        {
            "combined_ledger": identities["combined_ledger_sha256"],
            "train_csv": identities["train_csv_sha256"],
            "train_text": identities["train_text_sha256"],
        },
        reader,
    )
    return prepared, blobs


def run_sealed_train_leakage(output_dir, invocation, root=REPO_ROOT):
    """Production entry. Remains unexecuted by this implementation.

    Before any sealed source is opened, validates the invocation and the
    production identity bundle, validates the root and output paths, refuses an
    existing output destination, verifies the pinned contracts, and verifies
    that the runner commit is available. It then opens the combined ledger and
    verifies its production digest, opens the development TRAIN CSV and
    verifies its production digest, opens the development TRAIN text and
    verifies its production digest, and only then parses and computes metrics.
    The in-memory core repeats the digest, schema, count, provenance, and
    output-destination checks. It does not open VALIDATION, REF, or EVAL.
    Synthetic tests and this implementation task must not call this function.
    """

    def reader(path):
        return _read_allowlisted(path, _sealed_allowlist(root))

    prepared, (ledger_blob, csv_blob, text_blob) = prepare_sealed_train_inputs(
        output_dir,
        invocation,
        root,
        (
            sealed_combined_ledger_path(root),
            DEVELOPMENT_TRAIN_CSV,
            DEVELOPMENT_TRAIN_TEXT,
        ),
        reader,
    )
    return run_train_leakage(
        ledger_blob,
        csv_blob,
        text_blob,
        sealed_identities(),
        prepared["output_dir"],
        enforce_production_identities=True,
        root=prepared["root"],
        invocation=invocation,
        sealed_inputs_opened=True,
    )


if __name__ == "__main__":
    sys.stderr.write("sealed M9A TRAIN leakage entry remains unexecuted\n")
    raise SystemExit(2)

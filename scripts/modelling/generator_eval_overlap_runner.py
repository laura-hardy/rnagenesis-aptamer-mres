#!/usr/bin/env python3
"""M9A exact cross-condition overlap runner.

The public core accepts in-memory combined-ledger bytes and expected
identities. It verifies the frozen contract file, the governing plan, and the
supplied ledger bytes before it accepts a row. It then calls the frozen pure
overlap implementation and writes a sequence-free summary and manifest.

``run_sealed_cross_condition_overlap`` is the production entry point. It
contains the approved combined-ledger locator and always enforces production
totals. Synthetic tests must not call it. A synthetic run is not production
validation and does not complete M9A.
"""

from __future__ import annotations

import argparse
import hashlib
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
    CONDITION_PAIRS,
    CONDITIONS,
    CONTRACT_ID,
    GOVERNING_PLAN_SHA256,
    OverlapLeakageError,
    cross_condition_overlap,
)
from generator_eval_parser import (
    CANONICAL_SEQUENCE,
    FAILURE_REASONS,
    FORBIDDEN_BASENAMES,
    OUTCOME_EMPTY,
    OUTCOME_NON_ACGU,
    OUTCOME_VALID,
    PARSER_VERSION,
    REFUSED_ROLES,
    enforce_firewall,
    reject_control_string,
)
from generator_eval_production_ledger import PRODUCTION_LEDGER_SCHEMA, PRODUCTION_ROW_FIELDS
from generator_eval_source_adapters import ADAPTER_VERSION

SUMMARY_SCHEMA = "generator-eval-cross-condition-overlap-summary-m9a-r1"
MANIFEST_SCHEMA = "generator-eval-cross-condition-overlap-manifest-m9a-r1"
FROZEN_OVERLAP_CONTRACT_SHA256 = "6aeaa2338776cbe7aceffef63ee4ca7dfd7ed3643aa7d1e400fd54a02d113535"
CONTRACT_RELATIVE_PATH = "config/modelling/generator_eval_overlap_leakage_contract.json"
GOVERNING_PLAN_RELATIVE_PATH = "docs/aptarank_full_mres_thesis_evaluation_plan.md"
SEALED_COMBINED_LEDGER_RELATIVE = (
    "results/fine_tuning/m9_generator_evaluation/m9_all_conditions_derived_attempt_ledger.jsonl"
)
FUTURE_OUTPUT_RELATIVE = "results/fine_tuning/m9_generator_evaluation/m9a_exact_cross_condition_overlap"
SUMMARY_FILENAME = "m9_cross_condition_overlap_summary.json"
MANIFEST_FILENAME = "m9_cross_condition_overlap_manifest.json"
OUTPUT_FILENAMES = (SUMMARY_FILENAME, MANIFEST_FILENAME)
PRODUCTION_ROW_COUNTS = {"B0": 30080, "B1": 30000, "B2": 30000, "D1": 30000, "combined": 120080}
CONDITION_INDEX = {name: index for index, name in enumerate(CONDITIONS)}
IDENTITY_FIELDS = (
    "contract_id",
    "contract_sha256",
    "governing_plan_sha256",
    "combined_ledger_sha256",
    "parser_version",
    "adapter_version",
    "row_counts",
)
ROW_COUNT_FIELDS = CONDITIONS + ("combined",)
B0_NOT_POOLED_STATEMENT = "B0 was not pooled into a B1/B2/D1 aggregate or a causal comparison."
PROTECTED_DATASETS_STATEMENT = "TRAIN, VALIDATION, REF, and EVAL were not accessed."
TEMP_PREFIX = ".m9-overlap-runner."


class OverlapRunnerError(ValueError):
    """The overlap runner refused the request and wrote nothing."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _is_sha256(value):
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _refuse_protected_path(path):
    text = os.fspath(path)
    parts = text.replace("\\", "/").split("/")
    if any(part in REFUSED_ROLES for part in parts):
        raise OverlapRunnerError("role_refused", "a protected data role is not an input or output")
    if parts[-1].lower() in FORBIDDEN_BASENAMES:
        raise OverlapRunnerError("filename_refused", "a protected corpus filename is refused")


def _read_regular_file(path):
    """Read one regular file. Do not follow a symlink at the final path."""
    _refuse_protected_path(path)
    text = os.fspath(path)
    try:
        descriptor = os.open(text, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise OverlapRunnerError("input_missing", "a required input file is missing") from error
    except OSError as error:
        raise OverlapRunnerError("input_unreadable", "a required input file could not be read") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OverlapRunnerError("input_unreadable", "a required input is not a regular file")
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
        raise OverlapRunnerError("runner_commit_unavailable", "the runner git commit could not be read")
    commit = completed.stdout.strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise OverlapRunnerError("runner_commit_unavailable", "the runner git commit is not a full sha")
    return commit


def _json_document_bytes(value):
    try:
        text = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise OverlapRunnerError("output_serialization_failed", "an output document is not deterministic JSON") from error
    return (text + "\n").encode("utf-8")


def _require_bytes(value):
    if type(value) is bytes:
        return value
    if type(value) is str:
        reject_control_string(value)
    raise OverlapRunnerError("ledger_payload_invalid", "the combined ledger must be in-memory bytes")


def _require_sha256(value, label):
    if not _is_sha256(value):
        raise OverlapRunnerError("identity_invalid", label + " is not lowercase sha256")
    return value


def _row_count_identity(value):
    if type(value) is not dict or set(value) != set(ROW_COUNT_FIELDS):
        raise OverlapRunnerError("identity_invalid", "row-count identities are not B0, B1, B2, D1, and combined")
    counts = {}
    for name in ROW_COUNT_FIELDS:
        item = value[name]
        if type(item) is not int or isinstance(item, bool) or item < 0:
            raise OverlapRunnerError("identity_invalid", name + " row count is not a nonnegative integer")
        counts[name] = item
    if counts["combined"] != counts["B0"] + counts["B1"] + counts["B2"] + counts["D1"]:
        raise OverlapRunnerError("identity_invalid", "the combined row-count identity is not the sum of the conditions")
    return counts


def validate_identities(identities, *, enforce_production_counts):
    """Check expected identities. Do not open the combined ledger."""
    if type(identities) is not dict or set(identities) != set(IDENTITY_FIELDS):
        raise OverlapRunnerError("identity_invalid", "expected identities do not match the runner identity set")
    if type(enforce_production_counts) is not bool:
        raise OverlapRunnerError("identity_invalid", "production-count enforcement is not a boolean")
    if identities["contract_id"] != CONTRACT_ID:
        raise OverlapRunnerError("contract_identity_mismatch", "the contract identity is not the frozen identity")
    contract_sha = _require_sha256(identities["contract_sha256"], "the contract digest")
    plan_sha = _require_sha256(identities["governing_plan_sha256"], "the governing-plan digest")
    ledger_sha = _require_sha256(identities["combined_ledger_sha256"], "the combined-ledger digest")
    if identities["parser_version"] != PARSER_VERSION:
        raise OverlapRunnerError("parser_version_mismatch", "the expected parser is not m9-biological-parser-v1")
    if identities["adapter_version"] != ADAPTER_VERSION:
        raise OverlapRunnerError("adapter_version_mismatch", "the expected adapter is not m9-source-adapter-v2")
    counts = _row_count_identity(identities["row_counts"])
    if contract_sha != FROZEN_OVERLAP_CONTRACT_SHA256:
        raise OverlapRunnerError("contract_digest_mismatch", "the expected contract digest is not the frozen digest")
    if plan_sha != GOVERNING_PLAN_SHA256:
        raise OverlapRunnerError("governing_plan_digest_mismatch", "the expected governing-plan digest is not the frozen digest")
    if enforce_production_counts:
        if counts != PRODUCTION_ROW_COUNTS:
            raise OverlapRunnerError("production_count_mismatch", "production totals are not the sealed condition counts")
        if ledger_sha != COMBINED_LEDGER_SHA256:
            raise OverlapRunnerError(
                "production_ledger_digest_mismatch",
                "production enforcement requires the sealed combined-ledger digest",
            )
    return {
        "contract_id": CONTRACT_ID,
        "contract_sha256": contract_sha,
        "governing_plan_sha256": plan_sha,
        "combined_ledger_sha256": ledger_sha,
        "parser_version": PARSER_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "row_counts": counts,
    }


def sealed_identities():
    """Frozen production identities. This does not open the combined ledger."""
    return {
        "contract_id": CONTRACT_ID,
        "contract_sha256": FROZEN_OVERLAP_CONTRACT_SHA256,
        "governing_plan_sha256": GOVERNING_PLAN_SHA256,
        "combined_ledger_sha256": COMBINED_LEDGER_SHA256,
        "parser_version": PARSER_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "row_counts": {name: PRODUCTION_ROW_COUNTS[name] for name in ROW_COUNT_FIELDS},
    }


def sealed_combined_ledger_path(root=REPO_ROOT):
    """Return the approved locator. Do not open it."""
    return os.path.join(root, SEALED_COMBINED_LEDGER_RELATIVE)


def _verify_pinned_digest(blob, expected, frozen, code, label):
    recomputed = _sha256(blob)
    if recomputed != frozen or expected != frozen or recomputed != expected:
        raise OverlapRunnerError(code, label + " does not match the frozen digest")
    return recomputed


def _load_contract(root, expected_sha256):
    path = os.path.join(root, CONTRACT_RELATIVE_PATH)
    blob = _read_regular_file(path)
    recomputed = _verify_pinned_digest(
        blob,
        expected_sha256,
        FROZEN_OVERLAP_CONTRACT_SHA256,
        "contract_digest_mismatch",
        "the contract file",
    )
    try:
        document = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OverlapRunnerError("contract_digest_mismatch", "the contract file is not UTF-8 JSON") from error
    if type(document) is not dict or document.get("contract_id") != CONTRACT_ID:
        raise OverlapRunnerError("contract_identity_mismatch", "the contract identity is not the frozen identity")
    return blob, recomputed, document


def _load_governing_plan(root, expected_sha256):
    path = os.path.join(root, GOVERNING_PLAN_RELATIVE_PATH)
    blob = _read_regular_file(path)
    recomputed = _verify_pinned_digest(
        blob,
        expected_sha256,
        GOVERNING_PLAN_SHA256,
        "governing_plan_digest_mismatch",
        "the governing plan",
    )
    return blob, recomputed


def parse_combined_ledger(blob):
    """UTF-8 JSONL with one object per row. Do not repair or drop a row."""
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as error:
        raise OverlapRunnerError("jsonl_malformed", "the combined ledger is not UTF-8 JSONL") from error
    if "\r" in text or "\x00" in text:
        raise OverlapRunnerError("jsonl_malformed", "the combined ledger is not LF-delimited UTF-8 JSONL")
    if text == "":
        return []
    if not text.endswith("\n"):
        raise OverlapRunnerError("jsonl_malformed", "the combined ledger does not end with one LF per row")
    lines = text.split("\n")
    lines.pop()
    rows = []
    for line in lines:
        if line == "":
            raise OverlapRunnerError("jsonl_malformed", "the combined ledger contains an empty row")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise OverlapRunnerError("jsonl_malformed", "the combined ledger is not one JSON object per row") from error
        if type(value) is not dict:
            raise OverlapRunnerError("jsonl_malformed", "the combined ledger is not one JSON object per row")
        rows.append(value)
    return rows


def _assert_row_schema(row):
    if type(row) is not dict or tuple(row) != PRODUCTION_ROW_FIELDS:
        raise OverlapRunnerError("ledger_schema_invalid", "a production row field set drifted")
    if row["ledger_schema"] != PRODUCTION_LEDGER_SCHEMA:
        raise OverlapRunnerError("ledger_schema_invalid", "a production row schema version drifted")
    if row["parser_version"] != PARSER_VERSION:
        raise OverlapRunnerError("parser_version_mismatch", "a row parser version is not m9-biological-parser-v1")
    if row["adapter_version"] != ADAPTER_VERSION:
        raise OverlapRunnerError("adapter_version_mismatch", "a row adapter version is not m9-source-adapter-v2")
    if row["equal_seed_weighting_applied"] is not False:
        raise OverlapRunnerError("equal_seed_weighting_refused", "equal-seed weighting is not applied")
    condition = row["condition"]
    if type(condition) is not str or condition not in CONDITION_INDEX:
        raise OverlapRunnerError("condition_invalid", "a row condition is outside B0, B1, B2, and D1")
    record_id = row["record_id"]
    if type(record_id) is not str or record_id == "":
        raise OverlapRunnerError("attempt_id_invalid", "a stable attempt identity is missing")
    _assert_sequence_semantics(row)


def _assert_sequence_semantics(row):
    outcome = row["outcome"]
    sequence = row["parsed_sequence"]
    if outcome == OUTCOME_VALID:
        if row["is_valid_canonical"] is not True or row["failure_reason"] is not None:
            raise OverlapRunnerError("ledger_schema_invalid", "a valid row does not match the frozen ledger schema")
        if type(sequence) is not str or CANONICAL_SEQUENCE.fullmatch(sequence) is None:
            raise OverlapRunnerError("valid_sequence_invalid", "a valid row has no canonical parsed sequence")
        if row["parsed_length"] != len(sequence):
            raise OverlapRunnerError("valid_sequence_invalid", "a valid row length does not match its canonical sequence")
        return
    if outcome not in FAILURE_REASONS:
        raise OverlapRunnerError("ledger_schema_invalid", "a row outcome is outside the frozen ledger schema")
    if row["is_valid_canonical"] is not False or row["failure_reason"] != outcome:
        raise OverlapRunnerError("ledger_schema_invalid", "an invalid row does not match the frozen ledger schema")
    if row["valid_sequence_multiplicity"] is not None or row["is_exact_duplicate_within_condition"] is not None:
        raise OverlapRunnerError("invalid_row_semantics", "an invalid row carries duplicate accounting")
    if outcome == OUTCOME_NON_ACGU:
        if type(sequence) is not str or sequence == "" or CANONICAL_SEQUENCE.fullmatch(sequence) is not None:
            raise OverlapRunnerError("invalid_row_semantics", "a parsed non-ACGU row does not retain a non-canonical sequence")
        if row["parsed_length"] != len(sequence):
            raise OverlapRunnerError("invalid_row_semantics", "a parsed non-ACGU length does not match its retained sequence")
        return
    if sequence is not None:
        raise OverlapRunnerError("invalid_row_semantics", "an invalid row retains a sequence")
    if outcome == OUTCOME_EMPTY:
        if row["parsed_length"] != 0:
            raise OverlapRunnerError("invalid_row_semantics", "an empty row length is not zero")
    elif row["parsed_length"] is not None:
        raise OverlapRunnerError("invalid_row_semantics", "an invalid row length is not null")


def _accept_rows(rows, expected_counts):
    """Require source order and independently recomputed duplicate accounting."""
    grouped = {condition: [] for condition in CONDITIONS}
    seen_ids = {condition: set() for condition in CONDITIONS}
    last_index = -1
    open_condition = None
    for row in rows:
        _assert_row_schema(row)
        condition = row["condition"]
        index = CONDITION_INDEX[condition]
        if open_condition is None or condition != open_condition:
            if index <= last_index:
                raise OverlapRunnerError(
                    "condition_order_invalid",
                    "source order is not B0, then B1, then B2, then D1",
                )
            open_condition = condition
            last_index = index
        record_id = row["record_id"]
        if record_id in seen_ids[condition]:
            raise OverlapRunnerError("attempt_id_duplicated", "a stable attempt identity is duplicated within its condition")
        seen_ids[condition].add(record_id)
        grouped[condition].append(row)
    actual = {condition: len(grouped[condition]) for condition in CONDITIONS}
    actual["combined"] = len(rows)
    if actual != expected_counts:
        raise OverlapRunnerError("row_count_mismatch", "condition or combined row counts do not match the expected identities")
    _assert_stored_duplicates(grouped)
    return grouped, actual


def _assert_stored_duplicates(grouped):
    for rows in grouped.values():
        counts = {}
        for row in rows:
            if row["outcome"] != OUTCOME_VALID:
                continue
            sequence = row["parsed_sequence"]
            counts[sequence] = counts.get(sequence, 0) + 1
        for row in rows:
            if row["outcome"] != OUTCOME_VALID:
                continue
            multiplicity = counts[row["parsed_sequence"]]
            stored = row["valid_sequence_multiplicity"]
            flag = row["is_exact_duplicate_within_condition"]
            if type(stored) is not int or stored != multiplicity:
                raise OverlapRunnerError(
                    "multiplicity_mismatch",
                    "stored within-condition multiplicity does not match an independent recomputation",
                )
            if type(flag) is not bool or flag is not (multiplicity > 1):
                raise OverlapRunnerError(
                    "duplicate_flag_mismatch",
                    "stored within-condition duplicate flag does not match an independent recomputation",
                )


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


def _assert_sequence_free(document, rows):
    banned = set()
    for row in rows:
        for key in ("parsed_sequence", "record_id", "source_sequence_sha256"):
            item = row.get(key)
            if type(item) is str and item != "":
                banned.add(item)
    leaked = banned.intersection(_string_values(document))
    if leaked or _contains_sequence_text(document):
        raise OverlapRunnerError(
            "summary_sequence_leak",
            "an output contains a sequence, sequence hash, attempt identity, or overlap member",
        )
    return document


def _summary(contract, rows):
    try:
        computed = cross_condition_overlap(rows, contract)
    except OverlapLeakageError as error:
        raise OverlapRunnerError(error.code, error.detail) from error
    pairs = computed["pairs"]
    observed = [(item["condition_a"], item["condition_b"]) for item in pairs]
    if observed != list(CONDITION_PAIRS):
        raise OverlapRunnerError("condition_pairs_invalid", "the six unordered pairs drifted")
    source = computed["global_sequence_free_accounting"]
    exactly = source["distinct_sequences_in_exactly_n_conditions"]
    if tuple(exactly) != ("1", "2", "3", "4"):
        raise OverlapRunnerError("membership_reconciliation_failed", "exactly-n condition counts drifted")
    patterns = []
    for item in source["membership_patterns"]:
        conditions = list(item["conditions"])
        if not conditions or tuple(condition for condition in CONDITIONS if condition in conditions) != tuple(conditions):
            raise OverlapRunnerError("membership_reconciliation_failed", "a membership pattern is not an ordered nonempty subset")
        patterns.append({"conditions": conditions, "distinct_sequence_count": item["distinct_sequence_count"]})
    union_size = source["global_distinct_valid_sequence_count"]
    pattern_sum = sum(item["distinct_sequence_count"] for item in patterns)
    exactly_sum = exactly["1"] + exactly["2"] + exactly["3"] + exactly["4"]
    if pattern_sum != union_size or exactly_sum != union_size:
        raise OverlapRunnerError("membership_reconciliation_failed", "membership counts do not sum to the global union")
    if computed["b0_role"] != "external_comparator" or computed["b0_pooled_into_b1_b2_d1_aggregate"] is not False:
        raise OverlapRunnerError("b0_label_invalid", "B0 is not labelled as an external comparator")
    if computed["b0_included_in_causal_comparison"] is not False:
        raise OverlapRunnerError("b0_label_invalid", "B0 is not excluded from the causal comparison")
    global_block = {
        "global_distinct_valid_sequence_count": union_size,
        "distinct_sequences_in_exactly_n_conditions": {key: exactly[key] for key in ("1", "2", "3", "4")},
        "membership_patterns": patterns,
        "reconciliation": {
            "membership_pattern_count_sum": pattern_sum,
            "exactly_n_condition_count_sum": exactly_sum,
            "global_distinct_valid_sequence_count": union_size,
            "membership_pattern_counts_sum_to_global_union": True,
            "exactly_n_condition_counts_sum_to_global_union": True,
        },
        "membership_pattern_counts_sum_to_global_union": True,
        "exactly_n_condition_counts_sum_to_global_union": True,
        "sequence_strings_emitted": False,
        "sequence_hashes_emitted": False,
    }
    summary = {
        "schema": SUMMARY_SCHEMA,
        "contract_id": CONTRACT_ID,
        "pairs": pairs,
        "global_sequence_free_accounting": global_block,
        "b0_role": "external_comparator",
        "b0_external_comparator_labels": {
            "B0": "external_comparator",
            "pairs_calculated_identically": True,
            "b0_pooled_into_b1_b2_d1_aggregate": False,
            "b0_included_in_causal_comparison": False,
        },
        "b0_pooled_into_b1_b2_d1_aggregate": False,
        "b0_included_in_causal_comparison": False,
        "b0_not_pooled_statement": B0_NOT_POOLED_STATEMENT,
        "protected_datasets_not_accessed_statement": PROTECTED_DATASETS_STATEMENT,
        "train_accessed": False,
        "validation_accessed": False,
        "ref_accessed": False,
        "eval_accessed": False,
        "sequence_strings_emitted": False,
        "sequence_hashes_emitted": False,
        "attempt_identifiers_emitted": False,
        "overlap_member_lists_emitted": False,
    }
    return _assert_sequence_free(summary, rows)


def _metric_rules(contract):
    definitions = contract["definitions"]
    overlap = definitions["cross_condition_overlap"]
    distinct = definitions["distinct_sequence_sensitivity"]
    global_rules = definitions["global_sequence_free_accounting"]
    return {
        "row_grain": overlap["grain"],
        "row_numerator": overlap["numerator"],
        "row_denominator": overlap["denominator"],
        "row_direction": overlap["direction"],
        "row_rate": overlap["rate"],
        "duplicate_policy": overlap["duplicate_policy"],
        "input_population": overlap["input_population"],
        "condition_pairs": overlap["condition_pairs"],
        "zero_required_denominator_is_null": True,
        "zero_required_denominator_becomes_zero": False,
        "invalid_rows_enter_valid_denominators": False,
        "distinct_grain": distinct["grain"],
        "distinct_numerator": distinct["numerator"],
        "distinct_denominator": distinct["denominator"],
        "distinct_direction": distinct["direction"],
        "shared_sequence_count": distinct["shared_sequence_count"],
        "union_count": distinct["union_count"],
        "jaccard": distinct["jaccard"],
        "zero_denominator": distinct["zero_denominator"],
        "global_distinct_valid_sequence_count": global_rules["global_distinct_valid_sequence_count"],
        "exactly_n_conditions": global_rules["exactly_n_conditions"],
        "membership_patterns": global_rules["membership_patterns"],
        "reconciliation": global_rules["reconciliation"],
        "sequence_strings_emitted": False,
        "sequence_hashes_emitted": False,
    }


def _file_record(filename, blob, row_count):
    return {
        "filename": filename,
        "row_count": row_count,
        "byte_count": len(blob),
        "sha256": _sha256(blob),
    }


def _manifest(
    identities,
    contract,
    contract_bytes,
    contract_sha256,
    plan_bytes,
    plan_sha256,
    ledger_bytes,
    ledger_sha256,
    actual_counts,
    summary_bytes,
    *,
    enforce_production_counts,
    sealed_locator_opened,
    invocation,
):
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "runner_git_commit": _git_head(REPO_ROOT),
        "contract": {
            "contract_id": identities["contract_id"],
            "relative_path": CONTRACT_RELATIVE_PATH,
            "expected_sha256": identities["contract_sha256"],
            "recomputed_sha256": contract_sha256,
            "byte_count": len(contract_bytes),
        },
        "governing_plan": {
            "relative_path": GOVERNING_PLAN_RELATIVE_PATH,
            "expected_sha256": identities["governing_plan_sha256"],
            "recomputed_sha256": plan_sha256,
            "byte_count": len(plan_bytes),
        },
        "combined_ledger": {
            "filename": "m9_all_conditions_derived_attempt_ledger.jsonl",
            "supplied_as": "sealed_locator" if sealed_locator_opened else "in_memory_bytes",
            "relative_path": SEALED_COMBINED_LEDGER_RELATIVE if sealed_locator_opened else None,
            "expected_sha256": identities["combined_ledger_sha256"],
            "recomputed_sha256": ledger_sha256,
            "byte_count": len(ledger_bytes),
            "row_count": actual_counts["combined"],
            "row_counts": {name: actual_counts[name] for name in ROW_COUNT_FIELDS},
        },
        "outputs": [_file_record(SUMMARY_FILENAME, summary_bytes, None)],
        "metric_grain_and_denominator_rules": _metric_rules(contract),
        "serialization": "UTF-8 JSON, trailing LF, indent 2, ensure_ascii, constructed key order, allow_nan false",
        "deterministic_serialization": True,
        "access_boundary": {
            "train_accessed": False,
            "validation_accessed": False,
            "ref_accessed": False,
            "eval_accessed": False,
            "models_accessed": False,
            "checkpoints_accessed": False,
            "structure_tools_accessed": False,
            "aptarank_accessed": False,
            "sealed_combined_ledger_opened": sealed_locator_opened,
            "production_totals_enforced": enforce_production_counts,
            "rows_repaired": False,
            "rows_reordered": False,
            "rows_deduplicated": False,
            "rows_replenished": False,
            "rows_rewritten": False,
            "b0_pooled_into_b1_b2_d1_aggregate": False,
            "synthetic_execution_is_production_validation": False,
            "protected_datasets_not_accessed_statement": PROTECTED_DATASETS_STATEMENT,
        },
        "invocation": invocation,
        "future_output_relative_directory": FUTURE_OUTPUT_RELATIVE,
        "manifest_file": {
            "filename": MANIFEST_FILENAME,
            "sha256_embedded": False,
            "statement": "The SHA-256 of this manifest is the digest of these exact file bytes. It is not embedded, because embedding it would change the digest.",
        },
    }
    return manifest


def _refuse_existing_outputs(output_dir):
    if os.path.islink(output_dir):
        raise OverlapRunnerError("output_symlink", "the output directory is a symlink")
    if os.path.lexists(output_dir):
        raise OverlapRunnerError("output_exists", "the output directory already exists")


def validate_published_directory(directory, expected_files):
    """Re-read a finished temporary directory before it is promoted."""
    directory = os.fspath(directory)
    names = sorted(os.listdir(directory))
    if names != sorted(expected_files):
        raise OverlapRunnerError("output_validation_failed", "the temporary output names drifted")
    for filename, record in expected_files.items():
        blob = _read_regular_file(os.path.join(directory, filename))
        if blob != record["blob"] or _sha256(blob) != record["sha256"] or len(blob) != record["byte_count"]:
            raise OverlapRunnerError("output_validation_failed", filename + " did not match the prepared bytes")


def publish_output_directory(output_dir, blobs):
    """Write a temporary directory and promote it by one rename after validation."""
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


def run_cross_condition_overlap(
    combined_ledger_bytes,
    identities,
    output_dir,
    *,
    enforce_production_counts,
    root=REPO_ROOT,
    invocation=None,
    sealed_locator_opened=False,
    **controls,
):
    """Validate one in-memory combined ledger and publish sequence-free overlap files.

    ``enforce_production_counts`` is false for miniature synthetic ledgers. The
    sealed production entry point is the caller that sets it true.
    """
    payload = _require_bytes(combined_ledger_bytes)
    enforce_firewall(controls)
    if type(sealed_locator_opened) is not bool:
        raise OverlapRunnerError("identity_invalid", "the sealed-locator flag is not a boolean")
    _refuse_protected_path(output_dir)
    _refuse_protected_path(root)
    output_dir = os.path.abspath(output_dir)
    _refuse_existing_outputs(output_dir)
    checked = validate_identities(identities, enforce_production_counts=enforce_production_counts)
    if invocation is None:
        invocation = {
            "entrypoint": "in_memory_combined_ledger",
            "production_totals_enforced": enforce_production_counts,
            "sealed_locator_opened": sealed_locator_opened,
        }
    elif type(invocation) is not dict:
        raise OverlapRunnerError("identity_invalid", "the invocation record is not an object")
    contract_bytes, contract_sha256, contract = _load_contract(root, checked["contract_sha256"])
    plan_bytes, plan_sha256 = _load_governing_plan(root, checked["governing_plan_sha256"])
    ledger_sha256 = _sha256(payload)
    if ledger_sha256 != checked["combined_ledger_sha256"]:
        raise OverlapRunnerError("combined_ledger_hash_mismatch", "the combined-ledger bytes do not match the expected digest")
    rows = parse_combined_ledger(payload)
    _grouped, actual_counts = _accept_rows(rows, checked["row_counts"])
    summary = _summary(contract, rows)
    summary_bytes = _json_document_bytes(summary)
    manifest = _manifest(
        checked,
        contract,
        contract_bytes,
        contract_sha256,
        plan_bytes,
        plan_sha256,
        payload,
        ledger_sha256,
        actual_counts,
        summary_bytes,
        enforce_production_counts=enforce_production_counts,
        sealed_locator_opened=sealed_locator_opened,
        invocation=invocation,
    )
    _assert_sequence_free(manifest, rows)
    manifest_bytes = _json_document_bytes(manifest)
    named = ((SUMMARY_FILENAME, summary_bytes), (MANIFEST_FILENAME, manifest_bytes))
    if tuple(item[0] for item in named) != OUTPUT_FILENAMES:
        raise OverlapRunnerError("output_validation_failed", "the output name order drifted")
    publish_output_directory(output_dir, named)
    return {
        "output_dir": output_dir,
        "summary": summary,
        "manifest": manifest,
        "row_counts": actual_counts,
    }


def run_sealed_cross_condition_overlap(output_dir, invocation, root=REPO_ROOT):
    """Production entry. Opens the approved combined ledger and enforces production totals.

    Synthetic tests and this implementation task must not call this function.
    """
    if type(invocation) is not dict or invocation.get("production_totals") is not True:
        raise OverlapRunnerError("production_count_mismatch", "the sealed entry always enforces production totals")
    path = sealed_combined_ledger_path(root)
    blob = _read_regular_file(path)
    return run_cross_condition_overlap(
        blob,
        sealed_identities(),
        output_dir,
        enforce_production_counts=True,
        root=root,
        invocation=invocation,
        sealed_locator_opened=True,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compute M9A exact cross-condition overlap.")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    command = list(sys.argv) if argv is None else [os.path.basename(__file__), *list(argv)]
    try:
        result = run_sealed_cross_condition_overlap(
            args.output_dir,
            {"argv": command, "production_totals": True},
        )
    except OverlapRunnerError as error:
        sys.stderr.write(error.code + ": " + error.detail + "\n")
        return 1
    sys.stdout.write("output_dir=" + result["output_dir"] + "\n")
    for name in ROW_COUNT_FIELDS:
        sys.stdout.write(name + "_rows=" + str(result["row_counts"][name]) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Deterministic derived-ledger construction for synthetic parser rows.

The first construction does not require a derived hash. A later replay may
supply one and fails closed on mismatch. Serialization is canonical JSONL
with a trailing LF after every row. The accounting projection contains no
sequence strings.

A synthetic ledger is not a production derived ledger and is not production
validation. This module is not the production entry point.
"""

from __future__ import annotations

import hashlib
import json

from generator_eval_parser import (
    FAILURE_REASONS,
    OUTCOME_EMPTY,
    OUTCOME_NON_ACGU,
    OUTCOME_NON_SEQUENCE,
    OUTCOME_UNPARSEABLE,
    OUTCOME_VALID,
    ParserContractError,
    enforce_firewall,
    sha256_text,
)

DERIVED_LEDGER_SCHEMA = "generator-eval-derived-ledger-m9-r1"
DERIVED_FIELDS = (
    "record_id",
    "condition",
    "adapter_version",
    "parser_version",
    "source_artifact_id",
    "source_artifact_sha256",
    "outcome",
    "failure_reason",
    "parsed_sequence",
    "parsed_length",
    "removed_prefix",
    "removed_suffix",
    "line_number",
    "b0_seed",
    "b0_chunk_id",
    "nominal_max_seq_len",
    "requested_biological_length",
    "requested_biological_length_available",
    "master_attempt_index",
    "generation_seed",
    "invocation_index",
    "max_seq_len",
    "technical_block",
    "checkpoint_identity",
    "d1_training_seed",
    "source_raw_file_sha256",
    "source_raw_file_relative_path",
    "attempt_index",
    "sampled_length",
    "empirical_null_seed",
    "source_sequence_sha256",
    "source_valid_acgu_claim",
    "batch_number",
    "within_batch_position",
    "line_index",
    "authorization_id",
    "run_id",
    "condition_id",
    "schema_version",
    "equal_seed_weighting_applied",
)
ACCOUNTING_FIELDS = (
    "raw_source_attempts",
    "valid_canonical_sequences",
    "empty_outputs",
    "unparseable_outputs",
    "non_sequence_outputs",
    "parsed_non_acgu_outputs",
    "successfully_parsed_outputs",
    "unique_valid_sequences",
    "duplicate_excess",
    "failure_reason_counts",
    "d1_observed_counts_by_training_seed",
    "equal_seed_weighting_applied",
    "sequence_strings_emitted",
    "weighting",
)


def blank_derived_row():
    row = {key: None for key in DERIVED_FIELDS}
    row["requested_biological_length_available"] = False
    row["equal_seed_weighting_applied"] = False
    return row


def freeze_derived_row(values):
    """Return one derived row with the frozen key order. Do not drop fields."""
    if not isinstance(values, dict):
        raise ParserContractError("derived_row_schema_invalid", "a derived row is not an object")
    missing = [key for key in DERIVED_FIELDS if key not in values]
    extra = [key for key in values if key not in DERIVED_FIELDS]
    if missing or extra:
        raise ParserContractError(
            "derived_row_schema_invalid",
            "a derived row does not match the frozen field set",
        )
    if values["equal_seed_weighting_applied"] is not False:
        raise ParserContractError("equal_seed_weighting_refused", "equal-seed weighting is not applied")
    return {key: values[key] for key in DERIVED_FIELDS}


def canonical_jsonl_bytes(rows):
    """Canonical JSONL: frozen key order, compact separators, final LF per row."""
    if type(rows) is not list:
        raise ParserContractError("derived_ledger_invalid", "derived rows are not a list")
    chunks = []
    for row in rows:
        frozen = freeze_derived_row(row)
        chunks.append(
            json.dumps(frozen, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
        )
        chunks.append(b"\n")
    return b"".join(chunks)


def derived_ledger_sha256(rows):
    return hashlib.sha256(canonical_jsonl_bytes(rows)).hexdigest()


def construct_derived_ledger(rows, expected_sha256=None, **rejected):
    """Build the ledger. The first call may omit ``expected_sha256``.

    Replay with a hash fails closed on mismatch. This does not renumber,
    replenish, filter, deduplicate, or drop rows. The result is synthetic
    construction, not production validation.
    """
    enforce_firewall(rejected)
    if expected_sha256 is not None and not sha256_text(expected_sha256):
        raise ParserContractError("derived_ledger_sha256_invalid", "the expected derived hash is not lowercase sha256")
    payload = canonical_jsonl_bytes(rows)
    digest = hashlib.sha256(payload).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ParserContractError(
            "derived_ledger_sha256_mismatch",
            "the expected derived-ledger hash does not match the canonical bytes",
        )
    return {
        "schema": DERIVED_LEDGER_SCHEMA,
        "canonical_jsonl": payload,
        "derived_ledger_sha256": digest,
        "row_count": len(rows),
        "rows": [freeze_derived_row(row) for row in rows],
        "expected_sha256_was_required": False,
        "production_execution": False,
        "production_derived_ledger": False,
        "synthetic_execution_is_production_validation": False,
    }


def assert_attempt_identity(source_ids, rows, source_artifact_sha256):
    """Require exactly one derived row per source attempt, in source order."""
    if type(source_ids) is not list or type(rows) is not list:
        raise ParserContractError("attempt_join_invalid", "attempt identity inputs are not lists")
    if not sha256_text(source_artifact_sha256):
        raise ParserContractError("source_artifact_sha256_invalid", "the source artifact hash is not lowercase sha256")
    for record_id in source_ids:
        if type(record_id) is not str or record_id == "":
            raise ParserContractError("record_id_invalid", "a source attempt id is not text")
    derived_ids = []
    for row in rows:
        if not isinstance(row, dict) or type(row.get("record_id")) is not str or row["record_id"] == "":
            raise ParserContractError("record_id_invalid", "a derived row lacks a record id")
        if row.get("source_artifact_sha256") != source_artifact_sha256:
            raise ParserContractError(
                "source_artifact_sha256_mismatch",
                row["record_id"] + " does not carry the source artifact hash",
            )
        derived_ids.append(row["record_id"])
    counts = {}
    for record_id in derived_ids:
        counts[record_id] = counts.get(record_id, 0) + 1
    for record_id, count in counts.items():
        if count > 1:
            raise ParserContractError("attempt_id_duplicated", record_id + " is duplicated in the derived ledger")
    source_set = set(source_ids)
    derived_set = set(derived_ids)
    for record_id in source_ids:
        if record_id not in derived_set:
            raise ParserContractError("attempt_id_missing", record_id + " has no derived row")
    for record_id in derived_ids:
        if record_id not in source_set:
            raise ParserContractError("attempt_id_extra", record_id + " is not a source attempt")
    if len(rows) != len(source_ids) or derived_ids != source_ids:
        raise ParserContractError("attempt_id_reordered", "derived attempt ids were renumbered or reordered")
    return True


def _contains_sequence_text(value):
    if type(value) is str:
        return value != "" and all(character in "ACGU" for character in value)
    if isinstance(value, dict):
        return any(_contains_sequence_text(item) for item in value.values()) or any(
            _contains_sequence_text(item) for item in value.keys()
        )
    if isinstance(value, list):
        return any(_contains_sequence_text(item) for item in value)
    return False


def sequence_free_accounting(rows):
    """Count outcomes without emitting sequence strings or applying seed weights.

    Successfully parsed outputs are the rows that retain a parsed body:
    valid canonical sequences and parsed non-ACGU bodies. D1 seed counts are
    observed row counts.
    """
    enforce_firewall({})
    if type(rows) is not list:
        raise ParserContractError("accounting_invalid", "accounting input is not a list")
    valid_seen = set()
    valid_count = 0
    empty_count = 0
    unparseable_count = 0
    non_sequence_count = 0
    non_acgu_count = 0
    failure_counts = {reason: 0 for reason in FAILURE_REASONS}
    d1_counts = {}
    for row in rows:
        frozen = freeze_derived_row(row)
        outcome = frozen["outcome"]
        if outcome == OUTCOME_VALID:
            if type(frozen["parsed_sequence"]) is not str:
                raise ParserContractError("accounting_invalid", "a valid row has no parsed sequence")
            valid_count += 1
            valid_seen.add(frozen["parsed_sequence"])
        elif outcome == OUTCOME_EMPTY:
            empty_count += 1
        elif outcome == OUTCOME_UNPARSEABLE:
            unparseable_count += 1
        elif outcome == OUTCOME_NON_SEQUENCE:
            non_sequence_count += 1
        elif outcome == OUTCOME_NON_ACGU:
            non_acgu_count += 1
        else:
            raise ParserContractError("accounting_invalid", "a derived row has an unknown outcome")
        reason = frozen["failure_reason"]
        if outcome == OUTCOME_VALID:
            if reason is not None:
                raise ParserContractError("accounting_invalid", "a valid row has a failure reason")
        elif reason != outcome:
            raise ParserContractError("accounting_invalid", "a failure reason does not match its outcome")
        else:
            failure_counts[reason] += 1
        if frozen["condition"] == "D1":
            seed = frozen["d1_training_seed"]
            if type(seed) is not int:
                raise ParserContractError("d1_training_seed_invalid", "a D1 row has no integer training seed")
            key = str(seed)
            d1_counts[key] = d1_counts.get(key, 0) + 1
        elif frozen["d1_training_seed"] is not None:
            raise ParserContractError("d1_training_seed_invalid", "a non-D1 row carries a D1 training seed")
    unique = len(valid_seen)
    del valid_seen
    ordered_d1 = None
    if d1_counts:
        ordered_d1 = {key: d1_counts[key] for key in sorted(d1_counts, key=int)}
    projection = {
        "raw_source_attempts": len(rows),
        "valid_canonical_sequences": valid_count,
        "empty_outputs": empty_count,
        "unparseable_outputs": unparseable_count,
        "non_sequence_outputs": non_sequence_count,
        "parsed_non_acgu_outputs": non_acgu_count,
        "successfully_parsed_outputs": valid_count + non_acgu_count,
        "unique_valid_sequences": unique,
        "duplicate_excess": valid_count - unique,
        "failure_reason_counts": failure_counts,
        "d1_observed_counts_by_training_seed": ordered_d1,
        "equal_seed_weighting_applied": False,
        "sequence_strings_emitted": False,
        "weighting": "observed_counts_only",
    }
    if tuple(projection) != ACCOUNTING_FIELDS:
        raise ParserContractError("accounting_invalid", "the accounting projection fields drifted")
    if _contains_sequence_text(projection):
        raise ParserContractError("accounting_sequence_leak", "the accounting projection contains sequence text")
    counted = (
        valid_count + empty_count + unparseable_count + non_sequence_count + non_acgu_count
    )
    if counted != len(rows):
        raise ParserContractError("accounting_invalid", "outcome counts do not match the source attempt count")
    return projection

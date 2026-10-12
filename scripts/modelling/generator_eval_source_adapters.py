#!/usr/bin/env python3
"""In-memory source adapters for the frozen four-condition parser.

Public functions accept in-memory source bytes. They do not accept filesystem
paths and they do not open files. Decoded objects cannot verify the original
source bytes, so they are refused and are not a production entry point.

Every bytes adapter computes SHA-256 from the exact supplied bytes, compares
that digest with the caller-supplied expected hash before trusted parsing, and
fails closed on a malformed hash or a mismatch. Derived rows carry the
recomputed digest, not the caller-supplied string.

Source-container integrity and biological-output classification are different
layers. A hash mismatch, a JSONL structural failure, a missing required
identity, a duplicate source identity, or corruption that prevents reliable
attempt identity fails the source. The adapter does not invent a B1 or D1
record id, or a B2 attempt index, when it cannot be recovered. Malformed JSON
that prevents that recovery fails the source rather than emitting a fabricated
row.

``unparseable_output`` is used only when a unique source attempt is already
established and the attempt payload itself cannot be decoded. B0 establishes
seed and line identity from byte-level LF boundaries and explicit chunk
metadata before decoding, so one undecodable B0 record may become one
``unparseable_output`` row. A schema-valid B1, D1, or B2 record may carry an
accounted outcome for a null or otherwise uninterpretable payload only when
its identity and required provenance remain valid.

B0, B1, B2, and D1 share one biological parser after source adaptation.
``source_raw_file_relative_path`` is preserved M8 provenance. Adapter v2
checks it with the tracked writer form and does not treat its ``/``
separators as a filesystem argument. Other token fields stay slash-free.
Synthetic adaptation is not production validation. Production parsing is the
production-ledger entry point, not this adapter.
"""

from __future__ import annotations

import hashlib
import json
import re

from generator_eval_derived_ledger import blank_derived_row, freeze_derived_row
from generator_eval_parser import (
    OUTCOME_NON_SEQUENCE,
    OUTCOME_UNPARSEABLE,
    PARSER_VERSION,
    ParserContractError,
    enforce_firewall,
    parse_biological_text,
    reject_control_string,
    reject_primary_payload,
    sha256_text,
    split_raw_record_bytes,
)

ADAPTER_VERSION = "m9-source-adapter-v2"
# Writer form from scripts/modelling/m8_generation.py relative_raw_path:
# raw/invocation_{index:04d}/seqs_wo_guidance_top_p=0.95_2_{line_count}_m8_i{index:04d}_seed{seed}_len{length}.txt
_M8_RELATIVE_RAW_PATH = re.compile(
    r"raw/invocation_(?P<folder>[0-9]+)/"
    r"seqs_wo_guidance_top_p=0\.95_2_(?P<line_count>[0-9]+)"
    r"_m8_i(?P<file>[0-9]+)"
    r"_seed(?P<seed>[0-9]+)"
    r"_len(?P<length>[0-9]+)\.txt"
)
M8_SCHEMA_VERSION = "m8-raw-attempt-1"
B0_NOMINAL_MAX_SEQ_LEN = 37
CONDITION_LABELS = {
    "B0": "B0_released_aptamer_rnagenesis",
    "B1": "B1_generic_released_rnagenesis",
    "B2": "B2_train_matched_empirical_null",
    "D1": "D1_mres_curated_aptamer_diffusion_adapted",
}
M8_RECORD_FIELDS = (
    "authorization_id",
    "batch_number",
    "checkpoint_identity",
    "condition_id",
    "d1_training_seed",
    "generation_seed",
    "invocation_index",
    "line_index",
    "master_attempt_index",
    "max_seq_len",
    "raw_decoded_text",
    "record_id",
    "requested_biological_length",
    "run_id",
    "schema_version",
    "source_raw_file_relative_path",
    "source_raw_file_sha256",
    "technical_block",
    "within_batch_position",
)
B2_RECORD_FIELDS = (
    "attempt_index",
    "seed",
    "sampled_length",
    "sequence",
    "valid_acgu",
    "sequence_sha256",
)
B0_CHUNK_FIELDS = (
    "chunk_id",
    "nominal_max_seq_len",
    "seed",
    "source_artifact_id",
    "source_artifact_sha256",
)


def _exact_keys(value, expected):
    return isinstance(value, dict) and set(value) == set(expected)


def _nonnegative_int(value):
    return type(value) is int and value >= 0


def _token(value):
    if type(value) is not str or value == "":
        return False
    reject_control_string(value)
    return True


def _canonical_decimal(text):
    """True when text is the default decimal formatting of a nonnegative integer."""
    if text == "0":
        return True
    return text.isdigit() and text[0] != "0"


def _canonical_invocation_index(text):
    """True when text is ``{:04d}`` of a nonnegative invocation index."""
    if not text.isdigit():
        return False
    return "%04d" % int(text) == text


def validate_m8_source_raw_relative_path(value):
    """Accept one preserved M8 ``source_raw_file_relative_path`` lexically.

    The tracked writer emits
    ``raw/invocation_{index:04d}/seqs_wo_guidance_top_p=0.95_2_{line_count}_m8_i{index:04d}_seed{seed}_len{length}.txt``.
    The folder index and the filename index are the same value. This is
    provenance data, not a filesystem argument. The accepted string is
    returned unchanged. This function does not resolve, join, open, stat,
    or otherwise dereference it, and it does not choose an input from it.
    """
    if type(value) is not str:
        raise ParserContractError(
            "m8_relative_path_invalid",
            "source_raw_file_relative_path is not a string",
        )
    if value == "":
        raise ParserContractError(
            "m8_relative_path_invalid",
            "source_raw_file_relative_path is empty",
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ParserContractError(
            "m8_relative_path_invalid",
            "source_raw_file_relative_path contains a control character",
        )
    if "\\" in value or value.startswith("/") or value.startswith("~") or (len(value) >= 2 and value[1] == ":"):
        raise ParserContractError(
            "m8_relative_path_invalid",
            "source_raw_file_relative_path is not a POSIX-relative M8 path",
        )
    parts = value.split("/")
    if any(part == "" for part in parts):
        raise ParserContractError(
            "m8_relative_path_invalid",
            "source_raw_file_relative_path has an empty component",
        )
    if any(part in (".", "..") for part in parts):
        raise ParserContractError(
            "m8_relative_path_invalid",
            "source_raw_file_relative_path has a dot component",
        )
    if parts[0] != "raw":
        raise ParserContractError(
            "m8_relative_path_invalid",
            "source_raw_file_relative_path does not begin with raw/",
        )
    match = _M8_RELATIVE_RAW_PATH.fullmatch(value)
    if match is None:
        raise ParserContractError(
            "m8_relative_path_invalid",
            "source_raw_file_relative_path does not match the M8 writer form",
        )
    folder_index = match.group("folder")
    file_index = match.group("file")
    if folder_index != file_index or not _canonical_invocation_index(folder_index):
        raise ParserContractError(
            "m8_relative_path_invalid",
            "the M8 invocation index is not the writer form",
        )
    for group_name in ("line_count", "seed", "length"):
        if not _canonical_decimal(match.group(group_name)):
            raise ParserContractError(
                "m8_relative_path_invalid",
                "an M8 path integer is not canonical decimal",
            )
    return value


def _base_row(condition, source_artifact_id, source_artifact_sha256):
    row = blank_derived_row()
    row["condition"] = condition
    row["condition_id"] = CONDITION_LABELS[condition]
    row["adapter_version"] = ADAPTER_VERSION
    row["parser_version"] = PARSER_VERSION
    row["source_artifact_id"] = source_artifact_id
    row["source_artifact_sha256"] = source_artifact_sha256
    row["equal_seed_weighting_applied"] = False
    row["requested_biological_length_available"] = False
    return row


def _write_parse(row, parsed):
    row["outcome"] = parsed["outcome"]
    row["failure_reason"] = parsed["failure_reason"]
    row["parsed_sequence"] = parsed["parsed_sequence"]
    row["parsed_length"] = parsed["parsed_length"]
    row["removed_prefix"] = parsed["removed_prefix"]
    row["removed_suffix"] = parsed["removed_suffix"]
    return row


def _unparsed_row(row, outcome):
    parsed = parse_biological_text(None if outcome == OUTCOME_NON_SEQUENCE else b"\xff")
    if outcome == OUTCOME_UNPARSEABLE and parsed["outcome"] != OUTCOME_UNPARSEABLE:
        raise ParserContractError("parser_reconstruction_failed", "undecodable bytes were not unparseable")
    if outcome == OUTCOME_NON_SEQUENCE:
        parsed = parse_biological_text(None)
    _write_parse(row, parsed)
    return row


def _verified_source_digest(payload, expected):
    """Hash the exact supplied bytes and return that recomputed digest.

    Syntax and equality are checked before the caller parses the payload.
    The return value is ``hashlib``'s hex digest, not the caller-supplied object.
    """
    if type(payload) is list or isinstance(payload, dict):
        raise ParserContractError(
            "decoded_source_refused",
            "decoded objects cannot verify original source bytes and are not a production entry point",
        )
    if not isinstance(payload, (bytes, bytearray)):
        raise ParserContractError("payload_type_invalid", "the adapter accepts in-memory source bytes")
    if not sha256_text(expected):
        raise ParserContractError(
            "source_artifact_sha256_invalid",
            "the source artifact hash is not lowercase sha256",
        )
    digest = hashlib.sha256(bytes(payload)).hexdigest()
    if digest != expected:
        raise ParserContractError(
            "source_artifact_sha256_mismatch",
            "source_artifact_sha256 does not match the in-memory bytes",
        )
    return digest


def _jsonl_objects(payload):
    """Decode JSONL only after the source digest has been verified.

    A line that is not valid UTF-8, is not one JSON value, or is not an object
    fails the source. Identity is not recovered from a broken record.
    """
    values = []
    for blob in split_raw_record_bytes(payload):
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ParserContractError(
                "source_container_invalid",
                "a JSONL record is not valid UTF-8, so its attempt identity cannot be recovered",
            ) from error
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise ParserContractError(
                "source_container_invalid",
                "malformed JSON prevents recovery of the required attempt identity",
            ) from error
        if not isinstance(value, dict):
            raise ParserContractError(
                "source_container_invalid",
                "a JSONL record is not an object, so its attempt identity cannot be recovered",
            )
        values.append(value)
    return values


def _finish(rows, attempt_count):
    if len(rows) != attempt_count:
        raise ParserContractError("mutation_refused", "adaptation changed the attempt count")
    return [freeze_derived_row(row) for row in rows]


def adapt_b0(raw_bytes, chunk_metadata, **rejected):
    """Adapt one synthetic B0 chunk. Requested biological length stays unavailable."""
    enforce_firewall(rejected, control_values=_b0_control_values(chunk_metadata))
    reject_primary_payload(raw_bytes)
    if type(raw_bytes) is list or isinstance(raw_bytes, dict):
        raise ParserContractError(
            "decoded_source_refused",
            "decoded objects cannot verify original source bytes and are not a production entry point",
        )
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise ParserContractError("payload_type_invalid", "B0 adaptation accepts in-memory bytes")
    if not isinstance(chunk_metadata, dict):
        raise ParserContractError("b0_chunk_metadata_invalid", "B0 chunk metadata is not a decoded object")
    if "source_artifact_sha256" in chunk_metadata:
        source_hash = _verified_source_digest(raw_bytes, chunk_metadata["source_artifact_sha256"])
    else:
        source_hash = None
    if "requested_biological_length" in chunk_metadata or "requested_length" in chunk_metadata:
        raise ParserContractError(
            "b0_requested_length_unavailable",
            "nominal max_seq_len is not a biological requested length",
        )
    if not _exact_keys(chunk_metadata, B0_CHUNK_FIELDS):
        raise ParserContractError("b0_chunk_metadata_invalid", "B0 chunk metadata fields are not the frozen set")
    seed = chunk_metadata["seed"]
    if not _nonnegative_int(seed):
        raise ParserContractError("b0_seed_invalid", "the synthetic B0 seed is not a nonnegative integer")
    if type(chunk_metadata["nominal_max_seq_len"]) is not int or chunk_metadata["nominal_max_seq_len"] != B0_NOMINAL_MAX_SEQ_LEN:
        raise ParserContractError(
            "b0_nominal_max_seq_len_invalid",
            "nominal max_seq_len must stay 37 and is not a requested biological length",
        )
    if not _token(chunk_metadata["chunk_id"]) or not _token(chunk_metadata["source_artifact_id"]):
        raise ParserContractError("b0_chunk_metadata_invalid", "B0 chunk identity is not a logical token")
    records = split_raw_record_bytes(raw_bytes)
    rows = []
    for line_number, blob in enumerate(records, start=1):
        row = _base_row("B0", chunk_metadata["source_artifact_id"], source_hash)
        row["record_id"] = "b0:seed:%d:line:%d" % (seed, line_number)
        row["line_number"] = line_number
        row["b0_seed"] = seed
        row["b0_chunk_id"] = chunk_metadata["chunk_id"]
        row["nominal_max_seq_len"] = B0_NOMINAL_MAX_SEQ_LEN
        row["requested_biological_length"] = None
        row["requested_biological_length_available"] = False
        row["max_seq_len"] = None
        row["d1_training_seed"] = None
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            _unparsed_row(row, OUTCOME_UNPARSEABLE)
        else:
            _write_parse(row, parse_biological_text(text))
        rows.append(row)
    return _finish(rows, len(records))


def _b0_control_values(chunk_metadata):
    if not isinstance(chunk_metadata, dict):
        return ()
    values = []
    for key in ("chunk_id", "source_artifact_id"):
        if key in chunk_metadata:
            values.append(chunk_metadata[key])
    return values


def _copy_m8_provenance(row, record):
    row["record_id"] = record["record_id"]
    row["authorization_id"] = record["authorization_id"]
    row["batch_number"] = record["batch_number"]
    row["checkpoint_identity"] = record["checkpoint_identity"]
    row["condition_id"] = record["condition_id"]
    row["d1_training_seed"] = record["d1_training_seed"]
    row["generation_seed"] = record["generation_seed"]
    row["invocation_index"] = record["invocation_index"]
    row["line_index"] = record["line_index"]
    row["master_attempt_index"] = record["master_attempt_index"]
    row["max_seq_len"] = record["max_seq_len"]
    row["requested_biological_length"] = record["requested_biological_length"]
    row["requested_biological_length_available"] = True
    row["run_id"] = record["run_id"]
    row["schema_version"] = record["schema_version"]
    row["source_raw_file_relative_path"] = record["source_raw_file_relative_path"]
    row["source_raw_file_sha256"] = record["source_raw_file_sha256"]
    row["technical_block"] = record["technical_block"]
    row["within_batch_position"] = record["within_batch_position"]
    return row


def _m8_provenance_valid(record, condition):
    if not _exact_keys(record, M8_RECORD_FIELDS):
        return False
    if record["condition_id"] != CONDITION_LABELS[condition]:
        return False
    if condition == "B1" and record["d1_training_seed"] is not None:
        raise ParserContractError("d1_training_seed_invalid", "B1 requires a null d1_training_seed")
    if condition == "D1" and not _nonnegative_int(record["d1_training_seed"]):
        raise ParserContractError("d1_training_seed_invalid", "D1 requires an integer d1_training_seed")
    return (
        _token(record["authorization_id"])
        and _nonnegative_int(record["batch_number"])
        and _token(record["checkpoint_identity"])
        and _nonnegative_int(record["generation_seed"])
        and _nonnegative_int(record["invocation_index"])
        and _nonnegative_int(record["line_index"])
        and _nonnegative_int(record["master_attempt_index"])
        and type(record["max_seq_len"]) is int
        and record["max_seq_len"] >= 1
        and _token(record["record_id"])
        and type(record["requested_biological_length"]) is int
        and record["requested_biological_length"] >= 1
        and _token(record["run_id"])
        and record["schema_version"] == M8_SCHEMA_VERSION
        and validate_m8_source_raw_relative_path(record["source_raw_file_relative_path"]) == record["source_raw_file_relative_path"]
        and sha256_text(record["source_raw_file_sha256"])
        and record["technical_block"] in ("A", "B")
        and _nonnegative_int(record["within_batch_position"])
    )


def _account_m8(value, condition, source_artifact_id, source_hash, seen):
    """Account one schema-bearing M8 object, or fail the source."""
    if not isinstance(value, dict) or not _token(value.get("record_id")):
        raise ParserContractError(
            "source_attempt_identity_unrecoverable",
            "the B1/D1 record_id cannot be recovered",
        )
    record_id = value["record_id"]
    if record_id in seen:
        raise ParserContractError(
            "source_attempt_identity_duplicated",
            record_id + " is duplicated in the source",
        )
    seen.add(record_id)
    if not _m8_provenance_valid(value, condition):
        raise ParserContractError(
            "source_provenance_invalid",
            "required B1/D1 provenance is not valid",
        )
    row = _base_row(condition, source_artifact_id, source_hash)
    _copy_m8_provenance(row, value)
    sequence = value["raw_decoded_text"]
    if type(sequence) is not str:
        _unparsed_row(row, OUTCOME_NON_SEQUENCE)
        return row
    _write_parse(row, parse_biological_text(sequence))
    return row


def _adapt_m8(payload, condition, source_artifact_id, source_artifact_sha256, rejected):
    enforce_firewall(rejected, control_values=(source_artifact_id,))
    if not _token(source_artifact_id):
        raise ParserContractError("source_artifact_id_invalid", "the source artifact id is not a logical token")
    source_hash = _verified_source_digest(payload, source_artifact_sha256)
    values = _jsonl_objects(payload)
    rows = []
    seen = set()
    for value in values:
        rows.append(_account_m8(value, condition, source_artifact_id, source_hash, seen))
    return _finish(rows, len(values))


def adapt_b1(payload, *, source_artifact_id, source_artifact_sha256, **rejected):
    """Adapt synthetic M8 JSONL bytes for B1. ``d1_training_seed`` must be null."""
    return _adapt_m8(payload, "B1", source_artifact_id, source_artifact_sha256, rejected)


def adapt_d1(payload, *, source_artifact_id, source_artifact_sha256, **rejected):
    """Adapt synthetic M8 JSONL bytes for D1. ``d1_training_seed`` must be an integer.

    Seed counts stay on the rows as observed values. This adapter does not
    apply equal-seed weighting.
    """
    return _adapt_m8(payload, "D1", source_artifact_id, source_artifact_sha256, rejected)


def _b2_index(record):
    if not isinstance(record, dict):
        return None
    index = record.get("attempt_index")
    if type(index) is int and 0 <= index <= 99999:
        return index
    return None


def _b2_provenance_valid(record):
    if not _exact_keys(record, B2_RECORD_FIELDS):
        return False
    return (
        _b2_index(record) is not None
        and _nonnegative_int(record["seed"])
        and _nonnegative_int(record["sampled_length"])
        and type(record["valid_acgu"]) is bool
        and sha256_text(record["sequence_sha256"])
    )


def _account_b2(value, source_artifact_id, source_hash, seen):
    """Account one schema-bearing B2 object, or fail the source."""
    if not isinstance(value, dict) or _b2_index(value) is None:
        raise ParserContractError(
            "source_attempt_identity_unrecoverable",
            "the B2 attempt index cannot be recovered",
        )
    index = value["attempt_index"]
    if index in seen:
        raise ParserContractError(
            "source_attempt_identity_duplicated",
            "B2 attempt index %d is duplicated in the source" % index,
        )
    seen.add(index)
    if not _b2_provenance_valid(value):
        raise ParserContractError(
            "source_provenance_invalid",
            "required B2 provenance is not valid",
        )
    row = _base_row("B2", source_artifact_id, source_hash)
    row["d1_training_seed"] = None
    row["record_id"] = "b2:attempt:%05d" % index
    row["attempt_index"] = index
    row["empirical_null_seed"] = value["seed"]
    row["sampled_length"] = value["sampled_length"]
    row["source_sequence_sha256"] = value["sequence_sha256"]
    row["source_valid_acgu_claim"] = value["valid_acgu"]
    sequence = value["sequence"]
    if type(sequence) is not str:
        _unparsed_row(row, OUTCOME_NON_SEQUENCE)
        return row
    _write_parse(row, parse_biological_text(sequence))
    return row


def adapt_b2(payload, *, source_artifact_id, source_artifact_sha256, **rejected):
    """Adapt synthetic B2 JSONL bytes. ``valid_acgu`` is not the validity authority.

    The record ``seed`` is stored as the empirical-null seed. It is not a
    training seed, and seed 42 is not a general parser rule.
    """
    enforce_firewall(rejected, control_values=(source_artifact_id,))
    if not _token(source_artifact_id):
        raise ParserContractError("source_artifact_id_invalid", "the source artifact id is not a logical token")
    source_hash = _verified_source_digest(payload, source_artifact_sha256)
    values = _jsonl_objects(payload)
    rows = []
    seen = set()
    for value in values:
        rows.append(_account_b2(value, source_artifact_id, source_hash, seen))
    return _finish(rows, len(values))

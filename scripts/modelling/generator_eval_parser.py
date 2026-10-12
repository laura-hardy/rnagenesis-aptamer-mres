#!/usr/bin/env python3
"""Frozen four-condition biological parser.

On valid UTF-8 records, character-level splitting, boundary-marker removal,
and validity classification reproduce the pinned RNAGenesis cleaner
``scripts/audit_generation_output.py`` at blob
``3480af2dd758f4824655b3f7c8a5276214a61682``. This module does not claim
byte-for-byte behavioural identity with that cleaner for whole-file UTF-8
failure. A uniquely identifiable undecodable record may be represented as
``unparseable_output`` by the source-adapter layer. That extension does not
change boundary removal or biological validity, and it is not permission to
continue after a source-hash failure or loss of attempt identity.

This module accepts in-memory values only. It does not open files, and a
synthetic call is not production validation. Production execution and
production derived-ledger creation remain unauthorised. This branch has not
run production parsing.
"""

from __future__ import annotations

import re

STATUS = "M9_PARSER_IMPLEMENTED_SYNTHETIC_ONLY_NOT_AUTHORISED_FOR_PRODUCTION"
PARSER_CONTRACT_SCHEMA = "generator-eval-parser-contract-m9-r1"
SOURCE_MANIFEST_SCHEMA = "generator-eval-source-manifest-m9-r1"
PARSER_VERSION = "m9-biological-parser-v1"
PRODUCTION_EXECUTION_AUTHORISED = False
PRODUCTION_DERIVED_LEDGER_AUTHORISED = False

PINNED_RNAGENESIS_COMMIT = "e3b855bbf4d1af376f43747643fa30afd662828c"
PINNED_CLEANER_PATH = "scripts/audit_generation_output.py"
PINNED_CLEANER_INTRODUCING_COMMIT = "112a120282667c382790031fe74942f89f7b84eb"
PINNED_CLEANER_GIT_BLOB = "3480af2dd758f4824655b3f7c8a5276214a61682"
PINNED_CLEANER_SHA256 = "4d0c56a7d931a2c3c5c049cfeabd4937134b3d1125ef7a68b10472527d2fd2a2"

OUTCOME_VALID = "valid_canonical_sequence"
OUTCOME_EMPTY = "empty_output"
OUTCOME_UNPARSEABLE = "unparseable_output"
OUTCOME_NON_SEQUENCE = "non_sequence_output"
OUTCOME_NON_ACGU = "parsed_non_acgu"
OUTCOMES = (
    OUTCOME_VALID,
    OUTCOME_EMPTY,
    OUTCOME_UNPARSEABLE,
    OUTCOME_NON_SEQUENCE,
    OUTCOME_NON_ACGU,
)
FAILURE_REASONS = (
    OUTCOME_EMPTY,
    OUTCOME_UNPARSEABLE,
    OUTCOME_NON_SEQUENCE,
    OUTCOME_NON_ACGU,
)
SEQUENCE_RETAINED_OUTCOMES = (OUTCOME_VALID, OUTCOME_NON_ACGU)

BOUNDARY_MARKERS = frozenset("12")
CANONICAL_SEQUENCE = re.compile(r"^[ACGU]+$")
SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$")

REFUSED_ROLES = frozenset(("TRAIN", "VALIDATION", "REF", "EVAL"))
FORBIDDEN_BASENAMES = frozenset(
    ("corpus_final.txt", "ft_train.csv", "ft_validation.csv", "ref.csv", "eval.csv")
)
PRODUCTION_RUN_ROOT = "/home/laura/rnagenesis-mres-runs"
MUTATION_REQUESTS = frozenset(
    (
        "replenish",
        "replenishment",
        "filter",
        "filtering",
        "deduplicate",
        "deduplication",
        "drop",
        "replace",
        "replacement",
        "rewrite",
        "rewriting",
    )
)
PATH_ARGUMENT_KEYS = frozenset(
    ("path", "paths", "filename", "file", "filepath", "root", "run_root", "directory")
)
ROLE_ARGUMENT_KEYS = frozenset(("role", "data_role", "declared_role"))
UNLOCK_ARGUMENT_KEYS = frozenset(("eval_unlock", "unlock_eval", "unlock"))
MUTATION_ARGUMENT_KEYS = frozenset(("operation", "action", "mutation"))


class ParserContractError(ValueError):
    """The frozen parser contract refused the request."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def split_raw_records(text):
    """Split on LF delimiters without inventing a record for a final newline.

    CRLF is one delimiter. Empty text between delimiters is preserved. A file
    with no characters yields no records; a file whose only character is a
    newline yields one empty record. A carriage return is removed only when
    it is the partner of a CRLF delimiter.

    Equivalent to ``split_raw_records`` in the pinned cleaner.
    """
    if type(text) is not str:
        raise ParserContractError("payload_type_invalid", "record splitting requires a decoded string")
    if text == "":
        return []
    ended_with_newline = text.endswith("\n")
    parts = text.split("\n")
    if ended_with_newline:
        parts.pop()
    records = []
    last_index = len(parts) - 1
    for index, record in enumerate(parts):
        followed_by_newline = ended_with_newline or index != last_index
        if followed_by_newline and record.endswith("\r"):
            record = record[:-1]
        records.append(record)
    return records


def split_raw_record_bytes(data):
    """Byte analogue of ``split_raw_records``.

    LF and CR are single ASCII bytes, so this matches the pinned splitter
    after a successful UTF-8 decode. Each record is still decoded on its own.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise ParserContractError("payload_type_invalid", "byte splitting requires in-memory bytes")
    if data == b"" or data == bytearray():
        return []
    ended_with_newline = data.endswith(b"\n")
    parts = bytes(data).split(b"\n")
    if ended_with_newline:
        parts.pop()
    records = []
    last_index = len(parts) - 1
    for index, record in enumerate(parts):
        followed_by_newline = ended_with_newline or index != last_index
        if followed_by_newline and record.endswith(b"\r"):
            record = record[:-1]
        records.append(record)
    return records


def strip_boundary_markers(raw):
    """Return ``(removed_prefix, body, removed_suffix)``.

    The leading run of ``1`` and ``2`` is taken first. The trailing run is
    taken only from what remains, so the two removals do not overlap. A
    marker-only string is entirely the removed prefix, with an empty suffix.
    Internal characters are not changed.

    Equivalent to ``strip_boundary_markers`` in the pinned cleaner.
    """
    if type(raw) is not str:
        raise ParserContractError("payload_type_invalid", "boundary-marker removal requires a decoded string")
    start = 0
    length = len(raw)
    while start < length and raw[start] in BOUNDARY_MARKERS:
        start += 1
    end = length
    while end > start and raw[end - 1] in BOUNDARY_MARKERS:
        end -= 1
    return raw[:start], raw[start:end], raw[end:]


def _blank_parse(outcome):
    return {
        "outcome": outcome,
        "failure_reason": None if outcome == OUTCOME_VALID else outcome,
        "parsed_sequence": None,
        "parsed_length": 0 if outcome == OUTCOME_EMPTY else None,
        "removed_prefix": None,
        "removed_suffix": None,
    }


def parse_biological_text(value):
    """Parse one already extracted attempt payload.

    Strings lose leading and trailing ``1``/``2`` runs and are then classified.
    Marker strings are not treated as biologically invalid before that removal.
    A non-string decoded value is ``non_sequence_output``. Bytes that are not
    valid UTF-8 are ``unparseable_output``. Source-container failure, including
    whole-file UTF-8 failure and loss of attempt identity, is decided by the
    source adapter before this function sees a trusted payload. This function
    does not split records, uppercase, strip whitespace, convert T to U, or
    drop the attempt.
    """
    if _is_path_object(value):
        raise ParserContractError("filesystem_path_refused", "the biological parser does not accept a filesystem path")
    if isinstance(value, (bytes, bytearray)):
        try:
            text = bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            return _blank_parse(OUTCOME_UNPARSEABLE)
        value = text
    if type(value) is not str:
        return _blank_parse(OUTCOME_NON_SEQUENCE)
    prefix, body, suffix = strip_boundary_markers(value)
    if prefix + body + suffix != value:
        raise ParserContractError("parser_reconstruction_failed", "boundary-marker removal did not preserve the record")
    if body == "":
        parsed = _blank_parse(OUTCOME_EMPTY)
    elif CANONICAL_SEQUENCE.fullmatch(body):
        parsed = _blank_parse(OUTCOME_VALID)
        parsed["parsed_sequence"] = body
        parsed["parsed_length"] = len(body)
        parsed["failure_reason"] = None
    else:
        parsed = _blank_parse(OUTCOME_NON_ACGU)
        parsed["parsed_sequence"] = body
        parsed["parsed_length"] = len(body)
    parsed["removed_prefix"] = prefix
    parsed["removed_suffix"] = suffix
    return parsed


def sha256_text(value):
    return type(value) is str and SHA256_TEXT.fullmatch(value) is not None


def _is_path_object(value):
    if isinstance(value, (str, bytes, bytearray)):
        return False
    return callable(getattr(value, "__fspath__", None))


def _basename(value):
    text = str(value).replace("\\", "/")
    if text.endswith("/"):
        text = text[:-1]
    return text.rsplit("/", 1)[-1]


def reject_control_string(value, *, sequence_payload=False):
    """Refuse path, role, filename, and run-root control values.

    Sequence payloads are parsed even when they contain a slash or spell a
    role name. Those characters are biological parse input, not a file request.
    """
    if sequence_payload:
        return
    if _is_path_object(value):
        raise ParserContractError("filesystem_path_refused", "a filesystem path argument is refused")
    if type(value) is not str:
        return
    basename = _basename(value)
    if basename.lower() in FORBIDDEN_BASENAMES or value.lower() in FORBIDDEN_BASENAMES:
        raise ParserContractError("filename_refused", "a protected corpus filename is refused")
    if value in REFUSED_ROLES:
        raise ParserContractError("role_refused", "a protected data role is refused")
    if PRODUCTION_RUN_ROOT in value or value.rstrip("/") == PRODUCTION_RUN_ROOT:
        raise ParserContractError("production_run_root_refused", "a production run-root path is refused")
    if value.startswith("/") or value.startswith("~") or "\\" in value or "/" in value:
        raise ParserContractError("filesystem_path_refused", "a filesystem path argument is refused")


def enforce_firewall(rejected=None, control_values=()):
    """Refuse path, role, filename, EVAL-unlock, and row-mutation requests."""
    if rejected is None:
        rejected = {}
    if not isinstance(rejected, dict):
        raise ParserContractError("firewall_invalid", "firewall arguments are not an object")
    for key, value in rejected.items():
        if key in PATH_ARGUMENT_KEYS:
            if _is_path_object(value) or type(value) is str:
                reject_control_string(value)
            raise ParserContractError("filesystem_path_refused", "a filesystem path argument is refused")
        if key in ROLE_ARGUMENT_KEYS:
            if type(value) is str and value in REFUSED_ROLES:
                raise ParserContractError("role_refused", "a protected data role is refused")
            raise ParserContractError("role_refused", "a role argument is refused by the parser firewall")
        if key in UNLOCK_ARGUMENT_KEYS:
            if value is False or value is None:
                continue
            raise ParserContractError("eval_unlock_refused", "an EVAL unlock is refused")
        if key in MUTATION_ARGUMENT_KEYS:
            token = value.lower() if type(value) is str else str(value).lower()
            if token in MUTATION_REQUESTS:
                raise ParserContractError("mutation_refused", "replenishment, filtering, deduplication, and dropping are refused")
            raise ParserContractError("mutation_refused", "a row-mutation request is refused")
        raise ParserContractError("firewall_invalid", "an unexpected control argument is refused")
    for value in control_values:
        reject_control_string(value)


def reject_primary_payload(value):
    """Refuse a path-like object supplied where bytes or a decoded object belong."""
    if _is_path_object(value):
        raise ParserContractError("filesystem_path_refused", "a filesystem path argument is refused")
    if type(value) is str:
        reject_control_string(value)
        raise ParserContractError(
            "payload_type_invalid",
            "the parser accepts in-memory bytes or an already decoded object",
        )

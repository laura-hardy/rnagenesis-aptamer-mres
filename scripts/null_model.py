# B2 empirical-null generator.
# Statistical design preserved from the original sampler.
# Stage 2A authorises implementation and synthetic tests only.
# The repository configuration remains non-executable. Production paths are
# pinned in this file. When the execution gates are later opened, production
# also requires the scientific_execution_authorisation block to name exactly
# one output directory. The CLI cannot select a repository root, config,
# contract, TRAIN_TEXT path, seed, count, run root, or authorisation override.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from collections import Counter

PROBABILITY_ORDER = ("A", "C", "U", "G")
ABSOLUTE_SUM_TOLERANCE = 1e-12
RELATIVE_SUM_TOLERANCE = 0.0
DEFAULT_ATTEMPT_COUNT = 30000
DEFAULT_SEED = 42
EXPECTED_SEQUENCE_COUNT = 669
EXPECTED_UNIQUE_COUNT = 669
TRAIN_TEXT_SHA256 = (
    "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d"
)
AUTHORIZED_TRAIN_TEXT_PATH = Path(
    "/home/laura/rnagenesis-mres-data/development/corpus_final.txt"
)
PRODUCTION_RUN_ROOT = Path("/home/laura/rnagenesis-mres-runs")
BIOLOGICAL_DATA_ROOT = Path("/home/laura/rnagenesis-mres-data")
B2_CONFIG_RELATIVE = Path("config/experiments/B2_empirical_null.yaml")
FROZEN_CONTRACT_RELATIVE = Path("config/modelling/frozen_data_contract.json")
FROZEN_CONTRACT_SHA256 = (
    "396c83c3dbf9afc656ad5c60ec05c94fce3c5a684990c3cc1cebfb2411ccd5ff"
)
REF_CONTRACT_SHA256 = (
    "531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23"
)
EVAL_CONTRACT_SHA256 = (
    "ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015"
)
EXECUTABLE_DOCUMENT_STATUS = "APPROVED_FOR_SCIENTIFIC_EXECUTION"
NON_EXECUTABLE_DOCUMENT_STATUSES = frozenset(
    [
        "DRAFT_PENDING_HUMAN_APPROVAL",
        "APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION",
    ]
)
PROHIBITED_INPUT_FILENAMES = frozenset(
    ["ft_train.csv", "ft_validation.csv", "ref.csv", "eval.csv"]
)
AMBIGUOUS_OUTPUT_NAMES = frozenset(
    ["final", "final2", "best", "good_run", "new_model"]
)
RAW_RECORD_KEYS = (
    "attempt_index",
    "seed",
    "sampled_length",
    "sequence",
    "valid_acgu",
    "sequence_sha256",
)
RAW_JSONL_FILENAME = "b2_empirical_null_raw.jsonl"
RNG_CONSUMPTION_ORDER = (
    "one_vectorized_length_draw_with_replacement_from_the_empirical_length_list",
    "then_for_each_sampled_length_in_attempt_order_one_vectorized_nucleotide_draw_of_that_length",
)
TEST_ONLY_TOKEN = "M4_STAGE2A_TEST_ONLY_SYNTHETIC_FIXTURE_NOT_A_BIOLOGICAL_RUN"
ACGU_PATTERN = "^[ACGU]+$"
AUTHORISED_CONDITION = "B2_train_matched_empirical_null"
_AMBIGUITY = frozenset("NRYSWKMBDHVnryswkmbdhv")

# Manifest serialization, documented and deterministic:
# one UTF-8 JSON object; declared key order; compact separators "," and ":";
# ensure_ascii false; no spaces outside strings; no BOM; no carriage returns;
# one trailing LF. Float64 quantities are decimal strings from format ".17g".
# A successful manifest records observed values. Genuinely unavailable fields
# are {"value": null, "status": "NOT_APPLICABLE", "reason": ...}.
# This module does not invent observed run results.


class NullModelError(Exception):
    """Fail-closed error. Detail must not contain sequence contents."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        self.secondary_failure = None
        super(NullModelError, self).__init__("{}: {}".format(code, detail))


class TestOnlySyntheticFixture(object):
    """Test-only injection seam. Unreachable from the CLI.

    Environment variables cannot enable this object. The synthetic executor
    rejects the biological development root, the production TRAIN path, the
    production TRAIN hash, and the production run root before it reads them.
    """

    def __init__(
        self,
        fixture_root,
        config_path,
        contract_path,
        input_path,
        run_root,
        attempt_count,
        seed,
        expected_contract_sha256,
        fail_after_directory_creation=False,
    ):
        self.token = TEST_ONLY_TOKEN
        self.purpose = "synthetic_unit_test_not_a_biological_run"
        self.fixture_root = fixture_root
        self.config_path = config_path
        self.contract_path = contract_path
        self.input_path = input_path
        self.run_root = run_root
        self.attempt_count = attempt_count
        self.seed = seed
        self.expected_contract_sha256 = expected_contract_sha256
        self.fail_after_directory_creation = bool(fail_after_directory_creation)


def not_applicable(reason):
    """Explicit null for a field this run cannot observe. Not a protocol stand-in."""
    return {
        "value": None,
        "status": "NOT_APPLICABLE",
        "reason": reason,
    }


def _is_relative_to(path, root):
    try:
        Path(path).relative_to(root)
    except ValueError:
        return False
    return True


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sequence_sha256(sequence):
    """SHA-256 of the UTF-8 sequence bytes, without a trailing newline."""
    return _sha256_bytes(sequence.encode("utf-8"))


def _assert_no_spaces_outside_strings(text):
    in_string = False
    escape = False
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in (" ", "\t"):
            raise NullModelError(
                "canonical_json_spaces",
                "JSON contains whitespace outside a string value",
            )


def canonical_json_document(obj):
    """Deterministic UTF-8 JSON document with one trailing LF."""
    try:
        text = json.dumps(
            obj,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
            sort_keys=False,
        )
    except (TypeError, ValueError):
        raise NullModelError(
            "canonical_json_rejected",
            "value could not be serialized as canonical JSON",
        )
    if "\r" in text or text.startswith("\ufeff"):
        raise NullModelError(
            "canonical_json_rejected",
            "carriage return or BOM in JSON text",
        )
    _assert_no_spaces_outside_strings(text)
    data = text.encode("utf-8") + b"\n"
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data:
        raise NullModelError(
            "canonical_json_rejected",
            "carriage return or BOM in JSON bytes",
        )
    return data


def format_float64(value):
    return format(np.float64(value), ".17g")


def get_corpus_stats(sequences):
    """Compute nucleotide frequencies and length distribution from corpus."""
    all_bases = "".join(sequences)
    counts = Counter(all_bases)
    total = sum(counts.values())
    freqs = {b: counts[b] / total for b in "ACUG"}
    lengths = [len(s) for s in sequences]
    return freqs, lengths


def _sample_lengths_and_sequences(n, freqs, lengths, seed):
    rng = np.random.default_rng(seed)
    bases = list(freqs.keys())
    probs = [freqs[b] for b in bases]

    # Sample lengths from empirical distribution
    sampled_lengths = rng.choice(lengths, size=n, replace=True)

    sequences = []
    length_values = []
    for length in sampled_lengths:
        length_values.append(int(length))
        seq = "".join(rng.choice(bases, size=length, p=probs))
        sequences.append(seq)
    return sequences, length_values


def generate_null_sequences(n, freqs, lengths, seed=42):
    sequences, _length_values = _sample_lengths_and_sequences(
        n, freqs, lengths, seed
    )
    return sequences


def _reject_sequence_character(line_index, char):
    location = "line_index={}".format(line_index)
    if char.isspace():
        raise NullModelError("whitespace_rejected", "whitespace at " + location)
    if char in ("T", "t"):
        raise NullModelError("thymine_rejected", "T or t at " + location)
    if char in _AMBIGUITY:
        raise NullModelError(
            "ambiguity_symbol_rejected",
            "ambiguity symbol at " + location,
        )
    if char.islower():
        raise NullModelError("lowercase_rejected", "lowercase at " + location)
    if char not in "ACGU":
        raise NullModelError(
            "non_acgu_rejected",
            "character outside ACGU at " + location,
        )


def parse_train_text_bytes(raw):
    """Parse exact TRAIN text bytes. No stripping, case folding, or rewriting."""
    if not isinstance(raw, (bytes, bytearray)):
        raise NullModelError("input_type", "TRAIN text must be raw bytes")
    raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise NullModelError("bom_rejected", "UTF-8 BOM is not permitted")
    if b"\r" in raw:
        raise NullModelError(
            "carriage_return_rejected",
            "carriage returns are not permitted",
        )
    if raw == b"":
        raise NullModelError("empty_input", "TRAIN text is empty")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise NullModelError("utf8_rejected", "TRAIN text is not valid UTF-8")
    body = text[:-1] if text.endswith("\n") else text
    lines = body.split("\n")
    sequences = []
    for line_index, line in enumerate(lines):
        if line == "":
            raise NullModelError(
                "blank_line",
                "blank line at line_index={}".format(line_index),
            )
        for char in line:
            _reject_sequence_character(line_index, char)
        if line != line.strip() or any(char.isspace() for char in line):
            raise NullModelError(
                "whitespace_rejected",
                "whitespace at line_index={}".format(line_index),
            )
        sequences.append(line)
    return sequences


def reject_prohibited_input_path(path, role):
    """Refuse prohibited names and roles before any read."""
    if role in ("REF", "EVAL"):
        raise NullModelError(
            "ref_eval_access_prohibited",
            "REF and EVAL must not be opened",
        )
    if role != "TRAIN_TEXT":
        raise NullModelError(
            "unauthorised_input_role",
            "only the TRAIN_TEXT role is authorised",
        )
    name = Path(path).name.lower()
    if name in PROHIBITED_INPUT_FILENAMES:
        raise NullModelError(
            "prohibited_input",
            "refusing prohibited filename",
        )


def enforce_sequence_contract(sequences, expected_count, expected_unique):
    """Enforce physical count, uniqueness, and the ACGU pattern. No rewriting."""
    if len(sequences) == 0:
        raise NullModelError("empty_corpus", "sequence list is empty")
    if len(sequences) != expected_count:
        raise NullModelError(
            "sequence_count_mismatch",
            "actual_count={} expected_count={}".format(
                len(sequences), expected_count
            ),
        )
    seen = set()
    for line_index, sequence in enumerate(sequences):
        if sequence in seen:
            raise NullModelError(
                "duplicate_sequence",
                "duplicate at line_index={}".format(line_index),
            )
        seen.add(sequence)
        if not sequence or _contains_non_acgu(sequence):
            raise NullModelError(
                "non_acgu_rejected",
                "nonempty ACGU required at line_index={}".format(line_index),
            )
    unique_count = len(seen)
    if unique_count != expected_unique:
        raise NullModelError(
            "uniqueness_mismatch",
            "actual_unique={} expected_unique={}".format(
                unique_count, expected_unique
            ),
        )
    return unique_count


def _contains_non_acgu(sequence):
    for char in sequence:
        if char not in "ACGU":
            return True
    return False


def enforce_sha256(actual_sha256, expected_sha256):
    if actual_sha256 != expected_sha256:
        raise NullModelError(
            "sha256_mismatch",
            "actual_sha256={} expected_sha256={}".format(
                actual_sha256, expected_sha256
            ),
        )


def validate_probabilities(probabilities):
    """Float64 A/C/U/G probabilities. Relative tolerance is zero."""
    if RELATIVE_SUM_TOLERANCE != 0:
        raise NullModelError(
            "relative_tolerance_not_zero",
            "relative tolerance must be zero",
        )
    if not isinstance(probabilities, np.ndarray) or probabilities.dtype != np.float64:
        raise NullModelError(
            "probability_dtype",
            "probabilities must be a float64 vector",
        )
    if probabilities.shape != (4,):
        raise NullModelError(
            "probability_shape",
            "probability vector must contain 4 A/C/U/G values",
        )
    if not bool(np.all(np.isfinite(probabilities))):
        raise NullModelError(
            "probability_not_finite",
            "probabilities must be finite",
        )
    if bool(np.any(probabilities < 0)):
        raise NullModelError(
            "probability_negative",
            "probabilities must be nonnegative",
        )
    total = np.sum(probabilities, dtype=np.float64)
    deviation = np.abs(total - np.float64(1.0))
    if deviation > np.float64(ABSOLUTE_SUM_TOLERANCE):
        raise NullModelError(
            "probability_sum_tolerance",
            "abs(sum-1) exceeds absolute_tolerance={} relative_tolerance=0".format(
                format_float64(ABSOLUTE_SUM_TOLERANCE)
            ),
        )
    return probabilities


def probabilities_from_counts(counts):
    if list(counts.keys()) != list(PROBABILITY_ORDER):
        raise NullModelError(
            "probability_order",
            "nucleotide counts must be ordered A, C, U, G",
        )
    values = [counts[base] for base in PROBABILITY_ORDER]
    if any((not isinstance(value, int)) or isinstance(value, bool) or value < 0 for value in values):
        raise NullModelError(
            "nucleotide_counts",
            "nucleotide counts must be nonnegative integers",
        )
    total = sum(values)
    if total == 0:
        raise NullModelError("zero_nucleotides", "total nucleotide count is zero")
    probabilities = np.asarray(values, dtype=np.float64) / np.float64(total)
    return validate_probabilities(probabilities)


def _ordered_counts(counts):
    return {base: int(counts[base]) for base in PROBABILITY_ORDER}


def compute_corpus_statistics(sequences):
    if len(sequences) == 0:
        raise NullModelError("empty_corpus", "sequence list is empty")
    counts = {base: 0 for base in PROBABILITY_ORDER}
    lengths = []
    for line_index, sequence in enumerate(sequences):
        if sequence == "":
            raise NullModelError(
                "empty_sequence",
                "empty sequence at line_index={}".format(line_index),
            )
        for char in sequence:
            if char not in counts:
                _reject_sequence_character(line_index, char)
            counts[char] += 1
        lengths.append(len(sequence))
    total = sum(counts.values())
    if total == 0:
        raise NullModelError("zero_nucleotides", "total nucleotide count is zero")
    probabilities = probabilities_from_counts(counts)
    ordered = sorted(lengths)
    minimum = int(ordered[0])
    maximum = int(ordered[-1])
    mean = np.float64(np.asarray(ordered, dtype=np.float64).sum()) / np.float64(
        len(ordered)
    )
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        median = np.float64(ordered[midpoint])
    else:
        median = (
            np.float64(ordered[midpoint - 1]) + np.float64(ordered[midpoint])
        ) / np.float64(2.0)
    observed = {}
    for length in ordered:
        observed[length] = observed.get(length, 0) + 1
    complete = []
    for length in range(minimum, maximum + 1):
        complete.append({"length": length, "count": int(observed.get(length, 0))})
    return {
        "nucleotide_counts": _ordered_counts(counts),
        "nucleotide_count_order": list(PROBABILITY_ORDER),
        "total_nucleotides": int(total),
        "probabilities": probabilities,
        "probability_order": list(PROBABILITY_ORDER),
        "absolute_tolerance": np.float64(ABSOLUTE_SUM_TOLERANCE),
        "relative_tolerance": RELATIVE_SUM_TOLERANCE,
        "lengths": lengths,
        "complete_length_histogram": complete,
        "minimum_length": minimum,
        "maximum_length": maximum,
        "mean_length": np.float64(mean),
        "median_length": np.float64(median),
    }


def frequencies_from_probabilities(probabilities):
    validate_probabilities(probabilities)
    freqs = {}
    for index, base in enumerate(PROBABILITY_ORDER):
        freqs[base] = float(np.float64(probabilities[index]))
    return freqs


def sequence_is_valid_acgu(sequence):
    if not sequence:
        return False
    for char in sequence:
        if char not in "ACGU":
            return False
    return True


def build_raw_records(n, freqs, lengths, seed):
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise NullModelError("attempt_count", "attempt count must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise NullModelError("seed", "seed must be an integer")
    if list(freqs.keys()) != list(PROBABILITY_ORDER):
        raise NullModelError(
            "probability_order",
            "frequency mapping must be ordered A, C, U, G",
        )
    sequences, sampled_lengths = _sample_lengths_and_sequences(
        n, freqs, lengths, seed
    )
    if len(sequences) != n or len(sampled_lengths) != n:
        raise NullModelError(
            "retention_mismatch",
            "sampler did not retain every requested attempt",
        )
    records = []
    for attempt_index, (sampled_length, sequence) in enumerate(
        zip(sampled_lengths, sequences)
    ):
        records.append(
            {
                "attempt_index": attempt_index,
                "seed": int(seed),
                "sampled_length": int(sampled_length),
                "sequence": sequence,
                "valid_acgu": bool(sequence_is_valid_acgu(sequence)),
                "sequence_sha256": sequence_sha256(sequence),
            }
        )
    return records


def unique_count_diagnostic(records):
    return len(set(record["sequence"] for record in records))


def serialize_raw_record(record):
    ordered = {}
    for key in RAW_RECORD_KEYS:
        if key not in record:
            raise NullModelError(
                "raw_record_missing_field",
                "raw record is missing a required field",
            )
        ordered[key] = record[key]
    text = json.dumps(
        ordered,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
        sort_keys=False,
    )
    if "\r" in text or text.startswith("\ufeff"):
        raise NullModelError(
            "canonical_json_rejected",
            "carriage return or BOM in raw record",
        )
    _assert_no_spaces_outside_strings(text)
    if not text.endswith("}") or not text.startswith("{"):
        raise NullModelError("canonical_json_rejected", "raw record is not a JSON object")
    return text


def serialize_jsonl(records):
    if len(records) == 0:
        raise NullModelError("empty_output", "refusing to write an empty attempt file")
    pieces = []
    expected_index = 0
    for record in records:
        if record["attempt_index"] != expected_index:
            raise NullModelError(
                "attempt_index_not_contiguous",
                "attempt indexes must be contiguous and zero-based",
            )
        pieces.append(serialize_raw_record(record) + "\n")
        expected_index += 1
    data = "".join(pieces).encode("utf-8")
    if data.startswith(b"\xef\xbb\xbf") or b"\r" in data or not data.endswith(b"\n"):
        raise NullModelError(
            "canonical_json_rejected",
            "JSONL must be UTF-8, LF-only, without a BOM, and must end in LF",
        )
    return data


def _json_counts(counts):
    return {base: int(counts[base]) for base in PROBABILITY_ORDER}


def _json_histogram(histogram):
    return [
        {"length": int(item["length"]), "count": int(item["count"])}
        for item in histogram
    ]


def _json_probabilities(probabilities):
    validate_probabilities(probabilities)
    return {
        base: format_float64(probabilities[index])
        for index, base in enumerate(PROBABILITY_ORDER)
    }


def production_repository_root():
    """Repository root derived from this file. Not replaceable by the caller."""
    return Path(__file__).resolve().parents[1]


def _lexical_absolute(path):
    return Path(os.path.normpath(str(path)))


def approval_from_config(config, config_sha256):
    """Read approval metadata from the config object that passed the gate."""
    block = config.get("human_approval")
    if not isinstance(block, dict):
        raise NullModelError(
            "approval_metadata_missing",
            "human approval metadata is missing from configuration",
        )
    required = (
        "approving_person",
        "approval_date",
        "approval_recorded_timestamp",
        "approval_source",
        "approval_scope",
        "explicitly_not_approved",
        "m4_complete",
    )
    for key in required:
        if key not in block:
            raise NullModelError(
                "approval_metadata_missing",
                "human approval metadata is incomplete",
            )
    if not isinstance(block["explicitly_not_approved"], list):
        raise NullModelError(
            "approval_metadata_missing",
            "human approval metadata is incomplete",
        )
    return {
        "approving_person": block["approving_person"],
        "approval_date": block["approval_date"],
        "approval_recorded_timestamp": block["approval_recorded_timestamp"],
        "approval_source": block["approval_source"],
        "approval_scope": block["approval_scope"],
        "explicitly_not_approved": list(block["explicitly_not_approved"]),
        "m4_complete": block["m4_complete"],
        "document_status": config.get("document_status"),
        "consumable_by_executable_workflow": config.get(
            "consumable_by_executable_workflow"
        ),
        "configuration_sha256": config_sha256,
    }


def build_observed_success_manifest(observed):
    """Success manifest built only from values this completed run observed.

    Approval fields come from observed["approval"], which was read from the
    configuration bytes that passed the execution gate. Protocol requirements
    use *_expected keys. Runtime results use *_actual or plain observed values.
    """
    approval = observed["approval"]
    git_info = observed["git"]
    stats = observed["stats"]
    access_log = observed["access_log"]
    ref_opened_actual = any(entry.get("role") == "REF" for entry in access_log)
    eval_opened_actual = any(entry.get("role") == "EVAL" for entry in access_log)
    rows_dropped_actual = int(observed["attempt_count"]) - int(observed["retained_count"])
    return {
        "schema_version": observed["schema_version"],
        "approval_status": approval["document_status"],
        "consumable_by_executable_workflow": approval[
            "consumable_by_executable_workflow"
        ],
        "experiment_id": observed["experiment_id"],
        "condition_identifier": observed["condition_identifier"],
        "run_identifier": observed["run_identifier"],
        "attempt_identifier": observed["attempt_identifier"],
        "timestamps": {
            "start": observed["started_at"],
            "end": observed["ended_at"],
        },
        "hostname": observed["hostname"],
        "repository_provenance": {
            "mres_commit": git_info["mres_commit"],
            "mres_upstream_sha": git_info["mres_upstream_sha"],
            "branch": git_info["branch"],
            "dirty": git_info["dirty"],
            "patch_sha256": git_info["patch_sha256"],
            "patch_sha256_reason": git_info["patch_sha256_reason"],
            "rnagenesis_repository_sha": not_applicable(
                "B2 does not execute RNAGenesis model code"
            ),
            "upstream_training_code_sha": not_applicable("B2 is not a training run"),
            "frozen_corpus_commit": observed["frozen_corpus_commit"],
        },
        "configuration": {
            "path": observed["config_path"],
            "sha256": observed["config_sha256"],
            "approval_status": approval["document_status"],
        },
        "frozen_contract": {
            "path": observed["contract_path"],
            "sha256": observed["contract_sha256"],
        },
        "input": {
            "path": observed["input_path"],
            "role": "TRAIN_TEXT",
            "expected_sha256": observed["expected_input_sha256"],
            "actual_sha256": observed["actual_input_sha256"],
            "expected_sequence_count": observed["expected_sequence_count"],
            "actual_sequence_count": observed["actual_sequence_count"],
            "expected_unique_count": observed["expected_unique_count"],
            "actual_unique_count": observed["actual_unique_count"],
            "alphabet": ACGU_PATTERN,
            "alphabet_result": "passed",
        },
        "access_log": access_log,
        "ref_opened_expected": False,
        "ref_opened_actual": ref_opened_actual,
        "eval_opened_expected": False,
        "eval_opened_actual": eval_opened_actual,
        "ref_non_access": {
            "contract_sha256": REF_CONTRACT_SHA256,
            "statement": "REF contract hash is metadata. opened_actual is derived from the access log.",
        },
        "eval_non_access": {
            "contract_sha256": EVAL_CONTRACT_SHA256,
            "statement": "EVAL contract hash is metadata. opened_actual is derived from the access log.",
        },
        "corpus_statistics": {
            "nucleotide_counts": _json_counts(stats["nucleotide_counts"]),
            "total_nucleotides": int(stats["total_nucleotides"]),
            "probabilities": _json_probabilities(stats["probabilities"]),
            "probability_order": list(PROBABILITY_ORDER),
            "absolute_tolerance": format_float64(ABSOLUTE_SUM_TOLERANCE),
            "relative_tolerance": RELATIVE_SUM_TOLERANCE,
            "complete_length_histogram": _json_histogram(
                stats["complete_length_histogram"]
            ),
            "minimum_length": int(stats["minimum_length"]),
            "maximum_length": int(stats["maximum_length"]),
            "mean_length": format_float64(stats["mean_length"]),
            "median_length": format_float64(stats["median_length"]),
        },
        "rng": {
            "numpy_version": np.__version__,
            "rng_class": "numpy.random.Generator",
            "rng_constructor": "numpy.random.default_rng",
            "rng_type": "numpy.random.Generator",
            "seed": int(observed["seed"]),
            "rng_consumption_order": list(RNG_CONSUMPTION_ORDER),
        },
        "generation_accounting": {
            "requested_count": int(observed["attempt_count"]),
            "raw_count": int(observed["retained_count"]),
            "retained_count": int(observed["retained_count"]),
            "unique_count_diagnostic": int(observed["unique_count_diagnostic"]),
            "unique_count_is_not_an_acceptance_threshold": True,
            "rows_dropped_expected": 0,
            "rows_dropped_actual": rows_dropped_actual,
        },
        "command": observed["command"],
        "exit_status": 0,
        "raw_output": {
            "path": observed["output_path"],
            "filename": RAW_JSONL_FILENAME,
            "byte_count": int(observed["output_byte_count"]),
            "sha256": observed["output_sha256"],
        },
        "warnings": list(observed["warnings"]),
        "retries": list(observed["retries"]),
        "deviations": list(observed["deviations"]),
        "stopping_reason": observed["stopping_reason"],
        "overwrite_refusal_check": {
            "result": "passed_exclusive_create",
            "path_existed_before_create": False,
            "creation_primitive": "os.mkdir",
            "exist_ok": False,
        },
        "human_approval": approval,
        "gpu_used_expected": False,
        "device_backend_actual": "cpu_numpy",
        "gpu_api_invoked_actual": bool(observed["gpu_api_invoked"]),
        "device": {
            "gpu_used_expected": False,
            "device_backend_actual": "cpu_numpy",
            "gpu_api_invoked_actual": bool(observed["gpu_api_invoked"]),
            "physical_gpu_index": None,
            "physical_gpu_model": None,
            "cuda_visible_devices": None,
            "visible_logical_device": None,
            "nvidia_smi_snapshot": not_applicable(
                "B2 sampling does not invoke a GPU API"
            ),
        },
        "interpreter": {
            "python_version": sys.version,
            "executable": sys.executable,
            "numpy_version": np.__version__,
        },
        "not_applicable_model_fields": {
            "diffusers_patch_verification_hash": not_applicable(
                "B2 does not import diffusers or load model weights"
            ),
            "encdec_checkpoint_sha256": not_applicable(
                "B2 loads no EncDec checkpoint"
            ),
            "diffusion_checkpoint_sha256": not_applicable(
                "B2 loads no diffusion checkpoint"
            ),
            "selected_checkpoint_sha256": not_applicable(
                "B2 does not select a checkpoint"
            ),
        },
        "serialization": {
            "encoding": "utf-8",
            "separators": [",", ":"],
            "ensure_ascii": False,
            "sort_keys": False,
            "key_order": "declared_field_order",
            "bom": False,
            "carriage_returns": False,
            "trailing_lf": True,
            "float64_format": ".17g",
        },
    }


def serialize_manifest(manifest):
    return canonical_json_document(manifest)


def collect_git_provenance(repo_root):
    """Read-only git provenance. Used when a run builds its success manifest."""

    def _run(args):
        try:
            completed = subprocess.run(
                args,
                cwd=str(repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            raise NullModelError(
                "git_provenance_unavailable",
                "git provenance could not be read",
            )
        return completed.stdout.decode("utf-8")

    head = _run(["git", "rev-parse", "HEAD"]).strip()
    upstream = _run(["git", "rev-parse", "origin/main"]).strip()
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    porcelain = _run(["git", "status", "--porcelain"])
    dirty = porcelain.strip() != ""
    if dirty:
        patch = _run(["git", "diff", "HEAD"])
        staged = _run(["git", "diff", "--cached"])
        patch_sha = _sha256_bytes((patch + staged).encode("utf-8"))
        patch_reason = "dirty working tree; patch hash covers unstaged and staged diffs"
    else:
        patch_sha = None
        patch_reason = "working tree clean; patch hash is not applicable"
    return {
        "mres_commit": head,
        "mres_upstream_sha": upstream,
        "branch": branch,
        "dirty": dirty,
        "patch_sha256": patch_sha,
        "patch_sha256_reason": patch_reason,
    }


def load_b2_config_bytes(raw):
    try:
        import yaml
    except ImportError:
        raise NullModelError(
            "yaml_dependency_unavailable",
            "PyYAML is not installed. The B2 runner refuses to execute and does not install packages.",
        )
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise NullModelError(
            "config_encoding",
            "B2 configuration must be UTF-8 without a BOM or carriage return",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise NullModelError("config_encoding", "B2 configuration is not valid UTF-8")
    try:
        loaded = yaml.safe_load(text)
    except Exception:
        raise NullModelError("config_parse", "B2 configuration could not be parsed")
    if not isinstance(loaded, dict):
        raise NullModelError("config_shape", "B2 configuration root must be a mapping")
    return loaded


def assert_execution_authorised(config):
    consumable = config.get("consumable_by_executable_workflow", None)
    status = config.get("document_status", None)
    if consumable is not True or status in NON_EXECUTABLE_DOCUMENT_STATUSES or status != EXECUTABLE_DOCUMENT_STATUS:
        raise NullModelError(
            "execution_not_authorised",
            "consumable_by_executable_workflow={} document_status={}. "
            "Stage 1 approval authorises implementation only.".format(
                consumable, status
            ),
        )
    if config.get("test_only_synthetic_fixture", False) and config.get("biological_run", True) is not False:
        raise NullModelError(
            "execution_not_authorised",
            "a synthetic fixture config must declare biological_run false",
        )


def _absolute_canonical_output_text(path):
    """Return path when it is already an absolute lexical canonical string."""
    if not isinstance(path, str) or path == "":
        return None
    if not Path(path).is_absolute():
        return None
    if os.path.normpath(path) != path:
        return None
    if any(part in (".", "..") for part in Path(path).parts):
        return None
    return path


def _require_authorisation_agreement(actual, expected, label):
    if actual != expected:
        raise NullModelError(
            "execution_not_authorised",
            "authorisation {} does not match the canonical B2 configuration".format(
                label
            ),
        )


def assert_scientific_execution_authorisation(config, output_dir):
    """Validate the one-run authorisation block before any biological access.

    Called only for production, and only after the execution gate has passed.
    Containment uses validate_output_containment. A different child of the
    production run root is output_not_authorised. This function does not open
    the frozen contract or TRAIN_TEXT and does not create a directory.
    """
    execution = config.get("execution")
    if not isinstance(execution, dict) or execution.get("authorised") is not True:
        raise NullModelError(
            "execution_not_authorised",
            "execution.authorised is not true",
        )
    block = config.get("scientific_execution_authorisation")
    if not isinstance(block, dict):
        raise NullModelError(
            "execution_not_authorised",
            "scientific_execution_authorisation block is missing",
        )
    if block.get("authorisation_active") is not True:
        raise NullModelError(
            "execution_not_authorised",
            "authorisation_active is not true",
        )
    if block.get("single_run_only") is not True:
        raise NullModelError(
            "execution_not_authorised",
            "single_run_only is not true",
        )
    if block.get("success_claimed") is not False:
        raise NullModelError(
            "execution_not_authorised",
            "success_claimed must be false before execution",
        )
    if block.get("m4_complete") is not False:
        raise NullModelError(
            "execution_not_authorised",
            "m4_complete must be false before execution",
        )
    required_text = (
        ("condition", AUTHORISED_CONDITION),
        ("overwrite_or_append", "prohibited"),
        ("device", "CPU only"),
        ("gpu_use", "prohibited"),
        ("model_loading", "prohibited"),
        ("ref_access", "prohibited"),
        ("eval_access", "prohibited"),
        ("rng", "numpy.random.default_rng"),
        ("alphabet", ACGU_PATTERN),
    )
    for key, expected in required_text:
        if block.get(key) != expected:
            raise NullModelError(
                "execution_not_authorised",
                "authorisation {} is not the required value".format(key),
            )
    sampler = config.get("sampler") if isinstance(config.get("sampler"), dict) else {}
    input_block = config.get("input") if isinstance(config.get("input"), dict) else {}
    _require_authorisation_agreement(
        block.get("condition"),
        config.get("condition_manifest_label"),
        "condition",
    )
    _require_authorisation_agreement(block.get("seed"), sampler.get("seed"), "seed")
    _require_authorisation_agreement(
        block.get("raw_attempt_count"),
        sampler.get("raw_sequence_count"),
        "attempt count",
    )
    _require_authorisation_agreement(
        block.get("rng"),
        sampler.get("numpy_generator"),
        "rng",
    )
    _require_authorisation_agreement(
        block.get("train_text_path"),
        input_block.get("expected_development_path"),
        "TRAIN path",
    )
    _require_authorisation_agreement(
        block.get("train_text_sha256"),
        input_block.get("expected_sha256"),
        "TRAIN hash",
    )
    _require_authorisation_agreement(
        block.get("expected_records"),
        input_block.get("expected_sequence_count"),
        "record count",
    )
    _require_authorisation_agreement(
        block.get("expected_unique_records"),
        input_block.get("expected_unique_count"),
        "unique record count",
    )
    _require_authorisation_agreement(
        block.get("alphabet"),
        input_block.get("alphabet"),
        "alphabet",
    )
    pinned_train = str(_lexical_absolute(AUTHORIZED_TRAIN_TEXT_PATH))
    _require_authorisation_agreement(
        block.get("train_text_path"),
        pinned_train,
        "TRAIN path",
    )
    _require_authorisation_agreement(
        block.get("train_text_sha256"),
        TRAIN_TEXT_SHA256,
        "TRAIN hash",
    )
    _require_authorisation_agreement(block.get("seed"), DEFAULT_SEED, "seed")
    _require_authorisation_agreement(
        block.get("raw_attempt_count"),
        DEFAULT_ATTEMPT_COUNT,
        "attempt count",
    )
    _require_authorisation_agreement(
        block.get("expected_records"),
        EXPECTED_SEQUENCE_COUNT,
        "record count",
    )
    _require_authorisation_agreement(
        block.get("expected_unique_records"),
        EXPECTED_UNIQUE_COUNT,
        "unique record count",
    )
    authorised_text = _absolute_canonical_output_text(block.get("output_directory"))
    if authorised_text is None:
        raise NullModelError(
            "output_not_authorised",
            "authorised output directory is not an absolute canonical path",
        )
    authorised_resolved = validate_output_containment(
        authorised_text,
        PRODUCTION_RUN_ROOT,
    )
    if str(authorised_resolved) != authorised_text:
        raise NullModelError(
            "output_not_authorised",
            "authorised output directory is not an absolute canonical path",
        )
    cli_resolved = validate_output_containment(output_dir, PRODUCTION_RUN_ROOT)
    if str(cli_resolved) != authorised_text:
        raise NullModelError(
            "output_not_authorised",
            "output directory is not the single authorised output directory",
        )
    return cli_resolved


AUTHORISED_REPOSITORY_FILES = {
    "config": "config/experiments/B2_empirical_null.yaml",
    "contract": "config/modelling/frozen_data_contract.json",
}


def resolve_fixed_repository_file(root, relative, role):
    """Confirm lexical identity, then lstat. Do not open the path here."""
    expected_relative = AUTHORISED_REPOSITORY_FILES.get(role)
    if expected_relative is None or Path(relative).as_posix() != expected_relative:
        raise NullModelError(
            role + "_identity",
            "path is not the authorised repository location",
        )
    root_lexical = _lexical_absolute(root)
    lexical = _lexical_absolute(Path(root) / relative)
    expected = _lexical_absolute(Path(root) / expected_relative)
    if lexical != expected:
        raise NullModelError(
            role + "_identity",
            "lexical path is not the authorised repository location",
        )
    try:
        observed_relative = lexical.relative_to(root_lexical).as_posix()
    except ValueError:
        raise NullModelError(
            role + "_identity",
            "path escapes the repository root",
        )
    if observed_relative != expected_relative:
        raise NullModelError(
            role + "_identity",
            "repository-relative location is not authorised",
        )
    _assert_regular_nonsymlink(lexical, role)
    return lexical


def resolve_fixed_train_text():
    """Confirm the pinned TRAIN_TEXT path, then lstat. Do not open it here."""
    expected = Path("/home/laura/rnagenesis-mres-data/development/corpus_final.txt")
    lexical = _lexical_absolute(AUTHORIZED_TRAIN_TEXT_PATH)
    if lexical != expected:
        raise NullModelError(
            "train_identity",
            "TRAIN_TEXT path is not the pinned production path",
        )
    _assert_regular_nonsymlink(lexical, "train")
    return lexical


def _assert_regular_nonsymlink(path, role):
    try:
        info = os.lstat(str(path))
    except OSError:
        raise NullModelError(
            role + "_missing",
            "required path is missing or not a regular file",
        )
    if stat.S_ISLNK(info.st_mode):
        raise NullModelError(role + "_symlink", "required path is a symlink")
    if not stat.S_ISREG(info.st_mode):
        raise NullModelError(
            role + "_not_regular",
            "required path is missing or not a regular file",
        )


def validate_output_containment(path, run_root):
    """Refuse any output that is not a new child of run_root. Do not create it."""
    if path is None or str(path) == "":
        raise NullModelError(
            "output_directory_required",
            "an output directory must be supplied explicitly",
        )
    raw = Path(path)
    if not raw.is_absolute():
        raise NullModelError(
            "output_path_not_absolute",
            "output directory must be an absolute path",
        )
    if any(part == ".." for part in raw.parts):
        raise NullModelError(
            "output_path_escapes_root",
            "output path must not contain '..'",
        )
    lexical_root = _lexical_absolute(run_root)
    lexical = _lexical_absolute(raw)
    if lexical == lexical_root or not _is_relative_to(lexical, lexical_root):
        raise NullModelError(
            "output_not_a_child",
            "output directory must be a new child of the run root",
        )
    try:
        root_real = Path(os.path.realpath(str(run_root)))
    except OSError:
        raise NullModelError("run_root_unusable", "run root could not be resolved")
    if not root_real.is_dir():
        raise NullModelError("run_root_missing", "run root does not exist")
    parent = raw.parent
    try:
        parent_real = Path(os.path.realpath(str(parent)))
        candidate_real = Path(os.path.realpath(str(raw)))
    except OSError:
        raise NullModelError("output_path_unusable", "output path could not be resolved")
    parent_is_link = os.path.islink(str(parent))
    if parent_is_link and (
        parent_real == root_real or not _is_relative_to(parent_real, root_real)
        or candidate_real == root_real
        or not _is_relative_to(candidate_real, root_real)
    ):
        raise NullModelError(
            "output_symlink_escape",
            "output parent symlink escapes the run root",
        )
    if candidate_real == root_real or not _is_relative_to(candidate_real, root_real):
        raise NullModelError(
            "output_not_a_child",
            "output directory must be a new child of the run root",
        )
    if not _is_relative_to(parent_real, root_real) and parent_real != root_real:
        raise NullModelError(
            "output_symlink_escape",
            "output parent symlink escapes the run root",
        )
    for part in lexical.parts:
        if part.lower() in AMBIGUOUS_OUTPUT_NAMES:
            raise NullModelError(
                "ambiguous_output_name",
                "output path uses an ambiguous directory name",
            )
    if lexical.exists() or os.path.lexists(str(lexical)):
        raise NullModelError(
            "output_directory_exists",
            "output path already exists; refusing to overwrite or append",
        )
    if not parent_real.is_dir():
        raise NullModelError(
            "output_parent_missing",
            "output parent does not exist; parent directories are not created",
        )
    return lexical


def create_output_directory(path):
    try:
        os.mkdir(str(path))
    except FileExistsError:
        raise NullModelError(
            "output_directory_exists",
            "output path already exists; refusing to overwrite or append",
        )
    except FileNotFoundError:
        raise NullModelError(
            "output_parent_missing",
            "output parent does not exist; parent directories are not created",
        )
    except OSError:
        raise NullModelError(
            "output_directory_unusable",
            "output directory could not be created",
        )


def exclusive_fsync_write(path, data):
    """Create exclusively, write every byte, fsync, then close."""
    if not isinstance(data, (bytes, bytearray)):
        raise NullModelError("output_type", "output payload must be bytes")
    data = bytes(data)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(str(path), flags, 0o644)
    except FileExistsError:
        raise NullModelError(
            "output_file_exists",
            "refusing to overwrite or append to an existing file",
        )
    except OSError:
        raise NullModelError("output_unwritable", "output file could not be created")
    try:
        view = memoryview(data)
        while len(view) > 0:
            try:
                written = os.write(descriptor, view)
            except OSError:
                raise NullModelError("output_write_failed", "output write failed")
            if written <= 0:
                raise NullModelError(
                    "output_short_write",
                    "os.write returned zero bytes",
                )
            view = view[written:]
        try:
            os.fsync(descriptor)
        except OSError:
            raise NullModelError("output_fsync_failed", "output fsync failed")
    finally:
        os.close(descriptor)


def reread_closed_file(path, intended):
    """Hash the bytes re-read after the file descriptor has been closed."""
    try:
        observed = Path(path).read_bytes()
    except OSError:
        raise NullModelError(
            "output_reread_failed",
            "closed output could not be re-read",
        )
    if observed != intended:
        raise NullModelError(
            "output_reread_mismatch",
            "re-read bytes do not equal the intended canonical bytes",
        )
    return observed, _sha256_bytes(observed)


def write_failure_status(directory, error):
    code = error.code if isinstance(error, NullModelError) else "unexpected_error"
    detail = (
        error.detail
        if isinstance(error, NullModelError)
        else "run failed after directory creation"
    )
    payload = {
        "status": "FAILED",
        "error_code": code,
        "error_detail": detail,
        "scientific_run_completed": False,
        "overwrite": False,
    }
    exclusive_fsync_write(
        Path(directory) / "failure_status.json",
        canonical_json_document(payload),
    )


def _read_logged(path, role, access_log):
    if role in ("REF", "EVAL"):
        raise NullModelError(
            "ref_eval_access_prohibited",
            "REF and EVAL must not be opened",
        )
    if role == "TRAIN_TEXT":
        reject_prohibited_input_path(path, "TRAIN_TEXT")
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError:
        raise NullModelError("input_unreadable", "required file could not be read")
    access_log.append(
        {
            "path": str(path),
            "role": role,
            "byte_count": len(data),
        }
    )
    return data


def _refuse_test_only_production_targets(test_only):
    """Path refusals run before any biological file is opened."""
    if not isinstance(test_only, TestOnlySyntheticFixture):
        raise NullModelError(
            "test_only_type",
            "test-only authorization must use TestOnlySyntheticFixture",
        )
    if (
        test_only.token != TEST_ONLY_TOKEN
        or test_only.purpose != "synthetic_unit_test_not_a_biological_run"
    ):
        raise NullModelError(
            "test_only_token",
            "test-only fixture token was not recognised",
        )
    config_path = _lexical_absolute(test_only.config_path)
    repo_config = _lexical_absolute(
        production_repository_root() / B2_CONFIG_RELATIVE
    )
    if config_path == repo_config:
        raise NullModelError(
            "test_only_cannot_authorise_repository_config",
            "the repository B2 configuration cannot be executed through the test-only path",
        )
    input_path = _lexical_absolute(test_only.input_path)
    data_root = _lexical_absolute(BIOLOGICAL_DATA_ROOT)
    train_path = _lexical_absolute(AUTHORIZED_TRAIN_TEXT_PATH)
    if input_path == train_path:
        raise NullModelError(
            "test_only_biological_input",
            "test-only mode refuses the production TRAIN_TEXT path",
        )
    if input_path == data_root or _is_relative_to(input_path, data_root):
        raise NullModelError(
            "test_only_biological_input",
            "test-only mode refuses the biological development root",
        )
    run_root = _lexical_absolute(test_only.run_root)
    runs = _lexical_absolute(PRODUCTION_RUN_ROOT)
    if run_root == runs or _is_relative_to(run_root, runs):
        raise NullModelError(
            "test_only_production_run_root",
            "test-only mode refuses the production run root",
        )
    for label, candidate in (
        ("fixture_root", test_only.fixture_root),
        ("contract_path", test_only.contract_path),
        ("config_path", test_only.config_path),
    ):
        candidate_path = _lexical_absolute(candidate)
        if candidate_path == data_root or _is_relative_to(candidate_path, data_root):
            raise NullModelError(
                "test_only_biological_input",
                "test-only mode refuses the biological development root",
            )
        if candidate_path == runs or _is_relative_to(candidate_path, runs):
            raise NullModelError(
                "test_only_production_run_root",
                "test-only mode refuses the production run root",
            )
        if label == "contract_path" and candidate_path == train_path:
            raise NullModelError(
                "test_only_biological_input",
                "test-only mode refuses the production TRAIN_TEXT path",
            )


def refuse_test_only_train_hash(actual_sha256):
    if actual_sha256 == TRAIN_TEXT_SHA256:
        raise NullModelError(
            "biological_hash_refused_in_test_only",
            "test-only mode refuses the production TRAIN_TEXT hash",
        )


def _expected_histogram_from_config(config):
    block = config.get("expected_empirical_length_counts")
    if not isinstance(block, dict) or "counts" not in block:
        raise NullModelError(
            "expected_histogram_missing",
            "production configuration is missing the expected length histogram",
        )
    return {int(key): int(value) for key, value in block["counts"].items()}


def _assert_histogram_match(stats, expected_counts):
    observed = {
        int(item["length"]): int(item["count"])
        for item in stats["complete_length_histogram"]
        if int(item["count"]) > 0
    }
    if observed != expected_counts:
        raise NullModelError(
            "length_histogram_mismatch",
            "recomputed length histogram does not match the configured expected counts",
        )


def parse_contract_bytes(raw):
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise NullModelError(
            "contract_encoding",
            "frozen contract must be UTF-8 without a BOM or carriage return",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise NullModelError("contract_encoding", "frozen contract is not valid UTF-8")
    try:
        loaded = json.loads(text)
    except ValueError:
        raise NullModelError("contract_parse", "frozen contract could not be parsed")
    if not isinstance(loaded, dict):
        raise NullModelError("contract_shape", "frozen contract root must be an object")
    return loaded


def verify_frozen_contract_semantics(document, expected_train_sha256):
    if document.get("contract_id") != "rnagenesis_corrected_669_core_m0":
        raise NullModelError(
            "frozen_contract_id",
            "frozen contract id is not authorised",
        )
    roles = document.get("roles")
    if not isinstance(roles, dict):
        raise NullModelError(
            "frozen_contract_roles",
            "frozen contract is missing roles",
        )
    train = roles.get("TRAIN_TEXT")
    if not isinstance(train, dict):
        raise NullModelError("train_text_role_missing", "TRAIN_TEXT role is missing")
    allowed = train.get("allowed")
    if (
        not isinstance(allowed, list)
        or "fit" not in allowed
        or train.get("authoritative_rnagenesis_fitting_input") is not True
    ):
        raise NullModelError(
            "train_text_not_authorised_for_fitting",
            "TRAIN_TEXT is not authorised for fitting",
        )
    if train.get("sha256") != expected_train_sha256:
        raise NullModelError(
            "train_text_contract_hash",
            "TRAIN_TEXT hash recorded in the contract does not match the expected hash",
        )
    access = document.get("access_policy")
    if not isinstance(access, dict):
        raise NullModelError(
            "frozen_contract_access",
            "frozen contract is missing access policy",
        )
    allowlist = access.get("development_read_allowlist")
    if not isinstance(allowlist, list):
        raise NullModelError(
            "frozen_contract_access",
            "frozen contract is missing the development read allowlist",
        )
    for role_name in ("REF", "EVAL"):
        if role_name in allowlist:
            raise NullModelError(
                "ref_eval_not_b2_input",
                "REF and EVAL are not authorised B2 inputs",
            )
        role = roles.get(role_name)
        if not isinstance(role, dict):
            raise NullModelError(
                "ref_eval_role_missing",
                "REF or EVAL role is missing",
            )
        role_allowed = role.get("allowed") or []
        if (
            "fit" in role_allowed
            or role.get("available_during_generator_development") is not False
        ):
            raise NullModelError(
                "ref_eval_not_b2_input",
                "REF and EVAL are not authorised B2 inputs",
            )


def _assert_production_config_contract(config):
    if config.get("biological_run", True) is False or config.get(
        "test_only_synthetic_fixture", False
    ):
        raise NullModelError(
            "production_refuses_synthetic_config",
            "production mode refuses a synthetic fixture configuration",
        )
    block = config.get("input") if isinstance(config.get("input"), dict) else {}
    sampler = config.get("sampler") if isinstance(config.get("sampler"), dict) else {}
    if block.get("expected_sha256") != TRAIN_TEXT_SHA256:
        raise NullModelError(
            "production_input_contract",
            "production configuration TRAIN hash is not the pinned hash",
        )
    if block.get("expected_sequence_count") != EXPECTED_SEQUENCE_COUNT:
        raise NullModelError(
            "production_input_contract",
            "production configuration sequence count is not 669",
        )
    if block.get("expected_unique_count") != EXPECTED_UNIQUE_COUNT:
        raise NullModelError(
            "production_input_contract",
            "production configuration unique count is not 669",
        )
    if sampler.get("seed") != DEFAULT_SEED or sampler.get("raw_sequence_count") != DEFAULT_ATTEMPT_COUNT:
        raise NullModelError(
            "production_parameters",
            "production runs use 30000 attempts and seed 42",
        )


def _synthetic_parameters(config, test_only):
    if (
        config.get("test_only_synthetic_fixture") is not True
        or config.get("biological_run") is not False
    ):
        raise NullModelError(
            "test_only_config_marker",
            "test-only execution requires test_only_synthetic_fixture true and biological_run false",
        )
    block = config.get("input") if isinstance(config.get("input"), dict) else {}
    sampler = config.get("sampler") if isinstance(config.get("sampler"), dict) else {}
    expected_sha = block.get("expected_sha256")
    expected_count = block.get("expected_sequence_count")
    expected_unique = block.get("expected_unique_count")
    if (
        not isinstance(expected_sha, str)
        or isinstance(expected_count, bool)
        or not isinstance(expected_count, int)
        or isinstance(expected_unique, bool)
        or not isinstance(expected_unique, int)
    ):
        raise NullModelError(
            "test_only_contract",
            "test-only config is missing the synthetic input contract",
        )
    refuse_test_only_train_hash(expected_sha)
    if isinstance(test_only.attempt_count, bool) or not isinstance(test_only.attempt_count, int):
        raise NullModelError("test_only_parameters", "test-only attempt count must be an integer")
    if isinstance(test_only.seed, bool) or not isinstance(test_only.seed, int):
        raise NullModelError("test_only_parameters", "test-only seed must be an integer")
    if (
        sampler.get("seed") != test_only.seed
        or sampler.get("raw_sequence_count") != test_only.attempt_count
    ):
        raise NullModelError(
            "test_only_parameters",
            "test-only seed and count must match the synthetic configuration",
        )
    return (
        expected_sha,
        expected_count,
        expected_unique,
        test_only.attempt_count,
        test_only.seed,
    )


def _required_config_text(config, key):
    value = config.get(key)
    if not isinstance(value, str) or value == "":
        raise NullModelError(
            "config_field_missing",
            "configuration is missing a required field",
        )
    return value


def _preserve_original_after_secondary(primary, secondary):
    if isinstance(secondary, NullModelError):
        secondary_code = secondary.code
        secondary_detail = secondary.detail
    else:
        secondary_code = "failure_status_unwritable"
        secondary_detail = "failure status could not be written"
    primary.secondary_failure = {
        "code": secondary_code,
        "detail": secondary_detail,
    }
    sys.stderr.write(
        "secondary_failure: {}: {}\n".format(secondary_code, secondary_detail)
    )
    raise primary from secondary


def _open_verified_contract(contract_path, access_log, expected_contract_sha256, expected_train_sha256):
    _assert_regular_nonsymlink(contract_path, "contract")
    contract_bytes = _read_logged(contract_path, "FROZEN_CONTRACT", access_log)
    observed_sha = _sha256_bytes(contract_bytes)
    if observed_sha != expected_contract_sha256:
        raise NullModelError(
            "frozen_contract_hash",
            "frozen contract SHA-256 does not match the expected hash",
        )
    document = parse_contract_bytes(contract_bytes)
    verify_frozen_contract_semantics(document, expected_train_sha256)
    return document, observed_sha


def _execute_b2(output_dir, command, test_only):
    """Shared body. Production calls this with test_only None and pinned paths."""
    started_at = datetime.now(timezone.utc).astimezone().isoformat()
    access_log = []
    gpu_api_invoked = False
    if test_only is None:
        root = production_repository_root()
        config_path = resolve_fixed_repository_file(root, B2_CONFIG_RELATIVE, "config")
        run_root = PRODUCTION_RUN_ROOT
        synthetic = False
    else:
        _refuse_test_only_production_targets(test_only)
        config_path = _lexical_absolute(test_only.config_path)
        _assert_regular_nonsymlink(config_path, "config")
        run_root = _lexical_absolute(test_only.run_root)
        synthetic = True

    config_bytes = _read_logged(config_path, "B2_CONFIG", access_log)
    config_sha256 = _sha256_bytes(config_bytes)
    config = load_b2_config_bytes(config_bytes)
    assert_execution_authorised(config)

    if synthetic:
        (
            expected_sha,
            expected_count,
            expected_unique,
            attempt_count,
            seed,
        ) = _synthetic_parameters(config, test_only)
        expected_contract_sha = test_only.expected_contract_sha256
        if not isinstance(expected_contract_sha, str) or expected_contract_sha == "":
            raise NullModelError(
                "test_only_contract",
                "test-only fixture is missing the expected contract hash",
            )
        contract_path = _lexical_absolute(test_only.contract_path)
        resolved_output = None
    else:
        _assert_production_config_contract(config)
        resolved_output = assert_scientific_execution_authorisation(
            config,
            output_dir,
        )
        expected_sha = TRAIN_TEXT_SHA256
        expected_count = EXPECTED_SEQUENCE_COUNT
        expected_unique = EXPECTED_UNIQUE_COUNT
        attempt_count = DEFAULT_ATTEMPT_COUNT
        seed = DEFAULT_SEED
        expected_contract_sha = FROZEN_CONTRACT_SHA256
        contract_path = resolve_fixed_repository_file(
            production_repository_root(),
            FROZEN_CONTRACT_RELATIVE,
            "contract",
        )

    contract, contract_sha256 = _open_verified_contract(
        contract_path,
        access_log,
        expected_contract_sha,
        expected_sha,
    )
    if synthetic:
        recorded_train_sha = contract.get("roles", {}).get("TRAIN_TEXT", {}).get("sha256")
        refuse_test_only_train_hash(recorded_train_sha)
        refuse_test_only_train_hash(expected_sha)

    if resolved_output is None:
        resolved_output = validate_output_containment(output_dir, run_root)

    if synthetic:
        train_path = _lexical_absolute(test_only.input_path)
        _assert_regular_nonsymlink(train_path, "train")
    else:
        train_path = resolve_fixed_train_text()

    raw_input = _read_logged(train_path, "TRAIN_TEXT", access_log)
    actual_sha = _sha256_bytes(raw_input)
    if synthetic:
        refuse_test_only_train_hash(actual_sha)
    enforce_sha256(actual_sha, expected_sha)
    sequences = parse_train_text_bytes(raw_input)
    unique_count = enforce_sequence_contract(sequences, expected_count, expected_unique)
    stats = compute_corpus_statistics(sequences)
    if (not synthetic) or ("expected_empirical_length_counts" in config):
        _assert_histogram_match(stats, _expected_histogram_from_config(config))

    approval = approval_from_config(config, config_sha256)
    experiment_id = _required_config_text(config, "experiment_id")
    condition_identifier = _required_config_text(config, "condition_manifest_label")
    schema_version = _required_config_text(config, "schema_version")

    create_output_directory(resolved_output)
    try:
        if synthetic and test_only.fail_after_directory_creation:
            raise NullModelError(
                "injected_test_failure",
                "synthetic failure after directory creation; not a biological run",
            )
        freqs = frequencies_from_probabilities(stats["probabilities"])
        records = build_raw_records(attempt_count, freqs, stats["lengths"], seed)
        if len(records) != attempt_count:
            raise NullModelError(
                "retention_mismatch",
                "retained count does not equal the requested attempt count",
            )
        jsonl = serialize_jsonl(records)
        raw_path = resolved_output / RAW_JSONL_FILENAME
        exclusive_fsync_write(raw_path, jsonl)
        observed_bytes, observed_sha = reread_closed_file(raw_path, jsonl)
        ended_at = datetime.now(timezone.utc).astimezone().isoformat()
        deviations = []
        if synthetic:
            deviations.append("test_only_synthetic_fixture_not_a_biological_run")
        git_info = collect_git_provenance(production_repository_root())
        manifest = build_observed_success_manifest(
            {
                "approval": approval,
                "git": git_info,
                "stats": stats,
                "access_log": access_log,
                "attempt_count": attempt_count,
                "retained_count": len(records),
                "schema_version": schema_version,
                "experiment_id": experiment_id,
                "condition_identifier": condition_identifier,
                "run_identifier": resolved_output.name,
                "attempt_identifier": "invocation-0",
                "started_at": started_at,
                "ended_at": ended_at,
                "hostname": socket.gethostname(),
                "frozen_corpus_commit": contract.get("corpus_commit"),
                "config_path": str(config_path),
                "config_sha256": config_sha256,
                "contract_path": str(contract_path),
                "contract_sha256": contract_sha256,
                "input_path": str(train_path),
                "expected_input_sha256": expected_sha,
                "actual_input_sha256": actual_sha,
                "expected_sequence_count": expected_count,
                "actual_sequence_count": len(sequences),
                "expected_unique_count": expected_unique,
                "actual_unique_count": unique_count,
                "seed": seed,
                "unique_count_diagnostic": unique_count_diagnostic(records),
                "command": command,
                "output_path": str(raw_path),
                "output_byte_count": len(observed_bytes),
                "output_sha256": observed_sha,
                "warnings": [],
                "retries": [],
                "deviations": deviations,
                "stopping_reason": "completed_sampling_and_wrote_closed_output",
                "gpu_api_invoked": gpu_api_invoked,
            }
        )
        manifest_bytes = serialize_manifest(manifest)
        manifest_path = resolved_output / "manifest.json"
        exclusive_fsync_write(manifest_path, manifest_bytes)
        reread_closed_file(manifest_path, manifest_bytes)
    except Exception as exc:
        if isinstance(exc, NullModelError):
            primary = exc
        else:
            primary = NullModelError(
                "unexpected_error",
                "run failed after directory creation",
            )
        try:
            write_failure_status(resolved_output, primary)
        except Exception as secondary:
            _preserve_original_after_secondary(primary, secondary)
        raise primary
    return {
        "output_dir": str(resolved_output),
        "raw_sha256": observed_sha,
        "access_log": access_log,
        "retained_count": len(records),
    }


def run_b2_production(output_dir, command=None):
    """Production entry point. Paths, seed, and count are pinned in this module."""
    if command is None:
        command = " ".join(sys.argv)
    return _execute_b2(output_dir, command=command, test_only=None)


def execute_test_only_synthetic(test_only, output_dir, command=None):
    """Synthetic executor. Not called by the CLI and not enabled by the environment."""
    _refuse_test_only_production_targets(test_only)
    if command is None:
        command = "synthetic-test-only"
    return _execute_b2(output_dir, command=command, test_only=test_only)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="null_model")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    command_args = sys.argv if argv is None else ["null_model"] + list(argv)
    try:
        run_b2_production(args.output_dir, command=" ".join(command_args))
    except NullModelError as exc:
        sys.stderr.write("{}: {}\n".format(exc.code, exc.detail))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

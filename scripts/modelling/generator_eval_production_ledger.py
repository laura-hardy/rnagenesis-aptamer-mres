#!/usr/bin/env python3
"""Deterministic production ledger for the frozen M9 parser.

The controlling inputs are the frozen source manifest and an output directory.
File access is limited to the B0, B1, B2, and D1 artifacts named by that
manifest. SHA-256 is recomputed from the file bytes before any row is
accepted. Biological parsing is the committed source-adapter path. This
module does not replenish, filter, deduplicate, drop, or rewrite sources.
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

from generator_eval_derived_ledger import DERIVED_FIELDS
from generator_eval_parser import (
    FAILURE_REASONS,
    OUTCOMES,
    PARSER_CONTRACT_SCHEMA,
    PARSER_VERSION,
    ParserContractError,
    SOURCE_MANIFEST_SCHEMA,
)
from generator_eval_source_adapters import (
    ADAPTER_VERSION,
    B0_NOMINAL_MAX_SEQ_LEN,
    adapt_b0,
    adapt_b1,
    adapt_b2,
    adapt_d1,
)

PRODUCTION_LEDGER_SCHEMA = "generator-eval-production-ledger-m9-r1"
ACCOUNTING_SCHEMA = "generator-eval-parsing-accounting-m9-r1"
MANIFEST_SCHEMA = "generator-eval-production-manifest-m9-r1"
CONDITION_ORDER = ("B0", "B1", "B2", "D1")
PRODUCTION_ATTEMPT_COUNTS = {"B0": 30080, "B1": 30000, "B2": 30000, "D1": 30000}
PRODUCTION_COMBINED_ROWS = 120080
PRODUCTION_D1_SEED_COUNTS = {43: 15000, 44: 15000}
CONTRACT_RELATIVE_PATH = "config/modelling/generator_eval_parser_contract.json"
ROW_EXTENSION_FIELDS = (
    "ledger_schema",
    "is_valid_canonical",
    "valid_sequence_multiplicity",
    "is_exact_duplicate_within_condition",
)
PRODUCTION_ROW_FIELDS = DERIVED_FIELDS + ROW_EXTENSION_FIELDS
OUTPUT_NAMES = {
    "B0": "m9_b0_derived_attempt_ledger.jsonl",
    "B1": "m9_b1_derived_attempt_ledger.jsonl",
    "B2": "m9_b2_derived_attempt_ledger.jsonl",
    "D1": "m9_d1_derived_attempt_ledger.jsonl",
    "combined": "m9_all_conditions_derived_attempt_ledger.jsonl",
    "summary": "m9_parsing_accounting_summary.json",
    "manifest": "m9_production_manifest.json",
}
FORBIDDEN_PATH_COMPONENTS = frozenset(("TRAIN", "VALIDATION", "REF", "EVAL"))
FORBIDDEN_BASENAMES = frozenset(
    ("corpus_final.txt", "ft_train.csv", "ft_validation.csv", "ref.csv", "eval.csv")
)
B0_LOGICAL_FILES = (
    (
        "b0:chunk:1:seed:4201",
        "results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk1_seed4201_steps50_batch16_batchnum188_gpu1.txt",
    ),
    (
        "b0:chunk:2:seed:4202",
        "results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk2_seed4202_steps50_batch16_batchnum188_gpu1.txt",
    ),
    (
        "b0:chunk:3:seed:4203",
        "results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk3_seed4203_steps50_batch16_batchnum188_gpu1.txt",
    ),
    (
        "b0:chunk:4:seed:4204",
        "results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk4_seed4204_steps50_batch16_batchnum188_gpu1.txt",
    ),
    (
        "b0:chunk:5:seed:4205",
        "results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk5_seed4205_steps50_batch16_batchnum188_gpu1.txt",
    ),
    (
        "b0:chunk:6:seed:4206",
        "results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk6_seed4206_steps50_batch16_batchnum188_gpu1.txt",
    ),
    (
        "b0:chunk:7:seed:4207",
        "results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk7_seed4207_steps50_batch16_batchnum188_gpu1.txt",
    ),
    (
        "b0:chunk:8:seed:4208",
        "results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk8_seed4208_steps50_batch16_batchnum188_gpu1.txt",
    ),
    (
        "b0:chunk:9:seed:4209",
        "results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk9_seed4209_steps50_batch16_batchnum188_gpu1.txt",
    ),
    (
        "b0:chunk:10:seed:4210",
        "results/phase4_1_unadapted_rnagenesis_30k/raw/seqs_wo_guidance_top_p=0.95_2_3008_h200_baseline_30k_chunk10_seed4210_steps50_batch16_batchnum188_gpu1.txt",
    ),
)
SEALED_SINGLE_FILES = {
    "B1": (
        "b1:m8-combined-raw-attempt-ledger",
        "/home/laura/rnagenesis-mres-runs/m8_b1_combined_1069b63_cpu_attempt1/m8_combined_raw_attempt_ledger.jsonl",
    ),
    "B2": (
        "b2:empirical-null-raw-jsonl",
        "/home/laura/rnagenesis-mres-runs/m4_b2_empirical_null_6f82878_attempt2/b2_empirical_null_raw.jsonl",
    ),
    "D1": (
        "d1:m8-combined-raw-attempt-ledger",
        "/home/laura/rnagenesis-mres-runs/m8_d1_combined_1069b63_cpu_attempt1/m8_combined_raw_attempt_ledger.jsonl",
    ),
}


class ProductionLedgerError(ValueError):
    """The production ledger run failed closed."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(code + ": " + detail)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _is_sha256(value):
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _read_regular_file(path):
    """Read one regular file. Do not follow a symlink at the final path."""
    text = os.fspath(path)
    parts = text.replace("\\", "/").split("/")
    if any(part in FORBIDDEN_PATH_COMPONENTS for part in parts):
        raise ProductionLedgerError("protected_path_refused", "a protected data role is not an input")
    if parts[-1] in FORBIDDEN_BASENAMES:
        raise ProductionLedgerError("protected_path_refused", "a protected corpus filename is not an input")
    try:
        descriptor = os.open(text, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise ProductionLedgerError("source_missing", "a sealed source is missing") from error
    except OSError as error:
        raise ProductionLedgerError("source_unreadable", "a sealed source could not be read") from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ProductionLedgerError("source_unreadable", "a sealed source is not a regular file")
        chunks = []
        while True:
            blob = os.read(descriptor, 1024 * 1024)
            if blob == b"":
                break
            chunks.append(blob)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _load_json_bytes(blob, label):
    try:
        value = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProductionLedgerError("manifest_invalid", label + " is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ProductionLedgerError("manifest_invalid", label + " is not an object")
    return value


def _git_head(root):
    completed = subprocess.run(
        ["git", "-C", root, "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ProductionLedgerError("runner_commit_unavailable", "the runner git commit could not be read")
    commit = completed.stdout.strip()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise ProductionLedgerError("runner_commit_unavailable", "the runner git commit is not a full sha")
    return commit


def _contract_identity(root):
    path = os.path.join(root, CONTRACT_RELATIVE_PATH)
    blob = _read_regular_file(path)
    document = _load_json_bytes(blob, "the parser contract")
    if document.get("schema_version") != PARSER_CONTRACT_SCHEMA:
        raise ProductionLedgerError("parser_contract_mismatch", "the parser contract schema is not the committed revision")
    if document.get("adapter_version") != ADAPTER_VERSION:
        raise ProductionLedgerError("parser_contract_mismatch", "the parser contract adapter revision drifted")
    if document.get("parser_version") != PARSER_VERSION:
        raise ProductionLedgerError("parser_contract_mismatch", "the biological parser version drifted")
    return {
        "schema": PARSER_CONTRACT_SCHEMA,
        "relative_path": CONTRACT_RELATIVE_PATH,
        "sha256": _sha256(blob),
        "parser_version": PARSER_VERSION,
        "adapter_version": ADAPTER_VERSION,
    }


def _require_attempt_count(value, label):
    if type(value) is not int or value < 0:
        raise ProductionLedgerError("manifest_invalid", label + " attempt count is not a nonnegative integer")
    return value


def _seed_allocation(condition):
    allocation = condition.get("seed_allocation")
    if type(allocation) is not list or not allocation:
        raise ProductionLedgerError("manifest_invalid", "D1 seed allocation is missing")
    parsed = []
    seen = set()
    for item in allocation:
        if not isinstance(item, dict):
            raise ProductionLedgerError("manifest_invalid", "a D1 seed allocation entry is not an object")
        seed = item.get("d1_training_seed")
        attempts = item.get("attempts")
        if type(seed) is not int or seed < 0:
            raise ProductionLedgerError("manifest_invalid", "a D1 training seed is not a nonnegative integer")
        attempts = _require_attempt_count(attempts, "D1 seed")
        if seed in seen:
            raise ProductionLedgerError("manifest_invalid", "a D1 training seed is duplicated in the allocation")
        seen.add(seed)
        entry = {"d1_training_seed": seed, "attempts": attempts}
        if "technical_block" in item:
            entry["technical_block"] = item["technical_block"]
        parsed.append(entry)
    return parsed


def validate_source_manifest(document):
    """Check the identity fields the runner reads. Do not open the named sources."""
    if not isinstance(document, dict):
        raise ProductionLedgerError("manifest_invalid", "the source manifest is not an object")
    if document.get("schema_version") != SOURCE_MANIFEST_SCHEMA:
        raise ProductionLedgerError("manifest_invalid", "the source manifest schema is not the frozen revision")
    conditions = document.get("conditions")
    if not isinstance(conditions, dict) or set(conditions) != set(CONDITION_ORDER):
        raise ProductionLedgerError("manifest_invalid", "the source manifest conditions are not B0, B1, B2, and D1")
    normalised = {}
    for condition_name in CONDITION_ORDER:
        condition = conditions[condition_name]
        if not isinstance(condition, dict):
            raise ProductionLedgerError("manifest_invalid", condition_name + " is not an object")
        logical_id = condition.get("logical_artifact_id")
        if type(logical_id) is not str or logical_id == "" or "/" in logical_id or "\\" in logical_id:
            raise ProductionLedgerError("manifest_invalid", condition_name + " logical artifact id is not a token")
        attempt_count = _require_attempt_count(condition.get("attempt_count"), condition_name)
        normalised[condition_name] = {
            "logical_artifact_id": logical_id,
            "attempt_count": attempt_count,
        }
    b0 = conditions["B0"]
    chunks = b0.get("source_chunks")
    if type(chunks) is not list or not chunks:
        raise ProductionLedgerError("manifest_invalid", "B0 source chunks are missing")
    concatenation = b0.get("numeric_raw_concatenation_sha256")
    if not _is_sha256(concatenation):
        raise ProductionLedgerError("manifest_invalid", "the B0 concatenation hash is missing")
    parsed_chunks = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ProductionLedgerError("manifest_invalid", "a B0 chunk is not an object")
        logical_id = chunk.get("logical_artifact_id")
        digest = chunk.get("raw_sha256")
        seed = chunk.get("seed")
        if type(logical_id) is not str or logical_id == "" or "/" in logical_id:
            raise ProductionLedgerError("manifest_invalid", "a B0 chunk id is not a token")
        if not _is_sha256(digest):
            raise ProductionLedgerError("manifest_invalid", "a B0 chunk hash is not lowercase sha256")
        if type(seed) is not int or seed < 0:
            raise ProductionLedgerError("manifest_invalid", "a B0 chunk seed is not a nonnegative integer")
        parsed_chunks.append(
            {"logical_artifact_id": logical_id, "raw_sha256": digest, "seed": seed}
        )
    normalised["B0"]["source_chunks"] = parsed_chunks
    normalised["B0"]["numeric_raw_concatenation_sha256"] = concatenation
    for condition_name, field_name in (("B1", "combined_ledger_sha256"), ("D1", "combined_ledger_sha256"), ("B2", "raw_jsonl_sha256")):
        digest = conditions[condition_name].get(field_name)
        if not _is_sha256(digest):
            raise ProductionLedgerError("manifest_invalid", condition_name + " source hash is not lowercase sha256")
        normalised[condition_name]["sha256"] = digest
    normalised["D1"]["seed_allocation"] = _seed_allocation(conditions["D1"])
    return normalised


def sealed_source_locator(document, root=REPO_ROOT):
    """Return paths for the sealed logical ids. Do not open those paths."""
    manifest = validate_source_manifest(document)
    expected_ids = [item[0] for item in B0_LOGICAL_FILES]
    observed_ids = [chunk["logical_artifact_id"] for chunk in manifest["B0"]["source_chunks"]]
    if observed_ids != expected_ids:
        raise ProductionLedgerError("source_identity_invalid", "B0 chunk identities are not the sealed set")
    locator = {"B0": {}}
    for logical_id, relative_path in B0_LOGICAL_FILES:
        locator["B0"][logical_id] = os.path.join(root, relative_path)
    for condition_name, (logical_id, path) in SEALED_SINGLE_FILES.items():
        if manifest[condition_name]["logical_artifact_id"] != logical_id:
            raise ProductionLedgerError("source_identity_invalid", condition_name + " identity is not the sealed artifact")
        locator[condition_name] = {logical_id: path}
    return locator


def _locator_path(locator, condition_name, logical_id):
    condition = locator.get(condition_name) if isinstance(locator, dict) else None
    if not isinstance(condition, dict) or logical_id not in condition:
        raise ProductionLedgerError("source_missing", "the manifest artifact has no locator")
    return condition[logical_id]


def _verify_bytes(path, expected, logical_id):
    try:
        blob = _read_regular_file(path)
    except ProductionLedgerError as error:
        if error.code == "source_missing":
            raise ProductionLedgerError("source_missing", logical_id + " is missing") from error
        raise
    digest = _sha256(blob)
    if digest != expected:
        raise ProductionLedgerError("source_hash_mismatch", logical_id + " hash does not match the manifest")
    return blob, digest


def _load_sources(manifest, locator):
    """Hash every sealed input before any adapter sees a row."""
    inputs = []
    b0_blobs = []
    for chunk in manifest["B0"]["source_chunks"]:
        path = _locator_path(locator, "B0", chunk["logical_artifact_id"])
        blob, digest = _verify_bytes(path, chunk["raw_sha256"], chunk["logical_artifact_id"])
        b0_blobs.append(blob)
        inputs.append(
            {
                "condition": "B0",
                "logical_artifact_id": chunk["logical_artifact_id"],
                "expected_sha256": chunk["raw_sha256"],
                "recomputed_sha256": digest,
                "byte_count": len(blob),
            }
        )
    concatenation = b"".join(b0_blobs)
    concatenation_digest = _sha256(concatenation)
    if concatenation_digest != manifest["B0"]["numeric_raw_concatenation_sha256"]:
        raise ProductionLedgerError("source_hash_mismatch", "the B0 concatenation hash does not match the manifest")
    singles = {}
    for condition_name in ("B1", "B2", "D1"):
        logical_id = manifest[condition_name]["logical_artifact_id"]
        path = _locator_path(locator, condition_name, logical_id)
        blob, digest = _verify_bytes(path, manifest[condition_name]["sha256"], logical_id)
        singles[condition_name] = blob
        inputs.append(
            {
                "condition": condition_name,
                "logical_artifact_id": logical_id,
                "expected_sha256": manifest[condition_name]["sha256"],
                "recomputed_sha256": digest,
                "byte_count": len(blob),
            }
        )
    return {
        "inputs": inputs,
        "b0_blobs": b0_blobs,
        "singles": singles,
        "b0_concatenation_sha256": concatenation_digest,
    }


def _adapt_all(manifest, loaded):
    rows = {condition_name: [] for condition_name in CONDITION_ORDER}
    for chunk, blob in zip(manifest["B0"]["source_chunks"], loaded["b0_blobs"]):
        metadata = {
            "chunk_id": chunk["logical_artifact_id"],
            "nominal_max_seq_len": B0_NOMINAL_MAX_SEQ_LEN,
            "seed": chunk["seed"],
            "source_artifact_id": chunk["logical_artifact_id"],
            "source_artifact_sha256": chunk["raw_sha256"],
        }
        try:
            rows["B0"].extend(adapt_b0(blob, metadata))
        except ParserContractError as error:
            raise ProductionLedgerError(error.code, error.detail) from error
    adapters = {"B1": adapt_b1, "B2": adapt_b2, "D1": adapt_d1}
    for condition_name in ("B1", "B2", "D1"):
        try:
            rows[condition_name] = adapters[condition_name](
                loaded["singles"][condition_name],
                source_artifact_id=manifest[condition_name]["logical_artifact_id"],
                source_artifact_sha256=manifest[condition_name]["sha256"],
            )
        except ParserContractError as error:
            raise ProductionLedgerError(error.code, error.detail) from error
    return rows


def annotate_exact_duplicates(rows):
    """Mark within-condition exact duplicates. Keep every row and source order."""
    if type(rows) is not list:
        raise ProductionLedgerError("ledger_invalid", "derived rows are not a list")
    counts = {}
    for row in rows:
        if not isinstance(row, dict) or tuple(row) != DERIVED_FIELDS:
            raise ProductionLedgerError("ledger_invalid", "a derived row does not match the frozen field set")
        if row.get("outcome") == "valid_canonical_sequence":
            sequence = row.get("parsed_sequence")
            if type(sequence) is not str:
                raise ProductionLedgerError("ledger_invalid", "a valid row has no parsed sequence")
            counts[sequence] = counts.get(sequence, 0) + 1
    annotated = []
    for row in rows:
        produced = {key: row[key] for key in DERIVED_FIELDS}
        produced["ledger_schema"] = PRODUCTION_LEDGER_SCHEMA
        if row["outcome"] == "valid_canonical_sequence":
            multiplicity = counts[row["parsed_sequence"]]
            produced["is_valid_canonical"] = True
            produced["valid_sequence_multiplicity"] = multiplicity
            produced["is_exact_duplicate_within_condition"] = multiplicity > 1
        else:
            produced["is_valid_canonical"] = False
            produced["valid_sequence_multiplicity"] = None
            produced["is_exact_duplicate_within_condition"] = None
        if tuple(produced) != PRODUCTION_ROW_FIELDS:
            raise ProductionLedgerError("ledger_invalid", "a production row field order drifted")
        annotated.append(produced)
    return annotated


def ledger_jsonl_bytes(rows):
    chunks = []
    for row in rows:
        if tuple(row) != PRODUCTION_ROW_FIELDS:
            raise ProductionLedgerError("ledger_invalid", "a production row field order drifted")
        chunks.append(json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8"))
        chunks.append(b"\n")
    return b"".join(chunks)


def _json_document_bytes(value):
    text = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=False)
    return (text + "\n").encode("utf-8")


def _condition_accounting(rows):
    outcome_counts = {outcome: 0 for outcome in OUTCOMES}
    exclusion_counts = {reason: 0 for reason in FAILURE_REASONS}
    counts = {}
    for row in rows:
        outcome = row["outcome"]
        if outcome not in outcome_counts:
            raise ProductionLedgerError("accounting_invalid", "a row has an unknown parser outcome")
        outcome_counts[outcome] += 1
        if row["is_valid_canonical"] is True:
            if outcome != "valid_canonical_sequence" or row["failure_reason"] is not None:
                raise ProductionLedgerError("accounting_invalid", "a valid flag does not match the parser outcome")
            sequence = row["parsed_sequence"]
            counts[sequence] = counts.get(sequence, 0) + 1
        elif row["is_valid_canonical"] is not False:
            raise ProductionLedgerError("accounting_invalid", "is_valid_canonical is not a boolean")
        else:
            if outcome == "valid_canonical_sequence":
                raise ProductionLedgerError("accounting_invalid", "a valid outcome is not flagged valid")
            if row["failure_reason"] != outcome:
                raise ProductionLedgerError("accounting_invalid", "an exclusion reason does not match the parser outcome")
            exclusion_counts[outcome] += 1
            if row["valid_sequence_multiplicity"] is not None or row["is_exact_duplicate_within_condition"] is not None:
                raise ProductionLedgerError("accounting_invalid", "an invalid row carries duplicate accounting")
    valid = outcome_counts["valid_canonical_sequence"]
    for row in rows:
        if row["is_valid_canonical"] is not True:
            continue
        multiplicity = counts[row["parsed_sequence"]]
        if row["valid_sequence_multiplicity"] != multiplicity:
            raise ProductionLedgerError("accounting_invalid", "a duplicate group does not share one multiplicity")
        if row["is_exact_duplicate_within_condition"] is not (multiplicity > 1):
            raise ProductionLedgerError("accounting_invalid", "a duplicate flag does not match multiplicity")
    singleton_rows = 0
    duplicate_rows = 0
    repeated_groups = 0
    maximum = None
    for multiplicity in counts.values():
        if multiplicity == 1:
            singleton_rows += 1
        elif multiplicity > 1:
            repeated_groups += 1
            duplicate_rows += multiplicity
        else:
            raise ProductionLedgerError("accounting_invalid", "a valid multiplicity is below one")
        maximum = multiplicity if maximum is None else max(maximum, multiplicity)
    distinct = len(counts)
    invalid = len(rows) - valid
    if singleton_rows + duplicate_rows != valid:
        raise ProductionLedgerError("accounting_invalid", "valid duplicate rows do not reconcile")
    if distinct != singleton_rows + repeated_groups:
        raise ProductionLedgerError("accounting_invalid", "distinct valid sequences do not reconcile")
    if sum(outcome_counts.values()) != len(rows):
        raise ProductionLedgerError("accounting_invalid", "parser outcome counts do not reconcile")
    if valid + invalid != len(rows):
        raise ProductionLedgerError("accounting_invalid", "valid and invalid counts do not reconcile")
    projection = {
        "total_attempts": len(rows),
        "parser_outcome_counts": outcome_counts,
        "exclusion_reason_counts": exclusion_counts,
        "valid_canonical_count": valid,
        "invalid_or_non_sequence_count": invalid,
        "valid_singleton_row_count": singleton_rows,
        "valid_duplicate_member_row_count": duplicate_rows,
        "distinct_valid_sequences": distinct,
        "repeated_within_condition_sequence_groups": repeated_groups,
        "maximum_within_condition_multiplicity": maximum,
    }
    if _json_contains_sequence(projection, counts):
        raise ProductionLedgerError("accounting_sequence_leak", "the accounting projection contains a sequence")
    return projection


def _json_contains_sequence(value, sequences):
    if type(value) is str:
        if value in sequences:
            return True
        return len(value) >= 8 and all(character in "ACGU" for character in value)
    if isinstance(value, dict):
        return any(_json_contains_sequence(item, sequences) for item in value.values()) or any(
            _json_contains_sequence(item, sequences) for item in value
        )
    if isinstance(value, list):
        return any(_json_contains_sequence(item, sequences) for item in value)
    return False


def _d1_seed_counts(rows, allocation):
    expected = {item["d1_training_seed"]: item["attempts"] for item in allocation}
    blocks = {item["d1_training_seed"]: item.get("technical_block") for item in allocation}
    observed = {seed: 0 for seed in expected}
    for row in rows:
        seed = row.get("d1_training_seed")
        if seed not in observed:
            raise ProductionLedgerError("d1_seed_reconciliation_failed", "a D1 row seed is outside the manifest allocation")
        block = blocks.get(seed)
        if block is not None and row.get("technical_block") != block:
            raise ProductionLedgerError("d1_seed_reconciliation_failed", "a D1 row block does not match the manifest allocation")
        observed[seed] += 1
    if observed != expected:
        raise ProductionLedgerError("d1_seed_reconciliation_failed", "D1 training-seed attempt counts do not match the manifest")
    return {str(seed): observed[seed] for seed in sorted(observed)}


def build_accounting(rows_by_condition, d1_seed_counts):
    conditions = {}
    for condition_name in CONDITION_ORDER:
        projection = _condition_accounting(rows_by_condition[condition_name])
        if condition_name == "D1":
            projection["d1_training_seed_attempt_counts"] = d1_seed_counts
        elif any(row.get("d1_training_seed") is not None for row in rows_by_condition[condition_name]):
            raise ProductionLedgerError("d1_seed_reconciliation_failed", "a non-D1 row carries a D1 training seed")
        conditions[condition_name] = projection
    maxima = [
        item["maximum_within_condition_multiplicity"]
        for item in conditions.values()
        if item["maximum_within_condition_multiplicity"] is not None
    ]
    overall = {
        "total_attempts": sum(item["total_attempts"] for item in conditions.values()),
        "parser_outcome_counts": {outcome: 0 for outcome in OUTCOMES},
        "exclusion_reason_counts": {reason: 0 for reason in FAILURE_REASONS},
        "valid_canonical_count": sum(item["valid_canonical_count"] for item in conditions.values()),
        "invalid_or_non_sequence_count": sum(item["invalid_or_non_sequence_count"] for item in conditions.values()),
        "valid_singleton_row_count": sum(item["valid_singleton_row_count"] for item in conditions.values()),
        "valid_duplicate_member_row_count": sum(item["valid_duplicate_member_row_count"] for item in conditions.values()),
        "distinct_valid_sequences": sum(item["distinct_valid_sequences"] for item in conditions.values()),
        "repeated_within_condition_sequence_groups": sum(
            item["repeated_within_condition_sequence_groups"] for item in conditions.values()
        ),
        "maximum_within_condition_multiplicity": max(maxima) if maxima else None,
        "distinct_valid_sequences_are_within_condition_sums": True,
        "cross_condition_overlap_computed": False,
    }
    for condition in conditions.values():
        for outcome, count in condition["parser_outcome_counts"].items():
            overall["parser_outcome_counts"][outcome] += count
        for reason, count in condition["exclusion_reason_counts"].items():
            overall["exclusion_reason_counts"][reason] += count
    summary = {
        "schema": ACCOUNTING_SCHEMA,
        "sequence_strings_emitted": False,
        "cross_condition_overlap_computed": False,
        "conditions": conditions,
        "overall": overall,
    }
    return summary


def _assert_counts(manifest, rows_by_condition, production_totals):
    for condition_name in CONDITION_ORDER:
        if len(rows_by_condition[condition_name]) != manifest[condition_name]["attempt_count"]:
            raise ProductionLedgerError("row_count_mismatch", condition_name + " row count does not match the manifest")
    combined = sum(len(rows_by_condition[condition_name]) for condition_name in CONDITION_ORDER)
    if production_totals:
        for condition_name, expected in PRODUCTION_ATTEMPT_COUNTS.items():
            if manifest[condition_name]["attempt_count"] != expected or len(rows_by_condition[condition_name]) != expected:
                raise ProductionLedgerError("row_count_mismatch", condition_name + " is not the sealed attempt count")
        if combined != PRODUCTION_COMBINED_ROWS:
            raise ProductionLedgerError("row_count_mismatch", "the combined ledger is not the sealed attempt count")
        allocation = {item["d1_training_seed"]: item["attempts"] for item in manifest["D1"]["seed_allocation"]}
        if allocation != PRODUCTION_D1_SEED_COUNTS:
            raise ProductionLedgerError("d1_seed_reconciliation_failed", "the D1 manifest allocation is not 15000 from seed 43 and 15000 from seed 44")
    return combined


def _output_record(filename, blob, row_count):
    return {
        "filename": filename,
        "row_count": row_count,
        "byte_count": len(blob),
        "sha256": _sha256(blob),
    }


def _build_manifest(root, source_manifest_path, source_manifest_bytes, loaded, outputs, d1_seed_counts, invocation):
    contract = _contract_identity(root)
    return {
        "schema": MANIFEST_SCHEMA,
        "runner_git_commit": _git_head(root),
        "parser_contract": contract,
        "parser_version": PARSER_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "ledger_schema": PRODUCTION_LEDGER_SCHEMA,
        "source_manifest": {
            "schema": SOURCE_MANIFEST_SCHEMA,
            "path": os.path.abspath(source_manifest_path),
            "sha256": _sha256(source_manifest_bytes),
        },
        "inputs": loaded["inputs"],
        "b0_numeric_raw_concatenation_sha256": {
            "expected_sha256": loaded["expected_concatenation_sha256"],
            "recomputed_sha256": loaded["b0_concatenation_sha256"],
        },
        "outputs": outputs,
        "ordering": {
            "conditions": list(CONDITION_ORDER),
            "within_condition": "source order",
            "b0_chunks": "manifest source_chunks order",
            "combined_ledger": "byte concatenation of B0, B1, B2, then D1",
        },
        "duplicate_policy": {
            "population": "valid canonical sequences within one condition",
            "multiplicity": "count of valid rows with that exact sequence in the same condition",
            "duplicate_flag": "true for every valid row whose multiplicity is greater than one",
            "singletons_flagged": False,
            "invalid_rows": "multiplicity and duplicate flag are null",
            "rows_dropped": False,
            "cross_condition_overlap_computed": False,
        },
        "d1_training_seed_attempt_counts": d1_seed_counts,
        "invocation": invocation,
        "serialization": "UTF-8 JSONL, LF after every row, production field order, compact separators",
        "manifest_file": {
            "filename": OUTPUT_NAMES["manifest"],
            "sha256_embedded": False,
            "statement": "The SHA-256 of this manifest is the digest of these exact file bytes. It is not embedded, because embedding it would change the digest.",
        },
    }


def validate_published_directory(directory, expected_files):
    """Re-read a finished temporary directory before it is promoted."""
    directory = os.fspath(directory)
    pieces = []
    for condition_name in CONDITION_ORDER:
        filename = OUTPUT_NAMES[condition_name]
        blob = _read_regular_file(os.path.join(directory, filename))
        record = expected_files[filename]
        if _sha256(blob) != record["sha256"] or len(blob) != record["byte_count"]:
            raise ProductionLedgerError("output_validation_failed", filename + " did not match the prepared bytes")
        if blob.count(b"\n") != record["row_count"] or not blob.endswith(b"\n"):
            raise ProductionLedgerError("output_validation_failed", filename + " row count drifted")
        pieces.append(blob)
    combined = _read_regular_file(os.path.join(directory, OUTPUT_NAMES["combined"]))
    if combined != b"".join(pieces):
        raise ProductionLedgerError("combined_ledger_mismatch", "the combined ledger is not the ordered concatenation")
    combined_record = expected_files[OUTPUT_NAMES["combined"]]
    if _sha256(combined) != combined_record["sha256"] or combined.count(b"\n") != combined_record["row_count"]:
        raise ProductionLedgerError("combined_ledger_mismatch", "the combined ledger hash or row count drifted")
    for key in ("summary", "manifest"):
        filename = OUTPUT_NAMES[key]
        blob = _read_regular_file(os.path.join(directory, filename))
        record = expected_files[filename]
        if _sha256(blob) != record["sha256"] or len(blob) != record["byte_count"]:
            raise ProductionLedgerError("output_validation_failed", filename + " did not match the prepared bytes")


def _refuse_existing_outputs(output_dir):
    if os.path.islink(output_dir):
        raise ProductionLedgerError("output_symlink", "the output directory is a symlink")
    for filename in OUTPUT_NAMES.values():
        path = os.path.join(output_dir, filename)
        if os.path.lexists(path):
            raise ProductionLedgerError("output_exists", "an output file already exists")
    if os.path.exists(output_dir) and not os.path.isdir(output_dir):
        raise ProductionLedgerError("output_exists", "the output path is not a directory")


def publish_output_directory(output_dir, blobs):
    """Write a temporary directory and promote it only after validation."""
    output_dir = os.path.abspath(output_dir)
    _refuse_existing_outputs(output_dir)
    parent = os.path.dirname(output_dir)
    os.makedirs(parent, exist_ok=True)
    temp = tempfile.mkdtemp(prefix=".m9-production-ledger.", dir=parent)
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
            expected[filename] = {"sha256": _sha256(blob), "byte_count": len(blob), "row_count": blob.count(b"\n")}
        validate_published_directory(temp, expected)
        if not os.path.exists(output_dir):
            os.rename(temp, output_dir)
            promoted = True
        else:
            for filename, _blob in blobs:
                os.rename(os.path.join(temp, filename), os.path.join(output_dir, filename))
            os.rmdir(temp)
            promoted = True
    finally:
        if not promoted and os.path.isdir(temp):
            shutil.rmtree(temp)
    return output_dir


def run_ledger(source_manifest_path, output_dir, locator, *, production_totals, invocation, root=REPO_ROOT):
    """Build the output set from locator paths whose hashes match the manifest."""
    _refuse_existing_outputs(os.path.abspath(output_dir))
    source_blob = _read_regular_file(source_manifest_path)
    document = _load_json_bytes(source_blob, "the source manifest")
    manifest = validate_source_manifest(document)
    loaded = _load_sources(manifest, locator)
    loaded["expected_concatenation_sha256"] = manifest["B0"]["numeric_raw_concatenation_sha256"]
    parsed = _adapt_all(manifest, loaded)
    rows = {condition_name: annotate_exact_duplicates(parsed[condition_name]) for condition_name in CONDITION_ORDER}
    _assert_counts(manifest, rows, production_totals)
    d1_counts = _d1_seed_counts(rows["D1"], manifest["D1"]["seed_allocation"])
    for condition_name in CONDITION_ORDER:
        if any(row["equal_seed_weighting_applied"] is not False for row in rows[condition_name]):
            raise ProductionLedgerError("equal_seed_weighting_refused", "equal-seed weighting is not applied")
    summary = build_accounting(rows, d1_counts)
    ledger_blobs = {condition_name: ledger_jsonl_bytes(rows[condition_name]) for condition_name in CONDITION_ORDER}
    combined = b"".join(ledger_blobs[condition_name] for condition_name in CONDITION_ORDER)
    if combined != ledger_blobs["B0"] + ledger_blobs["B1"] + ledger_blobs["B2"] + ledger_blobs["D1"]:
        raise ProductionLedgerError("combined_ledger_mismatch", "the combined ledger is not the ordered concatenation")
    summary_blob = _json_document_bytes(summary)
    output_records = []
    named = []
    for condition_name in CONDITION_ORDER:
        filename = OUTPUT_NAMES[condition_name]
        blob = ledger_blobs[condition_name]
        output_records.append(_output_record(filename, blob, len(rows[condition_name])))
        named.append((filename, blob))
    output_records.append(_output_record(OUTPUT_NAMES["combined"], combined, sum(len(rows[name]) for name in CONDITION_ORDER)))
    named.append((OUTPUT_NAMES["combined"], combined))
    manifest_document = _build_manifest(
        root,
        source_manifest_path,
        source_blob,
        loaded,
        output_records + [
            _output_record(OUTPUT_NAMES["summary"], summary_blob, None),
        ],
        d1_counts,
        invocation,
    )
    manifest_blob = _json_document_bytes(manifest_document)
    named.append((OUTPUT_NAMES["summary"], summary_blob))
    named.append((OUTPUT_NAMES["manifest"], manifest_blob))
    if [item[0] for item in named] != [OUTPUT_NAMES[key] for key in ("B0", "B1", "B2", "D1", "combined", "summary", "manifest")]:
        raise ProductionLedgerError("output_validation_failed", "the output name order drifted")
    publish_output_directory(output_dir, named)
    return {
        "output_dir": os.path.abspath(output_dir),
        "row_counts": {condition_name: len(rows[condition_name]) for condition_name in CONDITION_ORDER},
        "combined_row_count": sum(len(rows[condition_name]) for condition_name in CONDITION_ORDER),
        "d1_training_seed_attempt_counts": d1_counts,
    }


def run_sealed_sources(source_manifest_path, output_dir, invocation, root=REPO_ROOT):
    """Production entry. The locator is the sealed logical-id table."""
    blob = _read_regular_file(source_manifest_path)
    document = _load_json_bytes(blob, "the source manifest")
    locator = sealed_source_locator(document, root)
    return run_ledger(
        source_manifest_path,
        output_dir,
        locator,
        production_totals=True,
        invocation=invocation,
        root=root,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the M9 production derived-attempt ledgers.")
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    command = list(sys.argv) if argv is None else [os.path.basename(__file__), *list(argv)]
    try:
        result = run_sealed_sources(
            args.source_manifest,
            args.output_dir,
            {"argv": command, "production_totals": True},
        )
    except ProductionLedgerError as error:
        sys.stderr.write(error.code + ": " + error.detail + "\n")
        return 1
    sys.stdout.write("output_dir=" + result["output_dir"] + "\n")
    for condition_name in CONDITION_ORDER:
        sys.stdout.write(condition_name + "_rows=" + str(result["row_counts"][condition_name]) + "\n")
    sys.stdout.write("combined_rows=" + str(result["combined_row_count"]) + "\n")
    sys.stdout.write("d1_training_seed_attempt_counts=" + json.dumps(result["d1_training_seed_attempt_counts"], sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

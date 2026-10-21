#!/usr/bin/env python3
"""Prepare the frozen Section 9 four-condition NDM-1 AptaRank package.

This production adapter joins the frozen B0/B1/B2/D1 unique-sequence pools
to their sequence-free attempt provenance, applies only the already-frozen
20--100 nt AptaRank input bound, and delegates sampling and opaque identifiers
to the unchanged M9B-2 implementation.  It prepares files for Laura's manual
browser run; it does not call AptaRank or calculate any score.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    from scripts.modelling import aptarank_candidate_preparation as m9b
except ModuleNotFoundError:  # Direct execution from scripts/modelling.
    import aptarank_candidate_preparation as m9b


PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_7.md"
PLAN_SHA256 = "24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9"
REFERENCE_RELATIVE = "data/aptarank_eval/reference/m9c_reference_upload_attempt3.csv"
REFERENCE_SHA256 = "5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6"
REFERENCE_ROWS = 113
SOURCE_ROOT_RELATIVE = "results/fine_tuning/generated_sequence_pools/frozen_m9_export_v1"
MEMBERSHIP_RELATIVE = SOURCE_ROOT_RELATIVE + "/private_provenance/valid_attempt_membership.jsonl"
MEMBERSHIP_SHA256 = "a04342d73f6037eb9b38a9e20a2f35d7c3cfcbfd5cfef71562feca90a3e95fe6"
M9B_CONTRACT_RELATIVE = "config/modelling/aptarank_candidate_preparation_contract.json"
M9B_CONTRACT_SHA256 = "3bcfbdf14cd7e777a0b2746f91d0335ba4876195f5012610157e5aa23e083096"
M9B_MODULE_RELATIVE = "scripts/modelling/aptarank_candidate_preparation.py"
M9B_MODULE_SHA256 = "a4f5b047f2803e775d9521c226287487412495055446e192681957c3d42879ca"
M9C_SUMMARY_RELATIVE = (
    "results/fine_tuning/m9_generator_evaluation/m9c_live_deployment_validation/"
    "m9c_live_deployment_validation_summary.json"
)
M9C_SUMMARY_SHA256 = "2abc4af0df4907bd96187c269b2ef2dd0bac32c3137b0dc8f8cb3687f203e4f4"
TARGET_TEXT_RELATIVE = "target/artifacts/ndm1_5zgx_fpocket4/aptarank_target_5zgx.txt"
TARGET_TEXT_SHA256 = "46471bb0643125ce86300ec050d6f0d3a09faa1d06dc325141c67cd1acdd5922"
TARGET_PROVENANCE_RELATIVE = "target/artifacts/ndm1_5zgx_fpocket4/target_configuration.json"
TARGET_PROVENANCE_SHA256 = "08f0c96af349ce4909d40c3004804317661777f72828cd807823341e0e4f0d04"
PACKAGE_ID = "section9_generated_conditions_ndm1_evaluation_preset_v1"
MEMBERSHIP_COUNT = 200
CONDITIONS = ("B0", "B1", "B2", "D1")
LENGTH_MIN = 20
LENGTH_MAX = 100
SOURCE_ID = re.compile(r"^(B0|B1|B2|D1)-U[0-9]{5}$")
OPAQUE_ID = re.compile(r"^cand_[0-9a-f]{32}$")
SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$")
EXPORT_FIELDS = ("rank", "candidate", "aptamer-likeness", "compatibility", "shuffle", "len", "sequence")

SOURCES = {
    "B0": {
        "filename": "B0_valid_unique_rna.csv",
        "sha256": "427363781efd26eaa58cc26edf9439ad8107c5487ad7dfbc7a5f47b838b3007e",
        "rows": 30080,
        "eligible": 30080,
        "below": 0,
        "above": 0,
        "header": (
            "condition", "source_candidate_id", "sequence", "sequence_length",
            "condition_multiplicity", "first_record_id", "b0_seed", "b0_chunk_id",
        ),
    },
    "B1": {
        "filename": "B1_valid_unique_rna.csv",
        "sha256": "7ec398c2cb737d08e764a5cc09da27190c0f78698af68ffac16d5a7835553c5c",
        "rows": 29983,
        "eligible": 29548,
        "below": 2,
        "above": 433,
        "header": (
            "condition", "source_candidate_id", "sequence", "sequence_length",
            "condition_multiplicity", "first_record_id", "technical_block", "checkpoint_identity",
        ),
    },
    "B2": {
        "filename": "B2_valid_unique_rna.csv",
        "sha256": "4a720360ff50b43a8872de1d56ff853f980c61574b2f5ab95329517d71eca1d4",
        "rows": 30000,
        "eligible": 29475,
        "below": 0,
        "above": 525,
        "header": (
            "condition", "source_candidate_id", "sequence", "sequence_length",
            "condition_multiplicity", "first_record_id", "empirical_null_seed",
        ),
    },
    "D1": {
        "filename": "D1_valid_unique_rna.csv",
        "sha256": "9b6cfb6c6e0d1cb1f7d7c3446843c193ac7934751c0394561655c132e7d5d612",
        "rows": 30000,
        "eligible": 29583,
        "below": 11,
        "above": 406,
        "header": (
            "condition", "source_candidate_id", "sequence", "sequence_length",
            "condition_multiplicity", "first_record_id", "d1_training_seed", "technical_block",
        ),
    },
}


class PreparationError(RuntimeError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_regular(path: Path) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PreparationError(f"not a regular file: {path}")
    return path.read_bytes()


def pinned(path: Path, expected: str) -> bytes:
    payload = read_regular(path)
    observed = sha256_bytes(payload)
    if observed != expected:
        raise PreparationError(f"hash mismatch for {path}: expected {expected}, observed {observed}")
    return payload


def integer(value: object, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool):
        raise PreparationError(f"{label} is not an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PreparationError(f"{label} is not an integer") from exc
    if str(parsed) != str(value) and not isinstance(value, int):
        raise PreparationError(f"{label} is not in canonical integer form")
    if minimum is not None and parsed < minimum:
        raise PreparationError(f"{label} is below {minimum}")
    return parsed


def parse_source(condition: str, payload: bytes) -> dict[str, dict[str, object]]:
    specification = SOURCES[condition]
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreparationError(f"{condition} source is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != specification["header"]:
        raise PreparationError(f"{condition} source header drifted")
    rows: dict[str, dict[str, object]] = {}
    sequences: set[str] = set()
    below = above = 0
    for row in reader:
        if row["condition"] != condition:
            raise PreparationError(f"{condition} source has a wrong condition token")
        source_id = row["source_candidate_id"]
        if SOURCE_ID.fullmatch(source_id) is None or not source_id.startswith(condition + "-"):
            raise PreparationError(f"{condition} source candidate id is malformed")
        sequence = row["sequence"]
        length = integer(row["sequence_length"], f"{condition} sequence length", 1)
        multiplicity = integer(row["condition_multiplicity"], f"{condition} multiplicity", 1)
        if not sequence or set(sequence) - set("ACGU") or len(sequence) != length:
            raise PreparationError(f"{condition} source has a noncanonical sequence or length mismatch")
        if source_id in rows or sequence in sequences:
            raise PreparationError(f"{condition} source is not unique by id and sequence")
        if length < LENGTH_MIN:
            below += 1
        elif length > LENGTH_MAX:
            above += 1
        rows[source_id] = {
            "condition": condition,
            "source_candidate_id": source_id,
            "sequence": sequence,
            "length": length,
            "multiplicity": multiplicity,
            "first_record_id": row["first_record_id"],
            "eligible": LENGTH_MIN <= length <= LENGTH_MAX,
        }
        sequences.add(sequence)
    eligible = sum(bool(row["eligible"]) for row in rows.values())
    if (len(rows), eligible, below, above) != (
        specification["rows"], specification["eligible"], specification["below"], specification["above"]
    ):
        raise PreparationError(f"{condition} source or eligibility accounting drifted")
    return rows


def provenance_for(condition: str, row: dict[str, object]) -> dict[str, object]:
    if condition == "B0":
        return {
            "b0_seed": integer(row.get("b0_seed"), "B0 seed", 0),
            "b0_chunk_id": row.get("b0_chunk_id"),
            "line_number": integer(row.get("line_number"), "B0 line number", 1),
            "source_artifact_id": row.get("source_artifact_id"),
            "source_artifact_sha256": row.get("source_artifact_sha256"),
        }
    if condition in ("B1", "D1"):
        seed = row.get("d1_training_seed")
        if condition == "B1" and seed is not None:
            raise PreparationError("B1 has a non-null D1 training seed")
        return {
            "checkpoint_identity": row.get("checkpoint_identity"),
            "generation_seed": integer(row.get("generation_seed"), f"{condition} generation seed", 0),
            "requested_biological_length": integer(
                row.get("requested_biological_length"), f"{condition} requested length", 1
            ),
            "invocation_index": integer(row.get("invocation_index"), f"{condition} invocation index", 0),
            "master_attempt_index": integer(
                row.get("master_attempt_index"), f"{condition} master attempt index", 0
            ),
            "technical_block": row.get("technical_block"),
            "source_artifact_id": row.get("source_artifact_id"),
            "source_artifact_sha256": row.get("source_artifact_sha256"),
            "d1_training_seed": None if condition == "B1" else integer(seed, "D1 training seed", 0),
        }
    return {
        "attempt_index": integer(row.get("attempt_index"), "B2 attempt index", 0),
        "empirical_null_seed": integer(row.get("empirical_null_seed"), "B2 empirical-null seed", 0),
        "sampled_length": integer(row.get("sampled_length"), "B2 sampled length", 0),
        "source_artifact_id": row.get("source_artifact_id"),
        "source_artifact_sha256": row.get("source_artifact_sha256"),
    }


def build_records(
    source_payloads: dict[str, bytes],
    membership_payload: bytes,
    *,
    expected_attempt_rows: int = 120080,
    expected_attempt_rows_by_condition: dict[str, int] | None = None,
) -> tuple[list[dict[str, object]], dict[str, dict[str, dict[str, object]]], dict[str, object]]:
    if set(source_payloads) != set(CONDITIONS):
        raise PreparationError("the four source payloads are required")
    sources = {condition: parse_source(condition, source_payloads[condition]) for condition in CONDITIONS}
    occurrences: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    occurrence_indexes: dict[tuple[str, str], set[int]] = defaultdict(set)
    first_counts: Counter[tuple[str, str]] = Counter()
    record_ids: set[str] = set()
    rows_by_condition: Counter[str] = Counter()
    try:
        text = membership_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreparationError("attempt membership is not UTF-8") from exc
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            raise PreparationError("attempt membership contains a blank record")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PreparationError(f"attempt membership row {line_number} is not JSON") from exc
        if not isinstance(row, dict):
            raise PreparationError("attempt membership row is not an object")
        condition = row.get("condition")
        source_id = row.get("source_candidate_id")
        if condition not in CONDITIONS or source_id not in sources[condition]:
            raise PreparationError("attempt membership does not join to a frozen source row")
        source = sources[condition][source_id]
        record_id = row.get("record_id")
        if not isinstance(record_id, str) or not record_id or record_id in record_ids:
            raise PreparationError("attempt membership record_id is missing or duplicated")
        record_ids.add(record_id)
        if row.get("multiplicity_group") != source_id:
            raise PreparationError("attempt membership multiplicity group drifted")
        if integer(row.get("condition_multiplicity"), "attempt multiplicity", 1) != source["multiplicity"]:
            raise PreparationError("attempt membership multiplicity disagrees with the source")
        if integer(row.get("parsed_length"), "attempt parsed length", 1) != source["length"]:
            raise PreparationError("attempt membership length disagrees with the source")
        if row.get("first_record_id") != source["first_record_id"]:
            raise PreparationError("attempt membership first-record identity drifted")
        if row.get("is_valid_canonical") is not True:
            raise PreparationError("attempt membership is not marked valid canonical")
        index = integer(row.get("occurrence_index"), "occurrence index", 1)
        key = (condition, source_id)
        if index in occurrence_indexes[key]:
            raise PreparationError("attempt membership occurrence index is duplicated")
        occurrence_indexes[key].add(index)
        if row.get("is_first_occurrence") is True:
            first_counts[key] += 1
            if record_id != source["first_record_id"]:
                raise PreparationError("first occurrence does not match first_record_id")
        rows_by_condition[condition] += 1
        if source["eligible"]:
            provenance = provenance_for(condition, row)
            for token in (provenance["source_artifact_id"], provenance["source_artifact_sha256"]):
                if not isinstance(token, str) or not token:
                    raise PreparationError("source artifact provenance is missing")
            if SHA256_TEXT.fullmatch(str(provenance["source_artifact_sha256"])) is None:
                raise PreparationError("source artifact digest is malformed")
            occurrences[key].append({"source_identity": record_id, "provenance": provenance})

    records: list[dict[str, object]] = []
    for condition in CONDITIONS:
        for source_id, source in sources[condition].items():
            key = (condition, source_id)
            expected_indexes = set(range(1, int(source["multiplicity"]) + 1))
            if occurrence_indexes[key] != expected_indexes or first_counts[key] != 1:
                raise PreparationError("attempt occurrence accounting does not reconcile")
            if source["eligible"]:
                records.append({
                    "condition": condition,
                    "sequence": source["sequence"],
                    "length": source["length"],
                    "multiplicity": source["multiplicity"],
                    "source_occurrences": occurrences[key],
                })
    expected_by_condition = expected_attempt_rows_by_condition or {
        "B0": 30080, "B1": 30000, "B2": 30000, "D1": 30000
    }
    if len(record_ids) != expected_attempt_rows or {
        condition: rows_by_condition[condition] for condition in CONDITIONS
    } != expected_by_condition:
        raise PreparationError("attempt-level denominator drifted")
    accounting = {
        "attempt_membership_rows": len(record_ids),
        "attempt_rows_by_condition": {condition: rows_by_condition[condition] for condition in CONDITIONS},
        "source_unique_rows_by_condition": {condition: len(sources[condition]) for condition in CONDITIONS},
        "eligible_unique_rows_by_condition": {
            condition: sum(bool(row["eligible"]) for row in sources[condition].values()) for condition in CONDITIONS
        },
        "ineligible_below_20_by_condition": {condition: SOURCES[condition]["below"] for condition in CONDITIONS},
        "ineligible_above_100_by_condition": {condition: SOURCES[condition]["above"] for condition in CONDITIONS},
    }
    return records, sources, accounting


def byte_record(payload: bytes) -> dict[str, object]:
    return {"sha256": sha256_bytes(payload), "byte_count": len(payload)}


def selected_source_key(
    upload: bytes,
    private_key: bytes,
    sources: dict[str, dict[str, dict[str, object]]],
) -> tuple[bytes, dict[str, object]]:
    upload_rows = list(csv.DictReader(io.StringIO(upload.decode("utf-8"), newline="")))
    sequence_by_id = {row["id"]: row["sequence"] for row in upload_rows}
    source_by_sequence = {
        condition: {str(row["sequence"]): source_id for source_id, row in source_rows.items()}
        for condition, source_rows in sources.items()
    }
    output = []
    condition_counts = Counter()
    d1_counts = Counter()
    b1_blocks = Counter()
    for line in private_key.decode("utf-8").splitlines():
        membership = json.loads(line)
        candidate_id = membership["candidate_id"]
        condition = membership["condition"]
        sequence = sequence_by_id.get(candidate_id)
        if sequence is None or sequence not in source_by_sequence[condition]:
            raise PreparationError("selected M9B membership does not reconcile to a frozen source")
        source_id = source_by_sequence[condition][sequence]
        source = sources[condition][source_id]
        output.append({
            "candidate_id": candidate_id,
            "condition": condition,
            "source_candidate_id": source_id,
            "sequence_sha256": hashlib.sha256(sequence.encode("utf-8")).hexdigest(),
            "length": membership["length"],
            "multiplicity": membership["multiplicity"],
            "source_record_ids": [item["source_identity"] for item in membership["source_occurrences"]],
        })
        condition_counts[condition] += 1
        if condition == "D1":
            d1_counts[membership["source_occurrences"][0]["provenance"]["d1_training_seed"]] += 1
        if condition == "B1":
            blocks = {item["provenance"]["technical_block"] for item in membership["source_occurrences"]}
            for block in blocks:
                b1_blocks[block] += 1
    if any(condition_counts[condition] != MEMBERSHIP_COUNT for condition in CONDITIONS):
        raise PreparationError("selected condition counts drifted")
    if d1_counts != Counter({43: 100, 44: 100}):
        raise PreparationError("selected D1 seed balance drifted")
    document = {
        "schema_version": "mres-aptarank-section9-source-key-v1",
        "status": "RESTRICTED_DO_NOT_UPLOAD_OR_COMMIT",
        "package_id": PACKAGE_ID,
        "join_key": ["candidate_id", "condition"],
        "sequence_strings_included": False,
        "memberships": output,
    }
    summary = {
        "selected_memberships_by_condition": {condition: condition_counts[condition] for condition in CONDITIONS},
        "d1_selected_by_training_seed": {"43": d1_counts[43], "44": d1_counts[44]},
        "b1_selected_memberships_touching_block": {block: b1_blocks[block] for block in sorted(b1_blocks)},
        "upload_rows": len(upload_rows),
    }
    return canonical_json(document), summary


def target_settings() -> bytes:
    return canonical_json({
        "schema_version": "mres-aptarank-section9-target-settings-v1",
        "package_id": PACKAGE_ID,
        "target": "NDM-1",
        "pdb_id": "5ZGX",
        "chain": "A",
        "binding_mode": "pocket",
        "recognition_interpretation": "pocket/groove recognition",
        "target_site_residues": [120, 122, 124, 189, 208, 250],
        "prepared_target_identifier": "0fde4d5e4370",
        "prepared_target_identifier_source": {"path": M9C_SUMMARY_RELATIVE, "sha256": M9C_SUMMARY_SHA256},
        "target_configuration": {"path": TARGET_TEXT_RELATIVE, "sha256": TARGET_TEXT_SHA256},
        "target_preparation_provenance": {"path": TARGET_PROVENANCE_RELATIVE, "sha256": TARGET_PROVENANCE_SHA256},
        "interpretation_boundary": (
            "The score is geometric computational prioritisation against one static NDM-1 groove configuration; "
            "it is not binding, affinity, specificity, inhibition or experimental validation."
        ),
    })


def expected_cells(upload: bytes) -> bytes:
    rows = list(csv.DictReader(io.StringIO(upload.decode("utf-8"), newline="")))
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)) or any(OPAQUE_ID.fullmatch(value) is None for value in ids):
        raise PreparationError("candidate upload ids are duplicated or malformed")
    return canonical_json({
        "schema_version": "mres-aptarank-section9-expected-cells-v1",
        "package_id": PACKAGE_ID,
        "expected_candidate_ids": ids,
        "expected_upload_row_count": len(ids),
        "expected_condition_memberships": 800,
        "candidate_id_export_field": "candidate",
        "expected_export_fields": list(EXPORT_FIELDS),
        "join_by_candidate_id": True,
        "row_position_is_join_key": False,
        "aptamer_likeness": "finite decimal in closed interval [0,1]",
        "compatibility_allowed_tokens": ["strong", "moderate", "weak"],
        "shuffle_allowed_tokens": ["pass", "fail"],
        "raw_tier2_score": "capture only if an untouched deployed artifact exposes it; do not reconstruct",
        "missing_or_excluded_rows": "record explicitly against every retained condition membership; do not replace",
    })


def run_sheet(
    upload: bytes,
    m9b_key: bytes,
    source_key: bytes,
    expected: bytes,
    target: bytes,
) -> bytes:
    upload_rows = len(list(csv.DictReader(io.StringIO(upload.decode("utf-8"), newline=""))))
    return canonical_json({
        "schema_version": "mres-aptarank-section9-run-sheet-v1",
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "package_id": PACKAGE_ID,
        "operator": "Laura",
        "deployment": {"aptarank_version": "0.1.0", "schema_version": "1.0.0", "git_revision": "49a85609e352"},
        "inputs": {
            "reference_upload": {"path": REFERENCE_RELATIVE, "sha256": REFERENCE_SHA256, "row_count": REFERENCE_ROWS},
            "candidate_upload": {"path": "upload/candidate_upload.csv", **byte_record(upload), "row_count": upload_rows},
            "m9b2_private_membership_key": {"restricted": True, **byte_record(m9b_key)},
            "source_candidate_key": {"restricted": True, **byte_record(source_key)},
            "expected_cell_manifest": {"path": "records/expected_cell_manifest.json", **byte_record(expected)},
            "target_settings": {"path": "records/target_settings.json", **byte_record(target)},
        },
        "settings": {
            "preset": "Evaluation",
            "seed": 42,
            "candidate_shuffled_controls": 99,
            "ensemble_samples": 200,
            "composite_method": "corpus_weighted_mean",
            "expected_scoring_signature": "95a49467ef3c6186",
        },
        "manual_steps": [
            "Upload the frozen 113-row attempt-3 reference CSV.",
            "Upload only upload/candidate_upload.csv from this package.",
            "Configure NDM-1, PDB 5ZGX, chain A, pocket mode and residues 120, 122, 124, 189, 208 and 250.",
            "Confirm that the prepared-target identifier is 0fde4d5e4370; stop if it differs.",
            "Select the named Evaluation preset and confirm seed 42, 99 candidate shuffles and 200 sampled structures.",
            "Stop before scoring if any frozen target or effective setting differs; do not manually approximate it.",
            "Run the candidate upload once and do not replenish any rejected candidate.",
            "Download the untouched shortlist CSV, exclusion register if present, result PDF and every available raw artifact.",
            "Record runtime, warnings, uploaded/scored/excluded counts, target settings and displayed scoring signature.",
        ],
        "reporting": {
            "tier1_and_tier2_separate": True,
            "combined_score": False,
            "section9_candidates_enter_supervisor_shortlist": False,
            "publication_eligible_false_marker": "known interface bug; ignore under the documented thesis-wide decision",
        },
    })


def preparation_manifest(
    accounting: dict[str, object],
    selection: dict[str, object],
    upload: bytes,
    m9b_key: bytes,
    source_key: bytes,
    expected: bytes,
    target: bytes,
    run: bytes,
) -> bytes:
    source_pins = {
        condition: {
            "path": SOURCE_ROOT_RELATIVE + "/valid_unique_candidate_sources/" + str(SOURCES[condition]["filename"]),
            "sha256": SOURCES[condition]["sha256"],
        }
        for condition in CONDITIONS
    }
    return canonical_json({
        "schema_version": "mres-aptarank-section9-preparation-manifest-v1",
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "package_id": PACKAGE_ID,
        "scientific_result": False,
        "aptarank_executed": False,
        "pins": {
            "governing_plan": {"path": PLAN_RELATIVE, "sha256": PLAN_SHA256},
            "reference_upload": {"path": REFERENCE_RELATIVE, "sha256": REFERENCE_SHA256},
            "candidate_preparation_contract": {"path": M9B_CONTRACT_RELATIVE, "sha256": M9B_CONTRACT_SHA256},
            "candidate_preparation_module": {"path": M9B_MODULE_RELATIVE, "sha256": M9B_MODULE_SHA256},
            "attempt_membership": {"path": MEMBERSHIP_RELATIVE, "sha256": MEMBERSHIP_SHA256},
            "candidate_sources": source_pins,
            "deployed_target_record": {"path": M9C_SUMMARY_RELATIVE, "sha256": M9C_SUMMARY_SHA256},
            "target_configuration": {"path": TARGET_TEXT_RELATIVE, "sha256": TARGET_TEXT_SHA256},
            "target_preparation_provenance": {"path": TARGET_PROVENANCE_RELATIVE, "sha256": TARGET_PROVENANCE_SHA256},
        },
        "eligibility": {
            "rule": "canonical frozen unique RNA and length 20 through 100 inclusive before score-blind sampling",
            "score_used": False,
            **accounting,
        },
        "sampling": {
            "membership_count_per_condition": MEMBERSHIP_COUNT,
            "total_condition_memberships": 800,
            "domain_separator": m9b.SAMPLING_DOMAIN,
            "sampling_seed": m9b.SAMPLING_SEED,
            "algorithm": "SHA-256 length-delimited priority; lowest priority without replacement",
            "d1_balance": {"training_seed_43": 100, "training_seed_44": 100},
            "score_blind": True,
            "replacement_or_replenishment": False,
        },
        "selection": selection,
        "opaque_id": {
            "domain_separator": m9b.ID_DOMAIN,
            "algorithm": "HMAC-SHA-256",
            "key_length_bytes": 32,
            "truncation_bytes": 16,
            "secret_in_public_package": False,
        },
        "artifacts": {
            "candidate_upload": byte_record(upload),
            "restricted_m9b2_private_membership_key": byte_record(m9b_key),
            "restricted_source_candidate_key": byte_record(source_key),
            "expected_cell_manifest": byte_record(expected),
            "target_settings": byte_record(target),
            "run_sheet": byte_record(run),
        },
    })


def validation_report(
    upload: bytes,
    m9b_key: bytes,
    source_key: bytes,
    expected: bytes,
    selection: dict[str, object],
) -> bytes:
    upload_rows = list(csv.DictReader(io.StringIO(upload.decode("utf-8"), newline="")))
    private_rows = [json.loads(line) for line in m9b_key.decode("utf-8").splitlines()]
    source_document = json.loads(source_key)
    expected_document = json.loads(expected)
    upload_ids = {row["id"] for row in upload_rows}
    if {row["candidate_id"] for row in private_rows} != upload_ids:
        raise PreparationError("M9B private key does not reconcile to the upload")
    if {row["candidate_id"] for row in source_document["memberships"]} != upload_ids:
        raise PreparationError("source key does not reconcile to the upload")
    if set(expected_document["expected_candidate_ids"]) != upload_ids:
        raise PreparationError("expected cells do not reconcile to the upload")
    return canonical_json({
        "schema_version": "mres-aptarank-section9-preflight-v1",
        "status": "PASS",
        "package_id": PACKAGE_ID,
        "aptarank_executed": False,
        "checks": {
            "all_source_hash_pins_match": True,
            "source_schemas_and_unique_keys_match": True,
            "attempt_membership_join_and_multiplicity_reconcile": True,
            "technical_eligibility_is_only_frozen_20_100_nt_bound": True,
            "m9b2_sampling_and_opaque_id_logic_reused_unchanged": True,
            "selected_condition_counts_are_200_each": True,
            "d1_training_seed_counts_are_100_each": True,
            "global_upload_deduplication_preserves_all_condition_memberships": True,
            "upload_private_keys_and_expected_cells_reconcile": True,
            "reference_and_target_pins_match": True,
            "evaluation_preset_run_sheet_is_frozen": True,
            "score_used_for_membership_selection": False,
            "aptarank_called": False,
        },
        "denominators": {
            "condition_memberships": 800,
            "upload_rows": len(upload_rows),
            "private_membership_rows": len(private_rows),
            "source_key_membership_rows": len(source_document["memberships"]),
            **selection,
        },
        "artifacts": {
            "candidate_upload": byte_record(upload),
            "restricted_m9b2_private_membership_key": byte_record(m9b_key),
            "restricted_source_candidate_key": byte_record(source_key),
            "expected_cell_manifest": byte_record(expected),
        },
    })


def readme(upload: bytes, private_key: bytes, source_key: bytes) -> bytes:
    upload_rows = len(list(csv.DictReader(io.StringIO(upload.decode("utf-8"), newline=""))))
    return (
        f"# {PACKAGE_ID}\n\n"
        "Status: `PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN`\n\n"
        "This is the blinded upload package for the frozen Section 9 comparison. It contains exactly 200 "
        "condition memberships from each of B0, B1, B2 and D1, with D1 balanced 100/100 across training "
        "seeds 43 and 44. Identical selected sequences across conditions are uploaded once while all 800 "
        f"memberships remain in the restricted keys. The resulting upload contains {upload_rows} rows.\n\n"
        "Upload only `upload/candidate_upload.csv`. Use the frozen 113-row attempt-3 REF upload and follow "
        "`records/run_sheet.json` exactly for the NDM-1 Evaluation-preset run. AptaRank was not run during "
        "preparation.\n\n"
        f"Restricted M9B-2 membership-key SHA-256: `{sha256_bytes(private_key)}`.\n\n"
        f"Restricted source-candidate-key SHA-256: `{sha256_bytes(source_key)}`.\n"
    ).encode("utf-8")


def sha_manifest(files: dict[str, bytes]) -> bytes:
    return "".join(f"{sha256_bytes(files[name])}  {name}\n" for name in sorted(files)).encode("ascii")


def publish_directory(destination: Path, files: dict[str, bytes], private_names: set[str] | None = None) -> None:
    if destination.exists() or destination.is_symlink():
        raise PreparationError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".section9-prep-", dir=destination.parent))
    promoted = False
    try:
        for relative, payload in files.items():
            path = temp / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = 0o600 if private_names and relative in private_names else 0o644
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise PreparationError(f"write stalled for {relative}")
                    view = view[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if read_regular(path) != payload:
                raise PreparationError(f"published bytes changed for {relative}")
        if private_names and private_names == set(files):
            os.chmod(temp, 0o700)
        os.rename(temp, destination)
        promoted = True
    finally:
        if not promoted and temp.exists():
            shutil.rmtree(temp)


def prepare(repo: Path, public_package: Path, restricted_package: Path, secret_path: Path) -> dict[str, object]:
    pinned(repo / PLAN_RELATIVE, PLAN_SHA256)
    reference = pinned(repo / REFERENCE_RELATIVE, REFERENCE_SHA256)
    pinned(repo / M9B_CONTRACT_RELATIVE, M9B_CONTRACT_SHA256)
    pinned(repo / M9B_MODULE_RELATIVE, M9B_MODULE_SHA256)
    pinned(repo / M9C_SUMMARY_RELATIVE, M9C_SUMMARY_SHA256)
    pinned(repo / TARGET_TEXT_RELATIVE, TARGET_TEXT_SHA256)
    pinned(repo / TARGET_PROVENANCE_RELATIVE, TARGET_PROVENANCE_SHA256)
    if len(list(csv.DictReader(io.StringIO(reference.decode("utf-8"), newline="")))) != REFERENCE_ROWS:
        raise PreparationError("reference upload row count drifted")
    source_payloads = {}
    for condition in CONDITIONS:
        relative = SOURCE_ROOT_RELATIVE + "/valid_unique_candidate_sources/" + str(SOURCES[condition]["filename"])
        source_payloads[condition] = pinned(repo / relative, str(SOURCES[condition]["sha256"]))
    membership = pinned(repo / MEMBERSHIP_RELATIVE, MEMBERSHIP_SHA256)
    secret = read_regular(secret_path)
    if len(secret) != 32:
        raise PreparationError("caller-supplied blinding secret must be exactly 32 bytes")

    records, sources, accounting = build_records(source_payloads, membership)
    try:
        frozen = m9b.prepare_candidates(records=records, membership_count=MEMBERSHIP_COUNT, blinding_key=secret)
    except m9b.CandidatePreparationError as exc:
        raise PreparationError(f"frozen M9B-2 preparation refused production records: {exc}") from exc
    upload = frozen["candidate_upload"]
    m9b_key = frozen["private_membership_key"]
    source_key, selection = selected_source_key(upload, m9b_key, sources)
    target = target_settings()
    expected = expected_cells(upload)
    run = run_sheet(upload, m9b_key, source_key, expected, target)
    manifest = preparation_manifest(accounting, selection, upload, m9b_key, source_key, expected, target, run)
    validation = validation_report(upload, m9b_key, source_key, expected, selection)
    read_me = readme(upload, m9b_key, source_key)
    public_files = {
        "README.md": read_me,
        "records/expected_cell_manifest.json": expected,
        "records/preparation_manifest.json": manifest,
        "records/run_sheet.json": run,
        "records/target_settings.json": target,
        "records/validation_report.json": validation,
        "upload/candidate_upload.csv": upload,
    }
    public_files["SHA256SUMS"] = sha_manifest(public_files)
    restricted_files = {
        "blinding_secret.bin": secret,
        "m9b2_private_membership_key.jsonl": m9b_key,
        "source_candidate_key.json": source_key,
    }
    restricted_files["SHA256SUMS"] = sha_manifest(restricted_files)
    publish_directory(restricted_package, restricted_files, set(restricted_files))
    publish_directory(public_package, public_files, {"upload/candidate_upload.csv"})
    return {
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "package_id": PACKAGE_ID,
        "condition_memberships": 800,
        "upload_rows": selection["upload_rows"],
        "d1_selected_by_training_seed": selection["d1_selected_by_training_seed"],
        "candidate_upload_sha256": sha256_bytes(upload),
        "m9b2_private_membership_key_sha256": sha256_bytes(m9b_key),
        "source_candidate_key_sha256": sha256_bytes(source_key),
        "preparation_manifest_sha256": sha256_bytes(manifest),
        "validation_report_sha256": sha256_bytes(validation),
        "public_package": str(public_package),
        "restricted_package": str(restricted_package),
        "aptarank_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--public-package", required=True, type=Path)
    parser.add_argument("--restricted-package", required=True, type=Path)
    parser.add_argument("--secret-file", required=True, type=Path)
    args = parser.parse_args()
    result = prepare(
        args.repo.resolve(), args.public_package.resolve(), args.restricted_package.resolve(), args.secret_file.resolve()
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Prepare the frozen 30,000-member D1 AptaRank production package.

This adapter preserves every frozen unique-valid D1 sequence, including rows
outside AptaRank's 20--100 nt scoring range so the deployed UI can record its
technical exclusions. It assigns fresh M9B-2 opaque IDs, retains complete
restricted provenance, and writes the v3.8 NDM-1 Evaluation-preset run sheet.
It does not run AptaRank, score a candidate, or build the review pool.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import secrets
from collections import Counter, defaultdict
from pathlib import Path

try:
    from scripts.modelling import aptarank_candidate_preparation as m9b
    from scripts.modelling import aptarank_section9_prepare_candidates as section9
except ModuleNotFoundError:
    import aptarank_candidate_preparation as m9b
    import aptarank_section9_prepare_candidates as section9


PACKAGE_ID = "section10_d1_full_pool_ndm1_evaluation_preset_v1"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_8.md"
PLAN_SHA256 = "8cf982180663ad8591583bd5e37613be4ce8234cfc8a2b82822a36b756d661dc"
V37_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_7.md"
V37_SHA256 = "24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9"
REFERENCE_RELATIVE = "data/aptarank_eval/reference/m9c_reference_upload_attempt3.csv"
REFERENCE_SHA256 = "5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6"
REFERENCE_ROWS = 113
SOURCE_RELATIVE = (
    "results/fine_tuning/generated_sequence_pools/frozen_m9_export_v1/"
    "valid_unique_candidate_sources/D1_valid_unique_rna.csv"
)
SOURCE_SHA256 = "9b6cfb6c6e0d1cb1f7d7c3446843c193ac7934751c0394561655c132e7d5d612"
SOURCE_ROWS = 30000
MEMBERSHIP_RELATIVE = (
    "results/fine_tuning/generated_sequence_pools/frozen_m9_export_v1/"
    "private_provenance/valid_attempt_membership.jsonl"
)
MEMBERSHIP_SHA256 = "a04342d73f6037eb9b38a9e20a2f35d7c3cfcbfd5cfef71562feca90a3e95fe6"
MEMBERSHIP_ROWS = 120080
ATTEMPT_ROWS_BY_CONDITION = {"B0": 30080, "B1": 30000, "B2": 30000, "D1": 30000}
M9B_CONTRACT_RELATIVE = "config/modelling/aptarank_candidate_preparation_contract.json"
M9B_CONTRACT_SHA256 = "3bcfbdf14cd7e777a0b2746f91d0335ba4876195f5012610157e5aa23e083096"
M9B_MODULE_RELATIVE = "scripts/modelling/aptarank_candidate_preparation.py"
M9B_MODULE_SHA256 = "a4f5b047f2803e775d9521c226287487412495055446e192681957c3d42879ca"
SECTION9_PREPARER_RELATIVE = "scripts/modelling/aptarank_section9_prepare_candidates.py"
SECTION9_PREPARER_SHA256 = "e0f4f2f334ff635f0ee8a7e280d694c1c4729c106baaae8f35be00bb43a5dd13"
M9C_SUMMARY_RELATIVE = (
    "results/fine_tuning/m9_generator_evaluation/m9c_live_deployment_validation/"
    "m9c_live_deployment_validation_summary.json"
)
M9C_SUMMARY_SHA256 = "2abc4af0df4907bd96187c269b2ef2dd0bac32c3137b0dc8f8cb3687f203e4f4"
TARGET_TEXT_RELATIVE = "target/artifacts/ndm1_5zgx_fpocket4/aptarank_target_5zgx.txt"
TARGET_TEXT_SHA256 = "46471bb0643125ce86300ec050d6f0d3a09faa1d06dc325141c67cd1acdd5922"
TARGET_PROVENANCE_RELATIVE = "target/artifacts/ndm1_5zgx_fpocket4/target_configuration.json"
TARGET_PROVENANCE_SHA256 = "08f0c96af349ce4909d40c3004804317661777f72828cd807823341e0e4f0d04"
SECTION8_CLOSURE_RELATIVE = (
    "results/aptarank/evaluation/section8_two_target_panel_evaluation_preset_v1/"
    "closure/section8_closure_record.json"
)
SECTION8_CLOSURE_SHA256 = "7de67471948c0630595342879c5da4fd091442271cf462321fc624eb139b5da8"
SECTION9_SUMMARY_RELATIVE = (
    "results/aptarank/evaluation/section9_generated_conditions_ndm1_evaluation_preset_v1/"
    "derived/analysis_v1/analysis_summary.json"
)
SECTION9_SUMMARY_SHA256 = "391e4cc2489965aa8465ff2c6eb99d9adac7b9f908aa50d6686dfcecec4c109f"
SECTION9_VISUAL_RELATIVE = (
    "results/aptarank/evaluation/section9_generated_conditions_ndm1_evaluation_preset_v1/"
    "records/pdf_visual_review.json"
)
SECTION9_VISUAL_SHA256 = "64fa94ef3e4dac03f684e763b572e239c8c4b2393f48f6fc3428f63748d2b6bc"

EXPECTED_COUNTS = {
    "upload_rows": 30000,
    "length_below_20": 11,
    "length_20_through_100": 29583,
    "length_above_100": 406,
    "training_seed_43": 15000,
    "training_seed_44": 15000,
    "technical_block_A": 15000,
    "technical_block_B": 15000,
}
OPAQUE_ID = re.compile(r"cand_[0-9a-f]{32}\Z")


class Section10PreparationError(RuntimeError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def byte_record(payload: bytes) -> dict[str, object]:
    return {"sha256": sha256_bytes(payload), "byte_count": len(payload)}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def pinned(path: Path, expected: str) -> bytes:
    payload = section9.read_regular(path)
    observed = sha256_bytes(payload)
    if observed != expected:
        raise Section10PreparationError(f"hash mismatch for {path}: expected {expected}, observed {observed}")
    return payload


def build_full_d1_records(source_payload: bytes, membership_payload: bytes) -> tuple[list[dict[str, object]], dict[str, dict[str, object]], dict[str, object]]:
    sources = section9.parse_source("D1", source_payload)
    if len(sources) != SOURCE_ROWS:
        raise Section10PreparationError("D1 source denominator drifted")

    occurrences: dict[str, list[dict[str, object]]] = defaultdict(list)
    indexes: dict[str, set[int]] = defaultdict(set)
    first_counts: Counter[str] = Counter()
    condition_rows: Counter[str] = Counter()
    record_ids: set[str] = set()
    try:
        lines = membership_payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise Section10PreparationError("attempt-membership sidecar is not UTF-8") from exc
    if len(lines) != MEMBERSHIP_ROWS or any(not line for line in lines):
        raise Section10PreparationError("attempt-membership sidecar denominator drifted")

    for line_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Section10PreparationError(f"attempt-membership row {line_number} is invalid JSON") from exc
        if not isinstance(row, dict):
            raise Section10PreparationError("attempt-membership row is not an object")
        condition = row.get("condition")
        if condition not in section9.CONDITIONS:
            raise Section10PreparationError("attempt-membership condition is invalid")
        condition_rows[str(condition)] += 1
        record_id = row.get("record_id")
        if not isinstance(record_id, str) or not record_id or record_id in record_ids:
            raise Section10PreparationError("attempt-membership record ID is missing or duplicated")
        record_ids.add(record_id)
        if condition != "D1":
            continue

        source_id = row.get("source_candidate_id")
        if source_id not in sources:
            raise Section10PreparationError("D1 attempt membership does not join to the frozen source")
        source = sources[str(source_id)]
        if row.get("multiplicity_group") != source_id:
            raise Section10PreparationError("D1 multiplicity group drifted")
        if section9.integer(row.get("condition_multiplicity"), "D1 multiplicity", 1) != source["multiplicity"]:
            raise Section10PreparationError("D1 multiplicity drifted")
        if section9.integer(row.get("parsed_length"), "D1 parsed length", 1) != source["length"]:
            raise Section10PreparationError("D1 parsed length drifted")
        if row.get("first_record_id") != source["first_record_id"] or row.get("is_valid_canonical") is not True:
            raise Section10PreparationError("D1 first-record or validity provenance drifted")
        index = section9.integer(row.get("occurrence_index"), "D1 occurrence index", 1)
        if index in indexes[str(source_id)]:
            raise Section10PreparationError("D1 occurrence index is duplicated")
        indexes[str(source_id)].add(index)
        if row.get("is_first_occurrence") is True:
            first_counts[str(source_id)] += 1
            if record_id != source["first_record_id"]:
                raise Section10PreparationError("D1 first occurrence does not match first_record_id")
        provenance = section9.provenance_for("D1", row)
        if not isinstance(provenance["source_artifact_id"], str) or section9.SHA256_TEXT.fullmatch(str(provenance["source_artifact_sha256"])) is None:
            raise Section10PreparationError("D1 source-artifact provenance is invalid")
        occurrences[str(source_id)].append({"source_identity": record_id, "provenance": provenance})

    if condition_rows != Counter(ATTEMPT_ROWS_BY_CONDITION):
        raise Section10PreparationError("attempt-membership condition counts drifted")

    normalized: list[dict[str, object]] = []
    source_by_sequence: dict[str, dict[str, object]] = {}
    seed_counts: Counter[str] = Counter()
    block_counts: Counter[str] = Counter()
    length_counts: Counter[str] = Counter()
    for source_id, source in sources.items():
        expected_indexes = set(range(1, int(source["multiplicity"]) + 1))
        if indexes[source_id] != expected_indexes or first_counts[source_id] != 1:
            raise Section10PreparationError("D1 occurrence accounting does not reconcile")
        frozen_occurrences = m9b._freeze_occurrences("D1", int(source["multiplicity"]), occurrences[source_id])
        row = {
            "condition": "D1",
            "sequence": source["sequence"],
            "length": source["length"],
            "comparison_role": m9b.COMPARISON_ROLES["D1"],
            "multiplicity": len(frozen_occurrences),
            "source_occurrences": frozen_occurrences,
        }
        seed = str(m9b._membership_training_seed(row))
        blocks = {str(item["provenance"]["technical_block"]) for item in frozen_occurrences}
        if len(blocks) != 1:
            raise Section10PreparationError("D1 source membership maps to multiple technical blocks")
        seed_counts[seed] += 1
        block_counts[next(iter(blocks))] += 1
        length = int(source["length"])
        if length < 20:
            length_counts["below"] += 1
        elif length > 100:
            length_counts["above"] += 1
        else:
            length_counts["inside"] += 1
        normalized.append(row)
        source_by_sequence[str(source["sequence"])] = {**source, "source_candidate_id": source_id}

    observed = {
        "upload_rows": len(normalized),
        "length_below_20": length_counts["below"],
        "length_20_through_100": length_counts["inside"],
        "length_above_100": length_counts["above"],
        "training_seed_43": seed_counts["43"],
        "training_seed_44": seed_counts["44"],
        "technical_block_A": block_counts["A"],
        "technical_block_B": block_counts["B"],
    }
    if observed != EXPECTED_COUNTS:
        raise Section10PreparationError(f"D1 full-pool accounting drifted: {observed!r}")
    return normalized, source_by_sequence, observed


def validate_upload(upload: bytes, ids: dict[str, str], source_by_sequence: dict[str, dict[str, object]]) -> list[dict[str, str]]:
    if b"\r" in upload:
        raise Section10PreparationError("candidate upload contains a carriage return")
    reader = csv.DictReader(io.StringIO(upload.decode("utf-8"), newline=""))
    if tuple(reader.fieldnames or ()) != ("id", "sequence"):
        raise Section10PreparationError("candidate upload schema drifted")
    rows = list(reader)
    if len(rows) != SOURCE_ROWS:
        raise Section10PreparationError("candidate upload does not contain 30,000 rows")
    seen_ids: set[str] = set()
    seen_sequences: set[str] = set()
    for row in rows:
        candidate, sequence = row["id"], row["sequence"]
        if OPAQUE_ID.fullmatch(candidate) is None or candidate != ids.get(sequence):
            raise Section10PreparationError("candidate upload opaque ID drifted")
        if sequence not in source_by_sequence or not sequence or set(sequence) - set("ACGU"):
            raise Section10PreparationError("candidate upload sequence drifted")
        if candidate in seen_ids or sequence in seen_sequences:
            raise Section10PreparationError("candidate upload ID or sequence is duplicated")
        seen_ids.add(candidate)
        seen_sequences.add(sequence)
    if seen_sequences != set(source_by_sequence):
        raise Section10PreparationError("candidate upload is incomplete")
    return rows


def build_source_candidate_key(upload_rows: list[dict[str, str]], private_key: bytes, source_by_sequence: dict[str, dict[str, object]]) -> bytes:
    private_rows = [json.loads(line) for line in private_key.decode("utf-8").splitlines()]
    by_id = {row["candidate_id"]: row for row in private_rows}
    memberships = []
    for row in upload_rows:
        private = by_id.get(row["id"])
        source = source_by_sequence[row["sequence"]]
        if private is None or private["length"] != source["length"] or private["multiplicity"] != source["multiplicity"]:
            raise Section10PreparationError("private membership key does not reconcile to source")
        memberships.append({
            "candidate_id": row["id"],
            "condition": "D1",
            "source_candidate_id": source["source_candidate_id"],
            "sequence_sha256": sha256_bytes(row["sequence"].encode("ascii")),
            "length": source["length"],
            "multiplicity": source["multiplicity"],
            "source_record_ids": [item["source_identity"] for item in private["source_occurrences"]],
        })
    if len(memberships) != len(upload_rows) or len(by_id) != len(upload_rows):
        raise Section10PreparationError("restricted source-key denominator drifted")
    return canonical_json({
        "schema_version": "mres-aptarank-section10-source-candidate-key-v1",
        "status": "RESTRICTED_DO_NOT_UPLOAD_OR_COMMIT",
        "package_id": PACKAGE_ID,
        "join_key": "candidate_id",
        "sequence_strings_included": False,
        "memberships": memberships,
    })


def expected_cells(upload_rows: list[dict[str, str]]) -> bytes:
    return canonical_json({
        "schema_version": "mres-aptarank-section10-expected-cells-v1",
        "package_id": PACKAGE_ID,
        "candidate_id_export_field": "candidate",
        "uploaded_candidate_ids": [row["id"] for row in upload_rows],
        "uploaded_rows": SOURCE_ROWS,
        "expected_input_length_accounting": {
            "below_20": EXPECTED_COUNTS["length_below_20"],
            "within_20_100": EXPECTED_COUNTS["length_20_through_100"],
            "above_100": EXPECTED_COUNTS["length_above_100"],
        },
        "returned_row_policy": "validate every returned row by opaque ID; record exported, excluded and missing rows separately; never infer a rejection reason for a missing row",
        "shortlist_limit_policy": "record the deployed export limit exactly if fewer rows are returned than valid scored candidates; do not treat unexported rows as technical failures",
        "aptamer_likeness": "finite decimal in closed interval [0,1]",
        "compatibility_allowed_tokens": ["strong", "moderate", "weak"],
        "shuffle_allowed_tokens": ["pass", "fail"],
    })


def target_settings() -> bytes:
    return canonical_json({
        "schema_version": "mres-aptarank-section10-target-settings-v1",
        "package_id": PACKAGE_ID,
        "target": "NDM-1",
        "pdb_id": "5ZGX",
        "chain": "A",
        "binding_mode": "pocket",
        "recognition_interpretation": "pocket/groove recognition",
        "target_site_residues": [120, 122, 124, 189, 208, 250],
        "prepared_target_identifier": "0fde4d5e4370",
        "target_configuration": {"path": TARGET_TEXT_RELATIVE, "sha256": TARGET_TEXT_SHA256},
        "target_preparation_provenance": {"path": TARGET_PROVENANCE_RELATIVE, "sha256": TARGET_PROVENANCE_SHA256},
        "required_warning_from_section9": "This cavity is oddly shaped: its robust extent and equivalent-sphere diameter disagree by more than 2\u00d7. The geometric comparison assumes a roughly convex pocket.",
        "interpretation_boundary": "Target compatibility is a coarse computational eligibility annotation, not binding, affinity, specificity, inhibition or experimental validation.",
    })


def review_pool_rule() -> bytes:
    return canonical_json({
        "schema_version": "mres-aptarank-section10-review-pool-rule-v1",
        "status": "FROZEN_BEFORE_SECTION10_APTARANK_RUN",
        "package_id": PACKAGE_ID,
        "governing_plan": {"path": PLAN_RELATIVE, "sha256": PLAN_SHA256},
        "eligibility": [
            "valid_scored_D1_candidate",
            "shuffle_token_is_pass",
            "compatibility_token_is_strong_or_moderate_pooled_as_one_favourable_class",
        ],
        "ordering": [
            "better_Tier_1_rank_across_pooled_favourable_class",
            "ascending_stable_opaque_candidate_id_on_exact_Tier_1_tie",
        ],
        "maximum_pool_size": 100,
        "minimum_pool_size": None,
        "desired_review_workload": "50-100; fewer than 50 does not permit criterion relaxation",
        "strong_precedes_moderate": False,
        "compatibility_token_retained_in_review_table": True,
        "combined_tier1_tier2_numeric_score": False,
        "technical_exclusions_replaced": False,
    })


def run_sheet(upload: bytes, private_key: bytes, source_key: bytes, expected: bytes, target: bytes, rule: bytes) -> bytes:
    return canonical_json({
        "schema_version": "mres-aptarank-section10-run-sheet-v1",
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "package_id": PACKAGE_ID,
        "operator": "Laura",
        "deployment": {"aptarank_version": "0.1.0", "schema_version": "1.0.0", "git_revision": "49a85609e352"},
        "settings": {
            "preset": "Evaluation",
            "seed": 42,
            "candidate_shuffled_controls": 99,
            "ensemble_samples": 200,
            "composite_method": "corpus_weighted_mean",
            "expected_scoring_signature": "95a49467ef3c6186",
        },
        "inputs": {
            "candidate_upload": {**byte_record(upload), "path": "upload/candidate_upload.csv", "row_count": SOURCE_ROWS},
            "reference_upload": {"path": REFERENCE_RELATIVE, "sha256": REFERENCE_SHA256, "row_count": REFERENCE_ROWS},
            "m9b2_private_membership_key": {**byte_record(private_key), "restricted": True},
            "source_candidate_key": {**byte_record(source_key), "restricted": True},
            "expected_cell_manifest": {**byte_record(expected), "path": "records/expected_cell_manifest.json"},
            "target_settings": {**byte_record(target), "path": "records/target_settings.json"},
            "review_pool_rule": {**byte_record(rule), "path": "records/review_pool_rule.json"},
        },
        "manual_steps": [
            "Upload the frozen 113-row attempt-3 reference CSV.",
            "Upload only upload/candidate_upload.csv from this package; it contains all 30000 frozen D1 sequences.",
            "Configure NDM-1, PDB 5ZGX, chain A, pocket mode and residues 120, 122, 124, 189, 208 and 250.",
            "Confirm prepared-target identifier 0fde4d5e4370; stop if it differs.",
            "Select Evaluation and confirm seed 42, 99 candidate shuffles and 200 sampled structures; stop if any effective setting differs.",
            "Run the upload once. Do not remove, replace or replenish a candidate because of length or any returned outcome.",
            "Download the untouched shortlist CSV, exclusion register, result PDF and every available raw artifact.",
            "Record uploaded, scored, exported, excluded and otherwise missing counts separately, including any deployed shortlist export limit.",
        ],
        "reporting": {
            "tier1_and_tier2_separate": True,
            "combined_score": False,
            "review_pool_built_only_after_export_validation": True,
            "compatibility_bands_pooled_for_eligibility": ["strong", "moderate"],
            "primary_ordering": "Tier_1_rank",
        },
    })


def preparation_manifest(accounting: dict[str, object], upload: bytes, private_key: bytes, source_key: bytes, expected: bytes, target: bytes, rule: bytes, run: bytes) -> bytes:
    return canonical_json({
        "schema_version": "mres-aptarank-section10-preparation-manifest-v1",
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "package_id": PACKAGE_ID,
        "aptarank_executed": False,
        "scientific_result": False,
        "pins": {
            "governing_plan": {"path": PLAN_RELATIVE, "sha256": PLAN_SHA256},
            "historical_v3_7_plan": {"path": V37_RELATIVE, "sha256": V37_SHA256},
            "reference_upload": {"path": REFERENCE_RELATIVE, "sha256": REFERENCE_SHA256},
            "D1_source": {"path": SOURCE_RELATIVE, "sha256": SOURCE_SHA256},
            "attempt_membership": {"path": MEMBERSHIP_RELATIVE, "sha256": MEMBERSHIP_SHA256},
            "M9B_2_contract": {"path": M9B_CONTRACT_RELATIVE, "sha256": M9B_CONTRACT_SHA256},
            "M9B_2_module": {"path": M9B_MODULE_RELATIVE, "sha256": M9B_MODULE_SHA256},
            "section9_preparation_module": {"path": SECTION9_PREPARER_RELATIVE, "sha256": SECTION9_PREPARER_SHA256},
            "deployed_target_record": {"path": M9C_SUMMARY_RELATIVE, "sha256": M9C_SUMMARY_SHA256},
            "target_configuration": {"path": TARGET_TEXT_RELATIVE, "sha256": TARGET_TEXT_SHA256},
            "target_preparation_provenance": {"path": TARGET_PROVENANCE_RELATIVE, "sha256": TARGET_PROVENANCE_SHA256},
            "section8_closure": {"path": SECTION8_CLOSURE_RELATIVE, "sha256": SECTION8_CLOSURE_SHA256},
            "section9_provisional_summary": {"path": SECTION9_SUMMARY_RELATIVE, "sha256": SECTION9_SUMMARY_SHA256},
            "section9_pdf_visual_review": {"path": SECTION9_VISUAL_RELATIVE, "sha256": SECTION9_VISUAL_SHA256},
        },
        "full_pool": {
            **accounting,
            "sampling_or_score_informed_selection": False,
            "pre_upload_length_filter": False,
            "technical_exclusions_replaced": False,
        },
        "opaque_id": {
            "algorithm": "HMAC-SHA-256",
            "domain_separator": m9b.ID_DOMAIN,
            "key_length_bytes": 32,
            "truncation_bytes": m9b.TRUNCATION_BYTES,
            "fresh_secret_generated_for_package": True,
            "secret_in_public_package": False,
        },
        "artifacts": {
            "candidate_upload": byte_record(upload),
            "restricted_m9b2_private_membership_key": byte_record(private_key),
            "restricted_source_candidate_key": byte_record(source_key),
            "expected_cell_manifest": byte_record(expected),
            "target_settings": byte_record(target),
            "review_pool_rule": byte_record(rule),
            "run_sheet": byte_record(run),
        },
    })


def validation_report(accounting: dict[str, object], upload: bytes, private_key: bytes, source_key: bytes, expected: bytes, rule: bytes) -> bytes:
    upload_rows = list(csv.DictReader(io.StringIO(upload.decode("utf-8"), newline="")))
    private_rows = [json.loads(line) for line in private_key.decode("utf-8").splitlines()]
    source_document = json.loads(source_key)
    expected_document = json.loads(expected)
    rule_document = json.loads(rule)
    upload_ids = {row["id"] for row in upload_rows}
    if {row["candidate_id"] for row in private_rows} != upload_ids:
        raise Section10PreparationError("private membership key does not reconcile to upload")
    if {row["candidate_id"] for row in source_document["memberships"]} != upload_ids:
        raise Section10PreparationError("source candidate key does not reconcile to upload")
    if set(expected_document["uploaded_candidate_ids"]) != upload_ids:
        raise Section10PreparationError("expected-cell manifest does not reconcile to upload")
    if rule_document["strong_precedes_moderate"] is not False or rule_document["ordering"][0] != "better_Tier_1_rank_across_pooled_favourable_class":
        raise Section10PreparationError("v3.8 review-pool ordering drifted")
    return canonical_json({
        "schema_version": "mres-aptarank-section10-preflight-v1",
        "status": "PASS",
        "package_id": PACKAGE_ID,
        "aptarank_executed": False,
        "checks": {
            "all_pinned_hashes_match": True,
            "all_30000_frozen_D1_sequences_preserved": True,
            "no_pre_upload_length_filter": True,
            "attempt_membership_and_multiplicity_reconcile": True,
            "training_seed_and_technical_block_counts_reconcile": True,
            "fresh_M9B_2_opaque_ids_are_unique_and_reproducible_from_restricted_secret": True,
            "upload_private_keys_and_expected_cells_reconcile": True,
            "reference_target_and_evaluation_preset_are_frozen": True,
            "v3_8_pooled_band_Tier_1_primary_rule_is_frozen": True,
            "strong_before_moderate_ordering_is_refused": True,
            "score_used_for_upload_membership": False,
            "aptarank_called": False,
        },
        "denominators": accounting,
        "artifacts": {
            "candidate_upload": byte_record(upload),
            "restricted_m9b2_private_membership_key": byte_record(private_key),
            "restricted_source_candidate_key": byte_record(source_key),
            "expected_cell_manifest": byte_record(expected),
            "review_pool_rule": byte_record(rule),
        },
    })


def readme(upload: bytes, private_key: bytes, source_key: bytes) -> bytes:
    return (
        f"# {PACKAGE_ID}\n\n"
        "Status: `PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN`\n\n"
        "This package contains a fresh blinded upload of all 30,000 frozen D1 unique-valid RNA sequences. "
        "No sequence was sampled, prefiltered by length, replaced or selected by a score. The upload therefore "
        "includes 11 sequences below 20 nt and 406 above 100 nt so the deployed tool can record its technical "
        "exclusions.\n\n"
        "Upload only `upload/candidate_upload.csv` with the frozen 113-row attempt-3 REF and follow "
        "`records/run_sheet.json` exactly. Do not upload the restricted package. AptaRank was not run during "
        "preparation.\n\n"
        "The v3.8 review rule is frozen in `records/review_pool_rule.json`: shuffle `pass` and `strong` or "
        "`moderate` compatibility are mandatory gates; the favourable bands are pooled and Tier 1 rank supplies "
        "the primary order. The review pool is not constructed until the returned artifacts pass validation.\n\n"
        f"Candidate-upload SHA-256: `{sha256_bytes(upload)}`.\n\n"
        f"Restricted M9B-2 membership-key SHA-256: `{sha256_bytes(private_key)}`.\n\n"
        f"Restricted source-candidate-key SHA-256: `{sha256_bytes(source_key)}`.\n"
    ).encode("utf-8")


def sha_manifest(files: dict[str, bytes]) -> bytes:
    return "".join(f"{sha256_bytes(files[name])}  {name}\n" for name in sorted(files)).encode("ascii")


def prepare(repo: Path, public_package: Path, restricted_package: Path, *, secret: bytes | None = None) -> dict[str, object]:
    pinned(repo / PLAN_RELATIVE, PLAN_SHA256)
    pinned(repo / V37_RELATIVE, V37_SHA256)
    reference = pinned(repo / REFERENCE_RELATIVE, REFERENCE_SHA256)
    source_payload = pinned(repo / SOURCE_RELATIVE, SOURCE_SHA256)
    membership_payload = pinned(repo / MEMBERSHIP_RELATIVE, MEMBERSHIP_SHA256)
    for relative, digest in (
        (M9B_CONTRACT_RELATIVE, M9B_CONTRACT_SHA256),
        (M9B_MODULE_RELATIVE, M9B_MODULE_SHA256),
        (SECTION9_PREPARER_RELATIVE, SECTION9_PREPARER_SHA256),
        (M9C_SUMMARY_RELATIVE, M9C_SUMMARY_SHA256),
        (TARGET_TEXT_RELATIVE, TARGET_TEXT_SHA256),
        (TARGET_PROVENANCE_RELATIVE, TARGET_PROVENANCE_SHA256),
        (SECTION8_CLOSURE_RELATIVE, SECTION8_CLOSURE_SHA256),
        (SECTION9_SUMMARY_RELATIVE, SECTION9_SUMMARY_SHA256),
        (SECTION9_VISUAL_RELATIVE, SECTION9_VISUAL_SHA256),
    ):
        pinned(repo / relative, digest)
    if len(list(csv.DictReader(io.StringIO(reference.decode("utf-8"), newline="")))) != REFERENCE_ROWS:
        raise Section10PreparationError("reference row count drifted")
    m9b.load_pinned_contract()

    records, sources, accounting = build_full_d1_records(source_payload, membership_payload)
    key = secrets.token_bytes(32) if secret is None else secret
    if type(key) is not bytes or len(key) != 32:
        raise Section10PreparationError("fresh blinding secret must be exactly 32 bytes")
    sequences = sorted(sources, key=lambda value: value.encode("utf-8"))
    ids = m9b.assign_candidate_ids(sequences, key, m9b.TRUNCATION_BYTES)
    upload = m9b._candidate_upload_bytes(sequences, ids)
    upload_rows = validate_upload(upload, ids, sources)
    private_key = m9b._private_key_bytes(records, ids)
    source_key = build_source_candidate_key(upload_rows, private_key, sources)
    expected = expected_cells(upload_rows)
    target = target_settings()
    rule = review_pool_rule()
    run = run_sheet(upload, private_key, source_key, expected, target, rule)
    manifest = preparation_manifest(accounting, upload, private_key, source_key, expected, target, rule, run)
    validation = validation_report(accounting, upload, private_key, source_key, expected, rule)
    read_me = readme(upload, private_key, source_key)

    public_files = {
        "README.md": read_me,
        "records/expected_cell_manifest.json": expected,
        "records/preparation_manifest.json": manifest,
        "records/review_pool_rule.json": rule,
        "records/run_sheet.json": run,
        "records/target_settings.json": target,
        "records/validation_report.json": validation,
        "upload/candidate_upload.csv": upload,
    }
    public_files["SHA256SUMS"] = sha_manifest(public_files)
    restricted_files = {
        "blinding_secret.bin": key,
        "m9b2_private_membership_key.jsonl": private_key,
        "source_candidate_key.json": source_key,
    }
    restricted_files["SHA256SUMS"] = sha_manifest(restricted_files)

    section9.publish_directory(restricted_package, restricted_files, set(restricted_files))
    section9.publish_directory(public_package, public_files, {"upload/candidate_upload.csv"})
    return {
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "package_id": PACKAGE_ID,
        "upload_rows": SOURCE_ROWS,
        "length_accounting": accounting,
        "candidate_upload_sha256": sha256_bytes(upload),
        "m9b2_private_membership_key_sha256": sha256_bytes(private_key),
        "source_candidate_key_sha256": sha256_bytes(source_key),
        "preparation_manifest_sha256": sha256_bytes(manifest),
        "review_pool_rule_sha256": sha256_bytes(rule),
        "run_sheet_sha256": sha256_bytes(run),
        "validation_report_sha256": sha256_bytes(validation),
        "public_package": str(public_package),
        "restricted_package": str(restricted_package),
        "aptarank_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--public-package", type=Path, required=True)
    parser.add_argument("--restricted-package", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.repo.resolve(), args.public_package.resolve(), args.restricted_package.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

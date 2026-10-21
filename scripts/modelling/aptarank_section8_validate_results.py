#!/usr/bin/env python3
"""Fail-closed technical validation for the two Section 8 AptaRank runs.

The deployed AptaRank UI remains the scorer. This adapter verifies the frozen
inputs, exact candidate joins, raw artifact bytes, export schema and values,
and a separately recorded visual review of each pinned result PDF. It writes
sequence-free validation outputs only. It does not reconstruct a numeric Tier
2 score, compare the two target modes, interpret the results, or commit them as
scientific findings.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import stat
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_7.md"
PLAN_SHA256 = "24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9"
PREPARATION_RELATIVE = "scripts/modelling/aptarank_section8_prepare_candidates.py"
PREPARATION_SHA256 = "952d201b81bfd6c1939577f20530dc52d13d7eec86b032ddece4c77863558e78"
REFERENCE_RELATIVE = "data/aptarank_eval/reference/m9c_reference_upload_attempt3.csv"
REFERENCE_SHA256 = "5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6"
REFERENCE_ROWS = 113
REFERENCE_FIELDS = ("id", "sequence", "target_name", "target_pdb_id")
PRIVATE_MANIFEST_SHA256 = "192d1973a718d049135b0be54d24891fdf5ccec3a8315b54a238eabfe4341f0a"
PANEL_ID = "section8_two_target_panel_v1"
STATUS = "SECTION8_TECHNICAL_VALIDATION_PASS_INTERPRETATION_AND_COMMITMENT_PENDING"
EXPORT_FIELDS = (
    "rank",
    "candidate",
    "aptamer-likeness",
    "compatibility",
    "shuffle",
    "len",
    "sequence",
)
UPLOAD_FIELDS = ("id", "sequence")
COMPATIBILITY_TOKENS = {"strong", "moderate", "weak"}
SHUFFLE_TOKENS = {"pass", "fail"}
CANDIDATE_ID = re.compile(r"cand_[0-9a-f]{32}\Z")
CANDIDATE_TOKEN_BYTES = re.compile(rb"cand_[0-9a-f]{32}")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


CASES = (
    {
        "case_id": "grk2_pocket",
        "case_label": "GRK2/3UZS pocket-mode descriptive case",
        "case_role": "pocket_mode_descriptive_case",
        "package_id": "section8_grk2_tier2_evaluation_preset_v2",
        "public_package": "data/aptarank_eval/sequence/section8_grk2_tier2_evaluation_preset_v2",
        "public_manifest_sha256": "f73eab1cc7f3408b8f78caedd959b76455158ef5d2d39a88564797cbabda6682",
        "upload_sha256": "e7589866fb3322eb3d9ea90a8276d613720ff9d64e59bfed6f7cb47433b9572f",
        "expected_cells_sha256": "c001e821ec44e8e25dd9228824039646027b80d0759ca87ce17ae927a870951c",
        "preparation_manifest_sha256": "f5123fc36f01e5a217538229ce6cd1b405155ef73abb6ca90b27568900e7550c",
        "preflight_sha256": "0a1ad6e6eafcf6c9c319148eaaa527cac61416c34ce8124d8c3ad133c9ac32b9",
        "run_sheet_sha256": "78c196b54d9a1d021820c8c6b2f1b0fafacd48e6ff220a2e15c2fe03c258ec83",
        "private_key_name": "grk2_pocket_private_key.json",
        "private_key_sha256": "d596a7465f633904039177db6f638d080b234f7d00959b04ee4609e1d1e0418f",
        "target_package": "data/aptarank_eval/target/section8_grk2_3uzs_v2",
        "target_manifest_sha256": "1acb57d632b85e43dbabc685654269db73c7956161ffeaddd74b57c548dd1eae",
        "target_freeze_sha256": "49d1c32db6b460a20cda0e712cd3e31120aa17ec7f1ed0d30d6cae815de31d18",
        "target_config_sha256": "105a1625b268d174b088dc2a1d701d84892d1fa42409a51311393b2cca789bea",
        "structure_sha256": "ff0ef60bf3beaaaf634b6a0e8236575dba914b0caa4b32636b88c356bf390eb6",
        "result_directory": "results/aptarank/evaluation/section8_grk2_3uzs_evaluation_preset_v1",
        "raw_manifest_sha256": "826649e6200818f8a665eb40e60dff12b89d474f3d7971204dde36bf9d150389",
        "export_name": "run_3uzs_1021_shortlist.csv",
        "export_sha256": "d9ecbb4b3745b496832575bba7b9ccbcba5850dd838e178810fa8eea6fd644c7",
        "pdf_name": "section8_3uzs_1021.pdf",
        "pdf_sha256": "cec6ad469ccab822818f92aeee6addc15368ed54d6f99cfb07cf45754ac782fb",
        "visual_review_sha256": "8339fd8294aaea9b3760018cff41e5636777df4ec7f8447d3d547b0ee6eba43e",
        "target_config_id": "GRK2_3UZS_A_pocket",
        "pdb_id": "3UZS",
        "chain": "A",
        "binding_mode": "pocket",
        "identity_count": 1,
        "core_count": 1,
        "cluster_count": 1,
        "expected_lengths": [28],
    },
    {
        "case_id": "hewl_surface",
        "case_label": "HEWL/4M4O surface-mode descriptive case",
        "case_role": "surface_mode_descriptive_case",
        "package_id": "section8_lysozyme_tier2_evaluation_preset_v2",
        "public_package": "data/aptarank_eval/sequence/section8_lysozyme_tier2_evaluation_preset_v2",
        "public_manifest_sha256": "78c3e8b8ee4eaae5acec9b165108de99544cf6f3345d5e05fb81ca2146291329",
        "upload_sha256": "ade52448da9a6b8630f082df446745f28c649031df460c7b8eb13c4c9b47ab9d",
        "expected_cells_sha256": "c722d636c419170929ad404800ec7ffb9e1f17add9602bb5bf7db418ee8e6120",
        "preparation_manifest_sha256": "8aaa403b53e3d5a01e9522951421ab588fcdf671013ba296b867fc433d5a921f",
        "preflight_sha256": "5acc9d65d0f7f9db61a088b20193c9c3a076a17f16369b8d004e8242aad01264",
        "run_sheet_sha256": "25a65d353eda5fb4b3e1973a329a5b8667c8ce2651d3c4447810cba2f345949d",
        "private_key_name": "hewl_surface_private_key.json",
        "private_key_sha256": "b9b9c2abb19dd388bb2135d0fb4b1e2f80f6b8afda8a84e1ffa6f5df74589153",
        "target_package": "data/aptarank_eval/target/section8_lysozyme_4m4o_v1",
        "target_manifest_sha256": "2939ea3788c75cc4536e84f0c5a7ce4804876f3f47bb9ac86c177194300e8038",
        "target_freeze_sha256": "6d9e69b7f61488d610ac58b421b1f852ea866e65a8fa4d4d5aaa014798db320c",
        "target_config_sha256": "bad68b30e64b48fd069ed8e53d266d79a249039122774518b06ddd6f45de631a",
        "structure_sha256": "17613b6fc82483f823ad2e6eb6e5dfdf55b98a9dd2cd3b39b7490b61021a5ae6",
        "result_directory": "results/aptarank/evaluation/section8_lysozyme_4m4o_evaluation_preset_v1",
        "raw_manifest_sha256": "590f6df0f5b436ffdc0b3a4cd6ee72de8451fdc966c9ff9460a219dd7daf88b3",
        "export_name": "4m4o_1025.csv",
        "export_sha256": "1cea5620a0a1a938b454c6c4b612c105fa2423fe8eeb7e66e9cd9b706dc70a6a",
        "pdf_name": "4m4o_1025.pdf",
        "pdf_sha256": "114efec24fd3e25e92cc7b15d71b1abec7835b0201806d85ef918843a39d994c",
        "visual_review_sha256": "27448cd316fe03a09b5b3018bac1209fefc57c3b7e3c2a10709f3bea167f2171",
        "target_config_id": "HEWL_4M4O_A_surface",
        "pdb_id": "4M4O",
        "chain": "A",
        "binding_mode": "surface",
        "identity_count": 2,
        "core_count": 2,
        "cluster_count": 1,
        "expected_lengths": [45, 59],
    },
)


class Section8ValidationError(ValueError):
    """Raised when any frozen input or validation invariant fails."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def byte_record(payload: bytes) -> dict[str, object]:
    return {"sha256": sha256_bytes(payload), "byte_count": len(payload)}


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_regular(path: Path) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise Section8ValidationError(f"not a regular file: {path}")
    return path.read_bytes()


def read_pinned(path: Path, expected_sha256: str, role: str) -> bytes:
    payload = read_regular(path)
    observed = sha256_bytes(payload)
    if observed != expected_sha256:
        raise Section8ValidationError(
            f"{role} SHA-256 mismatch: expected {expected_sha256}, observed {observed}"
        )
    return payload


def parse_json(payload: bytes, role: str) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Section8ValidationError(f"{role} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise Section8ValidationError(f"{role} is not a JSON object")
    return value


def validate_sha256_manifest(manifest: bytes, base: Path, role: str) -> None:
    try:
        lines = manifest.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise Section8ValidationError(f"{role} is not ASCII") from exc
    if not lines:
        raise Section8ValidationError(f"{role} is empty")
    seen: set[str] = set()
    for line in lines:
        if len(line) < 67 or line[64:66] != "  ":
            raise Section8ValidationError(f"{role} does not use the two-space SHA256SUMS format")
        digest, relative = line[:64], line[66:]
        if not SHA256.fullmatch(digest) or not relative or relative in seen:
            raise Section8ValidationError(f"invalid or duplicate entry in {role}")
        seen.add(relative)
        path = base / relative
        payload = read_regular(path)
        if sha256_bytes(payload) != digest:
            raise Section8ValidationError(f"{role} entry mismatch for {relative}")


def parse_csv(payload: bytes, fields: tuple[str, ...], role: str) -> list[dict[str, str]]:
    if b"\r" in payload:
        raise Section8ValidationError(f"{role} contains a carriage return")
    try:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8"), newline=""))
    except UnicodeDecodeError as exc:
        raise Section8ValidationError(f"{role} is not UTF-8") from exc
    if tuple(reader.fieldnames or ()) != fields:
        raise Section8ValidationError(
            f"{role} fields are {reader.fieldnames!r}, expected {list(fields)!r}"
        )
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise Section8ValidationError(f"{role} contains malformed rows")
    return rows


def parse_upload(payload: bytes) -> tuple[list[dict[str, str]], dict[str, str]]:
    rows = parse_csv(payload, UPLOAD_FIELDS, "candidate upload")
    by_id: dict[str, str] = {}
    sequences: set[str] = set()
    for row in rows:
        candidate = row["id"]
        sequence = row["sequence"]
        if not CANDIDATE_ID.fullmatch(candidate):
            raise Section8ValidationError("candidate upload contains an invalid opaque id")
        if candidate in by_id or sequence in sequences:
            raise Section8ValidationError("candidate upload ids and sequences must be unique")
        if not sequence or set(sequence) - set("ACGU"):
            raise Section8ValidationError("candidate upload contains a noncanonical RNA sequence")
        by_id[candidate] = sequence
        sequences.add(sequence)
    return rows, by_id


def parse_score(value: str) -> Decimal:
    try:
        score = Decimal(value)
    except InvalidOperation as exc:
        raise Section8ValidationError("aptamer-likeness is not a decimal") from exc
    if not score.is_finite() or score < 0 or score > 1:
        raise Section8ValidationError("aptamer-likeness must be finite and in [0,1]")
    return score


def validate_export(
    payload: bytes,
    upload_by_id: dict[str, str],
) -> list[dict[str, object]]:
    rows = parse_csv(payload, EXPORT_FIELDS, "downloaded shortlist")
    if len(rows) != len(upload_by_id):
        raise Section8ValidationError("downloaded shortlist does not have one row per upload row")
    observed_ids = [row["candidate"] for row in rows]
    if len(observed_ids) != len(set(observed_ids)) or set(observed_ids) != set(upload_by_id):
        raise Section8ValidationError("downloaded shortlist candidate ids do not reconcile to upload")

    validated: list[dict[str, object]] = []
    for row in rows:
        candidate = row["candidate"]
        sequence = row["sequence"]
        if sequence != upload_by_id[candidate]:
            raise Section8ValidationError("downloaded shortlist sequence does not match upload")
        try:
            rank = int(row["rank"])
            length = int(row["len"])
        except ValueError as exc:
            raise Section8ValidationError("rank or length is not an integer") from exc
        if length != len(sequence):
            raise Section8ValidationError("downloaded shortlist length does not match sequence")
        score = parse_score(row["aptamer-likeness"])
        if row["compatibility"] not in COMPATIBILITY_TOKENS:
            raise Section8ValidationError("unexpected compatibility token")
        if row["shuffle"] not in SHUFFLE_TOKENS:
            raise Section8ValidationError("unexpected shuffle token")
        validated.append(
            {
                "candidate": candidate,
                "sequence": sequence,
                "rank": rank,
                "length": length,
                "score": score,
                "score_text": row["aptamer-likeness"],
                "compatibility": row["compatibility"],
                "shuffle": row["shuffle"],
            }
        )

    by_rank = sorted(validated, key=lambda row: row["rank"])
    if [row["rank"] for row in by_rank] != list(range(1, len(by_rank) + 1)):
        raise Section8ValidationError("export ranks are not complete 1 through N")
    expected_order = sorted(validated, key=lambda row: (-row["score"], row["candidate"]))
    if [row["candidate"] for row in by_rank] != [row["candidate"] for row in expected_order]:
        raise Section8ValidationError("export ranks do not follow score descending and id ascending on ties")
    return by_rank


def contains_key(value: object, forbidden: str) -> bool:
    if isinstance(value, dict):
        return forbidden in value or any(contains_key(item, forbidden) for item in value.values())
    if isinstance(value, list):
        return any(contains_key(item, forbidden) for item in value)
    return False


def validate_private_key(
    document: dict[str, object],
    case: dict[str, object],
    upload_by_id: dict[str, str],
) -> list[dict[str, object]]:
    expected_top = {
        "schema_version": "mres-aptarank-section8-private-key-v1",
        "status": "RESTRICTED_DO_NOT_UPLOAD_OR_COMMIT",
        "package_id": case["package_id"],
        "panel_id": PANEL_ID,
        "join_key": "candidate_id",
        "row_position_is_join_key": False,
        "sequence_strings_included": False,
    }
    for key, expected in expected_top.items():
        if document.get(key) != expected:
            raise Section8ValidationError(f"private key {key} does not match frozen expectation")
    if contains_key(document, "sequence"):
        raise Section8ValidationError("private key unexpectedly contains a sequence field")
    candidates = document.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != len(upload_by_id):
        raise Section8ValidationError("private key candidate count does not match upload")
    by_id: dict[str, dict[str, object]] = {}
    for row in candidates:
        if not isinstance(row, dict) or not isinstance(row.get("candidate_id"), str):
            raise Section8ValidationError("private key candidate row is malformed")
        candidate = row["candidate_id"]
        if candidate in by_id:
            raise Section8ValidationError("duplicate private-key candidate id")
        by_id[candidate] = row
    if set(by_id) != set(upload_by_id):
        raise Section8ValidationError("private-key ids do not reconcile to upload")
    for candidate, sequence in upload_by_id.items():
        row = by_id[candidate]
        expected = {
            "case_id": case["case_id"],
            "target_config_id": case["target_config_id"],
            "class_label": "eval_cognate_core",
            "sequence_core_sha256": sha256_bytes(sequence.encode("utf-8")),
            "length": len(sequence),
        }
        for key, value in expected.items():
            if row.get(key) != value:
                raise Section8ValidationError(f"private-key {key} does not match upload")
    return list(by_id.values())


def validate_run_sheet(
    document: dict[str, object],
    case: dict[str, object],
    upload: bytes,
    private_key: bytes,
    expected_cells: bytes,
) -> None:
    if document.get("schema_version") != "mres-aptarank-section8-run-sheet-v1":
        raise Section8ValidationError("run-sheet schema mismatch")
    if document.get("package_id") != case["package_id"] or document.get("panel_id") != PANEL_ID:
        raise Section8ValidationError("run-sheet package or panel mismatch")
    settings = document.get("settings")
    required_settings = {
        "preset": "Evaluation",
        "seed": 42,
        "candidate_shuffled_controls": 99,
        "ensemble_samples": 200,
        "composite_method": "corpus_weighted_mean",
    }
    if not isinstance(settings, dict):
        raise Section8ValidationError("run-sheet settings are missing")
    for key, expected in required_settings.items():
        if settings.get(key) != expected:
            raise Section8ValidationError(f"run-sheet setting {key} is not frozen rigorous value")
    target = document.get("target")
    if not isinstance(target, dict):
        raise Section8ValidationError("run-sheet target is missing")
    for key in ("target_config_id", "pdb_id", "chain", "binding_mode"):
        expected = case[key]
        if target.get(key) != expected:
            raise Section8ValidationError(f"run-sheet target {key} mismatch")
    if target.get("target_freeze_sha256") != case["target_freeze_sha256"]:
        raise Section8ValidationError("run-sheet target-freeze digest mismatch")
    if target.get("target_config_sha256") != case["target_config_sha256"]:
        raise Section8ValidationError("run-sheet target-config digest mismatch")
    if target.get("structure_sha256") != case["structure_sha256"]:
        raise Section8ValidationError("run-sheet structure digest mismatch")
    inputs = document.get("inputs")
    if not isinstance(inputs, dict):
        raise Section8ValidationError("run-sheet inputs are missing")
    expected_records = {
        "candidate_upload": byte_record(upload),
        "private_key": byte_record(private_key),
        "expected_cell_manifest": byte_record(expected_cells),
    }
    for role, record in expected_records.items():
        observed = inputs.get(role)
        if not isinstance(observed, dict):
            raise Section8ValidationError(f"run-sheet {role} record is missing")
        for key, value in record.items():
            if observed.get(key) != value:
                raise Section8ValidationError(f"run-sheet {role} {key} mismatch")
    reference = inputs.get("reference_upload")
    if not isinstance(reference, dict) or reference.get("sha256") != REFERENCE_SHA256 or reference.get("row_count") != REFERENCE_ROWS:
        raise Section8ValidationError("run-sheet reference record mismatch")


def validate_expected_cells(
    document: dict[str, object],
    case: dict[str, object],
    upload_by_id: dict[str, str],
) -> None:
    expected = {
        "schema_version": "mres-aptarank-section8-expected-cells-v1",
        "package_id": case["package_id"],
        "panel_id": PANEL_ID,
        "target_config_id": case["target_config_id"],
        "expected_candidate_count": len(upload_by_id),
        "expected_export_fields": list(EXPORT_FIELDS),
        "candidate_id_export_field": "candidate",
        "join_by_candidate_id": True,
        "row_position_is_join_key": False,
        "compatibility_allowed_tokens": ["strong", "moderate", "weak"],
        "shuffle_allowed_tokens": ["pass", "fail"],
        "raw_tier2_score": "capture only if an untouched deployed artifact exposes it; do not reconstruct",
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise Section8ValidationError(f"expected-cell {key} mismatch")
    ids = document.get("expected_candidate_ids")
    if not isinstance(ids, list) or len(ids) != len(set(ids)) or set(ids) != set(upload_by_id):
        raise Section8ValidationError("expected-cell candidate ids do not reconcile to upload")


def validate_raw_manifest(
    document: dict[str, object],
    case: dict[str, object],
    result_directory: Path,
    upload: bytes,
) -> None:
    if document.get("schema_version") != "mres-aptarank-raw-artifact-manifest-v1":
        raise Section8ValidationError("raw artifact manifest schema mismatch")
    if document.get("package_id") != case["package_id"]:
        raise Section8ValidationError("raw artifact manifest package mismatch")
    if document.get("candidate_upload_sha256") != sha256_bytes(upload):
        raise Section8ValidationError("raw artifact manifest upload digest mismatch")
    if document.get("reference_upload_sha256") != REFERENCE_SHA256:
        raise Section8ValidationError("raw artifact manifest reference digest mismatch")
    accounting = document.get("accounting")
    if not isinstance(accounting, dict):
        raise Section8ValidationError("raw artifact accounting is missing")
    for key in ("uploaded", "scored", "shortlist_rows"):
        if accounting.get(key) != case["core_count"]:
            raise Section8ValidationError(f"raw artifact accounting {key} mismatch")
    if accounting.get("input_join_pass") is not True:
        raise Section8ValidationError("raw artifact input join was not recorded as passing")
    artifacts = document.get("raw_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise Section8ValidationError("raw artifact list is incomplete")
    expected = {
        f"raw/{case['export_name']}": case["export_sha256"],
        f"raw/{case['pdf_name']}": case["pdf_sha256"],
    }
    observed: dict[str, str] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise Section8ValidationError("raw artifact record is malformed")
        path = artifact.get("path")
        digest = artifact.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise Section8ValidationError("raw artifact record lacks path or digest")
        payload = read_regular(result_directory / path)
        if digest != sha256_bytes(payload) or artifact.get("byte_count") != len(payload):
            raise Section8ValidationError(f"raw artifact record mismatch for {path}")
        observed[path] = digest
    if observed != expected:
        raise Section8ValidationError("raw artifact set does not match frozen case")


def validate_visual_review(
    document: dict[str, object],
    case: dict[str, object],
    pdf: bytes,
    rows: list[dict[str, object]],
    run_sheet: dict[str, object],
    raw_manifest: dict[str, object],
) -> dict[str, object]:
    if document.get("schema_version") != "mres-aptarank-section8-pdf-visual-review-v1":
        raise Section8ValidationError("PDF visual-review schema mismatch")
    if document.get("status") != "VISUALLY_REVIEWED_SOURCE_HASH_PINNED":
        raise Section8ValidationError("PDF visual review is not complete")
    if document.get("automated_content_extraction") is not False or document.get("layout_readable") is not True:
        raise Section8ValidationError("PDF visual-review evidence class is inconsistent")
    source = document.get("source_pdf")
    if not isinstance(source, dict) or source.get("sha256") != sha256_bytes(pdf) or source.get("byte_count") != len(pdf):
        raise Section8ValidationError("PDF visual review does not bind the exact source bytes")
    observations = document.get("visual_observations")
    if not isinstance(observations, dict):
        raise Section8ValidationError("PDF visual observations are missing")
    accounting = observations.get("accounting")
    if not isinstance(accounting, dict) or accounting.get("candidates") != len(rows) or accounting.get("scored") != len(rows):
        raise Section8ValidationError("PDF visual accounting does not match export")
    displayed = observations.get("displayed_settings")
    raw_settings = raw_manifest.get("displayed_settings")
    run_settings = run_sheet.get("settings")
    if not isinstance(displayed, dict) or not isinstance(raw_settings, dict) or not isinstance(run_settings, dict):
        raise Section8ValidationError("displayed settings evidence is missing")
    for visual_key, raw_key in (
        ("candidate_shuffles", "candidate_shuffles"),
        ("seed", "seed"),
        ("ranking_runtime_seconds", "ranking_runtime_seconds"),
        ("composite_method", "composite_method"),
        ("scoring_signature", "scoring_signature"),
    ):
        if displayed.get(visual_key) != raw_settings.get(raw_key):
            raise Section8ValidationError(f"PDF visual {visual_key} does not match raw manifest")
    if displayed.get("candidate_shuffles") != run_settings.get("candidate_shuffled_controls") or displayed.get("seed") != run_settings.get("seed"):
        raise Section8ValidationError("PDF-displayed rigorous settings do not match run sheet")
    if displayed.get("sampled_structures_displayed") is not False:
        raise Section8ValidationError("sampled-structure evidence must remain run-sheet-only")
    target = observations.get("target")
    if not isinstance(target, dict) or target.get("pdb_id") != case["pdb_id"] or target.get("chain") != case["chain"]:
        raise Section8ValidationError("PDF visual target does not match frozen target")
    compatibility = observations.get("compatibility")
    if not isinstance(compatibility, dict):
        raise Section8ValidationError("PDF compatibility evidence is missing")
    if compatibility.get("bank_realized_count") != 5085:
        raise Section8ValidationError("PDF compatibility bank count is not the observed frozen count")
    if compatibility.get("bank_identifier_exposed") is not False or compatibility.get("bank_content_hash_exposed") is not False:
        raise Section8ValidationError("an unobserved compatibility-bank identifier or hash was invented")
    if compatibility.get("raw_numeric_tier2_score_exposed") is not False:
        raise Section8ValidationError("raw numeric Tier 2 score availability is inconsistent")
    bands = compatibility.get("bands")
    if not isinstance(bands, dict):
        raise Section8ValidationError("PDF compatibility bands are missing")
    observed_counts = Counter(str(row["compatibility"]) for row in rows)
    for token in COMPATIBILITY_TOKENS:
        if bands.get(token, 0) != observed_counts.get(token, 0):
            raise Section8ValidationError("PDF compatibility-band counts do not match export")
    if bands.get("moderate_threshold") != 0.75 or bands.get("strong_threshold") != 0.95:
        raise Section8ValidationError("PDF compatibility thresholds are not frozen values")
    marker = observations.get("known_interface_marker")
    if not isinstance(marker, dict) or marker.get("publication_eligible_false_displayed") is not True:
        raise Section8ValidationError("known interface marker was not recorded")
    if "ignored" not in str(marker.get("treatment", "")):
        raise Section8ValidationError("known interface marker treatment drifted")
    return observations


def validate_case(root: Path, private_root: Path, case: dict[str, object]) -> tuple[dict[str, object], dict[str, object], list[bytes]]:
    public = root / str(case["public_package"])
    target = root / str(case["target_package"])
    result = root / str(case["result_directory"])

    public_manifest = read_pinned(public / "SHA256SUMS", str(case["public_manifest_sha256"]), "public package manifest")
    validate_sha256_manifest(public_manifest, public, "public package manifest")
    target_manifest = read_pinned(target / "SHA256SUMS", str(case["target_manifest_sha256"]), "target package manifest")
    validate_sha256_manifest(target_manifest, target, "target package manifest")

    upload = read_pinned(public / "upload/candidate_upload.csv", str(case["upload_sha256"]), "candidate upload")
    upload_rows, upload_by_id = parse_upload(upload)
    if len(upload_rows) != case["core_count"] or sorted(map(len, upload_by_id.values())) != case["expected_lengths"]:
        raise Section8ValidationError("upload denominator or length set drifted")

    expected_cells_bytes = read_pinned(public / "records/expected_cell_manifest.json", str(case["expected_cells_sha256"]), "expected-cell manifest")
    expected_cells = parse_json(expected_cells_bytes, "expected-cell manifest")
    validate_expected_cells(expected_cells, case, upload_by_id)
    read_pinned(public / "records/preparation_manifest.json", str(case["preparation_manifest_sha256"]), "preparation manifest")
    read_pinned(public / "records/validation_report.json", str(case["preflight_sha256"]), "preflight report")
    run_sheet_bytes = read_pinned(public / "records/run_sheet.json", str(case["run_sheet_sha256"]), "run sheet")
    run_sheet = parse_json(run_sheet_bytes, "run sheet")

    private_key = read_pinned(private_root / str(case["private_key_name"]), str(case["private_key_sha256"]), "restricted private key")
    private_document = parse_json(private_key, "restricted private key")
    private_rows = validate_private_key(private_document, case, upload_by_id)
    validate_run_sheet(run_sheet, case, upload, private_key, expected_cells_bytes)

    read_pinned(target / "section8_target_freeze.json", str(case["target_freeze_sha256"]), "target freeze")
    if not any(sha256_bytes(read_regular(path)) == case["target_config_sha256"] for path in (target / "config").iterdir() if path.is_file()):
        raise Section8ValidationError("target configuration digest not found in target package")
    if not any(sha256_bytes(read_regular(path)) == case["structure_sha256"] for path in (target / "source").iterdir() if path.is_file()):
        raise Section8ValidationError("configured structure digest not found in target package")

    raw_manifest_bytes = read_pinned(result / "records/raw_artifact_manifest.json", str(case["raw_manifest_sha256"]), "raw artifact manifest")
    raw_manifest = parse_json(raw_manifest_bytes, "raw artifact manifest")
    validate_raw_manifest(raw_manifest, case, result, upload)
    export = read_pinned(result / "raw" / str(case["export_name"]), str(case["export_sha256"]), "downloaded shortlist")
    pdf = read_pinned(result / "raw" / str(case["pdf_name"]), str(case["pdf_sha256"]), "result PDF")
    export_rows = validate_export(export, upload_by_id)
    visual_review_bytes = read_pinned(result / "records/pdf_visual_review.json", str(case["visual_review_sha256"]), "PDF visual review")
    visual_review = parse_json(visual_review_bytes, "PDF visual review")
    visual = validate_visual_review(visual_review, case, pdf, export_rows, run_sheet, raw_manifest)

    clusters = {str(row.get("cluster_id")) for row in private_rows}
    if len(clusters) != case["cluster_count"]:
        raise Section8ValidationError("private-key cluster denominator drifted")
    compatibility_counts = Counter(str(row["compatibility"]) for row in export_rows)
    shuffle_counts = Counter(str(row["shuffle"]) for row in export_rows)
    scores = [row["score"] for row in export_rows]
    public_rows = [
        {
            "rank": row["rank"],
            "aptamer_likeness": row["score_text"],
            "compatibility_band": row["compatibility"],
            "candidate_shuffle": row["shuffle"],
            "length": row["length"],
        }
        for row in export_rows
    ]
    summary = {
        "case_id": case["case_id"],
        "case_label": case["case_label"],
        "case_role": case["case_role"],
        "status": STATUS,
        "technical_validation_pass": True,
        "scientific_result_committed": False,
        "interpretation_complete": False,
        "target": {
            "target_config_id": case["target_config_id"],
            "pdb_id": case["pdb_id"],
            "chain": case["chain"],
            "binding_mode": case["binding_mode"],
            "prepared_target_identifier": visual["target"]["prepared_target_identifier"],
        },
        "settings": {
            "preset": "Evaluation",
            "seed": 42,
            "candidate_shuffles": 99,
            "sampled_structures": 200,
            "sampled_structures_evidence": "pinned run sheet; not independently displayed in result PDF",
            "composite_method": "corpus_weighted_mean",
            "scoring_signature": visual["displayed_settings"]["scoring_signature"],
        },
        "denominators": {
            "scientific_identities": case["identity_count"],
            "unique_cores": case["core_count"],
            "clusters": case["cluster_count"],
            "uploaded": len(upload_rows),
            "scored": len(export_rows),
            "technical_exclusions": 0,
        },
        "automated_checks": {
            "public_and_target_package_manifests": "pass",
            "upload_private_key_expected_cells_join": "pass",
            "upload_export_id_sequence_digest_and_length_join": "pass",
            "complete_rank_set_and_order": "pass",
            "finite_closed_interval_aptamer_likeness": "pass",
            "compatibility_and_shuffle_tokens": "pass",
            "raw_artifact_hashes": "pass",
        },
        "exported_results": {
            "rows_in_rank_order": public_rows,
            "aptamer_likeness_min": str(min(scores)),
            "aptamer_likeness_max": str(max(scores)),
            "compatibility_band_counts": dict(sorted(compatibility_counts.items())),
            "candidate_shuffle_counts": dict(sorted(shuffle_counts.items())),
            "raw_numeric_tier2_score": {
                "available": False,
                "reconstructed": False,
                "reason": "no untouched deployed artifact exposed a numeric Tier 2 score",
            },
        },
        "pdf_visual_evidence": {
            "evidence_class": "manual visual review of all pages bound to the exact PDF SHA-256",
            "automated_content_extraction": False,
            "layout_readable": True,
            "pages_reviewed": visual_review["pages_rendered_and_reviewed"],
            "compatibility_bank": {
                "realized_count": visual["compatibility"]["bank_realized_count"],
                "identifier_exposed": False,
                "content_hash_exposed": False,
                "moderate_threshold": visual["compatibility"]["bands"]["moderate_threshold"],
                "strong_threshold": visual["compatibility"]["bands"]["strong_threshold"],
            },
            "target_diagnostics": visual["target"],
            "warnings": visual["warnings"],
            "known_publication_eligible_false_marker": "ignored under the documented thesis-wide interface-bug decision",
        },
        "scope_limits": [
            "descriptive target case only",
            "no cross-target numerical comparison",
            "no target-discrimination claim",
            "no binding, affinity, specificity, inhibition or experimental-function claim",
            "no confidence interval or inferential test with these one- and two-core denominators",
        ],
    }
    inputs = {
        "candidate_upload": byte_record(upload),
        "expected_cell_manifest": byte_record(expected_cells_bytes),
        "run_sheet": byte_record(run_sheet_bytes),
        "restricted_private_key": byte_record(private_key),
        "downloaded_shortlist": byte_record(export),
        "result_pdf": byte_record(pdf),
        "raw_artifact_manifest": byte_record(raw_manifest_bytes),
        "pdf_visual_review": byte_record(visual_review_bytes),
    }
    sensitive = [private_key, *(sequence.encode("utf-8") for sequence in upload_by_id.values())]
    return summary, inputs, sensitive


def ensure_public(payloads: dict[str, bytes], sensitive: list[bytes]) -> None:
    for role, payload in payloads.items():
        if CANDIDATE_TOKEN_BYTES.search(payload):
            raise Section8ValidationError(f"opaque candidate id leaked into public output {role}")
        for item in sensitive:
            if item and item in payload:
                raise Section8ValidationError(f"restricted or sequence-bearing bytes leaked into public output {role}")


def render_report(summary: dict[str, object]) -> bytes:
    sections = []
    for case in summary["cases"]:
        d = case["denominators"]
        identity_label = "scientific identity" if d["scientific_identities"] == 1 else "scientific identities"
        core_label = "unique core" if d["unique_cores"] == 1 else "unique cores"
        cluster_label = "cluster" if d["clusters"] == 1 else "clusters"
        rows = case["exported_results"]["rows_in_rank_order"]
        row_lines = "\n".join(
            f"- Rank {row['rank']}: aptamer-likeness {row['aptamer_likeness']}; "
            f"compatibility {row['compatibility_band']}; candidate shuffle {row['candidate_shuffle']}; "
            f"length {row['length']} nt."
            for row in rows
        )
        warnings = "\n".join(f"- {warning}." for warning in case["pdf_visual_evidence"]["warnings"])
        sections.append(
            f"""## {case['case_label']}

- Technical validation: pass.
- Target: {case['target']['pdb_id']} chain {case['target']['chain']}, {case['target']['binding_mode']} mode.
- Accounting: {d['scientific_identities']} {identity_label}, {d['unique_cores']} {core_label}, {d['clusters']} {cluster_label}, {d['uploaded']} uploaded, {d['scored']} scored, {d['technical_exclusions']} technical exclusions.
- Raw numeric Tier 2 score: unavailable and not reconstructed.

{row_lines}

PDF-recorded cautions:

{warnings}
"""
        )
    sections_text = "\n".join(sections)
    text = f"""# Section 8 two-target panel: technical validation

Status: `{STATUS}`

Both descriptive target runs passed the frozen package, identity-join, export-schema, rank, score-range, token and raw-artifact checks. All pages of both hash-pinned result PDFs were visually reviewed. The PDF observations are explicitly separate from the automated CSV and hash checks.

The cases below must be interpreted separately. Their different binding modes and target-specific control distributions prohibit numerical cross-target comparison.

{sections_text}
## Validation boundary

This document records technical validation only. Scientific interpretation and explicit result commitment remain pending. The exported compatibility bands are retained, but no numeric Tier 2 score was exposed by an untouched deployed artifact and none was reconstructed. These computational prioritisation outputs do not demonstrate binding, affinity, specificity, inhibition, target discrimination or experimental function.
"""
    return text.encode("utf-8")


def build_outputs(root: Path, private_root: Path, generated_at_utc: str) -> tuple[dict[str, bytes], dict[str, object]]:
    read_pinned(root / PLAN_RELATIVE, PLAN_SHA256, "governing plan")
    read_pinned(root / PREPARATION_RELATIVE, PREPARATION_SHA256, "Section 8 preparation adapter")
    validation_adapter = read_regular(Path(__file__).resolve())
    reference = read_pinned(root / REFERENCE_RELATIVE, REFERENCE_SHA256, "reference upload")
    if len(parse_csv(reference, REFERENCE_FIELDS, "reference upload")) != REFERENCE_ROWS:
        raise Section8ValidationError("reference upload row count drifted")

    private_manifest_path = private_root / "SHA256SUMS"
    private_manifest = read_pinned(
        private_manifest_path,
        PRIVATE_MANIFEST_SHA256,
        "restricted package manifest",
    )
    validate_sha256_manifest(private_manifest, private_root, "restricted package manifest")

    cases = []
    input_records = {}
    sensitive: list[bytes] = []
    for case in CASES:
        result, inputs, case_sensitive = validate_case(root, private_root, case)
        cases.append(result)
        input_records[str(case["case_id"])] = inputs
        sensitive.extend(case_sensitive)
    signatures = {case["settings"]["scoring_signature"] for case in cases}
    if signatures != {"95a49467ef3c6186"}:
        raise Section8ValidationError("Section 8 scoring signatures are inconsistent")

    summary = {
        "schema_version": "mres-aptarank-section8-validation-summary-v1",
        "status": STATUS,
        "generated_at_utc": generated_at_utc,
        "governing_plan": {"version": "3.7", "section": 8, "sha256": PLAN_SHA256},
        "panel_id": PANEL_ID,
        "technical_validation_pass": True,
        "scientific_result_committed": False,
        "interpretation_complete": False,
        "scores_recomputed": False,
        "raw_tier2_scores_reconstructed": False,
        "cross_target_numeric_comparison_performed": False,
        "cases": cases,
    }
    public = {
        "section8_validation_summary.json": canonical_json_bytes(summary),
        "section8_validation_report.md": render_report(summary),
    }
    manifest = {
        "schema_version": "mres-aptarank-section8-validation-manifest-v1",
        "status": STATUS,
        "generated_at_utc": generated_at_utc,
        "governing_plan_sha256": PLAN_SHA256,
        "preparation_adapter_sha256": PREPARATION_SHA256,
        "validation_adapter": byte_record(validation_adapter),
        "reference_upload": byte_record(reference),
        "restricted_package_manifest": byte_record(private_manifest),
        "inputs_by_case": input_records,
        "outputs": {
            name: byte_record(payload)
            for name, payload in sorted(public.items())
        },
    }
    public["validation_manifest.json"] = canonical_json_bytes(manifest)
    ensure_public(public, sensitive)
    return public, summary


def write_outputs(output_dir: Path, payloads: dict[str, bytes]) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise Section8ValidationError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (output_dir / name).write_bytes(payload)
    checksum_lines = [f"{sha256_bytes(payload)}  {name}" for name, payload in sorted(payloads.items())]
    (output_dir / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="ascii")


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "results/aptarank/evaluation/section8_two_target_panel_evaluation_preset_v1/validation_v1",
    )
    parser.add_argument("--generated-at-utc")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    root = Path(__file__).resolve().parents[2]
    generated = arguments.generated_at_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payloads, summary = build_outputs(root, arguments.private_root.resolve(), generated)
    write_outputs(arguments.output_dir.resolve(), payloads)
    print(json.dumps({
        "status": summary["status"],
        "technical_validation_pass": summary["technical_validation_pass"],
        "case_count": len(summary["cases"]),
        "output_dir": str(arguments.output_dir.resolve()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Prepare the two frozen Section 8 descriptive AptaRank candidate packages.

The adapter opens only the hash-pinned EVAL table, the already-frozen target
packages, the frozen reference upload, and a caller-supplied 32-byte secret. It
does not run AptaRank or calculate Tier 1 or Tier 2 scores. Candidate sequences
appear only in the two upload CSVs; the restricted key stores digests and
provenance rather than sequence strings.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path


PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_7.md"
PLAN_SHA256 = "24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9"
EVAL_RELATIVE = "data/processed/eval.csv"
EVAL_SHA256 = "ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015"
REFERENCE_RELATIVE = "data/aptarank_eval/reference/m9c_reference_upload_attempt3.csv"
REFERENCE_SHA256 = "5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6"
REFERENCE_ROWS = 113
PANEL_RELATIVE = "data/aptarank_eval/target/section8_two_target_panel_v1/section8_panel_freeze.json"
PANEL_SHA256 = "49d4aa9dcf2b17d6cd03317f0cc7222512473d5af7f02688b3661022923e34b7"
PANEL_ID = "section8_two_target_panel_v1"
ID_DOMAIN = "m9b2-candidate-id-v1"
ID_PREFIX = "cand_"
KEY_BYTES = 32
TRUNCATION_BYTES = 16
UPLOAD_COLUMNS = ("id", "sequence")
EXPORT_FIELDS = ("rank", "candidate", "aptamer-likeness", "compatibility", "shuffle", "len", "sequence")

CASES = (
    {
        "case_id": "grk2_pocket",
        "package_id": "section8_grk2_tier2_evaluation_preset_v2",
        "target_dictionary_id": "TD0251",
        "target_config_id": "GRK2_3UZS_A_pocket",
        "target_package_relative": "data/aptarank_eval/target/section8_grk2_3uzs_v2",
        "target_freeze_sha256": "49d1c32db6b460a20cda0e712cd3e31120aa17ec7f1ed0d30d6cae815de31d18",
        "target_config_relative": "config/GRK2_3UZS_A_pocket.txt",
        "target_config_sha256": "105a1625b268d174b088dc2a1d701d84892d1fa42409a51311393b2cca789bea",
        "structure_relative": "source/3UZS.pdb",
        "structure_sha256": "ff0ef60bf3beaaaf634b6a0e8236575dba914b0caa4b32636b88c356bf390eb6",
        "pdb_id": "3UZS",
        "chain": "A",
        "binding_mode": "pocket",
        "site_residues": [197, 198, 199, 200, 201, 205, 218, 220, 230, 255, 272, 273, 274, 278, 280, 319, 321, 322, 324, 334, 335],
        "site_rule": "fpocket pocket with greatest overlap with the 21 frozen crystallographic RNA-contact residues",
        "expected_identity_count": 1,
        "expected_core_count": 1,
        "expected_cluster_count": 1,
        "expected_core_sha256": ["94f70b3e7c6f7dd1868feec41e4c3be9d664790a14dff92b279c6417449b648e"],
    },
    {
        "case_id": "hewl_surface",
        "package_id": "section8_lysozyme_tier2_evaluation_preset_v2",
        "target_dictionary_id": "TD0296",
        "target_config_id": "HEWL_4M4O_A_surface",
        "target_package_relative": "data/aptarank_eval/target/section8_lysozyme_4m4o_v1",
        "target_freeze_sha256": "6d9e69b7f61488d610ac58b421b1f852ea866e65a8fa4d4d5aaa014798db320c",
        "target_config_relative": "config/HEWL_4M4O_A_surface.txt",
        "target_config_sha256": "bad68b30e64b48fd069ed8e53d266d79a249039122774518b06ddd6f45de631a",
        "structure_relative": "source/4M4O.pdb",
        "structure_sha256": "17613b6fc82483f823ad2e6eb6e5dfdf55b98a9dd2cd3b39b7490b61021a5ae6",
        "pdb_id": "4M4O",
        "chain": "A",
        "binding_mode": "surface",
        "site_residues": [1, 3, 5, 6, 7, 10, 126, 127, 128],
        "site_rule": "the nine frozen 4M4O chain-A residues within 4.5 A of crystallographic RNA chain B",
        "expected_identity_count": 2,
        "expected_core_count": 2,
        "expected_cluster_count": 1,
        "expected_core_sha256": [
            "2b5bb349c7767ac187e80b25e2a1879d3dc6f4b4ec65695fc7e7ce006f6604b0",
            "3103b1874ba9745f70b149c3e7dd761952e42ca59fc5913cf66565143002d5fa",
        ],
    },
)


class PreparationError(RuntimeError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def length_delimited(parts: list[str]) -> bytes:
    output = bytearray()
    for part in parts:
        encoded = part.encode("utf-8")
        output.extend(len(encoded).to_bytes(4, "big"))
        output.extend(encoded)
    return bytes(output)


def candidate_id(sequence: str, secret: bytes) -> str:
    digest = hmac.new(secret, length_delimited([ID_DOMAIN, sequence]), hashlib.sha256).digest()
    return ID_PREFIX + digest[:TRUNCATION_BYTES].hex()


def csv_bytes(rows: list[dict[str, str]]) -> bytes:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=list(UPLOAD_COLUMNS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    payload = handle.getvalue().encode("utf-8")
    if b"\r" in payload:
        raise PreparationError("candidate upload contains a carriage return")
    return payload


def parse_eval(payload: bytes) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreparationError("EVAL is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    required = {
        "scientific_identity_id", "sequence_core", "sequence_length_core", "sequence_core_sha256",
        "sequence_id", "cluster_id", "target_dictionary_id", "canonical_target_name",
        "contributing_pubmed_ids", "publication", "source_db", "source_dataset",
    }
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise PreparationError("EVAL header is missing required fields")
    rows = list(reader)
    if len(rows) != 181:
        raise PreparationError(f"EVAL identity count is {len(rows)}, expected 181")
    for row in rows:
        sequence = row["sequence_core"]
        if not sequence or set(sequence) - set("ACGU"):
            raise PreparationError("EVAL contains a noncanonical core")
        if int(row["sequence_length_core"]) != len(sequence):
            raise PreparationError("EVAL core length does not match sequence")
        if hashlib.sha256(sequence.encode("utf-8")).hexdigest() != row["sequence_core_sha256"]:
            raise PreparationError("EVAL core digest does not match sequence")
    return rows


def select_case(eval_rows: list[dict[str, str]], case: dict[str, object], secret: bytes) -> tuple[bytes, bytes, list[str]]:
    identities = [row for row in eval_rows if row["target_dictionary_id"] == case["target_dictionary_id"]]
    if len(identities) != case["expected_identity_count"]:
        raise PreparationError(f"{case['case_id']} identity count drifted")
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in identities:
        grouped.setdefault(row["sequence_core_sha256"], []).append(row)
    if sorted(grouped) != sorted(case["expected_core_sha256"]):
        raise PreparationError(f"{case['case_id']} frozen core set drifted")
    clusters = {row["cluster_id"] for row in identities}
    if len(grouped) != case["expected_core_count"] or len(clusters) != case["expected_cluster_count"]:
        raise PreparationError(f"{case['case_id']} core or cluster denominator drifted")

    private_rows = []
    upload_rows = []
    ids: set[str] = set()
    for digest, source_rows in grouped.items():
        sequences = {row["sequence_core"] for row in source_rows}
        if len(sequences) != 1:
            raise PreparationError("one core digest maps to multiple sequences")
        sequence = next(iter(sequences))
        opaque = candidate_id(sequence, secret)
        if opaque in ids:
            raise PreparationError("truncated HMAC candidate-id collision")
        ids.add(opaque)
        upload_rows.append({"id": opaque, "sequence": sequence})
        private_rows.append({
            "candidate_id": opaque,
            "case_id": case["case_id"],
            "target_config_id": case["target_config_id"],
            "target_dictionary_id": case["target_dictionary_id"],
            "class_label": "eval_cognate_core",
            "sequence_core_sha256": digest,
            "length": len(sequence),
            "cluster_id": next(iter({row["cluster_id"] for row in source_rows})),
            "sequence_ids": sorted({row["sequence_id"] for row in source_rows}),
            "scientific_identity_ids": sorted({row["scientific_identity_id"] for row in source_rows}),
            "canonical_target_names": sorted({row["canonical_target_name"] for row in source_rows}),
            "contributing_pubmed_ids": sorted({row["contributing_pubmed_ids"] for row in source_rows if row["contributing_pubmed_ids"]}),
            "publications": sorted({row["publication"] for row in source_rows if row["publication"]}),
            "source_datasets": sorted({row["source_db"] + ":" + row["source_dataset"] for row in source_rows}),
        })
    upload_rows.sort(key=lambda row: row["id"])
    private_rows.sort(key=lambda row: row["candidate_id"])
    upload = csv_bytes(upload_rows)
    private_document = {
        "schema_version": "mres-aptarank-section8-private-key-v1",
        "status": "RESTRICTED_DO_NOT_UPLOAD_OR_COMMIT",
        "package_id": case["package_id"],
        "panel_id": PANEL_ID,
        "join_key": "candidate_id",
        "row_position_is_join_key": False,
        "sequence_strings_included": False,
        "candidates": private_rows,
    }
    return upload, canonical_json(private_document), [row["id"] for row in upload_rows]


def byte_record(payload: bytes) -> dict[str, object]:
    return {"sha256": sha256_bytes(payload), "byte_count": len(payload)}


def expected_cells(case: dict[str, object], ids: list[str]) -> bytes:
    document = {
        "schema_version": "mres-aptarank-section8-expected-cells-v1",
        "package_id": case["package_id"],
        "panel_id": PANEL_ID,
        "target_config_id": case["target_config_id"],
        "expected_candidate_ids": ids,
        "expected_candidate_count": len(ids),
        "expected_export_fields": list(EXPORT_FIELDS),
        "candidate_id_export_field": "candidate",
        "join_by_candidate_id": True,
        "row_position_is_join_key": False,
        "aptamer_likeness": "finite value in closed interval [0,1]",
        "compatibility_allowed_tokens": ["strong", "moderate", "weak"],
        "shuffle_allowed_tokens": ["pass", "fail"],
        "raw_tier2_score": "capture only if an untouched deployed artifact exposes it; do not reconstruct",
        "missing_or_excluded_rows": "record explicitly and do not replace",
    }
    return canonical_json(document)


def run_sheet(case: dict[str, object], upload: bytes, private_key: bytes, expected: bytes) -> bytes:
    document = {
        "schema_version": "mres-aptarank-section8-run-sheet-v1",
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "package_id": case["package_id"],
        "panel_id": PANEL_ID,
        "operator": "Laura",
        "deployment": {"aptarank_version": "0.1.0", "schema_version": "1.0.0", "git_revision": "49a85609e352"},
        "inputs": {
            "reference_upload": {"path": REFERENCE_RELATIVE, "sha256": REFERENCE_SHA256, "row_count": REFERENCE_ROWS},
            "candidate_upload": {"path": "upload/candidate_upload.csv", **byte_record(upload), "row_count": len(json.loads(expected)["expected_candidate_ids"])},
            "private_key": {"restricted": True, **byte_record(private_key)},
            "expected_cell_manifest": {"path": "records/expected_cell_manifest.json", **byte_record(expected)},
        },
        "target": {
            "target_config_id": case["target_config_id"],
            "pdb_id": case["pdb_id"],
            "chain": case["chain"],
            "binding_mode": case["binding_mode"],
            "site_residues": case["site_residues"],
            "site_rule": case["site_rule"],
            "target_freeze_sha256": case["target_freeze_sha256"],
            "target_config_sha256": case["target_config_sha256"],
            "structure_sha256": case["structure_sha256"],
        },
        "settings": {
            "preset": "Evaluation",
            "seed": 42,
            "candidate_shuffled_controls": 99,
            "ensemble_samples": 200,
            "composite_method": "corpus_weighted_mean",
            "scoring_signature": "capture_from_rigorous_run; do_not_reuse_the_Standard_signature",
        },
        "manual_steps": [
            "Upload the frozen 113-row attempt-3 reference CSV.",
            "Upload only this package's candidate_upload.csv.",
            "Configure the exact frozen target, chain, binding mode, site and preparation from the target package.",
            "Select the named Evaluation preset and verify that the UI displays seed 42, 99 candidate shuffles and 200 sampled structures before starting.",
            "Stop before scoring if the named Evaluation preset displays different effective settings; do not manually approximate it.",
            "Run this target separately from the other Section 8 case.",
            "Download the untouched shortlist CSV, exclusion register if present, result PDF and every available raw run artifact.",
            "Record runtime, warnings, accepted/scored/excluded counts and the displayed target configuration.",
        ],
        "interpretation": {
            "descriptive_only": True,
            "cross_target_numeric_comparison": False,
            "target_discrimination_claim": False,
            "binding_affinity_specificity_or_inhibition_claim": False,
            "publication_eligible_false_marker": "known interface bug; ignore under the documented thesis-wide decision",
        },
    }
    return canonical_json(document)


def manifest(case: dict[str, object], upload: bytes, private_key: bytes, expected: bytes, run: bytes) -> bytes:
    document = {
        "schema_version": "mres-aptarank-section8-preparation-manifest-v1",
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "scientific_result": False,
        "aptarank_executed": False,
        "package_id": case["package_id"],
        "panel_id": PANEL_ID,
        "case_id": case["case_id"],
        "selection": "all frozen unique EVAL cores for the target dictionary id; no sampling, controls, replacements or score use",
        "denominators": {
            "scientific_identities": case["expected_identity_count"],
            "unique_cores": case["expected_core_count"],
            "clusters": case["expected_cluster_count"],
            "upload_rows": case["expected_core_count"],
        },
        "pins": {
            "governing_plan": {"path": PLAN_RELATIVE, "sha256": PLAN_SHA256},
            "eval": {"path": EVAL_RELATIVE, "sha256": EVAL_SHA256},
            "reference_upload": {"path": REFERENCE_RELATIVE, "sha256": REFERENCE_SHA256},
            "panel_freeze": {"path": PANEL_RELATIVE, "sha256": PANEL_SHA256},
            "target_freeze": {"path": case["target_package_relative"] + "/section8_target_freeze.json", "sha256": case["target_freeze_sha256"]},
            "target_configuration": {"path": case["target_package_relative"] + "/" + case["target_config_relative"], "sha256": case["target_config_sha256"]},
            "structure": {"path": case["target_package_relative"] + "/" + case["structure_relative"], "sha256": case["structure_sha256"]},
        },
        "opaque_id": {
            "algorithm": "HMAC-SHA-256",
            "domain_separator": ID_DOMAIN,
            "key_length_bytes": KEY_BYTES,
            "truncation_bytes": TRUNCATION_BYTES,
            "textual_form": "cand_ plus 32 lowercase hexadecimal characters",
            "secret_in_public_package": False,
            "upload_order": "ascending opaque candidate id",
        },
        "artifacts": {
            "candidate_upload": byte_record(upload),
            "restricted_private_key": byte_record(private_key),
            "expected_cell_manifest": byte_record(expected),
            "run_sheet": byte_record(run),
        },
    }
    return canonical_json(document)


def readme(case: dict[str, object], upload: bytes, private_key: bytes, expected: bytes, run: bytes, prep: bytes) -> bytes:
    text = f"""# {case['package_id']}

Status: `PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN`

This package contains the blinded candidate upload for the frozen Section 8 `{case['case_id']}` descriptive run under the named Evaluation preset (rigorous mode). It contains all {case['expected_core_count']} unique EVAL core(s) associated with target dictionary id `{case['target_dictionary_id']}`. No candidate was sampled, replaced or selected using an AptaRank score.

Upload only `upload/candidate_upload.csv`. Use the separate frozen 113-row attempt-3 REF upload and the target configuration pinned in `records/run_sheet.json`.

The restricted reconciliation key and shared 32-byte panel secret are stored outside the repository. The restricted private-key SHA-256 is `{sha256_bytes(private_key)}`. Do not upload or commit restricted material.

Artifact hashes are recorded in `records/preparation_manifest.json` and `SHA256SUMS`. AptaRank was not run during preparation.
"""
    return text.encode("utf-8")


def sha_manifest(files: dict[str, bytes]) -> bytes:
    return "".join(f"{sha256_bytes(files[name])}  {name}\n" for name in sorted(files)).encode("ascii")


def validation_report(case: dict[str, object], upload: bytes, private_key: bytes, expected: bytes, run: bytes) -> bytes:
    expected_document = json.loads(expected)
    upload_rows = list(csv.DictReader(io.StringIO(upload.decode("utf-8"), newline="")))
    private_document = json.loads(private_key)
    upload_ids = [row["id"] for row in upload_rows]
    private_ids = [row["candidate_id"] for row in private_document["candidates"]]
    if upload_ids != expected_document["expected_candidate_ids"] or sorted(upload_ids) != sorted(private_ids):
        raise PreparationError("candidate ids do not reconcile across the upload, expected cells and private key")
    document = {
        "schema_version": "mres-aptarank-section8-preflight-v1",
        "status": "PASS",
        "package_id": case["package_id"],
        "panel_id": PANEL_ID,
        "aptarank_executed": False,
        "checks": {
            "all_source_hash_pins_match": True,
            "frozen_eval_core_set_matches": True,
            "identity_core_cluster_denominators_match": True,
            "canonical_rna_and_length_digest_consistency": True,
            "opaque_candidate_ids_unique_and_well_formed": True,
            "upload_expected_cells_private_key_ids_reconcile": True,
            "target_configuration_and_structure_hashes_match": True,
            "reference_upload_hash_and_row_count_match": True,
            "candidate_upload_schema_is_exact": True,
            "no_candidate_sampling_replacement_or_score_use": True,
            "separate_target_specific_run_sheet": True,
            "restricted_sequence_strings_absent_from_private_key": True,
        },
        "denominators": {
            "scientific_identities": case["expected_identity_count"],
            "unique_cores": case["expected_core_count"],
            "clusters": case["expected_cluster_count"],
            "upload_rows": len(upload_rows),
        },
        "artifacts": {
            "candidate_upload": byte_record(upload),
            "restricted_private_key": byte_record(private_key),
            "expected_cell_manifest": byte_record(expected),
            "run_sheet": byte_record(run),
        },
    }
    return canonical_json(document)


def publish_directory(destination: Path, files: dict[str, bytes], private_names: set[str] | None = None) -> None:
    if destination.exists() or destination.is_symlink():
        raise PreparationError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".section8-prep-", dir=destination.parent))
    promoted = False
    try:
        for relative, payload in files.items():
            path = temp / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            mode = 0o600 if private_names and relative in private_names else 0o644
            descriptor = os.open(path, flags, mode)
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
        if private_names:
            os.chmod(temp, 0o700)
        os.rename(temp, destination)
        promoted = True
    finally:
        if not promoted and temp.exists():
            shutil.rmtree(temp)


def prepare(repo: Path, public_parent: Path, restricted: Path, secret_path: Path) -> dict[str, object]:
    plan = pinned(repo / PLAN_RELATIVE, PLAN_SHA256)
    eval_payload = pinned(repo / EVAL_RELATIVE, EVAL_SHA256)
    reference = pinned(repo / REFERENCE_RELATIVE, REFERENCE_SHA256)
    panel = pinned(repo / PANEL_RELATIVE, PANEL_SHA256)
    if len(list(csv.DictReader(io.StringIO(reference.decode("utf-8"), newline="")))) != REFERENCE_ROWS:
        raise PreparationError("reference upload row count drifted")
    if json.loads(panel)["panel_id"] != PANEL_ID:
        raise PreparationError("panel id drifted")
    if not plan:
        raise PreparationError("governing plan is empty")
    secret = read_regular(secret_path)
    if len(secret) != KEY_BYTES:
        raise PreparationError("caller-supplied secret must be exactly 32 bytes")
    eval_rows = parse_eval(eval_payload)

    public_payloads: dict[str, dict[str, bytes]] = {}
    restricted_payloads: dict[str, bytes] = {"blinding_secret.bin": secret}
    summary_cases = []
    for case in CASES:
        target_root = repo / str(case["target_package_relative"])
        pinned(target_root / "section8_target_freeze.json", str(case["target_freeze_sha256"]))
        pinned(target_root / str(case["target_config_relative"]), str(case["target_config_sha256"]))
        pinned(target_root / str(case["structure_relative"]), str(case["structure_sha256"]))
        upload, private_key, ids = select_case(eval_rows, case, secret)
        expected = expected_cells(case, ids)
        run = run_sheet(case, upload, private_key, expected)
        prep = manifest(case, upload, private_key, expected, run)
        validation = validation_report(case, upload, private_key, expected, run)
        read_me = readme(case, upload, private_key, expected, run, prep)
        files = {
            "README.md": read_me,
            "records/expected_cell_manifest.json": expected,
            "records/preparation_manifest.json": prep,
            "records/run_sheet.json": run,
            "records/validation_report.json": validation,
            "upload/candidate_upload.csv": upload,
        }
        files["SHA256SUMS"] = sha_manifest(files)
        public_payloads[str(case["package_id"])] = files
        restricted_payloads[str(case["case_id"]) + "_private_key.json"] = private_key
        summary_cases.append({
            "case_id": case["case_id"],
            "package_id": case["package_id"],
            "upload_rows": len(ids),
            "candidate_upload_sha256": sha256_bytes(upload),
            "private_key_sha256": sha256_bytes(private_key),
            "expected_cell_manifest_sha256": sha256_bytes(expected),
            "run_sheet_sha256": sha256_bytes(run),
            "preparation_manifest_sha256": sha256_bytes(prep),
            "validation_report_sha256": sha256_bytes(validation),
        })

    restricted_payloads["SHA256SUMS"] = sha_manifest(restricted_payloads)
    publish_directory(restricted, restricted_payloads, set(restricted_payloads))
    for package_id, files in public_payloads.items():
        publish_directory(public_parent / package_id, files, {"upload/candidate_upload.csv"})
    return {
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "panel_id": PANEL_ID,
        "cases": summary_cases,
        "restricted_package": str(restricted),
        "aptarank_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--public-parent", type=Path, required=True)
    parser.add_argument("--restricted-package", type=Path, required=True)
    parser.add_argument("--secret-file", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(
        args.repo.resolve(),
        args.public_parent.resolve(),
        args.restricted_package.resolve(),
        args.secret_file.resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

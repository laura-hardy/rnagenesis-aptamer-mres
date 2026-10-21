#!/usr/bin/env python3
"""Prepare the same-input Section 6 Evaluation-preset rerun package.

The first Standard run remains immutable. This adapter copies the exact
reviewed upload bytes into a new package and binds a new run sheet to the
existing REF upload and restricted private key. It does not open sequence
provenance, regenerate controls, run AptaRank, or calculate a result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path


PLAN = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_7.md"
PLAN_SHA256 = "24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9"
SOURCE_PACKAGE = "data/aptarank_eval/sequence/section6_eval_tier1_v3"
UPLOAD_RELATIVE = SOURCE_PACKAGE + "/upload/section6_eval_tier1_candidates.csv"
UPLOAD_SHA256 = "5554f68fd94d1754ff9bcc87fba81be7dc8391af7e45703400796f4a5a336ad2"
UPLOAD_BYTES = 29048
PRIVATE_KEY_SHA256 = "be1a40990875a3d02bcdf3ebed6a6a5fb57104fa93f78df41c2ca544b7dc8408"
PRIVATE_KEY_BYTES = 135789
REFERENCE = "data/aptarank_eval/reference/m9c_reference_upload_attempt3.csv"
REFERENCE_SHA256 = "5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6"
REFERENCE_ROWS = 113
METHOD_CONTRACT = "config/modelling/aptarank_section6_method_contract.json"
METHOD_CONTRACT_SHA256 = "50652795985ddec6d93925715c7a6a50462a215ed830c54ccd7faf9a7c84e555"
ANALYSIS_MODULE = "scripts/modelling/aptarank_section6_analysis.py"
ANALYSIS_MODULE_SHA256 = "f4051c232d1a5be0c12fc959006957c439973e67baf32e4e3fdd31544f0ae3bf"
STANDARD_ANALYSIS_SUMMARY_SHA256 = "b3dec6026badbdfb38cce10cd5d7ad04838d6a0f20069a1b7dab0878b6bf8422"
STANDARD_CLOSURE_SHA256 = "02fe7666add2ffb4008ab2351c7bf535e895e359d7805af58e35ec631d500fa9"
PACKAGE_ID = "section6_eval_tier1_evaluation_preset_v4"


class RerunPreparationError(RuntimeError):
    pass


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_regular(path: Path) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RerunPreparationError(f"not a regular file: {path}")
    return path.read_bytes()


def pinned(path: Path, expected: str, byte_count: int | None = None) -> bytes:
    payload = read_regular(path)
    if digest(payload) != expected:
        raise RerunPreparationError(f"hash mismatch: {path}")
    if byte_count is not None and len(payload) != byte_count:
        raise RerunPreparationError(f"byte-count mismatch: {path}")
    return payload


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def record(payload: bytes) -> dict[str, object]:
    return {"sha256": digest(payload), "byte_count": len(payload)}


def sha_manifest(files: dict[str, bytes]) -> bytes:
    return "".join(f"{digest(files[name])}  {name}\n" for name in sorted(files)).encode("ascii")


def publish(destination: Path, files: dict[str, bytes]) -> None:
    if destination.exists() or destination.is_symlink():
        raise RerunPreparationError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".section6-rigorous-", dir=destination.parent))
    promoted = False
    try:
        for relative, payload in files.items():
            path = temp / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = 0o600 if relative.startswith("upload/") else 0o644
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise RerunPreparationError(f"write stalled: {relative}")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            if read_regular(path) != payload:
                raise RerunPreparationError(f"published bytes changed: {relative}")
        os.rename(temp, destination)
        promoted = True
    finally:
        if not promoted and temp.exists():
            shutil.rmtree(temp)


def prepare(repo: Path, private_key_path: Path, destination: Path) -> dict[str, object]:
    pinned(repo / PLAN, PLAN_SHA256)
    upload = pinned(repo / UPLOAD_RELATIVE, UPLOAD_SHA256, UPLOAD_BYTES)
    reference = pinned(repo / REFERENCE, REFERENCE_SHA256)
    pinned(repo / METHOD_CONTRACT, METHOD_CONTRACT_SHA256)
    pinned(repo / ANALYSIS_MODULE, ANALYSIS_MODULE_SHA256)
    private_key = pinned(private_key_path, PRIVATE_KEY_SHA256, PRIVATE_KEY_BYTES)

    upload_rows = list(csv.DictReader(io.StringIO(upload.decode("utf-8"), newline="")))
    reference_rows = list(csv.DictReader(io.StringIO(reference.decode("utf-8"), newline="")))
    if len(upload_rows) != 308 or len(reference_rows) != REFERENCE_ROWS:
        raise RerunPreparationError("upload or reference row count drifted")
    if tuple(upload_rows[0]) != ("id", "sequence") or len({row["id"] for row in upload_rows}) != 308:
        raise RerunPreparationError("candidate upload schema or id uniqueness drifted")
    if any(not row["sequence"] or set(row["sequence"]) - set("ACGU") for row in upload_rows):
        raise RerunPreparationError("candidate upload contains noncanonical RNA")

    run_sheet = json_bytes({
        "schema_version": "mres-aptarank-section6-rigorous-rerun-v1",
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "package_id": PACKAGE_ID,
        "reference_upload_sha256": REFERENCE_SHA256,
        "reference_publication_attempt": 3,
        "candidate_upload_sha256": UPLOAD_SHA256,
        "private_key_sha256": PRIVATE_KEY_SHA256,
        "preset": "Evaluation",
        "preset_role": "paper_rigorous_mode",
        "seed": 42,
        "candidate_shuffles": 99,
        "sampled_structures": 200,
        "protein_target": None,
        "expected_compatibility_token": "not evaluated",
        "pre_start_gate": "Select the named Evaluation preset and stop before scoring if its displayed effective settings are not seed 42, 99 candidate shuffles and 200 sampled structures.",
        "scoring_signature": "capture_from_rigorous_run; do_not_reuse_the_Standard_signature",
    })
    lineage = json_bytes({
        "schema_version": "mres-aptarank-section6-rerun-lineage-v1",
        "package_id": PACKAGE_ID,
        "parent_result_directory": "results/aptarank/evaluation/section6_tier1_eval_v1",
        "parent_run_id": "run_20261020T063814Z_5554f68f",
        "parent_preset": "Standard",
        "parent_analysis_summary_sha256": STANDARD_ANALYSIS_SUMMARY_SHA256,
        "parent_closure_record_sha256": STANDARD_CLOSURE_SHA256,
        "rerun_reason": "method_correction_standard_to_evaluation_preset_before_remaining_thesis_scoring",
        "inputs_changed": False,
        "candidate_membership_changed": False,
        "controls_changed": False,
        "analysis_estimands_changed": False,
        "preset_changed": True,
        "pool_results_across_runs": False,
        "select_result_by_favourability": False,
        "standard_artifacts_preserved_unchanged": True,
    })
    manifest = json_bytes({
        "schema_version": "mres-aptarank-section6-rigorous-preparation-v1",
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "package_id": PACKAGE_ID,
        "scientific_result": False,
        "aptarank_executed": False,
        "governing_plan": {"path": PLAN, "sha256": PLAN_SHA256},
        "source_standard_package": {"path": SOURCE_PACKAGE, "upload_unchanged": True},
        "candidate_upload": {**record(upload), "row_count": 308},
        "reference_upload": {**record(reference), "row_count": REFERENCE_ROWS},
        "restricted_private_key": {**record(private_key), "reused_unchanged": True},
        "method_contract": {
            "path": METHOD_CONTRACT,
            "sha256": METHOD_CONTRACT_SHA256,
            "analysis_estimands_unchanged": True,
            "historical_standard_preset_superseded_by_v3_7": True,
        },
        "analysis_module": {"path": ANALYSIS_MODULE, "sha256": ANALYSIS_MODULE_SHA256},
        "run_sheet": record(run_sheet),
        "rerun_lineage": record(lineage),
        "counts": {"eval_cores": 154, "paired_uniform_controls": 154, "upload_rows": 308, "pre_rejection_clusters": 79},
    })
    validation = json_bytes({
        "schema_version": "mres-aptarank-section6-rigorous-preflight-v1",
        "status": "PASS",
        "package_id": PACKAGE_ID,
        "aptarank_executed": False,
        "checks": {
            "v3_7_plan_hash_matches": True,
            "candidate_upload_is_byte_identical_to_standard_run": True,
            "reference_upload_is_unchanged": True,
            "private_key_is_unchanged": True,
            "candidate_schema_and_308_unique_ids_match": True,
            "candidate_sequences_are_canonical_rna": True,
            "method_contract_and_analysis_module_unchanged_except_v3_7_preset_succession": True,
            "evaluation_preset_99_shuffles_200_structures_recorded": True,
            "target_free_recorded": True,
            "rerun_lineage_recorded": True,
        },
    })
    readme = f"""# Section 6 rigorous rerun package

Status: `PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN`

Upload the exact candidate file in `upload/section6_eval_tier1_candidates.csv` with the unchanged frozen attempt-3 REF upload. Select the named **Evaluation** preset, seed 42, and verify that the UI displays 99 candidate shuffles and 200 sampled structures. Use no protein target.

The candidate upload is byte-identical to the independently reviewed Standard run: SHA-256 `{UPLOAD_SHA256}`. The restricted private key is reused unchanged outside the repository; do not upload it. The first run and its result remain immutable historical evidence.

Stop before scoring if the named Evaluation preset displays different effective settings. Preserve every untouched download under a new result directory and record the parent run lineage. AptaRank was not run during this preparation.
""".encode("utf-8")

    files = {
        "README.md": readme,
        "records/preparation_manifest.json": manifest,
        "records/rerun_lineage.json": lineage,
        "records/run_sheet.json": run_sheet,
        "records/validation_report.json": validation,
        "upload/section6_eval_tier1_candidates.csv": upload,
    }
    files["SHA256SUMS"] = sha_manifest(files)
    publish(destination, files)
    return {
        "status": "PREPARED_AND_PREFLIGHT_VALIDATED_APTARANK_NOT_RUN",
        "package_id": PACKAGE_ID,
        "candidate_upload_sha256": UPLOAD_SHA256,
        "candidate_upload_rows": 308,
        "run_sheet_sha256": digest(run_sheet),
        "rerun_lineage_sha256": digest(lineage),
        "preparation_manifest_sha256": digest(manifest),
        "validation_report_sha256": digest(validation),
        "aptarank_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.repo.resolve(), args.private_key.resolve(), args.destination.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

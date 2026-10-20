#!/usr/bin/env python3
"""Prepare the production Section 6 Tier 1 EVAL upload package.

This adapter opens the corrected role files only to instantiate the already
frozen Section 6 control and blinding method.  It does not call AptaRank, score
sequences, read an AptaRank export, or alter the frozen method modules.

The caller supplies a pre-existing 32-byte secret file.  Uploadable material
is published separately from the restricted private key and retained secret.
Both destinations must be absent, so an existing package is never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import errno
import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import aptarank_section6_analysis as analysis
import aptarank_section6_blinding as blinding
import aptarank_section6_uniform as uniform


PACKAGE_ID = "SECTION6-EVAL-TIER1-UPLOAD-V1"
SCHEMA_VERSION = "aptarank-section6-production-upload-v1"
STATUS = "SECTION6_UPLOAD_PREPARED_PRODUCTION_NOT_RUN"
PLAN_RELATIVE = "docs/aptarank_full_mres_thesis_evaluation_plan_v3_5.md"
PLAN_SHA256 = "ebb0e66dd35c7ed20abecacf710ea7a90dd0e2737ba1973af66e8f0753e22c9d"
METHOD_CONTRACT_RELATIVE = "config/modelling/aptarank_section6_method_contract.json"
METHOD_CONTRACT_SHA256 = "50652795985ddec6d93925715c7a6a50462a215ed830c54ccd7faf9a7c84e555"
UNIFORM_RELATIVE = "scripts/modelling/aptarank_section6_uniform.py"
UNIFORM_SHA256 = "02b158fc372ca2c50d80f44fe7afce1c85a5f3ae035afb42e181863bece02ee2"
BLINDING_RELATIVE = "scripts/modelling/aptarank_section6_blinding.py"
BLINDING_SHA256 = "be644bfa62d37cc93a5a4b0714fcbd351e71e7fd5775b6bd254030e757b524ff"
ANALYSIS_RELATIVE = "scripts/modelling/aptarank_section6_analysis.py"
ANALYSIS_SHA256 = "f4051c232d1a5be0c12fc959006957c439973e67baf32e4e3fdd31544f0ae3bf"
PREPARER_RELATIVE = "scripts/modelling/aptarank_section6_prepare_upload.py"
REFERENCE_RELATIVE = "data/aptarank_eval/reference/m9c_reference_upload_attempt3.csv"
REFERENCE_SHA256 = "5f5c90572263818b5eae55198ef811ade0cd5291a7e09a9708866abfa191ccd6"
SOURCE_ROLES = {
    "TRAIN": (
        "data/processed/ft_train.csv",
        "84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0",
        669,
    ),
    "VALIDATION": (
        "data/processed/ft_validation.csv",
        "cb347a739455924a7f4c55206bd2ac0131b7f36d79c8881e37e42728b600e0cd",
        95,
    ),
    "REF": (
        "data/processed/ref.csv",
        "531dd98ff5887e349b2f0e16db463c3b60b51f5f02f912cf099a1a5eb2debf23",
        113,
    ),
    "EVAL": (
        "data/processed/eval.csv",
        "ff4b36535052981c240dfa0571acd9cf00a386c80d9487a5994d1597f3386015",
        154,
    ),
}
REQUIRED_COLUMNS = {
    "sequence_core",
    "sequence_core_sha256",
    "sequence_length_core",
    "sequence_id",
    "cluster_id",
}
PUBLIC_FILES = (
    "upload/section6_eval_tier1_candidates.csv",
    "records/preparation_manifest.json",
    "records/run_sheet.json",
    "records/validation_report.json",
    "README.md",
)
RESTRICTED_FILES = (
    "section6_eval_tier1_private_key.json",
    "section6_eval_tier1_blinding_secret.bin",
)
AT_FDCWD = -2
RENAME_EXCL = 0x00000004


class PreparationError(ValueError):
    """Fail-closed production preparation error."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_regular(path: Path) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PreparationError(f"not a regular file: {path}")
    return path.read_bytes()


def require_pin(root: Path, relative: str, expected: str) -> bytes:
    payload = read_regular(root / relative)
    observed = sha256_bytes(payload)
    if observed != expected:
        raise PreparationError(f"SHA-256 mismatch for {relative}: {observed}")
    return payload


def canonical_json_bytes(document: object) -> bytes:
    return json.dumps(document, ensure_ascii=True, indent=2, sort_keys=False).encode("utf-8") + b"\n"


def byte_record(payload: bytes) -> dict[str, object]:
    return {"sha256": sha256_bytes(payload), "byte_count": len(payload)}


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_destinations(root: Path, public_destination: Path, restricted_destination: Path) -> str:
    public_root = root / "data/aptarank_eval/sequence"
    if not is_within(public_destination, public_root) or public_destination == public_root:
        raise PreparationError("public destination must be a new package below data/aptarank_eval/sequence")
    if is_within(restricted_destination, root):
        raise PreparationError("restricted destination must be outside the repository")
    if is_within(public_destination, restricted_destination) or is_within(restricted_destination, public_destination):
        raise PreparationError("public and restricted destinations must not overlap")
    return str(restricted_destination)


def load_role(root: Path, role: str) -> tuple[list[dict[str, str]], set[str], dict[str, object]]:
    relative, expected_hash, expected_cores = SOURCE_ROLES[role]
    payload = require_pin(root, relative, expected_hash)
    text = payload.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = list(reader.fieldnames or [])
    missing = REQUIRED_COLUMNS - set(header)
    if missing:
        raise PreparationError(f"{role} is missing columns: {sorted(missing)}")
    first_by_digest: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(reader, start=2):
        sequence = row["sequence_core"]
        if not sequence or any(base not in "ACGU" for base in sequence):
            raise PreparationError(f"{role} row {row_number} has a noncanonical core")
        digest = sha256_bytes(sequence.encode("utf-8"))
        if row["sequence_core_sha256"] != digest:
            raise PreparationError(f"{role} row {row_number} has a core-digest mismatch")
        if not row["sequence_length_core"].isdigit() or int(row["sequence_length_core"]) != len(sequence):
            raise PreparationError(f"{role} row {row_number} has a core-length mismatch")
        if not row["sequence_id"] or not row["cluster_id"]:
            raise PreparationError(f"{role} row {row_number} lacks a stable sequence or cluster id")
        previous = first_by_digest.setdefault(digest, row)
        for key in ("sequence_core", "sequence_id", "cluster_id"):
            if previous[key] != row[key]:
                raise PreparationError(f"{role} maps one core digest inconsistently for {key}")
    if len(first_by_digest) != expected_cores:
        raise PreparationError(f"{role} has {len(first_by_digest)} unique cores, expected {expected_cores}")
    rows = list(first_by_digest.values())
    public = {
        "role": role,
        "path": relative,
        "sha256": expected_hash,
        "byte_count": len(payload),
        "unique_core_count": len(rows),
    }
    return rows, set(first_by_digest), public


def build_inputs(root: Path) -> tuple[list[dict[str, str]], set[str], list[dict[str, object]]]:
    role_rows: dict[str, list[dict[str, str]]] = {}
    role_digests: dict[str, set[str]] = {}
    source_records = []
    for role in ("TRAIN", "VALIDATION", "REF", "EVAL"):
        rows, digests, public = load_role(root, role)
        role_rows[role] = rows
        role_digests[role] = digests
        source_records.append(public)
    roles = list(role_digests)
    for index, left in enumerate(roles):
        for right in roles[index + 1 :]:
            if role_digests[left] & role_digests[right]:
                raise PreparationError(f"core overlap between {left} and {right}")
    inventory = set().union(*role_digests.values())
    if len(inventory) != 1031:
        raise PreparationError(f"known-core inventory has {len(inventory)} digests, expected 1031")
    parents = [
        {
            "parent_core_id": row["sequence_id"],
            "cluster_id": row["cluster_id"],
            "sequence": row["sequence_core"],
        }
        for row in role_rows["EVAL"]
    ]
    if len(parents) != 154 or len({row["cluster_id"] for row in parents}) != 79:
        raise PreparationError("EVAL parent gate is not 154 cores across 79 clusters")
    return parents, inventory, source_records


def instantiate(parents: list[dict[str, str]], inventory: set[str], secret: bytes) -> dict[str, object]:
    blinding.require_secret(secret)
    blinding.load_pinned_contract()
    ordered_parents, controls = uniform.generate_uniform_controls(parents, inventory)
    rows = blinding._candidate_rows(ordered_parents, controls, secret)
    sequences = [row["sequence"] for row in rows]
    if len(sequences) != 308 or len(set(sequences)) != 308:
        raise PreparationError("the upload does not contain 308 globally unique sequences")
    upload, parsed = blinding._upload_bytes(rows)
    if len(parsed) != 308:
        raise PreparationError("the validated upload row count is not 308")
    private_rows = sorted(
        (row["private"] for row in rows),
        key=lambda row: (row["pair_id"], row["class_label"]),
    )
    private_document = {
        "package_id": blinding.PACKAGE_ID,
        "schema_version": blinding.SCHEMA_VERSION,
        "restricted": True,
        "candidates": private_rows,
    }
    private_bytes = blinding.canonical_json_bytes(private_document)
    validated = analysis.validate_private_key(private_bytes)
    class_counts = Counter(row["class_label"] for row in validated)
    pair_count = len({row["pair_id"] for row in validated})
    cluster_count = len({row["cluster_id"] for row in validated})
    frozen_count_report = blinding.production_count_report(
        class_counts[blinding.CLASS_EVAL_CORE],
        class_counts[blinding.CLASS_PAIRED_UNIFORM],
        pair_count,
        len(set(sequences)),
        cluster_count,
    )
    blinding.assert_production_counts(frozen_count_report)
    counts = {
        "eval_core": frozen_count_report["real_memberships"],
        "paired_uniform_shuffle": frozen_count_report["controls"],
        "complete_pairs": frozen_count_report["complete_pairs"],
        "unique_upload_sequences": frozen_count_report["unique_upload_sequences"],
        "pre_rejection_clusters": frozen_count_report["pre_rejection_clusters"],
    }
    upload_ids = {row["id"] for row in parsed}
    private_ids = {row["candidate_id"] for row in validated}
    if upload_ids != private_ids:
        raise PreparationError("upload and private-key candidate ids do not reconcile")
    upload_by_id = {row["id"]: row["sequence"] for row in parsed}
    for row in validated:
        sequence = upload_by_id[row["candidate_id"]]
        if sha256_bytes(sequence.encode("utf-8")) != row["source_digest"]:
            raise PreparationError("a private-key source digest does not match the upload")
        if len(sequence) != row["length"]:
            raise PreparationError("a private-key length does not match the upload")
    if any(row["source_digest"] in inventory for row in validated if row["class_label"] == blinding.CLASS_PAIRED_UNIFORM):
        raise PreparationError("a uniform control collides with the known-core inventory")
    control_digests = [
        row["source_digest"] for row in validated if row["class_label"] == blinding.CLASS_PAIRED_UNIFORM
    ]
    if len(control_digests) != len(set(control_digests)):
        raise PreparationError("uniform controls are not distinct")
    attempts = Counter(control["accepted_attempt"] for control in controls)
    return {
        "candidate_upload": upload,
        "private_key": private_bytes,
        "counts": counts,
        "control_attempt_histogram": {str(key): attempts[key] for key in sorted(attempts)},
    }


def render_readme(
    upload_record: dict[str, object],
    private_record: dict[str, object],
    restricted_locator: str,
    preparation_attempt: int,
    prepared_at_utc: str,
) -> bytes:
    text = f"""# Section 6 EVAL Tier 1 upload package

Status: `{STATUS}`

Preparation attempt: {preparation_attempt}. Prepared at: `{prepared_at_utc}`.

This package contains the blinded 308-row candidate upload for the 154 unique EVAL cores and their 154 frozen paired exact-length uniform controls. It contains no AptaRank scores and records no scientific result.

## Uploadable file

Upload only `upload/section6_eval_tier1_candidates.csv` as the candidate file. Its SHA-256 is `{upload_record['sha256']}` and it contains exactly the columns `id,sequence`.

Use the already frozen reference file `data/aptarank_eval/reference/m9c_reference_upload_attempt3.csv`, SHA-256 `{REFERENCE_SHA256}`.

## Manual UI settings

The exact target-free settings are in `records/run_sheet.json`: Standard preset, seed 42, 20 candidate shuffles, 100 ensemble samples, and no protein target. Do not start the run until the separate manual-production approval is explicit.

## Restricted material

The private key and 32-byte secret are stored outside the repository under `{restricted_locator}/`. The private-key SHA-256 is `{private_record['sha256']}`. Do not upload, expose, or commit either restricted file.

Preserve the candidate upload and every downloaded export byte-for-byte. Record technical failures rather than replacing candidates.
"""
    return text.encode("utf-8")


def sha256sums(files: dict[str, bytes]) -> bytes:
    lines = [f"{sha256_bytes(payload)}  {name}" for name, payload in sorted(files.items())]
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_payload(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fchmod(handle.fileno(), mode)
        os.fsync(handle.fileno())


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_tree(root: Path) -> None:
    directories = [Path(directory) for directory, _, _ in os.walk(root, topdown=False)]
    for directory in directories:
        fsync_directory(directory)


def rename_noreplace(source: Path, destination: Path) -> None:
    if sys.platform != "darwin":
        raise PreparationError("atomic no-replace directory publication requires macOS renameatx_np")
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameatx_np
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    result = rename(
        AT_FDCWD,
        os.fsencode(source),
        AT_FDCWD,
        os.fsencode(destination),
        RENAME_EXCL,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise PreparationError(f"destination already exists: {destination}")
        raise OSError(error_number, os.strerror(error_number), str(destination))


def cleanup_temporary(temporary: Path, expected_parent: Path, expected_prefix: str) -> None:
    if not temporary.exists() and not temporary.is_symlink():
        return
    if temporary.parent != expected_parent or not temporary.name.startswith(expected_prefix):
        raise PreparationError("temporary cleanup target failed its path boundary")
    info = temporary.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise PreparationError("temporary cleanup target is not the created directory")
    shutil.rmtree(temporary)
    fsync_directory(expected_parent)


def publish(destination: Path, files: dict[str, tuple[bytes, int]]) -> None:
    if destination.exists() or destination.is_symlink():
        raise PreparationError(f"destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fsync_directory(destination.parent)
    prefix = f".{destination.name}."
    temporary = Path(tempfile.mkdtemp(prefix=prefix, dir=destination.parent))
    published = False
    try:
        for relative, (payload, mode) in files.items():
            write_payload(temporary / relative, payload, mode)
        for relative, (payload, mode) in files.items():
            written = read_regular(temporary / relative)
            if written != payload or stat.S_IMODE((temporary / relative).stat().st_mode) != mode:
                raise PreparationError(f"publication verification failed: {relative}")
        fsync_tree(temporary)
        rename_noreplace(temporary, destination)
        published = True
        try:
            fsync_directory(destination.parent)
        except OSError as exc:
            raise PreparationError(
                f"destination was published but parent-directory sync failed: {destination}"
            ) from exc
    except BaseException as exc:
        if not published:
            try:
                cleanup_temporary(temporary, destination.parent, prefix)
            except BaseException as cleanup_exc:
                raise PreparationError(
                    f"publication failed and temporary cleanup also failed: {temporary}: {cleanup_exc}"
                ) from exc
        raise


def publish_outputs(
    restricted_destination: Path,
    restricted_files: dict[str, tuple[bytes, int]],
    public_destination: Path,
    public_files: dict[str, tuple[bytes, int]],
) -> None:
    publish(restricted_destination, restricted_files)
    try:
        publish(public_destination, public_files)
    except BaseException as exc:
        raise PreparationError(
            f"public publication failed; restricted output was retained at {restricted_destination}"
        ) from exc


def prepare(
    secret_path: Path,
    public_destination: Path,
    restricted_destination: Path,
    preparation_attempt: int,
) -> dict[str, object]:
    root = repo_root()
    if type(preparation_attempt) is not int or preparation_attempt < 1:
        raise PreparationError("preparation attempt must be a positive integer")
    pins = (
        (PLAN_RELATIVE, PLAN_SHA256),
        (METHOD_CONTRACT_RELATIVE, METHOD_CONTRACT_SHA256),
        (UNIFORM_RELATIVE, UNIFORM_SHA256),
        (BLINDING_RELATIVE, BLINDING_SHA256),
        (ANALYSIS_RELATIVE, ANALYSIS_SHA256),
        (REFERENCE_RELATIVE, REFERENCE_SHA256),
    )
    for relative, expected in pins:
        require_pin(root, relative, expected)
    preparer_payload = read_regular(root / PREPARER_RELATIVE)
    preparer_record = {
        "path": PREPARER_RELATIVE,
        "sha256": sha256_bytes(preparer_payload),
        "byte_count": len(preparer_payload),
    }
    restricted_locator = validate_destinations(root, public_destination, restricted_destination)
    prepared_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    secret = read_regular(secret_path)
    blinding.require_secret(secret)
    parents, inventory, source_records = build_inputs(root)
    instantiated = instantiate(parents, inventory, secret)
    upload = instantiated["candidate_upload"]
    private_key = instantiated["private_key"]
    run_sheet = blinding.canonical_json_bytes(blinding.check_run_sheet(blinding.run_sheet_template()))
    upload_record = byte_record(upload)
    private_record = byte_record(private_key)
    run_sheet_record = byte_record(run_sheet)
    manifest = {
        "package_id": PACKAGE_ID,
        "schema_version": SCHEMA_VERSION,
        "status": STATUS,
        "preparation_attempt": preparation_attempt,
        "prepared_at_utc": prepared_at_utc,
        "production_upload_instantiated": True,
        "manual_aptarank_production_authorized": False,
        "aptarank_executed": False,
        "scientific_result": False,
        "secrets_embedded": False,
        "candidate_ids_embedded": False,
        "sequences_embedded": False,
        "governing_plan": {"path": PLAN_RELATIVE, "sha256": PLAN_SHA256, "section": 6},
        "frozen_method": {
            "contract": {"path": METHOD_CONTRACT_RELATIVE, "sha256": METHOD_CONTRACT_SHA256},
            "uniform_module": {"path": UNIFORM_RELATIVE, "sha256": UNIFORM_SHA256},
            "blinding_module": {"path": BLINDING_RELATIVE, "sha256": BLINDING_SHA256},
            "analysis_module": {"path": ANALYSIS_RELATIVE, "sha256": ANALYSIS_SHA256},
        },
        "preparer": preparer_record,
        "source_roles": source_records,
        "known_core_inventory_count": len(inventory),
        "reference_upload": {
            "path": REFERENCE_RELATIVE,
            "sha256": REFERENCE_SHA256,
            "publication_attempt": 3,
        },
        "counts": instantiated["counts"],
        "control_attempt_histogram": instantiated["control_attempt_histogram"],
        "candidate_upload": upload_record,
        "private_key": private_record,
        "run_sheet": run_sheet_record,
        "secret": {
            "byte_count": len(secret),
            "embedded": False,
            "sha256_recorded_in_public_manifest": False,
        },
        "upload_relative_path": "upload/section6_eval_tier1_candidates.csv",
        "restricted_directory": restricted_locator,
    }
    manifest_bytes = canonical_json_bytes(manifest)
    forbidden = (secret, secret.hex().encode("ascii"))
    for payload in (upload, private_key, manifest_bytes, run_sheet):
        if any(token in payload for token in forbidden):
            raise PreparationError("the blinding secret appeared in an output")
    validation = {
        "status": "PASS",
        "errors": [],
        "counts": instantiated["counts"],
        "known_core_inventory_count": len(inventory),
        "upload": upload_record,
        "private_key": private_record,
        "run_sheet": run_sheet_record,
        "source_hashes_verified": True,
        "frozen_module_hashes_verified": True,
        "canonical_rna_verified": True,
        "candidate_ids_unique": True,
        "source_digests_unique": True,
        "pair_consistency_verified": True,
        "controls_outside_known_core_inventory": True,
        "controls_mutually_distinct": True,
        "upload_private_key_reconciliation": True,
        "target_free_run_sheet_verified": True,
        "aptarank_executed": False,
    }
    validation_bytes = canonical_json_bytes(validation)
    readme = render_readme(
        upload_record,
        private_record,
        restricted_locator,
        preparation_attempt,
        prepared_at_utc,
    )
    public_payloads = {
        "upload/section6_eval_tier1_candidates.csv": upload,
        "records/preparation_manifest.json": manifest_bytes,
        "records/run_sheet.json": run_sheet,
        "records/validation_report.json": validation_bytes,
        "README.md": readme,
    }
    for role, payload in public_payloads.items():
        if any(token in payload for token in forbidden):
            raise PreparationError(f"the blinding secret appeared in public output {role}")
        if role != "upload/section6_eval_tier1_candidates.csv" and b"cand_" in payload:
            raise PreparationError(f"an opaque candidate id appeared in public record {role}")
    public_payloads["SHA256SUMS"] = sha256sums(public_payloads)
    if any(token in public_payloads["SHA256SUMS"] for token in forbidden):
        raise PreparationError("the blinding secret appeared in the public SHA256SUMS")
    restricted_payloads = {
        "section6_eval_tier1_private_key.json": private_key,
        "section6_eval_tier1_blinding_secret.bin": secret,
    }
    restricted_payloads["SHA256SUMS"] = sha256sums(restricted_payloads)
    publish_outputs(
        restricted_destination,
        {name: (payload, 0o600) for name, payload in restricted_payloads.items()},
        public_destination,
        {
            name: (payload, 0o600 if name.startswith("upload/") else 0o644)
            for name, payload in public_payloads.items()
        },
    )
    return {
        "status": "PASS",
        "public_destination": str(public_destination),
        "restricted_destination": str(restricted_destination),
        "candidate_upload": upload_record,
        "private_key": private_record,
        "counts": instantiated["counts"],
        "control_attempt_histogram": instantiated["control_attempt_histogram"],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-file", required=True, type=Path)
    parser.add_argument("--public-destination", required=True, type=Path)
    parser.add_argument("--restricted-destination", required=True, type=Path)
    parser.add_argument("--preparation-attempt", required=True, type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    report = prepare(
        arguments.secret_file.resolve(),
        arguments.public_destination.resolve(),
        arguments.restricted_destination.resolve(),
        arguments.preparation_attempt,
    )
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PreparationError, uniform.Section6Error, OSError, UnicodeError, csv.Error, json.JSONDecodeError) as exc:
        sys.stderr.write(f"section6_upload_preparation_failed: {exc}\n")
        raise SystemExit(1)

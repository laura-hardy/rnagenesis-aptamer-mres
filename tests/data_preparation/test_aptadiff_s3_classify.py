"""Tests for the AptaDiff S3 classification runner (synthetic fixtures only).

Does not read real AptaDiff source sequences except optional local skipif
production gates that assert counts without embedding sequences.
"""

from __future__ import annotations

import csv
import hashlib
import io
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadiff import SIDECAR_COLUMNS  # noqa: E402
from adapters.aptadiff_s2 import S2_QC_COLUMNS  # noqa: E402
from adapters.aptadiff_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    REJECTION_COLUMNS,
)
from common.corpus_schema import CORPUS_COLUMNS, S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from s3_classify import main, run_aptadiff_s3, run_s3_classification  # noqa: E402

POLICY_A_PATH = REPO_ROOT / "config" / "source_eligibility" / "aptadiff_a.json"
POLICY_B_PATH = REPO_ROOT / "config" / "source_eligibility" / "aptadiff_b.json"
SYNTHETIC_DNA_36 = "ACGT" * 9
SYNTHETIC_N_36 = ("ACGT" * 8) + "ACGN"
PRODUCTION_A_S2 = REPO_ROOT / "data" / "interim" / "normalised" / "aptadiff_a_normalised.csv"
PRODUCTION_B_S2 = REPO_ROOT / "data" / "interim" / "normalised" / "aptadiff_b_normalised.csv"
EXPECTED_A_RAW = REPO_ROOT / "data/raw/Aptadiff_datasetA/datasetA_IGFBP3_P6.csv"
EXPECTED_B_RAW = REPO_ROOT / "data/raw/Aptadiff_otherdata/datasetB_PTK7_P6.csv"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _s2_row(
    *,
    source_key: str,
    native_id: str,
    sequence: str,
    alphabet: str = "DNA_T",
    qc_flags: str = "",
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"{source_key}:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "random_region_only",
            "trim_status": "no_constants_detected",
            "trim_confidence": "n/a",
            "molecule_type": "ssDNA",
            "alphabet_as_reported": alphabet,
            "t_to_u_applied": "false",
            "chemistry": "DNA",
            "target_name_raw": "",
            "source_db": source_key,
            "source_dataset": f"{source_key}_demo",
            "contributing_sources": source_key,
            "contributing_datasets": f"{source_key}_demo",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "qc_flags": qc_flags,
        }
    )
    return record


def _qc_row(canonical: dict[str, str], *, p6: str) -> dict[str, str]:
    row = {column: "" for column in S2_QC_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "target_name_raw": canonical["target_name_raw"],
            "aptadiff_dataset": "A" if canonical["source_db"] == "aptadiff_a" else "B",
            "aptadiff_documented_target": (
                "IGFBP3" if canonical["source_db"] == "aptadiff_a" else "PTK7"
            ),
            "aptadiff_p6": p6,
            "alphabet_as_reported": canonical["alphabet_as_reported"],
            "molecule_type": canonical["molecule_type"],
            "chemistry": canonical["chemistry"],
            "t_to_u_applied": canonical["t_to_u_applied"],
            "sequence_length_full": canonical["sequence_length_full"],
            "sequence_length_core": canonical["sequence_length_core"],
            "construct_scope": canonical["construct_scope"],
            "trim_status": canonical["trim_status"],
            "trim_confidence": canonical["trim_confidence"],
            "qc_flags": canonical["qc_flags"],
        }
    )
    return row


def _meta_row(canonical: dict[str, str], *, p6: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    source_key = canonical["source_db"]
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "aptadiff_csv_data_row": str(int(canonical["native_id"])),
            "aptadiff_seq": canonical["sequence_raw"],
            "aptadiff_p6": p6,
            "aptadiff_dataset": "A" if source_key == "aptadiff_a" else "B",
            "aptadiff_source_key": source_key,
            "aptadiff_documented_target": (
                "IGFBP3" if source_key == "aptadiff_a" else "PTK7"
            ),
            "aptadiff_target_provenance": "synthetic fixture",
        }
    )
    return row


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _make_tree(tmp_path: Path, source_key: str) -> tuple[Path, Path, Path, Path]:
    repo_root = tmp_path / "repo"
    (repo_root / "config" / "source_eligibility").mkdir(parents=True)
    shutil.copy(
        POLICY_A_PATH if source_key == "aptadiff_a" else POLICY_B_PATH,
        repo_root / "config" / "source_eligibility" / f"{source_key}.json",
    )
    input_dir = repo_root / "data" / "interim" / "normalised"
    metadata_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "checkpoints" / f"{source_key}_cp1"
    input_dir.mkdir(parents=True)
    metadata_dir.mkdir(parents=True)
    return repo_root, input_dir, metadata_dir, output_dir


def _write_source(
    input_dir: Path,
    metadata_dir: Path,
    source_key: str,
    specs: list[tuple[str, str, str, str, str]],
) -> None:
    canonical_rows = []
    qc_rows = []
    meta_rows = []
    for native_id, sequence, alphabet, qc_flags, p6 in specs:
        canonical = _s2_row(
            source_key=source_key,
            native_id=native_id,
            sequence=sequence,
            alphabet=alphabet,
            qc_flags=qc_flags,
        )
        canonical_rows.append(canonical)
        qc_rows.append(_qc_row(canonical, p6=p6))
        meta_rows.append(_meta_row(canonical, p6=p6))
    _write_csv(input_dir / f"{source_key}_normalised.csv", list(CORPUS_COLUMNS), canonical_rows)
    _write_csv(input_dir / f"{source_key}_s2_qc.csv", list(S2_QC_COLUMNS), qc_rows)
    _write_csv(
        metadata_dir / f"{source_key}_source_metadata.csv",
        list(SIDECAR_COLUMNS),
        meta_rows,
    )


def test_runner_reconciles_clean_and_ambiguous_rows(tmp_path: Path) -> None:
    repo_root, input_dir, metadata_dir, output_dir = _make_tree(tmp_path, "aptadiff_a")
    _write_source(
        input_dir,
        metadata_dir,
        "aptadiff_a",
        [
            ("00001", SYNTHETIC_DNA_36, "DNA_T", "", "5"),
            ("00002", SYNTHETIC_DNA_36.replace("A", "C", 1), "DNA_T", "", "194981"),
            ("00003", SYNTHETIC_N_36, "ambiguous", "ambiguous_base", "9"),
        ],
    )
    result = run_aptadiff_s3(
        repo_root=repo_root,
        source_key="aptadiff_a",
        input_dir=input_dir,
        source_metadata_dir=metadata_dir,
        eligibility_policy=repo_root / "config" / "source_eligibility" / "aptadiff_a.json",
        output_dir=output_dir,
        expected_rows=3,
        check_deterministic_rerun=True,
    )
    stats = result.stats
    assert stats.s3_rows == 3
    assert stats.primary_route_counts[PRIMARY_ROUTE_SSDNA] == 2
    assert stats.primary_route_counts[PRIMARY_ROUTE_REJECT] == 1
    assert stats.primary_route_counts.get(PRIMARY_ROUTE_ELIGIBLE, 0) == 0
    assert stats.unique_checkpoint_review_records == 1
    assert stats.random_accept_audit_count == 0
    assert stats.random_accept_audit_pool_size == 0
    assert stats.random_accept_audit_shortfall == 30
    assert stats.t_to_u_applied_count == 0
    assert stats.applied_trims == 0
    assert result.deterministic_rerun_ok is True
    assert result.s2_integrity_ok is True
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "authorised_for_s4: `0`" in summary
    assert "technically eligible RNA = `0`" in summary
    decisions = list(csv.DictReader(result.output_decisions.open(encoding="utf-8")))
    parks = list(csv.DictReader(result.output_parked_ssdna.open(encoding="utf-8")))
    rejects = list(csv.DictReader(result.output_rejected.open(encoding="utf-8")))
    assert len(parks) == 2
    assert len(rejects) == 1
    assert rejects[0]["rejection_reason"] == "ambiguous_bases"
    assert "N" in rejects[0]["sequence_raw"]
    by_id = {row["record_id"]: row for row in decisions}
    assert by_id["aptadiff_a:00001"]["manual_review_required"] == "false"
    assert by_id["aptadiff_a:00003"]["manual_review_required"] == "true"
    assert by_id["aptadiff_a:00003"]["review_batch"] == "01_judgement_dependent_technical"
    local = list(csv.DictReader(result.output_local_detail.open(encoding="utf-8")))
    for row in local:
        assert row["manual_decision"] == ""
        for field in S3_FORBIDDEN_FIELDS:
            assert row.get(field, "") == ""
    review = list(csv.DictReader(result.output_review.open(encoding="utf-8")))
    assert len(review) == 3
    assert all("sequence_raw" not in DECISION_COLUMNS for _ in [0])


def test_a_and_b_outputs_remain_separate(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config" / "source_eligibility").mkdir(parents=True)
    shutil.copy(POLICY_A_PATH, repo_root / "config" / "source_eligibility" / "aptadiff_a.json")
    shutil.copy(POLICY_B_PATH, repo_root / "config" / "source_eligibility" / "aptadiff_b.json")
    input_dir = repo_root / "data" / "interim" / "normalised"
    metadata_dir = repo_root / "data" / "interim" / "extracted"
    input_dir.mkdir(parents=True)
    metadata_dir.mkdir(parents=True)
    _write_source(
        input_dir,
        metadata_dir,
        "aptadiff_a",
        [("00001", SYNTHETIC_N_36, "ambiguous", "ambiguous_base", "5")],
    )
    _write_source(
        input_dir,
        metadata_dir,
        "aptadiff_b",
        [
            ("00001", SYNTHETIC_DNA_36, "DNA_T", "", "2"),
            ("00002", SYNTHETIC_N_36, "ambiguous", "ambiguous_base", "4"),
        ],
    )
    out_a = repo_root / "data" / "interim" / "checkpoints" / "aptadiff_a_cp1"
    out_b = repo_root / "data" / "interim" / "checkpoints" / "aptadiff_b_cp1"
    result_a = run_aptadiff_s3(
        repo_root=repo_root,
        source_key="aptadiff_a",
        input_dir=input_dir,
        source_metadata_dir=metadata_dir,
        eligibility_policy=repo_root / "config" / "source_eligibility" / "aptadiff_a.json",
        output_dir=out_a,
        expected_rows=1,
    )
    result_b = run_aptadiff_s3(
        repo_root=repo_root,
        source_key="aptadiff_b",
        input_dir=input_dir,
        source_metadata_dir=metadata_dir,
        eligibility_policy=repo_root / "config" / "source_eligibility" / "aptadiff_b.json",
        output_dir=out_b,
        expected_rows=2,
    )
    assert result_a.source_key == "aptadiff_a"
    assert result_b.source_key == "aptadiff_b"
    assert result_a.output_canonical != result_b.output_canonical
    assert result_a.stats.s3_rows == 1
    assert result_b.stats.s3_rows == 2
    assert result_a.stats.primary_route_counts[PRIMARY_ROUTE_REJECT] == 1
    assert result_b.stats.primary_route_counts[PRIMARY_ROUTE_SSDNA] == 1
    assert result_b.stats.primary_route_counts[PRIMARY_ROUTE_REJECT] == 1


def test_cli_dispatch_writes_source_specific_checkpoint(tmp_path: Path) -> None:
    repo_root, input_dir, metadata_dir, output_dir = _make_tree(tmp_path, "aptadiff_b")
    _write_source(
        input_dir,
        metadata_dir,
        "aptadiff_b",
        [("00001", SYNTHETIC_DNA_36, "DNA_T", "", "4")],
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "aptadiff_b",
                "--repo-root",
                str(repo_root),
                "--input-dir",
                str(input_dir),
                "--source-metadata-dir",
                str(metadata_dir),
                "--eligibility-policy",
                str(repo_root / "config" / "source_eligibility" / "aptadiff_b.json"),
                "--output-dir",
                str(output_dir),
                "--expected-rows",
                "1",
            ]
        )
    assert code == 0
    assert "source=aptadiff_b" in stdout.getvalue()
    assert (output_dir / "aptadiff_b_s3_canonical.csv").is_file()
    assert not (output_dir / "aptadiff_a_s3_canonical.csv").is_file()


def test_run_s3_classification_dispatch(tmp_path: Path) -> None:
    repo_root, input_dir, metadata_dir, output_dir = _make_tree(tmp_path, "aptadiff_a")
    _write_source(
        input_dir,
        metadata_dir,
        "aptadiff_a",
        [("00001", SYNTHETIC_DNA_36, "DNA_T", "", "9")],
    )
    result = run_s3_classification(
        repo_root=repo_root,
        source_key="aptadiff_a",
        input_dir=input_dir,
        source_metadata_dir=metadata_dir,
        leakage_set=repo_root / "unused.csv",
        target_aliases=repo_root / "unused.csv",
        eligibility_policy=repo_root / "config" / "source_eligibility" / "aptadiff_a.json",
        output_dir=output_dir,
        expected_rows=1,
    )
    assert result.source_key == "aptadiff_a"
    assert result.stats.ssdna_parked_count == 1


@pytest.mark.skipif(
    not PRODUCTION_A_S2.is_file() or not EXPECTED_A_RAW.is_file(),
    reason="Registered AptaDiff Dataset A S2/raw files not present locally",
)
def test_production_dataset_a_s3_reconciliation_without_embedding_sequences() -> None:
    rows = list(csv.DictReader(PRODUCTION_A_S2.open(encoding="utf-8")))
    assert len(rows) == 13803
    assert all(row["molecule_type"] == "ssDNA" for row in rows)
    assert all(row["t_to_u_applied"] == "false" for row in rows)
    assert all(row["target_name_raw"] == "" for row in rows)
    assert sum(1 for row in rows if "ambiguous_base" in (row["qc_flags"] or "").split("|") if row["qc_flags"]) == 1


@pytest.mark.skipif(
    not PRODUCTION_B_S2.is_file() or not EXPECTED_B_RAW.is_file(),
    reason="Registered AptaDiff Dataset B S2/raw files not present locally",
)
def test_production_dataset_b_s3_reconciliation_without_embedding_sequences() -> None:
    rows = list(csv.DictReader(PRODUCTION_B_S2.open(encoding="utf-8")))
    assert len(rows) == 11547
    assert all(row["molecule_type"] == "ssDNA" for row in rows)
    assert sum(1 for row in rows if "ambiguous_base" in (row["qc_flags"] or "").split("|") if row["qc_flags"]) == 15

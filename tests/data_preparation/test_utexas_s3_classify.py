"""Tests for the UTexas S3 classification runner (synthetic fixtures only).

Every literal nucleotide string in this file is shorter than 20 nt except where
length thresholds are tested with strings built at runtime. Does not read real
UTexas source data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.utexas import SIDECAR_COLUMNS  # noqa: E402
from adapters.utexas_s2 import S2_QC_COLUMNS  # noqa: E402
from adapters.utexas_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS,
    REJECTION_COLUMNS,
)
from common.corpus_schema import CORPUS_COLUMNS, empty_corpus_record  # noqa: E402
from s3_classify import main, run_s3_classification, run_utexas_s3  # noqa: E402

POLICY_PATH = REPO_ROOT / "config" / "source_eligibility" / "utexas.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _s2_row(
    native_id: str,
    sequence: str,
    *,
    molecule_type: str = "RNA",
    alphabet: str = "RNA",
    chemistry: str = "RNA",
    target: str = "demo_target",
    qc_flags: str = "",
    trim_status: str = "no_constants_detected",
    trim_confidence: str = "",
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"utexas:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": "not_applicable" if sequence == "" else trim_status,
            "trim_confidence": trim_confidence,
            "molecule_type": "unknown" if sequence == "" else molecule_type,
            "alphabet_as_reported": "missing" if sequence == "" else alphabet,
            "t_to_u_applied": "false",
            "chemistry": "unknown" if sequence == "" else chemistry,
            "target_name_raw": target,
            "source_db": "utexas",
            "source_dataset": "demo_ds",
            "contributing_sources": "utexas",
            "contributing_datasets": "demo_ds",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "publication": "Demo",
            "qc_flags": qc_flags,
        }
    )
    return record


def _qc_row(canonical: dict[str, str]) -> dict[str, str]:
    row = {column: "" for column in S2_QC_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "aptamer_name": f"name-{canonical['native_id']}",
            "target_name_raw": canonical["target_name_raw"],
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


def _meta_row(canonical: dict[str, str]) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "utexas_name_of_aptamer": f"name-{canonical['native_id']}",
            "utexas_target": canonical["target_name_raw"],
            "utexas_kd_nm": "3.2",
            "utexas_affinity": "bound",
            "utexas_aptamer_sequence": canonical["sequence_raw"],
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


def _make_tree(tmp_path: Path, n_rows: int = 5) -> tuple[Path, Path, Path, Path]:
    repo_root = tmp_path / "repo"
    input_dir = repo_root / "data" / "interim" / "normalised"
    meta_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "checkpoints" / "utexas_cp1"
    canonical_rows: list[dict[str, str]] = []
    qc_rows: list[dict[str, str]] = []
    meta_rows: list[dict[str, str]] = []
    for i in range(1, n_rows + 1):
        if i == n_rows:
            row = _s2_row(str(i), "", qc_flags="missing_sequence|molecule_type_unknown")
        elif i == 1:
            row = _s2_row(str(i), _rna(40), molecule_type="RNA")
        elif i == 2:
            row = _s2_row(
                str(i),
                ("ACGT" * 10)[:40],
                molecule_type="ssDNA",
                alphabet="DNA_T",
                chemistry="DNA",
            )
        elif i == 3:
            row = _s2_row(
                str(i),
                _rna(40),
                molecule_type="unknown",
                qc_flags="molecule_type_unknown|molecule_type_requires_review",
                chemistry="unknown",
            )
        else:
            row = _s2_row(
                str(i),
                _rna(22),
                molecule_type="RNA",
            )
        canonical_rows.append(row)
        qc_rows.append(_qc_row(row))
        meta_rows.append(_meta_row(row))

    _write_csv(input_dir / "utexas_normalised.csv", list(CORPUS_COLUMNS), canonical_rows)
    _write_csv(input_dir / "utexas_s2_qc.csv", list(S2_QC_COLUMNS), qc_rows)
    _write_csv(meta_dir / "utexas_source_metadata.csv", list(SIDECAR_COLUMNS), meta_rows)
    return repo_root, input_dir, meta_dir, output_dir


def test_reconciliation_every_input_appears_once(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path, n_rows=5)
    before = _sha256(input_dir / "utexas_normalised.csv")
    result = run_utexas_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=5,
    )
    assert result.stats.s3_rows == 5
    assert result.stats.unique_record_ids == 5
    accept = result.stats.decision_counts.get("proposed_accept", 0)
    park = result.stats.decision_counts.get("proposed_park", 0)
    reject = result.stats.decision_counts.get("proposed_reject", 0)
    assert accept + park + reject == 5
    assert _sha256(result.output_canonical) == before
    with result.output_decisions.open(encoding="utf-8", newline="") as handle:
        decisions = list(csv.DictReader(handle))
    assert [row["record_id"] for row in decisions] == [
        f"utexas:{i}" for i in range(1, 6)
    ]
    assert list(csv.DictReader(result.output_decisions.open()).fieldnames) == list(
        DECISION_COLUMNS
    )
    for row in decisions:
        assert row["checkpoint_status"] == "pending_checkpoint_1_review"
        for col in ("target_type", "target_name", "binding_evidence_score"):
            assert col not in row


def test_canonical_later_fields_remain_empty(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path, n_rows=5)
    result = run_utexas_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=5,
    )
    with result.output_canonical.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        assert row["target_type"] == ""
        assert row["target_name"] == ""
        assert row["binding_evidence_score"] == ""
        assert row["affinity_value"] == ""
        assert row["cluster_id"] == ""
        assert row["partition"] == ""


def test_rejection_and_park_sidecars_reconcile(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path, n_rows=5)
    result = run_utexas_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=5,
    )
    with result.output_rejected.open(encoding="utf-8", newline="") as handle:
        rejected_reader = csv.DictReader(handle)
        assert list(rejected_reader.fieldnames) == list(REJECTION_COLUMNS)
        rejected = list(rejected_reader)
    with result.output_parks.open(encoding="utf-8", newline="") as handle:
        park_reader = csv.DictReader(handle)
        assert list(park_reader.fieldnames) == list(PARK_COLUMNS)
        parks = list(park_reader)
    assert len(rejected) == result.stats.decision_counts.get("proposed_reject", 0)
    assert len(parks) == result.stats.decision_counts.get("proposed_park", 0)
    assert all(row["stage"] == "S3" for row in rejected)


def test_review_has_no_sequences_local_detail_does(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path, n_rows=5)
    result = run_utexas_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=5,
    )
    review_fields = list(csv.DictReader(result.output_review.open()).fieldnames)
    for col in ("sequence_raw", "sequence_full", "sequence_core"):
        assert col not in review_fields
        assert col in LOCAL_DETAIL_COLUMNS
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "No record authorised for S4 yet." in summary
    assert "UTexas target type was not inferred in S3" in summary
    assert "ACGU" not in summary


def test_deterministic_rerun(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path, n_rows=5)
    first = run_utexas_s3(
        repo_root=repo,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=5,
        check_deterministic_rerun=True,
    )
    assert first.deterministic_rerun_ok is True


def test_cli_dispatch(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path, n_rows=5)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "utexas",
                "--repo-root",
                str(repo),
                "--input-dir",
                str(input_dir),
                "--source-metadata-dir",
                str(meta_dir),
                "--eligibility-policy",
                str(POLICY_PATH),
                "--output-dir",
                str(out_dir),
                "--expected-rows",
                "5",
            ]
        )
    assert code == 0
    assert "source=utexas" in stdout.getvalue()
    assert "ACGU" not in stdout.getvalue()


def test_run_s3_classification_dispatch(tmp_path: Path) -> None:
    repo, input_dir, meta_dir, out_dir = _make_tree(tmp_path, n_rows=5)
    result = run_s3_classification(
        repo_root=repo,
        source_key="utexas",
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=repo / "unused.csv",
        target_aliases=repo / "unused_aliases.csv",
        eligibility_policy=POLICY_PATH,
        output_dir=out_dir,
        expected_rows=5,
    )
    assert result.source_key == "utexas"
    assert result.stats.s3_rows == 5

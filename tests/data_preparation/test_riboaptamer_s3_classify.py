"""Tests for the RiboAptamer S3 classification runner (synthetic fixtures only).

Every literal nucleotide string in this file is shorter than 20 nt except where
length thresholds are tested with strings built at runtime. Does not read real
RiboAptamer source data except via the optional local production skipif gate.
"""

from __future__ import annotations

import csv
import hashlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.riboaptamer import SIDECAR_COLUMNS  # noqa: E402
from adapters.riboaptamer_s2 import CONSTANT_PROPOSAL_COLUMNS, S2_QC_COLUMNS  # noqa: E402
from adapters.riboaptamer_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    REJECTION_COLUMNS,
)
from common.corpus_schema import CORPUS_COLUMNS, S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from s3_classify import main, run_riboaptamer_s3, run_s3_classification  # noqa: E402

POLICY_PATH = REPO_ROOT / "config" / "source_eligibility" / "riboaptamer.json"
PRODUCTION_S2 = REPO_ROOT / "data" / "interim" / "normalised" / "riboaptamer_normalised.csv"
PRODUCTION_RAW = (
    REPO_ROOT / "data" / "raw" / "riboaptamer" / "all_sequences_509_rows.csv"
)


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
    target: str = "",
    qc_flags: str = "",
    trim_status: str = "no_constants_detected",
    trim_confidence: str = "n/a",
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"riboaptamer:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": "not_applicable" if sequence == "" else trim_status,
            "trim_confidence": trim_confidence,
            "molecule_type": molecule_type if sequence else "unknown",
            "alphabet_as_reported": alphabet if sequence else "missing",
            "t_to_u_applied": "false",
            "chemistry": chemistry if sequence else "unknown",
            "target_name_raw": target,
            "source_db": "riboaptamer",
            "source_dataset": "riboaptamer_full_2026-08",
            "contributing_sources": "riboaptamer",
            "contributing_datasets": "riboaptamer_full_2026-08",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "publication": "Demo",
            "pubmed_id": "11111111",
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
            "target_name_raw": canonical["target_name_raw"],
            "source_type": "Small molecules",
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


def _meta_row(canonical: dict[str, str], *, source_type: str = "Small molecules") -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "riboaptamer_native_id": canonical["native_id"],
            "riboaptamer_sequence_name": f"seq-{canonical['native_id']}",
            "riboaptamer_aptamer_name": f"name-{canonical['native_id']}",
            "riboaptamer_category": "Natural",
            "riboaptamer_type": source_type,
            "riboaptamer_article_name": "Demo article",
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


def _make_tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    input_dir = repo_root / "data" / "interim" / "normalised"
    meta_dir = repo_root / "data" / "interim" / "extracted"
    output_dir = repo_root / "data" / "interim" / "checkpoints" / "riboaptamer_cp1"
    input_dir.mkdir(parents=True)
    meta_dir.mkdir(parents=True)
    return repo_root, input_dir, meta_dir, output_dir


def _seed_inputs(
    input_dir: Path,
    meta_dir: Path,
    canonical_rows: list[dict[str, str]],
    *,
    proposals: list[dict[str, str]] | None = None,
    source_type: str = "Small molecules",
) -> None:
    qc_rows = [_qc_row(row) for row in canonical_rows]
    meta_rows = [_meta_row(row, source_type=source_type) for row in canonical_rows]
    _write_csv(input_dir / "riboaptamer_normalised.csv", list(CORPUS_COLUMNS), canonical_rows)
    _write_csv(input_dir / "riboaptamer_s2_qc.csv", list(S2_QC_COLUMNS), qc_rows)
    _write_csv(meta_dir / "riboaptamer_source_metadata.csv", list(SIDECAR_COLUMNS), meta_rows)
    _write_csv(
        input_dir / "detected_constants_riboaptamer.csv",
        list(CONSTANT_PROPOSAL_COLUMNS),
        proposals or [],
    )


def test_no_silent_row_disappearance_and_reconciliation(tmp_path: Path) -> None:
    repo_root, input_dir, meta_dir, output_dir = _make_tree(tmp_path)
    rows = [
        _s2_row("1", _rna(40)),
        _s2_row("2", _rna(19)),
        _s2_row("3", _rna(20)),
        _s2_row("4", _rna(100)),
        _s2_row("5", _rna(101)),
        _s2_row("6", _rna(40), qc_flags="ambiguous_base"),
        _s2_row(
            "7",
            _rna(30) + "X",
            alphabet="invalid",
            qc_flags="invalid_character",
        ),
        _s2_row(
            "8",
            "ACGUACGU...ACGU-ACGU1234ACGUACGU",
            alphabet="invalid",
            qc_flags="alignment_gaps|invalid_character|truncated_sequence",
        ),
        _s2_row("9", _rna(40), qc_flags="mixed_t_u"),
        _s2_row("10", _rna(90)),
    ]
    t7 = _s2_row(
        "11",
        _rna(40),
        qc_flags="known_promoter_detected|trim_requires_review",
        trim_status="constants_suspected_unresolved",
    )
    rows.append(t7)
    proposal = {
        "proposal_id": "riboaptamer:11:known_motif:five_prime:t7_promoter_minimal",
        "experiment_group_id": "riboaptamer:11",
        "proposal_source": "known_motif",
        "side": "five_prime",
        "proposed_sequence": "",
        "motif_id": "t7_promoter_minimal",
        "motif_length": "18",
        "support": "",
        "records_considered": "1",
        "records_matching_exactly": "1",
        "confidence": "configured_motif_library",
        "status": "proposed_for_review",
        "applied": "false",
        "reason_not_applied": "detection_only_not_an_approved_trim",
        "reason": "known_motif:t7_promoter_minimal",
    }
    _seed_inputs(input_dir, meta_dir, rows, proposals=[proposal])

    result = run_riboaptamer_s3(
        repo_root=repo_root,
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        eligibility_policy=POLICY_PATH,
        output_dir=output_dir,
        expected_rows=len(rows),
        check_deterministic_rerun=True,
    )
    stats = result.stats
    assert stats.s2_rows == stats.s3_rows == len(rows)
    assert stats.unique_record_ids == len(rows)
    rejected = stats.primary_route_counts.get(PRIMARY_ROUTE_REJECT, 0)
    eligible = stats.primary_route_counts.get(PRIMARY_ROUTE_ELIGIBLE, 0)
    assert rejected + eligible == len(rows)
    assert stats.ssdna_parked_count == 0
    assert stats.non_protein_parked_count == 0
    assert stats.sequence_leakage_count == 0
    assert stats.target_leakage_count == 0
    assert stats.group_consensus_proposal_record_count == 0
    assert stats.trim_pushed_length_count == 0
    assert stats.known_motif_proposal_record_count == 1
    assert stats.truncated_sequence_count == 1
    assert stats.alignment_gaps_count == 1
    assert stats.judgement_dependent_review_count == 1

    review_ids = []
    with result.output_review.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["manual_review_required"] == "true":
                review_ids.append(row["record_id"])
    assert len(review_ids) == len(set(review_ids))
    assert "riboaptamer:8" in review_ids
    assert "riboaptamer:11" in review_ids
    assert "riboaptamer:3" in review_ids
    assert "riboaptamer:4" in review_ids
    assert "riboaptamer:10" in review_ids

    with result.output_rejected.open("r", encoding="utf-8", newline="") as handle:
        rejected_rows = list(csv.DictReader(handle))
    reasons = {row["rejection_reason"] for row in rejected_rows}
    assert reasons <= set(
        {
            "missing_sequence",
            "length_out_of_range",
            "ambiguous_bases",
            "invalid_alphabet",
            "mixed_T_and_U",
            "alignment_gaps",
            "truncated_sequence",
            "primer_like",
            "library_template",
        }
    )
    selb = next(row for row in rejected_rows if row["record_id"] == "riboaptamer:8")
    assert selb["rejection_reason"] == "truncated_sequence"
    assert "invalid_alphabet" in selb["rejection_detail"]
    assert "alignment_gaps" in selb["rejection_detail"]

    with result.output_local_detail.open("r", encoding="utf-8", newline="") as handle:
        details = {row["record_id"]: row for row in csv.DictReader(handle)}
    assert details["riboaptamer:11"]["sequence_core"] == t7["sequence_core"]
    assert details["riboaptamer:11"]["manual_decision"] == ""
    assert details["riboaptamer:2"]["riboaptamer_type"] == "Small molecules"
    for field_name in S3_FORBIDDEN_FIELDS:
        assert details["riboaptamer:1"].get(field_name, "") == ""

    summary = result.output_summary.read_text(encoding="utf-8")
    assert "group-wise constant-region inference was disabled" in summary.lower()
    assert "Evidence scored" in summary
    assert "No human decisions applied" in summary
    assert result.deterministic_rerun_ok is True


def test_cli_and_dispatch(tmp_path: Path) -> None:
    repo_root, input_dir, meta_dir, output_dir = _make_tree(tmp_path)
    rows = [_s2_row("1", _rna(40)), _s2_row("2", _rna(40))]
    _seed_inputs(input_dir, meta_dir, rows)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "riboaptamer",
                "--repo-root",
                str(repo_root),
                "--input-dir",
                str(input_dir),
                "--source-metadata-dir",
                str(meta_dir),
                "--eligibility-policy",
                str(POLICY_PATH),
                "--output-dir",
                str(output_dir),
                "--expected-rows",
                "2",
            ]
        )
    assert code == 0
    assert "source=riboaptamer" in stdout.getvalue()
    dispatched = run_s3_classification(
        repo_root=repo_root,
        source_key="riboaptamer",
        input_dir=input_dir,
        source_metadata_dir=meta_dir,
        leakage_set=repo_root / "missing.csv",
        target_aliases=repo_root / "missing.csv",
        eligibility_policy=POLICY_PATH,
        output_dir=output_dir,
        expected_rows=2,
    )
    assert dispatched.source_key == "riboaptamer"
    assert dispatched.stats.s3_rows == 2


@pytest.mark.skipif(not PRODUCTION_S2.is_file(), reason="local S2 outputs not present")
def test_production_s3_reconciles_509() -> None:
    result = run_riboaptamer_s3(
        repo_root=REPO_ROOT,
        input_dir=REPO_ROOT / "data" / "interim" / "normalised",
        source_metadata_dir=REPO_ROOT / "data" / "interim" / "extracted",
        eligibility_policy=POLICY_PATH,
        output_dir=REPO_ROOT / "data" / "interim" / "checkpoints" / "riboaptamer_cp1",
        expected_rows=509,
        check_deterministic_rerun=False,
    )
    assert result.stats.s2_rows == 509
    assert result.stats.s3_rows == 509
    rejected = result.stats.primary_route_counts.get(PRIMARY_ROUTE_REJECT, 0)
    eligible = result.stats.primary_route_counts.get(PRIMARY_ROUTE_ELIGIBLE, 0)
    assert rejected + eligible == 509
    assert result.raw_sha_before == (
        "721d8c5ea81476c1f371ef8bfa814743f364eaf004c0a6eda2aabd6dc5d9a9fd"
    )
    if PRODUCTION_RAW.is_file():
        assert _sha256(PRODUCTION_RAW) == result.raw_sha_after

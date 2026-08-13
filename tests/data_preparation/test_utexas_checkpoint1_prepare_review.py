"""Tests for UTexas CHECKPOINT-1 review-package preparation (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt.
Does not read real UTexas checkpoint data.
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

from checkpoint1_prepare_review import (  # noqa: E402
    UTEXAS_INDEX_COLUMNS,
    UTEXAS_MANUAL_REVIEW_COLUMNS,
    UTEXAS_SEQUENCE_COLUMNS,
    Checkpoint1ReviewError,
    main,
    prepare_utexas_checkpoint1_review,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _review(
    record_id: str,
    *,
    decision: str,
    primary: str,
    required: str,
    batch: str = "",
    priority: str = "none",
    secondary: str = "",
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "native_id": record_id.split(":")[-1],
        "aptamer_name": f"name-{record_id}",
        "target_name_raw": "demo_target",
        "proposed_decision": decision,
        "primary_reason": primary,
        "secondary_reasons": secondary,
        "manual_review_required": required,
        "manual_review_priority": priority,
        "review_batch": batch,
        "checkpoint_status": "pending_checkpoint_1_review",
        "molecule_type": "RNA",
        "chemistry": "RNA",
        "alphabet_as_reported": "RNA",
        "sequence_length_full": "8",
        "sequence_length_core": "8",
        "construct_scope": "unknown",
        "trim_status": "no_constants_detected",
        "trim_confidence": "",
        "qc_flags": "",
        "notes": "",
    }


def _detail(review: dict[str, str], *, sequence: str = "ACGUACGU") -> dict[str, str]:
    length = str(len(sequence)) if sequence else ""
    return {
        "record_id": review["record_id"],
        "native_id": review["native_id"],
        "aptamer_name": review["aptamer_name"],
        "target_name_raw": review["target_name_raw"],
        "publication": "Demo",
        "proposed_decision": review["proposed_decision"],
        "primary_reason": review["primary_reason"],
        "secondary_reasons": review["secondary_reasons"],
        "manual_review_required": review["manual_review_required"],
        "manual_review_priority": review["manual_review_priority"],
        "review_batch": review["review_batch"],
        "checkpoint_status": review["checkpoint_status"],
        "sequence_raw": sequence,
        "sequence_full": sequence,
        "sequence_core": sequence,
        "sequence_length_full": length,
        "sequence_length_core": length,
        "molecule_type": review["molecule_type"],
        "chemistry": review["chemistry"],
        "alphabet_as_reported": review["alphabet_as_reported"],
        "t_to_u_applied": "false",
        "construct_scope": review["construct_scope"],
        "trim_status": review["trim_status"],
        "trim_confidence": review["trim_confidence"],
        "detected_constant_5p": "",
        "detected_constant_3p": "",
        "qc_flags": review["qc_flags"],
        "notes": "",
    }


def _make_tree(
    tmp_path: Path,
    review_rows: list[dict[str, str]],
    detail_rows: list[dict[str, str]] | None = None,
) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / ".git").mkdir()
    checkpoint = repo / "data" / "interim" / "checkpoints" / "utexas_cp1"
    checkpoint.mkdir(parents=True)
    details = detail_rows if detail_rows is not None else [
        _detail(row) for row in review_rows
    ]
    _write_csv(
        checkpoint / "utexas_checkpoint1_review.csv",
        list(review_rows[0].keys()),
        review_rows,
    )
    _write_csv(
        checkpoint / "utexas_checkpoint1_local_detail.csv",
        list(details[0].keys()),
        details,
    )
    output = checkpoint / "manual_review"
    return repo, checkpoint, output


def test_missing_and_ssdna_excluded_from_active_queue(tmp_path: Path) -> None:
    reviews = [
        _review(
            "utexas:miss",
            decision="proposed_reject",
            primary="missing_sequence",
            required="false",
        ),
        _review(
            "utexas:dna",
            decision="proposed_park",
            primary="non_rna_molecule",
            required="false",
        ),
        _review(
            "utexas:trim",
            decision="proposed_park",
            primary="trim_construct_unresolved",
            required="true",
            batch="04_park_trim_construct",
            priority="high",
        ),
        _review(
            "utexas:acc",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="02_accept_with_diagnostics",
            priority="low",
            secondary="random_accept_audit",
        ),
        _review(
            "utexas:mol",
            decision="proposed_park",
            primary="molecule_type_unresolved",
            required="true",
            batch="03_park_unresolved_molecule",
            priority="high",
        ),
        _review(
            "utexas:gap",
            decision="proposed_reject",
            primary="alignment_gaps",
            required="true",
            batch="05_repair_alignment_gaps",
            priority="high",
        ),
        _review(
            "utexas:rej",
            decision="proposed_reject",
            primary="length_out_of_range",
            required="true",
            batch="01_reject_review",
            priority="high",
            secondary="trim_pushed_length_out_of_range",
        ),
    ]
    repo, checkpoint, output = _make_tree(tmp_path, reviews)
    result = prepare_utexas_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=output,
        expected_active_rows=5,
        expected_total_rows=7,
    )
    assert result.stats.active_review_rows == 5
    assert result.stats.no_review_records == 2
    assert result.stats.batch_counts["04_park_trim_construct"] == 1
    assert result.stats.batch_counts["02_accept_with_diagnostics"] == 1
    assert result.stats.batch_counts["03_park_unresolved_molecule"] == 1
    assert result.stats.batch_counts["05_repair_alignment_gaps"] == 1
    assert result.stats.batch_counts["01_reject_review"] == 1
    with result.output_queue.open(encoding="utf-8", newline="") as handle:
        queue_reader = csv.DictReader(handle)
        assert list(queue_reader.fieldnames) == list(UTEXAS_MANUAL_REVIEW_COLUMNS)
        queue = list(queue_reader)
    assert all(row["review_action"] == "" for row in queue)
    assert all(row["reviewer_note"] == "" for row in queue)
    index_fields = list(csv.DictReader(result.output_index.open()).fieldnames)
    for col in UTEXAS_SEQUENCE_COLUMNS:
        assert col not in index_fields
        assert col in UTEXAS_MANUAL_REVIEW_COLUMNS
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "No review action has yet been recorded." in summary
    assert "reviewer_notes_required` = `false`" in summary
    assert "ACGU" not in summary


def test_ssdna_active_review_is_rejected(tmp_path: Path) -> None:
    reviews = [
        _review(
            "utexas:dna",
            decision="proposed_park",
            primary="non_rna_molecule",
            required="true",
            batch="04_park_ssdna",
            priority="medium",
        )
    ]
    repo, checkpoint, output = _make_tree(tmp_path, reviews)
    try:
        prepare_utexas_checkpoint1_review(
            repo_root=repo,
            checkpoint_dir=checkpoint,
            output_dir=output,
            expected_total_rows=1,
        )
        raise AssertionError("expected Checkpoint1ReviewError")
    except Checkpoint1ReviewError as exc:
        assert "Explicit DNA/ssDNA" in str(exc)


def test_cli_utexas_dispatch(tmp_path: Path) -> None:
    reviews = [
        _review(
            "utexas:trim",
            decision="proposed_park",
            primary="trim_construct_unresolved",
            required="true",
            batch="04_park_trim_construct",
            priority="high",
        ),
        _review(
            "utexas:miss",
            decision="proposed_reject",
            primary="missing_sequence",
            required="false",
        ),
    ]
    repo, checkpoint, output = _make_tree(tmp_path, reviews)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "utexas",
                "--repo-root",
                str(repo),
                "--checkpoint-dir",
                str(checkpoint),
                "--output-dir",
                str(output),
                "--expected-total-rows",
                "2",
                "--expected-active-rows",
                "1",
            ]
        )
    assert code == 0
    assert "source=utexas" in stdout.getvalue()
    assert "active_review_rows=1" in stdout.getvalue()
    assert "ACGU" not in stdout.getvalue()
    assert _sha256(checkpoint / "utexas_checkpoint1_review.csv") == _sha256(
        checkpoint / "utexas_checkpoint1_review.csv"
    )

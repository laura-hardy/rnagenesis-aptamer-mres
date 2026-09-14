"""Tests for NCBI Nucleotide CHECKPOINT-1 review-package preparation.

Synthetic non-biological fixtures only. Does not read real NCBI sequences.
"""

from __future__ import annotations

import csv
import io
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb_checkpoint1_review import MANUAL_FIELDS  # noqa: E402
from adapters.ncbi_nuc_s3 import DECISION_COLUMNS, LOCAL_DETAIL_COLUMNS  # noqa: E402
from checkpoint1_prepare_review import (  # noqa: E402
    NCBI_NUC_INDEX_COLUMNS,
    NCBI_NUC_MANUAL_REVIEW_COLUMNS,
    prepare_ncbi_nuc_checkpoint1_review,
)
from checkpoint1_validate_review import main as validate_main  # noqa: E402

SYNTHETIC_RNA_8 = "ACGUACGU"
RECOMMENDATIONS = (
    REPO_ROOT
    / "config"
    / "checkpoint_reviews"
    / "ncbi_nuc_checkpoint1_recommendations.json"
)


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
    review_reasons: str = "",
    route: str = "technically_eligible",
    molecule: str = "RNA",
    chemistry: str = "RNA",
    alphabet: str = "RNA",
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "native_id": record_id.split(":")[-1],
        "target_name_raw": "",
        "proposed_decision": decision,
        "primary_reason": primary,
        "secondary_reasons": secondary,
        "primary_route": route,
        "manual_review_required": required,
        "manual_review_priority": priority,
        "review_batch": batch,
        "checkpoint_review_reasons": review_reasons,
        "checkpoint_status": "pending_checkpoint_1_review",
        "molecule_type": molecule,
        "chemistry": chemistry,
        "alphabet_as_reported": alphabet,
        "t_to_u_applied": "false",
        "sequence_length_full": "8",
        "sequence_length_core": "8",
        "construct_scope": "unknown",
        "trim_status": "no_constants_detected",
        "trim_confidence": "n/a",
        "source_object_class": "",
        "primer_associated": "false",
        "cdna_template_associated": "false",
        "transcription_template": "false",
        "poly_a_fragment": "false",
        "possible_non_aptamer_source_object": "false",
        "qc_flags": "",
        "constant_proposal_ids": "",
        "constant_proposal_sources": "",
        "notes": "",
    }


def _detail(review: dict[str, str], *, sequence: str = SYNTHETIC_RNA_8) -> dict[str, str]:
    length = str(len(sequence)) if sequence else ""
    row = {column: review.get(column, "") for column in LOCAL_DETAIL_COLUMNS}
    row.update(
        {
            "publication": "",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "manual_decision": "",
            "manual_sequence_corrected": "",
            "manual_target_corrected": "",
            "manual_molecule_type_override": "",
            "manual_chemistry_override": "",
            "manual_trim_action": "",
            "manual_trim_5p_nt": "",
            "manual_trim_3p_nt": "",
            "manual_trim_group_override": "",
            "manual_notes": "",
        }
    )
    return row


def test_human_fields_blank_and_validator_fail_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    rec_dir = repo / "config" / "checkpoint_reviews"
    rec_dir.mkdir(parents=True)
    shutil.copy(RECOMMENDATIONS, rec_dir / "ncbi_nuc_checkpoint1_recommendations.json")
    checkpoint = repo / "data" / "interim" / "checkpoints" / "ncbi_nuc_cp1"
    reviews = [
        _review(
            "ncbi_nuc:RNA36",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="05_random_kept_audit",
            priority="low",
            secondary="random_accept_audit",
            review_reasons="random_kept_audit",
        ),
        _review(
            "ncbi_nuc:RNA99",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="04_length_boundary",
            priority="low",
            secondary="upper_length_boundary|random_accept_audit",
            review_reasons="length_boundary|random_kept_audit",
        ),
        _review(
            "ncbi_nuc:UNK36",
            decision="proposed_park",
            primary="molecule_type_unresolved",
            required="true",
            batch="02_molecule_type_unresolved",
            priority="high",
            review_reasons="molecule_type_unresolved",
            route="parked_molecule_unresolved",
            molecule="unknown",
            chemistry="unknown",
            alphabet="DNA_T",
        ),
        _review(
            "ncbi_nuc:PRIMER",
            decision="proposed_reject",
            primary="primer_like",
            required="true",
            batch="01_judgement_dependent_technical",
            priority="high",
            secondary="molecule_type_unresolved",
            review_reasons="judgement_dependent_technical|molecule_type_unresolved",
            route="technical_reject",
            molecule="unknown",
            chemistry="unknown",
            alphabet="DNA_T",
        ),
        _review(
            "ncbi_nuc:METHODDNA",
            decision="proposed_reject",
            primary="non_aptamer_source_object",
            required="true",
            batch="01_judgement_dependent_technical",
            priority="high",
            secondary="length_out_of_range",
            review_reasons="judgement_dependent_technical",
            route="technical_reject",
            molecule="DNA",
            chemistry="DNA",
            alphabet="DNA_T",
        ),
    ]
    details = [_detail(row) for row in reviews]
    _write_csv(
        checkpoint / "ncbi_nuc_checkpoint1_review.csv",
        list(DECISION_COLUMNS),
        reviews,
    )
    _write_csv(
        checkpoint / "ncbi_nuc_checkpoint1_local_detail.csv",
        list(LOCAL_DETAIL_COLUMNS),
        details,
    )
    result = prepare_ncbi_nuc_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_total_rows=5,
        expected_active_rows=5,
    )
    assert result.stats.active_review_rows == 5
    assert result.stats.no_review_records == 0
    queue = list(csv.DictReader(result.output_queue.open(encoding="utf-8", newline="")))
    assert list(queue[0].keys()) == list(NCBI_NUC_MANUAL_REVIEW_COLUMNS)
    assert all(row["manual_decision"] == "" for row in queue)
    for row in queue:
        for name in MANUAL_FIELDS:
            assert row.get(name, "") == ""
        assert row["sequence_core"] == row["sequence_full"]
        assert row["target_name_raw"] == ""
    primer = next(row for row in queue if row["record_id"] == "ncbi_nuc:PRIMER")
    assert primer["review_recommendation"]
    assert primer["recommended_manual_decision"] == "drop"
    assert primer["manual_decision"] == ""
    method = next(row for row in queue if row["record_id"] == "ncbi_nuc:METHODDNA")
    assert method["primary_reason"] == "non_aptamer_source_object"
    unresolved = next(row for row in queue if row["record_id"] == "ncbi_nuc:UNK36")
    assert unresolved["review_recommendation"]
    index = list(csv.DictReader(result.output_index.open(encoding="utf-8", newline="")))
    assert list(index[0].keys()) == list(NCBI_NUC_INDEX_COLUMNS)
    assert "sequence_core" not in index[0]
    assert "sequence_raw" not in index[0]
    group = list(
        csv.DictReader(result.output_group_review.open(encoding="utf-8", newline=""))
    )
    assert group == []
    bulk = list(
        csv.DictReader(
            result.output_bulk_confirmation.open(encoding="utf-8", newline="")
        )
    )
    assert bulk[0]["confirm"] == ""
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "No human decision has yet been recorded." in summary
    assert SYNTHETIC_RNA_8 not in summary
    validation = result.output_validation.read_text(encoding="utf-8")
    assert "ready for application: `0`" in validation

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = validate_main(
            [
                "--source",
                "ncbi_nuc",
                "--repo-root",
                str(repo),
                "--checkpoint-dir",
                str(checkpoint),
            ]
        )
    output = stdout.getvalue()
    assert "ready_for_application=0" in output
    assert "unresolved_judgement_required=" in output
    assert "CHECKPOINT-1 is not closed" in output
    assert code != 0


def test_no_review_rows_are_excluded_and_shortfall_not_fabricated(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    checkpoint = repo / "data" / "interim" / "checkpoints" / "ncbi_nuc_cp1"
    reviews = [
        _review(
            "ncbi_nuc:CLEAN",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="false",
        ),
        _review(
            "ncbi_nuc:AUDIT",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="05_random_kept_audit",
            priority="low",
            secondary="random_accept_audit",
            review_reasons="random_kept_audit",
        ),
    ]
    details = [_detail(row) for row in reviews]
    _write_csv(
        checkpoint / "ncbi_nuc_checkpoint1_review.csv",
        list(DECISION_COLUMNS),
        reviews,
    )
    _write_csv(
        checkpoint / "ncbi_nuc_checkpoint1_local_detail.csv",
        list(LOCAL_DETAIL_COLUMNS),
        details,
    )
    result = prepare_ncbi_nuc_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_total_rows=2,
        expected_active_rows=1,
    )
    queue = list(csv.DictReader(result.output_queue.open(encoding="utf-8", newline="")))
    assert len(queue) == 1
    assert queue[0]["record_id"] == "ncbi_nuc:AUDIT"
    assert result.stats.no_review_records == 1
    assert result.stats.active_review_rows == 1

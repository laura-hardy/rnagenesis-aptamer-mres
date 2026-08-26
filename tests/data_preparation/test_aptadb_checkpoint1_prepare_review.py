"""Tests for AptaDB CHECKPOINT-1 review-package preparation (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt.
Does not read real AptaDB checkpoint data.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb_s3 import DECISION_COLUMNS, LOCAL_DETAIL_COLUMNS  # noqa: E402
from checkpoint1_prepare_review import (  # noqa: E402
    APTADB_INDEX_COLUMNS,
    APTADB_MANUAL_REVIEW_COLUMNS,
    prepare_aptadb_checkpoint1_review,
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
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "native_id": record_id.split(":")[-1],
        "aptamer_name": f"name-{record_id}",
        "target_name_raw": "demo_protein",
        "proposed_decision": decision,
        "primary_reason": primary,
        "secondary_reasons": secondary,
        "primary_route": route,
        "manual_review_required": required,
        "manual_review_priority": priority,
        "review_batch": batch,
        "checkpoint_review_reasons": review_reasons,
        "checkpoint_status": "pending_checkpoint_1_review",
        "molecule_type": "RNA",
        "chemistry": "RNA",
        "aptadb_target_chemistry": "Protein",
        "alphabet_as_reported": "RNA",
        "sequence_length_full": "8",
        "sequence_length_core": "8",
        "construct_scope": "unknown",
        "trim_status": "no_constants_detected",
        "trim_confidence": "n/a",
        "qc_flags": "",
        "constant_proposal_ids": "",
        "constant_proposal_sources": "",
        "constant_proposal_sides": "",
        "constant_group_id": "",
        "constant_records_in_group": "",
        "constant_support": "",
        "constant_proposed_trim_length": "",
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
        "primary_route": review["primary_route"],
        "manual_review_required": review["manual_review_required"],
        "manual_review_priority": review["manual_review_priority"],
        "review_batch": review["review_batch"],
        "checkpoint_review_reasons": review["checkpoint_review_reasons"],
        "checkpoint_status": review["checkpoint_status"],
        "sequence_raw": sequence,
        "sequence_full": sequence,
        "sequence_core": sequence,
        "sequence_length_full": length,
        "sequence_length_core": length,
        "molecule_type": review["molecule_type"],
        "chemistry": review["chemistry"],
        "aptadb_target_chemistry": review["aptadb_target_chemistry"],
        "alphabet_as_reported": review["alphabet_as_reported"],
        "t_to_u_applied": "false",
        "construct_scope": review["construct_scope"],
        "trim_status": review["trim_status"],
        "trim_confidence": review["trim_confidence"],
        "detected_constant_5p": "",
        "detected_constant_3p": "",
        "qc_flags": review["qc_flags"],
        "constant_proposal_ids": review["constant_proposal_ids"],
        "constant_proposal_sources": review["constant_proposal_sources"],
        "constant_proposal_sides": review["constant_proposal_sides"],
        "constant_group_id": review["constant_group_id"],
        "constant_records_in_group": review["constant_records_in_group"],
        "constant_support": review["constant_support"],
        "constant_proposed_trim_length": review["constant_proposed_trim_length"],
        "notes": "",
        "manual_decision": "",
        "manual_sequence_corrected": "",
        "manual_target_corrected": "",
        "manual_notes": "",
    }


def test_active_queue_combines_reasons_and_leaves_decisions_blank(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    checkpoint = repo / "data" / "interim" / "checkpoints" / "aptadb_cp1"
    reviews = [
        _review(
            "aptadb:keep",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="false",
            route="technically_eligible",
        ),
        _review(
            "aptadb:combo",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="02_constant_region_proposal",
            priority="medium",
            secondary="constant_region_proposal|lower_length_boundary",
            review_reasons="constant_region_proposal|length_boundary",
        ),
        _review(
            "aptadb:gap",
            decision="proposed_reject",
            primary="alignment_gaps",
            required="true",
            batch="01_judgement_dependent_technical",
            priority="high",
            review_reasons="judgement_dependent_technical",
            route="technical_reject",
        ),
    ]
    details = [_detail(row) for row in reviews]
    _write_csv(
        checkpoint / "aptadb_checkpoint1_review.csv",
        list(DECISION_COLUMNS),
        reviews,
    )
    _write_csv(
        checkpoint / "aptadb_checkpoint1_local_detail.csv",
        list(LOCAL_DETAIL_COLUMNS),
        details,
    )
    result = prepare_aptadb_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_total_rows=3,
        expected_active_rows=2,
    )
    assert result.stats.active_review_rows == 2
    assert result.stats.no_review_records == 1
    queue = list(
        csv.DictReader(result.output_queue.open(encoding="utf-8", newline=""))
    )
    assert list(queue[0].keys()) == list(APTADB_MANUAL_REVIEW_COLUMNS)
    assert all(row["manual_decision"] == "" for row in queue)
    assert {row["record_id"] for row in queue} == {"aptadb:combo", "aptadb:gap"}
    combo = next(row for row in queue if row["record_id"] == "aptadb:combo")
    assert "constant_region_proposal" in combo["checkpoint_review_reasons"]
    assert "length_boundary" in combo["checkpoint_review_reasons"]
    index = list(csv.DictReader(result.output_index.open(encoding="utf-8", newline="")))
    assert list(index[0].keys()) == list(APTADB_INDEX_COLUMNS)
    assert "sequence_core" not in index[0]
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "ACGU" not in summary
    assert "No human decision has yet been recorded." in summary

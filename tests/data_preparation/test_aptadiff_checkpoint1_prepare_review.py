"""Tests for AptaDiff CHECKPOINT-1 review-package preparation (synthetic only).

Does not read real AptaDiff checkpoint sequences.
"""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadiff_checkpoint1_review import (  # noqa: E402
    AMBIGUOUS_N_RECOMMENDATION,
    AMBIGUOUS_N_RATIONALE,
    MANUAL_FIELDS,
)
from adapters.aptadiff_s3 import DECISION_COLUMNS, LOCAL_DETAIL_COLUMNS  # noqa: E402
from checkpoint1_prepare_review import (  # noqa: E402
    APTADIFF_INDEX_COLUMNS,
    APTADIFF_MANUAL_REVIEW_COLUMNS,
    prepare_aptadiff_checkpoint1_review,
)

SYNTHETIC_DNA_36 = "ACGT" * 9
SYNTHETIC_N_36 = ("ACGT" * 8) + "ACGN"
RECOMMENDATIONS_A = (
    REPO_ROOT / "config" / "checkpoint_reviews" / "aptadiff_a_checkpoint1_recommendations.json"
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
    route: str = "parked_ssdna",
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
        "molecule_type": "ssDNA",
        "chemistry": "DNA",
        "alphabet_as_reported": "DNA_T" if primary != "ambiguous_bases" else "ambiguous",
        "sequence_length_full": "36",
        "sequence_length_core": "36",
        "construct_scope": "random_region_only",
        "trim_status": "no_constants_detected",
        "trim_confidence": "n/a",
        "qc_flags": "ambiguous_base" if primary == "ambiguous_bases" else "",
        "aptadiff_dataset": "A",
        "aptadiff_documented_target": "IGFBP3",
        "aptadiff_p6": "9",
        "notes": "",
    }


def _detail(review: dict[str, str], *, sequence: str) -> dict[str, str]:
    return {
        "record_id": review["record_id"],
        "native_id": review["native_id"],
        "target_name_raw": review["target_name_raw"],
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
        "sequence_length_full": str(len(sequence)),
        "sequence_length_core": str(len(sequence)),
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
        "aptadiff_dataset": review["aptadiff_dataset"],
        "aptadiff_documented_target": review["aptadiff_documented_target"],
        "aptadiff_p6": review["aptadiff_p6"],
        "notes": review["notes"],
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


def test_prepare_limits_active_queue_to_ambiguous_n(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    checkpoint = repo / "data" / "interim" / "checkpoints" / "aptadiff_a_cp1"
    rec_dir = repo / "config" / "checkpoint_reviews"
    rec_dir.mkdir(parents=True)
    shutil.copy(RECOMMENDATIONS_A, rec_dir / "aptadiff_a_checkpoint1_recommendations.json")
    park = _review(
        "aptadiff_a:00001",
        decision="proposed_park",
        primary="ssdna_parked",
        required="false",
    )
    amb = _review(
        "aptadiff_a:00002",
        decision="proposed_reject",
        primary="ambiguous_bases",
        required="true",
        batch="01_judgement_dependent_technical",
        priority="high",
        secondary="ssdna_parked",
        review_reasons="judgement_dependent_technical",
        route="technical_reject",
    )
    _write_csv(checkpoint / "aptadiff_a_checkpoint1_review.csv", list(DECISION_COLUMNS), [park, amb])
    _write_csv(
        checkpoint / "aptadiff_a_checkpoint1_local_detail.csv",
        list(LOCAL_DETAIL_COLUMNS),
        [_detail(park, sequence=SYNTHETIC_DNA_36), _detail(amb, sequence=SYNTHETIC_N_36)],
    )
    output_dir = repo / "data" / "interim" / "checkpoints" / "aptadiff_a_cp1" / "manual_review"
    result = prepare_aptadiff_checkpoint1_review(
        repo_root=repo,
        source_key="aptadiff_a",
        checkpoint_dir=checkpoint,
        output_dir=output_dir,
        expected_active_rows=1,
        expected_total_rows=2,
    )
    assert result.stats.total_checkpoint_records == 2
    assert result.stats.active_review_rows == 1
    assert result.stats.no_review_records == 1
    queue = list(csv.DictReader(result.output_queue.open(encoding="utf-8")))
    assert len(queue) == 1
    assert queue[0]["record_id"] == "aptadiff_a:00002"
    assert queue[0]["review_recommendation"] == AMBIGUOUS_N_RECOMMENDATION
    assert queue[0]["review_rationale"] == AMBIGUOUS_N_RATIONALE
    for name in MANUAL_FIELDS:
        assert queue[0][name] == ""
    assert "N" in queue[0]["sequence_full"]
    index = list(csv.DictReader(result.output_index.open(encoding="utf-8")))
    assert "sequence_raw" not in APTADIFF_INDEX_COLUMNS
    assert index[0]["record_id"] == "aptadiff_a:00002"
    bulk = list(csv.DictReader(result.output_bulk_confirmation.open(encoding="utf-8")))
    assert bulk[0]["eligible_record_count"] == "0"
    assert bulk[0]["confirm"] == ""
    assert bulk[0]["reviewer_initials"] == ""
    groups = list(csv.DictReader(result.output_group_review.open(encoding="utf-8")))
    assert groups == []
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "No human decision has yet been recorded." in summary
    assert "authorised for S4 yet" in summary
    validation = result.output_validation.read_text(encoding="utf-8")
    assert "CHECKPOINT-1 is not closed." in validation
    assert "ready for application: `0`" in validation
    assert set(csv.DictReader(result.output_queue.open(encoding="utf-8")).fieldnames) == set(
        APTADIFF_MANUAL_REVIEW_COLUMNS
    )


def test_prepare_dataset_b_remains_separate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    rec_dir = repo / "config" / "checkpoint_reviews"
    rec_dir.mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / "config" / "checkpoint_reviews" / "aptadiff_b_checkpoint1_recommendations.json",
        rec_dir / "aptadiff_b_checkpoint1_recommendations.json",
    )
    checkpoint = repo / "data" / "interim" / "checkpoints" / "aptadiff_b_cp1"
    rows = []
    details = []
    for i in range(1, 4):
        native = f"{i:05d}"
        if i == 3:
            review = _review(
                f"aptadiff_b:{native}",
                decision="proposed_reject",
                primary="ambiguous_bases",
                required="true",
                batch="01_judgement_dependent_technical",
                priority="high",
                secondary="ssdna_parked",
                review_reasons="judgement_dependent_technical",
                route="technical_reject",
            )
            seq = SYNTHETIC_N_36
        else:
            review = _review(
                f"aptadiff_b:{native}",
                decision="proposed_park",
                primary="ssdna_parked",
                required="false",
            )
            seq = SYNTHETIC_DNA_36
        review["aptadiff_dataset"] = "B"
        review["aptadiff_documented_target"] = "PTK7"
        rows.append(review)
        details.append(_detail(review, sequence=seq))
        details[-1]["aptadiff_dataset"] = "B"
        details[-1]["aptadiff_documented_target"] = "PTK7"
    _write_csv(checkpoint / "aptadiff_b_checkpoint1_review.csv", list(DECISION_COLUMNS), rows)
    _write_csv(
        checkpoint / "aptadiff_b_checkpoint1_local_detail.csv",
        list(LOCAL_DETAIL_COLUMNS),
        details,
    )
    result = prepare_aptadiff_checkpoint1_review(
        repo_root=repo,
        source_key="aptadiff_b",
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_active_rows=1,
        expected_total_rows=3,
    )
    assert result.source_key == "aptadiff_b"
    assert result.stats.active_review_rows == 1
    assert result.output_queue.name.startswith("aptadiff_b_")
    queue = list(csv.DictReader(result.output_queue.open(encoding="utf-8")))
    assert queue[0]["manual_decision"] == ""
    assert queue[0]["review_recommendation"] == AMBIGUOUS_N_RECOMMENDATION

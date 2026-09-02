"""Tests for AptaIndex CHECKPOINT-1 review-package preparation (synthetic only).

Every literal nucleotide string is a short runtime-built tile.
Does not read real AptaIndex checkpoint data.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptaindex_s3 import DECISION_COLUMNS, LOCAL_DETAIL_COLUMNS  # noqa: E402
from checkpoint1_prepare_review import (  # noqa: E402
    APTAINDEX_INDEX_COLUMNS,
    APTAINDEX_MANUAL_REVIEW_COLUMNS,
    prepare_aptaindex_checkpoint1_review,
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


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
    mapping_class: str = "straightforward_rna",
    judgement_subcategory: str = "",
) -> dict[str, str]:
    native = record_id.split(":")[-1]
    row = {column: "" for column in DECISION_COLUMNS}
    row.update(
        {
            "record_id": record_id,
            "native_id": native,
            "aptamer_name": f"name-{native}",
            "target_name_raw": "demo_target",
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
            "alphabet_as_reported": "chemical_notation",
            "sequence_length_full": "40",
            "sequence_length_core": "40",
            "construct_scope": "unknown",
            "trim_status": "no_constants_detected",
            "trim_confidence": "n/a",
            "qc_flags": "",
            "aptaindex_type": "RNA",
            "mapping_class": mapping_class,
            "judgement_subcategory": judgement_subcategory,
        }
    )
    return row


def _detail(review: dict[str, str], *, sequence: str | None = None) -> dict[str, str]:
    sequence = _rna(8) if sequence is None else sequence
    length = str(len(sequence)) if sequence else ""
    row = {column: "" for column in LOCAL_DETAIL_COLUMNS}
    row.update(review)
    row.update(
        {
            "publication": "Demo",
            "aptaindex_title": f"title-{review['native_id']}",
            "aptaindex_type": review.get("aptaindex_type", "RNA"),
            "aptaindex_target": review.get("target_name_raw", ""),
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "t_to_u_applied": "false",
            "manual_decision": "",
        }
    )
    return row


def test_prepare_leaves_manual_blank_and_excludes_automatic_rejects(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    rec_path = (
        repo
        / "config"
        / "checkpoint_reviews"
        / "aptaindex_checkpoint1_recommendations.json"
    )
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text(
        (
            REPO_ROOT
            / "config"
            / "checkpoint_reviews"
            / "aptaindex_checkpoint1_recommendations.json"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    checkpoint = repo / "data" / "interim" / "checkpoints" / "aptaindex_cp1"
    reviews = [
        _review(
            "aptaindex:keep",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="false",
            route="technically_eligible",
        ),
        _review(
            "aptaindex:missing",
            decision="proposed_reject",
            primary="missing_sequence",
            required="false",
            route="technical_reject",
            mapping_class="missing_sequence",
        ),
        _review(
            "aptaindex:peptide",
            decision="proposed_reject",
            primary="non_nucleic_acid_molecule",
            required="false",
            route="technical_reject",
            mapping_class="peptide",
        ),
        _review(
            "aptaindex:unsupported",
            decision="proposed_park",
            primary="unsupported_chemical_notation",
            required="true",
            batch="01_judgement_dependent_technical",
            priority="high",
            review_reasons="judgement_dependent_technical|unsupported_chemical_notation",
            route="parked_chemistry_review",
            mapping_class="unsupported_notation",
            judgement_subcategory="unsupported_chemical_notation",
        ),
        _review(
            "aptaindex:motif",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="02_constant_region_proposal",
            priority="medium",
            secondary="known_motif_proposal",
            review_reasons="constant_region_proposal",
        ),
        _review(
            "aptaindex:boundary",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="03_length_boundary",
            priority="low",
            secondary="lower_length_boundary",
            review_reasons="length_boundary",
        ),
        _review(
            "aptaindex:audit",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="04_random_kept_audit",
            priority="low",
            secondary="random_accept_audit",
            review_reasons="random_kept_audit",
        ),
    ]
    details = [_detail(row) for row in reviews]
    _write_csv(
        checkpoint / "aptaindex_checkpoint1_review.csv",
        list(DECISION_COLUMNS),
        reviews,
    )
    _write_csv(
        checkpoint / "aptaindex_checkpoint1_local_detail.csv",
        list(LOCAL_DETAIL_COLUMNS),
        details,
    )
    result = prepare_aptaindex_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_total_rows=7,
        expected_active_rows=4,
    )
    assert result.stats.active_review_rows == 4
    assert result.stats.no_review_records == 3
    queue = list(
        csv.DictReader(result.output_queue.open(encoding="utf-8", newline=""))
    )
    assert list(queue[0].keys()) == list(APTAINDEX_MANUAL_REVIEW_COLUMNS)
    assert all(row["manual_decision"] == "" for row in queue)
    assert all(row["manual_sequence_corrected"] == "" for row in queue)
    ids = [row["record_id"] for row in queue]
    assert "aptaindex:missing" not in ids
    assert "aptaindex:peptide" not in ids
    assert ids[0] == "aptaindex:unsupported"
    unsupported = queue[0]
    assert unsupported["review_recommendation"] == "review_defer"
    assert unsupported["recommended_sequence_corrected"] == ""
    motif = next(row for row in queue if row["record_id"] == "aptaindex:motif")
    assert motif["review_recommendation"] == "decide_trim"
    assert motif["recommended_trim_action"] == "defer"
    boundary = next(row for row in queue if row["record_id"] == "aptaindex:boundary")
    assert boundary["audit_only_row"] == "true"
    assert boundary["review_recommendation"] == "keep_current_route"
    index = list(csv.DictReader(result.output_index.open(encoding="utf-8", newline="")))
    assert list(index[0].keys()) == list(APTAINDEX_INDEX_COLUMNS)
    assert "sequence_core" not in index[0]
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "ACGU" not in summary
    assert "No human decision has yet been recorded." in summary
    assert "fail closed" in summary.lower()
    assert result.inputs_unchanged is True

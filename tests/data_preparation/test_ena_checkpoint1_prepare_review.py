"""Tests for ENA CHECKPOINT-1 review-package preparation (synthetic only).

Every literal nucleotide string is a short runtime-built tile.
Does not read real ENA checkpoint data.
"""

from __future__ import annotations

import csv
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.ena_s2 import CONSTANT_PROPOSAL_COLUMNS, MEMBERSHIP_COLUMNS  # noqa: E402
from adapters.ena_s3 import DECISION_COLUMNS, LOCAL_DETAIL_COLUMNS  # noqa: E402
from checkpoint1_prepare_review import (  # noqa: E402
    ENA_INDEX_COLUMNS,
    ENA_MANUAL_REVIEW_COLUMNS,
    prepare_ena_checkpoint1_review,
)
from checkpoint1_validate_review import main as validate_main  # noqa: E402


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
    promoter: str = "false",
    group_covered: str = "false",
    t_to_u: str = "false",
    length: str = "40",
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "native_id": record_id.split(":")[-1],
        "review_unit_id": record_id.split(":")[-1],
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
        "alphabet_as_reported": "RNA",
        "t_to_u_applied": t_to_u,
        "sequence_length_full": length,
        "sequence_length_core": length,
        "construct_scope": "unknown",
        "trim_status": "no_constants_detected",
        "trim_confidence": "n/a",
        "qc_flags": "",
        "experiment_group_id": "g1",
        "source_promoter_or_template_concern": promoter,
        "source_t7_concern": "false",
        "sequence_corrected_applied": "0",
        "group_covered_by_rule_review": group_covered,
        "legacy_collapse_member": "false",
        "exact_sequence_full_duplicate_diagnostic": "false",
        "constant_proposal_ids": "",
        "constant_proposal_sources": "",
        "constant_proposal_sides": "",
        "constant_group_id": "",
        "constant_records_in_group": "",
        "constant_support": "",
        "constant_proposed_trim_length": "",
        "notes": "",
    }


def _detail(review: dict[str, str], *, sequence: str) -> dict[str, str]:
    length = str(len(sequence)) if sequence else review["sequence_length_core"]
    row = {column: review.get(column, "") for column in LOCAL_DETAIL_COLUMNS}
    row.update(
        {
            "publication": "",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "detected_constant_5p": "",
            "detected_constant_3p": "",
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


def _canonical(review: dict[str, str], sequence: str) -> dict[str, str]:
    return {
        "record_id": review["record_id"],
        "native_id": review["native_id"],
        "sequence_raw": sequence,
        "sequence_full": sequence,
        "sequence_core": sequence,
        "sequence_length_full": str(len(sequence)),
        "sequence_length_core": str(len(sequence)),
        "target_name_raw": review["target_name_raw"],
        "t_to_u_applied": review["t_to_u_applied"],
        "molecule_type": "RNA",
        "chemistry": "RNA",
    }


def test_blank_package_fails_closed_and_leaves_human_fields_blank(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    checkpoint = repo / "data" / "interim" / "checkpoints" / "ena_cp1"
    motif = "ACGUACGU"
    seq_ok = _rna(40)
    seq_grp = motif + _rna(32)
    seq_short = _rna(17)
    reviews = [
        _review(
            "ena:ok",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="04_random_kept_audit",
            priority="low",
            secondary="random_accept_audit",
            review_reasons="random_kept_audit",
        ),
        _review(
            "ena:grp",
            decision="proposed_park",
            primary="trim_construct_unresolved",
            required="false",
            route="parked_construct_review",
            group_covered="true",
            review_reasons="constant_region_proposal",
        ),
        _review(
            "ena:short",
            decision="proposed_reject",
            primary="length_out_of_range",
            required="true",
            batch="01_judgement_dependent_technical",
            priority="high",
            review_reasons="judgement_dependent_technical",
            route="technical_reject",
            length="17",
        ),
    ]
    sequences = {
        "ena:ok": seq_ok,
        "ena:grp": seq_grp,
        "ena:short": seq_short,
    }
    details = [_detail(row, sequence=sequences[row["record_id"]]) for row in reviews]
    canonical_rows = [
        _canonical(row, sequences[row["record_id"]]) for row in reviews
    ]
    _write_csv(checkpoint / "ena_checkpoint1_review.csv", list(DECISION_COLUMNS), reviews)
    _write_csv(
        checkpoint / "ena_checkpoint1_local_detail.csv",
        list(LOCAL_DETAIL_COLUMNS),
        details,
    )
    _write_csv(
        checkpoint / "ena_s3_canonical.csv",
        list(canonical_rows[0].keys()),
        canonical_rows,
    )
    _write_csv(
        repo / "data" / "interim" / "normalised" / "ena_constant_region_proposals.csv",
        list(CONSTANT_PROPOSAL_COLUMNS),
        [
            {
                "proposal_id": "g1:five_prime:group_consensus",
                "experiment_group_id": "g1",
                "proposal_source": "group_consensus",
                "side": "five_prime",
                "proposed_sequence": motif,
                "motif_length": str(len(motif)),
                "support": "0.8",
                "records_considered": "1",
                "records_matching_exactly": "1",
                "confidence": "medium",
                "applied": "false",
            }
        ],
    )
    _write_csv(
        repo / "data" / "interim" / "normalised" / "ena_constant_region_membership.csv",
        list(MEMBERSHIP_COLUMNS),
        [
            {
                "proposal_id": "g1:five_prime:group_consensus",
                "experiment_group_id": "g1",
                "record_id": "ena:grp",
                "proposal_source": "group_consensus",
                "side": "five_prime",
            }
        ],
    )
    result = prepare_ena_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_total_rows=3,
        expected_active_rows=2,
    )
    assert result.stats.active_review_rows == 2
    assert result.stats.no_review_records == 1
    queue = list(csv.DictReader(result.output_queue.open(encoding="utf-8", newline="")))
    assert list(queue[0].keys()) == list(ENA_MANUAL_REVIEW_COLUMNS)
    assert all(row["manual_decision"] == "" for row in queue)
    assert {row["record_id"] for row in queue} == {"ena:ok", "ena:short"}
    recs = {row["record_id"]: row["review_recommendation"] for row in queue}
    assert recs["ena:short"] == "confirm_current_length_reject"
    assert recs["ena:ok"] == "keep_current_route"
    assert recs["ena:short"] != queue[0]["manual_decision"]
    index = list(csv.DictReader(result.output_index.open(encoding="utf-8", newline="")))
    assert list(index[0].keys()) == list(ENA_INDEX_COLUMNS)
    assert "sequence_core" not in index[0]
    assert "detected_constant_5p" not in index[0]
    rules = list(
        csv.DictReader(result.output_group_review.open(encoding="utf-8", newline=""))
    )
    assert len(rules) == 1
    assert rules[0]["manual_trim_action"] == ""
    assert "proposed_sequence" not in rules[0]
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "ACGU" not in summary
    assert "No human decision has yet been recorded." in summary
    validation = result.output_validation.read_text(encoding="utf-8")
    assert "ready for application: `0`" in validation

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = validate_main(
            [
                "--source",
                "ena",
                "--repo-root",
                str(repo),
                "--checkpoint-dir",
                str(checkpoint),
            ]
        )
    assert code == 2
    assert "ready_for_application=0" in stdout.getvalue()
    assert "CHECKPOINT-1 is not closed" in stdout.getvalue()

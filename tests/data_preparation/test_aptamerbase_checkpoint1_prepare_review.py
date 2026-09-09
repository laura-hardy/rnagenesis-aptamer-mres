"""Tests for AptamerBase CHECKPOINT-1 review-package preparation (synthetic only).

Every literal nucleotide string is a short runtime-built tile.
Does not read real AptamerBase checkpoint data.
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

from adapters.aptadb_checkpoint1_review import MANUAL_FIELDS  # noqa: E402
from adapters.aptamerbase_s3 import DECISION_COLUMNS, LOCAL_DETAIL_COLUMNS  # noqa: E402
from checkpoint1_apply_review import (  # noqa: E402
    main as apply_main,
)
from checkpoint1_prepare_review import (  # noqa: E402
    APTAMERBASE_INDEX_COLUMNS,
    APTAMERBASE_MANUAL_REVIEW_COLUMNS,
    prepare_aptamerbase_checkpoint1_review,
)
from checkpoint1_validate_review import (  # noqa: E402
    main as validate_main,
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
    molecule_type: str = "RNA",
    chemistry: str = "RNA",
    source_object_type: str = "aptamer",
) -> dict[str, str]:
    native = record_id.split(":")[-1]
    row = {column: "" for column in DECISION_COLUMNS}
    row.update(
        {
            "record_id": record_id,
            "native_id": native,
            "aptamer_name": f"name-{native}",
            "aptamerbase_id": native,
            "source_object_type": source_object_type,
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
            "molecule_type": molecule_type,
            "chemistry": chemistry,
            "alphabet_as_reported": "RNA",
            "sequence_length_full": "40",
            "sequence_length_core": "40",
            "construct_scope": "unknown",
            "trim_status": "no_constants_detected",
            "trim_confidence": "n/a",
            "qc_flags": "",
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
            "aptamerbase_label": f"label-{review['native_id']}",
            "aptamerbase_type": "http://rdf.freebase.com/ns/base.aptamer.aptamer",
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


def test_prepare_leaves_manual_blank_and_excludes_automatic_rows(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    rec_path = (
        repo
        / "config"
        / "checkpoint_reviews"
        / "aptamerbase_checkpoint1_recommendations.json"
    )
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text(
        (
            REPO_ROOT
            / "config"
            / "checkpoint_reviews"
            / "aptamerbase_checkpoint1_recommendations.json"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    checkpoint = repo / "data" / "interim" / "checkpoints" / "aptamerbase_cp1"
    reviews = [
        _review(
            "aptamerbase:keep",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="false",
            route="technically_eligible",
        ),
        _review(
            "aptamerbase:missing",
            decision="proposed_reject",
            primary="missing_sequence",
            required="false",
            route="technical_reject",
        ),
        _review(
            "aptamerbase:structure",
            decision="proposed_reject",
            primary="non_aptamer_source_object",
            required="false",
            route="technical_reject",
            source_object_type="nucleic_acid_secondary_structure",
        ),
        _review(
            "aptamerbase:ssdna",
            decision="proposed_park",
            primary="ssdna_parked",
            required="false",
            route="parked_ssdna",
            molecule_type="ssDNA",
            chemistry="DNA",
        ),
        _review(
            "aptamerbase:length",
            decision="proposed_reject",
            primary="length_out_of_range",
            required="false",
            route="technical_reject",
        ),
        _review(
            "aptamerbase:invalid",
            decision="proposed_reject",
            primary="invalid_alphabet",
            required="true",
            batch="01_sequence_or_source_conflict",
            priority="high",
            review_reasons="sequence_notation",
            route="technical_reject",
        ),
        _review(
            "aptamerbase:conflict",
            decision="proposed_park",
            primary="ssdna_parked",
            required="true",
            batch="01_sequence_or_source_conflict",
            priority="high",
            review_reasons="source_molecule_alphabet_conflict",
            route="parked_ssdna",
            molecule_type="ssDNA",
            chemistry="DNA",
        ),
        _review(
            "aptamerbase:unknown",
            decision="proposed_park",
            primary="molecule_type_unresolved",
            required="true",
            batch="02_molecule_type_unresolved",
            priority="high",
            review_reasons="molecule_type_unresolved",
            route="parked_molecule_unresolved",
            molecule_type="unknown",
            chemistry="unknown",
        ),
        _review(
            "aptamerbase:chem",
            decision="proposed_park",
            primary="chemistry_requires_review",
            required="true",
            batch="03_chemistry_review",
            priority="high",
            review_reasons="chemistry_requires_review|spiegelmer_l_rna",
            route="parked_chemistry_review",
            chemistry="unknown",
        ),
        _review(
            "aptamerbase:motif",
            decision="proposed_park",
            primary="trim_construct_unresolved",
            required="true",
            batch="04_known_motif_construct",
            priority="medium",
            secondary="known_motif_proposal",
            review_reasons="constant_region_proposal",
            route="parked_construct_review",
        ),
        _review(
            "aptamerbase:boundary",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="05_accept_with_diagnostics",
            priority="low",
            secondary="lower_length_boundary",
            review_reasons="length_boundary",
        ),
        _review(
            "aptamerbase:audit",
            decision="proposed_accept",
            primary="technically_eligible_rna",
            required="true",
            batch="06_random_kept_audit",
            priority="low",
            secondary="random_accept_audit",
            review_reasons="random_kept_audit",
        ),
    ]
    details = [_detail(row) for row in reviews]
    _write_csv(
        checkpoint / "aptamerbase_checkpoint1_review.csv",
        list(DECISION_COLUMNS),
        reviews,
    )
    _write_csv(
        checkpoint / "aptamerbase_checkpoint1_local_detail.csv",
        list(LOCAL_DETAIL_COLUMNS),
        details,
    )
    result = prepare_aptamerbase_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_total_rows=12,
        expected_active_rows=7,
    )
    assert result.stats.active_review_rows == 7
    assert result.stats.no_review_records == 5
    queue = list(
        csv.DictReader(result.output_queue.open(encoding="utf-8", newline=""))
    )
    assert list(queue[0].keys()) == list(APTAMERBASE_MANUAL_REVIEW_COLUMNS)
    for row in queue:
        for name in MANUAL_FIELDS:
            assert row.get(name, "") == ""
    ids = [row["record_id"] for row in queue]
    assert "aptamerbase:missing" not in ids
    assert "aptamerbase:structure" not in ids
    assert "aptamerbase:ssdna" not in ids
    assert "aptamerbase:length" not in ids
    assert "aptamerbase:keep" not in ids
    assert len(ids) == len(set(ids))
    assert ids[0] in {"aptamerbase:conflict", "aptamerbase:invalid"}
    invalid = next(row for row in queue if row["record_id"] == "aptamerbase:invalid")
    assert invalid["review_recommendation"] == "inspect_sequence"
    conflict = next(row for row in queue if row["record_id"] == "aptamerbase:conflict")
    assert conflict["review_recommendation"] == "needs_source_review"
    unknown = next(row for row in queue if row["record_id"] == "aptamerbase:unknown")
    assert unknown["review_recommendation"] == "needs_source_review"
    chem = next(row for row in queue if row["record_id"] == "aptamerbase:chem")
    assert chem["review_recommendation"] == "needs_source_review"
    motif = next(row for row in queue if row["record_id"] == "aptamerbase:motif")
    assert motif["review_recommendation"] == "decide_trim"
    assert motif["recommended_trim_action"] == "defer"
    boundary = next(row for row in queue if row["record_id"] == "aptamerbase:boundary")
    assert boundary["audit_only_row"] == "true"
    assert boundary["review_recommendation"] == "keep_current_route"
    bulk = list(
        csv.DictReader(result.output_bulk_confirmation.open(encoding="utf-8", newline=""))
    )
    assert bulk[0]["confirm"] == ""
    assert bulk[0]["eligible_record_count"] == "2"
    audit_dir = checkpoint / "manual_review" / "audit"
    assert (audit_dir / "aptamerbase_checkpoint1_audit_summary.md").is_file()
    assert "ACGU" not in (
        audit_dir / "aptamerbase_checkpoint1_audit_summary.md"
    ).read_text(encoding="utf-8")
    index = list(csv.DictReader(result.output_index.open(encoding="utf-8", newline="")))
    assert list(index[0].keys()) == list(APTAMERBASE_INDEX_COLUMNS)
    assert "sequence_core" not in index[0]
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "ACGU" not in summary
    assert "No human decision has yet been recorded." in summary
    assert "fail closed" in summary.lower()
    assert "ready_for_application: `0`" in summary
    assert result.inputs_unchanged is True
    validation = result.output_validation.read_text(encoding="utf-8")
    assert "ready for application: `0`" in validation

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = validate_main(
            [
                "--source",
                "aptamerbase",
                "--repo-root",
                str(repo),
                "--checkpoint-dir",
                str(checkpoint),
            ]
        )
    assert code == 2
    assert "ready_for_application=0" in stdout.getvalue()
    assert "unresolved_manual_decisions=7" in stdout.getvalue()
    assert "unresolved_judgement_required=5" in stdout.getvalue()
    assert "audit_only_unconfirmed=2" in stdout.getvalue()
    assert "bulk_audit_confirmed=false" in stdout.getvalue()
    assert "CHECKPOINT-1 is not closed" in stdout.getvalue()

    apply_stdout = io.StringIO()
    apply_stderr = io.StringIO()
    with redirect_stdout(apply_stdout), redirect_stderr(apply_stderr):
        apply_code = apply_main(["--source", "aptamerbase"])
    assert apply_code == 1
    assert "not authorised" in apply_stderr.getvalue()
    assert "--dry-run" in apply_stderr.getvalue()

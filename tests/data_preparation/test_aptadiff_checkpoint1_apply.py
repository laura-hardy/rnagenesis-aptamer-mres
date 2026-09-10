"""AptaDiff CHECKPOINT-1 apply/validation tests (synthetic sequences only).

Does not read or embed real AptaDiff sequences.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadiff_checkpoint1_apply import (  # noqa: E402
    APTADIFF_TRACKED_RESOLUTION_COLUMNS,
    build_tracked_resolutions,
    tracked_payload_contains_sequence,
)
from adapters.aptadiff_checkpoint1_dry_run import (  # noqa: E402
    serialise_aptadiff_simulation_sequence_free,
    simulate_aptadiff_checkpoint1_application,
)
from adapters.aptadiff_checkpoint1_review import (  # noqa: E402
    CONFIRM_CURRENT_DECISION,
    CONFIRM_CURRENT_NOTE,
    MANUAL_FIELDS,
    AptaDiffCheckpoint1ReviewError,
    apply_aptadiff_checkpoint1_package,
    record_confirm_current_reject,
    validate_review_package,
)
from adapters.aptadiff_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    REJECTION_COLUMNS,
)
from checkpoint1_apply_review import (  # noqa: E402
    Checkpoint1ApplyError,
    main,
    run_aptadiff_checkpoint1_apply,
    run_aptadiff_checkpoint1_dry_run,
)
from checkpoint1_prepare_review import (  # noqa: E402
    APTADIFF_MANUAL_REVIEW_COLUMNS,
    prepare_aptadiff_checkpoint1_review,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402

SYNTHETIC_DNA_36 = "ACGT" * 9
SYNTHETIC_N_36 = ("ACGT" * 8) + "ACGN"
RECOMMENDATIONS_A = (
    REPO_ROOT / "config" / "checkpoint_reviews" / "aptadiff_a_checkpoint1_recommendations.json"
)
RECOMMENDATIONS_B = (
    REPO_ROOT / "config" / "checkpoint_reviews" / "aptadiff_b_checkpoint1_recommendations.json"
)


def _write_csv(path: Path, fieldnames: list[str] | tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _canonical(source_key: str, native_id: str, sequence: str) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence))
    record.update(
        {
            "record_id": f"{source_key}:{native_id}",
            "native_id": native_id,
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "random_region_only",
            "trim_status": "no_constants_detected",
            "trim_confidence": "n/a",
            "molecule_type": "ssDNA",
            "alphabet_as_reported": "ambiguous" if "N" in sequence else "DNA_T",
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
            "qc_flags": "ambiguous_base" if "N" in sequence else "",
        }
    )
    return record


def _decision(canonical: dict[str, str], *, reject: bool) -> dict[str, str]:
    row = {column: "" for column in DECISION_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "proposed_decision": "proposed_reject" if reject else "proposed_park",
            "primary_reason": "ambiguous_bases" if reject else "ssdna_parked",
            "secondary_reasons": "ssdna_parked" if reject else "",
            "primary_route": PRIMARY_ROUTE_REJECT if reject else PRIMARY_ROUTE_SSDNA,
            "manual_review_required": "true" if reject else "false",
            "manual_review_priority": "high" if reject else "none",
            "review_batch": "01_judgement_dependent_technical" if reject else "",
            "checkpoint_review_reasons": "judgement_dependent_technical" if reject else "",
            "checkpoint_status": "pending_checkpoint_1_review",
            "molecule_type": canonical["molecule_type"],
            "chemistry": canonical["chemistry"],
            "alphabet_as_reported": canonical["alphabet_as_reported"],
            "sequence_length_full": canonical["sequence_length_full"],
            "sequence_length_core": canonical["sequence_length_core"],
            "construct_scope": canonical["construct_scope"],
            "trim_status": canonical["trim_status"],
            "trim_confidence": canonical["trim_confidence"],
            "qc_flags": canonical["qc_flags"],
            "aptadiff_dataset": "A" if canonical["source_db"].endswith("_a") else "B",
            "aptadiff_documented_target": "IGFBP3" if canonical["source_db"].endswith("_a") else "PTK7",
            "aptadiff_p6": "9",
        }
    )
    return row


def _local_detail(decision: dict[str, str], sequence: str) -> dict[str, str]:
    row = {column: "" for column in LOCAL_DETAIL_COLUMNS}
    row.update(decision)
    row["sequence_raw"] = sequence
    row["sequence_full"] = sequence
    row["sequence_core"] = sequence
    row["t_to_u_applied"] = "false"
    for name in MANUAL_FIELDS:
        row[name] = ""
    return row


def _park(decision: dict[str, str]) -> dict[str, str]:
    return {
        "record_id": decision["record_id"],
        "native_id": decision["native_id"],
        "proposed_decision": decision["proposed_decision"],
        "park_reason": decision["primary_reason"],
        "secondary_reasons": decision["secondary_reasons"],
        "manual_review_required": decision["manual_review_required"],
        "review_batch": decision["review_batch"],
        "molecule_type": decision["molecule_type"],
        "chemistry": decision["chemistry"],
        "sequence_length_core": decision["sequence_length_core"],
        "trim_status": decision["trim_status"],
        "trim_confidence": decision["trim_confidence"],
        "qc_flags": decision["qc_flags"],
    }


def _rejection(canonical: dict[str, str]) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "source_db": canonical["source_db"],
        "source_dataset": canonical["source_dataset"],
        "native_id": canonical["native_id"],
        "sequence_raw": canonical["sequence_raw"],
        "target_name_raw": "",
        "stage": "S3",
        "rejection_reason": "ambiguous_bases",
        "rejection_detail": "ssdna_parked",
    }


def _bulk() -> dict[str, str]:
    return {
        "confirmation_id": "audit_only_keep_current_route",
        "scope": "length_boundary_and_or_random_kept_audit_only",
        "eligible_record_count": "0",
        "eligible_record_ids": "",
        "confirm": "",
        "reviewer_initials": "",
        "manual_notes": "",
    }


def _build_source(
    tmp_path: Path,
    *,
    source_key: str,
    n_park: int,
    n_reject: int,
    complete: bool = True,
) -> Path:
    repo = tmp_path / source_key
    checkpoint = repo / "data" / "interim" / "checkpoints" / f"{source_key}_cp1"
    rec_dir = repo / "config" / "checkpoint_reviews"
    rec_dir.mkdir(parents=True)
    src = RECOMMENDATIONS_A if source_key == "aptadiff_a" else RECOMMENDATIONS_B
    rec_dir.joinpath(src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    canonical_rows = []
    decision_rows = []
    local_rows = []
    park_rows = []
    rejection_rows = []
    native = 1
    for _ in range(n_park):
        nid = f"{native:05d}"
        canon = _canonical(source_key, nid, SYNTHETIC_DNA_36)
        decision = _decision(canon, reject=False)
        canonical_rows.append(canon)
        decision_rows.append(decision)
        local_rows.append(_local_detail(decision, SYNTHETIC_DNA_36))
        park_rows.append(_park(decision))
        native += 1
    for _ in range(n_reject):
        nid = f"{native:05d}"
        canon = _canonical(source_key, nid, SYNTHETIC_N_36)
        decision = _decision(canon, reject=True)
        canonical_rows.append(canon)
        decision_rows.append(decision)
        local_rows.append(_local_detail(decision, SYNTHETIC_N_36))
        rejection_rows.append(_rejection(canon))
        native += 1

    _write_csv(checkpoint / f"{source_key}_s3_canonical.csv", list(canonical_rows[0].keys()), canonical_rows)
    _write_csv(checkpoint / f"{source_key}_s3_decisions.csv", list(DECISION_COLUMNS), decision_rows)
    _write_csv(checkpoint / f"{source_key}_checkpoint1_review.csv", list(DECISION_COLUMNS), decision_rows)
    _write_csv(checkpoint / f"{source_key}_checkpoint1_local_detail.csv", list(LOCAL_DETAIL_COLUMNS), local_rows)
    _write_csv(checkpoint / f"{source_key}_s3_parked_ssdna.csv", list(PARK_COLUMNS), park_rows)
    _write_csv(checkpoint / f"rejected_{source_key}.csv", list(REJECTION_COLUMNS), rejection_rows)

    review_dir = checkpoint / "manual_review"
    prepare_aptadiff_checkpoint1_review(
        repo_root=repo,
        source_key=source_key,
        checkpoint_dir=checkpoint,
        output_dir=review_dir,
        expected_active_rows=n_reject,
        expected_total_rows=n_park + n_reject,
    )
    if complete:
        queue_path = review_dir / f"{source_key}_checkpoint1_manual_review.csv"
        queue = list(csv.DictReader(queue_path.open(encoding="utf-8")))
        completed = [record_confirm_current_reject(row) for row in queue]
        _write_csv(queue_path, list(APTADIFF_MANUAL_REVIEW_COLUMNS), completed)
        index_path = review_dir / f"{source_key}_checkpoint1_manual_review_index.csv"
        if index_path.is_file():
            index_rows = list(csv.DictReader(index_path.open(encoding="utf-8")))
            by_id = {row["record_id"]: row for row in completed}
            for row in index_rows:
                match = by_id.get(row["record_id"], {})
                for name in MANUAL_FIELDS:
                    if name in row:
                        row[name] = match.get(name, "")
            fields = list(index_rows[0].keys()) if index_rows else []
            if fields:
                _write_csv(index_path, fields, index_rows)
    return repo


def test_completed_one_row_a_style_validates(tmp_path: Path) -> None:
    repo = _build_source(tmp_path, source_key="aptadiff_a", n_park=2, n_reject=1)
    queue = list(
        csv.DictReader(
            (repo / "data/interim/checkpoints/aptadiff_a_cp1/manual_review/aptadiff_a_checkpoint1_manual_review.csv").open(
                encoding="utf-8"
            )
        )
    )
    bulk = [_bulk()]
    report = validate_review_package(
        queue_rows=queue,
        group_rows=[],
        bulk_confirmation=bulk[0],
    )
    assert report.ok
    assert report.total_review_records == 1
    assert report.unresolved_manual_decisions == 0
    assert report.blocking_issues == []
    assert report.ready_for_application == 1


def test_completed_multi_row_b_style_validates(tmp_path: Path) -> None:
    repo = _build_source(tmp_path, source_key="aptadiff_b", n_park=3, n_reject=15)
    queue = list(
        csv.DictReader(
            (repo / "data/interim/checkpoints/aptadiff_b_cp1/manual_review/aptadiff_b_checkpoint1_manual_review.csv").open(
                encoding="utf-8"
            )
        )
    )
    report = validate_review_package(
        queue_rows=queue,
        group_rows=[],
        bulk_confirmation=_bulk(),
    )
    assert report.ok
    assert report.total_review_records == 15
    assert report.unresolved_manual_decisions == 0
    assert report.ready_for_application == 15


def test_confirm_current_reject_preserves_ambiguous_bases(tmp_path: Path) -> None:
    repo = _build_source(tmp_path, source_key="aptadiff_a", n_park=1, n_reject=1)
    checkpoint = repo / "data/interim/checkpoints/aptadiff_a_cp1"
    queue = list(
        csv.DictReader(
            (checkpoint / "manual_review/aptadiff_a_checkpoint1_manual_review.csv").open(
                encoding="utf-8"
            )
        )
    )
    canonical = list(csv.DictReader((checkpoint / "aptadiff_a_s3_canonical.csv").open(encoding="utf-8")))
    decisions = list(csv.DictReader((checkpoint / "aptadiff_a_s3_decisions.csv").open(encoding="utf-8")))
    rejections = list(csv.DictReader((checkpoint / "rejected_aptadiff_a.csv").open(encoding="utf-8")))
    applied, report = apply_aptadiff_checkpoint1_package(
        queue_rows=queue,
        group_rows=[],
        canonical_by_id={row["record_id"]: row for row in canonical},
        decision_by_id={row["record_id"]: row for row in decisions},
        rejection_by_id={row["record_id"]: row for row in rejections},
        bulk_confirmation=_bulk(),
    )
    assert report.ok
    assert len(applied) == 1
    assert applied[0].primary_reason == "ambiguous_bases"
    assert applied[0].primary_route_after == PRIMARY_ROUTE_REJECT
    assert applied[0].rejection_row is not None
    assert applied[0].rejection_row["rejection_reason"] == "ambiguous_bases"
    assert applied[0].sequence_corrected is False
    assert "N" in applied[0].sequence_full
    assert applied[0].manual_decision if hasattr(applied[0], "manual_decision") else True
    assert queue[0]["manual_decision"] == CONFIRM_CURRENT_DECISION
    assert queue[0]["manual_sequence_corrected"] == ""


def test_no_sequence_correction_required(tmp_path: Path) -> None:
    repo = _build_source(tmp_path, source_key="aptadiff_a", n_park=1, n_reject=1)
    queue = list(
        csv.DictReader(
            (
                repo
                / "data/interim/checkpoints/aptadiff_a_cp1/manual_review/aptadiff_a_checkpoint1_manual_review.csv"
            ).open(encoding="utf-8")
        )
    )
    assert queue[0]["manual_sequence_corrected"] == ""
    assert queue[0]["manual_notes"] == CONFIRM_CURRENT_NOTE


def test_reviewed_ambiguous_ssdna_remains_rejected_not_park(tmp_path: Path) -> None:
    repo = _build_source(tmp_path, source_key="aptadiff_a", n_park=2, n_reject=1)
    checkpoint = repo / "data/interim/checkpoints/aptadiff_a_cp1"
    simulation = simulate_aptadiff_checkpoint1_application(
        source_key="aptadiff_a",
        queue_rows=list(
            csv.DictReader(
                (checkpoint / "manual_review/aptadiff_a_checkpoint1_manual_review.csv").open(
                    encoding="utf-8"
                )
            )
        ),
        group_rows=[],
        canonical_rows=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_canonical.csv").open(encoding="utf-8"))
        ),
        decision_rows=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_decisions.csv").open(encoding="utf-8"))
        ),
        existing_rejection_rows=list(
            csv.DictReader((checkpoint / "rejected_aptadiff_a.csv").open(encoding="utf-8"))
        ),
        existing_parked_ssdna=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_parked_ssdna.csv").open(encoding="utf-8"))
        ),
        bulk_confirmation=_bulk(),
        expected_source_rows=3,
        expected_reviewed_rows=1,
    )
    reviewed_id = simulation.applied[0].record_id
    assert simulation.applied[0].primary_route_after == PRIMARY_ROUTE_REJECT
    parked_ids = {row["record_id"] for row in simulation.preview_parked_ssdna}
    assert reviewed_id not in parked_ids
    assert reviewed_id in {row["record_id"] for row in simulation.preview_rejections}


def test_no_review_clean_ssdna_remains_parked(tmp_path: Path) -> None:
    repo = _build_source(tmp_path, source_key="aptadiff_a", n_park=2, n_reject=1)
    checkpoint = repo / "data/interim/checkpoints/aptadiff_a_cp1"
    simulation = simulate_aptadiff_checkpoint1_application(
        source_key="aptadiff_a",
        queue_rows=list(
            csv.DictReader(
                (checkpoint / "manual_review/aptadiff_a_checkpoint1_manual_review.csv").open(
                    encoding="utf-8"
                )
            )
        ),
        group_rows=[],
        canonical_rows=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_canonical.csv").open(encoding="utf-8"))
        ),
        decision_rows=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_decisions.csv").open(encoding="utf-8"))
        ),
        existing_rejection_rows=list(
            csv.DictReader((checkpoint / "rejected_aptadiff_a.csv").open(encoding="utf-8"))
        ),
        existing_parked_ssdna=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_parked_ssdna.csv").open(encoding="utf-8"))
        ),
        bulk_confirmation=_bulk(),
        expected_source_rows=3,
        expected_reviewed_rows=1,
    )
    assert simulation.stats["parked_ssdna"] == 2
    for row in simulation.preview_parked_ssdna:
        assert row["park_reason"] == "ssdna_parked"
        assert row["manual_review_required"] == "false"


def test_no_reviewed_record_becomes_s4_authorised_and_zero_is_valid(tmp_path: Path) -> None:
    repo = _build_source(tmp_path, source_key="aptadiff_b", n_park=2, n_reject=15)
    checkpoint = repo / "data/interim/checkpoints/aptadiff_b_cp1"
    simulation = simulate_aptadiff_checkpoint1_application(
        source_key="aptadiff_b",
        queue_rows=list(
            csv.DictReader(
                (checkpoint / "manual_review/aptadiff_b_checkpoint1_manual_review.csv").open(
                    encoding="utf-8"
                )
            )
        ),
        group_rows=[],
        canonical_rows=list(
            csv.DictReader((checkpoint / "aptadiff_b_s3_canonical.csv").open(encoding="utf-8"))
        ),
        decision_rows=list(
            csv.DictReader((checkpoint / "aptadiff_b_s3_decisions.csv").open(encoding="utf-8"))
        ),
        existing_rejection_rows=list(
            csv.DictReader((checkpoint / "rejected_aptadiff_b.csv").open(encoding="utf-8"))
        ),
        existing_parked_ssdna=list(
            csv.DictReader((checkpoint / "aptadiff_b_s3_parked_ssdna.csv").open(encoding="utf-8"))
        ),
        bulk_confirmation=_bulk(),
        expected_source_rows=17,
        expected_reviewed_rows=15,
    )
    assert simulation.stats["authorised_for_s4"] == 0
    assert simulation.stats["technically_eligible"] == 0
    assert simulation.preview_eligible == []
    for item in simulation.applied:
        assert item.primary_route_after != PRIMARY_ROUTE_ELIGIBLE
        for field_name in S3_FORBIDDEN_FIELDS:
            assert item.canonical.get(field_name, "") == ""


def test_zero_eligible_rna_audit_pool_does_not_manufacture_review_rows() -> None:
    report = validate_review_package(
        queue_rows=[],
        group_rows=[],
        bulk_confirmation=_bulk(),
    )
    assert report.ok
    assert report.total_review_records == 0
    assert report.audit_only_rows == 0
    bulk = _bulk()
    bulk["confirm"] = "true"
    blocked = validate_review_package(
        queue_rows=[],
        group_rows=[],
        bulk_confirmation=bulk,
    )
    assert not blocked.ok


def test_unresolved_decision_still_fails_closed(tmp_path: Path) -> None:
    repo = _build_source(
        tmp_path, source_key="aptadiff_a", n_park=1, n_reject=1, complete=False
    )
    queue = list(
        csv.DictReader(
            (
                repo
                / "data/interim/checkpoints/aptadiff_a_cp1/manual_review/aptadiff_a_checkpoint1_manual_review.csv"
            ).open(encoding="utf-8")
        )
    )
    report = validate_review_package(
        queue_rows=queue, group_rows=[], bulk_confirmation=_bulk()
    )
    assert not report.ok
    assert report.unresolved_manual_decisions == 1
    with pytest.raises(AptaDiffCheckpoint1ReviewError):
        apply_aptadiff_checkpoint1_package(
            queue_rows=queue,
            group_rows=[],
            canonical_by_id={},
            decision_by_id={},
            rejection_by_id={},
            bulk_confirmation=_bulk(),
        )


def test_dry_run_does_not_write_resolved_and_apply_uses_same_transform(
    tmp_path: Path,
) -> None:
    repo = _build_source(tmp_path, source_key="aptadiff_a", n_park=2, n_reject=1)
    checkpoint = repo / "data/interim/checkpoints/aptadiff_a_cp1"
    dry_dir = checkpoint / "dry_run"
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        run_aptadiff_checkpoint1_dry_run(
            repo_root=repo,
            source_key="aptadiff_a",
            checkpoint_dir=checkpoint,
            output_dir=dry_dir,
            check_deterministic_rerun=True,
            expected_source_rows=3,
            expected_reviewed_rows=1,
            verify_frozen_inputs=False,
            compare_to_pristine=True,
        )
    assert not (checkpoint / "resolved").exists()
    assert "CHECKPOINT-1 is not closed" in buf.getvalue()
    assert not (repo / "config/checkpoint_reviews/aptadiff_a_checkpoint1_resolutions.csv").exists()

    queue = list(
        csv.DictReader(
            (checkpoint / "manual_review/aptadiff_a_checkpoint1_manual_review.csv").open(
                encoding="utf-8"
            )
        )
    )
    first = simulate_aptadiff_checkpoint1_application(
        source_key="aptadiff_a",
        queue_rows=queue,
        group_rows=[],
        canonical_rows=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_canonical.csv").open(encoding="utf-8"))
        ),
        decision_rows=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_decisions.csv").open(encoding="utf-8"))
        ),
        existing_rejection_rows=list(
            csv.DictReader((checkpoint / "rejected_aptadiff_a.csv").open(encoding="utf-8"))
        ),
        existing_parked_ssdna=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_parked_ssdna.csv").open(encoding="utf-8"))
        ),
        bulk_confirmation=_bulk(),
        expected_source_rows=3,
        expected_reviewed_rows=1,
    )
    apply_buf = io.StringIO()
    with redirect_stdout(apply_buf), redirect_stderr(apply_buf):
        result = run_aptadiff_checkpoint1_apply(
            repo_root=repo,
            source_key="aptadiff_a",
            checkpoint_dir=checkpoint,
            output_dir=checkpoint / "resolved",
            tracked_manifest=repo
            / "config/checkpoint_reviews/aptadiff_a_checkpoint1_resolutions.csv",
            metadata_out=repo
            / "config/checkpoint_reviews/aptadiff_a_checkpoint1_metadata.json",
            check_deterministic_rerun=True,
            expected_source_rows=3,
            expected_reviewed_rows=1,
            verify_frozen_inputs=False,
            compare_to_pristine=True,
            compare_to_preview=True,
        )
    second = simulate_aptadiff_checkpoint1_application(
        source_key="aptadiff_a",
        queue_rows=queue,
        group_rows=[],
        canonical_rows=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_canonical.csv").open(encoding="utf-8"))
        ),
        decision_rows=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_decisions.csv").open(encoding="utf-8"))
        ),
        existing_rejection_rows=list(
            csv.DictReader((checkpoint / "rejected_aptadiff_a.csv").open(encoding="utf-8"))
        ),
        existing_parked_ssdna=list(
            csv.DictReader((checkpoint / "aptadiff_a_s3_parked_ssdna.csv").open(encoding="utf-8"))
        ),
        bulk_confirmation=_bulk(),
        expected_source_rows=3,
        expected_reviewed_rows=1,
    )
    assert serialise_aptadiff_simulation_sequence_free(
        first
    ) == serialise_aptadiff_simulation_sequence_free(second)
    assert result.semantic_mismatches == 0
    assert first.stats["parked_ssdna"] == second.stats["parked_ssdna"]
    assert first.stats["technical_rejects_after_review"] == second.stats[
        "technical_rejects_after_review"
    ]


def test_tracked_resolution_artefacts_are_sequence_free_and_separate(
    tmp_path: Path,
) -> None:
    repo_a = _build_source(tmp_path / "a", source_key="aptadiff_a", n_park=1, n_reject=1)
    repo_b = _build_source(tmp_path / "b", source_key="aptadiff_b", n_park=1, n_reject=2)
    for repo, source_key, n_total, n_review in (
        (repo_a, "aptadiff_a", 2, 1),
        (repo_b, "aptadiff_b", 3, 2),
    ):
        checkpoint = repo / "data/interim/checkpoints" / f"{source_key}_cp1"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            run_aptadiff_checkpoint1_dry_run(
                repo_root=repo,
                source_key=source_key,
                checkpoint_dir=checkpoint,
                output_dir=checkpoint / "dry_run",
                check_deterministic_rerun=False,
                expected_source_rows=n_total,
                expected_reviewed_rows=n_review,
                verify_frozen_inputs=False,
                compare_to_pristine=False,
            )
            run_aptadiff_checkpoint1_apply(
                repo_root=repo,
                source_key=source_key,
                checkpoint_dir=checkpoint,
                output_dir=checkpoint / "resolved",
                tracked_manifest=repo
                / "config/checkpoint_reviews"
                / f"{source_key}_checkpoint1_resolutions.csv",
                metadata_out=repo
                / "config/checkpoint_reviews"
                / f"{source_key}_checkpoint1_metadata.json",
                check_deterministic_rerun=False,
                expected_source_rows=n_total,
                expected_reviewed_rows=n_review,
                verify_frozen_inputs=False,
                compare_to_pristine=False,
                compare_to_preview=True,
            )
    res_a = (
        repo_a / "config/checkpoint_reviews/aptadiff_a_checkpoint1_resolutions.csv"
    )
    res_b = (
        repo_b / "config/checkpoint_reviews/aptadiff_b_checkpoint1_resolutions.csv"
    )
    meta_a = json.loads(
        (repo_a / "config/checkpoint_reviews/aptadiff_a_checkpoint1_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    meta_b = json.loads(
        (repo_b / "config/checkpoint_reviews/aptadiff_b_checkpoint1_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert res_a != res_b
    assert meta_a["source_key"] == "aptadiff_a"
    assert meta_b["source_key"] == "aptadiff_b"
    assert meta_a["checkpoint1_closed"] is True
    assert meta_b["authorised_for_s4"] == 0
    text_a = res_a.read_text(encoding="utf-8")
    text_b = res_b.read_text(encoding="utf-8")
    assert not tracked_payload_contains_sequence(text_a)
    assert not tracked_payload_contains_sequence(text_b)
    assert SYNTHETIC_N_36 not in text_a
    assert SYNTHETIC_DNA_36 not in text_a
    fields = list(csv.DictReader(res_a.open(encoding="utf-8")).fieldnames or [])
    assert fields == list(APTADIFF_TRACKED_RESOLUTION_COLUMNS)
    rows = list(csv.DictReader(res_a.open(encoding="utf-8")))
    reviewed = [row for row in rows if row["manual_review_required"] == "true"]
    parks = [row for row in rows if row["manual_review_required"] == "false"]
    assert len(reviewed) == 1
    assert reviewed[0]["manual_decision"] == "keep"
    assert reviewed[0]["primary_reason"] == "ambiguous_bases"
    assert reviewed[0]["authorised_for_s4"] == "false"
    assert parks[0]["manual_decision"] == ""
    assert parks[0]["primary_route"] == PRIMARY_ROUTE_SSDNA


def test_cli_dry_run_then_apply(tmp_path: Path) -> None:
    repo = _build_source(tmp_path, source_key="aptadiff_a", n_park=1, n_reject=1)
    checkpoint = repo / "data/interim/checkpoints/aptadiff_a_cp1"
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        code = main(
            [
                "--source",
                "aptadiff_a",
                "--dry-run",
                "--repo-root",
                str(repo),
                "--checkpoint-dir",
                str(checkpoint),
                "--expected-total-rows",
                "2",
                "--expected-active-rows",
                "1",
                "--skip-pipeline-integrity",
                "--skip-deterministic-rerun",
            ]
        )
    assert code == 0
    assert "mode=dry_run" in buf.getvalue()
    apply_buf = io.StringIO()
    with redirect_stdout(apply_buf), redirect_stderr(apply_buf):
        code = main(
            [
                "--source",
                "aptadiff_a",
                "--repo-root",
                str(repo),
                "--checkpoint-dir",
                str(checkpoint),
                "--expected-total-rows",
                "2",
                "--expected-active-rows",
                "1",
                "--skip-pipeline-integrity",
                "--skip-deterministic-rerun",
            ]
        )
    assert code == 0
    assert "checkpoint_closed=true" in apply_buf.getvalue()


def test_edit_and_drop_fail_closed(tmp_path: Path) -> None:
    repo = _build_source(tmp_path, source_key="aptadiff_a", n_park=1, n_reject=1)
    queue_path = (
        repo
        / "data/interim/checkpoints/aptadiff_a_cp1/manual_review/aptadiff_a_checkpoint1_manual_review.csv"
    )
    queue = list(csv.DictReader(queue_path.open(encoding="utf-8")))
    edited = dict(queue[0])
    edited["manual_decision"] = "edit"
    edited["manual_sequence_corrected"] = SYNTHETIC_DNA_36
    report = validate_review_package(
        queue_rows=[edited], group_rows=[], bulk_confirmation=_bulk()
    )
    assert not report.ok
    dropped = dict(queue[0])
    dropped["manual_decision"] = "drop"
    report = validate_review_package(
        queue_rows=[dropped], group_rows=[], bulk_confirmation=_bulk()
    )
    assert not report.ok

"""Structured RiboAptamer CHECKPOINT-1 review/apply tests (synthetic only).

Literal nucleotides are either short fixtures or repeating ACGU tiles.
Does not read real RiboAptamer source sequences.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.riboaptamer_checkpoint1_review import (  # noqa: E402
    RiboAptamerCheckpoint1ReviewError,
    apply_riboaptamer_checkpoint1_package,
    validate_review_package,
)
from adapters.riboaptamer_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    LOCAL_DETAIL_COLUMNS,
    REJECTION_COLUMNS,
)
from checkpoint1_apply_review import (  # noqa: E402
    Checkpoint1ApplyError,
    run_riboaptamer_checkpoint1_apply,
)
from checkpoint1_prepare_review import (  # noqa: E402
    RIBOAPTAMER_MANUAL_REVIEW_COLUMNS,
    prepare_riboaptamer_checkpoint1_review,
)
from common.corpus_schema import CORPUS_COLUMNS, S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import load_eligibility_policy  # noqa: E402

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "riboaptamer.json"
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _canonical(*, native_id: str = "1", sequence: str = "", **overrides: str) -> dict[str, str]:
    sequence = sequence or _rna(40)
    record = empty_corpus_record()
    length = str(len(sequence))
    record.update(
        {
            "record_id": f"riboaptamer:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": "no_constants_detected",
            "trim_confidence": "n/a",
            "molecule_type": "RNA",
            "alphabet_as_reported": "RNA",
            "t_to_u_applied": "false",
            "chemistry": "RNA",
            "target_name_raw": "",
            "source_db": "riboaptamer",
            "source_dataset": "riboaptamer_full_2026-08",
            "contributing_sources": "riboaptamer",
            "contributing_datasets": "riboaptamer_full_2026-08",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "qc_flags": "",
        }
    )
    record.update(overrides)
    return record


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _decision(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
    row = {column: "" for column in DECISION_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "aptamer_name": f"name-{canonical['native_id']}",
            "target_name_raw": "",
            "proposed_decision": "proposed_accept",
            "primary_reason": "technically_eligible_rna",
            "secondary_reasons": "lower_length_boundary",
            "primary_route": "technically_eligible",
            "manual_review_required": "true",
            "manual_review_priority": "low",
            "review_batch": "03_length_boundary",
            "checkpoint_review_reasons": "length_boundary",
            "checkpoint_status": "pending_checkpoint_1_review",
            "molecule_type": "RNA",
            "chemistry": "RNA",
            "alphabet_as_reported": "RNA",
            "sequence_length_full": canonical["sequence_length_full"],
            "sequence_length_core": canonical["sequence_length_core"],
            "construct_scope": "unknown",
            "trim_status": "no_constants_detected",
            "trim_confidence": "n/a",
            "qc_flags": canonical.get("qc_flags", ""),
        }
    )
    row.update(overrides)
    return row


def _detail(canonical: dict[str, str], decision: dict[str, str]) -> dict[str, str]:
    row = {column: "" for column in LOCAL_DETAIL_COLUMNS}
    row.update(decision)
    row.update(
        {
            "sequence_raw": canonical["sequence_raw"],
            "sequence_full": canonical["sequence_full"],
            "sequence_core": canonical["sequence_core"],
            "publication": "Demo",
            "riboaptamer_sequence_name": f"seq-{canonical['native_id']}",
            "riboaptamer_aptamer_name": f"name-{canonical['native_id']}",
            "riboaptamer_category": "Natural",
            "riboaptamer_type": "Proteins",
            "riboaptamer_article_name": "Demo article",
            "t_to_u_applied": "false",
        }
    )
    return row


def test_unresolved_package_cannot_apply() -> None:
    canonical = _canonical()
    review = _decision(canonical)
    review["manual_decision"] = ""
    with pytest.raises(RiboAptamerCheckpoint1ReviewError, match="remain unresolved"):
        apply_riboaptamer_checkpoint1_package(
            queue_rows=[review],
            group_rows=[],
            canonical_by_id={canonical["record_id"]: canonical},
            source_metadata_by_id={canonical["record_id"]: {"record_id": canonical["record_id"]}},
            s2_qc_by_id={canonical["record_id"]: {"record_id": canonical["record_id"]}},
            policy=POLICY,
        )


def test_validate_blank_review_is_not_ready() -> None:
    canonical = _canonical()
    review = _decision(canonical)
    report = validate_review_package(
        queue_rows=[review],
        group_rows=[],
        bulk_confirmation=None,
    )
    assert report.ok is False
    assert report.unresolved_manual_decisions == 1
    assert report.ready_for_application == 0


def test_prepare_leaves_manual_blank_and_does_not_duplicate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    rec_path = (
        repo
        / "config"
        / "checkpoint_reviews"
        / "riboaptamer_checkpoint1_recommendations.json"
    )
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text(
        (REPO_ROOT / "config" / "checkpoint_reviews" / "riboaptamer_checkpoint1_recommendations.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    checkpoint = repo / "data" / "interim" / "checkpoints" / "riboaptamer_cp1"
    keep = _canonical(native_id="keep", sequence=_rna(22))
    t7 = _canonical(native_id="t7", sequence=_rna(40))
    selb = _canonical(
        native_id="selb",
        sequence="ACGUACGU...ACGU-ACGU1234ACGUACGU",
        qc_flags="alignment_gaps|invalid_character|truncated_sequence",
    )
    d_keep = _decision(keep)
    d_t7 = _decision(
        t7,
        proposed_decision="proposed_accept",
        primary_reason="technically_eligible_rna",
        secondary_reasons="known_motif_proposal",
        review_batch="02_constant_region_proposal",
        checkpoint_review_reasons="constant_region_proposal",
        manual_review_priority="medium",
        constant_proposal_sources="known_motif",
        constant_proposed_trim_length="18",
    )
    d_selb = _decision(
        selb,
        proposed_decision="proposed_reject",
        primary_reason="truncated_sequence",
        secondary_reasons="alignment_gaps|invalid_alphabet",
        primary_route="technical_reject",
        review_batch="01_judgement_dependent_technical",
        checkpoint_review_reasons="judgement_dependent_technical",
        manual_review_priority="high",
        qc_flags=selb["qc_flags"],
    )
    review_rows = [d_keep, d_t7, d_selb]
    details = [
        _detail(keep, d_keep),
        _detail(t7, d_t7),
        _detail(selb, d_selb),
    ]
    _write_csv(checkpoint / "riboaptamer_checkpoint1_review.csv", list(DECISION_COLUMNS), review_rows)
    _write_csv(
        checkpoint / "riboaptamer_checkpoint1_local_detail.csv",
        list(LOCAL_DETAIL_COLUMNS),
        details,
    )
    _write_csv(
        checkpoint / "riboaptamer_s3_canonical.csv",
        list(CORPUS_COLUMNS),
        [keep, t7, selb],
    )
    output = checkpoint / "manual_review"
    result = prepare_riboaptamer_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=output,
        expected_active_rows=3,
        expected_total_rows=3,
    )
    assert result.stats.active_review_rows == 3
    with result.output_queue.open("r", encoding="utf-8", newline="") as handle:
        queue = list(csv.DictReader(handle))
    ids = [row["record_id"] for row in queue]
    assert len(ids) == len(set(ids)) == 3
    by_id = {row["record_id"]: row for row in queue}
    assert by_id["riboaptamer:selb"]["primary_reason"] == "truncated_sequence"
    assert "invalid_alphabet" in by_id["riboaptamer:selb"]["secondary_reasons"]
    assert "judgement_dependent_technical" in by_id["riboaptamer:selb"]["checkpoint_review_reasons"]
    assert by_id["riboaptamer:t7"]["constant_proposal_sources"] == "known_motif"
    for row in queue:
        assert row["manual_decision"] == ""
        assert row["manual_trim_action"] == ""
        assert row["sequence_core"]
    summary = result.output_summary.read_text(encoding="utf-8")
    assert "fail closed" in summary.lower()
    assert "Group-wise constant-region inference was disabled" in summary
    assert "T7" in summary or "t7" in summary.lower()
    validation = result.output_validation.read_text(encoding="utf-8")
    assert "unresolved manual decisions" in validation.lower()

    with pytest.raises(Checkpoint1ApplyError, match="remain unresolved"):
        run_riboaptamer_checkpoint1_apply(
            repo_root=repo,
            checkpoint_dir=checkpoint,
            dry_run=True,
        )


def test_keep_apply_preserves_sequence_raw() -> None:
    canonical = _canonical(native_id="keep")
    review = _decision(canonical)
    review["manual_decision"] = "keep"
    review["checkpoint_review_reasons"] = "length_boundary"
    review["secondary_reasons"] = "lower_length_boundary"
    applied, report = apply_riboaptamer_checkpoint1_package(
        queue_rows=[review],
        group_rows=[],
        canonical_by_id={canonical["record_id"]: canonical},
        source_metadata_by_id={
            canonical["record_id"]: {
                "record_id": canonical["record_id"],
                "riboaptamer_type": "Proteins",
                "riboaptamer_aptamer_name": "name-keep",
            }
        },
        s2_qc_by_id={
            canonical["record_id"]: {
                "record_id": canonical["record_id"],
                "native_id": "keep",
                "qc_flags": "",
            }
        },
        policy=POLICY,
        bulk_confirmation={"confirm": "true", "eligible_record_ids": canonical["record_id"]},
    )
    assert report.ok is True
    assert applied[0].sequence_raw == canonical["sequence_raw"]
    for field_name in S3_FORBIDDEN_FIELDS:
        assert applied[0].canonical.get(field_name, "") == ""

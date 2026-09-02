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
    CP1_FLAG_STRONG,
    CP1_FLAG_WEAK,
    QC_FLAG_STRONG,
    QC_FLAG_WEAK,
    RiboAptamerCheckpoint1ReviewError,
    apply_riboaptamer_checkpoint1_package,
    decode_mixed_utf8_macroman_bytes,
    normalise_riboaptamer_trim_action,
    parse_cp1_constant_flag,
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


def _meta(canonical: dict[str, str]) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "riboaptamer_type": "Proteins",
        "riboaptamer_aptamer_name": f"name-{canonical['native_id']}",
        "riboaptamer_sequence_name": f"seq-{canonical['native_id']}",
        "riboaptamer_category": "Mammalian",
    }


def _qc(canonical: dict[str, str]) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "qc_flags": canonical.get("qc_flags", ""),
    }


def test_trim_synonym_maps_to_approve() -> None:
    assert normalise_riboaptamer_trim_action("trim") == "approve"
    assert normalise_riboaptamer_trim_action("approve") == "approve"
    assert normalise_riboaptamer_trim_action("") == ""


def test_cp1_flag_parsing_does_not_use_hardcoded_ids() -> None:
    assert parse_cp1_constant_flag(
        f"{CP1_FLAG_STRONG} — keep sequence unchanged"
    ) == QC_FLAG_STRONG
    assert parse_cp1_constant_flag(
        f"{CP1_FLAG_WEAK} — possible scaffold"
    ) == QC_FLAG_WEAK
    assert parse_cp1_constant_flag("ordinary keep note") == ""


def test_macroman_emdash_roundtrip_does_not_change_decisions() -> None:
    text = "manual_decision,manual_notes\nkeep,CP1_FLAG:constants_suspected_unresolved — keep\n"
    mixed = text.replace("—", "\u00d1").encode("latin-1")
    decoded = decode_mixed_utf8_macroman_bytes(mixed)
    assert "—" in decoded
    assert "Ñ" not in decoded
    assert "keep" in decoded


def test_completed_review_with_keep_drop_edit_validates() -> None:
    keep = _canonical(native_id="keep", sequence=_rna(22))
    drop = _canonical(native_id="drop", sequence=_rna(22))
    t7_full = "G" * 17 + _rna(40)
    t7 = _canonical(native_id="t7", sequence=t7_full)
    r_keep = _decision(keep)
    r_keep["manual_decision"] = "keep"
    r_drop = _decision(
        drop,
        proposed_decision="proposed_reject",
        primary_reason="truncated_sequence",
        primary_route="technical_reject",
        checkpoint_review_reasons="judgement_dependent_technical",
        audit_only_row="FALSE",
        bulk_audit_eligible="FALSE",
    )
    r_drop["manual_decision"] = "drop"
    r_t7 = _decision(
        t7,
        review_batch="02_constant_region_proposal",
        checkpoint_review_reasons="constant_region_proposal",
        constant_proposal_sources="known_motif",
        constant_proposal_sides="five_prime",
        constant_proposed_trim_length="17",
        audit_only_row="FALSE",
        bulk_audit_eligible="FALSE",
    )
    r_t7["manual_decision"] = "edit"
    r_t7["manual_trim_action"] = "trim"
    r_t7["manual_notes"] = "known T7 promoter"
    from adapters.riboaptamer_checkpoint1_review import (
        normalise_riboaptamer_review_rows,
    )

    rows = normalise_riboaptamer_review_rows([r_keep, r_drop, r_t7])
    report = validate_review_package(
        queue_rows=rows, group_rows=[], bulk_confirmation=None
    )
    assert report.ok is True
    assert report.unresolved_manual_decisions == 0
    assert report.drop_records == 1
    assert report.blocking_issues == []
    assert rows[2]["manual_trim_action"] == "approve"


def test_selb_drop_does_not_invent_sequence() -> None:
    selb = _canonical(
        native_id="169",
        sequence="ACGUACGU...ACGU",
        qc_flags="alignment_gaps|invalid_character|truncated_sequence",
        notes='{"category_prior":"Bacteria"}',
    )
    review = _decision(
        selb,
        proposed_decision="proposed_reject",
        primary_reason="truncated_sequence",
        primary_route="technical_reject",
        checkpoint_review_reasons="judgement_dependent_technical",
        audit_only_row="FALSE",
    )
    review["manual_decision"] = "drop"
    applied, report = apply_riboaptamer_checkpoint1_package(
        queue_rows=[review],
        group_rows=[],
        canonical_by_id={selb["record_id"]: selb},
        source_metadata_by_id={selb["record_id"]: _meta(selb)},
        s2_qc_by_id={selb["record_id"]: _qc(selb)},
        policy=POLICY,
    )
    assert report.ok is True
    assert applied[0].sequence_core == selb["sequence_core"]
    assert applied[0].sequence_raw == selb["sequence_raw"]
    assert "..." in applied[0].sequence_core
    assert '{"category_prior":"Bacteria"}' in applied[0].notes
    assert "checkpoint1_manual_decision=drop" in applied[0].notes
    assert applied[0].canonical.get("manual_sequence_corrected", "") == ""


def test_t7_approval_trims_17nt_from_5p_and_keeps_raw_full() -> None:
    full = ("A" * 17) + _rna(79)
    canonical = _canonical(
        native_id="382",
        sequence=full,
        trim_status="constants_suspected_unresolved",
        qc_flags="constants_suspected_unresolved|known_promoter_detected|trim_requires_review",
        detected_constant_5p="t7_promoter_minimal",
        notes='{"category_prior":"Mammalian"}',
    )
    review = _decision(
        canonical,
        review_batch="02_constant_region_proposal",
        checkpoint_review_reasons="constant_region_proposal",
        constant_proposal_sources="known_motif",
        constant_proposal_sides="five_prime",
        constant_proposed_trim_length="17",
        audit_only_row="FALSE",
    )
    review["manual_decision"] = "edit"
    review["manual_trim_action"] = "trim"
    review["manual_notes"] = "known T7 promoter, at the terminus"
    proposals = [
        {
            "proposal_id": "riboaptamer:382:known_motif:five_prime:t7_promoter_minimal",
            "experiment_group_id": "riboaptamer:382",
            "proposal_source": "known_motif",
            "side": "five_prime",
            "motif_id": "t7_promoter_minimal",
            "motif_length": "17",
        }
    ]
    applied, report = apply_riboaptamer_checkpoint1_package(
        queue_rows=[review],
        group_rows=[],
        canonical_by_id={canonical["record_id"]: canonical},
        source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
        s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
        policy=POLICY,
        proposals_by_record={canonical["record_id"]: proposals},
    )
    assert report.ok is True
    item = applied[0]
    assert item.sequence_raw == full
    assert item.sequence_full == full
    assert item.sequence_core == _rna(79)
    assert item.sequence_length_core == 79
    assert 20 <= item.sequence_length_core <= 100
    assert item.applied_trim_5p_nt == 17
    assert item.applied_trim_3p_nt == 0
    assert item.trim_status == "t7_removed"
    assert item.trim_confidence == "high"
    assert item.primary_route_after == "technically_eligible"
    assert item.canonical["detected_constant_5p"] == "t7_promoter_minimal"
    assert "trim_requires_review" not in item.canonical["qc_flags"]
    assert '{"category_prior":"Mammalian"}' in item.notes
    assert "checkpoint1_reviewer_notes=" in item.notes
    for field_name in S3_FORBIDDEN_FIELDS:
        assert item.canonical.get(field_name, "") == ""

    again, _ = apply_riboaptamer_checkpoint1_package(
        queue_rows=[review],
        group_rows=[],
        canonical_by_id={canonical["record_id"]: canonical},
        source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
        s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
        policy=POLICY,
        proposals_by_record={canonical["record_id"]: proposals},
    )
    assert again[0].sequence_core == item.sequence_core
    assert again[0].sequence_length_core == 79
    assert again[0].notes == item.notes


def test_strong_flag_preserved_without_sequence_or_trim_change() -> None:
    canonical = _canonical(
        native_id="007",
        sequence=_rna(40),
        notes='{"category_prior":"Viral"}',
    )
    review = _decision(canonical)
    review["manual_decision"] = "keep"
    review["manual_notes"] = (
        f"{CP1_FLAG_STRONG} — keep sequence unchanged; strong shared terminals"
    )
    applied, _ = apply_riboaptamer_checkpoint1_package(
        queue_rows=[review],
        group_rows=[],
        canonical_by_id={canonical["record_id"]: canonical},
        source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
        s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
        policy=POLICY,
        bulk_confirmation={"confirm": "true", "eligible_record_ids": canonical["record_id"]},
    )
    item = applied[0]
    assert item.sequence_raw == canonical["sequence_raw"]
    assert item.sequence_core == canonical["sequence_core"]
    assert item.applied_trim_5p_nt == 0
    assert item.applied_trim_3p_nt == 0
    assert item.trim_status == QC_FLAG_STRONG
    assert item.trim_confidence == "n/a"
    assert QC_FLAG_STRONG in item.canonical["qc_flags"]
    assert QC_FLAG_WEAK not in item.canonical["qc_flags"]
    assert "checkpoint1_constant_flag=constants_suspected_unresolved" in item.notes
    assert CP1_FLAG_STRONG in item.notes
    assert '{"category_prior":"Viral"}' in item.notes


def test_weak_flag_distinct_from_strong_and_does_not_change_trim_status() -> None:
    canonical = _canonical(
        native_id="138",
        sequence=_rna(40),
        notes='{"category_prior":"Other"}',
    )
    review = _decision(canonical)
    review["manual_decision"] = "keep"
    review["manual_notes"] = (
        f"{CP1_FLAG_WEAK} — keep sequence unchanged; possible construct"
    )
    applied, _ = apply_riboaptamer_checkpoint1_package(
        queue_rows=[review],
        group_rows=[],
        canonical_by_id={canonical["record_id"]: canonical},
        source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
        s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
        policy=POLICY,
        bulk_confirmation={"confirm": "true", "eligible_record_ids": canonical["record_id"]},
    )
    item = applied[0]
    assert item.sequence_core == canonical["sequence_core"]
    assert item.trim_status == "no_constants_detected"
    assert item.trim_status != QC_FLAG_STRONG
    assert QC_FLAG_WEAK in item.canonical["qc_flags"]
    assert QC_FLAG_STRONG not in item.canonical["qc_flags"]
    assert "checkpoint1_constant_flag=possible_constants_unresolved" in item.notes


def test_ordinary_audit_keep_unchanged_except_review_notes() -> None:
    canonical = _canonical(
        native_id="011",
        sequence=_rna(40),
        notes='{"category_prior":"Mammalian"}',
    )
    review = _decision(canonical)
    review["manual_decision"] = "keep"
    applied, _ = apply_riboaptamer_checkpoint1_package(
        queue_rows=[review],
        group_rows=[],
        canonical_by_id={canonical["record_id"]: canonical},
        source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
        s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
        policy=POLICY,
        bulk_confirmation={"confirm": "true", "eligible_record_ids": canonical["record_id"]},
    )
    item = applied[0]
    assert item.sequence_core == canonical["sequence_core"]
    assert item.trim_status == "no_constants_detected"
    assert item.canonical["qc_flags"] == canonical["qc_flags"]
    assert QC_FLAG_STRONG not in item.canonical["qc_flags"]
    assert QC_FLAG_WEAK not in item.canonical["qc_flags"]
    assert "checkpoint1_manual_decision=keep" in item.notes
    assert '{"category_prior":"Mammalian"}' in item.notes


def test_no_target_routing_evidence_or_leakage_on_apply() -> None:
    canonical = _canonical(native_id="type", sequence=_rna(40))
    review = _decision(canonical)
    review["manual_decision"] = "keep"
    meta = _meta(canonical)
    meta["riboaptamer_type"] = "Small molecules"
    applied, _ = apply_riboaptamer_checkpoint1_package(
        queue_rows=[review],
        group_rows=[],
        canonical_by_id={canonical["record_id"]: canonical},
        source_metadata_by_id={canonical["record_id"]: meta},
        s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
        policy=POLICY,
        bulk_confirmation={"confirm": "true", "eligible_record_ids": canonical["record_id"]},
    )
    item = applied[0]
    assert item.primary_route_after == "technically_eligible"
    assert item.canonical["target_type"] == ""
    assert item.canonical["binding_evidence_score"] == ""
    assert item.canonical["target_uniprot"] == ""
    assert "non_protein" not in item.primary_route_after
    assert item.canonical.get("sequence_leakage_match", "") == ""


def test_simulation_reconciles_all_records_and_consumes_every_decision() -> None:
    from adapters.riboaptamer_checkpoint1_dry_run import (
        simulate_riboaptamer_checkpoint1_application,
    )

    keep = _canonical(native_id="keep", sequence=_rna(40))
    drop = _canonical(
        native_id="drop",
        sequence="ACGU...",
        qc_flags="truncated_sequence|invalid_character",
    )
    t7_full = ("U" * 17) + _rna(40)
    t7 = _canonical(native_id="t7", sequence=t7_full)
    extra = _canonical(native_id="extra", sequence=_rna(30))
    d_keep = _decision(keep)
    d_keep["manual_decision"] = "keep"
    d_keep["manual_notes"] = f"{CP1_FLAG_STRONG} — unresolved constants"
    d_drop = _decision(
        drop,
        proposed_decision="proposed_reject",
        primary_reason="truncated_sequence",
        primary_route="technical_reject",
        checkpoint_review_reasons="judgement_dependent_technical",
        audit_only_row="FALSE",
    )
    d_drop["manual_decision"] = "drop"
    d_t7 = _decision(
        t7,
        checkpoint_review_reasons="constant_region_proposal",
        constant_proposal_sources="known_motif",
        constant_proposal_sides="five_prime",
        constant_proposed_trim_length="17",
        audit_only_row="FALSE",
    )
    d_t7["manual_decision"] = "edit"
    d_t7["manual_trim_action"] = "approve"
    d_extra = _decision(
        extra,
        proposed_decision="proposed_reject",
        primary_reason="length_out_of_range",
        primary_route="technical_reject",
        manual_review_required="false",
        checkpoint_review_reasons="",
        review_batch="",
    )
    decisions = [
        {**d_keep, "primary_route": "technically_eligible"},
        {**d_drop, "primary_route": "technical_reject"},
        {**d_t7, "primary_route": "technically_eligible"},
        {**d_extra, "primary_route": "technical_reject", "manual_decision": ""},
    ]
    rejections = [
        {
            "record_id": drop["record_id"],
            "source_db": "riboaptamer",
            "source_dataset": "riboaptamer_full_2026-08",
            "native_id": "drop",
            "sequence_raw": drop["sequence_raw"],
            "target_name_raw": "",
            "stage": "S3",
            "rejection_reason": "truncated_sequence",
            "rejection_detail": "",
        },
        {
            "record_id": extra["record_id"],
            "source_db": "riboaptamer",
            "source_dataset": "riboaptamer_full_2026-08",
            "native_id": "extra",
            "sequence_raw": extra["sequence_raw"],
            "target_name_raw": "",
            "stage": "S3",
            "rejection_reason": "length_out_of_range",
            "rejection_detail": "",
        },
    ]
    simulation = simulate_riboaptamer_checkpoint1_application(
        queue_rows=[d_keep, d_drop, d_t7],
        group_rows=[],
        canonical_rows=[keep, drop, t7, extra],
        decision_rows=decisions,
        source_metadata_by_id={
            row["record_id"]: _meta(row) for row in (keep, drop, t7, extra)
        },
        s2_qc_by_id={row["record_id"]: _qc(row) for row in (keep, drop, t7, extra)},
        policy=POLICY,
        existing_rejection_rows=rejections,
        expected_source_rows=4,
    )
    assert simulation.stats["total_records"] == 4
    assert simulation.stats["decisions_consumed"] == 3
    assert simulation.stats["unconsumed_decisions"] == 0
    assert simulation.stats["human_reviewed_drops"] == 1
    assert simulation.stats["approved_known_t7_trims"] == 1
    assert simulation.stats["strong_unresolved_constant_flags"] == 1
    assert simulation.stats["group_consensus_proposals"] == 0
    assert simulation.stats["parked_ssdna"] == 0
    assert simulation.stats["parked_non_protein"] == 0
    assert (
        int(simulation.stats["technical_rejects_after_review"])
        + int(simulation.stats["parked_ssdna"])
        + int(simulation.stats["technically_eligible"])
        == 4
    )
    ids = [row["record_id"] for row in simulation.preview_canonical]
    assert ids == [keep["record_id"], drop["record_id"], t7["record_id"], extra["record_id"]]
    assert all(row["consumed"] == "true" for row in simulation.decision_audit)
    from adapters.riboaptamer_checkpoint1_dry_run import (
        serialise_riboaptamer_simulation,
    )

    second = simulate_riboaptamer_checkpoint1_application(
        queue_rows=[d_keep, d_drop, d_t7],
        group_rows=[],
        canonical_rows=[keep, drop, t7, extra],
        decision_rows=decisions,
        source_metadata_by_id={
            row["record_id"]: _meta(row) for row in (keep, drop, t7, extra)
        },
        s2_qc_by_id={row["record_id"]: _qc(row) for row in (keep, drop, t7, extra)},
        policy=POLICY,
        existing_rejection_rows=rejections,
        expected_source_rows=4,
    )
    assert serialise_riboaptamer_simulation(simulation) == serialise_riboaptamer_simulation(
        second
    )


@pytest.mark.skipif(
    not (
        REPO_ROOT
        / "data/interim/checkpoints/riboaptamer_cp1/manual_review"
        / "riboaptamer_checkpoint1_manual_review.csv"
    ).is_file(),
    reason="RiboAptamer CHECKPOINT-1 review CSV not present locally",
)
def test_real_completed_85_row_review_validates_without_embedding_sequences() -> None:
    from adapters.riboaptamer_checkpoint1_review import (
        normalise_riboaptamer_review_rows,
        read_riboaptamer_review_csv,
    )

    path = (
        REPO_ROOT
        / "data/interim/checkpoints/riboaptamer_cp1/manual_review"
        / "riboaptamer_checkpoint1_manual_review.csv"
    )
    rows = normalise_riboaptamer_review_rows(read_riboaptamer_review_csv(path))
    group_path = path.parent / "riboaptamer_checkpoint1_constant_group_review.csv"
    bulk_path = path.parent / "riboaptamer_checkpoint1_bulk_audit_confirmation.csv"
    import csv as _csv

    group_rows = list(_csv.DictReader(group_path.read_text(encoding="utf-8").splitlines()))
    bulk_rows = list(_csv.DictReader(bulk_path.read_text(encoding="utf-8").splitlines()))
    report = validate_review_package(
        queue_rows=rows,
        group_rows=group_rows,
        bulk_confirmation=bulk_rows[0] if bulk_rows else None,
    )
    assert len(rows) == 85
    assert report.unresolved_manual_decisions == 0
    assert report.unresolved_exceptions == 0
    assert report.audit_only_unconfirmed == 0
    assert report.blocking_issues == []
    assert report.ok is True
    assert report.ready_for_application == 85
    assert {row["manual_decision"] for row in rows} <= {"keep", "drop", "edit"}
    assert sum(1 for row in rows if row["manual_decision"] == "drop") == 1
    assert sum(1 for row in rows if row["manual_decision"] == "edit") == 1
    strong = [
        row["record_id"]
        for row in rows
        if parse_cp1_constant_flag(row.get("manual_notes", "")) == QC_FLAG_STRONG
    ]
    weak = [
        row["record_id"]
        for row in rows
        if parse_cp1_constant_flag(row.get("manual_notes", "")) == QC_FLAG_WEAK
    ]
    assert len(strong) == 35
    assert len(weak) == 3
    t7 = next(row for row in rows if row["record_id"] == "riboaptamer:382")
    assert t7["manual_trim_action"] == "approve"
    assert t7.get("manual_sequence_corrected", "") == ""
    selb = next(row for row in rows if row["record_id"] == "riboaptamer:169")
    assert selb["manual_decision"] == "drop"
    assert selb.get("manual_sequence_corrected", "") == ""
    chem = next(row for row in rows if row["record_id"] == "riboaptamer:157")
    assert chem.get("manual_chemistry_override", "") == ""


@pytest.mark.skipif(
    not (
        REPO_ROOT
        / "data/interim/checkpoints/riboaptamer_cp1/resolved"
        / "riboaptamer_checkpoint1_applied_canonical.csv"
    ).is_file(),
    reason="RiboAptamer CHECKPOINT-1 applied canonical not present locally",
)
def test_real_applied_outputs_reconcile_509_without_embedding_sequences() -> None:
    applied_dir = (
        REPO_ROOT / "data/interim/checkpoints/riboaptamer_cp1/resolved"
    )
    canonical = list(
        csv.DictReader(
            (applied_dir / "riboaptamer_checkpoint1_applied_canonical.csv").open(
                encoding="utf-8"
            )
        )
    )
    routing = list(
        csv.DictReader(
            (applied_dir / "riboaptamer_checkpoint1_applied_routing.csv").open(
                encoding="utf-8"
            )
        )
    )
    rejection = list(
        csv.DictReader(
            (applied_dir / "riboaptamer_checkpoint1_applied_rejection.csv").open(
                encoding="utf-8"
            )
        )
    )
    authorised = list(
        csv.DictReader(
            (applied_dir / "riboaptamer_checkpoint1_s4_authorised_ids.csv").open(
                encoding="utf-8"
            )
        )
    )
    audit = list(
        csv.DictReader(
            (applied_dir / "riboaptamer_checkpoint1_decision_audit.csv").open(
                encoding="utf-8"
            )
        )
    )
    parked = list(
        csv.DictReader(
            (applied_dir / "riboaptamer_checkpoint1_applied_parked_ssdna.csv").open(
                encoding="utf-8"
            )
        )
    )
    assert len(canonical) == 509
    assert len(routing) == 509
    assert len({row["record_id"] for row in canonical}) == 509
    eligible = [
        row for row in routing if row["primary_route"] == "technically_eligible"
    ]
    rejected = [
        row for row in routing if row["primary_route"] == "technical_reject"
    ]
    parked_routes = [row for row in routing if "park" in row["primary_route"]]
    assert len(eligible) == 397
    assert len(rejected) == 112
    assert parked_routes == []
    assert parked == []
    assert len(eligible) + len(rejected) + len(parked_routes) == 509
    assert len(authorised) == 397
    assert {row["record_id"] for row in authorised} == {
        row["record_id"] for row in eligible
    }
    assert "riboaptamer:169" not in {row["record_id"] for row in authorised}
    assert any(row["record_id"] == "riboaptamer:169" for row in rejection)
    t7 = next(row for row in canonical if row["record_id"] == "riboaptamer:382")
    t7_route = next(row for row in routing if row["record_id"] == "riboaptamer:382")
    assert t7["trim_status"] == "t7_removed"
    assert t7["sequence_length_core"] == "79"
    assert t7["trim_confidence"] == "high"
    assert t7_route["primary_route"] == "technically_eligible"
    assert "checkpoint1_reviewer_notes=" in t7["notes"]
    strong = [row for row in canonical if row["trim_status"] == QC_FLAG_STRONG]
    weak = [
        row
        for row in canonical
        if QC_FLAG_WEAK in row.get("qc_flags", "").split("|")
    ]
    assert len(strong) == 35
    assert len(weak) == 3
    assert all(row["trim_status"] == "no_constants_detected" for row in weak)
    assert all(row["consumed"] == "true" for row in audit)
    assert len(audit) == 85
    chem = next(row for row in canonical if row["record_id"] == "riboaptamer:157")
    assert chem["chemistry"] == "RNA"
    for row in canonical:
        assert row.get("target_name", "") == ""
        assert row.get("binding_evidence_score", "") == ""
        assert row.get("target_uniprot", "") == ""


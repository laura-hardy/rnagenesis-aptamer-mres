"""Structured AptaDB CHECKPOINT-1 review/apply tests (synthetic sequences only).

Literal nucleotides are either short fixtures or repeating ACGU/ACGT tiles.
Does not read real AptaDB source sequences.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadb_checkpoint1_review import (  # noqa: E402
    AptaDBCheckpoint1ReviewError,
    LARGE_TRIM_HUMAN_APPROVED_FLAG,
    apply_aptadb_checkpoint1_package,
    apply_numeric_terminal_trim,
    apply_reviewed_record,
    apply_sequence_correction_op,
    is_audit_only_row,
    load_review_recommendations,
    materialize_bulk_audit_decisions,
    populate_record_recommendations,
    resolve_effective_trim,
    validate_review_package,
)
from adapters.aptadb_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    LOCAL_DETAIL_COLUMNS,
    REJECTION_COLUMNS,
)
from checkpoint1_prepare_review import (  # noqa: E402
    APTADB_MANUAL_REVIEW_COLUMNS,
    prepare_aptadb_checkpoint1_review,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import load_eligibility_policy  # noqa: E402

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "aptadb.json"
)
RECS = load_review_recommendations(
    REPO_ROOT / "config" / "checkpoint_reviews" / "aptadb_checkpoint1_recommendations.json"
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _dna(n: int) -> str:
    return ("ACGT" * ((n // 4) + 1))[:n]


def _canonical(
    *,
    native_id: str = "1",
    sequence: str = "",
    molecule_type: str = "RNA",
    chemistry: str = "RNA",
    alphabet: str = "RNA",
    qc_flags: str = "",
    **overrides: str,
) -> dict[str, str]:
    sequence = sequence or _rna(40)
    record = empty_corpus_record()
    length = str(len(sequence))
    record.update(
        {
            "record_id": f"aptadb:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": "no_constants_detected",
            "trim_confidence": "n/a",
            "molecule_type": molecule_type,
            "alphabet_as_reported": alphabet,
            "t_to_u_applied": "false",
            "chemistry": chemistry,
            "target_name_raw": "demo_protein",
            "source_db": "aptadb",
            "source_dataset": "aptadb_official_export_2026-08",
            "contributing_sources": "aptadb",
            "contributing_datasets": "aptadb_official_export_2026-08",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "qc_flags": qc_flags,
        }
    )
    record.update(overrides)
    return record


def _qc(canonical: dict[str, str]) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical["chemistry"],
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "t_to_u_applied": canonical["t_to_u_applied"],
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical["trim_confidence"],
        "qc_flags": canonical["qc_flags"],
        "construct_scope": canonical["construct_scope"],
    }


def _meta(canonical: dict[str, str], *, target_chemistry: str = "Protein") -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "aptadb_target_chemistry": target_chemistry,
        "aptadb_aptamer_chemistry": (
            "RNA" if canonical["molecule_type"] == "RNA" else "DNA"
        ),
    }


def _review(
    canonical: dict[str, str],
    *,
    decision: str = "edit",
    route: str = PRIMARY_ROUTE_ELIGIBLE,
    **overrides: str,
) -> dict[str, str]:
    row = {
        "record_id": canonical["record_id"],
        "primary_route": route,
        "checkpoint_review_reasons": "",
        "constant_group_id": "",
        "constant_proposal_sources": "",
        "manual_decision": decision,
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
    row.update(overrides)
    return row


def test_recommendations_never_populate_manual_fields() -> None:
    row = {
        "record_id": "aptadb:230",
        "sequence_raw": "ACGT-ACGT-ACGTACGTACGTACGTACGTACGTACGTACGT",
        "checkpoint_review_reasons": "judgement_dependent_technical",
        "constant_group_id": "",
    }
    for name in (
        "manual_decision",
        "manual_sequence_corrected",
        "manual_molecule_type_override",
        "manual_trim_action",
        "manual_notes",
    ):
        row[name] = ""
    filled = populate_record_recommendations(row, recommendations=RECS)
    assert filled["manual_decision"] == ""
    assert filled["manual_sequence_corrected"] == ""
    assert filled["manual_trim_action"] == ""
    assert filled["review_recommendation"] == "edit_remove_internal_hyphens"
    assert filled["recommended_manual_decision"] == "edit"
    assert "-" not in filled["recommended_sequence_corrected"]
    assert filled["requires_specific_human_decision"] == "true"


def test_molecule_override_reruns_shared_normaliser() -> None:
    original = _dna(40)
    canonical = _canonical(
        native_id="9",
        sequence=original,
        molecule_type="ssDNA",
        chemistry="DNA",
        alphabet="DNA_T",
    )
    review = _review(
        canonical,
        route=PRIMARY_ROUTE_SSDNA,
        manual_molecule_type_override="RNA",
        manual_chemistry_override="RNA",
    )
    result = apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
    )
    assert result.sequence_raw == original
    assert result.molecule_type == "RNA"
    assert result.chemistry == "RNA"
    assert result.alphabet_as_reported == "DNA_T"
    assert result.t_to_u_applied is True
    assert "T" not in result.sequence_full
    assert "U" in result.sequence_full
    assert result.primary_route_before == PRIMARY_ROUTE_SSDNA
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    for field_name in S3_FORBIDDEN_FIELDS:
        assert result.canonical[field_name] == ""


def test_sequence_correction_preserves_raw_and_revalidates() -> None:
    original = _dna(20) + "-" + _dna(19)
    canonical = _canonical(
        native_id="230",
        sequence=original,
        molecule_type="ssDNA",
        chemistry="DNA",
        alphabet="DNA_T",
        qc_flags="alignment_gaps",
    )
    review = _review(
        canonical,
        route=PRIMARY_ROUTE_REJECT,
        manual_sequence_corrected=apply_sequence_correction_op(
            original, "remove_internal_hyphens"
        ),
    )
    result = apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
    )
    assert result.sequence_raw == original
    assert "-" not in result.sequence_full
    assert result.primary_route_after == PRIMARY_ROUTE_SSDNA
    assert "manual_sequence_correction_applied" in result.notes


def test_trim_approve_uses_machine_boundaries() -> None:
    sequence = _rna(40)
    canonical = _canonical(sequence=sequence)
    review = _review(canonical, manual_trim_action="approve")
    result = apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        machine_five=5,
        machine_three=5,
    )
    assert result.sequence_core == sequence[5:-5]
    assert result.sequence_length_core == 30
    assert result.trim_confidence == "medium"
    assert result.trim_status == "primers_removed"
    assert result.sequence_raw == sequence


def test_trim_override_uses_human_numeric_boundaries() -> None:
    sequence = _rna(40)
    canonical = _canonical(sequence=sequence)
    review = _review(
        canonical,
        manual_trim_action="override",
        manual_trim_5p_nt="3",
        manual_trim_3p_nt="4",
    )
    result = apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        machine_five=5,
        machine_three=5,
    )
    assert result.sequence_core == sequence[3:-4]
    assert "applied_5p=3" in result.notes
    assert "applied_3p=4" in result.notes


def test_trim_reject_leaves_core_unchanged() -> None:
    sequence = _rna(40)
    canonical = _canonical(sequence=sequence)
    review = _review(canonical, manual_trim_action="reject")
    result = apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        machine_five=5,
        machine_three=5,
    )
    assert result.sequence_core == sequence
    assert result.trim_confidence == "n/a"


def test_trim_defer_cannot_apply_or_close() -> None:
    sequence = _rna(40)
    canonical = _canonical(sequence=sequence)
    review = _review(canonical, manual_trim_action="defer")
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="Deferred trim"):
        apply_reviewed_record(
            canonical=canonical,
            review_row=review,
            source_metadata=_meta(canonical),
            s2_qc=_qc(canonical),
            policy=POLICY,
        )
    report = validate_review_package(
        queue_rows=[review],
        group_rows=[],
    )
    assert report.ok is False
    assert report.deferred_records == 1


def test_group_propagation_and_record_exception() -> None:
    group = {
        "constant_group_id": "group-a",
        "manual_trim_action": "approve",
        "manual_trim_5p_nt": "",
        "manual_trim_3p_nt": "",
        "machine_trim_5p_nt": "5",
        "machine_trim_3p_nt": "5",
    }
    member = _review(
        _canonical(native_id="10"),
        manual_decision="keep",
        constant_group_id="group-a",
    )
    exception = _review(
        _canonical(native_id="11"),
        manual_decision="edit",
        constant_group_id="group-a",
        manual_trim_action="override",
        manual_trim_3p_nt="0",
        manual_trim_group_override="true",
    )
    member_trim = resolve_effective_trim(
        member, group, machine_five=5, machine_three=5
    )
    exception_trim = resolve_effective_trim(
        exception, group, machine_five=5, machine_three=5
    )
    assert member_trim is not None
    assert member_trim.five_nt == 5
    assert member_trim.three_nt == 5
    assert member_trim.source == "group"
    assert exception_trim is not None
    assert exception_trim.five_nt == 5
    assert exception_trim.three_nt == 0
    assert exception_trim.source == "record"


def test_trim_guard_rails() -> None:
    sequence = _rna(40)
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="below 20"):
        apply_numeric_terminal_trim(
            sequence, five_nt=15, three_nt=6, record_id="aptadb:x"
        )
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="exceeds sequence length"):
        apply_numeric_terminal_trim(
            sequence, five_nt=50, three_nt=0, record_id="aptadb:x"
        )
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="empty core"):
        apply_numeric_terminal_trim(
            sequence, five_nt=20, three_nt=20, record_id="aptadb:x"
        )
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="non-negative integer"):
        from adapters.aptadb_checkpoint1_review import parse_trim_nt

        parse_trim_nt("-1", field_name="manual_trim_5p_nt", record_id="aptadb:x")
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="review guard rail"):
        apply_numeric_terminal_trim(
            sequence, five_nt=10, three_nt=10, record_id="aptadb:x"
        )


def test_machine_only_trim_within_40_percent_may_proceed() -> None:
    sequence = _rna(40)
    core = apply_numeric_terminal_trim(
        sequence, five_nt=5, three_nt=5, record_id="aptadb:x"
    )
    assert core == sequence[5:-5]


def test_machine_only_trim_over_40_percent_blocked() -> None:
    sequence = _rna(40)
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="review guard rail"):
        apply_numeric_terminal_trim(
            sequence,
            five_nt=10,
            three_nt=10,
            record_id="aptadb:x",
            human_authorised=False,
        )


def test_recommendation_only_trim_over_40_percent_not_applied() -> None:
    sequence = _rna(40)
    canonical = _canonical(sequence=sequence)
    review = _review(
        canonical,
        decision="keep",
        recommended_trim_action="approve",
        recommended_trim_5p_nt="10",
        recommended_trim_3p_nt="10",
    )
    result = apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        machine_five=10,
        machine_three=10,
    )
    assert result.sequence_core == sequence
    assert result.applied_trim_5p_nt == 0
    assert result.applied_trim_3p_nt == 0
    assert result.large_trim_human_approved is False
    assert LARGE_TRIM_HUMAN_APPROVED_FLAG not in result.canonical["qc_flags"]


def test_bulk_keep_without_trim_action_does_not_authorise_large_trim() -> None:
    sequence = _rna(40)
    canonical = _canonical(sequence=sequence)
    review = _review(canonical, decision="keep")
    result = apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        machine_five=10,
        machine_three=10,
    )
    assert result.sequence_core == sequence
    assert result.applied_trim_5p_nt == 0


def test_explicit_human_group_approve_over_40_percent_allowed() -> None:
    sequence = _rna(40)
    canonical = _canonical(sequence=sequence)
    group = {
        "constant_group_id": "group-wide",
        "manual_trim_action": "approve",
        "manual_trim_5p_nt": "",
        "manual_trim_3p_nt": "",
        "machine_trim_5p_nt": "10",
        "machine_trim_3p_nt": "10",
    }
    review = _review(
        canonical, decision="keep", constant_group_id="group-wide"
    )
    result = apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        group_row=group,
        machine_five=10,
        machine_three=10,
    )
    assert result.sequence_core == sequence[10:-10]
    assert result.sequence_length_core == 20
    assert result.large_trim_human_approved is True
    assert LARGE_TRIM_HUMAN_APPROVED_FLAG in result.canonical["qc_flags"]
    assert LARGE_TRIM_HUMAN_APPROVED_FLAG in result.notes
    assert "trim_pct=50.00" in result.notes
    assert "authorisation=CHECKPOINT-1" in result.notes
    assert "human_trim_action=approve" in result.notes
    assert result.trim_source == "group"


def test_explicit_human_group_override_over_40_percent_allowed() -> None:
    sequence = _rna(40)
    canonical = _canonical(sequence=sequence)
    group = {
        "constant_group_id": "group-wide",
        "manual_trim_action": "override",
        "manual_trim_5p_nt": "10",
        "manual_trim_3p_nt": "10",
        "machine_trim_5p_nt": "5",
        "machine_trim_3p_nt": "5",
    }
    review = _review(
        canonical, decision="keep", constant_group_id="group-wide"
    )
    result = apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        group_row=group,
        machine_five=5,
        machine_three=5,
    )
    assert result.sequence_length_core == 20
    assert result.applied_trim_5p_nt == 10
    assert result.applied_trim_3p_nt == 10
    assert result.large_trim_human_approved is True
    assert result.trim_source == "group"
    assert "human_trim_action=override" in result.notes


def test_explicit_human_record_override_over_40_percent_allowed() -> None:
    sequence = _rna(40)
    canonical = _canonical(sequence=sequence)
    group = {
        "constant_group_id": "group-wide",
        "manual_trim_action": "approve",
        "manual_trim_5p_nt": "",
        "manual_trim_3p_nt": "",
        "machine_trim_5p_nt": "5",
        "machine_trim_3p_nt": "5",
    }
    review = _review(
        canonical,
        decision="edit",
        constant_group_id="group-wide",
        manual_trim_action="override",
        manual_trim_5p_nt="10",
        manual_trim_3p_nt="10",
        manual_trim_group_override="true",
    )
    result = apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        group_row=group,
        machine_five=5,
        machine_three=5,
    )
    assert result.sequence_length_core == 20
    assert result.applied_trim_5p_nt == 10
    assert result.applied_trim_3p_nt == 10
    assert result.trim_source == "record"
    assert result.large_trim_human_approved is True
    assert LARGE_TRIM_HUMAN_APPROVED_FLAG in result.canonical["qc_flags"]


def test_explicit_human_trim_over_40_percent_core_below_20_still_fails() -> None:
    sequence = _rna(40)
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="below 20"):
        apply_numeric_terminal_trim(
            sequence,
            five_nt=15,
            three_nt=10,
            record_id="aptadb:x",
            human_authorised=True,
        )


def test_explicit_human_trim_exceeding_sequence_length_still_fails() -> None:
    sequence = _rna(40)
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="exceeds sequence length"):
        apply_numeric_terminal_trim(
            sequence,
            five_nt=50,
            three_nt=0,
            record_id="aptadb:x",
            human_authorised=True,
        )


def test_explicit_human_negative_or_non_integer_trim_still_fails() -> None:
    from adapters.aptadb_checkpoint1_review import parse_trim_nt

    with pytest.raises(AptaDBCheckpoint1ReviewError, match="non-negative integer"):
        parse_trim_nt("-1", field_name="manual_trim_5p_nt", record_id="aptadb:x")
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="non-negative integer"):
        parse_trim_nt("1.5", field_name="manual_trim_3p_nt", record_id="aptadb:x")
    canonical = _canonical(sequence=_rna(40))
    review = _review(
        canonical,
        manual_trim_action="override",
        manual_trim_5p_nt="-3",
        manual_trim_3p_nt="0",
    )
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="non-negative integer"):
        apply_reviewed_record(
            canonical=canonical,
            review_row=review,
            source_metadata=_meta(canonical),
            s2_qc=_qc(canonical),
            policy=POLICY,
        )


def test_bulk_audit_requires_confirm_and_excludes_overlaps() -> None:
    audit = {
        "record_id": "aptadb:a",
        "checkpoint_review_reasons": "length_boundary",
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
    overlap = {
        **audit,
        "record_id": "aptadb:b",
        "checkpoint_review_reasons": "constant_region_proposal|length_boundary",
    }
    assert is_audit_only_row(audit)
    assert not is_audit_only_row(overlap)
    confirmation = {
        "confirmation_id": "audit_only_keep_current_route",
        "confirm": "",
        "eligible_record_ids": "aptadb:a",
    }
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="confirm=true"):
        materialize_bulk_audit_decisions([audit], confirmation)
    confirmation["confirm"] = "true"
    updated = materialize_bulk_audit_decisions([audit, overlap], confirmation)
    by_id = {row["record_id"]: row for row in updated}
    assert by_id["aptadb:a"]["manual_decision"] == "keep"
    assert by_id["aptadb:b"]["manual_decision"] == ""


def test_unresolved_package_cannot_apply() -> None:
    canonical = _canonical()
    review = _review(canonical, decision="")
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="remain unresolved"):
        apply_aptadb_checkpoint1_package(
            queue_rows=[review],
            group_rows=[],
            canonical_by_id={canonical["record_id"]: canonical},
            source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
            s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
            policy=POLICY,
        )


def test_prepare_leaves_manual_blank_and_adds_recommendation_columns(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    rec_path = (
        repo
        / "config"
        / "checkpoint_reviews"
        / "aptadb_checkpoint1_recommendations.json"
    )
    rec_path.parent.mkdir(parents=True)
    rec_path.write_text(
        json.dumps(
            {
                "source_key": "aptadb",
                "records": {},
                "groups": {},
                "audit_only": {
                    "review_recommendation": "keep_current_route",
                    "recommended_manual_decision": "keep",
                    "rationale": "bulk audit",
                },
            }
        ),
        encoding="utf-8",
    )
    checkpoint = repo / "data" / "interim" / "checkpoints" / "aptadb_cp1"
    from adapters.aptadb_s3 import DECISION_COLUMNS

    review = {
        "record_id": "aptadb:keep",
        "native_id": "keep",
        "aptamer_name": "name",
        "target_name_raw": "demo",
        "proposed_decision": "proposed_accept",
        "primary_reason": "technically_eligible_rna",
        "secondary_reasons": "",
        "primary_route": "technically_eligible",
        "manual_review_required": "true",
        "manual_review_priority": "low",
        "review_batch": "03_length_boundary",
        "checkpoint_review_reasons": "length_boundary",
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
    detail = {column: "" for column in LOCAL_DETAIL_COLUMNS}
    detail.update(
        {
            "record_id": "aptadb:keep",
            "native_id": "keep",
            "aptamer_name": "name",
            "target_name_raw": "demo",
            "proposed_decision": "proposed_accept",
            "primary_reason": "technically_eligible_rna",
            "primary_route": "technically_eligible",
            "manual_review_required": "true",
            "manual_review_priority": "low",
            "review_batch": "03_length_boundary",
            "checkpoint_review_reasons": "length_boundary",
            "checkpoint_status": "pending_checkpoint_1_review",
            "sequence_raw": "ACGUACGU",
            "sequence_full": "ACGUACGU",
            "sequence_core": "ACGUACGU",
            "sequence_length_full": "8",
            "sequence_length_core": "8",
            "molecule_type": "RNA",
            "chemistry": "RNA",
            "aptadb_target_chemistry": "Protein",
            "alphabet_as_reported": "RNA",
            "t_to_u_applied": "false",
            "trim_confidence": "n/a",
        }
    )
    checkpoint.mkdir(parents=True)
    with (checkpoint / "aptadb_checkpoint1_review.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DECISION_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerow({col: review.get(col, "") for col in DECISION_COLUMNS})
    with (checkpoint / "aptadb_checkpoint1_local_detail.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(LOCAL_DETAIL_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerow({col: detail.get(col, "") for col in LOCAL_DETAIL_COLUMNS})
    result = prepare_aptadb_checkpoint1_review(
        repo_root=repo,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "manual_review",
        expected_total_rows=1,
        expected_active_rows=1,
    )
    queue = list(csv.DictReader(result.output_queue.open(encoding="utf-8", newline="")))
    assert list(queue[0].keys()) == list(APTADB_MANUAL_REVIEW_COLUMNS)
    assert queue[0]["manual_decision"] == ""
    assert queue[0]["review_recommendation"] == "keep_current_route"
    assert queue[0]["bulk_audit_eligible"] == "true"
    assert result.output_group_review is not None
    assert result.output_readme is not None
    assert "ACGU" not in result.output_readme.read_text(encoding="utf-8")
    assert "ACGU" not in result.output_summary.read_text(encoding="utf-8")


def _decision_row(canonical: dict[str, str], *, route: str, reason: str) -> dict[str, str]:
    proposed = {
        PRIMARY_ROUTE_ELIGIBLE: "proposed_accept",
        PRIMARY_ROUTE_SSDNA: "proposed_park",
        PRIMARY_ROUTE_REJECT: "proposed_reject",
    }[route]
    return {
        column: ""
        for column in DECISION_COLUMNS
    } | {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "proposed_decision": proposed,
        "primary_reason": reason,
        "primary_route": route,
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical["chemistry"],
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical["trim_confidence"],
        "qc_flags": canonical["qc_flags"],
    }


def test_dry_run_uses_apply_package_and_does_not_mutate_inputs() -> None:
    from adapters.aptadb_checkpoint1_dry_run import simulate_aptadb_checkpoint1_application
    from copy import deepcopy

    hyphen = _dna(20) + "-" + _dna(20)
    edited = _canonical(
        native_id="230",
        sequence=hyphen,
        molecule_type="ssDNA",
        chemistry="DNA",
        alphabet="DNA_T",
        qc_flags="alignment_gaps",
    )
    kept = _canonical(native_id="keep", sequence=_rna(40))
    dropped = _canonical(
        native_id="305",
        sequence=_rna(20) + "T" + _rna(19),
        qc_flags="mixed_t_u",
        alphabet="mixed_T_U",
    )
    unreviewed = _canonical(native_id="900", sequence=_rna(40))
    originals = [edited, kept, dropped, unreviewed]
    snapshot = deepcopy(originals)
    decisions = [
        _decision_row(edited, route=PRIMARY_ROUTE_REJECT, reason="alignment_gaps"),
        _decision_row(kept, route=PRIMARY_ROUTE_ELIGIBLE, reason="technically_eligible_rna"),
        _decision_row(dropped, route=PRIMARY_ROUTE_REJECT, reason="mixed_T_and_U"),
        _decision_row(
            unreviewed, route=PRIMARY_ROUTE_ELIGIBLE, reason="technically_eligible_rna"
        ),
    ]
    queue = [
        _review(
            edited,
            route=PRIMARY_ROUTE_REJECT,
            manual_sequence_corrected=hyphen.replace("-", ""),
        ),
        _review(kept, decision="keep", route=PRIMARY_ROUTE_ELIGIBLE),
        _review(dropped, decision="drop", route=PRIMARY_ROUTE_REJECT),
    ]
    unlinked = [
        {
            "apta_index": "u1",
            "aptamer_chemistry": "RNA",
            "sequence": "ACGU",
            "planned_s3_reason": "missing_target",
        },
        {
            "apta_index": "u2",
            "aptamer_chemistry": "DNA",
            "sequence": "ACGT",
            "planned_s3_reason": "missing_target",
        },
    ]
    rejection = {
        "record_id": dropped["record_id"],
        "source_db": "aptadb",
        "source_dataset": dropped["source_dataset"],
        "native_id": dropped["native_id"],
        "sequence_raw": dropped["sequence_raw"],
        "target_name_raw": dropped["target_name_raw"],
        "stage": "S3",
        "rejection_reason": "mixed_T_and_U",
        "rejection_detail": "",
    }
    meta = {row["record_id"]: _meta(row) for row in originals}
    qc = {row["record_id"]: _qc(row) for row in originals}
    first = simulate_aptadb_checkpoint1_application(
        queue_rows=queue,
        group_rows=[],
        canonical_rows=originals,
        decision_rows=decisions,
        source_metadata_by_id=meta,
        s2_qc_by_id=qc,
        policy=POLICY,
        unlinked_rows=unlinked,
        existing_rejection_rows=[rejection],
        expected_interaction_rows=4,
        expected_unlinked_rows=2,
    )
    second = simulate_aptadb_checkpoint1_application(
        queue_rows=queue,
        group_rows=[],
        canonical_rows=originals,
        decision_rows=decisions,
        source_metadata_by_id=meta,
        s2_qc_by_id=qc,
        policy=POLICY,
        unlinked_rows=unlinked,
        existing_rejection_rows=[rejection],
        expected_interaction_rows=4,
        expected_unlinked_rows=2,
    )
    assert originals == snapshot
    assert first.preview_canonical == second.preview_canonical
    assert first.preview_decisions == second.preview_decisions
    assert first.preview_rejections == second.preview_rejections
    by_id = {row["record_id"]: row for row in first.preview_decisions}
    assert by_id["aptadb:230"]["primary_route"] == PRIMARY_ROUTE_SSDNA
    assert by_id["aptadb:305"]["primary_route"] == PRIMARY_ROUTE_REJECT
    drop_rej = next(
        row for row in first.preview_rejections if row["record_id"] == "aptadb:305"
    )
    assert drop_rej["rejection_reason"] == "mixed_T_and_U"
    assert "checkpoint1_manual_decision=drop" in drop_rej["rejection_detail"]
    unlinked_ids = [
        row["record_id"]
        for row in first.preview_rejections
        if row["record_id"].startswith("aptadb:unlinked:")
    ]
    assert unlinked_ids == ["aptadb:unlinked:u1", "aptadb:unlinked:u2"]
    assert all(
        row["rejection_reason"] == "missing_target"
        for row in first.preview_rejections
        if row["record_id"].startswith("aptadb:unlinked:")
    )
    for row in first.preview_canonical:
        for field_name in S3_FORBIDDEN_FIELDS:
            assert row[field_name] == ""
        assert row["sequence_raw"] == snapshot[
            [item["record_id"] for item in snapshot].index(row["record_id"])
        ]["sequence_raw"]
    assert first.stats["human_reviewed_drops"] == 1
    assert first.stats["authorised_for_s4"] == 0
    assert first.stats["guard_rail_failures"] == 0


def test_dry_run_group_trim_and_record_override() -> None:
    from adapters.aptadb_checkpoint1_dry_run import simulate_aptadb_checkpoint1_application

    member = _canonical(native_id="10", sequence=_rna(40))
    exception = _canonical(native_id="11", sequence=_rna(40))
    group = {
        "constant_group_id": "group-a",
        "group_label": "demo",
        "manual_trim_action": "approve",
        "manual_trim_5p_nt": "5",
        "manual_trim_3p_nt": "5",
        "machine_trim_5p_nt": "5",
        "machine_trim_3p_nt": "5",
    }
    queue = [
        _review(
            member,
            decision="edit",
            route=PRIMARY_ROUTE_ELIGIBLE,
            constant_group_id="group-a",
        ),
        _review(
            exception,
            decision="edit",
            route=PRIMARY_ROUTE_ELIGIBLE,
            constant_group_id="group-a",
            manual_trim_action="override",
            manual_trim_5p_nt="5",
            manual_trim_3p_nt="0",
            manual_trim_group_override="true",
        ),
    ]
    rows = [member, exception]
    decisions = [
        _decision_row(row, route=PRIMARY_ROUTE_ELIGIBLE, reason="technically_eligible_rna")
        for row in rows
    ]
    simulation = simulate_aptadb_checkpoint1_application(
        queue_rows=queue,
        group_rows=[group],
        canonical_rows=rows,
        decision_rows=decisions,
        source_metadata_by_id={row["record_id"]: _meta(row) for row in rows},
        s2_qc_by_id={row["record_id"]: _qc(row) for row in rows},
        policy=POLICY,
        expected_interaction_rows=2,
        expected_unlinked_rows=0,
    )
    by_id = {item.record_id: item for item in simulation.applied}
    assert by_id["aptadb:10"].applied_trim_5p_nt == 5
    assert by_id["aptadb:10"].applied_trim_3p_nt == 5
    assert by_id["aptadb:10"].sequence_length_core == 30
    assert by_id["aptadb:11"].applied_trim_5p_nt == 5
    assert by_id["aptadb:11"].applied_trim_3p_nt == 0
    assert by_id["aptadb:11"].sequence_length_core == 35
    assert by_id["aptadb:10"].trim_source == "group"
    assert by_id["aptadb:11"].trim_source == "record"


def test_dry_run_molecule_override_changes_route() -> None:
    from adapters.aptadb_checkpoint1_dry_run import simulate_aptadb_checkpoint1_application

    original = _canonical(
        native_id="9",
        sequence=_dna(40),
        molecule_type="ssDNA",
        chemistry="DNA",
        alphabet="DNA_T",
    )
    queue = [
        _review(
            original,
            route=PRIMARY_ROUTE_SSDNA,
            manual_molecule_type_override="RNA",
            manual_chemistry_override="RNA",
        )
    ]
    simulation = simulate_aptadb_checkpoint1_application(
        queue_rows=queue,
        group_rows=[],
        canonical_rows=[original],
        decision_rows=[
            _decision_row(original, route=PRIMARY_ROUTE_SSDNA, reason="ssdna_parked")
        ],
        source_metadata_by_id={original["record_id"]: _meta(original)},
        s2_qc_by_id={original["record_id"]: _qc(original)},
        policy=POLICY,
        expected_interaction_rows=1,
        expected_unlinked_rows=0,
    )
    assert simulation.applied[0].primary_route_before == PRIMARY_ROUTE_SSDNA
    assert simulation.applied[0].primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    assert simulation.route_changed_ids == ("aptadb:9",)


def test_dry_run_human_approved_large_trim_produces_complete_preview() -> None:
    from adapters.aptadb_checkpoint1_dry_run import simulate_aptadb_checkpoint1_application

    record = _canonical(native_id="40pct", sequence=_rna(40))
    queue = [
        _review(
            record,
            decision="keep",
            route=PRIMARY_ROUTE_ELIGIBLE,
            constant_group_id="group-wide",
        )
    ]
    group = {
        "constant_group_id": "group-wide",
        "group_label": "wide",
        "manual_trim_action": "approve",
        "manual_trim_5p_nt": "10",
        "manual_trim_3p_nt": "10",
        "machine_trim_5p_nt": "10",
        "machine_trim_3p_nt": "10",
    }
    simulation = simulate_aptadb_checkpoint1_application(
        queue_rows=queue,
        group_rows=[group],
        canonical_rows=[record],
        decision_rows=[
            _decision_row(
                record, route=PRIMARY_ROUTE_ELIGIBLE, reason="technically_eligible_rna"
            )
        ],
        source_metadata_by_id={record["record_id"]: _meta(record)},
        s2_qc_by_id={record["record_id"]: _qc(record)},
        policy=POLICY,
        expected_interaction_rows=1,
        expected_unlinked_rows=0,
    )
    assert simulation.stats["guard_rail_failures"] == 0
    assert simulation.stats["preview_complete"] is True
    assert len(simulation.preview_canonical) == 1
    assert simulation.applied[0].large_trim_human_approved is True
    assert simulation.stats["large_trim_human_approved"] == 1
    assert simulation.large_trim_records[0]["record_id"] == "aptadb:40pct"
    assert simulation.large_trim_records[0]["authorisation"] == "CHECKPOINT-1"
    assert LARGE_TRIM_HUMAN_APPROVED_FLAG in simulation.preview_canonical[0]["qc_flags"]
    assert simulation.stats["authorised_for_s4"] == 0


def test_dry_run_collects_remaining_absolute_trim_guard_rail_failures() -> None:
    from adapters.aptadb_checkpoint1_dry_run import simulate_aptadb_checkpoint1_application

    record = _canonical(native_id="tooshort", sequence=_rna(40))
    queue = [
        _review(
            record,
            decision="edit",
            route=PRIMARY_ROUTE_ELIGIBLE,
            constant_group_id="group-wide",
            manual_trim_action="override",
            manual_trim_5p_nt="15",
            manual_trim_3p_nt="10",
        )
    ]
    group = {
        "constant_group_id": "group-wide",
        "group_label": "wide",
        "manual_trim_action": "approve",
        "manual_trim_5p_nt": "5",
        "manual_trim_3p_nt": "5",
        "machine_trim_5p_nt": "5",
        "machine_trim_3p_nt": "5",
    }
    simulation = simulate_aptadb_checkpoint1_application(
        queue_rows=queue,
        group_rows=[group],
        canonical_rows=[record],
        decision_rows=[
            _decision_row(
                record, route=PRIMARY_ROUTE_ELIGIBLE, reason="technically_eligible_rna"
            )
        ],
        source_metadata_by_id={record["record_id"]: _meta(record)},
        s2_qc_by_id={record["record_id"]: _qc(record)},
        policy=POLICY,
        expected_interaction_rows=1,
        expected_unlinked_rows=0,
    )
    assert simulation.stats["guard_rail_failures"] == 1
    assert simulation.preview_canonical == []
    assert simulation.guard_rail_failure_rows[0]["record_id"] == "aptadb:tooshort"
    assert "below 20" in simulation.guard_rail_failure_rows[0]["error"]
    assert simulation.stats["authorised_for_s4"] == 0
    assert simulation.stats["preview_complete"] is False


def test_dry_run_and_apply_package_share_large_trim_transformation() -> None:
    from adapters.aptadb_checkpoint1_dry_run import simulate_aptadb_checkpoint1_application

    record = _canonical(native_id="shared", sequence=_rna(40))
    queue = [
        _review(
            record,
            decision="keep",
            route=PRIMARY_ROUTE_ELIGIBLE,
            constant_group_id="group-wide",
        )
    ]
    group = {
        "constant_group_id": "group-wide",
        "group_label": "wide",
        "manual_trim_action": "approve",
        "manual_trim_5p_nt": "",
        "manual_trim_3p_nt": "",
        "machine_trim_5p_nt": "10",
        "machine_trim_3p_nt": "10",
    }
    canonical_by_id = {record["record_id"]: record}
    meta = {record["record_id"]: _meta(record)}
    qc = {record["record_id"]: _qc(record)}
    applied, _report = apply_aptadb_checkpoint1_package(
        queue_rows=queue,
        group_rows=[group],
        canonical_by_id=canonical_by_id,
        source_metadata_by_id=meta,
        s2_qc_by_id=qc,
        policy=POLICY,
    )
    simulation = simulate_aptadb_checkpoint1_application(
        queue_rows=queue,
        group_rows=[group],
        canonical_rows=[record],
        decision_rows=[
            _decision_row(
                record, route=PRIMARY_ROUTE_ELIGIBLE, reason="technically_eligible_rna"
            )
        ],
        source_metadata_by_id=meta,
        s2_qc_by_id=qc,
        policy=POLICY,
        expected_interaction_rows=1,
        expected_unlinked_rows=0,
    )
    assert applied[0].sequence_core == simulation.applied[0].sequence_core
    assert applied[0].sequence_length_core == simulation.applied[0].sequence_length_core
    assert applied[0].notes == simulation.applied[0].notes
    assert applied[0].canonical["qc_flags"] == simulation.applied[0].canonical["qc_flags"]
    assert applied[0].large_trim_human_approved is True
    assert simulation.applied[0].large_trim_human_approved is True
    assert applied[0].primary_route_after == simulation.applied[0].primary_route_after


def test_aptadb_live_apply_without_inputs_fails_closed(tmp_path: Path) -> None:
    from checkpoint1_apply_review import main
    from io import StringIO
    from contextlib import redirect_stderr

    err = StringIO()
    with redirect_stderr(err):
        rc = main(["--source", "aptadb", "--repo-root", str(tmp_path)])
    assert rc == 1
    message = err.getvalue()
    assert "not authorised" not in message
    assert "Missing apply input" in message or "does not exist" in message


def test_aptadb_live_apply_matches_dry_run_and_closes(tmp_path: Path) -> None:
    import hashlib
    import shutil
    from adapters.aptadb_s2 import CONSTANT_PROPOSAL_COLUMNS, S2_QC_COLUMNS
    from adapters.aptadb_s3 import PARK_COLUMNS
    from adapters.aptadb import UNLINKED_COLUMNS
    from adapters.aptadb_checkpoint1_review import (
        BULK_CONFIRMATION_COLUMNS,
        GROUP_REVIEW_COLUMNS,
    )
    from checkpoint1_apply_review import (
        run_aptadb_checkpoint1_apply,
        run_aptadb_checkpoint1_dry_run,
    )
    from checkpoint1_prepare_review import write_csv_atomic
    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic

    canonical = _canonical(native_id="1", sequence=_rna(40))
    edited = _canonical(
        native_id="230",
        sequence=_dna(20) + "-" + _dna(20),
        molecule_type="ssDNA",
        chemistry="DNA",
        alphabet="DNA_T",
        qc_flags="alignment_gaps",
    )
    rows = [canonical, edited]
    decisions = [
        _decision_row(canonical, route=PRIMARY_ROUTE_ELIGIBLE, reason="technically_eligible_rna"),
        _decision_row(edited, route=PRIMARY_ROUTE_REJECT, reason="alignment_gaps"),
    ]
    queue = [
        _review(canonical, decision="keep", route=PRIMARY_ROUTE_ELIGIBLE),
        _review(
            edited,
            route=PRIMARY_ROUTE_REJECT,
            manual_sequence_corrected=(_dna(20) + _dna(20)),
        ),
    ]
    rejection = {
        "record_id": edited["record_id"],
        "source_db": "aptadb",
        "source_dataset": edited["source_dataset"],
        "native_id": edited["native_id"],
        "sequence_raw": edited["sequence_raw"],
        "target_name_raw": edited["target_name_raw"],
        "stage": "S3",
        "rejection_reason": "alignment_gaps",
        "rejection_detail": "",
    }
    checkpoint = tmp_path / "data" / "interim" / "checkpoints" / "aptadb_cp1"
    review_dir = checkpoint / "manual_review"
    normalised = tmp_path / "data" / "interim" / "normalised"
    extracted = tmp_path / "data" / "interim" / "extracted"
    config_elig = tmp_path / "config" / "source_eligibility"
    config_norm = tmp_path / "config" / "source_normalisation"
    config_rev = tmp_path / "config" / "checkpoint_reviews"
    for path in (review_dir, normalised, extracted, config_elig, config_norm, config_rev):
        path.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO_ROOT / "config" / "source_eligibility" / "aptadb.json",
        config_elig / "aptadb.json",
    )
    shutil.copy(
        REPO_ROOT / "config" / "source_normalisation" / "aptadb.json",
        config_norm / "aptadb.json",
    )
    (config_rev / "aptadb_checkpoint1_recommendations.json").write_text(
        '{"source_key":"aptadb","records":{},"groups":{}}\n',
        encoding="utf-8",
    )
    write_corpus_csv_atomic(
        checkpoint / "aptadb_s3_canonical.csv", rows, columns=CORPUS_COLUMNS
    )
    write_corpus_csv_atomic(
        normalised / "aptadb_normalised.csv", rows, columns=CORPUS_COLUMNS
    )
    write_csv_atomic(checkpoint / "aptadb_s3_decisions.csv", DECISION_COLUMNS, decisions)
    write_csv_atomic(checkpoint / "rejected_aptadb.csv", REJECTION_COLUMNS, [rejection])
    write_csv_atomic(checkpoint / "aptadb_s3_parked_ssdna.csv", PARK_COLUMNS, [])
    write_csv_atomic(checkpoint / "aptadb_s3_parked_non_protein.csv", PARK_COLUMNS, [])
    write_csv_atomic(
        review_dir / "aptadb_checkpoint1_manual_review.csv",
        list(queue[0].keys()),
        queue,
    )
    write_csv_atomic(
        review_dir / "aptadb_checkpoint1_constant_group_review.csv",
        GROUP_REVIEW_COLUMNS,
        [],
    )
    write_csv_atomic(
        review_dir / "aptadb_checkpoint1_bulk_audit_confirmation.csv",
        BULK_CONFIRMATION_COLUMNS,
        [],
    )
    write_csv_atomic(
        normalised / "aptadb_s2_qc.csv",
        S2_QC_COLUMNS,
        [_qc(row) for row in rows],
    )
    write_csv_atomic(
        extracted / "aptadb_source_metadata.csv",
        ["record_id", "aptadb_target_chemistry", "aptadb_aptamer_chemistry"],
        [_meta(row) for row in rows],
    )
    write_csv_atomic(
        normalised / "aptadb_constant_region_proposals.csv",
        CONSTANT_PROPOSAL_COLUMNS,
        [],
    )
    write_csv_atomic(extracted / "aptadb_unlinked_aptamers.csv", UNLINKED_COLUMNS, [])

    preview_dir = checkpoint / "dry_run"
    run_aptadb_checkpoint1_dry_run(
        repo_root=tmp_path,
        checkpoint_dir=checkpoint,
        output_dir=preview_dir,
        check_deterministic_rerun=True,
        expected_interaction_rows=2,
        expected_unlinked_rows=0,
    )
    preview_canonical = preview_dir / "aptadb_checkpoint1_dry_run_canonical_preview.csv"
    preview_hash = hashlib.sha256(preview_canonical.read_bytes()).hexdigest()
    s3_hash = hashlib.sha256(
        (checkpoint / "aptadb_s3_canonical.csv").read_bytes()
    ).hexdigest()

    result = run_aptadb_checkpoint1_apply(
        repo_root=tmp_path,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "resolved",
        tracked_manifest=config_rev / "aptadb_checkpoint1_resolutions.csv",
        metadata_out=config_rev / "aptadb_checkpoint1_metadata.json",
        preview_dir=preview_dir,
        check_deterministic_rerun=True,
        expected_interaction_rows=2,
        expected_unlinked_rows=0,
        compare_to_preview=True,
    )
    applied_canonical = (
        checkpoint / "resolved" / "aptadb_checkpoint1_applied_canonical.csv"
    )
    assert result.checkpoint_closed is True
    assert result.preview_comparison_ok is True
    assert result.deterministic_rerun_ok is True
    assert applied_canonical.read_bytes() == preview_canonical.read_bytes()
    assert hashlib.sha256(preview_canonical.read_bytes()).hexdigest() == preview_hash
    assert (
        hashlib.sha256((checkpoint / "aptadb_s3_canonical.csv").read_bytes()).hexdigest()
        == s3_hash
    )
    metadata = json.loads(
        (config_rev / "aptadb_checkpoint1_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["checkpoint_closed"] is True
    assert metadata["s4_started"] is False
    assert metadata["source_key"] == "aptadb"

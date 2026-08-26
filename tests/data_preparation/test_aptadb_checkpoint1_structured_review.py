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
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    LOCAL_DETAIL_COLUMNS,
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
    with pytest.raises(AptaDBCheckpoint1ReviewError, match="guard rail"):
        apply_numeric_terminal_trim(
            sequence, five_nt=10, three_nt=10, record_id="aptadb:x"
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

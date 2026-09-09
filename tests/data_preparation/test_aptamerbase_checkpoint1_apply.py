"""AptamerBase CHECKPOINT-1 apply/dry-run tests (synthetic sequences only).

Literal nucleotides are repeating ACGU/ACGT tiles plus the frozen T7 motif
token. Does not read or embed real AptamerBase sequences.
"""

from __future__ import annotations

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

from adapters.aptadb_checkpoint1_review import (  # noqa: E402
    empty_manual_fields,
    validate_review_package,
)
from adapters.aptamerbase import TYPE_APTAMER  # noqa: E402
from adapters.aptamerbase_checkpoint1_apply import (  # noqa: E402
    APTAMERBASE_APPLY_NOT_AUTHORISED,
    AptamerBaseCheckpoint1ApplyError,
    refuse_unauthorised_apply,
)
from adapters.aptamerbase_checkpoint1_dry_run import (  # noqa: E402
    serialise_aptamerbase_simulation_sequence_free,
    simulate_aptamerbase_checkpoint1_application,
)
from adapters.aptamerbase_checkpoint1_review import (  # noqa: E402
    MANUAL_REJECT_REASON,
    T7_MOTIF_RNA,
    AptamerBaseCheckpoint1ReviewError,
    apply_aptamerbase_checkpoint1_package,
    apply_reviewed_record,
    compare_review_to_pristine,
)
from adapters.aptamerbase_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_MOLECULE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
)
from checkpoint1_apply_review import (  # noqa: E402
    Checkpoint1ApplyError,
    main,
    run_aptamerbase_checkpoint1_apply,
    run_aptamerbase_checkpoint1_dry_run,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import load_eligibility_policy  # noqa: E402

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "aptamerbase.json"
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _dna(n: int) -> str:
    return ("ACGT" * ((n // 4) + 1))[:n]


def _canonical(
    *,
    native_id: str = "0001",
    sequence: str = "",
    molecule_type: str = "RNA",
    chemistry: str = "RNA",
    alphabet: str = "RNA",
    qc_flags: str = "",
    sequence_raw: str | None = None,
    **overrides: str,
) -> dict[str, str]:
    sequence = sequence or _rna(40)
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"aptamerbase:{native_id}",
            "sequence_raw": sequence_raw if sequence_raw is not None else sequence,
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
            "target_name_raw": "",
            "source_db": "aptamerbase",
            "source_dataset": "aptamerbase_export_2026-06-24",
            "contributing_sources": "aptamerbase",
            "contributing_datasets": "aptamerbase_export_2026-06-24",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "publication": "Demo",
            "qc_flags": qc_flags,
        }
    )
    record.update(overrides)
    return record


def _qc(
    canonical: dict[str, str],
    *,
    source_object_type: str = "aptamer",
    rdf_has_rna: str = "true",
    rdf_has_dna: str = "false",
    chemistry_class: str = "unmodified_backbone",
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamerbase_id": canonical["native_id"],
        "source_object_type": source_object_type,
        "target_name_raw": "",
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical["chemistry"],
        "chemistry_class": chemistry_class,
        "molecule_evidence_source": "rdf",
        "t_to_u_applied": canonical["t_to_u_applied"],
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "reported_length_raw": canonical["sequence_length_core"],
        "length_matches_source": "true",
        "observable_length_bucket": "",
        "rdf_has_rna": rdf_has_rna,
        "rdf_has_dna": rdf_has_dna,
        "rdf_has_modified_nucleic_acid": "false",
        "rdf_has_minimal_aptamer_type": "false",
        "has_minimal_aptamer_sidecar": "false",
        "is_minimal_aptamer_of_sidecar": "false",
        "modification_text_present": "false",
        "detected_motifs": "",
        "construct_scope": canonical["construct_scope"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical["trim_confidence"],
        "qc_flags": canonical["qc_flags"],
        "review_reasons": "",
    }


def _meta(canonical: dict[str, str]) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamerbase_csv_data_row": "1",
        "aptamerbase_type": TYPE_APTAMER,
        "aptamerbase_id": canonical["native_id"],
        "aptamerbase_label": f"label-{canonical['native_id']}",
        "aptamerbase_sequence": canonical["sequence_raw"],
        "aptamerbase_sequence_length": canonical["sequence_length_core"],
        "aptamerbase_has_mutational_analysis": "",
        "aptamerbase_has_experimentally_determined_structure": "",
        "aptamerbase_has_minimal_aptamer": "",
        "aptamerbase_is_minimal_aptamer_of": "",
        "aptamerbase_has_application": "",
        "aptamerbase_has_modification_details": "",
        "aptamerbase_has_secondary_structure": "",
        "aptamerbase_has_predicted_secondary_structure": "",
        "aptamerbase_has_sequence_pattern": "",
    }


def _review(
    canonical: dict[str, str],
    *,
    decision: str = "keep",
    route: str = PRIMARY_ROUTE_ELIGIBLE,
    reason: str = "technically_eligible_rna",
    proposed: str = "proposed_accept",
    audit_only: bool = False,
    **fields: str,
) -> dict[str, str]:
    row = empty_manual_fields()
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "primary_route": route,
            "proposed_decision": proposed,
            "primary_reason": reason,
            "secondary_reasons": "",
            "molecule_type": canonical["molecule_type"],
            "chemistry": canonical["chemistry"],
            "sequence_full": canonical["sequence_full"],
            "sequence_length_core": canonical["sequence_length_core"],
            "sequence_length_full": canonical["sequence_length_full"],
            "trim_status": canonical["trim_status"],
            "trim_confidence": canonical["trim_confidence"],
            "qc_flags": canonical["qc_flags"],
            "alphabet_as_reported": canonical["alphabet_as_reported"],
            "constant_group_id": "",
            "constant_proposed_trim_length": "",
            "constant_proposal_sides": "",
            "checkpoint_review_reasons": (
                "length_boundary" if audit_only else "judgement_dependent_technical"
            ),
            "audit_only_row": "true" if audit_only else "false",
            "bulk_audit_eligible": "true" if audit_only else "false",
            "manual_decision": decision,
        }
    )
    row.update(fields)
    return row


def _decision_row(canonical: dict[str, str], review: dict[str, str]) -> dict[str, str]:
    return {column: str(review.get(column, "") or "") for column in DECISION_COLUMNS}


def _apply(canonical: dict[str, str], review: dict[str, str], **kwargs):
    return apply_reviewed_record(
        canonical=canonical,
        review_row=review,
        source_metadata=kwargs.get("meta") or _meta(canonical),
        s2_qc=kwargs.get("qc") or _qc(canonical),
        policy=POLICY,
        proposals=kwargs.get("proposals") or (),
        group_row=kwargs.get("group_row"),
        machine_five=kwargs.get("machine_five", 0),
        machine_three=kwargs.get("machine_three", 0),
    )


def _bulk(*, ids: list[str], confirm: str = "true") -> dict[str, str]:
    return {
        "confirmation_id": "audit_only_keep_current_route",
        "scope": "audit_only_keep_current_route",
        "eligible_record_count": str(len(ids)),
        "eligible_record_ids": "|".join(ids),
        "confirm": confirm,
        "reviewer_initials": "",
        "manual_notes": "",
    }


def _known_motif(record_id: str) -> dict[str, str]:
    return {
        "proposal_id": f"{record_id}:known_motif:five_prime:t7_promoter_minimal",
        "experiment_group_id": record_id,
        "proposal_source": "known_motif",
        "side": "five_prime",
        "proposed_sequence": "",
        "motif_id": "t7_promoter_minimal",
        "motif_length": "17",
        "support": "",
        "records_considered": "1",
        "records_matching_exactly": "1",
        "confidence": "configured_motif_library",
        "status": "proposed_for_review",
        "applied": "false",
        "reason_not_applied": "detection_only_not_an_approved_trim",
        "reason": "known_motif:t7_promoter_minimal",
    }


def test_completed_human_review_validates() -> None:
    judge = _canonical(native_id="j1")
    audit = _canonical(native_id="a1")
    queue = [
        _review(judge, decision="drop"),
        _review(audit, decision="", audit_only=True),
    ]
    report = validate_review_package(
        queue_rows=queue,
        group_rows=[],
        bulk_confirmation=_bulk(ids=[audit["record_id"]]),
    )
    assert report.ok
    assert report.judgement_required_rows == 1
    assert report.unresolved_judgement_required == 0
    assert report.audit_only_rows == 1
    assert report.audit_only_unconfirmed == 0
    assert report.bulk_audit_confirmed is True
    assert report.ready_for_application == 2
    assert report.blocking_issues == []


def test_blank_judgement_fails_closed() -> None:
    row = _canonical(native_id="j2")
    report = validate_review_package(
        queue_rows=[_review(row, decision="")],
        group_rows=[],
        bulk_confirmation=_bulk(ids=[], confirm="true"),
    )
    assert not report.ok
    assert report.unresolved_judgement_required == 1
    assert report.ready_for_application == 0


def test_invalid_judgement_fails_closed() -> None:
    row = _canonical(native_id="j3")
    report = validate_review_package(
        queue_rows=[_review(row, decision="accept")],
        group_rows=[],
    )
    assert not report.ok
    assert any("Invalid manual_decision" in item for item in report.blocking_issues)


def test_bulk_confirm_true_resolves_audit_only_cohort() -> None:
    audit = _canonical(native_id="a2")
    report = validate_review_package(
        queue_rows=[_review(audit, decision="", audit_only=True)],
        group_rows=[],
        bulk_confirmation=_bulk(ids=[audit["record_id"]], confirm="true"),
    )
    assert report.ok
    assert report.audit_only_unconfirmed == 0
    assert report.unresolved_manual_decisions == 0


def test_audit_only_manual_fields_can_remain_blank() -> None:
    audit = _canonical(native_id="a3")
    review = _review(audit, decision="", audit_only=True)
    assert review["manual_decision"] == ""
    assert review["manual_sequence_corrected"] == ""
    report = validate_review_package(
        queue_rows=[review],
        group_rows=[],
        bulk_confirmation=_bulk(ids=[audit["record_id"]]),
    )
    assert report.ok


def test_human_sequence_edit_preserves_sequence_raw() -> None:
    raw = "B" + _dna(40)
    canonical = _canonical(
        native_id="b1",
        sequence=raw,
        molecule_type="ssDNA",
        chemistry="DNA",
        alphabet="invalid",
        qc_flags="invalid_character",
        sequence_raw=raw,
    )
    corrected = _dna(40)
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_REJECT,
            reason="invalid_alphabet",
            proposed="proposed_reject",
            manual_sequence_corrected=corrected,
        ),
        qc=_qc(canonical, rdf_has_rna="false", rdf_has_dna="true"),
    )
    assert result.sequence_raw == raw
    assert result.canonical["sequence_raw"] == raw
    assert result.sequence_full == corrected
    assert result.molecule_type == "ssDNA"


def test_rna_t_to_u_reviewed_correction_applies_exactly_once() -> None:
    mixed = _dna(40)
    canonical = _canonical(
        native_id="t1",
        sequence=mixed,
        molecule_type="RNA",
        chemistry="RNA",
        alphabet="mixed_T_U",
        qc_flags="mixed_t_u",
        sequence_raw=mixed,
    )
    corrected = mixed.replace("T", "U")
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_REJECT,
            reason="mixed_T_and_U",
            proposed="proposed_reject",
            manual_sequence_corrected=corrected,
        ),
    )
    assert result.sequence_full == corrected
    assert "T" not in result.sequence_full
    assert result.sequence_full.count("U") == mixed.count("T")
    assert result.t_to_u_applied is True
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_biotin_display_token_correction_can_produce_ssdna_park() -> None:
    raw = "B" + _dna(40)
    canonical = _canonical(
        native_id="b2",
        sequence=raw,
        molecule_type="ssDNA",
        chemistry="DNA",
        alphabet="invalid",
        qc_flags="invalid_character",
        sequence_raw=raw,
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_REJECT,
            reason="invalid_alphabet",
            proposed="proposed_reject",
            manual_sequence_corrected=_dna(40),
        ),
        qc=_qc(canonical, rdf_has_rna="false", rdf_has_dna="true"),
    )
    assert result.primary_route_after == PRIMARY_ROUTE_SSDNA
    assert result.sequence_raw == raw
    assert "U" not in result.sequence_full


def test_molecule_override_rdf_dna_to_rna_preserves_rdf_provenance() -> None:
    seq = _rna(40)
    canonical = _canonical(
        native_id="d1",
        sequence=seq,
        molecule_type="ssDNA",
        chemistry="DNA",
        alphabet="RNA",
        qc_flags="source_molecule_alphabet_conflict",
    )
    qc = _qc(canonical, rdf_has_rna="false", rdf_has_dna="true")
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_SSDNA,
            reason="ssdna_parked",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="RNA",
        ),
        qc=qc,
    )
    assert result.molecule_type == "RNA"
    assert result.chemistry == "RNA"
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    assert result.decision["rdf_has_dna"] == "true"
    assert result.decision["rdf_has_rna"] == "false"
    assert "reviewed_source_override=true" in result.notes


def test_unknown_molecule_to_ssdna_routes_ssdna_park() -> None:
    seq = _dna(40)
    canonical = _canonical(
        native_id="u1",
        sequence=seq,
        molecule_type="unknown",
        chemistry="unknown",
        alphabet="DNA_T",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_MOLECULE,
            reason="molecule_type_unresolved",
            proposed="proposed_park",
            manual_molecule_type_override="ssDNA",
            manual_chemistry_override="DNA",
        ),
        qc=_qc(canonical, rdf_has_rna="false", rdf_has_dna="false"),
    )
    assert result.molecule_type == "ssDNA"
    assert result.chemistry == "DNA"
    assert result.primary_route_after == PRIMARY_ROUTE_SSDNA
    assert "U" not in result.sequence_full


def test_reviewed_chemistry_unknown_stays_chemistry_park() -> None:
    canonical = _canonical(
        native_id="c1",
        chemistry="unknown",
        qc_flags="chemistry_requires_review",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="chemistry_requires_review",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="unknown",
        ),
    )
    assert result.chemistry == "unknown"
    assert result.primary_route_after == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    assert result.primary_route_after != PRIMARY_ROUTE_ELIGIBLE


@pytest.mark.parametrize(
    ("chemistry", "native_id"),
    [
        ("2F-RNA", "c2"),
        ("2NH2-RNA", "c3"),
        ("2OMe-RNA", "c4"),
        ("mixed", "c5"),
    ],
)
def test_reviewed_modified_rna_chemistry_can_be_eligible(
    chemistry: str, native_id: str
) -> None:
    canonical = _canonical(
        native_id=native_id,
        chemistry="unknown",
        qc_flags="chemistry_requires_review",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="chemistry_requires_review",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override=chemistry,
        ),
    )
    assert result.chemistry == chemistry
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_pentynyl_du_records_override_to_ssdna_dna() -> None:
    seq = _dna(40)
    canonical = _canonical(
        native_id="p1",
        sequence=seq,
        molecule_type="RNA",
        chemistry="unknown",
        alphabet="DNA_T",
        qc_flags="chemistry_requires_review",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="chemistry_requires_review",
            proposed="proposed_park",
            manual_molecule_type_override="ssDNA",
            manual_chemistry_override="DNA",
        ),
        qc=_qc(canonical, rdf_has_rna="false", rdf_has_dna="true"),
    )
    assert result.molecule_type == "ssDNA"
    assert result.chemistry == "DNA"
    assert result.primary_route_after == PRIMARY_ROUTE_SSDNA


def test_approved_motif_trim_applies_exactly_17_nt_once() -> None:
    full = T7_MOTIF_RNA + _rna(40)
    canonical = _canonical(
        native_id="m1",
        sequence=full,
        qc_flags="known_promoter_detected",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CONSTRUCT,
            reason="trim_construct_unresolved",
            proposed="proposed_park",
            manual_trim_action="approve",
            manual_trim_5p_nt="17",
            manual_trim_3p_nt="0",
            constant_proposed_trim_length="17",
            constant_proposal_sides="five_prime",
        ),
        machine_five=17,
        proposals=[_known_motif(canonical["record_id"])],
    )
    assert result.applied_trim_5p_nt == 17
    assert result.applied_trim_3p_nt == 0
    assert result.sequence_length_full == 57
    assert result.sequence_length_core == 40
    assert result.sequence_core == full[17:]
    assert result.sequence_core != result.sequence_full
    assert result.trim_status == "t7_removed"
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_length_reject_becomes_in_range_after_approved_trim() -> None:
    full = T7_MOTIF_RNA + _rna(89)
    assert len(full) == 106
    canonical = _canonical(
        native_id="0922x",
        sequence=full,
        qc_flags="known_promoter_detected",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_REJECT,
            reason="length_out_of_range",
            proposed="proposed_reject",
            manual_trim_action="approve",
            manual_trim_5p_nt="17",
            manual_trim_3p_nt="0",
        ),
        machine_five=17,
        proposals=[_known_motif(canonical["record_id"])],
    )
    assert result.sequence_length_core == 89
    assert 20 <= result.sequence_length_core <= 100
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    assert result.primary_route_before == PRIMARY_ROUTE_REJECT


def test_manual_drop_routes_manual_reject() -> None:
    canonical = _canonical(native_id="x1")
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="drop",
            route=PRIMARY_ROUTE_REJECT,
            reason="invalid_alphabet",
            proposed="proposed_reject",
        ),
    )
    assert result.primary_route_after == PRIMARY_ROUTE_REJECT
    assert result.primary_reason == MANUAL_REJECT_REASON
    assert result.sequence_full == canonical["sequence_full"]


def test_edit_recomputes_rather_than_forcing_eligibility() -> None:
    canonical = _canonical(native_id="e1", chemistry="unknown")
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="chemistry_requires_review",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="unknown",
        ),
    )
    assert result.primary_route_after == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    assert result.primary_route_after != PRIMARY_ROUTE_ELIGIBLE


def test_dry_run_refuses_resolved_output_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "data" / "interim").mkdir(parents=True)
    with pytest.raises(Checkpoint1ApplyError, match="resolved"):
        run_aptamerbase_checkpoint1_dry_run(
            repo_root=repo,
            checkpoint_dir=repo / "data" / "interim" / "checkpoints" / "aptamerbase_cp1",
            output_dir=repo / "data" / "interim" / "checkpoints" / "resolved",
            check_deterministic_rerun=False,
            verify_frozen_inputs=False,
        )


def test_real_apply_without_explicit_authority_is_refused() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(["--source", "aptamerbase"])
    assert code == 1
    assert "not authorised" in stderr.getvalue()
    with pytest.raises(AptamerBaseCheckpoint1ApplyError, match="not authorised"):
        refuse_unauthorised_apply()
    with pytest.raises(Checkpoint1ApplyError, match="not authorised"):
        run_aptamerbase_checkpoint1_apply()
    assert "--dry-run" in APTAMERBASE_APPLY_NOT_AUTHORISED
    assert "--authorise-actual-apply" in APTAMERBASE_APPLY_NOT_AUTHORISED


def test_dry_run_is_deterministic() -> None:
    kept = _canonical(native_id="k1")
    dropped = _canonical(native_id="k2")
    queue = [
        _review(kept, decision="keep"),
        _review(
            dropped,
            decision="drop",
            route=PRIMARY_ROUTE_REJECT,
            reason="invalid_alphabet",
            proposed="proposed_reject",
        ),
    ]
    kwargs = dict(
        queue_rows=queue,
        group_rows=[],
        canonical_rows=[kept, dropped],
        decision_rows=[_decision_row(kept, queue[0]), _decision_row(dropped, queue[1])],
        source_metadata_by_id={row["record_id"]: _meta(row) for row in (kept, dropped)},
        s2_qc_by_id={row["record_id"]: _qc(row) for row in (kept, dropped)},
        policy=POLICY,
        expected_source_rows=2,
    )
    first = simulate_aptamerbase_checkpoint1_application(**kwargs)
    second = simulate_aptamerbase_checkpoint1_application(**kwargs)
    assert serialise_aptamerbase_simulation_sequence_free(
        first
    ) == serialise_aptamerbase_simulation_sequence_free(second)
    assert first.stats["total_records"] == 2
    assert first.stats["checkpoint_closed"] is False
    assert first.stats["authorised_for_s4"] == 0


def test_s4_fields_stay_empty() -> None:
    canonical = _canonical(native_id="s4")
    for field_name in S3_FORBIDDEN_FIELDS:
        canonical[field_name] = ""
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="RNA",
        ),
    )
    for field_name in S3_FORBIDDEN_FIELDS:
        assert result.canonical.get(field_name, "") == ""


def test_denominator_preserved_in_dry_run_merge() -> None:
    reviewed = _canonical(native_id="r1")
    untouched = _canonical(native_id="r2")
    queue = [_review(reviewed, decision="keep")]
    simulation = simulate_aptamerbase_checkpoint1_application(
        queue_rows=queue,
        group_rows=[],
        canonical_rows=[reviewed, untouched],
        decision_rows=[
            _decision_row(reviewed, queue[0]),
            {
                **{column: "" for column in DECISION_COLUMNS},
                "record_id": untouched["record_id"],
                "native_id": untouched["native_id"],
                "primary_route": PRIMARY_ROUTE_ELIGIBLE,
                "proposed_decision": "proposed_accept",
                "primary_reason": "technically_eligible_rna",
                "molecule_type": "RNA",
                "chemistry": "RNA",
            },
        ],
        source_metadata_by_id={
            reviewed["record_id"]: _meta(reviewed),
            untouched["record_id"]: _meta(untouched),
        },
        s2_qc_by_id={reviewed["record_id"]: _qc(reviewed), untouched["record_id"]: _qc(untouched)},
        policy=POLICY,
        expected_source_rows=2,
    )
    assert simulation.stats["total_records"] == 2
    assert simulation.stats["reviewed_records"] == 1
    assert simulation.stats["unaffected_records"] == 1
    assert len(simulation.preview_canonical) == 2


def test_unresolved_package_cannot_apply() -> None:
    canonical = _canonical(native_id="z1")
    with pytest.raises(AptamerBaseCheckpoint1ReviewError, match="unresolved"):
        apply_aptamerbase_checkpoint1_package(
            queue_rows=[_review(canonical, decision="")],
            group_rows=[],
            canonical_by_id={canonical["record_id"]: canonical},
            source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
            s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
            policy=POLICY,
        )


def test_manual_target_corrected_is_forbidden() -> None:
    canonical = _canonical(native_id="z2")
    review = _review(
        canonical,
        decision="edit",
        manual_molecule_type_override="RNA",
        manual_target_corrected="not-a-target",
    )
    with pytest.raises(AptamerBaseCheckpoint1ReviewError, match="manual_target_corrected"):
        apply_aptamerbase_checkpoint1_package(
            queue_rows=[review],
            group_rows=[],
            canonical_by_id={canonical["record_id"]: canonical},
            source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
            s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
            policy=POLICY,
        )


def test_compare_review_to_pristine_permits_only_human_fields() -> None:
    canonical = _canonical(native_id="p1")
    blank = _review(canonical, decision="")
    filled = dict(blank)
    filled["manual_decision"] = "drop"
    filled["manual_notes"] = "CHECKPOINT-1: notation unrecoverable."
    assert compare_review_to_pristine([filled], [blank]) == []
    drifted = dict(filled)
    drifted["review_recommendation"] = "keep"
    assert compare_review_to_pristine([drifted], [blank])


def test_dispatcher_dry_run_is_recognised(tmp_path: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "aptamerbase",
                "--dry-run",
                "--repo-root",
                str(tmp_path),
            ]
        )
    assert code == 1
    message = stderr.getvalue()
    assert "Missing dry-run input" in message or "does not exist" in message


def _install_mini_aptamerbase(
    tmp_path: Path,
    *,
    canonical_rows: list[dict[str, str]],
    decision_rows: list[dict[str, str]],
    queue_rows: list[dict[str, str]],
    qc_rows: list[dict[str, str]] | None = None,
    meta_rows: list[dict[str, str]] | None = None,
    rejection_rows: list[dict[str, str]] | None = None,
    proposal_rows: list[dict[str, str]] | None = None,
) -> Path:
    import shutil

    from adapters.aptadb_checkpoint1_review import (
        BULK_CONFIRMATION_COLUMNS,
        GROUP_REVIEW_COLUMNS,
    )
    from adapters.aptamerbase_s2 import CONSTANT_PROPOSAL_COLUMNS, S2_QC_COLUMNS
    from adapters.aptamerbase_s3 import PARK_COLUMNS, REJECTION_COLUMNS
    from checkpoint1_prepare_review import write_csv_atomic
    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic

    checkpoint = tmp_path / "data" / "interim" / "checkpoints" / "aptamerbase_cp1"
    review_dir = checkpoint / "manual_review"
    normalised = tmp_path / "data" / "interim" / "normalised"
    extracted = tmp_path / "data" / "interim" / "extracted"
    config_elig = tmp_path / "config" / "source_eligibility"
    config_rev = tmp_path / "config" / "checkpoint_reviews"
    for path in (review_dir, normalised, extracted, config_elig, config_rev):
        path.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO_ROOT / "config" / "source_eligibility" / "aptamerbase.json",
        config_elig / "aptamerbase.json",
    )
    (config_rev / "aptamerbase_checkpoint1_recommendations.json").write_text(
        '{"source_key":"aptamerbase","records":{},"groups":{}}\n',
        encoding="utf-8",
    )
    write_corpus_csv_atomic(
        checkpoint / "aptamerbase_s3_canonical.csv",
        canonical_rows,
        columns=CORPUS_COLUMNS,
        quoting=__import__("csv").QUOTE_ALL,
    )
    write_corpus_csv_atomic(
        normalised / "aptamerbase_normalised.csv",
        canonical_rows,
        columns=CORPUS_COLUMNS,
        quoting=__import__("csv").QUOTE_ALL,
    )
    write_csv_atomic(
        checkpoint / "aptamerbase_s3_decisions.csv",
        DECISION_COLUMNS,
        decision_rows,
        quoting=__import__("csv").QUOTE_ALL,
    )
    write_csv_atomic(
        checkpoint / "rejected_aptamerbase.csv",
        REJECTION_COLUMNS,
        rejection_rows or [],
        quoting=__import__("csv").QUOTE_ALL,
    )
    for name in (
        "aptamerbase_s3_parked_ssdna.csv",
        "aptamerbase_s3_parked_molecule_unresolved.csv",
        "aptamerbase_s3_parked_chemistry_review.csv",
        "aptamerbase_s3_parked_construct_review.csv",
    ):
        write_csv_atomic(
            checkpoint / name, PARK_COLUMNS, [], quoting=__import__("csv").QUOTE_ALL
        )
    write_csv_atomic(
        review_dir / "aptamerbase_checkpoint1_manual_review.csv",
        list(queue_rows[0].keys()),
        queue_rows,
        quoting=__import__("csv").QUOTE_ALL,
    )
    write_csv_atomic(
        review_dir / "aptamerbase_checkpoint1_constant_group_review.csv",
        GROUP_REVIEW_COLUMNS,
        [],
        quoting=__import__("csv").QUOTE_ALL,
    )
    audit_ids = [
        row["record_id"]
        for row in queue_rows
        if (row.get("audit_only_row") or "").lower() == "true"
    ]
    write_csv_atomic(
        review_dir / "aptamerbase_checkpoint1_bulk_audit_confirmation.csv",
        BULK_CONFIRMATION_COLUMNS,
        [_bulk(ids=audit_ids)] if queue_rows else [],
        quoting=__import__("csv").QUOTE_ALL,
    )
    qc_rows = qc_rows or [_qc(row) for row in canonical_rows]
    write_csv_atomic(
        normalised / "aptamerbase_s2_qc.csv",
        S2_QC_COLUMNS,
        qc_rows,
        quoting=__import__("csv").QUOTE_ALL,
    )
    meta_rows = meta_rows or [_meta(row) for row in canonical_rows]
    write_csv_atomic(
        extracted / "aptamerbase_source_metadata.csv",
        list(meta_rows[0].keys()),
        meta_rows,
        quoting=__import__("csv").QUOTE_ALL,
    )
    if proposal_rows:
        write_csv_atomic(
            normalised / "detected_constants_aptamerbase.csv",
            CONSTANT_PROPOSAL_COLUMNS,
            proposal_rows,
            quoting=__import__("csv").QUOTE_ALL,
        )
    return checkpoint


def _mini_apply_corpus() -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    eligible = _canonical(native_id="e001")
    audit = _canonical(native_id="a001")
    dropped = _canonical(native_id="d001")
    unknown_chem = _canonical(
        native_id="0410", chemistry="unknown", qc_flags="chemistry_requires_review"
    )
    amino = _canonical(
        native_id="n001", chemistry="unknown", qc_flags="chemistry_requires_review"
    )
    mixed = _canonical(
        native_id="x001", chemistry="unknown", qc_flags="chemistry_requires_review"
    )
    rescued = _canonical(
        native_id="0922",
        sequence=T7_MOTIF_RNA + _rna(89),
        qc_flags="known_promoter_detected|length_out_of_range",
    )
    untouched = _canonical(native_id="u001")
    rows = [eligible, audit, dropped, unknown_chem, amino, mixed, rescued, untouched]
    queue = [
        _review(eligible, decision="keep"),
        _review(audit, decision="", audit_only=True),
        _review(
            dropped,
            decision="drop",
            route=PRIMARY_ROUTE_REJECT,
            reason="invalid_alphabet",
            proposed="proposed_reject",
        ),
        _review(
            unknown_chem,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="chemistry_requires_review",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="unknown",
        ),
        _review(
            amino,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="chemistry_requires_review",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="2NH2-RNA",
        ),
        _review(
            mixed,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="chemistry_requires_review",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="mixed",
        ),
        _review(
            rescued,
            decision="edit",
            route=PRIMARY_ROUTE_REJECT,
            reason="length_out_of_range",
            proposed="proposed_reject",
            manual_trim_action="approve",
            manual_trim_5p_nt="17",
            manual_trim_3p_nt="0",
            constant_proposed_trim_length="17",
            constant_proposal_sides="five_prime",
        ),
    ]
    decisions = [
        _decision_row(eligible, queue[0]),
        _decision_row(audit, queue[1]),
        _decision_row(dropped, queue[2]),
        _decision_row(unknown_chem, queue[3]),
        _decision_row(amino, queue[4]),
        _decision_row(mixed, queue[5]),
        _decision_row(rescued, queue[6]),
        {
            **{column: "" for column in DECISION_COLUMNS},
            "record_id": untouched["record_id"],
            "native_id": untouched["native_id"],
            "primary_route": PRIMARY_ROUTE_ELIGIBLE,
            "proposed_decision": "proposed_accept",
            "primary_reason": "technically_eligible_rna",
            "molecule_type": "RNA",
            "chemistry": "RNA",
        },
    ]
    proposals = [_known_motif(rescued["record_id"])]
    return rows, decisions, queue, proposals


def test_apply_refuses_unresolved_review(tmp_path: Path) -> None:
    canonical = _canonical(native_id="z9")
    checkpoint = _install_mini_aptamerbase(
        tmp_path,
        canonical_rows=[canonical],
        decision_rows=[_decision_row(canonical, _review(canonical, decision="keep"))],
        queue_rows=[_review(canonical, decision="")],
    )
    with pytest.raises(Checkpoint1ApplyError, match="unresolved|not ready"):
        run_aptamerbase_checkpoint1_apply(
            repo_root=tmp_path,
            checkpoint_dir=checkpoint,
            output_dir=checkpoint / "resolved",
            tracked_manifest=(
                tmp_path / "config" / "checkpoint_reviews" / "resolutions.csv"
            ),
            metadata_out=tmp_path / "config" / "checkpoint_reviews" / "metadata.json",
            check_deterministic_rerun=False,
            expected_source_rows=1,
            verify_production_hashes=False,
            compare_to_preview=False,
            authorise_actual_apply=True,
        )


def test_apply_consumes_exactly_the_completed_review_hash(tmp_path: Path) -> None:
    import hashlib

    rows, decisions, queue, proposals = _mini_apply_corpus()
    checkpoint = _install_mini_aptamerbase(
        tmp_path,
        canonical_rows=rows,
        decision_rows=decisions,
        queue_rows=queue,
        proposal_rows=proposals,
    )
    queue_path = (
        checkpoint / "manual_review" / "aptamerbase_checkpoint1_manual_review.csv"
    )
    before = hashlib.sha256(queue_path.read_bytes()).hexdigest()
    run_aptamerbase_checkpoint1_apply(
        repo_root=tmp_path,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "resolved",
        tracked_manifest=(
            tmp_path / "config" / "checkpoint_reviews" / "resolutions.csv"
        ),
        metadata_out=tmp_path / "config" / "checkpoint_reviews" / "metadata.json",
        check_deterministic_rerun=False,
        expected_source_rows=len(rows),
        verify_production_hashes=False,
        compare_to_preview=False,
        authorise_actual_apply=True,
    )
    after = hashlib.sha256(queue_path.read_bytes()).hexdigest()
    assert after == before


def test_apply_requires_locked_review_hash_in_production_mode(tmp_path: Path) -> None:
    canonical = _canonical(native_id="h1")
    checkpoint = _install_mini_aptamerbase(
        tmp_path,
        canonical_rows=[canonical],
        decision_rows=[_decision_row(canonical, _review(canonical, decision="keep"))],
        queue_rows=[_review(canonical, decision="keep")],
    )
    with pytest.raises(Checkpoint1ApplyError, match="human review SHA-256"):
        run_aptamerbase_checkpoint1_apply(
            repo_root=tmp_path,
            checkpoint_dir=checkpoint,
            output_dir=checkpoint / "resolved",
            tracked_manifest=(
                tmp_path / "config" / "checkpoint_reviews" / "resolutions.csv"
            ),
            metadata_out=tmp_path / "config" / "checkpoint_reviews" / "metadata.json",
            check_deterministic_rerun=False,
            expected_source_rows=1,
            verify_production_hashes=True,
            compare_to_preview=False,
            authorise_actual_apply=True,
        )


def test_live_apply_matches_dry_run_and_closes(tmp_path: Path) -> None:
    import csv as csv_mod
    import hashlib
    import json

    from adapters.aptamerbase_checkpoint1_apply import (
        APTAMERBASE_TRACKED_RESOLUTION_COLUMNS,
        AUTHORISED_FOR_S4_MEANING,
        TRACKED_SEQUENCE_COLUMN_FRAGMENTS,
    )

    rows, decisions, queue, proposals = _mini_apply_corpus()
    checkpoint = _install_mini_aptamerbase(
        tmp_path,
        canonical_rows=rows,
        decision_rows=decisions,
        queue_rows=queue,
        proposal_rows=proposals,
    )
    preview_dir = checkpoint / "dry_run"
    run_aptamerbase_checkpoint1_dry_run(
        repo_root=tmp_path,
        checkpoint_dir=checkpoint,
        output_dir=preview_dir,
        check_deterministic_rerun=True,
        expected_source_rows=len(rows),
        verify_frozen_inputs=False,
    )
    preview_canonical = (
        preview_dir / "aptamerbase_checkpoint1_dry_run_canonical_preview.csv"
    )
    preview_hash = hashlib.sha256(preview_canonical.read_bytes()).hexdigest()
    s3_hash = hashlib.sha256(
        (checkpoint / "aptamerbase_s3_canonical.csv").read_bytes()
    ).hexdigest()
    queue_hash = hashlib.sha256(
        (
            checkpoint / "manual_review" / "aptamerbase_checkpoint1_manual_review.csv"
        ).read_bytes()
    ).hexdigest()

    result = run_aptamerbase_checkpoint1_apply(
        repo_root=tmp_path,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "resolved",
        tracked_manifest=(
            tmp_path
            / "config"
            / "checkpoint_reviews"
            / "aptamerbase_checkpoint1_resolutions.csv"
        ),
        metadata_out=(
            tmp_path
            / "config"
            / "checkpoint_reviews"
            / "aptamerbase_checkpoint1_metadata.json"
        ),
        preview_dir=preview_dir,
        check_deterministic_rerun=True,
        expected_source_rows=len(rows),
        verify_production_hashes=False,
        compare_to_preview=True,
        authorise_actual_apply=True,
    )
    applied_canonical = (
        checkpoint / "resolved" / "aptamerbase_checkpoint1_applied_canonical.csv"
    )
    assert result.checkpoint_closed is True
    assert result.preview_comparison_ok is True
    assert result.deterministic_rerun_ok is True
    assert result.semantic_mismatches == 0
    assert result.byte_identical_count == 10
    assert applied_canonical.read_bytes() == preview_canonical.read_bytes()
    assert hashlib.sha256(preview_canonical.read_bytes()).hexdigest() == preview_hash
    assert (
        hashlib.sha256((checkpoint / "aptamerbase_s3_canonical.csv").read_bytes()).hexdigest()
        == s3_hash
    )
    assert (
        hashlib.sha256(
            (
                checkpoint
                / "manual_review"
                / "aptamerbase_checkpoint1_manual_review.csv"
            ).read_bytes()
        ).hexdigest()
        == queue_hash
    )

    with applied_canonical.open(newline="") as handle:
        applied_rows = {row["native_id"]: row for row in csv_mod.DictReader(handle)}
    assert len(applied_rows) == 8
    assert applied_rows["0922"]["sequence_length_full"] == "106"
    assert applied_rows["0922"]["sequence_length_core"] == "89"
    assert 20 <= int(applied_rows["0922"]["sequence_length_core"]) <= 100
    assert applied_rows["0922"]["sequence_raw"] == rows[6]["sequence_raw"]
    assert applied_rows["0410"]["chemistry"] == "unknown"
    assert applied_rows["n001"]["chemistry"] == "2NH2-RNA"
    assert applied_rows["x001"]["chemistry"] == "mixed"
    for row in applied_rows.values():
        for field_name in S3_FORBIDDEN_FIELDS:
            assert row.get(field_name, "") == ""
        assert row.get("target_name_raw", "") == ""

    with (checkpoint / "resolved" / "aptamerbase_checkpoint1_applied_routing.csv").open(
        newline=""
    ) as handle:
        routes = {row["native_id"]: row for row in csv_mod.DictReader(handle)}
    assert routes["e001"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["a001"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["d001"]["primary_route"] == PRIMARY_ROUTE_REJECT
    assert routes["d001"]["primary_reason"] == MANUAL_REJECT_REASON
    assert routes["0410"]["primary_route"] == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    assert routes["n001"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["x001"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["0922"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["u001"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["0410"]["rdf_has_rna"] == "true"
    assert sum(1 for row in routes.values() if row["primary_route"] == PRIMARY_ROUTE_ELIGIBLE) == 6
    assert sum(1 for row in routes.values() if row["primary_route"] == PRIMARY_ROUTE_REJECT) == 1
    assert sum(
        1
        for row in routes.values()
        if row["primary_route"] == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    ) == 1
    assert sum(
        1
        for row in routes.values()
        if row["primary_route"] == PRIMARY_ROUTE_MOLECULE
    ) == 0
    assert sum(
        1
        for row in routes.values()
        if row["primary_route"] == PRIMARY_ROUTE_CONSTRUCT
    ) == 0

    with (checkpoint / "resolved" / "aptamerbase_checkpoint1_s4_authorised_ids.csv").open(
        newline=""
    ) as handle:
        authorised = list(csv_mod.DictReader(handle))
    assert len(authorised) == 6
    assert result.stats["authorised_for_s4"] == 6

    with (checkpoint / "resolved" / "aptamerbase_checkpoint1_trim_audit.csv").open(
        newline=""
    ) as handle:
        trims = list(csv_mod.DictReader(handle))
    assert len(trims) == 1
    assert trims[0]["record_id"] == "aptamerbase:0922"
    assert trims[0]["trim_5p_nt"] == "17"
    assert trims[0]["trim_3p_nt"] == "0"
    assert trims[0]["post_core_length"] == "89"

    resolutions_path = (
        tmp_path
        / "config"
        / "checkpoint_reviews"
        / "aptamerbase_checkpoint1_resolutions.csv"
    )
    metadata_path = (
        tmp_path
        / "config"
        / "checkpoint_reviews"
        / "aptamerbase_checkpoint1_metadata.json"
    )
    with resolutions_path.open(newline="") as handle:
        resolution_rows = list(csv_mod.DictReader(handle))
    assert list(resolution_rows[0].keys()) == list(APTAMERBASE_TRACKED_RESOLUTION_COLUMNS)
    joined = " ".join(resolution_rows[0].keys())
    for fragment in TRACKED_SEQUENCE_COLUMN_FRAGMENTS:
        assert fragment not in joined
    for row in resolution_rows:
        for value in row.values():
            assert "ACGU" not in value
            assert T7_MOTIF_RNA not in value
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["checkpoint_closed"] is True
    assert metadata["checkpoint"] == "CHECKPOINT-1"
    assert metadata["global_s4_run"] is False
    assert metadata["global_s4_handoff_prepared"] is False
    assert metadata["authorised_for_s4"] == 6
    assert metadata["authorised_for_s4_meaning"] == AUTHORISED_FOR_S4_MEANING
    metadata_text = json.dumps(metadata)
    assert "ACGU" not in metadata_text
    assert "sequence_raw" not in metadata
    assert not (tmp_path / "config" / "global_s4_sources" / "aptamerbase.json").exists()


def test_closure_refuses_on_parity_mismatch(tmp_path: Path) -> None:
    rows, decisions, queue, proposals = _mini_apply_corpus()
    checkpoint = _install_mini_aptamerbase(
        tmp_path,
        canonical_rows=rows,
        decision_rows=decisions,
        queue_rows=queue,
        proposal_rows=proposals,
    )
    preview_dir = checkpoint / "dry_run"
    run_aptamerbase_checkpoint1_dry_run(
        repo_root=tmp_path,
        checkpoint_dir=checkpoint,
        output_dir=preview_dir,
        check_deterministic_rerun=False,
        expected_source_rows=len(rows),
        verify_frozen_inputs=False,
    )
    routing_preview = preview_dir / "aptamerbase_checkpoint1_dry_run_routing_preview.csv"
    text = routing_preview.read_text(encoding="utf-8")
    routing_preview.write_text(
        text.replace(PRIMARY_ROUTE_ELIGIBLE, PRIMARY_ROUTE_REJECT, 1),
        encoding="utf-8",
    )
    metadata_out = tmp_path / "config" / "checkpoint_reviews" / "metadata.json"
    with pytest.raises(Checkpoint1ApplyError, match="scientific mismatches|byte-identical"):
        run_aptamerbase_checkpoint1_apply(
            repo_root=tmp_path,
            checkpoint_dir=checkpoint,
            output_dir=checkpoint / "resolved",
            tracked_manifest=(
                tmp_path / "config" / "checkpoint_reviews" / "resolutions.csv"
            ),
            metadata_out=metadata_out,
            preview_dir=preview_dir,
            check_deterministic_rerun=False,
            expected_source_rows=len(rows),
            verify_production_hashes=False,
            compare_to_preview=True,
            authorise_actual_apply=True,
        )
    assert not metadata_out.exists()
    payload = json.loads(
        (
            tmp_path / "config" / "checkpoint_reviews" / "aptamerbase_checkpoint1_metadata.json"
        ).read_text(encoding="utf-8")
        if (
            tmp_path / "config" / "checkpoint_reviews" / "aptamerbase_checkpoint1_metadata.json"
        ).exists()
        else "{}"
    )
    assert payload.get("checkpoint_closed") is not True


def test_existing_resolved_payload_must_match_identical_rerun(tmp_path: Path) -> None:
    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic

    rows, decisions, queue, proposals = _mini_apply_corpus()
    checkpoint = _install_mini_aptamerbase(
        tmp_path,
        canonical_rows=rows,
        decision_rows=decisions,
        queue_rows=queue,
        proposal_rows=proposals,
    )
    preview_dir = checkpoint / "dry_run"
    run_aptamerbase_checkpoint1_dry_run(
        repo_root=tmp_path,
        checkpoint_dir=checkpoint,
        output_dir=preview_dir,
        check_deterministic_rerun=False,
        expected_source_rows=len(rows),
        verify_frozen_inputs=False,
    )
    resolved = checkpoint / "resolved"
    resolved.mkdir(parents=True)
    write_corpus_csv_atomic(
        resolved / "aptamerbase_checkpoint1_applied_canonical.csv",
        [_canonical(native_id="other")],
        columns=CORPUS_COLUMNS,
        quoting=__import__("csv").QUOTE_ALL,
    )
    with pytest.raises(Checkpoint1ApplyError, match="Existing authoritative"):
        run_aptamerbase_checkpoint1_apply(
            repo_root=tmp_path,
            checkpoint_dir=checkpoint,
            output_dir=resolved,
            tracked_manifest=(
                tmp_path / "config" / "checkpoint_reviews" / "resolutions.csv"
            ),
            metadata_out=tmp_path / "config" / "checkpoint_reviews" / "metadata.json",
            preview_dir=preview_dir,
            check_deterministic_rerun=False,
            expected_source_rows=len(rows),
            verify_production_hashes=False,
            compare_to_preview=True,
            authorise_actual_apply=True,
        )

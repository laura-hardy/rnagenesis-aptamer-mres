"""ENA CHECKPOINT-1 apply/dry-run tests (synthetic sequences only).

Literal nucleotides are short fixtures or repeating ACGU/UGCA tiles.
Does not read real ENA source sequences.
"""

from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.ena import SIDECAR_COLUMNS  # noqa: E402
from adapters.ena_checkpoint1_apply import (  # noqa: E402
    AUTHORISED_FOR_S4_MEANING,
    ENA_TRACKED_RESOLUTION_COLUMNS,
    TRACKED_SEQUENCE_COLUMN_FRAGMENTS,
    EnaCheckpoint1ApplyError,
    apply_ena_checkpoint1_package,
    apply_ena_reviewed_record,
    apply_reviewed_terminal_trim,
    compare_ena_package_to_pristine,
    resolve_ena_effective_trim,
    simulate_ena_checkpoint1_application,
)
from adapters.ena_s3 import (  # noqa: E402
    DECISION_COLUMNS,
    PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
)
from adapters.aptadb_checkpoint1_review import EffectiveTrim  # noqa: E402
from checkpoint1_apply_review import (  # noqa: E402
    Checkpoint1ApplyError,
    main,
    run_ena_checkpoint1_apply,
    run_ena_checkpoint1_dry_run,
)
from common.corpus_schema import empty_corpus_record  # noqa: E402
from common.eligibility import load_eligibility_policy  # noqa: E402

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "ena.json"
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _flank(pattern: str, n: int) -> str:
    return (pattern * ((n // len(pattern)) + 1))[:n]


def _canonical(
    *,
    native_id: str,
    sequence: str,
    qc_flags: str = "",
    trim_status: str = "no_constants_detected",
    t_to_u_applied: str = "false",
    alphabet: str = "RNA",
    **overrides: str,
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence))
    record.update(
        {
            "record_id": f"ena:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "unknown",
            "trim_status": trim_status,
            "trim_confidence": "n/a",
            "molecule_type": "RNA",
            "alphabet_as_reported": alphabet,
            "t_to_u_applied": t_to_u_applied,
            "chemistry": "RNA",
            "target_name_raw": "demo_target",
            "source_db": "ena",
            "source_dataset": "ena_selected_v2_2026-08",
            "contributing_sources": "ena",
            "contributing_datasets": "ena_selected_v2_2026-08",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "qc_flags": qc_flags,
        }
    )
    record.update(overrides)
    return record


def _qc(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
    row = {
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
        "experiment_group_id": "g1",
        "source_promoter_or_template_concern": "false",
        "source_t7_concern": "false",
        "sequence_corrected_applied": "0",
    }
    row.update(overrides)
    return row


def _meta(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "review_unit_id": canonical["native_id"],
            "experiment_group_id": "g1",
        }
    )
    row.update(overrides)
    return row


def _decision(
    canonical: dict[str, str],
    *,
    route: str,
    reason: str,
    proposed: str,
    **overrides: str,
) -> dict[str, str]:
    row = {column: "" for column in DECISION_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "primary_route": route,
            "primary_reason": reason,
            "proposed_decision": proposed,
            "molecule_type": canonical["molecule_type"],
            "chemistry": canonical["chemistry"],
            "sequence_length_full": canonical["sequence_length_full"],
            "sequence_length_core": canonical["sequence_length_core"],
            "trim_status": canonical["trim_status"],
            "t_to_u_applied": canonical["t_to_u_applied"],
            "checkpoint_status": "pending_checkpoint_1_review",
        }
    )
    row.update(overrides)
    return row


def _review(
    canonical: dict[str, str],
    *,
    decision: str = "keep",
    route: str = PRIMARY_ROUTE_ELIGIBLE,
    **overrides: str,
) -> dict[str, str]:
    row = {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "primary_route": route,
        "proposed_decision": "proposed_accept",
        "primary_reason": "technically_eligible_rna",
        "checkpoint_review_reasons": "",
        "source_promoter_or_template_concern": "false",
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
        "audit_only_row": "false",
    }
    row.update(overrides)
    return row


def _rule(
    *,
    group_id: str,
    side: str,
    motif_length: int,
    action: str,
    five_nt: str = "",
    three_nt: str = "",
    n_records: int = 2,
) -> dict[str, str]:
    rule_id = f"{group_id}:{side}:group_consensus"
    return {
        "constant_rule_id": rule_id,
        "proposal_id": rule_id,
        "experiment_group_id": group_id,
        "side": side,
        "motif_length": str(motif_length),
        "confidence": "medium",
        "manual_trim_action": action,
        "manual_trim_5p_nt": five_nt,
        "manual_trim_3p_nt": three_nt,
        "machine_recommendation": "needs_source_review",
        "affected_s3_record_count": str(n_records),
    }


def _member(*, rule: dict[str, str], canonical: dict[str, str]) -> dict[str, str]:
    return {
        "constant_rule_id": rule["constant_rule_id"],
        "proposal_id": rule["proposal_id"],
        "experiment_group_id": rule["experiment_group_id"],
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "side": rule["side"],
    }


def _proposal(
    *,
    group_id: str,
    side: str,
    motif: str,
) -> dict[str, str]:
    return {
        "proposal_id": f"{group_id}:{side}:group_consensus",
        "experiment_group_id": group_id,
        "proposal_source": "group_consensus",
        "side": side,
        "proposed_sequence": motif,
        "motif_length": str(len(motif)),
        "confidence": "medium",
        "applied": "false",
        "records_considered": "2",
        "records_matching_exactly": "2",
        "support": "1",
    }


def test_keep_valid_accept_stays_eligible() -> None:
    canonical = _canonical(native_id="ok", sequence=_rna(40))
    result = apply_ena_reviewed_record(
        canonical=canonical,
        review_row=_review(canonical, decision="keep"),
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        original_decision=_decision(
            canonical,
            route=PRIMARY_ROUTE_ELIGIBLE,
            reason="technically_eligible_rna",
            proposed="proposed_accept",
        ),
    )
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    assert result.sequence_core == canonical["sequence_full"]
    assert result.applied_trim_5p_nt == 0
    assert "checkpoint1_manual_decision=keep" in result.notes


def test_short_keep_remains_technical_reject() -> None:
    canonical = _canonical(native_id="short", sequence=_rna(17))
    result = apply_ena_reviewed_record(
        canonical=canonical,
        review_row=_review(
            canonical,
            decision="keep",
            route=PRIMARY_ROUTE_REJECT,
            primary_reason="length_out_of_range",
            proposed_decision="proposed_reject",
        ),
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        original_decision=_decision(
            canonical,
            route=PRIMARY_ROUTE_REJECT,
            reason="length_out_of_range",
            proposed="proposed_reject",
        ),
    )
    assert result.primary_route_after == PRIMARY_ROUTE_REJECT
    assert result.primary_reason == "length_out_of_range"
    assert result.sequence_core == canonical["sequence_full"]
    assert result.rejection_row is not None
    assert result.rejection_row["rejection_reason"] == "length_out_of_range"


def test_promoter_keep_reject_trim_resolves_to_eligible() -> None:
    canonical = _canonical(
        native_id="prom",
        sequence=_rna(40),
        qc_flags="trim_requires_review",
        trim_status="constants_suspected_unresolved",
    )
    result = apply_ena_reviewed_record(
        canonical=canonical,
        review_row=_review(
            canonical,
            decision="keep",
            route=PRIMARY_ROUTE_CONSTRUCT,
            primary_reason="trim_construct_unresolved",
            proposed_decision="proposed_park",
            manual_trim_action="reject",
            source_promoter_or_template_concern="true",
        ),
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical, source_promoter_or_template_concern="true"),
        policy=POLICY,
        original_decision=_decision(
            canonical,
            route=PRIMARY_ROUTE_CONSTRUCT,
            reason="trim_construct_unresolved",
            proposed="proposed_park",
            source_promoter_or_template_concern="true",
        ),
    )
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    assert result.applied_trim_5p_nt == 0
    assert result.sequence_core == result.sequence_full
    assert "no_additional_trim" in result.notes


def test_group_both_end_trim_applied_once() -> None:
    five = _flank("ACGU", 23)
    three = _flank("UGCA", 19)
    core = _rna(40)
    seq = five + core + three
    canonical = _canonical(native_id="cass", sequence=seq)
    five_rule = _rule(
        group_id="g_cass",
        side="five_prime",
        motif_length=23,
        action="approve",
        five_nt="23",
    )
    three_rule = _rule(
        group_id="g_cass",
        side="three_prime",
        motif_length=20,
        action="override",
        three_nt="19",
    )
    effective = resolve_ena_effective_trim(
        record_id=canonical["record_id"],
        rules_for_record=[five_rule, three_rule],
        exceptions_for_record={},
    )
    assert effective is not None
    assert effective.five_nt == 23
    assert effective.three_nt == 19
    result = apply_ena_reviewed_record(
        canonical=canonical,
        review_row=_review(
            canonical,
            decision="keep",
            route=PRIMARY_ROUTE_CONSTRUCT,
            primary_reason="trim_construct_unresolved",
            proposed_decision="proposed_park",
        ),
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        proposals=[
            _proposal(group_id="g_cass", side="five_prime", motif=five),
            _proposal(group_id="g_cass", side="three_prime", motif="A" + three),
        ],
        effective=effective,
        five_motif=five,
        three_motif=three,
        original_decision=_decision(
            canonical,
            route=PRIMARY_ROUTE_CONSTRUCT,
            reason="trim_construct_unresolved",
            proposed="proposed_park",
        ),
    )
    assert result.sequence_full == seq
    assert result.sequence_core == core
    assert result.sequence_length_core == 40
    assert result.applied_trim_5p_nt == 23
    assert result.applied_trim_3p_nt == 19
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    assert result.trim_confidence == "medium"
    assert result.trim_status == "primers_removed"


def test_exception_override_applies_once_not_double() -> None:
    five = _flank("ACGU", 23)
    three19 = _flank("UGCA", 19)
    majority_three20 = "A" + three19
    exception_three20 = "C" + three19
    core = _rna(40)
    majority = _canonical(native_id="maj", sequence=five + core + majority_three20)
    exception = _canonical(native_id="exc", sequence=five + core + exception_three20)
    five_rule = _rule(
        group_id="g_exc",
        side="five_prime",
        motif_length=23,
        action="approve",
        five_nt="23",
        n_records=2,
    )
    three_rule = _rule(
        group_id="g_exc",
        side="three_prime",
        motif_length=20,
        action="override",
        three_nt="19",
        n_records=2,
    )
    exception_row = {
        "constant_rule_id": three_rule["constant_rule_id"],
        "proposal_id": three_rule["proposal_id"],
        "record_id": exception["record_id"],
        "exception_reason": "non_terminal_match",
        "manual_decision": "keep",
        "manual_trim_action": "override",
        "manual_trim_5p_nt": "",
        "manual_trim_3p_nt": "19",
        "machine_recommendation": "needs_source_review",
    }
    effective = resolve_ena_effective_trim(
        record_id=exception["record_id"],
        rules_for_record=[five_rule, three_rule],
        exceptions_for_record={three_rule["constant_rule_id"]: exception_row},
    )
    assert effective is not None
    assert effective.five_nt == 23
    assert effective.three_nt == 19
    assert effective.source == "record"
    result = apply_ena_reviewed_record(
        canonical=exception,
        review_row=_review(
            exception,
            decision="keep",
            route=PRIMARY_ROUTE_CONSTRUCT,
            primary_reason="trim_construct_unresolved",
            proposed_decision="proposed_park",
        ),
        source_metadata=_meta(exception),
        s2_qc=_qc(exception),
        policy=POLICY,
        effective=effective,
        five_motif=five,
        three_motif=three19,
        original_decision=_decision(
            exception,
            route=PRIMARY_ROUTE_CONSTRUCT,
            reason="trim_construct_unresolved",
            proposed="proposed_park",
        ),
    )
    assert result.sequence_core == core + "C"
    assert len(result.sequence_full) - len(result.sequence_core) == 42
    assert result.applied_trim_3p_nt == 19
    assert result.applied_trim_5p_nt == 23
    majority_effective = resolve_ena_effective_trim(
        record_id=majority["record_id"],
        rules_for_record=[five_rule, three_rule],
        exceptions_for_record={},
    )
    assert majority_effective is not None
    assert majority_effective.three_nt == 19


def test_rejected_group_trim_stays_untrimmed_and_eligible() -> None:
    motif = _flank("ACGU", 12)
    seq = motif + _rna(40)
    canonical = _canonical(
        native_id="ngf",
        sequence=seq,
        trim_status="constants_suspected_unresolved",
        qc_flags="trim_requires_review|constants_suspected_unresolved",
    )
    rule = _rule(
        group_id="g_ngf",
        side="five_prime",
        motif_length=12,
        action="reject",
    )
    effective = resolve_ena_effective_trim(
        record_id=canonical["record_id"],
        rules_for_record=[rule],
        exceptions_for_record={},
    )
    assert effective is None
    result = apply_ena_reviewed_record(
        canonical=canonical,
        review_row=_review(
            canonical,
            decision="keep",
            route=PRIMARY_ROUTE_CONSTRUCT,
            primary_reason="trim_construct_unresolved",
            proposed_decision="proposed_park",
        ),
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        proposals=[_proposal(group_id="g_ngf", side="five_prime", motif=motif)],
        original_decision=_decision(
            canonical,
            route=PRIMARY_ROUTE_CONSTRUCT,
            reason="trim_construct_unresolved",
            proposed="proposed_park",
        ),
    )
    assert result.sequence_core == result.sequence_full == seq
    assert result.applied_trim_5p_nt == 0
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_large_trim_fails_without_human_approval() -> None:
    five = _flank("ACGU", 23)
    three = _flank("UGCA", 19)
    core = _rna(40)
    seq = five + core + three
    with pytest.raises(EnaCheckpoint1ApplyError, match="40%|guard rail"):
        apply_reviewed_terminal_trim(
            seq,
            five_nt=23,
            three_nt=19,
            five_motif=five,
            three_motif=three,
            record_id="ena:big",
            human_authorised=False,
        )


def test_large_trim_passes_with_human_approval_and_provenance() -> None:
    five = _flank("ACGU", 23)
    three = _flank("UGCA", 19)
    core = _rna(40)
    seq = five + core + three
    canonical = _canonical(native_id="bigok", sequence=seq)
    effective = EffectiveTrim(
        action="override",
        five_nt=23,
        three_nt=19,
        source="group",
        group_id="g_big",
    )
    result = apply_ena_reviewed_record(
        canonical=canonical,
        review_row=_review(canonical, decision="keep", route=PRIMARY_ROUTE_CONSTRUCT),
        source_metadata=_meta(canonical),
        s2_qc=_qc(canonical),
        policy=POLICY,
        effective=effective,
        five_motif=five,
        three_motif=three,
        original_decision=_decision(
            canonical,
            route=PRIMARY_ROUTE_CONSTRUCT,
            reason="trim_construct_unresolved",
            proposed="proposed_park",
        ),
    )
    assert result.large_trim_human_approved is True
    assert "large_trim_human_approved=true" in result.notes
    assert "large_trim_human_approved" in result.canonical["qc_flags"]
    assert result.sequence_core == core


def test_retain_both_preserves_two_source_records() -> None:
    a = _canonical(native_id="a", sequence=_rna(40))
    b = _canonical(native_id="b", sequence=_rna(40))
    queue = [
        _review(a, decision="keep"),
        _review(b, decision="keep"),
    ]
    recon = [
        {
            "reconciliation_id": "ena_collapse_01",
            "record_id_a": a["record_id"],
            "record_id_b": b["record_id"],
            "manual_decision": "retain_both",
            "machine_recommendation": "retain_both_through_checkpoint_and_defer_exact_dedup",
            "manual_notes": "",
        }
    ]
    applied, _report, consumption = apply_ena_checkpoint1_package(
        queue_rows=queue,
        rule_rows=[],
        exception_rows=[],
        reconciliation_rows=recon,
        canonical_by_id={a["record_id"]: a, b["record_id"]: b},
        decision_by_id={
            a["record_id"]: _decision(
                a,
                route=PRIMARY_ROUTE_ELIGIBLE,
                reason="technically_eligible_rna",
                proposed="proposed_accept",
            ),
            b["record_id"]: _decision(
                b,
                route=PRIMARY_ROUTE_ELIGIBLE,
                reason="technically_eligible_rna",
                proposed="proposed_accept",
            ),
        },
        source_metadata_by_id={a["record_id"]: _meta(a), b["record_id"]: _meta(b)},
        s2_qc_by_id={a["record_id"]: _qc(a), b["record_id"]: _qc(b)},
        policy=POLICY,
        bulk_confirmation={"confirm": "true", "eligible_record_ids": ""},
    )
    assert consumption["reconciliation"] == 1
    assert {item.record_id for item in applied} == {a["record_id"], b["record_id"]}
    assert all(item.primary_route_after == PRIMARY_ROUTE_ELIGIBLE for item in applied)


def test_missing_rule_decision_fails() -> None:
    canonical = _canonical(native_id="miss", sequence=_rna(40))
    member = {
        "constant_rule_id": "missing:five_prime:group_consensus",
        "proposal_id": "missing:five_prime:group_consensus",
        "experiment_group_id": "missing",
        "record_id": canonical["record_id"],
        "side": "five_prime",
    }
    with pytest.raises(EnaCheckpoint1ApplyError, match="Missing rule decision"):
        apply_ena_checkpoint1_package(
            queue_rows=[_review(canonical, decision="keep")],
            rule_rows=[],
            exception_rows=[],
            reconciliation_rows=[],
            canonical_by_id={canonical["record_id"]: canonical},
            decision_by_id={
                canonical["record_id"]: _decision(
                    canonical,
                    route=PRIMARY_ROUTE_ELIGIBLE,
                    reason="technically_eligible_rna",
                    proposed="proposed_accept",
                )
            },
            source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
            s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
            policy=POLICY,
            membership_rows=[member],
            bulk_confirmation={"confirm": "true", "eligible_record_ids": ""},
        )


def test_invalid_override_trim_length_fails() -> None:
    rule = _rule(
        group_id="g_bad",
        side="three_prime",
        motif_length=20,
        action="override",
        three_nt="",
    )
    with pytest.raises(EnaCheckpoint1ApplyError, match="Invalid trim length"):
        resolve_ena_side_trim_safe(rule)


def resolve_ena_side_trim_safe(rule: dict[str, str]) -> None:
    from adapters.ena_checkpoint1_apply import resolve_ena_side_trim

    resolve_ena_side_trim(
        record_id="ena:x",
        side="three_prime",
        rule=rule,
        exception=None,
    )


def test_core_below_20_after_reviewed_trim_fails() -> None:
    five = _flank("ACGU", 23)
    three = _flank("UGCA", 19)
    core = _rna(10)
    seq = five + core + three
    with pytest.raises(EnaCheckpoint1ApplyError, match="below 20"):
        apply_reviewed_terminal_trim(
            seq,
            five_nt=23,
            three_nt=19,
            five_motif=five,
            three_motif=three,
            record_id="ena:tiny",
            human_authorised=True,
        )


def test_pristine_machine_field_drift_fails() -> None:
    queue = [
        {
            "record_id": "ena:a",
            "primary_reason": "technically_eligible_rna",
            "manual_decision": "keep",
        }
    ]
    pristine = [
        {
            "record_id": "ena:a",
            "primary_reason": "length_out_of_range",
            "manual_decision": "",
        }
    ]
    blank = [{"confirmation_id": "audit_only_keep_current_route", "confirm": ""}]
    reviewed_bulk = [{"confirmation_id": "audit_only_keep_current_route", "confirm": "true"}]
    with pytest.raises(EnaCheckpoint1ApplyError, match="pristine"):
        compare_ena_package_to_pristine(
            reviewed_queue=queue,
            pristine_queue=pristine,
            reviewed_rules=[],
            pristine_rules=[],
            reviewed_exceptions=[],
            pristine_exceptions=[],
            reviewed_reconciliation=[],
            pristine_reconciliation=[],
            reviewed_bulk=reviewed_bulk,
            pristine_bulk=blank,
        )


def test_in_memory_transform_matches_dry_run_preview() -> None:
    canonical = _canonical(native_id="par", sequence=_rna(40))
    queue = [_review(canonical, decision="keep")]
    decision = _decision(
        canonical,
        route=PRIMARY_ROUTE_ELIGIBLE,
        reason="technically_eligible_rna",
        proposed="proposed_accept",
    )
    applied, _report, _cons = apply_ena_checkpoint1_package(
        queue_rows=queue,
        rule_rows=[],
        exception_rows=[],
        reconciliation_rows=[],
        canonical_by_id={canonical["record_id"]: canonical},
        decision_by_id={canonical["record_id"]: decision},
        source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
        s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
        policy=POLICY,
        bulk_confirmation={"confirm": "true", "eligible_record_ids": ""},
    )
    simulation = simulate_ena_checkpoint1_application(
        queue_rows=queue,
        rule_rows=[],
        exception_rows=[],
        reconciliation_rows=[],
        canonical_rows=[canonical],
        decision_rows=[decision],
        source_metadata_by_id={canonical["record_id"]: _meta(canonical)},
        s2_qc_by_id={canonical["record_id"]: _qc(canonical)},
        policy=POLICY,
        bulk_confirmation={"confirm": "true", "eligible_record_ids": ""},
        expected_total_rows=1,
    )
    assert simulation.preview_canonical[0]["sequence_core"] == applied[0].sequence_core
    assert simulation.preview_decisions[0]["primary_route"] == applied[0].primary_route_after
    assert simulation.stats["technically_eligible"] == 1
    assert simulation.stats["authorised_for_s4"] == 0
    assert simulation.stats["checkpoint_closed"] is False


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def _install_mini_ena(
    tmp_path: Path,
    *,
    canonical_rows: list[dict[str, str]],
    decision_rows: list[dict[str, str]],
    queue_rows: list[dict[str, str]],
    qc_rows: list[dict[str, str]] | None = None,
    meta_rows: list[dict[str, str]] | None = None,
    rule_rows: list[dict[str, str]] | None = None,
    membership_rows: list[dict[str, str]] | None = None,
    exception_rows: list[dict[str, str]] | None = None,
    reconciliation_rows: list[dict[str, str]] | None = None,
    proposal_rows: list[dict[str, str]] | None = None,
) -> Path:
    checkpoint = tmp_path / "data" / "interim" / "checkpoints" / "ena_cp1"
    review = checkpoint / "manual_review"
    review.mkdir(parents=True)
    (tmp_path / "data" / "interim" / "normalised").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "interim" / "extracted").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "source_eligibility").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "checkpoint_reviews").mkdir(parents=True, exist_ok=True)
    policy_src = REPO_ROOT / "config" / "source_eligibility" / "ena.json"
    (tmp_path / "config" / "source_eligibility" / "ena.json").write_bytes(
        policy_src.read_bytes()
    )
    qc_rows = qc_rows or [_qc(row) for row in canonical_rows]
    meta_rows = meta_rows or [_meta(row) for row in canonical_rows]
    rule_rows = rule_rows or []
    membership_rows = membership_rows or []
    exception_rows = exception_rows or []
    reconciliation_rows = reconciliation_rows or []
    proposal_rows = proposal_rows or []
    _write_csv(review / "ena_checkpoint1_manual_review.csv", list(queue_rows[0]), queue_rows)
    _write_csv(
        review / "ena_checkpoint1_constant_rule_review.csv",
        list(rule_rows[0]) if rule_rows else ["constant_rule_id"],
        rule_rows,
    )
    _write_csv(
        review / "ena_checkpoint1_constant_rule_membership.csv",
        list(membership_rows[0]) if membership_rows else ["constant_rule_id", "record_id"],
        membership_rows,
    )
    _write_csv(
        review / "ena_checkpoint1_constant_exceptions.csv",
        list(exception_rows[0])
        if exception_rows
        else ["record_id", "constant_rule_id", "manual_decision", "manual_trim_action"],
        exception_rows,
    )
    recon_fields = (
        list(reconciliation_rows[0])
        if reconciliation_rows
        else ["reconciliation_id", "record_id_a", "record_id_b", "manual_decision"]
    )
    _write_csv(
        review / "ena_checkpoint1_legacy_collapse_reconciliation.csv",
        recon_fields,
        reconciliation_rows,
    )
    _write_csv(
        review / "ena_checkpoint1_legacy_collapse_reconciliation_index.csv",
        recon_fields,
        reconciliation_rows,
    )
    _write_csv(
        review / "ena_checkpoint1_bulk_audit_confirmation.csv",
        ["confirmation_id", "confirm", "eligible_record_ids"],
        [
            {
                "confirmation_id": "audit_only_keep_current_route",
                "confirm": "true",
                "eligible_record_ids": "",
            }
        ],
    )
    _write_csv(checkpoint / "ena_s3_canonical.csv", list(canonical_rows[0]), canonical_rows)
    _write_csv(checkpoint / "ena_s3_decisions.csv", list(decision_rows[0]), decision_rows)
    _write_csv(
        tmp_path / "data" / "interim" / "normalised" / "ena_normalised.csv",
        list(canonical_rows[0]),
        canonical_rows,
    )
    _write_csv(
        tmp_path / "data" / "interim" / "normalised" / "ena_s2_qc.csv",
        list(qc_rows[0]),
        qc_rows,
    )
    _write_csv(
        tmp_path / "data" / "interim" / "extracted" / "ena_source_metadata.csv",
        list(meta_rows[0]),
        meta_rows,
    )
    _write_csv(
        tmp_path / "data" / "interim" / "normalised" / "ena_constant_region_proposals.csv",
        list(proposal_rows[0])
        if proposal_rows
        else ["proposal_id", "proposal_source", "applied"],
        proposal_rows,
    )
    return checkpoint


def _live_ena_fixture(tmp_path: Path) -> tuple[Path, dict[str, dict[str, str]]]:
    five = _flank("ACGU", 23)
    three19 = _flank("UGCA", 19)
    core = _rna(40)
    majority_three20 = "A" + three19
    exception_three20 = "C" + three19
    eligible = _canonical(native_id="ok", sequence=_rna(40))
    short = _canonical(native_id="short", sequence=_rna(15))
    cass = _canonical(
        native_id="cass",
        sequence=five + core + majority_three20,
        qc_flags="trim_requires_review|constants_suspected_unresolved",
        trim_status="constants_suspected_unresolved",
    )
    exc = _canonical(
        native_id="exc",
        sequence=five + core + exception_three20,
        qc_flags="trim_requires_review|constants_suspected_unresolved",
        trim_status="constants_suspected_unresolved",
    )
    ngf = _canonical(
        native_id="ngf",
        sequence=_flank("ACGU", 12) + _rna(40),
        qc_flags="trim_requires_review|constants_suspected_unresolved",
        trim_status="constants_suspected_unresolved",
    )
    prom = _canonical(
        native_id="prom",
        sequence=_rna(40),
        qc_flags="source_promoter_or_template_concern",
    )
    dup_a = _canonical(native_id="dup_a", sequence=_rna(40))
    dup_b = _canonical(native_id="dup_b", sequence=_rna(40))
    rows = [eligible, short, cass, exc, ngf, prom, dup_a, dup_b]
    five_rule = _rule(
        group_id="g_cass",
        side="five_prime",
        motif_length=23,
        action="approve",
        five_nt="23",
        n_records=2,
    )
    three_rule = _rule(
        group_id="g_cass",
        side="three_prime",
        motif_length=20,
        action="override",
        three_nt="19",
        n_records=2,
    )
    ngf_rule = _rule(
        group_id="g_ngf",
        side="five_prime",
        motif_length=12,
        action="reject",
        n_records=1,
    )
    queue = [
        _review(eligible, decision="keep"),
        _review(
            short,
            decision="keep",
            route=PRIMARY_ROUTE_REJECT,
            primary_reason="length_out_of_range",
            proposed_decision="proposed_reject",
        ),
        _review(
            cass,
            decision="keep",
            route=PRIMARY_ROUTE_CONSTRUCT,
            primary_reason="trim_construct_unresolved",
            proposed_decision="proposed_park",
        ),
        _review(
            exc,
            decision="keep",
            route=PRIMARY_ROUTE_CONSTRUCT,
            primary_reason="trim_construct_unresolved",
            proposed_decision="proposed_park",
        ),
        _review(
            ngf,
            decision="keep",
            route=PRIMARY_ROUTE_CONSTRUCT,
            primary_reason="trim_construct_unresolved",
            proposed_decision="proposed_park",
        ),
        _review(
            prom,
            decision="keep",
            route=PRIMARY_ROUTE_CONSTRUCT,
            primary_reason="trim_construct_unresolved",
            proposed_decision="proposed_park",
            source_promoter_or_template_concern="true",
            manual_trim_action="reject",
        ),
        _review(dup_a, decision="keep"),
        _review(dup_b, decision="keep"),
    ]
    decisions = [
        _decision(
            eligible,
            route=PRIMARY_ROUTE_ELIGIBLE,
            reason="technically_eligible_rna",
            proposed="proposed_accept",
        ),
        _decision(
            short,
            route=PRIMARY_ROUTE_REJECT,
            reason="length_out_of_range",
            proposed="proposed_reject",
        ),
        _decision(
            cass,
            route=PRIMARY_ROUTE_CONSTRUCT,
            reason="trim_construct_unresolved",
            proposed="proposed_park",
        ),
        _decision(
            exc,
            route=PRIMARY_ROUTE_CONSTRUCT,
            reason="trim_construct_unresolved",
            proposed="proposed_park",
        ),
        _decision(
            ngf,
            route=PRIMARY_ROUTE_CONSTRUCT,
            reason="trim_construct_unresolved",
            proposed="proposed_park",
        ),
        _decision(
            prom,
            route=PRIMARY_ROUTE_CONSTRUCT,
            reason="trim_construct_unresolved",
            proposed="proposed_park",
        ),
        _decision(
            dup_a,
            route=PRIMARY_ROUTE_ELIGIBLE,
            reason="technically_eligible_rna",
            proposed="proposed_accept",
        ),
        _decision(
            dup_b,
            route=PRIMARY_ROUTE_ELIGIBLE,
            reason="technically_eligible_rna",
            proposed="proposed_accept",
        ),
    ]
    exception_row = {
        "constant_rule_id": three_rule["constant_rule_id"],
        "proposal_id": three_rule["proposal_id"],
        "record_id": exc["record_id"],
        "exception_reason": "non_terminal_match",
        "manual_decision": "keep",
        "manual_trim_action": "override",
        "manual_trim_5p_nt": "",
        "manual_trim_3p_nt": "19",
        "machine_recommendation": "needs_source_review",
    }
    recon = [
        {
            "reconciliation_id": "ena_collapse_01",
            "record_id_a": dup_a["record_id"],
            "record_id_b": dup_b["record_id"],
            "manual_decision": "retain_both",
            "machine_recommendation": "retain_both_through_checkpoint_and_defer_exact_dedup",
            "manual_notes": "",
        }
    ]
    membership = [
        _member(rule=five_rule, canonical=cass),
        _member(rule=three_rule, canonical=cass),
        _member(rule=five_rule, canonical=exc),
        _member(rule=three_rule, canonical=exc),
        _member(rule=ngf_rule, canonical=ngf),
    ]
    proposals = [
        _proposal(group_id="g_cass", side="five_prime", motif=five),
        _proposal(group_id="g_cass", side="three_prime", motif=majority_three20),
        _proposal(group_id="g_ngf", side="five_prime", motif=_flank("ACGU", 12)),
    ]
    qc_rows = [
        _qc(eligible),
        _qc(short),
        _qc(cass, experiment_group_id="g_cass"),
        _qc(exc, experiment_group_id="g_cass"),
        _qc(ngf, experiment_group_id="g_ngf"),
        _qc(prom, source_promoter_or_template_concern="true"),
        _qc(dup_a),
        _qc(dup_b),
    ]
    meta_rows = [
        _meta(eligible),
        _meta(short),
        _meta(cass, experiment_group_id="g_cass"),
        _meta(exc, experiment_group_id="g_cass"),
        _meta(ngf, experiment_group_id="g_ngf"),
        _meta(prom),
        _meta(dup_a),
        _meta(dup_b),
    ]
    checkpoint = _install_mini_ena(
        tmp_path,
        canonical_rows=rows,
        decision_rows=decisions,
        queue_rows=queue,
        qc_rows=qc_rows,
        meta_rows=meta_rows,
        rule_rows=[five_rule, three_rule, ngf_rule],
        membership_rows=membership,
        exception_rows=[exception_row],
        reconciliation_rows=recon,
        proposal_rows=proposals,
    )
    by_id = {row["native_id"]: row for row in rows}
    return checkpoint, by_id


def test_frozen_hash_mismatch_fails(tmp_path: Path) -> None:
    canonical = _canonical(native_id="hash", sequence=_rna(40))
    checkpoint = _install_mini_ena(
        tmp_path,
        canonical_rows=[canonical],
        decision_rows=[
            _decision(
                canonical,
                route=PRIMARY_ROUTE_ELIGIBLE,
                reason="technically_eligible_rna",
                proposed="proposed_accept",
            )
        ],
        queue_rows=[_review(canonical, decision="keep")],
    )
    with pytest.raises(Checkpoint1ApplyError, match="Frozen review hash mismatch"):
        run_ena_checkpoint1_dry_run(
            repo_root=tmp_path,
            checkpoint_dir=checkpoint,
            output_dir=checkpoint / "dry_run",
            check_deterministic_rerun=False,
            expected_total_rows=1,
            verify_frozen_review=True,
            compare_to_pristine=False,
            skip_pipeline_integrity=True,
            expected_review_hashes={
                "ena_checkpoint1_manual_review.csv": "0" * 64,
            },
        )


def test_real_apply_refuses_unresolved_review(tmp_path: Path) -> None:
    canonical = _canonical(native_id="open", sequence=_rna(40))
    checkpoint = _install_mini_ena(
        tmp_path,
        canonical_rows=[canonical],
        decision_rows=[
            _decision(
                canonical,
                route=PRIMARY_ROUTE_ELIGIBLE,
                reason="technically_eligible_rna",
                proposed="proposed_accept",
            )
        ],
        queue_rows=[_review(canonical, decision="")],
    )
    with pytest.raises(Checkpoint1ApplyError, match="unresolved|not ready|Invalid"):
        run_ena_checkpoint1_apply(
            repo_root=tmp_path,
            checkpoint_dir=checkpoint,
            output_dir=checkpoint / "resolved",
            tracked_manifest=(
                tmp_path / "config" / "checkpoint_reviews" / "ena_checkpoint1_resolutions.csv"
            ),
            metadata_out=(
                tmp_path / "config" / "checkpoint_reviews" / "ena_checkpoint1_metadata.json"
            ),
            check_deterministic_rerun=False,
            expected_total_rows=1,
            verify_frozen_review=False,
            compare_to_pristine=False,
            skip_pipeline_integrity=True,
            compare_to_preview=False,
        )


def test_real_apply_refuses_altered_frozen_review(tmp_path: Path) -> None:
    canonical = _canonical(native_id="alt", sequence=_rna(40))
    checkpoint = _install_mini_ena(
        tmp_path,
        canonical_rows=[canonical],
        decision_rows=[
            _decision(
                canonical,
                route=PRIMARY_ROUTE_ELIGIBLE,
                reason="technically_eligible_rna",
                proposed="proposed_accept",
            )
        ],
        queue_rows=[_review(canonical, decision="keep")],
    )
    with pytest.raises(Checkpoint1ApplyError, match="Frozen review hash mismatch"):
        run_ena_checkpoint1_apply(
            repo_root=tmp_path,
            checkpoint_dir=checkpoint,
            output_dir=checkpoint / "resolved",
            tracked_manifest=(
                tmp_path / "config" / "checkpoint_reviews" / "ena_checkpoint1_resolutions.csv"
            ),
            metadata_out=(
                tmp_path / "config" / "checkpoint_reviews" / "ena_checkpoint1_metadata.json"
            ),
            check_deterministic_rerun=False,
            expected_total_rows=1,
            verify_frozen_review=True,
            compare_to_pristine=False,
            skip_pipeline_integrity=True,
            compare_to_preview=False,
            expected_review_hashes={
                "ena_checkpoint1_manual_review.csv": "0" * 64,
            },
        )


def test_ena_live_apply_matches_dry_run_and_closes(tmp_path: Path) -> None:
    import json

    from common.corpus_schema import S3_FORBIDDEN_FIELDS

    checkpoint, _by_id = _live_ena_fixture(tmp_path)
    preview_dir = checkpoint / "dry_run"
    run_ena_checkpoint1_dry_run(
        repo_root=tmp_path,
        checkpoint_dir=checkpoint,
        output_dir=preview_dir,
        check_deterministic_rerun=True,
        expected_total_rows=8,
        verify_frozen_review=False,
        compare_to_pristine=False,
        skip_pipeline_integrity=True,
    )
    preview_canonical = preview_dir / "ena_checkpoint1_dry_run_canonical_preview.csv"
    preview_hash = hashlib.sha256(preview_canonical.read_bytes()).hexdigest()
    s3_hash = hashlib.sha256((checkpoint / "ena_s3_canonical.csv").read_bytes()).hexdigest()

    result = run_ena_checkpoint1_apply(
        repo_root=tmp_path,
        checkpoint_dir=checkpoint,
        output_dir=checkpoint / "resolved",
        tracked_manifest=(
            tmp_path / "config" / "checkpoint_reviews" / "ena_checkpoint1_resolutions.csv"
        ),
        metadata_out=(
            tmp_path / "config" / "checkpoint_reviews" / "ena_checkpoint1_metadata.json"
        ),
        preview_dir=preview_dir,
        check_deterministic_rerun=True,
        expected_total_rows=8,
        verify_frozen_review=False,
        compare_to_pristine=False,
        skip_pipeline_integrity=True,
        compare_to_preview=True,
    )
    applied_canonical = checkpoint / "resolved" / "ena_checkpoint1_applied_canonical.csv"
    applied_routing = checkpoint / "resolved" / "ena_checkpoint1_applied_routing.csv"
    assert result.checkpoint_closed is True
    assert result.preview_comparison_ok is True
    assert result.deterministic_rerun_ok is True
    assert result.semantic_mismatches == 0
    assert applied_canonical.read_bytes() == preview_canonical.read_bytes()
    assert hashlib.sha256(preview_canonical.read_bytes()).hexdigest() == preview_hash
    assert (
        hashlib.sha256((checkpoint / "ena_s3_canonical.csv").read_bytes()).hexdigest()
        == s3_hash
    )
    assert all(result.byte_identical.values())
    eligible_n = int(result.stats["technically_eligible"])
    parked_n = int(result.stats["parked_construct_review"])
    reject_n = int(result.stats["technical_rejects"])
    total_n = int(result.stats["total_records"])
    assert eligible_n + parked_n + reject_n == total_n
    assert result.stats["authorised_for_s4"] == eligible_n
    assert parked_n == 0
    assert reject_n == 1
    assert int(result.stats["records_trimmed"]) == 2
    assert int(result.stats["trimmed_both_ends"]) == 2
    assert int(result.stats["large_trim_human_approved"]) == 2
    assert int(result.stats["guard_rail_failures"]) == 0
    assert int(result.stats["unresolved_after_consumption"]) == 0
    assert int(result.stats["collapse_retained"]) == 2

    with applied_canonical.open(newline="", encoding="utf-8") as handle:
        applied_rows = {row["native_id"]: row for row in csv.DictReader(handle)}
    assert applied_rows["cass"]["sequence_length_core"] == "41"
    assert applied_rows["exc"]["sequence_length_core"] == "41"
    assert applied_rows["cass"]["trim_confidence"] == "medium"
    assert applied_rows["ngf"]["sequence_core"] == applied_rows["ngf"]["sequence_full"]
    assert applied_rows["prom"]["sequence_core"] == applied_rows["prom"]["sequence_full"]
    assert applied_rows["short"]["sequence_length_core"] == "15"
    for row in applied_rows.values():
        for field_name in S3_FORBIDDEN_FIELDS:
            assert row.get(field_name, "") == ""

    with applied_routing.open(newline="", encoding="utf-8") as handle:
        routes = {row["native_id"]: row for row in csv.DictReader(handle)}
    assert routes["ok"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["cass"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["exc"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["ngf"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["prom"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["dup_a"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["dup_b"]["primary_route"] == PRIMARY_ROUTE_ELIGIBLE
    assert routes["short"]["primary_route"] == PRIMARY_ROUTE_REJECT
    assert routes["short"]["primary_reason"] == "length_out_of_range"

    resolutions_path = (
        tmp_path / "config" / "checkpoint_reviews" / "ena_checkpoint1_resolutions.csv"
    )
    metadata_path = (
        tmp_path / "config" / "checkpoint_reviews" / "ena_checkpoint1_metadata.json"
    )
    with resolutions_path.open(newline="", encoding="utf-8") as handle:
        resolution_rows = list(csv.DictReader(handle))
    assert list(resolution_rows[0].keys()) == list(ENA_TRACKED_RESOLUTION_COLUMNS)
    joined = " ".join(resolution_rows[0].keys())
    for fragment in TRACKED_SEQUENCE_COLUMN_FRAGMENTS:
        assert fragment not in joined
    for row in resolution_rows:
        assert "pending_checkpoint_1_review" not in row["checkpoint1_resolution_status"]
        if row["native_id"] == "short":
            assert row["authorised_for_s4"] == "false"
            assert row["checkpoint1_resolution_status"] == "rejected_after_checkpoint1"
        else:
            assert row["authorised_for_s4"] == "true"
            assert row["checkpoint1_resolution_status"] == "approved_for_s4"
        for value in row.values():
            assert "ACGU" not in value
            assert "UGCA" not in value
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["checkpoint_closed"] is True
    assert metadata["s4_started"] is False
    assert metadata["global_s4_handoff_prepared"] is False
    assert metadata["global_s4_run"] is False
    assert metadata["source_key"] == "ena"
    assert metadata["application_mode"] == "apply"
    assert metadata["preview_comparison_ok"] is True
    assert metadata["authorised_for_s4"] == eligible_n
    assert AUTHORISED_FOR_S4_MEANING in metadata["authorised_for_s4_meaning"]
    assert metadata["next_stage"] == "review_ena_closure_before_global_s4_handoff"
    metadata_text = json.dumps(metadata)
    assert "ACGU" not in metadata_text
    assert "sequence_raw" not in metadata
    assert "sequence_full" not in metadata
    assert not (tmp_path / "config" / "global_s4_sources" / "ena.json").exists()
    assert not (
        tmp_path / "data" / "interim" / "global_s4_ready" / "ena_global_s4_input.csv"
    ).exists()
    summary = (checkpoint / "resolved" / "ena_checkpoint1_resolution_summary.md").read_text(
        encoding="utf-8"
    )
    assert "CHECKPOINT-1 CLOSED" in summary
    assert "ACGU" not in summary


def test_cli_runs_real_ena_apply(tmp_path: Path) -> None:
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO

    canonical = _canonical(native_id="cli", sequence=_rna(40))
    _install_mini_ena(
        tmp_path,
        canonical_rows=[canonical],
        decision_rows=[
            _decision(
                canonical,
                route=PRIMARY_ROUTE_ELIGIBLE,
                reason="technically_eligible_rna",
                proposed="proposed_accept",
            )
        ],
        queue_rows=[_review(canonical, decision="keep")],
    )
    err = StringIO()
    out = StringIO()
    with redirect_stderr(err), redirect_stdout(out):
        rc = main(
            [
                "--source",
                "ena",
                "--repo-root",
                str(tmp_path),
                "--skip-pipeline-integrity",
                "--expected-total-rows",
                "1",
                "--skip-deterministic-rerun",
            ]
        )
    assert rc == 0, err.getvalue()
    assert "CHECKPOINT-1 CLOSED" in out.getvalue()
    assert "mode=apply" in out.getvalue()
    assert (
        tmp_path / "data" / "interim" / "checkpoints" / "ena_cp1" / "resolved"
        / "ena_checkpoint1_applied_canonical.csv"
    ).is_file()
    assert (
        tmp_path / "config" / "checkpoint_reviews" / "ena_checkpoint1_metadata.json"
    ).is_file()

"""AptaIndex CHECKPOINT-1 apply/dry-run tests (synthetic sequences only).

Literal nucleotides are repeating ACGU/ACGT tiles or short chemical-looking
tokens. Does not read or embed real AptaIndex sequences.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptaindex_checkpoint1_dry_run import (  # noqa: E402
    simulate_aptaindex_checkpoint1_application,
)
from adapters.aptaindex_checkpoint1_review import (  # noqa: E402
    AptaIndexCheckpoint1ReviewError,
    apply_aptaindex_checkpoint1_package,
    apply_reviewed_record,
    mapping_class_for_resolved_state,
)
from adapters.aptaindex_s3 import (  # noqa: E402
    PRIMARY_ROUTE_CHEMISTRY_REVIEW,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
)
from checkpoint1_apply_review import main  # noqa: E402
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import load_eligibility_policy  # noqa: E402
from common.sequence_normalisation import normalise_sequence  # noqa: E402

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "aptaindex.json"
)
CHEMICAL_RAW = "rArCrG{5'/Phosphate}"


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
    alphabet: str = "chemical_notation",
    qc_flags: str = "",
    sequence_raw: str | None = None,
    **overrides: str,
) -> dict[str, str]:
    sequence = sequence or _rna(40)
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"aptaindex:{native_id}",
            "sequence_raw": sequence_raw if sequence_raw is not None else CHEMICAL_RAW,
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
            "target_name_raw": "demo_target",
            "source_db": "aptaindex",
            "source_dataset": "aptaindex_export_2026-07-22",
            "contributing_sources": "aptaindex",
            "contributing_datasets": "aptaindex_export_2026-07-22",
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
    mapping_class: str = "straightforward_rna",
    parser_status: str = "success",
    source_type: str = "RNA",
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "source_type": source_type,
        "parser_status": parser_status,
        "parser_reason_category": "",
        "mapping_class": mapping_class,
        "token_family_summary": "r",
        "has_l_prefix": "false",
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical["chemistry"],
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "construct_scope": canonical["construct_scope"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical["trim_confidence"],
        "qc_flags": canonical["qc_flags"],
        "t_to_u_applied": canonical["t_to_u_applied"],
        "mixed_t_u": "false",
    }


def _meta(canonical: dict[str, str], *, aptaindex_type: str = "RNA") -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "aptaindex_native_id": canonical["native_id"],
        "aptaindex_title": f"title-{canonical['native_id']}",
        "aptaindex_type": aptaindex_type,
        "aptaindex_target": canonical["target_name_raw"],
        "aptaindex_target_type": "Protein",
        "aptaindex_affinity_type": "",
        "aptaindex_affinity": "",
        "aptaindex_affinity_units": "",
        "aptaindex_reference": "Demo",
    }


def _review(
    canonical: dict[str, str],
    *,
    decision: str = "keep",
    route: str = PRIMARY_ROUTE_ELIGIBLE,
    reason: str = "technically_eligible_rna",
    proposed: str = "proposed_accept",
    **overrides: str,
) -> dict[str, str]:
    row = {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "primary_route": route,
        "proposed_decision": proposed,
        "primary_reason": reason,
        "secondary_reasons": "",
        "checkpoint_review_reasons": "judgement_dependent_technical",
        "audit_only_row": "false",
        "constant_group_id": "",
        "constant_proposal_sources": "",
        "constant_proposal_sides": "",
        "constant_proposed_trim_length": "",
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
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical["chemistry"],
        "aptaindex_type": "RNA",
        "mapping_class": "straightforward_rna",
        "sequence_length_core": canonical["sequence_length_core"],
    }
    row.update(overrides)
    return row


def _decision_row(
    canonical: dict[str, str],
    *,
    route: str,
    reason: str,
) -> dict[str, str]:
    if route == PRIMARY_ROUTE_ELIGIBLE:
        proposed = "proposed_accept"
    elif route == PRIMARY_ROUTE_REJECT:
        proposed = "proposed_reject"
    else:
        proposed = "proposed_park"
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "primary_route": route,
        "proposed_decision": proposed,
        "primary_reason": reason,
        "secondary_reasons": "",
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical["chemistry"],
        "mapping_class": "",
        "notes": "",
        "sequence_length_core": canonical["sequence_length_core"],
        "sequence_length_full": canonical["sequence_length_full"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical["trim_confidence"],
        "qc_flags": canonical["qc_flags"],
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "manual_review_required": "true",
        "manual_review_priority": "high",
        "review_batch": "01_judgement_dependent_technical",
        "checkpoint_review_reasons": "judgement_dependent_technical",
        "checkpoint_status": "pending_checkpoint_1_review",
        "aptamer_name": "",
        "target_name_raw": canonical["target_name_raw"],
        "construct_scope": canonical["construct_scope"],
        "aptaindex_type": "RNA",
        "aptaindex_target_type": "",
        "parser_status": "success",
        "parser_reason_category": "",
        "token_family_summary": "",
        "has_l_prefix": "false",
        "judgement_subcategory": "",
        "constant_proposal_ids": "",
        "constant_proposal_sources": "",
        "constant_proposal_sides": "",
        "constant_group_id": "",
        "constant_records_in_group": "",
        "constant_support": "",
        "constant_proposed_trim_length": "",
    }


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


def test_dispatcher_recognises_aptaindex_dry_run(tmp_path: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "aptaindex",
                "--dry-run",
                "--repo-root",
                str(tmp_path),
            ]
        )
    assert code == 1
    message = stderr.getvalue()
    assert "Missing dry-run input" in message or "does not exist" in message


def test_dispatcher_refuses_actual_apply_without_dry_run() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(["--source", "aptaindex"])
    assert code == 1
    assert "pass --dry-run" in stderr.getvalue()


def test_dry_run_accepts_fully_resolved_review() -> None:
    eligible = _canonical(native_id="1001")
    parked = _canonical(
        native_id="1002",
        sequence=_dna(40),
        molecule_type="ssDNA",
        chemistry="DNA",
    )
    queue = [
        _review(eligible, decision="keep"),
        _review(
            parked,
            decision="keep",
            route=PRIMARY_ROUTE_SSDNA,
            reason="ssdna_parked",
            proposed="proposed_park",
        ),
    ]
    rows = [eligible, parked]
    simulation = simulate_aptaindex_checkpoint1_application(
        queue_rows=queue,
        group_rows=[],
        canonical_rows=rows,
        decision_rows=[
            _decision_row(
                eligible, route=PRIMARY_ROUTE_ELIGIBLE, reason="technically_eligible_rna"
            ),
            _decision_row(parked, route=PRIMARY_ROUTE_SSDNA, reason="ssdna_parked"),
        ],
        source_metadata_by_id={row["record_id"]: _meta(row) for row in rows},
        s2_qc_by_id={
            eligible["record_id"]: _qc(eligible),
            parked["record_id"]: _qc(
                parked, mapping_class="straightforward_dna", source_type="DNA"
            ),
        },
        policy=POLICY,
        expected_source_rows=2,
    )
    assert simulation.stats["decisions_consumed"] == 2
    assert simulation.stats["unconsumed_decisions"] == 0
    assert simulation.stats["keep_unexpected_route_changes"] == 0


def test_chemical_raw_is_not_passed_to_generic_normalisation() -> None:
    canonical = _canonical(native_id="2001", sequence_raw=CHEMICAL_RAW)
    review = _review(canonical, decision="keep")
    with patch(
        "adapters.aptaindex_checkpoint1_review.normalise_sequence",
        wraps=normalise_sequence,
    ) as mocked:
        result = _apply(canonical, review)
    mocked.assert_not_called()
    assert result.sequence_raw == CHEMICAL_RAW
    assert result.sequence_full == canonical["sequence_full"]
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_no_manual_correction_uses_s2_nucleotide_sequence() -> None:
    s2_seq = _rna(40)
    canonical = _canonical(
        native_id="2002",
        sequence=s2_seq,
        sequence_raw=CHEMICAL_RAW,
    )
    review = _review(
        canonical,
        decision="edit",
        manual_chemistry_override="2F-RNA",
        manual_molecule_type_override="RNA",
    )
    with patch(
        "adapters.aptaindex_checkpoint1_review.normalise_sequence",
        wraps=normalise_sequence,
    ) as mocked:
        result = _apply(
            canonical,
            review,
            qc=_qc(canonical, mapping_class="type_token_disagreement"),
        )
    mocked.assert_not_called()
    assert result.sequence_full == s2_seq
    assert result.sequence_raw == CHEMICAL_RAW
    assert result.chemistry == "2F-RNA"
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_manual_corrected_sequence_uses_corrected_nucleotide() -> None:
    corrected = _rna(40)
    canonical = _canonical(
        native_id="2003",
        sequence=_rna(36),
        sequence_raw=CHEMICAL_RAW,
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="unsupported_notation|molecule_type_unknown",
        sequence_full="",
        sequence_core="",
        sequence_length_full="",
        sequence_length_core="",
    )
    review = _review(
        canonical,
        decision="edit",
        route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
        reason="unsupported_chemical_notation",
        proposed="proposed_park",
        manual_sequence_corrected=corrected,
        manual_molecule_type_override="RNA",
        manual_chemistry_override="RNA",
    )
    with patch(
        "adapters.aptaindex_checkpoint1_review.normalise_sequence",
        wraps=normalise_sequence,
    ) as mocked:
        result = _apply(
            canonical,
            review,
            qc=_qc(
                canonical,
                mapping_class="unsupported_notation",
                parser_status="unsupported",
            ),
        )
    mocked.assert_called()
    assert mocked.call_args.args[0] == corrected
    assert mocked.call_args.args[0] != CHEMICAL_RAW
    assert result.sequence_raw == CHEMICAL_RAW
    assert result.sequence_full == corrected
    assert result.sequence_length_core == 40
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_molecule_override_supersedes_stale_mapping_class() -> None:
    seq = _rna(40)
    canonical = _canonical(
        native_id="2004",
        sequence=seq,
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="molecule_type_unknown|source_type_token_disagreement",
    )
    review = _review(
        canonical,
        decision="edit",
        route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
        reason="source_type_token_disagreement",
        proposed="proposed_park",
        manual_molecule_type_override="RNA",
        manual_chemistry_override="RNA",
    )
    result = _apply(
        canonical,
        review,
        qc=_qc(canonical, mapping_class="type_token_disagreement"),
    )
    assert result.molecule_type == "RNA"
    assert result.chemistry == "RNA"
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    assert result.decision["mapping_class"] == "straightforward_rna"


def test_chemistry_override_supersedes_stale_mapping_class() -> None:
    seq = _rna(40)
    canonical = _canonical(
        native_id="2005",
        sequence=seq,
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="molecule_type_unknown|mixed_token_chemistry",
    )
    review = _review(
        canonical,
        decision="edit",
        route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
        reason="source_type_token_disagreement",
        proposed="proposed_park",
        manual_molecule_type_override="RNA",
        manual_chemistry_override="2F-RNA",
    )
    result = _apply(
        canonical,
        review,
        qc=_qc(canonical, mapping_class="type_token_disagreement"),
        meta=_meta(canonical, aptaindex_type="Chimeric"),
    )
    assert result.chemistry == "2F-RNA"
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    assert result.decision["mapping_class"] == "straightforward_2f_rna"
    assert mapping_class_for_resolved_state("RNA", "2F-RNA") == "straightforward_2f_rna"


def test_keep_eligible_rna_preserves_route() -> None:
    canonical = _canonical(native_id="2006")
    result = _apply(canonical, _review(canonical, decision="keep"))
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    assert result.sequence_full == canonical["sequence_full"]
    assert "checkpoint1_manual_decision=keep" in result.notes


def test_keep_parked_ssdna_preserves_ssdna_park() -> None:
    canonical = _canonical(
        native_id="2007",
        sequence=_dna(40),
        molecule_type="ssDNA",
        chemistry="DNA",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="keep",
            route=PRIMARY_ROUTE_SSDNA,
            reason="ssdna_parked",
            proposed="proposed_park",
        ),
        qc=_qc(canonical, mapping_class="straightforward_dna", source_type="DNA"),
        meta=_meta(canonical, aptaindex_type="DNA"),
    )
    assert result.primary_route_after == PRIMARY_ROUTE_SSDNA
    assert result.molecule_type == "ssDNA"


def test_keep_chemistry_review_preserves_chemistry_park() -> None:
    canonical = _canonical(
        native_id="2008",
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="l_nucleotide_syntax|molecule_type_unknown",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="keep",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="l_rna_stereochemistry",
            proposed="proposed_park",
        ),
        qc=_qc(canonical, mapping_class="l_rna", source_type="L-RNA"),
        meta=_meta(canonical, aptaindex_type="L-RNA"),
    )
    assert result.primary_route_after == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    assert result.molecule_type == "unknown"


def test_drop_becomes_manual_reject() -> None:
    canonical = _canonical(native_id="2009")
    result = _apply(
        canonical,
        _review(canonical, decision="drop", route=PRIMARY_ROUTE_ELIGIBLE),
    )
    assert result.primary_route_after == PRIMARY_ROUTE_REJECT
    assert result.primary_reason == "manual_reject"
    assert result.rejection_row is not None
    assert result.rejection_row["rejection_reason"] == "manual_reject"
    assert "checkpoint1_manual_decision=drop" in result.notes
    assert result.park_row is None


def test_edited_ssdna_reparks() -> None:
    canonical = _canonical(
        native_id="2010",
        sequence=_dna(40),
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="unsupported_notation|molecule_type_unknown",
        sequence_full="",
        sequence_core="",
        sequence_length_full="",
        sequence_length_core="",
    )
    review = _review(
        canonical,
        decision="edit",
        route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
        reason="unsupported_chemical_notation",
        proposed="proposed_park",
        manual_sequence_corrected=_dna(48),
        manual_molecule_type_override="ssDNA",
        manual_chemistry_override="DNA",
    )
    result = _apply(
        canonical,
        review,
        qc=_qc(
            canonical,
            mapping_class="unsupported_notation",
            parser_status="unsupported",
            source_type="DNA",
        ),
        meta=_meta(canonical, aptaindex_type="DNA"),
    )
    assert result.molecule_type == "ssDNA"
    assert result.chemistry == "DNA"
    assert result.sequence_length_core == 48
    assert result.primary_route_after == PRIMARY_ROUTE_SSDNA


def test_edited_straightforward_rna_becomes_eligible() -> None:
    canonical = _canonical(
        native_id="2011",
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="molecule_type_unknown|source_type_token_disagreement",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="source_type_token_disagreement",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="RNA",
        ),
        qc=_qc(canonical, mapping_class="type_token_disagreement"),
    )
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_edited_2f_rna_becomes_eligible() -> None:
    canonical = _canonical(
        native_id="2012",
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="mixed_token_chemistry|molecule_type_unknown",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="source_type_token_disagreement",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="2F-RNA",
        ),
        qc=_qc(canonical, mapping_class="mixed_token_chemistry"),
        meta=_meta(canonical, aptaindex_type="2'-F-RNA"),
    )
    assert result.chemistry == "2F-RNA"
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_edited_2nh2_rna_follows_chemistry_review_policy() -> None:
    canonical = _canonical(
        native_id="2013",
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="mixed_token_chemistry|molecule_type_unknown",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="source_type_token_disagreement",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="2NH2-RNA",
        ),
        qc=_qc(canonical, mapping_class="mixed_token_chemistry"),
    )
    assert result.chemistry == "2NH2-RNA"
    assert result.primary_route_after == PRIMARY_ROUTE_CHEMISTRY_REVIEW
    assert result.decision["mapping_class"] == "type_token_disagreement"


def test_edited_2ome_rna_follows_chemistry_review_policy() -> None:
    canonical = _canonical(
        native_id="2014",
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="molecule_type_unknown",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="source_type_token_disagreement",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="2OMe-RNA",
        ),
        qc=_qc(canonical, mapping_class="type_token_disagreement"),
    )
    assert result.chemistry == "2OMe-RNA"
    assert result.primary_route_after == PRIMARY_ROUTE_CHEMISTRY_REVIEW


def test_edited_mixed_rna_follows_chemistry_review_policy() -> None:
    canonical = _canonical(
        native_id="2015",
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="molecule_type_unknown",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="chimeric_molecule",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="mixed",
        ),
        qc=_qc(canonical, mapping_class="chimeric"),
        meta=_meta(canonical, aptaindex_type="Chimeric"),
    )
    assert result.chemistry == "mixed"
    assert result.primary_route_after == PRIMARY_ROUTE_CHEMISTRY_REVIEW


@pytest.mark.parametrize(
    ("length", "expected_route", "expected_reason"),
    [
        (19, PRIMARY_ROUTE_REJECT, "length_out_of_range"),
        (20, PRIMARY_ROUTE_ELIGIBLE, "technically_eligible_rna"),
        (100, PRIMARY_ROUTE_ELIGIBLE, "technically_eligible_rna"),
        (101, PRIMARY_ROUTE_REJECT, "length_out_of_range"),
    ],
)
def test_corrected_length_uses_current_20_100_policy(
    length: int, expected_route: str, expected_reason: str
) -> None:
    canonical = _canonical(
        native_id=f"3{length:03d}",
        sequence="",
        molecule_type="unknown",
        chemistry="unknown",
        sequence_full="",
        sequence_core="",
        sequence_length_full="",
        sequence_length_core="",
        qc_flags="unsupported_notation|molecule_type_unknown",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="unsupported_chemical_notation",
            proposed="proposed_park",
            manual_sequence_corrected=_rna(length),
            manual_molecule_type_override="RNA",
            manual_chemistry_override="2F-RNA",
        ),
        qc=_qc(
            canonical,
            mapping_class="unsupported_notation",
            parser_status="unsupported",
        ),
    )
    assert result.sequence_length_core == length
    assert result.molecule_type == "RNA"
    assert result.chemistry == "2F-RNA"
    assert result.primary_route_after == expected_route
    assert result.primary_reason == expected_reason


def test_corrected_mature_sequence_plus_trim_reject_has_no_additional_trim() -> None:
    mature = _rna(51)
    canonical = _canonical(
        native_id="0187",
        sequence=_rna(68),
        sequence_raw=CHEMICAL_RAW,
        qc_flags="known_promoter_detected|trim_requires_review",
    )
    review = _review(
        canonical,
        decision="edit",
        manual_sequence_corrected=mature,
        manual_molecule_type_override="RNA",
        manual_chemistry_override="2F-RNA",
        manual_trim_action="reject",
        constant_proposal_sources="known_motif",
        constant_proposal_sides="five_prime",
        constant_proposed_trim_length="17",
    )
    result = _apply(
        canonical,
        review,
        machine_five=17,
        proposals=[
            {
                "proposal_id": "aptaindex:0187:known_motif:five_prime:t7_promoter_minimal",
                "experiment_group_id": "aptaindex:0187",
                "proposal_source": "known_motif",
                "side": "five_prime",
                "motif_length": "17",
            }
        ],
    )
    assert result.sequence_length_core == 51
    assert result.applied_trim_5p_nt == 0
    assert result.applied_trim_3p_nt == 0
    assert "no_additional_trim" in result.notes
    assert result.primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_trim_approve_applies_shared_numeric_trim() -> None:
    full = _rna(40)
    canonical = _canonical(native_id="2016", sequence=full)
    review = _review(
        canonical,
        decision="edit",
        manual_trim_action="approve",
        constant_proposal_sources="known_motif",
        constant_proposal_sides="five_prime",
        constant_proposed_trim_length="5",
    )
    result = _apply(canonical, review, machine_five=5)
    assert result.applied_trim_5p_nt == 5
    assert result.sequence_length_core == 35
    assert result.sequence_core == full[5:]
    assert result.sequence_raw == CHEMICAL_RAW


def test_drop_with_blank_trim_is_valid() -> None:
    canonical = _canonical(native_id="0276")
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="drop",
            constant_proposed_trim_length="17",
            constant_proposal_sides="five_prime",
        ),
        machine_five=17,
    )
    assert result.primary_route_after == PRIMARY_ROUTE_REJECT
    assert result.applied_trim_5p_nt == 0
    assert result.sequence_full == canonical["sequence_full"]


def test_s4_forbidden_fields_remain_empty() -> None:
    canonical = _canonical(native_id="2017")
    for field_name in S3_FORBIDDEN_FIELDS:
        canonical[field_name] = ""
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            manual_chemistry_override="RNA",
            manual_molecule_type_override="RNA",
        ),
    )
    for field_name in S3_FORBIDDEN_FIELDS:
        assert result.canonical.get(field_name, "") == ""


def test_no_human_decision_silently_disappears() -> None:
    eligible = _canonical(native_id="2018")
    dropped = _canonical(native_id="2019")
    edited = _canonical(
        native_id="2020",
        molecule_type="unknown",
        chemistry="unknown",
        qc_flags="molecule_type_unknown",
    )
    queue = [
        _review(eligible, decision="keep"),
        _review(dropped, decision="drop"),
        _review(
            edited,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="source_type_token_disagreement",
            proposed="proposed_park",
            manual_molecule_type_override="RNA",
            manual_chemistry_override="RNA",
        ),
    ]
    rows = [eligible, dropped, edited]
    applied, report = apply_aptaindex_checkpoint1_package(
        queue_rows=queue,
        group_rows=[],
        canonical_by_id={row["record_id"]: row for row in rows},
        source_metadata_by_id={row["record_id"]: _meta(row) for row in rows},
        s2_qc_by_id={
            eligible["record_id"]: _qc(eligible),
            dropped["record_id"]: _qc(dropped),
            edited["record_id"]: _qc(edited, mapping_class="type_token_disagreement"),
        },
        policy=POLICY,
    )
    assert report.ok is True
    assert {item.record_id for item in applied} == {row["record_id"] for row in rows}
    by_id = {item.record_id: item for item in applied}
    assert by_id[eligible["record_id"]].primary_route_after == PRIMARY_ROUTE_ELIGIBLE
    assert by_id[dropped["record_id"]].primary_reason == "manual_reject"
    assert by_id[edited["record_id"]].primary_route_after == PRIMARY_ROUTE_ELIGIBLE


def test_dry_run_is_deterministic() -> None:
    canonical = _canonical(native_id="2021")
    extra = _canonical(
        native_id="2022",
        sequence=_dna(40),
        molecule_type="ssDNA",
        chemistry="DNA",
    )
    queue = [_review(canonical, decision="keep")]
    kwargs = {
        "queue_rows": queue,
        "group_rows": [],
        "canonical_rows": [canonical, extra],
        "decision_rows": [
            _decision_row(
                canonical,
                route=PRIMARY_ROUTE_ELIGIBLE,
                reason="technically_eligible_rna",
            ),
            _decision_row(extra, route=PRIMARY_ROUTE_SSDNA, reason="ssdna_parked"),
        ],
        "source_metadata_by_id": {
            canonical["record_id"]: _meta(canonical),
            extra["record_id"]: _meta(extra, aptaindex_type="DNA"),
        },
        "s2_qc_by_id": {
            canonical["record_id"]: _qc(canonical),
            extra["record_id"]: _qc(
                extra, mapping_class="straightforward_dna", source_type="DNA"
            ),
        },
        "policy": POLICY,
        "expected_source_rows": 2,
    }
    first = simulate_aptaindex_checkpoint1_application(**kwargs)
    second = simulate_aptaindex_checkpoint1_application(**kwargs)
    assert first.preview_decisions == second.preview_decisions
    assert first.change_report == second.change_report
    assert first.stats == second.stats
    assert first.stats["total_records"] == 2
    assert first.stats["unaffected_records"] == 1


def test_source_type_fallback_for_dna_without_override() -> None:
    canonical = _canonical(
        native_id="0412",
        sequence="",
        molecule_type="unknown",
        chemistry="unknown",
        sequence_full="",
        sequence_core="",
        sequence_length_full="",
        sequence_length_core="",
        qc_flags="unsupported_notation|molecule_type_unknown",
    )
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="unsupported_chemical_notation",
            proposed="proposed_park",
            manual_sequence_corrected=_dna(40),
            aptaindex_type="DNA",
        ),
        qc=_qc(
            canonical,
            mapping_class="unsupported_notation",
            parser_status="unsupported",
            source_type="DNA",
        ),
        meta=_meta(canonical, aptaindex_type="DNA"),
    )
    assert result.molecule_type == "ssDNA"
    assert result.chemistry == "DNA"
    assert result.primary_route_after == PRIMARY_ROUTE_SSDNA


def test_chemical_looking_correction_is_not_reparsed_as_aptaindex_notation() -> None:
    """Human corrections are nucleotide input, even if they still look chemical."""
    canonical = _canonical(
        native_id="2024",
        sequence="",
        molecule_type="unknown",
        chemistry="unknown",
        sequence_full="",
        sequence_core="",
        sequence_length_full="",
        sequence_length_core="",
        qc_flags="unsupported_notation",
        sequence_raw=CHEMICAL_RAW,
    )
    # Synthetic phosphate-like tokens; not a real AptaIndex sequence.
    # ``d`` is avoided because uppercase ``D`` is an IUPAC ambiguity code.
    tokenish = "pApCpGpT" * 8
    result = _apply(
        canonical,
        _review(
            canonical,
            decision="edit",
            route=PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            reason="unsupported_chemical_notation",
            proposed="proposed_park",
            manual_sequence_corrected=tokenish,
            aptaindex_type="DNA",
        ),
        qc=_qc(
            canonical,
            mapping_class="unsupported_notation",
            parser_status="unsupported",
            source_type="DNA",
        ),
        meta=_meta(canonical, aptaindex_type="DNA"),
    )
    assert result.sequence_raw == CHEMICAL_RAW
    assert result.molecule_type == "ssDNA"
    assert result.chemistry == "DNA"
    assert result.primary_route_after == PRIMARY_ROUTE_REJECT
    assert result.primary_reason == "invalid_alphabet"
    assert result.sequence_full != ""
    assert "rA" not in result.sequence_full


def test_preview_csv_roundtrip_preserves_embedded_cr(tmp_path: Path) -> None:
    import csv

    from common.corpus_schema import CORPUS_COLUMNS, write_corpus_csv_atomic

    canonical = _canonical(
        native_id="2025",
        sequence_raw=CHEMICAL_RAW + "\r" + "rU",
    )
    path = tmp_path / "preview.csv"
    write_corpus_csv_atomic(
        path, [canonical], columns=CORPUS_COLUMNS, quoting=csv.QUOTE_ALL
    )
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["record_id"] == canonical["record_id"]
    assert rows[0]["sequence_raw"] == canonical["sequence_raw"]
    assert rows[0]["molecule_type"] == "RNA"


def test_unresolved_edit_fails_closed() -> None:
    canonical = _canonical(native_id="2023")
    with pytest.raises(AptaIndexCheckpoint1ReviewError):
        _apply(canonical, _review(canonical, decision=""))

"""Tests for the AptaDiff S3 eligibility adapter (synthetic sequences only).

Tracked tests never embed real AptaDiff sequence values.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptadiff import SIDECAR_COLUMNS  # noqa: E402
from adapters.aptadiff_s2 import S2_QC_COLUMNS  # noqa: E402
from adapters.aptadiff_s3 import (  # noqa: E402
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    PRIMARY_ROUTE_SSDNA,
    apply_random_accept_audit,
    classify_aptadiff_record,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import (  # noqa: E402
    EligibilityDecision,
    EligibilityReason,
    load_eligibility_policy,
)

POLICY_A = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "aptadiff_a.json"
)
POLICY_B = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "aptadiff_b.json"
)

SYNTHETIC_DNA_36 = "ACGT" * 9
SYNTHETIC_N_36 = ("ACGT" * 8) + "ACGN"


def _s2(
    *,
    source_key: str = "aptadiff_a",
    native_id: str = "00001",
    sequence: str = SYNTHETIC_DNA_36,
    molecule_type: str = "ssDNA",
    alphabet: str = "DNA_T",
    chemistry: str = "DNA",
    qc_flags: str = "",
    target_name_raw: str = "",
    **overrides: str,
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"{source_key}:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": "random_region_only" if sequence else "unknown",
            "trim_status": "no_constants_detected" if sequence else "not_applicable",
            "trim_confidence": "n/a",
            "molecule_type": molecule_type if sequence else "unknown",
            "alphabet_as_reported": alphabet if sequence else "missing",
            "t_to_u_applied": "false",
            "chemistry": chemistry if sequence else "unknown",
            "target_name_raw": target_name_raw,
            "source_db": source_key,
            "source_dataset": f"{source_key}_demo",
            "contributing_sources": source_key,
            "contributing_datasets": f"{source_key}_demo",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": native_id,
            "qc_flags": qc_flags,
        }
    )
    record.update(overrides)
    return record


def _qc(canonical: dict[str, str], *, p6: str = "9") -> dict[str, str]:
    row = {column: "" for column in S2_QC_COLUMNS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "target_name_raw": canonical["target_name_raw"],
            "aptadiff_dataset": "A" if canonical["source_db"] == "aptadiff_a" else "B",
            "aptadiff_documented_target": (
                "IGFBP3" if canonical["source_db"] == "aptadiff_a" else "PTK7"
            ),
            "aptadiff_p6": p6,
            "alphabet_as_reported": canonical["alphabet_as_reported"],
            "molecule_type": canonical["molecule_type"],
            "chemistry": canonical["chemistry"],
            "t_to_u_applied": canonical["t_to_u_applied"],
            "sequence_length_full": canonical["sequence_length_full"],
            "sequence_length_core": canonical["sequence_length_core"],
            "construct_scope": canonical["construct_scope"],
            "trim_status": canonical["trim_status"],
            "trim_confidence": canonical["trim_confidence"],
            "qc_flags": canonical["qc_flags"],
        }
    )
    return row


def _meta(canonical: dict[str, str], *, p6: str = "9") -> dict[str, str]:
    row = {column: "" for column in SIDECAR_COLUMNS}
    source_key = canonical["source_db"]
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "aptadiff_csv_data_row": str(int(canonical["native_id"])),
            "aptadiff_seq": canonical["sequence_raw"],
            "aptadiff_p6": p6,
            "aptadiff_dataset": "A" if source_key == "aptadiff_a" else "B",
            "aptadiff_source_key": source_key,
            "aptadiff_documented_target": (
                "IGFBP3" if source_key == "aptadiff_a" else "PTK7"
            ),
            "aptadiff_target_provenance": "synthetic fixture",
        }
    )
    return row


def _classify(
    canonical: dict[str, str],
    *,
    p6: str = "9",
    policy=POLICY_A,
):
    return classify_aptadiff_record(
        canonical,
        _qc(canonical, p6=p6),
        _meta(canonical, p6=p6),
        policy=policy,
    )


def test_clean_ssdna_routes_to_parked_ssdna() -> None:
    result = _classify(_s2())
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.SSDNA_PARKED
    assert result.primary_route == PRIMARY_ROUTE_SSDNA
    assert result.park_row is not None
    assert result.rejection_row is None


def test_clean_ssdna_is_not_technically_eligible_rna() -> None:
    result = _classify(_s2())
    assert result.primary_route != PRIMARY_ROUTE_ELIGIBLE
    assert (
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
        not in result.eligibility.all_reasons
    )


def test_clean_ssdna_does_not_require_manual_review() -> None:
    result = _classify(_s2())
    assert result.eligibility.manual_review_required is False
    assert result.decision["manual_review_required"] == "false"
    assert result.decision["review_batch"] == ""


def test_ambiguous_n_hits_technical_failure_before_ssdna_parking() -> None:
    result = _classify(
        _s2(
            sequence=SYNTHETIC_N_36,
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
            native_id="00002",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.AMBIGUOUS_BASES
    assert result.primary_route == PRIMARY_ROUTE_REJECT
    assert EligibilityReason.SSDNA_PARKED in result.eligibility.secondary_reasons
    assert result.rejection_row is not None
    assert result.park_row is None


def test_ambiguous_n_sequence_is_not_repaired() -> None:
    canonical = _s2(
        sequence=SYNTHETIC_N_36,
        alphabet="ambiguous",
        qc_flags="ambiguous_base",
        native_id="00003",
    )
    result = _classify(canonical)
    assert result.canonical["sequence_raw"] == SYNTHETIC_N_36
    assert result.canonical["sequence_full"] == SYNTHETIC_N_36
    assert result.canonical["sequence_core"] == SYNTHETIC_N_36
    assert "N" in result.canonical["sequence_full"]
    assert result.canonical["t_to_u_applied"] == "false"


def test_ambiguous_n_retained_in_canonical() -> None:
    result = _classify(
        _s2(
            sequence=SYNTHETIC_N_36,
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
            native_id="00004",
        )
    )
    assert result.canonical["record_id"] == "aptadiff_a:00004"
    assert result.canonical["sequence_length_core"] == "36"


def test_ambiguous_n_uses_closed_vocabulary_reason() -> None:
    result = _classify(
        _s2(
            sequence=SYNTHETIC_N_36,
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
            native_id="00005",
        )
    )
    assert result.decision["primary_reason"] == "ambiguous_bases"
    assert result.rejection_row["rejection_reason"] == "ambiguous_bases"


def test_ambiguous_n_enters_active_checkpoint_review() -> None:
    result = _classify(
        _s2(
            sequence=SYNTHETIC_N_36,
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
            native_id="00006",
        )
    )
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "01_judgement_dependent_technical"
    assert "judgement_dependent_technical" in result.decision["checkpoint_review_reasons"]


def test_human_decision_fields_remain_blank() -> None:
    result = _classify(
        _s2(
            sequence=SYNTHETIC_N_36,
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
            native_id="00007",
        )
    )
    detail = result.decision
    assert detail.get("manual_decision", "") == ""
    local = classify_aptadiff_record(
        _s2(
            sequence=SYNTHETIC_N_36,
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
            native_id="00007",
        ),
        _qc(
            _s2(
                sequence=SYNTHETIC_N_36,
                alphabet="ambiguous",
                qc_flags="ambiguous_base",
                native_id="00007",
            )
        ),
        _meta(
            _s2(
                sequence=SYNTHETIC_N_36,
                alphabet="ambiguous",
                qc_flags="ambiguous_base",
                native_id="00007",
            )
        ),
        policy=POLICY_A,
    )
    from adapters.aptadiff_s3 import build_local_detail_row

    built = build_local_detail_row(
        canonical=local.canonical,
        s2_qc=_qc(local.canonical),
        source_metadata=_meta(local.canonical),
        decision=local.decision,
    )
    for name in (
        "manual_decision",
        "manual_sequence_corrected",
        "manual_notes",
        "manual_trim_action",
    ):
        assert built[name] == ""


def test_empty_rna_pool_does_not_fabricate_random_audit() -> None:
    clean = _classify(_s2(native_id="00010"))
    ambiguous = _classify(
        _s2(
            sequence=SYNTHETIC_N_36,
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
            native_id="00011",
        )
    )
    decisions = [clean.decision, ambiguous.decision]
    details = {
        clean.canonical["record_id"]: {"record_id": clean.canonical["record_id"]},
        ambiguous.canonical["record_id"]: {
            "record_id": ambiguous.canonical["record_id"]
        },
    }
    sampled, pool, shortfall = apply_random_accept_audit(
        decisions, details, seed=42, sample_size=30
    )
    assert sampled == 0
    assert pool == 0
    assert shortfall == 30
    assert all(row["review_batch"] != "04_random_kept_audit" for row in decisions)


def test_empty_target_name_raw_does_not_reject() -> None:
    result = _classify(_s2(target_name_raw=""))
    assert result.eligibility.primary_reason != EligibilityReason.MISSING_TARGET
    assert result.primary_route == PRIMARY_ROUTE_SSDNA


def test_p6_does_not_affect_route() -> None:
    low = _classify(_s2(native_id="00020"), p6="2")
    high = _classify(_s2(native_id="00021"), p6="194981")
    assert low.primary_route == high.primary_route == PRIMARY_ROUTE_SSDNA
    n_low = _classify(
        _s2(
            sequence=SYNTHETIC_N_36,
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
            native_id="00022",
        ),
        p6="5",
    )
    n_high = _classify(
        _s2(
            sequence=SYNTHETIC_N_36,
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
            native_id="00023",
        ),
        p6="36136",
    )
    assert n_low.primary_route == n_high.primary_route == PRIMARY_ROUTE_REJECT


def test_no_evidence_affinity_or_leakage_fields_populated() -> None:
    result = _classify(_s2())
    for field in S3_FORBIDDEN_FIELDS:
        assert result.canonical.get(field, "") == ""
        assert result.decision.get(field, "") == ""
    assert result.eligibility.sequence_leakage_match is None
    assert result.eligibility.target_leakage_match is None


def test_length_36_is_not_rejected() -> None:
    result = _classify(_s2())
    assert EligibilityReason.LENGTH_OUT_OF_RANGE not in result.eligibility.all_reasons
    assert result.canonical["sequence_length_core"] == "36"


def test_random_region_only_does_not_create_trim_review() -> None:
    result = _classify(_s2())
    assert result.decision["review_batch"] != "02_constant_region_proposal"
    assert "constant_region_proposal" not in result.decision["checkpoint_review_reasons"]
    assert result.canonical["construct_scope"] == "random_region_only"
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]


def test_dataset_b_uses_separate_policy_identity() -> None:
    result = _classify(
        _s2(source_key="aptadiff_b", native_id="00001"),
        policy=POLICY_B,
    )
    assert result.canonical["source_db"] == "aptadiff_b"
    assert result.primary_route == PRIMARY_ROUTE_SSDNA
    assert result.decision["aptadiff_documented_target"] == "PTK7"

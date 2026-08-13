"""Tests for the UTexas S3 eligibility adapter (synthetic only).

Every literal nucleotide string in this file is shorter than 20 nt except where
length thresholds are tested with strings built at runtime. Does not read real
UTexas source sequences.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.utexas_s3 import (  # noqa: E402
    apply_random_accept_audit,
    classify_utexas_record,
)
from common.corpus_schema import S3_FORBIDDEN_FIELDS, empty_corpus_record  # noqa: E402
from common.eligibility import (  # noqa: E402
    EligibilityDecision,
    EligibilityReason,
    load_eligibility_policy,
)

POLICY = load_eligibility_policy(
    REPO_ROOT / "config" / "source_eligibility" / "utexas.json"
)


def _rna(n: int) -> str:
    return ("ACGU" * ((n // 4) + 1))[:n]


def _s2(
    *,
    sequence: str = "ACGUAC",
    molecule_type: str = "RNA",
    alphabet: str = "RNA",
    chemistry: str = "RNA",
    target: str = "demo_target",
    qc_flags: str = "",
    trim_status: str = "no_constants_detected",
    trim_confidence: str = "",
    construct_scope: str = "unknown",
    native_id: str = "1",
    **overrides: str,
) -> dict[str, str]:
    record = empty_corpus_record()
    length = str(len(sequence)) if sequence else ""
    record.update(
        {
            "record_id": f"utexas:{native_id}",
            "sequence_raw": sequence,
            "sequence_full": sequence,
            "sequence_core": sequence,
            "sequence_length_full": length,
            "sequence_length_core": length,
            "construct_scope": construct_scope if sequence else "unknown",
            "trim_status": "not_applicable" if sequence == "" else trim_status,
            "trim_confidence": trim_confidence,
            "molecule_type": molecule_type if sequence else "unknown",
            "alphabet_as_reported": alphabet if sequence else "missing",
            "t_to_u_applied": "false",
            "chemistry": chemistry if sequence else "unknown",
            "target_name_raw": target,
            "source_db": "utexas",
            "source_dataset": "demo_ds",
            "contributing_sources": "utexas",
            "contributing_datasets": "demo_ds",
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


def _qc(canonical: dict[str, str]) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamer_name": f"name-{canonical['native_id']}",
        "target_name_raw": canonical["target_name_raw"],
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical["chemistry"],
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "construct_scope": canonical["construct_scope"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical["trim_confidence"],
        "qc_flags": canonical["qc_flags"],
    }


def _meta(canonical: dict[str, str], **overrides: str) -> dict[str, str]:
    row = {
        "record_id": canonical["record_id"],
        "utexas_name_of_aptamer": f"name-{canonical['native_id']}",
        "utexas_target": canonical["target_name_raw"],
        "utexas_kd_nm": "12.5",
        "utexas_affinity": "high affinity",
        "utexas_type_of_nucleic_acid": "ssRNA",
    }
    row.update(overrides)
    return row


def _classify(canonical: dict[str, str], **meta: str):
    return classify_utexas_record(
        canonical, _qc(canonical), _meta(canonical, **meta), policy=POLICY
    )


def test_missing_plus_ssdna_rejects_missing() -> None:
    row = _s2(
        sequence="",
        molecule_type="ssDNA",
        alphabet="missing",
        chemistry="DNA",
        qc_flags="missing_sequence|molecule_type_unknown",
        native_id="miss_dna",
    )
    # Preserve explicit ssDNA on a blank sequence to test precedence.
    row["molecule_type"] = "ssDNA"
    result = _classify(row)
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    assert EligibilityReason.NON_RNA_MOLECULE in result.eligibility.all_reasons
    assert result.eligibility.manual_review_required is False
    assert result.decision["review_batch"] == ""


def test_ssdna_valid_parks_without_review() -> None:
    seq = _rna(30).replace("U", "T")
    result = _classify(
        _s2(
            sequence=seq,
            molecule_type="ssDNA",
            alphabet="DNA_T",
            chemistry="DNA",
            native_id="dna_ok",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert result.eligibility.primary_reason == EligibilityReason.NON_RNA_MOLECULE
    assert result.eligibility.manual_review_required is False
    assert result.decision["review_batch"] == ""


def test_unknown_molecule_valid_parks_for_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(30),
            molecule_type="unknown",
            alphabet="RNA",
            chemistry="unknown",
            qc_flags="molecule_type_unknown|molecule_type_requires_review",
            native_id="fana",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
    )
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "03_park_unresolved_molecule"


def test_rna_ambiguous_rejects() -> None:
    result = _classify(
        _s2(
            sequence=_rna(29) + "N",
            molecule_type="RNA",
            alphabet="ambiguous",
            qc_flags="ambiguous_base",
            native_id="ambig",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.AMBIGUOUS_BASES
    assert result.eligibility.manual_review_required is False


def test_rna_invalid_rejects() -> None:
    result = _classify(
        _s2(
            sequence=_rna(29) + "X",
            molecule_type="RNA",
            alphabet="invalid",
            qc_flags="invalid_character",
            native_id="invalid",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.INVALID_ALPHABET
    assert result.eligibility.manual_review_required is False


def test_gap_sequence_rejects_with_repair_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(29) + "-",
            molecule_type="RNA",
            alphabet="invalid",
            qc_flags="invalid_character",
            native_id="gap",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.ALIGNMENT_GAPS
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "05_repair_alignment_gaps"


def test_rna_valid_20_100_accepts_unless_unresolved_trim() -> None:
    clean = _classify(
        _s2(sequence=_rna(40), native_id="clean", construct_scope="unknown")
    )
    assert clean.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert (
        clean.eligibility.primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    )
    assert clean.eligibility.manual_review_required is False

    unresolved = _classify(
        _s2(
            sequence=_rna(40),
            qc_flags="trim_requires_review",
            trim_status="constants_suspected_unresolved",
            native_id="trim_open",
        )
    )
    assert unresolved.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        unresolved.eligibility.primary_reason
        == EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED
    )
    assert unresolved.decision["review_batch"] == "04_park_trim_construct"


def test_length_below_20_rejects() -> None:
    result = _classify(_s2(sequence=_rna(19), native_id="short"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.eligibility.manual_review_required is False


def test_length_above_100_rejects() -> None:
    result = _classify(_s2(sequence=_rna(101), native_id="long"))
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert result.eligibility.manual_review_required is False


def test_overlength_with_unresolved_trim_rejects_but_reviews() -> None:
    result = _classify(
        _s2(
            sequence=_rna(120),
            qc_flags="trim_requires_review|core_above_max_length",
            trim_status="constants_suspected_unresolved",
            native_id="long_trim",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert (
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED in result.eligibility.all_reasons
    )
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "04_park_trim_construct"


def test_boundary_lengths_accept_with_review() -> None:
    low = _classify(_s2(sequence=_rna(22), native_id="low"))
    high = _classify(_s2(sequence=_rna(95), native_id="high"))
    assert low.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert high.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.LOWER_LENGTH_BOUNDARY in low.eligibility.all_reasons
    assert EligibilityReason.UPPER_LENGTH_BOUNDARY in high.eligibility.all_reasons
    assert low.decision["review_batch"] == "02_accept_with_diagnostics"
    assert high.decision["review_batch"] == "02_accept_with_diagnostics"


def test_full_passes_core_fails_goes_to_review() -> None:
    row = _s2(sequence=_rna(40), native_id="trim_push")
    row["sequence_core"] = _rna(15)
    row["sequence_length_core"] = "15"
    row["sequence_length_full"] = "40"
    row["qc_flags"] = "core_below_min_length"
    result = _classify(row)
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
    assert result.eligibility.primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE
    assert (
        EligibilityReason.TRIM_PUSHED_LENGTH_OUT_OF_RANGE
        in result.eligibility.all_reasons
    )
    assert result.eligibility.manual_review_required is True
    assert result.decision["review_batch"] == "01_reject_review"


def test_medium_applied_trim_accepts_with_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            trim_status="primers_removed",
            trim_confidence="medium",
            construct_scope="partial_construct",
            native_id="med",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert EligibilityReason.MEDIUM_CONFIDENCE_TRIM in result.eligibility.all_reasons
    assert result.decision["review_batch"] == "02_accept_with_diagnostics"


def test_blocked_40pct_trim_parks_for_review() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            qc_flags="trim_requires_review|trim_combined_exceeds_40pct",
            trim_status="constants_suspected_unresolved",
            native_id="pct40",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    assert (
        result.eligibility.primary_reason
        == EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED
    )
    assert (
        EligibilityReason.TRIM_COMBINED_EXCEEDS_40PCT in result.eligibility.all_reasons
    )
    assert result.decision["review_batch"] == "04_park_trim_construct"


def test_high_confidence_or_no_issue_core_may_accept() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            trim_status="no_constants_detected",
            trim_confidence="",
            native_id="plain",
        )
    )
    assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
    assert result.eligibility.manual_review_required is False


def test_modified_rna_chemistry_is_not_rejected() -> None:
    for chemistry, native_id in (
        ("2F-RNA", "f"),
        ("2NH2-RNA", "n"),
        ("2OMe-RNA", "o"),
        ("mixed", "m"),
        ("unknown", "u"),
    ):
        result = _classify(
            _s2(
                sequence=_rna(40),
                chemistry=chemistry,
                native_id=native_id,
            )
        )
        assert result.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
        assert result.canonical["chemistry"] == chemistry


def test_s3_does_not_populate_target_or_evidence_from_utexas_text() -> None:
    result = _classify(
        _s2(
            sequence=_rna(40),
            target="thrombin",
            native_id="thrombin",
        )
    )
    for field in S3_FORBIDDEN_FIELDS:
        assert result.canonical[field] == ""
    assert "target_type" not in result.decision
    assert "binding_evidence_score" not in result.decision
    assert "affinity_value" not in result.decision
    assert result.canonical["target_name"] == ""
    assert result.canonical["binding_evidence_score"] == ""


def test_ssdna_invalid_still_parks_as_dna_not_invalid() -> None:
    seq = ("ACGT" * 8)[:31] + "X"
    result = _classify(
        _s2(
            sequence=seq,
            molecule_type="ssDNA",
            alphabet="invalid",
            chemistry="DNA",
            qc_flags="invalid_character",
            native_id="dna_bad",
        )
    )
    assert result.eligibility.primary_reason == EligibilityReason.NON_RNA_MOLECULE
    assert EligibilityReason.INVALID_ALPHABET in result.eligibility.all_reasons
    assert result.eligibility.manual_review_required is False


def test_random_accept_audit_is_deterministic() -> None:
    rows = []
    details = {}
    for i in range(1, 41):
        canonical = _s2(sequence=_rna(40), native_id=str(i))
        classified = _classify(canonical)
        rows.append(classified.decision)
        details[classified.decision["record_id"]] = {
            "secondary_reasons": classified.decision["secondary_reasons"],
            "manual_review_required": classified.decision["manual_review_required"],
            "manual_review_priority": classified.decision["manual_review_priority"],
            "review_batch": classified.decision["review_batch"],
        }
    first = [dict(row) for row in rows]
    take_a, pool_a, short_a = apply_random_accept_audit(
        rows, details, seed=42, sample_size=30
    )
    selected_a = {
        row["record_id"]
        for row in rows
        if "random_accept_audit" in row["secondary_reasons"]
    }
    assert take_a == 30
    assert pool_a == 40
    assert short_a == 0
    assert len(selected_a) == 30
    for row in rows:
        if row["record_id"] in selected_a:
            assert row["review_batch"] == "02_accept_with_diagnostics"
            assert row["manual_review_required"] == "true"

    take_b, pool_b, _ = apply_random_accept_audit(
        first, {key: dict(val) for key, val in details.items()}, seed=42, sample_size=30
    )
    selected_b = {
        row["record_id"]
        for row in first
        if "random_accept_audit" in row["secondary_reasons"]
    }
    assert take_b == take_a
    assert pool_b == pool_a
    assert selected_a == selected_b

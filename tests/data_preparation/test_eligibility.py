"""Tests for generic S3 eligibility types and leakage helpers.

Every literal nucleotide string in this file is shorter than 20 nt except where
length thresholds are tested with strings built at runtime. No real source data.
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

from common.eligibility import (  # noqa: E402
    EligibilityDecision,
    EligibilityError,
    EligibilityReason,
    ExclusionReference,
    LeakageMatch,
    ManualReviewPriority,
    SequenceLeakageIndex,
    TargetAliasRule,
    build_eligibility_result,
    format_identity,
    format_reasons,
    load_eligibility_policy,
    load_sequence_leakage_index,
    load_target_alias_rules,
    match_target_leakage,
    normalise_target_text,
    review_sort_key,
)
from common.leakage_matching import comparison_form  # noqa: E402

POLICY_PATH = REPO_ROOT / "config" / "source_eligibility" / "aptabase.json"
ALIASES_PATH = REPO_ROOT / "config" / "leakage_target_aliases.csv"


def _rna(n: int, *, base: str = "ACGU") -> str:
    """Build a synthetic RNA string of length ``n`` at runtime."""
    if n < 0:
        raise ValueError("n must be non-negative")
    return (base * ((n // len(base)) + 1))[:n]


def _exclusion(
    exclusion_id: str,
    sequence: str,
    *,
    reference_id: str = "ref_a",
    target: str = "NDM-1",
) -> ExclusionReference:
    cmp = comparison_form(sequence)
    return ExclusionReference(
        exclusion_id=exclusion_id,
        reference_id=reference_id,
        target_name=target,
        evaluation_role="positive",
        sequence_compare_full=cmp,
        sequence_compare_core=cmp,
        status="resolved",
    )


def test_load_aptabase_eligibility_policy() -> None:
    policy = load_eligibility_policy(POLICY_PATH)
    assert policy.source_key == "aptabase"
    assert policy.core_length_min == 20
    assert policy.core_length_max == 100
    assert policy.sequence_identity_threshold == 0.9
    assert policy.checkpoint_requires_manual_approval is True
    assert policy.sequence_leakage_matching_enabled is True
    assert policy.defer_target_classification is False


def test_load_aptadb_eligibility_policy() -> None:
    policy = load_eligibility_policy(
        REPO_ROOT / "config" / "source_eligibility" / "aptadb.json"
    )
    assert policy.source_key == "aptadb"
    assert policy.defer_target_classification is True
    assert policy.defer_evidence_scoring is True
    assert policy.defer_leakage_exclusion is True
    assert policy.sequence_leakage_matching_enabled is False
    assert policy.use_plan_reason_vocabulary is True
    assert policy.random_accept_audit_size == 30
    assert policy.random_seed == 42
    assert policy.ssdna_decision == "proposed_park"
    assert policy.non_protein_target_decision == "proposed_park"


def test_load_riboaptamer_eligibility_policy() -> None:
    policy = load_eligibility_policy(
        REPO_ROOT / "config" / "source_eligibility" / "riboaptamer.json"
    )
    assert policy.source_key == "riboaptamer"
    assert policy.defer_target_classification is True
    assert policy.defer_evidence_scoring is True
    assert policy.defer_leakage_exclusion is True
    assert policy.sequence_leakage_matching_enabled is False
    assert policy.use_plan_reason_vocabulary is True
    assert policy.random_accept_audit_size == 30
    assert policy.random_seed == 42
    assert policy.core_length_min == 20
    assert policy.core_length_max == 100
    assert policy.decision_precedence[0] == "missing_sequence"
    assert policy.decision_precedence.index("truncated_sequence") < (
        policy.decision_precedence.index("invalid_alphabet")
    )
    assert policy.decision_precedence.index("alignment_gaps") < (
        policy.decision_precedence.index("invalid_alphabet")
    )
    assert "ssdna_parked" in policy.decision_precedence
    assert "non_protein_target_parked" not in policy.decision_precedence


def test_load_utexas_eligibility_policy() -> None:
    policy = load_eligibility_policy(
        REPO_ROOT / "config" / "source_eligibility" / "utexas.json"
    )
    assert policy.source_key == "utexas"
    assert policy.defer_target_classification is True
    assert policy.defer_evidence_scoring is True
    assert policy.defer_leakage_exclusion is True
    assert policy.sequence_leakage_matching_enabled is False
    assert policy.target_leakage_matching_enabled is False
    assert policy.explicit_non_rna_requires_manual_review is False
    assert policy.use_plan_reason_vocabulary is True
    assert policy.random_accept_audit_size == 30
    assert policy.random_seed == 42
    assert policy.reviewer_initials_required is False
    assert policy.reviewer_notes_required is False
    assert policy.invalid_sequence_decision == "proposed_reject"
    assert policy.ssdna_decision == "proposed_park"
    assert policy.decision_precedence[0] == "missing_sequence"
    assert policy.decision_precedence[1] == "non_rna_molecule"


def test_load_ena_eligibility_policy() -> None:
    policy = load_eligibility_policy(
        REPO_ROOT / "config" / "source_eligibility" / "ena.json"
    )
    assert policy.source_key == "ena"
    assert policy.defer_target_classification is True
    assert policy.defer_evidence_scoring is True
    assert policy.defer_leakage_exclusion is True
    assert policy.sequence_leakage_matching_enabled is False
    assert policy.target_leakage_matching_enabled is False
    assert policy.use_plan_reason_vocabulary is True
    assert policy.unresolved_trim_blocks_eligibility is True
    assert policy.random_accept_audit_size == 30
    assert policy.random_seed == 42
    assert policy.core_length_min == 20
    assert policy.core_length_max == 100
    assert policy.length_out_of_range_decision == "proposed_reject"
    assert policy.trim_review_decision == "proposed_park"
    assert policy.eligible_rna_decision == "proposed_accept"
    assert policy.decision_precedence[0] == "missing_sequence"
    assert policy.decision_precedence[-1] == "technically_eligible_rna"
    assert "length_out_of_range" in policy.decision_precedence
    assert "trim_construct_unresolved" in policy.decision_precedence
    assert "ssdna_parked" not in policy.decision_precedence
    assert "non_protein_target_parked" not in policy.decision_precedence
    assert policy.active_review_batches[0] == "01_judgement_dependent_technical"


def test_load_aptaindex_eligibility_policy() -> None:
    policy = load_eligibility_policy(
        REPO_ROOT / "config" / "source_eligibility" / "aptaindex.json"
    )
    assert policy.source_key == "aptaindex"
    assert policy.defer_target_classification is True
    assert policy.defer_evidence_scoring is True
    assert policy.defer_leakage_exclusion is True
    assert policy.sequence_leakage_matching_enabled is False
    assert policy.target_leakage_matching_enabled is False
    assert policy.use_plan_reason_vocabulary is True
    assert policy.random_accept_audit_size == 30
    assert policy.random_seed == 42
    assert policy.ssdna_decision == "proposed_park"
    assert policy.non_nucleic_acid_molecule_decision == "proposed_reject"
    assert policy.unknown_molecule_decision == "proposed_park"
    assert policy.decision_precedence[0] == "missing_sequence"
    assert policy.decision_precedence[1] == "non_nucleic_acid_molecule"
    assert "unsupported_chemical_notation" in policy.decision_precedence
    assert "l_rna_stereochemistry" in policy.decision_precedence
    assert "ssdna_parked" in policy.decision_precedence
    assert "non_protein_target_parked" not in policy.decision_precedence


def test_non_nucleic_acid_molecule_is_closed_reason_without_changing_completed_sources() -> None:
    assert EligibilityReason.NON_NUCLEIC_ACID_MOLECULE.value == (
        "non_nucleic_acid_molecule"
    )
    aptadb = load_eligibility_policy(
        REPO_ROOT / "config" / "source_eligibility" / "aptadb.json"
    )
    ribo = load_eligibility_policy(
        REPO_ROOT / "config" / "source_eligibility" / "riboaptamer.json"
    )
    utexas = load_eligibility_policy(
        REPO_ROOT / "config" / "source_eligibility" / "utexas.json"
    )
    for policy in (aptadb, ribo, utexas):
        assert "non_nucleic_acid_molecule" not in policy.decision_precedence
        assert policy.non_nucleic_acid_molecule_decision == "proposed_reject"


def test_60_unknown_decision_value_fails(tmp_path: Path) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["decision_values"] = [
        "proposed_accept",
        "proposed_park",
        "proposed_reject",
        "final_include",
    ]
    path = tmp_path / "bad_policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EligibilityError, match="unknown decision"):
        load_eligibility_policy(path)


def test_build_eligibility_result_secondary_sorted() -> None:
    result = build_eligibility_result(
        record_id="aptabase:1",
        proposed_decision=EligibilityDecision.PROPOSED_REJECT,
        primary_reason=EligibilityReason.MISSING_SEQUENCE,
        secondary_reasons=(
            EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW,
            EligibilityReason.MOLECULE_TYPE_UNRESOLVED,
            EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW,
        ),
        manual_review_priority=ManualReviewPriority.NONE,
    )
    assert result.secondary_reasons == (
        EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED,
    )
    assert format_reasons(result.secondary_reasons) == (
        "missing_target_requires_source_review|molecule_type_unresolved"
    )


def test_17_exact_full_sequence_match() -> None:
    seq = "ACGUACGUAC"
    index = SequenceLeakageIndex(references=(_exclusion("ex1", seq),))
    match = index.best_match(
        sequence_full=seq, sequence_core=seq, threshold=0.9
    )
    assert match is not None
    assert match.identity == pytest.approx(1.0)
    assert match.matched_exclusion_id == "ex1"


def test_18_exact_core_sequence_match() -> None:
    core = "ACGUACGU"
    full = "GG" + core + "CC"
    index = SequenceLeakageIndex(
        references=(
            ExclusionReference(
                exclusion_id="ex_core",
                reference_id="ref_core",
                target_name="KPC-2",
                evaluation_role="positive",
                sequence_compare_full=comparison_form("UUUUUUUU"),
                sequence_compare_core=comparison_form(core),
                status="resolved",
            ),
        )
    )
    match = index.best_match(
        sequence_full=full, sequence_core=core, threshold=0.9
    )
    assert match is not None
    assert "core" in match.matched_form
    assert match.matched_reference_id == "ref_core"


def test_19_tu_equivalent_match() -> None:
    dna = "ACGTACGTAC"
    rna = "ACGUACGUAC"
    index = SequenceLeakageIndex(references=(_exclusion("ex_tu", dna),))
    match = index.best_match(
        sequence_full=rna, sequence_core=rna, threshold=0.9
    )
    assert match is not None
    assert match.identity == pytest.approx(1.0)


def test_20_exactly_90_percent_identity_matches() -> None:
    # Length 10, one substitution → identity 0.90.
    a = "ACGTACGTAC"
    b = "ACGTACGTAG"
    index = SequenceLeakageIndex(references=(_exclusion("ex90", a),))
    match = index.best_match(sequence_full=b, sequence_core=b, threshold=0.9)
    assert match is not None
    assert match.identity == pytest.approx(0.9)


def test_21_below_90_percent_does_not_match() -> None:
    a = "ACGTACGTAC"
    b = "ACGTACGAAA"  # two substitutions → 0.80
    index = SequenceLeakageIndex(references=(_exclusion("ex80", a),))
    match = index.best_match(sequence_full=b, sequence_core=b, threshold=0.9)
    assert match is None


def test_22_best_match_selected_deterministically() -> None:
    query = "ACGUACGUAC"
    near = "ACGUACGUAG"  # 0.9
    exact = "ACGUACGUAC"  # 1.0
    index = SequenceLeakageIndex(
        references=(
            _exclusion("ex_b", near, reference_id="ref_near"),
            _exclusion("ex_a", exact, reference_id="ref_exact"),
        )
    )
    match = index.best_match(
        sequence_full=query, sequence_core=query, threshold=0.9
    )
    assert match is not None
    assert match.matched_exclusion_id == "ex_a"
    assert match.identity == pytest.approx(1.0)


def test_23_target_exact_alias_match() -> None:
    rules = load_target_alias_rules(ALIASES_PATH)
    match = match_target_leakage(["NDM-1"], rules)
    assert match is not None
    assert match.match_type == "exact_alias"
    assert match.matched_canonical_target == "NDM-1"


def test_24_target_normalised_alias_match() -> None:
    rules = load_target_alias_rules(ALIASES_PATH)
    match = match_target_leakage(["HIS  NDM-1"], rules)
    assert match is not None
    assert match.match_type in {"exact_alias", "normalised_alias"}
    assert match.matched_canonical_target == "NDM-1"


def test_25_bounded_family_pattern_match() -> None:
    rules = load_target_alias_rules(ALIASES_PATH)
    match = match_target_leakage(["serine beta-lactamase inhibitor screen"], rules)
    assert match is not None
    assert match.match_type == "family_pattern"
    assert "lactamase" in match.matched_alias.casefold() or match.target_family


def test_26_bare_substring_false_positive_rejected() -> None:
    rules = load_target_alias_rules(ALIASES_PATH)
    # "HSA" must not match inside an unrelated token; "albumin" alone omitted.
    assert match_target_leakage(["CHSA peptide"], rules) is None
    assert match_target_leakage(["bovine albumin fragment"], rules) is None
    assert match_target_leakage(["noncarbapenemase protein"], rules) is None


def test_27_missing_leakage_file_fails(tmp_path: Path) -> None:
    with pytest.raises(EligibilityError, match="Missing leakage"):
        load_sequence_leakage_index(tmp_path / "missing.csv")


def test_28_duplicate_leakage_ids_fail(tmp_path: Path) -> None:
    path = tmp_path / "leak.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "exclusion_id",
                "reference_id",
                "target_name",
                "evaluation_role",
                "sequence_compare_full",
                "sequence_compare_core",
                "status",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        row = {
            "exclusion_id": "dup",
            "reference_id": "r1",
            "target_name": "NDM-1",
            "evaluation_role": "positive",
            "sequence_compare_full": "ACGT",
            "sequence_compare_core": "ACGT",
            "status": "resolved",
        }
        writer.writerow(row)
        writer.writerow(row)
    with pytest.raises(EligibilityError, match="Duplicate exclusion_id"):
        load_sequence_leakage_index(path)


def test_29_no_sequence_in_leakage_match_dataclass() -> None:
    match = LeakageMatch(
        matched_exclusion_id="ex1",
        matched_reference_id="ref1",
        matched_target="NDM-1",
        matched_evaluation_role="positive",
        matched_form="full_vs_full",
        identity=1.0,
    )
    assert "sequence" not in match.__dataclass_fields__
    assert "ACGU" not in repr(match)


def test_normalise_target_text_hyphen_and_case() -> None:
    assert normalise_target_text("HIS-NDM-1") == normalise_target_text("his ndm 1")
    assert "beta" in normalise_target_text("β-lactamase")


def test_review_sort_key_priority_then_decision() -> None:
    rows = [
        {
            "manual_review_priority": "none",
            "proposed_decision": "proposed_accept",
            "primary_reason": "technically_eligible_rna",
            "record_id": "aptabase:2",
        },
        {
            "manual_review_priority": "high",
            "proposed_decision": "proposed_reject",
            "primary_reason": "evaluation_sequence_leakage",
            "record_id": "aptabase:1",
        },
        {
            "manual_review_priority": "high",
            "proposed_decision": "proposed_park",
            "primary_reason": "mixed_t_u_requires_review",
            "record_id": "aptabase:3",
        },
    ]
    ordered = sorted(rows, key=review_sort_key)
    assert ordered[0]["record_id"] == "aptabase:3"
    assert ordered[1]["record_id"] == "aptabase:1"
    assert ordered[2]["record_id"] == "aptabase:2"


def test_format_identity_deterministic() -> None:
    assert format_identity(0.9) == "0.9"
    assert format_identity(1.0) == "1"

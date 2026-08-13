"""Tests for UTexas constant-region review decisions and approved trim application.

Synthetic nucleotide strings only. Does not embed real UTexas aptamer sequences.
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

from adapters.utexas_approved_trims import (  # noqa: E402
    ApprovedTrimRule,
    apply_single_record_trim_for_tests,
)
from adapters.utexas_constant_region_review import (  # noqa: E402
    EXPECTED_APPROVE,
    EXPECTED_CANDIDATE_RULES,
    EXPECTED_NEEDS_SOURCE_REVIEW,
    apply_explicit_review_decisions,
    validate_reviewed_candidate_package,
)

CANDIDATE_PATH = (
    REPO_ROOT
    / "data"
    / "interim"
    / "normalised"
    / "utexas_constant_region_rule_candidates.csv"
)


def _rule(
    rule_id: str,
    side: str,
    motif: str,
    *,
    agreement: str = "pool_type_plus_consensus_agree",
) -> ApprovedTrimRule:
    return ApprovedTrimRule(
        candidate_rule_id=rule_id,
        side=side,
        motif=motif,
        motif_length=len(motif),
        evidence_sources="group_consensus",
        agreement_category=agreement,
        group_consensus_support="1",
        confidence="medium",
    )


def test_review_decision_reconciliation_on_reviewed_package() -> None:
    if not CANDIDATE_PATH.is_file():
        pytest.skip("reviewed UTexas candidate package is not present")
    with CANDIDATE_PATH.open(encoding="utf-8", newline="") as handle:
        candidates = list(csv.DictReader(handle))
    validate_reviewed_candidate_package(candidates)
    decisions = apply_explicit_review_decisions(candidates)
    counts = {}
    for row in decisions:
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1
    assert counts.get("approve", 0) == EXPECTED_APPROVE == 47
    assert counts.get("needs_source_review", 0) == EXPECTED_NEEDS_SOURCE_REVIEW == 522
    assert counts.get("reject", 0) == 0
    assert all(row["decision"] for row in decisions)
    assert len(decisions) == EXPECTED_CANDIDATE_RULES
    assert all(row["reviewer_initials"] == "" for row in decisions)


def test_exact_five_prime_trim_applies() -> None:
    core, skip, flags = apply_single_record_trim_for_tests(
        "AAAA" + "C" * 20,
        approved_rules=[_rule("r5", "five_prime", "AAAA")],
    )
    assert core == "C" * 20
    assert skip == ""
    assert "trim_requires_review" not in flags


def test_exact_three_prime_trim_applies() -> None:
    core, skip, flags = apply_single_record_trim_for_tests(
        "C" * 20 + "AAAA",
        approved_rules=[_rule("r3", "three_prime", "AAAA")],
    )
    assert core == "C" * 20
    assert skip == ""
    assert "trim_requires_review" not in flags


def test_non_exact_record_is_not_trimmed() -> None:
    core, skip, _flags = apply_single_record_trim_for_tests(
        "GGGGCCCCCCCC",
        approved_rules=[_rule("r5", "five_prime", "AAAA")],
    )
    assert core == "GGGGCCCCCCCC"
    assert skip == ""


def test_same_side_ambiguity_does_not_trim() -> None:
    core, skip, flags = apply_single_record_trim_for_tests(
        "AAAACCCCCCCC",
        approved_rules=[
            _rule("r5a", "five_prime", "AAAA"),
            _rule("r5b", "five_prime", "AAAACC"),
        ],
    )
    assert core == "AAAACCCCCCCC"
    assert skip == "same_side_ambiguous"
    assert "trim_same_side_ambiguous" in flags
    assert "trim_requires_review" in flags


def test_same_motif_two_rule_ids_is_one_trim() -> None:
    core, skip, _flags = apply_single_record_trim_for_tests(
        "AAAA" + "C" * 20,
        approved_rules=[
            _rule("r5a", "five_prime", "AAAA"),
            _rule("r5b", "five_prime", "AAAA"),
        ],
    )
    assert core == "C" * 20
    assert skip == ""


def test_both_sides_safe_both_apply() -> None:
    core, skip, _flags = apply_single_record_trim_for_tests(
        "AAAA" + "C" * 20 + "GGGG",
        approved_rules=[
            _rule("r5", "five_prime", "AAAA"),
            _rule("r3", "three_prime", "GGGG"),
        ],
    )
    assert core == "C" * 20
    assert skip == ""


def test_combined_below_20_neither_applies() -> None:
    # Individually each motif is short; together they would leave 8 nt.
    core, skip, flags = apply_single_record_trim_for_tests(
        "AAAACCCCGGGG",
        approved_rules=[
            _rule("r5", "five_prime", "AAAA"),
            _rule("r3", "three_prime", "GGGG"),
        ],
    )
    assert core == "AAAACCCCGGGG"
    assert skip == "combined_core_below_20"
    assert "trim_combined_core_below_min" in flags


def test_combined_over_40pct_neither_applies() -> None:
    # 8+8 removed from 20 nt = 80% > 40%; remaining core would be 4 < 20 anyway
    # Use 30 nt so remaining would be 18... wait 12+12 from 30 = 24/30=80%, core=6.
    # Need remaining >= 20 but fraction > 0.40: remove 10+10 from 30 → core 10, still <20.
    # remove 8+8 from 30 → core 14 still <20.
    # remove 7+7 from 40 → core 26 >=20, fraction 14/40=0.35 <=0.40. Too small.
    # remove 9+9 from 40 → core 22 >=20, fraction 18/40=0.45 >0.40.
    core, skip, flags = apply_single_record_trim_for_tests(
        "AAAAAAAAA" + "C" * 22 + "GGGGGGGGG",
        approved_rules=[
            _rule("r5", "five_prime", "AAAAAAAAA"),
            _rule("r3", "three_prime", "GGGGGGGGG"),
        ],
    )
    assert core == "AAAAAAAAA" + "C" * 22 + "GGGGGGGGG"
    assert skip == "combined_trim_exceeds_40pct"
    assert "trim_combined_exceeds_40pct" in flags


def test_one_side_safe_applies() -> None:
    core, skip, _flags = apply_single_record_trim_for_tests(
        "AAAA" + "C" * 20,
        approved_rules=[_rule("r5", "five_prime", "AAAA")],
    )
    assert core == "C" * 20
    assert skip == ""


def test_unresolved_rule_cannot_trim() -> None:
    core, skip, flags = apply_single_record_trim_for_tests(
        "AAAACCCCCCCCCCCCCCCC",
        approved_rules=[],
        unresolved_rule_ids={"r5"},
    )
    assert core == "AAAACCCCCCCCCCCCCCCC"
    assert skip == ""
    assert "trim_requires_review" in flags
    assert "constants_suspected_unresolved" in flags


def test_t_u_collapsed_exact_match() -> None:
    core, skip, _flags = apply_single_record_trim_for_tests(
        "UUUU" + "C" * 20,
        approved_rules=[_rule("r5", "five_prime", "TTTT")],
    )
    assert core == "C" * 20
    assert skip == ""


def test_sequence_full_not_changed_by_helper() -> None:
    original = "AAAA" + "C" * 20
    core, _skip, _flags = apply_single_record_trim_for_tests(
        original,
        approved_rules=[_rule("r5", "five_prime", "AAAA")],
    )
    assert core == "C" * 20
    assert original == "AAAA" + "C" * 20

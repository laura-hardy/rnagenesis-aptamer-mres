"""Tests for group-level constant-region inference (synthetic sequences only).

Every literal nucleotide string in this file is shorter than 20 nt.
Constant-region inference proposes only; it does not prove biological
nonfunctionality.
"""

from __future__ import annotations

import copy
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

from common.constant_region_inference import (  # noqa: E402
    GROUP_INFERENCE_KEY_AUTO,
    GROUP_INFERENCE_KEY_EXPERIMENT_GROUP,
    GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
    QUALIFYING_TIER2_STATUS,
    TIER2_CONFIDENCE_LABEL,
    ConstantRegionInferenceError,
    InferenceRecord,
    apply_approved_trim,
    build_group_inference_key,
    infer_group_constant_regions,
    infer_group_constant_regions_with_diagnostics,
    proposal_to_trim_plan,
    resolve_publication_identity,
)
from common.sequence_normalisation import (  # noqa: E402
    TrimProposal,
    load_normalisation_rules,
    rules_to_public_dict,
    validate_rules_dict,
)


@pytest.fixture(scope="module")
def short_rules():
    """Unit-test rules with short motifs so synthetic sequences stay <20 nt."""
    base = load_normalisation_rules()
    return validate_rules_dict(
        {
            **rules_to_public_dict(base),
            "constant_region_inference": {
                "minimum_group_size": 5,
                "minimum_support": 0.9,
                "minimum_region_length": 4,
                "maximum_region_length": 30,
            },
        }
    )


@pytest.fixture(scope="module")
def plan_rules():
    """Plan-aligned thresholds (support >=0.80, motif >=12)."""
    return load_normalisation_rules()


def _group_records(
    group_id: str,
    sequences: list[str],
    *,
    id_prefix: str = "r",
) -> list[dict[str, str | None]]:
    return [
        {
            "record_id": f"{id_prefix}{index}",
            "experiment_group_id": group_id,
            "sequence_full": sequence,
        }
        for index, sequence in enumerate(sequences)
    ]


def test_29_high_support_five_prime_proposal(short_rules) -> None:
    seqs = [
        "AAAACCCC",
        "AAAAGGGG",
        "AAAAUUUU",
        "AAAACCGG",
        "AAAAGGCC",
    ]
    proposals = infer_group_constant_regions(
        _group_records("g1", seqs), rules=short_rules
    )
    five = [p for p in proposals if p.side == "five_prime" and p.experiment_group_id == "g1"]
    assert len(five) == 1
    assert five[0].status == QUALIFYING_TIER2_STATUS
    assert five[0].confidence == TIER2_CONFIDENCE_LABEL
    assert five[0].proposed_sequence == "AAAA"
    assert five[0].support >= 0.9


def test_30_high_support_three_prime_proposal(short_rules) -> None:
    seqs = [
        "CCCCAAAA",
        "GGGGAAAA",
        "UUUUAAAA",
        "CCGGAAAA",
        "GGCCAAAA",
    ]
    proposals = infer_group_constant_regions(
        _group_records("g2", seqs), rules=short_rules
    )
    three = [p for p in proposals if p.side == "three_prime"]
    assert three[0].status == QUALIFYING_TIER2_STATUS
    assert three[0].proposed_sequence == "AAAA"


def test_31_both_end_proposals(short_rules) -> None:
    seqs = [
        "AAAACCCCUUUU",
        "AAAAGGGGUUUU",
        "AAAAUUUUUUUU",
        "AAAACCGGUUUU",
        "AAAAGGCCUUUU",
    ]
    proposals = infer_group_constant_regions(
        _group_records("g3", seqs), rules=short_rules
    )
    by_side = {p.side: p for p in proposals if p.status == QUALIFYING_TIER2_STATUS}
    assert by_side["five_prime"].proposed_sequence == "AAAA"
    assert by_side["three_prime"].proposed_sequence == "UUUU"


def test_32_small_group_yields_no_proposal(short_rules) -> None:
    seqs = ["AAAACCCC", "AAAAGGGG", "AAAAUUUU"]
    result = infer_group_constant_regions_with_diagnostics(
        _group_records("g4", seqs), rules=short_rules
    )
    assert result.proposals == ()
    assert result.diagnostics.groups_below_min_size == 1
    diagnostic = infer_group_constant_regions(
        _group_records("g4", seqs),
        rules=short_rules,
        include_non_qualifying=True,
    )
    assert all(p.status == "insufficient_group_size" for p in diagnostic)
    assert all(p.proposed_sequence is None for p in diagnostic)


def test_33_support_below_threshold_stops_extension(short_rules) -> None:
    seqs = [
        "AAAACCCC",
        "AAAACGGG",
        "AAAACUUU",
        "AAAACCGG",
        "GGGGAAAA",
    ]
    proposals = infer_group_constant_regions(
        _group_records("g5", seqs),
        rules=short_rules,
        include_non_qualifying=True,
    )
    five = next(p for p in proposals if p.side == "five_prime")
    assert five.status in {"insufficient_support", "no_constant_region"}
    assert five.proposed_sequence is None
    assert (
        infer_group_constant_regions(_group_records("g5", seqs), rules=short_rules)
        == ()
    )


def test_34_maximum_inferred_length_respected(short_rules) -> None:
    tight = validate_rules_dict(
        {
            **rules_to_public_dict(short_rules),
            "constant_region_inference": {
                "minimum_group_size": 5,
                "minimum_support": 0.9,
                "minimum_region_length": 4,
                "maximum_region_length": 4,
            },
        }
    )
    seqs = [
        "AAAACCCCGG",
        "AAAACCCCUU",
        "AAAACCCCAA",
        "AAAACCCCGG",
        "AAAACCCCUU",
    ]
    proposals = infer_group_constant_regions(_group_records("g6", seqs), rules=tight)
    five = next(p for p in proposals if p.side == "five_prime")
    assert five.status == QUALIFYING_TIER2_STATUS
    assert five.length == 4
    assert five.proposed_sequence == "AAAA"


def test_35_missing_group_id_not_pooled(short_rules) -> None:
    records = [
        {"record_id": "a1", "experiment_group_id": None, "sequence_full": "AAAACCCC"},
        {"record_id": "a2", "experiment_group_id": None, "sequence_full": "AAAAGGGG"},
        {"record_id": "a3", "experiment_group_id": None, "sequence_full": "AAAAUUUU"},
        {"record_id": "a4", "experiment_group_id": None, "sequence_full": "AAAACCGG"},
        {"record_id": "a5", "experiment_group_id": None, "sequence_full": "AAAAGGCC"},
        {"record_id": "b1", "experiment_group_id": "kept", "sequence_full": "GGGGCCCC"},
        {"record_id": "b2", "experiment_group_id": "kept", "sequence_full": "GGGGGGGG"},
        {"record_id": "b3", "experiment_group_id": "kept", "sequence_full": "GGGGUUUU"},
        {"record_id": "b4", "experiment_group_id": "kept", "sequence_full": "GGGGCCGG"},
        {"record_id": "b5", "experiment_group_id": "kept", "sequence_full": "GGGGGGCC"},
    ]
    proposals = infer_group_constant_regions(records, rules=short_rules)
    group_ids = {p.experiment_group_id for p in proposals}
    assert None not in group_ids
    assert "kept" in group_ids
    assert not any(p.proposed_sequence == "AAAA" for p in proposals)


def test_36_invalid_missing_sequences_excluded_and_counted(short_rules) -> None:
    records = _group_records(
        "g7",
        ["AAAACCCC", "AAAAGGGG", "AAAAUUUU", "AAAACCGG", "AAAAGGCC"],
    )
    records.append(
        {"record_id": "bad", "experiment_group_id": "g7", "sequence_full": None}
    )
    records.append(
        {"record_id": "bad2", "experiment_group_id": "g7", "sequence_full": "ACGX"}
    )
    proposals = infer_group_constant_regions(records, rules=short_rules)
    five = next(p for p in proposals if p.side == "five_prime")
    assert five.records_excluded == 2
    assert five.status == QUALIFYING_TIER2_STATUS


def test_37_input_order_independence(short_rules) -> None:
    seqs = [
        "AAAACCCC",
        "AAAAGGGG",
        "AAAAUUUU",
        "AAAACCGG",
        "AAAAGGCC",
    ]
    forward = infer_group_constant_regions(
        _group_records("g8", seqs), rules=short_rules
    )
    reverse = infer_group_constant_regions(
        list(reversed(_group_records("g8", seqs))), rules=short_rules
    )
    assert forward == reverse


def test_38_exact_application_of_approved_inferred_trim(short_rules) -> None:
    seqs = [
        "AAAACCCC",
        "AAAAGGGG",
        "AAAAUUUU",
        "AAAACCGG",
        "AAAAGGCC",
    ]
    proposals = infer_group_constant_regions(
        _group_records("g9", seqs), rules=short_rules
    )
    five = next(p for p in proposals if p.side == "five_prime")
    plan = proposal_to_trim_plan(five)
    applied = apply_approved_trim(
        "AAAACCCC",
        molecule_type="RNA",
        trim_plan=plan,
        record_id="r0",
        rules=short_rules,
    )
    assert applied.matched is True
    assert applied.sequence_full == "AAAACCCC"
    assert applied.sequence_core == "CCCC"
    assert applied.applied_trims[0].side == "five_prime"


def test_39_nonmatching_record_remains_untrimmed_and_flagged(short_rules) -> None:
    plan = TrimProposal(
        five_prime="AAAA",
        reason="approved_inference",
        confidence=0.95,
        source="test",
        status="approved",
    )
    applied = apply_approved_trim(
        "GGGGCCCC",
        molecule_type="RNA",
        trim_plan=plan,
        record_id="x",
        rules=short_rules,
    )
    assert applied.matched is False
    assert applied.sequence_core == applied.sequence_full == "GGGGCCCC"
    assert applied.applied_trims == ()
    assert "trim_requires_review" in applied.qc_flags


def test_40_proposal_generation_does_not_mutate_inputs(short_rules) -> None:
    records = _group_records(
        "g10",
        ["AAAACCCC", "AAAAGGGG", "AAAAUUUU", "AAAACCGG", "AAAAGGCC"],
    )
    snapshot = copy.deepcopy(records)
    infer_group_constant_regions(records, rules=short_rules)
    assert records == snapshot


def test_41_multiple_experiment_groups_remain_separate(short_rules) -> None:
    records = _group_records(
        "alpha",
        ["AAAACCCC", "AAAAGGGG", "AAAAUUUU", "AAAACCGG", "AAAAGGCC"],
        id_prefix="a",
    ) + _group_records(
        "beta",
        ["GGGGCCCC", "GGGGGGGG", "GGGGUUUU", "GGGGCCGG", "GGGGGGCC"],
        id_prefix="b",
    )
    proposals = infer_group_constant_regions(records, rules=short_rules)
    alpha_five = next(
        p
        for p in proposals
        if p.experiment_group_id == "alpha" and p.side == "five_prime"
    )
    beta_five = next(
        p
        for p in proposals
        if p.experiment_group_id == "beta" and p.side == "five_prime"
    )
    assert alpha_five.proposed_sequence == "AAAA"
    assert beta_five.proposed_sequence == "GGGG"


def test_42_no_constant_region_when_agreement_inadequate(short_rules) -> None:
    seqs = [
        "ACGUACGU",
        "UGCAUGCA",
        "GCGCGCGC",
        "CGCGCGCG",
        "AUAUAUAU",
    ]
    proposals = infer_group_constant_regions(
        _group_records("g11", seqs),
        rules=short_rules,
        include_non_qualifying=True,
    )
    assert all(p.proposed_sequence is None for p in proposals)
    assert all(
        p.status in {"insufficient_support", "no_constant_region"} for p in proposals
    )
    assert (
        infer_group_constant_regions(_group_records("g11", seqs), rules=short_rules)
        == ()
    )


def test_inference_record_typed_input(short_rules) -> None:
    records = [
        InferenceRecord("t0", "typed", "AAAACCCC"),
        InferenceRecord("t1", "typed", "AAAAGGGG"),
        InferenceRecord("t2", "typed", "AAAAUUUU"),
        InferenceRecord("t3", "typed", "AAAACCGG"),
        InferenceRecord("t4", "typed", "AAAAGGCC"),
    ]
    proposals = infer_group_constant_regions(records, rules=short_rules)
    five = next(p for p in proposals if p.side == "five_prime")
    assert five.proposed_sequence == "AAAA"


def test_unapproved_trim_plan_rejected(short_rules) -> None:
    plan = TrimProposal(
        five_prime="AAAA",
        reason="draft",
        confidence=0.5,
        source="test",
        status="requires_review",
    )
    with pytest.raises(ConstantRegionInferenceError):
        apply_approved_trim(
            "AAAACCCC", molecule_type="RNA", trim_plan=plan, rules=short_rules
        )


def test_no_stdout_on_inference(short_rules) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    records = _group_records(
        "g12",
        ["AAAACCCC", "AAAAGGGG", "AAAAUUUU", "AAAACCGG", "AAAAGGCC"],
    )
    with redirect_stdout(stdout), redirect_stderr(stderr):
        infer_group_constant_regions(records, rules=short_rules)
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""


def test_repeated_inference_identical(short_rules) -> None:
    records = _group_records(
        "g13",
        ["AAAACCCC", "AAAAGGGG", "AAAAUUUU", "AAAACCGG", "AAAAGGCC"],
    )
    a = infer_group_constant_regions(records, rules=short_rules)
    b = infer_group_constant_regions(records, rules=short_rules)
    assert a == b
    assert json.dumps([p.__dict__ for p in a], sort_keys=True) == json.dumps(
        [p.__dict__ for p in b], sort_keys=True
    )


def test_no_zero_length_in_default_proposals(short_rules) -> None:
    seqs = ["AAAACCCC", "AAAAGGGG", "AAAAUUUU"]
    proposals = infer_group_constant_regions(
        _group_records("tiny", seqs), rules=short_rules
    )
    assert all(p.length > 0 and p.proposed_sequence for p in proposals)


def test_group_key_experiment_group_precedence() -> None:
    key = build_group_inference_key(
        source_db="utexas",
        grouping_mode=GROUP_INFERENCE_KEY_AUTO,
        experiment_group_id="expA",
        target_name_raw="targetX",
        publication="paperY",
    )
    assert key == "utexas:experiment_group:expA"


def test_group_key_target_publication_fallback() -> None:
    key = build_group_inference_key(
        source_db="utexas",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        experiment_group_id=None,
        target_name_raw="targetX",
        publication="paperY",
    )
    assert key is not None
    assert key.startswith("utexas:tgt_pub:")


def test_group_key_missing_values_not_pooled() -> None:
    assert (
        build_group_inference_key(
            source_db="utexas",
            grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
            target_name_raw="",
            publication="paperY",
        )
        is None
    )
    assert (
        build_group_inference_key(
            source_db="utexas",
            grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
            target_name_raw="targetX",
            publication="",
        )
        is None
    )


def test_different_targets_same_pool_type_not_merged() -> None:
    key_a = build_group_inference_key(
        source_db="utexas",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetA",
        publication="same_paper",
    )
    key_b = build_group_inference_key(
        source_db="utexas",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetB",
        publication="same_paper",
    )
    assert key_a != key_b


def test_same_target_different_publications_not_merged() -> None:
    key_a = build_group_inference_key(
        source_db="utexas",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetA",
        publication="paper1",
    )
    key_b = build_group_inference_key(
        source_db="utexas",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetA",
        publication="paper2",
    )
    assert key_a != key_b


def test_plan_support_threshold_and_medium_confidence(plan_rules) -> None:
    constant = "AAAAAAAAAAAA"
    seqs = [
        constant + "CCCC",
        constant + "GGGG",
        constant + "UUUU",
        constant + "CCGG",
        constant + "GGCC",
    ]
    proposals = infer_group_constant_regions(
        _group_records("plan1", seqs), rules=plan_rules
    )
    five = next(p for p in proposals if p.side == "five_prime")
    assert five.length >= 12
    assert five.support >= 0.80
    assert five.confidence == "medium"
    assert five.status == QUALIFYING_TIER2_STATUS
    assert five.status != "high_confidence_proposal"


def test_plan_support_below_080_no_proposal(plan_rules) -> None:
    constant = "AAAAAAAAAAAA"
    seqs = [
        constant + "CCCC",
        constant + "GGGG",
        constant + "UUUU",
        "CCCCCCCCCCCCAAAA",
        "GGGGGGGGGGGGAAAA",
    ]
    proposals = infer_group_constant_regions(
        _group_records("plan2", seqs), rules=plan_rules
    )
    assert proposals == ()


def test_experiment_group_mode_requires_id() -> None:
    assert (
        build_group_inference_key(
            source_db="ena",
            grouping_mode=GROUP_INFERENCE_KEY_EXPERIMENT_GROUP,
            experiment_group_id=None,
            target_name_raw="t",
            publication="p",
        )
        is None
    )


def test_publication_preferred_over_pubmed_id() -> None:
    with_pub = build_group_inference_key(
        source_db="aptadb",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetA",
        publication="Paper A",
        pubmed_id="999",
    )
    pub_only = build_group_inference_key(
        source_db="aptadb",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetA",
        publication="Paper A",
        pubmed_id=None,
    )
    pmid_only = build_group_inference_key(
        source_db="aptadb",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetA",
        publication="",
        pubmed_id="999",
    )
    assert with_pub is not None
    assert with_pub == pub_only
    assert pmid_only is not None
    assert with_pub != pmid_only


def test_pubmed_id_fallback_when_publication_empty() -> None:
    key = build_group_inference_key(
        source_db="aptadb",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetA",
        publication="",
        pubmed_id="12345678",
    )
    assert key is not None
    assert key.startswith("aptadb:tgt_pub:")
    same = build_group_inference_key(
        source_db="aptadb",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetA",
        publication=None,
        pubmed_id="12345678",
    )
    assert key == same


def test_empty_target_prevents_pubmed_grouping() -> None:
    assert (
        build_group_inference_key(
            source_db="aptadb",
            grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
            target_name_raw="",
            publication="",
            pubmed_id="12345678",
        )
        is None
    )
    assert (
        build_group_inference_key(
            source_db="aptadb",
            grouping_mode=GROUP_INFERENCE_KEY_AUTO,
            experiment_group_id=None,
            target_name_raw=None,
            publication=None,
            pubmed_id="12345678",
        )
        is None
    )


def test_publication_identity_helper_does_not_invent_text() -> None:
    assert resolve_publication_identity(publication="Paper A", pubmed_id="999") == (
        "Paper A"
    )
    assert resolve_publication_identity(publication="", pubmed_id="999") == "999"
    assert resolve_publication_identity(publication=None, pubmed_id=None) is None
    assert resolve_publication_identity(publication="  ", pubmed_id="  ") is None


def test_utexas_publication_grouping_unchanged_when_publication_present() -> None:
    original = build_group_inference_key(
        source_db="utexas",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetX",
        publication="paperY",
    )
    with_unused_pmid = build_group_inference_key(
        source_db="utexas",
        grouping_mode=GROUP_INFERENCE_KEY_TARGET_PUBLICATION,
        target_name_raw="targetX",
        publication="paperY",
        pubmed_id="should_be_ignored",
    )
    assert original is not None
    assert original == with_unused_pmid
    assert original.startswith("utexas:tgt_pub:")

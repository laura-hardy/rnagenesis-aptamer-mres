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
    ConstantRegionInferenceError,
    InferenceRecord,
    apply_approved_trim,
    infer_group_constant_regions,
    proposal_to_trim_plan,
)
from common.sequence_normalisation import (  # noqa: E402
    TrimProposal,
    load_normalisation_rules,
    rules_to_public_dict,
    validate_rules_dict,
)


@pytest.fixture(scope="module")
def rules():
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


def test_29_high_support_five_prime_proposal(rules) -> None:
    # Shared 5′ AAAA (len 4) across five records; variable cores differ.
    seqs = [
        "AAAACCCC",
        "AAAAGGGG",
        "AAAAUUUU",
        "AAAACCGG",
        "AAAAGGCC",
    ]
    proposals = infer_group_constant_regions(_group_records("g1", seqs), rules=rules)
    five = [p for p in proposals if p.side == "five_prime" and p.experiment_group_id == "g1"]
    assert len(five) == 1
    assert five[0].status == "high_confidence_proposal"
    assert five[0].proposed_sequence == "AAAA"
    assert five[0].support >= 0.9


def test_30_high_support_three_prime_proposal(rules) -> None:
    seqs = [
        "CCCCAAAA",
        "GGGGAAAA",
        "UUUUAAAA",
        "CCGGAAAA",
        "GGCCAAAA",
    ]
    proposals = infer_group_constant_regions(_group_records("g2", seqs), rules=rules)
    three = [p for p in proposals if p.side == "three_prime"]
    assert three[0].status == "high_confidence_proposal"
    assert three[0].proposed_sequence == "AAAA"


def test_31_both_end_proposals(rules) -> None:
    seqs = [
        "AAAACCCCUUUU",
        "AAAAGGGGUUUU",
        "AAAAUUUUUUUU",
        "AAAACCGGUUUU",
        "AAAAGGCCUUUU",
    ]
    proposals = infer_group_constant_regions(_group_records("g3", seqs), rules=rules)
    by_side = {p.side: p for p in proposals if p.status == "high_confidence_proposal"}
    assert by_side["five_prime"].proposed_sequence == "AAAA"
    assert by_side["three_prime"].proposed_sequence == "UUUU"


def test_32_small_group_yields_no_proposal(rules) -> None:
    seqs = ["AAAACCCC", "AAAAGGGG", "AAAAUUUU"]
    proposals = infer_group_constant_regions(_group_records("g4", seqs), rules=rules)
    assert all(p.status == "insufficient_group_size" for p in proposals)
    assert all(p.proposed_sequence is None for p in proposals)


def test_33_support_below_threshold_stops_extension(rules) -> None:
    # Positions 0–3 agree; position 4 disagrees enough to stop before len 5.
    seqs = [
        "AAAACCCC",
        "AAAACGGG",
        "AAAACUUU",
        "AAAACCGG",
        "GGGGAAAA",  # breaks early consensus if extended carelessly; 4/5 on AAAA
    ]
    # First four share AAAA; fifth differs at 5′ — support for A = 0.8 < 0.9.
    proposals = infer_group_constant_regions(_group_records("g5", seqs), rules=rules)
    five = next(p for p in proposals if p.side == "five_prime")
    assert five.status in {"insufficient_support", "no_constant_region"}
    assert five.proposed_sequence is None


def test_34_maximum_inferred_length_respected(rules) -> None:
    tight = validate_rules_dict(
        {
            **rules_to_public_dict(rules),
            "constant_region_inference": {
                "minimum_group_size": 5,
                "minimum_support": 0.9,
                "minimum_region_length": 4,
                "maximum_region_length": 4,
            },
        }
    )
    # Identical 8-nt prefix would extend further if uncapped.
    seqs = [
        "AAAACCCCGG",
        "AAAACCCCUU",
        "AAAACCCCAA",
        "AAAACCCCGG",
        "AAAACCCCUU",
    ]
    proposals = infer_group_constant_regions(_group_records("g6", seqs), rules=tight)
    five = next(p for p in proposals if p.side == "five_prime")
    assert five.status == "high_confidence_proposal"
    assert five.length == 4
    assert five.proposed_sequence == "AAAA"


def test_35_missing_group_id_not_pooled(rules) -> None:
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
    proposals = infer_group_constant_regions(records, rules=rules)
    group_ids = {p.experiment_group_id for p in proposals}
    assert None not in group_ids
    assert "kept" in group_ids
    # Missing-group records must not create a pooled high-confidence AAAA proposal.
    assert not any(
        p.proposed_sequence == "AAAA" for p in proposals
    )


def test_36_invalid_missing_sequences_excluded_and_counted(rules) -> None:
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
    proposals = infer_group_constant_regions(records, rules=rules)
    five = next(p for p in proposals if p.side == "five_prime")
    assert five.records_excluded == 2
    assert five.status == "high_confidence_proposal"


def test_37_input_order_independence(rules) -> None:
    seqs = [
        "AAAACCCC",
        "AAAAGGGG",
        "AAAAUUUU",
        "AAAACCGG",
        "AAAAGGCC",
    ]
    forward = infer_group_constant_regions(_group_records("g8", seqs), rules=rules)
    reverse = infer_group_constant_regions(
        list(reversed(_group_records("g8", seqs))), rules=rules
    )
    assert forward == reverse


def test_38_exact_application_of_approved_inferred_trim(rules) -> None:
    seqs = [
        "AAAACCCC",
        "AAAAGGGG",
        "AAAAUUUU",
        "AAAACCGG",
        "AAAAGGCC",
    ]
    proposals = infer_group_constant_regions(_group_records("g9", seqs), rules=rules)
    five = next(p for p in proposals if p.side == "five_prime")
    plan = proposal_to_trim_plan(five)
    applied = apply_approved_trim(
        "AAAACCCC",
        molecule_type="RNA",
        trim_plan=plan,
        record_id="r0",
        rules=rules,
    )
    assert applied.matched is True
    assert applied.sequence_full == "AAAACCCC"
    assert applied.sequence_core == "CCCC"
    assert applied.applied_trims[0].side == "five_prime"


def test_39_nonmatching_record_remains_untrimmed_and_flagged(rules) -> None:
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
        rules=rules,
    )
    assert applied.matched is False
    assert applied.sequence_core == applied.sequence_full == "GGGGCCCC"
    assert applied.applied_trims == ()
    assert "trim_requires_review" in applied.qc_flags


def test_40_proposal_generation_does_not_mutate_inputs(rules) -> None:
    records = _group_records(
        "g10",
        ["AAAACCCC", "AAAAGGGG", "AAAAUUUU", "AAAACCGG", "AAAAGGCC"],
    )
    snapshot = copy.deepcopy(records)
    infer_group_constant_regions(records, rules=rules)
    assert records == snapshot


def test_41_multiple_experiment_groups_remain_separate(rules) -> None:
    records = _group_records(
        "alpha",
        ["AAAACCCC", "AAAAGGGG", "AAAAUUUU", "AAAACCGG", "AAAAGGCC"],
        id_prefix="a",
    ) + _group_records(
        "beta",
        ["GGGGCCCC", "GGGGGGGG", "GGGGUUUU", "GGGGCCGG", "GGGGGGCC"],
        id_prefix="b",
    )
    proposals = infer_group_constant_regions(records, rules=rules)
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


def test_42_no_constant_region_when_agreement_inadequate(rules) -> None:
    seqs = [
        "ACGUACGU",
        "UGCAUGCA",
        "GCGCGCGC",
        "CGCGCGCG",
        "AUAUAUAU",
    ]
    proposals = infer_group_constant_regions(_group_records("g11", seqs), rules=rules)
    assert all(p.proposed_sequence is None for p in proposals)
    assert all(
        p.status in {"insufficient_support", "no_constant_region"} for p in proposals
    )


def test_inference_record_typed_input(rules) -> None:
    records = [
        InferenceRecord("t0", "typed", "AAAACCCC"),
        InferenceRecord("t1", "typed", "AAAAGGGG"),
        InferenceRecord("t2", "typed", "AAAAUUUU"),
        InferenceRecord("t3", "typed", "AAAACCGG"),
        InferenceRecord("t4", "typed", "AAAAGGCC"),
    ]
    proposals = infer_group_constant_regions(records, rules=rules)
    five = next(p for p in proposals if p.side == "five_prime")
    assert five.proposed_sequence == "AAAA"


def test_unapproved_trim_plan_rejected(rules) -> None:
    plan = TrimProposal(
        five_prime="AAAA",
        reason="draft",
        confidence=0.5,
        source="test",
        status="requires_review",
    )
    with pytest.raises(ConstantRegionInferenceError):
        apply_approved_trim(
            "AAAACCCC", molecule_type="RNA", trim_plan=plan, rules=rules
        )


def test_no_stdout_on_inference(rules) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    records = _group_records(
        "g12",
        ["AAAACCCC", "AAAAGGGG", "AAAAUUUU", "AAAACCGG", "AAAAGGCC"],
    )
    with redirect_stdout(stdout), redirect_stderr(stderr):
        infer_group_constant_regions(records, rules=rules)
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""


def test_repeated_inference_identical(rules) -> None:
    records = _group_records(
        "g13",
        ["AAAACCCC", "AAAAGGGG", "AAAAUUUU", "AAAACCGG", "AAAAGGCC"],
    )
    a = infer_group_constant_regions(records, rules=rules)
    b = infer_group_constant_regions(records, rules=rules)
    assert a == b
    assert json.dumps([p.__dict__ for p in a], sort_keys=True) == json.dumps(
        [p.__dict__ for p in b], sort_keys=True
    )

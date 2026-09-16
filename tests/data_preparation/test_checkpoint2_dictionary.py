"""Synthetic tests for CHECKPOINT-2 inactive-target and override-identity semantics."""

from __future__ import annotations

import copy
import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.checkpoint2_dictionary import (  # noqa: E402
    EXACT_EXISTING_ORIGIN,
    HUMAN_DERIVED_ORIGIN,
    INACTIVE_REASON_PARKED_ONLY,
    INACTIVE_REASON_SUPERSEDED,
    build_effective_target_dictionary,
    exact_dictionary_matches,
    human_derived_target_dictionary_id,
    materialise_human_derived_target_review_rows,
    project_effective_target_relationships,
    resolve_override_dictionary_identity,
    validate_inactive_target_decision,
)
from adapters.s4_scientific_common import (  # noqa: E402
    HUMAN_FIELDS,
    INACTIVE_TARGET_DECISION,
    ScientificProposalError,
)
from checkpoint2_prepare_review import (  # noqa: E402
    TARGET_REVIEW_COLUMNS,
    prepare_checkpoint2_package,
)
from checkpoint2_validate_review import validate_checkpoint2_package  # noqa: E402


def _machine(
    record_id: str,
    raw_target: str,
    dictionary_id: str,
    *,
    index: str = "1",
    source_db: str = "synthetic",
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "relationship_index": index,
        "source_db": source_db,
        "raw_target": raw_target,
        "target_dictionary_id": dictionary_id,
        "target_type_proposed": "unknown",
        "uniprot_proposed": "",
        "target_family_proposed": "unknown",
        "record_expansion_proposed": "true",
        "relationship_status": "resolved_multiple",
        "requires_checkpoint2": "true",
    }


def _dictionary(did: str, name: str) -> dict[str, str]:
    return {
        "target_dictionary_id": did,
        "raw_target": name,
        "canonical_target_name_proposal": name,
        "canonicalisation_method": "most_frequent_whitespace_normalised_raw_string",
        "target_type_proposed": "small_molecule",
        "target_family_proposed": "other",
        "requires_checkpoint2": "true",
    }


def _review(
    decision_id: str,
    record_id: str,
    decision: str,
    **fields: str,
) -> dict[str, str]:
    row = {
        "decision_id": decision_id,
        "record_id": record_id,
        "manual_decision": decision,
        "manual_target_name": "",
        "manual_target_type": "",
        "manual_uniprot": "",
        "manual_target_family": "",
        "manual_pfam_interpro": "",
        "manual_relationship_action": "",
        "manual_notes": "",
    }
    row.update(fields)
    return row


def _target_review(decision_id: str, did: str, name: str, decision: str = "") -> dict[str, str]:
    row = {
        "decision_id": decision_id,
        "target_dictionary_id": did,
        "raw_target": name,
        "canonical_target_name_proposal": name,
        **{field: "" for field in HUMAN_FIELDS},
    }
    row["manual_decision"] = decision
    return row


def _write_review_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0].keys()), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _projected_bundle():
    machine = [
        _machine("synthetic:keep", "TOKEN_KEEP", "TD_KEEP", index="1"),
        _machine("synthetic:keep", "TOKEN_SUPERSEDED", "TD_SUPERSEDED", index="2"),
        _machine("synthetic:park", "TOKEN_PARKED", "TD_PARKED", index="1"),
        _machine("synthetic:park", "TOKEN_PARKED_SIBLING", "TD_PARKED_SIB", index="2"),
        _machine("synthetic:active", "TOKEN_ACTIVE", "TD_ACTIVE", index="1"),
        _machine("synthetic:active", "TOKEN_ACTIVE_ELSEWHERE", "TD_SHARED", index="2"),
        _machine("synthetic:shared_park", "TOKEN_ACTIVE_ELSEWHERE", "TD_SHARED", index="1"),
        _machine("synthetic:shared_park", "TOKEN_PARK_CONTEXT", "TD_PARK_CONTEXT", index="2"),
        _machine("synthetic:override", "TOKEN_FRAGMENT_A", "TD_FRAG_A", index="1"),
        _machine("synthetic:override", "TOKEN_FRAGMENT_B", "TD_FRAG_B", index="2"),
        _machine("synthetic:unreviewed", "TOKEN_UNRELATED", "TD_UNRELATED", index="1"),
    ]
    dictionary = [
        _dictionary("TD_KEEP", "TOKEN_KEEP"),
        _dictionary("TD_SUPERSEDED", "TOKEN_SUPERSEDED"),
        _dictionary("TD_PARKED", "TOKEN_PARKED"),
        _dictionary("TD_PARKED_SIB", "TOKEN_PARKED_SIBLING"),
        _dictionary("TD_ACTIVE", "TOKEN_ACTIVE"),
        _dictionary("TD_SHARED", "TOKEN_ACTIVE_ELSEWHERE"),
        _dictionary("TD_PARK_CONTEXT", "TOKEN_PARK_CONTEXT"),
        _dictionary("TD_FRAG_A", "TOKEN_FRAGMENT_A"),
        _dictionary("TD_FRAG_B", "TOKEN_FRAGMENT_B"),
        _dictionary("TD_UNRELATED", "TOKEN_UNRELATED"),
        _dictionary("TD_EXACT", "TOKEN_EXACT_LIGAND"),
    ]
    reviews = [
        _review("C2R_KEEP", "synthetic:keep", "reject_proposed_relationship"),
        _review("C2R_PARK", "synthetic:park", "park_unresolved"),
        _review("C2R_ACTIVE", "synthetic:active", "confirm_multi_target_expansion"),
        _review("C2R_SHARED", "synthetic:shared_park", "park_unresolved"),
        _review(
            "C2R_OV",
            "synthetic:override",
            "override",
            manual_target_name="TOKEN_NOVEL_LIGAND",
            manual_target_type="small_molecule",
        ),
    ]
    snapshot = copy.deepcopy(machine)
    projection, resolutions = project_effective_target_relationships(
        machine, reviews, dictionary, []
    )
    return machine, snapshot, dictionary, reviews, projection, resolutions


def test_inactive_action_allowed_when_zero_active_relationships() -> None:
    _machine_rows, _snap, _dictionary, _reviews, projection, _res = _projected_bundle()
    reason = validate_inactive_target_decision(
        _target_review("C2T_S", "TD_SUPERSEDED", "TOKEN_SUPERSEDED", INACTIVE_TARGET_DECISION),
        projection,
    )
    assert reason == INACTIVE_REASON_SUPERSEDED
    parked = validate_inactive_target_decision(
        _target_review("C2T_P", "TD_PARKED", "TOKEN_PARKED", INACTIVE_TARGET_DECISION),
        projection,
    )
    assert parked == INACTIVE_REASON_PARKED_ONLY


def test_inactive_action_rejected_when_active_elsewhere() -> None:
    _machine_rows, _snap, _dictionary, _reviews, projection, _res = _projected_bundle()
    with pytest.raises(ScientificProposalError, match="invalid for active dictionary TD_SHARED"):
        validate_inactive_target_decision(
            _target_review(
                "C2T_SHARED",
                "TD_SHARED",
                "TOKEN_ACTIVE_ELSEWHERE",
                INACTIVE_TARGET_DECISION,
            ),
            projection,
        )
    with pytest.raises(ScientificProposalError, match="invalid for active dictionary TD_KEEP"):
        validate_inactive_target_decision(
            _target_review("C2T_K", "TD_KEEP", "TOKEN_KEEP", INACTIVE_TARGET_DECISION),
            projection,
        )


def test_superseded_and_parked_only_excluded_from_effective_dictionary() -> None:
    machine, snapshot, dictionary, reviews, projection, resolutions = _projected_bundle()
    target_reviews = [
        _target_review("C2T_KEEP", "TD_KEEP", "TOKEN_KEEP", "approve_proposal"),
        _target_review("C2T_S", "TD_SUPERSEDED", "TOKEN_SUPERSEDED", INACTIVE_TARGET_DECISION),
        _target_review("C2T_P", "TD_PARKED", "TOKEN_PARKED", INACTIVE_TARGET_DECISION),
        _target_review("C2T_PS", "TD_PARKED_SIB", "TOKEN_PARKED_SIBLING", INACTIVE_TARGET_DECISION),
        _target_review("C2T_A", "TD_ACTIVE", "TOKEN_ACTIVE", "approve_proposal"),
        _target_review("C2T_U", "TD_UNRELATED", "TOKEN_UNRELATED", "override"),
        _target_review("C2T_PARKSCI", "TD_PARK_CONTEXT", "TOKEN_PARK_CONTEXT", "park_unresolved"),
        _target_review("C2T_FRAG", "TD_FRAG_A", "TOKEN_FRAGMENT_A", INACTIVE_TARGET_DECISION),
    ]
    target_reviews[5]["manual_target_name"] = "TOKEN_UNRELATED"
    target_reviews[5]["manual_target_type"] = "small_molecule"
    effective = build_effective_target_dictionary(
        dictionary, target_reviews, projection, resolutions
    )
    resolved_ids = {row["target_dictionary_id"] for row in effective.resolved_entries}
    inactive_ids = {row["target_dictionary_id"] for row in effective.inactive_entries}
    assert "TD_SUPERSEDED" not in resolved_ids
    assert "TD_PARKED" not in resolved_ids
    assert "TD_PARKED_SIB" not in resolved_ids
    assert "TD_FRAG_A" not in resolved_ids
    assert "TD_KEEP" in resolved_ids
    assert "TD_ACTIVE" in resolved_ids
    assert "TD_UNRELATED" in resolved_ids
    assert "TD_SUPERSEDED" in inactive_ids
    assert "TD_PARKED" in inactive_ids
    superseded = next(
        row for row in effective.inactive_entries if row["target_dictionary_id"] == "TD_SUPERSEDED"
    )
    parked = next(
        row for row in effective.inactive_entries if row["target_dictionary_id"] == "TD_PARKED"
    )
    assert superseded["_inactivity_reason"] == INACTIVE_REASON_SUPERSEDED
    assert parked["_inactivity_reason"] == INACTIVE_REASON_PARKED_ONLY
    assert any(
        item["target_dictionary_id"] == "TD_PARKED" and item["record_id"] == "synthetic:park"
        for item in effective.parked_only_provenance
    )
    assert not any(
        item["target_dictionary_id"] == "TD_SUPERSEDED"
        for item in effective.parked_only_provenance
    )
    assert machine == snapshot
    assert [row["raw_target"] for row in machine if row["target_dictionary_id"] == "TD_UNRELATED"] == [
        "TOKEN_UNRELATED"
    ]
    pending_names = {item.name for item in effective.human_derived_pending_review}
    assert "TOKEN_NOVEL_LIGAND" in pending_names
    assert "TD_UNRELATED" in resolved_ids


def test_existing_target_actions_unchanged() -> None:
    _machine_rows, _snap, dictionary, _reviews, projection, resolutions = _projected_bundle()
    target_reviews = [
        _target_review("C2T_KEEP", "TD_KEEP", "TOKEN_KEEP", "approve_proposal"),
        _target_review("C2T_U", "TD_UNRELATED", "TOKEN_UNRELATED", "override"),
        _target_review("C2T_PARKSCI", "TD_PARK_CONTEXT", "TOKEN_PARK_CONTEXT", "park_unresolved"),
    ]
    target_reviews[1]["manual_target_name"] = "TOKEN_UNRELATED"
    target_reviews[1]["manual_target_type"] = "small_molecule"
    effective = build_effective_target_dictionary(
        dictionary, target_reviews, projection, resolutions
    )
    by_id = {row["target_dictionary_id"]: row for row in effective.resolved_entries}
    assert by_id["TD_KEEP"]["_target_decision"] == "approve_proposal"
    assert by_id["TD_UNRELATED"]["_target_decision"] == "override"
    assert "TD_PARK_CONTEXT" not in by_id
    assert all(row["_target_decision"] != "park_unresolved" for row in effective.resolved_entries)


def test_exact_override_reuses_existing_dictionary_identity() -> None:
    dictionary = [_dictionary("TD_EXACT", "TOKEN_EXACT_LIGAND")]
    first = resolve_override_dictionary_identity(
        manual_target_name="TOKEN_EXACT_LIGAND",
        manual_target_type="small_molecule",
        relationship_decision_ids=["C2R_SYN_1"],
        dictionary_rows=dictionary,
        target_review_rows=[],
    )
    second = resolve_override_dictionary_identity(
        manual_target_name="TOKEN_EXACT_LIGAND",
        manual_target_type="small_molecule",
        relationship_decision_ids=["C2R_SYN_2"],
        dictionary_rows=dictionary,
        target_review_rows=[],
    )
    assert first.target_dictionary_id == "TD_EXACT"
    assert first.origin == EXACT_EXISTING_ORIGIN
    assert first.existing_dictionary_id_reused is True
    assert first.proposed_target_review_row is None
    assert first == second or first.target_dictionary_id == second.target_dictionary_id
    snapshot = copy.deepcopy(dictionary)
    assert dictionary == snapshot


def test_nonmatching_override_creates_deterministic_human_identity() -> None:
    dictionary = [
        _dictionary("TD_CAMP", "cAMP"),
        _dictionary("TD_CYCLIC", "Cyclic adenosine monophosphate"),
    ]
    snapshot = copy.deepcopy(dictionary)
    first = resolve_override_dictionary_identity(
        manual_target_name="TOKEN_3_PRIME_5_PRIME_CYCLIC",
        manual_target_type="small_molecule",
        relationship_decision_ids=["C2R_A", "C2R_B"],
        dictionary_rows=dictionary,
        target_review_rows=[],
    )
    second = resolve_override_dictionary_identity(
        manual_target_name="TOKEN_3_PRIME_5_PRIME_CYCLIC",
        manual_target_type="small_molecule",
        relationship_decision_ids=["C2R_B", "C2R_A"],
        dictionary_rows=dictionary,
        target_review_rows=[],
    )
    assert first.origin == HUMAN_DERIVED_ORIGIN
    assert first.existing_dictionary_id_reused is False
    assert first.target_dictionary_id.startswith("TDH")
    assert first.target_dictionary_id == second.target_dictionary_id
    assert first.target_dictionary_id == human_derived_target_dictionary_id(
        "TOKEN_3_PRIME_5_PRIME_CYCLIC", "small_molecule"
    )
    assert first.proposed_target_review_row is not None
    assert first.proposed_target_review_row["manual_decision"] == ""
    assert first.proposed_dictionary_row["target_type_proposed"] == "small_molecule"
    assert first.proposed_dictionary_row["target_family_proposed"] == "other"
    assert first.family_proposal == "other"
    assert "checkpoint2_relationship_override" in first.proposed_dictionary_row["resolution_provenance"]
    assert dictionary == snapshot
    assert exact_dictionary_matches(
        "TOKEN_3_PRIME_5_PRIME_CYCLIC", dictionary, []
    ) == []
    assert exact_dictionary_matches("cAMP", dictionary, []) == ["TD_CAMP"]
    assert exact_dictionary_matches("camp", dictionary, []) == []
    assert exact_dictionary_matches("Cyclic adenosine monophosphate", dictionary, []) == [
        "TD_CYCLIC"
    ]


def test_no_fuzzy_merge_and_unrelated_identities_unchanged() -> None:
    dictionary = [
        _dictionary("TD_CAMP", "cAMP"),
        _dictionary("TD_CYCLIC", "Cyclic adenosine monophosphate"),
        _dictionary("TD_OTHER", "TOKEN_UNRELATED_STABLE"),
    ]
    snapshot = copy.deepcopy(dictionary)
    resolution = resolve_override_dictionary_identity(
        manual_target_name="3',5'-cyclic adenosine monophosphate (cAMP)",
        manual_target_type="small_molecule",
        relationship_decision_ids=["C2R_CAMP"],
        dictionary_rows=dictionary,
        target_review_rows=[
            _target_review("C2T_CAMP", "TD_CAMP", "cAMP", "approve_proposal")
        ],
    )
    assert resolution.origin == HUMAN_DERIVED_ORIGIN
    assert resolution.target_dictionary_id not in {"TD_CAMP", "TD_CYCLIC", "TD_OTHER"}
    assert dictionary == snapshot
    assert [row["target_dictionary_id"] for row in dictionary] == [
        "TD_CAMP",
        "TD_CYCLIC",
        "TD_OTHER",
    ]
    machine = [
        _machine("synthetic:override", "cAMP", "TD_CAMP", index="1"),
        _machine("synthetic:override", "Cyclic adenosine monophosphate", "TD_CYCLIC", index="2"),
        _machine("synthetic:stable", "TOKEN_UNRELATED_STABLE", "TD_OTHER", index="1"),
    ]
    machine_snapshot = copy.deepcopy(machine)
    projection, resolutions = project_effective_target_relationships(
        machine,
        [
            _review(
                "C2R_CAMP",
                "synthetic:override",
                "override",
                manual_target_name="3',5'-cyclic adenosine monophosphate (cAMP)",
                manual_target_type="small_molecule",
            )
        ],
        dictionary,
        [],
    )
    assert machine == machine_snapshot
    override_ids = {
        row["target_dictionary_id"]
        for row in projection.effective_resolved
        if row["record_id"] == "synthetic:override"
    }
    stable_ids = {
        row["target_dictionary_id"]
        for row in projection.effective_resolved
        if row["record_id"] == "synthetic:stable"
    }
    assert override_ids == {resolution.target_dictionary_id}
    assert stable_ids == {"TD_OTHER"}
    assert resolutions[0].target_dictionary_id == resolution.target_dictionary_id


def test_validator_rejects_inactive_action_on_active_target(tmp_path: Path) -> None:
    prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[
            {
                "target_dictionary_id": "TD_SHARED",
                "raw_target": "TOKEN_ACTIVE_ELSEWHERE",
                "source_keys": "synthetic",
                "n_records": "1",
                "canonical_target_name_proposal": "TOKEN_ACTIVE_ELSEWHERE",
                "uniprot_proposed": "",
                "uniprot_candidates": "",
                "target_type_proposed": "unknown",
                "target_family_proposed": "unknown",
                "target_pfam_proposed": "",
                "target_interpro_proposed": "",
                "proposal_confidence": "low",
                "resolution_provenance": "",
                "scientific_ambiguity_reason": "",
                "machine_recommendation": "review_required",
                "requires_checkpoint2": "true",
            }
        ],
        relationship_rows=[],
        extraction_rows=[],
        evidence_rows=[],
        leakage_rows=[],
        routing_rows=[],
    )
    path = tmp_path / "cp2" / "checkpoint2_target_dictionary_review.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rows[0]["manual_decision"] = INACTIVE_TARGET_DECISION
    _write_review_csv(path, rows)
    machine = [
        _machine("synthetic:live", "TOKEN_ACTIVE_ELSEWHERE", "TD_SHARED", index="1"),
        _machine("synthetic:live", "TOKEN_OTHER", "TD_OTHER", index="2"),
    ]
    result = validate_checkpoint2_package(
        tmp_path / "cp2",
        machine_relationship_rows=machine,
        dictionary_rows=[_dictionary("TD_SHARED", "TOKEN_ACTIVE_ELSEWHERE")],
    )
    assert result["ready_for_application"] is False
    assert any("invalid for active dictionary TD_SHARED" in item for item in result["errors"])


def test_validator_accepts_inactive_action_when_invariant_holds(tmp_path: Path) -> None:
    prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[
            {
                "target_dictionary_id": "TD_SUPERSEDED",
                "raw_target": "TOKEN_SUPERSEDED",
                "source_keys": "synthetic",
                "n_records": "1",
                "canonical_target_name_proposal": "TOKEN_SUPERSEDED",
                "uniprot_proposed": "",
                "uniprot_candidates": "",
                "target_type_proposed": "unknown",
                "target_family_proposed": "unknown",
                "target_pfam_proposed": "",
                "target_interpro_proposed": "",
                "proposal_confidence": "low",
                "resolution_provenance": "",
                "scientific_ambiguity_reason": "",
                "machine_recommendation": "review_required",
                "requires_checkpoint2": "true",
            }
        ],
        relationship_rows=[
            {
                "record_id": "synthetic:keep",
                "source_db": "synthetic",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "raw_target": "TOKEN_KEEP",
                "target_dictionary_id": "TD_KEEP",
                "requires_checkpoint2": "true",
            },
            {
                "record_id": "synthetic:keep",
                "source_db": "synthetic",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "raw_target": "TOKEN_SUPERSEDED",
                "target_dictionary_id": "TD_SUPERSEDED",
                "requires_checkpoint2": "true",
            },
        ],
        extraction_rows=[
            {
                "record_id": "synthetic:keep",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "ambiguity_reason": "",
            }
        ],
        evidence_rows=[
            {
                "record_id": "synthetic:e1",
                "source_db": "synthetic",
                "evidence_rule": "SYNTHETIC_E4_E5",
                "evidence_level_proposed": "E5",
                "alternative_evidence_level": "E4",
                "e4_e5_threshold_ambiguous": "true",
                "evidence_requires_review": "true",
                "evidence_provenance": "synthetic",
                "affinity_requires_review": "false",
                "affinity_parse_status": "absent",
            }
        ],
        leakage_rows=[],
        routing_rows=[],
    )
    target_path = tmp_path / "cp2" / "checkpoint2_target_dictionary_review.csv"
    targets = list(csv.DictReader(target_path.open(newline="", encoding="utf-8")))
    targets[0]["manual_decision"] = INACTIVE_TARGET_DECISION
    _write_review_csv(target_path, targets)
    rel_path = tmp_path / "cp2" / "checkpoint2_relationship_review.csv"
    rels = list(csv.DictReader(rel_path.open(newline="", encoding="utf-8")))
    rels[0]["manual_decision"] = "reject_proposed_relationship"
    _write_review_csv(rel_path, rels)
    machine = [
        _machine("synthetic:keep", "TOKEN_KEEP", "TD_KEEP", index="1"),
        _machine("synthetic:keep", "TOKEN_SUPERSEDED", "TD_SUPERSEDED", index="2"),
    ]
    result = validate_checkpoint2_package(
        tmp_path / "cp2",
        machine_relationship_rows=machine,
        dictionary_rows=[
            _dictionary("TD_KEEP", "TOKEN_KEEP"),
            _dictionary("TD_SUPERSEDED", "TOKEN_SUPERSEDED"),
        ],
    )
    assert result["errors"] == []
    assert result["target_completion"][INACTIVE_TARGET_DECISION] == 1
    assert result["target_completion"][INACTIVE_REASON_SUPERSEDED] == 1
    assert result["ready_for_application"] is False
    assert result["unresolved_decisions"] > 0


def test_inactive_action_not_valid_on_relationship_file(tmp_path: Path) -> None:
    prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[],
        relationship_rows=[
            {
                "record_id": "synthetic:alpha",
                "source_db": "synthetic",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "raw_target": "TOKEN_ALPHA",
                "target_dictionary_id": "TD_A",
                "requires_checkpoint2": "true",
            }
        ],
        extraction_rows=[
            {
                "record_id": "synthetic:alpha",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "ambiguity_reason": "",
            }
        ],
        evidence_rows=[],
        leakage_rows=[],
        routing_rows=[],
    )
    path = tmp_path / "cp2" / "checkpoint2_relationship_review.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rows[0]["manual_decision"] = INACTIVE_TARGET_DECISION
    _write_review_csv(path, rows)
    result = validate_checkpoint2_package(tmp_path / "cp2")
    assert any("target-dictionary action" in item for item in result["errors"])


def test_two_overrides_materialise_one_idempotent_human_derived_row() -> None:
    camp_name = "3',5'-cyclic adenosine monophosphate (cAMP)"
    dictionary = [
        _dictionary("TD_CAMP", "cAMP"),
        _dictionary("TD_CYCLIC", "Cyclic adenosine monophosphate"),
        _dictionary("TD_FRAG_A", "TOKEN_3_PRIME"),
        _dictionary("TD_FRAG_B", "TOKEN_5_PRIME_CAMP"),
        _dictionary("TD_EXACT", "TOKEN_EXACT_LIGAND"),
        _dictionary("TD_STABLE", "TOKEN_UNRELATED_STABLE"),
    ]
    dictionary_snapshot = copy.deepcopy(dictionary)
    machine = [
        _machine("synthetic:camp_a", "TOKEN_3_PRIME", "TD_FRAG_A", index="1"),
        _machine("synthetic:camp_a", "TOKEN_5_PRIME_CAMP", "TD_FRAG_B", index="2"),
        _machine("synthetic:camp_b", "TOKEN_3_PRIME", "TD_FRAG_A", index="1"),
        _machine("synthetic:camp_b", "TOKEN_5_PRIME_CAMP", "TD_FRAG_B", index="2"),
        _machine("synthetic:exact", "TOKEN_OTHER_FRAG", "TD_OTHER_FRAG", index="1"),
        _machine("synthetic:stable", "TOKEN_UNRELATED_STABLE", "TD_STABLE", index="1"),
    ]
    reviews = [
        _review(
            "C2R_CAMP_A",
            "synthetic:camp_a",
            "override",
            manual_target_name=camp_name,
            manual_target_type="small_molecule",
        ),
        _review(
            "C2R_CAMP_B",
            "synthetic:camp_b",
            "override",
            manual_target_name=camp_name,
            manual_target_type="small_molecule",
        ),
        _review(
            "C2R_EXACT",
            "synthetic:exact",
            "override",
            manual_target_name="TOKEN_EXACT_LIGAND",
            manual_target_type="small_molecule",
        ),
    ]
    existing_reviews = [
        _target_review("C2T_CAMP", "TD_CAMP", "cAMP", "approve_proposal"),
        _target_review("C2T_CYCLIC", "TD_CYCLIC", "Cyclic adenosine monophosphate"),
        _target_review("C2T_FRAG_A", "TD_FRAG_A", "TOKEN_3_PRIME", INACTIVE_TARGET_DECISION),
        _target_review("C2T_FRAG_B", "TD_FRAG_B", "TOKEN_5_PRIME_CAMP", INACTIVE_TARGET_DECISION),
        _target_review("C2T_EXACT", "TD_EXACT", "TOKEN_EXACT_LIGAND", "approve_proposal"),
        _target_review("C2T_STABLE", "TD_STABLE", "TOKEN_UNRELATED_STABLE", "approve_proposal"),
    ]
    assert exact_dictionary_matches(camp_name, dictionary, existing_reviews) == []

    projection, resolutions = project_effective_target_relationships(
        machine, reviews, dictionary, existing_reviews
    )
    human_derived = [item for item in resolutions if item.origin == HUMAN_DERIVED_ORIGIN]
    reused = [item for item in resolutions if item.origin == EXACT_EXISTING_ORIGIN]
    assert len(human_derived) == 1
    assert human_derived[0].name == camp_name
    assert human_derived[0].target_type == "small_molecule"
    assert human_derived[0].family_proposal == "other"
    assert human_derived[0].target_dictionary_id == human_derived_target_dictionary_id(
        camp_name, "small_molecule"
    )
    provenance = human_derived[0].proposed_dictionary_row["resolution_provenance"]
    assert "C2R_CAMP_A" in provenance
    assert "C2R_CAMP_B" in provenance
    assert {item.target_dictionary_id for item in reused} == {"TD_EXACT"}
    override_ids = {
        row["target_dictionary_id"]
        for row in projection.effective_resolved
        if row["record_id"] in {"synthetic:camp_a", "synthetic:camp_b"}
    }
    assert override_ids == {human_derived[0].target_dictionary_id}

    first_rows, first_added = materialise_human_derived_target_review_rows(
        existing_reviews, resolutions, columns=TARGET_REVIEW_COLUMNS
    )
    assert len(first_added) == 1
    assert len(first_rows) == len(existing_reviews) + 1
    added = first_added[0]
    assert added["decision_id"].startswith("C2TH")
    assert added["target_dictionary_id"] == human_derived[0].target_dictionary_id
    assert added["canonical_target_name_proposal"] == camp_name
    assert added["target_type_proposed"] == "small_molecule"
    assert added["target_family_proposed"] == "other"
    assert added["uniprot_proposed"] == ""
    assert added["target_pfam_proposed"] == ""
    assert added["target_interpro_proposed"] == ""
    assert added["manual_decision"] == ""
    assert added["scientific_ambiguity_reason"] == HUMAN_DERIVED_ORIGIN
    existing_ids = {row["decision_id"] for row in existing_reviews}
    assert [row["decision_id"] for row in first_rows if row["decision_id"] in existing_ids] == [
        row["decision_id"] for row in existing_reviews
    ]

    second_rows, second_added = materialise_human_derived_target_review_rows(
        first_rows, resolutions, columns=TARGET_REVIEW_COLUMNS
    )
    assert second_added == ()
    assert [row["decision_id"] for row in second_rows] == [
        row["decision_id"] for row in first_rows
    ]
    assert sum(
        1
        for row in second_rows
        if row["target_dictionary_id"] == human_derived[0].target_dictionary_id
    ) == 1

    reviewed = [dict(row) for row in first_rows]
    new_row = next(
        row
        for row in reviewed
        if row["target_dictionary_id"] == human_derived[0].target_dictionary_id
    )
    new_row["manual_decision"] = "approve_proposal"
    new_row["manual_notes"] = "retain-me"
    third_rows, third_added = materialise_human_derived_target_review_rows(
        reviewed, resolutions, columns=TARGET_REVIEW_COLUMNS
    )
    assert third_added == ()
    retained = next(
        row
        for row in third_rows
        if row["target_dictionary_id"] == human_derived[0].target_dictionary_id
    )
    assert retained["manual_decision"] == "approve_proposal"
    assert retained["manual_notes"] == "retain-me"
    assert retained["manual_target_name"] == ""

    effective = build_effective_target_dictionary(
        dictionary, third_rows, projection, resolutions
    )
    resolved_by_id = {row["target_dictionary_id"]: row for row in effective.resolved_entries}
    camp_id = human_derived[0].target_dictionary_id
    assert camp_id in resolved_by_id
    assert resolved_by_id[camp_id]["canonical_target_name_proposal"] == camp_name
    assert resolved_by_id[camp_id]["target_type_proposed"] == "small_molecule"
    assert resolved_by_id[camp_id]["target_family_proposed"] == "other"
    assert resolved_by_id[camp_id]["_target_decision"] == "approve_proposal"
    assert "TD_CAMP" in resolved_by_id
    assert "TD_EXACT" in resolved_by_id
    assert "TD_STABLE" in resolved_by_id
    assert "TD_FRAG_A" not in resolved_by_id
    assert "TD_FRAG_B" not in resolved_by_id
    assert "TD_CYCLIC" not in resolved_by_id
    inactive_ids = {row["target_dictionary_id"] for row in effective.inactive_entries}
    assert inactive_ids == {"TD_FRAG_A", "TD_FRAG_B"}
    assert effective.human_derived_pending_review == ()
    assert dictionary == dictionary_snapshot
    assert exact_dictionary_matches(camp_name, dictionary, third_rows) == []
    assert exact_dictionary_matches("cAMP", dictionary, third_rows) == ["TD_CAMP"]
    assert exact_dictionary_matches(
        "Cyclic adenosine monophosphate", dictionary, third_rows
    ) == ["TD_CYCLIC"]

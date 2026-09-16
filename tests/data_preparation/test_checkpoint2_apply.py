"""Synthetic tests for CHECKPOINT-2 application. Does not start S5."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.checkpoint2_apply import (  # noqa: E402
    apply_checkpoint2_reviews,
    s5_duplicate_diagnostics,
)
from adapters.s4_scientific_common import HUMAN_FIELDS  # noqa: E402
from common.eligibility import SequenceLeakageIndex  # noqa: E402


def _combined(record_id: str, source: str = "synthetic", **fields: str) -> dict[str, str]:
    row = {
        "record_id": record_id,
        "source_db": source,
        "native_id": record_id.split(":", 1)[-1],
        "sequence_full": "",
        "sequence_core": "",
        "molecule_type": "RNA",
        "chemistry": "",
        "publication": "",
        "doi": "",
        "pubmed_id": "",
        "accession": "",
        "target_name_raw": fields.get("target_name_raw", "VEGF"),
    }
    row.update(fields)
    return row


def _machine_rel(
    record_id: str,
    raw: str,
    did: str,
    *,
    index: str = "1",
    source: str = "synthetic",
    rel_status: str = "resolved_single",
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "relationship_index": index,
        "source_db": source,
        "raw_target": raw,
        "target_dictionary_id": did,
        "target_type_proposed": "protein",
        "uniprot_proposed": "P15692",
        "target_family_proposed": "growth_factor",
        "target_pfam_proposed": "",
        "target_interpro_proposed": "",
        "target_provenance_source": "synthetic",
        "target_provenance_locator": "",
        "target_region_or_fragment": "",
        "relationship_status": rel_status,
        "record_expansion_proposed": "true" if rel_status == "resolved_multiple" else "false",
        "requires_checkpoint2": "true",
    }


def _dictionary(did: str, name: str, *, target_type: str = "protein", family: str = "growth_factor") -> dict[str, str]:
    return {
        "target_dictionary_id": did,
        "raw_target": name,
        "canonical_target_name_proposal": name,
        "canonicalisation_method": "most_frequent_whitespace_normalised_raw_string",
        "target_type_proposed": target_type,
        "target_family_proposed": family,
        "uniprot_proposed": "P15692" if target_type == "protein" else "",
        "target_pfam_proposed": "",
        "target_interpro_proposed": "",
        "requires_checkpoint2": "false",
        "resolution_provenance": "synthetic",
    }


def _rel_review(decision_id: str, record_id: str, decision: str, **fields: str) -> dict[str, str]:
    row = {
        "decision_id": decision_id,
        "record_id": record_id,
        **{field: "" for field in HUMAN_FIELDS},
        "manual_decision": decision,
    }
    row.update(fields)
    return row


def _target_review(decision_id: str, did: str, name: str, decision: str, **fields: str) -> dict[str, str]:
    row = {
        "decision_id": decision_id,
        "target_dictionary_id": did,
        "raw_target": name,
        "canonical_target_name_proposal": name,
        "target_type_proposed": "protein",
        "target_family_proposed": "growth_factor",
        **{field: "" for field in HUMAN_FIELDS},
        "manual_decision": decision,
    }
    row.update(fields)
    return row


def _evidence(
    record_id: str,
    level: str,
    *,
    source: str = "synthetic",
    raw: str = "",
    unit: str = "",
    molar: str = "",
    parse_status: str = "absent",
    requires_review: str = "false",
    rule: str = "SYNTHETIC",
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "relationship_index": "1",
        "source_db": source,
        "evidence_level_proposed": level,
        "evidence_rule": rule,
        "evidence_provenance": "synthetic",
        "alternative_evidence_level": "",
        "e4_e5_threshold_ambiguous": "false",
        "affinity_value_raw": raw,
        "affinity_unit_raw": unit,
        "affinity_value_molar_proposed": molar,
        "affinity_parse_status": parse_status,
        "affinity_parse_rule": "",
        "affinity_type_proposed": "Kd" if raw else "",
        "affinity_requires_review": requires_review,
    }


def _apply(**kwargs):
    kwargs.setdefault("evidence_review_rows", [])
    kwargs.setdefault("evidence_consistency_rows", [])
    kwargs.setdefault("affinity_review_rows", [])
    kwargs.setdefault("leakage_review_rows", [])
    kwargs.setdefault("leakage_index", SequenceLeakageIndex())
    kwargs.setdefault("alias_rules", ())
    kwargs.setdefault("require_camp_identity", False)
    return apply_checkpoint2_reviews(**kwargs)


def test_confirm_expansion_keeps_two_relationships() -> None:
    result = _apply(
        combined_rows=[_combined("synthetic:multi")],
        machine_relationship_rows=[
            _machine_rel("synthetic:multi", "p50", "TD_P50", index="1", rel_status="resolved_multiple"),
            _machine_rel("synthetic:multi", "p65", "TD_P65", index="2", rel_status="resolved_multiple"),
        ],
        dictionary_rows=[_dictionary("TD_P50", "p50"), _dictionary("TD_P65", "p65")],
        evidence_rows=[_evidence("synthetic:multi", "E4")],
        target_review_rows=[
            _target_review("C2T1", "TD_P50", "p50", "approve_proposal"),
            _target_review("C2T2", "TD_P65", "p65", "approve_proposal"),
        ],
        relationship_review_rows=[
            _rel_review("C2R1", "synthetic:multi", "confirm_multi_target_expansion")
        ],
    )
    assert result.validation["ok"] is True
    assert len(result.reviewed_relationships) == 2
    assert {row["target_dictionary_id"] for row in result.reviewed_relationships} == {
        "TD_P50",
        "TD_P65",
    }
    assert result.record_map[0]["n_effective_relationships"] == "2"


def test_reject_keeps_index_one_only() -> None:
    result = _apply(
        combined_rows=[_combined("synthetic:reject")],
        machine_relationship_rows=[
            _machine_rel("synthetic:reject", "keep", "TD_KEEP", index="1", rel_status="resolved_multiple"),
            _machine_rel("synthetic:reject", "drop", "TD_DROP", index="2", rel_status="resolved_multiple"),
        ],
        dictionary_rows=[_dictionary("TD_KEEP", "keep"), _dictionary("TD_DROP", "drop")],
        evidence_rows=[_evidence("synthetic:reject", "E3")],
        target_review_rows=[
            _target_review("C2T1", "TD_KEEP", "keep", "approve_proposal"),
            _target_review("C2T2", "TD_DROP", "drop", "exclude_no_active_relationship"),
        ],
        relationship_review_rows=[
            _rel_review("C2R1", "synthetic:reject", "reject_proposed_relationship")
        ],
    )
    assert [row["target_dictionary_id"] for row in result.reviewed_relationships] == ["TD_KEEP"]
    inactive = [row for row in result.reviewed_dictionary if row["target_dictionary_id"] == "TD_DROP"]
    assert inactive == []


def test_relationship_park_has_zero_active_rows() -> None:
    result = _apply(
        combined_rows=[_combined("synthetic:park")],
        machine_relationship_rows=[
            _machine_rel("synthetic:park", "ambiguous", "TD_AMB"),
        ],
        dictionary_rows=[_dictionary("TD_AMB", "ambiguous")],
        evidence_rows=[_evidence("synthetic:park", "E4")],
        target_review_rows=[
            _target_review("C2T1", "TD_AMB", "ambiguous", "exclude_no_active_relationship")
        ],
        relationship_review_rows=[
            _rel_review("C2R1", "synthetic:park", "park_unresolved")
        ],
    )
    assert result.reviewed_relationships == []
    assert result.record_map[0]["s4_record_outcome"] == "relationship_parked"
    assert any(row["audit_class"] == "relationship_parked" for row in result.parked_audit)


def test_target_park_is_not_an_active_relationship() -> None:
    result = _apply(
        combined_rows=[_combined("synthetic:tpark")],
        machine_relationship_rows=[_machine_rel("synthetic:tpark", "HCV polyprotein", "TD_HCV")],
        dictionary_rows=[_dictionary("TD_HCV", "HCV polyprotein")],
        evidence_rows=[_evidence("synthetic:tpark", "E2")],
        target_review_rows=[
            _target_review("C2T1", "TD_HCV", "HCV polyprotein", "park_unresolved")
        ],
        relationship_review_rows=[],
    )
    assert result.reviewed_relationships == []
    assert result.record_map[0]["s4_record_outcome"] == "target_parked"
    assert all(
        row["target_dictionary_id"] != "TD_HCV" for row in result.reviewed_relationships
    )


def test_no_binding_is_rejected_not_primary() -> None:
    result = _apply(
        combined_rows=[_combined("synthetic:nobind")],
        machine_relationship_rows=[_machine_rel("synthetic:nobind", "MBNL1", "TD_MBNL")],
        dictionary_rows=[_dictionary("TD_MBNL", "MBNL1")],
        evidence_rows=[
            _evidence(
                "synthetic:nobind",
                "E5",
                raw="no binding",
                parse_status="malformed",
                requires_review="true",
            )
        ],
        target_review_rows=[
            _target_review("C2T1", "TD_MBNL", "MBNL1", "approve_proposal")
        ],
        relationship_review_rows=[],
        affinity_review_rows=[
            {
                "decision_id": "C2A0010",
                "source_db": "synthetic",
                "affinity_parse_status": "malformed",
                "affinity_parse_rule": "",
                "affinity_subgroup": "no_binding",
                "record_ids": "synthetic:nobind",
                "manual_decision": "exclude_non_affinity",
                "manual_affinity_non_affinity_reason": "no_binding",
                "manual_affinity_type": "",
                "manual_affinity_value": "",
                "manual_affinity_unit": "",
                "manual_affinity_transform_rule": "",
                "manual_affinity_qualifier": "",
                "manual_affinity_range_status": "",
            }
        ],
    )
    assert len(result.reviewed_relationships) == 1
    assert result.reviewed_relationships[0]["s4_route"] == "reject_no_binding_evidence"
    assert result.reviewed_relationships[0]["canonical_affinity_value"] == ""
    assert result.reviewed_relationships[0]["non_affinity_reason"] == "no_binding"


def test_e5_is_not_primary() -> None:
    result = _apply(
        combined_rows=[_combined("synthetic:e5")],
        machine_relationship_rows=[_machine_rel("synthetic:e5", "VEGF", "TD_VEGF")],
        dictionary_rows=[_dictionary("TD_VEGF", "VEGF")],
        evidence_rows=[_evidence("synthetic:e5", "E5")],
        target_review_rows=[_target_review("C2T1", "TD_VEGF", "VEGF", "approve_proposal")],
        relationship_review_rows=[],
    )
    assert result.reviewed_relationships[0]["s4_route"] == "park_evidence_e5"


def test_non_protein_parks() -> None:
    result = _apply(
        combined_rows=[_combined("synthetic:theoph")],
        machine_relationship_rows=[
            _machine_rel("synthetic:theoph", "Theophylline", "TD_THEO")
        ],
        dictionary_rows=[
            _dictionary("TD_THEO", "Theophylline", target_type="small_molecule", family="other")
        ],
        evidence_rows=[_evidence("synthetic:theoph", "E2", raw="10 nM", unit="nM", molar="1e-8", parse_status="normalised")],
        target_review_rows=[
            _target_review(
                "C2T1",
                "TD_THEO",
                "Theophylline",
                "override",
                manual_target_name="Theophylline",
                manual_target_type="small_molecule",
                manual_target_family="other",
            )
        ],
        relationship_review_rows=[],
    )
    row = result.reviewed_relationships[0]
    assert row["s4_route"] == "park_non_protein"
    assert row["target_type"] == "small_molecule"
    assert row["canonical_affinity_value"] == "1e-8"


def test_equal_canonical_names_are_not_merged() -> None:
    result = _apply(
        combined_rows=[
            _combined("synthetic:a"),
            _combined("synthetic:b"),
        ],
        machine_relationship_rows=[
            _machine_rel("synthetic:a", "Apramycin", "TD_APRA1"),
            _machine_rel("synthetic:b", "Apramycin", "TD_APRA2"),
        ],
        dictionary_rows=[
            _dictionary("TD_APRA1", "Apramycin", target_type="small_molecule", family="other"),
            _dictionary("TD_APRA2", "Apramycin", target_type="small_molecule", family="other"),
        ],
        evidence_rows=[
            _evidence("synthetic:a", "E3"),
            _evidence("synthetic:b", "E3"),
        ],
        target_review_rows=[
            _target_review(
                "C2T1",
                "TD_APRA1",
                "Apramycin",
                "override",
                manual_target_name="Apramycin",
                manual_target_type="small_molecule",
                manual_target_family="other",
            ),
            _target_review(
                "C2T2",
                "TD_APRA2",
                "Apramycin",
                "override",
                manual_target_name="Apramycin",
                manual_target_type="small_molecule",
                manual_target_family="other",
            ),
        ],
        relationship_review_rows=[],
    )
    ids = [row["target_dictionary_id"] for row in result.reviewed_relationships]
    assert ids == ["TD_APRA1", "TD_APRA2"]
    diag = s5_duplicate_diagnostics(result.reviewed_relationships)
    assert diag["s5_operations_run"] is False
    assert diag["label"] == "S5 diagnostic only"


def test_application_is_idempotent() -> None:
    kwargs = dict(
        combined_rows=[_combined("synthetic:id")],
        machine_relationship_rows=[_machine_rel("synthetic:id", "VEGF", "TD_VEGF")],
        dictionary_rows=[_dictionary("TD_VEGF", "VEGF")],
        evidence_rows=[_evidence("synthetic:id", "E2")],
        target_review_rows=[_target_review("C2T1", "TD_VEGF", "VEGF", "approve_proposal")],
        relationship_review_rows=[],
        require_camp_identity=False,
    )
    first = _apply(**copy.deepcopy(kwargs))
    second = _apply(**copy.deepcopy(kwargs))
    assert first.reviewed_relationships == second.reviewed_relationships
    assert first.record_map == second.record_map
    assert first.reviewed_dictionary == second.reviewed_dictionary


def test_unresolved_source_record_is_documented() -> None:
    result = _apply(
        combined_rows=[_combined("synthetic:none")],
        machine_relationship_rows=[],
        dictionary_rows=[],
        evidence_rows=[_evidence("synthetic:none", "E5")],
        target_review_rows=[],
        relationship_review_rows=[],
    )
    assert result.record_map[0]["s4_record_outcome"] == "unresolved_no_relationship"
    assert result.reviewed_relationships == []


def test_every_input_record_has_an_outcome() -> None:
    result = _apply(
        combined_rows=[
            _combined("synthetic:keep"),
            _combined("synthetic:park"),
            _combined("synthetic:none"),
        ],
        machine_relationship_rows=[
            _machine_rel("synthetic:keep", "VEGF", "TD_VEGF"),
            _machine_rel("synthetic:park", "amb", "TD_AMB"),
        ],
        dictionary_rows=[_dictionary("TD_VEGF", "VEGF"), _dictionary("TD_AMB", "amb")],
        evidence_rows=[
            _evidence("synthetic:keep", "E2"),
            _evidence("synthetic:park", "E4"),
            _evidence("synthetic:none", "E5"),
        ],
        target_review_rows=[
            _target_review("C2T1", "TD_VEGF", "VEGF", "approve_proposal"),
            _target_review("C2T2", "TD_AMB", "amb", "exclude_no_active_relationship"),
        ],
        relationship_review_rows=[
            _rel_review("C2R1", "synthetic:park", "park_unresolved"),
        ],
    )
    assert [row["record_id"] for row in result.record_map] == [
        "synthetic:keep",
        "synthetic:park",
        "synthetic:none",
    ]
    outcomes = {row["record_id"]: row["s4_record_outcome"] for row in result.record_map}
    assert outcomes["synthetic:keep"] == "primary_candidate"
    assert outcomes["synthetic:park"] == "relationship_parked"
    assert outcomes["synthetic:none"] == "unresolved_no_relationship"

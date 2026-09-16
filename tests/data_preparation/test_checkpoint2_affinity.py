"""Synthetic tests for CHECKPOINT-2 affinity review semantics."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.checkpoint2_affinity import (  # noqa: E402
    AFFINITY_REVIEW_STATUS_EXACT,
    AFFINITY_REVIEW_STATUS_EXCLUDE,
    AFFINITY_REVIEW_STATUS_RAW,
    SUBGROUP_BINDING_PERCENTAGE,
    SUBGROUP_GLUED_UNIT,
    SUBGROUP_TRUE_RANGE,
    classify_affinity_subgroup,
    flag_evidence_affinity_inconsistency,
    inconsistency_kind,
    materialise_affinity_review_splits,
    parse_inequality_bound,
    project_affinity_reviews,
    project_record_affinity,
    propose_affinity_review_splits,
    validate_affinity_review_row,
)
from adapters.s4_scientific_common import (  # noqa: E402
    CONFIRM_AFFINITY_SCALAR,
    EXCLUDE_NON_AFFINITY,
    INACTIVE_TARGET_DECISION,
    RETAIN_AFFINITY_RAW,
)
from checkpoint2_prepare_review import AFFINITY_REVIEW_COLUMNS, prepare_checkpoint2_package  # noqa: E402
from checkpoint2_validate_review import validate_checkpoint2_package  # noqa: E402


def _machine(
    record_id: str,
    raw: str,
    *,
    unit: str = "",
    status: str = "malformed",
    rule: str = "unparseable_numeric",
    source: str = "synthetic",
    evidence: str = "E4",
    aff_type: str = "Kd",
    index: str = "1",
) -> dict[str, str]:
    return {
        "record_id": record_id,
        "relationship_index": index,
        "source_db": source,
        "evidence_level_proposed": evidence,
        "affinity_type_proposed": aff_type,
        "affinity_value_raw": raw,
        "affinity_unit_raw": unit,
        "affinity_value_molar_proposed": "",
        "affinity_parse_status": status,
        "affinity_parse_rule": rule,
        "affinity_requires_review": "true",
    }


def _review(
    decision: str,
    *,
    decision_id: str = "C2A0001",
    source: str = "synthetic",
    status: str = "malformed",
    rule: str = "unparseable_numeric",
    **fields: str,
) -> dict[str, str]:
    row = {
        "decision_id": decision_id,
        "source_db": source,
        "affinity_parse_status": status,
        "affinity_parse_rule": rule,
        "manual_decision": decision,
        "manual_affinity_value": "",
        "manual_affinity_unit": "",
        "manual_affinity_type": "",
        "manual_affinity_qualifier": "",
        "manual_affinity_range_status": "",
        "manual_affinity_transform_rule": "",
        "manual_affinity_non_affinity_reason": "",
        "manual_notes": "",
    }
    row.update(fields)
    return row


def test_exact_scalar_review() -> None:
    machine = _machine("syn:1", "5", unit="nM", status="missing_unit", rule="numeric_without_unit")
    review = _review(
        CONFIRM_AFFINITY_SCALAR,
        status="missing_unit",
        rule="numeric_without_unit",
        manual_affinity_value="5",
        manual_affinity_unit="nM",
        manual_affinity_type="Kd",
    )
    assert validate_affinity_review_row(review) == []
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert projected["affinity_review_status"] == AFFINITY_REVIEW_STATUS_EXACT
    assert abs(float(projected["affinity_value_molar"]) - 5e-9) < 1e-18
    assert projected["canonical_affinity_value"] == projected["affinity_value_molar"]
    assert projected["canonical_affinity_unit"] == "M"
    assert projected["canonical_affinity_type"] == "Kd"


def test_raw_only_range() -> None:
    machine = _machine(
        "syn:range",
        "22.25-24.74",
        unit="nM",
        status="range_or_multiple",
        rule="range_or_multiple_not_scalar",
    )
    review = _review(
        RETAIN_AFFINITY_RAW,
        status="range_or_multiple",
        rule="range_or_multiple_not_scalar",
        manual_affinity_type="Kd",
        manual_affinity_range_status="range",
    )
    assert validate_affinity_review_row(review) == []
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert projected["affinity_review_status"] == AFFINITY_REVIEW_STATUS_RAW
    assert projected["affinity_value_molar"] == ""
    assert projected["canonical_affinity_value"] == ""
    assert projected["affinity_range_status"] == "range"
    assert projected["affinity_value_raw"] == "22.25-24.74"


def test_inequality_qualifier() -> None:
    machine = _machine(
        "syn:lt",
        "<1.0",
        unit="pM",
        status="inequality",
        rule="inequality_not_scalar",
    )
    review = _review(
        RETAIN_AFFINITY_RAW,
        status="inequality",
        rule="inequality_not_scalar",
        manual_affinity_type="Kd",
        manual_affinity_qualifier="<",
        manual_affinity_transform_rule="parse_inequality_bound",
    )
    assert validate_affinity_review_row(review) == []
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert projected["affinity_review_status"] == AFFINITY_REVIEW_STATUS_RAW
    assert projected["affinity_qualifier"] == "<"
    assert abs(float(projected["affinity_bound_molar"]) - 1e-12) < 1e-18
    assert projected["canonical_affinity_value"] == ""
    qualifier, bound = parse_inequality_bound("<1.0", unit="pM", affinity_type="Kd")
    assert qualifier == "<"
    assert abs(float(bound) - 1e-12) < 1e-18


def test_approximation() -> None:
    machine = _machine(
        "syn:approx",
        "Kd: ~75 nM",
        unit="nM",
        status="approximate",
        rule="approximate_not_scalar",
        source="riboaptamer",
    )
    review = _review(
        RETAIN_AFFINITY_RAW,
        source="riboaptamer",
        status="approximate",
        rule="approximate_not_scalar",
        manual_affinity_type="Kd",
        manual_affinity_qualifier="approximate",
    )
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert projected["affinity_qualifier"] == "approximate"
    assert projected["affinity_value_molar"] == ""
    assert projected["canonical_affinity_value"] == ""


def test_non_affinity_lod() -> None:
    machine = _machine(
        "syn:lod",
        "1",
        unit="pM",
        status="lod_not_binding_affinity",
        rule="scalar_unit_to_molar",
        source="aptaindex",
        evidence="E4",
        aff_type="other",
    )
    review = _review(
        EXCLUDE_NON_AFFINITY,
        source="aptaindex",
        status="lod_not_binding_affinity",
        rule="scalar_unit_to_molar",
        manual_affinity_non_affinity_reason="lod",
    )
    assert validate_affinity_review_row(review) == []
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert projected["affinity_review_status"] == AFFINITY_REVIEW_STATUS_EXCLUDE
    assert projected["canonical_affinity_value"] == ""
    assert projected["canonical_affinity_unit"] == ""
    assert projected["affinity_value_raw"] == "1"
    assert projected["non_affinity_reason"] == "lod"
    assert flag_evidence_affinity_inconsistency(projected) == ""


def test_non_affinity_binding_percentage() -> None:
    machine = _machine(
        "syn:pct",
        "Binding percentage: ≈8%",
        status="approximate",
        rule="approximate_not_scalar",
        source="riboaptamer",
        evidence="E2",
    )
    review = _review(
        EXCLUDE_NON_AFFINITY,
        source="riboaptamer",
        status="approximate",
        rule="approximate_not_scalar",
        manual_affinity_non_affinity_reason="binding_percentage",
    )
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert projected["affinity_review_status"] == AFFINITY_REVIEW_STATUS_EXCLUDE
    assert projected["canonical_affinity_value"] == ""
    assert classify_affinity_subgroup(machine) == SUBGROUP_BINDING_PERCENTAGE


def test_na_is_non_affinity() -> None:
    machine = _machine("syn:na", "Kd: NA", source="riboaptamer")
    review = _review(
        EXCLUDE_NON_AFFINITY,
        source="riboaptamer",
        manual_affinity_non_affinity_reason="missing_value",
    )
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert projected["affinity_review_status"] == AFFINITY_REVIEW_STATUS_EXCLUDE
    assert projected["canonical_affinity_value"] == ""
    assert classify_affinity_subgroup(machine) == "missing_value"


def test_missing_unrecoverable_unit() -> None:
    machine = _machine(
        "syn:nounit",
        "Kd: 325",
        status="missing_unit",
        rule="numeric_without_unit",
        source="riboaptamer",
    )
    review = _review(
        RETAIN_AFFINITY_RAW,
        source="riboaptamer",
        status="missing_unit",
        rule="numeric_without_unit",
        manual_affinity_type="Kd",
    )
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert projected["affinity_review_status"] == AFFINITY_REVIEW_STATUS_RAW
    assert projected["affinity_value_molar"] == ""
    assert projected["canonical_affinity_value"] == ""
    assert classify_affinity_subgroup(machine) == "missing_unit_unrecoverable"


def test_recoverable_micro_m_mojibake_rule() -> None:
    rows = [
        _machine(
            "aptabase:12",
            "1.9",
            status="missing_unit",
            rule="numeric_without_unit",
            source="aptabase",
        ),
        _machine(
            "aptabase:372",
            "18.0",
            status="missing_unit",
            rule="numeric_without_unit",
            source="aptabase",
        ),
    ]
    review = _review(
        CONFIRM_AFFINITY_SCALAR,
        source="aptabase",
        status="missing_unit",
        rule="numeric_without_unit",
        manual_affinity_type="Kd",
        manual_affinity_transform_rule="mojibake_micro_M",
    )
    assert validate_affinity_review_row(review) == []
    first = project_record_affinity(rows[0], review, relationship_active=True)
    second = project_record_affinity(rows[1], review, relationship_active=True)
    assert abs(float(first["affinity_value_molar"]) - 1.9e-6) < 1e-18
    assert abs(float(second["affinity_value_molar"]) - 1.8e-5) < 1e-18
    assert first["affinity_value_molar"] != second["affinity_value_molar"]


def test_scientific_notation_with_negative_exponent() -> None:
    machine = _machine(
        "syn:sci",
        "Kd: 2 x 10^-5 M",
        unit="M",
        status="range_or_multiple",
        rule="range_or_multiple_not_scalar",
        source="riboaptamer",
        evidence="E2",
    )
    review = _review(
        CONFIRM_AFFINITY_SCALAR,
        source="riboaptamer",
        status="range_or_multiple",
        rule="range_or_multiple_not_scalar",
        manual_affinity_type="Kd",
        manual_affinity_transform_rule="scientific_notation",
    )
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert abs(float(projected["affinity_value_molar"]) - 2e-5) < 1e-18


def test_glued_nm() -> None:
    machine = _machine("syn:glued", "Kd: 50nM", source="riboaptamer")
    assert classify_affinity_subgroup(machine) == SUBGROUP_GLUED_UNIT
    review = _review(
        CONFIRM_AFFINITY_SCALAR,
        source="riboaptamer",
        manual_affinity_type="Kd",
        manual_affinity_transform_rule="glued_unit",
    )
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert abs(float(projected["affinity_value_molar"]) - 5e-8) < 1e-18


def test_uncertainty_after_unit() -> None:
    machine = _machine(
        "syn:unc",
        "Kd: 78.2 nM±2.6 nM",
        unit="nM",
        source="riboaptamer",
    )
    review = _review(
        CONFIRM_AFFINITY_SCALAR,
        source="riboaptamer",
        manual_affinity_type="Kd",
        manual_affinity_transform_rule="central_value_uncertainty",
    )
    projected = project_record_affinity(machine, review, relationship_active=True)
    assert abs(float(projected["affinity_value_molar"]) - 7.82e-8) < 1e-18


def test_per_record_transform_under_one_rule() -> None:
    evidence = [
        _machine(
            "aptabase:a",
            "1.9",
            status="missing_unit",
            rule="numeric_without_unit",
            source="aptabase",
        ),
        _machine(
            "aptabase:b",
            "2.5",
            status="missing_unit",
            rule="numeric_without_unit",
            source="aptabase",
        ),
    ]
    review = [
        _review(
            CONFIRM_AFFINITY_SCALAR,
            source="aptabase",
            status="missing_unit",
            rule="numeric_without_unit",
            manual_affinity_type="Kd",
            manual_affinity_transform_rule="mojibake_micro_M",
        )
    ]
    projected, _flags = project_affinity_reviews(evidence, review)
    molars = [row["affinity_value_molar"] for row in projected]
    assert abs(float(molars[0]) - 1.9e-6) < 1e-18
    assert abs(float(molars[1]) - 2.5e-6) < 1e-18
    assert molars[0] != molars[1]


def test_heterogeneous_group_requires_deterministic_split() -> None:
    evidence = [
        _machine(
            "ribo:range",
            "22.25-24.74",
            unit="nM",
            status="range_or_multiple",
            rule="range_or_multiple_not_scalar",
            source="aptaindex",
            evidence="E2",
        ),
        _machine(
            "ribo:list",
            "npBACE 360 and 280",
            unit="nM",
            status="range_or_multiple",
            rule="range_or_multiple_not_scalar",
            source="aptaindex",
            evidence="E2",
        ),
    ]
    reviews = [
        {
            "decision_id": "C2A0009",
            "source_db": "aptaindex",
            "affinity_parse_status": "range_or_multiple",
            "affinity_parse_rule": "range_or_multiple_not_scalar",
            "manual_decision": "",
        }
    ]
    proposal = propose_affinity_review_splits(reviews, evidence)
    assert "C2A0009" in proposal.split_decision_ids
    subgroups = {group.subgroup for group in proposal.groups}
    assert SUBGROUP_TRUE_RANGE in subgroups
    assert "multiple_kd" in subgroups
    assert proposal.n_proposed_rows == 2
    ids = {group.proposed_decision_id for group in proposal.groups}
    assert ids == {"C2A0009A", "C2A0009B"}
    parent_ids = {group.old_decision_id for group in proposal.groups}
    assert parent_ids == {"C2A0009"}
    assert "C2A0009" not in ids
    biphasic = _machine(
        "ribo:bi",
        "Kd: exhibits biphasic binding, 0.32±0.07 nM, 140±80 nM",
        unit="nM",
        source="riboaptamer",
    )
    assert classify_affinity_subgroup(biphasic) == "multiple_kd"


def test_evidence_affinity_consistency_flag() -> None:
    no_binding = _machine(
        "syn:nobind",
        "no binding",
        source="aptamerbase",
        evidence="E2",
    )
    exclude = _review(
        EXCLUDE_NON_AFFINITY,
        source="aptamerbase",
        manual_affinity_non_affinity_reason="no_binding",
    )
    excluded = project_record_affinity(no_binding, exclude, relationship_active=True)
    assert flag_evidence_affinity_inconsistency(excluded) == "evidence_affinity_inconsistency"
    excluded["evidence_affinity_inconsistency"] = "evidence_affinity_inconsistency"
    assert inconsistency_kind(excluded) == "machine_e2_reviewed_non_affinity"

    recovered = _machine(
        "syn:e4",
        "Kd: 50nM",
        source="riboaptamer",
        evidence="E4",
    )
    confirm = _review(
        CONFIRM_AFFINITY_SCALAR,
        source="riboaptamer",
        manual_affinity_type="Kd",
        manual_affinity_transform_rule="glued_unit",
    )
    exact = project_record_affinity(recovered, confirm, relationship_active=True)
    assert exact["affinity_value_molar"]
    assert flag_evidence_affinity_inconsistency(exact) == "evidence_affinity_inconsistency"
    exact["evidence_affinity_inconsistency"] = "evidence_affinity_inconsistency"
    assert inconsistency_kind(exact) == "machine_e4_reviewed_exact_quantitative_affinity"

    lod = _machine(
        "syn:lod2",
        "1",
        unit="pM",
        status="lod_not_binding_affinity",
        rule="scalar_unit_to_molar",
        source="aptaindex",
        evidence="E4",
        aff_type="other",
    )
    lod_review = _review(
        EXCLUDE_NON_AFFINITY,
        source="aptaindex",
        status="lod_not_binding_affinity",
        rule="scalar_unit_to_molar",
        manual_affinity_non_affinity_reason="lod",
    )
    lod_proj = project_record_affinity(lod, lod_review, relationship_active=True)
    assert flag_evidence_affinity_inconsistency(lod_proj) == ""


def test_evidence_affinity_inconsistency_blocks_application(tmp_path: Path) -> None:
    prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[],
        relationship_rows=[],
        extraction_rows=[],
        evidence_rows=[
            {
                "record_id": "syn:nobind",
                "source_db": "synthetic",
                "evidence_rule": "SYN_E2",
                "evidence_level_proposed": "E2",
                "alternative_evidence_level": "",
                "e4_e5_threshold_ambiguous": "false",
                "evidence_requires_review": "false",
                "evidence_provenance": "",
                "affinity_requires_review": "true",
                "affinity_parse_status": "malformed",
                "affinity_parse_rule": "unparseable_numeric",
                "affinity_type_proposed": "Kd",
                "affinity_value_raw": "no binding",
                "affinity_unit_raw": "",
            }
        ],
        leakage_rows=[],
        routing_rows=[],
    )
    path = tmp_path / "cp2" / "checkpoint2_affinity_review.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rows[0]["manual_decision"] = EXCLUDE_NON_AFFINITY
    rows[0]["manual_affinity_non_affinity_reason"] = "no_binding"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    evidence_path = tmp_path / "evidence_affinity_proposals.csv"
    with evidence_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "record_id",
                "relationship_index",
                "source_db",
                "evidence_level_proposed",
                "affinity_type_proposed",
                "affinity_value_raw",
                "affinity_unit_raw",
                "affinity_parse_status",
                "affinity_parse_rule",
                "affinity_requires_review",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "record_id": "syn:nobind",
                "relationship_index": "1",
                "source_db": "synthetic",
                "evidence_level_proposed": "E2",
                "affinity_type_proposed": "Kd",
                "affinity_value_raw": "no binding",
                "affinity_unit_raw": "",
                "affinity_parse_status": "malformed",
                "affinity_parse_rule": "unparseable_numeric",
                "affinity_requires_review": "true",
            }
        )
    result = validate_checkpoint2_package(tmp_path / "cp2")
    assert result["errors"] == []
    assert result["unresolved_decisions"] == 0
    assert result["application_blocked_by_evidence_affinity_inconsistency"] is True
    assert result["ready_for_application"] is False
    assert "syn:nobind" in result["evidence_affinity_inconsistency_records"]


def test_existing_target_relationship_evidence_semantics_unchanged(tmp_path: Path) -> None:
    result = prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[
            {
                "target_dictionary_id": "TD0001",
                "raw_target": "VEGF",
                "source_keys": "utexas",
                "n_records": "1",
                "canonical_target_name_proposal": "VEGF",
                "uniprot_proposed": "",
                "uniprot_candidates": "",
                "target_type_proposed": "protein",
                "target_family_proposed": "growth_factor",
                "target_pfam_proposed": "",
                "target_interpro_proposed": "",
                "proposal_confidence": "medium",
                "resolution_provenance": "",
                "scientific_ambiguity_reason": "",
                "machine_recommendation": "review_required",
                "requires_checkpoint2": "true",
            }
        ],
        relationship_rows=[
            {
                "record_id": "aptamerbase:1",
                "source_db": "aptamerbase",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "raw_target": "p50",
                "target_dictionary_id": "TD0002",
                "requires_checkpoint2": "true",
            }
        ],
        extraction_rows=[
            {
                "record_id": "aptamerbase:1",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "ambiguity_reason": "",
            }
        ],
        evidence_rows=[
            {
                "record_id": "ena:1",
                "source_db": "ena",
                "evidence_rule": "ENA_TARGET_SPECIFIC_CLAIM",
                "evidence_level_proposed": "E5",
                "alternative_evidence_level": "E4",
                "e4_e5_threshold_ambiguous": "true",
                "evidence_requires_review": "true",
                "evidence_provenance": "ena",
                "affinity_requires_review": "true",
                "affinity_parse_status": "malformed",
                "affinity_parse_rule": "unparseable_numeric",
                "affinity_type_proposed": "Kd",
            }
        ],
        leakage_rows=[],
        routing_rows=[],
    )
    assert INACTIVE_TARGET_DECISION in result["manual_decision_vocabulary"]
    assert CONFIRM_AFFINITY_SCALAR in result["manual_decision_vocabulary"]
    validator = validate_checkpoint2_package(tmp_path / "cp2")
    assert validator["ready_for_application"] is False
    assert validator["fail_closed_blank_package"] is True
    target_path = tmp_path / "cp2" / "checkpoint2_target_dictionary_review.csv"
    rows = list(csv.DictReader(target_path.open(newline="", encoding="utf-8")))
    rows[0]["manual_decision"] = "approve_proposal"
    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    relationship_path = tmp_path / "cp2" / "checkpoint2_relationship_review.csv"
    rels = list(csv.DictReader(relationship_path.open(newline="", encoding="utf-8")))
    rels[0]["manual_decision"] = "confirm_multi_target_expansion"
    with relationship_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rels[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rels[0])
    evidence_path = tmp_path / "cp2" / "checkpoint2_evidence_review.csv"
    evs = list(csv.DictReader(evidence_path.open(newline="", encoding="utf-8")))
    evs[0]["manual_decision"] = "confirm_evidence"
    with evidence_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(evs[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(evs[0])
    filled = validate_checkpoint2_package(tmp_path / "cp2")
    assert filled["errors"] == []
    assert filled["target_completion"]["approve_proposal"] == 1
    assert filled["unresolved_decisions"] > 0
    assert filled["ready_for_application"] is False

    rows[0]["manual_decision"] = CONFIRM_AFFINITY_SCALAR
    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    wrong_grain = validate_checkpoint2_package(tmp_path / "cp2")
    assert any("not valid on this review grain" in item for item in wrong_grain["errors"])


def test_validator_rejects_contradictory_affinity_combinations(tmp_path: Path) -> None:
    prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[],
        relationship_rows=[],
        extraction_rows=[],
        evidence_rows=[
            {
                "record_id": "syn:1",
                "source_db": "synthetic",
                "evidence_rule": "SYN",
                "evidence_level_proposed": "E2",
                "alternative_evidence_level": "",
                "e4_e5_threshold_ambiguous": "false",
                "evidence_requires_review": "false",
                "evidence_provenance": "",
                "affinity_requires_review": "true",
                "affinity_parse_status": "malformed",
                "affinity_parse_rule": "unparseable_numeric",
                "affinity_type_proposed": "Kd",
            }
        ],
        leakage_rows=[],
        routing_rows=[],
    )
    path = tmp_path / "cp2" / "checkpoint2_affinity_review.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rows[0]["manual_decision"] = EXCLUDE_NON_AFFINITY
    rows[0]["manual_affinity_value"] = "5"
    rows[0]["manual_affinity_unit"] = "nM"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    excluded = validate_checkpoint2_package(tmp_path / "cp2")
    assert any("cannot carry a manual scalar" in item for item in excluded["errors"])

    rows[0]["manual_affinity_value"] = ""
    rows[0]["manual_affinity_unit"] = ""
    rows[0]["manual_decision"] = CONFIRM_AFFINITY_SCALAR
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    missing = validate_checkpoint2_package(tmp_path / "cp2")
    assert any("requires a numeric value/unit" in item for item in missing["errors"])

    rows[0]["manual_decision"] = RETAIN_AFFINITY_RAW
    rows[0]["manual_affinity_value"] = "1e-9"
    rows[0]["manual_affinity_unit"] = "M"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    fake_scalar = validate_checkpoint2_package(tmp_path / "cp2")
    assert any("cannot carry a fake exact scalar" in item for item in fake_scalar["errors"])

    rows[0]["manual_decision"] = "park_unresolved"
    rows[0]["manual_affinity_value"] = ""
    rows[0]["manual_affinity_unit"] = ""
    rows[0]["manual_affinity_qualifier"] = "<"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    parked = validate_checkpoint2_package(tmp_path / "cp2")
    assert any("park_unresolved has incompatible" in item for item in parked["errors"])

    rows[0]["manual_decision"] = RETAIN_AFFINITY_RAW
    rows[0]["manual_affinity_qualifier"] = ""
    rows[0]["manual_affinity_type"] = "Kd"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    ok = validate_checkpoint2_package(tmp_path / "cp2")
    assert not any("affinity" in item and "invalid" in item for item in ok["errors"] if "manual_decision" in item)
    assert ok["affinity_completion"][RETAIN_AFFINITY_RAW] == 1
    assert ok["affinity_completion"]["blank"] == 0
    assert ok["errors"] == []
    assert ok["unresolved_decisions"] == 0
    # A fully resolved synthetic package with no evidence inconsistency is
    # application-ready at the validator. Live CHECKPOINT-2 is not.


def test_parked_relationship_does_not_populate_canonical_scalar() -> None:
    machine = _machine(
        "syn:parked",
        "1.9",
        status="missing_unit",
        rule="numeric_without_unit",
        source="aptabase",
    )
    review = _review(
        CONFIRM_AFFINITY_SCALAR,
        source="aptabase",
        status="missing_unit",
        rule="numeric_without_unit",
        manual_affinity_type="Kd",
        manual_affinity_transform_rule="mojibake_micro_M",
    )
    projected = project_record_affinity(machine, review, relationship_active=False)
    assert projected["affinity_review_status"] == AFFINITY_REVIEW_STATUS_EXACT
    assert projected["canonical_affinity_value"] == ""
    assert projected["relationship_active"] == "false"


def test_materialise_splits_are_idempotent_and_preserve_human_fields() -> None:
    evidence = [
        _machine(
            "ribo:range",
            "22.25-24.74",
            unit="nM",
            status="range_or_multiple",
            rule="range_or_multiple_not_scalar",
            source="aptaindex",
            evidence="E2",
        ),
        _machine(
            "ribo:list",
            "npBACE 360 and 280",
            unit="nM",
            status="range_or_multiple",
            rule="range_or_multiple_not_scalar",
            source="aptaindex",
            evidence="E2",
        ),
        _machine(
            "aptabase:a",
            "1.9",
            status="missing_unit",
            rule="numeric_without_unit",
            source="aptabase",
        ),
        _machine(
            "aptabase:b",
            "2.5",
            status="missing_unit",
            rule="numeric_without_unit",
            source="aptabase",
        ),
    ]
    reviews = [
        {
            "decision_id": "C2A0009",
            "source_db": "aptaindex",
            "affinity_parse_status": "range_or_multiple",
            "affinity_parse_rule": "range_or_multiple_not_scalar",
            "affinity_type_proposed": "Kd",
            "manual_decision": "",
        },
        {
            "decision_id": "C2A0002",
            "source_db": "aptabase",
            "affinity_parse_status": "missing_unit",
            "affinity_parse_rule": "numeric_without_unit",
            "affinity_type_proposed": "Kd",
            "manual_decision": "",
        },
    ]
    first, proposal = materialise_affinity_review_splits(
        reviews, evidence, columns=AFFINITY_REVIEW_COLUMNS
    )
    assert proposal.split_decision_ids == ("C2A0009",)
    assert proposal.unsplit_decision_ids == ("C2A0002",)
    ids = [row["decision_id"] for row in first]
    assert ids == ["C2A0009A", "C2A0009B", "C2A0002"]
    assert "C2A0009" not in ids
    by_id = {row["decision_id"]: row for row in first}
    assert by_id["C2A0009A"]["parent_decision_id"] == "C2A0009"
    assert by_id["C2A0009A"]["affinity_subgroup"] == "multiple_kd"
    assert by_id["C2A0009B"]["affinity_subgroup"] == SUBGROUP_TRUE_RANGE
    assert by_id["C2A0002"]["parent_decision_id"] == "C2A0002"
    assert by_id["C2A0002"]["n_records"] == "2"
    assert by_id["C2A0009A"]["record_ids"] == "ribo:list"
    assert by_id["C2A0009B"]["record_ids"] == "ribo:range"
    for row in first:
        assert row["manual_decision"] == ""
        assert row["manual_affinity_transform_rule"] == ""
        assert row["review_consequence"]
    second, _proposal = materialise_affinity_review_splits(
        first, evidence, columns=AFFINITY_REVIEW_COLUMNS
    )
    assert [row["decision_id"] for row in second] == ids
    assert [row["record_ids"] for row in second] == [row["record_ids"] for row in first]
    reviewed = [dict(row) for row in first]
    reviewed[0]["manual_decision"] = RETAIN_AFFINITY_RAW
    reviewed[0]["manual_notes"] = "keep-me"
    third, _proposal = materialise_affinity_review_splits(
        reviewed, evidence, columns=AFFINITY_REVIEW_COLUMNS
    )
    retained = {row["decision_id"]: row for row in third}
    assert retained["C2A0009A"]["manual_decision"] == RETAIN_AFFINITY_RAW
    assert retained["C2A0009A"]["manual_notes"] == "keep-me"
    assert retained["C2A0009B"]["manual_decision"] == ""
    assert retained["C2A0002"]["manual_decision"] == ""


def test_materialised_package_validator_counts_blank_children(tmp_path: Path) -> None:
    evidence = [
        {
            "record_id": "aptaindex:range",
            "source_db": "aptaindex",
            "evidence_rule": "SYN",
            "evidence_level_proposed": "E2",
            "alternative_evidence_level": "",
            "e4_e5_threshold_ambiguous": "false",
            "evidence_requires_review": "false",
            "evidence_provenance": "",
            "affinity_requires_review": "true",
            "affinity_parse_status": "range_or_multiple",
            "affinity_parse_rule": "range_or_multiple_not_scalar",
            "affinity_type_proposed": "Kd",
            "affinity_value_raw": "22.25-24.74",
            "affinity_unit_raw": "nM",
        },
        {
            "record_id": "aptaindex:list",
            "source_db": "aptaindex",
            "evidence_rule": "SYN",
            "evidence_level_proposed": "E2",
            "alternative_evidence_level": "",
            "e4_e5_threshold_ambiguous": "false",
            "evidence_requires_review": "false",
            "evidence_provenance": "",
            "affinity_requires_review": "true",
            "affinity_parse_status": "range_or_multiple",
            "affinity_parse_rule": "range_or_multiple_not_scalar",
            "affinity_type_proposed": "Kd",
            "affinity_value_raw": "npBACE 360 and 280",
            "affinity_unit_raw": "nM",
        },
    ]
    prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[],
        relationship_rows=[],
        extraction_rows=[],
        evidence_rows=evidence,
        leakage_rows=[],
        routing_rows=[],
    )
    path = tmp_path / "cp2" / "checkpoint2_affinity_review.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    assert len(rows) == 1
    materialised, proposal = materialise_affinity_review_splits(
        rows, evidence, columns=AFFINITY_REVIEW_COLUMNS
    )
    assert proposal.n_proposed_rows == 2
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(AFFINITY_REVIEW_COLUMNS), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(materialised)
    result = validate_checkpoint2_package(tmp_path / "cp2")
    assert result["errors"] == []
    assert result["affinity_completion"]["blank"] == 2
    assert result["unresolved_decisions"] == 2
    assert result["ready_for_application"] is False


def test_documented_unsplit_row_stays_one_review_unit() -> None:
    evidence = [
        _machine(
            "aptabase:12",
            "1.9",
            status="missing_unit",
            rule="numeric_without_unit",
            source="aptabase",
        ),
        _machine(
            "aptabase:372",
            "18.0",
            status="missing_unit",
            rule="numeric_without_unit",
            source="aptabase",
        ),
    ]
    reviews = [
        {
            "decision_id": "C2A0002",
            "source_db": "aptabase",
            "affinity_parse_status": "missing_unit",
            "affinity_parse_rule": "numeric_without_unit",
            "affinity_type_proposed": "Kd",
            "manual_decision": "",
        }
    ]
    proposal = propose_affinity_review_splits(reviews, evidence)
    assert proposal.split_decision_ids == ()
    assert proposal.unsplit_decision_ids == ("C2A0002",)
    assert proposal.n_proposed_rows == 1
    assert proposal.groups[0].proposed_decision_id == "C2A0002"
    assert proposal.groups[0].n_records == 2
    assert proposal.groups[0].transform_rule == "mojibake_micro_M"


def test_authorised_affinity_decisions_are_complete_and_valid() -> None:
    from checkpoint2_record_affinity_review import (  # noqa: E402
        AUTHORISED_AFFINITY_DECISIONS,
        apply_authorised_affinity_decisions,
        authorised_affinity_decision_counts,
    )

    counts = authorised_affinity_decision_counts()
    assert counts[CONFIRM_AFFINITY_SCALAR] == 4
    assert counts[RETAIN_AFFINITY_RAW] == 15
    assert counts[EXCLUDE_NON_AFFINITY] == 12
    assert counts["park_unresolved"] == 0
    assert len(AUTHORISED_AFFINITY_DECISIONS) == 31
    blank_rows = [
        {
            "decision_id": decision_id,
            "source_db": "synthetic",
            "affinity_parse_status": "malformed",
            "affinity_parse_rule": "unparseable_numeric",
            "manual_decision": "",
        }
        for decision_id in AUTHORISED_AFFINITY_DECISIONS
    ]
    recorded = apply_authorised_affinity_decisions(blank_rows)
    assert [row["decision_id"] for row in recorded] == list(AUTHORISED_AFFINITY_DECISIONS)
    assert all(row["manual_decision"] for row in recorded)
    assert all(row["manual_decision"] != "park_unresolved" for row in recorded)
    assert {row["decision_id"] for row in recorded if row["manual_decision"] == CONFIRM_AFFINITY_SCALAR} == {
        "C2A0002",
        "C2A0016A",
        "C2A0016B",
        "C2A0018B",
    }
    mixed = next(row for row in recorded if row["decision_id"] == "C2A0016D")
    assert mixed["manual_affinity_type"] == ""
    approx = next(row for row in recorded if row["decision_id"] == "C2A0014A")
    assert approx["manual_affinity_qualifier"] == "approximate"
    tbd = next(row for row in recorded if row["decision_id"] == "C2A0019")
    assert tbd["manual_affinity_non_affinity_reason"] == "placeholder"

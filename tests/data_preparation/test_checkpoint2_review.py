"""Synthetic tests for CHECKPOINT-2 blank package and fail-closed validation."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.checkpoint2_relationship import (  # noqa: E402
    apply_relationship_override,
    apply_relationship_overrides,
)
from adapters.s4_scientific_common import HUMAN_FIELDS, INACTIVE_TARGET_DECISION  # noqa: E402
from checkpoint2_prepare_review import prepare_checkpoint2_package  # noqa: E402
from checkpoint2_validate_review import validate_checkpoint2_package  # noqa: E402


def test_blank_package_fails_closed(tmp_path: Path) -> None:
    result = prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[
            {
                "target_dictionary_id": "TD0001",
                "raw_target": "VEGF",
                "source_keys": "utexas",
                "n_records": "3",
                "canonical_target_name_proposal": "VEGF",
                "uniprot_proposed": "",
                "uniprot_candidates": "P15692|P26644",
                "target_type_proposed": "protein",
                "target_family_proposed": "growth_factor",
                "target_pfam_proposed": "",
                "target_interpro_proposed": "",
                "proposal_confidence": "medium",
                "resolution_provenance": "type=source_prior",
                "scientific_ambiguity_reason": "multiple_local_uniprot_candidates",
                "machine_recommendation": "review_uniprot_ambiguity",
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
            },
            {
                "record_id": "aptamerbase:1",
                "source_db": "aptamerbase",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "raw_target": "p65",
                "target_dictionary_id": "TD0003",
                "requires_checkpoint2": "true",
            },
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
                "evidence_provenance": "ena_source_binding_evidence_type",
                "affinity_requires_review": "false",
                "affinity_parse_status": "absent",
            }
        ],
        leakage_rows=[
            {
                "record_id": "ena:2",
                "source_db": "ena",
                "sequence_match_kind": "identity_ge_0.90",
                "identity": "0.910000",
                "target_alias_match": "false",
                "matched_canonical_target": "",
                "notes": "borderline_sequence_identity",
                "requires_review": "true",
            }
        ],
        routing_rows=[],
    )
    assert result["decision_counts"]["target"] == 1
    assert result["decision_counts"]["relationship"] == 1
    assert result["decision_counts"]["evidence"] == 1
    assert result["decision_counts"]["leakage"] == 1
    validator = validate_checkpoint2_package(tmp_path / "cp2")
    assert validator["ready_for_application"] is False
    assert validator["unresolved_decisions"] > 0
    assert validator["fail_closed_blank_package"] is True
    with (tmp_path / "cp2" / "checkpoint2_target_dictionary_review.csv").open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    for field in HUMAN_FIELDS:
        assert row[field] == ""


def test_deterministic_e2_is_not_an_evidence_decision(tmp_path: Path) -> None:
    result = prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[],
        relationship_rows=[],
        extraction_rows=[],
        evidence_rows=[
            {
                "record_id": "utexas:1",
                "source_db": "utexas",
                "evidence_rule": "UTEXAS_QUANTITATIVE_KD",
                "evidence_level_proposed": "E2",
                "alternative_evidence_level": "",
                "e4_e5_threshold_ambiguous": "false",
                "evidence_requires_review": "false",
                "evidence_provenance": "utexas_kd_nm",
                "affinity_requires_review": "true",
                "affinity_parse_status": "range_or_multiple",
                "affinity_parse_rule": "range_or_multiple_not_scalar",
                "affinity_type_proposed": "Kd",
            }
        ],
        leakage_rows=[],
        routing_rows=[],
    )
    assert result["decision_counts"]["evidence"] == 0
    assert result["decision_counts"]["affinity"] == 1


def test_grouped_decisions_not_one_row_per_record(tmp_path: Path) -> None:
    evidence = [
        {
            "record_id": f"ena:{i}",
            "source_db": "ena",
            "evidence_rule": "ENA_TARGET_SPECIFIC_CLAIM",
            "evidence_level_proposed": "E5",
            "alternative_evidence_level": "E4",
            "e4_e5_threshold_ambiguous": "true",
            "evidence_requires_review": "true",
            "evidence_provenance": "ena_source_binding_evidence_type",
            "affinity_requires_review": "false",
            "affinity_parse_status": "absent",
        }
        for i in range(12)
    ]
    result = prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[],
        relationship_rows=[],
        extraction_rows=[],
        evidence_rows=evidence,
        leakage_rows=[],
        routing_rows=[],
    )
    assert result["decision_counts"]["evidence"] == 1
    assert result["decision_counts"]["evidence"] < 12


def test_override_validation_requires_corrected_fields(tmp_path: Path) -> None:
    prepare_checkpoint2_package(
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
                "target_type_proposed": "unknown",
                "target_family_proposed": "unknown",
                "target_pfam_proposed": "",
                "target_interpro_proposed": "",
                "proposal_confidence": "low",
                "resolution_provenance": "",
                "scientific_ambiguity_reason": "unknown_type",
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
    rows[0]["manual_decision"] = "override"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    result = validate_checkpoint2_package(tmp_path / "cp2")
    assert result["ready_for_application"] is False
    assert any("missing manual_target_name" in item or "missing manual_target_type" in item for item in result["errors"])


def test_evidence_and_leakage_override_validation(tmp_path: Path) -> None:
    prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[],
        relationship_rows=[],
        extraction_rows=[],
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
                "affinity_requires_review": "false",
                "affinity_parse_status": "absent",
            }
        ],
        leakage_rows=[
            {
                "record_id": "ena:2",
                "source_db": "ena",
                "sequence_match_kind": "exact",
                "identity": "1.000000",
                "target_alias_match": "true",
                "matched_canonical_target": "NDM-1",
                "notes": "",
                "requires_review": "true",
            }
        ],
        routing_rows=[],
    )
    evidence_path = tmp_path / "cp2" / "checkpoint2_evidence_review.csv"
    rows = list(csv.DictReader(evidence_path.open(newline="", encoding="utf-8")))
    rows[0]["manual_decision"] = "override_evidence"
    with evidence_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    leak_path = tmp_path / "cp2" / "checkpoint2_leakage_review.csv"
    leaks = list(csv.DictReader(leak_path.open(newline="", encoding="utf-8")))
    leaks[0]["manual_decision"] = "retain_despite_false_positive_leakage"
    with leak_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(leaks[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(leaks[0])
    result = validate_checkpoint2_package(tmp_path / "cp2")
    assert any("missing manual_evidence_level" in item for item in result["errors"])
    assert any("missing manual_notes" in item for item in result["errors"])


def test_multi_target_decision_validation(tmp_path: Path) -> None:
    prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[],
        relationship_rows=[
            {
                "record_id": "aptamerbase:1",
                "source_db": "aptamerbase",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "raw_target": "p50",
                "target_dictionary_id": "TD1",
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
        evidence_rows=[],
        leakage_rows=[],
        routing_rows=[],
    )
    path = tmp_path / "cp2" / "checkpoint2_relationship_review.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rows[0]["manual_decision"] = "confirm_multi_target_expansion"
    rows[0]["manual_relationship_action"] = "reject_proposed_relationship"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerow(rows[0])
    result = validate_checkpoint2_package(tmp_path / "cp2")
    assert any("inconsistent multi-target action" in item for item in result["errors"])


def _write_review_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0].keys()), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _synthetic_machine_pair(
    record_id: str,
    first: str,
    second: str,
    *,
    source_db: str = "synthetic",
) -> list[dict[str, str]]:
    return [
        {
            "record_id": record_id,
            "relationship_index": "1",
            "source_db": source_db,
            "raw_target": first,
            "target_type_proposed": "unknown",
            "uniprot_proposed": "KEEP_ME_OUT",
            "target_family_proposed": "unknown",
            "target_pfam_proposed": "PF00000",
            "record_expansion_proposed": "true",
            "relationship_status": "resolved_multiple",
            "requires_checkpoint2": "true",
            "notes": "machine_fragment_a",
        },
        {
            "record_id": record_id,
            "relationship_index": "2",
            "source_db": source_db,
            "raw_target": second,
            "target_type_proposed": "unknown",
            "uniprot_proposed": "",
            "target_family_proposed": "unknown",
            "target_pfam_proposed": "",
            "record_expansion_proposed": "true",
            "relationship_status": "resolved_multiple",
            "requires_checkpoint2": "true",
            "notes": "machine_fragment_b",
        },
    ]


def test_relationship_override_validation_requires_name_and_type(
    tmp_path: Path,
) -> None:
    prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[
            {
                "target_dictionary_id": "TD_HOLD",
                "raw_target": "TOKEN_HOLD",
                "source_keys": "synthetic",
                "n_records": "1",
                "canonical_target_name_proposal": "TOKEN_HOLD",
                "uniprot_proposed": "",
                "uniprot_candidates": "",
                "target_type_proposed": "unknown",
                "target_family_proposed": "unknown",
                "target_pfam_proposed": "",
                "target_interpro_proposed": "",
                "proposal_confidence": "low",
                "resolution_provenance": "",
                "scientific_ambiguity_reason": "unknown_type",
                "machine_recommendation": "review_required",
                "requires_checkpoint2": "true",
            }
        ],
        relationship_rows=[
            {
                "record_id": "synthetic:alpha",
                "source_db": "synthetic",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "raw_target": "TOKEN_ALPHA",
                "target_dictionary_id": "TD_A",
                "requires_checkpoint2": "true",
            },
            {
                "record_id": "synthetic:alpha",
                "source_db": "synthetic",
                "relationship_status": "resolved_multiple",
                "record_expansion_proposed": "true",
                "raw_target": "TOKEN_BETA",
                "target_dictionary_id": "TD_B",
                "requires_checkpoint2": "true",
            },
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
    rows[0]["manual_decision"] = "override"
    _write_review_csv(path, rows)
    missing = validate_checkpoint2_package(tmp_path / "cp2")
    assert any("missing manual_target_name" in item for item in missing["errors"])
    assert any("missing manual_target_type" in item for item in missing["errors"])

    rows[0]["manual_target_name"] = "TOKEN_RECONSTRUCTED"
    rows[0]["manual_target_type"] = "small_molecule"
    rows[0]["manual_notes"] = "synthetic override of split fragments"
    _write_review_csv(path, rows)
    filled = validate_checkpoint2_package(tmp_path / "cp2")
    assert filled["errors"] == []
    assert filled["ready_for_application"] is False


def test_relationship_override_replaces_set_with_one_manual_target() -> None:
    machine = _synthetic_machine_pair(
        "synthetic:alpha", "TOKEN_ALPHA", "TOKEN_BETA"
    )
    snapshot = [dict(row) for row in machine]
    review = {
        "decision_id": "C2R9999",
        "record_id": "synthetic:alpha",
        "manual_decision": "override",
        "manual_target_name": "TOKEN_RECONSTRUCTED",
        "manual_target_type": "small_molecule",
        "manual_uniprot": "",
        "manual_target_family": "",
        "manual_pfam_interpro": "",
        "manual_relationship_action": "",
        "manual_notes": "reconstructed from split tokens",
    }
    first = apply_relationship_override(machine, review)
    second = apply_relationship_override(machine, review)

    assert first == second
    assert len(first) == 1
    assert first[0]["raw_target"] == "TOKEN_RECONSTRUCTED"
    assert first[0]["raw_target"] not in {"TOKEN_ALPHA", "TOKEN_BETA"}
    assert first[0]["relationship_index"] == "1"
    assert first[0]["target_type_proposed"] == "small_molecule"
    assert first[0]["uniprot_proposed"] == ""
    assert first[0]["target_family_proposed"] == ""
    assert first[0]["target_pfam_proposed"] == ""
    assert first[0]["record_expansion_proposed"] == "false"
    assert first[0]["relationship_status"] == "resolved_single"
    assert machine == snapshot
    assert [row["raw_target"] for row in machine] == ["TOKEN_ALPHA", "TOKEN_BETA"]
    assert [row["relationship_index"] for row in machine] == ["1", "2"]

    other = _synthetic_machine_pair(
        "synthetic:delta", "TOKEN_DELTA", "TOKEN_EPSILON"
    )
    other_snapshot = [dict(row) for row in other]
    combined = apply_relationship_overrides(
        machine + other,
        [review],
    )
    assert [row["record_id"] for row in combined] == [
        "synthetic:alpha",
        "synthetic:delta",
        "synthetic:delta",
    ]
    assert combined[0]["raw_target"] == "TOKEN_RECONSTRUCTED"
    assert combined[1:] == other_snapshot
    assert other == other_snapshot


def test_prepare_readme_includes_inactive_target_action(tmp_path: Path) -> None:
    result = prepare_checkpoint2_package(
        repo_root=tmp_path,
        output_dir=tmp_path / "cp2",
        dictionary_rows=[],
        relationship_rows=[],
        extraction_rows=[],
        evidence_rows=[],
        leakage_rows=[],
        routing_rows=[],
    )
    assert INACTIVE_TARGET_DECISION in result["manual_decision_vocabulary"]
    readme = (tmp_path / "cp2" / "README.md").read_text(encoding="utf-8")
    assert INACTIVE_TARGET_DECISION in readme

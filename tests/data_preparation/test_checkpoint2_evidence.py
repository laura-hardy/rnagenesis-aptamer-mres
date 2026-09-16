"""Synthetic tests for CHECKPOINT-2 supplemental evidence-consistency review."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.checkpoint2_affinity import (  # noqa: E402
    flag_evidence_affinity_inconsistency,
)
from adapters.checkpoint2_evidence import (  # noqa: E402
    EVIDENCE_CONSISTENCY_FILE,
    EVIDENCE_CONSISTENCY_REVIEW_COLUMNS,
    EVIDENCE_SOURCE_MACHINE,
    EVIDENCE_SOURCE_ORIGINAL,
    EVIDENCE_SOURCE_SUPPLEMENTAL,
    EXPECTED_CORRECTED_DISTRIBUTION,
    EXPECTED_DECISION_IDS,
    EXPECTED_DECISION_LEVEL_COUNTS,
    EXPECTED_GROUP_COUNTS,
    EXPECTED_GROUPS,
    EXPECTED_NEW_EVIDENCE_PARKS,
    EXPECTED_TARGET_PARKED_INDEPENDENT,
    EXPECTED_TRANSITIONS,
    EXPECTED_UNIQUE_RECORDS,
    apply_evidence_consistency_decisions,
    collect_consistency_flag_record_ids,
    compare_consistency_review_to_pristine,
    dry_run_supplemental_routing,
    expected_record_ids,
    materialise_evidence_consistency_review,
    original_evidence_membership,
    project_effective_evidence_level,
    summarise_member_outcomes,
    validate_group_spec,
)
from adapters.s4_scientific_common import (  # noqa: E402
    CONFIRM_AFFINITY_SCALAR,
    EVIDENCE_SCORE_BY_LEVEL,
    EXCLUDE_NON_AFFINITY,
    HUMAN_FIELDS,
    ScientificProposalError,
)
from checkpoint2_prepare_review import prepare_checkpoint2_package  # noqa: E402
from checkpoint2_record_evidence_consistency import (  # noqa: E402
    AUTHORISED_EVIDENCE_CONSISTENCY_DECISIONS,
)
from checkpoint2_validate_review import validate_checkpoint2_package  # noqa: E402


def _machine_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for group in EXPECTED_GROUPS:
        for record_id in group.record_ids:
            rows.append(
                {
                    "record_id": record_id,
                    "relationship_index": "1",
                    "source_db": group.source_db,
                    "evidence_level_proposed": group.machine_evidence_level,
                    "evidence_rule": group.expected_evidence_rule,
                    "evidence_provenance": f"synthetic:{group.decision_id}",
                    "e4_e5_threshold_ambiguous": "false",
                    "affinity_requires_review": "true",
                    "affinity_parse_status": "malformed",
                    "affinity_parse_rule": "unparseable_numeric",
                    "affinity_type_proposed": "Kd",
                    "affinity_value_raw": "synthetic",
                    "affinity_unit_raw": "",
                }
            )
    return rows


def _affinity_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for group in EXPECTED_GROUPS:
        rows.append(
            {
                "decision_id": group.affinity_decision_id,
                "source_db": group.source_db,
                "record_ids": "|".join(group.record_ids),
                "manual_decision": group.reviewed_affinity_outcome,
                "manual_affinity_transform_rule": (
                    "mojibake_micro_M" if group.decision_id == "C2EC0001" else ""
                ),
            }
        )
    return rows


def _original_evidence_rows() -> list[dict[str, str]]:
    return [
        {
            "decision_id": "C2E0001",
            "source_db": "aptadb",
            "evidence_rule": "APTADB_PMID_WITHOUT_ASSAY",
            "evidence_level_proposed": "E4",
            "alternative_evidence_level": "E5",
            "manual_decision": "override_evidence",
            "manual_evidence_level": "E5",
        },
        {
            "decision_id": "C2E0002",
            "source_db": "ena",
            "evidence_rule": "ENA_TARGET_SPECIFIC_CLAIM",
            "evidence_level_proposed": "E5",
            "alternative_evidence_level": "E4",
            "manual_decision": "confirm_evidence",
            "manual_evidence_level": "",
        },
        {
            "decision_id": "C2E0003",
            "source_db": "ncbi_nuc",
            "evidence_rule": "NCBI_PUBLICATION_ONLY",
            "evidence_level_proposed": "E5",
            "alternative_evidence_level": "E4",
            "manual_decision": "confirm_evidence",
            "manual_evidence_level": "",
        },
    ]


def _original_machine_rows() -> list[dict[str, str]]:
    return [
        {
            "record_id": "aptadb:40",
            "source_db": "aptadb",
            "evidence_rule": "APTADB_PMID_WITHOUT_ASSAY",
            "evidence_level_proposed": "E4",
            "alternative_evidence_level": "E5",
            "e4_e5_threshold_ambiguous": "true",
        },
        {
            "record_id": "ena:rev2_example",
            "source_db": "ena",
            "evidence_rule": "ENA_TARGET_SPECIFIC_CLAIM",
            "evidence_level_proposed": "E5",
            "alternative_evidence_level": "E4",
            "e4_e5_threshold_ambiguous": "true",
        },
        {
            "record_id": "ncbi_nuc:BD161067",
            "source_db": "ncbi_nuc",
            "evidence_rule": "NCBI_PUBLICATION_ONLY",
            "evidence_level_proposed": "E5",
            "alternative_evidence_level": "E4",
            "e4_e5_threshold_ambiguous": "true",
        },
    ]


def test_group_spec_and_counts() -> None:
    validate_group_spec()
    assert list(EXPECTED_DECISION_IDS) == [group.decision_id for group in EXPECTED_GROUPS]
    assert EXPECTED_GROUPS[2].affinity_decision_id == "C2A0004B"
    assert EXPECTED_GROUPS[3].affinity_decision_id == "C2A0004B"
    assert EXPECTED_GROUPS[2].corrected_evidence_level == "E3"
    assert EXPECTED_GROUPS[3].corrected_evidence_level == "E5"
    members = expected_record_ids()
    assert len(members) == EXPECTED_UNIQUE_RECORDS
    assert len(set(members)) == EXPECTED_UNIQUE_RECORDS
    assert dict(EXPECTED_GROUP_COUNTS) == {
        group.decision_id: len(group.record_ids) for group in EXPECTED_GROUPS
    }
    distribution = {"E2": 0, "E3": 0, "E4": 0, "E5": 0}
    transitions: dict[tuple[str, str], int] = {}
    for group in EXPECTED_GROUPS:
        distribution[group.corrected_evidence_level] += len(group.record_ids)
        key = (group.machine_evidence_level, group.corrected_evidence_level)
        transitions[key] = transitions.get(key, 0) + len(group.record_ids)
    assert distribution == EXPECTED_CORRECTED_DISTRIBUTION
    assert transitions == EXPECTED_TRANSITIONS


def test_materialise_nine_blank_rows_independent_of_csv_order() -> None:
    evidence = _machine_rows()
    affinity = _affinity_rows()
    original = _original_evidence_rows()
    shuffled_evidence = list(reversed(evidence))
    shuffled_affinity = list(reversed(affinity))
    first = materialise_evidence_consistency_review(
        shuffled_evidence,
        shuffled_affinity,
        original + _original_machine_rows(),
        flagged_record_ids=expected_record_ids(),
    )
    second = materialise_evidence_consistency_review(
        evidence,
        affinity,
        original,
        flagged_record_ids=expected_record_ids(),
    )
    assert [row["decision_id"] for row in first] == list(EXPECTED_DECISION_IDS)
    assert [row["decision_id"] for row in second] == list(EXPECTED_DECISION_IDS)
    assert [row["record_ids"] for row in first] == [row["record_ids"] for row in second]
    assert [row["n_records"] for row in first] == [
        str(EXPECTED_GROUP_COUNTS[decision_id]) for decision_id in EXPECTED_DECISION_IDS
    ]
    seen: set[str] = set()
    for row in first:
        members = row["record_ids"].split("|")
        assert len(members) == int(row["n_records"])
        assert not set(members) & seen
        seen.update(members)
        for field in HUMAN_FIELDS:
            assert row[field] == ""
        assert row["machine_recommendation"] == "override_evidence"
    assert len(seen) == EXPECTED_UNIQUE_RECORDS
    by_id = {row["decision_id"]: row for row in first}
    assert by_id["C2EC0001"]["source_db"] == "aptabase"
    assert by_id["C2EC0001"]["evidence_level_proposed"] == "E4"
    assert by_id["C2EC0001"]["corrected_evidence_level_proposed"] == "E2"
    assert by_id["C2EC0001"]["affinity_decision_id"] == "C2A0002"
    assert by_id["C2EC0003"]["corrected_evidence_level_proposed"] == "E3"
    assert by_id["C2EC0004"]["corrected_evidence_level_proposed"] == "E5"
    assert by_id["C2EC0004"]["affinity_decision_id"] == "C2A0004B"


def test_materialise_is_idempotent_and_preserves_human_fields() -> None:
    evidence = _machine_rows()
    affinity = _affinity_rows()
    original = _original_evidence_rows()
    first = materialise_evidence_consistency_review(
        evidence,
        affinity,
        original,
        flagged_record_ids=expected_record_ids(),
    )
    second = materialise_evidence_consistency_review(
        evidence,
        affinity,
        original,
        first,
        flagged_record_ids=expected_record_ids(),
    )
    assert [row["decision_id"] for row in second] == list(EXPECTED_DECISION_IDS)
    assert [row["record_ids"] for row in second] == [row["record_ids"] for row in first]
    reviewed = [dict(row) for row in first]
    reviewed[0]["manual_decision"] = "override_evidence"
    reviewed[0]["manual_evidence_level"] = "E2"
    reviewed[0]["manual_notes"] = "keep-me"
    third = materialise_evidence_consistency_review(
        evidence,
        affinity,
        original,
        reviewed,
        flagged_record_ids=expected_record_ids(),
    )
    retained = {row["decision_id"]: row for row in third}
    assert retained["C2EC0001"]["manual_decision"] == "override_evidence"
    assert retained["C2EC0001"]["manual_evidence_level"] == "E2"
    assert retained["C2EC0001"]["manual_notes"] == "keep-me"
    assert retained["C2EC0002"]["manual_decision"] == ""
    assert len(third) == 9


def test_blank_supplemental_does_not_change_effective_evidence() -> None:
    machine = _machine_rows()[0]
    supplemental = materialise_evidence_consistency_review(
        _machine_rows(),
        _affinity_rows(),
        _original_evidence_rows(),
        flagged_record_ids=expected_record_ids(),
    )
    projected = project_effective_evidence_level(
        machine, supplemental_rows=supplemental
    )
    assert projected["evidence_level"] == "E4"
    assert projected["source"] == EVIDENCE_SOURCE_MACHINE
    assert projected["decision_id"] == ""


def test_completed_supplemental_outranks_machine_and_original() -> None:
    machine = {
        "record_id": "aptabase:12",
        "evidence_level_proposed": "E4",
        "source_db": "aptabase",
        "evidence_rule": "APTABASE_SELECTION_PUBLICATION",
        "e4_e5_threshold_ambiguous": "false",
    }
    original = [
        {
            "decision_id": "C2E0001",
            "source_db": "aptabase",
            "evidence_rule": "APTABASE_SELECTION_PUBLICATION",
            "evidence_level_proposed": "E4",
            "alternative_evidence_level": "E5",
            "manual_decision": "confirm_evidence",
        }
    ]
    original_machine = [
        {
            **machine,
            "e4_e5_threshold_ambiguous": "true",
            "alternative_evidence_level": "E5",
        }
    ]
    blank = {
        "decision_id": "C2EC0001",
        "record_ids": "aptabase:12",
        "manual_decision": "",
        "manual_evidence_level": "",
        "corrected_evidence_level_proposed": "E2",
    }
    completed = {
        **blank,
        "manual_decision": "override_evidence",
        "manual_evidence_level": "E2",
    }
    assert (
        project_effective_evidence_level(
            machine, supplemental_rows=[blank], original_evidence_rows=original
        )["source"]
        == EVIDENCE_SOURCE_MACHINE
    )
    original_only = project_effective_evidence_level(
        original_machine[0],
        supplemental_rows=[blank],
        original_evidence_rows=original,
        original_by_record=original_evidence_membership(original, original_machine),
    )
    assert original_only["source"] == EVIDENCE_SOURCE_ORIGINAL
    assert original_only["evidence_level"] == "E4"
    asserted = project_effective_evidence_level(
        original_machine[0],
        supplemental_rows=[completed],
        original_evidence_rows=original,
        original_by_record=original_evidence_membership(original, original_machine),
    )
    assert asserted["source"] == EVIDENCE_SOURCE_SUPPLEMENTAL
    assert asserted["evidence_level"] == "E2"
    assert asserted["decision_id"] == "C2EC0001"


def test_original_evidence_override_outranks_machine() -> None:
    machine = _original_machine_rows()[0]
    original = _original_evidence_rows()
    projected = project_effective_evidence_level(
        machine,
        original_evidence_rows=original,
        original_by_record=original_evidence_membership(original, [machine]),
    )
    assert projected["source"] == EVIDENCE_SOURCE_ORIGINAL
    assert projected["evidence_level"] == "E5"
    assert projected["decision_id"] == "C2E0001"


def test_completed_supplemental_clears_effective_flag() -> None:
    machine = {
        "record_id": "syn:nobind",
        "relationship_index": "1",
        "source_db": "synthetic",
        "evidence_level_proposed": "E2",
        "evidence_rule": "SYN_E2",
        "e4_e5_threshold_ambiguous": "false",
        "affinity_requires_review": "true",
        "affinity_parse_status": "malformed",
        "affinity_parse_rule": "unparseable_numeric",
        "affinity_type_proposed": "Kd",
        "affinity_value_raw": "no binding",
        "affinity_unit_raw": "",
    }
    review = {
        "decision_id": "C2A0010",
        "source_db": "synthetic",
        "affinity_parse_status": "malformed",
        "affinity_parse_rule": "unparseable_numeric",
        "record_ids": "syn:nobind",
        "manual_decision": EXCLUDE_NON_AFFINITY,
        "manual_affinity_non_affinity_reason": "no_binding",
    }
    blank_flags = collect_consistency_flag_record_ids(
        [machine],
        [review],
        supplemental_rows=[
            {
                "decision_id": "C2EC0005",
                "record_ids": "syn:nobind",
                "manual_decision": "",
                "corrected_evidence_level_proposed": "E5",
            }
        ],
    )
    assert blank_flags == ("syn:nobind",)
    completed_flags = collect_consistency_flag_record_ids(
        [machine],
        [review],
        supplemental_rows=[
            {
                "decision_id": "C2EC0005",
                "record_ids": "syn:nobind",
                "manual_decision": "override_evidence",
                "manual_evidence_level": "E5",
                "corrected_evidence_level_proposed": "E5",
            }
        ],
    )
    assert completed_flags == ()
    overlay = {
        "affinity_review_status": "exclude_non_affinity",
        "machine_evidence_level": "E2",
        "effective_evidence_level": "E5",
    }
    assert flag_evidence_affinity_inconsistency(overlay) == ""
    overlay["effective_evidence_level"] = ""
    assert flag_evidence_affinity_inconsistency(overlay) == "evidence_affinity_inconsistency"


def test_overlap_with_original_evidence_stops_materialisation() -> None:
    evidence = _machine_rows()
    affinity = _affinity_rows()
    original = _original_evidence_rows()
    colliding = {
        "record_id": "aptabase:12",
        "source_db": "aptadb",
        "evidence_rule": "APTADB_PMID_WITHOUT_ASSAY",
        "evidence_level_proposed": "E4",
        "alternative_evidence_level": "E5",
        "e4_e5_threshold_ambiguous": "true",
    }
    try:
        materialise_evidence_consistency_review(
            evidence + [colliding],
            affinity,
            original,
            flagged_record_ids=expected_record_ids(),
        )
    except ScientificProposalError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("expected overlap to stop materialisation")


def test_flag_mismatch_stops_materialisation() -> None:
    try:
        materialise_evidence_consistency_review(
            _machine_rows(),
            _affinity_rows(),
            _original_evidence_rows(),
            flagged_record_ids=("aptabase:12",),
        )
    except ScientificProposalError as exc:
        assert "flags do not match" in str(exc)
    else:
        raise AssertionError("expected flag mismatch to stop materialisation")


def _write_review_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0].keys()), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def test_validator_counts_blank_supplemental_as_unresolved(tmp_path: Path) -> None:
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
                "affinity_requires_review": "true",
                "affinity_parse_status": "malformed",
                "affinity_parse_rule": "unparseable_numeric",
                "affinity_type_proposed": "Kd",
            }
        ],
        leakage_rows=[],
        routing_rows=[],
    )
    evidence_path = tmp_path / "cp2" / "checkpoint2_evidence_review.csv"
    evs = list(csv.DictReader(evidence_path.open(newline="", encoding="utf-8")))
    evs[0]["manual_decision"] = "confirm_evidence"
    _write_review_csv(evidence_path, evs)
    affinity_path = tmp_path / "cp2" / "checkpoint2_affinity_review.csv"
    affs = list(csv.DictReader(affinity_path.open(newline="", encoding="utf-8")))
    affs[0]["manual_decision"] = EXCLUDE_NON_AFFINITY
    affs[0]["manual_affinity_non_affinity_reason"] = "no_binding"
    affs[0]["record_ids"] = "ena:1"
    _write_review_csv(affinity_path, affs)
    without = validate_checkpoint2_package(tmp_path / "cp2")
    assert without["evidence_consistency_completion"]["missing_package"] is True
    assert without["unresolved_decisions"] == 0

    supplemental = materialise_evidence_consistency_review(
        _machine_rows(),
        _affinity_rows(),
        _original_evidence_rows(),
        flagged_record_ids=expected_record_ids(),
    )
    _write_review_csv(tmp_path / "cp2" / EVIDENCE_CONSISTENCY_FILE, supplemental)
    sibling = tmp_path / "evidence_affinity_proposals.csv"
    with sibling.open("w", encoding="utf-8", newline="") as handle:
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
                "record_id": "ena:1",
                "relationship_index": "1",
                "source_db": "ena",
                "evidence_level_proposed": "E5",
                "affinity_type_proposed": "Kd",
                "affinity_value_raw": "n/a",
                "affinity_unit_raw": "",
                "affinity_parse_status": "malformed",
                "affinity_parse_rule": "unparseable_numeric",
                "affinity_requires_review": "true",
            }
        )
    filled = validate_checkpoint2_package(tmp_path / "cp2")
    assert filled["errors"] == []
    assert filled["evidence_consistency_completion"]["blank"] == 9
    assert filled["evidence_consistency_completion"]["resolved"] == 0
    assert filled["unresolved_decisions"] == 9
    assert filled["ready_for_application"] is False
    for field in HUMAN_FIELDS:
        assert all(row[field] == "" for row in supplemental)


def test_columns_include_evidence_human_schema() -> None:
    for field in ("manual_decision", "manual_evidence_level", "manual_notes"):
        assert field in EVIDENCE_CONSISTENCY_REVIEW_COLUMNS
    for field in HUMAN_FIELDS:
        assert field in EVIDENCE_CONSISTENCY_REVIEW_COLUMNS
    assert CONFIRM_AFFINITY_SCALAR
    assert EVIDENCE_CONSISTENCY_REVIEW_COLUMNS[-len(HUMAN_FIELDS) :] == HUMAN_FIELDS


def _routing_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for group in EXPECTED_GROUPS:
        for record_id in group.record_ids:
            if record_id in {"aptabase:372", "aptabase:373"}:
                route = "park_non_protein"
                target_type = "peptide"
            elif group.decision_id == "C2EC0005":
                route = "hold_target_unresolved"
                target_type = "unknown"
            elif group.decision_id == "C2EC0006":
                route = "park_non_protein"
                target_type = "cell"
            elif group.decision_id == "C2EC0009":
                route = "hold_target_unresolved"
                target_type = "unknown"
            else:
                route = "primary_candidate"
                target_type = "protein"
            rows.append(
                {
                    "record_id": record_id,
                    "relationship_status": "resolved_single",
                    "target_type_proposed": target_type,
                    "routing_preview": route,
                    "leakage_exclusion_proposed": "false",
                }
            )
    return rows


def test_authorised_decisions_are_complete_overrides() -> None:
    blank = materialise_evidence_consistency_review(
        _machine_rows(),
        _affinity_rows(),
        _original_evidence_rows(),
        flagged_record_ids=expected_record_ids(),
    )
    recorded = apply_evidence_consistency_decisions(
        blank, AUTHORISED_EVIDENCE_CONSISTENCY_DECISIONS
    )
    assert [row["decision_id"] for row in recorded] == list(EXPECTED_DECISION_IDS)
    assert all(row["manual_decision"] == "override_evidence" for row in recorded)
    counts: dict[str, int] = {"E2": 0, "E3": 0, "E4": 0, "E5": 0}
    record_counts: dict[str, int] = {"E2": 0, "E3": 0, "E4": 0, "E5": 0}
    for row in recorded:
        level = row["manual_evidence_level"]
        counts[level] += 1
        record_counts[level] += int(row["n_records"])
        assert row["manual_evidence_level"] == next(
            group.corrected_evidence_level
            for group in EXPECTED_GROUPS
            if group.decision_id == row["decision_id"]
        )
        for field in HUMAN_FIELDS:
            if field in {"manual_decision", "manual_evidence_level", "manual_notes"}:
                assert row[field]
            else:
                assert row[field] == ""
    assert counts == EXPECTED_DECISION_LEVEL_COUNTS
    assert record_counts == EXPECTED_CORRECTED_DISTRIBUTION
    c2ec5 = next(row for row in recorded if row["decision_id"] == "C2EC0005")
    assert "do not encode no-binding as zero kd" in c2ec5["manual_notes"].casefold()
    compare_consistency_review_to_pristine(recorded, blank)
    drifted = [dict(row) for row in recorded]
    drifted[0]["evidence_level_proposed"] = "E1"
    try:
        compare_consistency_review_to_pristine(drifted, blank)
    except ScientificProposalError as exc:
        assert "machine field" in str(exc)
    else:
        raise AssertionError("expected pristine machine-field drift to fail")


def test_recorded_supplemental_outcomes_and_routing_dry_run() -> None:
    blank = materialise_evidence_consistency_review(
        _machine_rows(),
        _affinity_rows(),
        _original_evidence_rows(),
        flagged_record_ids=expected_record_ids(),
    )
    recorded = apply_evidence_consistency_decisions(
        blank, AUTHORISED_EVIDENCE_CONSISTENCY_DECISIONS
    )
    outcomes = summarise_member_outcomes(
        _machine_rows() + _original_machine_rows(),
        recorded,
        _original_evidence_rows(),
    )
    assert outcomes["distribution"] == EXPECTED_CORRECTED_DISTRIBUTION
    assert outcomes["transitions"] == {
        "E4->E2": 9,
        "E2->E3": 30,
        "E2->E5": 10,
    }
    routing = dry_run_supplemental_routing(
        supplemental_rows=recorded,
        routing_rows=_routing_rows(),
        machine_evidence_rows=_machine_rows(),
        original_evidence_rows=_original_evidence_rows(),
        target_parked_record_ids=EXPECTED_TARGET_PARKED_INDEPENDENT,
    )
    assert routing["new_evidence_parks"] == list(EXPECTED_NEW_EVIDENCE_PARKS)
    assert len(routing["pass_e2"]) == 9
    assert len(routing["pass_e3"]) == 30
    assert len(routing["fail_e5"]) == 10
    independent = set(routing["independent_parks"])
    assert set(EXPECTED_TARGET_PARKED_INDEPENDENT) <= independent
    assert {"aptabase:372", "aptabase:373"} <= independent
    assert {"aptamerbase:0127", "aptamerbase:0129", "aptamerbase:1516"} <= independent
    assert {"riboaptamer:487", "riboaptamer:488"} <= independent
    assert "utexas:row_1491" in independent


def test_validator_ready_after_recorded_supplemental(tmp_path: Path) -> None:
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
                "affinity_requires_review": "true",
                "affinity_parse_status": "malformed",
                "affinity_parse_rule": "unparseable_numeric",
                "affinity_type_proposed": "Kd",
            }
        ],
        leakage_rows=[],
        routing_rows=[],
    )
    evidence_path = tmp_path / "cp2" / "checkpoint2_evidence_review.csv"
    evs = list(csv.DictReader(evidence_path.open(newline="", encoding="utf-8")))
    evs[0]["manual_decision"] = "confirm_evidence"
    _write_review_csv(evidence_path, evs)
    affinity_path = tmp_path / "cp2" / "checkpoint2_affinity_review.csv"
    affs = list(csv.DictReader(affinity_path.open(newline="", encoding="utf-8")))
    affs[0]["manual_decision"] = EXCLUDE_NON_AFFINITY
    affs[0]["manual_affinity_non_affinity_reason"] = "no_binding"
    affs[0]["record_ids"] = "ena:1"
    _write_review_csv(affinity_path, affs)
    blank = materialise_evidence_consistency_review(
        _machine_rows(),
        _affinity_rows(),
        _original_evidence_rows(),
        flagged_record_ids=expected_record_ids(),
    )
    recorded = apply_evidence_consistency_decisions(
        blank, AUTHORISED_EVIDENCE_CONSISTENCY_DECISIONS
    )
    _write_review_csv(tmp_path / "cp2" / EVIDENCE_CONSISTENCY_FILE, recorded)
    sibling = tmp_path / "evidence_affinity_proposals.csv"
    with sibling.open("w", encoding="utf-8", newline="") as handle:
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
                "record_id": "ena:1",
                "relationship_index": "1",
                "source_db": "ena",
                "evidence_level_proposed": "E5",
                "affinity_type_proposed": "Kd",
                "affinity_value_raw": "n/a",
                "affinity_unit_raw": "",
                "affinity_parse_status": "malformed",
                "affinity_parse_rule": "unparseable_numeric",
                "affinity_requires_review": "true",
            }
        )
    filled = validate_checkpoint2_package(tmp_path / "cp2")
    assert filled["errors"] == []
    assert filled["evidence_consistency_completion"]["blank"] == 0
    assert filled["evidence_consistency_completion"]["resolved"] == 9
    assert filled["unresolved_decisions"] == 0
    assert filled["n_evidence_affinity_inconsistencies"] == 0
    assert filled["ready_for_application"] is True
    assert EVIDENCE_SCORE_BY_LEVEL["E2"] == 4
    assert EVIDENCE_SCORE_BY_LEVEL["E3"] == 3
    assert EVIDENCE_SCORE_BY_LEVEL["E5"] == 1

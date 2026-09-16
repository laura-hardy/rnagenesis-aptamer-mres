"""Supplemental CHECKPOINT-2 evidence-consistency review. Not the apply stage.

The closed 3-row E4/E5 evidence review (C2E0001–C2E0003) is not reopened.
These C2EC* rows reconcile completed affinity review with machine evidence
for the 49 evidence-affinity inconsistency records. Human C2EC fields
are recorded as override_evidence in Milestone 4F.3. Machine proposal
tables are not mutated. CHECKPOINT-2 application remains out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from adapters.checkpoint2_affinity import (
    project_affinity_reviews,
)
from adapters.s4_scientific_common import (
    CONFIRM_AFFINITY_SCALAR,
    EVIDENCE_DECISION_VOCAB,
    EVIDENCE_SCORE_BY_LEVEL,
    EVIDENCE_TYPE_BY_LEVEL,
    EXCLUDE_NON_AFFINITY,
    HUMAN_FIELDS,
    ScientificProposalError,
    assert_human_fields_blank,
    blank_human_fields,
    fill_row,
    join_unique,
    split_pipe,
)

ORIGINAL_EVIDENCE_DECISION_IDS: tuple[str, ...] = ("C2E0001", "C2E0002", "C2E0003")
EXPECTED_DECISION_IDS: tuple[str, ...] = (
    "C2EC0001",
    "C2EC0002",
    "C2EC0003",
    "C2EC0004",
    "C2EC0005",
    "C2EC0006",
    "C2EC0007",
    "C2EC0008",
    "C2EC0009",
)
EXPECTED_GROUP_COUNTS: dict[str, int] = {
    "C2EC0001": 4,
    "C2EC0002": 9,
    "C2EC0003": 19,
    "C2EC0004": 6,
    "C2EC0005": 3,
    "C2EC0006": 2,
    "C2EC0007": 2,
    "C2EC0008": 3,
    "C2EC0009": 1,
}
EXPECTED_UNIQUE_RECORDS = 49
EXPECTED_CORRECTED_DISTRIBUTION: dict[str, int] = {"E2": 9, "E3": 30, "E4": 0, "E5": 10}
EXPECTED_TRANSITIONS: dict[tuple[str, str], int] = {
    ("E4", "E2"): 9,
    ("E2", "E3"): 30,
    ("E2", "E5"): 10,
}
EXPECTED_DECISION_LEVEL_COUNTS: dict[str, int] = {"E2": 3, "E3": 3, "E4": 0, "E5": 3}
EXPECTED_NEW_EVIDENCE_PARKS: tuple[str, ...] = (
    "aptadb:132",
    "aptadb:133",
    "aptadb:134",
    "aptadb:135",
    "aptadb:136",
    "aptadb:1068",
)
EXPECTED_TARGET_PARKED_INDEPENDENT: tuple[str, ...] = (
    "aptadb:383",
    "aptadb:384",
    "aptadb:385",
    "aptadb:386",
)
INDEPENDENT_MACHINE_ROUTES: frozenset[str] = frozenset(
    {
        "hold_target_unresolved",
        "park_non_protein",
        "leakage_exclusion_proposed",
        "reject_no_binding_evidence",
        "hold_evidence_ambiguous",
    }
)
PASSES_EVIDENCE_THRESHOLD = frozenset({"E1", "E2", "E3", "E4"})

EVIDENCE_CONSISTENCY_FILE = "checkpoint2_evidence_consistency_review.csv"
EVIDENCE_SOURCE_SUPPLEMENTAL = "supplemental_consistency_review"
EVIDENCE_SOURCE_ORIGINAL = "original_evidence_review"
EVIDENCE_SOURCE_MACHINE = "machine_evidence"

# Ordering (independent of CSV row order):
# 1. Source/review groups from Milestone 4F.1:
#    AptaBase C2A0002, AptaDB C2A0004A, AptaDB C2A0004B,
#    AptamerBase C2A0010, RiboAptamer C2A0014B, RiboAptamer C2A0016A,
#    RiboAptamer C2A0016B, UTexas C2A0019.
# 2. Within C2A0004B, the E3 remainder subgroup is assigned before the
#    E5 annotation-only subgroup.
# 3. Record membership is the frozen 4F.1 inventory, not CSV enumeration.
DECISION_ID_ORDERING = (
    "C2EC0001 AptaBase C2A0002 recovered quantitative Kd",
    "C2EC0002 AptaDB C2A0004A assay-caption false E2, qualitative binding remains",
    "C2EC0003 AptaDB C2A0004B foreign/non-row Kd removed, qualitative binding remains (E3 before E5)",
    "C2EC0004 AptaDB C2A0004B foreign/non-row Kd removed, annotation only",
    "C2EC0005 AptamerBase C2A0010 no binding",
    "C2EC0006 RiboAptamer C2A0014B binding percentage",
    "C2EC0007 RiboAptamer C2A0016A recovered GRK2 Kd",
    "C2EC0008 RiboAptamer C2A0016B recovered glued-unit Kd",
    "C2EC0009 UTexas C2A0019 TBD placeholder",
)

EVIDENCE_CONSISTENCY_REVIEW_COLUMNS: tuple[str, ...] = (
    "decision_id",
    "source_db",
    "record_ids",
    "n_records",
    "record_ids_preview",
    "evidence_level_proposed",
    "evidence_rule",
    "evidence_provenance",
    "affinity_decision_id",
    "reviewed_affinity_outcome",
    "affinity_transform_rule",
    "corrected_evidence_level_proposed",
    "corrected_evidence_score",
    "consistency_reason",
    "routing_consequence",
    "scientific_ambiguity_reason",
    "machine_recommendation",
    *HUMAN_FIELDS,
)

ROUTING_PASS_E4 = "passes_e4_inclusion_threshold"
ROUTING_FAIL_NEW_PARK = "fails_e4_inclusion_threshold_new_evidence_park"
ROUTING_FAIL_TARGET_HELD = "fails_e4_inclusion_threshold_already_target_held"
ROUTING_FAIL_TARGET_UNRESOLVED = "fails_e4_inclusion_threshold_already_target_unresolved"


def _blank(value: str | None) -> str:
    return (value or "").strip()


def _preview_ids(record_ids: Sequence[str], *, limit: int = 8) -> str:
    ordered = list(dict.fromkeys(item for item in record_ids if item))
    if len(ordered) <= limit:
        return "|".join(ordered)
    return "|".join(ordered[:limit]) + f"|+{len(ordered) - limit}"


@dataclass(frozen=True)
class EvidenceConsistencyGroup:
    decision_id: str
    source_db: str
    record_ids: tuple[str, ...]
    machine_evidence_level: str
    expected_evidence_rule: str
    affinity_decision_id: str
    reviewed_affinity_outcome: str
    corrected_evidence_level: str
    consistency_reason: str
    routing_consequence: str
    scientific_ambiguity_reason: str


EXPECTED_GROUPS: tuple[EvidenceConsistencyGroup, ...] = (
    EvidenceConsistencyGroup(
        decision_id="C2EC0001",
        source_db="aptabase",
        record_ids=("aptabase:12", "aptabase:372", "aptabase:373", "aptabase:419"),
        machine_evidence_level="E4",
        expected_evidence_rule="APTABASE_SELECTION_PUBLICATION",
        affinity_decision_id="C2A0002",
        reviewed_affinity_outcome=CONFIRM_AFFINITY_SCALAR,
        corrected_evidence_level="E2",
        consistency_reason="machine_e4_reviewed_exact_quantitative_affinity",
        routing_consequence=ROUTING_PASS_E4,
        scientific_ambiguity_reason=(
            "Reviewed affinity is a genuine per-record aptamer-target Kd "
            "recovered by mojibake_micro_M; machine E4 is a false negative."
        ),
    ),
    EvidenceConsistencyGroup(
        decision_id="C2EC0002",
        source_db="aptadb",
        record_ids=(
            "aptadb:51",
            "aptadb:157",
            "aptadb:158",
            "aptadb:159",
            "aptadb:433",
            "aptadb:434",
            "aptadb:435",
            "aptadb:465",
            "aptadb:1200",
        ),
        machine_evidence_level="E2",
        expected_evidence_rule="APTADB_QUANTITATIVE_AFFINITY",
        affinity_decision_id="C2A0004A",
        reviewed_affinity_outcome=EXCLUDE_NON_AFFINITY,
        corrected_evidence_level="E3",
        consistency_reason="machine_e2_reviewed_non_affinity_qualitative_binding_remains",
        routing_consequence=ROUTING_PASS_E4,
        scientific_ambiguity_reason=(
            "Numeric/caption material is not a row-specific Kd, but a named "
            "aptamer-target binding assay remains locally preserved."
        ),
    ),
    EvidenceConsistencyGroup(
        decision_id="C2EC0003",
        source_db="aptadb",
        record_ids=(
            "aptadb:1",
            "aptadb:2",
            "aptadb:6",
            "aptadb:43",
            "aptadb:52",
            "aptadb:53",
            "aptadb:54",
            "aptadb:55",
            "aptadb:99",
            "aptadb:174",
            "aptadb:273",
            "aptadb:285",
            "aptadb:298",
            "aptadb:324",
            "aptadb:383",
            "aptadb:384",
            "aptadb:385",
            "aptadb:386",
            "aptadb:1170",
        ),
        machine_evidence_level="E2",
        expected_evidence_rule="APTADB_QUANTITATIVE_AFFINITY",
        affinity_decision_id="C2A0004B",
        reviewed_affinity_outcome=EXCLUDE_NON_AFFINITY,
        corrected_evidence_level="E3",
        consistency_reason="machine_e2_reviewed_non_affinity_qualitative_binding_remains",
        routing_consequence=ROUTING_PASS_E4,
        scientific_ambiguity_reason=(
            "Parsed quantitative value belongs to a control, comparison, group "
            "statement, titration concentration, or another aptamer, but "
            "direct/functional qualitative aptamer-target interaction remains "
            "locally supported. aptadb:383-386 remain target-parked regardless "
            "of this evidence correction."
        ),
    ),
    EvidenceConsistencyGroup(
        decision_id="C2EC0004",
        source_db="aptadb",
        record_ids=(
            "aptadb:132",
            "aptadb:133",
            "aptadb:134",
            "aptadb:135",
            "aptadb:136",
            "aptadb:1068",
        ),
        machine_evidence_level="E2",
        expected_evidence_rule="APTADB_QUANTITATIVE_AFFINITY",
        affinity_decision_id="C2A0004B",
        reviewed_affinity_outcome=EXCLUDE_NON_AFFINITY,
        corrected_evidence_level="E5",
        consistency_reason="machine_e2_reviewed_non_affinity_annotation_only",
        routing_consequence=ROUTING_FAIL_NEW_PARK,
        scientific_ambiguity_reason=(
            "After removing the false row-level Kd, remaining local material is "
            "not an aptamer-target binding assay (IL2-CD25 protein-protein EC50 "
            "or an Azo-1 absorption spectrum). Only publication/database association "
            "remains. These protein-primary rows would become new evidence parks."
        ),
    ),
    EvidenceConsistencyGroup(
        decision_id="C2EC0005",
        source_db="aptamerbase",
        record_ids=("aptamerbase:0127", "aptamerbase:0129", "aptamerbase:1516"),
        machine_evidence_level="E2",
        expected_evidence_rule="APTAMERBASE_INTERACTION_KD",
        affinity_decision_id="C2A0010",
        reviewed_affinity_outcome=EXCLUDE_NON_AFFINITY,
        corrected_evidence_level="E5",
        consistency_reason="machine_e2_reviewed_non_affinity_no_binding",
        routing_consequence=ROUTING_FAIL_TARGET_HELD,
        scientific_ambiguity_reason=(
            "RDF no binding was incorrectly stored as a dissociation-constant "
            "value. No SELEX or publication evidence remains locally. Negative "
            "binding is not E2 or E3. Rows are already target-type held and later "
            "eligible for reject_no_binding_evidence."
        ),
    ),
    EvidenceConsistencyGroup(
        decision_id="C2EC0006",
        source_db="riboaptamer",
        record_ids=("riboaptamer:487", "riboaptamer:488"),
        machine_evidence_level="E2",
        expected_evidence_rule="RIBOAPTAMER_QUANTITATIVE_KD",
        affinity_decision_id="C2A0014B",
        reviewed_affinity_outcome=EXCLUDE_NON_AFFINITY,
        corrected_evidence_level="E3",
        consistency_reason="machine_e2_reviewed_non_affinity_qualitative_binding_remains",
        routing_consequence=ROUTING_PASS_E4,
        scientific_ambiguity_reason=(
            "The percentage is not a Kd, but it is a measured aptamer-target "
            "binding fraction and therefore supports qualitative binding. These "
            "records remain non-protein/cell parked independently."
        ),
    ),
    EvidenceConsistencyGroup(
        decision_id="C2EC0007",
        source_db="riboaptamer",
        record_ids=("riboaptamer:347", "riboaptamer:348"),
        machine_evidence_level="E4",
        expected_evidence_rule="RIBOAPTAMER_PUBLICATION_SELECTION",
        affinity_decision_id="C2A0016A",
        reviewed_affinity_outcome=CONFIRM_AFFINITY_SCALAR,
        corrected_evidence_level="E2",
        consistency_reason="machine_e4_reviewed_exact_quantitative_affinity",
        routing_consequence=ROUTING_PASS_E4,
        scientific_ambiguity_reason=(
            "Reviewed affinity is an exact central Kd with uncertainty retained; "
            "machine E4 is a false negative."
        ),
    ),
    EvidenceConsistencyGroup(
        decision_id="C2EC0008",
        source_db="riboaptamer",
        record_ids=("riboaptamer:120", "riboaptamer:121", "riboaptamer:452"),
        machine_evidence_level="E4",
        expected_evidence_rule="RIBOAPTAMER_PUBLICATION_SELECTION",
        affinity_decision_id="C2A0016B",
        reviewed_affinity_outcome=CONFIRM_AFFINITY_SCALAR,
        corrected_evidence_level="E2",
        consistency_reason="machine_e4_reviewed_exact_quantitative_affinity",
        routing_consequence=ROUTING_PASS_E4,
        scientific_ambiguity_reason=(
            "Reviewed affinity is an exact target-specific Kd recovered from a "
            "glued unit; machine E4 is a false negative."
        ),
    ),
    EvidenceConsistencyGroup(
        decision_id="C2EC0009",
        source_db="utexas",
        record_ids=("utexas:row_1491",),
        machine_evidence_level="E2",
        expected_evidence_rule="UTEXAS_QUANTITATIVE_KD",
        affinity_decision_id="C2A0019",
        reviewed_affinity_outcome=EXCLUDE_NON_AFFINITY,
        corrected_evidence_level="E5",
        consistency_reason="machine_e2_reviewed_non_affinity_placeholder",
        routing_consequence=ROUTING_FAIL_TARGET_UNRESOLVED,
        scientific_ambiguity_reason=(
            "TBD is not a quantitative affinity. Remaining local support is "
            "patent/database association only. The record is already target-unresolved."
        ),
    ),
)


def validate_group_spec() -> None:
    ids = [group.decision_id for group in EXPECTED_GROUPS]
    if ids != list(EXPECTED_DECISION_IDS):
        raise ScientificProposalError(f"C2EC decision IDs drifted: {ids}")
    members: list[str] = []
    for group in EXPECTED_GROUPS:
        if group.decision_id not in EXPECTED_GROUP_COUNTS:
            raise ScientificProposalError(f"missing count for {group.decision_id}")
        if len(group.record_ids) != EXPECTED_GROUP_COUNTS[group.decision_id]:
            raise ScientificProposalError(
                f"{group.decision_id} expected {EXPECTED_GROUP_COUNTS[group.decision_id]} "
                f"records, got {len(group.record_ids)}"
            )
        if len(set(group.record_ids)) != len(group.record_ids):
            raise ScientificProposalError(f"{group.decision_id} has duplicate members")
        members.extend(group.record_ids)
    if len(members) != len(set(members)):
        raise ScientificProposalError("C2EC groups have overlapping record membership")
    if len(set(members)) != EXPECTED_UNIQUE_RECORDS:
        raise ScientificProposalError(
            f"expected {EXPECTED_UNIQUE_RECORDS} unique records, got {len(set(members))}"
        )
    distribution: dict[str, int] = {"E2": 0, "E3": 0, "E4": 0, "E5": 0}
    transitions: dict[tuple[str, str], int] = {}
    for group in EXPECTED_GROUPS:
        distribution[group.corrected_evidence_level] = (
            distribution.get(group.corrected_evidence_level, 0) + len(group.record_ids)
        )
        key = (group.machine_evidence_level, group.corrected_evidence_level)
        transitions[key] = transitions.get(key, 0) + len(group.record_ids)
    if distribution != EXPECTED_CORRECTED_DISTRIBUTION:
        raise ScientificProposalError(f"corrected distribution drifted: {distribution}")
    if transitions != EXPECTED_TRANSITIONS:
        raise ScientificProposalError(f"correction transitions drifted: {transitions}")
    decision_levels: dict[str, int] = {"E2": 0, "E3": 0, "E4": 0, "E5": 0}
    for group in EXPECTED_GROUPS:
        decision_levels[group.corrected_evidence_level] = (
            decision_levels.get(group.corrected_evidence_level, 0) + 1
        )
    if decision_levels != EXPECTED_DECISION_LEVEL_COUNTS:
        raise ScientificProposalError(
            f"decision-level counts drifted: {decision_levels}"
        )


def expected_record_ids() -> tuple[str, ...]:
    members: list[str] = []
    for group in EXPECTED_GROUPS:
        members.extend(group.record_ids)
    return tuple(members)


def _index_by_record_id(rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    out: dict[str, Mapping[str, str]] = {}
    for row in rows:
        record_id = _blank(row.get("record_id"))
        if record_id and record_id not in out:
            out[record_id] = row
    return out


def _index_affinity_by_record(
    affinity_review_rows: Sequence[Mapping[str, str]],
) -> dict[str, Mapping[str, str]]:
    out: dict[str, Mapping[str, str]] = {}
    for row in affinity_review_rows:
        for record_id in split_pipe(_blank(row.get("record_ids"))):
            if record_id in out:
                raise ScientificProposalError(
                    f"affinity review maps {record_id} to multiple rows"
                )
            out[record_id] = row
    return out


def original_evidence_membership(
    original_evidence_rows: Sequence[Mapping[str, str]],
    machine_rows: Sequence[Mapping[str, str]],
) -> dict[str, Mapping[str, str]]:
    """Map record_id -> original C2E* review row via E4/E5 grouping keys."""
    groups: dict[tuple[str, str, str, str], Mapping[str, str]] = {}
    for row in original_evidence_rows:
        decision_id = _blank(row.get("decision_id"))
        if decision_id and decision_id not in ORIGINAL_EVIDENCE_DECISION_IDS:
            continue
        key = (
            _blank(row.get("source_db")),
            _blank(row.get("evidence_rule")),
            _blank(row.get("evidence_level_proposed")),
            _blank(row.get("alternative_evidence_level")),
        )
        groups[key] = row
    membership: dict[str, Mapping[str, str]] = {}
    for machine in machine_rows:
        if _blank(machine.get("e4_e5_threshold_ambiguous")) != "true":
            continue
        key = (
            _blank(machine.get("source_db")),
            _blank(machine.get("evidence_rule")),
            _blank(machine.get("evidence_level_proposed")),
            _blank(machine.get("alternative_evidence_level")),
        )
        review = groups.get(key)
        if review is None:
            continue
        record_id = _blank(machine.get("record_id"))
        if record_id:
            membership[record_id] = review
    return membership


def supplemental_membership(
    supplemental_rows: Sequence[Mapping[str, str]],
) -> dict[str, Mapping[str, str]]:
    out: dict[str, Mapping[str, str]] = {}
    for row in supplemental_rows:
        for record_id in split_pipe(_blank(row.get("record_ids"))):
            if record_id in out:
                raise ScientificProposalError(
                    f"supplemental review maps {record_id} to multiple rows"
                )
            out[record_id] = row
    return out


def _completed_correction_level(
    review_row: Mapping[str, str] | None,
    *,
    confirm_level_field: str,
) -> str:
    if review_row is None:
        return ""
    decision = _blank(review_row.get("manual_decision"))
    if decision not in EVIDENCE_DECISION_VOCAB:
        return ""
    if decision == "override_evidence":
        return _blank(review_row.get("manual_evidence_level"))
    if decision == "confirm_evidence":
        return _blank(review_row.get(confirm_level_field)) or _blank(
            review_row.get("evidence_level_proposed")
        )
    return ""


def project_effective_evidence_level(
    machine_row: Mapping[str, str],
    *,
    supplemental_rows: Sequence[Mapping[str, str]] = (),
    original_evidence_rows: Sequence[Mapping[str, str]] = (),
    supplemental_by_record: Mapping[str, Mapping[str, str]] | None = None,
    original_by_record: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, str]:
    """Effective evidence for one record. Does not mutate machine proposals.

    Precedence:
    1. completed supplemental C2EC* correction, if present;
    2. else completed original C2E0001–C2E0003 evidence review;
    3. else machine evidence_level_proposed.
    """
    record_id = _blank(machine_row.get("record_id"))
    machine_level = _blank(machine_row.get("evidence_level_proposed"))
    supp_index = supplemental_by_record
    if supp_index is None:
        supp_index = supplemental_membership(supplemental_rows)
    orig_index = original_by_record
    if orig_index is None:
        orig_index = original_evidence_membership(original_evidence_rows, [machine_row])

    supplemental = supp_index.get(record_id)
    supplemental_level = _completed_correction_level(
        supplemental, confirm_level_field="corrected_evidence_level_proposed"
    )
    if supplemental_level:
        decision_id = _blank(supplemental.get("decision_id") if supplemental else "")
        return {
            "record_id": record_id,
            "evidence_level": supplemental_level,
            "evidence_score": str(EVIDENCE_SCORE_BY_LEVEL.get(supplemental_level, "")),
            "evidence_type": EVIDENCE_TYPE_BY_LEVEL.get(supplemental_level, ""),
            "source": EVIDENCE_SOURCE_SUPPLEMENTAL,
            "decision_id": decision_id,
            "provenance": f"checkpoint2_evidence_consistency:{decision_id}",
        }

    original = orig_index.get(record_id)
    original_level = _completed_correction_level(
        original, confirm_level_field="evidence_level_proposed"
    )
    if original_level:
        decision_id = _blank(original.get("decision_id") if original else "")
        return {
            "record_id": record_id,
            "evidence_level": original_level,
            "evidence_score": str(EVIDENCE_SCORE_BY_LEVEL.get(original_level, "")),
            "evidence_type": EVIDENCE_TYPE_BY_LEVEL.get(original_level, ""),
            "source": EVIDENCE_SOURCE_ORIGINAL,
            "decision_id": decision_id,
            "provenance": f"checkpoint2_evidence:{decision_id}",
        }

    return {
        "record_id": record_id,
        "evidence_level": machine_level,
        "evidence_score": str(EVIDENCE_SCORE_BY_LEVEL.get(machine_level, "")),
        "evidence_type": EVIDENCE_TYPE_BY_LEVEL.get(machine_level, ""),
        "source": EVIDENCE_SOURCE_MACHINE,
        "decision_id": "",
        "provenance": "machine_evidence",
    }


def project_effective_evidence_for_records(
    machine_rows: Sequence[Mapping[str, str]],
    *,
    supplemental_rows: Sequence[Mapping[str, str]] = (),
    original_evidence_rows: Sequence[Mapping[str, str]] = (),
) -> dict[str, dict[str, str]]:
    supp_index = supplemental_membership(supplemental_rows)
    orig_index = original_evidence_membership(original_evidence_rows, machine_rows)
    out: dict[str, dict[str, str]] = {}
    for machine in machine_rows:
        record_id = _blank(machine.get("record_id"))
        if not record_id or record_id in out:
            continue
        out[record_id] = project_effective_evidence_level(
            machine,
            supplemental_by_record=supp_index,
            original_by_record=orig_index,
        )
    return out


def summarise_evidence_consistency(
    supplemental_rows: Sequence[Mapping[str, str]] | None,
) -> dict[str, int | bool]:
    if supplemental_rows is None:
        return {"resolved": 0, "blank": 0, "n_rows": 0, "missing_package": True}
    resolved = 0
    blank = 0
    for row in supplemental_rows:
        if _blank(row.get("manual_decision")):
            resolved += 1
        else:
            blank += 1
    return {
        "resolved": resolved,
        "blank": blank,
        "n_rows": len(list(supplemental_rows)),
        "missing_package": False,
    }


def collect_consistency_flag_record_ids(
    evidence_rows: Sequence[Mapping[str, str]],
    affinity_review_rows: Sequence[Mapping[str, str]],
    *,
    supplemental_rows: Sequence[Mapping[str, str]] = (),
    original_evidence_rows: Sequence[Mapping[str, str]] = (),
) -> tuple[str, ...]:
    """Unique flagged record IDs using effective evidence when available."""
    from adapters.checkpoint2_affinity import flag_evidence_affinity_inconsistency

    projected, _machine_flags = project_affinity_reviews(
        evidence_rows, affinity_review_rows
    )
    effective = project_effective_evidence_for_records(
        evidence_rows,
        supplemental_rows=supplemental_rows,
        original_evidence_rows=original_evidence_rows,
    )
    flagged: list[str] = []
    seen: set[str] = set()
    for row in projected:
        record_id = _blank(row.get("record_id"))
        overlay = dict(row)
        effective_row = effective.get(record_id, {})
        overlay["effective_evidence_level"] = effective_row.get(
            "evidence_level", _blank(row.get("machine_evidence_level"))
        )
        if not flag_evidence_affinity_inconsistency(overlay):
            continue
        if record_id and record_id not in seen:
            seen.add(record_id)
            flagged.append(record_id)
    return tuple(flagged)


def assert_no_original_evidence_overlap(
    flagged_record_ids: Sequence[str],
    original_membership: Mapping[str, Mapping[str, str]],
) -> None:
    overlap = sorted(
        record_id
        for record_id in flagged_record_ids
        if record_id in original_membership
    )
    if overlap:
        raise ScientificProposalError(
            "evidence-consistency flags overlap closed C2E0001-C2E0003: "
            + "|".join(overlap)
        )


def materialise_evidence_consistency_review(
    evidence_rows: Sequence[Mapping[str, str]],
    affinity_review_rows: Sequence[Mapping[str, str]],
    original_evidence_rows: Sequence[Mapping[str, str]],
    existing_rows: Sequence[Mapping[str, str]] = (),
    *,
    columns: Sequence[str] = EVIDENCE_CONSISTENCY_REVIEW_COLUMNS,
    flagged_record_ids: Sequence[str] | None = None,
) -> list[dict[str, str]]:
    """Materialise the 9-row blank supplemental package. Human fields preserved."""
    validate_group_spec()
    spec_ids = set(expected_record_ids())
    original_map = original_evidence_membership(original_evidence_rows, evidence_rows)
    live_flags = flagged_record_ids
    if flagged_record_ids is None:
        live_flags = collect_consistency_flag_record_ids(
            evidence_rows,
            affinity_review_rows,
            original_evidence_rows=original_evidence_rows,
        )
    if live_flags is not None:
        if set(live_flags) != spec_ids:
            raise ScientificProposalError(
                "live evidence-affinity flags do not match the frozen 49-record "
                f"C2EC inventory: extra={sorted(set(live_flags) - spec_ids)} "
                f"missing={sorted(spec_ids - set(live_flags))}"
            )
        assert_no_original_evidence_overlap(live_flags, original_map)

    existing_by_id = {
        _blank(row.get("decision_id")): dict(row) for row in existing_rows
    }
    unexpected = set(existing_by_id) - set(EXPECTED_DECISION_IDS)
    if unexpected:
        raise ScientificProposalError(
            "existing supplemental review has unexpected decision IDs: "
            + "|".join(sorted(unexpected))
        )

    machine_by_id = _index_by_record_id(evidence_rows)
    affinity_by_id = _index_affinity_by_record(affinity_review_rows)
    out: list[dict[str, str]] = []
    for group in EXPECTED_GROUPS:
        rules: list[str] = []
        provenances: list[str] = []
        transform_rules: list[str] = []
        for record_id in group.record_ids:
            machine = machine_by_id.get(record_id)
            if machine is None:
                raise ScientificProposalError(
                    f"{group.decision_id} missing machine evidence for {record_id}"
                )
            if _blank(machine.get("source_db")) != group.source_db:
                raise ScientificProposalError(
                    f"{group.decision_id} {record_id} source_db mismatch"
                )
            level = _blank(machine.get("evidence_level_proposed"))
            if level != group.machine_evidence_level:
                raise ScientificProposalError(
                    f"{group.decision_id} {record_id} machine evidence {level} "
                    f"!= {group.machine_evidence_level}"
                )
            rule = _blank(machine.get("evidence_rule"))
            if rule != group.expected_evidence_rule:
                raise ScientificProposalError(
                    f"{group.decision_id} {record_id} evidence_rule {rule} "
                    f"!= {group.expected_evidence_rule}"
                )
            rules.append(rule)
            provenances.append(_blank(machine.get("evidence_provenance")))
            affinity = affinity_by_id.get(record_id)
            if affinity is None:
                raise ScientificProposalError(
                    f"{group.decision_id} {record_id} is not in affinity review"
                )
            affinity_id = _blank(affinity.get("decision_id"))
            if affinity_id != group.affinity_decision_id:
                raise ScientificProposalError(
                    f"{group.decision_id} {record_id} affinity {affinity_id} "
                    f"!= {group.affinity_decision_id}"
                )
            outcome = _blank(affinity.get("manual_decision"))
            if outcome != group.reviewed_affinity_outcome:
                raise ScientificProposalError(
                    f"{group.decision_id} {record_id} affinity outcome {outcome} "
                    f"!= {group.reviewed_affinity_outcome}"
                )
            transform_rules.append(
                _blank(affinity.get("manual_affinity_transform_rule"))
                or _blank(affinity.get("machine_affinity_transform_rule"))
            )
        payload = {
            "decision_id": group.decision_id,
            "source_db": group.source_db,
            "record_ids": join_unique(list(group.record_ids)),
            "n_records": str(len(group.record_ids)),
            "record_ids_preview": _preview_ids(group.record_ids),
            "evidence_level_proposed": group.machine_evidence_level,
            "evidence_rule": join_unique(rules) or group.expected_evidence_rule,
            "evidence_provenance": join_unique(provenances),
            "affinity_decision_id": group.affinity_decision_id,
            "reviewed_affinity_outcome": group.reviewed_affinity_outcome,
            "affinity_transform_rule": join_unique(transform_rules),
            "corrected_evidence_level_proposed": group.corrected_evidence_level,
            "corrected_evidence_score": str(
                EVIDENCE_SCORE_BY_LEVEL[group.corrected_evidence_level]
            ),
            "consistency_reason": group.consistency_reason,
            "routing_consequence": group.routing_consequence,
            "scientific_ambiguity_reason": group.scientific_ambiguity_reason,
            "machine_recommendation": "override_evidence",
            **blank_human_fields(),
        }
        existing = existing_by_id.get(group.decision_id)
        if existing is not None:
            for field in HUMAN_FIELDS:
                payload[field] = existing.get(field, "")
        row = fill_row(columns, payload)
        if existing is None:
            assert_human_fields_blank(row, label=f"evidence consistency {group.decision_id}")
        out.append(row)

    ids = [row["decision_id"] for row in out]
    if ids != list(EXPECTED_DECISION_IDS):
        raise ScientificProposalError(f"materialised C2EC IDs drifted: {ids}")
    if len(out) != len(EXPECTED_DECISION_IDS):
        raise ScientificProposalError("materialisation produced the wrong row count")
    return out


def expected_decision_levels() -> dict[str, str]:
    return {group.decision_id: group.corrected_evidence_level for group in EXPECTED_GROUPS}


def apply_evidence_consistency_decisions(
    rows: Sequence[Mapping[str, str]],
    decisions: Mapping[str, Mapping[str, str]],
    *,
    columns: Sequence[str] = EVIDENCE_CONSISTENCY_REVIEW_COLUMNS,
) -> list[dict[str, str]]:
    """Fill authorised human fields. Machine columns are preserved."""
    if len(rows) != len(EXPECTED_DECISION_IDS):
        raise ScientificProposalError(
            f"expected {len(EXPECTED_DECISION_IDS)} supplemental rows, got {len(rows)}"
        )
    expected_levels = expected_decision_levels()
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        decision_id = _blank(row.get("decision_id"))
        fields = decisions.get(decision_id)
        if fields is None:
            raise ScientificProposalError(
                f"unauthorised evidence-consistency decision id {decision_id}"
            )
        if decision_id in seen:
            raise ScientificProposalError(
                f"duplicate evidence-consistency decision id {decision_id}"
            )
        seen.add(decision_id)
        updated = dict(row)
        for field in HUMAN_FIELDS:
            updated[field] = fields.get(field, "")
        filled = fill_row(columns, updated)
        decision = _blank(filled.get("manual_decision"))
        if decision != "override_evidence":
            raise ScientificProposalError(
                f"{decision_id} must be override_evidence, got {decision!r}"
            )
        level = _blank(filled.get("manual_evidence_level"))
        if level != expected_levels[decision_id]:
            raise ScientificProposalError(
                f"{decision_id} manual_evidence_level {level} != {expected_levels[decision_id]}"
            )
        if level == "E4":
            raise ScientificProposalError(f"{decision_id} must not be an E4 decision")
        notes = filled.get("manual_notes", "")
        if decision_id == "C2EC0005":
            folded = notes.casefold()
            if "do not encode" not in folded:
                raise ScientificProposalError(
                    "C2EC0005 must state that no-binding is not encoded as zero Kd"
                )
        out.append(filled)
    missing = sorted(set(EXPECTED_DECISION_IDS) - seen)
    if missing:
        raise ScientificProposalError(
            f"missing authorised evidence-consistency ids: {missing}"
        )
    counts: dict[str, int] = {"E2": 0, "E3": 0, "E4": 0, "E5": 0}
    for fields in decisions.values():
        counts[_blank(fields.get("manual_evidence_level"))] = (
            counts.get(_blank(fields.get("manual_evidence_level")), 0) + 1
        )
    if counts != EXPECTED_DECISION_LEVEL_COUNTS:
        raise ScientificProposalError(f"authorised decision counts drifted: {counts}")
    return out


def compare_consistency_review_to_pristine(
    reviewed_rows: Sequence[Mapping[str, str]],
    pristine_rows: Sequence[Mapping[str, str]],
    *,
    columns: Sequence[str] = EVIDENCE_CONSISTENCY_REVIEW_COLUMNS,
) -> None:
    if len(reviewed_rows) != len(pristine_rows):
        raise ScientificProposalError(
            "supplemental review row count differs from pristine: "
            f"{len(reviewed_rows)} vs {len(pristine_rows)}"
        )
    reviewed_ids = [_blank(row.get("decision_id")) for row in reviewed_rows]
    pristine_ids = [_blank(row.get("decision_id")) for row in pristine_rows]
    if reviewed_ids != pristine_ids:
        raise ScientificProposalError(
            "supplemental decision_id order differs from pristine"
        )
    human = set(HUMAN_FIELDS)
    for reviewed, pristine in zip(reviewed_rows, pristine_rows, strict=True):
        decision_id = _blank(reviewed.get("decision_id"))
        for column in columns:
            if column in human:
                continue
            if (reviewed.get(column) or "") != (pristine.get(column) or ""):
                raise ScientificProposalError(
                    f"{decision_id} machine field {column} changed from pristine"
                )


def summarise_member_outcomes(
    machine_rows: Sequence[Mapping[str, str]],
    supplemental_rows: Sequence[Mapping[str, str]],
    original_evidence_rows: Sequence[Mapping[str, str]] = (),
    *,
    member_ids: Sequence[str] | None = None,
) -> dict[str, object]:
    members = list(member_ids or expected_record_ids())
    member_set = set(members)
    if len(member_set) != EXPECTED_UNIQUE_RECORDS:
        raise ScientificProposalError(
            f"expected {EXPECTED_UNIQUE_RECORDS} members, got {len(member_set)}"
        )
    effective = project_effective_evidence_for_records(
        machine_rows,
        supplemental_rows=supplemental_rows,
        original_evidence_rows=original_evidence_rows,
    )
    machine_by_id = _index_by_record_id(machine_rows)
    distribution: dict[str, int] = {"E2": 0, "E3": 0, "E4": 0, "E5": 0}
    transitions: dict[tuple[str, str], int] = {}
    extra_supplemental: list[str] = []
    missing_members: list[str] = []
    for record_id in members:
        row = effective.get(record_id)
        if row is None:
            missing_members.append(record_id)
            continue
        level = _blank(row.get("evidence_level"))
        distribution[level] = distribution.get(level, 0) + 1
        if _blank(row.get("source")) != EVIDENCE_SOURCE_SUPPLEMENTAL:
            raise ScientificProposalError(
                f"{record_id} effective evidence is {row.get('source')}, "
                "not supplemental_consistency_review"
            )
        machine_level = _blank(
            machine_by_id.get(record_id, {}).get("evidence_level_proposed")
        )
        key = (machine_level, level)
        transitions[key] = transitions.get(key, 0) + 1
    for record_id, row in effective.items():
        if record_id in member_set:
            continue
        if _blank(row.get("source")) == EVIDENCE_SOURCE_SUPPLEMENTAL:
            extra_supplemental.append(record_id)
    if missing_members:
        raise ScientificProposalError(
            "missing effective evidence for members: " + "|".join(missing_members)
        )
    if extra_supplemental:
        raise ScientificProposalError(
            "supplemental evidence leaked to non-member records: "
            + "|".join(extra_supplemental)
        )
    if distribution != EXPECTED_CORRECTED_DISTRIBUTION:
        raise ScientificProposalError(
            f"member evidence distribution drifted: {distribution}"
        )
    if transitions != EXPECTED_TRANSITIONS:
        raise ScientificProposalError(f"member transitions drifted: {transitions}")
    return {
        "n_members": len(members),
        "distribution": distribution,
        "transitions": {
            f"{src}->{dst}": count for (src, dst), count in transitions.items()
        },
        "n_extra_supplemental": 0,
    }


def target_parked_member_ids(
    target_rows: Sequence[Mapping[str, str]],
    relationship_scientific_rows: Sequence[Mapping[str, str]],
    *,
    member_ids: Sequence[str] | None = None,
) -> tuple[str, ...]:
    members = set(member_ids or expected_record_ids())
    parked_dict_ids = {
        _blank(row.get("target_dictionary_id"))
        for row in target_rows
        if _blank(row.get("manual_decision")) == "park_unresolved"
        and _blank(row.get("target_dictionary_id"))
    }
    parked: list[str] = []
    seen: set[str] = set()
    for row in relationship_scientific_rows:
        record_id = _blank(row.get("record_id"))
        if record_id not in members or record_id in seen:
            continue
        if _blank(row.get("target_dictionary_id")) in parked_dict_ids:
            seen.add(record_id)
            parked.append(record_id)
    return tuple(parked)


def dry_run_supplemental_routing(
    *,
    supplemental_rows: Sequence[Mapping[str, str]],
    routing_rows: Sequence[Mapping[str, str]],
    machine_evidence_rows: Sequence[Mapping[str, str]],
    original_evidence_rows: Sequence[Mapping[str, str]] = (),
    target_parked_record_ids: Sequence[str] = (),
) -> dict[str, object]:
    """Project routing for the 49 members. Does not write routing fields."""
    from adapters.s4_routing import routing_preview

    members = list(expected_record_ids())
    member_set = set(members)
    target_parked = set(target_parked_record_ids)
    effective = project_effective_evidence_for_records(
        machine_evidence_rows,
        supplemental_rows=supplemental_rows,
        original_evidence_rows=original_evidence_rows,
    )
    routing_by_id = _index_by_record_id(routing_rows)
    rows_out: list[dict[str, str]] = []
    pass_by_level: dict[str, list[str]] = {"E2": [], "E3": []}
    fail_e5: list[str] = []
    new_parks: list[str] = []
    independent: list[str] = []
    for record_id in members:
        current = routing_by_id.get(record_id)
        if current is None:
            raise ScientificProposalError(f"missing routing preview for {record_id}")
        overlay = effective.get(record_id)
        if overlay is None:
            raise ScientificProposalError(f"missing effective evidence for {record_id}")
        level = _blank(overlay.get("evidence_level"))
        current_route = _blank(current.get("routing_preview"))
        new_route, reason = routing_preview(
            relationship_status=_blank(current.get("relationship_status")),
            target_type=_blank(current.get("target_type_proposed")),
            evidence_level=level,
            evidence_ambiguous=False,
            leakage_proposed=_blank(current.get("leakage_exclusion_proposed")) == "true",
            no_binding=False,
        )
        if current_route in INDEPENDENT_MACHINE_ROUTES:
            effective_route = current_route
            independent.append(record_id)
        elif record_id in target_parked:
            effective_route = "target_park_unresolved"
            independent.append(record_id)
        else:
            effective_route = new_route
        if level in PASSES_EVIDENCE_THRESHOLD:
            if level in pass_by_level:
                pass_by_level[level].append(record_id)
        elif level == "E5":
            fail_e5.append(record_id)
        else:
            raise ScientificProposalError(
                f"{record_id} unexpected effective evidence {level}"
            )
        if (
            current_route == "primary_candidate"
            and effective_route == "park_evidence_e5"
            and record_id not in target_parked
        ):
            new_parks.append(record_id)
        rows_out.append(
            {
                "record_id": record_id,
                "decision_id": _blank(overlay.get("decision_id")),
                "effective_evidence_level": level,
                "current_routing": current_route,
                "recomputed_routing": new_route,
                "effective_routing": effective_route,
                "routing_reason": reason,
                "target_type": _blank(current.get("target_type_proposed")),
                "passes_evidence_threshold": (
                    "true" if level in PASSES_EVIDENCE_THRESHOLD else "false"
                ),
            }
        )
    if tuple(new_parks) != EXPECTED_NEW_EVIDENCE_PARKS:
        raise ScientificProposalError(
            f"new evidence parks drifted: {new_parks}"
        )
    if set(target_parked) != set(EXPECTED_TARGET_PARKED_INDEPENDENT):
        raise ScientificProposalError(
            f"independent target parks drifted: {sorted(target_parked)}"
        )
    if len(pass_by_level["E2"]) != EXPECTED_CORRECTED_DISTRIBUTION["E2"]:
        raise ScientificProposalError(
            f"E2 evidence-threshold pass drifted: {len(pass_by_level['E2'])}"
        )
    if len(pass_by_level["E3"]) != EXPECTED_CORRECTED_DISTRIBUTION["E3"]:
        raise ScientificProposalError(
            f"E3 evidence-threshold pass drifted: {len(pass_by_level['E3'])}"
        )
    if len(fail_e5) != EXPECTED_CORRECTED_DISTRIBUTION["E5"]:
        raise ScientificProposalError(f"E5 evidence-threshold fail drifted: {len(fail_e5)}")
    extra_members = [
        _blank(row.get("record_id"))
        for row in routing_rows
        if _blank(row.get("record_id")) in member_set
    ]
    if set(extra_members) != member_set:
        missing = sorted(member_set - set(extra_members))
        raise ScientificProposalError(f"routing coverage incomplete: {missing}")
    return {
        "n_members": len(members),
        "pass_e2": pass_by_level["E2"],
        "pass_e3": pass_by_level["E3"],
        "fail_e5": fail_e5,
        "new_evidence_parks": new_parks,
        "independent_parks": independent,
        "rows": rows_out,
    }

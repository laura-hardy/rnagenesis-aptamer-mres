"""Relationship-grain CHECKPOINT-2 transforms. Not the apply stage.

``manual_decision=override`` replaces one record's machine relationship set
with a single human-specified target. This module does not write combined
input, proposal tables, or a CHECKPOINT-2 apply CLI.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

from adapters.s4_scientific_common import ScientificProposalError
from adapters.target_extraction_common import (
    RecordExtraction,
    TargetRelationship,
    apply_relationships,
)

OVERRIDE_PROVENANCE = "checkpoint2_human_override"
PROJECTION_KIND_FIELD = "checkpoint2_projection_kind"
PARKED_PROJECTION_KIND = "park_unresolved"
OVERRIDE_PROJECTION_KIND = "override"
REJECT_PROJECTION_KIND = "reject_proposed_relationship"
CONFIRM_PROJECTION_KIND = "confirm_multi_target_expansion"
UNREVIEWED_PROJECTION_KIND = "unreviewed_machine"
RESOLVED_PROJECTION_KINDS = frozenset(
    {
        UNREVIEWED_PROJECTION_KIND,
        CONFIRM_PROJECTION_KIND,
        REJECT_PROJECTION_KIND,
        OVERRIDE_PROJECTION_KIND,
    }
)


def _blank(value: str | None) -> str:
    return (value or "").strip()


def _copy_row(row: Mapping[str, str], *, kind: str) -> dict[str, str]:
    copied = dict(row)
    copied[PROJECTION_KIND_FIELD] = kind
    return copied


def _group_machine_rows(
    machine_rows: Sequence[Mapping[str, str]],
) -> tuple[dict[str, list[Mapping[str, str]]], list[str]]:
    by_record: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    order: list[str] = []
    for row in machine_rows:
        record_id = row.get("record_id", "")
        if record_id not in by_record:
            order.append(record_id)
            by_record[record_id] = []
        by_record[record_id].append(row)
    for record_id in order:
        by_record[record_id].sort(
            key=lambda item: int((item.get("relationship_index") or "0") or 0)
        )
    return by_record, order


@dataclass(frozen=True)
class RelationshipProjection:
    """Reviewed relationship sets projected into resolved vs parked rows.

    ``effective_resolved`` contains relationships that survive as corpus
    target relationships. ``parked`` retains parked-relationship provenance
    for audit and is not an effective resolved set. Machine input is not
    mutated.
    """

    effective_resolved: tuple[dict[str, str], ...]
    parked: tuple[dict[str, str], ...]
    dropped_by_reject: tuple[dict[str, str], ...]
    dropped_by_override: tuple[dict[str, str], ...]


def project_relationship_reviews(
    machine_rows: Sequence[Mapping[str, str]],
    review_rows: Sequence[Mapping[str, str]],
) -> RelationshipProjection:
    """Project relationship reviews without writing proposal tables.

    ``park_unresolved`` contributes parked provenance only.
    ``reject_proposed_relationship`` keeps the index-1 machine row.
    ``override`` replaces the machine set via ``apply_relationship_override``.
    Unreviewed records keep their machine relationships.
    """
    by_record, order = _group_machine_rows(machine_rows)
    review_by_record: dict[str, Mapping[str, str]] = {}
    for review in review_rows:
        decision = _blank(review.get("manual_decision"))
        if not decision:
            continue
        record_id = review.get("record_id", "")
        if record_id in review_by_record:
            raise ScientificProposalError(
                f"duplicate relationship review for {record_id}"
            )
        review_by_record[record_id] = review

    effective: list[dict[str, str]] = []
    parked: list[dict[str, str]] = []
    dropped_by_reject: list[dict[str, str]] = []
    dropped_by_override: list[dict[str, str]] = []

    for record_id in order:
        group = by_record[record_id]
        review = review_by_record.get(record_id)
        if review is None:
            effective.extend(
                _copy_row(row, kind=UNREVIEWED_PROJECTION_KIND) for row in group
            )
            continue
        decision = _blank(review.get("manual_decision"))
        if decision == "park_unresolved":
            parked.extend(_copy_row(row, kind=PARKED_PROJECTION_KIND) for row in group)
            continue
        if decision == "override":
            replacement = apply_relationship_override(group, review)
            dropped_by_override.extend(
                _copy_row(row, kind=OVERRIDE_PROJECTION_KIND) for row in group
            )
            for row in replacement:
                copied = dict(row)
                copied[PROJECTION_KIND_FIELD] = OVERRIDE_PROJECTION_KIND
                copied["target_dictionary_id"] = ""
                copied["_override_decision_id"] = _blank(review.get("decision_id"))
                copied["_override_name"] = _blank(review.get("manual_target_name"))
                copied["_override_type"] = _blank(review.get("manual_target_type"))
                effective.append(copied)
            continue
        if decision == "confirm_multi_target_expansion":
            effective.extend(
                _copy_row(row, kind=CONFIRM_PROJECTION_KIND) for row in group
            )
            continue
        if decision == "reject_proposed_relationship":
            if not group:
                raise ScientificProposalError(
                    f"reject_proposed_relationship requires a machine set for {record_id}"
                )
            kept = _copy_row(group[0], kind=REJECT_PROJECTION_KIND)
            effective.append(kept)
            dropped_by_reject.extend(
                _copy_row(row, kind=REJECT_PROJECTION_KIND) for row in group[1:]
            )
            continue
        raise ScientificProposalError(
            f"project_relationship_reviews cannot interpret {decision!r}"
        )

    return RelationshipProjection(
        effective_resolved=tuple(effective),
        parked=tuple(parked),
        dropped_by_reject=tuple(dropped_by_reject),
        dropped_by_override=tuple(dropped_by_override),
    )


def apply_relationship_override(
    machine_rows: Sequence[Mapping[str, str]],
    review_row: Mapping[str, str],
) -> list[dict[str, str]]:
    """Replace one record's machine relationships with one manual target.

    Returns a new one-row list. Does not mutate ``machine_rows``.
    """
    decision = _blank(review_row.get("manual_decision"))
    if decision != "override":
        raise ScientificProposalError(
            f"apply_relationship_override requires override, got {decision!r}"
        )
    name = _blank(review_row.get("manual_target_name"))
    target_type = _blank(review_row.get("manual_target_type"))
    if not name:
        raise ScientificProposalError("override requires manual_target_name")
    if not target_type:
        raise ScientificProposalError("override requires manual_target_type")
    copied = [dict(row) for row in machine_rows]
    if not copied:
        raise ScientificProposalError("override requires a machine relationship set")
    record_ids = {row.get("record_id", "") for row in copied}
    if len(record_ids) != 1:
        raise ScientificProposalError(
            "override applies to exactly one record relationship set"
        )
    record_id = copied[0].get("record_id", "")
    source_db = copied[0].get("source_db", "")
    extraction = RecordExtraction(
        record_id=record_id,
        source_db=source_db,
        native_id="",
        existing_target_name_raw="",
    )
    replacement = TargetRelationship(
        record_id=record_id,
        source_db=source_db,
        raw_target=name,
        target_provenance_source=OVERRIDE_PROVENANCE,
        target_provenance_locator=_blank(review_row.get("decision_id")),
        relationship_confidence="high",
        requires_checkpoint2=False,
    )
    apply_relationships(
        extraction,
        [replacement],
        status="resolved_single",
        method="checkpoint2_relationship_override",
        confidence="high",
        expansion=False,
        checkpoint2=False,
        effective_override=name,
        notes="checkpoint2_manual_decision=override",
    )
    surviving = extraction.relationships[0]
    numbered = surviving.as_row()
    out = {key: "" for key in copied[0]}
    for key, value in numbered.items():
        if key in out:
            out[key] = value
    out["record_id"] = record_id
    out["source_db"] = source_db
    out["relationship_index"] = str(surviving.relationship_index)
    out["raw_target"] = name
    if "target_type_proposed" in out:
        out["target_type_proposed"] = target_type
    if "uniprot_proposed" in out:
        out["uniprot_proposed"] = _blank(review_row.get("manual_uniprot"))
    if "target_family_proposed" in out:
        out["target_family_proposed"] = _blank(review_row.get("manual_target_family"))
    if "target_pfam_proposed" in out:
        out["target_pfam_proposed"] = _blank(review_row.get("manual_pfam_interpro"))
    if "record_expansion_proposed" in out:
        out["record_expansion_proposed"] = "false"
    if "relationship_status" in out:
        out["relationship_status"] = "resolved_single"
    if "requires_checkpoint2" in out:
        out["requires_checkpoint2"] = "false"
    if "notes" in out:
        out["notes"] = "checkpoint2_manual_decision=override"
    return [out]


def apply_relationship_overrides(
    machine_rows: Sequence[Mapping[str, str]],
    review_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Apply override reviews; copy non-overridden records unchanged.

    Does not mutate ``machine_rows``. Other manual_decision values are
    ignored here; this is not a full CHECKPOINT-2 apply stage.
    """
    by_record: dict[str, list[Mapping[str, str]]] = {}
    order: list[str] = []
    for row in machine_rows:
        record_id = row.get("record_id", "")
        if record_id not in by_record:
            order.append(record_id)
            by_record[record_id] = []
        by_record[record_id].append(row)
    review_by_record: dict[str, Mapping[str, str]] = {}
    for review in review_rows:
        if _blank(review.get("manual_decision")) != "override":
            continue
        record_id = review.get("record_id", "")
        if record_id in review_by_record:
            raise ScientificProposalError(
                f"duplicate override review for {record_id}"
            )
        review_by_record[record_id] = review
    out: list[dict[str, str]] = []
    for record_id in order:
        group = by_record[record_id]
        review = review_by_record.get(record_id)
        if review is None:
            out.extend(dict(row) for row in group)
            continue
        out.extend(apply_relationship_override(group, review))
    return out

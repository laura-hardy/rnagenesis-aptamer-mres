"""Target-dictionary CHECKPOINT-2 transforms. Not the apply stage.

Relationship review precedes effective dictionary construction. Machine
candidates with no surviving resolved relationship are inactive, not
unresolved biological targets. Relationship overrides reuse an exact
dictionary identity or create a deterministic human-derived identity.
This module does not write combined input, proposal tables, review
CSVs, or a CHECKPOINT-2 apply CLI.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from typing import Mapping, Sequence

from adapters.checkpoint2_relationship import (
    OVERRIDE_PROJECTION_KIND,
    RelationshipProjection,
    project_relationship_reviews,
)
from adapters.s4_scientific_common import (
    INACTIVE_TARGET_DECISION,
    ScientificProposalError,
    TARGET_TYPE_VOCAB,
    assert_human_fields_blank,
    blank_human_fields,
    fill_row,
    split_pipe,
)

INACTIVE_REASON_SUPERSEDED = "superseded_by_relationship_review"
INACTIVE_REASON_PARKED_ONLY = "parked_relationship_only"
HUMAN_DERIVED_ORIGIN = "human_derived_relationship_override"
EXACT_EXISTING_ORIGIN = "exact_existing"
HUMAN_DERIVED_ID_NAMESPACE = "checkpoint2_relationship_override"
HUMAN_DERIVED_CANONICALISATION = "checkpoint2_relationship_override"
HUMAN_DERIVED_REVIEW_STATUS = "human_derived_relationship_override"


def _blank(value: str | None) -> str:
    return (value or "").strip()


def _exact_name(value: str | None) -> str:
    return unicodedata.normalize("NFC", value or "").strip()


def proposed_family_for_type(target_type: str) -> str:
    """Policy family proposal only; not an applied canonical family."""
    kind = _blank(target_type)
    if kind in {"protein", "peptide", "unknown", ""}:
        return "unknown"
    if kind in TARGET_TYPE_VOCAB:
        return "other"
    return "unknown"


def human_derived_target_dictionary_id(name: str, target_type: str) -> str:
    """Stable ID from the exact override name and type. No fuzzy keying."""
    payload = (
        f"{HUMAN_DERIVED_ID_NAMESPACE}\n{_exact_name(name)}\t{_blank(target_type)}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"TDH{digest}"


def human_derived_target_decision_id(name: str, target_type: str) -> str:
    digest = human_derived_target_dictionary_id(name, target_type).removeprefix("TDH")
    return f"C2TH{digest}"


def exact_dictionary_matches(
    name: str,
    dictionary_rows: Sequence[Mapping[str, str]],
    target_review_rows: Sequence[Mapping[str, str]] | None = None,
) -> list[str]:
    """Exact string matches only. No primary-key or alias merge."""
    needle = _exact_name(name)
    if not needle:
        return []
    ids: list[str] = []
    for row in dictionary_rows:
        did = _blank(row.get("target_dictionary_id"))
        if not did:
            continue
        if _exact_name(row.get("canonical_target_name_proposal")) == needle:
            ids.append(did)
        for raw in split_pipe(row.get("raw_target", "")):
            if _exact_name(raw) == needle:
                ids.append(did)
    for row in target_review_rows or ():
        did = _blank(row.get("target_dictionary_id"))
        if did and _exact_name(row.get("manual_target_name")) == needle:
            ids.append(did)
    return list(dict.fromkeys(ids))


@dataclass(frozen=True)
class OverrideDictionaryResolution:
    target_dictionary_id: str
    origin: str
    name: str
    target_type: str
    family_proposal: str
    existing_dictionary_id_reused: bool
    proposed_dictionary_row: dict[str, str]
    proposed_target_review_row: dict[str, str] | None


def resolve_override_dictionary_identity(
    *,
    manual_target_name: str,
    manual_target_type: str,
    relationship_decision_ids: Sequence[str],
    dictionary_rows: Sequence[Mapping[str, str]],
    target_review_rows: Sequence[Mapping[str, str]] | None = None,
) -> OverrideDictionaryResolution:
    """Reuse an exact dictionary identity or create a human-derived one.

    Ambiguous exact matches fail closed. Alias/primary-key neighbours are
    never reused.
    """
    name = _exact_name(manual_target_name)
    target_type = _blank(manual_target_type)
    if not name:
        raise ScientificProposalError("override dictionary identity requires a name")
    if not target_type:
        raise ScientificProposalError("override dictionary identity requires a type")
    matches = exact_dictionary_matches(
        name, dictionary_rows, target_review_rows
    )
    provenance = "|".join(
        dict.fromkeys(_blank(item) for item in relationship_decision_ids if _blank(item))
    )
    family = proposed_family_for_type(target_type)
    if len(matches) > 1:
        raise ScientificProposalError(
            f"ambiguous exact dictionary match for {name!r}: {'|'.join(matches)}"
        )
    if len(matches) == 1:
        did = matches[0]
        existing = next(
            (
                dict(row)
                for row in dictionary_rows
                if _blank(row.get("target_dictionary_id")) == did
            ),
            {
                "target_dictionary_id": did,
                "canonical_target_name_proposal": name,
                "raw_target": name,
            },
        )
        return OverrideDictionaryResolution(
            target_dictionary_id=did,
            origin=EXACT_EXISTING_ORIGIN,
            name=name,
            target_type=target_type,
            family_proposal=_blank(existing.get("target_family_proposed")) or family,
            existing_dictionary_id_reused=True,
            proposed_dictionary_row=existing,
            proposed_target_review_row=None,
        )

    did = human_derived_target_dictionary_id(name, target_type)
    dictionary_row = {
        "target_dictionary_id": did,
        "raw_target": name,
        "canonical_target_name_proposal": name,
        "canonicalisation_method": HUMAN_DERIVED_CANONICALISATION,
        "target_type_proposed": target_type,
        "target_family_proposed": family,
        "review_status": HUMAN_DERIVED_REVIEW_STATUS,
        "resolution_provenance": f"{HUMAN_DERIVED_ID_NAMESPACE}:{provenance}",
        "requires_checkpoint2": "true",
        "machine_recommendation": "review_relationship_override_identity",
        "scientific_ambiguity_reason": HUMAN_DERIVED_ORIGIN,
        "proposal_confidence": "high",
        "n_records": "",
        "n_relationships": "",
        "source_keys": "",
        "uniprot_proposed": "",
        "uniprot_candidates": "",
        "target_pfam_proposed": "",
        "target_interpro_proposed": "",
    }
    review_row = {
        "decision_id": human_derived_target_decision_id(name, target_type),
        "target_dictionary_id": did,
        "raw_target": name,
        "canonical_target_name_proposal": name,
        "target_type_proposed": target_type,
        "target_family_proposed": family,
        "proposal_confidence": "high",
        "resolution_provenance": f"{HUMAN_DERIVED_ID_NAMESPACE}:{provenance}",
        "scientific_ambiguity_reason": HUMAN_DERIVED_ORIGIN,
        "machine_recommendation": "review_relationship_override_identity",
        **blank_human_fields(),
    }
    return OverrideDictionaryResolution(
        target_dictionary_id=did,
        origin=HUMAN_DERIVED_ORIGIN,
        name=name,
        target_type=target_type,
        family_proposal=family,
        existing_dictionary_id_reused=False,
        proposed_dictionary_row=dictionary_row,
        proposed_target_review_row=review_row,
    )


def _index_target_review_ids(
    rows: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    by_decision: dict[str, str] = {}
    by_dictionary: dict[str, str] = {}
    for row in rows:
        decision_id = _blank(row.get("decision_id"))
        dictionary_id = _blank(row.get("target_dictionary_id"))
        if decision_id:
            if decision_id in by_decision:
                raise ScientificProposalError(
                    f"duplicate target decision id {decision_id}"
                )
            by_decision[decision_id] = dictionary_id
        if dictionary_id:
            if dictionary_id in by_dictionary:
                raise ScientificProposalError(
                    f"duplicate target dictionary id {dictionary_id}"
                )
            by_dictionary[dictionary_id] = decision_id
    return by_decision, by_dictionary


def materialise_human_derived_target_review_rows(
    target_review_rows: Sequence[Mapping[str, str]],
    override_resolutions: Sequence[OverrideDictionaryResolution],
    *,
    columns: Sequence[str],
) -> tuple[list[dict[str, str]], tuple[dict[str, str], ...]]:
    """Append blank review rows for new human-derived identities.

    Idempotent: existing rows, including recorded human decisions, are
    retained field-wise. Exact dictionary reuse does not create a row.
    Duplicate decision or dictionary IDs fail closed.
    """
    if not columns:
        raise ScientificProposalError("human-derived materialisation requires columns")
    out = [fill_row(columns, dict(row)) for row in target_review_rows]
    by_decision, by_dictionary = _index_target_review_ids(out)
    added: list[dict[str, str]] = []
    for resolution in override_resolutions:
        if resolution.existing_dictionary_id_reused:
            continue
        proposed = resolution.proposed_target_review_row
        if proposed is None:
            continue
        decision_id = _blank(proposed.get("decision_id"))
        dictionary_id = _blank(proposed.get("target_dictionary_id"))
        if not decision_id or not dictionary_id:
            raise ScientificProposalError(
                "human-derived review row requires decision and dictionary ids"
            )
        if decision_id in by_decision:
            existing_dictionary = by_decision[decision_id]
            if existing_dictionary != dictionary_id:
                raise ScientificProposalError(
                    f"decision {decision_id} already maps to {existing_dictionary}"
                )
            continue
        if dictionary_id in by_dictionary:
            existing_decision = by_dictionary[dictionary_id]
            if existing_decision != decision_id:
                raise ScientificProposalError(
                    f"dictionary {dictionary_id} already maps to {existing_decision}"
                )
            continue
        row = fill_row(columns, proposed)
        assert_human_fields_blank(row, label="human-derived target review")
        if (
            row["decision_id"] != decision_id
            or row["target_dictionary_id"] != dictionary_id
        ):
            raise ScientificProposalError(
                "human-derived review row lost its deterministic identifiers"
            )
        out.append(row)
        added.append(row)
        by_decision[decision_id] = dictionary_id
        by_dictionary[dictionary_id] = decision_id
    return out, tuple(added)


def attach_override_dictionary_identities(
    projection: RelationshipProjection,
    dictionary_rows: Sequence[Mapping[str, str]],
    target_review_rows: Sequence[Mapping[str, str]] | None = None,
) -> tuple[RelationshipProjection, tuple[OverrideDictionaryResolution, ...]]:
    """Map override rows to exact or human-derived dictionary IDs.

    Does not mutate ``projection`` rows in place. Machine proposal tables
    are not inputs that get written.
    """
    resolutions: dict[tuple[str, str], OverrideDictionaryResolution] = {}
    remapped: list[dict[str, str]] = []
    for row in projection.effective_resolved:
        copied = dict(row)
        if copied.get("checkpoint2_projection_kind") != OVERRIDE_PROJECTION_KIND:
            remapped.append(copied)
            continue
        key = (_exact_name(copied.get("_override_name")), _blank(copied.get("_override_type")))
        resolution = resolutions.get(key)
        if resolution is None:
            decision_ids = [_blank(copied.get("_override_decision_id"))]
            for other in projection.effective_resolved:
                if (
                    other.get("checkpoint2_projection_kind") == OVERRIDE_PROJECTION_KIND
                    and _exact_name(other.get("_override_name")) == key[0]
                    and _blank(other.get("_override_type")) == key[1]
                ):
                    decision_ids.append(_blank(other.get("_override_decision_id")))
            resolution = resolve_override_dictionary_identity(
                manual_target_name=key[0],
                manual_target_type=key[1],
                relationship_decision_ids=decision_ids,
                dictionary_rows=dictionary_rows,
                target_review_rows=target_review_rows,
            )
            resolutions[key] = resolution
        copied["target_dictionary_id"] = resolution.target_dictionary_id
        copied["_dictionary_origin"] = resolution.origin
        remapped.append(copied)
    attached = RelationshipProjection(
        effective_resolved=tuple(remapped),
        parked=tuple(dict(row) for row in projection.parked),
        dropped_by_reject=tuple(dict(row) for row in projection.dropped_by_reject),
        dropped_by_override=tuple(dict(row) for row in projection.dropped_by_override),
    )
    return attached, tuple(resolutions.values())


def project_effective_target_relationships(
    machine_rows: Sequence[Mapping[str, str]],
    relationship_review_rows: Sequence[Mapping[str, str]],
    dictionary_rows: Sequence[Mapping[str, str]],
    target_review_rows: Sequence[Mapping[str, str]] | None = None,
) -> tuple[RelationshipProjection, tuple[OverrideDictionaryResolution, ...]]:
    """Relationship projection plus exact/human-derived override mapping."""
    projection = project_relationship_reviews(machine_rows, relationship_review_rows)
    return attach_override_dictionary_identities(
        projection, dictionary_rows, target_review_rows
    )


def _ids_from(rows: Sequence[Mapping[str, str]]) -> set[str]:
    return {
        _blank(row.get("target_dictionary_id"))
        for row in rows
        if _blank(row.get("target_dictionary_id"))
    }


def inactivity_reason_for_dictionary_id(
    target_dictionary_id: str,
    projection: RelationshipProjection,
) -> str | None:
    """Return the inactive reason, or None if the identity is still active."""
    did = _blank(target_dictionary_id)
    if not did:
        raise ScientificProposalError("inactivity classification requires a dictionary id")
    effective_ids = _ids_from(projection.effective_resolved)
    if did in effective_ids:
        return None
    parked_ids = _ids_from(projection.parked)
    dropped_ids = _ids_from(projection.dropped_by_reject) | _ids_from(
        projection.dropped_by_override
    )
    if did in parked_ids and did not in dropped_ids:
        return INACTIVE_REASON_PARKED_ONLY
    return INACTIVE_REASON_SUPERSEDED


def validate_inactive_target_decision(
    review_row: Mapping[str, str],
    projection: RelationshipProjection,
) -> str:
    """Fail if an inactive action is applied to an identity that is still active."""
    decision = _blank(review_row.get("manual_decision"))
    if decision != INACTIVE_TARGET_DECISION:
        raise ScientificProposalError(
            f"inactive validation requires {INACTIVE_TARGET_DECISION}, got {decision!r}"
        )
    did = _blank(review_row.get("target_dictionary_id"))
    if not did:
        raise ScientificProposalError(
            f"{INACTIVE_TARGET_DECISION} requires target_dictionary_id"
        )
    reason = inactivity_reason_for_dictionary_id(did, projection)
    if reason is None:
        raise ScientificProposalError(
            f"{INACTIVE_TARGET_DECISION} is invalid for active dictionary {did}"
        )
    return reason


@dataclass(frozen=True)
class EffectiveTargetDictionary:
    """Resolved dictionary entries after target review. Not a write stage."""

    resolved_entries: tuple[dict[str, str], ...]
    inactive_entries: tuple[dict[str, str], ...]
    parked_only_provenance: tuple[dict[str, str], ...]
    human_derived_pending_review: tuple[OverrideDictionaryResolution, ...]


def _dictionary_by_id(
    dictionary_rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    return {
        _blank(row.get("target_dictionary_id")): dict(row)
        for row in dictionary_rows
        if _blank(row.get("target_dictionary_id"))
    }


def build_effective_target_dictionary(
    dictionary_rows: Sequence[Mapping[str, str]],
    target_review_rows: Sequence[Mapping[str, str]],
    projection: RelationshipProjection,
    override_resolutions: Sequence[OverrideDictionaryResolution] = (),
) -> EffectiveTargetDictionary:
    """Build the reviewed effective dictionary without applying it.

    ``approve_proposal`` / ``override`` enter the resolved set.
    ``park_unresolved`` stays out of the resolved set as a scientific park.
    ``exclude_no_active_relationship`` is excluded, with superseded vs
    parked-only provenance distinguished. Human-derived override
    identities remain pending until a target-level decision exists.
    Human-derived identities approved at target grain enter the resolved
    set from the review row / override proposal without requiring a
    machine dictionary write.
    """
    by_id = _dictionary_by_id(dictionary_rows)
    for item in override_resolutions:
        if item.target_dictionary_id not in by_id:
            by_id[item.target_dictionary_id] = dict(item.proposed_dictionary_row)
    resolved: list[dict[str, str]] = []
    inactive: list[dict[str, str]] = []
    parked_only: list[dict[str, str]] = []
    reviewed_ids: set[str] = set()

    for review in target_review_rows:
        did = _blank(review.get("target_dictionary_id"))
        decision = _blank(review.get("manual_decision"))
        if not did or not decision:
            continue
        reviewed_ids.add(did)
        source = dict(by_id.get(did, {"target_dictionary_id": did}))
        for field in (
            "canonical_target_name_proposal",
            "target_type_proposed",
            "target_family_proposed",
            "raw_target",
            "resolution_provenance",
        ):
            if _blank(source.get(field)):
                value = _blank(review.get(field))
                if value:
                    source[field] = value
        source["_target_decision_id"] = _blank(review.get("decision_id"))
        source["_target_decision"] = decision
        if decision == INACTIVE_TARGET_DECISION:
            reason = validate_inactive_target_decision(review, projection)
            source["_inactivity_reason"] = reason
            inactive.append(source)
            if reason == INACTIVE_REASON_PARKED_ONLY:
                for row in projection.parked:
                    if _blank(row.get("target_dictionary_id")) == did:
                        parked_only.append(
                            {
                                "target_dictionary_id": did,
                                "record_id": row.get("record_id", ""),
                                "raw_target": row.get("raw_target", ""),
                                "inactivity_reason": reason,
                            }
                        )
            continue
        if decision == "park_unresolved":
            source["_inactivity_reason"] = "park_unresolved"
            continue
        if decision in {"approve_proposal", "override"}:
            if decision == "override":
                if _blank(review.get("manual_target_name")):
                    source["canonical_target_name_proposal"] = _blank(
                        review.get("manual_target_name")
                    )
                if _blank(review.get("manual_target_type")):
                    source["target_type_proposed"] = _blank(
                        review.get("manual_target_type")
                    )
                if _blank(review.get("manual_target_family")):
                    source["target_family_proposed"] = _blank(
                        review.get("manual_target_family")
                    )
            resolved.append(source)
            continue

    pending = tuple(
        item
        for item in override_resolutions
        if not item.existing_dictionary_id_reused
        and item.target_dictionary_id not in reviewed_ids
    )
    return EffectiveTargetDictionary(
        resolved_entries=tuple(resolved),
        inactive_entries=tuple(inactive),
        parked_only_provenance=tuple(parked_only),
        human_derived_pending_review=pending,
    )


def classify_target_review_inactivity(
    target_review_rows: Sequence[Mapping[str, str]],
    projection: RelationshipProjection,
) -> dict[str, dict[str, str]]:
    """Dry-run inactivity classification for machine dictionary candidates."""
    report: dict[str, dict[str, str]] = {}
    for row in target_review_rows:
        did = _blank(row.get("target_dictionary_id"))
        if not did:
            continue
        reason = inactivity_reason_for_dictionary_id(did, projection)
        report[did] = {
            "decision_id": _blank(row.get("decision_id")),
            "target_dictionary_id": did,
            "raw_target": row.get("raw_target", ""),
            "canonical_target_name_proposal": row.get(
                "canonical_target_name_proposal", ""
            ),
            "current_manual_decision": _blank(row.get("manual_decision")),
            "inactive_action_valid": "true" if reason else "false",
            "inactivity_reason": reason or "",
        }
    return report

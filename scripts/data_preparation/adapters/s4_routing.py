"""S4 routing vocabulary and deterministic precedence.

Used for machine routing preview and for CHECKPOINT-2 application.
Does not invent new route tokens; parked relationship/target states reuse
``hold_target_unresolved`` with distinct reasons.
"""

from __future__ import annotations

from typing import Mapping

from adapters.s4_scientific_common import ROUTING_VOCAB

NON_PROTEIN = frozenset(
    {
        "peptide",
        "small_molecule",
        "ion",
        "nucleic_acid",
        "cell",
        "organism",
        "other",
    }
)


def routing_preview(
    *,
    relationship_status: str,
    target_type: str,
    evidence_level: str,
    evidence_ambiguous: bool,
    leakage_proposed: bool,
    no_binding: bool,
    relationship_parked: bool = False,
    target_parked: bool = False,
) -> tuple[str, str]:
    """Return (routing_preview, reason) using documented precedence.

    Precedence: leakage → relationship park → unresolved/ambiguous
    relationship → target scientific park → unknown type on an unresolved
    relationship → no-binding reject → evidence hold → non-protein park →
    E5 park → primary candidate.

    ``relationship_parked`` / ``target_parked`` use existing
    ``hold_target_unresolved`` vocabulary with distinct reasons. No-binding
    remains expressible as ``reject_no_binding_evidence`` even when target
    metadata is otherwise usable.
    """
    if leakage_proposed:
        return "leakage_exclusion_proposed", "leakage_match"
    if relationship_parked:
        return "hold_target_unresolved", "relationship_park_unresolved"
    if relationship_status in {"unresolved", "ambiguous"} or not (target_type or "").strip():
        if relationship_status in {"unresolved", "ambiguous"}:
            return "hold_target_unresolved", f"relationship_status={relationship_status}"
    if target_parked:
        return "hold_target_unresolved", "target_park_unresolved"
    if target_type in {"unknown", ""} and relationship_status not in {"resolved_single", "resolved_multiple"}:
        return "hold_target_unresolved", "target_type_unknown"
    if no_binding:
        return "reject_no_binding_evidence", "no_defensible_binding_evidence"
    if evidence_ambiguous:
        return "hold_evidence_ambiguous", "e4_e5_threshold_ambiguous"
    if target_type in NON_PROTEIN:
        return "park_non_protein", f"target_type={target_type}"
    if evidence_level == "E5":
        return "park_evidence_e5", "evidence_level=E5"
    if evidence_level in {"E1", "E2", "E3", "E4"} and target_type == "protein":
        return "primary_candidate", f"protein_{evidence_level}"
    if target_type == "protein" and not evidence_level:
        return "hold_evidence_ambiguous", "protein_without_evidence_level"
    if target_type == "unknown":
        return "hold_target_unresolved", "target_type_unknown"
    return "hold_evidence_ambiguous", "unclassified_routing_state"


def assert_routing_vocab(value: str) -> None:
    if value not in ROUTING_VOCAB:
        raise ValueError(f"invalid routing_preview {value!r}")

"""CHECKPOINT-2 application. Consumes reviewed projection helpers.

Does not reimplement target, evidence, affinity, leakage, or routing science.
Does not collapse duplicate ``(sequence, target)`` rows, cluster, balance,
or assign FT/REF/EVAL. Exact scientific deduplication is S5A. Clustering,
balancing, and splits are later milestones. NCBI/ENA duplicate resolution
is not an S5A operation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from adapters.checkpoint2_affinity import (
    AFFINITY_REVIEW_STATUS_EXACT,
    AFFINITY_REVIEW_STATUS_EXCLUDE,
    AFFINITY_REVIEW_STATUS_PARK,
    AFFINITY_REVIEW_STATUS_RAW,
    AFFINITY_REVIEW_STATUS_UNREVIEWED,
    flag_evidence_affinity_inconsistency,
    project_affinity_reviews,
)
from adapters.checkpoint2_dictionary import (
    HUMAN_DERIVED_ORIGIN,
    build_effective_target_dictionary,
    project_effective_target_relationships,
)
from adapters.checkpoint2_evidence import (
    collect_consistency_flag_record_ids,
    project_effective_evidence_for_records,
)
from adapters.checkpoint2_relationship import RelationshipProjection
from adapters.s4_leakage_proposal import propose_leakage
from adapters.s4_routing import assert_routing_vocab, routing_preview
from adapters.s4_scientific_common import (
    EVIDENCE_SCORE_BY_LEVEL,
    EVIDENCE_TYPE_BY_LEVEL,
    ScientificProposalError,
    bool_token,
    fill_row,
    join_unique,
)
from common.eligibility import SequenceLeakageIndex

CAMP_TARGET_DICTIONARY_ID = "TDHc92005d63414"
CAMP_CANONICAL_NAME = "3',5'-cyclic adenosine monophosphate (cAMP)"
CAMP_TARGET_TYPE = "small_molecule"
CAMP_TARGET_FAMILY = "other"

# Historical S4 boundary tokens. S4 must not mark these as run.
# S5A implements exact_cross_source_deduplication / merge_duplicate_sequence_target
# only. ncbi_ena_duplicate_resolution is not required on the true S5 input
# (NCBI rows = 0; exact/near overlap with ENA = 0) and is not implemented.
S5_OPERATIONS = (
    "exact_cross_source_deduplication",
    "merge_duplicate_sequence_target",
    "ncbi_ena_duplicate_resolution",
    "mmseqs_cdhit_clustering",
    "sequence_clustering",
    "target_balancing_or_capping",
    "ft_ref_eval_assignment",
    "train_validation_test_split",
)

RECORD_OUTCOME_PRECEDENCE: tuple[str, ...] = (
    "relationship_parked",
    "unresolved_no_relationship",
    "target_parked",
    "leakage_excluded",
    "reject_no_binding_evidence",
    "hold_evidence_ambiguous",
    "park_non_protein",
    "park_evidence_e5",
    "hold_target_unresolved",
    "primary_candidate",
)

REVIEWED_RELATIONSHIP_COLUMNS: tuple[str, ...] = (
    "reviewed_relationship_id",
    "record_id",
    "source_db",
    "native_id",
    "relationship_index",
    "relationship_projection_kind",
    "relationship_decision_id",
    "raw_target",
    "target_provenance_source",
    "target_provenance_locator",
    "target_dictionary_id",
    "canonical_target_name",
    "target_type",
    "target_family",
    "target_uniprot",
    "target_pfam",
    "target_interpro",
    "target_region_or_fragment",
    "target_decision_id",
    "target_decision",
    "evidence_level",
    "evidence_score",
    "evidence_type",
    "evidence_source",
    "evidence_decision_id",
    "evidence_provenance",
    "evidence_rule",
    "affinity_value_raw",
    "affinity_unit_raw",
    "affinity_review_status",
    "affinity_type",
    "affinity_value_molar",
    "affinity_unit_normalized",
    "affinity_qualifier",
    "affinity_range_status",
    "affinity_bound_molar",
    "non_affinity_reason",
    "affinity_transform_rule",
    "affinity_decision_id",
    "affinity_provenance",
    "canonical_affinity_value",
    "canonical_affinity_unit",
    "canonical_affinity_type",
    "sequence_full",
    "sequence_core",
    "molecule_type",
    "chemistry",
    "publication",
    "doi",
    "pubmed_id",
    "accession",
    "leakage_exclusion",
    "leakage_sequence_match_kind",
    "leakage_identity",
    "leakage_target_alias_match",
    "leakage_reason",
    "s4_route",
    "s4_route_reason",
)

REVIEWED_DICTIONARY_COLUMNS: tuple[str, ...] = (
    "target_dictionary_id",
    "canonical_target_name",
    "raw_target",
    "target_type",
    "target_family",
    "target_uniprot",
    "target_pfam",
    "target_interpro",
    "target_decision_id",
    "target_decision",
    "dictionary_origin",
    "reviewed_resolved",
    "n_active_relationships",
    "resolution_provenance",
)

RECORD_MAP_COLUMNS: tuple[str, ...] = (
    "record_id",
    "source_db",
    "n_effective_relationships",
    "n_target_parked_relationships",
    "relationship_parked",
    "unresolved_no_relationship",
    "reviewed_relationship_ids",
    "target_dictionary_ids",
    "s4_record_outcome",
    "s4_record_route",
    "s4_record_route_reason",
)

PARKED_AUDIT_COLUMNS: tuple[str, ...] = (
    "record_id",
    "source_db",
    "audit_class",
    "reason",
    "reviewed_relationship_id",
    "target_dictionary_id",
    "raw_target",
    "canonical_target_name",
    "evidence_level",
    "s4_route",
    "s4_route_reason",
)

UNSAFE_CANONICAL_AFFINITY_REASONS = frozenset(
    {
        "lod",
        "assay_caption",
        "mentioned_foreign_kd",
        "binding_percentage",
        "rate",
        "missing_value",
        "no_binding",
        "placeholder",
    }
)


def _blank(value: str | None) -> str:
    return (value or "").strip()


def _index_first(rows: Sequence[Mapping[str, str]], key: str) -> dict[str, Mapping[str, str]]:
    out: dict[str, Mapping[str, str]] = {}
    for row in rows:
        item = _blank(row.get(key))
        if item and item not in out:
            out[item] = row
    return out


def reviewed_relationship_id(record_id: str, relationship_index: str) -> str:
    return f"{record_id}|{relationship_index or '1'}"


def project_unreviewed_affinity(machine_row: Mapping[str, str]) -> dict[str, str]:
    """Carry deterministic machine affinity. Never invent a scalar."""
    raw = _blank(machine_row.get("affinity_value_raw"))
    unit = _blank(machine_row.get("affinity_unit_raw"))
    molar = _blank(machine_row.get("affinity_value_molar_proposed"))
    parse_status = _blank(machine_row.get("affinity_parse_status"))
    aff_type = _blank(machine_row.get("affinity_type_proposed"))
    record_id = _blank(machine_row.get("record_id"))
    base = {
        "record_id": record_id,
        "relationship_index": _blank(machine_row.get("relationship_index")),
        "source_db": _blank(machine_row.get("source_db")),
        "review_decision_id": "",
        "affinity_review_status": AFFINITY_REVIEW_STATUS_UNREVIEWED,
        "affinity_type": aff_type,
        "affinity_value_raw": raw,
        "affinity_value_molar": "",
        "affinity_unit_normalized": "",
        "affinity_qualifier": "",
        "affinity_range_status": "",
        "affinity_bound_molar": "",
        "non_affinity_reason": "",
        "transform_rule": "",
        "provenance": "machine_affinity",
        "canonical_affinity_value": "",
        "canonical_affinity_unit": "",
        "canonical_affinity_type": "",
        "relationship_active": "true",
        "machine_evidence_level": _blank(machine_row.get("evidence_level_proposed")),
        "evidence_affinity_inconsistency": "",
    }
    if parse_status == "normalised" and molar:
        base.update(
            {
                "affinity_review_status": "machine_normalised",
                "affinity_value_molar": molar,
                "affinity_unit_normalized": "M",
                "canonical_affinity_value": molar,
                "canonical_affinity_unit": "M",
                "canonical_affinity_type": aff_type,
                "provenance": "machine_affinity_normalised",
            }
        )
        return base
    if raw or unit:
        base["affinity_review_status"] = "machine_raw"
        base["affinity_unit_raw"] = unit
    return base


def corpus_affinity_by_record(
    evidence_rows: Sequence[Mapping[str, str]],
    affinity_review_rows: Sequence[Mapping[str, str]],
    *,
    relationship_projection: RelationshipProjection,
) -> dict[str, dict[str, str]]:
    """Record-grain affinity after review. Unreviewed normalised scalars kept."""
    projected, _flags = project_affinity_reviews(
        evidence_rows,
        affinity_review_rows,
        relationship_projection=relationship_projection,
    )
    reviewed: dict[str, dict[str, str]] = {}
    for row in projected:
        record_id = _blank(row.get("record_id"))
        if record_id and record_id not in reviewed:
            reviewed[record_id] = dict(row)
    machine_by_id = _index_first(evidence_rows, "record_id")
    out: dict[str, dict[str, str]] = {}
    for record_id, machine in machine_by_id.items():
        if record_id in reviewed:
            out[record_id] = reviewed[record_id]
        else:
            out[record_id] = project_unreviewed_affinity(machine)
    return out


def _canonical_affinity_allowed(row: Mapping[str, str]) -> bool:
    status = _blank(row.get("affinity_review_status"))
    reason = _blank(row.get("non_affinity_reason"))
    if reason in UNSAFE_CANONICAL_AFFINITY_REASONS:
        return False
    if status in {
        AFFINITY_REVIEW_STATUS_EXCLUDE,
        AFFINITY_REVIEW_STATUS_RAW,
        AFFINITY_REVIEW_STATUS_PARK,
    }:
        return False
    molar = _blank(row.get("affinity_value_molar")) or _blank(
        row.get("canonical_affinity_value")
    )
    return bool(molar) and status in {
        AFFINITY_REVIEW_STATUS_EXACT,
        "machine_normalised",
    }


def apply_leakage_reviews(
    leakage_rows: Sequence[Mapping[str, str]],
    leakage_review_rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    """Apply leakage review onto matcher proposals. Empty review is valid."""
    review_by_record = _index_first(leakage_review_rows, "record_id")
    out: dict[str, dict[str, str]] = {}
    for row in leakage_rows:
        record_id = _blank(row.get("record_id"))
        copied = dict(row)
        proposed = _blank(row.get("leakage_exclusion_proposed")) == "true"
        needs_review = _blank(row.get("requires_review")) == "true"
        review = review_by_record.get(record_id)
        decision = _blank(review.get("manual_decision") if review else "")
        if needs_review and not decision:
            raise ScientificProposalError(
                f"leakage match for {record_id} requires review but has no decision"
            )
        excluded = False
        if decision == "confirm_leakage_exclusion":
            excluded = True
        elif decision == "retain_despite_false_positive_leakage":
            excluded = False
        elif decision == "park_unresolved":
            excluded = False
            copied["leakage_parked"] = "true"
        elif proposed and not needs_review:
            excluded = True
        copied["leakage_exclusion_applied"] = bool_token(excluded)
        copied["leakage_review_decision"] = decision
        out[record_id] = copied
    unexpected = set(review_by_record) - set(out)
    if unexpected:
        raise ScientificProposalError(
            "leakage review for records with no matcher row: "
            + "|".join(sorted(unexpected))
        )
    return out


def _record_outcome_from_routes(
    routes: Sequence[str],
    *,
    relationship_parked: bool,
    unresolved: bool,
    target_parked: bool,
    reasons: Sequence[str] = (),
) -> tuple[str, str, str]:
    if relationship_parked:
        return "relationship_parked", "hold_target_unresolved", "relationship_park_unresolved"
    if unresolved:
        return "unresolved_no_relationship", "hold_target_unresolved", "relationship_status=unresolved"
    if target_parked:
        return "target_parked", "hold_target_unresolved", "target_park_unresolved"
    ranked: dict[str, int] = {name: index for index, name in enumerate(RECORD_OUTCOME_PRECEDENCE)}
    mapped: list[str] = []
    for route in routes:
        if route == "leakage_exclusion_proposed":
            mapped.append("leakage_excluded")
        else:
            mapped.append(route)
    if not mapped:
        return "other_hold", "hold_target_unresolved", "no_reviewed_relationship"
    winner = min(mapped, key=lambda item: ranked.get(item, len(ranked)))
    route = routes[mapped.index(winner)]
    reason = reasons[mapped.index(winner)] if reasons and len(reasons) == len(routes) else winner
    return winner, route, reason


def s5_duplicate_diagnostics(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """Count duplicates. Does not merge or drop rows."""
    by_core: dict[str, list[str]] = defaultdict(list)
    by_pair: dict[tuple[str, str], list[str]] = defaultdict(list)
    by_source_core: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        rel_id = _blank(row.get("reviewed_relationship_id"))
        core = _blank(row.get("sequence_core"))
        name = _blank(row.get("canonical_target_name"))
        source = _blank(row.get("source_db"))
        if core:
            by_core[core].append(rel_id)
            by_source_core[core].add(source)
        if core and name:
            by_pair[(core, name)].append(rel_id)
    duplicate_cores = {core: ids for core, ids in by_core.items() if len(ids) > 1}
    duplicate_pairs = {
        f"{core}|{name}": ids for (core, name), ids in by_pair.items() if len(ids) > 1
    }
    cross_source = {
        core: sorted(sources)
        for core, sources in by_source_core.items()
        if len(sources) > 1 and core in duplicate_cores
    }
    ncbi_ena = []
    for core, sources in cross_source.items():
        if "ncbi_nuc" in sources and "ena" in sources:
            ncbi_ena.append(core)
    return {
        "label": "S5 diagnostic only",
        "s5_operations_run": False,
        "duplicate_sequence_core_count": len(duplicate_cores),
        "rows_participating_in_duplicate_sequence_core": sum(
            len(ids) for ids in duplicate_cores.values()
        ),
        "exact_sequence_core_canonical_target_duplicate_count": len(duplicate_pairs),
        "rows_participating_in_exact_pair_duplicates": sum(
            len(ids) for ids in duplicate_pairs.values()
        ),
        "cross_source_duplicate_sequence_core_count": len(cross_source),
        "ncbi_ena_overlapping_sequence_core_count": len(ncbi_ena),
    }


@dataclass
class Checkpoint2Application:
    """In-memory reviewed S4 application. Combined input is not mutated."""

    reviewed_relationships: list[dict[str, str]] = field(default_factory=list)
    reviewed_dictionary: list[dict[str, str]] = field(default_factory=list)
    record_map: list[dict[str, str]] = field(default_factory=list)
    parked_audit: list[dict[str, str]] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)


def apply_checkpoint2_reviews(
    *,
    combined_rows: Sequence[Mapping[str, str]],
    machine_relationship_rows: Sequence[Mapping[str, str]],
    dictionary_rows: Sequence[Mapping[str, str]],
    evidence_rows: Sequence[Mapping[str, str]],
    target_review_rows: Sequence[Mapping[str, str]],
    relationship_review_rows: Sequence[Mapping[str, str]],
    evidence_review_rows: Sequence[Mapping[str, str]],
    evidence_consistency_rows: Sequence[Mapping[str, str]],
    affinity_review_rows: Sequence[Mapping[str, str]],
    leakage_review_rows: Sequence[Mapping[str, str]],
    leakage_index: SequenceLeakageIndex | None = None,
    alias_rules: Sequence = (),
    expected_combined_records: int | None = None,
    expected_reviewed_resolved_targets: int | None = None,
    require_camp_identity: bool = True,
) -> Checkpoint2Application:
    """Project completed CHECKPOINT-2 reviews onto the combined S4 input.

    Idempotent for identical inputs. Does not write files or run S5.
    """
    if expected_combined_records is not None and len(combined_rows) != expected_combined_records:
        raise ScientificProposalError(
            f"combined input must have {expected_combined_records} records, "
            f"got {len(combined_rows)}"
        )
    combined_ids = [_blank(row.get("record_id")) for row in combined_rows]
    if len(set(combined_ids)) != len(combined_ids):
        raise ScientificProposalError("combined input has duplicate record_id values")

    projection, override_resolutions = project_effective_target_relationships(
        machine_relationship_rows,
        relationship_review_rows,
        dictionary_rows,
        target_review_rows,
    )
    effective_dictionary = build_effective_target_dictionary(
        dictionary_rows,
        target_review_rows,
        projection,
        override_resolutions,
    )
    if effective_dictionary.human_derived_pending_review:
        pending = [
            item.target_dictionary_id
            for item in effective_dictionary.human_derived_pending_review
        ]
        raise ScientificProposalError(
            "human-derived target identities still pending review: "
            + "|".join(pending)
        )

    parked_target_ids = {
        _blank(row.get("target_dictionary_id"))
        for row in target_review_rows
        if _blank(row.get("manual_decision")) == "park_unresolved"
        and _blank(row.get("target_dictionary_id"))
    }
    inactive_ids = {
        _blank(row.get("target_dictionary_id"))
        for row in effective_dictionary.inactive_entries
    }
    resolved_reviewed = {
        _blank(row.get("target_dictionary_id")): dict(row)
        for row in effective_dictionary.resolved_entries
        if _blank(row.get("target_dictionary_id"))
    }
    if require_camp_identity:
        if CAMP_TARGET_DICTIONARY_ID not in resolved_reviewed:
            raise ScientificProposalError(
                f"missing human-derived identity {CAMP_TARGET_DICTIONARY_ID}"
            )
        camp = resolved_reviewed[CAMP_TARGET_DICTIONARY_ID]
        camp_name = _blank(camp.get("canonical_target_name_proposal"))
        camp_type = _blank(camp.get("target_type_proposed"))
        camp_family = _blank(camp.get("target_family_proposed"))
        if camp_name != CAMP_CANONICAL_NAME:
            raise ScientificProposalError(f"cAMP canonical name drifted: {camp_name!r}")
        if camp_type != CAMP_TARGET_TYPE or camp_family != CAMP_TARGET_FAMILY:
            raise ScientificProposalError("cAMP type/family drifted")

    dict_by_id = {
        _blank(row.get("target_dictionary_id")): dict(row)
        for row in dictionary_rows
        if _blank(row.get("target_dictionary_id"))
    }
    for item in override_resolutions:
        dict_by_id.setdefault(
            item.target_dictionary_id, dict(item.proposed_dictionary_row)
        )

    evidence_by_record = project_effective_evidence_for_records(
        evidence_rows,
        supplemental_rows=evidence_consistency_rows,
        original_evidence_rows=evidence_review_rows,
    )
    affinity_by_record = corpus_affinity_by_record(
        evidence_rows,
        affinity_review_rows,
        relationship_projection=projection,
    )
    for record_id, aff in affinity_by_record.items():
        overlay = dict(aff)
        overlay["effective_evidence_level"] = _blank(
            evidence_by_record.get(record_id, {}).get("evidence_level")
        )
        overlay["evidence_affinity_inconsistency"] = flag_evidence_affinity_inconsistency(
            overlay
        )
        affinity_by_record[record_id] = overlay

    flags = collect_consistency_flag_record_ids(
        evidence_rows,
        affinity_review_rows,
        supplemental_rows=evidence_consistency_rows,
        original_evidence_rows=evidence_review_rows,
    )
    if flags:
        raise ScientificProposalError(
            "evidence-affinity inconsistencies remain after application: "
            + "|".join(flags)
        )

    evidence_machine = _index_first(evidence_rows, "record_id")
    relationship_review_by_record = _index_first(relationship_review_rows, "record_id")
    combined_by_id = _index_first(combined_rows, "record_id")

    rels_by_record: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in projection.effective_resolved:
        rels_by_record[_blank(row.get("record_id"))].append(row)
    parked_rels_by_record: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in projection.parked:
        parked_rels_by_record[_blank(row.get("record_id"))].append(row)

    index = leakage_index if leakage_index is not None else SequenceLeakageIndex()
    leakage_proposals: list[dict[str, str]] = []
    for combined in combined_rows:
        record_id = _blank(combined.get("record_id"))
        target_texts: list[str] = [_blank(combined.get("target_name_raw"))]
        for rel in rels_by_record.get(record_id, ()):
            did = _blank(rel.get("target_dictionary_id"))
            reviewed = resolved_reviewed.get(did, {})
            machine = dict_by_id.get(did, {})
            target_texts.append(_blank(rel.get("raw_target")))
            target_texts.append(
                _blank(reviewed.get("canonical_target_name_proposal"))
                or _blank(machine.get("canonical_target_name_proposal"))
            )
        leakage_proposals.append(
            propose_leakage(
                combined,
                index=index,
                rules=alias_rules,
                target_texts=target_texts,
            )
        )
    leakage_applied = apply_leakage_reviews(leakage_proposals, leakage_review_rows)

    reviewed_relationships: list[dict[str, str]] = []
    parked_audit: list[dict[str, str]] = []
    active_id_counts: Counter[str] = Counter()

    def dictionary_fields(did: str) -> dict[str, str]:
        reviewed = resolved_reviewed.get(did)
        machine = dict_by_id.get(did, {})
        source = reviewed if reviewed is not None else machine
        origin = "reviewed"
        if reviewed is None:
            origin = "unreviewed_deterministic"
        elif _blank(source.get("canonicalisation_method")) == "checkpoint2_relationship_override":
            origin = HUMAN_DERIVED_ORIGIN
        elif _blank(source.get("_dictionary_origin")):
            origin = _blank(source.get("_dictionary_origin"))
        return {
            "canonical_target_name": _blank(
                source.get("canonical_target_name_proposal")
            ),
            "target_type": _blank(source.get("target_type_proposed")),
            "target_family": _blank(source.get("target_family_proposed")),
            "target_uniprot": _blank(source.get("uniprot_proposed")),
            "target_pfam": _blank(source.get("target_pfam_proposed")),
            "target_interpro": _blank(source.get("target_interpro_proposed")),
            "target_decision_id": _blank(source.get("_target_decision_id")),
            "target_decision": _blank(source.get("_target_decision"))
            or ("unreviewed_deterministic" if reviewed is None else ""),
            "dictionary_origin": origin,
        }

    for combined in combined_rows:
        record_id = _blank(combined.get("record_id"))
        for rel in rels_by_record.get(record_id, ()):
            did = _blank(rel.get("target_dictionary_id"))
            if did in parked_target_ids:
                continue
            if did in inactive_ids:
                raise ScientificProposalError(
                    f"active relationship {record_id} references inactive target {did}"
                )
            if did not in resolved_reviewed and did not in dict_by_id:
                raise ScientificProposalError(
                    f"active relationship {record_id} has unknown target {did}"
                )
            if did in resolved_reviewed or (
                did in dict_by_id
                and did not in parked_target_ids
                and did not in inactive_ids
            ):
                meta = dictionary_fields(did)
                if not meta["canonical_target_name"]:
                    raise ScientificProposalError(
                        f"active relationship {record_id} missing canonical target name"
                    )
                evidence = evidence_by_record.get(record_id) or {}
                affinity = dict(affinity_by_record.get(record_id) or {})
                canonical_ok = _canonical_affinity_allowed(affinity)
                leakage = leakage_applied.get(record_id, {})
                no_binding = _blank(affinity.get("non_affinity_reason")) == "no_binding"
                route, reason = routing_preview(
                    relationship_status="resolved_single"
                    if _blank(rel.get("checkpoint2_projection_kind"))
                    != "confirm_multi_target_expansion"
                    else "resolved_multiple",
                    target_type=meta["target_type"],
                    evidence_level=_blank(evidence.get("evidence_level")),
                    evidence_ambiguous=False,
                    leakage_proposed=_blank(leakage.get("leakage_exclusion_applied"))
                    == "true",
                    no_binding=no_binding,
                )
                assert_routing_vocab(route)
                if route == "primary_candidate" and _blank(evidence.get("evidence_level")) == "E5":
                    raise ScientificProposalError(
                        f"E5 relationship {record_id} routed as primary"
                    )
                rel_id = reviewed_relationship_id(
                    record_id, _blank(rel.get("relationship_index"))
                )
                row = fill_row(
                    REVIEWED_RELATIONSHIP_COLUMNS,
                    {
                        "reviewed_relationship_id": rel_id,
                        "record_id": record_id,
                        "source_db": _blank(combined.get("source_db")),
                        "native_id": _blank(combined.get("native_id")),
                        "relationship_index": _blank(rel.get("relationship_index")) or "1",
                        "relationship_projection_kind": _blank(
                            rel.get("checkpoint2_projection_kind")
                        ),
                        "relationship_decision_id": _blank(
                            relationship_review_by_record.get(record_id, {}).get(
                                "decision_id"
                            )
                        ),
                        "raw_target": _blank(rel.get("raw_target")),
                        "target_provenance_source": _blank(
                            rel.get("target_provenance_source")
                        ),
                        "target_provenance_locator": _blank(
                            rel.get("target_provenance_locator")
                        ),
                        "target_dictionary_id": did,
                        **meta,
                        "target_region_or_fragment": _blank(
                            rel.get("target_region_or_fragment")
                        ),
                        "evidence_level": _blank(evidence.get("evidence_level")),
                        "evidence_score": _blank(evidence.get("evidence_score"))
                        or str(
                            EVIDENCE_SCORE_BY_LEVEL.get(
                                _blank(evidence.get("evidence_level")), ""
                            )
                        ),
                        "evidence_type": _blank(evidence.get("evidence_type"))
                        or EVIDENCE_TYPE_BY_LEVEL.get(
                            _blank(evidence.get("evidence_level")), ""
                        ),
                        "evidence_source": _blank(evidence.get("source")),
                        "evidence_decision_id": _blank(evidence.get("decision_id")),
                        "evidence_provenance": _blank(evidence.get("provenance")),
                        "evidence_rule": _blank(
                            evidence_machine.get(record_id, {}).get("evidence_rule")
                        ),
                        "affinity_value_raw": _blank(affinity.get("affinity_value_raw")),
                        "affinity_unit_raw": _blank(
                            affinity.get("affinity_unit_raw")
                        )
                        or _blank(
                            evidence_machine.get(record_id, {}).get("affinity_unit_raw")
                        ),
                        "affinity_review_status": _blank(
                            affinity.get("affinity_review_status")
                        ),
                        "affinity_type": _blank(affinity.get("affinity_type")),
                        "affinity_value_molar": _blank(
                            affinity.get("affinity_value_molar")
                        )
                        if canonical_ok
                        else "",
                        "affinity_unit_normalized": _blank(
                            affinity.get("affinity_unit_normalized")
                        )
                        if canonical_ok
                        else "",
                        "affinity_qualifier": _blank(affinity.get("affinity_qualifier")),
                        "affinity_range_status": _blank(
                            affinity.get("affinity_range_status")
                        ),
                        "affinity_bound_molar": _blank(
                            affinity.get("affinity_bound_molar")
                        ),
                        "non_affinity_reason": _blank(
                            affinity.get("non_affinity_reason")
                        ),
                        "affinity_transform_rule": _blank(
                            affinity.get("transform_rule")
                        ),
                        "affinity_decision_id": _blank(
                            affinity.get("review_decision_id")
                        ),
                        "affinity_provenance": _blank(affinity.get("provenance")),
                        "canonical_affinity_value": _blank(
                            affinity.get("canonical_affinity_value")
                        )
                        if canonical_ok
                        else "",
                        "canonical_affinity_unit": _blank(
                            affinity.get("canonical_affinity_unit")
                        )
                        if canonical_ok
                        else "",
                        "canonical_affinity_type": _blank(
                            affinity.get("canonical_affinity_type")
                        )
                        if canonical_ok
                        else "",
                        "sequence_full": _blank(combined.get("sequence_full")),
                        "sequence_core": _blank(combined.get("sequence_core")),
                        "molecule_type": _blank(combined.get("molecule_type")),
                        "chemistry": _blank(combined.get("chemistry")),
                        "publication": _blank(combined.get("publication")),
                        "doi": _blank(combined.get("doi")),
                        "pubmed_id": _blank(combined.get("pubmed_id")),
                        "accession": _blank(combined.get("accession")),
                        "leakage_exclusion": bool_token(
                            _blank(leakage.get("leakage_exclusion_applied")) == "true"
                        ),
                        "leakage_sequence_match_kind": _blank(
                            leakage.get("sequence_match_kind")
                        ),
                        "leakage_identity": _blank(leakage.get("identity")),
                        "leakage_target_alias_match": _blank(
                            leakage.get("target_alias_match")
                        ),
                        "leakage_reason": _blank(leakage.get("notes")),
                        "s4_route": route,
                        "s4_route_reason": reason,
                    },
                )
                reviewed_relationships.append(row)
                active_id_counts[did] += 1
                if route != "primary_candidate":
                    parked_audit.append(
                        fill_row(
                            PARKED_AUDIT_COLUMNS,
                            {
                                "record_id": record_id,
                                "source_db": row["source_db"],
                                "audit_class": route,
                                "reason": reason,
                                "reviewed_relationship_id": rel_id,
                                "target_dictionary_id": did,
                                "raw_target": row["raw_target"],
                                "canonical_target_name": row["canonical_target_name"],
                                "evidence_level": row["evidence_level"],
                                "s4_route": route,
                                "s4_route_reason": reason,
                            },
                        )
                    )

    for combined in combined_rows:
        record_id = _blank(combined.get("record_id"))
        source_db = _blank(combined.get("source_db"))
        for rel in rels_by_record.get(record_id, ()):
            did = _blank(rel.get("target_dictionary_id"))
            if did not in parked_target_ids:
                continue
            evidence = evidence_by_record.get(record_id) or {}
            route, reason = routing_preview(
                relationship_status=_blank(rel.get("relationship_status"))
                or "resolved_single",
                target_type=_blank(rel.get("target_type_proposed")) or "unknown",
                evidence_level=_blank(evidence.get("evidence_level")),
                evidence_ambiguous=False,
                leakage_proposed=_blank(
                    leakage_applied.get(record_id, {}).get("leakage_exclusion_applied")
                )
                == "true",
                no_binding=False,
                target_parked=True,
            )
            parked_audit.append(
                fill_row(
                    PARKED_AUDIT_COLUMNS,
                    {
                        "record_id": record_id,
                        "source_db": source_db,
                        "audit_class": "target_parked",
                        "reason": reason,
                        "reviewed_relationship_id": reviewed_relationship_id(
                            record_id, _blank(rel.get("relationship_index"))
                        ),
                        "target_dictionary_id": did,
                        "raw_target": _blank(rel.get("raw_target")),
                        "canonical_target_name": _blank(
                            dict_by_id.get(did, {}).get("canonical_target_name_proposal")
                        ),
                        "evidence_level": _blank(evidence.get("evidence_level")),
                        "s4_route": route,
                        "s4_route_reason": reason,
                    },
                )
            )
        for rel in parked_rels_by_record.get(record_id, ()):
            route, reason = routing_preview(
                relationship_status="unresolved",
                target_type="",
                evidence_level=_blank(
                    evidence_by_record.get(record_id, {}).get("evidence_level")
                ),
                evidence_ambiguous=False,
                leakage_proposed=False,
                no_binding=False,
                relationship_parked=True,
            )
            parked_audit.append(
                fill_row(
                    PARKED_AUDIT_COLUMNS,
                    {
                        "record_id": record_id,
                        "source_db": source_db,
                        "audit_class": "relationship_parked",
                        "reason": reason,
                        "reviewed_relationship_id": reviewed_relationship_id(
                            record_id, _blank(rel.get("relationship_index"))
                        ),
                        "target_dictionary_id": _blank(rel.get("target_dictionary_id")),
                        "raw_target": _blank(rel.get("raw_target")),
                        "canonical_target_name": "",
                        "evidence_level": _blank(
                            evidence_by_record.get(record_id, {}).get("evidence_level")
                        ),
                        "s4_route": route,
                        "s4_route_reason": reason,
                    },
                )
            )

    dictionary_out: list[dict[str, str]] = []
    for did, row in resolved_reviewed.items():
        dictionary_out.append(
            fill_row(
                REVIEWED_DICTIONARY_COLUMNS,
                {
                    "target_dictionary_id": did,
                    "canonical_target_name": _blank(
                        row.get("canonical_target_name_proposal")
                    ),
                    "raw_target": _blank(row.get("raw_target")),
                    "target_type": _blank(row.get("target_type_proposed")),
                    "target_family": _blank(row.get("target_family_proposed")),
                    "target_uniprot": _blank(row.get("uniprot_proposed")),
                    "target_pfam": _blank(row.get("target_pfam_proposed")),
                    "target_interpro": _blank(row.get("target_interpro_proposed")),
                    "target_decision_id": _blank(row.get("_target_decision_id")),
                    "target_decision": _blank(row.get("_target_decision")),
                    "dictionary_origin": HUMAN_DERIVED_ORIGIN
                    if did == CAMP_TARGET_DICTIONARY_ID
                    else "reviewed",
                    "reviewed_resolved": "true",
                    "n_active_relationships": str(active_id_counts.get(did, 0)),
                    "resolution_provenance": _blank(row.get("resolution_provenance")),
                },
            )
        )
    unreviewed_ids = sorted(
        did
        for did in active_id_counts
        if did not in resolved_reviewed
    )
    for did in unreviewed_ids:
        row = dict_by_id[did]
        dictionary_out.append(
            fill_row(
                REVIEWED_DICTIONARY_COLUMNS,
                {
                    "target_dictionary_id": did,
                    "canonical_target_name": _blank(
                        row.get("canonical_target_name_proposal")
                    ),
                    "raw_target": _blank(row.get("raw_target")),
                    "target_type": _blank(row.get("target_type_proposed")),
                    "target_family": _blank(row.get("target_family_proposed")),
                    "target_uniprot": _blank(row.get("uniprot_proposed")),
                    "target_pfam": _blank(row.get("target_pfam_proposed")),
                    "target_interpro": _blank(row.get("target_interpro_proposed")),
                    "target_decision_id": "",
                    "target_decision": "unreviewed_deterministic",
                    "dictionary_origin": "unreviewed_deterministic",
                    "reviewed_resolved": "false",
                    "n_active_relationships": str(active_id_counts[did]),
                    "resolution_provenance": _blank(row.get("resolution_provenance")),
                },
            )
        )
    dictionary_out.sort(key=lambda item: item["target_dictionary_id"])

    rels_out_by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in reviewed_relationships:
        rels_out_by_record[row["record_id"]].append(row)

    record_map: list[dict[str, str]] = []
    parked_rel_records = {
        _blank(row.get("record_id")) for row in projection.parked
    }
    machine_rel_records = {
        _blank(row.get("record_id")) for row in machine_relationship_rows
    }
    target_park_records = {
        _blank(row.get("record_id"))
        for row in projection.effective_resolved
        if _blank(row.get("target_dictionary_id")) in parked_target_ids
    }
    for combined in combined_rows:
        record_id = _blank(combined.get("record_id"))
        active = rels_out_by_record.get(record_id, [])
        n_target_park = sum(
            1
            for rel in rels_by_record.get(record_id, ())
            if _blank(rel.get("target_dictionary_id")) in parked_target_ids
        )
        relationship_parked = record_id in parked_rel_records
        unresolved = (
            record_id not in machine_rel_records and not relationship_parked
        )
        all_target_parked = (
            n_target_park > 0
            and not active
            and not relationship_parked
            and not unresolved
        )
        outcome, route, reason = _record_outcome_from_routes(
            [row["s4_route"] for row in active],
            relationship_parked=relationship_parked,
            unresolved=unresolved,
            target_parked=all_target_parked,
            reasons=[row["s4_route_reason"] for row in active],
        )
        if unresolved:
            parked_audit.append(
                fill_row(
                    PARKED_AUDIT_COLUMNS,
                    {
                        "record_id": record_id,
                        "source_db": _blank(combined.get("source_db")),
                        "audit_class": "unresolved_no_relationship",
                        "reason": reason,
                        "reviewed_relationship_id": "",
                        "target_dictionary_id": "",
                        "raw_target": _blank(combined.get("target_name_raw")),
                        "canonical_target_name": "",
                        "evidence_level": _blank(
                            evidence_by_record.get(record_id, {}).get("evidence_level")
                        ),
                        "s4_route": route,
                        "s4_route_reason": reason,
                    },
                )
            )
        record_map.append(
            fill_row(
                RECORD_MAP_COLUMNS,
                {
                    "record_id": record_id,
                    "source_db": _blank(combined.get("source_db")),
                    "n_effective_relationships": str(len(active)),
                    "n_target_parked_relationships": str(n_target_park),
                    "relationship_parked": bool_token(relationship_parked),
                    "unresolved_no_relationship": bool_token(unresolved),
                    "reviewed_relationship_ids": join_unique(
                        [row["reviewed_relationship_id"] for row in active]
                    ),
                    "target_dictionary_ids": join_unique(
                        [row["target_dictionary_id"] for row in active]
                    ),
                    "s4_record_outcome": outcome,
                    "s4_record_route": route,
                    "s4_record_route_reason": reason,
                },
            )
        )

    mapped_ids = {_blank(row.get("record_id")) for row in record_map}
    if mapped_ids != set(combined_ids):
        missing = sorted(set(combined_ids) - mapped_ids)
        extra = sorted(mapped_ids - set(combined_ids))
        raise ScientificProposalError(
            f"record map coverage failed missing={missing[:10]} extra={extra[:10]}"
        )

    counts = _application_counts(
        combined_rows=combined_rows,
        projection=projection,
        parked_target_ids=parked_target_ids,
        reviewed_relationships=reviewed_relationships,
        record_map=record_map,
        dictionary_out=dictionary_out,
        target_review_rows=target_review_rows,
        affinity_by_record=affinity_by_record,
        evidence_by_record=evidence_by_record,
        leakage_applied=leakage_applied,
        override_resolutions=override_resolutions,
        target_park_records=target_park_records,
    )
    validation = validate_application(
        combined_rows=combined_rows,
        reviewed_relationships=reviewed_relationships,
        record_map=record_map,
        dictionary_out=dictionary_out,
        parked_target_ids=parked_target_ids,
        inactive_ids=inactive_ids,
        affinity_by_record=affinity_by_record,
        flags=flags,
        counts=counts,
        require_camp_identity=require_camp_identity,
        expected_reviewed_resolved_targets=expected_reviewed_resolved_targets,
    )
    return Checkpoint2Application(
        reviewed_relationships=reviewed_relationships,
        reviewed_dictionary=dictionary_out,
        record_map=record_map,
        parked_audit=parked_audit,
        counts=counts,
        validation=validation,
    )


def _application_counts(
    *,
    combined_rows: Sequence[Mapping[str, str]],
    projection: RelationshipProjection,
    parked_target_ids: set[str],
    reviewed_relationships: Sequence[Mapping[str, str]],
    record_map: Sequence[Mapping[str, str]],
    dictionary_out: Sequence[Mapping[str, str]],
    target_review_rows: Sequence[Mapping[str, str]],
    affinity_by_record: Mapping[str, Mapping[str, str]],
    evidence_by_record: Mapping[str, Mapping[str, str]],
    leakage_applied: Mapping[str, Mapping[str, str]],
    override_resolutions: Sequence,
    target_park_records: set[str],
) -> dict[str, Any]:
    rel_kinds = Counter(
        _blank(row.get("checkpoint2_projection_kind"))
        for row in projection.effective_resolved
    )
    n_multi = sum(
        1
        for _record, n in Counter(
            _blank(row.get("record_id")) for row in projection.effective_resolved
        ).items()
        if n > 1
    )
    target_decisions = Counter(
        _blank(row.get("manual_decision")) for row in target_review_rows
    )
    reviewed_resolved = sum(
        1 for row in dictionary_out if row.get("reviewed_resolved") == "true"
    )
    unreviewed = sum(
        1 for row in dictionary_out if row.get("reviewed_resolved") == "false"
    )
    evidence_dist = Counter(
        _blank(row.get("evidence_level")) for row in evidence_by_record.values()
    )
    evidence_source = Counter(
        _blank(row.get("source")) for row in evidence_by_record.values()
    )
    aff_status = Counter()
    exact_examples: list[dict[str, str]] = []
    seen_aff: set[str] = set()
    for record_id, row in affinity_by_record.items():
        if record_id in seen_aff:
            continue
        seen_aff.add(record_id)
        status = _blank(row.get("affinity_review_status"))
        if status == AFFINITY_REVIEW_STATUS_EXACT:
            aff_status["exact_scalar"] += 1
            if _blank(row.get("affinity_value_molar")):
                exact_examples.append(
                    {
                        "record_id": record_id,
                        "affinity_type": _blank(row.get("affinity_type")),
                        "affinity_value_molar": _blank(row.get("affinity_value_molar")),
                        "transform_rule": _blank(row.get("transform_rule")),
                    }
                )
        elif status == AFFINITY_REVIEW_STATUS_RAW:
            aff_status["raw_only"] += 1
        elif status == AFFINITY_REVIEW_STATUS_EXCLUDE:
            aff_status["non_affinity"] += 1
        elif status == AFFINITY_REVIEW_STATUS_PARK:
            aff_status["affinity_park"] += 1
        elif status == "machine_normalised":
            aff_status["machine_normalised"] += 1
        elif status == "machine_raw":
            aff_status["machine_raw"] += 1
        else:
            aff_status["unreviewed_blank"] += 1
    rel_routes = Counter(row.get("s4_route") for row in reviewed_relationships)
    record_outcomes = Counter(row.get("s4_record_outcome") for row in record_map)
    by_source_rel: dict[str, Counter[str]] = defaultdict(Counter)
    by_source_rec: dict[str, Counter[str]] = defaultdict(Counter)
    for row in reviewed_relationships:
        by_source_rel[_blank(row.get("source_db"))][row.get("s4_route") or ""] += 1
    for row in record_map:
        by_source_rec[_blank(row.get("source_db"))][row.get("s4_record_outcome") or ""] += 1
    leakage_excluded = sum(
        1
        for row in leakage_applied.values()
        if _blank(row.get("leakage_exclusion_applied")) == "true"
    )
    return {
        "n_combined_records": len(list(combined_rows)),
        "n_machine_relationship_rows": len(list(projection.effective_resolved))
        + len(list(projection.parked))
        + len(list(projection.dropped_by_reject))
        + len(list(projection.dropped_by_override)),
        "n_effective_relationship_rows_including_target_parks": len(
            projection.effective_resolved
        ),
        "n_relationship_parked_rows": len(projection.parked),
        "n_relationship_parked_records": len(
            {row.get("record_id") for row in projection.parked}
        ),
        "n_dropped_by_reject": len(projection.dropped_by_reject),
        "n_dropped_by_override": len(projection.dropped_by_override),
        "n_records_with_multiple_effective_targets": n_multi,
        "relationship_projection_kinds": dict(rel_kinds),
        "n_reviewed_relationship_rows": len(reviewed_relationships),
        "n_target_park_records": len(target_park_records),
        "n_target_park_relationships": sum(
            1
            for row in projection.effective_resolved
            if _blank(row.get("target_dictionary_id")) in parked_target_ids
        ),
        "target_review_decisions": dict(target_decisions),
        "n_reviewed_resolved_targets": reviewed_resolved,
        "n_unreviewed_deterministic_targets": unreviewed,
        "n_effective_dictionary_entries": len(dictionary_out),
        "n_human_derived_targets": sum(
            1
            for item in override_resolutions
            if getattr(item, "origin", "") == HUMAN_DERIVED_ORIGIN
        ),
        "evidence_distribution_record_grain": dict(evidence_dist),
        "evidence_source_record_grain": dict(evidence_source),
        "affinity_record_grain": dict(aff_status),
        "exact_scalar_examples": exact_examples,
        "relationship_routing": dict(rel_routes),
        "source_record_outcomes": dict(record_outcomes),
        "relationship_routing_by_source": {
            source: dict(counts) for source, counts in sorted(by_source_rel.items())
        },
        "source_record_outcomes_by_source": {
            source: dict(counts) for source, counts in sorted(by_source_rec.items())
        },
        "n_leakage_excluded_records": leakage_excluded,
        "duplicate_diagnostics": s5_duplicate_diagnostics(reviewed_relationships),
        "s5_operations_run": False,
        "s5_operations_not_run": list(S5_OPERATIONS),
    }


def validate_application(
    *,
    combined_rows: Sequence[Mapping[str, str]],
    reviewed_relationships: Sequence[Mapping[str, str]],
    record_map: Sequence[Mapping[str, str]],
    dictionary_out: Sequence[Mapping[str, str]],
    parked_target_ids: set[str],
    inactive_ids: set[str],
    affinity_by_record: Mapping[str, Mapping[str, str]],
    flags: Sequence[str],
    counts: Mapping[str, Any],
    require_camp_identity: bool = True,
    expected_reviewed_resolved_targets: int | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if len(record_map) != len(combined_rows):
        errors.append("record map length != combined input")
    combined_ids = [_blank(row.get("record_id")) for row in combined_rows]
    map_ids = [_blank(row.get("record_id")) for row in record_map]
    if combined_ids != map_ids:
        errors.append("record map order/identity does not match combined input")
    dict_ids = [_blank(row.get("target_dictionary_id")) for row in dictionary_out]
    if len(dict_ids) != len(set(dict_ids)):
        errors.append("duplicate target dictionary ids in effective dictionary")
    if require_camp_identity:
        camp_rows = [
            row
            for row in dictionary_out
            if row.get("target_dictionary_id") == CAMP_TARGET_DICTIONARY_ID
        ]
        if len(camp_rows) != 1:
            errors.append("cAMP identity must appear exactly once")
        elif camp_rows[0].get("canonical_target_name") != CAMP_CANONICAL_NAME:
            errors.append("cAMP canonical name mismatch")
    reviewed_resolved = [
        row for row in dictionary_out if row.get("reviewed_resolved") == "true"
    ]
    if (
        expected_reviewed_resolved_targets is not None
        and len(reviewed_resolved) != expected_reviewed_resolved_targets
    ):
        errors.append(
            "reviewed resolved dictionary expected "
            f"{expected_reviewed_resolved_targets}, got {len(reviewed_resolved)}"
        )
    dict_lookup = {
        _blank(row.get("target_dictionary_id")): row for row in dictionary_out
    }
    for row in reviewed_relationships:
        did = _blank(row.get("target_dictionary_id"))
        if did in parked_target_ids:
            errors.append(f"{row.get('reviewed_relationship_id')} references parked target")
        if did in inactive_ids:
            errors.append(f"{row.get('reviewed_relationship_id')} references inactive target")
        if did not in dict_lookup:
            errors.append(f"{row.get('reviewed_relationship_id')} missing dictionary {did}")
        if not _blank(row.get("canonical_target_name")):
            errors.append(f"{row.get('reviewed_relationship_id')} missing canonical name")
        if not _blank(row.get("evidence_level")):
            errors.append(f"{row.get('reviewed_relationship_id')} missing evidence")
        if row.get("s4_route") == "primary_candidate" and row.get("evidence_level") == "E5":
            errors.append(f"{row.get('reviewed_relationship_id')} E5 primary")
        status = _blank(row.get("affinity_review_status"))
        canonical = _blank(row.get("canonical_affinity_value"))
        if canonical and status not in {AFFINITY_REVIEW_STATUS_EXACT, "machine_normalised"}:
            errors.append(
                f"{row.get('reviewed_relationship_id')} unsafe canonical affinity"
            )
        if _blank(row.get("non_affinity_reason")) in UNSAFE_CANONICAL_AFFINITY_REASONS:
            if canonical or _blank(row.get("affinity_value_molar")):
                errors.append(
                    f"{row.get('reviewed_relationship_id')} non-affinity wrote a scalar"
                )
        try:
            assert_routing_vocab(_blank(row.get("s4_route")))
        except ValueError as exc:
            errors.append(str(exc))
        if row.get("leakage_exclusion") == "true" and row.get("s4_route") != "leakage_exclusion_proposed":
            errors.append(f"{row.get('reviewed_relationship_id')} leakage bypass")
    if flags:
        errors.append(f"evidence-affinity flags remain: {len(flags)}")
    e2_non_affinity = [
        record_id
        for record_id, row in affinity_by_record.items()
        if _blank(row.get("affinity_review_status")) == AFFINITY_REVIEW_STATUS_EXCLUDE
        and _blank(row.get("effective_evidence_level")) == "E2"
    ]
    if e2_non_affinity:
        errors.append("active E2 relies on reviewed exclude_non_affinity")
    exact_not_e2 = [
        record_id
        for record_id, row in affinity_by_record.items()
        if _blank(row.get("affinity_review_status")) == AFFINITY_REVIEW_STATUS_EXACT
        and _blank(row.get("affinity_value_molar"))
        and _blank(row.get("effective_evidence_level")) != "E2"
    ]
    if exact_not_e2:
        errors.append("reviewed exact Kd without effective E2")
    if counts.get("s5_operations_run"):
        errors.append("S5 operations were marked as run")
    return {
        "ok": not errors,
        "errors": errors,
        "n_evidence_affinity_inconsistencies": len(list(flags)),
        "n_reviewed_relationships": len(list(reviewed_relationships)),
        "n_record_map": len(list(record_map)),
        "n_dictionary": len(list(dictionary_out)),
    }

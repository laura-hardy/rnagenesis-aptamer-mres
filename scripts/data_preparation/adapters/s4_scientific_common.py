"""Shared vocabularies, columns, and helpers for Milestone-3 scientific proposals."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final, Mapping, MutableMapping, Sequence

from adapters.target_extraction_common import (
    CANONICAL_FIELDS_MUST_STAY_EMPTY,
    SEQ_LEAK_RE,
    TargetExtractionError,
    alias_candidate_key,
    bool_token,
    join_unique,
    primary_match_key,
)

ScientificProposalError = TargetExtractionError

TARGET_TYPE_VOCAB: Final[frozenset[str]] = frozenset(
    {
        "protein",
        "peptide",
        "small_molecule",
        "ion",
        "nucleic_acid",
        "cell",
        "organism",
        "other",
        "unknown",
    }
)
TARGET_FAMILY_VOCAB: Final[frozenset[str]] = frozenset(
    {
        "enzyme",
        "receptor",
        "cytokine",
        "growth_factor",
        "antibody_immunoglobulin",
        "transcription_factor",
        "structural_protein",
        "viral_protein",
        "bacterial_surface_protein",
        "transport_protein",
        "other",
        "unknown",
    }
)
EVIDENCE_LEVELS: Final[tuple[str, ...]] = ("E1", "E2", "E3", "E4", "E5")
EVIDENCE_TYPE_BY_LEVEL: Final[dict[str, str]] = {
    "E1": "structural",
    "E2": "quantitative_affinity",
    "E3": "qualitative_binding",
    "E4": "selection_enrichment",
    "E5": "database_annotation",
}
EVIDENCE_SCORE_BY_LEVEL: Final[dict[str, int]] = {
    "E1": 5,
    "E2": 4,
    "E3": 3,
    "E4": 2,
    "E5": 1,
}
AFFINITY_TYPE_VOCAB: Final[frozenset[str]] = frozenset(
    {"Kd", "Ka", "IC50", "EC50", "Ki", "other"}
)
ROUTING_VOCAB: Final[tuple[str, ...]] = (
    "leakage_exclusion_proposed",
    "hold_target_unresolved",
    "reject_no_binding_evidence",
    "hold_evidence_ambiguous",
    "park_non_protein",
    "park_evidence_e5",
    "primary_candidate",
)
INACTIVE_TARGET_DECISION: Final[str] = "exclude_no_active_relationship"
CONFIRM_AFFINITY_SCALAR: Final[str] = "confirm_affinity_scalar"
RETAIN_AFFINITY_RAW: Final[str] = "retain_affinity_raw"
EXCLUDE_NON_AFFINITY: Final[str] = "exclude_non_affinity"
AFFINITY_DECISION_VOCAB: Final[frozenset[str]] = frozenset(
    {
        CONFIRM_AFFINITY_SCALAR,
        RETAIN_AFFINITY_RAW,
        EXCLUDE_NON_AFFINITY,
        "park_unresolved",
    }
)
TARGET_DECISION_VOCAB: Final[frozenset[str]] = frozenset(
    {
        "approve_proposal",
        "override",
        "park_unresolved",
        INACTIVE_TARGET_DECISION,
    }
)
RELATIONSHIP_DECISION_VOCAB: Final[frozenset[str]] = frozenset(
    {
        "confirm_multi_target_expansion",
        "reject_proposed_relationship",
        "override",
        "park_unresolved",
    }
)
EVIDENCE_DECISION_VOCAB: Final[frozenset[str]] = frozenset(
    {
        "confirm_evidence",
        "override_evidence",
        "park_unresolved",
    }
)
LEAKAGE_DECISION_VOCAB: Final[frozenset[str]] = frozenset(
    {
        "confirm_leakage_exclusion",
        "retain_despite_false_positive_leakage",
        "park_unresolved",
    }
)
MANUAL_DECISION_VOCAB: Final[frozenset[str]] = (
    TARGET_DECISION_VOCAB
    | RELATIONSHIP_DECISION_VOCAB
    | EVIDENCE_DECISION_VOCAB
    | AFFINITY_DECISION_VOCAB
    | LEAKAGE_DECISION_VOCAB
)
AFFINITY_QUALIFIER_VOCAB: Final[frozenset[str]] = frozenset(
    {"<", "<=", ">", ">=", ">>", "approximate"}
)
AFFINITY_RANGE_STATUS_VOCAB: Final[frozenset[str]] = frozenset(
    {"range", "list", "multi_condition"}
)
AFFINITY_TRANSFORM_RULE_VOCAB: Final[frozenset[str]] = frozenset(
    {
        "mojibake_micro_M",
        "glued_unit",
        "scientific_notation",
        "central_value_uncertainty",
        "parse_inequality_bound",
    }
)
AFFINITY_SCALAR_TRANSFORM_RULES: Final[frozenset[str]] = frozenset(
    {
        "mojibake_micro_M",
        "glued_unit",
        "scientific_notation",
        "central_value_uncertainty",
    }
)
NON_AFFINITY_REASON_VOCAB: Final[frozenset[str]] = frozenset(
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
HUMAN_FIELDS: Final[tuple[str, ...]] = (
    "manual_decision",
    "manual_target_name",
    "manual_uniprot",
    "manual_target_type",
    "manual_target_family",
    "manual_pfam_interpro",
    "manual_relationship_action",
    "manual_evidence_level",
    "manual_affinity_value",
    "manual_affinity_unit",
    "manual_notes",
)
AFFINITY_EXTRA_HUMAN_FIELDS: Final[tuple[str, ...]] = (
    "manual_affinity_type",
    "manual_affinity_qualifier",
    "manual_affinity_range_status",
    "manual_affinity_transform_rule",
    "manual_affinity_non_affinity_reason",
)

ENRICHED_DICTIONARY_COLUMNS: Final[tuple[str, ...]] = (
    "target_dictionary_id",
    "raw_target",
    "primary_match_key",
    "alias_candidate_key",
    "canonical_target_name_proposal",
    "canonicalisation_method",
    "proposal_confidence",
    "source_keys",
    "n_records",
    "n_relationships",
    "source_uniprot_seed",
    "source_target_type_priors",
    "source_target_ids",
    "record_expansion_involved",
    "ambiguity_flags",
    "requires_checkpoint2",
    "review_status",
    "target_type_proposed",
    "target_type_source_proposed",
    "target_type_confidence",
    "uniprot_proposed",
    "uniprot_candidates",
    "uniprot_resolution_tier",
    "uniprot_query",
    "uniprot_organism_context",
    "uniprot_ambiguity_reason",
    "target_family_proposed",
    "target_family_source",
    "target_pfam_proposed",
    "target_interpro_proposed",
    "target_region_or_fragment",
    "resolution_provenance",
    "machine_recommendation",
    "scientific_ambiguity_reason",
)

RELATIONSHIP_SCIENTIFIC_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "relationship_index",
    "source_db",
    "target_dictionary_id",
    "raw_target",
    "relationship_status",
    "record_expansion_proposed",
    "target_type_proposed",
    "target_type_source_proposed",
    "uniprot_proposed",
    "target_family_proposed",
    "target_pfam_proposed",
    "target_region_or_fragment",
    "evidence_level_proposed",
    "evidence_type_proposed",
    "evidence_score_proposed",
    "evidence_rule",
    "evidence_provenance",
    "alternative_evidence_level",
    "evidence_requires_review",
    "affinity_type_proposed",
    "affinity_value_raw",
    "affinity_unit_raw",
    "affinity_value_molar_proposed",
    "affinity_parse_status",
    "affinity_parse_rule",
    "affinity_requires_review",
    "routing_preview",
    "leakage_match_kind",
    "requires_checkpoint2",
    "notes",
)

EVIDENCE_AFFINITY_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "relationship_index",
    "source_db",
    "evidence_level_proposed",
    "evidence_type_proposed",
    "evidence_score_proposed",
    "evidence_rule",
    "evidence_provenance",
    "alternative_evidence_level",
    "evidence_requires_review",
    "e4_e5_threshold_ambiguous",
    "affinity_type_proposed",
    "affinity_value_raw",
    "affinity_unit_raw",
    "affinity_value_molar_proposed",
    "affinity_parse_status",
    "affinity_parse_rule",
    "affinity_requires_review",
    "structural_complex_status",
    "notes",
)

LEAKAGE_PROPOSAL_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "source_db",
    "sequence_match_kind",
    "identity",
    "matched_form",
    "matched_exclusion_id",
    "matched_reference_id",
    "matched_evaluation_role",
    "target_alias_match",
    "matched_canonical_target",
    "target_alias_match_type",
    "both_sequence_and_target",
    "requires_review",
    "leakage_exclusion_proposed",
    "comparison_representation",
    "notes",
)

ROUTING_PREVIEW_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "source_db",
    "relationship_status",
    "n_target_relationships_proposed",
    "record_expansion_proposed",
    "target_type_proposed",
    "evidence_level_proposed",
    "leakage_exclusion_proposed",
    "routing_preview",
    "routing_reason",
    "requires_checkpoint2",
    "notes",
)

REGION_HINT_RE: Final[str] = (
    r"(?i)\b(domain|extracellular|fragment|subunit|complex|truncat|"
    r"peptide fragment|runt domain|ectodomain)\b"
)


def empty_row(columns: Sequence[str]) -> dict[str, str]:
    return {column: "" for column in columns}


def fill_row(columns: Sequence[str], values: Mapping[str, str]) -> dict[str, str]:
    return {column: values.get(column, "") or "" for column in columns}


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    write_text_atomic(path, text)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def assert_no_sequence_leak(text: str, *, label: str) -> None:
    if SEQ_LEAK_RE.search(text or ""):
        raise ScientificProposalError(
            f"{label} must not contain biological sequence strings"
        )


def blank_human_fields() -> dict[str, str]:
    return {field: "" for field in HUMAN_FIELDS}


def blank_affinity_human_fields() -> dict[str, str]:
    return {
        field: ""
        for field in (*HUMAN_FIELDS, *AFFINITY_EXTRA_HUMAN_FIELDS)
    }


def assert_human_fields_blank(row: Mapping[str, str], *, label: str) -> None:
    populated = [field for field in HUMAN_FIELDS if (row.get(field) or "").strip()]
    if populated:
        raise ScientificProposalError(
            f"{label} has populated human fields: {', '.join(populated)}"
        )


def assert_affinity_human_fields_blank(row: Mapping[str, str], *, label: str) -> None:
    fields = (*HUMAN_FIELDS, *AFFINITY_EXTRA_HUMAN_FIELDS)
    populated = [field for field in fields if (row.get(field) or "").strip()]
    if populated:
        raise ScientificProposalError(
            f"{label} has populated affinity human fields: {', '.join(populated)}"
        )


def assert_combined_canonical_empty(row: Mapping[str, str]) -> None:
    for field in CANONICAL_FIELDS_MUST_STAY_EMPTY:
        if (row.get(field) or "").strip():
            raise ScientificProposalError(
                f"Combined input canonical field {field} is populated"
            )


def split_pipe(value: str) -> list[str]:
    return [item for item in (value or "").split("|") if item]


__all__ = [
    "AFFINITY_DECISION_VOCAB",
    "AFFINITY_EXTRA_HUMAN_FIELDS",
    "AFFINITY_QUALIFIER_VOCAB",
    "AFFINITY_RANGE_STATUS_VOCAB",
    "AFFINITY_SCALAR_TRANSFORM_RULES",
    "AFFINITY_TRANSFORM_RULE_VOCAB",
    "AFFINITY_TYPE_VOCAB",
    "CANONICAL_FIELDS_MUST_STAY_EMPTY",
    "CONFIRM_AFFINITY_SCALAR",
    "ENRICHED_DICTIONARY_COLUMNS",
    "EVIDENCE_AFFINITY_COLUMNS",
    "EVIDENCE_DECISION_VOCAB",
    "EVIDENCE_LEVELS",
    "EVIDENCE_SCORE_BY_LEVEL",
    "EVIDENCE_TYPE_BY_LEVEL",
    "EXCLUDE_NON_AFFINITY",
    "HUMAN_FIELDS",
    "INACTIVE_TARGET_DECISION",
    "LEAKAGE_DECISION_VOCAB",
    "LEAKAGE_PROPOSAL_COLUMNS",
    "MANUAL_DECISION_VOCAB",
    "NON_AFFINITY_REASON_VOCAB",
    "REGION_HINT_RE",
    "RELATIONSHIP_DECISION_VOCAB",
    "RELATIONSHIP_SCIENTIFIC_COLUMNS",
    "RETAIN_AFFINITY_RAW",
    "ROUTING_PREVIEW_COLUMNS",
    "ROUTING_VOCAB",
    "ScientificProposalError",
    "TARGET_DECISION_VOCAB",
    "TARGET_FAMILY_VOCAB",
    "TARGET_TYPE_VOCAB",
    "alias_candidate_key",
    "assert_combined_canonical_empty",
    "assert_affinity_human_fields_blank",
    "assert_human_fields_blank",
    "assert_no_sequence_leak",
    "blank_affinity_human_fields",
    "blank_human_fields",
    "bool_token",
    "empty_row",
    "fill_row",
    "join_unique",
    "primary_match_key",
    "split_pipe",
    "write_json_atomic",
    "write_text_atomic",
]

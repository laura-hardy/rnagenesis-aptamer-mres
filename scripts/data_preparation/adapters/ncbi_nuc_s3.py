"""NCBI Nucleotide S3 adapter: technical/source-object eligibility.

Consumes S2 canonical rows, S2 QC, the GenBank sidecar, and unapplied
known-motif proposals. Assigns exactly one provisional accept/park/reject
route per record. Does not infer molecule type from alphabet, apply trims,
repair sequences, extract targets, score evidence, apply leakage, or
deduplicate against ENA.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Mapping, Sequence

from common.corpus_schema import S3_FORBIDDEN_FIELDS, validate_s3_record
from common.eligibility import (
    CHECKPOINT_STATUS_PENDING,
    EligibilityDecision,
    EligibilityPolicy,
    EligibilityReason,
    EligibilityResult,
    ManualReviewPriority,
    build_eligibility_result,
    format_reasons,
    parse_qc_flags,
)

DECISION_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "target_name_raw",
    "proposed_decision",
    "primary_reason",
    "secondary_reasons",
    "primary_route",
    "manual_review_required",
    "manual_review_priority",
    "review_batch",
    "checkpoint_review_reasons",
    "checkpoint_status",
    "molecule_type",
    "chemistry",
    "alphabet_as_reported",
    "t_to_u_applied",
    "sequence_length_full",
    "sequence_length_core",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "source_object_class",
    "primer_associated",
    "cdna_template_associated",
    "transcription_template",
    "poly_a_fragment",
    "possible_non_aptamer_source_object",
    "qc_flags",
    "constant_proposal_ids",
    "constant_proposal_sources",
    "notes",
)

REASON_COUNT_COLUMNS: Final[tuple[str, ...]] = (
    "proposed_decision",
    "primary_reason",
    "record_count",
)

REJECTION_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "source_db",
    "source_dataset",
    "native_id",
    "sequence_raw",
    "target_name_raw",
    "stage",
    "rejection_reason",
    "rejection_detail",
)

PARK_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "proposed_decision",
    "park_reason",
    "secondary_reasons",
    "manual_review_required",
    "review_batch",
    "molecule_type",
    "chemistry",
    "alphabet_as_reported",
    "sequence_length_core",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "source_object_class",
    "qc_flags",
)

LOCAL_DETAIL_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "target_name_raw",
    "publication",
    "proposed_decision",
    "primary_reason",
    "secondary_reasons",
    "primary_route",
    "manual_review_required",
    "manual_review_priority",
    "review_batch",
    "checkpoint_review_reasons",
    "checkpoint_status",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "molecule_type",
    "chemistry",
    "alphabet_as_reported",
    "t_to_u_applied",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "detected_constant_5p",
    "detected_constant_3p",
    "source_object_class",
    "primer_associated",
    "cdna_template_associated",
    "transcription_template",
    "poly_a_fragment",
    "possible_non_aptamer_source_object",
    "qc_flags",
    "constant_proposal_ids",
    "constant_proposal_sources",
    "notes",
    "manual_decision",
    "manual_sequence_corrected",
    "manual_target_corrected",
    "manual_molecule_type_override",
    "manual_chemistry_override",
    "manual_trim_action",
    "manual_trim_5p_nt",
    "manual_trim_3p_nt",
    "manual_trim_group_override",
    "manual_notes",
)

DEFAULT_NCBI_NUC_BATCHES: Final[tuple[str, ...]] = (
    "01_judgement_dependent_technical",
    "02_molecule_type_unresolved",
    "03_construct_or_known_motif",
    "04_length_boundary",
    "05_random_kept_audit",
)

GAP_CHARACTERS: Final[frozenset[str]] = frozenset({"-", "."})
APPROVED_RNA_ACCESSIONS: Final[frozenset[str]] = frozenset(
    {"U34759", "U37124", "U37123", "AF083271", "BD161067"}
)
APPROVED_DNA_ACCESSIONS: Final[frozenset[str]] = frozenset({"QT662269"})

REJECTION_STAGE: Final[str] = "S3"

PRIMARY_ROUTE_REJECT: Final[str] = "technical_reject"
PRIMARY_ROUTE_MOLECULE: Final[str] = "parked_molecule_unresolved"
PRIMARY_ROUTE_ELIGIBLE: Final[str] = "technically_eligible"

PLAN_REJECTION_REASONS: Final[frozenset[str]] = frozenset(
    {
        "missing_sequence",
        "missing_target",
        "length_out_of_range",
        "ambiguous_bases",
        "invalid_alphabet",
        "mixed_T_and_U",
        "alignment_gaps",
        "truncated_sequence",
        "primer_like",
        "library_template",
        "ssdna_parked",
        "non_protein_target_parked",
        "non_nucleic_acid_molecule",
        "non_aptamer_source_object",
        "no_binding_evidence",
        "evidence_below_threshold",
        "leakage_excluded",
        "duplicate",
        "target_cap_subsample",
        "manual_reject",
    }
)

DIAGNOSTIC_REASONS: Final[frozenset[EligibilityReason]] = frozenset(
    {
        EligibilityReason.MEDIUM_CONFIDENCE_TRIM,
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
        EligibilityReason.TRIM_COMBINED_EXCEEDS_40PCT,
        EligibilityReason.TRIM_PUSHED_LENGTH_OUT_OF_RANGE,
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED,
        EligibilityReason.RANDOM_ACCEPT_AUDIT,
        EligibilityReason.CONSTANT_REGION_PROPOSAL,
        EligibilityReason.KNOWN_MOTIF_PROPOSAL,
    }
)

JUDGEMENT_DEPENDENT_REASONS: Final[frozenset[EligibilityReason]] = frozenset(
    {
        EligibilityReason.PRIMER_LIKE,
        EligibilityReason.NON_APTAMER_SOURCE_OBJECT,
        EligibilityReason.ALIGNMENT_GAPS,
        EligibilityReason.MIXED_T_AND_U,
        EligibilityReason.INVALID_ALPHABET,
    }
)

REVIEW_REASON_JUDGEMENT: Final[str] = "judgement_dependent_technical"
REVIEW_REASON_MOLECULE: Final[str] = "molecule_type_unresolved"
REVIEW_REASON_CONSTRUCT: Final[str] = "construct_source_object"
REVIEW_REASON_AMBIGUOUS: Final[str] = "ambiguous_bases"
REVIEW_REASON_CONSTANT: Final[str] = "constant_region_proposal"
REVIEW_REASON_BOUNDARY: Final[str] = "length_boundary"
REVIEW_REASON_RANDOM: Final[str] = "random_kept_audit"


class NcbiNucS3Error(ValueError):
    """Hard failure during NCBI Nucleotide S3 eligibility classification."""


@dataclass(frozen=True)
class NcbiNucS3RowResult:
    """Canonical S3 row plus decision/rejection/park payloads for one record."""

    canonical: dict[str, str]
    decision: dict[str, str]
    eligibility: EligibilityResult
    rejection_row: dict[str, str] | None = None
    park_row: dict[str, str] | None = None
    primary_route: str = ""


@dataclass
class NcbiNucS3Stats:
    """Aggregate S3 counts (no sequences or row identifiers)."""

    s2_rows: int = 0
    s3_rows: int = 0
    unique_record_ids: int = 0
    unique_native_ids: int = 0
    order_preserved: bool = False
    decision_counts: dict[str, int] = field(default_factory=dict)
    primary_reason_counts: dict[str, int] = field(default_factory=dict)
    primary_route_counts: dict[str, int] = field(default_factory=dict)
    review_priority_counts: dict[str, int] = field(default_factory=dict)
    review_batch_counts: dict[str, int] = field(default_factory=dict)
    checkpoint_review_reason_counts: dict[str, int] = field(default_factory=dict)
    secondary_reason_counts: dict[str, int] = field(default_factory=dict)
    manual_review_required_true_count: int = 0
    manual_review_required_false_count: int = 0
    missing_sequence_count: int = 0
    mixed_t_u_count: int = 0
    ambiguous_bases_count: int = 0
    invalid_alphabet_count: int = 0
    alignment_gaps_count: int = 0
    length_out_of_range_count: int = 0
    primer_like_count: int = 0
    non_aptamer_source_object_count: int = 0
    molecule_type_unresolved_count: int = 0
    technically_eligible_rna_count: int = 0
    trim_construct_unresolved_count: int = 0
    known_motif_proposal_count: int = 0
    applied_trims: int = 0
    core_equals_full: int = 0
    nonempty_target_name_raw: int = 0
    nonempty_s4_fields: int = 0
    t_to_u_applied_count: int = 0
    multiple_reasons_count: int = 0
    random_accept_audit_count: int = 0
    random_accept_audit_pool_size: int = 0
    random_accept_audit_shortfall: int = 0
    boundary_review_count: int = 0
    judgement_dependent_review_count: int = 0
    molecule_review_count: int = 0
    construct_review_count: int = 0
    unique_checkpoint_review_records: int = 0
    molecule_type_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    alphabet_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() == "true"


def _parse_length(value: str, *, record_id: str, field_name: str) -> int | None:
    text = (value or "").strip()
    if text == "":
        return None
    try:
        parsed = int(text)
    except ValueError as exc:
        raise NcbiNucS3Error(
            f"{field_name} must be an integer for {record_id!r}; got {value!r}"
        ) from exc
    if parsed < 0:
        raise NcbiNucS3Error(f"{field_name} must be non-negative for {record_id!r}")
    return parsed


def _has_alignment_gaps(sequence: str) -> bool:
    return any(char in GAP_CHARACTERS for char in sequence)


def actual_core_length(canonical: Mapping[str, str]) -> int | None:
    return _parse_length(
        canonical.get("sequence_length_core", ""),
        record_id=canonical.get("record_id", ""),
        field_name="sequence_length_core",
    )


def read_constant_proposals(path: Path) -> list[dict[str, str]]:
    """Read S2 known-motif proposals. Header-only files are valid empty input.

    NCBI S2 proposal tables use ``experiment_group_id`` rather than
    ``record_id``. Missing ``record_id`` is filled from that field.
    """
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise NcbiNucS3Error(f"constant proposals CSV has no header: {path.name}")
        rows: list[dict[str, str]] = []
        for row in reader:
            cleaned = {key: ("" if value is None else value) for key, value in row.items()}
            if not cleaned.get("record_id"):
                cleaned["record_id"] = cleaned.get("experiment_group_id", "")
            rows.append(cleaned)
    return rows


def index_constant_proposals(
    proposals: Sequence[Mapping[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Index unapplied proposals by record_id. Never applies them."""
    attached: dict[str, list[dict[str, str]]] = {}
    for row in proposals:
        if _truthy(row.get("applied", "false")):
            raise NcbiNucS3Error("ncbi_nuc S3 must not receive applied proposals")
        record_id = row.get("record_id") or ""
        if not record_id:
            continue
        attached.setdefault(record_id, []).append(dict(row))
    return attached


def _collect_reasons(
    *,
    canonical: Mapping[str, str],
    s2_qc: Mapping[str, str],
    flags: frozenset[str],
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]],
) -> list[EligibilityReason]:
    """Collect applicable reasons. Alphabet never assigns molecule type."""
    reasons: list[EligibilityReason] = []
    record_id = canonical.get("record_id", "")
    sequence_core = canonical.get("sequence_core", "")
    sequence_full = canonical.get("sequence_full", "")
    missing = sequence_core == ""
    if missing:
        reasons.append(EligibilityReason.MISSING_SEQUENCE)

    if "mixed_t_u" in flags:
        reasons.append(EligibilityReason.MIXED_T_AND_U)
    if "ambiguous_base" in flags:
        reasons.append(EligibilityReason.AMBIGUOUS_BASES)

    inspect_seq = sequence_full or sequence_core
    has_gaps = "alignment_gaps" in flags or _has_alignment_gaps(inspect_seq)
    if "alignment_gaps" in flags or has_gaps:
        reasons.append(EligibilityReason.ALIGNMENT_GAPS)
    if "invalid_character" in flags:
        reasons.append(EligibilityReason.INVALID_ALPHABET)

    primer = _truthy(s2_qc.get("primer_associated", "")) or "primer_associated" in flags
    if primer:
        reasons.append(EligibilityReason.PRIMER_LIKE)

    poly_a = _truthy(s2_qc.get("poly_a_fragment", "")) or "poly_a_fragment" in flags
    method_object = (
        _truthy(s2_qc.get("possible_non_aptamer_source_object", ""))
        or "possible_non_aptamer_source_object" in flags
    )
    if poly_a or method_object:
        reasons.append(EligibilityReason.NON_APTAMER_SOURCE_OBJECT)

    molecule = canonical.get("molecule_type", "")
    # molecule_type from S2 is authoritative. alphabet_as_reported is
    # never consulted for routing, including A-only/poly-A RNA-alphabet ties.
    _ = canonical.get("alphabet_as_reported", "")
    if molecule == "unknown" or "molecule_type_unknown" in flags:
        reasons.append(EligibilityReason.MOLECULE_TYPE_UNRESOLVED)

    if not missing:
        core_len = actual_core_length(canonical)
        if (
            core_len is not None
            and not (policy.core_length_min <= core_len <= policy.core_length_max)
        ):
            reasons.append(EligibilityReason.LENGTH_OUT_OF_RANGE)
        if (
            core_len is not None
            and policy.core_length_min <= core_len <= policy.length_boundary_low_max
        ):
            reasons.append(EligibilityReason.LOWER_LENGTH_BOUNDARY)
        if (
            core_len is not None
            and policy.length_boundary_high_min <= core_len <= policy.core_length_max
        ):
            reasons.append(EligibilityReason.UPPER_LENGTH_BOUNDARY)

    cdna = (
        _truthy(s2_qc.get("cdna_template_associated", ""))
        or "cdna_template_associated" in flags
    )
    transcription = (
        _truthy(s2_qc.get("transcription_template", ""))
        or "transcription_template" in flags
    )
    construct_review = (
        _truthy(s2_qc.get("construct_requires_review", ""))
        or "construct_requires_review" in flags
        or cdna
        or transcription
        or primer
        or poly_a
    )
    if construct_review:
        reasons.append(EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED)

    if any(row.get("proposal_source") == "group_consensus" for row in proposals):
        raise NcbiNucS3Error(
            "Group-consensus proposals are forbidden for ncbi_nuc S3"
        )
    has_known_motif = any(
        row.get("proposal_source") == "known_motif" for row in proposals
    ) or "known_promoter_detected" in flags
    if has_known_motif:
        reasons.append(EligibilityReason.KNOWN_MOTIF_PROPOSAL)

    return reasons


def _select_primary(
    applicable: Sequence[EligibilityReason],
    precedence: Sequence[str],
    *,
    diagnostic: frozenset[EligibilityReason],
) -> EligibilityReason | None:
    applicable_set = {
        reason.value for reason in applicable if reason not in diagnostic
    }
    for code in precedence:
        if code in applicable_set:
            return EligibilityReason(code)
    return None


def _decision_for_reason(
    reason: EligibilityReason,
    policy: EligibilityPolicy,
) -> EligibilityDecision:
    mapping = {
        EligibilityReason.MISSING_SEQUENCE: policy.missing_sequence_decision,
        EligibilityReason.PRIMER_LIKE: policy.invalid_sequence_decision,
        EligibilityReason.NON_APTAMER_SOURCE_OBJECT: (
            policy.non_aptamer_source_object_decision
        ),
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED: policy.unknown_molecule_decision,
        EligibilityReason.MIXED_T_AND_U: policy.mixed_t_u_decision,
        EligibilityReason.AMBIGUOUS_BASES: policy.ambiguous_sequence_decision,
        EligibilityReason.ALIGNMENT_GAPS: policy.alignment_gaps_decision,
        EligibilityReason.INVALID_ALPHABET: policy.invalid_sequence_decision,
        EligibilityReason.LENGTH_OUT_OF_RANGE: policy.length_out_of_range_decision,
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA: policy.eligible_rna_decision,
    }
    if reason not in mapping:
        raise NcbiNucS3Error(f"No decision mapping for primary reason {reason.value}")
    return EligibilityDecision(mapping[reason])


def _is_technically_eligible_rna(
    *,
    canonical: Mapping[str, str],
    applicable: Sequence[EligibilityReason],
    policy: EligibilityPolicy,
) -> bool:
    blocking = {
        EligibilityReason.MISSING_SEQUENCE,
        EligibilityReason.PRIMER_LIKE,
        EligibilityReason.NON_APTAMER_SOURCE_OBJECT,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED,
        EligibilityReason.MIXED_T_AND_U,
        EligibilityReason.AMBIGUOUS_BASES,
        EligibilityReason.ALIGNMENT_GAPS,
        EligibilityReason.INVALID_ALPHABET,
        EligibilityReason.LENGTH_OUT_OF_RANGE,
    }
    if set(applicable) & blocking:
        return False
    if canonical.get("molecule_type") != "RNA":
        return False
    if canonical.get("chemistry") != "RNA":
        return False
    sequence_core = canonical.get("sequence_core", "")
    if sequence_core == "":
        return False
    core_len = actual_core_length(canonical)
    if core_len is None:
        return False
    if not (policy.core_length_min <= core_len <= policy.core_length_max):
        return False
    return True


def _primary_route(decision: EligibilityDecision, reason: EligibilityReason) -> str:
    if decision == EligibilityDecision.PROPOSED_REJECT:
        return PRIMARY_ROUTE_REJECT
    if reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED:
        return PRIMARY_ROUTE_MOLECULE
    if (
        decision == EligibilityDecision.PROPOSED_ACCEPT
        and reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    ):
        return PRIMARY_ROUTE_ELIGIBLE
    if decision == EligibilityDecision.PROPOSED_PARK:
        return PRIMARY_ROUTE_MOLECULE
    raise NcbiNucS3Error(
        "Could not assign a closed ncbi_nuc primary route for "
        f"{decision.value}/{reason.value}"
    )


def _checkpoint_review_reasons(
    *,
    all_reasons: Sequence[EligibilityReason],
    s2_qc: Mapping[str, str],
    flags: frozenset[str],
) -> list[str]:
    labels: list[str] = []
    reason_set = set(all_reasons)
    if reason_set & JUDGEMENT_DEPENDENT_REASONS:
        labels.append(REVIEW_REASON_JUDGEMENT)
    if EligibilityReason.MOLECULE_TYPE_UNRESOLVED in reason_set:
        labels.append(REVIEW_REASON_MOLECULE)
    cdna = (
        _truthy(s2_qc.get("cdna_template_associated", ""))
        or "cdna_template_associated" in flags
    )
    transcription = (
        _truthy(s2_qc.get("transcription_template", ""))
        or "transcription_template" in flags
    )
    construct = EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED in reason_set
    if cdna or transcription or construct:
        labels.append(REVIEW_REASON_CONSTRUCT)
    if EligibilityReason.AMBIGUOUS_BASES in reason_set:
        labels.append(REVIEW_REASON_AMBIGUOUS)
    if reason_set & {
        EligibilityReason.CONSTANT_REGION_PROPOSAL,
        EligibilityReason.KNOWN_MOTIF_PROPOSAL,
    }:
        labels.append(REVIEW_REASON_CONSTANT)
    if reason_set & {
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
    }:
        labels.append(REVIEW_REASON_BOUNDARY)
    if EligibilityReason.RANDOM_ACCEPT_AUDIT in reason_set:
        labels.append(REVIEW_REASON_RANDOM)
    return labels


def assign_manual_review_priority(
    *,
    primary_reason: EligibilityReason,
    all_reasons: Sequence[EligibilityReason],
) -> ManualReviewPriority:
    """Assign review priority; never overrides the proposed decision."""
    reason_set = set(all_reasons)
    if primary_reason == EligibilityReason.MISSING_SEQUENCE:
        return ManualReviewPriority.NONE
    if reason_set & JUDGEMENT_DEPENDENT_REASONS:
        return ManualReviewPriority.HIGH
    if EligibilityReason.MOLECULE_TYPE_UNRESOLVED in reason_set:
        return ManualReviewPriority.HIGH
    if reason_set & {
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED,
        EligibilityReason.KNOWN_MOTIF_PROPOSAL,
        EligibilityReason.AMBIGUOUS_BASES,
    }:
        return ManualReviewPriority.HIGH
    if primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA and reason_set & {
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
        EligibilityReason.RANDOM_ACCEPT_AUDIT,
    }:
        return ManualReviewPriority.LOW
    return ManualReviewPriority.NONE


def assign_ncbi_nuc_review_batch(
    *,
    review_reasons: Sequence[str],
    manual_review_required: bool,
) -> str:
    if not manual_review_required:
        return ""
    if REVIEW_REASON_JUDGEMENT in review_reasons:
        return "01_judgement_dependent_technical"
    if REVIEW_REASON_MOLECULE in review_reasons:
        return "02_molecule_type_unresolved"
    if (
        REVIEW_REASON_CONSTRUCT in review_reasons
        or REVIEW_REASON_CONSTANT in review_reasons
        or REVIEW_REASON_AMBIGUOUS in review_reasons
    ):
        return "03_construct_or_known_motif"
    if REVIEW_REASON_BOUNDARY in review_reasons:
        return "04_length_boundary"
    if REVIEW_REASON_RANDOM in review_reasons:
        return "05_random_kept_audit"
    raise NcbiNucS3Error(
        "Review-required record belongs to no ncbi_nuc batch: "
        f"reasons={list(review_reasons)}"
    )


def _proposal_metadata(proposals: Sequence[Mapping[str, str]]) -> dict[str, str]:
    if not proposals:
        return {
            "constant_proposal_ids": "",
            "constant_proposal_sources": "",
        }
    ordered = sorted(proposals, key=lambda row: row.get("proposal_id", ""))
    return {
        "constant_proposal_ids": format_reasons(
            row.get("proposal_id", "") for row in ordered
        ),
        "constant_proposal_sources": format_reasons(
            row.get("proposal_source", "") for row in ordered
        ),
    }


def classify_ncbi_nuc_record(
    s2_record: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]] = (),
) -> NcbiNucS3RowResult:
    """Apply deterministic NCBI Nucleotide S3 technical-eligibility rules."""
    record_id = s2_record["record_id"]
    if record_id != s2_qc.get("record_id", ""):
        raise NcbiNucS3Error("canonical and S2 QC record_id mismatch")
    if record_id != source_metadata.get("record_id", ""):
        raise NcbiNucS3Error("canonical and source-metadata record_id mismatch")

    for field_name in S3_FORBIDDEN_FIELDS:
        if (s2_record.get(field_name) or "") != "":
            raise NcbiNucS3Error(
                f"S3 must not receive populated later-stage field {field_name!r}"
            )
    if (s2_record.get("target_name_raw") or "") != "":
        raise NcbiNucS3Error("ncbi_nuc S3 must leave target_name_raw empty")
    if policy.defer_target_classification is not True:
        raise NcbiNucS3Error("ncbi_nuc S3 must defer target classification")
    if policy.defer_evidence_scoring is not True:
        raise NcbiNucS3Error("ncbi_nuc S3 must defer evidence scoring")
    if policy.defer_leakage_exclusion is not True:
        raise NcbiNucS3Error("ncbi_nuc S3 must defer leakage exclusion")
    if s2_record.get("sequence_core") != s2_record.get("sequence_full"):
        raise NcbiNucS3Error("ncbi_nuc S3 must not receive an applied trim")

    flags = parse_qc_flags(s2_record.get("qc_flags", ""))
    applicable = _collect_reasons(
        canonical=s2_record,
        s2_qc=s2_qc,
        flags=flags,
        policy=policy,
        proposals=proposals,
    )
    eligible = _is_technically_eligible_rna(
        canonical=s2_record,
        applicable=applicable,
        policy=policy,
    )
    if eligible:
        applicable.append(EligibilityReason.TECHNICALLY_ELIGIBLE_RNA)

    primary = _select_primary(
        applicable, policy.decision_precedence, diagnostic=DIAGNOSTIC_REASONS
    )
    if primary is None:
        raise NcbiNucS3Error(
            f"No eligibility reason resolved for record_id={record_id!r}"
        )
    proposed = _decision_for_reason(primary, policy)
    secondary = [reason for reason in applicable if reason != primary]
    priority = assign_manual_review_priority(
        primary_reason=primary,
        all_reasons=applicable,
    )
    eligibility = build_eligibility_result(
        record_id=record_id,
        proposed_decision=proposed,
        primary_reason=primary,
        secondary_reasons=secondary,
        manual_review_priority=priority,
        sequence_leakage_match=None,
        target_leakage_match=None,
        checkpoint_status=CHECKPOINT_STATUS_PENDING,
    )
    review_reasons = _checkpoint_review_reasons(
        all_reasons=eligibility.all_reasons,
        s2_qc=s2_qc,
        flags=flags,
    )
    review_batch = assign_ncbi_nuc_review_batch(
        review_reasons=review_reasons,
        manual_review_required=eligibility.manual_review_required,
    )
    primary_route = _primary_route(proposed, primary)

    if proposed == EligibilityDecision.PROPOSED_ACCEPT:
        if not eligible or primary != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA:
            raise NcbiNucS3Error(
                f"Accept proposed without technical RNA eligibility: {record_id!r}"
            )
        if s2_record.get("molecule_type") != "RNA":
            raise NcbiNucS3Error(f"Non-RNA must not be accepted: {record_id!r}")
        if s2_record.get("chemistry") != "RNA":
            raise NcbiNucS3Error(f"Non-RNA chemistry must not be accepted: {record_id!r}")
        alphabet = s2_record.get("alphabet_as_reported", "")
        if (
            alphabet == "RNA"
            and s2_record.get("molecule_type") != "RNA"
        ):
            raise NcbiNucS3Error(
                "alphabet_as_reported must not authorise RNA acceptance"
            )

    if primary == EligibilityReason.MISSING_SEQUENCE and proposed != (
        EligibilityDecision.PROPOSED_REJECT
    ):
        raise NcbiNucS3Error(f"Missing sequence must be rejected: {record_id!r}")
    if (
        primary == EligibilityReason.MOLECULE_TYPE_UNRESOLVED
        and proposed != EligibilityDecision.PROPOSED_PARK
    ):
        raise NcbiNucS3Error(
            f"Unresolved molecule must be parked: {record_id!r}"
        )
    if eligibility.manual_review_required and not review_batch:
        raise NcbiNucS3Error(f"Review-required record missing review_batch: {record_id!r}")
    if (not eligibility.manual_review_required) and review_batch:
        raise NcbiNucS3Error(f"No-review record must not have a review_batch: {record_id!r}")

    canonical = validate_s3_record(dict(s2_record), s2_record=s2_record)
    if canonical.get("sequence_core") != s2_record.get("sequence_core"):
        raise NcbiNucS3Error("S3 must not alter sequence_core")
    if canonical.get("sequence_full") != s2_record.get("sequence_full"):
        raise NcbiNucS3Error("S3 must not alter sequence_full")
    if canonical.get("sequence_raw") != s2_record.get("sequence_raw"):
        raise NcbiNucS3Error("S3 must not alter sequence_raw")
    if canonical.get("molecule_type") != s2_record.get("molecule_type"):
        raise NcbiNucS3Error("S3 must not alter molecule_type")
    if canonical.get("chemistry") != s2_record.get("chemistry"):
        raise NcbiNucS3Error("S3 must not alter chemistry")
    if canonical.get("t_to_u_applied") != s2_record.get("t_to_u_applied"):
        raise NcbiNucS3Error("S3 must not alter T→U provenance")
    if canonical.get("construct_scope") != s2_record.get("construct_scope"):
        raise NcbiNucS3Error("S3 must not alter construct_scope")
    if canonical.get("target_name_raw") != "":
        raise NcbiNucS3Error("ncbi_nuc S3 must leave target_name_raw empty")

    proposal_meta = _proposal_metadata(proposals)
    decision = _build_decision_row(
        canonical=canonical,
        s2_qc=s2_qc,
        eligibility=eligibility,
        review_batch=review_batch,
        review_reasons=review_reasons,
        primary_route=primary_route,
        proposal_meta=proposal_meta,
    )
    rejection_row = None
    park_row = None
    if proposed == EligibilityDecision.PROPOSED_REJECT:
        rejection_row = _build_rejection_row(canonical=canonical, decision=decision)
    elif proposed == EligibilityDecision.PROPOSED_PARK:
        park_row = _build_park_row(canonical=canonical, decision=decision, s2_qc=s2_qc)

    return NcbiNucS3RowResult(
        canonical=canonical,
        decision=decision,
        eligibility=eligibility,
        rejection_row=rejection_row,
        park_row=park_row,
        primary_route=primary_route,
    )


def _build_decision_row(
    *,
    canonical: Mapping[str, str],
    s2_qc: Mapping[str, str],
    eligibility: EligibilityResult,
    review_batch: str,
    review_reasons: Sequence[str],
    primary_route: str,
    proposal_meta: Mapping[str, str],
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "target_name_raw": canonical["target_name_raw"],
        "proposed_decision": eligibility.proposed_decision.value,
        "primary_reason": eligibility.primary_reason.value,
        "secondary_reasons": format_reasons(eligibility.secondary_reasons),
        "primary_route": primary_route,
        "manual_review_required": (
            "true" if eligibility.manual_review_required else "false"
        ),
        "manual_review_priority": eligibility.manual_review_priority.value,
        "review_batch": review_batch,
        "checkpoint_review_reasons": format_reasons(review_reasons),
        "checkpoint_status": eligibility.checkpoint_status,
        "molecule_type": canonical["molecule_type"],
        "chemistry": canonical.get("chemistry", ""),
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "t_to_u_applied": canonical.get("t_to_u_applied", ""),
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "construct_scope": canonical["construct_scope"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical.get("trim_confidence", ""),
        "source_object_class": s2_qc.get("source_object_class", ""),
        "primer_associated": s2_qc.get("primer_associated", ""),
        "cdna_template_associated": s2_qc.get("cdna_template_associated", ""),
        "transcription_template": s2_qc.get("transcription_template", ""),
        "poly_a_fragment": s2_qc.get("poly_a_fragment", ""),
        "possible_non_aptamer_source_object": s2_qc.get(
            "possible_non_aptamer_source_object", ""
        ),
        "qc_flags": canonical["qc_flags"],
        "constant_proposal_ids": proposal_meta.get("constant_proposal_ids", ""),
        "constant_proposal_sources": proposal_meta.get("constant_proposal_sources", ""),
        "notes": "",
    }


def _build_rejection_row(
    *,
    canonical: Mapping[str, str],
    decision: Mapping[str, str],
) -> dict[str, str]:
    reason = decision["primary_reason"]
    if reason not in PLAN_REJECTION_REASONS:
        raise NcbiNucS3Error(
            f"Rejection reason {reason!r} is not in the plan closed vocabulary"
        )
    detail_parts = [
        part for part in (decision.get("secondary_reasons") or "").split("|") if part
    ]
    return {
        "record_id": canonical["record_id"],
        "source_db": canonical.get("source_db", "ncbi_nuc"),
        "source_dataset": canonical.get("source_dataset", ""),
        "native_id": canonical["native_id"],
        "sequence_raw": canonical.get("sequence_raw", ""),
        "target_name_raw": canonical.get("target_name_raw", ""),
        "stage": REJECTION_STAGE,
        "rejection_reason": reason,
        "rejection_detail": format_reasons(detail_parts),
    }


def _build_park_row(
    *,
    canonical: Mapping[str, str],
    decision: Mapping[str, str],
    s2_qc: Mapping[str, str],
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "proposed_decision": decision["proposed_decision"],
        "park_reason": decision["primary_reason"],
        "secondary_reasons": decision.get("secondary_reasons", ""),
        "manual_review_required": decision.get("manual_review_required", ""),
        "review_batch": decision.get("review_batch", ""),
        "molecule_type": canonical.get("molecule_type", ""),
        "chemistry": canonical.get("chemistry", ""),
        "alphabet_as_reported": canonical.get("alphabet_as_reported", ""),
        "sequence_length_core": canonical.get("sequence_length_core", ""),
        "construct_scope": canonical.get("construct_scope", ""),
        "trim_status": canonical.get("trim_status", ""),
        "trim_confidence": canonical.get("trim_confidence", ""),
        "source_object_class": s2_qc.get("source_object_class", ""),
        "qc_flags": canonical.get("qc_flags", ""),
    }


def build_local_detail_row(
    *,
    canonical: Mapping[str, str],
    s2_qc: Mapping[str, str],
    decision: Mapping[str, str],
) -> dict[str, str]:
    """Build one sequence-bearing local-detail review row."""
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "target_name_raw": canonical.get("target_name_raw", ""),
        "publication": canonical.get("publication", ""),
        "proposed_decision": decision.get("proposed_decision", ""),
        "primary_reason": decision.get("primary_reason", ""),
        "secondary_reasons": decision.get("secondary_reasons", ""),
        "primary_route": decision.get("primary_route", ""),
        "manual_review_required": decision.get("manual_review_required", ""),
        "manual_review_priority": decision.get("manual_review_priority", ""),
        "review_batch": decision.get("review_batch", ""),
        "checkpoint_review_reasons": decision.get("checkpoint_review_reasons", ""),
        "checkpoint_status": decision.get("checkpoint_status", ""),
        "sequence_raw": canonical.get("sequence_raw", ""),
        "sequence_full": canonical.get("sequence_full", ""),
        "sequence_core": canonical.get("sequence_core", ""),
        "sequence_length_full": canonical.get("sequence_length_full", ""),
        "sequence_length_core": canonical.get("sequence_length_core", ""),
        "molecule_type": canonical.get("molecule_type", ""),
        "chemistry": canonical.get("chemistry", ""),
        "alphabet_as_reported": canonical.get("alphabet_as_reported", ""),
        "t_to_u_applied": canonical.get("t_to_u_applied", ""),
        "construct_scope": canonical.get("construct_scope", ""),
        "trim_status": canonical.get("trim_status", ""),
        "trim_confidence": canonical.get("trim_confidence", ""),
        "detected_constant_5p": canonical.get("detected_constant_5p", ""),
        "detected_constant_3p": canonical.get("detected_constant_3p", ""),
        "source_object_class": s2_qc.get("source_object_class", ""),
        "primer_associated": s2_qc.get("primer_associated", ""),
        "cdna_template_associated": s2_qc.get("cdna_template_associated", ""),
        "transcription_template": s2_qc.get("transcription_template", ""),
        "poly_a_fragment": s2_qc.get("poly_a_fragment", ""),
        "possible_non_aptamer_source_object": s2_qc.get(
            "possible_non_aptamer_source_object", ""
        ),
        "qc_flags": canonical.get("qc_flags", ""),
        "constant_proposal_ids": decision.get("constant_proposal_ids", ""),
        "constant_proposal_sources": decision.get("constant_proposal_sources", ""),
        "notes": decision.get("notes", ""),
        "manual_decision": "",
        "manual_sequence_corrected": "",
        "manual_target_corrected": "",
        "manual_molecule_type_override": "",
        "manual_chemistry_override": "",
        "manual_trim_action": "",
        "manual_trim_5p_nt": "",
        "manual_trim_3p_nt": "",
        "manual_trim_group_override": "",
        "manual_notes": "",
    }


def apply_random_accept_audit(
    decision_rows: list[dict[str, str]],
    local_detail_by_id: dict[str, dict[str, str]],
    *,
    seed: int,
    sample_size: int,
) -> tuple[int, int, int]:
    """Mark a seeded sample of technically eligible RNA records.

    Returns ``(selected_count, pool_size, shortfall)``. Never fabricates
    rows when the clean RNA pool is smaller than ``sample_size``.
    """
    if sample_size < 0:
        raise NcbiNucS3Error("random_accept_audit_size must be non-negative")
    candidates = [
        row
        for row in decision_rows
        if row["proposed_decision"] == "proposed_accept"
        and row["primary_reason"] == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value
        and row.get("primary_route") == PRIMARY_ROUTE_ELIGIBLE
        and row.get("molecule_type") == "RNA"
    ]
    candidates.sort(key=lambda row: row["record_id"])
    pool_size = len(candidates)
    take = min(sample_size, pool_size)
    shortfall = max(0, sample_size - pool_size)
    selected_ids: set[str] = set()
    if take:
        rng = random.Random(seed)
        selected_ids = {row["record_id"] for row in rng.sample(candidates, take)}

    for row in decision_rows:
        if row["record_id"] not in selected_ids:
            continue
        extras = [
            part for part in (row.get("secondary_reasons") or "").split("|") if part
        ]
        extras.append(EligibilityReason.RANDOM_ACCEPT_AUDIT.value)
        row["secondary_reasons"] = format_reasons(extras)
        review_reasons = [
            part
            for part in (row.get("checkpoint_review_reasons") or "").split("|")
            if part
        ]
        if REVIEW_REASON_RANDOM not in review_reasons:
            review_reasons.append(REVIEW_REASON_RANDOM)
        row["checkpoint_review_reasons"] = format_reasons(review_reasons)
        row["manual_review_required"] = "true"
        if row.get("manual_review_priority") in {"", "none"}:
            row["manual_review_priority"] = ManualReviewPriority.LOW.value
        if not row.get("review_batch"):
            row["review_batch"] = assign_ncbi_nuc_review_batch(
                review_reasons=review_reasons,
                manual_review_required=True,
            )
        detail = local_detail_by_id.get(row["record_id"])
        if detail is not None:
            detail["secondary_reasons"] = row["secondary_reasons"]
            detail["checkpoint_review_reasons"] = row["checkpoint_review_reasons"]
            detail["manual_review_required"] = "true"
            detail["manual_review_priority"] = row["manual_review_priority"]
            detail["review_batch"] = row["review_batch"]

    return take, pool_size, shortfall


def update_stats_from_row(stats: NcbiNucS3Stats, row: NcbiNucS3RowResult) -> None:
    """Accumulate aggregate counters from one classified row."""
    decision = row.eligibility.proposed_decision.value
    primary = row.eligibility.primary_reason.value
    priority = row.eligibility.manual_review_priority.value
    molecule = row.canonical.get("molecule_type") or "unknown"
    alphabet = row.canonical.get("alphabet_as_reported") or "missing"
    reasons = set(row.eligibility.all_reasons)

    stats.decision_counts[decision] = stats.decision_counts.get(decision, 0) + 1
    stats.primary_reason_counts[primary] = (
        stats.primary_reason_counts.get(primary, 0) + 1
    )
    stats.primary_route_counts[row.primary_route] = (
        stats.primary_route_counts.get(row.primary_route, 0) + 1
    )
    stats.review_priority_counts[priority] = (
        stats.review_priority_counts.get(priority, 0) + 1
    )
    batch = row.decision.get("review_batch") or ""
    if batch:
        stats.review_batch_counts[batch] = stats.review_batch_counts.get(batch, 0) + 1
    if row.eligibility.manual_review_required:
        stats.manual_review_required_true_count += 1
    else:
        stats.manual_review_required_false_count += 1

    if EligibilityReason.MISSING_SEQUENCE in reasons:
        stats.missing_sequence_count += 1
    if EligibilityReason.MIXED_T_AND_U in reasons:
        stats.mixed_t_u_count += 1
    if EligibilityReason.AMBIGUOUS_BASES in reasons:
        stats.ambiguous_bases_count += 1
    if EligibilityReason.INVALID_ALPHABET in reasons:
        stats.invalid_alphabet_count += 1
    if EligibilityReason.ALIGNMENT_GAPS in reasons:
        stats.alignment_gaps_count += 1
    if EligibilityReason.LENGTH_OUT_OF_RANGE in reasons:
        stats.length_out_of_range_count += 1
    if EligibilityReason.PRIMER_LIKE in reasons:
        stats.primer_like_count += 1
    if EligibilityReason.NON_APTAMER_SOURCE_OBJECT in reasons:
        stats.non_aptamer_source_object_count += 1
    if EligibilityReason.MOLECULE_TYPE_UNRESOLVED in reasons:
        stats.molecule_type_unresolved_count += 1
    if EligibilityReason.TECHNICALLY_ELIGIBLE_RNA in reasons:
        stats.technically_eligible_rna_count += 1
    if EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED in reasons:
        stats.trim_construct_unresolved_count += 1
    if EligibilityReason.KNOWN_MOTIF_PROPOSAL in reasons:
        stats.known_motif_proposal_count += 1
    if len(row.eligibility.all_reasons) > 1:
        stats.multiple_reasons_count += 1
    for reason in row.eligibility.secondary_reasons:
        stats.secondary_reason_counts[reason.value] = (
            stats.secondary_reason_counts.get(reason.value, 0) + 1
        )

    if row.canonical.get("t_to_u_applied") == "true":
        stats.t_to_u_applied_count += 1
    if row.canonical.get("sequence_core") == row.canonical.get("sequence_full"):
        stats.core_equals_full += 1
    else:
        stats.applied_trims += 1
    if row.canonical.get("target_name_raw"):
        stats.nonempty_target_name_raw += 1
    if any(row.canonical.get(field) for field in S3_FORBIDDEN_FIELDS):
        stats.nonempty_s4_fields += 1

    mol_map = stats.molecule_type_by_decision.setdefault(decision, {})
    mol_map[molecule] = mol_map.get(molecule, 0) + 1
    alph_map = stats.alphabet_by_decision.setdefault(decision, {})
    alph_map[alphabet] = alph_map.get(alphabet, 0) + 1


def refresh_stats_after_audit(
    stats: NcbiNucS3Stats, decision_rows: Sequence[Mapping[str, str]]
) -> None:
    """Recompute review-dependent counters after the random-accept audit."""
    stats.manual_review_required_true_count = 0
    stats.manual_review_required_false_count = 0
    stats.review_batch_counts = {}
    stats.review_priority_counts = {}
    stats.checkpoint_review_reason_counts = {}
    stats.random_accept_audit_count = 0
    stats.boundary_review_count = 0
    stats.judgement_dependent_review_count = 0
    stats.molecule_review_count = 0
    stats.construct_review_count = 0
    stats.unique_checkpoint_review_records = 0
    for row in decision_rows:
        required = row.get("manual_review_required") == "true"
        if required:
            stats.manual_review_required_true_count += 1
            stats.unique_checkpoint_review_records += 1
        else:
            stats.manual_review_required_false_count += 1
        batch = row.get("review_batch") or ""
        if batch:
            stats.review_batch_counts[batch] = (
                stats.review_batch_counts.get(batch, 0) + 1
            )
        priority = row.get("manual_review_priority") or "none"
        stats.review_priority_counts[priority] = (
            stats.review_priority_counts.get(priority, 0) + 1
        )
        for reason in (row.get("checkpoint_review_reasons") or "").split("|"):
            if not reason:
                continue
            stats.checkpoint_review_reason_counts[reason] = (
                stats.checkpoint_review_reason_counts.get(reason, 0) + 1
            )
        secondaries = {
            part for part in (row.get("secondary_reasons") or "").split("|") if part
        }
        if EligibilityReason.RANDOM_ACCEPT_AUDIT.value in secondaries:
            stats.random_accept_audit_count += 1
        review_set = {
            part
            for part in (row.get("checkpoint_review_reasons") or "").split("|")
            if part
        }
        if REVIEW_REASON_BOUNDARY in review_set:
            stats.boundary_review_count += 1
        if REVIEW_REASON_JUDGEMENT in review_set:
            stats.judgement_dependent_review_count += 1
        if REVIEW_REASON_MOLECULE in review_set:
            stats.molecule_review_count += 1
        if REVIEW_REASON_CONSTRUCT in review_set or REVIEW_REASON_CONSTANT in review_set:
            stats.construct_review_count += 1


def assert_ncbi_nuc_accept_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    """Hard-fail if any proposed accept violates RNA technical eligibility."""
    for row in decision_rows:
        if row["proposed_decision"] != "proposed_accept":
            continue
        if row["molecule_type"] != "RNA":
            raise NcbiNucS3Error("proposed accept contains non-RNA molecule_type")
        if row.get("chemistry") != "RNA":
            raise NcbiNucS3Error("proposed accept contains non-RNA chemistry")
        if row["primary_reason"] != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value:
            raise NcbiNucS3Error(
                "proposed accept primary_reason must be technically_eligible_rna"
            )
        if row.get("primary_route") != PRIMARY_ROUTE_ELIGIBLE:
            raise NcbiNucS3Error("proposed accept primary_route mismatch")
        flags = parse_qc_flags(row.get("qc_flags", ""))
        if flags & {"invalid_character", "ambiguous_base", "mixed_t_u", "alignment_gaps"}:
            raise NcbiNucS3Error("proposed accept has unresolved alphabet/gap QC flags")
        try:
            core_len = int(row["sequence_length_core"])
        except ValueError as exc:
            raise NcbiNucS3Error(
                "proposed accept has non-integer sequence_length_core"
            ) from exc
        if not (20 <= core_len <= 100):
            raise NcbiNucS3Error("proposed accept core length outside 20–100 nt policy")
        if row.get("target_name_raw"):
            raise NcbiNucS3Error("proposed accept must not populate target_name_raw")


def assert_ncbi_nuc_reject_park_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    seen: dict[str, str] = {}
    for row in decision_rows:
        record_id = row["record_id"]
        route = row.get("primary_route", "")
        if record_id in seen:
            raise NcbiNucS3Error(f"Duplicate decision record_id {record_id!r}")
        seen[record_id] = route
        decision = row["proposed_decision"]
        primary = row["primary_reason"]
        if primary == "missing_sequence" and decision != "proposed_reject":
            raise NcbiNucS3Error("missing sequence must never be accepted or parked")
        if primary == "primer_like" and decision != "proposed_reject":
            raise NcbiNucS3Error("primer_like must be a proposed reject")
        if primary == "non_aptamer_source_object" and decision != "proposed_reject":
            raise NcbiNucS3Error("non_aptamer_source_object must be a proposed reject")
        if primary == "molecule_type_unresolved" and decision != "proposed_park":
            raise NcbiNucS3Error("molecule_type_unresolved must be a park")
        if primary == "length_out_of_range" and decision == "proposed_accept":
            raise NcbiNucS3Error("length_out_of_range must never be accepted")
        if (
            row.get("molecule_type") == "unknown"
            and decision == "proposed_accept"
        ):
            raise NcbiNucS3Error("unknown molecule must never be accepted")
        if (
            row.get("alphabet_as_reported") == "RNA"
            and row.get("molecule_type") != "RNA"
            and decision == "proposed_accept"
        ):
            raise NcbiNucS3Error("alphabet_as_reported must not resolve molecule type")
        if row["checkpoint_status"] != CHECKPOINT_STATUS_PENDING:
            raise NcbiNucS3Error("Unexpected checkpoint_status at S3")
        if decision not in {
            "proposed_accept",
            "proposed_park",
            "proposed_reject",
        }:
            raise NcbiNucS3Error(f"Unknown proposed_decision {decision!r}")
        if route not in {
            PRIMARY_ROUTE_REJECT,
            PRIMARY_ROUTE_MOLECULE,
            PRIMARY_ROUTE_ELIGIBLE,
        }:
            raise NcbiNucS3Error(f"Unknown primary_route {route!r}")
        required = row.get("manual_review_required")
        if required not in {"true", "false"}:
            raise NcbiNucS3Error("manual_review_required must be lowercase true/false")
        if required == "true" and not row.get("review_batch"):
            raise NcbiNucS3Error("Active review row missing review_batch")
        if required == "false" and row.get("review_batch"):
            raise NcbiNucS3Error("Mechanical row must not carry a review_batch")
        for forbidden in S3_FORBIDDEN_FIELDS:
            if forbidden in row and row[forbidden]:
                raise NcbiNucS3Error(
                    f"S3 decision sidecar must not populate {forbidden}"
                )
        if row.get("manual_decision"):
            raise NcbiNucS3Error("S3 must not pre-fill a human manual_decision")
        for field_name in (
            "manual_sequence_corrected",
            "manual_molecule_type_override",
            "manual_chemistry_override",
            "manual_trim_action",
        ):
            if row.get(field_name):
                raise NcbiNucS3Error(f"S3 must not pre-fill {field_name}")

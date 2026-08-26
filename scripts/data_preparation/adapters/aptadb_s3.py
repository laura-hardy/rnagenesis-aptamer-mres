"""AptaDB S3 adapter: technical eligibility, parking, and CHECKPOINT-1.

Consumes S2 canonical rows, S2 QC, the AptaDB source-metadata sidecar, S2
constant-region proposals, and the S1 unlinked-aptamer table. Assigns exactly
one primary interaction-stream route per record. Does not apply trims, repair
sequences, canonicalise targets, score evidence, or apply leakage exclusions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Final, Mapping, Sequence

from adapters.aptadb import (
    TARGET_CHEMISTRY_NON_PROTEIN,
    TARGET_CHEMISTRY_PROTEIN,
)
from common.constant_region_inference import build_group_inference_key
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
    "aptamer_name",
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
    "aptadb_target_chemistry",
    "alphabet_as_reported",
    "sequence_length_full",
    "sequence_length_core",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "qc_flags",
    "constant_proposal_ids",
    "constant_proposal_sources",
    "constant_proposal_sides",
    "constant_group_id",
    "constant_records_in_group",
    "constant_support",
    "constant_proposed_trim_length",
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
    "aptadb_target_chemistry",
    "sequence_length_core",
    "trim_status",
    "trim_confidence",
    "qc_flags",
)

LOCAL_DETAIL_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "aptamer_name",
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
    "aptadb_target_chemistry",
    "alphabet_as_reported",
    "t_to_u_applied",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "detected_constant_5p",
    "detected_constant_3p",
    "qc_flags",
    "constant_proposal_ids",
    "constant_proposal_sources",
    "constant_proposal_sides",
    "constant_group_id",
    "constant_records_in_group",
    "constant_support",
    "constant_proposed_trim_length",
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

DEFAULT_APTADB_BATCHES: Final[tuple[str, ...]] = (
    "01_judgement_dependent_technical",
    "02_constant_region_proposal",
    "03_length_boundary",
    "04_random_kept_audit",
)

ALLOWED_MANUAL_DECISIONS: Final[frozenset[str]] = frozenset({"keep", "drop", "edit", ""})

GAP_CHARACTERS: Final[frozenset[str]] = frozenset({"-", "."})
NUCLEOTIDE_OR_AMBIGUITY: Final[frozenset[str]] = frozenset("ACGTUNRYWSMKHBVD")
EXPLICIT_DNA_TYPES: Final[frozenset[str]] = frozenset({"ssDNA", "DNA"})
PROTEIN_TARGET_CHEMISTRY: Final[str] = TARGET_CHEMISTRY_PROTEIN
NON_PROTEIN_TARGET_CHEMISTRY: Final[frozenset[str]] = TARGET_CHEMISTRY_NON_PROTEIN
ALLOWED_TARGET_CHEMISTRY: Final[frozenset[str]] = frozenset(
    {PROTEIN_TARGET_CHEMISTRY} | NON_PROTEIN_TARGET_CHEMISTRY
)

UNLINKED_RECORD_ID_PREFIX: Final[str] = "aptadb:unlinked:"
UNLINKED_REJECTION_STAGE: Final[str] = "S3_source_reconciliation"
INTERACTION_REJECTION_STAGE: Final[str] = "S3"

PRIMARY_ROUTE_REJECT: Final[str] = "technical_reject"
PRIMARY_ROUTE_SSDNA: Final[str] = "parked_ssdna"
PRIMARY_ROUTE_NON_PROTEIN: Final[str] = "parked_non_protein"
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
        EligibilityReason.ALIGNMENT_GAPS,
        EligibilityReason.MIXED_T_AND_U,
        EligibilityReason.INVALID_ALPHABET,
        EligibilityReason.PRIMER_LIKE,
        EligibilityReason.LIBRARY_TEMPLATE,
        EligibilityReason.TRUNCATED_SEQUENCE,
        EligibilityReason.TRIM_PUSHED_LENGTH_OUT_OF_RANGE,
    }
)

REVIEW_REASON_JUDGEMENT: Final[str] = "judgement_dependent_technical"
REVIEW_REASON_CONSTANT: Final[str] = "constant_region_proposal"
REVIEW_REASON_BOUNDARY: Final[str] = "length_boundary"
REVIEW_REASON_RANDOM: Final[str] = "random_kept_audit"

GROUPING_MODE_DEFAULT: Final[str] = "target_name_raw_plus_publication"


class AptaDBS3Error(ValueError):
    """Hard failure during AptaDB S3 eligibility classification."""


@dataclass(frozen=True)
class AptaDBS3RowResult:
    """Canonical S3 row plus decision/rejection/park payloads for one record."""

    canonical: dict[str, str]
    decision: dict[str, str]
    eligibility: EligibilityResult
    rejection_row: dict[str, str] | None = None
    park_row: dict[str, str] | None = None
    primary_route: str = ""


@dataclass
class AptaDBS3Stats:
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
    manual_review_required_true_count: int = 0
    manual_review_required_false_count: int = 0
    missing_sequence_excluded_from_review_count: int = 0
    missing_sequence_count: int = 0
    mixed_t_u_count: int = 0
    ambiguous_bases_count: int = 0
    invalid_alphabet_count: int = 0
    alignment_gaps_count: int = 0
    length_out_of_range_count: int = 0
    primer_like_count: int = 0
    library_template_count: int = 0
    truncated_sequence_count: int = 0
    ssdna_parked_count: int = 0
    non_protein_parked_count: int = 0
    technically_eligible_rna_count: int = 0
    source_ssdna_before_technical: int = 0
    technically_rejected_ssdna: int = 0
    rna_non_protein_before_technical: int = 0
    technically_rejected_rna_non_protein: int = 0
    rna_protein_before_technical: int = 0
    technically_rejected_rna_protein: int = 0
    unlinked_aptamers: int = 0
    unlinked_missing_target_rejects: int = 0
    unlinked_dna: int = 0
    unlinked_rna: int = 0
    constant_proposal_record_count: int = 0
    known_motif_proposal_record_count: int = 0
    boundary_low_count: int = 0
    boundary_high_count: int = 0
    boundary_review_count: int = 0
    judgement_dependent_review_count: int = 0
    constant_review_count: int = 0
    random_accept_audit_count: int = 0
    random_accept_audit_pool_size: int = 0
    random_accept_audit_shortfall: int = 0
    unique_checkpoint_review_records: int = 0
    multiple_reasons_count: int = 0
    molecule_type_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    alphabet_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    core_length_bucket_by_decision: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    target_chemistry_by_route: dict[str, dict[str, int]] = field(default_factory=dict)
    sequence_leakage_count: int = 0
    target_leakage_count: int = 0
    both_leakage_count: int = 0


def unlinked_rejection_record_id(apta_index: str) -> str:
    """Stable source-level identity for an unlinked AptaDB aptamer row."""
    text = (apta_index or "").strip()
    if not text:
        raise AptaDBS3Error("Unlinked aptamer is missing Apta_index")
    return f"{UNLINKED_RECORD_ID_PREFIX}{text}"


def _parse_length(raw: str, *, record_id: str, field_name: str) -> int | None:
    text = (raw or "").strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise AptaDBS3Error(
            f"Non-integer {field_name} for {record_id!r}"
        ) from exc


def _core_length_bucket(length: int | None) -> str:
    if length is None:
        return "missing"
    if length < 20:
        return "below_20"
    if length <= 100:
        return "20_to_100"
    if length <= 200:
        return "101_to_200"
    return "above_200"


def _has_alignment_gaps(sequence: str) -> bool:
    return any(ch in sequence for ch in GAP_CHARACTERS)


def _has_non_gap_invalid(sequence: str) -> bool:
    return any(
        ch not in NUCLEOTIDE_OR_AMBIGUITY and ch not in GAP_CHARACTERS
        for ch in sequence.upper()
    )


def _target_chemistry(source_metadata: Mapping[str, str]) -> str:
    value = (source_metadata.get("aptadb_target_chemistry") or "").strip()
    if value not in ALLOWED_TARGET_CHEMISTRY:
        raise AptaDBS3Error(
            "AptaDB S3 requires explicit Target chemistry "
            f"(Protein/Molecule/Cell/Other); got {value!r}"
        )
    return value


def _aptamer_name(s2_qc: Mapping[str, str], source_metadata: Mapping[str, str]) -> str:
    return (
        s2_qc.get("aptamer_name")
        or source_metadata.get("aptadb_aptamer_description")
        or ""
    )


def index_constant_proposals(
    canonical_rows: Sequence[Mapping[str, str]],
    proposals: Sequence[Mapping[str, str]],
    *,
    grouping_mode: str = GROUPING_MODE_DEFAULT,
) -> dict[str, list[dict[str, str]]]:
    """Map canonical record_id values to unapplied S2 proposal rows."""
    by_group: dict[str, list[dict[str, str]]] = {}
    by_record: dict[str, list[dict[str, str]]] = {}
    for proposal in proposals:
        row = {key: ("" if value is None else str(value)) for key, value in proposal.items()}
        source = row.get("proposal_source", "")
        if source == "group_consensus":
            group_id = row.get("experiment_group_id", "")
            if group_id:
                by_group.setdefault(group_id, []).append(row)
        elif source == "known_motif":
            record_id = row.get("experiment_group_id") or ""
            if record_id:
                by_record.setdefault(record_id, []).append(row)

    attached: dict[str, list[dict[str, str]]] = {}
    for canonical in canonical_rows:
        record_id = canonical["record_id"]
        matches: list[dict[str, str]] = list(by_record.get(record_id, ()))
        group_id = build_group_inference_key(
            source_db=canonical.get("source_db") or "aptadb",
            grouping_mode=grouping_mode,
            experiment_group_id=canonical.get("experiment_group_id") or None,
            target_name_raw=canonical.get("target_name_raw") or None,
            publication=canonical.get("publication") or None,
            pubmed_id=canonical.get("pubmed_id") or None,
        )
        if group_id is not None:
            matches.extend(by_group.get(group_id, ()))
        if matches:
            attached[record_id] = matches
    return attached


def _collect_reasons(
    *,
    canonical: Mapping[str, str],
    flags: frozenset[str],
    policy: EligibilityPolicy,
    target_chemistry: str,
    proposals: Sequence[Mapping[str, str]],
) -> list[EligibilityReason]:
    """Collect every applicable reason without applying precedence."""
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
    if "alignment_gaps" in flags or (has_gaps and "invalid_character" in flags):
        reasons.append(EligibilityReason.ALIGNMENT_GAPS)
    if "invalid_character" in flags and (
        _has_non_gap_invalid(inspect_seq) or not has_gaps
    ):
        reasons.append(EligibilityReason.INVALID_ALPHABET)

    if "primer_like" in flags:
        reasons.append(EligibilityReason.PRIMER_LIKE)
    if "library_template" in flags:
        reasons.append(EligibilityReason.LIBRARY_TEMPLATE)
    if "truncated_sequence" in flags:
        reasons.append(EligibilityReason.TRUNCATED_SEQUENCE)

    core_len = _parse_length(
        canonical.get("sequence_length_core", ""),
        record_id=record_id,
        field_name="sequence_length_core",
    )
    full_len = _parse_length(
        canonical.get("sequence_length_full", ""),
        record_id=record_id,
        field_name="sequence_length_full",
    )
    if (
        not missing
        and core_len is not None
        and not (policy.core_length_min <= core_len <= policy.core_length_max)
    ):
        reasons.append(EligibilityReason.LENGTH_OUT_OF_RANGE)
        if (
            full_len is not None
            and policy.core_length_min <= full_len <= policy.core_length_max
        ):
            reasons.append(EligibilityReason.TRIM_PUSHED_LENGTH_OUT_OF_RANGE)

    molecule = canonical.get("molecule_type", "")
    if molecule in EXPLICIT_DNA_TYPES:
        reasons.append(EligibilityReason.SSDNA_PARKED)
    elif molecule == "RNA":
        if target_chemistry in NON_PROTEIN_TARGET_CHEMISTRY:
            reasons.append(EligibilityReason.NON_PROTEIN_TARGET_PARKED)
    elif molecule == "unknown" or "molecule_type_unknown" in flags:
        raise AptaDBS3Error(
            f"AptaDB S3 does not accept unresolved molecule_type for {record_id!r}"
        )
    else:
        raise AptaDBS3Error(
            f"Unrecognised AptaDB molecule_type {molecule!r} for {record_id!r}"
        )

    trim_unresolved = (
        "trim_requires_review" in flags
        or canonical.get("trim_status") == "constants_suspected_unresolved"
        or "known_promoter_detected" in flags
    )
    if trim_unresolved:
        reasons.append(EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED)

    if (
        not missing
        and core_len is not None
        and policy.core_length_min <= core_len <= policy.length_boundary_low_max
    ):
        reasons.append(EligibilityReason.LOWER_LENGTH_BOUNDARY)
    if (
        not missing
        and core_len is not None
        and policy.length_boundary_high_min <= core_len <= policy.core_length_max
    ):
        reasons.append(EligibilityReason.UPPER_LENGTH_BOUNDARY)

    if any(row.get("proposal_source") == "group_consensus" for row in proposals):
        reasons.append(EligibilityReason.CONSTANT_REGION_PROPOSAL)
    if any(row.get("proposal_source") == "known_motif" for row in proposals):
        reasons.append(EligibilityReason.KNOWN_MOTIF_PROPOSAL)
    elif "known_promoter_detected" in flags:
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
        EligibilityReason.MIXED_T_AND_U: policy.mixed_t_u_decision,
        EligibilityReason.AMBIGUOUS_BASES: policy.ambiguous_sequence_decision,
        EligibilityReason.ALIGNMENT_GAPS: policy.alignment_gaps_decision,
        EligibilityReason.INVALID_ALPHABET: policy.invalid_sequence_decision,
        EligibilityReason.TRUNCATED_SEQUENCE: policy.invalid_sequence_decision,
        EligibilityReason.PRIMER_LIKE: policy.invalid_sequence_decision,
        EligibilityReason.LIBRARY_TEMPLATE: policy.invalid_sequence_decision,
        EligibilityReason.LENGTH_OUT_OF_RANGE: policy.length_out_of_range_decision,
        EligibilityReason.SSDNA_PARKED: policy.ssdna_decision,
        EligibilityReason.NON_PROTEIN_TARGET_PARKED: (
            policy.non_protein_target_decision
        ),
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA: policy.eligible_rna_decision,
    }
    if reason not in mapping:
        raise AptaDBS3Error(f"No decision mapping for primary reason {reason.value}")
    return EligibilityDecision(mapping[reason])


def _is_technically_eligible_rna_protein(
    *,
    canonical: Mapping[str, str],
    applicable: Sequence[EligibilityReason],
    target_chemistry: str,
    policy: EligibilityPolicy,
) -> bool:
    blocking = {
        EligibilityReason.MISSING_SEQUENCE,
        EligibilityReason.MIXED_T_AND_U,
        EligibilityReason.AMBIGUOUS_BASES,
        EligibilityReason.ALIGNMENT_GAPS,
        EligibilityReason.INVALID_ALPHABET,
        EligibilityReason.TRUNCATED_SEQUENCE,
        EligibilityReason.PRIMER_LIKE,
        EligibilityReason.LIBRARY_TEMPLATE,
        EligibilityReason.LENGTH_OUT_OF_RANGE,
        EligibilityReason.SSDNA_PARKED,
        EligibilityReason.NON_PROTEIN_TARGET_PARKED,
    }
    if set(applicable) & blocking:
        return False
    if canonical.get("molecule_type") != "RNA":
        return False
    if target_chemistry != PROTEIN_TARGET_CHEMISTRY:
        return False
    sequence_core = canonical.get("sequence_core", "")
    if sequence_core == "":
        return False
    core_len = _parse_length(
        canonical.get("sequence_length_core", ""),
        record_id=canonical.get("record_id", ""),
        field_name="sequence_length_core",
    )
    if core_len is None:
        return False
    if not (policy.core_length_min <= core_len <= policy.core_length_max):
        return False
    return True


def _primary_route(decision: EligibilityDecision, reason: EligibilityReason) -> str:
    if decision == EligibilityDecision.PROPOSED_REJECT:
        return PRIMARY_ROUTE_REJECT
    if reason == EligibilityReason.SSDNA_PARKED:
        return PRIMARY_ROUTE_SSDNA
    if reason == EligibilityReason.NON_PROTEIN_TARGET_PARKED:
        return PRIMARY_ROUTE_NON_PROTEIN
    if (
        decision == EligibilityDecision.PROPOSED_ACCEPT
        and reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    ):
        return PRIMARY_ROUTE_ELIGIBLE
    raise AptaDBS3Error(
        "Could not assign a closed AptaDB primary route for "
        f"{decision.value}/{reason.value}"
    )


def _checkpoint_review_reasons(
    all_reasons: Sequence[EligibilityReason],
) -> list[str]:
    labels: list[str] = []
    reason_set = set(all_reasons)
    if reason_set & JUDGEMENT_DEPENDENT_REASONS:
        labels.append(REVIEW_REASON_JUDGEMENT)
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
    if reason_set & {
        EligibilityReason.CONSTANT_REGION_PROPOSAL,
        EligibilityReason.KNOWN_MOTIF_PROPOSAL,
    }:
        return ManualReviewPriority.MEDIUM
    if reason_set & {
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
        EligibilityReason.RANDOM_ACCEPT_AUDIT,
    }:
        return ManualReviewPriority.LOW
    return ManualReviewPriority.NONE


def assign_aptadb_review_batch(
    *,
    review_reasons: Sequence[str],
    manual_review_required: bool,
) -> str:
    if not manual_review_required:
        return ""
    if REVIEW_REASON_JUDGEMENT in review_reasons:
        return "01_judgement_dependent_technical"
    if REVIEW_REASON_CONSTANT in review_reasons:
        return "02_constant_region_proposal"
    if REVIEW_REASON_BOUNDARY in review_reasons:
        return "03_length_boundary"
    if REVIEW_REASON_RANDOM in review_reasons:
        return "04_random_kept_audit"
    raise AptaDBS3Error(
        "Review-required record belongs to no AptaDB batch: "
        f"reasons={list(review_reasons)}"
    )


def _proposal_metadata(proposals: Sequence[Mapping[str, str]]) -> dict[str, str]:
    if not proposals:
        return {
            "constant_proposal_ids": "",
            "constant_proposal_sources": "",
            "constant_proposal_sides": "",
            "constant_group_id": "",
            "constant_records_in_group": "",
            "constant_support": "",
            "constant_proposed_trim_length": "",
        }
    ordered = sorted(proposals, key=lambda row: row.get("proposal_id", ""))
    group_ids = [
        row.get("experiment_group_id", "")
        for row in ordered
        if row.get("proposal_source") == "group_consensus"
    ]
    return {
        "constant_proposal_ids": format_reasons(
            row.get("proposal_id", "") for row in ordered
        ),
        "constant_proposal_sources": format_reasons(
            row.get("proposal_source", "") for row in ordered
        ),
        "constant_proposal_sides": format_reasons(
            row.get("side", "") for row in ordered
        ),
        "constant_group_id": group_ids[0] if group_ids else ordered[0].get(
            "experiment_group_id", ""
        ),
        "constant_records_in_group": format_reasons(
            row.get("records_considered", "") for row in ordered
        ),
        "constant_support": format_reasons(row.get("support", "") for row in ordered),
        "constant_proposed_trim_length": format_reasons(
            row.get("motif_length", "") for row in ordered
        ),
    }


def classify_aptadb_record(
    s2_record: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]] = (),
) -> AptaDBS3RowResult:
    """Apply deterministic AptaDB S3 technical-eligibility rules to one record."""
    record_id = s2_record["record_id"]
    if record_id != s2_qc.get("record_id", ""):
        raise AptaDBS3Error("canonical and S2 QC record_id mismatch")
    if record_id != source_metadata.get("record_id", ""):
        raise AptaDBS3Error("canonical and source-metadata record_id mismatch")

    for field_name in S3_FORBIDDEN_FIELDS:
        if (s2_record.get(field_name) or "") != "":
            raise AptaDBS3Error(
                f"S3 must not receive populated later-stage field {field_name!r}"
            )
    if (s2_record.get("trim_confidence") or "") not in {"", "n/a"}:
        if s2_record.get("trim_confidence") == "medium" and (
            s2_record.get("sequence_core") == s2_record.get("sequence_full")
        ):
            raise AptaDBS3Error(
                "Unapplied AptaDB proposals must not set trim_confidence=medium"
            )

    flags = parse_qc_flags(s2_record.get("qc_flags", ""))
    target_chemistry = _target_chemistry(source_metadata)
    applicable = _collect_reasons(
        canonical=s2_record,
        flags=flags,
        policy=policy,
        target_chemistry=target_chemistry,
        proposals=proposals,
    )
    eligible = _is_technically_eligible_rna_protein(
        canonical=s2_record,
        applicable=applicable,
        target_chemistry=target_chemistry,
        policy=policy,
    )
    if eligible:
        applicable.append(EligibilityReason.TECHNICALLY_ELIGIBLE_RNA)

    primary = _select_primary(
        applicable, policy.decision_precedence, diagnostic=DIAGNOSTIC_REASONS
    )
    if primary is None:
        raise AptaDBS3Error(
            f"No eligibility reason resolved for record_id={record_id!r}"
        )
    proposed = _decision_for_reason(primary, policy)
    secondary = [reason for reason in applicable if reason != primary]
    automatic_length_reject = (
        proposed == EligibilityDecision.PROPOSED_REJECT
        and primary == EligibilityReason.LENGTH_OUT_OF_RANGE
        and EligibilityReason.TRIM_PUSHED_LENGTH_OUT_OF_RANGE not in applicable
        and not (set(applicable) & JUDGEMENT_DEPENDENT_REASONS)
        and EligibilityReason.CONSTANT_REGION_PROPOSAL not in applicable
        and EligibilityReason.KNOWN_MOTIF_PROPOSAL not in applicable
    )
    priority = assign_manual_review_priority(
        primary_reason=primary,
        all_reasons=applicable,
    )
    if automatic_length_reject:
        priority = ManualReviewPriority.NONE

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
    review_reasons = _checkpoint_review_reasons(eligibility.all_reasons)
    if automatic_length_reject:
        review_reasons = [
            reason for reason in review_reasons if reason != REVIEW_REASON_BOUNDARY
        ]
    review_batch = assign_aptadb_review_batch(
        review_reasons=review_reasons,
        manual_review_required=eligibility.manual_review_required,
    )
    primary_route = _primary_route(proposed, primary)

    if proposed == EligibilityDecision.PROPOSED_ACCEPT:
        if not eligible or primary != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA:
            raise AptaDBS3Error(
                f"Accept proposed without RNA-protein eligibility: {record_id!r}"
            )
        if s2_record.get("molecule_type") != "RNA":
            raise AptaDBS3Error(f"Non-RNA must not be accepted: {record_id!r}")
        if target_chemistry != PROTEIN_TARGET_CHEMISTRY:
            raise AptaDBS3Error(
                f"Non-protein target must not be accepted at S3: {record_id!r}"
            )

    if primary == EligibilityReason.MISSING_SEQUENCE and proposed != (
        EligibilityDecision.PROPOSED_REJECT
    ):
        raise AptaDBS3Error(f"Missing sequence must be rejected: {record_id!r}")
    if primary == EligibilityReason.SSDNA_PARKED and proposed != (
        EligibilityDecision.PROPOSED_PARK
    ):
        raise AptaDBS3Error(f"ssDNA must be parked when technically valid: {record_id!r}")

    if eligibility.manual_review_required and not review_batch:
        raise AptaDBS3Error(
            f"Review-required record missing review_batch: {record_id!r}"
        )
    if (not eligibility.manual_review_required) and review_batch:
        raise AptaDBS3Error(
            f"No-review record must not have a review_batch: {record_id!r}"
        )

    canonical = validate_s3_record(dict(s2_record), s2_record=s2_record)
    if canonical.get("sequence_core") != s2_record.get("sequence_core"):
        raise AptaDBS3Error("S3 must not alter sequence_core")
    if canonical.get("trim_confidence") != s2_record.get("trim_confidence"):
        raise AptaDBS3Error("S3 must not alter trim_confidence")

    proposal_meta = _proposal_metadata(proposals)
    decision = _build_decision_row(
        canonical=canonical,
        s2_qc=s2_qc,
        source_metadata=source_metadata,
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
        park_row = _build_park_row(
            canonical=canonical,
            decision=decision,
            target_chemistry=target_chemistry,
        )

    return AptaDBS3RowResult(
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
    source_metadata: Mapping[str, str],
    eligibility: EligibilityResult,
    review_batch: str,
    review_reasons: Sequence[str],
    primary_route: str,
    proposal_meta: Mapping[str, str],
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamer_name": _aptamer_name(s2_qc, source_metadata),
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
        "aptadb_target_chemistry": source_metadata.get("aptadb_target_chemistry", ""),
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "construct_scope": canonical["construct_scope"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical.get("trim_confidence", ""),
        "qc_flags": canonical["qc_flags"],
        "constant_proposal_ids": proposal_meta.get("constant_proposal_ids", ""),
        "constant_proposal_sources": proposal_meta.get("constant_proposal_sources", ""),
        "constant_proposal_sides": proposal_meta.get("constant_proposal_sides", ""),
        "constant_group_id": proposal_meta.get("constant_group_id", ""),
        "constant_records_in_group": proposal_meta.get("constant_records_in_group", ""),
        "constant_support": proposal_meta.get("constant_support", ""),
        "constant_proposed_trim_length": proposal_meta.get(
            "constant_proposed_trim_length", ""
        ),
        "notes": "",
    }


def _build_rejection_row(
    *,
    canonical: Mapping[str, str],
    decision: Mapping[str, str],
    stage: str = INTERACTION_REJECTION_STAGE,
) -> dict[str, str]:
    reason = decision["primary_reason"]
    if reason not in PLAN_REJECTION_REASONS:
        raise AptaDBS3Error(
            f"Rejection reason {reason!r} is not in the plan closed vocabulary"
        )
    detail_parts = [
        part for part in (decision.get("secondary_reasons") or "").split("|") if part
    ]
    return {
        "record_id": canonical["record_id"],
        "source_db": canonical.get("source_db", "aptadb"),
        "source_dataset": canonical.get("source_dataset", ""),
        "native_id": canonical["native_id"],
        "sequence_raw": canonical.get("sequence_raw", ""),
        "target_name_raw": canonical.get("target_name_raw", ""),
        "stage": stage,
        "rejection_reason": reason,
        "rejection_detail": format_reasons(detail_parts),
    }


def _build_park_row(
    *,
    canonical: Mapping[str, str],
    decision: Mapping[str, str],
    target_chemistry: str,
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "proposed_decision": decision["proposed_decision"],
        "park_reason": decision["primary_reason"],
        "secondary_reasons": decision.get("secondary_reasons", ""),
        "manual_review_required": decision["manual_review_required"],
        "review_batch": decision.get("review_batch", ""),
        "molecule_type": canonical.get("molecule_type", ""),
        "chemistry": canonical.get("chemistry", ""),
        "aptadb_target_chemistry": target_chemistry,
        "sequence_length_core": canonical.get("sequence_length_core", ""),
        "trim_status": canonical.get("trim_status", ""),
        "trim_confidence": canonical.get("trim_confidence", ""),
        "qc_flags": canonical.get("qc_flags", ""),
    }


def build_unlinked_rejection_row(
    unlinked: Mapping[str, str],
    *,
    source_dataset: str,
) -> dict[str, str]:
    """Build a source-level missing_target rejection for an unlinked aptamer."""
    apta_index = (unlinked.get("apta_index") or "").strip()
    chemistry = (unlinked.get("aptamer_chemistry") or "").strip()
    record_id = unlinked_rejection_record_id(apta_index)
    planned = (unlinked.get("planned_s3_reason") or "").strip()
    if planned and planned != EligibilityReason.MISSING_TARGET.value:
        raise AptaDBS3Error(
            f"Unlinked aptamer planned reason must be missing_target; got {planned!r}"
        )
    detail = format_reasons(
        [
            "unlinked_aptamer_no_interaction",
            f"aptamer_chemistry={chemistry or 'blank'}",
        ]
    )
    return {
        "record_id": record_id,
        "source_db": "aptadb",
        "source_dataset": source_dataset,
        "native_id": apta_index,
        "sequence_raw": unlinked.get("sequence") or "",
        "target_name_raw": "",
        "stage": UNLINKED_REJECTION_STAGE,
        "rejection_reason": EligibilityReason.MISSING_TARGET.value,
        "rejection_detail": detail,
    }


def build_local_detail_row(
    *,
    canonical: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    decision: Mapping[str, str],
) -> dict[str, str]:
    """Build one sequence-bearing local-detail review row."""
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamer_name": decision.get("aptamer_name", "")
        or _aptamer_name(s2_qc, source_metadata),
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
        "aptadb_target_chemistry": source_metadata.get("aptadb_target_chemistry", ""),
        "alphabet_as_reported": canonical.get("alphabet_as_reported", ""),
        "t_to_u_applied": canonical.get("t_to_u_applied", ""),
        "construct_scope": canonical.get("construct_scope", ""),
        "trim_status": canonical.get("trim_status", ""),
        "trim_confidence": canonical.get("trim_confidence", ""),
        "detected_constant_5p": canonical.get("detected_constant_5p", ""),
        "detected_constant_3p": canonical.get("detected_constant_3p", ""),
        "qc_flags": canonical.get("qc_flags", ""),
        "constant_proposal_ids": decision.get("constant_proposal_ids", ""),
        "constant_proposal_sources": decision.get("constant_proposal_sources", ""),
        "constant_proposal_sides": decision.get("constant_proposal_sides", ""),
        "constant_group_id": decision.get("constant_group_id", ""),
        "constant_records_in_group": decision.get("constant_records_in_group", ""),
        "constant_support": decision.get("constant_support", ""),
        "constant_proposed_trim_length": decision.get(
            "constant_proposed_trim_length", ""
        ),
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
    """Mark a seeded sample of RNA-protein technically eligible records.

    Returns ``(selected_count, pool_size, shortfall)``.
    """
    if sample_size < 0:
        raise AptaDBS3Error("random_accept_audit_size must be non-negative")
    candidates = [
        row
        for row in decision_rows
        if row["proposed_decision"] == "proposed_accept"
        and row["primary_reason"] == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value
        and row.get("primary_route") == PRIMARY_ROUTE_ELIGIBLE
        and row.get("molecule_type") == "RNA"
        and row.get("aptadb_target_chemistry") == PROTEIN_TARGET_CHEMISTRY
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
            row["review_batch"] = assign_aptadb_review_batch(
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


def update_stats_from_row(stats: AptaDBS3Stats, row: AptaDBS3RowResult) -> None:
    """Accumulate aggregate counters from one classified interaction row."""
    decision = row.eligibility.proposed_decision.value
    primary = row.eligibility.primary_reason.value
    priority = row.eligibility.manual_review_priority.value
    molecule = row.canonical.get("molecule_type") or "unknown"
    alphabet = row.canonical.get("alphabet_as_reported") or "missing"
    target_chemistry = row.decision.get("aptadb_target_chemistry") or "unknown"
    core_len = _parse_length(
        row.canonical.get("sequence_length_core", ""),
        record_id=row.canonical.get("record_id", ""),
        field_name="sequence_length_core",
    )
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
    if (
        row.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
        and row.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    ):
        stats.missing_sequence_excluded_from_review_count += 1

    if molecule in EXPLICIT_DNA_TYPES:
        stats.source_ssdna_before_technical += 1
        if row.primary_route == PRIMARY_ROUTE_REJECT:
            stats.technically_rejected_ssdna += 1
    if molecule == "RNA" and target_chemistry in NON_PROTEIN_TARGET_CHEMISTRY:
        stats.rna_non_protein_before_technical += 1
        if row.primary_route == PRIMARY_ROUTE_REJECT:
            stats.technically_rejected_rna_non_protein += 1
    if molecule == "RNA" and target_chemistry == PROTEIN_TARGET_CHEMISTRY:
        stats.rna_protein_before_technical += 1
        if row.primary_route == PRIMARY_ROUTE_REJECT:
            stats.technically_rejected_rna_protein += 1

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
    if EligibilityReason.LIBRARY_TEMPLATE in reasons:
        stats.library_template_count += 1
    if EligibilityReason.TRUNCATED_SEQUENCE in reasons:
        stats.truncated_sequence_count += 1
    if row.primary_route == PRIMARY_ROUTE_SSDNA:
        stats.ssdna_parked_count += 1
    if row.primary_route == PRIMARY_ROUTE_NON_PROTEIN:
        stats.non_protein_parked_count += 1
    if EligibilityReason.TECHNICALLY_ELIGIBLE_RNA in reasons:
        stats.technically_eligible_rna_count += 1
    if EligibilityReason.CONSTANT_REGION_PROPOSAL in reasons:
        stats.constant_proposal_record_count += 1
    if EligibilityReason.KNOWN_MOTIF_PROPOSAL in reasons:
        stats.known_motif_proposal_record_count += 1
    if EligibilityReason.LOWER_LENGTH_BOUNDARY in reasons:
        stats.boundary_low_count += 1
    if EligibilityReason.UPPER_LENGTH_BOUNDARY in reasons:
        stats.boundary_high_count += 1
    if reasons & {
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
    } and row.eligibility.manual_review_required:
        stats.boundary_review_count += 1
    if reasons & JUDGEMENT_DEPENDENT_REASONS and row.eligibility.manual_review_required:
        stats.judgement_dependent_review_count += 1
    if reasons & {
        EligibilityReason.CONSTANT_REGION_PROPOSAL,
        EligibilityReason.KNOWN_MOTIF_PROPOSAL,
    } and row.eligibility.manual_review_required:
        stats.constant_review_count += 1
    if EligibilityReason.RANDOM_ACCEPT_AUDIT in reasons:
        stats.random_accept_audit_count += 1
    if len(row.eligibility.all_reasons) > 1:
        stats.multiple_reasons_count += 1

    mol_map = stats.molecule_type_by_decision.setdefault(decision, {})
    mol_map[molecule] = mol_map.get(molecule, 0) + 1
    alph_map = stats.alphabet_by_decision.setdefault(decision, {})
    alph_map[alphabet] = alph_map.get(alphabet, 0) + 1
    chem_map = stats.target_chemistry_by_route.setdefault(row.primary_route, {})
    chem_map[target_chemistry] = chem_map.get(target_chemistry, 0) + 1
    bucket = _core_length_bucket(core_len)
    len_map = stats.core_length_bucket_by_decision.setdefault(decision, {})
    len_map[bucket] = len_map.get(bucket, 0) + 1


def refresh_stats_after_audit(
    stats: AptaDBS3Stats, decision_rows: Sequence[Mapping[str, str]]
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
    stats.constant_review_count = 0
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
        if required and (
            EligibilityReason.LOWER_LENGTH_BOUNDARY.value in secondaries
            or EligibilityReason.UPPER_LENGTH_BOUNDARY.value in secondaries
            or REVIEW_REASON_BOUNDARY
            in {
                part
                for part in (row.get("checkpoint_review_reasons") or "").split("|")
                if part
            }
        ):
            stats.boundary_review_count += 1
        review_set = {
            part
            for part in (row.get("checkpoint_review_reasons") or "").split("|")
            if part
        }
        if required and REVIEW_REASON_JUDGEMENT in review_set:
            stats.judgement_dependent_review_count += 1
        if required and REVIEW_REASON_CONSTANT in review_set:
            stats.constant_review_count += 1


def assert_aptadb_accept_invariants(decision_rows: Sequence[Mapping[str, str]]) -> None:
    """Hard-fail if any proposed accept violates RNA-protein eligibility."""
    for row in decision_rows:
        if row["proposed_decision"] != "proposed_accept":
            continue
        if row["molecule_type"] != "RNA":
            raise AptaDBS3Error("proposed accept contains non-RNA molecule_type")
        if row.get("aptadb_target_chemistry") != PROTEIN_TARGET_CHEMISTRY:
            raise AptaDBS3Error("proposed accept is not an AptaDB Protein target")
        if row["primary_reason"] != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value:
            raise AptaDBS3Error(
                "proposed accept primary_reason must be technically_eligible_rna"
            )
        if row.get("primary_route") != PRIMARY_ROUTE_ELIGIBLE:
            raise AptaDBS3Error("proposed accept primary_route mismatch")
        flags = parse_qc_flags(row.get("qc_flags", ""))
        if flags & {"invalid_character", "ambiguous_base", "mixed_t_u", "alignment_gaps"}:
            raise AptaDBS3Error("proposed accept has unresolved alphabet/gap QC flags")
        try:
            core_len = int(row["sequence_length_core"])
        except ValueError as exc:
            raise AptaDBS3Error(
                "proposed accept has non-integer sequence_length_core"
            ) from exc
        if not (20 <= core_len <= 100):
            raise AptaDBS3Error(
                "proposed accept core length outside 20–100 nt policy"
            )


def assert_aptadb_reject_park_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    seen: dict[str, str] = {}
    for row in decision_rows:
        record_id = row["record_id"]
        route = row.get("primary_route", "")
        if record_id in seen:
            raise AptaDBS3Error(f"Duplicate decision record_id {record_id!r}")
        seen[record_id] = route
        decision = row["proposed_decision"]
        primary = row["primary_reason"]
        if primary == "missing_sequence" and decision != "proposed_reject":
            raise AptaDBS3Error("missing sequence must never be accepted or parked")
        if primary == "ssdna_parked" and decision != "proposed_park":
            raise AptaDBS3Error("ssdna_parked must be a park")
        if primary == "non_protein_target_parked" and decision != "proposed_park":
            raise AptaDBS3Error("non_protein_target_parked must be a park")
        if primary == "length_out_of_range" and decision == "proposed_accept":
            raise AptaDBS3Error("length_out_of_range must never be accepted")
        if row["checkpoint_status"] != CHECKPOINT_STATUS_PENDING:
            raise AptaDBS3Error("Unexpected checkpoint_status at S3")
        if decision not in {
            "proposed_accept",
            "proposed_park",
            "proposed_reject",
        }:
            raise AptaDBS3Error(f"Unknown proposed_decision {decision!r}")
        if route not in {
            PRIMARY_ROUTE_REJECT,
            PRIMARY_ROUTE_SSDNA,
            PRIMARY_ROUTE_NON_PROTEIN,
            PRIMARY_ROUTE_ELIGIBLE,
        }:
            raise AptaDBS3Error(f"Unknown primary_route {route!r}")
        required = row.get("manual_review_required")
        if required not in {"true", "false"}:
            raise AptaDBS3Error("manual_review_required must be lowercase true/false")
        if required == "true" and not row.get("review_batch"):
            raise AptaDBS3Error("Active review row missing review_batch")
        if required == "false" and row.get("review_batch"):
            raise AptaDBS3Error("Mechanical row must not carry a review_batch")
        for forbidden in S3_FORBIDDEN_FIELDS:
            if forbidden in row and row[forbidden]:
                raise AptaDBS3Error(
                    f"S3 decision sidecar must not populate {forbidden}"
                )
        if row.get("manual_decision"):
            raise AptaDBS3Error("S3 must not pre-fill a human manual_decision")
        for field_name in (
            "manual_sequence_corrected",
            "manual_target_corrected",
            "manual_molecule_type_override",
            "manual_chemistry_override",
            "manual_trim_action",
            "manual_trim_5p_nt",
            "manual_trim_3p_nt",
            "manual_trim_group_override",
            "manual_notes",
        ):
            if row.get(field_name):
                raise AptaDBS3Error(
                    f"S3 must not pre-fill human field {field_name}"
                )

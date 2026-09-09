"""AptamerBase S3 adapter: technical eligibility, parking, and CHECKPOINT-1.

Consumes S2 canonical rows, S2 QC, the AptamerBase source-metadata sidecar,
and S2 known-motif proposals. Applies closed technical reasons plus
source-object routing. Does not apply trims, repair sequences, override RDF
molecule type, extract targets, score evidence, or apply leakage exclusions.

RDF-flattened secondary-structure and predicted-secondary-structure rows are
excluded as non-aptamer source objects. Target/evidence remain empty by
design until later global S4.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
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
    "aptamer_name",
    "aptamerbase_id",
    "source_object_type",
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
    "chemistry_class",
    "alphabet_as_reported",
    "t_to_u_applied",
    "sequence_length_full",
    "sequence_length_core",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "qc_flags",
    "rdf_has_rna",
    "rdf_has_dna",
    "has_minimal_aptamer_sidecar",
    "is_minimal_aptamer_of_sidecar",
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
    "source_object_type",
    "aptamerbase_id",
)

PARK_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "aptamerbase_id",
    "proposed_decision",
    "park_reason",
    "secondary_reasons",
    "manual_review_required",
    "review_batch",
    "molecule_type",
    "chemistry",
    "chemistry_class",
    "alphabet_as_reported",
    "t_to_u_applied",
    "source_object_type",
    "sequence_length_core",
    "trim_status",
    "trim_confidence",
    "qc_flags",
)

LOCAL_DETAIL_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "aptamer_name",
    "aptamerbase_id",
    "source_object_type",
    "target_name_raw",
    "publication",
    "aptamerbase_label",
    "aptamerbase_type",
    "aptamerbase_has_modification_details",
    "aptamerbase_has_minimal_aptamer",
    "aptamerbase_is_minimal_aptamer_of",
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
    "chemistry_class",
    "alphabet_as_reported",
    "t_to_u_applied",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "detected_constant_5p",
    "detected_constant_3p",
    "qc_flags",
    "rdf_has_rna",
    "rdf_has_dna",
    "rdf_has_modified_nucleic_acid",
    "has_minimal_aptamer_sidecar",
    "is_minimal_aptamer_of_sidecar",
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

DEFAULT_APTAMERBASE_BATCHES: Final[tuple[str, ...]] = (
    "01_sequence_or_source_conflict",
    "02_molecule_type_unresolved",
    "03_chemistry_review",
    "04_known_motif_construct",
    "05_accept_with_diagnostics",
    "06_random_kept_audit",
)

GAP_CHARACTERS: Final[frozenset[str]] = frozenset({"-", "."})
EXPLICIT_DNA_TYPES: Final[frozenset[str]] = frozenset({"ssDNA", "DNA"})
# Pre-review S3 accepted RNA/2F-RNA only. CHECKPOINT-1 reviewed chemistry
# now also permits 2NH2-RNA, 2OMe-RNA, and mixed for this source. ``unknown``
# remains a chemistry-review park. Do not silently infer RNA from molecule
# type after a human ``unknown`` override. This set is AptamerBase-specific.
ELIGIBLE_RNA_CHEMISTRIES: Final[frozenset[str]] = frozenset(
    {"RNA", "2F-RNA", "2NH2-RNA", "2OMe-RNA", "mixed"}
)
STRUCTURE_OBJECT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "nucleic_acid_secondary_structure",
        "predicted_secondary_structure",
    }
)
ALPHABET_RNA: Final[str] = "RNA"
ALPHABET_MISSING: Final[str] = "missing"
ALPHABET_MIXED: Final[str] = "mixed_T_U"
ALPHABET_AMBIGUOUS: Final[str] = "ambiguous"
ALPHABET_INVALID: Final[str] = "invalid"

REJECTION_STAGE: Final[str] = "S3"

PRIMARY_ROUTE_REJECT: Final[str] = "technical_reject"
PRIMARY_ROUTE_SSDNA: Final[str] = "parked_ssdna"
PRIMARY_ROUTE_MOLECULE: Final[str] = "parked_molecule_unresolved"
PRIMARY_ROUTE_CHEMISTRY_REVIEW: Final[str] = "parked_chemistry_review"
PRIMARY_ROUTE_CONSTRUCT: Final[str] = "parked_construct_review"
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
        EligibilityReason.RANDOM_ACCEPT_AUDIT,
        EligibilityReason.CONSTANT_REGION_PROPOSAL,
        EligibilityReason.KNOWN_MOTIF_PROPOSAL,
    }
)

AUTOMATIC_REJECTION_REASONS: Final[frozenset[EligibilityReason]] = frozenset(
    {
        EligibilityReason.NON_APTAMER_SOURCE_OBJECT,
        EligibilityReason.MISSING_SEQUENCE,
        EligibilityReason.LENGTH_OUT_OF_RANGE,
    }
)

SEQUENCE_SYNTAX_REASONS: Final[frozenset[EligibilityReason]] = frozenset(
    {
        EligibilityReason.MIXED_T_AND_U,
        EligibilityReason.AMBIGUOUS_BASES,
        EligibilityReason.ALIGNMENT_GAPS,
        EligibilityReason.INVALID_ALPHABET,
    }
)

REVIEW_REASON_SEQUENCE: Final[str] = "sequence_notation"
REVIEW_REASON_SOURCE_CONFLICT: Final[str] = "source_molecule_alphabet_conflict"
REVIEW_REASON_MOLECULE: Final[str] = "molecule_type_unresolved"
REVIEW_REASON_CHEMISTRY: Final[str] = "chemistry_requires_review"
REVIEW_REASON_SPIEGELMER: Final[str] = "spiegelmer_l_rna"
REVIEW_REASON_CONSTANT: Final[str] = "constant_region_proposal"
REVIEW_REASON_BOUNDARY: Final[str] = "length_boundary"
REVIEW_REASON_RANDOM: Final[str] = "random_kept_audit"


class AptamerBaseS3Error(ValueError):
    """Hard failure during AptamerBase S3 eligibility classification."""


@dataclass(frozen=True)
class AptamerBaseS3RowResult:
    """Canonical S3 row plus decision/rejection/park payloads for one record."""

    canonical: dict[str, str]
    decision: dict[str, str]
    eligibility: EligibilityResult
    rejection_row: dict[str, str] | None = None
    park_row: dict[str, str] | None = None
    primary_route: str = ""


@dataclass
class AptamerBaseS3Stats:
    """Aggregate S3 counts (no sequences or row identifiers)."""

    s2_rows: int = 0
    s3_rows: int = 0
    unique_record_ids: int = 0
    unique_native_ids: int = 0
    unique_freebase_ids: int = 0
    order_preserved: bool = False
    group_inference_disabled: bool = True
    decision_counts: dict[str, int] = field(default_factory=dict)
    primary_reason_counts: dict[str, int] = field(default_factory=dict)
    primary_route_counts: dict[str, int] = field(default_factory=dict)
    review_priority_counts: dict[str, int] = field(default_factory=dict)
    review_batch_counts: dict[str, int] = field(default_factory=dict)
    checkpoint_review_reason_counts: dict[str, int] = field(default_factory=dict)
    source_object_type_counts: dict[str, int] = field(default_factory=dict)
    source_object_by_route: dict[str, dict[str, int]] = field(default_factory=dict)
    molecule_type_counts: dict[str, int] = field(default_factory=dict)
    chemistry_counts: dict[str, int] = field(default_factory=dict)
    chemistry_class_counts: dict[str, int] = field(default_factory=dict)
    alphabet_counts: dict[str, int] = field(default_factory=dict)
    molecule_type_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    alphabet_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    core_length_bucket_by_decision: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    manual_review_required_true_count: int = 0
    manual_review_required_false_count: int = 0
    unique_checkpoint_review_records: int = 0
    missing_sequence_count: int = 0
    missing_sequence_excluded_from_review_count: int = 0
    missing_sequence_structure_count: int = 0
    missing_sequence_aptamer_count: int = 0
    non_aptamer_source_object_count: int = 0
    structure_topic_rows: int = 0
    structure_topic_nonempty_sequence: int = 0
    mixed_t_u_count: int = 0
    ambiguous_bases_count: int = 0
    invalid_alphabet_count: int = 0
    alignment_gaps_count: int = 0
    length_out_of_range_count: int = 0
    length_below_min_count: int = 0
    length_above_max_count: int = 0
    ssdna_parked_count: int = 0
    ssdna_source_count: int = 0
    dna_u_conflict_count: int = 0
    molecule_unresolved_count: int = 0
    molecule_unknown_source_count: int = 0
    molecule_unknown_structure_count: int = 0
    molecule_unknown_aptamer_count: int = 0
    chemistry_review_parked_count: int = 0
    spiegelmer_count: int = 0
    construct_review_parked_count: int = 0
    known_motif_proposal_record_count: int = 0
    known_motif_proposal_row_count: int = 0
    group_consensus_proposal_record_count: int = 0
    technically_eligible_rna_count: int = 0
    eligible_rna_chemistry_count: int = 0
    eligible_twof_chemistry_count: int = 0
    boundary_low_count: int = 0
    boundary_high_count: int = 0
    boundary_review_count: int = 0
    random_accept_audit_count: int = 0
    random_accept_audit_pool_size: int = 0
    random_accept_audit_shortfall: int = 0
    judgement_dependent_review_count: int = 0
    constant_review_count: int = 0
    sequence_notation_review_count: int = 0
    source_conflict_review_count: int = 0
    multiple_reasons_count: int = 0
    applied_trim_count: int = 0
    core_differs_from_full: int = 0
    missing_target_raw_count: int = 0
    missing_target_rejected_count: int = 0
    target_canonicalised_count: int = 0
    evidence_scored_count: int = 0
    affinity_normalised_count: int = 0
    sequence_leakage_count: int = 0
    target_leakage_count: int = 0
    both_leakage_count: int = 0


def _aptamer_name(s2_qc: Mapping[str, str], source_metadata: Mapping[str, str]) -> str:
    return (
        source_metadata.get("aptamerbase_label")
        or s2_qc.get("aptamer_name")
        or ""
    )


def actual_core_length(canonical: Mapping[str, str]) -> int | None:
    """Return ``len(sequence_core)``; never infer length from S2 QC flags."""
    sequence_core = canonical.get("sequence_core") or ""
    if sequence_core == "":
        return None
    return len(sequence_core)


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


def source_object_type(
    s2_qc: Mapping[str, str], source_metadata: Mapping[str, str]
) -> str:
    qc_type = (s2_qc.get("source_object_type") or "").strip()
    if qc_type:
        return qc_type
    raw_type = (source_metadata.get("aptamerbase_type") or "").strip()
    if raw_type.endswith("nucleic_acid_secondary_structure"):
        return "nucleic_acid_secondary_structure"
    if raw_type.endswith("predicted_secondary_structure"):
        return "predicted_secondary_structure"
    if raw_type.endswith("aptamer") or raw_type.endswith("base.aptamer.aptamer"):
        return "aptamer"
    return raw_type


def is_structure_object(
    *,
    object_type: str,
    flags: frozenset[str],
) -> bool:
    if object_type in STRUCTURE_OBJECT_TYPES:
        return True
    return "non_aptamer_structure_topic" in flags


def index_constant_proposals(
    canonical_rows: Sequence[Mapping[str, str]],
    proposals: Sequence[Mapping[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Map canonical record_id values to unapplied S2 proposal rows.

    Group-wise consensus proposals are forbidden: S2 ran with group
    inference disabled. Known-motif rows attach by record_id stored in
    ``experiment_group_id``.
    """
    by_record: dict[str, list[dict[str, str]]] = {}
    for proposal in proposals:
        row = {key: ("" if value is None else str(value)) for key, value in proposal.items()}
        source = row.get("proposal_source", "")
        if source == "group_consensus":
            raise AptamerBaseS3Error(
                "AptamerBase S3 received a group_consensus constant-region "
                "proposal, but group-wise inference was disabled"
            )
        if source != "known_motif":
            raise AptamerBaseS3Error(
                f"Unexpected AptamerBase proposal_source {source!r}"
            )
        if (row.get("applied") or "").strip() not in {"", "false"}:
            raise AptamerBaseS3Error(
                "AptamerBase S3 must not receive an already-applied motif trim"
            )
        record_id = row.get("experiment_group_id") or ""
        if not record_id:
            raise AptamerBaseS3Error("known_motif proposal missing experiment_group_id")
        by_record.setdefault(record_id, []).append(row)

    attached: dict[str, list[dict[str, str]]] = {}
    canonical_ids = {row["record_id"] for row in canonical_rows}
    for record_id, matches in by_record.items():
        if record_id not in canonical_ids:
            raise AptamerBaseS3Error(
                f"known_motif proposal references unknown record_id {record_id!r}"
            )
        attached[record_id] = matches
    return attached


def _collect_reasons(
    *,
    canonical: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    flags: frozenset[str],
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]],
) -> list[EligibilityReason]:
    """Collect every applicable reason without applying precedence."""
    reasons: list[EligibilityReason] = []
    sequence_core = canonical.get("sequence_core", "")
    sequence_full = canonical.get("sequence_full", "")
    object_type = source_object_type(s2_qc, source_metadata)
    structure = is_structure_object(object_type=object_type, flags=flags)
    if structure:
        reasons.append(EligibilityReason.NON_APTAMER_SOURCE_OBJECT)

    missing = (
        "missing_sequence" in flags
        or sequence_core == ""
        or (canonical.get("alphabet_as_reported") or "") == ALPHABET_MISSING
    )
    if missing:
        reasons.append(EligibilityReason.MISSING_SEQUENCE)

    inspect_seq = sequence_full or sequence_core
    alphabet = canonical.get("alphabet_as_reported") or ""
    molecule = canonical.get("molecule_type", "")
    chemistry = canonical.get("chemistry") or ""
    if not missing:
        if "mixed_t_u" in flags or alphabet == ALPHABET_MIXED:
            reasons.append(EligibilityReason.MIXED_T_AND_U)
        if "ambiguous_base" in flags or alphabet == ALPHABET_AMBIGUOUS:
            reasons.append(EligibilityReason.AMBIGUOUS_BASES)
        has_gaps = "alignment_gaps" in flags or _has_alignment_gaps(inspect_seq)
        if has_gaps:
            reasons.append(EligibilityReason.ALIGNMENT_GAPS)
        if "invalid_character" in flags or alphabet == ALPHABET_INVALID:
            reasons.append(EligibilityReason.INVALID_ALPHABET)

        core_len = actual_core_length(canonical)
        if (
            core_len is not None
            and not (policy.core_length_min <= core_len <= policy.core_length_max)
        ):
            reasons.append(EligibilityReason.LENGTH_OUT_OF_RANGE)

        if molecule in EXPLICIT_DNA_TYPES:
            reasons.append(EligibilityReason.SSDNA_PARKED)

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

    if molecule == "unknown" and not structure:
        reasons.append(EligibilityReason.MOLECULE_TYPE_UNRESOLVED)
    if (
        molecule == "RNA"
        and chemistry not in ELIGIBLE_RNA_CHEMISTRIES
        and not missing
    ):
        reasons.append(EligibilityReason.CHEMISTRY_REQUIRES_REVIEW)

    if any(row.get("proposal_source") == "group_consensus" for row in proposals):
        raise AptamerBaseS3Error(
            "Group-consensus proposals are forbidden for AptamerBase S3"
        )
    has_known_motif = any(
        row.get("proposal_source") == "known_motif" for row in proposals
    ) or "known_promoter_detected" in flags
    if has_known_motif:
        reasons.append(EligibilityReason.KNOWN_MOTIF_PROPOSAL)
        trim_already_applied = canonical.get("trim_status") in {
            "t7_removed",
            "primers_removed",
            "t7_and_primers_removed",
        }
        if policy.unresolved_trim_blocks_eligibility and not trim_already_applied:
            reasons.append(EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED)

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
        EligibilityReason.NON_APTAMER_SOURCE_OBJECT: (
            policy.non_aptamer_source_object_decision
        ),
        EligibilityReason.MISSING_SEQUENCE: policy.missing_sequence_decision,
        EligibilityReason.MIXED_T_AND_U: policy.mixed_t_u_decision,
        EligibilityReason.AMBIGUOUS_BASES: policy.ambiguous_sequence_decision,
        EligibilityReason.ALIGNMENT_GAPS: policy.alignment_gaps_decision,
        EligibilityReason.INVALID_ALPHABET: policy.invalid_sequence_decision,
        EligibilityReason.LENGTH_OUT_OF_RANGE: policy.length_out_of_range_decision,
        EligibilityReason.SSDNA_PARKED: policy.ssdna_decision,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED: policy.unknown_molecule_decision,
        EligibilityReason.CHEMISTRY_REQUIRES_REVIEW: policy.chemistry_review_decision,
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED: policy.trim_review_decision,
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA: policy.eligible_rna_decision,
    }
    if reason not in mapping:
        raise AptamerBaseS3Error(
            f"No decision mapping for primary reason {reason.value}"
        )
    return EligibilityDecision(mapping[reason])


def _is_technically_eligible_rna(
    *,
    canonical: Mapping[str, str],
    applicable: Sequence[EligibilityReason],
    policy: EligibilityPolicy,
    object_type: str,
) -> bool:
    blocking = {
        EligibilityReason.NON_APTAMER_SOURCE_OBJECT,
        EligibilityReason.MISSING_SEQUENCE,
        EligibilityReason.MIXED_T_AND_U,
        EligibilityReason.AMBIGUOUS_BASES,
        EligibilityReason.ALIGNMENT_GAPS,
        EligibilityReason.INVALID_ALPHABET,
        EligibilityReason.LENGTH_OUT_OF_RANGE,
        EligibilityReason.SSDNA_PARKED,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED,
        EligibilityReason.CHEMISTRY_REQUIRES_REVIEW,
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED,
    }
    if set(applicable) & blocking:
        return False
    if object_type != "aptamer":
        return False
    if canonical.get("molecule_type") != "RNA":
        return False
    if (canonical.get("chemistry") or "") not in ELIGIBLE_RNA_CHEMISTRIES:
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
    if reason == EligibilityReason.SSDNA_PARKED:
        return PRIMARY_ROUTE_SSDNA
    if reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED:
        return PRIMARY_ROUTE_MOLECULE
    if reason == EligibilityReason.CHEMISTRY_REQUIRES_REVIEW:
        return PRIMARY_ROUTE_CHEMISTRY_REVIEW
    if reason == EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED:
        return PRIMARY_ROUTE_CONSTRUCT
    if (
        decision == EligibilityDecision.PROPOSED_ACCEPT
        and reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    ):
        return PRIMARY_ROUTE_ELIGIBLE
    if decision == EligibilityDecision.PROPOSED_PARK:
        if reason == EligibilityReason.SSDNA_PARKED:
            return PRIMARY_ROUTE_SSDNA
        if reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED:
            return PRIMARY_ROUTE_MOLECULE
        if reason == EligibilityReason.CHEMISTRY_REQUIRES_REVIEW:
            return PRIMARY_ROUTE_CHEMISTRY_REVIEW
        return PRIMARY_ROUTE_CONSTRUCT
    raise AptamerBaseS3Error(
        "Could not assign a closed AptamerBase primary route for "
        f"{decision.value}/{reason.value}"
    )


def _has_dna_u_conflict(*, canonical: Mapping[str, str], flags: frozenset[str]) -> bool:
    if "source_molecule_alphabet_conflict" in flags:
        return True
    molecule = canonical.get("molecule_type", "")
    alphabet = canonical.get("alphabet_as_reported", "")
    return (
        molecule in EXPLICIT_DNA_TYPES
        and alphabet == ALPHABET_RNA
        and canonical.get("t_to_u_applied") == "false"
    )


def _checkpoint_review_reasons(
    *,
    all_reasons: Sequence[EligibilityReason],
    flags: frozenset[str],
    canonical: Mapping[str, str],
    dna_u_conflict: bool,
    spiegelmer: bool,
) -> list[str]:
    labels: list[str] = []
    reason_set = set(all_reasons)
    if reason_set & SEQUENCE_SYNTAX_REASONS:
        labels.append(REVIEW_REASON_SEQUENCE)
    if dna_u_conflict:
        labels.append(REVIEW_REASON_SOURCE_CONFLICT)
    if EligibilityReason.MOLECULE_TYPE_UNRESOLVED in reason_set:
        labels.append(REVIEW_REASON_MOLECULE)
    if EligibilityReason.CHEMISTRY_REQUIRES_REVIEW in reason_set:
        labels.append(REVIEW_REASON_CHEMISTRY)
    if spiegelmer or "spiegelmer_l_rna_review" in flags:
        if REVIEW_REASON_SPIEGELMER not in labels:
            labels.append(REVIEW_REASON_SPIEGELMER)
    if reason_set & {
        EligibilityReason.CONSTANT_REGION_PROPOSAL,
        EligibilityReason.KNOWN_MOTIF_PROPOSAL,
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED,
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
    dna_u_conflict: bool,
) -> ManualReviewPriority:
    """Assign review priority; never overrides the proposed decision."""
    reason_set = set(all_reasons)
    if primary_reason == EligibilityReason.NON_APTAMER_SOURCE_OBJECT:
        return ManualReviewPriority.NONE
    if primary_reason == EligibilityReason.MISSING_SEQUENCE:
        return ManualReviewPriority.NONE
    if reason_set & SEQUENCE_SYNTAX_REASONS or dna_u_conflict:
        return ManualReviewPriority.HIGH
    if EligibilityReason.MOLECULE_TYPE_UNRESOLVED in reason_set:
        return ManualReviewPriority.HIGH
    if EligibilityReason.CHEMISTRY_REQUIRES_REVIEW in reason_set:
        return ManualReviewPriority.HIGH
    if reason_set & {
        EligibilityReason.CONSTANT_REGION_PROPOSAL,
        EligibilityReason.KNOWN_MOTIF_PROPOSAL,
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED,
    }:
        return ManualReviewPriority.MEDIUM
    if primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA and reason_set & {
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
        EligibilityReason.RANDOM_ACCEPT_AUDIT,
    }:
        return ManualReviewPriority.LOW
    return ManualReviewPriority.NONE


def assign_aptamerbase_review_batch(
    *,
    review_reasons: Sequence[str],
    manual_review_required: bool,
) -> str:
    if not manual_review_required:
        return ""
    if (
        REVIEW_REASON_SEQUENCE in review_reasons
        or REVIEW_REASON_SOURCE_CONFLICT in review_reasons
    ):
        return "01_sequence_or_source_conflict"
    if REVIEW_REASON_MOLECULE in review_reasons:
        return "02_molecule_type_unresolved"
    if (
        REVIEW_REASON_CHEMISTRY in review_reasons
        or REVIEW_REASON_SPIEGELMER in review_reasons
    ):
        return "03_chemistry_review"
    if REVIEW_REASON_CONSTANT in review_reasons:
        return "04_known_motif_construct"
    if REVIEW_REASON_BOUNDARY in review_reasons:
        return "05_accept_with_diagnostics"
    if REVIEW_REASON_RANDOM in review_reasons:
        return "06_random_kept_audit"
    raise AptamerBaseS3Error(
        "Review-required record belongs to no AptamerBase batch: "
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
        "constant_group_id": "",
        "constant_records_in_group": format_reasons(
            row.get("records_considered", "") for row in ordered
        ),
        "constant_support": format_reasons(row.get("support", "") for row in ordered),
        "constant_proposed_trim_length": format_reasons(
            row.get("motif_length", "") for row in ordered
        ),
    }


def classify_aptamerbase_record(
    s2_record: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]] = (),
) -> AptamerBaseS3RowResult:
    """Apply deterministic AptamerBase S3 technical-eligibility rules."""
    record_id = s2_record["record_id"]
    if record_id != s2_qc.get("record_id", ""):
        raise AptamerBaseS3Error("canonical and S2 QC record_id mismatch")
    if record_id != source_metadata.get("record_id", ""):
        raise AptamerBaseS3Error("canonical and source-metadata record_id mismatch")

    for field_name in S3_FORBIDDEN_FIELDS:
        if (s2_record.get(field_name) or "") != "":
            raise AptamerBaseS3Error(
                f"S3 must not receive populated later-stage field {field_name!r}"
            )
    if policy.defer_target_classification is not True:
        raise AptamerBaseS3Error("AptamerBase S3 must defer target classification")
    if policy.defer_evidence_scoring is not True:
        raise AptamerBaseS3Error("AptamerBase S3 must defer evidence scoring")
    if policy.defer_leakage_exclusion is not True:
        raise AptamerBaseS3Error("AptamerBase S3 must defer leakage exclusion")

    flags = parse_qc_flags(s2_record.get("qc_flags", ""))
    object_type = source_object_type(s2_qc, source_metadata)
    applicable = _collect_reasons(
        canonical=s2_record,
        s2_qc=s2_qc,
        source_metadata=source_metadata,
        flags=flags,
        policy=policy,
        proposals=proposals,
    )
    eligible = _is_technically_eligible_rna(
        canonical=s2_record,
        applicable=applicable,
        policy=policy,
        object_type=object_type,
    )
    if eligible:
        applicable.append(EligibilityReason.TECHNICALLY_ELIGIBLE_RNA)

    primary = _select_primary(
        applicable, policy.decision_precedence, diagnostic=DIAGNOSTIC_REASONS
    )
    if primary is None:
        raise AptamerBaseS3Error(
            f"No eligibility reason resolved for record_id={record_id!r}"
        )
    proposed = _decision_for_reason(primary, policy)
    secondary = [reason for reason in applicable if reason != primary]
    dna_u_conflict = _has_dna_u_conflict(canonical=s2_record, flags=flags)
    spiegelmer = "spiegelmer_l_rna_review" in flags
    judgement_overlap = set(applicable) & SEQUENCE_SYNTAX_REASONS
    has_motif = EligibilityReason.KNOWN_MOTIF_PROPOSAL in applicable
    automatic_only_reject = (
        proposed == EligibilityDecision.PROPOSED_REJECT
        and primary in AUTOMATIC_REJECTION_REASONS
        and not judgement_overlap
        and not has_motif
        and not dna_u_conflict
    )
    priority = assign_manual_review_priority(
        primary_reason=primary,
        all_reasons=applicable,
        dna_u_conflict=dna_u_conflict,
    )
    if automatic_only_reject:
        priority = ManualReviewPriority.NONE
    if dna_u_conflict and primary == EligibilityReason.SSDNA_PARKED:
        priority = ManualReviewPriority.HIGH
    if (
        primary == EligibilityReason.LENGTH_OUT_OF_RANGE
        and has_motif
        and not judgement_overlap
    ):
        priority = ManualReviewPriority.MEDIUM

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
        flags=flags,
        canonical=s2_record,
        dna_u_conflict=dna_u_conflict,
        spiegelmer=spiegelmer,
    )
    if automatic_only_reject:
        review_reasons = [
            reason
            for reason in review_reasons
            if reason
            not in {
                REVIEW_REASON_BOUNDARY,
                REVIEW_REASON_SEQUENCE,
                REVIEW_REASON_MOLECULE,
                REVIEW_REASON_CHEMISTRY,
            }
        ]
    if proposed != EligibilityDecision.PROPOSED_ACCEPT:
        review_reasons = [
            reason for reason in review_reasons if reason != REVIEW_REASON_BOUNDARY
        ]
    if not eligibility.manual_review_required:
        review_reasons = []
    elif primary == EligibilityReason.LENGTH_OUT_OF_RANGE and has_motif:
        if REVIEW_REASON_CONSTANT not in review_reasons:
            review_reasons.append(REVIEW_REASON_CONSTANT)
        review_reasons = [
            reason for reason in review_reasons if reason != REVIEW_REASON_BOUNDARY
        ]
    elif (
        proposed == EligibilityDecision.PROPOSED_ACCEPT
        and REVIEW_REASON_BOUNDARY in review_reasons
        and not (
            {REVIEW_REASON_SEQUENCE, REVIEW_REASON_SOURCE_CONFLICT,
             REVIEW_REASON_MOLECULE, REVIEW_REASON_CHEMISTRY,
             REVIEW_REASON_CONSTANT}
            & set(review_reasons)
        )
    ):
        review_reasons = [REVIEW_REASON_BOUNDARY]
    review_batch = assign_aptamerbase_review_batch(
        review_reasons=review_reasons,
        manual_review_required=eligibility.manual_review_required,
    )
    primary_route = _primary_route(proposed, primary)

    if proposed == EligibilityDecision.PROPOSED_ACCEPT:
        if not eligible or primary != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA:
            raise AptamerBaseS3Error(
                f"Accept proposed without RNA eligibility: {record_id!r}"
            )
        if s2_record.get("molecule_type") != "RNA":
            raise AptamerBaseS3Error(f"Non-RNA must not be accepted: {record_id!r}")
        if (s2_record.get("chemistry") or "") not in ELIGIBLE_RNA_CHEMISTRIES:
            raise AptamerBaseS3Error(
                f"Chemistry {s2_record.get('chemistry')!r} must not be "
                f"accepted at S3: {record_id!r}"
            )
        if object_type != "aptamer":
            raise AptamerBaseS3Error(
                f"Non-aptamer source object must not be accepted: {record_id!r}"
            )

    if primary == EligibilityReason.MISSING_SEQUENCE and proposed != (
        EligibilityDecision.PROPOSED_REJECT
    ):
        raise AptamerBaseS3Error(f"Missing sequence must be rejected: {record_id!r}")
    if primary == EligibilityReason.NON_APTAMER_SOURCE_OBJECT and proposed != (
        EligibilityDecision.PROPOSED_REJECT
    ):
        raise AptamerBaseS3Error(
            f"Non-aptamer source objects must be rejected: {record_id!r}"
        )
    if primary == EligibilityReason.SSDNA_PARKED and proposed != (
        EligibilityDecision.PROPOSED_PARK
    ):
        raise AptamerBaseS3Error(
            f"ssDNA must be parked when technically valid: {record_id!r}"
        )
    if primary == EligibilityReason.MISSING_TARGET:
        raise AptamerBaseS3Error(
            "AptamerBase S3 must not reject missing_target; "
            "target classification is deferred"
        )

    if eligibility.manual_review_required and not review_batch:
        raise AptamerBaseS3Error(
            f"Review-required record missing review_batch: {record_id!r}"
        )
    if (not eligibility.manual_review_required) and review_batch:
        raise AptamerBaseS3Error(
            f"No-review record must not have a review_batch: {record_id!r}"
        )

    canonical = validate_s3_record(dict(s2_record), s2_record=s2_record)
    if canonical.get("sequence_core") != s2_record.get("sequence_core"):
        raise AptamerBaseS3Error("S3 must not alter sequence_core")
    if canonical.get("trim_confidence") != s2_record.get("trim_confidence"):
        raise AptamerBaseS3Error("S3 must not alter trim_confidence")
    if canonical.get("molecule_type") != s2_record.get("molecule_type"):
        raise AptamerBaseS3Error("S3 must not alter molecule_type")
    if canonical.get("t_to_u_applied") != s2_record.get("t_to_u_applied"):
        raise AptamerBaseS3Error("S3 must not alter t_to_u_applied")
    if canonical.get("target_name_raw") != "":
        raise AptamerBaseS3Error("AptamerBase S3 must leave target_name_raw empty")

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
        object_type=object_type,
    )
    rejection_row = None
    park_row = None
    if proposed == EligibilityDecision.PROPOSED_REJECT:
        rejection_row = _build_rejection_row(
            canonical=canonical,
            decision=decision,
            object_type=object_type,
            source_metadata=source_metadata,
        )
    elif proposed == EligibilityDecision.PROPOSED_PARK:
        park_row = _build_park_row(
            canonical=canonical,
            decision=decision,
            source_metadata=source_metadata,
            s2_qc=s2_qc,
            object_type=object_type,
        )

    return AptamerBaseS3RowResult(
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
    object_type: str,
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamer_name": _aptamer_name(s2_qc, source_metadata),
        "aptamerbase_id": source_metadata.get("aptamerbase_id", "")
        or s2_qc.get("aptamerbase_id", ""),
        "source_object_type": object_type,
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
        "chemistry_class": s2_qc.get("chemistry_class", ""),
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "t_to_u_applied": canonical.get("t_to_u_applied", ""),
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "construct_scope": canonical["construct_scope"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical.get("trim_confidence", ""),
        "qc_flags": canonical["qc_flags"],
        "rdf_has_rna": s2_qc.get("rdf_has_rna", ""),
        "rdf_has_dna": s2_qc.get("rdf_has_dna", ""),
        "has_minimal_aptamer_sidecar": s2_qc.get("has_minimal_aptamer_sidecar", ""),
        "is_minimal_aptamer_of_sidecar": s2_qc.get(
            "is_minimal_aptamer_of_sidecar", ""
        ),
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
    object_type: str,
    source_metadata: Mapping[str, str],
    stage: str = REJECTION_STAGE,
) -> dict[str, str]:
    reason = decision["primary_reason"]
    if reason not in PLAN_REJECTION_REASONS:
        raise AptamerBaseS3Error(
            f"Rejection reason {reason!r} is not in the plan closed vocabulary"
        )
    detail_parts = [
        part for part in (decision.get("secondary_reasons") or "").split("|") if part
    ]
    return {
        "record_id": canonical["record_id"],
        "source_db": canonical.get("source_db", "aptamerbase"),
        "source_dataset": canonical.get("source_dataset", ""),
        "native_id": canonical["native_id"],
        "sequence_raw": canonical.get("sequence_raw", ""),
        "target_name_raw": canonical.get("target_name_raw", ""),
        "stage": stage,
        "rejection_reason": reason,
        "rejection_detail": format_reasons(detail_parts),
        "source_object_type": object_type,
        "aptamerbase_id": source_metadata.get("aptamerbase_id", ""),
    }


def _build_park_row(
    *,
    canonical: Mapping[str, str],
    decision: Mapping[str, str],
    source_metadata: Mapping[str, str],
    s2_qc: Mapping[str, str],
    object_type: str,
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamerbase_id": source_metadata.get("aptamerbase_id", "")
        or s2_qc.get("aptamerbase_id", ""),
        "proposed_decision": decision["proposed_decision"],
        "park_reason": decision["primary_reason"],
        "secondary_reasons": decision.get("secondary_reasons", ""),
        "manual_review_required": decision["manual_review_required"],
        "review_batch": decision.get("review_batch", ""),
        "molecule_type": canonical.get("molecule_type", ""),
        "chemistry": canonical.get("chemistry", ""),
        "chemistry_class": s2_qc.get("chemistry_class", ""),
        "alphabet_as_reported": canonical.get("alphabet_as_reported", ""),
        "t_to_u_applied": canonical.get("t_to_u_applied", ""),
        "source_object_type": object_type,
        "sequence_length_core": canonical.get("sequence_length_core", ""),
        "trim_status": canonical.get("trim_status", ""),
        "trim_confidence": canonical.get("trim_confidence", ""),
        "qc_flags": canonical.get("qc_flags", ""),
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
        "aptamerbase_id": decision.get("aptamerbase_id", "")
        or source_metadata.get("aptamerbase_id", ""),
        "source_object_type": decision.get("source_object_type", ""),
        "target_name_raw": canonical.get("target_name_raw", ""),
        "publication": canonical.get("publication", ""),
        "aptamerbase_label": source_metadata.get("aptamerbase_label", ""),
        "aptamerbase_type": source_metadata.get("aptamerbase_type", ""),
        "aptamerbase_has_modification_details": source_metadata.get(
            "aptamerbase_has_modification_details", ""
        ),
        "aptamerbase_has_minimal_aptamer": source_metadata.get(
            "aptamerbase_has_minimal_aptamer", ""
        ),
        "aptamerbase_is_minimal_aptamer_of": source_metadata.get(
            "aptamerbase_is_minimal_aptamer_of", ""
        ),
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
        "chemistry_class": s2_qc.get("chemistry_class", ""),
        "alphabet_as_reported": canonical.get("alphabet_as_reported", ""),
        "t_to_u_applied": canonical.get("t_to_u_applied", ""),
        "construct_scope": canonical.get("construct_scope", ""),
        "trim_status": canonical.get("trim_status", ""),
        "trim_confidence": canonical.get("trim_confidence", ""),
        "detected_constant_5p": canonical.get("detected_constant_5p", ""),
        "detected_constant_3p": canonical.get("detected_constant_3p", ""),
        "qc_flags": canonical.get("qc_flags", ""),
        "rdf_has_rna": s2_qc.get("rdf_has_rna", ""),
        "rdf_has_dna": s2_qc.get("rdf_has_dna", ""),
        "rdf_has_modified_nucleic_acid": s2_qc.get(
            "rdf_has_modified_nucleic_acid", ""
        ),
        "has_minimal_aptamer_sidecar": s2_qc.get("has_minimal_aptamer_sidecar", ""),
        "is_minimal_aptamer_of_sidecar": s2_qc.get(
            "is_minimal_aptamer_of_sidecar", ""
        ),
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
    """Mark a seeded sample of technically eligible RNA records.

    Returns ``(selected_count, pool_size, shortfall)``. Records already in
    the review queue stay in their existing batch and are not duplicated.
    """
    if sample_size < 0:
        raise AptamerBaseS3Error("random_accept_audit_size must be non-negative")
    candidates = [
        row
        for row in decision_rows
        if row["proposed_decision"] == "proposed_accept"
        and row["primary_reason"] == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value
        and row.get("primary_route") == PRIMARY_ROUTE_ELIGIBLE
        and row.get("molecule_type") == "RNA"
        and row.get("manual_review_required") != "true"
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
            row["review_batch"] = assign_aptamerbase_review_batch(
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


def update_stats_from_row(stats: AptamerBaseS3Stats, row: AptamerBaseS3RowResult) -> None:
    """Accumulate aggregate counters from one classified row."""
    decision = row.eligibility.proposed_decision.value
    primary = row.eligibility.primary_reason.value
    priority = row.eligibility.manual_review_priority.value
    molecule = row.canonical.get("molecule_type") or "unknown"
    alphabet = row.canonical.get("alphabet_as_reported") or "missing"
    chemistry = row.canonical.get("chemistry") or "unknown"
    chem_class = row.decision.get("chemistry_class") or "(empty)"
    core_len = actual_core_length(row.canonical)
    reasons = set(row.eligibility.all_reasons)
    object_type = row.decision.get("source_object_type") or "(blank)"
    flags = parse_qc_flags(row.canonical.get("qc_flags", ""))

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

    stats.source_object_type_counts[object_type] = (
        stats.source_object_type_counts.get(object_type, 0) + 1
    )
    route_map = stats.source_object_by_route.setdefault(row.primary_route, {})
    route_map[object_type] = route_map.get(object_type, 0) + 1
    stats.molecule_type_counts[molecule] = (
        stats.molecule_type_counts.get(molecule, 0) + 1
    )
    stats.chemistry_counts[chemistry] = stats.chemistry_counts.get(chemistry, 0) + 1
    stats.chemistry_class_counts[chem_class] = (
        stats.chemistry_class_counts.get(chem_class, 0) + 1
    )
    stats.alphabet_counts[alphabet] = stats.alphabet_counts.get(alphabet, 0) + 1

    if not (row.canonical.get("target_name_raw") or "").strip():
        stats.missing_target_raw_count += 1
    if molecule in EXPLICIT_DNA_TYPES:
        stats.ssdna_source_count += 1
    if molecule == "unknown":
        stats.molecule_unknown_source_count += 1
        if object_type in STRUCTURE_OBJECT_TYPES:
            stats.molecule_unknown_structure_count += 1
        else:
            stats.molecule_unknown_aptamer_count += 1
    if object_type in STRUCTURE_OBJECT_TYPES:
        stats.structure_topic_rows += 1
        if row.canonical.get("sequence_core"):
            stats.structure_topic_nonempty_sequence += 1
    if EligibilityReason.MISSING_SEQUENCE in reasons:
        stats.missing_sequence_count += 1
        if object_type in STRUCTURE_OBJECT_TYPES:
            stats.missing_sequence_structure_count += 1
        else:
            stats.missing_sequence_aptamer_count += 1
    if (
        row.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
        and row.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    ):
        stats.missing_sequence_excluded_from_review_count += 1
    if EligibilityReason.NON_APTAMER_SOURCE_OBJECT in reasons:
        stats.non_aptamer_source_object_count += 1
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
        if core_len is not None and core_len < 20:
            stats.length_below_min_count += 1
        if core_len is not None and core_len > 100:
            stats.length_above_max_count += 1
    if EligibilityReason.TECHNICALLY_ELIGIBLE_RNA in reasons:
        stats.technically_eligible_rna_count += 1
    if EligibilityReason.KNOWN_MOTIF_PROPOSAL in reasons:
        stats.known_motif_proposal_record_count += 1
    if EligibilityReason.LOWER_LENGTH_BOUNDARY in reasons:
        stats.boundary_low_count += 1
    if EligibilityReason.UPPER_LENGTH_BOUNDARY in reasons:
        stats.boundary_high_count += 1
    if EligibilityReason.MOLECULE_TYPE_UNRESOLVED in reasons:
        stats.molecule_unresolved_count += 1
    if "source_molecule_alphabet_conflict" in flags or (
        molecule in EXPLICIT_DNA_TYPES and alphabet == ALPHABET_RNA
    ):
        stats.dna_u_conflict_count += 1
    if "spiegelmer_l_rna_review" in flags:
        stats.spiegelmer_count += 1
    if row.primary_route == PRIMARY_ROUTE_SSDNA:
        stats.ssdna_parked_count += 1
    if row.primary_route == PRIMARY_ROUTE_CHEMISTRY_REVIEW:
        stats.chemistry_review_parked_count += 1
    if row.primary_route == PRIMARY_ROUTE_CONSTRUCT:
        stats.construct_review_parked_count += 1
    if row.primary_route == PRIMARY_ROUTE_ELIGIBLE:
        if chemistry == "RNA":
            stats.eligible_rna_chemistry_count += 1
        elif chemistry == "2F-RNA":
            stats.eligible_twof_chemistry_count += 1
    if row.canonical.get("sequence_core") != row.canonical.get("sequence_full"):
        stats.core_differs_from_full += 1
        stats.applied_trim_count += 1
    if len(row.eligibility.all_reasons) > 1:
        stats.multiple_reasons_count += 1
    proposal_ids = row.decision.get("constant_proposal_ids") or ""
    if proposal_ids:
        stats.known_motif_proposal_row_count += proposal_ids.count("|") + 1

    mol_map = stats.molecule_type_by_decision.setdefault(decision, {})
    mol_map[molecule] = mol_map.get(molecule, 0) + 1
    alph_map = stats.alphabet_by_decision.setdefault(decision, {})
    alph_map[alphabet] = alph_map.get(alphabet, 0) + 1
    bucket = _core_length_bucket(core_len)
    len_map = stats.core_length_bucket_by_decision.setdefault(decision, {})
    len_map[bucket] = len_map.get(bucket, 0) + 1


def refresh_stats_after_audit(
    stats: AptamerBaseS3Stats, decision_rows: Sequence[Mapping[str, str]]
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
    stats.sequence_notation_review_count = 0
    stats.source_conflict_review_count = 0
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
        if required and REVIEW_REASON_BOUNDARY in review_set:
            stats.boundary_review_count += 1
        if required and (
            REVIEW_REASON_SEQUENCE in review_set
            or REVIEW_REASON_SOURCE_CONFLICT in review_set
            or REVIEW_REASON_MOLECULE in review_set
            or REVIEW_REASON_CHEMISTRY in review_set
        ):
            stats.judgement_dependent_review_count += 1
        if required and REVIEW_REASON_CONSTANT in review_set:
            stats.constant_review_count += 1
        if required and REVIEW_REASON_SEQUENCE in review_set:
            stats.sequence_notation_review_count += 1
        if required and REVIEW_REASON_SOURCE_CONFLICT in review_set:
            stats.source_conflict_review_count += 1


def assert_aptamerbase_accept_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    """Hard-fail if any proposed accept violates RNA technical eligibility."""
    for row in decision_rows:
        if row["proposed_decision"] != "proposed_accept":
            continue
        if row.get("source_object_type") != "aptamer":
            raise AptamerBaseS3Error("proposed accept is not an aptamer source object")
        if row["molecule_type"] != "RNA":
            raise AptamerBaseS3Error("proposed accept contains non-RNA molecule_type")
        if (row.get("chemistry") or "") not in ELIGIBLE_RNA_CHEMISTRIES:
            raise AptamerBaseS3Error(
                "proposed accept chemistry is not in the AptamerBase "
                "reviewed-eligible RNA set"
            )
        if row["primary_reason"] != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value:
            raise AptamerBaseS3Error(
                "proposed accept primary_reason must be technically_eligible_rna"
            )
        if row.get("primary_route") != PRIMARY_ROUTE_ELIGIBLE:
            raise AptamerBaseS3Error("proposed accept primary_route mismatch")
        if row.get("target_name_raw"):
            raise AptamerBaseS3Error("proposed accept must not populate target_name_raw")
        flags = parse_qc_flags(row.get("qc_flags", ""))
        if flags & {"invalid_character", "ambiguous_base", "mixed_t_u", "alignment_gaps"}:
            raise AptamerBaseS3Error(
                "proposed accept has unresolved alphabet/gap QC flags"
            )
        try:
            core_len = int(row["sequence_length_core"])
        except ValueError as exc:
            raise AptamerBaseS3Error(
                "proposed accept has non-integer sequence_length_core"
            ) from exc
        if not (20 <= core_len <= 100):
            raise AptamerBaseS3Error(
                "proposed accept core length outside 20–100 nt policy"
            )
        if EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED.value in (
            row.get("secondary_reasons") or ""
        ).split("|"):
            raise AptamerBaseS3Error(
                "proposed accept has unresolved known-motif/construct blocker"
            )


def assert_aptamerbase_reject_park_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    seen: dict[str, str] = {}
    for row in decision_rows:
        record_id = row["record_id"]
        route = row.get("primary_route", "")
        if record_id in seen:
            raise AptamerBaseS3Error(f"Duplicate decision record_id {record_id!r}")
        seen[record_id] = route
        decision = row["proposed_decision"]
        primary = row["primary_reason"]
        if primary == "missing_sequence" and decision != "proposed_reject":
            raise AptamerBaseS3Error("missing sequence must never be accepted or parked")
        if primary == "non_aptamer_source_object" and decision != "proposed_reject":
            raise AptamerBaseS3Error(
                "non-aptamer source objects must be rejected"
            )
        if primary == "missing_target":
            raise AptamerBaseS3Error(
                "AptamerBase S3 must not reject missing_target; "
                "target classification is deferred"
            )
        if primary == "ssdna_parked" and decision != "proposed_park":
            raise AptamerBaseS3Error("ssdna_parked must be a park")
        if primary == "length_out_of_range" and decision == "proposed_accept":
            raise AptamerBaseS3Error("length_out_of_range must never be accepted")
        if row["checkpoint_status"] != CHECKPOINT_STATUS_PENDING:
            raise AptamerBaseS3Error("Unexpected checkpoint_status at S3")
        if decision not in {
            "proposed_accept",
            "proposed_park",
            "proposed_reject",
        }:
            raise AptamerBaseS3Error(f"Unknown proposed_decision {decision!r}")
        if route not in {
            PRIMARY_ROUTE_REJECT,
            PRIMARY_ROUTE_SSDNA,
            PRIMARY_ROUTE_MOLECULE,
            PRIMARY_ROUTE_CHEMISTRY_REVIEW,
            PRIMARY_ROUTE_CONSTRUCT,
            PRIMARY_ROUTE_ELIGIBLE,
        }:
            raise AptamerBaseS3Error(f"Unknown primary_route {route!r}")
        if row.get("target_name_raw"):
            raise AptamerBaseS3Error("S3 must not populate target_name_raw")
        required = row.get("manual_review_required") == "true"
        batch = row.get("review_batch") or ""
        if required and not batch:
            raise AptamerBaseS3Error(
                f"Review-required row missing review_batch: {record_id!r}"
            )
        if (not required) and batch:
            raise AptamerBaseS3Error(
                f"No-review row must not have review_batch: {record_id!r}"
            )
        if primary == "non_aptamer_source_object" and required:
            raise AptamerBaseS3Error(
                "Non-aptamer source objects must not require human review"
            )
        if primary == "missing_sequence" and required:
            raise AptamerBaseS3Error(
                "Missing-sequence rejects must not require human review"
            )
        if row.get("manual_decision"):
            raise AptamerBaseS3Error("S3 must not pre-fill a human manual_decision")
        for field_name in S3_FORBIDDEN_FIELDS:
            if field_name in row and row[field_name]:
                raise AptamerBaseS3Error(
                    f"S3 decision sidecar must not populate {field_name}"
                )

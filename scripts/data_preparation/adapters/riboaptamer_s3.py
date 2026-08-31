"""RiboAptamer S3 adapter: technical eligibility and CHECKPOINT-1 routing.

Consumes S2 canonical rows, S2 QC, the RiboAptamer source-metadata sidecar,
and S2 known-motif proposals. Applies the 20–100 nt core-length policy and
closed technical reasons. Does not apply trims, repair sequences, classify
targets, score evidence, park from source Type, or apply leakage exclusions.

Length eligibility uses the actual computed ``sequence_core`` length, not S2
``core_above_max_length`` / ``core_below_min_length`` QC flags. Judgement-
dependent truncation/alignment/primer/library conditions take CHECKPOINT-1
review precedence when they overlap automatic alphabet or length failures.
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
    "riboaptamer_sequence_name",
    "riboaptamer_aptamer_name",
    "riboaptamer_category",
    "riboaptamer_type",
    "riboaptamer_article_name",
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

DEFAULT_RIBOAPTAMER_BATCHES: Final[tuple[str, ...]] = (
    "01_judgement_dependent_technical",
    "02_constant_region_proposal",
    "03_length_boundary",
    "04_random_kept_audit",
)

ALLOWED_MANUAL_DECISIONS: Final[frozenset[str]] = frozenset({"keep", "drop", "edit", ""})

GAP_CHARACTERS: Final[frozenset[str]] = frozenset({"-", "."})
NUCLEOTIDE_OR_AMBIGUITY: Final[frozenset[str]] = frozenset("ACGTUNRYWSMKHBVD")
EXPLICIT_DNA_TYPES: Final[frozenset[str]] = frozenset({"ssDNA", "DNA"})

REJECTION_STAGE: Final[str] = "S3"

PRIMARY_ROUTE_REJECT: Final[str] = "technical_reject"
PRIMARY_ROUTE_SSDNA: Final[str] = "parked_ssdna"
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

# Automatic technical exclusions. These do not by themselves enter
# CHECKPOINT-1 unless a judgement-dependent condition also applies.
AUTOMATIC_REJECTION_REASONS: Final[frozenset[EligibilityReason]] = frozenset(
    {
        EligibilityReason.MISSING_SEQUENCE,
        EligibilityReason.AMBIGUOUS_BASES,
        EligibilityReason.INVALID_ALPHABET,
        EligibilityReason.MIXED_T_AND_U,
        EligibilityReason.LENGTH_OUT_OF_RANGE,
    }
)

# Judgement-dependent conditions always route to CHECKPOINT-1, even when an
# overlapping automatic reason (e.g. invalid_alphabet) is also present.
JUDGEMENT_DEPENDENT_REASONS: Final[frozenset[EligibilityReason]] = frozenset(
    {
        EligibilityReason.ALIGNMENT_GAPS,
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

REASON_PRIORITY_RULE: Final[str] = (
    "Judgement-dependent truncation/alignment/primer/library conditions take "
    "CHECKPOINT-1 review precedence over overlapping automatic reasons such as "
    "invalid_alphabet. Primary rejection_reason remains a single closed-vocabulary "
    "value; secondary_reasons and checkpoint_review_reasons retain the overlap."
)


class RiboAptamerS3Error(ValueError):
    """Hard failure during RiboAptamer S3 eligibility classification."""


@dataclass(frozen=True)
class RiboAptamerS3RowResult:
    """Canonical S3 row plus decision/rejection/park payloads for one record."""

    canonical: dict[str, str]
    decision: dict[str, str]
    eligibility: EligibilityResult
    rejection_row: dict[str, str] | None = None
    park_row: dict[str, str] | None = None
    primary_route: str = ""


@dataclass
class RiboAptamerS3Stats:
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
    length_below_min_count: int = 0
    length_above_max_count: int = 0
    primer_like_count: int = 0
    library_template_count: int = 0
    truncated_sequence_count: int = 0
    ssdna_parked_count: int = 0
    non_protein_parked_count: int = 0
    technically_eligible_rna_count: int = 0
    constant_proposal_record_count: int = 0
    known_motif_proposal_record_count: int = 0
    group_consensus_proposal_record_count: int = 0
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
    trim_pushed_length_count: int = 0
    invalid_and_length_count: int = 0
    truncated_and_invalid_count: int = 0
    truncated_and_alignment_count: int = 0
    ambiguous_and_length_count: int = 0
    boundary_with_other_technical_count: int = 0
    known_motif_in_length_window_count: int = 0
    source_type_used_for_parking: bool = False
    group_inference_disabled: bool = True
    molecule_type_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    alphabet_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    core_length_bucket_by_decision: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    sequence_leakage_count: int = 0
    target_leakage_count: int = 0
    both_leakage_count: int = 0


def _aptamer_name(s2_qc: Mapping[str, str], source_metadata: Mapping[str, str]) -> str:
    return (
        source_metadata.get("riboaptamer_aptamer_name")
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


def _has_non_gap_invalid(sequence: str) -> bool:
    return any(
        ch not in NUCLEOTIDE_OR_AMBIGUITY and ch not in GAP_CHARACTERS
        for ch in sequence.upper()
    )


def index_constant_proposals(
    canonical_rows: Sequence[Mapping[str, str]],
    proposals: Sequence[Mapping[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Map canonical record_id values to unapplied S2 proposal rows.

    Group-wise consensus proposals are forbidden for this source: S2 ran with
    group inference disabled. Known-motif rows attach by record_id stored in
    ``experiment_group_id``.
    """
    by_record: dict[str, list[dict[str, str]]] = {}
    for proposal in proposals:
        row = {key: ("" if value is None else str(value)) for key, value in proposal.items()}
        source = row.get("proposal_source", "")
        if source == "group_consensus":
            raise RiboAptamerS3Error(
                "RiboAptamer S3 received a group_consensus constant-region "
                "proposal, but group-wise inference was disabled"
            )
        if source != "known_motif":
            raise RiboAptamerS3Error(
                f"Unexpected RiboAptamer proposal_source {source!r}"
            )
        record_id = row.get("experiment_group_id") or ""
        if not record_id:
            raise RiboAptamerS3Error("known_motif proposal missing experiment_group_id")
        by_record.setdefault(record_id, []).append(row)

    attached: dict[str, list[dict[str, str]]] = {}
    canonical_ids = {row["record_id"] for row in canonical_rows}
    for record_id, matches in by_record.items():
        if record_id not in canonical_ids:
            raise RiboAptamerS3Error(
                f"known_motif proposal references unknown record_id {record_id!r}"
            )
        attached[record_id] = matches
    return attached


def _collect_reasons(
    *,
    canonical: Mapping[str, str],
    flags: frozenset[str],
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]],
    enforce_rna_contract: bool,
) -> list[EligibilityReason]:
    """Collect every applicable reason without applying precedence."""
    reasons: list[EligibilityReason] = []
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

    core_len = actual_core_length(canonical)
    full_seq = sequence_full or ""
    full_len = len(full_seq) if full_seq else None
    if (
        not missing
        and core_len is not None
        and not (policy.core_length_min <= core_len <= policy.core_length_max)
    ):
        reasons.append(EligibilityReason.LENGTH_OUT_OF_RANGE)
        if (
            full_len is not None
            and policy.core_length_min <= full_len <= policy.core_length_max
            and canonical.get("sequence_core") != canonical.get("sequence_full")
        ):
            reasons.append(EligibilityReason.TRIM_PUSHED_LENGTH_OUT_OF_RANGE)

    molecule = canonical.get("molecule_type", "")
    if molecule in EXPLICIT_DNA_TYPES:
        if enforce_rna_contract:
            raise RiboAptamerS3Error(
                "RiboAptamer S3 source contract is experimental RNA; "
                f"unexpected molecule_type={molecule!r} for "
                f"{canonical.get('record_id', '')!r}. Do not silently park as ssDNA."
            )
        reasons.append(EligibilityReason.SSDNA_PARKED)
    elif molecule not in {"RNA", "unknown"}:
        raise RiboAptamerS3Error(
            f"Unrecognised RiboAptamer molecule_type {molecule!r} for "
            f"{canonical.get('record_id', '')!r}"
        )
    if molecule == "unknown" or "molecule_type_unknown" in flags:
        if not missing:
            raise RiboAptamerS3Error(
                "RiboAptamer S3 does not accept unresolved molecule_type for "
                f"{canonical.get('record_id', '')!r}"
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
        raise RiboAptamerS3Error(
            "Group-consensus proposals are forbidden for RiboAptamer S3"
        )
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
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA: policy.eligible_rna_decision,
    }
    if reason not in mapping:
        raise RiboAptamerS3Error(
            f"No decision mapping for primary reason {reason.value}"
        )
    return EligibilityDecision(mapping[reason])


def _is_technically_eligible_rna(
    *,
    canonical: Mapping[str, str],
    applicable: Sequence[EligibilityReason],
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
    }
    if set(applicable) & blocking:
        return False
    if canonical.get("molecule_type") != "RNA":
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
    if (
        decision == EligibilityDecision.PROPOSED_ACCEPT
        and reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    ):
        return PRIMARY_ROUTE_ELIGIBLE
    raise RiboAptamerS3Error(
        "Could not assign a closed RiboAptamer primary route for "
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


def assign_riboaptamer_review_batch(
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
    raise RiboAptamerS3Error(
        "Review-required record belongs to no RiboAptamer batch: "
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
        # Known-motif proposals stay record-level. Do not invent a consensus
        # group id from the record_id; group-wise inference is disabled.
        "constant_group_id": "",
        "constant_records_in_group": format_reasons(
            row.get("records_considered", "") for row in ordered
        ),
        "constant_support": format_reasons(row.get("support", "") for row in ordered),
        "constant_proposed_trim_length": format_reasons(
            row.get("motif_length", "") for row in ordered
        ),
    }


def classify_riboaptamer_record(
    s2_record: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]] = (),
    enforce_rna_contract: bool = True,
) -> RiboAptamerS3RowResult:
    """Apply deterministic RiboAptamer S3 technical-eligibility rules."""
    record_id = s2_record["record_id"]
    if record_id != s2_qc.get("record_id", ""):
        raise RiboAptamerS3Error("canonical and S2 QC record_id mismatch")
    if record_id != source_metadata.get("record_id", ""):
        raise RiboAptamerS3Error("canonical and source-metadata record_id mismatch")

    for field_name in S3_FORBIDDEN_FIELDS:
        if (s2_record.get(field_name) or "") != "":
            raise RiboAptamerS3Error(
                f"S3 must not receive populated later-stage field {field_name!r}"
            )
    if policy.defer_target_classification is not True:
        raise RiboAptamerS3Error("RiboAptamer S3 must defer target classification")
    if policy.defer_evidence_scoring is not True:
        raise RiboAptamerS3Error("RiboAptamer S3 must defer evidence scoring")
    if policy.defer_leakage_exclusion is not True:
        raise RiboAptamerS3Error("RiboAptamer S3 must defer leakage exclusion")

    flags = parse_qc_flags(s2_record.get("qc_flags", ""))
    applicable = _collect_reasons(
        canonical=s2_record,
        flags=flags,
        policy=policy,
        proposals=proposals,
        enforce_rna_contract=enforce_rna_contract,
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
        raise RiboAptamerS3Error(
            f"No eligibility reason resolved for record_id={record_id!r}"
        )
    proposed = _decision_for_reason(primary, policy)
    secondary = [reason for reason in applicable if reason != primary]
    judgement_overlap = set(applicable) & JUDGEMENT_DEPENDENT_REASONS
    automatic_only_reject = (
        proposed == EligibilityDecision.PROPOSED_REJECT
        and primary in AUTOMATIC_REJECTION_REASONS
        and not judgement_overlap
        and EligibilityReason.CONSTANT_REGION_PROPOSAL not in applicable
        and EligibilityReason.KNOWN_MOTIF_PROPOSAL not in applicable
    )
    priority = assign_manual_review_priority(
        primary_reason=primary,
        all_reasons=applicable,
    )
    if automatic_only_reject:
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
    if automatic_only_reject:
        review_reasons = [
            reason
            for reason in review_reasons
            if reason
            not in {REVIEW_REASON_BOUNDARY, REVIEW_REASON_JUDGEMENT}
        ]
    review_batch = assign_riboaptamer_review_batch(
        review_reasons=review_reasons,
        manual_review_required=eligibility.manual_review_required,
    )
    primary_route = _primary_route(proposed, primary)

    if proposed == EligibilityDecision.PROPOSED_ACCEPT:
        if not eligible or primary != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA:
            raise RiboAptamerS3Error(
                f"Accept proposed without RNA eligibility: {record_id!r}"
            )
        if s2_record.get("molecule_type") != "RNA":
            raise RiboAptamerS3Error(f"Non-RNA must not be accepted: {record_id!r}")

    if primary == EligibilityReason.MISSING_SEQUENCE and proposed != (
        EligibilityDecision.PROPOSED_REJECT
    ):
        raise RiboAptamerS3Error(f"Missing sequence must be rejected: {record_id!r}")

    if eligibility.manual_review_required and not review_batch:
        raise RiboAptamerS3Error(
            f"Review-required record missing review_batch: {record_id!r}"
        )
    if (not eligibility.manual_review_required) and review_batch:
        raise RiboAptamerS3Error(
            f"No-review record must not have a review_batch: {record_id!r}"
        )

    canonical = validate_s3_record(dict(s2_record), s2_record=s2_record)
    if canonical.get("sequence_core") != s2_record.get("sequence_core"):
        raise RiboAptamerS3Error("S3 must not alter sequence_core")
    if canonical.get("trim_confidence") != s2_record.get("trim_confidence"):
        raise RiboAptamerS3Error("S3 must not alter trim_confidence")

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
        if enforce_rna_contract:
            raise RiboAptamerS3Error(
                "RiboAptamer S3 must not park under the RNA source contract"
            )
        park_row = {
            "record_id": canonical["record_id"],
            "native_id": canonical["native_id"],
            "proposed_decision": decision["proposed_decision"],
            "park_reason": decision["primary_reason"],
            "secondary_reasons": decision.get("secondary_reasons", ""),
            "manual_review_required": decision["manual_review_required"],
            "review_batch": decision.get("review_batch", ""),
            "molecule_type": canonical.get("molecule_type", ""),
            "chemistry": canonical.get("chemistry", ""),
            "sequence_length_core": canonical.get("sequence_length_core", ""),
            "trim_status": canonical.get("trim_status", ""),
            "trim_confidence": canonical.get("trim_confidence", ""),
            "qc_flags": canonical.get("qc_flags", ""),
        }

    return RiboAptamerS3RowResult(
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
    stage: str = REJECTION_STAGE,
) -> dict[str, str]:
    reason = decision["primary_reason"]
    if reason not in PLAN_REJECTION_REASONS:
        raise RiboAptamerS3Error(
            f"Rejection reason {reason!r} is not in the plan closed vocabulary"
        )
    detail_parts = [
        part for part in (decision.get("secondary_reasons") or "").split("|") if part
    ]
    return {
        "record_id": canonical["record_id"],
        "source_db": canonical.get("source_db", "riboaptamer"),
        "source_dataset": canonical.get("source_dataset", ""),
        "native_id": canonical["native_id"],
        "sequence_raw": canonical.get("sequence_raw", ""),
        "target_name_raw": canonical.get("target_name_raw", ""),
        "stage": stage,
        "rejection_reason": reason,
        "rejection_detail": format_reasons(detail_parts),
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
        "publication": source_metadata.get("riboaptamer_article_name", "")
        or canonical.get("publication", ""),
        "riboaptamer_sequence_name": source_metadata.get(
            "riboaptamer_sequence_name", ""
        ),
        "riboaptamer_aptamer_name": source_metadata.get(
            "riboaptamer_aptamer_name", ""
        ),
        "riboaptamer_category": source_metadata.get("riboaptamer_category", ""),
        "riboaptamer_type": source_metadata.get("riboaptamer_type", ""),
        "riboaptamer_article_name": source_metadata.get(
            "riboaptamer_article_name", ""
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
    """Mark a seeded sample of technically eligible RNA records.

    Returns ``(selected_count, pool_size, shortfall)``. Records already in
    the review queue (boundary / known-motif) stay in their existing batch
    and are not duplicated.
    """
    if sample_size < 0:
        raise RiboAptamerS3Error("random_accept_audit_size must be non-negative")
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
            row["review_batch"] = assign_riboaptamer_review_batch(
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


def update_stats_from_row(
    stats: RiboAptamerS3Stats, row: RiboAptamerS3RowResult
) -> None:
    """Accumulate aggregate counters from one classified row."""
    decision = row.eligibility.proposed_decision.value
    primary = row.eligibility.primary_reason.value
    priority = row.eligibility.manual_review_priority.value
    molecule = row.canonical.get("molecule_type") or "unknown"
    alphabet = row.canonical.get("alphabet_as_reported") or "missing"
    core_len = actual_core_length(row.canonical)
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
        if core_len is not None and core_len < 20:
            stats.length_below_min_count += 1
        if core_len is not None and core_len > 100:
            stats.length_above_max_count += 1
    if EligibilityReason.PRIMER_LIKE in reasons:
        stats.primer_like_count += 1
    if EligibilityReason.LIBRARY_TEMPLATE in reasons:
        stats.library_template_count += 1
    if EligibilityReason.TRUNCATED_SEQUENCE in reasons:
        stats.truncated_sequence_count += 1
    if EligibilityReason.TECHNICALLY_ELIGIBLE_RNA in reasons:
        stats.technically_eligible_rna_count += 1
    if EligibilityReason.CONSTANT_REGION_PROPOSAL in reasons:
        stats.constant_proposal_record_count += 1
    if EligibilityReason.KNOWN_MOTIF_PROPOSAL in reasons:
        stats.known_motif_proposal_record_count += 1
        if core_len is not None and 20 <= core_len <= 100:
            stats.known_motif_in_length_window_count += 1
    if EligibilityReason.LOWER_LENGTH_BOUNDARY in reasons:
        stats.boundary_low_count += 1
    if EligibilityReason.UPPER_LENGTH_BOUNDARY in reasons:
        stats.boundary_high_count += 1
    if EligibilityReason.TRIM_PUSHED_LENGTH_OUT_OF_RANGE in reasons:
        stats.trim_pushed_length_count += 1
    if (
        EligibilityReason.INVALID_ALPHABET in reasons
        and EligibilityReason.LENGTH_OUT_OF_RANGE in reasons
    ):
        stats.invalid_and_length_count += 1
    if (
        EligibilityReason.TRUNCATED_SEQUENCE in reasons
        and EligibilityReason.INVALID_ALPHABET in reasons
    ):
        stats.truncated_and_invalid_count += 1
    if (
        EligibilityReason.TRUNCATED_SEQUENCE in reasons
        and EligibilityReason.ALIGNMENT_GAPS in reasons
    ):
        stats.truncated_and_alignment_count += 1
    if (
        EligibilityReason.AMBIGUOUS_BASES in reasons
        and EligibilityReason.LENGTH_OUT_OF_RANGE in reasons
    ):
        stats.ambiguous_and_length_count += 1
    if reasons & {
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
    } and reasons & (
        AUTOMATIC_REJECTION_REASONS | JUDGEMENT_DEPENDENT_REASONS
    ):
        stats.boundary_with_other_technical_count += 1
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
    bucket = _core_length_bucket(core_len)
    len_map = stats.core_length_bucket_by_decision.setdefault(decision, {})
    len_map[bucket] = len_map.get(bucket, 0) + 1


def refresh_stats_after_audit(
    stats: RiboAptamerS3Stats, decision_rows: Sequence[Mapping[str, str]]
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
        review_set = {
            part
            for part in (row.get("checkpoint_review_reasons") or "").split("|")
            if part
        }
        if required and REVIEW_REASON_BOUNDARY in review_set:
            stats.boundary_review_count += 1
        if required and REVIEW_REASON_JUDGEMENT in review_set:
            stats.judgement_dependent_review_count += 1
        if required and REVIEW_REASON_CONSTANT in review_set:
            stats.constant_review_count += 1


def assert_riboaptamer_accept_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    """Hard-fail if any proposed accept violates RNA technical eligibility."""
    for row in decision_rows:
        if row["proposed_decision"] != "proposed_accept":
            continue
        if row["molecule_type"] != "RNA":
            raise RiboAptamerS3Error("proposed accept contains non-RNA molecule_type")
        if row["primary_reason"] != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value:
            raise RiboAptamerS3Error(
                "proposed accept primary_reason must be technically_eligible_rna"
            )
        if row.get("primary_route") != PRIMARY_ROUTE_ELIGIBLE:
            raise RiboAptamerS3Error("proposed accept primary_route mismatch")
        flags = parse_qc_flags(row.get("qc_flags", ""))
        if flags & {"invalid_character", "ambiguous_base", "mixed_t_u", "alignment_gaps"}:
            raise RiboAptamerS3Error(
                "proposed accept has unresolved alphabet/gap QC flags"
            )
        try:
            core_len = int(row["sequence_length_core"])
        except ValueError as exc:
            raise RiboAptamerS3Error(
                "proposed accept has non-integer sequence_length_core"
            ) from exc
        if not (20 <= core_len <= 100):
            raise RiboAptamerS3Error(
                "proposed accept core length outside 20–100 nt policy"
            )


def assert_riboaptamer_reject_park_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    seen: dict[str, str] = {}
    for row in decision_rows:
        record_id = row["record_id"]
        route = row.get("primary_route", "")
        if record_id in seen:
            raise RiboAptamerS3Error(f"Duplicate decision record_id {record_id!r}")
        seen[record_id] = route
        decision = row["proposed_decision"]
        primary = row["primary_reason"]
        if primary == "missing_sequence" and decision != "proposed_reject":
            raise RiboAptamerS3Error("missing sequence must never be accepted or parked")
        if primary == "missing_target":
            raise RiboAptamerS3Error(
                "RiboAptamer S3 must not reject missing_target; "
                "target classification is deferred"
            )
        if primary == "non_protein_target_parked":
            raise RiboAptamerS3Error(
                "RiboAptamer S3 must not park from source Type / non-protein routing"
            )
        if primary == "ssdna_parked":
            raise RiboAptamerS3Error(
                "RiboAptamer S3 must not park ssDNA under the RNA source contract"
            )
        if primary == "length_out_of_range" and decision == "proposed_accept":
            raise RiboAptamerS3Error("length_out_of_range must never be accepted")
        if row["checkpoint_status"] != CHECKPOINT_STATUS_PENDING:
            raise RiboAptamerS3Error("Unexpected checkpoint_status at S3")
        if decision not in {
            "proposed_accept",
            "proposed_park",
            "proposed_reject",
        }:
            raise RiboAptamerS3Error(f"Unknown proposed_decision {decision!r}")
        if decision == "proposed_park":
            raise RiboAptamerS3Error(
                "RiboAptamer S3 produced a park; the RNA source contract "
                "expects zero parking at this stage"
            )
        if primary in PLAN_REJECTION_REASONS and decision == "proposed_accept":
            if primary not in {"technically_eligible_rna"}:
                raise RiboAptamerS3Error(
                    f"Closed rejection reason {primary!r} must not be accepted"
                )
        required = row.get("manual_review_required") == "true"
        batch = row.get("review_batch") or ""
        if required and not batch:
            raise RiboAptamerS3Error(
                f"Review-required row missing review_batch: {record_id!r}"
            )
        if (not required) and batch:
            raise RiboAptamerS3Error(
                f"No-review row must not have review_batch: {record_id!r}"
            )
        reasons = set(part for part in (row.get("checkpoint_review_reasons") or "").split("|") if part)
        if REVIEW_REASON_JUDGEMENT in reasons and not required:
            raise RiboAptamerS3Error(
                "Judgement-dependent record must enter CHECKPOINT-1: "
                f"{record_id!r}"
            )

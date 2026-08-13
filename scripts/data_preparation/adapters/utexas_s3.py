"""UTexas S3 adapter: technical sequence/molecule eligibility for CHECKPOINT-1.

Consumes S2 canonical rows and S2 QC sidecars. Assigns one provisional
accept/park/reject decision per record. Does not infer target type from free
text, parse Kd/Affinity, apply leakage exclusions, or authorise records for S4.
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
    "manual_review_required",
    "manual_review_priority",
    "review_batch",
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
    "proposed_decision",
    "primary_reason",
    "secondary_reasons",
    "manual_review_required",
    "manual_review_priority",
    "review_batch",
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
    "notes",
)

GAP_CHARACTERS: Final[frozenset[str]] = frozenset({"-", "."})
NUCLEOTIDE_OR_AMBIGUITY: Final[frozenset[str]] = frozenset("ACGTUNRYWSMKHBVD")
EXPLICIT_DNA_TYPES: Final[frozenset[str]] = frozenset({"ssDNA", "DNA"})

DEFAULT_UTEXAS_BATCHES: Final[tuple[str, ...]] = (
    "01_reject_review",
    "02_accept_with_diagnostics",
    "03_park_unresolved_molecule",
    "04_park_trim_construct",
    "05_repair_alignment_gaps",
)

# Diagnostics never become the primary decision.
DIAGNOSTIC_REASONS: Final[frozenset[EligibilityReason]] = frozenset(
    {
        EligibilityReason.MEDIUM_CONFIDENCE_TRIM,
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
        EligibilityReason.TRIM_COMBINED_EXCEEDS_40PCT,
        EligibilityReason.TRIM_PUSHED_LENGTH_OUT_OF_RANGE,
        EligibilityReason.RANDOM_ACCEPT_AUDIT,
    }
)

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


class UTexasS3Error(ValueError):
    """Hard failure during UTexas S3 eligibility classification."""


@dataclass(frozen=True)
class UTexasS3RowResult:
    """Canonical S3 row plus decision/rejection/park payloads for one record."""

    canonical: dict[str, str]
    decision: dict[str, str]
    eligibility: EligibilityResult
    rejection_row: dict[str, str] | None = None
    park_row: dict[str, str] | None = None


@dataclass
class UTexasS3Stats:
    """Aggregate S3 counts (no sequences or row identifiers)."""

    s2_rows: int = 0
    s3_rows: int = 0
    unique_record_ids: int = 0
    unique_native_ids: int = 0
    order_preserved: bool = False
    decision_counts: dict[str, int] = field(default_factory=dict)
    primary_reason_counts: dict[str, int] = field(default_factory=dict)
    review_priority_counts: dict[str, int] = field(default_factory=dict)
    review_batch_counts: dict[str, int] = field(default_factory=dict)
    manual_review_required_true_count: int = 0
    manual_review_required_false_count: int = 0
    missing_sequence_excluded_from_review_count: int = 0
    missing_sequence_count: int = 0
    non_rna_molecule_count: int = 0
    unknown_molecule_count: int = 0
    mixed_t_u_count: int = 0
    ambiguous_bases_count: int = 0
    invalid_alphabet_count: int = 0
    alignment_gaps_count: int = 0
    length_out_of_range_count: int = 0
    trim_construct_unresolved_count: int = 0
    technically_eligible_rna_count: int = 0
    medium_trim_count: int = 0
    medium_trim_review_count: int = 0
    boundary_low_count: int = 0
    boundary_high_count: int = 0
    boundary_review_count: int = 0
    trim_combined_exceeds_40pct_count: int = 0
    trim_pushed_length_count: int = 0
    random_accept_audit_count: int = 0
    random_accept_audit_pool_size: int = 0
    random_accept_audit_shortfall: int = 0
    multiple_reasons_count: int = 0
    molecule_type_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    alphabet_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    core_length_bucket_by_decision: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    chemistry_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    construct_scope_counts: dict[str, int] = field(default_factory=dict)
    trim_confidence_counts: dict[str, int] = field(default_factory=dict)
    sequence_leakage_count: int = 0
    target_leakage_count: int = 0
    both_leakage_count: int = 0


def _parse_length(raw: str, *, record_id: str, field_name: str) -> int | None:
    text = (raw or "").strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise UTexasS3Error(
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


def _collect_reasons(
    *,
    canonical: Mapping[str, str],
    flags: frozenset[str],
    policy: EligibilityPolicy,
) -> list[EligibilityReason]:
    """Collect every applicable reason without applying precedence."""
    reasons: list[EligibilityReason] = []
    record_id = canonical.get("record_id", "")
    sequence_core = canonical.get("sequence_core", "")
    sequence_full = canonical.get("sequence_full", "")
    missing = sequence_core == ""
    if missing:
        reasons.append(EligibilityReason.MISSING_SEQUENCE)

    molecule = canonical.get("molecule_type", "")
    if molecule in EXPLICIT_DNA_TYPES:
        reasons.append(EligibilityReason.NON_RNA_MOLECULE)
    elif molecule == "unknown" or "molecule_type_unknown" in flags:
        reasons.append(EligibilityReason.MOLECULE_TYPE_UNRESOLVED)
    elif "molecule_type_requires_review" in flags:
        reasons.append(EligibilityReason.MOLECULE_TYPE_UNRESOLVED)

    if "mixed_t_u" in flags:
        reasons.append(EligibilityReason.MIXED_T_AND_U)
    if "ambiguous_base" in flags:
        reasons.append(EligibilityReason.AMBIGUOUS_BASES)

    inspect_seq = sequence_full or sequence_core
    if "invalid_character" in flags:
        if _has_alignment_gaps(inspect_seq):
            reasons.append(EligibilityReason.ALIGNMENT_GAPS)
            if _has_non_gap_invalid(inspect_seq):
                reasons.append(EligibilityReason.INVALID_ALPHABET)
        else:
            reasons.append(EligibilityReason.INVALID_ALPHABET)

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

    trim_unresolved = (
        "trim_requires_review" in flags
        or canonical.get("trim_status") == "constants_suspected_unresolved"
    )
    if trim_unresolved:
        reasons.append(EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED)
    if "trim_combined_exceeds_40pct" in flags:
        reasons.append(EligibilityReason.TRIM_COMBINED_EXCEEDS_40PCT)
        if EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED not in reasons:
            reasons.append(EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED)

    if (canonical.get("trim_confidence") or "").strip() == "medium":
        reasons.append(EligibilityReason.MEDIUM_CONFIDENCE_TRIM)

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

    return reasons


def _select_primary(
    applicable: Sequence[EligibilityReason],
    precedence: Sequence[str],
) -> EligibilityReason | None:
    """Select the highest-precedence primary among decision-level reasons."""
    applicable_set = {
        reason.value for reason in applicable if reason not in DIAGNOSTIC_REASONS
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
        EligibilityReason.NON_RNA_MOLECULE: policy.non_rna_molecule_decision,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED: policy.unknown_molecule_decision,
        EligibilityReason.MIXED_T_AND_U: policy.mixed_t_u_decision,
        EligibilityReason.AMBIGUOUS_BASES: policy.ambiguous_sequence_decision,
        EligibilityReason.ALIGNMENT_GAPS: policy.alignment_gaps_decision,
        EligibilityReason.INVALID_ALPHABET: policy.invalid_sequence_decision,
        EligibilityReason.LENGTH_OUT_OF_RANGE: policy.length_out_of_range_decision,
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED: policy.trim_review_decision,
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA: policy.eligible_rna_decision,
    }
    if reason not in mapping:
        raise UTexasS3Error(f"No decision mapping for primary reason {reason.value}")
    return EligibilityDecision(mapping[reason])


def _is_technically_eligible_rna(
    *,
    canonical: Mapping[str, str],
    applicable: Sequence[EligibilityReason],
    policy: EligibilityPolicy,
) -> bool:
    blocking = {
        EligibilityReason.MISSING_SEQUENCE,
        EligibilityReason.NON_RNA_MOLECULE,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED,
        EligibilityReason.MIXED_T_AND_U,
        EligibilityReason.AMBIGUOUS_BASES,
        EligibilityReason.ALIGNMENT_GAPS,
        EligibilityReason.INVALID_ALPHABET,
        EligibilityReason.LENGTH_OUT_OF_RANGE,
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED,
    }
    if set(applicable) & blocking:
        return False
    if canonical.get("molecule_type") != "RNA":
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


def assign_manual_review_priority(
    *,
    proposed_decision: EligibilityDecision,
    primary_reason: EligibilityReason,
    all_reasons: Sequence[EligibilityReason],
    policy: EligibilityPolicy,
) -> ManualReviewPriority:
    """Assign review priority; never overrides the proposed decision."""
    reason_set = set(all_reasons)

    if primary_reason == EligibilityReason.MISSING_SEQUENCE:
        return ManualReviewPriority.NONE

    if primary_reason == EligibilityReason.NON_RNA_MOLECULE:
        if policy.explicit_non_rna_requires_manual_review:
            return ManualReviewPriority.MEDIUM
        return ManualReviewPriority.NONE

    if primary_reason == EligibilityReason.ALIGNMENT_GAPS:
        return ManualReviewPriority.HIGH
    if primary_reason in {
        EligibilityReason.MIXED_T_AND_U,
        EligibilityReason.AMBIGUOUS_BASES,
        EligibilityReason.INVALID_ALPHABET,
    }:
        return ManualReviewPriority.NONE

    if primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE:
        if reason_set & {
            EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED,
            EligibilityReason.TRIM_PUSHED_LENGTH_OUT_OF_RANGE,
            EligibilityReason.TRIM_COMBINED_EXCEEDS_40PCT,
        }:
            return ManualReviewPriority.HIGH
        return ManualReviewPriority.NONE

    if primary_reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED:
        return ManualReviewPriority.HIGH
    if primary_reason == EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED:
        return ManualReviewPriority.HIGH

    if (
        proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
        and primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
    ):
        if EligibilityReason.MEDIUM_CONFIDENCE_TRIM in reason_set:
            return ManualReviewPriority.MEDIUM
        if reason_set & {
            EligibilityReason.LOWER_LENGTH_BOUNDARY,
            EligibilityReason.UPPER_LENGTH_BOUNDARY,
        }:
            return ManualReviewPriority.LOW
        return ManualReviewPriority.NONE

    return ManualReviewPriority.LOW


def assign_utexas_review_batch(
    *,
    proposed_decision: EligibilityDecision,
    primary_reason: EligibilityReason,
    all_reasons: Sequence[EligibilityReason],
    manual_review_required: bool,
) -> str:
    """Assign exactly one active-review batch, or blank if no review."""
    if not manual_review_required:
        return ""

    reason_set = set(all_reasons)
    if primary_reason == EligibilityReason.ALIGNMENT_GAPS:
        return "05_repair_alignment_gaps"
    if primary_reason == EligibilityReason.MOLECULE_TYPE_UNRESOLVED:
        return "03_park_unresolved_molecule"
    if primary_reason == EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED:
        return "04_park_trim_construct"
    if primary_reason == EligibilityReason.LENGTH_OUT_OF_RANGE and (
        reason_set
        & {
            EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED,
            EligibilityReason.TRIM_COMBINED_EXCEEDS_40PCT,
        }
    ):
        return "04_park_trim_construct"
    if (
        proposed_decision == EligibilityDecision.PROPOSED_REJECT
        and primary_reason != EligibilityReason.MISSING_SEQUENCE
    ):
        return "01_reject_review"
    if proposed_decision == EligibilityDecision.PROPOSED_ACCEPT:
        return "02_accept_with_diagnostics"
    raise UTexasS3Error(
        "Review-required record belongs to no UTexas batch: "
        f"decision={proposed_decision.value} primary={primary_reason.value}"
    )


def classify_utexas_record(
    s2_record: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: EligibilityPolicy,
) -> UTexasS3RowResult:
    """Apply deterministic UTexas S3 technical-eligibility rules to one record."""
    record_id = s2_record["record_id"]
    if record_id != s2_qc.get("record_id", ""):
        raise UTexasS3Error("canonical and S2 QC record_id mismatch")
    if record_id != source_metadata.get("record_id", ""):
        raise UTexasS3Error("canonical and source-metadata record_id mismatch")

    for field_name in S3_FORBIDDEN_FIELDS:
        if (s2_record.get(field_name) or "") != "":
            raise UTexasS3Error(
                f"S3 must not receive populated later-stage field {field_name!r}"
            )

    flags = parse_qc_flags(s2_record.get("qc_flags", ""))
    applicable = _collect_reasons(
        canonical=s2_record, flags=flags, policy=policy
    )
    eligible = _is_technically_eligible_rna(
        canonical=s2_record, applicable=applicable, policy=policy
    )
    if eligible:
        applicable.append(EligibilityReason.TECHNICALLY_ELIGIBLE_RNA)

    primary = _select_primary(applicable, policy.decision_precedence)
    if primary is None:
        raise UTexasS3Error(
            f"No eligibility reason resolved for record_id={record_id!r}"
        )
    proposed = _decision_for_reason(primary, policy)
    secondary = [reason for reason in applicable if reason != primary]
    priority = assign_manual_review_priority(
        proposed_decision=proposed,
        primary_reason=primary,
        all_reasons=applicable,
        policy=policy,
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
    review_batch = assign_utexas_review_batch(
        proposed_decision=proposed,
        primary_reason=primary,
        all_reasons=eligibility.all_reasons,
        manual_review_required=eligibility.manual_review_required,
    )

    if proposed == EligibilityDecision.PROPOSED_ACCEPT:
        if not eligible or primary != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA:
            raise UTexasS3Error(
                f"Accept proposed without technical RNA eligibility: {record_id!r}"
            )
        if s2_record.get("molecule_type") != "RNA":
            raise UTexasS3Error(f"Non-RNA must not be accepted: {record_id!r}")
        if s2_record.get("sequence_core", "") == "":
            raise UTexasS3Error(f"Missing sequence must not be accepted: {record_id!r}")
        if EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED in eligibility.all_reasons:
            raise UTexasS3Error(
                f"Unresolved trim/construct must not be accepted: {record_id!r}"
            )

    if primary == EligibilityReason.MISSING_SEQUENCE and proposed != (
        EligibilityDecision.PROPOSED_REJECT
    ):
        raise UTexasS3Error(f"Missing sequence must be rejected: {record_id!r}")

    if eligibility.manual_review_required and not review_batch:
        raise UTexasS3Error(
            f"Review-required record missing review_batch: {record_id!r}"
        )
    if (not eligibility.manual_review_required) and review_batch:
        raise UTexasS3Error(
            f"No-review record must not have a review_batch: {record_id!r}"
        )

    canonical = validate_s3_record(dict(s2_record), s2_record=s2_record)
    decision = _build_decision_row(
        canonical=canonical,
        s2_qc=s2_qc,
        eligibility=eligibility,
        review_batch=review_batch,
    )
    rejection_row = None
    park_row = None
    if proposed == EligibilityDecision.PROPOSED_REJECT:
        rejection_row = _build_rejection_row(canonical=canonical, decision=decision)
    elif proposed == EligibilityDecision.PROPOSED_PARK:
        park_row = _build_park_row(canonical=canonical, decision=decision)

    return UTexasS3RowResult(
        canonical=canonical,
        decision=decision,
        eligibility=eligibility,
        rejection_row=rejection_row,
        park_row=park_row,
    )


def _build_decision_row(
    *,
    canonical: Mapping[str, str],
    s2_qc: Mapping[str, str],
    eligibility: EligibilityResult,
    review_batch: str,
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamer_name": s2_qc.get("aptamer_name") or "",
        "target_name_raw": canonical["target_name_raw"],
        "proposed_decision": eligibility.proposed_decision.value,
        "primary_reason": eligibility.primary_reason.value,
        "secondary_reasons": format_reasons(eligibility.secondary_reasons),
        "manual_review_required": (
            "true" if eligibility.manual_review_required else "false"
        ),
        "manual_review_priority": eligibility.manual_review_priority.value,
        "review_batch": review_batch,
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
        "notes": "",
    }


def _build_rejection_row(
    *,
    canonical: Mapping[str, str],
    decision: Mapping[str, str],
) -> dict[str, str]:
    reason = decision["primary_reason"]
    if reason not in PLAN_REJECTION_REASONS:
        raise UTexasS3Error(
            f"Rejection reason {reason!r} is not in the plan closed vocabulary"
        )
    detail_parts = [
        part for part in (decision.get("secondary_reasons") or "").split("|") if part
    ]
    return {
        "record_id": canonical["record_id"],
        "source_db": canonical.get("source_db", "utexas"),
        "source_dataset": canonical.get("source_dataset", ""),
        "native_id": canonical["native_id"],
        "sequence_raw": canonical.get("sequence_raw", ""),
        "target_name_raw": canonical.get("target_name_raw", ""),
        "stage": "S3",
        "rejection_reason": reason,
        "rejection_detail": format_reasons(detail_parts),
    }


def _build_park_row(
    *,
    canonical: Mapping[str, str],
    decision: Mapping[str, str],
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
        "sequence_length_core": canonical.get("sequence_length_core", ""),
        "trim_status": canonical.get("trim_status", ""),
        "trim_confidence": canonical.get("trim_confidence", ""),
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
        "aptamer_name": s2_qc.get("aptamer_name") or decision.get("aptamer_name", ""),
        "target_name_raw": canonical.get("target_name_raw", ""),
        "publication": canonical.get("publication", ""),
        "proposed_decision": decision.get("proposed_decision", ""),
        "primary_reason": decision.get("primary_reason", ""),
        "secondary_reasons": decision.get("secondary_reasons", ""),
        "manual_review_required": decision.get("manual_review_required", ""),
        "manual_review_priority": decision.get("manual_review_priority", ""),
        "review_batch": decision.get("review_batch", ""),
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
        "notes": decision.get("notes", ""),
    }


def apply_random_accept_audit(
    decision_rows: list[dict[str, str]],
    local_detail_by_id: dict[str, dict[str, str]],
    *,
    seed: int,
    sample_size: int,
) -> tuple[int, int, int]:
    """Mark a seeded sample of clean accepts for eyeballing.

    Returns ``(selected_count, pool_size, shortfall)``.
    """
    if sample_size < 0:
        raise UTexasS3Error("random_accept_audit_size must be non-negative")
    candidates = [
        row
        for row in decision_rows
        if row["proposed_decision"] == "proposed_accept"
        and row["manual_review_required"] == "false"
        and row["primary_reason"] == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value
        and not row.get("review_batch")
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
        row["manual_review_required"] = "true"
        row["manual_review_priority"] = ManualReviewPriority.LOW.value
        row["review_batch"] = "02_accept_with_diagnostics"
        detail = local_detail_by_id.get(row["record_id"])
        if detail is not None:
            detail["secondary_reasons"] = row["secondary_reasons"]
            detail["manual_review_required"] = "true"
            detail["manual_review_priority"] = ManualReviewPriority.LOW.value
            detail["review_batch"] = "02_accept_with_diagnostics"

    return take, pool_size, shortfall


def update_stats_from_row(stats: UTexasS3Stats, row: UTexasS3RowResult) -> None:
    """Accumulate aggregate counters from one classified row."""
    decision = row.eligibility.proposed_decision.value
    primary = row.eligibility.primary_reason.value
    priority = row.eligibility.manual_review_priority.value
    molecule = row.canonical.get("molecule_type") or "unknown"
    alphabet = row.canonical.get("alphabet_as_reported") or "missing"
    chemistry = row.canonical.get("chemistry") or "unknown"
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
    if EligibilityReason.NON_RNA_MOLECULE in reasons:
        stats.non_rna_molecule_count += 1
    if EligibilityReason.MOLECULE_TYPE_UNRESOLVED in reasons:
        stats.unknown_molecule_count += 1
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
    if EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED in reasons:
        stats.trim_construct_unresolved_count += 1
    if EligibilityReason.TECHNICALLY_ELIGIBLE_RNA in reasons:
        stats.technically_eligible_rna_count += 1
    if EligibilityReason.MEDIUM_CONFIDENCE_TRIM in reasons:
        stats.medium_trim_count += 1
        if row.eligibility.manual_review_required:
            stats.medium_trim_review_count += 1
    if EligibilityReason.LOWER_LENGTH_BOUNDARY in reasons:
        stats.boundary_low_count += 1
    if EligibilityReason.UPPER_LENGTH_BOUNDARY in reasons:
        stats.boundary_high_count += 1
    if reasons & {
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
    } and row.eligibility.manual_review_required:
        stats.boundary_review_count += 1
    if EligibilityReason.TRIM_COMBINED_EXCEEDS_40PCT in reasons:
        stats.trim_combined_exceeds_40pct_count += 1
    if EligibilityReason.TRIM_PUSHED_LENGTH_OUT_OF_RANGE in reasons:
        stats.trim_pushed_length_count += 1
    if EligibilityReason.RANDOM_ACCEPT_AUDIT in reasons:
        stats.random_accept_audit_count += 1
    if len(row.eligibility.all_reasons) > 1:
        stats.multiple_reasons_count += 1

    mol_map = stats.molecule_type_by_decision.setdefault(decision, {})
    mol_map[molecule] = mol_map.get(molecule, 0) + 1
    alph_map = stats.alphabet_by_decision.setdefault(decision, {})
    alph_map[alphabet] = alph_map.get(alphabet, 0) + 1
    chem_map = stats.chemistry_by_decision.setdefault(decision, {})
    chem_map[chemistry] = chem_map.get(chemistry, 0) + 1
    bucket = _core_length_bucket(core_len)
    len_map = stats.core_length_bucket_by_decision.setdefault(decision, {})
    len_map[bucket] = len_map.get(bucket, 0) + 1

    scope = row.canonical.get("construct_scope") or "(empty)"
    stats.construct_scope_counts[scope] = (
        stats.construct_scope_counts.get(scope, 0) + 1
    )
    trim_conf = row.canonical.get("trim_confidence") or "(empty)"
    stats.trim_confidence_counts[trim_conf] = (
        stats.trim_confidence_counts.get(trim_conf, 0) + 1
    )


def refresh_stats_after_audit(
    stats: UTexasS3Stats, decision_rows: Sequence[Mapping[str, str]]
) -> None:
    """Recompute review-dependent counters after the random-accept audit."""
    stats.manual_review_required_true_count = 0
    stats.manual_review_required_false_count = 0
    stats.review_batch_counts = {}
    stats.review_priority_counts = {}
    stats.random_accept_audit_count = 0
    stats.medium_trim_review_count = 0
    stats.boundary_review_count = 0
    for row in decision_rows:
        required = row.get("manual_review_required") == "true"
        if required:
            stats.manual_review_required_true_count += 1
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
        secondaries = {
            part for part in (row.get("secondary_reasons") or "").split("|") if part
        }
        if EligibilityReason.RANDOM_ACCEPT_AUDIT.value in secondaries:
            stats.random_accept_audit_count += 1
        if required and EligibilityReason.MEDIUM_CONFIDENCE_TRIM.value in secondaries:
            stats.medium_trim_review_count += 1
        if required and (
            EligibilityReason.LOWER_LENGTH_BOUNDARY.value in secondaries
            or EligibilityReason.UPPER_LENGTH_BOUNDARY.value in secondaries
            or row.get("primary_reason")
            in {
                EligibilityReason.LOWER_LENGTH_BOUNDARY.value,
                EligibilityReason.UPPER_LENGTH_BOUNDARY.value,
            }
        ):
            stats.boundary_review_count += 1


def assert_utexas_accept_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    """Hard-fail if any proposed accept violates RNA technical eligibility."""
    for row in decision_rows:
        if row["proposed_decision"] != "proposed_accept":
            continue
        if row["molecule_type"] != "RNA":
            raise UTexasS3Error("proposed accept contains non-RNA molecule_type")
        if row["primary_reason"] != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value:
            raise UTexasS3Error(
                "proposed accept primary_reason must be technically_eligible_rna"
            )
        flags = parse_qc_flags(row.get("qc_flags", ""))
        if flags & {"invalid_character", "ambiguous_base", "mixed_t_u"}:
            raise UTexasS3Error("proposed accept has unresolved alphabet QC flags")
        if "trim_requires_review" in flags:
            raise UTexasS3Error("proposed accept still has trim_requires_review")
        try:
            core_len = int(row["sequence_length_core"])
        except ValueError as exc:
            raise UTexasS3Error(
                "proposed accept has non-integer sequence_length_core"
            ) from exc
        if not (20 <= core_len <= 100):
            raise UTexasS3Error(
                "proposed accept core length outside 20–100 nt policy"
            )


def assert_utexas_reject_park_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    for row in decision_rows:
        decision = row["proposed_decision"]
        primary = row["primary_reason"]
        if primary == "missing_sequence" and decision != "proposed_reject":
            raise UTexasS3Error("missing sequence must never be accepted or parked")
        if primary == "non_rna_molecule" and decision == "proposed_accept":
            raise UTexasS3Error("explicit DNA/ssDNA must never be accepted")
        if primary == "molecule_type_unresolved" and decision == "proposed_accept":
            raise UTexasS3Error("unresolved molecule type must never be accepted")
        if primary == "length_out_of_range" and decision == "proposed_accept":
            raise UTexasS3Error("length_out_of_range must never be accepted")
        if row["checkpoint_status"] != CHECKPOINT_STATUS_PENDING:
            raise UTexasS3Error("Unexpected checkpoint_status at S3")
        if decision not in {
            "proposed_accept",
            "proposed_park",
            "proposed_reject",
        }:
            raise UTexasS3Error(f"Unknown proposed_decision {decision!r}")
        required = row.get("manual_review_required")
        if required not in {"true", "false"}:
            raise UTexasS3Error("manual_review_required must be lowercase true/false")
        if required == "true" and not row.get("review_batch"):
            raise UTexasS3Error("Active review row missing review_batch")
        if required == "false" and row.get("review_batch"):
            raise UTexasS3Error("Mechanical row must not carry a review_batch")
        for forbidden in (
            "target_type",
            "target_name",
            "binding_evidence_score",
            "affinity_value",
            "cluster_id",
            "partition",
        ):
            if forbidden in row and row[forbidden]:
                raise UTexasS3Error(
                    f"S3 decision sidecar must not populate {forbidden}"
                )

"""AptaDiff Dataset A/B S3 adapter: technical eligibility for CHECKPOINT-1.

Two distinct source identities share scientifically neutral S3 helpers.
They do not share a combined ``aptadiff`` output. Technical sequence failure
precedes otherwise-valid ssDNA parking. Constant-region inference remains
disabled. Targets, evidence, affinity, leakage, p6 ranking, and Dataset-A
replication are not evaluated here.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Final, Mapping, Sequence

from adapters.aptadiff import APTADIFF_SOURCE_KEYS, SOURCE_PROFILES
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
    "sequence_length_full",
    "sequence_length_core",
    "construct_scope",
    "trim_status",
    "trim_confidence",
    "qc_flags",
    "aptadiff_dataset",
    "aptadiff_documented_target",
    "aptadiff_p6",
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
    "aptadiff_dataset",
    "aptadiff_documented_target",
    "aptadiff_p6",
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

DEFAULT_APTADIFF_BATCHES: Final[tuple[str, ...]] = (
    "01_judgement_dependent_technical",
    "02_constant_region_proposal",
    "03_length_boundary",
    "04_random_kept_audit",
)

REJECTION_STAGE: Final[str] = "S3"
EXPLICIT_DNA_TYPES: Final[frozenset[str]] = frozenset({"ssDNA", "DNA"})
GAP_CHARACTERS: Final[frozenset[str]] = frozenset({"-", "."})
NUCLEOTIDE_OR_AMBIGUITY: Final[frozenset[str]] = frozenset("ACGTUNRYWSMKHBVD")

PRIMARY_ROUTE_REJECT: Final[str] = "technical_reject"
PRIMARY_ROUTE_SSDNA: Final[str] = "parked_ssdna"
PRIMARY_ROUTE_ELIGIBLE: Final[str] = "technically_eligible"

PLAN_REJECTION_REASONS: Final[frozenset[str]] = frozenset(
    {
        "missing_sequence",
        "length_out_of_range",
        "ambiguous_bases",
        "invalid_alphabet",
        "mixed_T_and_U",
        "alignment_gaps",
        "ssdna_parked",
    }
)

DIAGNOSTIC_REASONS: Final[frozenset[EligibilityReason]] = frozenset(
    {
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
        EligibilityReason.RANDOM_ACCEPT_AUDIT,
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED,
        EligibilityReason.CONSTANT_REGION_PROPOSAL,
        EligibilityReason.KNOWN_MOTIF_PROPOSAL,
    }
)

# AptaDiff N-containing rows are the only genuine scientific exceptions.
# They remain experimentally ssDNA, but the unresolved IUPAC N is a
# technical sequence failure that must be confirmed at CHECKPOINT-1.
JUDGEMENT_DEPENDENT_REASONS: Final[frozenset[EligibilityReason]] = frozenset(
    {
        EligibilityReason.AMBIGUOUS_BASES,
        EligibilityReason.MIXED_T_AND_U,
        EligibilityReason.INVALID_ALPHABET,
        EligibilityReason.ALIGNMENT_GAPS,
    }
)

REVIEW_REASON_JUDGEMENT: Final[str] = "judgement_dependent_technical"
REVIEW_REASON_CONSTANT: Final[str] = "constant_region_proposal"
REVIEW_REASON_BOUNDARY: Final[str] = "length_boundary"
REVIEW_REASON_RANDOM: Final[str] = "random_kept_audit"


class AptaDiffS3Error(ValueError):
    """Hard failure during AptaDiff S3 eligibility classification."""


@dataclass(frozen=True)
class AptaDiffS3RowResult:
    """Canonical S3 row plus decision/rejection/park payloads for one record."""

    canonical: dict[str, str]
    decision: dict[str, str]
    eligibility: EligibilityResult
    rejection_row: dict[str, str] | None = None
    park_row: dict[str, str] | None = None
    primary_route: str = ""


@dataclass
class AptaDiffS3Stats:
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
    ssdna_parked_count: int = 0
    technically_eligible_rna_count: int = 0
    source_ssdna_before_technical: int = 0
    technically_rejected_ssdna: int = 0
    t_to_u_applied_count: int = 0
    applied_trims: int = 0
    trim_construct_unresolved_count: int = 0
    constant_region_proposals: int = 0
    length_36_count: int = 0
    nonempty_target_name_raw: int = 0
    nonempty_evidence_or_affinity: int = 0
    nonempty_canonical_target_fields: int = 0
    sequence_repaired_count: int = 0
    judgement_dependent_review_count: int = 0
    constant_review_count: int = 0
    boundary_review_count: int = 0
    random_accept_audit_count: int = 0
    random_accept_audit_pool_size: int = 0
    random_accept_audit_shortfall: int = 0
    unique_checkpoint_review_records: int = 0
    multiple_reasons_count: int = 0
    molecule_type_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    alphabet_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
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
        raise AptaDiffS3Error(
            f"Non-integer {field_name} for {record_id!r}"
        ) from exc


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
    """Collect every applicable reason without applying precedence.

    Technical sequence defects are collected before ssDNA parking so that
    malformed DNA is not hidden inside the ordinary parked-ssDNA lane.
    Missing ``target_name_raw`` is not a reason: targets remain deferred.
    ``p6`` is ignored. Constant/trim proposals are not collected.
    """
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

    core_len = _parse_length(
        canonical.get("sequence_length_core", ""),
        record_id=record_id,
        field_name="sequence_length_core",
    )
    if (
        not missing
        and core_len is not None
        and not (policy.core_length_min <= core_len <= policy.core_length_max)
    ):
        reasons.append(EligibilityReason.LENGTH_OUT_OF_RANGE)

    molecule = canonical.get("molecule_type", "")
    if molecule in EXPLICIT_DNA_TYPES:
        reasons.append(EligibilityReason.SSDNA_PARKED)
    elif molecule == "RNA":
        pass
    elif molecule == "unknown" or "molecule_type_unknown" in flags:
        reasons.append(EligibilityReason.MOLECULE_TYPE_UNRESOLVED)
    else:
        raise AptaDiffS3Error(
            f"Unrecognised AptaDiff molecule_type {molecule!r} for {record_id!r}"
        )

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
        EligibilityReason.LENGTH_OUT_OF_RANGE: policy.length_out_of_range_decision,
        EligibilityReason.SSDNA_PARKED: policy.ssdna_decision,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED: policy.unknown_molecule_decision,
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA: policy.eligible_rna_decision,
    }
    if reason not in mapping:
        raise AptaDiffS3Error(f"No decision mapping for primary reason {reason.value}")
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
        EligibilityReason.LENGTH_OUT_OF_RANGE,
        EligibilityReason.SSDNA_PARKED,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED,
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
    raise AptaDiffS3Error(
        "Could not assign a closed AptaDiff primary route for "
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


def assign_aptadiff_review_batch(
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
    raise AptaDiffS3Error(
        "Review-required record belongs to no AptaDiff batch: "
        f"reasons={list(review_reasons)}"
    )


def classify_aptadiff_record(
    s2_record: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: EligibilityPolicy,
) -> AptaDiffS3RowResult:
    """Apply deterministic AptaDiff S3 technical-eligibility rules to one record."""
    record_id = s2_record["record_id"]
    if record_id != s2_qc.get("record_id", ""):
        raise AptaDiffS3Error("canonical and S2 QC record_id mismatch")
    if record_id != source_metadata.get("record_id", ""):
        raise AptaDiffS3Error("canonical and source-metadata record_id mismatch")
    if policy.source_key not in APTADIFF_SOURCE_KEYS:
        raise AptaDiffS3Error(
            f"policy source_key must be aptadiff_a or aptadiff_b; "
            f"got {policy.source_key!r}"
        )
    if s2_record.get("source_db") != policy.source_key:
        raise AptaDiffS3Error(
            f"source_db must be {policy.source_key}; "
            f"got {s2_record.get('source_db')!r}"
        )

    for field_name in S3_FORBIDDEN_FIELDS:
        if (s2_record.get(field_name) or "") != "":
            raise AptaDiffS3Error(
                f"S3 must not receive populated later-stage field {field_name!r}"
            )

    flags = parse_qc_flags(s2_record.get("qc_flags", ""))
    applicable = _collect_reasons(
        canonical=s2_record,
        flags=flags,
        policy=policy,
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
        raise AptaDiffS3Error(
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
    review_reasons = _checkpoint_review_reasons(eligibility.all_reasons)
    review_batch = assign_aptadiff_review_batch(
        review_reasons=review_reasons,
        manual_review_required=eligibility.manual_review_required,
    )
    primary_route = _primary_route(proposed, primary)

    if proposed == EligibilityDecision.PROPOSED_ACCEPT:
        if not eligible or primary != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA:
            raise AptaDiffS3Error(
                f"Accept proposed without RNA eligibility: {record_id!r}"
            )
        if s2_record.get("molecule_type") != "RNA":
            raise AptaDiffS3Error(f"Non-RNA must not be accepted: {record_id!r}")

    if primary == EligibilityReason.MISSING_SEQUENCE and proposed != (
        EligibilityDecision.PROPOSED_REJECT
    ):
        raise AptaDiffS3Error(f"Missing sequence must be rejected: {record_id!r}")
    if primary == EligibilityReason.SSDNA_PARKED and proposed != (
        EligibilityDecision.PROPOSED_PARK
    ):
        raise AptaDiffS3Error(f"ssDNA must be parked when technically valid: {record_id!r}")
    if primary == EligibilityReason.AMBIGUOUS_BASES and proposed != (
        EligibilityDecision.PROPOSED_REJECT
    ):
        raise AptaDiffS3Error(
            f"Ambiguous-base ssDNA must be a technical reject: {record_id!r}"
        )

    sequence_full = s2_record.get("sequence_full", "")
    sequence_core = s2_record.get("sequence_core", "")
    if sequence_full != s2_record.get("sequence_raw", "") and sequence_full:
        # S2 may uppercase; it must not repair N or transcribe T→U.
        if "N" in s2_record.get("sequence_raw", "") and "N" not in sequence_full:
            raise AptaDiffS3Error(
                f"S3 must not receive an N-repaired sequence: {record_id!r}"
            )
    if s2_record.get("t_to_u_applied") == "true":
        raise AptaDiffS3Error(
            f"AptaDiff S3 must not receive T→U-transcribed rows: {record_id!r}"
        )
    if sequence_core != sequence_full:
        raise AptaDiffS3Error(
            f"AptaDiff S3 requires sequence_core == sequence_full: {record_id!r}"
        )

    if eligibility.manual_review_required and not review_batch:
        raise AptaDiffS3Error(
            f"Review-required record missing review_batch: {record_id!r}"
        )
    if (not eligibility.manual_review_required) and review_batch:
        raise AptaDiffS3Error(
            f"No-review record must not have a review_batch: {record_id!r}"
        )

    canonical = validate_s3_record(dict(s2_record), s2_record=s2_record)
    if canonical.get("sequence_core") != s2_record.get("sequence_core"):
        raise AptaDiffS3Error("S3 must not alter sequence_core")
    if canonical.get("sequence_full") != s2_record.get("sequence_full"):
        raise AptaDiffS3Error("S3 must not alter sequence_full")
    if canonical.get("t_to_u_applied") != s2_record.get("t_to_u_applied"):
        raise AptaDiffS3Error("S3 must not alter t_to_u_applied")

    decision = _build_decision_row(
        canonical=canonical,
        s2_qc=s2_qc,
        source_metadata=source_metadata,
        eligibility=eligibility,
        review_batch=review_batch,
        review_reasons=review_reasons,
        primary_route=primary_route,
    )
    rejection_row = None
    park_row = None
    if proposed == EligibilityDecision.PROPOSED_REJECT:
        rejection_row = _build_rejection_row(canonical=canonical, decision=decision)
    elif proposed == EligibilityDecision.PROPOSED_PARK:
        park_row = _build_park_row(canonical=canonical, decision=decision)

    return AptaDiffS3RowResult(
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
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "construct_scope": canonical["construct_scope"],
        "trim_status": canonical["trim_status"],
        "trim_confidence": canonical.get("trim_confidence", ""),
        "qc_flags": canonical["qc_flags"],
        "aptadiff_dataset": (
            s2_qc.get("aptadiff_dataset")
            or source_metadata.get("aptadiff_dataset")
            or ""
        ),
        "aptadiff_documented_target": (
            s2_qc.get("aptadiff_documented_target")
            or source_metadata.get("aptadiff_documented_target")
            or ""
        ),
        "aptadiff_p6": (
            s2_qc.get("aptadiff_p6") or source_metadata.get("aptadiff_p6") or ""
        ),
        "notes": "",
    }


def _build_rejection_row(
    *,
    canonical: Mapping[str, str],
    decision: Mapping[str, str],
) -> dict[str, str]:
    reason = decision["primary_reason"]
    if reason not in PLAN_REJECTION_REASONS:
        raise AptaDiffS3Error(
            f"Rejection reason {reason!r} is not in the plan closed vocabulary"
        )
    detail_parts = [
        part for part in (decision.get("secondary_reasons") or "").split("|") if part
    ]
    return {
        "record_id": canonical["record_id"],
        "source_db": canonical.get("source_db", ""),
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
    source_metadata: Mapping[str, str],
    decision: Mapping[str, str],
) -> dict[str, str]:
    """Build one sequence-bearing local-detail review row."""
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "target_name_raw": canonical.get("target_name_raw", ""),
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
        "aptadiff_dataset": decision.get("aptadiff_dataset", "")
        or s2_qc.get("aptadiff_dataset", "")
        or source_metadata.get("aptadiff_dataset", ""),
        "aptadiff_documented_target": decision.get("aptadiff_documented_target", "")
        or s2_qc.get("aptadiff_documented_target", "")
        or source_metadata.get("aptadiff_documented_target", ""),
        "aptadiff_p6": decision.get("aptadiff_p6", "")
        or s2_qc.get("aptadiff_p6", "")
        or source_metadata.get("aptadiff_p6", ""),
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

    Returns ``(selected_count, pool_size, shortfall)``. AptaDiff has no
    RNA-eligible pool; the shortfall is documented rather than fabricating
    a random-kept audit from parked ssDNA.
    """
    if sample_size < 0:
        raise AptaDiffS3Error("random_accept_audit_size must be non-negative")
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
            row["review_batch"] = assign_aptadiff_review_batch(
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


def update_stats_from_row(stats: AptaDiffS3Stats, row: AptaDiffS3RowResult) -> None:
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
    if (
        row.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
        and row.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    ):
        stats.missing_sequence_excluded_from_review_count += 1

    if molecule in EXPLICIT_DNA_TYPES:
        stats.source_ssdna_before_technical += 1
        if row.primary_route == PRIMARY_ROUTE_REJECT:
            stats.technically_rejected_ssdna += 1

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
    if row.primary_route == PRIMARY_ROUTE_SSDNA:
        stats.ssdna_parked_count += 1
    if EligibilityReason.TECHNICALLY_ELIGIBLE_RNA in reasons:
        stats.technically_eligible_rna_count += 1
    if EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED in reasons:
        stats.trim_construct_unresolved_count += 1
    if len(row.eligibility.all_reasons) > 1:
        stats.multiple_reasons_count += 1

    if row.canonical.get("t_to_u_applied") == "true":
        stats.t_to_u_applied_count += 1
    if row.canonical.get("sequence_core") != row.canonical.get("sequence_full"):
        stats.applied_trims += 1
    if (row.canonical.get("sequence_length_core") or "") == "36":
        stats.length_36_count += 1
    if row.canonical.get("target_name_raw"):
        stats.nonempty_target_name_raw += 1
    if any(row.canonical.get(field) for field in S3_FORBIDDEN_FIELDS):
        stats.nonempty_canonical_target_fields += 1
        affinity_fields = (
            "affinity_value",
            "affinity_unit",
            "affinity_type",
            "binding_evidence_type",
            "binding_evidence_score",
        )
        if any(row.canonical.get(field) for field in affinity_fields):
            stats.nonempty_evidence_or_affinity += 1
    raw = row.canonical.get("sequence_raw", "")
    full = row.canonical.get("sequence_full", "")
    if "N" in raw.upper() and "N" not in full.upper() and full:
        stats.sequence_repaired_count += 1

    mol_map = stats.molecule_type_by_decision.setdefault(decision, {})
    mol_map[molecule] = mol_map.get(molecule, 0) + 1
    alph_map = stats.alphabet_by_decision.setdefault(decision, {})
    alph_map[alphabet] = alph_map.get(alphabet, 0) + 1


def refresh_stats_after_audit(
    stats: AptaDiffS3Stats, decision_rows: Sequence[Mapping[str, str]]
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


def assert_aptadiff_accept_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    """Hard-fail if any proposed accept violates RNA eligibility."""
    for row in decision_rows:
        if row["proposed_decision"] != "proposed_accept":
            continue
        if row["molecule_type"] != "RNA":
            raise AptaDiffS3Error("proposed accept contains non-RNA molecule_type")
        if row["primary_reason"] != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value:
            raise AptaDiffS3Error(
                "proposed accept primary_reason must be technically_eligible_rna"
            )
        if row.get("primary_route") != PRIMARY_ROUTE_ELIGIBLE:
            raise AptaDiffS3Error("proposed accept primary_route mismatch")


def assert_aptadiff_reject_park_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    seen: dict[str, str] = {}
    for row in decision_rows:
        record_id = row["record_id"]
        route = row.get("primary_route", "")
        if record_id in seen:
            raise AptaDiffS3Error(f"Duplicate decision record_id {record_id!r}")
        seen[record_id] = route
        decision = row["proposed_decision"]
        primary = row["primary_reason"]
        if primary == "missing_sequence" and decision != "proposed_reject":
            raise AptaDiffS3Error("missing sequence must never be accepted or parked")
        if primary == "ssdna_parked" and decision != "proposed_park":
            raise AptaDiffS3Error("ssdna_parked must be a park")
        if primary == "ambiguous_bases" and decision != "proposed_reject":
            raise AptaDiffS3Error("ambiguous_bases must be a technical reject")
        if primary == "length_out_of_range" and decision == "proposed_accept":
            raise AptaDiffS3Error("length_out_of_range must never be accepted")
        if row["checkpoint_status"] != CHECKPOINT_STATUS_PENDING:
            raise AptaDiffS3Error("Unexpected checkpoint_status at S3")
        if decision not in {
            "proposed_accept",
            "proposed_park",
            "proposed_reject",
        }:
            raise AptaDiffS3Error(f"Unknown proposed_decision {decision!r}")
        if route not in {
            PRIMARY_ROUTE_REJECT,
            PRIMARY_ROUTE_SSDNA,
            PRIMARY_ROUTE_ELIGIBLE,
        }:
            raise AptaDiffS3Error(f"Unknown primary_route {route!r}")
        required = row.get("manual_review_required")
        if required not in {"true", "false"}:
            raise AptaDiffS3Error("manual_review_required must be lowercase true/false")
        if required == "true" and not row.get("review_batch"):
            raise AptaDiffS3Error("Active review row missing review_batch")
        if required == "false" and row.get("review_batch"):
            raise AptaDiffS3Error("Mechanical row must not carry a review_batch")
        if (
            primary == "ssdna_parked"
            and required == "true"
            and "judgement_dependent_technical"
            not in (row.get("checkpoint_review_reasons") or "")
            and "length_boundary"
            not in (row.get("checkpoint_review_reasons") or "")
            and "constant_region_proposal"
            not in (row.get("checkpoint_review_reasons") or "")
        ):
            raise AptaDiffS3Error(
                "Ordinary clean ssDNA parks must not require manual review"
            )
        for forbidden in S3_FORBIDDEN_FIELDS:
            if forbidden in row and row[forbidden]:
                raise AptaDiffS3Error(
                    f"S3 decision sidecar must not populate {forbidden}"
                )
        if row.get("manual_decision"):
            raise AptaDiffS3Error("S3 must not pre-fill a human manual_decision")
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
                raise AptaDiffS3Error(
                    f"S3 must not pre-fill human field {field_name}"
                )


def expected_documented_target(source_key: str) -> str:
    """Return the sidecar-only documented target for one AptaDiff source."""
    try:
        return SOURCE_PROFILES[source_key].documented_target
    except KeyError as exc:
        raise AptaDiffS3Error(
            f"Unknown AptaDiff source_key={source_key!r}"
        ) from exc

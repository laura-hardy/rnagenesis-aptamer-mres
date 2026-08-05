"""AptaBase S3 adapter: provisional eligibility decisions for CHECKPOINT-1.

Consumes S2 canonical rows, S2 QC sidecars and AptaBase source-metadata rows.
Does not import the legacy AptaBase cleaner. Does not normalise targets, score
evidence, interpret affinity, deduplicate, cluster, balance or partition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Mapping, Sequence

from common.corpus_schema import validate_s3_record
from common.eligibility import (
    CHECKPOINT_STATUS_PENDING,
    EligibilityDecision,
    EligibilityError,
    EligibilityPolicy,
    EligibilityReason,
    EligibilityResult,
    LeakageMatch,
    ManualReviewPriority,
    SequenceLeakageIndex,
    TargetAliasRule,
    TargetLeakageMatch,
    build_eligibility_result,
    format_identity,
    format_reasons,
    match_target_leakage,
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
    "checkpoint_status",
    "molecule_type",
    "alphabet_as_reported",
    "sequence_length_full",
    "sequence_length_core",
    "construct_scope",
    "trim_status",
    "sequence_leakage_match",
    "sequence_leakage_identity",
    "sequence_leakage_reference_id",
    "sequence_leakage_target",
    "target_leakage_match",
    "target_leakage_canonical_target",
    "target_leakage_match_type",
    "source_record_validity",
    "qc_flags",
    "notes",
)

LEAKAGE_MATCH_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "match_scope",
    "matched_reference_id",
    "matched_target",
    "matched_evaluation_role",
    "matched_form",
    "identity",
    "target_match_alias",
    "target_match_type",
    "proposed_decision",
    "primary_reason",
)

REASON_COUNT_COLUMNS: Final[tuple[str, ...]] = (
    "proposed_decision",
    "primary_reason",
    "record_count",
)

# Sequence-bearing scientific review table (ignored under data/; never tracked).
LOCAL_DETAIL_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "aptamer_name",
    "target_name_raw",
    "target_general_raw",
    "target_specific_raw",
    "publication",
    "proposed_decision",
    "primary_reason",
    "secondary_reasons",
    "manual_review_required",
    "manual_review_priority",
    "checkpoint_status",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "sequence_length_full",
    "sequence_length_core",
    "molecule_type",
    "alphabet_as_reported",
    "t_to_u_applied",
    "construct_scope",
    "trim_status",
    "detected_constant_5p",
    "detected_constant_3p",
    "source_record_validity",
    "source_parse_warnings",
    "reported_length_raw",
    "reported_length_difference",
    "gc_reported_raw",
    "gc_calculated_s2",
    "gc_difference_percentage_points",
    "sequence_leakage_match",
    "sequence_leakage_identity",
    "sequence_leakage_reference_id",
    "target_leakage_match",
    "target_leakage_canonical_target",
    "qc_flags",
    "notes",
)


class AptaBaseS3Error(ValueError):
    """Hard failure during AptaBase S3 eligibility classification."""


@dataclass(frozen=True)
class AptaBaseS3RowResult:
    """Canonical S3 row plus decision/leakage sidecar payloads for one record."""

    canonical: dict[str, str]
    decision: dict[str, str]
    eligibility: EligibilityResult
    leakage_rows: tuple[dict[str, str], ...] = ()


@dataclass
class AptaBaseS3Stats:
    """Aggregate S3 counts (no sequences or row identifiers)."""

    s2_rows: int = 0
    s3_rows: int = 0
    unique_record_ids: int = 0
    order_preserved: bool = False
    decision_counts: dict[str, int] = field(default_factory=dict)
    primary_reason_counts: dict[str, int] = field(default_factory=dict)
    review_priority_counts: dict[str, int] = field(default_factory=dict)
    manual_review_required_true_count: int = 0
    manual_review_required_false_count: int = 0
    missing_sequence_excluded_from_review_count: int = 0
    sequence_leakage_count: int = 0
    target_leakage_count: int = 0
    both_leakage_count: int = 0
    missing_sequence_count: int = 0
    source_invalid_count: int = 0
    core_below_minimum_count: int = 0
    invalid_sequence_count: int = 0
    ambiguous_sequence_count: int = 0
    mixed_t_u_count: int = 0
    trim_review_count: int = 0
    core_above_maximum_count: int = 0
    ssdna_count: int = 0
    unknown_molecule_count: int = 0
    missing_target_count: int = 0
    technically_eligible_rna_count: int = 0
    multiple_reasons_count: int = 0
    molecule_type_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    alphabet_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    core_length_bucket_by_decision: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    invalid_by_decision: dict[str, int] = field(default_factory=dict)
    ambiguous_by_decision: dict[str, int] = field(default_factory=dict)
    mixed_by_decision: dict[str, int] = field(default_factory=dict)


def assert_no_legacy_cleaner_import() -> None:
    """Hard-fail if the legacy AptaBase cleaner module is imported."""
    import sys

    forbidden = {
        "aptabase_cleaning",
        "scripts.data_preparation.aptabase_cleaning",
    }
    for name in forbidden:
        if name in sys.modules:
            raise AptaBaseS3Error(
                "legacy AptaBase cleaner must not be imported by S3"
            )


def _parse_core_length(canonical: Mapping[str, str]) -> int | None:
    raw = (canonical.get("sequence_length_core") or "").strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise AptaBaseS3Error(
            f"Non-integer sequence_length_core for {canonical.get('record_id')!r}"
        ) from exc


def _core_length_bucket(length: int | None) -> str:
    if length is None:
        return "missing"
    if length < 20:
        return "below_20"
    if length <= 100:
        return "20_to_100"
    return "above_100"


def _collect_secondary_conditions(
    *,
    canonical: Mapping[str, str],
    source_metadata: Mapping[str, str],
    flags: frozenset[str],
    policy: EligibilityPolicy,
    sequence_leakage: LeakageMatch | None,
    target_leakage: TargetLeakageMatch | None,
) -> list[EligibilityReason]:
    """Collect every applicable reason without applying precedence."""
    reasons: list[EligibilityReason] = []
    if sequence_leakage is not None:
        reasons.append(EligibilityReason.EVALUATION_SEQUENCE_LEAKAGE)
    if target_leakage is not None:
        reasons.append(EligibilityReason.EVALUATION_TARGET_LEAKAGE)

    sequence_full = canonical.get("sequence_full", "")
    if sequence_full == "":
        reasons.append(EligibilityReason.MISSING_SEQUENCE)

    validity = (source_metadata.get("aptabase_record_validity") or "").strip()
    if validity.casefold() == "invalid":
        reasons.append(EligibilityReason.SOURCE_RECORD_INVALID)

    core_len = _parse_core_length(canonical)
    if sequence_full != "" and core_len is not None and core_len < policy.core_length_min:
        reasons.append(EligibilityReason.CORE_BELOW_MINIMUM)

    if "invalid_character" in flags:
        reasons.append(EligibilityReason.INVALID_SEQUENCE_REQUIRES_REVIEW)
    if "ambiguous_base" in flags:
        reasons.append(EligibilityReason.AMBIGUOUS_SEQUENCE_REQUIRES_REVIEW)
    if "mixed_t_u" in flags:
        reasons.append(EligibilityReason.MIXED_T_U_REQUIRES_REVIEW)

    trim_review = (
        canonical.get("trim_status") == "review_required"
        or "trim_requires_review" in flags
        or "known_promoter_detected" in flags
    )
    if trim_review:
        reasons.append(EligibilityReason.TRIM_OR_CONSTRUCT_REQUIRES_REVIEW)

    if (
        sequence_full != ""
        and core_len is not None
        and core_len > policy.core_length_max
    ):
        reasons.append(EligibilityReason.CORE_ABOVE_MAXIMUM_REQUIRES_REVIEW)

    molecule = canonical.get("molecule_type", "")
    if molecule == "ssDNA":
        reasons.append(EligibilityReason.SSDNA_NOT_ELIGIBLE_FOR_RNA_TRAINING)
    elif molecule == "unknown":
        reasons.append(EligibilityReason.MOLECULE_TYPE_UNRESOLVED)

    if not (canonical.get("target_name_raw") or "").strip():
        reasons.append(EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW)

    return reasons


def _select_primary(
    applicable: Sequence[EligibilityReason],
) -> EligibilityReason | None:
    """Select the highest-precedence primary reason from applicable reasons."""
    precedence = (
        EligibilityReason.EVALUATION_SEQUENCE_LEAKAGE,
        EligibilityReason.EVALUATION_TARGET_LEAKAGE,
        EligibilityReason.MISSING_SEQUENCE,
        EligibilityReason.SOURCE_RECORD_INVALID,
        EligibilityReason.CORE_BELOW_MINIMUM,
        EligibilityReason.INVALID_SEQUENCE_REQUIRES_REVIEW,
        EligibilityReason.AMBIGUOUS_SEQUENCE_REQUIRES_REVIEW,
        EligibilityReason.MIXED_T_U_REQUIRES_REVIEW,
        EligibilityReason.TRIM_OR_CONSTRUCT_REQUIRES_REVIEW,
        EligibilityReason.CORE_ABOVE_MAXIMUM_REQUIRES_REVIEW,
        EligibilityReason.SSDNA_NOT_ELIGIBLE_FOR_RNA_TRAINING,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED,
        EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW,
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA,
    )
    applicable_set = set(applicable)
    for reason in precedence:
        if reason in applicable_set:
            return reason
    return None


def _decision_for_reason(
    reason: EligibilityReason,
    policy: EligibilityPolicy,
) -> EligibilityDecision:
    mapping = {
        EligibilityReason.EVALUATION_SEQUENCE_LEAKAGE: policy.evaluation_leakage_decision,
        EligibilityReason.EVALUATION_TARGET_LEAKAGE: policy.evaluation_leakage_decision,
        EligibilityReason.MISSING_SEQUENCE: policy.missing_sequence_decision,
        EligibilityReason.SOURCE_RECORD_INVALID: policy.source_record_invalid_decision,
        EligibilityReason.CORE_BELOW_MINIMUM: policy.core_below_minimum_decision,
        EligibilityReason.INVALID_SEQUENCE_REQUIRES_REVIEW: (
            policy.invalid_sequence_decision
        ),
        EligibilityReason.AMBIGUOUS_SEQUENCE_REQUIRES_REVIEW: (
            policy.ambiguous_sequence_decision
        ),
        EligibilityReason.MIXED_T_U_REQUIRES_REVIEW: policy.mixed_t_u_decision,
        EligibilityReason.TRIM_OR_CONSTRUCT_REQUIRES_REVIEW: (
            policy.trim_review_decision
        ),
        EligibilityReason.CORE_ABOVE_MAXIMUM_REQUIRES_REVIEW: (
            policy.core_above_maximum_decision
        ),
        EligibilityReason.SSDNA_NOT_ELIGIBLE_FOR_RNA_TRAINING: policy.ssdna_decision,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED: policy.unknown_molecule_decision,
        EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW: (
            policy.missing_target_decision
        ),
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA: policy.eligible_rna_decision,
    }
    value = mapping[reason]
    return EligibilityDecision(value)


def _is_technically_eligible_rna(
    *,
    canonical: Mapping[str, str],
    flags: frozenset[str],
    policy: EligibilityPolicy,
    sequence_leakage: LeakageMatch | None,
    target_leakage: TargetLeakageMatch | None,
) -> bool:
    sequence_full = canonical.get("sequence_full", "")
    sequence_core = canonical.get("sequence_core", "")
    if sequence_full == "" or sequence_core == "":
        return False
    if sequence_leakage is not None or target_leakage is not None:
        return False
    if canonical.get("molecule_type") != "RNA":
        return False
    alphabet = canonical.get("alphabet_as_reported", "")
    if alphabet not in {"RNA", "DNA_T"}:
        return False
    # DNA_T is acceptable only when S2 classified the molecule as RNA and the
    # canonical core is already in the RNA alphabet.
    if alphabet == "DNA_T":
        core_upper = sequence_core.upper()
        if "T" in core_upper or any(ch not in set("ACGU") for ch in core_upper):
            return False
    core_len = _parse_core_length(canonical)
    if core_len is None:
        return False
    if not (policy.core_length_min <= core_len <= policy.core_length_max):
        return False
    if flags & {"invalid_character", "ambiguous_base", "mixed_t_u"}:
        return False
    if (
        canonical.get("trim_status") == "review_required"
        or "trim_requires_review" in flags
        or "known_promoter_detected" in flags
    ):
        return False
    if not (canonical.get("target_name_raw") or "").strip():
        return False
    return True


def assign_manual_review_priority(
    *,
    proposed_decision: EligibilityDecision,
    primary_reason: EligibilityReason,
    all_reasons: Sequence[EligibilityReason],
    flags: frozenset[str],
    source_metadata: Mapping[str, str],
) -> ManualReviewPriority:
    """Assign review priority; never overrides the proposed decision.

    Mechanical missing-sequence rejections are excluded from the manual-review
    queue even when secondary reasons such as unresolved molecule type or
    missing target are also present. Those secondary reasons remain in the
    decision sidecar for provenance. This rule does not apply to source-invalid,
    leakage, short-core, invalid/mixed, or any park decisions.
    """
    if (
        proposed_decision == EligibilityDecision.PROPOSED_REJECT
        and primary_reason == EligibilityReason.MISSING_SEQUENCE
    ):
        return ManualReviewPriority.NONE

    reason_set = set(all_reasons)

    high_triggers = {
        EligibilityReason.EVALUATION_SEQUENCE_LEAKAGE,
        EligibilityReason.EVALUATION_TARGET_LEAKAGE,
        EligibilityReason.SOURCE_RECORD_INVALID,
        EligibilityReason.MIXED_T_U_REQUIRES_REVIEW,
        EligibilityReason.INVALID_SEQUENCE_REQUIRES_REVIEW,
        EligibilityReason.TRIM_OR_CONSTRUCT_REQUIRES_REVIEW,
    }
    if reason_set & high_triggers:
        return ManualReviewPriority.HIGH
    if "legacy_molecule_type_disagreement" in flags:
        return ManualReviewPriority.HIGH

    medium_triggers = {
        EligibilityReason.AMBIGUOUS_SEQUENCE_REQUIRES_REVIEW,
        EligibilityReason.MOLECULE_TYPE_UNRESOLVED,
        EligibilityReason.SSDNA_NOT_ELIGIBLE_FOR_RNA_TRAINING,
        EligibilityReason.CORE_ABOVE_MAXIMUM_REQUIRES_REVIEW,
        EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW,
    }
    if reason_set & medium_triggers:
        return ManualReviewPriority.MEDIUM
    if "reported_length_mismatch" in flags and (
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA in reason_set
        or proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
        or "molecule_type_unknown" not in flags
    ):
        # Length mismatch on an otherwise plausible RNA / non-unknown case.
        if "molecule_type_unknown" not in flags or (
            EligibilityReason.TECHNICALLY_ELIGIBLE_RNA in reason_set
        ):
            return ManualReviewPriority.MEDIUM

    low_legacy = {
        "legacy_sequence_clean_disagreement",
        "legacy_length_disagreement",
        "legacy_alphabet_disagreement",
        "legacy_gc_disagreement",
        "legacy_molecule_type_unrecognised",
    }
    if flags & low_legacy:
        return ManualReviewPriority.LOW
    if "reported_gc_mismatch" in flags or "reported_gc_unparseable" in flags:
        return ManualReviewPriority.LOW
    warnings = (source_metadata.get("aptabase_parse_warnings") or "").strip()
    validity = (source_metadata.get("aptabase_record_validity") or "").strip()
    if warnings or validity.casefold() == "valid_with_warnings":
        if proposed_decision != EligibilityDecision.PROPOSED_ACCEPT or (
            len(all_reasons) > 1
        ):
            return ManualReviewPriority.LOW
        # Accept with only source-warning metadata still gets low review signal.
        return ManualReviewPriority.LOW

    if (
        proposed_decision == EligibilityDecision.PROPOSED_ACCEPT
        and primary_reason == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA
        and len(all_reasons) == 1
    ):
        return ManualReviewPriority.NONE

    if proposed_decision == EligibilityDecision.PROPOSED_ACCEPT:
        return ManualReviewPriority.NONE

    return ManualReviewPriority.LOW


def classify_aptabase_record(
    s2_record: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: EligibilityPolicy,
    leakage_index: SequenceLeakageIndex,
    target_alias_rules: Sequence[TargetAliasRule],
) -> AptaBaseS3RowResult:
    """Apply deterministic AptaBase S3 eligibility rules to one record."""
    record_id = s2_record["record_id"]
    if record_id != source_metadata.get("record_id", ""):
        raise AptaBaseS3Error("canonical and source-metadata record_id mismatch")
    if record_id != s2_qc.get("record_id", ""):
        raise AptaBaseS3Error("canonical and S2 QC record_id mismatch")

    flags = parse_qc_flags(s2_record.get("qc_flags", ""))
    sequence_full = s2_record.get("sequence_full", "")
    sequence_core = s2_record.get("sequence_core", "")

    sequence_leakage: LeakageMatch | None = None
    if sequence_full != "":
        sequence_leakage = leakage_index.best_match(
            sequence_full=sequence_full,
            sequence_core=sequence_core,
            threshold=policy.sequence_identity_threshold,
        )

    target_leakage: TargetLeakageMatch | None = None
    if policy.target_leakage_matching_enabled:
        target_texts = [
            s2_record.get("target_name_raw", ""),
            source_metadata.get("aptabase_target_general", ""),
            source_metadata.get("aptabase_target_specific", ""),
        ]
        target_leakage = match_target_leakage(target_texts, target_alias_rules)

    applicable = _collect_secondary_conditions(
        canonical=s2_record,
        source_metadata=source_metadata,
        flags=flags,
        policy=policy,
        sequence_leakage=sequence_leakage,
        target_leakage=target_leakage,
    )

    eligible = _is_technically_eligible_rna(
        canonical=s2_record,
        flags=flags,
        policy=policy,
        sequence_leakage=sequence_leakage,
        target_leakage=target_leakage,
    )
    if eligible:
        applicable.append(EligibilityReason.TECHNICALLY_ELIGIBLE_RNA)

    primary = _select_primary(applicable)
    if primary is None:
        raise AptaBaseS3Error(
            f"No eligibility reason resolved for record_id={record_id!r}"
        )

    # Sequence leakage outranks target leakage when both apply.
    if (
        sequence_leakage is not None
        and EligibilityReason.EVALUATION_SEQUENCE_LEAKAGE in applicable
    ):
        primary = EligibilityReason.EVALUATION_SEQUENCE_LEAKAGE
    elif (
        target_leakage is not None
        and EligibilityReason.EVALUATION_TARGET_LEAKAGE in applicable
        and sequence_leakage is None
    ):
        primary = EligibilityReason.EVALUATION_TARGET_LEAKAGE

    proposed = _decision_for_reason(primary, policy)
    secondary = [reason for reason in applicable if reason != primary]
    priority = assign_manual_review_priority(
        proposed_decision=proposed,
        primary_reason=primary,
        all_reasons=applicable,
        flags=flags,
        source_metadata=source_metadata,
    )

    eligibility = build_eligibility_result(
        record_id=record_id,
        proposed_decision=proposed,
        primary_reason=primary,
        secondary_reasons=secondary,
        manual_review_priority=priority,
        sequence_leakage_match=sequence_leakage,
        target_leakage_match=target_leakage,
        checkpoint_status=CHECKPOINT_STATUS_PENDING,
    )

    # Hard invariants for accept / reject edge cases.
    if proposed == EligibilityDecision.PROPOSED_ACCEPT:
        if not eligible or primary != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA:
            raise AptaBaseS3Error(
                f"Accept proposed without technical RNA eligibility: {record_id!r}"
            )
        if s2_record.get("molecule_type") in {"ssDNA", "unknown"}:
            raise AptaBaseS3Error(f"ssDNA/unknown must not be accepted: {record_id!r}")
        if sequence_full == "":
            raise AptaBaseS3Error(f"Missing sequence must not be accepted: {record_id!r}")

    if primary == EligibilityReason.MISSING_SEQUENCE and proposed != (
        EligibilityDecision.PROPOSED_REJECT
    ):
        raise AptaBaseS3Error(
            f"Missing sequence must be rejected: {record_id!r}"
        )

    canonical = validate_s3_record(dict(s2_record), s2_record=s2_record)
    decision = _build_decision_row(
        canonical=canonical,
        s2_qc=s2_qc,
        source_metadata=source_metadata,
        eligibility=eligibility,
    )
    leakage_rows = _build_leakage_rows(
        canonical=canonical,
        eligibility=eligibility,
    )
    return AptaBaseS3RowResult(
        canonical=canonical,
        decision=decision,
        eligibility=eligibility,
        leakage_rows=tuple(leakage_rows),
    )


def _build_decision_row(
    *,
    canonical: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    eligibility: EligibilityResult,
) -> dict[str, str]:
    seq_match = eligibility.sequence_leakage_match
    tgt_match = eligibility.target_leakage_match
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamer_name": s2_qc.get("aptamer_name")
        or source_metadata.get("aptabase_aptamer_name", ""),
        "target_name_raw": canonical["target_name_raw"],
        "proposed_decision": eligibility.proposed_decision.value,
        "primary_reason": eligibility.primary_reason.value,
        "secondary_reasons": format_reasons(eligibility.secondary_reasons),
        "manual_review_required": (
            "true" if eligibility.manual_review_required else "false"
        ),
        "manual_review_priority": eligibility.manual_review_priority.value,
        "checkpoint_status": eligibility.checkpoint_status,
        "molecule_type": canonical["molecule_type"],
        "alphabet_as_reported": canonical["alphabet_as_reported"],
        "sequence_length_full": canonical["sequence_length_full"],
        "sequence_length_core": canonical["sequence_length_core"],
        "construct_scope": canonical["construct_scope"],
        "trim_status": canonical["trim_status"],
        "sequence_leakage_match": "true" if seq_match is not None else "false",
        "sequence_leakage_identity": (
            format_identity(seq_match.identity) if seq_match is not None else ""
        ),
        "sequence_leakage_reference_id": (
            seq_match.matched_reference_id if seq_match is not None else ""
        ),
        "sequence_leakage_target": (
            seq_match.matched_target if seq_match is not None else ""
        ),
        "target_leakage_match": "true" if tgt_match is not None else "false",
        "target_leakage_canonical_target": (
            tgt_match.matched_canonical_target if tgt_match is not None else ""
        ),
        "target_leakage_match_type": (
            tgt_match.match_type if tgt_match is not None else ""
        ),
        "source_record_validity": source_metadata.get("aptabase_record_validity", ""),
        "qc_flags": canonical["qc_flags"],
        "notes": "",
    }


def _build_leakage_rows(
    *,
    canonical: Mapping[str, str],
    eligibility: EligibilityResult,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seq_match = eligibility.sequence_leakage_match
    tgt_match = eligibility.target_leakage_match
    if seq_match is not None:
        rows.append(
            {
                "record_id": canonical["record_id"],
                "native_id": canonical["native_id"],
                "match_scope": "sequence",
                "matched_reference_id": seq_match.matched_reference_id,
                "matched_target": seq_match.matched_target,
                "matched_evaluation_role": seq_match.matched_evaluation_role,
                "matched_form": seq_match.matched_form,
                "identity": format_identity(seq_match.identity),
                "target_match_alias": "",
                "target_match_type": "",
                "proposed_decision": eligibility.proposed_decision.value,
                "primary_reason": eligibility.primary_reason.value,
            }
        )
    if tgt_match is not None:
        rows.append(
            {
                "record_id": canonical["record_id"],
                "native_id": canonical["native_id"],
                "match_scope": "target",
                "matched_reference_id": "",
                "matched_target": tgt_match.matched_canonical_target,
                "matched_evaluation_role": "",
                "matched_form": "",
                "identity": "",
                "target_match_alias": tgt_match.matched_alias,
                "target_match_type": tgt_match.match_type,
                "proposed_decision": eligibility.proposed_decision.value,
                "primary_reason": eligibility.primary_reason.value,
            }
        )
    return rows


def build_local_detail_row(
    *,
    canonical: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    decision: Mapping[str, str],
) -> dict[str, str]:
    """Build one sequence-bearing local-detail review row.

    Source ``sequence_raw`` and canonical full/core fields are copied exactly
    with no extra cleaning. Intended only for ignored outputs under ``data/``.
    """
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "aptamer_name": (
            s2_qc.get("aptamer_name")
            or source_metadata.get("aptabase_aptamer_name", "")
            or decision.get("aptamer_name", "")
        ),
        "target_name_raw": canonical.get("target_name_raw", ""),
        "target_general_raw": source_metadata.get("aptabase_target_general", ""),
        "target_specific_raw": source_metadata.get("aptabase_target_specific", ""),
        "publication": canonical.get("publication", ""),
        "proposed_decision": decision.get("proposed_decision", ""),
        "primary_reason": decision.get("primary_reason", ""),
        "secondary_reasons": decision.get("secondary_reasons", ""),
        "manual_review_required": decision.get("manual_review_required", ""),
        "manual_review_priority": decision.get("manual_review_priority", ""),
        "checkpoint_status": decision.get("checkpoint_status", ""),
        "sequence_raw": source_metadata.get(
            "aptabase_sequence_raw", canonical.get("sequence_raw", "")
        ),
        "sequence_full": canonical.get("sequence_full", ""),
        "sequence_core": canonical.get("sequence_core", ""),
        "sequence_length_full": canonical.get("sequence_length_full", ""),
        "sequence_length_core": canonical.get("sequence_length_core", ""),
        "molecule_type": canonical.get("molecule_type", ""),
        "alphabet_as_reported": canonical.get("alphabet_as_reported", ""),
        "t_to_u_applied": canonical.get("t_to_u_applied", ""),
        "construct_scope": canonical.get("construct_scope", ""),
        "trim_status": canonical.get("trim_status", ""),
        "detected_constant_5p": canonical.get("detected_constant_5p", ""),
        "detected_constant_3p": canonical.get("detected_constant_3p", ""),
        "source_record_validity": source_metadata.get("aptabase_record_validity", ""),
        "source_parse_warnings": source_metadata.get("aptabase_parse_warnings", ""),
        "reported_length_raw": s2_qc.get("reported_length_raw", ""),
        "reported_length_difference": s2_qc.get("reported_length_difference", ""),
        "gc_reported_raw": s2_qc.get("gc_reported_raw", ""),
        "gc_calculated_s2": s2_qc.get("gc_calculated_s2", ""),
        "gc_difference_percentage_points": s2_qc.get(
            "gc_difference_percentage_points", ""
        ),
        "sequence_leakage_match": decision.get("sequence_leakage_match", ""),
        "sequence_leakage_identity": decision.get("sequence_leakage_identity", ""),
        "sequence_leakage_reference_id": decision.get(
            "sequence_leakage_reference_id", ""
        ),
        "target_leakage_match": decision.get("target_leakage_match", ""),
        "target_leakage_canonical_target": decision.get(
            "target_leakage_canonical_target", ""
        ),
        "qc_flags": canonical.get("qc_flags", ""),
        "notes": decision.get("notes", ""),
    }

def update_stats_from_row(stats: AptaBaseS3Stats, row: AptaBaseS3RowResult) -> None:
    """Accumulate aggregate counters from one classified row."""
    decision = row.eligibility.proposed_decision.value
    primary = row.eligibility.primary_reason.value
    priority = row.eligibility.manual_review_priority.value
    flags = parse_qc_flags(row.canonical.get("qc_flags", ""))
    molecule = row.canonical.get("molecule_type") or "unknown"
    alphabet = row.canonical.get("alphabet_as_reported") or "missing"
    core_len = _parse_core_length(row.canonical)

    stats.decision_counts[decision] = stats.decision_counts.get(decision, 0) + 1
    stats.primary_reason_counts[primary] = (
        stats.primary_reason_counts.get(primary, 0) + 1
    )
    stats.review_priority_counts[priority] = (
        stats.review_priority_counts.get(priority, 0) + 1
    )
    if row.eligibility.manual_review_required:
        stats.manual_review_required_true_count += 1
    else:
        stats.manual_review_required_false_count += 1
    if (
        row.eligibility.proposed_decision == EligibilityDecision.PROPOSED_REJECT
        and row.eligibility.primary_reason == EligibilityReason.MISSING_SEQUENCE
    ):
        stats.missing_sequence_excluded_from_review_count += 1

    has_seq = row.eligibility.sequence_leakage_match is not None
    has_tgt = row.eligibility.target_leakage_match is not None
    if has_seq:
        stats.sequence_leakage_count += 1
    if has_tgt:
        stats.target_leakage_count += 1
    if has_seq and has_tgt:
        stats.both_leakage_count += 1

    if EligibilityReason.MISSING_SEQUENCE in row.eligibility.all_reasons:
        stats.missing_sequence_count += 1
    if EligibilityReason.SOURCE_RECORD_INVALID in row.eligibility.all_reasons:
        stats.source_invalid_count += 1
    if EligibilityReason.CORE_BELOW_MINIMUM in row.eligibility.all_reasons:
        stats.core_below_minimum_count += 1
    if EligibilityReason.INVALID_SEQUENCE_REQUIRES_REVIEW in row.eligibility.all_reasons:
        stats.invalid_sequence_count += 1
    if (
        EligibilityReason.AMBIGUOUS_SEQUENCE_REQUIRES_REVIEW
        in row.eligibility.all_reasons
    ):
        stats.ambiguous_sequence_count += 1
    if EligibilityReason.MIXED_T_U_REQUIRES_REVIEW in row.eligibility.all_reasons:
        stats.mixed_t_u_count += 1
    if (
        EligibilityReason.TRIM_OR_CONSTRUCT_REQUIRES_REVIEW
        in row.eligibility.all_reasons
    ):
        stats.trim_review_count += 1
    if (
        EligibilityReason.CORE_ABOVE_MAXIMUM_REQUIRES_REVIEW
        in row.eligibility.all_reasons
    ):
        stats.core_above_maximum_count += 1
    if (
        EligibilityReason.SSDNA_NOT_ELIGIBLE_FOR_RNA_TRAINING
        in row.eligibility.all_reasons
    ):
        stats.ssdna_count += 1
    if EligibilityReason.MOLECULE_TYPE_UNRESOLVED in row.eligibility.all_reasons:
        stats.unknown_molecule_count += 1
    if (
        EligibilityReason.MISSING_TARGET_REQUIRES_SOURCE_REVIEW
        in row.eligibility.all_reasons
    ):
        stats.missing_target_count += 1
    if EligibilityReason.TECHNICALLY_ELIGIBLE_RNA in row.eligibility.all_reasons:
        stats.technically_eligible_rna_count += 1
    if len(row.eligibility.all_reasons) > 1:
        stats.multiple_reasons_count += 1

    mol_map = stats.molecule_type_by_decision.setdefault(decision, {})
    mol_map[molecule] = mol_map.get(molecule, 0) + 1
    alph_map = stats.alphabet_by_decision.setdefault(decision, {})
    alph_map[alphabet] = alph_map.get(alphabet, 0) + 1
    bucket = _core_length_bucket(core_len)
    len_map = stats.core_length_bucket_by_decision.setdefault(decision, {})
    len_map[bucket] = len_map.get(bucket, 0) + 1

    if "invalid_character" in flags:
        stats.invalid_by_decision[decision] = (
            stats.invalid_by_decision.get(decision, 0) + 1
        )
    if "ambiguous_base" in flags:
        stats.ambiguous_by_decision[decision] = (
            stats.ambiguous_by_decision.get(decision, 0) + 1
        )
    if "mixed_t_u" in flags:
        stats.mixed_by_decision[decision] = stats.mixed_by_decision.get(decision, 0) + 1

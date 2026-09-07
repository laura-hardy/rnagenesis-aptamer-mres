"""ENA S3 adapter: technical sequence/molecule/construct eligibility.

Consumes S2 canonical rows, S2 QC, the ENA source-metadata sidecar, and S2
constant-region proposals. Assigns exactly one provisional accept/park/reject
route per record. Does not apply trims, reclassify T-encoded RNA as DNA,
canonicalise targets, score evidence, apply leakage exclusions, or deduplicate.
"""

from __future__ import annotations

import random
from collections import Counter
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
    "review_unit_id",
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
    "qc_flags",
    "experiment_group_id",
    "source_promoter_or_template_concern",
    "source_t7_concern",
    "sequence_corrected_applied",
    "group_covered_by_rule_review",
    "legacy_collapse_member",
    "exact_sequence_full_duplicate_diagnostic",
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
    "source_promoter_or_template_concern",
    "group_covered_by_rule_review",
    "constant_proposal_ids",
)

LOCAL_DETAIL_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "review_unit_id",
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
    "qc_flags",
    "experiment_group_id",
    "source_promoter_or_template_concern",
    "source_t7_concern",
    "sequence_corrected_applied",
    "group_covered_by_rule_review",
    "legacy_collapse_member",
    "exact_sequence_full_duplicate_diagnostic",
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

DEFAULT_ENA_BATCHES: Final[tuple[str, ...]] = (
    "01_judgement_dependent_technical",
    "02_transcription_or_reconciliation_audit",
    "03_length_boundary",
    "04_random_kept_audit",
)

GAP_CHARACTERS: Final[frozenset[str]] = frozenset({"-", "."})
NUCLEOTIDE_OR_AMBIGUITY: Final[frozenset[str]] = frozenset("ACGTUNRYWSMKHBVD")

REJECTION_STAGE: Final[str] = "S3"
PRIMARY_ROUTE_REJECT: Final[str] = "technical_reject"
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

REVIEW_REASON_JUDGEMENT: Final[str] = "judgement_dependent_technical"
REVIEW_REASON_CONSTANT: Final[str] = "constant_region_proposal"
REVIEW_REASON_TRANSCRIPTION: Final[str] = "t_to_u_transcription_audit"
REVIEW_REASON_COLLAPSE: Final[str] = "legacy_collapse_member"
REVIEW_REASON_BOUNDARY: Final[str] = "length_boundary"
REVIEW_REASON_RANDOM: Final[str] = "random_kept_audit"
REVIEW_REASON_SOURCE_PROMOTER: Final[str] = "source_promoter_or_template_concern"

DUPLICATE_DIAGNOSTIC_NOTE: Final[str] = (
    "diagnostic only — no deduplication performed"
)
ENA_EXPERIMENT_GROUP_PREFIX: Final[str] = "ena:experiment_group:"


class EnaS3Error(ValueError):
    """Hard failure during ENA S3 eligibility classification."""


@dataclass(frozen=True)
class EnaS3RowResult:
    """Canonical S3 row plus decision/rejection/park payloads for one record."""

    canonical: dict[str, str]
    decision: dict[str, str]
    eligibility: EligibilityResult
    rejection_row: dict[str, str] | None = None
    park_row: dict[str, str] | None = None
    primary_route: str = ""


@dataclass
class EnaS3Stats:
    """Aggregate S3 counts (no sequences or row identifiers)."""

    s2_rows: int = 0
    s3_rows: int = 0
    unique_record_ids: int = 0
    unique_native_ids: int = 0
    order_preserved: bool = False
    decision_counts: dict[str, int] = field(default_factory=dict)
    primary_reason_counts: dict[str, int] = field(default_factory=dict)
    secondary_reason_counts: dict[str, int] = field(default_factory=dict)
    primary_route_counts: dict[str, int] = field(default_factory=dict)
    review_priority_counts: dict[str, int] = field(default_factory=dict)
    review_batch_counts: dict[str, int] = field(default_factory=dict)
    checkpoint_review_reason_counts: dict[str, int] = field(default_factory=dict)
    manual_review_required_true_count: int = 0
    manual_review_required_false_count: int = 0
    missing_sequence_count: int = 0
    mixed_t_u_count: int = 0
    ambiguous_bases_count: int = 0
    invalid_alphabet_count: int = 0
    alignment_gaps_count: int = 0
    length_out_of_range_count: int = 0
    length_below_20_count: int = 0
    length_above_100_count: int = 0
    trim_construct_unresolved_count: int = 0
    technically_eligible_rna_count: int = 0
    ssdna_parked_count: int = 0
    chemistry_park_count: int = 0
    non_rna_park_count: int = 0
    group_consensus_record_count: int = 0
    group_covered_park_count: int = 0
    source_promoter_count: int = 0
    source_promoter_without_group_count: int = 0
    source_promoter_with_group_count: int = 0
    t_to_u_count: int = 0
    t_to_u_accept_count: int = 0
    boundary_low_count: int = 0
    boundary_high_count: int = 0
    boundary_review_count: int = 0
    judgement_dependent_review_count: int = 0
    transcription_review_count: int = 0
    random_accept_audit_count: int = 0
    random_accept_audit_pool_size: int = 0
    random_accept_audit_shortfall: int = 0
    unique_checkpoint_review_records: int = 0
    multiple_reasons_count: int = 0
    duplicate_sequence_full_values: int = 0
    duplicate_sequence_full_records: int = 0
    unresolved_target_count: int = 0
    genuine_target_conflict_count: int = 0
    molecule_type_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    alphabet_by_decision: dict[str, dict[str, int]] = field(default_factory=dict)
    core_length_bucket_by_decision: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
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
        raise EnaS3Error(f"Non-integer {field_name} for {record_id!r}") from exc


def _core_length_bucket(length: int | None) -> str:
    if length is None:
        return "missing"
    if length < 20:
        return "below_20"
    if length <= 25:
        return "20_to_25"
    if length <= 89:
        return "26_to_89"
    if length <= 100:
        return "90_to_100"
    return "above_100"


def _has_alignment_gaps(sequence: str) -> bool:
    return any(ch in sequence for ch in GAP_CHARACTERS)


def _has_non_gap_invalid(sequence: str) -> bool:
    return any(
        ch not in NUCLEOTIDE_OR_AMBIGUITY and ch not in GAP_CHARACTERS
        for ch in sequence.upper()
    )


def _truthy(value: str) -> bool:
    return (value or "").strip().lower() == "true"


def normalise_ena_experiment_group_id(value: str) -> str:
    """Join QC sidecar group ids with namespaced S2 proposal group ids."""
    text = (value or "").strip()
    if text.startswith(ENA_EXPERIMENT_GROUP_PREFIX):
        return text[len(ENA_EXPERIMENT_GROUP_PREFIX) :]
    return text


def index_constant_proposals(
    qc_rows: Sequence[Mapping[str, str]],
    proposals: Sequence[Mapping[str, str]],
    membership_rows: Sequence[Mapping[str, str]] = (),
) -> dict[str, list[dict[str, str]]]:
    """Map canonical record_id values to unapplied group-consensus proposals.

    S2 QC/sidecar ``experiment_group_id`` values are the source grouping key
    (``experiment_<hash>``). Proposal/membership rows use the namespaced form
    ``ena:experiment_group:experiment_<hash>``. Match both, and also attach
    explicit membership record_ids.
    """
    by_group: dict[str, list[dict[str, str]]] = {}
    proposals_by_id: dict[str, dict[str, str]] = {}
    for proposal in proposals:
        row = {key: ("" if value is None else str(value)) for key, value in proposal.items()}
        if row.get("proposal_source") != "group_consensus":
            continue
        if _truthy(row.get("applied", "false")):
            raise EnaS3Error(
                "ENA S3 received an applied constant-region proposal; "
                "S3 must not consume applied trims"
            )
        proposal_id = row.get("proposal_id", "")
        if proposal_id:
            proposals_by_id[proposal_id] = row
        group_id = row.get("experiment_group_id", "")
        keys = {group_id, normalise_ena_experiment_group_id(group_id)}
        keys.discard("")
        for key in keys:
            by_group.setdefault(key, []).append(row)

    attached: dict[str, list[dict[str, str]]] = {}

    def _extend(record_id: str, rows: Sequence[Mapping[str, str]]) -> None:
        if not record_id or not rows:
            return
        current = attached.setdefault(record_id, [])
        seen = {row.get("proposal_id", "") for row in current}
        for row in rows:
            proposal_id = row.get("proposal_id", "")
            if proposal_id in seen:
                continue
            current.append(dict(row))
            seen.add(proposal_id)

    for qc in qc_rows:
        record_id = qc.get("record_id", "")
        group_id = qc.get("experiment_group_id", "")
        keys = {group_id, normalise_ena_experiment_group_id(group_id)}
        if group_id and not group_id.startswith(ENA_EXPERIMENT_GROUP_PREFIX):
            keys.add(f"{ENA_EXPERIMENT_GROUP_PREFIX}{group_id}")
        keys.discard("")
        matches: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for key in keys:
            for row in by_group.get(key, ()):
                proposal_id = row.get("proposal_id", "")
                if proposal_id in seen_ids:
                    continue
                matches.append(row)
                seen_ids.add(proposal_id)
        _extend(record_id, matches)

    for member in membership_rows:
        if member.get("proposal_source") != "group_consensus":
            continue
        record_id = member.get("record_id", "")
        proposal_id = member.get("proposal_id", "")
        proposal = proposals_by_id.get(proposal_id)
        if proposal is None:
            continue
        _extend(record_id, [proposal])
    return attached


def _collect_reasons(
    *,
    canonical: Mapping[str, str],
    flags: frozenset[str],
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]],
    source_promoter: bool,
    construct_review_resolved: bool = False,
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

    group_proposals = [
        row for row in proposals if row.get("proposal_source") == "group_consensus"
    ]
    known_proposals = [
        row for row in proposals if row.get("proposal_source") == "known_motif"
    ]
    if not construct_review_resolved:
        trim_unresolved = (
            "trim_requires_review" in flags
            or canonical.get("trim_status") == "constants_suspected_unresolved"
            or bool(group_proposals)
            or source_promoter
            or "known_promoter_detected" in flags
        )
        if trim_unresolved:
            reasons.append(EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED)
    if group_proposals:
        reasons.append(EligibilityReason.CONSTANT_REGION_PROPOSAL)
        if any((row.get("confidence") or "").strip() == "medium" for row in group_proposals):
            reasons.append(EligibilityReason.MEDIUM_CONFIDENCE_TRIM)
    if known_proposals or "known_promoter_detected" in flags:
        reasons.append(EligibilityReason.KNOWN_MOTIF_PROPOSAL)

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
        EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED: policy.trim_review_decision,
        EligibilityReason.TECHNICALLY_ELIGIBLE_RNA: policy.eligible_rna_decision,
    }
    if reason not in mapping:
        raise EnaS3Error(f"No decision mapping for primary reason {reason.value}")
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


def _checkpoint_review_reasons(
    *,
    all_reasons: Sequence[EligibilityReason],
    source_promoter: bool,
    t_to_u_applied: bool,
    group_proposals: Sequence[Mapping[str, str]],
    length_reject: bool,
) -> list[str]:
    labels: list[str] = []
    reason_set = set(all_reasons)
    group_covered = bool(group_proposals)
    source_without_group = source_promoter and not group_covered
    if length_reject or source_without_group:
        labels.append(REVIEW_REASON_JUDGEMENT)
    if source_promoter:
        labels.append(REVIEW_REASON_SOURCE_PROMOTER)
    if group_covered:
        labels.append(REVIEW_REASON_CONSTANT)
    if t_to_u_applied:
        labels.append(REVIEW_REASON_TRANSCRIPTION)
    if reason_set & {
        EligibilityReason.LOWER_LENGTH_BOUNDARY,
        EligibilityReason.UPPER_LENGTH_BOUNDARY,
    }:
        labels.append(REVIEW_REASON_BOUNDARY)
    if EligibilityReason.RANDOM_ACCEPT_AUDIT in reason_set:
        labels.append(REVIEW_REASON_RANDOM)
    return labels


def assign_ena_review_batch(
    *,
    review_reasons: Sequence[str],
    group_covered: bool,
    proposed_decision: EligibilityDecision,
) -> str:
    """Assign at most one record-level review batch.

    Group-consensus parks whose only construct issue is covered by the
    structured rule table do not enter the per-record queue unless a higher
    record-level reason (length reject, uncovered source-promoter concern,
    T→U audit, collapse membership, length boundary, or random audit) applies.
    """
    reasons = set(review_reasons)
    if REVIEW_REASON_JUDGEMENT in reasons:
        return "01_judgement_dependent_technical"
    if REVIEW_REASON_TRANSCRIPTION in reasons or REVIEW_REASON_COLLAPSE in reasons:
        return "02_transcription_or_reconciliation_audit"
    if REVIEW_REASON_BOUNDARY in reasons and proposed_decision == (
        EligibilityDecision.PROPOSED_ACCEPT
    ):
        return "03_length_boundary"
    if REVIEW_REASON_RANDOM in reasons:
        return "04_random_kept_audit"
    if group_covered and REVIEW_REASON_CONSTANT in reasons:
        return ""
    if reasons:
        raise EnaS3Error(
            "Review-required ENA record belongs to no record-level batch: "
            f"reasons={sorted(reasons)}"
        )
    return ""


def _record_level_review_required(
    review_batch: str,
    review_reasons: Sequence[str],
    group_covered: bool,
) -> bool:
    if review_batch:
        return True
    reasons = set(review_reasons)
    if group_covered and reasons <= {
        REVIEW_REASON_CONSTANT,
        REVIEW_REASON_SOURCE_PROMOTER,
    }:
        return False
    return bool(review_batch)


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
        "constant_proposal_sides": format_reasons(row.get("side", "") for row in ordered),
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


def classify_ena_record(
    s2_record: Mapping[str, str],
    s2_qc: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]] = (),
    construct_review_resolved: bool = False,
) -> EnaS3RowResult:
    """Apply deterministic ENA S3 technical-eligibility rules to one record.

    ``construct_review_resolved`` is False during pre-review S3. After an
    explicit CHECKPOINT-1 trim/no-trim/promoter decision, callers set it True
    so a consumed concern does not re-park the record. Length, alphabet, and
    molecule rules still apply. Default False preserves completed S3
    semantics.
    """
    record_id = s2_record["record_id"]
    if record_id != s2_qc.get("record_id", ""):
        raise EnaS3Error("canonical and S2 QC record_id mismatch")
    if record_id != source_metadata.get("record_id", ""):
        raise EnaS3Error("canonical and source-metadata record_id mismatch")

    for field_name in S3_FORBIDDEN_FIELDS:
        if (s2_record.get(field_name) or "") != "":
            raise EnaS3Error(
                f"S3 must not receive populated later-stage field {field_name!r}"
            )
    if s2_record.get("molecule_type") != "RNA":
        raise EnaS3Error(
            f"ENA S3 source contract requires molecule_type=RNA; got "
            f"{s2_record.get('molecule_type')!r} for {record_id!r}"
        )
    if s2_record.get("chemistry") != "RNA":
        raise EnaS3Error(
            f"ENA S3 source contract requires chemistry=RNA; got "
            f"{s2_record.get('chemistry')!r} for {record_id!r}"
        )

    flags = parse_qc_flags(s2_record.get("qc_flags", ""))
    source_promoter = _truthy(s2_qc.get("source_promoter_or_template_concern", ""))
    group_proposals = [
        row for row in proposals if row.get("proposal_source") == "group_consensus"
    ]
    applicable = _collect_reasons(
        canonical=s2_record,
        flags=flags,
        policy=policy,
        proposals=proposals,
        source_promoter=source_promoter,
        construct_review_resolved=construct_review_resolved,
    )
    eligible = _is_technically_eligible_rna(
        canonical=s2_record, applicable=applicable, policy=policy
    )
    if eligible:
        applicable.append(EligibilityReason.TECHNICALLY_ELIGIBLE_RNA)

    primary = _select_primary(
        applicable, policy.decision_precedence, diagnostic=DIAGNOSTIC_REASONS
    )
    if primary is None:
        raise EnaS3Error(f"No eligibility reason resolved for record_id={record_id!r}")
    proposed = _decision_for_reason(primary, policy)
    secondary = [reason for reason in applicable if reason != primary]
    length_reject = (
        proposed == EligibilityDecision.PROPOSED_REJECT
        and primary == EligibilityReason.LENGTH_OUT_OF_RANGE
    )
    t_to_u_applied = _truthy(s2_record.get("t_to_u_applied", ""))
    review_reasons = _checkpoint_review_reasons(
        all_reasons=applicable,
        source_promoter=source_promoter,
        t_to_u_applied=t_to_u_applied,
        group_proposals=group_proposals,
        length_reject=length_reject,
    )
    group_covered = bool(group_proposals)
    review_batch = assign_ena_review_batch(
        review_reasons=review_reasons,
        group_covered=group_covered,
        proposed_decision=proposed,
    )
    record_review = _record_level_review_required(
        review_batch, review_reasons, group_covered
    )
    if record_review:
        if review_batch.startswith("01_"):
            priority = ManualReviewPriority.HIGH
        elif review_batch.startswith("02_"):
            priority = ManualReviewPriority.MEDIUM
        else:
            priority = ManualReviewPriority.LOW
    else:
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
    # Group-covered parks are reviewed at rule level, not per record.
    if not record_review and eligibility.manual_review_required:
        eligibility = build_eligibility_result(
            record_id=record_id,
            proposed_decision=proposed,
            primary_reason=primary,
            secondary_reasons=secondary,
            manual_review_priority=ManualReviewPriority.NONE,
            sequence_leakage_match=None,
            target_leakage_match=None,
            checkpoint_status=CHECKPOINT_STATUS_PENDING,
        )

    if proposed == EligibilityDecision.PROPOSED_ACCEPT:
        if not eligible or primary != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA:
            raise EnaS3Error(
                f"Accept proposed without technical RNA eligibility: {record_id!r}"
            )
        if EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED in eligibility.all_reasons:
            raise EnaS3Error(
                f"Unresolved trim/construct must not be accepted: {record_id!r}"
            )
        if "t_in_reported_rna" in flags and not t_to_u_applied:
            raise EnaS3Error(
                f"t_in_reported_rna without successful T→U for {record_id!r}"
            )

    if primary == EligibilityReason.MISSING_SEQUENCE and proposed != (
        EligibilityDecision.PROPOSED_REJECT
    ):
        raise EnaS3Error(f"Missing sequence must be rejected: {record_id!r}")
    if eligibility.manual_review_required and not review_batch:
        raise EnaS3Error(f"Review-required record missing review_batch: {record_id!r}")
    if (not eligibility.manual_review_required) and review_batch:
        raise EnaS3Error(f"No-review record must not have a review_batch: {record_id!r}")

    canonical = validate_s3_record(dict(s2_record), s2_record=s2_record)
    if canonical.get("sequence_core") != s2_record.get("sequence_core"):
        raise EnaS3Error("S3 must not alter sequence_core")
    if canonical.get("sequence_full") != s2_record.get("sequence_full"):
        raise EnaS3Error("S3 must not alter sequence_full")
    if canonical.get("sequence_raw") != s2_record.get("sequence_raw"):
        raise EnaS3Error("S3 must not alter sequence_raw")
    if canonical.get("t_to_u_applied") != s2_record.get("t_to_u_applied"):
        raise EnaS3Error("S3 must not alter T→U provenance")

    primary_route = PRIMARY_ROUTE_ELIGIBLE
    if proposed == EligibilityDecision.PROPOSED_REJECT:
        primary_route = PRIMARY_ROUTE_REJECT
    elif proposed == EligibilityDecision.PROPOSED_PARK:
        primary_route = PRIMARY_ROUTE_CONSTRUCT

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
        source_promoter=source_promoter,
        group_covered=group_covered,
    )
    rejection_row = None
    park_row = None
    if proposed == EligibilityDecision.PROPOSED_REJECT:
        rejection_row = _build_rejection_row(canonical=canonical, decision=decision)
    elif proposed == EligibilityDecision.PROPOSED_PARK:
        park_row = _build_park_row(canonical=canonical, decision=decision)

    return EnaS3RowResult(
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
    source_promoter: bool,
    group_covered: bool,
) -> dict[str, str]:
    return {
        "record_id": canonical["record_id"],
        "native_id": canonical["native_id"],
        "review_unit_id": source_metadata.get("review_unit_id")
        or canonical["native_id"],
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
        "qc_flags": canonical["qc_flags"],
        "experiment_group_id": s2_qc.get("experiment_group_id", ""),
        "source_promoter_or_template_concern": (
            "true" if source_promoter else "false"
        ),
        "source_t7_concern": s2_qc.get("source_t7_concern", ""),
        "sequence_corrected_applied": s2_qc.get("sequence_corrected_applied", ""),
        "group_covered_by_rule_review": "true" if group_covered else "false",
        "legacy_collapse_member": "false",
        "exact_sequence_full_duplicate_diagnostic": "false",
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
) -> dict[str, str]:
    reason = decision["primary_reason"]
    if reason not in PLAN_REJECTION_REASONS:
        raise EnaS3Error(
            f"Rejection reason {reason!r} is not in the plan closed vocabulary"
        )
    if reason in {"duplicate", "missing_target", "no_binding_evidence", "leakage_excluded"}:
        raise EnaS3Error(
            f"ENA S3 must not emit premature rejection reason {reason!r}"
        )
    detail_parts = [
        part for part in (decision.get("secondary_reasons") or "").split("|") if part
    ]
    return {
        "record_id": canonical["record_id"],
        "source_db": canonical.get("source_db", "ena"),
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
        "source_promoter_or_template_concern": decision.get(
            "source_promoter_or_template_concern", ""
        ),
        "group_covered_by_rule_review": decision.get(
            "group_covered_by_rule_review", ""
        ),
        "constant_proposal_ids": decision.get("constant_proposal_ids", ""),
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
        "review_unit_id": decision.get("review_unit_id")
        or source_metadata.get("review_unit_id")
        or canonical["native_id"],
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
        "qc_flags": canonical.get("qc_flags", ""),
        "experiment_group_id": decision.get("experiment_group_id")
        or s2_qc.get("experiment_group_id", ""),
        "source_promoter_or_template_concern": decision.get(
            "source_promoter_or_template_concern", ""
        ),
        "source_t7_concern": decision.get("source_t7_concern")
        or s2_qc.get("source_t7_concern", ""),
        "sequence_corrected_applied": decision.get("sequence_corrected_applied")
        or s2_qc.get("sequence_corrected_applied", ""),
        "group_covered_by_rule_review": decision.get(
            "group_covered_by_rule_review", ""
        ),
        "legacy_collapse_member": decision.get("legacy_collapse_member", "false"),
        "exact_sequence_full_duplicate_diagnostic": decision.get(
            "exact_sequence_full_duplicate_diagnostic", "false"
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


def duplicate_sequence_full_ids(
    canonical_rows: Sequence[Mapping[str, str]],
) -> tuple[set[str], int, int]:
    """Return record_ids involved in exact post-S2 sequence_full collisions.

    Diagnostic only — does not change S3 routes.
    """
    counts: Counter[str] = Counter()
    by_seq: dict[str, list[str]] = {}
    for row in canonical_rows:
        seq = row.get("sequence_full") or ""
        if not seq:
            continue
        counts[seq] += 1
        by_seq.setdefault(seq, []).append(row["record_id"])
    duplicated_values = [seq for seq, count in counts.items() if count > 1]
    record_ids = {rid for seq in duplicated_values for rid in by_seq[seq]}
    return record_ids, len(duplicated_values), len(record_ids)


def apply_duplicate_sequence_diagnostic(
    decision_rows: list[dict[str, str]],
    local_detail_by_id: dict[str, dict[str, str]],
    duplicate_ids: set[str],
) -> None:
    """Flag exact sequence_full collisions without changing the S3 route."""
    for row in decision_rows:
        if row["record_id"] not in duplicate_ids:
            continue
        row["exact_sequence_full_duplicate_diagnostic"] = "true"
        row["legacy_collapse_member"] = "true"
        notes = [part for part in (row.get("notes") or "").split("|") if part]
        if DUPLICATE_DIAGNOSTIC_NOTE not in notes:
            notes.append(DUPLICATE_DIAGNOSTIC_NOTE)
        row["notes"] = "|".join(notes)
        reasons = [
            part
            for part in (row.get("checkpoint_review_reasons") or "").split("|")
            if part
        ]
        if REVIEW_REASON_COLLAPSE not in reasons:
            reasons.append(REVIEW_REASON_COLLAPSE)
        row["checkpoint_review_reasons"] = format_reasons(reasons)
        if row["manual_review_required"] != "true":
            # Collapse members already in the group-rule table stay there;
            # otherwise they enter the transcription/reconciliation audit.
            group_only = (
                row.get("group_covered_by_rule_review") == "true"
                and not row.get("review_batch")
                and row["proposed_decision"] == "proposed_park"
            )
            if not group_only:
                row["manual_review_required"] = "true"
                if row.get("manual_review_priority") in {"", "none"}:
                    row["manual_review_priority"] = ManualReviewPriority.MEDIUM.value
                row["review_batch"] = assign_ena_review_batch(
                    review_reasons=reasons,
                    group_covered=row.get("group_covered_by_rule_review") == "true",
                    proposed_decision=EligibilityDecision(row["proposed_decision"]),
                )
        else:
            row["review_batch"] = assign_ena_review_batch(
                review_reasons=reasons,
                group_covered=row.get("group_covered_by_rule_review") == "true",
                proposed_decision=EligibilityDecision(row["proposed_decision"]),
            )
        detail = local_detail_by_id.get(row["record_id"])
        if detail is not None:
            detail["exact_sequence_full_duplicate_diagnostic"] = "true"
            detail["legacy_collapse_member"] = "true"
            detail["notes"] = row["notes"]
            detail["checkpoint_review_reasons"] = row["checkpoint_review_reasons"]
            detail["manual_review_required"] = row["manual_review_required"]
            detail["manual_review_priority"] = row["manual_review_priority"]
            detail["review_batch"] = row["review_batch"]


def apply_random_accept_audit(
    decision_rows: list[dict[str, str]],
    local_detail_by_id: dict[str, dict[str, str]],
    *,
    seed: int,
    sample_size: int,
) -> tuple[int, int, int]:
    """Mark a seeded sample of otherwise-clean proposed accepts.

    Returns ``(selected_count, pool_size, shortfall)``.
    """
    if sample_size < 0:
        raise EnaS3Error("random_accept_audit_size must be non-negative")
    candidates = [
        row
        for row in decision_rows
        if row["proposed_decision"] == "proposed_accept"
        and row["primary_reason"] == EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value
        and row.get("primary_route") == PRIMARY_ROUTE_ELIGIBLE
        and row.get("molecule_type") == "RNA"
        and row.get("manual_review_required") != "true"
        and row.get("group_covered_by_rule_review") != "true"
        and row.get("source_promoter_or_template_concern") != "true"
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
        row["review_batch"] = assign_ena_review_batch(
            review_reasons=review_reasons,
            group_covered=False,
            proposed_decision=EligibilityDecision.PROPOSED_ACCEPT,
        )
        detail = local_detail_by_id.get(row["record_id"])
        if detail is not None:
            detail["secondary_reasons"] = row["secondary_reasons"]
            detail["checkpoint_review_reasons"] = row["checkpoint_review_reasons"]
            detail["manual_review_required"] = "true"
            detail["manual_review_priority"] = row["manual_review_priority"]
            detail["review_batch"] = row["review_batch"]

    return take, pool_size, shortfall


def update_stats_from_row(stats: EnaS3Stats, row: EnaS3RowResult) -> None:
    """Accumulate aggregate counters from one classified row."""
    decision = row.eligibility.proposed_decision.value
    primary = row.eligibility.primary_reason.value
    priority = row.eligibility.manual_review_priority.value
    molecule = row.canonical.get("molecule_type") or "unknown"
    alphabet = row.canonical.get("alphabet_as_reported") or "missing"
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
    for reason in row.eligibility.secondary_reasons:
        key = reason.value
        stats.secondary_reason_counts[key] = (
            stats.secondary_reason_counts.get(key, 0) + 1
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
        if core_len is not None and core_len < 20:
            stats.length_below_20_count += 1
        if core_len is not None and core_len > 100:
            stats.length_above_100_count += 1
    if EligibilityReason.TRIM_CONSTRUCT_UNRESOLVED in reasons:
        stats.trim_construct_unresolved_count += 1
    if EligibilityReason.TECHNICALLY_ELIGIBLE_RNA in reasons:
        stats.technically_eligible_rna_count += 1
    if EligibilityReason.CONSTANT_REGION_PROPOSAL in reasons:
        stats.group_consensus_record_count += 1
    if row.decision.get("group_covered_by_rule_review") == "true" and (
        row.eligibility.proposed_decision == EligibilityDecision.PROPOSED_PARK
    ):
        stats.group_covered_park_count += 1
    if row.decision.get("source_promoter_or_template_concern") == "true":
        stats.source_promoter_count += 1
        if row.decision.get("group_covered_by_rule_review") == "true":
            stats.source_promoter_with_group_count += 1
        else:
            stats.source_promoter_without_group_count += 1
    if _truthy(row.canonical.get("t_to_u_applied", "")):
        stats.t_to_u_count += 1
        if row.eligibility.proposed_decision == EligibilityDecision.PROPOSED_ACCEPT:
            stats.t_to_u_accept_count += 1
    if EligibilityReason.LOWER_LENGTH_BOUNDARY in reasons:
        stats.boundary_low_count += 1
    if EligibilityReason.UPPER_LENGTH_BOUNDARY in reasons:
        stats.boundary_high_count += 1
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
    stats: EnaS3Stats, decision_rows: Sequence[Mapping[str, str]]
) -> None:
    """Recompute review-dependent counters after post-classification audits."""
    stats.manual_review_required_true_count = 0
    stats.manual_review_required_false_count = 0
    stats.review_batch_counts = {}
    stats.review_priority_counts = {}
    stats.checkpoint_review_reason_counts = {}
    stats.random_accept_audit_count = 0
    stats.boundary_review_count = 0
    stats.judgement_dependent_review_count = 0
    stats.transcription_review_count = 0
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
            stats.secondary_reason_counts[
                EligibilityReason.RANDOM_ACCEPT_AUDIT.value
            ] = stats.secondary_reason_counts.get(
                EligibilityReason.RANDOM_ACCEPT_AUDIT.value, 0
            ) + 1
        review_set = {
            part
            for part in (row.get("checkpoint_review_reasons") or "").split("|")
            if part
        }
        if required and REVIEW_REASON_BOUNDARY in review_set:
            stats.boundary_review_count += 1
        if required and REVIEW_REASON_JUDGEMENT in review_set:
            stats.judgement_dependent_review_count += 1
        if required and (
            REVIEW_REASON_TRANSCRIPTION in review_set
            or REVIEW_REASON_COLLAPSE in review_set
        ):
            stats.transcription_review_count += 1


def assert_ena_accept_invariants(decision_rows: Sequence[Mapping[str, str]]) -> None:
    """Hard-fail if any proposed accept violates RNA technical eligibility."""
    for row in decision_rows:
        if row["proposed_decision"] != "proposed_accept":
            continue
        if row["molecule_type"] != "RNA":
            raise EnaS3Error("proposed accept contains non-RNA molecule_type")
        if row.get("chemistry") != "RNA":
            raise EnaS3Error("proposed accept chemistry must remain RNA")
        if row["primary_reason"] != EligibilityReason.TECHNICALLY_ELIGIBLE_RNA.value:
            raise EnaS3Error(
                "proposed accept primary_reason must be technically_eligible_rna"
            )
        if row.get("primary_route") != PRIMARY_ROUTE_ELIGIBLE:
            raise EnaS3Error("proposed accept primary_route mismatch")
        flags = parse_qc_flags(row.get("qc_flags", ""))
        if flags & {"invalid_character", "ambiguous_base", "mixed_t_u", "alignment_gaps"}:
            raise EnaS3Error("proposed accept has unresolved alphabet/gap QC flags")
        if "trim_requires_review" in flags or row.get("trim_status") == (
            "constants_suspected_unresolved"
        ):
            raise EnaS3Error("proposed accept still has unresolved construct flags")
        if row.get("source_promoter_or_template_concern") == "true":
            raise EnaS3Error(
                "source promoter/template concern must not be proposed_accept"
            )
        if row.get("group_covered_by_rule_review") == "true":
            raise EnaS3Error(
                "unresolved group-consensus proposal must not be proposed_accept"
            )
        try:
            core_len = int(row["sequence_length_core"])
        except ValueError as exc:
            raise EnaS3Error(
                "proposed accept has non-integer sequence_length_core"
            ) from exc
        if not (20 <= core_len <= 100):
            raise EnaS3Error("proposed accept core length outside 20–100 nt policy")


def assert_ena_reject_park_invariants(
    decision_rows: Sequence[Mapping[str, str]],
) -> None:
    seen: set[str] = set()
    for row in decision_rows:
        record_id = row["record_id"]
        if record_id in seen:
            raise EnaS3Error(f"Duplicate decision record_id {record_id!r}")
        seen.add(record_id)
        decision = row["proposed_decision"]
        primary = row["primary_reason"]
        if primary == "missing_sequence" and decision != "proposed_reject":
            raise EnaS3Error("missing sequence must never be accepted or parked")
        if primary == "length_out_of_range" and decision == "proposed_accept":
            raise EnaS3Error("length_out_of_range must never be accepted")
        if primary == "ssdna_parked":
            raise EnaS3Error("ENA S3 must not park records as ssDNA")
        if primary == "non_rna_molecule":
            raise EnaS3Error("ENA S3 must not park records as non-RNA")
        if row["checkpoint_status"] != CHECKPOINT_STATUS_PENDING:
            raise EnaS3Error("Unexpected checkpoint_status at S3")
        if decision not in {
            "proposed_accept",
            "proposed_park",
            "proposed_reject",
        }:
            raise EnaS3Error(f"Unknown proposed_decision {decision!r}")
        route = row.get("primary_route", "")
        if route not in {
            PRIMARY_ROUTE_REJECT,
            PRIMARY_ROUTE_CONSTRUCT,
            PRIMARY_ROUTE_ELIGIBLE,
        }:
            raise EnaS3Error(f"Unknown primary_route {route!r}")
        required = row.get("manual_review_required")
        if required not in {"true", "false"}:
            raise EnaS3Error("manual_review_required must be lowercase true/false")
        if required == "true" and not row.get("review_batch"):
            raise EnaS3Error("Active review row missing review_batch")
        if required == "false" and row.get("review_batch"):
            raise EnaS3Error("Mechanical row must not carry a review_batch")
        for forbidden in S3_FORBIDDEN_FIELDS:
            if forbidden in row and row[forbidden] and forbidden != "experiment_group_id":
                raise EnaS3Error(
                    f"S3 decision sidecar must not populate {forbidden}"
                )
        if row.get("manual_decision"):
            raise EnaS3Error("S3 must not pre-fill a human manual_decision")
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
                raise EnaS3Error(f"S3 must not pre-fill human field {field_name}")
        if row.get("target_name") or row.get("target_uniprot") or row.get("target_type"):
            raise EnaS3Error("S3 must not populate canonical target fields")
        if row.get("binding_evidence_score") or row.get("cluster_id"):
            raise EnaS3Error("S3 must not populate S4 clustering/evidence fields")

"""Group-level constant-region inference (proposal only).

This module proposes possible 5′/3′ constant regions from experiment groups.
It does **not** alter source records and does **not** prove that a region is
biologically nonfunctional. Application requires an explicit approved trim plan
and an exact prefix or suffix match per record.

Inference is deterministic regardless of input order.

Tier-2 qualifying proposals use plan semantics:
``trim_confidence = medium`` / status ``proposed_for_checkpoint1``.
Failed inference attempts are diagnostics, not scientific proposals.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .sequence_normalisation import (
    AppliedTrim,
    SequenceNormalisationError,
    SequenceNormalisationResult,
    SequenceNormalisationRules,
    TrimMismatchError,
    TrimProposal,
    load_normalisation_rules,
    normalise_sequence,
)

GROUP_INFERENCE_KEY_EXPERIMENT_GROUP: str = "experiment_group_id"
GROUP_INFERENCE_KEY_TARGET_PUBLICATION: str = "target_name_raw_plus_publication"
GROUP_INFERENCE_KEY_AUTO: str = "experiment_group_then_target_publication"

QUALIFYING_TIER2_STATUS: str = "proposed_for_checkpoint1"
TIER2_CONFIDENCE_LABEL: str = "medium"


class ConstantRegionInferenceError(SequenceNormalisationError):
    """Invalid constant-region inference input (never embeds sequences)."""


@dataclass(frozen=True)
class InferenceRecord:
    """Minimal record used for group-level constant-region inference."""

    record_id: str
    experiment_group_id: str | None
    sequence_full: str | None


@dataclass(frozen=True)
class ConstantRegionProposal:
    """A group-level constant-region proposal (not automatically applied)."""

    experiment_group_id: str
    side: str
    proposed_sequence: str | None
    length: int
    support: float
    records_considered: int
    records_matching_exactly: int
    records_excluded: int
    confidence: str
    status: str
    reason: str


@dataclass(frozen=True)
class GroupInferenceDiagnostics:
    """Aggregate counts for failed or ineligible Tier-2 inference attempts."""

    skipped_missing_group: int = 0
    groups_total: int = 0
    groups_below_min_size: int = 0
    groups_usable_below_min_size: int = 0
    groups_no_qualifying_prefix: int = 0
    groups_no_qualifying_suffix: int = 0
    groups_qualifying_prefix: int = 0
    groups_qualifying_suffix: int = 0
    group_size_histogram: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class GroupInferenceResult:
    """Qualifying proposals plus aggregate diagnostics."""

    proposals: tuple[ConstantRegionProposal, ...]
    diagnostics: GroupInferenceDiagnostics


@dataclass(frozen=True)
class TrimApplicationResult:
    """Result of applying an approved inferred trim to one record."""

    record_id: str
    matched: bool
    sequence_full: str | None
    sequence_core: str | None
    applied_trims: tuple[AppliedTrim, ...]
    qc_flags: tuple[str, ...]
    normalisation: SequenceNormalisationResult | None = None


def _nonempty_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def build_group_inference_key(
    *,
    source_db: str,
    grouping_mode: str,
    experiment_group_id: str | None = None,
    target_name_raw: str | None = None,
    publication: str | None = None,
) -> str | None:
    """Build a deterministic Tier-2 consensus group key.

    Missing grouping evidence returns ``None`` so unrelated rows are never
    pooled into a catch-all group.

    Modes:
    - ``experiment_group_id``: require a nonempty experiment group ID
    - ``target_name_raw_plus_publication``: require both target and publication
    - ``experiment_group_then_target_publication``: experiment group if present,
      otherwise target + publication
    """
    source = _nonempty_text(source_db) or "unknown_source"
    group_id = _nonempty_text(experiment_group_id)
    target = _nonempty_text(target_name_raw)
    pub = _nonempty_text(publication)

    if grouping_mode == GROUP_INFERENCE_KEY_EXPERIMENT_GROUP:
        if group_id is None:
            return None
        return f"{source}:experiment_group:{group_id}"

    if grouping_mode == GROUP_INFERENCE_KEY_TARGET_PUBLICATION:
        if target is None or pub is None:
            return None
        digest = hashlib.sha256(f"{target}\0{pub}".encode("utf-8")).hexdigest()[:16]
        return f"{source}:tgt_pub:{digest}"

    if grouping_mode == GROUP_INFERENCE_KEY_AUTO:
        if group_id is not None:
            return f"{source}:experiment_group:{group_id}"
        if target is None or pub is None:
            return None
        digest = hashlib.sha256(f"{target}\0{pub}".encode("utf-8")).hexdigest()[:16]
        return f"{source}:tgt_pub:{digest}"

    raise ConstantRegionInferenceError(
        f"unsupported group inference grouping_mode: {grouping_mode!r}"
    )


def _as_inference_record(item: Mapping[str, Any] | InferenceRecord) -> InferenceRecord:
    if isinstance(item, InferenceRecord):
        return item
    if not isinstance(item, Mapping):
        raise ConstantRegionInferenceError("inference record must be a mapping")
    record_id = item.get("record_id")
    if record_id is None or str(record_id).strip() == "":
        raise ConstantRegionInferenceError("record_id is required")
    group_raw = item.get("experiment_group_id")
    if group_raw is None:
        group_id: str | None = None
    else:
        group_text = str(group_raw).strip()
        group_id = group_text if group_text else None
    seq = item.get("sequence_full")
    sequence_full = None if seq is None else str(seq)
    return InferenceRecord(
        record_id=str(record_id),
        experiment_group_id=group_id,
        sequence_full=sequence_full,
    )


def _is_usable_sequence(sequence: str | None) -> bool:
    if sequence is None or sequence == "":
        return False
    # Exclude clearly invalid characters from positional consensus.
    allowed = set("ACGTU")
    return all(ch in allowed for ch in sequence.upper())


def _alphabet_family(sequence: str) -> str:
    upper = sequence.upper()
    has_t = "T" in upper
    has_u = "U" in upper
    if has_t and has_u:
        return "mixed"
    if has_u:
        return "rna"
    if has_t:
        return "dna"
    return "neutral"


def _comparison_form(sequence: str) -> str:
    """Explicit T/U-collapsed representation for positional consensus."""
    return sequence.upper().replace("U", "T")


def _families_compatible(families: set[str]) -> bool:
    # Per-sequence mixed T/U cannot be compared safely. DNA-alphabet and
    # RNA-alphabet group members are compared via ``_comparison_form``.
    return "mixed" not in families


def _size_bucket(size: int) -> str:
    if size < 5:
        return "1-4"
    if size < 10:
        return "5-9"
    if size < 25:
        return "10-24"
    if size < 50:
        return "25-49"
    return "50+"


def _positional_consensus(
    sequences: Sequence[str],
    *,
    side: str,
    minimum_support: float,
    minimum_region_length: int,
    maximum_region_length: int,
) -> tuple[str | None, float, int, str]:
    """Extend a consensus prefix/suffix while support stays at threshold.

    Returns ``(sequence_or_none, support, exact_matches, reason)``.

    Positional comparison uses an explicit T/U-collapsed representation so
    DNA-alphabet and RNA-alphabet members of the same experiment group can be
    compared without silently mixing incompatible bases.
    """
    if not sequences:
        return None, 0.0, 0, "no_usable_sequences"

    families = {_alphabet_family(seq) for seq in sequences}
    if not _families_compatible(families):
        return None, 0.0, 0, "mixed_alphabets_without_comparison_representation"

    compared = [_comparison_form(seq) for seq in sequences]
    n = len(compared)
    max_len = min(maximum_region_length, min(len(seq) for seq in compared))
    if max_len < minimum_region_length:
        return None, 0.0, 0, "sequences_shorter_than_minimum_region_length"

    consensus_chars: list[str] = []
    last_support = 0.0
    for offset in range(max_len):
        bases: list[str] = []
        for seq in compared:
            if side == "five_prime":
                bases.append(seq[offset])
            else:
                bases.append(seq[-(offset + 1)])
        counts = Counter(bases)
        base, count = counts.most_common(1)[0]
        support = count / n
        if support < minimum_support:
            break
        consensus_chars.append(base)
        last_support = support

    if side == "three_prime":
        consensus_chars.reverse()

    if len(consensus_chars) < minimum_region_length:
        return None, last_support, 0, "insufficient_support"

    proposed = "".join(consensus_chars)
    # Exact match is evaluated in comparison space; original sequences match if
    # their comparison form shares the proposed prefix/suffix.
    if side == "five_prime":
        exact = sum(1 for seq in compared if seq.startswith(proposed))
    else:
        exact = sum(1 for seq in compared if seq.endswith(proposed))
    support = exact / n
    if support < minimum_support:
        return None, support, exact, "insufficient_support"

    # Emit the proposal in the group's dominant alphabet when unambiguous.
    if families == {"rna"} or (families <= {"rna", "neutral"} and "rna" in families):
        proposed = proposed.replace("T", "U")

    return proposed, support, exact, "group_consensus_support_met"


def infer_group_constant_regions(
    records: Iterable[Mapping[str, Any] | InferenceRecord],
    *,
    rules: SequenceNormalisationRules | None = None,
    include_non_qualifying: bool = False,
) -> tuple[ConstantRegionProposal, ...]:
    """Propose qualifying 5′/3′ constant regions per experiment group.

    Missing group IDs are never pooled. By default only motifs that meet the
    configured minimum length and support are returned. Failed attempts are
    available via :func:`infer_group_constant_regions_with_diagnostics`.
    """
    return infer_group_constant_regions_with_diagnostics(
        records,
        rules=rules,
        include_non_qualifying=include_non_qualifying,
    ).proposals


def infer_group_constant_regions_with_diagnostics(
    records: Iterable[Mapping[str, Any] | InferenceRecord],
    *,
    rules: SequenceNormalisationRules | None = None,
    include_non_qualifying: bool = False,
) -> GroupInferenceResult:
    """Propose Tier-2 constant regions and return aggregate diagnostics."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    cfg = active_rules.constant_region_inference

    parsed = [_as_inference_record(item) for item in records]
    # Deterministic regardless of input order.
    parsed.sort(key=lambda item: (item.record_id, str(item.experiment_group_id)))

    grouped: dict[str, list[InferenceRecord]] = defaultdict(list)
    skipped_missing_group = 0
    for item in parsed:
        if item.experiment_group_id is None:
            skipped_missing_group += 1
            continue
        grouped[item.experiment_group_id].append(item)

    proposals: list[ConstantRegionProposal] = []
    size_histogram: dict[str, int] = defaultdict(int)
    groups_below_min_size = 0
    groups_usable_below_min_size = 0
    groups_no_qualifying_prefix = 0
    groups_no_qualifying_suffix = 0
    groups_qualifying_prefix = 0
    groups_qualifying_suffix = 0

    for group_id in sorted(grouped):
        members = grouped[group_id]
        # Stable within-group order by record_id.
        members = sorted(members, key=lambda item: item.record_id)
        total = len(members)
        size_histogram[_size_bucket(total)] += 1
        usable: list[str] = []
        excluded = 0
        for member in members:
            if _is_usable_sequence(member.sequence_full):
                usable.append(member.sequence_full.upper())  # type: ignore[union-attr]
            else:
                excluded += 1

        def _emit_non_qualifying(side: str, *, status: str, reason: str, support: float = 0.0, exact: int = 0) -> None:
            if not include_non_qualifying:
                return
            proposals.append(
                ConstantRegionProposal(
                    experiment_group_id=group_id,
                    side=side,
                    proposed_sequence=None,
                    length=0,
                    support=support,
                    records_considered=total,
                    records_matching_exactly=exact,
                    records_excluded=excluded,
                    confidence="n/a",
                    status=status,
                    reason=reason,
                )
            )

        if total < cfg.minimum_group_size:
            groups_below_min_size += 1
            for side in ("five_prime", "three_prime"):
                _emit_non_qualifying(
                    side,
                    status="insufficient_group_size",
                    reason="group_smaller_than_minimum",
                )
            continue

        if len(usable) < cfg.minimum_group_size:
            groups_usable_below_min_size += 1
            for side in ("five_prime", "three_prime"):
                _emit_non_qualifying(
                    side,
                    status="insufficient_group_size",
                    reason="usable_sequences_below_minimum_group_size",
                )
            continue

        for side in ("five_prime", "three_prime"):
            proposed, support, exact, reason = _positional_consensus(
                usable,
                side=side,
                minimum_support=cfg.minimum_support,
                minimum_region_length=cfg.minimum_region_length,
                maximum_region_length=cfg.maximum_region_length,
            )
            if proposed is None:
                if side == "five_prime":
                    groups_no_qualifying_prefix += 1
                else:
                    groups_no_qualifying_suffix += 1
                status = (
                    "insufficient_support"
                    if reason == "insufficient_support"
                    else "no_constant_region"
                )
                if reason == "mixed_alphabets_without_comparison_representation":
                    status = "requires_review"
                _emit_non_qualifying(
                    side,
                    status=status,
                    reason=reason,
                    support=support,
                    exact=exact,
                )
            else:
                if side == "five_prime":
                    groups_qualifying_prefix += 1
                else:
                    groups_qualifying_suffix += 1
                proposals.append(
                    ConstantRegionProposal(
                        experiment_group_id=group_id,
                        side=side,
                        proposed_sequence=proposed,
                        length=len(proposed),
                        support=support,
                        records_considered=total,
                        records_matching_exactly=exact,
                        records_excluded=excluded,
                        confidence=TIER2_CONFIDENCE_LABEL,
                        status=QUALIFYING_TIER2_STATUS,
                        reason=reason,
                    )
                )

    proposals.sort(key=lambda item: (item.experiment_group_id, item.side))
    diagnostics = GroupInferenceDiagnostics(
        skipped_missing_group=skipped_missing_group,
        groups_total=len(grouped),
        groups_below_min_size=groups_below_min_size,
        groups_usable_below_min_size=groups_usable_below_min_size,
        groups_no_qualifying_prefix=groups_no_qualifying_prefix,
        groups_no_qualifying_suffix=groups_no_qualifying_suffix,
        groups_qualifying_prefix=groups_qualifying_prefix,
        groups_qualifying_suffix=groups_qualifying_suffix,
        group_size_histogram=dict(sorted(size_histogram.items())),
    )
    return GroupInferenceResult(proposals=tuple(proposals), diagnostics=diagnostics)


def apply_approved_trim(
    sequence_raw: str | None,
    *,
    molecule_type: str | None,
    trim_plan: TrimProposal,
    record_id: str = "",
    rules: SequenceNormalisationRules | None = None,
) -> TrimApplicationResult:
    """Apply an approved trim plan via shared normalisation.

    A record that does not match remains untrimmed and receives a QC flag.
    Partial trimming is never performed.
    """
    if trim_plan.status and trim_plan.status not in {"approved", ""}:
        raise ConstantRegionInferenceError(
            "trim_plan must be approved before application"
        )

    active_rules = rules if rules is not None else load_normalisation_rules()
    try:
        result = normalise_sequence(
            sequence_raw,
            molecule_type=molecule_type,
            trim_plan=trim_plan,
            rules=active_rules,
        )
    except TrimMismatchError:
        # Exact match failed — leave untrimmed and flag.
        untrimmed = normalise_sequence(
            sequence_raw,
            molecule_type=molecule_type,
            trim_plan=None,
            rules=active_rules,
        )
        flags = list(untrimmed.qc_flags)
        if "trim_requires_review" not in flags:
            flags.append("trim_requires_review")
        flags = sorted(set(flags))
        return TrimApplicationResult(
            record_id=record_id,
            matched=False,
            sequence_full=untrimmed.sequence_full,
            sequence_core=untrimmed.sequence_core,
            applied_trims=(),
            qc_flags=tuple(flags),
            normalisation=untrimmed,
        )

    return TrimApplicationResult(
        record_id=record_id,
        matched=bool(result.applied_trims),
        sequence_full=result.sequence_full,
        sequence_core=result.sequence_core,
        applied_trims=result.applied_trims,
        qc_flags=result.qc_flags,
        normalisation=result,
    )


def proposal_to_trim_plan(
    proposal: ConstantRegionProposal,
    *,
    reason: str | None = None,
    confidence: float | None = None,
) -> TrimProposal:
    """Convert a qualifying proposal into an approved trim plan.

    Callers must only invoke this after human or documented approval. The
    returned plan still requires an exact match at application time.
    """
    allowed = {QUALIFYING_TIER2_STATUS, "high_confidence_proposal"}
    if proposal.status not in allowed or not proposal.proposed_sequence:
        raise ConstantRegionInferenceError(
            "only a qualifying proposal with a sequence may become a trim plan"
        )
    five = proposal.proposed_sequence if proposal.side == "five_prime" else None
    three = proposal.proposed_sequence if proposal.side == "three_prime" else None
    numeric_confidence = (
        confidence if confidence is not None else float(proposal.support)
    )
    return TrimProposal(
        five_prime=five,
        three_prime=three,
        reason=reason or proposal.reason,
        confidence=numeric_confidence,
        source=f"constant_region_inference:{proposal.experiment_group_id}:{proposal.side}",
        status="approved",
    )


def ensure_mapping_not_mutated(
    original: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> None:
    """Raise if ``candidate`` differs from ``original`` (mutation guard for tests)."""
    if dict(original) != dict(candidate):
        raise ConstantRegionInferenceError("input mapping was mutated")

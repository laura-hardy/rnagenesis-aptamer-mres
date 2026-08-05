"""Group-level constant-region inference (proposal only).

This module proposes possible 5′/3′ constant regions from experiment groups.
It does **not** alter source records and does **not** prove that a region is
biologically nonfunctional. Application requires an explicit approved trim plan
and an exact prefix or suffix match per record.

Inference is deterministic regardless of input order.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
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
    confidence: float
    status: str
    reason: str


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

    return proposed, support, exact, "high_confidence_proposal"


def infer_group_constant_regions(
    records: Iterable[Mapping[str, Any] | InferenceRecord],
    *,
    rules: SequenceNormalisationRules | None = None,
) -> tuple[ConstantRegionProposal, ...]:
    """Propose 5′/3′ constant regions per experiment group.

    Missing group IDs are never pooled. Groups smaller than the configured
    minimum produce an ``insufficient_group_size`` status without a sequence.
    Invalid or missing sequences are excluded and counted.

    Constant-region inference is a technical aid only; it is not biological
    proof that a region is nonfunctional.
    """
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
    for group_id in sorted(grouped):
        members = grouped[group_id]
        # Stable within-group order by record_id.
        members = sorted(members, key=lambda item: item.record_id)
        total = len(members)
        usable: list[str] = []
        excluded = 0
        for member in members:
            if _is_usable_sequence(member.sequence_full):
                usable.append(member.sequence_full.upper())  # type: ignore[union-attr]
            else:
                excluded += 1

        if total < cfg.minimum_group_size:
            for side in ("five_prime", "three_prime"):
                proposals.append(
                    ConstantRegionProposal(
                        experiment_group_id=group_id,
                        side=side,
                        proposed_sequence=None,
                        length=0,
                        support=0.0,
                        records_considered=total,
                        records_matching_exactly=0,
                        records_excluded=excluded,
                        confidence=0.0,
                        status="insufficient_group_size",
                        reason="group_smaller_than_minimum",
                    )
                )
            continue

        if len(usable) < cfg.minimum_group_size:
            for side in ("five_prime", "three_prime"):
                proposals.append(
                    ConstantRegionProposal(
                        experiment_group_id=group_id,
                        side=side,
                        proposed_sequence=None,
                        length=0,
                        support=0.0,
                        records_considered=total,
                        records_matching_exactly=0,
                        records_excluded=excluded,
                        confidence=0.0,
                        status="insufficient_group_size",
                        reason="usable_sequences_below_minimum_group_size",
                    )
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
                status = (
                    "insufficient_support"
                    if reason == "insufficient_support"
                    else "no_constant_region"
                )
                if reason == "mixed_alphabets_without_comparison_representation":
                    status = "requires_review"
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
                        confidence=support,
                        status=status,
                        reason=reason,
                    )
                )
            else:
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
                        confidence=support,
                        status="high_confidence_proposal",
                        reason=reason,
                    )
                )

    proposals.sort(key=lambda item: (item.experiment_group_id, item.side))
    return tuple(proposals)


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
    """Convert a high-confidence proposal into an approved trim plan.

    Callers must only invoke this after human or documented approval. The
    returned plan still requires an exact match at application time.
    """
    if proposal.status != "high_confidence_proposal" or not proposal.proposed_sequence:
        raise ConstantRegionInferenceError(
            "only high_confidence_proposal with a sequence may become a trim plan"
        )
    five = proposal.proposed_sequence if proposal.side == "five_prime" else None
    three = proposal.proposed_sequence if proposal.side == "three_prime" else None
    return TrimProposal(
        five_prime=five,
        three_prime=three,
        reason=reason or proposal.reason,
        confidence=confidence if confidence is not None else proposal.confidence,
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

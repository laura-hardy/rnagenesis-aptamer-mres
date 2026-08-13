"""Apply explicitly approved UTexas constant-region trim rules.

An approved rule is permission to attempt an exact terminal match, not a
licence to guess. Same-side competing motifs and combined per-record guard
rails block application. Unresolved rules are never applied.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from adapters.utexas_s2 import (
    QC_DELIMITER,
    UTexasS2Error,
    UTexasS2RowResult,
    _comparison_form,
    _end_matches,
)
from common.corpus_schema import format_qc_flags, validate_s2_record
from common.sequence_normalisation import validate_core_length

TRIM_AUDIT_COLUMNS: tuple[str, ...] = (
    "record_id",
    "native_id",
    "applied",
    "five_prime_rule_ids",
    "three_prime_rule_ids",
    "five_prime_bases_removed",
    "three_prime_bases_removed",
    "combined_bases_trimmed",
    "combined_trim_fraction",
    "sequence_length_full",
    "sequence_length_core",
    "skip_reason",
    "unresolved_rule_count",
)

AMBIGUITY_COLUMNS: tuple[str, ...] = (
    "record_id",
    "native_id",
    "side",
    "matching_rule_ids",
    "distinct_motif_count",
)

SKIP_SAME_SIDE_AMBIGUOUS = "same_side_ambiguous"
SKIP_COMBINED_BELOW_20 = "combined_core_below_20"
SKIP_COMBINED_OVER_40 = "combined_trim_exceeds_40pct"
SKIP_NONE = ""


@dataclass(frozen=True)
class ApprovedTrimRule:
    """One source-scoped approved constant-region trim rule."""

    candidate_rule_id: str
    side: str
    motif: str
    motif_length: int
    evidence_sources: str
    agreement_category: str
    group_consensus_support: str
    confidence: str = "medium"


@dataclass
class TrimApplicationStats:
    """Aggregate approved-trim application counts."""

    approved_rules: int = 0
    unresolved_rules: int = 0
    approved_rules_matching_ge1: int = 0
    approved_rules_matching_none: int = 0
    records_trimmed: int = 0
    five_prime_only: int = 0
    three_prime_only: int = 0
    both_ends: int = 0
    same_side_ambiguities: int = 0
    skipped_combined_below_20: int = 0
    skipped_combined_over_40: int = 0
    skipped_other_ambiguity: int = 0
    total_bases_removed: int = 0
    core_differs_from_full: int = 0
    core_equals_full: int = 0
    resolved_by_approved_trim: int = 0
    still_trim_requires_review: int = 0
    same_motif_multi_rule_applications: int = 0
    rescued_overlength_to_20_100: int = 0
    core_became_out_of_range: int = 0


@dataclass
class TrimApplicationResult:
    """Per-run trim application artefacts."""

    audit_rows: list[dict[str, str]] = field(default_factory=list)
    ambiguity_rows: list[dict[str, str]] = field(default_factory=list)
    stats: TrimApplicationStats = field(default_factory=TrimApplicationStats)


def load_approved_trim_rules(path: str | Path) -> tuple[ApprovedTrimRule, ...]:
    """Load the tracked approved UTexas trim-rule config."""
    rules_path = Path(path)
    try:
        payload = json.loads(rules_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise UTexasS2Error(f"cannot read approved trim rules: {exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise UTexasS2Error(f"approved trim rules JSON is invalid: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise UTexasS2Error("approved trim rules payload must be a JSON object")
    if payload.get("source_key") != "utexas":
        raise UTexasS2Error("approved trim rules source_key must be utexas")
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise UTexasS2Error("approved trim rules.rules must be a list")
    parsed: list[ApprovedTrimRule] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_rules):
        if not isinstance(item, Mapping):
            raise UTexasS2Error(f"approved trim rules[{index}] must be an object")
        rule_id = str(item.get("candidate_rule_id") or "").strip()
        side = str(item.get("side") or "").strip()
        motif = str(item.get("motif") or "").strip().upper()
        if not rule_id:
            raise UTexasS2Error(f"approved trim rules[{index}] missing candidate_rule_id")
        if rule_id in seen:
            raise UTexasS2Error(f"duplicate approved trim rule id: {rule_id}")
        if side not in {"five_prime", "three_prime"}:
            raise UTexasS2Error(f"approved trim rule {rule_id} has invalid side")
        if not motif or not all(ch in "ACGTU" for ch in motif):
            raise UTexasS2Error(
                f"approved trim rule {rule_id} must have a nucleotide motif"
            )
        length = item.get("motif_length")
        if not isinstance(length, int) or length != len(motif):
            raise UTexasS2Error(
                f"approved trim rule {rule_id} motif_length must equal motif length"
            )
        seen.add(rule_id)
        parsed.append(
            ApprovedTrimRule(
                candidate_rule_id=rule_id,
                side=side,
                motif=motif,
                motif_length=length,
                evidence_sources=str(item.get("evidence_sources") or ""),
                agreement_category=str(item.get("agreement_category") or ""),
                group_consensus_support=str(item.get("group_consensus_support") or ""),
                confidence=str(item.get("confidence") or "medium"),
            )
        )
    parsed.sort(key=lambda item: item.candidate_rule_id)
    return tuple(parsed)


def _membership_index(
    membership_rows: Sequence[Mapping[str, str]],
) -> dict[str, set[str]]:
    """Map record_id -> candidate_rule_ids."""
    index: dict[str, set[str]] = defaultdict(set)
    for row in membership_rows:
        record_id = row.get("record_id") or ""
        rule_id = row.get("candidate_rule_id") or ""
        if record_id and rule_id:
            index[record_id].add(rule_id)
    return dict(index)


def _motif_key(motif: str) -> str:
    return _comparison_form(motif)


def _select_unambiguous_side(
    *,
    sequence_full: str,
    side: str,
    candidate_rules: Sequence[ApprovedTrimRule],
) -> tuple[ApprovedTrimRule | None, tuple[ApprovedTrimRule, ...], bool]:
    """Return (chosen_rule, matching_rules, is_ambiguous).

    Multiple rule IDs for the exact same motif are one biological trim.
    Different motifs on the same side are ambiguous.
    """
    matching = [
        rule
        for rule in candidate_rules
        if rule.side == side
        and _end_matches(sequence_full, side=side, motif=rule.motif)
    ]
    if not matching:
        return None, (), False
    distinct = {_motif_key(rule.motif) for rule in matching}
    if len(distinct) > 1:
        return None, tuple(matching), True
    # Deterministic provenance: sorted rule IDs, first is primary.
    matching_sorted = tuple(sorted(matching, key=lambda item: item.candidate_rule_id))
    return matching_sorted[0], matching_sorted, False


def _slice_terminal(sequence_full: str, *, side: str, motif: str) -> str:
    if side == "five_prime":
        return sequence_full[len(motif) :]
    return sequence_full[: len(sequence_full) - len(motif)]


def _fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def apply_approved_trims_to_rows(
    row_results: Sequence[UTexasS2RowResult],
    *,
    approved_rules: Sequence[ApprovedTrimRule],
    unresolved_rule_ids: set[str],
    membership_rows: Sequence[Mapping[str, str]],
    s1_by_id: Mapping[str, Mapping[str, str]],
) -> TrimApplicationResult:
    """Apply approved exact-match trims; never mutate sequence_raw/full."""
    rules_by_id = {rule.candidate_rule_id: rule for rule in approved_rules}
    record_to_rules = _membership_index(membership_rows)
    matching_rule_ids: set[str] = set()
    result = TrimApplicationResult()
    result.stats.approved_rules = len(approved_rules)
    result.stats.unresolved_rules = len(unresolved_rule_ids)

    for row in row_results:
        canonical = row.canonical
        record_id = canonical["record_id"]
        sequence_full = canonical.get("sequence_full") or ""
        sequence_raw = canonical["sequence_raw"]
        member_rule_ids = record_to_rules.get(record_id, set())
        approved_for_record = [
            rules_by_id[rule_id]
            for rule_id in sorted(member_rule_ids)
            if rule_id in rules_by_id
        ]
        unresolved_for_record = sorted(member_rule_ids & unresolved_rule_ids)

        skip_reason = SKIP_NONE
        five_rule = None
        three_rule = None
        five_matches: tuple[ApprovedTrimRule, ...] = ()
        three_matches: tuple[ApprovedTrimRule, ...] = ()
        applied = False
        core = sequence_full
        five_bases = 0
        three_bases = 0

        if sequence_full:
            five_rule, five_matches, five_amb = _select_unambiguous_side(
                sequence_full=sequence_full,
                side="five_prime",
                candidate_rules=approved_for_record,
            )
            three_rule, three_matches, three_amb = _select_unambiguous_side(
                sequence_full=sequence_full,
                side="three_prime",
                candidate_rules=approved_for_record,
            )
            if five_amb or three_amb:
                skip_reason = SKIP_SAME_SIDE_AMBIGUOUS
                result.stats.same_side_ambiguities += 1
                result.stats.skipped_other_ambiguity += 1
                for side, matches, amb in (
                    ("five_prime", five_matches, five_amb),
                    ("three_prime", three_matches, three_amb),
                ):
                    if not amb:
                        continue
                    result.ambiguity_rows.append(
                        {
                            "record_id": record_id,
                            "native_id": canonical.get("native_id", ""),
                            "side": side,
                            "matching_rule_ids": QC_DELIMITER.join(
                                rule.candidate_rule_id for rule in matches
                            ),
                            "distinct_motif_count": str(
                                len({_motif_key(rule.motif) for rule in matches})
                            ),
                        }
                    )
            elif five_rule or three_rule:
                five_len = five_rule.motif_length if five_rule else 0
                three_len = three_rule.motif_length if three_rule else 0
                combined = five_len + three_len
                combined_core = len(sequence_full) - combined
                fraction = combined / len(sequence_full) if sequence_full else 0.0
                if combined_core < 20:
                    skip_reason = SKIP_COMBINED_BELOW_20
                    result.stats.skipped_combined_below_20 += 1
                elif fraction > 0.40:
                    skip_reason = SKIP_COMBINED_OVER_40
                    result.stats.skipped_combined_over_40 += 1
                else:
                    core = sequence_full
                    if five_rule is not None:
                        core = _slice_terminal(
                            core, side="five_prime", motif=five_rule.motif
                        )
                        five_bases = five_rule.motif_length
                    if three_rule is not None:
                        core = _slice_terminal(
                            core, side="three_prime", motif=three_rule.motif
                        )
                        three_bases = three_rule.motif_length
                    applied = True

        if five_matches:
            matching_rule_ids.update(rule.candidate_rule_id for rule in five_matches)
        if three_matches:
            matching_rule_ids.update(rule.candidate_rule_id for rule in three_matches)
        if len(five_matches) > 1:
            result.stats.same_motif_multi_rule_applications += 1
        if len(three_matches) > 1:
            result.stats.same_motif_multi_rule_applications += 1

        flags = [
            part for part in (canonical.get("qc_flags") or "").split(QC_DELIMITER) if part
        ]
        flags = [
            flag
            for flag in flags
            if flag
            not in {
                "constants_suspected_unresolved",
                "trim_requires_review",
                "core_below_min_length",
                "core_above_max_length",
            }
        ]

        trim_status = canonical.get("trim_status") or ""
        construct_scope = canonical.get("construct_scope") or ""
        trim_confidence = canonical.get("trim_confidence") or ""
        detected_5p = canonical.get("detected_constant_5p") or ""
        detected_3p = canonical.get("detected_constant_3p") or ""

        still_unresolved = bool(unresolved_for_record) or skip_reason != SKIP_NONE
        if applied:
            if five_rule and three_rule:
                construct_scope = "full_construct"
                result.stats.both_ends += 1
            elif five_rule:
                construct_scope = "partial_construct"
                result.stats.five_prime_only += 1
            else:
                construct_scope = "partial_construct"
                result.stats.three_prime_only += 1
            trim_status = "primers_removed"
            trim_confidence = "medium"
            result.stats.records_trimmed += 1
            result.stats.total_bases_removed += five_bases + three_bases
            if five_rule:
                ids = QC_DELIMITER.join(r.candidate_rule_id for r in five_matches)
                detected_5p = QC_DELIMITER.join(
                    part for part in (detected_5p, ids) if part
                )
            if three_rule:
                ids = QC_DELIMITER.join(r.candidate_rule_id for r in three_matches)
                detected_3p = QC_DELIMITER.join(
                    part for part in (detected_3p, ids) if part
                )
            if still_unresolved:
                flags.append("constants_suspected_unresolved")
                flags.append("trim_requires_review")
            else:
                result.stats.resolved_by_approved_trim += 1
        else:
            if skip_reason == SKIP_SAME_SIDE_AMBIGUOUS:
                flags.append("trim_same_side_ambiguous")
                flags.append("trim_requires_review")
                flags.append("constants_suspected_unresolved")
            elif skip_reason == SKIP_COMBINED_BELOW_20:
                flags.append("trim_combined_core_below_min")
                flags.append("trim_requires_review")
                flags.append("constants_suspected_unresolved")
            elif skip_reason == SKIP_COMBINED_OVER_40:
                flags.append("trim_combined_exceeds_40pct")
                flags.append("trim_requires_review")
                flags.append("constants_suspected_unresolved")
            elif unresolved_for_record or "pool_type_constants_proposed" in flags:
                if "constants_suspected_unresolved" not in flags:
                    flags.append("constants_suspected_unresolved")
                if "trim_requires_review" not in flags:
                    flags.append("trim_requires_review")
            core = sequence_full

        if sequence_full:
            length_val = validate_core_length(core)
            for flag in length_val.flags:
                flags.append(flag)
            length_core = str(len(core))
            length_full = str(len(sequence_full))
        else:
            length_core = canonical.get("sequence_length_core") or ""
            length_full = canonical.get("sequence_length_full") or ""

        flags = sorted(set(flags))
        canonical["sequence_raw"] = sequence_raw
        canonical["sequence_full"] = sequence_full
        canonical["sequence_core"] = core
        canonical["sequence_length_full"] = length_full
        canonical["sequence_length_core"] = length_core
        canonical["construct_scope"] = construct_scope
        canonical["trim_status"] = trim_status
        canonical["trim_confidence"] = trim_confidence
        canonical["detected_constant_5p"] = detected_5p
        canonical["detected_constant_3p"] = detected_3p
        canonical["qc_flags"] = format_qc_flags(flags)
        s1 = s1_by_id[record_id]
        row.canonical = validate_s2_record(canonical, s1_record=s1)
        row.qc["sequence_length_full"] = row.canonical["sequence_length_full"]
        row.qc["sequence_length_core"] = row.canonical["sequence_length_core"]
        row.qc["construct_scope"] = row.canonical["construct_scope"]
        row.qc["trim_status"] = row.canonical["trim_status"]
        row.qc["trim_confidence"] = row.canonical["trim_confidence"]
        row.qc["qc_flags"] = row.canonical["qc_flags"]

        if row.canonical["sequence_full"] != row.canonical["sequence_core"]:
            result.stats.core_differs_from_full += 1
        else:
            result.stats.core_equals_full += 1
        if "trim_requires_review" in flags:
            result.stats.still_trim_requires_review += 1

        full_len = len(sequence_full)
        core_len = len(core) if sequence_full else 0
        if applied and full_len > 100 and 20 <= core_len <= 100:
            result.stats.rescued_overlength_to_20_100 += 1
        if applied and 20 <= full_len <= 100 and (core_len < 20 or core_len > 100):
            result.stats.core_became_out_of_range += 1

        combined_bases = five_bases + three_bases if applied else 0
        fraction = (
            (combined_bases / full_len) if applied and full_len else None
        )
        five_ids = QC_DELIMITER.join(r.candidate_rule_id for r in five_matches)
        three_ids = QC_DELIMITER.join(r.candidate_rule_id for r in three_matches)
        result.audit_rows.append(
            {
                "record_id": record_id,
                "native_id": canonical.get("native_id", ""),
                "applied": "true" if applied else "false",
                "five_prime_rule_ids": five_ids,
                "three_prime_rule_ids": three_ids,
                "five_prime_bases_removed": str(five_bases) if applied else "0",
                "three_prime_bases_removed": str(three_bases) if applied else "0",
                "combined_bases_trimmed": str(combined_bases),
                "combined_trim_fraction": _fmt_float(fraction),
                "sequence_length_full": str(full_len) if sequence_full else "",
                "sequence_length_core": (
                    str(len(core)) if sequence_full else ""
                ),
                "skip_reason": skip_reason,
                "unresolved_rule_count": str(len(unresolved_for_record)),
            }
        )

    result.stats.approved_rules_matching_ge1 = len(matching_rule_ids)
    result.stats.approved_rules_matching_none = (
        result.stats.approved_rules - result.stats.approved_rules_matching_ge1
    )
    result.audit_rows.sort(key=lambda item: item["record_id"])
    result.ambiguity_rows.sort(key=lambda item: (item["record_id"], item["side"]))
    return result


def apply_single_record_trim_for_tests(
    sequence_full: str,
    *,
    approved_rules: Sequence[ApprovedTrimRule],
    unresolved_rule_ids: set[str] | None = None,
) -> tuple[str, str, tuple[str, ...]]:
    """Synthetic helper: apply approved rules as if the record is a member of all.

    Returns ``(sequence_core, skip_reason, qc_flags)``.
    """
    dummy_id = "synthetic:record"
    membership_ids = [rule.candidate_rule_id for rule in approved_rules]
    if unresolved_rule_ids:
        membership_ids.extend(sorted(unresolved_rule_ids))
    membership = [
        {
            "record_id": dummy_id,
            "candidate_rule_id": rule_id,
        }
        for rule_id in membership_ids
    ]
    from common.corpus_schema import empty_corpus_record

    canonical = empty_corpus_record()
    canonical.update(
        {
            "record_id": dummy_id,
            "native_id": "record",
            "sequence_raw": sequence_full,
            "sequence_full": sequence_full,
            "sequence_core": sequence_full,
            "sequence_length_full": str(len(sequence_full)),
            "sequence_length_core": str(len(sequence_full)),
            "source_db": "utexas",
            "source_dataset": "demo",
            "contributing_sources": "utexas",
            "contributing_datasets": "demo",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "construct_scope": "unknown",
            "trim_status": "constants_suspected_unresolved",
            "trim_confidence": "",
            "molecule_type": "RNA",
            "alphabet_as_reported": "RNA",
            "t_to_u_applied": "false",
            "chemistry": "RNA",
            "qc_flags": "constants_suspected_unresolved|trim_requires_review",
        }
    )
    row = UTexasS2RowResult(canonical=dict(canonical), qc=dict(canonical))
    applied = apply_approved_trims_to_rows(
        [row],
        approved_rules=approved_rules,
        unresolved_rule_ids=unresolved_rule_ids or set(),
        membership_rows=membership,
        s1_by_id={dummy_id: canonical},
    )
    skip = applied.audit_rows[0]["skip_reason"]
    flags = tuple(
        part for part in row.canonical["qc_flags"].split(QC_DELIMITER) if part
    )
    return row.canonical["sequence_core"], skip, flags

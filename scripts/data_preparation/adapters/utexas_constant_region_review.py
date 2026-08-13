"""UTexas constant-region rule review package (proposal only; no trims applied).

Builds rule-level candidate tables, membership sidecars, decision templates and
a sequence-safe review summary. Never mutates canonical sequences.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from common.constant_region_inference import GroupInferenceDiagnostics

RULE_CANDIDATE_COLUMNS: tuple[str, ...] = (
    "candidate_rule_id",
    "side",
    "motif_or_motif_id",
    "motif_length",
    "evidence_sources",
    "agreement_category",
    "conflict_status",
    "number_of_groups",
    "number_of_records",
    "records_matching_exactly",
    "match_fraction",
    "group_consensus_support",
    "documented_random_region_lengths",
    "source_documented",
    "hypothetical_core_length_min",
    "hypothetical_core_length_median",
    "hypothetical_core_length_max",
    "n_would_fail_min_length",
    "n_would_exceed_40pct_trim",
    "n_prefix_or_suffix_not_exactly_matched",
    "recommended_review_priority",
)

RULE_MEMBERSHIP_COLUMNS: tuple[str, ...] = (
    "candidate_rule_id",
    "record_id",
    "native_id",
    "proposal_source",
    "side",
    "motif_or_motif_id",
    "exact_match",
    "sequence_length_full",
    "hypothetical_core_length",
    "fraction_trimmed",
    "would_leave_core_below_20",
    "would_trim_more_than_40_percent",
    "prefix_or_suffix_not_exactly_matched",
)

REVIEW_DECISION_COLUMNS: tuple[str, ...] = (
    "candidate_rule_id",
    "decision",
    "review_note",
    "reviewer_initials",
)

ALLOWED_REVIEW_DECISIONS: frozenset[str] = frozenset(
    {"approve", "reject", "needs_source_review", ""}
)

REVIEW_POLICY_VERSION: str = "utexas_constant_region_rules_v1"
REVIEW_DECISION_DATE: str = "2026-08-13"
REVIEW_SCOPE: str = "constant_region_rules"

EXPECTED_CANDIDATE_RULES: int = 569
EXPECTED_APPROVE: int = 47
EXPECTED_NEEDS_SOURCE_REVIEW: int = 522
EXPECTED_REJECT: int = 0
EXPECTED_AGREEMENT_COUNTS: dict[str, int] = {
    "pool_type_only": 464,
    "conflicting_evidence": 56,
    "pool_type_plus_consensus_agree": 47,
    "known_motif_only": 1,
    "consensus_only": 1,
}

RESOLUTION_MANIFEST_COLUMNS: tuple[str, ...] = (
    "candidate_rule_id",
    "side",
    "motif_length",
    "evidence_sources",
    "agreement_category",
    "conflict_status",
    "decision",
    "reviewer_note_present",
    "reviewer_note_sha256",
)

NOTE_APPROVE_AGREE = (
    "Approved: source-documented Pool Type and qualifying target+publication "
    "consensus agree; no rule-level trim guard-rail violation."
)
NOTE_APPROVE_CONSENSUS = (
    "Approved: Tier-2 target+publication consensus satisfies the plan "
    "thresholds and has no rule-level guard-rail violation."
)
NOTE_POOL_ONLY = (
    "Needs source review: source-documented Pool Type evidence is not "
    "independently confirmed by qualifying Tier-2 consensus."
)
NOTE_CONFLICT = (
    "Needs source review: constant-region evidence channels conflict."
)
NOTE_KNOWN = (
    "Needs source review: known-motif detection conflicts with other "
    "construct evidence; do not choose a trim extent automatically."
)
NOTE_GUARD40 = (
    "Needs source review: otherwise supported rule has a hypothetical "
    "application exceeding the 40% trim guard rail."
)
NOTE_DEFAULT_UNRESOLVED = (
    "Needs source review: trim rule remains unresolved pending source "
    "or CHECKPOINT-1 review."
)


@dataclass
class HypotheticalTrimEffect:
    """Simulated effect of applying one proposed trim to one record."""

    matched: bool
    sequence_length_full: int
    hypothetical_core_length: int | None
    fraction_trimmed: float | None
    would_leave_core_below_20: bool
    would_trim_more_than_40_percent: bool
    prefix_or_suffix_not_exactly_matched: bool


@dataclass
class ConstantRegionReviewPackage:
    """Artefacts for Laura/ChatGPT trim-rule review."""

    proposals: list[dict[str, str]]
    rule_candidates: list[dict[str, str]]
    rule_membership: list[dict[str, str]]
    review_decisions: list[dict[str, str]]
    summary_markdown: str
    diagnostics: GroupInferenceDiagnostics
    agreement_counts: dict[str, int] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)


def _comparison_form(sequence: str) -> str:
    return sequence.upper().replace("U", "T")


def simulate_hypothetical_trim(
    sequence_full: str,
    *,
    side: str,
    motif: str,
    min_core_length: int = 20,
    max_fraction: float = 0.40,
) -> HypotheticalTrimEffect:
    """Simulate a trim without mutating the sequence."""
    full = sequence_full or ""
    full_len = len(full)
    if not full or not motif:
        return HypotheticalTrimEffect(
            matched=False,
            sequence_length_full=full_len,
            hypothetical_core_length=None,
            fraction_trimmed=None,
            would_leave_core_below_20=False,
            would_trim_more_than_40_percent=False,
            prefix_or_suffix_not_exactly_matched=True,
        )

    compared_full = _comparison_form(full)
    compared_motif = _comparison_form(motif)
    if side == "five_prime":
        matched = compared_full.startswith(compared_motif)
        core = full[len(motif) :] if matched else None
    elif side == "three_prime":
        matched = compared_full.endswith(compared_motif)
        core = full[: full_len - len(motif)] if matched else None
    else:
        matched = False
        core = None

    if not matched or core is None:
        return HypotheticalTrimEffect(
            matched=False,
            sequence_length_full=full_len,
            hypothetical_core_length=None,
            fraction_trimmed=None,
            would_leave_core_below_20=False,
            would_trim_more_than_40_percent=False,
            prefix_or_suffix_not_exactly_matched=True,
        )

    core_len = len(core)
    fraction = (len(motif) / full_len) if full_len else 0.0
    return HypotheticalTrimEffect(
        matched=True,
        sequence_length_full=full_len,
        hypothetical_core_length=core_len,
        fraction_trimmed=fraction,
        would_leave_core_below_20=core_len < min_core_length,
        would_trim_more_than_40_percent=fraction > max_fraction,
        prefix_or_suffix_not_exactly_matched=False,
    )


def _motif_key(side: str, motif_or_id: str) -> str:
    text = (motif_or_id or "").strip()
    if not text:
        return f"{side}:"
    # Known-motif IDs stay as identifiers; sequence motifs compare in T/U-collapsed form.
    if all(ch in "ACGTUacgtu" for ch in text):
        return f"{side}:{_comparison_form(text)}"
    return f"{side}:{text}"


def _rule_id_for(side: str, motif_or_id: str) -> str:
    digest = hashlib.sha256(_motif_key(side, motif_or_id).encode("utf-8")).hexdigest()[:12]
    return f"utexas_rule:{side}:{digest}"


def _fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _median(values: Sequence[int]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _priority(
    *,
    agreement_category: str,
    conflict: bool,
    n_fail_min: int,
    n_exceed_40: int,
) -> str:
    if conflict or agreement_category == "conflicting_evidence":
        return "high_conflict"
    if n_fail_min or n_exceed_40:
        return "high_guardrail"
    if agreement_category in {
        "pool_type_plus_consensus_agree",
        "known_motif_plus_other_agree",
    }:
        return "high_agreement"
    if agreement_category in {"known_motif_only", "pool_type_only", "consensus_only"}:
        return "medium"
    return "medium"


def _as_int(value: str | None, default: int = 0) -> int:
    text = (value or "").strip()
    if not text:
        return default
    return int(text)


def _as_float(value: str | None, default: float = 0.0) -> float:
    text = (value or "").strip()
    if not text:
        return default
    return float(text)


def _note_sha256(note: str) -> str:
    if not note:
        return ""
    return hashlib.sha256(note.encode("utf-8")).hexdigest()


def validate_reviewed_candidate_package(
    candidates: Sequence[Mapping[str, str]],
    *,
    decisions: Sequence[Mapping[str, str]] | None = None,
) -> None:
    """Hard-fail if the review package differs from the reviewed 569-rule set."""
    if len(candidates) != EXPECTED_CANDIDATE_RULES:
        raise ValueError(
            f"candidate rules must be {EXPECTED_CANDIDATE_RULES}; got {len(candidates)}"
        )
    cand_ids = [row["candidate_rule_id"] for row in candidates]
    if len(set(cand_ids)) != EXPECTED_CANDIDATE_RULES:
        raise ValueError("candidate_rule_id values are not unique in candidates")
    agreement = {}
    for row in candidates:
        key = row.get("agreement_category") or ""
        agreement[key] = agreement.get(key, 0) + 1
    if agreement != EXPECTED_AGREEMENT_COUNTS:
        raise ValueError(
            f"agreement_category counts differ from reviewed inputs: {agreement}"
        )
    if decisions is None:
        return
    if len(decisions) != EXPECTED_CANDIDATE_RULES:
        raise ValueError(
            f"decision-template rows must be {EXPECTED_CANDIDATE_RULES}; "
            f"got {len(decisions)}"
        )
    dec_ids = [row["candidate_rule_id"] for row in decisions]
    if len(set(dec_ids)) != EXPECTED_CANDIDATE_RULES:
        raise ValueError("candidate_rule_id values are not unique in decisions")
    if set(cand_ids) != set(dec_ids):
        raise ValueError("candidate ID sets in candidates and decisions are not equal")


def _is_safe_agreement_approve(row: Mapping[str, str]) -> bool:
    return (
        row.get("agreement_category") == "pool_type_plus_consensus_agree"
        and (row.get("conflict_status") or "none") == "none"
        and _as_float(row.get("group_consensus_support")) >= 0.80
        and _as_int(row.get("motif_length")) >= 12
        and _as_int(row.get("n_would_fail_min_length")) == 0
        and _as_int(row.get("n_would_exceed_40pct_trim")) == 0
    )


def _is_safe_consensus_only_approve(row: Mapping[str, str]) -> bool:
    return (
        row.get("agreement_category") == "consensus_only"
        and (row.get("conflict_status") or "none") == "none"
        and _as_float(row.get("group_consensus_support")) >= 0.80
        and _as_int(row.get("motif_length")) >= 12
        and _as_int(row.get("n_would_fail_min_length")) == 0
        and _as_int(row.get("n_would_exceed_40pct_trim")) == 0
    )


def apply_explicit_review_decisions(
    candidates: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Fill the human-reviewed UTexas constant-region decision policy."""
    validate_reviewed_candidate_package(candidates)
    decisions: list[dict[str, str]] = []
    for row in candidates:
        if _is_safe_agreement_approve(row):
            decision = "approve"
            note = NOTE_APPROVE_AGREE
        elif _is_safe_consensus_only_approve(row):
            decision = "approve"
            note = NOTE_APPROVE_CONSENSUS
        else:
            decision = "needs_source_review"
            category = row.get("agreement_category") or ""
            if category == "pool_type_only":
                note = NOTE_POOL_ONLY
            elif category == "conflicting_evidence":
                note = NOTE_CONFLICT
            elif category == "known_motif_only":
                note = NOTE_KNOWN
            elif (
                category == "pool_type_plus_consensus_agree"
                and _as_int(row.get("n_would_exceed_40pct_trim")) > 0
            ):
                note = NOTE_GUARD40
            else:
                note = NOTE_DEFAULT_UNRESOLVED
        decisions.append(
            {
                "candidate_rule_id": row["candidate_rule_id"],
                "decision": decision,
                "review_note": note,
                "reviewer_initials": "",
            }
        )
    decisions.sort(key=lambda item: item["candidate_rule_id"])
    counts = {}
    for row in decisions:
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1
    if counts.get("approve", 0) != EXPECTED_APPROVE:
        raise ValueError(
            f"approve count must be {EXPECTED_APPROVE}; got {counts.get('approve', 0)}"
        )
    if counts.get("needs_source_review", 0) != EXPECTED_NEEDS_SOURCE_REVIEW:
        raise ValueError(
            "needs_source_review count must be "
            f"{EXPECTED_NEEDS_SOURCE_REVIEW}; got {counts.get('needs_source_review', 0)}"
        )
    if counts.get("reject", 0) != EXPECTED_REJECT:
        raise ValueError(
            f"reject count must be {EXPECTED_REJECT}; got {counts.get('reject', 0)}"
        )
    if any(not row["decision"] for row in decisions):
        raise ValueError("blank decisions remain after explicit review policy")
    if len(decisions) != EXPECTED_CANDIDATE_RULES:
        raise ValueError(
            f"decision total must be {EXPECTED_CANDIDATE_RULES}; got {len(decisions)}"
        )
    return decisions


def build_resolution_manifest_rows(
    candidates: Sequence[Mapping[str, str]],
    decisions: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Sequence-safe tracked resolution rows (no aptamer records)."""
    notes = {row["candidate_rule_id"]: row for row in decisions}
    manifest: list[dict[str, str]] = []
    for row in candidates:
        rule_id = row["candidate_rule_id"]
        decision_row = notes[rule_id]
        note = decision_row.get("review_note") or ""
        manifest.append(
            {
                "candidate_rule_id": rule_id,
                "side": row.get("side") or "",
                "motif_length": row.get("motif_length") or "",
                "evidence_sources": row.get("evidence_sources") or "",
                "agreement_category": row.get("agreement_category") or "",
                "conflict_status": row.get("conflict_status") or "",
                "decision": decision_row.get("decision") or "",
                "reviewer_note_present": "true" if note else "false",
                "reviewer_note_sha256": _note_sha256(note),
            }
        )
    manifest.sort(key=lambda item: item["candidate_rule_id"])
    return manifest


def build_approved_trim_rules_payload(
    candidates: Sequence[Mapping[str, str]],
    decisions: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Build the tracked approved-trim-rule config (source-scoped motifs)."""
    decision_by_id = {row["candidate_rule_id"]: row["decision"] for row in decisions}
    rules: list[dict[str, Any]] = []
    for row in candidates:
        if decision_by_id.get(row["candidate_rule_id"]) != "approve":
            continue
        motif = (row.get("motif_or_motif_id") or "").strip()
        if not motif or not all(ch in "ACGTUacgtu" for ch in motif):
            raise ValueError(
                "approved rule must have a nucleotide motif for exact matching"
            )
        rules.append(
            {
                "candidate_rule_id": row["candidate_rule_id"],
                "side": row["side"],
                "motif": motif.upper(),
                "motif_length": _as_int(row.get("motif_length")),
                "evidence_sources": row.get("evidence_sources") or "",
                "agreement_category": row.get("agreement_category") or "",
                "group_consensus_support": row.get("group_consensus_support") or "",
                "confidence": "medium",
            }
        )
    rules.sort(key=lambda item: item["candidate_rule_id"])
    if len(rules) != EXPECTED_APPROVE:
        raise ValueError(
            f"approved trim rule count must be {EXPECTED_APPROVE}; got {len(rules)}"
        )
    return {
        "source_key": "utexas",
        "review_scope": REVIEW_SCOPE,
        "review_policy_version": REVIEW_POLICY_VERSION,
        "trim_confidence": "medium",
        "apply_approved_trims": True,
        "rules": rules,
    }


def build_review_metadata(
    *,
    candidate_sha256: str,
    decision_sha256: str,
    approved_count: int = EXPECTED_APPROVE,
    needs_source_review_count: int = EXPECTED_NEEDS_SOURCE_REVIEW,
    rejected_count: int = EXPECTED_REJECT,
) -> dict[str, Any]:
    """Tracked sequence-safe review metadata."""
    return {
        "source_key": "utexas",
        "review_scope": REVIEW_SCOPE,
        "review_policy_version": REVIEW_POLICY_VERSION,
        "review_model": "single_reviewer",
        "reviewer_initials_required": False,
        "decision_date": REVIEW_DECISION_DATE,
        "candidate_count": EXPECTED_CANDIDATE_RULES,
        "approved_count": approved_count,
        "needs_source_review_count": needs_source_review_count,
        "rejected_count": rejected_count,
        "candidate_file_sha256": candidate_sha256,
        "decision_file_sha256": decision_sha256,
        "checkpoint_status": "constant_region_rules_closed",
        "next_stage": "S3_not_started",
    }


def build_constant_region_review_package(
    *,
    proposals: Sequence[Mapping[str, str]],
    normalised_rows: Sequence[Mapping[str, str]],
    group_membership: Mapping[str, Sequence[str]],
    pool_type_record_ids: Mapping[str, Sequence[str]],
    diagnostics: GroupInferenceDiagnostics,
    old_proposal_rows: int = 1653,
    old_pool_type: int = 816,
    old_group_consensus: int = 816,
    old_known_motif: int = 21,
    old_zero_length: int = 717,
    apply_reviewed_policy: bool = False,
) -> ConstantRegionReviewPackage:
    """Collapse row/group proposals into unique candidate trim rules."""
    by_record = {row["record_id"]: row for row in normalised_rows}

    # Index proposals by motif key and collect evidence channels.
    buckets: dict[str, dict[str, Any]] = {}
    for proposal in proposals:
        source = proposal["proposal_source"]
        side = proposal["side"]
        motif = (proposal.get("proposed_sequence") or "").strip()
        motif_id = (proposal.get("motif_id") or "").strip()
        motif_or_id = motif_id if source == "known_motif" else motif
        if not motif_or_id:
            continue
        key = _motif_key(side, motif_or_id)
        entry = buckets.get(key)
        if entry is None:
            entry = {
                "side": side,
                "motif_or_id": motif_or_id,
                "motif_length": int(proposal["motif_length"] or 0),
                "sources": set(),
                "groups": set(),
                "record_ids": set(),
                "exact_matches": 0,
                "considered": 0,
                "supports": [],
                "documented_n": set(),
                "source_documented": False,
                "proposals": [],
            }
            buckets[key] = entry
        entry["sources"].add(source)
        entry["proposals"].append(proposal)
        if proposal.get("source_documented") == "yes":
            entry["source_documented"] = True
        group_id = proposal.get("experiment_group_id") or ""
        if group_id:
            entry["groups"].add(group_id)
        if source == "group_consensus":
            members = group_membership.get(group_id, ())
            entry["record_ids"].update(members)
            entry["supports"].append(float(proposal.get("support") or 0.0))
            entry["considered"] += int(proposal.get("records_considered") or 0)
            entry["exact_matches"] += int(proposal.get("records_matching_exactly") or 0)
        elif source == "pool_type":
            members = pool_type_record_ids.get(group_id, ())
            entry["record_ids"].update(members)
            entry["considered"] += int(proposal.get("records_considered") or 0)
            entry["exact_matches"] += int(proposal.get("records_matching_exactly") or 0)
            nlen = (proposal.get("documented_random_region_length") or "").strip()
            if nlen:
                entry["documented_n"].add(nlen)
        elif source == "known_motif":
            # known_motif proposals are record-scoped; experiment_group_id holds record_id
            rid = group_id
            if rid:
                entry["record_ids"].add(rid)
            entry["considered"] += 1
            entry["exact_matches"] += int(proposal.get("records_matching_exactly") or 1)

    rule_candidates: list[dict[str, str]] = []
    rule_membership: list[dict[str, str]] = []
    agreement_counts: dict[str, int] = defaultdict(int)

    for key in sorted(buckets):
        entry = buckets[key]
        sources = frozenset(entry["sources"])
        side = entry["side"]
        motif_or_id = entry["motif_or_id"]
        rule_id = _rule_id_for(side, motif_or_id)

        has_pool = "pool_type" in sources
        has_consensus = "group_consensus" in sources
        has_known = "known_motif" in sources

        conflict = False
        if has_pool and has_consensus:
            # Same motif key means agreement on motif identity; disagreement is
            # handled separately when pool and consensus propose different motifs
            # for overlapping records (see cross-check below).
            agreement = "pool_type_plus_consensus_agree"
        elif has_known and (has_pool or has_consensus):
            agreement = "known_motif_plus_other_agree"
        elif has_known:
            agreement = "known_motif_only"
        elif has_pool:
            agreement = "pool_type_only"
        elif has_consensus:
            agreement = "consensus_only"
        else:
            agreement = "other"

        # Detect conflicting motifs on the same side for overlapping records.
        # Marked after all buckets exist; placeholder refined below.
        core_lengths: list[int] = []
        n_fail_min = 0
        n_exceed_40 = 0
        n_unmatched = 0
        exact_for_rule = 0
        for record_id in sorted(entry["record_ids"]):
            row = by_record.get(record_id)
            if row is None:
                continue
            sequence_full = row.get("sequence_full") or ""
            if entry["motif_length"] and all(ch in "ACGTUacgtu" for ch in motif_or_id):
                effect = simulate_hypothetical_trim(
                    sequence_full,
                    side=side,
                    motif=motif_or_id,
                )
            else:
                # Known motif ID without sequence in this artefact: use proposal fields.
                effect = HypotheticalTrimEffect(
                    matched=True,
                    sequence_length_full=len(sequence_full),
                    hypothetical_core_length=(
                        len(sequence_full) - entry["motif_length"]
                        if sequence_full and entry["motif_length"]
                        else None
                    ),
                    fraction_trimmed=(
                        (entry["motif_length"] / len(sequence_full))
                        if sequence_full and entry["motif_length"]
                        else None
                    ),
                    would_leave_core_below_20=False,
                    would_trim_more_than_40_percent=False,
                    prefix_or_suffix_not_exactly_matched=False,
                )
                if effect.hypothetical_core_length is not None:
                    effect.would_leave_core_below_20 = (
                        effect.hypothetical_core_length < 20
                    )
                if effect.fraction_trimmed is not None:
                    effect.would_trim_more_than_40_percent = (
                        effect.fraction_trimmed > 0.40
                    )

            if effect.matched and effect.hypothetical_core_length is not None:
                core_lengths.append(effect.hypothetical_core_length)
                exact_for_rule += 1
            if effect.would_leave_core_below_20:
                n_fail_min += 1
            if effect.would_trim_more_than_40_percent:
                n_exceed_40 += 1
            if effect.prefix_or_suffix_not_exactly_matched:
                n_unmatched += 1

            # Determine which proposal sources claim this record.
            record_sources: list[str] = []
            if has_pool and record_id in set().union(
                *[set(pool_type_record_ids.get(g, ())) for g in entry["groups"]]
            ):
                record_sources.append("pool_type")
            if has_consensus and record_id in set().union(
                *[set(group_membership.get(g, ())) for g in entry["groups"]]
            ):
                record_sources.append("group_consensus")
            if has_known and record_id in entry["record_ids"] and "known_motif" in sources:
                # known motif membership is record-scoped
                if any(
                    p.get("proposal_source") == "known_motif"
                    and p.get("experiment_group_id") == record_id
                    for p in entry["proposals"]
                ):
                    record_sources.append("known_motif")
            if not record_sources:
                record_sources = sorted(sources)

            for source_name in sorted(set(record_sources)):
                rule_membership.append(
                    {
                        "candidate_rule_id": rule_id,
                        "record_id": record_id,
                        "native_id": row.get("native_id", ""),
                        "proposal_source": source_name,
                        "side": side,
                        "motif_or_motif_id": motif_or_id,
                        "exact_match": "true" if effect.matched else "false",
                        "sequence_length_full": str(effect.sequence_length_full),
                        "hypothetical_core_length": (
                            ""
                            if effect.hypothetical_core_length is None
                            else str(effect.hypothetical_core_length)
                        ),
                        "fraction_trimmed": _fmt_float(effect.fraction_trimmed),
                        "would_leave_core_below_20": (
                            "true" if effect.would_leave_core_below_20 else "false"
                        ),
                        "would_trim_more_than_40_percent": (
                            "true" if effect.would_trim_more_than_40_percent else "false"
                        ),
                        "prefix_or_suffix_not_exactly_matched": (
                            "true"
                            if effect.prefix_or_suffix_not_exactly_matched
                            else "false"
                        ),
                    }
                )

        n_records = len(entry["record_ids"])
        match_fraction = (exact_for_rule / n_records) if n_records else 0.0
        support_val = max(entry["supports"]) if entry["supports"] else None
        median_core = _median(core_lengths)

        rule_candidates.append(
            {
                "candidate_rule_id": rule_id,
                "side": side,
                "motif_or_motif_id": motif_or_id,
                "motif_length": str(entry["motif_length"]),
                "evidence_sources": "|".join(sorted(sources)),
                "agreement_category": agreement,
                "conflict_status": "conflict" if conflict else "none",
                "number_of_groups": str(len(entry["groups"])),
                "number_of_records": str(n_records),
                "records_matching_exactly": str(exact_for_rule),
                "match_fraction": _fmt_float(match_fraction),
                "group_consensus_support": _fmt_float(support_val),
                "documented_random_region_lengths": "|".join(
                    sorted(entry["documented_n"])
                ),
                "source_documented": "yes" if entry["source_documented"] else "no",
                "hypothetical_core_length_min": (
                    str(min(core_lengths)) if core_lengths else ""
                ),
                "hypothetical_core_length_median": (
                    _fmt_float(median_core) if median_core is not None else ""
                ),
                "hypothetical_core_length_max": (
                    str(max(core_lengths)) if core_lengths else ""
                ),
                "n_would_fail_min_length": str(n_fail_min),
                "n_would_exceed_40pct_trim": str(n_exceed_40),
                "n_prefix_or_suffix_not_exactly_matched": str(n_unmatched),
                "recommended_review_priority": _priority(
                    agreement_category=agreement,
                    conflict=conflict,
                    n_fail_min=n_fail_min,
                    n_exceed_40=n_exceed_40,
                ),
            }
        )
        agreement_counts[agreement] += 1

    # Cross-evidence conflict: same record+side claimed by different motifs.
    record_side_motifs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for member in rule_membership:
        record_side_motifs[(member["record_id"], member["side"])].add(
            member["motif_or_motif_id"]
        )
    conflicted_rules: set[str] = set()
    for (record_id, side), motifs in record_side_motifs.items():
        if len(motifs) > 1:
            for candidate in rule_candidates:
                if candidate["side"] != side:
                    continue
                if candidate["motif_or_motif_id"] in motifs:
                    conflicted_rules.add(candidate["candidate_rule_id"])

    for candidate in rule_candidates:
        if candidate["candidate_rule_id"] in conflicted_rules:
            candidate["conflict_status"] = "conflict"
            if candidate["agreement_category"] in {
                "pool_type_plus_consensus_agree",
                "known_motif_plus_other_agree",
                "pool_type_only",
                "consensus_only",
            }:
                # Overlapping records have competing motifs from other rules.
                if "pool_type" in candidate["evidence_sources"] and (
                    "group_consensus" in candidate["evidence_sources"]
                ):
                    pass
                candidate["agreement_category"] = "conflicting_evidence"
                candidate["recommended_review_priority"] = "high_conflict"
            agreement_counts["conflicting_evidence"] = agreement_counts.get(
                "conflicting_evidence", 0
            )

    # Recount agreement categories after conflict marking.
    agreement_counts = defaultdict(int)
    for candidate in rule_candidates:
        agreement_counts[candidate["agreement_category"]] += 1

    rule_candidates.sort(key=lambda row: row["candidate_rule_id"])
    rule_membership.sort(
        key=lambda row: (row["candidate_rule_id"], row["record_id"], row["proposal_source"])
    )
    if apply_reviewed_policy:
        validate_reviewed_candidate_package(rule_candidates)
        review_decisions = apply_explicit_review_decisions(rule_candidates)
    else:
        review_decisions = [
            {
                "candidate_rule_id": row["candidate_rule_id"],
                "decision": "",
                "review_note": "",
                "reviewer_initials": "",
            }
            for row in rule_candidates
        ]
    decision_counts: dict[str, int] = defaultdict(int)
    for row in review_decisions:
        key = row["decision"] or "blank"
        decision_counts[key] += 1

    source_counts: dict[str, int] = defaultdict(int)
    for proposal in proposals:
        source_counts[proposal["proposal_source"]] += 1

    records_affected = {m["record_id"] for m in rule_membership}
    cores_20_100 = 0
    cores_below_20 = 0
    exceed_40_records = 0
    seen_record_effect: set[tuple[str, str]] = set()
    for member in rule_membership:
        key = (member["record_id"], member["candidate_rule_id"])
        if key in seen_record_effect:
            continue
        seen_record_effect.add(key)
        core = member["hypothetical_core_length"]
        if core:
            core_i = int(core)
            if 20 <= core_i <= 100:
                cores_20_100 += 1
            if core_i < 20:
                cores_below_20 += 1
        if member["would_trim_more_than_40_percent"] == "true":
            exceed_40_records += 1

    high_priority = sum(
        1
        for row in rule_candidates
        if row["recommended_review_priority"].startswith("high")
    )
    conflicted = sum(
        1 for row in rule_candidates if row["conflict_status"] == "conflict"
    )
    needs_source = sum(
        1
        for row in rule_candidates
        if row["agreement_category"] in {"pool_type_only", "conflicting_evidence"}
    )
    rules_fail_min = sum(
        1 for row in rule_candidates if int(row["n_would_fail_min_length"]) > 0
    )
    rules_exceed_40 = sum(
        1 for row in rule_candidates if int(row["n_would_exceed_40pct_trim"]) > 0
    )

    # Pool-type empirical agreement bands from proposals.
    pool_props = [p for p in proposals if p["proposal_source"] == "pool_type"]
    perfect = 0
    partial = 0
    poor = 0
    for prop in pool_props:
        frac = float(prop.get("empirical_exact_match_fraction") or 0.0)
        if frac >= 0.999:
            perfect += 1
        elif frac >= 0.5:
            partial += 1
        else:
            poor += 1

    groups_ge5 = (
        diagnostics.groups_total
        - diagnostics.groups_below_min_size
    )

    summary_lines = [
        "# UTexas constant-region trim review summary",
        "",
        "Sequence-safe report for Laura/ChatGPT review. Literal aptamer sequences",
        "are omitted. Known motifs may be named by identifier.",
        "",
        "## Previous S2 proposal state (superseded)",
        "",
        "The following counts came from the first UTexas S2 proposal pass, which",
        "incorrectly grouped Tier-2 consensus by Pool Type. They are retained only",
        "as a superseded diagnostic baseline:",
        "",
        f"- old proposal rows = `{old_proposal_rows}`",
        f"- pool_type = `{old_pool_type}`",
        f"- group_consensus = `{old_group_consensus}`",
        f"- known_motif = `{old_known_motif}`",
        f"- old zero-length consensus pseudo-proposals = `{old_zero_length}`",
        "- applied trims = `0`",
        "",
        "## Corrected grouping",
        "",
        "- Tier-2 grouping key = `(source_db, target_name_raw, publication)`",
        "- Pool Type is **not** used as the Tier-2 consensus key",
        f"- `(target_name_raw, publication)` groups = `{diagnostics.groups_total}`",
        f"- group-size histogram = `{dict(diagnostics.group_size_histogram)}`",
        f"- groups with >=5 records (eligible) ≈ `{groups_ge5}` "
        f"(total minus below-min-size groups `{diagnostics.groups_below_min_size}`)",
        f"- groups producing qualifying 5′ consensus = "
        f"`{diagnostics.groups_qualifying_prefix}`",
        f"- groups producing qualifying 3′ consensus = "
        f"`{diagnostics.groups_qualifying_suffix}`",
        f"- qualifying Tier-2 proposal count = `{source_counts.get('group_consensus', 0)}`",
        f"- skipped rows lacking target+publication grouping evidence = "
        f"`{diagnostics.skipped_missing_group}`",
        f"- groups with usable sequences below minimum = "
        f"`{diagnostics.groups_usable_below_min_size}`",
        f"- groups with no qualifying 5′ motif = "
        f"`{diagnostics.groups_no_qualifying_prefix}`",
        f"- groups with no qualifying 3′ motif = "
        f"`{diagnostics.groups_no_qualifying_suffix}`",
        "",
        "## Pool Type evidence",
        "",
        "- Pool Type remains independent **source-documented** library-design evidence",
        f"- source-documented Pool Type proposals = `{source_counts.get('pool_type', 0)}`",
        f"- empirical exact-match perfect (>=0.999) = `{perfect}`",
        f"- empirical exact-match partial (0.5–0.999) = `{partial}`",
        f"- empirical exact-match zero/poor (<0.5) = `{poor}`",
        "",
        "## Known-motif proposals",
        "",
        f"- known-motif proposals = `{source_counts.get('known_motif', 0)}`",
        "- Detection does not authorise trimming",
        "",
        "## Cross-evidence agreement (rule-level)",
        "",
    ]
    for name in sorted(agreement_counts):
        summary_lines.append(f"- `{name}` = `{agreement_counts[name]}`")
    summary_lines.extend(
        [
            "",
            "## Rule-level review burden",
            "",
            f"- unique candidate rules = `{len(rule_candidates)}`",
            f"- high-priority rules = `{high_priority}`",
            f"- conflicted rules = `{conflicted}`",
            f"- rules requiring source review (pool-only or conflicted) = `{needs_source}`",
            f"- rules that would violate minimum core length for ≥1 record = "
            f"`{rules_fail_min}`",
            f"- rules exceeding 40% hypothetical trim for ≥1 record = "
            f"`{rules_exceed_40}`",
            "",
            "## Hypothetical trim effects",
            "",
            f"- records affected = `{len(records_affected)}`",
            f"- record-rule pairs whose hypothetical core is 20–100 nt = "
            f"`{cores_20_100}`",
            f"- record-rule pairs whose hypothetical core would be <20 nt = "
            f"`{cores_below_20}`",
            f"- record-rule pairs exceeding 40% trim = `{exceed_40_records}`",
            "",
            "## Corrected proposal counts",
            "",
            f"- corrected genuine proposals = `{len(proposals)}`",
            f"- pool-type proposals = `{source_counts.get('pool_type', 0)}`",
            f"- qualifying target+publication consensus proposals = "
            f"`{source_counts.get('group_consensus', 0)}`",
            f"- known-motif proposals = `{source_counts.get('known_motif', 0)}`",
            "- new zero-length proposals = `0`",
            "",
            "## Human-reviewed rule decisions",
            "",
            f"- approve = `{decision_counts.get('approve', 0)}`",
            f"- needs_source_review = `{decision_counts.get('needs_source_review', 0)}`",
            f"- reject = `{decision_counts.get('reject', 0)}`",
            f"- blank = `{decision_counts.get('blank', 0)}`",
            "",
            "Unresolved `needs_source_review` rules are not applied.",
            "",
            "## Pipeline state",
            "",
            "```text",
            "Constant-region rule review recorded.",
            "Unresolved rules remain pending source/CHECKPOINT-1 review.",
            "S3 has not started.",
            "CHECKPOINT-1 record eligibility review has not started.",
            "```",
            "",
        ]
    )

    stats = {
        "genuine_proposals": len(proposals),
        "proposal_source_counts": dict(source_counts),
        "unique_candidate_rules": len(rule_candidates),
        "high_priority_rules": high_priority,
        "conflicted_rules": conflicted,
        "rules_fail_min_core": rules_fail_min,
        "rules_exceed_40pct": rules_exceed_40,
        "records_affected": len(records_affected),
        "agreement_counts": dict(agreement_counts),
        "pool_exact_perfect": perfect,
        "pool_exact_partial": partial,
        "pool_exact_poor": poor,
        "decision_counts": dict(decision_counts),
        "approved_count": int(decision_counts.get("approve", 0)),
        "needs_source_review_count": int(
            decision_counts.get("needs_source_review", 0)
        ),
    }
    return ConstantRegionReviewPackage(
        proposals=list(proposals),
        rule_candidates=rule_candidates,
        rule_membership=rule_membership,
        review_decisions=review_decisions,
        summary_markdown="\n".join(summary_lines) + "\n",
        diagnostics=diagnostics,
        agreement_counts=dict(agreement_counts),
        stats=stats,
    )


def write_review_package_files(
    package: ConstantRegionReviewPackage,
    output_dir: Path,
    *,
    write_csv_atomic,
) -> dict[str, Path]:
    """Write ignored review artefacts under the normalised output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "rule_candidates": output_dir / "utexas_constant_region_rule_candidates.csv",
        "rule_membership": output_dir / "utexas_constant_region_rule_membership.csv",
        "review_decisions": output_dir / "utexas_constant_region_review_decisions.csv",
        "review_summary": output_dir / "utexas_constant_region_review_summary.md",
    }
    write_csv_atomic(paths["rule_candidates"], RULE_CANDIDATE_COLUMNS, package.rule_candidates)
    write_csv_atomic(paths["rule_membership"], RULE_MEMBERSHIP_COLUMNS, package.rule_membership)
    write_csv_atomic(
        paths["review_decisions"], REVIEW_DECISION_COLUMNS, package.review_decisions
    )
    paths["review_summary"].write_text(package.summary_markdown, encoding="utf-8")
    return paths


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically write pretty-printed JSON with a trailing newline."""
    import os
    import tempfile

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def write_tracked_review_artefacts(
    *,
    repo_root: Path,
    candidates: Sequence[Mapping[str, str]],
    decisions: Sequence[Mapping[str, str]],
    candidate_sha256: str,
    decision_sha256: str,
    write_csv_atomic,
) -> dict[str, Path]:
    """Write sequence-safe tracked review provenance and approved-rule config."""
    repo_root = Path(repo_root)
    manifest_path = (
        repo_root / "config" / "checkpoint_reviews" / "utexas_constant_region_resolutions.csv"
    )
    metadata_path = (
        repo_root
        / "config"
        / "checkpoint_reviews"
        / "utexas_constant_region_review_metadata.json"
    )
    rules_path = (
        repo_root
        / "config"
        / "source_normalisation"
        / "utexas_approved_trim_rules.json"
    )
    write_csv_atomic(
        manifest_path,
        RESOLUTION_MANIFEST_COLUMNS,
        build_resolution_manifest_rows(candidates, decisions),
    )
    write_json_atomic(
        metadata_path,
        build_review_metadata(
            candidate_sha256=candidate_sha256,
            decision_sha256=decision_sha256,
        ),
    )
    write_json_atomic(
        rules_path, build_approved_trim_rules_payload(candidates, decisions)
    )
    return {
        "resolutions": manifest_path,
        "metadata": metadata_path,
        "approved_trim_rules": rules_path,
    }

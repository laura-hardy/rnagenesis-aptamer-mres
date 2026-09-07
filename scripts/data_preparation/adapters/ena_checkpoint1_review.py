"""ENA CHECKPOINT-1 structured review: group rules, exceptions, reconciliation.

Prepares rule-level constant-region review, hypothetical trim simulation,
record-level exceptions, and the 679-versus-676 legacy-collapse reconciliation.
Does not fill human decision fields, apply trims, collapse pairs, or start S4.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from adapters.ena_s3 import (
    REVIEW_REASON_BOUNDARY,
    REVIEW_REASON_COLLAPSE,
    REVIEW_REASON_JUDGEMENT,
    REVIEW_REASON_RANDOM,
    REVIEW_REASON_SOURCE_PROMOTER,
    REVIEW_REASON_TRANSCRIPTION,
)
from adapters.utexas_constant_region_review import simulate_hypothetical_trim
from finalize_ena_aptamer_supplement import (
    canonicalise_target,
    clean_rna_sequence,
    make_clean_record_id,
)

ALLOWED_MANUAL_DECISIONS: Final[frozenset[str]] = frozenset({"", "keep", "drop", "edit"})
ALLOWED_TRIM_ACTIONS: Final[frozenset[str]] = frozenset(
    {"", "approve", "override", "reject", "defer"}
)
ALLOWED_GROUP_OVERRIDE: Final[frozenset[str]] = frozenset({"", "true", "false"})
ALLOWED_RECONCILIATION_DECISIONS: Final[frozenset[str]] = frozenset(
    {"", "retain_both", "reject_one_member", "needs_source_review"}
)
MAX_COMBINED_TRIM_FRACTION: Final[float] = 0.40
CORE_LENGTH_MIN: Final[int] = 20
AUDIT_ONLY_REASONS: Final[frozenset[str]] = frozenset(
    {"length_boundary", "random_kept_audit"}
)

MANUAL_FIELDS: Final[tuple[str, ...]] = (
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

RECOMMENDATION_FIELDS: Final[tuple[str, ...]] = (
    "review_recommendation",
    "review_rationale",
    "requires_specific_human_decision",
    "recommended_manual_decision",
    "recommended_sequence_correction_op",
    "recommended_sequence_corrected",
    "recommended_molecule_type_override",
    "recommended_chemistry_override",
    "recommended_trim_action",
    "recommended_trim_5p_nt",
    "recommended_trim_3p_nt",
    "recommended_trim_group_override",
    "audit_only_row",
    "bulk_audit_eligible",
)

RULE_REVIEW_COLUMNS: Final[tuple[str, ...]] = (
    "constant_rule_id",
    "proposal_id",
    "experiment_group_id",
    "side",
    "inference_method",
    "confidence",
    "support",
    "motif_length",
    "group_size",
    "records_matching_exactly",
    "affected_s3_record_count",
    "source_promoter_overlap_count",
    "t_encoded_overlap_count",
    "length_boundary_overlap_count",
    "short_record_overlap_count",
    "n_not_exact_terminal_match",
    "n_same_side_conflict",
    "n_combined_trim",
    "n_hypothetical_core_below_20",
    "n_hypothetical_exceeds_40pct",
    "n_hard_invalid",
    "machine_recommendation",
    "machine_rationale",
    "requires_specific_human_decision",
    "recommended_trim_action",
    "manual_trim_action",
    "manual_trim_5p_nt",
    "manual_trim_3p_nt",
    "manual_notes",
)

RULE_SEQUENCE_COLUMNS: Final[frozenset[str]] = frozenset(
    {"proposed_sequence", "motif", "sequence_full", "sequence_core", "sequence_raw"}
)

RULE_MEMBERSHIP_COLUMNS: Final[tuple[str, ...]] = (
    "constant_rule_id",
    "proposal_id",
    "experiment_group_id",
    "record_id",
    "native_id",
    "side",
    "sequence_length_full",
    "sequence_length_core",
    "proposed_5p_removal_nt",
    "proposed_3p_removal_nt",
    "hypothetical_core_length",
    "fraction_removed",
    "exact_terminal_match",
    "opposite_end_also_proposed",
    "combined_trimming_would_occur",
    "combined_hypothetical_core_length",
    "combined_fraction_removed",
    "would_leave_core_below_20",
    "combined_would_exceed_40pct",
    "same_side_conflict",
    "hard_invalid",
    "hard_invalid_reason",
    "source_promoter_or_template_concern",
    "t_to_u_applied",
    "length_below_20",
    "length_boundary",
    "sequence_full",
    "sequence_core",
    "proposed_sequence",
)

EXCEPTION_COLUMNS: Final[tuple[str, ...]] = (
    "constant_rule_id",
    "proposal_id",
    "record_id",
    "exception_reason",
    "machine_recommendation",
    "machine_rationale",
    "manual_decision",
    "manual_trim_action",
    "manual_trim_5p_nt",
    "manual_trim_3p_nt",
    "manual_notes",
)

RECONCILIATION_COLUMNS: Final[tuple[str, ...]] = (
    "reconciliation_id",
    "record_id_a",
    "record_id_b",
    "review_unit_id_a",
    "review_unit_id_b",
    "clean_record_id",
    "legacy_t_to_u",
    "legacy_target_alias",
    "legacy_exact_sequence_target_consolidation",
    "unified_s2_sequence_full_identical",
    "raw_target_name_identical",
    "prior_manual_sequence_or_target_correction",
    "source_promoter_or_template_concern",
    "group_consensus_proposal",
    "machine_recommendation",
    "machine_rationale",
    "manual_decision",
    "manual_notes",
)

RECONCILIATION_INDEX_COLUMNS: Final[tuple[str, ...]] = RECONCILIATION_COLUMNS

BULK_CONFIRMATION_COLUMNS: Final[tuple[str, ...]] = (
    "confirmation_id",
    "scope",
    "eligible_record_count",
    "eligible_record_ids",
    "confirm",
    "reviewer_initials",
    "manual_notes",
)

BULK_CONFIRMATION_ID: Final[str] = "audit_only_keep_current_route"
BULK_SCOPE: Final[str] = "length_boundary_and_or_random_kept_audit_only"

REC_KEEP_CURRENT: Final[str] = "keep_current_route"
REC_CONFIRM_LENGTH_REJECT: Final[str] = "confirm_current_length_reject"
REC_NEEDS_CONSTRUCT: Final[str] = (
    "needs human construct review; no automatic trim"
)
REC_NEEDS_SOURCE_REVIEW: Final[str] = "needs_source_review"
REC_APPROVE_TRIM: Final[str] = "approve_candidate_trim"
REC_REJECT_TRIM: Final[str] = "reject_candidate_trim"
REC_RETAIN_BOTH: Final[str] = "retain_both_through_checkpoint_and_defer_exact_dedup"

RECONCILIATION_RATIONALE: Final[str] = (
    "Retain both 679-row identities through S3/CHECKPOINT-1 and defer exact "
    "sequence-target provenance merging to the later corpus-wide deduplication "
    "stage, unless human review identifies a genuine source-level reason to "
    "reject one member. Current source grain preserves all reviewed records; "
    "T→U is a legitimate S2 transformation; target canonicalisation has not "
    "yet occurred; exact deduplication belongs later and must merge provenance "
    "rather than silently delete evidence."
)


class EnaCheckpoint1ReviewError(ValueError):
    """Invalid ENA CHECKPOINT-1 review schema, validation, or input."""


@dataclass
class ValidationReport:
    """Fail-closed CHECKPOINT-1 review validation (aggregates only)."""

    total_review_records: int = 0
    unresolved_manual_decisions: int = 0
    unresolved_constant_rules: int = 0
    unresolved_exceptions: int = 0
    unresolved_reconciliation_groups: int = 0
    audit_only_unconfirmed: int = 0
    ready_for_application: int = 0
    blocking_issues: list[str] = field(default_factory=list)
    eligible_bulk_audit_ids: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.blocking_issues and self.ready_for_application > 0

    @property
    def unresolved_constant_groups(self) -> int:
        return self.unresolved_constant_rules


def _blank(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _truthy(value: str) -> bool:
    return _blank(value).lower() == "true"


def _fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def parse_review_reasons(value: str) -> frozenset[str]:
    return frozenset(part for part in _blank(value).split("|") if part)


def is_audit_only_row(row: Mapping[str, str]) -> bool:
    reasons = parse_review_reasons(row.get("checkpoint_review_reasons", ""))
    return bool(reasons) and reasons <= AUDIT_ONLY_REASONS


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise EnaCheckpoint1ReviewError(f"CSV has no header: {Path(path).name}")
        rows = list(reader)
    for row in rows:
        for key, value in list(row.items()):
            row[key] = "" if value is None else value
    return rows


def empty_manual_fields() -> dict[str, str]:
    return {name: "" for name in MANUAL_FIELDS}


def empty_recommendation_fields() -> dict[str, str]:
    return {name: "" for name in RECOMMENDATION_FIELDS}


def populate_record_recommendations(row: dict[str, str]) -> dict[str, str]:
    """Fill recommendation fields only. Never writes ``manual_*`` values."""
    out = dict(row)
    for name in RECOMMENDATION_FIELDS:
        out.setdefault(name, "")
    for name in MANUAL_FIELDS:
        out[name] = ""

    reasons = parse_review_reasons(out.get("checkpoint_review_reasons", ""))
    decision = out.get("proposed_decision", "")
    primary = out.get("primary_reason", "")
    audit_only = is_audit_only_row(out)

    if primary == "length_out_of_range" and decision == "proposed_reject":
        out["review_recommendation"] = REC_CONFIRM_LENGTH_REJECT
        out["review_rationale"] = (
            "Corpus core-length rule is 20–100 nt. Confirm the unified "
            "length-policy rejection unless Laura records an intentional "
            "source-specific exception."
        )
        out["requires_specific_human_decision"] = "true"
        out["recommended_manual_decision"] = "keep"
    elif REVIEW_REASON_JUDGEMENT in reasons and _truthy(
        out.get("source_promoter_or_template_concern", "")
    ):
        out["review_recommendation"] = REC_NEEDS_CONSTRUCT
        out["review_rationale"] = (
            "Needs human construct review; do not trim from legacy source "
            "flag alone. Shared known-motif detector found no match."
        )
        out["requires_specific_human_decision"] = "true"
        out["recommended_manual_decision"] = ""
        out["recommended_trim_action"] = ""
    elif REVIEW_REASON_TRANSCRIPTION in reasons or REVIEW_REASON_COLLAPSE in reasons:
        out["review_recommendation"] = REC_KEEP_CURRENT
        out["review_rationale"] = (
            "Keep the current technical route. T→U is a completed S2 "
            "transcription of an experimental RNA record; do not reconfirm "
            "molecule identity unless contradictory evidence exists."
        )
        out["requires_specific_human_decision"] = "false"
        out["recommended_manual_decision"] = "keep"
    elif audit_only:
        out["review_recommendation"] = REC_KEEP_CURRENT
        out["review_rationale"] = (
            "Eyeball/audit condition only; keep the current technical route."
        )
        out["requires_specific_human_decision"] = "false"
        out["recommended_manual_decision"] = "keep"
    else:
        out["review_recommendation"] = REC_KEEP_CURRENT
        out["review_rationale"] = "Keep the current technical route."
        out["requires_specific_human_decision"] = "false"
        out["recommended_manual_decision"] = "keep"

    out["audit_only_row"] = "true" if audit_only else "false"
    out["bulk_audit_eligible"] = "true" if audit_only else "false"
    for name in MANUAL_FIELDS:
        if out.get(name):
            raise EnaCheckpoint1ReviewError(
                f"Recommendations must not populate {name} for {out.get('record_id')!r}"
            )
    return out


def _parse_int(raw: str) -> int | None:
    text = _blank(raw)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _comparison_form(sequence: str) -> str:
    return (sequence or "").upper().replace("U", "T")


def simulate_member_detail(
    *,
    sequence_full: str,
    this_side: str,
    this_motif: str,
    opposite_motif: str,
    opposite_side: str,
    same_side_conflict: bool,
    source_promoter: bool,
    t_to_u_applied: bool,
    core_len: int | None,
) -> dict[str, str]:
    """Hypothetical one-record trim simulation. Does not mutate sequences."""
    this_effect = simulate_hypothetical_trim(
        sequence_full, side=this_side, motif=this_motif
    )
    five_nt = 0
    three_nt = 0
    if this_side == "five_prime" and this_effect.matched:
        five_nt = len(this_motif)
    elif this_side == "three_prime" and this_effect.matched:
        three_nt = len(this_motif)

    opposite_effect = None
    opposite_end = bool(opposite_motif)
    combined = False
    combined_core: int | None = None
    combined_fraction: float | None = None
    combined_over_40 = False
    combined_below_20 = False
    if opposite_end:
        opposite_effect = simulate_hypothetical_trim(
            sequence_full, side=opposite_side, motif=opposite_motif
        )
        if this_effect.matched and opposite_effect.matched:
            combined = True
            opp_five = len(opposite_motif) if opposite_side == "five_prime" else 0
            opp_three = len(opposite_motif) if opposite_side == "three_prime" else 0
            total_five = five_nt + opp_five
            total_three = three_nt + opp_three
            full_len = len(sequence_full or "")
            if total_five + total_three >= full_len:
                combined_core = 0
                combined_fraction = 1.0 if full_len else None
                combined_below_20 = True
                combined_over_40 = True
            else:
                combined_core = full_len - total_five - total_three
                combined_fraction = (
                    (total_five + total_three) / full_len if full_len else None
                )
                combined_below_20 = combined_core < CORE_LENGTH_MIN
                combined_over_40 = bool(
                    combined_fraction is not None
                    and combined_fraction > MAX_COMBINED_TRIM_FRACTION
                )

    hard_invalid = False
    hard_reason = ""
    if not this_motif:
        hard_invalid = True
        hard_reason = "missing_motif"
    elif not this_effect.matched:
        hard_invalid = True
        hard_reason = "non_terminal_match"
    elif this_effect.hypothetical_core_length is None:
        hard_invalid = True
        hard_reason = "impossible_trim_length"
    elif this_effect.hypothetical_core_length == 0:
        hard_invalid = True
        hard_reason = "empty_core"

    below_20 = bool(this_effect.would_leave_core_below_20 or combined_below_20)
    exceeds_40 = bool(
        this_effect.would_trim_more_than_40_percent or combined_over_40
    )
    length_boundary = False
    if core_len is not None and CORE_LENGTH_MIN <= core_len <= 25:
        length_boundary = True
    if core_len is not None and 90 <= core_len <= 100:
        length_boundary = True

    return {
        "sequence_length_full": str(this_effect.sequence_length_full),
        "proposed_5p_removal_nt": str(five_nt),
        "proposed_3p_removal_nt": str(three_nt),
        "hypothetical_core_length": (
            ""
            if this_effect.hypothetical_core_length is None
            else str(this_effect.hypothetical_core_length)
        ),
        "fraction_removed": _fmt_float(this_effect.fraction_trimmed),
        "exact_terminal_match": "true" if this_effect.matched else "false",
        "opposite_end_also_proposed": "true" if opposite_end else "false",
        "combined_trimming_would_occur": "true" if combined else "false",
        "combined_hypothetical_core_length": (
            "" if combined_core is None else str(combined_core)
        ),
        "combined_fraction_removed": _fmt_float(combined_fraction),
        "would_leave_core_below_20": "true" if below_20 else "false",
        "combined_would_exceed_40pct": "true" if exceeds_40 else "false",
        "same_side_conflict": "true" if same_side_conflict else "false",
        "hard_invalid": "true" if hard_invalid else "false",
        "hard_invalid_reason": hard_reason,
        "source_promoter_or_template_concern": (
            "true" if source_promoter else "false"
        ),
        "t_to_u_applied": "true" if t_to_u_applied else "false",
        "length_below_20": (
            "true" if core_len is not None and core_len < CORE_LENGTH_MIN else "false"
        ),
        "length_boundary": "true" if length_boundary else "false",
        "sequence_full": sequence_full,
        "proposed_sequence": this_motif,
    }


def build_rule_review_tables(
    *,
    proposals: Sequence[Mapping[str, str]],
    membership_rows: Sequence[Mapping[str, str]],
    canonical_by_id: Mapping[str, Mapping[str, str]],
    decision_by_id: Mapping[str, Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Build one rule row per inferred group-consensus proposal."""
    members_by_proposal: dict[str, list[str]] = defaultdict(list)
    for row in membership_rows:
        if row.get("proposal_source") != "group_consensus":
            continue
        proposal_id = row.get("proposal_id", "")
        record_id = row.get("record_id", "")
        if proposal_id and record_id:
            members_by_proposal[proposal_id].append(record_id)

    proposals_by_group_side: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(
        list
    )
    opposite = {"five_prime": "three_prime", "three_prime": "five_prime"}
    group_proposals: dict[str, list[dict[str, str]]] = defaultdict(list)
    ordered_proposals = sorted(
        (
            row
            for row in proposals
            if row.get("proposal_source") == "group_consensus"
        ),
        key=lambda row: row.get("proposal_id", ""),
    )
    for proposal in ordered_proposals:
        group_id = proposal.get("experiment_group_id", "")
        side = proposal.get("side", "")
        group_proposals[group_id].append(dict(proposal))
        proposals_by_group_side[(group_id, side)].append(dict(proposal))

    rule_rows: list[dict[str, str]] = []
    membership_out: list[dict[str, str]] = []
    exceptions: list[dict[str, str]] = []

    for proposal in ordered_proposals:
        proposal_id = proposal.get("proposal_id", "")
        group_id = proposal.get("experiment_group_id", "")
        side = proposal.get("side", "")
        motif = proposal.get("proposed_sequence", "") or ""
        opp_side = opposite.get(side, "")
        opp_props = [
            row
            for row in group_proposals.get(group_id, ())
            if row.get("side") == opp_side
        ]
        opp_motif = opp_props[0].get("proposed_sequence", "") if opp_props else ""
        same_side = proposals_by_group_side.get((group_id, side), [])
        same_side_conflict = len(same_side) > 1 and len(
            {_comparison_form(row.get("proposed_sequence", "")) for row in same_side}
        ) > 1

        member_ids = sorted(set(members_by_proposal.get(proposal_id, ())))
        hypo_below_20 = 0
        hypo_over_40 = 0
        not_exact = 0
        conflict_n = 0
        combined_n = 0
        hard_n = 0
        promoter_n = 0
        t_encoded_n = 0
        boundary_n = 0
        short_n = 0
        member_details: list[dict[str, str]] = []

        for record_id in member_ids:
            canonical = canonical_by_id.get(record_id, {})
            decision = decision_by_id.get(record_id, {})
            sequence_full = canonical.get("sequence_full", "")
            core_len = _parse_int(canonical.get("sequence_length_core", ""))
            source_promoter = _truthy(
                decision.get("source_promoter_or_template_concern", "")
            )
            t_to_u = _truthy(canonical.get("t_to_u_applied", ""))
            detail = simulate_member_detail(
                sequence_full=sequence_full,
                this_side=side,
                this_motif=motif,
                opposite_motif=opp_motif,
                opposite_side=opp_side,
                same_side_conflict=same_side_conflict,
                source_promoter=source_promoter,
                t_to_u_applied=t_to_u,
                core_len=core_len,
            )
            member_row = {
                "constant_rule_id": proposal_id,
                "proposal_id": proposal_id,
                "experiment_group_id": group_id,
                "record_id": record_id,
                "native_id": canonical.get("native_id") or decision.get("native_id", ""),
                "side": side,
                "sequence_length_core": canonical.get("sequence_length_core", ""),
                "sequence_core": canonical.get("sequence_core", ""),
                **detail,
            }
            member_details.append(member_row)
            membership_out.append(member_row)
            if detail["would_leave_core_below_20"] == "true":
                hypo_below_20 += 1
            if detail["combined_would_exceed_40pct"] == "true":
                hypo_over_40 += 1
            if detail["exact_terminal_match"] != "true":
                not_exact += 1
            if detail["same_side_conflict"] == "true":
                conflict_n += 1
            if detail["combined_trimming_would_occur"] == "true":
                combined_n += 1
            if detail["hard_invalid"] == "true":
                hard_n += 1
            if source_promoter:
                promoter_n += 1
            if t_to_u:
                t_encoded_n += 1
            if detail["length_boundary"] == "true":
                boundary_n += 1
            if detail["length_below_20"] == "true":
                short_n += 1

            exception_reasons: list[str] = []
            if detail["exact_terminal_match"] != "true":
                exception_reasons.append("non_terminal_match")
            if detail["same_side_conflict"] == "true":
                exception_reasons.append("same_side_motif_conflict")
            if detail["would_leave_core_below_20"] == "true":
                exception_reasons.append("combined_or_single_trim_below_20")
            if detail["hard_invalid"] == "true":
                hard_reason = detail["hard_invalid_reason"] or "hard_invalid"
                if hard_reason not in exception_reasons:
                    exception_reasons.append(hard_reason)
            if exception_reasons:
                exceptions.append(
                    {
                        "constant_rule_id": proposal_id,
                        "proposal_id": proposal_id,
                        "record_id": record_id,
                        "exception_reason": "|".join(exception_reasons),
                        "machine_recommendation": REC_NEEDS_SOURCE_REVIEW,
                        "machine_rationale": (
                            "Group-level approval would not be uniformly safe "
                            "for this record."
                        ),
                        "manual_decision": "",
                        "manual_trim_action": "",
                        "manual_trim_5p_nt": "",
                        "manual_trim_3p_nt": "",
                        "manual_notes": "",
                    }
                )

        majority_over_40 = (
            len(member_ids) > 0 and hypo_over_40 * 2 >= len(member_ids)
        )
        if majority_over_40:
            # Majority/uniform >40% is a group-level review trigger, not a
            # per-record exception and not an automatic rejection.
            pass
        elif hypo_over_40:
            for member_row in member_details:
                if member_row["combined_would_exceed_40pct"] != "true":
                    continue
                existing = next(
                    (
                        row
                        for row in exceptions
                        if row["record_id"] == member_row["record_id"]
                        and row["proposal_id"] == proposal_id
                    ),
                    None,
                )
                if existing is not None:
                    reasons = existing["exception_reason"].split("|")
                    if "unusual_over_40pct_trim" not in reasons:
                        reasons.append("unusual_over_40pct_trim")
                        existing["exception_reason"] = "|".join(reasons)
                    continue
                exceptions.append(
                    {
                        "constant_rule_id": proposal_id,
                        "proposal_id": proposal_id,
                        "record_id": member_row["record_id"],
                        "exception_reason": "unusual_over_40pct_trim",
                        "machine_recommendation": REC_NEEDS_SOURCE_REVIEW,
                        "machine_rationale": (
                            ">40% combined trim is a human-review trigger, not "
                            "an automatic biological prohibition."
                        ),
                        "manual_decision": "",
                        "manual_trim_action": "",
                        "manual_trim_5p_nt": "",
                        "manual_trim_3p_nt": "",
                        "manual_notes": "",
                    }
                )

        if hard_n == len(member_ids) and member_ids:
            machine_rec = REC_REJECT_TRIM
            rationale = (
                "Every matching member is hard-invalid under hypothetical "
                "application (empty core, non-terminal match, or impossible "
                "trim length)."
            )
        else:
            machine_rec = REC_NEEDS_SOURCE_REVIEW
            rationale = (
                "Medium-confidence group-consensus proposal remains unapplied. "
                "Shared known-motif detector found no independent confirmation. "
                ">40% hypothetical trim is a review trigger, not an automatic "
                "rejection."
            )

        matching_exact = _parse_int(proposal.get("records_matching_exactly", "")) or 0
        group_size = _parse_int(proposal.get("records_considered", "")) or 0
        rule_rows.append(
            {
                "constant_rule_id": proposal_id,
                "proposal_id": proposal_id,
                "experiment_group_id": group_id,
                "side": side,
                "inference_method": proposal.get("proposal_source", "group_consensus"),
                "confidence": proposal.get("confidence", ""),
                "support": proposal.get("support", ""),
                "motif_length": proposal.get("motif_length", ""),
                "group_size": str(group_size),
                "records_matching_exactly": str(matching_exact),
                "affected_s3_record_count": str(len(member_ids)),
                "source_promoter_overlap_count": str(promoter_n),
                "t_encoded_overlap_count": str(t_encoded_n),
                "length_boundary_overlap_count": str(boundary_n),
                "short_record_overlap_count": str(short_n),
                "n_not_exact_terminal_match": str(not_exact),
                "n_same_side_conflict": str(conflict_n),
                "n_combined_trim": str(combined_n),
                "n_hypothetical_core_below_20": str(hypo_below_20),
                "n_hypothetical_exceeds_40pct": str(hypo_over_40),
                "n_hard_invalid": str(hard_n),
                "machine_recommendation": machine_rec,
                "machine_rationale": rationale,
                "requires_specific_human_decision": "true",
                "recommended_trim_action": "",
                "manual_trim_action": "",
                "manual_trim_5p_nt": "",
                "manual_trim_3p_nt": "",
                "manual_notes": "",
            }
        )

    return rule_rows, membership_out, exceptions


def build_legacy_collapse_reconciliation(
    *,
    canonical_rows: Sequence[Mapping[str, str]],
    sidecar_rows: Sequence[Mapping[str, str]],
    processed_rows: Sequence[Mapping[str, str]],
    decision_by_id: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    """Reproduce the legacy 679→676 pair collapses without dropping records.

    Inspects the processed 676-row file only as a reconciliation target. Never
    uses it as an S1/S2/S3 routing source and never overwrites a 679-row
    identity.
    """
    sidecar_by_id = {row.get("record_id", ""): row for row in sidecar_rows}
    processed_by_id = {
        row.get("clean_record_id", ""): row for row in processed_rows if row.get("clean_record_id")
    }

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for canonical in canonical_rows:
        record_id = canonical.get("record_id", "")
        sidecar = sidecar_by_id.get(record_id, {})
        source_seq = sidecar.get("sequence") or canonical.get("sequence_raw") or ""
        target_raw = (
            sidecar.get("target") or canonical.get("target_name_raw") or ""
        )
        clean_seq, actions, t_to_u = clean_rna_sequence(source_seq)
        canonical_target, cmp_key, tgt_actions = canonicalise_target(target_raw)
        buckets[(clean_seq, cmp_key)].append(
            {
                "record_id": record_id,
                "review_unit_id": sidecar.get("review_unit_id")
                or canonical.get("native_id", ""),
                "clean_seq": clean_seq,
                "cmp_key": cmp_key,
                "canonical_target": canonical_target,
                "target_raw": target_raw,
                "sequence_full": canonical.get("sequence_full", ""),
                "actions": actions,
                "t_to_u": t_to_u,
                "tgt_actions": tgt_actions,
                "manual_sequence_corrected": sidecar.get("manual_sequence_corrected", ""),
                "manual_target_corrected": sidecar.get("manual_target_corrected", ""),
                "sequence_corrected_applied": sidecar.get(
                    "sequence_corrected_applied", ""
                ),
                "target_corrected_applied": sidecar.get("target_corrected_applied", ""),
            }
        )

    collapse_groups = [
        (key, rows) for key, rows in buckets.items() if len(rows) > 1
    ]
    collapse_groups.sort(key=lambda item: (item[0][1], item[1][0]["record_id"]))

    out: list[dict[str, str]] = []
    for index, ((clean_seq, cmp_key), rows) in enumerate(collapse_groups, start=1):
        ordered = sorted(rows, key=lambda row: row["record_id"])
        if len(ordered) != 2:
            raise EnaCheckpoint1ReviewError(
                "ENA legacy collapse group is not a pair: "
                f"n={len(ordered)} key={cmp_key!r}"
            )
        left, right = ordered
        clean_id = make_clean_record_id(clean_seq, cmp_key)
        processed = processed_by_id.get(clean_id, {})
        if processed and processed.get("internal_duplicate_count") not in {"", "2"}:
            # Still record the pair; do not drop source identities.
            pass
        alias_actions = sorted(
            {
                action
                for row in (left, right)
                for action in row["tgt_actions"]
                if str(action).startswith("alias:")
            }
        )
        decision_left = decision_by_id.get(left["record_id"], {})
        decision_right = decision_by_id.get(right["record_id"], {})
        promoter = _truthy(
            decision_left.get("source_promoter_or_template_concern", "")
        ) or _truthy(decision_right.get("source_promoter_or_template_concern", ""))
        group_proposal = _truthy(
            decision_left.get("group_covered_by_rule_review", "")
        ) or _truthy(decision_right.get("group_covered_by_rule_review", ""))
        prior_correction = any(
            _truthy(str(row.get(field, "")))
            or _blank(str(row.get(text_field, ""))) not in {"", "0"}
            for row in (left, right)
            for field, text_field in (
                ("sequence_corrected_applied", "manual_sequence_corrected"),
                ("target_corrected_applied", "manual_target_corrected"),
            )
        )
        out.append(
            {
                "reconciliation_id": f"ena_collapse_{index:02d}",
                "record_id_a": left["record_id"],
                "record_id_b": right["record_id"],
                "review_unit_id_a": left["review_unit_id"],
                "review_unit_id_b": right["review_unit_id"],
                "clean_record_id": processed.get("clean_record_id") or clean_id,
                "legacy_t_to_u": (
                    "true" if left["t_to_u"] or right["t_to_u"] else "false"
                ),
                "legacy_target_alias": "true" if alias_actions else "false",
                "legacy_exact_sequence_target_consolidation": "true",
                "unified_s2_sequence_full_identical": (
                    "true"
                    if left["sequence_full"] == right["sequence_full"]
                    and left["sequence_full"] != ""
                    else "false"
                ),
                "raw_target_name_identical": (
                    "true" if left["target_raw"] == right["target_raw"] else "false"
                ),
                "prior_manual_sequence_or_target_correction": (
                    "true" if prior_correction else "false"
                ),
                "source_promoter_or_template_concern": (
                    "true" if promoter else "false"
                ),
                "group_consensus_proposal": "true" if group_proposal else "false",
                "machine_recommendation": REC_RETAIN_BOTH,
                "machine_rationale": RECONCILIATION_RATIONALE,
                "manual_decision": "",
                "manual_notes": "",
            }
        )
    return out


def build_bulk_confirmation_row(
    queue_rows: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    eligible = [
        row["record_id"]
        for row in queue_rows
        if is_audit_only_row(row)
    ]
    return {
        "confirmation_id": BULK_CONFIRMATION_ID,
        "scope": BULK_SCOPE,
        "eligible_record_count": str(len(eligible)),
        "eligible_record_ids": "|".join(eligible),
        "confirm": "",
        "reviewer_initials": "",
        "manual_notes": "",
    }


def validate_ena_review_package(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    rule_rows: Sequence[Mapping[str, str]],
    exception_rows: Sequence[Mapping[str, str]] = (),
    reconciliation_rows: Sequence[Mapping[str, str]] = (),
    bulk_confirmation: Mapping[str, str] | None = None,
) -> ValidationReport:
    """Fail-closed validation. Blank human fields are SUCCESS for this milestone."""
    report = ValidationReport(total_review_records=len(queue_rows))
    bulk_confirmed = (
        bulk_confirmation is not None
        and _blank(bulk_confirmation.get("confirm")).lower() == "true"
    )

    for rule in rule_rows:
        action = _blank(rule.get("manual_trim_action"))
        if action not in ALLOWED_TRIM_ACTIONS:
            report.blocking_issues.append(
                f"Invalid rule trim action for {rule.get('constant_rule_id')}"
            )
        if action == "":
            report.unresolved_constant_rules += 1
            report.blocking_issues.append(
                f"Unresolved constant rule {rule.get('constant_rule_id')}"
            )
        rec = _blank(rule.get("machine_recommendation"))
        if rec and action == rec:
            report.blocking_issues.append(
                "Machine recommendation must not count as a human decision "
                f"for {rule.get('constant_rule_id')}"
            )

    for row in queue_rows:
        record_id = row.get("record_id", "")
        decision = _blank(row.get("manual_decision"))
        if decision not in ALLOWED_MANUAL_DECISIONS:
            report.blocking_issues.append(f"Invalid manual_decision for {record_id}")
            continue
        if decision == "":
            report.unresolved_manual_decisions += 1
            report.blocking_issues.append(f"Unresolved manual_decision for {record_id}")
        rec = _blank(row.get("review_recommendation"))
        if rec and decision == rec:
            report.blocking_issues.append(
                "Machine recommendation must not count as a human decision "
                f"for {record_id}"
            )
        for name in MANUAL_FIELDS:
            if name == "manual_decision":
                continue
            if row.get(name):
                # Populated human fields are allowed after review; blank
                # package must not have them.
                pass
        trim_action = _blank(row.get("manual_trim_action"))
        if trim_action not in ALLOWED_TRIM_ACTIONS:
            report.blocking_issues.append(f"Invalid trim action for {record_id}")
        if is_audit_only_row(row) and decision == "":
            report.audit_only_unconfirmed += 1
            if not bulk_confirmed:
                report.blocking_issues.append(
                    f"Audit-only row unconfirmed for {record_id}"
                )

    for row in exception_rows:
        if _blank(row.get("manual_decision")) == "" and _blank(
            row.get("manual_trim_action")
        ) == "":
            report.unresolved_exceptions += 1
            report.blocking_issues.append(
                f"Unresolved record-level exception for {row.get('record_id')}"
            )

    for row in reconciliation_rows:
        decision = _blank(row.get("manual_decision"))
        if decision not in ALLOWED_RECONCILIATION_DECISIONS:
            report.blocking_issues.append(
                f"Invalid reconciliation decision for {row.get('reconciliation_id')}"
            )
        if decision == "":
            report.unresolved_reconciliation_groups += 1
            report.blocking_issues.append(
                f"Unresolved reconciliation group {row.get('reconciliation_id')}"
            )
        rec = _blank(row.get("machine_recommendation"))
        if rec and decision == rec:
            report.blocking_issues.append(
                "Machine recommendation must not count as a human decision "
                f"for {row.get('reconciliation_id')}"
            )

    if bulk_confirmed:
        eligible = {
            part
            for part in _blank(
                (bulk_confirmation or {}).get("eligible_record_ids", "")
            ).split("|")
            if part
        }
        report.eligible_bulk_audit_ids = tuple(sorted(eligible))
        for row in queue_rows:
            if row.get("record_id") in eligible and not is_audit_only_row(row):
                report.blocking_issues.append(
                    f"Bulk confirmation includes non-audit row {row.get('record_id')}"
                )

    if (
        not report.blocking_issues
        and report.unresolved_manual_decisions == 0
        and report.unresolved_constant_rules == 0
        and report.unresolved_reconciliation_groups == 0
        and report.unresolved_exceptions == 0
    ):
        report.ready_for_application = report.total_review_records
    else:
        report.ready_for_application = 0
    return report


def format_validation_markdown(report: ValidationReport) -> str:
    lines = [
        "# ENA CHECKPOINT-1 review validation",
        "",
        f"- total review records: `{report.total_review_records}`",
        f"- unresolved manual decisions: `{report.unresolved_manual_decisions}`",
        f"- unresolved constant rules: `{report.unresolved_constant_rules}`",
        f"- unresolved exceptions: `{report.unresolved_exceptions}`",
        f"- unresolved reconciliation groups: `{report.unresolved_reconciliation_groups}`",
        f"- audit-only unconfirmed: `{report.audit_only_unconfirmed}`",
        f"- ready for application: `{report.ready_for_application}`",
        f"- blocking issues: `{len(report.blocking_issues)}`",
        "",
        "Human decision fields are blank. Machine recommendations are not",
        "human decisions. Apply would fail closed. This is SUCCESS for",
        "CHECKPOINT-1 preparation.",
        "",
        "CHECKPOINT-1 is not closed. No record is authorised for S4.",
    ]
    return "\n".join(lines) + "\n"


def build_review_readme() -> str:
    return (
        "# ENA CHECKPOINT-1 manual review\n\n"
        "This package is a structured review queue. Machine "
        "`review_recommendation` / `machine_recommendation` fields are not "
        "human decisions.\n\n"
        "Review components:\n\n"
        "1. Record-level queue (`ena_checkpoint1_manual_review.csv`) — one "
        "row per record that needs an individual judgement, transcription/"
        "reconciliation audit, length-boundary eyeball, or random kept audit. "
        "Records whose only trim issue is covered by a group-consensus rule "
        "are not duplicated here.\n"
        "2. Constant-region rule table — one row per inferred proposal "
        "(expected 5). Approve / reject / override / defer at rule level.\n"
        "3. Record-level exceptions — only where group approval would not be "
        "uniformly safe.\n"
        "4. 679-versus-676 reconciliation — one row per legacy collapse pair "
        "(expected 3). Do not collapse pairs in this source lane.\n"
        "5. Optional bulk confirmation for audit-only rows.\n\n"
        "Do not apply trims from this package until human fields are complete "
        "and validation is ready_for_application.\n"
    )


def rule_summary_markdown(rule_rows: Sequence[Mapping[str, str]]) -> str:
    lines = [
        "## Constant-region group/rule review",
        "",
        f"- inferred proposals: `{len(rule_rows)}`",
    ]
    for row in rule_rows:
        lines.extend(
            [
                "",
                f"### `{row.get('constant_rule_id', '')}`",
                f"- side: `{row.get('side', '')}`",
                f"- group size: `{row.get('group_size', '')}`",
                f"- support: `{row.get('support', '')}`",
                f"- motif length: `{row.get('motif_length', '')}`",
                f"- affected S3 records: `{row.get('affected_s3_record_count', '')}`",
                f"- hypothetical <20: `{row.get('n_hypothetical_core_below_20', '')}`",
                f"- hypothetical >40%: `{row.get('n_hypothetical_exceeds_40pct', '')}`",
                f"- same-side conflict: `{row.get('n_same_side_conflict', '')}`",
                f"- source-promoter overlap: `{row.get('source_promoter_overlap_count', '')}`",
                f"- machine recommendation: `{row.get('machine_recommendation', '')}`",
            ]
        )
    return "\n".join(lines)

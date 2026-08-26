"""AptaDB CHECKPOINT-1 structured review: schema, recommendations, apply path.

Prepares richer human-review fields and future application semantics. Does not
fill ``manual_*`` decisions, apply trims, or start S4. Recommendations live in
separate fields and must never masquerade as human decisions.
"""

from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from common.corpus_schema import CHEMISTRY_VOCABULARY, S3_FORBIDDEN_FIELDS
from common.eligibility import EligibilityPolicy, load_eligibility_policy
from common.sequence_normalisation import (
    TRIM_CONFIDENCE_HIGH,
    TRIM_CONFIDENCE_MEDIUM,
    TRIM_CONFIDENCE_NA,
    normalise_sequence,
)

ALLOWED_MANUAL_DECISIONS: Final[frozenset[str]] = frozenset({"", "keep", "drop", "edit"})
ALLOWED_MOLECULE_OVERRIDES: Final[frozenset[str]] = frozenset({"", "RNA", "ssDNA"})
ALLOWED_TRIM_ACTIONS: Final[frozenset[str]] = frozenset(
    {"", "approve", "override", "reject", "defer"}
)
ALLOWED_GROUP_OVERRIDE: Final[frozenset[str]] = frozenset({"", "true", "false"})
AUDIT_ONLY_REASONS: Final[frozenset[str]] = frozenset(
    {"length_boundary", "random_kept_audit"}
)
MAX_COMBINED_TRIM_FRACTION: Final[float] = 0.40
CORE_LENGTH_MIN: Final[int] = 20
DEFAULT_RECOMMENDATIONS_REL: Final[str] = (
    "config/checkpoint_reviews/aptadb_checkpoint1_recommendations.json"
)
DEFAULT_POLICY_REL: Final[str] = "config/source_eligibility/aptadb.json"

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

RECORD_REVIEW_EXTRA_COLUMNS: Final[tuple[str, ...]] = MANUAL_FIELDS + RECOMMENDATION_FIELDS

GROUP_REVIEW_COLUMNS: Final[tuple[str, ...]] = (
    "constant_group_id",
    "group_label",
    "proposal_ids",
    "proposal_source",
    "proposal_type",
    "target_name_raw",
    "pubmed_id",
    "publication",
    "n_records",
    "n_review_records",
    "associated_record_ids",
    "machine_trim_5p_nt",
    "machine_trim_3p_nt",
    "support_5p",
    "support_3p",
    "records_matching_exactly_5p",
    "records_matching_exactly_3p",
    "core_length_min",
    "core_length_median",
    "core_length_max",
    "hypothetical_core_min",
    "hypothetical_core_median",
    "hypothetical_core_max",
    "known_motif_vs_group_consensus",
    "proposed_5p_sequence",
    "proposed_3p_sequence",
    "review_recommendation",
    "review_rationale",
    "requires_specific_human_decision",
    "recommended_trim_action",
    "recommended_trim_5p_nt",
    "recommended_trim_3p_nt",
    "recommended_record_exceptions",
    "manual_trim_action",
    "manual_trim_5p_nt",
    "manual_trim_3p_nt",
    "manual_notes",
)

GROUP_SEQUENCE_COLUMNS: Final[frozenset[str]] = frozenset(
    {"proposed_5p_sequence", "proposed_3p_sequence"}
)

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

RNA_CHEMISTRIES: Final[frozenset[str]] = frozenset(
    {"RNA", "2F-RNA", "2NH2-RNA", "2OMe-RNA"}
)
DNA_CHEMISTRIES: Final[frozenset[str]] = frozenset({"DNA"})


class AptaDBCheckpoint1ReviewError(ValueError):
    """Invalid AptaDB CHECKPOINT-1 review schema, validation, or apply input."""


@dataclass
class ValidationReport:
    """Fail-closed CHECKPOINT-1 review validation (aggregates only)."""

    total_review_records: int = 0
    unresolved_manual_decisions: int = 0
    unresolved_constant_groups: int = 0
    contradictory_records: int = 0
    invalid_trim_lengths: int = 0
    unresolved_exceptions: int = 0
    edit_without_change: int = 0
    drop_records: int = 0
    deferred_records: int = 0
    deferred_groups: int = 0
    audit_only_unconfirmed: int = 0
    ready_for_application: int = 0
    blocking_issues: list[str] = field(default_factory=list)
    eligible_bulk_audit_ids: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.blocking_issues and self.ready_for_application == (
            self.total_review_records
        )


@dataclass(frozen=True)
class EffectiveTrim:
    """Resolved numeric trim for one record."""

    action: str
    five_nt: int
    three_nt: int
    source: str
    group_id: str


@dataclass
class AppliedRecordResult:
    """Result of applying one reviewed AptaDB record (no S4 fields)."""

    record_id: str
    sequence_raw: str
    sequence_full: str
    sequence_core: str
    sequence_length_full: int
    sequence_length_core: int
    molecule_type: str
    chemistry: str
    alphabet_as_reported: str
    t_to_u_applied: bool
    trim_status: str
    trim_confidence: str
    primary_route_before: str
    primary_route_after: str
    notes: str
    canonical: dict[str, str]


def _blank(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _truthy(value: str) -> bool:
    return _blank(value).lower() == "true"


def parse_review_reasons(value: str) -> frozenset[str]:
    return frozenset(part for part in _blank(value).split("|") if part)


def is_audit_only_row(row: Mapping[str, str]) -> bool:
    reasons = parse_review_reasons(row.get("checkpoint_review_reasons", ""))
    return bool(reasons) and reasons <= AUDIT_ONLY_REASONS


def load_review_recommendations(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("source_key") != "aptadb":
        raise AptaDBCheckpoint1ReviewError(
            "recommendation file source_key must be aptadb"
        )
    return payload


def apply_sequence_correction_op(sequence: str, op: str) -> str:
    """Deterministic sequence-correction operators (no silent gap stripping)."""
    if not op:
        return sequence
    if op == "remove_internal_hyphens":
        return sequence.replace("-", "")
    if op == "remove_terminal_period":
        return sequence[:-1] if sequence.endswith(".") else sequence
    if op == "remove_trailing_nonbiological_3":
        return sequence[:-1] if sequence.endswith("3") else sequence
    raise AptaDBCheckpoint1ReviewError(f"Unknown sequence_correction_op {op!r}")


def parse_trim_nt(value: str, *, field_name: str, record_id: str) -> int | None:
    text = _blank(value)
    if text == "":
        return None
    if not text.isdigit():
        raise AptaDBCheckpoint1ReviewError(
            f"{field_name} must be a non-negative integer or blank for "
            f"{record_id!r}; got {text!r}"
        )
    return int(text)


def validate_trim_lengths(
    *,
    sequence_length: int,
    five_nt: int,
    three_nt: int,
    record_id: str,
    min_core: int = CORE_LENGTH_MIN,
    max_fraction: float = MAX_COMBINED_TRIM_FRACTION,
) -> None:
    if five_nt < 0 or three_nt < 0:
        raise AptaDBCheckpoint1ReviewError(
            f"Trim lengths must be >=0 for {record_id!r}"
        )
    if five_nt > sequence_length or three_nt > sequence_length:
        raise AptaDBCheckpoint1ReviewError(
            f"Trim exceeds sequence length for {record_id!r}"
        )
    combined = five_nt + three_nt
    if combined >= sequence_length:
        raise AptaDBCheckpoint1ReviewError(
            f"Trim would leave an empty core for {record_id!r}"
        )
    core = sequence_length - combined
    if core < min_core:
        raise AptaDBCheckpoint1ReviewError(
            f"Trim would leave core below {min_core} nt for {record_id!r}"
        )
    if sequence_length and (combined / sequence_length) > max_fraction:
        raise AptaDBCheckpoint1ReviewError(
            f"Combined trim exceeds {max_fraction:.0%} guard rail for {record_id!r}"
        )


def apply_numeric_terminal_trim(
    sequence_full: str,
    *,
    five_nt: int,
    three_nt: int,
    record_id: str,
    min_core: int = CORE_LENGTH_MIN,
    max_fraction: float = MAX_COMBINED_TRIM_FRACTION,
) -> str:
    """Trim reviewed ``sequence_full`` by nucleotide counts. Never trim raw."""
    validate_trim_lengths(
        sequence_length=len(sequence_full),
        five_nt=five_nt,
        three_nt=three_nt,
        record_id=record_id,
        min_core=min_core,
        max_fraction=max_fraction,
    )
    end = len(sequence_full) - three_nt if three_nt else len(sequence_full)
    return sequence_full[five_nt:end]


def default_chemistry_for_molecule(molecule_type: str) -> str:
    if molecule_type == "RNA":
        return "RNA"
    if molecule_type in {"ssDNA", "DNA"}:
        return "DNA"
    return ""


def _molecule_chemistry_consistent(molecule: str, chemistry: str) -> bool:
    if not molecule or not chemistry:
        return True
    if molecule == "RNA" and chemistry in DNA_CHEMISTRIES:
        return False
    if molecule == "ssDNA" and chemistry in RNA_CHEMISTRIES:
        return False
    if chemistry and chemistry not in CHEMISTRY_VOCABULARY:
        return False
    return True


def empty_manual_fields() -> dict[str, str]:
    return {name: "" for name in MANUAL_FIELDS}


def empty_recommendation_fields() -> dict[str, str]:
    return {name: "" for name in RECOMMENDATION_FIELDS}


def populate_record_recommendations(
    row: dict[str, str],
    *,
    recommendations: Mapping[str, Any],
) -> dict[str, str]:
    """Fill recommendation fields only. Never writes ``manual_*`` values."""
    out = dict(row)
    for name in RECOMMENDATION_FIELDS:
        out.setdefault(name, "")
    for name in MANUAL_FIELDS:
        out[name] = ""

    record_id = out.get("record_id", "")
    record_cfg = (recommendations.get("records") or {}).get(record_id, {})
    group_id = out.get("constant_group_id", "")
    group_cfg = (recommendations.get("groups") or {}).get(group_id, {})
    audit_cfg = recommendations.get("audit_only") or {}
    audit_only = is_audit_only_row(out)

    cfg: dict[str, Any] = {}
    if record_cfg:
        cfg.update(record_cfg)
    elif audit_only:
        cfg.update(audit_cfg)
    elif group_cfg and "constant_region_proposal" in parse_review_reasons(
        out.get("checkpoint_review_reasons", "")
    ):
        cfg = {
            "review_recommendation": group_cfg.get("review_recommendation", ""),
            "rationale": (
                "Follow the group-level constant-region recommendation unless a "
                "record-level exception is marked."
            ),
            "requires_specific_human_decision": group_cfg.get(
                "requires_specific_human_decision", True
            ),
            "recommended_trim_action": group_cfg.get("recommended_trim_action", ""),
            "recommended_trim_5p_nt": group_cfg.get("recommended_trim_5p_nt", ""),
            "recommended_trim_3p_nt": group_cfg.get("recommended_trim_3p_nt", ""),
        }

    if cfg:
        out["review_recommendation"] = _blank(cfg.get("review_recommendation"))
        out["review_rationale"] = _blank(cfg.get("rationale"))
        out["requires_specific_human_decision"] = (
            "true" if cfg.get("requires_specific_human_decision") else "false"
        )
        out["recommended_manual_decision"] = _blank(
            cfg.get("recommended_manual_decision")
        )
        op = _blank(cfg.get("sequence_correction_op"))
        out["recommended_sequence_correction_op"] = op
        if op:
            out["recommended_sequence_corrected"] = apply_sequence_correction_op(
                out.get("sequence_raw", ""), op
            )
        out["recommended_molecule_type_override"] = _blank(
            cfg.get("recommended_molecule_type_override")
        )
        out["recommended_chemistry_override"] = _blank(
            cfg.get("recommended_chemistry_override")
        )
        out["recommended_trim_action"] = _blank(cfg.get("recommended_trim_action"))
        five = cfg.get("recommended_trim_5p_nt", "")
        three = cfg.get("recommended_trim_3p_nt", "")
        out["recommended_trim_5p_nt"] = "" if five in (None, "") else str(five)
        out["recommended_trim_3p_nt"] = "" if three in (None, "") else str(three)
        override = cfg.get("recommended_trim_group_override")
        if override is True:
            out["recommended_trim_group_override"] = "true"
        elif override is False:
            out["recommended_trim_group_override"] = "false"
        else:
            out["recommended_trim_group_override"] = _blank(override)

    out["audit_only_row"] = "true" if audit_only else "false"
    out["bulk_audit_eligible"] = "true" if audit_only else "false"
    if audit_only and not out["review_recommendation"]:
        out["review_recommendation"] = "keep_current_route"
        out["review_rationale"] = _blank(audit_cfg.get("rationale"))
        out["recommended_manual_decision"] = "keep"
        out["requires_specific_human_decision"] = "false"

    for name in MANUAL_FIELDS:
        if out.get(name):
            raise AptaDBCheckpoint1ReviewError(
                f"Recommendations must not populate {name} for {record_id!r}"
            )
    return out


def machine_trim_lengths(
    proposals: Sequence[Mapping[str, str]],
) -> tuple[str, str, str, str]:
    five = ""
    three = ""
    five_seq = ""
    three_seq = ""
    for row in proposals:
        side = row.get("side", "")
        length = _blank(row.get("motif_length"))
        seq = row.get("proposed_sequence", "") or ""
        if side == "five_prime":
            five = length
            five_seq = seq
        elif side == "three_prime":
            three = length
            three_seq = seq
    return five, three, five_seq, three_seq


def build_group_review_rows(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    proposals: Sequence[Mapping[str, str]],
    canonical_by_id: Mapping[str, Mapping[str, str]],
    recommendations: Mapping[str, Any],
) -> list[dict[str, str]]:
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in queue_rows:
        group_id = _blank(row.get("constant_group_id"))
        if not group_id:
            continue
        grouped.setdefault(group_id, []).append(row)

    proposals_by_group: dict[str, list[Mapping[str, str]]] = {}
    for proposal in proposals:
        group_id = _blank(proposal.get("experiment_group_id"))
        if group_id:
            proposals_by_group.setdefault(group_id, []).append(proposal)

    group_ids = sorted(set(grouped) | set(proposals_by_group))
    rows: list[dict[str, str]] = []
    group_cfg_all = recommendations.get("groups") or {}
    for group_id in group_ids:
        members = grouped.get(group_id, [])
        props = proposals_by_group.get(group_id, [])
        if not members and not props:
            continue
        source = ""
        if props:
            sources = sorted({p.get("proposal_source", "") for p in props if p.get("proposal_source")})
            source = sources[0] if len(sources) == 1 else "|".join(sources)
        elif members:
            source = members[0].get("constant_proposal_sources", "")
        five, three, five_seq, three_seq = machine_trim_lengths(props)
        if not five and members:
            # Fall back to concatenated decision metadata if needed.
            sides = (members[0].get("constant_proposal_sides") or "").split("|")
            lengths = (members[0].get("constant_proposed_trim_length") or "").split("|")
            side_to_len = {
                side: length
                for side, length in zip(sides, lengths)
                if side and length
            }
            five = side_to_len.get("five_prime", five)
            three = side_to_len.get("three_prime", three)
        supports = {p.get("side"): p.get("support", "") for p in props}
        matching = {
            p.get("side"): p.get("records_matching_exactly", "") for p in props
        }
        n_from_prop = ""
        if props:
            n_from_prop = props[0].get("records_considered", "")
        cores: list[int] = []
        hypothetical: list[int] = []
        pubmed_ids: set[str] = set()
        publications: set[str] = set()
        targets: set[str] = set()
        record_ids: list[str] = []
        seen_ids: set[str] = set()
        for member in members:
            record_id = member["record_id"]
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            record_ids.append(record_id)
            targets.add(member.get("target_name_raw", ""))
            publications.add(member.get("publication", ""))
            canonical = canonical_by_id.get(record_id, {})
            pubmed_ids.add(canonical.get("pubmed_id", "") or "")
            try:
                core_len = int(member.get("sequence_length_core") or "0")
            except ValueError:
                core_len = 0
            if core_len:
                cores.append(core_len)
            five_n = int(five) if five.isdigit() else 0
            three_n = int(three) if three.isdigit() else 0
            hypo = core_len - five_n - three_n
            if core_len:
                hypothetical.append(hypo)
        record_ids.sort()
        cfg = group_cfg_all.get(group_id, {})
        proposal_type = (
            "known_motif" if source == "known_motif" else "group_consensus"
        )
        row = {column: "" for column in GROUP_REVIEW_COLUMNS}
        row.update(
            {
                "constant_group_id": group_id,
                "group_label": _blank(cfg.get("label")),
                "proposal_ids": "|".join(
                    sorted(p.get("proposal_id", "") for p in props if p.get("proposal_id"))
                ),
                "proposal_source": source,
                "proposal_type": proposal_type,
                "target_name_raw": sorted(t for t in targets if t)[0] if any(targets) else "",
                "pubmed_id": sorted(p for p in pubmed_ids if p)[0] if any(pubmed_ids) else "",
                "publication": sorted(p for p in publications if p)[0]
                if any(publications)
                else "",
                "n_records": n_from_prop or str(len(record_ids)),
                "n_review_records": str(len(record_ids)),
                "associated_record_ids": "|".join(record_ids),
                "machine_trim_5p_nt": five,
                "machine_trim_3p_nt": three,
                "support_5p": _blank(supports.get("five_prime")),
                "support_3p": _blank(supports.get("three_prime")),
                "records_matching_exactly_5p": _blank(matching.get("five_prime")),
                "records_matching_exactly_3p": _blank(matching.get("three_prime")),
                "core_length_min": str(min(cores)) if cores else "",
                "core_length_median": (
                    str(int(statistics.median(cores))) if cores else ""
                ),
                "core_length_max": str(max(cores)) if cores else "",
                "hypothetical_core_min": str(min(hypothetical)) if hypothetical else "",
                "hypothetical_core_median": (
                    str(int(statistics.median(hypothetical))) if hypothetical else ""
                ),
                "hypothetical_core_max": str(max(hypothetical)) if hypothetical else "",
                "known_motif_vs_group_consensus": proposal_type,
                "proposed_5p_sequence": five_seq,
                "proposed_3p_sequence": three_seq,
                "review_recommendation": _blank(cfg.get("review_recommendation")),
                "review_rationale": _blank(cfg.get("rationale")),
                "requires_specific_human_decision": (
                    "true"
                    if cfg.get("requires_specific_human_decision", True)
                    else "false"
                ),
                "recommended_trim_action": _blank(cfg.get("recommended_trim_action")),
                "recommended_trim_5p_nt": (
                    ""
                    if cfg.get("recommended_trim_5p_nt") in (None, "")
                    else str(cfg.get("recommended_trim_5p_nt"))
                ),
                "recommended_trim_3p_nt": (
                    ""
                    if cfg.get("recommended_trim_3p_nt") in (None, "")
                    else str(cfg.get("recommended_trim_3p_nt"))
                ),
                "recommended_record_exceptions": _blank(
                    cfg.get("recommended_record_exceptions")
                ),
                "manual_trim_action": "",
                "manual_trim_5p_nt": "",
                "manual_trim_3p_nt": "",
                "manual_notes": "",
            }
        )
        rows.append(row)
    return rows


def build_bulk_confirmation_row(
    queue_rows: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    eligible = sorted(
        row["record_id"] for row in queue_rows if is_audit_only_row(row)
    )
    return {
        "confirmation_id": BULK_CONFIRMATION_ID,
        "scope": BULK_SCOPE,
        "eligible_record_count": str(len(eligible)),
        "eligible_record_ids": "|".join(eligible),
        "confirm": "",
        "reviewer_initials": "",
        "manual_notes": "",
    }


def materialize_bulk_audit_decisions(
    queue_rows: Sequence[Mapping[str, str]],
    confirmation: Mapping[str, str],
) -> list[dict[str, str]]:
    """Apply bulk keep only after explicit human confirm=true. Opt-in helper."""
    if _blank(confirmation.get("confirm")).lower() != "true":
        raise AptaDBCheckpoint1ReviewError(
            "Bulk audit materialisation requires explicit confirm=true"
        )
    if confirmation.get("confirmation_id") != BULK_CONFIRMATION_ID:
        raise AptaDBCheckpoint1ReviewError("Unexpected bulk confirmation_id")
    allowed = set(
        part
        for part in _blank(confirmation.get("eligible_record_ids")).split("|")
        if part
    )
    updated: list[dict[str, str]] = []
    for row in queue_rows:
        out = dict(row)
        record_id = out["record_id"]
        if record_id not in allowed:
            updated.append(out)
            continue
        if not is_audit_only_row(out):
            raise AptaDBCheckpoint1ReviewError(
                f"Bulk audit ID is not audit-only: {record_id!r}"
            )
        if any(out.get(name) for name in MANUAL_FIELDS if name != "manual_notes"):
            raise AptaDBCheckpoint1ReviewError(
                f"Bulk audit cannot overwrite an existing decision for {record_id!r}"
            )
        out["manual_decision"] = "keep"
        updated.append(out)
    return updated


def _int_or_none(value: str, *, field_name: str, record_id: str) -> int | None:
    try:
        return parse_trim_nt(value, field_name=field_name, record_id=record_id)
    except AptaDBCheckpoint1ReviewError:
        raise


def resolve_effective_trim(
    record: Mapping[str, str],
    group: Mapping[str, str] | None,
    *,
    machine_five: int,
    machine_three: int,
) -> EffectiveTrim | None:
    """Record-level trim fields take precedence over the group decision."""
    record_id = record.get("record_id", "")
    record_action = _blank(record.get("manual_trim_action"))
    group_action = _blank(group.get("manual_trim_action") if group else "")
    action = record_action or group_action
    if action in {"", "reject", "defer"}:
        return None
    if action not in {"approve", "override"}:
        raise AptaDBCheckpoint1ReviewError(
            f"Unsupported trim action {action!r} for {record_id!r}"
        )
    five = machine_five
    three = machine_three
    if action == "override" or record_action:
        rec_five = _int_or_none(
            record.get("manual_trim_5p_nt", ""),
            field_name="manual_trim_5p_nt",
            record_id=record_id,
        )
        rec_three = _int_or_none(
            record.get("manual_trim_3p_nt", ""),
            field_name="manual_trim_3p_nt",
            record_id=record_id,
        )
        grp_five = _int_or_none(
            group.get("manual_trim_5p_nt", "") if group else "",
            field_name="manual_trim_5p_nt",
            record_id=record_id,
        )
        grp_three = _int_or_none(
            group.get("manual_trim_3p_nt", "") if group else "",
            field_name="manual_trim_3p_nt",
            record_id=record_id,
        )
        if rec_five is not None:
            five = rec_five
        elif grp_five is not None and not record_action:
            five = grp_five
        elif grp_five is not None and record_action == "override" and rec_five is None:
            five = grp_five
        if rec_three is not None:
            three = rec_three
        elif grp_three is not None and not record_action:
            three = grp_three
        elif grp_three is not None and record_action == "override" and rec_three is None:
            three = grp_three
    source = "record" if record_action else "group"
    return EffectiveTrim(
        action=action,
        five_nt=five,
        three_nt=three,
        source=source,
        group_id=_blank(record.get("constant_group_id")),
    )


def validate_review_package(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    bulk_confirmation: Mapping[str, str] | None = None,
    allow_deferred: bool = False,
) -> ValidationReport:
    report = ValidationReport(total_review_records=len(queue_rows))
    groups_by_id = {row["constant_group_id"]: row for row in group_rows}
    bulk_confirmed = (
        bulk_confirmation is not None
        and _blank(bulk_confirmation.get("confirm")).lower() == "true"
    )

    for group in group_rows:
        action = _blank(group.get("manual_trim_action"))
        if action not in ALLOWED_TRIM_ACTIONS:
            report.blocking_issues.append(
                f"Invalid group trim action for {group['constant_group_id']}"
            )
        if action == "":
            report.unresolved_constant_groups += 1
            report.blocking_issues.append(
                f"Unresolved constant group {group['constant_group_id']}"
            )
        elif action == "defer":
            report.deferred_groups += 1
            if not allow_deferred:
                report.blocking_issues.append(
                    f"Deferred group {group['constant_group_id']} blocks closure"
                )
        if action == "override":
            if not group.get("manual_trim_5p_nt") and not group.get("manual_trim_3p_nt"):
                report.invalid_trim_lengths += 1
                report.blocking_issues.append(
                    f"Group override missing numeric trim for {group['constant_group_id']}"
                )

    for row in queue_rows:
        record_id = row["record_id"]
        decision = _blank(row.get("manual_decision"))
        if decision not in ALLOWED_MANUAL_DECISIONS:
            report.blocking_issues.append(f"Invalid manual_decision for {record_id}")
            continue
        if decision == "":
            report.unresolved_manual_decisions += 1
            report.blocking_issues.append(f"Unresolved manual_decision for {record_id}")
        if decision == "drop":
            report.drop_records += 1
            if any(
                _blank(row.get(name))
                for name in (
                    "manual_sequence_corrected",
                    "manual_molecule_type_override",
                    "manual_chemistry_override",
                    "manual_trim_action",
                )
            ):
                report.contradictory_records += 1
                report.blocking_issues.append(
                    f"drop combined with edit/override fields for {record_id}"
                )
        molecule = _blank(row.get("manual_molecule_type_override"))
        chemistry = _blank(row.get("manual_chemistry_override"))
        if molecule not in ALLOWED_MOLECULE_OVERRIDES:
            report.contradictory_records += 1
            report.blocking_issues.append(
                f"Invalid molecule override for {record_id}"
            )
        if chemistry and chemistry not in CHEMISTRY_VOCABULARY:
            report.contradictory_records += 1
            report.blocking_issues.append(
                f"Invalid chemistry override for {record_id}"
            )
        if not _molecule_chemistry_consistent(molecule, chemistry):
            report.contradictory_records += 1
            report.blocking_issues.append(
                f"Molecule/chemistry override conflict for {record_id}"
            )
        trim_action = _blank(row.get("manual_trim_action"))
        if trim_action not in ALLOWED_TRIM_ACTIONS:
            report.contradictory_records += 1
            report.blocking_issues.append(f"Invalid trim action for {record_id}")
        if _blank(row.get("manual_trim_group_override")) not in ALLOWED_GROUP_OVERRIDE:
            report.contradictory_records += 1
            report.blocking_issues.append(
                f"Invalid manual_trim_group_override for {record_id}"
            )
        try:
            five = parse_trim_nt(
                row.get("manual_trim_5p_nt", ""),
                field_name="manual_trim_5p_nt",
                record_id=record_id,
            )
            three = parse_trim_nt(
                row.get("manual_trim_3p_nt", ""),
                field_name="manual_trim_3p_nt",
                record_id=record_id,
            )
        except AptaDBCheckpoint1ReviewError as exc:
            report.invalid_trim_lengths += 1
            report.blocking_issues.append(str(exc))
            five = three = None
        if trim_action == "override" and five is None and three is None:
            report.invalid_trim_lengths += 1
            report.blocking_issues.append(
                f"override requires at least one numeric trim length for {record_id}"
            )
        if trim_action == "defer":
            report.deferred_records += 1
            if not allow_deferred:
                report.blocking_issues.append(
                    f"Deferred trim blocks checkpoint closure for {record_id}"
                )
        if decision == "edit":
            changed = any(
                _blank(row.get(name))
                for name in (
                    "manual_sequence_corrected",
                    "manual_target_corrected",
                    "manual_molecule_type_override",
                    "manual_chemistry_override",
                    "manual_trim_action",
                )
            )
            group = groups_by_id.get(row.get("constant_group_id", ""), {})
            group_action = _blank(group.get("manual_trim_action"))
            if not changed and group_action not in {"approve", "override"}:
                report.edit_without_change += 1
                report.blocking_issues.append(
                    f"edit without sequence/molecule/trim change for {record_id}"
                )
        if record_id == "aptadb:1170" and trim_action == "" and decision != "drop":
            report.unresolved_exceptions += 1
            report.blocking_issues.append(
                f"Unresolved core-boundary decision for {record_id}"
            )
        if is_audit_only_row(row) and decision == "":
            report.audit_only_unconfirmed += 1
            if not bulk_confirmed:
                report.blocking_issues.append(
                    f"Audit-only row unconfirmed for {record_id}"
                )
        exception_needed = _truthy(row.get("recommended_trim_group_override"))
        if exception_needed and trim_action == "" and decision != "drop":
            report.unresolved_exceptions += 1
            report.blocking_issues.append(
                f"Unresolved record-level trim exception for {record_id}"
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
            if row["record_id"] in eligible and not is_audit_only_row(row):
                report.blocking_issues.append(
                    f"Bulk confirmation includes non-audit row {row['record_id']}"
                )

    if (
        not report.blocking_issues
        and report.unresolved_manual_decisions == 0
        and report.unresolved_constant_groups == 0
    ):
        report.ready_for_application = report.total_review_records
    return report


def format_validation_markdown(report: ValidationReport) -> str:
    lines = [
        "# AptaDB CHECKPOINT-1 review validation",
        "",
        f"- total review records: `{report.total_review_records}`",
        f"- unresolved manual decisions: `{report.unresolved_manual_decisions}`",
        f"- unresolved constant groups: `{report.unresolved_constant_groups}`",
        f"- contradictory records: `{report.contradictory_records}`",
        f"- invalid trim lengths: `{report.invalid_trim_lengths}`",
        f"- unresolved exceptions: `{report.unresolved_exceptions}`",
        f"- edit without change: `{report.edit_without_change}`",
        f"- drop records: `{report.drop_records}`",
        f"- deferred records: `{report.deferred_records}`",
        f"- deferred groups: `{report.deferred_groups}`",
        f"- audit-only unconfirmed: `{report.audit_only_unconfirmed}`",
        f"- ready for application: `{report.ready_for_application}`",
        "",
        "## Blocking issues",
        "",
    ]
    if report.blocking_issues:
        # Counts only; do not dump every record id in tracked docs. Local file may.
        lines.append(f"- issue count: `{len(report.blocking_issues)}`")
        for issue in report.blocking_issues:
            lines.append(f"- {issue}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Status",
            "",
            "CHECKPOINT-1 is not closed.",
            "No human decisions have been applied.",
            "S4 remains blocked.",
            "",
        ]
    )
    return "\n".join(lines)


def build_review_readme() -> str:
    return """# AptaDB CHECKPOINT-1 human review

This package is a human-review gate. Machine recommendations are guidance
only. Do not treat `review_recommendation` as a completed `manual_decision`.

Permitted `manual_decision` values: `keep` / `drop` / `edit`.

Permitted `manual_trim_action` values: `approve` / `override` / `reject` / `defer`.

`manual_trim_5p_nt` and `manual_trim_3p_nt` are nucleotide counts removed from
reviewed `sequence_full`. Do not paste a hand-trimmed `sequence_core`.

## Step 1 — technical anomalies

Review the 4 judgement-dependent technical records individually
(`review_batch = 01_judgement_dependent_technical`).

## Step 2 — constant-region groups

Fill `aptadb_checkpoint1_constant_group_review.csv` first.

Then inspect record-level exceptions, especially AP65_A1 (`aptadb:459`) and
G5α3N.4 (`aptadb:1170`). The G5α3N.4 5-prime core boundary is deliberately
unresolved until you enter an explicit trim action or `defer`.

## Step 3 — boundary/random audit

Otherwise-clean `length_boundary` and/or `random_kept_audit` rows are marked
`bulk_audit_eligible=true` with recommendation `keep_current_route`.

To confirm them in bulk later, set `confirm=true` in
`aptadb_checkpoint1_bulk_audit_confirmation.csv`. Do not do this until the
technical and constant-region decisions are settled. Recommendations alone
do not apply keep.

## Step 4 — validation

From the repository root:

```text
uv run python scripts/data_preparation/checkpoint1_validate_review.py --source aptadb
```

The validator fails closed while required fields are blank.

## Step 5 — stop

Do not run checkpoint apply until Laura/ChatGPT have reviewed the completed
files. Do not start S4.

WARNING: the record-level CSV contains sequences. It must remain under ignored
`data/` and must never be staged or tracked.
"""


def _source_molecule_note(original_molecule: str, reviewed_molecule: str) -> str:
    if original_molecule == reviewed_molecule:
        return ""
    return (
        f"manual_molecule_override original={original_molecule} "
        f"reviewed={reviewed_molecule}"
    )


def apply_reviewed_record(
    *,
    canonical: Mapping[str, str],
    review_row: Mapping[str, str],
    source_metadata: Mapping[str, str],
    s2_qc: Mapping[str, str],
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]] = (),
    group_row: Mapping[str, str] | None = None,
    machine_five: int = 0,
    machine_three: int = 0,
) -> AppliedRecordResult:
    """Apply one reviewed record through shared normalisation + S3 routing.

    Does not mutate ``sequence_raw``. Does not populate S4 fields.
    """
    from adapters.aptadb_s3 import classify_aptadb_record

    record_id = canonical["record_id"]
    original_raw = canonical["sequence_raw"]
    original_molecule = canonical.get("molecule_type", "")
    original_chemistry = canonical.get("chemistry", "")
    route_before = review_row.get("primary_route", "")
    decision = _blank(review_row.get("manual_decision"))
    if decision not in {"keep", "drop", "edit"}:
        raise AptaDBCheckpoint1ReviewError(
            f"Cannot apply unresolved manual_decision for {record_id!r}"
        )
    if decision == "drop":
        updated = dict(canonical)
        for field_name in S3_FORBIDDEN_FIELDS:
            updated[field_name] = ""
        note_parts = [
            "checkpoint1_manual_decision=drop",
            _blank(review_row.get("manual_notes")),
        ]
        updated["notes"] = "|".join(part for part in note_parts if part)
        return AppliedRecordResult(
            record_id=record_id,
            sequence_raw=original_raw,
            sequence_full=canonical.get("sequence_full", ""),
            sequence_core=canonical.get("sequence_core", ""),
            sequence_length_full=int(canonical.get("sequence_length_full") or 0),
            sequence_length_core=int(canonical.get("sequence_length_core") or 0),
            molecule_type=original_molecule,
            chemistry=original_chemistry,
            alphabet_as_reported=canonical.get("alphabet_as_reported", ""),
            t_to_u_applied=canonical.get("t_to_u_applied", "") == "true",
            trim_status=canonical.get("trim_status", ""),
            trim_confidence=canonical.get("trim_confidence", "") or TRIM_CONFIDENCE_NA,
            primary_route_before=route_before,
            primary_route_after=route_before,
            notes=updated["notes"],
            canonical=updated,
        )

    working_input = _blank(review_row.get("manual_sequence_corrected")) or original_raw
    molecule = (
        _blank(review_row.get("manual_molecule_type_override")) or original_molecule
    )
    chemistry = _blank(review_row.get("manual_chemistry_override"))
    if not chemistry:
        chemistry = (
            default_chemistry_for_molecule(molecule)
            if molecule != original_molecule
            else original_chemistry
        )
    if molecule not in ALLOWED_MOLECULE_OVERRIDES and molecule != original_molecule:
        raise AptaDBCheckpoint1ReviewError(
            f"Unsupported molecule override for {record_id!r}"
        )
    if not _molecule_chemistry_consistent(molecule, chemistry):
        raise AptaDBCheckpoint1ReviewError(
            f"Molecule/chemistry override conflict for {record_id!r}"
        )

    trim_action = _blank(review_row.get("manual_trim_action"))
    if trim_action == "defer":
        raise AptaDBCheckpoint1ReviewError(
            f"Deferred trim cannot be applied for {record_id!r}"
        )

    norm = normalise_sequence(working_input, molecule_type=molecule)
    sequence_full = norm.sequence_full or ""
    sequence_core = sequence_full
    trim_status = canonical.get("trim_status") or "no_constants_detected"
    trim_confidence = canonical.get("trim_confidence") or TRIM_CONFIDENCE_NA
    applied_five = 0
    applied_three = 0
    effective = resolve_effective_trim(
        review_row,
        group_row,
        machine_five=machine_five,
        machine_three=machine_three,
    )
    if effective is not None:
        sequence_core = apply_numeric_terminal_trim(
            sequence_full,
            five_nt=effective.five_nt,
            three_nt=effective.three_nt,
            record_id=record_id,
        )
        applied_five = effective.five_nt
        applied_three = effective.three_nt
        source = review_row.get("constant_proposal_sources", "")
        if source == "known_motif" or "known_motif" in source:
            trim_confidence = TRIM_CONFIDENCE_HIGH
            trim_status = "t7_removed" if applied_five and not applied_three else (
                "t7_and_primers_removed" if applied_five and applied_three else "primers_removed"
            )
        else:
            trim_confidence = TRIM_CONFIDENCE_MEDIUM
            trim_status = "primers_removed"

    updated = dict(canonical)
    updated["sequence_raw"] = original_raw
    updated["sequence_full"] = sequence_full
    updated["sequence_core"] = sequence_core
    updated["sequence_length_full"] = str(len(sequence_full)) if sequence_full else ""
    updated["sequence_length_core"] = str(len(sequence_core)) if sequence_core else ""
    updated["molecule_type"] = molecule
    updated["chemistry"] = chemistry
    updated["alphabet_as_reported"] = norm.alphabet_as_reported
    updated["t_to_u_applied"] = "true" if norm.t_to_u_applied else "false"
    updated["trim_status"] = trim_status
    updated["trim_confidence"] = trim_confidence
    updated["qc_flags"] = "|".join(norm.qc_flags)
    for field_name in S3_FORBIDDEN_FIELDS:
        updated[field_name] = ""

    qc = dict(s2_qc)
    qc["record_id"] = record_id
    qc["molecule_type"] = molecule
    qc["chemistry"] = chemistry
    qc["alphabet_as_reported"] = updated["alphabet_as_reported"]
    qc["t_to_u_applied"] = updated["t_to_u_applied"]
    qc["sequence_length_full"] = updated["sequence_length_full"]
    qc["sequence_length_core"] = updated["sequence_length_core"]
    qc["trim_status"] = trim_status
    qc["trim_confidence"] = trim_confidence
    qc["qc_flags"] = updated["qc_flags"]

    classified = classify_aptadb_record(
        updated,
        qc,
        source_metadata,
        policy=policy,
        proposals=proposals,
    )
    route_after = classified.decision["primary_route"]

    note_parts = [
        f"checkpoint1_manual_decision={decision}",
    ]
    if working_input != original_raw:
        note_parts.append("manual_sequence_correction_applied")
    mol_note = _source_molecule_note(original_molecule, molecule)
    if mol_note:
        note_parts.append(mol_note)
    if effective is not None:
        note_parts.append(
            f"manual_trim_action={effective.action};"
            f"applied_5p={applied_five};applied_3p={applied_three};"
            f"trim_source={effective.source};group={effective.group_id}"
        )
    if review_row.get("manual_notes"):
        note_parts.append(f"reviewer_notes_present=true")
    note_parts.append(f"route_before={route_before}")
    note_parts.append(f"route_after={route_after}")
    updated["notes"] = "|".join(part for part in note_parts if part)
    updated["primary_route"] = route_after

    return AppliedRecordResult(
        record_id=record_id,
        sequence_raw=original_raw,
        sequence_full=sequence_full,
        sequence_core=sequence_core,
        sequence_length_full=len(sequence_full),
        sequence_length_core=len(sequence_core),
        molecule_type=molecule,
        chemistry=chemistry,
        alphabet_as_reported=updated["alphabet_as_reported"],
        t_to_u_applied=norm.t_to_u_applied,
        trim_status=trim_status,
        trim_confidence=trim_confidence,
        primary_route_before=route_before,
        primary_route_after=route_after,
        notes=updated["notes"],
        canonical=updated,
    )


def apply_aptadb_checkpoint1_package(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    group_rows: Sequence[Mapping[str, str]],
    canonical_by_id: Mapping[str, Mapping[str, str]],
    source_metadata_by_id: Mapping[str, Mapping[str, str]],
    s2_qc_by_id: Mapping[str, Mapping[str, str]],
    policy: EligibilityPolicy,
    proposals_by_record: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
    bulk_confirmation: Mapping[str, str] | None = None,
    allow_deferred: bool = False,
) -> tuple[list[AppliedRecordResult], ValidationReport]:
    """Apply a fully resolved AptaDB CHECKPOINT-1 package.

    Fail-closed: unresolved, deferred (unless allowed), or invalid fields raise.
    """
    report = validate_review_package(
        queue_rows=queue_rows,
        group_rows=group_rows,
        bulk_confirmation=bulk_confirmation,
        allow_deferred=allow_deferred,
    )
    if not report.ok:
        raise AptaDBCheckpoint1ReviewError(
            "CHECKPOINT-1 cannot be applied while required human decisions "
            f"remain unresolved ({len(report.blocking_issues)} blocking issues)"
        )
    groups_by_id = {row["constant_group_id"]: row for row in group_rows}
    proposals_by_record = proposals_by_record or {}
    applied: list[AppliedRecordResult] = []
    for row in queue_rows:
        record_id = row["record_id"]
        group = groups_by_id.get(row.get("constant_group_id", ""), None)
        machine_five = 0
        machine_three = 0
        if group:
            machine_five = int(group["machine_trim_5p_nt"] or 0) if str(
                group.get("machine_trim_5p_nt") or ""
            ).isdigit() else 0
            machine_three = int(group["machine_trim_3p_nt"] or 0) if str(
                group.get("machine_trim_3p_nt") or ""
            ).isdigit() else 0
        applied.append(
            apply_reviewed_record(
                canonical=canonical_by_id[record_id],
                review_row=row,
                source_metadata=source_metadata_by_id[record_id],
                s2_qc=s2_qc_by_id[record_id],
                policy=policy,
                proposals=list(proposals_by_record.get(record_id, ())),
                group_row=group,
                machine_five=machine_five,
                machine_three=machine_three,
            )
        )
    return applied, report


def load_default_policy(repo_root: Path) -> EligibilityPolicy:
    return load_eligibility_policy(repo_root / DEFAULT_POLICY_REL)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))

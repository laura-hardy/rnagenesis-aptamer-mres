"""ENA CHECKPOINT-1 application transform, dry-run preview, and closure helpers.

Dry-run and real apply share ``apply_ena_reviewed_record`` /
``simulate_ena_checkpoint1_application``. Real apply writes ignored
``resolved/`` outputs and sequence-free tracked closure artefacts.
It does not start S4 or prepare a global-S4 source handoff.

``manual_decision=keep`` retains the source record, applies reviewed
trim/no-trim resolution, then recomputes technical eligibility. It does not
force ``technically_eligible``.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Final, Mapping, Sequence

from adapters.aptadb_checkpoint1_review import (
    AppliedRecordResult,
    AptaDBCheckpoint1ReviewError,
    EffectiveTrim,
    LARGE_TRIM_HUMAN_APPROVED_FLAG,
    apply_numeric_terminal_trim,
    combined_trim_exceeds_review_threshold,
    combined_trim_fraction,
    format_large_trim_provenance,
    is_explicit_human_trim_authorisation,
    parse_trim_nt,
)
from adapters.ena_checkpoint1_review import (
    ALLOWED_RECONCILIATION_DECISIONS,
    ALLOWED_TRIM_ACTIONS,
    CORE_LENGTH_MIN,
    MANUAL_FIELDS,
    ValidationReport,
    _comparison_form,
    _truthy,
    validate_ena_review_package,
)
from adapters.ena_s3 import (
    DECISION_COLUMNS,
    PARK_COLUMNS,
    PRIMARY_ROUTE_CONSTRUCT,
    PRIMARY_ROUTE_ELIGIBLE,
    PRIMARY_ROUTE_REJECT,
    REJECTION_COLUMNS,
    classify_ena_record,
)
from adapters.utexas_constant_region_review import simulate_hypothetical_trim
from common.corpus_schema import (
    CORPUS_COLUMNS,
    S3_FORBIDDEN_FIELDS,
    format_qc_flags,
)
from common.eligibility import EligibilityPolicy, parse_qc_flags
from common.sequence_normalisation import TRIM_CONFIDENCE_MEDIUM, TRIM_CONFIDENCE_NA

DEFAULT_POLICY_REL: Final[str] = "config/source_eligibility/ena.json"
CORE_LENGTH_MAX: Final[int] = 100
PARKING_TRIM_FLAGS: Final[frozenset[str]] = frozenset(
    {"trim_requires_review", "constants_suspected_unresolved"}
)
DRY_RUN_BANNER: Final[str] = (
    "DRY-RUN PREVIEW. NOT AUTHORITATIVE. CHECKPOINT-1 IS NOT APPLIED. "
    "S4 REMAINS BLOCKED."
)
SOURCE_DATASET: Final[str] = "ena_selected_v2_2026-08"
AUTHORISED_FOR_S4_MEANING: Final[str] = (
    "authorised_for_s4=true means technically eligible after ENA "
    "sequence/molecule/construct CHECKPOINT-1 and allowed to enter a "
    "future global-S4 source handoff. It does not mean target "
    "canonicalised, protein confirmed, evidence threshold passed, "
    "leakage cleared, deduplicated, clustered, balanced, or partitioned."
)
ENA_CHECKPOINT_CLOSED_STATEMENT: Final[str] = (
    "CHECKPOINT-1 CLOSED: human review has been applied and validated.\n"
    "Only records with authorised_for_s4=true may proceed to a future "
    "global S4 handoff.\n"
    + AUTHORISED_FOR_S4_MEANING
)

QUEUE_HUMAN_FIELDS: Final[frozenset[str]] = frozenset(MANUAL_FIELDS)
RULE_HUMAN_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "manual_trim_action",
        "manual_trim_5p_nt",
        "manual_trim_3p_nt",
        "manual_notes",
    }
)
EXCEPTION_HUMAN_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "manual_decision",
        "manual_trim_action",
        "manual_trim_5p_nt",
        "manual_trim_3p_nt",
        "manual_notes",
    }
)
RECONCILIATION_HUMAN_FIELDS: Final[frozenset[str]] = frozenset(
    {"manual_decision", "manual_notes"}
)
BULK_HUMAN_FIELDS: Final[frozenset[str]] = frozenset(
    {"confirm", "reviewer_initials", "manual_notes"}
)

CHANGE_REPORT_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "pre_review_route",
    "post_review_route",
    "manual_decision",
    "trim_action",
    "trim_5p_nt",
    "trim_3p_nt",
    "trim_source",
    "pre_core_length",
    "post_core_length",
    "route_changed",
    "primary_reason_before",
    "primary_reason_after",
    "rejection_reason_before",
    "rejection_reason_after",
    "large_trim_human_approved",
    "cause",
)

GROUP_SUMMARY_COLUMNS: Final[tuple[str, ...]] = (
    "constant_rule_id",
    "experiment_group_id",
    "side",
    "manual_trim_action",
    "applied_nt",
    "n_linked_records",
    "n_trimmed",
    "n_large_trim_human_approved",
    "core_length_min",
    "core_length_median",
    "core_length_max",
    "guard_rail_failures",
    "n_route_changed",
    "record_exceptions",
)

ELIGIBLE_PREVIEW_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "proposed_decision",
    "primary_reason",
    "primary_route",
    "molecule_type",
    "chemistry",
    "sequence_length_full",
    "sequence_length_core",
    "trim_status",
    "trim_confidence",
    "t_to_u_applied",
)

GUARD_RAIL_FAILURE_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "experiment_group_id",
    "manual_decision",
    "pre_full_length",
    "pre_core_length",
    "trim_5p_nt",
    "trim_3p_nt",
    "combined_trim_nt",
    "combined_trim_fraction",
    "hypothetical_core_length",
    "error",
)

LARGE_TRIM_RECORD_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "experiment_group_id",
    "trim_source",
    "human_trim_action",
    "full_length",
    "trim_5p_nt",
    "trim_3p_nt",
    "trim_fraction",
    "trim_pct",
    "core_length",
    "authorisation",
    "large_trim_human_approved",
    "pre_review_route",
    "post_review_route",
    "route_changed",
)

PREVIEW_COMPARISON_FILES: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "canonical",
        "ena_checkpoint1_dry_run_canonical_preview.csv",
        "ena_checkpoint1_applied_canonical.csv",
    ),
    (
        "routing",
        "ena_checkpoint1_dry_run_routing_preview.csv",
        "ena_checkpoint1_applied_routing.csv",
    ),
    (
        "rejection",
        "ena_checkpoint1_dry_run_rejection_preview.csv",
        "ena_checkpoint1_applied_rejection.csv",
    ),
    (
        "parked_construct",
        "ena_checkpoint1_dry_run_parked_construct_preview.csv",
        "ena_checkpoint1_applied_parked_construct.csv",
    ),
    (
        "eligible",
        "ena_checkpoint1_dry_run_eligible_preview.csv",
        "ena_checkpoint1_applied_eligible.csv",
    ),
    (
        "change_report",
        "ena_checkpoint1_dry_run_change_report.csv",
        "ena_checkpoint1_applied_change_report.csv",
    ),
    (
        "group_summary",
        "ena_checkpoint1_dry_run_group_summary.csv",
        "ena_checkpoint1_applied_group_summary.csv",
    ),
    (
        "large_trim_human_approved",
        "ena_checkpoint1_dry_run_large_trim_human_approved.csv",
        "ena_checkpoint1_applied_large_trim_human_approved.csv",
    ),
    (
        "guard_rail_failures",
        "ena_checkpoint1_dry_run_guard_rail_failures.csv",
        "ena_checkpoint1_applied_guard_rail_failures.csv",
    ),
)

ENA_TRACKED_RESOLUTION_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "primary_route",
    "proposed_decision",
    "resolved_decision",
    "primary_reason",
    "checkpoint1_resolution_status",
    "authorised_for_s4",
    "manual_decision",
    "route_changed",
)

ROUTE_TO_STATUS: Final[Mapping[str, str]] = {
    PRIMARY_ROUTE_ELIGIBLE: "approved_for_s4",
    PRIMARY_ROUTE_CONSTRUCT: "parked_after_checkpoint1",
    PRIMARY_ROUTE_REJECT: "rejected_after_checkpoint1",
}

CLOSURE_ONLY_FIELDS: Final[tuple[str, ...]] = (
    "checkpoint_status",
    "checkpoint_closed",
    "application_mode",
    "review_file_sha256",
    "review_index_sha256",
    "review_rules_sha256",
    "review_exceptions_sha256",
    "review_reconciliation_sha256",
    "review_reconciliation_index_sha256",
    "review_bulk_sha256",
    "raw_sha256",
    "s1_sha256",
    "sidecar_sha256",
    "s2_sha256",
    "s3_sha256",
    "s3_decisions_sha256",
    "accepted_dry_run_hashes",
    "output_hashes",
    "record_decisions",
    "next_stage",
    "s4_started",
    "global_s4_handoff_prepared",
    "global_s4_run",
)

TRACKED_SEQUENCE_COLUMN_FRAGMENTS: Final[tuple[str, ...]] = (
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "manual_sequence_corrected",
    "detected_constant_5p",
    "detected_constant_3p",
    "proposed_sequence",
    "proposed_5p_sequence",
    "proposed_3p_sequence",
    "motif",
)


class EnaCheckpoint1ApplyError(ValueError):
    """Hard failure while applying or dry-running ENA CHECKPOINT-1."""


@dataclass
class EnaDryRunSimulation:
    """In-memory dry-run preview. Not an applied checkpoint."""

    preview_canonical: list[dict[str, str]]
    preview_decisions: list[dict[str, str]]
    preview_rejections: list[dict[str, str]]
    preview_parked_construct: list[dict[str, str]]
    preview_eligible: list[dict[str, str]]
    change_report: list[dict[str, str]]
    group_summaries: list[dict[str, str]]
    applied: list[AppliedRecordResult]
    route_changed_ids: tuple[str, ...]
    guard_rail_failure_rows: list[dict[str, str]] = field(default_factory=list)
    large_trim_records: list[dict[str, str]] = field(default_factory=list)
    stats: dict[str, int | str | bool | float] = field(default_factory=dict)


def _blank(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _corpus_only(record: Mapping[str, str]) -> dict[str, str]:
    return {column: str(record.get(column, "") or "") for column in CORPUS_COLUMNS}


def _row(columns: Sequence[str], source: Mapping[str, str]) -> dict[str, str]:
    return {column: str(source.get(column, "") or "") for column in columns}


def _int_len(value: str) -> int:
    text = _blank(value)
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


def load_default_policy(repo_root) -> EligibilityPolicy:
    from pathlib import Path

    from common.eligibility import load_eligibility_policy

    return load_eligibility_policy(Path(repo_root) / DEFAULT_POLICY_REL)


def _cells_equal(left: str, right: str) -> bool:
    return _blank(left) == _blank(right)


def _compare_table(
    *,
    reviewed: Sequence[Mapping[str, str]],
    pristine: Sequence[Mapping[str, str]],
    key_fields: Sequence[str],
    human_fields: frozenset[str],
    label: str,
) -> None:
    if len(reviewed) != len(pristine):
        raise EnaCheckpoint1ApplyError(
            f"{label} row count differs from pristine: "
            f"{len(reviewed)} vs {len(pristine)}"
        )

    def _key(row: Mapping[str, str]) -> tuple[str, ...]:
        return tuple(_blank(row.get(name, "")) for name in key_fields)

    reviewed_by = {_key(row): row for row in reviewed}
    pristine_by = {_key(row): row for row in pristine}
    if len(reviewed_by) != len(reviewed):
        raise EnaCheckpoint1ApplyError(f"{label} has duplicate comparison keys")
    missing = sorted(pristine_by.keys() - reviewed_by.keys())
    extra = sorted(reviewed_by.keys() - pristine_by.keys())
    if missing or extra:
        raise EnaCheckpoint1ApplyError(
            f"{label} keys differ from pristine baseline"
        )
    drifts: list[str] = []
    for key, pristine_row in pristine_by.items():
        reviewed_row = reviewed_by[key]
        fields = set(pristine_row) | set(reviewed_row)
        for field_name in sorted(fields):
            if field_name in human_fields:
                continue
            if not _cells_equal(
                reviewed_row.get(field_name, ""), pristine_row.get(field_name, "")
            ):
                drifts.append(f"{label}:{field_name}:{key[0]}")
    if drifts:
        raise EnaCheckpoint1ApplyError(
            "Non-review fields differ from pristine baseline: "
            + ", ".join(drifts[:12])
        )


def compare_ena_package_to_pristine(
    *,
    reviewed_queue: Sequence[Mapping[str, str]],
    pristine_queue: Sequence[Mapping[str, str]],
    reviewed_rules: Sequence[Mapping[str, str]],
    pristine_rules: Sequence[Mapping[str, str]],
    reviewed_exceptions: Sequence[Mapping[str, str]],
    pristine_exceptions: Sequence[Mapping[str, str]],
    reviewed_reconciliation: Sequence[Mapping[str, str]],
    pristine_reconciliation: Sequence[Mapping[str, str]],
    reviewed_bulk: Sequence[Mapping[str, str]],
    pristine_bulk: Sequence[Mapping[str, str]],
    reviewed_membership: Sequence[Mapping[str, str]] | None = None,
    pristine_membership: Sequence[Mapping[str, str]] | None = None,
) -> None:
    """Hard-fail if scientific/machine fields changed outside human columns."""
    _compare_table(
        reviewed=reviewed_queue,
        pristine=pristine_queue,
        key_fields=("record_id",),
        human_fields=QUEUE_HUMAN_FIELDS,
        label="queue",
    )
    _compare_table(
        reviewed=reviewed_rules,
        pristine=pristine_rules,
        key_fields=("constant_rule_id",),
        human_fields=RULE_HUMAN_FIELDS,
        label="rules",
    )
    _compare_table(
        reviewed=reviewed_exceptions,
        pristine=pristine_exceptions,
        key_fields=("constant_rule_id", "record_id"),
        human_fields=EXCEPTION_HUMAN_FIELDS,
        label="exceptions",
    )
    _compare_table(
        reviewed=reviewed_reconciliation,
        pristine=pristine_reconciliation,
        key_fields=("reconciliation_id",),
        human_fields=RECONCILIATION_HUMAN_FIELDS,
        label="reconciliation",
    )
    _compare_table(
        reviewed=reviewed_bulk,
        pristine=pristine_bulk,
        key_fields=("confirmation_id",),
        human_fields=BULK_HUMAN_FIELDS,
        label="bulk",
    )
    if reviewed_membership is not None and pristine_membership is not None:
        _compare_table(
            reviewed=reviewed_membership,
            pristine=pristine_membership,
            key_fields=("constant_rule_id", "record_id"),
            human_fields=frozenset(),
            label="membership",
        )


def _side_nt(row: Mapping[str, str], side: str) -> int | None:
    field_name = "manual_trim_5p_nt" if side == "five_prime" else "manual_trim_3p_nt"
    record_id = row.get("record_id") or row.get("constant_rule_id") or ""
    return parse_trim_nt(
        row.get(field_name, ""),
        field_name=field_name,
        record_id=record_id,
    )


def _motif_length(row: Mapping[str, str]) -> int:
    text = _blank(row.get("motif_length"))
    if not text.isdigit():
        raise EnaCheckpoint1ApplyError(
            f"Missing motif_length for {row.get('constant_rule_id')!r}"
        )
    return int(text)


def resolve_ena_side_trim(
    *,
    record_id: str,
    side: str,
    rule: Mapping[str, str],
    exception: Mapping[str, str] | None,
) -> tuple[str, int, str]:
    """Return ``(action, nt, source)`` for one side. Reject yields nt=0."""
    if exception is not None:
        action = _blank(exception.get("manual_trim_action")) or _blank(
            rule.get("manual_trim_action")
        )
        source = "record"
        try:
            nt_override = _side_nt(exception, side)
        except AptaDBCheckpoint1ReviewError as exc:
            raise EnaCheckpoint1ApplyError(str(exc)) from exc
    else:
        action = _blank(rule.get("manual_trim_action"))
        source = "group"
        nt_override = None
    if action not in ALLOWED_TRIM_ACTIONS or action in {"", "defer"}:
        raise EnaCheckpoint1ApplyError(
            f"Missing or deferred trim decision for {record_id!r} side={side}"
        )
    if action == "reject":
        return action, 0, source
    try:
        rule_nt = _side_nt(rule, side)
    except AptaDBCheckpoint1ReviewError as exc:
        raise EnaCheckpoint1ApplyError(str(exc)) from exc
    machine = _motif_length(rule)
    if action == "approve":
        nt = nt_override if nt_override is not None else (
            rule_nt if rule_nt is not None else machine
        )
    else:
        nt = nt_override if nt_override is not None else rule_nt
        if nt is None:
            raise EnaCheckpoint1ApplyError(
                f"Invalid trim length for override on {record_id!r} side={side}"
            )
    if nt <= 0:
        raise EnaCheckpoint1ApplyError(
            f"Invalid trim length {nt} for {record_id!r} side={side}"
        )
    return action, nt, source


def resolve_ena_effective_trim(
    *,
    record_id: str,
    rules_for_record: Sequence[Mapping[str, str]],
    exceptions_for_record: Mapping[str, Mapping[str, str]],
) -> EffectiveTrim | None:
    """Combine matching 5′/3′ group rules and record exceptions once.

    Record-level exception decisions take precedence for that side. They do
    not stack on top of the group length.
    """
    five_action = ""
    three_action = ""
    five_nt = 0
    three_nt = 0
    five_source = ""
    three_source = ""
    group_id = ""
    for rule in rules_for_record:
        side = _blank(rule.get("side"))
        rule_id = _blank(rule.get("constant_rule_id") or rule.get("proposal_id"))
        exception = exceptions_for_record.get(rule_id)
        action, nt, source = resolve_ena_side_trim(
            record_id=record_id,
            side=side,
            rule=rule,
            exception=exception,
        )
        group_id = group_id or _blank(rule.get("experiment_group_id"))
        if side == "five_prime":
            if five_action:
                raise EnaCheckpoint1ApplyError(
                    f"Duplicate 5′ rule application for {record_id!r}"
                )
            five_action, five_nt, five_source = action, nt, source
        elif side == "three_prime":
            if three_action:
                raise EnaCheckpoint1ApplyError(
                    f"Duplicate 3′ rule application for {record_id!r}"
                )
            three_action, three_nt, three_source = action, nt, source
        else:
            raise EnaCheckpoint1ApplyError(
                f"Unknown trim side {side!r} for {record_id!r}"
            )
    if not five_action and not three_action:
        return None
    if five_nt == 0 and three_nt == 0:
        return None
    actions = [part for part in (five_action, three_action) if part in {"approve", "override"}]
    if not actions:
        return None
    action = "override" if "override" in actions else "approve"
    source = "record" if "record" in {five_source, three_source} else "group"
    return EffectiveTrim(
        action=action,
        five_nt=five_nt,
        three_nt=three_nt,
        source=source,
        group_id=group_id,
    )


def derive_reviewed_terminal_motif(
    sequences: Sequence[str],
    *,
    side: str,
    length: int,
    record_ids: Sequence[str],
) -> str:
    """Derive one reviewed terminal motif from ignored sequence-bearing data.

    All members with the same reviewed length must share one comparison-form
    terminal. Does not embed a biological motif in tracked artefacts.
    """
    if length <= 0:
        raise EnaCheckpoint1ApplyError("Reviewed motif length must be positive")
    forms: dict[str, str] = {}
    for record_id, sequence in zip(record_ids, sequences, strict=True):
        if len(sequence) < length:
            raise EnaCheckpoint1ApplyError(
                f"Reviewed {side} trim exceeds sequence_full for {record_id!r}"
            )
        terminal = sequence[:length] if side == "five_prime" else sequence[-length:]
        form = _comparison_form(terminal)
        forms.setdefault(form, terminal)
    if len(forms) != 1:
        raise EnaCheckpoint1ApplyError(
            f"Reviewed {side} {length}-nt boundary is not a unique terminal "
            f"constant across {len(record_ids)} records"
        )
    return next(iter(forms.values()))


def apply_reviewed_terminal_trim(
    sequence_full: str,
    *,
    five_nt: int,
    three_nt: int,
    five_motif: str,
    three_motif: str,
    record_id: str,
    human_authorised: bool,
    min_core: int = CORE_LENGTH_MIN,
    max_core: int = CORE_LENGTH_MAX,
) -> str:
    """Apply one combined reviewed trim after exact-terminal verification."""
    if five_nt:
        effect = simulate_hypothetical_trim(
            sequence_full, side="five_prime", motif=five_motif
        )
        if not effect.matched:
            raise EnaCheckpoint1ApplyError(
                f"Reviewed 5′ boundary is not an exact terminal match for "
                f"{record_id!r}"
            )
        if len(five_motif) != five_nt:
            raise EnaCheckpoint1ApplyError(
                f"Reviewed 5′ motif length mismatch for {record_id!r}"
            )
    if three_nt:
        effect = simulate_hypothetical_trim(
            sequence_full, side="three_prime", motif=three_motif
        )
        if not effect.matched:
            raise EnaCheckpoint1ApplyError(
                f"Reviewed 3′ boundary is not an exact terminal match for "
                f"{record_id!r}"
            )
        if len(three_motif) != three_nt:
            raise EnaCheckpoint1ApplyError(
                f"Reviewed 3′ motif length mismatch for {record_id!r}"
            )
    try:
        core = apply_numeric_terminal_trim(
            sequence_full,
            five_nt=five_nt,
            three_nt=three_nt,
            record_id=record_id,
            min_core=min_core,
            human_authorised=human_authorised,
        )
    except AptaDBCheckpoint1ReviewError as exc:
        raise EnaCheckpoint1ApplyError(str(exc)) from exc
    if not core:
        raise EnaCheckpoint1ApplyError(f"Trim would leave an empty core for {record_id!r}")
    if len(core) < min_core:
        raise EnaCheckpoint1ApplyError(
            f"Trim would leave core below {min_core} nt for {record_id!r}"
        )
    if len(core) > max_core:
        raise EnaCheckpoint1ApplyError(
            f"Trim would leave core above {max_core} nt for {record_id!r}"
        )
    if core not in sequence_full:
        raise EnaCheckpoint1ApplyError(
            f"sequence_core is not a contiguous substring of sequence_full "
            f"for {record_id!r}"
        )
    return core


def _synthetic_review_row(
    *,
    canonical: Mapping[str, str],
    decision: Mapping[str, str],
) -> dict[str, str]:
    row = {name: "" for name in MANUAL_FIELDS}
    row.update(
        {
            "record_id": canonical["record_id"],
            "native_id": canonical.get("native_id", ""),
            "primary_route": decision.get("primary_route", ""),
            "proposed_decision": decision.get("proposed_decision", ""),
            "primary_reason": decision.get("primary_reason", ""),
            "checkpoint_review_reasons": decision.get("checkpoint_review_reasons", ""),
            "source_promoter_or_template_concern": decision.get(
                "source_promoter_or_template_concern", ""
            ),
            "manual_decision": "keep",
        }
    )
    return row


def apply_ena_reviewed_record(
    *,
    canonical: Mapping[str, str],
    review_row: Mapping[str, str],
    source_metadata: Mapping[str, str],
    s2_qc: Mapping[str, str],
    policy: EligibilityPolicy,
    proposals: Sequence[Mapping[str, str]] = (),
    effective: EffectiveTrim | None = None,
    five_motif: str = "",
    three_motif: str = "",
    construct_review_resolved: bool = True,
    original_decision: Mapping[str, str] | None = None,
) -> AppliedRecordResult:
    """Apply one reviewed ENA record through shared trim + S3 recompute."""
    record_id = canonical["record_id"]
    original_raw = canonical["sequence_raw"]
    original_molecule = canonical.get("molecule_type", "")
    original_chemistry = canonical.get("chemistry", "")
    route_before = (
        review_row.get("primary_route")
        or (original_decision or {}).get("primary_route", "")
    )
    decision = _blank(review_row.get("manual_decision"))
    if decision not in {"keep", "drop", "edit"}:
        raise EnaCheckpoint1ApplyError(
            f"Cannot apply unresolved manual_decision for {record_id!r}"
        )
    if _blank(review_row.get("manual_sequence_corrected")):
        raise EnaCheckpoint1ApplyError(
            f"Unexpected sequence correction for {record_id!r}"
        )
    if _blank(review_row.get("manual_molecule_type_override")) or _blank(
        review_row.get("manual_chemistry_override")
    ):
        raise EnaCheckpoint1ApplyError(
            f"Unexpected molecule/chemistry override for {record_id!r}"
        )
    if decision == "drop":
        raise EnaCheckpoint1ApplyError(
            f"ENA CHECKPOINT-1 drop is not authorised for {record_id!r} "
            "in this milestone"
        )
    if decision == "edit":
        raise EnaCheckpoint1ApplyError(
            f"ENA CHECKPOINT-1 edit is not authorised for {record_id!r} "
            "in this milestone"
        )

    sequence_full = canonical.get("sequence_full", "")
    sequence_core = canonical.get("sequence_core", "") or sequence_full
    trim_status = canonical.get("trim_status") or "no_constants_detected"
    trim_confidence = canonical.get("trim_confidence") or TRIM_CONFIDENCE_NA
    applied_five = 0
    applied_three = 0
    trim_frac = 0.0
    large_trim_human_approved = False
    detected_5p = canonical.get("detected_constant_5p", "")
    detected_3p = canonical.get("detected_constant_3p", "")
    record_trim_action = _blank(review_row.get("manual_trim_action"))
    if record_trim_action == "defer":
        raise EnaCheckpoint1ApplyError(
            f"Deferred trim cannot be applied for {record_id!r}"
        )

    if effective is not None:
        human_authorised = is_explicit_human_trim_authorisation(effective.action)
        sequence_core = apply_reviewed_terminal_trim(
            sequence_full,
            five_nt=effective.five_nt,
            three_nt=effective.three_nt,
            five_motif=five_motif,
            three_motif=three_motif,
            record_id=record_id,
            human_authorised=human_authorised,
            min_core=CORE_LENGTH_MIN,
            max_core=int(policy.core_length_max or CORE_LENGTH_MAX),
        )
        applied_five = effective.five_nt
        applied_three = effective.three_nt
        trim_frac = combined_trim_fraction(
            len(sequence_full), applied_five, applied_three
        )
        large_trim_human_approved = (
            human_authorised
            and combined_trim_exceeds_review_threshold(
                len(sequence_full), applied_five, applied_three
            )
        )
        trim_confidence = TRIM_CONFIDENCE_MEDIUM
        trim_status = "primers_removed"
        if applied_five:
            detected_5p = five_motif
        if applied_three:
            detected_3p = three_motif

    updated = _corpus_only(canonical)
    updated["sequence_raw"] = original_raw
    updated["sequence_full"] = sequence_full
    updated["sequence_core"] = sequence_core
    updated["sequence_length_full"] = str(len(sequence_full)) if sequence_full else ""
    updated["sequence_length_core"] = str(len(sequence_core)) if sequence_core else ""
    updated["molecule_type"] = original_molecule
    updated["chemistry"] = original_chemistry
    updated["alphabet_as_reported"] = canonical.get("alphabet_as_reported", "")
    updated["t_to_u_applied"] = canonical.get("t_to_u_applied", "")
    updated["trim_status"] = trim_status
    updated["trim_confidence"] = trim_confidence
    updated["detected_constant_5p"] = detected_5p
    updated["detected_constant_3p"] = detected_3p
    qc_flag_values = [
        flag
        for flag in parse_qc_flags(canonical.get("qc_flags", ""))
        if flag not in PARKING_TRIM_FLAGS
    ]
    if large_trim_human_approved:
        qc_flag_values.append(LARGE_TRIM_HUMAN_APPROVED_FLAG)
    updated["qc_flags"] = format_qc_flags(qc_flag_values)
    for field_name in S3_FORBIDDEN_FIELDS:
        updated[field_name] = ""

    qc = dict(s2_qc)
    qc["record_id"] = record_id
    qc["molecule_type"] = original_molecule
    qc["chemistry"] = original_chemistry
    qc["alphabet_as_reported"] = updated["alphabet_as_reported"]
    qc["t_to_u_applied"] = updated["t_to_u_applied"]
    qc["sequence_length_full"] = updated["sequence_length_full"]
    qc["sequence_length_core"] = updated["sequence_length_core"]
    qc["trim_status"] = trim_status
    qc["trim_confidence"] = trim_confidence
    qc["qc_flags"] = updated["qc_flags"]

    classified = classify_ena_record(
        updated,
        qc,
        source_metadata,
        policy=policy,
        proposals=proposals,
        construct_review_resolved=construct_review_resolved,
    )
    route_after = classified.decision["primary_route"]
    if classified.canonical.get("sequence_raw") != original_raw:
        raise EnaCheckpoint1ApplyError(
            f"Apply mutated sequence_raw for {record_id!r}"
        )
    if classified.canonical.get("t_to_u_applied") != updated["t_to_u_applied"]:
        raise EnaCheckpoint1ApplyError(
            f"Apply mutated T→U provenance for {record_id!r}"
        )

    note_parts = [f"checkpoint1_manual_decision={decision}"]
    if effective is not None:
        note_parts.append(
            f"manual_trim_action={effective.action};"
            f"applied_5p={applied_five};applied_3p={applied_three};"
            f"trim_source={effective.source};group={effective.group_id}"
        )
    elif record_trim_action == "reject":
        note_parts.append("manual_trim_action=reject;no_additional_trim")
        if _truthy(review_row.get("source_promoter_or_template_concern")):
            note_parts.append(
                "checkpoint1_promoter_or_template_concern_reviewed=true;"
                "no_trim_applied"
            )
    elif not rules_empty(proposals) and applied_five == 0 and applied_three == 0:
        note_parts.append("manual_trim_action=reject;no_additional_trim")
    if large_trim_human_approved:
        note_parts.append(
            format_large_trim_provenance(
                fraction=trim_frac,
                five_nt=applied_five,
                three_nt=applied_three,
                core_length=len(sequence_core),
                trim_source=effective.source if effective is not None else "",
                human_trim_action=effective.action if effective is not None else "",
                group_id=effective.group_id if effective is not None else "",
            )
        )
    if review_row.get("manual_notes"):
        note_parts.append("reviewer_notes_present=true")
    note_parts.append(f"route_before={route_before}")
    note_parts.append(f"route_after={route_after}")
    updated["notes"] = "|".join(part for part in note_parts if part)
    classified.canonical["notes"] = updated["notes"]
    classified.canonical["detected_constant_5p"] = detected_5p
    classified.canonical["detected_constant_3p"] = detected_3p
    classified.canonical["qc_flags"] = updated["qc_flags"]
    decision_row = dict(classified.decision)
    decision_row["notes"] = updated["notes"]
    decision_row["trim_status"] = trim_status
    decision_row["trim_confidence"] = trim_confidence
    decision_row["qc_flags"] = updated["qc_flags"]
    decision_row["sequence_length_full"] = updated["sequence_length_full"]
    decision_row["sequence_length_core"] = updated["sequence_length_core"]
    if original_decision:
        for field_name in (
            "legacy_collapse_member",
            "exact_sequence_full_duplicate_diagnostic",
        ):
            if original_decision.get(field_name):
                decision_row[field_name] = original_decision[field_name]
        if original_decision.get("exact_sequence_full_duplicate_diagnostic") == "true":
            notes = [
                part for part in (decision_row.get("notes") or "").split("|") if part
            ]
            diagnostic = "diagnostic only — no deduplication performed"
            if diagnostic not in notes:
                notes.append(diagnostic)
            decision_row["notes"] = "|".join(notes)
            classified.canonical["notes"] = decision_row["notes"]
            updated["notes"] = decision_row["notes"]
    rejection_row = dict(classified.rejection_row) if classified.rejection_row else None
    park_row = dict(classified.park_row) if classified.park_row else None
    if park_row is not None:
        park_row["sequence_length_core"] = updated["sequence_length_core"]
        park_row["trim_status"] = trim_status
        park_row["trim_confidence"] = trim_confidence
        park_row["qc_flags"] = updated["qc_flags"]

    return AppliedRecordResult(
        record_id=record_id,
        sequence_raw=original_raw,
        sequence_full=sequence_full,
        sequence_core=sequence_core,
        sequence_length_full=len(sequence_full) if sequence_full else 0,
        sequence_length_core=len(sequence_core) if sequence_core else 0,
        molecule_type=original_molecule,
        chemistry=original_chemistry,
        alphabet_as_reported=updated["alphabet_as_reported"],
        t_to_u_applied=updated["t_to_u_applied"] == "true",
        trim_status=trim_status,
        trim_confidence=trim_confidence,
        primary_route_before=route_before,
        primary_route_after=route_after,
        notes=updated["notes"],
        canonical=classified.canonical,
        proposed_decision=decision_row.get("proposed_decision", ""),
        primary_reason=decision_row.get("primary_reason", ""),
        decision=decision_row,
        rejection_row=rejection_row,
        park_row=park_row,
        applied_trim_5p_nt=applied_five,
        applied_trim_3p_nt=applied_three,
        trim_source=effective.source if effective is not None else "",
        sequence_corrected=False,
        molecule_overridden=False,
        large_trim_human_approved=large_trim_human_approved,
        trim_fraction=trim_frac,
    )


def rules_empty(proposals: Sequence[Mapping[str, str]]) -> bool:
    return not any(
        row.get("proposal_source") == "group_consensus" for row in proposals
    )


def _index_rules(
    rule_rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rule_rows:
        rule_id = _blank(row.get("constant_rule_id") or row.get("proposal_id"))
        if not rule_id:
            raise EnaCheckpoint1ApplyError("Rule row missing constant_rule_id")
        if rule_id in indexed:
            raise EnaCheckpoint1ApplyError(f"Duplicate constant_rule_id {rule_id!r}")
        indexed[rule_id] = dict(row)
    return indexed


def _index_exceptions(
    exception_rows: Sequence[Mapping[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    indexed: dict[tuple[str, str], dict[str, str]] = {}
    for row in exception_rows:
        record_id = _blank(row.get("record_id"))
        rule_id = _blank(row.get("constant_rule_id") or row.get("proposal_id"))
        key = (record_id, rule_id)
        if key in indexed:
            raise EnaCheckpoint1ApplyError(
                f"Duplicate exception for {record_id!r} / {rule_id!r}"
            )
        indexed[key] = dict(row)
    return indexed


def _membership_by_record(
    membership_rows: Sequence[Mapping[str, str]],
) -> dict[str, list[dict[str, str]]]:
    by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in membership_rows:
        record_id = _blank(row.get("record_id"))
        if record_id:
            by_record[record_id].append(dict(row))
    return by_record


def _consume_reconciliation(
    reconciliation_rows: Sequence[Mapping[str, str]],
) -> tuple[int, tuple[str, ...]]:
    retained: list[str] = []
    consumed = 0
    for row in reconciliation_rows:
        decision = _blank(row.get("manual_decision"))
        if decision not in ALLOWED_RECONCILIATION_DECISIONS or decision == "":
            raise EnaCheckpoint1ApplyError(
                f"Unresolved reconciliation {row.get('reconciliation_id')!r}"
            )
        if decision != "retain_both":
            raise EnaCheckpoint1ApplyError(
                "ENA CHECKPOINT-1 cannot collapse reconciliation "
                f"group {row.get('reconciliation_id')!r}"
            )
        consumed += 1
        for field_name in ("record_id_a", "record_id_b"):
            record_id = _blank(row.get(field_name))
            if record_id:
                retained.append(record_id)
    return consumed, tuple(retained)


def _group_motifs_for_rules(
    *,
    rule_rows: Sequence[Mapping[str, str]],
    membership_by_record: Mapping[str, Sequence[Mapping[str, str]]],
    canonical_by_id: Mapping[str, Mapping[str, str]],
    exceptions_by_key: Mapping[tuple[str, str], Mapping[str, str]],
) -> dict[tuple[str, str], str]:
    """Map ``(experiment_group_id, side)`` to one derived reviewed motif."""
    members_by_group_side: dict[tuple[str, str], list[str]] = defaultdict(list)
    for record_id, members in membership_by_record.items():
        for member in members:
            group_id = _blank(member.get("experiment_group_id"))
            side = _blank(member.get("side"))
            if group_id and side:
                members_by_group_side[(group_id, side)].append(record_id)
    motifs: dict[tuple[str, str], str] = {}
    for rule in rule_rows:
        group_id = _blank(rule.get("experiment_group_id"))
        side = _blank(rule.get("side"))
        rule_id = _blank(rule.get("constant_rule_id") or rule.get("proposal_id"))
        record_ids = sorted(set(members_by_group_side.get((group_id, side), ())))
        if not record_ids:
            continue
        lengths: dict[int, list[str]] = defaultdict(list)
        for record_id in record_ids:
            exception = exceptions_by_key.get((record_id, rule_id))
            _action, nt, _source = resolve_ena_side_trim(
                record_id=record_id,
                side=side,
                rule=rule,
                exception=exception,
            )
            if nt:
                lengths[nt].append(record_id)
        for nt, ids in lengths.items():
            sequences = [canonical_by_id[record_id]["sequence_full"] for record_id in ids]
            motifs[(group_id, side)] = derive_reviewed_terminal_motif(
                sequences,
                side=side,
                length=nt,
                record_ids=ids,
            )
    return motifs


def apply_ena_checkpoint1_package(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    rule_rows: Sequence[Mapping[str, str]],
    exception_rows: Sequence[Mapping[str, str]],
    reconciliation_rows: Sequence[Mapping[str, str]],
    canonical_by_id: Mapping[str, Mapping[str, str]],
    decision_by_id: Mapping[str, Mapping[str, str]],
    source_metadata_by_id: Mapping[str, Mapping[str, str]],
    s2_qc_by_id: Mapping[str, Mapping[str, str]],
    policy: EligibilityPolicy,
    membership_rows: Sequence[Mapping[str, str]] = (),
    proposals_by_record: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
    bulk_confirmation: Mapping[str, str] | None = None,
) -> tuple[list[AppliedRecordResult], ValidationReport, dict[str, int]]:
    """Apply a fully resolved ENA CHECKPOINT-1 package in memory."""
    report = validate_ena_review_package(
        queue_rows=queue_rows,
        rule_rows=rule_rows,
        exception_rows=exception_rows,
        reconciliation_rows=reconciliation_rows,
        bulk_confirmation=bulk_confirmation,
    )
    if not report.ok:
        raise EnaCheckpoint1ApplyError(
            "CHECKPOINT-1 cannot be applied while required human decisions "
            f"remain unresolved ({len(report.blocking_issues)} blocking issues)"
        )
    recon_consumed, retained_ids = _consume_reconciliation(reconciliation_rows)
    rules_by_id = _index_rules(rule_rows)
    exceptions_by_key = _index_exceptions(exception_rows)
    membership_by_record = _membership_by_record(membership_rows)
    for member_rows in membership_by_record.values():
        for member in member_rows:
            rule_id = _blank(member.get("constant_rule_id") or member.get("proposal_id"))
            if rule_id not in rules_by_id:
                raise EnaCheckpoint1ApplyError(
                    f"Missing rule decision for {rule_id!r}"
                )
    motifs = _group_motifs_for_rules(
        rule_rows=rule_rows,
        membership_by_record=membership_by_record,
        canonical_by_id=canonical_by_id,
        exceptions_by_key=exceptions_by_key,
    )
    proposals_by_record = proposals_by_record or {}
    queue_by_id = {row["record_id"]: dict(row) for row in queue_rows}
    transform_ids = set(queue_by_id) | set(membership_by_record) | {
        record_id for record_id, _rule_id in exceptions_by_key
    }
    missing_records = sorted(transform_ids - set(canonical_by_id))
    if missing_records:
        raise EnaCheckpoint1ApplyError(
            "Review refers to missing source records: " + ", ".join(missing_records[:8])
        )
    applied: list[AppliedRecordResult] = []
    consumed_exceptions = 0
    for record_id in sorted(transform_ids):
        canonical = canonical_by_id[record_id]
        original_decision = decision_by_id[record_id]
        review_row = queue_by_id.get(record_id) or _synthetic_review_row(
            canonical=canonical,
            decision=original_decision,
        )
        member_rows = membership_by_record.get(record_id, [])
        rules_for_record = []
        exceptions_for_record: dict[str, Mapping[str, str]] = {}
        for member in member_rows:
            rule_id = _blank(member.get("constant_rule_id") or member.get("proposal_id"))
            rules_for_record.append(rules_by_id[rule_id])
            exception = exceptions_by_key.get((record_id, rule_id))
            if exception is not None:
                exceptions_for_record[rule_id] = exception
                consumed_exceptions += 1
        effective = resolve_ena_effective_trim(
            record_id=record_id,
            rules_for_record=rules_for_record,
            exceptions_for_record=exceptions_for_record,
        )
        five_motif = ""
        three_motif = ""
        if effective is not None:
            group_id = effective.group_id
            if effective.five_nt:
                five_motif = motifs.get((group_id, "five_prime"), "")
                if not five_motif:
                    raise EnaCheckpoint1ApplyError(
                        f"Missing derived 5′ motif for {record_id!r}"
                    )
            if effective.three_nt:
                three_motif = motifs.get((group_id, "three_prime"), "")
                if not three_motif:
                    raise EnaCheckpoint1ApplyError(
                        f"Missing derived 3′ motif for {record_id!r}"
                    )
        applied.append(
            apply_ena_reviewed_record(
                canonical=canonical,
                review_row=review_row,
                source_metadata=source_metadata_by_id[record_id],
                s2_qc=s2_qc_by_id[record_id],
                policy=policy,
                proposals=list(proposals_by_record.get(record_id, ())),
                effective=effective,
                five_motif=five_motif,
                three_motif=three_motif,
                construct_review_resolved=True,
                original_decision=original_decision,
            )
        )
    if consumed_exceptions != len(exception_rows):
        raise EnaCheckpoint1ApplyError(
            "Not every record-level exception was consumed: "
            f"{consumed_exceptions} vs {len(exception_rows)}"
        )
    consumption = {
        "record_decisions": len(queue_rows),
        "group_rules": len(rule_rows),
        "exceptions": len(exception_rows),
        "reconciliation": recon_consumed,
        "bulk_confirmed": 1 if _truthy((bulk_confirmation or {}).get("confirm", "")) else 0,
        "retained_collapse_members": len(retained_ids),
        "transformed_records": len(applied),
        "unresolved_exceptions_after_review": 0,
    }
    return applied, report, consumption


def _derive_cause(
    *,
    trimmed: bool,
    trim_rejected: bool,
    route_changed: bool,
) -> str:
    if trimmed:
        return "trim"
    if trim_rejected and route_changed:
        return "rejected trim"
    if route_changed:
        return "recompute"
    return "keep current"


def simulate_ena_checkpoint1_application(
    *,
    queue_rows: Sequence[Mapping[str, str]],
    rule_rows: Sequence[Mapping[str, str]],
    exception_rows: Sequence[Mapping[str, str]],
    reconciliation_rows: Sequence[Mapping[str, str]],
    canonical_rows: Sequence[Mapping[str, str]],
    decision_rows: Sequence[Mapping[str, str]],
    source_metadata_by_id: Mapping[str, Mapping[str, str]],
    s2_qc_by_id: Mapping[str, Mapping[str, str]],
    policy: EligibilityPolicy,
    membership_rows: Sequence[Mapping[str, str]] = (),
    proposals_by_record: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
    bulk_confirmation: Mapping[str, str] | None = None,
    existing_rejection_rows: Sequence[Mapping[str, str]] = (),
    existing_parked_construct: Sequence[Mapping[str, str]] = (),
    expected_total_rows: int | None = 679,
) -> EnaDryRunSimulation:
    """Apply reviewed records in memory and merge onto the full ENA set."""
    if len(canonical_rows) != len(decision_rows):
        raise EnaCheckpoint1ApplyError(
            "Canonical and decision sidecars must have the same row count"
        )
    if expected_total_rows is not None and len(canonical_rows) != expected_total_rows:
        raise EnaCheckpoint1ApplyError(
            f"Dry-run canonical must have {expected_total_rows} rows; "
            f"got {len(canonical_rows)}"
        )
    canonical_by_id = {row["record_id"]: row for row in canonical_rows}
    decision_by_id = {row["record_id"]: row for row in decision_rows}
    if len(canonical_by_id) != len(canonical_rows):
        raise EnaCheckpoint1ApplyError("Duplicate canonical record_id")
    existing_rejections = {row["record_id"]: row for row in existing_rejection_rows}
    existing_parks = {row["record_id"]: row for row in existing_parked_construct}

    applied, _report, consumption = apply_ena_checkpoint1_package(
        queue_rows=queue_rows,
        rule_rows=rule_rows,
        exception_rows=exception_rows,
        reconciliation_rows=reconciliation_rows,
        canonical_by_id=canonical_by_id,
        decision_by_id=decision_by_id,
        source_metadata_by_id=source_metadata_by_id,
        s2_qc_by_id=s2_qc_by_id,
        policy=policy,
        membership_rows=membership_rows,
        proposals_by_record=proposals_by_record,
        bulk_confirmation=bulk_confirmation,
    )
    applied_by_id = {item.record_id: item for item in applied}
    if set(canonical_by_id) - set(canonical_by_id):
        raise EnaCheckpoint1ApplyError("Source record disappeared during apply")

    queue_by_id = {row["record_id"]: row for row in queue_rows}
    preview_canonical: list[dict[str, str]] = []
    preview_decisions: list[dict[str, str]] = []
    preview_rejections: list[dict[str, str]] = []
    preview_parked: list[dict[str, str]] = []
    preview_eligible: list[dict[str, str]] = []
    change_report: list[dict[str, str]] = []
    route_changed: list[str] = []
    n_trimmed = 0
    n_five_only = 0
    n_three_only = 0
    n_both = 0
    n_group = 0
    n_record = 0
    n_no_trim = 0
    transitions: Counter[tuple[str, str]] = Counter()

    for original_canonical, original_decision in zip(
        canonical_rows, decision_rows, strict=True
    ):
        record_id = original_canonical["record_id"]
        original_raw = original_canonical["sequence_raw"]
        applied_row = applied_by_id.get(record_id)
        if applied_row is None:
            canonical = _corpus_only(original_canonical)
            decision = _row(DECISION_COLUMNS, original_decision)
            rejection = existing_rejections.get(record_id)
            park = existing_parks.get(record_id)
            route = decision["primary_route"]
            transitions[(original_decision.get("primary_route", ""), route)] += 1
        else:
            canonical = _corpus_only(applied_row.canonical)
            if canonical["sequence_raw"] != original_raw:
                raise EnaCheckpoint1ApplyError(
                    f"Dry-run mutated sequence_raw for {record_id!r}"
                )
            if not applied_row.decision:
                raise EnaCheckpoint1ApplyError(
                    f"Missing post-review decision for {record_id!r}"
                )
            decision = _row(DECISION_COLUMNS, applied_row.decision)
            decision["notes"] = applied_row.notes
            rejection = applied_row.rejection_row
            park = applied_row.park_row
            route = applied_row.primary_route_after
            review = queue_by_id.get(record_id, {})
            if applied_row.primary_route_after != applied_row.primary_route_before:
                route_changed.append(record_id)
            trimmed = bool(
                applied_row.applied_trim_5p_nt or applied_row.applied_trim_3p_nt
            )
            if trimmed:
                n_trimmed += 1
                if applied_row.applied_trim_5p_nt and applied_row.applied_trim_3p_nt:
                    n_both += 1
                elif applied_row.applied_trim_5p_nt:
                    n_five_only += 1
                else:
                    n_three_only += 1
                if applied_row.trim_source == "group":
                    n_group += 1
                elif applied_row.trim_source == "record":
                    n_record += 1
            else:
                n_no_trim += 1
            transitions[
                (applied_row.primary_route_before, applied_row.primary_route_after)
            ] += 1
            if (
                canonical["sequence_full"]
                and canonical["sequence_core"]
                and canonical["sequence_core"] not in canonical["sequence_full"]
            ):
                raise EnaCheckpoint1ApplyError(
                    f"sequence_core is not a substring of sequence_full for "
                    f"{record_id!r}"
                )
            trim_rejected = (
                _blank(review.get("manual_trim_action")) == "reject"
                or "no_additional_trim" in applied_row.notes
            )
            change_report.append(
                {
                    "record_id": record_id,
                    "pre_review_route": applied_row.primary_route_before,
                    "post_review_route": applied_row.primary_route_after,
                    "manual_decision": review.get("manual_decision", "") or "keep",
                    "trim_action": (
                        review.get("manual_trim_action", "")
                        or (
                            "approve/override"
                            if trimmed
                            else ("reject" if trim_rejected else "")
                        )
                    ),
                    "trim_5p_nt": str(applied_row.applied_trim_5p_nt) if trimmed else "",
                    "trim_3p_nt": str(applied_row.applied_trim_3p_nt) if trimmed else "",
                    "trim_source": applied_row.trim_source,
                    "pre_core_length": original_canonical.get("sequence_length_core", ""),
                    "post_core_length": canonical.get("sequence_length_core", ""),
                    "route_changed": (
                        "true"
                        if applied_row.primary_route_after
                        != applied_row.primary_route_before
                        else "false"
                    ),
                    "primary_reason_before": original_decision.get("primary_reason", ""),
                    "primary_reason_after": decision.get("primary_reason", ""),
                    "rejection_reason_before": existing_rejections.get(record_id, {}).get(
                        "rejection_reason", ""
                    ),
                    "rejection_reason_after": (rejection or {}).get("rejection_reason", ""),
                    "large_trim_human_approved": (
                        "true" if applied_row.large_trim_human_approved else "false"
                    ),
                    "cause": _derive_cause(
                        trimmed=trimmed,
                        trim_rejected=trim_rejected,
                        route_changed=(
                            applied_row.primary_route_after
                            != applied_row.primary_route_before
                        ),
                    ),
                }
            )

        for field_name in S3_FORBIDDEN_FIELDS:
            if canonical.get(field_name, ""):
                raise EnaCheckpoint1ApplyError(
                    f"Dry-run populated S4 field {field_name!r} for {record_id!r}"
                )
        preview_canonical.append(canonical)
        preview_decisions.append(decision)
        if route == PRIMARY_ROUTE_REJECT:
            if rejection is None:
                raise EnaCheckpoint1ApplyError(
                    f"technical_reject missing rejection row for {record_id!r}"
                )
            preview_rejections.append(_row(REJECTION_COLUMNS, rejection))
        elif route == PRIMARY_ROUTE_CONSTRUCT:
            if park is None:
                raise EnaCheckpoint1ApplyError(
                    f"parked_construct_review missing park row for {record_id!r}"
                )
            preview_parked.append(_row(PARK_COLUMNS, park))
        elif route == PRIMARY_ROUTE_ELIGIBLE:
            preview_eligible.append(_row(ELIGIBLE_PREVIEW_COLUMNS, decision))
        else:
            raise EnaCheckpoint1ApplyError(
                f"Unknown primary_route {route!r} for {record_id!r}"
            )

    if len(preview_canonical) != len(canonical_rows):
        raise EnaCheckpoint1ApplyError("A source record disappeared during dry-run")
    preview_ids = [row["record_id"] for row in preview_canonical]
    if preview_ids != [row["record_id"] for row in canonical_rows]:
        raise EnaCheckpoint1ApplyError("Dry-run reordered or dropped source identities")

    routes = [row["primary_route"] for row in preview_decisions]
    eligible_n = sum(1 for route in routes if route == PRIMARY_ROUTE_ELIGIBLE)
    parked_n = sum(1 for route in routes if route == PRIMARY_ROUTE_CONSTRUCT)
    reject_n = sum(1 for route in routes if route == PRIMARY_ROUTE_REJECT)
    if eligible_n + parked_n + reject_n != len(canonical_rows):
        raise EnaCheckpoint1ApplyError("Preview routes do not reconcile to 679/total")
    if len(preview_eligible) != eligible_n:
        raise EnaCheckpoint1ApplyError("Eligible preview count mismatch")
    if len(preview_parked) != parked_n:
        raise EnaCheckpoint1ApplyError("Parked preview count mismatch")
    if len(preview_rejections) != reject_n:
        raise EnaCheckpoint1ApplyError("Rejection preview count mismatch")

    membership_group_by_record = {
        _blank(row.get("record_id")): _blank(row.get("experiment_group_id"))
        for row in membership_rows
        if _blank(row.get("record_id"))
    }
    large_trim_records = [
        {
            "record_id": item.record_id,
            "experiment_group_id": (
                item.decision.get("constant_group_id", "")
                or membership_group_by_record.get(item.record_id, "")
            ),
            "trim_source": item.trim_source,
            "human_trim_action": "approve/override",
            "full_length": str(item.sequence_length_full),
            "trim_5p_nt": str(item.applied_trim_5p_nt),
            "trim_3p_nt": str(item.applied_trim_3p_nt),
            "trim_fraction": f"{item.trim_fraction:.6f}",
            "trim_pct": f"{item.trim_fraction * 100:.2f}",
            "core_length": str(item.sequence_length_core),
            "authorisation": "CHECKPOINT-1",
            "large_trim_human_approved": "true",
            "pre_review_route": item.primary_route_before,
            "post_review_route": item.primary_route_after,
            "route_changed": (
                "true"
                if item.primary_route_after != item.primary_route_before
                else "false"
            ),
        }
        for item in applied
        if item.large_trim_human_approved
    ]

    group_summaries = _ena_group_summaries(
        rule_rows=rule_rows,
        membership_rows=membership_rows,
        applied_by_id=applied_by_id,
        exception_rows=exception_rows,
    )
    cassette_ids = _cassette_record_ids(applied)
    cassette_cores = sorted(
        applied_by_id[record_id].sequence_length_core for record_id in cassette_ids
    )
    short_after = [
        row
        for row in preview_decisions
        if row.get("primary_route") == PRIMARY_ROUTE_REJECT
        and row.get("primary_reason") == "length_out_of_range"
    ]
    promoter_ids = [
        row["record_id"]
        for row in queue_rows
        if _truthy(row.get("source_promoter_or_template_concern"))
    ]
    ngf_ids = _rejected_group_record_ids(rule_rows, membership_rows)
    collapse_ids = []
    for row in reconciliation_rows:
        collapse_ids.extend(
            [
                _blank(row.get("record_id_a")),
                _blank(row.get("record_id_b")),
            ]
        )
    collapse_ids = [record_id for record_id in collapse_ids if record_id]

    stats: dict[str, int | str | bool | float] = {
        "total_records": len(canonical_rows),
        "transformed_records": len(applied),
        "record_decisions_consumed": consumption["record_decisions"],
        "group_rules_consumed": consumption["group_rules"],
        "exceptions_consumed": consumption["exceptions"],
        "reconciliation_consumed": consumption["reconciliation"],
        "bulk_confirmation_consumed": consumption["bulk_confirmed"],
        "unresolved_after_consumption": 0,
        "unresolved_exceptions_after_review": 0,
        "records_trimmed": n_trimmed,
        "trimmed_5p_only": n_five_only,
        "trimmed_3p_only": n_three_only,
        "trimmed_both_ends": n_both,
        "trimmed_by_group": n_group,
        "trimmed_by_record_override": n_record,
        "no_trim_decisions": n_no_trim,
        "exact_terminal_failures": 0,
        "core_below_20_failures": 0,
        "overlapping_trim_failures": 0,
        "large_trim_human_approved": len(large_trim_records),
        "guard_rail_failures": 0,
        "technically_eligible": eligible_n,
        "parked_construct_review": parked_n,
        "technical_rejects": reject_n,
        "route_changed": len(route_changed),
        "human_drops": 0,
        "authorised_for_s4": 0,
        "checkpoint_closed": False,
        "preview_complete": True,
        "s4_fields_populated": 0,
        "short_length_rejects": len(short_after),
        "promoter_records": len(promoter_ids),
        "promoter_eligible": sum(
            1
            for record_id in promoter_ids
            if applied_by_id.get(record_id) is not None
            and applied_by_id[record_id].primary_route_after == PRIMARY_ROUTE_ELIGIBLE
        ),
        "cassette_records": len(cassette_ids),
        "cassette_both_end_trims": sum(
            1
            for record_id in cassette_ids
            if applied_by_id[record_id].applied_trim_5p_nt
            and applied_by_id[record_id].applied_trim_3p_nt
        ),
        "cassette_core_min": cassette_cores[0] if cassette_cores else 0,
        "cassette_core_median": (
            statistics.median(cassette_cores) if cassette_cores else 0
        ),
        "cassette_core_max": cassette_cores[-1] if cassette_cores else 0,
        "ngf_records": len(ngf_ids),
        "ngf_untrimmed": sum(
            1
            for record_id in ngf_ids
            if applied_by_id.get(record_id) is not None
            and applied_by_id[record_id].applied_trim_5p_nt == 0
            and applied_by_id[record_id].applied_trim_3p_nt == 0
            and applied_by_id[record_id].sequence_core
            == applied_by_id[record_id].sequence_full
        ),
        "ngf_eligible": sum(
            1
            for record_id in ngf_ids
            if applied_by_id.get(record_id) is not None
            and applied_by_id[record_id].primary_route_after == PRIMARY_ROUTE_ELIGIBLE
        ),
        "collapse_members": len(collapse_ids),
        "collapse_retained": sum(
            1 for record_id in collapse_ids if record_id in canonical_by_id
        ),
        "accept_to_accept": transitions[(PRIMARY_ROUTE_ELIGIBLE, PRIMARY_ROUTE_ELIGIBLE)],
        "park_to_accept": transitions[(PRIMARY_ROUTE_CONSTRUCT, PRIMARY_ROUTE_ELIGIBLE)],
        "park_to_park": transitions[(PRIMARY_ROUTE_CONSTRUCT, PRIMARY_ROUTE_CONSTRUCT)],
        "park_to_reject": transitions[(PRIMARY_ROUTE_CONSTRUCT, PRIMARY_ROUTE_REJECT)],
        "reject_to_reject": transitions[(PRIMARY_ROUTE_REJECT, PRIMARY_ROUTE_REJECT)],
        "reject_to_accept": transitions[(PRIMARY_ROUTE_REJECT, PRIMARY_ROUTE_ELIGIBLE)],
        "korean_exception_records": sum(
            1
            for row in exception_rows
            if _blank(row.get("manual_trim_action")) == "override"
        ),
        "ngf_exception_records": sum(
            1
            for row in exception_rows
            if _blank(row.get("manual_trim_action")) == "reject"
        ),
    }
    return EnaDryRunSimulation(
        preview_canonical=preview_canonical,
        preview_decisions=preview_decisions,
        preview_rejections=preview_rejections,
        preview_parked_construct=preview_parked,
        preview_eligible=preview_eligible,
        change_report=change_report,
        group_summaries=group_summaries,
        applied=applied,
        route_changed_ids=tuple(route_changed),
        large_trim_records=large_trim_records,
        stats=stats,
    )


def _cassette_record_ids(applied: Sequence[AppliedRecordResult]) -> tuple[str, ...]:
    return tuple(
        item.record_id
        for item in applied
        if item.applied_trim_5p_nt and item.applied_trim_3p_nt
    )


def _rejected_group_record_ids(
    rule_rows: Sequence[Mapping[str, str]],
    membership_rows: Sequence[Mapping[str, str]],
) -> tuple[str, ...]:
    rejected_groups = {
        _blank(row.get("experiment_group_id"))
        for row in rule_rows
        if _blank(row.get("manual_trim_action")) == "reject"
    }
    ids = [
        _blank(row.get("record_id"))
        for row in membership_rows
        if _blank(row.get("experiment_group_id")) in rejected_groups
    ]
    return tuple(sorted({record_id for record_id in ids if record_id}))


def _ena_group_summaries(
    *,
    rule_rows: Sequence[Mapping[str, str]],
    membership_rows: Sequence[Mapping[str, str]],
    applied_by_id: Mapping[str, AppliedRecordResult],
    exception_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    members_by_rule: dict[str, list[str]] = defaultdict(list)
    for row in membership_rows:
        rule_id = _blank(row.get("constant_rule_id") or row.get("proposal_id"))
        record_id = _blank(row.get("record_id"))
        if rule_id and record_id:
            members_by_rule[rule_id].append(record_id)
    exceptions_by_rule: dict[str, list[str]] = defaultdict(list)
    for row in exception_rows:
        exceptions_by_rule[
            _blank(row.get("constant_rule_id") or row.get("proposal_id"))
        ].append(_blank(row.get("record_id")))
    summaries: list[dict[str, str]] = []
    for rule in rule_rows:
        rule_id = _blank(rule.get("constant_rule_id"))
        members = members_by_rule.get(rule_id, [])
        cores: list[int] = []
        trimmed = 0
        large = 0
        changed = 0
        applied_nt = ""
        for record_id in members:
            item = applied_by_id.get(record_id)
            if item is None:
                continue
            cores.append(item.sequence_length_core)
            side = _blank(rule.get("side"))
            nt = (
                item.applied_trim_5p_nt
                if side == "five_prime"
                else item.applied_trim_3p_nt
            )
            if nt:
                trimmed += 1
                applied_nt = str(nt)
            if item.large_trim_human_approved:
                large += 1
            if item.primary_route_after != item.primary_route_before:
                changed += 1
        cores_sorted = sorted(cores)
        summaries.append(
            {
                "constant_rule_id": rule_id,
                "experiment_group_id": rule.get("experiment_group_id", ""),
                "side": rule.get("side", ""),
                "manual_trim_action": rule.get("manual_trim_action", ""),
                "applied_nt": applied_nt,
                "n_linked_records": str(len(members)),
                "n_trimmed": str(trimmed),
                "n_large_trim_human_approved": str(large),
                "core_length_min": str(cores_sorted[0]) if cores_sorted else "",
                "core_length_median": (
                    str(statistics.median(cores_sorted)) if cores_sorted else ""
                ),
                "core_length_max": str(cores_sorted[-1]) if cores_sorted else "",
                "guard_rail_failures": "0",
                "n_route_changed": str(changed),
                "record_exceptions": "|".join(
                    record_id
                    for record_id in exceptions_by_rule.get(rule_id, [])
                    if record_id
                ),
            }
        )
    return summaries


def serialise_ena_simulation(simulation: EnaDryRunSimulation) -> bytes:
    chunks = [
        json.dumps(simulation.preview_canonical, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_decisions, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.preview_rejections, sort_keys=True, ensure_ascii=True),
        json.dumps(
            simulation.preview_parked_construct, sort_keys=True, ensure_ascii=True
        ),
        json.dumps(simulation.preview_eligible, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.change_report, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.group_summaries, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.guard_rail_failure_rows, sort_keys=True, ensure_ascii=True),
        json.dumps(simulation.large_trim_records, sort_keys=True, ensure_ascii=True),
    ]
    return "\n".join(chunks).encode("utf-8")


def format_dry_run_markdown(
    simulation: EnaDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
) -> str:
    stats = simulation.stats
    lines = [
        "# ENA CHECKPOINT-1 application dry-run",
        "",
        DRY_RUN_BANNER,
        "",
        "Human decisions were simulated through the real apply transformation.",
        "Canonical S2/S3 outputs were not rewritten. CHECKPOINT-1 is not closed.",
        "No record is authorised for S4. Global S4 has not been run.",
        "",
        "## Review consumption",
        "",
        f"- record decisions consumed: `{stats['record_decisions_consumed']}`",
        f"- group rules consumed: `{stats['group_rules_consumed']}`",
        f"- exceptions consumed: `{stats['exceptions_consumed']}`",
        f"- reconciliation decisions consumed: `{stats['reconciliation_consumed']}`",
        f"- bulk confirmation consumed: `{stats['bulk_confirmation_consumed']}`",
        f"- unresolved after consumption: `{stats['unresolved_after_consumption']}`",
        f"- unresolved trim exceptions after review: "
        f"`{stats['unresolved_exceptions_after_review']}`",
        "",
        "## Frozen review hashes",
        "",
    ]
    for name, digest in review_hashes.items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Trim application preview",
            "",
            f"- total records trimmed: `{stats['records_trimmed']}`",
            f"- 5′ only: `{stats['trimmed_5p_only']}`",
            f"- 3′ only: `{stats['trimmed_3p_only']}`",
            f"- both ends: `{stats['trimmed_both_ends']}`",
            f"- group-approved/overridden: `{stats['trimmed_by_group']}`",
            f"- record-exception overrides: `{stats['trimmed_by_record_override']}`",
            f"- no-trim decisions (transformed, untrimmed): `{stats['no_trim_decisions']}`",
            f"- exact-terminal failures: `{stats['exact_terminal_failures']}`",
            f"- core <20 failures: `{stats['core_below_20_failures']}`",
            f"- overlapping trim failures: `{stats['overlapping_trim_failures']}`",
            f"- >40% human-approved records: `{stats['large_trim_human_approved']}`",
            f"- remaining guard-rail blockers: `{stats['guard_rail_failures']}`",
            "",
            "## Routing",
            "",
            f"- post-review technically eligible: `{stats['technically_eligible']}`",
            f"- post-review parked: `{stats['parked_construct_review']}`",
            f"- post-review rejected: `{stats['technical_rejects']}`",
            f"- total: `{stats['total_records']}`",
            f"- human drops: `{stats['human_drops']}`",
            "",
            "## Transition matrix",
            "",
            f"- accept → accept: `{stats['accept_to_accept']}`",
            f"- park → accept: `{stats['park_to_accept']}`",
            f"- park → park: `{stats['park_to_park']}`",
            f"- park → reject: `{stats['park_to_reject']}`",
            f"- reject → reject: `{stats['reject_to_reject']}`",
            f"- reject → accept: `{stats['reject_to_accept']}`",
            "",
            "## Short cohort",
            "",
            f"- length_out_of_range rejects: `{stats['short_length_rejects']}`",
            "",
            "## Promoter/template cohort",
            "",
            f"- records: `{stats['promoter_records']}`",
            f"- technically eligible after resolved no-trim: `{stats['promoter_eligible']}`",
            "",
            "## Both-end reviewed cassette",
            "",
            f"- records: `{stats['cassette_records']}`",
            f"- both-end trims: `{stats['cassette_both_end_trims']}`",
            f"- core min/median/max: `{stats['cassette_core_min']}` / "
            f"`{stats['cassette_core_median']}` / `{stats['cassette_core_max']}`",
            f"- >40% human-approved (all transformed large trims): "
            f"`{stats['large_trim_human_approved']}`",
            "",
            "## Rejected group-trim cohort",
            "",
            f"- records: `{stats['ngf_records']}`",
            f"- untrimmed (core=full): `{stats['ngf_untrimmed']}`",
            f"- technically eligible: `{stats['ngf_eligible']}`",
            "",
            "## Legacy collapse reconciliation",
            "",
            f"- members: `{stats['collapse_members']}`",
            f"- retained: `{stats['collapse_retained']}`",
            "- no deduplication performed",
            "",
            "## S4 fields",
            "",
            f"- populated S4/forbidden fields: `{stats['s4_fields_populated']}`",
            "",
            "## Integrity",
            "",
        ]
    )
    for name, digest in integrity.items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Status",
            "",
            "- mode: dry-run / non-authoritative",
            "- CHECKPOINT-1 remains open and unapplied",
            "- global S4 has not been run",
        ]
    )
    return "\n".join(lines) + "\n"


def count_manual_decisions(queue_rows: Sequence[Mapping[str, str]]) -> dict[str, int]:
    counts = Counter((row.get("manual_decision") or "").strip() for row in queue_rows)
    return {key: int(counts.get(key, 0)) for key in ("keep", "edit", "drop")}


def resolution_status_for_route(route: str) -> str:
    if route not in ROUTE_TO_STATUS:
        raise EnaCheckpoint1ApplyError(f"Unknown primary_route {route!r}")
    return ROUTE_TO_STATUS[route]


def build_tracked_resolutions(
    *,
    decisions: Sequence[Mapping[str, str]],
    queue_rows: Sequence[Mapping[str, str]],
    route_changed_ids: Sequence[str],
) -> list[dict[str, str]]:
    """Sequence-free CHECKPOINT-1 resolution rows for tracked audit."""
    review_by_id = {row["record_id"]: row for row in queue_rows}
    changed = set(route_changed_ids)
    rows: list[dict[str, str]] = []
    for decision in decisions:
        record_id = decision["record_id"]
        route = decision["primary_route"]
        authorised = route == PRIMARY_ROUTE_ELIGIBLE
        if authorised:
            resolved = "accept"
        elif route == PRIMARY_ROUTE_REJECT:
            resolved = "reject"
        else:
            resolved = "park"
        rows.append(
            {
                "record_id": record_id,
                "native_id": decision.get("native_id", ""),
                "primary_route": route,
                "proposed_decision": decision.get("proposed_decision", ""),
                "resolved_decision": resolved,
                "primary_reason": decision.get("primary_reason", ""),
                "checkpoint1_resolution_status": resolution_status_for_route(route),
                "authorised_for_s4": "true" if authorised else "false",
                "manual_decision": review_by_id.get(record_id, {}).get(
                    "manual_decision", ""
                ),
                "route_changed": "true" if record_id in changed else "false",
            }
        )
    return rows


def format_closure_markdown(
    simulation: EnaDryRunSimulation,
    *,
    review_hashes: Mapping[str, str],
    integrity: Mapping[str, str],
    output_hashes: Mapping[str, str],
    record_decisions: Mapping[str, int],
    deterministic_ok: bool,
    preview_comparison_ok: bool,
    semantic_mismatches: int,
) -> str:
    stats = simulation.stats
    lines = [
        "# ENA CHECKPOINT-1 closure",
        "",
        ENA_CHECKPOINT_CLOSED_STATEMENT,
        "",
        "Frozen human CHECKPOINT-1 decisions were applied through the",
        "fail-closed `apply_ena_reviewed_record` path used by the accepted",
        "dry-run. Pre-review S2/S3 snapshots were not overwritten. S4 was",
        "not started. An ENA global-S4 source handoff was not prepared.",
        "",
        "## Review inputs",
        "",
    ]
    for name, digest in review_hashes.items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Human decisions",
            "",
            f"- record decisions consumed: `{stats['record_decisions_consumed']}`",
            f"- keep: `{record_decisions.get('keep', 0)}`",
            f"- edit: `{record_decisions.get('edit', 0)}`",
            f"- drop: `{record_decisions.get('drop', 0)}`",
            f"- group rules consumed: `{stats['group_rules_consumed']}`",
            f"- exceptions consumed: `{stats['exceptions_consumed']}`",
            f"- reconciliation groups consumed: `{stats['reconciliation_consumed']}`",
            f"- unresolved after consumption: `{stats['unresolved_after_consumption']}`",
            "",
            "## Routing reconciliation",
            "",
            f"- total source records: `{stats['total_records']}`",
            f"- technically eligible: `{stats['technically_eligible']}`",
            f"- parked construct review: `{stats['parked_construct_review']}`",
            f"- technical rejects: `{stats['technical_rejects']}`",
            f"- authorised for a future global-S4 handoff: "
            f"`{stats['authorised_for_s4']}`",
            "",
            AUTHORISED_FOR_S4_MEANING,
            "",
            "## Transition matrix",
            "",
            f"- accept → accept: `{stats['accept_to_accept']}`",
            f"- park → accept: `{stats['park_to_accept']}`",
            f"- park → park: `{stats['park_to_park']}`",
            f"- park → reject: `{stats['park_to_reject']}`",
            f"- reject → reject: `{stats['reject_to_reject']}`",
            f"- reject → accept: `{stats['reject_to_accept']}`",
            "",
            "## Reviewed trims",
            "",
            f"- total records trimmed: `{stats['records_trimmed']}`",
            f"- 5′ only: `{stats['trimmed_5p_only']}`",
            f"- 3′ only: `{stats['trimmed_3p_only']}`",
            f"- both ends: `{stats['trimmed_both_ends']}`",
            f"- large_trim_human_approved: `{stats['large_trim_human_approved']}`",
            f"- guard-rail failures: `{stats['guard_rail_failures']}`",
            "",
            "## Korean cassette cohort",
            "",
            f"- records: `{stats['cassette_records']}`",
            f"- both-end trims: `{stats['cassette_both_end_trims']}`",
            f"- core min/median/max: `{stats['cassette_core_min']}` / "
            f"`{stats['cassette_core_median']}` / `{stats['cassette_core_max']}`",
            "",
            "## NGF / rejected-group-trim cohort",
            "",
            f"- records: `{stats['ngf_records']}`",
            f"- untrimmed (core=full): `{stats['ngf_untrimmed']}`",
            f"- technically eligible: `{stats['ngf_eligible']}`",
            "",
            "## Promoter/template cohort",
            "",
            f"- records: `{stats['promoter_records']}`",
            f"- technically eligible after resolved no-trim: "
            f"`{stats['promoter_eligible']}`",
            "",
            "## Short cohort",
            "",
            f"- length_out_of_range rejects: `{stats['short_length_rejects']}`",
            "",
            "## Legacy collapse reconciliation",
            "",
            f"- members: `{stats['collapse_members']}`",
            f"- retained: `{stats['collapse_retained']}`",
            "- no deduplication performed",
            "",
            "## Integrity",
            "",
            f"- raw SHA-256: `{integrity.get('raw', '')}`",
            f"- S1 SHA-256: `{integrity.get('s1', '')}`",
            f"- sidecar SHA-256: `{integrity.get('sidecar', '')}`",
            f"- S2 SHA-256: `{integrity.get('s2', '')}`",
            f"- pre-review S3 SHA-256: `{integrity.get('s3', '')}`",
            f"- dry-run/apply parity: "
            f"`{'true' if preview_comparison_ok else 'false'}`",
            f"- scientific/semantic mismatches: `{semantic_mismatches}`",
            f"- deterministic rerun: `{'true' if deterministic_ok else 'false'}`",
            f"- populated S4/forbidden fields: `{stats['s4_fields_populated']}`",
            "",
            "## Output hashes",
            "",
        ]
    )
    for name, digest in output_hashes.items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Next stage",
            "",
            "CHECKPOINT-1 is closed. Global S4 has not been run. An ENA",
            "global-S4 source handoff has not been prepared. The next",
            "milestone is to review this closure and, only if accepted,",
            "prepare a future global-S4 handoff as a separate milestone.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"

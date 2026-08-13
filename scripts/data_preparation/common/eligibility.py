"""Generic eligibility decision types and leakage helpers for S3.

Defines proposed accept/park/reject decisions, reason codes, sequence- and
target-level evaluation-leakage matching, and shared policy loading. Does not
perform target normalisation, UniProt mapping, evidence scoring, affinity
interpretation, deduplication, clustering, balancing or partitioning.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, Sequence

from common.leakage_matching import (
    LeakageMatchingError,
    comparison_form,
    global_edit_identity,
)

REASON_DELIMITER: Final[str] = "|"
CHECKPOINT_STATUS_PENDING: Final[str] = "pending_checkpoint_1_review"

ALLOWED_DECISIONS: Final[frozenset[str]] = frozenset(
    {
        "proposed_accept",
        "proposed_park",
        "proposed_reject",
    }
)

ALLOWED_MATCH_TYPES: Final[frozenset[str]] = frozenset(
    {
        "exact_alias",
        "normalised_alias",
        "family_pattern",
    }
)

REVIEW_PRIORITY_ORDER: Final[tuple[str, ...]] = ("high", "medium", "low", "none")
DECISION_REVIEW_ORDER: Final[tuple[str, ...]] = (
    "proposed_park",
    "proposed_reject",
    "proposed_accept",
)

_HYPHEN_VARIANTS_RE = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\-]+")
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\sβΒ]", re.UNICODE)
_NON_WORD_BOUNDARY = r"[^\wβΒ]"


class EligibilityError(ValueError):
    """Invalid eligibility policy, leakage input, or decision construction."""


class EligibilityDecision(str, Enum):
    """Closed vocabulary of provisional S3 decisions."""

    PROPOSED_ACCEPT = "proposed_accept"
    PROPOSED_PARK = "proposed_park"
    PROPOSED_REJECT = "proposed_reject"


class EligibilityReason(str, Enum):
    """Closed vocabulary of deterministic eligibility reason codes."""

    EVALUATION_SEQUENCE_LEAKAGE = "evaluation_sequence_leakage"
    EVALUATION_TARGET_LEAKAGE = "evaluation_target_leakage"
    MISSING_SEQUENCE = "missing_sequence"
    SOURCE_RECORD_INVALID = "source_record_invalid"
    CORE_BELOW_MINIMUM = "core_below_minimum"
    INVALID_SEQUENCE_REQUIRES_REVIEW = "invalid_sequence_requires_review"
    AMBIGUOUS_SEQUENCE_REQUIRES_REVIEW = "ambiguous_sequence_requires_review"
    MIXED_T_U_REQUIRES_REVIEW = "mixed_t_u_requires_review"
    TRIM_OR_CONSTRUCT_REQUIRES_REVIEW = "trim_or_construct_requires_review"
    CORE_ABOVE_MAXIMUM_REQUIRES_REVIEW = "core_above_maximum_requires_review"
    SSDNA_NOT_ELIGIBLE_FOR_RNA_TRAINING = "ssdna_not_eligible_for_rna_training"
    MOLECULE_TYPE_UNRESOLVED = "molecule_type_unresolved"
    MISSING_TARGET_REQUIRES_SOURCE_REVIEW = "missing_target_requires_source_review"
    TECHNICALLY_ELIGIBLE_RNA = "technically_eligible_rna"
    # Plan-aligned technical-eligibility reasons used by UTexas S3.
    # AptaBase continues to use the *_requires_review / ssdna_* names above.
    NON_RNA_MOLECULE = "non_rna_molecule"
    MIXED_T_AND_U = "mixed_T_and_U"
    AMBIGUOUS_BASES = "ambiguous_bases"
    INVALID_ALPHABET = "invalid_alphabet"
    ALIGNMENT_GAPS = "alignment_gaps"
    LENGTH_OUT_OF_RANGE = "length_out_of_range"
    TRIM_CONSTRUCT_UNRESOLVED = "trim_construct_unresolved"
    TRIM_PUSHED_LENGTH_OUT_OF_RANGE = "trim_pushed_length_out_of_range"
    TRIM_COMBINED_EXCEEDS_40PCT = "trim_combined_exceeds_40pct"
    MEDIUM_CONFIDENCE_TRIM = "medium_confidence_trim"
    LOWER_LENGTH_BOUNDARY = "lower_length_boundary"
    UPPER_LENGTH_BOUNDARY = "upper_length_boundary"
    RANDOM_ACCEPT_AUDIT = "random_accept_audit"


class ManualReviewPriority(str, Enum):
    """Review ordering priority; never overrides the proposed decision."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass(frozen=True)
class LeakageMatch:
    """Aggregate-safe sequence leakage match metadata (no sequences)."""

    matched_exclusion_id: str
    matched_reference_id: str
    matched_target: str
    matched_evaluation_role: str
    matched_form: str
    identity: float


@dataclass(frozen=True)
class TargetLeakageMatch:
    """Aggregate-safe raw-target leakage match metadata."""

    matched_canonical_target: str
    matched_alias: str
    match_type: str
    target_family: str


@dataclass(frozen=True)
class EligibilityResult:
    """Provisional eligibility outcome for one corpus record."""

    record_id: str
    proposed_decision: EligibilityDecision
    primary_reason: EligibilityReason
    all_reasons: tuple[EligibilityReason, ...]
    manual_review_required: bool
    manual_review_priority: ManualReviewPriority
    sequence_leakage_match: LeakageMatch | None
    target_leakage_match: TargetLeakageMatch | None
    checkpoint_status: str = CHECKPOINT_STATUS_PENDING

    @property
    def secondary_reasons(self) -> tuple[EligibilityReason, ...]:
        return tuple(r for r in self.all_reasons if r != self.primary_reason)


@dataclass(frozen=True)
class EligibilityPolicy:
    """Tracked source eligibility policy for S3 classification."""

    source_key: str
    contract_version: str
    decision_values: tuple[str, ...]
    decision_precedence: tuple[str, ...]
    core_length_min: int
    core_length_max: int
    missing_sequence_decision: str
    source_record_invalid_decision: str
    core_below_minimum_decision: str
    evaluation_leakage_decision: str
    invalid_sequence_decision: str
    ambiguous_sequence_decision: str
    mixed_t_u_decision: str
    trim_review_decision: str
    core_above_maximum_decision: str
    ssdna_decision: str
    unknown_molecule_decision: str
    missing_target_decision: str
    eligible_rna_decision: str
    sequence_identity_threshold: float
    target_leakage_matching_enabled: bool
    legacy_fields_are_diagnostic_only: bool
    checkpoint_requires_manual_approval: bool
    sequence_leakage_matching_enabled: bool = True
    explicit_non_rna_requires_manual_review: bool = True
    defer_target_classification: bool = False
    defer_evidence_scoring: bool = False
    defer_leakage_exclusion: bool = False
    use_plan_reason_vocabulary: bool = False
    length_out_of_range_decision: str = "proposed_reject"
    alignment_gaps_decision: str = "proposed_reject"
    non_rna_molecule_decision: str = "proposed_park"
    length_boundary_low_max: int = 25
    length_boundary_high_min: int = 90
    random_accept_audit_size: int = 0
    random_seed: int = 42
    review_model: str = "single_reviewer"
    reviewer_initials_required: bool = True
    reviewer_notes_required: bool = True
    active_review_batches: tuple[str, ...] = ()
    unresolved_trim_blocks_eligibility: bool = True


@dataclass(frozen=True)
class TargetAliasRule:
    """One configured raw-target leakage alias or family pattern."""

    canonical_target: str
    alias: str
    match_type: str
    target_family: str
    exclusion_reason: str
    notes: str
    normalised_alias: str
    exact_alias_folded: str


@dataclass(frozen=True)
class ExclusionReference:
    """One leakage-exclusion sequence row (comparison forms only in memory)."""

    exclusion_id: str
    reference_id: str
    target_name: str
    evaluation_role: str
    sequence_compare_full: str
    sequence_compare_core: str
    status: str


@dataclass
class SequenceLeakageIndex:
    """Loaded leakage-exclusion set for deterministic sequence matching."""

    references: tuple[ExclusionReference, ...] = ()

    def best_match(
        self,
        *,
        sequence_full: str,
        sequence_core: str,
        threshold: float,
    ) -> LeakageMatch | None:
        """Return the best sequence leakage match at or above ``threshold``."""
        query_forms: list[tuple[str, str]] = []
        for label, raw in (("full", sequence_full), ("core", sequence_core)):
            if not raw:
                continue
            try:
                query_forms.append((label, comparison_form(raw)))
            except LeakageMatchingError:
                continue
        if not query_forms:
            return None

        candidates: list[tuple[float, str, str, ExclusionReference]] = []
        for ref in self.references:
            exclusion_forms = (
                ("full", ref.sequence_compare_full),
                ("core", ref.sequence_compare_core),
            )
            for query_label, query_cmp in query_forms:
                for excl_label, excl_cmp in exclusion_forms:
                    if not excl_cmp:
                        continue
                    try:
                        identity = global_edit_identity(query_cmp, excl_cmp)
                    except LeakageMatchingError:
                        continue
                    if identity >= threshold:
                        form = f"{query_label}_vs_{excl_label}"
                        candidates.append((identity, form, ref.exclusion_id, ref))

        if not candidates:
            return None

        # Highest identity, then matched_form, then exclusion_id.
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        identity, matched_form, _eid, ref = candidates[0]
        return LeakageMatch(
            matched_exclusion_id=ref.exclusion_id,
            matched_reference_id=ref.reference_id,
            matched_target=ref.target_name,
            matched_evaluation_role=ref.evaluation_role,
            matched_form=matched_form,
            identity=identity,
        )


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EligibilityError(f"{name} must be a JSON object")
    return value


def _require_str_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EligibilityError(f"{name} must be a list of strings")
    return tuple(value)


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise EligibilityError(f"{name} must be a boolean")
    return value


def _require_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EligibilityError(f"{name} must be a number")
    return float(value)


def _require_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EligibilityError(f"{name} must be an integer")
    return value


def _optional_bool(data: Mapping[str, Any], name: str, default: bool) -> bool:
    if name not in data:
        return default
    return _require_bool(data.get(name), name)


def _optional_int(data: Mapping[str, Any], name: str, default: int) -> int:
    if name not in data:
        return default
    return _require_int(data.get(name), name)


def _optional_str(data: Mapping[str, Any], name: str, default: str) -> str:
    if name not in data:
        return default
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise EligibilityError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_decision(data: Mapping[str, Any], name: str, default: str) -> str:
    if name not in data:
        return default
    return _require_decision(data.get(name), name)


def _optional_str_list(
    data: Mapping[str, Any], name: str, default: tuple[str, ...]
) -> tuple[str, ...]:
    if name not in data:
        return default
    return _require_str_list(data.get(name), name)


def _require_decision(value: Any, name: str) -> str:
    text = str(value)
    if text not in ALLOWED_DECISIONS:
        raise EligibilityError(
            f"{name} has unknown decision value {text!r}; "
            f"allowed={sorted(ALLOWED_DECISIONS)}"
        )
    return text


def load_eligibility_policy(path: str | Path) -> EligibilityPolicy:
    """Load and validate a tracked source eligibility policy JSON."""
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EligibilityError(
            f"cannot read eligibility policy: {exc.strerror}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EligibilityError(
            f"eligibility policy JSON is invalid: {exc.msg}"
        ) from exc

    data = _require_mapping(payload, "eligibility policy")
    decision_values = _require_str_list(data.get("decision_values"), "decision_values")
    unknown = [value for value in decision_values if value not in ALLOWED_DECISIONS]
    if unknown:
        raise EligibilityError(
            f"decision_values contains unknown decision(s): {unknown}"
        )
    if set(decision_values) != ALLOWED_DECISIONS:
        raise EligibilityError(
            "decision_values must exactly contain proposed_accept, "
            "proposed_park and proposed_reject"
        )

    source_key = data.get("source_key")
    if not isinstance(source_key, str) or not source_key.strip():
        raise EligibilityError("source_key must be a non-empty string")
    contract_version = data.get("contract_version")
    if not isinstance(contract_version, str) or not contract_version.strip():
        raise EligibilityError("contract_version must be a non-empty string")

    return EligibilityPolicy(
        source_key=source_key.strip(),
        contract_version=contract_version.strip(),
        decision_values=decision_values,
        decision_precedence=_require_str_list(
            data.get("decision_precedence"), "decision_precedence"
        ),
        core_length_min=_require_int(data.get("core_length_min"), "core_length_min"),
        core_length_max=_require_int(data.get("core_length_max"), "core_length_max"),
        missing_sequence_decision=_require_decision(
            data.get("missing_sequence_decision"), "missing_sequence_decision"
        ),
        source_record_invalid_decision=_require_decision(
            data.get("source_record_invalid_decision"),
            "source_record_invalid_decision",
        ),
        core_below_minimum_decision=_require_decision(
            data.get("core_below_minimum_decision"), "core_below_minimum_decision"
        ),
        evaluation_leakage_decision=_require_decision(
            data.get("evaluation_leakage_decision"), "evaluation_leakage_decision"
        ),
        invalid_sequence_decision=_require_decision(
            data.get("invalid_sequence_decision"), "invalid_sequence_decision"
        ),
        ambiguous_sequence_decision=_require_decision(
            data.get("ambiguous_sequence_decision"), "ambiguous_sequence_decision"
        ),
        mixed_t_u_decision=_require_decision(
            data.get("mixed_t_u_decision"), "mixed_t_u_decision"
        ),
        trim_review_decision=_require_decision(
            data.get("trim_review_decision"), "trim_review_decision"
        ),
        core_above_maximum_decision=_require_decision(
            data.get("core_above_maximum_decision"), "core_above_maximum_decision"
        ),
        ssdna_decision=_require_decision(data.get("ssdna_decision"), "ssdna_decision"),
        unknown_molecule_decision=_require_decision(
            data.get("unknown_molecule_decision"), "unknown_molecule_decision"
        ),
        missing_target_decision=_require_decision(
            data.get("missing_target_decision"), "missing_target_decision"
        ),
        eligible_rna_decision=_require_decision(
            data.get("eligible_rna_decision"), "eligible_rna_decision"
        ),
        sequence_identity_threshold=_require_number(
            data.get("sequence_identity_threshold"), "sequence_identity_threshold"
        ),
        target_leakage_matching_enabled=_require_bool(
            data.get("target_leakage_matching_enabled"),
            "target_leakage_matching_enabled",
        ),
        legacy_fields_are_diagnostic_only=_require_bool(
            data.get("legacy_fields_are_diagnostic_only"),
            "legacy_fields_are_diagnostic_only",
        ),
        checkpoint_requires_manual_approval=_require_bool(
            data.get("checkpoint_requires_manual_approval"),
            "checkpoint_requires_manual_approval",
        ),
        sequence_leakage_matching_enabled=_optional_bool(
            data, "sequence_leakage_matching_enabled", True
        ),
        explicit_non_rna_requires_manual_review=_optional_bool(
            data, "explicit_non_rna_requires_manual_review", True
        ),
        defer_target_classification=_optional_bool(
            data, "defer_target_classification", False
        ),
        defer_evidence_scoring=_optional_bool(
            data, "defer_evidence_scoring", False
        ),
        defer_leakage_exclusion=_optional_bool(
            data, "defer_leakage_exclusion", False
        ),
        use_plan_reason_vocabulary=_optional_bool(
            data, "use_plan_reason_vocabulary", False
        ),
        length_out_of_range_decision=_optional_decision(
            data, "length_out_of_range_decision", "proposed_reject"
        ),
        alignment_gaps_decision=_optional_decision(
            data, "alignment_gaps_decision", "proposed_reject"
        ),
        non_rna_molecule_decision=_optional_decision(
            data, "non_rna_molecule_decision", "proposed_park"
        ),
        length_boundary_low_max=_optional_int(data, "length_boundary_low_max", 25),
        length_boundary_high_min=_optional_int(data, "length_boundary_high_min", 90),
        random_accept_audit_size=_optional_int(data, "random_accept_audit_size", 0),
        random_seed=_optional_int(data, "random_seed", 42),
        review_model=_optional_str(data, "review_model", "single_reviewer"),
        reviewer_initials_required=_optional_bool(
            data, "reviewer_initials_required", True
        ),
        reviewer_notes_required=_optional_bool(
            data, "reviewer_notes_required", True
        ),
        active_review_batches=_optional_str_list(
            data, "active_review_batches", ()
        ),
        unresolved_trim_blocks_eligibility=_optional_bool(
            data, "unresolved_trim_blocks_eligibility", True
        ),
    )


def format_identity(value: float) -> str:
    """Deterministic float serialisation for identity columns."""
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text if text else "0"


def format_reasons(reasons: Iterable[EligibilityReason | str]) -> str:
    """Join reason codes with the canonical delimiter in sorted order."""
    normalised: set[str] = set()
    for reason in reasons:
        if not reason:
            continue
        if isinstance(reason, EligibilityReason):
            normalised.add(reason.value)
        else:
            normalised.add(str(reason))
    return REASON_DELIMITER.join(sorted(normalised))


def parse_qc_flags(qc_flags: str) -> frozenset[str]:
    """Split a canonical QC-flag string into a frozenset."""
    if not qc_flags:
        return frozenset()
    return frozenset(part for part in qc_flags.split("|") if part)


def normalise_target_text(text: str) -> str:
    """Deterministic raw-target text normaliser for leakage matching only.

    Case-folds, collapses whitespace, unifies hyphen variants, and strips
    residual punctuation. Does not perform UniProt resolution or full target
    normalisation.
    """
    if text is None:
        return ""
    folded = str(text).casefold()
    folded = folded.replace("β", "beta").replace("Β", "beta")
    folded = _HYPHEN_VARIANTS_RE.sub("-", folded)
    folded = _PUNCT_RE.sub(" ", folded)
    folded = _WHITESPACE_RE.sub(" ", folded).strip()
    # Collapse hyphen/space variants around tokens: "his-ndm-1" / "his ndm 1".
    folded = folded.replace("-", " ")
    folded = _WHITESPACE_RE.sub(" ", folded).strip()
    return folded


def load_target_alias_rules(path: str | Path) -> tuple[TargetAliasRule, ...]:
    """Load configured target leakage aliases from CSV."""
    alias_path = Path(path)
    if not alias_path.is_file():
        raise EligibilityError(f"Missing target-alias file: {alias_path.name}")
    with alias_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = [
            "canonical_target",
            "alias",
            "match_type",
            "target_family",
            "exclusion_reason",
            "notes",
        ]
        if list(reader.fieldnames or []) != expected:
            raise EligibilityError(
                "leakage_target_aliases.csv columns must match "
                f"{expected}; got {list(reader.fieldnames or [])}"
            )
        rows = list(reader)

    rules: list[TargetAliasRule] = []
    for index, row in enumerate(rows, start=2):
        match_type = (row.get("match_type") or "").strip()
        if match_type not in ALLOWED_MATCH_TYPES:
            raise EligibilityError(
                f"Invalid match_type on leakage_target_aliases.csv row {index}"
            )
        canonical = (row.get("canonical_target") or "").strip()
        alias = (row.get("alias") or "").strip()
        if not canonical or not alias:
            raise EligibilityError(
                f"Empty canonical_target/alias on leakage_target_aliases.csv "
                f"row {index}"
            )
        rules.append(
            TargetAliasRule(
                canonical_target=canonical,
                alias=alias,
                match_type=match_type,
                target_family=(row.get("target_family") or "").strip(),
                exclusion_reason=(row.get("exclusion_reason") or "").strip(),
                notes=(row.get("notes") or "").strip(),
                normalised_alias=normalise_target_text(alias),
                exact_alias_folded=alias.casefold().strip(),
            )
        )
    return tuple(rules)


def match_target_leakage(
    texts: Sequence[str],
    rules: Sequence[TargetAliasRule],
) -> TargetLeakageMatch | None:
    """Match raw target texts against configured alias/family rules.

    Matching is bounded: exact aliases require full-string equality after
    casefold; normalised aliases require full-string equality after
    ``normalise_target_text``; family patterns require whole-token / phrase
    boundaries. Unbounded substring search is not used.
    """
    candidates: list[tuple[str, str, str, TargetAliasRule, str]] = []
    prepared: list[tuple[str, str, str]] = []
    for text in texts:
        raw = (text or "").strip()
        if not raw:
            continue
        prepared.append((raw, raw.casefold().strip(), normalise_target_text(raw)))

    if not prepared:
        return None

    for rule in rules:
        for _raw, folded, normalised in prepared:
            matched = False
            if rule.match_type == "exact_alias":
                matched = folded == rule.exact_alias_folded
            elif rule.match_type == "normalised_alias":
                matched = (
                    normalised == rule.normalised_alias and rule.normalised_alias != ""
                )
            elif rule.match_type == "family_pattern":
                pattern_norm = rule.normalised_alias
                if pattern_norm:
                    # Whole-phrase token boundaries on normalised whitespace text.
                    escaped = re.escape(pattern_norm)
                    regex = re.compile(rf"(?<!\w){escaped}(?!\w)")
                    matched = bool(regex.search(normalised))
            if matched:
                candidates.append(
                    (
                        rule.match_type,
                        rule.canonical_target,
                        rule.alias,
                        rule,
                        rule.target_family,
                    )
                )
                break

    if not candidates:
        return None

    # Deterministic precedence: exact_alias, normalised_alias, family_pattern,
    # then canonical target, then alias text.
    type_rank = {"exact_alias": 0, "normalised_alias": 1, "family_pattern": 2}
    candidates.sort(
        key=lambda item: (
            type_rank.get(item[0], 99),
            item[1],
            item[2],
        )
    )
    match_type, canonical, alias, rule, family = candidates[0]
    return TargetLeakageMatch(
        matched_canonical_target=canonical,
        matched_alias=alias,
        match_type=match_type,
        target_family=family,
    )


def load_sequence_leakage_index(path: str | Path) -> SequenceLeakageIndex:
    """Load the leakage-exclusion set; hard-fail on missing/malformed/duplicates."""
    leakage_path = Path(path)
    if not leakage_path.is_file():
        raise EligibilityError(f"Missing leakage exclusion set: {leakage_path.name}")

    with leakage_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise EligibilityError("leakage exclusion set has no header")
        required = {
            "exclusion_id",
            "reference_id",
            "target_name",
            "evaluation_role",
            "sequence_compare_full",
            "sequence_compare_core",
            "status",
        }
        missing = required - set(reader.fieldnames)
        if missing:
            raise EligibilityError(
                "leakage exclusion set missing columns: "
                + ", ".join(sorted(missing))
            )
        rows = list(reader)

    seen_ids: set[str] = set()
    references: list[ExclusionReference] = []
    for index, row in enumerate(rows, start=2):
        exclusion_id = (row.get("exclusion_id") or "").strip()
        if not exclusion_id:
            raise EligibilityError(
                f"Blank exclusion_id on leakage exclusion row {index}"
            )
        if exclusion_id in seen_ids:
            raise EligibilityError(
                f"Duplicate exclusion_id in leakage exclusion set: {exclusion_id!r}"
            )
        seen_ids.add(exclusion_id)
        references.append(
            ExclusionReference(
                exclusion_id=exclusion_id,
                reference_id=(row.get("reference_id") or "").strip(),
                target_name=(row.get("target_name") or "").strip(),
                evaluation_role=(row.get("evaluation_role") or "").strip(),
                sequence_compare_full=(row.get("sequence_compare_full") or "").strip(),
                sequence_compare_core=(row.get("sequence_compare_core") or "").strip(),
                status=(row.get("status") or "").strip(),
            )
        )
    return SequenceLeakageIndex(references=tuple(references))


def build_eligibility_result(
    *,
    record_id: str,
    proposed_decision: EligibilityDecision,
    primary_reason: EligibilityReason,
    secondary_reasons: Sequence[EligibilityReason] = (),
    manual_review_priority: ManualReviewPriority,
    sequence_leakage_match: LeakageMatch | None = None,
    target_leakage_match: TargetLeakageMatch | None = None,
    checkpoint_status: str = CHECKPOINT_STATUS_PENDING,
) -> EligibilityResult:
    """Construct a validated eligibility result with sorted reason inventory."""
    if proposed_decision.value not in ALLOWED_DECISIONS:
        raise EligibilityError(f"Unknown proposed decision: {proposed_decision}")
    if checkpoint_status != CHECKPOINT_STATUS_PENDING:
        raise EligibilityError(
            f"Unsupported checkpoint_status at S3: {checkpoint_status!r}"
        )

    unique_secondary = tuple(
        sorted({reason for reason in secondary_reasons if reason != primary_reason},
               key=lambda item: item.value)
    )
    all_reasons = (primary_reason,) + unique_secondary
    manual_review_required = manual_review_priority != ManualReviewPriority.NONE
    return EligibilityResult(
        record_id=record_id,
        proposed_decision=proposed_decision,
        primary_reason=primary_reason,
        all_reasons=all_reasons,
        manual_review_required=manual_review_required,
        manual_review_priority=manual_review_priority,
        sequence_leakage_match=sequence_leakage_match,
        target_leakage_match=target_leakage_match,
        checkpoint_status=checkpoint_status,
    )


def review_sort_key(row: Mapping[str, str]) -> tuple[int, int, str, str]:
    """Sort key for CHECKPOINT-1 review ordering."""
    priority = row.get("manual_review_priority", "none")
    decision = row.get("proposed_decision", "")
    try:
        priority_rank = REVIEW_PRIORITY_ORDER.index(priority)
    except ValueError:
        priority_rank = len(REVIEW_PRIORITY_ORDER)
    try:
        decision_rank = DECISION_REVIEW_ORDER.index(decision)
    except ValueError:
        decision_rank = len(DECISION_REVIEW_ORDER)
    return (
        priority_rank,
        decision_rank,
        row.get("primary_reason", ""),
        row.get("record_id", ""),
    )

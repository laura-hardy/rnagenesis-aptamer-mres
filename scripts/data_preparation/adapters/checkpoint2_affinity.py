"""Affinity-grain CHECKPOINT-2 transforms. Not the apply stage.

Reviewed affinity outcomes project an effective per-record affinity
representation without writing combined input, proposal tables, review
CSVs, or a CHECKPOINT-2 apply CLI. Canonical scalar columns stay blank
unless a reviewed exact scalar is scientifically safe.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

from adapters.checkpoint2_relationship import RelationshipProjection
from adapters.s4_affinity import (
    UNIT_IN_TEXT_RE,
    parse_affinity_from_text,
    parse_affinity_value,
)
from adapters.s4_scientific_common import (
    AFFINITY_DECISION_VOCAB,
    AFFINITY_EXTRA_HUMAN_FIELDS,
    AFFINITY_QUALIFIER_VOCAB,
    AFFINITY_RANGE_STATUS_VOCAB,
    AFFINITY_SCALAR_TRANSFORM_RULES,
    AFFINITY_TRANSFORM_RULE_VOCAB,
    AFFINITY_TYPE_VOCAB,
    CONFIRM_AFFINITY_SCALAR,
    EVIDENCE_SCORE_BY_LEVEL,
    EXCLUDE_NON_AFFINITY,
    HUMAN_FIELDS,
    NON_AFFINITY_REASON_VOCAB,
    RETAIN_AFFINITY_RAW,
    ScientificProposalError,
    assert_affinity_human_fields_blank,
    blank_affinity_human_fields,
    fill_row,
    join_unique,
    split_pipe,
)

AFFINITY_REVIEW_STATUS_EXACT = "exact_scalar"
AFFINITY_REVIEW_STATUS_RAW = "retain_raw"
AFFINITY_REVIEW_STATUS_EXCLUDE = "exclude_non_affinity"
AFFINITY_REVIEW_STATUS_PARK = "park_unresolved"
AFFINITY_REVIEW_STATUS_UNREVIEWED = "unreviewed"

SUBGROUP_ASSAY_CAPTION = "assay_caption"
SUBGROUP_BINDING_PERCENTAGE = "binding_percentage"
SUBGROUP_CENTRAL_UNCERTAINTY = "central_value_uncertainty"
SUBGROUP_GLUED_UNIT = "glued_unit"
SUBGROUP_INEQUALITY = "inequality"
SUBGROUP_LOD = "lod"
SUBGROUP_MENTIONED_FOREIGN_KD = "mentioned_foreign_kd"
SUBGROUP_MISSING_UNIT = "missing_unit_unrecoverable"
SUBGROUP_MISSING_VALUE = "missing_value"
SUBGROUP_MOJIBAKE_MICRO_M = "mojibake_micro_M"
SUBGROUP_MULTIPLE_KD = "multiple_kd"
SUBGROUP_NO_BINDING = "no_binding"
SUBGROUP_PLACEHOLDER = "placeholder"
SUBGROUP_APPROXIMATION = "approximation"
SUBGROUP_RATE = "rate"
SUBGROUP_SCIENTIFIC_NOTATION = "scientific_notation"
SUBGROUP_TRUE_RANGE = "true_range"
SUBGROUP_UNCERTAINTY = "uncertainty"
SUBGROUP_UNRESOLVED = "unresolved_source_text"

SUBGROUP_TO_OUTCOME: dict[str, str] = {
    SUBGROUP_LOD: EXCLUDE_NON_AFFINITY,
    SUBGROUP_ASSAY_CAPTION: EXCLUDE_NON_AFFINITY,
    SUBGROUP_MENTIONED_FOREIGN_KD: EXCLUDE_NON_AFFINITY,
    SUBGROUP_BINDING_PERCENTAGE: EXCLUDE_NON_AFFINITY,
    SUBGROUP_RATE: EXCLUDE_NON_AFFINITY,
    SUBGROUP_MISSING_VALUE: EXCLUDE_NON_AFFINITY,
    SUBGROUP_NO_BINDING: EXCLUDE_NON_AFFINITY,
    SUBGROUP_PLACEHOLDER: EXCLUDE_NON_AFFINITY,
    SUBGROUP_INEQUALITY: RETAIN_AFFINITY_RAW,
    SUBGROUP_APPROXIMATION: RETAIN_AFFINITY_RAW,
    SUBGROUP_TRUE_RANGE: RETAIN_AFFINITY_RAW,
    SUBGROUP_MULTIPLE_KD: RETAIN_AFFINITY_RAW,
    SUBGROUP_UNCERTAINTY: RETAIN_AFFINITY_RAW,
    SUBGROUP_MISSING_UNIT: RETAIN_AFFINITY_RAW,
    SUBGROUP_MOJIBAKE_MICRO_M: CONFIRM_AFFINITY_SCALAR,
    SUBGROUP_GLUED_UNIT: CONFIRM_AFFINITY_SCALAR,
    SUBGROUP_SCIENTIFIC_NOTATION: CONFIRM_AFFINITY_SCALAR,
    SUBGROUP_CENTRAL_UNCERTAINTY: CONFIRM_AFFINITY_SCALAR,
    SUBGROUP_UNRESOLVED: "park_unresolved",
}

SUBGROUP_TO_TRANSFORM: dict[str, str] = {
    SUBGROUP_MOJIBAKE_MICRO_M: "mojibake_micro_M",
    SUBGROUP_GLUED_UNIT: "glued_unit",
    SUBGROUP_SCIENTIFIC_NOTATION: "scientific_notation",
    SUBGROUP_CENTRAL_UNCERTAINTY: "central_value_uncertainty",
    SUBGROUP_INEQUALITY: "parse_inequality_bound",
}

SUBGROUP_TO_NON_AFFINITY_REASON: dict[str, str] = {
    SUBGROUP_LOD: "lod",
    SUBGROUP_ASSAY_CAPTION: "assay_caption",
    SUBGROUP_MENTIONED_FOREIGN_KD: "mentioned_foreign_kd",
    SUBGROUP_BINDING_PERCENTAGE: "binding_percentage",
    SUBGROUP_RATE: "rate",
    SUBGROUP_MISSING_VALUE: "missing_value",
    SUBGROUP_NO_BINDING: "no_binding",
    SUBGROUP_PLACEHOLDER: "placeholder",
}

SUBGROUP_TO_RANGE_STATUS: dict[str, str] = {
    SUBGROUP_TRUE_RANGE: "range",
    SUBGROUP_MULTIPLE_KD: "list",
}

# Documented unsplit live rows. One scientific rule covers the group.
UNSPLIT_AFFINITY_DECISION_IDS: tuple[str, ...] = (
    "C2A0001",
    "C2A0002",
    "C2A0003",
    "C2A0005",
    "C2A0006",
    "C2A0007",
    "C2A0008",
    "C2A0010",
    "C2A0011",
    "C2A0012",
    "C2A0015",
    "C2A0017",
    "C2A0019",
)

# Documented split parents. Child suffixes A, B, ... follow this order,
# not row order and not whichever subgroups happen to appear first.
AFFINITY_SPLIT_SUBGROUPS: dict[str, tuple[str, ...]] = {
    "C2A0004": (SUBGROUP_ASSAY_CAPTION, SUBGROUP_MENTIONED_FOREIGN_KD),
    "C2A0009": (SUBGROUP_MULTIPLE_KD, SUBGROUP_TRUE_RANGE),
    "C2A0013": (SUBGROUP_INEQUALITY, SUBGROUP_MULTIPLE_KD, SUBGROUP_UNCERTAINTY),
    "C2A0014": (
        SUBGROUP_APPROXIMATION,
        SUBGROUP_BINDING_PERCENTAGE,
        SUBGROUP_TRUE_RANGE,
    ),
    "C2A0016": (
        SUBGROUP_CENTRAL_UNCERTAINTY,
        SUBGROUP_GLUED_UNIT,
        SUBGROUP_MISSING_VALUE,
        SUBGROUP_MULTIPLE_KD,
        SUBGROUP_RATE,
    ),
    "C2A0018": (
        SUBGROUP_MULTIPLE_KD,
        SUBGROUP_SCIENTIFIC_NOTATION,
        SUBGROUP_TRUE_RANGE,
    ),
}

EXPECTED_LIVE_AFFINITY_DECISION_IDS: tuple[str, ...] = (
    "C2A0001",
    "C2A0002",
    "C2A0003",
    "C2A0004A",
    "C2A0004B",
    "C2A0005",
    "C2A0006",
    "C2A0007",
    "C2A0008",
    "C2A0009A",
    "C2A0009B",
    "C2A0010",
    "C2A0011",
    "C2A0012",
    "C2A0013A",
    "C2A0013B",
    "C2A0013C",
    "C2A0014A",
    "C2A0014B",
    "C2A0014C",
    "C2A0015",
    "C2A0016A",
    "C2A0016B",
    "C2A0016C",
    "C2A0016D",
    "C2A0016E",
    "C2A0017",
    "C2A0018A",
    "C2A0018B",
    "C2A0018C",
    "C2A0019",
)

SUBGROUP_AMBIGUITY_REASON: dict[str, str] = {
    SUBGROUP_ASSAY_CAPTION: "assay_caption_not_row_kd",
    SUBGROUP_MENTIONED_FOREIGN_KD: "mentioned_foreign_kd_not_row_level",
    SUBGROUP_BINDING_PERCENTAGE: "binding_percentage_not_affinity",
    SUBGROUP_RATE: "rate_not_binding_affinity",
    SUBGROUP_MISSING_VALUE: "missing_or_not_available",
    SUBGROUP_LOD: "lod_not_binding_affinity",
    SUBGROUP_NO_BINDING: "no_binding",
    SUBGROUP_PLACEHOLDER: "placeholder_not_affinity",
    SUBGROUP_INEQUALITY: "inequality_bound_not_exact_scalar",
    SUBGROUP_APPROXIMATION: "approximate_affinity_not_exact_scalar",
    SUBGROUP_TRUE_RANGE: "true_range_not_midpoint",
    SUBGROUP_MULTIPLE_KD: "multiple_or_condition_specific_values",
    SUBGROUP_UNCERTAINTY: "uncertainty_form_not_exact_scalar",
    SUBGROUP_MISSING_UNIT: "missing_unit_unrecoverable",
    SUBGROUP_MOJIBAKE_MICRO_M: "mojibake_micro_M_per_record_transform",
    SUBGROUP_GLUED_UNIT: "glued_unit_per_record_scalar",
    SUBGROUP_SCIENTIFIC_NOTATION: "scientific_notation_per_record_scalar",
    SUBGROUP_CENTRAL_UNCERTAINTY: "central_value_uncertainty_per_record_scalar",
    SUBGROUP_UNRESOLVED: "unresolved_source_text",
}

PARENT_DECISION_ID_RE = re.compile(r"^(C2A\d{4})[A-Z]$")
RAW_EXAMPLE_LIMIT = 8
RAW_EXAMPLE_MAX_CHARS = 160

AFFINITY_REVIEW_MACHINE_COLUMNS: tuple[str, ...] = (
    "parent_decision_id",
    "affinity_subgroup",
    "record_ids",
    "affinity_raw_examples",
    "scientific_ambiguity_reason",
    "review_consequence",
    "machine_affinity_transform_rule",
    "park_provenance_record_ids",
)

TYPE_PREFIX_RE = re.compile(r"(?i)^(?:kd|ki|ic50|ec50|ka)\s*[:=]?\s*")
GLUED_EXACT_RE = re.compile(
    r"(?i)^(?:(?:kd|ki|ic50|ec50|ka)\s*[:=]?\s*)?"
    r"\d+(?:\.\d+)?(?:nM|uM|µM|μm|pM|fM|mM|M)$"
)
UNCERTAINTY_AFTER_UNIT_RE = re.compile(
    r"(?i)\d+(?:\.\d+)?\s*(?:nM|uM|µM|μm|pM|fM|mM|M)\s*±\s*\d+"
)
NUMERIC_AFFINITY_MENTION_RE = re.compile(
    r"(?i)(?:\b(?:kd|ki|ic50|ec50|ka)\b.{0,24}\d)|"
    r"(?:\d+(?:\.\d+)?\s*(?:nM|uM|µM|μm|pM|fM|mM|M)\b)"
)
PLAIN_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
CAPTION_HINT_RE = re.compile(
    r"(?i)\b(curve|curves|assay|elisa|figure|plot|sensorgram|titration|"
    r"isotherm|sensorgrams|authoradiograph|autoradiograph)\b"
)
INEQUALITY_TOKEN_RE = re.compile(r"<<|>>|<=|>=|≤|≥|[<>]")
RANGE_HYPHEN_RE = re.compile(r"\d\s*[-–—]\s*\d")
SCI_TIMES_TEN_RE = re.compile(r"(?i)\d\s*[x×]\s*10\s*\^")


def _blank(value: str | None) -> str:
    return (value or "").strip()


def extract_affinity_qualifier(raw: str) -> str:
    text = raw or ""
    if ">>" in text:
        return ">>"
    if ">=" in text or "≥" in text:
        return ">="
    if "<=" in text or "≤" in text:
        return "<="
    if "<" in text:
        return "<"
    if ">" in text:
        return ">"
    if re.search(r"[~≈]", text) and not re.search(r"\d\s*[~≈]\s*\d", text):
        return "approximate"
    return ""


def _is_assay_caption(raw: str) -> bool:
    text = raw or ""
    if TYPE_PREFIX_RE.match(text):
        return False
    words = [item for item in text.split() if item]
    if len(words) >= 5:
        return True
    if CAPTION_HINT_RE.search(text) and len(words) >= 4:
        return True
    return False


def classify_affinity_subgroup(row: Mapping[str, str]) -> str:
    """Assign one scientific subgroup from source text. Not a human decision."""
    raw = _blank(row.get("affinity_value_raw"))
    status = _blank(row.get("affinity_parse_status"))
    source = _blank(row.get("source_db"))
    folded = raw.casefold()
    stripped = TYPE_PREFIX_RE.sub("", raw).strip()

    if status == "lod_not_binding_affinity" or re.search(
        r"(?i)\blod\b|limit of detection", folded
    ):
        return SUBGROUP_LOD
    if re.search(r"(?i)\bno binding\b", folded):
        return SUBGROUP_NO_BINDING
    if re.search(r"(?i)binding percentage", folded) or (
        "%" in raw and re.search(r"(?i)percent|binding", folded)
    ):
        return SUBGROUP_BINDING_PERCENTAGE
    if re.search(r"(?i)\(1/s\)|\b1/s\b", folded):
        return SUBGROUP_RATE
    if re.fullmatch(r"(?i)tbd", stripped):
        return SUBGROUP_PLACEHOLDER
    if re.match(r"(?i)^n/?a\b", stripped) or re.fullmatch(r"(?i)na", stripped):
        return SUBGROUP_MISSING_VALUE
    if _is_assay_caption(raw):
        if NUMERIC_AFFINITY_MENTION_RE.search(raw):
            return SUBGROUP_MENTIONED_FOREIGN_KD
        return SUBGROUP_ASSAY_CAPTION
    if (
        source == "aptabase"
        and status == "missing_unit"
        and PLAIN_NUMBER_RE.fullmatch(raw)
    ):
        return SUBGROUP_MOJIBAKE_MICRO_M
    compact = re.sub(r"\s+", "", stripped)
    if GLUED_EXACT_RE.fullmatch(stripped) or GLUED_EXACT_RE.fullmatch(compact):
        return SUBGROUP_GLUED_UNIT
    if re.search(r"(?i)\bbiphasic\b|\bkd1\b|\bkd2\b", folded):
        return SUBGROUP_MULTIPLE_KD
    if re.search(r"(?i)\bki\b", folded) and re.search(r"(?i)\bkd\b", folded):
        return SUBGROUP_MULTIPLE_KD
    if re.search(r"\d\s*/\s*\d", raw):
        return SUBGROUP_MULTIPLE_KD
    if "|" in raw:
        return SUBGROUP_MULTIPLE_KD
    if UNCERTAINTY_AFTER_UNIT_RE.search(raw) and not re.search(
        r"(?i)\bor\b|,", raw
    ):
        return SUBGROUP_CENTRAL_UNCERTAINTY
    if SCI_TIMES_TEN_RE.search(raw):
        return SUBGROUP_SCIENTIFIC_NOTATION
    if status == "inequality" or INEQUALITY_TOKEN_RE.search(raw):
        return SUBGROUP_INEQUALITY
    if re.search(r"\d\s*[~≈]\s*\d", raw):
        return SUBGROUP_TRUE_RANGE
    if status == "approximate" or re.search(r"[~≈]", raw):
        return SUBGROUP_APPROXIMATION
    if re.search(r"(?i)\berror\b|\(\s*\+/-", raw):
        return SUBGROUP_UNCERTAINTY
    if re.search(r"(?i)\bbetween\b.+\band\b", folded) or RANGE_HYPHEN_RE.search(raw):
        return SUBGROUP_TRUE_RANGE
    if "|" in raw or "&" in raw or re.search(r"(?i)\bor\b", folded):
        return SUBGROUP_MULTIPLE_KD
    unit_hits = UNIT_IN_TEXT_RE.findall(raw)
    if len(unit_hits) >= 2 and "±" not in raw:
        return SUBGROUP_MULTIPLE_KD
    if re.search(r"(?i)\band\b", folded) and re.search(r"\d", raw):
        return SUBGROUP_MULTIPLE_KD
    if status == "missing_unit":
        return SUBGROUP_MISSING_UNIT
    if TYPE_PREFIX_RE.match(raw):
        return SUBGROUP_MULTIPLE_KD
    if status in {"range_or_multiple", "malformed", "approximate"}:
        return SUBGROUP_UNRESOLVED
    return SUBGROUP_UNRESOLVED


def proposed_outcome_for_subgroup(subgroup: str) -> str:
    return SUBGROUP_TO_OUTCOME.get(subgroup, "park_unresolved")


def parse_inequality_bound(
    raw: str,
    *,
    unit: str = "",
    affinity_type: str = "Kd",
) -> tuple[str, str]:
    """Return (qualifier, molar bound). Bound is not an exact scalar."""
    qualifier = extract_affinity_qualifier(raw)
    remainder = TYPE_PREFIX_RE.sub("", raw).strip()
    remainder = re.sub(r"^(?:<<|>>|<=|>=|≤|≥|<|>)\s*", "", remainder).strip()
    parsed = parse_affinity_value(remainder, unit=unit, affinity_type=affinity_type)
    bound = _blank(parsed.get("affinity_value_molar_proposed"))
    return qualifier, bound


def apply_affinity_transform(
    raw: str,
    *,
    unit: str = "",
    affinity_type: str = "Kd",
    transform_rule: str = "",
) -> dict[str, str]:
    """Apply a reviewed source-rule to one record's own source text."""
    rule = _blank(transform_rule)
    type_hint = _blank(affinity_type) or "Kd"
    if rule == "mojibake_micro_M":
        return parse_affinity_value(raw, unit="µM", affinity_type=type_hint)
    if rule == "glued_unit":
        return parse_affinity_from_text(raw) if not unit else parse_affinity_value(
            raw, unit=unit, affinity_type=type_hint
        )
    if rule == "scientific_notation":
        return parse_affinity_from_text(raw) if not unit else parse_affinity_value(
            raw, unit=unit, affinity_type=type_hint
        )
    if rule == "central_value_uncertainty":
        return parse_affinity_value(raw, unit=unit, affinity_type=type_hint)
    if rule == "parse_inequality_bound":
        qualifier, bound = parse_inequality_bound(
            raw, unit=unit, affinity_type=type_hint
        )
        parsed = parse_affinity_value(raw, unit=unit, affinity_type=type_hint)
        parsed["affinity_value_molar_proposed"] = ""
        parsed["_qualifier"] = qualifier
        parsed["_bound_molar"] = bound
        return parsed
    if unit:
        return parse_affinity_value(raw, unit=unit, affinity_type=type_hint)
    return parse_affinity_from_text(raw)


def _preview_ids(record_ids: Sequence[str], *, limit: int = 8) -> str:
    ordered = list(dict.fromkeys(item for item in record_ids if item))
    if len(ordered) <= limit:
        return "|".join(ordered)
    return "|".join(ordered[:limit]) + f"|+{len(ordered) - limit}"


def _collapse_raw_example(raw: str) -> str:
    text = " ".join((raw or "").split())
    if len(text) <= RAW_EXAMPLE_MAX_CHARS:
        return text
    return text[: RAW_EXAMPLE_MAX_CHARS - 3].rstrip() + "..."


def _raw_examples(rows: Sequence[Mapping[str, str]]) -> tuple[str, ...]:
    seen: list[str] = []
    for row in rows:
        example = _collapse_raw_example(_blank(row.get("affinity_value_raw")))
        if example and example not in seen:
            seen.append(example)
        if len(seen) >= RAW_EXAMPLE_LIMIT:
            break
    return tuple(seen)


def parent_affinity_decision_id(row: Mapping[str, str]) -> str:
    """Return the original parent decision ID for a live or materialised row."""
    explicit = _blank(row.get("parent_decision_id"))
    if explicit:
        return explicit
    decision_id = _blank(row.get("decision_id"))
    if decision_id in AFFINITY_SPLIT_SUBGROUPS or decision_id in UNSPLIT_AFFINITY_DECISION_IDS:
        return decision_id
    match = PARENT_DECISION_ID_RE.fullmatch(decision_id)
    if match and match.group(1) in AFFINITY_SPLIT_SUBGROUPS:
        return match.group(1)
    return decision_id


def collapse_affinity_review_to_parent_grain(
    affinity_review_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Collapse materialised children back to one parent grain per original group."""
    parents: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in affinity_review_rows:
        parent = parent_affinity_decision_id(row)
        if parent in parents:
            continue
        parents[parent] = {
            "decision_id": parent,
            "source_db": _blank(row.get("source_db")),
            "affinity_parse_status": _blank(row.get("affinity_parse_status")),
            "affinity_parse_rule": _blank(row.get("affinity_parse_rule")),
            "affinity_type_proposed": _blank(row.get("affinity_type_proposed")),
        }
        order.append(parent)
    return [parents[item] for item in order]


def child_affinity_decision_id(
    parent: str,
    subgroup: str,
    present_subgroups: Sequence[str],
) -> str:
    """Stable child ID from parent + subgroup rule. Independent of row order."""
    present = tuple(dict.fromkeys(present_subgroups))
    spec = AFFINITY_SPLIT_SUBGROUPS.get(parent)
    if spec is not None:
        unexpected = [item for item in present if item not in spec]
        missing = [item for item in spec if item not in present]
        if unexpected or missing:
            raise ScientificProposalError(
                f"{parent} subgroup set {tuple(sorted(present))} does not match "
                f"documented split {spec}"
            )
        return f"{parent}{chr(ord('A') + spec.index(subgroup))}"
    if len(present) <= 1:
        return parent
    ordered = tuple(sorted(present))
    return f"{parent}{chr(ord('A') + ordered.index(subgroup))}"


@dataclass(frozen=True)
class AffinitySplitGroup:
    old_decision_id: str
    subgroup: str
    proposed_decision_id: str
    proposed_outcome: str
    transform_rule: str
    record_ids: tuple[str, ...]
    n_records: int
    raw_examples: tuple[str, ...]
    source_db: str
    affinity_parse_status: str
    affinity_parse_rule: str
    affinity_type_proposed: str


@dataclass(frozen=True)
class ProposedAffinitySplit:
    """Deterministic split proposal. Materialisation is a separate write step."""

    groups: tuple[AffinitySplitGroup, ...]
    unsplit_decision_ids: tuple[str, ...]
    split_decision_ids: tuple[str, ...]
    n_input_rows: int
    n_parent_rows: int
    n_proposed_rows: int

    @property
    def n_live_rows(self) -> int:
        return self.n_parent_rows


def _affinity_evidence_groups(
    evidence_rows: Sequence[Mapping[str, str]],
) -> dict[tuple[str, str, str], list[Mapping[str, str]]]:
    by_key: dict[tuple[str, str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in evidence_rows:
        if _blank(row.get("affinity_requires_review")) != "true":
            continue
        if _blank(row.get("affinity_parse_status")) in {"", "absent"}:
            continue
        key = (
            _blank(row.get("source_db")),
            _blank(row.get("affinity_parse_status")),
            _blank(row.get("affinity_parse_rule")),
        )
        by_key[key].append(row)
    return by_key


def propose_affinity_review_splits(
    affinity_review_rows: Sequence[Mapping[str, str]],
    evidence_rows: Sequence[Mapping[str, str]],
) -> ProposedAffinitySplit:
    """Map parent-grain rows to deterministic scientific subgroups.

    Already-materialised child rows are collapsed to their parent grain first,
    so reruns do not append further suffixes.
    """
    parents = collapse_affinity_review_to_parent_grain(affinity_review_rows)
    by_key = _affinity_evidence_groups(evidence_rows)

    groups: list[AffinitySplitGroup] = []
    unsplit: list[str] = []
    split: list[str] = []
    for review in parents:
        decision_id = _blank(review.get("decision_id"))
        key = (
            _blank(review.get("source_db")),
            _blank(review.get("affinity_parse_status")),
            _blank(review.get("affinity_parse_rule")),
        )
        members = by_key.get(key, [])
        subgroup_rows: dict[str, list[Mapping[str, str]]] = defaultdict(list)
        subgroup_ids: dict[str, list[str]] = defaultdict(list)
        for item in members:
            record_id = _blank(item.get("record_id"))
            if not record_id:
                continue
            subgroup = classify_affinity_subgroup(item)
            subgroup_rows[subgroup].append(item)
            if record_id not in subgroup_ids[subgroup]:
                subgroup_ids[subgroup].append(record_id)
        present = tuple(subgroup_ids)
        if decision_id in AFFINITY_SPLIT_SUBGROUPS:
            ordered = tuple(
                item
                for item in AFFINITY_SPLIT_SUBGROUPS[decision_id]
                if item in subgroup_ids
            )
        elif len(present) <= 1:
            ordered = present
        else:
            ordered = tuple(sorted(present))
        if not ordered:
            ordered = (SUBGROUP_UNRESOLVED,)
            subgroup_ids[SUBGROUP_UNRESOLVED] = []
            subgroup_rows[SUBGROUP_UNRESOLVED] = []
        if len(ordered) <= 1 and decision_id not in AFFINITY_SPLIT_SUBGROUPS:
            subgroup = ordered[0]
            record_ids = tuple(subgroup_ids.get(subgroup, ()))
            groups.append(
                AffinitySplitGroup(
                    old_decision_id=decision_id,
                    subgroup=subgroup,
                    proposed_decision_id=child_affinity_decision_id(
                        decision_id, subgroup, present or (subgroup,)
                    ),
                    proposed_outcome=proposed_outcome_for_subgroup(subgroup),
                    transform_rule=SUBGROUP_TO_TRANSFORM.get(subgroup, ""),
                    record_ids=record_ids,
                    n_records=len(record_ids),
                    raw_examples=_raw_examples(subgroup_rows.get(subgroup, ())),
                    source_db=key[0],
                    affinity_parse_status=key[1],
                    affinity_parse_rule=key[2],
                    affinity_type_proposed=_blank(review.get("affinity_type_proposed")),
                )
            )
            unsplit.append(decision_id)
            continue
        split.append(decision_id)
        for subgroup in ordered:
            record_ids = tuple(subgroup_ids[subgroup])
            groups.append(
                AffinitySplitGroup(
                    old_decision_id=decision_id,
                    subgroup=subgroup,
                    proposed_decision_id=child_affinity_decision_id(
                        decision_id, subgroup, present
                    ),
                    proposed_outcome=proposed_outcome_for_subgroup(subgroup),
                    transform_rule=SUBGROUP_TO_TRANSFORM.get(subgroup, ""),
                    record_ids=record_ids,
                    n_records=len(record_ids),
                    raw_examples=_raw_examples(subgroup_rows[subgroup]),
                    source_db=key[0],
                    affinity_parse_status=key[1],
                    affinity_parse_rule=key[2],
                    affinity_type_proposed=_blank(review.get("affinity_type_proposed")),
                )
            )
    return ProposedAffinitySplit(
        groups=tuple(groups),
        unsplit_decision_ids=tuple(unsplit),
        split_decision_ids=tuple(split),
        n_input_rows=len(affinity_review_rows),
        n_parent_rows=len(parents),
        n_proposed_rows=len(groups),
    )


def _as_split_map(proposal: ProposedAffinitySplit) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for group in proposal.groups:
        out.setdefault(group.old_decision_id, {})[group.subgroup] = list(group.record_ids)
    return out


def validate_affinity_review_row(
    row: Mapping[str, str],
    *,
    line: str = "affinity",
) -> list[str]:
    """Fail closed on contradictory affinity human fields."""
    errors: list[str] = []
    decision = _blank(row.get("manual_decision"))
    if not decision:
        return errors
    if decision not in AFFINITY_DECISION_VOCAB:
        errors.append(f"{line} invalid affinity manual_decision {decision}")
        return errors
    value = _blank(row.get("manual_affinity_value"))
    unit = _blank(row.get("manual_affinity_unit"))
    aff_type = _blank(row.get("manual_affinity_type"))
    qualifier = _blank(row.get("manual_affinity_qualifier"))
    range_status = _blank(row.get("manual_affinity_range_status"))
    transform = _blank(row.get("manual_affinity_transform_rule"))
    reason = _blank(row.get("manual_affinity_non_affinity_reason"))
    if aff_type and aff_type not in AFFINITY_TYPE_VOCAB:
        errors.append(f"{line} invalid manual_affinity_type")
    if qualifier and qualifier not in AFFINITY_QUALIFIER_VOCAB:
        errors.append(f"{line} invalid manual_affinity_qualifier")
    if range_status and range_status not in AFFINITY_RANGE_STATUS_VOCAB:
        errors.append(f"{line} invalid manual_affinity_range_status")
    if transform and transform not in AFFINITY_TRANSFORM_RULE_VOCAB:
        errors.append(f"{line} invalid manual_affinity_transform_rule")
    if reason and reason not in NON_AFFINITY_REASON_VOCAB:
        errors.append(f"{line} invalid manual_affinity_non_affinity_reason")
    if value and not unit:
        errors.append(f"{line} affinity value without unit")

    if decision == EXCLUDE_NON_AFFINITY:
        if value or unit:
            errors.append(f"{line} {EXCLUDE_NON_AFFINITY} cannot carry a manual scalar")
        if transform in AFFINITY_SCALAR_TRANSFORM_RULES:
            errors.append(f"{line} {EXCLUDE_NON_AFFINITY} cannot use a scalar transform")
        if not reason:
            errors.append(f"{line} {EXCLUDE_NON_AFFINITY} missing non-affinity reason")
    elif decision == CONFIRM_AFFINITY_SCALAR:
        has_scalar = bool(value and unit)
        has_rule = transform in AFFINITY_SCALAR_TRANSFORM_RULES
        if not has_scalar and not has_rule:
            errors.append(
                f"{line} {CONFIRM_AFFINITY_SCALAR} requires a numeric value/unit "
                "or a per-record scalar transform"
            )
        if qualifier in {"<", "<=", ">", ">=", ">>"}:
            errors.append(
                f"{line} {CONFIRM_AFFINITY_SCALAR} cannot carry an inequality qualifier"
            )
        if range_status:
            errors.append(
                f"{line} {CONFIRM_AFFINITY_SCALAR} cannot carry range/list status"
            )
        if reason:
            errors.append(f"{line} {CONFIRM_AFFINITY_SCALAR} cannot mark non-affinity")
    elif decision == RETAIN_AFFINITY_RAW:
        if value:
            errors.append(
                f"{line} {RETAIN_AFFINITY_RAW} cannot carry a fake exact scalar"
            )
        if transform in AFFINITY_SCALAR_TRANSFORM_RULES:
            errors.append(
                f"{line} {RETAIN_AFFINITY_RAW} cannot use a scalar-producing transform"
            )
        if reason:
            errors.append(f"{line} {RETAIN_AFFINITY_RAW} is an affinity outcome")
    elif decision == "park_unresolved":
        if value or unit or transform or qualifier or range_status or reason:
            errors.append(f"{line} park_unresolved has incompatible affinity fields")
    return errors


def _canonical_from_projection(
    *,
    decision: str,
    molar: str,
    aff_type: str,
    relationship_active: bool,
) -> tuple[str, str, str]:
    if (
        decision == CONFIRM_AFFINITY_SCALAR
        and molar
        and relationship_active
    ):
        return molar, "M", aff_type
    return "", "", ""


def _range_status_for(review: Mapping[str, str], raw: str, subgroup: str) -> str:
    explicit = _blank(review.get("manual_affinity_range_status"))
    if explicit:
        return explicit
    if subgroup:
        return SUBGROUP_TO_RANGE_STATUS.get(subgroup, "")
    if re.search(r"\d\s*[-–—]\s*\d", raw) or re.search(r"\d\s*[~≈]\s*\d", raw) or re.search(r"(?i)\bbetween\b", raw):
        return "range"
    if "|" in raw or re.search(r"(?i)\bor\b|\band\b", raw):
        return "list"
    return ""


def project_record_affinity(
    machine_row: Mapping[str, str],
    review_row: Mapping[str, str] | None,
    *,
    relationship_active: bool,
    subgroup: str = "",
) -> dict[str, str]:
    """Project one record/relationship's reviewed affinity. No corpus write."""
    raw = _blank(machine_row.get("affinity_value_raw"))
    unit = _blank(machine_row.get("affinity_unit_raw"))
    machine_type = _blank(machine_row.get("affinity_type_proposed"))
    machine_evidence = _blank(machine_row.get("evidence_level_proposed"))
    record_id = _blank(machine_row.get("record_id"))
    relationship_index = _blank(machine_row.get("relationship_index"))
    source_db = _blank(machine_row.get("source_db"))
    decision_id = _blank(review_row.get("decision_id")) if review_row else ""
    decision = _blank(review_row.get("manual_decision")) if review_row else ""
    base = {
        "record_id": record_id,
        "relationship_index": relationship_index,
        "source_db": source_db,
        "review_decision_id": decision_id,
        "affinity_review_status": AFFINITY_REVIEW_STATUS_UNREVIEWED,
        "affinity_type": machine_type,
        "affinity_value_raw": raw,
        "affinity_value_molar": "",
        "affinity_unit_normalized": "",
        "affinity_qualifier": "",
        "affinity_range_status": "",
        "affinity_bound_molar": "",
        "non_affinity_reason": "",
        "transform_rule": "",
        "provenance": "",
        "canonical_affinity_value": "",
        "canonical_affinity_unit": "",
        "canonical_affinity_type": "",
        "relationship_active": "true" if relationship_active else "false",
        "machine_evidence_level": machine_evidence,
        "evidence_affinity_inconsistency": "",
    }
    if not decision:
        base["provenance"] = "affinity_unreviewed"
        return base

    aff_type = _blank(review_row.get("manual_affinity_type")) or machine_type
    transform = _blank(review_row.get("manual_affinity_transform_rule"))
    qualifier = _blank(review_row.get("manual_affinity_qualifier"))
    reason = _blank(review_row.get("manual_affinity_non_affinity_reason"))

    if decision == EXCLUDE_NON_AFFINITY:
        canonical_value, canonical_unit, canonical_type = _canonical_from_projection(
            decision=decision, molar="", aff_type="", relationship_active=relationship_active
        )
        base.update(
            {
                "affinity_review_status": AFFINITY_REVIEW_STATUS_EXCLUDE,
                "affinity_type": "",
                "affinity_value_molar": "",
                "affinity_unit_normalized": "",
                "non_affinity_reason": reason or SUBGROUP_TO_NON_AFFINITY_REASON.get(subgroup, ""),
                "provenance": f"checkpoint2_affinity:{decision_id}:{EXCLUDE_NON_AFFINITY}",
                "canonical_affinity_value": canonical_value,
                "canonical_affinity_unit": canonical_unit,
                "canonical_affinity_type": canonical_type,
            }
        )
        return base

    if decision == "park_unresolved":
        base.update(
            {
                "affinity_review_status": AFFINITY_REVIEW_STATUS_PARK,
                "provenance": f"checkpoint2_affinity:{decision_id}:park_unresolved",
            }
        )
        return base

    if decision == RETAIN_AFFINITY_RAW:
        if not qualifier:
            qualifier = extract_affinity_qualifier(raw)
        bound = ""
        if qualifier in {"<", "<=", ">", ">=", ">>"} or transform == "parse_inequality_bound":
            parsed_q, bound = parse_inequality_bound(
                raw, unit=unit, affinity_type=aff_type or "Kd"
            )
            qualifier = qualifier or parsed_q
        base.update(
            {
                "affinity_review_status": AFFINITY_REVIEW_STATUS_RAW,
                "affinity_type": aff_type,
                "affinity_qualifier": qualifier,
                "affinity_range_status": _range_status_for(review_row, raw, subgroup),
                "affinity_bound_molar": bound,
                "transform_rule": transform,
                "provenance": f"checkpoint2_affinity:{decision_id}:{RETAIN_AFFINITY_RAW}",
            }
        )
        return base

    if decision == CONFIRM_AFFINITY_SCALAR:
        parsed = apply_affinity_transform(
            raw,
            unit=unit,
            affinity_type=aff_type or "Kd",
            transform_rule=transform,
        )
        if not transform:
            review_value = _blank(review_row.get("manual_affinity_value"))
            review_unit = _blank(review_row.get("manual_affinity_unit"))
            if review_value and review_unit:
                parsed = parse_affinity_value(
                    review_value, unit=review_unit, affinity_type=aff_type or "Kd"
                )
        molar = _blank(parsed.get("affinity_value_molar_proposed"))
        if _blank(parsed.get("affinity_parse_status")) != "normalised":
            molar = ""
        canonical_value, canonical_unit, canonical_type = _canonical_from_projection(
            decision=decision,
            molar=molar,
            aff_type=aff_type,
            relationship_active=relationship_active,
        )
        base.update(
            {
                "affinity_review_status": AFFINITY_REVIEW_STATUS_EXACT,
                "affinity_type": aff_type,
                "affinity_value_molar": molar if relationship_active else "",
                "affinity_unit_normalized": "M" if molar and relationship_active else "",
                "transform_rule": transform,
                "provenance": f"checkpoint2_affinity:{decision_id}:{CONFIRM_AFFINITY_SCALAR}",
                "canonical_affinity_value": canonical_value,
                "canonical_affinity_unit": canonical_unit,
                "canonical_affinity_type": canonical_type,
            }
        )
        return base

    raise ScientificProposalError(
        f"project_record_affinity cannot interpret {decision!r}"
    )


def _index_affinity_reviews(
    review_rows: Sequence[Mapping[str, str]],
) -> tuple[
    dict[tuple[str, str, str, str], Mapping[str, str]],
    dict[tuple[str, str, str], Mapping[str, str]],
    dict[str, Mapping[str, str]],
]:
    by_subgroup: dict[tuple[str, str, str, str], Mapping[str, str]] = {}
    by_key: dict[tuple[str, str, str], Mapping[str, str]] = {}
    by_record: dict[str, Mapping[str, str]] = {}
    for row in review_rows:
        key = (
            _blank(row.get("source_db")),
            _blank(row.get("affinity_parse_status")),
            _blank(row.get("affinity_parse_rule")),
        )
        subgroup = _blank(row.get("affinity_subgroup"))
        if subgroup:
            by_subgroup[(*key, subgroup)] = row
        else:
            by_key[key] = row
        for record_id in split_pipe(_blank(row.get("record_ids"))):
            by_record[record_id] = row
    return by_subgroup, by_key, by_record


def _lookup_affinity_review(
    machine: Mapping[str, str],
    *,
    by_subgroup: Mapping[tuple[str, str, str, str], Mapping[str, str]],
    by_key: Mapping[tuple[str, str, str], Mapping[str, str]],
    by_record: Mapping[str, Mapping[str, str]],
    subgroup: str,
) -> Mapping[str, str] | None:
    key = (
        _blank(machine.get("source_db")),
        _blank(machine.get("affinity_parse_status")),
        _blank(machine.get("affinity_parse_rule")),
    )
    if subgroup:
        found = by_subgroup.get((*key, subgroup))
        if found is not None:
            return found
    record_id = _blank(machine.get("record_id"))
    if record_id and record_id in by_record:
        return by_record[record_id]
    return by_key.get(key)


def _active_record_ids(projection: RelationshipProjection | None) -> set[str]:
    if projection is None:
        return set()
    return {
        _blank(row.get("record_id"))
        for row in projection.effective_resolved
        if _blank(row.get("record_id"))
    }


def _evidence_level_for_flag(row: Mapping[str, str]) -> str:
    """Prefer completed effective evidence; otherwise machine evidence."""
    return _blank(row.get("effective_evidence_level")) or _blank(
        row.get("machine_evidence_level")
    )


def flag_evidence_affinity_inconsistency(row: Mapping[str, str]) -> str:
    """Return a flag token or blank. Does not mutate evidence."""
    status = _blank(row.get("affinity_review_status"))
    evidence = _evidence_level_for_flag(row)
    if status == AFFINITY_REVIEW_STATUS_EXCLUDE and evidence == "E2":
        return "evidence_affinity_inconsistency"
    if status == AFFINITY_REVIEW_STATUS_EXACT and _blank(row.get("affinity_value_molar")):
        score = EVIDENCE_SCORE_BY_LEVEL.get(evidence, 0)
        if score and score < EVIDENCE_SCORE_BY_LEVEL["E2"]:
            return "evidence_affinity_inconsistency"
    return ""


def inconsistency_kind(row: Mapping[str, str]) -> str:
    """Classify a flagged row. Does not mutate evidence."""
    if not _blank(row.get("evidence_affinity_inconsistency")):
        return ""
    status = _blank(row.get("affinity_review_status"))
    evidence = _evidence_level_for_flag(row)
    if status == AFFINITY_REVIEW_STATUS_EXCLUDE and evidence == "E2":
        return "machine_e2_reviewed_non_affinity"
    if status == AFFINITY_REVIEW_STATUS_EXACT:
        if evidence == "E4":
            return "machine_e4_reviewed_exact_quantitative_affinity"
        if evidence and evidence != "E2":
            return "machine_weaker_than_e2_reviewed_exact_quantitative_affinity"
    return ""


def project_affinity_reviews(
    evidence_rows: Sequence[Mapping[str, str]],
    affinity_review_rows: Sequence[Mapping[str, str]],
    *,
    relationship_projection: RelationshipProjection | None = None,
) -> tuple[tuple[dict[str, str], ...], tuple[dict[str, str], ...]]:
    """Project reviewed affinity for flagged records. Combined input is untouched."""
    by_subgroup, by_key, by_record = _index_affinity_reviews(affinity_review_rows)
    active_ids = _active_record_ids(relationship_projection)
    treat_unprojected_as_active = relationship_projection is None
    projected: list[dict[str, str]] = []
    for machine in evidence_rows:
        if _blank(machine.get("affinity_requires_review")) != "true":
            continue
        if _blank(machine.get("affinity_parse_status")) in {"", "absent"}:
            continue
        record_id = _blank(machine.get("record_id"))
        active = treat_unprojected_as_active or record_id in active_ids
        subgroup = classify_affinity_subgroup(machine)
        review = _lookup_affinity_review(
            machine,
            by_subgroup=by_subgroup,
            by_key=by_key,
            by_record=by_record,
            subgroup=subgroup,
        )
        row = project_record_affinity(
            machine,
            review,
            relationship_active=active,
            subgroup=subgroup,
        )
        flag = flag_evidence_affinity_inconsistency(row)
        row["evidence_affinity_inconsistency"] = flag
        projected.append(row)
    inconsistencies = tuple(
        dict(row) for row in projected if row.get("evidence_affinity_inconsistency")
    )
    return tuple(projected), inconsistencies


def summarise_affinity_projection(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, int]:
    counts = {
        "exact_scalar": 0,
        "retain_raw": 0,
        "exclude_non_affinity": 0,
        "park": 0,
        "unreviewed": 0,
        "deterministic_scalar_recovery": 0,
        "no_safe_scalar": 0,
        "evidence_affinity_inconsistency_records": 0,
    }
    flagged_records: set[str] = set()
    recovered: set[str] = set()
    no_scalar: set[str] = set()
    for row in rows:
        status = _blank(row.get("affinity_review_status"))
        record_id = _blank(row.get("record_id"))
        if status == AFFINITY_REVIEW_STATUS_EXACT:
            counts["exact_scalar"] += 1
            if _blank(row.get("affinity_value_molar")):
                recovered.add(record_id)
            else:
                no_scalar.add(record_id)
        elif status == AFFINITY_REVIEW_STATUS_RAW:
            counts["retain_raw"] += 1
            no_scalar.add(record_id)
        elif status == AFFINITY_REVIEW_STATUS_EXCLUDE:
            counts["exclude_non_affinity"] += 1
            no_scalar.add(record_id)
        elif status == AFFINITY_REVIEW_STATUS_PARK:
            counts["park"] += 1
            no_scalar.add(record_id)
        else:
            counts["unreviewed"] += 1
            no_scalar.add(record_id)
        if _blank(row.get("evidence_affinity_inconsistency")):
            flagged_records.add(record_id)
    counts["deterministic_scalar_recovery"] = len(recovered)
    counts["no_safe_scalar"] = len(no_scalar)
    counts["evidence_affinity_inconsistency_records"] = len(flagged_records)
    return counts


def dry_run_affinity_semantics(
    affinity_review_rows: Sequence[Mapping[str, str]],
    evidence_rows: Sequence[Mapping[str, str]],
    *,
    relationship_projection: RelationshipProjection | None = None,
) -> dict[str, object]:
    """Project split/outcome classes without writing review decisions."""
    proposal = propose_affinity_review_splits(affinity_review_rows, evidence_rows)
    member_reviews: dict[str, dict[str, str]] = {}
    by_key: dict[tuple[str, str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in evidence_rows:
        if _blank(row.get("affinity_requires_review")) != "true":
            continue
        if _blank(row.get("affinity_parse_status")) in {"", "absent"}:
            continue
        key = (
            _blank(row.get("source_db")),
            _blank(row.get("affinity_parse_status")),
            _blank(row.get("affinity_parse_rule")),
        )
        by_key[key].append(row)

    live_by_id = {_blank(row.get("decision_id")): row for row in affinity_review_rows}
    for group in proposal.groups:
        live = live_by_id.get(group.proposed_decision_id) or live_by_id.get(
            group.old_decision_id, {}
        )
        review = {
            "decision_id": group.proposed_decision_id,
            "manual_decision": group.proposed_outcome,
            "manual_affinity_transform_rule": group.transform_rule,
            "manual_affinity_non_affinity_reason": SUBGROUP_TO_NON_AFFINITY_REASON.get(
                group.subgroup, ""
            ),
            "manual_affinity_range_status": SUBGROUP_TO_RANGE_STATUS.get(group.subgroup, ""),
            "manual_affinity_qualifier": "",
            "manual_affinity_type": "Kd" if group.proposed_outcome != EXCLUDE_NON_AFFINITY else "",
            "manual_affinity_value": "",
            "manual_affinity_unit": "",
        }
        if group.subgroup == SUBGROUP_LOD:
            review["manual_affinity_type"] = "other"
        if group.subgroup == SUBGROUP_INEQUALITY:
            review["manual_affinity_qualifier"] = ""
        key = (
            group.source_db or _blank(live.get("source_db")),
            group.affinity_parse_status or _blank(live.get("affinity_parse_status")),
            group.affinity_parse_rule or _blank(live.get("affinity_parse_rule")),
        )
        allowed = set(group.record_ids)
        for item in by_key.get(key, []):
            record_id = _blank(item.get("record_id"))
            if record_id not in allowed:
                continue
            if classify_affinity_subgroup(item) != group.subgroup:
                continue
            member_reviews[f"{record_id}|{_blank(item.get('relationship_index'))}|{raw_key(item)}"] = review

    active_ids = _active_record_ids(relationship_projection)
    treat_unprojected_as_active = relationship_projection is None
    projected: list[dict[str, str]] = []
    for machine in evidence_rows:
        if _blank(machine.get("affinity_requires_review")) != "true":
            continue
        if _blank(machine.get("affinity_parse_status")) in {"", "absent"}:
            continue
        lookup = f"{_blank(machine.get('record_id'))}|{_blank(machine.get('relationship_index'))}|{raw_key(machine)}"
        review = member_reviews.get(lookup)
        record_id = _blank(machine.get("record_id"))
        active = treat_unprojected_as_active or record_id in active_ids
        subgroup = classify_affinity_subgroup(machine)
        row = project_record_affinity(
            machine,
            review,
            relationship_active=active,
            subgroup=subgroup,
        )
        row["evidence_affinity_inconsistency"] = flag_evidence_affinity_inconsistency(row)
        projected.append(row)

    unique_records = list(dict.fromkeys(_blank(row.get("record_id")) for row in projected))
    flagged_rows = [row for row in projected if row.get("evidence_affinity_inconsistency")]
    flagged_records = list(
        dict.fromkeys(_blank(row.get("record_id")) for row in flagged_rows)
    )
    flag_by_decision: dict[str, dict[str, object]] = {}
    for row in flagged_rows:
        decision_id = _blank(row.get("review_decision_id"))
        record_id = _blank(row.get("record_id"))
        kind = inconsistency_kind(row)
        entry = flag_by_decision.setdefault(
            decision_id,
            {"record_ids": [], "kinds": []},
        )
        ids = entry["record_ids"]
        kinds = entry["kinds"]
        if record_id and record_id not in ids:
            ids.append(record_id)
        if kind and kind not in kinds:
            kinds.append(kind)
    outcome_records = {
        "exact_scalar": set(),
        "retain_raw": set(),
        "exclude_non_affinity": set(),
        "park": set(),
    }
    recovered: set[str] = set()
    no_scalar: set[str] = set()
    for row in projected:
        record_id = _blank(row.get("record_id"))
        status = _blank(row.get("affinity_review_status"))
        if status == AFFINITY_REVIEW_STATUS_EXACT:
            outcome_records["exact_scalar"].add(record_id)
            if _blank(row.get("affinity_value_molar")):
                recovered.add(record_id)
            else:
                no_scalar.add(record_id)
        elif status == AFFINITY_REVIEW_STATUS_RAW:
            outcome_records["retain_raw"].add(record_id)
            no_scalar.add(record_id)
        elif status == AFFINITY_REVIEW_STATUS_EXCLUDE:
            outcome_records["exclude_non_affinity"].add(record_id)
            no_scalar.add(record_id)
        elif status == AFFINITY_REVIEW_STATUS_PARK:
            outcome_records["park"].add(record_id)
            no_scalar.add(record_id)
        else:
            no_scalar.add(record_id)

    return {
        "n_live_rows": proposal.n_live_rows,
        "n_proposed_rows": proposal.n_proposed_rows,
        "unsplit_decision_ids": list(proposal.unsplit_decision_ids),
        "split_decision_ids": list(proposal.split_decision_ids),
        "split_map": _as_split_map(proposal),
        "groups": [
            {
                "old_decision_id": group.old_decision_id,
                "proposed_decision_id": group.proposed_decision_id,
                "subgroup": group.subgroup,
                "proposed_outcome": group.proposed_outcome,
                "transform_rule": group.transform_rule,
                "n_records": group.n_records,
                "record_ids": list(group.record_ids),
            }
            for group in proposal.groups
        ],
        "outcome_class_record_counts": {
            key: len(value) for key, value in outcome_records.items()
        },
        "n_projected_rows": len(projected),
        "n_unique_records": len(unique_records),
        "deterministic_scalar_recovery_records": sorted(recovered),
        "n_deterministic_scalar_recovery": len(recovered),
        "n_no_safe_scalar": len(no_scalar),
        "n_evidence_affinity_inconsistency_records": len(flagged_records),
        "evidence_affinity_inconsistency_records": flagged_records,
        "evidence_affinity_inconsistency_by_decision": {
            decision_id: {
                "n_records": len(item["record_ids"]),  # type: ignore[arg-type]
                "record_ids": item["record_ids"],
                "kinds": item["kinds"],
            }
            for decision_id, item in flag_by_decision.items()
        },
        "application_blocked_by_evidence_affinity_inconsistency": bool(flagged_records),
        "outcome_class_review_row_counts": {
            CONFIRM_AFFINITY_SCALAR: sum(
                1
                for group in proposal.groups
                if group.proposed_outcome == CONFIRM_AFFINITY_SCALAR
            ),
            RETAIN_AFFINITY_RAW: sum(
                1 for group in proposal.groups if group.proposed_outcome == RETAIN_AFFINITY_RAW
            ),
            EXCLUDE_NON_AFFINITY: sum(
                1 for group in proposal.groups if group.proposed_outcome == EXCLUDE_NON_AFFINITY
            ),
            "park_unresolved": sum(
                1 for group in proposal.groups if group.proposed_outcome == "park_unresolved"
            ),
        },
    }


def raw_key(row: Mapping[str, str]) -> str:
    return "|".join(
        [
            _blank(row.get("affinity_value_raw")),
            _blank(row.get("affinity_unit_raw")),
        ]
    )


def collect_affinity_park_record_ids(
    *,
    target_review_rows: Sequence[Mapping[str, str]] = (),
    relationship_review_rows: Sequence[Mapping[str, str]] = (),
    relationship_scientific_rows: Sequence[Mapping[str, str]] = (),
) -> frozenset[str]:
    """Record IDs whose target or relationship review is parked. Provenance only."""
    parked: set[str] = set()
    for row in relationship_review_rows:
        if _blank(row.get("manual_decision")) == "park_unresolved":
            record_id = _blank(row.get("record_id"))
            if record_id:
                parked.add(record_id)
    parked_targets = {
        _blank(row.get("target_dictionary_id"))
        for row in target_review_rows
        if _blank(row.get("manual_decision")) == "park_unresolved"
        and _blank(row.get("target_dictionary_id"))
    }
    for row in relationship_scientific_rows:
        if _blank(row.get("target_dictionary_id")) in parked_targets:
            record_id = _blank(row.get("record_id"))
            if record_id:
                parked.add(record_id)
    return frozenset(parked)


def materialise_affinity_review_splits(
    affinity_review_rows: Sequence[Mapping[str, str]],
    evidence_rows: Sequence[Mapping[str, str]],
    *,
    columns: Sequence[str],
    parked_record_ids: frozenset[str] | Sequence[str] = (),
) -> tuple[list[dict[str, str]], ProposedAffinitySplit]:
    """Rewrite grouped affinity review rows to one scientific rule per row.

    Human decision fields are preserved by child decision ID when already
    present, and left blank for newly created children. The parent ID is not
    reused as a child. Reruns are idempotent: they do not append duplicates.
    Combined input is not modified.
    """
    if not columns:
        raise ScientificProposalError("affinity materialisation requires columns")
    proposal = propose_affinity_review_splits(affinity_review_rows, evidence_rows)
    existing_by_id = {
        _blank(row.get("decision_id")): dict(row) for row in affinity_review_rows
    }
    parked = {item for item in parked_record_ids if item}
    out: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for group in proposal.groups:
        decision_id = group.proposed_decision_id
        if decision_id in seen_ids:
            raise ScientificProposalError(f"duplicate affinity decision id {decision_id}")
        if (
            decision_id in proposal.split_decision_ids
            and decision_id == group.old_decision_id
        ):
            raise ScientificProposalError(
                f"split parent {group.old_decision_id} must not be reused as a child"
            )
        seen_ids.add(decision_id)
        park_ids = [item for item in group.record_ids if item in parked]
        machine = {
            "decision_id": decision_id,
            "parent_decision_id": group.old_decision_id,
            "source_db": group.source_db,
            "affinity_parse_status": group.affinity_parse_status,
            "affinity_parse_rule": group.affinity_parse_rule,
            "affinity_subgroup": group.subgroup,
            "affinity_type_proposed": group.affinity_type_proposed,
            "n_records": str(group.n_records),
            "record_ids": join_unique(list(group.record_ids)),
            "record_ids_preview": _preview_ids(group.record_ids),
            "affinity_raw_examples": join_unique(list(group.raw_examples)),
            "scientific_ambiguity_reason": SUBGROUP_AMBIGUITY_REASON.get(
                group.subgroup, group.subgroup
            ),
            "review_consequence": group.proposed_outcome,
            "machine_recommendation": "review_affinity_parse",
            "machine_affinity_transform_rule": group.transform_rule,
            "park_provenance_record_ids": join_unique(park_ids),
            **blank_affinity_human_fields(),
        }
        existing = existing_by_id.get(decision_id)
        if existing is not None:
            for field in AFFINITY_HUMAN_FIELDS:
                machine[field] = existing.get(field, "")
        row = fill_row(columns, machine)
        if existing is None:
            assert_affinity_human_fields_blank(
                row, label=f"affinity review {decision_id}"
            )
        if row["decision_id"] != decision_id:
            raise ScientificProposalError(
                f"affinity review row lost decision id {decision_id}"
            )
        out.append(row)
    expected_ids = [group.proposed_decision_id for group in proposal.groups]
    if [row["decision_id"] for row in out] != expected_ids:
        raise ScientificProposalError("affinity materialisation lost decision-id order")
    if len(out) != len(set(expected_ids)):
        raise ScientificProposalError("affinity materialisation produced duplicate ids")
    return out, proposal


AFFINITY_HUMAN_FIELDS = (*HUMAN_FIELDS, *AFFINITY_EXTRA_HUMAN_FIELDS)

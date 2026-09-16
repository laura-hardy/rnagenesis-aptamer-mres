"""Deterministic affinity parsing and molar normalisation proposals."""

from __future__ import annotations

import re
from typing import Mapping

UNIT_TO_MOLAR: dict[str, float] = {
    "m": 1.0,
    "mm": 1e-3,
    "um": 1e-6,
    "µm": 1e-6,
    "μm": 1e-6,
    "nm": 1e-9,
    "pm": 1e-12,
    "fm": 1e-15,
}

TYPE_ALIASES: dict[str, str] = {
    "kd": "Kd",
    "affinity (kd)": "Kd",
    "affinity(kd)": "Kd",
    "dissociation constant": "Kd",
    "ka": "Ka",
    "ic50": "IC50",
    "ec50": "EC50",
    "ki": "Ki",
}

BLANK_TOKENS = frozenset(
    {"", "n/a", "na", "na.", "none", ".", "-", "'-", "np", "see source (non-kd)", "see reference"}
)
RANGE_RE = re.compile(r"(?i)(?:\d.*[-–—to]+\s*\d)|(?:\band\b)")
INEQUALITY_RE = re.compile(r"<<|>>|[<>≤≥]|<=|>=|less than|greater than")
APPROX_RE = re.compile(r"[~≈]|approx")
NUMBER_RE = re.compile(
    r"^[±+]?\s*(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(?:±\s*\d+(?:\.\d+)?)?\s*$"
)
# Hyphens that belong to 2e-5 / 10^-5 / 2 x 10^-5, not numeric ranges.
SCI_EXPONENT_RE = re.compile(
    r"(?i)(?:[eE][+-]?\d+)|(?:[x×]\s*10\s*\^\s*[+-]?\d+)|(?:10\s*\^\s*[+-]?\d+)"
)
SCI_TIMES_TEN_RE = re.compile(
    r"(?i)(\d+(?:\.\d+)?)\s*[x×]\s*10\s*\^\s*([+-]?\d+)"
)
# Word-boundary-before-unit fails on glued 50nM; allow a preceding digit.
UNIT_IN_TEXT_RE = re.compile(r"(?i)(?<![A-Za-z])(fM|pM|nM|uM|µM|μm|mM|M)\b")
UNCERTAINTY_RE = re.compile(
    r"(?i)±\s*\d+(?:\.\d+)?(?:\s*(?:fM|pM|nM|uM|µM|μm|mM|M))?"
)
TYPE_PREFIX_RE = re.compile(r"(?i)^(?:kd|ki|ic50|ec50|ka)\s*[:=]?\s*")
BLANK_WITH_UNIT_RE = re.compile(
    r"(?i)^(n/?a|na|na\.|none|np)\s*(?:fM|pM|nM|uM|µM|μm|mM|M)?$"
)


def _norm_unit(unit: str) -> str:
    text = (unit or "").strip().casefold().replace("μ", "µ")
    text = text.replace("u m", "um")
    return text


def _hyphens_are_scientific_exponents(text: str) -> bool:
    """True when every hyphen/en-dash is an exponent, not a numeric range."""
    stripped = SCI_EXPONENT_RE.sub("", text)
    return not re.search(r"[-–—]", stripped)


def _rewrite_scientific_times_ten(text: str) -> str:
    """Rewrite ``2 x 10^-5`` to ``2e-5`` so the scalar parser can read it."""
    return SCI_TIMES_TEN_RE.sub(r"\1e\2", text)


def canonical_affinity_type(raw_type: str) -> str:
    key = re.sub(r"\s+", " ", (raw_type or "").strip()).casefold()
    if key in {"lod", "limit of detection"}:
        return ""
    return TYPE_ALIASES.get(key, "")


def parse_affinity_value(
    raw_value: str,
    *,
    unit: str = "",
    affinity_type: str = "",
) -> dict[str, str]:
    """Safely parse a source affinity string.

    Ranges, inequalities, approximate verbal values, multiple values, and
    malformed units remain unconverted. LOD is not treated as a binding type.
    Hyphens that belong to scientific notation are not treated as ranges.
    """
    raw = (raw_value or "").strip()
    unit_raw = (unit or "").strip()
    type_raw = (affinity_type or "").strip()
    proposed_type = canonical_affinity_type(type_raw)
    if not proposed_type and type_raw:
        folded = type_raw.casefold()
        if "kd" in folded:
            proposed_type = "Kd"
        elif folded in {"ki"}:
            proposed_type = "Ki"
        elif "ic50" in folded:
            proposed_type = "IC50"
        elif "ec50" in folded:
            proposed_type = "EC50"
        elif folded in {"ka"}:
            proposed_type = "Ka"
        elif folded in {"lod"}:
            proposed_type = ""
        else:
            proposed_type = "other" if raw else ""

    result = {
        "affinity_type_proposed": proposed_type,
        "affinity_value_raw": raw,
        "affinity_unit_raw": unit_raw,
        "affinity_value_molar_proposed": "",
        "affinity_parse_status": "absent",
        "affinity_parse_rule": "",
        "affinity_requires_review": "false",
    }
    token = raw.casefold().strip()
    if token in BLANK_TOKENS:
        result["affinity_parse_status"] = "absent"
        result["affinity_parse_rule"] = "blank_or_unavailable"
        return result
    if not raw:
        return result

    rewritten = _rewrite_scientific_times_ten(raw)
    label_stripped = TYPE_PREFIX_RE.sub("", rewritten).strip()
    if label_stripped.casefold() in BLANK_TOKENS or BLANK_WITH_UNIT_RE.match(label_stripped):
        result["affinity_parse_status"] = "absent"
        result["affinity_parse_rule"] = "blank_or_unavailable"
        return result

    range_candidate = RANGE_RE.search(rewritten) or (
        re.search(r"\d.+\d", rewritten)
        and ("-" in rewritten or "–" in rewritten or "—" in rewritten or " and " in rewritten.casefold())
    )
    if range_candidate and (
        re.search(r"[-–—]", rewritten) or re.search(r"(?i)\band\b", rewritten)
    ):
        if not _hyphens_are_scientific_exponents(rewritten) and not NUMBER_RE.match(
            rewritten.replace(" ", "")
        ):
            result["affinity_parse_status"] = "range_or_multiple"
            result["affinity_parse_rule"] = "range_or_multiple_not_scalar"
            result["affinity_requires_review"] = "true"
            if not proposed_type:
                result["affinity_type_proposed"] = "Kd" if "kd" in type_raw.casefold() else "other"
            return result

    if INEQUALITY_RE.search(rewritten):
        result["affinity_parse_status"] = "inequality"
        result["affinity_parse_rule"] = "inequality_not_scalar"
        result["affinity_requires_review"] = "true"
        return result
    if APPROX_RE.search(rewritten) and not NUMBER_RE.match(
        re.sub(r"[~≈]", "", rewritten).strip()
    ):
        result["affinity_parse_status"] = "approximate"
        result["affinity_parse_rule"] = "approximate_not_scalar"
        result["affinity_requires_review"] = "true"
        return result

    stripped = label_stripped.replace("μ", "µ")
    embedded_unit = ""
    unit_match = UNIT_IN_TEXT_RE.search(stripped)
    if unit_match:
        embedded_unit = unit_match.group(1)
        stripped = stripped[: unit_match.start()] + stripped[unit_match.end() :]
        stripped = stripped.strip(" ,;")
    if APPROX_RE.search(stripped):
        stripped = re.sub(r"[~≈]", "", stripped).strip()
        result["affinity_parse_rule"] = "approximate_prefix_stripped_if_scalar"
    if INEQUALITY_RE.search(stripped):
        result["affinity_parse_status"] = "inequality"
        result["affinity_parse_rule"] = "inequality_not_scalar"
        result["affinity_requires_review"] = "true"
        return result
    if (
        re.search(r"(?i)\b(?:and|to)\b|[-–—]", stripped)
        and not _hyphens_are_scientific_exponents(stripped)
        and not NUMBER_RE.match(stripped.replace(" ", ""))
    ):
        result["affinity_parse_status"] = "range_or_multiple"
        result["affinity_parse_rule"] = "range_or_multiple_not_scalar"
        result["affinity_requires_review"] = "true"
        return result

    stripped = UNCERTAINTY_RE.sub("", stripped).strip()
    scalar = re.sub(r"\s+", "", stripped)
    match = re.fullmatch(r"(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", scalar)
    if match is None:
        result["affinity_parse_status"] = "malformed"
        result["affinity_parse_rule"] = "unparseable_numeric"
        result["affinity_requires_review"] = "true"
        return result

    number = float(match.group(1))
    unit_key = _norm_unit(unit_raw or embedded_unit)
    if not unit_key:
        result["affinity_parse_status"] = "missing_unit"
        result["affinity_parse_rule"] = "numeric_without_unit"
        result["affinity_requires_review"] = "true"
        return result
    factor = UNIT_TO_MOLAR.get(unit_key)
    if factor is None:
        result["affinity_parse_status"] = "malformed"
        result["affinity_parse_rule"] = "unsupported_unit"
        result["affinity_requires_review"] = "true"
        return result
    molar = number * factor
    molar_text = f"{molar:.12g}"
    result["affinity_value_molar_proposed"] = molar_text
    result["affinity_parse_status"] = "normalised"
    result["affinity_parse_rule"] = result["affinity_parse_rule"] or "scalar_unit_to_molar"
    if not proposed_type:
        result["affinity_type_proposed"] = "Kd"
    return result


def parse_affinity_from_text(text: str) -> dict[str, str]:
    """Parse a free-text affinity field such as UTexas/RiboAptamer Kd: 5 nM."""
    raw = (text or "").strip()
    if not raw:
        return parse_affinity_value("", unit="", affinity_type="")
    type_hint = ""
    folded = raw.casefold()
    if folded.startswith("kd"):
        type_hint = "Kd"
    elif folded.startswith("ki"):
        type_hint = "Ki"
    elif "ic50" in folded[:8]:
        type_hint = "IC50"
    elif "ec50" in folded[:8]:
        type_hint = "EC50"
    unit = ""
    unit_match = UNIT_IN_TEXT_RE.search(raw)
    if unit_match:
        unit = unit_match.group(1)
    return parse_affinity_value(raw, unit=unit, affinity_type=type_hint or "Kd")

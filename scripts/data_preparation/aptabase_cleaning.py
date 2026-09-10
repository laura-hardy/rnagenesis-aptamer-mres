"""Conservative cleaning and QC helpers for AptaBase raw records.

Scientific choices are intentionally cautious:
- raw website text is never overwritten;
- sequences are not converted between T and U;
- missing affinity / missing sequence alone do not invalidate a record;
- energy units (kcal/mol) are not treated as molar affinities.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import ftfy
import pandas as pd

logger = logging.getLogger(__name__)

CLEANED_COLUMNS = [
    "record_id",
    "aptamer_name",
    "target_general",
    "target_specific",
    "reported_length",
    "affinity_raw",
    "affinity_measurement_type",
    "affinity_relation",
    "affinity_value",
    "affinity_uncertainty",
    "affinity_lower",
    "affinity_upper",
    "affinity_unit",
    "affinity_molar",
    "buffer",
    "gc_content_raw",
    "gc_content_reported",
    "gc_content_calculated",
    "gc_content_difference",
    "sequence_raw",
    "sequence_clean",
    "sequence_length_calculated",
    "sequence_alphabet",
    "molecule_type_inferred",
    "sequence_normalization_status",
    "reference",
    "doi",
    "pmid",
    "duplicate_group",
    "record_validity",
    "source_page",
    "source_url",
    "parse_warnings",
]

NUCLEOTIDE_CHARS = set("ACGTUN")
DNA_CHARS = set("ACGT")
RNA_CHARS = set("ACGU")

UNIT_TO_MOLAR = {
    "M": 1.0,
    "mM": 1e-3,
    "µM": 1e-6,
    "uM": 1e-6,
    "nM": 1e-9,
    "pM": 1e-12,
    "fM": 1e-15,
}

UNIT_ALIASES = {
    "m": "M",
    "mm": "mM",
    "um": "µM",
    "μm": "µM",
    "µM": "µM",
    "μmolar": "µM",
    "umolar": "µM",
    "micromolar": "µM",
    "micro molar": "µM",
    "nm": "nM",
    "pm": "pM",
    "fm": "fM",
}

DOI_RE = re.compile(
    r"(?:doi\s*[:=]\s*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.IGNORECASE,
)
PMID_RE = re.compile(r"\bPMID\s*[:=]?\s*(\d{5,9})\b", re.IGNORECASE)

# Terminal labels such as 5'-...-3' or 5′ ... 3′
TERMINAL_LABEL_RE = re.compile(
    r"(?i)(?:^|[\s\"'‘’“”\-–—])*([53]['′’])(?:[\s\"'‘’“”\-–—]*)|"
    r"(?:[\s\"'‘’“”\-–—])*([53]['′’])(?:[\s\"'‘’“”\-–—])*$"
)

T7_PROMOTER_HINT_RE = re.compile(r"TAATACGACTCACTATA", re.IGNORECASE)
RNA_APTAMER_HINT_RE = re.compile(r"\bRNA\s+aptamer\b|\bribozyme\b|\bRNA\s+ligand\b", re.IGNORECASE)

ENERGY_RE = re.compile(r"kcal(?:\.|\s*/?\s*)mol(?:e)?-?1|kcal\s*/\s*mol", re.IGNORECASE)

AFFINITY_NA_RE = re.compile(r"^\s*(?:n/?a|na|none|null|-|–|—)\b", re.IGNORECASE)


def repair_text(text: str) -> tuple[str, bool]:
    """Repair common mojibake with ftfy; return (repaired, changed).

    Does not attempt aggressive reconstruction of placeholders such as
    ``TGF-??1`` where the intended character is ambiguous.
    """
    if text is None:
        return "", False
    original = str(text)
    if original == "":
        return "", False
    repaired = ftfy.fix_text(original)
    # Normalise a few leftover Windows-1252 / UTF-8 artefacts that sometimes
    # remain after a single ftfy pass on mixed encodings.
    replacements = {
        "Â±": "±",
        "Î¼": "µ",
        "Î¼M": "µM",
        "â€“": "–",
        "â€”": "—",
        "â€™": "’",
        "Âµg": "µg",
    }
    for bad, good in replacements.items():
        if bad in repaired:
            repaired = repaired.replace(bad, good)
    # Prefer micro sign for molar units for consistency with biological text.
    repaired = repaired.replace("μM", "µM").replace("μg", "µg")
    return repaired, repaired != original


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text if text else None


def parse_reported_length(text: str) -> tuple[float | None, list[str]]:
    """Parse a reported length value if it is numeric."""
    warnings: list[str] = []
    cleaned = (text or "").strip()
    if not cleaned:
        warnings.append("reported_length_missing")
        return None, warnings
    match = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if not match:
        warnings.append("reported_length_nonnumeric")
        return None, warnings
    return float(cleaned), warnings


def normalise_sequence(sequence_raw: str) -> dict[str, Any]:
    """Conservatively normalise a displayed aptamer sequence."""
    warnings: list[str] = []
    raw = sequence_raw if sequence_raw is not None else ""
    raw = str(raw)

    if not raw.strip():
        return {
            "sequence_clean": "",
            "sequence_length_calculated": None,
            "sequence_alphabet": "missing",
            "molecule_type_inferred": "missing",
            "sequence_normalization_status": "missing",
            "warnings": ["sequence_missing"],
        }

    working = raw
    removed_terminal_labels = False

    # Remove 5'/3' terminal labels and surrounding punctuation/quotes/dashes.
    # Include corrupted primes commonly seen in saved HTML (�, ?, �) so that
    # encoding damage around terminal labels does not invalidate an otherwise
    # nucleotide sequence.
    terminal_marker = r"['′’`´\?？�]"
    before = working
    working = re.sub(
        rf"(?i)(^|[\s\"'‘’“”\-–—]+)[53]{terminal_marker}",
        r"\1",
        working,
    )
    working = re.sub(
        rf"(?i)[53]{terminal_marker}([\s\"'‘’“”\-–—]+|$)",
        r"\1",
        working,
    )
    # Also strip bare leading/trailing 5-/3- ornaments left after prime loss.
    working = re.sub(r"(?i)^[\s\"'‘’“”]*[53][\s\-–—]+", "", working)
    working = re.sub(r"(?i)[\s\-–—]+[53][\s\"'‘’“”]*$", "", working)
    if working != before:
        removed_terminal_labels = True

    # Remove remaining quotes often used as terminal markers.
    working = working.replace('"', "").replace("'", "").replace("‘", "").replace("’", "")
    working = working.replace("“", "").replace("”", "")

    # Remove whitespace and common separators used only for display.
    working = re.sub(r"[\s\-–—]+", "", working)
    working = working.upper()

    if not working:
        return {
            "sequence_clean": "",
            "sequence_length_calculated": None,
            "sequence_alphabet": "missing",
            "molecule_type_inferred": "missing",
            "sequence_normalization_status": "missing",
            "warnings": ["sequence_empty_after_formatting_removal"],
        }

    letters = [ch for ch in working if ch.isalpha()]
    non_letters = [ch for ch in working if not ch.isalpha()]
    letter_set = set(letters)

    # Substantial non-nucleotide content after formatting removal => invalid.
    nucleotide_like = letter_set <= NUCLEOTIDE_CHARS
    if non_letters or not nucleotide_like:
        # Allow a few non-letter characters only if almost everything is nucleotide.
        non_nuc_fraction = 0.0
        if working:
            non_nuc = sum(1 for ch in working if ch not in NUCLEOTIDE_CHARS)
            non_nuc_fraction = non_nuc / len(working)
        if non_nuc_fraction > 0.05 or not nucleotide_like:
            warnings.append("sequence_contains_non_nucleotide_characters")
            return {
                "sequence_clean": working,
                "sequence_length_calculated": len(working),
                "sequence_alphabet": "invalid",
                "molecule_type_inferred": "invalid",
                "sequence_normalization_status": "invalid",
                "warnings": warnings,
            }

    has_t = "T" in letter_set
    has_u = "U" in letter_set
    has_n = "N" in letter_set

    if has_t and has_u:
        alphabet = "mixed_T_U"
        status = "mixed_t_u"
        molecule = "mixed_or_uncertain"
        warnings.append("sequence_contains_both_T_and_U")
    elif has_n and letter_set <= (DNA_CHARS | RNA_CHARS | {"N"}):
        alphabet = "ambiguous"
        status = "ambiguous"
        molecule = "mixed_or_uncertain"
        warnings.append("sequence_contains_ambiguous_N")
    elif letter_set <= DNA_CHARS:
        alphabet = "DNA"
        status = "success"
        molecule = "DNA_like_sequence"
    elif letter_set <= RNA_CHARS:
        alphabet = "RNA"
        status = "success"
        molecule = "RNA_like_sequence"
    else:
        alphabet = "invalid"
        status = "invalid"
        molecule = "invalid"
        warnings.append("sequence_alphabet_unrecognised")

    if removed_terminal_labels and status == "success":
        status = "success_with_terminal_labels_removed"

    return {
        "sequence_clean": "".join(letters) if alphabet != "invalid" else working,
        "sequence_length_calculated": len(letters) if alphabet != "invalid" else len(working),
        "sequence_alphabet": alphabet,
        "molecule_type_inferred": molecule,
        "sequence_normalization_status": status,
        "warnings": warnings,
        "removed_terminal_labels": removed_terminal_labels,
    }


def refine_molecule_type(
    molecule_type: str,
    sequence_alphabet: str,
    sequence_clean: str,
    reference: str,
) -> tuple[str, list[str]]:
    """Optionally mark DNA-like sequences that may be RNA transcription templates."""
    warnings: list[str] = []
    if molecule_type != "DNA_like_sequence":
        return molecule_type, warnings
    ref = reference or ""
    looks_like_rna_paper = bool(RNA_APTAMER_HINT_RE.search(ref))
    has_promoter = bool(T7_PROMOTER_HINT_RE.search(sequence_clean or ""))
    if looks_like_rna_paper and (sequence_alphabet == "DNA" or has_promoter):
        warnings.append("possible_DNA_template_for_RNA_from_reference")
        return "possible_DNA_template_for_RNA", warnings
    return molecule_type, warnings


def parse_gc_content(text: str) -> tuple[float | None, list[str]]:
    """Parse reported GC content into a percentage float."""
    warnings: list[str] = []
    cleaned = (text or "").strip()
    if not cleaned or AFFINITY_NA_RE.match(cleaned):
        warnings.append("gc_content_missing")
        return None, warnings
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*%?", cleaned)
    if not match:
        warnings.append("gc_content_unparseable")
        return None, warnings
    return float(match.group(1)), warnings


def calculate_gc_content(sequence_clean: str, alphabet: str) -> float | None:
    """Calculate GC% from a clean DNA/RNA sequence."""
    if not sequence_clean or alphabet not in {"DNA", "RNA", "ambiguous", "mixed_T_U"}:
        return None
    if alphabet == "invalid" or alphabet == "missing":
        return None
    seq = sequence_clean.upper()
    length = len(seq)
    if length == 0:
        return None
    gc = sum(1 for ch in seq if ch in {"G", "C"})
    return 100.0 * gc / length


def _normalise_unit(unit_text: str | None) -> str | None:
    if not unit_text:
        return None
    compact = re.sub(r"\s+", " ", unit_text.strip())
    key = compact.lower().replace("μ", "µ")
    key_nospace = key.replace(" ", "")
    if key in UNIT_ALIASES:
        return UNIT_ALIASES[key]
    if key_nospace in UNIT_ALIASES:
        return UNIT_ALIASES[key_nospace]
    # Direct canonical forms
    for canonical in ("µM", "mM", "nM", "pM", "fM", "M"):
        if compact == canonical or key == canonical.lower():
            return canonical
    if key_nospace in {"micromolar", "μm", "um"}:
        return "µM"
    return None


def parse_affinity(affinity_raw: str) -> dict[str, Any]:
    """Parse heterogeneous affinity strings into structured fields."""
    warnings: list[str] = []
    raw = (affinity_raw or "").strip()
    result = {
        "affinity_measurement_type": "",
        "affinity_relation": "",
        "affinity_value": None,
        "affinity_uncertainty": None,
        "affinity_lower": None,
        "affinity_upper": None,
        "affinity_unit": "",
        "affinity_molar": None,
        "warnings": warnings,
    }

    if not raw:
        result["affinity_measurement_type"] = "missing"
        warnings.append("affinity_missing")
        return result

    repaired, _ = repair_text(raw)
    text = repaired.strip()

    if ENERGY_RE.search(text):
        result["affinity_measurement_type"] = "energy_or_other"
        warnings.append("affinity_energy_unit_not_molar")
        # Still capture a leading number for transparency, without molar conversion.
        number_match = re.search(r"([-+]?\d+(?:\.\d+)?)", text)
        if number_match:
            result["affinity_value"] = float(number_match.group(1))
            result["affinity_relation"] = "exact"
        return result

    # Values such as "na nM" or "NA" must not become zero.
    if AFFINITY_NA_RE.match(text) or re.fullmatch(r"(?i)n/?a(?:\s*[a-zµμ]*)?", text):
        result["affinity_measurement_type"] = "unavailable"
        warnings.append("affinity_unavailable")
        return result

    # Less-than / greater-than
    inequality = re.match(
        r"^\s*([<>]=?|≤|≥)\s*([-+]?\d+(?:\.\d+)?)\s*([A-Za-zµμμ/. ]+)?\s*$",
        text,
    )
    if inequality:
        relation_map = {"<": "lt", "<=": "lte", "≤": "lte", ">": "gt", ">=": "gte", "≥": "gte"}
        result["affinity_relation"] = relation_map.get(inequality.group(1), inequality.group(1))
        result["affinity_value"] = float(inequality.group(2))
        unit = _normalise_unit(inequality.group(3))
        result["affinity_unit"] = unit or ""
        result["affinity_measurement_type"] = "concentration"
        if unit and unit in UNIT_TO_MOLAR:
            result["affinity_molar"] = result["affinity_value"] * UNIT_TO_MOLAR[unit]
        elif not unit:
            warnings.append("affinity_unit_missing")
        return result

    # Plus/minus uncertainty: 13.1 ± 2.10 µM or 0.3337 (+/-) 0.1485
    pm = re.search(
        r"([-+]?\d+(?:\.\d+)?)\s*(?:±|\+/-|\(\+/-\)|\(\±\))\s*([-+]?\d+(?:\.\d+)?)"
        r"(?:\s*([A-Za-zµμμ/. ]+))?",
        text,
    )
    if pm:
        value = float(pm.group(1))
        uncertainty = float(pm.group(2))
        unit = _normalise_unit(pm.group(3)) if pm.group(3) else None
        # Sometimes unit appears elsewhere in the string.
        if unit is None:
            unit_match = re.search(
                r"(micro\s*molar|micromolar|µM|μM|uM|nM|pM|fM|mM|\bM\b)",
                text,
                re.IGNORECASE,
            )
            if unit_match:
                unit = _normalise_unit(unit_match.group(1))
        result["affinity_measurement_type"] = "concentration"
        result["affinity_relation"] = "exact"
        result["affinity_value"] = value
        result["affinity_uncertainty"] = uncertainty
        result["affinity_unit"] = unit or ""
        if unit and unit in UNIT_TO_MOLAR:
            result["affinity_molar"] = value * UNIT_TO_MOLAR[unit]
        else:
            warnings.append("affinity_unit_missing")
        return result

    # Numeric range: 10-20 nM
    range_match = re.search(
        r"([-+]?\d+(?:\.\d+)?)\s*[-–—to]+\s*([-+]?\d+(?:\.\d+)?)\s*([A-Za-zµμμ/. ]+)?",
        text,
        re.IGNORECASE,
    )
    if range_match:
        lower = float(range_match.group(1))
        upper = float(range_match.group(2))
        unit = _normalise_unit(range_match.group(3))
        result["affinity_measurement_type"] = "concentration"
        result["affinity_relation"] = "range"
        result["affinity_lower"] = lower
        result["affinity_upper"] = upper
        result["affinity_value"] = (lower + upper) / 2.0
        result["affinity_unit"] = unit or ""
        if unit and unit in UNIT_TO_MOLAR:
            result["affinity_molar"] = result["affinity_value"] * UNIT_TO_MOLAR[unit]
        else:
            warnings.append("affinity_unit_missing")
        return result

    # Simple value + unit: 35.6 nM
    simple = re.search(
        r"([-+]?\d+(?:\.\d+)?)\s*(micro\s*molar|micromolar|µM|μM|uM|nM|pM|fM|mM|\bM\b)?",
        text,
        re.IGNORECASE,
    )
    if simple:
        value = float(simple.group(1))
        unit = _normalise_unit(simple.group(2)) if simple.group(2) else None
        result["affinity_measurement_type"] = "concentration" if unit else "numeric_no_unit"
        result["affinity_relation"] = "exact"
        result["affinity_value"] = value
        result["affinity_unit"] = unit or ""
        if unit and unit in UNIT_TO_MOLAR:
            result["affinity_molar"] = value * UNIT_TO_MOLAR[unit]
        else:
            warnings.append("affinity_unit_missing")
        return result

    result["affinity_measurement_type"] = "unparsed"
    warnings.append("affinity_unparsed")
    return result


def extract_doi(reference: str) -> str:
    """Extract a DOI without URL prefixes, or empty string."""
    if not reference:
        return ""
    match = DOI_RE.search(reference)
    if not match:
        return ""
    doi = match.group(1).rstrip(" .);,]")
    # Strip accidental URL path leftovers
    if doi.lower().startswith("http"):
        path = urlparse(doi).path
        doi = path.lstrip("/")
    return doi


def extract_pmid(reference: str) -> str:
    """Extract an explicit PMID if present."""
    if not reference:
        return ""
    match = PMID_RE.search(reference)
    return match.group(1) if match else ""


def _normalise_for_duplicate_key(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def assign_duplicate_groups(cleaned: pd.DataFrame) -> pd.DataFrame:
    """Assign duplicate_group IDs for probable same-aptamer clusters.

    Key: normalised name + normalised specific target + reported length.
    Records that do not share a key with another row remain blank.
    """
    frame = cleaned.copy()
    keys: list[str] = []
    for _, row in frame.iterrows():
        name = _normalise_for_duplicate_key(str(row.get("aptamer_name", "")))
        target = _normalise_for_duplicate_key(str(row.get("target_specific", "")))
        length = row.get("reported_length")
        length_key = "" if length is None or (isinstance(length, float) and math.isnan(length)) else str(int(length) if float(length).is_integer() else length)
        if not name:
            keys.append("")
            continue
        keys.append(f"{name}|{target}|{length_key}")

    frame["_dup_key"] = keys
    key_counts = Counter(k for k in keys if k)
    group_ids: dict[str, str] = {}
    next_id = 1
    assigned: list[str] = []
    for key in keys:
        if key and key_counts[key] >= 2:
            if key not in group_ids:
                group_ids[key] = f"dup_{next_id:04d}"
                next_id += 1
            assigned.append(group_ids[key])
        else:
            assigned.append("")
    frame["duplicate_group"] = assigned
    frame = frame.drop(columns=["_dup_key"])
    return frame


def assess_record_validity(row: dict[str, Any], warnings: list[str]) -> str:
    """Decide valid / valid_with_warnings / invalid for one cleaned row.

    Missing sequence or unavailable affinity alone should not invalidate.
    Strong multi-field spam / nonsense patterns should.
    """
    strong_problems = 0

    record_id = row.get("record_id")
    if record_id is None:
        strong_problems += 1
        warnings.append("record_id_nonnumeric")

    if row.get("reported_length") is None and "reported_length_nonnumeric" in warnings:
        strong_problems += 1

    alphabet = row.get("sequence_alphabet")
    if alphabet == "invalid":
        strong_problems += 1

    target_general = (row.get("target_general") or "").strip()
    nonsense_targets = {"skks", "test", "asdf", "xxx", "na", "n/a"}
    if target_general.lower() in nonsense_targets:
        strong_problems += 1
        warnings.append("target_general_nonsensical")

    # Short random-looking fields across multiple columns.
    short_random = 0
    for field in ("aptamer_name", "target_general", "buffer", "sequence_clean", "reference"):
        value = (row.get(field) or "").strip()
        if value and len(value) <= 6 and re.fullmatch(r"[A-Za-z]{2,6}", value):
            # Common real short names like B3/B4 are 2 chars and valid; require
            # repeated junk-like pattern or several short fields together.
            short_random += 1
    if short_random >= 3:
        strong_problems += 1
        warnings.append("multiple_short_random_fields")

    reference = (row.get("reference") or "").strip()
    if reference and len(reference) <= 6 and not extract_doi(reference):
        # Placeholder-like reference
        if re.fullmatch(r"[A-Za-z]{2,6}", reference):
            strong_problems += 1
            warnings.append("reference_implausible_placeholder")

    if strong_problems >= 2:
        return "invalid"
    if warnings:
        return "valid_with_warnings"
    return "valid"


def clean_raw_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Convert a raw AptaBase DataFrame into the cleaned schema."""
    cleaned_rows: list[dict[str, Any]] = []

    for _, raw in raw_df.iterrows():
        warnings: list[str] = []
        if raw.get("row_parse_warnings"):
            warnings.append(str(raw["row_parse_warnings"]))

        text_fields = {}
        for raw_key, clean_key in [
            ("aptamer_name_raw", "aptamer_name"),
            ("target_general_raw", "target_general"),
            ("target_specific_raw", "target_specific"),
            ("affinity_raw", "affinity_raw_preserved"),
            ("buffer_raw", "buffer"),
            ("gc_content_raw", "gc_content_raw"),
            ("sequence_raw", "sequence_raw"),
            ("reference_raw", "reference"),
        ]:
            repaired, changed = repair_text(str(raw.get(raw_key, "") or ""))
            text_fields[clean_key] = repaired
            if changed:
                warnings.append(f"mojibake_repaired:{clean_key}")

        record_id_raw = str(raw.get("record_id_raw", "") or "").strip()
        record_id: int | None
        if re.fullmatch(r"\d+", record_id_raw):
            record_id = int(record_id_raw)
        else:
            record_id = None
            warnings.append("record_id_nonnumeric")

        reported_length, length_warnings = parse_reported_length(
            str(raw.get("reported_length_raw", "") or "")
        )
        warnings.extend(length_warnings)

        seq_info = normalise_sequence(text_fields["sequence_raw"])
        warnings.extend(seq_info["warnings"])

        molecule_type, mol_warnings = refine_molecule_type(
            seq_info["molecule_type_inferred"],
            seq_info["sequence_alphabet"],
            seq_info["sequence_clean"],
            text_fields["reference"],
        )
        warnings.extend(mol_warnings)

        seq_len = seq_info["sequence_length_calculated"]
        if reported_length is not None and seq_len is not None:
            diff = abs(reported_length - seq_len)
            if diff > 0:
                warnings.append("length_mismatch")
            if diff > 1:
                warnings.append("length_mismatch_gt_1")
        elif seq_info["sequence_alphabet"] == "missing":
            pass  # already warned

        gc_reported, gc_warnings = parse_gc_content(text_fields["gc_content_raw"])
        warnings.extend(gc_warnings)
        gc_calc = calculate_gc_content(
            seq_info["sequence_clean"],
            seq_info["sequence_alphabet"],
        )
        gc_diff = None
        if gc_reported is not None and gc_calc is not None:
            gc_diff = gc_calc - gc_reported
            if abs(gc_diff) > 0.5:
                warnings.append("gc_content_mismatch_gt_0.5")

        affinity = parse_affinity(text_fields["affinity_raw_preserved"])
        warnings.extend(affinity["warnings"])

        doi = extract_doi(text_fields["reference"])
        pmid = extract_pmid(text_fields["reference"])

        row = {
            "record_id": record_id,
            "aptamer_name": text_fields["aptamer_name"],
            "target_general": text_fields["target_general"],
            "target_specific": text_fields["target_specific"],
            "reported_length": reported_length,
            "affinity_raw": text_fields["affinity_raw_preserved"],
            "affinity_measurement_type": affinity["affinity_measurement_type"],
            "affinity_relation": affinity["affinity_relation"],
            "affinity_value": affinity["affinity_value"],
            "affinity_uncertainty": affinity["affinity_uncertainty"],
            "affinity_lower": affinity["affinity_lower"],
            "affinity_upper": affinity["affinity_upper"],
            "affinity_unit": affinity["affinity_unit"],
            "affinity_molar": affinity["affinity_molar"],
            "buffer": text_fields["buffer"],
            "gc_content_raw": text_fields["gc_content_raw"],
            "gc_content_reported": gc_reported,
            "gc_content_calculated": gc_calc,
            "gc_content_difference": gc_diff,
            "sequence_raw": text_fields["sequence_raw"],
            "sequence_clean": seq_info["sequence_clean"],
            "sequence_length_calculated": seq_len,
            "sequence_alphabet": seq_info["sequence_alphabet"],
            "molecule_type_inferred": molecule_type,
            "sequence_normalization_status": seq_info["sequence_normalization_status"],
            "reference": text_fields["reference"],
            "doi": doi,
            "pmid": pmid,
            "duplicate_group": "",
            "record_validity": "",
            "source_page": raw.get("source_page"),
            "source_url": raw.get("source_url"),
            "parse_warnings": "",
        }

        # Deduplicate warnings while preserving order.
        unique_warnings: list[str] = []
        seen = set()
        for warning in warnings:
            if warning and warning not in seen:
                unique_warnings.append(warning)
                seen.add(warning)

        row["record_validity"] = assess_record_validity(row, unique_warnings)
        row["parse_warnings"] = "; ".join(unique_warnings)
        cleaned_rows.append(row)

    cleaned = pd.DataFrame(cleaned_rows)
    if cleaned.empty:
        return pd.DataFrame(columns=CLEANED_COLUMNS)
    cleaned = assign_duplicate_groups(cleaned)
    return cleaned[CLEANED_COLUMNS]


def _missing_id_ranges(sorted_ids: list[int]) -> list[str]:
    if len(sorted_ids) < 2:
        return []
    ranges: list[str] = []
    for prev, curr in zip(sorted_ids, sorted_ids[1:]):
        if curr - prev > 1:
            start = prev + 1
            end = curr - 1
            if start == end:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{end}")
    return ranges


def generate_qc_report(
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    *,
    stopping_reason: str = "not_recorded",
    scrape_date: str | None = None,
) -> str:
    """Build a Markdown quality-control report."""
    if scrape_date is None:
        scrape_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pages = sorted(
        {
            int(p)
            for p in raw_df["source_page"].dropna().tolist()
            if str(p).strip().isdigit() or isinstance(p, (int, float))
        }
    )
    total_rows = len(raw_df)
    id_series = cleaned_df["record_id"].dropna()
    id_series = id_series.astype(int)
    unique_ids = sorted(id_series.unique().tolist())
    id_counts = id_series.value_counts()
    duplicate_db_ids = sorted(id_counts[id_counts > 1].index.astype(int).tolist())

    missing_ranges = _missing_id_ranges(unique_ids)

    lines: list[str] = []
    lines.append("# AptaBase quality-control report")
    lines.append("")
    lines.append(f"- Scrape date (UTC date): {scrape_date}")
    lines.append(f"- HTML pages parsed: {len(pages)}")
    if pages:
        lines.append(f"- First page number: {pages[0]}")
        lines.append(f"- Last page number: {pages[-1]}")
    else:
        lines.append("- First page number: n/a")
        lines.append("- Last page number: n/a")
    lines.append(f"- Stopping reason: {stopping_reason}")
    lines.append(f"- Total rows extracted: {total_rows}")
    lines.append(f"- Unique database record IDs: {len(unique_ids)}")
    lines.append(f"- Duplicate database IDs: {len(duplicate_db_ids)}")
    if unique_ids:
        lines.append(f"- Minimum record ID: {min(unique_ids)}")
        lines.append(f"- Maximum record ID: {max(unique_ids)}")
    lines.append("")
    lines.append("## Missing record-ID ranges")
    lines.append("")
    lines.append(
        "Note: AptaBase IDs may be intentionally non-contiguous "
        "(for example deleted or unpublished entries). Gaps are informational only."
    )
    lines.append("")
    if missing_ranges:
        preview = ", ".join(missing_ranges[:50])
        suffix = " ..." if len(missing_ranges) > 50 else ""
        lines.append(f"- Gaps between observed IDs: {preview}{suffix}")
        lines.append(f"- Gap count: {len(missing_ranges)}")
    else:
        lines.append("- No gaps between observed consecutive unique IDs.")
    lines.append("")

    def _count_section(title: str, series: pd.Series) -> None:
        lines.append(f"## {title}")
        lines.append("")
        counts = series.fillna("(blank)").astype(str).value_counts()
        for key, count in counts.items():
            lines.append(f"- {key}: {count}")
        lines.append("")

    _count_section("Counts by target-general category", cleaned_df["target_general"])
    _count_section("Counts by sequence alphabet", cleaned_df["sequence_alphabet"])
    _count_section("Counts by molecule type inferred", cleaned_df["molecule_type_inferred"])

    missing_seq = int((cleaned_df["sequence_alphabet"] == "missing").sum())
    invalid_seq = int((cleaned_df["sequence_alphabet"] == "invalid").sum())
    missing_aff = int(
        cleaned_df["affinity_measurement_type"].isin(["missing", "unavailable"]).sum()
    )
    length_mismatch = int(
        cleaned_df["parse_warnings"].fillna("").str.contains("length_mismatch").sum()
    )
    gc_mismatch = int(
        cleaned_df["parse_warnings"].fillna("").str.contains("gc_content_mismatch").sum()
    )
    dup_groups = sorted({g for g in cleaned_df["duplicate_group"] if g})
    invalid_records = cleaned_df[cleaned_df["record_validity"] == "invalid"]
    mojibake = int(
        cleaned_df["parse_warnings"].fillna("").str.contains("mojibake_repaired").sum()
    )
    any_warning = int((cleaned_df["parse_warnings"].fillna("") != "").sum())

    lines.append("## Summary counts")
    lines.append("")
    lines.append(f"- Missing sequence count: {missing_seq}")
    lines.append(f"- Invalid sequence count: {invalid_seq}")
    lines.append(f"- Missing/unavailable affinity count: {missing_aff}")
    lines.append(f"- Length mismatch count: {length_mismatch}")
    lines.append(f"- GC-content mismatch count: {gc_mismatch}")
    lines.append(f"- Probable duplicate groups: {len(dup_groups)}")
    lines.append(f"- Invalid record count: {len(invalid_records)}")
    lines.append(f"- Records containing mojibake repairs: {mojibake}")
    lines.append(f"- Records with any parse warning: {any_warning}")
    lines.append("")

    _count_section("Affinity-unit counts", cleaned_df["affinity_unit"].replace("", "(none/blank)"))

    lines.append("## Duplicate diagnostics")
    lines.append("")
    name_counts = cleaned_df["aptamer_name"].fillna("").value_counts()
    dup_names = name_counts[name_counts > 1]
    lines.append(f"- Duplicate aptamer names: {len(dup_names)}")
    seq_counts = cleaned_df.loc[
        cleaned_df["sequence_clean"].fillna("") != "", "sequence_clean"
    ].value_counts()
    dup_seqs = seq_counts[seq_counts > 1]
    lines.append(f"- Duplicate clean sequences: {len(dup_seqs)}")
    combo = (
        cleaned_df["aptamer_name"].fillna("")
        + " || "
        + cleaned_df["target_specific"].fillna("")
    )
    combo_counts = combo.value_counts()
    lines.append(f"- Duplicate name-target combinations: {int((combo_counts > 1).sum())}")

    conflicting = 0
    missing_one = 0
    for group_id, group in cleaned_df[cleaned_df["duplicate_group"] != ""].groupby(
        "duplicate_group"
    ):
        seqs = [s for s in group["sequence_clean"].tolist() if s]
        blanks = int((group["sequence_clean"].fillna("") == "").sum())
        if len(set(seqs)) > 1:
            conflicting += 1
        if blanks and seqs:
            missing_one += 1
    lines.append(f"- Duplicate groups with conflicting sequences: {conflicting}")
    lines.append(f"- Duplicate groups where one sequence is missing: {missing_one}")
    lines.append("")

    lines.append("## Invalid records")
    lines.append("")
    if invalid_records.empty:
        lines.append("- None")
    else:
        ids = [
            str(int(i)) if pd.notna(i) else "(nonnumeric)"
            for i in invalid_records["record_id"].tolist()
        ]
        lines.append(f"- Database IDs: {', '.join(ids)}")
    lines.append("")

    lines.append("## Major problem records")
    lines.append("")
    major_mask = cleaned_df["parse_warnings"].fillna("").str.contains(
        "sequence_contains_non_nucleotide|reference_implausible|target_general_nonsensical|"
        "multiple_short_random|length_mismatch_gt_1|gc_content_mismatch",
        regex=True,
    )
    major = cleaned_df[major_mask]
    if major.empty:
        lines.append("- None flagged beyond routine warnings.")
    else:
        for _, row in major.iterrows():
            rid = row["record_id"]
            rid_text = str(int(rid)) if pd.notna(rid) else "(nonnumeric)"
            lines.append(
                f"- ID {rid_text} (validity={row['record_validity']}): {row['parse_warnings']}"
            )
    lines.append("")
    lines.append(
        "Always check database records against their cited publications before "
        "including them in a training corpus."
    )
    lines.append("")
    return "\n".join(lines)


def summarise_duplicate_name_conflicts(cleaned_df: pd.DataFrame) -> dict[str, Any]:
    """Helper used by tests and logging for duplicate-name detection."""
    name_counts = cleaned_df["aptamer_name"].fillna("").value_counts()
    duplicates = name_counts[name_counts > 1]
    return {
        "duplicate_name_count": int(len(duplicates)),
        "duplicate_names": duplicates.index.tolist(),
    }

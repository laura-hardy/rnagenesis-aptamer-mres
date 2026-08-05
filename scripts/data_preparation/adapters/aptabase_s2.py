"""AptaBase S2 adapter: molecule evidence, diagnostics and row normalisation.

Consumes S1 canonical rows plus the AptaBase source-metadata sidecar. Does not
import the legacy AptaBase cleaner. Does not accept, reject or park records.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, Sequence

from common.corpus_schema import (
    format_qc_flags,
    validate_s2_record,
)
from common.sequence_normalisation import (
    ALPHABET_DNA_T,
    ALPHABET_MISSING,
    ALPHABET_RNA,
    SequenceNormalisationRules,
    classify_alphabet,
    clean_display_sequence,
    load_normalisation_rules,
    normalise_sequence,
)

QC_DELIMITER: Final[str] = "|"

S2_QC_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "aptamer_name",
    "target_name_raw",
    "alphabet_as_reported",
    "molecule_type",
    "molecule_evidence_source",
    "molecule_evidence_category",
    "t_to_u_applied",
    "sequence_length_full",
    "sequence_length_core",
    "reported_length_raw",
    "reported_length_parsed",
    "reported_length_difference",
    "gc_reported_raw",
    "gc_reported_parsed",
    "gc_calculated_s2",
    "gc_difference_percentage_points",
    "detected_motifs",
    "construct_scope",
    "trim_status",
    "legacy_sequence_alphabet",
    "legacy_molecule_type_inferred",
    "legacy_sequence_length_calculated",
    "legacy_gc_content_calculated",
    "legacy_molecule_comparison_status",
    "legacy_molecule_comparison_reason",
    "legacy_disagreement_flags",
    "qc_flags",
)

CONSTANT_PROPOSAL_COLUMNS: Final[tuple[str, ...]] = (
    "experiment_group_id",
    "side",
    "proposed_sequence",
    "length",
    "support",
    "records_considered",
    "records_matching_exactly",
    "confidence",
    "status",
    "reason",
)

REVIEW_RELEVANT_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "missing_sequence",
        "invalid_character",
        "ambiguous_base",
        "mixed_t_u",
        "molecule_type_unknown",
        "conflicting_molecule_evidence",
        "t_in_reported_rna",
        "u_in_reported_dna",
        "known_promoter_detected",
        "trim_requires_review",
        "core_below_min_length",
        "core_above_max_length",
        "reported_length_unparseable",
        "reported_length_mismatch",
        "reported_gc_unparseable",
        "reported_gc_mismatch",
        "legacy_molecule_type_disagreement",
        "legacy_molecule_type_unrecognised",
    }
)

_TEXTUAL_NULLS: Final[frozenset[str]] = frozenset(
    {"", "NA", "N/A", "NULL", "NONE", "-"}
)

# AptaBase-observed corrupted terminal-label forms only. Digits 5/3 plus a
# replacement character or question mark standing in for a prime, optionally
# followed by an apostrophe/prime remnant and an optional display hyphen.
# Anchored strictly at the start (5′) or end (3′); never applied internally.
_APTABASE_CORRUPTED_5P_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*5\s*[?\ufffd]\s*['′’`´ʹ΄]?\s*[-–—:]?\s*",
    re.IGNORECASE,
)
_APTABASE_CORRUPTED_3P_RE: Final[re.Pattern[str]] = re.compile(
    r"\s*[-–—:]?\s*3\s*[?\ufffd]\s*['′’`´ʹ΄]?\s*$",
    re.IGNORECASE,
)

_LEGACY_MOLECULE_CATEGORY: Final[dict[str, str]] = {
    "RNA_like": "rna",
    "RNA_like_sequence": "rna",
    "DNA_like": "dna",
    "DNA_like_sequence": "dna",
    "missing": "missing",
    "invalid": "invalid",
    "mixed_or_uncertain": "mixed",
    "possible_DNA_template_for_RNA": "rna_template_candidate",
}

_NEW_MOLECULE_CATEGORY: Final[dict[str, str]] = {
    "RNA": "rna",
    "ssDNA": "dna",
    "DNA": "dna",
    "unknown": "unknown",
}


class AptaBaseS2Error(ValueError):
    """Hard failure during AptaBase S2 normalisation."""


@dataclass(frozen=True)
class AptabaseNormalisationPolicy:
    """Tracked AptaBase S2 source-normalisation policy."""

    source_key: str
    contract_version: str
    molecule_evidence_precedence: tuple[str, ...]
    rna_terms: tuple[str, ...]
    dna_terms: tuple[str, ...]
    text_fields_for_molecule_evidence: tuple[str, ...]
    forbidden_molecule_evidence_fields: tuple[str, ...]
    t_only_without_explicit_molecule_evidence: str
    u_only_without_explicit_molecule_evidence: str
    conflicting_text_evidence: str
    legacy_sequence_clean_is_canonical: bool
    legacy_molecule_inference_is_canonical: bool
    legacy_fields_are_diagnostics_only: bool
    reported_length_integer_tolerance: float
    gc_difference_review_threshold_percentage_points: float


@dataclass(frozen=True)
class MoleculeEvidenceResult:
    """Structured molecule-type evidence resolution for one AptaBase record."""

    molecule_type: str
    evidence_source: str
    evidence_category: str
    rna_terms_found: tuple[str, ...]
    dna_terms_found: tuple[str, ...]
    conflict: bool
    qc_flags: tuple[str, ...]


@dataclass
class LengthDiagnostic:
    """Reported-length parse and comparison diagnostic."""

    reported_length_raw: str
    reported_length_parsed: str
    reported_length_difference: str
    qc_flags: tuple[str, ...] = ()


@dataclass
class GcDiagnostic:
    """GC parse, calculation and comparison diagnostic."""

    gc_reported_raw: str
    gc_reported_parsed: str
    gc_calculated_s2: str
    gc_difference_percentage_points: str
    qc_flags: tuple[str, ...] = ()


@dataclass
class LegacyDiagnostic:
    """Comparison against legacy AptaBase derived fields."""

    legacy_disagreement_flags: tuple[str, ...]
    qc_flags: tuple[str, ...] = ()
    molecule_comparison_status: str = ""
    molecule_comparison_reason: str = ""


@dataclass(frozen=True)
class AptabaseTerminalLabelCleanResult:
    """Result of AptaBase-specific corrupted terminal-label preprocessing."""

    value_for_shared_normaliser: str | None
    removed_five_prime_artifact: bool
    removed_three_prime_artifact: bool
    transformations: tuple[str, ...]
    qc_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class LegacyMoleculeComparison:
    """Semantic comparison of legacy versus new molecule-type labels."""

    status: str
    legacy_semantic_category: str
    new_semantic_category: str
    disagreement: bool
    reason: str


@dataclass
class AptaBaseS2RowResult:
    """Canonical S2 row plus QC sidecar payload for one record."""

    canonical: dict[str, str]
    qc: dict[str, str]
    transformations: tuple[str, ...] = ()


@dataclass
class AptaBaseS2Stats:
    """Aggregate S2 counts (no sequences or row identifiers)."""

    s1_rows: int = 0
    source_metadata_rows: int = 0
    s2_rows: int = 0
    unique_record_ids: int = 0
    missing_sequence_rows: int = 0
    nonempty_sequence_rows: int = 0
    order_preserved: bool = False
    provenance_preserved: bool = False
    sequence_raw_unchanged: bool = False
    transformation_counts: dict[str, int] = field(default_factory=dict)
    alphabet_counts: dict[str, int] = field(default_factory=dict)
    molecule_type_counts: dict[str, int] = field(default_factory=dict)
    molecule_evidence_source_counts: dict[str, int] = field(default_factory=dict)
    t_to_u_count: int = 0
    invalid_character_count: int = 0
    ambiguous_base_count: int = 0
    mixed_t_u_count: int = 0
    known_motif_detection_count: int = 0
    trim_review_count: int = 0
    core_below_min_count: int = 0
    core_above_max_count: int = 0
    reported_length_unparseable_count: int = 0
    reported_length_mismatch_count: int = 0
    reported_gc_unparseable_count: int = 0
    reported_gc_mismatch_count: int = 0
    rows_with_any_qc_flag: int = 0
    rows_with_multiple_qc_flags: int = 0
    legacy_sequence_clean_disagreement_count: int = 0
    legacy_length_disagreement_count: int = 0
    legacy_alphabet_disagreement_count: int = 0
    legacy_molecule_type_disagreement_count: int = 0
    legacy_molecule_type_agreement_count: int = 0
    legacy_molecule_type_compatible_difference_count: int = 0
    legacy_molecule_type_unresolved_comparison_count: int = 0
    legacy_molecule_type_unrecognised_count: int = 0
    legacy_molecule_type_empty_legacy_count: int = 0
    legacy_gc_disagreement_count: int = 0
    review_candidate_rows: int = 0
    records_with_experiment_group_id: int = 0
    eligible_groups: int = 0
    constant_region_proposals: int = 0
    constant_region_reason: str = "no_experiment_group_id"


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AptaBaseS2Error(f"{name} must be a JSON object")
    return value


def _require_str_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AptaBaseS2Error(f"{name} must be a list of strings")
    return tuple(value)


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise AptaBaseS2Error(f"{name} must be a boolean")
    return value


def _require_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AptaBaseS2Error(f"{name} must be a number")
    return float(value)


def load_aptabase_policy(path: str | Path) -> AptabaseNormalisationPolicy:
    """Load and validate the AptaBase source-normalisation policy JSON."""
    policy_path = Path(path)
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AptaBaseS2Error(f"cannot read AptaBase policy: {exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise AptaBaseS2Error(f"AptaBase policy JSON is invalid: {exc.msg}") from exc

    data = _require_mapping(payload, "policy")
    source_key = data.get("source_key")
    if source_key != "aptabase":
        raise AptaBaseS2Error("policy source_key must be 'aptabase'")
    contract_version = data.get("contract_version")
    if not isinstance(contract_version, str) or not contract_version.strip():
        raise AptaBaseS2Error("contract_version must be a non-empty string")

    return AptabaseNormalisationPolicy(
        source_key=source_key,
        contract_version=contract_version.strip(),
        molecule_evidence_precedence=_require_str_list(
            data.get("molecule_evidence_precedence"),
            "molecule_evidence_precedence",
        ),
        rna_terms=_require_str_list(data.get("rna_terms"), "rna_terms"),
        dna_terms=_require_str_list(data.get("dna_terms"), "dna_terms"),
        text_fields_for_molecule_evidence=_require_str_list(
            data.get("text_fields_for_molecule_evidence"),
            "text_fields_for_molecule_evidence",
        ),
        forbidden_molecule_evidence_fields=_require_str_list(
            data.get("forbidden_molecule_evidence_fields"),
            "forbidden_molecule_evidence_fields",
        ),
        t_only_without_explicit_molecule_evidence=str(
            data.get("t_only_without_explicit_molecule_evidence", "unknown")
        ),
        u_only_without_explicit_molecule_evidence=str(
            data.get("u_only_without_explicit_molecule_evidence", "RNA")
        ),
        conflicting_text_evidence=str(data.get("conflicting_text_evidence", "unknown")),
        legacy_sequence_clean_is_canonical=_require_bool(
            data.get("legacy_sequence_clean_is_canonical"),
            "legacy_sequence_clean_is_canonical",
        ),
        legacy_molecule_inference_is_canonical=_require_bool(
            data.get("legacy_molecule_inference_is_canonical"),
            "legacy_molecule_inference_is_canonical",
        ),
        legacy_fields_are_diagnostics_only=_require_bool(
            data.get("legacy_fields_are_diagnostics_only"),
            "legacy_fields_are_diagnostics_only",
        ),
        reported_length_integer_tolerance=_require_float(
            data.get("reported_length_integer_tolerance"),
            "reported_length_integer_tolerance",
        ),
        gc_difference_review_threshold_percentage_points=_require_float(
            data.get("gc_difference_review_threshold_percentage_points"),
            "gc_difference_review_threshold_percentage_points",
        ),
    )


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term.lower()).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)


def find_molecule_terms(text: str, terms: Sequence[str]) -> tuple[str, ...]:
    """Return configured terms found with case-insensitive phrase boundaries."""
    if not text:
        return ()
    found: list[str] = []
    for term in terms:
        if _term_pattern(term).search(text):
            found.append(term)
    return tuple(found)


def _classify_text_evidence(
    text: str,
    policy: AptabaseNormalisationPolicy,
) -> tuple[str | None, tuple[str, ...], tuple[str, ...], bool]:
    rna_found = find_molecule_terms(text, policy.rna_terms)
    dna_found = find_molecule_terms(text, policy.dna_terms)
    if rna_found and dna_found:
        return None, rna_found, dna_found, True
    if rna_found:
        return "RNA", rna_found, dna_found, False
    if dna_found:
        return "ssDNA", rna_found, dna_found, False
    return None, rna_found, dna_found, False


def resolve_aptabase_molecule_type(
    source_metadata: Mapping[str, str],
    alphabet_as_reported: str,
    policy: AptabaseNormalisationPolicy,
    *,
    has_t: bool = False,
    has_u: bool = False,
) -> MoleculeEvidenceResult:
    """Resolve molecule type from AptaBase text evidence then alphabet fallback.

    Target fields and legacy inferred molecule/alphabet fields are never used as
    authoritative evidence.
    """
    for forbidden in policy.forbidden_molecule_evidence_fields:
        # Explicit guard: callers must not treat these as evidence inputs.
        _ = source_metadata.get(forbidden, "")

    rna_all: list[str] = []
    dna_all: list[str] = []

    name_text = source_metadata.get("aptabase_aptamer_name", "")
    name_type, name_rna, name_dna, name_conflict = _classify_text_evidence(
        name_text, policy
    )
    rna_all.extend(name_rna)
    dna_all.extend(name_dna)

    if name_conflict:
        return MoleculeEvidenceResult(
            molecule_type=policy.conflicting_text_evidence,
            evidence_source="aptamer_name",
            evidence_category="conflict",
            rna_terms_found=tuple(sorted(set(rna_all))),
            dna_terms_found=tuple(sorted(set(dna_all))),
            conflict=True,
            qc_flags=("conflicting_molecule_evidence", "molecule_type_unknown"),
        )

    if name_type is not None:
        return MoleculeEvidenceResult(
            molecule_type=name_type,
            evidence_source="aptamer_name",
            evidence_category="explicit_text",
            rna_terms_found=tuple(sorted(set(rna_all))),
            dna_terms_found=tuple(sorted(set(dna_all))),
            conflict=False,
            qc_flags=(),
        )

    ref_text = source_metadata.get("aptabase_reference", "")
    ref_type, ref_rna, ref_dna, ref_conflict = _classify_text_evidence(
        ref_text, policy
    )
    rna_all.extend(ref_rna)
    dna_all.extend(ref_dna)

    if ref_conflict:
        return MoleculeEvidenceResult(
            molecule_type=policy.conflicting_text_evidence,
            evidence_source="reference",
            evidence_category="conflict",
            rna_terms_found=tuple(sorted(set(rna_all))),
            dna_terms_found=tuple(sorted(set(dna_all))),
            conflict=True,
            qc_flags=("conflicting_molecule_evidence", "molecule_type_unknown"),
        )

    if ref_type is not None:
        return MoleculeEvidenceResult(
            molecule_type=ref_type,
            evidence_source="reference",
            evidence_category="explicit_text",
            rna_terms_found=tuple(sorted(set(rna_all))),
            dna_terms_found=tuple(sorted(set(dna_all))),
            conflict=False,
            qc_flags=(),
        )

    # Alphabet fallback only when no explicit textual evidence exists.
    if alphabet_as_reported == ALPHABET_RNA and has_u and not has_t:
        molecule = policy.u_only_without_explicit_molecule_evidence
        flags: tuple[str, ...] = ()
        if molecule == "unknown":
            flags = ("molecule_type_unknown",)
        return MoleculeEvidenceResult(
            molecule_type=molecule,
            evidence_source="sequence_alphabet",
            evidence_category="alphabet",
            rna_terms_found=tuple(sorted(set(rna_all))),
            dna_terms_found=tuple(sorted(set(dna_all))),
            conflict=False,
            qc_flags=flags,
        )

    if alphabet_as_reported == ALPHABET_DNA_T and has_t and not has_u:
        molecule = policy.t_only_without_explicit_molecule_evidence
        flags = ("molecule_type_unknown",) if molecule == "unknown" else ()
        return MoleculeEvidenceResult(
            molecule_type=molecule,
            evidence_source="sequence_alphabet",
            evidence_category="alphabet",
            rna_terms_found=tuple(sorted(set(rna_all))),
            dna_terms_found=tuple(sorted(set(dna_all))),
            conflict=False,
            qc_flags=flags,
        )

    return MoleculeEvidenceResult(
        molecule_type="unknown",
        evidence_source="",
        evidence_category="none",
        rna_terms_found=tuple(sorted(set(rna_all))),
        dna_terms_found=tuple(sorted(set(dna_all))),
        conflict=False,
        qc_flags=("molecule_type_unknown",),
    )


def parse_reported_length(
    raw: str,
    *,
    tolerance: float,
) -> tuple[int | None, tuple[str, ...]]:
    """Parse an integer or integer-valued decimal reported length."""
    text = (raw or "").strip()
    if text == "" or text.upper() in _TEXTUAL_NULLS:
        return None, ()
    try:
        value = float(text)
    except ValueError:
        return None, ("reported_length_unparseable",)
    if not math.isfinite(value):
        return None, ("reported_length_unparseable",)
    nearest = round(value)
    if abs(value - nearest) > tolerance:
        return None, ("reported_length_unparseable",)
    if nearest < 0:
        return None, ("reported_length_unparseable",)
    return int(nearest), ()


def compare_reported_length(
    raw: str,
    sequence_length_full: int | None,
    *,
    tolerance: float,
) -> LengthDiagnostic:
    """Compare parsed reported length with ``sequence_length_full``."""
    parsed, flags = parse_reported_length(raw, tolerance=tolerance)
    flag_list = list(flags)
    parsed_str = "" if parsed is None else str(parsed)
    diff_str = ""
    if parsed is not None and sequence_length_full is not None:
        diff = sequence_length_full - parsed
        diff_str = str(diff)
        if diff != 0:
            flag_list.append("reported_length_mismatch")
    return LengthDiagnostic(
        reported_length_raw=raw,
        reported_length_parsed=parsed_str,
        reported_length_difference=diff_str,
        qc_flags=tuple(flag_list),
    )


def parse_reported_gc(raw: str) -> tuple[float | None, tuple[str, ...]]:
    """Conservatively parse a source-reported GC percentage."""
    text = (raw or "").strip()
    if text == "" or text.upper() in _TEXTUAL_NULLS:
        return None, ()
    cleaned = text.rstrip("%").strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None, ("reported_gc_unparseable",)
    if not math.isfinite(value):
        return None, ("reported_gc_unparseable",)
    if value < 0.0 or value > 100.0:
        return None, ("reported_gc_unparseable",)
    return value, ()


def calculate_gc_percentage(
    sequence_full: str | None,
    alphabet_as_reported: str,
) -> float | None:
    """Calculate GC% only for canonical nonempty DNA/RNA alphabets."""
    if sequence_full is None or sequence_full == "":
        return None
    if alphabet_as_reported not in {ALPHABET_RNA, ALPHABET_DNA_T}:
        return None
    upper = sequence_full.upper()
    if alphabet_as_reported == ALPHABET_RNA:
        allowed = set("ACGU")
    else:
        allowed = set("ACGT")
    if any(ch not in allowed for ch in upper):
        return None
    if "T" in upper and "U" in upper:
        return None
    length = len(upper)
    if length == 0:
        return None
    gc = upper.count("G") + upper.count("C")
    return 100.0 * gc / length


def compare_gc_content(
    reported_raw: str,
    sequence_full: str | None,
    alphabet_as_reported: str,
    *,
    threshold_pp: float,
) -> GcDiagnostic:
    """Compare S2-calculated GC with the source-reported value."""
    parsed, parse_flags = parse_reported_gc(reported_raw)
    calculated = calculate_gc_percentage(sequence_full, alphabet_as_reported)
    flags = list(parse_flags)
    parsed_str = "" if parsed is None else _format_float(parsed)
    calc_str = "" if calculated is None else _format_float(calculated)
    diff_str = ""
    if parsed is not None and calculated is not None:
        diff = calculated - parsed
        diff_str = _format_float(diff)
        if abs(diff) >= threshold_pp:
            flags.append("reported_gc_mismatch")
    return GcDiagnostic(
        gc_reported_raw=reported_raw,
        gc_reported_parsed=parsed_str,
        gc_calculated_s2=calc_str,
        gc_difference_percentage_points=diff_str,
        qc_flags=tuple(flags),
    )


def _format_float(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _legacy_float_or_none(raw: str) -> float | None:
    text = (raw or "").strip()
    if text == "" or text.upper() in _TEXTUAL_NULLS:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def clean_aptabase_terminal_label_artifacts(
    sequence_raw: str | None,
) -> AptabaseTerminalLabelCleanResult:
    """Remove AptaBase-specific corrupted 5′/3′ terminal display labels only.

    Recognises only tightly anchored patterns observed in AptaBase encoding
    damage: digit 5 or 3 with a replacement character or question mark in place
    of a prime, optionally followed by an apostrophe/prime remnant and an
    optional display hyphen. Does not remove internal digits, question marks,
    replacement characters, nucleotides, or chemical-modification notation.
    """
    if sequence_raw is None:
        return AptabaseTerminalLabelCleanResult(
            value_for_shared_normaliser=None,
            removed_five_prime_artifact=False,
            removed_three_prime_artifact=False,
            transformations=(),
        )

    text = str(sequence_raw)
    transformations: list[str] = []
    removed_five = False
    removed_three = False

    after_five = _APTABASE_CORRUPTED_5P_RE.sub("", text, count=1)
    if after_five != text:
        removed_five = True
        transformations.append("remove_aptabase_corrupted_5p_label")
        text = after_five

    after_three = _APTABASE_CORRUPTED_3P_RE.sub("", text, count=1)
    if after_three != text:
        removed_three = True
        transformations.append("remove_aptabase_corrupted_3p_label")
        text = after_three

    return AptabaseTerminalLabelCleanResult(
        value_for_shared_normaliser=text,
        removed_five_prime_artifact=removed_five,
        removed_three_prime_artifact=removed_three,
        transformations=tuple(transformations),
    )


def compare_legacy_molecule_type(
    *,
    new_molecule_type: str,
    legacy_molecule_type: str,
    new_alphabet: str,
    molecule_evidence_source: str,
) -> LegacyMoleculeComparison:
    """Compare legacy and new molecule labels using semantic categories.

    Literal vocabulary differences (for example ``RNA_like_sequence`` versus
    ``RNA``) are not disagreements. Only substantive semantic conflicts raise
    ``legacy_molecule_type_disagreement``.
    """
    legacy_raw = (legacy_molecule_type or "").strip()
    new_raw = (new_molecule_type or "").strip()

    if legacy_raw == "" or legacy_raw.upper() in _TEXTUAL_NULLS:
        return LegacyMoleculeComparison(
            status="empty_legacy",
            legacy_semantic_category="",
            new_semantic_category=_NEW_MOLECULE_CATEGORY.get(new_raw, "unrecognised"),
            disagreement=False,
            reason="legacy_molecule_type_empty",
        )

    legacy_category = _LEGACY_MOLECULE_CATEGORY.get(legacy_raw)
    new_category = _NEW_MOLECULE_CATEGORY.get(new_raw)

    if legacy_category is None:
        return LegacyMoleculeComparison(
            status="unrecognised",
            legacy_semantic_category="unrecognised",
            new_semantic_category=new_category or "unrecognised",
            disagreement=False,
            reason="legacy_molecule_type_unrecognised",
        )

    if new_category is None:
        return LegacyMoleculeComparison(
            status="unrecognised",
            legacy_semantic_category=legacy_category,
            new_semantic_category="unrecognised",
            disagreement=False,
            reason="new_molecule_type_unrecognised",
        )

    # Direct semantic agreement, including DNA↔ssDNA/DNA and RNA↔RNA.
    if legacy_category == new_category:
        return LegacyMoleculeComparison(
            status="agreement",
            legacy_semantic_category=legacy_category,
            new_semantic_category=new_category,
            disagreement=False,
            reason="semantic_agreement",
        )

    # DNA-template candidate versus RNA is treated as agreement when RNA is
    # independently established; versus unknown remains unresolved.
    if legacy_category == "rna_template_candidate":
        if new_category == "rna":
            return LegacyMoleculeComparison(
                status="agreement",
                legacy_semantic_category=legacy_category,
                new_semantic_category=new_category,
                disagreement=False,
                reason="rna_template_candidate_agrees_with_rna",
            )
        if new_category == "unknown":
            return LegacyMoleculeComparison(
                status="unresolved",
                legacy_semantic_category=legacy_category,
                new_semantic_category=new_category,
                disagreement=False,
                reason="rna_template_candidate_versus_unknown",
            )
        return LegacyMoleculeComparison(
            status="disagreement",
            legacy_semantic_category=legacy_category,
            new_semantic_category=new_category,
            disagreement=True,
            reason="rna_template_candidate_versus_non_rna",
        )

    # Unresolved legacy buckets versus new unknown are compatible, not
    # biological disagreements.
    if (
        legacy_category in {"missing", "invalid", "mixed"}
        and new_category == "unknown"
    ):
        return LegacyMoleculeComparison(
            status="compatible_difference",
            legacy_semantic_category=legacy_category,
            new_semantic_category=new_category,
            disagreement=False,
            reason=f"legacy_{legacy_category}_compatible_with_unknown",
        )

    # Conservative T-only policy: legacy DNA-like versus new unknown without
    # explicit text evidence is unresolved rather than a disagreement.
    if legacy_category == "dna" and new_category == "unknown":
        if (
            new_alphabet == ALPHABET_DNA_T
            and molecule_evidence_source in {"", "sequence_alphabet", "none"}
        ):
            return LegacyMoleculeComparison(
                status="unresolved",
                legacy_semantic_category=legacy_category,
                new_semantic_category=new_category,
                disagreement=False,
                reason="dna_like_versus_conservative_t_only_unknown",
            )
        return LegacyMoleculeComparison(
            status="unresolved",
            legacy_semantic_category=legacy_category,
            new_semantic_category=new_category,
            disagreement=False,
            reason="dna_like_versus_unknown",
        )

    # Legacy RNA-like versus new unknown is a substantive disagreement.
    if legacy_category == "rna" and new_category == "unknown":
        return LegacyMoleculeComparison(
            status="disagreement",
            legacy_semantic_category=legacy_category,
            new_semantic_category=new_category,
            disagreement=True,
            reason="rna_like_versus_unknown",
        )

    # Cross-family swaps (RNA↔DNA) are substantive disagreements.
    if {legacy_category, new_category} == {"rna", "dna"}:
        return LegacyMoleculeComparison(
            status="disagreement",
            legacy_semantic_category=legacy_category,
            new_semantic_category=new_category,
            disagreement=True,
            reason="rna_dna_semantic_conflict",
        )

    # Any remaining category mismatch is a substantive disagreement.
    return LegacyMoleculeComparison(
        status="disagreement",
        legacy_semantic_category=legacy_category,
        new_semantic_category=new_category,
        disagreement=True,
        reason="semantic_category_mismatch",
    )


def compare_legacy_diagnostics(
    *,
    sequence_full: str | None,
    sequence_length_full: int | None,
    alphabet_as_reported: str,
    molecule_type: str,
    molecule_evidence_source: str,
    gc_calculated_s2: str,
    source_metadata: Mapping[str, str],
) -> LegacyDiagnostic:
    """Compare S2 outputs with legacy derived sidecar fields (diagnostics only)."""
    flags: list[str] = []
    qc_extra: list[str] = []

    legacy_clean = source_metadata.get("aptabase_sequence_clean", "")
    if sequence_full is None:
        if legacy_clean.strip() and legacy_clean.strip().upper() not in _TEXTUAL_NULLS:
            flags.append("legacy_sequence_clean_disagreement")
    else:
        if legacy_clean.strip().upper() not in _TEXTUAL_NULLS:
            if legacy_clean.strip().upper() != sequence_full:
                flags.append("legacy_sequence_clean_disagreement")
        elif sequence_full:
            # Legacy empty/null while S2 has a sequence.
            flags.append("legacy_sequence_clean_disagreement")

    legacy_len_raw = source_metadata.get("aptabase_sequence_length_calculated", "")
    legacy_len = _legacy_float_or_none(legacy_len_raw)
    if sequence_length_full is None:
        if legacy_len is not None:
            flags.append("legacy_length_disagreement")
    elif legacy_len is None:
        if legacy_len_raw.strip() and legacy_len_raw.strip().upper() not in _TEXTUAL_NULLS:
            flags.append("legacy_length_disagreement")
    else:
        if abs(legacy_len - sequence_length_full) > 1e-9:
            flags.append("legacy_length_disagreement")

    legacy_alphabet = source_metadata.get("aptabase_sequence_alphabet", "").strip()
    if legacy_alphabet and legacy_alphabet.upper() not in _TEXTUAL_NULLS:
        if legacy_alphabet != alphabet_as_reported:
            flags.append("legacy_alphabet_disagreement")

    legacy_molecule = source_metadata.get(
        "aptabase_molecule_type_inferred", ""
    ).strip()
    molecule_cmp = compare_legacy_molecule_type(
        new_molecule_type=molecule_type,
        legacy_molecule_type=legacy_molecule,
        new_alphabet=alphabet_as_reported,
        molecule_evidence_source=molecule_evidence_source,
    )
    if molecule_cmp.disagreement:
        flags.append("legacy_molecule_type_disagreement")
        qc_extra.append("legacy_molecule_type_disagreement")
    elif molecule_cmp.status == "compatible_difference":
        flags.append("legacy_molecule_type_compatible_difference")
    elif molecule_cmp.status == "unresolved":
        flags.append("legacy_molecule_type_unresolved_comparison")
    elif molecule_cmp.status == "unrecognised":
        flags.append("legacy_molecule_type_unrecognised")
        qc_extra.append("legacy_molecule_type_unrecognised")

    legacy_gc = _legacy_float_or_none(
        source_metadata.get("aptabase_gc_content_calculated", "")
    )
    s2_gc = _legacy_float_or_none(gc_calculated_s2)
    if legacy_gc is None and s2_gc is None:
        pass
    elif legacy_gc is None or s2_gc is None:
        if legacy_gc is not None or s2_gc is not None:
            flags.append("legacy_gc_disagreement")
    elif abs(legacy_gc - s2_gc) >= 1e-6:
        flags.append("legacy_gc_disagreement")

    ordered = tuple(sorted(set(flags)))
    # Canonical qc_flags carry only review-relevant molecule comparison outcomes
    # plus other legacy disagreements that remain diagnostic in qc_flags.
    qc_flags = tuple(
        sorted(
            set(qc_extra)
            | {
                flag
                for flag in ordered
                if flag
                not in {
                    "legacy_molecule_type_compatible_difference",
                    "legacy_molecule_type_unresolved_comparison",
                }
            }
        )
    )
    return LegacyDiagnostic(
        legacy_disagreement_flags=ordered,
        qc_flags=qc_flags,
        molecule_comparison_status=molecule_cmp.status,
        molecule_comparison_reason=molecule_cmp.reason,
    )


def _motif_names_by_side(
    motifs: Iterable[Any],
) -> tuple[str, str]:
    five: list[str] = []
    three: list[str] = []
    for motif in motifs:
        name = getattr(motif, "name", str(motif))
        position = getattr(motif, "position", "")
        if position == "five_prime":
            five.append(name)
        elif position == "three_prime":
            three.append(name)
    return (
        QC_DELIMITER.join(sorted(set(five))),
        QC_DELIMITER.join(sorted(set(three))),
    )


def normalise_aptabase_record(
    s1_record: Mapping[str, str],
    source_metadata: Mapping[str, str],
    *,
    policy: AptabaseNormalisationPolicy,
    rules: SequenceNormalisationRules | None = None,
) -> AptaBaseS2RowResult:
    """Normalise one AptaBase S1 record into S2 canonical + QC rows."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    if s1_record["record_id"] != source_metadata.get("record_id", ""):
        raise AptaBaseS2Error("canonical and sidecar record_id values must match")

    sequence_raw = s1_record["sequence_raw"]
    terminal = clean_aptabase_terminal_label_artifacts(sequence_raw)
    display_input = terminal.value_for_shared_normaliser
    display = clean_display_sequence(display_input, rules=active_rules)
    alphabet_pre = classify_alphabet(
        display.sequence_display_clean, rules=active_rules
    )

    molecule = resolve_aptabase_molecule_type(
        source_metadata,
        alphabet_pre.alphabet,
        policy,
        has_t=alphabet_pre.has_t,
        has_u=alphabet_pre.has_u,
    )

    qc_flags: list[str] = list(molecule.qc_flags)
    qc_flags.extend(terminal.qc_flags)
    source_transformations = list(terminal.transformations)

    if display.is_missing:
        canonical = dict(s1_record)
        for key in (
            "sequence_full",
            "sequence_core",
            "sequence_length_full",
            "sequence_length_core",
            "trim_confidence",
            "detected_constant_5p",
            "detected_constant_3p",
        ):
            canonical[key] = ""
        canonical["construct_scope"] = "missing"
        canonical["trim_status"] = "not_applicable"
        canonical["molecule_type"] = "unknown"
        canonical["alphabet_as_reported"] = ALPHABET_MISSING
        canonical["t_to_u_applied"] = "false"
        qc_flags = sorted(
            set(qc_flags) | {"missing_sequence", "molecule_type_unknown"}
        )
        length_diag = compare_reported_length(
            source_metadata.get("aptabase_reported_length", ""),
            None,
            tolerance=policy.reported_length_integer_tolerance,
        )
        gc_diag = compare_gc_content(
            source_metadata.get("aptabase_gc_content_reported", ""),
            None,
            ALPHABET_MISSING,
            threshold_pp=policy.gc_difference_review_threshold_percentage_points,
        )
        legacy = compare_legacy_diagnostics(
            sequence_full=None,
            sequence_length_full=None,
            alphabet_as_reported=ALPHABET_MISSING,
            molecule_type="unknown",
            molecule_evidence_source=molecule.evidence_source,
            gc_calculated_s2="",
            source_metadata=source_metadata,
        )
        qc_flags = sorted(
            set(qc_flags)
            | set(length_diag.qc_flags)
            | set(gc_diag.qc_flags)
            | set(legacy.qc_flags)
        )
        canonical["qc_flags"] = format_qc_flags(qc_flags)
        # Provenance: canonical sequence_raw remains the S1 value.
        canonical["sequence_raw"] = sequence_raw
        validated = validate_s2_record(canonical, s1_record=s1_record)
        qc = _build_qc_row(
            validated=validated,
            source_metadata=source_metadata,
            molecule=molecule,
            length_diag=length_diag,
            gc_diag=gc_diag,
            legacy=legacy,
            detected_motifs="",
        )
        return AptaBaseS2RowResult(
            canonical=validated,
            qc=qc,
            transformations=tuple(source_transformations + list(display.transformations)),
        )

    # Shared normaliser receives the AptaBase-preprocessed display value, not
    # a mutated canonical sequence_raw.
    norm = normalise_sequence(
        display_input,
        molecule_type=molecule.molecule_type,
        trim_plan=None,
        rules=active_rules,
    )

    # AptaBase has no approved trim plan in this milestone.
    sequence_full = norm.sequence_full or ""
    sequence_core = sequence_full
    five_motifs, three_motifs = _motif_names_by_side(norm.detected_motifs)
    qc_flags.extend(norm.qc_flags)

    if norm.detected_motifs:
        qc_flags.append("trim_requires_review")
        trim_status = "review_required"
    else:
        trim_status = "not_trimmed"

    # Ensure molecule_type_unknown is present when still unknown.
    resolved_molecule = norm.molecule_type
    if resolved_molecule == "unknown":
        qc_flags.append("molecule_type_unknown")

    length_diag = compare_reported_length(
        source_metadata.get("aptabase_reported_length", ""),
        len(sequence_full) if sequence_full else None,
        tolerance=policy.reported_length_integer_tolerance,
    )
    gc_diag = compare_gc_content(
        source_metadata.get("aptabase_gc_content_reported", ""),
        sequence_full if sequence_full else None,
        norm.alphabet_as_reported,
        threshold_pp=policy.gc_difference_review_threshold_percentage_points,
    )
    legacy = compare_legacy_diagnostics(
        sequence_full=sequence_full if sequence_full else None,
        sequence_length_full=len(sequence_full) if sequence_full else None,
        alphabet_as_reported=norm.alphabet_as_reported,
        molecule_type=resolved_molecule,
        molecule_evidence_source=molecule.evidence_source,
        gc_calculated_s2=gc_diag.gc_calculated_s2,
        source_metadata=source_metadata,
    )
    qc_flags.extend(length_diag.qc_flags)
    qc_flags.extend(gc_diag.qc_flags)
    qc_flags.extend(legacy.qc_flags)

    canonical = dict(s1_record)
    canonical["sequence_raw"] = sequence_raw
    canonical["sequence_full"] = sequence_full
    canonical["sequence_core"] = sequence_core
    canonical["sequence_length_full"] = str(len(sequence_full))
    canonical["sequence_length_core"] = str(len(sequence_core))
    canonical["construct_scope"] = "full_equals_core_untrimmed"
    canonical["trim_status"] = trim_status
    canonical["trim_confidence"] = ""
    canonical["detected_constant_5p"] = five_motifs
    canonical["detected_constant_3p"] = three_motifs
    canonical["molecule_type"] = resolved_molecule
    canonical["alphabet_as_reported"] = norm.alphabet_as_reported
    canonical["t_to_u_applied"] = "true" if norm.t_to_u_applied else "false"
    canonical["qc_flags"] = format_qc_flags(qc_flags)

    validated = validate_s2_record(canonical, s1_record=s1_record)
    detected_motif_names = QC_DELIMITER.join(
        sorted({motif.name for motif in norm.detected_motifs})
    )
    qc = _build_qc_row(
        validated=validated,
        source_metadata=source_metadata,
        molecule=molecule,
        length_diag=length_diag,
        gc_diag=gc_diag,
        legacy=legacy,
        detected_motifs=detected_motif_names,
    )
    return AptaBaseS2RowResult(
        canonical=validated,
        qc=qc,
        transformations=tuple(source_transformations + list(norm.transformations)),
    )


def _build_qc_row(
    *,
    validated: Mapping[str, str],
    source_metadata: Mapping[str, str],
    molecule: MoleculeEvidenceResult,
    length_diag: LengthDiagnostic,
    gc_diag: GcDiagnostic,
    legacy: LegacyDiagnostic,
    detected_motifs: str,
) -> dict[str, str]:
    return {
        "record_id": validated["record_id"],
        "native_id": validated["native_id"],
        "aptamer_name": source_metadata.get("aptabase_aptamer_name", ""),
        "target_name_raw": validated["target_name_raw"],
        "alphabet_as_reported": validated["alphabet_as_reported"],
        "molecule_type": validated["molecule_type"],
        "molecule_evidence_source": molecule.evidence_source,
        "molecule_evidence_category": molecule.evidence_category,
        "t_to_u_applied": validated["t_to_u_applied"],
        "sequence_length_full": validated["sequence_length_full"],
        "sequence_length_core": validated["sequence_length_core"],
        "reported_length_raw": length_diag.reported_length_raw,
        "reported_length_parsed": length_diag.reported_length_parsed,
        "reported_length_difference": length_diag.reported_length_difference,
        "gc_reported_raw": gc_diag.gc_reported_raw,
        "gc_reported_parsed": gc_diag.gc_reported_parsed,
        "gc_calculated_s2": gc_diag.gc_calculated_s2,
        "gc_difference_percentage_points": gc_diag.gc_difference_percentage_points,
        "detected_motifs": detected_motifs,
        "construct_scope": validated["construct_scope"],
        "trim_status": validated["trim_status"],
        "legacy_sequence_alphabet": source_metadata.get(
            "aptabase_sequence_alphabet", ""
        ),
        "legacy_molecule_type_inferred": source_metadata.get(
            "aptabase_molecule_type_inferred", ""
        ),
        "legacy_sequence_length_calculated": source_metadata.get(
            "aptabase_sequence_length_calculated", ""
        ),
        "legacy_gc_content_calculated": source_metadata.get(
            "aptabase_gc_content_calculated", ""
        ),
        "legacy_molecule_comparison_status": legacy.molecule_comparison_status,
        "legacy_molecule_comparison_reason": legacy.molecule_comparison_reason,
        "legacy_disagreement_flags": format_qc_flags(legacy.legacy_disagreement_flags),
        "qc_flags": validated["qc_flags"],
    }


def is_review_candidate(qc_flags: str) -> bool:
    """Return True when any manual-review-relevant flag is present."""
    if not qc_flags:
        return False
    flags = {part for part in qc_flags.split(QC_DELIMITER) if part}
    return bool(flags & REVIEW_RELEVANT_FLAGS)


def update_stats_from_row(
    stats: AptaBaseS2Stats,
    row: AptaBaseS2RowResult,
) -> None:
    """Accumulate aggregate counters from one normalised row."""
    canonical = row.canonical
    qc = row.qc
    flags = [part for part in canonical["qc_flags"].split(QC_DELIMITER) if part]

    if canonical["sequence_full"] == "":
        stats.missing_sequence_rows += 1
    else:
        stats.nonempty_sequence_rows += 1

    for transformation in row.transformations:
        stats.transformation_counts[transformation] = (
            stats.transformation_counts.get(transformation, 0) + 1
        )

    alphabet = canonical["alphabet_as_reported"] or "missing"
    stats.alphabet_counts[alphabet] = stats.alphabet_counts.get(alphabet, 0) + 1

    molecule = canonical["molecule_type"] or "unknown"
    stats.molecule_type_counts[molecule] = (
        stats.molecule_type_counts.get(molecule, 0) + 1
    )

    evidence_source = qc["molecule_evidence_source"] or "none"
    stats.molecule_evidence_source_counts[evidence_source] = (
        stats.molecule_evidence_source_counts.get(evidence_source, 0) + 1
    )

    if canonical["t_to_u_applied"] == "true":
        stats.t_to_u_count += 1
    if "invalid_character" in flags:
        stats.invalid_character_count += 1
    if "ambiguous_base" in flags:
        stats.ambiguous_base_count += 1
    if "mixed_t_u" in flags:
        stats.mixed_t_u_count += 1
    if qc["detected_motifs"]:
        stats.known_motif_detection_count += 1
    if "trim_requires_review" in flags or canonical["trim_status"] == "review_required":
        stats.trim_review_count += 1
    if "core_below_min_length" in flags:
        stats.core_below_min_count += 1
    if "core_above_max_length" in flags:
        stats.core_above_max_count += 1
    if "reported_length_unparseable" in flags:
        stats.reported_length_unparseable_count += 1
    if "reported_length_mismatch" in flags:
        stats.reported_length_mismatch_count += 1
    if "reported_gc_unparseable" in flags:
        stats.reported_gc_unparseable_count += 1
    if "reported_gc_mismatch" in flags:
        stats.reported_gc_mismatch_count += 1
    if flags:
        stats.rows_with_any_qc_flag += 1
    if len(flags) > 1:
        stats.rows_with_multiple_qc_flags += 1
    if "legacy_sequence_clean_disagreement" in flags:
        stats.legacy_sequence_clean_disagreement_count += 1
    if "legacy_length_disagreement" in flags:
        stats.legacy_length_disagreement_count += 1
    if "legacy_alphabet_disagreement" in flags:
        stats.legacy_alphabet_disagreement_count += 1
    if "legacy_molecule_type_disagreement" in flags:
        stats.legacy_molecule_type_disagreement_count += 1
    status = qc.get("legacy_molecule_comparison_status", "")
    if status == "agreement":
        stats.legacy_molecule_type_agreement_count += 1
    elif status == "compatible_difference":
        stats.legacy_molecule_type_compatible_difference_count += 1
    elif status == "unresolved":
        stats.legacy_molecule_type_unresolved_comparison_count += 1
    elif status == "unrecognised":
        stats.legacy_molecule_type_unrecognised_count += 1
    elif status == "empty_legacy":
        stats.legacy_molecule_type_empty_legacy_count += 1
    elif status == "disagreement":
        # Substantive disagreements are also counted from qc_flags above;
        # keep this branch so every defined status is handled explicitly.
        pass
    if "legacy_gc_disagreement" in flags:
        stats.legacy_gc_disagreement_count += 1
    if is_review_candidate(canonical["qc_flags"]):
        stats.review_candidate_rows += 1


def assert_no_legacy_cleaner_import() -> None:
    """Hard-fail if the legacy AptaBase cleaner module is imported."""
    import sys

    forbidden = {
        "aptabase_cleaning",
        "scripts.data_preparation.aptabase_cleaning",
    }
    for name in forbidden:
        if name in sys.modules:
            raise AptaBaseS2Error(
                "legacy AptaBase cleaner must not be imported by S2"
            )

"""Shared sequence normalisation for S2 onward (canonical corpus fields).

This module is the authoritative implementation of
``docs/data_curation/sequence_normalisation_contract.md``. Source adapters must
not implement independent normalisation policies. Input records are immutable;
all transformations are deterministic and auditable.

Constant-region detection does not authorise trimming. Trimming requires an
explicit approved trim plan with exact prefix/suffix matches.

Do not import ``scripts/data_preparation/aptabase_cleaning.py``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Iterable, Mapping

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_RULES_PATH: Final[Path] = (
    REPO_ROOT / "config" / "sequence_normalisation_rules.json"
)

TEXTUAL_NULLS: Final[frozenset[str]] = frozenset(
    {"", "NA", "N/A", "NULL", "NONE", "-"}
)

ALPHABET_MISSING: Final[str] = "missing"
ALPHABET_RNA: Final[str] = "RNA"
ALPHABET_DNA_T: Final[str] = "DNA_T"
ALPHABET_MIXED_T_U: Final[str] = "mixed_T_U"
ALPHABET_AMBIGUOUS: Final[str] = "ambiguous"
ALPHABET_INVALID: Final[str] = "invalid"

_LEADING_TERMINAL_RE = re.compile(
    r"^(?:5[\s]*[′'ʹ΄]|5\s*['′])\s*[-–—:]?\s*",
    re.IGNORECASE,
)
_TRAILING_TERMINAL_RE = re.compile(
    r"\s*[-–—:]?\s*(?:3[\s]*[′'ʹ΄]|3\s*['′])\s*$",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")


class SequenceNormalisationError(ValueError):
    """Invalid normalisation input or configuration (never embeds sequences)."""


class TrimMismatchError(SequenceNormalisationError):
    """Approved trim does not match the sequence exactly."""


class ConfigurationError(SequenceNormalisationError):
    """Normalisation rules configuration is invalid."""


@dataclass(frozen=True)
class KnownMotifRule:
    """A known non-core motif detection rule (flag-only by default)."""

    name: str
    sequence: str
    expected_position: str
    action: str
    notes: str = ""


@dataclass(frozen=True)
class ConstantRegionInferenceConfig:
    """Group-level constant-region inference thresholds."""

    minimum_group_size: int
    minimum_support: float
    minimum_region_length: int
    maximum_region_length: int


@dataclass(frozen=True)
class SequenceNormalisationRules:
    """Tracked normalisation configuration."""

    contract_version: str
    core_length_min: int
    core_length_max: int
    allowed_rna_bases: frozenset[str]
    allowed_dna_bases: frozenset[str]
    supported_ambiguity_codes: frozenset[str]
    display_separator_characters: frozenset[str]
    known_non_core_motifs: tuple[KnownMotifRule, ...]
    constant_region_inference: ConstantRegionInferenceConfig
    mixed_t_u_policy: str = "review"
    source_path: str | None = None


@dataclass(frozen=True)
class TrimProposal:
    """An approved or proposed trim of a prefix and/or suffix."""

    five_prime: str | None = None
    three_prime: str | None = None
    reason: str = ""
    confidence: float | None = None
    source: str = ""
    status: str = "approved"


@dataclass(frozen=True)
class AppliedTrim:
    """Provenance for one successfully applied trim side or combined plan."""

    side: str
    bases_removed: int
    reason: str
    confidence: float | None
    source: str
    sequence_removed_length: int


@dataclass(frozen=True)
class DetectedMotif:
    """A known motif observed in a sequence without automatic trimming."""

    name: str
    position: str
    start_index: int
    length: int
    action: str
    notes: str = ""


@dataclass(frozen=True)
class CoreLengthValidation:
    """Result of evaluating core length against the training policy."""

    sequence_length_core: int | None
    within_policy: bool
    flags: tuple[str, ...]


@dataclass(frozen=True)
class DisplayCleanResult:
    """Result of display-only cleaning."""

    sequence_raw: str | None
    sequence_display_clean: str | None
    transformations: tuple[str, ...]
    qc_flags: tuple[str, ...]
    is_missing: bool


@dataclass(frozen=True)
class AlphabetClassification:
    """Alphabet category for a cleaned sequence."""

    alphabet: str
    has_t: bool
    has_u: bool
    has_ambiguity: bool
    unexpected_characters: tuple[str, ...]
    qc_flags: tuple[str, ...]


@dataclass(frozen=True)
class SequenceNormalisationResult:
    """Structured result of shared sequence normalisation."""

    sequence_raw: str | None
    sequence_display_clean: str | None
    sequence_full: str | None
    sequence_core: str | None
    alphabet_as_reported: str
    alphabet_after_normalisation: str
    molecule_type: str
    t_to_u_applied: bool
    sequence_length_full: int | None
    sequence_length_core: int | None
    detected_motifs: tuple[DetectedMotif, ...]
    applied_trims: tuple[AppliedTrim, ...]
    qc_flags: tuple[str, ...]
    transformations: tuple[str, ...]


def _sorted_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{name} must be a mapping")
    return value


def _require_str_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(f"{name} must be a list of strings")
    return value


def _require_int(value: Any, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}")
    return value


def _require_float_01(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{name} must be a number")
    number = float(value)
    if number < 0.0 or number > 1.0:
        raise ConfigurationError(f"{name} must be between 0 and 1 inclusive")
    return number


def validate_rules_dict(payload: Mapping[str, Any]) -> SequenceNormalisationRules:
    """Validate a rules mapping and return a frozen configuration object."""
    data = _require_mapping(payload, "rules")

    contract_version = data.get("contract_version")
    if not isinstance(contract_version, str) or not contract_version.strip():
        raise ConfigurationError("contract_version must be a non-empty string")

    core_length_min = _require_int(data.get("core_length_min"), "core_length_min", minimum=1)
    core_length_max = _require_int(data.get("core_length_max"), "core_length_max", minimum=1)
    if core_length_min > core_length_max:
        raise ConfigurationError("core_length_min cannot exceed core_length_max")

    allowed_rna = frozenset(_require_str_list(data.get("allowed_rna_bases"), "allowed_rna_bases"))
    allowed_dna = frozenset(_require_str_list(data.get("allowed_dna_bases"), "allowed_dna_bases"))
    ambiguity = frozenset(
        _require_str_list(data.get("supported_ambiguity_codes"), "supported_ambiguity_codes")
    )
    separators = frozenset(
        _require_str_list(
            data.get("display_separator_characters"), "display_separator_characters"
        )
    )

    motifs_raw = data.get("known_non_core_motifs")
    if not isinstance(motifs_raw, list):
        raise ConfigurationError("known_non_core_motifs must be a list")
    motifs: list[KnownMotifRule] = []
    for index, item in enumerate(motifs_raw):
        motif = _require_mapping(item, f"known_non_core_motifs[{index}]")
        name = motif.get("name")
        sequence = motif.get("sequence")
        expected_position = motif.get("expected_position")
        action = motif.get("action")
        notes = motif.get("notes", "")
        if not isinstance(name, str) or not name:
            raise ConfigurationError(f"known_non_core_motifs[{index}].name must be a string")
        if not isinstance(sequence, str) or not sequence:
            raise ConfigurationError(
                f"known_non_core_motifs[{index}].sequence must be a non-empty string"
            )
        if not isinstance(expected_position, str) or not expected_position:
            raise ConfigurationError(
                f"known_non_core_motifs[{index}].expected_position must be a string"
            )
        if not isinstance(action, str) or not action:
            raise ConfigurationError(f"known_non_core_motifs[{index}].action must be a string")
        if notes is None:
            notes = ""
        if not isinstance(notes, str):
            raise ConfigurationError(f"known_non_core_motifs[{index}].notes must be a string")
        motifs.append(
            KnownMotifRule(
                name=name,
                sequence=sequence.upper(),
                expected_position=expected_position,
                action=action,
                notes=notes,
            )
        )

    inference_raw = _require_mapping(
        data.get("constant_region_inference"), "constant_region_inference"
    )
    inference = ConstantRegionInferenceConfig(
        minimum_group_size=_require_int(
            inference_raw.get("minimum_group_size"),
            "constant_region_inference.minimum_group_size",
            minimum=1,
        ),
        minimum_support=_require_float_01(
            inference_raw.get("minimum_support"),
            "constant_region_inference.minimum_support",
        ),
        minimum_region_length=_require_int(
            inference_raw.get("minimum_region_length"),
            "constant_region_inference.minimum_region_length",
            minimum=1,
        ),
        maximum_region_length=_require_int(
            inference_raw.get("maximum_region_length"),
            "constant_region_inference.maximum_region_length",
            minimum=1,
        ),
    )
    if inference.minimum_region_length > inference.maximum_region_length:
        raise ConfigurationError(
            "constant_region_inference.minimum_region_length cannot exceed "
            "maximum_region_length"
        )

    mixed_policy = data.get("mixed_t_u_policy", "review")
    if not isinstance(mixed_policy, str) or mixed_policy not in {"review", "rna_t_to_u"}:
        raise ConfigurationError(
            "mixed_t_u_policy must be 'review' or 'rna_t_to_u'"
        )

    return SequenceNormalisationRules(
        contract_version=contract_version.strip(),
        core_length_min=core_length_min,
        core_length_max=core_length_max,
        allowed_rna_bases=allowed_rna,
        allowed_dna_bases=allowed_dna,
        supported_ambiguity_codes=ambiguity,
        display_separator_characters=separators,
        known_non_core_motifs=tuple(motifs),
        constant_region_inference=inference,
        mixed_t_u_policy=mixed_policy,
    )


def load_normalisation_rules(
    path: str | Path | None = None,
) -> SequenceNormalisationRules:
    """Load and validate the tracked normalisation rules JSON."""
    rules_path = Path(path) if path is not None else DEFAULT_RULES_PATH
    try:
        text = rules_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"cannot read rules file: {exc.strerror}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"rules JSON is invalid: {exc.msg}") from exc
    if not isinstance(payload, Mapping):
        raise ConfigurationError("rules JSON root must be an object")
    rules = validate_rules_dict(payload)
    return SequenceNormalisationRules(
        contract_version=rules.contract_version,
        core_length_min=rules.core_length_min,
        core_length_max=rules.core_length_max,
        allowed_rna_bases=rules.allowed_rna_bases,
        allowed_dna_bases=rules.allowed_dna_bases,
        supported_ambiguity_codes=rules.supported_ambiguity_codes,
        display_separator_characters=rules.display_separator_characters,
        known_non_core_motifs=rules.known_non_core_motifs,
        constant_region_inference=rules.constant_region_inference,
        mixed_t_u_policy=rules.mixed_t_u_policy,
        source_path=str(rules_path),
    )


def _is_textual_null(value: str) -> bool:
    return value.strip().upper() in TEXTUAL_NULLS or value.strip() == "-"


def clean_display_sequence(
    sequence_raw: str | None,
    *,
    rules: SequenceNormalisationRules | None = None,
) -> DisplayCleanResult:
    """Remove display-only artefacts without changing nucleotide identity.

    Ambiguity codes and unexpected biological characters are retained. Empty or
    textual-null inputs return ``is_missing=True``.
    """
    active_rules = rules if rules is not None else load_normalisation_rules()
    transformations: list[str] = []
    qc_flags: list[str] = []

    if sequence_raw is None:
        return DisplayCleanResult(
            sequence_raw=None,
            sequence_display_clean=None,
            transformations=(),
            qc_flags=("missing_sequence",),
            is_missing=True,
        )

    original = sequence_raw
    text = str(sequence_raw)

    if _is_textual_null(text):
        return DisplayCleanResult(
            sequence_raw=original,
            sequence_display_clean=None,
            transformations=("textual_null",),
            qc_flags=("missing_sequence",),
            is_missing=True,
        )

    stripped = text.strip()
    if stripped != text:
        transformations.append("strip_whitespace")
        text = stripped

    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1]
        transformations.append("remove_wrapping_quotes")
        text = text.strip()

    if _is_textual_null(text):
        return DisplayCleanResult(
            sequence_raw=original,
            sequence_display_clean=None,
            transformations=tuple(transformations + ["textual_null"]),
            qc_flags=("missing_sequence",),
            is_missing=True,
        )

    before = text
    text = _LEADING_TERMINAL_RE.sub("", text)
    if text != before:
        transformations.append("remove_five_prime_label")

    before = text
    text = _TRAILING_TERMINAL_RE.sub("", text)
    if text != before:
        transformations.append("remove_three_prime_label")

    before = text
    text = _WHITESPACE_RE.sub("", text)
    if text != before:
        transformations.append("remove_whitespace")

    separators = active_rules.display_separator_characters
    if separators:
        before = text
        text = "".join(ch for ch in text if ch not in separators)
        if text != before:
            transformations.append("remove_display_separators")

    before = text
    text = text.upper()
    if text != before:
        transformations.append("uppercase")

    if not text:
        return DisplayCleanResult(
            sequence_raw=original,
            sequence_display_clean=None,
            transformations=tuple(transformations + ["empty_after_display_clean"]),
            qc_flags=("missing_sequence",),
            is_missing=True,
        )

    allowed = (
        active_rules.allowed_rna_bases
        | active_rules.allowed_dna_bases
        | active_rules.supported_ambiguity_codes
    )
    unexpected = _sorted_unique(ch for ch in text if ch not in allowed)
    if unexpected:
        qc_flags.append("invalid_character")

    return DisplayCleanResult(
        sequence_raw=original,
        sequence_display_clean=text,
        transformations=tuple(transformations),
        qc_flags=tuple(qc_flags),
        is_missing=False,
    )


def classify_alphabet(
    sequence: str | None,
    *,
    rules: SequenceNormalisationRules | None = None,
) -> AlphabetClassification:
    """Classify the alphabet of a cleaned sequence string."""
    active_rules = rules if rules is not None else load_normalisation_rules()

    if sequence is None or sequence == "":
        return AlphabetClassification(
            alphabet=ALPHABET_MISSING,
            has_t=False,
            has_u=False,
            has_ambiguity=False,
            unexpected_characters=(),
            qc_flags=("missing_sequence",),
        )

    text = sequence.upper()
    chars = set(text)
    rna = active_rules.allowed_rna_bases
    dna = active_rules.allowed_dna_bases
    ambiguity = active_rules.supported_ambiguity_codes
    canonical = rna | dna
    allowed = canonical | ambiguity

    unexpected = _sorted_unique(ch for ch in chars if ch not in allowed)
    has_t = "T" in chars
    has_u = "U" in chars
    has_ambiguity = bool(chars & ambiguity)
    qc_flags: list[str] = []

    if unexpected:
        qc_flags.append("invalid_character")
        return AlphabetClassification(
            alphabet=ALPHABET_INVALID,
            has_t=has_t,
            has_u=has_u,
            has_ambiguity=has_ambiguity,
            unexpected_characters=unexpected,
            qc_flags=tuple(qc_flags),
        )

    if has_ambiguity:
        qc_flags.append("ambiguous_base")
        return AlphabetClassification(
            alphabet=ALPHABET_AMBIGUOUS,
            has_t=has_t,
            has_u=has_u,
            has_ambiguity=True,
            unexpected_characters=(),
            qc_flags=tuple(qc_flags),
        )

    if has_t and has_u:
        qc_flags.append("mixed_t_u")
        return AlphabetClassification(
            alphabet=ALPHABET_MIXED_T_U,
            has_t=True,
            has_u=True,
            has_ambiguity=False,
            unexpected_characters=(),
            qc_flags=tuple(qc_flags),
        )

    # Subset of A/C/G/U with no T → RNA alphabet (includes A/C/G-only and U-bearing).
    if chars <= rna and not has_t:
        return AlphabetClassification(
            alphabet=ALPHABET_RNA,
            has_t=False,
            has_u=has_u,
            has_ambiguity=False,
            unexpected_characters=(),
            qc_flags=(),
        )

    # Subset of A/C/G/T with no U → DNA_T alphabet.
    if chars <= dna and not has_u:
        return AlphabetClassification(
            alphabet=ALPHABET_DNA_T,
            has_t=has_t,
            has_u=False,
            has_ambiguity=False,
            unexpected_characters=(),
            qc_flags=(),
        )

    return AlphabetClassification(
        alphabet=ALPHABET_INVALID,
        has_t=has_t,
        has_u=has_u,
        has_ambiguity=has_ambiguity,
        unexpected_characters=(),
        qc_flags=("invalid_character",),
    )


def _normalise_molecule_type(molecule_type: str | None) -> str:
    if molecule_type is None:
        return "unknown"
    text = str(molecule_type).strip()
    if not text or text.upper() in TEXTUAL_NULLS:
        return "unknown"
    upper = text.upper().replace("-", "")
    if upper in {"RNA"}:
        return "RNA"
    if upper in {"SSDNA", "SS_DNA"}:
        return "ssDNA"
    if upper in {"DNA", "DSDNA", "DS_DNA"}:
        return "DNA"
    if upper in {"UNKNOWN"}:
        return "unknown"
    raise SequenceNormalisationError(
        f"unsupported molecule_type label: {text!r}"
    )


def detect_known_non_core_motifs(
    sequence: str,
    rules: SequenceNormalisationRules | None = None,
) -> tuple[DetectedMotif, ...]:
    """Detect configured known motifs without trimming.

    Detection alone never authorises trimming. Motifs are reported in
    deterministic name/position order. DNA-alphabet motif definitions are also
    matched in T→U form so RNA ``sequence_full`` values remain detectable.
    """
    active_rules = rules if rules is not None else load_normalisation_rules()
    if not sequence:
        return ()

    text = sequence.upper()
    found: list[DetectedMotif] = []
    seen: set[tuple[str, int, str]] = set()
    for motif in active_rules.known_non_core_motifs:
        needles = [motif.sequence.upper()]
        rna_form = needles[0].replace("T", "U")
        if rna_form != needles[0]:
            needles.append(rna_form)
        for needle in needles:
            start = 0
            while True:
                index = text.find(needle, start)
                if index < 0:
                    break
                if motif.expected_position == "five_prime" and index != 0:
                    start = index + 1
                    continue
                if (
                    motif.expected_position == "three_prime"
                    and index + len(needle) != len(text)
                ):
                    start = index + 1
                    continue
                position = motif.expected_position
                if motif.expected_position not in {"five_prime", "three_prime"}:
                    position = "internal"
                key = (motif.name, index, position)
                if key not in seen:
                    seen.add(key)
                    found.append(
                        DetectedMotif(
                            name=motif.name,
                            position=position,
                            start_index=index,
                            length=len(needle),
                            action=motif.action,
                            notes=motif.notes,
                        )
                    )
                start = index + 1

    found.sort(key=lambda item: (item.name, item.start_index, item.position))
    return tuple(found)


def validate_core_length(
    sequence_core: str | None,
    rules: SequenceNormalisationRules | None = None,
) -> CoreLengthValidation:
    """Evaluate core length against the training corpus policy (20–100 nt)."""
    active_rules = rules if rules is not None else load_normalisation_rules()
    if sequence_core is None:
        return CoreLengthValidation(
            sequence_length_core=None,
            within_policy=False,
            flags=("missing_sequence",),
        )
    length = len(sequence_core)
    flags: list[str] = []
    if length < active_rules.core_length_min:
        flags.append("core_below_min_length")
    if length > active_rules.core_length_max:
        flags.append("core_above_max_length")
    return CoreLengthValidation(
        sequence_length_core=length,
        within_policy=not flags,
        flags=tuple(flags),
    )


def _apply_trim_plan(
    sequence_full: str,
    trim_plan: TrimProposal,
) -> tuple[str, tuple[AppliedTrim, ...], tuple[str, ...]]:
    """Apply an approved exact prefix/suffix trim plan.

    Raises ``TrimMismatchError`` when the approved trim does not match.
    Rejects trims that would remove the entire sequence.
    """
    five = trim_plan.five_prime.upper() if trim_plan.five_prime else None
    three = trim_plan.three_prime.upper() if trim_plan.three_prime else None
    remaining = sequence_full
    applied: list[AppliedTrim] = []
    flags: list[str] = []

    if five:
        if not remaining.startswith(five):
            raise TrimMismatchError("approved five_prime trim does not match sequence")
        remaining = remaining[len(five) :]
        applied.append(
            AppliedTrim(
                side="five_prime",
                bases_removed=len(five),
                reason=trim_plan.reason,
                confidence=trim_plan.confidence,
                source=trim_plan.source,
                sequence_removed_length=len(five),
            )
        )

    if three:
        if not remaining.endswith(three):
            raise TrimMismatchError("approved three_prime trim does not match sequence")
        remaining = remaining[: len(remaining) - len(three)]
        applied.append(
            AppliedTrim(
                side="three_prime",
                bases_removed=len(three),
                reason=trim_plan.reason,
                confidence=trim_plan.confidence,
                source=trim_plan.source,
                sequence_removed_length=len(three),
            )
        )

    if not remaining:
        raise TrimMismatchError("approved trim would remove the entire sequence")

    if trim_plan.status and trim_plan.status != "approved":
        flags.append("trim_requires_review")

    return remaining, tuple(applied), tuple(flags)


def normalise_sequence(
    sequence_raw: str | None,
    *,
    molecule_type: str | None = None,
    trim_plan: TrimProposal | None = None,
    rules: SequenceNormalisationRules | None = None,
) -> SequenceNormalisationResult:
    """Normalise a source sequence into full/core fields with provenance.

    ``sequence_raw`` is never overwritten. Without an approved trim plan,
    ``sequence_core`` equals ``sequence_full``. Detection of known motifs does
    not automatically trim.
    """
    active_rules = rules if rules is not None else load_normalisation_rules()
    transformations: list[str] = []
    qc_flags: list[str] = []

    display = clean_display_sequence(sequence_raw, rules=active_rules)
    transformations.extend(display.transformations)
    qc_flags.extend(display.qc_flags)

    resolved_molecule = _normalise_molecule_type(molecule_type)

    if display.is_missing or display.sequence_display_clean is None:
        if resolved_molecule == "unknown":
            qc_flags.append("molecule_type_unknown")
        return SequenceNormalisationResult(
            sequence_raw=sequence_raw,
            sequence_display_clean=None,
            sequence_full=None,
            sequence_core=None,
            alphabet_as_reported=ALPHABET_MISSING,
            alphabet_after_normalisation=ALPHABET_MISSING,
            molecule_type=resolved_molecule,
            t_to_u_applied=False,
            sequence_length_full=None,
            sequence_length_core=None,
            detected_motifs=(),
            applied_trims=(),
            qc_flags=_sorted_unique(qc_flags),
            transformations=tuple(transformations),
        )

    cleaned = display.sequence_display_clean
    reported = classify_alphabet(cleaned, rules=active_rules)
    qc_flags.extend(reported.qc_flags)
    alphabet_as_reported = reported.alphabet

    sequence_full = cleaned
    t_to_u_applied = False
    alphabet_after = alphabet_as_reported

    if alphabet_as_reported == ALPHABET_INVALID:
        # Do not repair by dropping characters.
        if resolved_molecule == "unknown":
            qc_flags.append("molecule_type_unknown")
        detected = detect_known_non_core_motifs(sequence_full, active_rules)
        if any(m.name == "t7_promoter_minimal" for m in detected):
            qc_flags.append("known_promoter_detected")
        return SequenceNormalisationResult(
            sequence_raw=sequence_raw,
            sequence_display_clean=cleaned,
            sequence_full=sequence_full,
            sequence_core=sequence_full,
            alphabet_as_reported=alphabet_as_reported,
            alphabet_after_normalisation=alphabet_after,
            molecule_type=resolved_molecule,
            t_to_u_applied=False,
            sequence_length_full=len(sequence_full),
            sequence_length_core=len(sequence_full),
            detected_motifs=detected,
            applied_trims=(),
            qc_flags=_sorted_unique(qc_flags),
            transformations=tuple(transformations),
        )

    if alphabet_as_reported == ALPHABET_MIXED_T_U:
        if "mixed_t_u" not in qc_flags:
            qc_flags.append("mixed_t_u")
        if resolved_molecule == "RNA" and active_rules.mixed_t_u_policy == "rna_t_to_u":
            sequence_full = cleaned.replace("T", "U")
            t_to_u_applied = "T" in cleaned
            if t_to_u_applied:
                transformations.append("t_to_u")
            alphabet_after = classify_alphabet(sequence_full, rules=active_rules).alphabet
        else:
            # Conservative default: leave for review; do not silently repair.
            qc_flags.append("trim_requires_review")
            if resolved_molecule == "RNA":
                qc_flags.append("t_in_reported_rna")
            if resolved_molecule in {"DNA", "ssDNA"}:
                qc_flags.append("u_in_reported_dna")
            alphabet_after = ALPHABET_MIXED_T_U
    elif resolved_molecule == "RNA":
        if "T" in cleaned:
            sequence_full = cleaned.replace("T", "U")
            t_to_u_applied = True
            transformations.append("t_to_u")
            qc_flags.append("t_in_reported_rna")
        alphabet_after = classify_alphabet(sequence_full, rules=active_rules).alphabet
        if alphabet_after == ALPHABET_DNA_T and "T" not in sequence_full:
            # A/C/G-only under explicit RNA is reported as RNA after normalisation.
            alphabet_after = ALPHABET_RNA
    elif resolved_molecule in {"DNA", "ssDNA"}:
        if "U" in cleaned:
            qc_flags.append("u_in_reported_dna")
        # Never convert U→T silently; retain as reported after display clean.
        alphabet_after = alphabet_as_reported
    else:
        # unknown molecule type — do not force RNA from a T-only alphabet.
        if alphabet_as_reported == ALPHABET_RNA and reported.has_u:
            resolved_molecule = "RNA"
            alphabet_after = ALPHABET_RNA
        elif alphabet_as_reported == ALPHABET_DNA_T and reported.has_t:
            resolved_molecule = "unknown"
            qc_flags.append("molecule_type_unknown")
            alphabet_after = ALPHABET_DNA_T
        else:
            resolved_molecule = "unknown"
            qc_flags.append("molecule_type_unknown")
            alphabet_after = alphabet_as_reported

    detected = detect_known_non_core_motifs(sequence_full, active_rules)
    if any(motif.name == "t7_promoter_minimal" for motif in detected):
        qc_flags.append("known_promoter_detected")
    # Motifs with action flag_only never auto-trim.
    for motif in detected:
        if motif.action != "flag_only":
            qc_flags.append("trim_requires_review")

    applied_trims: tuple[AppliedTrim, ...] = ()
    sequence_core = sequence_full
    if trim_plan is not None:
        if trim_plan.status and trim_plan.status not in {"approved", ""}:
            qc_flags.append("trim_requires_review")
            # Unapproved plans are not applied.
        else:
            sequence_core, applied_trims, trim_flags = _apply_trim_plan(
                sequence_full, trim_plan
            )
            qc_flags.extend(trim_flags)
            if applied_trims:
                transformations.append("apply_approved_trim")

    length_check = validate_core_length(sequence_core, active_rules)
    qc_flags.extend(length_check.flags)

    return SequenceNormalisationResult(
        sequence_raw=sequence_raw,
        sequence_display_clean=cleaned,
        sequence_full=sequence_full,
        sequence_core=sequence_core,
        alphabet_as_reported=alphabet_as_reported,
        alphabet_after_normalisation=alphabet_after,
        molecule_type=resolved_molecule,
        t_to_u_applied=t_to_u_applied,
        sequence_length_full=len(sequence_full) if sequence_full is not None else None,
        sequence_length_core=len(sequence_core) if sequence_core is not None else None,
        detected_motifs=detected,
        applied_trims=applied_trims,
        qc_flags=_sorted_unique(qc_flags),
        transformations=tuple(transformations),
    )


def rules_to_public_dict(rules: SequenceNormalisationRules) -> dict[str, Any]:
    """Return a JSON-serialisable view of rules without absolute path leakage."""
    return {
        "contract_version": rules.contract_version,
        "core_length_min": rules.core_length_min,
        "core_length_max": rules.core_length_max,
        "allowed_rna_bases": sorted(rules.allowed_rna_bases),
        "allowed_dna_bases": sorted(rules.allowed_dna_bases),
        "supported_ambiguity_codes": sorted(rules.supported_ambiguity_codes),
        "display_separator_characters": sorted(rules.display_separator_characters),
        "known_non_core_motifs": [
            {
                "name": motif.name,
                "sequence": motif.sequence,
                "expected_position": motif.expected_position,
                "action": motif.action,
                "notes": motif.notes,
            }
            for motif in rules.known_non_core_motifs
        ],
        "constant_region_inference": {
            "minimum_group_size": rules.constant_region_inference.minimum_group_size,
            "minimum_support": rules.constant_region_inference.minimum_support,
            "minimum_region_length": rules.constant_region_inference.minimum_region_length,
            "maximum_region_length": rules.constant_region_inference.maximum_region_length,
        },
        "mixed_t_u_policy": rules.mixed_t_u_policy,
    }

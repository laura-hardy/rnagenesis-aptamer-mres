"""UTexas RNA alphabet-exception diagnostics and proposed classification.

This module inspects source-reported RNA records that S3 rejected for
``ambiguous_bases`` or ``invalid_alphabet``. It proposes a scientific
exception class and, only when safe, an underlying A/C/G/U sequence.

Canonical S2 sequences are mutated only when a tracked
``accept_recovered_sequence`` resolution authorises a named recovery.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Mapping, Sequence

CLASS_RECOVERABLE: Final[str] = "recoverable_modification_notation"
CLASS_IUPAC: Final[str] = "true_iupac_degenerate_sequence"
CLASS_UNRESOLVED_MOD: Final[str] = "modified_rna_underlying_sequence_unresolved"
CLASS_MALFORMED: Final[str] = "malformed_or_unrecoverable"
CLASS_NEEDS_REVIEW: Final[str] = "needs_manual_source_review"

ALLOWED_EXCEPTION_CLASSES: Final[frozenset[str]] = frozenset(
    {
        CLASS_RECOVERABLE,
        CLASS_IUPAC,
        CLASS_UNRESOLVED_MOD,
        CLASS_MALFORMED,
        CLASS_NEEDS_REVIEW,
    }
)

SUGGESTED_ACCEPT_RECOVERED: Final[str] = "accept_recovered_sequence"
SUGGESTED_CONFIRM_REJECT: Final[str] = "confirm_reject"
SUGGESTED_OVERRIDE_PARK: Final[str] = "override_to_park"
SUGGESTED_SOURCE_REVIEW: Final[str] = "needs_source_review"

ALLOWED_REVIEW_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        SUGGESTED_ACCEPT_RECOVERED,
        SUGGESTED_CONFIRM_REJECT,
        SUGGESTED_OVERRIDE_PARK,
        SUGGESTED_SOURCE_REVIEW,
        "",
    }
)

CANONICAL_RNA: Final[frozenset[str]] = frozenset("ACGU")
IUPAC_AMBIGUITY: Final[frozenset[str]] = frozenset("NRYWSMKHBVD")
STANDARD_NUCLEOTIDES: Final[frozenset[str]] = frozenset("ACGUT")
NONSTANDARD_BASE_SYMBOLS: Final[frozenset[str]] = frozenset("IOFXΨψ")

PRIMARY_REASONS: Final[frozenset[str]] = frozenset(
    {"ambiguous_bases", "invalid_alphabet"}
)
EXPECTED_EXCEPTION_ROWS: Final[int] = 31
EXPECTED_AMBIGUOUS: Final[int] = 8
EXPECTED_INVALID: Final[int] = 23

PRIME_CHARS: Final[str] = "'′’‘`´ʹ΄\""
_PRIME_CLASS: Final[str] = r"['′’‘`´ʹ΄\"]"

_LEADING_FIVE_PRIME_RE = re.compile(
    rf"^5\s*{_PRIME_CLASS}*\s*",
    re.IGNORECASE,
)
_TRAILING_THREE_PRIME_RE = re.compile(
    rf"\s*{_PRIME_CLASS}*\s*3\s*{_PRIME_CLASS}*\s*$",
    re.IGNORECASE,
)
_REVERSED_TRAILING_THREE_RE = re.compile(
    rf"\s*{_PRIME_CLASS}+\s*3\s*$",
)
_INVERTED_CAP_RE = re.compile(
    rf"(?:3\s*{_PRIME_CLASS}*)?\s*\(\s*3\s*{_PRIME_CLASS}*\s*([UT])\s*5\s*{_PRIME_CLASS}*\s*\)\s*$",
    re.IGNORECASE,
)
_TWO_PRIME_F_RE = re.compile(
    rf"\(\s*2\s*{_PRIME_CLASS}?\s*F\s*([ACGUT])\s*\)",
    re.IGNORECASE,
)
_INVERTED_DEOXY_RE = re.compile(r"id([ACGUT])$", re.IGNORECASE)
_GCON_RE = re.compile(r"Gcon", re.IGNORECASE)
_TWO_OME_PS_RE = re.compile(
    r"m\(\s*([ACGUT])\s*s\s*([ACGUT])\s*\)",
    re.IGNORECASE,
)
_TWO_OME_RE = re.compile(
    r"m\(\s*([ACGUT]+)\s*\)",
    re.IGNORECASE,
)
_PAREN_RE = re.compile(r"\([^()]*\)")
_BRACKET_RE = re.compile(r"\[[^\[\]]*\]")
_N_RUN_RE = re.compile(r"N\d+", re.IGNORECASE)
_INTERNAL_JUNCTION_RE = re.compile(
    rf"([ACGU]{{8,}})3{_PRIME_CLASS}*\s*5{_PRIME_CLASS}*([ACGU]{{8,}})",
    re.IGNORECASE,
)
_CONCAT_LABEL_RE = re.compile(
    r"surand|complementary\s*strand|complementarystrand|strand\s*:",
    re.IGNORECASE,
)
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_PHOSPHOROTHIOATE_S_RE = re.compile(r"(?<=[ACGUTNacgutn])s(?=[ACGUTNacgutn])")

YES: Final[str] = "yes"
NO: Final[str] = "no"
UNCLEAR: Final[str] = "unclear"

CLASS_TO_SUGGESTED_ACTION: Final[Mapping[str, str]] = {
    CLASS_RECOVERABLE: SUGGESTED_ACCEPT_RECOVERED,
    CLASS_IUPAC: SUGGESTED_CONFIRM_REJECT,
    CLASS_UNRESOLVED_MOD: SUGGESTED_OVERRIDE_PARK,
    CLASS_MALFORMED: SUGGESTED_CONFIRM_REJECT,
    CLASS_NEEDS_REVIEW: SUGGESTED_SOURCE_REVIEW,
}

REVIEW_POLICY_VERSION: Final[str] = "utexas_alphabet_exceptions_v1"
REVIEW_DECISION_DATE: Final[str] = "2026-08-13"

REASON_ACCEPT_RECOVERED: Final[str] = (
    "Approved at the alphabet-normalisation level only; remains subject to "
    "approved constant-region processing, core length 20-100, and other S3 "
    "technical rules."
)
REASON_IUPAC_REJECT: Final[str] = (
    "Genuine IUPAC/degenerate sequence; no arbitrary nucleotide substitution "
    "is scientifically justified."
)
REASON_MALFORMED_REJECT: Final[str] = (
    "Sequence field is corrupted/unrecoverable; no deterministic underlying "
    "RNA sequence can be established."
)
REASON_COMPLEX_PARK: Final[str] = (
    "Complex or concatenated RNA construct; underlying standalone aptamer "
    "sequence not deterministically recoverable from the database sequence "
    "field. Retained as parked rather than rejected."
)

CLASS_TO_HUMAN_ACTION: Final[Mapping[str, str]] = {
    CLASS_RECOVERABLE: SUGGESTED_ACCEPT_RECOVERED,
    CLASS_IUPAC: SUGGESTED_CONFIRM_REJECT,
    CLASS_MALFORMED: SUGGESTED_CONFIRM_REJECT,
    CLASS_NEEDS_REVIEW: SUGGESTED_OVERRIDE_PARK,
}

CLASS_TO_HUMAN_REASON: Final[Mapping[str, str]] = {
    CLASS_RECOVERABLE: REASON_ACCEPT_RECOVERED,
    CLASS_IUPAC: REASON_IUPAC_REJECT,
    CLASS_MALFORMED: REASON_MALFORMED_REJECT,
    CLASS_NEEDS_REVIEW: REASON_COMPLEX_PARK,
}

EXPECTED_CLASS_COUNTS: Final[Mapping[str, int]] = {
    CLASS_RECOVERABLE: 17,
    CLASS_IUPAC: 9,
    CLASS_UNRESOLVED_MOD: 0,
    CLASS_MALFORMED: 1,
    CLASS_NEEDS_REVIEW: 4,
}

EXPECTED_DECISION_COUNTS: Final[Mapping[str, int]] = {
    SUGGESTED_ACCEPT_RECOVERED: 17,
    SUGGESTED_CONFIRM_REJECT: 10,
    SUGGESTED_OVERRIDE_PARK: 4,
    SUGGESTED_SOURCE_REVIEW: 0,
    "": 0,
}

RESOLUTION_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "decision",
    "transformation_profile",
    "expected_recovered_length",
    "review_note",
)

RECOVERY_AUDIT_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "decision",
    "transformation_profile",
    "expected_recovered_length",
    "recovered_length",
    "applied",
)

REVIEW_COLUMNS: Final[tuple[str, ...]] = (
    "record_id",
    "native_id",
    "name_of_aptamer",
    "source_type_of_nucleic_acid",
    "molecule_type",
    "chemistry",
    "sequence_raw",
    "sequence_full",
    "sequence_core",
    "alphabet_as_reported",
    "qc_flags",
    "proposed_decision",
    "primary_reason",
    "post_selex_modifications",
    "additional_information",
    "source_sequence_length",
    "source_gc_content",
    "publication",
    "doi",
    "pubmed_id",
    "pubmed_link",
    "target_name_raw",
    "pool_type",
    "pool_random_region",
    "utexas_application_as_quoted",
    "utexas_serial_number",
    "unexpected_characters",
    "unexpected_tokens",
    "contains_iupac_ambiguity",
    "contains_bracketed_modification",
    "contains_parenthetical_modification",
    "contains_digit_annotation",
    "contains_star_or_linkage_marker",
    "contains_nonstandard_base_symbol",
    "contains_internal_separator",
    "contains_other_notation",
    "contains_cyrillic_lookalike",
    "contains_concatenated_entries",
    "unexpected_token_positions",
    "exception_class",
    "proposed_underlying_rna_sequence",
    "recovery_transformations",
    "recovery_confidence",
    "recovered_sequence_length",
    "recovered_passes_length_policy",
    "modification_metadata_supports_interpretation",
    "modification_metadata_reason",
    "suggested_review_action",
    "suggested_later_disposition",
    "review_action",
    "reviewer_note",
    "reviewer_initials",
)


class AlphabetExceptionError(ValueError):
    """Hard failure during alphabet-exception review (never embeds sequences)."""


@dataclass(frozen=True)
class SequenceDiagnostic:
    """Character-level diagnostic of why a sequence failed A/C/G/U validation."""

    unexpected_characters: tuple[str, ...]
    unexpected_tokens: tuple[str, ...]
    contains_iupac_ambiguity: bool
    contains_bracketed_modification: bool
    contains_parenthetical_modification: bool
    contains_digit_annotation: bool
    contains_star_or_linkage_marker: bool
    contains_nonstandard_base_symbol: bool
    contains_internal_separator: bool
    contains_other_notation: bool
    contains_cyrillic_lookalike: bool
    contains_concatenated_entries: bool
    contains_numbered_n_run: bool
    unexpected_token_positions: str


@dataclass(frozen=True)
class RecoveryResult:
    """Attempted recovery of an underlying A/C/G/U sequence."""

    sequence: str
    transformations: tuple[str, ...]
    confidence: str
    leftover_characters: tuple[str, ...]


@dataclass(frozen=True)
class AlphabetResolution:
    """Sequence-safe human alphabet-exception resolution for one record."""

    record_id: str
    decision: str
    transformation_profile: str
    expected_recovered_length: int | None
    review_note: str


@dataclass(frozen=True)
class ExceptionClassification:
    """Proposed exception class plus optional recovered sequence."""

    exception_class: str
    proposed_underlying_rna_sequence: str
    recovery_transformations: tuple[str, ...]
    recovery_confidence: str
    modification_metadata_supports_interpretation: str
    modification_metadata_reason: str
    suggested_review_action: str
    suggested_later_disposition: str


def _yes_no(value: bool) -> str:
    return YES if value else NO


def _pipe(values: Sequence[str]) -> str:
    return "|".join(values)


def _unique_sorted_chars(text: str, *, predicate) -> tuple[str, ...]:
    return tuple(sorted({ch for ch in text if predicate(ch)}, key=lambda ch: (ord(ch), ch)))


def _has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text or ""))


def _has_concatenated_entries(sequence_raw: str, sequence_full: str) -> bool:
    raw = sequence_raw or ""
    full = sequence_full or ""
    if _CONCAT_LABEL_RE.search(raw) or _CONCAT_LABEL_RE.search(full):
        return True
    if "\n" in raw and _INTERNAL_JUNCTION_RE.search(raw.replace("\n", "")):
        return True
    if _INTERNAL_JUNCTION_RE.search(full):
        return True
    if _INTERNAL_JUNCTION_RE.search(re.sub(r"\s+", "", raw)):
        return True
    return False


def diagnose_sequence(*, sequence_full: str, sequence_raw: str) -> SequenceDiagnostic:
    """Diagnose non-ACGU notation in the failed canonical string.

    ``sequence_full`` is the S2/S3 string that failed A/C/G/U validation.
    ``sequence_raw`` is consulted only for case-sensitive linkage markers and
    concatenation/newlines. No characters are removed.
    """
    full = sequence_full or ""
    raw = sequence_raw or ""
    inspect = full if full else raw
    upper = inspect.upper()

    unexpected_chars = _unique_sorted_chars(
        upper, predicate=lambda ch: ch not in CANONICAL_RNA
    )
    parens = tuple(dict.fromkeys(_PAREN_RE.findall(inspect)))
    brackets = tuple(dict.fromkeys(_BRACKET_RE.findall(inspect)))
    n_runs = tuple(dict.fromkeys(_N_RUN_RE.findall(inspect)))

    tokens: list[str] = []
    tokens.extend(parens)
    tokens.extend(brackets)
    tokens.extend(n_runs)
    if _LEADING_FIVE_PRIME_RE.match(inspect) or _LEADING_FIVE_PRIME_RE.match(raw):
        tokens.append("leading_five_prime_label")
    if _TRAILING_THREE_PRIME_RE.search(inspect) or _REVERSED_TRAILING_THREE_RE.search(
        inspect
    ):
        tokens.append("trailing_three_prime_label")
    if _INVERTED_CAP_RE.search(inspect) or _INVERTED_CAP_RE.search(raw):
        tokens.append("inverted_terminal_cap")
    if _GCON_RE.search(raw) or _GCON_RE.search(inspect):
        tokens.append("Gcon")
    if _INVERTED_DEOXY_RE.search(inspect.rstrip()) or _INVERTED_DEOXY_RE.search(
        raw.rstrip()
    ):
        tokens.append("inverted_deoxy_cap")
    if _TWO_OME_RE.search(raw) or _TWO_OME_RE.search(inspect):
        tokens.append("two_prime_ome_parenthetical")

    iupac_present = any(ch in IUPAC_AMBIGUITY for ch in upper)
    digits = any(ch.isdigit() for ch in inspect)
    stars = "*" in inspect or "*" in raw
    linkage = bool(_PHOSPHOROTHIOATE_S_RE.search(raw))
    nonstandard = any(ch in NONSTANDARD_BASE_SYMBOLS for ch in upper)
    internal_sep = (
        "\n" in raw
        or "\r" in raw
        or bool(_INTERNAL_JUNCTION_RE.search(upper))
    )
    cyrillic = _has_cyrillic(inspect) or _has_cyrillic(raw)
    concatenated = _has_concatenated_entries(raw, full)
    other = any(
        (not ch.isalnum())
        and ch not in CANONICAL_RNA
        and ch not in "[]()*"
        and not ch.isspace()
        for ch in inspect
    )
    if cyrillic:
        other = True

    positions: list[str] = []
    for token in parens + brackets + n_runs:
        start = inspect.find(token)
        if start >= 0:
            positions.append(f"{token}@{start + 1}-{start + len(token)}")
    for index, ch in enumerate(upper):
        if ch in IUPAC_AMBIGUITY or ch in NONSTANDARD_BASE_SYMBOLS:
            positions.append(f"{ch}@{index + 1}")
    # Keep positions compact and deterministic.
    positions = list(dict.fromkeys(positions))

    return SequenceDiagnostic(
        unexpected_characters=unexpected_chars,
        unexpected_tokens=tuple(dict.fromkeys(tokens)),
        contains_iupac_ambiguity=iupac_present,
        contains_bracketed_modification=bool(brackets),
        contains_parenthetical_modification=bool(parens),
        contains_digit_annotation=digits,
        contains_star_or_linkage_marker=stars or linkage,
        contains_nonstandard_base_symbol=nonstandard,
        contains_internal_separator=internal_sep,
        contains_other_notation=other,
        contains_cyrillic_lookalike=cyrillic,
        contains_concatenated_entries=concatenated,
        contains_numbered_n_run=bool(n_runs),
        unexpected_token_positions=_pipe(positions),
    )


def _map_t_in_explicit_token(base: str) -> str:
    upper = base.upper()
    if upper == "T":
        return "U"
    return upper


def attempt_recovery(sequence_raw: str) -> RecoveryResult:
    """Apply only local, named, unambiguous notation transforms.

    Unknown characters are never deleted. If anything non-ACGU remains,
    ``sequence`` is empty.
    """
    working = sequence_raw or ""
    transformations: list[str] = []

    if not working:
        return RecoveryResult("", (), "unresolved", ())

    def _apply(pattern: re.Pattern[str], repl, name: str) -> None:
        nonlocal working
        updated, count = pattern.subn(repl, working)
        if count:
            working = updated
            transformations.append(name)

    before = working
    working = _LEADING_FIVE_PRIME_RE.sub("", working)
    if working != before:
        transformations.append("remove_leading_five_prime_display_label")

    before = working
    updated = _TRAILING_THREE_PRIME_RE.sub("", working)
    if updated != working:
        working = updated
        transformations.append("remove_trailing_three_prime_display_label")
    else:
        updated = _REVERSED_TRAILING_THREE_RE.sub("", working)
        if updated != working:
            working = updated
            transformations.append("remove_reversed_trailing_three_prime_label")

    def _inverted_cap(match: re.Match[str]) -> str:
        return _map_t_in_explicit_token(match.group(1))

    _apply(_INVERTED_CAP_RE, _inverted_cap, "map_inverted_terminal_cap_to_base")

    def _two_prime_f(match: re.Match[str]) -> str:
        return _map_t_in_explicit_token(match.group(1))

    _apply(_TWO_PRIME_F_RE, _two_prime_f, "map_2f_parenthetical_residue")

    def _id_cap(match: re.Match[str]) -> str:
        return _map_t_in_explicit_token(match.group(1))

    _apply(_INVERTED_DEOXY_RE, _id_cap, "map_inverted_deoxy_cap_to_base")
    _apply(_GCON_RE, "G", "map_gcon_conserved_guanosine")

    def _ome_ps(match: re.Match[str]) -> str:
        return _map_t_in_explicit_token(match.group(1)) + _map_t_in_explicit_token(
            match.group(2)
        )

    _apply(_TWO_OME_PS_RE, _ome_ps, "map_2ome_phosphorothioate_parenthetical")

    def _ome(match: re.Match[str]) -> str:
        return "".join(_map_t_in_explicit_token(ch) for ch in match.group(1))

    _apply(_TWO_OME_RE, _ome, "map_2ome_parenthetical_residues")

    leftover = _unique_sorted_chars(
        working.upper(), predicate=lambda ch: ch not in CANONICAL_RNA and not ch.isspace()
    )
    compact = re.sub(r"\s+", "", working).upper()
    leftover_compact = _unique_sorted_chars(
        compact, predicate=lambda ch: ch not in CANONICAL_RNA
    )
    if leftover_compact:
        return RecoveryResult("", tuple(transformations), "unresolved", leftover_compact)
    if not compact:
        return RecoveryResult("", tuple(transformations), "unresolved", leftover)
    if not all(ch in CANONICAL_RNA for ch in compact):
        return RecoveryResult("", tuple(transformations), "unresolved", leftover_compact)
    confidence = "high" if transformations else "unresolved"
    if not transformations:
        # Already canonical ACGU — not an alphabet exception recovery.
        return RecoveryResult(compact, (), "unresolved", ())
    return RecoveryResult(compact, tuple(transformations), confidence, ())


def _metadata_blob(*parts: str) -> str:
    return " ".join(part or "" for part in parts).strip().lower()


def assess_modification_metadata(
    *,
    exception_class: str,
    diagnostic: SequenceDiagnostic,
    post_selex: str,
    additional: str,
    recovered: bool,
    recovery_transformations: Sequence[str] = (),
) -> tuple[str, str]:
    """Compare sequence notation with post-SELEX / additional-information text.

    Reasons are sequence-safe: they never paste aptamer sequences.
    """
    blob = _metadata_blob(post_selex, additional)
    has_mod_text = bool(blob) and blob not in {"not applicable", "n/a", "na", "none"}
    transforms = set(recovery_transformations)

    if exception_class == CLASS_IUPAC:
        if any(
            token in blob
            for token in (
                "r=a or g",
                "y=c or u",
                "y = pyrimidine",
                "r = purine",
                "n=any",
                "any residue",
            )
        ):
            return YES, "source explicitly defines IUPAC ambiguity codes"
        if diagnostic.contains_numbered_n_run:
            return YES, "numbered N-run notation represents variable library positions"
        return YES, "IUPAC ambiguity appears to represent a variable position"

    if exception_class == CLASS_RECOVERABLE:
        if "map_inverted_terminal_cap_to_base" in transforms and (
            "thymidine cap" in blob or "3'-3'" in blob or "3′-3′" in blob
        ):
            return YES, "source explicitly reports a 3'-3' inverted terminal cap"
        if "map_2f_parenthetical_residue" in transforms and (
            "2′fc" in blob
            or "2'fc" in blob
            or "2′-flurocytosine" in blob
            or "2'-flurocytosine" in blob
            or "2′-fluoro" in blob
            or "2'-fluoro" in blob
        ):
            return YES, "source explicitly reports modified cytidine/uridine tokens"
        if "map_gcon_conserved_guanosine" in transforms and (
            "gcon" in blob and "conserved" in blob
        ):
            return YES, "source describes Gcon as a conserved guanosine"
        if (
            "map_2ome_parenthetical_residues" in transforms
            or "map_2ome_phosphorothioate_parenthetical" in transforms
        ) and (
            "2′-fluorine" in blob
            or "2'-fluorine" in blob
            or "o-methyl" in blob
            or "2'-o" in blob
        ):
            return YES, "source reports 2'-modified RNA consistent with mapped tokens"
        if "map_inverted_terminal_cap_to_base" in transforms:
            return YES, "inverted terminal cap token has an explicit underlying base"
        if recovered and transforms <= {
            "remove_leading_five_prime_display_label",
            "remove_trailing_three_prime_display_label",
            "remove_reversed_trailing_three_prime_label",
        }:
            if not has_mod_text:
                return NO, "no modification information; leftover characters are display labels"
            return UNCLEAR, "display-label recovery; modification text is not required"
        if recovered:
            return YES, "mapped tokens have explicit underlying bases in the source notation"
        return UNCLEAR, "recovery proposed but modification text is limited"

    if exception_class == CLASS_UNRESOLVED_MOD:
        if has_mod_text:
            return YES, "source describes modified RNA but specialised residues cannot be reduced"
        return UNCLEAR, "modified-residue symbols present; modification text is limited"

    if exception_class == CLASS_MALFORMED:
        if diagnostic.contains_cyrillic_lookalike:
            return NO, "mixed-script lookalike characters indicate a corrupted sequence field"
        return NO, "sequence notation is malformed; metadata does not supply a recoverable alphabet"

    if exception_class == CLASS_NEEDS_REVIEW:
        if diagnostic.contains_concatenated_entries:
            return UNCLEAR, "sequence field appears to concatenate more than one construct"
        return UNCLEAR, "local UTexas fields are insufficient for a confident mapping"

    return UNCLEAR, "no modification information"


def _later_disposition(exception_class: str) -> str:
    if exception_class == CLASS_RECOVERABLE:
        return "recover"
    if exception_class == CLASS_UNRESOLVED_MOD:
        return "park"
    if exception_class == CLASS_NEEDS_REVIEW:
        return "source_review"
    return "reject"


def classify_exception(
    *,
    sequence_raw: str,
    sequence_full: str,
    diagnostic: SequenceDiagnostic | None = None,
    post_selex: str = "",
    additional: str = "",
    chemistry: str = "",
    source_type: str = "",
) -> ExceptionClassification:
    """Propose an exception class without applying it to canonical data."""
    diagnostic = diagnostic or diagnose_sequence(
        sequence_full=sequence_full, sequence_raw=sequence_raw
    )
    blob = _metadata_blob(post_selex, additional, chemistry, source_type)
    modified_rna_context = any(
        token in blob
        for token in (
            "2'-fluoro",
            "2′-fluoro",
            "2'-amino",
            "2′-amino",
            "2'-o-me",
            "2′-o-me",
            "o-methyl",
            "modified rna",
            "2f-rna",
            "2nh2-rna",
            "2ome-rna",
        )
    )

    if diagnostic.contains_cyrillic_lookalike:
        exception_class = CLASS_MALFORMED
        recovery = RecoveryResult("", (), "unresolved", diagnostic.unexpected_characters)
    elif diagnostic.contains_concatenated_entries:
        exception_class = CLASS_NEEDS_REVIEW
        recovery = RecoveryResult("", (), "unresolved", ())
    else:
        recovery = attempt_recovery(sequence_raw)
        if recovery.sequence and recovery.confidence == "high":
            exception_class = CLASS_RECOVERABLE
        elif diagnostic.contains_numbered_n_run or (
            diagnostic.contains_iupac_ambiguity
            and not diagnostic.contains_parenthetical_modification
            and not diagnostic.contains_cyrillic_lookalike
            and set(diagnostic.unexpected_characters) <= IUPAC_AMBIGUITY
        ):
            exception_class = CLASS_IUPAC
            recovery = RecoveryResult("", (), "unresolved", ())
        elif (
            diagnostic.contains_nonstandard_base_symbol
            or diagnostic.contains_parenthetical_modification
        ) and modified_rna_context:
            exception_class = CLASS_UNRESOLVED_MOD
        elif recovery.leftover_characters and not diagnostic.contains_iupac_ambiguity:
            leftover_set = set(recovery.leftover_characters)
            if leftover_set & set("!@#$%^&{}\\|<>") or any(
                ord(ch) > 127 for ch in leftover_set
            ):
                exception_class = CLASS_MALFORMED
            elif modified_rna_context:
                exception_class = CLASS_UNRESOLVED_MOD
            else:
                exception_class = CLASS_NEEDS_REVIEW
        elif diagnostic.contains_iupac_ambiguity:
            exception_class = CLASS_IUPAC
        else:
            exception_class = CLASS_NEEDS_REVIEW
            recovery = RecoveryResult("", recovery.transformations, "unresolved", recovery.leftover_characters)

    supports, reason = assess_modification_metadata(
        exception_class=exception_class,
        diagnostic=diagnostic,
        post_selex=post_selex,
        additional=additional,
        recovered=bool(recovery.sequence),
        recovery_transformations=recovery.transformations,
    )
    if exception_class == CLASS_RECOVERABLE and not recovery.sequence:
        exception_class = CLASS_NEEDS_REVIEW
        supports, reason = assess_modification_metadata(
            exception_class=exception_class,
            diagnostic=diagnostic,
            post_selex=post_selex,
            additional=additional,
            recovered=False,
            recovery_transformations=(),
        )

    return ExceptionClassification(
        exception_class=exception_class,
        proposed_underlying_rna_sequence=recovery.sequence
        if exception_class == CLASS_RECOVERABLE
        else "",
        recovery_transformations=recovery.transformations
        if exception_class == CLASS_RECOVERABLE
        else (),
        recovery_confidence=recovery.confidence
        if exception_class == CLASS_RECOVERABLE
        else "unresolved",
        modification_metadata_supports_interpretation=supports,
        modification_metadata_reason=reason,
        suggested_review_action=CLASS_TO_SUGGESTED_ACTION[exception_class],
        suggested_later_disposition=_later_disposition(exception_class),
    )


def select_exception_cohort(
    decision_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Select RNA rows whose primary S3 reason is an alphabet reject."""
    selected = [
        dict(row)
        for row in decision_rows
        if (row.get("primary_reason") or "") in PRIMARY_REASONS
    ]
    if len(selected) != EXPECTED_EXCEPTION_ROWS:
        raise AlphabetExceptionError(
            f"Expected {EXPECTED_EXCEPTION_ROWS} alphabet exceptions, "
            f"found {len(selected)}"
        )
    ambiguous = sum(1 for row in selected if row.get("primary_reason") == "ambiguous_bases")
    invalid = sum(1 for row in selected if row.get("primary_reason") == "invalid_alphabet")
    if ambiguous != EXPECTED_AMBIGUOUS or invalid != EXPECTED_INVALID:
        raise AlphabetExceptionError(
            "Alphabet-exception reason split drifted: "
            f"ambiguous_bases={ambiguous} invalid_alphabet={invalid}"
        )
    non_rna = [row.get("record_id", "") for row in selected if row.get("molecule_type") != "RNA"]
    if non_rna:
        raise AlphabetExceptionError(
            "Alphabet-exception cohort contains non-RNA molecule_type: "
            + ",".join(sorted(non_rna)[:8])
        )
    selected.sort(key=lambda row: row.get("record_id") or "")
    return selected


def build_review_row(
    *,
    decision: Mapping[str, str],
    detail: Mapping[str, str],
    metadata: Mapping[str, str],
    canonical: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Assemble one sequence-bearing exception-review row."""
    canonical = canonical or {}
    sequence_raw = detail.get("sequence_raw") or canonical.get("sequence_raw") or ""
    sequence_full = detail.get("sequence_full") or canonical.get("sequence_full") or ""
    sequence_core = detail.get("sequence_core") or canonical.get("sequence_core") or ""
    diagnostic = diagnose_sequence(sequence_full=sequence_full, sequence_raw=sequence_raw)
    classification = classify_exception(
        sequence_raw=sequence_raw,
        sequence_full=sequence_full,
        diagnostic=diagnostic,
        post_selex=metadata.get("utexas_post_selex_modifications", ""),
        additional=metadata.get("utexas_additional_information", ""),
        chemistry=decision.get("chemistry") or detail.get("chemistry") or "",
        source_type=metadata.get("utexas_type_of_nucleic_acid", ""),
    )
    recovered = classification.proposed_underlying_rna_sequence
    recovered_len = str(len(recovered)) if recovered else ""
    passes_length = ""
    if recovered:
        passes_length = _yes_no(20 <= len(recovered) <= 100)
    return {
        "record_id": decision.get("record_id") or "",
        "native_id": decision.get("native_id") or "",
        "name_of_aptamer": (
            detail.get("aptamer_name")
            or metadata.get("utexas_name_of_aptamer")
            or ""
        ),
        "source_type_of_nucleic_acid": metadata.get("utexas_type_of_nucleic_acid", ""),
        "molecule_type": decision.get("molecule_type") or "",
        "chemistry": decision.get("chemistry") or "",
        "sequence_raw": sequence_raw,
        "sequence_full": sequence_full,
        "sequence_core": sequence_core,
        "alphabet_as_reported": decision.get("alphabet_as_reported") or "",
        "qc_flags": decision.get("qc_flags") or "",
        "proposed_decision": decision.get("proposed_decision") or "",
        "primary_reason": decision.get("primary_reason") or "",
        "post_selex_modifications": metadata.get("utexas_post_selex_modifications", ""),
        "additional_information": metadata.get("utexas_additional_information", ""),
        "source_sequence_length": metadata.get("utexas_sequence_length", ""),
        "source_gc_content": metadata.get("utexas_gc_content", ""),
        "publication": detail.get("publication") or canonical.get("publication") or "",
        "doi": canonical.get("doi") or metadata.get("utexas_journal_doi") or "",
        "pubmed_id": canonical.get("pubmed_id") or "",
        "pubmed_link": metadata.get("utexas_link_to_pubmed_entry", ""),
        "target_name_raw": decision.get("target_name_raw") or "",
        "pool_type": metadata.get("utexas_pool_type", ""),
        "pool_random_region": metadata.get("utexas_pool_random_region", ""),
        "utexas_application_as_quoted": metadata.get("utexas_application_as_quoted", ""),
        "utexas_serial_number": metadata.get("utexas_serial_number", ""),
        "unexpected_characters": _pipe(diagnostic.unexpected_characters),
        "unexpected_tokens": _pipe(diagnostic.unexpected_tokens),
        "contains_iupac_ambiguity": _yes_no(diagnostic.contains_iupac_ambiguity),
        "contains_bracketed_modification": _yes_no(
            diagnostic.contains_bracketed_modification
        ),
        "contains_parenthetical_modification": _yes_no(
            diagnostic.contains_parenthetical_modification
        ),
        "contains_digit_annotation": _yes_no(diagnostic.contains_digit_annotation),
        "contains_star_or_linkage_marker": _yes_no(
            diagnostic.contains_star_or_linkage_marker
        ),
        "contains_nonstandard_base_symbol": _yes_no(
            diagnostic.contains_nonstandard_base_symbol
        ),
        "contains_internal_separator": _yes_no(diagnostic.contains_internal_separator),
        "contains_other_notation": _yes_no(diagnostic.contains_other_notation),
        "contains_cyrillic_lookalike": _yes_no(diagnostic.contains_cyrillic_lookalike),
        "contains_concatenated_entries": _yes_no(
            diagnostic.contains_concatenated_entries
        ),
        "unexpected_token_positions": diagnostic.unexpected_token_positions,
        "exception_class": classification.exception_class,
        "proposed_underlying_rna_sequence": recovered,
        "recovery_transformations": _pipe(classification.recovery_transformations),
        "recovery_confidence": classification.recovery_confidence,
        "recovered_sequence_length": recovered_len,
        "recovered_passes_length_policy": passes_length,
        "modification_metadata_supports_interpretation": (
            classification.modification_metadata_supports_interpretation
        ),
        "modification_metadata_reason": classification.modification_metadata_reason,
        "suggested_review_action": classification.suggested_review_action,
        "suggested_later_disposition": classification.suggested_later_disposition,
        "review_action": "",
        "reviewer_note": "",
        "reviewer_initials": "",
    }


def _count_by(rows: Sequence[Mapping[str, str]], field: str) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter((row.get(field) or "(empty)") for row in rows)
    return sorted(counter.items())


def _count_yes(rows: Sequence[Mapping[str, str]], field: str) -> int:
    return sum(1 for row in rows if row.get(field) == YES)


def build_exception_summary(
    rows: Sequence[Mapping[str, str]],
    *,
    raw_sha_before: str,
    raw_sha_after: str,
    s2_hash_before: str,
    s2_hash_after: str,
    s3_hash_before: str,
    s3_hash_after: str,
    checkpoint_actions_populated: int,
    deterministic_rerun_ok: bool | None = None,
) -> str:
    """Sequence-safe summary for Laura/ChatGPT. Never includes aptamer sequences."""
    if len(rows) != EXPECTED_EXCEPTION_ROWS:
        raise AlphabetExceptionError(
            f"Summary expected {EXPECTED_EXCEPTION_ROWS} rows, found {len(rows)}"
        )
    class_counts = dict(_count_by(rows, "exception_class"))
    reason_counts = dict(_count_by(rows, "primary_reason"))
    high_conf = sum(1 for row in rows if row.get("recovery_confidence") == "high")
    recovered = sum(1 for row in rows if row.get("proposed_underlying_rna_sequence"))
    recovered_length_fail = sum(
        1 for row in rows if row.get("recovered_passes_length_policy") == NO
    )
    would_reject = sum(
        1
        for row in rows
        if row.get("suggested_later_disposition") == "reject"
    )
    would_park = sum(
        1
        for row in rows
        if row.get("suggested_later_disposition") == "park"
    )
    would_review = sum(
        1
        for row in rows
        if row.get("suggested_later_disposition") == "source_review"
    )
    would_recover = sum(
        1
        for row in rows
        if row.get("suggested_later_disposition") == "recover"
    )
    metadata_yes = sum(
        1
        for row in rows
        if row.get("modification_metadata_supports_interpretation") == YES
    )
    review_filled = sum(1 for row in rows if (row.get("review_action") or "").strip())

    def _md_counts(pairs: Sequence[tuple[str, int]]) -> list[str]:
        return [f"- `{key}`: `{value}`" for key, value in pairs]

    lines = [
        "# UTexas alphabet exception review",
        "",
        "Proposed scientific review of source-reported RNA records currently",
        "rejected at S3 for `ambiguous_bases` or `invalid_alphabet`.",
        "Classifications are **proposals only**. Canonical sequences and",
        "CHECKPOINT-1 decisions were not changed.",
        "",
        "## Cohort",
        "",
        f"- total exceptions = `{len(rows)}`",
        f"- `ambiguous_bases` = `{reason_counts.get('ambiguous_bases', 0)}`",
        f"- `invalid_alphabet` = `{reason_counts.get('invalid_alphabet', 0)}`",
        "- `molecule_type` for every selected row = `RNA`",
        "",
        "## Proposed exception classifications",
        "",
        f"- `recoverable_modification_notation` = `{class_counts.get(CLASS_RECOVERABLE, 0)}`",
        f"- `true_iupac_degenerate_sequence` = `{class_counts.get(CLASS_IUPAC, 0)}`",
        f"- `modified_rna_underlying_sequence_unresolved` = `{class_counts.get(CLASS_UNRESOLVED_MOD, 0)}`",
        f"- `malformed_or_unrecoverable` = `{class_counts.get(CLASS_MALFORMED, 0)}`",
        f"- `needs_manual_source_review` = `{class_counts.get(CLASS_NEEDS_REVIEW, 0)}`",
        "",
        "## Source chemistry distribution",
        "",
        *_md_counts(_count_by(rows, "chemistry")),
        "",
        "### Source Type of Nucleic Acid",
        "",
        *_md_counts(_count_by(rows, "source_type_of_nucleic_acid")),
        "",
        "## Unexpected character/token categories",
        "",
        f"- contains IUPAC ambiguity: `{_count_yes(rows, 'contains_iupac_ambiguity')}`",
        f"- contains parenthetical modification: `{_count_yes(rows, 'contains_parenthetical_modification')}`",
        f"- contains bracketed modification: `{_count_yes(rows, 'contains_bracketed_modification')}`",
        f"- contains digit annotation: `{_count_yes(rows, 'contains_digit_annotation')}`",
        f"- contains star or linkage marker: `{_count_yes(rows, 'contains_star_or_linkage_marker')}`",
        f"- contains nonstandard base symbol: `{_count_yes(rows, 'contains_nonstandard_base_symbol')}`",
        f"- contains internal separator: `{_count_yes(rows, 'contains_internal_separator')}`",
        f"- contains other notation: `{_count_yes(rows, 'contains_other_notation')}`",
        f"- contains Cyrillic lookalike characters: `{_count_yes(rows, 'contains_cyrillic_lookalike')}`",
        f"- contains concatenated entries: `{_count_yes(rows, 'contains_concatenated_entries')}`",
        "",
        "## Source-metadata agreement",
        "",
        f"- `modification_metadata_supports_interpretation = yes`: `{metadata_yes}`",
        f"- `unclear`: `{sum(1 for row in rows if row.get('modification_metadata_supports_interpretation') == UNCLEAR)}`",
        f"- `no`: `{sum(1 for row in rows if row.get('modification_metadata_supports_interpretation') == NO)}`",
        "",
        "## Proposed recoveries and later dispositions",
        "",
        f"- high-confidence recoverable underlying RNA sequences = `{high_conf}`",
        f"- recovered A/C/G/U strings emitted = `{recovered}`",
        f"- recovered strings still outside 20–100 nt = `{recovered_length_fail}`",
        f"- would later `accept_recovered_sequence` (alphabet only) = `{would_recover}`",
        f"- proposed reject cases = `{would_reject}`",
        f"- proposed park cases = `{would_park}`",
        f"- needs source-paper review = `{would_review}`",
        "",
        "Length policy is **not** applied by this exception review. "
        f"`{recovered_length_fail}` alphabet-recoverable records are still "
        "outside 20–100 nt.",
        "",
        "## Suggested reviewer actions (blank until human review)",
        "",
        *_md_counts(_count_by(rows, "suggested_review_action")),
        f"- populated `review_action` cells in this package = `{review_filled}`",
        "",
        "## Integrity",
        "",
        f"- Raw workbook SHA-256 before: `{raw_sha_before}`",
        f"- Raw workbook SHA-256 after: `{raw_sha_after}`",
        f"- S2 canonical hash before: `{s2_hash_before}`",
        f"- S2 canonical hash after: `{s2_hash_after}`",
        f"- S3 canonical hash before: `{s3_hash_before}`",
        f"- S3 canonical hash after: `{s3_hash_after}`",
        f"- CHECKPOINT-1 populated review actions: `{checkpoint_actions_populated}`",
        f"- Canonical sequences changed: `no`",
        f"- CHECKPOINT-1 actions applied: `no`",
        f"- CHECKPOINT-1 closed: `no`",
        f"- S4 started: `no`",
        (
            f"- Deterministic rerun: `{'pass' if deterministic_rerun_ok else 'fail'}`"
            if deterministic_rerun_ok is not None
            else "- Deterministic rerun: `not_checked`"
        ),
        "",
        "## Outputs",
        "",
        "- `data/interim/checkpoints/utexas_cp1/exceptions/utexas_alphabet_exception_review.csv`",
        "- `data/interim/checkpoints/utexas_cp1/exceptions/utexas_alphabet_exception_summary.md`",
        "",
        "WARNING: the review CSV contains source sequences. It must remain",
        "beneath ignored `data/` and must never be staged or tracked.",
        "",
        "## Pipeline stop",
        "",
        "Alphabet-exception review package generated.",
        "No canonical sequence was changed.",
        "No CHECKPOINT-1 decision was applied.",
        "CHECKPOINT-1 remains open.",
        "Global S4 has not started.",
        "",
    ]
    return "\n".join(lines)


def assert_reviewed_package_counts(rows: Sequence[Mapping[str, str]]) -> None:
    """Hard-fail if the 31-row reviewed exception package has drifted."""
    if len(rows) != EXPECTED_EXCEPTION_ROWS:
        raise AlphabetExceptionError(
            f"Expected {EXPECTED_EXCEPTION_ROWS} exception rows, found {len(rows)}"
        )
    class_counts = Counter((row.get("exception_class") or "") for row in rows)
    for key, expected in EXPECTED_CLASS_COUNTS.items():
        got = class_counts.get(key, 0)
        if got != expected:
            raise AlphabetExceptionError(
                f"exception_class {key} expected {expected}; got {got}"
            )
    non_rna = [
        row.get("record_id") or ""
        for row in rows
        if (row.get("molecule_type") or "") != "RNA"
    ]
    if non_rna:
        raise AlphabetExceptionError(
            "Alphabet-exception package contains non-RNA molecule_type"
        )
    recoverable = [
        row for row in rows if row.get("exception_class") == CLASS_RECOVERABLE
    ]
    if len(recoverable) != EXPECTED_CLASS_COUNTS[CLASS_RECOVERABLE]:
        raise AlphabetExceptionError("Recoverable cohort count drifted")
    for row in recoverable:
        if (row.get("recovery_confidence") or "") != "high":
            raise AlphabetExceptionError(
                "Recoverable exception missing high recovery_confidence"
            )
        if not (row.get("proposed_underlying_rna_sequence") or "").strip():
            raise AlphabetExceptionError(
                "Recoverable exception missing proposed_underlying_rna_sequence"
            )
    in_range = sum(
        1 for row in recoverable if row.get("recovered_passes_length_policy") == YES
    )
    out_range = sum(
        1 for row in recoverable if row.get("recovered_passes_length_policy") == NO
    )
    if in_range != 7 or out_range != 10:
        raise AlphabetExceptionError(
            "Recovered length split drifted: "
            f"in_20_100={in_range} outside={out_range}"
        )


def apply_human_exception_decisions(
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Populate CHECKPOINT-1 alphabet-exception review_action cells."""
    assert_reviewed_package_counts(rows)
    updated: list[dict[str, str]] = []
    for row in rows:
        exception_class = row.get("exception_class") or ""
        if exception_class not in CLASS_TO_HUMAN_ACTION:
            raise AlphabetExceptionError(
                f"No human action mapping for exception_class={exception_class}"
            )
        out = dict(row)
        out["review_action"] = CLASS_TO_HUMAN_ACTION[exception_class]
        out["reviewer_note"] = CLASS_TO_HUMAN_REASON[exception_class]
        out["reviewer_initials"] = ""
        updated.append(out)

    action_counts = Counter((row.get("review_action") or "") for row in updated)
    for key, expected in EXPECTED_DECISION_COUNTS.items():
        got = action_counts.get(key, 0)
        if got != expected:
            raise AlphabetExceptionError(
                f"review_action {key or 'blank'} expected {expected}; got {got}"
            )
    if sum(action_counts.values()) != EXPECTED_EXCEPTION_ROWS:
        raise AlphabetExceptionError("Decision counts do not cover all 31 rows")
    return updated


def build_tracked_resolution_rows(
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Build sequence-safe tracked resolution rows from decided exception rows."""
    if any(not (row.get("review_action") or "").strip() for row in rows):
        raise AlphabetExceptionError("Cannot emit resolutions with blank review_action")
    tracked: list[dict[str, str]] = []
    for row in sorted(rows, key=lambda item: item.get("record_id") or ""):
        action = row.get("review_action") or ""
        profile = ""
        expected_length = ""
        if action == SUGGESTED_ACCEPT_RECOVERED:
            profile = row.get("recovery_transformations") or ""
            expected_length = row.get("recovered_sequence_length") or ""
            if not profile or not expected_length:
                raise AlphabetExceptionError(
                    "Approved recovery missing transformation profile or length"
                )
        tracked.append(
            {
                "record_id": row.get("record_id") or "",
                "decision": action,
                "transformation_profile": profile,
                "expected_recovered_length": expected_length,
                "review_note": row.get("reviewer_note") or "",
            }
        )
    ids = [row["record_id"] for row in tracked]
    if len(set(ids)) != len(ids):
        raise AlphabetExceptionError("Duplicate record_id in alphabet resolutions")
    if any(not record_id for record_id in ids):
        raise AlphabetExceptionError("Blank record_id in alphabet resolutions")
    return tracked


def load_alphabet_exception_resolutions(
    path: str | Path,
) -> dict[str, AlphabetResolution]:
    """Load the tracked sequence-safe alphabet-exception resolution table."""
    resolution_path = Path(path)
    if not resolution_path.is_file():
        raise AlphabetExceptionError(
            f"Missing alphabet-exception resolutions: {resolution_path.name}"
        )
    with resolution_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != EXPECTED_EXCEPTION_ROWS:
        raise AlphabetExceptionError(
            f"Expected {EXPECTED_EXCEPTION_ROWS} resolution rows, found {len(rows)}"
        )
    loaded: dict[str, AlphabetResolution] = {}
    for row in rows:
        record_id = (row.get("record_id") or "").strip()
        decision = (row.get("decision") or "").strip()
        if not record_id:
            raise AlphabetExceptionError("Alphabet resolution row missing record_id")
        if record_id in loaded:
            raise AlphabetExceptionError("Duplicate alphabet resolution record_id")
        if decision not in ALLOWED_REVIEW_ACTIONS or not decision:
            raise AlphabetExceptionError(
                f"Unknown alphabet resolution decision={decision!r}"
            )
        length_raw = (row.get("expected_recovered_length") or "").strip()
        expected_length: int | None = None
        if length_raw:
            try:
                expected_length = int(length_raw)
            except ValueError as exc:
                raise AlphabetExceptionError(
                    "expected_recovered_length must be an integer"
                ) from exc
        if decision == SUGGESTED_ACCEPT_RECOVERED:
            if not (row.get("transformation_profile") or "").strip():
                raise AlphabetExceptionError(
                    "Approved recovery missing transformation_profile"
                )
            if expected_length is None:
                raise AlphabetExceptionError(
                    "Approved recovery missing expected_recovered_length"
                )
        elif (row.get("transformation_profile") or "").strip() or expected_length is not None:
            raise AlphabetExceptionError(
                "Non-recovery resolution must not carry recovery fields"
            )
        loaded[record_id] = AlphabetResolution(
            record_id=record_id,
            decision=decision,
            transformation_profile=row.get("transformation_profile") or "",
            expected_recovered_length=expected_length,
            review_note=row.get("review_note") or "",
        )
    action_counts = Counter(item.decision for item in loaded.values())
    for key, expected in EXPECTED_DECISION_COUNTS.items():
        if not key:
            continue
        got = action_counts.get(key, 0)
        if got != expected:
            raise AlphabetExceptionError(
                f"Tracked decision {key} expected {expected}; got {got}"
            )
    return loaded


def approved_recovery_ids(
    resolutions: Mapping[str, AlphabetResolution],
) -> frozenset[str]:
    """Return the record IDs approved for deterministic alphabet recovery."""
    return frozenset(
        record_id
        for record_id, item in resolutions.items()
        if item.decision == SUGGESTED_ACCEPT_RECOVERED
    )


def apply_approved_recovery(
    sequence_raw: str,
    resolution: AlphabetResolution,
) -> RecoveryResult:
    """Apply a reviewed recovery; never invent a sequence for other decisions."""
    if resolution.decision != SUGGESTED_ACCEPT_RECOVERED:
        raise AlphabetExceptionError(
            "Alphabet recovery requested for a non-approved record"
        )
    recovery = attempt_recovery(sequence_raw)
    if recovery.confidence != "high" or not recovery.sequence:
        raise AlphabetExceptionError("Approved alphabet recovery failed")
    if resolution.expected_recovered_length is not None and (
        len(recovery.sequence) != resolution.expected_recovered_length
    ):
        raise AlphabetExceptionError(
            "Approved recovery length does not match the reviewed expectation"
        )
    actual_profile = "|".join(recovery.transformations)
    if (
        resolution.transformation_profile
        and actual_profile != resolution.transformation_profile
    ):
        raise AlphabetExceptionError(
            "Approved recovery transformation profile does not match review"
        )
    return recovery


def park_override_ids(
    resolutions: Mapping[str, AlphabetResolution],
) -> frozenset[str]:
    return frozenset(
        record_id
        for record_id, item in resolutions.items()
        if item.decision == SUGGESTED_OVERRIDE_PARK
    )


def reject_confirm_ids(
    resolutions: Mapping[str, AlphabetResolution],
) -> frozenset[str]:
    return frozenset(
        record_id
        for record_id, item in resolutions.items()
        if item.decision == SUGGESTED_CONFIRM_REJECT
    )

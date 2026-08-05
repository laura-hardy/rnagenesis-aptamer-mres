"""Leakage-specific sequence comparison helpers (not the general S2 normaliser).

These utilities support evaluation-reference leakage exclusion: display cleanup,
DNA/RNA T↔U comparison equivalence, and global edit identity at the 0.90
threshold used later during corpus merge. They must not trim promoters/primers,
must not convert genuine ssDNA into RNA, and must never print sequences.
"""

from __future__ import annotations

import re
from typing import Final

IDENTITY_THRESHOLD: Final[float] = 0.90

_WHITESPACE_RE = re.compile(r"\s+")
_TERMINAL_MARK_RE = re.compile(
    r"(?:^\s*(?:5[′']|5'|5′)\s*[-–—:]?\s*)|(?:\s*[-–—:]?\s*(?:3[′']|3'|3′)\s*$)",
    re.IGNORECASE,
)
_GAP_RE = re.compile(r"[-.]+")
_SIMPLE_NT_RE = re.compile(r"^[ACGTU]+$", re.IGNORECASE)


class LeakageMatchingError(ValueError):
    """Invalid sequence comparison or cleanup input (never embeds sequences)."""


def remove_display_artifacts(sequence: str) -> str:
    """Remove display-only whitespace, terminal 5′/3′ marks, and alignment gaps.

    Gap characters (``-``, ``.``) are treated as table/alignment padding only.
    No promoter or primer trimming is performed.
    """
    if sequence is None:
        raise LeakageMatchingError("sequence is missing")
    text = str(sequence)
    text = _TERMINAL_MARK_RE.sub("", text)
    text = _WHITESPACE_RE.sub("", text)
    text = _GAP_RE.sub("", text)
    return text


def is_simple_nucleotide_string(sequence: str) -> bool:
    """Return True if ``sequence`` contains only A/C/G/T/U (case-insensitive)."""
    if not sequence:
        return False
    return bool(_SIMPLE_NT_RE.fullmatch(sequence))


def validate_simple_nucleotide_string(sequence: str, *, context: str = "sequence") -> str:
    """Validate a cleaned A/C/G/T/U string; raise without echoing the sequence."""
    if not sequence:
        raise LeakageMatchingError(f"{context} is empty after display cleanup")
    if not is_simple_nucleotide_string(sequence):
        raise LeakageMatchingError(
            f"{context} contains characters outside A/C/G/T/U after display cleanup"
        )
    return sequence


def rna_form_from_dna_alphabet(sequence: str, *, molecule_type: str) -> str:
    """Derive the RNA alphabet form of an experimentally RNA record printed with T.

    Conversion is applied only when ``molecule_type`` indicates RNA. Genuine
    ssDNA/DNA records are rejected if callers request RNA conversion.
    """
    cleaned = validate_simple_nucleotide_string(
        remove_display_artifacts(sequence), context="rna_form input"
    )
    mol = (molecule_type or "").strip().upper()
    if mol not in {"RNA", "RRNA", "TRNA", "MRNA"} and "RNA" not in mol:
        raise LeakageMatchingError(
            "refusing T→U conversion for non-RNA molecule_type"
        )
    # Experimental RNA printed with DNA alphabet: T→U; existing U retained.
    return cleaned.upper().replace("T", "U")


def comparison_form(sequence: str) -> str:
    """Collapse U→T for DNA/RNA-equivalent leakage comparison."""
    cleaned = validate_simple_nucleotide_string(
        remove_display_artifacts(sequence), context="comparison_form input"
    )
    return cleaned.upper().replace("U", "T")


def edit_distance(a: str, b: str) -> int:
    """Deterministic global Levenshtein edit distance (insert/delete/substitute)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Ensure b is the shorter sequence for memory locality.
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            ins = current[j - 1] + 1
            delete = previous[j] + 1
            sub = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(ins, delete, sub))
        previous = current
    return previous[-1]


def global_edit_identity(a: str, b: str) -> float:
    """Return ``1 - edit_distance / max(len_a, len_b)``.

    Empty strings are never compared. Inputs should already be comparison forms
    (or any comparable alphabet); this function does not print sequences.
    """
    if a is None or b is None:
        raise LeakageMatchingError("cannot compare missing sequences")
    if a == "" or b == "":
        raise LeakageMatchingError("cannot compare empty sequences")
    denom = max(len(a), len(b))
    if denom == 0:
        raise LeakageMatchingError("cannot compare empty sequences")
    return 1.0 - (edit_distance(a, b) / denom)


def meets_identity_threshold(
    a: str, b: str, *, threshold: float = IDENTITY_THRESHOLD
) -> bool:
    """True when global edit identity is greater than or equal to ``threshold``."""
    return global_edit_identity(a, b) >= threshold


def prepare_molecule_native_sequence(
    sequence_raw: str,
    *,
    molecule_type: str,
    alphabet_as_reported: str,
) -> tuple[str, bool]:
    """Return ``(sequence_full, t_to_u_applied)`` in the molecule-native alphabet.

    RNA records reported with a DNA/T alphabet are converted T→U.
    ssDNA/DNA records retain T and never receive T→U conversion.
    """
    cleaned = validate_simple_nucleotide_string(
        remove_display_artifacts(sequence_raw), context="molecule-native sequence"
    )
    mol = (molecule_type or "").strip().upper()
    alphabet = (alphabet_as_reported or "").strip().upper()
    is_rna = mol == "RNA" or (mol.startswith("RNA") and "DNA" not in mol)
    reported_with_t = alphabet in {"DNA", "DNA_T", "T", "DNA-T"} or (
        "DNA" in alphabet and "U" not in alphabet
    )

    if is_rna and reported_with_t:
        return cleaned.upper().replace("T", "U"), True
    if is_rna:
        # Already RNA alphabet (may contain U); normalise case only.
        return cleaned.upper().replace("T", "U"), cleaned.upper().find("T") >= 0
    # Genuine DNA / ssDNA: retain T; never convert to RNA.
    return cleaned.upper().replace("U", "T"), False

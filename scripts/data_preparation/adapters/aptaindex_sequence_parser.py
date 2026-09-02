"""AptaIndex chemical-notation parser (S2, source-specific).

Deterministic full-consumption tokenisation of AptaIndex Sequence values.
Does not decide eligibility, inclusion, parking, or chemistry policy.
Unknown or incomplete syntax fails closed: no partial nucleotide sequence
is returned as success.

This module must not log or embed restricted AptaIndex sequences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

STATUS_MISSING: Final[str] = "missing"
STATUS_NOT_APPLICABLE_PEPTIDE: Final[str] = "not_applicable_peptide"
STATUS_SUCCESS: Final[str] = "success"
STATUS_UNSUPPORTED: Final[str] = "unsupported"

PEPTIDE_SOURCE_TYPE: Final[str] = "Peptide"

# Explicitly supported nucleotide-token grammar (case-sensitive as observed).
TOKEN_PREFIXES: Final[frozenset[str]] = frozenset({"d", "r", "m", "f", "n"})
TOKEN_BASES: Final[frozenset[str]] = frozenset({"A", "C", "G", "T", "U", "I"})
LINKAGE_MARKERS: Final[frozenset[str]] = frozenset({"p", "s"})

# Terminal quote/prime characters actually observed in this export.
TERMINAL_QUOTES: Final[str] = "'\u2019\u2032"  # ASCII apostrophe, rsquo, prime
_QUOTE_CLASS: Final[str] = re.escape(TERMINAL_QUOTES)

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"L?[drmfn][ACGTUI]")
_START_5_QUOTE_RE: Final[re.Pattern[str]] = re.compile(
    rf"^5[{_QUOTE_CLASS}]\s*[-–—:]?\s*"
)
_START_QUOTE_5_RE: Final[re.Pattern[str]] = re.compile(
    rf"^[{_QUOTE_CLASS}]5\s*[-–—:]?\s*"
)
_END_3_QUOTE_RE: Final[re.Pattern[str]] = re.compile(
    rf"\s*[-–—:]?\s*3[{_QUOTE_CLASS}]$"
)
_END_QUOTE_3_RE: Final[re.Pattern[str]] = re.compile(
    rf"\s*[-–—:]?\s*[{_QUOTE_CLASS}]3$"
)
# Reverse-orientation markers: recognised only so they can fail closed.
_START_3_QUOTE_RE: Final[re.Pattern[str]] = re.compile(
    rf"^3[{_QUOTE_CLASS}]\s*[-–—:]?\s*"
)
_START_QUOTE_3_RE: Final[re.Pattern[str]] = re.compile(
    rf"^[{_QUOTE_CLASS}]3\s*[-–—:]?\s*"
)
_END_5_QUOTE_RE: Final[re.Pattern[str]] = re.compile(
    rf"\s*[-–—:]?\s*5[{_QUOTE_CLASS}]$"
)
_END_QUOTE_5_RE: Final[re.Pattern[str]] = re.compile(
    rf"\s*[-–—:]?\s*[{_QUOTE_CLASS}]5$"
)

REASON_MISSING: Final[str] = "missing_sequence"
REASON_PEPTIDE: Final[str] = "source_declared_peptide"
REASON_SUCCESS: Final[str] = "full_consumption"
REASON_SWAPPED_ORIENTATION: Final[str] = "swapped_terminal_orientation"
REASON_BRACE_LABEL: Final[str] = "brace_label"
REASON_SLASH: Final[str] = "slash_decoration"
REASON_THIOL: Final[str] = "thiol_decoration"
REASON_SPACER: Final[str] = "spacer"
REASON_UNKNOWN_TOKEN: Final[str] = "unknown_token"
REASON_IUPAC_N: Final[str] = "iupac_n"
REASON_BARE_MODIFICATION: Final[str] = "bare_modification"
REASON_OMITTED_PREFIX: Final[str] = "omitted_chemistry_prefix"
REASON_UNCONSUMED_SUFFIX: Final[str] = "unconsumed_suffix"
REASON_UNPREFIXED: Final[str] = "unprefixed_nucleotides"
REASON_UNSUPPORTED: Final[str] = "unsupported_notation"


class AptaIndexParserError(ValueError):
    """Invalid parser invocation (never embeds sequence text)."""


@dataclass(frozen=True)
class AptaIndexParseResult:
    """Structured result of one AptaIndex Sequence parse.

    ``base_string`` is nonempty only on ``STATUS_SUCCESS``. Failed parses
    never return a partial nucleotide sequence.
    """

    status: str
    reason_category: str
    base_string: str = ""
    token_family_summary: str = ""
    token_prefixes: tuple[str, ...] = ()
    has_l_prefix: bool = False
    linkage_summary: str = ""
    internucleotide_linkages: tuple[str, ...] = ()
    has_terminal_phosphate: bool = False
    terminal_phosphate_marker: str = ""
    terminal_form: str = ""
    has_t: bool = False
    has_u: bool = False
    has_i: bool = False
    mixed_t_u: bool = False
    n_tokens: int = 0
    whitespace_skipped: bool = False
    unconsumed_class: str = ""


def _empty_result(*, status: str, reason_category: str, unconsumed_class: str = "") -> AptaIndexParseResult:
    return AptaIndexParseResult(
        status=status,
        reason_category=reason_category,
        unconsumed_class=unconsumed_class,
    )


def _classify_unconsumed(leftover: str) -> tuple[str, str]:
    """Map leftover text to a closed reason category. Never returns the text."""
    text = leftover.lstrip()
    if not text:
        return REASON_UNSUPPORTED, "empty_leftover"
    if text[0] in "{}":
        return REASON_BRACE_LABEL, "brace_label"
    if text[0] == "/":
        return REASON_SLASH, "slash_decoration"
    if text.startswith("SH"):
        return REASON_THIOL, "thiol_decoration"
    if text.startswith("Dsp"):
        return REASON_SPACER, "spacer"
    if text.startswith("Xlk"):
        return REASON_UNKNOWN_TOKEN, "unknown_token"
    if text.startswith("bTn") or text.startswith("b"):
        return REASON_UNKNOWN_TOKEN, "unknown_token"
    if text[0] == "N":
        return REASON_IUPAC_N, "iupac_n"
    if text[0] == "i":
        return REASON_BARE_MODIFICATION, "bare_modification"
    if text[0] in "ACGTU":
        return REASON_UNPREFIXED, "unprefixed_nucleotides"
    if text[0] in "-–—":
        return REASON_UNSUPPORTED, "internal_hyphen"
    return REASON_UNSUPPORTED, "unsupported_notation"


def _strip_supported_terminals(text: str) -> tuple[str, str, str] | AptaIndexParseResult:
    """Strip 5′ start / 3′ end markers. Reverse orientation fails closed."""
    start_form = "none"
    end_form = "none"
    inner = text

    if _START_3_QUOTE_RE.match(inner) or _START_QUOTE_3_RE.match(inner):
        return _empty_result(
            status=STATUS_UNSUPPORTED,
            reason_category=REASON_SWAPPED_ORIENTATION,
            unconsumed_class="swapped_terminal_orientation",
        )

    match = _START_5_QUOTE_RE.match(inner)
    if match:
        inner = inner[match.end() :]
        start_form = "5_quote"
    else:
        match = _START_QUOTE_5_RE.match(inner)
        if match:
            inner = inner[match.end() :]
            start_form = "quote_5"

    if _END_5_QUOTE_RE.search(inner) or _END_QUOTE_5_RE.search(inner):
        return _empty_result(
            status=STATUS_UNSUPPORTED,
            reason_category=REASON_SWAPPED_ORIENTATION,
            unconsumed_class="swapped_terminal_orientation",
        )

    match = _END_3_QUOTE_RE.search(inner)
    if match:
        inner = inner[: match.start()]
        end_form = "3_quote"
    else:
        match = _END_QUOTE_3_RE.search(inner)
        if match:
            inner = inner[: match.start()]
            end_form = "quote_3"

    return inner, start_form, end_form


def parse_chemical_notation(sequence: str | None) -> AptaIndexParseResult:
    """Parse one AptaIndex chemical-notation string.

    Success requires that every character is accounted for by explicitly
    supported terminal, token, linkage, optional terminal-phosphate, or
    token-separating whitespace syntax.
    """
    if sequence is None:
        return _empty_result(status=STATUS_MISSING, reason_category=REASON_MISSING)

    original = str(sequence)
    stripped = original.strip()
    if stripped == "":
        return _empty_result(status=STATUS_MISSING, reason_category=REASON_MISSING)

    terminal = _strip_supported_terminals(stripped)
    if isinstance(terminal, AptaIndexParseResult):
        return terminal
    inner, start_form, end_form = terminal
    if start_form == "none" and end_form == "none":
        terminal_form = "none"
    else:
        terminal_form = f"{start_form}+{end_form}"

    whitespace_skipped = original != stripped or any(ch.isspace() for ch in inner)

    tokens: list[str] = []
    linkages: list[str] = []
    terminal_phosphate = ""
    i = 0
    n = len(inner)

    def _skip_ws(pos: int) -> int:
        while pos < n and inner[pos].isspace():
            pos += 1
        return pos

    i = _skip_ws(i)
    if i >= n:
        return _empty_result(
            status=STATUS_UNSUPPORTED,
            reason_category=REASON_UNSUPPORTED,
            unconsumed_class="empty_after_terminals",
        )

    while i < n:
        i = _skip_ws(i)
        if i >= n:
            break

        token_match = _TOKEN_RE.match(inner, i)
        if token_match:
            if terminal_phosphate:
                return _empty_result(
                    status=STATUS_UNSUPPORTED,
                    reason_category=REASON_UNCONSUMED_SUFFIX,
                    unconsumed_class="token_after_terminal_phosphate",
                )
            tokens.append(token_match.group(0))
            i = token_match.end()
            continue

        if inner[i] in LINKAGE_MARKERS:
            marker = inner[i]
            after = _skip_ws(i + 1)
            next_token = _TOKEN_RE.match(inner, after) if after < n else None
            if next_token is not None:
                if not tokens:
                    reason, klass = _classify_unconsumed(inner[i:])
                    return _empty_result(
                        status=STATUS_UNSUPPORTED,
                        reason_category=reason,
                        unconsumed_class=klass,
                    )
                linkages.append(marker)
                i = after
                continue
            if after >= n:
                # Trailing 3′-phosphate / phosphorothioate after the last token.
                if not tokens:
                    reason, klass = _classify_unconsumed(inner[i:])
                    return _empty_result(
                        status=STATUS_UNSUPPORTED,
                        reason_category=reason,
                        unconsumed_class=klass,
                    )
                terminal_phosphate = marker
                i = after
                continue
            # Linkage followed by non-token material: omitted prefix or unknown.
            leftover = inner[after:]
            if leftover and leftover[0] in TOKEN_BASES:
                return _empty_result(
                    status=STATUS_UNSUPPORTED,
                    reason_category=REASON_OMITTED_PREFIX,
                    unconsumed_class="omitted_chemistry_prefix",
                )
            reason, klass = _classify_unconsumed(leftover)
            return _empty_result(
                status=STATUS_UNSUPPORTED,
                reason_category=reason,
                unconsumed_class=klass,
            )

        if tokens:
            reason, klass = _classify_unconsumed(inner[i:])
            if reason == REASON_UNSUPPORTED:
                reason = REASON_UNCONSUMED_SUFFIX
                klass = "unconsumed_suffix"
            return _empty_result(
                status=STATUS_UNSUPPORTED,
                reason_category=reason,
                unconsumed_class=klass,
            )
        reason, klass = _classify_unconsumed(inner[i:])
        return _empty_result(
            status=STATUS_UNSUPPORTED,
            reason_category=reason,
            unconsumed_class=klass,
        )

    if i != n:
        reason, klass = _classify_unconsumed(inner[i:])
        return _empty_result(
            status=STATUS_UNSUPPORTED,
            reason_category=reason,
            unconsumed_class=klass,
        )
    if not tokens:
        return _empty_result(
            status=STATUS_UNSUPPORTED,
            reason_category=REASON_UNSUPPORTED,
            unconsumed_class="no_tokens",
        )

    prefixes: list[str] = []
    has_l = False
    bases: list[str] = []
    for token in tokens:
        body = token
        if body.startswith("L"):
            has_l = True
            body = body[1:]
        prefixes.append(body[0])
        bases.append(body[1])

    family = tuple(sorted(set(prefixes)))
    family_summary = "+".join(family)
    internucleotide = tuple(linkages)
    if internucleotide:
        link_set = tuple(sorted(set(internucleotide)))
        linkage_summary = "+".join(link_set)
    else:
        linkage_summary = "none"

    has_t = "T" in bases
    has_u = "U" in bases
    has_i = "I" in bases
    return AptaIndexParseResult(
        status=STATUS_SUCCESS,
        reason_category=REASON_SUCCESS,
        base_string="".join(bases),
        token_family_summary=family_summary,
        token_prefixes=family,
        has_l_prefix=has_l,
        linkage_summary=linkage_summary,
        internucleotide_linkages=internucleotide,
        has_terminal_phosphate=bool(terminal_phosphate),
        terminal_phosphate_marker=terminal_phosphate,
        terminal_form=terminal_form,
        has_t=has_t,
        has_u=has_u,
        has_i=has_i,
        mixed_t_u=has_t and has_u,
        n_tokens=len(tokens),
        whitespace_skipped=whitespace_skipped,
    )


def parse_aptaindex_source_sequence(
    sequence: str | None,
    *,
    source_type: str = "",
) -> AptaIndexParseResult:
    """Parse one AptaIndex Sequence in the context of source ``Type``.

    Source-declared peptide rows are not fed to the nucleotide parser.
    """
    if (source_type or "") == PEPTIDE_SOURCE_TYPE:
        return _empty_result(
            status=STATUS_NOT_APPLICABLE_PEPTIDE,
            reason_category=REASON_PEPTIDE,
        )
    return parse_chemical_notation(sequence)

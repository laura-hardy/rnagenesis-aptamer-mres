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
from typing import Final, Mapping

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

# Allowlisted 5′ decorations only. Not a generic brace/label stripper.
_FIVE_PRIME_PHOSPHATE_BRACE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\{5'/Phosphate\}-?"
)
_FIVE_PRIME_P_HYPHEN_RE: Final[re.Pattern[str]] = re.compile(r"^P-")
_FIVE_PRIME_THIOL_HEXYL_RE: Final[re.Pattern[str]] = re.compile(r"^SH-\(CH2\)6-")
_DISPLAY_HYPHENS: Final[frozenset[str]] = frozenset({"-", "–", "—"})

# Uniform-family omitted-prefix inheritance is permitted only when the unique
# explicit chemistry prefix is compatible with source Type. Blank Type is
# allowed in unit tests; Chimeric / L-* / unknown Types never inherit.
_INHERIT_COMPATIBLE_PREFIXES: Final[Mapping[str, frozenset[str]]] = {
    "DNA": frozenset({"d"}),
    "RNA": frozenset({"r"}),
    "2'-F-RNA": frozenset({"f"}),
}

SYNTAX_INHERITED_PREFIX: Final[str] = "inherited_token_prefix"
SYNTAX_TERMINAL_PHOSPHATE: Final[str] = "terminal_phosphate_stripped"
SYNTAX_THIOL_CAP: Final[str] = "terminal_thiol_cap_stripped"
SYNTAX_DISPLAY_SEPARATOR: Final[str] = "display_separator_normalised"

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
    syntax_events: tuple[str, ...] = ()
    inherited_token_prefix: str = ""


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


def _strip_allowlisted_five_prime_decorations(
    inner: str,
) -> tuple[str, tuple[str, ...]]:
    """Strip only known 5′ phosphate / thiol-hexyl decorations.

    Arbitrary brace labels, internal spacers, and other SH- chemistry are
    left in place so full-consumption tokenisation fails closed.
    """
    events: list[str] = []
    match = _FIVE_PRIME_PHOSPHATE_BRACE_RE.match(inner)
    if match:
        inner = inner[match.end() :]
        events.append(SYNTAX_TERMINAL_PHOSPHATE)
        return inner, tuple(events)
    match = _FIVE_PRIME_P_HYPHEN_RE.match(inner)
    if match:
        inner = inner[match.end() :]
        events.append(SYNTAX_TERMINAL_PHOSPHATE)
        return inner, tuple(events)
    match = _FIVE_PRIME_THIOL_HEXYL_RE.match(inner)
    if match:
        inner = inner[match.end() :]
        events.append(SYNTAX_THIOL_CAP)
        return inner, tuple(events)
    return inner, ()


def _explicit_token_prefixes(inner: str) -> tuple[frozenset[str], bool]:
    """Return chemistry prefixes of explicit tokens and whether any is L-."""
    prefixes: set[str] = set()
    has_l = False
    for match in _TOKEN_RE.finditer(inner):
        token = match.group(0)
        body = token
        if body.startswith("L"):
            has_l = True
            body = body[1:]
        prefixes.add(body[0])
    return frozenset(prefixes), has_l


def _uniform_inherited_prefix(inner: str, source_type: str) -> str:
    """Return the unique inherit-able prefix, or empty when the rule must not fire.

    Requires a single explicit chemistry prefix, no L tokens, leftover
    material that is only bare bases / linkage / whitespace / display
    hyphens, and source Type that does not contradict that prefix.
    Chemistry is never inferred from Type alone.
    """
    prefixes, has_l = _explicit_token_prefixes(inner)
    if has_l or len(prefixes) != 1:
        return ""
    prefix = next(iter(prefixes))
    if source_type:
        allowed = _INHERIT_COMPATIBLE_PREFIXES.get(source_type)
        if allowed is None or prefix not in allowed:
            return ""
    leftover_ok = True
    pos = 0
    n = len(inner)
    while pos < n:
        token_match = _TOKEN_RE.match(inner, pos)
        if token_match:
            pos = token_match.end()
            continue
        ch = inner[pos]
        if (
            ch.isspace()
            or ch in LINKAGE_MARKERS
            or ch in TOKEN_BASES
            or ch in _DISPLAY_HYPHENS
        ):
            pos += 1
            continue
        leftover_ok = False
        break
    if not leftover_ok:
        return ""
    return prefix


def parse_chemical_notation(
    sequence: str | None,
    *,
    source_type: str = "",
) -> AptaIndexParseResult:
    """Parse one AptaIndex chemical-notation string.

    Success requires that every character is accounted for by explicitly
    supported terminal, token, linkage, optional terminal-phosphate,
    allowlisted 5′ decoration, token-separating whitespace, or the
    tightly guarded omitted-prefix / display-hyphen syntax below.
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

    syntax_events: list[str] = []
    inner, decoration_events = _strip_allowlisted_five_prime_decorations(inner)
    syntax_events.extend(decoration_events)

    whitespace_skipped = original != stripped or any(ch.isspace() for ch in inner)
    inherited_prefix = _uniform_inherited_prefix(inner, source_type)

    tokens: list[str] = []
    linkages: list[str] = []
    terminal_phosphate = ""
    inherited_used = False
    hyphen_skipped = False
    i = 0
    n = len(inner)

    def _skip_ws(pos: int) -> int:
        while pos < n and inner[pos].isspace():
            pos += 1
        return pos

    def _match_token(pos: int) -> re.Match[str] | tuple[str, int] | None:
        token_match = _TOKEN_RE.match(inner, pos)
        if token_match:
            return token_match
        if inherited_prefix and pos < n and inner[pos] in TOKEN_BASES:
            return inherited_prefix + inner[pos], pos + 1
        return None

    def _skip_display_hyphen(pos: int) -> int:
        nonlocal hyphen_skipped
        if not tokens or pos >= n or inner[pos] not in _DISPLAY_HYPHENS:
            return pos
        nxt = _skip_ws(pos + 1)
        if _match_token(nxt) is not None:
            hyphen_skipped = True
            return nxt
        if nxt < n and inner[nxt] in LINKAGE_MARKERS:
            after_link = _skip_ws(nxt + 1)
            if _match_token(after_link) is not None:
                hyphen_skipped = True
                return nxt
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
        i = _skip_display_hyphen(i)
        if i >= n:
            break

        matched = _match_token(i)
        if matched is not None:
            if terminal_phosphate:
                return _empty_result(
                    status=STATUS_UNSUPPORTED,
                    reason_category=REASON_UNCONSUMED_SUFFIX,
                    unconsumed_class="token_after_terminal_phosphate",
                )
            if isinstance(matched, tuple):
                token_text, end = matched
                tokens.append(token_text)
                inherited_used = True
                i = end
            else:
                tokens.append(matched.group(0))
                i = matched.end()
            continue

        if inner[i] in LINKAGE_MARKERS:
            marker = inner[i]
            after = _skip_ws(i + 1)
            after = _skip_display_hyphen(after) if tokens else after
            next_token = _match_token(after) if after < n else None
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

    if inherited_used:
        syntax_events.append(SYNTAX_INHERITED_PREFIX)
    if hyphen_skipped:
        syntax_events.append(SYNTAX_DISPLAY_SEPARATOR)
    ordered_events = tuple(dict.fromkeys(syntax_events))

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
        syntax_events=ordered_events,
        inherited_token_prefix=inherited_prefix if inherited_used else "",
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
    return parse_chemical_notation(sequence, source_type=source_type)

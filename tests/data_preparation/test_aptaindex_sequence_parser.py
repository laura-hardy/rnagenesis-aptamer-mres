"""Synthetic unit tests for the AptaIndex chemical-notation parser.

Every Sequence literal in this file is invented. Real AptaIndex sequences
are never copied here.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptaindex_sequence_parser import (  # noqa: E402
    STATUS_MISSING,
    STATUS_NOT_APPLICABLE_PEPTIDE,
    STATUS_SUCCESS,
    STATUS_UNSUPPORTED,
    parse_aptaindex_source_sequence,
    parse_chemical_notation,
)


def test_missing_input() -> None:
    for raw in (None, "", "   "):
        result = parse_chemical_notation(raw)
        assert result.status == STATUS_MISSING
        assert result.base_string == ""


def test_dna_standard_tokens_retain_t() -> None:
    result = parse_chemical_notation("5'-dApdTpdGpdC-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ATGC"
    assert result.token_family_summary == "d"
    assert result.has_t is True
    assert result.has_u is False
    assert result.has_l_prefix is False


def test_rna_standard_tokens() -> None:
    result = parse_chemical_notation("5'-rAprUprGprC-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AUGC"
    assert result.token_family_summary == "r"
    assert result.has_u is True
    assert result.has_t is False


def test_2f_rna_mix_with_safe_whitespace() -> None:
    result = parse_chemical_notation("5'-fAprU pfGprC-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AUGC"
    assert result.token_family_summary == "f+r"
    assert result.whitespace_skipped is True


def test_omethyl_like_m_prefix_parses_without_chemistry_claim() -> None:
    result = parse_chemical_notation("5'-mAmCmG-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ACG"
    assert result.token_family_summary == "m"


def test_n_prefix_parses_syntactically_without_unsupported_chemistry() -> None:
    result = parse_chemical_notation("5'-nAnCnG-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ACG"
    assert result.token_family_summary == "n"


def test_l_rna_syntax() -> None:
    result = parse_chemical_notation("5'-LrALrGLrC-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AGC"
    assert result.token_family_summary == "r"
    assert result.has_l_prefix is True


def test_l_dna_syntax() -> None:
    result = parse_chemical_notation("5'-LdALdTLdG-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ATG"
    assert result.token_family_summary == "d"
    assert result.has_l_prefix is True
    assert result.has_t is True


def test_phosphorothioate_linkage() -> None:
    result = parse_chemical_notation("5'-dAsdTsdG-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ATG"
    assert result.linkage_summary == "s"
    assert "s" in result.internucleotide_linkages


def test_mixed_p_and_s_linkages() -> None:
    result = parse_chemical_notation("5'-dApdTsdG-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ATG"
    assert result.linkage_summary == "p+s"


def test_trailing_terminal_phosphate_is_consumed() -> None:
    result = parse_chemical_notation("5'-dApdTpdGp-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ATG"
    assert result.has_terminal_phosphate is True
    assert result.terminal_phosphate_marker == "p"


def test_unicode_right_single_quote_terminals() -> None:
    result = parse_chemical_notation("5\u2019-rAprG-3\u2019")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AG"
    assert result.token_family_summary == "r"


def test_unicode_prime_terminals() -> None:
    result = parse_chemical_notation("5\u2032-dApdC-3\u2032")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AC"


def test_swapped_quote_before_digit_still_5_to_3() -> None:
    result = parse_chemical_notation("'5-dApdTpdG-'3")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ATG"


def test_no_terminals_still_parses_explicit_tokens() -> None:
    result = parse_chemical_notation("dApdTpdGpdC")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ATGC"


def test_safe_token_separating_whitespace() -> None:
    result = parse_chemical_notation("5'-dA p dT p dG-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ATG"
    assert result.whitespace_skipped is True


def test_outer_whitespace_preserved_only_as_formatting() -> None:
    result = parse_chemical_notation("  5'-rAprC-3'  ")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AC"


def test_inosine_base_letter_parses() -> None:
    result = parse_chemical_notation("5'-rIprAprC-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "IAC"
    assert result.has_i is True


def _assert_full_failure(raw: str) -> None:
    result = parse_chemical_notation(raw)
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""
    assert result.n_tokens == 0


def test_unknown_token_xlk_fails_closed() -> None:
    _assert_full_failure("5'-dApXlkdT-3'")


def test_spacer_dsp_fails_closed() -> None:
    _assert_full_failure("5'-dADspdT-3'")


def test_brace_label_fails_closed() -> None:
    _assert_full_failure("5'-{5'/FAM}dApdT-3'")


def test_thiol_decoration_fails_closed() -> None:
    _assert_full_failure("5'-SH-(NH2)6-dApdT-3'")


def test_iupac_n_fails_closed() -> None:
    _assert_full_failure("5'-dNpdApdT-3'")
    result = parse_chemical_notation("5'-dApdNpdT-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_bare_unknown_modification_fails_closed() -> None:
    _assert_full_failure("5'-dApidT-3'")


def test_unknown_text_between_valid_tokens_fails_closed() -> None:
    result = parse_chemical_notation("5'-dApZZZdT-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_valid_prefix_followed_by_unconsumed_suffix_fails_closed() -> None:
    result = parse_chemical_notation("5'-dApdT-extra-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_omitted_chemistry_prefix_fails_closed() -> None:
    result = parse_chemical_notation("5'-dApUprG-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_slash_prefix_fails_closed() -> None:
    _assert_full_failure("/dApdTpdG")


def test_unprefixed_stretch_fails_closed() -> None:
    _assert_full_failure("ATGCGC")


def test_swapped_3_to_5_orientation_fails_closed() -> None:
    result = parse_chemical_notation("3'-dApdTpdG-5'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""
    assert result.reason_category == "swapped_terminal_orientation"


def test_peptide_source_type_is_not_applicable() -> None:
    result = parse_aptaindex_source_sequence(
        "ACDEFGHIKLMNPQRSTVWY",
        source_type="Peptide",
    )
    assert result.status == STATUS_NOT_APPLICABLE_PEPTIDE
    assert result.base_string == ""
    assert result.reason_category == "source_declared_peptide"


def test_peptide_text_is_not_treated_as_malformed_rna() -> None:
    result = parse_aptaindex_source_sequence(
        "ACDEFG",
        source_type="Peptide",
    )
    assert result.status != STATUS_UNSUPPORTED
    assert result.status == STATUS_NOT_APPLICABLE_PEPTIDE

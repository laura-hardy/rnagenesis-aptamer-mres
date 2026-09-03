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
    SYNTAX_DISPLAY_SEPARATOR,
    SYNTAX_INHERITED_PREFIX,
    SYNTAX_TERMINAL_PHOSPHATE,
    SYNTAX_THIOL_CAP,
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


def test_uniform_r_stream_inherits_prefix_for_one_bare_u() -> None:
    result = parse_chemical_notation("5'-rAprUprGpUprC-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AUGUC"
    assert result.token_family_summary == "r"
    assert result.inherited_token_prefix == "r"
    assert SYNTAX_INHERITED_PREFIX in result.syntax_events


def test_uniform_r_stream_inherits_prefix_for_several_bare_bases() -> None:
    result = parse_chemical_notation("5'-rApUprGpCprA-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AUGCA"
    assert result.token_family_summary == "r"
    assert SYNTAX_INHERITED_PREFIX in result.syntax_events


def test_uniform_f_stream_inherits_prefix_for_one_bare_u() -> None:
    result = parse_chemical_notation("5'-fApfUpfGpUfC-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AUGUC"
    assert result.token_family_summary == "f"
    assert result.inherited_token_prefix == "f"


def test_leading_bare_base_inherits_uniform_f_prefix() -> None:
    result = parse_chemical_notation("5'-UfAfCfG-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "UACG"
    assert result.token_family_summary == "f"
    assert result.inherited_token_prefix == "f"
    assert SYNTAX_INHERITED_PREFIX in result.syntax_events


def test_leading_bare_base_with_source_type_2f_inherits_f() -> None:
    result = parse_aptaindex_source_sequence(
        "5'-UfAfCfG-3'",
        source_type="2'-F-RNA",
    )
    assert result.status == STATUS_SUCCESS
    assert result.token_family_summary == "f"


def test_explicit_d_stream_with_source_type_rna_does_not_inherit() -> None:
    result = parse_aptaindex_source_sequence(
        "5'-dApUpdG-3'",
        source_type="RNA",
    )
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_mixed_explicit_d_and_r_stream_does_not_infer_prefix() -> None:
    result = parse_chemical_notation("5'-dAprUpUprG-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_unknown_token_after_recoverable_bare_bases_still_fails() -> None:
    result = parse_chemical_notation("5'-rApUprGXlk-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_partial_consumption_remains_failure_with_inherit_candidate() -> None:
    result = parse_chemical_notation("5'-rApUprG-extra-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_terminal_phosphate_brace_then_rna_tokens_succeeds() -> None:
    result = parse_chemical_notation("5'-{5'/Phosphate}-rAprUprG-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AUG"
    assert result.token_family_summary == "r"
    assert SYNTAX_TERMINAL_PHOSPHATE in result.syntax_events


def test_leading_p_hyphen_then_rna_tokens_succeeds() -> None:
    result = parse_chemical_notation("5'-P-rAprUprG-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AUG"
    assert result.token_family_summary == "r"
    assert SYNTAX_TERMINAL_PHOSPHATE in result.syntax_events


def test_internal_spacer_brace_still_fails() -> None:
    _assert_full_failure("5'-rAp{Spacer 18}rU-3'")


def test_arbitrary_brace_label_still_fails() -> None:
    _assert_full_failure("5'-{Label}rAprU-3'")
    _assert_full_failure("5'-{FAM-dT}rAprU-3'")
    _assert_full_failure("5'-{Dabcyl-dT}dApdT-3'")


def test_allowlisted_thiol_hexyl_then_dna_tokens_succeeds() -> None:
    result = parse_chemical_notation("5'-SH-(CH2)6-dApdTpdG-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "ATG"
    assert result.token_family_summary == "d"
    assert SYNTAX_THIOL_CAP in result.syntax_events
    assert result.n_tokens == 3


def test_arbitrary_thiol_chemistry_still_fails() -> None:
    _assert_full_failure("5'-SH-foo-dApdT-3'")
    _assert_full_failure("5'-SH-(NH2)6-dApdT-3'")


def test_safe_display_hyphen_inside_same_family_succeeds() -> None:
    result = parse_chemical_notation("5'-rAprU-rGprC-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AUGC"
    assert result.token_family_summary == "r"
    assert SYNTAX_DISPLAY_SEPARATOR in result.syntax_events


def test_hyphen_plus_inherited_bare_base_in_uniform_r_family_succeeds() -> None:
    result = parse_chemical_notation("5'-rAprUp-U-rGprC-3'")
    assert result.status == STATUS_SUCCESS
    assert result.base_string == "AUUGC"
    assert result.token_family_summary == "r"
    assert SYNTAX_INHERITED_PREFIX in result.syntax_events
    assert SYNTAX_DISPLAY_SEPARATOR in result.syntax_events


def test_hyphen_r_n_insertion_still_fails() -> None:
    _assert_full_failure("5'-dApdT-R-N-dG-3'")


def test_hyphen_y_still_fails() -> None:
    _assert_full_failure("5'-rAprU-Y-rG-3'")


def test_hyphen_next_to_unknown_modification_still_fails() -> None:
    result = parse_chemical_notation("5'-dAp-XlkdT-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_regression_reverse_orientation_still_fails() -> None:
    result = parse_chemical_notation("3'-dApdTpdG-5'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""
    assert result.reason_category == "swapped_terminal_orientation"


def test_regression_trailing_i_still_fails() -> None:
    result = parse_chemical_notation("5'-dApdTpdGi-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_regression_dn_nap_du_still_fails() -> None:
    _assert_full_failure("5'-dNpdApdT-3'")
    result = parse_chemical_notation("5'-dApdNpdT-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_regression_dd_still_fails() -> None:
    _assert_full_failure("5'-dDpdApdT-3'")
    result = parse_chemical_notation("5'-dApdDpdT-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_regression_btn_still_fails() -> None:
    _assert_full_failure("5'-dApbTndT-3'")
    result = parse_chemical_notation("5'-dApdTpbTndG-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_regression_xlk_still_fails() -> None:
    _assert_full_failure("5'-dApXlkdT-3'")


def test_regression_brace_spacer_still_fails() -> None:
    _assert_full_failure("5'-dAp{Internal/Spacer 18}dT-3'")


def test_regression_mixed_incompatible_families_do_not_inherit() -> None:
    result = parse_aptaindex_source_sequence(
        "5'-dApUpdGpdC-3'",
        source_type="2'-F-RNA",
    )
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""


def test_plain_unprefixed_string_still_fails() -> None:
    _assert_full_failure("ATGCGC")
    _assert_full_failure("5'-AUGCGC-3'")


def test_lowercase_token_base_still_fails() -> None:
    result = parse_chemical_notation("5'-dApdtpdG-3'")
    assert result.status == STATUS_UNSUPPORTED
    assert result.base_string == ""

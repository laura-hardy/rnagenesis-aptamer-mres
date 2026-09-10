"""Tests for ENA review v2 (stage 4: target/evidence repair + group-first review)."""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ena_review_v2_rules import (  # noqa: E402
    BINDING_EVIDENCE_TYPES,
    classify_conflict_type,
    conflict_is_biological,
    normalize_binding_evidence_type,
    normalize_target_comparison_key,
    preferred_display_name,
    propose_promoter_trim,
    repair_binding_evidence_v2,
    repair_target_v2,
    strongest_evidence_scope_v2,
    targets_compare_equivalent,
    validate_manual_group_include,
)
from refine_ena_manual_review import (  # noqa: E402
    ReviewValidationError,
    apply_group_corrections_to_accessions,
    build_group_review,
    build_parser,
    build_sequence_review_for_groups,
    consolidate_accepted_pairs,
    consolidate_sequence_target_units,
    derive_effective_sequence,
    derive_effective_target,
    effective_group_target,
    is_unresolved_effective_target,
    main,
    run_apply_group_review,
    run_apply_sequence_review,
    validate_sequence_template_against_groups,
)



# ---------------------------------------------------------------------------
# 1–3 Alias / comparison keys
# ---------------------------------------------------------------------------


def test_fgf2_fgf_dash_same_comparison_key():
    assert normalize_target_comparison_key("FGF2") == normalize_target_comparison_key("FGF-2")
    assert normalize_target_comparison_key("FGF2") == normalize_target_comparison_key("fgf 2")
    assert targets_compare_equivalent("FGF2", "FGF-2")


def test_fgf2_not_biological_conflict():
    items = [
        (normalize_target_comparison_key("FGF2"), "", "FGF2"),
        (normalize_target_comparison_key("FGF-2"), "", "FGF-2"),
    ]
    ctype = classify_conflict_type(items)
    assert ctype in {"no_conflict", "orthographic_alias_only"}
    # orthographic_alias_only must not enter the biological conflict queue
    assert not conflict_is_biological(ctype)


def test_il17_il_dash_17_equivalent():
    assert targets_compare_equivalent("IL17", "IL-17")
    assert targets_compare_equivalent("IL17", "IL 17")
    assert normalize_target_comparison_key("IL21") == normalize_target_comparison_key("IL-21")
    assert targets_compare_equivalent("TNF alpha", "TNF-α")


# ---------------------------------------------------------------------------
# 4–11 Target repairs
# ---------------------------------------------------------------------------


def test_purification_of_human_igg():
    r = repair_target_v2("purification of human IgG", target_type="unknown")
    assert r.target_name.lower() == "human igg"
    assert r.target_type == "antibody"
    assert "purification" not in r.target_name.lower()


def test_pcv2_capsid_protein_is_protein_not_enzyme():
    r = repair_target_v2(
        "PCV2 capsid protein",
        target_type="enzyme",
        context_text="inhibits replication of porcine circovirus",
    )
    assert r.target_type == "protein"
    assert "PCV2" in r.target_name
    assert "capsid" in (r.target_region or r.target_name).lower()


def test_surface_protein_tsa56_is_protein():
    r = repair_target_v2(
        "surface protein TSA56 of Orientia tsutsugamushi",
        target_type="unknown",
    )
    assert r.target_name == "TSA56"
    assert r.target_type == "protein"
    assert "surface" in r.target_region.lower()


def test_rna_aptamer_binding_erbb2():
    r = repair_target_v2("RNA aptamer binding ErbB2", target_type="unknown")
    assert "erbb2" in r.target_name.lower() or "ErbB2" in r.target_display_name
    assert r.target_type == "protein"


def test_bare_erbb2_alias_is_protein():
    r = repair_target_v2("ErbB2", target_type="unknown")
    assert r.target_type == "protein"
    assert r.target_comparison_key == normalize_target_comparison_key("ErbB2")


def test_tsa56_not_compound_when_protein_context():
    r = repair_target_v2(
        "TSA56",
        target_type="protein",
        context_text="surface protein TSA56 of Orientia tsutsugamushi",
    )
    assert r.target_type == "protein"
    assert r.target_type != "unknown_or_probable_small_molecule"


def test_specifically_binding_tyrosinase():
    r = repair_target_v2(
        "RNA aptamer specifically binding tyrosinase",
        target_type="unknown",
    )
    assert "tyrosinase" in r.target_name.lower()
    assert r.target_type in {"protein", "enzyme"}


def test_hcv_replicon_not_enzyme():
    r = repair_target_v2(
        "replication of Hepatitis C virus replicon",
        target_type="enzyme",
    )
    assert r.target_type == "viral_process_or_system"
    assert r.target_type != "enzyme"


def test_histamine_non_protein():
    r = repair_target_v2("histamine", target_type="protein")
    assert r.target_type == "small_molecule"
    assert r.target_type != "protein"


def test_generic_target_protein_unknown():
    r = repair_target_v2("target protein", target_type="protein")
    assert r.target_type == "unknown"
    assert r.target_confidence == "low"
    assert r.was_generic


# ---------------------------------------------------------------------------
# 12–14 Evidence repairs
# ---------------------------------------------------------------------------


def test_anti_target_patent_title_weak_patent_claim():
    ev = repair_binding_evidence_v2(
        description="WO 2017094897-A/1: Anti-IL-17 aptamer having improved retentivity in blood.",
        reference_titles="Anti-IL-17 aptamer having improved retentivity in blood",
        binding_evidence_status="none_found",
        binding_evidence_strength="none",
        prior_scope="none",
    )
    assert ev.evidence_scope == "patent_claim_level"
    assert ev.binding_evidence_type == "target_specific_aptamer_claim"
    assert ev.binding_evidence_strength == "weak"
    assert ev.evidence_scope != "none"


def test_selectively_binds_patent_moderate_claim():
    ev = repair_binding_evidence_v2(
        description=(
            "WO 2015/000000: RNA aptamer that selectively binds to "
            "extracellular domain of PAP"
        ),
        reference_titles="RNA aptamer that selectively binds to extracellular domain of PAP",
        binding_evidence_strength="none",
        prior_scope="none",
    )
    assert ev.evidence_scope == "patent_claim_level"
    assert ev.binding_evidence_type == "explicit_binding_claim"
    assert ev.binding_evidence_strength == "moderate"


def test_patent_title_not_individual_sequence_evidence():
    ev = repair_binding_evidence_v2(
        description="WO 2017094897: Anti-IL-17 aptamer having improved retentivity in blood.",
        reference_titles="Anti-IL-17 aptamer",
        binding_evidence_status="explicit_binds_or_recognizes_statement",
        binding_evidence_strength="moderate",
        prior_scope="individual_sequence_qualitative",
        accession_count=1,
    )
    assert ev.evidence_scope == "patent_claim_level"
    assert not ev.evidence_scope.startswith("individual")


def test_strongest_evidence_scope_prefers_stronger_not_weaker():
    assert (
        strongest_evidence_scope_v2(["none", "individual_sequence_quantitative"])
        == "individual_sequence_quantitative"
    )
    assert (
        strongest_evidence_scope_v2(
            ["selection_context_only", "patent_claim_level", "none"]
        )
        == "patent_claim_level"
    )
    assert (
        strongest_evidence_scope_v2(
            ["experiment_or_family_level", "selection_context_only"]
        )
        == "experiment_family_level"
    )
    assert strongest_evidence_scope_v2([]) == "none"


def test_preserved_prior_uses_valid_binding_evidence_type():
    ev = repair_binding_evidence_v2(
        description="RNA aptamer study without patent markers",
        binding_evidence_strength="moderate",
        binding_evidence_types="",
        prior_scope="experiment_family_level",
    )
    assert ev.repair_reason == "preserved_prior"
    assert ev.binding_evidence_type in BINDING_EVIDENCE_TYPES
    assert ev.binding_evidence_type != "experiment_family"

    ev2 = repair_binding_evidence_v2(
        description="plain text",
        binding_evidence_strength="moderate",
        binding_evidence_types="explicit_binds_or_recognizes_statement",
        prior_scope="experiment_or_family_level",
    )
    assert ev2.repair_reason == "preserved_prior"
    assert ev2.binding_evidence_type == "explicit_binding_claim"
    assert ev2.binding_evidence_type in BINDING_EVIDENCE_TYPES


def test_normalize_binding_evidence_type_rejects_experiment_family_token():
    assert normalize_binding_evidence_type("experiment_family") in BINDING_EVIDENCE_TYPES
    assert normalize_binding_evidence_type("experiment_family") != "experiment_family"
    assert (
        normalize_binding_evidence_type("", evidence_scope="selection_context_only")
        == "selection_against_target"
    )


# ---------------------------------------------------------------------------
# 15–16 Ambiguous consolidation
# ---------------------------------------------------------------------------


def _acc(**kwargs):
    base = {
        "accession": "A1",
        "review_unit_id_v1": "u1",
        "experiment_group_id": "exp1",
        "sequence_deposited": "GGGTAGCCGGAGGAGNCAGNRAUCGGTACCC",
        "rna_sequence": "GGGUAGCCGGAGGAGNCAGNRAUCGGUACCC",
        "sequence_length": "31",
        "is_concrete": "0",
        "contains_ambiguous_bases": "1",
        "ambiguous_base_count": "3",
        "longest_ambiguous_run": "1",
        "ambiguity_symbols": "NR",
        "sequence_quality_status": "possible_consensus_pattern",
        "length_status": "20_to_120_typical_range",
        "contains_t7_promoter": "0",
        "possible_post_promoter_sequence": "",
        "post_promoter_sequence_length": "0",
        "promoter_trim_status": "",
        "description": "WO 2017094897: Anti-IL-17 aptamer",
        "reference": "Anti-IL-17 aptamer",
        "rna_identity_status": "explicit_rna_aptamer",
        "sequence_role": "likely_full_aptamer_sequence",
        "selection_evidence": "",
        "source_candidate_tier": "Tier_B_plausible_needs_review",
        "doi_values": "",
        "pubmed_values": "",
        "publication_or_patent_identifier": "WO 2017094897",
        "target_raw": "IL-17",
        "target_name": "IL-17",
        "target_display_name": "IL-17",
        "target_comparison_key": normalize_target_comparison_key("IL-17"),
        "target_region": "",
        "target_context": "",
        "target_type": "protein",
        "target_repair_reason": "unchanged",
        "target_confidence": "moderate",
        "target_type_prior": "protein",
        "target_type_changed": "0",
        "target_alias_applied": "0",
        "target_was_generic": "0",
        "target_unresolved": "0",
        "target_notes": "",
        "binding_evidence_strength": "weak",
        "binding_evidence_type": "target_specific_aptamer_claim",
        "evidence_scope": "patent_claim_level",
        "binding_evidence_text": "Anti-IL-17 aptamer",
        "evidence_prior_scope": "selection_context_only",
        "evidence_repair_reason": "patent_anti_target_claim",
        "evidence_upgraded_from_none": "1",
        "evidence_downgraded_from_individual": "0",
    }
    base.update(kwargs)
    return base


def test_identical_ambiguous_sequence_target_consolidate():
    seq = "GGGUAGCCGGAGGAGNCAGNRAUCGGUACCC"
    acc_df = pd.DataFrame(
        [
            _acc(accession="LX1", rna_sequence=seq),
            _acc(accession="LX2", rna_sequence=seq, review_unit_id_v1="u2"),
            _acc(accession="LX3", rna_sequence=seq, review_unit_id_v1="u3"),
        ]
    )
    units, prov, _ = consolidate_sequence_target_units(acc_df)
    assert len(units) == 1
    assert int(units.iloc[0]["accession_count"]) == 3
    assert set(prov["accession"]) == {"LX1", "LX2", "LX3"}


def test_ambiguous_sequence_provenance_retained():
    seq = "GGGUAGCCGGAGGAGNCAGNRAUCGGUACCC"
    acc_df = pd.DataFrame(
        [
            _acc(accession="LX1", rna_sequence=seq, ambiguity_symbols="NR", ambiguous_base_count="3"),
            _acc(accession="LX2", rna_sequence=seq, ambiguity_symbols="NR", ambiguous_base_count="3"),
        ]
    )
    units, prov, _ = consolidate_sequence_target_units(acc_df)
    assert units.iloc[0]["contains_ambiguous_bases"] == "1"
    assert units.iloc[0]["ambiguity_symbols"] == "NR"
    assert int(units.iloc[0]["ambiguous_base_count"]) == 3
    assert len(prov) == 2
    assert set(prov["ambiguity_symbols"]) == {"NR"}


# ---------------------------------------------------------------------------
# 17–18 Conflicts
# ---------------------------------------------------------------------------


def test_viral_process_fallback_key_not_dropped_from_conflicts():
    """Literal VIRAL_PROCESS fallback must not be excluded from conflict analysis."""
    ctype = classify_conflict_type(
        [
            (normalize_target_comparison_key("PAP"), "", "PAP"),
            ("VIRAL_PROCESS", "", "replication of Hepatitis C virus replicon"),
        ]
    )
    assert ctype == "genuine_different_target"
    assert conflict_is_biological(ctype)


def test_genuine_pap_hcv_conflict_flagged():
    seq = "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGU"
    pap_key = normalize_target_comparison_key("PAP")
    hcv_key = normalize_target_comparison_key("replication of Hepatitis C virus replicon")
    assert pap_key != hcv_key
    acc_df = pd.DataFrame(
        [
            _acc(
                accession="P1",
                rna_sequence=seq,
                is_concrete="1",
                contains_ambiguous_bases="0",
                ambiguous_base_count="0",
                ambiguity_symbols="",
                sequence_quality_status="concrete_candidate_sequence",
                target_raw="PAP",
                target_name="PAP",
                target_display_name="PAP",
                target_comparison_key=pap_key,
                target_type="protein",
            ),
            _acc(
                accession="H1",
                rna_sequence=seq,
                is_concrete="1",
                contains_ambiguous_bases="0",
                ambiguous_base_count="0",
                ambiguity_symbols="",
                sequence_quality_status="concrete_candidate_sequence",
                target_raw="replication of Hepatitis C virus replicon",
                target_name="replication of Hepatitis C virus replicon",
                target_display_name="replication of Hepatitis C virus replicon",
                target_comparison_key=hcv_key,
                target_type="viral_process_or_system",
                review_unit_id_v1="u2",
            ),
        ]
    )
    units, _, conflicts = consolidate_sequence_target_units(acc_df)
    assert len(units) == 2
    assert set(units["genuine_target_conflict"]) == {"1"}
    assert len(conflicts) >= 1
    assert all(conflicts["conflict_type"] == "genuine_different_target")


def test_alias_only_conflicts_removed_from_conflict_csv():
    seq = "GCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGC"
    k = normalize_target_comparison_key("FGF2")
    acc_df = pd.DataFrame(
        [
            _acc(
                accession="F1",
                rna_sequence=seq,
                is_concrete="1",
                contains_ambiguous_bases="0",
                ambiguous_base_count="0",
                ambiguity_symbols="",
                sequence_quality_status="concrete_candidate_sequence",
                target_raw="FGF2",
                target_name="FGF2",
                target_display_name="FGF2",
                target_comparison_key=k,
            ),
            _acc(
                accession="F2",
                rna_sequence=seq,
                is_concrete="1",
                contains_ambiguous_bases="0",
                ambiguous_base_count="0",
                ambiguity_symbols="",
                sequence_quality_status="concrete_candidate_sequence",
                target_raw="FGF-2",
                target_name="FGF-2",
                target_display_name="FGF2",
                target_comparison_key=k,
                review_unit_id_v1="u2",
            ),
        ]
    )
    units, _, conflicts = consolidate_sequence_target_units(acc_df)
    assert len(units) == 1
    assert units.iloc[0]["genuine_target_conflict"] == "0"
    assert len(conflicts) == 0


# ---------------------------------------------------------------------------
# 19–21 Group → sequence workflow
# ---------------------------------------------------------------------------


def test_group_manual_decisions_accept_only_blank_0_1():
    assert validate_manual_group_include("") == ""
    assert validate_manual_group_include("0") == "0"
    assert validate_manual_group_include("1") == "1"
    assert validate_manual_group_include("2") is None
    assert validate_manual_group_include("yes") is None


def test_sequence_review_only_from_groups_marked_1(tmp_path: Path):
    seq_keep = "ACGU" * 10
    seq_reject = "GCGC" * 10
    seq_blank = "UGCA" * 10
    prov = pd.DataFrame(
        [
            {
                "review_unit_id": "r1",
                "accession": "A1",
                "experiment_group_id": "g_keep",
                "sequence_deposited": seq_keep.replace("U", "T"),
                "rna_sequence": seq_keep,
                "target_raw": "IL-17",
                "target_name": "IL-17",
                "target_display_name": "IL-17",
                "target_comparison_key": normalize_target_comparison_key("IL-17"),
                "target_region": "",
                "target_type": "protein",
                "target_repair_reason": "",
                "description": "Anti-IL-17 aptamer",
                "reference": "",
                "binding_evidence_type": "target_specific_aptamer_claim",
                "binding_evidence_strength": "weak",
                "evidence_scope": "patent_claim_level",
                "evidence_repair_reason": "",
                "selection_evidence": "",
                "sequence_role": "likely_full_aptamer_sequence",
                "sequence_quality_status": "concrete_candidate_sequence",
                "ambiguity_symbols": "",
                "ambiguous_base_count": "0",
                "longest_ambiguous_run": "0",
                "promoter_trim_status": "",
                "possible_post_promoter_sequence": "",
                "source_candidate_tier": "Tier_B_plausible_needs_review",
                "review_unit_id_v1": "u1",
            },
            {
                "review_unit_id": "r2",
                "accession": "A2",
                "experiment_group_id": "g_reject",
                "sequence_deposited": seq_reject.replace("U", "T"),
                "rna_sequence": seq_reject,
                "target_raw": "histamine",
                "target_name": "histamine",
                "target_display_name": "histamine",
                "target_comparison_key": normalize_target_comparison_key("histamine"),
                "target_region": "",
                "target_type": "small_molecule",
                "target_repair_reason": "",
                "description": "histamine aptamer",
                "reference": "",
                "binding_evidence_type": "none",
                "binding_evidence_strength": "none",
                "evidence_scope": "none",
                "evidence_repair_reason": "",
                "selection_evidence": "",
                "sequence_role": "",
                "sequence_quality_status": "concrete_candidate_sequence",
                "ambiguity_symbols": "",
                "ambiguous_base_count": "0",
                "longest_ambiguous_run": "0",
                "promoter_trim_status": "",
                "possible_post_promoter_sequence": "",
                "source_candidate_tier": "",
                "review_unit_id_v1": "u2",
            },
            {
                "review_unit_id": "r3",
                "accession": "A3",
                "experiment_group_id": "g_blank",
                "sequence_deposited": seq_blank.replace("U", "T"),
                "rna_sequence": seq_blank,
                "target_raw": "VEGF",
                "target_name": "VEGF",
                "target_display_name": "VEGF",
                "target_comparison_key": normalize_target_comparison_key("VEGF"),
                "target_region": "",
                "target_type": "protein",
                "target_repair_reason": "",
                "description": "VEGF aptamer",
                "reference": "",
                "binding_evidence_type": "explicit_binding_claim",
                "binding_evidence_strength": "moderate",
                "evidence_scope": "patent_claim_level",
                "evidence_repair_reason": "",
                "selection_evidence": "",
                "sequence_role": "",
                "sequence_quality_status": "concrete_candidate_sequence",
                "ambiguity_symbols": "",
                "ambiguous_base_count": "0",
                "longest_ambiguous_run": "0",
                "promoter_trim_status": "",
                "possible_post_promoter_sequence": "",
                "source_candidate_tier": "",
                "review_unit_id_v1": "u3",
            },
        ]
    )
    prov.to_csv(tmp_path / "ena_sequence_review_provenance_all.csv", index=False)

    group = pd.DataFrame(
        {
            "manual_group_include": ["1", "0", ""],
            "manual_target_corrected": ["", "", ""],
            "manual_target_type_corrected": ["", "", ""],
            "experiment_group_id": ["g_keep", "g_reject", "g_blank"],
            "target_display_name": ["IL-17", "histamine", "VEGF"],
            "target_type": ["protein", "small_molecule", "protein"],
        }
    )
    group_path = tmp_path / "ena_group_review_template.csv"
    group.to_csv(group_path, index=False)

    summary = run_apply_group_review(group_path, tmp_path)
    assert summary["groups_retained"] == 1
    assert summary["groups_rejected"] == 1
    assert summary["groups_unreviewed"] == 1
    assert summary["sequence_review_rows"] == 1

    seq_t = pd.read_csv(tmp_path / "ena_sequence_review_template.csv", dtype=str).fillna("")
    assert list(seq_t["experiment_group_id"]) == ["g_keep"]
    assert "g_reject" not in set(seq_t["experiment_group_id"])
    assert "g_blank" not in set(seq_t["experiment_group_id"])
    assert (seq_t["manual_include"] == "").all()

    seq_p = pd.read_csv(tmp_path / "ena_sequence_review_provenance.csv", dtype=str).fillna("")
    assert set(seq_p["accession"]) == {"A1"}


def test_sequence_review_sorts_length_numerically():
    """String lengths must not sort alphabetically ('9' after '10')."""
    units = pd.DataFrame(
        [
            {
                "review_unit_id": "r10",
                "experiment_group_id": "g1",
                "target_display_name": "VEGF",
                "target_region": "",
                "target_type": "protein",
                "rna_sequence": "A" * 10,
                "sequence_length": "10",
                "sequence_quality_status": "concrete_candidate_sequence",
                "length_status": "under_15_high_concern",
                "near_duplicate_family_id": "",
                "near_duplicate_family_size": "",
                "accession_count": "1",
                "accessions": "A10",
                "binding_evidence_type": "none",
                "binding_evidence_strength": "none",
                "evidence_scope": "none",
                "representative_title": "",
                "automatic_concern_flags": "",
                "genuine_target_conflict": "0",
            },
            {
                "review_unit_id": "r9",
                "experiment_group_id": "g1",
                "target_display_name": "VEGF",
                "target_region": "",
                "target_type": "protein",
                "rna_sequence": "B" * 9,
                "sequence_length": "9",
                "sequence_quality_status": "concrete_candidate_sequence",
                "length_status": "under_15_high_concern",
                "near_duplicate_family_id": "",
                "near_duplicate_family_size": "",
                "accession_count": "1",
                "accessions": "A9",
                "binding_evidence_type": "none",
                "binding_evidence_strength": "none",
                "evidence_scope": "none",
                "representative_title": "",
                "automatic_concern_flags": "",
                "genuine_target_conflict": "0",
            },
            {
                "review_unit_id": "r20",
                "experiment_group_id": "g1",
                "target_display_name": "VEGF",
                "target_region": "",
                "target_type": "protein",
                "rna_sequence": "C" * 20,
                "sequence_length": "20",
                "sequence_quality_status": "concrete_candidate_sequence",
                "length_status": "20_to_120_typical_range",
                "near_duplicate_family_id": "",
                "near_duplicate_family_size": "",
                "accession_count": "1",
                "accessions": "A20",
                "binding_evidence_type": "none",
                "binding_evidence_strength": "none",
                "evidence_scope": "none",
                "representative_title": "",
                "automatic_concern_flags": "",
                "genuine_target_conflict": "0",
            },
        ]
    )
    prov = pd.DataFrame(
        [
            {"review_unit_id": "r10", "accession": "A10", "experiment_group_id": "g1"},
            {"review_unit_id": "r9", "accession": "A9", "experiment_group_id": "g1"},
            {"review_unit_id": "r20", "accession": "A20", "experiment_group_id": "g1"},
        ]
    )
    template, _ = build_sequence_review_for_groups(units, prov, {"g1"})
    assert list(template["sequence_length"]) == ["9", "10", "20"]
    assert list(template["review_unit_id"]) == ["r9", "r10", "r20"]


def test_full_provenance_outside_compact_templates():
    """Group provenance holds bulky fields; template stays compact."""
    acc_df = pd.DataFrame(
        [
            _acc(accession="X1", experiment_group_id="eg1", description="short title " + ("long " * 200)),
            _acc(accession="X2", experiment_group_id="eg1", description="other desc"),
        ]
    )
    units, _, _ = consolidate_sequence_target_units(acc_df)
    stage3 = pd.DataFrame(
        [
            {
                "experiment_group_id": "eg1",
                "representative_accession": "X1",
                "common_description": "short",
                "common_reference": "ref",
            }
        ]
    )
    template, prov = build_group_review(acc_df, units, stage3)
    assert "all_descriptions" in prov.columns
    assert "all_descriptions" not in template.columns
    assert "sample_sequence_1" in template.columns
    assert "manual_group_include" in template.columns


def test_apply_group_review_rejects_invalid_manual_value(tmp_path: Path):
    seq = "ACGUACGU"
    prov = pd.DataFrame(
        [
            {
                "review_unit_id": "r1",
                "accession": "A1",
                "experiment_group_id": "g1",
                "sequence_deposited": seq.replace("U", "T"),
                "rna_sequence": seq,
                "target_raw": "X",
                "target_name": "X",
                "target_display_name": "X",
                "target_comparison_key": "X",
                "target_region": "",
                "target_type": "protein",
                "target_repair_reason": "",
                "description": "",
                "reference": "",
                "binding_evidence_type": "none",
                "binding_evidence_strength": "none",
                "evidence_scope": "none",
                "evidence_repair_reason": "",
                "selection_evidence": "",
                "sequence_role": "",
                "sequence_quality_status": "too_short_requires_review",
                "ambiguity_symbols": "",
                "ambiguous_base_count": "0",
                "longest_ambiguous_run": "0",
                "promoter_trim_status": "",
                "possible_post_promoter_sequence": "",
                "source_candidate_tier": "",
                "review_unit_id_v1": "u1",
            }
        ]
    )
    prov.to_csv(tmp_path / "ena_sequence_review_provenance_all.csv", index=False)
    group = pd.DataFrame(
        {
            "manual_group_include": ["maybe"],
            "experiment_group_id": ["g1"],
            "target_display_name": ["X"],
            "target_type": ["protein"],
            "manual_target_corrected": [""],
            "manual_target_type_corrected": [""],
        }
    )
    path = tmp_path / "groups.csv"
    group.to_csv(path, index=False)
    with pytest.raises(ReviewValidationError):
        run_apply_group_review(path, tmp_path)


# ---------------------------------------------------------------------------
# 22 Offline
# ---------------------------------------------------------------------------


def test_no_internet_required():
    with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
        assert targets_compare_equivalent("FGF2", "FGF-2")
        r = repair_target_v2("purification of human IgG")
        assert r.target_name.lower() == "human igg"
        ev = repair_binding_evidence_v2(
            description="WO 1: Aptamer against FGF-2 and use thereof",
            reference_titles="Aptamer against FGF-2 and use thereof",
        )
        assert ev.evidence_scope == "patent_claim_level"


def test_promoter_trim_proposed_not_applied():
    promo = "UAAUACGACUCACUAUA" + "ACGUACGUACGU"
    t = propose_promoter_trim(promo)
    assert t.promoter_trim_status == "proposed_for_review"
    assert t.possible_post_promoter_sequence == "ACGUACGUACGU"
    internal = "ACGU" + "UAAUACGACUCACUAUA" + "ACGU"
    t2 = propose_promoter_trim(internal)
    assert t2.promoter_trim_status == "unresolved"


def test_extracellular_domain_of_pap():
    r = repair_target_v2("extracellular domain of PAP")
    assert r.target_name == "PAP"
    assert "extracellular" in r.target_region.lower()
    assert r.target_type == "protein"


# ---------------------------------------------------------------------------
# Group-correction propagation (apply-group-review)
# ---------------------------------------------------------------------------


def _prov_row(accession: str, group_id: str, seq: str, target: str, ttype: str, **kwargs):
    row = {
        "review_unit_id": f"u_{accession}",
        "accession": accession,
        "experiment_group_id": group_id,
        "sequence_deposited": seq.replace("U", "T"),
        "rna_sequence": seq,
        "target_raw": target,
        "target_name": target,
        "target_display_name": target,
        "target_comparison_key": normalize_target_comparison_key(target) if target else "UNKNOWN",
        "target_region": "",
        "target_type": ttype,
        "target_repair_reason": "",
        "description": kwargs.get("description", f"aptamer for {target}"),
        "reference": kwargs.get("reference", ""),
        "binding_evidence_type": "target_specific_aptamer_claim",
        "binding_evidence_strength": "weak",
        "evidence_scope": "patent_claim_level",
        "evidence_repair_reason": "",
        "selection_evidence": "",
        "sequence_role": "likely_full_aptamer_sequence",
        "sequence_quality_status": "concrete_candidate_sequence",
        "ambiguity_symbols": "",
        "ambiguous_base_count": "0",
        "longest_ambiguous_run": "0",
        "promoter_trim_status": "",
        "possible_post_promoter_sequence": "",
        "source_candidate_tier": "Tier_B_plausible_needs_review",
        "review_unit_id_v1": f"v1_{accession}",
    }
    row.update(kwargs)
    return row


def test_blank_target_corrected_to_phospholamban(tmp_path: Path):
    seq = "ACGUACGUACGUACGUACGUACGUACGUACGU"
    prov = pd.DataFrame([_prov_row("P1", "g_phos", seq, "", "unknown", description="phospholamban-targeted")])
    # blank display
    prov.loc[0, "target_display_name"] = ""
    prov.loc[0, "target_comparison_key"] = "UNKNOWN"
    prov.to_csv(tmp_path / "ena_sequence_review_provenance_all.csv", index=False)
    group = pd.DataFrame(
        {
            "manual_group_include": ["1"],
            "manual_target_corrected": ["phospholamban"],
            "manual_target_type_corrected": ["protein"],
            "experiment_group_id": ["g_phos"],
            "target_display_name": [""],
            "target_type": ["unknown"],
        }
    )
    group.to_csv(tmp_path / "groups.csv", index=False)
    run_apply_group_review(tmp_path / "groups.csv", tmp_path)
    seq_t = pd.read_csv(tmp_path / "ena_sequence_review_template.csv", dtype=str).fillna("")
    assert list(seq_t["target_display_name"]) == ["phospholamban"]
    assert list(seq_t["target_type"]) == ["protein"]
    assert (seq_t["manual_include"] == "").all()


def test_blank_target_corrected_to_human_cyclin_t1(tmp_path: Path):
    seq = "GCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGC"
    prov = pd.DataFrame([_prov_row("C1", "g_cyc", seq, "", "unknown")])
    prov.loc[0, "target_display_name"] = ""
    prov.loc[0, "target_comparison_key"] = "UNKNOWN"
    prov.to_csv(tmp_path / "ena_sequence_review_provenance_all.csv", index=False)
    group = pd.DataFrame(
        {
            "manual_group_include": ["1"],
            "manual_target_corrected": ["Human cyclin T1"],
            "manual_target_type_corrected": ["protein"],
            "experiment_group_id": ["g_cyc"],
            "target_display_name": [""],
            "target_type": ["unknown"],
        }
    )
    group.to_csv(tmp_path / "groups.csv", index=False)
    run_apply_group_review(tmp_path / "groups.csv", tmp_path)
    seq_t = pd.read_csv(tmp_path / "ena_sequence_review_template.csv", dtype=str).fillna("")
    assert "cyclin" in seq_t.iloc[0]["target_display_name"].lower()
    assert seq_t.iloc[0]["target_type"] == "protein"


def test_tst56_tsg56_become_tsa56_and_cross_patent_dedup(tmp_path: Path):
    seq = "GGAGAGCGGAAGCGUGCUGGGCC" + "ACGUACGUACGUACGU"
    assert normalize_target_comparison_key("TST56") == normalize_target_comparison_key("TSA56")
    assert normalize_target_comparison_key("TSG56") == normalize_target_comparison_key("TSA56")
    prov = pd.DataFrame(
        [
            _prov_row("T1", "g_tst", seq, "TST56", "protein"),
            _prov_row("T2", "g_tsg", seq, "TSG56", "protein"),
            _prov_row("T3", "g_tsa", seq, "TSA56", "protein"),
        ]
    )
    prov.to_csv(tmp_path / "ena_sequence_review_provenance_all.csv", index=False)
    group = pd.DataFrame(
        {
            "manual_group_include": ["1", "1", "1"],
            "manual_target_corrected": ["TSA56", "TSA56", ""],
            "manual_target_type_corrected": ["", "", ""],
            "experiment_group_id": ["g_tst", "g_tsg", "g_tsa"],
            "target_display_name": ["TST56", "TSG56", "TSA56"],
            "target_type": ["protein", "protein", "protein"],
        }
    )
    group.to_csv(tmp_path / "groups.csv", index=False)
    run_apply_group_review(tmp_path / "groups.csv", tmp_path)
    seq_t = pd.read_csv(tmp_path / "ena_sequence_review_template.csv", dtype=str).fillna("")
    assert len(seq_t) == 1
    assert seq_t.iloc[0]["target_display_name"] == "TSA56"
    assert int(seq_t.iloc[0]["accession_count"]) == 3
    assert seq_t.iloc[0]["genuine_target_conflict"] == "0"
    prov_out = pd.read_csv(tmp_path / "ena_sequence_review_provenance.csv", dtype=str).fillna("")
    assert set(prov_out["accession"]) == {"T1", "T2", "T3"}
    conflicts_path = tmp_path / "ena_sequence_conflicts.csv"
    if conflicts_path.stat().st_size == 0:
        conflicts = pd.DataFrame()
    else:
        conflicts = pd.read_csv(conflicts_path, dtype=str).fillna("")
    assert len(conflicts) == 0


def test_chymase_unknown_becomes_chymase_enzyme(tmp_path: Path):
    seq = "AUGCAUGCAUGCAUGCAUGCAUGCAUGCAUGC"
    prov = pd.DataFrame([_prov_row("CH1", "g_chy", seq, "unknown", "unknown")])
    prov.to_csv(tmp_path / "ena_sequence_review_provenance_all.csv", index=False)
    group = pd.DataFrame(
        {
            "manual_group_include": ["1"],
            "manual_target_corrected": ["CHYMASE"],
            "manual_target_type_corrected": ["enzyme"],
            "experiment_group_id": ["g_chy"],
            "target_display_name": ["unknown"],
            "target_type": ["unknown"],
        }
    )
    group.to_csv(tmp_path / "groups.csv", index=False)
    run_apply_group_review(tmp_path / "groups.csv", tmp_path)
    seq_t = pd.read_csv(tmp_path / "ena_sequence_review_template.csv", dtype=str).fillna("")
    assert seq_t.iloc[0]["target_display_name"].upper() == "CHYMASE"
    assert seq_t.iloc[0]["target_type"] == "enzyme"


def test_rf1_type_only_enzyme_to_protein(tmp_path: Path):
    seq = "UUUUACGUACGUACGUACGUACGUACGUACGU"
    prov = pd.DataFrame(
        [_prov_row("R1", "g_rf1", seq, "E. Coli termination factor RF1", "enzyme")]
    )
    prov.to_csv(tmp_path / "ena_sequence_review_provenance_all.csv", index=False)
    group = pd.DataFrame(
        {
            "manual_group_include": ["1"],
            "manual_target_corrected": [""],
            "manual_target_type_corrected": ["protein"],
            "experiment_group_id": ["g_rf1"],
            "target_display_name": ["E. Coli termination factor RF1"],
            "target_type": ["enzyme"],
        }
    )
    group.to_csv(tmp_path / "groups.csv", index=False)
    run_apply_group_review(tmp_path / "groups.csv", tmp_path)
    seq_t = pd.read_csv(tmp_path / "ena_sequence_review_template.csv", dtype=str).fillna("")
    assert "RF1" in seq_t.iloc[0]["target_display_name"]
    assert seq_t.iloc[0]["target_type"] == "protein"


def test_target_conflicts_recomputed_after_corrections():
    seq = "ACGU" * 10
    acc = pd.DataFrame(
        [
            _acc(
                accession="A1",
                experiment_group_id="g1",
                rna_sequence=seq,
                is_concrete="1",
                contains_ambiguous_bases="0",
                ambiguous_base_count="0",
                ambiguity_symbols="",
                sequence_quality_status="concrete_candidate_sequence",
                target_raw="TST56",
                target_name="TST56",
                target_display_name="TST56",
                target_comparison_key=normalize_target_comparison_key("TST56"),
                target_type="protein",
            ),
            _acc(
                accession="A2",
                experiment_group_id="g2",
                rna_sequence=seq,
                is_concrete="1",
                contains_ambiguous_bases="0",
                ambiguous_base_count="0",
                ambiguity_symbols="",
                sequence_quality_status="concrete_candidate_sequence",
                target_raw="TSG56",
                target_name="TSG56",
                target_display_name="TSG56",
                target_comparison_key=normalize_target_comparison_key("TSG56"),
                target_type="protein",
                review_unit_id_v1="u2",
            ),
        ]
    )
    # After alias keying they share a key — apply corrections as apply-group would
    retained = pd.DataFrame(
        {
            "experiment_group_id": ["g1", "g2"],
            "target_display_name": ["TST56", "TSG56"],
            "target_type": ["protein", "protein"],
            "manual_target_corrected": ["TSA56", "TSA56"],
            "manual_target_type_corrected": ["", ""],
        }
    )
    corrected = apply_group_corrections_to_accessions(acc, retained)
    assert set(corrected["target_comparison_key"]) == {
        normalize_target_comparison_key("TSA56")
    }
    units, _, conflicts = consolidate_sequence_target_units(corrected)
    assert len(units) == 1
    assert units.iloc[0]["genuine_target_conflict"] == "0"
    assert len(conflicts) == 0


def test_validation_fails_when_correction_not_propagated():
    retained = pd.DataFrame(
        {
            "experiment_group_id": ["g1"],
            "target_display_name": [""],
            "target_type": ["unknown"],
            "manual_target_corrected": ["phospholamban"],
            "manual_target_type_corrected": ["protein"],
        }
    )
    # Template still has blank/unknown — should fail
    template = pd.DataFrame(
        {
            "experiment_group_id": ["g1"],
            "experiment_group_ids": ["g1"],
            "target_display_name": [""],
            "target_comparison_key": ["UNKNOWN"],
            "target_type": ["unknown"],
            "unresolved_target": ["0"],
        }
    )
    errors = validate_sequence_template_against_groups(template, retained)
    assert errors


def test_pdgf_group_not_assumed_vegf():
    """Composition mentioning a VEGF antagonist must not rewrite PDGF aptamer target."""
    grow = {
        "experiment_group_id": "experiment_a9a8323cf6",
        "target_display_name": "PDGF",
        "target_type": "protein",
        "manual_target_corrected": "",
        "manual_target_type_corrected": "",
        "representative_title": "COMPOSITIONS COMPRISING AN ANTI-PDGF APTAMER AND A VEGF ANTAGONIST",
    }
    display, ttype, _, _ = effective_group_target(grow)
    assert display == "PDGF"
    assert ttype == "protein"
    assert "VEGF" not in display


def test_genome_editing_enzyme_group_marked_unresolved():
    assert is_unresolved_effective_target(
        "genome editing enzyme", "experiment_00caf42363"
    )
    assert is_unresolved_effective_target("", "experiment_aa2c06865e")


def test_resolved_target_empty_comparison_key_falls_back_to_unknown():
    """Resolved and unresolved branches must share cmp_key or 'UNKNOWN'."""
    acc = pd.DataFrame(
        [
            {
                "accession": "A1",
                "experiment_group_id": "g1",
                "rna_sequence": "ACGU" * 8,
                "target_raw": "",
                "target_name": "",
                "target_display_name": "",
                "target_comparison_key": "",
                "target_type": "unknown",
                "target_region": "",
                "target_context": "",
                "target_repair_reason": "",
                "target_confidence": "low",
                "target_unresolved": "0",
                "manual_target_applied": "0",
                "manual_target_type_applied": "0",
                "unresolved_target": "0",
            }
        ]
    )
    # Punctuation-only display normalises to '' but is not flagged unresolved
    assert normalize_target_comparison_key("---") == ""
    assert not is_unresolved_effective_target("---")
    retained = pd.DataFrame(
        {
            "experiment_group_id": ["g1"],
            "target_display_name": ["---"],
            "target_type": ["protein"],
            "manual_target_corrected": ["---"],
            "manual_target_type_corrected": ["protein"],
        }
    )
    out = apply_group_corrections_to_accessions(acc, retained)
    assert out.iloc[0]["target_comparison_key"] == "UNKNOWN"
    assert out.iloc[0]["unresolved_target"] == "0"


def test_tyrosinase_and_gst_type_corrections(tmp_path: Path):
    seq1 = "AAAA" * 10
    seq2 = "CCCC" * 10
    prov = pd.DataFrame(
        [
            _prov_row("Y1", "g_tyr", seq1, "", "unknown"),
            _prov_row("G1", "g_gst", seq2, "Tansferase", "protein"),
        ]
    )
    prov.loc[0, "target_display_name"] = ""
    prov.loc[0, "target_comparison_key"] = "UNKNOWN"
    prov.to_csv(tmp_path / "ena_sequence_review_provenance_all.csv", index=False)
    group = pd.DataFrame(
        {
            "manual_group_include": ["1", "1"],
            "manual_target_corrected": ["TYROSINASE", "glutathione S-transferase"],
            "manual_target_type_corrected": ["enzyme", "enzyme"],
            "experiment_group_id": ["g_tyr", "g_gst"],
            "target_display_name": ["", "Tansferase"],
            "target_type": ["unknown", "protein"],
        }
    )
    group.to_csv(tmp_path / "groups.csv", index=False)
    run_apply_group_review(tmp_path / "groups.csv", tmp_path)
    seq_t = pd.read_csv(tmp_path / "ena_sequence_review_template.csv", dtype=str).fillna("")
    by_g = {r["experiment_group_id"]: r for _, r in seq_t.iterrows()}
    assert by_g["g_tyr"]["target_type"] == "enzyme"
    assert "TYROSINASE" in by_g["g_tyr"]["target_display_name"].upper()
    assert by_g["g_gst"]["target_type"] == "enzyme"
    assert "glutathione" in by_g["g_gst"]["target_display_name"].lower()


# ---------------------------------------------------------------------------
# Apply sequence-level review
# ---------------------------------------------------------------------------


def _seq_review_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "manual_include": "1",
        "manual_target_corrected": "",
        "manual_sequence_corrected": "",
        "manual_exclusion_reason": "",
        "manual_notes": "",
        "allow_ambiguous_include": "",
        "review_unit_id": "rev2_unit1",
        "experiment_group_id": "experiment_g1",
        "experiment_group_ids": "experiment_g1",
        "target_display_name": "VEGF",
        "target_comparison_key": "VEGF",
        "target_region": "",
        "target_type": "protein",
        "unresolved_target": "0",
        "rna_sequence": "ACGUACGUACGUACGUACGU",
        "sequence_length": "20",
        "sequence_quality_status": "concrete_candidate_sequence",
        "length_status": "20_to_120_typical_range",
        "near_duplicate_family_id": "",
        "near_duplicate_family_size": "",
        "accession_count": "1",
        "accessions": "ACC1",
        "binding_evidence_type": "explicit_binding_claim",
        "binding_evidence_strength": "moderate",
        "evidence_scope": "patent_claim_level",
        "representative_title": "Anti-VEGF aptamer",
        "automatic_concern_flags": "",
        "genuine_target_conflict": "0",
    }
    base.update(overrides)
    return base


def _write_seq_review(path: Path, rows: list[dict[str, object]]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _write_seq_provenance(path: Path, rows: list[dict[str, object]]) -> Path:
    if rows:
        pd.DataFrame(rows).to_csv(path, index=False)
    else:
        pd.DataFrame(columns=["review_unit_id", "accession"]).to_csv(path, index=False)
    return path


def _prov_for_unit(
    review_unit_id: str,
    accession: str,
    sequence: str = "ACGUACGUACGUACGUACGU",
    target: str = "VEGF",
) -> dict[str, object]:
    return {
        "review_unit_id": review_unit_id,
        "accession": accession,
        "experiment_group_id": "experiment_g1",
        "sequence_deposited": sequence.replace("U", "T"),
        "rna_sequence": sequence,
        "target_raw": target,
        "target_name": target,
        "target_display_name": target,
        "target_comparison_key": target.upper().replace("-", ""),
        "target_region": "",
        "target_type": "protein",
        "target_repair_reason": "",
        "unresolved_target": "0",
        "manual_target_applied": "0",
        "manual_target_type_applied": "0",
        "description": "desc",
        "reference": "ref",
        "binding_evidence_type": "explicit_binding_claim",
        "binding_evidence_strength": "moderate",
        "evidence_scope": "patent_claim_level",
        "evidence_repair_reason": "",
        "selection_evidence": "SELEX",
        "sequence_role": "aptamer",
        "sequence_quality_status": "concrete_candidate_sequence",
        "ambiguity_symbols": "",
        "ambiguous_base_count": "0",
        "longest_ambiguous_run": "0",
        "promoter_trim_status": "",
        "possible_post_promoter_sequence": "",
        "source_candidate_tier": "1",
        "review_unit_id_v1": "",
    }


def test_apply_sequence_review_exports_accepted_rejected_unreviewed(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [
            _seq_review_row(review_unit_id="u_acc", manual_include="1", accessions="A1"),
            _seq_review_row(
                review_unit_id="u_rej",
                manual_include="0",
                rna_sequence="GGGG",
                accessions="A2",
                manual_exclusion_reason="non_protein",
            ),
            _seq_review_row(
                review_unit_id="u_blank",
                manual_include="",
                rna_sequence="CCCCACGUACGUACGUACGU",
                accessions="A3",
            ),
        ],
    )
    _write_seq_provenance(
        tmp_path / "ena_sequence_review_provenance.csv",
        [
            _prov_for_unit("u_acc", "A1"),
            _prov_for_unit("u_rej", "A2", sequence="GGGG"),
            _prov_for_unit("u_blank", "A3", sequence="CCCCACGUACGUACGUACGU"),
        ],
    )
    summary = run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert summary["accepted_unique_pairs"] == 1
    assert summary["rejected"] == 1
    assert summary["unreviewed"] == 1

    sel = pd.read_csv(tmp_path / "ena_selected_after_manual_review.csv", dtype=str)
    assert len(sel) == 1
    assert sel.iloc[0]["sequence"] == "ACGUACGUACGUACGUACGU"
    assert sel.iloc[0]["target"] == "VEGF"
    assert sel.iloc[0]["source_database"] == "ENA"

    rej = pd.read_csv(tmp_path / "ena_rejected_after_manual_review.csv", dtype=str)
    assert len(rej) == 1
    assert rej.iloc[0]["review_unit_id"] == "u_rej"
    assert rej.iloc[0]["manual_exclusion_reason"] == "non_protein"

    unrev = pd.read_csv(tmp_path / "ena_unreviewed_after_manual_review.csv", dtype=str)
    assert len(unrev) == 1
    assert unrev.iloc[0]["review_unit_id"] == "u_blank"


def test_apply_sequence_review_invalid_decision_fails(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [_seq_review_row(manual_include="yes")],
    )
    with pytest.raises(ReviewValidationError) as exc:
        run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert "yes" in str(exc.value)
    assert "manual_include" in str(exc.value)


def test_apply_sequence_review_duplicate_review_unit_id_fails(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [
            _seq_review_row(review_unit_id="dup"),
            _seq_review_row(review_unit_id="dup", rna_sequence="GGGUACGUACGUACGUACGU"),
        ],
    )
    with pytest.raises(ReviewValidationError) as exc:
        run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert "duplicate review_unit_id" in str(exc.value)


def test_apply_sequence_review_corrected_target_and_sequence(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [
            _seq_review_row(
                review_unit_id="u_corr",
                manual_target_corrected="VEGF-A",
                manual_sequence_corrected="  acgu acgu\nacguacguacgu  ",
                target_display_name="VEGF",
                rna_sequence="GGGGACGUACGUACGUACGU",
                accessions="A1",
            )
        ],
    )
    _write_seq_provenance(
        tmp_path / "ena_sequence_review_provenance.csv",
        [_prov_for_unit("u_corr", "A1")],
    )
    run_apply_sequence_review(review, tmp_path, overwrite=True)
    sel = pd.read_csv(tmp_path / "ena_selected_after_manual_review.csv", dtype=str)
    assert sel.iloc[0]["target"] == "VEGF-A"
    assert sel.iloc[0]["sequence"] == "ACGUACGUACGUACGUACGU"
    assert sel.iloc[0]["sequence_corrected_applied"] == "1"
    assert sel.iloc[0]["target_corrected_applied"] == "1"


def test_apply_sequence_review_ambiguous_requires_override(tmp_path: Path):
    amb_seq = "ACGUACGUACGUACGUACGN"
    review = _write_seq_review(
        tmp_path / "review.csv",
        [
            _seq_review_row(
                review_unit_id="u_amb",
                rna_sequence=amb_seq,
                allow_ambiguous_include="",
            )
        ],
    )
    with pytest.raises(ReviewValidationError) as exc:
        run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert "ambiguity" in str(exc.value).lower()

    review2 = _write_seq_review(
        tmp_path / "review2.csv",
        [
            _seq_review_row(
                review_unit_id="u_amb2",
                rna_sequence=amb_seq,
                allow_ambiguous_include="1",
            )
        ],
    )
    _write_seq_provenance(
        tmp_path / "ena_sequence_review_provenance.csv",
        [_prov_for_unit("u_amb2", "ACC1", sequence=amb_seq)],
    )
    summary = run_apply_sequence_review(review2, tmp_path, overwrite=True)
    assert summary["accepted_unique_pairs"] == 1
    assert summary["ambiguous_overrides"] == 1


def test_apply_sequence_review_non_iupac_fails(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [_seq_review_row(rna_sequence="ACGUACGUACGUACGUACGX")],
    )
    with pytest.raises(ReviewValidationError) as exc:
        run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert "non-IUPAC" in str(exc.value)


def test_apply_sequence_review_missing_target_fails(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [
            _seq_review_row(
                target_display_name="unknown",
                manual_target_corrected="",
            )
        ],
    )
    with pytest.raises(ReviewValidationError) as exc:
        run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert "target" in str(exc.value).lower()


def test_apply_sequence_review_consolidates_exact_duplicates(tmp_path: Path):
    seq = "ACGUACGUACGUACGUACGU"
    review = _write_seq_review(
        tmp_path / "review.csv",
        [
            _seq_review_row(
                review_unit_id="u1",
                rna_sequence=seq,
                accessions="A1",
                experiment_group_id="g1",
                experiment_group_ids="g1",
                target_display_name="FGF2",
            ),
            _seq_review_row(
                review_unit_id="u2",
                rna_sequence=seq,
                accessions="A2|A3",
                experiment_group_id="g2",
                experiment_group_ids="g2",
                target_display_name="FGF-2",
            ),
        ],
    )
    _write_seq_provenance(
        tmp_path / "ena_sequence_review_provenance.csv",
        [
            _prov_for_unit("u1", "A1", sequence=seq, target="FGF2"),
            _prov_for_unit("u2", "A2", sequence=seq, target="FGF-2"),
            _prov_for_unit("u2", "A3", sequence=seq, target="FGF-2"),
        ],
    )
    summary = run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert summary["accepted_before_consolidation"] == 2
    assert summary["accepted_unique_pairs"] == 1
    assert summary["duplicate_consolidations"] == 1
    sel = pd.read_csv(tmp_path / "ena_selected_after_manual_review.csv", dtype=str)
    assert len(sel) == 1
    ids = set(sel.iloc[0]["review_unit_ids"].split("|"))
    assert ids == {"u1", "u2"}
    accs = set(sel.iloc[0]["accessions"].split("|"))
    assert accs == {"A1", "A2", "A3"}
    prov = pd.read_csv(tmp_path / "ena_selected_sequence_provenance.csv", dtype=str)
    assert set(prov["accession"]) == {"A1", "A2", "A3"}
    assert set(prov["review_unit_id"]) == {"u1", "u2"}


def test_consolidate_accepted_pairs_sorts_sequence_length_numerically():
    short = "ACGUACGUACGU"
    mid = "ACGU" * 5  # 20
    long = "ACGU" * 25  # 100
    accepted = pd.DataFrame(
        [
            _seq_review_row(
                review_unit_id="long",
                rna_sequence=long,
                target_display_name="VEGF",
                sequence_length=str(len(long)),
            ),
            _seq_review_row(
                review_unit_id="short",
                rna_sequence=short,
                target_display_name="VEGF",
                sequence_length=str(len(short)),
            ),
            _seq_review_row(
                review_unit_id="mid",
                rna_sequence=mid,
                target_display_name="VEGF",
                sequence_length=str(len(mid)),
            ),
        ]
    )
    selected, _ = consolidate_accepted_pairs(accepted)
    assert selected["sequence_length"].tolist() == ["12", "20", "100"]
    assert selected["review_unit_id"].tolist() == ["short", "mid", "long"]


def test_apply_sequence_review_rejected_need_not_have_valid_sequence(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [
            _seq_review_row(
                review_unit_id="u_bad",
                manual_include="0",
                rna_sequence="!!!",
                manual_exclusion_reason="",
            )
        ],
    )
    _write_seq_provenance(tmp_path / "ena_sequence_review_provenance.csv", [])
    summary = run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert summary["rejected"] == 1
    assert summary["accepted_unique_pairs"] == 0


def test_apply_sequence_review_blank_not_treated_as_rejected(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [_seq_review_row(review_unit_id="u_open", manual_include="")],
    )
    _write_seq_provenance(tmp_path / "ena_sequence_review_provenance.csv", [])
    summary = run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert summary["unreviewed"] == 1
    assert summary["rejected"] == 0
    unrev = pd.read_csv(tmp_path / "ena_unreviewed_after_manual_review.csv", dtype=str)
    rej = pd.read_csv(tmp_path / "ena_rejected_after_manual_review.csv", dtype=str)
    assert len(unrev) == 1
    assert len(rej) == 0


def test_apply_sequence_review_reports_missing_provenance(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [_seq_review_row(review_unit_id="u_missing", accessions="A9")],
    )
    _write_seq_provenance(tmp_path / "ena_sequence_review_provenance.csv", [])
    summary = run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert summary["provenance_missing"] == 1
    qc = (tmp_path / "ena_apply_sequence_review_qc_report.md").read_text(encoding="utf-8")
    assert "u_missing" in qc
    assert "missing or unmatched provenance" in qc.lower()


def test_apply_sequence_review_refuses_overwrite_without_flag(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [_seq_review_row(review_unit_id="u1")],
    )
    _write_seq_provenance(
        tmp_path / "ena_sequence_review_provenance.csv",
        [_prov_for_unit("u1", "ACC1")],
    )
    run_apply_sequence_review(review, tmp_path, overwrite=True)
    with pytest.raises(FileExistsError):
        run_apply_sequence_review(review, tmp_path, overwrite=False)


def test_apply_sequence_review_no_internet(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [_seq_review_row(review_unit_id="u_offline")],
    )
    _write_seq_provenance(
        tmp_path / "ena_sequence_review_provenance.csv",
        [_prov_for_unit("u_offline", "ACC1")],
    )

    def _deny(*_a, **_k):
        raise AssertionError("network access attempted")

    with patch.object(socket, "create_connection", side_effect=_deny):
        summary = run_apply_sequence_review(review, tmp_path, overwrite=True)
    assert summary["accepted_unique_pairs"] == 1


def test_cli_exposes_apply_sequence_review():
    parser = build_parser()
    args = parser.parse_args(
        [
            "apply-sequence-review",
            "--sequence-review-file",
            "x.csv",
            "--output-dir",
            "out",
            "--overwrite",
        ]
    )
    assert args.command == "apply-sequence-review"
    assert args.overwrite is True


def test_apply_sequence_review_qc_report_counts(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [
            _seq_review_row(review_unit_id="a1", manual_include="1", accessions="A1"),
            _seq_review_row(
                review_unit_id="r1",
                manual_include="0",
                rna_sequence="GGGG",
                accessions="A2",
                manual_exclusion_reason="too_short",
            ),
            _seq_review_row(
                review_unit_id="b1",
                manual_include="",
                rna_sequence="CCCCACGUACGUACGUACGU",
                accessions="A3",
            ),
        ],
    )
    _write_seq_provenance(
        tmp_path / "ena_sequence_review_provenance.csv",
        [_prov_for_unit("a1", "A1")],
    )
    run_apply_sequence_review(review, tmp_path, overwrite=True)
    qc = (tmp_path / "ena_apply_sequence_review_qc_report.md").read_text(encoding="utf-8")
    assert "| total sequence-review rows | 3 |" in qc
    assert "| accepted rows before exact consolidation | 1 |" in qc
    assert "| final accepted unique sequence–target pairs | 1 |" in qc
    assert "| rejected rows | 1 |" in qc
    assert "| unreviewed rows | 1 |" in qc


def test_derive_effective_helpers():
    row = {
        "manual_sequence_corrected": " ac gu ",
        "rna_sequence": "AAAA",
        "manual_target_corrected": "PAP",
        "target_display_name": "prostatic acid phosphatase",
    }
    seq, seq_corr = derive_effective_sequence(row)
    tgt, tgt_corr = derive_effective_target(row)
    assert seq == "ACGU"
    assert seq_corr is True
    assert tgt == "PAP"
    assert tgt_corr is True


def test_main_apply_sequence_review_cli(tmp_path: Path):
    review = _write_seq_review(
        tmp_path / "review.csv",
        [_seq_review_row(review_unit_id="cli1")],
    )
    _write_seq_provenance(
        tmp_path / "ena_sequence_review_provenance.csv",
        [_prov_for_unit("cli1", "ACC1")],
    )
    rc = main(
        [
            "apply-sequence-review",
            "--sequence-review-file",
            str(tmp_path / "review.csv"),
            "--output-dir",
            str(tmp_path),
            "--overwrite",
        ]
    )
    assert rc == 0
    assert (tmp_path / "ena_selected_after_manual_review.csv").exists()

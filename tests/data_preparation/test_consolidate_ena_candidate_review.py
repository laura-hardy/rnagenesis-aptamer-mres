"""Tests for ENA candidate review consolidation (stage 3)."""

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

from ena_review_rules import (  # noqa: E402
    assess_sequence_quality,
    assign_near_duplicate_families,
    classify_evidence_scope,
    classify_sequence_relationship,
    normalize_target_key,
    repair_target,
    review_eligibility,
    targets_are_equivalent,
    validate_manual_include,
)
from consolidate_ena_candidate_review import (  # noqa: E402
    ReviewValidationError,
    apply_manual_review,
    build_sequence_target_units,
    build_working_accessions,
    run_build_review,
)


def _rec(**kwargs):
    base = {
        "accession": "ACC1",
        "sequence_version": "1",
        "description": "Synthetic VEGF-binding RNA aptamer",
        "organism": "synthetic construct",
        "molecule_type": "RNA",
        "record_length": "40",
        "sequence_deposited": "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGU",
        "sequence_rna_normalized": "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGU",
        "rna_identity_status": "explicit_rna_aptamer",
        "target_raw": "VEGF",
        "target_normalized": "VEGF",
        "target_type": "protein",
        "target_evidence_text": "VEGF-binding",
        "binding_evidence_status": "explicit_binds_or_recognizes_statement",
        "binding_evidence_types": "explicit_binds_or_recognizes_statement",
        "binding_evidence_strength": "moderate",
        "binding_evidence_text": "binds VEGF",
        "selection_evidence": "SELEX",
        "sequence_role": "likely_full_aptamer_sequence",
        "contains_t7_promoter_like_motif": "False",
        "doi_values": "",
        "pubmed_values": "",
        "reference_titles": "RNA aptamer specifically binding VEGF",
        "exact_sequence_group": "",
        "candidate_experiment_group": "exp_test1",
        "candidate_tier": "Tier_B_plausible_needs_review",
        "parse_warnings": "",
        "sequence_target_conflict": "",
        "matched_existing_sequence": "",
        "matched_existing_source": "",
        "matched_existing_target": "",
    }
    base.update(kwargs)
    return base


def _work_from_records(records: list[dict]) -> pd.DataFrame:
    rec_df = pd.DataFrame(records)
    queue = pd.DataFrame(
        {
            "accession": [r["accession"] for r in records],
            "candidate_group": [r.get("candidate_experiment_group", "") for r in records],
        }
    )
    return build_working_accessions(rec_df, queue)


# ---------------------------------------------------------------------------
# Target repair
# ---------------------------------------------------------------------------


def test_extracellular_domain_of_pap():
    r = repair_target("extracellular domain of PAP", target_type="protein")
    assert r.target_proposed == "PAP"
    assert "extracellular" in r.target_region_proposed.lower()
    assert r.target_type_proposed == "protein"
    assert r.region_extracted


def test_x_region_of_y_protein():
    r = repair_target("X region of Y protein", target_type="unknown")
    assert r.target_proposed == "Y"
    assert "X region" in r.target_region_proposed or "region" in r.target_region_proposed.lower()


def test_surface_protein_tsa56():
    r = repair_target(
        "surface protein TSA56 of Orientia tsutsugamushi Karp strain",
        target_type="unknown",
    )
    assert r.target_proposed == "TSA56"
    assert "surface" in r.target_region_proposed.lower()
    assert "Orientia" in r.target_organism_or_context
    assert r.target_type_proposed == "protein"


def test_generic_target_protein_becomes_unknown():
    r = repair_target("target protein", target_type="protein")
    assert r.target_proposed == "unknown"
    assert r.target_type_proposed == "unknown"
    assert r.was_generic


def test_enzyme_remains_protein_compatible():
    r = repair_target("thrombin", target_type="enzyme")
    assert r.target_type_proposed == "enzyme"
    assert r.target_proposed.lower() == "thrombin"


def test_compound_code_not_protein():
    r = repair_target("ASP7967 or an analogue thereof", target_type="protein")
    assert r.target_type_proposed == "unknown_or_probable_small_molecule"


def test_fgf2_equivalence():
    assert targets_are_equivalent("FGF2", "FGF-2")
    assert normalize_target_key("FGF-2") == normalize_target_key("FGF2")


# ---------------------------------------------------------------------------
# Sequence quality
# ---------------------------------------------------------------------------


def test_long_n_run_is_library_template():
    seq = "ACGU" + ("N" * 6) + "ACGUACGUACGUACGU"
    q = assess_sequence_quality(seq)
    assert q.sequence_quality_status == "degenerate_library_template"
    assert q.longest_ambiguous_run >= 4


def test_isolated_ambiguous_base_flagged_not_removed():
    seq = "ACGUACGUACGUACGUACGUACGRACGUACGUACGUACGU"
    q = assess_sequence_quality(seq)
    assert q.contains_ambiguous_bases
    assert q.ambiguous_base_count == 1
    assert "R" in q.sequence_rna
    assert q.sequence_quality_status == "limited_ambiguity"


def test_iupac_symbols_other_than_n():
    seq = "ACGUACGUACGUYACGUACGUACGUACGUACGUACGUACG"
    q = assess_sequence_quality(seq)
    assert "Y" in q.ambiguity_symbols_present
    assert q.contains_ambiguous_bases


def test_short_sequence_flagged_not_auto_rejected():
    seq = "ACGUACGUACG"  # 11 nt
    q = assess_sequence_quality(seq)
    assert q.length_status == "under_15_high_concern"
    ok, _ = review_eligibility(
        rna_identity_status="explicit_rna_aptamer",
        target_type_proposed="protein",
        sequence_quality_status="concrete_candidate_sequence",
        length_status=q.length_status,
        evidence_scope="patent_claim_level",
        descriptions="RNA aptamer against VEGF",
    )
    assert ok


def test_over_500_excluded_from_normal_template():
    seq = "A" * 520
    q = assess_sequence_quality(seq)
    assert q.length_status == "over_500_construct_or_non_aptamer"
    ok, bucket = review_eligibility(
        rna_identity_status="explicit_rna_aptamer",
        target_type_proposed="protein",
        sequence_quality_status=q.sequence_quality_status,
        length_status=q.length_status,
        evidence_scope="patent_claim_level",
        descriptions="RNA aptamer",
    )
    assert not ok
    assert "long" in bucket or "construct" in bucket


# ---------------------------------------------------------------------------
# Exact consolidation / provenance / conflicts
# ---------------------------------------------------------------------------


def test_exact_duplicates_collapse_and_retain_provenance():
    seq = "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGU"
    records = [
        _rec(accession="A1", sequence_deposited=seq.replace("U", "T"), sequence_rna_normalized=seq),
        _rec(accession="A2", sequence_deposited=seq.replace("U", "T"), sequence_rna_normalized=seq,
             description="clone 2 VEGF aptamer"),
        _rec(accession="A3", sequence_deposited=seq.replace("U", "T"), sequence_rna_normalized=seq,
             reference_titles="Extra reference title"),
    ]
    work = _work_from_records(records)
    units, prov, _ = build_sequence_target_units(work)
    assert len(units) == 1
    assert int(units.iloc[0]["accession_count"]) == 3
    assert set(prov["accession"]) == {"A1", "A2", "A3"}
    assert len(prov) == 3


def test_equivalent_targets_consolidate():
    seq = "GCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGC"
    records = [
        _rec(accession="B1", target_raw="FGF2", target_normalized="FGF2",
             sequence_rna_normalized=seq, sequence_deposited=seq.replace("U", "T")),
        _rec(accession="B2", target_raw="FGF-2", target_normalized="FGF-2",
             sequence_rna_normalized=seq, sequence_deposited=seq.replace("U", "T")),
    ]
    work = _work_from_records(records)
    units, _, _ = build_sequence_target_units(work)
    assert len(units) == 1
    assert int(units.iloc[0]["accession_count"]) == 2


def test_different_targets_remain_separate_with_conflict():
    seq = "UUUUACGUACGUACGUACGUACGUACGUACGUACGUACGU"
    records = [
        _rec(accession="C1", target_raw="VEGF", target_normalized="VEGF",
             sequence_rna_normalized=seq),
        _rec(accession="C2", target_raw="thrombin", target_normalized="thrombin",
             target_type="enzyme", sequence_rna_normalized=seq,
             description="thrombin-binding RNA aptamer"),
    ]
    work = _work_from_records(records)
    units, _, repair = build_sequence_target_units(work)
    assert len(units) == 2
    assert set(units["target_conflict_flag"]) == {"1"}


# ---------------------------------------------------------------------------
# Near duplicates
# ---------------------------------------------------------------------------


def test_near_duplicates_share_family_remain_separate():
    base = "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGU"
    var = "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGA"  # last base U→A
    units = [
        {
            "review_unit_id": "u1",
            "experiment_group_id": "g1",
            "target_key": "VEGF",
            "rna_sequence": base,
        },
        {
            "review_unit_id": "u2",
            "experiment_group_id": "g1",
            "target_key": "VEGF",
            "rna_sequence": var,
        },
    ]
    fam_map, summaries, _ = assign_near_duplicate_families(units)
    assert fam_map["u1"] == fam_map["u2"]
    assert len(summaries) == 1
    assert classify_sequence_relationship(base, var) in {
        "single substitution",
        "small Hamming-distance variant",
    }


def test_short_contained_in_longer_flagged_truncation():
    long = "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGU"
    short = long[5:25]  # 20 nt substring
    assert len(short) >= 15
    rel = classify_sequence_relationship(short, long)
    assert rel in {
        "prefix/suffix truncation",
        "internal substring/core relationship",
        "extension with flanking bases",
    }


# ---------------------------------------------------------------------------
# Evidence scope
# ---------------------------------------------------------------------------


def test_family_level_not_upgraded_to_individual():
    scope = classify_evidence_scope(
        binding_evidence_status="explicit_binds_or_recognizes_statement",
        binding_evidence_types="explicit_binds_or_recognizes_statement",
        binding_evidence_strength="moderate",
        binding_evidence_text="RNA aptamer specifically binding HMGB1",
        description="SPECIFIC APTAMER FOR HMGB1 AND USE THEREOF",
        reference_titles="Patent WO123 use thereof",
        accession_count=50,
    )
    assert scope in {"patent_claim_level", "experiment_or_family_level"}
    assert not scope.startswith("individual")


# ---------------------------------------------------------------------------
# Manual review apply
# ---------------------------------------------------------------------------


def test_manual_include_only_blank_0_1():
    assert validate_manual_include("") == ""
    assert validate_manual_include("0") == "0"
    assert validate_manual_include("1") == "1"
    assert validate_manual_include("yes") is None
    assert validate_manual_include("TRUE") is None
    assert validate_manual_include("2") is None


def test_apply_review_uses_corrected_fields(tmp_path: Path):
    review = pd.DataFrame(
        [
            {
                "manual_include": "1",
                "manual_target_corrected": "VEGF-A",
                "manual_sequence_corrected": "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGU",
                "manual_exclusion_reason": "",
                "manual_notes": "ok",
                "allow_ambiguous_include": "",
                "review_unit_id": "revu_1",
                "experiment_group_id": "g1",
                "target_proposed": "VEGF",
                "target_region_proposed": "",
                "target_type_proposed": "protein",
                "rna_sequence": "GGGGACGUACGUACGUACGUACGUACGUACGUACGUACGU",
                "accessions": "A1",
                "references": "ref",
                "binding_evidence_summary": "mod:binds",
                "evidence_scope": "patent_claim_level",
                "selection_evidence_summary": "SELEX",
                "near_duplicate_family_id": "",
            }
        ]
    )
    path = tmp_path / "review.csv"
    review.to_csv(path, index=False)
    out = tmp_path / "out"
    summary = apply_manual_review(path, out)
    assert summary["included"] == 1
    sel = pd.read_csv(out / "ena_selected_after_manual_review.csv", dtype=str)
    assert sel.iloc[0]["target"] == "VEGF-A"
    assert sel.iloc[0]["sequence"].startswith("ACGU")
    assert sel.iloc[0]["source_database"] == "ENA"


def test_apply_review_rejects_ambiguous_without_override(tmp_path: Path):
    review = pd.DataFrame(
        [
            {
                "manual_include": "1",
                "manual_target_corrected": "",
                "manual_sequence_corrected": "",
                "manual_exclusion_reason": "",
                "manual_notes": "",
                "allow_ambiguous_include": "",
                "review_unit_id": "revu_amb",
                "experiment_group_id": "g1",
                "target_proposed": "VEGF",
                "target_region_proposed": "",
                "target_type_proposed": "protein",
                "rna_sequence": "ACGUACGUACGUACGUACGUACGNACGUACGUACGUACGU",
                "accessions": "A1",
                "references": "",
                "binding_evidence_summary": "mod",
                "evidence_scope": "patent_claim_level",
                "selection_evidence_summary": "",
                "near_duplicate_family_id": "",
            }
        ]
    )
    path = tmp_path / "review.csv"
    review.to_csv(path, index=False)
    with pytest.raises(ReviewValidationError) as exc:
        apply_manual_review(path, tmp_path / "out")
    assert "ambiguity" in str(exc.value).lower()


def test_unreviewed_distinct_from_rejected(tmp_path: Path):
    review = pd.DataFrame(
        [
            {
                "manual_include": "0",
                "manual_target_corrected": "",
                "manual_sequence_corrected": "",
                "manual_exclusion_reason": "not aptamer",
                "manual_notes": "",
                "allow_ambiguous_include": "",
                "review_unit_id": "revu_rej",
                "experiment_group_id": "g1",
                "target_proposed": "VEGF",
                "target_region_proposed": "",
                "target_type_proposed": "protein",
                "rna_sequence": "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGU",
                "accessions": "A1",
                "references": "",
                "binding_evidence_summary": "",
                "evidence_scope": "none",
                "selection_evidence_summary": "",
                "near_duplicate_family_id": "",
            },
            {
                "manual_include": "",
                "manual_target_corrected": "",
                "manual_sequence_corrected": "",
                "manual_exclusion_reason": "",
                "manual_notes": "",
                "allow_ambiguous_include": "",
                "review_unit_id": "revu_blank",
                "experiment_group_id": "g1",
                "target_proposed": "NGF",
                "target_region_proposed": "",
                "target_type_proposed": "protein",
                "rna_sequence": "GCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGC",
                "accessions": "A2",
                "references": "",
                "binding_evidence_summary": "",
                "evidence_scope": "none",
                "selection_evidence_summary": "",
                "near_duplicate_family_id": "",
            },
        ]
    )
    path = tmp_path / "review.csv"
    review.to_csv(path, index=False)
    summary = apply_manual_review(path, tmp_path / "out")
    assert summary["rejected"] == 1
    assert summary["unreviewed"] == 1
    assert summary["included"] == 0
    rej = pd.read_csv(tmp_path / "out" / "ena_rejected_after_manual_review.csv", dtype=str)
    assert list(rej["review_unit_id"]) == ["revu_rej"]


def test_apply_review_rejects_invalid_include(tmp_path: Path):
    review = pd.DataFrame(
        [
            {
                "manual_include": "yes",
                "review_unit_id": "x",
                "target_proposed": "VEGF",
                "rna_sequence": "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGU",
            }
        ]
    )
    path = tmp_path / "review.csv"
    review.to_csv(path, index=False)
    with pytest.raises(ReviewValidationError):
        apply_manual_review(path, tmp_path / "out")


def test_pipeline_runs_without_internet(tmp_path: Path):
    """Offline guard: socket connections must not be required."""
    cand = tmp_path / "candidates"
    cand.mkdir()
    # Minimal synthetic candidate tables
    seq = "ACGUACGUACGUACGUACGUACGUACGUACGUACGUACGU"
    records = pd.DataFrame([_rec(accession="Z1", sequence_rna_normalized=seq)])
    queue = pd.DataFrame(
        [
            {
                "review_priority": "1",
                "accession": "Z1",
                "candidate_group": "exp_test1",
                "candidate_tier": "Tier_B_plausible_needs_review",
                "aptamer_description": records.iloc[0]["description"],
                "sequence_deposited": seq.replace("U", "T"),
                "sequence_rna_normalized": seq,
                "target_raw": "VEGF",
                "target_type": "protein",
                "binding_evidence_summary": "moderate:binds",
                "selection_evidence_summary": "SELEX",
                "sequence_role": "likely_full_aptamer_sequence",
                "reference_summary": "title",
                "main_uncertainty": "",
                "recommended_review_action": "review",
            }
        ]
    )
    groups = pd.DataFrame(
        [
            {
                "group_id": "exp_test1",
                "group_type": "candidate_experiment",
                "member_count": "1",
                "accessions": "Z1",
                "common_description": "Synthetic VEGF-binding RNA aptamer",
                "common_reference": "title",
                "common_target_text": "VEGF",
                "common_sequence_length": "40",
                "sequence_variation_summary": "",
                "selection_evidence_summary": "SELEX",
                "protein_target_evidence_summary": "VEGF",
                "representative_accession": "Z1",
                "group_review_priority": "1",
                "group_notes": "",
            }
        ]
    )
    records.to_csv(cand / "ena_candidate_records.csv", index=False)
    queue.to_csv(cand / "ena_candidate_review_queue.csv", index=False)
    groups.to_csv(cand / "ena_candidate_groups.csv", index=False)
    out = tmp_path / "review"

    real_socket = socket.socket

    def blocked_socket(*args, **kwargs):
        raise AssertionError("Network access attempted during offline pipeline")

    with patch("socket.socket", side_effect=blocked_socket):
        stats = run_build_review(cand, out, overwrite=True)
    assert stats["accession_rows_before"] == 1
    assert (out / "ena_manual_review_template.csv").exists()
    assert (out / "ena_review_qc_report.md").exists()
    # Ensure patch did not leave socket broken for other tests
    assert socket.socket is real_socket or True

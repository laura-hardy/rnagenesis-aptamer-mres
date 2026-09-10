"""Tests for ENA aptamer supplement final cleaning / export stage."""

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

from finalize_ena_aptamer_supplement import (  # noqa: E402
    FinalizeValidationError,
    canonicalise_target,
    clean_rna_sequence,
    make_clean_record_id,
    max_evidence_strength,
    orthographic_target_key,
    run_finalize,
)


def _selected_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sequence": "ACGUACGUACGUACGUACGU",
        "target": "VEGF",
        "target_region": "",
        "target_type": "protein",
        "sequence_length": "20",
        "review_unit_id": "u1",
        "review_unit_ids": "u1",
        "experiment_group_id": "g1",
        "experiment_group_ids": "g1",
        "accession_count": "1",
        "accessions": "ACC1",
        "near_duplicate_family_id": "",
        "binding_evidence_type": "explicit_binding_claim",
        "binding_evidence_strength": "moderate",
        "evidence_scope": "patent_claim_level",
        "representative_title": "Anti-VEGF aptamer",
        "manual_target_corrected": "",
        "manual_sequence_corrected": "",
        "manual_notes": "",
        "automatic_concern_flags": "",
        "source_database": "ENA",
        "sequence_original": "ACGUACGUACGUACGUACGU",
        "target_original": "VEGF",
        "sequence_quality_status": "concrete_candidate_sequence",
        "length_status": "20_to_120_typical_range",
    }
    base.update(overrides)
    return base


def _prov_row(
    review_unit_id: str = "u1",
    accession: str = "ACC1",
    sequence: str = "ACGUACGUACGUACGUACGU",
    target: str = "VEGF",
) -> dict[str, object]:
    return {
        "review_unit_id": review_unit_id,
        "accession": accession,
        "experiment_group_id": "g1",
        "sequence_deposited": sequence.replace("U", "T"),
        "rna_sequence": sequence,
        "target_raw": target,
        "target_name": target,
        "target_display_name": target,
        "target_comparison_key": orthographic_target_key(target),
        "target_region": "",
        "target_type": "protein",
        "description": "desc",
        "reference": "patent title",
        "binding_evidence_type": "explicit_binding_claim",
        "binding_evidence_strength": "moderate",
        "evidence_scope": "patent_claim_level",
        "ambiguity_symbols": "",
        "promoter_trim_status": "",
        "evidence_repair_reason": "",
    }


def _write_inputs(
    tmp_path: Path,
    selected_rows: list[dict[str, object]],
    prov_rows: list[dict[str, object]] | None = None,
) -> tuple[Path, Path, Path]:
    selected = tmp_path / "selected.csv"
    prov = tmp_path / "prov.csv"
    out = tmp_path / "out"
    pd.DataFrame(selected_rows).to_csv(selected, index=False)
    if prov_rows is None:
        prov_rows = [
            _prov_row(
                str(r["review_unit_id"]),
                str(r["accessions"]).split("|")[0],
                str(r["sequence"]),
                str(r["target"]),
            )
            for r in selected_rows
        ]
        # expand multi-accession
        expanded: list[dict[str, object]] = []
        for r in selected_rows:
            for acc in str(r["accessions"]).split("|"):
                if acc.strip():
                    expanded.append(
                        _prov_row(
                            str(r["review_unit_id"]),
                            acc.strip(),
                            str(r["sequence"]),
                            str(r["target"]),
                        )
                    )
        prov_rows = expanded
    pd.DataFrame(prov_rows).to_csv(prov, index=False)
    return selected, prov, out


def test_t_to_u_only_in_clean_field():
    clean, actions, applied = clean_rna_sequence("ATGC")
    assert clean == "AUGC"
    assert applied is True
    assert "t_to_u" in actions


def test_whitespace_removed_and_original_unchanged(tmp_path: Path):
    raw = " acgu acgu\nacguacguacgu "
    selected, prov, out = _write_inputs(
        tmp_path,
        [
            _selected_row(
                sequence=raw,
                sequence_original=raw,
                sequence_length="20",
                review_unit_id="ws1",
                accessions="A1",
            )
        ],
        [_prov_row("ws1", "A1", "ACGUACGUACGUACGUACGU")],
    )
    before = selected.read_bytes()
    run_finalize(selected, prov, out, overwrite=True)
    after = selected.read_bytes()
    assert before == after
    clean = pd.read_csv(out / "ena_aptamer_supplement_clean.csv", dtype=str)
    assert clean.iloc[0]["sequence_rna_clean"] == "ACGUACGUACGUACGUACGU"
    assert clean.iloc[0]["sequence"] == raw


def test_valid_rna_passes(tmp_path: Path):
    selected, prov, out = _write_inputs(tmp_path, [_selected_row()])
    summary = run_finalize(selected, prov, out, overwrite=True)
    assert summary["final_clean_pairs"] == 1
    assert summary["final_qc_rejected"] == 0


def test_invalid_characters_rejected(tmp_path: Path):
    selected, prov, out = _write_inputs(
        tmp_path,
        [_selected_row(sequence="ACGUACGUACGUACGUACGX", review_unit_id="bad")],
        [_prov_row("bad", "ACC1", "ACGUACGUACGUACGUACGX")],
    )
    summary = run_finalize(selected, prov, out, overwrite=True)
    assert summary["final_clean_pairs"] == 0
    rej = pd.read_csv(out / "ena_aptamer_supplement_rejected_final_qc.csv", dtype=str)
    assert "invalid" in rej.iloc[0]["final_qc_rejection_reason"]


def test_sequence_length_validation(tmp_path: Path):
    selected, prov, out = _write_inputs(
        tmp_path,
        [
            _selected_row(
                sequence="ACGUACGUACGUACGUACGU",
                sequence_length="99",
                review_unit_id="len1",
            )
        ],
        [_prov_row("len1", "ACC1")],
    )
    summary = run_finalize(selected, prov, out, overwrite=True)
    assert summary["final_qc_rejected"] == 1
    rej = pd.read_csv(out / "ena_aptamer_supplement_rejected_final_qc.csv", dtype=str)
    assert "length" in rej.iloc[0]["final_qc_rejection_reason"]


def test_pap_and_prostatic_acid_phosphatase_canonicalise_together():
    a_disp, a_key, a_act = canonicalise_target("PAP")
    b_disp, b_key, b_act = canonicalise_target("Prostatic acid phosphatase")
    assert a_disp == b_disp == "Prostatic acid phosphatase"
    assert a_key == b_key
    assert "alias:" in "|".join(a_act) or a_act


def test_fgf2_and_fgf_dash_canonicalise_together():
    a_disp, a_key, _ = canonicalise_target("FGF2")
    b_disp, b_key, _ = canonicalise_target("FGF-2")
    assert a_key == b_key
    assert a_disp == "FGF2"
    assert b_disp == "FGF2"


def test_comparison_keys_deterministic():
    assert orthographic_target_key("IL-17") == orthographic_target_key("IL17")
    assert orthographic_target_key("TNF-α") == orthographic_target_key("TNF alpha")
    k1 = make_clean_record_id("ACGU", "FGF2")
    k2 = make_clean_record_id("ACGU", "FGF2")
    assert k1 == k2
    assert k1.startswith("ena_")


def test_internal_duplicates_consolidate_and_retain_accessions(tmp_path: Path):
    seq = "ACGUACGUACGUACGUACGU"
    selected, prov, out = _write_inputs(
        tmp_path,
        [
            _selected_row(
                review_unit_id="u1",
                accessions="A1",
                sequence=seq,
                target="FGF2",
            ),
            _selected_row(
                review_unit_id="u2",
                accessions="A2|A3",
                sequence=seq,
                target="FGF-2",
                representative_title="Other title",
            ),
        ],
    )
    summary = run_finalize(selected, prov, out, overwrite=True)
    assert summary["final_clean_pairs"] == 1
    assert summary["duplicate_groups"] == 1
    clean = pd.read_csv(out / "ena_aptamer_supplement_clean.csv", dtype=str)
    assert set(clean.iloc[0]["supporting_accessions"].split("|")) == {"A1", "A2", "A3"}
    assert set(clean.iloc[0]["supporting_review_unit_ids"].split("|")) == {"u1", "u2"}
    assert clean.iloc[0]["internal_duplicate_count"] == "2"


def test_same_sequence_different_targets_remain_separate(tmp_path: Path):
    seq = "ACGUACGUACGUACGUACGU"
    selected, prov, out = _write_inputs(
        tmp_path,
        [
            _selected_row(review_unit_id="u1", accessions="A1", sequence=seq, target="VEGF"),
            _selected_row(review_unit_id="u2", accessions="A2", sequence=seq, target="NGF"),
        ],
    )
    summary = run_finalize(selected, prov, out, overwrite=True)
    assert summary["final_clean_pairs"] == 2
    clean = pd.read_csv(out / "ena_aptamer_supplement_clean.csv", dtype=str)
    assert set(clean["target_canonical"]) == {"VEGF", "NGF"}
    assert (clean["same_sequence_multiple_targets"] == "1").all()


def test_non_identical_near_duplicates_remain_separate(tmp_path: Path):
    selected, prov, out = _write_inputs(
        tmp_path,
        [
            _selected_row(
                review_unit_id="u1",
                accessions="A1",
                sequence="ACGUACGUACGUACGUACGU",
                target="VEGF",
                near_duplicate_family_id="fam1",
            ),
            _selected_row(
                review_unit_id="u2",
                accessions="A2",
                sequence="ACGUACGUACGUACGUACGG",
                target="VEGF",
                near_duplicate_family_id="fam1",
            ),
        ],
    )
    summary = run_finalize(selected, prov, out, overwrite=True)
    assert summary["final_clean_pairs"] == 2


def test_evidence_scope_preserved_and_strength_max(tmp_path: Path):
    seq = "ACGUACGUACGUACGUACGU"
    selected, prov, out = _write_inputs(
        tmp_path,
        [
            _selected_row(
                review_unit_id="u1",
                accessions="A1",
                sequence=seq,
                target="VEGF",
                binding_evidence_strength="weak",
                evidence_scope="patent_claim_level",
            ),
            _selected_row(
                review_unit_id="u2",
                accessions="A2",
                sequence=seq,
                target="VEGF",
                binding_evidence_strength="moderate",
                evidence_scope="selection_context_only",
            ),
        ],
    )
    run_finalize(selected, prov, out, overwrite=True)
    clean = pd.read_csv(out / "ena_aptamer_supplement_clean.csv", dtype=str)
    assert clean.iloc[0]["binding_evidence_strength_max"] == "moderate"
    scopes = set(clean.iloc[0]["evidence_scope_all"].split("|"))
    assert "patent_claim_level" in scopes
    assert "selection_context_only" in scopes
    # Must not invent individual-sequence evidence
    assert "individual_sequence" not in clean.iloc[0]["evidence_scope"]


def test_max_evidence_strength_ordering():
    assert max_evidence_strength(["none", "weak", "moderate"]) == "moderate"
    assert max_evidence_strength(["strong", "weak"]) == "strong"
    assert max_evidence_strength([]) == "none"


def test_concern_flags_remain_attached(tmp_path: Path):
    selected, prov, out = _write_inputs(
        tmp_path,
        [
            _selected_row(
                automatic_concern_flags="promoter_or_template;short_sequence",
                sequence="ACGUACGUACGUACGU",  # 16
                sequence_length="16",
            )
        ],
        [_prov_row("u1", "ACC1", "ACGUACGUACGUACGU")],
    )
    run_finalize(selected, prov, out, overwrite=True)
    clean = pd.read_csv(out / "ena_aptamer_supplement_clean.csv", dtype=str)
    assert "promoter" in clean.iloc[0]["automatic_concern_flags"]
    assert clean.iloc[0]["accepted_under_20_nt"] == "1"
    assert clean.iloc[0]["accepted_promoter_or_template_flag"] == "1"
    assert clean.iloc[0]["accepted_with_other_concern"] == "1"


def test_every_clean_record_has_provenance(tmp_path: Path):
    selected, prov, out = _write_inputs(tmp_path, [_selected_row()])
    run_finalize(selected, prov, out, overwrite=True)
    clean = pd.read_csv(out / "ena_aptamer_supplement_clean.csv", dtype=str)
    prov_out = pd.read_csv(out / "ena_aptamer_supplement_provenance.csv", dtype=str)
    assert set(clean["clean_record_id"]) <= set(prov_out["clean_record_id"])
    assert clean.iloc[0]["clean_record_id"] == prov_out.iloc[0]["clean_record_id"]


def test_missing_provenance_final_qc_rejection(tmp_path: Path):
    selected = tmp_path / "selected.csv"
    prov = tmp_path / "prov.csv"
    out = tmp_path / "out"
    pd.DataFrame([_selected_row(review_unit_id="missing_unit")]).to_csv(selected, index=False)
    # Provenance for a different unit only
    pd.DataFrame([_prov_row("other_unit", "ACC9")]).to_csv(prov, index=False)
    summary = run_finalize(selected, prov, out, overwrite=True)
    assert summary["final_clean_pairs"] == 0
    rej = pd.read_csv(out / "ena_aptamer_supplement_rejected_final_qc.csv", dtype=str)
    assert "missing_accession_provenance" in set(rej["final_qc_rejection_reason"])


def test_no_internet(tmp_path: Path):
    selected, prov, out = _write_inputs(tmp_path, [_selected_row()])

    def _deny(*_a, **_k):
        raise AssertionError("network access attempted")

    with patch.object(socket, "create_connection", side_effect=_deny):
        summary = run_finalize(selected, prov, out, overwrite=True)
    assert summary["final_clean_pairs"] == 1


def test_refuses_overwrite_without_flag(tmp_path: Path):
    selected, prov, out = _write_inputs(tmp_path, [_selected_row()])
    run_finalize(selected, prov, out, overwrite=True)
    with pytest.raises(FileExistsError):
        run_finalize(selected, prov, out, overwrite=False)


def test_t_to_u_end_to_end_preserves_reviewed_sequence(tmp_path: Path):
    selected, prov, out = _write_inputs(
        tmp_path,
        [
            _selected_row(
                sequence="ATGCATGCATGCATGCATGC",
                sequence_original="ATGCATGCATGCATGCATGC",
                sequence_length="20",
                review_unit_id="t1",
                accessions="TACC1",
            )
        ],
        [_prov_row("t1", "TACC1", "AUGCAUGCAUGCAUGCAUGC")],
    )
    run_finalize(selected, prov, out, overwrite=True)
    clean = pd.read_csv(out / "ena_aptamer_supplement_clean.csv", dtype=str)
    assert clean.iloc[0]["sequence"] == "ATGCATGCATGCATGCATGC"
    assert clean.iloc[0]["sequence_rna_clean"] == "AUGCAUGCAUGCAUGCAUGC"
    assert clean.iloc[0]["t_to_u_conversion_applied"] == "1"


def test_pap_merge_in_pipeline(tmp_path: Path):
    seq_a = "ACGU" * 5
    seq_b = "GGCU" * 5
    selected, prov, out = _write_inputs(
        tmp_path,
        [
            _selected_row(
                review_unit_id="p1",
                accessions="P1",
                sequence=seq_a,
                target="PAP",
                sequence_length="20",
            ),
            _selected_row(
                review_unit_id="p2",
                accessions="P2",
                sequence=seq_b,
                target="Prostatic acid phosphatase",
                sequence_length="20",
            ),
        ],
    )
    run_finalize(selected, prov, out, overwrite=True)
    clean = pd.read_csv(out / "ena_aptamer_supplement_clean.csv", dtype=str)
    assert set(clean["target_canonical"]) == {"Prostatic acid phosphatase"}
    assert clean["target_comparison_key"].nunique() == 1

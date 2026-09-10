"""Tests for ENA aptamer flat-file inspection (diagnostic stage only)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "data_preparation"
    / "fixtures"
    / "ena"
    / "synthetic_aptamer_cases.embl"
)

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from inspect_ena_aptamer_records import (  # noqa: E402
    EXPECTED_OUTPUT_FILES,
    analyse_duplicates,
    enrich_record,
    extract_sequence_from_raw,
    load_and_parse_records,
    main,
    parse_raw_record,
    reverse_complement,
    rna_equivalent,
    split_embl_records,
    write_outputs,
)


@pytest.fixture(scope="module")
def fixture_text() -> str:
    assert FIXTURE_PATH.exists(), f"Missing fixture: {FIXTURE_PATH}"
    return FIXTURE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def records(fixture_text: str):
    blocks = split_embl_records(fixture_text)
    parsed = [enrich_record(parse_raw_record(i, block)) for i, block in enumerate(blocks)]
    return parsed


@pytest.fixture(scope="module")
def by_accession(records):
    return {r.accession: r for r in records if r.accession}


def test_fixture_splits_into_expected_blocks(fixture_text: str):
    blocks = split_embl_records(fixture_text)
    # 18 scenario types across 19 blocks (duplicate-sequence pair adds one block;
    # reverse-complement pair adds one; multiline note is embedded in SYNSELEX1).
    assert len(blocks) == 19
    accessions = []
    for block in blocks:
        for line in block.splitlines():
            if line.startswith("AC   "):
                accessions.append(line[5:].strip().rstrip(";"))
                break
    assert "SYNSELEX1" in accessions
    assert "REFTITLE1" in accessions
    assert any("NOT A VALID" in b for b in blocks)


def test_multiline_description_joined(by_accession):
    rec = by_accession["MULTIDE01"]
    assert "Synthetic multiline description" in rec.description_joined
    assert "binds streptomycin" in rec.description_joined
    assert "\n" not in rec.description_joined


def test_multiline_feature_note_joined(by_accession):
    rec = by_accession["SYNSELEX1"]
    notes = " ".join(
        q.value for f in rec.features for q in f.qualifiers if q.name == "note"
    )
    assert "Systematic Evolution of Ligands by Exponential Enrichment" in notes
    assert "in vitro evolved" in notes


def test_sequence_extraction_excludes_position_numbers(by_accession):
    rec = by_accession["RNWITH_T1"]
    assert rec.sequence is not None
    assert rec.sequence.sequence_deposited == "GGGACGAAGCTTAAAACGACGGCCAGTGCC"
    assert "30" not in rec.sequence.sequence_deposited
    assert rec.sequence.sequence_length_calculated == 30


def test_raw_record_text_recoverable(records):
    for rec in records:
        assert rec.raw_record_text
        assert rec.raw_record_character_count == len(rec.raw_record_text)
        assert rec.raw_record_line_count == len(rec.raw_record_text.splitlines())


def test_evidence_flags_are_non_exclusive(by_accession):
    # Genomic SELEX natural motif can carry natural + selection-related phrases.
    rec = by_accession["HUMGENOM1"]
    assert rec.signals.get("signal_natural_or_genomic")
    # May also be uncertain; signals must be able to overlap elsewhere.
    construct = by_accession["APTAZY001"]
    assert construct.signals.get("signal_engineered_construct")
    # Engineered construct should not be auto-approved or excluded.
    assert "include" not in construct.discrepancies
    assert "exclude" not in construct.discrepancies


def test_no_automatic_inclusion_or_exclusion_decisions(records):
    for rec in records:
        joined = "|".join(rec.discrepancies).lower()
        assert "approved" not in joined
        assert "excluded_from_corpus" not in joined
        assert rec.parse_status in {"ok", "malformed"}


def test_rna_record_with_t_reported_but_not_corrupted(by_accession):
    rec = by_accession["RNWITH_T1"]
    original = rec.sequence.sequence_deposited
    assert "T" in original
    assert "U" not in original
    assert "RNA_molecule_stored_with_T_ENA_convention" in rec.discrepancies
    # rna_equivalent is temporary only
    derived = rna_equivalent(original)
    assert "U" in derived
    assert rec.sequence.sequence_deposited == original


def test_original_sequence_never_altered_by_enrichment(fixture_text: str):
    blocks = split_embl_records(fixture_text)
    before = extract_sequence_from_raw(blocks[0]).sequence_deposited
    rec = enrich_record(parse_raw_record(0, blocks[0]))
    assert rec.sequence.sequence_deposited == before


def test_synthetic_selex_signal(by_accession):
    rec = by_accession["SYNSELEX1"]
    assert rec.signals["signal_synthetic_selected"]
    assert rec.phrase_hits.has("selection")
    assert "selex" in rec.raw_record_text.lower()


def test_natural_genomic_and_riboswitch(by_accession):
    assert by_accession["HUMGENOM1"].signals["signal_natural_or_genomic"]
    assert by_accession["RIBOSW001"].signals["signal_riboswitch_related"]


def test_dna_template_t7_promoter(by_accession):
    rec = by_accession["DNATEMP01"]
    assert rec.contains_t7_promoter_like_motif
    assert rec.t7_promoter_match == "TAATACGACTCACTATA"
    assert rec.signals["signal_dna_template_or_promoter"]


def test_complement_and_subregion_features(by_accession):
    assert by_accession["COMPFEAT1"].signals["signal_reverse_complement_feature"]
    assert "aptamer_feature_is_complement" in by_accession["COMPFEAT1"].discrepancies
    assert by_accession["SUBREG001"].signals["signal_feature_subregion"]


def test_missing_doi_pmid_and_multiple_references(by_accession):
    no_id = by_accession["NODPI001"]
    assert "missing_DOI" in no_id.discrepancies
    assert "missing_PMID" in no_id.discrepancies
    multi = by_accession["MULTIREF1"]
    assert len(multi.references) >= 3
    assert "multiple_references_present" in multi.discrepancies


def test_length_mismatch_and_mixed_alphabet(by_accession):
    assert "reported_length_differs_from_calculated_length" in by_accession[
        "LENMIS001"
    ].discrepancies
    mixed = by_accession["MIXEDTU01"]
    assert mixed.sequence.sequence_alphabet == "mixed_T_U"
    assert "sequence_contains_both_T_and_U" in mixed.discrepancies


def test_incidental_reference_only_aptamer(by_accession):
    rec = by_accession["REFTITLE1"]
    assert rec.signals["signal_incidental_aptamer_reference"]
    assert "aptamer" not in rec.description_joined.lower()


def test_malformed_record_flagged(records):
    malformed = [r for r in records if r.parse_status != "ok"]
    assert malformed
    assert any("missing_ID_line" in r.parse_warnings or "missing_accession" in r.parse_warnings for r in malformed)


def test_duplicate_sequence_and_reverse_complement(records, by_accession):
    dup = analyse_duplicates(records)
    exact = dup[dup["duplicate_type"] == "exact_sequence"]
    assert not exact.empty
    accessions = set()
    for vals in exact["accessions"]:
        accessions.update(str(vals).split("|"))
    assert {"DUPSEQ_A1", "DUPSEQ_B1"} <= accessions

    fwd = by_accession["RCSEQ_F01"].sequence.sequence_deposited
    rev = by_accession["RCSEQ_R01"].sequence.sequence_deposited
    assert reverse_complement(fwd) == rev
    rc_rows = dup[dup["duplicate_type"] == "reverse_complement"]
    assert not rc_rows.empty


def test_script_writes_all_expected_outputs(tmp_path: Path):
    out = tmp_path / "inspection"
    records = load_and_parse_records(FIXTURE_PATH)
    paths = write_outputs(
        records,
        FIXTURE_PATH,
        out,
        examples_per_category=3,
        overwrite=True,
    )
    for name in EXPECTED_OUTPUT_FILES:
        assert (out / name).exists(), f"missing {name}"
        assert paths[name].exists()

    inventory = pd.read_csv(out / "ena_record_inventory.csv")
    assert len(inventory) == len(records)
    assert "signal_synthetic_selected" in inventory.columns
    assert "discrepancies" in inventory.columns

    # Per-accession raw records written for small runs
    assert (out / "records").is_dir()


def test_cli_main_on_fixture(tmp_path: Path):
    out = tmp_path / "cli_out"
    code = main(
        [
            "--input",
            str(FIXTURE_PATH),
            "--output-dir",
            str(out),
            "--overwrite",
            "--examples-per-category",
            "2",
            "--log-level",
            "WARNING",
        ]
    )
    assert code == 0
    assert (out / "ena_inspection_report.md").exists()
    assert (out / "ena_inspection_log.txt").exists()


def test_cli_fails_on_missing_input(tmp_path: Path):
    code = main(
        [
            "--input",
            str(tmp_path / "does_not_exist.embl"),
            "--output-dir",
            str(tmp_path / "out"),
            "--overwrite",
        ]
    )
    assert code != 0

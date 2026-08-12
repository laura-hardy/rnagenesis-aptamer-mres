"""Tests for the UTexas S2 adapter (synthetic sequences only).

Every literal nucleotide string in this file is shorter than 20 nt.
Does not read real UTexas aptamer sequences.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.utexas_s2 import (  # noqa: E402
    build_pool_type_proposals,
    load_utexas_policy,
    normalise_utexas_record,
    parse_pool_type_constants,
    resolve_utexas_molecule_and_chemistry,
)
from common.corpus_schema import empty_corpus_record  # noqa: E402
from common.sequence_normalisation import load_normalisation_rules  # noqa: E402

POLICY_PATH = REPO_ROOT / "config" / "source_normalisation" / "utexas.json"


def _meta(**overrides: str) -> dict[str, str]:
    row = {
        "record_id": "utexas:row_0002",
        "utexas_type_of_nucleic_acid": "ssRNA",
        "utexas_name_of_aptamer": "demo",
        "utexas_pool_type": "",
        "utexas_pool_random_region": "",
        "utexas_sequence_length": "",
        "utexas_post_selex_modifications": "",
    }
    row.update(overrides)
    return row


def _s1(**overrides: str) -> dict[str, str]:
    record = empty_corpus_record()
    record.update(
        {
            "record_id": "utexas:row_0002",
            "sequence_raw": "ACGUAC",
            "source_db": "utexas",
            "source_dataset": "utexas_sept2023_2026-08",
            "contributing_sources": "utexas",
            "contributing_datasets": "utexas_sept2023_2026-08",
            "corroboration_count": "1",
            "redistribution_status": "unknown",
            "independently_attested_by_permissive_source": "false",
            "native_id": "row_0002",
            "target_name_raw": "demo_target",
            "publication": "Demo",
            "doi": "",
            "pubmed_id": "",
            "notes": json.dumps({"aptamer_name": "demo"}, separators=(",", ":")),
        }
    )
    record.update(overrides)
    return record


@pytest.fixture(scope="module")
def policy():
    return load_utexas_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def rules():
    return load_normalisation_rules()


# --- Molecule / chemistry mapping ---


@pytest.mark.parametrize(
    ("source", "molecule", "chemistry"),
    [
        ("ssRNA", "RNA", "RNA"),
        ("ssDNA", "ssDNA", "DNA"),
        ("dsDNA", "DNA", "DNA"),
        ("2\'-fluoro-RNA", "RNA", "2F-RNA"),
        ("2\'-amino-RNA", "RNA", "2NH2-RNA"),
        ("2\'-O-Me-RNA", "RNA", "2OMe-RNA"),
        ("2\'-fluoro/O-Me-RNA", "RNA", "mixed"),
        ("2\'-fluoro/amino-RNA", "RNA", "mixed"),
        ("", "unknown", "unknown"),
        ("FANA XNA", "unknown", "unknown"),
        ("4\'-thio-RNA", "RNA", "unknown"),
        ("5-uracil-modified-RNA", "RNA", "unknown"),
        ("5-uracil-modified-DNA", "DNA", "unknown"),
        ("2\',4\'-BNA/LNA-DNA", "DNA", "unknown"),
    ],
)
def test_molecule_chemistry_map(policy, source, molecule, chemistry) -> None:
    result = resolve_utexas_molecule_and_chemistry(
        {"utexas_type_of_nucleic_acid": source},
        policy,
    )
    assert result.molecule_type == molecule
    assert result.chemistry == chemistry


def test_unsupported_chemistry_flagged(policy) -> None:
    result = resolve_utexas_molecule_and_chemistry(
        {"utexas_type_of_nucleic_acid": "4\'-thio-RNA"},
        policy,
    )
    assert "chemistry_not_in_canonical_vocab" in result.qc_flags


def test_fana_requires_molecule_review(policy) -> None:
    result = resolve_utexas_molecule_and_chemistry(
        {"utexas_type_of_nucleic_acid": "FANA XNA"},
        policy,
    )
    assert result.molecule_type == "unknown"
    assert "molecule_type_requires_review" in result.qc_flags


# --- Molecule policy with sequences ---


def test_ssrna_u_no_t_to_u(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(utexas_type_of_nucleic_acid="ssRNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "RNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGUAC"


def test_ssrna_t_converted(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(utexas_type_of_nucleic_acid="ssRNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["alphabet_as_reported"] == "DNA_T"
    assert result.canonical["t_to_u_applied"] == "true"
    assert result.canonical["sequence_full"] == "ACGUAC"


def test_ssdna_retains_t(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(utexas_type_of_nucleic_acid="ssDNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "ssDNA"
    assert result.canonical["chemistry"] == "DNA"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGTAC"


def test_dsdna_retains_t(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(utexas_type_of_nucleic_acid="dsDNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "DNA"
    assert result.canonical["t_to_u_applied"] == "false"


def test_fluoro_rna_t_converted(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(utexas_type_of_nucleic_acid="2\'-fluoro-RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "RNA"
    assert result.canonical["chemistry"] == "2F-RNA"
    assert result.canonical["t_to_u_applied"] == "true"
    assert result.canonical["sequence_full"] == "ACGUAC"


def test_amino_rna_u_unchanged(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(utexas_type_of_nucleic_acid="2\'-amino-RNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["chemistry"] == "2NH2-RNA"
    assert result.canonical["t_to_u_applied"] == "false"


def test_fana_t_not_converted(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(utexas_type_of_nucleic_acid="FANA XNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["chemistry"] == "unknown"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGTAC"
    assert "molecule_type_requires_review" in result.canonical["qc_flags"]


def test_blank_type_t_stays_unknown(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGTAC"),
        _meta(utexas_type_of_nucleic_acid=""),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["chemistry"] == "unknown"
    assert result.canonical["t_to_u_applied"] == "false"
    assert result.canonical["sequence_full"] == "ACGTAC"


def test_mixed_t_u_unrepaired(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGTU"),
        _meta(utexas_type_of_nucleic_acid="ssRNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_full"] == "ACGTU"
    assert result.canonical["t_to_u_applied"] == "false"
    assert "mixed_t_u" in result.canonical["qc_flags"]


# --- Stage boundary ---


def test_rows_preserved_and_no_later_fields(policy, rules) -> None:
    s1 = _s1(sequence_raw="ACGUAC")
    result = normalise_utexas_record(s1, _meta(), policy=policy, rules=rules)
    assert result.canonical["record_id"] == s1["record_id"]
    assert result.canonical["native_id"] == s1["native_id"]
    assert result.canonical["sequence_raw"] == s1["sequence_raw"]
    for field in (
        "target_name",
        "target_uniprot",
        "affinity_value",
        "binding_evidence_type",
        "cluster_id",
        "partition",
    ):
        assert result.canonical[field] == ""


def test_missing_sequence_retained(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw=""),
        _meta(utexas_type_of_nucleic_acid=""),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_raw"] == ""
    assert result.canonical["sequence_full"] == ""
    assert result.canonical["sequence_core"] == ""
    assert result.canonical["molecule_type"] == "unknown"
    assert result.canonical["chemistry"] == "unknown"
    assert "missing_sequence" in result.canonical["qc_flags"]


def test_post_selex_does_not_alter_sequence(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGUAC"),
        _meta(utexas_post_selex_modifications="2\'-O-methyl at position 3"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_full"] == "ACGUAC"
    assert result.qc["post_selex_modifications_present"] == "true"


# --- Constant regions ---


def test_pool_type_parse_simple() -> None:
    parsed = parse_pool_type_constants(
        "5\'-AGCAGCACAGAGGTCAGATG-N40-CCTATGCGTGCTACCGTGAA-3\'"
    )
    assert parsed is not None
    assert parsed.five_prime == "AGCAGCACAGAGGTCAGATG"
    assert parsed.three_prime == "CCTATGCGTGCTACCGTGAA"
    assert parsed.documented_n_length == 40


def test_pool_type_multi_n_not_guessed() -> None:
    parsed = parse_pool_type_constants(
        "5\'-AUUCUGU-N6-GUACGCAAGUAC-N6-ACAG-3\'"
    )
    assert parsed is None


def test_detection_does_not_trim(policy, rules) -> None:
    pool = "5\'-AAAA-N8-CCCC-3\'"
    # Use a sequence that matches the documented flanks after cleaning.
    raw = "5\'-AAAACCCCCCCC-3\'"
    result = normalise_utexas_record(
        _s1(sequence_raw=raw),
        _meta(utexas_pool_type=pool, utexas_type_of_nucleic_acid="ssDNA"),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.canonical["trim_status"] == "constants_suspected_unresolved"
    assert result.pool_parse is not None
    proposals = build_pool_type_proposals([result])
    assert len(proposals) == 2
    assert all(p["applied"] == "false" for p in proposals)
    assert all(p["reason_not_applied"] == "no_approved_utexas_trim_rule" for p in proposals)


def test_no_pool_means_no_constants_detected(policy, rules) -> None:
    result = normalise_utexas_record(
        _s1(sequence_raw="ACGUACGUAC"),
        _meta(utexas_pool_type=""),
        policy=policy,
        rules=rules,
    )
    assert result.canonical["sequence_core"] == result.canonical["sequence_full"]
    assert result.canonical["trim_status"] == "no_constants_detected"

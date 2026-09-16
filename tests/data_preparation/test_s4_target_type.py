"""Synthetic tests for Milestone-3 canonical target-type proposals."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_target_type import map_source_type_prior, merge_dictionary_type_priors  # noqa: E402


def test_source_prior_mapping() -> None:
    protein = map_source_type_prior("aptabase", "Protein")
    assert protein["target_type_proposed"] == "protein"
    peptide = map_source_type_prior("aptabase", "Peptide")
    assert peptide["target_type_proposed"] == "peptide"
    small = map_source_type_prior("aptaindex", "Small Organic")
    assert small["target_type_proposed"] == "small_molecule"
    aptadb = map_source_type_prior("aptadb", "Protein")
    assert aptadb["target_type_proposed"] == "protein"
    ribo = map_source_type_prior("riboaptamer", "Cells")
    assert ribo["target_type_proposed"] == "cell"


def test_source_prior_conflict_requires_review() -> None:
    mixed = map_source_type_prior("aptamerbase", "Nucleic acid|Protein")
    assert mixed["target_type_proposed"] == "unknown"
    assert mixed["type_requires_review"] == "true"
    merged = merge_dictionary_type_priors(
        {"aptadb": "Protein", "riboaptamer": "Small molecules"}
    )
    assert merged["target_type_proposed"] == "unknown"
    assert merged["type_requires_review"] == "true"


def test_enzyme_maps_to_protein_with_family_clue() -> None:
    result = map_source_type_prior("ena", "enzyme")
    assert result["target_type_proposed"] == "protein"
    assert result["family_clue"] == "enzyme"


def test_unknown_remains_unknown() -> None:
    result = map_source_type_prior("utexas", "")
    assert result["target_type_proposed"] == "unknown"
    assert result["target_type_source_proposed"] == "unresolved"


def test_no_accidental_protein_inference_from_unmapped_prior() -> None:
    result = map_source_type_prior("aptaindex", "Tissue")
    assert result["target_type_proposed"] == "other"
    assert result["type_requires_review"] == "true"
    antibody = map_source_type_prior("aptabase", "Antibody")
    assert antibody["target_type_proposed"] == "protein"
    assert antibody["family_clue"] == "antibody_immunoglobulin"

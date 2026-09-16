"""Synthetic tests for family/Pfam proposals."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_family_pfam import parse_pfam_interpro, propose_family, region_or_fragment  # noqa: E402


def test_supported_family_assignment() -> None:
    result = propose_family(target_type="protein", family_clues=["enzyme"])
    assert result["target_family_proposed"] == "enzyme"


def test_unresolved_family_permitted() -> None:
    result = propose_family(target_type="protein", family_clues=[])
    assert result["target_family_proposed"] == "unknown"
    assert result["family_requires_review"] == "false"


def test_non_protein_family_is_other() -> None:
    result = propose_family(target_type="small_molecule", family_clues=["enzyme"])
    assert result["target_family_proposed"] == "other"


def test_pfam_not_required_and_multi_value() -> None:
    pfam, interpro = parse_pfam_interpro("PF00001;IPR000001", "PF00002")
    assert "PF00001" in pfam
    assert "PF00002" in pfam
    assert interpro == "IPR000001"


def test_region_or_fragment_flag() -> None:
    assert region_or_fragment("extracellular domain of HER3") == "true"
    assert region_or_fragment("VEGF") == "false"

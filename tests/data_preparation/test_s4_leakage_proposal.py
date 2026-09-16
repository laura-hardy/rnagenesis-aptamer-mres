"""Synthetic tests for diagnostic leakage proposals (not corpus dedup)."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.s4_leakage_proposal import load_leakage_resources, propose_leakage  # noqa: E402
from common.eligibility import SequenceLeakageIndex, TargetAliasRule  # noqa: E402
from common.leakage_matching import comparison_form  # noqa: E402

LEAKAGE_COLUMNS = [
    "exclusion_id",
    "reference_id",
    "target_name",
    "evaluation_role",
    "sequence_compare_full",
    "sequence_compare_core",
    "status",
]


def _write_exclusion(path: Path, seq: str) -> None:
    compare = comparison_form(seq)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEAKAGE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerow(
            {
                "exclusion_id": "EX1",
                "reference_id": "REF1",
                "target_name": "NDM-1",
                "evaluation_role": "eval",
                "sequence_compare_full": compare,
                "sequence_compare_core": compare,
                "status": "active",
            }
        )


def _write_aliases(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "canonical_target",
                "alias",
                "match_type",
                "target_family",
                "exclusion_reason",
                "notes",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(
            {
                "canonical_target": "NDM-1",
                "alias": "NDM-1",
                "match_type": "exact_alias",
                "target_family": "carbapenemase",
                "exclusion_reason": "evaluation_reference_target",
                "notes": "",
            }
        )


def test_exact_and_threshold_and_tu(tmp_path: Path) -> None:
    exclusion = tmp_path / "leak.csv"
    aliases = tmp_path / "aliases.csv"
    _write_exclusion(exclusion, "ACGUACGUAC")
    _write_aliases(aliases)
    index, rules = load_leakage_resources(exclusion_set=exclusion, alias_csv=aliases)
    exact = propose_leakage(
        {"record_id": "x:1", "source_db": "ena", "sequence_full": "ACGTACGTAC", "sequence_core": "ACGTACGTAC"},
        index=index,
        rules=rules,
        target_texts=["VEGF"],
    )
    assert exact["sequence_match_kind"] == "exact"
    assert exact["leakage_exclusion_proposed"] == "true"

    near = propose_leakage(
        {"record_id": "x:2", "source_db": "ena", "sequence_full": "ACGTACGTAG", "sequence_core": "ACGTACGTAG"},
        index=index,
        rules=rules,
        target_texts=["VEGF"],
    )
    assert near["sequence_match_kind"] == "identity_ge_0.90"


def test_empty_skip_and_no_substring(tmp_path: Path) -> None:
    exclusion = tmp_path / "leak.csv"
    aliases = tmp_path / "aliases.csv"
    _write_exclusion(exclusion, "ACGUACGUAC")
    _write_aliases(aliases)
    index, rules = load_leakage_resources(exclusion_set=exclusion, alias_csv=aliases)
    empty = propose_leakage(
        {"record_id": "x:3", "source_db": "ena", "sequence_full": "", "sequence_core": ""},
        index=index,
        rules=rules,
        target_texts=["VEGF"],
    )
    assert empty["leakage_exclusion_proposed"] == "false"
    substring = propose_leakage(
        {"record_id": "x:4", "source_db": "ena", "sequence_full": "ACGTACGTACCCCC", "sequence_core": "ACGTACGTACCCCC"},
        index=index,
        rules=rules,
        target_texts=["not a leakage target"],
    )
    assert substring["leakage_exclusion_proposed"] == "false"


def test_target_alias_and_not_corpus_dedup(tmp_path: Path) -> None:
    exclusion = tmp_path / "leak.csv"
    aliases = tmp_path / "aliases.csv"
    _write_exclusion(exclusion, "GGGGGGGGGG")
    _write_aliases(aliases)
    index, rules = load_leakage_resources(exclusion_set=exclusion, alias_csv=aliases)
    alias = propose_leakage(
        {"record_id": "x:5", "source_db": "ena", "sequence_full": "AAAAAAAAAA", "sequence_core": "ACGTACGTAA"},
        index=index,
        rules=rules,
        target_texts=["NDM-1"],
    )
    assert alias["target_alias_match"] == "true"
    assert alias["leakage_exclusion_proposed"] == "true"
    # Ordinary identical non-exclusion sequences are not leakage.
    ordinary = propose_leakage(
        {"record_id": "x:6", "source_db": "ena", "sequence_full": "CCCCCCCCCC", "sequence_core": "ACGTACGTCC"},
        index=index,
        rules=rules,
        target_texts=["VEGF"],
    )
    assert ordinary["leakage_exclusion_proposed"] == "false"

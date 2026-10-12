#!/usr/bin/env python3
"""Unit tests for the frozen NDM-1 target-preparation workflow."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from prepare_ndm1_target import (
    TargetPreparationError,
    parse_fpocket_info,
    pocket_geometry,
    select_pocket,
)
from verify_replication import compare


def pocket(number: int, core: list[int], extended: list[int], zn1: list[int], zn2: list[int]) -> dict:
    return {
        "pocket_number": number,
        "core_overlap": core,
        "extended_overlap": extended,
        "zn1_overlap": zn1,
        "zn2_overlap": zn2,
    }


class FpocketParserTests(unittest.TestCase):
    def test_parses_blank_line_delimited_descriptors(self) -> None:
        content = """Pocket 1 :\n\tScore : 12.50\n\tDruggability Score : 0.42\n\tVolume : 321.0\n\nPocket 2 :\n\tScore : 8.0\n\tDruggability Score : 0.10\n\tVolume : 100.5\n"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture_info.txt"
            path.write_text(content, encoding="utf-8")
            parsed = parse_fpocket_info(path)
        self.assertEqual(sorted(parsed), [1, 2])
        self.assertEqual(parsed[1]["Volume"], 321.0)
        self.assertEqual(parsed[2]["Score"], 8.0)

    def test_geometry_uses_paper_principal_axis_formula(self) -> None:
        coords = np.asarray([[-2.0, 0.0, 0.0], [0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
        result = pocket_geometry(coords, volume_a3=100.0)
        expected = 2.0 * np.linalg.svd(coords, full_matrices=False)[1][0] / np.sqrt(3)
        self.assertAlmostEqual(result["characteristic_dimension_A"], expected)


class PocketSelectionTests(unittest.TestCase):
    def test_core_overlap_precedes_extended_overlap(self) -> None:
        chosen = select_pocket([
            pocket(1, [120], [65, 67, 70, 73], [120], []),
            pocket(2, [120, 124], [65], [120], [124]),
        ])
        self.assertEqual(chosen["pocket_number"], 2)

    def test_extended_overlap_breaks_core_tie(self) -> None:
        chosen = select_pocket([
            pocket(1, [120, 124], [65], [120], [124]),
            pocket(2, [120, 124], [65, 67], [120], [124]),
        ])
        self.assertEqual(chosen["pocket_number"], 2)

    def test_unresolved_tie_fails_closed(self) -> None:
        with self.assertRaises(TargetPreparationError):
            select_pocket([
                pocket(1, [120, 124], [65], [120], [124]),
                pocket(2, [120, 124], [67], [120], [124]),
            ])

    def test_both_zinc_subsites_are_required(self) -> None:
        with self.assertRaises(TargetPreparationError):
            select_pocket([pocket(1, [120, 122], [65], [120, 122], [])])


class ReplicationTests(unittest.TestCase):
    def test_volume_variation_does_not_fail_stable_geometry(self) -> None:
        reference = {
            "pocket_number": 1,
            "alpha_sphere_count_parsed": 42,
            "lining_residues": [65, 120, 124],
            "core_overlap": [120, 124],
            "extended_overlap": [65],
            "zn1_overlap": [120],
            "zn2_overlap": [124],
            "characteristic_dimension_A": 9.2,
            "volume_A3": 600.0,
        }
        replication = {**reference, "volume_A3": 620.0}
        self.assertEqual(compare(reference, replication)["status"], "pass")


if __name__ == "__main__":
    unittest.main()

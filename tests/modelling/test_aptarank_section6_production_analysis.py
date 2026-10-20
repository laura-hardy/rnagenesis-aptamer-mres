#!/usr/bin/env python3
"""Focused tests for the Section 6 production-analysis adapter."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODELLING = ROOT / "scripts" / "modelling"
sys.path.insert(0, str(MODELLING))
SPEC = importlib.util.spec_from_file_location(
    "section6_production_analysis",
    MODELLING / "aptarank_section6_production_analysis.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ProductionAnalysisTests(unittest.TestCase):
    def test_exclusion_register_is_strict(self):
        payload = (
            "row,id,sequence,reason\n"
            "2,cand_0123456789abcdef0123456789abcdef,ACGU,length 4 above maximum 3\n"
        ).encode("utf-8")
        self.assertEqual(
            module.parse_exclusions(payload),
            [
                {
                    "candidate_id": "cand_0123456789abcdef0123456789abcdef",
                    "reason": "length 4 above maximum 3",
                }
            ],
        )
        with self.assertRaises(module.ProductionAnalysisError):
            module.parse_exclusions(payload.replace(b"row,id,sequence,reason", b"id,sequence,reason"))
        with self.assertRaises(module.ProductionAnalysisError):
            module.parse_exclusions(payload + payload.splitlines()[1] + b"\n")

    def test_fraction_rendering(self):
        self.assertEqual(module.decimal_text("1/8"), "0.125")
        self.assertEqual(module.percent_text("1/17"), "5.9%")

    def test_public_output_rejects_candidate_ids(self):
        with self.assertRaises(module.ProductionAnalysisError):
            module.ensure_public(
                {"summary": b"cand_0123456789abcdef0123456789abcdef"},
                b"restricted-key-bytes",
            )

    def test_public_output_rejects_private_key_bytes(self):
        with self.assertRaises(module.ProductionAnalysisError):
            module.ensure_public({"summary": b"prefix restricted-key-bytes suffix"}, b"restricted-key-bytes")

    def test_denominator_gate(self):
        summary = {
            "denominators": {
                "input_candidates": 308,
                "evaluable_scores": 306,
                "technical_failures": 2,
                "complete_score_pairs": 153,
                "incomplete_score_pairs": 1,
                "pre_rejection_clusters": 79,
                "clusters_with_complete_score_pairs": 79,
                "paired_shuffle_pairs": 153,
                "imputed_replicates": 0,
                "evaluable_scores_by_class": {"eval_core": 153, "paired_uniform_shuffle": 153},
                "shuffle_valid_by_class": {"eval_core": 153, "paired_uniform_shuffle": 153},
                "bootstrap_replicates": 10000,
                "bootstrap_defined_replicates": {"auroc": 10000},
                "bootstrap_undefined_replicates": {"auroc": 0},
            }
        }
        module.validate_production_denominators(summary)
        summary["denominators"]["complete_score_pairs"] = 152
        with self.assertRaises(module.ProductionAnalysisError):
            module.validate_production_denominators(summary)


if __name__ == "__main__":
    unittest.main()

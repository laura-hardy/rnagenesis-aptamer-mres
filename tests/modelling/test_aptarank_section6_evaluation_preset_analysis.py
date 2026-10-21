#!/usr/bin/env python3
"""Focused tests for the Section 6 Evaluation-preset analysis adapter."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODELLING = ROOT / "scripts" / "modelling"
sys.path.insert(0, str(MODELLING))
SPEC = importlib.util.spec_from_file_location(
    "section6_evaluation_preset_analysis",
    MODELLING / "aptarank_section6_evaluation_preset_analysis.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class EvaluationPresetAnalysisTests(unittest.TestCase):
    def test_run_sheet_requires_rigorous_settings(self):
        sheet = {
            "preset": "Evaluation",
            "preset_role": "paper_rigorous_mode",
            "seed": 42,
            "candidate_shuffles": 99,
            "sampled_structures": 200,
            "protein_target": None,
            "expected_compatibility_token": "not evaluated",
        }
        module.validate_run_sheet(sheet)
        for key, value in (("preset", "Standard"), ("candidate_shuffles", 20), ("sampled_structures", 100)):
            changed = dict(sheet)
            changed[key] = value
            with self.assertRaises(module.RigorousAnalysisError):
                module.validate_run_sheet(changed)

    def test_public_output_rejects_candidate_ids_and_private_key(self):
        with self.assertRaises(module.RigorousAnalysisError):
            module.ensure_public(
                {"summary": b"cand_0123456789abcdef0123456789abcdef"},
                b"private-key",
            )
        with self.assertRaises(module.RigorousAnalysisError):
            module.ensure_public({"summary": b"prefix private-key suffix"}, b"private-key")

    def test_adapter_pins_new_plan_and_preserves_historical_lineage(self):
        self.assertEqual(
            module.PLAN_SHA256,
            "24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9",
        )
        self.assertEqual(module.RUN_SHEET_SHA256, "0dbe9ab773d68537605990d50df1cc50e4f5c8080118b3d6e25d5f683603db0f")
        self.assertNotEqual(module.RUN_SHEET_SHA256, module.historical.RUN_SHEET_SHA256)
        self.assertEqual(module.RUN_SHEET_VALIDATION_OWNER, "v3.7_evaluation_preset_adapter")
        self.assertIn("AWAITING_INDEPENDENT_REVIEW", module.STATUS)


if __name__ == "__main__":
    unittest.main()

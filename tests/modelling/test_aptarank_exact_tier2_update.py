#!/usr/bin/env python3
"""Focused tests for the exact Tier 2 supplemental analysis adapter."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODELLING = ROOT / "scripts" / "modelling"
sys.path.insert(0, str(MODELLING))
SPEC = importlib.util.spec_from_file_location(
    "aptarank_exact_tier2_update",
    MODELLING / "aptarank_exact_tier2_update.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

CID_A = "cand_00000000000000000000000000000000"
CID_B = "cand_11111111111111111111111111111111"


def exact_csv(rows: list[str]) -> bytes:
    header = ",candidate,rank,tier1,control_percentile,mismatch,band,selected"
    return ("\ufeff" + header + "\r\n" + "\r\n".join(rows) + "\r\n").encode("utf-8")


class ExactTier2UpdateTests(unittest.TestCase):
    def test_exact_export_accepts_bom_crlf_and_closed_interval(self):
        payload = exact_csv([
            f"0,{CID_A},1,1,0,5,weak,true",
            f"1,{CID_B},2,0,1,2,strong,false",
        ])
        rows = module.parse_exact_export(payload, 2)
        self.assertEqual(rows[0]["control_percentile"], Decimal("0"))
        self.assertEqual(rows[1]["control_percentile"], Decimal("1"))

    def test_band_thresholds_are_enforced(self):
        valid = exact_csv([
            f"0,{CID_A},1,0.5,0.75,5,moderate,true",
            f"1,{CID_B},2,0.4,0.95,2,strong,false",
        ])
        self.assertEqual([row["band"] for row in module.parse_exact_export(valid, 2)], ["moderate", "strong"])
        invalid = valid.replace(b",0.75,5,moderate,", b",0.75,5,weak,")
        with self.assertRaises(module.ExactTier2UpdateError):
            module.parse_exact_export(invalid, 2)

    def test_reconciliation_is_by_candidate_rank_tier1_and_band(self):
        exact = module.parse_exact_export(exact_csv([
            f"0,{CID_A},1,0.8,0.96,1,strong,true",
            f"1,{CID_B},2,0.4,0.2,4,weak,false",
        ]), 2)
        validated = [
            {"candidate": CID_A, "rank": 1, "score": Decimal("0.8"), "compatibility": "strong"},
            {"candidate": CID_B, "rank": 2, "score": Decimal("0.4"), "compatibility": "weak"},
        ]
        module.reconcile_exact(exact, validated)
        validated[0]["candidate"] = CID_B
        with self.assertRaises(module.ExactTier2UpdateError):
            module.reconcile_exact(exact, validated)

    def test_tie_aware_spearman(self):
        left = [Decimal("1"), Decimal("2"), Decimal("2"), Decimal("4")]
        right = [Decimal("4"), Decimal("2"), Decimal("2"), Decimal("1")]
        self.assertAlmostEqual(module.spearman_rho(left, right), -1.0)

    def test_public_outputs_reject_ids_and_sequences(self):
        with self.assertRaises(module.ExactTier2UpdateError):
            module.ensure_public({"report": CID_A.encode()})
        with self.assertRaises(module.ExactTier2UpdateError):
            module.ensure_public({"report": b"ACGUACGUACGUACGUACGU"})

    def test_statuses_cannot_commit_results(self):
        self.assertIn("PROVISIONAL", module.SECTION8_STATUS)
        self.assertIn("RECOMMITMENT", module.SECTION8_STATUS)
        self.assertIn("PROVISIONAL", module.SECTION9_STATUS)
        self.assertIn("EXPLICIT_RESULT_COMMITMENT", module.SECTION9_STATUS)


if __name__ == "__main__":
    unittest.main()

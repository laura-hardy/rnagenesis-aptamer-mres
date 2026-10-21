#!/usr/bin/env python3
"""Focused tests for Section 10 validation and pool construction."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODELLING = ROOT / "scripts" / "modelling"
sys.path.insert(0, str(MODELLING))
SPEC = importlib.util.spec_from_file_location(
    "aptarank_section10_analyze_and_build_review_pool",
    MODELLING / "aptarank_section10_analyze_and_build_review_pool.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def sequence_for(index: int) -> str:
    alphabet = "ACGU"
    value = index
    suffix = []
    for _ in range(8):
        suffix.append(alphabet[value % 4])
        value //= 4
    return "ACGUACGUACGU" + "".join(reversed(suffix))


def pool_fixture() -> tuple[list[dict[str, object]], dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    rows = []
    sources = {}
    private = {}
    for index in range(137):
        candidate = f"cand_{index:032x}"
        sequence = sequence_for(index)
        band = "moderate" if index % 2 == 0 else "strong"
        score = Decimal("1") - Decimal(index) / Decimal("1000")
        rows.append({
            "rank": index + 1,
            "candidate": candidate,
            "score": score,
            "score_text": str(score),
            "compatibility": band,
            "shuffle": "pass",
            "length": 20,
            "sequence": sequence,
            "exact_export_row_index": index,
            "control_percentile": Decimal("0.8") if band == "moderate" else Decimal("0.96"),
            "control_percentile_text": "0.8" if band == "moderate" else "0.96",
            "mismatch": Decimal(index),
            "mismatch_text": str(index),
            "band": band,
        })
        sources[candidate] = {
            "source_candidate_id": f"source_{index}",
            "sequence_sha256": module.sha256_bytes(sequence.encode("ascii")),
            "length": 20,
            "source_record_ids": [f"record_{index}"],
        }
        seed = "43" if index % 2 == 0 else "44"
        block = "A" if seed == "43" else "B"
        private[candidate] = {
            "length": 20,
            "source_occurrences": [{
                "source_identity": f"record_{index}",
                "provenance": {
                    "d1_training_seed": int(seed),
                    "technical_block": block,
                },
            }],
        }
    return rows, sources, private


class Section10AnalysisTests(unittest.TestCase):
    def test_pool_uses_tier1_order_not_band_order_and_caps_at_100(self):
        rows, sources, private = pool_fixture()
        eligible, pool = module.build_pool(rows, sources, private)
        self.assertEqual(len(eligible), 137)
        self.assertEqual(len(pool), 100)
        self.assertEqual(pool[0]["band"], "moderate")
        self.assertEqual(pool[1]["band"], "strong")
        self.assertEqual([row["rank"] for row in pool], list(range(1, 101)))

    def test_pool_requires_shuffle_pass_and_favourable_band(self):
        rows, sources, private = pool_fixture()
        rows[0]["shuffle"] = "fail"
        with self.assertRaises(module.Section10AnalysisError):
            module.build_pool(rows, sources, private)
        rows[0]["shuffle"] = "pass"
        rows[0]["band"] = "weak"
        with self.assertRaises(module.Section10AnalysisError):
            module.build_pool(rows, sources, private)

    def test_restricted_outputs_include_dashboard_numbers_sequences_and_blank_decisions(self):
        rows, sources, private = pool_fixture()
        _, pool = module.build_pool(rows, sources, private)
        outputs = module.build_restricted_outputs(pool)
        numbers = outputs["dashboard_candidate_numbers.txt"].decode().splitlines()
        self.assertEqual(numbers[:3], ["1", "2", "3"])
        self.assertEqual(len(numbers), 100)
        sequence_text = outputs["supervisor_review_sequences.txt"].decode()
        self.assertIn(sequence_for(0), sequence_text)
        records = [json.loads(line) for line in outputs["supervisor_review_records.jsonl"].decode().splitlines()]
        self.assertEqual(len(records), 100)
        self.assertEqual(records[0]["manual_review"], {
            "decision": None,
            "reason": None,
            "review_date": None,
            "supervisor": None,
        })

    def test_public_privacy_rejects_ids_and_sequences(self):
        rows, sources, private = pool_fixture()
        _, pool = module.build_pool(rows, sources, private)
        with self.assertRaises(module.Section10AnalysisError):
            module.ensure_public({"report": str(pool[0]["candidate"]).encode()}, pool)
        with self.assertRaises(module.Section10AnalysisError):
            module.ensure_public({"report": str(pool[0]["sequence"]).encode()}, pool)

    def test_percentage_and_type7_summary(self):
        self.assertEqual(module.percent(29583, 30000), "98.61")
        rows = [{"score": Decimal(value)} for value in ("1", "2", "3", "4")]
        summary = module.score_summary(rows, "score")
        self.assertEqual(summary["q1_type7"], "1.75")
        self.assertEqual(summary["median_type7"], "2.5")
        self.assertEqual(summary["q3_type7"], "3.25")

    def test_tie_aware_spearman(self):
        left = [Decimal("1"), Decimal("2"), Decimal("2"), Decimal("4")]
        right = [Decimal("4"), Decimal("2"), Decimal("2"), Decimal("1")]
        self.assertAlmostEqual(module.spearman_rho(left, right), -1.0)

    def test_status_is_provisional_and_cannot_commit_result(self):
        self.assertIn("PROVISIONAL", module.STATUS)
        self.assertIn("INDEPENDENT_REVIEW", module.STATUS)
        self.assertIn("EXPLICIT_RESULT_COMMITMENT", module.STATUS)


if __name__ == "__main__":
    unittest.main()

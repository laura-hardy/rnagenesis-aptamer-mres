#!/usr/bin/env python3
"""Focused tests for the Section 9 result-analysis adapter."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODELLING = ROOT / "scripts" / "modelling"
sys.path.insert(0, str(MODELLING))
SPEC = importlib.util.spec_from_file_location(
    "section9_analyze_results",
    MODELLING / "aptarank_section9_analyze_results.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

CID_A = "cand_00000000000000000000000000000000"
CID_B = "cand_11111111111111111111111111111111"
SEQ_A = "ACGUACGUACGUACGUACGU"
SEQ_B = "GGGGAAAACCCCUUUUGGGG"


def csv_bytes(header: str, rows: list[str]) -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode()


class Section9AnalysisTests(unittest.TestCase):
    def test_type7_quantiles(self):
        values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]
        self.assertEqual(module.quantile_type7(values, Decimal("0.25")), Decimal("1.75"))
        self.assertEqual(module.quantile_type7(values, Decimal("0.5")), Decimal("2.5"))
        self.assertEqual(module.quantile_type7(values, Decimal("0.75")), Decimal("3.25"))

    def test_export_joins_by_id_and_sorts_by_rank(self):
        upload = {CID_A: SEQ_A, CID_B: SEQ_B}
        payload = csv_bytes(
            ",".join(module.EXPORT_FIELDS),
            [
                f"2,{CID_A},0.4,weak,fail,20,{SEQ_A}",
                f"1,{CID_B},0.8,strong,pass,20,{SEQ_B}",
            ],
        )
        rows = module.validate_export(payload, upload)
        self.assertEqual([row["candidate"] for row in rows], [CID_B, CID_A])

    def test_export_rejects_score_order_and_bad_tokens(self):
        upload = {CID_A: SEQ_A, CID_B: SEQ_B}
        bad_order = csv_bytes(
            ",".join(module.EXPORT_FIELDS),
            [
                f"1,{CID_A},0.4,weak,fail,20,{SEQ_A}",
                f"2,{CID_B},0.8,strong,pass,20,{SEQ_B}",
            ],
        )
        with self.assertRaises(module.Section9AnalysisError):
            module.validate_export(bad_order, upload)
        bad_token = bad_order.replace(b",weak,", b",unknown,")
        with self.assertRaises(module.Section9AnalysisError):
            module.validate_export(bad_token, upload)

    def test_source_key_is_digest_bound_and_sequence_free(self):
        upload = {CID_A: SEQ_A}
        document = {
            "package_id": module.PACKAGE_ID,
            "sequence_strings_included": False,
            "memberships": [{
                "candidate_id": CID_A,
                "condition": "B0",
                "length": 20,
                "sequence_sha256": module.sha256_bytes(SEQ_A.encode()),
            }],
        }
        payload = module.canonical_json(document)
        by_id = module.validate_source_key(payload, upload)
        self.assertEqual(by_id[CID_A]["condition"], "B0")
        document["memberships"][0]["sequence_sha256"] = "0" * 64
        with self.assertRaises(module.Section9AnalysisError):
            module.validate_source_key(module.canonical_json(document), upload)

    def test_summary_keeps_tiers_separate(self):
        rows = [
            {"score": Decimal("0.8"), "compatibility": "strong", "shuffle": "fail"},
            {"score": Decimal("0.2"), "compatibility": "weak", "shuffle": "pass"},
        ]
        summary = module.summarize(rows)
        self.assertEqual(summary["aptamer_likeness"]["median_type7"], "0.5")
        self.assertEqual(summary["shuffle"], {"pass": 1, "fail": 1})
        self.assertEqual(summary["compatibility_favourable_strong_or_moderate"], 1)
        self.assertEqual(summary["tier_cross_tabulation"]["strong"]["fail"], 1)

    def test_run_record_requires_exact_cavity_warning(self):
        raw_csv, raw_pdf = b"csv", b"pdf"
        manifest = {
            "package_id": module.PACKAGE_ID,
            "artifacts": {
                "downloaded_shortlist": {"byte_count": 3, "path": "raw/run_ndm1_section9_1134.csv", "sha256": module.sha256_bytes(raw_csv)},
                "result_pdf": {"byte_count": 3, "path": "raw/section9_ndm1_1134.pdf", "sha256": module.sha256_bytes(raw_pdf)},
            },
            "download_accounting": {"exclusion_register_available": False, "other_raw_artifacts_available": False, "scored_rows": 800, "uploaded_rows": 800},
        }
        visual = {
            "package_id": module.PACKAGE_ID,
            "target_geometry": {"warning_exact": module.CAVITY_WARNING},
            "tier_relationship_display": {"n": 800, "p_value": 0.0421, "raw_tier2_numeric_values_exported": False, "spearman_rho": -0.072},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "records").mkdir()
            (root / "records/raw_artifact_manifest.json").write_text(json.dumps(manifest))
            (root / "records/pdf_visual_review.json").write_text(json.dumps(visual))
            module.validate_run_records(root, raw_csv, raw_pdf)
            visual["target_geometry"]["warning_exact"] = "altered"
            (root / "records/pdf_visual_review.json").write_text(json.dumps(visual))
            with self.assertRaises(module.Section9AnalysisError):
                module.validate_run_records(root, raw_csv, raw_pdf)

    def test_adapter_pins_v37_and_cannot_commit_results(self):
        self.assertEqual(module.PLAN_SHA256, "24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9")
        self.assertIn("PROVISIONAL", module.STATUS)
        self.assertIn("EXPLICIT_RESULT_COMMITMENT", module.STATUS)


if __name__ == "__main__":
    unittest.main()

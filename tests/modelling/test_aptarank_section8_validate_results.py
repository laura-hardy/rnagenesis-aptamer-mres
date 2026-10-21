#!/usr/bin/env python3
"""Focused tests for the Section 8 technical-validation adapter."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODELLING = ROOT / "scripts" / "modelling"
sys.path.insert(0, str(MODELLING))
SPEC = importlib.util.spec_from_file_location(
    "section8_validate_results",
    MODELLING / "aptarank_section8_validate_results.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


CID_A = "cand_00000000000000000000000000000000"
CID_B = "cand_11111111111111111111111111111111"


def csv_bytes(header: str, rows: list[str]) -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")


class Section8ValidationTests(unittest.TestCase):
    def test_upload_and_export_join_by_id_not_row_position(self):
        upload = csv_bytes("id,sequence", [f"{CID_A},ACGU", f"{CID_B},GGAA"])
        _, by_id = module.parse_upload(upload)
        export = csv_bytes(
            "rank,candidate,aptamer-likeness,compatibility,shuffle,len,sequence",
            [
                f"2,{CID_A},0.5,weak,fail,4,ACGU",
                f"1,{CID_B},0.7,moderate,pass,4,GGAA",
            ],
        )
        rows = module.validate_export(export, by_id)
        self.assertEqual([row["candidate"] for row in rows], [CID_B, CID_A])

    def test_export_rejects_bad_score_token_sequence_and_rank_order(self):
        upload = csv_bytes("id,sequence", [f"{CID_A},ACGU"])
        _, by_id = module.parse_upload(upload)
        templates = [
            f"1,{CID_A},1.01,weak,fail,4,ACGU",
            f"1,{CID_A},0.5,unknown,fail,4,ACGU",
            f"1,{CID_A},0.5,weak,fail,4,AAAA",
            f"2,{CID_A},0.5,weak,fail,4,ACGU",
        ]
        for row in templates:
            with self.subTest(row=row):
                export = csv_bytes(
                    "rank,candidate,aptamer-likeness,compatibility,shuffle,len,sequence",
                    [row],
                )
                with self.assertRaises(module.Section8ValidationError):
                    module.validate_export(export, by_id)

    def test_private_key_is_sequence_free_and_digest_bound(self):
        case = dict(module.CASES[0])
        sequence = "ACGU"
        document = {
            "schema_version": "mres-aptarank-section8-private-key-v1",
            "status": "RESTRICTED_DO_NOT_UPLOAD_OR_COMMIT",
            "package_id": case["package_id"],
            "panel_id": module.PANEL_ID,
            "join_key": "candidate_id",
            "row_position_is_join_key": False,
            "sequence_strings_included": False,
            "candidates": [{
                "candidate_id": CID_A,
                "case_id": case["case_id"],
                "target_config_id": case["target_config_id"],
                "class_label": "eval_cognate_core",
                "sequence_core_sha256": module.sha256_bytes(sequence.encode()),
                "length": 4,
                "cluster_id": "cluster_1",
            }],
        }
        module.validate_private_key(document, case, {CID_A: sequence})
        document["candidates"][0]["sequence"] = sequence
        with self.assertRaises(module.Section8ValidationError):
            module.validate_private_key(document, case, {CID_A: sequence})

    def test_run_sheet_requires_evaluation_42_99_200(self):
        case = dict(module.CASES[0])
        upload = b"upload"
        private = b"private"
        expected_cells = b"expected"
        document = {
            "schema_version": "mres-aptarank-section8-run-sheet-v1",
            "package_id": case["package_id"],
            "panel_id": module.PANEL_ID,
            "settings": {
                "preset": "Evaluation",
                "seed": 42,
                "candidate_shuffled_controls": 99,
                "ensemble_samples": 200,
                "composite_method": "corpus_weighted_mean",
            },
            "target": {
                "target_config_id": case["target_config_id"],
                "pdb_id": case["pdb_id"],
                "chain": case["chain"],
                "binding_mode": case["binding_mode"],
                "target_freeze_sha256": case["target_freeze_sha256"],
                "target_config_sha256": case["target_config_sha256"],
                "structure_sha256": case["structure_sha256"],
            },
            "inputs": {
                "candidate_upload": module.byte_record(upload),
                "private_key": module.byte_record(private),
                "expected_cell_manifest": module.byte_record(expected_cells),
                "reference_upload": {"sha256": module.REFERENCE_SHA256, "row_count": 113},
            },
        }
        module.validate_run_sheet(document, case, upload, private, expected_cells)
        document["settings"]["candidate_shuffled_controls"] = 20
        with self.assertRaises(module.Section8ValidationError):
            module.validate_run_sheet(document, case, upload, private, expected_cells)

    def test_visual_review_keeps_raw_tier2_score_unavailable(self):
        case = dict(module.CASES[0])
        pdf = b"pdf"
        rows = [{"compatibility": "weak"}]
        run_sheet = {"settings": {"candidate_shuffled_controls": 99, "seed": 42}}
        raw_manifest = {"displayed_settings": {
            "candidate_shuffles": 99,
            "seed": 42,
            "ranking_runtime_seconds": 0,
            "composite_method": "corpus_weighted_mean",
            "scoring_signature": "95a49467ef3c6186",
        }}
        document = {
            "schema_version": "mres-aptarank-section8-pdf-visual-review-v1",
            "status": "VISUALLY_REVIEWED_SOURCE_HASH_PINNED",
            "automated_content_extraction": False,
            "layout_readable": True,
            "source_pdf": module.byte_record(pdf),
            "visual_observations": {
                "accounting": {"candidates": 1, "scored": 1},
                "displayed_settings": {
                    **raw_manifest["displayed_settings"],
                    "sampled_structures_displayed": False,
                },
                "target": {"pdb_id": case["pdb_id"], "chain": case["chain"]},
                "compatibility": {
                    "bank_realized_count": 5085,
                    "bank_identifier_exposed": False,
                    "bank_content_hash_exposed": False,
                    "raw_numeric_tier2_score_exposed": False,
                    "bands": {"weak": 1, "moderate_threshold": 0.75, "strong_threshold": 0.95},
                },
                "known_interface_marker": {
                    "publication_eligible_false_displayed": True,
                    "treatment": "ignored under the documented decision",
                },
            },
        }
        module.validate_visual_review(document, case, pdf, rows, run_sheet, raw_manifest)
        document["visual_observations"]["compatibility"]["raw_numeric_tier2_score_exposed"] = True
        with self.assertRaises(module.Section8ValidationError):
            module.validate_visual_review(document, case, pdf, rows, run_sheet, raw_manifest)

    def test_sha256_manifest_requires_two_space_format_and_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = b"evidence\n"
            (root / "evidence.txt").write_bytes(payload)
            digest = module.sha256_bytes(payload)
            module.validate_sha256_manifest(
                f"{digest}  evidence.txt\n".encode("ascii"), root, "test manifest"
            )
            with self.assertRaises(module.Section8ValidationError):
                module.validate_sha256_manifest(
                    f"{digest} evidence.txt\n".encode("ascii"), root, "test manifest"
                )

    def test_public_outputs_reject_ids_sequences_and_private_bytes(self):
        with self.assertRaises(module.Section8ValidationError):
            module.ensure_public({"summary": CID_A.encode()}, [b"ACGU", b"private"])
        with self.assertRaises(module.Section8ValidationError):
            module.ensure_public({"summary": b"contains ACGU"}, [b"ACGU", b"private"])
        with self.assertRaises(module.Section8ValidationError):
            module.ensure_public({"summary": b"contains private"}, [b"ACGU", b"private"])

    def test_adapter_pins_v37_and_never_authorizes_interpretation(self):
        self.assertEqual(module.PLAN_SHA256, "24ae601f4c9bf64325ec8aa509ef7a5eafefd5b77a7610fbd014554e16553db9")
        self.assertEqual(module.PREPARATION_SHA256, "952d201b81bfd6c1939577f20530dc52d13d7eec86b032ddece4c77863558e78")
        self.assertIn("INTERPRETATION_AND_COMMITMENT_PENDING", module.STATUS)
        self.assertEqual({case["binding_mode"] for case in module.CASES}, {"pocket", "surface"})


if __name__ == "__main__":
    unittest.main()

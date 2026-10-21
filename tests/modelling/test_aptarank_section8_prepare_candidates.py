"""Synthetic checks for the Section 8 production-preparation adapter."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from scripts.modelling import aptarank_section8_prepare_candidates as section8


def synthetic_row(sequence: str, identity: str, sequence_id: str, cluster: str) -> dict[str, str]:
    return {
        "scientific_identity_id": identity,
        "sequence_core": sequence,
        "sequence_length_core": str(len(sequence)),
        "sequence_core_sha256": hashlib.sha256(sequence.encode("utf-8")).hexdigest(),
        "sequence_id": sequence_id,
        "cluster_id": cluster,
        "target_dictionary_id": "TD_SYN",
        "canonical_target_name": "Synthetic target",
        "contributing_pubmed_ids": "1",
        "publication": "synthetic",
        "source_db": "synthetic",
        "source_dataset": "fixture",
    }


class Section8PreparationTests(unittest.TestCase):
    def test_candidate_id_matches_frozen_m9b2_encoding(self):
        sequence = "ACGU" * 5
        secret = bytes(range(32))
        payload = section8.length_delimited([section8.ID_DOMAIN, sequence])
        expected = "cand_" + hmac.new(secret, payload, hashlib.sha256).digest()[:16].hex()
        self.assertEqual(section8.candidate_id(sequence, secret), expected)

    def test_selection_reconciles_upload_private_key_and_expected_cells(self):
        sequences = ["ACGU" * 5, "UGCA" * 6]
        rows = [
            synthetic_row(sequences[0], "sid-1", "seq-1", "cluster-1"),
            synthetic_row(sequences[1], "sid-2", "seq-2", "cluster-1"),
        ]
        case = {
            "case_id": "synthetic_case",
            "package_id": "synthetic_package",
            "target_dictionary_id": "TD_SYN",
            "target_config_id": "synthetic_config",
            "expected_identity_count": 2,
            "expected_core_count": 2,
            "expected_cluster_count": 1,
            "expected_core_sha256": sorted(row["sequence_core_sha256"] for row in rows),
        }
        upload, private_key, ids = section8.select_case(rows, case, bytes(range(32)))
        parsed = list(csv.DictReader(io.StringIO(upload.decode("utf-8"), newline="")))
        self.assertEqual([row["id"] for row in parsed], ids)
        self.assertEqual(ids, sorted(ids))
        private_document = json.loads(private_key)
        self.assertEqual(sorted(row["candidate_id"] for row in private_document["candidates"]), ids)
        for sequence in sequences:
            self.assertNotIn(sequence, private_key.decode("utf-8"))

        expected = section8.expected_cells(case, ids)
        run_case = {
            **case,
            "pdb_id": "1SYN",
            "chain": "A",
            "binding_mode": "surface",
            "site_residues": [1],
            "site_rule": "synthetic",
            "target_freeze_sha256": "0" * 64,
            "target_config_sha256": "1" * 64,
            "structure_sha256": "2" * 64,
        }
        run = section8.run_sheet(run_case, upload, private_key, expected)
        run_document = json.loads(run)
        self.assertEqual(run_document["settings"]["preset"], "Evaluation")
        self.assertEqual(run_document["settings"]["candidate_shuffled_controls"], 99)
        self.assertEqual(run_document["settings"]["ensemble_samples"], 200)
        self.assertNotEqual(run_document["settings"]["scoring_signature"], "6dec9dc463a8fde1")
        report = json.loads(section8.validation_report(run_case, upload, private_key, expected, run))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["denominators"]["upload_rows"], 2)

    def test_publication_refuses_existing_destination_and_preserves_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "new-package"
            section8.publish_directory(
                destination,
                {"upload/candidate_upload.csv": b"id,sequence\n"},
                {"upload/candidate_upload.csv"},
            )
            self.assertEqual((destination / "upload/candidate_upload.csv").read_bytes(), b"id,sequence\n")
            self.assertEqual((destination / "upload/candidate_upload.csv").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(section8.PreparationError):
                section8.publish_directory(destination, {"x": b"x"})


if __name__ == "__main__":
    unittest.main()

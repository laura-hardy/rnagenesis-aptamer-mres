#!/usr/bin/env python3
"""Focused tests for the v3.10 future-shortlisting procedure."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


STAGE_ROOT = Path(__file__).resolve().parents[2]
REPO = Path("/Users/laura/Desktop/rnagenesis-aptamer-mres")
sys.path.insert(0, str(REPO))
SPEC = importlib.util.spec_from_file_location(
    "aptarank_future_shortlisting",
    STAGE_ROOT / "scripts/modelling/aptarank_future_shortlisting.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def sequence_for(index: int) -> str:
    alphabet = "ACGU"
    return "ACGUACGUACGU" + "".join(alphabet[(index // (4 ** shift)) % 4] for shift in range(7, -1, -1))


def fixture():
    full = []
    exact = []
    source = {}
    private = {}
    for index in range(1000):
        rank = index + 1
        candidate = f"cand_{index:032x}"
        sequence = sequence_for(index)
        score = f"{1 - index / 2000:.6f}"
        band = "strong" if index % 3 == 0 else "moderate" if index % 3 == 1 else "weak"
        percentile = "0.96" if band == "strong" else "0.8" if band == "moderate" else "0.2"
        shuffle = "fail" if index % 5 == 0 else "pass"
        full.append({
            "rank": str(rank), "candidate": candidate, "aptamer-likeness": score,
            "compatibility": band, "shuffle": shuffle, "len": "20", "sequence": sequence,
        })
        exact.append({
            "": str(index), "candidate": candidate, "rank": str(rank), "tier1": score,
            "control_percentile": percentile, "mismatch": str(index + 0.5), "band": band,
            "selected": "true",
        })
        digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
        record = f"record_{index}"
        seed = 43 if index % 2 == 0 else 44
        block = "A" if seed == 43 else "B"
        source[candidate] = {
            "condition": "D1", "length": 20, "multiplicity": 1,
            "sequence_sha256": digest, "source_candidate_id": f"D1-U{index + 1}",
            "source_record_ids": [record],
        }
        private[candidate] = {
            "condition": "D1", "length": 20, "multiplicity": 1,
            "source_occurrences": [{
                "source_identity": record,
                "provenance": {
                    "checkpoint_identity": f"checkpoint_{index}",
                    "d1_training_seed": seed,
                    "generation_seed": 800000 + index,
                    "invocation_index": index,
                    "master_attempt_index": index,
                    "requested_biological_length": 20,
                    "source_artifact_id": "d1:m8-combined-raw-attempt-ledger",
                    "source_artifact_sha256": module.SOURCE_ARTIFACT_SHA256,
                    "technical_block": block,
                },
            }],
        }
    # The production denominator is checked before selecting, so pad full to 29,583.
    full.extend({**full[-1], "rank": str(index + 1), "candidate": f"cand_{index:032x}"} for index in range(1000, 29583))
    return full, exact, source, private


class FutureShortlistingTests(unittest.TestCase):
    def test_tier1_ranks_1_to_50_are_selected_regardless_of_annotations(self):
        full, exact, source, private = fixture()
        rows = module.select_and_enrich(full, exact, source, private)
        self.assertEqual(len(rows), 50)
        self.assertEqual([row["aptarank_tier1_rank"] for row in rows], list(range(1, 51)))
        self.assertIn("fail", {row["shuffle_annotation"] for row in rows})
        self.assertIn("weak", {row["tier2_band_annotation"] for row in rows})

    def test_sequence_and_full_provenance_are_preserved(self):
        full, exact, source, private = fixture()
        row = module.select_and_enrich(full, exact, source, private)[0]
        self.assertEqual(row["sequence"], sequence_for(0))
        self.assertEqual(row["d1_source_candidate_id"], "D1-U1")
        self.assertEqual(row["d1_provenance"]["source_record_id"], "record_0")
        self.assertEqual(row["d1_provenance"]["d1_training_seed"], 43)
        self.assertFalse(row["d1_provenance"]["requested_length_differs_from_realised_sequence"])

    def test_requested_and_realised_lengths_are_distinct_provenance_fields(self):
        full, exact, source, private = fixture()
        private[full[0]["candidate"]]["source_occurrences"][0]["provenance"]["requested_biological_length"] = 30
        row = module.select_and_enrich(full, exact, source, private)[0]
        self.assertEqual(row["length_nt"], 20)
        self.assertEqual(row["d1_provenance"]["requested_biological_length"], 30)
        self.assertTrue(row["d1_provenance"]["requested_length_differs_from_realised_sequence"])

    def test_exact_export_mismatch_fails_closed(self):
        full, exact, source, private = fixture()
        exact[0]["candidate"] = exact[1]["candidate"]
        with self.assertRaises(module.FutureShortlistingError):
            module.select_and_enrich(full, exact, source, private)

    def test_missing_provenance_fails_closed(self):
        full, exact, source, private = fixture()
        private.pop(full[0]["candidate"])
        with self.assertRaises(module.FutureShortlistingError):
            module.select_and_enrich(full, exact, source, private)

    def test_outputs_state_no_experimental_progression(self):
        full, exact, source, private = fixture()
        rows = module.select_and_enrich(full, exact, source, private)
        outputs = module.build_outputs(rows, {"synthetic": {"sha256": "0" * 64, "byte_count": 0}})
        decision = json.loads(outputs["future_shortlisting_decision_record.json"])
        self.assertEqual(decision["advanced_to_experimental_validation"], 0)
        self.assertEqual(decision["retained_as_progressing_towards_future_shortlisting"], 50)
        self.assertIn(sequence_for(0), outputs["future_shortlisting_sequences.fasta"].decode())

    def test_status_and_plan_are_final_and_versioned(self):
        self.assertEqual(module.STATUS, "FUTURE_SHORTLISTING_SET_SCIENTIFICALLY_COMMITTED")
        self.assertTrue(module.PLAN_RELATIVE.endswith("v3_10.md"))


if __name__ == "__main__":
    unittest.main()

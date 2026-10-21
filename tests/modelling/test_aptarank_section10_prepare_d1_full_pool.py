#!/usr/bin/env python3
"""Focused tests for the Section 10 full-pool D1 preparer."""

from __future__ import annotations

import csv
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from scripts.modelling import aptarank_candidate_preparation as m9b
from scripts.modelling import aptarank_section9_prepare_candidates as section9
from scripts.modelling import aptarank_section10_prepare_d1_full_pool as section10


ARTIFACT_SHA = "a" * 64


def sequence(index: int, length: int) -> str:
    alphabet = "ACGU"
    output = []
    value = index
    for _ in range(length):
        output.append(alphabet[value % 4])
        value //= 4
    return "".join(output)


def source_payload(rows: list[tuple[str, str, int, str]]) -> bytes:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=list(section9.SOURCES["D1"]["header"]), lineterminator="\n")
    writer.writeheader()
    for source_id, seq, seed, block in rows:
        writer.writerow({
            "condition": "D1",
            "source_candidate_id": source_id,
            "sequence": seq,
            "sequence_length": len(seq),
            "condition_multiplicity": 1,
            "first_record_id": "d1:record:" + source_id[-5:],
            "d1_training_seed": seed,
            "technical_block": block,
        })
    return handle.getvalue().encode()


def membership_payload(rows: list[tuple[str, str, int, str]]) -> bytes:
    output = []
    for index, (source_id, seq, seed, block) in enumerate(rows):
        record_id = "d1:record:" + source_id[-5:]
        document = {
            "condition": "D1",
            "source_candidate_id": source_id,
            "record_id": record_id,
            "multiplicity_group": source_id,
            "condition_multiplicity": 1,
            "parsed_length": len(seq),
            "first_record_id": record_id,
            "is_valid_canonical": True,
            "occurrence_index": 1,
            "is_first_occurrence": True,
            "checkpoint_identity": "d1:checkpoint",
            "generation_seed": 800000 + index,
            "requested_biological_length": max(1, len(seq)),
            "invocation_index": index,
            "master_attempt_index": index,
            "technical_block": block,
            "d1_training_seed": seed,
            "source_artifact_id": "d1:artifact",
            "source_artifact_sha256": ARTIFACT_SHA,
        }
        output.append(json.dumps(document, separators=(",", ":")).encode() + b"\n")
    return b"".join(output)


class Section10PreparationTests(unittest.TestCase):
    def synthetic_records(self):
        rows = [
            ("D1-U00001", sequence(1, 10), 43, "A"),
            ("D1-U00002", sequence(2, 20), 43, "A"),
            ("D1-U00003", sequence(3, 101), 44, "B"),
        ]
        source_spec = {**section9.SOURCES["D1"], "rows": 3, "eligible": 1, "below": 1, "above": 1}
        expected = {
            "upload_rows": 3,
            "length_below_20": 1,
            "length_20_through_100": 1,
            "length_above_100": 1,
            "training_seed_43": 2,
            "training_seed_44": 1,
            "technical_block_A": 2,
            "technical_block_B": 1,
        }
        with (
            patch.dict(section9.SOURCES, {**section9.SOURCES, "D1": source_spec}, clear=True),
            patch.object(section10, "SOURCE_ROWS", 3),
            patch.object(section10, "MEMBERSHIP_ROWS", 3),
            patch.object(section10, "ATTEMPT_ROWS_BY_CONDITION", {"D1": 3}),
            patch.object(section10, "EXPECTED_COUNTS", expected),
        ):
            records, sources, accounting = section10.build_full_d1_records(
                source_payload(rows), membership_payload(rows)
            )
        return rows, records, sources, accounting

    def test_full_pool_keeps_out_of_range_lengths(self):
        rows, records, sources, accounting = self.synthetic_records()
        self.assertEqual(len(records), 3)
        self.assertEqual(sorted(row["length"] for row in records), [10, 20, 101])
        self.assertEqual(accounting["length_below_20"], 1)
        self.assertEqual(accounting["length_above_100"], 1)
        self.assertEqual(set(sources), {row[1] for row in rows})

    def test_fresh_opaque_upload_and_private_keys_reconcile(self):
        _, records, sources, _ = self.synthetic_records()
        key = b"k" * 32
        sequences = sorted(sources)
        ids = m9b.assign_candidate_ids(sequences, key, m9b.TRUNCATION_BYTES)
        upload = m9b._candidate_upload_bytes(sequences, ids)
        with patch.object(section10, "SOURCE_ROWS", 3):
            upload_rows = section10.validate_upload(upload, ids, sources)
        private = m9b._private_key_bytes(records, ids)
        source_key = json.loads(section10.build_source_candidate_key(upload_rows, private, sources))
        self.assertEqual(len(upload_rows), 3)
        self.assertEqual(len(source_key["memberships"]), 3)
        self.assertFalse(source_key["sequence_strings_included"])
        for row in private.decode().splitlines():
            self.assertNotIn("sequence", json.loads(row))

    def test_review_rule_pools_bands_and_orders_by_tier1(self):
        rule = json.loads(section10.review_pool_rule())
        self.assertFalse(rule["strong_precedes_moderate"])
        self.assertEqual(rule["ordering"][0], "better_Tier_1_rank_across_pooled_favourable_class")
        self.assertIn("compatibility_token_is_strong_or_moderate_pooled_as_one_favourable_class", rule["eligibility"])
        self.assertFalse(rule["combined_tier1_tier2_numeric_score"])

    def test_run_sheet_freezes_full_upload_and_evaluation_target(self):
        upload = b"id,sequence\ncand_00000000000000000000000000000000,ACGU\n"
        payload = json.loads(section10.run_sheet(
            upload, b"private\n", b"source\n", b"expected\n", section10.target_settings(), section10.review_pool_rule()
        ))
        self.assertEqual(payload["settings"]["preset"], "Evaluation")
        self.assertEqual(payload["settings"]["candidate_shuffled_controls"], 99)
        self.assertEqual(payload["settings"]["ensemble_samples"], 200)
        self.assertEqual(payload["reporting"]["primary_ordering"], "Tier_1_rank")
        self.assertEqual(payload["inputs"]["candidate_upload"]["row_count"], 30000)

    def test_adapter_pins_v38_and_does_not_run_aptarank(self):
        self.assertEqual(section10.PLAN_SHA256, "8cf982180663ad8591583bd5e37613be4ce8234cfc8a2b82822a36b756d661dc")
        self.assertNotIn("aptarank", {name.lower() for name in section10.prepare.__code__.co_names if "run" in name.lower()})


if __name__ == "__main__":
    unittest.main()

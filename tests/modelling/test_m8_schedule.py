#!/usr/bin/env python3
"""Deterministic M8 schedule tests. CPU only. No model, GPU, or sequence text."""

from __future__ import annotations

import os
import random
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import m8_support as support

schedule = support.schedule


class ScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = support.pinned_vector_bytes()
        cls.lengths = schedule.assert_pinned_length_vector(cls.raw)
        cls.built = schedule.build_schedule(cls.lengths)

    def test_vector_hash_and_count(self):
        self.assertEqual(schedule.sha256_bytes(self.raw), schedule.LENGTH_VECTOR_SHA256)
        self.assertEqual(len(self.lengths), 669)

    def test_eighty_nine_lengths_between_20_and_123(self):
        histogram = self.built["histogram"]["lengths"]
        self.assertEqual(len(histogram), 89)
        self.assertEqual(histogram[0]["biological_length"], 20)
        self.assertEqual(histogram[-1]["biological_length"], 123)
        self.assertEqual([row["biological_length"] for row in histogram], sorted(row["biological_length"] for row in histogram))

    def test_quota_total_is_30000(self):
        rows = self.built["quota_allocation"]["rows"]
        self.assertEqual(sum(row["quota"] for row in rows), 30000)

    def test_length_87_loses_the_exact_remainder_tie_to_shorter_lengths(self):
        rows = schedule.largest_remainder_quotas(self.lengths)
        target = [row for row in rows if row["biological_length"] == 87][0]
        tied = [row for row in rows if row["remainder"] == target["remainder"]]
        self.assertGreater(len(tied), 1)
        self.assertFalse(target["received_extra_seat"])
        winners = [row for row in tied if row["received_extra_seat"]]
        losers = [row for row in tied if not row["received_extra_seat"]]
        self.assertTrue(winners)
        self.assertTrue(all(row["biological_length"] < target["biological_length"] for row in winners))
        self.assertTrue(all(row["biological_length"] <= min(item["biological_length"] for item in losers) or row in winners for row in tied))
        synthetic = schedule.allocate_largest_remainder(
            [
                {"biological_length": 30, "empirical_count": 1},
                {"biological_length": 10, "empirical_count": 1},
                {"biological_length": 20, "empirical_count": 1},
            ],
            4,
            3,
        )
        by_length = {row["biological_length"]: row for row in synthetic}
        self.assertTrue(by_length[10]["received_extra_seat"])
        self.assertFalse(by_length[20]["received_extra_seat"])
        self.assertFalse(by_length[30]["received_extra_seat"])
        self.assertEqual(by_length[10]["remainder"], by_length[30]["remainder"])

    def test_blocks_total_15000_and_differ_by_at_most_one(self):
        rows = self.built["quota_allocation"]["rows"]
        self.assertEqual(sum(row["block_a_count"] for row in rows), 15000)
        self.assertEqual(sum(row["block_b_count"] for row in rows), 15000)
        self.assertTrue(all(abs(row["block_a_count"] - row["block_b_count"]) <= 1 for row in rows))

    def test_odd_strata_alternate_starting_with_a(self):
        synthetic = schedule.split_block_counts(
            [
                {"biological_length": 20, "quota": 4},
                {"biological_length": 21, "quota": 5},
                {"biological_length": 22, "quota": 7},
                {"biological_length": 23, "quota": 2},
                {"biological_length": 24, "quota": 9},
            ]
        )
        self.assertEqual([row["block_a_count"] for row in synthetic], [2, 3, 3, 1, 5])
        self.assertEqual([row["block_b_count"] for row in synthetic], [2, 2, 4, 1, 4])

    def test_requested_nucleotide_totals(self):
        self.assertEqual(schedule.nucleotide_total(self.lengths, "A"), 830348)
        self.assertEqual(schedule.nucleotide_total(self.lengths, "B"), 830404)

    def test_invocation_counts_shapes_and_seeds(self):
        block_a = self.built["invocations"]["A"]["invocations"]
        block_b = self.built["invocations"]["B"]["invocations"]
        self.assertEqual(len(block_a), 163)
        self.assertEqual(len(block_b), 164)
        self.assertEqual([row["generation_seed"] for row in block_a], list(range(800000, 800163)))
        self.assertEqual([row["generation_seed"] for row in block_b], list(range(900000, 900164)))
        self.assertEqual(set(row["generation_seed"] for row in block_a).intersection(row["generation_seed"] for row in block_b), set())
        for invocation in block_a + block_b:
            self.assertGreater(invocation["batch_size"], 0)
            self.assertGreater(invocation["batch_num"], 0)
            self.assertEqual(invocation["max_seq_len"], invocation["requested_biological_length"] + 1)
            self.assertNotIn(0, (invocation["batch_size"], invocation["batch_num"]))
            if invocation["kind"] == "full_group":
                self.assertEqual(invocation["batch_size"], 16)
            else:
                self.assertEqual(invocation["kind"], "remainder")
                self.assertEqual(invocation["batch_num"], 1)
                self.assertLess(invocation["batch_size"], 16)
            if invocation["batch_num"] > 1:
                self.assertEqual(invocation["batch_size"], 16)
                self.assertEqual(invocation["kind"], "full_group")
        self.assertTrue(any(row["batch_num"] > 1 for row in block_a))

    def test_master_indexes_are_complete(self):
        rows = self.built["master_attempt_map"]["rows"]
        indexes = [row["master_attempt_index"] for row in rows]
        self.assertEqual(indexes, list(range(30000)))
        self.assertEqual(len(indexes), len(set(indexes)))
        self.assertEqual(sum(1 for row in rows if row["block"] == "A"), 15000)
        self.assertEqual(sum(1 for row in rows if row["block"] == "B"), 15000)

    def test_prohibited_seed_namespaces_are_absent(self):
        used = []
        for block in ("A", "B"):
            used.extend(row["generation_seed"] for row in self.built["invocations"][block]["invocations"])
        self.assertEqual(schedule.prohibited_generation_seeds().intersection(used), set())
        for name, _values in schedule.PROHIBITED_SEED_NAMESPACES:
            self.assertNotIn(name, ("m8_block_a", "m8_block_b"))

    def test_hashes_are_reproducible_and_pinned(self):
        first = schedule.hashes_for_pinned_bytes(self.raw)
        second = schedule.hashes_for_pinned_bytes(self.raw)
        self.assertEqual(first, second)
        self.assertEqual(first, schedule.EXPECTED_SCHEDULE_HASHES)
        self.assertEqual(len(set(first.values())), len(first))

    def test_input_order_does_not_change_canonical_results(self):
        shuffled = list(self.lengths)
        random.Random(7).shuffle(shuffled)
        self.assertNotEqual(shuffled, self.lengths)
        self.assertEqual(schedule.schedule_hashes(shuffled), schedule.schedule_hashes(self.lengths))
        encoded = schedule.canonical_bytes(shuffled)
        self.assertNotEqual(schedule.sha256_bytes(encoded), schedule.LENGTH_VECTOR_SHA256)

    def test_schedule_module_has_no_model_gpu_or_sampler(self):
        with open(schedule.__file__, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("import torch", text)
        self.assertNotIn("sample_target_lengths", text)
        self.assertNotIn("cuda", text.lower())
        self.assertNotIn("generation.py", text)


if __name__ == "__main__":
    unittest.main()

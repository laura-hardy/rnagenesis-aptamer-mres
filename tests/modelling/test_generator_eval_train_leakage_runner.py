"""Synthetic tests for M9A TRAIN leakage preparation.

Sequences, ledgers, and TRAIN tables in this module are constructed in memory.
No production JSONL, TRAIN, VALIDATION, REF, EVAL, model, checkpoint, structure
tool, or AptaRank resource is opened. The sealed production entry point is not
called. A passing run is not production validation.
"""

from __future__ import annotations

import ast
import copy
import csv
import hashlib
import io
import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)

import generator_eval_derived_ledger as derived
import generator_eval_overlap_leakage as leakage
import generator_eval_parser as biological
import generator_eval_production_ledger as production
import generator_eval_train_leakage_runner as runner
from m6_diagnostic_generation import edit_distance

ORDER = "UUUUUUUUUUUU"
MATCH = "ACGUACGUACGU"
UNEQUAL = "ACGUACGUACGUA"
TIED = "ACGUACGU"
TIE_A = "ACGUACGG"
TIE_B = "ACGUACG"
MISS = "UUUUAAAACCCC"
NON_ACGU = "ACGT"
SOURCE_HASH = hashlib.sha256(b"canary-source-sequence-hash").hexdigest()
PUBLICATION = 'canary-publication, "quoted"\r\nsecond'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def core_hash(core):
    return sha256(core.encode("utf-8"))


def derived_row(record_id, condition, sequence=None, *, outcome=None, seed=None):
    item = derived.blank_derived_row()
    item["record_id"] = record_id
    item["condition"] = condition
    item["parser_version"] = biological.PARSER_VERSION
    item["adapter_version"] = "m9-source-adapter-v2"
    item["source_sequence_sha256"] = SOURCE_HASH
    if outcome is None:
        outcome = biological.OUTCOME_VALID if sequence is not None else biological.OUTCOME_EMPTY
    item["outcome"] = outcome
    if outcome == biological.OUTCOME_VALID:
        item["parsed_sequence"] = sequence
        item["parsed_length"] = len(sequence)
        item["failure_reason"] = None
    elif outcome == biological.OUTCOME_NON_ACGU:
        item["parsed_sequence"] = sequence
        item["parsed_length"] = len(sequence)
        item["failure_reason"] = outcome
    else:
        item["parsed_sequence"] = None
        item["parsed_length"] = 0 if outcome == biological.OUTCOME_EMPTY else None
        item["failure_reason"] = outcome
    item["d1_training_seed"] = seed if condition == "D1" else None
    if condition == "D1" and item["d1_training_seed"] is None:
        item["d1_training_seed"] = 43
    return item


def main_groups():
    return {
        "B0": [
            derived_row("canary-attempt-b0-empty", "B0", outcome=biological.OUTCOME_EMPTY),
            derived_row("canary-attempt-b0-miss", "B0", MISS),
        ],
        "B1": [
            derived_row("canary-attempt-b1-match-1", "B1", MATCH),
            derived_row("canary-attempt-b1-match-2", "B1", MATCH),
            derived_row("canary-attempt-b1-unequal", "B1", UNEQUAL),
        ],
        "B2": [
            derived_row("canary-attempt-b2-tie-1", "B2", TIED),
            derived_row("canary-attempt-b2-tie-2", "B2", TIED),
            derived_row("canary-attempt-b2-non-acgu", "B2", NON_ACGU, outcome=biological.OUTCOME_NON_ACGU),
        ],
        "D1": [
            derived_row("canary-attempt-d1-43", "D1", MATCH, seed=43),
            derived_row("canary-attempt-d1-44-miss", "D1", MISS, seed=44),
            derived_row("canary-attempt-d1-44-unequal", "D1", UNEQUAL, seed=44),
            derived_row("canary-attempt-d1-44-tie", "D1", TIED, seed=44),
        ],
    }


def annotate(groups):
    rows = []
    for condition in ("B0", "B1", "B2", "D1"):
        rows.extend(production.annotate_exact_duplicates(groups[condition]))
    return rows


def counts_for(rows):
    counts = {condition: 0 for condition in ("B0", "B1", "B2", "D1")}
    for row in rows:
        counts[row["condition"]] += 1
    counts["combined"] = len(rows)
    return counts


def train_table():
    cores = (
        ("canary-identity-0001", ORDER, "canary-target-order", "canary-cluster-order"),
        ("canary-identity-0002", MATCH, "canary-target-match", "canary-cluster-match"),
        ("canary-identity-0003", TIE_A, "canary-target-tie-a", "canary-cluster-tie-a"),
        ("canary-identity-0004", TIE_B, "canary-target-tie-b", "canary-cluster-tie-b"),
        ("canary-identity-0005", MATCH, "canary-target-match-repeat", "canary-cluster-match-repeat"),
    )
    rows = []
    for index, (identity, core, target, cluster) in enumerate(cores):
        rows.append(
            {
                "scientific_identity_id": identity,
                "sequence_core": core,
                "sequence_core_sha256": core_hash(core),
                "sequence_length_core": str(len(core)),
                "cluster_id": cluster,
                "canonical_target_name": target,
                "partition": "FT",
                "ft_split": "TRAIN",
                "publication": PUBLICATION if index == 0 else "canary-publication",
            }
        )
    return rows


def csv_bytes(rows):
    fieldnames = list(runner.REQUIRED_TRAIN_COLUMNS) + ["publication"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def text_bytes(cores):
    return ("".join(core + "\n" for core in cores)).encode("utf-8")


def first_occurrence(rows):
    ordered = []
    seen = set()
    for row in rows:
        core = row["sequence_core"]
        if core not in seen:
            seen.add(core)
            ordered.append(core)
    return ordered


def identities_for(ledger, csv_blob, text_blob, counts, train_rows, **overrides):
    identities = {
        "m9a_contract_id": runner.M9A_CONTRACT_ID,
        "m9a_contract_sha256": runner.M9A_CONTRACT_SHA256,
        "governing_plan_sha256": runner.GOVERNING_PLAN_SHA256,
        "frozen_data_contract_sha256": runner.FROZEN_DATA_CONTRACT_SHA256,
        "runner_contract_id": runner.RUNNER_CONTRACT_ID,
        "runner_contract_sha256": runner.RUNNER_CONTRACT_SHA256,
        "combined_ledger_sha256": sha256(ledger),
        "train_csv_sha256": sha256(csv_blob),
        "train_text_sha256": sha256(text_blob),
        "parser_version": biological.PARSER_VERSION,
        "adapter_version": "m9-source-adapter-v2",
        "ledger_row_counts": {name: counts[name] for name in runner.ROW_COUNT_FIELDS},
        "train_identity_rows": len(train_rows),
        "train_distinct_cores": len(first_occurrence(train_rows)),
        "synthetic_execution_is_production_validation": False,
    }
    identities.update(overrides)
    return identities


def nearest_distance(sequence, cores):
    return min(edit_distance(sequence, core) / float(max(len(sequence), len(core))) for core in cores)


def strings_in(value):
    if type(value) is str:
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings_in(key)
            yield from strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)


def calls_named(tree, name):
    found = []
    for node in ast.walk(tree):
        if type(node) is not ast.Call:
            continue
        func = node.func
        if type(func) is ast.Name and func.id == name:
            found.append(node)
        elif type(func) is ast.Attribute and func.attr == name:
            found.append(node)
    return found


class TrainLeakageRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = os.path.join(self.temp.name, "out")
        self.rows = annotate(main_groups())
        self.ledger = production.ledger_jsonl_bytes(self.rows)
        self.counts = counts_for(self.rows)
        self.train_rows = train_table()
        self.csv_blob = csv_bytes(self.train_rows)
        self.cores = first_occurrence(self.train_rows)
        self.text_blob = text_bytes(self.cores)
        self.real_open = os.open

        def guarded(path, flags, *args, **kwargs):
            text = os.fspath(path)
            base = os.path.basename(text)
            if text.endswith(".jsonl") or "m9_all_conditions_derived_attempt_ledger" in text:
                raise AssertionError("opened " + text)
            if "rnagenesis-mres-data" in text:
                raise AssertionError("opened " + text)
            if base in ("ft_train.csv", "ft_validation.csv", "corpus_final.txt", "ref.csv", "eval.csv"):
                raise AssertionError("opened " + base)
            return self.real_open(path, flags, *args, **kwargs)

        os.open = guarded

    def tearDown(self):
        os.open = self.real_open
        self.temp.cleanup()

    def _identities(self, ledger=None, csv_blob=None, text_blob=None, counts=None, train_rows=None, **overrides):
        return identities_for(
            self.ledger if ledger is None else ledger,
            self.csv_blob if csv_blob is None else csv_blob,
            self.text_blob if text_blob is None else text_blob,
            self.counts if counts is None else counts,
            self.train_rows if train_rows is None else train_rows,
            **overrides,
        )

    def _run(self, ledger=None, csv_blob=None, text_blob=None, counts=None, train_rows=None, output=None, **kwargs):
        payload = self.ledger if ledger is None else ledger
        csv_payload = self.csv_blob if csv_blob is None else csv_blob
        text_payload = self.text_blob if text_blob is None else text_blob
        identities = kwargs.pop("identities", None)
        if identities is None:
            identities = self._identities(payload, csv_payload, text_payload, counts, train_rows)
        return runner.run_train_leakage(
            payload,
            csv_payload,
            text_payload,
            identities,
            output or self.output,
            enforce_production_identities=kwargs.pop("enforce_production_identities", False),
            **kwargs,
        )

    def _read(self, output=None):
        directory = output or self.output
        blobs = {}
        for filename in runner.OUTPUT_FILENAMES:
            with open(os.path.join(directory, filename), "rb") as handle:
                blobs[filename] = handle.read()
        exact = json.loads(blobs[runner.EXACT_SUMMARY_FILENAME].decode("utf-8"))
        nearest = json.loads(blobs[runner.NEAREST_SUMMARY_FILENAME].decode("utf-8"))
        manifest = json.loads(blobs[runner.MANIFEST_FILENAME].decode("utf-8"))
        return exact, nearest, manifest, blobs

    def _assert_firewall(self, blobs, rows, train_rows):
        rendered = b"".join(blobs.values())
        text = rendered.decode("utf-8")
        self.assertNotIn(b"\r", rendered)
        self.assertNotIn("canary-", text)
        for sequence in (ORDER, MATCH, UNEQUAL, TIED, TIE_A, TIE_B, MISS, NON_ACGU):
            self.assertNotIn(sequence, text)
            self.assertNotIn(core_hash(sequence), text)
        self.assertNotIn(SOURCE_HASH, text)
        for row in rows:
            self.assertNotIn(row["record_id"], text)
        for row in train_rows:
            for key in ("scientific_identity_id", "canonical_target_name", "cluster_id", "sequence_core", "sequence_core_sha256"):
                self.assertNotIn(row[key], text)
        for blob in blobs.values():
            parsed = json.loads(blob.decode("utf-8"))
            self.assertTrue(all(biological.CANONICAL_SEQUENCE.fullmatch(item) is None for item in strings_in(parsed)))

    def test_exact_matches_duplicates_lengths_ties_and_seed_pooling(self):
        result = self._run()
        exact, nearest, manifest, blobs = self._read()
        self.assertEqual(result["exact_summary"], exact)
        self.assertEqual(result["nearest_summary"], nearest)
        self.assertEqual(result["train_identity_rows"], 5)
        self.assertEqual(result["train_distinct_cores"], 4)
        self.assertEqual(self.cores[0], ORDER)
        self.assertNotEqual(self.cores, sorted(self.cores))
        self.assertEqual(exact["train_identity_row_count"], 5)
        self.assertEqual(exact["train_distinct_core_count"], 4)
        self.assertEqual(exact["supplied_distinct_train_core_count"], 4)
        self.assertFalse(exact["csv_rows_silently_deduplicated"])
        self.assertFalse(exact["cores_rewritten"])
        self.assertFalse(exact["historical_0_01_guardrail_used_as_decision_threshold"])
        self.assertIsNone(exact["identity_threshold"])
        self.assertEqual(exact["match"], "full_parsed_string_membership")
        self.assertFalse(exact["partial_match"])
        self.assertFalse(exact["substring_match"])
        self.assertEqual(exact["b0_role"], "external_comparator")
        self.assertFalse(exact["b0_pooled_into_b1_b2_d1_aggregate"])
        self.assertEqual(exact["by_condition"]["B0"]["role"], "external_comparator")
        self.assertEqual(exact["by_condition"]["B0"]["row_leakage"], {"numerator": 0, "denominator": 1, "rate": 0.0})
        self.assertEqual(exact["by_condition"]["B1"]["row_leakage"], {"numerator": 2, "denominator": 3, "rate": 2 / 3})
        self.assertEqual(exact["by_condition"]["B1"]["distinct_sequence_sensitivity"], {"numerator": 1, "denominator": 2, "rate": 0.5})
        self.assertNotEqual(
            exact["by_condition"]["B1"]["row_leakage"]["rate"],
            exact["by_condition"]["B1"]["distinct_sequence_sensitivity"]["rate"],
        )
        self.assertEqual(exact["by_condition"]["B2"]["row_leakage"], {"numerator": 0, "denominator": 2, "rate": 0.0})
        self.assertEqual(exact["by_condition"]["B2"]["distinct_sequence_sensitivity"]["denominator"], 1)
        d1 = exact["d1"]
        self.assertEqual(d1["seed_43_valid_conditional_row_rate"], {"numerator": 1, "denominator": 1, "rate": 1.0})
        self.assertEqual(d1["seed_44_valid_conditional_row_rate"], {"numerator": 0, "denominator": 3, "rate": 0.0})
        self.assertEqual(d1["unweighted_arithmetic_mean_of_seed_specific_row_rates"], 0.5)
        self.assertEqual(d1["actual_attempt_pooled"]["row_leakage"], {"numerator": 1, "denominator": 4, "rate": 0.25})
        self.assertNotEqual(
            d1["unweighted_arithmetic_mean_of_seed_specific_row_rates"],
            d1["actual_attempt_pooled"]["row_leakage"]["rate"],
        )
        self.assertEqual(d1["actual_attempt_pooled"]["label"], "actual_attempt_pooled")
        self.assertFalse(d1["actual_attempt_pooled"]["replaces_seed_specific_rates"])
        self.assertIsNone(d1["confidence_interval"])
        self.assertFalse(d1["bootstrap"])
        self.assertFalse(d1["hypothesis_test"])
        self.assertEqual(nearest["by_condition"]["B1"]["valid_row_count"], 3)
        self.assertEqual(nearest["by_condition"]["B1"]["distinct_valid_sequence_count"], 2)
        self.assertEqual(nearest["by_condition"]["B1"]["nearest_train_normalized_edit_distance"]["minimum"], 0.0)
        self.assertEqual(
            nearest["by_condition"]["B1"]["nearest_train_normalized_edit_distance"]["maximum"],
            nearest_distance(UNEQUAL, self.cores),
        )
        self.assertNotEqual(len(UNEQUAL), len(MATCH))
        self.assertGreater(nearest_distance(UNEQUAL, self.cores), 0.0)
        tie = nearest_distance(TIED, self.cores)
        self.assertEqual(tie, 0.125)
        self.assertEqual(edit_distance(TIED, TIE_A) / 8, tie)
        self.assertEqual(edit_distance(TIED, TIE_B) / 8, tie)
        block = nearest["by_condition"]["B2"]
        self.assertEqual(block["valid_row_count"], 2)
        self.assertEqual(block["distinct_valid_sequence_count"], 1)
        self.assertEqual(block["distinct_distance_computations"], 1)
        self.assertEqual(block["row_distance_projections"], 2)
        self.assertEqual(block["nearest_train_normalized_edit_distance"]["minimum"], tie)
        self.assertEqual(block["nearest_train_normalized_edit_distance"]["maximum"], tie)
        self.assertEqual(block["maximum_edit_similarity_to_train"], 1.0 - tie)
        self.assertFalse(block["edit_similarity_is_sequence_identity"])
        self.assertIn("not a sequence identity", block["maximum_edit_similarity_definition"])
        self.assertFalse(block["historical_0_01_guardrail_used_as_decision_threshold"])
        self.assertEqual(nearest["d1"]["by_training_seed"]["43"]["valid_row_count"], 1)
        self.assertEqual(nearest["d1"]["by_training_seed"]["44"]["valid_row_count"], 3)
        self.assertEqual(nearest["d1"]["pooled_equal_mixture_rule"], "inclusive_cumulative_weight_exact_v2")
        self.assertFalse(nearest["d1"]["pooled_equal_mixture_distance_quantiles_absent"])
        self.assertFalse(nearest["replaces_frozen_implementation"])
        self.assertEqual(manifest["schema"], runner.MANIFEST_SCHEMA)
        self.assertEqual(manifest["runner_contract"]["contract_id"], "m9a-train-leakage-runner-v1")
        self.assertEqual(manifest["runner_contract"]["recomputed_sha256"], runner.RUNNER_CONTRACT_SHA256)
        self.assertEqual(manifest["m9a_contract"]["recomputed_sha256"], runner.M9A_CONTRACT_SHA256)
        self.assertEqual(manifest["governing_plan"]["recomputed_sha256"], runner.GOVERNING_PLAN_SHA256)
        self.assertEqual(manifest["frozen_data_contract"]["recomputed_sha256"], runner.FROZEN_DATA_CONTRACT_SHA256)
        self.assertEqual(manifest["combined_ledger"]["recomputed_sha256"], sha256(self.ledger))
        self.assertEqual(manifest["train_csv"]["identity_row_count"], 5)
        self.assertEqual(manifest["train_csv"]["distinct_core_count"], 4)
        self.assertFalse(manifest["train_csv"]["csv_rows_silently_deduplicated"])
        self.assertIsNone(manifest["train_csv"]["path"])
        self.assertFalse(manifest["access_boundary"]["synthetic_execution_is_production_validation"])
        self.assertFalse(manifest["access_boundary"]["production_identities_enforced"])
        self.assertFalse(manifest["access_boundary"]["validation_accessed"])
        self.assertFalse(manifest["access_boundary"]["train_files_opened"])
        self.assertFalse(manifest["manifest_file"]["sha256_embedded"])
        self.assertNotIn(sha256(blobs[runner.MANIFEST_FILENAME]).encode("ascii"), blobs[runner.MANIFEST_FILENAME])
        self.assertEqual([item["filename"] for item in manifest["outputs"]], [runner.EXACT_SUMMARY_FILENAME, runner.NEAREST_SUMMARY_FILENAME])
        self._assert_firewall(blobs, self.rows, self.train_rows)

    def test_cached_nearest_matches_the_frozen_implementation(self):
        with open(os.path.join(ROOT, runner.M9A_CONTRACT_RELATIVE), "rb") as handle:
            contract = json.loads(handle.read().decode("utf-8"))
        real = leakage.nearest_train
        cached_calls = []
        pure_calls = []

        def counting(bucket):
            def wrapped(sequence, cores):
                bucket.append(sequence)
                return real(sequence, cores)
            return wrapped

        leakage.nearest_train = counting(cached_calls)
        try:
            cached = runner.cached_nearest_train_distance_summaries(self.rows, self.cores, contract)
        finally:
            leakage.nearest_train = real
        self.assertIs(leakage.nearest_train, real)
        leakage.nearest_train = counting(pure_calls)
        try:
            pure = leakage.nearest_train_distance_summaries(self.rows, self.cores, contract)
        finally:
            leakage.nearest_train = real
        self.assertEqual(cached, pure)
        valid = {row["parsed_sequence"] for row in self.rows if row["outcome"] == biological.OUTCOME_VALID}
        self.assertEqual(set(cached_calls), valid)
        self.assertEqual(len(cached_calls), len(valid))
        self.assertGreater(len(pure_calls), len(cached_calls))
        self.assertEqual(cached["by_condition"]["B1"]["valid_row_count"], pure["by_condition"]["B1"]["valid_row_count"])
        self.assertEqual(cached["by_condition"]["B2"]["nearest_train_normalized_edit_distance"], pure["by_condition"]["B2"]["nearest_train_normalized_edit_distance"])
        self.assertEqual(cached["d1"]["pooled_equal_mixture_distance_quantiles"], pure["d1"]["pooled_equal_mixture_distance_quantiles"])
        self.assertEqual(cached["d1"]["by_training_seed"]["43"]["valid_row_count"], 1)
        self.assertEqual(cached["d1"]["by_training_seed"]["44"]["valid_row_count"], 3)
        result = self._run(output=os.path.join(self.temp.name, "cached-publish"))
        self.assertEqual(result["nearest_summary"]["by_condition"], pure["by_condition"])
        self.assertEqual(result["nearest_summary"]["d1"], pure["d1"])

    def test_zero_valid_condition_denominator_is_null(self):
        groups = main_groups()
        groups["B0"] = [
            derived_row("canary-attempt-b0-empty", "B0", outcome=biological.OUTCOME_EMPTY),
            derived_row("canary-attempt-b0-also-empty", "B0", outcome=biological.OUTCOME_EMPTY),
        ]
        rows = annotate(groups)
        blob = production.ledger_jsonl_bytes(rows)
        self._run(blob, counts=counts_for(rows), output=os.path.join(self.temp.name, "zero-b0"))
        exact, _nearest, _manifest, blobs = self._read(os.path.join(self.temp.name, "zero-b0"))
        self.assertEqual(exact["by_condition"]["B0"]["row_leakage"], {"numerator": 0, "denominator": 0, "rate": None})
        self.assertEqual(exact["by_condition"]["B0"]["distinct_sequence_sensitivity"]["rate"], None)
        self.assertEqual(exact["by_condition"]["D1"]["row_leakage"]["denominator"], 4)
        self._assert_firewall(blobs, rows, self.train_rows)

    def test_empty_valid_population_and_d1_seed_failures(self):
        groups = main_groups()
        for condition, rows in groups.items():
            for row in rows:
                if row["outcome"] == biological.OUTCOME_VALID:
                    row["outcome"] = biological.OUTCOME_EMPTY
                    row["parsed_sequence"] = None
                    row["parsed_length"] = 0
                    row["failure_reason"] = biological.OUTCOME_EMPTY
        empty_rows = annotate(groups)
        empty_blob = production.ledger_jsonl_bytes(empty_rows)
        with self.assertRaises(runner.TrainLeakageRunnerError) as empty_error:
            self._run(empty_blob, counts=counts_for(empty_rows), output=os.path.join(self.temp.name, "empty-valid"))
        self.assertEqual(empty_error.exception.code, "d1_valid_denominator_zero")
        with open(os.path.join(ROOT, runner.M9A_CONTRACT_RELATIVE), "rb") as handle:
            contract = json.loads(handle.read().decode("utf-8"))
        pure = leakage.nearest_train_distance_summaries(empty_rows, self.cores, contract)
        cached = runner.cached_nearest_train_distance_summaries(empty_rows, self.cores, contract)
        self.assertEqual(cached, pure)
        self.assertIsNone(pure["by_condition"]["B1"]["nearest_train_normalized_edit_distance"])
        self.assertTrue(pure["d1"]["pooled_equal_mixture_distance_quantiles_absent"])
        self.assertEqual(pure["d1"]["pooled_equal_mixture_absent_reason"], "zero_valid_denominator")
        zero_seed = main_groups()
        for row in zero_seed["D1"]:
            if row["d1_training_seed"] == 44:
                row["outcome"] = biological.OUTCOME_EMPTY
                row["parsed_sequence"] = None
                row["parsed_length"] = 0
                row["failure_reason"] = biological.OUTCOME_EMPTY
        zero_rows = annotate(zero_seed)
        zero_blob = production.ledger_jsonl_bytes(zero_rows)
        with self.assertRaises(runner.TrainLeakageRunnerError) as zero_error:
            self._run(zero_blob, counts=counts_for(zero_rows), output=os.path.join(self.temp.name, "zero-seed"))
        self.assertEqual(zero_error.exception.code, "d1_valid_denominator_zero")
        nearest = runner.cached_nearest_train_distance_summaries(zero_rows, self.cores, contract)
        frozen = leakage.nearest_train_distance_summaries(zero_rows, self.cores, contract)
        self.assertEqual(nearest, frozen)
        self.assertIsNone(nearest["d1"]["by_training_seed"]["44"]["nearest_train_normalized_edit_distance"])
        self.assertEqual(nearest["d1"]["by_training_seed"]["43"]["valid_row_count"], 1)
        self.assertEqual(nearest["d1"]["pooled_equal_mixture_absent_reason"], "zero_valid_denominator")
        missing = main_groups()
        missing["D1"] = [row for row in missing["D1"] if row["d1_training_seed"] == 43]
        missing_rows = annotate(missing)
        missing_blob = production.ledger_jsonl_bytes(missing_rows)
        with self.assertRaises(runner.TrainLeakageRunnerError) as missing_error:
            self._run(missing_blob, counts=counts_for(missing_rows), output=os.path.join(self.temp.name, "missing-seed"))
        self.assertEqual(missing_error.exception.code, "d1_seed_missing")
        with self.assertRaises(leakage.OverlapLeakageError) as frozen_missing:
            leakage.nearest_train_distance_summaries(missing_rows, self.cores, contract)
        self.assertEqual(frozen_missing.exception.code, "d1_seed_missing")
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "empty-valid")))
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "zero-seed")))
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "missing-seed")))

    def test_empty_train_duplicate_text_and_order_mismatch(self):
        header = csv_bytes([])
        with self.assertRaises(runner.TrainLeakageRunnerError) as empty_error:
            self._run(
                csv_blob=header,
                text_blob=b"",
                train_rows=[],
                identities=self._identities(csv_blob=header, text_blob=b"", train_rows=[]),
                output=os.path.join(self.temp.name, "empty-train"),
            )
        self.assertEqual(empty_error.exception.code, "train_cores_empty")
        duplicated = text_bytes([ORDER, ORDER])
        with self.assertRaises(runner.TrainLeakageRunnerError) as duplicate_error:
            self._run(
                text_blob=duplicated,
                identities=self._identities(text_blob=duplicated),
                output=os.path.join(self.temp.name, "duplicate-text"),
            )
        self.assertEqual(duplicate_error.exception.code, "duplicate_train_cores")
        swapped = text_bytes([self.cores[1], self.cores[0], *self.cores[2:]])
        with self.assertRaises(runner.TrainLeakageRunnerError) as order_error:
            self._run(
                text_blob=swapped,
                identities=self._identities(text_blob=swapped),
                output=os.path.join(self.temp.name, "order"),
            )
        self.assertEqual(order_error.exception.code, "train_text_order_mismatch")
        crlf = self.text_blob.replace(b"\n", b"\r\n")
        with self.assertRaises(runner.TrainLeakageRunnerError) as crlf_error:
            self._run(text_blob=crlf, identities=self._identities(text_blob=crlf), output=os.path.join(self.temp.name, "crlf"))
        self.assertEqual(crlf_error.exception.code, "train_text_invalid")
        self.assertFalse(os.path.exists(self.output))

    def test_duplicate_identity_bad_core_hash_length_and_role(self):
        duplicated = copy.deepcopy(self.train_rows)
        duplicated[4]["scientific_identity_id"] = duplicated[1]["scientific_identity_id"]
        blob = csv_bytes(duplicated)
        with self.assertRaises(runner.TrainLeakageRunnerError) as identity_error:
            self._run(csv_blob=blob, identities=self._identities(csv_blob=blob, train_rows=duplicated), output=os.path.join(self.temp.name, "dup-id"))
        self.assertEqual(identity_error.exception.code, "duplicate_scientific_identity")
        tainted = copy.deepcopy(self.train_rows)
        tainted[1]["sequence_core"] = NON_ACGU
        tainted[1]["sequence_core_sha256"] = core_hash(NON_ACGU)
        tainted[1]["sequence_length_core"] = "4"
        blob = csv_bytes(tainted)
        with self.assertRaises(runner.TrainLeakageRunnerError) as alphabet_error:
            self._run(csv_blob=blob, identities=self._identities(csv_blob=blob, train_rows=tainted), output=os.path.join(self.temp.name, "alphabet"))
        self.assertEqual(alphabet_error.exception.code, "train_core_invalid")
        bad_hash = copy.deepcopy(self.train_rows)
        bad_hash[1]["sequence_core_sha256"] = "0" * 64
        blob = csv_bytes(bad_hash)
        with self.assertRaises(runner.TrainLeakageRunnerError) as hash_error:
            self._run(csv_blob=blob, identities=self._identities(csv_blob=blob, train_rows=bad_hash), output=os.path.join(self.temp.name, "hash"))
        self.assertEqual(hash_error.exception.code, "train_core_hash_mismatch")
        bad_length = copy.deepcopy(self.train_rows)
        bad_length[1]["sequence_length_core"] = "1"
        blob = csv_bytes(bad_length)
        with self.assertRaises(runner.TrainLeakageRunnerError) as length_error:
            self._run(csv_blob=blob, identities=self._identities(csv_blob=blob, train_rows=bad_length), output=os.path.join(self.temp.name, "length"))
        self.assertEqual(length_error.exception.code, "train_core_length_mismatch")
        wrong_split = copy.deepcopy(self.train_rows)
        wrong_split[0]["ft_split"] = "VALIDATION"
        blob = csv_bytes(wrong_split)
        with self.assertRaises(runner.TrainLeakageRunnerError) as split_error:
            self._run(csv_blob=blob, identities=self._identities(csv_blob=blob, train_rows=wrong_split), output=os.path.join(self.temp.name, "split"))
        self.assertEqual(split_error.exception.code, "train_role_mismatch")
        wrong_partition = copy.deepcopy(self.train_rows)
        wrong_partition[0]["partition"] = "REF"
        blob = csv_bytes(wrong_partition)
        with self.assertRaises(runner.TrainLeakageRunnerError) as partition_error:
            self._run(csv_blob=blob, identities=self._identities(csv_blob=blob, train_rows=wrong_partition), output=os.path.join(self.temp.name, "partition"))
        self.assertEqual(partition_error.exception.code, "train_role_mismatch")
        self.assertFalse(os.path.exists(self.output))

    def test_corrupted_digest_for_each_byte_source_fails_before_parsing(self):
        missing_root = os.path.join(self.temp.name, "missing-root")
        cases = (
            ("combined_ledger_hash_mismatch", {"combined_ledger_sha256": "0" * 64}),
            ("train_csv_hash_mismatch", {"train_csv_sha256": "0" * 64}),
            ("train_text_hash_mismatch", {"train_text_sha256": "0" * 64}),
        )
        for code, overrides in cases:
            with self.assertRaises(runner.TrainLeakageRunnerError) as caught:
                self._run(
                    identities=self._identities(**overrides),
                    output=os.path.join(self.temp.name, code),
                    root=missing_root,
                )
            self.assertEqual(caught.exception.code, code)
        bad_ledger = b"{"
        with self.assertRaises(runner.TrainLeakageRunnerError) as parsed:
            self._run(
                bad_ledger,
                identities=self._identities(ledger=bad_ledger, combined_ledger_sha256="0" * 64),
                output=os.path.join(self.temp.name, "bad-ledger-hash"),
                root=missing_root,
            )
        self.assertEqual(parsed.exception.code, "combined_ledger_hash_mismatch")
        with self.assertRaises(runner.TrainLeakageRunnerError) as syntax:
            self._identities(m9a_contract_sha256="zz" * 32)
            runner.validate_identities(self._identities(m9a_contract_sha256="zz" * 32), enforce_production_identities=False)
        self.assertEqual(syntax.exception.code, "identity_invalid")
        self.assertFalse(os.path.exists(missing_root))

    def test_malformed_jsonl_and_csv(self):
        samples = (b"\xff\n", b"{}\n\n", b"[]\n", b'{"a": 1}', b"not-json\n", b'{"a": 1}\r\n')
        for sample in samples:
            with self.assertRaises(runner.TrainLeakageRunnerError) as caught:
                self._run(
                    sample,
                    identities=self._identities(ledger=sample),
                    output=os.path.join(self.temp.name, "jsonl-" + sha256(sample)[:8]),
                )
            self.assertEqual(caught.exception.code, "jsonl_malformed")
        csv_samples = (b"\xff", b"", b"scientific_identity_id\x00,sequence_core\n", b"a,b\n1,2,3\n")
        codes = set()
        for sample in csv_samples:
            with self.assertRaises(runner.TrainLeakageRunnerError) as caught:
                self._run(
                    csv_blob=sample,
                    identities=self._identities(csv_blob=sample),
                    output=os.path.join(self.temp.name, "csv-" + sha256(sample)[:8]),
                )
            codes.add(caught.exception.code)
        self.assertIn("csv_malformed", codes)
        self.assertFalse(os.path.exists(self.output))

    def test_set_and_decoded_objects_are_refused(self):
        identities = self._identities()
        with self.assertRaises(runner.TrainLeakageRunnerError) as set_error:
            runner.run_train_leakage(self.ledger, {ORDER}, self.text_blob, identities, self.output, enforce_production_identities=False)
        self.assertEqual(set_error.exception.code, "payload_type_invalid")
        with self.assertRaises(runner.TrainLeakageRunnerError) as list_error:
            runner.run_train_leakage(self.rows, self.csv_blob, self.text_blob, identities, os.path.join(self.temp.name, "list-out"), enforce_production_identities=False)
        self.assertEqual(list_error.exception.code, "payload_type_invalid")
        with self.assertRaises(runner.TrainLeakageRunnerError) as text_error:
            runner.run_train_leakage(self.ledger, self.csv_blob, "ACGU\n", identities, os.path.join(self.temp.name, "text-out"), enforce_production_identities=False)
        self.assertEqual(text_error.exception.code, "payload_type_invalid")
        with self.assertRaises(biological.ParserContractError) as path_error:
            runner.run_train_leakage(self.ledger, "/tmp/ft_train.csv", self.text_blob, identities, os.path.join(self.temp.name, "path-out"), enforce_production_identities=False)
        self.assertEqual(path_error.exception.code, "filename_refused")
        self.assertFalse(os.path.exists(self.output))

    def test_existing_output_directory_is_refused_and_cleanup_runs(self):
        os.makedirs(self.output)
        with self.assertRaises(runner.TrainLeakageRunnerError) as caught:
            self._run()
        self.assertEqual(caught.exception.code, "output_exists")
        self.assertEqual(os.listdir(self.output), [])
        self.assertEqual([name for name in os.listdir(self.temp.name) if name.startswith(runner.TEMP_PREFIX)], [])
        original = runner.validate_published_directory

        def fail(directory, expected):
            raise runner.TrainLeakageRunnerError("output_validation_failed", "injected")

        runner.validate_published_directory = fail
        try:
            with self.assertRaises(runner.TrainLeakageRunnerError) as validation:
                self._run(output=os.path.join(self.temp.name, "publish-fail"))
        finally:
            runner.validate_published_directory = original
        self.assertEqual(validation.exception.code, "output_validation_failed")
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "publish-fail")))
        self.assertEqual([name for name in os.listdir(self.temp.name) if name.startswith(runner.TEMP_PREFIX)], [])

    def test_production_identities_are_rejected_when_synthetic_mode_claims_them(self):
        with self.assertRaises(runner.TrainLeakageRunnerError) as claim:
            runner.run_train_leakage(
                b"x",
                b"y",
                b"z",
                runner.sealed_identities(),
                self.output,
                enforce_production_identities=False,
            )
        self.assertEqual(claim.exception.code, "production_identity_claim_refused")
        flagged = self._identities()
        flagged["synthetic_execution_is_production_validation"] = True
        with self.assertRaises(runner.TrainLeakageRunnerError) as flagged_error:
            runner.run_train_leakage(self.ledger, self.csv_blob, self.text_blob, flagged, os.path.join(self.temp.name, "flagged"), enforce_production_identities=False)
        self.assertEqual(flagged_error.exception.code, "production_validation_claim_refused")
        with self.assertRaises(runner.TrainLeakageRunnerError) as enforced:
            self._run(enforce_production_identities=True, output=os.path.join(self.temp.name, "enforced"))
        self.assertEqual(enforced.exception.code, "production_identity_mismatch")
        sealed = runner.sealed_identities()
        self.assertEqual(sealed["combined_ledger_sha256"], "d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e")
        self.assertEqual(sealed["train_csv_sha256"], "84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0")
        self.assertEqual(sealed["train_text_sha256"], "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d")
        self.assertEqual(sealed["ledger_row_counts"], {"B0": 30080, "B1": 30000, "B2": 30000, "D1": 30000, "combined": 120080})
        self.assertEqual(sealed["train_identity_rows"], 726)
        self.assertEqual(sealed["train_distinct_cores"], 669)
        self.assertFalse(sealed["synthetic_execution_is_production_validation"])
        self.assertFalse(os.path.exists(self.output))

    def test_pinned_contract_digest_mismatches_write_nothing(self):
        paths = (
            (runner.M9A_CONTRACT_RELATIVE, "m9a_contract_digest_mismatch"),
            (runner.GOVERNING_PLAN_RELATIVE, "governing_plan_digest_mismatch"),
            (runner.FROZEN_DATA_CONTRACT_RELATIVE, "frozen_data_contract_digest_mismatch"),
            (runner.RUNNER_CONTRACT_RELATIVE, "runner_contract_digest_mismatch"),
        )
        originals = {}
        for relative, _code in paths:
            with open(os.path.join(ROOT, relative), "rb") as handle:
                originals[relative] = handle.read()
        for relative, code in paths:
            root = os.path.join(self.temp.name, code)
            for item, blob in originals.items():
                destination = os.path.join(root, item)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                payload = bytearray(blob)
                if item == relative:
                    payload[-1] ^= 0x01
                with open(destination, "wb") as handle:
                    handle.write(payload)
            with self.assertRaises(runner.TrainLeakageRunnerError) as caught:
                self._run(root=root, output=os.path.join(self.temp.name, "out-" + code))
            self.assertEqual(caught.exception.code, code)
            self.assertFalse(os.path.exists(os.path.join(self.temp.name, "out-" + code)))
        for relative, blob in originals.items():
            with open(os.path.join(ROOT, relative), "rb") as handle:
                self.assertEqual(handle.read(), blob)

    def test_contract_documentation_and_sealed_entry_remain_unexecuted(self):
        with open(os.path.join(ROOT, runner.RUNNER_CONTRACT_RELATIVE), "rb") as handle:
            contract_blob = handle.read()
        self.assertEqual(sha256(contract_blob), runner.RUNNER_CONTRACT_SHA256)
        document = json.loads(contract_blob.decode("utf-8"))
        self.assertEqual(document["contract_id"], "m9a-train-leakage-runner-v1")
        self.assertFalse(document["synthetic_execution_is_production_validation"])
        self.assertTrue(document["sealed_production_entry_remains_unexecuted"])
        self.assertFalse(document["formulas"]["modified_by_this_runner"])
        self.assertFalse(document["formulas"]["nearest_execution_replaces_frozen_implementation"])
        self.assertEqual(document["d1_training_seeds"], [43, 44])
        with open(os.path.join(ROOT, "docs", "fine_tuning", "m9_train_leakage_runner.md"), "r", encoding="utf-8") as handle:
            prose = handle.read()
        self.assertIn(runner.RUNNER_CONTRACT_SHA256, prose)
        self.assertIn("remains unexecuted", prose)
        self.assertIn("Before any sealed source is opened", prose)
        self.assertIn("before opening either TRAIN file", prose)
        self.assertIn("before opening TRAIN text", prose)
        self.assertIn(runner.DEVELOPMENT_TRAIN_CSV, prose)
        self.assertIn(runner.DEVELOPMENT_TRAIN_TEXT, prose)
        self.assertEqual(document["sealed_source_opening_order"], runner.SEALED_SOURCE_OPENING_ORDER)
        self.assertEqual(
            document["sealed_source_opening_order"]["then_open_and_verify_each_digest_before_the_next_open"],
            ["combined_ledger", "train_csv", "train_text"],
        )
        self.assertFalse(document["sealed_source_opening_order"]["source_parsed_before_its_digest_matches"])
        self.assertTrue(
            document["sealed_source_opening_order"][
                "in_memory_core_rechecks_digests_schema_counts_provenance_and_output_destination"
            ]
        )
        source = inspect.getsource(runner.run_sealed_train_leakage)
        self.assertLess(source.index("prepare_sealed_train_inputs("), source.index("run_train_leakage("))
        prepare_source = inspect.getsource(runner.prepare_sealed_train_inputs)
        self.assertLess(prepare_source.index("preflight_sealed_train_leakage("), prepare_source.index("open_verified_sealed_sources("))
        self.assertIn('identities["combined_ledger_sha256"]', prepare_source)
        self.assertIn('identities["train_csv_sha256"]', prepare_source)
        self.assertIn('identities["train_text_sha256"]', prepare_source)
        preflight_source = inspect.getsource(runner.preflight_sealed_train_leakage)
        self.assertNotIn("open_verified_sealed_sources", preflight_source)
        self.assertNotIn("_read_allowlisted", preflight_source)
        markers = [
            "validate_identities(",
            "_validate_sealed_paths(",
            "_refuse_existing_outputs(",
            "_load_m9a_contract(",
            "_load_governing_plan(",
            "_load_frozen_data_contract(",
            "_load_runner_contract(",
            "_git_head(",
        ]
        positions = [preflight_source.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("enforce_production_identities=True", source)
        self.assertIn("DEVELOPMENT_TRAIN_CSV", source)
        self.assertIn("DEVELOPMENT_TRAIN_TEXT", source)
        self.assertIn("unexecuted", source)
        sealed_tree = ast.parse(source)
        self.assertEqual(calls_named(sealed_tree, "run_sealed_train_leakage"), [])
        module_tree = ast.parse(inspect.getsource(runner))
        self.assertEqual(calls_named(module_tree, "run_sealed_train_leakage"), [])
        test_tree = ast.parse(inspect.getsource(sys.modules[__name__]))
        self.assertEqual(calls_named(test_tree, "run_sealed_train_leakage"), [])
        self.assertNotIn("run_sealed_train_leakage(", inspect.getsource(self._run))
        profile_rows = [{"scientific_identity_id": "id", "cluster_id": "cluster", "sequence_core_sha256": "ab" * 32}]
        self.assertEqual(runner.identity_set_hash(profile_rows), sha256(b"id\tcluster\t" + (b"ab" * 32)))
        self.assertEqual(runner.cluster_set_hash(profile_rows), sha256(b"cluster"))
        with self.assertRaises(runner.TrainLeakageRunnerError) as profile:
            runner.assert_production_train_profile(self.train_rows, self.cores, ["only"], self.csv_blob, self.text_blob)
        self.assertEqual(profile.exception.code, "production_train_profile_mismatch")
        head = subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"], text=True).strip()
        self._run()
        _exact, _nearest, manifest, _blobs = self._read()
        self.assertEqual(manifest["runner_git_commit"], head)

    def _assert_production_identities_unchanged(self):
        self.assertEqual(runner.COMBINED_LEDGER_SHA256, "d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e")
        self.assertEqual(runner.TRAIN_CSV_SHA256, "84c4a357abb314b9a3b0cb667a4b7c194c96f70c032adec9aac26e66d3204bd0")
        self.assertEqual(runner.TRAIN_TEXT_SHA256, "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d")
        self.assertEqual(runner.PRODUCTION_ROW_COUNTS, {"B0": 30080, "B1": 30000, "B2": 30000, "D1": 30000, "combined": 120080})
        self.assertEqual(runner.PRODUCTION_TRAIN_IDENTITY_ROWS, 726)
        self.assertEqual(runner.PRODUCTION_TRAIN_DISTINCT_CORES, 669)

    def _synthetic_sources(self):
        directory = os.path.join(self.temp.name, "synthetic-sources")
        os.makedirs(directory, exist_ok=True)
        payloads = {
            "ledger": b"synthetic-ledger-bytes\n",
            "csv": b"synthetic-csv-bytes\n",
            "text": b"synthetic-text-bytes\n",
        }
        paths = {
            "ledger": os.path.join(directory, "synthetic-ledger.bin"),
            "csv": os.path.join(directory, "synthetic-train-table.csv"),
            "text": os.path.join(directory, "synthetic-train-lines.txt"),
        }
        for label, payload in payloads.items():
            with open(paths[label], "wb") as handle:
                handle.write(payload)
        return paths, payloads

    def test_existing_output_destination_makes_no_sealed_source_read(self):
        self._assert_production_identities_unchanged()
        attempts = []

        def reader(path):
            attempts.append(os.fspath(path))
            raise AssertionError("sealed source read attempted")

        empty_root = os.path.join(self.temp.name, "empty-root")
        os.makedirs(empty_root)
        os.makedirs(self.output)
        paths = ("synthetic-ledger", "synthetic-csv", "synthetic-text")
        with self.assertRaises(runner.TrainLeakageRunnerError) as existing:
            runner.prepare_sealed_train_inputs(
                self.output,
                {"production_identities": True},
                empty_root,
                paths,
                reader,
            )
        self.assertEqual(existing.exception.code, "output_exists")
        self.assertEqual(os.listdir(self.output), [])
        link = os.path.join(self.temp.name, "output-link")
        os.symlink(self.output, link)
        with self.assertRaises(runner.TrainLeakageRunnerError) as linked:
            runner.prepare_sealed_train_inputs(
                link,
                {"production_identities": True},
                empty_root,
                paths,
                reader,
            )
        self.assertEqual(linked.exception.code, "output_symlink")
        self.assertEqual(attempts, [])

    def test_pinned_contract_mismatch_makes_no_sealed_source_read(self):
        self._assert_production_identities_unchanged()
        relatives = (
            (runner.M9A_CONTRACT_RELATIVE, "m9a_contract_digest_mismatch"),
            (runner.GOVERNING_PLAN_RELATIVE, "governing_plan_digest_mismatch"),
            (runner.FROZEN_DATA_CONTRACT_RELATIVE, "frozen_data_contract_digest_mismatch"),
            (runner.RUNNER_CONTRACT_RELATIVE, "runner_contract_digest_mismatch"),
        )
        originals = {}
        for relative, _code in relatives:
            with open(os.path.join(ROOT, relative), "rb") as handle:
                originals[relative] = handle.read()
        attempts = []

        def reader(path):
            attempts.append(os.fspath(path))
            raise AssertionError("sealed source read attempted")

        for relative, code in relatives:
            root = os.path.join(self.temp.name, "pin-" + code)
            for item, blob in originals.items():
                destination = os.path.join(root, item)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                payload = bytearray(blob)
                if item == relative:
                    payload[-1] ^= 0x01
                with open(destination, "wb") as handle:
                    handle.write(payload)
            output = os.path.join(self.temp.name, "pin-out-" + code)
            with self.assertRaises(runner.TrainLeakageRunnerError) as caught:
                runner.prepare_sealed_train_inputs(
                    output,
                    {"production_identities": True},
                    root,
                    ("synthetic-ledger", "synthetic-csv", "synthetic-text"),
                    reader,
                )
            self.assertEqual(caught.exception.code, code)
            self.assertFalse(os.path.exists(output))
            self.assertEqual(attempts, [])
        for relative, blob in originals.items():
            with open(os.path.join(ROOT, relative), "rb") as handle:
                self.assertEqual(handle.read(), blob)

    def test_ledger_digest_mismatch_stops_before_train_sources(self):
        self._assert_production_identities_unchanged()
        paths, payloads = self._synthetic_sources()
        attempts = []

        def reader(path):
            attempts.append(os.fspath(path))
            with open(path, "rb") as handle:
                return handle.read()

        output = os.path.join(self.temp.name, "ledger-mismatch-out")
        with self.assertRaises(runner.TrainLeakageRunnerError) as caught:
            runner.prepare_sealed_train_inputs(
                output,
                {"production_identities": True},
                ROOT,
                (paths["ledger"], paths["csv"], paths["text"]),
                reader,
            )
        self.assertEqual(caught.exception.code, "combined_ledger_hash_mismatch")
        self.assertEqual(attempts, [paths["ledger"]])
        self.assertNotEqual(sha256(payloads["ledger"]), runner.COMBINED_LEDGER_SHA256)
        self.assertFalse(os.path.exists(output))

    def test_train_csv_digest_mismatch_stops_before_train_text(self):
        self._assert_production_identities_unchanged()
        paths, payloads = self._synthetic_sources()
        attempts = []

        def reader(path):
            attempts.append(os.fspath(path))
            with open(path, "rb") as handle:
                return handle.read()

        with self.assertRaises(runner.TrainLeakageRunnerError) as caught:
            runner.open_verified_sealed_sources(
                (paths["ledger"], paths["csv"], paths["text"]),
                {
                    "combined_ledger": sha256(payloads["ledger"]),
                    "train_csv": "0" * 64,
                    "train_text": sha256(payloads["text"]),
                },
                reader,
            )
        self.assertEqual(caught.exception.code, "train_csv_hash_mismatch")
        self.assertEqual(attempts, [paths["ledger"], paths["csv"]])
        self.assertNotIn(paths["text"], attempts)
        self.assertNotEqual(sha256(payloads["csv"]), runner.TRAIN_CSV_SHA256)

    def test_synthetic_staged_reads_follow_ledger_csv_text_order(self):
        self._assert_production_identities_unchanged()
        paths, payloads = self._synthetic_sources()
        attempts = []
        parsed = []

        def reader(path):
            attempts.append(os.fspath(path))
            with open(path, "rb") as handle:
                return handle.read()

        def refuse(name):
            def wrapped(*_args, **_kwargs):
                parsed.append(name)
                raise AssertionError(name + " was called during staged reads")

            return wrapped

        originals = {
            "parse_combined_ledger": runner.parse_combined_ledger,
            "parse_train_csv": runner.parse_train_csv,
            "parse_train_text": runner.parse_train_text,
            "prepare_train_cores": runner.prepare_train_cores,
            "run_train_leakage": runner.run_train_leakage,
        }
        for name, original in originals.items():
            setattr(runner, name, refuse(name))
        try:
            blobs = runner.open_verified_sealed_sources(
                (paths["ledger"], paths["csv"], paths["text"]),
                {
                    "combined_ledger": sha256(payloads["ledger"]),
                    "train_csv": sha256(payloads["csv"]),
                    "train_text": sha256(payloads["text"]),
                },
                reader,
            )
        finally:
            for name, original in originals.items():
                setattr(runner, name, original)
        self.assertEqual(attempts, [paths["ledger"], paths["csv"], paths["text"]])
        self.assertEqual(blobs, (payloads["ledger"], payloads["csv"], payloads["text"]))
        self.assertEqual(parsed, [])
        for path in attempts:
            self.assertNotIn("rnagenesis-mres-data", path)
            self.assertNotIn("m9_all_conditions_derived_attempt_ledger", path)
            self.assertFalse(path.endswith(".jsonl"))
        self.assertNotEqual(sha256(payloads["ledger"]), runner.COMBINED_LEDGER_SHA256)
        self.assertNotEqual(sha256(payloads["csv"]), runner.TRAIN_CSV_SHA256)
        self.assertNotEqual(sha256(payloads["text"]), runner.TRAIN_TEXT_SHA256)


if __name__ == "__main__":
    unittest.main()

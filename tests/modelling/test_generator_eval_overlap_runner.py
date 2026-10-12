"""Synthetic tests for the M9A exact cross-condition overlap runner.

Sequences and ledgers in this module are constructed in memory. No production
JSONL, TRAIN, VALIDATION, REF, EVAL, model, checkpoint, structure tool, or
AptaRank resource is opened. The sealed production entry point is not called.
"""

from __future__ import annotations

import copy
import hashlib
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
import generator_eval_overlap_runner as runner
import generator_eval_parser as biological
import generator_eval_production_ledger as production

SEQUENCES = ("AAAA", "AAAC", "CCCC", "GGGG", "UUUU", "AAAG", "AAAU", "ACGT")
EXPECTED_PAIRS = {
    ("B0", "B1"): {"a_to_b": (1, 2), "b_to_a": (3, 5), "shared": 1, "a_distinct": (1, 2), "b_distinct": (1, 3), "union": 4, "jaccard": (1, 4)},
    ("B0", "B2"): {"a_to_b": (0, 2), "b_to_a": (0, 2), "shared": 0, "a_distinct": (0, 2), "b_distinct": (0, 2), "union": 4, "jaccard": (0, 4)},
    ("B0", "D1"): {"a_to_b": (0, 2), "b_to_a": (0, 2), "shared": 0, "a_distinct": (0, 2), "b_distinct": (0, 2), "union": 4, "jaccard": (0, 4)},
    ("B1", "B2"): {"a_to_b": (1, 5), "b_to_a": (1, 2), "shared": 1, "a_distinct": (1, 3), "b_distinct": (1, 2), "union": 4, "jaccard": (1, 4)},
    ("B1", "D1"): {"a_to_b": (0, 5), "b_to_a": (0, 2), "shared": 0, "a_distinct": (0, 3), "b_distinct": (0, 2), "union": 5, "jaccard": (0, 5)},
    ("B2", "D1"): {"a_to_b": (0, 2), "b_to_a": (0, 2), "shared": 0, "a_distinct": (0, 2), "b_distinct": (0, 2), "union": 4, "jaccard": (0, 4)},
}
EXPECTED_PATTERNS = {
    ("B0",): 1,
    ("B1",): 1,
    ("B2",): 1,
    ("D1",): 2,
    ("B0", "B1"): 1,
    ("B1", "B2"): 1,
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    with open(path, "rb") as handle:
        return sha256(handle.read())


def derived_row(record_id, condition, sequence=None, *, outcome=None, seed=None):
    item = derived.blank_derived_row()
    item["record_id"] = record_id
    item["condition"] = condition
    item["parser_version"] = biological.PARSER_VERSION
    item["adapter_version"] = "m9-source-adapter-v2"
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
            derived_row("b0-row-0", "B0", "AAAA"),
            derived_row("b0-row-1", "B0", "AAAC"),
            derived_row("b0-row-2", "B0", outcome=biological.OUTCOME_EMPTY),
        ],
        "B1": [
            derived_row("b1-row-0", "B1", "AAAC"),
            derived_row("b1-row-1", "B1", "AAAC"),
            derived_row("b1-row-2", "B1", "AAAC"),
            derived_row("b1-row-3", "B1", "CCCC"),
            derived_row("b1-row-4", "B1", "GGGG"),
            derived_row("b1-row-5", "B1", outcome=biological.OUTCOME_EMPTY),
        ],
        "B2": [
            derived_row("b2-row-0", "B2", "GGGG"),
            derived_row("b2-row-1", "B2", "UUUU"),
            derived_row("b2-row-2", "B2", "ACGT", outcome=biological.OUTCOME_NON_ACGU),
        ],
        "D1": [
            derived_row("d1-row-0", "D1", "AAAG", seed=43),
            derived_row("d1-row-1", "D1", "AAAU", seed=44),
        ],
    }


def zero_groups():
    return {
        "B0": [],
        "B1": [derived_row("b1-empty", "B1", outcome=biological.OUTCOME_EMPTY)],
        "B2": [derived_row("b2-non-acgu", "B2", "ACGT", outcome=biological.OUTCOME_NON_ACGU)],
        "D1": [derived_row("d1-only", "D1", "AAAA", seed=43)],
    }


def annotate(groups):
    rows = []
    for condition in ("B0", "B1", "B2", "D1"):
        rows.extend(production.annotate_exact_duplicates(groups[condition]))
    return rows


def ledger_bytes(rows):
    return production.ledger_jsonl_bytes(rows)


def counts_for(rows):
    counts = {condition: 0 for condition in ("B0", "B1", "B2", "D1")}
    for row in rows:
        counts[row["condition"]] += 1
    counts["combined"] = len(rows)
    return counts


def identities_for(blob, counts, **overrides):
    identities = {
        "contract_id": runner.CONTRACT_ID,
        "contract_sha256": runner.FROZEN_OVERLAP_CONTRACT_SHA256,
        "governing_plan_sha256": runner.GOVERNING_PLAN_SHA256,
        "combined_ledger_sha256": sha256(blob),
        "parser_version": biological.PARSER_VERSION,
        "adapter_version": "m9-source-adapter-v2",
        "row_counts": {name: counts[name] for name in ("B0", "B1", "B2", "D1", "combined")},
    }
    identities.update(overrides)
    return identities


def rate(numerator, denominator):
    return None if denominator == 0 else numerator / denominator


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


class OverlapRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = os.path.join(self.temp.name, "out")
        self.rows = annotate(main_groups())
        self.blob = ledger_bytes(self.rows)
        self.counts = counts_for(self.rows)

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, blob=None, counts=None, output=None, **kwargs):
        payload = self.blob if blob is None else blob
        identity_counts = self.counts if counts is None else counts
        identities = kwargs.pop("identities", None)
        if identities is None:
            identities = identities_for(payload, identity_counts)
        return runner.run_cross_condition_overlap(
            payload,
            identities,
            output or self.output,
            enforce_production_counts=kwargs.pop("enforce_production_counts", False),
            **kwargs,
        )

    def _read_outputs(self, output=None):
        directory = output or self.output
        summary_path = os.path.join(directory, runner.SUMMARY_FILENAME)
        manifest_path = os.path.join(directory, runner.MANIFEST_FILENAME)
        with open(summary_path, "rb") as handle:
            summary_blob = handle.read()
        with open(manifest_path, "rb") as handle:
            manifest_blob = handle.read()
        summary = json.loads(summary_blob.decode("utf-8"))
        manifest = json.loads(manifest_blob.decode("utf-8"))
        return summary, manifest, summary_blob, manifest_blob

    def _assert_rate(self, block, numerator, denominator):
        self.assertEqual(block["numerator"], numerator)
        self.assertEqual(block["denominator"], denominator)
        self.assertEqual(block["rate"], rate(numerator, denominator))

    def _assert_no_private_leak(self, blobs, rows):
        rendered = b"".join(blobs)
        text = rendered.decode("utf-8")
        for sequence in SEQUENCES:
            self.assertNotIn(sequence, text)
            self.assertNotIn(sha256(sequence.encode("utf-8")), text)
        for row in rows:
            self.assertNotIn(row["record_id"], text)
            if type(row["parsed_sequence"]) is str:
                self.assertNotIn(row["parsed_sequence"], text)
        for document in blobs:
            parsed = json.loads(document.decode("utf-8"))
            self.assertTrue(all(biological.CANONICAL_SEQUENCE.fullmatch(item) is None for item in strings_in(parsed)))

    def test_frozen_statistics_pairs_directions_and_reconciliation(self):
        opened = []
        real_open = os.open

        def guarded(path, flags, mode=0o777):
            text = os.fspath(path)
            opened.append(text)
            if text.endswith(".jsonl") or "m9_all_conditions_derived_attempt_ledger" in text:
                raise AssertionError("opened " + text)
            if "m9_generator_evaluation" in text:
                raise AssertionError("opened " + text)
            for role in ("TRAIN", "VALIDATION", "REF", "EVAL"):
                if role in text.replace("\\", "/").split("/"):
                    raise AssertionError("opened " + role)
            return real_open(path, flags, mode)

        os.open = guarded
        try:
            result = self._run()
        finally:
            os.open = real_open
        summary, manifest, summary_blob, manifest_blob = self._read_outputs()
        self.assertEqual(result["summary"], summary)
        self.assertEqual(result["manifest"], manifest)
        self.assertEqual([item["filename"] for item in manifest["outputs"]], [runner.SUMMARY_FILENAME])
        self.assertEqual([(item["condition_a"], item["condition_b"]) for item in summary["pairs"]], list(runner.CONDITION_PAIRS))
        self.assertEqual(len(summary["pairs"]), 6)
        for pair in summary["pairs"]:
            key = (pair["condition_a"], pair["condition_b"])
            expected = EXPECTED_PAIRS[key]
            self._assert_rate(pair["row_coverage"]["a_to_b"], *expected["a_to_b"])
            self._assert_rate(pair["row_coverage"]["b_to_a"], *expected["b_to_a"])
            self.assertEqual(pair["distinct"]["shared_sequence_count"], expected["shared"])
            self._assert_rate(pair["distinct"]["a_distinct_coverage_by_b"], *expected["a_distinct"])
            self._assert_rate(pair["distinct"]["b_distinct_coverage_by_a"], *expected["b_distinct"])
            self.assertEqual(pair["distinct"]["union_count"], expected["union"])
            self._assert_rate(pair["distinct"]["jaccard"], *expected["jaccard"])
            self.assertTrue(pair["unordered"])
            self.assertTrue(pair["calculated_identically"])
            self.assertFalse(pair["pooled_into_b1_b2_d1_aggregate"])
            self.assertFalse(pair["b0_included_in_causal_comparison"])
            if "B0" in key:
                self.assertEqual(pair["b0_role"], "external_comparator")
            else:
                self.assertIsNone(pair["b0_role"])
        repeated = summary["pairs"][0]
        self.assertEqual(repeated["row_coverage"]["b_to_a"]["rate"], 3 / 5)
        self.assertEqual(repeated["distinct"]["b_distinct_coverage_by_a"]["rate"], 1 / 3)
        self.assertNotEqual(
            repeated["row_coverage"]["b_to_a"]["rate"],
            repeated["distinct"]["b_distinct_coverage_by_a"]["rate"],
        )
        self.assertEqual(repeated["row_coverage"]["a_to_b"]["denominator"], 2)
        self.assertNotEqual(repeated["row_coverage"]["b_to_a"]["denominator"], 6)
        global_block = summary["global_sequence_free_accounting"]
        self.assertEqual(global_block["global_distinct_valid_sequence_count"], 7)
        self.assertEqual(global_block["distinct_sequences_in_exactly_n_conditions"], {"1": 5, "2": 2, "3": 0, "4": 0})
        patterns = {tuple(item["conditions"]): item["distinct_sequence_count"] for item in global_block["membership_patterns"]}
        self.assertEqual(patterns, EXPECTED_PATTERNS)
        reconciliation = global_block["reconciliation"]
        self.assertEqual(reconciliation["membership_pattern_count_sum"], 7)
        self.assertEqual(reconciliation["exactly_n_condition_count_sum"], 7)
        self.assertEqual(reconciliation["global_distinct_valid_sequence_count"], 7)
        self.assertTrue(reconciliation["membership_pattern_counts_sum_to_global_union"])
        self.assertTrue(reconciliation["exactly_n_condition_counts_sum_to_global_union"])
        self.assertTrue(global_block["membership_pattern_counts_sum_to_global_union"])
        self.assertEqual(summary["b0_role"], "external_comparator")
        self.assertEqual(summary["b0_external_comparator_labels"]["B0"], "external_comparator")
        self.assertFalse(summary["b0_pooled_into_b1_b2_d1_aggregate"])
        self.assertFalse(summary["b0_included_in_causal_comparison"])
        self.assertIn("not pooled", summary["b0_not_pooled_statement"])
        for role in ("TRAIN", "VALIDATION", "REF", "EVAL"):
            self.assertIn(role, summary["protected_datasets_not_accessed_statement"])
        self.assertIn("not accessed", summary["protected_datasets_not_accessed_statement"])
        self.assertFalse(summary["train_accessed"])
        self.assertFalse(summary["validation_accessed"])
        self.assertFalse(summary["ref_accessed"])
        self.assertFalse(summary["eval_accessed"])
        self.assertFalse(summary["sequence_strings_emitted"])
        self.assertFalse(summary["sequence_hashes_emitted"])
        self.assertFalse(summary["attempt_identifiers_emitted"])
        self.assertFalse(summary["overlap_member_lists_emitted"])
        self._assert_no_private_leak((summary_blob, manifest_blob), self.rows)
        self.assertTrue(all(not text.endswith(".jsonl") for text in opened))
        self.assertTrue(any(text.endswith("generator_eval_overlap_leakage_contract.json") for text in opened))
        self.assertTrue(any(text.endswith("aptarank_full_mres_thesis_evaluation_plan.md") for text in opened))

    def test_manifest_records_digests_rules_and_access_boundary(self):
        self._run()
        summary, manifest, summary_blob, manifest_blob = self._read_outputs()
        head = subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"], text=True).strip()
        self.assertEqual(manifest["runner_git_commit"], head)
        self.assertEqual(manifest["contract"]["contract_id"], "m9a-overlap-leakage-definitions-v1")
        self.assertEqual(manifest["contract"]["expected_sha256"], runner.FROZEN_OVERLAP_CONTRACT_SHA256)
        self.assertEqual(manifest["contract"]["recomputed_sha256"], runner.FROZEN_OVERLAP_CONTRACT_SHA256)
        self.assertEqual(manifest["contract"]["recomputed_sha256"], file_sha256(os.path.join(ROOT, runner.CONTRACT_RELATIVE_PATH)))
        self.assertEqual(manifest["contract"]["byte_count"], os.path.getsize(os.path.join(ROOT, runner.CONTRACT_RELATIVE_PATH)))
        self.assertEqual(manifest["governing_plan"]["expected_sha256"], runner.GOVERNING_PLAN_SHA256)
        self.assertEqual(manifest["governing_plan"]["recomputed_sha256"], runner.GOVERNING_PLAN_SHA256)
        self.assertEqual(manifest["governing_plan"]["recomputed_sha256"], file_sha256(os.path.join(ROOT, runner.GOVERNING_PLAN_RELATIVE_PATH)))
        self.assertEqual(manifest["governing_plan"]["byte_count"], os.path.getsize(os.path.join(ROOT, runner.GOVERNING_PLAN_RELATIVE_PATH)))
        ledger = manifest["combined_ledger"]
        self.assertEqual(ledger["expected_sha256"], sha256(self.blob))
        self.assertEqual(ledger["recomputed_sha256"], sha256(self.blob))
        self.assertEqual(ledger["byte_count"], len(self.blob))
        self.assertEqual(ledger["row_count"], self.counts["combined"])
        self.assertEqual(ledger["row_counts"], self.counts)
        self.assertEqual(ledger["supplied_as"], "in_memory_bytes")
        self.assertIsNone(ledger["relative_path"])
        summary_record = manifest["outputs"][0]
        self.assertEqual(summary_record["sha256"], sha256(summary_blob))
        self.assertEqual(summary_record["byte_count"], len(summary_blob))
        self.assertIsNone(summary_record["row_count"])
        rules = manifest["metric_grain_and_denominator_rules"]
        self.assertEqual(rules["row_grain"], "valid_canonical_row")
        self.assertEqual(rules["distinct_grain"], "distinct_valid_sequence")
        self.assertIn("null", rules["row_rate"])
        self.assertFalse(rules["invalid_rows_enter_valid_denominators"])
        self.assertTrue(rules["zero_required_denominator_is_null"])
        self.assertFalse(rules["zero_required_denominator_becomes_zero"])
        self.assertEqual(rules["condition_pairs"], [list(pair) for pair in runner.CONDITION_PAIRS])
        self.assertTrue(manifest["deterministic_serialization"])
        self.assertIn("UTF-8 JSON", manifest["serialization"])
        boundary = manifest["access_boundary"]
        for key in (
            "train_accessed",
            "validation_accessed",
            "ref_accessed",
            "eval_accessed",
            "models_accessed",
            "checkpoints_accessed",
            "structure_tools_accessed",
            "aptarank_accessed",
            "sealed_combined_ledger_opened",
            "production_totals_enforced",
            "rows_repaired",
            "rows_reordered",
            "rows_deduplicated",
            "rows_replenished",
            "rows_rewritten",
            "b0_pooled_into_b1_b2_d1_aggregate",
            "synthetic_execution_is_production_validation",
        ):
            self.assertIs(boundary[key], False)
        self.assertFalse(manifest["manifest_file"]["sha256_embedded"])
        self.assertNotIn(sha256(manifest_blob).encode("ascii"), manifest_blob)
        self.assertEqual(summary["schema"], runner.SUMMARY_SCHEMA)
        self.assertEqual(manifest["schema"], runner.MANIFEST_SCHEMA)
        self.assertNotIn(b"\r", summary_blob + manifest_blob)
        self.assertTrue(summary_blob.endswith(b"\n"))
        self.assertTrue(manifest_blob.endswith(b"\n"))

    def test_repeat_run_is_byte_identical(self):
        self._run()
        second = os.path.join(self.temp.name, "out-2")
        self._run(output=second)
        for filename in runner.OUTPUT_FILENAMES:
            with open(os.path.join(self.output, filename), "rb") as handle:
                first_blob = handle.read()
            with open(os.path.join(second, filename), "rb") as handle:
                second_blob = handle.read()
            self.assertEqual(first_blob, second_blob)

    def test_zero_denominators_are_null_and_patterns_reconcile(self):
        rows = annotate(zero_groups())
        blob = ledger_bytes(rows)
        counts = counts_for(rows)
        self._run(blob, counts)
        summary, _manifest, summary_blob, manifest_blob = self._read_outputs()
        empty = [item for item in summary["pairs"] if (item["condition_a"], item["condition_b"]) == ("B0", "B2")][0]
        self._assert_rate(empty["row_coverage"]["a_to_b"], 0, 0)
        self._assert_rate(empty["row_coverage"]["b_to_a"], 0, 0)
        self._assert_rate(empty["distinct"]["a_distinct_coverage_by_b"], 0, 0)
        self._assert_rate(empty["distinct"]["jaccard"], 0, 0)
        self.assertIsNone(empty["distinct"]["jaccard"]["rate"])
        directional = [item for item in summary["pairs"] if (item["condition_a"], item["condition_b"]) == ("B1", "D1")][0]
        self._assert_rate(directional["row_coverage"]["a_to_b"], 0, 0)
        self._assert_rate(directional["row_coverage"]["b_to_a"], 0, 1)
        self.assertEqual(directional["row_coverage"]["b_to_a"]["rate"], 0)
        self.assertIsNone(directional["distinct"]["a_distinct_coverage_by_b"]["rate"])
        global_block = summary["global_sequence_free_accounting"]
        self.assertEqual(global_block["global_distinct_valid_sequence_count"], 1)
        self.assertEqual(global_block["distinct_sequences_in_exactly_n_conditions"], {"1": 1, "2": 0, "3": 0, "4": 0})
        self.assertEqual(global_block["membership_patterns"], [{"conditions": ["D1"], "distinct_sequence_count": 1}])
        self.assertEqual(global_block["reconciliation"]["membership_pattern_count_sum"], 1)
        self.assertEqual(global_block["reconciliation"]["exactly_n_condition_count_sum"], 1)
        self._assert_no_private_leak((summary_blob, manifest_blob), rows)

    def test_invalid_row_semantics_are_refused(self):
        cases = []
        retained = copy.deepcopy(self.rows)
        retained[2]["parsed_sequence"] = "AAAA"
        cases.append(retained)
        multiplicity = copy.deepcopy(self.rows)
        multiplicity[2]["valid_sequence_multiplicity"] = 1
        cases.append(multiplicity)
        canonical = copy.deepcopy(self.rows)
        canonical[11]["parsed_sequence"] = "ACGU"
        canonical[11]["parsed_length"] = 4
        cases.append(canonical)
        missing = copy.deepcopy(self.rows)
        missing[0]["parsed_sequence"] = None
        missing[0]["parsed_length"] = None
        cases.append(missing)
        for rows in cases:
            blob = ledger_bytes(rows)
            with self.assertRaises(runner.OverlapRunnerError) as caught:
                self._run(blob, counts_for(rows), output=os.path.join(self.temp.name, "invalid-" + sha256(blob)[:8]))
            self.assertIn(caught.exception.code, ("invalid_row_semantics", "valid_sequence_invalid", "ledger_schema_invalid"))
        self.assertFalse(os.path.exists(self.output))

    def test_combined_ledger_hash_mismatch_writes_nothing(self):
        identities = identities_for(self.blob, self.counts)
        identities["combined_ledger_sha256"] = "0" * 64
        with self.assertRaises(runner.OverlapRunnerError) as caught:
            self._run(identities=identities)
        self.assertEqual(caught.exception.code, "combined_ledger_hash_mismatch")
        self.assertFalse(os.path.exists(self.output))
        self.assertEqual([name for name in os.listdir(self.temp.name) if name.startswith(runner.TEMP_PREFIX)], [])

    def _alternate_root(self, *, contract_bytes, plan_bytes):
        root = os.path.join(self.temp.name, "alternate-root")
        os.makedirs(os.path.join(root, "config", "modelling"), exist_ok=True)
        os.makedirs(os.path.join(root, "docs"), exist_ok=True)
        with open(os.path.join(root, runner.CONTRACT_RELATIVE_PATH), "wb") as handle:
            handle.write(contract_bytes)
        with open(os.path.join(root, runner.GOVERNING_PLAN_RELATIVE_PATH), "wb") as handle:
            handle.write(plan_bytes)
        return root

    def test_contract_and_governing_plan_digest_mismatches_write_nothing(self):
        with open(os.path.join(ROOT, runner.CONTRACT_RELATIVE_PATH), "rb") as handle:
            contract = bytearray(handle.read())
        with open(os.path.join(ROOT, runner.GOVERNING_PLAN_RELATIVE_PATH), "rb") as handle:
            plan = bytearray(handle.read())
        self.assertEqual(sha256(contract), runner.FROZEN_OVERLAP_CONTRACT_SHA256)
        self.assertEqual(sha256(plan), runner.GOVERNING_PLAN_SHA256)
        altered_contract = bytearray(contract)
        altered_contract[-1] ^= 0x01
        altered_plan = bytearray(plan)
        altered_plan[-1] ^= 0x01
        with self.assertRaises(runner.OverlapRunnerError) as contract_error:
            self._run(root=self._alternate_root(contract_bytes=altered_contract, plan_bytes=plan))
        self.assertEqual(contract_error.exception.code, "contract_digest_mismatch")
        with self.assertRaises(runner.OverlapRunnerError) as plan_error:
            self._run(
                root=self._alternate_root(contract_bytes=contract, plan_bytes=altered_plan),
                output=os.path.join(self.temp.name, "plan-out"),
            )
        self.assertEqual(plan_error.exception.code, "governing_plan_digest_mismatch")
        self.assertFalse(os.path.exists(self.output))
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "plan-out")))
        self.assertEqual(file_sha256(os.path.join(ROOT, runner.CONTRACT_RELATIVE_PATH)), runner.FROZEN_OVERLAP_CONTRACT_SHA256)
        self.assertEqual(file_sha256(os.path.join(ROOT, runner.GOVERNING_PLAN_RELATIVE_PATH)), runner.GOVERNING_PLAN_SHA256)

    def test_malformed_jsonl_is_refused(self):
        samples = (
            b"\xff\n",
            b"{}\n\n",
            b"[]\n",
            b'{"a": 1}{"b": 2}\n',
            b'{"a": 1}',
            b"not-json\n",
            b'{"a": 1}\r\n',
        )
        zero = {name: 0 for name in ("B0", "B1", "B2", "D1", "combined")}
        for sample in samples:
            with self.assertRaises(runner.OverlapRunnerError) as caught:
                self._run(sample, zero, output=os.path.join(self.temp.name, "bad-" + sha256(sample)[:8]))
            self.assertEqual(caught.exception.code, "jsonl_malformed")
        self.assertFalse(os.path.exists(self.output))

    def test_schema_and_version_drift_are_refused(self):
        cases = []
        extra = copy.deepcopy(self.rows)
        extra[0]["unexpected"] = 1
        cases.append(extra)
        missing = copy.deepcopy(self.rows)
        del missing[0]["ledger_schema"]
        cases.append(missing)
        schema = copy.deepcopy(self.rows)
        schema[0]["ledger_schema"] = "generator-eval-production-ledger-m9-r0"
        cases.append(schema)
        parser = copy.deepcopy(self.rows)
        parser[0]["parser_version"] = "m9-biological-parser-v0"
        cases.append(parser)
        adapter = copy.deepcopy(self.rows)
        adapter[0]["adapter_version"] = "m9-source-adapter-v1"
        cases.append(adapter)
        codes = []
        for rows in cases:
            blob = self._dump(rows)
            with self.assertRaises(runner.OverlapRunnerError) as caught:
                self._run(blob, counts_for(rows), output=os.path.join(self.temp.name, "drift-" + sha256(blob)[:8]))
            codes.append(caught.exception.code)
        self.assertIn("ledger_schema_invalid", codes)
        self.assertIn("parser_version_mismatch", codes)
        self.assertIn("adapter_version_mismatch", codes)
        self.assertFalse(os.path.exists(self.output))

    def test_wrong_order_counts_duplicate_identity_and_stored_flags(self):
        groups = {condition: production.annotate_exact_duplicates(rows) for condition, rows in main_groups().items()}
        reordered = groups["B1"] + groups["B0"] + groups["B2"] + groups["D1"]
        blob = ledger_bytes(reordered)
        with self.assertRaises(runner.OverlapRunnerError) as order_error:
            self._run(blob, counts_for(reordered), output=os.path.join(self.temp.name, "order"))
        self.assertEqual(order_error.exception.code, "condition_order_invalid")
        wrong_counts = dict(self.counts)
        wrong_counts["B0"] += 1
        wrong_counts["combined"] += 1
        with self.assertRaises(runner.OverlapRunnerError) as count_error:
            self._run(counts=wrong_counts, output=os.path.join(self.temp.name, "counts"))
        self.assertEqual(count_error.exception.code, "row_count_mismatch")
        duplicated = copy.deepcopy(self.rows)
        duplicated[4]["record_id"] = duplicated[3]["record_id"]
        blob = ledger_bytes(duplicated)
        with self.assertRaises(runner.OverlapRunnerError) as duplicate_error:
            self._run(blob, counts_for(duplicated), output=os.path.join(self.temp.name, "duplicate"))
        self.assertEqual(duplicate_error.exception.code, "attempt_id_duplicated")
        multiplicity = copy.deepcopy(self.rows)
        multiplicity[3]["valid_sequence_multiplicity"] = 2
        blob = ledger_bytes(multiplicity)
        with self.assertRaises(runner.OverlapRunnerError) as multiplicity_error:
            self._run(blob, counts_for(multiplicity), output=os.path.join(self.temp.name, "multiplicity"))
        self.assertEqual(multiplicity_error.exception.code, "multiplicity_mismatch")
        flag = copy.deepcopy(self.rows)
        flag[6]["is_exact_duplicate_within_condition"] = True
        blob = ledger_bytes(flag)
        with self.assertRaises(runner.OverlapRunnerError) as flag_error:
            self._run(blob, counts_for(flag), output=os.path.join(self.temp.name, "flag"))
        self.assertEqual(flag_error.exception.code, "duplicate_flag_mismatch")
        self.assertFalse(os.path.exists(self.output))

    def test_existing_empty_output_directory_is_refused(self):
        os.makedirs(self.output)
        with self.assertRaises(runner.OverlapRunnerError) as caught:
            self._run()
        self.assertEqual(caught.exception.code, "output_exists")
        self.assertEqual(os.listdir(self.output), [])
        self.assertTrue(os.path.isdir(self.output))
        self.assertEqual([name for name in os.listdir(self.temp.name) if name.startswith(runner.TEMP_PREFIX)], [])
        marker = os.path.join(self.output, "keep.txt")
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write("keep")
        with self.assertRaises(runner.OverlapRunnerError):
            self._run()
        with open(marker, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "keep")

    def test_validation_failure_removes_the_temporary_directory(self):
        original = runner.validate_published_directory

        def fail(directory, expected):
            raise runner.OverlapRunnerError("output_validation_failed", "injected")

        runner.validate_published_directory = fail
        try:
            with self.assertRaises(runner.OverlapRunnerError) as caught:
                self._run()
        finally:
            runner.validate_published_directory = original
        self.assertEqual(caught.exception.code, "output_validation_failed")
        self.assertFalse(os.path.exists(self.output))
        self.assertEqual([name for name in os.listdir(self.temp.name) if name.startswith(runner.TEMP_PREFIX)], [])

    def test_protected_controls_are_refused(self):
        for role in ("TRAIN", "VALIDATION", "REF", "EVAL"):
            with self.assertRaises(biological.ParserContractError) as role_error:
                self._run(role=role)
            self.assertEqual(role_error.exception.code, "role_refused")
            with self.assertRaises(runner.OverlapRunnerError) as path_error:
                self._run(output=os.path.join(self.temp.name, role, "out"))
            self.assertEqual(path_error.exception.code, "role_refused")
            self.assertFalse(os.path.exists(os.path.join(self.temp.name, role, "out")))
        with self.assertRaises(biological.ParserContractError) as ledger_path:
            runner.run_cross_condition_overlap(
                "/tmp/m9_all_conditions_derived_attempt_ledger.jsonl",
                identities_for(self.blob, self.counts),
                self.output,
                enforce_production_counts=False,
            )
        self.assertEqual(ledger_path.exception.code, "filesystem_path_refused")
        self.assertFalse(os.path.exists(self.output))

    def test_production_counts_are_separate_from_miniature_runs(self):
        self._run(enforce_production_counts=False)
        self.assertTrue(os.path.isdir(self.output))
        with self.assertRaises(runner.OverlapRunnerError) as caught:
            self._run(enforce_production_counts=True, output=os.path.join(self.temp.name, "production-sized"))
        self.assertEqual(caught.exception.code, "production_count_mismatch")
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "production-sized")))
        identities = runner.sealed_identities()
        self.assertEqual(identities["row_counts"], {"B0": 30080, "B1": 30000, "B2": 30000, "D1": 30000, "combined": 120080})
        self.assertEqual(identities["combined_ledger_sha256"], "d50c30e85b26e39e8a25ea2660f9a7fa07433417de757364eb36799ca8c6073e")
        self.assertEqual(identities["contract_id"], "m9a-overlap-leakage-definitions-v1")
        self.assertEqual(identities["contract_sha256"], runner.FROZEN_OVERLAP_CONTRACT_SHA256)
        self.assertEqual(identities["governing_plan_sha256"], runner.GOVERNING_PLAN_SHA256)
        self.assertEqual(
            runner.SEALED_COMBINED_LEDGER_RELATIVE,
            "results/fine_tuning/m9_generator_evaluation/m9_all_conditions_derived_attempt_ledger.jsonl",
        )
        self.assertEqual(
            runner.FUTURE_OUTPUT_RELATIVE,
            "results/fine_tuning/m9_generator_evaluation/m9a_exact_cross_condition_overlap",
        )
        source = inspect.getsource(runner.run_sealed_cross_condition_overlap)
        self.assertIn("enforce_production_counts=True", source)
        self.assertIn("sealed_locator_opened=True", source)
        self.assertNotIn("run_sealed_cross_condition_overlap(", inspect.getsource(self._run))

    def _dump(self, rows):
        chunks = []
        for row in rows:
            chunks.append(json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8"))
            chunks.append(b"\n")
        return b"".join(chunks)


if __name__ == "__main__":
    unittest.main()

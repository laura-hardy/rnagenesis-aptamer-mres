"""Synthetic tests for the frozen M9A overlap and leakage definitions.

Sequences in this module are constructed literals. No production ledger, TRAIN,
VALIDATION, REF, EVAL, model, checkpoint, structure resource, or AptaRank
resource is opened. A passing run is not production validation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import sys
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)

import generator_eval_derived_ledger as ledger
import generator_eval_overlap_leakage as overlap
import generator_eval_parser as biological

CONTRACT_PATH = os.path.join(ROOT, "config", "modelling", "generator_eval_overlap_leakage_contract.json")
DOC_PATH = os.path.join(ROOT, "docs", "fine_tuning", "m9_overlap_leakage_contract.md")
PLAN_PATH = os.path.join(ROOT, "docs", "aptarank_full_mres_thesis_evaluation_plan.md")
PINNED_SPECS = (
    os.path.join(ROOT, "config", "modelling", "generator_eval_metric_spec.json"),
    os.path.join(ROOT, "config", "modelling", "aptarank_io_spec.json"),
    os.path.join(ROOT, "config", "modelling", "aptarank_tier1_analysis_spec.json"),
)
SEQUENCES = ("AAAA", "AAAC", "CCCC", "GGGG", "UUUU", "AAAG", "AAAU", "ACGT")
TRAIN_MATCH = "ACGUACGU"
TRAIN_OTHER = "GGGGCCCC"
TRAIN_MISS = "UUUUAAAA"


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        digest.update(handle.read())
    return digest.hexdigest()


def parsed_row(record_id, condition, sequence=None, *, outcome=None, seed=None):
    item = ledger.blank_derived_row()
    item["record_id"] = record_id
    item["condition"] = condition
    if outcome is None:
        outcome = biological.OUTCOME_VALID if sequence is not None else biological.OUTCOME_EMPTY
    item["outcome"] = outcome
    if outcome == biological.OUTCOME_VALID:
        item["parsed_sequence"] = sequence
        item["parsed_length"] = len(sequence)
        item["failure_reason"] = None
    elif outcome == biological.OUTCOME_NON_ACGU:
        item["parsed_sequence"] = sequence
        item["parsed_length"] = 0 if sequence is None else len(sequence)
        item["failure_reason"] = outcome
    else:
        item["parsed_sequence"] = None
        item["parsed_length"] = 0
        item["failure_reason"] = outcome
    item["d1_training_seed"] = seed if condition == "D1" else None
    if condition == "D1" and item["d1_training_seed"] is None:
        item["d1_training_seed"] = 43
    return item


def overlap_population():
    rows = [
        parsed_row("b0-only", "B0", "AAAA"),
        parsed_row("b0-shared", "B0", "AAAC"),
        parsed_row("b1-repeat-1", "B1", "AAAC"),
        parsed_row("b1-repeat-2", "B1", "AAAC"),
        parsed_row("b1-repeat-3", "B1", "AAAC"),
        parsed_row("b1-only", "B1", "CCCC"),
        parsed_row("b1-shared-b2", "B1", "GGGG"),
        parsed_row("b1-invalid", "B1", outcome=biological.OUTCOME_EMPTY),
        parsed_row("b2-shared", "B2", "GGGG"),
        parsed_row("b2-only", "B2", "UUUU"),
        parsed_row("b2-invalid", "B2", "ACGT", outcome=biological.OUTCOME_NON_ACGU),
        parsed_row("d1-43", "D1", "AAAG", seed=43),
        parsed_row("d1-44", "D1", "AAAU", seed=44),
    ]
    return rows


def leakage_population():
    return [
        parsed_row("b0-miss", "B0", "AAAACCCC"),
        parsed_row("b1-match", "B1", TRAIN_MATCH),
        parsed_row("b1-miss", "B1", TRAIN_MISS),
        parsed_row("d43-match", "D1", TRAIN_MATCH, seed=43),
        parsed_row("d43-miss", "D1", TRAIN_MISS, seed=43),
        parsed_row("d44-match", "D1", TRAIN_MATCH, seed=44),
        parsed_row("d44-miss-1", "D1", "AAAAACCC", seed=44),
        parsed_row("d44-miss-2", "D1", "AAAAGGGG", seed=44),
        parsed_row("d44-miss-3", "D1", "AAAAUUUU", seed=44),
    ]


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


def pair_named(summary, condition_a, condition_b):
    found = [
        item
        for item in summary["pairs"]
        if item["condition_a"] == condition_a and item["condition_b"] == condition_b
    ]
    if len(found) != 1:
        raise AssertionError("missing pair " + condition_a + " " + condition_b)
    return found[0]


class OverlapLeakageContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load_json(CONTRACT_PATH)

    def test_contract_identity_and_plan_pins(self):
        plan_hash = sha256(PLAN_PATH)
        self.assertEqual(self.contract["status"], overlap.STATUS)
        self.assertEqual(self.contract["contract_id"], overlap.CONTRACT_ID)
        self.assertFalse(self.contract["m9a_complete"])
        self.assertFalse(self.contract["m9b_complete"])
        self.assertFalse(self.contract["m9c_complete"])
        self.assertFalse(self.contract["synthetic_execution_is_production_validation"])
        self.assertEqual(self.contract["references"]["parser_version"], "m9-biological-parser-v1")
        self.assertEqual(self.contract["references"]["adapter_version"], "m9-source-adapter-v2")
        self.assertEqual(self.contract["references"]["combined_ledger"]["sha256"], overlap.COMBINED_LEDGER_SHA256)
        self.assertEqual(self.contract["references"]["production_manifest"]["sha256"], overlap.PRODUCTION_MANIFEST_SHA256)
        self.assertEqual(self.contract["references"]["governing_plan"]["sha256"], plan_hash)
        self.assertEqual(plan_hash, overlap.GOVERNING_PLAN_SHA256)
        self.assertEqual(self.contract["references"]["gep2_metric_specification"]["freeze_status"], "draft")
        self.assertTrue(self.contract["references"]["gep2_metric_specification"]["remains_draft"])
        self.assertEqual(self.contract["within_condition_distinct_sum_label"]["value"], 120063)
        self.assertFalse(self.contract["within_condition_distinct_sum_label"]["is_global_distinctness"])
        for path in PINNED_SPECS:
            spec = load_json(path)
            self.assertEqual(spec["governing_plan"]["sha256"], plan_hash)
        metric_spec = load_json(PINNED_SPECS[0])
        self.assertEqual(metric_spec["freeze_status"], "draft")
        with open(DOC_PATH, "r", encoding="utf-8") as handle:
            document = handle.read()
        self.assertIn(overlap.STATUS, document)
        self.assertIn(sha256(CONTRACT_PATH), document)
        self.assertIn(plan_hash, document)

    def test_repeated_source_rows_differ_from_distinct_coverage_and_directions(self):
        summary = overlap.cross_condition_overlap(overlap_population(), self.contract)
        pair = pair_named(summary, "B0", "B1")
        self.assertEqual(pair["row_coverage"]["b_to_a"]["numerator"], 3)
        self.assertEqual(pair["row_coverage"]["b_to_a"]["denominator"], 5)
        self.assertEqual(pair["row_coverage"]["b_to_a"]["rate"], 3 / 5)
        self.assertEqual(pair["distinct"]["b_distinct_coverage_by_a"]["numerator"], 1)
        self.assertEqual(pair["distinct"]["b_distinct_coverage_by_a"]["denominator"], 3)
        self.assertEqual(pair["distinct"]["b_distinct_coverage_by_a"]["rate"], 1 / 3)
        self.assertNotEqual(pair["row_coverage"]["b_to_a"]["rate"], pair["distinct"]["b_distinct_coverage_by_a"]["rate"])
        self.assertEqual(pair["row_coverage"]["a_to_b"]["numerator"], 1)
        self.assertEqual(pair["row_coverage"]["a_to_b"]["denominator"], 2)
        self.assertEqual(pair["row_coverage"]["a_to_b"]["rate"], 1 / 2)
        self.assertNotEqual(pair["row_coverage"]["a_to_b"]["rate"], pair["row_coverage"]["b_to_a"]["rate"])

    def test_all_six_pairs_and_b0_external_comparator(self):
        summary = overlap.cross_condition_overlap(overlap_population(), self.contract)
        observed = [(item["condition_a"], item["condition_b"]) for item in summary["pairs"]]
        self.assertEqual(observed, list(overlap.CONDITION_PAIRS))
        self.assertEqual(summary["b0_role"], "external_comparator")
        self.assertFalse(summary["b0_pooled_into_b1_b2_d1_aggregate"])
        self.assertFalse(summary["b0_included_in_causal_comparison"])
        self.assertNotIn("b0_b1_b2_d1_aggregate", summary)
        for item in summary["pairs"]:
            self.assertTrue(item["calculated_identically"])
            self.assertFalse(item["pooled_into_b1_b2_d1_aggregate"])
            self.assertFalse(item["b0_included_in_causal_comparison"])
            includes_b0 = item["condition_a"] == "B0" or item["condition_b"] == "B0"
            if includes_b0:
                self.assertEqual(item["b0_role"], "external_comparator")
            else:
                self.assertIsNone(item["b0_role"])
        self.assertEqual(summary["attempt_accounting"]["B0"]["role"], "external_comparator")

    def test_invalid_rows_stay_in_accounting_and_out_of_valid_denominators(self):
        summary = overlap.cross_condition_overlap(overlap_population(), self.contract)
        b1 = summary["attempt_accounting"]["B1"]
        b2 = summary["attempt_accounting"]["B2"]
        self.assertEqual(b1["raw_source_attempts"], 6)
        self.assertEqual(b1["valid_canonical_sequences"], 5)
        self.assertEqual(b1["empty_outputs"], 1)
        self.assertFalse(b1["invalid_rows_deleted"])
        self.assertEqual(b2["raw_source_attempts"], 3)
        self.assertEqual(b2["valid_canonical_sequences"], 2)
        self.assertEqual(b2["parsed_non_acgu_outputs"], 1)
        pair = pair_named(summary, "B1", "B2")
        self.assertEqual(pair["row_coverage"]["a_to_b"]["denominator"], 5)
        self.assertEqual(pair["row_coverage"]["b_to_a"]["denominator"], 2)
        self.assertNotEqual(pair["row_coverage"]["a_to_b"]["denominator"], b1["raw_source_attempts"])

    def test_zero_denominators_are_null(self):
        rows = [
            parsed_row("b1-only", "B1", "AAAA"),
            parsed_row("d1-invalid", "D1", outcome=biological.OUTCOME_EMPTY, seed=43),
        ]
        summary = overlap.cross_condition_overlap(rows, self.contract)
        pair = pair_named(summary, "B1", "D1")
        self.assertEqual(pair["row_coverage"]["b_to_a"]["numerator"], 0)
        self.assertEqual(pair["row_coverage"]["b_to_a"]["denominator"], 0)
        self.assertIsNone(pair["row_coverage"]["b_to_a"]["rate"])
        self.assertEqual(pair["row_coverage"]["a_to_b"]["denominator"], 1)
        self.assertEqual(pair["row_coverage"]["a_to_b"]["rate"], 0)
        self.assertEqual(pair["distinct"]["b_distinct_coverage_by_a"]["denominator"], 0)
        self.assertIsNone(pair["distinct"]["b_distinct_coverage_by_a"]["rate"])
        self.assertEqual(pair["distinct"]["jaccard"]["denominator"], 1)
        self.assertEqual(pair["distinct"]["jaccard"]["rate"], 0)
        empty = pair_named(summary, "B0", "B2")
        self.assertEqual(empty["distinct"]["jaccard"]["numerator"], 0)
        self.assertEqual(empty["distinct"]["jaccard"]["denominator"], 0)
        self.assertIsNone(empty["distinct"]["jaccard"]["rate"])
        self.assertEqual(summary["attempt_accounting"]["D1"]["raw_source_attempts"], 1)
        self.assertEqual(summary["attempt_accounting"]["D1"]["valid_canonical_sequences"], 0)

    def test_global_union_reconciles_membership_patterns_without_sequences(self):
        summary = overlap.cross_condition_overlap(overlap_population(), self.contract)
        global_accounting = summary["global_sequence_free_accounting"]
        self.assertEqual(global_accounting["global_distinct_valid_sequence_count"], 7)
        exactly = global_accounting["distinct_sequences_in_exactly_n_conditions"]
        self.assertEqual(exactly, {"1": 5, "2": 2, "3": 0, "4": 0})
        self.assertEqual(sum(exactly.values()), global_accounting["global_distinct_valid_sequence_count"])
        pattern_sum = sum(item["distinct_sequence_count"] for item in global_accounting["membership_patterns"])
        self.assertEqual(pattern_sum, 7)
        self.assertTrue(global_accounting["membership_pattern_counts_sum_to_global_union"])
        patterns = {tuple(item["conditions"]): item["distinct_sequence_count"] for item in global_accounting["membership_patterns"]}
        self.assertEqual(patterns[("B0", "B1")], 1)
        self.assertEqual(patterns[("B1", "B2")], 1)
        self.assertEqual(patterns[("D1",)], 2)
        labelled = summary["within_condition_distinct_sum"]
        self.assertEqual(labelled["synthetic_sum_of_within_condition_distinct_counts"], 9)
        self.assertFalse(labelled["synthetic_sum_is_global_distinctness"])
        self.assertEqual(labelled["production_field"], "overall.distinct_valid_sequences")
        self.assertEqual(labelled["production_value"], 120063)
        self.assertFalse(labelled["production_value_is_global_distinctness"])
        self.assertFalse(labelled["production_value_reused_as_global_distinctness"])
        self.assertNotEqual(global_accounting["global_distinct_valid_sequence_count"], labelled["production_value"])
        self.assertNotEqual(
            global_accounting["global_distinct_valid_sequence_count"],
            labelled["synthetic_sum_of_within_condition_distinct_counts"],
        )
        rendered = list(strings_in(summary))
        for sequence in SEQUENCES:
            self.assertNotIn(sequence, rendered)
        self.assertTrue(all(biological.CANONICAL_SEQUENCE.fullmatch(item) is None for item in rendered))
        self.assertFalse(summary["sequence_strings_emitted"])
        self.assertFalse(summary["sequence_hashes_emitted"])

    def test_exact_train_matches_nonmatches_and_duplicate_cores_are_refused(self):
        cores = [TRAIN_MATCH, TRAIN_OTHER]
        summary = overlap.exact_train_leakage(leakage_population(), cores, self.contract)
        b1 = summary["by_condition"]["B1"]
        self.assertEqual(b1["row_leakage"], {"numerator": 1, "denominator": 2, "rate": 1 / 2})
        self.assertEqual(b1["distinct_sequence_sensitivity"]["numerator"], 1)
        self.assertEqual(b1["distinct_sequence_sensitivity"]["denominator"], 2)
        self.assertFalse(b1["historical_0_01_guardrail_used_as_decision_threshold"])
        self.assertFalse(summary["partial_match"])
        self.assertFalse(summary["substring_match"])
        self.assertIsNone(summary["identity_threshold"])
        self.assertEqual(summary["by_condition"]["B0"]["role"], "external_comparator")
        self.assertFalse(summary["b0_pooled_into_b1_b2_d1_aggregate"])
        b2 = summary["by_condition"]["B2"]["row_leakage"]
        self.assertEqual(b2["numerator"], 0)
        self.assertEqual(b2["denominator"], 0)
        self.assertIsNone(b2["rate"])
        with self.assertRaises(overlap.OverlapLeakageError) as duplicated:
            overlap.exact_train_leakage(leakage_population(), [TRAIN_MATCH, TRAIN_MATCH], self.contract)
        self.assertEqual(duplicated.exception.code, "duplicate_train_cores")
        with self.assertRaises(overlap.OverlapLeakageError) as empty:
            overlap.exact_train_leakage(leakage_population(), [], self.contract)
        self.assertEqual(empty.exception.code, "train_cores_empty")
        with self.assertRaises(overlap.OverlapLeakageError) as noncanonical:
            overlap.exact_train_leakage(leakage_population(), ["ACGT"], self.contract)
        self.assertEqual(noncanonical.exception.code, "train_core_invalid")

    def test_d1_seed_mean_range_and_pooled_attempt_rate(self):
        summary = overlap.exact_train_leakage(leakage_population(), [TRAIN_MATCH, TRAIN_OTHER], self.contract)
        d1 = summary["d1"]
        self.assertEqual(d1["seed_43_valid_conditional_row_rate"]["rate"], 1 / 2)
        self.assertEqual(d1["seed_44_valid_conditional_row_rate"]["rate"], 1 / 4)
        self.assertEqual(d1["unweighted_arithmetic_mean_of_seed_specific_row_rates"], (1 / 2 + 1 / 4) / 2)
        self.assertEqual(d1["observed_range"], {"minimum": 1 / 4, "maximum": 1 / 2})
        pooled = d1["actual_attempt_pooled"]
        self.assertEqual(pooled["label"], "actual_attempt_pooled")
        self.assertTrue(pooled["separately_labelled"])
        self.assertFalse(pooled["replaces_seed_specific_rates"])
        self.assertEqual(pooled["row_leakage"]["numerator"], 2)
        self.assertEqual(pooled["row_leakage"]["denominator"], 6)
        self.assertEqual(pooled["row_leakage"]["rate"], 2 / 6)
        self.assertNotEqual(pooled["row_leakage"]["rate"], d1["unweighted_arithmetic_mean_of_seed_specific_row_rates"])
        self.assertIsNone(d1["confidence_interval"])
        self.assertFalse(d1["bootstrap"])
        self.assertFalse(d1["hypothesis_test"])
        rendered = list(strings_in(summary))
        self.assertNotIn(TRAIN_MATCH, rendered)
        self.assertNotIn(TRAIN_MISS, rendered)

    def test_missing_d1_seed_and_zero_valid_denominator_fail_closed(self):
        missing = [row for row in leakage_population() if row["d1_training_seed"] != 44]
        with self.assertRaises(overlap.OverlapLeakageError) as missing_seed:
            overlap.exact_train_leakage(missing, [TRAIN_MATCH], self.contract)
        self.assertEqual(missing_seed.exception.code, "d1_seed_missing")
        self.assertIn("not replaced with a pooled estimate", missing_seed.exception.detail)
        zero_valid = [
            row
            for row in leakage_population()
            if not (row["condition"] == "D1" and row["d1_training_seed"] == 44)
        ]
        zero_valid.append(parsed_row("d44-invalid", "D1", outcome=biological.OUTCOME_EMPTY, seed=44))
        with self.assertRaises(overlap.OverlapLeakageError) as zero_denominator:
            overlap.exact_train_leakage(zero_valid, [TRAIN_MATCH], self.contract)
        self.assertEqual(zero_denominator.exception.code, "d1_valid_denominator_zero")
        self.assertIn("not replaced with a pooled estimate", zero_denominator.exception.detail)

    def test_nearest_train_projects_distinct_distances_and_reuses_weighted_quantiles(self):
        rows = [
            parsed_row("d43", "D1", "A", seed=43),
            parsed_row("d44-1", "D1", "GGGG", seed=44),
            parsed_row("d44-2", "D1", "GGGG", seed=44),
            parsed_row("d44-3", "D1", "GGGG", seed=44),
        ]
        summary = overlap.nearest_train_distance_summaries(rows, ["A"], self.contract)
        seed_44 = summary["d1"]["by_training_seed"]["44"]
        self.assertEqual(seed_44["distinct_distance_computations"], 1)
        self.assertEqual(seed_44["row_distance_projections"], 3)
        self.assertEqual(seed_44["nearest_train_normalized_edit_distance"]["count"], 3)
        self.assertEqual(seed_44["maximum_edit_similarity_to_train"], 0.0)
        self.assertFalse(seed_44["edit_similarity_is_sequence_identity"])
        self.assertEqual(summary["d1"]["by_training_seed"]["43"]["maximum_edit_similarity_to_train"], 1.0)
        pooled = summary["d1"]["pooled_equal_mixture_distance_quantiles"]
        self.assertFalse(summary["d1"]["pooled_equal_mixture_distance_quantiles_absent"])
        self.assertEqual(summary["d1"]["pooled_equal_mixture_rule"], "inclusive_cumulative_weight_exact_v2")
        self.assertFalse(summary["d1"]["new_quantile_rule_invented"])
        self.assertEqual(pooled["median"], 0.0)
        self.assertEqual(pooled["p75"], 1.0)
        self.assertEqual(summary["by_condition"]["B0"]["role"], "external_comparator")
        rendered = list(strings_in(summary))
        self.assertNotIn("A", rendered)
        self.assertNotIn("GGGG", rendered)

    def test_nearest_train_pooled_quantile_is_absent_when_a_seed_has_no_valid_rows(self):
        rows = [
            parsed_row("d43", "D1", "A", seed=43),
            parsed_row("d44-invalid", "D1", outcome=biological.OUTCOME_EMPTY, seed=44),
        ]
        summary = overlap.nearest_train_distance_summaries(rows, ["A"], self.contract)
        self.assertTrue(summary["d1"]["pooled_equal_mixture_distance_quantiles_absent"])
        self.assertIsNone(summary["d1"]["pooled_equal_mixture_distance_quantiles"])
        self.assertEqual(summary["d1"]["pooled_equal_mixture_absent_reason"], "zero_valid_denominator")
        self.assertIsNone(summary["d1"]["by_training_seed"]["44"]["nearest_train_normalized_edit_distance"])
        missing = [parsed_row("d43", "D1", "A", seed=43)]
        with self.assertRaises(overlap.OverlapLeakageError) as missing_seed:
            overlap.nearest_train_distance_summaries(missing, ["A"], self.contract)
        self.assertEqual(missing_seed.exception.code, "d1_seed_missing")

    def test_filesystem_paths_and_protected_roles_are_refused(self):
        rows = overlap_population()
        with self.assertRaises(biological.ParserContractError) as ledger_path:
            overlap.cross_condition_overlap("/tmp/m9_all_conditions_derived_attempt_ledger.jsonl", self.contract)
        self.assertEqual(ledger_path.exception.code, "filesystem_path_refused")
        for role in ("TRAIN", "VALIDATION", "REF", "EVAL"):
            with self.assertRaises(biological.ParserContractError) as role_control:
                overlap.cross_condition_overlap(rows, self.contract, role=role)
            self.assertEqual(role_control.exception.code, "role_refused")
            with self.assertRaises(biological.ParserContractError) as core_role:
                overlap.exact_train_leakage(rows, role, self.contract)
            self.assertEqual(core_role.exception.code, "role_refused")
        with self.assertRaises(biological.ParserContractError) as filename:
            overlap.exact_train_leakage(rows, ["ft_train.csv"], self.contract)
        self.assertEqual(filename.exception.code, "filename_refused")
        with self.assertRaises(biological.ParserContractError) as path_object:
            overlap.nearest_train_distance_summaries(rows, pathlib.Path("/tmp/ft_validation.csv"), self.contract)
        self.assertIn(path_object.exception.code, ("filesystem_path_refused", "filename_refused"))
        with self.assertRaises(biological.ParserContractError) as unlock:
            overlap.cross_condition_overlap(rows, self.contract, eval_unlock=True)
        self.assertEqual(unlock.exception.code, "eval_unlock_refused")
        with self.assertRaises(biological.ParserContractError) as rooted:
            overlap.exact_train_leakage(rows, ["/home/laura/rnagenesis-mres-runs/ref.csv"], self.contract)
        self.assertIn(rooted.exception.code, ("filename_refused", "production_run_root_refused", "filesystem_path_refused"))

    def test_absent_required_definitions_fail_closed(self):
        for field in ("numerator", "denominator", "grain", "direction"):
            broken = copy.deepcopy(self.contract)
            del broken["definitions"]["cross_condition_overlap"][field]
            with self.assertRaises(overlap.OverlapLeakageError) as missing:
                overlap.cross_condition_overlap(overlap_population(), broken)
            self.assertEqual(missing.exception.code, "definition_absent")
        for group in (
            "distinct_sequence_sensitivity",
            "exact_train_leakage",
            "nearest_train_normalized_edit_distance",
        ):
            broken = copy.deepcopy(self.contract)
            broken["definitions"][group]["denominator"] = None
            with self.assertRaises(overlap.OverlapLeakageError) as missing_group:
                overlap.exact_train_leakage(leakage_population(), [TRAIN_MATCH], broken)
            self.assertEqual(missing_group.exception.code, "definition_absent")
        broken_pairs = copy.deepcopy(self.contract)
        del broken_pairs["definitions"]["cross_condition_overlap"]["condition_pairs"]
        with self.assertRaises(overlap.OverlapLeakageError) as missing_pairs:
            overlap.cross_condition_overlap(overlap_population(), broken_pairs)
        self.assertEqual(missing_pairs.exception.code, "definition_absent")


if __name__ == "__main__":
    unittest.main()

"""Synthetic GEP-1 contract tests.

No EVAL, REF, VALIDATION, TRAIN, pool, checkpoint, or model output is opened.
Sequences stay in the synthetic fixture files.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_module():
    path = os.path.join(ROOT, "scripts/modelling/generator_eval_preflight.py")
    spec = importlib.util.spec_from_file_location("generator_eval_preflight", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gep1 = load_module()


def fixture(name):
    path = os.path.join(gep1.fixture_root(), name)
    metadata, records = gep1.load_synthetic_fixture(path)
    return metadata, records


def codes(error):
    return [item["code"] for item in error.errors]


class MetricSpecTests(unittest.TestCase):
    def test_shipped_spec_matches_implemented_ids_and_thresholds(self):
        metrics = gep1._load_module("m4_diagnostic_metrics.py", "gep1_test_m4")
        report = gep1._load_module("m6_diagnostic_generation.py", "gep1_test_m6")
        spec = gep1.load_metric_spec()
        found = [metric["metric_id"] for metric in spec["metrics"]]
        expected = set(metrics.IMPLEMENTED_METRIC_IDS) | set(metrics.HARD_GUARDRAIL_IDS) | set(gep1.ADDITIONAL_IMPLEMENTED_METRIC_IDS)
        self.assertEqual(set(found), expected)
        self.assertEqual(len(found), len(expected))
        self.assertEqual(
            gep1.ADDITIONAL_IMPLEMENTED_METRIC_IDS,
            (
                "per_requested_length_exact_hit_rate",
                "nearest_train_normalized_edit_distance",
                "maximum_edit_similarity_to_train",
                "nucleotide_distribution",
                "dinucleotide_distribution",
                "mfe",
                "mfe_per_nt",
                "paired_fraction",
                "full_length_stratified_results",
            ),
        )
        by_id = {metric["metric_id"]: metric for metric in spec["metrics"]}
        for metric_id, rule in metrics.GUARDRAIL_THRESHOLDS.items():
            self.assertEqual(by_id[metric_id]["approved_threshold"], rule)
            self.assertEqual(by_id[metric_id]["scientific_role"], "guardrail")
        self.assertEqual(by_id["exact_hit_rate"]["direction"], "not_applicable")
        self.assertEqual(by_id["mfe"]["direction"], "not_applicable")
        self.assertEqual(by_id["mfe_per_nt"]["direction"], "not_applicable")
        self.assertEqual(by_id["exact_train_match_rate"]["direction"], "lower")
        self.assertEqual(by_id["exact_train_match_rate"]["scientific_role"], "guardrail")
        self.assertEqual(by_id["valid_nonempty_acgu_fraction"]["direction"], "higher")
        self.assertEqual(by_id["nearest_train_normalized_edit_distance"]["scientific_role"], "outcome")
        self.assertEqual(by_id["nearest_train_normalized_edit_distance"]["direction"], "higher")
        self.assertTrue(by_id["nearest_train_normalized_edit_distance"]["novelty_direction_only"])
        self.assertEqual(by_id["maximum_edit_similarity_to_train"]["scientific_role"], "outcome")
        self.assertEqual(by_id["maximum_edit_similarity_to_train"]["direction"], "lower")
        self.assertTrue(by_id["maximum_edit_similarity_to_train"]["novelty_direction_only"])
        self.assertEqual(spec["novelty_direction_statement"], gep1.NOVELTY_DIRECTION_STATEMENT)
        self.assertNotIn("closeness", spec["novelty_direction_statement"])
        self.assertIn("not extra votes for overall generator quality", spec["novelty_direction_statement"])
        self.assertTrue(all(metric["freeze_status"] == "draft" for metric in spec["metrics"]))
        self.assertEqual(spec["freeze_status"], "draft")
        self.assertNotIn("closeness", [metric["scientific_role"] for metric in spec["metrics"]])
        self.assertFalse(spec["aggregate_generator_quality_score"])
        for metric in spec["metrics"]:
            self.assertEqual(set(metric["code_revision"]), {"path", "sha256"})
            self.assertEqual(set(metric["config_revision"]), {"path", "sha256"})
            self.assertEqual(gep1._hash_revision_path(metric["code_revision"]["path"]), metric["code_revision"]["sha256"])
            self.assertEqual(gep1._hash_revision_path(metric["config_revision"]["path"]), metric["config_revision"]["sha256"])
        self.assertEqual(spec["governing_plan"]["path"], gep1.GOVERNING_PLAN_RELATIVE)
        self.assertEqual(spec["governing_plan"]["version"], "3.0")
        self.assertEqual(gep1._hash_revision_path(spec["governing_plan"]["path"]), spec["governing_plan"]["sha256"])
        for deferred in metrics.DEFERRED_BEYOND_M4:
            self.assertNotIn(deferred, found)
        covered = set(found)
        for name in report.REPORT_ONLY_ITEMS:
            if name not in covered:
                self.assertTrue(any(name in item["related_names"] for item in spec["blocking_items"]))

    def test_frozen_status_is_recognised_and_refused_for_this_package(self):
        spec = gep1.load_metric_spec()
        mutated = copy.deepcopy(spec)
        mutated["metrics"][0]["freeze_status"] = "frozen"
        mutated["freeze_status"] = "frozen"
        gep1.validate_metric_spec(mutated, require_draft=False)
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_metric_spec(mutated, require_draft=True)
        self.assertEqual(caught.exception.code, "metric_spec_frozen_in_gep1")

    def test_closeness_role_is_refused(self):
        spec = copy.deepcopy(gep1.load_metric_spec())
        spec["metrics"][0]["scientific_role"] = "closeness"
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_metric_spec(spec, require_draft=False)
        self.assertEqual(caught.exception.code, "closeness_metric_not_implemented")

    def test_source_hash_mismatch_is_detected(self):
        spec = copy.deepcopy(gep1.load_metric_spec())
        spec["governing_plan"]["sha256"] = "ab" * 32
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_metric_spec(spec, require_draft=True)
        self.assertEqual(caught.exception.code, "source_hash_mismatch")
        spec = copy.deepcopy(gep1.load_metric_spec())
        spec["metrics"][0]["code_revision"]["sha256"] = "cd" * 32
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_metric_spec(spec, require_draft=True)
        self.assertEqual(caught.exception.code, "source_hash_mismatch")
        spec = copy.deepcopy(gep1.load_metric_spec())
        spec["metrics"][0]["code_revision"] = {"path": "eval.csv", "sha256": "ab" * 32}
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_metric_spec(spec, require_draft=True)
        self.assertEqual(caught.exception.code, "revision_path_refused")


class RecordContractTests(unittest.TestCase):
    def test_main_fixture_covers_conditions_seeds_chunks_and_denominators(self):
        metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        rows = gep1.validate_records(records)
        self.assertEqual(metadata["chunk_id_namespace"], gep1.SYNTHETIC_CHUNK_NAMESPACE)
        self.assertEqual(sorted({row["condition"] for row in rows}), ["B0", "B1", "B2", "D1"])
        b0 = [row for row in rows if row["condition"] == "B0"]
        self.assertTrue(all(row["requested_length"] is None for row in b0))
        self.assertTrue(all(row["nominal_max_seq_len"] == 37 for row in b0))
        self.assertTrue(all(row["length_regime"] == "historical_37nt" for row in b0))
        self.assertTrue(all(row["generation_seed"] is None and row["training_seed"] is None for row in b0))
        self.assertEqual(sorted({row["historical_generation_seed"] for row in b0}), [96001, 96002])
        valid_b0 = [row for row in b0 if gep1._row_is_valid(row)]
        self.assertTrue(valid_b0)
        self.assertTrue(all(row["observed_length"] == 36 for row in valid_b0))
        self.assertEqual(sorted({row["empirical_null_seed"] for row in rows if row["condition"] == "B2"}), [77001])
        self.assertEqual(sorted({row["training_seed"] for row in rows if row["condition"] == "D1"}), [91001, 91002])
        structure = gep1.matched_schedule_structure(rows)
        self.assertEqual(structure["matched_invocation_indexes"], [1])
        self.assertEqual(structure["b1_only_invocation_indexes"], [2])
        self.assertEqual(structure["d1_only_invocation_indexes"], [3])
        self.assertEqual(structure["incompatible_invocation_indexes"], [])
        self.assertFalse(structure["generation_chunk_label_is_sufficient_evidence"])
        self.assertFalse(structure["b0_in_matched_b1_d1_controlled_comparison"])
        self.assertFalse(structure["production_schedule_wired"])
        self.assertTrue(all(block["included_in_controlled_comparison"] is False for block in structure["b1_only_schedule_blocks"]))
        self.assertTrue(all(block["included_in_controlled_comparison"] is False for block in structure["d1_only_schedule_blocks"]))
        self.assertTrue(all(block["is_training_replicate"] is False for block in structure["matched_schedule_blocks"]))
        b1 = gep1._accounting([row for row in rows if row["condition"] == "B1"], "B1")
        self.assertEqual(b1["attempted"], 5)
        self.assertEqual(b1["parsed_status_true"], 4)
        self.assertEqual(b1["valid_acgu"], 3)
        self.assertEqual(b1["unique_valid"], 2)
        self.assertEqual(b1["exact_length_hits"], 2)
        self.assertEqual(b1["exact_hit_rate_denominator"], "attempted_rows")
        b0_counts = gep1._accounting(b0, "B0")
        self.assertGreater(b0_counts["valid_acgu"], b0_counts["unique_valid"])
        self.assertEqual(b0_counts["exact_hit_applicability"], "not_applicable")
        self.assertIsNone(b0_counts["exact_hit_rate"])
        self.assertEqual(b0_counts["nominal_max_seq_len"], 37)
        self.assertEqual(b0_counts["observed_cleaned_lengths"], [36])
        self.assertEqual(b0_counts["requested_length"], "unavailable")
        self.assertTrue(any(row["parsed_status"] is False for row in rows))
        self.assertTrue(any(row["alphabet_valid"] is False and row["parsed_status"] is True for row in rows))
        self.assertTrue(any(row["observed_length"] != row["requested_length"] for row in rows if gep1._row_is_valid(row)))

    def test_duplicate_record_ids_are_rejected(self):
        _metadata, records = fixture("synthetic_duplicate_record_ids.json")
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_records(records)
        self.assertIn("duplicate_record_id", codes(caught.exception))

    def test_unknown_condition_and_generic_seed_are_rejected(self):
        _metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        unknown = copy.deepcopy(records[0])
        unknown["record_id"] = "unknown-condition"
        unknown["condition"] = "B3"
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_records([unknown])
        self.assertIn("unknown_condition", codes(caught.exception))
        generic = copy.deepcopy(records[0])
        generic["record_id"] = "generic-seed"
        generic["seed"] = 1
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_records([generic])
        self.assertIn("ambiguous_seed_field", codes(caught.exception))

    def test_forbidden_seed_roles_are_rejected(self):
        _metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        b0 = copy.deepcopy(next(row for row in records if row["record_id"] == "b0-valid-36"))
        b0["training_seed"] = 1
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_records([b0])
        self.assertIn("b0_seed_forbidden", codes(caught.exception))
        b1 = copy.deepcopy(next(row for row in records if row["record_id"] == "b1-exact-chunk-m1"))
        b1["training_seed"] = 91001
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_records([b1])
        self.assertIn("b1_training_seed_forbidden", codes(caught.exception))
        b2 = [copy.deepcopy(row) for row in records if row["condition"] == "B2"]
        extra = copy.deepcopy(b2[0])
        extra["record_id"] = "b2-second-seed"
        extra["empirical_null_seed"] = 77002
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_records(b2 + [extra])
        self.assertIn("b2_multiple_seeds", codes(caught.exception))
        d1 = copy.deepcopy(next(row for row in records if row["record_id"] == "d1-seed-a-chunk-m1"))
        d1["length_condition_seed"] = 88111
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_records([d1])
        self.assertIn("d1_seed_role_invalid", codes(caught.exception))

    def test_reorder_does_not_change_the_preflight(self):
        metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        forward = gep1.run_preflight(records, metadata=metadata)
        backward = gep1.run_preflight(list(reversed(records)), metadata=metadata)
        self.assertEqual(forward, backward)

    def test_m4_projection_matches_exact_hit_accounting(self):
        metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        report = gep1.run_preflight(records, metadata=metadata)
        self.assertEqual(report["m4_reconciliation"]["status"], "matched")
        self.assertTrue(report["m4_reconciliation"]["rates_equal"])
        self.assertGreater(report["m4_reconciliation"]["m4_parsed_outputs"], report["m4_reconciliation"]["contract_parsed_status_true"])
        metrics = gep1._load_module("m4_diagnostic_metrics.py", "gep1_test_guardrail")
        rows = gep1.validate_records(records)
        projected = []
        for row in sorted(rows, key=lambda item: item["record_id"]):
            attempt = gep1.project_m4_attempt(row, len(projected))
            if attempt is not None:
                projected.append(attempt)
        evaluation = metrics.evaluate_hard_guardrails(projected, set())
        self.assertEqual([item["id"] for item in evaluation["decisions"]], list(metrics.HARD_GUARDRAIL_IDS))
        self.assertEqual(evaluation["exact_train_matches"], 0)
        self.assertFalse(evaluation["exact_hit_rate_is_an_eligibility_threshold"])


class ReplicateSemanticsTests(unittest.TestCase):
    def test_forbidden_pseudo_replication_is_explicit(self):
        _metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        claims = [
            (
                {"kind": "matched_b1_d1_controlled_comparison", "include_conditions": ["B0", "B1", "D1"]},
                "b0_forbidden_in_matched_b1_d1_controlled_comparison",
            ),
            (
                {"kind": "matched_b1_d1_controlled_comparison", "include_conditions": ["B1", "B2", "D1"]},
                "b2_forbidden_in_matched_b1_d1_controlled_comparison",
            ),
            (
                {"kind": "training_replicate_summary", "condition": "B0", "unit": "historical_generation_seed"},
                "b0_unit_is_not_a_training_replicate",
            ),
            (
                {"kind": "training_replicate_summary", "condition": "B0", "unit": "historical_batch_index"},
                "b0_unit_is_not_a_training_replicate",
            ),
            ({"kind": "training_replicate_summary", "condition": "B2"}, "b2_rows_are_not_training_replicates"),
            (
                {"kind": "training_replicate_summary", "condition": "B1", "seed_role": "length_condition_seed"},
                "b1_length_condition_seed_is_not_a_training_replicate",
            ),
            ({"kind": "training_replicate_summary", "condition": "D1", "unit": "record_id"}, "d1_unit_is_not_a_training_replicate"),
            (
                {"kind": "training_replicate_summary", "condition": "D1", "unit": "generation_chunk_id"},
                "d1_unit_is_not_a_training_replicate",
            ),
        ]
        for claim, code in claims:
            with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
                gep1.assess_claim(records, claim)
            self.assertEqual(caught.exception.code, code)

    def test_matched_controlled_comparison_uses_the_schedule_not_the_chunk_label(self):
        _metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        claim = {"kind": "matched_b1_d1_controlled_comparison", "include_conditions": ["B1", "D1"]}
        structure = gep1.assess_claim(records, claim)
        self.assertEqual(structure["matched_invocation_indexes"], [1])
        self.assertEqual(structure["b1_only_invocation_indexes"], [2])
        self.assertEqual(structure["d1_only_invocation_indexes"], [3])
        self.assertEqual(structure["incompatible_schedule_blocks"], [])
        self.assertFalse(structure["schedule_blocks_are_training_replicates"])
        self.assertFalse(structure["candidate_rows_are_training_replicates"])
        self.assertFalse(structure["production_schedule_wired"])
        self.assertFalse(any(block["included_in_controlled_comparison"] for block in structure["b1_only_schedule_blocks"]))
        self.assertFalse(any(block["included_in_controlled_comparison"] for block in structure["d1_only_schedule_blocks"]))
        relabelled = []
        for record in records:
            row = copy.deepcopy(record)
            if row["condition"] == "D1" and row["invocation_index"] == 1:
                row["generation_chunk_id"] = "chunk-relabelled"
            if row["record_id"] == "b1-duplicate-length-control":
                row["generation_chunk_id"] = "chunk-m1"
            relabelled.append(row)
        relabelled_structure = gep1.assess_claim(relabelled, claim)
        self.assertEqual(relabelled_structure["matched_invocation_indexes"], [1])
        self.assertEqual(relabelled_structure["b1_only_invocation_indexes"], [2])
        self.assertIn("chunk-m1", relabelled_structure["b1_only_schedule_blocks"][0]["generation_chunk_ids"])
        self.assertNotIn(2, relabelled_structure["matched_invocation_indexes"])

    def test_reused_chunk_label_with_a_different_generation_seed_fails(self):
        metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        changed = []
        for record in records:
            row = copy.deepcopy(record)
            if row["condition"] == "D1" and row["invocation_index"] == 1:
                self.assertEqual(row["generation_chunk_id"], "chunk-m1")
                row["length_schedule_provenance"] = copy.deepcopy(row["length_schedule_provenance"])
                row["length_schedule_provenance"]["generation_seed_base"] = 88010
                row["invocation_seed"] = 88011
                row["generation_seed"] = 88011
            changed.append(row)
        self.assertTrue(any(row["generation_chunk_id"] == "chunk-m1" and row["condition"] == "B1" for row in changed))
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.assess_claim(changed, {"kind": "matched_b1_d1_controlled_comparison", "include_conditions": ["B1", "D1"]})
        self.assertEqual(caught.exception.code, "matched_schedule_incompatible")
        self.assertIn("invocation_seed", caught.exception.detail)
        self.assertNotIn("requested_length_position_schedule", caught.exception.detail)
        report = gep1.run_preflight(changed, metadata=metadata)
        self.assertEqual(report["status"], "failed")
        self.assertIn("matched_schedule_incompatible", [item["code"] for item in report["errors"]])
        self.assertNotIn(1, report["matched_b1_d1_schedule"]["matched_invocation_indexes"])
        self.assertEqual(report["matched_b1_d1_schedule"]["incompatible_invocation_indexes"], [1])
        self.assertNotEqual(gep1.preflight_exit_code(report), 0)

    def test_reused_chunk_label_with_a_different_length_position_schedule_fails(self):
        metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        changed = []
        for record in records:
            row = copy.deepcopy(record)
            if row["condition"] == "D1" and row["invocation_index"] == 1:
                self.assertEqual(row["generation_chunk_id"], "chunk-m1")
                self.assertEqual(row["invocation_seed"], 88001)
                row["requested_length"] = 24
                row["requested_target_length"] = 24
                row["max_seq_len"] = 25
                row["batch_position"] = row["batch_position"] + 1
            changed.append(row)
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.assess_claim(changed, {"kind": "matched_b1_d1_controlled_comparison"})
        self.assertEqual(caught.exception.code, "matched_schedule_incompatible")
        self.assertIn("requested_length_position_schedule", caught.exception.detail)
        self.assertNotIn("invocation_seed", caught.exception.detail)
        report = gep1.run_preflight(changed, metadata=metadata)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["matched_b1_d1_schedule"]["incompatible_invocation_indexes"], [1])
        self.assertEqual(report["matched_b1_d1_schedule"]["matched_invocation_indexes"], [])
        self.assertEqual(report["matched_b1_d1_schedule"]["b1_only_invocation_indexes"], [2])
        self.assertEqual(report["matched_b1_d1_schedule"]["d1_only_invocation_indexes"], [3])

    def test_one_d1_seed_states_the_uncertainty_limit(self):
        metadata, records = fixture("synthetic_one_d1_seed.json")
        summary = gep1.assess_claim(records, {"kind": "training_replicate_summary", "condition": "D1", "unit": "training_seed"})
        self.assertEqual(summary["d1_training_seed_count"], 1)
        self.assertEqual(summary["d1_row_count"], 2)
        self.assertTrue(summary["one_d1_training_seed_limitation"])
        self.assertTrue(summary["uncertainty_excludes_training_run_variability"])
        self.assertEqual(summary["statement"], "Uncertainty excludes training-run variability.")
        report = gep1.run_preflight(records, metadata=metadata)
        self.assertEqual(report["status"], "passed_with_limitations")
        self.assertTrue(report["one_d1_training_seed_limitation"])
        self.assertEqual(report["one_d1_training_seed_limitation_statement"], "Uncertainty excludes training-run variability.")
        self.assertEqual(report["seed_structure"]["b2_empirical_null_seeds"], [77001])
        self.assertTrue(report["b0_external_comparator"])
        self.assertFalse(report["b0_included_in_matched_b1_d1_controlled_comparison"])
        self.assertEqual(report["b0_nominal_max_seq_len"], 37)
        self.assertEqual(report["b0_exact_hit_applicability"], "not_applicable")
        self.assertEqual(report["b0_observed_cleaned_lengths"], [36])
        self.assertFalse(report["b0_historical_generation_seeds_are_training_replicates"])

    def test_missing_d1_training_seed_fails_the_summary(self):
        metadata, records = fixture("synthetic_missing_d1_training_seed.json")
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.assess_claim(records, {"kind": "training_replicate_summary", "condition": "D1", "unit": "training_seed"})
        self.assertEqual(caught.exception.code, "d1_training_seed_provenance_missing")
        report = gep1.run_preflight(records, metadata=metadata)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["d1_training_seed_summary"]["status"], "failed")
        self.assertEqual(report["d1_training_seed_summary"]["code"], "d1_training_seed_provenance_missing")
        self.assertFalse(report["d1_training_seed_summary"]["usable_training_seed_summary"])
        self.assertNotIn("d1_training_seed_count", report["d1_training_seed_summary"])
        self.assertNotIn("statement", report["d1_training_seed_summary"])
        self.assertEqual(report["errors"][0]["code"], "d1_training_seed_provenance_missing")
        self.assertNotEqual(gep1.preflight_exit_code(report), 0)
        self.assertNotEqual(report["status"], "passed_with_limitations")

    def test_two_d1_seeds_do_not_claim_a_confidence_interval(self):
        _metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        summary = gep1.assess_claim(records, {"kind": "training_replicate_summary", "condition": "D1", "unit": "training_seed"})
        self.assertEqual(summary["d1_training_seeds"], [91001, 91002])
        self.assertFalse(summary["one_d1_training_seed_limitation"])
        self.assertFalse(summary["uncertainty_excludes_training_run_variability"])
        self.assertNotIn("confidence interval is computed", summary["statement"])
        self.assertIn("does not compute a confidence interval", summary["statement"])


class EvalGateTests(unittest.TestCase):
    def binding(self):
        digest = "a" * 64
        return {
            "corrected_role_hashes": {role: digest for role in gep1.ROLE_HASH_KEYS},
            "m9a_artefact_references": ["synthetic-m9a-not-a-real-artefact"],
            "m9b_artefact_references": ["synthetic-m9b-not-a-real-artefact"],
            "m9c_code_configuration_hashes": {"synthetic-code": "b" * 64},
            "frozen_plan_identifier": "synthetic-plan-not-the-frozen-record",
        }

    def unlock(self, **changes):
        record = {
            "timestamp": "2026-10-07T00:00:00+00:00",
            "operator": "synthetic-operator",
            "reviewer": "synthetic-reviewer",
            "unlock_assertion": True,
        }
        record.update(self.binding())
        record.update(changes)
        return record

    def assert_refused(self, code, **kwargs):
        opener = kwargs.pop("opener", None)
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.evaluate_eval_gate(opener=opener, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(getattr(opener, "calls", 0), 0)
        return caught.exception

    def test_default_mode_refuses_eval_without_opening(self):
        opener = Opener()
        self.assertEqual(gep1.DEFAULT_MODE, "synthetic_preflight")
        error = self.assert_refused(
            "eval_requires_frozen_unlocked_mode",
            declared_role="EVAL",
            filename="synthetic_panel.json",
            opener=opener,
        )
        self.assertIn("eval_requires_frozen_unlocked_mode", codes(error))

    def test_eval_unlock_absences_are_refused(self):
        expected = self.binding()
        self.assert_refused(
            "unlock_record_absent",
            declared_role="EVAL",
            mode="frozen_unlocked",
            unlock_record=None,
            expected_binding=expected,
            filename="synthetic_panel.json",
            opener=Opener(),
        )
        incomplete = self.unlock()
        del incomplete["reviewer"]
        self.assert_refused(
            "unlock_record_incomplete",
            declared_role="EVAL",
            mode="frozen_unlocked",
            unlock_record=incomplete,
            expected_binding=expected,
            filename="synthetic_panel.json",
            opener=Opener(),
        )
        false_record = self.unlock(unlock_assertion=False)
        self.assert_refused(
            "unlock_assertion_false",
            declared_role="EVAL",
            mode="frozen_unlocked",
            unlock_record=false_record,
            expected_binding=expected,
            filename="synthetic_panel.json",
            opener=Opener(),
        )
        mismatched = self.unlock()
        mismatched["corrected_role_hashes"] = dict(mismatched["corrected_role_hashes"])
        mismatched["corrected_role_hashes"]["EVAL"] = "c" * 64
        self.assert_refused(
            "unlock_record_mismatched",
            declared_role="EVAL",
            mode="frozen_unlocked",
            unlock_record=mismatched,
            expected_binding=expected,
            filename="synthetic_panel.json",
            opener=Opener(),
        )

    def test_complete_matching_unlock_still_does_not_open_eval(self):
        self.assert_refused(
            "eval_load_not_wired_in_gep1",
            declared_role="EVAL",
            mode="frozen_unlocked",
            unlock_record=self.unlock(),
            expected_binding=self.binding(),
            filename="synthetic_panel.json",
            opener=Opener(),
        )

    def test_filename_guard_is_additional_to_the_role_check(self):
        self.assert_refused(
            "filename_guard",
            declared_role="SYNTHETIC",
            filename="nested/eval.csv",
            opener=Opener(),
        )
        error = self.assert_refused(
            "unlock_record_absent",
            declared_role="EVAL",
            mode="frozen_unlocked",
            filename="eval.csv",
            opener=Opener(),
        )
        self.assertIn("filename_guard", codes(error))
        self.assertIn("unlock_record_absent", codes(error))
        self.assert_refused("data_role_refused", declared_role="REF", filename="synthetic_panel.json", opener=Opener())
        self.assert_refused("data_role_refused", declared_role="VALIDATION", filename="synthetic_panel.json", opener=Opener())

    def test_fixture_loader_stays_inside_the_synthetic_directory(self):
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.load_synthetic_fixture(os.path.join(gep1.fixture_root(), "eval.csv"))
        self.assertEqual(caught.exception.code, "filename_guard")
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.load_synthetic_fixture(os.path.join(ROOT, "README.md"))
        self.assertEqual(caught.exception.code, "fixture_path_refused")


class PreflightReportTests(unittest.TestCase):
    def test_main_preflight_reports_structure_without_sequences(self):
        metadata, records = fixture("synthetic_four_condition_two_d1_seeds.json")
        report = gep1.run_preflight(records, metadata=metadata)
        text = gep1.render_preflight_text(report)
        encoded = json.dumps(report)
        for record in records:
            if record["sequence"]:
                self.assertNotIn(record["sequence"], encoded)
                self.assertNotIn(record["sequence"], text)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["synthetic_input_counts_by_condition"], {"B0": 4, "B1": 5, "B2": 4, "D1": 5})
        self.assertEqual(report["seed_structure"]["d1_training_seeds_present"], [91001, 91002])
        self.assertEqual(report["seed_structure"]["b2_empirical_null_seeds"], [77001])
        self.assertFalse(report["seed_structure"]["b2_rows_are_training_replicates"])
        self.assertFalse(report["seed_structure"]["b1_length_condition_seeds_are_training_replicates"])
        self.assertEqual(report["seed_structure"]["b1_length_condition_seeds"], [88111])
        self.assertTrue(report["b0_external_comparator"])
        self.assertEqual(report["b0_length_regime"], "historical_37nt")
        self.assertEqual(report["b0_nominal_max_seq_len"], 37)
        self.assertEqual(report["b0_requested_length_status"], "unavailable")
        self.assertEqual(report["b0_exact_hit_applicability"], "not_applicable")
        self.assertEqual(report["b0_observed_cleaned_lengths"], [36])
        provenance = report["seed_structure"]["b0_historical_generation_provenance"]
        self.assertEqual(provenance["historical_generation_seeds"], [96001, 96002])
        self.assertFalse(provenance["historical_generation_seeds_are_training_replicates"])
        self.assertFalse(provenance["historical_batches_are_training_replicates"])
        self.assertFalse(provenance["candidate_rows_are_training_replicates"])
        self.assertFalse(report["b0_included_in_matched_b1_d1_controlled_comparison"])
        self.assertEqual(report["matched_b1_d1_schedule"]["matched_invocation_indexes"], [1])
        self.assertNotIn(2, report["matched_b1_d1_schedule"]["matched_invocation_indexes"])
        self.assertNotIn(3, report["matched_b1_d1_schedule"]["matched_invocation_indexes"])
        self.assertFalse(report["one_d1_training_seed_limitation"])
        self.assertTrue(report["no_eval_data_loaded"])
        self.assertEqual(report["no_eval_statement"], "No EVAL data were loaded.")
        self.assertIn("No EVAL data were loaded.", text)
        self.assertFalse(report["train_reference_loaded"])
        self.assertFalse(report["structure_metrics_executed"])
        self.assertFalse(report["production_pools_loaded"])
        self.assertFalse(report["aggregate_generator_quality_score"])
        self.assertTrue(report["package_revision"]["git_head"])
        self.assertIn("eval_closeness_not_implemented", text)

    def test_empty_and_all_invalid_subsets_do_not_crash(self):
        empty_meta, empty_records = fixture("synthetic_empty.json")
        empty = gep1.run_preflight(empty_records, metadata=empty_meta)
        self.assertEqual(empty["accounting_overall"]["attempted"], 0)
        self.assertEqual(empty["accounting_overall"]["exact_hit_rate"], 0.0)
        self.assertEqual(empty["status"], "passed_with_limitations")
        self.assertFalse(empty["one_d1_training_seed_limitation"])
        self.assertFalse(empty["b0_external_comparator"])
        self.assertIsNone(empty["seed_structure"]["b0_historical_generation_provenance"])
        self.assertEqual(empty["errors"], [])
        invalid_meta, invalid_records = fixture("synthetic_all_invalid.json")
        invalid = gep1.run_preflight(invalid_records, metadata=invalid_meta)
        self.assertEqual(invalid["accounting_overall"]["valid_acgu"], 0)
        self.assertEqual(invalid["accounting_overall"]["unique_valid"], 0)
        self.assertEqual(invalid["accounting_overall"]["exact_length_hits"], 0)
        self.assertGreater(invalid["accounting_overall"]["attempted"], 0)
        self.assertEqual(invalid["status"], "passed_with_limitations")
        self.assertEqual(invalid["errors"], [])
        self.assertEqual(invalid["accounting_by_condition"]["B0"]["exact_hit_applicability"], "not_applicable")
        self.assertEqual(invalid["seed_structure"]["d1_training_seeds_present"], [91001, 91002])

    def test_cli_rejects_paths_and_prints_the_synthetic_preflight(self):
        self.assertEqual(gep1.main(["eval.csv"]), 2)
        self.assertEqual(gep1.main([]), 0)


class Opener:
    calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("opener was called")


if __name__ == "__main__":
    unittest.main()

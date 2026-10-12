"""CPU/mock tests for the inactive M7 final-selection stage.

The selection stage reads sealed manifest bytes only. These tests build those
manifests from two real CPU mock replicate runs. No biological corpus, weight,
checkpoint, accepted run directory, or GPU is touched.
"""

from __future__ import annotations

import copy
import itertools
import json
import os
import subprocess
import sys
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import importlib.util

ROOT = "/home/laura/rnagenesis-aptamer-mres"
SUPPORT_PATH = os.path.join(ROOT, "tests/modelling/m7_support.py")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


support = load_module("m7_support_for_selection_tests", SUPPORT_PATH)
selection = support.selection
guardrails = support.guardrails
contract = support.contract
common = support.common
M7Error = common.M7Error

MSE_A = {1: 0.50, 2: 0.40, 3: 0.20, 4: 0.30, 5: 0.25}      # ranking 3, 5, 4, 2, 1
MSE_B = {1: 0.45, 2: 0.35, 3: 0.33, 4: 0.20, 5: 0.40}      # ranking 4, 3, 2, 5, 1
MSE_TIE = {1: 0.30, 2: 0.30, 3: 0.20, 4: 0.20, 5: 0.40}    # ranking 3, 4, 1, 2, 5 (earlier epoch wins ties)


def tearDownModule():
    support.cleanup_cache()


def build(seed43, seed44=None, deviation=None):
    """Run the final stage over (replicate blob, guardrail blobs) pairs."""
    replicates = [seed43[0]] + ([seed44[0]] if seed44 is not None else [])
    guardrail_blobs = list(seed43[1]) + (list(seed44[1]) if seed44 is not None else [])
    return selection.build_final_selection(replicates, guardrail_blobs, deviation)


def two_seed_scenario():
    return support.scenario(43, MSE_A, [False, True]), support.scenario(44, MSE_B, [True])


class ConfigurationTests(unittest.TestCase):
    def test_configuration_is_inactive_and_the_entry_point_is_closed(self):
        with open(os.path.join(ROOT, "config/experiments/D1_final_selection.yaml"), "rb") as handle:
            raw = handle.read()
        config = common.load_config_bytes(raw)
        self.assertTrue(contract.assert_inactive_text(raw.decode("utf-8")))
        self.assertTrue(selection.assert_inactive_configuration(config))
        with self.assertRaises(M7Error) as caught:
            selection.reject_inactive_before_execution(config)
        self.assertEqual(caught.exception.code, "execution_not_authorised")
        for mutate in (
            lambda c: c.update(consumable_by_executable_workflow=True),
            lambda c: c["execution"].update(authorised=True),
            lambda c: c["allowed_seed_plan"].update(target_seeds=[42, 43]),
            lambda c: c["selection_rules"].update(select_first_passing_candidate_of_the_sealed_ranking=False),
            lambda c: c["m8_boundary"].update(two_seed_attempts_each=10000),
            lambda c: c["final_manifest"]["closure"].update(m7_complete=True),
        ):
            changed = copy.deepcopy(config)
            mutate(changed)
            with self.assertRaises(M7Error):
                selection.assert_inactive_configuration(changed)
        path = os.path.join(ROOT, "scripts/modelling/m7_selection.py")
        for arguments, ok in ((["--help"], True), (["--schema"], True), ([], False), (["--manifest", "/x"], False), (["--seed", "43"], False)):
            completed = subprocess.run([sys.executable, "-B", path] + arguments, capture_output=True, text=True, cwd="/tmp")
            self.assertEqual(completed.returncode == 0, ok, arguments)


class SelectionTests(unittest.TestCase):
    def test_two_seeds_select_the_first_passing_candidate_of_each_sealed_ranking(self):
        manifest = build(*two_seed_scenario())
        self.assertEqual(manifest["selection_outcome"], "selected_set_complete")
        self.assertEqual(manifest["completed_seeds"], [43, 44])
        by_seed = {item["seed"]: item for item in manifest["selected_set"]}
        self.assertEqual(by_seed[43]["epoch"], 5)   # ranking 3 (failed), 5 (passed)
        self.assertEqual(by_seed[44]["epoch"], 4)   # ranking 4 (passed)
        self.assertEqual(by_seed[43]["update"], 105)
        self.assertEqual(manifest["selected_set_sha256"], selection.selected_set_sha256(manifest["selected_set"]))
        self.assertEqual([item["seed"] for item in manifest["selected_set"]], [43, 44])
        for item in manifest["selected_set"]:
            self.assertEqual(item["members_sha256"][common.WEIGHT_MEMBER], item["weight_sha256"])
            self.assertNotIn(item["weight_sha256"], common.M6_FORBIDDEN_WEIGHT_SHA256)
        self.assertTrue(selection.validate_final_selection_manifest(manifest))

    def test_final_manifest_binds_everything_and_stays_gated(self):
        first, second = two_seed_scenario()
        manifest = build(first, second)
        self.assertIs(manifest["closure"]["human_gate_required"], True)
        self.assertIs(manifest["closure"]["m7_complete"], False)
        self.assertEqual(manifest["ref_eval_access"], {"eval_opened": False, "ref_opened": False})
        self.assertIs(manifest["closure"]["ref_opened"] or manifest["closure"]["eval_opened"], False)
        self.assertEqual(manifest["allowed_seed_plan"]["target_seeds"], [43, 44])
        self.assertEqual(manifest["allowed_seed_plan"]["excluded_seeds"], [42])
        self.assertIsNone(manifest["deviation"])
        self.assertEqual(
            manifest["replicate_manifests"],
            [{"seed": 43, "sha256": common.sha256_bytes(first[0])}, {"seed": 44, "sha256": common.sha256_bytes(second[0])}],
        )
        self.assertEqual(len(manifest["guardrail_manifests"]), 3)
        self.assertEqual(
            sorted(item["sha256"] for item in manifest["guardrail_manifests"]),
            sorted(common.sha256_bytes(blob) for blob in first[1] + second[1]),
        )
        self.assertEqual([(row["seed"], row["epoch"]) for row in manifest["candidate_table"]], [(s, e) for s in (43, 44) for e in range(1, 6)])
        self.assertEqual(len(manifest["candidate_table"]), 10)
        self.assertEqual({item["seed"]: item["ranked_epochs"] for item in manifest["validation_rankings"]}, {43: [3, 5, 4, 2, 1], 44: [4, 3, 2, 5, 1]})
        trace = {item["seed"]: item["trace"] for item in manifest["lazy_evaluation_traces"]}
        self.assertEqual([(item["rank"], item["epoch"], item["evaluated"], item["outcome"]) for item in trace[43]][:3], [(1, 3, True, "failed"), (2, 5, True, "passed"), (3, 4, False, "not_evaluated_lazy_stop_after_first_passing_candidate")])
        self.assertEqual([item["evaluated"] for item in trace[44]], [True, False, False, False, False])
        self.assertEqual(manifest["m8_allocation"], {"43": 15000, "44": 15000})
        self.assertEqual(manifest["m8_boundary"]["total_raw_d1_attempts"], 30000)
        self.assertIs(manifest["m8_boundary"]["implemented_in_this_package"], False)
        self.assertIs(manifest["closure"]["m8_generation_performed"], False)
        self.assertEqual(manifest["config_version"], selection.SCHEMA_VERSION)
        for row in manifest["candidate_table"]:
            self.assertEqual(row["update"], contract.epoch_update_range(row["epoch"])[1])
            self.assertGreaterEqual(row["rank"], 1)

    def test_canonical_bytes_do_not_depend_on_input_order(self):
        (rep43, g43, _m43), (rep44, g44, _m44) = two_seed_scenario()
        g43 = list(g43)
        reference = selection.final_selection_bytes(selection.build_final_selection([rep43, rep44], g43 + list(g44)))
        for replicates in itertools.permutations([rep43, rep44]):
            for guardrail_blobs in itertools.permutations(g43 + list(g44)):
                observed = selection.final_selection_bytes(selection.build_final_selection(list(replicates), list(guardrail_blobs)))
                self.assertEqual(observed, reference)
        self.assertEqual(common.canonical_json(json.loads(reference.decode("utf-8"))), reference)
        self.assertEqual(common.sha256_bytes(reference), common.sha256_bytes(selection.final_selection_bytes(build((rep43, g43, None), (rep44, g44, None)))))

    def test_fallback_selects_the_next_ranked_candidate_after_a_failure(self):
        scenario = support.scenario(43, MSE_A, [False, False, True])
        deviation = support.deviation_blob(scenario[0], scenario[2])
        manifest = build(scenario, None, deviation)
        self.assertEqual(manifest["selected_set"][0]["epoch"], 4)   # ranking 3, 5 failed; 4 passed
        trace = manifest["lazy_evaluation_traces"][0]["trace"]
        self.assertEqual([item["outcome"] for item in trace], ["failed", "failed", "passed", "not_evaluated_lazy_stop_after_first_passing_candidate", "not_evaluated_lazy_stop_after_first_passing_candidate"])
        self.assertEqual(manifest["seed_records"][0]["status"], "selected")

    def test_exact_validation_tie_goes_to_the_earlier_epoch(self):
        scenario = support.scenario(43, MSE_TIE, [True])
        deviation = support.deviation_blob(scenario[0], scenario[2])
        manifest = build(scenario, None, deviation)
        self.assertEqual(manifest["validation_rankings"][0]["ranked_epochs"], [3, 4, 1, 2, 5])
        self.assertEqual(manifest["selected_set"][0]["epoch"], 3)
        failing_first = support.scenario(43, MSE_TIE, [False, True])
        again = build(failing_first, None, support.deviation_blob(failing_first[0], failing_first[2]))
        self.assertEqual(again["selected_set"][0]["epoch"], 4)
        later = support.scenario(43, MSE_TIE, [False, False, True])
        third = build(later, None, support.deviation_blob(later[0], later[2]))
        self.assertEqual(third["selected_set"][0]["epoch"], 1)

    def test_no_eligible_checkpoint_is_recorded_without_any_automatic_change(self):
        none = support.scenario(43, MSE_A, [False] * 5)
        passing = support.scenario(44, MSE_B, [True])
        manifest = build(none, passing)
        self.assertEqual(manifest["selection_outcome"], "no_eligible_checkpoint")
        self.assertIsNone(manifest["selected_set"])
        self.assertIsNone(manifest["selected_set_sha256"])
        statuses = {item["seed"]: item["status"] for item in manifest["seed_records"]}
        self.assertEqual(statuses, {43: "no_eligible_checkpoint", 44: "selected"})
        self.assertTrue(all(item["evaluated"] for item in manifest["lazy_evaluation_traces"][0]["trace"]))
        self.assertIs(manifest["closure"]["human_gate_required"], True)
        self.assertIs(manifest["closure"]["m7_complete"], False)
        self.assertTrue(selection.validate_final_selection_manifest(manifest))
        for key in ("learning_rate", "threshold", "architecture", "seed_change"):
            self.assertNotIn(key, json.dumps(manifest))

    def test_one_seed_requires_the_sealed_operational_deviation(self):
        scenario = support.scenario(43, MSE_A, [True])
        with self.assertRaises(M7Error) as caught:
            build(scenario)
        self.assertIn("deviation", caught.exception.detail)
        deviation = support.deviation_blob(scenario[0], scenario[2])
        manifest = build(scenario, None, deviation)
        self.assertEqual(manifest["completed_seeds"], [43])
        self.assertEqual(manifest["deviation"]["omitted_seed"], 44)
        self.assertEqual(manifest["m8_allocation"], {"43": 30000})
        self.assertEqual([item["seed"] for item in manifest["selected_set"]], [43])
        self.assertTrue(selection.validate_final_selection_manifest(manifest))
        with self.assertRaises(M7Error):
            build(*two_seed_scenario(), deviation)

    def test_seed_44_alone_duplicates_and_unexpected_seeds_are_refused(self):
        alone = support.scenario(44, MSE_B, [True])
        with self.assertRaises(M7Error):
            build(alone)
        with self.assertRaises(M7Error):
            build(alone, None, support.deviation_blob(alone[0], alone[2]))
        one = support.scenario(43, MSE_A, [True])
        with self.assertRaises(M7Error) as caught:
            selection.build_final_selection([one[0], one[0]], list(one[1]))
        self.assertIn("more than one", caught.exception.detail)
        with self.assertRaises(M7Error):
            selection.build_final_selection([], [])
        for seed in (42, 45, 1):
            manifest = copy.deepcopy(support.successful_run(43)["manifest"])
            manifest["seed"] = seed
            manifest["authorisation"]["seed"] = seed
            with self.assertRaises(M7Error) as caught:
                selection.build_final_selection([common.canonical_json(manifest)], [])
            self.assertEqual(caught.exception.code, "unexpected_seed")

    def test_cross_seed_inconsistency_is_refused(self):
        first, second = two_seed_scenario()
        for mutate in (
            lambda m: m["b1_identity"].update(initial_state_aggregate_digest=support.digest("other-b1")),
            lambda m: m["b1_identity"].update(initial_state_parameter_names_sha256=support.digest("other-names")),
            lambda m: m["configuration"]["implementation_file_hashes"].__setitem__(
                sorted(m["configuration"]["implementation_file_hashes"])[0], support.digest("other-implementation")
            ),
        ):
            manifest = copy.deepcopy(json.loads(second[0].decode("utf-8")))
            mutate(manifest)
            with self.assertRaises(M7Error) as caught:
                selection.build_final_selection([first[0], common.canonical_json(manifest)], list(first[1]))
            self.assertEqual(caught.exception.code, "selection_invalid")
        manifest = copy.deepcopy(json.loads(second[0].decode("utf-8")))
        manifest["validation_artifacts"]["noise_sha256"] = support.digest("other-noise")
        with self.assertRaises(M7Error):
            selection.build_final_selection([first[0], common.canonical_json(manifest)], list(first[1]))

    def test_a_replicate_whose_candidates_are_incomplete_is_refused(self):
        first, _second = two_seed_scenario()
        for mutate in (
            lambda m: m["validation_observations"].pop(),
            lambda m: m["checkpoints"].pop(),
            lambda m: m["validation_observations"].append(copy.deepcopy(m["validation_observations"][-1])),
            lambda m: m["validation_ranking"]["ranked_candidates"].append(copy.deepcopy(m["validation_ranking"]["ranked_candidates"][0])),
            lambda m: m["validation_observations"][0].update(candidate=True),
        ):
            manifest = copy.deepcopy(json.loads(first[0].decode("utf-8")))
            mutate(manifest)
            with self.assertRaises(M7Error):
                selection.build_final_selection([common.canonical_json(manifest)], [])

    def test_inputs_must_be_canonical_json_bytes(self):
        first, _second = two_seed_scenario()
        for bad in (first[0].rstrip(b"\n"), first[0] + b" ", json.dumps(json.loads(first[0].decode("utf-8")), indent=1).encode("utf-8"), "text", b"{", b"[]"):
            with self.assertRaises(M7Error):
                selection.build_final_selection([bad], [])


class LazyEvaluationRuleTests(unittest.TestCase):
    def test_non_prefix_evaluation_is_refused(self):
        rep, blobs, manifest = support.scenario(43, MSE_A, [False, False, False])
        deviation = support.deviation_blob(rep, manifest)
        with self.assertRaises(M7Error):
            selection.build_final_selection([rep], [blobs[0], blobs[2]], deviation)
        with self.assertRaises(M7Error):
            selection.build_final_selection([rep], [blobs[1]], deviation)

    def test_evaluating_after_the_first_pass_is_refused(self):
        rep, _blobs, manifest = support.scenario(43, MSE_A, [True])
        order = [item["epoch"] for item in manifest["validation_ranking"]["ranked_candidates"]]
        first = support.guardrail_blob(manifest, rep, order[0], True, 1, [])
        second = support.guardrail_blob(manifest, rep, order[1], True, 2, [{"epoch": order[0], "manifest_sha256": common.sha256_bytes(first), "outcome": "failed"}])
        deviation = support.deviation_blob(rep, manifest)
        with self.assertRaises(M7Error):
            selection.build_final_selection([rep], [first, second], deviation)

    def test_incomplete_lazy_evaluation_cannot_be_selected(self):
        scenario = support.scenario(43, MSE_A, [False, False])
        deviation = support.deviation_blob(scenario[0], scenario[2])
        with self.assertRaises(M7Error) as caught:
            build(scenario, None, deviation)
        self.assertIn("incomplete", caught.exception.detail)
        with self.assertRaises(M7Error):
            selection.build_final_selection([scenario[0]], [], deviation)

    def test_a_guardrail_manifest_must_bind_the_earlier_failed_manifests(self):
        rep, blobs, manifest = support.scenario(43, MSE_A, [False])
        order = [item["epoch"] for item in manifest["validation_ranking"]["ranked_candidates"]]
        deviation = support.deviation_blob(rep, manifest)
        wrong = support.guardrail_blob(manifest, rep, order[1], True, 2, [{"epoch": order[0], "manifest_sha256": support.digest("other"), "outcome": "failed"}])
        with self.assertRaises(M7Error):
            selection.build_final_selection([rep], [blobs[0], wrong], deviation)
        right = support.guardrail_blob(manifest, rep, order[1], True, 2, [{"epoch": order[0], "manifest_sha256": common.sha256_bytes(blobs[0]), "outcome": "failed"}])
        built = selection.build_final_selection([rep], [blobs[0], right], deviation)
        self.assertEqual(built["selected_set"][0]["epoch"], order[1])

    def test_guardrail_manifests_must_match_the_replicate_they_evaluate(self):
        first, second = two_seed_scenario()
        mismatches = (
            lambda m: m["replicate_binding"].update(replicate_manifest_sha256=support.digest("other-replicate")),
            lambda m: m["replicate_binding"].update(validation_ranking_sha256=support.digest("other-ranking")),
            lambda m: m["replicate_binding"].update(validation_mse="0.9"),
            lambda m: m["candidate"].update(ranking_position=3),
        )
        for mutate in mismatches:
            manifest = json.loads(first[1][0].decode("utf-8"))
            mutate(manifest)
            with self.assertRaises(M7Error):
                selection.build_final_selection([first[0], second[0]], [common.canonical_json(manifest)] + list(first[1][1:]) + list(second[1]))
        stranger = support.scenario(44, MSE_B, [True])[1][0]
        deviation = support.deviation_blob(first[0], first[2])
        with self.assertRaises(M7Error):
            selection.build_final_selection([first[0]], list(first[1]) + [stranger], deviation)
        duplicate = [first[1][0], first[1][0]]
        with self.assertRaises(M7Error):
            selection.build_final_selection([first[0]], duplicate, deviation)

    def test_a_different_checkpoint_hash_in_a_guardrail_manifest_is_refused(self):
        first, _second = two_seed_scenario()
        manifest = json.loads(first[1][0].decode("utf-8"))
        manifest["checkpoint"]["members_sha256"][common.WEIGHT_MEMBER] = support.digest("different")
        manifest["checkpoint"]["weight_sha256"] = support.digest("different")
        manifest["checkpoint"]["weights_sha256_before_generation"] = support.digest("different")
        manifest["checkpoint"]["weights_sha256_after_generation"] = support.digest("different")
        manifest["replicate_binding"]["weight_sha256"] = support.digest("different")
        deviation = support.deviation_blob(first[0], first[2])
        with self.assertRaises(M7Error):
            selection.build_final_selection([first[0]], [common.canonical_json(manifest)] + list(first[1][1:]), deviation)


class RefEvalAndUpdateZeroTests(unittest.TestCase):
    def test_ref_or_eval_derived_input_is_refused_everywhere(self):
        first, second = two_seed_scenario()
        for key, value in (("ref_opened", True), ("eval_opened", True)):
            manifest = json.loads(first[0].decode("utf-8"))
            manifest["ref_eval_access"][key] = value
            with self.assertRaises(M7Error) as caught:
                selection.build_final_selection([common.canonical_json(manifest)], [])
            self.assertEqual(caught.exception.code, "ref_or_eval_access")
            guardrail = json.loads(first[1][0].decode("utf-8"))
            guardrail["ref_eval_access"][key] = value
            with self.assertRaises(M7Error) as caught:
                selection.build_final_selection([first[0], second[0]], [common.canonical_json(guardrail)] + list(first[1][1:]) + list(second[1]))
            self.assertEqual(caught.exception.code, "ref_or_eval_access")
        for role in ("REF", "EVAL"):
            guardrail = json.loads(first[1][0].decode("utf-8"))
            guardrail["input_roles"].append(role)
            with self.assertRaises(M7Error):
                selection.build_final_selection([first[0], second[0]], [common.canonical_json(guardrail)] + list(first[1][1:]) + list(second[1]))
        for document in (
            {"a": {"ref_opened": True}},
            {"a": {"eval_opened": True}},
            {"roles": ["TRAIN_TEXT", "EVAL"]},
            {"input_roles": ["ref"]},
            {"ref_path": "/x"},
            {"eval_path": "/x"},
            {"b": {"path": "/x/Eval.CSV"}},
            {"b": {"path": "/x/ref.csv"}},
        ):
            with self.assertRaises(M7Error):
                selection.reject_ref_eval_derived(document, "document")
        self.assertTrue(selection.reject_ref_eval_derived({"ref_opened": False, "eval_opened": False, "path": "/x/data.csv", "ref_path": None}, "document"))

    def test_update_zero_is_never_selectable(self):
        manifest = build(*two_seed_scenario())
        for mutate in (
            lambda m: m["candidate_table"][0].update(epoch=0, update=0),
            lambda m: m["selected_set"][0].update(epoch=0, update=0),
            lambda m: m["seed_records"][0].update(selected_epoch=0),
            lambda m: m["validation_rankings"][0]["ranked_epochs"].insert(0, 0),
        ):
            tampered = copy.deepcopy(manifest)
            mutate(tampered)
            with self.assertRaises(M7Error):
                selection.validate_final_selection_manifest(tampered)
        rep, blobs, replicate_manifest = support.scenario(43, MSE_A, [True])
        zero = json.loads(blobs[0].decode("utf-8"))
        zero["authorisation"]["candidate_epoch"] = 0
        zero["candidate"]["epoch"] = 0
        deviation = support.deviation_blob(rep, replicate_manifest)
        with self.assertRaises(M7Error):
            selection.build_final_selection([rep], [common.canonical_json(zero)], deviation)

    def test_a_failed_or_unevaluated_candidate_cannot_be_selected(self):
        manifest = build(*two_seed_scenario())
        table = {(row["seed"], row["epoch"]): row for row in manifest["candidate_table"]}
        failed_row = table[(43, 3)]
        unevaluated_row = table[(43, 1)]
        for row in (failed_row, unevaluated_row):
            tampered = copy.deepcopy(manifest)
            tampered["selected_set"][0].update(
                {key: row[key] for key in ("epoch", "update", "validation_mse", "weight_sha256", "checkpoint_name")}
            )
            tampered["selected_set_sha256"] = selection.selected_set_sha256(tampered["selected_set"])
            tampered["seed_records"][0]["selected_epoch"] = row["epoch"]
            with self.assertRaises(M7Error):
                selection.validate_final_selection_manifest(tampered)
        tampered = copy.deepcopy(manifest)
        tampered["lazy_evaluation_traces"][0]["trace"][1]["evaluated"] = False
        with self.assertRaises(M7Error):
            selection.validate_final_selection_manifest(tampered)

    def test_final_manifest_tampering_is_refused(self):
        manifest = build(*two_seed_scenario())

        def drop_row(m):
            m["candidate_table"].pop(3)

        def duplicate_row(m):
            m["candidate_table"].append(copy.deepcopy(m["candidate_table"][0]))

        def extra_epoch(m):
            row = copy.deepcopy(m["candidate_table"][0])
            row["epoch"] = 6
            m["candidate_table"].append(row)

        def human_gate(m):
            m["closure"]["human_gate_required"] = False

        def complete(m):
            m["closure"]["m7_complete"] = True

        def hash_drift(m):
            m["selected_set_sha256"] = support.digest("x")

        def ranking_drift(m):
            m["validation_rankings"][0]["ranked_epochs"] = [1, 2, 3, 4, 5]

        def outcome(m):
            m["selection_outcome"] = "no_eligible_checkpoint"

        def wrong_allocation(m):
            m["m8_allocation"] = {"43": 30000}

        def seed_plan(m):
            m["allowed_seed_plan"]["minimum_completed_seeds"] = 2

        def sequence(m):
            m["warnings"] = "ACGUACGUACGU"

        def extra_key(m):
            m["extra"] = 1

        def ref(m):
            m["ref_eval_access"]["ref_opened"] = True

        for mutate in (drop_row, duplicate_row, extra_epoch, human_gate, complete, hash_drift, ranking_drift, outcome, wrong_allocation, seed_plan, sequence, extra_key, ref):
            tampered = copy.deepcopy(manifest)
            mutate(tampered)
            with self.assertRaises(M7Error, msg=mutate.__name__):
                selection.validate_final_selection_manifest(tampered)


class DeviationRecordTests(unittest.TestCase):
    def setUp(self):
        self.rep, _blobs, self.manifest = support.scenario(43, MSE_A, [True])
        self.record = json.loads(support.deviation_blob(self.rep, self.manifest).decode("utf-8"))

    def test_a_sealed_record_is_valid_and_bound_to_seed_43(self):
        self.assertTrue(selection.validate_deviation(self.record, self.manifest, common.sha256_bytes(self.rep)))
        self.assertEqual(self.record["rule"]["hard_target"], "2026-10-08T17:00:00+11:00")
        self.assertEqual(self.record["rule"]["time_factor"], 1.25)
        self.assertEqual(self.record["rule"]["buffer_hours"], 2)
        self.assertIs(self.record["depends_on_scientific_results"], False)

    def test_projection_arithmetic_matches_the_human_rule(self):
        projected = selection.project_completion("2026-10-07T09:00:00+11:00", "3600")
        self.assertEqual(projected.isoformat(), "2026-10-07T12:15:00+11:00")   # 09:00 + 1.25 h + 2 h
        late = selection.project_completion("2026-10-08T15:00:00+11:00", "14400")
        self.assertEqual(late.isoformat(), "2026-10-08T22:00:00+11:00")
        for bad in ("0", "-1", "nan", "x"):
            with self.assertRaises(M7Error):
                selection.project_completion("2026-10-07T09:00:00+11:00", bad)
        with self.assertRaises(M7Error):
            selection.project_completion("2026-10-07 09:00", "10")

    def test_altered_unsealed_or_inconsistent_records_are_refused(self):
        def reseal(record):
            return selection.seal_deviation(record)

        cases = {
            "altered": lambda r: r.update(omitted_seed=43),
            "unsealed": lambda r: r.update(sealed=False),
            "scientific": lambda r: r.update(depends_on_scientific_results=True),
            "m8_started": lambda r: r.update(m8_generation_started=True),
            "after_m8": lambda r: r.update(recorded_before_m8_generation=False),
            "seed": lambda r: r.update(completed_seeds=[43, 44]),
            "kind": lambda r: r.update(kind="other"),
            "rule": lambda r: r["rule"].update(time_factor=1.0),
            "sealer": lambda r: r.update(sealed_by="automation"),
            "early_seal": lambda r: r.update(sealed_at="2026-10-08T10:00:00+11:00"),
            "projection": lambda r: r.update(projected_completion_time="2026-10-08T23:00:00+11:00"),
            "not_exceeding": lambda r: r.update(decision_time="2026-10-07T09:00:00+11:00", sealed_at="2026-10-07T09:30:00+11:00"),
            "measured": lambda r: r.update(measured_seed_43_end_to_end_seconds="99999"),
        }
        for name, mutate in cases.items():
            record = copy.deepcopy(self.record)
            mutate(record)
            if name != "altered":
                record = reseal(record)
            with self.assertRaises(M7Error, msg=name):
                selection.validate_deviation(record, self.manifest, common.sha256_bytes(self.rep))
        with self.assertRaises(M7Error):
            selection.validate_deviation(self.record, self.manifest, support.digest("other-seed-43"))
        with self.assertRaises(M7Error):
            selection.validate_deviation({key: value for key, value in self.record.items() if key != "deviation_sha256"})
        extra = dict(self.record, extra=1)
        with self.assertRaises(M7Error):
            selection.validate_deviation(extra)


class IsolationTests(unittest.TestCase):
    def test_the_replicate_manifest_carries_no_selection_and_nothing_cross_seed(self):
        for seed in (43, 44):
            manifest = support.successful_run(seed)["manifest"]
            text = json.dumps(manifest)
            for fragment in ("selected_set", "no_eligible", "lazy_evaluation", "guardrail_manifest", "selection_outcome", "ensemble"):
                self.assertNotIn(fragment, text)
            self.assertEqual(manifest["closure"]["scope"], "single_seed_training_evidence_only")
            self.assertIs(manifest["closure"]["cross_seed_claim"], False)
            self.assertIs(manifest["closure"]["candidate_diagnostics_performed"], False)
            self.assertEqual(sorted(item["seed"] for item in [manifest]), [seed])
            self.assertEqual([item["epoch"] for item in manifest["validation_ranking"]["ranked_candidates"]].count(0), 0)

    def test_the_selection_module_imports_no_training_stack_and_opens_no_data(self):
        code = (
            "import importlib.util,sys;"
            "spec=importlib.util.spec_from_file_location('s', %r);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
            "bad=[n for n in ('torch','accelerate','diffusers','transformers','numpy') if n in sys.modules];"
            "sys.stderr.write(','.join(bad))"
        ) % os.path.join(ROOT, "scripts/modelling/m7_selection.py")
        completed = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, cwd="/tmp")
        self.assertEqual(completed.stderr, "")


# ------------------------------------------------------------------ the validator re-derives every claim


def at(document, path):
    for key in path:
        document = document[key]
    return document


def put(document, path, value):
    at(document, path[:-1])[path[-1]] = value


BAD_DIGESTS = ("", "xyz", "A" * 64, "0" * 63, "0" * 65, 12, True, ["a" * 64], "g" * 64)


class ValidatorStrictnessTests(unittest.TestCase):
    """Every field that was under-validated in revision 3 is rejected when altered, including after the selected-set hash is recomputed."""

    @classmethod
    def setUpClass(cls):
        cls.two = build(*two_seed_scenario())                       # 43: ranks 3 (failed), 5 (passed); 44: rank 4 (passed)
        scenario = support.scenario(43, MSE_A, [False] * 5)
        cls.none = build(scenario, support.scenario(44, MSE_B, [True]))   # 43: no eligible checkpoint
        one = support.scenario(43, MSE_A, [False, False, True])
        cls.one = build(one, None, support.deviation_blob(one[0], one[2]))

    def refuse(self, mutate, base=None, rehash=True, label=""):
        manifest = copy.deepcopy(self.two if base is None else base)
        mutate(manifest)
        if rehash and isinstance(manifest.get("selected_set"), list):
            try:
                manifest["selected_set_sha256"] = selection.selected_set_sha256(manifest["selected_set"])
            except (TypeError, KeyError, M7Error):
                pass
        with self.assertRaises(M7Error, msg=label or str(mutate)):
            selection.validate_final_selection_manifest(manifest)
        return manifest

    def test_the_untouched_manifests_validate(self):
        for manifest in (self.two, self.none, self.one):
            self.assertTrue(selection.validate_final_selection_manifest(manifest))
        self.assertEqual(self.two["config_version"], "m7-final-selection-config-2")
        self.assertEqual(self.two["manifest_schema_version"], "m7-final-selection-manifest-2")
        for row in self.two["candidate_table"]:
            self.assertEqual(sorted(row["members_sha256"]), sorted(common.CHECKPOINT_MEMBERS))
            self.assertEqual(row["members_sha256"][common.WEIGHT_MEMBER], row["weight_sha256"])

    # -- exact nested key sets

    NESTED = (
        ("replicate index row", ("replicate_manifests", 0)),
        ("guardrail index row", ("guardrail_manifests", 0)),
        ("candidate row", ("candidate_table", 2)),
        ("candidate guardrail block", ("candidate_table", 2, "guardrail")),
        ("unevaluated guardrail block", ("candidate_table", 0, "guardrail")),
        ("candidate members mapping", ("candidate_table", 2, "members_sha256")),
        ("ranking row", ("validation_rankings", 0)),
        ("trace container", ("lazy_evaluation_traces", 0)),
        ("trace row", ("lazy_evaluation_traces", 0, "trace", 0)),
        ("unevaluated trace row", ("lazy_evaluation_traces", 0, "trace", 3)),
        ("seed record", ("seed_records", 0)),
        ("selected row", ("selected_set", 0)),
        ("selected members mapping", ("selected_set", 0, "members_sha256")),
    )

    def test_every_nested_record_has_an_exact_key_set(self):
        for label, path in self.NESTED:
            self.refuse(lambda m, path=path: at(m, path).update(extra_key=1), label=label + " extra key")
            keys = list(at(self.two, path))
            for key in keys:
                self.refuse(lambda m, path=path, key=key: at(m, path).pop(key), label="%s missing %s" % (label, key))
        for label, path in self.NESTED:
            self.refuse(lambda m, path=path: put(m, path[:-1] + (path[-1],), None) if False else at(m, path[:-1]).__setitem__(path[-1], []), label=label + " wrong type")

    def test_the_nested_key_sets_are_the_documented_ones(self):
        self.assertEqual(sorted(self.two["candidate_table"][0]), sorted(selection.CANDIDATE_ROW_KEYS))
        self.assertEqual(sorted(self.two["selected_set"][0]), sorted(selection.SELECTED_ROW_KEYS))
        self.assertEqual(sorted(self.two["seed_records"][0]), sorted(selection.SEED_RECORD_KEYS))
        self.assertEqual(sorted(self.two["validation_rankings"][0]), sorted(selection.RANKING_ROW_KEYS))
        self.assertEqual(sorted(self.two["lazy_evaluation_traces"][0]), sorted(selection.TRACE_CONTAINER_KEYS))
        self.assertEqual(sorted(self.two["lazy_evaluation_traces"][0]["trace"][0]), sorted(selection.TRACE_ROW_KEYS))
        self.assertEqual(sorted(self.two["guardrail_manifests"][0]), sorted(selection.GUARDRAIL_INDEX_KEYS))
        self.assertEqual(sorted(self.two["replicate_manifests"][0]), sorted(selection.REPLICATE_INDEX_KEYS))
        config = common.load_config_bytes(open(os.path.join(ROOT, "config/experiments/D1_final_selection.yaml"), "rb").read())
        self.assertEqual(config["final_manifest"]["nested_keys"], {name: list(keys) for name, keys in selection.NESTED_KEY_SETS.items()})

    # -- digest type and shape

    DIGESTS = (
        ("replicate index digest", ("replicate_manifests", 0, "sha256")),
        ("second replicate index digest", ("replicate_manifests", 1, "sha256")),
        ("guardrail index digest", ("guardrail_manifests", 0, "sha256")),
        ("candidate weight", ("candidate_table", 0, "weight_sha256")),
        ("candidate guardrail digest", ("candidate_table", 2, "guardrail", "manifest_sha256")),
        ("ranking digest", ("validation_rankings", 0, "ranking_sha256")),
        ("trace digest", ("lazy_evaluation_traces", 0, "trace", 0, "guardrail_manifest_sha256")),
        ("seed record digest", ("seed_records", 0, "replicate_manifest_sha256")),
        ("selected weight", ("selected_set", 0, "weight_sha256")),
        ("selected-set digest", ("selected_set_sha256",)),
    ) + tuple(("candidate member " + name, ("candidate_table", 2, "members_sha256", name)) for name in common.CHECKPOINT_MEMBERS) + tuple(
        ("selected member " + name, ("selected_set", 0, "members_sha256", name)) for name in common.CHECKPOINT_MEMBERS
    )

    def test_every_recorded_digest_must_have_the_sha256_shape(self):
        for label, path in self.DIGESTS:
            for bad in BAD_DIGESTS:
                self.refuse(lambda m, path=path, bad=bad: put(m, path, bad), rehash=path != ("selected_set_sha256",), label="%s = %r" % (label, bad))
        # a digest that is only absent where a digest is required
        self.refuse(lambda m: put(m, ("selected_set_sha256",), None), rehash=False)
        self.refuse(lambda m: put(m, ("candidate_table", 2, "guardrail", "manifest_sha256"), None))
        self.refuse(lambda m: put(m, ("lazy_evaluation_traces", 0, "trace", 0, "guardrail_manifest_sha256"), None))
        # and a digest where none is allowed
        self.refuse(lambda m: put(m, ("candidate_table", 0, "guardrail", "manifest_sha256"), digest_of("x")))
        self.refuse(lambda m: put(m, ("lazy_evaluation_traces", 0, "trace", 3, "guardrail_manifest_sha256"), digest_of("x")))

    def test_integers_must_be_integers(self):
        for path, bad in (
            (("completed_seeds",), [43.0, 44.0]),
            (("completed_seeds",), [True, 44]),
            (("replicate_manifests", 0, "seed"), 43.0),
            (("guardrail_manifests", 0, "seed"), 43.0),
            (("guardrail_manifests", 0, "epoch"), 3.0),
            (("candidate_table", 2, "seed"), 43.0),
            (("candidate_table", 2, "epoch"), 3.0),
            (("candidate_table", 2, "epoch"), True),
            (("candidate_table", 2, "epoch"), "3"),
            (("candidate_table", 2, "rank"), 1.0),
            (("candidate_table", 2, "update"), 63.0),
            (("validation_rankings", 0, "seed"), 43.0),
            (("validation_rankings", 0, "ranked_epochs"), [3.0, 5, 4, 2, 1]),
            (("lazy_evaluation_traces", 0, "seed"), 43.0),
            (("lazy_evaluation_traces", 0, "trace", 0, "epoch"), 3.0),
            (("lazy_evaluation_traces", 0, "trace", 0, "rank"), 1.0),
            (("seed_records", 0, "seed"), 43.0),
            (("seed_records", 0, "selected_epoch"), 5.0),
            (("selected_set", 0, "epoch"), 5.0),
            (("selected_set", 0, "update"), 105.0),
            (("selected_set", 0, "seed"), 43.0),
        ):
            self.refuse(lambda m, path=path, bad=bad: put(m, path, bad), label=str((path, bad)))

    def test_json_types_are_compared_strictly(self):
        for path, bad in (
            (("closure", "human_gate_required"), 1),
            (("closure", "m7_complete"), 0),
            (("closure", "ref_opened"), 0),
            (("ref_eval_access", "eval_opened"), 0),
            (("allowed_seed_plan", "minimum_completed_seeds"), True),
            (("allowed_seed_plan", "validation_draw_seed"), 1.0),
            (("allowed_seed_plan", "target_seeds"), [43.0, 44.0]),
            (("m8_boundary", "two_seed_attempts_each"), 15000.0),
            (("m8_boundary", "implemented_in_this_package"), 0),
            (("m8_allocation", "43"), 15000.0),
        ):
            self.refuse(lambda m, path=path, bad=bad: put(m, path, bad), label=str((path, bad)))

        def reseal_with(**changes):
            def mutate(m):
                m["deviation"].update(changes)
                m["deviation"] = selection.seal_deviation(m["deviation"])

            return mutate

        self.refuse(reseal_with(omitted_seed=44.0), base=self.one)
        self.refuse(reseal_with(completed_seeds=[43.0]), base=self.one)
        self.refuse(reseal_with(rule=dict(selection.RULE_RECORD, decision_is_operational_only=1)), base=self.one)
        self.refuse(reseal_with(rule=dict(selection.RULE_RECORD, time_factor=True)), base=self.one)
        config = common.load_config_bytes(open(os.path.join(ROOT, "config/experiments/D1_final_selection.yaml"), "rb").read())
        for mutate in (
            lambda c: c["execution"].update(authorised=0),
            lambda c: c["allowed_seed_plan"].update(one_seed_requires_sealed_operational_deviation=1),
            lambda c: c["m8_boundary"].update(two_seed_attempts_each=15000.0),
            lambda c: c["authorisation_schema"].update(cpu_only=1),
        ):
            changed = copy.deepcopy(config)
            mutate(changed)
            with self.assertRaises(M7Error):
                selection.assert_inactive_configuration(changed)

    def test_checkpoint_names_and_values_are_validated(self):
        for path, bad in (
            (("candidate_table", 2, "checkpoint_name"), "x"),
            (("candidate_table", 2, "checkpoint_name"), None),
            (("candidate_table", 2, "checkpoint_name"), self.two["candidate_table"][1]["checkpoint_name"]),
            (("candidate_table", 2, "validation_mse"), "nan"),
            (("candidate_table", 2, "validation_mse"), 0.2),
            (("candidate_table", 2, "validation_mse"), None),
            (("selected_set", 0, "validation_mse"), "0.1"),
            (("selected_set", 0, "checkpoint_name"), self.two["candidate_table"][0]["checkpoint_name"]),
        ):
            self.refuse(lambda m, path=path, bad=bad: put(m, path, bad), label=str((path, bad)))

    # -- index entries

    def test_replicate_index_entries_cannot_be_duplicate_missing_extra_or_out_of_order(self):
        self.refuse(lambda m: m["replicate_manifests"].append(copy.deepcopy(m["replicate_manifests"][0])))
        self.refuse(lambda m: m["replicate_manifests"].pop())
        self.refuse(lambda m: m["replicate_manifests"].pop(0))
        self.refuse(lambda m: m["replicate_manifests"].reverse())
        self.refuse(lambda m: m["replicate_manifests"].append({"seed": 45, "sha256": digest_of("x")}))
        self.refuse(lambda m: m["replicate_manifests"].append({"seed": 42, "sha256": digest_of("x")}))
        self.refuse(lambda m: m["replicate_manifests"][1].update(seed=43))
        self.refuse(lambda m: m["replicate_manifests"].clear())
        self.refuse(lambda m: m.update(replicate_manifests=None))

    def test_guardrail_index_entries_cannot_be_duplicate_missing_extra_or_out_of_order(self):
        self.refuse(lambda m: m["guardrail_manifests"].append(copy.deepcopy(m["guardrail_manifests"][0])))
        for index in range(3):
            self.refuse(lambda m, index=index: m["guardrail_manifests"].pop(index), label="missing %d" % index)
        self.refuse(lambda m: m["guardrail_manifests"].reverse())
        self.refuse(lambda m: m["guardrail_manifests"].insert(0, m["guardrail_manifests"].pop()))
        self.refuse(lambda m: m["guardrail_manifests"].append({"epoch": 1, "seed": 43, "sha256": digest_of("unevaluated")}))
        self.refuse(lambda m: m["guardrail_manifests"].append({"epoch": 2, "seed": 44, "sha256": digest_of("unevaluated")}))
        self.refuse(lambda m: m["guardrail_manifests"].append({"epoch": 1, "seed": 45, "sha256": digest_of("stranger")}))
        self.refuse(lambda m: m["guardrail_manifests"][0].update(epoch=1))
        self.refuse(lambda m: m["guardrail_manifests"][0].update(seed=44))
        self.refuse(lambda m: m["guardrail_manifests"][0].update(sha256=digest_of("other")))
        self.refuse(lambda m: m["guardrail_manifests"][1].update(sha256=m["guardrail_manifests"][0]["sha256"]))
        self.refuse(lambda m: m["guardrail_manifests"].clear())

    def test_the_guardrail_index_equals_exactly_the_evaluated_rows_of_the_lazy_traces_and_candidate_table(self):
        evaluated = sorted((row["seed"], row["epoch"], row["guardrail"]["manifest_sha256"]) for row in self.two["candidate_table"] if row["guardrail"]["evaluated"])
        self.assertEqual(evaluated, sorted((item["seed"], item["epoch"], item["sha256"]) for item in self.two["guardrail_manifests"]))
        traced = sorted(
            (container["seed"], item["epoch"], item["guardrail_manifest_sha256"])
            for container in self.two["lazy_evaluation_traces"]
            for item in container["trace"]
            if item["evaluated"]
        )
        self.assertEqual(evaluated, traced)
        # a candidate marked evaluated in the table but not indexed, and the reverse
        def mark_evaluated(m):
            row = m["candidate_table"][0]
            row["guardrail"] = {"evaluated": True, "manifest_sha256": digest_of("x"), "passed": False}

        self.refuse(mark_evaluated)

        def unmark(m):
            m["candidate_table"][2]["guardrail"] = {"evaluated": False, "manifest_sha256": None, "passed": None}

        self.refuse(unmark)

    # -- ranking hashes

    def test_a_ranking_digest_is_recomputed_from_the_candidate_table(self):
        for seed_index, seed in enumerate((43, 44)):
            rows = {row["epoch"]: row for row in self.two["candidate_table"] if row["seed"] == seed}
            order = common.rank_validation_candidates({epoch: row["validation_mse"] for epoch, row in rows.items()})
            record = selection._ranking_record(rows, order)
            self.assertEqual(self.two["validation_rankings"][seed_index]["ranking_sha256"], selection._ranking_sha256(record))
            # the rebuilt record is the replicate-style ranking record exactly
            replicate_ranking = json.loads(two_seed_scenario()[seed_index][0].decode("utf-8"))["validation_ranking"]
            self.assertEqual(record, replicate_ranking)
        self.refuse(lambda m: m["validation_rankings"][0].update(ranking_sha256=digest_of("other")))
        self.refuse(lambda m: m["validation_rankings"][1].update(ranking_sha256=m["validation_rankings"][0]["ranking_sha256"]))
        self.refuse(lambda m: m["validation_rankings"][0].update(ranking_sha256=m["validation_rankings"][1]["ranking_sha256"]))

    def test_a_ranking_digest_recomputed_over_any_other_record_is_refused(self):
        def rebuilt(m, index=0, **changes):
            seed = m["completed_seeds"][index]
            rows = {row["epoch"]: row for row in m["candidate_table"] if row["seed"] == seed}
            order = m["validation_rankings"][index]["ranked_epochs"]
            record = selection._ranking_record(rows, order)
            for key, value in changes.items():
                record[key] = value
            return selection._ranking_sha256(record)

        def with_value(m):
            m["validation_rankings"][0]["ranking_sha256"] = rebuilt(m, 0, excludes_update_0=False)

        def with_rule(m):
            m["validation_rankings"][0]["ranking_sha256"] = rebuilt(m, 0, rule="best_epoch")

        def with_update_zero(m):
            seed = 43
            rows = {row["epoch"]: row for row in m["candidate_table"] if row["seed"] == seed}
            record = selection._ranking_record(rows, m["validation_rankings"][0]["ranked_epochs"])
            record["ranked_candidates"].append({"aggregate_mse": "0.0", "epoch": 0, "rank": 6, "update": 0})
            m["validation_rankings"][0]["ranking_sha256"] = selection._ranking_sha256(record)

        def with_other_mse(m):
            m["candidate_table"][2]["validation_mse"] = "0.20000000000000002"          # same order, different value; digest not recomputed

        def with_other_mse_consistent(m):
            m["candidate_table"][2]["validation_mse"] = "0.20000000000000002"
            m["selected_set"][0]["validation_mse"] = m["selected_set"][0]["validation_mse"]
            m["validation_rankings"][0]["ranking_sha256"] = "0" * 64

        for mutate in (with_value, with_rule, with_update_zero, with_other_mse, with_other_mse_consistent):
            self.refuse(mutate, label=mutate.__name__)
        # the order, the rule and the ranks themselves
        self.refuse(lambda m: m["validation_rankings"][0].update(ranked_epochs=[1, 2, 3, 4, 5]))
        self.refuse(lambda m: m["validation_rankings"][0].update(ranked_epochs=[5, 3, 4, 2, 1]))
        self.refuse(lambda m: m["validation_rankings"][0].update(ranked_epochs=[0, 3, 5, 4, 2, 1]))
        self.refuse(lambda m: m["validation_rankings"][0].update(ranked_epochs=[3, 5, 4, 2]))
        self.refuse(lambda m: m["validation_rankings"][0].update(rule="best_epoch"))
        self.refuse(lambda m: m["candidate_table"][2].update(rank=2))
        self.refuse(lambda m: m["lazy_evaluation_traces"][0]["trace"].reverse())

    def test_a_change_of_a_validation_value_that_keeps_the_order_still_breaks_the_digest(self):
        manifest = copy.deepcopy(self.two)
        row = manifest["candidate_table"][0]                      # seed 43 epoch 1 is ranked last and stays last
        row["validation_mse"] = common.format_decimal(float(row["validation_mse"]) + 0.01)
        with self.assertRaises(M7Error):
            selection.validate_final_selection_manifest(manifest)

    # -- seed status

    def test_a_seed_status_follows_from_the_lazy_trace(self):
        for label, mutate, base in (
            ("selected but marked none", lambda m: m["seed_records"][0].update(status="no_eligible_checkpoint"), self.two),
            ("selected epoch dropped", lambda m: m["seed_records"][0].update(selected_epoch=None), self.two),
            ("selected epoch moved to a failed candidate", lambda m: m["seed_records"][0].update(selected_epoch=3), self.two),
            ("selected epoch moved to an unevaluated candidate", lambda m: m["seed_records"][0].update(selected_epoch=4), self.two),
            ("selected epoch zero", lambda m: m["seed_records"][0].update(selected_epoch=0), self.two),
            ("selected epoch six", lambda m: m["seed_records"][0].update(selected_epoch=6), self.two),
            ("unknown status", lambda m: m["seed_records"][0].update(status="best"), self.two),
            ("status missing meaning", lambda m: m["seed_records"][0].update(status=None), self.two),
            ("lazy state altered", lambda m: m["seed_records"][0].update(lazy_state="no_eligible_checkpoint"), self.two),
            ("lazy state unknown", lambda m: m["seed_records"][0].update(lazy_state="selected"), self.two),
            ("none marked selected", lambda m: m["seed_records"][0].update(status="selected"), self.none),
            ("none given a selected epoch", lambda m: m["seed_records"][0].update(selected_epoch=3, status="selected"), self.none),
            ("none given a lazy state", lambda m: m["seed_records"][0].update(lazy_state="passed"), self.none),
            ("one seed marked none", lambda m: m["seed_records"][0].update(status="no_eligible_checkpoint", selected_epoch=None, lazy_state="no_eligible_checkpoint"), self.one),
        ):
            self.refuse(mutate, base=base, label=label)

    def test_no_eligible_checkpoint_requires_all_five_candidates_evaluated_and_failed(self):
        def unevaluate_last(m):
            row = next(item for item in m["candidate_table"] if item["seed"] == 43 and item["epoch"] == 1)    # rank 5 of seed 43
            row["guardrail"] = {"evaluated": False, "manifest_sha256": None, "passed": None}
            m["guardrail_manifests"] = [item for item in m["guardrail_manifests"] if not (item["seed"] == 43 and item["epoch"] == 1)]
            trace = m["lazy_evaluation_traces"][0]["trace"][-1]
            trace.update(evaluated=False, guardrail_manifest_sha256=None, outcome=selection.UNEVALUATED_OUTCOME)

        def pass_the_last(m):
            row = next(item for item in m["candidate_table"] if item["seed"] == 43 and item["epoch"] == 1)
            row["guardrail"]["passed"] = True
            m["lazy_evaluation_traces"][0]["trace"][-1]["outcome"] = "passed"

        self.refuse(unevaluate_last, base=self.none)
        self.refuse(pass_the_last, base=self.none)
        self.refuse(lambda m: m.update(selection_outcome="selected_set_complete"), base=self.none)
        self.refuse(lambda m: m.update(selected_set=[], selected_set_sha256=selection.selected_set_sha256([])), base=self.none)
        self.refuse(lambda m: m.update(selected_set_sha256=digest_of("x")), base=self.none, rehash=False)

    def test_the_first_passing_candidate_is_the_one_selected(self):
        # make the failed rank-1 candidate pass: then it, not rank 2, is the first passing candidate
        def pass_first(m):
            m["candidate_table"][2]["guardrail"]["passed"] = True
            m["lazy_evaluation_traces"][0]["trace"][0]["outcome"] = "passed"

        self.refuse(pass_first)

        def trace_after_pass(m):
            m["lazy_evaluation_traces"][0]["trace"][2].update(evaluated=True, guardrail_manifest_sha256=digest_of("x"), outcome="failed")

        self.refuse(trace_after_pass)
        self.refuse(lambda m: m["lazy_evaluation_traces"][0]["trace"][2].update(outcome="failed"))
        self.refuse(lambda m: m["lazy_evaluation_traces"][0]["trace"][2].update(outcome="not_evaluated"))
        self.refuse(lambda m: m["lazy_evaluation_traces"][0]["trace"].pop())
        self.refuse(lambda m: m["lazy_evaluation_traces"][0]["trace"][0].update(evaluated=False))
        self.refuse(lambda m: m["lazy_evaluation_traces"][0]["trace"][1].update(outcome="failed"))

    # -- checkpoint member hashes

    def test_every_checkpoint_member_hash_of_the_selected_row_is_bound_even_when_the_set_hash_is_recomputed(self):
        for name in common.CHECKPOINT_MEMBERS:
            if name == common.WEIGHT_MEMBER:
                continue
            tampered = self.refuse(lambda m, name=name: m["selected_set"][0]["members_sha256"].update({name: digest_of("tampered " + name)}), label=name)
            self.assertEqual(tampered["selected_set_sha256"], selection.selected_set_sha256(tampered["selected_set"]), "the set hash was recomputed")
        self.refuse(lambda m: m["selected_set"][0]["members_sha256"].update({common.WEIGHT_MEMBER: digest_of("w")}))
        self.refuse(lambda m: m["selected_set"][0].update(weight_sha256=digest_of("w")))

        def weight_everywhere_in_selected(m):
            m["selected_set"][0]["weight_sha256"] = digest_of("w")
            m["selected_set"][0]["members_sha256"][common.WEIGHT_MEMBER] = digest_of("w")

        self.refuse(weight_everywhere_in_selected)
        # a member renamed, removed or added
        self.refuse(lambda m: m["selected_set"][0]["members_sha256"].update({"unet/other.json": digest_of("x")}))
        self.refuse(lambda m: m["selected_set"][0]["members_sha256"].pop("model_index.json"))
        self.refuse(lambda m: m["selected_set"][0].pop("members_sha256"))

    def test_the_candidate_row_members_must_match_the_selected_row_and_the_weight(self):
        for name in common.CHECKPOINT_MEMBERS:
            if name == common.WEIGHT_MEMBER:
                continue
            self.refuse(lambda m, name=name: m["candidate_table"][4]["members_sha256"].update({name: digest_of("tampered " + name)}), label=name)
        self.refuse(lambda m: m["candidate_table"][4]["members_sha256"].update({common.WEIGHT_MEMBER: digest_of("w")}))
        for index in (0, 1, 2, 3, 4):
            self.refuse(lambda m, index=index: m["candidate_table"][index]["members_sha256"].update({common.WEIGHT_MEMBER: digest_of("w%d" % index)}), label="weight %d" % index)
        self.refuse(lambda m: m["candidate_table"][1]["members_sha256"].pop("unet/config.json"))
        self.refuse(lambda m: m["candidate_table"][1].pop("members_sha256"))
        self.refuse(lambda m: m["candidate_table"][1].update(members_sha256=None))

    def test_a_forbidden_m6_weight_or_a_repeated_weight_is_refused(self):
        forbidden = next(iter(common.M6_FORBIDDEN_WEIGHT_SHA256))

        def forbid_candidate(m):
            m["candidate_table"][0]["weight_sha256"] = forbidden
            m["candidate_table"][0]["members_sha256"][common.WEIGHT_MEMBER] = forbidden

        def forbid_selected(m):
            m["selected_set"][0]["weight_sha256"] = forbidden
            m["selected_set"][0]["members_sha256"][common.WEIGHT_MEMBER] = forbidden
            m["candidate_table"][4]["weight_sha256"] = forbidden
            m["candidate_table"][4]["members_sha256"][common.WEIGHT_MEMBER] = forbidden

        def repeat(m):
            m["candidate_table"][1]["weight_sha256"] = m["candidate_table"][0]["weight_sha256"]
            m["candidate_table"][1]["members_sha256"][common.WEIGHT_MEMBER] = m["candidate_table"][0]["weight_sha256"]

        for mutate in (forbid_candidate, forbid_selected, repeat):
            self.refuse(mutate, label=mutate.__name__)

    def test_a_consistent_rewrite_of_a_non_weight_member_needs_the_sealed_inputs_to_detect(self):
        """The manifest alone cannot prove the replicate bytes, so ``rebuild_matches`` is the authenticity check."""
        first, second = two_seed_scenario()
        replicates = [first[0], second[0]]
        guardrail_blobs = list(first[1]) + list(second[1])
        exact = selection.final_selection_bytes(self.two)
        self.assertTrue(selection.rebuild_matches(exact, replicates, guardrail_blobs))
        forged = copy.deepcopy(self.two)
        name = "model_index.json"
        forged["candidate_table"][4]["members_sha256"][name] = digest_of("forged")
        forged["selected_set"][0]["members_sha256"][name] = digest_of("forged")
        forged["selected_set_sha256"] = selection.selected_set_sha256(forged["selected_set"])
        self.assertTrue(selection.validate_final_selection_manifest(forged), "self-consistent, so the manifest alone cannot refute it")
        self.assertFalse(selection.rebuild_matches(selection.final_selection_bytes(forged), replicates, guardrail_blobs))
        self.assertFalse(selection.rebuild_matches(exact + b" ", replicates, guardrail_blobs))
        with self.assertRaises(M7Error):
            selection.rebuild_matches(exact, replicates, guardrail_blobs[:-1])

    def test_the_selected_set_hash_is_a_content_hash_and_is_documented_as_one(self):
        documentation = selection.validate_final_selection_manifest.__doc__
        self.assertIn("not an authenticity mechanism", documentation)
        self.assertIn("not an authenticity mechanism", selection.selected_set_sha256.__doc__)
        self.assertEqual(self.two["selected_set_sha256"], selection.selected_set_sha256(self.two["selected_set"]))
        self.assertEqual(selection.selected_set_sha256(list(reversed(self.two["selected_set"]))), self.two["selected_set_sha256"])
        # tampering without recomputing the hash
        self.refuse(lambda m: m["selected_set"][0].update(update=84), rehash=False)
        self.refuse(lambda m: m["selected_set"][0]["members_sha256"].update({"model_index.json": digest_of("x")}), rehash=False)

    # -- replicate hashes against seed records and deviation bindings

    def test_replicate_hashes_must_agree_between_the_index_the_seed_records_and_the_deviation(self):
        self.refuse(lambda m: m["seed_records"][0].update(replicate_manifest_sha256=digest_of("other")))
        self.refuse(lambda m: m["seed_records"][1].update(replicate_manifest_sha256=m["seed_records"][0]["replicate_manifest_sha256"]))
        self.refuse(lambda m: m["replicate_manifests"][0].update(sha256=digest_of("other")))
        # one seed: the index and the seed record agree, the sealed deviation names another seed-43 manifest
        def rebind(m):
            m["replicate_manifests"][0]["sha256"] = digest_of("other")
            m["seed_records"][0]["replicate_manifest_sha256"] = digest_of("other")

        self.refuse(rebind, base=self.one)

        def reseal_elsewhere(m):
            m["deviation"]["seed_43_replicate_manifest_sha256"] = digest_of("other")
            m["deviation"] = selection.seal_deviation(m["deviation"])

        self.refuse(reseal_elsewhere, base=self.one)
        self.refuse(lambda m: m["deviation"].update(omitted_seed=43), base=self.one)
        self.refuse(lambda m: m["deviation"].update(sealed=False), base=self.one)
        self.refuse(lambda m: m["deviation"].pop("sealed_at"), base=self.one)

    # -- the plan itself

    def test_the_seed_plan_rules_still_hold(self):
        self.refuse(lambda m: m.update(completed_seeds=[44]))
        self.refuse(lambda m: m.update(completed_seeds=[43]))
        self.refuse(lambda m: m.update(completed_seeds=[44, 43]))
        self.refuse(lambda m: m.update(completed_seeds=[43, 44, 45]))
        self.refuse(lambda m: m.update(completed_seeds=[]))
        self.refuse(lambda m: m.update(deviation=copy.deepcopy(self.one["deviation"])))
        self.refuse(lambda m: m.update(deviation=None), base=self.one)
        self.refuse(lambda m: m.update(m8_allocation={"43": 30000}))
        self.refuse(lambda m: m.update(m8_allocation={"43": 15000, "44": 15000}), base=self.one)
        for epoch_row in (0, 6):
            self.refuse(lambda m, epoch_row=epoch_row: m["candidate_table"][0].update(epoch=epoch_row, update=epoch_row * 21))
        self.refuse(lambda m: m["candidate_table"].pop(0))
        self.refuse(lambda m: m["candidate_table"].reverse())
        self.refuse(lambda m: m["candidate_table"].append(copy.deepcopy(m["candidate_table"][0])))
        self.refuse(lambda m: m["lazy_evaluation_traces"].reverse())
        self.refuse(lambda m: m["seed_records"].reverse())
        self.refuse(lambda m: m["validation_rankings"].reverse())
        self.refuse(lambda m: m["selected_set"].reverse())
        self.refuse(lambda m: m["closure"].update(human_gate_required=False))
        self.refuse(lambda m: m.update(manifest_schema_version="m7-final-selection-manifest-1"))
        self.refuse(lambda m: m.update(schema_version="m7-final-selection-config-1"))


# The sealed seed-43 training implementation, the sealed seed-44 training
# implementation, the failed seed-43 attempt-1 implementation (another
# replicate), and current main, which is later than the seed-43 training
# commit. The last value stands for a later guardrail execution commit. This
# fixture does not authorise it.
SEED43_TRAINING_COMMIT = "c150894b9982d7afebfb2b3390b0797a4da146b5"
SEED44_TRAINING_COMMIT = "2cb1b6a26391ed36754ec21685a4501d659d50ef"
OTHER_REPLICATE_TRAINING_COMMIT = "e682cb6064a578868cc258e58465a0c036afe0d4"
LATER_GUARDRAIL_EXECUTION_COMMIT = "00db7d9d5317e7b17f5d51adbbcd6c87bf9cce12"


def retarget_training(manifest, commit):
    """A replicate manifest whose training implementation is ``commit``.

    A replicate manifest's ``executing_implementation_commit`` is that training
    implementation. Checkpoint directory names are resealed to the same commit.
    """
    changed = copy.deepcopy(manifest)
    changed["authorisation"]["authorization_parent_commit"] = commit
    changed["authorisation"]["executing_implementation_commit"] = commit
    for item in changed["checkpoints"]:
        item["directory_name"] = contract.checkpoint_child_name(changed["seed"], item["epoch"], commit)
    contract.validate_replicate_manifest(changed)
    return changed


def trained_manifest(seed, mse, commit):
    base = support.variant(support.successful_run(seed)["manifest"], mse_by_epoch=mse, weight_salt="seed%d" % seed)
    return retarget_training(base, commit)


def prefix_guardrails(manifest, replicate_blob, outcomes, execution_commit=None):
    order = [item["epoch"] for item in manifest["validation_ranking"]["ranked_candidates"]]
    blobs = []
    preceding = []
    for position, passed in enumerate(outcomes, start=1):
        epoch = order[position - 1]
        blob_i = support.guardrail_blob(manifest, replicate_blob, epoch, passed, position, list(preceding), execution_commit=execution_commit)
        blobs.append(blob_i)
        if not passed:
            preceding.append({"epoch": epoch, "manifest_sha256": common.sha256_bytes(blob_i), "outcome": "failed"})
    return order, blobs


def forward_seed43(outcomes=(False, True)):
    """Seed 43 trained at c150894, with a later unequal guardrail execution commit."""
    manifest = trained_manifest(43, MSE_A, SEED43_TRAINING_COMMIT)
    blob = common.canonical_json(manifest)
    order, guards = prefix_guardrails(manifest, blob, outcomes, LATER_GUARDRAIL_EXECUTION_COMMIT)
    deviation = support.deviation_blob(blob, manifest)
    return blob, guards, manifest, order, deviation


def rewrite_checkpoint_training(guardrail, commit, rewrite_directory):
    changed = copy.deepcopy(guardrail)
    changed["authorisation"]["checkpoint_training_implementation_commit"] = commit
    if rewrite_directory:
        changed["checkpoint"]["directory_name"] = contract.checkpoint_child_name(changed["candidate"]["seed"], changed["candidate"]["epoch"], commit)
    return changed


class ForwardProvenanceSelectionTests(unittest.TestCase):
    """Selection binds checkpoint provenance, not the guardrail execution commit."""

    def test_a_forward_guardrail_manifest_selects_when_training_provenance_matches(self):
        blob, guards, manifest, order, deviation = forward_seed43()
        parsed_guard = json.loads(guards[0].decode("utf-8"))
        authorisation = parsed_guard["authorisation"]
        self.assertEqual(authorisation["checkpoint_training_implementation_commit"], SEED43_TRAINING_COMMIT)
        self.assertEqual(authorisation["executing_implementation_commit"], LATER_GUARDRAIL_EXECUTION_COMMIT)
        self.assertEqual(authorisation["authorization_parent_commit"], LATER_GUARDRAIL_EXECUTION_COMMIT)
        self.assertNotEqual(authorisation["executing_implementation_commit"], authorisation["checkpoint_training_implementation_commit"])
        self.assertEqual(manifest["authorisation"]["executing_implementation_commit"], SEED43_TRAINING_COMMIT)
        self.assertTrue(parsed_guard["checkpoint"]["directory_name"].endswith(SEED43_TRAINING_COMMIT))
        built = selection.build_final_selection([blob], guards, deviation)
        self.assertEqual(built["selection_outcome"], selection.OUTCOME_COMPLETE)
        self.assertEqual(built["completed_seeds"], [43])
        self.assertEqual(built["m8_allocation"], {"43": 30000})
        self.assertEqual(built["validation_rankings"][0]["ranked_epochs"], order)
        self.assertEqual(built["validation_rankings"][0]["rule"], common.RANKING_RULE)
        self.assertEqual(built["seed_records"][0]["selected_epoch"], order[1])
        self.assertEqual(built["seed_records"][0]["status"], "selected")
        self.assertEqual(built["seed_records"][0]["lazy_state"], "passed")
        self.assertEqual(built["selected_set"][0]["epoch"], order[1])
        self.assertTrue(built["selected_set"][0]["checkpoint_name"].endswith(SEED43_TRAINING_COMMIT))
        self.assertFalse(built["selected_set"][0]["checkpoint_name"].endswith(LATER_GUARDRAIL_EXECUTION_COMMIT))
        self.assertEqual(built["candidate_table"][order[0] - 1]["guardrail"]["passed"], False)
        self.assertEqual(built["candidate_table"][order[1] - 1]["guardrail"]["passed"], True)
        self.assertEqual(built["guardrail_manifests"], [
            {"epoch": order[0], "seed": 43, "sha256": common.sha256_bytes(guards[0])},
            {"epoch": order[1], "seed": 43, "sha256": common.sha256_bytes(guards[1])},
        ])
        self.assertIsNotNone(built["deviation"])
        rendered = selection.final_selection_bytes(built).decode("utf-8")
        self.assertIn(SEED43_TRAINING_COMMIT, rendered)
        self.assertNotIn(LATER_GUARDRAIL_EXECUTION_COMMIT, rendered)
        self.assertNotIn("executing_implementation_commit", built)
        self.assertNotIn("checkpoint_training_implementation_commit", built)
        self.assertTrue(selection.rebuild_matches(selection.final_selection_bytes(built), [blob], guards, deviation))
        reversed_bytes = selection.final_selection_bytes(selection.build_final_selection([blob], list(reversed(guards)), deviation))
        self.assertEqual(reversed_bytes, selection.final_selection_bytes(built))

    def test_existing_equal_commit_ranking_fallback_two_seed_and_allocation_behavior_is_unchanged(self):
        first, second = two_seed_scenario()
        for guardrail_blob in list(first[1]) + list(second[1]):
            authorisation = json.loads(guardrail_blob.decode("utf-8"))["authorisation"]
            self.assertEqual(
                authorisation["checkpoint_training_implementation_commit"],
                authorisation["executing_implementation_commit"],
            )
        built = build(first, second)
        self.assertEqual(built["selection_outcome"], selection.OUTCOME_COMPLETE)
        self.assertEqual(built["completed_seeds"], [43, 44])
        self.assertEqual(built["m8_allocation"], {"43": 15000, "44": 15000})
        self.assertIsNone(built["deviation"])
        self.assertEqual([row["seed"] for row in built["selected_set"]], [43, 44])
        self.assertEqual(built["validation_rankings"][0]["rule"], common.RANKING_RULE)
        one = support.scenario(43, MSE_A, [False, False, False, False, False])
        deviation = support.deviation_blob(one[0], one[2])
        none = build(one, None, deviation)
        self.assertEqual(none["selection_outcome"], selection.OUTCOME_NONE)
        self.assertIsNone(none["selected_set"])
        self.assertEqual(none["m8_allocation"], {"43": 30000})

    def test_missing_malformed_substituted_and_mismatched_checkpoint_training_commits_are_refused(self):
        blob, guards, _manifest, _order, deviation = forward_seed43((True,))
        original = json.loads(guards[0].decode("utf-8"))

        missing = copy.deepcopy(original)
        del missing["authorisation"]["checkpoint_training_implementation_commit"]
        with self.assertRaises(M7Error) as caught:
            selection.build_final_selection([blob], [common.canonical_json(missing)], deviation)
        self.assertEqual(caught.exception.code, "guardrail_manifest_invalid")

        for malformed in ("short", "B" * 40, "", None, "c150894b9982d7afebfb2b3390b0797a4da146b"):
            changed = copy.deepcopy(original)
            changed["authorisation"]["checkpoint_training_implementation_commit"] = malformed
            with self.assertRaises(M7Error) as caught:
                selection.build_final_selection([blob], [common.canonical_json(changed)], deviation)
            self.assertEqual(caught.exception.code, "guardrail_manifest_invalid")

        substituted = rewrite_checkpoint_training(original, "d" * 40, rewrite_directory=False)
        with self.assertRaises(M7Error) as caught:
            selection.build_final_selection([blob], [common.canonical_json(substituted)], deviation)
        self.assertEqual(caught.exception.code, "guardrail_manifest_invalid")

        mismatched = rewrite_checkpoint_training(original, LATER_GUARDRAIL_EXECUTION_COMMIT, rewrite_directory=True)
        self.assertEqual(mismatched["authorisation"]["executing_implementation_commit"], LATER_GUARDRAIL_EXECUTION_COMMIT)
        self.assertNotEqual(mismatched["authorisation"]["checkpoint_training_implementation_commit"], SEED43_TRAINING_COMMIT)
        with self.assertRaises(M7Error) as caught:
            selection.build_final_selection([blob], [common.canonical_json(mismatched)], deviation)
        self.assertEqual(caught.exception.code, "selection_invalid")
        self.assertIn("sealed training implementation", caught.exception.detail)

    def test_a_checkpoint_training_commit_that_names_another_seed_or_replicate_is_refused(self):
        blob, guards, _manifest, _order, deviation = forward_seed43((True,))
        original = json.loads(guards[0].decode("utf-8"))
        for foreign in (SEED44_TRAINING_COMMIT, OTHER_REPLICATE_TRAINING_COMMIT):
            named = rewrite_checkpoint_training(original, foreign, rewrite_directory=True)
            named["authorisation"]["executing_implementation_commit"] = SEED43_TRAINING_COMMIT
            named["authorisation"]["authorization_parent_commit"] = SEED43_TRAINING_COMMIT
            self.assertEqual(named["authorisation"]["executing_implementation_commit"], SEED43_TRAINING_COMMIT)
            self.assertNotEqual(named["authorisation"]["checkpoint_training_implementation_commit"], SEED43_TRAINING_COMMIT)
            with self.assertRaises(M7Error) as caught:
                selection.build_final_selection([blob], [common.canonical_json(named)], deviation)
            self.assertEqual(caught.exception.code, "selection_invalid")
            self.assertIn("sealed training implementation", caught.exception.detail)

    def test_selection_does_not_substitute_the_execution_commit_for_checkpoint_provenance(self):
        blob, guards, _manifest, _order, deviation = forward_seed43((True,))
        original = json.loads(guards[0].decode("utf-8"))
        trapped = rewrite_checkpoint_training(original, SEED44_TRAINING_COMMIT, rewrite_directory=True)
        trapped["authorisation"]["executing_implementation_commit"] = SEED43_TRAINING_COMMIT
        trapped["authorisation"]["authorization_parent_commit"] = SEED43_TRAINING_COMMIT
        self.assertEqual(trapped["authorisation"]["executing_implementation_commit"], SEED43_TRAINING_COMMIT)
        with self.assertRaises(M7Error) as caught:
            selection.build_final_selection([blob], [common.canonical_json(trapped)], deviation)
        self.assertEqual(caught.exception.code, "selection_invalid")
        self.assertIn("sealed training implementation", caught.exception.detail)
        accepted = json.loads(guards[0].decode("utf-8"))
        self.assertNotEqual(accepted["authorisation"]["executing_implementation_commit"], SEED43_TRAINING_COMMIT)
        self.assertEqual(accepted["authorisation"]["checkpoint_training_implementation_commit"], SEED43_TRAINING_COMMIT)
        built = selection.build_final_selection([blob], guards, deviation)
        self.assertEqual(built["selection_outcome"], selection.OUTCOME_COMPLETE)
        self.assertTrue(built["selected_set"][0]["checkpoint_name"].endswith(SEED43_TRAINING_COMMIT))


# Real sealed training commits and the SHA-256 of each parent replicate YAML.
# The configuration hashes differ because those YAML bytes carry different
# single-use authorisation state. They are not a second training protocol.
SEED43_CONFIG_SHA256 = "be4af21865f1561471ae5e63dd6231269adace8470f0fcd8bfede7847b89bdd6"
SEED44_CONFIG_SHA256 = "d65b78ac72bd4dccd8d7dd52be5914d8227c34f0759315064f8d3fe3c649be35"
SEED43_AUTHORIZATION_COMMIT = SEED44_TRAINING_COMMIT
SEED44_AUTHORIZATION_COMMIT = "00db7d9d5317e7b17f5d51adbbcd6c87bf9cce12"
# Synthetic stand-ins for later guardrail execution. They authorise nothing.
GUARDRAIL_EXECUTION_SEED43 = "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1"
GUARDRAIL_EXECUTION_SEED44 = "b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2"


def revision_2_consistency_signature(view):
    """Revision 2 required these fields, including the training commit, to be equal."""
    parsed = view["parsed"]
    identity = parsed["b1_identity"]
    artifacts = parsed["validation_artifacts"]
    return {
        "b1_initial_state_aggregate_digest": identity["initial_state_aggregate_digest"],
        "b1_initial_state_parameter_names_sha256": identity["initial_state_parameter_names_sha256"],
        "b1_unet_config_sha256": identity["unet_config_sha256"],
        "b1_weight_sha256": identity["weight_sha256"],
        "checkpoint_training_implementation_commit": view["checkpoint_training_implementation_commit"],
        "implementation_config_sha256": parsed["configuration"]["implementation_config_sha256"],
        "schedule_trace_sha256": parsed["schedule"]["applied_learning_rate_trace_sha256"],
        "validation_artifacts": {
            key: artifacts[key]
            for key in (
                "draw_manifest_sha256",
                "hash_report_sha256",
                "noise_sha256",
                "order_artifact_sha256",
                "sequence_order_sha256",
                "timestep_sha256",
                "validation_csv_sha256",
            )
        },
    }


def revision_2_assert_cross_seed_consistency(views):
    """The revision-2 rule. Equal training commits are impossible for the real pair."""
    signatures = {seed: revision_2_consistency_signature(view) for seed, view in views.items()}
    reference = next(iter(signatures.values()))
    for seed, signature in signatures.items():
        if signature["b1_initial_state_aggregate_digest"] != reference["b1_initial_state_aggregate_digest"] or (
            signature["b1_initial_state_parameter_names_sha256"] != reference["b1_initial_state_parameter_names_sha256"]
        ):
            raise M7Error("selection_invalid", "the B1 initial-state digests differ between seeds")
        if signature["validation_artifacts"] != reference["validation_artifacts"]:
            raise M7Error("selection_invalid", "the validation artifact identities differ between seeds")
        if signature != reference:
            raise M7Error("selection_invalid", "the seeds were not trained under one identical implementation and B1")
    return True


def seal_sequential_replicate(seed, mse, training_commit, authorization_commit, config_sha256):
    manifest = trained_manifest(seed, mse, training_commit)
    if authorization_commit == training_commit:
        raise AssertionError("an authorisation commit must not alias the training commit")
    manifest["authorisation"]["authorization_commit"] = authorization_commit
    manifest["configuration"]["implementation_config_sha256"] = config_sha256
    manifest["repository"]["authorization_commit"] = authorization_commit
    manifest["repository"]["executing_implementation_commit"] = training_commit
    contract.validate_replicate_manifest(manifest)
    return manifest


def actual_training_topology():
    """The real two-seed commit topology, as synthetic manifest bytes.

    Seed 43 is sealed at c150894…. Seed 44 is sealed at 2cb1b6a…. Each
    guardrail execution commit is later than, and distinct from, both training
    commits. Rank-1 passes, so both seeds are selected.
    """
    left = seal_sequential_replicate(43, MSE_A, SEED43_TRAINING_COMMIT, SEED43_AUTHORIZATION_COMMIT, SEED43_CONFIG_SHA256)
    right = seal_sequential_replicate(44, MSE_B, SEED44_TRAINING_COMMIT, SEED44_AUTHORIZATION_COMMIT, SEED44_CONFIG_SHA256)
    left_blob = common.canonical_json(left)
    right_blob = common.canonical_json(right)
    _order43, guards43 = prefix_guardrails(left, left_blob, (True,), GUARDRAIL_EXECUTION_SEED43)
    _order44, guards44 = prefix_guardrails(right, right_blob, (True,), GUARDRAIL_EXECUTION_SEED44)
    return (left_blob, guards43, left), (right_blob, guards44, right)


def topology_views(pair):
    views = {}
    for blob, _guards, _manifest in pair:
        parsed, sha = selection._parse_canonical(blob, "a replicate manifest")
        views[parsed["seed"]] = selection._replicate_view(parsed, sha)
    return views


class SequentialAuthorisationSelectionTests(unittest.TestCase):
    """Two real training commits must select. Cross-seed substitution must not."""

    def setUp(self):
        self.pair = actual_training_topology()
        self.views = topology_views(self.pair)

    def test_actual_two_seed_training_commits_select_and_revision_2_equality_refuses(self):
        left, right = self.pair
        self.assertEqual(left[2]["authorisation"]["executing_implementation_commit"], SEED43_TRAINING_COMMIT)
        self.assertEqual(right[2]["authorisation"]["executing_implementation_commit"], SEED44_TRAINING_COMMIT)
        self.assertNotEqual(SEED43_TRAINING_COMMIT, SEED44_TRAINING_COMMIT)
        self.assertEqual(left[2]["configuration"]["implementation_config_sha256"], SEED43_CONFIG_SHA256)
        self.assertEqual(right[2]["configuration"]["implementation_config_sha256"], SEED44_CONFIG_SHA256)
        self.assertNotEqual(SEED43_CONFIG_SHA256, SEED44_CONFIG_SHA256)
        self.assertEqual(left[2]["configuration"]["implementation_file_hashes"], right[2]["configuration"]["implementation_file_hashes"])
        for blob, guards, manifest in (left, right):
            guard = json.loads(guards[0].decode("utf-8"))["authorisation"]
            training = manifest["authorisation"]["executing_implementation_commit"]
            self.assertEqual(guard["checkpoint_training_implementation_commit"], training)
            self.assertNotIn(guard["executing_implementation_commit"], (SEED43_TRAINING_COMMIT, SEED44_TRAINING_COMMIT))
            self.assertNotEqual(guard["executing_implementation_commit"], training)
        signature = selection._consistency_signature(self.views[43])
        self.assertNotIn("checkpoint_training_implementation_commit", signature)
        self.assertNotIn("implementation_config_sha256", signature)
        self.assertEqual(selection._consistency_signature(self.views[44]), signature)
        with self.assertRaises(M7Error) as caught:
            revision_2_assert_cross_seed_consistency(self.views)
        self.assertEqual(caught.exception.code, "selection_invalid")
        self.assertIn("identical implementation", caught.exception.detail)
        built = build(left, right)
        self.assertEqual(built["selection_outcome"], selection.OUTCOME_COMPLETE)
        self.assertEqual(built["completed_seeds"], [43, 44])
        self.assertIsNone(built["deviation"])
        self.assertEqual(built["m8_allocation"], {"43": 15000, "44": 15000})
        self.assertEqual(sum(built["m8_allocation"].values()), 30000)
        selected = {item["seed"]: item for item in built["selected_set"]}
        self.assertEqual(sorted(selected), [43, 44])
        self.assertTrue(selected[43]["checkpoint_name"].endswith(SEED43_TRAINING_COMMIT))
        self.assertTrue(selected[44]["checkpoint_name"].endswith(SEED44_TRAINING_COMMIT))
        self.assertNotIn(GUARDRAIL_EXECUTION_SEED43, selection.final_selection_bytes(built).decode("utf-8"))
        self.assertNotIn(GUARDRAIL_EXECUTION_SEED44, selection.final_selection_bytes(built).decode("utf-8"))
        self.assertTrue(selection.rebuild_matches(selection.final_selection_bytes(built), [left[0], right[0]], list(left[1]) + list(right[1])))
        reversed_bytes = selection.final_selection_bytes(selection.build_final_selection([right[0], left[0]], list(right[1]) + list(left[1])))
        self.assertEqual(reversed_bytes, selection.final_selection_bytes(built))

    def _refuse_substituted_guardrail(self, seed, foreign_commit):
        left, right = self.pair
        source = left if seed == 43 else right
        original = json.loads(source[1][0].decode("utf-8"))
        swapped = rewrite_checkpoint_training(original, foreign_commit, rewrite_directory=True)
        self.assertEqual(swapped["authorisation"]["checkpoint_training_implementation_commit"], foreign_commit)
        self.assertNotEqual(swapped["authorisation"]["checkpoint_training_implementation_commit"], source[2]["authorisation"]["executing_implementation_commit"])
        guard43 = common.canonical_json(swapped) if seed == 43 else left[1][0]
        guard44 = common.canonical_json(swapped) if seed == 44 else right[1][0]
        with self.assertRaises(M7Error) as caught:
            selection.build_final_selection([left[0], right[0]], [guard43, guard44])
        self.assertEqual(caught.exception.code, "selection_invalid")
        self.assertIn("sealed training implementation", caught.exception.detail)

    def test_seed_43_guardrail_bound_to_seed_44_training_commit_is_refused(self):
        self._refuse_substituted_guardrail(43, SEED44_TRAINING_COMMIT)

    def test_seed_44_guardrail_bound_to_seed_43_training_commit_is_refused(self):
        self._refuse_substituted_guardrail(44, SEED43_TRAINING_COMMIT)

    def test_different_implementation_file_hashes_are_refused(self):
        left, right = self.pair
        changed = copy.deepcopy(right[2])
        path = sorted(changed["configuration"]["implementation_file_hashes"])[0]
        changed["configuration"]["implementation_file_hashes"][path] = support.digest("other-implementation-file")
        contract.validate_replicate_manifest(changed)
        with self.assertRaises(M7Error) as caught:
            selection.build_final_selection([left[0], common.canonical_json(changed)], list(left[1]) + list(right[1]))
        self.assertEqual(caught.exception.code, "selection_invalid")
        self.assertIn("implementation file hashes", caught.exception.detail)

    def test_different_b1_identity_is_refused(self):
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["b1_identity"]["initial_state_aggregate_digest"] = support.digest("other-b1-aggregate")
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("B1 initial-state digests", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["b1_identity"]["initial_state_parameter_names_sha256"] = support.digest("other-b1-names")
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("B1 initial-state digests", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["b1_identity"]["initial_state_entry_count"] = views[44]["parsed"]["b1_identity"]["initial_state_entry_count"] + 1
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("B1 initialisation identity", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["b1_identity"]["weight_sha256"] = support.digest("other-b1-weight")
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("B1 initialisation identity", caught.exception.detail)
        views = copy.deepcopy(self.views)
        asset = sorted(views[44]["parsed"]["b1_identity"]["observed_assets"])[0]
        views[44]["parsed"]["b1_identity"]["observed_assets"][asset]["sha256"] = support.digest("other-b1-asset")
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("B1 initialisation identity", caught.exception.detail)

    def test_different_model_architecture_identity_is_refused(self):
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["b1_identity"]["unet_config_sha256"] = support.digest("other-unet")
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("B1 initialisation identity", caught.exception.detail)
        views = copy.deepcopy(self.views)
        digest = support.digest("other-frozen-buffer")
        for key in views[44]["parsed"]["frozen_state"]["persistent_buffer_digests_by_update"]:
            views[44]["parsed"]["frozen_state"]["persistent_buffer_digests_by_update"][key] = digest
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("model architecture identity", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["frozen_state"]["encdec_requires_grad_false"] = False
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("model architecture identity", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["repository"]["rnagenesis_commit"] = "c" * 40
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("model architecture identity", caught.exception.detail)

    def test_different_schedule_or_non_seed_protocol_is_refused(self):
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["schedule"]["applied_learning_rate_trace_sha256"] = support.digest("other-schedule")
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("learning-rate schedule", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["optimizer"]["learning_rate"] = "1e-4"
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("non-seed training protocol", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["accounting"]["physical_microbatch"] = 4
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("non-seed training protocol", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["post_schedule_position"]["multiplier"] = "1"
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("learning-rate schedule", caught.exception.detail)

    def test_different_train_or_validation_identity_is_refused(self):
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["data_roles"]["train_text"]["observed_sha256"] = support.digest("other-train")
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("TRAIN identity", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["data_roles"]["validation_csv"]["observed_sha256"] = support.digest("other-validation")
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("VALIDATION identity", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["validation_artifacts"]["noise_sha256"] = support.digest("other-noise")
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("validation artifact identities", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["rng"]["validation_draw_seed"] = 2
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("validation draw seed", caught.exception.detail)

    def test_other_sealed_scientific_fields_are_refused(self):
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["experiment_id"] = "D1_other"
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("sealed training implementation and protocol", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["deviations"] = list(views[44]["parsed"]["deviations"]) + [{"id": "unapproved"}]
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("non-seed training protocol", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["initialisation_isolation"]["m6_checkpoint_loaded"] = True
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("B1 initialisation identity", caught.exception.detail)
        views = copy.deepcopy(self.views)
        views[44]["parsed"]["schema_version"] = "m7-replicate-config-2"
        with self.assertRaises(M7Error) as caught:
            selection._assert_cross_seed_consistency(views)
        self.assertIn("sealed training implementation and protocol", caught.exception.detail)


def digest_of(text):
    return support.digest(text)


if __name__ == "__main__":
    unittest.main()

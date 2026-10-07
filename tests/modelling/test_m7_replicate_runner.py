"""CPU/mock tests for the inactive M7 replicate runner.

The real worker and launcher run over a tiny CPU stand-in. No biological corpus,
model weight, accepted run directory, or GPU is opened. Torch is used only for
tiny CPU tensors.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import unittest
from unittest import mock

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

ROOT = "/home/laura/rnagenesis-aptamer-mres"
SUPPORT_PATH = os.path.join(ROOT, "tests/modelling/m7_support.py")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


support = load_module("m7_support_for_runner_tests", SUPPORT_PATH)
torch = support.torch
runner = support.runner
contract = support.contract
common = support.common
m6 = support.m6
M7Error = common.M7Error
RNA_MESSAGE = support.RNA_MESSAGE


def tearDownModule():
    support.cleanup_cache()


def failure_record(directory):
    with open(os.path.join(directory, common.FAILURE_RECORD_NAME), "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


class SuccessfulReplicateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run43 = support.successful_run(43)
        cls.run44 = support.successful_run(44)

    def test_five_epochs_105_updates_and_a_ten_update_warmup(self):
        manifest = self.run43["manifest"]
        stack = self.run43["stack"]
        self.assertTrue(contract.validate_replicate_manifest(manifest))
        self.assertEqual(manifest["accounting"]["epochs"], 5)
        self.assertEqual(manifest["accounting"]["total_optimizer_updates"], 105)
        self.assertEqual(len(manifest["train_update_observations"]), 105)
        self.assertEqual(stack.training_microbatches, 420)
        self.assertEqual(len(stack.optimizer_steps), 105)
        trace = contract.applied_learning_rate_trace()
        self.assertEqual(tuple(stack.optimizer_steps), trace)
        self.assertTrue(all(value > 0.0 for value in stack.optimizer_steps))
        base = contract.BASE_LEARNING_RATE
        self.assertEqual(stack.optimizer_steps[0], base * 0.1)
        self.assertEqual(stack.optimizer_steps[9], base)
        self.assertEqual(manifest["schedule"]["warmup_updates"], 10)
        self.assertEqual(manifest["schedule"]["update_1_multiplier"], "0.1")
        self.assertEqual(manifest["schedule"]["applied_learning_rate_trace_sha256"], contract.APPLIED_LEARNING_RATE_TRACE_SHA256)
        self.assertEqual(manifest["applied_learning_rate_trace"], contract.trace_strings())
        self.assertEqual([row["learning_rate"] for row in manifest["train_update_observations"]], contract.trace_strings())
        self.assertEqual(manifest["post_schedule_position"]["position"], 106)
        self.assertIs(manifest["post_schedule_position"]["applied_to_optimizer"], False)
        self.assertEqual([row["update"] for row in manifest["validation_observations"]], [0, 21, 42, 63, 84, 105])
        self.assertEqual(len(stack.validation_flags), 6 * 380)
        self.assertTrue(all(enabled is False and training is False for enabled, training in stack.validation_flags))

    def test_exact_per_epoch_accumulation_windows_and_example_weights(self):
        stack = self.run43["stack"]
        batches = stack.train_batches
        self.assertEqual(len(batches), 5 * 84)
        for epoch in range(5):
            sizes = [len(batch) for batch in batches[epoch * 84:(epoch + 1) * 84]]
            self.assertEqual(sizes[-4:], [8, 8, 8, 5])
            self.assertEqual(sizes[:-4], [8] * 80)
            self.assertEqual(sum(sizes), 669)
            records = sorted(value for batch in batches[epoch * 84:(epoch + 1) * 84] for value in batch)
            self.assertEqual(records, list(range(669)))
        ratios = [applied / raw for applied, raw in zip(stack.backward_values, stack.raw_losses)]
        self.assertEqual(len(ratios), 420)
        for update in range(105):
            window = ratios[update * 4:(update + 1) * 4]
            self.assertAlmostEqual(sum(window), 1.0, places=5)
            if update % 21 == 20:
                for observed, expected in zip(window, (8 / 29.0, 8 / 29.0, 8 / 29.0, 5 / 29.0)):
                    self.assertAlmostEqual(observed, expected, places=5)
            else:
                for observed in window:
                    self.assertAlmostEqual(observed, 0.25, places=5)
        accounting = self.run43["manifest"]["accounting"]
        self.assertEqual((accounting["microbatches_per_epoch"], accounting["optimizer_updates_per_epoch"]), (84, 21))
        self.assertEqual(accounting["final_window_microbatch_sizes"], [8, 8, 8, 5])
        self.assertEqual(accounting["final_window_examples"], 29)

    def test_a_fresh_permutation_is_drawn_every_epoch(self):
        for seed, run in ((43, self.run43), (44, self.run44)):
            generator = torch.Generator(device="cpu")
            generator.manual_seed(seed)
            expected = [torch.randperm(669, generator=generator).tolist() for _ in range(5)]
            batches = run["stack"].train_batches
            for epoch in range(5):
                observed = [value for batch in batches[epoch * 84:(epoch + 1) * 84] for value in batch]
                self.assertEqual(observed, expected[epoch], (seed, epoch))
            digests = [item["permutation_digest"] for item in run["manifest"]["epoch_plan"]]
            self.assertEqual(digests, [contract.permutation_digest(order) for order in expected])
            self.assertEqual(len(set(digests)), 5)
        self.assertNotEqual(
            [item["permutation_digest"] for item in self.run43["manifest"]["epoch_plan"]],
            [item["permutation_digest"] for item in self.run44["manifest"]["epoch_plan"]],
        )

    def test_epoch_plan_boundaries(self):
        plan = self.run43["manifest"]["epoch_plan"]
        self.assertEqual([(item["first_update"], item["last_update"]) for item in plan], [(1, 21), (22, 42), (43, 63), (64, 84), (85, 105)])
        self.assertEqual([row["epoch"] for row in self.run43["manifest"]["train_update_observations"]][::21], [1, 2, 3, 4, 5])

    def test_one_checkpoint_per_epoch_is_saved_reloaded_and_proved(self):
        manifest = self.run43["manifest"]
        directory = self.run43["directory"]
        commit = manifest["authorisation"]["executing_implementation_commit"]
        names = contract.expected_checkpoint_names(43, commit)
        self.assertEqual([item["directory_name"] for item in manifest["checkpoints"]], names)
        weights = set()
        for item in manifest["checkpoints"]:
            path = os.path.join(directory, item["directory_name"])
            tree = common.observe_checkpoint_tree_strict(path, directory)
            self.assertEqual(sorted(tree), sorted(common.CHECKPOINT_MEMBERS))
            for member in common.CHECKPOINT_MEMBERS:
                self.assertEqual(common.stream_sha256(os.path.join(path, member), require_single_link=True), item["saved_hashes"][member])
            self.assertEqual(item["weight_sha256"], item["saved_hashes"][common.WEIGHT_MEMBER])
            weights.add(item["weight_sha256"])
            comparison = item["state_comparison"]
            self.assertIs(comparison["complete_state_equal"], True)
            self.assertIs(comparison["includes_persistent_buffers"], True)
            self.assertEqual(comparison["mismatched_parameter_count"], 0)
            for name in ("w1", "w2", "w3", "w4", "scale", "index"):
                self.assertIn(name, comparison["entry_digests"])
            self.assertIs(item["resume_supported"], False)
            self.assertIs(item["weight_reload_is_training_resume"], False)
            self.assertEqual(item["state_scope"], "parameters_and_persistent_buffers")
            self.assertNotEqual(item["original_object_id"], item["reloaded_object_id"])
            self.assertEqual(
                item["inventory"],
                {
                    "all_leaf_link_counts_one": True,
                    "all_regular_non_symlink_files": True,
                    "ancestry_symlink_free": True,
                    "member_count": 4,
                    "same_device": True,
                    "tree_unchanged_across_hash_and_reload": True,
                },
            )
        self.assertEqual(len(weights), 5)
        self.assertTrue(weights.isdisjoint(common.M6_FORBIDDEN_WEIGHT_SHA256))
        top = sorted(os.listdir(directory))
        self.assertEqual([name for name in top if name.startswith("D1_generic")], names)

    def test_validation_ranking_is_sealed_and_excludes_update_zero(self):
        manifest = self.run43["manifest"]
        ranking = manifest["validation_ranking"]
        self.assertIs(ranking["excludes_update_0"], True)
        self.assertEqual(sorted(item["epoch"] for item in ranking["ranked_candidates"]), [1, 2, 3, 4, 5])
        values = {row["epoch"]: row["aggregate_mse"] for row in manifest["validation_observations"] if row["candidate"]}
        self.assertEqual([item["epoch"] for item in ranking["ranked_candidates"]], common.rank_validation_candidates(values))
        zero = [row for row in manifest["validation_observations"] if row["update"] == 0][0]
        self.assertEqual((zero["candidate"], zero["epoch"]), (False, None))

    def test_b1_initialisation_is_fresh_and_identical_for_both_seeds(self):
        first = self.run43["manifest"]["b1_identity"]
        second = self.run44["manifest"]["b1_identity"]
        for key in ("initial_state_aggregate_digest", "initial_state_parameter_names_sha256", "initial_state_entry_count", "weight_sha256", "unet_config_sha256"):
            self.assertEqual(first[key], second[key], key)
        self.assertEqual(first["weight_sha256"], m6.B1_WEIGHT_SHA256)
        for run in (self.run43, self.run44):
            self.assertEqual(len(run["stack"].denoisers), 1)
            isolation = run["manifest"]["initialisation_isolation"]
            self.assertIs(isolation["b1_loaded_fresh_for_this_seed"], True)
            self.assertIs(isolation["cross_seed_state_reused"], False)
            self.assertIs(isolation["m6_checkpoint_loaded"], False)
            self.assertEqual(isolation["forbidden_weight_sha256"], sorted(common.M6_FORBIDDEN_WEIGHT_SHA256))
        self.assertIsNot(self.run43["stack"].denoisers[0], self.run44["stack"].denoisers[0])
        self.assertNotEqual(self.run43["manifest"]["checkpoints"][0]["weight_sha256"], self.run44["manifest"]["checkpoints"][0]["weight_sha256"])
        self.assertEqual(self.run43["manifest"]["rng"]["training_seed"], 43)
        self.assertEqual(self.run44["manifest"]["rng"]["training_seed"], 44)
        self.assertEqual(self.run43["manifest"]["rng"]["validation_draw_seed"], 1)

    def test_cross_seed_model_state_would_change_the_recorded_initial_digest(self):
        harness = support.cached_harness()
        trained = self.run43["stack"].denoisers[0]
        self.assertNotEqual(
            runner.initial_state_digest(trained)["initial_state_aggregate_digest"],
            self.run44["manifest"]["b1_identity"]["initial_state_aggregate_digest"],
        )
        self.assertEqual(
            runner.initial_state_digest(support.TinyDenoiser())["initial_state_aggregate_digest"],
            self.run44["manifest"]["b1_identity"]["initial_state_aggregate_digest"],
        )
        del harness

    def test_manifest_is_canonical_closed_and_has_no_sequence_or_selection_evidence(self):
        for run in (self.run43, self.run44):
            self.assertEqual(common.canonical_json(run["manifest"]), run["blob"])
            manifest = run["manifest"]
            self.assertTrue(common.reject_sequence_text(manifest))
            for key, _value in common.walk(manifest):
                folded = str(key).casefold()
                for fragment in ("select", "guardrail", "eligib", "ensemble", "best_epoch", "winner"):
                    self.assertNotIn(fragment, folded)
            self.assertEqual(manifest["closure"], contract.CLOSURE)
            self.assertIs(manifest["closure"]["m7_complete"], False)
            self.assertIs(manifest["closure"]["cross_seed_claim"], False)
            self.assertIs(manifest["closure"]["human_gate_required"], True)
            self.assertEqual(manifest["ref_eval_access"]["ref_opened"], False)
            self.assertEqual(manifest["ref_eval_access"]["eval_opened"], False)
            self.assertNotIn("input_ids", run["blob"].decode("utf-8"))
            self.assertNotIn("optimizer_moments", run["blob"].decode("utf-8").replace("optimizer_moments_saved", ""))

    def test_environment_gpu_free_space_and_timing_evidence(self):
        manifest = self.run43["manifest"]
        self.assertIs(manifest["environment"]["allow_listed_child_environment"], True)
        self.assertEqual(manifest["environment"]["stray_environment_names"], 0)
        self.assertEqual(manifest["gpu"]["logical_device"], "cuda:0")
        self.assertEqual(manifest["gpu"]["device_count"], 1)
        self.assertTrue(manifest["free_space"]["sufficient"])
        self.assertEqual(manifest["free_space"]["checkpoint_count"], 5)
        self.assertEqual(len(manifest["timing"]["training_update_seconds"]), 105)
        self.assertGreater(float(manifest["timing"]["end_to_end_seconds"]), float(manifest["timing"]["training_seconds"]))

    def test_consumption_record_and_isolated_directories_remain(self):
        directory = self.run43["directory"]
        with open(os.path.join(directory, common.CONSUMPTION_RECORD_NAME), "rb") as handle:
            record = json.loads(handle.read().decode("utf-8"))
        self.assertEqual((record["seed"], record["reuse_permitted"]), (43, False))
        self.assertFalse(os.path.exists(os.path.join(directory, common.FAILURE_RECORD_NAME)))
        for name in common.ISOLATED_DIRECTORIES:
            self.assertTrue(os.path.isdir(os.path.join(directory, name)))
        self.assertFalse(any(name.endswith(".partial") for name in os.listdir(directory)))


class ManifestValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.replicate_run = support.successful_run(43)

    def fresh(self):
        return copy.deepcopy(self.replicate_run["manifest"])

    def test_the_ld_library_path_record_is_required_and_consistent(self):
        self.assertEqual(self.fresh()["environment"]["ld_library_path"], common.unbound_ld_library_path_record())
        for mutate in (
            lambda m: m["environment"].pop("ld_library_path"),
            lambda m: m["environment"].update(ld_library_path={"bound": True, "passed_to_child": True, "sha256": None}),
            lambda m: m["environment"].update(ld_library_path={"bound": False, "passed_to_child": True, "sha256": None}),
            lambda m: m["environment"].update(ld_library_path={"bound": False, "passed_to_child": False, "sha256": "0" * 64}),
            lambda m: m["environment"].update(ld_library_path="/home/laura/lib"),
        ):
            manifest = self.fresh()
            mutate(manifest)
            with self.assertRaises(M7Error):
                contract.validate_replicate_manifest(manifest)

    def test_mutated_manifests_are_refused(self):
        def zero_lr(m):
            m["train_update_observations"][4]["learning_rate"] = "0"

        def drop_row(m):
            m["train_update_observations"].pop()

        def four_epochs(m):
            m["epoch_plan"].pop()

        def duplicate_permutation(m):
            m["epoch_plan"][1]["permutation_digest"] = m["epoch_plan"][0]["permutation_digest"]

        def update_zero_candidate(m):
            m["validation_observations"][0]["candidate"] = True

        def tamper_ranking(m):
            ranked = m["validation_ranking"]["ranked_candidates"]
            ranked[0], ranked[1] = ranked[1], ranked[0]

        def ref_opened(m):
            m["ref_eval_access"]["ref_opened"] = True

        def forbidden_weight(m):
            weight = sorted(common.M6_FORBIDDEN_WEIGHT_SHA256)[0]
            m["checkpoints"][0]["saved_hashes"][common.WEIGHT_MEMBER] = weight
            m["checkpoints"][0]["weight_sha256"] = weight

        def duplicate_weight(m):
            m["checkpoints"][1]["saved_hashes"][common.WEIGHT_MEMBER] = m["checkpoints"][0]["weight_sha256"]
            m["checkpoints"][1]["weight_sha256"] = m["checkpoints"][0]["weight_sha256"]

        def wrong_seed_name(m):
            m["checkpoints"][0]["directory_name"] = m["checkpoints"][0]["directory_name"].replace("seed-43", "seed-44")

        def not_single_link(m):
            m["checkpoints"][2]["inventory"]["all_leaf_link_counts_one"] = False

        def no_buffers(m):
            m["checkpoints"][2]["state_comparison"]["includes_persistent_buffers"] = False

        def m6_initialisation(m):
            m["initialisation_isolation"]["m6_checkpoint_loaded"] = True

        def stray_environment(m):
            m["environment"]["stray_environment_names"] = 1

        def closure(m):
            m["closure"]["m7_complete"] = True

        def seed_mismatch(m):
            m["rng"]["training_seed"] = 44

        def wrong_trace(m):
            m["applied_learning_rate_trace"][0] = m["applied_learning_rate_trace"][1]

        def applied_post(m):
            m["post_schedule_position"]["applied_to_optimizer"] = True

        def free_space(m):
            m["free_space"]["sufficient"] = False

        def missing_digest(m):
            m["b1_identity"]["initial_state_aggregate_digest"] = "x"

        def extra_key(m):
            m["unexpected"] = 1

        def sequence(m):
            m["warnings"] = ["ACGUACGUACGU"]

        def no_denoiser_change(m):
            m["train_update_observations"][7]["denoiser_change"]["value_after"] = m["train_update_observations"][7]["denoiser_change"]["value_before"]

        for mutate in (
            zero_lr, drop_row, four_epochs, duplicate_permutation, update_zero_candidate, tamper_ranking, ref_opened, forbidden_weight,
            duplicate_weight, wrong_seed_name, not_single_link, no_buffers, m6_initialisation, stray_environment, closure, seed_mismatch,
            wrong_trace, applied_post, free_space, missing_digest, extra_key, sequence, no_denoiser_change,
        ):
            manifest = self.fresh()
            mutate(manifest)
            with self.assertRaises(M7Error, msg=mutate.__name__):
                contract.validate_replicate_manifest(manifest)

    def test_selection_and_guardrail_evidence_cannot_enter_a_replicate_manifest(self):
        for key in ("selected_checkpoint", "selected_epoch", "guardrail_results", "eligible", "ensemble_hash", "best_epoch", "winner_seed", "cross_seed_selection"):
            manifest = self.fresh()
            manifest[key] = 1
            with self.assertRaises(M7Error, msg=key):
                contract.validate_replicate_manifest(manifest)
            manifest = self.fresh()
            manifest["validation_ranking"][key] = 1
            with self.assertRaises(M7Error, msg=key):
                contract.validate_replicate_manifest(manifest)

    def test_binding_to_the_entry_is_enforced(self):
        manifest = self.fresh()
        authorisation = manifest["authorisation"]
        binding = {key: authorisation[key] for key in ("authorisation_id", "authorization_commit", "authorization_parent_commit", "executing_implementation_commit", "seed")}
        self.assertTrue(contract.validate_replicate_manifest(manifest, binding))
        for key, value in (("seed", 44), ("authorisation_id", "m7_other_seed43"), ("authorization_commit", "c" * 40)):
            with self.assertRaises(M7Error):
                contract.validate_replicate_manifest(manifest, dict(binding, **{key: value}))


class FailureHandlingTests(unittest.TestCase):
    def setUp(self):
        self.harness = support.Harness()
        self.addCleanup(self.harness.close)

    def test_mid_training_failure_records_seed_epoch_update_substage_and_partial_state(self):
        stack = self.harness.make_stack(43, fail_microbatch=178)
        directory, error = self.harness.run_worker(43, stack)
        self.assertIsInstance(error, M7Error)
        record = failure_record(directory)
        self.assertEqual(record["code"], "unexpected_runtime_failure")
        self.assertEqual((record["seed"], record["epoch"], record["update"], record["microbatch"], record["stage"]), (43, 3, 45, 2, "microbatch"))
        self.assertEqual(record["retained_checkpoint_epochs"], [1, 2])
        self.assertEqual(record["partial_checkpoint"]["state"], "verified")
        self.assertEqual(record["partial_checkpoint"]["epoch"], 2)
        self.assertEqual(record["entry_kind"], "replicate")
        self.assertIsNone(record["candidate"])
        self.assertNotIn(RNA_MESSAGE, json.dumps(record))
        self.assertIn("exception_class=RuntimeError", record["detail"])
        self.assertFalse(os.path.exists(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)))
        self.assertTrue(os.path.isfile(os.path.join(directory, common.CONSUMPTION_RECORD_NAME)))
        self.assertIs(record["resumable"], False)
        self.assertIs(record["m7_complete"], False)

    def test_keyboard_interrupt_and_system_exit_are_recorded_and_propagate(self):
        for exception, expected in ((KeyboardInterrupt(), KeyboardInterrupt), (SystemExit(3), SystemExit)):
            harness = support.Harness()
            self.addCleanup(harness.close)
            stack = harness.make_stack(43, fail_microbatch=5, fail_exception=exception)
            directory, error = harness.run_worker(43, stack)
            self.assertIs(error, exception)
            self.assertIsInstance(error, expected)
            record = failure_record(directory)
            self.assertEqual(record["code"], "interrupted")
            self.assertEqual((record["seed"], record["epoch"], record["stage"]), (43, 1, "microbatch"))
            self.assertEqual(record["update"], 2)
            self.assertFalse(os.path.exists(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)))

    def test_failure_record_writer_failure_reports_the_secondary_failure(self):
        stack = self.harness.make_stack(43, fail_microbatch=3)
        entry, directory, env = self.harness.consume(43)
        runner.reset_process_claim_for_tests()
        with self.harness.patched(env), mock.patch.object(common, "write_atomic_json", side_effect=OSError("cannot write")):
            with self.assertRaises(M7Error) as caught:
                runner.worker_main(
                    directory,
                    entry["authorisation_id"],
                    config_loader=lambda: self.harness.config,
                    observation_loader=lambda config, selected: self.harness.observation(43, consumed=True),
                    stack_loader=lambda authorised: stack,
                    interpreter_observer=self.harness.interpreter_observer(43),
                )
        self.assertEqual(caught.exception.code, "unexpected_runtime_failure")
        self.assertEqual(caught.exception.secondary_failure["class"], "OSError")
        self.assertFalse(os.path.exists(os.path.join(directory, common.FAILURE_RECORD_NAME)))
        self.assertIn("secondary_failure=", common.format_error_line(caught.exception))

    def test_a_seed_failure_leaves_the_other_seed_unconsumed(self):
        stack = self.harness.make_stack(43, fail_microbatch=2)
        directory, error = self.harness.run_worker(43, stack)
        self.assertIsNotNone(error)
        self.assertFalse(os.path.lexists(self.harness.entries[44]["output_directory"]))
        stack44 = self.harness.make_stack(44)
        directory44, error44 = self.harness.run_worker(44, stack44)
        self.assertIsNone(error44)
        self.assertTrue(os.path.isfile(os.path.join(directory44, contract.SUCCESS_MANIFEST_NAME)))
        self.assertFalse(os.path.exists(os.path.join(directory44, common.FAILURE_RECORD_NAME)))

    def test_a_second_replicate_in_one_process_is_refused(self):
        stack = self.harness.make_stack(43)
        directory, error = self.harness.run_worker(43, stack)
        self.assertIsNone(error)
        self.assertEqual(runner._PROCESS_CLAIM["seed"], 43)
        entry, directory44, env = self.harness.consume(44)
        with self.harness.patched(env):
            with self.assertRaises(M7Error) as caught:
                runner.worker_main(
                    directory44,
                    entry["authorisation_id"],
                    config_loader=lambda: self.harness.config,
                    observation_loader=lambda config, selected: self.harness.observation(44, consumed=True),
                    stack_loader=lambda authorised: self.harness.make_stack(44),
                    interpreter_observer=self.harness.interpreter_observer(44),
                )
        self.assertEqual(caught.exception.code, "cross_seed_state")
        self.assertEqual(failure_record(directory44)["code"], "cross_seed_state")
        runner.reset_process_claim_for_tests()
        with self.assertRaises(M7Error):
            runner.claim_process_for_seed(42)
        runner.claim_process_for_seed(44)
        with self.assertRaises(M7Error):
            runner.claim_process_for_seed(44)
        runner.reset_process_claim_for_tests()

    def test_worker_refuses_a_directory_that_is_not_the_bound_output_or_lacks_a_record(self):
        entry, directory, env = self.harness.consume(43)
        os.remove(os.path.join(directory, common.CONSUMPTION_RECORD_NAME))
        runner.reset_process_claim_for_tests()
        with self.harness.patched(env):
            with self.assertRaises(M7Error) as caught:
                runner.worker_main(
                    directory,
                    entry["authorisation_id"],
                    config_loader=lambda: self.harness.config,
                    observation_loader=lambda config, selected: self.harness.observation(43, consumed=True),
                    stack_loader=lambda authorised: self.harness.make_stack(43),
                    interpreter_observer=self.harness.interpreter_observer(43),
                )
        self.assertEqual(caught.exception.code, "authorization_reuse")


class CheckpointFailureTests(unittest.TestCase):
    def setUp(self):
        self.harness = support.Harness()
        self.addCleanup(self.harness.close)

    def run_failing(self, harness=None, **faults):
        harness = self.harness if harness is None else harness
        stack = harness.make_stack(43, **faults)
        directory, error = harness.run_worker(43, stack)
        self.assertIsInstance(error, M7Error)
        return failure_record(directory), directory

    def test_m6_weight_hash_is_forbidden_as_a_saved_checkpoint(self):
        import hashlib

        fixture = {hashlib.sha256(b"FORBIDDEN-FIXTURE").hexdigest(): "m6_update_21"}
        with mock.patch.dict(common.M6_FORBIDDEN_WEIGHT_SHA256, fixture):
            harness = support.Harness()
            self.addCleanup(harness.close)
            record, directory = self.run_failing(harness, save_mode="constant_weight")
        self.assertEqual(record["code"], "m6_checkpoint_forbidden")
        self.assertEqual((record["seed"], record["epoch"], record["update"], record["stage"]), (43, 1, 21, "checkpoint_hash"))
        self.assertEqual(record["partial_checkpoint"]["state"], "saved_unverified")
        self.assertEqual(record["retained_checkpoint_epochs"], [])

    def test_state_and_buffer_mismatch_is_caught_at_the_state_proof(self):
        for mode in ("mutate_buffer", "mutate_parameter"):
            harness = support.Harness()
            self.addCleanup(harness.close)
            stack = harness.make_stack(43, reload_mode=mode)
            directory, error = harness.run_worker(43, stack)
            record = failure_record(directory)
            self.assertEqual(record["code"], "checkpoint_save_reload_incompatibility", mode)
            self.assertEqual((record["stage"], record["epoch"], record["update"]), ("checkpoint_state_proof", 1, 21), mode)
            self.assertEqual(record["partial_checkpoint"]["state"], "saved_unverified")

    def test_configuration_mismatch_is_caught_before_the_state_comparison(self):
        record, directory = self.run_failing(reload_mode="bad_config")
        self.assertEqual(record["code"], "checkpoint_save_reload_incompatibility")
        self.assertEqual(record["stage"], "checkpoint_config_proof")

    def test_reload_that_reuses_the_training_object_is_refused(self):
        record, directory = self.run_failing(reload_mode="same_object")
        self.assertEqual(record["code"], "checkpoint_save_reload_incompatibility")
        self.assertEqual(record["stage"], "checkpoint_reload")

    def test_hard_link_extra_member_and_symlink_are_refused(self):
        expected = {
            "hardlink": ("checkpoint_ancestry_unsafe", "checkpoint_inventory"),
            "extra_member": ("checkpoint_save_reload_incompatibility", "checkpoint_inventory"),
            "symlink_leaf": ("checkpoint_save_reload_incompatibility", "checkpoint_flush"),
        }
        for mode, (code, stage) in expected.items():
            harness = support.Harness()
            self.addCleanup(harness.close)
            stack = harness.make_stack(43, save_mode=mode)
            directory, error = harness.run_worker(43, stack)
            record = failure_record(directory)
            self.assertEqual(record["code"], code, mode)
            self.assertEqual(record["stage"], stage, mode)
            self.assertEqual(record["partial_checkpoint"]["state"], "saved_unverified")

    def test_an_existing_checkpoint_directory_is_never_overwritten(self):
        entry, directory, env = self.harness.consume(43)
        name = contract.checkpoint_child_name(43, 1, entry["executing_implementation_commit"])
        os.mkdir(os.path.join(directory, name))
        stack = self.harness.make_stack(43)
        entry_for_run = self.harness.validated(43) if False else entry
        progress = common.new_progress(43, "replicate")
        runner.reset_process_claim_for_tests()
        with self.harness.patched(env):
            with self.assertRaises(M7Error) as caught:
                runner.run_authorised_replicate(entry_for_run, stack, directory, progress=progress)
        self.assertEqual(caught.exception.code, "checkpoint_overwrite_risk")
        self.assertEqual(os.listdir(os.path.join(directory, name)), [])


class PreOpenGateTests(unittest.TestCase):
    """Identity, environment, free space and path gates all close before any biological open."""

    def setUp(self):
        self.harness = support.Harness()
        self.addCleanup(self.harness.close)

    def run_direct(self, **faults):
        stack = self.harness.make_stack(43, **faults)
        manifest, progress, error, directory = self.harness.run_direct(43, stack, extra_env=faults.pop("extra_env", None))
        return stack, manifest, progress, error

    def test_gpu_identity_mismatches_are_refused_before_any_open(self):
        for changes in (
            {"uuid": "GPU-00000000-0000-0000-0000-000000000000"},
            {"pci_bus": "00000000:41:00.0"},
            {"logical_device": "cuda:1"},
            {"device_count": 2},
            {"cuda_visible_devices": "0"},
            {"physical_index": 0},
            {"source": "guess"},
        ):
            harness = support.Harness()
            self.addCleanup(harness.close)
            stack = harness.make_stack(43, gpu=changes)
            manifest, progress, error, directory = harness.run_direct(43, stack)
            self.assertIsInstance(error, M7Error, changes)
            self.assertEqual(error.code, "identity_mismatch", changes)
            self.assertEqual(harness.verify_calls, [], changes)
            self.assertIsNone(manifest)

    def test_free_space_refusal_comes_before_any_open(self):
        stack = self.harness.make_stack(43, available_bytes=4096)
        manifest, progress, error, directory = self.harness.run_direct(43, stack)
        self.assertEqual(error.code, "insufficient_free_space")
        self.assertEqual(progress["stage"], "free_space")
        self.assertEqual(self.harness.verify_calls, [])

    def test_stray_environment_variables_are_refused_before_any_open(self):
        for extra in ({"PYTHONPATH": "/x"}, {"GIT_DIR": "/x"}, {"HF_TOKEN": "x"}, {"DISPLAY": ":0"}):
            harness = support.Harness()
            self.addCleanup(harness.close)
            stack = harness.make_stack(43)
            manifest, progress, error, directory = harness.run_direct(43, stack, extra_env=extra)
            self.assertEqual(error.code, "environment_rejected", extra)
            self.assertEqual(harness.verify_calls, [])

    def test_ref_and_eval_paths_are_refused_before_any_open_in_every_case(self):
        base = common.m6_contract()
        cases = (
            ("train_text_path", base.FUTURE_TRAIN_TEXT_PATH.replace("corpus_final.txt", "REF.csv")),
            ("train_text_path", "/home/laura/rnagenesis-mres-data/development/Eval.CSV"),
            ("train_text_path", "/home/laura/rnagenesis-mres-data/final/EVAL/corpus_final.txt"),
            ("validation_csv_path", "/home/laura/rnagenesis-mres-data/development/ref.csv"),
            ("validation_csv_path", "/home/laura/rnagenesis-mres-data/development/eVaL.csv"),
            ("validation_artifact_directory", base.ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY + "/EVAL"),
        )
        for key, path in cases:
            harness = support.Harness()
            self.addCleanup(harness.close)
            authorised = harness.validated(43)
            authorised.payload[key] = path
            stack = harness.make_stack(43)
            manifest, progress, error, directory = harness.run_direct(43, stack, entry=authorised)
            self.assertIsInstance(error, M7Error, path)
            self.assertEqual(error.code, "ref_or_eval_access", path)
            self.assertEqual(harness.verify_calls, [], path)
            self.assertEqual(harness.artifact_calls, [], path)

    def test_sibling_evidence_and_wrong_role_paths_are_refused_before_any_open(self):
        sibling = common.RUN_ROOT + "/m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6/corpus_final.txt"
        for key, path in (("train_text_path", sibling), ("validation_artifact_directory", common.RUN_ROOT + "/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1")):
            harness = support.Harness()
            self.addCleanup(harness.close)
            authorised = harness.validated(43)
            authorised.payload[key] = path
            manifest, progress, error, directory = harness.run_direct(43, harness.make_stack(43), entry=authorised)
            self.assertEqual(error.code, "sibling_evidence_access", path)
            self.assertEqual(harness.verify_calls, [])
        harness = support.Harness()
        self.addCleanup(harness.close)
        authorised = harness.validated(43)
        authorised.payload["train_text_path"] = "/home/laura/rnagenesis-mres-data/development/other.txt"
        manifest, progress, error, directory = harness.run_direct(43, harness.make_stack(43), entry=authorised)
        self.assertEqual(error.code, "unexpected_biological_path_or_role")
        self.assertEqual(harness.verify_calls, [])

    def test_unexpected_seed_is_refused_by_the_run_function(self):
        for seed in (1, 42, 45):
            authorised = self.harness.validated(43)
            authorised.payload["seed"] = seed
            with self.assertRaises(M7Error) as caught:
                runner.run_authorised_replicate(authorised, self.harness.make_stack(43), self.harness.temp)
            self.assertEqual(caught.exception.code, "unexpected_seed")


class LauncherTests(unittest.TestCase):
    def setUp(self):
        import yaml

        self.harness = support.Harness()
        self.addCleanup(self.harness.close)
        self.config_bytes = yaml.safe_dump(self.harness.config, sort_keys=True).encode("utf-8")
        self.parent = dict(support.SAFE_PARENT_ENVIRONMENT)
        self.seen = {"assets": 0, "python": 0}

    def launch(self, seed, spawn, environ=None, statvfs=None, config_bytes=None):
        entry = self.harness.entries[seed]
        return runner.launch_authorised_entry(
            entry["authorisation_id"],
            run_root=self.harness.temp,
            spawn=spawn,
            asset_observer=lambda: self.seen.__setitem__("assets", self.seen["assets"] + 1),
            python_observer=lambda: self.seen.__setitem__("python", self.seen["python"] + 1),
            environ=self.parent if environ is None else environ,
            config_bytes=self.config_bytes if config_bytes is None else config_bytes,
            observation=self.harness.observation(seed),
            statvfs=statvfs or (lambda path: type("S", (), {"f_bavail": 10**12, "f_frsize": 4096})()),
            interpreter_observer=self.harness.interpreter_observer(seed),
        )

    def worker_spawn(self, seed):
        """Run the real ``worker_main`` where a child process would run, with the child environment."""
        stack = self.harness.make_stack(seed)
        captured = {}

        def spawn(argv, env, cwd):
            captured.update(argv=argv, env=env, cwd=cwd)
            runner.reset_process_claim_for_tests()
            with self.harness.patched(env):
                try:
                    runner.worker_main(
                        argv[-2],
                        argv[-1],
                        config_loader=lambda: self.harness.config,
                        observation_loader=lambda config, selected: self.harness.observation(seed, consumed=True),
                        stack_loader=lambda authorised: stack,
                        interpreter_observer=self.harness.interpreter_observer(seed),
                    )
                except BaseException:
                    return type("Completed", (), {"returncode": 1})()
            return type("Completed", (), {"returncode": 0})()

        return spawn, captured

    def test_launcher_runs_one_seed_through_a_strict_environment(self):
        spawn, captured = self.worker_spawn(43)
        directory = self.launch(43, spawn)
        self.assertEqual(directory, self.harness.entries[43]["output_directory"])
        self.assertEqual(captured["argv"][0], common.PINNED_PYTHON)
        self.assertIn("-B", captured["argv"])
        self.assertEqual(captured["cwd"], common.RNAGENESIS_ROOT)
        env = captured["env"]
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "1")
        self.assertEqual(env["CUDA_DEVICE_ORDER"], "PCI_BUS_ID")
        self.assertTrue(env["HOME"].startswith(directory + os.sep))
        self.assertTrue(env["TMPDIR"].startswith(directory + os.sep))
        self.assertTrue(set(env) <= set(common.ENVIRONMENT_ALLOW_LIST) | set(common.OFFLINE_CONTROLS) | set(common.isolated_paths(directory)) | set(common.FIXED_CHILD_ENVIRONMENT_CONTROLS) | {"PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER"})
        self.assertEqual(env["PATH"], common.FIXED_CHILD_PATH)
        self.assertEqual(self.seen, {"assets": 1, "python": 1})
        self.assertFalse(os.path.lexists(self.harness.entries[44]["output_directory"]))
        with self.assertRaises(M7Error) as caught:
            self.launch(43, spawn)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertTrue(os.path.isfile(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)))
        self.assertFalse(os.path.exists(os.path.join(directory, common.FAILURE_RECORD_NAME)))

    def test_the_second_seed_is_launched_independently(self):
        spawn43, _captured = self.worker_spawn(43)
        self.launch(43, spawn43)
        spawn44, _captured = self.worker_spawn(44)
        directory = self.launch(44, spawn44)
        self.assertEqual(directory, self.harness.entries[44]["output_directory"])

    def test_nonzero_worker_exit_is_a_consumed_failure_and_the_entry_cannot_be_reused(self):
        def spawn(argv, env, cwd):
            return type("Completed", (), {"returncode": 1})()

        with self.assertRaises(M7Error) as caught:
            self.launch(43, spawn)
        self.assertEqual(caught.exception.code, "incomplete_evidence_or_manifest")
        directory = self.harness.entries[43]["output_directory"]
        record = failure_record(directory)
        self.assertEqual((record["seed"], record["stage"]), (43, "worker_launch"))
        with open(os.path.join(directory, common.FAILURE_RECORD_NAME), "rb") as handle:
            before = handle.read()
        with self.assertRaises(M7Error) as reused:
            self.launch(43, spawn)
        self.assertEqual(reused.exception.code, "authorization_reuse")
        with open(os.path.join(directory, common.FAILURE_RECORD_NAME), "rb") as handle:
            self.assertEqual(handle.read(), before)
        self.assertFalse(os.path.lexists(self.harness.entries[44]["output_directory"]))

    def test_interrupt_in_the_parent_is_recorded_and_propagates(self):
        for exception in (KeyboardInterrupt(), SystemExit(4)):
            harness_before = self.harness
            self.harness = support.Harness()
            self.addCleanup(self.harness.close)
            import yaml

            self.config_bytes = yaml.safe_dump(self.harness.config, sort_keys=True).encode("utf-8")

            def spawn(argv, env, cwd, exception=exception):
                raise exception

            with self.assertRaises(type(exception)):
                self.launch(43, spawn)
            record = failure_record(self.harness.entries[43]["output_directory"])
            self.assertEqual((record["code"], record["seed"]), ("interrupted", 43))
            self.assertEqual(record["stage"], "worker_launch")
            del harness_before

    def test_zero_exit_without_a_valid_manifest_is_a_failure(self):
        def spawn(argv, env, cwd):
            return type("Completed", (), {"returncode": 0})()

        with self.assertRaises(M7Error) as caught:
            self.launch(43, spawn)
        self.assertEqual(caught.exception.code, "incomplete_evidence_or_manifest")
        self.assertEqual(failure_record(self.harness.entries[43]["output_directory"])["stage"], "worker_success_verification")

        def spawn_wrong_seed(argv, env, cwd):
            manifest = copy.deepcopy(support.successful_run(44)["manifest"])
            common.write_atomic_json(argv[-2], contract.SUCCESS_MANIFEST_NAME, manifest)
            return type("Completed", (), {"returncode": 0})()

        harness = support.Harness()
        self.addCleanup(harness.close)
        import yaml

        self.harness = harness
        self.config_bytes = yaml.safe_dump(harness.config, sort_keys=True).encode("utf-8")
        with self.assertRaises(M7Error):
            self.launch(43, spawn_wrong_seed)
        self.assertTrue(os.path.isfile(os.path.join(harness.entries[43]["output_directory"], common.FAILURE_RECORD_NAME)))
        self.assertFalse(os.path.exists(os.path.join(harness.entries[43]["output_directory"], contract.SUCCESS_MANIFEST_NAME)))

    def test_refusals_before_consumption_create_nothing(self):
        def spawn(argv, env, cwd):
            raise AssertionError("must not start a worker")

        with self.assertRaises(M7Error) as caught:
            self.launch(43, spawn, statvfs=lambda path: type("S", (), {"f_bavail": 1, "f_frsize": 4096})())
        self.assertEqual(caught.exception.code, "insufficient_free_space")
        for extra in ({"PYTHONPATH": "/x"}, {"GIT_DIR": "/x"}, {"ANTHROPIC_API_KEY": "x"}):
            with self.assertRaises(M7Error) as caught:
                self.launch(43, spawn, environ=dict(self.parent, **extra))
            self.assertEqual(caught.exception.code, "environment_rejected", extra)
        with open(os.path.join(ROOT, "config/experiments/D1_final_replicates.yaml"), "rb") as handle:
            inactive = handle.read()
        with self.assertRaises(M7Error) as caught:
            self.launch(43, spawn, config_bytes=inactive)
        self.assertEqual(caught.exception.code, "execution_not_authorised")
        with self.assertRaises(M7Error):
            runner.launch_authorised_entry("m7_unit_seed42_gpu1", run_root=self.harness.temp, environ=self.parent, config_bytes=self.config_bytes, observation={})
        self.assertEqual(os.listdir(self.harness.temp), [])
        self.assertEqual(self.seen, {"assets": 0, "python": 0})


class LdLibraryPathLauncherTests(unittest.TestCase):
    """An authorisation-bound ``LD_LIBRARY_PATH`` is matched, passed exactly, and recorded by digest."""

    VALUE = "/home/laura/miniconda3/envs/rnagenesis-h200/lib:/usr/local/cuda/lib64"

    def build(self, ld_library_path):
        import yaml

        harness = support.Harness(ld_library_path=ld_library_path)
        self.addCleanup(harness.close)
        return harness, yaml.safe_dump(harness.config, sort_keys=True).encode("utf-8")

    def launch(self, harness, config_bytes, seed, spawn, environ):
        return runner.launch_authorised_entry(
            harness.entries[seed]["authorisation_id"],
            run_root=harness.temp,
            spawn=spawn,
            asset_observer=lambda: None,
            python_observer=lambda: None,
            environ=environ,
            config_bytes=config_bytes,
            observation=harness.observation(seed),
            statvfs=lambda path: type("S", (), {"f_bavail": 10**12, "f_frsize": 4096})(),
            interpreter_observer=harness.interpreter_observer(seed),
        )

    def worker_spawn(self, harness, seed, captured):
        stack = harness.make_stack(seed)

        def spawn(argv, env, cwd):
            captured.update(env=env)
            runner.reset_process_claim_for_tests()
            with harness.patched(env):
                try:
                    runner.worker_main(
                        argv[-2],
                        argv[-1],
                        config_loader=lambda: harness.config,
                        observation_loader=lambda config, selected: harness.observation(seed, consumed=True),
                        stack_loader=lambda authorised: stack,
                        interpreter_observer=harness.interpreter_observer(seed),
                    )
                except BaseException:
                    return type("Completed", (), {"returncode": 1})()
            return type("Completed", (), {"returncode": 0})()

        return spawn

    def test_a_matching_value_reaches_the_child_and_its_digest_is_in_the_manifest(self):
        harness, config_bytes = self.build(self.VALUE)
        captured = {}
        parent = dict(support.SAFE_PARENT_ENVIRONMENT, LD_LIBRARY_PATH=self.VALUE)
        directory = self.launch(harness, config_bytes, 43, self.worker_spawn(harness, 43, captured), parent)
        env = captured["env"]
        self.assertEqual(env["LD_LIBRARY_PATH"], self.VALUE)
        permitted = set(common.ENVIRONMENT_ALLOW_LIST) | set(common.OFFLINE_CONTROLS) | set(common.isolated_paths(directory))
        permitted |= set(common.FIXED_CHILD_ENVIRONMENT_CONTROLS) | {"LD_LIBRARY_PATH", "PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER"}
        self.assertTrue(set(env) <= permitted, sorted(set(env) - permitted))
        self.assertEqual(env["PATH"], common.FIXED_CHILD_PATH)
        with open(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME), "rb") as handle:
            manifest = json.loads(handle.read().decode("utf-8"))
        record = manifest["environment"]["ld_library_path"]
        self.assertEqual(record, {"bound": True, "passed_to_child": True, "sha256": common.ld_library_path_digest(self.VALUE)})
        self.assertNotIn(self.VALUE, json.dumps(manifest))
        self.assertEqual(manifest["environment"]["stray_environment_names"], 0)
        self.assertTrue(contract.validate_replicate_manifest(manifest, runner._binding(harness.validated(43))))

    def test_a_missing_or_mismatching_value_is_refused_before_consumption(self):
        harness, config_bytes = self.build(self.VALUE)

        def spawn(argv, env, cwd):
            raise AssertionError("must not start a worker")

        for parent in (
            dict(support.SAFE_PARENT_ENVIRONMENT),
            dict(support.SAFE_PARENT_ENVIRONMENT, LD_LIBRARY_PATH=self.VALUE + ":/extra"),
            dict(support.SAFE_PARENT_ENVIRONMENT, LD_LIBRARY_PATH="/other/lib"),
            dict(support.SAFE_PARENT_ENVIRONMENT, LD_LIBRARY_PATH=""),
        ):
            with self.assertRaises(M7Error) as caught:
                self.launch(harness, config_bytes, 43, spawn, parent)
            self.assertEqual(caught.exception.code, "environment_rejected", parent)
            self.assertNotIn(self.VALUE, str(caught.exception))
            self.assertEqual(os.listdir(harness.temp), [])

    def test_an_unbound_entry_never_passes_an_ambient_value_on(self):
        harness, config_bytes = self.build(None)
        captured = {}
        parent = dict(support.SAFE_PARENT_ENVIRONMENT, LD_LIBRARY_PATH=self.VALUE)
        directory = self.launch(harness, config_bytes, 43, self.worker_spawn(harness, 43, captured), parent)
        self.assertNotIn("LD_LIBRARY_PATH", captured["env"])
        with open(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME), "rb") as handle:
            manifest = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(manifest["environment"]["ld_library_path"], common.unbound_ld_library_path_record())

    def test_a_worker_whose_environment_lost_the_bound_value_fails_closed(self):
        harness, config_bytes = self.build(self.VALUE)
        entry, directory, env = harness.consume(43)
        self.assertEqual(env["LD_LIBRARY_PATH"], self.VALUE)
        for changed in ({key: value for key, value in env.items() if key != "LD_LIBRARY_PATH"}, dict(env, LD_LIBRARY_PATH=self.VALUE + ":/extra")):
            runner.reset_process_claim_for_tests()
            with harness.patched(changed):
                with self.assertRaises(M7Error) as caught:
                    runner.worker_main(
                        directory,
                        entry["authorisation_id"],
                        config_loader=lambda: harness.config,
                        observation_loader=lambda config, selected: harness.observation(43, consumed=True),
                        stack_loader=lambda authorised: harness.make_stack(43),
                        interpreter_observer=harness.interpreter_observer(43),
                    )
            self.assertEqual(caught.exception.code, "environment_rejected")
            os.remove(os.path.join(directory, common.FAILURE_RECORD_NAME))

    def test_the_manifest_digest_must_match_the_entry(self):
        harness, config_bytes = self.build(self.VALUE)
        parent = dict(support.SAFE_PARENT_ENVIRONMENT, LD_LIBRARY_PATH=self.VALUE)
        directory = self.launch(harness, config_bytes, 43, self.worker_spawn(harness, 43, {}), parent)
        with open(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME), "rb") as handle:
            manifest = json.loads(handle.read().decode("utf-8"))
        binding = runner._binding(harness.validated(43))
        self.assertTrue(contract.validate_replicate_manifest(manifest, binding))
        for wrong in (None, common.ld_library_path_digest("/other/lib")):
            with self.assertRaises(M7Error) as caught:
                contract.validate_replicate_manifest(manifest, dict(binding, ld_library_path_sha256=wrong))
            self.assertEqual(caught.exception.code, "environment_rejected")


class IntroducingClock(object):
    """Stand-in for ``SynchronizedClock.stamp`` introducing the pinned runtime variable."""

    def __init__(self, extra=None):
        self.extra = extra
        self.calls = 0
        self.value_before = None

    def stamp(self):
        self.calls += 1
        if self.calls == 1:
            self.value_before = os.environ.get("CUDA_MODULE_LOADING")
        os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")
        if self.extra is not None:
            name, value = self.extra
            os.environ[name] = value
        return float(self.calls)


class SilentClock(object):
    """A clock that does not repair the environment."""

    def stamp(self):
        return 1.0


class CudaModuleLoadingRuntimeTests(unittest.TestCase):
    """The second isolation check accepts the fixed control and still rejects a stray name."""

    def setUp(self):
        self.harness = support.Harness()
        self.addCleanup(self.harness.close)

    def test_a_clock_that_introduces_lazy_no_longer_fails_the_second_isolation_check(self):
        entry, directory, env = self.harness.consume(43)
        self.assertEqual(env["CUDA_MODULE_LOADING"], "LAZY")
        clock = IntroducingClock()
        stack = self.harness.make_stack(43)
        stack.clock = lambda clock=clock: clock
        progress = common.new_progress(43, "replicate")
        runner.reset_process_claim_for_tests()
        with self.harness.patched(env):
            manifest = runner.run_authorised_replicate(entry, stack, directory, progress=progress)
        self.assertEqual(clock.value_before, "LAZY")
        self.assertGreaterEqual(clock.calls, 1)
        self.assertEqual(manifest["seed"], 43)
        self.assertEqual(manifest["environment"]["stray_environment_names"], 0)
        self.assertTrue(self.harness.verify_calls)

    def test_injected_fault_missing_or_altered_values_still_fail_the_second_check(self):
        cases = (
            ("missing", SilentClock(), lambda env: env.pop("CUDA_MODULE_LOADING"), "fixed child control is missing: CUDA_MODULE_LOADING"),
            ("empty", IntroducingClock(), lambda env: env.__setitem__("CUDA_MODULE_LOADING", ""), "fixed child control is empty: CUDA_MODULE_LOADING"),
            ("case", IntroducingClock(), lambda env: env.__setitem__("CUDA_MODULE_LOADING", "lazy"), "fixed child control differs in case: CUDA_MODULE_LOADING"),
            ("alternative", IntroducingClock(), lambda env: env.__setitem__("CUDA_MODULE_LOADING", "EAGER"), "fixed child control is not the required value: CUDA_MODULE_LOADING"),
        )
        for name, clock, mutate, detail in cases:
            harness = support.Harness()
            self.addCleanup(harness.close)
            entry, directory, env = harness.consume(43)
            mutate(env)
            stack = harness.make_stack(43)
            stack.clock = lambda clock=clock: clock
            progress = common.new_progress(43, "replicate")
            runner.reset_process_claim_for_tests()
            with harness.patched(env):
                with self.assertRaises(M7Error, msg=name) as caught:
                    runner.run_authorised_replicate(entry, stack, directory, progress=progress)
            self.assertEqual(caught.exception.code, "environment_rejected", name)
            self.assertEqual(caught.exception.detail, detail, name)
            self.assertEqual(progress["stage"], "runtime_identity", name)
            self.assertEqual(harness.verify_calls, [], name)
            self.assertNotIn("EAGER", str(caught.exception), name)
            self.assertNotIn("lazy", str(caught.exception), name)

    def test_a_stray_variable_introduced_beside_the_fixed_control_is_still_rejected(self):
        entry, directory, env = self.harness.consume(43)
        secret = "clock-secret-value-not-reported"
        clock = IntroducingClock(extra=("STRAY_FROM_CLOCK", secret))
        stack = self.harness.make_stack(43)
        stack.clock = lambda clock=clock: clock
        progress = common.new_progress(43, "replicate")
        runner.reset_process_claim_for_tests()
        with self.harness.patched(env):
            with self.assertRaises(M7Error) as caught:
                runner.run_authorised_replicate(entry, stack, directory, progress=progress)
        self.assertEqual(clock.value_before, "LAZY")
        self.assertEqual(caught.exception.code, "environment_rejected")
        self.assertEqual(progress["stage"], "runtime_identity")
        self.assertEqual(caught.exception.detail, "the worker environment holds 1 names outside the allow-list: STRAY_FROM_CLOCK")
        self.assertNotIn(secret, str(caught.exception))
        self.assertEqual(self.harness.verify_calls, [])


if __name__ == "__main__":
    unittest.main()

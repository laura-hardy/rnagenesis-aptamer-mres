"""CPU/mock tests for the inactive M7 candidate-guardrail stage.

No generation, checkpoint weight, biological corpus, accepted run directory, or
GPU is used. Checkpoint trees are tiny temporary files.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

ROOT = "/home/laura/rnagenesis-aptamer-mres"
SUPPORT_PATH = os.path.join(ROOT, "tests/modelling/m7_support.py")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


support = load_module("m7_support_for_guardrail_tests", SUPPORT_PATH)
guardrails = support.guardrails
contract = support.contract
common = support.common
M7Error = common.M7Error
PARENT = "b" * 40
HEAD = "a" * 40
GPU = {"cuda_visible_devices": "1", "logical_device": "cuda:0", "pci_bus": "00000000:61:00.0", "physical_index": 1, "uuid": "GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f"}


def tearDownModule():
    support.cleanup_cache()


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hashes():
    return {path: digest(path) for path in guardrails.IMPLEMENTATION_FILE_PATHS}


def entry_for(root, seed=43, epoch=3, position=1, preceding=(), commit=PARENT, training_commit=None, ld_library_path=None):
    name = "m7_unit_seed%d_epoch%d_candidate" % (seed, epoch)
    output = root.rstrip("/") + "/" + name
    training = commit if training_commit is None else training_commit
    checkpoint = "%s/m7_unit_seed%d_gpu1/%s" % (root.rstrip("/"), seed, contract.checkpoint_child_name(seed, epoch, training))
    return {
        "activation_status": "active_unconsumed",
        "authorisation_id": name,
        "authorisation_timestamp": "2026-10-07T20:00:00+11:00",
        "authorization_parent_commit": commit,
        "candidate_epoch": epoch,
        "candidate_seed": seed,
        "candidate_update": epoch * 21,
        "checkpoint_directory": checkpoint,
        "checkpoint_member_sha256": {member: digest(member) for member in common.CHECKPOINT_MEMBERS},
        "checkpoint_relative_name": os.path.basename(checkpoint),
        "checkpoint_training_implementation_commit": training,
        "checkpoint_weight_sha256": digest(common.WEIGHT_MEMBER),
        "consumed": False,
        "cuda_visible_devices": "1",
        "evidence_directory": output,
        "executing_implementation_commit": commit,
        "expected_schedule_sha256": common.m6_contract().PAIRED_SCHEDULE_SHA256,
        "gpu_uuid": GPU["uuid"],
        "implementation_config_sha256": digest("implementation-config"),
        "implementation_file_hashes": file_hashes(),
        "interpreter": dict(support.INTERPRETER),
        "ld_library_path": ld_library_path,
        "logical_device": "cuda:0",
        "output_directory": output,
        "pci_bus": GPU["pci_bus"],
        "permitted_roles": list(guardrails.ACTIVE_ROLES),
        "phase": guardrails.ACTIVE_PHASE,
        "physical_gpu_index": 1,
        "preceding_candidates": [dict(item) for item in preceding],
        "ranking_position": position,
        "replicate_manifest_bytes": 4096,
        "replicate_manifest_path": os.path.join(os.path.dirname(checkpoint), contract.SUCCESS_MANIFEST_NAME),
        "replicate_manifest_sha256": digest("replicate"),
        "reuse_permitted": False,
        "scope": "single_use_m7_d1_candidate_guardrail_seed_%d_epoch_%d" % (seed, epoch),
        "session": {"consumption_event": contract.CONSUMPTION_EVENT, "pattern": contract.SESSION_PATTERN, "resume_permitted": False, "wall_clock_expiry": None},
        "single_use": True,
        "validation_ranking_sha256": digest("ranking"),
    }


def failed(epoch):
    return {"epoch": epoch, "manifest_sha256": digest("failed%d" % epoch), "outcome": "failed"}


class InactiveStageTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "config/experiments/D1_candidate_guardrails.yaml"), "rb") as handle:
            self.raw = handle.read()
        self.config = common.load_config_bytes(self.raw)

    def test_checked_in_configuration_is_inactive_and_refused(self):
        self.assertTrue(guardrails.assert_inactive_text(self.raw.decode("utf-8")))
        self.assertTrue(guardrails.assert_inactive_configuration(self.config))
        with self.assertRaises(M7Error) as caught:
            guardrails.reject_inactive_before_execution(self.config)
        self.assertEqual(caught.exception.code, "execution_not_authorised")
        self.assertEqual(self.config["authorisation_entries"], [])
        self.assertIs(self.config["consumable_by_executable_workflow"], False)

    def test_drift_and_activation_are_refused(self):
        for mutate in (
            lambda c: c["candidate_plan"].update(evaluation="eager"),
            lambda c: c["candidate_plan"].update(update_0_is_a_candidate=True),
            lambda c: c["diagnostic_design"].update(raw_attempts=999),
            lambda c: c["hard_guardrails"][0].update(threshold=0.5),
            lambda c: c["report_only"].update(requested_length_matching_is_a_threshold=True),
            lambda c: c["data"].update(validation_csv_access=True),
            lambda c: c["execution"].update(authorised=True),
            lambda c: c.update(authorisation_entries=[entry_for("/x")]),
            lambda c: c.update(document_status=guardrails.ACTIVE_DOCUMENT_STATUS),
            lambda c: c.update(ld_library_path="/usr/lib"),
            lambda c: c["diagnostic_design"].update(production_generation_callable_implemented_in_this_package=False),
            lambda c: c["diagnostic_design"].update(invocation_seed_base=1),
        ):
            config = copy.deepcopy(self.config)
            mutate(config)
            with self.assertRaises(M7Error):
                guardrails.assert_inactive_configuration(config)

    def test_entry_point_accepts_only_help_and_schema(self):
        path = os.path.join(ROOT, "scripts/modelling/m7_candidate_guardrails.py")
        for arguments, ok in ((["--help"], True), (["--schema"], True), ([], False), (["--seed", "43"], False), (["--epoch", "3"], False), (["--checkpoint", "/x"], False)):
            completed = subprocess.run([sys.executable, "-B", path] + arguments, capture_output=True, text=True, cwd="/tmp")
            self.assertEqual(completed.returncode == 0, ok, arguments)
        schema = json.loads(subprocess.run([sys.executable, "-B", path, "--schema"], capture_output=True, text=True, cwd="/tmp").stdout)
        self.assertEqual(schema["entry_keys"], list(guardrails.ACTIVE_ENTRY_KEYS))


class GuardrailEvaluationTests(unittest.TestCase):
    def test_thresholds_are_the_accepted_five(self):
        m6 = common.m6_contract()
        self.assertEqual(
            {rule[0]: (rule[1], rule[2]) for rule in guardrails.HARD_GUARDRAIL_RULES},
            {
                "valid_nonempty_acgu_fraction": ("minimum", m6.GUARDRAILS["valid_nonempty_acgu_fraction_min"]),
                "empty_or_unparseable_fraction": ("maximum", m6.GUARDRAILS["empty_or_unparseable_fraction_max"]),
                "unique_fraction": ("minimum", m6.GUARDRAILS["unique_fraction_min"]),
                "exact_train_match_rate": ("maximum", m6.GUARDRAILS["exact_train_match_rate_max"]),
                "largest_duplicate_share": ("maximum", m6.GUARDRAILS["largest_duplicate_share_max"]),
            },
        )
        metrics = support.load_module("m4_metrics_for_m7_tests", os.path.join(ROOT, "scripts/modelling/m4_diagnostic_metrics.py"))
        self.assertEqual(
            {key: dict(value) for key, value in metrics.GUARDRAIL_THRESHOLDS.items()},
            {rule[0]: {"comparison": rule[1], "threshold": rule[2]} for rule in guardrails.HARD_GUARDRAIL_RULES},
        )
        self.assertEqual(tuple(metrics.HARD_GUARDRAIL_IDS), tuple(rule[0] for rule in guardrails.HARD_GUARDRAIL_RULES))
        for guardrail_id, comparison, threshold in guardrails.HARD_GUARDRAIL_RULES:
            for value in (0.0, threshold - 1e-9, threshold, threshold + 1e-9, 1.0):
                ours = guardrails.guardrail_decision(guardrail_id, value)
                theirs = metrics._threshold_decision(guardrail_id, value, True)
                self.assertEqual(ours["passed"], theirs["passed"], (guardrail_id, value))
                self.assertEqual(ours["status"], theirs["status"])

    def test_all_five_must_pass(self):
        passing = guardrails.evaluate_guardrail_values(support.PASSING_VALUES)
        self.assertIs(passing["passed"], True)
        self.assertEqual(len(passing["decisions"]), 5)
        self.assertIs(passing["exact_hit_rate_is_a_threshold"], False)
        for key in support.PASSING_VALUES:
            values = dict(support.PASSING_VALUES)
            values[key] = 0.5 if key in ("valid_nonempty_acgu_fraction", "unique_fraction") else 0.5
            result = guardrails.evaluate_guardrail_values(values)
            self.assertIs(result["passed"], False, key)
            self.assertEqual([item["id"] for item in result["decisions"] if not item["passed"]], [key])

    def test_boundary_and_invalid_values(self):
        exact = dict(support.PASSING_VALUES, valid_nonempty_acgu_fraction=0.99, empty_or_unparseable_fraction=0.01, unique_fraction=0.95, exact_train_match_rate=0.01, largest_duplicate_share=0.01)
        self.assertIs(guardrails.evaluate_guardrail_values(exact)["passed"], True)
        for bad in (-0.1, 1.1, float("nan"), float("inf"), True, "0.5"):
            with self.assertRaises(M7Error):
                guardrails.evaluate_guardrail_values(dict(support.PASSING_VALUES, unique_fraction=bad))
        self.assertIs(guardrails.guardrail_decision("unique_fraction", None)["passed"], False)
        with self.assertRaises(M7Error):
            guardrails.guardrail_decision("requested_length_exact_hit_rate", 1.0)
        for bad in ({}, dict(support.PASSING_VALUES, extra=1), {key: value for key, value in support.PASSING_VALUES.items() if key != "unique_fraction"}):
            with self.assertRaises(M7Error):
                guardrails.evaluate_guardrail_values(bad)


class LazyPlanTests(unittest.TestCase):
    RANKING = [3, 5, 1, 2, 4]

    def test_states(self):
        plan = guardrails.lazy_plan(self.RANKING, [])
        self.assertEqual((plan["state"], plan["next_epoch"]), ("pending", 3))
        plan = guardrails.lazy_plan(self.RANKING, [(3, False)])
        self.assertEqual((plan["state"], plan["next_epoch"]), ("pending", 5))
        plan = guardrails.lazy_plan(self.RANKING, [(3, False), (5, True)])
        self.assertEqual((plan["state"], plan["selected_epoch"], plan["next_epoch"]), ("passed", 5, None))
        plan = guardrails.lazy_plan(self.RANKING, [(3, True)])
        self.assertEqual((plan["state"], plan["selected_epoch"]), ("passed", 3))
        plan = guardrails.lazy_plan(self.RANKING, [(3, False), (5, False), (1, False), (2, False), (4, False)])
        self.assertEqual((plan["state"], plan["selected_epoch"]), ("no_eligible_checkpoint", None))

    def test_non_prefix_and_post_pass_evaluation_are_refused(self):
        for evaluated in (
            [(5, False)],
            [(3, False), (1, False)],
            [(3, False), (5, False), (2, False)],
            [(3, True), (5, False)],
            [(3, True), (5, True)],
            [(3, False), (5, False), (1, False), (2, False), (4, False), (4, False)],
            [(3, "no")],
            [(0, False)],
        ):
            with self.assertRaises(M7Error, msg=str(evaluated)):
                guardrails.lazy_plan(self.RANKING, evaluated)
        for bad_ranking in ([1, 2, 3, 4], [0, 1, 2, 3, 4, 5], [1, 1, 2, 3, 4]):
            with self.assertRaises(M7Error):
                guardrails.lazy_plan(bad_ranking, [])


class ActiveEntryTests(unittest.TestCase):
    def setUp(self):
        self.root = "/home/laura/rnagenesis-mres-runs"

    def test_entry_for_the_best_ranked_candidate_binds_nothing_earlier(self):
        self.assertTrue(guardrails.assert_active_entry(entry_for(self.root, position=1), self.root))

    def test_a_later_entry_binds_every_earlier_failed_candidate(self):
        entry = entry_for(self.root, epoch=4, position=3, preceding=[failed(2), failed(5)])
        self.assertTrue(guardrails.assert_active_entry(entry, self.root))
        for mutate in (
            lambda e: e.update(preceding_candidates=[failed(2)]),
            lambda e: e.update(preceding_candidates=[]),
            lambda e: e.update(preceding_candidates=[failed(2), failed(2)]),
            lambda e: e.update(preceding_candidates=[failed(2), failed(4)]),
            lambda e: e.update(preceding_candidates=[failed(2), dict(failed(5), outcome="passed")]),
            lambda e: e.update(preceding_candidates=[failed(2), dict(failed(5), manifest_sha256="short")]),
            lambda e: e.update(ranking_position=6),
            lambda e: e.update(ranking_position=0),
        ):
            changed = copy.deepcopy(entry)
            mutate(changed)
            with self.assertRaises(M7Error):
                guardrails.assert_active_entry(changed, self.root)

    def test_update_zero_and_unexpected_seeds_are_never_candidates(self):
        for epoch in (0, 6, True, 1.5):
            entry = entry_for(self.root)
            entry["candidate_epoch"] = epoch
            with self.assertRaises(M7Error):
                guardrails.assert_active_entry(entry, self.root)
        for seed in (1, 42, 45):
            entry = entry_for(self.root)
            entry["candidate_seed"] = seed
            with self.assertRaises(M7Error):
                guardrails.assert_active_entry(entry, self.root)

    def test_binding_rules(self):
        for mutate in (
            lambda e: e.update(authorisation_id="m7_unit_seed44_epoch3_candidate"),
            lambda e: e.update(activation_status="inactive_no_authorisation"),
            lambda e: e.update(single_use=False),
            lambda e: e.update(permitted_roles=list(guardrails.ACTIVE_ROLES) + ["EVAL"]),
            lambda e: e.update(permitted_roles=["REF"]),
            lambda e: e.update(physical_gpu_index=0),
            lambda e: e.update(logical_device="cuda:1"),
            lambda e: e.update(expected_schedule_sha256="0" * 64),
            lambda e: e.update(checkpoint_directory=e["checkpoint_directory"].replace("epoch-3", "epoch-4")),
            lambda e: e.update(checkpoint_directory=common.RUN_ROOT + "/m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6/" + contract.checkpoint_child_name(43, 3, PARENT)),
            lambda e: e.update(checkpoint_directory=e["checkpoint_directory"].replace("m7_unit", "REF_unit")),
            lambda e: e["checkpoint_member_sha256"].update({common.WEIGHT_MEMBER: sorted(common.M6_FORBIDDEN_WEIGHT_SHA256)[0]}),
            lambda e: e["checkpoint_member_sha256"].pop("model_index.json"),
            lambda e: e.update(replicate_manifest_sha256="short"),
            lambda e: e.update(authorization_commit=HEAD),
            lambda e: e.update(extra=1),
        ):
            entry = entry_for(self.root)
            mutate(entry)
            with self.assertRaises(M7Error):
                guardrails.assert_active_entry(entry, self.root)

    def test_ld_library_path_binding_and_implementation_config_hash(self):
        for value in (None, "/home/laura/miniconda3/envs/rnagenesis-h200/lib", "/usr/lib:/usr/local/cuda/lib64"):
            self.assertTrue(guardrails.assert_active_entry(entry_for(self.root, ld_library_path=value), self.root))
        for value in ("", "lib", "/lib:", "/lib/../x", "/a b", 7, "/home/laura/data/EVAL/lib"):
            with self.assertRaises(M7Error, msg=repr(value)) as caught:
                guardrails.assert_active_entry(entry_for(self.root, ld_library_path=value), self.root)
            self.assertEqual(caught.exception.code, "environment_rejected")
        entry = entry_for(self.root)
        del entry["ld_library_path"]
        with self.assertRaises(M7Error):
            guardrails.assert_active_entry(entry, self.root)
        entry = entry_for(self.root)
        entry["implementation_config_sha256"] = "short"
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_active_entry(entry, self.root)
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        self.assertIn("ld_library_path", guardrails.ACTIVE_ENTRY_KEYS)
        self.assertIn("implementation_config_sha256", guardrails.ACTIVE_ENTRY_KEYS)
        self.assertIn("checkpoint_training_implementation_commit", guardrails.ACTIVE_ENTRY_KEYS)

    def test_training_provenance_is_separate_from_the_guardrail_execution_commit(self):
        training = "c150894b9982d7afebfb2b3390b0797a4da146b5"
        execution = "d" * 40
        entry = entry_for(self.root, commit=execution, training_commit=training)
        self.assertEqual(entry["authorization_parent_commit"], execution)
        self.assertEqual(entry["executing_implementation_commit"], execution)
        self.assertEqual(entry["checkpoint_training_implementation_commit"], training)
        self.assertNotEqual(training, execution)
        self.assertTrue(guardrails.assert_active_entry(entry, self.root))
        self.assertIn(training, entry["checkpoint_relative_name"])
        self.assertNotIn(execution, entry["checkpoint_relative_name"])
        for bad in ("", "abc", "G" * 40, "c150894", None, execution + "ff"):
            changed = entry_for(self.root, commit=execution, training_commit=training)
            changed["checkpoint_training_implementation_commit"] = bad
            with self.assertRaises(M7Error, msg=repr(bad)) as caught:
                guardrails.assert_active_entry(changed, self.root)
            self.assertIn(caught.exception.code, ("provenance_mismatch", "authorisation_scope_invalid", "authorisation_shape_invalid"))
        missing = entry_for(self.root, commit=execution, training_commit=training)
        del missing["checkpoint_training_implementation_commit"]
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_active_entry(missing, self.root)
        self.assertEqual(caught.exception.code, "authorisation_shape_invalid")
        mismatched_parent = entry_for(self.root, commit=execution, training_commit=training)
        mismatched_parent["authorization_parent_commit"] = "e" * 40
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_active_entry(mismatched_parent, self.root)
        self.assertEqual(caught.exception.code, "authorisation_commit_invalid")

    def test_one_entry_per_candidate_in_an_active_document(self):
        with open(os.path.join(ROOT, "config/experiments/D1_candidate_guardrails.yaml"), "rb") as handle:
            inactive = common.load_config_bytes(handle.read())
        config = copy.deepcopy(inactive)
        config["document_status"] = guardrails.ACTIVE_DOCUMENT_STATUS
        config["consumable_by_executable_workflow"] = True
        for key in contract.EXECUTION_KEYS:
            config["execution"][key] = True
        config["authorisation_entries"] = [entry_for(self.root, 43, 3), entry_for(self.root, 44, 3)]
        entries = guardrails.assert_active_configuration(config, self.root)
        self.assertEqual(sorted(entries), [(43, 3), (44, 3)])
        config["authorisation_entries"].append(entry_for(self.root, 43, 3))
        with self.assertRaises(M7Error):
            guardrails.assert_active_configuration(config, self.root)
        config["authorisation_entries"] = []
        with self.assertRaises(M7Error):
            guardrails.assert_active_configuration(config, self.root)


class CommandTests(unittest.TestCase):
    INVOCATION = {"actual_chunk_size": 8, "batch_num": 1, "invocation_index": 3, "invocation_seed": 44003, "max_seq_len": 38, "target_length": 37}

    def test_one_authorised_checkpoint_is_substituted_for_the_diffusion_model(self):
        entry = entry_for("/home/laura/rnagenesis-mres-runs", epoch=2)
        argv = guardrails.build_candidate_argv(self.INVOCATION, entry["checkpoint_directory"], entry)
        self.assertEqual(argv.count("--dm_file"), 1)
        self.assertEqual(argv[argv.index("--dm_file") + 1], entry["checkpoint_directory"])
        self.assertEqual(argv[0], common.PINNED_PYTHON)
        self.assertIn("--do_sample", argv)

    def test_other_checkpoints_and_m6_checkpoints_are_refused(self):
        entry = entry_for("/home/laura/rnagenesis-mres-runs", epoch=2)
        with self.assertRaises(M7Error):
            guardrails.build_candidate_argv(self.INVOCATION, entry["checkpoint_directory"].replace("epoch-2", "epoch-3"), entry)
        m6_directory = common.RUN_ROOT + "/m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6/D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-42__update-21__git-" + "6" * 40
        entry["checkpoint_directory"] = m6_directory
        with self.assertRaises(M7Error) as caught:
            guardrails.build_candidate_argv(self.INVOCATION, m6_directory, entry)
        self.assertEqual(caught.exception.code, "m6_checkpoint_forbidden")


class CandidateLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = os.path.realpath(tempfile.mkdtemp(prefix="m7test"))
        self.addCleanup(lambda: shutil.rmtree(self.temp, ignore_errors=True))
        self.run = support.successful_run(43)["manifest"]
        self.blob = support.successful_run(43)["blob"]
        self.entry = entry_for(self.temp, seed=43, epoch=2, position=1)
        self.entry["authorization_commit"] = HEAD
        self.entry["output_directory"] = self.temp + "/m7_unit_seed43_epoch2_candidate"
        self.entry["evidence_directory"] = self.entry["output_directory"]
        os.makedirs(os.path.dirname(self.entry["checkpoint_directory"]))
        for member in common.CHECKPOINT_MEMBERS:
            target = os.path.join(self.entry["checkpoint_directory"], member)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(("payload " + member).encode("ascii"))
        self.entry["checkpoint_member_sha256"] = {
            member: common.stream_sha256(os.path.join(self.entry["checkpoint_directory"], member)) for member in common.CHECKPOINT_MEMBERS
        }
        self.weight = self.entry["checkpoint_member_sha256"][common.WEIGHT_MEMBER]

    def measure(self, entry, checkpoint_directory, output):
        return {
            "accounting": {
                "cleaner_sha256": guardrails.CLEANER_SHA256,
                "invocation_count": 112,
                "raw_attempts": 1000,
                "schedule_sha256": common.m6_contract().PAIRED_SCHEDULE_SHA256,
                "valid_outputs": 1000,
            },
            "environment": {"interpreter": dict(support.INTERPRETER), "ld_library_path": common.unbound_ld_library_path_record()},
            "gpu": dict(GPU),
            "ledgers": dict(support.LEDGER_HASHES),
            "provenance": guardrails.provenance_block(file_hashes()),
            "replicate_binding": {
                "epoch": 2,
                "replicate_manifest_sha256": digest("replicate"),
                "seed": 43,
                "validation_mse": "0.5",
                "validation_ranking_sha256": digest("ranking"),
                "weight_sha256": self.weight,
            },
            "report_only": dict(support.REPORT_ONLY),
            "values": dict(support.PASSING_VALUES),
        }

    def test_success_writes_one_validated_manifest(self):
        manifest = guardrails.run_candidate(self.entry, self.measure, run_root=self.temp)
        self.assertTrue(guardrails.validate_candidate_manifest(manifest))
        path = os.path.join(self.entry["output_directory"], guardrails.SUCCESS_MANIFEST_NAME)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), common.canonical_json(manifest))
        self.assertTrue(manifest["guardrails"]["passed"])
        self.assertEqual((manifest["candidate"]["seed"], manifest["candidate"]["epoch"]), (43, 2))
        self.assertEqual(manifest["checkpoint"]["weight_sha256"], self.weight)
        self.assertEqual(manifest["closure"]["no_selection_claim"], True)
        self.assertFalse(os.path.exists(os.path.join(self.entry["output_directory"], common.FAILURE_RECORD_NAME)))
        with self.assertRaises(M7Error) as caught:
            guardrails.run_candidate(self.entry, self.measure, run_root=self.temp)
        self.assertEqual(caught.exception.code, "authorization_reuse")

    def failure(self, measure):
        with self.assertRaises(BaseException) as caught:
            guardrails.run_candidate(self.entry, measure, run_root=self.temp)
        with open(os.path.join(self.entry["output_directory"], common.FAILURE_RECORD_NAME), "rb") as handle:
            return caught.exception, json.loads(handle.read().decode("utf-8"))

    def test_failures_record_the_candidate_and_the_stage(self):
        def raising(entry, checkpoint, output):
            raise RuntimeError("fixture " + support.RNA_MESSAGE)

        error, record = self.failure(raising)
        self.assertEqual(record["code"], "unexpected_runtime_failure")
        self.assertEqual((record["seed"], record["epoch"], record["stage"], record["entry_kind"]), (43, 2, "generation", "candidate"))
        self.assertEqual(record["candidate"], {"epoch": 2, "ranking_position": 1, "seed": 43})
        self.assertNotIn(support.RNA_MESSAGE, json.dumps(record))

    def test_interrupts_are_recorded_and_propagate(self):
        for exception in (KeyboardInterrupt(), SystemExit(2)):
            self.tearDown_directory()
            self.setUp()

            def interrupting(entry, checkpoint, output, exception=exception):
                raise exception

            error, record = self.failure(interrupting)
            self.assertIs(error, exception)
            self.assertEqual(record["code"], "interrupted")
            self.assertEqual(record["candidate"]["epoch"], 2)

    def tearDown_directory(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_a_checkpoint_that_changes_during_generation_is_refused(self):
        def changing(entry, checkpoint, output):
            with open(os.path.join(checkpoint, "unet", "config.json"), "ab") as handle:
                handle.write(b"x")
            return self.measure(entry, checkpoint, output)

        error, record = self.failure(changing)
        self.assertEqual(record["code"], "checkpoint_save_reload_incompatibility")
        self.assertEqual(record["stage"], "checkpoint_verification_after")

    def test_a_checkpoint_that_does_not_match_the_authorisation_is_refused_before_generation(self):
        self.entry["checkpoint_member_sha256"]["model_index.json"] = digest("other")
        calls = []
        error, record = self.failure(lambda entry, checkpoint, output: calls.append(1))
        self.assertEqual(calls, [])
        self.assertEqual(record["stage"], "checkpoint_verification_before")

    def test_a_tampered_measurement_cannot_produce_a_manifest(self):
        def tampered(entry, checkpoint, output):
            measured = self.measure(entry, checkpoint, output)
            measured["report_only"]["thresholds_defined"] = True
            return measured

        error, record = self.failure(tampered)
        self.assertEqual(record["code"], "guardrail_manifest_invalid")
        self.assertFalse(os.path.exists(os.path.join(self.entry["output_directory"], guardrails.SUCCESS_MANIFEST_NAME)))

    def test_existing_output_directory_is_not_written_into(self):
        os.makedirs(self.entry["output_directory"])
        with self.assertRaises(M7Error) as caught:
            guardrails.run_candidate(self.entry, self.measure, run_root=self.temp)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertEqual(os.listdir(self.entry["output_directory"]), [])


class CandidateManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.replicate = support.successful_run(43)
        cls.blob = support.guardrail_blob(cls.replicate["manifest"], cls.replicate["blob"], 3, False, 1, [])
        cls.manifest = json.loads(cls.blob.decode("utf-8"))

    def fresh(self):
        return copy.deepcopy(self.manifest)

    def test_valid_manifest_binds_one_seed_epoch_and_checkpoint(self):
        self.assertTrue(guardrails.validate_candidate_manifest(self.fresh()))
        self.assertEqual(self.manifest["candidate"]["seed"], 43)
        self.assertEqual(self.manifest["candidate"]["epoch"], 3)
        self.assertIs(self.manifest["guardrails"]["passed"], False)
        self.assertEqual(common.canonical_json(self.manifest), self.blob)

    def test_mutations_are_refused(self):
        def flip_passed(m):
            m["guardrails"]["passed"] = True

        def change_value(m):
            m["guardrails"]["values"]["unique_fraction"] = 1.0

        def other_epoch(m):
            m["candidate"]["epoch"] = 4

        def update_zero(m):
            m["authorisation"]["candidate_epoch"] = 0
            m["candidate"]["epoch"] = 0

        def weight_changed(m):
            m["checkpoint"]["weights_sha256_after_generation"] = digest("x")

        def forbidden(m):
            weight = sorted(common.M6_FORBIDDEN_WEIGHT_SHA256)[0]
            m["checkpoint"]["members_sha256"][common.WEIGHT_MEMBER] = weight
            m["checkpoint"]["weight_sha256"] = weight

        def ref_roles(m):
            m["input_roles"].append("REF")

        def eval_opened(m):
            m["ref_eval_access"]["eval_opened"] = True

        def attempts(m):
            m["accounting"]["raw_attempts"] = 999

        def threshold(m):
            m["report_only"]["thresholds_defined"] = True

        def selection_claim(m):
            m["closure"]["no_selection_claim"] = False

        def wrong_preceding(m):
            m["preceding_candidates"] = [dict(failed(1))]

        def schedule(m):
            m["accounting"]["schedule_sha256"] = "0" * 64

        def unexpected_seed(m):
            m["authorisation"]["candidate_seed"] = 42
            m["candidate"]["seed"] = 42

        for mutate in (
            flip_passed, change_value, other_epoch, update_zero, weight_changed, forbidden, ref_roles, eval_opened, attempts, threshold,
            selection_claim, wrong_preceding, schedule, unexpected_seed,
        ):
            manifest = self.fresh()
            mutate(manifest)
            with self.assertRaises(M7Error, msg=mutate.__name__):
                guardrails.validate_candidate_manifest(manifest)

    def test_sequence_text_and_extra_keys_are_refused(self):
        manifest = self.fresh()
        manifest["report_only"]["gross_length_behaviour"] = {"raw_decoded_text": "ACGU"}
        with self.assertRaises(M7Error):
            guardrails.validate_candidate_manifest(manifest)
        manifest = self.fresh()
        manifest["selected"] = True
        with self.assertRaises(M7Error):
            guardrails.validate_candidate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()

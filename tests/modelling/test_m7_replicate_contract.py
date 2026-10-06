"""CPU/mock tests for the inactive M7 replicate contract.

These tests do not open biological corpora, model weights, accepted run
directories, or a GPU. They read only tracked configuration and source files.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

ROOT = "/home/laura/rnagenesis-aptamer-mres"
CONTRACT_PATH = os.path.join(ROOT, "scripts/modelling/m7_replicate_contract.py")
CONFIG_PATH = os.path.join(ROOT, "config/experiments/D1_final_replicates.yaml")
RUNNER_PATH = os.path.join(ROOT, "scripts/modelling/m7_replicate_runner.py")
HEAD = "a" * 40
PARENT = "b" * 40
GPU_UUID = "GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f"
PCI = "00000000:61:00.0"
M6_PILOT_YAML_BLOB = "4c0ef9b700f0c4566e1fdaa71dc68c25370712f0"
M6_DIAGNOSTIC_YAML_BLOB = "d33a0284b7edf81b922364eb4838b9f52a551d57"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = load_module("m7_replicate_contract_under_test", CONTRACT_PATH)
common = contract.common
M7Error = common.M7Error


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_blob_id(path):
    with open(path, "rb") as handle:
        data = handle.read()
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def file_hashes():
    return {path: digest(path) for path in contract.IMPLEMENTATION_FILE_PATHS}


def load_inactive():
    with open(CONFIG_PATH, "rb") as handle:
        raw = handle.read()
    return raw, contract.load_config_bytes(raw)


def interpreter_record():
    return {
        "path": common.PINNED_PYTHON,
        "resolved_path": common.PINNED_ENVIRONMENT_PREFIX + "/bin/python3.8",
        "sha256": digest("pinned interpreter executable"),
        "size": 17000000,
    }


def entry_for(seed, run_root, commit=PARENT, gpu=1, attempt="gpu1", ld_library_path=None):
    m6 = common.m6_contract()
    name = "m7_unit_seed%d_%s" % (seed, attempt)
    output = run_root.rstrip("/") + "/" + name
    return {
        "activation_status": "active_unconsumed",
        "applied_learning_rate_trace_sha256": contract.APPLIED_LEARNING_RATE_TRACE_SHA256,
        "authorisation_id": name,
        "authorisation_timestamp": "2026-10-07T09:00:00+11:00",
        "authorization_parent_commit": commit,
        "b1_relative_path": m6.B1_RELATIVE_PATH,
        "b1_unet_config_sha256": m6.B1_UNET_CONFIG_SHA256,
        "b1_weight_sha256": m6.B1_WEIGHT_SHA256,
        "consumed": False,
        "cuda_visible_devices": str(gpu),
        "evidence_directory": output,
        "executing_implementation_commit": commit,
        "expected_checkpoint_names": contract.expected_checkpoint_names(seed, commit),
        "expected_epochs": list(contract.CANDIDATE_EPOCHS),
        "expected_update_counts": list(contract.CANDIDATE_UPDATES),
        "forbidden_initialisation_weight_sha256": sorted(common.M6_FORBIDDEN_WEIGHT_SHA256),
        "gpu_uuid": GPU_UUID,
        "implementation_config_sha256": digest("implementation-config"),
        "implementation_file_hashes": file_hashes(),
        "interpreter": interpreter_record(),
        "ld_library_path": ld_library_path,
        "logical_device": "cuda:0",
        "output_directory": output,
        "pci_bus": PCI,
        "permitted_roles": list(contract.ACTIVE_ROLES),
        "phase": contract.ACTIVE_PHASE,
        "physical_gpu_index": gpu,
        "reuse_permitted": False,
        "scope": contract.ACTIVE_SCOPE_PREFIX + str(seed),
        "seed": seed,
        "session": {
            "consumption_event": contract.CONSUMPTION_EVENT,
            "pattern": contract.SESSION_PATTERN,
            "resume_permitted": False,
            "wall_clock_expiry": None,
        },
        "single_use": True,
        "train_record_count": m6.TRAIN_RECORD_COUNT,
        "train_text_path": m6.FUTURE_TRAIN_TEXT_PATH,
        "train_text_sha256": m6.TRAIN_TEXT_SHA256,
        "validation_artifact_directory": m6.ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY,
        "validation_artifact_sha256": {
            "draw_manifest": m6.VALIDATION_DRAW_MANIFEST_SHA256,
            "noise": m6.VALIDATION_NOISE_SHA256,
            "order_artifact": m6.VALIDATION_ORDER_ARTIFACT_SHA256,
            "sequence_order": m6.VALIDATION_SEQUENCE_ORDER_SHA256,
            "timesteps": m6.VALIDATION_TIMESTEPS_SHA256,
        },
        "validation_csv_path": m6.FUTURE_VALIDATION_CSV_PATH,
        "validation_csv_sha256": m6.VALIDATION_CSV_SHA256,
        "validation_record_count": m6.VALIDATION_SEQUENCE_COUNT,
    }


def active_from(inactive, run_root, seeds=(43, 44), ld_library_path=None):
    config = copy.deepcopy(inactive)
    config["document_status"] = contract.ACTIVE_DOCUMENT_STATUS
    config["consumable_by_executable_workflow"] = True
    for key in contract.EXECUTION_KEYS:
        config["execution"][key] = True
    config["authorisation_entries"] = [entry_for(seed, run_root, ld_library_path=ld_library_path) for seed in seeds]
    return config


def observation(inactive_raw, inactive, entry, hashes=None, file_porcelain="?? .cache/huggingface/hub/version.txt\n"):
    hashes = file_hashes() if hashes is None else hashes
    m5 = common.m6_contract().m5_contract()
    return {
        "changed_files": list(contract.PERMITTED_AUTHORIZATION_FILES),
        "component_symlink": False,
        "file_sha256_at_parent": hashes,
        "file_sha256_working_tree": dict(hashes),
        "gpu_probe": {
            "cuda_visible_devices": entry["cuda_visible_devices"],
            "logical_device": "cuda:0",
            "pci_bus": entry["pci_bus"],
            "physical_index": entry["physical_gpu_index"],
            "uuid": entry["gpu_uuid"],
        },
        "implementation_config": inactive,
        "implementation_config_bytes": b"implementation-config",
        "mres_branch": "main",
        "mres_head": HEAD,
        "mres_origin_main": PARENT,
        "mres_parents": [PARENT],
        "mres_porcelain": "",
        "output_exists": False,
        "output_symlink": False,
        "rnagenesis_branch": common.RNAGENESIS_BRANCH,
        "rnagenesis_directory_porcelain": m5.reviewed_rnagenesis_porcelain(),
        "rnagenesis_file_porcelain": file_porcelain,
        "rnagenesis_head": common.RNAGENESIS_COMMIT,
    }


class InactivePackageTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.inactive = load_inactive()

    def test_checked_in_configuration_is_inactive_and_refused(self):
        text = self.raw.decode("utf-8")
        self.assertTrue(contract.assert_inactive_text(text))
        self.assertTrue(contract.assert_inactive_configuration(self.inactive))
        self.assertEqual(contract.classify_configuration(self.inactive), "inactive")
        with self.assertRaises(M7Error) as caught:
            contract.reject_inactive_before_execution(self.inactive)
        self.assertEqual(caught.exception.code, "execution_not_authorised")
        self.assertEqual(self.inactive["authorisation_entries"], [])
        self.assertIs(self.inactive["consumable_by_executable_workflow"], False)
        self.assertEqual(self.inactive["document_status"], "M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED")
        for token in ("GPU-", "authorisation_id: m7", "output_directory: /"):
            self.assertNotIn(token, text)

    def test_m6_configuration_blobs_are_unchanged_and_inactive(self):
        self.assertEqual(git_blob_id(os.path.join(ROOT, "config/experiments/D1_diffusion_pilot.yaml")), M6_PILOT_YAML_BLOB)
        self.assertEqual(git_blob_id(os.path.join(ROOT, "config/experiments/D1_update21_diagnostic_generation.yaml")), M6_DIAGNOSTIC_YAML_BLOB)

    def test_every_activation_attempt_on_the_inactive_document_is_refused(self):
        mutations = (
            lambda c: c.update(document_status=contract.ACTIVE_DOCUMENT_STATUS),
            lambda c: c.update(consumable_by_executable_workflow=True),
            lambda c: c["execution"].update(authorised=True),
            lambda c: c["execution"].update(biological_paths_permitted=True),
            lambda c: c["execution"].update(gpu_identity_bound=True),
            lambda c: c.update(authorisation_entries=[entry_for(43, common.RUN_ROOT)]),
            lambda c: c.update(authorization_commit=HEAD),
            lambda c: c["execution"].update(output_directory="/x"),
            lambda c: c["seed_plan"].update(target_seeds=[42, 43]),
            lambda c: c["seed_plan"].update(target_seeds=[43, 44, 45]),
            lambda c: c["seed_plan"].update(validation_draw_seed=43),
            lambda c: c["replicate_decisions"].update(epochs=6),
            lambda c: c["replicate_decisions"].update(ema_enabled=True),
            lambda c: c["replicate_decisions"].update(learning_rate=1e-5),
            lambda c: c["replicate_decisions"].update(resume_supported=True),
            lambda c: c["schedule"].update(warmup_updates=2),
            lambda c: c["schedule"].update(applied_learning_rate_may_be_zero=True),
            lambda c: c["validation"].update(update_0_selectable=True),
            lambda c: c["data"].update(ref_access=True),
            lambda c: c["data"].update(eval_path="/x/eval.csv"),
            lambda c: c["model"].update(prohibited_initialisation=[]),
            lambda c: c["m8_boundary"].update(total_raw_d1_attempts=10),
            lambda c: c["operational_cutoff"].update(recorded_not_automated=False),
            lambda c: c["seed_plan"]["forbidden_initialisation_weight_sha256"].update(update_7="0" * 64),
            lambda c: c.pop("candidate_guardrail_boundary"),
        )
        for mutate in mutations:
            config = copy.deepcopy(self.inactive)
            mutate(config)
            with self.assertRaises(M7Error):
                contract.assert_inactive_configuration(config)
        for token in ("authorised: true", "consumable_by_executable_workflow: true", "GPU-abc", "CUDA_VISIBLE_DEVICES: 1", "authorization_commit: x"):
            with self.assertRaises(M7Error):
                contract.assert_inactive_text(self.raw.decode("utf-8") + "\n" + token + "\n")
        for line in ("  output_directory: /x", "  authorisation_id: m7_x", "  executing_implementation_commit: " + "a" * 40):
            with self.assertRaises(M7Error):
                contract.assert_inactive_text(self.raw.decode("utf-8") + "\n" + line + "\n")

    def test_classification_refuses_a_mixed_document(self):
        config = copy.deepcopy(self.inactive)
        config["consumable_by_executable_workflow"] = True
        with self.assertRaises(M7Error):
            contract.classify_configuration(config)
        with self.assertRaises(M7Error):
            contract.classify_configuration([])

    def test_decisions_are_exactly_the_approved_ones(self):
        decisions = self.inactive["replicate_decisions"]
        plan = self.inactive["seed_plan"]
        self.assertEqual(plan["target_seeds"], [43, 44])
        self.assertEqual(plan["excluded_seeds"], [42])
        self.assertEqual(plan["validation_draw_seed"], 1)
        self.assertEqual(plan["minimum_permitted_completed_seeds"], 1)
        self.assertEqual(plan["m6_checkpoint_updates_forbidden_as_initialisation_or_resume"], [7, 14, 21])
        self.assertEqual(
            (decisions["epochs"], decisions["microbatches_per_epoch"], decisions["optimizer_updates_per_epoch"], decisions["total_optimizer_updates_per_seed"]),
            (5, 84, 21, 105),
        )
        self.assertEqual((decisions["physical_microbatch"], decisions["gradient_accumulation"], decisions["intended_effective_batch"]), (8, 4, 32))
        self.assertEqual(decisions["final_window_microbatch_sizes_every_epoch"], [8, 8, 8, 5])
        self.assertEqual(decisions["precision"], "fp32")
        self.assertEqual((decisions["optimizer_name"], decisions["learning_rate"], decisions["beta1"], decisions["beta2"]), ("AdamW", 3e-5, 0.95, 0.999))
        self.assertEqual((decisions["epsilon"], decisions["weight_decay"], decisions["gradient_clip_norm"]), (1e-8, 1e-6, 1.0))
        self.assertIs(decisions["ema_enabled"], False)
        self.assertIs(decisions["resume_supported"], False)
        self.assertEqual(self.inactive["validation"]["validation_updates"], [0, 21, 42, 63, 84, 105])
        self.assertEqual(self.inactive["checkpoints"]["retention_minimum_date"], "2026-11-01")
        self.assertIs(self.inactive["checkpoints"]["deletion_implemented"], False)
        self.assertEqual(self.inactive["m8_boundary"]["two_seed_attempts_each"], 15000)
        cutoff = self.inactive["operational_cutoff"]
        self.assertEqual((cutoff["stretch_target"], cutoff["hard_target"]), ("2026-10-07T18:00:00+11:00", "2026-10-08T17:00:00+11:00"))
        self.assertIs(cutoff["may_depend_on_seed_43_scientific_results"], False)


class ScheduleTests(unittest.TestCase):
    def test_105_updates_ten_warmup_updates_and_the_first_is_a_tenth(self):
        trace = contract.applied_learning_rate_trace()
        self.assertEqual(len(trace), 105)
        base = contract.BASE_LEARNING_RATE
        self.assertEqual(trace[0], base * 0.1)
        for update in range(1, 11):
            self.assertAlmostEqual(trace[update - 1] / base, update / 10.0, places=15)
        self.assertEqual(trace[9], base)
        self.assertEqual(trace[10], base)
        self.assertTrue(all(trace[index] > trace[index + 1] for index in range(10, 104)))
        self.assertTrue(all(value > 0.0 for value in trace))

    def test_no_applied_update_has_a_zero_learning_rate(self):
        self.assertEqual(contract.learning_rate_multiplier(106), 0.0)
        for bad in (0, -1, 106, 107, True, 1.0, "1"):
            with self.assertRaises(M7Error) as caught:
                contract.applied_learning_rate(bad)
            self.assertIn(caught.exception.code, ("learning_rate_zero_applied", "learning_rate_schedule_invalid"))
        with self.assertRaises(M7Error):
            contract.learning_rate_multiplier(0)
        with self.assertRaises(M7Error):
            contract.learning_rate_multiplier(107)

        class Optimizer(object):
            param_groups = [{"lr": 1.0}, {"lr": 2.0}]

        optimizer = Optimizer()
        for update in (1, 10, 11, 105):
            value = contract.assign_applied_learning_rate(optimizer, update)
            self.assertEqual([group["lr"] for group in optimizer.param_groups], [value, value])
        with self.assertRaises(M7Error):
            contract.assign_applied_learning_rate(optimizer, 106)
        with self.assertRaises(M7Error):
            contract.assign_applied_learning_rate(type("Empty", (), {"param_groups": []})(), 1)

    def test_trace_hash_is_recorded_and_pinned(self):
        self.assertTrue(contract.assert_trace_hash())
        self.assertEqual(contract.trace_sha256(), contract.APPLIED_LEARNING_RATE_TRACE_SHA256)
        strings = contract.trace_strings()
        self.assertEqual(len(strings), 105)
        self.assertEqual(strings[0], "3.0000000000000001e-06")
        altered = list(strings)
        altered[50] = altered[51]
        self.assertNotEqual(contract.trace_sha256(altered), contract.APPLIED_LEARNING_RATE_TRACE_SHA256)
        _raw, inactive = load_inactive()
        self.assertEqual(inactive["schedule"]["applied_learning_rate_trace_sha256"], contract.trace_sha256())

    def test_the_schedule_generalises_the_accepted_m6_convention(self):
        m6 = common.m6_contract()
        for position in range(1, 22):
            m7_like = contract.learning_rate_multiplier(position) if position <= 105 else None
            if position <= 2:
                self.assertEqual(m6.learning_rate_multiplier(position), position / 2.0)
        self.assertEqual(m6.learning_rate_multiplier(1), 0.5)
        self.assertEqual(contract.learning_rate_multiplier(1), 0.1)


class SeedAndArithmeticTests(unittest.TestCase):
    def test_only_seeds_43_and_44_are_accepted(self):
        self.assertEqual(contract.assert_seed(43), 43)
        self.assertEqual(contract.assert_seed(44), 44)
        for bad in (1, 42, 0, 45, 4300, -43, True, False, 43.0, "43", None):
            with self.assertRaises(M7Error) as caught:
                contract.assert_seed(bad)
            self.assertEqual(caught.exception.code, "unexpected_seed", repr(bad))

    def test_epoch_windows_end_in_8_8_8_5_and_cover_every_record_once(self):
        windows = contract.epoch_windows()
        self.assertEqual(len(windows), 21)
        self.assertEqual(windows[-1], (8, 8, 8, 5))
        self.assertTrue(all(window == (8, 8, 8, 8) for window in windows[:-1]))
        self.assertEqual(sum(len(window) for window in windows), 84)
        self.assertEqual(sum(sum(window) for window in windows), 669)
        self.assertEqual(contract.TOTAL_UPDATES, 105)
        self.assertEqual(contract.TOTAL_MICROBATCHES, 420)

    def test_epoch_boundaries(self):
        self.assertEqual([contract.epoch_update_range(epoch) for epoch in range(1, 6)], [(1, 21), (22, 42), (43, 63), (64, 84), (85, 105)])
        self.assertEqual([contract.epoch_of_update(update) for update in (1, 21, 22, 42, 43, 105)], [1, 1, 2, 2, 3, 5])
        for bad in (0, 6, True, 1.0):
            with self.assertRaises(M7Error):
                contract.epoch_update_range(bad)
        for bad in (0, 106, True):
            with self.assertRaises(M7Error):
                contract.epoch_of_update(bad)

    def test_update_zero_is_provenance_only(self):
        self.assertTrue(contract.validation_schedule_for(0))
        self.assertFalse(contract.identifies_candidate(0))
        for update in (21, 42, 63, 84, 105):
            self.assertTrue(contract.identifies_candidate(update))
        for bad in (1, 20, 22, 106):
            with self.assertRaises(M7Error):
                contract.validation_schedule_for(bad)

    def test_checkpoint_universe_per_seed(self):
        names = contract.expected_checkpoint_names(43, PARENT)
        self.assertEqual(len(names), 5)
        self.assertEqual(len(set(names)), 5)
        self.assertTrue(all("seed-43__epoch-" in name and name.endswith("__git-" + PARENT) for name in names))
        self.assertTrue(names[0].endswith("__update-21__git-" + PARENT) or "__update-21__" in names[0])
        self.assertEqual([name.split("__update-")[1].split("__")[0] for name in names], ["21", "42", "63", "84", "105"])
        self.assertTrue(set(names).isdisjoint(contract.expected_checkpoint_names(44, PARENT)))
        self.assertIsNone(common.M6_CHECKPOINT_NAME_PATTERN.search(" ".join(names)))
        for bad_seed in (42, 1):
            with self.assertRaises(M7Error):
                contract.checkpoint_child_name(bad_seed, 1, PARENT)
        with self.assertRaises(M7Error):
            contract.checkpoint_child_name(43, 1, "short")
        with self.assertRaises(M7Error):
            contract.checkpoint_child_name(43, 6, PARENT)

    def test_permutation_digest_requires_a_full_permutation(self):
        self.assertEqual(len(contract.permutation_digest(list(range(669)))), 64)
        with self.assertRaises(M7Error):
            contract.permutation_digest(list(range(668)))
        with self.assertRaises(M7Error):
            contract.permutation_digest([0] * 669)


class ActiveSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = os.path.realpath(tempfile.mkdtemp(prefix="m7test"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.temp, ignore_errors=True))
        self.raw, self.inactive = load_inactive()

    def test_two_independent_entries_are_accepted(self):
        config = active_from(self.inactive, self.temp)
        entries = contract.assert_active_configuration(config, self.temp)
        self.assertEqual(sorted(entries), [43, 44])
        self.assertNotEqual(entries[43]["output_directory"], entries[44]["output_directory"])
        self.assertNotEqual(entries[43]["authorisation_id"], entries[44]["authorisation_id"])
        self.assertEqual(contract.find_entry(entries, "m7_unit_seed43_gpu1")["seed"], 43)
        self.assertEqual(contract.find_entry(entries, "m7_unit_seed44_gpu1")["seed"], 44)

    def test_one_entry_alone_is_accepted_for_either_seed(self):
        for seed in (43, 44):
            config = active_from(self.inactive, self.temp, seeds=(seed,))
            self.assertEqual(list(contract.assert_active_configuration(config, self.temp)), [seed])

    def test_entry_count_seed_and_identity_rules(self):
        base = active_from(self.inactive, self.temp)
        config = copy.deepcopy(base)
        config["authorisation_entries"] = []
        with self.assertRaises(M7Error):
            contract.assert_active_configuration(config, self.temp)
        config["authorisation_entries"] = base["authorisation_entries"] + [entry_for(43, self.temp, attempt="gpu0")]
        with self.assertRaises(M7Error):
            contract.assert_active_configuration(config, self.temp)
        config = copy.deepcopy(base)
        config["authorisation_entries"][1]["output_directory"] = config["authorisation_entries"][0]["output_directory"]
        config["authorisation_entries"][1]["evidence_directory"] = config["authorisation_entries"][0]["output_directory"]
        with self.assertRaises(M7Error):
            contract.assert_active_configuration(config, self.temp)
        config = copy.deepcopy(base)
        config["authorisation_entries"][1] = entry_for(44, self.temp, commit="c" * 40)
        with self.assertRaises(M7Error) as caught:
            contract.assert_active_configuration(config, self.temp)
        self.assertEqual(caught.exception.code, "authorisation_evidence_mismatch")

    def test_each_binding_is_enforced(self):
        def mutate_nested(key, value):
            def apply(entry):
                entry[key] = value

            return apply

        cases = {
            "unexpected_seed": [mutate_nested("seed", 42), mutate_nested("seed", 1), mutate_nested("seed", 45), mutate_nested("seed", True)],
            "authorisation_field_missing": [mutate_nested("authorisation_id", "m7_seed44_x"), mutate_nested("authorisation_id", "m6_unit_seed43"), mutate_nested("authorisation_timestamp", "yesterday")],
            "authorisation_inactive": [mutate_nested("activation_status", "inactive_no_authorisation"), mutate_nested("consumed", True)],
            "authorization_reuse": [mutate_nested("single_use", False), mutate_nested("reuse_permitted", True)],
            "authorisation_commit_invalid": [mutate_nested("authorization_parent_commit", "c" * 40), mutate_nested("executing_implementation_commit", "short")],
            "authorisation_scope_invalid": [
                mutate_nested("phase", "M6_D1_diffusion_pilot"),
                mutate_nested("scope", contract.ACTIVE_SCOPE_PREFIX + "44"),
                mutate_nested("permitted_roles", list(contract.ACTIVE_ROLES) + ["REF"]),
                mutate_nested("permitted_roles", ["EVAL"]),
                mutate_nested("expected_epochs", [1, 2, 3, 4]),
                mutate_nested("expected_update_counts", [0, 21, 42, 63, 84, 105]),
                mutate_nested("expected_checkpoint_names", []),
            ],
            "identity_mismatch": [
                mutate_nested("physical_gpu_index", 0),
                mutate_nested("cuda_visible_devices", "0"),
                mutate_nested("logical_device", "cuda:1"),
                mutate_nested("gpu_uuid", "GPU-x"),
                mutate_nested("pci_bus", "61:00.0"),
                mutate_nested("train_text_sha256", "0" * 64),
                mutate_nested("validation_csv_sha256", "0" * 64),
                mutate_nested("b1_weight_sha256", "0" * 64),
                mutate_nested("applied_learning_rate_trace_sha256", "0" * 64),
            ],
            "m6_checkpoint_forbidden": [mutate_nested("forbidden_initialisation_weight_sha256", [])],
            "execution_not_authorised": [mutate_nested("evidence_directory", "/home/laura/rnagenesis-mres-runs/other")],
            "provenance_mismatch": [mutate_nested("implementation_config_sha256", "short")],
        }
        for expected_code, mutations in cases.items():
            for mutate in mutations:
                entry = entry_for(43, self.temp)
                mutate(entry)
                with self.assertRaises(M7Error) as caught:
                    contract.assert_active_entry(entry, self.temp)
                self.assertEqual(caught.exception.code, expected_code, mutate.__closure__[1].cell_contents if mutate.__closure__ else "")
        entry = entry_for(43, self.temp)
        entry["authorization_commit"] = HEAD
        with self.assertRaises(M7Error):
            contract.assert_active_entry(entry, self.temp)
        entry = entry_for(43, self.temp)
        entry["output_directory"] = "/home/laura/rnagenesis-mres-runs/m7_unit_seed43_gpu1"
        with self.assertRaises(M7Error):
            contract.assert_active_entry(entry, self.temp)
        entry = entry_for(43, self.temp)
        entry["implementation_file_hashes"].pop(contract.IMPLEMENTATION_FILE_PATHS[0])
        with self.assertRaises(M7Error):
            contract.assert_active_entry(entry, self.temp)
        entry = entry_for(43, self.temp)
        entry["extra"] = 1
        with self.assertRaises(M7Error):
            contract.assert_active_entry(entry, self.temp)

    def test_output_name_must_be_the_authorisation_id_and_not_ref_eval_or_m6(self):
        for name in ("m7_unit_seed43_ref", "m7_unit_seed43_EVAL_x"):
            entry = entry_for(43, self.temp)
            entry["authorisation_id"] = name
            entry["output_directory"] = self.temp + "/" + name
            entry["evidence_directory"] = entry["output_directory"]
            with self.assertRaises(M7Error):
                contract.assert_active_entry(entry, self.temp)

    def test_launcher_accepts_only_an_authorisation_id(self):
        self.assertEqual(contract.parse_launcher_argv(["--authorisation-id", "m7_unit_seed43_gpu1"]), "m7_unit_seed43_gpu1")
        for bad in (
            [],
            ["m7_unit_seed43_gpu1"],
            ["--authorisation-id"],
            ["--authorisation-id", "m6_unit_seed43"],
            ["--authorisation-id", "m7_unit_seed43_gpu1", "--seed", "43"],
            ["--seed", "43"],
            ["--authorisation-id", "m7_unit_seed43_gpu1", "--gpu", "1"],
            ["--authorisation-id", "m7_unit_seed43_gpu1", "--output-dir", "/x"],
            ["--authorisation-id", "m7_unit_seed43_gpu1", "--learning-rate", "1e-5"],
            ["--config", "x"],
        ):
            with self.assertRaises(M7Error) as caught:
                contract.parse_launcher_argv(bad)
            self.assertEqual(caught.exception.code, "cli_argument_rejected", bad)
        entries = contract.assert_active_configuration(active_from(self.inactive, self.temp), self.temp)
        with self.assertRaises(M7Error):
            contract.find_entry(entries, "m7_unit_seed43_missing")
        with self.assertRaises(M7Error):
            contract.find_entry(entries, "not-an-id")

    def test_authorisation_delta_permits_only_activation_paths(self):
        config = active_from(self.inactive, self.temp)
        paths = contract.assert_authorisation_delta(self.inactive, config)
        self.assertTrue(set(paths) <= set(contract.PERMITTED_ACTIVATION_PATHS))
        for mutate in (
            lambda c: c["replicate_decisions"].update(epochs=6),
            lambda c: c["schedule"].update(warmup_updates=5),
            lambda c: c["data"].update(future_train_text_path="/x"),
            lambda c: c.update(rnagenesis_commit="c" * 40),
        ):
            tampered = copy.deepcopy(config)
            mutate(tampered)
            with self.assertRaises(M7Error) as caught:
                contract.assert_authorisation_delta(self.inactive, tampered)
            self.assertEqual(caught.exception.code, "authorisation_delta_invalid")
        with self.assertRaises(M7Error):
            contract.assert_authorisation_delta(self.inactive, copy.deepcopy(self.inactive))


class LdLibraryPathEntryTests(unittest.TestCase):
    """The entry field is ``None`` or one exact value; the inactive document binds neither."""

    VALUE = "/home/laura/miniconda3/envs/rnagenesis-h200/lib:/usr/local/cuda/lib64"

    def setUp(self):
        self.temp = os.path.realpath(tempfile.mkdtemp(prefix="m7test"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.temp, ignore_errors=True))
        self.raw, self.inactive = load_inactive()

    def test_none_and_one_exact_value_are_valid_entries(self):
        for value in (None, self.VALUE, "/usr/lib"):
            entry = entry_for(43, self.temp, ld_library_path=value)
            self.assertTrue(contract.assert_active_entry(entry, self.temp))
            self.assertEqual(entry["ld_library_path"], value)

    def test_malformed_values_are_refused(self):
        for value in ("", "lib", "/lib:", "/lib/../x", "/a b", 7, ["/lib"], "/home/laura/REF/lib", contract.common.RNAGENESIS_ROOT + "/.cache/lib"):
            with self.assertRaises(M7Error, msg=repr(value)) as caught:
                contract.assert_active_entry(entry_for(43, self.temp, ld_library_path=value), self.temp)
            self.assertEqual(caught.exception.code, "environment_rejected")

    def test_the_key_is_part_of_the_entry_schema_and_absence_is_refused(self):
        self.assertIn("ld_library_path", contract.ACTIVE_ENTRY_KEYS)
        self.assertIn("ld_library_path", contract.authorisation_schema()["entry_keys"])
        entry = entry_for(43, self.temp)
        del entry["ld_library_path"]
        with self.assertRaises(M7Error) as caught:
            contract.assert_active_entry(entry, self.temp)
        self.assertEqual(caught.exception.code, "authorisation_shape_invalid")

    def test_the_inactive_document_binds_no_value(self):
        self.assertTrue(contract.assert_inactive_configuration(self.inactive))
        self.assertNotIn("ld_library_path:", self.raw.decode("utf-8"))
        self.assertIn("exact_ld_library_path_value_or_none", self.inactive["authorisation_schema"]["entry_binds"])
        for mutate in (
            lambda c: c.update(ld_library_path=self.VALUE),
            lambda c: c["seed_plan"].update(ld_library_path=None),
            lambda c: c["authorisation_schema"].update(ld_library_path=self.VALUE),
        ):
            config = copy.deepcopy(self.inactive)
            mutate(config)
            with self.assertRaises(M7Error):
                contract.assert_inactive_configuration(config)
        self.assertNotIn("ambient_ld_library_path_not_inherited_by_child", self.inactive["residual_limitations"])


class ValidatedEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = os.path.realpath(tempfile.mkdtemp(prefix="m7test"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.temp, ignore_errors=True))
        self.raw, self.inactive = load_inactive()
        self.config = active_from(self.inactive, self.temp)
        self.entries = contract.assert_active_configuration(self.config, self.temp)

    def validate(self, seed, **changes):
        entry = self.entries[seed]
        observed = observation(self.raw, self.inactive, entry)
        observed.update(changes)
        return contract.validate_active_execution(self.config, entry["authorisation_id"], observed, self.temp)

    def test_validation_binds_one_entry_and_the_live_commit(self):
        authorised = self.validate(43)
        self.assertEqual(authorised["seed"], 43)
        self.assertEqual(authorised["authorization_commit"], HEAD)
        self.assertEqual(authorised["gpu_probe"]["physical_index"], 1)
        self.assertTrue(authorised["repository_observation"]["rnagenesis_untracked_preserved"])
        with self.assertRaises(M7Error):
            contract.ValidatedEntry({}, object())

    def test_repository_and_gpu_refusals(self):
        for changes, code in (
            ({"mres_parents": [PARENT, "c" * 40]}, "authorisation_commit_invalid"),
            ({"mres_parents": ["c" * 40]}, "authorisation_commit_invalid"),
            ({"mres_head": PARENT}, "authorisation_commit_invalid"),
            ({"changed_files": ["config/experiments/D1_final_replicates.yaml", "scripts/modelling/m7_common.py"]}, "authorisation_delta_invalid"),
            ({"changed_files": ["config/experiments/D1_diffusion_pilot.yaml"]}, "authorisation_delta_invalid"),
            ({"mres_porcelain": " M scripts/modelling/m7_common.py\n"}, "provenance_mismatch"),
            ({"mres_porcelain": "?? stray.txt\n"}, "provenance_mismatch"),
            ({"rnagenesis_head": "c" * 40}, "provenance_mismatch"),
            ({"rnagenesis_file_porcelain": " M models/x.py\n"}, "provenance_mismatch"),
            ({"output_exists": True}, "authorization_reuse"),
            ({"output_symlink": True}, "authorization_reuse"),
            ({"component_symlink": True}, "execution_not_authorised"),
            ({"gpu_probe": {"cuda_visible_devices": "0", "logical_device": "cuda:0", "pci_bus": PCI, "physical_index": 0, "uuid": GPU_UUID}}, "identity_mismatch"),
            ({"gpu_probe": {"cuda_visible_devices": "1", "logical_device": "cuda:0", "pci_bus": "00000000:41:00.0", "physical_index": 1, "uuid": GPU_UUID}}, "identity_mismatch"),
            ({"gpu_probe": {"cuda_visible_devices": "1", "logical_device": "cuda:0", "pci_bus": PCI, "physical_index": 1, "uuid": "GPU-00000000-0000-0000-0000-000000000000"}}, "identity_mismatch"),
        ):
            with self.assertRaises(M7Error) as caught:
                self.validate(43, **changes)
            self.assertEqual(caught.exception.code, code, changes)

    def test_hash_drift_in_parent_or_working_tree_is_refused(self):
        entry = self.entries[43]
        for where in ("file_sha256_at_parent", "file_sha256_working_tree"):
            observed = observation(self.raw, self.inactive, entry)
            observed[where][contract.IMPLEMENTATION_FILE_PATHS[0]] = digest("drift")
            with self.assertRaises(M7Error) as caught:
                contract.validate_active_execution(self.config, entry["authorisation_id"], observed, self.temp)
            self.assertEqual(caught.exception.code, "provenance_mismatch")
        observed = observation(self.raw, self.inactive, entry)
        observed["implementation_config_bytes"] = b"other"
        with self.assertRaises(M7Error):
            contract.validate_active_execution(self.config, entry["authorisation_id"], observed, self.temp)

    def test_consuming_one_entry_never_consumes_the_other(self):
        first = self.validate(43)
        directory = contract.consume_entry(first, self.temp)
        self.assertEqual(directory, self.entries[43]["output_directory"])
        self.assertFalse(os.path.lexists(self.entries[44]["output_directory"]))
        with self.assertRaises(M7Error) as caught:
            self.validate(43, output_exists=True)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        with self.assertRaises(M7Error) as caught:
            contract.consume_entry(first, self.temp)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        second = self.validate(44)
        self.assertEqual(contract.consume_entry(second, self.temp), self.entries[44]["output_directory"])
        self.assertTrue(os.path.isfile(os.path.join(directory, common.CONSUMPTION_RECORD_NAME)))
        import json

        with open(os.path.join(directory, common.CONSUMPTION_RECORD_NAME), "rb") as handle:
            record = json.loads(handle.read().decode("utf-8"))
        self.assertEqual((record["seed"], record["authorisation_id"], record["reuse_permitted"]), (43, first["authorisation_id"], False))
        with self.assertRaises(M7Error):
            contract.consume_entry(self.entries[43], self.temp)

    def test_a_failed_first_seed_does_not_consume_the_second(self):
        first = self.validate(43)
        directory = contract.consume_entry(first, self.temp)
        common.record_consumed_failure(directory, RuntimeError("boom"), {"authorisation_id": first["authorisation_id"], "output_directory": directory}, common.new_progress(43), contract.SUCCESS_MANIFEST_NAME)
        self.assertTrue(os.path.isfile(os.path.join(directory, common.FAILURE_RECORD_NAME)))
        second = self.validate(44)
        self.assertFalse(os.path.lexists(second["output_directory"]))
        contract.consume_entry(second, self.temp)

    def test_worker_revalidation_requires_the_consumed_directory(self):
        entry = self.entries[43]
        observed = observation(self.raw, self.inactive, entry)
        with self.assertRaises(M7Error):
            contract.validate_active_execution(self.config, entry["authorisation_id"], observed, self.temp, consumed_worker=True)
        observed["output_exists"] = True
        self.assertEqual(contract.validate_active_execution(self.config, entry["authorisation_id"], observed, self.temp, consumed_worker=True)["seed"], 43)


class EntryPointTests(unittest.TestCase):
    def run_cli(self, *arguments):
        environment = {key: value for key, value in os.environ.items()}
        completed = subprocess.run(
            [sys.executable, "-B", RUNNER_PATH] + list(arguments), env=environment, capture_output=True, text=True, cwd="/tmp"
        )
        return completed

    def test_help_and_schema_only(self):
        helped = self.run_cli("--help")
        self.assertEqual(helped.returncode, 0)
        self.assertIn("--authorisation-id <id>", helped.stdout)
        schema = self.run_cli("--schema")
        self.assertEqual(schema.returncode, 0)
        import json

        parsed = json.loads(schema.stdout)
        self.assertEqual(parsed["document_status"], contract.DOCUMENT_STATUS)
        self.assertEqual(parsed["entry_keys"], list(contract.ACTIVE_ENTRY_KEYS))

    def test_everything_else_is_refused(self):
        for arguments in (
            [],
            ["--seed", "43"],
            ["--authorisation-id", "m7_unit_seed43_gpu1"],
            ["--authorisation-id", "bad"],
            ["--output-dir", "/x"],
            ["--help", "--schema"],
            ["--gpu", "1"],
        ):
            completed = self.run_cli(*arguments)
            self.assertNotEqual(completed.returncode, 0, arguments)
            self.assertEqual(completed.stdout, "")
            self.assertTrue(
                completed.stderr.startswith("cli_argument_rejected") or completed.stderr.startswith("execution_not_authorised"),
                completed.stderr,
            )

    def test_help_and_schema_import_no_training_stack(self):
        code = (
            "import importlib.util,sys;"
            "spec=importlib.util.spec_from_file_location('r', %r);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
            "m.main(['--schema']);"
            "bad=[n for n in ('torch','accelerate','diffusers','transformers') if n in sys.modules];"
            "sys.stderr.write(','.join(bad))"
        ) % RUNNER_PATH
        completed = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, cwd="/tmp")
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()

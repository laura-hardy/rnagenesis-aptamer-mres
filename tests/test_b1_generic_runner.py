"""Synthetic tests for the B1 Phase A runner.

These tests do not load a model, initialise CUDA, query a GPU, open
biological sequence data, execute RNAGenesis generation, or create the
Phase A evidence directory. External operations are injected. Cleaning
tests call the approved pure-Python audit functions on synthetic strings.
The checked-in configuration carries one active, unconsumed Phase A
authorisation. Closed-gate cases use synthetic copies.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import inspect
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_RUNTIME_MODULES = (
    "torch",
    "numpy",
    "diffusers",
    "transformers",
    "RNA",
    "fm",
    "omegaconf",
    "tokenizers",
    "huggingface_hub",
    "accelerate",
    "safetensors",
    "einops",
)


def load_source_module(name, path):
    """Compile source bytes in memory. Do not consult bytecode caches."""
    source = Path(path).read_bytes()
    code = compile(source, str(path), "exec", dont_inherit=True)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    exec(code, module.__dict__)
    return module


runner = load_source_module(
    "b1_generic_runner",
    ROOT / "scripts" / "b1_generic_runner.py",
)

COMMIT = "a" * 40
IMPLEMENTATION_COMMIT = "bdb3dbda1650a3bd65407e1deadcf0862249f972"
AUTHORISATION_ID = "m4_b1_phase_a_bdb3dbda1650_gpu0_attempt1"
REAL_EVIDENCE = Path(
    "/home/laura/rnagenesis-mres-runs/"
    "m4_b1_generic_generation_B1_generic_released_rnagenesis_bdb3dbda1650_phaseA"
)
WEIGHT_SUFFIXES = (".bin", ".safetensors")


def setUpModule():
    if REAL_EVIDENCE.exists() or REAL_EVIDENCE.is_symlink():
        raise AssertionError("real Phase A evidence path already exists")


def tearDownModule():
    if REAL_EVIDENCE.exists() or REAL_EVIDENCE.is_symlink():
        raise AssertionError("real Phase A evidence path was created")
    loaded = [name for name in FORBIDDEN_RUNTIME_MODULES if name in sys.modules]
    if loaded:
        raise AssertionError(
            "test process imported {}".format(", ".join(loaded))
        )


class FakeStat(object):
    def __init__(self, mode, size):
        self.st_mode = mode
        self.st_size = size


def real_config_bytes():
    return runner.B1_CONFIG_PATH.read_bytes()


def real_config():
    return runner.load_config_bytes(real_config_bytes())


def authorisation(commit=COMMIT, **overrides):
    evidence = runner.evidence_directory_for_commit(commit)
    block = {
        "authorisation_id": "synthetic-test-authorisation",
        "authorisation_active": True,
        "activation_status": runner.ACTIVE_UNCONSUMED_STATUS,
        "consumed": False,
        "authorises_b1_phase_a": True,
        "gpu_use_authorised": True,
        "physical_gpu": 0,
        "executing_implementation_commit": commit,
        "mres_branch": "main",
        "condition": runner.CONDITION_LABEL,
        "phase": "A",
        "output_directory": evidence,
        "evidence_directory": evidence,
        "success_claimed": False,
        "m4_complete": False,
        "b1_eligible": False,
        "phase_b_authorised": False,
        "development_pool_authorised": False,
    }
    block.update(overrides)
    return block


def opened_config(commit=COMMIT, **auth_overrides):
    config = copy.deepcopy(real_config())
    config["consumable_by_executable_workflow"] = True
    config["document_status"] = runner.EXECUTABLE_DOCUMENT_STATUS
    config["phase_a"]["executable_now"] = True
    config["phase_a"]["status"] = runner.PHASE_A_EXECUTION_STATUS
    config["execution"]["authorised"] = True
    config["execution"]["gpu_authorised_by_this_approval"] = True
    config["scientific_execution_authorisation"] = authorisation(
        commit, **auth_overrides
    )
    return config


def dumped(config):
    return yaml.safe_dump(config).encode("utf-8")


class RecordingDeps(object):
    def __init__(self, config_bytes, environ):
        self.config_bytes = config_bytes
        self.events = []
        self.environ = environ

    def read_bytes(self, path):
        self.events.append(("read_bytes", str(path)))
        if Path(path) != runner.B1_CONFIG_PATH:
            raise AssertionError("unexpected read {}".format(path))
        if path.name.endswith(WEIGHT_SUFFIXES):
            raise AssertionError(path)
        return self.config_bytes

    def forbid(self, name):
        def inner(*args, **kwargs):
            self.events.append((name,))
            raise AssertionError("{} was called".format(name))

        return inner

    def build(self, **overrides):
        deps = runner.RunnerDependencies(
            read_bytes=overrides.get("read_bytes", self.read_bytes),
            lstat=overrides.get("lstat", self.forbid("lstat")),
            realpath=overrides.get("realpath", self.forbid("realpath")),
            sha256_file=overrides.get("sha256_file", self.forbid("sha256_file")),
            environ=self.environ,
            git=overrides.get("git", self.forbid("git")),
            gpu_preflight=overrides.get(
                "gpu_preflight", self.forbid("gpu_preflight")
            ),
            mkdir=overrides.get("mkdir", self.forbid("mkdir")),
            write_exclusive=overrides.get(
                "write_exclusive", self.forbid("write_exclusive")
            ),
            subprocess_run=overrides.get(
                "subprocess_run", self.forbid("subprocess_run")
            ),
            load_cleaner=overrides.get("load_cleaner", self.forbid("load_cleaner")),
            clock=overrides.get("clock", self.forbid("clock")),
            hostname=overrides.get("hostname", self.forbid("hostname")),
        )
        return deps


def assert_closed(test, code, stderr, deps, gate):
    test.assertEqual(code, 1)
    test.assertIn("error: {}:".format(gate), stderr)
    test.assertEqual([event[0] for event in deps.events], ["read_bytes"])
    forbidden = {
        "lstat",
        "realpath",
        "sha256_file",
        "git",
        "gpu_preflight",
        "mkdir",
        "write_exclusive",
        "subprocess_run",
        "load_cleaner",
    }
    test.assertTrue(forbidden.isdisjoint(event[0] for event in deps.events))


def run_main(deps, output_dir):
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = runner.main(["--output-dir", output_dir], deps=deps)
    return code, stderr.getvalue()


def synthetic_closed_copy():
    """Copy of the checked-in configuration with the consumable gate closed."""
    config = copy.deepcopy(real_config())
    config["consumable_by_executable_workflow"] = False
    return config


def assign_path(config, path, value):
    cursor = config
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value


class ClosedGateTests(unittest.TestCase):
    def test_checked_in_configuration_is_one_unconsumed_phase_a_run(self):
        config = real_config()
        block = config["scientific_execution_authorisation"]
        self.assertEqual(set(block), set(runner.SCIENTIFIC_AUTHORISATION_KEYS))
        self.assertEqual(list(block), list(runner.SCIENTIFIC_AUTHORISATION_KEYS))
        snapshot = runner.assert_document_gates(config)
        self.assertEqual(snapshot, block)
        self.assertEqual(block["authorisation_id"], AUTHORISATION_ID)
        self.assertIs(block["authorisation_active"], True)
        self.assertEqual(block["activation_status"], "active_unconsumed")
        self.assertEqual(block["activation_status"], runner.ACTIVE_UNCONSUMED_STATUS)
        self.assertIs(block["consumed"], False)
        self.assertIs(block["authorises_b1_phase_a"], True)
        self.assertIs(block["gpu_use_authorised"], True)
        self.assertIs(type(block["physical_gpu"]), int)
        self.assertEqual(block["physical_gpu"], 0)
        self.assertEqual(block["executing_implementation_commit"], IMPLEMENTATION_COMMIT)
        self.assertEqual(block["mres_branch"], "main")
        self.assertEqual(block["condition"], "B1_generic_released_rnagenesis")
        self.assertEqual(block["condition"], runner.CONDITION_LABEL)
        self.assertEqual(block["phase"], "A")
        self.assertEqual(block["output_directory"], str(REAL_EVIDENCE))
        self.assertEqual(block["evidence_directory"], str(REAL_EVIDENCE))
        self.assertEqual(
            block["output_directory"],
            runner.evidence_directory_for_commit(IMPLEMENTATION_COMMIT),
        )
        self.assertEqual(
            block["evidence_directory"],
            runner.evidence_directory_for_commit(IMPLEMENTATION_COMMIT),
        )
        self.assertIs(block["success_claimed"], False)
        self.assertIs(block["m4_complete"], False)
        self.assertIs(block["b1_eligible"], False)
        self.assertIs(block["phase_b_authorised"], False)
        self.assertIs(block["development_pool_authorised"], False)
        self.assertIs(config["consumable_by_executable_workflow"], True)
        self.assertEqual(config["document_status"], runner.EXECUTABLE_DOCUMENT_STATUS)
        self.assertIs(config["phase_a"]["executable_now"], True)
        self.assertEqual(config["phase_a"]["status"], runner.PHASE_A_EXECUTION_STATUS)
        self.assertIs(config["execution"]["authorised"], True)
        self.assertIs(config["execution"]["gpu_authorised_by_this_approval"], True)
        self.assertIs(config["phase_b"]["executable_now"], False)
        self.assertIs(config["execution"]["gpu_authorised_by_this_draft"], False)
        self.assertEqual(config["phase_a"]["invocations"], 33)
        self.assertEqual(config["phase_a"]["total_raw_attempts"], 528)
        self.assertEqual(config["phase_a"]["raw_attempts_per_candidate"], 16)
        self.assertEqual(config["phase_a"]["base_seed"], 41000)
        self.assertEqual(config["phase_a"]["first_seed"], 41000)
        self.assertEqual(config["phase_a"]["last_seed"], 41010)
        self.assertEqual(
            config["phase_a"]["candidate_max_seq_len_for_each_target"],
            ["target", "target_plus_1", "target_plus_2"],
        )
        self.assertEqual(
            list(config["phase_a"]["target_biological_lengths"]),
            list(runner.REQUESTED_LENGTHS),
        )
        plan = runner.build_phase_a_plan(config)
        self.assertEqual(len(plan), 33)
        self.assertEqual(len(plan) * 16, 528)
        self.assertFalse(REAL_EVIDENCE.exists())
        self.assertFalse(REAL_EVIDENCE.is_symlink())

    def test_synthetic_closed_configuration_refuses_before_side_effects(self):
        recorder = RecordingDeps(
            dumped(synthetic_closed_copy()),
            {"CUDA_VISIBLE_DEVICES": "0"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            before = set(Path(tmp).iterdir())
            code, stderr = run_main(recorder.build(), tmp)
            after = set(Path(tmp).iterdir())
        assert_closed(self, code, stderr, recorder, "configuration_not_consumable")
        self.assertEqual(before, after)
        self.assertIn("consumable_by_executable_workflow is not true", stderr)
        self.assertFalse(REAL_EVIDENCE.exists())

    def test_missing_cuda_does_not_outrank_the_closed_document(self):
        recorder = RecordingDeps(dumped(synthetic_closed_copy()), {})
        code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
        assert_closed(self, code, stderr, recorder, "configuration_not_consumable")
        self.assertFalse(REAL_EVIDENCE.exists())

    def test_direct_gate_identifies_the_closed_document(self):
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(synthetic_closed_copy())
        self.assertEqual(caught.exception.code, "configuration_not_consumable")

    def test_each_closed_gate_field_refuses_on_a_synthetic_copy(self):
        specs = [
            (("consumable_by_executable_workflow",), False, "configuration_not_consumable"),
            (
                ("document_status",),
                "APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION",
                "configuration_not_consumable",
            ),
            (("phase_a", "executable_now"), False, "phase_a_not_authorised"),
            (
                ("phase_a", "status"),
                "APPROVED_DESIGN_NOT_APPROVED_FOR_GPU_EXECUTION",
                "phase_a_not_authorised",
            ),
            (("execution", "authorised"), False, "execution_not_authorised"),
            (
                ("execution", "gpu_authorised_by_this_approval"),
                False,
                "gpu_not_authorised",
            ),
            (
                ("scientific_execution_authorisation", "authorisation_active"),
                False,
                "scientific_authorisation_inactive",
            ),
            (
                ("scientific_execution_authorisation", "activation_status"),
                "inactive",
                "scientific_authorisation_inactive",
            ),
            (
                ("scientific_execution_authorisation", "consumed"),
                True,
                "scientific_authorisation_consumed",
            ),
            (
                ("scientific_execution_authorisation", "consumed"),
                "false",
                "scientific_authorisation_consumed",
            ),
            (
                ("scientific_execution_authorisation", "authorises_b1_phase_a"),
                False,
                "phase_a_not_authorised",
            ),
            (
                ("scientific_execution_authorisation", "gpu_use_authorised"),
                False,
                "gpu_not_authorised",
            ),
            (
                ("scientific_execution_authorisation", "physical_gpu"),
                "0",
                "gpu_not_authorised",
            ),
            (("scientific_execution_authorisation", "physical_gpu"), 1, "gpu_not_authorised"),
            (("scientific_execution_authorisation", "physical_gpu"), 2, "gpu_not_authorised"),
            (("scientific_execution_authorisation", "physical_gpu"), None, "gpu_not_authorised"),
            (
                ("scientific_execution_authorisation", "executing_implementation_commit"),
                "c" * 40,
                "authorisation_evidence_mismatch",
            ),
            (
                ("scientific_execution_authorisation", "executing_implementation_commit"),
                "not-a-commit",
                "authorisation_commit_invalid",
            ),
            (
                ("scientific_execution_authorisation", "mres_branch"),
                "other",
                "mres_branch_not_main",
            ),
            (
                ("scientific_execution_authorisation", "condition"),
                "other",
                "scientific_authorisation_incomplete",
            ),
            (("scientific_execution_authorisation", "phase"), "B", "phase_a_not_authorised"),
            (
                ("scientific_execution_authorisation", "output_directory"),
                "/tmp/other",
                "authorisation_evidence_mismatch",
            ),
            (
                ("scientific_execution_authorisation", "output_directory"),
                str(REAL_EVIDENCE) + "/",
                "authorisation_evidence_mismatch",
            ),
            (
                ("scientific_execution_authorisation", "evidence_directory"),
                "/home/laura/rnagenesis-mres-runs/../rnagenesis-mres-runs/"
                + REAL_EVIDENCE.name,
                "authorisation_evidence_mismatch",
            ),
            (
                ("scientific_execution_authorisation", "success_claimed"),
                True,
                "scientific_authorisation_incomplete",
            ),
            (
                ("scientific_execution_authorisation", "m4_complete"),
                True,
                "scientific_authorisation_incomplete",
            ),
            (
                ("scientific_execution_authorisation", "b1_eligible"),
                True,
                "b1_eligibility_not_claimable",
            ),
            (
                ("scientific_execution_authorisation", "phase_b_authorised"),
                True,
                "phase_b_not_authorised",
            ),
            (
                ("scientific_execution_authorisation", "development_pool_authorised"),
                True,
                "development_pool_not_authorised",
            ),
        ]
        for path, value, code in specs:
            config = copy.deepcopy(real_config())
            assign_path(config, path, value)
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.assert_document_gates(config)
            self.assertEqual(caught.exception.code, code, path)
        missing_gpu = copy.deepcopy(real_config())
        del missing_gpu["scientific_execution_authorisation"]["physical_gpu"]
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(missing_gpu)
        self.assertEqual(caught.exception.code, "scientific_authorisation_incomplete")
        self.assertIn("physical_gpu", caught.exception.detail)
        self.assertFalse(REAL_EVIDENCE.exists())


class AuthorisationTests(unittest.TestCase):
    def test_opened_authorisation_passes_document_gates(self):
        snapshot = runner.assert_document_gates(opened_config())
        self.assertEqual(snapshot["physical_gpu"], 0)
        self.assertEqual(snapshot["phase"], "A")
        self.assertFalse(snapshot["consumed"])
        self.assertFalse(snapshot["b1_eligible"])
        self.assertEqual(
            snapshot["evidence_directory"],
            runner.evidence_directory_for_commit(COMMIT),
        )

    def test_missing_scientific_authorisation_is_not_invented(self):
        config = opened_config()
        del config["scientific_execution_authorisation"]
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(config)
        self.assertEqual(caught.exception.code, "scientific_authorisation_missing")

    def test_missing_authorisation_field_is_named(self):
        config = opened_config()
        del config["scientific_execution_authorisation"]["consumed"]
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(config)
        self.assertEqual(caught.exception.code, "scientific_authorisation_incomplete")
        self.assertIn("consumed", caught.exception.detail)

    def test_unexpected_authorisation_field_is_rejected(self):
        config = opened_config()
        config["scientific_execution_authorisation"]["notes"] = "extra"
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(config)
        self.assertEqual(caught.exception.code, "scientific_authorisation_incomplete")

    def test_inactive_and_consumed_authorisations_refuse(self):
        inactive = opened_config()
        inactive["scientific_execution_authorisation"]["authorisation_active"] = False
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(inactive)
        self.assertEqual(caught.exception.code, "scientific_authorisation_inactive")
        wrong_status = opened_config()
        wrong_status["scientific_execution_authorisation"]["activation_status"] = "inactive"
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(wrong_status)
        self.assertEqual(caught.exception.code, "scientific_authorisation_inactive")
        consumed = opened_config()
        consumed["scientific_execution_authorisation"]["consumed"] = True
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(consumed)
        self.assertEqual(caught.exception.code, "scientific_authorisation_consumed")
        string_false = opened_config()
        string_false["scientific_execution_authorisation"]["consumed"] = "false"
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(string_false)
        self.assertEqual(caught.exception.code, "scientific_authorisation_consumed")

    def test_gpu_must_be_integer_zero(self):
        for value in ("0", True, 1, 2, -1, 0.0, None, False):
            config = opened_config()
            config["scientific_execution_authorisation"]["physical_gpu"] = value
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.assert_document_gates(config)
            self.assertEqual(caught.exception.code, "gpu_not_authorised")
        missing = opened_config()
        del missing["scientific_execution_authorisation"]["physical_gpu"]
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(missing)
        self.assertEqual(caught.exception.code, "scientific_authorisation_incomplete")
        self.assertIn("physical_gpu", caught.exception.detail)

    def test_phase_a_and_eligibility_flags_refuse_when_wrong(self):
        config = opened_config()
        config["phase_a"]["executable_now"] = False
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(config)
        self.assertEqual(caught.exception.code, "phase_a_not_authorised")
        flags = (
            ("b1_eligible", "b1_eligibility_not_claimable"),
            ("phase_b_authorised", "phase_b_not_authorised"),
            ("development_pool_authorised", "development_pool_not_authorised"),
            ("success_claimed", "scientific_authorisation_incomplete"),
            ("m4_complete", "scientific_authorisation_incomplete"),
        )
        for key, code in flags:
            mutated = opened_config()
            mutated["scientific_execution_authorisation"][key] = True
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.assert_document_gates(mutated)
            self.assertEqual(caught.exception.code, code)

    def test_evidence_binding_uses_the_authorised_commit(self):
        commit = IMPLEMENTATION_COMMIT
        self.assertEqual(
            runner.evidence_directory_for_commit(commit),
            str(REAL_EVIDENCE),
        )
        config = opened_config(commit)
        config["scientific_execution_authorisation"]["output_directory"] = "/tmp/other"
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(config)
        self.assertEqual(caught.exception.code, "authorisation_evidence_mismatch")
        self.assertFalse(REAL_EVIDENCE.exists())


class CudaAndOutputTests(unittest.TestCase):
    def test_missing_cuda_visible_devices_refuses(self):
        recorder = RecordingDeps(dumped(opened_config()), {})
        code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
        assert_closed(self, code, stderr, recorder, "cuda_visible_devices_missing")

    def test_cuda_values_other_than_exact_zero_refuse(self):
        for value in ("1", "", "0 ", "00", "0,1", "0\n"):
            recorder = RecordingDeps(
                dumped(opened_config()),
                {"CUDA_VISIBLE_DEVICES": value},
            )
            code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
            assert_closed(self, code, stderr, recorder, "cuda_visible_devices_refused")

    def test_checked_in_configuration_refuses_empty_cuda_before_preflight(self):
        recorder = RecordingDeps(
            real_config_bytes(),
            {"CUDA_VISIBLE_DEVICES": ""},
        )
        code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
        assert_closed(self, code, stderr, recorder, "cuda_visible_devices_refused")
        self.assertNotIn("nvidia-smi", stderr)
        self.assertFalse(REAL_EVIDENCE.exists())
        self.assertFalse(REAL_EVIDENCE.is_symlink())

    def test_real_evidence_aliases_refuse_before_lstat(self):
        expected = str(REAL_EVIDENCE)
        supplied = [
            "phaseA",
            expected + "/",
            "/home/laura/rnagenesis-mres-runs/../rnagenesis-mres-runs/"
            + REAL_EVIDENCE.name,
            "/tmp/b1-not-the-evidence-path",
        ]
        for output_dir in supplied:
            recorder = RecordingDeps(
                real_config_bytes(),
                {"CUDA_VISIBLE_DEVICES": "0"},
            )
            code, stderr = run_main(recorder.build(), output_dir)
            assert_closed(self, code, stderr, recorder, "output_path_mismatch")
        self.assertFalse(REAL_EVIDENCE.exists())
        self.assertFalse(REAL_EVIDENCE.is_symlink())

    def test_output_mismatch_relative_and_alias_refuse_before_lstat(self):
        expected = runner.evidence_directory_for_commit(COMMIT)
        supplied = [
            "phaseA",
            expected + "/",
            "/home/laura/rnagenesis-mres-runs/../rnagenesis-mres-runs/"
            + Path(expected).name,
            "/tmp/b1-not-the-evidence-path",
        ]
        for output_dir in supplied:
            recorder = RecordingDeps(
                dumped(opened_config()),
                {"CUDA_VISIBLE_DEVICES": "0"},
            )
            code, stderr = run_main(recorder.build(), output_dir)
            assert_closed(self, code, stderr, recorder, "output_path_mismatch")

    def test_existing_empty_directory_refuses(self):
        expected = runner.evidence_directory_for_commit(COMMIT)
        recorder = RecordingDeps(
            dumped(opened_config()),
            {"CUDA_VISIBLE_DEVICES": "0"},
        )

        def lstat(path):
            recorder.events.append(("lstat", str(path)))
            self.assertEqual(str(path), expected)
            return FakeStat(stat.S_IFDIR, 0)

        def realpath(path):
            recorder.events.append(("realpath", str(path)))
            return str(path)

        code, stderr = run_main(
            recorder.build(lstat=lstat, realpath=realpath),
            expected,
        )
        self.assertEqual(code, 1)
        self.assertIn("error: output_path_exists:", stderr)
        self.assertNotIn("sha256_file", [event[0] for event in recorder.events])
        self.assertNotIn("mkdir", [event[0] for event in recorder.events])
        self.assertNotIn("gpu_preflight", [event[0] for event in recorder.events])
        self.assertFalse(REAL_EVIDENCE.exists())
        self.assertFalse(Path(expected).exists())

    def test_symlink_and_resolved_alias_refuse(self):
        expected = runner.evidence_directory_for_commit(COMMIT)
        recorder = RecordingDeps(
            dumped(opened_config()),
            {"CUDA_VISIBLE_DEVICES": "0"},
        )

        def lstat(path):
            return FakeStat(stat.S_IFLNK, 0)

        code, stderr = run_main(
            recorder.build(lstat=lstat, realpath=lambda path: path),
            expected,
        )
        self.assertEqual(code, 1)
        self.assertIn("error: output_path_symlink:", stderr)

        def missing(path):
            raise FileNotFoundError(path)

        code, stderr = run_main(
            recorder.build(
                lstat=missing,
                realpath=lambda path: "/tmp/alias-of-evidence",
            ),
            expected,
        )
        self.assertEqual(code, 1)
        self.assertIn("error: output_path_symlink:", stderr)


class PlanAndArgvTests(unittest.TestCase):
    def test_phase_a_plan_has_33_invocations_and_528_attempts(self):
        plan = runner.build_phase_a_plan(real_config())
        self.assertEqual(len(plan), 33)
        self.assertEqual(len(plan) * 16, 528)
        self.assertEqual(
            [item["requested_biological_length"] for item in plan][::3],
            list(runner.REQUESTED_LENGTHS),
        )
        self.assertTrue(all(item["fresh_process"] is True for item in plan))
        self.assertTrue(all(item["batch_size"] == 16 for item in plan))
        self.assertTrue(all(item["batch_num"] == 1 for item in plan))

    def test_seeds_41000_through_41010_are_shared_across_caps(self):
        plan = runner.build_phase_a_plan(real_config())
        for index, length in enumerate(runner.REQUESTED_LENGTHS):
            group = [
                item
                for item in plan
                if item["requested_biological_length"] == length
            ]
            self.assertEqual(len(group), 3)
            self.assertEqual({item["seed"] for item in group}, {41000 + index})
            self.assertEqual(
                [item["max_seq_len"] for item in group],
                [length, length + 1, length + 2],
            )
        self.assertEqual(plan[0]["seed"], 41000)
        self.assertEqual(plan[-1]["seed"], 41010)

    def test_argv_encoding_and_prohibited_flags(self):
        plan = runner.build_phase_a_plan(real_config())
        evidence = runner.evidence_directory_for_commit(COMMIT)
        parent = {"CUDA_VISIBLE_DEVICES": "0", "HF_HUB_OFFLINE": "0"}
        before = dict(parent)
        commands = [
            runner.build_subprocess_invocation(item, evidence, parent)
            for item in plan
        ]
        self.assertEqual(parent, before)
        self.assertEqual(len(commands), 33)
        self.assertEqual(len({id(command["argv"]) for command in commands}), 33)
        for item, command in zip(plan, commands):
            argv = command["argv"]
            self.assertIsInstance(argv, list)
            self.assertFalse(command["shell"])
            self.assertEqual(command["cwd"], "/home/laura/RNAGenesis")
            self.assertEqual(command["env"]["CUDA_VISIBLE_DEVICES"], "0")
            self.assertEqual(command["env"]["HF_HUB_OFFLINE"], "1")
            self.assertEqual(command["env"]["TRANSFORMERS_OFFLINE"], "1")
            self.assertEqual(command["env"]["PYTHONDONTWRITEBYTECODE"], "1")
            self.assertTrue(
                command["env"]["PYTHONPYCACHEPREFIX"].startswith(evidence + "/python_pycache")
            )
            self.assertTrue(command["env"]["HF_HOME"].startswith(evidence + "/isolated_runtime_cache/"))
            self.assertTrue(command["env"]["TORCH_HOME"].startswith(evidence + "/isolated_runtime_cache/"))
            self.assertFalse(command["env"]["HF_HOME"].startswith("/home/laura/RNAGenesis"))
            self.assertNotIn("PYTHONDONTWRITEBYTECODE", parent)
            self.assertEqual(argv[0], runner.PINNED_PYTHON)
            self.assertEqual(argv[1], str(runner.GENERATION_ENTRY))
            self.assertNotIn("sys.executable", inspect.getsource(runner.build_generation_argv))
            self.assertEqual(argv.count("--max_seq_len"), 1)
            self.assertEqual(
                argv[argv.index("--max_seq_len") + 1],
                str(item["max_seq_len"]),
            )
            self.assertEqual(argv[argv.index("--seed") + 1], str(item["seed"]))
            self.assertEqual(argv[argv.index("--enc_dec_file") + 1], runner.ENCDEC_RELATIVE)
            self.assertEqual(argv[argv.index("--dm_file") + 1], runner.DIFFUSION_RELATIVE)
            self.assertEqual(argv[argv.index("--device") + 1], "cuda:0")
            self.assertEqual(argv[argv.index("--num_inference_steps") + 1], "50")
            self.assertEqual(argv[argv.index("--eta") + 1], "0")
            self.assertEqual(argv[argv.index("--top_p") + 1], "0.95")
            self.assertEqual(argv[argv.index("--top_k") + 1], "0")
            self.assertEqual(argv[argv.index("--batch_size") + 1], "16")
            self.assertEqual(argv[argv.index("--batch_num") + 1], "1")
            self.assertEqual(argv[argv.index("--bos_token") + 1], "1")
            self.assertEqual(argv[argv.index("--eos_token") + 1], "2")
            self.assertIn("--do_sample", argv)
            self.assertEqual(
                argv[argv.index("--guidance_classifier_model_config") + 1],
                runner.CLASSIFIER_RELATIVE,
            )
            for option in runner.PROHIBITED_ARGV_OPTIONS:
                self.assertNotIn(option, argv)
            blob = "\n".join(argv)
            self.assertNotIn("checkpoints/Aptamer/diffusion", blob)
            self.assertNotIn("clean_generated_sequences.py", blob)
            self.assertNotIn("checkpoint-15000", blob)
            self.assertNotIn("checkpoint-30000", blob)
            for element in argv:
                self.assertTrue(
                    runner.PROHIBITED_PATH_COMPONENTS.isdisjoint(element.split("/"))
                )
        self.assertEqual(parent["HF_HUB_OFFLINE"], "0")

    def test_parent_encdec_is_selected_and_subcheckpoints_are_rejected(self):
        runner.assert_encdec_selection(runner.ENCDEC_RELATIVE)
        runner.assert_diffusion_selection(runner.DIFFUSION_RELATIVE)
        for relative in (
            "configs/rnagenesis/autoencoder/checkpoint-15000",
            "configs/rnagenesis/autoencoder/checkpoint-30000",
        ):
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.assert_encdec_selection(relative)
            self.assertEqual(caught.exception.code, "encdec_substitute_rejected")
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_diffusion_selection("checkpoints/Aptamer/diffusion")
        self.assertEqual(caught.exception.code, "prohibited_diffusion")
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_cleaner_allowed(runner.PROHIBITED_CLEANER)
        self.assertEqual(caught.exception.code, "prohibited_cleaner")


class PinTests(unittest.TestCase):
    def asset(self, role):
        return next(item for item in runner.PINNED_FILES if item.role == role)

    def test_regular_file_size_symlink_and_hash_failures(self):
        asset = self.asset("encdec_config")
        hashed = []

        def refuse_hash(path):
            hashed.append(path)
            raise AssertionError("hash should not run")

        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.verify_asset(
                asset,
                lambda path: (_ for _ in ()).throw(FileNotFoundError(path)),
                refuse_hash,
            )
        self.assertEqual(caught.exception.code, "pinned_file_missing")
        self.assertEqual(hashed, [])

        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.verify_asset(
                asset,
                lambda path: FakeStat(stat.S_IFLNK, asset.size),
                refuse_hash,
            )
        self.assertEqual(caught.exception.code, "pinned_file_symlink")

        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.verify_asset(
                asset,
                lambda path: FakeStat(stat.S_IFDIR, asset.size),
                refuse_hash,
            )
        self.assertEqual(caught.exception.code, "pinned_file_not_regular")

        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.verify_asset(
                asset,
                lambda path: FakeStat(stat.S_IFREG, 1),
                refuse_hash,
            )
        self.assertEqual(caught.exception.code, "pinned_file_size_mismatch")
        self.assertEqual(hashed, [])

        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.verify_asset(
                asset,
                lambda path: FakeStat(stat.S_IFREG, asset.size),
                lambda path: "0" * 64,
            )
        self.assertEqual(caught.exception.code, "pinned_file_hash_mismatch")

    def test_encdec_substitute_hashes_are_rejected(self):
        asset = self.asset("encdec_weights")
        self.assertTrue(asset.large)
        self.assertEqual(asset.size, 3476049782)
        for digest, name in runner.PROHIBITED_SUBSTITUTE_SHA256.items():
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.verify_asset(
                    asset,
                    lambda path: FakeStat(stat.S_IFREG, asset.size),
                    lambda path, digest=digest: digest,
                )
            self.assertEqual(caught.exception.code, "encdec_substitute_rejected")
            self.assertIn(name, caught.exception.detail)

    def test_large_weights_are_separate_from_small_pins(self):
        large = [item.relative for item in runner.PINNED_FILES if item.large]
        self.assertEqual(
            large,
            [
                "configs/rnagenesis/autoencoder/pytorch_model.bin",
                "configs/rnagenesis/diffusion/unet/diffusion_pytorch_model.safetensors",
            ],
        )

    def test_diffusers_patch_is_a_small_pinned_input(self):
        asset = self.asset("diffusers_normalization_patch")
        self.assertFalse(asset.large)
        self.assertEqual(asset.size, 9516)
        self.assertEqual(
            asset.sha256,
            "09bc632069f1d6e1dc1b1cb7f5b9ca096c83e3010835f11b8dc6c58b45aa13a5",
        )
        self.assertEqual(str(asset.absolute_path()), runner.DIFFUSERS_PATCH_PATH)
        self.assertTrue(str(asset.absolute_path()).endswith("diffusers/models/normalization.py"))
        record = runner.verify_asset(
            asset,
            lambda path: FakeStat(stat.S_IFREG, asset.size),
            lambda path: asset.sha256,
        )
        self.assertEqual(record["path"], runner.DIFFUSERS_PATCH_PATH)
        self.assertEqual(record["size"], 9516)
        self.assertEqual(record["sha256"], asset.sha256)


class CleaningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cleaner = runner.default_load_cleaner()
        cls.invocation = runner.build_phase_a_plan(real_config())[0]

    def adapt(self, raw):
        audited = self.cleaner.audit_line(1, raw)
        return runner.adapt_audited_line(raw, audited, self.invocation, 0)

    def test_synthetic_cleaning_cases(self):
        cases = {
            "11ACGU": {
                "cleaned_sequence": "ACGU",
                "leading_boundary_marker_run": "11",
                "trailing_boundary_marker_run": "",
                "validity": True,
                "rejection_reason": None,
                "termination_observation": runner.TERMINATION_NOT_OBSERVABLE,
            },
            "11ACGU2": {
                "cleaned_sequence": "ACGU",
                "leading_boundary_marker_run": "11",
                "trailing_boundary_marker_run": "2",
                "validity": True,
                "rejection_reason": None,
                "termination_observation": runner.EOS_OBSERVED,
            },
            "": {
                "cleaned_sequence": "",
                "validity": False,
                "rejection_reason": "empty_after_boundary_removal",
                "termination_observation": runner.TERMINATION_NOT_OBSERVABLE,
            },
            "acgu": {
                "cleaned_sequence": "acgu",
                "validity": False,
                "rejection_reason": "invalid_symbols",
            },
            "ACGT": {
                "cleaned_sequence": "ACGT",
                "validity": False,
                "rejection_reason": "invalid_symbols",
            },
            "AC1G2U": {
                "cleaned_sequence": "AC1G2U",
                "leading_boundary_marker_run": "",
                "trailing_boundary_marker_run": "",
                "validity": False,
                "rejection_reason": "invalid_symbols",
                "termination_observation": runner.TERMINATION_NOT_OBSERVABLE,
            },
            "11AC1GU2": {
                "cleaned_sequence": "AC1GU",
                "leading_boundary_marker_run": "11",
                "trailing_boundary_marker_run": "2",
                "validity": False,
                "rejection_reason": "invalid_symbols",
                "termination_observation": runner.EOS_OBSERVED,
            },
        }
        for raw, expected in cases.items():
            record = self.adapt(raw)
            for key, value in expected.items():
                self.assertEqual(record[key], value, "{} {}".format(raw, key))
            self.assertNotEqual(record["cleaned_sequence"], "ACGU" if raw in ("acgu", "ACGT", "AC1G2U") else None)

    def test_termination_is_not_inferred_from_length(self):
        record = self.adapt("11ACGU")
        self.assertNotEqual(record["cleaned_length"], self.invocation["max_seq_len"])
        self.assertEqual(
            record["termination_observation"],
            runner.TERMINATION_NOT_OBSERVABLE,
        )
        self.assertNotIn("max_seq_len", record["termination_observation"])
        self.assertNotIn("cap", record["termination_observation"])

    def test_exactly_16_lines_are_required(self):
        def text(count):
            return "".join("11ACGU\n" for _ in range(count))

        records = runner.audit_invocation_output(
            text(16),
            self.cleaner.split_raw_records,
            self.cleaner.audit_line,
            self.invocation,
        )
        self.assertEqual(len(records), 16)
        for count in (0, 15, 17):
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.audit_invocation_output(
                    text(count),
                    self.cleaner.split_raw_records,
                    self.cleaner.audit_line,
                    self.invocation,
                )
            self.assertEqual(caught.exception.code, "invocation_output_line_count")
            self.assertNotIn("ACGU", caught.exception.detail)

    def test_rejected_attempts_are_retained_in_both_ledgers(self):
        lines = ["11ACGU"] * 15 + ["ACGT"]
        text = "".join(line + "\n" for line in lines)
        records = runner.audit_invocation_output(
            text,
            self.cleaner.split_raw_records,
            self.cleaner.audit_line,
            self.invocation,
        )
        self.assertEqual(len(records), 16)
        self.assertFalse(records[-1]["validity"])
        self.assertEqual(records[-1]["pairing_group"], records[-1]["requested_biological_length"])
        self.assertEqual(records[-1]["attempt_within_candidate"], 15)
        raw_payload = runner.serialize_jsonl(records, runner.RAW_LEDGER_KEYS)
        audited_payload = runner.serialize_jsonl(records, runner.AUDITED_LEDGER_KEYS)
        self.assertNotEqual(raw_payload, audited_payload)
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / runner.RAW_LEDGER_NAME
            audited_path = Path(tmp) / runner.AUDITED_LEDGER_NAME
            runner.write_exclusive_bytes(raw_path, raw_payload)
            runner.write_exclusive_bytes(audited_path, audited_payload)
            raw_rows = [
                json.loads(line)
                for line in raw_path.read_text(encoding="utf-8").splitlines()
            ]
            audited_rows = [
                json.loads(line)
                for line in audited_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(raw_rows), 16)
            self.assertEqual(len(audited_rows), 16)
            self.assertEqual(raw_rows[-1]["raw_decoded_text"], "ACGT")
            self.assertFalse(raw_rows[-1]["validity"])
            self.assertEqual(raw_rows[-1]["rejection_reason"], "invalid_symbols")
            self.assertNotIn("cleaned_sequence", raw_rows[-1])
            self.assertEqual(audited_rows[-1]["cleaned_sequence"], "ACGT")
            self.assertEqual(audited_rows[-1]["rejection_reason"], "invalid_symbols")
            self.assertIn("termination_observation", audited_rows[-1])


class DiagnosticsAndManifestTests(unittest.TestCase):
    def test_provisional_thresholds_do_not_decide_eligibility(self):
        parameters = list(
            __import__("inspect").signature(runner.sequence_only_diagnostics).parameters
        )
        self.assertEqual(parameters, ["attempts"])
        perfect = runner.sequence_only_diagnostics(
            [
                {
                    "requested_biological_length": 4,
                    "validity": True,
                    "cleaned_length": 4,
                }
            ]
        )
        failed = runner.sequence_only_diagnostics(
            [
                {
                    "requested_biological_length": 20,
                    "validity": True,
                    "cleaned_length": 4,
                }
            ]
        )
        for diagnostics in (perfect, failed):
            self.assertEqual(diagnostics["eligibility_decision"], "not_made")
            self.assertEqual(diagnostics["b1_eligibility"], "not_declared")
            self.assertEqual(diagnostics["corpus_dependent_guardrails"], "not_evaluated")
            self.assertEqual(diagnostics["exact_train_match_rate"], "not_evaluated")
            self.assertEqual(
                diagnostics["provisional_thresholds"]["overall_exact_hit_threshold"],
                "0.90",
            )
            self.assertEqual(
                diagnostics["provisional_thresholds"]["per_length_exact_hit_threshold"],
                "0.50",
            )
            self.assertFalse(
                diagnostics["provisional_thresholds"]["applied_as_b1_eligibility_gate"]
            )
        self.assertEqual(perfect["overall_exact_hit_rate"], 1.0)
        self.assertEqual(failed["overall_exact_hit_rate"], 0.0)

    def test_incomplete_ledger_cannot_build_a_success_manifest(self):
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.build_success_manifest(
                {
                    "attempts": [],
                    "diagnostics": runner.sequence_only_diagnostics([]),
                }
            )
        self.assertEqual(caught.exception.code, "success_manifest_refused")

    def test_failure_manifest_is_failed_and_exclusive(self):
        deps = runner.RunnerDependencies(
            write_exclusive=runner.write_exclusive_bytes,
            clock=lambda: "2026-09-30T00:00:00Z",
            hostname=lambda: "synthetic-test-host",
        )
        with tempfile.TemporaryDirectory() as tmp:
            def operation():
                raise runner.B1RunnerError(
                    "invocation_output_line_count",
                    "expected 16 output lines and observed 15",
                )

            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.after_directory_created(
                    tmp,
                    deps,
                    operation,
                    {"config": {}, "snapshot": {}},
                )
            self.assertEqual(caught.exception.code, "invocation_output_line_count")
            success = Path(tmp) / runner.SUCCESS_MANIFEST_NAME
            failure = Path(tmp) / runner.FAILURE_MANIFEST_NAME
            self.assertFalse(success.exists())
            document = json.loads(failure.read_text(encoding="utf-8"))
            self.assertEqual(document["status"], "failed")
            self.assertEqual(document["failure"]["scientific_run_completed"], False)
            self.assertEqual(document["b1_eligibility"], "not_declared")
            self.assertNotIn("manifest_sha256", document)
            self.assertNotIn("manifest_sha256", document["hashes"])
            sentinel = b"sentinel\n"
            failure.write_bytes(sentinel)
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.record_failure(
                    tmp,
                    runner.B1RunnerError("invocation_output_line_count", "again"),
                    deps,
                    {},
                )
            self.assertEqual(caught.exception.code, "failure_manifest_exists")
            self.assertEqual(failure.read_bytes(), sentinel)

    def test_exclusive_writer_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "phase_a_raw_attempts.jsonl"
            runner.write_exclusive_bytes(path, b"first\n")
            with self.assertRaises(FileExistsError):
                runner.write_exclusive_bytes(path, b"second\n")
            self.assertEqual(path.read_bytes(), b"first\n")


class SyntheticExecutionTests(unittest.TestCase):
    def test_mocked_execution_retains_rejections_and_writes_no_self_hash(self):
        config = opened_config()
        plan = runner.build_phase_a_plan(config)
        snapshot = runner.assert_document_gates(config)
        parent = {"CUDA_VISIBLE_DEVICES": "0", "HF_HUB_OFFLINE": "0", "MARKER": "keep"}
        calls = []

        def sha256_file(path):
            text = str(path)
            if text.endswith(WEIGHT_SUFFIXES) or "pytorch_model" in text:
                raise AssertionError(text)
            return runner.default_sha256_file(path)

        def subprocess_run(argv, cwd, env, shell=False):
            self.assertFalse(shell)
            self.assertEqual(cwd, "/home/laura/RNAGenesis")
            self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0")
            self.assertEqual(parent["HF_HUB_OFFLINE"], "0")
            calls.append(list(argv))
            runner.assert_argv_prohibitions(argv)
            mid = argv[argv.index("--mid_folder") + 1]
            remark = argv[argv.index("--remark") + 1]
            superfolder = argv[argv.index("--superfolder") + 1]
            folder = Path(superfolder) / mid
            folder.mkdir(parents=True, exist_ok=False)
            lines = ["11ACGU"] * 16
            if mid == "invocation_00":
                lines[-1] = "ACGT"
            payload = "".join(line + "\n" for line in lines)
            (folder / runner.predicted_generation_filename(remark)).write_text(
                payload,
                encoding="utf-8",
            )

        write_order = []

        def write_exclusive(path, data):
            write_order.append(Path(path).name)
            runner.write_exclusive_bytes(path, data)

        deps = runner.RunnerDependencies(
            read_bytes=runner.default_read_bytes,
            lstat=os_lstat,
            sha256_file=sha256_file,
            environ=parent,
            gpu_preflight=lambda child_env: (_ for _ in ()).throw(
                AssertionError("gpu queried")
            ),
            mkdir=lambda path: (_ for _ in ()).throw(AssertionError("mkdir")),
            write_exclusive=write_exclusive,
            subprocess_run=subprocess_run,
            load_cleaner=runner.default_load_cleaner,
            clock=lambda: "2026-09-30T00:01:00Z",
            hostname=lambda: "synthetic-test-host",
        )
        with tempfile.TemporaryDirectory() as tmp:
            prepared = {
                "output_dir": tmp,
                "config": config,
                "snapshot": snapshot,
                "plan": plan,
                "provenance": {
                    "rnagenesis": {
                        "head": runner.RNAGENESIS_HEAD,
                        "dirty_tree_porcelain": "?? configs/\n",
                        "runner_modified_repository": False,
                    }
                },
                "pins": [],
                "gpu": {
                    "index": 0,
                    "uuid": "GPU-synthetic",
                    "name": "Synthetic GPU",
                    "memory": "1",
                    "compute_mode": "Default",
                    "logical_device": "cuda:0",
                    "cpu_fallback": False,
                },
                "started_at": "2026-09-30T00:00:00Z",
            }
            manifest = runner.execute_phase_a(prepared, deps)
            self.assertEqual(
                write_order,
                [
                    runner.RAW_LEDGER_NAME,
                    runner.AUDITED_LEDGER_NAME,
                    runner.HASH_REPORT_NAME,
                    runner.SUCCESS_MANIFEST_NAME,
                ],
            )
            self.assertEqual(parent["MARKER"], "keep")
            self.assertEqual(parent["HF_HUB_OFFLINE"], "0")
            self.assertEqual(len(calls), 33)
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["final_raw_output_verification"]["passed"], True)
            self.assertEqual(manifest["final_raw_output_verification"]["file_count"], 33)
            self.assertEqual(manifest["eligibility_decision"], "not_made")
            self.assertEqual(manifest["b1_eligibility"], "not_declared")
            self.assertEqual(manifest["corpus_dependent_guardrails"], "not_evaluated")
            self.assertFalse(manifest["m4_complete"])
            self.assertFalse(manifest["phase_b_executed"])
            self.assertFalse(manifest["development_pool_sampled"])
            self.assertEqual(
                manifest["sequence_only_diagnostics"]["overall_exact_hit_rate"],
                0.0,
            )
            self.assertFalse(
                manifest["sequence_only_diagnostics"]["provisional_thresholds"][
                    "applied_as_b1_eligibility_gate"
                ]
            )
            self.assertNotIn("manifest_sha256", manifest)
            self.assertNotIn("manifest_sha256", manifest["hashes"])
            success = Path(tmp) / runner.SUCCESS_MANIFEST_NAME
            failure = Path(tmp) / runner.FAILURE_MANIFEST_NAME
            report = json.loads(
                (Path(tmp) / runner.HASH_REPORT_NAME).read_text(encoding="utf-8")
            )
            self.assertFalse(failure.exists())
            self.assertEqual(report["manifest_sha256"], runner.default_sha256_file(success))
            self.assertNotEqual(report["manifest_sha256"], manifest["hashes"]["raw_ledger_sha256"])
            raw_rows = [
                json.loads(line)
                for line in (Path(tmp) / runner.RAW_LEDGER_NAME).read_text(encoding="utf-8").splitlines()
            ]
            audited_rows = [
                json.loads(line)
                for line in (Path(tmp) / runner.AUDITED_LEDGER_NAME).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(raw_rows), 528)
            self.assertEqual(len(audited_rows), 528)
            self.assertNotEqual(set(raw_rows[0]), set(audited_rows[0]))
            self.assertNotEqual(
                manifest["hashes"]["raw_ledger_sha256"],
                manifest["hashes"]["audited_ledger_sha256"],
            )
            for rows in (raw_rows, audited_rows):
                rejected = [row for row in rows if row["validity"] is False]
                self.assertEqual(len(rejected), 1)
                self.assertEqual(rejected[0]["raw_decoded_text"], "ACGT")
                self.assertEqual(rejected[0]["rejection_reason"], "invalid_symbols")
            self.assertEqual(audited_rows[15]["cleaned_sequence"], "ACGT")
            self.assertNotIn("cleaned_sequence", raw_rows[15])
            self.assertEqual(len(manifest["hashes"]["raw_outputs"]), 33)
        self.assertFalse(REAL_EVIDENCE.exists())


class IsolationTests(unittest.TestCase):
    def test_runner_source_has_no_model_imports_or_shell(self):
        source = (ROOT / "scripts" / "b1_generic_runner.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append((node.module or "").split(".")[0])
        for name in imported:
            self.assertNotIn(
                name,
                {
                    "torch",
                    "diffusers",
                    "transformers",
                    "generation",
                    "pandas",
                    "numpy",
                },
            )
        self.assertNotIn("shell=True", source)
        self.assertIn("shell=False", source)
        self.assertNotIn("torch", sys.modules)

    def test_gpu_preflight_refuses_before_authorisation(self):
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.default_gpu_preflight({"CUDA_VISIBLE_DEVICES": "0"})
        self.assertEqual(caught.exception.code, "gpu_preflight_before_authorisation")

        def query():
            raise AssertionError("gpu queried")

        def probe():
            raise AssertionError("probe ran")

        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.preflight_gpu({}, query, probe)
        self.assertEqual(caught.exception.code, "cpu_fallback_prohibited")
        identity = runner.parse_gpu_identity(
            "0, GPU-synthetic, Synthetic GPU, 81920, Default\n"
        )
        self.assertEqual(identity["index"], 0)
        self.assertEqual(identity["uuid"], "GPU-synthetic")
        self.assertNotIn("logical_device_confirmed", identity)
        self.assertFalse(identity["cpu_fallback"])

    def test_repository_pins_allow_a_later_authorization_commit(self):
        implementation = COMMIT
        runtime = "b" * 40
        snapshot = runner.assert_document_gates(opened_config(implementation))
        provenance = runner.assert_repository_pins(
            snapshot,
            repository_git(runtime, implementation),
        )
        self.assertEqual(provenance["mres"]["implementation_commit"], implementation)
        self.assertEqual(provenance["mres"]["authorization_commit"], runtime)
        self.assertNotEqual(
            provenance["mres"]["authorization_commit"],
            snapshot["executing_implementation_commit"],
        )
        self.assertEqual(
            snapshot["evidence_directory"],
            runner.evidence_directory_for_commit(implementation),
        )
        self.assertFalse(provenance["rnagenesis"]["runner_modified_repository"])
        self.assertIn("?? configs/", provenance["rnagenesis"]["dirty_tree_porcelain"])
        self.assertTrue(provenance["mres"]["runner_bytes_match_implementation"])

    def test_cli_exposes_only_output_dir_and_help(self):
        parser = runner.build_parser()
        option_strings = []
        for action in parser._actions:
            option_strings.extend(action.option_strings)
        self.assertEqual(set(option_strings), {"--output-dir", "-h", "--help"})
        recorder = RecordingDeps(real_config_bytes(), {})
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = runner.main(["-h"], deps=recorder.build())
        self.assertEqual(code, 0)
        self.assertEqual(recorder.events, [])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = runner.main(
                ["--output-dir", "/tmp/b1-not-the-evidence-path", "--seed", "1"],
                deps=recorder.build(),
            )
        self.assertEqual(code, 2)
        self.assertEqual(recorder.events, [])


def repository_git(runtime_head, implementation_commit, **overrides):
    blob = overrides.get("blob", "abc123")
    origin = overrides.get("origin", runtime_head)
    ancestor = overrides.get("ancestor", implementation_commit)
    mres_branch = overrides.get("mres_branch", "main")
    mres_status = overrides.get("mres_status", "")
    rna_status = overrides.get("rna_status", "?? configs/\n")
    rna_branch = overrides.get("rna_branch", runner.RNAGENESIS_BRANCH)
    rna_head = overrides.get("rna_head", runner.RNAGENESIS_HEAD)
    worktree_blob = overrides.get("worktree_blob", blob)
    impl_blob = overrides.get("impl_blob", blob)

    def git(repo, args):
        key = (str(repo), tuple(args))
        table = {
            (str(runner.MRES_ROOT), ("rev-parse", "HEAD")): runtime_head + "\n",
            (str(runner.MRES_ROOT), ("rev-parse", "--abbrev-ref", "HEAD")): mres_branch + "\n",
            (str(runner.MRES_ROOT), ("status", "--porcelain=v1")): mres_status,
            (str(runner.MRES_ROOT), ("rev-parse", "origin/main")): origin + "\n",
            (
                str(runner.MRES_ROOT),
                ("merge-base", implementation_commit, "HEAD"),
            ): ancestor + "\n",
            (
                str(runner.MRES_ROOT),
                (
                    "rev-parse",
                    "{}:{}".format(implementation_commit, runner.RUNNER_RELATIVE),
                ),
            ): impl_blob + "\n",
            (
                str(runner.MRES_ROOT),
                ("hash-object", "--", str(runner.RUNNER_PATH)),
            ): worktree_blob + "\n",
            (str(runner.RNAGENESIS_ROOT), ("rev-parse", "HEAD")): rna_head + "\n",
            (
                str(runner.RNAGENESIS_ROOT),
                ("rev-parse", "--abbrev-ref", "HEAD"),
            ): rna_branch + "\n",
            (str(runner.RNAGENESIS_ROOT), ("status", "--porcelain=v1")): rna_status,
        }
        if key not in table:
            raise AssertionError(key)
        return table[key]

    return git


def probe_payload(**overrides):
    payload = {
        "python_executable": runner.PINNED_PYTHON,
        "python_version": "3.11.0",
        "torch_version": "2.4.0",
        "cuda_version": "12.4",
        "cuda_available": True,
        "device_count": 1,
        "logical_device_index": 0,
        "logical_device": "cuda:0",
        "device_name": "Synthetic GPU",
        "logical_device_confirmed": True,
        "allocation_ok": True,
        "packages": {
            "numpy": "0",
            "torch": "2.4.0",
            "diffusers": "0",
            "transformers": "0",
            "omegaconf": "0",
            "tokenizers": "0",
            "rna-fm": "0",
            "ViennaRNA": "0",
        },
        "cuda_visible_devices": "0",
    }
    payload.update(overrides)
    return payload


def nvidia_smi_text(name="Synthetic GPU"):
    return "0, GPU-synthetic, {}, 81920, Default\n".format(name)


def attempt_for(length, cap, validity, cleaned, leading, trailing, termination):
    return {
        "requested_biological_length": length,
        "max_seq_len": cap,
        "validity": validity,
        "cleaned_length": cleaned,
        "leading_boundary_marker_run": leading,
        "trailing_boundary_marker_run": trailing,
        "termination_observation": termination,
    }


class RepositorySeparationTests(unittest.TestCase):
    def test_equal_commits_still_pass_when_the_tree_is_clean(self):
        snapshot = runner.assert_document_gates(opened_config(COMMIT))
        provenance = runner.assert_repository_pins(
            snapshot,
            repository_git(COMMIT, COMMIT),
        )
        self.assertEqual(provenance["mres"]["authorization_commit"], COMMIT)
        self.assertEqual(provenance["mres"]["implementation_commit"], COMMIT)

    def test_runtime_difference_passes_only_when_every_pin_holds(self):
        implementation = COMMIT
        runtime = "b" * 40
        snapshot = runner.assert_document_gates(opened_config(implementation))
        cases = [
            ({"mres_status": " M scripts/b1_generic_runner.py\n"}, "mres_worktree_dirty", "tracked"),
            ({"mres_status": "M  scripts/b1_generic_runner.py\n"}, "mres_worktree_dirty", "staged"),
            ({"mres_status": "?? notes.txt\n"}, "mres_worktree_dirty", "untracked"),
            ({"origin": "e" * 40}, "mres_origin_main_mismatch", "origin/main"),
            ({"ancestor": "e" * 40}, "mres_implementation_not_ancestor", "ancestor"),
            ({"worktree_blob": "different"}, "runner_bytes_mismatch", "byte-identical"),
            ({"rna_status": " M generation.py\n"}, "rnagenesis_worktree_dirty", "tracked"),
            ({"rna_status": "M  generation.py\n"}, "rnagenesis_worktree_dirty", "staged"),
            ({"rna_branch": "main"}, "rnagenesis_branch_mismatch", "mres-d1-diffusion-finetune"),
            ({"rna_status": "?? notes.txt\n"}, "rnagenesis_untracked_refused", "known RNAGenesis"),
        ]
        for overrides, code, detail in cases:
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.assert_repository_pins(
                    snapshot,
                    repository_git(runtime, implementation, **overrides),
                )
            self.assertEqual(caught.exception.code, code)
            self.assertIn(detail, caught.exception.detail)
        passing = runner.assert_repository_pins(
            snapshot,
            repository_git(
                runtime,
                implementation,
                rna_status="?? configs/\n?? checkpoints/\n",
            ),
        )
        self.assertEqual(passing["mres"]["origin_main"], runtime)
        self.assertEqual(passing["rnagenesis"]["branch"], runner.RNAGENESIS_BRANCH)
        self.assertEqual(passing["rnagenesis"]["head"], runner.RNAGENESIS_HEAD)


class CudaProbeTests(unittest.TestCase):
    def setUp(self):
        self.evidence = runner.evidence_directory_for_commit(COMMIT)
        self.env = runner.build_child_environment(
            {"CUDA_VISIBLE_DEVICES": "0"},
            self.evidence,
        )

    def preflight(self, text, payload):
        return runner.preflight_gpu(
            self.env,
            lambda: text,
            lambda: payload if isinstance(payload, str) else json.dumps(payload),
            resolve_python=lambda path: path,
        )

    def test_probe_confirms_logical_device_only_after_both_mocked_queries(self):
        calls = []

        def query():
            calls.append("nvidia-smi")
            return nvidia_smi_text()

        def probe():
            calls.append("torch-probe")
            return json.dumps(probe_payload())

        identity = runner.preflight_gpu(
            self.env,
            query,
            probe,
            resolve_python=lambda path: path,
        )
        self.assertEqual(calls, ["nvidia-smi", "torch-probe"])
        self.assertIs(identity["logical_device_confirmed"], True)
        self.assertEqual(identity["logical_device"], "cuda:0")
        self.assertEqual(identity["device_count"], 1)
        self.assertEqual(identity["device_name"], "Synthetic GPU")
        self.assertEqual(identity["packages"]["torch"], "2.4.0")
        self.assertEqual(
            set(identity["packages"]),
            set(runner.GENERATION_CRITICAL_DISTRIBUTIONS),
        )
        self.assertEqual(identity["python_executable"], runner.PINNED_PYTHON)
        generation_command = runner.build_subprocess_invocation(
            runner.build_phase_a_plan(real_config())[0],
            self.evidence,
            {"CUDA_VISIBLE_DEVICES": "0"},
        )
        self.assertEqual(generation_command["env"], self.env)
        self.assertEqual(generation_command["env"]["PYTHONDONTWRITEBYTECODE"], "1")
        command = runner.build_cuda_probe_command(self.env)
        generation = runner.build_generation_argv(
            runner.build_phase_a_plan(real_config())[0],
            runner.evidence_directory_for_commit(COMMIT),
            False,
        )
        self.assertIs(command["env"], self.env)
        self.assertEqual(command["argv"][0], generation[0])
        self.assertEqual(command["argv"][0], runner.PINNED_PYTHON)
        self.assertFalse(command["shell"])
        self.assertEqual(runner.physical_gpu_query_argv()[-2:], ["-i", "0"])
        source = inspect.getsource(runner.default_gpu_preflight)
        self.assertIn("default_query_gpu_text", source)
        self.assertIn("default_cuda_probe", source)
        self.assertIsNotNone(compile(runner.CUDA_PROBE_SOURCE, "<cuda-probe>", "exec"))
        self.assertNotIn("sys.executable", inspect.getsource(runner.build_generation_argv))

    def test_cpu_only_zero_multiple_allocation_and_malformed_probe_results_refuse(self):
        refusals = [
            (probe_payload(cuda_available=False, device_count=0, allocation_ok=False, logical_device_confirmed=False), "cuda_unavailable"),
            (probe_payload(device_count=0, allocation_ok=False, logical_device_confirmed=False), "cuda_device_count"),
            (probe_payload(device_count=2, allocation_ok=False, logical_device_confirmed=False), "cuda_device_count"),
            (probe_payload(allocation_ok=False, logical_device_confirmed=False, logical_device_index=None, logical_device=None), "cuda_allocation_failed"),
            ("not-json", "cuda_probe_malformed"),
            ("", "cuda_probe_malformed"),
            ("[]", "cuda_probe_malformed"),
            ("{", "cuda_probe_malformed"),
            (probe_payload(device_name="Other GPU"), "cuda_probe_mismatch"),
            (probe_payload(python_executable="/tmp/other-python"), "cuda_probe_mismatch"),
            (
                probe_payload(
                    packages={
                        name: "0"
                        for name in runner.GENERATION_CRITICAL_DISTRIBUTIONS
                        if name != "ViennaRNA"
                    }
                ),
                "cuda_probe_malformed",
            ),
        ]
        for payload, code in refusals:
            with self.assertRaises(runner.B1RunnerError) as caught:
                self.preflight(nvidia_smi_text(), payload)
            self.assertEqual(caught.exception.code, code)


class DiagnosticTests(unittest.TestCase):
    def test_cap_diagnostics_and_zero_valid_exact_hit_rate(self):
        zero = [
            attempt_for(20, 22, False, 0, "11", "2", runner.EOS_OBSERVED),
            attempt_for(20, 22, False, 20, "", "", runner.TERMINATION_NOT_OBSERVABLE),
        ]
        diagnostics = runner.sequence_only_diagnostics(zero)
        row = diagnostics["per_candidate"][0]
        self.assertEqual(row["raw_attempts"], 2)
        self.assertEqual(row["valid_outputs"], 0)
        self.assertEqual(row["invalid_outputs"], 2)
        self.assertEqual(row["exact_hits"], 0)
        self.assertEqual(row["exact_hit_rate"], 0.0)
        self.assertEqual(diagnostics["per_requested_length"][0]["exact_hit_rate"], 0.0)
        self.assertEqual(diagnostics["overall_exact_hit_rate"], 0.0)
        self.assertEqual(diagnostics["raw_attempts"], 2)
        self.assertEqual(diagnostics["valid_outputs"], 0)
        self.assertEqual(diagnostics["exact_hits"], 0)
        self.assertEqual(row["eos_marker_observed_count"], 1)
        self.assertEqual(diagnostics["cap_selection"], "not_made")
        self.assertEqual(diagnostics["phase_b_mapping"], "not_inferred")
        mixed = [
            attempt_for(20, 20, True, 20, "11", "", runner.TERMINATION_NOT_OBSERVABLE),
            attempt_for(20, 20, True, 18, "11", "2", runner.EOS_OBSERVED),
            attempt_for(20, 20, False, 0, "", "", runner.TERMINATION_NOT_OBSERVABLE),
        ]
        mixed_row = runner.sequence_only_diagnostics(mixed)["per_candidate"][0]
        self.assertEqual(mixed_row["raw_attempts"], 3)
        self.assertEqual(mixed_row["valid_outputs"], 2)
        self.assertEqual(mixed_row["invalid_outputs"], 1)
        self.assertEqual(mixed_row["exact_hits"], 1)
        self.assertEqual(mixed_row["exact_hit_rate"], 0.5)
        self.assertEqual(
            mixed_row["cleaned_length_distribution"],
            [{"value": 0, "count": 1}, {"value": 18, "count": 1}, {"value": 20, "count": 1}],
        )
        self.assertEqual(mixed_row["leading_boundary_distribution"][0]["value"], "")
        self.assertEqual(mixed_row["eos_marker_observed_count"], 1)
        self.assertNotIn("selected_cap", runner.sequence_only_diagnostics(mixed))


class EvidenceFinalizationTests(unittest.TestCase):
    def generation_bytes(self, invocation_index):
        lines = ["11ACGU"] * 16
        if invocation_index == 0:
            lines[-1] = "ACGT"
        return ("".join(line + "\n" for line in lines)).encode("utf-8")

    def subprocess_run(self, argv, cwd, env, shell=False):
        self.assertFalse(shell)
        self.assertEqual(argv[0], runner.PINNED_PYTHON)
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0")
        mid = argv[argv.index("--mid_folder") + 1]
        remark = argv[argv.index("--remark") + 1]
        folder = Path(argv[argv.index("--superfolder") + 1]) / mid
        folder.mkdir(parents=True, exist_ok=False)
        invocation_index = int(mid.split("_")[1])
        (
            folder / runner.predicted_generation_filename(remark)
        ).write_bytes(self.generation_bytes(invocation_index))

    def prepared(self, tmp):
        config = opened_config()
        return {
            "output_dir": tmp,
            "config": config,
            "snapshot": runner.assert_document_gates(config),
            "plan": runner.build_phase_a_plan(config),
            "provenance": {
                "mres": {
                    "authorization_commit": "b" * 40,
                    "implementation_commit": COMMIT,
                }
            },
            "pins": [
                {
                    "role": "diffusion_unet_weights",
                    "path": "synthetic-weight",
                    "sha256": "c" * 64,
                    "size": 1,
                }
            ],
            "gpu": {
                "python_resolved_path": runner.PINNED_PYTHON,
                "python_version": "3.11.0",
                "packages": {"torch": "2.4.0"},
                "logical_device_confirmed": True,
            },
            "input_hashes": {
                "configuration": runner.file_content_record(
                    runner.B1_CONFIG_PATH,
                    dumped(config),
                ),
                "runner": runner.file_content_record(runner.RUNNER_PATH, b"runner-bytes"),
            },
            "started_at": "2026-09-30T00:00:00Z",
        }

    def deps(self, subprocess_run=None, write_exclusive=None, read_bytes=None):
        return runner.RunnerDependencies(
            read_bytes=read_bytes or runner.default_read_bytes,
            lstat=os.lstat,
            environ={"CUDA_VISIBLE_DEVICES": "0", "HF_HUB_OFFLINE": "0"},
            write_exclusive=write_exclusive or runner.write_exclusive_bytes,
            subprocess_run=subprocess_run or self.subprocess_run,
            load_cleaner=runner.default_load_cleaner,
            clock=lambda: "2026-09-30T00:02:00Z",
            hostname=lambda: "synthetic-test-host",
        )

    def test_failure_after_each_evidence_writing_stage(self):
        stages = [
            runner.RAW_LEDGER_NAME,
            runner.AUDITED_LEDGER_NAME,
            runner.HASH_REPORT_NAME,
            runner.SUCCESS_MANIFEST_NAME,
        ]
        for fail_name in stages:
            with tempfile.TemporaryDirectory() as tmp:
                def write_exclusive(path, data, fail_name=fail_name):
                    if Path(path).name == fail_name:
                        raise runner.B1RunnerError(
                            "evidence_write_failed",
                            "injected write failure",
                        )
                    runner.write_exclusive_bytes(path, data)

                prepared = self.prepared(tmp)
                with self.assertRaises(runner.B1RunnerError) as caught:
                    runner.after_directory_created(
                        tmp,
                        self.deps(write_exclusive=write_exclusive),
                        lambda: runner.execute_phase_a(prepared, self.deps(write_exclusive=write_exclusive)),
                        prepared,
                    )
                self.assertEqual(caught.exception.code, "evidence_write_failed")
                self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())
                failure = Path(tmp) / runner.FAILURE_MANIFEST_NAME
                self.assertTrue(failure.exists())
                document = json.loads(failure.read_text(encoding="utf-8"))
                self.assertEqual(document["status"], "failed")
                self.assertEqual(document["failure"]["attempt_count"], 528)
                self.assertEqual(
                    document["failure"]["completed_invocation_indexes"],
                    list(range(33)),
                )
                self.assertEqual(len(document["hashes"]["raw_outputs"]), 33)
                self.assertEqual(document["hashes"]["configuration"]["sha256"], prepared["input_hashes"]["configuration"]["sha256"])
                self.assertEqual(document["hashes"]["runner"]["byte_count"], len(b"runner-bytes"))
                self.assertEqual(document["hashes"]["pinned_assets"][0]["sha256"], "c" * 64)
                self.assertNotIn("manifest_sha256", document["hashes"])
                if fail_name == runner.RAW_LEDGER_NAME:
                    self.assertIsNone(document["hashes"]["raw_ledger_sha256"])
                if fail_name == runner.SUCCESS_MANIFEST_NAME:
                    self.assertTrue((Path(tmp) / runner.HASH_REPORT_NAME).exists())
                    self.assertIsNotNone(document["hashes"]["audited_ledger_sha256"])

    def test_operational_failures_omit_sequence_text(self):
        secret = "ACGUACGUACGUACGU"

        def failing_process(argv, cwd, env, shell=False):
            raise subprocess.CalledProcessError(1, argv, stderr=secret)

        def missing_read(path):
            raise FileNotFoundError(secret)

        def filesystem_read(path):
            raise PermissionError(secret)

        def decode_read(path):
            return secret.encode("utf-16")

        cases = [
            (failing_process, runner.default_read_bytes, "generation_process_failed"),
            (self.subprocess_run, missing_read, "output_file_missing"),
            (self.subprocess_run, filesystem_read, "filesystem_error"),
            (self.subprocess_run, decode_read, "output_decode_failed"),
        ]
        for subprocess_run, read_bytes, code in cases:
            with tempfile.TemporaryDirectory() as tmp:
                prepared = self.prepared(tmp)
                deps = self.deps(subprocess_run=subprocess_run, read_bytes=read_bytes)
                with self.assertRaises(runner.B1RunnerError) as caught:
                    runner.after_directory_created(
                        tmp,
                        deps,
                        lambda: runner.execute_phase_a(prepared, deps),
                        prepared,
                    )
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(secret, caught.exception.detail)
                failure = (Path(tmp) / runner.FAILURE_MANIFEST_NAME).read_text(encoding="utf-8")
                self.assertNotIn(secret, failure)
                self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())

    def test_live_context_and_manifests_do_not_coexist(self):
        def subprocess_run(argv, cwd, env, shell=False):
            mid = argv[argv.index("--mid_folder") + 1]
            if mid == "invocation_01":
                raise subprocess.CalledProcessError(1, argv)
            self.subprocess_run(argv, cwd, env, shell=shell)

        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepared(tmp)
            deps = self.deps(subprocess_run=subprocess_run)
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.after_directory_created(
                    tmp,
                    deps,
                    lambda: runner.execute_phase_a(prepared, deps),
                    prepared,
                )
            self.assertEqual(caught.exception.code, "generation_process_failed")
            document = json.loads(
                (Path(tmp) / runner.FAILURE_MANIFEST_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(document["progress"]["completed_invocation_indexes"], [0])
            self.assertEqual(document["failure"]["attempt_count"], 16)
            self.assertEqual(len(document["failure"]["raw_outputs"]), 1)
            self.assertEqual(document["failure"]["raw_outputs"][0]["line_count"], 16)
            self.assertEqual(document["failure"]["raw_outputs"][0]["invocation_index"], 0)
            self.assertEqual(len(document["commands"]), 2)
            self.assertNotIn("raw_decoded_text", document["failure"]["raw_outputs"][0])
            self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / runner.SUCCESS_MANIFEST_NAME).write_bytes(b"{}\n")
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.record_failure(
                    tmp,
                    runner.B1RunnerError("evidence_write_failed", "injected write failure"),
                    self.deps(),
                    {},
                )
            self.assertEqual(caught.exception.code, "success_marker_present")
            self.assertFalse((Path(tmp) / runner.FAILURE_MANIFEST_NAME).exists())


class MockedRunTests(unittest.TestCase):
    def test_mocked_run_records_distinct_ledgers_and_input_hashes(self):
        implementation = COMMIT
        runtime = "b" * 40
        evidence = Path(runner.evidence_directory_for_commit(implementation))
        self.assertFalse(evidence.exists())
        self.assertFalse(REAL_EVIDENCE.exists())
        config_bytes = dumped(opened_config(implementation))
        runner_bytes = runner.RUNNER_PATH.read_bytes()
        parent = {"CUDA_VISIBLE_DEVICES": "0", "HF_HUB_OFFLINE": "0", "MARKER": "keep"}
        outputs = {}
        seen = {}
        probe_order = []
        write_order = []

        def read_bytes(path):
            if Path(path) == runner.B1_CONFIG_PATH:
                return config_bytes
            if Path(path) == runner.RUNNER_PATH:
                return runner_bytes
            if Path(path) == runner.APPROVED_CLEANER:
                return runner.APPROVED_CLEANER.read_bytes()
            if str(path) in outputs:
                return outputs[str(path)]
            raise AssertionError(path)

        def lstat(path):
            text = str(path)
            if text in outputs:
                return FakeStat(stat.S_IFREG, len(outputs[text]))
            if text == str(evidence) or "rnagenesis_generation_output" in text:
                raise FileNotFoundError(text)
            for asset in runner.PINNED_FILES:
                if text == str(asset.absolute_path()):
                    size = asset.size if asset.size is not None else 3
                    return FakeStat(stat.S_IFREG, size)
            raise FileNotFoundError(text)

        def sha256_file(path):
            text = str(path)
            for asset in runner.PINNED_FILES:
                if text == str(asset.absolute_path()):
                    return asset.sha256
            raise AssertionError(text)

        def gpu_preflight(env):
            seen["env"] = dict(env)

            def query():
                probe_order.append("nvidia-smi")
                return nvidia_smi_text()

            def probe():
                probe_order.append("torch-probe")
                return json.dumps(probe_payload())

            return runner.preflight_gpu(
                env,
                query,
                probe,
                resolve_python=lambda path: path,
            )

        def subprocess_run(argv, cwd, env, shell=False):
            self.assertFalse(shell)
            self.assertEqual(cwd, "/home/laura/RNAGenesis")
            self.assertEqual(argv[0], runner.PINNED_PYTHON)
            self.assertEqual(dict(env), seen["env"])
            self.assertEqual(parent["HF_HUB_OFFLINE"], "0")
            self.assertEqual(env["HF_HUB_OFFLINE"], "1")
            mid = argv[argv.index("--mid_folder") + 1]
            remark = argv[argv.index("--remark") + 1]
            predicted = str(
                Path(argv[argv.index("--superfolder") + 1])
                / mid
                / runner.predicted_generation_filename(remark)
            )
            lines = ["11ACGU"] * 16
            if mid == "invocation_00":
                lines[-1] = "ACGT"
            outputs[predicted] = ("".join(line + "\n" for line in lines)).encode("utf-8")
            preserved[predicted] = outputs[predicted]

        preserved = {}

        with tempfile.TemporaryDirectory() as tmp:
            def write_exclusive(path, data):
                self.assertEqual(Path(path).parent, evidence)
                write_order.append(Path(path).name)
                runner.write_exclusive_bytes(Path(tmp) / Path(path).name, data)

            deps = runner.RunnerDependencies(
                read_bytes=read_bytes,
                lstat=lstat,
                realpath=lambda path: str(path),
                sha256_file=sha256_file,
                environ=parent,
                git=repository_git(runtime, implementation),
                gpu_preflight=gpu_preflight,
                mkdir=lambda path: seen.setdefault("mkdir", []).append(path),
                write_exclusive=write_exclusive,
                subprocess_run=subprocess_run,
                load_cleaner=runner.default_load_cleaner,
                clock=lambda: "2026-09-30T00:03:00Z",
                hostname=lambda: "synthetic-test-host",
            )
            manifest = runner.run(str(evidence), deps)
            self.assertEqual(probe_order, ["nvidia-smi", "torch-probe"])
            self.assertEqual(seen["mkdir"], [str(evidence)])
            self.assertEqual(write_order[-1], runner.SUCCESS_MANIFEST_NAME)
            self.assertEqual(write_order[-2], runner.HASH_REPORT_NAME)
            self.assertEqual(
                write_order,
                [
                    runner.RAW_LEDGER_NAME,
                    runner.AUDITED_LEDGER_NAME,
                    runner.HASH_REPORT_NAME,
                    runner.SUCCESS_MANIFEST_NAME,
                ],
            )
            self.assertEqual(manifest["authorization_runtime_commit"], runtime)
            self.assertEqual(
                manifest["authorization"]["executing_implementation_commit"],
                implementation,
            )
            self.assertNotEqual(
                manifest["authorization_runtime_commit"],
                manifest["authorization"]["executing_implementation_commit"],
            )
            self.assertIs(manifest["gpu_identity"]["logical_device_confirmed"], True)
            self.assertEqual(manifest["hashes"]["python"]["executable"], runner.PINNED_PYTHON)
            self.assertEqual(manifest["hashes"]["python"]["version"], "3.11.0")
            self.assertEqual(manifest["hashes"]["packages"]["torch"], "2.4.0")
            self.assertEqual(
                set(manifest["hashes"]["packages"]),
                set(runner.GENERATION_CRITICAL_DISTRIBUTIONS),
            )
            self.assertEqual(manifest["final_raw_output_verification"]["passed"], True)
            self.assertEqual(manifest["final_raw_output_verification"]["file_count"], 33)
            self.assertEqual(
                manifest["child_environment_controls"]["PYTHONDONTWRITEBYTECODE"],
                "1",
            )
            self.assertTrue(
                manifest["child_environment_controls"]["PYTHONPYCACHEPREFIX"].startswith(
                    str(evidence) + "/python_pycache"
                )
            )
            self.assertTrue(
                manifest["child_environment_controls"]["HF_HOME"].startswith(
                    str(evidence) + "/isolated_runtime_cache/"
                )
            )
            patch_pins = [
                item
                for item in manifest["pinned_inputs"]
                if item["role"] == "diffusers_normalization_patch"
            ]
            self.assertEqual(len(patch_pins), 1)
            self.assertEqual(patch_pins[0]["path"], runner.DIFFUSERS_PATCH_PATH)
            self.assertEqual(patch_pins[0]["size"], runner.DIFFUSERS_PATCH_SIZE)
            self.assertEqual(patch_pins[0]["sha256"], runner.DIFFUSERS_PATCH_SHA256)
            self.assertEqual(
                manifest["hashes"]["configuration"],
                runner.file_content_record(runner.B1_CONFIG_PATH, config_bytes),
            )
            self.assertEqual(
                manifest["hashes"]["runner"],
                runner.file_content_record(runner.RUNNER_PATH, runner_bytes),
            )
            self.assertEqual(len(manifest["hashes"]["raw_outputs"]), 33)
            self.assertEqual(len(manifest["hashes"]["pinned_assets"]), len(runner.PINNED_FILES))
            self.assertNotIn("manifest_sha256", json.dumps(manifest))
            indexes = []
            for item in manifest["hashes"]["raw_outputs"]:
                indexes.append(item["invocation_index"])
                self.assertEqual(item["byte_count"], len(preserved[item["path"]]))
                self.assertEqual(
                    item["sha256"],
                    hashlib.sha256(preserved[item["path"]]).hexdigest(),
                )
                self.assertEqual(preserved[item["path"]], outputs[item["path"]])
                self.assertEqual(item["line_count"], 16)
                self.assertIn("cap", item)
                self.assertIn("seed", item)
                self.assertIn("requested_biological_length", item)
            self.assertEqual(indexes, list(range(33)))
            raw_rows = [
                json.loads(line)
                for line in (Path(tmp) / runner.RAW_LEDGER_NAME).read_text(encoding="utf-8").splitlines()
            ]
            audited_rows = [
                json.loads(line)
                for line in (Path(tmp) / runner.AUDITED_LEDGER_NAME).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(raw_rows), 528)
            self.assertEqual(len(audited_rows), 528)
            self.assertNotEqual(set(raw_rows[0]), set(audited_rows[0]))
            self.assertNotEqual(
                manifest["hashes"]["raw_ledger_sha256"],
                manifest["hashes"]["audited_ledger_sha256"],
            )
            self.assertEqual(
                [row["attempt_within_candidate"] for row in audited_rows[:16]],
                list(range(16)),
            )
            self.assertEqual(
                [row["attempt_index"] for row in audited_rows[:16]],
                list(range(16)),
            )
            self.assertTrue(
                all(row["pairing_group"] == row["requested_biological_length"] for row in audited_rows)
            )
            self.assertTrue(
                all(
                    row["max_seq_len"] == row["requested_biological_length"] + row["cap_offset"]
                    for row in audited_rows
                )
            )
            self.assertEqual(manifest["sequence_only_diagnostics"]["cap_selection"], "not_made")
            self.assertEqual(manifest["sequence_only_diagnostics"]["phase_b_mapping"], "not_inferred")
            self.assertEqual(len(manifest["sequence_only_diagnostics"]["per_candidate"]), 33)
            self.assertEqual(parent["MARKER"], "keep")
            self.assertFalse((Path(tmp) / runner.FAILURE_MANIFEST_NAME).exists())
        self.assertFalse(evidence.exists())
        self.assertFalse(REAL_EVIDENCE.exists())


class AcceptanceCorrectionTests(unittest.TestCase):
    def test_runtime_caches_stay_inside_the_evidence_directory(self):
        evidence = runner.evidence_directory_for_commit(COMMIT)
        parent = {"CUDA_VISIBLE_DEVICES": "0", "HF_HUB_OFFLINE": "0"}
        before = dict(parent)
        child = runner.build_child_environment(parent, evidence)
        invocation = runner.build_subprocess_invocation(
            runner.build_phase_a_plan(real_config())[0],
            evidence,
            parent,
        )
        probe = runner.build_cuda_probe_command(child)
        self.assertEqual(parent, before)
        self.assertEqual(invocation["env"], child)
        self.assertIs(probe["env"], child)
        self.assertEqual(child["PYTHONDONTWRITEBYTECODE"], "1")
        for key in (
            "PYTHONPYCACHEPREFIX",
            "HF_HOME",
            "HUGGINGFACE_HUB_CACHE",
            "HF_HUB_CACHE",
            "TRANSFORMERS_CACHE",
            "TORCH_HOME",
        ):
            self.assertTrue(child[key].startswith(evidence + "/"), key)
            self.assertFalse(child[key].startswith("/home/laura/RNAGenesis"), key)
        self.assertFalse(Path(evidence).exists())
        self.assertFalse(Path(child["PYTHONPYCACHEPREFIX"]).exists())
        self.assertFalse(Path(child["HF_HOME"]).exists())
        compiled = compile(runner.CUDA_PROBE_SOURCE, "<cuda-probe>", "exec")
        self.assertIsNotNone(compiled)
        for distribution, _module_name in runner.GENERATION_CRITICAL_PACKAGES:
            self.assertIn(repr(distribution), runner.CUDA_PROBE_SOURCE)
        self.assertIn("importlib.metadata", runner.CUDA_PROBE_SOURCE)
        source = (ROOT / "scripts" / "b1_generic_runner.py").read_text(encoding="utf-8")
        self.assertNotIn("spec_from_file_location", source)
        for name in FORBIDDEN_RUNTIME_MODULES:
            self.assertNotIn(name, sys.modules)

        def realpath(path):
            if str(path).endswith("python_pycache"):
                return "/home/laura/RNAGenesis/.cache"
            return str(path)

        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.build_child_environment(parent, evidence, realpath=realpath)
        self.assertEqual(caught.exception.code, "runtime_cache_not_isolated")

    def test_cleaner_loads_from_verified_source_bytes(self):
        source = runner.APPROVED_CLEANER.read_bytes()
        module = runner.load_cleaner_from_verified_source(source)
        self.assertTrue(callable(module.audit_line))
        self.assertTrue(callable(module.split_raw_records))
        self.assertNotIn("b1_approved_audit_generation_output", sys.modules)
        again = runner.default_load_cleaner(source)
        self.assertIsNot(module, again)
        self.assertEqual(again.audit_line(1, "11ACGU")["cleaned"], "ACGU")
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.load_cleaner_from_verified_source(source + b"\n")
        self.assertEqual(caught.exception.code, "pinned_file_hash_mismatch")
        self.assertNotIn("spec_from_file_location", (ROOT / "scripts" / "b1_generic_runner.py").read_text(encoding="utf-8"))

    def test_unexpected_exceptions_keep_their_classification_when_evidence_write_fails(self):
        secret = "ACGUACGUACGUACGU"
        deps = runner.RunnerDependencies(
            clock=lambda: "2026-09-30T00:04:00Z",
            hostname=lambda: "synthetic-test-host",
        )
        for exc_type in (KeyError, TypeError):
            with tempfile.TemporaryDirectory() as tmp:

                def operation(exc_type=exc_type):
                    raise exc_type(secret)

                with self.assertRaises(runner.B1RunnerError) as caught:
                    runner.after_directory_created(tmp, deps, operation, {"config": {}, "snapshot": {}})
                self.assertEqual(caught.exception.code, "unexpected_runtime_failure")
                self.assertNotIn(secret, caught.exception.detail)
                self.assertIsNone(caught.exception.secondary_failure)
                failure = Path(tmp) / runner.FAILURE_MANIFEST_NAME
                success = Path(tmp) / runner.SUCCESS_MANIFEST_NAME
                self.assertFalse(success.exists())
                document = json.loads(failure.read_text(encoding="utf-8"))
                self.assertEqual(document["status"], "failed")
                self.assertEqual(document["failure"]["code"], "unexpected_runtime_failure")
                self.assertNotIn(secret, failure.read_text(encoding="utf-8"))
                self.assertNotIn("manifest_sha256", document["hashes"])
                self.assertFalse(document["final_raw_output_verification"]["passed"])

        with tempfile.TemporaryDirectory() as tmp:
            def write_exclusive(path, data):
                if Path(path).name == runner.FAILURE_MANIFEST_NAME:
                    raise OSError(secret)
                runner.write_exclusive_bytes(path, data)

            failing_deps = runner.RunnerDependencies(
                write_exclusive=write_exclusive,
                clock=lambda: "2026-09-30T00:04:00Z",
                hostname=lambda: "synthetic-test-host",
            )

            def operation():
                raise runner.B1RunnerError(
                    "invocation_output_line_count",
                    "expected 16 output lines and observed 15",
                )

            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.after_directory_created(tmp, failing_deps, operation, {"config": {}, "snapshot": {}})
            self.assertEqual(caught.exception.code, "invocation_output_line_count")
            self.assertEqual(caught.exception.secondary_failure, "failure_manifest_write_failed")
            self.assertNotIn(secret, caught.exception.detail)
            self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())
            self.assertFalse((Path(tmp) / runner.FAILURE_MANIFEST_NAME).exists())

    def test_keyboard_interrupt_and_system_exit_are_not_classified(self):
        deps = runner.RunnerDependencies(
            clock=lambda: "2026-09-30T00:04:00Z",
            hostname=lambda: "synthetic-test-host",
        )
        for exc_type in (KeyboardInterrupt, SystemExit):
            with tempfile.TemporaryDirectory() as tmp:
                def operation(exc_type=exc_type):
                    raise exc_type()

                with self.assertRaises(exc_type):
                    runner.after_directory_created(
                        tmp,
                        deps,
                        operation,
                        {"config": {}, "snapshot": {}},
                    )
                self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())
                self.assertFalse((Path(tmp) / runner.FAILURE_MANIFEST_NAME).exists())

    def test_typeerror_after_a_completed_invocation_retains_safe_progress(self):
        secret = "ACGUACGUACGUACGU"
        with tempfile.TemporaryDirectory() as tmp:
            config = opened_config()
            prepared = {
                "output_dir": tmp,
                "config": config,
                "snapshot": runner.assert_document_gates(config),
                "plan": runner.build_phase_a_plan(config),
                "provenance": None,
                "pins": [],
                "gpu": None,
                "started_at": "2026-09-30T00:00:00Z",
            }

            def subprocess_run(argv, cwd, env, shell=False):
                mid = argv[argv.index("--mid_folder") + 1]
                if mid == "invocation_01":
                    raise TypeError(secret)
                remark = argv[argv.index("--remark") + 1]
                folder = Path(argv[argv.index("--superfolder") + 1]) / mid
                folder.mkdir(parents=True, exist_ok=False)
                payload = ("11ACGU\n" * 16).encode("utf-8")
                (folder / runner.predicted_generation_filename(remark)).write_bytes(payload)

            deps = runner.RunnerDependencies(
                read_bytes=runner.default_read_bytes,
                lstat=os.lstat,
                environ={"CUDA_VISIBLE_DEVICES": "0"},
                write_exclusive=runner.write_exclusive_bytes,
                subprocess_run=subprocess_run,
                load_cleaner=runner.default_load_cleaner,
                clock=lambda: "2026-09-30T00:06:00Z",
                hostname=lambda: "synthetic-test-host",
            )
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.after_directory_created(
                    tmp,
                    deps,
                    lambda: runner.execute_phase_a(prepared, deps),
                    prepared,
                )
            self.assertEqual(caught.exception.code, "unexpected_runtime_failure")
            self.assertNotIn(secret, caught.exception.detail)
            self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())
            document = json.loads(
                (Path(tmp) / runner.FAILURE_MANIFEST_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(document["failure"]["completed_invocation_indexes"], [0])
            self.assertEqual(document["failure"]["attempt_count"], 16)
            self.assertEqual(len(document["commands"]), 2)
            self.assertNotIn(secret, json.dumps(document))


class RawOutputVerificationTests(unittest.TestCase):
    def generation_bytes(self, invocation_index):
        lines = ["11ACGU"] * 16
        if invocation_index == 0:
            lines[-1] = "ACGT"
        return ("".join(line + "\n" for line in lines)).encode("utf-8")

    def subprocess_run(self, argv, cwd, env, shell=False):
        mid = argv[argv.index("--mid_folder") + 1]
        remark = argv[argv.index("--remark") + 1]
        folder = Path(argv[argv.index("--superfolder") + 1]) / mid
        folder.mkdir(parents=True, exist_ok=False)
        invocation_index = int(mid.split("_")[1])
        (folder / runner.predicted_generation_filename(remark)).write_bytes(
            self.generation_bytes(invocation_index)
        )

    def prepared(self, tmp):
        config = opened_config()
        return {
            "output_dir": tmp,
            "config": config,
            "snapshot": runner.assert_document_gates(config),
            "plan": runner.build_phase_a_plan(config),
            "provenance": {"mres": {"authorization_commit": "b" * 40}},
            "pins": [],
            "gpu": {"packages": {"torch": "2.4.0"}, "logical_device_confirmed": True},
            "started_at": "2026-09-30T00:00:00Z",
        }

    def run_case(self, mutate):
        secret = "ACGUACGUACGUACGU"
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepared(tmp)
            target = runner.predicted_generation_path(tmp, prepared["plan"][0])

            def subprocess_run(argv, cwd, env, shell=False):
                self.subprocess_run(argv, cwd, env, shell=shell)
                if argv[argv.index("--mid_folder") + 1] == "invocation_32":
                    mutate(target, secret)

            deps = runner.RunnerDependencies(
                read_bytes=runner.default_read_bytes,
                lstat=os.lstat,
                environ={"CUDA_VISIBLE_DEVICES": "0"},
                write_exclusive=runner.write_exclusive_bytes,
                subprocess_run=subprocess_run,
                load_cleaner=runner.default_load_cleaner,
                clock=lambda: "2026-09-30T00:05:00Z",
                hostname=lambda: "synthetic-test-host",
            )
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.after_directory_created(
                    tmp,
                    deps,
                    lambda: runner.execute_phase_a(prepared, deps),
                    prepared,
                )
            self.assertEqual(caught.exception.code, "raw_output_verification_failed")
            self.assertNotIn(secret, caught.exception.detail)
            success = Path(tmp) / runner.SUCCESS_MANIFEST_NAME
            failure = Path(tmp) / runner.FAILURE_MANIFEST_NAME
            report = Path(tmp) / runner.HASH_REPORT_NAME
            self.assertFalse(success.exists())
            self.assertFalse(report.exists())
            self.assertTrue(failure.exists())
            text = failure.read_text(encoding="utf-8")
            self.assertNotIn(secret, text)
            document = json.loads(text)
            self.assertEqual(document["status"], "failed")
            self.assertEqual(document["failure"]["code"], "raw_output_verification_failed")
            self.assertEqual(document["failure"]["attempt_count"], 528)
            self.assertEqual(document["failure"]["completed_invocation_indexes"], list(range(33)))
            self.assertFalse(document["final_raw_output_verification"]["passed"])
            self.assertFalse(REAL_EVIDENCE.exists())

    def test_mutated_deleted_truncated_and_replaced_raw_files_refuse_success(self):
        secret = "ACGUACGUACGUACGU"

        def mutate(path, _secret):
            payload = bytearray(Path(path).read_bytes())
            payload[-2] = payload[-2] ^ 0x01
            Path(path).write_bytes(bytes(payload))

        def delete(path, _secret):
            Path(path).unlink()

        def truncate(path, _secret):
            Path(path).write_bytes(b"")

        def replace(path, marker):
            Path(path).write_bytes((marker + "\n").encode("utf-8"))

        def symlink(path, _secret):
            path = Path(path)
            other = path.parent / "other.txt"
            other.write_bytes(b"replacement\n")
            path.unlink()
            path.symlink_to(other.name)

        for operation in (mutate, delete, truncate, replace, symlink):
            self.run_case(operation)

    def test_line_count_mismatch_refuses_without_a_success_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = ("11ACGU\n" * 16).encode("utf-8")
            outputs = []
            for index in range(33):
                path = Path(tmp) / "raw_{:02d}.txt".format(index)
                path.write_bytes(payload)
                item = {
                    "path": str(path),
                    "byte_count": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "line_count": 16,
                }
                outputs.append(item)
            outputs[0]["line_count"] = 15
            context = {"raw_outputs": outputs}
            cleaner = runner.default_load_cleaner()
            deps = runner.RunnerDependencies(
                read_bytes=runner.default_read_bytes,
                lstat=os.lstat,
            )
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.verify_retained_raw_outputs(context, deps, cleaner)
            self.assertEqual(caught.exception.code, "raw_output_verification_failed")
            self.assertIn("line count", caught.exception.detail)
            self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())


def os_lstat(path):
    return os.lstat(path)


if __name__ == "__main__":
    unittest.main()

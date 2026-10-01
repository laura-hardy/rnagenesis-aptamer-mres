"""Synthetic tests for the B1 Phase A runner.

These tests do not load a model, initialise CUDA, query a GPU, open
biological sequence data, execute RNAGenesis generation, or create an
evidence directory. External operations are injected. Cleaning tests
call the approved pure-Python audit functions on synthetic strings.
The checked-in configuration records consumed, complete physical GPU 1
Phase A and Phase B authorisations. Accepted Phase A evidence and
accepted Phase B evidence are snapshotted and must remain unchanged.
Shared document and execution gates are closed. Phase A remains
non-executable. The revoked, unconsumed GPU 0 authorisation is retained
as historical provenance. Globally closed cases use synthetic copies.
"""

from __future__ import annotations

import ast
import collections
import collections.abc
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
from unittest import mock
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
IMPLEMENTATION_COMMIT = "de60793a66d134e1d4b48bfe9ac9c5abe3874758"
AUTHORISATION_ID = "m4_b1_phase_a_de60793a66d1_gpu1_attempt1"
AUTHORIZATION_COMMIT = "f1d8e78dece7a611c14275f606e57c4cbdb30691"
CANDIDATE_STATUS = (
    "APPROVED_CANDIDATE_FOR_PHASE_B_EVALUATION_NOT_FINAL_PRODUCTION_MAPPING"
)
CANDIDATE_FORMULA = "max_seq_len = requested_biological_length + 1"
REAL_EVIDENCE = Path(
    "/home/laura/rnagenesis-mres-runs/"
    "m4_b1_generic_generation_B1_generic_released_rnagenesis_de60793a66d1_phaseA"
)
HISTORICAL_IMPLEMENTATION_COMMIT = "bdb3dbda1650a3bd65407e1deadcf0862249f972"
HISTORICAL_AUTHORISATION_ID = "m4_b1_phase_a_bdb3dbda1650_gpu0_attempt1"
HISTORICAL_EVIDENCE = Path(
    "/home/laura/rnagenesis-mres-runs/"
    "m4_b1_generic_generation_B1_generic_released_rnagenesis_bdb3dbda1650_phaseA"
)
PHASE_B_IMPLEMENTATION_COMMIT = "688b18f88f21b427edb9e3e2a79130cc92485440"
PHASE_B_AUTHORISATION_ID = "m4_b1_phase_b_688b18f88f21_gpu1_attempt1"
PHASE_B_EVIDENCE = Path(
    "/home/laura/rnagenesis-mres-runs/"
    "m4_b1_generic_generation_B1_generic_released_rnagenesis_688b18f88f21_phaseB"
)
EXPECTED_PHASE_B_SHA256 = {
    "phase_b_manifest.json": (
        "49cd5b773a0701606ba63f9b28c03cfb6a4aee32865e7f65a4e849481d628de7"
    ),
    "phase_b_manifest_sha256.json": (
        "c81f628389e257bb1e5bb7577e3450c55348ececbb44c2a11b15a299fb0a088e"
    ),
    "phase_b_raw_attempts.jsonl": (
        "bc8baf3f1dd8f9f1e21efd4a8489a0ccec9908f5ed9a6723cab60a2f68366c9b"
    ),
    "phase_b_audited_attempts.jsonl": (
        "a20911c33d647fb3de1fdc0c8a32d944e33e124e37ab76dd481631cbde52259a"
    ),
}
EVIDENCE_KEY_FILES = (
    "phase_a_manifest.json",
    "phase_a_manifest_sha256.json",
    "phase_a_raw_attempts.jsonl",
    "phase_a_audited_attempts.jsonl",
)
EXPECTED_EVIDENCE_SHA256 = {
    "phase_a_manifest.json": (
        "582fe16d622660c5d305cd4763b1fd8091c3c773798fbf94f0ec723d8322c47a"
    ),
    "phase_a_manifest_sha256.json": (
        "79d43c43d42539eb9da2339b1f0dd8917b108c28c64da22059e43ec0ebbcbfe1"
    ),
    "phase_a_raw_attempts.jsonl": (
        "650bcc01eea4cfd0f33feb7fbd3569f4d0c176b750ab8aec9f61f5c97c01c0dc"
    ),
    "phase_a_audited_attempts.jsonl": (
        "a9e153fc47bf71b7839c3c1880d33f7d6655eb7a2defccda9d8bea38ee607f3c"
    ),
}
WEIGHT_SUFFIXES = (".bin", ".safetensors")
_ACCEPTED_EVIDENCE_SNAPSHOT = None
_PHASE_B_EVIDENCE_SNAPSHOT = None


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_tree(root):
    records = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(dirpath) / name
            info = path.lstat()
            relative = str(path.relative_to(root))
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                records[relative] = ("not-regular", info.st_mode)
                continue
            records[relative] = ("file", info.st_size, _sha256_file(path))
    return records


def _ledger_record_count(path):
    with open(path, "rb") as handle:
        return sum(1 for line in handle if line.strip())


def assert_phase_b_evidence_identity(snapshot):
    if snapshot is None:
        raise AssertionError("accepted Phase B evidence directory is missing")
    for name, digest in EXPECTED_PHASE_B_SHA256.items():
        if name not in snapshot or snapshot[name][0] != "file":
            raise AssertionError("accepted Phase B evidence missing {}".format(name))
        if snapshot[name][2] != digest:
            raise AssertionError("accepted Phase B hash changed for {}".format(name))
    raw_files = [
        relative
        for relative, record in snapshot.items()
        if relative.startswith("rnagenesis_generation_output/") and record[0] == "file"
    ]
    if len(raw_files) != 89:
        raise AssertionError(
            "accepted Phase B raw generation file count is {}".format(len(raw_files))
        )
    if "phase_b_failure_manifest.json" in snapshot:
        raise AssertionError("accepted Phase B failure manifest is present")
    for name in ("phase_b_raw_attempts.jsonl", "phase_b_audited_attempts.jsonl"):
        count = _ledger_record_count(PHASE_B_EVIDENCE / name)
        if count != 1424:
            raise AssertionError("{} has {} records".format(name, count))


def snapshot_accepted_evidence():
    """Read-only snapshots of the accepted Phase A and Phase B evidence."""
    global _ACCEPTED_EVIDENCE_SNAPSHOT, _PHASE_B_EVIDENCE_SNAPSHOT
    if REAL_EVIDENCE.exists() or REAL_EVIDENCE.is_symlink():
        _ACCEPTED_EVIDENCE_SNAPSHOT = _snapshot_tree(REAL_EVIDENCE)
    else:
        _ACCEPTED_EVIDENCE_SNAPSHOT = None
    if PHASE_B_EVIDENCE.is_symlink() or not PHASE_B_EVIDENCE.is_dir():
        raise AssertionError(
            "accepted Phase B evidence directory is missing: {}".format(PHASE_B_EVIDENCE)
        )
    _PHASE_B_EVIDENCE_SNAPSHOT = _snapshot_tree(PHASE_B_EVIDENCE)
    assert_phase_b_evidence_identity(_PHASE_B_EVIDENCE_SNAPSHOT)


def assert_historical_evidence_absent(message):
    if HISTORICAL_EVIDENCE.exists() or HISTORICAL_EVIDENCE.is_symlink():
        raise AssertionError("{}: {}".format(message, HISTORICAL_EVIDENCE))


def assert_phase_b_evidence_unchanged(message):
    if PHASE_B_EVIDENCE.is_symlink() or not PHASE_B_EVIDENCE.is_dir():
        raise AssertionError(
            "{}: accepted Phase B evidence directory changed: {}".format(
                message, PHASE_B_EVIDENCE
            )
        )
    observed = _snapshot_tree(PHASE_B_EVIDENCE)
    if observed != _PHASE_B_EVIDENCE_SNAPSHOT:
        raise AssertionError(
            "{}: accepted Phase B evidence bytes, paths, or file count changed".format(
                message
            )
        )


def assert_evidence_unchanged(message):
    assert_historical_evidence_absent(message)
    assert_phase_b_evidence_unchanged(message)
    present = REAL_EVIDENCE.exists() or REAL_EVIDENCE.is_symlink()
    if _ACCEPTED_EVIDENCE_SNAPSHOT is None:
        if present:
            raise AssertionError(
                "{}: accepted evidence path was created: {}".format(
                    message, REAL_EVIDENCE
                )
            )
        return
    if not present or not REAL_EVIDENCE.is_dir():
        raise AssertionError(
            "{}: accepted evidence directory changed: {}".format(
                message, REAL_EVIDENCE
            )
        )
    observed = _snapshot_tree(REAL_EVIDENCE)
    if observed != _ACCEPTED_EVIDENCE_SNAPSHOT:
        raise AssertionError(
            "{}: accepted evidence hashes changed".format(message)
        )


def setUpModule():
    snapshot_accepted_evidence()
    assert_evidence_unchanged("accepted Phase A evidence changed before tests")
    loaded = [name for name in FORBIDDEN_RUNTIME_MODULES if name in sys.modules]
    if loaded:
        raise AssertionError(
            "test process imported {}".format(", ".join(loaded))
        )


def tearDownModule():
    assert_evidence_unchanged("accepted Phase A evidence changed during tests")
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
        "physical_gpu": runner.PHYSICAL_GPU,
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


def open_environ(**extra):
    environ = {
        "CUDA_VISIBLE_DEVICES": str(runner.PHYSICAL_GPU),
        "CUDA_DEVICE_ORDER": runner.CUDA_DEVICE_ORDER,
    }
    environ.update(extra)
    return environ


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
    def test_checked_in_configuration_is_consumed_complete_gpu1(self):
        config = real_config()
        text = real_config_bytes().decode("utf-8")
        block = config["scientific_execution_authorisation"]
        self.assertEqual(set(block), set(runner.SCIENTIFIC_AUTHORISATION_KEYS))
        self.assertEqual(list(block), list(runner.SCIENTIFIC_AUTHORISATION_KEYS))
        self.assertEqual(len(block), 18)
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(config)
        self.assertEqual(caught.exception.code, "phase_a_not_authorised")
        self.assertEqual(
            caught.exception.detail,
            "phase_a.executable_now is not true",
        )
        self.assertEqual(block["authorisation_id"], AUTHORISATION_ID)
        self.assertIs(block["authorisation_active"], False)
        self.assertEqual(block["activation_status"], "consumed_complete")
        self.assertNotEqual(block["activation_status"], "revoked_unconsumed")
        self.assertNotEqual(block["activation_status"], runner.ACTIVE_UNCONSUMED_STATUS)
        self.assertIs(block["consumed"], True)
        self.assertIs(block["authorises_b1_phase_a"], True)
        self.assertIs(block["gpu_use_authorised"], True)
        self.assertIs(type(block["physical_gpu"]), int)
        self.assertEqual(block["physical_gpu"], 1)
        self.assertEqual(block["physical_gpu"], runner.PHYSICAL_GPU)
        self.assertNotEqual(block["physical_gpu"], "1")
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
        self.assertIs(block["success_claimed"], True)
        self.assertIs(block["m4_complete"], False)
        self.assertIs(block["b1_eligible"], False)
        self.assertIs(block["phase_b_authorised"], False)
        self.assertIs(block["development_pool_authorised"], False)
        historical_records = config["historical_scientific_execution_authorisations"]
        self.assertEqual(len(historical_records), 1)
        historical = historical_records[0]
        self.assertEqual(set(historical), set(runner.SCIENTIFIC_AUTHORISATION_KEYS))
        self.assertEqual(list(historical), list(runner.SCIENTIFIC_AUTHORISATION_KEYS))
        self.assertEqual(len(historical), 18)
        self.assertEqual(historical["authorisation_id"], HISTORICAL_AUTHORISATION_ID)
        self.assertNotEqual(historical["authorisation_id"], block["authorisation_id"])
        self.assertIs(historical["authorisation_active"], False)
        self.assertEqual(historical["activation_status"], "revoked_unconsumed")
        self.assertNotEqual(historical["activation_status"], runner.ACTIVE_UNCONSUMED_STATUS)
        self.assertIs(historical["consumed"], False)
        self.assertIs(type(historical["physical_gpu"]), int)
        self.assertEqual(historical["physical_gpu"], 0)
        self.assertNotEqual(historical["physical_gpu"], block["physical_gpu"])
        self.assertEqual(
            historical["executing_implementation_commit"],
            HISTORICAL_IMPLEMENTATION_COMMIT,
        )
        self.assertNotEqual(
            historical["executing_implementation_commit"],
            block["executing_implementation_commit"],
        )
        self.assertEqual(historical["mres_branch"], "main")
        self.assertEqual(historical["condition"], runner.CONDITION_LABEL)
        self.assertEqual(historical["phase"], "A")
        self.assertEqual(historical["output_directory"], str(HISTORICAL_EVIDENCE))
        self.assertEqual(historical["evidence_directory"], str(HISTORICAL_EVIDENCE))
        self.assertEqual(
            historical["output_directory"],
            runner.evidence_directory_for_commit(HISTORICAL_IMPLEMENTATION_COMMIT),
        )
        self.assertEqual(
            historical["evidence_directory"],
            runner.evidence_directory_for_commit(HISTORICAL_IMPLEMENTATION_COMMIT),
        )
        self.assertNotEqual(historical["output_directory"], block["output_directory"])
        self.assertNotEqual(historical["evidence_directory"], block["evidence_directory"])
        self.assertIs(historical["success_claimed"], False)
        self.assertIs(historical["m4_complete"], False)
        self.assertIs(historical["b1_eligible"], False)
        self.assertIs(historical["phase_b_authorised"], False)
        self.assertIs(historical["development_pool_authorised"], False)
        self.assertNotEqual(historical, block)
        self.assertEqual(text.count("activation_status: revoked_unconsumed"), 1)
        self.assertEqual(text.count("activation_status: consumed_complete"), 2)
        self.assertEqual(text.count("activation_status: active_unconsumed"), 1)
        self.assertEqual(text.count("authorisation_active: true"), 1)
        phase_a_section = text.split("scientific_execution_authorisation:\n", 1)[1]
        phase_a_section = phase_a_section.split("\n\n", 1)[0]
        self.assertIn("activation_status: consumed_complete", phase_a_section)
        self.assertIn("authorisation_active: false", phase_a_section)
        self.assertNotIn("active_unconsumed", phase_a_section)
        historical_section = text.split(
            "historical_scientific_execution_authorisations:\n",
            1,
        )[1]
        historical_section = historical_section.split("\n\n", 1)[0]
        self.assertIn("activation_status: revoked_unconsumed", historical_section)
        self.assertNotIn("active_unconsumed", historical_section)
        phase_b_section = text.split(
            "phase_b_scientific_execution_authorisation:\n",
            1,
        )[1]
        phase_b_section = phase_b_section.split("\n\n", 1)[0]
        self.assertEqual(
            phase_b_section.count("activation_status: consumed_complete"),
            1,
        )
        self.assertIn("authorisation_active: false", phase_b_section)
        self.assertNotIn("active_unconsumed", phase_b_section)
        self.assertIn("\n  consumed: true\n", "\n" + phase_b_section + "\n")
        self.assertNotIn('consumed: "true"', phase_b_section)
        self.assertIn("\n  success_claimed: true\n", "\n" + phase_b_section + "\n")
        self.assertIn("\n  physical_gpu: 1\n", "\n" + phase_b_section + "\n")
        self.assertNotIn('physical_gpu: "1"', phase_b_section)
        self.assertEqual(
            [line.strip() for line in text.splitlines() if "rnagenesis-mres-runs" in line],
            [
                "output_directory: {}".format(REAL_EVIDENCE),
                "evidence_directory: {}".format(REAL_EVIDENCE),
                "output_directory: {}".format(HISTORICAL_EVIDENCE),
                "evidence_directory: {}".format(HISTORICAL_EVIDENCE),
                "output_directory: {}".format(PHASE_B_EVIDENCE),
                "evidence_directory: {}".format(PHASE_B_EVIDENCE),
                "evidence_directory: {}".format(REAL_EVIDENCE),
                "output_directory: {}".format(PHASE_B_EVIDENCE),
                "evidence_directory: {}".format(PHASE_B_EVIDENCE),
                "evidence_directory: {}".format(PHASE_B_EVIDENCE),
                "directory: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1",
                "path: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1/ordered_train_length_vector.json",
                "path: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1/development_pool_schedule.json",
                "path: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1/development_pool_schedule_sha256.json",
                "path: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1/schedule_materialization_driver.py",
                "path: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1/schedule_materialization_driver_sha256.json",
                "path: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1/schedule_materialization_manifest.json",
                "path: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1/schedule_materialization_manifest_sha256.json",
                "directory: /home/laura/rnagenesis-mres-runs/m4_validation_draw_artifacts_d2b2041520d1",
                "path: /home/laura/rnagenesis-mres-runs/m4_validation_draw_artifacts_d2b2041520d1/validation_draw_manifest.json",
                "path: /home/laura/rnagenesis-mres-runs/m4_validation_draw_artifacts_d2b2041520d1/validation_draw_manifest_sha256.json",
                "path: /home/laura/rnagenesis-mres-runs/m4_validation_draw_artifacts_d2b2041520d1/validation_timesteps.int64",
                "path: /home/laura/rnagenesis-mres-runs/m4_validation_draw_artifacts_d2b2041520d1/validation_noise.float32",
                "path: /home/laura/rnagenesis-mres-runs/m4_validation_draw_artifacts_d2b2041520d1/validation_order_artifact.csv",
                "schedule_path: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1/development_pool_schedule.json",
                "length_vector_path: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1/ordered_train_length_vector.json",
                "output_directory: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1",
                "evidence_directory: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1",
                "output_directory: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1",
                "evidence_directory: /home/laura/rnagenesis-mres-runs/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1",
            ],
        )
        self.assertNotEqual(REAL_EVIDENCE, HISTORICAL_EVIDENCE)
        self.assertNotEqual(REAL_EVIDENCE, PHASE_B_EVIDENCE)
        self.assertNotEqual(HISTORICAL_EVIDENCE, PHASE_B_EVIDENCE)
        self.assertTrue(str(REAL_EVIDENCE).endswith("_phaseA"))
        self.assertTrue(str(HISTORICAL_EVIDENCE).endswith("_phaseA"))
        self.assertTrue(str(PHASE_B_EVIDENCE).endswith("_phaseB"))
        self.assertFalse(HISTORICAL_EVIDENCE.exists() or HISTORICAL_EVIDENCE.is_symlink())
        self.assertTrue(PHASE_B_EVIDENCE.is_dir())
        self.assertFalse(PHASE_B_EVIDENCE.is_symlink())
        refused = opened_config()
        refused["scientific_execution_authorisation"] = copy.deepcopy(historical)
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(refused)
        self.assertEqual(caught.exception.code, "scientific_authorisation_inactive")
        reused = opened_config()
        reused["scientific_execution_authorisation"] = copy.deepcopy(block)
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(reused)
        self.assertEqual(caught.exception.code, "scientific_authorisation_inactive")
        phase_b_block = config["phase_b_scientific_execution_authorisation"]
        self.assertEqual(phase_b_block["authorisation_id"], PHASE_B_AUTHORISATION_ID)
        self.assertIs(phase_b_block["authorisation_active"], False)
        self.assertEqual(phase_b_block["activation_status"], "consumed_complete")
        self.assertNotEqual(
            phase_b_block["activation_status"],
            runner.ACTIVE_UNCONSUMED_STATUS,
        )
        self.assertIs(phase_b_block["consumed"], True)
        self.assertIs(type(phase_b_block["consumed"]), bool)
        self.assertNotEqual(phase_b_block["consumed"], "true")
        self.assertIs(phase_b_block["authorises_b1_phase_b"], True)
        self.assertNotIn("authorises_b1_phase_a", phase_b_block)
        self.assertIs(type(phase_b_block["physical_gpu"]), int)
        self.assertEqual(phase_b_block["physical_gpu"], 1)
        self.assertEqual(phase_b_block["physical_gpu"], runner.PHYSICAL_GPU)
        self.assertNotEqual(phase_b_block["physical_gpu"], "1")
        self.assertEqual(phase_b_block["phase"], "B")
        self.assertEqual(
            phase_b_block["executing_implementation_commit"],
            PHASE_B_IMPLEMENTATION_COMMIT,
        )
        self.assertEqual(phase_b_block["output_directory"], str(PHASE_B_EVIDENCE))
        self.assertEqual(phase_b_block["evidence_directory"], str(PHASE_B_EVIDENCE))
        self.assertNotEqual(phase_b_block["evidence_directory"], block["evidence_directory"])
        self.assertNotEqual(
            phase_b_block["evidence_directory"],
            historical["evidence_directory"],
        )
        self.assertIs(phase_b_block["success_claimed"], True)
        borrowed = opened_config()
        borrowed["scientific_execution_authorisation"] = copy.deepcopy(phase_b_block)
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(borrowed)
        self.assertEqual(caught.exception.code, "scientific_authorisation_incomplete")
        self.assertIn("authorises_b1_phase_a", caught.exception.detail)
        forced = copy.deepcopy(config)
        forced["consumable_by_executable_workflow"] = True
        forced["document_status"] = runner.EXECUTABLE_DOCUMENT_STATUS
        forced["execution"]["authorised"] = True
        forced["execution"]["gpu_authorised_by_this_approval"] = True
        forced["phase_a"]["executable_now"] = True
        forced["phase_a"]["status"] = runner.PHASE_A_EXECUTION_STATUS
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(forced)
        self.assertEqual(caught.exception.code, "scientific_authorisation_inactive")
        self.assertEqual(caught.exception.detail, "authorisation_active is not true")
        self.assertIs(config["consumable_by_executable_workflow"], True)
        self.assertEqual(config["document_status"], runner.EXECUTABLE_DOCUMENT_STATUS)
        self.assertNotIn(config["document_status"], runner.NON_EXECUTABLE_DOCUMENT_STATUSES)
        self.assertIs(config["phase_a"]["executable_now"], False)
        self.assertIs(type(config["phase_a"]["executable_now"]), bool)
        self.assertEqual(config["phase_a"]["status"], "COMPLETE_EVIDENCE_ACCEPTED")
        self.assertNotEqual(config["phase_a"]["status"], runner.PHASE_A_EXECUTION_STATUS)
        self.assertEqual(
            config["phase_a"]["blocked_until"],
            "complete_accepted_evidence_not_reexecutable",
        )
        self.assertIs(config["execution"]["authorised"], True)
        self.assertIs(config["execution"]["gpu_authorised_by_this_approval"], True)
        self.assertIs(config["phase_b"]["executable_now"], False)
        self.assertIs(type(config["phase_b"]["executable_now"]), bool)
        self.assertEqual(config["phase_b"]["status"], "COMPLETE_EVIDENCE_ACCEPTED")
        self.assertIs(config["phase_b"]["human_approved_candidate_mapping_required"], False)
        self.assertEqual(
            config["phase_b"]["blocked_until"],
            (
                "Phase B evidence is accepted and is not re-executable. "
                "The 1 October 2026 course change restored the Stage 1 "
                "diagnostic contract for the separate development-pool "
                "workflow and superseded Approach A before implementation."
            ),
        )
        self.assertIs(config["execution"]["gpu_authorised_by_this_draft"], False)
        shared = config["shared_generation_settings"]
        self.assertIsNone(shared["physical_gpu"])
        self.assertIs(shared["physical_gpu_selected_by_this_document"], False)
        self.assertIsNone(shared["cuda_visible_devices"])
        self.assertEqual(shared["child_logical_device"], "cuda:0")
        historical_device = config["historical_consumed_phase_a_and_phase_b_device"]
        self.assertIs(type(historical_device["physical_gpu"]), int)
        self.assertEqual(historical_device["physical_gpu"], 1)
        self.assertEqual(historical_device["physical_gpu"], runner.PHYSICAL_GPU)
        self.assertEqual(historical_device["cuda_visible_devices"], "1")
        self.assertIs(type(historical_device["cuda_visible_devices"]), str)
        self.assertEqual(historical_device["cuda_visible_devices"], str(runner.PHYSICAL_GPU))
        self.assertIs(historical_device["selects_a_device_for_the_development_pool"], False)
        self.assertEqual(shared["cuda_device_order"], "PCI_BUS_ID")
        self.assertEqual(shared["cuda_device_order"], runner.CUDA_DEVICE_ORDER)
        self.assertEqual(shared["visible_python_device"], "cuda:0")
        self.assertIs(shared["cpu_fallback"], False)
        self.assertIs(shared["other_gpu_fallback"], False)
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
        self._assert_phase_a_acceptance(config)
        self._assert_candidate_mapping(config)
        self._assert_checked_in_configuration_refuses_before_side_effects()
        if _ACCEPTED_EVIDENCE_SNAPSHOT is not None:
            self._assert_present_evidence_matches_acceptance(config)
        assert_evidence_unchanged("real Phase A evidence path was created")

    def _assert_phase_a_acceptance(self, config):
        acceptance = config["phase_a_evidence_acceptance"]
        self.assertEqual(acceptance["status"], "ACCEPTED")
        self.assertEqual(acceptance["accepted_by"], "Laura Hardy")
        self.assertEqual(acceptance["acceptance_date"], "30 September 2026")
        self.assertEqual(
            acceptance["acceptance_source"],
            "formal human acceptance in the M4 review chat",
        )
        self.assertEqual(acceptance["authorisation_id"], AUTHORISATION_ID)
        self.assertEqual(
            acceptance["executing_implementation_commit"],
            IMPLEMENTATION_COMMIT,
        )
        self.assertEqual(acceptance["authorization_commit"], AUTHORIZATION_COMMIT)
        self.assertEqual(acceptance["evidence_directory"], str(REAL_EVIDENCE))
        self.assertEqual(acceptance["manifest_schema"], "m4-b1-phase-a-manifest-1")
        self.assertEqual(acceptance["manifest_schema"], runner.MANIFEST_SCHEMA_VERSION)
        self.assertEqual(acceptance["run_status"], "complete")
        self.assertEqual(acceptance["started_at"], "2026-09-30T07:48:14Z")
        self.assertEqual(acceptance["finished_at"], "2026-09-30T08:10:18Z")
        self.assertIs(type(acceptance["physical_gpu"]), int)
        self.assertEqual(acceptance["physical_gpu"], 1)
        self.assertEqual(
            acceptance["gpu_uuid"],
            "GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f",
        )
        self.assertEqual(acceptance["pci_bus"], "00000000:61:00.0")
        self.assertEqual(acceptance["logical_device"], "cuda:0")
        self.assertEqual(acceptance["completed_invocations"], 33)
        self.assertEqual(acceptance["raw_attempts"], 528)
        self.assertEqual(acceptance["raw_outputs"], 33)
        self.assertEqual(acceptance["valid_outputs"], 528)
        self.assertEqual(acceptance["invalid_outputs"], 0)
        self.assertIs(acceptance["final_raw_output_verification_passed"], True)
        self.assertIs(acceptance["phase_a_failure_manifest_present"], False)
        hashes = acceptance["evidence_sha256"]
        self.assertEqual(
            hashes["phase_a_manifest_json"],
            EXPECTED_EVIDENCE_SHA256["phase_a_manifest.json"],
        )
        self.assertEqual(
            hashes["phase_a_manifest_sha256_json"],
            EXPECTED_EVIDENCE_SHA256["phase_a_manifest_sha256.json"],
        )
        self.assertEqual(
            hashes["phase_a_raw_attempts_jsonl"],
            EXPECTED_EVIDENCE_SHA256["phase_a_raw_attempts.jsonl"],
        )
        self.assertEqual(
            hashes["phase_a_audited_attempts_jsonl"],
            EXPECTED_EVIDENCE_SHA256["phase_a_audited_attempts.jsonl"],
        )
        self.assertEqual(
            acceptance["review_archive_sha256"],
            "2dccab9cbd4c4412a9088da4e5046418aff3eb54b22fae3ceb31efe4443b7a75",
        )
        boundary = acceptance["boundary_observations"]
        self.assertEqual(boundary["leading_boundary_11"]["marker"], "11")
        self.assertEqual(boundary["leading_boundary_11"]["observed"], 528)
        self.assertEqual(boundary["leading_boundary_11"]["total"], 528)
        self.assertEqual(boundary["empty_trailing_boundary"]["observed"], 492)
        self.assertEqual(boundary["empty_trailing_boundary"]["total"], 528)
        self.assertEqual(boundary["trailing_eos_marker_2"]["marker"], "2")
        self.assertEqual(boundary["trailing_eos_marker_2"]["observed"], 36)
        self.assertEqual(boundary["trailing_eos_marker_2"]["total"], 528)
        self.assertEqual(boundary["selected_cap_early_eos"]["observed"], 12)
        self.assertEqual(boundary["selected_cap_early_eos"]["total"], 176)
        self.assertIs(boundary["boundary_reconstruction_exact"], True)
        self.assertIs(boundary["silent_truncation_used"], False)
        self.assertIs(boundary["accepted_cleaned_sequences_contain_only_acgu"], True)

    def _assert_candidate_mapping(self, config):
        mapping = config["phase_b"]["approved_candidate_mapping"]
        recorded = config["length_algorithm"]["phase_b_candidate_mapping"]
        self.assertEqual(mapping["status"], CANDIDATE_STATUS)
        self.assertEqual(recorded["status"], CANDIDATE_STATUS)
        self.assertEqual(mapping["formula"], CANDIDATE_FORMULA)
        self.assertEqual(recorded["formula"], CANDIDATE_FORMULA)
        self.assertEqual(mapping["max_seq_len_offset"], 1)
        self.assertEqual(recorded["max_seq_len_offset"], 1)
        self.assertIs(mapping["final_production_mapping"], False)
        self.assertIs(recorded["final_production_mapping"], False)
        self.assertIs(
            config["length_algorithm"]["final_empirical_length_matching_algorithm_declared"],
            False,
        )
        self.assertIs(
            config["length_algorithm"]["final_rejection_or_resampling_algorithm_declared"],
            False,
        )
        self.assertEqual(mapping["non_eos_selected_cap_exact"], {"exact": 164, "total": 164})
        self.assertEqual(mapping["selected_cap_exact"], {"exact": 164, "total": 176})
        self.assertEqual(mapping["overall_exact_hit_rate"], "0.9318181818181818")
        self.assertEqual(mapping["overall_exact_hit_rate"], format(164 / 176, ".16f"))
        self.assertEqual(mapping["selected_cap_valid_outputs"], {"valid": 176, "total": 176})
        self.assertEqual(
            mapping["selected_cap_unique_cleaned_sequences"],
            {"unique": 176, "total": 176},
        )
        self.assertEqual(mapping["early_eos"], {"observed": 12, "total": 176})
        self.assertIs(mapping["increasing_the_cap_rescued_paired_early_eos_attempts"], False)
        cleaned = mapping["non_eos_cleaned_length"]
        self.assertEqual(
            cleaned["cap_target"]["cleaned_length"],
            "requested_biological_length_minus_1",
        )
        self.assertIs(cleaned["cap_target"]["every_non_eos_output"], True)
        self.assertEqual(
            cleaned["cap_target_plus_1"]["cleaned_length"],
            "requested_biological_length",
        )
        self.assertIs(cleaned["cap_target_plus_1"]["every_non_eos_output"], True)
        self.assertEqual(
            cleaned["cap_target_plus_2"]["cleaned_length"],
            "requested_biological_length_plus_1",
        )
        self.assertIs(cleaned["cap_target_plus_2"]["every_non_eos_output"], True)
        expected_rows = (
            (20, 21, 16, 0),
            (30, 31, 16, 0),
            (40, 41, 16, 0),
            (50, 51, 16, 0),
            (60, 61, 16, 0),
            (70, 71, 15, 1),
            (80, 81, 16, 0),
            (90, 91, 16, 0),
            (100, 101, 14, 2),
            (112, 113, 11, 5),
            (123, 124, 12, 4),
        )
        rows = mapping["per_target_selected_cap"]
        self.assertEqual(len(rows), 11)
        self.assertEqual(
            [
                (row["target"], row["cap"], row["exact"], row["early_eos"])
                for row in rows
            ],
            list(expected_rows),
        )
        self.assertTrue(all(row["attempts"] == 16 for row in rows))
        self.assertTrue(all(row["cap"] == row["target"] + 1 for row in rows))
        self.assertEqual(sum(row["exact"] for row in rows), 164)
        self.assertEqual(sum(row["early_eos"] for row in rows), 12)
        self.assertEqual(sum(row["attempts"] for row in rows), 176)
        interpretation = mapping["interpretation"]
        self.assertIs(interpretation["provisional_0_90_aggregate_diagnostic_exceeded"], True)
        self.assertIs(
            interpretation["every_tested_length_exceeds_provisional_0_50_per_length_diagnostic"],
            True,
        )
        self.assertIs(interpretation["b1_eligibility_claim"], False)
        self.assertIs(
            interpretation[
                "phase_b_must_test_candidate_mapping_across_all_frozen_train_lengths"
            ],
            True,
        )
        self.assertIs(
            interpretation[
                "early_termination_requires_explicit_rejection_or_resampling_consideration"
            ],
            True,
        )
        self.assertIs(interpretation["silent_trimming_or_truncation_authorized"], False)
        self.assertIs(interpretation["phase_b_authorised"], False)
        self.assertIs(interpretation["development_pool_authorised"], False)
        self.assertIs(interpretation["m4_complete"], False)
        self.assertIs(config["scientific_execution_authorisation"]["b1_eligible"], False)
        self.assertIs(config["scientific_execution_authorisation"]["phase_b_authorised"], False)
        self.assertIs(
            config["scientific_execution_authorisation"]["development_pool_authorised"],
            False,
        )
        self.assertIs(config["scientific_execution_authorisation"]["m4_complete"], False)
        pool = config["limited_development_pool"]
        self.assertEqual(
            pool["status"],
            "RESTORED_STAGE_1_DIAGNOSTIC_CONTRACT_AUTHORISED_FOR_ONE_UNCONSUMED_RUN",
        )
        self.assertIs(pool["phase_b_candidate_mapping_unblocks_this_pool"], False)
        self.assertIs(pool["development_pool_authorised"], True)
        self.assertIs(pool["sampling_authorised"], False)
        self.assertIs(pool["executable_now"], True)
        self.assertEqual(pool["raw_target_lengths"], 1000)
        self.assertIs(
            pool[
                "execution_blocked_until_length_mapping_or_rejection_resampling_algorithm_approved"
            ],
            False,
        )
        self.assertIn("4de4246aa4a97eadaf30caf449e3046378832366", pool["blocked_until"])
        self.assertIn("Phase A, Phase B, M5", pool["blocked_until"])
        decision = config["phase_b_human_scientific_decision"]
        self.assertEqual(decision["approving_person"], "Laura Hardy")
        self.assertEqual(decision["approval_date"], "1 October 2026")
        self.assertIs(decision["phase_b_evidence_accepted"], True)
        self.assertEqual(
            decision["selected_decision"],
            "DIAGNOSTIC_NO_REJECTION_REPLACEMENT_OR_RESAMPLING",
        )
        self.assertIs(decision["active_design_uses_rejection_replacement_or_resampling"], False)
        historical_decision = decision["historical_superseded_exact_length_rejection_resampling"]
        self.assertEqual(
            historical_decision["selected_decision"],
            "REQUIRE_DETERMINISTIC_EXACT_LENGTH_REJECTION_RESAMPLING",
        )
        self.assertIs(historical_decision["deterministic_rejection_or_resampling_direction_approved"], True)
        self.assertIs(historical_decision["executed"], False)
        self.assertIs(decision["approves_an_executable_algorithm"], False)
        self.assertIs(decision["exact_algorithm_finalized"], False)
        self.assertIs(decision["exact_algorithm_implemented"], False)
        self.assertIs(decision["limited_b1_development_pool_authorized"], False)
        self.assertIs(decision["b1_eligible"], False)
        self.assertIs(decision["m4_complete"], False)
        self.assertIs(
            config["length_algorithm"]["exact_algorithm_finalized"],
            False,
        )
        self.assertIs(
            config["length_algorithm"]["exact_algorithm_implemented"],
            False,
        )

    def _assert_checked_in_configuration_refuses_before_side_effects(self):
        for environ in (
            {},
            {"CUDA_VISIBLE_DEVICES": "", "CUDA_DEVICE_ORDER": ""},
            open_environ(),
        ):
            for output_dir in (
                str(REAL_EVIDENCE),
                str(REAL_EVIDENCE) + "/",
                str(HISTORICAL_EVIDENCE),
                str(PHASE_B_EVIDENCE),
                str(PHASE_B_EVIDENCE) + "/",
                "/tmp/b1-not-the-evidence-path",
            ):
                recorder = RecordingDeps(real_config_bytes(), environ)
                code, stderr = run_main(recorder.build(), output_dir)
                assert_closed(
                    self,
                    code,
                    stderr,
                    recorder,
                    "phase_a_not_authorised",
                )
                self.assertIn("phase_a.executable_now is not true", stderr)
                self.assertNotIn("nvidia-smi", stderr)
                self.assertNotIn("cuda_visible_devices", stderr)
                self.assertNotIn("cuda_device_order", stderr)
                for name in FORBIDDEN_RUNTIME_MODULES:
                    self.assertNotIn(name, sys.modules)

    def _assert_present_evidence_matches_acceptance(self, config):
        acceptance = config["phase_a_evidence_acceptance"]
        for name, digest in EXPECTED_EVIDENCE_SHA256.items():
            self.assertEqual(_ACCEPTED_EVIDENCE_SNAPSHOT[name][2], digest)
            self.assertEqual(
                _sha256_file(REAL_EVIDENCE / name),
                acceptance["evidence_sha256"][
                    {
                        "phase_a_manifest.json": "phase_a_manifest_json",
                        "phase_a_manifest_sha256.json": "phase_a_manifest_sha256_json",
                        "phase_a_raw_attempts.jsonl": "phase_a_raw_attempts_jsonl",
                        "phase_a_audited_attempts.jsonl": "phase_a_audited_attempts_jsonl",
                    }[name]
                ],
            )
        self.assertNotIn("phase_a_failure_manifest.json", _ACCEPTED_EVIDENCE_SNAPSHOT)
        raw_files = [
            relative
            for relative in _ACCEPTED_EVIDENCE_SNAPSHOT
            if relative.startswith("rnagenesis_generation_output/")
            and _ACCEPTED_EVIDENCE_SNAPSHOT[relative][0] == "file"
        ]
        self.assertEqual(len(raw_files), 33)
        for name in ("phase_a_raw_attempts.jsonl", "phase_a_audited_attempts.jsonl"):
            with open(REAL_EVIDENCE / name, "rb") as handle:
                row_count = sum(1 for line in handle if line.strip())
            self.assertEqual(row_count, 528)

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
        assert_evidence_unchanged("accepted Phase A evidence changed")

    def test_missing_cuda_does_not_outrank_the_closed_document(self):
        recorder = RecordingDeps(dumped(synthetic_closed_copy()), {})
        code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
        assert_closed(self, code, stderr, recorder, "configuration_not_consumable")
        assert_evidence_unchanged("accepted Phase A evidence changed")

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
                ("scientific_execution_authorisation", "activation_status"),
                "revoked_unconsumed",
                "scientific_authorisation_inactive",
            ),
            (
                ("scientific_execution_authorisation", "physical_gpu"),
                "1",
                "gpu_not_authorised",
            ),
            (
                ("scientific_execution_authorisation", "physical_gpu"),
                "0",
                "gpu_not_authorised",
            ),
            (("scientific_execution_authorisation", "physical_gpu"), 0, "gpu_not_authorised"),
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
            config = opened_config()
            assign_path(config, path, value)
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.assert_document_gates(config)
            self.assertEqual(caught.exception.code, code, path)
        missing_gpu = opened_config()
        del missing_gpu["scientific_execution_authorisation"]["physical_gpu"]
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(missing_gpu)
        self.assertEqual(caught.exception.code, "scientific_authorisation_incomplete")
        self.assertIn("physical_gpu", caught.exception.detail)
        assert_evidence_unchanged("real Phase A evidence path was created")


class AuthorisationTests(unittest.TestCase):
    def test_opened_authorisation_passes_document_gates(self):
        snapshot = runner.assert_document_gates(opened_config())
        self.assertIs(type(snapshot["physical_gpu"]), int)
        self.assertEqual(snapshot["physical_gpu"], 1)
        self.assertEqual(snapshot["physical_gpu"], runner.PHYSICAL_GPU)
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

    def test_gpu_must_be_integer_one(self):
        self.assertIs(type(runner.PHYSICAL_GPU), int)
        self.assertEqual(runner.PHYSICAL_GPU, 1)
        for value in ("1", "0", True, 0, 2, -1, 0.0, None, False):
            config = opened_config()
            config["scientific_execution_authorisation"]["physical_gpu"] = value
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.assert_document_gates(config)
            self.assertEqual(caught.exception.code, "gpu_not_authorised")
            self.assertIn("physical GPU 1", caught.exception.detail)
        accepted = runner.assert_document_gates(opened_config())
        self.assertEqual(accepted["physical_gpu"], runner.PHYSICAL_GPU)
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
        self.assertEqual(
            runner.evidence_directory_for_commit(HISTORICAL_IMPLEMENTATION_COMMIT),
            str(HISTORICAL_EVIDENCE),
        )
        self.assertNotEqual(str(REAL_EVIDENCE), str(HISTORICAL_EVIDENCE))
        config = opened_config(commit)
        config["scientific_execution_authorisation"]["authorisation_id"] = AUTHORISATION_ID
        self.assertEqual(
            config["scientific_execution_authorisation"]["physical_gpu"],
            1,
        )
        self.assertIs(
            type(config["scientific_execution_authorisation"]["physical_gpu"]),
            int,
        )
        config["scientific_execution_authorisation"]["output_directory"] = "/tmp/other"
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(config)
        self.assertEqual(caught.exception.code, "authorisation_evidence_mismatch")
        historical_path = opened_config(commit)
        historical_path["scientific_execution_authorisation"]["output_directory"] = str(
            HISTORICAL_EVIDENCE
        )
        historical_path["scientific_execution_authorisation"]["evidence_directory"] = str(
            HISTORICAL_EVIDENCE
        )
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(historical_path)
        self.assertEqual(caught.exception.code, "authorisation_evidence_mismatch")
        wrong_commit = opened_config(HISTORICAL_IMPLEMENTATION_COMMIT)
        self.assertEqual(
            wrong_commit["scientific_execution_authorisation"]["executing_implementation_commit"],
            HISTORICAL_IMPLEMENTATION_COMMIT,
        )
        self.assertNotEqual(
            wrong_commit["scientific_execution_authorisation"]["evidence_directory"],
            str(REAL_EVIDENCE),
        )
        wrong_commit["scientific_execution_authorisation"]["output_directory"] = str(
            REAL_EVIDENCE
        )
        wrong_commit["scientific_execution_authorisation"]["evidence_directory"] = str(
            REAL_EVIDENCE
        )
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_document_gates(wrong_commit)
        self.assertEqual(caught.exception.code, "authorisation_evidence_mismatch")
        assert_evidence_unchanged("real Phase A evidence path was created")


class CudaAndOutputTests(unittest.TestCase):
    def test_missing_cuda_visible_devices_refuses(self):
        for environ in ({}, {"CUDA_DEVICE_ORDER": runner.CUDA_DEVICE_ORDER}):
            recorder = RecordingDeps(dumped(opened_config()), environ)
            code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
            assert_closed(self, code, stderr, recorder, "cuda_visible_devices_missing")
            self.assertNotIn("nvidia-smi", stderr)

    def test_cuda_values_other_than_exact_one_refuse(self):
        for value in ("0", "01", "", "1 ", "11", "0,1", "1\n", "1,0", 0, 1, 2, None):
            recorder = RecordingDeps(
                dumped(opened_config()),
                {
                    "CUDA_VISIBLE_DEVICES": value,
                    "CUDA_DEVICE_ORDER": runner.CUDA_DEVICE_ORDER,
                },
            )
            code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
            assert_closed(self, code, stderr, recorder, "cuda_visible_devices_refused")
            self.assertNotIn("nvidia-smi", stderr)

    def test_device_order_other_than_pci_bus_id_refuses(self):
        for value in ("", "FASTEST_FIRST", "PCI_BUS_ID ", "fastest_first", "0", None):
            recorder = RecordingDeps(
                dumped(opened_config()),
                {
                    "CUDA_VISIBLE_DEVICES": str(runner.PHYSICAL_GPU),
                    "CUDA_DEVICE_ORDER": value,
                },
            )
            code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
            assert_closed(self, code, stderr, recorder, "cuda_device_order_refused")
            self.assertNotIn("nvidia-smi", stderr)
        recorder = RecordingDeps(
            dumped(opened_config()),
            {"CUDA_VISIBLE_DEVICES": str(runner.PHYSICAL_GPU)},
        )
        code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
        assert_closed(self, code, stderr, recorder, "cuda_device_order_missing")
        self.assertNotIn("nvidia-smi", stderr)

    def test_exact_gpu1_environment_reaches_the_output_gate(self):
        recorder = RecordingDeps(dumped(opened_config()), open_environ())
        code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
        assert_closed(self, code, stderr, recorder, "output_path_mismatch")
        self.assertNotIn("nvidia-smi", stderr)

    def test_checked_in_configuration_refuses_before_cuda_preflight(self):
        environments = (
            {"CUDA_VISIBLE_DEVICES": "", "CUDA_DEVICE_ORDER": ""},
            {},
            open_environ(),
            {"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID"},
            {"CUDA_VISIBLE_DEVICES": "1", "CUDA_DEVICE_ORDER": "FASTEST_FIRST"},
            {"CUDA_VISIBLE_DEVICES": "1"},
        )
        for environ in environments:
            recorder = RecordingDeps(real_config_bytes(), environ)
            code, stderr = run_main(recorder.build(), "/tmp/b1-not-the-evidence-path")
            assert_closed(self, code, stderr, recorder, "phase_a_not_authorised")
            self.assertIn("phase_a.executable_now is not true", stderr)
            self.assertNotIn("nvidia-smi", stderr)
            self.assertNotIn("cuda_visible_devices", stderr)
            self.assertNotIn("cuda_device_order", stderr)
            for name in FORBIDDEN_RUNTIME_MODULES:
                self.assertNotIn(name, sys.modules)
        assert_evidence_unchanged("real Phase A evidence path was created")
        self.assertTrue(PHASE_B_EVIDENCE.is_dir())
        self.assertFalse(PHASE_B_EVIDENCE.is_symlink())

    def test_real_evidence_aliases_refuse_before_lstat(self):
        expected = str(REAL_EVIDENCE)
        phase_b = str(PHASE_B_EVIDENCE)
        supplied = [
            expected,
            "phaseA",
            expected + "/",
            "/home/laura/rnagenesis-mres-runs/../rnagenesis-mres-runs/"
            + REAL_EVIDENCE.name,
            "/tmp/b1-not-the-evidence-path",
            str(HISTORICAL_EVIDENCE),
            phase_b,
            "phaseB",
            phase_b + "/",
            "/home/laura/rnagenesis-mres-runs/../rnagenesis-mres-runs/"
            + PHASE_B_EVIDENCE.name,
        ]
        for output_dir in supplied:
            recorder = RecordingDeps(real_config_bytes(), open_environ())
            code, stderr = run_main(recorder.build(), output_dir)
            assert_closed(self, code, stderr, recorder, "phase_a_not_authorised")
            self.assertIn("phase_a.executable_now is not true", stderr)
            self.assertNotIn("nvidia-smi", stderr)
            for name in FORBIDDEN_RUNTIME_MODULES:
                self.assertNotIn(name, sys.modules)
        assert_evidence_unchanged("real Phase A evidence path was created")
        self.assertFalse(HISTORICAL_EVIDENCE.exists() or HISTORICAL_EVIDENCE.is_symlink())
        self.assertTrue(PHASE_B_EVIDENCE.is_dir())
        self.assertFalse(PHASE_B_EVIDENCE.is_symlink())

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
            recorder = RecordingDeps(dumped(opened_config()), open_environ())
            code, stderr = run_main(recorder.build(), output_dir)
            assert_closed(self, code, stderr, recorder, "output_path_mismatch")

    def test_existing_empty_directory_refuses(self):
        expected = runner.evidence_directory_for_commit(COMMIT)
        recorder = RecordingDeps(dumped(opened_config()), open_environ())

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
        assert_evidence_unchanged("accepted Phase A evidence changed")
        self.assertFalse(Path(expected).exists())

    def test_symlink_and_resolved_alias_refuse(self):
        expected = runner.evidence_directory_for_commit(COMMIT)
        recorder = RecordingDeps(dumped(opened_config()), open_environ())

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

    def test_non_dict_mappings_accept_exact_gpu1_and_refuse_other_values(self):
        evidence = runner.evidence_directory_for_commit(COMMIT)
        self.assertFalse(Path(evidence).exists())
        assert_evidence_unchanged("accepted Phase A evidence changed")
        self.assertEqual(runner.PHYSICAL_GPU, 1)
        self.assertEqual(runner.CUDA_DEVICE_ORDER, "PCI_BUS_ID")
        source = inspect.getsource(runner.assert_cuda_environment)
        self.assertIn("collections.abc.Mapping", source)
        self.assertNotIn("isinstance(environ, dict)", source)
        self.assertNotIn("type(environ)", source)
        cuda_before = (
            os.environ.get("CUDA_VISIBLE_DEVICES"),
            os.environ.get("CUDA_DEVICE_ORDER"),
        )

        def forbidden(*_args, **_kwargs):
            raise AssertionError("GPU query or subprocess was called")

        def assert_parent_unchanged(mapping, before_items):
            after_items = list(mapping.items())
            if after_items == before_items:
                return
            before = dict(before_items)
            after = dict(after_items)
            changed = sorted(
                key
                for key in set(before) | set(after)
                if before.get(key) != after.get(key)
            )
            self.fail("parent mapping changed: {}".format(", ".join(changed)))

        def accept(parent):
            self.assertNotIsInstance(parent, dict)
            self.assertIsInstance(parent, collections.abc.Mapping)
            before_items = list(parent.items())
            runner.assert_cuda_environment(parent)
            assert_parent_unchanged(parent, before_items)
            child = runner.build_child_environment(parent, evidence)
            assert_parent_unchanged(parent, before_items)
            self.assertIsInstance(child, dict)
            self.assertIsNot(child, parent)
            self.assertEqual(child["CUDA_VISIBLE_DEVICES"], "1")
            self.assertEqual(child["CUDA_VISIBLE_DEVICES"], str(runner.PHYSICAL_GPU))
            self.assertEqual(child["CUDA_DEVICE_ORDER"], "PCI_BUS_ID")
            self.assertEqual(child["CUDA_DEVICE_ORDER"], runner.CUDA_DEVICE_ORDER)
            self.assertIs(type(child["CUDA_VISIBLE_DEVICES"]), str)
            self.assertIs(type(child["CUDA_DEVICE_ORDER"]), str)
            self.assertEqual(child["HF_HUB_OFFLINE"], "1")
            self.assertEqual(child["PYTHONDONTWRITEBYTECODE"], "1")
            child["CUDA_VISIBLE_DEVICES"] = "0"
            child["B1_SYNTHETIC_CHILD_MARKER"] = "child-only"
            self.assertEqual(parent["CUDA_VISIBLE_DEVICES"], "1")
            self.assertNotIn("B1_SYNTHETIC_CHILD_MARKER", parent)
            assert_parent_unchanged(parent, before_items)
            self.assertFalse(Path(evidence).exists())
            assert_evidence_unchanged("accepted Phase A evidence changed")
            for name in FORBIDDEN_RUNTIME_MODULES:
                self.assertNotIn(name, sys.modules)

        def refuse(parent, code):
            before_items = list(parent.items())
            for operation in (
                lambda: runner.assert_cuda_environment(parent),
                lambda: runner.build_child_environment(parent, evidence),
            ):
                with self.assertRaises(runner.B1RunnerError) as caught:
                    operation()
                self.assertEqual(caught.exception.code, code)
            assert_parent_unchanged(parent, before_items)
            self.assertFalse(Path(evidence).exists())
            assert_evidence_unchanged("accepted Phase A evidence changed")

        def refuse_os(values, removed, code):
            with mock.patch.dict(os.environ, values, clear=False):
                for key in removed:
                    os.environ.pop(key, None)
                self.assertIs(runner.production_dependencies().environ, os.environ)
                refuse(os.environ, code)

        user = collections.UserDict(
            {
                "CUDA_VISIBLE_DEVICES": "1",
                "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
                "B1_SYNTHETIC_PARENT_MARKER": "keep",
                "HF_HUB_OFFLINE": "0",
            }
        )
        patches = (
            mock.patch.object(runner.subprocess, "run", forbidden),
            mock.patch.object(runner.subprocess, "Popen", forbidden),
            mock.patch.object(runner.subprocess, "call", forbidden),
            mock.patch.object(runner.subprocess, "check_call", forbidden),
            mock.patch.object(runner.subprocess, "check_output", forbidden),
            mock.patch.object(runner, "default_subprocess_run", forbidden),
            mock.patch.object(runner, "default_query_gpu_text", forbidden),
            mock.patch.object(runner, "default_cuda_probe", forbidden),
            mock.patch.object(runner, "default_gpu_preflight", forbidden),
            mock.patch.object(runner, "production_gpu_preflight", forbidden),
            mock.patch("os.system", forbidden),
        )
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            accept(user)
            self.assertEqual(user["B1_SYNTHETIC_PARENT_MARKER"], "keep")
            self.assertEqual(user["HF_HUB_OFFLINE"], "0")
            self.assertNotIn("PYTHONDONTWRITEBYTECODE", user)
            for value in ("0", "01", "", "1 ", "11", "0,1", "1\n", "1,0", 0, 1, 2, None):
                refuse(
                    collections.UserDict(
                        {
                            "CUDA_VISIBLE_DEVICES": value,
                            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
                        }
                    ),
                    "cuda_visible_devices_refused",
                )
            for value in ("", "FASTEST_FIRST", "PCI_BUS_ID ", "fastest_first", "0", None):
                refuse(
                    collections.UserDict(
                        {
                            "CUDA_VISIBLE_DEVICES": "1",
                            "CUDA_DEVICE_ORDER": value,
                        }
                    ),
                    "cuda_device_order_refused",
                )
            refuse(collections.UserDict(), "cuda_visible_devices_missing")
            refuse(
                collections.UserDict({"CUDA_DEVICE_ORDER": "PCI_BUS_ID"}),
                "cuda_visible_devices_missing",
            )
            refuse(
                collections.UserDict({"CUDA_VISIBLE_DEVICES": "1"}),
                "cuda_device_order_missing",
            )
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.assert_cuda_environment(None)
            self.assertEqual(caught.exception.code, "cuda_visible_devices_missing")
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.build_child_environment(None, evidence)
            self.assertEqual(caught.exception.code, "cuda_visible_devices_missing")

            with mock.patch.dict(
                os.environ,
                {
                    "CUDA_VISIBLE_DEVICES": "1",
                    "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
                    "B1_SYNTHETIC_PARENT_MARKER": "keep",
                },
            ):
                environ = runner.production_dependencies().environ
                self.assertIs(environ, os.environ)
                accept(environ)
                self.assertEqual(environ["B1_SYNTHETIC_PARENT_MARKER"], "keep")
                self.assertEqual(environ["CUDA_DEVICE_ORDER"], "PCI_BUS_ID")

            for value in ("0", "01", "", "1 ", "11", "0,1", "1\n", "1,0"):
                refuse_os(
                    {
                        "CUDA_VISIBLE_DEVICES": value,
                        "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
                    },
                    (),
                    "cuda_visible_devices_refused",
                )
            for value in ("", "FASTEST_FIRST", "PCI_BUS_ID ", "fastest_first", "0"):
                refuse_os(
                    {
                        "CUDA_VISIBLE_DEVICES": "1",
                        "CUDA_DEVICE_ORDER": value,
                    },
                    (),
                    "cuda_device_order_refused",
                )
            refuse_os(
                {"CUDA_DEVICE_ORDER": "PCI_BUS_ID"},
                ("CUDA_VISIBLE_DEVICES",),
                "cuda_visible_devices_missing",
            )
            refuse_os(
                {},
                ("CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER"),
                "cuda_visible_devices_missing",
            )
            refuse_os(
                {"CUDA_VISIBLE_DEVICES": "1"},
                ("CUDA_DEVICE_ORDER",),
                "cuda_device_order_missing",
            )

        self.assertNotIn("B1_SYNTHETIC_PARENT_MARKER", os.environ)
        self.assertEqual(
            (
                os.environ.get("CUDA_VISIBLE_DEVICES"),
                os.environ.get("CUDA_DEVICE_ORDER"),
            ),
            cuda_before,
        )
        self.assertFalse(Path(evidence).exists())
        assert_evidence_unchanged("accepted Phase A evidence changed")
        for name in FORBIDDEN_RUNTIME_MODULES:
            self.assertNotIn(name, sys.modules)


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

    def test_plan_settings_name_only_physical_gpu_one(self):
        refusals = (
            ("physical_gpu", 0),
            ("physical_gpu", "1"),
            ("physical_gpu", 1),
            ("physical_gpu", 2),
            ("cuda_visible_devices", "0"),
            ("cuda_visible_devices", "1"),
            ("cuda_visible_devices", "01"),
            ("cuda_visible_devices", ""),
            ("cuda_device_order", "FASTEST_FIRST"),
            ("cuda_device_order", ""),
        )
        for key, value in refusals:
            config = opened_config()
            config["shared_generation_settings"][key] = value
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.build_phase_a_plan(config)
            self.assertEqual(caught.exception.code, "phase_a_plan_invalid", key)
        missing = opened_config()
        del missing["shared_generation_settings"]["cuda_device_order"]
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.build_phase_a_plan(missing)
        self.assertEqual(caught.exception.code, "phase_a_plan_invalid")
        self.assertEqual(len(runner.build_phase_a_plan(real_config())), 33)

    def test_argv_encoding_and_prohibited_flags(self):
        plan = runner.build_phase_a_plan(real_config())
        evidence = runner.evidence_directory_for_commit(COMMIT)
        parent = open_environ(HF_HUB_OFFLINE="0")
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
            self.assertEqual(command["env"]["CUDA_VISIBLE_DEVICES"], "1")
            self.assertEqual(command["env"]["CUDA_VISIBLE_DEVICES"], str(runner.PHYSICAL_GPU))
            self.assertEqual(command["env"]["CUDA_DEVICE_ORDER"], runner.CUDA_DEVICE_ORDER)
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
        parent = open_environ(HF_HUB_OFFLINE="0", MARKER="keep")
        calls = []

        def sha256_file(path):
            text = str(path)
            if text.endswith(WEIGHT_SUFFIXES) or "pytorch_model" in text:
                raise AssertionError(text)
            return runner.default_sha256_file(path)

        def subprocess_run(argv, cwd, env, shell=False):
            self.assertFalse(shell)
            self.assertEqual(cwd, "/home/laura/RNAGenesis")
            self.assertEqual(env["CUDA_VISIBLE_DEVICES"], str(runner.PHYSICAL_GPU))
            self.assertEqual(env["CUDA_DEVICE_ORDER"], runner.CUDA_DEVICE_ORDER)
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
                    "index": runner.PHYSICAL_GPU,
                    "physical_gpu": runner.PHYSICAL_GPU,
                    "uuid": "GPU-synthetic",
                    "pci_bus_id": "0000:01:00.0",
                    "name": "Synthetic GPU",
                    "memory": "1",
                    "compute_mode": "Default",
                    "logical_device": "cuda:0",
                    "logical_device_index": 0,
                    "cuda_visible_devices": str(runner.PHYSICAL_GPU),
                    "cuda_device_order": runner.CUDA_DEVICE_ORDER,
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
        assert_evidence_unchanged("accepted Phase A evidence changed")


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
            runner.default_gpu_preflight(open_environ())
        self.assertEqual(caught.exception.code, "gpu_preflight_before_authorisation")

        def query():
            raise AssertionError("gpu queried")

        def probe():
            raise AssertionError("probe ran")

        refusals = (
            ({}, "cuda_visible_devices_missing"),
            (
                {"CUDA_DEVICE_ORDER": runner.CUDA_DEVICE_ORDER},
                "cuda_visible_devices_missing",
            ),
            (
                {"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": runner.CUDA_DEVICE_ORDER},
                "cuda_visible_devices_refused",
            ),
            (
                {"CUDA_VISIBLE_DEVICES": "1", "CUDA_DEVICE_ORDER": "FASTEST_FIRST"},
                "cuda_device_order_refused",
            ),
            (
                {"CUDA_VISIBLE_DEVICES": str(runner.PHYSICAL_GPU)},
                "cuda_device_order_missing",
            ),
        )
        for environ, code in refusals:
            with self.assertRaises(runner.B1RunnerError) as caught:
                runner.preflight_gpu(environ, query, probe)
            self.assertEqual(caught.exception.code, code)
        identity = runner.parse_gpu_identity(nvidia_smi_text())
        self.assertIs(type(identity["index"]), int)
        self.assertEqual(identity["index"], 1)
        self.assertEqual(identity["index"], runner.PHYSICAL_GPU)
        self.assertEqual(identity["physical_gpu"], runner.PHYSICAL_GPU)
        self.assertEqual(identity["uuid"], "GPU-synthetic")
        self.assertEqual(identity["pci_bus_id"], "0000:01:00.0")
        self.assertEqual(identity["name"], "Synthetic GPU")
        self.assertEqual(identity["memory"], "81920")
        self.assertEqual(identity["compute_mode"], "Default")
        self.assertNotIn("logical_device_confirmed", identity)
        self.assertIs(identity["cpu_fallback"], False)

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
    rna_status = overrides["rna_status"] if "rna_status" in overrides else runner.reviewed_rnagenesis_porcelain()
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
        "cuda_visible_devices": str(runner.PHYSICAL_GPU),
        "cuda_device_order": runner.CUDA_DEVICE_ORDER,
    }
    payload.update(overrides)
    return payload


def nvidia_smi_text(name="Synthetic GPU", index=None, pci="0000:01:00.0", uuid="GPU-synthetic"):
    if index is None:
        index = runner.PHYSICAL_GPU
    return "{}, {}, {}, {}, 81920, Default\n".format(index, uuid, pci, name)


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
            ({"rna_status": ""}, "rnagenesis_untracked_refused", "known RNAGenesis"),
            (
                {"rna_status": "?? configs/\n?? checkpoints/\n"},
                "rnagenesis_untracked_refused",
                "known RNAGenesis",
            ),
            (
                {
                    "rna_status": runner.reviewed_rnagenesis_porcelain().replace(
                        "?? configs/\n",
                        "?? config_renamed/\n",
                        1,
                    )
                },
                "rnagenesis_untracked_refused",
                "known RNAGenesis",
            ),
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
            repository_git(runtime, implementation),
        )
        self.assertEqual(passing["mres"]["origin_main"], runtime)
        self.assertEqual(passing["rnagenesis"]["branch"], runner.RNAGENESIS_BRANCH)
        self.assertEqual(passing["rnagenesis"]["head"], runner.RNAGENESIS_HEAD)

    def test_rnagenesis_provenance_requires_the_live_untracked_fingerprint(self):
        snapshot = runner.assert_document_gates(opened_config(COMMIT))
        live = runner.reviewed_rnagenesis_porcelain()
        self.assertTrue(all(line.startswith("?? ") and line.endswith("/") for line in live.splitlines()))
        self.assertEqual(
            [line[3:] for line in live.splitlines()],
            list(runner.KNOWN_RNAGENESIS_UNTRACKED),
        )
        provenance = runner.assert_repository_pins(
            snapshot,
            repository_git("b" * 40, COMMIT, rna_status=live),
        )
        self.assertEqual(provenance["rnagenesis"]["branch"], runner.RNAGENESIS_BRANCH)
        self.assertEqual(provenance["rnagenesis"]["head"], runner.RNAGENESIS_HEAD)
        reversed_live = "".join("?? {}\n".format(path) for path in reversed(runner.KNOWN_RNAGENESIS_UNTRACKED))
        reversed_provenance = runner.assert_repository_pins(
            snapshot,
            repository_git("b" * 40, COMMIT, rna_status=reversed_live),
        )
        self.assertEqual(reversed_provenance["rnagenesis"]["head"], runner.RNAGENESIS_HEAD)
        unexpected = live + "?? notes.txt\n"
        with self.assertRaises(runner.B1RunnerError) as caught:
            runner.assert_repository_pins(
                snapshot,
                repository_git("b" * 40, COMMIT, rna_status=unexpected),
            )
        self.assertEqual(caught.exception.code, "rnagenesis_untracked_refused")
        self.assertIn("known RNAGenesis", caught.exception.detail)


class CudaProbeTests(unittest.TestCase):
    def setUp(self):
        self.evidence = runner.evidence_directory_for_commit(COMMIT)
        self.env = runner.build_child_environment(
            open_environ(),
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
        self.assertEqual(identity["logical_device_index"], 0)
        self.assertEqual(identity["device_count"], 1)
        self.assertEqual(identity["device_name"], "Synthetic GPU")
        self.assertIs(type(identity["index"]), int)
        self.assertEqual(identity["index"], 1)
        self.assertEqual(identity["physical_gpu"], runner.PHYSICAL_GPU)
        self.assertEqual(identity["uuid"], "GPU-synthetic")
        self.assertEqual(identity["pci_bus_id"], "0000:01:00.0")
        self.assertEqual(identity["memory"], "81920")
        self.assertEqual(identity["compute_mode"], "Default")
        self.assertEqual(identity["cuda_visible_devices"], "1")
        self.assertEqual(identity["cuda_device_order"], "PCI_BUS_ID")
        self.assertIs(identity["cpu_fallback"], False)
        self.assertEqual(identity["packages"]["torch"], "2.4.0")
        self.assertEqual(
            set(identity["packages"]),
            set(runner.GENERATION_CRITICAL_DISTRIBUTIONS),
        )
        self.assertEqual(identity["python_executable"], runner.PINNED_PYTHON)
        generation_command = runner.build_subprocess_invocation(
            runner.build_phase_a_plan(real_config())[0],
            self.evidence,
            open_environ(),
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
        query_argv = runner.physical_gpu_query_argv()
        self.assertEqual(query_argv[-2:], ["-i", "1"])
        self.assertEqual(query_argv[-2:], ["-i", str(runner.PHYSICAL_GPU)])
        self.assertIn("pci.bus_id", query_argv[1])
        source = inspect.getsource(runner.default_gpu_preflight)
        self.assertIn("default_query_gpu_text", source)
        self.assertIn("default_cuda_probe", source)
        self.assertIsNotNone(compile(runner.CUDA_PROBE_SOURCE, "<cuda-probe>", "exec"))
        self.assertIn('device="cuda:0"', runner.CUDA_PROBE_SOURCE)
        self.assertIn("torch.cuda.synchronize(0)", runner.CUDA_PROBE_SOURCE)
        self.assertIn("CUDA_DEVICE_ORDER", runner.CUDA_PROBE_SOURCE)
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
            (probe_payload(cuda_visible_devices="0"), "cuda_probe_mismatch"),
            (probe_payload(cuda_visible_devices="01"), "cuda_probe_mismatch"),
            (probe_payload(cuda_visible_devices=""), "cuda_probe_mismatch"),
            (probe_payload(cuda_device_order="FASTEST_FIRST"), "cuda_probe_mismatch"),
            (probe_payload(cuda_device_order=""), "cuda_probe_mismatch"),
            (probe_payload(cuda_device_order=None), "cuda_probe_mismatch"),
            (probe_payload(logical_device="cuda:1", logical_device_index=1), "cuda_allocation_failed"),
            (probe_payload(logical_device="cpu"), "cuda_probe_mismatch"),
            (probe_payload(logical_device_index=1), "cuda_allocation_failed"),
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
        malformed = (
            nvidia_smi_text(index=0),
            nvidia_smi_text(index=2),
            nvidia_smi_text(index="01"),
            nvidia_smi_text(uuid=""),
            nvidia_smi_text(uuid="N/A"),
            nvidia_smi_text(pci=""),
            nvidia_smi_text(pci="N/A"),
            "1, GPU-synthetic, 0000:01:00.0, Synthetic GPU, 81920\n",
            "1, GPU-synthetic, 0000:01:00.0, , 81920, Default\n",
            "",
            "1, GPU-synthetic, 0000:01:00.0, Synthetic GPU, 81920, Default\n"
            "1, GPU-other, 0000:02:00.0, Other GPU, 1, Default\n",
        )
        for text in malformed:
            with self.assertRaises(runner.B1RunnerError) as caught:
                self.preflight(text, probe_payload())
            self.assertEqual(caught.exception.code, "cpu_fallback_prohibited")


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
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], str(runner.PHYSICAL_GPU))
        self.assertEqual(env["CUDA_DEVICE_ORDER"], runner.CUDA_DEVICE_ORDER)
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
            environ=open_environ(HF_HUB_OFFLINE="0"),
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
        assert_evidence_unchanged("accepted Phase A evidence changed")
        config_bytes = dumped(opened_config(implementation))
        runner_bytes = runner.RUNNER_PATH.read_bytes()
        parent = open_environ(HF_HUB_OFFLINE="0", MARKER="keep")
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
            self.assertEqual(manifest["gpu_identity"]["logical_device"], "cuda:0")
            self.assertEqual(manifest["gpu_identity"]["logical_device_index"], 0)
            self.assertIs(type(manifest["gpu_identity"]["index"]), int)
            self.assertEqual(manifest["gpu_identity"]["index"], 1)
            self.assertEqual(manifest["gpu_identity"]["physical_gpu"], runner.PHYSICAL_GPU)
            self.assertEqual(manifest["gpu_identity"]["uuid"], "GPU-synthetic")
            self.assertEqual(manifest["gpu_identity"]["pci_bus_id"], "0000:01:00.0")
            self.assertEqual(manifest["gpu_identity"]["cuda_visible_devices"], "1")
            self.assertEqual(
                manifest["gpu_identity"]["cuda_device_order"],
                runner.CUDA_DEVICE_ORDER,
            )
            self.assertEqual(manifest["authorization"]["physical_gpu"], runner.PHYSICAL_GPU)
            self.assertEqual(
                manifest["child_environment_controls"]["CUDA_VISIBLE_DEVICES"],
                str(runner.PHYSICAL_GPU),
            )
            self.assertEqual(
                manifest["child_environment_controls"]["CUDA_DEVICE_ORDER"],
                runner.CUDA_DEVICE_ORDER,
            )
            self.assertEqual(
                manifest["child_environment_controls"]["physical_gpu"],
                runner.PHYSICAL_GPU,
            )
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
        assert_evidence_unchanged("accepted Phase A evidence changed")


class AcceptanceCorrectionTests(unittest.TestCase):
    def test_runtime_caches_stay_inside_the_evidence_directory(self):
        evidence = runner.evidence_directory_for_commit(COMMIT)
        parent = open_environ(HF_HUB_OFFLINE="0")
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
                environ=open_environ(),
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
                environ=open_environ(),
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
            assert_evidence_unchanged("accepted Phase A evidence changed")

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

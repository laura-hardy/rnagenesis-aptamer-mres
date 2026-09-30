"""Synthetic tests for the non-executable B1 Phase B runner.

External operations, GPU queries, CUDA, model loading, generation, and
biological sequence files are injected or mocked. The checked-in
configuration stays closed. These tests must not create Phase B evidence
or modify accepted Phase A evidence.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import io
import json
import os
import stat
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
    source = Path(path).read_bytes()
    code = compile(source, str(path), "exec", dont_inherit=True)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    exec(code, module.__dict__)
    return module


runner = load_source_module(
    "b1_phase_b_runner",
    ROOT / "scripts" / "b1_phase_b_runner.py",
)

COMMIT = "a" * 40
RUNTIME = "b" * 40
PHASE_A_EVIDENCE = Path(
    "/home/laura/rnagenesis-mres-runs/"
    "m4_b1_generic_generation_B1_generic_released_rnagenesis_de60793a66d1_phaseA"
)
HISTORICAL_EVIDENCE = Path(
    "/home/laura/rnagenesis-mres-runs/"
    "m4_b1_generic_generation_B1_generic_released_rnagenesis_bdb3dbda1650_phaseA"
)
EXPECTED_PHASE_A_SHA256 = {
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
_ACCEPTED_EVIDENCE_SNAPSHOT = None
_PHASE_B_PATHS_BEFORE = None


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


def _phase_b_run_paths():
    root = Path("/home/laura/rnagenesis-mres-runs")
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.name.endswith("_phaseB"))


def snapshot_accepted_evidence():
    global _ACCEPTED_EVIDENCE_SNAPSHOT, _PHASE_B_PATHS_BEFORE
    if PHASE_A_EVIDENCE.exists() or PHASE_A_EVIDENCE.is_symlink():
        _ACCEPTED_EVIDENCE_SNAPSHOT = _snapshot_tree(PHASE_A_EVIDENCE)
    else:
        _ACCEPTED_EVIDENCE_SNAPSHOT = None
    _PHASE_B_PATHS_BEFORE = _phase_b_run_paths()


def assert_historical_evidence_absent(message):
    if HISTORICAL_EVIDENCE.exists() or HISTORICAL_EVIDENCE.is_symlink():
        raise AssertionError("{}: {}".format(message, HISTORICAL_EVIDENCE))


def assert_evidence_unchanged(message):
    assert_historical_evidence_absent(message)
    present = PHASE_A_EVIDENCE.exists() or PHASE_A_EVIDENCE.is_symlink()
    if _ACCEPTED_EVIDENCE_SNAPSHOT is None:
        if present:
            raise AssertionError("{}: accepted evidence path was created".format(message))
        return
    if not present or not PHASE_A_EVIDENCE.is_dir():
        raise AssertionError("{}: accepted evidence directory changed".format(message))
    observed = _snapshot_tree(PHASE_A_EVIDENCE)
    if observed != _ACCEPTED_EVIDENCE_SNAPSHOT:
        raise AssertionError("{}: accepted evidence hashes changed".format(message))
    if _phase_b_run_paths() != _PHASE_B_PATHS_BEFORE:
        raise AssertionError("{}: a Phase B evidence directory was created".format(message))


def assert_forbidden_modules_absent(message):
    loaded = [name for name in FORBIDDEN_RUNTIME_MODULES if name in __import__("sys").modules]
    if loaded:
        raise AssertionError("{}: {}".format(message, ", ".join(loaded)))


def setUpModule():
    snapshot_accepted_evidence()
    assert_evidence_unchanged("accepted Phase A evidence changed before tests")
    assert_forbidden_modules_absent("test process imported a forbidden module before tests")


def tearDownModule():
    assert_evidence_unchanged("accepted Phase A evidence changed during tests")
    assert_forbidden_modules_absent("test process imported a forbidden module during tests")


class FakeStat(object):
    def __init__(self, mode, size):
        self.st_mode = mode
        self.st_size = size


def real_config_bytes():
    return runner.B1_CONFIG_PATH.read_bytes()


def real_config():
    return runner.load_config_bytes(real_config_bytes())


def authorisation(commit=COMMIT, physical_gpu=0, **overrides):
    evidence = runner.evidence_directory_for_commit(commit)
    block = {
        "authorisation_id": "synthetic-phase-b-authorisation",
        "authorisation_active": True,
        "activation_status": runner.ACTIVE_UNCONSUMED_STATUS,
        "consumed": False,
        "authorises_b1_phase_b": True,
        "gpu_use_authorised": True,
        "physical_gpu": physical_gpu,
        "executing_implementation_commit": commit,
        "mres_branch": "main",
        "condition": runner.CONDITION_LABEL,
        "phase": "B",
        "output_directory": evidence,
        "evidence_directory": evidence,
        "success_claimed": False,
        "m4_complete": False,
        "b1_eligible": False,
        "development_pool_authorised": False,
        "final_production_mapping_declared": False,
        "rejection_or_resampling_algorithm_declared": False,
    }
    block.update(overrides)
    return block


def opened_config(commit=COMMIT, physical_gpu=0, **auth_overrides):
    config = copy.deepcopy(real_config())
    config["consumable_by_executable_workflow"] = True
    config["document_status"] = runner.EXECUTABLE_DOCUMENT_STATUS
    config["phase_b"]["executable_now"] = True
    config["phase_b"]["status"] = runner.PHASE_B_EXECUTION_STATUS
    config["execution"]["authorised"] = True
    config["execution"]["gpu_authorised_by_this_approval"] = True
    config[runner.PHASE_B_AUTHORISATION_NAME] = authorisation(
        commit,
        physical_gpu,
        **auth_overrides,
    )
    return config


def open_environ(physical_gpu, **extra):
    environ = {
        "CUDA_VISIBLE_DEVICES": str(physical_gpu),
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
        return self.config_bytes

    def forbid(self, name):
        def inner(*args, **kwargs):
            self.events.append((name,))
            raise AssertionError("{} was called".format(name))

        return inner

    def build(self, **overrides):
        return runner.RunnerDependencies(
            read_bytes=overrides.get("read_bytes", self.read_bytes),
            lstat=overrides.get("lstat", self.forbid("lstat")),
            realpath=overrides.get("realpath", self.forbid("realpath")),
            sha256_file=overrides.get("sha256_file", self.forbid("sha256_file")),
            environ=self.environ,
            git=overrides.get("git", self.forbid("git")),
            gpu_preflight=overrides.get("gpu_preflight", self.forbid("gpu_preflight")),
            mkdir=overrides.get("mkdir", self.forbid("mkdir")),
            write_exclusive=overrides.get("write_exclusive", self.forbid("write_exclusive")),
            subprocess_run=overrides.get("subprocess_run", self.forbid("subprocess_run")),
            load_cleaner=overrides.get("load_cleaner", self.forbid("load_cleaner")),
            clock=overrides.get("clock", self.forbid("clock")),
            hostname=overrides.get("hostname", self.forbid("hostname")),
        )


def run_main(deps, output_dir, physical_gpu):
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = runner.main(
            ["--output-dir", output_dir, "--physical-gpu", str(physical_gpu)],
            deps=deps,
        )
    return code, stderr.getvalue()


def assert_closed(test, code, stderr, deps):
    test.assertEqual(code, 1)
    test.assertIn("error: configuration_not_consumable:", stderr)
    test.assertEqual([event[0] for event in deps.events], ["read_bytes"])


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
                ("rev-parse", "{}:{}".format(implementation_commit, runner.RUNNER_RELATIVE)),
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


def probe_payload(physical_gpu, **overrides):
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
        "cuda_visible_devices": str(physical_gpu),
        "cuda_device_order": runner.CUDA_DEVICE_ORDER,
    }
    payload.update(overrides)
    return payload


def nvidia_smi_text(physical_gpu, name="Synthetic GPU", index=None):
    if index is None:
        index = physical_gpu
    return "{}, GPU-synthetic-{}, 0000:01:00.0, {}, 81920, Default\n".format(
        index,
        physical_gpu,
        name,
    )


def synthetic_cleaner():
    def split_raw_records(text):
        if text == "":
            return []
        ended = text.endswith("\n")
        parts = text.split("\n")
        if ended:
            parts.pop()
        return parts

    def audit_line(_line_number, raw):
        body = raw
        prefix = []
        while body[:1] in "12":
            prefix.append(body[0])
            body = body[1:]
        suffix = []
        while body[-1:] in "12":
            suffix.append(body[-1])
            body = body[:-1]
        suffix.reverse()
        accepted = body != "" and all(character in "ACGU" for character in body)
        return {
            "raw": raw,
            "cleaned": body,
            "removed_prefix": "".join(prefix),
            "removed_suffix": "".join(suffix),
            "accepted": accepted,
            "reason": None if accepted else "rejected",
        }

    module = types.SimpleNamespace(split_raw_records=split_raw_records, audit_line=audit_line)
    return module


def exact_line(length):
    body = ("ACGU" * ((length // 4) + 1))[:length]
    return "11" + body + "2"


class ClosedConfigurationTests(unittest.TestCase):
    def test_checked_in_configuration_refuses_before_every_side_effect(self):
        config = real_config()
        self.assertIs(config["consumable_by_executable_workflow"], False)
        self.assertEqual(
            config["document_status"],
            "APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION",
        )
        self.assertIs(config["execution"]["authorised"], False)
        self.assertIs(config["execution"]["gpu_authorised_by_this_approval"], False)
        self.assertIs(config["phase_b"]["executable_now"], False)
        self.assertNotIn(runner.PHASE_B_AUTHORISATION_NAME, config)
        self.assertIs(config["scientific_execution_authorisation"]["consumed"], True)
        self.assertIs(config["scientific_execution_authorisation"]["phase_b_authorised"], False)
        self.assertIs(config["scientific_execution_authorisation"]["b1_eligible"], False)
        self.assertIs(config["human_approval"]["m4_complete"], False)
        self.assertIs(config["limited_development_pool"]["phase_b_candidate_mapping_unblocks_this_pool"], False)
        record = config["phase_b"]["implementation_record"]
        self.assertEqual(record["status"], "AWAITING_REVIEW_NOT_EXECUTION")
        self.assertEqual(record["runner"], "scripts/b1_phase_b_runner.py")
        self.assertIs(record["authorisation_block_present"], False)
        self.assertIs(record["implementation_commit_recorded"], False)
        self.assertIs(record["authorization_commit_recorded"], False)
        self.assertIs(record["output_path_recorded"], False)
        self.assertIs(record["approval_timestamp_recorded"], False)
        self.assertIs(record["selected_physical_gpu_recorded"], False)
        hashes = config["phase_a_evidence_acceptance"]["evidence_sha256"]
        self.assertEqual(hashes["phase_a_manifest_json"], EXPECTED_PHASE_A_SHA256["phase_a_manifest.json"])
        self.assertEqual(
            hashes["phase_a_audited_attempts_jsonl"],
            EXPECTED_PHASE_A_SHA256["phase_a_audited_attempts.jsonl"],
        )
        for physical_gpu in ("0", "1", "2", ""):
            for output_dir in (
                str(PHASE_A_EVIDENCE),
                str(HISTORICAL_EVIDENCE),
                "/tmp/not-a-phase-b-evidence-directory",
                "relative/output",
            ):
                recorder = RecordingDeps(real_config_bytes(), {})
                code, stderr = run_main(recorder.build(), output_dir, physical_gpu)
                assert_closed(self, code, stderr, recorder)
        assert_evidence_unchanged("closed-gate test touched evidence")

    def test_plan_mutation_refuses_before_output_inspection(self):
        config = opened_config()
        config["phase_b"]["frozen_biological_lengths"] = [20]
        recorder = RecordingDeps(dumped(config), open_environ(0))
        code, stderr = run_main(recorder.build(), "/tmp/unused", "0")
        self.assertEqual(code, 1)
        self.assertIn("error: phase_b_plan_invalid:", stderr)
        self.assertEqual([event[0] for event in recorder.events], ["read_bytes"])


class FrozenScheduleTests(unittest.TestCase):
    def test_exact_frozen_length_list(self):
        config = real_config()
        lengths = list(config["phase_b"]["frozen_biological_lengths"])
        self.assertEqual(lengths, list(runner.FROZEN_TRAIN_LENGTHS))
        self.assertEqual(lengths, sorted(set(lengths)))
        self.assertEqual(len(lengths), 89)
        self.assertEqual(lengths[0], 20)
        self.assertEqual(lengths[-1], 123)
        self.assertNotIn(94, lengths)
        self.assertNotIn(101, lengths)
        provenance = config["phase_b"]["frozen_train_length_provenance"]
        self.assertEqual(
            provenance["m3_report"],
            "docs/fine_tuning/m3_frozen_corpus_loader_and_modelling_interface.md",
        )
        self.assertEqual(
            provenance["accepted_m3_summary_sha256"],
            "8862ecb066fac12ae80529737a2398322227f8789af07c2de2d375279896638c",
        )
        self.assertEqual(
            provenance["accepted_m3_tokenizer_audit_sha256"],
            "063a068187e5b34c598b1ef4a294f924f3167538aec824786d6e9fac01d4eb9f",
        )
        self.assertEqual(provenance["train_core_count"], 669)
        self.assertEqual(provenance["distinct_train_length_count"], 89)
        self.assertEqual(provenance["minimum"], 20)
        self.assertEqual(provenance["maximum"], 123)
        self.assertIs(provenance["source_files_opened_by_runner"], False)

    def test_exact_schedule_caps_seeds_and_indexes(self):
        plan = runner.build_phase_b_plan(real_config())
        self.assertEqual(len(plan), 89)
        self.assertEqual(len(plan) * 16, 1424)
        lengths = []
        seeds = []
        global_indexes = []
        for invocation in plan:
            length = invocation["requested_biological_length"]
            lengths.append(length)
            seeds.append(invocation["seed"])
            self.assertEqual(invocation["max_seq_len"], length + 1)
            self.assertEqual(invocation["cap_offset"], 1)
            self.assertEqual(invocation["batch_size"], 16)
            self.assertEqual(invocation["batch_num"], 1)
            self.assertIs(invocation["seed_confounded_with_length"], True)
            self.assertIs(invocation["independent_replicate"], False)
            self.assertEqual(invocation["attempt_index_first"], 0)
            self.assertEqual(invocation["attempt_index_last"], 15)
            start = invocation["invocation_index"] * 16
            self.assertEqual(invocation["attempt_index_global_first"], start)
            self.assertEqual(invocation["attempt_index_global_last"], start + 15)
            global_indexes.extend(range(start, start + 16))
        self.assertEqual(lengths, list(runner.FROZEN_TRAIN_LENGTHS))
        self.assertEqual(seeds, list(range(42000, 42089)))
        self.assertEqual(seeds[0], 42000)
        self.assertEqual(seeds[-1], 42088)
        self.assertEqual(len(set(seeds)), 89)
        self.assertEqual(global_indexes, list(range(1424)))
        within = []
        for invocation in plan:
            within.extend(range(16))
        self.assertEqual(within[:16], list(range(16)))
        self.assertEqual(within[-16:], list(range(16)))

    def test_schedule_mutations_refuse(self):
        cases = []
        mutated = copy.deepcopy(real_config())
        mutated["phase_b"]["frozen_biological_lengths"][-1] = 124
        cases.append(mutated)
        omitted = copy.deepcopy(real_config())
        del omitted["phase_b"]["frozen_biological_lengths"][4]
        cases.append(omitted)
        duplicated = copy.deepcopy(real_config())
        duplicated["phase_b"]["frozen_biological_lengths"][2] = duplicated["phase_b"]["frozen_biological_lengths"][1]
        cases.append(duplicated)
        reordered = copy.deepcopy(real_config())
        reordered["phase_b"]["frozen_biological_lengths"][0] = 21
        reordered["phase_b"]["frozen_biological_lengths"][1] = 20
        cases.append(reordered)
        extra = copy.deepcopy(real_config())
        extra["phase_b"]["frozen_biological_lengths"].append(124)
        cases.append(extra)
        wrong_cap = copy.deepcopy(real_config())
        wrong_cap["phase_b"]["frozen_schedule"]["max_seq_len_offset"] = 2
        cases.append(wrong_cap)
        wrong_seed = copy.deepcopy(real_config())
        wrong_seed["phase_b"]["frozen_schedule"]["base_seed"] = 42001
        cases.append(wrong_seed)
        wrong_attempts = copy.deepcopy(real_config())
        wrong_attempts["phase_b"]["frozen_schedule"]["raw_attempts_per_length"] = 15
        cases.append(wrong_attempts)
        wrong_total = copy.deepcopy(real_config())
        wrong_total["phase_b"]["frozen_schedule"]["total_raw_attempts"] = 1423
        cases.append(wrong_total)
        for config in cases:
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.build_phase_b_plan(config)
            self.assertEqual(caught.exception.code, "phase_b_plan_invalid")


class AuthorisationTests(unittest.TestCase):
    def test_separate_phase_b_authorisation_is_mandatory(self):
        config = opened_config()
        del config[runner.PHASE_B_AUTHORISATION_NAME]
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_phase_b_authorisation(config, 0)
        self.assertEqual(caught.exception.code, "phase_a_authorisation_cannot_authorise_phase_b")

    def test_consumed_phase_a_authorisation_cannot_authorise_phase_b(self):
        config = opened_config()
        config[runner.PHASE_B_AUTHORISATION_NAME] = copy.deepcopy(
            real_config()["scientific_execution_authorisation"]
        )
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_phase_b_authorisation(config, 1)
        self.assertEqual(caught.exception.code, "phase_a_authorisation_cannot_authorise_phase_b")
        self.assertIs(config["scientific_execution_authorisation"]["consumed"], True)
        self.assertEqual(config["scientific_execution_authorisation"]["phase"], "A")

    def test_inactive_consumed_wrong_phase_gpu_directory_commit_and_overbroad_refuse(self):
        cases = (
            ({"authorisation_active": False}, "phase_b_authorisation_inactive"),
            ({"activation_status": "consumed_complete", "consumed": False}, "phase_b_authorisation_inactive"),
            ({"consumed": True}, "phase_b_authorisation_consumed"),
            ({"phase": "C"}, "phase_b_wrong_phase"),
            ({"physical_gpu": 1}, "phase_b_gpu_mismatch"),
            ({"physical_gpu": True}, "phase_b_gpu_mismatch"),
            ({"output_directory": "/tmp/elsewhere"}, "authorisation_evidence_mismatch"),
            ({"evidence_directory": "/tmp/elsewhere"}, "authorisation_evidence_mismatch"),
            ({"executing_implementation_commit": "abc"}, "authorisation_commit_invalid"),
            ({"b1_eligible": True}, "phase_b_authorisation_overbroad"),
            ({"m4_complete": True}, "phase_b_authorisation_overbroad"),
            ({"development_pool_authorised": True}, "phase_b_authorisation_overbroad"),
            ({"final_production_mapping_declared": True}, "phase_b_authorisation_overbroad"),
            ({"rejection_or_resampling_algorithm_declared": True}, "phase_b_authorisation_overbroad"),
            ({"authorises_development_pool": True}, "phase_b_authorisation_overbroad"),
        )
        for overrides, code in cases:
            config = opened_config(physical_gpu=0)
            config[runner.PHASE_B_AUTHORISATION_NAME].update(overrides)
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.assert_phase_b_authorisation(config, 0)
            self.assertEqual(caught.exception.code, code, overrides)

    def test_gpu_zero_and_gpu_one_authorisations_pass(self):
        for physical_gpu in (0, 1):
            snapshot = runner.assert_phase_b_authorisation(
                opened_config(physical_gpu=physical_gpu),
                physical_gpu,
            )
            self.assertEqual(snapshot["phase"], "B")
            self.assertEqual(snapshot["physical_gpu"], physical_gpu)
            self.assertIs(snapshot["authorises_b1_phase_b"], True)
            self.assertIs(snapshot["consumed"], False)
            self.assertTrue(snapshot["evidence_directory"].endswith("_phaseB"))
            self.assertNotIn("_phaseA", snapshot["evidence_directory"])

    def test_only_exact_boolean_false_consumed_passes(self):
        snapshot = runner.assert_phase_b_authorisation(opened_config(physical_gpu=0), 0)
        self.assertIs(snapshot["consumed"], False)
        malformed = (True, "false", "true", 0, 1, None, [], {})
        for value in malformed:
            config = opened_config(physical_gpu=0)
            config[runner.PHASE_B_AUTHORISATION_NAME]["consumed"] = value
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.assert_phase_b_authorisation(config, 0)
            self.assertEqual(
                caught.exception.code,
                "phase_b_authorisation_consumed",
                repr(value),
            )
        missing = opened_config(physical_gpu=0)
        del missing[runner.PHASE_B_AUTHORISATION_NAME]["consumed"]
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_phase_b_authorisation(missing, 0)
        self.assertEqual(caught.exception.code, "phase_b_authorisation_missing")
        extra = opened_config(physical_gpu=0)
        extra[runner.PHASE_B_AUTHORISATION_NAME]["consumed"] = "false"
        extra[runner.PHASE_B_AUTHORISATION_NAME]["unexpected_field"] = False
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_phase_b_authorisation(extra, 0)
        self.assertEqual(caught.exception.code, "phase_b_authorisation_overbroad")


class GpuAndOutputTests(unittest.TestCase):
    def test_runtime_gpus_pass_mocked_preflight_and_source_does_not_fix_one(self):
        source = (ROOT / "scripts" / "b1_phase_b_runner.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id in ("PHYSICAL_GPU", "CUDA_VISIBLE_DEVICES", "SELECTED_PHYSICAL_GPU"):
                    self.fail(target.id)
                if isinstance(node.value, ast.Constant) and node.value.value in (0, 1, "0", "1"):
                    if "GPU" in target.id or "CUDA" in target.id:
                        self.fail(target.id)
        self.assertEqual(runner.SUPPORTED_PHYSICAL_GPUS, (0, 1))
        self.assertNotIn("PHYSICAL_GPU = 0", source)
        self.assertNotIn("PHYSICAL_GPU = 1", source)
        self.assertEqual(runner.physical_gpu_query_argv(0)[-1], "0")
        self.assertEqual(runner.physical_gpu_query_argv(1)[-1], "1")
        self.assertEqual(runner.CUDA_DEVICE_ORDER, "PCI_BUS_ID")
        for physical_gpu in (0, 1):
            env = open_environ(physical_gpu)
            identity = runner.preflight_gpu(
                env,
                physical_gpu,
                lambda physical_gpu=physical_gpu: nvidia_smi_text(physical_gpu),
                lambda physical_gpu=physical_gpu: json.dumps(probe_payload(physical_gpu)),
                resolve_python=lambda path: path,
            )
            self.assertEqual(identity["physical_gpu"], physical_gpu)
            self.assertEqual(identity["index"], physical_gpu)
            self.assertEqual(identity["logical_device"], "cuda:0")
            self.assertIs(identity["logical_device_confirmed"], True)
            self.assertEqual(identity["device_count"], 1)
            self.assertEqual(identity["cuda_visible_devices"], str(physical_gpu))
            self.assertEqual(identity["cuda_device_order"], "PCI_BUS_ID")
            self.assertIs(identity["cpu_fallback"], False)
            self.assertEqual(
                runner.physical_gpu_query_argv(physical_gpu),
                [
                    "nvidia-smi",
                    "--query-gpu=index,uuid,pci.bus_id,name,memory.total,compute_mode",
                    "--format=csv,noheader,nounits",
                    "-i",
                    str(physical_gpu),
                ],
            )

    def test_cli_environment_and_query_mismatches_refuse(self):
        config = opened_config(physical_gpu=0)
        snapshot = runner.assert_phase_b_authorisation(config, 0)
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_phase_b_authorisation(config, 1)
        self.assertEqual(caught.exception.code, "phase_b_gpu_mismatch")
        refusals = (
            ({}, 0, "cuda_visible_devices_missing"),
            ({"CUDA_VISIBLE_DEVICES": "1", "CUDA_DEVICE_ORDER": "PCI_BUS_ID"}, 0, "cuda_visible_devices_refused"),
            ({"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "FASTEST_FIRST"}, 0, "cuda_device_order_refused"),
            ({"CUDA_VISIBLE_DEVICES": "0"}, 0, "cuda_device_order_missing"),
        )
        for environ, physical_gpu, code in refusals:
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.assert_cuda_environment(environ, physical_gpu)
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(snapshot["physical_gpu"], 0)
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.parse_gpu_identity(nvidia_smi_text(0, index=1), 0)
        self.assertEqual(caught.exception.code, "gpu_identity_mismatch")
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.parse_physical_gpu_argument("2")
        self.assertEqual(caught.exception.code, "unsupported_physical_gpu")
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.parse_physical_gpu_argument("01")
        self.assertEqual(caught.exception.code, "unsupported_physical_gpu")

    def test_cpu_zero_multi_allocation_malformed_and_identity_mismatch_refuse(self):
        identity = runner.parse_gpu_identity(nvidia_smi_text(0), 0)
        cases = (
            ({"cuda_available": False}, "cuda_unavailable"),
            ({"cuda_available": True, "device_count": 0, "allocation_ok": False}, "cuda_device_count"),
            ({"device_count": 2}, "cuda_device_count"),
            ({"allocation_ok": False, "logical_device_index": None, "logical_device_confirmed": False}, "cuda_allocation_failed"),
            ({"device_name": "Other GPU"}, "gpu_identity_mismatch"),
            ({"cuda_visible_devices": "1"}, "cuda_probe_mismatch"),
            ({"cuda_device_order": "FASTEST_FIRST"}, "cuda_probe_mismatch"),
        )
        for overrides, code in cases:
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.validate_cuda_probe(
                    probe_payload(0, **overrides),
                    identity,
                    0,
                    resolve_python=lambda path: path,
                )
            self.assertEqual(caught.exception.code, code, overrides)
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.parse_cuda_probe_json("not-json")
        self.assertEqual(caught.exception.code, "cuda_probe_malformed")
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.parse_cuda_probe_json("")
        self.assertEqual(caught.exception.code, "cuda_probe_malformed")

    def test_output_mismatch_alias_symlink_existing_and_overwrite_refuse(self):
        snapshot = runner.assert_phase_b_authorisation(opened_config(physical_gpu=0), 0)
        expected = snapshot["evidence_directory"]

        def absent(_path):
            raise FileNotFoundError(_path)

        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_output_directory("/tmp/other", snapshot, absent, lambda path: path)
        self.assertEqual(caught.exception.code, "output_path_mismatch")
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_output_directory("relative", snapshot, absent, lambda path: path)
        self.assertEqual(caught.exception.code, "output_path_mismatch")
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_output_directory(
                expected,
                snapshot,
                absent,
                lambda path: path + "/alias",
            )
        self.assertEqual(caught.exception.code, "output_path_symlink")
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_output_directory(
                expected,
                snapshot,
                lambda path: FakeStat(stat.S_IFLNK, 0),
                lambda path: path,
            )
        self.assertEqual(caught.exception.code, "output_path_symlink")
        for mode in (stat.S_IFDIR, stat.S_IFREG):
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.assert_output_directory(
                    expected,
                    snapshot,
                    lambda path, mode=mode: FakeStat(mode, 0),
                    lambda path: path,
                )
            self.assertEqual(caught.exception.code, "output_path_exists")
        self.assertFalse(Path(expected).exists())


class GenerationContractTests(unittest.TestCase):
    def test_prohibited_model_and_cleaner_paths_refuse(self):
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_diffusion_selection("checkpoints/Aptamer/diffusion")
        self.assertEqual(caught.exception.code, "prohibited_diffusion")
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_cleaner_allowed(runner.PROHIBITED_CLEANER)
        self.assertEqual(caught.exception.code, "prohibited_cleaner")
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_not_biological_data_path("/tmp/TRAIN/ft_train.csv")
        self.assertEqual(caught.exception.code, "biological_data_access_refused")
        with self.assertRaises(runner.PhaseBRunnerError) as caught:
            runner.assert_argv_prohibitions(
                ["python", "generation.py", "--guidance", "--dm_file", "checkpoints/Aptamer/diffusion"]
            )
        self.assertIn(
            caught.exception.code,
            ("prohibited_generation_option", "prohibited_generation_path"),
        )

    def test_generation_argv_uses_approved_settings(self):
        plan = runner.build_phase_b_plan(real_config())
        evidence = runner.evidence_directory_for_commit(COMMIT)
        for invocation in (plan[0], plan[-1]):
            argv = runner.build_generation_argv(invocation, evidence, guidance_enabled=False)
            self.assertEqual(argv[0], runner.PINNED_PYTHON)
            self.assertEqual(runner._argv_value(argv, "--num_inference_steps"), "50")
            self.assertEqual(runner._argv_value(argv, "--eta"), "0")
            self.assertEqual(runner._argv_value(argv, "--top_p"), "0.95")
            self.assertEqual(runner._argv_value(argv, "--top_k"), "0")
            self.assertEqual(runner._argv_value(argv, "--batch_size"), "16")
            self.assertEqual(runner._argv_value(argv, "--batch_num"), "1")
            self.assertEqual(runner._argv_value(argv, "--device"), "cuda:0")
            self.assertEqual(
                runner._argv_value(argv, "--max_seq_len"),
                str(invocation["requested_biological_length"] + 1),
            )
            self.assertEqual(runner._argv_value(argv, "--seed"), str(invocation["seed"]))
            self.assertIn("--do_sample", argv)
            for option in runner.PROHIBITED_ARGV_OPTIONS:
                self.assertNotIn(option, argv)
            self.assertNotIn("--guidance", argv)
            joined = " ".join(argv)
            self.assertNotIn("checkpoints/Aptamer/diffusion", joined)
            self.assertNotIn("clean_generated_sequences.py", joined)
            self.assertNotIn("ft_train.csv", joined)
            self.assertNotIn(runner.M3_REPORT, joined)

    def test_all_attempt_records_match_the_frozen_plan(self):
        plan = runner.build_phase_b_plan(real_config())
        cleaner = synthetic_cleaner()
        attempts = []
        for invocation in plan:
            if invocation["invocation_index"] == 0:
                lines = ["TTTT"] * 16
            else:
                lines = [exact_line(invocation["requested_biological_length"])] * 16
            text = "".join(line + "\n" for line in lines)
            attempts.extend(
                runner.audit_invocation_output(
                    text,
                    cleaner.split_raw_records,
                    cleaner.audit_line,
                    invocation,
                )
            )
        self.assertEqual(len(attempts), 1424)
        runner._assert_complete_attempts(attempts, plan)
        self.assertEqual([row["attempt_index"] for row in attempts], list(range(1424)))
        self.assertEqual(attempts[0]["attempt_within_length"], 0)
        self.assertEqual(attempts[15]["attempt_within_length"], 15)
        self.assertEqual(attempts[16]["attempt_index"], 16)
        self.assertIs(attempts[0]["validity"], False)
        self.assertIs(attempts[0]["exact_length"], False)
        self.assertEqual(attempts[0]["rejection_reason"], "rejected")
        self.assertIs(attempts[16]["exact_length"], True)
        self.assertEqual(attempts[-1]["requested_biological_length"], 123)
        self.assertEqual(attempts[-1]["max_seq_len"], 124)
        self.assertEqual(attempts[-1]["seed"], 42088)
        raw = runner.serialize_jsonl(attempts, runner.RAW_LEDGER_KEYS)
        audited = runner.serialize_jsonl(attempts, runner.AUDITED_LEDGER_KEYS)
        self.assertNotEqual(raw, audited)
        self.assertEqual(raw.count(b"\n"), 1424)
        self.assertEqual(audited.count(b"\n"), 1424)
        raw_keys = set(json.loads(raw.splitlines()[0]))
        audited_keys = set(json.loads(audited.splitlines()[0]))
        self.assertTrue(
            {
                "leading_boundary_marker_run",
                "trailing_boundary_marker_run",
                "cleaned_sequence",
                "cleaned_length",
                "termination_observation",
                "exact_length",
            }.issubset(audited_keys - raw_keys)
        )
        self.assertIn("validity", raw_keys)
        self.assertIn("rejection_reason", raw_keys)


class DiagnosticTests(unittest.TestCase):
    def attempt(self, length, valid, cleaned, exact, termination="not_observable_from_decoded_text"):
        return {
            "requested_biological_length": length,
            "raw_decoded_text": "synthetic",
            "validity": valid,
            "cleaned_sequence": cleaned if valid else "",
            "cleaned_length": len(cleaned) if valid else 0,
            "exact_length": exact,
            "termination_observation": termination,
            "leading_boundary_marker_run": "11",
            "trailing_boundary_marker_run": "",
        }

    def test_zero_valid_outputs_have_exact_hit_rate_zero(self):
        attempts = [self.attempt(50, False, "", False) for _ in range(16)]
        diagnostics = runner.phase_b_diagnostics(attempts)
        self.assertEqual(diagnostics["valid_outputs"], 0)
        self.assertEqual(diagnostics["invalid_outputs"], 16)
        self.assertEqual(diagnostics["overall_exact_hit_rate"], 0.0)
        self.assertEqual(diagnostics["per_length"][0]["exact_hit_rate"], 0.0)
        self.assertEqual(diagnostics["per_length"][0]["raw_attempts"], 16)
        self.assertEqual(diagnostics["lengths_below_provisional_0_50_floor"], 1)
        self.assertIs(diagnostics["provisional_aggregate_0_90_diagnostic_reached"], False)
        self.assertIs(diagnostics["b1_eligible"], False)
        self.assertEqual(diagnostics["b1_eligibility"], "not_declared")

    def test_provisional_diagnostics_do_not_change_eligibility(self):
        attempts = []
        for length in runner.FROZEN_TRAIN_LENGTHS:
            sequence = "A" * length
            for _index in range(16):
                attempts.append(
                    self.attempt(length, True, sequence, True, runner.EOS_OBSERVED)
                )
        diagnostics = runner.phase_b_diagnostics(attempts)
        self.assertEqual(diagnostics["raw_attempts"], 1424)
        self.assertEqual(diagnostics["parsed_outputs"], 1424)
        self.assertEqual(diagnostics["valid_outputs"], 1424)
        self.assertEqual(diagnostics["exact_hits"], 1424)
        self.assertEqual(diagnostics["overall_exact_hit_rate"], 1.0)
        self.assertEqual(diagnostics["valid_fraction"], 1.0)
        self.assertEqual(diagnostics["lengths_below_provisional_0_50_floor"], 0)
        self.assertIs(diagnostics["provisional_aggregate_0_90_diagnostic_reached"], True)
        self.assertEqual(len(diagnostics["per_length"]), 89)
        self.assertIs(diagnostics["final_production_mapping_declared"], False)
        self.assertIs(diagnostics["rejection_or_resampling_algorithm_declared"], False)
        self.assertIs(diagnostics["development_pool_authorised"], False)
        self.assertIs(diagnostics["development_pool_executed"], False)
        self.assertIs(diagnostics["m4_complete"], False)
        self.assertIs(diagnostics["b1_eligible"], False)
        self.assertEqual(diagnostics["eligibility_decision"], "not_made")
        self.assertEqual(diagnostics["per_length"][0]["unique_valid_outputs"], 1)
        self.assertEqual(diagnostics["per_length"][0]["duplicate_outputs"], 15)
        self.assertEqual(diagnostics["per_length"][0]["eos_marker_observed_count"], 16)
        self.assertEqual(diagnostics["per_length"][0]["eos_marker_observed_rate"], 1.0)
        self.assertEqual(diagnostics["per_length"][0]["early_eos_count"], 0)
        self.assertEqual(diagnostics["per_length"][0]["early_eos_rate"], 0.0)
        self.assertEqual(diagnostics["eos_marker_observed_count"], 1424)
        self.assertEqual(diagnostics["early_eos_count"], 0)
        self.assertEqual(diagnostics["eos_marker_and_early_eos_rate_denominator"], "raw_attempts")
        self.assertTrue(diagnostics["per_length"][0]["cleaned_length_distribution"])
        self.assertTrue(diagnostics["per_length"][0]["leading_boundary_distribution"])
        self.assertTrue(diagnostics["per_length"][0]["trailing_boundary_distribution"])
        self.assertIs(diagnostics["final_production_mapping_declared"], False)
        self.assertIs(diagnostics["development_pool_authorised"], False)
        self.assertIs(diagnostics["m4_complete"], False)
        self.assertEqual(diagnostics["b1_eligibility"], "not_declared")
        runner._assert_diagnostics_do_not_authorise(diagnostics)

    def audited_attempt(self, raw, length, attempt_within_length):
        cleaner = synthetic_cleaner()
        invocation = {
            "invocation_index": 0,
            "requested_biological_length": length,
            "max_seq_len": length + 1,
            "seed": 42000,
        }
        audited = cleaner.audit_line(attempt_within_length + 1, raw)
        return runner.adapt_audited_line(raw, audited, invocation, attempt_within_length)

    def test_eos_marker_observed_is_not_early_eos(self):
        length = 20
        body = ("ACGU" * ((length // 4) + 1))[:length]
        exact_eos = self.audited_attempt("11" + body + "2", length, 0)
        shorter_eos = self.audited_attempt("11" + body[:-1] + "2", length, 1)
        exact_without = self.audited_attempt("11" + body, length, 2)
        invalid_eos = self.audited_attempt("11" + ("T" * length) + "2", length, 3)

        self.assertIs(exact_eos["validity"], True)
        self.assertIs(exact_eos["exact_length"], True)
        self.assertEqual(exact_eos["cleaned_length"], length)
        self.assertEqual(exact_eos["termination_observation"], "eos_marker_observed")
        self.assertTrue(exact_eos["raw_decoded_text"].endswith("2"))
        self.assertIs(runner.early_eos_event(exact_eos), False)

        self.assertIs(shorter_eos["validity"], True)
        self.assertIs(shorter_eos["exact_length"], False)
        self.assertLess(shorter_eos["cleaned_length"], length)
        self.assertEqual(shorter_eos["termination_observation"], "eos_marker_observed")
        self.assertTrue(shorter_eos["raw_decoded_text"].endswith("2"))
        self.assertIs(runner.early_eos_event(shorter_eos), True)

        self.assertIs(exact_without["validity"], True)
        self.assertIs(exact_without["exact_length"], True)
        self.assertEqual(exact_without["termination_observation"], "not_observable_from_decoded_text")
        self.assertFalse(exact_without["raw_decoded_text"].endswith("2"))
        self.assertIs(runner.early_eos_event(exact_without), False)

        self.assertIs(invalid_eos["validity"], False)
        self.assertEqual(invalid_eos["termination_observation"], "eos_marker_observed")
        self.assertTrue(invalid_eos["raw_decoded_text"].endswith("2"))
        self.assertIs(runner.early_eos_event(invalid_eos), False)

        exact_only = runner.phase_b_diagnostics([exact_eos])
        exact_row = exact_only["per_length"][0]
        self.assertEqual(exact_only["exact_hits"], 1)
        self.assertEqual(exact_only["eos_marker_observed_count"], 1)
        self.assertEqual(exact_only["early_eos_count"], 0)
        self.assertEqual(exact_row["eos_marker_observed_count"], 1)
        self.assertEqual(exact_row["eos_marker_observed_rate"], 1.0)
        self.assertEqual(exact_row["early_eos_count"], 0)
        self.assertEqual(exact_row["early_eos_rate"], 0.0)

        with_shorter = runner.phase_b_diagnostics([exact_eos, shorter_eos])
        shorter_row = with_shorter["per_length"][0]
        self.assertEqual(with_shorter["eos_marker_observed_count"], 2)
        self.assertEqual(with_shorter["early_eos_count"], 1)
        self.assertEqual(shorter_row["eos_marker_observed_count"], 2)
        self.assertEqual(shorter_row["eos_marker_observed_rate"], 1.0)
        self.assertEqual(shorter_row["early_eos_count"], 1)
        self.assertEqual(shorter_row["early_eos_rate"], 0.5)

        with_plain = runner.phase_b_diagnostics([exact_eos, shorter_eos, exact_without])
        plain_row = with_plain["per_length"][0]
        self.assertEqual(with_plain["exact_hits"], 2)
        self.assertEqual(with_plain["eos_marker_observed_count"], 2)
        self.assertEqual(with_plain["early_eos_count"], 1)
        self.assertEqual(plain_row["eos_marker_observed_count"], 2)
        self.assertEqual(plain_row["early_eos_count"], 1)
        self.assertEqual(plain_row["raw_attempts"], 3)

        invalid_only = runner.phase_b_diagnostics([invalid_eos])
        invalid_row = invalid_only["per_length"][0]
        self.assertEqual(invalid_only["valid_outputs"], 0)
        self.assertEqual(invalid_only["invalid_outputs"], 1)
        self.assertEqual(invalid_only["exact_hits"], 0)
        self.assertEqual(invalid_only["eos_marker_observed_count"], 1)
        self.assertEqual(invalid_only["early_eos_count"], 0)
        self.assertEqual(invalid_row["invalid_outputs"], 1)
        self.assertEqual(invalid_row["eos_marker_observed_count"], 1)
        self.assertEqual(invalid_row["early_eos_count"], 0)

        combined = runner.phase_b_diagnostics(
            [exact_eos, shorter_eos, exact_without, invalid_eos]
        )
        combined_row = combined["per_length"][0]
        trailing = [item["value"] for item in combined_row["trailing_boundary_distribution"]]
        leading = [item["value"] for item in combined_row["leading_boundary_distribution"]]
        self.assertEqual(combined["valid_outputs"], 3)
        self.assertEqual(combined["invalid_outputs"], 1)
        self.assertEqual(combined["eos_marker_observed_count"], 3)
        self.assertEqual(combined["early_eos_count"], 1)
        self.assertEqual(combined["eos_marker_and_early_eos_rate_denominator"], "raw_attempts")
        self.assertIn("2", trailing)
        self.assertIn("", trailing)
        self.assertIn("11", leading)
        self.assertTrue(combined_row["cleaned_length_distribution"])
        self.assertIs(combined["b1_eligible"], False)
        self.assertIs(combined["final_production_mapping_declared"], False)
        self.assertIs(combined["development_pool_authorised"], False)
        self.assertIs(combined["m4_complete"], False)
        self.assertEqual(combined["eligibility_decision"], "not_made")


class EvidenceTests(unittest.TestCase):
    def prepared(self, tmp, physical_gpu=0):
        config = opened_config(physical_gpu=physical_gpu)
        return {
            "output_dir": tmp,
            "config": config,
            "snapshot": runner.assert_phase_b_authorisation(config, physical_gpu),
            "plan": runner.build_phase_b_plan(config),
            "provenance": {"mres": {"authorization_commit": RUNTIME}},
            "pins": [],
            "gpu": {
                "physical_gpu": physical_gpu,
                "index": physical_gpu,
                "uuid": "GPU-synthetic-{}".format(physical_gpu),
                "pci_bus_id": "0000:01:00.0",
                "logical_device": "cuda:0",
                "logical_device_confirmed": True,
                "cuda_visible_devices": str(physical_gpu),
                "cpu_fallback": False,
                "packages": {"torch": "2.4.0"},
                "python_resolved_path": runner.PINNED_PYTHON,
                "python_version": "3.11.0",
            },
            "selected_physical_gpu": physical_gpu,
            "started_at": "2026-09-30T00:00:00Z",
            "commands": [],
            "raw_outputs": [],
            "completed_invocation_indexes": [],
            "attempts": [],
            "attempt_count": 0,
        }

    def test_unexpected_exception_retains_progress_and_original_classification(self):
        secret = "ACGUACGUACGUACGU"
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepared(tmp)
            calls = {"count": 0}

            def subprocess_run(argv, cwd, env, shell=False):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise TypeError(secret)
                self.write_output(tmp, argv, invalid=False)

            deps = runner.RunnerDependencies(
                read_bytes=lambda path: Path(path).read_bytes(),
                lstat=os.lstat,
                environ=open_environ(0),
                write_exclusive=runner.write_exclusive_bytes,
                subprocess_run=subprocess_run,
                load_cleaner=lambda source_bytes=None: synthetic_cleaner(),
                clock=lambda: "2026-09-30T00:01:00Z",
                hostname=lambda: "synthetic-host",
            )
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.after_directory_created(
                    tmp,
                    deps,
                    lambda: runner.execute_phase_b(prepared, deps),
                    prepared,
                )
            self.assertEqual(caught.exception.code, "unexpected_runtime_failure")
            self.assertNotIn(secret, caught.exception.detail)
            self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())
            document = json.loads((Path(tmp) / runner.FAILURE_MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(document["status"], "failed")
            self.assertEqual(document["failure"]["code"], "unexpected_runtime_failure")
            self.assertEqual(document["failure"]["completed_invocation_indexes"], [0])
            self.assertEqual(document["failure"]["attempt_count"], 16)
            self.assertIs(document["b1_eligible"], False)
            self.assertIs(document["m4_complete"], False)

    def write_output(self, tmp, argv, invalid):
        mid = argv[argv.index("--mid_folder") + 1]
        remark = argv[argv.index("--remark") + 1]
        folder = Path(argv[argv.index("--superfolder") + 1]) / mid
        folder.mkdir(parents=True, exist_ok=False)
        index = int(mid.split("_")[1])
        length = runner.FROZEN_TRAIN_LENGTHS[index]
        if invalid or index == 0:
            lines = ["TTTT"] * 16
        else:
            lines = [exact_line(length)] * 16
        (folder / runner.predicted_generation_filename(remark)).write_bytes(
            ("".join(line + "\n" for line in lines)).encode("utf-8")
        )

    def test_keyboard_interrupt_and_system_exit_are_not_caught(self):
        deps = runner.RunnerDependencies(
            clock=lambda: "2026-09-30T00:02:00Z",
            hostname=lambda: "synthetic-host",
        )
        for exc_type in (KeyboardInterrupt, SystemExit):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(exc_type):
                    runner.after_directory_created(tmp, deps, lambda exc_type=exc_type: (_ for _ in ()).throw(exc_type()), {})
                self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())
                self.assertFalse((Path(tmp) / runner.FAILURE_MANIFEST_NAME).exists())

    def test_raw_output_mutation_prevents_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = ("11ACGU\n" * 16).encode("utf-8")
            outputs = []
            plan = runner.build_phase_b_plan(real_config())
            for invocation in plan:
                path = runner.predicted_generation_path(tmp, invocation)
                path.parent.mkdir(parents=True, exist_ok=False)
                path.write_bytes(payload)
                outputs.append(
                    {
                        "path": str(path),
                        "byte_count": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "line_count": 16,
                        "invocation_index": invocation["invocation_index"],
                    }
                )
            context = {"output_dir": tmp, "raw_outputs": outputs, "plan": plan}
            cleaner = synthetic_cleaner()
            deps = runner.RunnerDependencies(read_bytes=lambda path: Path(path).read_bytes(), lstat=os.lstat)

            def expect(mutate):
                mutate()
                with self.assertRaises(runner.PhaseBRunnerError) as caught:
                    runner.verify_retained_raw_outputs(context, deps, cleaner)
                self.assertEqual(caught.exception.code, "raw_output_verification_failed")
                self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())

            original = Path(outputs[0]["path"]).read_bytes()
            expect(lambda: Path(outputs[0]["path"]).write_bytes(original + b"X"))
            Path(outputs[0]["path"]).write_bytes(original)
            expect(lambda: Path(outputs[0]["path"]).unlink())
            Path(outputs[0]["path"]).write_bytes(original)
            expect(lambda: Path(outputs[0]["path"]).write_bytes(b""))
            Path(outputs[0]["path"]).write_bytes(original)
            expect(lambda: Path(outputs[0]["path"]).write_bytes(b"replacement\n"))
            Path(outputs[0]["path"]).write_bytes(original)
            def symlink():
                path = Path(outputs[0]["path"])
                path.unlink()
                path.symlink_to(Path(outputs[1]["path"]).name)
            expect(symlink)
            Path(outputs[0]["path"]).unlink()
            Path(outputs[0]["path"]).write_bytes(original)
            outputs[0]["line_count"] = 15
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.verify_retained_raw_outputs(context, deps, cleaner)
            self.assertEqual(caught.exception.code, "raw_output_verification_failed")
            self.assertIn("line count", caught.exception.detail)

    def test_success_and_failure_manifests_cannot_coexist(self):
        with tempfile.TemporaryDirectory() as tmp:
            success = Path(tmp) / runner.SUCCESS_MANIFEST_NAME
            failure = Path(tmp) / runner.FAILURE_MANIFEST_NAME
            success.write_bytes(b"{}\n")
            deps = runner.RunnerDependencies(
                clock=lambda: "2026-09-30T00:03:00Z",
                hostname=lambda: "synthetic-host",
                write_exclusive=runner.write_exclusive_bytes,
            )
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.record_failure(
                    tmp,
                    runner.PhaseBRunnerError("generation_process_failed", "stopped"),
                    deps,
                    {"config": {}, "snapshot": {}},
                )
            self.assertEqual(caught.exception.code, "success_marker_present")
            self.assertFalse(failure.exists())
            success.unlink()
            failure.write_bytes(b"{}\n")
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.record_failure(
                    tmp,
                    runner.PhaseBRunnerError("generation_process_failed", "stopped"),
                    deps,
                    {"config": {}, "snapshot": {}},
                )
            self.assertEqual(caught.exception.code, "failure_manifest_exists")

    def test_caches_remain_under_the_evidence_directory(self):
        evidence = runner.evidence_directory_for_commit(COMMIT)
        parent = open_environ(1, HF_HUB_OFFLINE="0")
        before = dict(parent)
        child = runner.build_child_environment(parent, evidence, 1, realpath=lambda path: path)
        self.assertEqual(parent, before)
        self.assertEqual(child["CUDA_VISIBLE_DEVICES"], "1")
        self.assertEqual(child["CUDA_DEVICE_ORDER"], "PCI_BUS_ID")
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


class MockedRunTests(unittest.TestCase):
    def test_both_physical_gpus_complete_a_fully_mocked_run(self):
        for physical_gpu in (0, 1):
            with self.subTest(physical_gpu=physical_gpu):
                self.run_gpu(physical_gpu)
        assert_evidence_unchanged("mocked run touched real evidence")
        assert_forbidden_modules_absent("mocked run imported a forbidden module")

    def run_gpu(self, physical_gpu):
        evidence = runner.evidence_directory_for_commit(COMMIT)
        self.assertFalse(Path(evidence).exists())
        config = opened_config(physical_gpu=physical_gpu)
        config_bytes = dumped(config)
        runner_bytes = runner.RUNNER_PATH.read_bytes()
        cleaner_bytes = runner.APPROVED_CLEANER.read_bytes()
        outputs = {}
        write_order = []
        parent = open_environ(physical_gpu, MARKER="keep")

        def read_bytes(path):
            text = str(path)
            if Path(path) == runner.B1_CONFIG_PATH:
                return config_bytes
            if Path(path) == runner.RUNNER_PATH:
                return runner_bytes
            if Path(path) == runner.APPROVED_CLEANER:
                return cleaner_bytes
            if text in outputs:
                return outputs[text]
            raise AssertionError(path)

        def lstat(path):
            text = str(path)
            if text in outputs:
                return FakeStat(stat.S_IFREG, len(outputs[text]))
            if text == evidence or "rnagenesis_generation_output" in text:
                raise FileNotFoundError(text)
            for asset in runner.PINNED_FILES:
                if text == str(asset.absolute_path()):
                    size = asset.size if asset.size is not None else 3
                    return FakeStat(stat.S_IFREG, size)
            raise FileNotFoundError(text)

        def sha256_file(path):
            for asset in runner.PINNED_FILES:
                if str(path) == str(asset.absolute_path()):
                    return asset.sha256
            raise AssertionError(path)

        def gpu_preflight(env, selected):
            self.assertEqual(selected, physical_gpu)
            return runner.preflight_gpu(
                env,
                selected,
                lambda: nvidia_smi_text(selected),
                lambda: json.dumps(probe_payload(selected)),
                resolve_python=lambda path: path,
            )

        def subprocess_run(argv, cwd, env, shell=False):
            self.assertFalse(shell)
            self.assertEqual(env["CUDA_VISIBLE_DEVICES"], str(physical_gpu))
            self.assertEqual(env["CUDA_DEVICE_ORDER"], "PCI_BUS_ID")
            self.assertEqual(parent["MARKER"], "keep")
            mid = argv[argv.index("--mid_folder") + 1]
            remark = argv[argv.index("--remark") + 1]
            predicted = str(
                Path(argv[argv.index("--superfolder") + 1])
                / mid
                / runner.predicted_generation_filename(remark)
            )
            index = int(mid.split("_")[1])
            length = runner.FROZEN_TRAIN_LENGTHS[index]
            if index == 0:
                lines = ["TTTT"] * 16
            else:
                lines = [exact_line(length)] * 16
            outputs[predicted] = ("".join(line + "\n" for line in lines)).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            def write_exclusive(path, data):
                write_order.append(Path(path).name)
                destination = Path(tmp) / Path(path).name
                self.assertFalse(destination.exists())
                destination.write_bytes(data)

            deps = runner.RunnerDependencies(
                read_bytes=read_bytes,
                lstat=lstat,
                realpath=lambda path: str(path),
                sha256_file=sha256_file,
                environ=parent,
                git=repository_git(RUNTIME, COMMIT),
                gpu_preflight=gpu_preflight,
                mkdir=lambda path: self.assertEqual(path, evidence),
                write_exclusive=write_exclusive,
                subprocess_run=subprocess_run,
                load_cleaner=lambda source_bytes=None: synthetic_cleaner(),
                clock=lambda: "2026-09-30T00:04:00Z",
                hostname=lambda: "synthetic-host",
            )
            manifest = runner.run(evidence, str(physical_gpu), deps)
            self.assertEqual(
                write_order,
                [
                    runner.RAW_LEDGER_NAME,
                    runner.AUDITED_LEDGER_NAME,
                    runner.HASH_REPORT_NAME,
                    runner.SUCCESS_MANIFEST_NAME,
                ],
            )
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["phase"], "B")
            self.assertEqual(manifest["selected_physical_gpu"], physical_gpu)
            self.assertEqual(manifest["gpu_identity"]["physical_gpu"], physical_gpu)
            self.assertEqual(manifest["gpu_identity"]["cuda_visible_devices"], str(physical_gpu))
            self.assertEqual(manifest["authorization"]["physical_gpu"], physical_gpu)
            self.assertEqual(manifest["authorization_runtime_commit"], RUNTIME)
            self.assertNotEqual(
                manifest["authorization_runtime_commit"],
                manifest["authorization"]["executing_implementation_commit"],
            )
            self.assertIs(manifest["b1_eligible"], False)
            self.assertIs(manifest["m4_complete"], False)
            self.assertIs(manifest["final_production_mapping_declared"], False)
            self.assertIs(manifest["development_pool_executed"], False)
            self.assertIs(manifest["phase_a_authorisation_accepted_for_phase_b"], False)
            self.assertEqual(manifest["final_raw_output_verification"]["file_count"], 89)
            diagnostics = manifest["sequence_only_diagnostics"]
            self.assertEqual(diagnostics["raw_attempts"], 1424)
            self.assertEqual(diagnostics["parsed_outputs"], 1424)
            self.assertEqual(diagnostics["invalid_outputs"], 16)
            self.assertEqual(diagnostics["valid_outputs"], 1408)
            self.assertEqual(diagnostics["per_length"][0]["exact_hit_rate"], 0.0)
            self.assertEqual(diagnostics["per_length"][0]["invalid_outputs"], 16)
            self.assertEqual(diagnostics["per_length"][0]["eos_marker_observed_count"], 0)
            self.assertEqual(diagnostics["per_length"][0]["early_eos_count"], 0)
            self.assertEqual(diagnostics["per_length"][1]["exact_hits"], 16)
            self.assertEqual(diagnostics["per_length"][1]["eos_marker_observed_count"], 16)
            self.assertEqual(diagnostics["per_length"][1]["early_eos_count"], 0)
            self.assertEqual(diagnostics["eos_marker_observed_count"], 1408)
            self.assertEqual(diagnostics["early_eos_count"], 0)
            self.assertGreaterEqual(diagnostics["lengths_below_provisional_0_50_floor"], 1)
            self.assertIs(diagnostics["provisional_aggregate_0_90_diagnostic_reached"], True)
            self.assertIs(diagnostics["b1_eligible"], False)
            self.assertEqual(diagnostics["b1_eligibility"], "not_declared")
            self.assertIs(diagnostics["final_production_mapping_declared"], False)
            self.assertIs(diagnostics["development_pool_authorised"], False)
            self.assertIs(diagnostics["m4_complete"], False)
            self.assertEqual(diagnostics["eligibility_decision"], "not_made")
            self.assertEqual(len(diagnostics["per_length"]), 89)
            self.assertNotIn("manifest_sha256", json.dumps(manifest))
            raw_rows = [
                json.loads(line)
                for line in (Path(tmp) / runner.RAW_LEDGER_NAME).read_text(encoding="utf-8").splitlines()
            ]
            audited_rows = [
                json.loads(line)
                for line in (Path(tmp) / runner.AUDITED_LEDGER_NAME).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(raw_rows), 1424)
            self.assertEqual(len(audited_rows), 1424)
            self.assertNotEqual(set(raw_rows[0]), set(audited_rows[0]))
            self.assertEqual([row["attempt_index"] for row in audited_rows], list(range(1424)))
            self.assertTrue(all(row["max_seq_len"] == row["requested_biological_length"] + 1 for row in audited_rows))
            self.assertEqual(audited_rows[0]["termination_observation"], "not_observable_from_decoded_text")
            self.assertIs(audited_rows[0]["validity"], False)
            self.assertEqual(audited_rows[16]["termination_observation"], "eos_marker_observed")
            self.assertTrue(audited_rows[16]["raw_decoded_text"].endswith("2"))
            self.assertIs(audited_rows[16]["exact_length"], True)
            self.assertIs(runner.early_eos_event(audited_rows[16]), False)
            self.assertFalse((Path(tmp) / runner.FAILURE_MANIFEST_NAME).exists())
            for key in ("PYTHONPYCACHEPREFIX", "HF_HOME", "TORCH_HOME"):
                self.assertTrue(manifest["child_environment_controls"][key].startswith(evidence + "/"))
        self.assertFalse(Path(evidence).exists())


class InterfaceTests(unittest.TestCase):
    def test_cli_exposes_only_output_dir_physical_gpu_and_help(self):
        parser = runner.build_parser()
        option_strings = []
        for action in parser._actions:
            option_strings.extend(action.option_strings)
        self.assertEqual(set(option_strings), {"--output-dir", "--physical-gpu", "-h", "--help"})
        recorder = RecordingDeps(real_config_bytes(), {})
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = runner.main(["-h"], deps=recorder.build())
        self.assertEqual(code, 0)
        self.assertEqual(recorder.events, [])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = runner.main(["--output-dir", "/tmp/unused", "--seed", "1"], deps=recorder.build())
        self.assertEqual(code, 2)
        self.assertEqual(recorder.events, [])

    def test_runner_source_does_not_import_a_model_stack(self):
        source = (ROOT / "scripts" / "b1_phase_b_runner.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append((node.module or "").split(".")[0])
        for name in imported:
            self.assertNotIn(name, set(FORBIDDEN_RUNTIME_MODULES))
        self.assertNotIn("shell=True", source)
        self.assertIn("shell=False", source)

    def test_repository_rules_allow_a_later_clean_authorisation_commit(self):
        snapshot = runner.assert_phase_b_authorisation(opened_config(), 0)
        provenance = runner.assert_repository_pins(snapshot, repository_git(RUNTIME, COMMIT))
        self.assertEqual(provenance["mres"]["implementation_commit"], COMMIT)
        self.assertEqual(provenance["mres"]["authorization_commit"], RUNTIME)
        self.assertEqual(provenance["mres"]["origin_main"], RUNTIME)
        self.assertEqual(provenance["rnagenesis"]["head"], runner.RNAGENESIS_HEAD)
        self.assertEqual(provenance["rnagenesis"]["branch"], runner.RNAGENESIS_BRANCH)
        self.assertTrue(provenance["mres"]["runner_bytes_match_implementation"])
        cases = (
            ({"mres_status": " M scripts/b1_phase_b_runner.py\n"}, "mres_worktree_dirty"),
            ({"mres_status": "M  scripts/b1_phase_b_runner.py\n"}, "mres_worktree_dirty"),
            ({"mres_status": "?? notes.txt\n"}, "mres_worktree_dirty"),
            ({"origin": "e" * 40}, "mres_origin_main_mismatch"),
            ({"ancestor": "e" * 40}, "mres_implementation_not_ancestor"),
            ({"worktree_blob": "different"}, "runner_bytes_mismatch"),
            ({"rna_status": " M generation.py\n"}, "rnagenesis_worktree_dirty"),
            ({"rna_branch": "main"}, "rnagenesis_branch_mismatch"),
            ({"rna_head": "f" * 40}, "rnagenesis_head_mismatch"),
            ({"rna_status": "?? notes.txt\n"}, "rnagenesis_untracked_refused"),
        )
        for overrides, code in cases:
            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.assert_repository_pins(snapshot, repository_git(RUNTIME, COMMIT, **overrides))
            self.assertEqual(caught.exception.code, code)

    def test_secondary_failure_preserves_the_original_classification(self):
        secret = "ACGUACGUACGUACGU"
        with tempfile.TemporaryDirectory() as tmp:
            def write_exclusive(_path, _data):
                raise OSError(secret)

            deps = runner.RunnerDependencies(
                write_exclusive=write_exclusive,
                clock=lambda: "2026-09-30T00:05:00Z",
                hostname=lambda: "synthetic-host",
            )

            def operation():
                raise runner.PhaseBRunnerError("invocation_output_line_count", secret)

            with self.assertRaises(runner.PhaseBRunnerError) as caught:
                runner.after_directory_created(tmp, deps, operation, {"config": {}, "snapshot": {}})
            self.assertEqual(caught.exception.code, "invocation_output_line_count")
            self.assertEqual(caught.exception.secondary_failure, "failure_manifest_write_failed")
            self.assertNotIn(secret, caught.exception.detail)
            self.assertFalse((Path(tmp) / runner.SUCCESS_MANIFEST_NAME).exists())
            self.assertFalse((Path(tmp) / runner.FAILURE_MANIFEST_NAME).exists())


if __name__ == "__main__":
    unittest.main()

"""CPU/mock tests for the production candidate-generation path of the M7 guardrail stage.

Nothing real is generated. There is no model, GPU, checkpoint weight, TRAIN
corpus, VALIDATION data, REF, EVAL, accepted run directory or RNAGenesis asset.
A synthetic world supplies:

* a 669-value length vector whose real B1 schedule has exactly 1,000 attempts in
  112 invocations (so the production schedule checks run unchanged);
* a fake generator subprocess that writes raw outputs for each invocation;
* tiny checkpoint directories and a sealed replicate manifest in a temporary run
  root outside both repositories;
* fake stat and hash tables for the pinned RNAGenesis assets (never opened).

Only tracked code files are read for real: the approved cleaner, the M4 metrics
module with its configuration, and the MRes implementation files the entry hashes. Every access is recorded, so a test
can show that REF, EVAL, VALIDATION and sibling evidence are never reached.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import json
import os
import random
import shutil
import stat
import subprocess
import sys
import tempfile
import types
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


support = load_module("m7_support_for_generation_tests", SUPPORT_PATH)
guardrails = support.guardrails
contract = support.contract
common = support.common
M7Error = common.M7Error
diag = guardrails.diagnostic()
b1 = diag.b1_runner()
PARENT = "b" * 40
HEAD = "a" * 40
GPU_UUID = "GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f"
PCI = "00000000:61:00.0"
LD_VALUE = "/home/laura/miniconda3/envs/rnagenesis-h200/lib:/usr/local/cuda/lib64"
MSE = {1: 0.9, 2: 0.5, 3: 0.7, 4: 0.6, 5: 0.8}
RANKING = [2, 4, 3, 5, 1]
BIOLOGICAL_PREFIXES = ("/home/laura/rnagenesis-mres-data",)
CODE_FILES = (str(b1.APPROVED_CLEANER),) + tuple(
    os.path.join(ROOT, relative) for relative in guardrails.IMPLEMENTATION_FILE_PATHS
)


def tearDownModule():
    support.cleanup_cache()


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ synthetic accepted inputs

_SYNTHETIC = {}


def synthetic_inputs():
    """The length vector, its real B1 schedule, and a TRAIN text with matching lengths."""
    if not _SYNTHETIC:
        values = [20 + (index % 110) for index in range(669)]
        vector = json.dumps(values, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
        schedule = b1.build_schedule(values, require_source_count=669)
        body = b1.canonical_schedule_bytes(schedule)
        rng = random.Random(7)
        cores, seen = [], set()
        for length in values:
            while True:
                core = "".join(rng.choice("ACGU") for _ in range(length))
                if core not in seen:
                    seen.add(core)
                    cores.append(core)
                    break
        text = ("\n".join(cores) + "\n").encode("utf-8")
        by_length = {}
        for core in cores:
            by_length.setdefault(len(core), []).append(core)
        _SYNTHETIC.update(values=values, vector=vector, schedule=schedule, body=body, cores=cores, text=text, by_length=by_length)
    return _SYNTHETIC


def synthetic_pins():
    inputs = synthetic_inputs()
    pins = diag.production_pins()
    scheduled = pins["schedule"]
    scheduled["length_vector"] = {"name": scheduled["length_vector"]["name"], "sha256": sha(inputs["vector"]), "bytes": len(inputs["vector"])}
    scheduled["schedule"] = {"name": scheduled["schedule"]["name"], "sha256": sha(inputs["body"]), "bytes": len(inputs["body"])}
    scheduled["attempts"] = 1000
    scheduled["invocations"] = 112
    pins["train"].update(sha256=sha(inputs["text"]), bytes=len(inputs["text"]), count=len(inputs["cores"]))
    return pins


def asset_tables():
    m5 = common.m6_contract().m5_contract()
    sizes, hashes = {}, {}
    for relative, expected, size, _role in m5.REQUIRED_MODEL_FILES:
        path = os.path.join(common.RNAGENESIS_ROOT, relative)
        sizes[path], hashes[path] = size, expected
    sizes[m5.DIFFUSERS_PATCH_PATH], hashes[m5.DIFFUSERS_PATCH_PATH] = m5.DIFFUSERS_PATCH_SIZE, m5.DIFFUSERS_PATCH_SHA256
    for relative, expected, _large in b1.MODEL_INPUTS:
        path = os.path.join(common.RNAGENESIS_ROOT, relative)
        hashes[path] = expected
        sizes.setdefault(path, 1)
    return sizes, hashes


def fake_stat(size):
    return types.SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_size=size, st_nlink=1, st_mtime_ns=0, st_ino=1, st_dev=1)


def implementation_hashes():
    result = {}
    for relative in guardrails.IMPLEMENTATION_FILE_PATHS:
        with open(os.path.join(ROOT, relative), "rb") as handle:
            result[relative] = sha(handle.read())
    return result


def slurp(path):
    with open(path, "rb") as handle:
        return handle.read()


def inactive_config():
    with open(guardrails.CONFIG_PATH, "rb") as handle:
        raw = handle.read()
    return raw, common.load_config_bytes(raw)


# ------------------------------------------------------------------ the synthetic world


class World(object):
    """A temporary run root, a sealed replicate manifest, five tiny checkpoints, and a fake generator."""

    def __init__(self, seed=43, ld_library_path=None, mode="clean", ambient_ld_library_path=None):
        self.temp = os.path.realpath(tempfile.mkdtemp(prefix="m7gen"))
        self.run_root = os.path.join(self.temp, "runs")
        os.makedirs(self.run_root)
        self.seed = seed
        self.mode = mode
        self.ld_library_path = ld_library_path
        self.ambient = ambient_ld_library_path if ambient_ld_library_path is not None else ld_library_path
        self.pins = synthetic_pins()
        self.interpreter = dict(support.INTERPRETER)
        inputs = synthetic_inputs()
        self.schedule = inputs["schedule"]
        self.virtual = {
            os.path.join(self.pins["schedule"]["directory"], self.pins["schedule"]["length_vector"]["name"]): inputs["vector"],
            os.path.join(self.pins["schedule"]["directory"], self.pins["schedule"]["schedule"]["name"]): inputs["body"],
            self.pins["train"]["path"]: inputs["text"],
        }
        self.asset_sizes, self.asset_hashes = asset_tables()
        self.fake_dirs = set(["/"])
        for known in list(self.virtual) + list(self.asset_sizes):
            parent = os.path.dirname(known)
            while parent not in self.fake_dirs:
                self.fake_dirs.add(parent)
                parent = os.path.dirname(parent)
        # Ancestors of the temporary run root and of the tracked code files are real directories.
        self.real_dirs = set()
        for known in [self.temp] + list(CODE_FILES):
            parent = os.path.dirname(known)
            while parent != "/" and parent not in self.real_dirs:
                self.real_dirs.add(parent)
                parent = os.path.dirname(parent)
        self.accesses = []
        self.calls = []
        self.written = {}
        self.fail_at = {}
        self.read_hook = None
        self.patcher = None
        try:
            self.replicate_directory = os.path.join(self.run_root, "m7_unit_seed%d_gpu1" % seed)
            os.makedirs(self.replicate_directory)
            self.members = {}
            self.manifest = self.seal_replicate()
            self.manifest_blob = common.canonical_json(self.manifest)
            with open(os.path.join(self.replicate_directory, contract.SUCCESS_MANIFEST_NAME), "wb") as handle:
                handle.write(self.manifest_blob)
            self.impl = implementation_hashes()
            # The synthetic schedule stands in for the accepted one only after the
            # replicate fixtures (which compare the real hash) have been built.
            self.patcher = mock.patch.object(common.m6_contract(), "PAIRED_SCHEDULE_SHA256", self.pins["schedule"]["schedule"]["sha256"])
            self.patcher.start()
            import yaml

            _raw, parent_config = inactive_config()
            for name, section in guardrails.expected_static_sections().items():
                parent_config[name] = section
            self.inactive = parent_config
            self.raw_config = yaml.safe_dump(parent_config, sort_keys=True).encode("utf-8")
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.patcher is not None:
            self.patcher.stop()
            self.patcher = None
        shutil.rmtree(self.temp, ignore_errors=True)

    # -- replicate and checkpoints

    def seal_replicate(self):
        base = support.successful_run(self.seed)["manifest"]
        changed = support.variant(base, mse_by_epoch=MSE)
        for item in changed["checkpoints"]:
            directory = os.path.join(self.replicate_directory, item["directory_name"])
            hashes = {}
            for member in common.CHECKPOINT_MEMBERS:
                target = os.path.join(directory, member)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as handle:
                    handle.write(("seed%d epoch%d %s" % (self.seed, item["epoch"], member)).encode("ascii"))
                hashes[member] = common.stream_sha256(target)
            item["saved_hashes"] = dict(hashes)
            item["weight_sha256"] = hashes[common.WEIGHT_MEMBER]
            self.members[item["epoch"]] = hashes
        contract.validate_replicate_manifest(changed)
        self.commit = changed["authorisation"]["executing_implementation_commit"]
        assert [r["epoch"] for r in changed["validation_ranking"]["ranked_candidates"]] == RANKING
        return changed

    def entry(self, epoch, include_commit=True, ld_library_path="world"):
        ld_value = self.ld_library_path if ld_library_path == "world" else ld_library_path
        position = RANKING.index(epoch) + 1
        preceding = [{"epoch": earlier, "manifest_sha256": digest("failed%d" % earlier), "outcome": "failed"} for earlier in RANKING[: position - 1]]
        name = "m7_unit_seed%d_epoch%d_candidate" % (self.seed, epoch)
        output = os.path.join(self.run_root, name)
        entry = {
            "activation_status": "active_unconsumed",
            "authorisation_id": name,
            "authorisation_timestamp": "2026-10-07T20:00:00+11:00",
            "authorization_parent_commit": self.commit,
            "candidate_epoch": epoch,
            "candidate_seed": self.seed,
            "candidate_update": epoch * 21,
            "checkpoint_directory": os.path.join(self.replicate_directory, contract.checkpoint_child_name(self.seed, epoch, self.commit)),
            "checkpoint_member_sha256": dict(self.members[epoch]),
            "checkpoint_relative_name": contract.checkpoint_child_name(self.seed, epoch, self.commit),
            "checkpoint_weight_sha256": self.members[epoch][common.WEIGHT_MEMBER],
            "consumed": False,
            "cuda_visible_devices": "1",
            "evidence_directory": output,
            "executing_implementation_commit": self.commit,
            "expected_schedule_sha256": self.pins["schedule"]["schedule"]["sha256"],
            "gpu_uuid": GPU_UUID,
            "implementation_config_sha256": sha(self.raw_config),
            "implementation_file_hashes": dict(self.impl),
            "interpreter": dict(self.interpreter),
            "ld_library_path": ld_value,
            "logical_device": "cuda:0",
            "output_directory": output,
            "pci_bus": PCI,
            "permitted_roles": list(guardrails.ACTIVE_ROLES),
            "phase": guardrails.ACTIVE_PHASE,
            "physical_gpu_index": 1,
            "preceding_candidates": preceding,
            "ranking_position": position,
            "replicate_manifest_bytes": len(self.manifest_blob),
            "replicate_manifest_path": os.path.join(self.replicate_directory, contract.SUCCESS_MANIFEST_NAME),
            "replicate_manifest_sha256": sha(self.manifest_blob),
            "reuse_permitted": False,
            "scope": "single_use_m7_d1_candidate_guardrail_seed_%d_epoch_%d" % (self.seed, epoch),
            "session": {"consumption_event": contract.CONSUMPTION_EVENT, "pattern": contract.SESSION_PATTERN, "resume_permitted": False, "wall_clock_expiry": None},
            "single_use": True,
            "validation_ranking_sha256": guardrails.ranking_sha256(self.manifest["validation_ranking"]),
        }
        if include_commit:
            entry["authorization_commit"] = HEAD
        return entry

    # -- injected effects

    def is_real(self, path):
        path = str(path)
        return path == self.temp or path.startswith(self.temp + os.sep) or path in CODE_FILES

    def note(self, kind, path):
        self.accesses.append((kind, str(path)))

    def read_bytes(self, path):
        path = str(path)
        self.note("read", path)
        if self.read_hook is not None:
            self.read_hook(path)
        if path in self.virtual:
            return self.virtual[path]
        if self.is_real(path):
            with open(path, "rb") as handle:
                return handle.read()
        raise AssertionError("unexpected read: " + path)

    def lstat(self, path):
        path = str(path)
        self.note("lstat", path)
        if path in self.virtual:
            return fake_stat(len(self.virtual[path]))
        if path in CODE_FILES:
            return os.lstat(path)
        if path in self.asset_sizes:
            return fake_stat(self.asset_sizes[path])
        if self.is_real(path):
            return os.lstat(path)
        if path in self.real_dirs:
            return os.lstat(path)
        if path in self.fake_dirs:
            return types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_size=4096, st_nlink=2, st_mtime_ns=0, st_ino=2, st_dev=1)
        raise AssertionError("unexpected lstat: " + path)

    def listdir(self, path):
        self.note("listdir", path)
        if self.is_real(path):
            return os.listdir(path)
        raise AssertionError("unexpected listdir: " + str(path))

    def sha256_file(self, path):
        path = str(path)
        self.note("hash", path)
        if path in self.asset_hashes:
            return self.asset_hashes[path]
        if self.is_real(path):
            with open(path, "rb") as handle:
                return sha(handle.read())
        raise AssertionError("unexpected hash: " + path)

    def git(self, repo, args):
        repo, args = str(repo), list(args)
        self.note("git", repo + " " + " ".join(args))
        if repo == common.MRES_ROOT:
            if args == ["rev-parse", "HEAD"]:
                return HEAD + "\n"
            if args == ["rev-parse", "HEAD^@"]:
                return self.commit + "\n"
            if args[:1] == ["status"]:
                return ""
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return "main\n"
            if args == ["rev-parse", "origin/main"]:
                return self.commit + "\n"
            if args[:2] == ["diff", "--name-only"] and args[3:] == ["HEAD"]:
                return guardrails.CONFIG_RELATIVE + "\n"
        elif repo == common.RNAGENESIS_ROOT:
            if args == ["rev-parse", "HEAD"]:
                return common.RNAGENESIS_COMMIT + "\n"
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return common.RNAGENESIS_BRANCH + "\n"
            if args == ["status", "--porcelain=v1"]:
                return common.m6_contract().m5_contract().reviewed_rnagenesis_porcelain()
            if args == ["status", "--porcelain=v1", "--untracked-files=all"]:
                return "?? .cache/huggingface/hub/version.txt\n"
        raise AssertionError("unexpected git call: %r %r" % (repo, args))

    def git_blob(self, spec):
        self.note("git_blob", spec)
        _commit, _, relative = spec.partition(":")
        if relative == guardrails.CONFIG_RELATIVE:
            return self.raw_config
        with open(os.path.join(ROOT, relative), "rb") as handle:
            return handle.read()

    def gpu_preflight(self, parent, physical):
        self.note("gpu", str(physical))
        return {
            "physical_index": physical,
            "uuid": GPU_UUID,
            "pci_bus": PCI,
            "logical_device": "cuda:0",
            "device_type": "cuda",
            "cuda_device_count": 1,
            "cpu_fallback": False,
            "other_gpu_fallback": False,
        }

    def environ(self):
        parent = {"CUDA_VISIBLE_DEVICES": "1", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        if self.ambient is not None:
            parent["LD_LIBRARY_PATH"] = self.ambient
        return parent

    # -- the fake generator

    def raw_lines(self, index, size, target):
        inputs = synthetic_inputs()
        lines = []
        for position in range(size):
            rng = random.Random(index * 1000 + position)
            body = "".join(rng.choice("ACGU") for _ in range(target))
            line = "11" + body
            slot = index * 16 + position
            if self.mode == "mixed":
                if slot % 50 == 0:
                    line = "11XXXX" + body[:5]
                elif slot % 31 == 0:
                    line = "11"
                elif slot % 37 == 0:
                    line = "11" + body[:-3] + "2"
                elif slot % 29 == 0:
                    line = "11" + body[:-2]
                elif slot % 41 == 0 and position > 0:
                    line = lines[-1]
            elif self.mode == "train_copy" and position == 0 and index < 14:
                line = "11" + inputs["by_length"][target][0]
            lines.append(line)
        return lines

    def subprocess_run(self, argv, cwd, env, shell=False):
        self.calls.append({"argv": list(argv), "cwd": cwd, "env": dict(env), "shell": shell})
        index = int(argv[argv.index("--mid_folder") + 1].split("_")[-1])
        fault = self.fail_at.get(index)
        if fault == "interrupt":
            raise KeyboardInterrupt()
        if fault == "raise":
            raise RuntimeError("library said " + support.RNA_MESSAGE)
        if fault == "exit":
            return types.SimpleNamespace(returncode=3)
        size = int(argv[argv.index("--batch_size") + 1])
        target = int(argv[argv.index("--max_seq_len") + 1]) - 1
        lines = self.raw_lines(index, size, target)
        if fault == "excess":
            lines = lines + [lines[0]]
        if fault == "missing":
            lines = lines[:-1] if len(lines) > 1 else []
        self.written[index] = list(lines)
        if fault != "no_output":
            superfolder = argv[argv.index("--superfolder") + 1]
            predicted = b1.predicted_generation_path(
                os.path.dirname(superfolder),
                {"actual_chunk_size": size, "batch_num": 1, "invocation_index": index, "invocation_seed": int(argv[argv.index("--seed") + 1]), "max_seq_len": target + 1},
            )
            with open(str(predicted), "w") as handle:
                handle.write("\n".join(lines) + ("\n" if lines else ""))
        return types.SimpleNamespace(returncode=0)

    def deps(self, **overrides):
        parameters = dict(
            read_bytes=self.read_bytes,
            lstat=self.lstat,
            listdir=self.listdir,
            sha256_file_fn=self.sha256_file,
            environ=self.environ(),
            git=self.git,
            git_blob=self.git_blob,
            gpu_preflight=self.gpu_preflight,
            subprocess_run=self.subprocess_run,
            pins=self.pins,
            fold=lambda sequence: ("." * len(sequence), -1.0),
            nearest=lambda sequence, train: 1.0,
            observe_interpreter=lambda path: dict(self.interpreter),
        )
        parameters.update(overrides)
        return guardrails.CandidateDependencies(**parameters)

    def run(self, epoch, **overrides):
        return guardrails.run_candidate(self.entry(epoch), None, run_root=self.run_root, deps=self.deps(**overrides))

    def active_config(self, epochs):
        config = copy.deepcopy(self.inactive)
        config["document_status"] = guardrails.ACTIVE_DOCUMENT_STATUS
        config["consumable_by_executable_workflow"] = True
        for key in contract.EXECUTION_KEYS:
            config["execution"][key] = True
        for name, section in guardrails.expected_static_sections().items():
            config[name] = section
        config["authorisation_entries"] = [self.entry(epoch, include_commit=False) for epoch in epochs]
        import yaml

        return yaml.safe_dump(config, sort_keys=True).encode("utf-8")

    def launch(self, epoch, epochs=None, **overrides):
        deps = self.deps(**overrides)
        return guardrails.launch_authorised_candidate(
            "m7_unit_seed%d_epoch%d_candidate" % (self.seed, epoch),
            run_root=self.run_root,
            deps=deps,
            config_bytes=self.active_config(epochs or [epoch]),
        )

    def output(self, epoch):
        return os.path.join(self.run_root, "m7_unit_seed%d_epoch%d_candidate" % (self.seed, epoch))

    def failure(self, epoch):
        with open(os.path.join(self.output(epoch), common.FAILURE_RECORD_NAME), "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))

    def audited_rows(self, epoch):
        with open(os.path.join(self.output(epoch), guardrails.AUDITED_LEDGER_NAME), "rb") as handle:
            return [json.loads(line) for line in handle.read().decode("utf-8").splitlines()]

    def raw_rows(self, epoch):
        with open(os.path.join(self.output(epoch), guardrails.RAW_LEDGER_NAME), "rb") as handle:
            return [json.loads(line) for line in handle.read().decode("utf-8").splitlines()]


class WorldCase(unittest.TestCase):
    seed = 43

    def make(self, **keywords):
        world = World(seed=self.seed, **keywords)
        self.addCleanup(world.close)
        return world


# ------------------------------------------------------------------ schedule and invocations


class ScheduleAndInvocationTests(WorldCase):
    def test_the_synthetic_schedule_has_the_accepted_shape(self):
        schedule = synthetic_inputs()["schedule"]
        self.assertEqual((schedule["total_attempts"], schedule["invocation_count"]), (1000, 112))
        self.assertEqual([item["invocation_seed"] for item in schedule["invocations"]], [44000 + index for index in range(112)])

    def test_exactly_112_invocations_and_1000_attempts_in_schedule_order(self):
        world = self.make()
        manifest = world.run(2)
        self.assertEqual(len(world.calls), 112)
        self.assertEqual(manifest["accounting"]["raw_attempts"], 1000)
        self.assertEqual(manifest["accounting"]["invocation_count"], 112)
        invocations = world.schedule["invocations"]
        for call, invocation in zip(world.calls, invocations):
            argv = call["argv"]
            index = invocation["invocation_index"]
            self.assertEqual(argv[argv.index("--mid_folder") + 1], "invocation_%04d" % index)
            self.assertEqual(int(argv[argv.index("--seed") + 1]), 44000 + index)
            self.assertEqual(int(argv[argv.index("--max_seq_len") + 1]), invocation["target_length"] + 1)
            self.assertEqual(int(argv[argv.index("--batch_size") + 1]), invocation["actual_chunk_size"])
            self.assertEqual(argv[argv.index("--dm_file") + 1], world.entry(2)["checkpoint_directory"])
            self.assertEqual((call["cwd"], call["shell"]), (common.RNAGENESIS_ROOT, False))
        requested = [call["argv"][call["argv"].index("--max_seq_len") + 1] for call in world.calls]
        self.assertEqual(requested, [str(item["target_length"] + 1) for item in invocations])
        rows = world.audited_rows(2)
        self.assertEqual([row["original_attempt_index"] for row in rows], list(range(1000)))
        expected = {}
        for invocation in invocations:
            for position, index in enumerate(invocation["original_attempt_indexes"]):
                expected[index] = (invocation["invocation_index"], position, invocation["target_length"], invocation["max_seq_len"], invocation["invocation_seed"])
        for row in rows:
            self.assertEqual(
                (row["invocation_index"], row["batch_position"], row["requested_target_length"], row["max_seq_len"], row["invocation_seed"]),
                expected[row["original_attempt_index"]],
            )

    def test_subprocess_arguments_for_arbitrary_authorised_seed_and_epoch_candidates(self):
        invocation = synthetic_inputs()["schedule"]["invocations"][7]
        for seed in (43, 44):
            for epoch in (1, 2, 3, 4, 5):
                directory = "%s/m7_unit_seed%d_gpu1/%s" % (common.RUN_ROOT, seed, contract.checkpoint_child_name(seed, epoch, PARENT))
                entry = {"checkpoint_directory": directory, "ld_library_path": None, "physical_gpu_index": 1}
                output = os.path.join(tempfile.gettempdir(), "m7_unit_argument_probe_seed%d_epoch%d" % (seed, epoch))
                command = guardrails.build_candidate_command(invocation, output, {"CUDA_VISIBLE_DEVICES": "1", "PATH": "/usr/bin"}, 1, directory, entry)
                reference = b1.build_generation_argv(invocation)
                argv = command["argv"]
                self.assertEqual(argv.count("--dm_file"), 1)
                position = argv.index("--dm_file") + 1
                self.assertEqual(argv[position], directory)
                self.assertIn("seed-%d__epoch-%d__update-%d__" % (seed, epoch, epoch * 21), argv[position])
                restored = list(argv[: len(reference)])
                restored[position] = reference[position]
                self.assertEqual(restored, reference)
                self.assertEqual(argv[len(reference):], ["--superfolder", os.path.join(output, "rnagenesis_generation_output"), "--mid_folder", "invocation_0007"])
                self.assertEqual(argv[0], common.PINNED_PYTHON)
                self.assertEqual((command["cwd"], command["shell"]), (common.RNAGENESIS_ROOT, False))
                self.assertEqual(command["env"]["CUDA_VISIBLE_DEVICES"], "1")
                self.assertNotIn("LD_LIBRARY_PATH", command["env"])
                self.assertEqual([item for item in argv if item.startswith("--") and "ema" in item.lower() and item != "--remark"], [])

    def test_a_checkpoint_other_than_the_authorised_one_is_never_substituted(self):
        invocation = synthetic_inputs()["schedule"]["invocations"][0]
        world = self.make()
        entry = world.entry(2)
        other = world.entry(3)["checkpoint_directory"]
        with self.assertRaises(M7Error) as caught:
            guardrails.build_candidate_command(invocation, world.temp, {"CUDA_VISIBLE_DEVICES": "1"}, 1, other, entry)
        self.assertEqual(caught.exception.code, "authorisation_scope_invalid")

    def test_the_schedule_contract_refuses_any_drift(self):
        world = self.make()
        schedule = world.schedule
        pins = world.pins
        self.assertTrue(guardrails.assert_schedule_contract(schedule, pins))
        for mutate in (
            lambda s: s.update(total_attempts=999),
            lambda s: s.update(invocation_count=111),
            lambda s: s["invocations"].pop(),
            lambda s: s["invocations"][5].update(invocation_seed=1),
            lambda s: s["invocations"][5].update(invocation_index=6),
            lambda s: s["invocations"][5].update(max_seq_len=s["invocations"][5]["target_length"]),
            lambda s: s["invocations"][5].update(batch_num=2),
            lambda s: s["invocations"][5].update(actual_chunk_size=17),
            lambda s: s["invocations"][5].update(expected_batch_positions=[0]),
            lambda s: s["invocations"][5]["original_attempt_indexes"].__setitem__(0, 0),
        ):
            changed = copy.deepcopy(schedule)
            mutate(changed)
            with self.assertRaises(M7Error):
                guardrails.assert_schedule_contract(changed, pins)
        wrong = copy.deepcopy(pins)
        wrong["schedule"]["schedule"]["sha256"] = "0" * 64
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_schedule_contract(schedule, wrong)
        self.assertEqual(caught.exception.code, "identity_mismatch")

    def test_the_accepted_schedule_is_rebuilt_and_matched_byte_for_byte(self):
        world = self.make()
        schedule, body, vector = guardrails.load_accepted_schedule(world.deps())
        self.assertEqual(body, synthetic_inputs()["body"])
        self.assertEqual(vector, synthetic_inputs()["vector"])
        self.assertEqual(schedule["invocation_count"], 112)
        tampered = dict(world.virtual)
        key = os.path.join(world.pins["schedule"]["directory"], world.pins["schedule"]["length_vector"]["name"])
        tampered[key] = tampered[key].replace(b"20,21", b"21,20")
        world.virtual = tampered
        with self.assertRaises(M7Error) as caught:
            guardrails.load_accepted_schedule(world.deps())
        self.assertEqual(caught.exception.code, "schedule_hash_mismatch")


# ------------------------------------------------------------------ ledger and failure handling


class LedgerAndTextTests(WorldCase):
    def test_raw_and_normalised_text_are_retained_together_for_every_attempt(self):
        world = self.make(mode="mixed")
        manifest = world.run(2)
        rows = world.audited_rows(2)
        raw = world.raw_rows(2)
        self.assertEqual((len(rows), len(raw)), (1000, 1000))
        by_index = {}
        for invocation in world.schedule["invocations"]:
            for position, index in enumerate(invocation["original_attempt_indexes"]):
                by_index[index] = world.written[invocation["invocation_index"]][position]
        for row, raw_row in zip(rows, raw):
            text = by_index[row["original_attempt_index"]]
            prefix, body, suffix = diag.independent_normalisation(text)
            self.assertEqual(row["raw_decoded_text"], text)
            self.assertEqual(raw_row["raw_decoded_text"], text)
            self.assertEqual((row["leading_boundary_marker_run"], row["cleaned_sequence"], row["trailing_boundary_marker_run"]), (prefix, body, suffix))
            self.assertEqual(row["raw_length"], len(text))
            self.assertNotIn("cleaned_sequence", raw_row)
        self.assertIn("11", {row["leading_boundary_marker_run"] for row in rows})
        self.assertEqual(manifest["ledgers"]["raw_ledger_sha256"], sha(slurp(os.path.join(world.output(2), guardrails.RAW_LEDGER_NAME))))
        self.assertNotEqual(manifest["ledgers"]["raw_ledger_sha256"], manifest["ledgers"]["audited_ledger_sha256"])

    def test_no_resampling_replacement_or_silent_exclusion(self):
        world = self.make(mode="mixed")
        manifest = world.run(2)
        self.assertEqual(len(world.calls), 112)
        self.assertEqual([call["argv"][call["argv"].index("--mid_folder") + 1] for call in world.calls], ["invocation_%04d" % index for index in range(112)])
        rows = world.audited_rows(2)
        invalid = [row for row in rows if row["validity"] is not True]
        valid = [row for row in rows if row["validity"] is True]
        self.assertGreater(len(invalid), 20)
        self.assertEqual(manifest["accounting"]["valid_outputs"], len(valid))
        self.assertEqual(manifest["accounting"]["raw_attempts"], 1000)
        self.assertGreater(len({row["cleaned_sequence"] for row in valid}), 0)
        self.assertLess(len({row["cleaned_sequence"] for row in valid}), len(valid))
        self.assertGreater(sum(1 for row in rows if row["early_eos"] is True), 0)
        self.assertGreater(sum(1 for row in valid if row["length_delta"] != 0), 0)
        report = manifest["report_only"]
        self.assertEqual(report["requested_length_matching"]["raw_attempts"], 1000)
        self.assertEqual(report["requested_length_matching"]["invalid_attempts"], len(invalid))
        self.assertEqual(report["early_eos_count"], sum(1 for row in rows if row["early_eos"] is True))
        self.assertEqual(report["requested_length_matching"]["exact_hits"], sum(1 for row in rows if row["exact_length_hit"] is True))
        self.assertEqual(report["eligibility_effect"], "none")
        self.assertIs(report["thresholds_defined"], False)
        self.assertIs(manifest["guardrails"]["passed"], False)
        for flag in ("valid_nonempty_acgu_fraction", "empty_or_unparseable_fraction"):
            self.assertIn(flag, manifest["guardrails"]["values"])
        self.assertEqual(manifest["guardrails"]["values"]["valid_nonempty_acgu_fraction"], len(valid) / 1000.0)

    def test_requested_length_early_eos_and_collapse_are_report_only(self):
        world = self.make(mode="mixed")
        manifest = world.run(2)
        failed = {item["id"] for item in manifest["guardrails"]["decisions"] if not item["passed"]}
        self.assertTrue(failed <= {rule[0] for rule in guardrails.HARD_GUARDRAIL_RULES})
        self.assertNotIn("requested_length_exact_hit_rate", {item["id"] for item in manifest["guardrails"]["decisions"]})
        self.assertEqual(len(manifest["guardrails"]["decisions"]), 5)
        clean = self.make(mode="clean")
        passed = clean.run(2)
        self.assertIs(passed["guardrails"]["passed"], True)
        self.assertEqual(passed["report_only"]["early_eos_count"], 0)
        self.assertEqual(passed["report_only"]["gross_length_behaviour"]["valid_attempts_below_half_the_requested_length"], 0)

    def test_the_exact_train_match_guardrail_uses_train_and_only_train(self):
        world = self.make(mode="train_copy")
        manifest = world.run(2)
        values = manifest["guardrails"]["values"]
        self.assertGreater(values["exact_train_match_rate"], 0.01)
        decision = next(item for item in manifest["guardrails"]["decisions"] if item["id"] == "exact_train_match_rate")
        self.assertIs(decision["passed"], False)
        self.assertIs(manifest["guardrails"]["passed"], False)
        train_reads = [path for kind, path in world.accesses if kind == "read" and path == world.pins["train"]["path"]]
        self.assertEqual(len(train_reads), 1)
        self.assertEqual(manifest["input_roles"], list(guardrails.ALLOWED_INPUT_ROLES))
        self.assertEqual(manifest["ref_eval_access"], {"eval_opened": False, "ref_opened": False})

    def test_the_manifest_is_complete_and_carries_no_sequence_text(self):
        world = self.make()
        manifest = world.run(2)
        self.assertTrue(guardrails.validate_candidate_manifest(manifest))
        self.assertEqual(common.canonical_json(manifest), slurp(os.path.join(world.output(2), guardrails.SUCCESS_MANIFEST_NAME)))
        self.assertTrue(common.reject_sequence_text(manifest))
        for key, name in guardrails.LEDGER_FILES.items():
            with open(os.path.join(world.output(2), name), "rb") as handle:
                self.assertEqual(manifest["ledgers"][key], sha(handle.read()), name)
        self.assertEqual(manifest["provenance"], guardrails.provenance_block(world.impl))
        self.assertEqual(manifest["replicate_binding"]["weight_sha256"], world.members[2][common.WEIGHT_MEMBER])
        self.assertEqual(manifest["replicate_binding"]["validation_mse"], world.manifest["validation_ranking"]["ranked_candidates"][0]["aggregate_mse"])
        self.assertEqual((manifest["candidate"]["seed"], manifest["candidate"]["epoch"], manifest["candidate"]["ranking_position"]), (43, 2, 1))
        self.assertEqual(manifest["checkpoint"]["weights_sha256_before_generation"], manifest["checkpoint"]["weights_sha256_after_generation"])
        schedule_copy = os.path.join(world.output(2), guardrails.SCHEDULE_COPY_NAME)
        with open(schedule_copy, "rb") as handle:
            self.assertEqual(handle.read(), synthetic_inputs()["body"])
        self.assertIs(manifest["closure"]["no_selection_claim"], True)

    def test_malformed_missing_duplicate_and_excess_ledger_rows_are_refused(self):
        world = self.make()
        world.run(2)
        rows = [{field: row[field] for field in b1.ATTEMPT_FIELDS} for row in world.audited_rows(2)]
        schedule = world.schedule
        self.assertTrue(guardrails.verify_attempt_ledger([dict(row) for row in rows], schedule))

        def mutate(function):
            changed = [dict(row) for row in rows]
            function(changed)
            return changed

        def drop_field(changed):
            del changed[3]["early_eos"]

        def extra_field(changed):
            changed[3]["selected"] = True

        def reorder_fields(changed):
            row = changed[3]
            changed[3] = {key: row[key] for key in reversed(list(row))}

        def duplicate(changed):
            changed[10] = dict(changed[9])

        def unscheduled(changed):
            changed[4]["original_attempt_index"] = 1000

        def boolean_index(changed):
            changed[0]["original_attempt_index"] = False

        def wrong_seed(changed):
            changed[6]["invocation_seed"] = 1

        def wrong_length(changed):
            changed[6]["requested_target_length"] += 1

        def wrong_text_type(changed):
            changed[8]["raw_decoded_text"] = None

        def wrong_normalisation(changed):
            changed[8]["cleaned_sequence"] = changed[8]["cleaned_sequence"][1:]

        reasons = {
            "drop_field": "malformed",
            "extra_field": "malformed",
            "reorder_fields": "malformed",
            "duplicate": "duplicated",
            "unscheduled": "unscheduled",
            "boolean_index": "unscheduled",
            "wrong_seed": "departs from the accepted schedule",
            "wrong_length": "departs from the accepted schedule",
            "wrong_text_type": "malformed text",
        }
        for function in (drop_field, extra_field, reorder_fields, duplicate, unscheduled, boolean_index, wrong_seed, wrong_length, wrong_text_type, wrong_normalisation):
            with self.assertRaises(M7Error, msg=function.__name__) as caught:
                guardrails.verify_attempt_ledger(mutate(function), schedule)
            self.assertIn(caught.exception.code, ("attempt_ledger_invalid", "unexpected_output_normalization"), function.__name__)
            if function.__name__ in reasons:
                self.assertIn(reasons[function.__name__], caught.exception.detail, function.__name__)
        for changed in (rows[:-1], rows + [dict(rows[0])], [], None, tuple(rows)):
            with self.assertRaises(M7Error) as caught:
                guardrails.verify_attempt_ledger(changed, schedule)
            self.assertEqual(caught.exception.code, "attempt_ledger_invalid")


class InvocationFailureTests(WorldCase):
    def test_a_failed_invocation_records_its_exact_index_and_stage_and_stops(self):
        world = self.make()
        world.fail_at[17] = "exit"
        with self.assertRaises(M7Error) as caught:
            world.run(2)
        self.assertEqual(caught.exception.code, "generation_process_failed")
        record = world.failure(2)
        self.assertEqual(record["code"], "generation_process_failed")
        self.assertEqual(record["stage"], "generation_invocation_spawn")
        self.assertEqual(record["candidate"], {"epoch": 2, "invocation_index": 17, "ranking_position": 1, "seed": 43})
        self.assertEqual((record["seed"], record["entry_kind"], record["resumable"], record["reuse_permitted"]), (43, "candidate", False, False))
        self.assertEqual(len(world.calls), 18)
        self.assertFalse(os.path.exists(os.path.join(world.output(2), guardrails.SUCCESS_MANIFEST_NAME)))
        self.assertFalse(os.path.exists(os.path.join(world.output(2), guardrails.AUDITED_LEDGER_NAME)))

    def test_output_mapping_failures_name_the_invocation_and_the_stage(self):
        for fault, code, stage in (
            ("excess", "output_line_count_mismatch", "generation_invocation_output_mapping"),
            ("missing", "output_line_count_mismatch", "generation_invocation_output_mapping"),
            ("no_output", "filesystem_error", "generation_invocation_output_read"),
        ):
            world = self.make()
            world.fail_at[5] = fault
            with self.assertRaises(M7Error) as caught:
                world.run(2)
            self.assertEqual(caught.exception.code, code, fault)
            record = world.failure(2)
            self.assertEqual((record["code"], record["stage"], record["candidate"]["invocation_index"]), (code, stage, 5), fault)
            self.assertEqual(len(world.calls), 6, fault)

    def test_an_interrupt_during_an_invocation_is_recorded_and_propagates(self):
        world = self.make()
        world.fail_at[3] = "interrupt"
        with self.assertRaises(KeyboardInterrupt):
            world.run(2)
        record = world.failure(2)
        self.assertEqual((record["code"], record["stage"], record["candidate"]["invocation_index"]), ("interrupted", "generation_invocation_spawn", 3))
        self.assertEqual(len(world.calls), 4)

    def test_a_failed_candidate_cannot_be_retried_under_the_same_entry(self):
        world = self.make()
        world.fail_at[0] = "exit"
        with self.assertRaises(M7Error):
            world.run(2)
        before = slurp(os.path.join(world.output(2), common.FAILURE_RECORD_NAME))
        world.fail_at.clear()
        with self.assertRaises(M7Error) as caught:
            world.run(2)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertEqual(slurp(os.path.join(world.output(2), common.FAILURE_RECORD_NAME)), before)

    def test_a_failure_record_never_carries_sequence_text_or_library_messages(self):
        world = self.make()
        world.fail_at[4] = "raise"
        with self.assertRaises(M7Error) as caught:
            world.run(2)
        self.assertEqual(caught.exception.code, "unexpected_runtime_failure")
        record = world.failure(2)
        self.assertEqual((record["code"], record["stage"], record["candidate"]["invocation_index"]), ("unexpected_runtime_failure", "generation_invocation_spawn", 4))
        self.assertIn("RuntimeError", record["detail"])
        self.assertNotIn(support.RNA_MESSAGE, json.dumps(record))
        self.assertNotIn("library said", json.dumps(record))


# ------------------------------------------------------------------ identity and binding before generation


class BindingBeforeGenerationTests(WorldCase):
    def failed_before_generation(self, world, epoch, stage, code):
        with self.assertRaises(M7Error) as caught:
            world.run(epoch)
        self.assertEqual(caught.exception.code, code)
        record = world.failure(epoch)
        self.assertEqual((record["stage"], record["code"]), (stage, code))
        self.assertEqual(world.calls, [])
        self.assertEqual([path for kind, path in world.accesses if path == world.pins["train"]["path"]], [])
        self.assertFalse(os.path.exists(os.path.join(world.output(epoch), guardrails.AUDITED_LEDGER_NAME)))

    def test_a_checkpoint_that_differs_from_the_authorisation_is_refused_before_generation(self):
        world = self.make()
        with open(os.path.join(world.entry(2)["checkpoint_directory"], "unet", "config.json"), "ab") as handle:
            handle.write(b"x")
        self.failed_before_generation(world, 2, "checkpoint_verification_before", "checkpoint_save_reload_incompatibility")

    def test_a_checkpoint_identity_that_differs_from_the_replicate_manifest_is_refused(self):
        world = self.make()
        entry = world.entry(2)
        entry["checkpoint_member_sha256"]["model_index.json"] = digest("other")
        with self.assertRaises(M7Error) as caught:
            guardrails.verify_replicate_binding(entry, world.deps(), world.run_root)
        self.assertEqual(caught.exception.code, "identity_mismatch")
        changed = world.entry(2)
        with open(os.path.join(changed["checkpoint_directory"], "model_index.json"), "ab") as handle:
            handle.write(b"x")
        changed["checkpoint_member_sha256"]["model_index.json"] = common.stream_sha256(os.path.join(changed["checkpoint_directory"], "model_index.json"))
        with self.assertRaises(M7Error) as second:
            guardrails.run_candidate(changed, None, run_root=world.run_root, deps=world.deps())
        self.assertEqual(second.exception.code, "identity_mismatch")
        record = world.failure(2)
        self.assertEqual(record["stage"], "replicate_binding")
        self.assertEqual(world.calls, [])

    def test_a_checkpoint_not_listed_in_the_sealed_replicate_manifest_is_refused(self):
        world = self.make()
        entry = world.entry(2)
        unlisted = os.path.join(world.replicate_directory, contract.checkpoint_child_name(43, 2, "c" * 40))
        entry["checkpoint_directory"] = unlisted
        entry["checkpoint_relative_name"] = os.path.basename(unlisted)
        with self.assertRaises(M7Error) as caught:
            guardrails.verify_replicate_binding(entry, world.deps(), world.run_root)
        self.assertEqual(caught.exception.code, "authorisation_scope_invalid")

    def test_the_replicate_manifest_must_be_the_one_bound_and_intact(self):
        world = self.make()
        entry = world.entry(2)
        entry["replicate_manifest_sha256"] = digest("another manifest")
        with self.assertRaises(M7Error) as caught:
            guardrails.verify_replicate_binding(entry, world.deps(), world.run_root)
        self.assertEqual(caught.exception.code, "authorisation_evidence_mismatch")
        path = os.path.join(world.replicate_directory, contract.SUCCESS_MANIFEST_NAME)
        pristine = slurp(path)
        for payload in (b"not json", pristine.rstrip(b"\n"), json.dumps(json.loads(pristine.decode("utf-8")), indent=1).encode("utf-8")):
            with open(path, "wb") as handle:
                handle.write(payload)
            entry = world.entry(2)
            entry["replicate_manifest_sha256"] = sha(payload)
            with self.assertRaises(M7Error) as caught:
                guardrails.verify_replicate_binding(entry, world.deps(), world.run_root)
            self.assertEqual(caught.exception.code, "authorisation_evidence_mismatch")
        os.remove(path)
        with self.assertRaises(M7Error) as caught:
            guardrails.verify_replicate_binding(world.entry(2), world.deps(), world.run_root)
        self.assertEqual(caught.exception.code, "authorisation_evidence_mismatch")
        os.symlink(os.path.join(world.temp, "elsewhere"), path)
        with self.assertRaises(M7Error):
            guardrails.verify_replicate_binding(world.entry(2), world.deps(), world.run_root)

    def test_a_manifest_that_does_not_validate_is_refused(self):
        world = self.make()
        changed = copy.deepcopy(world.manifest)
        changed["closure"]["ref_opened"] = True
        blob = common.canonical_json(changed)
        with open(os.path.join(world.replicate_directory, contract.SUCCESS_MANIFEST_NAME), "wb") as handle:
            handle.write(blob)
        entry = world.entry(2)
        entry["replicate_manifest_sha256"] = sha(blob)
        with self.assertRaises(M7Error):
            guardrails.verify_replicate_binding(entry, world.deps(), world.run_root)

    def test_a_sibling_replicates_checkpoint_is_refused(self):
        world = self.make()
        sibling = os.path.join(world.run_root, "m7_unit_seed44_gpu1")
        os.makedirs(sibling)
        entry = world.entry(2)
        entry["checkpoint_directory"] = os.path.join(sibling, os.path.basename(entry["checkpoint_directory"]).replace("seed-43", "seed-44"))
        with self.assertRaises(M7Error) as caught:
            guardrails.verify_replicate_binding(entry, world.deps(), world.run_root)
        self.assertEqual(caught.exception.code, "sibling_evidence_access")
        entry = world.entry(2)
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_input_permitted(os.path.join(sibling, "unet", "config.json"), "SEED_EPOCH_CHECKPOINT", entry, world.run_root)
        self.assertEqual(caught.exception.code, "sibling_evidence_access")
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_input_permitted(os.path.join(world.run_root, "m7_unit_seed43_gpu1_other", "x"), "SEED_EPOCH_CHECKPOINT", entry, world.run_root)
        self.assertEqual(caught.exception.code, "sibling_evidence_access")
        self.assertEqual([path for kind, path in world.accesses if sibling in path], [])

    def test_m6_checkpoints_and_evidence_are_refused_before_open(self):
        world = self.make()
        entry = world.entry(2, include_commit=False)
        m6_evidence = common.RUN_ROOT + "/m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6"
        m6_checkpoint = m6_evidence + "/D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-42__update-21__git-" + "6" * 40
        for path in (m6_evidence, m6_checkpoint, m6_checkpoint + "/unet/diffusion_pytorch_model.safetensors", common.RUN_ROOT + "/x/seed-42__update-14__y"):
            with self.assertRaises(M7Error, msg=path) as caught:
                guardrails.assert_input_permitted(path, "SEED_EPOCH_CHECKPOINT", entry, world.run_root, world.deps().realpath)
            self.assertEqual(caught.exception.code, "m6_checkpoint_forbidden", path)
        weight = sorted(common.M6_FORBIDDEN_WEIGHT_SHA256)[0]
        entry["checkpoint_member_sha256"][common.WEIGHT_MEMBER] = weight
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_active_entry(entry, world.run_root)
        self.assertEqual(caught.exception.code, "m6_checkpoint_forbidden")
        self.assertEqual(world.accesses, [])

    def test_an_already_evaluated_or_consumed_candidate_is_refused(self):
        world = self.make()
        entry = world.entry(2)
        self.assertTrue(guardrails.assert_candidate_not_already_evaluated(entry, world.run_root, world.deps()))
        failed_elsewhere = os.path.join(world.run_root, "m7_other_seed43_epoch2_attempt1")
        os.makedirs(failed_elsewhere)
        self.assertTrue(guardrails.assert_candidate_not_already_evaluated(entry, world.run_root, world.deps()))
        with open(os.path.join(failed_elsewhere, guardrails.SUCCESS_MANIFEST_NAME), "wb") as handle:
            handle.write(b"{}\n")
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_candidate_not_already_evaluated(entry, world.run_root, world.deps())
        self.assertEqual(caught.exception.code, "authorization_reuse")
        other_epoch = world.entry(3)
        self.assertTrue(guardrails.assert_candidate_not_already_evaluated(other_epoch, world.run_root, world.deps()))
        consumed = world.entry(4, include_commit=False)
        consumed["consumed"] = True
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_active_entry(consumed, world.run_root)
        self.assertEqual(caught.exception.code, "authorisation_inactive")
        os.makedirs(world.output(5))
        with self.assertRaises(M7Error) as caught:
            world.run(5)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertEqual(os.listdir(world.output(5)), [])

    def test_update_zero_epochs_outside_1_to_5_and_unexpected_seeds_are_refused(self):
        world = self.make()
        for epoch in (0, 6, -1, True, 2.0, "2", None):
            entry = world.entry(2, include_commit=False)
            entry["candidate_epoch"] = epoch
            with self.assertRaises(M7Error, msg=repr(epoch)):
                guardrails.assert_active_entry(entry, world.run_root)
        for seed in (0, 1, 42, 45, True, 43.0, "43"):
            entry = world.entry(2, include_commit=False)
            entry["candidate_seed"] = seed
            with self.assertRaises(M7Error, msg=repr(seed)):
                guardrails.assert_active_entry(entry, world.run_root)
        self.assertEqual(world.calls, [])

    def test_the_default_producer_refuses_a_checkpoint_other_than_the_entrys(self):
        world = self.make()
        entry = world.entry(2)
        os.makedirs(world.output(2))
        with self.assertRaises(M7Error) as caught:
            guardrails.production_generate_and_measure(entry, world.entry(3)["checkpoint_directory"], world.output(2), deps=world.deps(), run_root=world.run_root)
        self.assertEqual(caught.exception.code, "authorisation_scope_invalid")


class LazyPrefixTests(WorldCase):
    def test_every_ranked_entry_binds_exactly_the_prefix_of_the_sealed_ranking(self):
        world = self.make()
        for position, epoch in enumerate(RANKING, start=1):
            entry = world.entry(epoch)
            binding = guardrails.verify_replicate_binding(entry, world.deps(), world.run_root)
            self.assertEqual((binding["epoch"], binding["seed"]), (epoch, 43))
            self.assertEqual(entry["ranking_position"], position)
            self.assertEqual([item["epoch"] for item in entry["preceding_candidates"]], RANKING[: position - 1])
            plan = guardrails.lazy_plan(RANKING, [(earlier, False) for earlier in RANKING[: position - 1]])
            self.assertEqual((plan["state"], plan["next_epoch"]), ("pending", epoch))

    def test_a_non_prefix_or_misranked_entry_is_refused(self):
        world = self.make()
        for epoch, mutate in (
            (3, lambda e: e.update(preceding_candidates=[e["preceding_candidates"][1], e["preceding_candidates"][0]])),
            (3, lambda e: e.update(preceding_candidates=[e["preceding_candidates"][0]])),
            (3, lambda e: e.update(ranking_position=2)),
            (3, lambda e: e.update(preceding_candidates=[{"epoch": 1, "manifest_sha256": digest("x"), "outcome": "failed"}, e["preceding_candidates"][1]])),
            (2, lambda e: e.update(ranking_position=2, preceding_candidates=[{"epoch": 4, "manifest_sha256": digest("x"), "outcome": "failed"}])),
            (5, lambda e: e.update(validation_ranking_sha256=digest("ranking"))),
        ):
            entry = world.entry(epoch)
            mutate(entry)
            with self.assertRaises(M7Error, msg=str(epoch)) as caught:
                guardrails.verify_replicate_binding(entry, world.deps(), world.run_root)
            self.assertIn(caught.exception.code, ("selection_invalid", "authorisation_evidence_mismatch"))
        for evaluated in ([(4, False)], [(2, False), (3, False)], [(2, True), (4, False)]):
            with self.assertRaises(M7Error):
                guardrails.lazy_plan(RANKING, evaluated)

    def test_lazy_evaluation_stops_at_the_first_passing_candidate(self):
        world = self.make()
        first = world.run(2)
        self.assertTrue(first["guardrails"]["passed"])
        plan = guardrails.lazy_plan(RANKING, [(2, first["guardrails"]["passed"])])
        self.assertEqual((plan["state"], plan["selected_epoch"], plan["next_epoch"]), ("passed", 2, None))
        for evaluated in ([(2, True), (4, False)], [(2, True), (4, True)]):
            with self.assertRaises(M7Error):
                guardrails.lazy_plan(RANKING, evaluated)


# ------------------------------------------------------------------ REF/EVAL/VALIDATION denial before any filesystem access


class DenialBeforeOpenTests(WorldCase):
    def test_ref_and_eval_are_refused_by_role_and_by_path_before_any_access(self):
        world = self.make()
        deps = world.deps()
        entry = world.entry(2)
        pins = world.pins
        for role in ("REF", "EVAL"):
            with self.assertRaises(M7Error) as caught:
                guardrails.assert_input_permitted(pins["train"]["path"], role, entry, world.run_root, deps.realpath)
            self.assertEqual(caught.exception.code, "ref_or_eval_access")
        for path in (
            "/home/laura/rnagenesis-mres-data/final/ref.csv",
            "/home/laura/rnagenesis-mres-data/development/EVAL.CSV",
            "/home/laura/rnagenesis-mres-data/Ref/corpus.txt",
            entry["checkpoint_directory"].replace("m7_unit", "REF_unit"),
            entry["checkpoint_directory"] + "/eval/x",
        ):
            for role in ("SEED_EPOCH_CHECKPOINT", "TRAIN_TEXT_DIAGNOSTIC_ONLY", "ACCEPTED_SCHEDULE", "FROZEN_ENCDEC"):
                with self.assertRaises(M7Error, msg=path) as caught:
                    guardrails.assert_input_permitted(path, role, entry, world.run_root, deps.realpath)
                self.assertEqual(caught.exception.code, "ref_or_eval_access", path)
        self.assertEqual(world.accesses, [])

    def test_a_ref_or_eval_train_pin_is_refused_before_train_is_read(self):
        world = self.make()
        for name in ("REF.csv", "eval.csv", "Eval/corpus.txt"):
            pins = copy.deepcopy(world.pins)
            pins["train"]["path"] = "/home/laura/rnagenesis-mres-data/final/" + name
            with self.assertRaises(M7Error) as caught:
                guardrails.open_train_cores(world.deps(pins=pins), synthetic_inputs()["vector"])
            self.assertEqual(caught.exception.code, "ref_or_eval_access", name)
        self.assertEqual(world.accesses, [])

    def test_validation_and_unknown_roles_and_obsolete_paths_are_refused(self):
        world = self.make()
        entry = world.entry(2)
        for role in ("VALIDATION_CSV", "VALIDATION_ARTIFACT"):
            with self.assertRaises(M7Error) as caught:
                guardrails.assert_input_permitted(common.m6_contract().FUTURE_VALIDATION_CSV_PATH, role, entry, world.run_root)
            self.assertEqual(caught.exception.code, "unexpected_biological_path_or_role")
        for role in ("B1_INITIALISATION", "TRAIN_TEXT", "OWN_OUTPUT", "", None):
            with self.assertRaises(M7Error):
                guardrails.assert_input_permitted(entry["checkpoint_directory"], role, entry, world.run_root)
        with self.assertRaises(M7Error):
            guardrails.assert_input_permitted(world.pins["train"]["path"].replace("development", "other"), "TRAIN_TEXT_DIAGNOSTIC_ONLY", entry, world.run_root, pins=world.pins)
        with self.assertRaises(M7Error):
            guardrails.assert_input_permitted(world.pins["schedule"]["directory"] + "_other", "ACCEPTED_SCHEDULE")
        with self.assertRaises(M7Error):
            guardrails.assert_input_permitted("/home/laura/elsewhere/file", "FROZEN_ENCDEC")
        with self.assertRaises(M7Error):
            guardrails.assert_input_permitted(common.RNAGENESIS_ROOT + "/.cache/huggingface/x", "FROZEN_ENCDEC")
        self.assertEqual(world.accesses, [])

    def test_a_full_run_touches_only_permitted_paths_and_opens_train_once_after_consumption(self):
        world = self.make()
        seen_after_consumption = []
        train = world.pins["train"]["path"]
        world.read_hook = lambda path: seen_after_consumption.append(os.path.isdir(world.output(2))) if path == train else None
        world.run(2)
        self.assertEqual(seen_after_consumption, [True])
        touched = [path for _kind, path in world.accesses]
        for path in touched:
            self.assertFalse(common.path_is_ref_or_eval(path), path)
            if path.startswith(BIOLOGICAL_PREFIXES):
                # Only the virtual TRAIN file, and the (fake) metadata of its ancestor directories.
                self.assertTrue(path == train or path in world.fake_dirs, path)
                self.assertNotIn(path, world.real_dirs)
            self.assertNotIn("validation", path.lower().replace("validation_metrics_v1", ""), path)
            self.assertIsNone(common.M6_EVIDENCE_NAME_PATTERN.search(path), path)
            self.assertIsNone(common.M6_CHECKPOINT_NAME_PATTERN.search(path), path)
        sibling = [path for path in touched if path.startswith(world.run_root + os.sep) and not path.startswith(world.output(2)) and not path.startswith(world.replicate_directory)]
        self.assertEqual(sibling, [path for path in sibling if path == world.run_root])
        self.assertEqual(sum(1 for kind, path in world.accesses if kind == "read" and path == train), 1)
        self.assertEqual(world.accesses[0][0] in ("read", "lstat", "listdir", "hash", "git", "git_blob"), True)

    def test_the_denied_role_table_matches_the_active_roles(self):
        self.assertEqual(set(guardrails.DENIED_ROLES) & set(guardrails.ACTIVE_ROLES), set())
        self.assertEqual(set(guardrails.ACTIVE_ROLES), {"ACCEPTED_SCHEDULE", "FROZEN_ENCDEC", "SEED_EPOCH_CHECKPOINT", "TRAIN_TEXT_DIAGNOSTIC_ONLY"})
        self.assertEqual(set(guardrails.ALLOWED_INPUT_ROLES), set(guardrails.ACTIVE_ROLES))


# ------------------------------------------------------------------ LD_LIBRARY_PATH


class LdLibraryPathCandidateTests(WorldCase):
    def test_a_required_matching_value_reaches_every_invocation_and_its_digest_is_recorded(self):
        world = self.make(ld_library_path=LD_VALUE)
        manifest = world.run(2)
        self.assertEqual(len(world.calls), 112)
        for call in world.calls:
            self.assertEqual(call["env"]["LD_LIBRARY_PATH"], LD_VALUE)
            permitted = set(common.ENVIRONMENT_ALLOW_LIST) | set(common.OFFLINE_CONTROLS) | set(common.isolated_paths(world.output(2)))
            permitted |= set(common.FIXED_CHILD_ENVIRONMENT_CONTROLS) | {"LD_LIBRARY_PATH", "PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER"}
            self.assertTrue(set(call["env"]) <= permitted, sorted(set(call["env"]) - permitted))
            self.assertEqual(call["env"]["PATH"], common.FIXED_CHILD_PATH)
        record = manifest["environment"]["ld_library_path"]
        self.assertEqual(record, {"bound": True, "passed_to_child": True, "sha256": common.ld_library_path_digest(LD_VALUE)})
        self.assertNotIn(LD_VALUE, json.dumps(manifest))

    def test_a_missing_or_mismatching_value_is_refused_at_launch_before_consumption(self):
        for ambient in (None, LD_VALUE + ":/extra", "/other/lib", ""):
            world = self.make(ld_library_path=LD_VALUE, ambient_ld_library_path=ambient) if ambient is not None else self.make(ld_library_path=LD_VALUE)
            if ambient is None:
                world.ambient = None
            with self.assertRaises(M7Error, msg=repr(ambient)) as caught:
                world.launch(2)
            self.assertEqual(caught.exception.code, "environment_rejected")
            self.assertNotIn(LD_VALUE, str(caught.exception))
            self.assertFalse(os.path.exists(world.output(2)))
            self.assertEqual(world.calls, [])

    def test_a_value_that_changes_after_launch_fails_the_producer_closed(self):
        world = self.make(ld_library_path=LD_VALUE)
        environment = world.environ()
        entry = world.entry(2)
        os.makedirs(world.output(2))
        environment["LD_LIBRARY_PATH"] = "/changed/lib"
        with self.assertRaises(M7Error) as caught:
            guardrails.production_generate_and_measure(entry, entry["checkpoint_directory"], world.output(2), deps=world.deps(environ=environment), run_root=world.run_root)
        self.assertEqual(caught.exception.code, "environment_rejected")
        self.assertEqual(world.calls, [])

    def test_an_unbound_entry_drops_an_ambient_value(self):
        world = self.make(ld_library_path=None, ambient_ld_library_path=LD_VALUE)
        manifest = world.run(2)
        for call in world.calls:
            self.assertNotIn("LD_LIBRARY_PATH", call["env"])
        self.assertEqual(manifest["environment"]["ld_library_path"], common.unbound_ld_library_path_record())

    def test_the_manifest_record_is_validated(self):
        world = self.make()
        manifest = world.run(2)
        for mutate in (
            lambda m: m["environment"].update(ld_library_path={"bound": True, "passed_to_child": True, "sha256": None}),
            lambda m: m["environment"].update(extra=1),
            lambda m: m.pop("environment"),
        ):
            changed = copy.deepcopy(manifest)
            mutate(changed)
            with self.assertRaises(M7Error):
                guardrails.validate_candidate_manifest(changed)


# ------------------------------------------------------------------ production wiring and the inactive gate


class ProductionWiringTests(WorldCase):
    def test_the_default_callable_is_the_production_callable_and_needs_no_injection(self):
        self.assertIsNone(inspect.signature(guardrails.run_candidate).parameters["generate_and_measure"].default)
        self.assertTrue(callable(guardrails.production_generate_and_measure))
        self.assertTrue(callable(guardrails.launch_authorised_candidate))
        world = self.make()
        manifest = world.run(2)
        self.assertEqual(len(world.calls), 112)
        self.assertTrue(guardrails.validate_candidate_manifest(manifest))
        source = inspect.getsource(guardrails.run_candidate)
        self.assertIn("production_generate_and_measure", source)

    def test_an_authorised_launch_runs_the_real_defaults_with_only_io_mocks(self):
        world = self.make(ld_library_path=LD_VALUE)
        manifest = world.launch(2)
        self.assertEqual(manifest["authorisation"]["authorization_commit"], HEAD)
        self.assertEqual(manifest["authorisation"]["authorisation_id"], "m7_unit_seed43_epoch2_candidate")
        self.assertEqual(len(world.calls), 112)
        kinds = {kind for kind, _path in world.accesses}
        self.assertTrue({"git", "git_blob", "gpu", "listdir"} <= kinds)
        self.assertTrue(os.path.isfile(os.path.join(world.output(2), guardrails.SUCCESS_MANIFEST_NAME)))
        with self.assertRaises(M7Error) as caught:
            world.launch(2)
        self.assertEqual(caught.exception.code, "authorization_reuse")

    def test_a_launch_selects_one_entry_and_leaves_the_others_alone(self):
        world = self.make()
        world.launch(4, epochs=[2, 4])
        self.assertTrue(os.path.isdir(world.output(4)))
        self.assertFalse(os.path.exists(world.output(2)))
        with self.assertRaises(M7Error):
            world.launch(3, epochs=[2, 4])
        self.assertFalse(os.path.exists(world.output(3)))

    def test_launch_refusals_before_consumption_create_nothing(self):
        world = self.make()
        for overrides, code in (
            ({"gpu_preflight": lambda parent, physical: dict(world.gpu_preflight(parent, physical), uuid="GPU-00000000-0000-0000-0000-000000000000")}, "unauthorized_gpu"),
            ({"environ": dict(world.environ(), CUDA_VISIBLE_DEVICES="0")}, "environment_rejected"),
            ({"environ": {key: value for key, value in world.environ().items() if key != "CUDA_DEVICE_ORDER"}}, "cuda_environment_invalid"),
            ({"environ": dict(world.environ(), PYTHONPATH="/x")}, "environment_rejected"),
            ({"environ": dict(world.environ(), HF_TOKEN="x")}, "environment_rejected"),
        ):
            with self.assertRaises(M7Error, msg=code) as caught:
                world.launch(2, **overrides)
            self.assertEqual(caught.exception.code, code)
            self.assertFalse(os.path.exists(world.output(2)))
        self.assertEqual(world.calls, [])

    def test_repository_binding_failures_are_refused_before_consumption(self):
        world = self.make()
        original_git = world.git

        def dirty(repo, args):
            if repo == common.MRES_ROOT and args[:1] == ["status"]:
                return " M scripts/modelling/m7_common.py\n"
            return original_git(repo, args)

        def other_parent(repo, args):
            if repo == common.MRES_ROOT and args == ["rev-parse", "HEAD^@"]:
                return "d" * 40 + "\n"
            return original_git(repo, args)

        def drifted_rnagenesis(repo, args):
            if repo == common.RNAGENESIS_ROOT and args == ["rev-parse", "HEAD"]:
                return "e" * 40 + "\n"
            return original_git(repo, args)

        def extra_file(repo, args):
            if repo == common.MRES_ROOT and args[:2] == ["diff", "--name-only"]:
                return guardrails.CONFIG_RELATIVE + "\nscripts/modelling/m7_common.py\n"
            return original_git(repo, args)

        for git in (dirty, other_parent, drifted_rnagenesis, extra_file):
            with self.assertRaises(M7Error, msg=git.__name__):
                world.launch(2, git=git)
            self.assertFalse(os.path.exists(world.output(2)))
        original_blob = world.git_blob

        def drifted_file(spec):
            if spec.endswith("m7_common.py"):
                return b"drifted"
            return original_blob(spec)

        with self.assertRaises(M7Error) as caught:
            world.launch(2, git_blob=drifted_file)
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        self.assertFalse(os.path.exists(world.output(2)))

    def test_an_already_evaluated_candidate_is_refused_at_launch(self):
        world = self.make()
        elsewhere = os.path.join(world.run_root, "m7_earlier_seed43_epoch2_attempt")
        os.makedirs(elsewhere)
        with open(os.path.join(elsewhere, guardrails.SUCCESS_MANIFEST_NAME), "wb") as handle:
            handle.write(b"{}\n")
        with self.assertRaises(M7Error) as caught:
            world.launch(2)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertFalse(os.path.exists(world.output(2)))

    def test_the_inactive_configuration_still_refuses_launch_with_the_real_defaults(self):
        with open(guardrails.CONFIG_PATH, "rb") as handle:
            raw = handle.read()
        accesses = []

        def spy(name):
            def wrapped(*arguments, **keywords):
                accesses.append((name, arguments))
                raise AssertionError("the inactive gate must not reach " + name)

            return wrapped

        deps = guardrails.CandidateDependencies(
            lstat=spy("lstat"), listdir=spy("listdir"), sha256_file_fn=spy("sha256_file"), git=spy("git"), git_blob=spy("git_blob"),
            gpu_preflight=spy("gpu"), mkdir=spy("mkdir"), subprocess_run=spy("subprocess"), write_bytes=spy("write"), environ={},
        )
        for identifier in ("m7_unit_seed43_epoch2_candidate", "m7_unit_seed44_epoch5_candidate"):
            with self.assertRaises(M7Error) as caught:
                guardrails.launch_authorised_candidate(identifier, deps=deps, config_bytes=raw)
            self.assertEqual(caught.exception.code, "execution_not_authorised")
        with self.assertRaises(M7Error) as caught:
            guardrails.launch_authorised_candidate("m7_unit_seed43_epoch2_candidate")
        self.assertEqual(caught.exception.code, "execution_not_authorised")
        for bad in ("", "m7_seed42_epoch1_x", "m7_seed43_epoch0_x", "m7_seed43_epoch6_x", None, 7):
            with self.assertRaises(M7Error) as caught:
                guardrails.launch_authorised_candidate(bad, deps=deps, config_bytes=raw)
            self.assertEqual(caught.exception.code, "cli_argument_rejected")
        self.assertEqual(accesses, [])

    def test_the_command_line_accepts_an_authorisation_id_and_refuses_it_while_inactive(self):
        path = os.path.join(ROOT, "scripts/modelling/m7_candidate_guardrails.py")
        for arguments, code in (
            (["--authorisation-id", "m7_unit_seed43_epoch2_candidate"], 2),
            (["--authorisation-id", "m7_unit_seed43_epoch2_candidate", "--seed", "43"], 2),
            (["--authorisation-id"], 2),
            (["--checkpoint", "/x"], 2),
            (["--help"], 0),
            (["--schema"], 0),
        ):
            completed = subprocess.run([sys.executable, "-B", path] + arguments, capture_output=True, text=True, cwd="/tmp")
            self.assertEqual(completed.returncode, code, arguments)
        refused = subprocess.run([sys.executable, "-B", path, "--authorisation-id", "m7_unit_seed43_epoch2_candidate"], capture_output=True, text=True, cwd="/tmp")
        self.assertIn("execution_not_authorised", refused.stderr)

    def test_the_inactive_files_stay_inactive_and_unbound(self):
        for name in ("D1_candidate_guardrails.yaml", "D1_final_replicates.yaml", "D1_final_selection.yaml"):
            with open(os.path.join(ROOT, "config/experiments", name), "rb") as handle:
                text = handle.read().decode("utf-8")
            config = common.load_config_bytes(text.encode("utf-8"))
            self.assertEqual(config["document_status"], "M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED", name)
            self.assertIs(config["consumable_by_executable_workflow"], False, name)
            self.assertEqual(config.get("authorisation_entries", []), [], name)
            for token in ("GPU-", "ld_library_path:", "output_directory:", "evidence_directory:", "authorization_commit:", "gpu_uuid:", "authorisation_timestamp:"):
                self.assertNotIn(token, text, (name, token))
            self.assertIs(config.get("execution", {}).get("gpu_identity_bound", False), False, name)
        guardrails_config = inactive_config()[1]
        self.assertTrue(guardrails.assert_inactive_configuration(guardrails_config))
        self.assertIs(guardrails_config["diagnostic_design"]["production_generation_callable_implemented_in_this_package"], True)


if __name__ == "__main__":
    unittest.main()

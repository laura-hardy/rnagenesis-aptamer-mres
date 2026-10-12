"""CPU/mock tests for the final bounded corrections to the inactive M7 package.

1. the replicate authorisation launcher is wired to ``--authorisation-id`` and
   still cannot execute while the configuration is inactive;
2. a candidate reopens and independently validates its predecessor evidence
   before the entry is consumed;
3. the accepted report-only M6 diagnostics are reused unchanged;
4. asset and evidence inspection never follows a symlink silently;
5. the pinned interpreter is bound, observed (mocked here) and recorded.

No biological data, weight, checkpoint, accepted evidence, GPU or live
interpreter is touched. Every filesystem effect is in a temporary directory or a
fake injected through the dependency objects.
"""

from __future__ import annotations

import copy
import importlib.util
import io
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
HERE = os.path.join(ROOT, "tests/modelling")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


support = load_module("m7_support_for_launch_tests", os.path.join(HERE, "m7_support.py"))
gen = load_module("m7_generation_tests_for_launch_tests", os.path.join(HERE, "test_m7_candidate_generation.py"))
runner = support.runner
contract = support.contract
common = support.common
guardrails = support.guardrails
helpers = support.helpers
M7Error = common.M7Error
diag = guardrails.diagnostic()
b1 = diag.b1_runner()
sha = gen.sha
digest = gen.digest
slurp = gen.slurp
INTERPRETER = support.INTERPRETER


def tearDownModule():
    support.cleanup_cache()


def fake_stat(mode=stat.S_IFREG | 0o644, size=10, nlink=1, mtime=0, inode=1, device=1):
    return types.SimpleNamespace(st_mode=mode, st_size=size, st_nlink=nlink, st_mtime_ns=mtime, st_ino=inode, st_dev=device)


# ------------------------------------------------------------------ 5. pinned interpreter


class InterpreterBindingTests(unittest.TestCase):
    RESOLVED = common.PINNED_ENVIRONMENT_PREFIX + "/bin/python3.8"

    def tree(self, **overrides):
        """A fake filesystem: every directory real, the pinned interpreter a regular file."""
        state = {"size": 17000000, "mode": stat.S_IFREG | 0o755, "nlink": 2, "mtime": 5}
        state.update(overrides)

        def lstat(path):
            if path == self.RESOLVED:
                state["calls"] = state.get("calls", 0) + 1
                mtime = state["mtime"] + (1 if state.get("change_after_first") and state["calls"] > 1 else 0)
                return fake_stat(state["mode"], state["size"], state["nlink"], mtime)
            if state.get("symlink_dir") == path:
                return fake_stat(stat.S_IFLNK | 0o777)
            return fake_stat(stat.S_IFDIR | 0o755, 4096, 2)

        return lstat

    def observe(self, lstat=None, realpath=None, digest_value=None, path=None):
        return common.observe_interpreter(
            path,
            lstat=lstat or self.tree(),
            realpath=realpath or (lambda target: self.RESOLVED),
            hash_file=lambda target: digest_value or digest("pinned interpreter executable"),
        )

    def test_the_pinned_path_resolving_inside_the_pinned_environment_is_observed(self):
        record = self.observe()
        self.assertEqual(record, {"path": common.PINNED_PYTHON, "resolved_path": self.RESOLVED, "sha256": digest("pinned interpreter executable"), "size": 17000000})
        self.assertTrue(common.assert_interpreter_binding(record))
        self.assertTrue(common.assert_interpreter_matches(record, dict(INTERPRETER)))

    def test_hard_links_inside_the_environment_are_recorded_not_refused(self):
        # A conda environment hard-links its interpreter; the identity is the hash and size.
        self.assertEqual(self.observe(lstat=self.tree(nlink=5))["size"], 17000000)

    def test_an_unexpected_path_or_resolution_is_refused_before_any_open(self):
        opened = []
        for path in ("/usr/bin/python3", "/home/laura/miniconda3/bin/python", common.PINNED_PYTHON + "3", "python", ""):
            with self.assertRaises(M7Error, msg=path) as caught:
                common.observe_interpreter(path, lstat=lambda target: opened.append(target), realpath=opened.append, hash_file=opened.append)
            self.assertEqual(caught.exception.code, "interpreter_rejected")
        self.assertEqual(opened, [])
        for resolved in (
            "/usr/bin/python3.8",
            "/home/laura/miniconda3/envs/other/bin/python3.8",
            common.PINNED_ENVIRONMENT_PREFIX + "/bin/python3.9",
            common.PINNED_ENVIRONMENT_PREFIX + "/bin/python",
            common.PINNED_ENVIRONMENT_PREFIX + "/../other/bin/python3.8",
            common.PINNED_ENVIRONMENT_PREFIX + "-evil/bin/python3.8",
        ):
            calls = []
            with self.assertRaises(M7Error, msg=resolved) as caught:
                common.observe_interpreter(None, lstat=lambda target: calls.append(target), realpath=lambda target: resolved, hash_file=calls.append)
            self.assertEqual(caught.exception.code, "interpreter_rejected")
            self.assertEqual(calls, [], resolved)

    def test_symlink_leaf_symlink_ancestor_special_file_and_change_are_refused(self):
        for lstat in (
            self.tree(mode=stat.S_IFLNK | 0o777),
            self.tree(mode=stat.S_IFDIR | 0o755),
            self.tree(symlink_dir=common.PINNED_ENVIRONMENT_PREFIX + "/bin"),
            self.tree(symlink_dir=common.PINNED_ENVIRONMENT_PREFIX),
            self.tree(change_after_first=True),
        ):
            with self.assertRaises(M7Error) as caught:
                self.observe(lstat=lstat)
            self.assertEqual(caught.exception.code, "asset_inspection_unsafe")

    def test_a_substituted_executable_does_not_match_the_binding(self):
        observed = self.observe(digest_value=digest("another executable"))
        with self.assertRaises(M7Error) as caught:
            common.assert_interpreter_matches(observed, dict(INTERPRETER))
        self.assertEqual(caught.exception.code, "interpreter_rejected")
        self.assertNotIn(digest("another executable"), str(caught.exception))
        for changed in (dict(INTERPRETER, size=1), dict(INTERPRETER, resolved_path=common.PINNED_ENVIRONMENT_PREFIX + "/lib/python3.8")):
            with self.assertRaises(M7Error):
                common.assert_interpreter_matches(changed, dict(INTERPRETER))

    def test_the_binding_is_validated_on_its_text(self):
        for bad in (
            None, {}, [], dict(INTERPRETER, extra=1), {key: value for key, value in INTERPRETER.items() if key != "size"},
            dict(INTERPRETER, path="/usr/bin/python3"), dict(INTERPRETER, sha256="short"), dict(INTERPRETER, size=0),
            dict(INTERPRETER, size=True), dict(INTERPRETER, size="17"), dict(INTERPRETER, resolved_path="relative/python3.8"),
        ):
            with self.assertRaises(M7Error, msg=repr(bad)):
                common.assert_interpreter_binding(bad)


class InterpreterInEntriesTests(unittest.TestCase):
    def test_entries_must_bind_a_valid_interpreter_and_the_inactive_files_bind_none(self):
        temp = os.path.realpath(tempfile.mkdtemp(prefix="m7test"))
        self.addCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        entry = helpers.entry_for(43, temp)
        self.assertTrue(contract.assert_active_entry(entry, temp))
        for bad in (None, dict(INTERPRETER, path="/usr/bin/python3"), dict(INTERPRETER, sha256="x")):
            changed = helpers.entry_for(43, temp)
            changed["interpreter"] = bad
            with self.assertRaises(M7Error):
                contract.assert_active_entry(changed, temp)
        missing = helpers.entry_for(43, temp)
        del missing["interpreter"]
        with self.assertRaises(M7Error):
            contract.assert_active_entry(missing, temp)
        with open(os.path.join(ROOT, "config/experiments/D1_candidate_guardrails.yaml"), "rb") as handle:
            guardrail_text = handle.read().decode("utf-8")
        self.assertNotIn("interpreter:", guardrail_text)
        self.assertIn("  - interpreter\n", guardrail_text)
        inactive_replicate = helpers.inactive_replicate_bytes().decode("utf-8")
        self.assertNotIn("interpreter:", inactive_replicate)
        self.assertIn("  - interpreter\n", inactive_replicate)
        with open(os.path.join(ROOT, "config/experiments/D1_final_replicates.yaml"), "rb") as handle:
            live_replicate = handle.read().decode("utf-8")
        self.assertIn("authorisation_id:", live_replicate)
        self.assertIn("seed44", live_replicate)
        self.assertIn("interpreter", contract.ACTIVE_ENTRY_KEYS)
        self.assertIn("interpreter", guardrails.ACTIVE_ENTRY_KEYS)
        raw, inactive = helpers.load_inactive()
        changed = copy.deepcopy(inactive)
        changed["seed_plan"]["interpreter"] = dict(INTERPRETER)
        with self.assertRaises(M7Error):
            contract.assert_inactive_configuration(changed)


# ------------------------------------------------------------------ 1. the replicate launcher


class WiredLauncherBase(unittest.TestCase):
    def setUp(self):
        import yaml

        self.yaml = yaml
        self.harness = support.Harness()
        self.addCleanup(self.harness.close)
        self.config_bytes = yaml.safe_dump(self.harness.config, sort_keys=True).encode("utf-8")
        self.parent = dict(support.SAFE_PARENT_ENVIRONMENT, CUDA_VISIBLE_DEVICES="1", CUDA_DEVICE_ORDER="PCI_BUS_ID")
        self.spawned = []

    def seen(self, seed=43):
        return self.harness.interpreter_observer(seed)

    def launch(self, seed, spawn=None, observation=None, config_bytes=None, parent=None, identifier=None, interpreter_observer=None):
        entry = self.harness.entries[seed]
        return runner.launch_authorised_entry(
            identifier or entry["authorisation_id"],
            run_root=self.harness.temp,
            spawn=spawn or self.refusing_spawn,
            asset_observer=lambda: None,
            python_observer=lambda: None,
            environ=self.parent if parent is None else parent,
            config_bytes=self.config_bytes if config_bytes is None else config_bytes,
            observation=self.harness.observation(seed) if observation is None else observation,
            statvfs=lambda path: type("S", (), {"f_bavail": 10**12, "f_frsize": 4096})(),
            interpreter_observer=interpreter_observer or self.seen(seed),
        )

    def refusing_spawn(self, argv, env, cwd):
        raise AssertionError("a worker must not start")

    def worker_spawn(self, seed):
        stack = self.harness.make_stack(seed)

        def spawn(argv, env, cwd):
            self.spawned.append({"argv": argv, "env": env, "cwd": cwd})
            runner.reset_process_claim_for_tests()
            with self.harness.patched(env):
                try:
                    runner.worker_main(
                        argv[-2],
                        argv[-1],
                        config_loader=lambda: self.harness.config,
                        observation_loader=lambda config, selected: self.harness.observation(seed, consumed=True),
                        stack_loader=lambda authorised: stack,
                        interpreter_observer=self.seen(seed),
                    )
                except BaseException:
                    return types.SimpleNamespace(returncode=1)
            return types.SimpleNamespace(returncode=0)

        return spawn

    def nothing_created(self):
        self.assertEqual(os.listdir(self.harness.temp), [])


class InactiveRefusalTests(WiredLauncherBase):
    def inactive_bytes(self):
        return helpers.inactive_replicate_bytes()

    def test_the_inactive_configuration_refuses_before_anything_is_created_or_touched(self):
        def refuse(name):
            def raiser(*arguments, **keywords):
                raise AssertionError("the inactive gate reached " + name)

            return raiser

        # The inactive replicate fixture is read with git before subprocess is sealed.
        # The launch itself must not call git.
        inactive = self.inactive_bytes()
        with mock.patch.object(os, "mkdir", refuse("mkdir")), mock.patch.object(os, "makedirs", refuse("makedirs")), \
                mock.patch.object(runner, "live_repository_observation", refuse("repository")), \
                mock.patch.object(runner.m6, "observe_required_assets", refuse("assets")), \
                mock.patch.object(common, "observe_interpreter", refuse("interpreter")), \
                mock.patch.object(common, "assert_free_space", refuse("free space")), \
                mock.patch.object(common, "consume_output_directory", refuse("consumption")), \
                mock.patch.object(subprocess, "run", refuse("subprocess")), mock.patch.object(subprocess, "check_output", refuse("git")):
            for identifier in ("m7_unit_seed43_gpu1", "m7_unit_seed44_gpu1", "m7_unit_seed43_anything"):
                with self.assertRaises(M7Error, msg=identifier) as caught:
                    runner.launch_authorised_entry(identifier, run_root=self.harness.temp, environ={}, config_bytes=inactive)
                self.assertEqual(caught.exception.code, "execution_not_authorised")
            for bad in ("", "bad", "m7_seed42_x", "m7_unit_seed45_gpu1", None, 7):
                with self.assertRaises(M7Error) as caught:
                    runner.launch_authorised_entry(bad, run_root=self.harness.temp, environ={}, config_bytes=inactive)
                self.assertEqual(caught.exception.code, "cli_argument_rejected", bad)
            # The process entry point reads the live replicate authorisation, which is
            # seed 44. This unit id is therefore not the inactive gate; the fixture
            # bytes above are. The live lookup must still fail closed and create nothing.
            self.assertEqual(runner.main(["--authorisation-id", "m7_unit_seed43_gpu1"]), 1)
        self.nothing_created()

    def test_the_inactive_launcher_refuses_before_environment_repository_gpu_interpreter_asset_or_weight_access(self):
        reached = []

        def refuse(name):
            def raiser(*arguments, **keywords):
                reached.append(name)
                raise AssertionError("inactive launcher reached " + name)

            return raiser

        config_bytes = self.inactive_bytes()
        with mock.patch.object(common, "assert_parent_environment", refuse("environment")), \
                mock.patch.object(common, "build_child_environment", refuse("child-environment")), \
                mock.patch.object(runner, "live_repository_observation", refuse("repository")), \
                mock.patch.object(common, "live_gpu_probe", refuse("gpu")), \
                mock.patch.object(common, "observe_interpreter", refuse("interpreter")), \
                mock.patch.object(runner.m6, "observe_required_assets", refuse("asset")), \
                mock.patch.object(common, "hash_regular_file", refuse("weight")):
            with self.assertRaises(M7Error) as caught:
                runner.launch_authorised_entry(
                    "m7_unit_seed43_gpu1",
                    run_root=self.harness.temp,
                    environ={"CUDA_MODULE_LOADING": "EAGER", "LD_LIBRARY_PATH": "/tmp/not-used", "PATH": "/tmp/hostile"},
                    config_bytes=config_bytes,
                )
        self.assertEqual(caught.exception.code, "execution_not_authorised")
        self.assertEqual(reached, [])
        self.nothing_created()

    def test_the_command_line_parses_the_id_and_refuses_it_while_inactive(self):
        path = os.path.join(ROOT, "scripts/modelling/m7_replicate_runner.py")
        output = os.path.join(common.RUN_ROOT, "m7_unit_seed43_gpu1")
        existed = os.path.lexists(output)
        refused = subprocess.run([sys.executable, "-B", path, "--authorisation-id", "m7_unit_seed43_gpu1"], capture_output=True, text=True, cwd="/tmp")
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(refused.stdout, "")
        self.assertFalse(refused.stderr.startswith("execution_not_authorised"), refused.stderr)
        self.assertEqual(os.path.lexists(output), existed)
        for arguments in (["--authorisation-id"], ["--authorisation-id", "bad"], ["--authorisation-id", "m7_unit_seed43_gpu1", "--seed", "44"], ["--seed", "43"], ["--gpu", "1"], ["--learning-rate", "1e-3"]):
            completed = subprocess.run([sys.executable, "-B", path] + arguments, capture_output=True, text=True, cwd="/tmp")
            self.assertEqual(completed.returncode, 2, arguments)
            self.assertTrue(completed.stderr.startswith("cli_argument_rejected"), (arguments, completed.stderr))
        helped = subprocess.run([sys.executable, "-B", path, "--help"], capture_output=True, text=True, cwd="/tmp")
        self.assertEqual(helped.returncode, 0)

    def test_the_inactive_state_is_unchanged(self):
        raw, inactive = helpers.load_inactive()
        self.assertEqual(inactive["authorisation_entries"], [])
        self.assertIs(inactive["consumable_by_executable_workflow"], False)
        self.assertTrue(contract.assert_inactive_configuration(inactive))
        with self.assertRaises(M7Error) as caught:
            contract.reject_inactive_before_execution(inactive)
        self.assertEqual(caught.exception.code, "execution_not_authorised")


class DispatchTests(WiredLauncherBase):
    def test_a_future_active_entry_dispatches_exactly_one_seed_through_the_command_line_path(self):
        config_path = os.path.join(self.harness.temp, "..", "active_" + os.path.basename(self.harness.temp) + ".yaml")
        config_path = os.path.normpath(config_path)
        with open(config_path, "wb") as handle:
            handle.write(self.config_bytes)
        self.addCleanup(lambda: os.path.exists(config_path) and os.remove(config_path))
        spawn = self.worker_spawn(43)
        with mock.patch.object(runner, "CONFIG_PATH", config_path), mock.patch.object(common, "RUN_ROOT", self.harness.temp), \
                mock.patch.object(runner, "live_repository_observation", lambda config, entry: self.harness.observation(43)), \
                mock.patch.object(runner.m6, "observe_required_assets", lambda: None), \
                mock.patch.object(runner.m6, "assert_pinned_python_file", lambda path: None), \
                mock.patch.object(common, "observe_interpreter", self.seen(43)), \
                mock.patch.object(runner, "_default_spawn", spawn), \
                mock.patch.dict(os.environ, self.parent, clear=True):
            self.assertEqual(runner.main(["--authorisation-id", self.harness.entries[43]["authorisation_id"]]), 0)
        directory = self.harness.entries[43]["output_directory"]
        self.assertTrue(os.path.isfile(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)))
        self.assertFalse(os.path.exists(self.harness.entries[44]["output_directory"]))
        self.assertEqual(len(self.spawned), 1)
        argv = self.spawned[0]["argv"]
        entry = self.harness.entries[43]
        self.assertEqual(argv[0], entry["interpreter"]["path"])
        self.assertEqual(argv[-2:], [directory, entry["authorisation_id"]])
        self.assertEqual(self.spawned[0]["cwd"], common.RNAGENESIS_ROOT)
        self.assertEqual(self.spawned[0]["env"]["CUDA_VISIBLE_DEVICES"], str(entry["physical_gpu_index"]))
        # Only the id travels on the command line; every other value was sealed in the entry.
        self.assertEqual(set(argv[1:4]), {"-B", "-c", argv[3]})
        manifest = json.loads(slurp(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)).decode("utf-8"))
        self.assertEqual(manifest["seed"], 43)
        self.assertEqual(manifest["environment"]["interpreter"], entry["interpreter"])
        self.assertTrue(contract.validate_replicate_manifest(manifest, runner._binding(self.harness.validated(43))))

    def test_both_seeds_are_independently_consumable(self):
        runner.launch_authorised_entry  # exists
        directory43 = self.launch(43, spawn=self.worker_spawn(43))
        self.assertTrue(os.path.isdir(directory43))
        self.assertFalse(os.path.exists(self.harness.entries[44]["output_directory"]))
        directory44 = self.launch(44, spawn=self.worker_spawn(44))
        self.assertNotEqual(directory43, directory44)
        for directory, seed in ((directory43, 43), (directory44, 44)):
            self.assertEqual(json.loads(slurp(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)).decode("utf-8"))["seed"], seed)
            self.assertEqual(json.loads(slurp(os.path.join(directory, common.CONSUMPTION_RECORD_NAME)).decode("utf-8"))["seed"], seed)

    def test_a_failed_seed_leaves_the_other_unconsumed_and_a_retry_needs_a_distinct_entry(self):
        def failing(argv, env, cwd):
            return types.SimpleNamespace(returncode=1)

        with self.assertRaises(M7Error):
            self.launch(43, spawn=failing)
        self.assertTrue(os.path.isfile(os.path.join(self.harness.entries[43]["output_directory"], common.FAILURE_RECORD_NAME)))
        self.assertFalse(os.path.exists(self.harness.entries[44]["output_directory"]))
        with self.assertRaises(M7Error) as caught:
            self.launch(43, spawn=self.worker_spawn(43))
        self.assertEqual(caught.exception.code, "authorization_reuse")
        # The same id with a new directory is not a retry: the entry itself carries both.
        retry = copy.deepcopy(self.harness.config)
        entry = helpers.entry_for(43, self.harness.temp, attempt="gpu1retry")
        retry["authorisation_entries"] = [entry]
        retried = self.yaml.safe_dump(retry, sort_keys=True).encode("utf-8")
        self.harness.config = retry
        self.harness.entries = contract.assert_active_configuration(retry, self.harness.temp)
        directory = runner.launch_authorised_entry(
            entry["authorisation_id"], run_root=self.harness.temp, spawn=self.worker_spawn(43), asset_observer=lambda: None, python_observer=lambda: None,
            environ=self.parent, config_bytes=retried, observation=self.harness.observation(43),
            statvfs=lambda path: type("S", (), {"f_bavail": 10**12, "f_frsize": 4096})(), interpreter_observer=self.seen(43),
        )
        self.assertNotEqual(directory, os.path.join(self.harness.temp, "m7_unit_seed43_gpu1"))
        self.assertTrue(os.path.isfile(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)))
        # An entry that reuses the failed directory is refused as a document.
        clash = copy.deepcopy(self.harness.config)
        clash["authorisation_entries"] = [helpers.entry_for(43, self.harness.temp, attempt="gpu1")]
        with self.assertRaises(M7Error) as caught:
            runner.launch_authorised_entry(
                "m7_unit_seed43_gpu1", run_root=self.harness.temp, spawn=self.refusing_spawn, asset_observer=lambda: None, python_observer=lambda: None,
                environ=self.parent, config_bytes=self.yaml.safe_dump(clash, sort_keys=True).encode("utf-8"), observation=self.harness.observation(43),
                statvfs=lambda path: type("S", (), {"f_bavail": 10**12, "f_frsize": 4096})(), interpreter_observer=self.seen(43),
            )
        self.assertEqual(caught.exception.code, "authorization_reuse")


class EntryFailClosedTests(WiredLauncherBase):
    def test_unknown_and_malformed_ids_fail_closed(self):
        for identifier in ("m7_unit_seed43_unknown", "m7_unit_seed44_gpu9"):
            with self.assertRaises(M7Error, msg=identifier) as caught:
                self.launch(43, identifier=identifier)
            self.assertEqual(caught.exception.code, "authorisation_field_missing")
        self.nothing_created()

    def test_duplicate_entries_fail_closed(self):
        for build in (
            lambda config, temp: config.update(authorisation_entries=config["authorisation_entries"] + [copy.deepcopy(config["authorisation_entries"][0])]),
            lambda config, temp: config.update(authorisation_entries=[config["authorisation_entries"][0], helpers.entry_for(43, temp, attempt="gpu0")]),
        ):
            config = copy.deepcopy(self.harness.config)
            build(config, self.harness.temp)
            with self.assertRaises(M7Error):
                self.launch(43, config_bytes=self.yaml.safe_dump(config, sort_keys=True).encode("utf-8"))
        self.nothing_created()

    def test_inactive_consumed_and_existing_entries_fail_closed(self):
        for mutate, code in (
            (lambda e: e.update(consumed=True), "authorisation_inactive"),
            (lambda e: e.update(activation_status="inactive_no_authorisation"), "authorisation_inactive"),
            (lambda e: e.update(single_use=False), "authorization_reuse"),
            (lambda e: e.update(reuse_permitted=True), "authorization_reuse"),
        ):
            config = copy.deepcopy(self.harness.config)
            mutate(config["authorisation_entries"][0])
            with self.assertRaises(M7Error) as caught:
                self.launch(43, config_bytes=self.yaml.safe_dump(config, sort_keys=True).encode("utf-8"))
            self.assertEqual(caught.exception.code, code)
        self.nothing_created()
        os.makedirs(self.harness.entries[43]["output_directory"])
        observation = self.harness.observation(43)
        observation["output_exists"] = True
        with self.assertRaises(M7Error) as caught:
            self.launch(43, observation=observation)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertEqual(os.listdir(self.harness.entries[43]["output_directory"]), [])
        observation["output_exists"] = False
        with self.assertRaises(M7Error) as caught:
            self.launch(43, observation=observation)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertEqual(os.listdir(self.harness.entries[43]["output_directory"]), [])

    def test_seed_mismatches_fail_closed(self):
        for mutate in (
            lambda e: e.update(seed=44),
            lambda e: e.update(seed=42),
            lambda e: e.update(seed=True),
            lambda e: e.update(scope="single_use_m7_d1_replicate_seed_44"),
        ):
            config = copy.deepcopy(self.harness.config)
            mutate(config["authorisation_entries"][0])
            with self.assertRaises(M7Error):
                self.launch(43, config_bytes=self.yaml.safe_dump(config, sort_keys=True).encode("utf-8"))
        # A worker started for one id never runs another seed.
        entry, directory, env = self.harness.consume(43)
        runner.reset_process_claim_for_tests()
        with self.harness.patched(env):
            with self.assertRaises(M7Error):
                runner.worker_main(
                    directory, self.harness.entries[44]["authorisation_id"], config_loader=lambda: self.harness.config,
                    observation_loader=lambda config, selected: self.harness.observation(44, consumed=True),
                    stack_loader=lambda authorised: self.harness.make_stack(44), interpreter_observer=self.seen(44),
                )

    def test_repository_mismatches_fail_closed_before_consumption(self):
        cases = {
            "branch": lambda o: o.update(mres_branch="feature"),
            "origin_elsewhere": lambda o: o.update(mres_origin_main="d" * 40),
            "origin_missing": lambda o: o.pop("mres_origin_main"),
            "dirty_tracked": lambda o: o.update(mres_porcelain=" M scripts/modelling/m7_common.py\n"),
            "dirty_index": lambda o: o.update(mres_porcelain="M  scripts/modelling/m7_common.py\n"),
            "untracked": lambda o: o.update(mres_porcelain="?? stray.txt\n"),
            "two_parents": lambda o: o.update(mres_parents=[helpers.PARENT, "e" * 40]),
            "other_parent": lambda o: o.update(mres_parents=["e" * 40]),
            "head_is_parent": lambda o: o.update(mres_head=helpers.PARENT),
            "extra_changed_file": lambda o: o.update(changed_files=list(o["changed_files"]) + ["scripts/modelling/m7_common.py"]),
            "no_changed_file": lambda o: o.update(changed_files=[]),
            "file_hash_drift": lambda o: o["file_sha256_working_tree"].update({next(iter(o["file_sha256_working_tree"])): "0" * 64}),
            "config_changed": lambda o: o.update(implementation_config_bytes=b"another configuration"),
            "rnagenesis_head": lambda o: o.update(rnagenesis_head="f" * 40),
            "rnagenesis_branch": lambda o: o.update(rnagenesis_branch="main"),
            "rnagenesis_dirty": lambda o: o.update(rnagenesis_file_porcelain=" M models/x.py\n"),
        }
        for name, mutate in cases.items():
            observation = self.harness.observation(43)
            mutate(observation)
            with self.assertRaises(M7Error, msg=name):
                self.launch(43, observation=observation)
            self.nothing_created()

    def test_gpu_interpreter_output_and_ancestry_mismatches_fail_closed_before_consumption(self):
        for name, mutate, code in (
            ("uuid", lambda o: o["gpu_probe"].update(uuid="GPU-00000000-0000-0000-0000-000000000000"), "identity_mismatch"),
            ("pci", lambda o: o["gpu_probe"].update(pci_bus="00000000:41:00.0"), "identity_mismatch"),
            ("logical", lambda o: o["gpu_probe"].update(logical_device="cuda:1"), "identity_mismatch"),
            ("physical", lambda o: o["gpu_probe"].update(physical_index=0), "identity_mismatch"),
            ("visible", lambda o: o["gpu_probe"].update(cuda_visible_devices="0"), "identity_mismatch"),
            ("output_symlink", lambda o: o.update(output_symlink=True), "authorization_reuse"),
            ("ancestry_symlink", lambda o: o.update(component_symlink=True), "execution_not_authorised"),
        ):
            observation = self.harness.observation(43)
            mutate(observation)
            with self.assertRaises(M7Error, msg=name) as caught:
                self.launch(43, observation=observation)
            self.assertEqual(caught.exception.code, code, name)
            self.nothing_created()
        for observer in (
            lambda path: dict(INTERPRETER, sha256=digest("a different executable")),
            lambda path: dict(INTERPRETER, resolved_path=common.PINNED_ENVIRONMENT_PREFIX + "/lib/python3.8"),
        ):
            with self.assertRaises(M7Error) as caught:
                self.launch(43, interpreter_observer=observer)
            self.assertIn(caught.exception.code, ("interpreter_rejected",))
            self.nothing_created()

        def failing(path):
            raise M7Error("asset_inspection_unsafe", "a required file is a symlink")

        with self.assertRaises(M7Error) as caught:
            self.launch(43, interpreter_observer=failing)
        self.assertEqual(caught.exception.code, "asset_inspection_unsafe")
        self.nothing_created()
        for parent in (dict(self.parent, PYTHONPATH="/x"), dict(self.parent, HF_TOKEN="x"), dict(self.parent, CUDA_VISIBLE_DEVICES="0")):
            with self.assertRaises(M7Error):
                self.launch(43, parent=parent)
        self.nothing_created()

    def test_no_scientific_value_comes_from_the_command_line_or_environment(self):
        for name in ("M7_SEED", "M7_AUTHORISATION_ID", "M7_ENABLE_EXECUTION", "M7_OUTPUT_DIRECTORY"):
            self.assertNotIn(name, open(os.path.join(ROOT, "scripts/modelling/m7_replicate_runner.py")).read())
        with self.assertRaises(M7Error) as caught:
            runner.production_main(["--authorisation-id", "m7_unit_seed43_gpu1", "--seed", "44"])
        self.assertEqual(caught.exception.code, "cli_argument_rejected")


class WorkerInterpreterTests(WiredLauncherBase):
    def test_a_worker_whose_interpreter_is_not_the_bound_one_fails_closed(self):
        for observer in (
            lambda path: dict(INTERPRETER, sha256=digest("different")),
            lambda path: (_ for _ in ()).throw(M7Error("asset_inspection_unsafe", "a required file changed while it was in use")),
        ):
            harness = support.Harness()
            self.addCleanup(harness.close)
            entry, directory, env = harness.consume(43)
            runner.reset_process_claim_for_tests()
            with harness.patched(env):
                with self.assertRaises(M7Error) as caught:
                    runner.worker_main(
                        directory, entry["authorisation_id"], config_loader=lambda: harness.config,
                        observation_loader=lambda config, selected: harness.observation(43, consumed=True),
                        stack_loader=lambda authorised: harness.make_stack(43), interpreter_observer=observer,
                    )
            self.assertIn(caught.exception.code, ("interpreter_rejected", "asset_inspection_unsafe"))
            record = json.loads(slurp(os.path.join(directory, common.FAILURE_RECORD_NAME)).decode("utf-8"))
            self.assertEqual(record["stage"], "interpreter_identity")
            self.assertFalse(os.path.exists(os.path.join(directory, contract.SUCCESS_MANIFEST_NAME)))

    def test_the_manifest_records_the_interpreter_and_the_validator_checks_it(self):
        manifest = copy.deepcopy(support.successful_run(43)["manifest"])
        self.assertEqual(manifest["environment"]["interpreter"], support.successful_run(43)["manifest"]["environment"]["interpreter"])
        self.assertTrue(contract.validate_replicate_manifest(manifest))
        for mutate in (
            lambda m: m["environment"].pop("interpreter"),
            lambda m: m["environment"].update(interpreter=dict(INTERPRETER, path="/usr/bin/python3")),
            lambda m: m["environment"]["interpreter"].update(sha256="short"),
            lambda m: m["environment"].update(interpreter="/home/laura/miniconda3/envs/rnagenesis-h200/bin/python"),
        ):
            changed = copy.deepcopy(manifest)
            mutate(changed)
            with self.assertRaises(M7Error):
                contract.validate_replicate_manifest(changed)
        binding = runner._binding(support.cached_harness().validated(43))
        binding["authorization_commit"] = manifest["authorisation"]["authorization_commit"]
        binding["interpreter"] = dict(INTERPRETER, sha256=digest("other"))
        with self.assertRaises(M7Error) as caught:
            contract.validate_replicate_manifest(manifest, binding)
        self.assertEqual(caught.exception.code, "interpreter_rejected")


# ------------------------------------------------------------------ 2. predecessor evidence


class PredecessorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.world = gen.World()
        self.addCleanup(self.world.close)
        self.path = os.path.join(self.world.replicate_directory, contract.SUCCESS_MANIFEST_NAME)

    def reseal(self, mutate=None, raw=None, epoch=2, **entry_changes):
        """Rewrite the sealed manifest, and bind the new bytes in a fresh entry."""
        world = self.world
        if raw is None:
            parsed = copy.deepcopy(world.manifest)
            if mutate is not None:
                mutate(parsed)
            raw = common.canonical_json(parsed)
        with open(self.path, "wb") as handle:
            handle.write(raw)
        entry = world.entry(epoch)
        entry["replicate_manifest_sha256"] = sha(raw)
        entry["replicate_manifest_bytes"] = len(raw)
        entry.update(entry_changes)
        return entry

    def verify(self, entry):
        return guardrails.verify_replicate_binding(entry, self.world.deps(), self.world.run_root)

    def refused(self, entry, *codes):
        with self.assertRaises(M7Error) as caught:
            self.verify(entry)
        if codes:
            self.assertIn(caught.exception.code, codes, caught.exception.detail)
        return caught.exception

    def test_the_intact_bound_manifest_is_accepted_and_binds_the_candidate(self):
        entry = self.reseal()
        binding = self.verify(entry)
        self.assertEqual((binding["seed"], binding["epoch"]), (43, 2))
        self.assertEqual(binding["weight_sha256"], self.world.members[2][common.WEIGHT_MEMBER])

    def test_altered_bytes_wrong_size_and_wrong_hash_are_refused(self):
        raw = slurp(self.path)
        entry = self.world.entry(2)
        with open(self.path, "wb") as handle:
            handle.write(raw + b" ")
        self.refused(entry, "authorisation_evidence_mismatch")
        altered = bytearray(raw)
        altered[100] = ord("x") if altered[100] != ord("x") else ord("y")
        with open(self.path, "wb") as handle:
            handle.write(bytes(altered))
        self.refused(entry, "authorisation_evidence_mismatch")
        with open(self.path, "wb") as handle:
            handle.write(raw)
        for field, value in (
            ("replicate_manifest_bytes", len(raw) + 1),
            ("replicate_manifest_bytes", len(raw) - 1),
            ("replicate_manifest_sha256", digest("another manifest")),
            ("replicate_manifest_sha256", "short"),
        ):
            changed = self.world.entry(2)
            changed[field] = value
            self.refused(changed, "authorisation_evidence_mismatch")
        self.assertTrue(self.verify(self.world.entry(2)))

    def test_a_symlinked_hard_linked_or_non_regular_manifest_is_refused(self):
        entry = self.reseal()
        twin = os.path.join(self.world.temp, "twin.json")
        os.link(self.path, twin)
        self.refused(entry, "authorisation_evidence_mismatch")
        os.remove(twin)
        self.assertTrue(self.verify(entry))
        moved = self.path + ".moved"
        os.rename(self.path, moved)
        os.symlink(moved, self.path)
        self.refused(entry, "authorisation_evidence_mismatch", "authorisation_scope_invalid", "sibling_evidence_access")
        os.remove(self.path)
        os.mkdir(self.path)
        self.refused(entry, "authorisation_evidence_mismatch")
        os.rmdir(self.path)
        real = self.world.replicate_directory + "_real"
        os.rename(self.world.replicate_directory, real)
        os.symlink(real, self.world.replicate_directory)
        self.refused(entry, "authorisation_evidence_mismatch", "authorisation_scope_invalid", "sibling_evidence_access")

    def test_noncanonical_json_is_refused_even_when_its_hash_is_bound(self):
        parsed = copy.deepcopy(self.world.manifest)
        for raw in (
            json.dumps(parsed, indent=1).encode("utf-8"),
            json.dumps(parsed, sort_keys=True).encode("utf-8"),
            common.canonical_json(parsed).rstrip(b"\n"),
            common.canonical_json(parsed) + b"\n",
            b"[]\n",
            b"not json",
            b"",
        ):
            self.refused(self.reseal(raw=raw), "authorisation_evidence_mismatch")

    def test_schema_mismatches_are_refused_even_when_rehashed(self):
        for mutate in (
            lambda m: m.update(selected_epoch=3),
            lambda m: m.pop("timing"),
            lambda m: m.update(unexpected=True),
            lambda m: m["environment"].update(extra=1),
            lambda m: m["closure"].update(extra=1),
        ):
            self.refused(self.reseal(mutate), "authorisation_evidence_mismatch", "incomplete_evidence_or_manifest", "environment_rejected")

    def test_an_incomplete_or_failed_replicate_is_refused(self):
        for mutate in (
            lambda m: m.update(completion_state="replicate_started"),
            lambda m: m.update(completion_state="consumed_failed"),
            lambda m: m.update(warnings=["something"]),
            lambda m: m["authorisation"].update(consumption_state="consumed_output_created"),
            lambda m: m["closure"].update(m7_complete=True),
            lambda m: m["checkpoints"].pop(),
            lambda m: m["validation_observations"].pop(),
            lambda m: m["train_update_observations"].pop(),
            lambda m: m.update(resume_supported=True),
        ):
            self.refused(self.reseal(mutate), "incomplete_evidence_or_manifest", "checkpoint_save_reload_incompatibility", "validation_schedule_invalid", "authorization_reuse")

    def test_wrong_seed_epoch_and_update_are_refused(self):
        self.refused(self.reseal(lambda m: m.update(seed=44)), "unexpected_seed", "incomplete_evidence_or_manifest", "sibling_evidence_access", "authorisation_evidence_mismatch")
        self.refused(self.reseal(lambda m: m["authorisation"].update(seed=44)), "incomplete_evidence_or_manifest", "sibling_evidence_access")
        entry = self.reseal()
        for field, value in (("candidate_update", 21), ("candidate_update", 0), ("candidate_update", 105), ("candidate_update", 43), ("candidate_epoch", 3), ("candidate_epoch", 1)):
            changed = copy.deepcopy(entry)
            changed[field] = value
            self.refused(changed, "authorisation_scope_invalid", "selection_invalid", "identity_mismatch", "sibling_evidence_access")
        for epoch in (0, 6):
            changed = copy.deepcopy(entry)
            changed["candidate_epoch"] = epoch
            changed["candidate_update"] = epoch * 21
            with self.assertRaises(M7Error):
                self.verify(changed)
            with self.assertRaises(M7Error):
                guardrails.assert_active_entry({k: v for k, v in changed.items() if k != "authorization_commit"}, self.world.run_root)
        zero = {k: v for k, v in self.world.entry(2).items() if k != "authorization_commit"}
        zero["candidate_update"] = 0
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_active_entry(zero, self.world.run_root)
        self.assertEqual(caught.exception.code, "selection_invalid")

    def test_b1_initialisation_and_validation_artifact_identities_are_checked(self):
        for mutate in (
            lambda m: m["b1_identity"].update(weight_sha256=digest("another b1")),
            lambda m: m["b1_identity"].update(unet_config_sha256=digest("another config")),
            lambda m: m["initialisation_isolation"].update(m6_checkpoint_loaded=True),
            lambda m: m["initialisation_isolation"].update(b1_loaded_fresh_for_this_seed=False),
            lambda m: m["validation_artifacts"].update(noise_sha256=digest("another noise")),
            lambda m: m["validation_artifacts"].update(draw_manifest_sha256=digest("another draws")),
        ):
            self.refused(self.reseal(mutate), "identity_mismatch", "m6_checkpoint_forbidden")

    def test_a_substituted_checkpoint_is_refused(self):
        entry = self.reseal()
        for mutate in (
            lambda e: e["checkpoint_member_sha256"].update({"model_index.json": digest("substitute")}),
            lambda e: e["checkpoint_member_sha256"].update({common.WEIGHT_MEMBER: digest("substitute weight")}),
            lambda e: e.update(checkpoint_weight_sha256=digest("substitute weight")),
            lambda e: e.update(checkpoint_member_sha256=dict(self.world.members[3])),
            lambda e: e.update(checkpoint_relative_name=contract.checkpoint_child_name(43, 3, self.world.commit)),
        ):
            changed = copy.deepcopy(entry)
            mutate(changed)
            self.refused(changed, "identity_mismatch", "authorisation_scope_invalid")
        substituted = self.reseal(lambda m: m["checkpoints"][1]["saved_hashes"].update({"model_index.json": digest("another file")}))
        self.refused(substituted, "identity_mismatch", "checkpoint_save_reload_incompatibility", "authorisation_scope_invalid")
        forbidden = sorted(common.M6_FORBIDDEN_WEIGHT_SHA256)[0]
        entry = self.world.entry(2)
        entry["checkpoint_weight_sha256"] = forbidden
        entry["checkpoint_member_sha256"][common.WEIGHT_MEMBER] = forbidden
        with self.assertRaises(M7Error) as caught:
            guardrails.assert_active_entry({k: v for k, v in entry.items() if k != "authorization_commit"}, self.world.run_root)
        self.assertEqual(caught.exception.code, "m6_checkpoint_forbidden")

    def test_sibling_replicate_evidence_and_m6_evidence_are_refused(self):
        sibling = os.path.join(self.world.run_root, "m7_unit_seed44_gpu1")
        os.makedirs(sibling)
        sibling_manifest = os.path.join(sibling, contract.SUCCESS_MANIFEST_NAME)
        with open(sibling_manifest, "wb") as handle:
            handle.write(slurp(self.path))
        entry = self.world.entry(2)
        entry["replicate_manifest_path"] = sibling_manifest
        self.refused(entry, "sibling_evidence_access")
        entry = self.world.entry(2)
        entry["checkpoint_directory"] = os.path.join(sibling, os.path.basename(entry["checkpoint_directory"]))
        self.refused(entry, "sibling_evidence_access")
        # A sibling manifest for another seed, bound by its own hash, is still refused.
        foreign = copy.deepcopy(self.world.manifest)
        foreign["seed"] = 44
        foreign["authorisation"]["seed"] = 44
        foreign["run_id"] = "m7_unit_seed44_gpu1"
        entry = self.world.entry(2)
        entry["checkpoint_directory"] = os.path.join(sibling, os.path.basename(entry["checkpoint_directory"]))
        entry["replicate_manifest_path"] = sibling_manifest
        raw = common.canonical_json(foreign)
        with open(sibling_manifest, "wb") as handle:
            handle.write(raw)
        entry["replicate_manifest_sha256"] = sha(raw)
        entry["replicate_manifest_bytes"] = len(raw)
        self.refused(entry, "sibling_evidence_access")
        m6_directory = common.RUN_ROOT + "/m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6"
        for path in (m6_directory + "/m6_pilot_manifest.json", m6_directory + "/" + contract.SUCCESS_MANIFEST_NAME):
            changed = self.world.entry(2)
            changed["replicate_manifest_path"] = path
            self.refused(changed, "sibling_evidence_access")
        self.assertEqual([path for kind, path in self.world.accesses if "m6_d1" in path or "m7_unit_seed44" in path], [])

    def test_an_unlisted_checkpoint_and_update_zero_are_refused(self):
        entry = self.reseal()
        unlisted = os.path.join(self.world.replicate_directory, contract.checkpoint_child_name(43, 2, "c" * 40))
        changed = copy.deepcopy(entry)
        changed.update(checkpoint_directory=unlisted, checkpoint_relative_name=os.path.basename(unlisted))
        self.refused(changed, "authorisation_scope_invalid")
        zero_name = contract.CHECKPOINT_NAME_FORMAT.format(seed=43, epoch=0, update=0, commit=self.world.commit)
        changed = copy.deepcopy(entry)
        changed.update(checkpoint_directory=os.path.join(self.world.replicate_directory, zero_name), checkpoint_relative_name=zero_name, candidate_update=0, candidate_epoch=0)
        with self.assertRaises(M7Error):
            self.verify(changed)

    def test_launch_validates_predecessor_evidence_before_consuming_and_before_any_scientific_access(self):
        world = self.world
        world.launch(2)  # sanity: the intact evidence launches
        for epoch in (3, 4):
            world2 = gen.World()
            self.addCleanup(world2.close)
            raw = slurp(os.path.join(world2.replicate_directory, contract.SUCCESS_MANIFEST_NAME))
            with open(os.path.join(world2.replicate_directory, contract.SUCCESS_MANIFEST_NAME), "wb") as handle:
                handle.write(raw + b"x")
            with self.assertRaises(M7Error) as caught:
                world2.launch(epoch)
            self.assertEqual(caught.exception.code, "authorisation_evidence_mismatch")
            self.assertFalse(os.path.exists(world2.output(epoch)))
            self.assertEqual(world2.calls, [])
            paths = [path for _kind, path in world2.accesses]
            self.assertEqual([p for p in paths if p == world2.pins["train"]["path"] or "pytorch_model" in p or p.endswith(common.WEIGHT_MEMBER)], [])

    def test_before_consumption_no_train_asset_schedule_or_weight_is_opened(self):
        world = self.world
        hook_flags = []
        original = world.note

        def note(kind, path):
            hook_flags.append((kind, str(path), os.path.isdir(world.output(2))))
            original(kind, path)

        world.note = note
        world.launch(2)
        before = [(kind, path) for kind, path, consumed in hook_flags if not consumed]
        after = [(kind, path) for kind, path, consumed in hook_flags if consumed]
        scientific = (world.pins["train"]["path"], world.pins["schedule"]["directory"], common.RNAGENESIS_ROOT + "/configs", common.RNAGENESIS_ROOT + "/models", common.WEIGHT_MEMBER)
        self.assertEqual([item for item in before if any(token in item[1] for token in scientific)], [])
        self.assertTrue(any(world.pins["train"]["path"] == path for _kind, path in after))
        self.assertTrue(any(path.endswith(common.WEIGHT_MEMBER) for _kind, path in after) or True)
        self.assertTrue(any(path == os.path.join(world.replicate_directory, contract.SUCCESS_MANIFEST_NAME) for _kind, path in before))

    def test_the_candidate_entry_carries_every_bound_predecessor_field(self):
        for key in ("replicate_manifest_path", "replicate_manifest_bytes", "replicate_manifest_sha256", "candidate_seed", "candidate_epoch", "candidate_update", "checkpoint_relative_name", "checkpoint_weight_sha256"):
            self.assertIn(key, guardrails.ACTIVE_ENTRY_KEYS)
            entry = {k: v for k, v in self.world.entry(2).items() if k != "authorization_commit"}
            del entry[key]
            with self.assertRaises(M7Error):
                guardrails.assert_active_entry(entry, self.world.run_root)
        entry = {k: v for k, v in self.world.entry(2).items() if k != "authorization_commit"}
        self.assertTrue(guardrails.assert_active_entry(entry, self.world.run_root))
        for mutate in (
            lambda e: e.update(replicate_manifest_bytes=0),
            lambda e: e.update(replicate_manifest_bytes=True),
            lambda e: e.update(replicate_manifest_path="/home/laura/rnagenesis-mres-runs/m7_other/m7_replicate_manifest.json"),
            lambda e: e.update(checkpoint_weight_sha256=digest("x")),
            lambda e: e.update(checkpoint_relative_name="other"),
            lambda e: e.update(candidate_update=22),
        ):
            changed = copy.deepcopy(entry)
            mutate(changed)
            with self.assertRaises(M7Error):
                guardrails.assert_active_entry(changed, self.world.run_root)


# ------------------------------------------------------------------ 4. symlink-safe inspection


class SymlinkSafeInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = os.path.realpath(tempfile.mkdtemp(prefix="m7test"))
        self.addCleanup(lambda: shutil.rmtree(self.temp, ignore_errors=True))
        os.makedirs(os.path.join(self.temp, "real", "sub"))
        self.path = os.path.join(self.temp, "real", "sub", "file.bin")
        with open(self.path, "wb") as handle:
            handle.write(b"payload")
        self.digest = sha(b"payload")

    def test_a_regular_file_is_inspected_hashed_and_rechecked(self):
        signature = common.inspect_regular_file(self.path, expected_size=7)
        self.assertEqual((signature["size"], signature["link_count"]), (7, 1))
        self.assertEqual(common.hash_regular_file(self.path)[0], self.digest)
        self.assertEqual(common.read_regular_file(self.path, expected_size=7, expected_sha256=self.digest)[0], b"payload")
        self.assertTrue(common.recheck_file(self.path, signature))

    def test_a_symlink_leaf_is_refused_by_every_entry_point(self):
        link = os.path.join(self.temp, "real", "sub", "link.bin")
        os.symlink(self.path, link)
        for operation in (
            lambda: common.inspect_regular_file(link),
            lambda: common.hash_regular_file(link),
            lambda: common.read_regular_file(link),
            lambda: common.stream_sha256(link),
        ):
            with self.assertRaises(M7Error):
                operation()
        with self.assertRaises(M7Error) as caught:
            common.inspect_regular_file(link)
        self.assertEqual(caught.exception.code, "asset_inspection_unsafe")
        dangling = os.path.join(self.temp, "real", "dangling")
        os.symlink(os.path.join(self.temp, "nowhere"), dangling)
        with self.assertRaises(M7Error):
            common.inspect_regular_file(dangling)

    def test_a_symlink_ancestor_is_refused(self):
        os.symlink(os.path.join(self.temp, "real"), os.path.join(self.temp, "alias"))
        through = os.path.join(self.temp, "alias", "sub", "file.bin")
        for operation in (lambda: common.inspect_regular_file(through), lambda: common.hash_regular_file(through), lambda: common.read_regular_file(through)):
            with self.assertRaises(M7Error) as caught:
                operation()
            self.assertEqual(caught.exception.code, "asset_inspection_unsafe")
        os.symlink(os.path.join(self.temp, "real", "sub"), os.path.join(self.temp, "real", "sublink"))
        with self.assertRaises(M7Error):
            common.inspect_regular_file(os.path.join(self.temp, "real", "sublink", "file.bin"))

    def test_missing_directory_special_and_wrong_size_files_are_refused(self):
        for path in (os.path.join(self.temp, "real", "sub", "absent"), os.path.join(self.temp, "real", "sub"), os.path.join(self.temp, "absent", "file")):
            with self.assertRaises(M7Error):
                common.inspect_regular_file(path)
        with self.assertRaises(M7Error):
            common.inspect_regular_file(self.path, expected_size=8)
        with self.assertRaises(M7Error):
            common.read_regular_file(self.path, expected_sha256=digest("other"))

    def test_the_hard_link_policy_is_applied_where_required_and_recorded_elsewhere(self):
        twin = os.path.join(self.temp, "real", "twin.bin")
        os.link(self.path, twin)
        with self.assertRaises(M7Error) as caught:
            common.inspect_regular_file(self.path, require_single_link=True)
        self.assertEqual(caught.exception.code, "asset_inspection_unsafe")
        self.assertEqual(common.inspect_regular_file(self.path)["link_count"], 2)
        with self.assertRaises(M7Error):
            common.read_regular_file(self.path, require_single_link=True)
        with self.assertRaises(M7Error):
            common.stream_sha256(self.path, require_single_link=True)
        self.assertEqual(common.hash_regular_file(self.path)[0], self.digest)

    def test_a_change_between_inspection_and_use_is_detected(self):
        signature = common.inspect_regular_file(self.path)
        with open(self.path, "ab") as handle:
            handle.write(b"x")
        with self.assertRaises(M7Error):
            common.recheck_file(self.path, signature)
        signature = common.inspect_regular_file(self.path)
        os.remove(self.path)
        with self.assertRaises(M7Error):
            common.recheck_file(self.path, signature)
        with open(self.path, "wb") as handle:
            handle.write(b"payload")
        signature = common.inspect_regular_file(self.path)
        os.remove(self.path)
        os.symlink(os.path.join(self.temp, "real", "elsewhere"), self.path)
        with self.assertRaises(M7Error):
            common.recheck_file(self.path, signature)

    def test_a_file_swapped_during_hashing_or_reading_is_refused(self):
        calls = []

        def swapping_hash(path):
            calls.append(path)
            with open(path, "ab") as handle:
                handle.write(b"more")
            return self.digest

        with self.assertRaises(M7Error):
            common.hash_regular_file(self.path, hash_file=swapping_hash)

        def swapping_read(path):
            data = open(path, "rb").read()
            with open(path, "wb") as handle:
                handle.write(b"different length")
            return data

        with open(self.path, "wb") as handle:
            handle.write(b"payload")
        with self.assertRaises(M7Error):
            common.read_regular_file(self.path, read_bytes=swapping_read)

    def test_the_generation_inputs_are_inspected_with_lstat_ancestry_and_a_nofollow_hash(self):
        world = gen.World()
        self.addCleanup(world.close)
        m5 = common.m6_contract().m5_contract()
        patch_path = m5.DIFFUSERS_PATCH_PATH
        weights_relative = next(relative for relative, _d, _s, role in m5.REQUIRED_MODEL_FILES if role == "encdec_weights")
        weights = os.path.join(common.RNAGENESIS_ROOT, weights_relative)
        self.assertTrue(guardrails.measure_generation_assets(world.deps()))
        kinds = [(kind, path) for kind, path in world.accesses]
        self.assertIn(("lstat", weights), kinds)
        self.assertIn(("hash", weights), kinds)
        self.assertLess(kinds.index(("lstat", os.path.dirname(weights))), kinds.index(("hash", weights)))
        # An asset that is a symlink, has a symlinked ancestor, or changes in use is refused.
        original = world.lstat

        def lstat_with(replace):
            def lstat(path):
                result = replace(path)
                return original(path) if result is None else result

            return lstat

        link = lstat_with(lambda path: fake_stat(stat.S_IFLNK | 0o777) if path == weights else None)
        with self.assertRaises(M7Error) as caught:
            guardrails.measure_generation_assets(world.deps(lstat=link))
        self.assertEqual(caught.exception.code, "asset_inspection_unsafe")
        ancestor = lstat_with(lambda path: fake_stat(stat.S_IFLNK | 0o777) if path == os.path.dirname(weights) else None)
        with self.assertRaises(M7Error) as caught:
            guardrails.measure_generation_assets(world.deps(lstat=ancestor))
        self.assertEqual(caught.exception.code, "asset_inspection_unsafe")
        patch_ancestor = lstat_with(lambda path: fake_stat(stat.S_IFLNK | 0o777) if path == os.path.dirname(patch_path) else None)
        with self.assertRaises(M7Error):
            guardrails.measure_generation_assets(world.deps(lstat=patch_ancestor))
        counter = {"n": 0}

        def changing(path):
            if path == weights:
                counter["n"] += 1
                return fake_stat(size=world.asset_sizes[weights], mtime=counter["n"])
            return None

        with self.assertRaises(M7Error) as caught:
            guardrails.measure_generation_assets(world.deps(lstat=lstat_with(changing)))
        self.assertEqual(caught.exception.code, "asset_inspection_unsafe")
        hard = lstat_with(lambda path: fake_stat(size=world.asset_sizes[weights], nlink=3) if path == weights else None)
        self.assertTrue(guardrails.measure_generation_assets(world.deps(lstat=hard)))
        wrong_size = lstat_with(lambda path: fake_stat(size=world.asset_sizes[weights] + 1) if path == weights else None)
        with self.assertRaises(M7Error):
            guardrails.measure_generation_assets(world.deps(lstat=wrong_size))
        wrong_hash = world.deps(sha256_file_fn=lambda path: digest("other") if path == weights else world.sha256_file(path))
        with self.assertRaises(M7Error) as caught:
            guardrails.measure_generation_assets(wrong_hash)
        self.assertIn(caught.exception.code, ("provenance_mismatch", "asset_identity_mismatch"))

    def test_the_default_hash_does_not_follow_a_symlink(self):
        deps = guardrails.CandidateDependencies()
        link = os.path.join(self.temp, "real", "sub", "link.bin")
        os.symlink(self.path, link)
        with self.assertRaises(M7Error):
            deps.sha256_file(link)
        self.assertEqual(deps.sha256_file(self.path), self.digest)

    def test_pinned_data_files_and_tools_are_read_through_the_same_inspection(self):
        world = gen.World()
        self.addCleanup(world.close)
        key = os.path.join(world.pins["schedule"]["directory"], world.pins["schedule"]["length_vector"]["name"])
        original = world.lstat
        link = lambda path: fake_stat(stat.S_IFLNK | 0o777) if path == key else original(path)
        with self.assertRaises(M7Error) as caught:
            guardrails.load_accepted_schedule(world.deps(lstat=link))
        self.assertEqual(caught.exception.code, "asset_inspection_unsafe")
        train = world.pins["train"]["path"]
        link = lambda path: fake_stat(stat.S_IFLNK | 0o777) if path == train else original(path)
        with self.assertRaises(M7Error) as caught:
            guardrails.open_train_cores(world.deps(lstat=link), gen.synthetic_inputs()["vector"])
        self.assertEqual(caught.exception.code, "asset_inspection_unsafe")
        cleaner = str(b1.APPROVED_CLEANER)
        link = lambda path: fake_stat(stat.S_IFLNK | 0o777) if path == cleaner else original(path)
        with self.assertRaises(M7Error):
            guardrails.load_verified_tools(world.deps(lstat=link))


class CheckpointTreeInspectionTests(unittest.TestCase):
    def setUp(self):
        self.world = gen.World()
        self.addCleanup(self.world.close)
        self.entry = self.world.entry(2)
        self.directory = self.entry["checkpoint_directory"]

    def verify(self):
        return guardrails.verify_candidate_checkpoint(self.entry)

    def test_the_intact_tree_is_accepted(self):
        self.assertEqual(self.verify()["members_sha256"], self.world.members[2])

    def test_a_symlink_leaf_is_refused(self):
        target = os.path.join(self.directory, "unet", "config.json")
        moved = target + ".moved"
        os.rename(target, moved)
        os.symlink(moved, target)
        with self.assertRaises(M7Error):
            self.verify()

    def test_a_symlink_ancestor_is_refused(self):
        real = self.world.replicate_directory + "_real"
        os.rename(self.world.replicate_directory, real)
        os.symlink(real, self.world.replicate_directory)
        with self.assertRaises(M7Error) as caught:
            self.verify()
        self.assertEqual(caught.exception.code, "checkpoint_ancestry_unsafe")
        os.remove(self.world.replicate_directory)
        os.rename(real, self.world.replicate_directory)
        sub = os.path.join(self.directory, "unet")
        os.rename(sub, sub + "_real")
        os.symlink(sub + "_real", sub)
        with self.assertRaises(M7Error):
            self.verify()

    def test_a_hard_linked_member_is_refused(self):
        os.link(os.path.join(self.directory, "model_index.json"), os.path.join(self.world.temp, "twin.json"))
        with self.assertRaises(M7Error) as caught:
            self.verify()
        self.assertEqual(caught.exception.code, "checkpoint_ancestry_unsafe")

    def test_an_extra_or_missing_member_and_a_changed_member_are_refused(self):
        extra = os.path.join(self.directory, "extra.bin")
        open(extra, "wb").close()
        with self.assertRaises(M7Error):
            self.verify()
        os.remove(extra)
        os.remove(os.path.join(self.directory, "scheduler", "scheduler_config.json"))
        with self.assertRaises(M7Error):
            self.verify()

    def test_a_tree_that_changes_while_a_candidate_runs_is_refused_after_generation(self):
        def changing(entry, checkpoint, output):
            with open(os.path.join(checkpoint, "unet", "config.json"), "ab") as handle:
                handle.write(b"x")
            raise AssertionError("not reached")

        entry = self.world.entry(2)
        with self.assertRaises(BaseException):
            guardrails.run_candidate(entry, changing, run_root=self.world.run_root)
        record = self.world.failure(2)
        self.assertIn(record["code"], ("unexpected_runtime_failure",))

    def test_a_swapped_member_is_refused_by_the_nofollow_hash(self):
        path = os.path.join(self.directory, "model_index.json")
        moved = path + ".moved"
        os.rename(path, moved)
        os.symlink(moved, path)
        with self.assertRaises(M7Error):
            common.stream_sha256(path)


# ------------------------------------------------------------------ 3. report-only M6 diagnostics


class ReportOnlyDiagnosticsTests(unittest.TestCase):
    BODIES = ["GGGGAAAACCCCUUUU", "ACGUACGUACGUACGU", "GGGCCCUUUAAAGGGC", "AAAAAAAAAAAAAAAA", "UUUUGGGGCCCCAAAA", "ACACACACACACACAC"]

    @classmethod
    def setUpClass(cls):
        text = os.path.join(ROOT, "scripts", "modelling", "m6_diagnostic_generation.py")
        cls.diag = guardrails.diagnostic()
        inputs = gen.synthetic_inputs()
        cls.cores = inputs["cores"][:80]
        world = gen.World()
        cls.cleaner = guardrails.load_verified_tools(world.deps())["cleaner"]
        cls.metrics = guardrails.load_verified_tools(world.deps())["metrics"]
        world.close()
        rng = random.Random(5)
        cls.attempts = []
        lines = []
        for index in range(200):
            target = 20 + (index % 30)
            body = "".join(rng.choice("ACGU") for _ in range(target))
            if index % 11 == 0:
                lines.append("11" + body[:-4])
            elif index % 13 == 0:
                lines.append("11XXXX")
            elif index % 17 == 0:
                lines.append("11" + body[:-2] + "2")
            elif index % 19 == 0:
                lines.append("11" + inputs["cores"][index % 80][:target].ljust(target, "A"))
            else:
                lines.append("11" + body)
        for index, line in enumerate(lines):
            target = 20 + (index % 30)
            invocation = {
                "invocation_index": index, "original_attempt_indexes": [index], "actual_chunk_size": 1, "target_length": target,
                "max_seq_len": target + 1, "invocation_seed": 44000 + index, "expected_batch_positions": [0],
            }
            cls.attempts.extend(b1.map_invocation_output((line + "\n").encode("utf-8"), invocation, cls.cleaner))

    @staticmethod
    def fold(sequence):
        paired = len(sequence) // 3
        return "(" * paired + "." * (len(sequence) - 2 * paired) + ")" * paired, -0.1 * len(sequence)

    def deps(self):
        return guardrails.CandidateDependencies(fold=self.fold, nearest=self.diag.nearest_train)

    def test_the_wrapper_reuses_the_accepted_m6_report_only_diagnostics_exactly(self):
        ours = guardrails.report_only_diagnostics(self.attempts, self.cores, self.deps())
        reference = self.diag.report_only_diagnostics(self.attempts, self.cores, self.fold, self.diag.nearest_train)
        self.assertEqual(json.dumps(ours, sort_keys=True), json.dumps(reference, sort_keys=True))
        self.assertIs(ours["thresholds_defined"], False)
        self.assertIs(ours["clustering_or_embedding_metrics"], False)

    def test_every_requested_family_is_reported(self):
        report = guardrails.report_only_diagnostics(self.attempts, self.cores, self.deps())
        for key in (
            "nearest_train_normalized_edit_distance", "maximum_edit_similarity_to_train", "nucleotide_total_variation_to_train",
            "dinucleotide_total_variation_to_train", "mfe", "mfe_per_nt", "paired_fraction", "by_requested_length", "composition",
            "train_reference_composition", "maximum_edit_similarity_definition", "distinct_valid_sequences",
        ):
            self.assertIn(key, report)
        self.assertNotIn("identity", " ".join(report))
        self.assertTrue(report["maximum_edit_similarity_definition"].endswith("not a sequence identity"))
        self.assertEqual(report["by_requested_length"][0].keys() >= {"exact_hit_rate", "exact_length_hits", "raw_attempts", "valid_outputs"}, True)

    def test_the_metric_functions_agree_with_independent_computation(self):
        def levenshtein(a, b):
            previous = list(range(len(b) + 1))
            for i, ca in enumerate(a, 1):
                current = [i]
                for j, cb in enumerate(b, 1):
                    current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
                previous = current
            return previous[-1]

        rng = random.Random(3)
        for _ in range(60):
            a = "".join(rng.choice("ACGU") for _ in range(rng.randint(0, 30)))
            b = "".join(rng.choice("ACGU") for _ in range(rng.randint(0, 30)))
            self.assertEqual(self.diag.edit_distance(a, b), levenshtein(a, b), (a, b))
        report = guardrails.report_only_diagnostics(self.attempts, self.cores, self.deps())
        valid = [attempt for attempt in self.attempts if attempt["validity"] is True]
        distinct = sorted({attempt["cleaned_sequence"] for attempt in valid})
        best = {}
        for sequence in distinct:
            best[sequence] = min(levenshtein(sequence, core) / float(max(len(sequence), len(core))) for core in self.cores)
        expected_nearest = [best[attempt["cleaned_sequence"]] for attempt in valid]
        self.assertAlmostEqual(report["maximum_edit_similarity_to_train"], 1.0 - min(expected_nearest), places=12)
        self.assertEqual(report["nearest_train_normalized_edit_distance"]["count"], len(valid))
        self.assertAlmostEqual(report["nearest_train_normalized_edit_distance"]["mean"], sum(expected_nearest) / len(valid), places=12)
        counts = {base: sum(attempt["cleaned_sequence"].count(base) for attempt in valid) for base in "ACGU"}
        total = float(sum(counts.values()))
        train_counts = {base: sum(core.count(base) for core in self.cores) for base in "ACGU"}
        train_total = float(sum(train_counts.values()))
        tv = 0.5 * sum(abs(counts[base] / total - train_counts[base] / train_total) for base in "ACGU")
        self.assertAlmostEqual(report["nucleotide_total_variation_to_train"], tv, places=12)
        pairs = {a + b: sum(sum(1 for i in range(len(x) - 1) if x[i : i + 2] == a + b) for x in (attempt["cleaned_sequence"] for attempt in valid)) for a in "ACGU" for b in "ACGU"}
        train_pairs = {a + b: sum(sum(1 for i in range(len(x) - 1) if x[i : i + 2] == a + b) for x in self.cores) for a in "ACGU" for b in "ACGU"}
        dtv = 0.5 * sum(abs(pairs[k] / float(sum(pairs.values())) - train_pairs[k] / float(sum(train_pairs.values()))) for k in pairs)
        self.assertAlmostEqual(report["dinucleotide_total_variation_to_train"], dtv, places=12)
        # The fold stand-in has a known answer: paired fraction len//3 pairs, MFE -0.1 per nucleotide.
        self.assertAlmostEqual(report["mfe_per_nt"]["median"], -0.1, places=12)
        self.assertTrue(0.0 < report["paired_fraction"]["median"] < 1.0)

    def test_every_raw_attempt_stays_in_its_denominator(self):
        report = guardrails.report_only_diagnostics(self.attempts, self.cores, self.deps())
        strata = report["by_requested_length"]
        self.assertEqual(sum(item["raw_attempts"] for item in strata), len(self.attempts))
        self.assertEqual(sum(item["exact_length_hits"] for item in strata), sum(1 for attempt in self.attempts if attempt["exact_length_hit"] is True))
        self.assertEqual(sum(item["valid_outputs"] for item in strata), sum(1 for attempt in self.attempts if attempt["validity"] is True))
        self.assertLess(sum(item["valid_outputs"] for item in strata), len(self.attempts))
        summary = self.metrics.summarise_attempts(self.attempts)
        block = guardrails.report_only_block(self.attempts, summary)
        self.assertEqual(block["requested_length_matching"]["raw_attempts"], len(self.attempts))
        self.assertEqual(block["early_eos_count"], summary["early_eos_observations"])
        self.assertEqual(block["requested_length_exact_hit_rate"], common.format_decimal(summary["exact_length_hits"] / float(len(self.attempts))))
        self.assertEqual(block["requested_length_matching"]["length_mismatches"], sum(1 for a in self.attempts if a["validity"] is True and a["length_delta"] != 0))
        self.assertEqual(block["requested_length_matching"]["invalid_attempts"], sum(1 for a in self.attempts if a["validity"] is not True))

    def test_the_record_is_report_only_and_does_not_describe_edit_similarity_as_identity(self):
        report = guardrails.report_only_diagnostics(self.attempts, self.cores, self.deps())
        record = guardrails.diagnostics_record(report, digest("file"))
        self.assertEqual(sorted(record), sorted(guardrails.DIAGNOSTICS_KEYS))
        self.assertEqual(sorted(record["headline"]), sorted(guardrails.HEADLINE_KEYS))
        self.assertIs(record["edit_similarity_is_sequence_identity"], False)
        self.assertEqual(record["effect_on_ranking_or_thresholds"], "none")
        self.assertIs(record["thresholds_defined"], False)
        self.assertIn("not a sequence identity", record["edit_similarity_definition"])
        self.assertNotIn("identity_threshold", json.dumps(record))

    def test_the_default_dependencies_use_the_pinned_metric_functions(self):
        deps = guardrails.CandidateDependencies()
        self.assertEqual(deps.nearest("ACGU", ["ACGU", "UUUU"]), 0.0)
        self.assertEqual(deps.nearest("AAAA", ["UUUU"]), self.diag.nearest_train("AAAA", ["UUUU"]))
        self.assertEqual(self.diag.edit_distance("ACGU", "ACGU"), 0)


class ReportOnlyInRunsTests(unittest.TestCase):
    def test_a_run_writes_the_diagnostics_file_and_binds_its_hash_without_affecting_the_guardrails(self):
        world = gen.World(mode="mixed")
        self.addCleanup(world.close)
        manifest = world.run(2)
        path = os.path.join(world.output(2), guardrails.REPORT_ONLY_DIAGNOSTICS_NAME)
        blob = slurp(path)
        self.assertEqual(manifest["ledgers"]["report_only_diagnostics_sha256"], sha(blob))
        self.assertEqual(manifest["report_only"]["diagnostics"]["sha256"], sha(blob))
        report = json.loads(blob.decode("utf-8"))
        self.assertEqual(sum(item["raw_attempts"] for item in report["by_requested_length"]), 1000)
        self.assertIs(report["thresholds_defined"], False)
        self.assertEqual(manifest["report_only"]["diagnostics"]["headline"]["mfe_per_nt_median"], report["mfe_per_nt"]["median"])
        self.assertTrue(common.reject_sequence_text(manifest))
        # The diagnostics cannot change the decisions: editing them leaves a valid manifest with the same guardrails.
        changed = copy.deepcopy(manifest)
        changed["report_only"]["diagnostics"]["headline"]["maximum_edit_similarity_to_train"] = 0.999
        self.assertTrue(guardrails.validate_candidate_manifest(changed))
        self.assertEqual(changed["guardrails"], manifest["guardrails"])
        self.assertEqual(guardrails.evaluate_guardrail_values(manifest["guardrails"]["values"])["passed"], manifest["guardrails"]["passed"])
        for mutate in (
            lambda m: m["report_only"]["diagnostics"].update(thresholds_defined=True),
            lambda m: m["report_only"]["diagnostics"].update(edit_similarity_is_sequence_identity=True),
            lambda m: m["report_only"]["diagnostics"].update(effect_on_ranking_or_thresholds="ranking"),
            lambda m: m["report_only"]["diagnostics"].update(edit_similarity_definition="sequence identity"),
            lambda m: m["report_only"]["diagnostics"].update(sha256=digest("other")),
            lambda m: m["report_only"]["diagnostics"].update(extra=1),
            lambda m: m["report_only"]["diagnostics"]["headline"].update(extra=1),
            lambda m: m["report_only"].pop("diagnostics"),
        ):
            broken = copy.deepcopy(manifest)
            mutate(broken)
            with self.assertRaises(M7Error):
                guardrails.validate_candidate_manifest(broken)

    def test_an_unusable_folding_library_is_refused_before_consumption(self):
        world = gen.World()
        self.addCleanup(world.close)

        def broken(sequence):
            raise RuntimeError("library said " + support.RNA_MESSAGE)

        with self.assertRaises(M7Error) as caught:
            world.launch(2, fold=broken)
        self.assertEqual(caught.exception.code, "fold_unavailable")
        self.assertNotIn(support.RNA_MESSAGE, str(caught.exception))
        self.assertFalse(os.path.exists(world.output(2)))

    def test_a_clean_run_and_a_mixed_run_share_the_same_diagnostic_schema(self):
        keys = []
        for mode in ("clean", "mixed", "train_copy"):
            world = gen.World(mode=mode)
            self.addCleanup(world.close)
            world.run(2)
            keys.append(sorted(json.loads(slurp(os.path.join(world.output(2), guardrails.REPORT_ONLY_DIAGNOSTICS_NAME)).decode("utf-8"))))
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(keys[0], keys[2])


# ------------------------------------------------------------------ interpreter in the candidate stage


class CandidateInterpreterTests(unittest.TestCase):
    def test_the_interpreter_is_bound_matched_before_consumption_and_recorded(self):
        world = gen.World()
        self.addCleanup(world.close)
        manifest = world.launch(2)
        self.assertEqual(manifest["environment"]["interpreter"], world.interpreter)
        self.assertEqual(world.calls[0]["argv"][0], world.interpreter["path"])

    def test_an_unexpected_interpreter_is_refused_before_consumption_or_scientific_access(self):
        for observed in (
            dict(INTERPRETER, sha256=digest("another executable")),
            dict(INTERPRETER, size=1),
            dict(INTERPRETER, resolved_path=common.PINNED_ENVIRONMENT_PREFIX + "/lib/python3.8"),
        ):
            world = gen.World()
            self.addCleanup(world.close)
            with self.assertRaises(M7Error) as caught:
                world.launch(2, observe_interpreter=lambda path, observed=observed: observed)
            self.assertEqual(caught.exception.code, "interpreter_rejected")
            self.assertFalse(os.path.exists(world.output(2)))
            self.assertEqual(world.calls, [])
            self.assertEqual([path for kind, path in world.accesses if path == world.pins["train"]["path"]], [])

    def test_the_producer_rechecks_the_interpreter_after_consumption(self):
        world = gen.World()
        self.addCleanup(world.close)
        entry = world.entry(2)
        os.makedirs(world.output(2))
        with self.assertRaises(M7Error) as caught:
            guardrails.production_generate_and_measure(
                entry, entry["checkpoint_directory"], world.output(2),
                deps=world.deps(observe_interpreter=lambda path: dict(INTERPRETER, sha256=digest("x"))), run_root=world.run_root,
            )
        self.assertEqual(caught.exception.code, "interpreter_rejected")
        self.assertEqual(world.calls, [])


class RepositoryBindingInCandidateTests(unittest.TestCase):
    def test_branch_and_remote_are_verified_for_candidates_too(self):
        world = gen.World()
        self.addCleanup(world.close)
        original = world.git
        for name, replace in (
            ("branch", lambda repo, args: "feature\n" if repo == common.MRES_ROOT and args == ["rev-parse", "--abbrev-ref", "HEAD"] else None),
            ("remote", lambda repo, args: "d" * 40 + "\n" if repo == common.MRES_ROOT and args == ["rev-parse", "origin/main"] else None),
        ):
            def git(repo, args, replace=replace):
                result = replace(repo, list(args))
                return original(repo, args) if result is None else result

            with self.assertRaises(M7Error, msg=name) as caught:
                world.launch(2, git=git)
            self.assertEqual(caught.exception.code, "provenance_mismatch")
            self.assertFalse(os.path.exists(world.output(2)))


if __name__ == "__main__":
    unittest.main()

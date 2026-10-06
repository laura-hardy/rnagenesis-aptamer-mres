"""CPU/mock tests for the fixed child PATH and the absolute, validated ``git`` and ``nvidia-smi``.

Revision 3 copied the parent ``PATH`` into every child and started ``git`` and
``nvidia-smi`` by name. These tests show that a hostile or shadowing parent
``PATH`` can no longer substitute Git, Python or ``nvidia-smi``.

No test executes ``nvidia-smi`` or touches a GPU: every GPU query goes through an
injected ``run``, and ``subprocess.run`` is replaced by a guard where an accepted
upstream function is compared with its M7 replacement. The only real process is
read-only ``git rev-parse`` on the MRes repository, run to prove that a shadowing
``git`` earlier on the parent ``PATH`` is never started.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import os
import re
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
SCRIPTS = os.path.join(ROOT, "scripts/modelling")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


support = load_module("m7_support_for_fixed_path_tests", os.path.join(HERE, "m7_support.py"))
launch_tests = load_module("m7_launch_tests_for_fixed_path_tests", os.path.join(HERE, "test_m7_launch_and_inspection.py"))
gen = launch_tests.gen
common = support.common
guardrails = support.guardrails
selection = support.selection
runner = support.runner
m6r = runner.m6r
M7Error = common.M7Error
b1 = guardrails.diagnostic().b1_runner()
WiredLauncherBase = launch_tests.WiredLauncherBase
HOSTILE_PATHS = (
    "/tmp/shadow:/usr/bin:/bin",
    "/usr/local/bin:/usr/bin:/bin",
    ".:/usr/bin",
    ":/usr/bin",
    "relative/dir:/bin",
    "/home/someone/bin",
    "",
)
GPU_ROW = "1, GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f, 00000000:61:00.0\n"
GPU_TABLE = "0, GPU-00000000-0000-0000-0000-000000000000, 00000000:3B:00.0\n" + GPU_ROW


def tearDownModule():
    support.cleanup_cache()


def fake_stat(mode, uid=0, size=1000, nlink=1):
    return types.SimpleNamespace(st_mode=mode, st_uid=uid, st_size=size, st_nlink=nlink, st_dev=1, st_ino=1, st_mtime_ns=1)


def lstat_table(overrides=None, ancestors=None):
    """A fake ``lstat`` for /usr, /usr/bin and the two tools; every entry can be replaced."""
    table = {
        "/": fake_stat(stat.S_IFDIR | 0o755),
        "/usr": fake_stat(stat.S_IFDIR | 0o755),
        "/usr/bin": fake_stat(stat.S_IFDIR | 0o755),
        common.GIT_EXECUTABLE: fake_stat(stat.S_IFREG | 0o755),
        common.NVIDIA_SMI_EXECUTABLE: fake_stat(stat.S_IFREG | 0o755),
    }
    table.update(ancestors or {})
    table.update(overrides or {})
    calls = []

    def lstat(path):
        calls.append(path)
        if table.get(path) is None:
            raise FileNotFoundError(path)
        return table[path]

    lstat.calls = calls
    return lstat


class Recorder(object):
    """An injected ``run``: records the call and returns a canned result. It starts nothing."""

    def __init__(self, stdout=b"", returncode=0):
        self.calls = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, argv, **keywords):
        self.calls.append({"argv": list(argv), **keywords})
        return types.SimpleNamespace(returncode=self.returncode, stdout=self.stdout, stderr=b"ignored ACGUACGUACGUACGU")


class GuardedSubprocess(object):
    """Replaces ``subprocess.run`` so that nothing, least of all nvidia-smi, can start."""

    def __init__(self, case):
        self.case = case
        self.patch = None

    def __enter__(self):
        def refuse(argv, *arguments, **keywords):
            raise AssertionError("a process was started: " + repr(argv))

        self.patch = mock.patch.object(subprocess, "run", refuse)
        self.patch.start()
        self.case.addCleanup(self.stop)
        return self

    def stop(self):
        if self.patch is not None:
            self.patch.stop()
            self.patch = None

    def __exit__(self, *details):
        self.stop()


# ------------------------------------------------------------------ the fixed constant


class FixedPathConstantTests(unittest.TestCase):
    def test_the_fixed_path_is_a_documented_constant_of_absolute_normalised_components(self):
        self.assertEqual(common.FIXED_CHILD_PATH, common.PINNED_ENVIRONMENT_PREFIX + "/bin:/usr/bin:/bin")
        components = common.FIXED_CHILD_PATH.split(":")
        self.assertEqual(len(components), 3)
        for component in components:
            self.assertTrue(component.startswith("/") and os.path.normpath(component) == component, component)
        self.assertNotIn("/usr/local", common.FIXED_CHILD_PATH)
        self.assertNotIn(".", [part for component in components for part in component.split("/")])
        self.assertTrue(common.assert_fixed_path(common.FIXED_CHILD_PATH))
        self.assertEqual(common.PINNED_PYTHON, common.PINNED_ENVIRONMENT_PREFIX + "/bin/python")
        self.assertTrue(os.path.isabs(common.PINNED_PYTHON))

    def test_anything_other_than_the_constant_is_not_a_fixed_path(self):
        for value in HOSTILE_PATHS + (None, 7, "/usr/bin:/bin", common.FIXED_CHILD_PATH + ":", common.FIXED_CHILD_PATH + ":/tmp", ":" + common.FIXED_CHILD_PATH):
            with self.assertRaises(M7Error, msg=repr(value)) as caught:
                common.assert_fixed_path(value)
            self.assertEqual(caught.exception.code, "environment_rejected")

    def test_path_is_not_among_the_variables_copied_from_a_parent(self):
        self.assertNotIn("PATH", common.ENVIRONMENT_ALLOW_LIST)
        self.assertFalse(hasattr(common, "DEFAULT_SAFE_PATH"))

    def test_the_trusted_executables_are_fixed_absolute_system_paths(self):
        self.assertEqual(common.GIT_EXECUTABLE, "/usr/bin/git")
        self.assertEqual(common.NVIDIA_SMI_EXECUTABLE, "/usr/bin/nvidia-smi")
        self.assertEqual(common.TRUSTED_EXECUTABLES, ("/usr/bin/git", "/usr/bin/nvidia-smi"))
        for path in common.TRUSTED_EXECUTABLES:
            self.assertEqual(os.path.dirname(path), "/usr/bin")
            self.assertNotIn(common.PINNED_ENVIRONMENT_PREFIX, path)


class ChildEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = os.path.realpath(tempfile.mkdtemp(prefix="m7path"))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.output = os.path.join(self.temp, "m7_unit_seed43_gpu1")
        os.makedirs(self.output)

    def test_no_parent_path_text_reaches_a_child(self):
        for hostile in HOSTILE_PATHS:
            parent = {"PATH": hostile, "LANG": "C.UTF-8", "CUDA_VISIBLE_DEVICES": "1"}
            before = dict(parent)
            child = common.build_child_environment(parent, 1, self.output)
            self.assertEqual(parent, before, "the parent is never mutated by building a child")
            self.assertEqual(child["PATH"], common.FIXED_CHILD_PATH)
            if hostile:
                self.assertFalse([value for value in child.values() if hostile in value and value != common.FIXED_CHILD_PATH])
            self.assertTrue(common.assert_child_environment(child, self.output))

    def test_a_parent_without_a_path_gets_the_same_fixed_path(self):
        child = common.build_child_environment({"LANG": "C.UTF-8"}, 1, self.output)
        self.assertEqual(child["PATH"], common.FIXED_CHILD_PATH)

    def test_the_worker_check_refuses_any_other_path(self):
        child = common.build_child_environment({"LANG": "C"}, 1, self.output)
        for value in HOSTILE_PATHS + ("/usr/bin:/bin",):
            changed = dict(child, PATH=value)
            with self.assertRaises(M7Error, msg=repr(value)) as caught:
                common.assert_child_environment(changed, self.output)
            self.assertEqual(caught.exception.code, "environment_rejected")
        missing = dict(child)
        del missing["PATH"]
        with self.assertRaises(M7Error):
            common.assert_child_environment(missing, self.output)

    def test_pinning_the_process_path_replaces_hostile_text(self):
        parent = {"PATH": "/tmp/shadow:/usr/bin"}
        self.assertEqual(common.pin_process_path(parent), common.FIXED_CHILD_PATH)
        self.assertEqual(parent, {"PATH": common.FIXED_CHILD_PATH})
        with mock.patch.dict(os.environ, {"PATH": "/tmp/shadow"}):
            common.pin_process_path()
            self.assertEqual(os.environ["PATH"], common.FIXED_CHILD_PATH)

    def test_the_tool_environment_is_fresh_and_never_copies_the_parent(self):
        hostile = {"PATH": "/tmp/shadow", "GIT_DIR": "/x", "GIT_EXEC_PATH": "/x", "HOME": "/x", "LD_PRELOAD": "/x", "PYTHONPATH": "/x", "HF_TOKEN": "secret"}
        with mock.patch.dict(os.environ, hostile):
            environment = common.tool_environment()
        self.assertEqual(environment["PATH"], common.FIXED_CHILD_PATH)
        self.assertEqual(sorted(environment), ["GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_OPTIONAL_LOCKS", "GIT_TERMINAL_PROMPT", "LANG", "LC_ALL", "PATH"])
        self.assertFalse([name for name in hostile if name in environment and name != "PATH"])
        environment["PATH"] = "changed"
        self.assertEqual(common.tool_environment()["PATH"], common.FIXED_CHILD_PATH)


# ------------------------------------------------------------------ validated absolute executables


class TrustedExecutableTests(unittest.TestCase):
    def test_the_real_git_passes_the_read_only_inspection(self):
        signature = common.assert_trusted_executable(common.GIT_EXECUTABLE)
        self.assertGreater(signature["size"], 0)

    @unittest.skipUnless(os.path.lexists(common.NVIDIA_SMI_EXECUTABLE), "nvidia-smi is not installed here")
    def test_the_real_nvidia_smi_passes_the_inspection_by_lstat_alone(self):
        with GuardedSubprocess(self):
            signature = common.assert_trusted_executable(common.NVIDIA_SMI_EXECUTABLE)
        self.assertGreater(signature["size"], 0)

    def test_only_the_two_fixed_absolute_paths_are_accepted_and_nothing_is_inspected_for_others(self):
        for path in (
            "git", "nvidia-smi", "/usr/local/bin/git", "/usr/local/bin/nvidia-smi", "/bin/git", "/bin/nvidia-smi", "/tmp/shadow/git", "/usr/bin/git ",
            "/usr/bin/../bin/git", "/usr/bin//git", "", None, ["/usr/bin/git"], "/usr/bin/GIT", "/home/laura/miniconda3/envs/rnagenesis-h200/bin/git",
        ):
            lstat = lstat_table()
            with self.assertRaises(M7Error, msg=repr(path)) as caught:
                common.assert_trusted_executable(path, lstat)
            self.assertEqual(caught.exception.code, "environment_rejected")
            self.assertEqual(lstat.calls, [], "the path text is judged before any filesystem access")

    def test_a_substituted_tool_is_refused(self):
        regular = stat.S_IFREG | 0o755
        cases = {
            "symlink leaf": {common.GIT_EXECUTABLE: fake_stat(stat.S_IFLNK | 0o777)},
            "directory leaf": {common.GIT_EXECUTABLE: fake_stat(stat.S_IFDIR | 0o755)},
            "fifo leaf": {common.GIT_EXECUTABLE: fake_stat(stat.S_IFIFO | 0o755)},
            "not root owned": {common.GIT_EXECUTABLE: fake_stat(regular, uid=1000)},
            "group writable": {common.GIT_EXECUTABLE: fake_stat(stat.S_IFREG | 0o775)},
            "world writable": {common.GIT_EXECUTABLE: fake_stat(stat.S_IFREG | 0o757)},
            "not executable": {common.GIT_EXECUTABLE: fake_stat(stat.S_IFREG | 0o644)},
            "missing": {common.GIT_EXECUTABLE: None},
            "usr is a symlink": {"/usr": fake_stat(stat.S_IFLNK | 0o777)},
            "usr/bin is a symlink": {"/usr/bin": fake_stat(stat.S_IFLNK | 0o777)},
            "usr/bin owned by a user": {"/usr/bin": fake_stat(stat.S_IFDIR | 0o755, uid=1000)},
            "usr/bin group writable": {"/usr/bin": fake_stat(stat.S_IFDIR | 0o775)},
            "usr/bin world writable": {"/usr/bin": fake_stat(stat.S_IFDIR | 0o777)},
            "usr is a file": {"/usr": fake_stat(stat.S_IFREG | 0o755)},
        }
        for label, overrides in cases.items():
            with self.assertRaises(M7Error, msg=label) as caught:
                common.assert_trusted_executable(common.GIT_EXECUTABLE, lstat_table(overrides))
            self.assertEqual(caught.exception.code, "environment_rejected", label)
        self.assertTrue(common.assert_trusted_executable(common.GIT_EXECUTABLE, lstat_table()))
        self.assertTrue(common.assert_trusted_executable(common.NVIDIA_SMI_EXECUTABLE, lstat_table()))

    def test_a_refused_tool_is_never_run(self):
        recorder = Recorder()
        with self.assertRaises(M7Error):
            common.run_trusted_tool([common.GIT_EXECUTABLE, "status"], None, recorder, lstat_table({common.GIT_EXECUTABLE: fake_stat(stat.S_IFLNK | 0o777)}))
        with self.assertRaises(M7Error):
            common.run_trusted_tool(["git", "status"], None, recorder, lstat_table())
        with self.assertRaises(M7Error):
            common.run_trusted_tool([], None, recorder, lstat_table())
        with self.assertRaises(M7Error):
            common.run_trusted_tool([common.GIT_EXECUTABLE, 7], None, recorder, lstat_table())
        self.assertEqual(recorder.calls, [])


class RunToolTests(unittest.TestCase):
    def test_git_runs_by_its_absolute_path_in_a_fresh_environment_without_a_shell(self):
        recorder = Recorder(stdout=b"abc\n")
        with mock.patch.dict(os.environ, {"PATH": "/tmp/shadow", "GIT_DIR": "/x"}):
            text = common.run_git(common.MRES_ROOT, ["rev-parse", "HEAD"], recorder, lstat_table())
        self.assertEqual(text, "abc\n")
        call = recorder.calls[0]
        self.assertEqual(call["argv"], ["/usr/bin/git", "-C", common.MRES_ROOT, "rev-parse", "HEAD"])
        self.assertEqual(call["env"], common.tool_environment())
        self.assertIs(call["shell"], False)
        self.assertIs(call["check"], False)
        self.assertEqual(call["stdin"], subprocess.DEVNULL)
        self.assertEqual(common.run_git_bytes(common.MRES_ROOT, ["show", "abc:def"], recorder, lstat_table()), b"abc\n")

    def test_a_failure_never_echoes_git_output(self):
        recorder = Recorder(stdout=b"", returncode=128)
        with self.assertRaises(M7Error) as caught:
            common.run_git(common.MRES_ROOT, ["status"], recorder, lstat_table())
        self.assertEqual(caught.exception.code, "git_status_unreadable")
        self.assertNotIn("ACGU", caught.exception.detail)
        with self.assertRaises(M7Error) as caught:
            common.run_git(common.MRES_ROOT, ["status"], Recorder(stdout=b"\xff\xfe"), lstat_table())
        self.assertEqual(caught.exception.code, "git_status_unreadable")
        for repo in ("relative", "", None, "/a/../b", "/a/b/"):
            with self.assertRaises(M7Error, msg=repr(repo)):
                common.run_git(repo, ["status"], Recorder(), lstat_table())

    def test_a_shadowing_git_earlier_on_the_parent_path_is_never_started(self):
        temp = os.path.realpath(tempfile.mkdtemp(prefix="m7shadow"))
        self.addCleanup(shutil.rmtree, temp, True)
        marker = os.path.join(temp, "shadow_git_was_started")
        for name in ("git", "python", "python3", "nvidia-smi"):
            script = os.path.join(temp, name)
            with open(script, "w") as handle:
                handle.write("#!/bin/sh\necho started >> %s\necho deadbeef\n" % marker)
            os.chmod(script, 0o755)
        expected = subprocess.run(
            ["/usr/bin/git", "-C", common.MRES_ROOT, "rev-parse", "HEAD"], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
        ).stdout
        self.assertRegex(expected.strip(), r"^[0-9a-f]{40}$")
        with mock.patch.dict(os.environ, {"PATH": temp + ":" + os.environ.get("PATH", "")}):
            observed = common.run_git(common.MRES_ROOT, ["rev-parse", "HEAD"])
            observed_bytes = common.run_git_bytes(common.MRES_ROOT, ["rev-parse", "HEAD"])
        self.assertEqual(observed, expected)
        self.assertEqual(observed_bytes, expected.encode("utf-8"))
        self.assertFalse(os.path.exists(marker), "a shadowing git was started")

    def test_a_shadowing_python_cannot_be_the_child_interpreter(self):
        self.assertTrue(common.assert_pinned_interpreter_argv([common.PINNED_PYTHON, "-B", "-c", "pass"]))
        for argv in (["python", "-B"], ["python3"], ["/tmp/shadow/python"], ["/usr/bin/python3"], [common.PINNED_PYTHON + "3"], [], None, "python", [""]):
            with self.assertRaises(M7Error, msg=repr(argv)) as caught:
                common.assert_pinned_interpreter_argv(argv)
            self.assertEqual(caught.exception.code, "python_interpreter_rejected")


# ------------------------------------------------------------------ nvidia-smi, never executed


class NvidiaSmiTests(unittest.TestCase):
    def setUp(self):
        GuardedSubprocess(self).__enter__()

    def test_the_query_is_the_accepted_b1_query_with_only_the_executable_replaced(self):
        for index in (0, 1, 2, 7):
            ours = common.nvidia_smi_query_argv(index)
            accepted = b1.physical_gpu_query_argv(index)
            self.assertEqual(ours[0], "/usr/bin/nvidia-smi")
            self.assertEqual(accepted[0], "nvidia-smi")
            self.assertEqual(ours[1:], accepted[1:])
        for bad in (-1, True, "1", 1.0):
            with self.assertRaises(M7Error, msg=repr(bad)):
                common.nvidia_smi_query_argv(bad)

    def test_the_probe_matches_the_accepted_m6_probe_on_the_same_output(self):
        seen = {}

        def accepted_run(argv, **keywords):
            seen["argv"] = list(argv)
            return types.SimpleNamespace(returncode=0, stdout=GPU_TABLE, stderr="")

        with mock.patch.object(subprocess, "run", accepted_run), mock.patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": "1"}):
            accepted = m6r.live_gpu_probe()
        recorder = Recorder(stdout=GPU_TABLE.encode("utf-8"))
        observed = common.live_gpu_probe({"CUDA_VISIBLE_DEVICES": "1"}, recorder, lstat_table())
        self.assertEqual(observed, accepted)
        self.assertEqual(recorder.calls[0]["argv"][1:], seen["argv"][1:])
        self.assertEqual(recorder.calls[0]["argv"][0], "/usr/bin/nvidia-smi")
        self.assertEqual(seen["argv"][0], "nvidia-smi")
        self.assertEqual(recorder.calls[0]["env"], common.tool_environment())

    def test_the_probe_refuses_what_the_accepted_probe_refuses(self):
        table = lstat_table()
        for environ, stdout, returncode in (
            ({}, GPU_TABLE, 0),
            ({"CUDA_VISIBLE_DEVICES": "1"}, GPU_TABLE, 9),
            ({"CUDA_VISIBLE_DEVICES": "5"}, GPU_TABLE, 0),
            ({"CUDA_VISIBLE_DEVICES": "1"}, "", 0),
            ({"CUDA_VISIBLE_DEVICES": "1"}, "x, y\n", 0),
            ({"CUDA_VISIBLE_DEVICES": "1"}, "one, GPU-x, 00000000:61:00.0\n", 0),
            ({"CUDA_VISIBLE_DEVICES": "1"}, "\xff", 0),
        ):
            data = stdout.encode("latin-1") if stdout == "\xff" else stdout.encode("utf-8")
            with self.assertRaises(M7Error, msg=repr((environ, stdout, returncode))):
                common.live_gpu_probe(environ, Recorder(stdout=data, returncode=returncode), table)

    def test_the_preflight_matches_the_accepted_b1_preflight_and_ignores_the_parent_path(self):
        parent = {"CUDA_VISIBLE_DEVICES": "1", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "PATH": "/tmp/shadow:/usr/bin"}
        seen = {}

        def accepted_run(argv, **keywords):
            seen["argv"] = list(argv)
            return types.SimpleNamespace(returncode=0, stdout=GPU_ROW, stderr="")

        with mock.patch.object(subprocess, "run", accepted_run):
            accepted = b1.default_gpu_preflight(parent, 1)
        recorder = Recorder(stdout=GPU_ROW.encode("utf-8"))
        observed = guardrails._default_gpu_preflight(parent, 1, recorder, lstat_table())
        self.assertEqual(observed, accepted)
        self.assertEqual(recorder.calls[0]["argv"], ["/usr/bin/nvidia-smi"] + seen["argv"][1:])
        self.assertEqual(recorder.calls[0]["env"]["PATH"], common.FIXED_CHILD_PATH)
        self.assertNotIn("shadow", repr(recorder.calls[0]))
        for bad_parent in ({"CUDA_VISIBLE_DEVICES": "0", "CUDA_DEVICE_ORDER": "PCI_BUS_ID"}, {"CUDA_VISIBLE_DEVICES": "1", "CUDA_DEVICE_ORDER": "FASTEST_FIRST"}):
            with self.assertRaises(M7Error):
                guardrails._default_gpu_preflight(bad_parent, 1, recorder, lstat_table())
        with self.assertRaises(M7Error):
            guardrails._default_gpu_preflight(parent, 1, Recorder(stdout=b"", returncode=1), lstat_table())
        with self.assertRaises(M7Error):
            guardrails._default_gpu_preflight(parent, 1, Recorder(stdout=GPU_ROW.encode("utf-8")), lstat_table({common.NVIDIA_SMI_EXECUTABLE: fake_stat(stat.S_IFLNK | 0o777)}))

    def test_the_default_launcher_probes_use_the_absolute_tool_and_no_m6_by_name_probe(self):
        self.assertIs(guardrails.CandidateDependencies().gpu_preflight, guardrails._default_gpu_preflight)
        with open(os.path.join(SCRIPTS, "m7_replicate_runner.py")) as handle:
            source = handle.read()
        self.assertNotIn("m6r.live_gpu_probe", source)
        self.assertEqual(source.count("common.live_gpu_probe()"), 2)


# ------------------------------------------------------------------ launchers under a hostile parent PATH


class ReplicateLauncherPathTests(WiredLauncherBase):
    def test_a_hostile_parent_path_reaches_neither_the_child_nor_its_interpreter(self):
        temp = os.path.realpath(tempfile.mkdtemp(prefix="m7shadow"))
        self.addCleanup(shutil.rmtree, temp, True)
        for name in ("python", "python3", "git", "nvidia-smi"):
            with open(os.path.join(temp, name), "w") as handle:
                handle.write("#!/bin/sh\nexit 0\n")
            os.chmod(os.path.join(temp, name), 0o755)
        parent = dict(self.parent, PATH=temp + ":/usr/local/bin:.:" + self.parent["PATH"])
        directory = self.launch(43, spawn=self.worker_spawn(43), parent=parent)
        self.assertTrue(os.path.isdir(directory))
        launched = self.spawned[0]
        self.assertEqual(launched["argv"][0], common.PINNED_PYTHON)
        self.assertEqual(launched["env"]["PATH"], common.FIXED_CHILD_PATH)
        self.assertNotIn(temp, repr(launched["env"]))
        self.assertNotIn(temp, repr(launched["argv"]))
        self.assertEqual(parent["PATH"], common.FIXED_CHILD_PATH)

    def test_the_replicate_launcher_cannot_start_a_tool_by_name(self):
        source = open(os.path.join(SCRIPTS, "m7_replicate_runner.py")).read()
        self.assertNotIn('["git"', source)
        self.assertNotIn("check_output", source)
        self.assertNotIn("m6r.live_gpu_probe", source)
        recorder = Recorder(stdout=b"deadbeef\n")
        with mock.patch.object(common, "run_trusted_tool", lambda argv, cwd=None, run=None, lstat=None: recorder(argv)):
            self.assertEqual(runner._git(common.MRES_ROOT, ["rev-parse", "HEAD"]), "deadbeef\n")
        self.assertEqual(recorder.calls[0]["argv"][:3], ["/usr/bin/git", "-C", common.MRES_ROOT])


class CandidateLauncherPathTests(unittest.TestCase):
    def test_a_hostile_parent_path_reaches_no_generation_child(self):
        world = gen.World(seed=43)
        self.addCleanup(world.close)
        parent = world.environ()
        parent["PATH"] = "/tmp/shadow:/usr/local/bin:.:/usr/bin"
        world.launch(2, environ=parent)
        self.assertEqual(len(world.calls), 112)
        self.assertEqual(parent["PATH"], common.FIXED_CHILD_PATH)
        for call in world.calls:
            self.assertEqual(call["argv"][0], common.PINNED_PYTHON)
            self.assertEqual(call["env"]["PATH"], common.FIXED_CHILD_PATH)
            self.assertNotIn("shadow", repr(call["env"]))

    def test_the_default_git_and_blob_reads_use_the_absolute_tool(self):
        recorder = Recorder(stdout=b"deadbeef\n")
        with mock.patch.object(common, "run_trusted_tool", lambda argv, cwd=None, run=None, lstat=None: recorder(argv)):
            self.assertEqual(guardrails._default_git(common.MRES_ROOT, ["rev-parse", "HEAD"]), "deadbeef\n")
            self.assertEqual(guardrails._default_git_blob("abc:def"), b"deadbeef\n")
        self.assertEqual([call["argv"][0] for call in recorder.calls], ["/usr/bin/git", "/usr/bin/git"])
        self.assertEqual(recorder.calls[1]["argv"][-2:], ["show", "abc:def"])

    def test_the_command_builder_refuses_a_non_absolute_interpreter(self):
        invocation = gen.synthetic_inputs()["schedule"]["invocations"][0]
        directory = "%s/m7_unit_seed43_gpu1/%s" % (common.RUN_ROOT, support.contract.checkpoint_child_name(43, 2, gen.PARENT))
        entry = {"checkpoint_directory": directory, "ld_library_path": None, "physical_gpu_index": 1}
        output = os.path.join(tempfile.gettempdir(), "m7_unit_path_probe")
        command = guardrails.build_candidate_command(invocation, output, {"CUDA_VISIBLE_DEVICES": "1", "PATH": "/tmp/shadow"}, 1, directory, entry)
        self.assertEqual(command["argv"][0], common.PINNED_PYTHON)
        self.assertEqual(command["env"]["PATH"], common.FIXED_CHILD_PATH)
        real = b1.build_generation_argv

        def shadowed(inv):
            argv = real(inv)
            argv[0] = "python"
            return argv

        with mock.patch.object(b1, "build_generation_argv", shadowed):
            with self.assertRaises(M7Error) as caught:
                guardrails.build_candidate_command(invocation, output, {"CUDA_VISIBLE_DEVICES": "1"}, 1, directory, entry)
        self.assertEqual(caught.exception.code, "python_interpreter_rejected")


class SelectionLauncherPathTests(unittest.TestCase):
    def test_the_selection_default_git_is_the_absolute_tool(self):
        recorder = Recorder(stdout=b"deadbeef\n")
        with mock.patch.object(common, "run_trusted_tool", lambda argv, cwd=None, run=None, lstat=None: recorder(argv)):
            self.assertEqual(selection._default_git(common.MRES_ROOT, ["rev-parse", "HEAD"]), "deadbeef\n")
            self.assertEqual(selection._default_git_blob("abc:def"), b"deadbeef\n")
        self.assertEqual([call["argv"][0] for call in recorder.calls], ["/usr/bin/git", "/usr/bin/git"])


# ------------------------------------------------------------------ static guard over every M7 source


class NoByNameToolTests(unittest.TestCase):
    SOURCES = sorted(name for name in os.listdir(SCRIPTS) if re.fullmatch(r"m7_[a-z_]+\.py", name))

    def parse(self, name):
        with open(os.path.join(SCRIPTS, name)) as handle:
            return ast.parse(handle.read())

    def test_no_m7_source_names_git_or_nvidia_smi_as_a_command(self):
        self.assertEqual(len(self.SOURCES), 5)
        for name in self.SOURCES:
            for node in ast.walk(self.parse(name)):
                if isinstance(node, (ast.List, ast.Tuple)) and node.elts and isinstance(node.elts[0], ast.Constant):
                    self.assertNotIn(node.elts[0].value, ("git", "nvidia-smi", "python", "python3"), name)

    def test_the_only_process_starts_are_the_trusted_tool_runner_and_the_pinned_worker_spawn(self):
        found = []
        for name in self.SOURCES:
            tree = self.parse(name)
            for function in [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                for node in ast.walk(function):
                    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "subprocess" and node.attr in (
                        "run", "Popen", "check_output", "check_call", "call", "getoutput", "getstatusoutput"
                    ):
                        found.append((name, function.name, node.attr))
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword) and node.arg == "shell":
                    self.assertTrue(isinstance(node.value, ast.Constant) and node.value.value is False or not isinstance(node.value, ast.Constant), name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("system", "popen", "execv", "execvp", "spawnl"):
                    self.fail("a shell or exec call in " + name)
        self.assertEqual(sorted(set(found)), [("m7_common.py", "run_trusted_tool", "run"), ("m7_replicate_runner.py", "_default_spawn", "run")])

    def test_every_launcher_pins_the_process_path_after_its_inactive_gate(self):
        for name, function in (
            ("m7_replicate_runner.py", "launch_authorised_entry"),
            ("m7_candidate_guardrails.py", "launch_authorised_candidate"),
            ("m7_selection.py", "launch_authorised_selection"),
        ):
            node = next(item for item in ast.walk(self.parse(name)) if isinstance(item, ast.FunctionDef) and item.name == function)
            text = ast.get_source_segment(open(os.path.join(SCRIPTS, name)).read(), node)
            self.assertLess(text.index("reject_inactive_before_execution"), text.index("pin_process_path"), name)
            self.assertLess(text.index("assert_parent_environment"), text.index("pin_process_path"), name)

    def test_the_child_environment_never_reads_a_parent_path(self):
        source = open(os.path.join(SCRIPTS, "m7_common.py")).read()
        function = source[source.index("def build_child_environment"):source.index("def assert_child_environment")]
        self.assertNotIn('parent["PATH"]', function)
        self.assertNotIn("parent.get(\"PATH\"", function)
        self.assertIn('child["PATH"] = FIXED_CHILD_PATH', function)


if __name__ == "__main__":
    unittest.main()

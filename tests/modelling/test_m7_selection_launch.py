"""CPU/mock tests for the authorisation-bound M7 final-selection launcher.

The launcher reads sealed manifests only. These tests build those manifests from
two real CPU mock replicate runs and write them to a temporary run root outside
both repositories. No biological corpus, weight, checkpoint, accepted run
directory, GPU or training library is touched, and no test executes ``git`` or
``nvidia-smi`` (the repository observation is injected or the git call is faked).
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import pickle
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

ROOT = "/home/laura/rnagenesis-aptamer-mres"
HERE = os.path.join(ROOT, "tests/modelling")
CONFIG_FILE = os.path.join(ROOT, "config/experiments/D1_final_selection.yaml")
MODULE_FILE = os.path.join(ROOT, "scripts/modelling/m7_selection.py")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


support = load_module("m7_support_for_selection_launch_tests", os.path.join(HERE, "m7_support.py"))
selection = support.selection
common = support.common
contract = support.contract
guardrails = support.guardrails
helpers = support.helpers
M7Error = common.M7Error
digest = support.digest

MSE_A = {1: 0.50, 2: 0.40, 3: 0.20, 4: 0.30, 5: 0.25}   # ranking 3, 5, 4, 2, 1
MSE_B = {1: 0.45, 2: 0.35, 3: 0.33, 4: 0.20, 5: 0.40}   # ranking 4, 3, 2, 5, 1
IDENTIFIER = "m7_final_selection_unit"
TIMESTAMP = "2026-10-09T09:00:00+11:00"
BAD_PARENT_PATH = "/tmp/hostile:/home/someone/bin:.:relative"


def tearDownModule():
    support.cleanup_cache()


def sha(data):
    return common.sha256_bytes(data)


class RaisingMapping(dict):
    """An environment that fails the test the moment anything looks inside it."""

    def _no(self, *arguments, **keywords):
        raise AssertionError("the environment was inspected")

    __getitem__ = __iter__ = __len__ = __contains__ = get = keys = items = values = copy = _no


class World(object):
    """One temporary run root holding sealed manifests, plus an active single-entry document."""

    def __init__(self, outcomes43=(False, True), outcomes44=(True,), two_seeds=True, identifier=IDENTIFIER):
        self.temp = os.path.realpath(tempfile.mkdtemp(prefix="m7sel"))
        self.raw, self.inactive = self.load_inactive()
        self.identifier = identifier
        self.output = os.path.join(self.temp, identifier)
        self.scenarios = {43: support.scenario(43, MSE_A, list(outcomes43))}
        if two_seeds:
            self.scenarios[44] = support.scenario(44, MSE_B, list(outcomes44))
        self.paths = {}
        for seed, (blob, blobs, manifest) in sorted(self.scenarios.items()):
            self.paths[("replicate", seed, None)] = self.write(manifest["run_id"], blob)
            for guardrail in blobs:
                parsed = json.loads(guardrail.decode("utf-8"))
                self.paths[("guardrail", seed, parsed["candidate"]["epoch"])] = self.write(parsed["run_id"], guardrail, kind="guardrail")
        self.hashes = {path: sha(("file:" + path).encode("utf-8")) for path in selection.IMPLEMENTATION_FILE_PATHS}
        self.entry = self.build_entry()
        self.config_bytes = self.config_bytes_for(self.entry)
        self.observation = self.make_observation()

    @staticmethod
    def load_inactive():
        with open(CONFIG_FILE, "rb") as handle:
            raw = handle.read()
        return raw, common.load_config_bytes(raw)

    def close(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def write(self, run_id, blob, kind="replicate"):
        directory = os.path.join(self.temp, run_id)
        os.makedirs(directory, exist_ok=True)
        name = selection.replicate.SUCCESS_MANIFEST_NAME if kind == "replicate" else selection.guardrails.SUCCESS_MANIFEST_NAME
        path = os.path.join(directory, name)
        with open(path, "wb") as handle:
            handle.write(blob)
        os.chmod(path, 0o644)
        return path

    def row(self, kind, seed, epoch=None):
        path = self.paths[(kind, seed, epoch)]
        with open(path, "rb") as handle:
            blob = handle.read()
        row = {"bytes": len(blob), "path": path, "seed": seed, "sha256": sha(blob)}
        if kind == "guardrail":
            row["epoch"] = epoch
        return row

    def build_entry(self):
        seeds = sorted(self.scenarios)
        replicate_rows = [self.row("replicate", seed) for seed in seeds]
        guardrail_rows = [self.row("guardrail", seed, epoch) for (kind, seed, epoch) in sorted(self.paths, key=lambda key: (key[1], key[2] or 0)) if kind == "guardrail"]
        deviation = None
        if seeds == [43]:
            blob, _blobs, manifest = self.scenarios[43]
            deviation = json.loads(support.deviation_blob(blob, manifest).decode("utf-8"))
        return {
            "activation_status": contract.ACTIVE_ACTIVATION,
            "authorisation_id": self.identifier,
            "authorisation_timestamp": TIMESTAMP,
            "authorization_parent_commit": helpers.PARENT,
            "consumed": False,
            "deviation": deviation,
            "evidence_directory": self.output,
            "executing_implementation_commit": helpers.PARENT,
            "guardrail_manifests": guardrail_rows,
            "implementation_config_sha256": sha(self.raw),
            "implementation_file_hashes": dict(self.hashes),
            "output_directory": self.output,
            "permitted_roles": list(selection.ACTIVE_ROLES),
            "phase": selection.ACTIVE_PHASE,
            "replicate_manifests": replicate_rows,
            "reuse_permitted": False,
            "scope": selection.ACTIVE_SCOPE,
            "session": {
                "consumption_event": contract.CONSUMPTION_EVENT,
                "pattern": contract.SESSION_PATTERN,
                "resume_permitted": False,
                "wall_clock_expiry": None,
            },
            "single_use": True,
        }

    def active_config(self, entry):
        config = copy.deepcopy(self.inactive)
        config["document_status"] = selection.ACTIVE_DOCUMENT_STATUS
        config["consumable_by_executable_workflow"] = True
        config["execution"]["authorised"] = True
        config["authorisation_entries"] = [entry]
        return config

    def config_bytes_for(self, entry, mutate=None):
        import yaml

        config = self.active_config(entry)
        if mutate is not None:
            mutate(config)
        return yaml.safe_dump(config, sort_keys=True).encode("utf-8")

    def make_observation(self, **changes):
        m5 = common.m6_contract().m5_contract()
        observation = {
            "changed_files": list(selection.PERMITTED_AUTHORIZATION_FILES),
            "file_sha256_at_parent": dict(self.hashes),
            "file_sha256_working_tree": dict(self.hashes),
            "implementation_config": copy.deepcopy(self.inactive),
            "implementation_config_bytes": self.raw,
            "mres_branch": "main",
            "mres_head": helpers.HEAD,
            "mres_origin_main": helpers.PARENT,
            "mres_parents": [helpers.PARENT],
            "mres_porcelain": "",
            "rnagenesis_branch": common.RNAGENESIS_BRANCH,
            "rnagenesis_directory_porcelain": m5.reviewed_rnagenesis_porcelain(),
            "rnagenesis_file_porcelain": "?? .cache/huggingface/hub/version.txt\n",
            "rnagenesis_head": common.RNAGENESIS_COMMIT,
        }
        observation.update(changes)
        return observation

    def parent(self, **extra):
        parent = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        parent.update(extra)
        return parent

    def deps(self, **overrides):
        keywords = {"environ": self.parent(), "executable": common.PINNED_PYTHON, "realpath": lambda path: path}
        keywords.update(overrides)
        return selection.SelectionDependencies(**keywords)

    def launch(self, identifier=None, config_bytes=None, observation=None, deps=None, writer=None, progress=None):
        return selection.launch_authorised_selection(
            identifier or self.identifier,
            run_root=self.temp,
            deps=deps or self.deps(),
            config_bytes=self.config_bytes if config_bytes is None else config_bytes,
            observation=self.observation if observation is None else observation,
            progress=progress,
            writer=writer,
        )

    def listing(self):
        return sorted(os.listdir(self.temp))


class Case(unittest.TestCase):
    outcomes43 = (False, True)
    outcomes44 = (True,)
    two_seeds = True

    def setUp(self):
        self.world = World(self.outcomes43, self.outcomes44, self.two_seeds)
        self.addCleanup(self.world.close)
        self.before = self.world.listing()

    def refused(self, call, *codes):
        with self.assertRaises(M7Error) as caught:
            call()
        if codes:
            self.assertIn(caught.exception.code, codes, caught.exception.detail)
        self.assertEqual(self.world.listing(), self.before, "a refusal before consumption created something")
        return caught.exception

    def entry_refused(self, mutate, *codes, entry=None):
        entry = copy.deepcopy(self.world.entry if entry is None else entry)
        mutate(entry)
        return self.refused(lambda: selection.assert_active_entry(entry, self.world.temp), *codes)

    def launch_refused(self, mutate, *codes):
        entry = copy.deepcopy(self.world.entry)
        mutate(entry)
        return self.refused(lambda: self.world.launch(config_bytes=self.world.config_bytes_for(entry)), *codes)


# ------------------------------------------------------------------ the inactive gate


class InactiveGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="m7selinactive")
        self.addCleanup(shutil.rmtree, self.temp, True)
        with open(CONFIG_FILE, "rb") as handle:
            self.inactive_bytes = handle.read()
        self.calls = []

        def forbidden(name):
            def raiser(*arguments, **keywords):
                self.calls.append(name)
                raise AssertionError("the inactive gate reached " + name)

            return raiser

        self.forbidden = forbidden

    def deps(self, read_log):
        def read_bytes(path):
            read_log.append(path)
            return self.inactive_bytes

        return selection.SelectionDependencies(
            read_bytes=read_bytes,
            lstat=self.forbidden("lstat"),
            listdir=self.forbidden("listdir"),
            realpath=self.forbidden("realpath"),
            environ=RaisingMapping(),
            git=self.forbidden("git"),
            git_blob=self.forbidden("git blob"),
            executable="/nonexistent/python",
        )

    def test_the_inactive_configuration_refuses_before_every_external_effect(self):
        for identifier in (IDENTIFIER, "m7_final_selection_other", "m7_final_selection_retry_2"):
            reads = []
            with mock.patch.object(os, "mkdir", self.forbidden("mkdir")), mock.patch.object(os, "makedirs", self.forbidden("makedirs")), \
                    mock.patch.object(subprocess, "run", self.forbidden("subprocess.run")), mock.patch.object(subprocess, "Popen", self.forbidden("Popen")), \
                    mock.patch.object(subprocess, "check_output", self.forbidden("check_output")), \
                    mock.patch.object(common, "run_git", self.forbidden("run_git")), mock.patch.object(common, "run_trusted_tool", self.forbidden("tool")), \
                    mock.patch.object(common, "consume_output_directory", self.forbidden("consume")), \
                    mock.patch.object(common, "assert_parent_environment", self.forbidden("environment")), \
                    mock.patch.object(common, "pin_process_path", self.forbidden("pin path")), \
                    mock.patch.object(selection, "live_repository_observation", self.forbidden("repository")), \
                    mock.patch.object(selection, "read_bound_inputs", self.forbidden("inputs")), \
                    mock.patch.object(selection, "assert_launch_interpreter", self.forbidden("interpreter")):
                with self.assertRaises(M7Error, msg=identifier) as caught:
                    selection.launch_authorised_selection(identifier, run_root=self.temp, deps=self.deps(reads))
                self.assertEqual(caught.exception.code, "execution_not_authorised")
            self.assertEqual(reads, [selection.CONFIG_PATH], "only the tracked configuration is read")
        self.assertEqual(self.calls, [])
        self.assertEqual(os.listdir(self.temp), [])

    def test_a_malformed_or_foreign_id_is_refused_before_even_the_configuration_is_read(self):
        long_id = "m7_final_selection_" + "x" * 200
        for bad in (
            "", "bad", None, 7, ["m7_final_selection_a"], long_id, "M7_FINAL_SELECTION_UNIT", "m7_final_selection\n", "m7_final_selection x",
            "m7_final_selection/../x", "m7_final_selection_x\x00", "m7_unit_seed43_gpu1", "m7_unit_seed44_epoch2_candidate", "m7_seed43_final_selection",
            "m7_final_selection_seed44", "final_selection", "m7_final", "../m7_final_selection_x",
        ):
            reads = []
            with self.assertRaises(M7Error, msg=repr(bad)) as caught:
                selection.launch_authorised_selection(bad, run_root=self.temp, deps=self.deps(reads))
            self.assertEqual(caught.exception.code, "cli_argument_rejected", repr(bad))
            self.assertEqual(reads, [])
        self.assertEqual(os.listdir(self.temp), [])

    def test_the_command_line_accepts_only_help_schema_and_an_authorisation_id(self):
        for arguments in (
            ["--authorisation-id"], ["--authorisation-id", "bad"], ["--authorisation-id", IDENTIFIER, "--seed", "43"], ["--seed", "43"],
            ["--manifest", "/x"], ["--manifest-path", "/x/m7_replicate_manifest.json"], ["--epochs", "5"], ["--checkpoint", "/x"],
            ["--checkpoint-path", "/x"], ["--output", "/x"], ["--output-directory", "/x"], ["--learning-rate", "1e-3"], ["--help", "--schema"],
            ["--schema", "--help"], ["--authorisation-id", IDENTIFIER, "--authorisation-id", IDENTIFIER], ["--config", "/x"], [IDENTIFIER], [],
        ):
            with self.assertRaises(M7Error, msg=arguments) as caught:
                selection.production_main(arguments, stdout=type("S", (), {"write": lambda self, text: None})())
            self.assertEqual(caught.exception.code, "cli_argument_rejected", arguments)
            self.assertEqual(selection.main(arguments), 2)

    def test_the_real_command_line_refuses_the_inactive_configuration(self):
        refused = subprocess.run(
            [sys.executable, "-B", MODULE_FILE, "--authorisation-id", IDENTIFIER], capture_output=True, text=True, cwd=self.temp,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(refused.returncode, 2)
        self.assertTrue(refused.stderr.startswith("execution_not_authorised"), refused.stderr)
        for arguments, expected in ((["--help"], 0), (["--schema"], 0), (["--manifest", "/x"], 2), (["--seed", "43"], 2), (["--authorisation-id", "bad"], 2)):
            completed = subprocess.run([sys.executable, "-B", MODULE_FILE] + arguments, capture_output=True, text=True, cwd=self.temp)
            self.assertEqual(completed.returncode, expected, arguments)
        schema = json.loads(subprocess.run([sys.executable, "-B", MODULE_FILE, "--schema"], capture_output=True, text=True, cwd=self.temp).stdout)
        self.assertEqual(schema["entry_keys"], list(selection.ACTIVE_ENTRY_KEYS))
        self.assertEqual(schema["authorisation_schema"], selection.authorisation_schema())
        self.assertEqual(os.listdir(self.temp), [])

    def test_the_checked_in_configuration_is_inactive_with_no_live_binding(self):
        text = self.inactive_bytes.decode("utf-8")
        config = common.load_config_bytes(self.inactive_bytes)
        self.assertTrue(selection.assert_inactive_text(text))
        self.assertTrue(selection.assert_inactive_configuration(config))
        self.assertEqual(selection.classify_configuration(config), "inactive")
        self.assertEqual(config["authorisation_entries"], [])
        self.assertIs(config["consumable_by_executable_workflow"], False)
        self.assertEqual(config["document_status"], "M7_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED")
        self.assertEqual(config["execution"], {"authorised": False, "biological_paths_permitted": False, "gpu_identity_bound": False})
        self.assertEqual((config["schema_version"], config["manifest_schema_version"]), (selection.SCHEMA_VERSION, selection.MANIFEST_SCHEMA_VERSION))
        for token in ("GPU-", "/home/", "/tmp/", "CUDA_VISIBLE_DEVICES", "authorization_commit", "authorised: true", "consumable_by_executable_workflow: true"):
            self.assertNotIn(token, text)
        keys = {str(key) for key, _value in common.walk(config)}
        for key in ("output_directory", "evidence_directory", "authorisation_timestamp", "gpu_uuid", "pci_bus", "interpreter", "ld_library_path", "replicate_manifests", "deviation_id"):
            self.assertNotIn(key, keys)
        for mutate in (
            lambda c: c.update(consumable_by_executable_workflow=True),
            lambda c: c.update(document_status=selection.ACTIVE_DOCUMENT_STATUS),
            lambda c: c["execution"].update(authorised=True),
            lambda c: c["execution"].update(gpu_identity_bound=True),
            lambda c: c.update(authorisation_entries=[{}]),
            lambda c: c.update(authorization_commit=helpers.HEAD),
            lambda c: c["authorisation_schema"].update(entries_exactly=2),
            lambda c: c.update(schema_version="m7-final-selection-config-1"),
            lambda c: c.update(manifest_schema_version="m7-final-selection-manifest-1"),
        ):
            changed = copy.deepcopy(config)
            mutate(changed)
            with self.assertRaises(M7Error):
                selection.assert_inactive_configuration(changed)

    def test_the_other_m7_configurations_and_the_m6_blobs_stay_inactive(self):
        replicate = contract.load_config_bytes(helpers.inactive_replicate_bytes())
        self.assertTrue(contract.assert_inactive_configuration(replicate))
        self.assertEqual(replicate["authorisation_entries"], [])
        with open(os.path.join(ROOT, "config/experiments/D1_candidate_guardrails.yaml"), "rb") as handle:
            raw = handle.read()
        config = common.load_config_bytes(raw)
        self.assertTrue(guardrails.assert_inactive_configuration(config))
        self.assertEqual(config["authorisation_entries"], [])
        self.assertIs(config["consumable_by_executable_workflow"], False)
        with open(os.path.join(ROOT, "config/experiments/D1_final_replicates.yaml"), "rb") as handle:
            live = common.load_config_bytes(handle.read())
        self.assertEqual(live["document_status"], contract.ACTIVE_DOCUMENT_STATUS)
        self.assertIn("seed44", live["authorisation_entries"][0]["authorisation_id"])
        self.assertEqual(helpers.git_blob_id(os.path.join(ROOT, "config/experiments/D1_diffusion_pilot.yaml")), helpers.M6_PILOT_YAML_BLOB)
        self.assertEqual(helpers.git_blob_id(os.path.join(ROOT, "config/experiments/D1_update21_diagnostic_generation.yaml")), helpers.M6_DIAGNOSTIC_YAML_BLOB)


# ------------------------------------------------------------------ exact active schema


class ActiveSchemaTests(Case):
    def test_a_well_formed_two_seed_entry_is_accepted(self):
        entry = selection.assert_active_configuration(common.load_config_bytes(self.world.config_bytes), self.world.temp)
        self.assertEqual(entry["authorisation_id"], IDENTIFIER)
        self.assertEqual([row["seed"] for row in entry["replicate_manifests"]], [43, 44])
        self.assertEqual([(row["seed"], row["epoch"]) for row in entry["guardrail_manifests"]], [(43, 3), (43, 5), (44, 4)])
        self.assertIsNone(entry["deviation"])

    def test_every_entry_key_is_required_and_no_other_key_is_allowed(self):
        for key in selection.ACTIVE_ENTRY_KEYS:
            self.entry_refused(lambda e, key=key: e.pop(key), "authorisation_shape_invalid")
        self.entry_refused(lambda e: e.update(extra=1), "authorisation_shape_invalid")
        self.entry_refused(lambda e: e.update(authorization_commit=helpers.HEAD), "authorisation_shape_invalid")
        self.entry_refused(lambda e: e.update(physical_gpu_index=1), "authorisation_shape_invalid")
        self.entry_refused(lambda e: e.update(interpreter={}), "authorisation_shape_invalid")

    def test_status_single_use_scope_and_session_are_exact(self):
        for mutate, codes in (
            (lambda e: e.update(activation_status="inactive_no_authorisation"), ("authorisation_inactive",)),
            (lambda e: e.update(consumed=True), ("authorisation_inactive",)),
            (lambda e: e.update(single_use=False), ("authorization_reuse",)),
            (lambda e: e.update(reuse_permitted=True), ("authorization_reuse",)),
            (lambda e: e.update(phase="M7_D1_candidate_guardrail"), ("authorisation_scope_invalid",)),
            (lambda e: e.update(scope="single_use_m7_d1_replicate_seed_43"), ("authorisation_scope_invalid",)),
            (lambda e: e.update(permitted_roles=list(selection.ACTIVE_ROLES) + ["REF"]), ("authorisation_scope_invalid",)),
            (lambda e: e.update(permitted_roles=list(selection.ACTIVE_ROLES) + ["EVAL"]), ("authorisation_scope_invalid",)),
            (lambda e: e.update(permitted_roles=list(selection.ACTIVE_ROLES) + ["VALIDATION_CSV"]), ("authorisation_scope_invalid",)),
            (lambda e: e.update(permitted_roles=["SEALED_REPLICATE_MANIFEST"]), ("authorisation_scope_invalid",)),
            (lambda e: e.update(permitted_roles=list(guardrails.ACTIVE_ROLES)), ("authorisation_scope_invalid",)),
            (lambda e: e["session"].update(resume_permitted=True), ("authorisation_scope_invalid",)),
            (lambda e: e["session"].update(wall_clock_expiry=TIMESTAMP), ("authorisation_scope_invalid",)),
            (lambda e: e["session"].update(pattern="other"), ("authorisation_scope_invalid",)),
            (lambda e: e["session"].update(consumption_event="other"), ("authorisation_scope_invalid",)),
            (lambda e: e["session"].pop("pattern"), ("authorisation_shape_invalid",)),
        ):
            self.entry_refused(mutate, *codes)

    def test_commits_timestamp_and_hashes_are_exact(self):
        other = "c" * 40
        for mutate, codes in (
            (lambda e: e.update(authorization_parent_commit=other), ("authorisation_commit_invalid",)),
            (lambda e: e.update(executing_implementation_commit=other), ("authorisation_commit_invalid",)),
            (lambda e: e.update(authorization_parent_commit="abc", executing_implementation_commit="abc"), ("authorisation_commit_invalid",)),
            (lambda e: e.update(authorisation_timestamp="2026-10-09 09:00"), ("authorisation_field_missing",)),
            (lambda e: e.update(authorisation_timestamp="2026-10-09T09:00:00"), ("authorisation_field_missing",)),
            (lambda e: e.update(authorisation_timestamp=None), ("authorisation_field_missing",)),
            (lambda e: e.update(implementation_config_sha256="short"), ("provenance_mismatch",)),
            (lambda e: e["implementation_file_hashes"].pop(selection.MODULE_RELATIVE), ("provenance_mismatch",)),
            (lambda e: e["implementation_file_hashes"].update(extra=digest("x")), ("provenance_mismatch",)),
            (lambda e: e["implementation_file_hashes"].update({selection.MODULE_RELATIVE: "nothex"}), ("provenance_mismatch",)),
        ):
            self.entry_refused(mutate, *codes)

    def test_the_output_directory_is_the_exact_new_direct_child_named_by_the_id(self):
        for mutate in (
            lambda e: e.update(output_directory="relative/" + IDENTIFIER, evidence_directory="relative/" + IDENTIFIER),
            lambda e: e.update(output_directory=self.world.temp + "/" + IDENTIFIER + "/", evidence_directory=self.world.temp + "/" + IDENTIFIER + "/"),
            lambda e: e.update(output_directory="/elsewhere/" + IDENTIFIER, evidence_directory="/elsewhere/" + IDENTIFIER),
            lambda e: e.update(output_directory=self.world.temp + "/nested/" + IDENTIFIER, evidence_directory=self.world.temp + "/nested/" + IDENTIFIER),
            lambda e: e.update(output_directory=self.world.temp + "/m7_final_selection_other", evidence_directory=self.world.temp + "/m7_final_selection_other"),
            lambda e: e.update(evidence_directory=self.world.temp + "/m7_final_selection_other"),
            lambda e: e.update(output_directory=self.world.temp + "/../" + IDENTIFIER, evidence_directory=self.world.temp + "/../" + IDENTIFIER),
            lambda e: e.update(output_directory=None, evidence_directory=None),
        ):
            self.entry_refused(mutate, "execution_not_authorised", "authorisation_scope_invalid", "sibling_evidence_access")

    def test_the_replicate_manifest_rows_are_exact(self):
        row = lambda e, index=0: e["replicate_manifests"][index]
        for mutate, codes in (
            (lambda e: e.update(replicate_manifests=[]), ("authorisation_shape_invalid",)),
            (lambda e: e.update(replicate_manifests=e["replicate_manifests"] * 2), ("authorisation_shape_invalid",)),
            (lambda e: e.update(replicate_manifests=[e["replicate_manifests"][0], e["replicate_manifests"][0]]), ("selection_invalid",)),
            (lambda e: e.update(replicate_manifests=[e["replicate_manifests"][1]]), ("selection_invalid",)),
            (lambda e: e.update(replicate_manifests=list(reversed(e["replicate_manifests"]))), ("selection_invalid",)),
            (lambda e: row(e).update(seed=42), ("unexpected_seed",)),
            (lambda e: row(e).update(seed=45), ("unexpected_seed",)),
            (lambda e: row(e).update(seed=1), ("unexpected_seed",)),
            (lambda e: row(e).update(seed=True), ("unexpected_seed",)),
            (lambda e: row(e).update(seed="43"), ("unexpected_seed",)),
            (lambda e: row(e).update(seed=43.0), ("unexpected_seed",)),
            (lambda e: row(e).update(bytes=0), ("authorisation_field_missing",)),
            (lambda e: row(e).update(bytes=-5), ("authorisation_field_missing",)),
            (lambda e: row(e).update(bytes=True), ("authorisation_field_missing",)),
            (lambda e: row(e).update(bytes="100"), ("authorisation_field_missing",)),
            (lambda e: row(e).update(sha256="short"), ("authorisation_field_missing",)),
            (lambda e: row(e).update(sha256=row(e)["sha256"].upper()), ("authorisation_field_missing",)),
            (lambda e: row(e).update(extra=1), ("authorisation_shape_invalid",)),
            (lambda e: row(e).pop("path"), ("authorisation_shape_invalid",)),
            (lambda e: row(e).update(epoch=1), ("authorisation_shape_invalid",)),
            (lambda e: row(e, 1).update(sha256=row(e)["sha256"]), ("selection_invalid",)),
        ):
            self.entry_refused(mutate, *codes)

    def test_the_guardrail_manifest_rows_are_exact(self):
        row = lambda e, index=0: e["guardrail_manifests"][index]
        for mutate, codes in (
            (lambda e: e.update(guardrail_manifests=[]), ("authorisation_shape_invalid",)),
            (lambda e: e.update(guardrail_manifests=e["guardrail_manifests"] * 4), ("authorisation_shape_invalid", "selection_invalid")),
            (lambda e: e.update(guardrail_manifests=[row(e), row(e)]), ("selection_invalid",)),
            (lambda e: e.update(guardrail_manifests=list(reversed(e["guardrail_manifests"]))), ("selection_invalid",)),
            (lambda e: row(e).update(epoch=0), ("selection_invalid",)),
            (lambda e: row(e).update(epoch=6), ("selection_invalid",)),
            (lambda e: row(e).update(epoch=True), ("selection_invalid",)),
            (lambda e: row(e).update(epoch="3"), ("selection_invalid",)),
            (lambda e: row(e).update(epoch=3.0), ("selection_invalid",)),
            (lambda e: row(e).update(seed=45), ("unexpected_seed",)),
            (lambda e: row(e).pop("epoch"), ("authorisation_shape_invalid",)),
            (lambda e: row(e).update(extra=1), ("authorisation_shape_invalid",)),
            (lambda e: row(e).update(bytes=0), ("authorisation_field_missing",)),
            (lambda e: row(e).update(sha256="x"), ("authorisation_field_missing",)),
            (lambda e: row(e, 1).update(sha256=row(e, 0)["sha256"]), ("selection_invalid",)),
        ):
            self.entry_refused(mutate, *codes)

    def test_a_guardrail_row_for_an_unbound_seed_is_refused(self):
        entry = copy.deepcopy(self.world.entry)
        entry["replicate_manifests"] = entry["replicate_manifests"][:1]
        self.entry_refused(lambda e: None, "selection_invalid", "authorisation_scope_invalid", entry=entry)

    def test_the_deviation_binding_follows_the_seed_plan(self):
        self.entry_refused(lambda e: e.update(deviation={"x": 1}), "selection_invalid", "authorisation_shape_invalid")
        record = json.loads(support.deviation_blob(*self.world.scenarios[43][::2]).decode("utf-8"))
        self.entry_refused(lambda e: e.update(deviation=record), "selection_invalid")

    def test_the_document_level_schema_is_exact(self):
        good = common.load_config_bytes(self.world.config_bytes)
        self.assertTrue(selection.assert_active_configuration(good, self.world.temp))
        import yaml

        def refuse(mutate, *codes):
            config = copy.deepcopy(good)
            mutate(config)
            with self.assertRaises(M7Error) as caught:
                selection.assert_active_configuration(common.load_config_bytes(yaml.safe_dump(config, sort_keys=True).encode("utf-8")), self.world.temp)
            if codes:
                self.assertIn(caught.exception.code, codes, caught.exception.detail)

        refuse(lambda c: c.update(document_status=selection.DOCUMENT_STATUS), "authorisation_inactive")
        refuse(lambda c: c.update(consumable_by_executable_workflow=False), "authorisation_inactive")
        refuse(lambda c: c["execution"].update(authorised=False), "authorisation_inactive")
        refuse(lambda c: c["execution"].update(gpu_identity_bound=True), "authorisation_inactive")
        refuse(lambda c: c["execution"].update(biological_paths_permitted=True), "authorisation_inactive")
        refuse(lambda c: c.update(authorisation_entries=[]), "authorisation_shape_invalid")
        refuse(lambda c: c.update(authorisation_entries=c["authorisation_entries"] * 2), "authorisation_shape_invalid")
        refuse(lambda c: c.update(authorisation_entries={}), "authorisation_shape_invalid")
        refuse(lambda c: c.update(authorization_commit=helpers.HEAD), "authorisation_commit_invalid", "authorisation_shape_invalid")
        refuse(lambda c: c.update(extra=1), "authorisation_shape_invalid")
        refuse(lambda c: c.update(schema_version="m7-final-selection-config-1"), "authorisation_scope_invalid")
        refuse(lambda c: c.update(manifest_schema_version="m7-final-selection-manifest-1"), "authorisation_scope_invalid")
        refuse(lambda c: c.update(experiment_id="D1_final_replicates"), "authorisation_scope_invalid")
        refuse(lambda c: c.update(rnagenesis_commit="f" * 40), "provenance_mismatch")
        refuse(lambda c: c.update(created_against_mres_commit="f" * 40), "provenance_mismatch")
        refuse(lambda c: c["allowed_seed_plan"].update(target_seeds=[43]), "authorisation_scope_invalid")
        refuse(lambda c: c["selection_rules"].update(ranking_rule="best_epoch"), "authorisation_scope_invalid")
        refuse(lambda c: c["final_manifest"]["closure"].update(m7_complete=True), "authorisation_scope_invalid")
        refuse(lambda c: c["m8_boundary"].update(total_raw_d1_attempts=1), "authorisation_scope_invalid")
        refuse(lambda c: c["authorisation_schema"].update(entries_exactly=2), "authorisation_scope_invalid")

    def test_an_unknown_but_well_formed_id_fails_closed_before_the_environment_is_inspected(self):
        for identifier in ("m7_final_selection_other", "m7_final_selection_unit_2", "m7_final_selection"):
            accessed = []
            deps = self.world.deps(environ=RaisingMapping(), lstat=lambda p: accessed.append(p) or os.lstat(p), listdir=lambda p: accessed.append(p) or [])
            with self.assertRaises(M7Error, msg=identifier) as caught:
                self.world.launch(identifier=identifier, deps=deps)
            self.assertEqual(caught.exception.code, "authorisation_field_missing")
            self.assertEqual(accessed, [])
            self.assertEqual(self.world.listing(), self.before)

    def test_the_manifest_path_text_is_judged_before_any_filesystem_access(self):
        world = self.world
        good = world.entry["replicate_manifests"][0]["path"]
        run_id = os.path.basename(os.path.dirname(good))
        name = selection.replicate.SUCCESS_MANIFEST_NAME
        candidates = {
            "relative": "relative/" + run_id + "/" + name,
            "traversal": world.temp + "/" + run_id + "/../" + run_id + "/" + name,
            "trailing slash": good + "/",
            "double slash": world.temp + "//" + run_id + "/" + name,
            "backslash": world.temp + "\\" + run_id + "\\" + name,
            "other root": "/elsewhere/" + run_id + "/" + name,
            "the real run root": common.RUN_ROOT + "/" + run_id + "/" + name,
            "REF token": world.temp + "/m7_unit_ref_seed43_gpu1/" + name,
            "EVAL token": world.temp + "/m7_unit_seed43_eval_gpu1/" + name,
            "REF csv": world.temp + "/" + run_id + "/ref.csv",
            "M6 evidence": world.temp + "/m6_d1_diffusion_pilot_attempt6/" + name,
            "M6 checkpoint": world.temp + "/" + run_id + "/seed-42__update-21__x/" + name,
            "checkpoint depth": good.replace(name, "checkpoint/" + name),
            "weight file": world.temp + "/" + run_id + "/unet/diffusion_pytorch_model.safetensors",
            "another file name": world.temp + "/" + run_id + "/train.csv",
            "run root file": world.temp + "/" + name,
            "data root": "/home/laura/rnagenesis-mres-data/train.txt",
            "RNAGenesis asset": "/home/laura/RNAGenesis/models/autoencoder/encoder/model.safetensors",
            "sibling seed": good.replace("seed43", "seed44"),
            "candidate directory": world.temp + "/m7_unit_seed43_epoch3_candidate/" + name,
            "output directory": world.output + "/" + name,
            "empty": "",
            "NUL": good + "\x00",
            "none": None,
        }
        for label, path in candidates.items():
            for row_index, kind in ((0, "replicate_manifests"),):
                entry = copy.deepcopy(world.entry)
                entry[kind][row_index]["path"] = path
                accessed = []
                deps = world.deps(read_bytes=lambda p: accessed.append(p) or b"", lstat=lambda p: accessed.append(p) or os.lstat(p), listdir=lambda p: accessed.append(p) or [])
                with self.assertRaises(M7Error, msg=label):
                    world.launch(config_bytes=world.config_bytes_for(entry), deps=deps)
                self.assertEqual(accessed, [], label)
                self.assertEqual(world.listing(), self.before, label)
        guardrail_good = world.entry["guardrail_manifests"][0]["path"]
        for label, path in {
            "wrong epoch": guardrail_good.replace("epoch3", "epoch4"),
            "replicate directory": good,
            "wrong name": guardrail_good.replace(guardrails.SUCCESS_MANIFEST_NAME, name),
            "checkpoint": guardrail_good.replace(guardrails.SUCCESS_MANIFEST_NAME, "unet/config.json"),
            "other seed": guardrail_good.replace("seed43", "seed44"),
        }.items():
            entry = copy.deepcopy(world.entry)
            entry["guardrail_manifests"][0]["path"] = path
            with self.assertRaises(M7Error, msg=label):
                selection.assert_active_entry(entry, world.temp)


class OneSeedSchemaTests(Case):
    outcomes43 = (True,)
    two_seeds = False

    def test_a_one_seed_entry_carries_the_sealed_deviation_and_validates_it_against_the_seed_43_row(self):
        entry = selection.assert_active_configuration(common.load_config_bytes(self.world.config_bytes), self.world.temp)
        self.assertEqual([row["seed"] for row in entry["replicate_manifests"]], [43])
        self.assertEqual(entry["deviation"]["omitted_seed"], 44)
        self.assertEqual(entry["deviation"]["seed_43_replicate_manifest_sha256"], entry["replicate_manifests"][0]["sha256"])
        self.entry_refused(lambda e: e.update(deviation=None), "selection_invalid")
        self.entry_refused(lambda e: e["deviation"].update(omitted_seed=43), "selection_invalid")
        self.entry_refused(lambda e: e["deviation"].update(sealed=False), "selection_invalid")
        self.entry_refused(lambda e: e["deviation"].update(seed_43_replicate_manifest_sha256=digest("another")), "selection_invalid")
        self.entry_refused(lambda e: e["deviation"].pop("sealed_at"), "selection_invalid")
        self.entry_refused(lambda e: e.update(replicate_manifests=[dict(e["replicate_manifests"][0], seed=44, path=e["replicate_manifests"][0]["path"].replace("seed43", "seed44"))]), "selection_invalid")

    def test_nothing_in_the_launcher_decides_that_seed_44_is_omitted(self):
        source = open(MODULE_FILE).read()
        for fragment in ("omit_seed_44", "decide_deviation", "time.time(", "datetime.now", "datetime.datetime.now", "utcnow"):
            self.assertNotIn(fragment, source)


# ------------------------------------------------------------------ authorisation-only repository delta


class RepositoryBindingTests(Case):
    def refuse_observation(self, *codes, **changes):
        observation = self.world.make_observation(**changes)
        return self.refused(lambda: self.world.launch(observation=observation), *codes)

    def test_the_authorisation_only_delta_is_accepted_and_nothing_else(self):
        config = common.load_config_bytes(self.world.config_bytes)
        head = selection.assert_repository_binding(config, self.world.entry, self.world.observation)
        self.assertEqual(head, helpers.HEAD)
        paths = selection.assert_selection_delta(self.world.inactive, config)
        self.assertEqual(sorted(paths), sorted(selection.PERMITTED_ACTIVATION_PATHS))

    def test_a_delta_beyond_the_permitted_activation_paths_is_refused(self):
        config = common.load_config_bytes(self.world.config_bytes)
        for mutate in (
            lambda c: c["execution"].update(gpu_identity_bound=True),
            lambda c: c["execution"].update(biological_paths_permitted=True),
            lambda c: c["m8_boundary"].update(total_raw_d1_attempts=1),
            lambda c: c.update(schema_version="other"),
            lambda c: c["selection_rules"].update(ranking_rule="best_epoch"),
            lambda c: c.update(extra=1),
        ):
            changed = copy.deepcopy(config)
            mutate(changed)
            with self.assertRaises(M7Error, msg=str(mutate)) as caught:
                selection.assert_selection_delta(self.world.inactive, changed)
            self.assertEqual(caught.exception.code, "authorisation_delta_invalid")
        with self.assertRaises(M7Error):
            selection.assert_selection_delta(self.world.inactive, copy.deepcopy(self.world.inactive))
        # The replicate binding alone would allow a GPU flag; this stage does not.
        gpu = copy.deepcopy(config)
        gpu["execution"]["gpu_identity_bound"] = True
        self.assertTrue(contract.assert_authorisation_delta(self.world.inactive, gpu))
        with self.assertRaises(M7Error):
            selection.assert_selection_delta(self.world.inactive, gpu)

    def test_a_changed_file_outside_the_configuration_is_refused_before_consumption(self):
        self.refuse_observation("authorisation_delta_invalid", changed_files=[selection.CONFIG_RELATIVE, "scripts/modelling/m7_selection.py"])
        self.refuse_observation("authorisation_delta_invalid", changed_files=["scripts/modelling/m7_selection.py"])
        self.refuse_observation("authorisation_delta_invalid", changed_files=[])
        self.refuse_observation("authorisation_delta_invalid", changed_files=["config/experiments/D1_final_replicates.yaml"])

    def test_the_parent_configuration_must_differ_only_by_the_permitted_paths(self):
        tampered = copy.deepcopy(self.world.inactive)
        tampered["m8_boundary"]["total_raw_d1_attempts"] = 1
        self.refuse_observation("authorisation_delta_invalid", implementation_config=tampered)
        self.refuse_observation("provenance_mismatch", implementation_config_bytes=self.world.raw + b"#")

    def test_the_repository_pins_and_a_clean_tracked_tree_are_required(self):
        self.refuse_observation("authorisation_commit_invalid", mres_parents=[])
        self.refuse_observation("authorisation_commit_invalid", mres_parents=[helpers.PARENT, "c" * 40])
        self.refuse_observation("authorisation_commit_invalid", mres_head=helpers.PARENT)
        self.refuse_observation("authorisation_commit_invalid", mres_parents=["c" * 40])
        self.refuse_observation("provenance_mismatch", mres_branch="feature")
        self.refuse_observation("provenance_mismatch", mres_origin_main="c" * 40)
        for porcelain in (" M scripts/modelling/m7_selection.py\n", "M  scripts/modelling/m7_common.py\n", "?? scripts/new.py\n", " M config/experiments/D1_final_selection.yaml\n"):
            self.refuse_observation(mres_porcelain=porcelain)
        self.refuse_observation("provenance_mismatch", rnagenesis_head="c" * 40)
        self.refuse_observation("provenance_mismatch", rnagenesis_branch="main")
        self.refuse_observation(rnagenesis_directory_porcelain=" M models/diffusion/x.py\n")
        self.refuse_observation(rnagenesis_file_porcelain=" M models/diffusion/x.py\n")
        drifted = dict(self.world.hashes)
        drifted[selection.MODULE_RELATIVE] = digest("tampered module")
        self.refuse_observation("provenance_mismatch", file_sha256_working_tree=drifted)
        self.refuse_observation("provenance_mismatch", file_sha256_at_parent=drifted)
        self.refuse_observation("provenance_mismatch", file_sha256_working_tree={})

    def test_the_live_observation_uses_only_the_injected_git_and_matches_the_binding(self):
        raw = self.world.raw
        calls = []
        m5 = common.m6_contract().m5_contract()

        def git(repo, args):
            calls.append((repo, tuple(args)))
            key = (repo, tuple(args))
            table = {
                (common.MRES_ROOT, ("rev-parse", "HEAD")): helpers.HEAD + "\n",
                (common.MRES_ROOT, ("rev-parse", "HEAD^@")): helpers.PARENT + "\n",
                (common.MRES_ROOT, ("rev-parse", "--abbrev-ref", "HEAD")): "main\n",
                (common.MRES_ROOT, ("rev-parse", "origin/main")): helpers.PARENT + "\n",
                (common.MRES_ROOT, ("status", "--porcelain=v1", "--untracked-files=all")): "",
                (common.MRES_ROOT, ("diff", "--name-only", helpers.PARENT, "HEAD")): selection.CONFIG_RELATIVE + "\n",
                (common.RNAGENESIS_ROOT, ("rev-parse", "--abbrev-ref", "HEAD")): common.RNAGENESIS_BRANCH + "\n",
                (common.RNAGENESIS_ROOT, ("rev-parse", "HEAD")): common.RNAGENESIS_COMMIT + "\n",
                (common.RNAGENESIS_ROOT, ("status", "--porcelain=v1")): m5.reviewed_rnagenesis_porcelain(),
                (common.RNAGENESIS_ROOT, ("status", "--porcelain=v1", "--untracked-files=all")): "?? .cache/huggingface/hub/version.txt\n",
            }
            return table[key]

        def git_blob(spec):
            parent, _, relative = spec.partition(":")
            self.assertEqual(parent, helpers.PARENT)
            return raw if relative == selection.CONFIG_RELATIVE else ("file:" + relative).encode("utf-8")

        def read_bytes(path):
            self.assertTrue(path.startswith(common.MRES_ROOT + "/"))
            return ("file:" + os.path.relpath(path, common.MRES_ROOT)).encode("utf-8")

        deps = self.world.deps(git=git, git_blob=git_blob, read_bytes=read_bytes)
        config = common.load_config_bytes(self.world.config_bytes)
        observation = selection.live_repository_observation(config, self.world.entry, deps)
        self.assertEqual(selection.assert_repository_binding(config, self.world.entry, observation), helpers.HEAD)
        for repo, args in calls:
            self.assertIn(repo, (common.MRES_ROOT, common.RNAGENESIS_ROOT))
            self.assertIn(args[0], ("rev-parse", "status", "diff"), "git is only asked to read")

    def test_the_default_git_is_the_absolute_fixed_executable(self):
        with mock.patch.object(common, "run_git", lambda repo, args: "x") as patched, mock.patch.object(common, "run_git_bytes", lambda repo, args: b"y"):
            deps = selection.SelectionDependencies()
            self.assertEqual(deps.git(common.MRES_ROOT, ["rev-parse", "HEAD"]), "x")
            self.assertEqual(deps.git_blob("a:b"), b"y")
        self.assertIs(selection.SelectionDependencies().git, selection._default_git)


# ------------------------------------------------------------------ the environment, interpreter and path


class EnvironmentTests(Case):
    def test_a_redirecting_or_credential_variable_is_refused_before_the_repository_is_observed(self):
        def explode(config, entry, deps):
            raise AssertionError("the repository was observed")

        with mock.patch.object(selection, "live_repository_observation", explode):
            for extra in ({"PYTHONPATH": "/x"}, {"LD_PRELOAD": "/x"}, {"GIT_DIR": "/x"}, {"HF_TOKEN": "t"}, {"AWS_SECRET_ACCESS_KEY": "t"}):
                self.refused(lambda extra=extra: self.world.launch(observation=None, deps=self.world.deps(environ=self.world.parent(**extra))), "environment_rejected")

    def test_the_launcher_must_run_under_the_pinned_interpreter(self):
        def explode(config, entry, deps):
            raise AssertionError("the repository was observed")

        with mock.patch.object(selection, "live_repository_observation", explode):
            for executable in ("/usr/bin/python3", "python3", "/tmp/hostile/python", ""):
                self.refused(lambda executable=executable: self.world.launch(observation=None, deps=self.world.deps(executable=executable)), "interpreter_rejected")
        self.assertTrue(selection.assert_launch_interpreter(self.world.deps(executable=common.PINNED_PYTHON)))

    def test_a_hostile_parent_path_is_replaced_by_the_fixed_path_and_never_reaches_a_subprocess(self):
        parent = self.world.parent(PATH=BAD_PARENT_PATH)
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("no subprocess")), mock.patch.object(subprocess, "Popen", side_effect=AssertionError("no subprocess")):
            self.world.launch(deps=self.world.deps(environ=parent))
        self.assertEqual(parent["PATH"], common.FIXED_CHILD_PATH)
        self.assertNotIn("hostile", json.dumps(parent))


# ------------------------------------------------------------------ bound input manifests


class InputBindingTests(Case):
    def setUp(self):
        super().setUp()
        self.originals = {}

    def rebind(self, kind, seed, epoch, blob, **row_changes):
        """Overwrite one bound file and rebind its size and hash, so only the new content is in question."""
        world = self.world
        path = world.paths[(kind, seed, epoch)]
        if path not in self.originals:
            with open(path, "rb") as handle:
                self.originals[path] = handle.read()
        with open(path, "wb") as handle:
            handle.write(blob)
        entry = copy.deepcopy(world.entry)
        rows = entry["replicate_manifests"] if kind == "replicate" else entry["guardrail_manifests"]
        row = next(item for item in rows if item["seed"] == seed and item.get("epoch") == epoch)
        row.update(bytes=len(blob), sha256=sha(blob))
        row.update(row_changes)
        return world.config_bytes_for(entry)

    def original(self, kind, seed, epoch=None):
        with open(self.world.paths[(kind, seed, epoch)], "rb") as handle:
            return handle.read()

    def relaunch_refused(self, config_bytes, *codes):
        try:
            return self.refused(lambda: self.world.launch(config_bytes=config_bytes), *codes)
        finally:
            for path, blob in self.originals.items():
                with open(path, "wb") as handle:
                    handle.write(blob)
            self.originals.clear()

    def test_the_intact_inputs_are_read_exactly_as_bound(self):
        inputs = selection.read_bound_inputs(self.world.entry, self.world.deps(), self.world.temp)
        self.assertEqual(len(inputs["replicates"]), 2)
        self.assertEqual(len(inputs["guardrails"]), 3)
        self.assertEqual([sha(blob) for blob in inputs["replicates"]], [row["sha256"] for row in self.world.entry["replicate_manifests"]])

    def test_a_wrong_size_or_hash_is_refused(self):
        for mutate in (
            lambda e: e["replicate_manifests"][0].update(bytes=e["replicate_manifests"][0]["bytes"] + 1),
            lambda e: e["replicate_manifests"][0].update(bytes=e["replicate_manifests"][0]["bytes"] - 1),
            lambda e: e["replicate_manifests"][0].update(sha256=digest("another")),
            lambda e: e["guardrail_manifests"][0].update(bytes=e["guardrail_manifests"][0]["bytes"] + 1),
            lambda e: e["guardrail_manifests"][0].update(sha256=digest("another")),
        ):
            self.launch_refused(mutate, "authorisation_evidence_mismatch")

    def test_altered_bytes_are_refused_even_when_the_length_is_unchanged(self):
        path = self.world.paths[("replicate", 43, None)]
        raw = self.original("replicate", 43)
        altered = bytearray(raw)
        altered[200] = ord("x") if altered[200] != ord("x") else ord("y")
        with open(path, "wb") as handle:
            handle.write(bytes(altered))
        self.refused(lambda: self.world.launch(), "authorisation_evidence_mismatch")

    def test_non_canonical_or_non_json_inputs_are_refused_even_when_their_hash_is_bound(self):
        parsed = json.loads(self.original("replicate", 43).decode("utf-8"))
        for raw in (
            json.dumps(parsed, indent=1).encode("utf-8"),
            json.dumps(parsed, sort_keys=True).encode("utf-8"),
            common.canonical_json(parsed).rstrip(b"\n"),
            common.canonical_json(parsed) + b"\n",
            b"[]\n",
            b"not json",
            b"{",
            b"",
            b"\xff\xfe",
        ):
            if raw == b"":
                config = self.rebind("replicate", 43, None, raw, bytes=1)
            else:
                config = self.rebind("replicate", 43, None, raw)
            self.relaunch_refused(config, "authorisation_evidence_mismatch")
        guardrail = json.loads(self.original("guardrail", 43, 3).decode("utf-8"))
        self.relaunch_refused(self.rebind("guardrail", 43, 3, json.dumps(guardrail, indent=1).encode("utf-8")), "authorisation_evidence_mismatch")

    def test_schema_drift_is_refused_even_when_rehashed(self):
        for kind, seed, epoch in (("replicate", 43, None), ("guardrail", 43, 3)):
            parsed = json.loads(self.original(kind, seed, epoch).decode("utf-8"))
            for label, mutate in (("extra key", lambda m: m.update(extra=1)), ("missing key", lambda m: m.pop("closure")), ("schema version", lambda m: m.update(schema_version="other"))):
                changed = copy.deepcopy(parsed)
                mutate(changed)
                self.relaunch_refused(self.rebind(kind, seed, epoch, common.canonical_json(changed)), "authorisation_evidence_mismatch", "incomplete_evidence_or_manifest", "guardrail_manifest_invalid")
                self.rebind(kind, seed, epoch, common.canonical_json(parsed))

    def test_identity_in_the_manifest_must_match_its_row_and_directory(self):
        # A fresh, valid seed-44 manifest (its digest is bound nowhere else) offered for the seed-43 row.
        fresh44 = support.scenario(44, MSE_B, [True], salt="fresh44")
        self.relaunch_refused(self.rebind("replicate", 43, None, fresh44[0]), "sibling_evidence_access")
        replicate43 = json.loads(self.original("replicate", 43).decode("utf-8"))
        changed = copy.deepcopy(replicate43)
        changed["run_id"] = "m7_unit_seed43_other"
        changed["authorisation"]["authorisation_id"] = "m7_unit_seed43_other"
        self.relaunch_refused(self.rebind("replicate", 43, None, common.canonical_json(changed)), "sibling_evidence_access")
        # Reusing another bound manifest's exact bytes is a duplicate digest and is refused earlier still.
        self.relaunch_refused(self.rebind("replicate", 43, None, self.original("replicate", 44)), "selection_invalid")

    def test_a_valid_manifest_of_another_candidate_cannot_be_substituted(self):
        fresh43 = support.scenario(43, MSE_A, [False, True], salt="fresh43")
        fresh44 = support.scenario(44, MSE_B, [True], salt="fresh44")
        # epoch 5 of a fresh seed-43 run offered for the epoch-3 row
        self.relaunch_refused(self.rebind("guardrail", 43, 3, fresh43[1][1]), "sibling_evidence_access")
        # a seed-44 candidate offered for a seed-43 row
        self.relaunch_refused(self.rebind("guardrail", 43, 5, fresh44[1][0]), "sibling_evidence_access")
        # a replicate manifest offered where a guardrail manifest is bound
        self.relaunch_refused(self.rebind("guardrail", 44, 4, fresh44[0]), "authorisation_evidence_mismatch")

    def test_a_missing_input_is_refused(self):
        os.remove(self.world.paths[("guardrail", 43, 3)])
        self.refused(lambda: self.world.launch(), "authorisation_evidence_mismatch")

    def test_a_symlink_leaf_ancestor_hard_link_and_non_regular_file_are_refused(self):
        world = self.world
        for kind, seed, epoch in (("replicate", 43, None), ("guardrail", 43, 3)):
            path = world.paths[(kind, seed, epoch)]
            directory = os.path.dirname(path)
            moved = path + ".moved"
            # a symlink leaf
            os.rename(path, moved)
            os.symlink(moved, path)
            self.refused(lambda: world.launch(), "authorisation_evidence_mismatch")
            os.remove(path)
            # a non-regular leaf (a FIFO is refused on lstat, without being opened)
            os.mkfifo(path)
            self.refused(lambda: world.launch(), "authorisation_evidence_mismatch")
            os.remove(path)
            # a directory in place of the file
            os.mkdir(path)
            self.refused(lambda: world.launch(), "authorisation_evidence_mismatch")
            os.rmdir(path)
            os.rename(moved, path)
            # a hard-linked leaf
            twin = world.temp + "_twin.json"
            os.link(path, twin)
            self.refused(lambda: world.launch(), "authorisation_evidence_mismatch")
            os.remove(twin)
            # a symlinked ancestor
            real = world.temp + "_real_" + os.path.basename(directory)
            os.rename(directory, real)
            os.symlink(real, directory)
            self.refused(lambda: world.launch(), "authorisation_evidence_mismatch")
            os.remove(directory)
            os.rename(real, directory)
            self.before = world.listing()
        self.assertTrue(world.launch())

    def test_a_file_that_changes_while_it_is_read_is_refused(self):
        world = self.world
        path = world.paths[("replicate", 43, None)]

        def touching(target):
            with open(target, "rb") as handle:
                data = handle.read()
            if target == path:
                os.utime(target, ns=(1, 1))
            return data

        self.refused(lambda: world.launch(deps=world.deps(read_bytes=touching)), "authorisation_evidence_mismatch")

        def growing(target):
            with open(target, "rb") as handle:
                data = handle.read()
            if target == path:
                with open(target, "ab") as extra:
                    extra.write(b" ")
            return data

        self.refused(lambda: world.launch(deps=world.deps(read_bytes=growing)), "authorisation_evidence_mismatch")
        self.assertEqual(world.listing(), self.before)

    def test_ref_eval_checkpoint_and_m6_derived_manifests_are_refused(self):
        guardrail = json.loads(self.original("guardrail", 43, 3).decode("utf-8"))
        for mutate in (
            lambda m: m["ref_eval_access"].update(ref_opened=True),
            lambda m: m["ref_eval_access"].update(eval_opened=True),
            lambda m: m["input_roles"].append("EVAL"),
            lambda m: m["input_roles"].append("REF"),
            lambda m: m["checkpoint"].update(weight_sha256=next(iter(common.M6_FORBIDDEN_WEIGHT_SHA256))),
        ):
            changed = copy.deepcopy(guardrail)
            mutate(changed)
            self.relaunch_refused(self.rebind("guardrail", 43, 3, common.canonical_json(changed)))
            self.rebind("guardrail", 43, 3, common.canonical_json(guardrail))
        replicate = json.loads(self.original("replicate", 43).decode("utf-8"))
        for mutate in (
            lambda m: m["ref_eval_access"].update(ref_opened=True),
            lambda m: m["data_roles"]["eval"].update(opened=True),
            lambda m: m["checkpoints"][0].update(weight_sha256=next(iter(common.M6_FORBIDDEN_WEIGHT_SHA256))),
        ):
            changed = copy.deepcopy(replicate)
            mutate(changed)
            self.relaunch_refused(self.rebind("replicate", 43, None, common.canonical_json(changed)))
            self.rebind("replicate", 43, None, common.canonical_json(replicate))

    def test_missing_extra_or_duplicate_guardrail_manifests_are_refused(self):
        world = self.world
        # a missing evaluated candidate leaves lazy evaluation incomplete
        self.launch_refused(lambda e: e["guardrail_manifests"].pop(0), "selection_invalid")
        self.launch_refused(lambda e: e["guardrail_manifests"].pop(1), "selection_invalid")
        # an unlisted extra manifest, evaluated after the first pass, is refused
        blob, blobs, manifest = world.scenarios[43]
        order = [item["epoch"] for item in manifest["validation_ranking"]["ranked_candidates"]]
        preceding = [
            {"epoch": order[0], "manifest_sha256": sha(blobs[0]), "outcome": "failed"},
            {"epoch": order[1], "manifest_sha256": sha(blobs[1]), "outcome": "failed"},
        ]
        extra = support.guardrail_blob(manifest, blob, order[2], True, 3, preceding)
        path = world.write(json.loads(extra.decode("utf-8"))["run_id"], extra, kind="guardrail")
        entry = copy.deepcopy(world.entry)
        entry["guardrail_manifests"].append({"bytes": len(extra), "epoch": order[2], "path": path, "seed": 43, "sha256": sha(extra)})
        entry["guardrail_manifests"].sort(key=lambda row: (row["seed"], row["epoch"]))
        self.before = world.listing()
        self.refused(lambda: world.launch(config_bytes=world.config_bytes_for(entry)), "selection_invalid")
        # a duplicate row for one candidate is refused at the schema
        self.entry_refused(lambda e: e["guardrail_manifests"].append(copy.deepcopy(e["guardrail_manifests"][0])), "selection_invalid")

    def test_one_seed_selection_without_its_deviation_or_seed_44_alone_cannot_run(self):
        self.launch_refused(lambda e: e.update(replicate_manifests=e["replicate_manifests"][1:]), "selection_invalid")
        self.launch_refused(lambda e: e.update(replicate_manifests=e["replicate_manifests"][:1]), "selection_invalid", "authorisation_scope_invalid")


# ------------------------------------------------------------------ consumption and execution


class ExecutionTests(Case):
    def written(self):
        directory = self.world.output
        names = sorted(os.listdir(directory))
        return names, directory

    def test_a_two_seed_selection_is_consumed_built_validated_and_written_atomically(self):
        progress = common.new_progress(None, "final_selection")
        manifest = self.world.launch(progress=progress)
        names, directory = self.written()
        self.assertEqual(names, [common.CONSUMPTION_RECORD_NAME, selection.SUCCESS_MANIFEST_NAME])
        self.assertFalse([name for name in names if name.endswith(".partial")])
        with open(os.path.join(directory, selection.SUCCESS_MANIFEST_NAME), "rb") as handle:
            written = handle.read()
        self.assertEqual(written, selection.final_selection_bytes(manifest))
        self.assertEqual(common.canonical_json(json.loads(written.decode("utf-8"))), written)
        replicates = [blob for _seed, (blob, _g, _m) in sorted(self.world.scenarios.items())]
        guardrail_blobs = [blob for _seed, (_b, blobs, _m) in sorted(self.world.scenarios.items()) for blob in blobs]
        self.assertTrue(selection.rebuild_matches(written, replicates, guardrail_blobs))
        self.assertTrue(selection.validate_final_selection_manifest(json.loads(written.decode("utf-8"))))
        self.assertEqual(manifest["selection_outcome"], "selected_set_complete")
        self.assertEqual([(item["seed"], item["epoch"]) for item in manifest["selected_set"]], [(43, 5), (44, 4)])
        self.assertIs(manifest["closure"]["human_gate_required"], True)
        self.assertIs(manifest["closure"]["m7_complete"], False)
        self.assertEqual(manifest["ref_eval_access"], {"eval_opened": False, "ref_opened": False})
        for key in ("ref_opened", "eval_opened", "validation_csv_opened", "m8_generation_performed"):
            self.assertIs(manifest["closure"][key], False)
        with open(os.path.join(directory, common.CONSUMPTION_RECORD_NAME), "rb") as handle:
            consumption = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(consumption["authorisation_id"], IDENTIFIER)
        self.assertEqual(consumption["authorization_commit"], helpers.HEAD)
        self.assertEqual(consumption["consumption_state"], "consumed_output_created")
        self.assertIs(consumption["reuse_permitted"], False)
        self.assertEqual(consumption["output_directory"], self.world.output)
        self.assertEqual(consumption["schema_version"], selection.CONSUMPTION_SCHEMA_VERSION)
        self.assertEqual(progress["stage"], "manifest_write")
        self.assertEqual(oct(os.stat(os.path.join(directory, selection.SUCCESS_MANIFEST_NAME)).st_mode & 0o777), "0o644")

    def test_the_selection_is_independent_of_the_row_order_the_files_were_read_in(self):
        first = self.world.launch()
        replicates = [blob for _seed, (blob, _g, _m) in sorted(self.world.scenarios.items(), reverse=True)]
        guardrail_blobs = [blob for _seed, (_b, blobs, _m) in sorted(self.world.scenarios.items(), reverse=True) for blob in reversed(blobs)]
        self.assertEqual(selection.final_selection_bytes(selection.build_final_selection(replicates, guardrail_blobs)), selection.final_selection_bytes(first))

    def test_the_bound_output_is_the_only_thing_created(self):
        self.world.launch()
        self.assertEqual(self.world.listing(), sorted(self.before + [IDENTIFIER]))

    def test_a_second_use_of_the_same_authorisation_is_refused_and_leaves_the_first_intact(self):
        self.world.launch()
        names, directory = self.written()
        with open(os.path.join(directory, selection.SUCCESS_MANIFEST_NAME), "rb") as handle:
            first = handle.read()
        for _ in range(2):
            with self.assertRaises(M7Error) as caught:
                self.world.launch()
            self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertEqual(self.written()[0], names)
        with open(os.path.join(directory, selection.SUCCESS_MANIFEST_NAME), "rb") as handle:
            self.assertEqual(handle.read(), first)

    def test_a_new_id_cannot_overwrite_an_existing_selection(self):
        self.world.launch()
        again = World(self.outcomes43, self.outcomes44, True, identifier="m7_final_selection_retry")
        self.addCleanup(again.close)
        # The retry's inputs live elsewhere; it shares the run root of the first world by construction below.
        entry = copy.deepcopy(self.world.entry)
        entry.update(authorisation_id="m7_final_selection_retry", output_directory=os.path.join(self.world.temp, "m7_final_selection_retry"))
        entry["evidence_directory"] = entry["output_directory"]
        with self.assertRaises(M7Error) as caught:
            self.world.launch(identifier="m7_final_selection_retry", config_bytes=self.world.config_bytes_for(entry))
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertFalse(os.path.lexists(entry["output_directory"]))

    def test_an_existing_output_a_symlink_or_an_unsafe_ancestor_is_refused_before_consumption(self):
        world = self.world
        os.mkdir(world.output)
        self.before = world.listing()
        self.refused(lambda: world.launch(), "authorization_reuse")
        os.rmdir(world.output)
        os.symlink(world.temp, world.output)
        self.before = world.listing()
        self.refused(lambda: world.launch(), "authorization_reuse")
        os.remove(world.output)
        with open(world.output, "wb") as handle:
            handle.write(b"x")
        self.before = world.listing()
        self.refused(lambda: world.launch(), "authorization_reuse")
        os.remove(world.output)
        real = world.temp + "_real"
        os.rename(world.temp, real)
        os.symlink(real, world.temp)
        try:
            with self.assertRaises(M7Error):
                selection.assert_output_available(world.entry, world.deps(), world.temp)
        finally:
            os.remove(world.temp)
            os.rename(real, world.temp)
        shutil.rmtree(world.temp)
        with self.assertRaises(M7Error):
            selection.assert_output_available(world.entry, world.deps(), world.temp)
        os.makedirs(world.temp)

    def test_the_selection_is_not_consumed_when_the_dry_run_build_refuses(self):
        self.launch_refused(lambda e: e["guardrail_manifests"].pop(), "selection_invalid")

    def test_a_failed_write_after_consumption_is_recorded_and_a_retry_needs_a_new_id(self):
        def failing_writer(directory, name, payload):
            raise OSError("disk full ACGUACGUACGUACGU")

        with self.assertRaises(M7Error) as caught:
            self.world.launch(writer=failing_writer)
        self.assertEqual(caught.exception.code, "filesystem_error")
        self.assertNotIn("ACGU", caught.exception.detail)
        names, directory = self.written()
        self.assertIn(common.FAILURE_RECORD_NAME, names)
        self.assertNotIn(selection.SUCCESS_MANIFEST_NAME, names)
        with open(os.path.join(directory, common.FAILURE_RECORD_NAME), "rb") as handle:
            record = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(record["code"], "filesystem_error")
        self.assertEqual(record["stage"], "manifest_write")
        self.assertEqual(record["entry_kind"], "final_selection")
        self.assertEqual(record["authorisation_id"], IDENTIFIER)
        self.assertEqual((record["status"], record["completion_state"], record["m7_complete"], record["resumable"], record["reuse_permitted"]), ("failed", "consumed_failed", False, False, False))
        self.assertNotIn("ACGU", json.dumps(record))
        # the same id is consumed, so it cannot be reused
        with self.assertRaises(M7Error) as reused:
            self.world.launch()
        self.assertEqual(reused.exception.code, "authorization_reuse")
        # a retry needs a new id and a new output directory
        entry = copy.deepcopy(self.world.entry)
        entry.update(authorisation_id="m7_final_selection_retry", output_directory=os.path.join(self.world.temp, "m7_final_selection_retry"))
        entry["evidence_directory"] = entry["output_directory"]
        manifest = self.world.launch(identifier="m7_final_selection_retry", config_bytes=self.world.config_bytes_for(entry))
        self.assertEqual(manifest["selection_outcome"], "selected_set_complete")
        self.assertTrue(os.path.isfile(os.path.join(entry["output_directory"], selection.SUCCESS_MANIFEST_NAME)))

    def test_every_base_exception_after_consumption_is_recorded_and_interrupts_are_preserved(self):
        for index, (raised, expected_code, preserved) in enumerate(
            (
                (RuntimeError("secret ACGUACGUACGUACGU text"), "unexpected_runtime_failure", False),
                (MemoryError(), "unexpected_runtime_failure", False),
                (KeyboardInterrupt(), "interrupted", True),
                (SystemExit(3), "interrupted", True),
                (GeneratorExit(), "unexpected_runtime_failure", False),
            )
        ):
            identifier = "m7_final_selection_case%d" % index
            entry = copy.deepcopy(self.world.entry)
            entry.update(authorisation_id=identifier, output_directory=os.path.join(self.world.temp, identifier))
            entry["evidence_directory"] = entry["output_directory"]

            def writer(directory, name, payload, raised=raised):
                raise raised

            call = lambda: self.world.launch(identifier=identifier, config_bytes=self.world.config_bytes_for(entry), writer=writer)
            if preserved:
                with self.assertRaises(type(raised)) as caught:
                    call()
                self.assertIs(caught.exception, raised)
            else:
                with self.assertRaises(M7Error) as caught:
                    call()
                self.assertEqual(caught.exception.code, expected_code)
                self.assertNotIn("ACGU", caught.exception.detail)
            with open(os.path.join(entry["output_directory"], common.FAILURE_RECORD_NAME), "rb") as handle:
                record = json.loads(handle.read().decode("utf-8"))
            self.assertEqual(record["code"], expected_code)
            self.assertFalse(os.path.exists(os.path.join(entry["output_directory"], selection.SUCCESS_MANIFEST_NAME)))
            self.assertNotIn("ACGU", json.dumps(record))

    def test_a_failure_during_the_build_after_consumption_is_recorded(self):
        calls = {"count": 0}
        real = selection.build_from_inputs

        def flaky(inputs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise ValueError("late failure")
            return real(inputs)

        with mock.patch.object(selection, "build_from_inputs", flaky):
            with self.assertRaises(M7Error) as caught:
                self.world.launch()
        self.assertEqual(caught.exception.code, "unexpected_runtime_failure")
        self.assertIn("ValueError", caught.exception.detail)
        names, directory = self.written()
        self.assertIn(common.FAILURE_RECORD_NAME, names)
        with open(os.path.join(directory, common.FAILURE_RECORD_NAME), "rb") as handle:
            self.assertEqual(json.loads(handle.read().decode("utf-8"))["stage"], "selection_build")

    def test_the_manifest_is_written_atomically_and_a_replace_failure_leaves_no_partial_file(self):
        with mock.patch.object(os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(M7Error):
                self.world.launch()
        names, _directory = self.written()
        self.assertFalse([name for name in names if name.endswith(".partial")])
        self.assertNotIn(selection.SUCCESS_MANIFEST_NAME, names)

    def test_a_consumption_record_failure_is_recorded_and_interrupts_are_preserved(self):
        real = common.write_atomic_json

        def failing(directory, name, payload, sync_directory=True):
            if name == common.CONSUMPTION_RECORD_NAME:
                raise OSError("no space")
            return real(directory, name, payload, sync_directory)

        with mock.patch.object(common, "write_atomic_json", failing):
            with self.assertRaises(M7Error) as caught:
                self.world.launch()
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertIn(common.FAILURE_RECORD_NAME, os.listdir(self.world.output))
        interrupted = copy.deepcopy(self.world.entry)
        interrupted.update(authorisation_id="m7_final_selection_interrupt", output_directory=os.path.join(self.world.temp, "m7_final_selection_interrupt"))
        interrupted["evidence_directory"] = interrupted["output_directory"]

        def interrupting(directory, name, payload, sync_directory=True):
            if name == common.CONSUMPTION_RECORD_NAME:
                raise KeyboardInterrupt()
            return real(directory, name, payload, sync_directory)

        with mock.patch.object(common, "write_atomic_json", interrupting):
            with self.assertRaises(KeyboardInterrupt):
                self.world.launch(identifier="m7_final_selection_interrupt", config_bytes=self.world.config_bytes_for(interrupted))

    def test_a_failure_record_that_cannot_be_written_keeps_the_original_error_and_reports_both(self):
        real = common.write_atomic_json

        def failing(directory, name, payload, sync_directory=True):
            if name == common.FAILURE_RECORD_NAME:
                raise OSError("no space")
            return real(directory, name, payload, sync_directory)

        def failing_writer(directory, name, payload):
            raise RuntimeError("late")

        with mock.patch.object(common, "write_atomic_json", failing):
            with self.assertRaises(M7Error) as caught:
                self.world.launch(writer=failing_writer)
        self.assertEqual(caught.exception.code, "unexpected_runtime_failure")
        self.assertEqual(caught.exception.secondary_failure["code"], "failure_record_write_failed")
        self.assertIn("secondary_failure=", common.format_error_line(caught.exception))


class NoEligibleCheckpointTests(Case):
    outcomes43 = (False,) * 5
    outcomes44 = (True,)

    def test_no_eligible_checkpoint_is_recorded_without_any_automatic_change(self):
        manifest = self.world.launch()
        self.assertEqual(manifest["selection_outcome"], "no_eligible_checkpoint")
        self.assertIsNone(manifest["selected_set"])
        with open(os.path.join(self.world.output, selection.SUCCESS_MANIFEST_NAME), "rb") as handle:
            written = json.loads(handle.read().decode("utf-8"))
        self.assertTrue(selection.validate_final_selection_manifest(written))
        self.assertEqual({item["seed"]: item["status"] for item in written["seed_records"]}, {43: "no_eligible_checkpoint", 44: "selected"})
        self.assertIs(written["closure"]["human_gate_required"], True)
        for fragment in ("learning_rate", "threshold", "architecture", "seed_change"):
            self.assertNotIn(fragment, json.dumps(written))


class OneSeedExecutionTests(Case):
    outcomes43 = (False, False, True)
    two_seeds = False

    def test_a_one_seed_selection_with_the_sealed_deviation_runs(self):
        manifest = self.world.launch()
        self.assertEqual(manifest["completed_seeds"], [43])
        self.assertEqual(manifest["deviation"], self.world.entry["deviation"])
        self.assertEqual(manifest["m8_allocation"], {"43": 30000})
        self.assertEqual(manifest["selected_set"][0]["epoch"], 4)
        self.assertIs(manifest["closure"]["m7_complete"], False)
        self.assertEqual(sorted(os.listdir(self.world.output)), [common.CONSUMPTION_RECORD_NAME, selection.SUCCESS_MANIFEST_NAME])


# ------------------------------------------------------------------ no data, model, checkpoint, GPU or training-library access


class IsolationTests(Case):
    def test_only_the_bound_manifests_and_the_bound_output_are_touched(self):
        world = self.world
        opened = []
        stated = []
        real_open = open
        real_os_open = os.open

        def recording_open(path, *arguments, **keywords):
            opened.append(os.fspath(path))
            return real_open(path, *arguments, **keywords)

        def recording_os_open(path, *arguments, **keywords):
            opened.append(os.fspath(path))
            return real_os_open(path, *arguments, **keywords)

        def recording_lstat(path):
            stated.append(os.fspath(path))
            return os.lstat(path)

        def refuse(name):
            def raiser(*arguments, **keywords):
                raise AssertionError("unexpected " + name)

            return raiser

        bound = {row["path"] for row in world.entry["replicate_manifests"] + world.entry["guardrail_manifests"]}
        with mock.patch("builtins.open", recording_open), mock.patch.object(os, "open", recording_os_open), \
                mock.patch.object(subprocess, "run", refuse("subprocess.run")), mock.patch.object(subprocess, "Popen", refuse("Popen")), \
                mock.patch.object(subprocess, "check_output", refuse("check_output")), mock.patch.object(common, "run_trusted_tool", refuse("a trusted tool")):
            world.launch(deps=world.deps(lstat=recording_lstat))
        for path in opened:
            if path.endswith((".pyc",)) or "/lib/python" in path or path.startswith("/proc/"):
                continue
            self.assertTrue(
                path in bound or path.startswith(world.output + os.sep) or path in (world.output, world.temp), "opened an unbound path: " + path
            )
        self.assertEqual({path for path in opened if path in bound}, bound)
        forbidden = ("/home/laura/RNAGenesis", "/home/laura/rnagenesis-mres-data", common.RUN_ROOT, "/dev/nvidia", ".safetensors", ".pt", ".csv", ".ckpt", "/unet/")
        for path in opened + stated:
            for fragment in forbidden:
                self.assertNotIn(fragment, path)
            self.assertTrue(path.startswith(world.temp) or world.temp.startswith(path.rstrip("/") or "/"), "touched a path outside the bound run root and its ancestors: " + path)

    def test_the_selection_path_imports_no_training_stack_numpy_or_gpu_tooling(self):
        world = self.world
        payload = {
            "config_bytes": world.config_bytes,
            "identifier": IDENTIFIER,
            "observation": world.observation,
            "run_root": world.temp,
        }
        pickle_path = os.path.join(world.temp, "..", "payload_" + os.path.basename(world.temp) + ".pkl")
        pickle_path = os.path.normpath(pickle_path)
        with open(pickle_path, "wb") as handle:
            pickle.dump(payload, handle)
        self.addCleanup(lambda: os.path.exists(pickle_path) and os.remove(pickle_path))
        code = (
            "import importlib.util, pickle, sys\n"
            "payload = pickle.load(open(sys.argv[2], 'rb'))\n"
            "spec = importlib.util.spec_from_file_location('s', sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "deps = m.SelectionDependencies(environ={'PATH': '/usr/bin:/bin'}, executable=m.common.PINNED_PYTHON, realpath=lambda p: p)\n"
            "manifest = m.launch_authorised_selection(payload['identifier'], run_root=payload['run_root'], deps=deps, config_bytes=payload['config_bytes'], observation=payload['observation'])\n"
            "bad = [n for n in ('torch', 'accelerate', 'diffusers', 'transformers', 'numpy', 'safetensors', 'torchvision', 'scipy', 'pandas', 'pynvml', 'triton') if n in sys.modules]\n"
            "sys.stdout.write(manifest['selection_outcome'] + '|' + ','.join(bad))\n"
        )
        completed = subprocess.run(
            [common.PINNED_PYTHON, "-B", "-c", code, MODULE_FILE, pickle_path], capture_output=True, text=True, cwd=world.temp,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "CUDA_VISIBLE_DEVICES": ""},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "selected_set_complete|")
        self.assertTrue(os.path.isfile(os.path.join(world.output, selection.SUCCESS_MANIFEST_NAME)))

    def test_the_module_text_names_no_gpu_tool_checkpoint_loader_or_training_import(self):
        source = open(MODULE_FILE).read()
        for fragment in ("import torch", "import numpy", "import accelerate", "import diffusers", "import transformers", "nvidia", "safetensors", "torch.load", "load_state_dict", "cuda"):
            self.assertNotIn(fragment, source.replace("CUDA_VISIBLE_DEVICES", ""), fragment)


if __name__ == "__main__":
    unittest.main()

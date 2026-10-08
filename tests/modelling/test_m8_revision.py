#!/usr/bin/env python3
"""Focused revision tests. CPU fakes only. No GPU, weights, or biological data."""

from __future__ import annotations

import copy
import json
import os
import shutil
import stat
import tempfile
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

import yaml

import m8_support as support
from test_m8_generation import FakeDeps, FakeStat

generation = support.generation
assemble = support.assemble
schedule = support.schedule
M8Error = generation.M8Error

SCHEDULE_HASHES = {
    "source_length_vector_sha256": "7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c",
    "empirical_histogram_sha256": "dc599c637dafa455447551a78b0234c818262d82a86989cc863e09136abcaee3",
    "quota_allocation_sha256": "d477d1ffc1d8f3df6f9124b0c613e3beb8891ffa8100b6a5744ac8f9d51aa721",
    "master_attempt_map_sha256": "a99ac979d430c2145f47f696822ec6cc06627142032aaf2f9c5766ffa1cdc14a",
    "block_a_invocation_schedule_sha256": "491c47d8df603e6b9277464611ba27da94dc15134b5e8b2290d91962c45cd13e",
    "block_b_invocation_schedule_sha256": "7b66e5f79f5ce9bb44a896371715c707b7093883e40b8adf5963abf49e135b8f",
}
LIBRARY_VALUE = "/usr/lib64"


def _replace_asset(manifest):
    role = sorted(manifest["asset_verification"]["before"])[0]
    manifest["asset_verification"]["before"][role] = "0" * 64
    manifest["asset_verification"]["after"][role] = "0" * 64


class PoisonDeps(object):
    def __getattr__(self, name):
        raise AssertionError("launch reached " + name)


def _dump(document):
    return yaml.safe_dump(document, sort_keys=True).encode("utf-8")


def _inactive():
    return generation.parse_config(generation.read_m8_config_bytes())


def _seal_generation(document):
    document["authorisation_entries"][0]["active_configuration_sha256"] = generation.active_configuration_identity(document)
    return document


def _generation_document(root, arm="b1_block_a", name=None):
    document = copy.deepcopy(_inactive())
    name = "m8_{}_active".format(arm) if name is None else name
    output = os.path.join(root, name)
    entry = support.generation_entry(arm, output, root)
    document["document_status"] = generation.ACTIVE_DOCUMENT_STATUS
    document["consumable_by_executable_workflow"] = True
    document["execution"] = dict(generation.GENERATION_EXECUTION)
    document["closure"]["execution_authorised"] = True
    document["closure"]["m8_execution_authorised"] = True
    document["authorisation_entries"] = [entry]
    document["assembly_authorisation_entries"] = []
    _seal_generation(document)
    return document, document["authorisation_entries"][0]


def _assembly_entry(root, sources, name="m8_asm_active"):
    return {
        "activation_status": "active_unconsumed",
        "active_configuration_sha256": "ab" * 32,
        "authorisation_id": name,
        "authorization_parent_commit": "a" * 40,
        "condition_id": generation.CONDITION_B1,
        "consumed": False,
        "executing_implementation_commit": "b" * 40,
        "implementation_file_hashes": support.implementation_file_hashes(),
        "ld_library_path": None,
        "output_directory": os.path.join(root, name),
        "reuse_permitted": False,
        "run_root": root,
        "single_use": True,
        "sources": sources,
    }


def _assembly_document(root, sources, name="m8_asm_active"):
    document = copy.deepcopy(_inactive())
    entry = _assembly_entry(root, sources, name)
    document["document_status"] = generation.ACTIVE_ASSEMBLY_STATUS
    document["consumable_by_executable_workflow"] = True
    document["execution"] = dict(generation.ASSEMBLY_EXECUTION)
    document["closure"]["execution_authorised"] = True
    document["closure"]["m8_execution_authorised"] = True
    document["authorisation_entries"] = []
    document["assembly_authorisation_entries"] = [entry]
    entry["active_configuration_sha256"] = generation.active_configuration_identity(document)
    return document, document["assembly_authorisation_entries"][0]


def _refuse(testcase, function, authorisation_id, raw):
    saved = []
    targets = (
        (os, "stat"),
        (os, "lstat"),
        (os, "mkdir"),
        (os, "listdir"),
        (os, "scandir"),
        (os.path, "lexists"),
    )

    def bomb(*_args, **_kwargs):
        raise AssertionError("filesystem access")

    for module, name in targets:
        saved.append((module, name, getattr(module, name)))
        setattr(module, name, bomb)
    try:
        with testcase.assertRaises(M8Error):
            function(authorisation_id, config_bytes=raw, deps=PoisonDeps())
    finally:
        for module, name, value in saved:
            setattr(module, name, value)


class ActiveDocumentTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="m8rev_")
        self._run_root = generation.RUN_ROOT
        generation.RUN_ROOT = self.root

    def tearDown(self):
        generation.RUN_ROOT = self._run_root
        shutil.rmtree(self.root, ignore_errors=True)

    def test_schedule_hashes_and_selection_pins_stay_fixed(self):
        self.assertEqual(schedule.EXPECTED_SCHEDULE_HASHES, SCHEDULE_HASHES)
        self.assertEqual(generation.FINAL_SELECTION_MANIFEST_BYTES, 13124)
        self.assertEqual(
            generation.FINAL_SELECTION_MANIFEST_SHA256,
            "49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c",
        )
        self.assertEqual(
            generation.SELECTED_SET_IDENTITY["selected_set_sha256"],
            "af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f",
        )
        self.assertTrue(generation.FINAL_SELECTION_MANIFEST_PATH.endswith("/m7_final_selection_manifest.json"))

    def test_minimal_active_status_cannot_reach_the_runner(self):
        document = copy.deepcopy(_inactive())
        document["document_status"] = generation.ACTIVE_DOCUMENT_STATUS
        document["consumable_by_executable_workflow"] = True
        _refuse(self, generation.launch_authorised_generation, "m8_b1_block_a_active", _dump(document))
        document["document_status"] = generation.ACTIVE_ASSEMBLY_STATUS
        _refuse(self, assemble.launch_authorised_assembly, "m8_asm_active", _dump(document))

    def test_each_generation_contract_mutation_refuses_before_access(self):
        document, entry = _generation_document(self.root)
        self.assertEqual(generation.parse_config(_dump(document)), document)
        mutations = [
            ("repository_identity", lambda item: item["repository_identity"].__setitem__("mres_commit", "0" * 40)),
            ("selected_set_identity", lambda item: item["selected_set_identity"].__setitem__("selected_set_sha256", "0" * 64)),
            ("schedule_hashes", lambda item: item["schedule_hashes"].__setitem__("master_attempt_map_sha256", "0" * 64)),
            ("checkpoints", lambda item: item["checkpoints"]["b1_generic"].__setitem__("weight_sha256", "0" * 64)),
            ("sampler", lambda item: item["sampler"].__setitem__("ddim_steps", 10)),
            ("arms", lambda item: item["arms"].pop()),
            ("pairing", lambda item: item["pairing"].__setitem__("b1_block_a", "b1_block_b")),
            ("record_schema", lambda item: item["record_schema"].__setitem__("raw_decoded_text_rule", "other")),
            ("retry_rule", lambda item: item.__setitem__("retry_rule", "resume")),
            ("retention", lambda item: item.__setitem__("retention_minimum_date", "2020-01-01")),
            ("deletion", lambda item: item.__setitem__("deletion_implemented", True)),
            ("unknown_field", lambda item: item.__setitem__("unexpected_field", True)),
            ("missing_sampler", lambda item: item.pop("sampler")),
            ("execution_flags", lambda item: item.__setitem__("execution", dict(generation.ASSEMBLY_EXECUTION))),
            ("two_entries", lambda item: item["authorisation_entries"].append(copy.deepcopy(item["authorisation_entries"][0]))),
            ("assembly_list", lambda item: item["assembly_authorisation_entries"].append({"block": "A"})),
            ("empty_generation_list", lambda item: item.__setitem__("authorisation_entries", [])),
        ]
        for name, mutate in mutations:
            candidate = copy.deepcopy(document)
            mutate(candidate)
            with self.subTest(name=name):
                _refuse(self, generation.launch_authorised_generation, entry["authorisation_id"], _dump(candidate))

    def test_each_assembly_contract_mutation_refuses_before_access(self):
        sources = [{"block": "A"}, {"block": "B"}]
        document, entry = _assembly_document(self.root, sources)
        mutations = [
            ("repository_identity", lambda item: item["repository_identity"].__setitem__("rnagenesis_commit", "0" * 40)),
            ("selected_set_identity", lambda item: item["selected_set_identity"].__setitem__("final_selection_manifest_sha256", "0" * 64)),
            ("schedule_hashes", lambda item: item["schedule_hashes"].__setitem__("quota_allocation_sha256", "0" * 64)),
            ("checkpoints", lambda item: item["checkpoints"]["d1_seed_44"].__setitem__("weight_sha256", "0" * 64)),
            ("sampler", lambda item: item["sampler"].__setitem__("guidance_enabled", True)),
            ("arms", lambda item: item.__setitem__("arms", ["b1_block_a"])),
            ("pairing", lambda item: item["pairing"].pop("b1_block_b")),
            ("record_schema", lambda item: item["record_schema"].__setitem__("raw_bytes_authoritative", False)),
            ("retry_rule", lambda item: item.__setitem__("retry_rule", "resume")),
            ("retention", lambda item: item.__setitem__("deletion_implemented", True)),
            ("unknown_field", lambda item: item.__setitem__("gpu_authorised", True)),
            ("missing_closure", lambda item: item.pop("closure")),
            ("generation_flags", lambda item: item.__setitem__("execution", dict(generation.GENERATION_EXECUTION))),
            ("gpu_flag", lambda item: item["execution"].__setitem__("gpu_identity_bound", True)),
            ("generation_list", lambda item: item["authorisation_entries"].append(copy.deepcopy(item["assembly_authorisation_entries"][0]))),
            ("two_assembly_entries", lambda item: item["assembly_authorisation_entries"].append(copy.deepcopy(item["assembly_authorisation_entries"][0]))),
            ("empty_assembly_list", lambda item: item.__setitem__("assembly_authorisation_entries", [])),
            ("gpu_field", lambda item: item["assembly_authorisation_entries"][0].__setitem__("physical_gpu", 0)),
        ]
        for name, mutate in mutations:
            candidate = copy.deepcopy(document)
            mutate(candidate)
            with self.subTest(name=name):
                _refuse(self, assemble.launch_authorised_assembly, entry["authorisation_id"], _dump(candidate))

    def test_generation_status_does_not_activate_assembly(self):
        document, entry = _generation_document(self.root)
        _refuse(self, assemble.launch_authorised_assembly, entry["authorisation_id"], _dump(document))

    def test_public_generation_launch_records_authorization_and_library_path(self):
        document, entry = _generation_document(self.root)
        entry["ld_library_path"] = LIBRARY_VALUE
        _seal_generation(document)
        deps = FakeDeps(entry)
        deps.environ["LD_LIBRARY_PATH"] = LIBRARY_VALUE
        manifest = generation.launch_authorised_generation(entry["authorisation_id"], config_bytes=_dump(document), deps=deps)
        self.assertEqual(manifest["raw_attempt_count"], 15000)
        self.assertEqual(manifest["authorization"]["authorization_commit"], "d" * 40)
        self.assertEqual(manifest["authorization"]["authorization_parent_commit"], "a" * 40)
        self.assertEqual(manifest["authorization"]["executing_implementation_commit"], "b" * 40)
        self.assertEqual(manifest["authorization"]["origin_main"], "d" * 40)
        self.assertEqual(manifest["authorization"]["implementation_file_hashes"], entry["implementation_file_hashes"])
        self.assertEqual(manifest["authorization"]["active_configuration_sha256"], entry["active_configuration_sha256"])
        self.assertEqual(manifest["authorization"]["active_configuration_raw_sha256"], generation.sha256_bytes(_dump(document)))
        self.assertEqual(manifest["repository_identity"]["mres_commit"], manifest["authorization"]["authorization_commit"])
        self.assertEqual(manifest["repository_identity"]["proposal_base_commit"], generation.MRES_COMMIT)
        self.assertNotEqual(manifest["repository_identity"]["mres_commit"], generation.MRES_COMMIT)
        self.assertTrue(os.path.isdir(os.path.join(entry["output_directory"], "isolated_tmp")))
        self.assertFalse(os.path.islink(os.path.join(entry["output_directory"], "isolated_tmp")))
        self.assertEqual(manifest["environment"]["controller_interpreter"]["executable"], generation.PINNED_PYTHON)
        self.assertEqual(manifest["environment"]["child_interpreter"]["sha256"], generation.PINNED_INTERPRETER_SHA256)
        self.assertEqual(manifest["selected_set_evidence"], {"applicable": False})
        self.assertEqual(manifest["environment"]["interpreter_path"], generation.PINNED_PYTHON)
        self.assertEqual(manifest["environment"]["interpreter_resolved_path"], generation.PINNED_RESOLVED_PYTHON)
        self.assertEqual(manifest["environment"]["interpreter_sha256"], generation.PINNED_INTERPRETER_SHA256)
        self.assertEqual(manifest["environment"]["ld_library_path_sha256"], generation.sha256_bytes(LIBRARY_VALUE.encode("utf-8")))
        self.assertTrue(all(env.get("LD_LIBRARY_PATH") == LIBRARY_VALUE for env in deps.envs))
        self.assertEqual(manifest["gpu"]["compute_processes"], 0)
        self.assertGreaterEqual(manifest["storage"]["filesystem_free_bytes"], entry["minimum_free_filesystem_bytes"])
        self.assertFalse(manifest["asset_verification"]["members_copied"])


class DocumentationTests(unittest.TestCase):
    def test_proposal_documents_use_the_corrected_wording(self):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs")
        names = (
            "fine_tuning/m8_raw_generation.md",
            "fine-tuning-implementation-plan.md",
            "fine_tuning/validation_protocol.md",
            "fine_tuning/run_manifest_schema.md",
            "log.md",
        )
        combined = []
        for name in names:
            with open(os.path.join(root, name), "r", encoding="utf-8") as handle:
                combined.append(handle.read())
        text = "\n".join(combined)
        required = (
            "Exact raw bytes remain authoritative",
            "deterministic UTF-8-else-Latin-1",
            "must not treat 30,000 attempts as 30,000 independent model replicates",
            "6.4–10.4 GPU-hours",
            "12–16 hour reservation",
            "active_configuration_raw_sha256",
            "proposal_base_commit",
            "/proc/self/exe",
            "Every commit after the executing implementation commit",
        )
        self.assertNotIn("Raw decoded text is authoritative", text)
        for phrase in required:
            self.assertTrue(phrase in text, phrase)
        self.assertNotIn("ld_library_path:", generation.read_m8_config_bytes().decode("utf-8").lower())


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="m8auth_")
        self._run_root = generation.RUN_ROOT
        generation.RUN_ROOT = self.root
        self.entry = support.generation_entry("b1_block_a", os.path.join(self.root, "m8_b1_block_a_auth"), self.root)
        self.observation = support.repository_observation(self.entry)

    def tearDown(self):
        generation.RUN_ROOT = self._run_root
        shutil.rmtree(self.root, ignore_errors=True)

    def test_parent_may_equal_or_follow_the_implementation_commit(self):
        self.assertNotEqual(self.observation["mres_head"], generation.MRES_COMMIT)
        head = generation.assert_repository_binding(self.entry, self.observation)
        self.assertEqual(head, self.observation["mres_head"])
        first = copy.deepcopy(self.entry)
        first["executing_implementation_commit"] = first["authorization_parent_commit"]
        generation.assert_repository_binding(first, support.repository_observation(first))

    def test_dirty_branch_origin_and_delta_are_refused(self):
        cases = []
        dirty = dict(self.observation)
        dirty["mres_porcelain"] = " M config/experiments/M8_raw_generation.yaml"
        cases.append(dirty)
        branch = dict(self.observation)
        branch["mres_branch"] = "side"
        cases.append(branch)
        origin = dict(self.observation)
        origin["mres_origin_main"] = "e" * 40
        cases.append(origin)
        delta = dict(self.observation)
        delta["changed_files"] = ("config/experiments/M8_raw_generation.yaml", "scripts/modelling/m8_generation.py")
        cases.append(delta)
        rna = dict(self.observation)
        rna["rnagenesis_head"] = "f" * 40
        cases.append(rna)
        ancestor = dict(self.observation)
        ancestor["executing_implementation_is_ancestor"] = False
        cases.append(ancestor)
        same = dict(self.observation)
        same["mres_head"] = self.entry["executing_implementation_commit"]
        same["mres_origin_main"] = same["mres_head"]
        cases.append(same)
        for observation in cases:
            with self.subTest(head=observation.get("mres_head"), branch=observation.get("mres_branch")):
                with self.assertRaises(M8Error):
                    generation.assert_repository_binding(self.entry, observation)

    def test_intervening_commit_outside_the_configuration_is_refused(self):
        observation = copy.deepcopy(self.observation)
        rows = [dict(row) for row in observation["revision_range"]]
        rows[0]["changed_files"] = ("scripts/modelling/m6_pilot_contract.py",)
        observation["revision_range"] = tuple(rows)
        self.assertEqual(observation["changed_files"], ("config/experiments/M8_raw_generation.yaml",))
        with self.assertRaises(M8Error) as caught:
            generation.assert_repository_binding(self.entry, observation)
        self.assertEqual(caught.exception.code, "authorisation_delta_invalid")

        class BadRange(FakeDeps):
            def repository_observation(self, observed_entry=None):
                return observation

        with self.assertRaises(M8Error) as caught:
            generation.run_authorised_arm(self.entry, BadRange(self.entry), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "authorisation_delta_invalid")
        self.assertFalse(os.path.exists(self.entry["output_directory"]))

    def test_live_head_must_not_be_copied_into_the_entry(self):
        copied = copy.deepcopy(self.entry)
        copied["gpu_uuid"] = self.observation["mres_head"]
        with self.assertRaises(M8Error) as caught:
            generation.assert_repository_binding(copied, self.observation)
        self.assertEqual(caught.exception.code, "authorisation_commit_invalid")


class RuntimeAndPreflightTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="m8pre_")
        self._run_root = generation.RUN_ROOT
        self._selection = (
            generation.FINAL_SELECTION_MANIFEST_BYTES,
            generation.FINAL_SELECTION_MANIFEST_SHA256,
            generation.SELECTED_SET_SHA256,
        )
        generation.RUN_ROOT = self.root

    def tearDown(self):
        generation.RUN_ROOT = self._run_root
        (
            generation.FINAL_SELECTION_MANIFEST_BYTES,
            generation.FINAL_SELECTION_MANIFEST_SHA256,
            generation.SELECTED_SET_SHA256,
        ) = self._selection
        shutil.rmtree(self.root, ignore_errors=True)

    def _entry(self, arm="b1_block_a"):
        return support.generation_entry(arm, os.path.join(self.root, "m8_{}_pre".format(arm)), self.root)

    def test_interpreter_and_library_path_are_exact(self):
        entry = self._entry()
        wrong = copy.deepcopy(entry)
        wrong["interpreter_resolved_path"] = generation.PINNED_PYTHON
        with self.assertRaises(M8Error) as caught:
            generation.assert_generation_entry_schema(wrong)
        self.assertEqual(caught.exception.code, "python_interpreter_rejected")
        wrong = copy.deepcopy(entry)
        wrong["interpreter_sha256"] = "0" * 64
        with self.assertRaises(M8Error):
            generation.assert_generation_entry_schema(wrong)

        class BadController(FakeDeps):
            def observe_interpreter(self):
                observed = support.controller_observation()
                observed["executable"] = "/usr/bin/python3"
                observed["resolved_path"] = "/usr/bin/python3.8"
                return observed

        deps = BadController(entry)
        with self.assertRaises(M8Error) as caught:
            generation.run_authorised_arm(entry, deps, raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "python_interpreter_rejected")
        self.assertFalse(os.path.exists(entry["output_directory"]))

        class BadChildExecutable(FakeDeps):
            def observe_child_interpreter(self):
                observed = support.child_observation()
                observed["executable"] = "/tmp/other-python"
                return observed

        deps = BadChildExecutable(entry)
        with self.assertRaises(M8Error) as caught:
            generation.run_authorised_arm(entry, deps, raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "python_interpreter_rejected")
        self.assertFalse(os.path.exists(entry["output_directory"]))

        class BadChildHash(FakeDeps):
            def observe_child_interpreter(self):
                observed = support.child_observation()
                observed["sha256"] = "0" * 64
                return observed

        deps = BadChildHash(entry)
        with self.assertRaises(M8Error) as caught:
            generation.run_authorised_arm(entry, deps, raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "python_interpreter_rejected")
        self.assertFalse(os.path.exists(entry["output_directory"]))

        child = generation.build_child_environment({"LANG": "C", "LD_LIBRARY_PATH": LIBRARY_VALUE}, 1, entry["output_directory"], None)
        self.assertNotIn("LD_LIBRARY_PATH", child)
        bound = generation.build_child_environment({"LD_LIBRARY_PATH": LIBRARY_VALUE}, 1, entry["output_directory"], LIBRARY_VALUE)
        self.assertEqual(bound["LD_LIBRARY_PATH"], LIBRARY_VALUE)
        mismatch = copy.deepcopy(entry)
        mismatch["ld_library_path"] = LIBRARY_VALUE
        deps = FakeDeps(mismatch)
        deps.environ["LD_LIBRARY_PATH"] = "/usr/lib"
        with self.assertRaises(M8Error) as caught:
            generation.run_authorised_arm(mismatch, deps, raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "environment_rejected")
        self.assertFalse(os.path.exists(mismatch["output_directory"]))
        absent = FakeDeps(mismatch)
        with self.assertRaises(M8Error):
            generation.run_authorised_arm(mismatch, absent, raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)

    def test_gpu_and_storage_predicates_stop_before_consumption(self):
        entry = self._entry()
        probes = [
            ("compute_processes", 1, "gpu_probe_invalid"),
            ("uuid", "GPU-other", "gpu_probe_invalid"),
            ("pci_bus", "0000:11:22.0", "gpu_probe_invalid"),
            ("memory_free_bytes", 1, "gpu_probe_invalid"),
            ("filesystem_free_bytes", 1, "insufficient_free_space"),
        ]
        for field, value, code in probes:
            class BadProbe(FakeDeps):
                def gpu_probe(_self, environ):
                    probe = FakeDeps.gpu_probe(_self, environ)
                    probe[field] = value
                    return probe

            with self.subTest(field=field):
                with self.assertRaises(M8Error) as caught:
                    generation.run_authorised_arm(entry, BadProbe(entry), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
                self.assertEqual(caught.exception.code, code)
                self.assertFalse(os.path.exists(entry["output_directory"]))

    def test_canonical_run_root_rejects_repositories_and_other_roots(self):
        self.assertEqual(generation.CANONICAL_RUN_ROOT, "/home/laura/rnagenesis-mres-runs")
        generation.RUN_ROOT = generation.CANONICAL_RUN_ROOT
        for root in ("/tmp", generation.MRES_ROOT, generation.RNAGENESIS_ROOT, generation.EVALUATION_WORKTREE):
            with self.subTest(root=root):
                with self.assertRaises(M8Error):
                    generation.assert_canonical_output_directory(root + "/m8_arm", root, "m8_arm")
        nested = generation.CANONICAL_RUN_ROOT + "/nested/m8_arm"
        with self.assertRaises(M8Error):
            generation.assert_canonical_output_directory(nested, generation.CANONICAL_RUN_ROOT, "m8_arm")
        generation.RUN_ROOT = generation.MRES_ROOT
        with self.assertRaises(M8Error) as caught:
            generation.assert_canonical_output_directory(generation.MRES_ROOT + "/m8_arm", generation.MRES_ROOT, "m8_arm")
        self.assertEqual(caught.exception.code, "prohibited_input")

    def test_selected_set_and_checkpoint_inventory_reject_mismatches(self):
        entry = self._entry("d1_seed43_block_a")
        blob, digest = support.synthetic_selection_manifest()
        self.assertNotEqual(len(blob), 13124)
        generation.FINAL_SELECTION_MANIFEST_BYTES = len(blob)
        generation.FINAL_SELECTION_MANIFEST_SHA256 = generation.sha256_bytes(blob)
        generation.SELECTED_SET_SHA256 = digest
        deps = FakeDeps(entry)
        deps.selection_blob = blob
        verified = generation.verify_selected_set(entry, deps)
        self.assertEqual(verified["manifest_sha256"], generation.sha256_bytes(blob))
        self.assertEqual(verified["seed"], 43)
        self.assertEqual(verified["epoch"], 5)
        self.assertEqual(verified["update"], 105)
        self.assertEqual(verified["checkpoint_name"], generation.D1_CHECKPOINTS[43]["checkpoint_name"])
        self.assertEqual(generation.assert_d1_checkpoint_inventory(entry, deps), generation.diffusion_argument(entry))

        manifest = json.loads(blob.decode("utf-8"))
        manifest["selected_set"][0]["weight_sha256"] = "0" * 64
        manifest["selected_set"][0]["members_sha256"]["unet/diffusion_pytorch_model.safetensors"] = "0" * 64
        replacement = generation._selected_set_digest(manifest["selected_set"])
        manifest["selected_set_sha256"] = replacement
        altered = generation.canonical_bytes(manifest)
        generation.FINAL_SELECTION_MANIFEST_BYTES = len(altered)
        generation.FINAL_SELECTION_MANIFEST_SHA256 = generation.sha256_bytes(altered)
        generation.SELECTED_SET_SHA256 = replacement
        deps.selection_blob = altered
        with self.assertRaises(M8Error) as caught:
            generation.verify_selected_set(entry, deps)
        self.assertEqual(caught.exception.code, "selected_set_mismatch")

        class ExtraMember(FakeDeps):
            def listdir(self, path):
                names = list(FakeDeps.listdir(self, path))
                if path.endswith(os.sep + "scheduler") or path.endswith(os.sep + "unet"):
                    return names
                return names + ["extra.json"]

        deps.selection_blob = blob
        generation.FINAL_SELECTION_MANIFEST_BYTES = len(blob)
        generation.FINAL_SELECTION_MANIFEST_SHA256 = generation.sha256_bytes(blob)
        generation.SELECTED_SET_SHA256 = digest
        with self.assertRaises(M8Error) as caught:
            generation.assert_d1_checkpoint_inventory(entry, ExtraMember(entry))
        self.assertEqual(caught.exception.code, "asset_inspection_unsafe")

        class LinkedWeight(FakeDeps):
            def lstat(self, path):
                measured = FakeDeps.lstat(self, path)
                if path.endswith("diffusion_pytorch_model.safetensors"):
                    linked = FakeStat()
                    linked.st_nlink = 2
                    return linked
                return measured

        with self.assertRaises(M8Error) as caught:
            generation.assert_d1_checkpoint_inventory(entry, LinkedWeight(entry))
        self.assertEqual(caught.exception.code, "asset_inspection_unsafe")

    def test_short_writes_complete_and_interruption_removes_the_temporary(self):
        directory = os.path.join(self.root, "evidence")
        os.mkdir(directory)
        payload = b"abc" * 100
        real_write = os.write

        def short(descriptor, data):
            view = memoryview(data)
            return real_write(descriptor, view[:1])

        os.write = short
        try:
            path = generation.write_atomic_bytes(directory, "complete.json", payload)
        finally:
            os.write = real_write
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), payload)
        self.assertFalse(any(name.startswith(".") for name in os.listdir(directory)))

        calls = {"count": 0}

        def interrupt(descriptor, data):
            calls["count"] += 1
            if calls["count"] > 2:
                raise KeyboardInterrupt
            return real_write(descriptor, memoryview(data)[:1])

        os.write = interrupt
        try:
            with self.assertRaises(KeyboardInterrupt):
                generation.write_atomic_bytes(directory, "interrupted.json", payload)
        finally:
            os.write = real_write
        self.assertFalse(os.path.exists(os.path.join(directory, "interrupted.json")))
        self.assertFalse(os.path.exists(os.path.join(directory, ".interrupted.json.tmp")))

    def test_generation_failure_records_progress_without_sequence_text(self):
        entry = self._entry()
        deps = FakeDeps(entry, mode="short_output")
        with self.assertRaises(M8Error):
            generation.run_authorised_arm(entry, deps, raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        with open(os.path.join(entry["output_directory"], generation.FAILURE_NAME), "rb") as handle:
            failure = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(failure["completed_invocation_count"], 0)
        self.assertEqual(failure["failing_invocation_index"], 0)
        self.assertEqual(failure["authorization_commit"], "d" * 40)
        self.assertEqual(failure["authorization_parent_commit"], entry["authorization_parent_commit"])
        self.assertEqual(failure["executing_implementation_commit"], entry["executing_implementation_commit"])
        self.assertEqual(failure["origin_main"], "d" * 40)
        self.assertNotIn("hello", json.dumps(failure))
        self.assertNotIn("stderr", json.dumps(failure))

        class Boom(FakeDeps):
            def subprocess_run(self, argv, cwd, env, shell=False):
                raise RuntimeError("credential ACGUACGUACGU secret")

        fresh = self._entry("b1_block_b")
        with self.assertRaises(M8Error) as caught:
            generation.run_authorised_arm(fresh, Boom(fresh), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "generation_failed")
        with open(os.path.join(fresh["output_directory"], generation.FAILURE_NAME), "rb") as handle:
            text = handle.read().decode("utf-8")
        self.assertNotIn("credential", text)
        self.assertNotIn("ACGUACGU", text)
        self.assertIn("an unexpected failure was contained", text)


    def test_production_probe_observes_the_running_interpreter(self):
        controller = generation.observe_controller_interpreter()
        child = generation.probe_child_interpreter()
        self.assertEqual(controller["resolved_path"], generation.PINNED_RESOLVED_PYTHON)
        self.assertEqual(controller["sha256"], generation.PINNED_INTERPRETER_SHA256)
        self.assertEqual(controller["python_version"], generation.ACCEPTED_RUNTIME_VERSIONS["python"])
        self.assertEqual(controller["proc_self_exe_resolved"], generation.PINNED_RESOLVED_PYTHON)
        self.assertEqual(child["sha256"], generation.PINNED_INTERPRETER_SHA256)
        self.assertEqual(child["python_version"], generation.ACCEPTED_RUNTIME_VERSIONS["python"])
        self.assertIn(child["executable"], (generation.PINNED_PYTHON, generation.PINNED_RESOLVED_PYTHON))

    def test_symlink_run_root_and_checkpoint_are_refused_before_consumption(self):
        parent = tempfile.mkdtemp(prefix="m8link_")
        real_root = os.path.join(parent, "real-root")
        os.mkdir(real_root)
        link_root = os.path.join(parent, "link-root")
        os.symlink(real_root, link_root)
        generation.RUN_ROOT = link_root
        entry = support.generation_entry("b1_block_a", os.path.join(link_root, "m8_b1_block_a_link"), link_root)

        class RealPaths(FakeDeps):
            def path_lstat(self, path):
                return os.lstat(path)

            def realpath(self, path):
                return os.path.realpath(path)

        with self.assertRaises(M8Error) as caught:
            generation.run_authorised_arm(entry, RealPaths(entry), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "path_unsafe")
        self.assertFalse(os.path.exists(entry["output_directory"]))

        generation.RUN_ROOT = real_root
        entry = support.generation_entry("d1_seed43_block_a", os.path.join(real_root, "m8_d1_seed43_block_a_link"), real_root)
        checkpoint = generation.diffusion_argument(entry)
        os.makedirs(os.path.dirname(checkpoint))
        os.symlink(parent, checkpoint)

        class Mixed(FakeDeps):
            def path_lstat(self, path):
                if path == entry["output_directory"]:
                    raise FileNotFoundError(path)
                if path == entry["run_root"] or path.startswith(entry["run_root"] + os.sep):
                    return os.lstat(path)
                measured = FakeStat()
                measured.st_mode = stat.S_IFDIR | 0o755
                return measured

            def realpath(self, path):
                if path == entry["run_root"] or path.startswith(entry["run_root"] + os.sep):
                    return os.path.realpath(path)
                return os.path.abspath(path)

        with self.assertRaises(M8Error) as caught:
            generation.run_authorised_arm(entry, Mixed(entry), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "path_unsafe")
        self.assertFalse(os.path.exists(entry["output_directory"]))


class AssemblyRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="m8asmrev_")
        cls._run_root = generation.RUN_ROOT
        generation.RUN_ROOT = cls.root
        cls.arms = {
            "A": support.materialise_arm(os.path.join(cls.root, "m8_b1_a"), "b1_block_a"),
            "B": support.materialise_arm(os.path.join(cls.root, "m8_b1_b"), "b1_block_b"),
        }

    @classmethod
    def tearDownClass(cls):
        generation.RUN_ROOT = cls._run_root
        shutil.rmtree(cls.root, ignore_errors=True)

    def _sources(self):
        return [
            {"block": sealed["block"], "byte_count": sealed["byte_count"], "path": sealed["path"], "sha256": sealed["sha256"]}
            for sealed in (self.arms["A"], self.arms["B"])
        ]

    def test_public_assembly_launch_does_not_probe_a_gpu(self):
        document, entry = _assembly_document(self.root, self._sources(), "m8_asm_public")

        class AssemblyDeps(support.ByteDeps):
            def gpu_probe(self, *_args, **_kwargs):
                raise AssertionError("assembly queried a GPU")

        result = assemble.launch_authorised_assembly(entry["authorisation_id"], config_bytes=_dump(document), deps=AssemblyDeps())
        self.assertEqual(result["manifest"]["raw_attempt_count"], 30000)
        self.assertEqual(result["manifest"]["authorization"]["active_configuration_raw_sha256"], generation.sha256_bytes(_dump(document)))
        self.assertEqual(result["manifest"]["repository_identity"]["mres_commit"], "d" * 40)
        self.assertEqual(result["manifest"]["repository_identity"]["proposal_base_commit"], generation.MRES_COMMIT)
        self.assertEqual(result["manifest"]["authorization"]["authorization_commit"], "d" * 40)
        self.assertEqual(result["manifest"]["combined_ledger_byte_count"], len(result["ledger"]))
        self.assertFalse(result["manifest"]["filtering_performed"])
        self.assertFalse(result["manifest"]["parsing_performed"])
        self.assertFalse(result["manifest"]["deduplication_performed"])
        consumption = os.path.join(entry["output_directory"], generation.CONSUMPTION_NAME)
        self.assertTrue(os.path.isfile(consumption))
        self.assertLess(os.path.getmtime(consumption), os.path.getmtime(os.path.join(entry["output_directory"], assemble.MANIFEST_NAME)))

    def test_unsafe_source_ledger_and_raw_links_are_rejected(self):
        outside = os.path.join(tempfile.mkdtemp(prefix="m8out_"), "m8_arm_manifest.json")
        entry = _assembly_entry(
            self.root,
            [{"block": "A", "byte_count": 1, "path": outside, "sha256": "ab" * 32}, self._sources()[1]],
            "m8_asm_outside",
        )
        with self.assertRaises(M8Error):
            assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        nested = os.path.join(self.root, "m8_nested", "inner", generation.MANIFEST_NAME)
        entry = _assembly_entry(
            self.root,
            [{"block": "A", "byte_count": 1, "path": nested, "sha256": "ab" * 32}, self._sources()[1]],
            "m8_asm_nested",
        )
        with self.assertRaises(M8Error):
            assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)

        copied = self._copy_arm(self.arms["A"])
        manifest_path = copied["path"]
        real = manifest_path + ".real"
        os.rename(manifest_path, real)
        os.symlink(real, manifest_path)
        entry = _assembly_entry(self.root, [copied, self._sources()[1]], "m8_asm_symlink")
        with self.assertRaises(M8Error) as caught:
            assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "path_unsafe")

        copied = self._copy_arm(self.arms["A"])
        raw_files = []
        for current, _dirs, files in os.walk(os.path.dirname(copied["path"])):
            for name in files:
                if name.endswith(".txt"):
                    raw_files.append(os.path.join(current, name))
        os.link(raw_files[0], raw_files[0] + ".hardlink")
        entry = _assembly_entry(self.root, [copied, self._sources()[1]], "m8_asm_hardlink")
        with self.assertRaises(M8Error) as caught:
            assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "assembly_invalid")

    def test_schedule_record_tampering_is_rejected(self):
        def tamper(manifest, records):
            records[3]["generation_seed"] = records[3]["generation_seed"] + 1
            records[4]["max_seq_len"] = records[4]["requested_biological_length"]
            records[5]["record_id"] = "m8:other"
            return records

        altered = self._mutate(self.arms["A"], tamper)
        entry = _assembly_entry(self.root, [altered, self._sources()[1]], "m8_asm_tamper")
        with self.assertRaises(M8Error) as caught:
            assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "assembly_invalid")

    def test_consumption_failure_requires_a_new_directory(self):
        entry = _assembly_entry(self.root, self._sources(), "m8_asm_fail")
        original = generation.write_atomic_bytes

        def fail_ledger(directory, name, blob):
            if name == assemble.LEDGER_NAME:
                raise M8Error("assembly_invalid", "stopped after consumption", "assembly")
            return original(directory, name, blob)

        generation.write_atomic_bytes = fail_ledger
        try:
            with self.assertRaises(M8Error):
                assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        finally:
            generation.write_atomic_bytes = original
        output = entry["output_directory"]
        self.assertTrue(os.path.isfile(os.path.join(output, generation.CONSUMPTION_NAME)))
        self.assertTrue(os.path.isfile(os.path.join(output, generation.FAILURE_NAME)))
        self.assertFalse(os.path.exists(os.path.join(output, assemble.MANIFEST_NAME)))
        with open(os.path.join(output, generation.FAILURE_NAME), "rb") as handle:
            failure = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(failure["authorization_commit"], "d" * 40)
        self.assertEqual(failure["active_configuration_raw_sha256"], support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertNotEqual(failure["active_configuration_raw_sha256"], failure["active_configuration_sha256"])
        self.assertEqual(failure["executing_implementation_commit"], entry["executing_implementation_commit"])
        self.assertFalse(failure["resumable"])
        with self.assertRaises(M8Error) as caught:
            assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "output_directory_exists")
        retry = _assembly_entry(self.root, self._sources(), "m8_asm_retry")
        result = assemble.assemble_authorised(retry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(result["manifest"]["raw_attempt_count"], 30000)

    def test_distinct_yaml_bytes_keep_distinct_raw_hashes(self):
        document, entry = _assembly_document(self.root, self._sources(), "m8_asm_raw_a")
        block = yaml.safe_dump(document, sort_keys=True).encode("utf-8")
        flow = yaml.safe_dump(document, sort_keys=True, default_flow_style=True).encode("utf-8")
        self.assertNotEqual(block, flow)
        identity_block = generation.active_configuration_identity(generation.parse_config(block))
        identity_flow = generation.active_configuration_identity(generation.parse_config(flow))
        self.assertEqual(identity_block, identity_flow)
        self.assertNotEqual(generation.sha256_bytes(block), generation.sha256_bytes(flow))
        first = assemble.launch_authorised_assembly(entry["authorisation_id"], config_bytes=block, deps=support.ByteDeps())
        self.assertEqual(first["manifest"]["authorization"]["active_configuration_raw_sha256"], generation.sha256_bytes(block))
        self.assertEqual(first["manifest"]["authorization"]["active_configuration_sha256"], identity_block)
        with open(os.path.join(entry["output_directory"], generation.CONSUMPTION_NAME), "rb") as handle:
            consumed = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(consumed["active_configuration_raw_sha256"], generation.sha256_bytes(block))
        shutil.rmtree(entry["output_directory"])
        second = assemble.launch_authorised_assembly(entry["authorisation_id"], config_bytes=flow, deps=support.ByteDeps())
        self.assertEqual(second["manifest"]["authorization"]["active_configuration_raw_sha256"], generation.sha256_bytes(flow))
        self.assertEqual(second["manifest"]["authorization"]["active_configuration_sha256"], identity_flow)

        failed, failed_entry = _assembly_document(self.root, self._sources(), "m8_asm_raw_fail")
        raw = yaml.safe_dump(failed, sort_keys=True).encode("utf-8")
        original = generation.write_atomic_bytes

        def fail_ledger(directory, name, blob):
            if name == assemble.LEDGER_NAME:
                raise M8Error("assembly_invalid", "stopped after consumption", "assembly")
            return original(directory, name, blob)

        generation.write_atomic_bytes = fail_ledger
        try:
            with self.assertRaises(M8Error):
                assemble.launch_authorised_assembly(failed_entry["authorisation_id"], config_bytes=raw, deps=support.ByteDeps())
        finally:
            generation.write_atomic_bytes = original
        with open(os.path.join(failed_entry["output_directory"], generation.CONSUMPTION_NAME), "rb") as handle:
            consumed = json.loads(handle.read().decode("utf-8"))
        with open(os.path.join(failed_entry["output_directory"], generation.FAILURE_NAME), "rb") as handle:
            failure = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(consumed["active_configuration_raw_sha256"], generation.sha256_bytes(raw))
        self.assertEqual(failure["active_configuration_raw_sha256"], generation.sha256_bytes(raw))
        self.assertNotEqual(failure["active_configuration_raw_sha256"], failure["active_configuration_sha256"])

    def test_assembly_refuses_a_missing_raw_digest_before_output(self):
        entry = _assembly_entry(self.root, self._sources(), "m8_asm_no_raw")
        with self.assertRaises(M8Error) as caught:
            assemble.assemble_authorised(entry, support.ByteDeps())
        self.assertEqual(caught.exception.code, "provenance_mismatch")
        self.assertFalse(os.path.exists(entry["output_directory"]))

    def test_each_nested_arm_section_rejects_a_semantic_mutation(self):
        source = self.arms["A"]
        mutations = [
            ("sampler", lambda manifest, records: manifest["sampler"].__setitem__("ddim_steps", 49) or records),
            ("sequence_access", lambda manifest, records: manifest["sequence_access"].__setitem__("TRAIN", True) or records),
            ("model_kind", lambda manifest, records: manifest["model_assets"].__setitem__("kind", "other") or records),
            ("asset_inventory", lambda manifest, records: _replace_asset(manifest) or records),
            ("raw_output_hashes", lambda manifest, records: manifest["raw_output_hashes"].__setitem__(0, "0" * 64) or records),
            ("paired_schedule", lambda manifest, records: manifest["schedule"].__setitem__("paired_block_invocation_schedule_sha256", "0" * 64) or records),
            ("controller", lambda manifest, records: manifest["environment"]["controller_interpreter"].__setitem__("executable", "/usr/bin/python3") or records),
            ("gpu_threshold", lambda manifest, records: manifest["gpu"].__setitem__("memory_free_bytes", 0) or records),
            ("storage_threshold", lambda manifest, records: manifest["storage"].__setitem__("filesystem_free_bytes", 0) or records),
            ("elapsed", lambda manifest, records: manifest["timestamps"].__setitem__("elapsed_seconds", -1) or records),
        ]
        for label, mutator in mutations:
            with self.subTest(label=label):
                altered = self._mutate(source, mutator)
                with self.assertRaises(M8Error) as caught:
                    assemble.assemble_authorised(
                        _assembly_entry(self.root, [altered, self._sources()[1]], "m8_asm_" + label),
                        support.ByteDeps(),
                        raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256,
                    )
                self.assertEqual(caught.exception.code, "assembly_invalid")
                self.assertFalse(os.path.exists(os.path.join(self.root, "m8_asm_" + label)))

        def rewrite_ids(manifest, records):
            manifest["run_id"] = "m8_not_the_directory"
            manifest["authorization"]["authorisation_id"] = "m8_not_the_directory"
            for record in records:
                record["run_id"] = "m8_not_the_directory"
                record["authorization_id"] = "m8_not_the_directory"
            return records

        altered = self._mutate(source, lambda manifest, records: records, after=rewrite_ids)
        with self.assertRaises(M8Error) as caught:
            assemble.assemble_authorised(
                _assembly_entry(self.root, [altered, self._sources()[1]], "m8_asm_identity"),
                support.ByteDeps(),
                raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256,
            )
        self.assertEqual(caught.exception.code, "assembly_invalid")

    def test_d1_selected_checkpoint_chain_is_enforced(self):
        first = support.materialise_arm(os.path.join(self.root, "m8_d1_chain_a"), "d1_seed43_block_a")
        second = support.materialise_arm(os.path.join(self.root, "m8_d1_chain_b"), "d1_seed44_block_b")
        altered = self._mutate(first, lambda manifest, records: manifest["selected_set_evidence"].__setitem__("checkpoint_name", "other.pt") or records)
        entry = _assembly_entry(
            self.root,
            [
                {"block": altered["block"], "byte_count": altered["byte_count"], "path": altered["path"], "sha256": altered["sha256"]},
                {"block": second["block"], "byte_count": second["byte_count"], "path": second["path"], "sha256": second["sha256"]},
            ],
            "m8_asm_d1_chain",
        )
        entry["condition_id"] = generation.CONDITION_D1
        with self.assertRaises(M8Error) as caught:
            assemble.assemble_authorised(
                entry,
                support.ByteDeps(),
                raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256,
            )
        self.assertEqual(caught.exception.code, "assembly_invalid")
        self.assertFalse(os.path.exists(os.path.join(self.root, "m8_asm_d1_chain")))

    def test_symlinked_arm_and_nested_raw_directories_are_refused(self):
        copied = self._copy_arm(self.arms["A"])
        arm = os.path.dirname(copied["path"])
        parent = os.path.dirname(arm)
        outside = tempfile.mkdtemp(prefix="m8armout_")
        moved = os.path.join(outside, os.path.basename(arm))
        shutil.move(arm, moved)
        os.symlink(moved, arm)
        with self.assertRaises(M8Error) as caught:
            assemble.assemble_authorised(
                _assembly_entry(
                    self.root,
                    [
                        {"block": copied["block"], "byte_count": copied["byte_count"], "path": copied["path"], "sha256": copied["sha256"]},
                        self._sources()[1],
                    ],
                    "m8_asm_armlink",
                ),
                support.ByteDeps(),
                raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256,
            )
        self.assertEqual(caught.exception.code, "path_unsafe")
        self.assertFalse(os.path.exists(os.path.join(self.root, "m8_asm_armlink")))

        nested = self._copy_arm(self.arms["B"])
        raw_root = os.path.join(os.path.dirname(nested["path"]), "raw")
        invocation = os.listdir(raw_root)[0]
        invocation_path = os.path.join(raw_root, invocation)
        escaped = tempfile.mkdtemp(prefix="m8rawout_")
        target = os.path.join(escaped, invocation)
        shutil.move(invocation_path, target)
        os.symlink(target, invocation_path)
        with self.assertRaises(M8Error) as caught:
            assemble.assemble_authorised(
                _assembly_entry(
                    self.root,
                    [
                        self._sources()[0],
                        {"block": nested["block"], "byte_count": nested["byte_count"], "path": nested["path"], "sha256": nested["sha256"]},
                    ],
                    "m8_asm_rawlink",
                ),
                support.ByteDeps(),
                raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256,
            )
        self.assertEqual(caught.exception.code, "path_unsafe")
        self.assertFalse(os.path.exists(os.path.join(self.root, "m8_asm_rawlink")))

    def _copy_arm(self, sealed):
        return self._mutate(sealed, lambda manifest, records: records)

    def _mutate(self, sealed, mutator, after=None):
        directory = tempfile.mkdtemp(prefix="m8_copy_", dir=self.root)
        source = os.path.dirname(sealed["path"])
        for name in os.listdir(source):
            src = os.path.join(source, name)
            dst = os.path.join(directory, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        manifest_path = os.path.join(directory, generation.MANIFEST_NAME)
        ledger_path = os.path.join(directory, generation.LEDGER_NAME)
        with open(manifest_path, "rb") as handle:
            manifest = json.loads(handle.read().decode("utf-8"))
        with open(ledger_path, "rb") as handle:
            records = [json.loads(line) for line in handle.read().split(b"\n")[:-1]]
        records = mutator(manifest, records)
        name = os.path.basename(directory)
        manifest["run_id"] = name
        manifest["authorization"]["authorisation_id"] = name
        for record in records:
            record["authorization_id"] = name
            record["run_id"] = name
        if after is not None:
            records = after(manifest, records)
        ledger = b"".join(generation.canonical_bytes(record) for record in records)
        with open(ledger_path, "wb") as handle:
            handle.write(ledger)
        manifest["raw_attempt_ledger_sha256"] = generation.sha256_bytes(ledger)
        manifest["raw_attempt_ledger_byte_count"] = len(ledger)
        manifest["raw_attempt_count"] = len(records)
        blob = generation.canonical_bytes(manifest)
        with open(manifest_path, "wb") as handle:
            handle.write(blob)
        measured = os.lstat(manifest_path)
        self.assertFalse(stat.S_ISLNK(measured.st_mode))
        return {"block": sealed["block"], "byte_count": len(blob), "path": manifest_path, "sha256": generation.sha256_bytes(blob)}


if __name__ == "__main__":
    unittest.main()

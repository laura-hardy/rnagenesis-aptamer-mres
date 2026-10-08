#!/usr/bin/env python3
"""Inactive M8 generation tests with fake assets and a fake generation.py."""

from __future__ import annotations

import io
import os
import stat
import tempfile
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

import m8_support as support

generation = support.generation
schedule = support.schedule
M8Error = generation.M8Error


class FakeStat(object):
    st_mode = stat.S_IFREG | 0o644
    st_size = 4
    st_nlink = 1
    st_ino = 7
    st_dev = 3


class FakeCompleted(object):
    def __init__(self, returncode):
        self.returncode = returncode


class FakeDeps(object):
    def __init__(self, entry, mode="success"):
        self.entry = entry
        self.mode = mode
        self.environ = {"LANG": "C", "LC_ALL": "C"}
        self.argvs = []
        self.envs = []
        self.hash_calls = []
        self.before_raw_reverify = None
        self.expected = {path: digest for path, digest, _role in generation.asset_table(entry)}
        self._vector = support.pinned_vector_bytes()
        self.selection_blob = b""
        self._mono = 0
        self._now = 0

    def read_bytes(self, path):
        if path == schedule.LENGTH_VECTOR_PATH:
            return self._vector
        if path == generation.FINAL_SELECTION_MANIFEST_PATH:
            return self.selection_blob
        raise AssertionError(path)

    def lstat(self, path):
        if path not in self.expected:
            raise AssertionError(path)
        return FakeStat()

    def listdir(self, path):
        if path.endswith(os.sep + "scheduler"):
            return ["scheduler_config.json"]
        if path.endswith(os.sep + "unet"):
            return ["config.json", "diffusion_pytorch_model.safetensors"]
        return ["model_index.json", "scheduler", "unet"]

    def observe_interpreter(self):
        return support.controller_observation()

    def observe_child_interpreter(self):
        return support.child_observation()

    def path_lstat(self, path):
        if path == self.entry["output_directory"]:
            raise FileNotFoundError(path)
        measured = FakeStat()
        if path in self.expected:
            measured.st_mode = stat.S_IFREG | 0o644
        else:
            measured.st_mode = stat.S_IFDIR | 0o755
        return measured

    def realpath(self, path):
        return os.path.abspath(path)

    def repository_observation(self, entry=None):
        return support.repository_observation(self.entry if entry is None else entry)

    def hash_file(self, path):
        self.hash_calls.append(path)
        if self.mode == "bad_before":
            return "0" * 64
        if self.mode == "bad_after" and self.hash_calls.count(path) > 1:
            return "0" * 64
        return self.expected[path]

    def subprocess_run(self, argv, cwd, env, shell=False):
        if shell is not False:
            raise AssertionError("shell")
        self.argvs.append(list(argv))
        self.envs.append(dict(env))
        batch_size = int(argv[argv.index("--batch_size") + 1])
        batch_num = int(argv[argv.index("--batch_num") + 1])
        superfolder = argv[argv.index("--superfolder") + 1]
        mid = argv[argv.index("--mid_folder") + 1]
        remark = argv[argv.index("--remark") + 1]
        count = batch_size * batch_num
        if self.mode == "short_output":
            count = max(0, count - 1)
        name = "seqs_wo_guidance_top_p=0.95_2_{}{}.txt".format(batch_size * batch_num, remark)
        path = os.path.join(superfolder, mid, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for index in range(count):
                if index == 0:
                    handle.write("hello\n")
                elif index == 1:
                    handle.write("\n")
                else:
                    handle.write("ACGU\n")
        return FakeCompleted(0)

    def gpu_probe(self, environ):
        return {
            "compute_processes": 0,
            "cuda_visible_devices": "1",
            "filesystem_free_bytes": 10 ** 12,
            "logical_device": "cuda:0",
            "memory_free_bytes": 10 ** 12,
            "memory_total_bytes": 2 * 10 ** 12,
            "pci_bus": "0000:00:00.0",
            "physical_gpu": 1,
            "uuid": "GPU-test",
        }

    def library_versions(self):
        return dict(generation.ACCEPTED_RUNTIME_VERSIONS)

    def now(self):
        self._now += 1
        return "2026-10-08T00:00:0{}+00:00".format(self._now)

    def monotonic(self):
        self._mono += 5
        return self._mono


class InactiveAndArgvTests(unittest.TestCase):
    def test_help_and_schema_do_not_open_the_configuration(self):
        original = generation.read_m8_config_bytes

        def boom():
            raise AssertionError("config opened")

        generation.read_m8_config_bytes = boom
        try:
            stdout = io.StringIO()
            self.assertEqual(generation.production_main(["--help"], stdout=stdout), 0)
            self.assertIn("not authorised", stdout.getvalue())
            stdout = io.StringIO()
            self.assertEqual(generation.production_main(["--schema"], stdout=stdout), 0)
            self.assertIn("execution_authorised", stdout.getvalue())
        finally:
            generation.read_m8_config_bytes = original

    def test_inactive_authorisation_refuses_before_side_effects(self):
        calls = []

        def bomb(*_args, **_kwargs):
            calls.append("side")
            raise AssertionError("side effect")

        original = generation.ProductionDeps
        saved = {}
        for name in ("verify_assets", "_load_schedule", "_consume_directory", "build_child_environment", "run_authorised_arm"):
            saved[name] = getattr(generation, name)
            setattr(generation, name, bomb)
        generation.ProductionDeps = bomb
        try:
            code = generation.main(["--authorisation-id", "m8_b1_block_a_review"])
        finally:
            generation.ProductionDeps = original
            for name, value in saved.items():
                setattr(generation, name, value)
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])

    def test_m7_ids_schemas_and_the_live_seed44_file_are_rejected(self):
        original = generation.read_m8_config_bytes

        def boom():
            raise AssertionError("config opened")

        generation.read_m8_config_bytes = boom
        try:
            code = generation.main(["--authorisation-id", generation.LIVE_M7_SEED44_AUTHORISATION_ID])
            self.assertEqual(code, 2)
            code = generation.main(["--authorisation-id", "m7_other"])
            self.assertEqual(code, 2)
        finally:
            generation.read_m8_config_bytes = original
        live = "/home/laura/rnagenesis-aptamer-mres/config/experiments/D1_final_replicates.yaml"
        with open(live, "rb") as handle:
            before = handle.read()
        with self.assertRaises(M8Error) as caught:
            generation.reject_configuration_path(live)
        self.assertEqual(caught.exception.code, "m7_authority_rejected")
        document = generation.parse_config(before)
        with self.assertRaises(M8Error) as caught:
            generation.reject_m7_document(document)
        self.assertEqual(caught.exception.code, "m7_authority_rejected")
        self.assertTrue(str(document.get("schema_version", "")).startswith("m7-"))
        self.assertTrue(str(document.get("document_status", "")).startswith("M7_"))
        with open(live, "rb") as handle:
            after = handle.read()
        self.assertEqual(before, after)

    def test_prohibited_paths_are_rejected_before_open(self):
        def opener(_path):
            raise AssertionError("opened")

        paths = [
            "/tmp/REF/ref.csv",
            "/tmp/EVAL/eval.csv",
            "/tmp/VALIDATION/ft_validation.csv",
            "/tmp/TRAIN/ft_train.csv",
            "/tmp/TRAIN/corpus_final.txt",
            "/home/laura/rnagenesis-mres-worktrees/generator-eval-prep",
            "/home/laura/rnagenesis-mres-worktrees/generator-eval-prep/nested",
            "/home/laura/rnagenesis-mres-runs/m7_d1_final_selection_b5de24327ed5_attempt1/m7_final_selection_manifest.json",
        ]
        for path in paths:
            with self.assertRaises(M8Error) as caught:
                generation.refuse_before_open(path, opener)
            self.assertEqual(caught.exception.code, "prohibited_input")

    def test_checked_in_configuration_is_inactive(self):
        document = generation.parse_config(generation.read_m8_config_bytes())
        generation.assert_inactive_configuration(document)
        text = generation.read_m8_config_bytes().decode("utf-8")
        self.assertNotIn("ld_library_path:", text.lower())
        self.assertNotIn(generation.PINNED_PYTHON, text)
        self.assertNotIn("output_directory:", text)
        self.assertNotIn("cuda:", text.lower())

    def test_active_entry_cannot_name_an_existing_directory(self):
        with tempfile.TemporaryDirectory() as root:
            output = os.path.join(root, "m8_b1_block_a_exists")
            os.mkdir(output)
            original = generation.RUN_ROOT
            generation.RUN_ROOT = root
            try:
                entry = support.generation_entry("b1_block_a", output, root)
                with self.assertRaises(M8Error) as caught:
                    generation.validate_generation_entry(entry)
                self.assertEqual(caught.exception.code, "output_directory_exists")
            finally:
                generation.RUN_ROOT = original

    def test_full_and_remainder_argv_and_pairing(self):
        lengths = schedule.assert_pinned_length_vector(support.pinned_vector_bytes())
        built = schedule.build_schedule(lengths)
        full = next(row for row in built["invocations"]["A"]["invocations"] if row["batch_num"] > 1)
        remainder = next(row for row in built["invocations"]["A"]["invocations"] if row["kind"] == "remainder")
        b1 = generation.build_generation_argv(full, generation.PINNED_PYTHON, "configs/rnagenesis/diffusion")
        d1_directory = generation.diffusion_argument(
            {"asset_kind": "d1", "d1_training_seed": 43, "technical_block": "A"}
        )
        d1 = generation.build_generation_argv(full, generation.PINNED_PYTHON, d1_directory)
        self.assertGreater(int(b1[b1.index("--batch_num") + 1]), 1)
        self.assertEqual(b1[b1.index("--batch_size") + 1], "16")
        self.assertNotIn("--truncate", b1)
        self.assertNotIn("--guidance", b1)
        self.assertIn("--do_sample", b1)
        self.assertEqual(b1[b1.index("--device") + 1], "cuda:0")
        self.assertEqual(b1[0], generation.PINNED_PYTHON)
        self.assertEqual(b1[b1.index("--seed") + 1], d1[d1.index("--seed") + 1])
        self.assertNotEqual(b1[b1.index("--dm_file") + 1], d1[d1.index("--dm_file") + 1])
        remainder_argv = generation.build_generation_argv(remainder, generation.PINNED_PYTHON, "configs/rnagenesis/diffusion")
        self.assertEqual(remainder_argv[remainder_argv.index("--batch_num") + 1], "1")
        self.assertLess(int(remainder_argv[remainder_argv.index("--batch_size") + 1]), 16)
        block_b = built["invocations"]["B"]["invocations"]
        self.assertEqual(
            [row["generation_seed"] for row in built["invocations"]["A"]["invocations"]],
            [row["generation_seed"] for row in built["invocations"]["A"]["invocations"]],
        )
        self.assertEqual(block_b[0]["generation_seed"], 900000)
        self.assertEqual(set(row["generation_seed"] for row in built["invocations"]["A"]["invocations"]).isdisjoint(
            row["generation_seed"] for row in block_b
        ), True)
        with self.assertRaises(M8Error):
            bad = dict(full)
            bad["batch_num"] = 2
            bad["batch_size"] = 3
            bad["kind"] = "remainder"
            generation.build_generation_argv(bad, generation.PINNED_PYTHON, "configs/rnagenesis/diffusion")

    def test_empty_and_non_acgu_lines_are_retained_without_a_validity_field(self):
        invocation = {
            "batch_num": 1,
            "batch_size": 3,
            "block": "A",
            "generation_seed": 800000,
            "invocation_index": 0,
            "kind": "remainder",
            "line_count": 3,
            "master_attempt_indexes": [0, 1, 2],
            "max_seq_len": 21,
            "requested_biological_length": 20,
        }
        entry = {
            "authorisation_id": "m8_example",
            "condition_id": generation.CONDITION_B1,
            "d1_training_seed": None,
            "run_id": "m8_example",
            "technical_block": "A",
            "asset_kind": "b1",
        }
        records = generation.map_invocation_lines(entry, invocation, b"hello\n\nACGU\n")
        self.assertEqual([row["raw_decoded_text"] for row in records], ["hello", "", "ACGU"])
        self.assertEqual([row["batch_number"] for row in records], [0, 0, 0])
        self.assertEqual([row["within_batch_position"] for row in records], [0, 1, 2])
        self.assertEqual(records[0]["record_id"], "m8:{}:master:00000".format(generation.CONDITION_B1))
        for record in records:
            self.assertEqual(tuple(sorted(record)), generation.RAW_RECORD_KEYS)
            self.assertNotIn("validity", record)
        with self.assertRaises(M8Error) as caught:
            generation.map_invocation_lines(entry, invocation, b"only-one\n")
        self.assertEqual(caught.exception.code, "raw_output_line_count")

    def test_module_does_not_call_the_cleaner_or_m7_guardrails(self):
        with open(generation.__file__, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("audit_generation_output", text)
        self.assertNotIn("sample_target_lengths", text)
        self.assertNotIn("production_generate_and_measure", text)
        self.assertNotIn("shutil.copy", text)


class FakeRunTests(unittest.TestCase):
    def setUp(self):
        self._run_root = generation.RUN_ROOT
        self._selection = (
            generation.FINAL_SELECTION_MANIFEST_BYTES,
            generation.FINAL_SELECTION_MANIFEST_SHA256,
            generation.SELECTED_SET_SHA256,
        )

    def tearDown(self):
        generation.RUN_ROOT = self._run_root
        (
            generation.FINAL_SELECTION_MANIFEST_BYTES,
            generation.FINAL_SELECTION_MANIFEST_SHA256,
            generation.SELECTED_SET_SHA256,
        ) = self._selection

    def _run(self, arm, mode="success", hook=None):
        root = tempfile.mkdtemp(prefix="m8test_")
        generation.RUN_ROOT = root
        output = os.path.join(root, "m8_{}_run".format(arm))
        entry = support.generation_entry(arm, output, root)
        deps = FakeDeps(entry, mode=mode)
        deps.before_raw_reverify = hook
        if arm.startswith("d1_"):
            blob, digest = support.synthetic_selection_manifest()
            deps.selection_blob = blob
            generation.FINAL_SELECTION_MANIFEST_BYTES = len(blob)
            generation.FINAL_SELECTION_MANIFEST_SHA256 = generation.sha256_bytes(blob)
            generation.SELECTED_SET_SHA256 = digest
        try:
            document = generation.run_authorised_arm(entry, deps, raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        except M8Error:
            return root, output, entry, deps, None
        return root, output, entry, deps, document

    def test_b1_and_d1_arms_retain_raw_text_and_reverify_assets(self):
        for arm, seed_base in (("b1_block_a", 800000), ("d1_seed43_block_a", 800000)):
            _root, output, _entry, deps, document = self._run(arm)
            self.assertIsNotNone(document)
            self.assertEqual(document["raw_attempt_count"], 15000)
            self.assertFalse(document["filtering_performed"])
            self.assertFalse(document["cleaner_invoked"])
            self.assertFalse(document["replacement_or_replenishment_performed"])
            self.assertFalse(any(document["sequence_access"].values()))
            self.assertTrue(document["later_evaluation_required"])
            self.assertTrue(document["reuse_prohibited"])
            self.assertEqual(document["asset_verification"]["before"], document["asset_verification"]["after"])
            self.assertFalse(document["asset_verification"]["members_copied"])
            self.assertEqual(document["environment"]["path"], generation.FIXED_CHILD_PATH)
            self.assertEqual(document["environment"]["cuda_visible_devices"], "1")
            self.assertEqual(document["gpu"]["logical_device"], "cuda:0")
            self.assertTrue(any(int(argv[argv.index("--batch_num") + 1]) > 1 for argv in deps.argvs))
            self.assertTrue(all("--truncate" not in argv for argv in deps.argvs))
            self.assertTrue(all(argv[argv.index("--device") + 1] == "cuda:0" for argv in deps.argvs))
            self.assertTrue(all(int(argv[argv.index("--seed") + 1]) >= seed_base for argv in deps.argvs))
            self.assertEqual(len(deps.hash_calls), 2 * len(deps.expected))
            with open(os.path.join(output, generation.LEDGER_NAME), "r", encoding="utf-8") as handle:
                first = handle.readline()
            self.assertIn('"raw_decoded_text":"hello"', first)
            self.assertNotIn("validity", first)
            self.assertFalse(any(name.endswith(".safetensors") for _dir, _dirs, files in os.walk(output) for name in files))

    def test_line_count_mismatch_is_consumed_and_not_replaced(self):
        _root, output, entry, _deps, document = self._run("b1_block_a", mode="short_output")
        self.assertIsNone(document)
        self.assertFalse(os.path.exists(os.path.join(output, generation.MANIFEST_NAME)))
        self.assertFalse(os.path.exists(os.path.join(output, generation.LEDGER_NAME)))
        with open(os.path.join(output, generation.FAILURE_NAME), "rb") as handle:
            failure = handle.read()
        self.assertIn(b'"resumable":false', failure)
        self.assertIn(b'"consumed":true', failure)
        self.assertNotIn(b"hello", failure)
        with self.assertRaises(M8Error) as caught:
            generation.validate_generation_entry(entry)
        self.assertEqual(caught.exception.code, "output_directory_exists")
        with open(os.path.join(output, generation.FAILURE_NAME), "rb") as handle:
            self.assertEqual(handle.read(), failure)

    def test_retry_requires_a_new_id_and_directory(self):
        root, output, entry, _deps, _document = self._run("b1_block_b", mode="short_output")
        with self.assertRaises(M8Error) as caught:
            generation.run_authorised_arm(entry, FakeDeps(entry), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(caught.exception.code, "output_directory_exists")
        renamed = dict(entry)
        renamed["authorisation_id"] = "m8_other_id"
        renamed["run_id"] = "m8_other_id"
        with self.assertRaises(M8Error) as caught:
            generation.validate_generation_entry(renamed)
        self.assertEqual(caught.exception.code, "authorisation_scope_invalid")
        fresh_root = tempfile.mkdtemp(prefix="m8retry_")
        generation.RUN_ROOT = fresh_root
        fresh = support.generation_entry("b1_block_b", os.path.join(fresh_root, "m8_b1_block_b_retry"), fresh_root)
        document = generation.run_authorised_arm(fresh, FakeDeps(fresh), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        self.assertEqual(document["raw_attempt_count"], 15000)
        self.assertTrue(os.path.exists(os.path.join(output, generation.FAILURE_NAME)))

    def test_altered_checkpoint_or_raw_file_fails_and_checkpoint_is_not_copied(self):
        _root, output, _entry, deps, document = self._run("d1_seed44_block_b", mode="bad_before")
        self.assertIsNone(document)
        self.assertFalse(os.path.exists(output))
        self.assertTrue(deps.hash_calls)
        _root, output, _entry, deps, document = self._run("d1_seed43_block_a", mode="bad_after")
        self.assertIsNone(document)
        self.assertTrue(os.path.exists(os.path.join(output, generation.FAILURE_NAME)))
        self.assertFalse(os.path.exists(os.path.join(output, generation.MANIFEST_NAME)))
        self.assertGreater(len(deps.hash_calls), len(deps.expected))

        def alter(_entry, outputs):
            path = os.path.join(_entry["output_directory"], outputs[0]["relative_path"])
            with open(path, "ab") as handle:
                handle.write(b"x")

        _root, output, _entry, _deps, document = self._run("b1_block_a", hook=alter)
        self.assertIsNone(document)
        with open(os.path.join(output, generation.FAILURE_NAME), "rb") as handle:
            self.assertIn(b"raw_output_changed", handle.read())


if __name__ == "__main__":
    unittest.main()

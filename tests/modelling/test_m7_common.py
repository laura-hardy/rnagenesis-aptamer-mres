"""CPU/mock tests for the shared M7 primitives.

These tests do not open biological corpora, model weights, accepted run
directories, or a GPU. They create temporary files under a temporary directory
outside both repositories and use no torch.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
import tempfile
import types
import unittest
from unittest import mock

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

ROOT = "/home/laura/rnagenesis-aptamer-mres"
CONTRACT_PATH = os.path.join(ROOT, "scripts/modelling/m7_replicate_contract.py")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = load_module("m7_replicate_contract_for_common_tests", CONTRACT_PATH)
common = contract.common
M7Error = common.M7Error
RNA_MESSAGE = "ACGUACGUACGUACGU"
COMMIT = "c" * 40


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_tree(base, name="ckpt", payload=b"x"):
    root = os.path.join(base, name)
    for member in common.CHECKPOINT_MEMBERS:
        target = os.path.join(root, member)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(payload + member.encode("ascii"))
    return root


class _TempCase(unittest.TestCase):
    def setUp(self):
        self.temp = os.path.realpath(tempfile.mkdtemp(prefix="m7test"))
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil

        shutil.rmtree(self.temp, ignore_errors=True)


class PathDenialTests(unittest.TestCase):
    DENIED = (
        "/x/REF.csv",
        "/x/ref.csv",
        "/x/Eval.CSV",
        "/x/EVAL/anything",
        "/x/eVaL_set.txt",
        "/home/laura/Ref/data",
        "C:\\data\\EVAL.csv",
        "/x/\uff32\uff25\uff26.csv",
        "/x/my-ref.v2/data",
    )

    def test_ref_and_eval_denied_in_every_case_before_open(self):
        calls = []
        for path in self.DENIED:
            self.assertTrue(common.path_is_ref_or_eval(path), path)
            with self.assertRaises(M7Error) as caught:
                common.open_after_denial(path, "TRAIN_TEXT", calls.append)
            self.assertEqual(caught.exception.code, "ref_or_eval_access", path)
        for role in ("REF", "EVAL"):
            with self.assertRaises(M7Error) as caught:
                common.open_after_denial(contract.common.m6_contract().FUTURE_TRAIN_TEXT_PATH, role, calls.append)
            self.assertEqual(caught.exception.code, "ref_or_eval_access")
        self.assertEqual(calls, [])

    def test_resolved_target_is_checked_before_open(self):
        calls = []
        train = common.m6_contract().FUTURE_TRAIN_TEXT_PATH
        with self.assertRaises(M7Error) as caught:
            common.open_after_denial(train, "TRAIN_TEXT", calls.append, realpath=lambda path: "/x/EVAL.csv")
        self.assertEqual(caught.exception.code, "ref_or_eval_access")
        self.assertEqual(calls, [])

    def test_legitimate_paths_are_not_false_positives(self):
        m6 = common.m6_contract()
        for path in ("/x/reference/data", "/x/retrieval.csv", m6.FUTURE_TRAIN_TEXT_PATH, m6.ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY):
            self.assertFalse(common.path_is_ref_or_eval(path), path)
        opened = []
        self.assertEqual(common.open_after_denial(m6.FUTURE_TRAIN_TEXT_PATH, "TRAIN_TEXT", lambda path: opened.append(path) or "ok"), "ok")
        self.assertEqual(opened, [m6.FUTURE_TRAIN_TEXT_PATH])

    def test_sibling_and_m6_evidence_denied_before_open(self):
        calls = []
        m6_dir = common.RUN_ROOT + "/m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6/m6_pilot_manifest.json"
        other = common.RUN_ROOT + "/m4_b1_development_pool_d2b2041520d1_gpu1_attempt1/development_pool_manifest.json"
        bound = common.RUN_ROOT + "/m7_d1_replicate_seed43_unit"
        for path in (m6_dir, other):
            with self.assertRaises(M7Error) as caught:
                common.open_after_denial(path, "OWN_OUTPUT", calls.append, bound_output=bound)
            self.assertIn(caught.exception.code, ("sibling_evidence_access", "unexpected_biological_path_or_role"))
        with self.assertRaises(M7Error) as caught:
            common.open_after_denial(other, "VALIDATION_ARTIFACT", calls.append, bound_output=bound)
        self.assertEqual(caught.exception.code, "sibling_evidence_access")
        self.assertEqual(calls, [])
        accepted = common.m6_contract().ACCEPTED_VALIDATION_ARTIFACT_DIRECTORY
        self.assertEqual(common.assert_path_permitted(accepted + "/validation_noise.float32", "VALIDATION_ARTIFACT", bound_output=bound), accepted + "/validation_noise.float32")

    def test_wrong_role_path_and_obsolete_repository_data_refused(self):
        m6 = common.m6_contract()
        with self.assertRaises(M7Error) as caught:
            common.assert_path_permitted(m6.FUTURE_TRAIN_TEXT_PATH, "VALIDATION_CSV")
        self.assertEqual(caught.exception.code, "unexpected_biological_path_or_role")
        with self.assertRaises(M7Error) as caught:
            common.assert_path_permitted("/home/laura/rnagenesis-aptamer-mres/data/processed/x.csv", "TRAIN_TEXT")
        self.assertEqual(caught.exception.code, "unexpected_biological_path_or_role")
        with self.assertRaises(M7Error) as caught:
            common.assert_path_permitted(m6.FUTURE_TRAIN_TEXT_PATH, "SOMETHING_ELSE")
        self.assertEqual(caught.exception.code, "unexpected_biological_path_or_role")

    def test_m6_checkpoints_and_weights_are_forbidden_initialisation(self):
        name = "D1_generic-diffusion__data-d6cbc41a__lr-3e-5__ebs-32__seed-42__update-21__git-" + "6" * 40
        for path in (
            common.RUN_ROOT + "/m6_d1_diffusion_pilot_6fd611589d7a_gpu1_attempt6/" + name,
            "/anywhere/" + name.replace("update-21", "update-7"),
            "/anywhere/" + name.replace("update-21", "update-14"),
        ):
            with self.assertRaises(M7Error) as caught:
                common.assert_initialisation_input(path)
            self.assertEqual(caught.exception.code, "m6_checkpoint_forbidden", path)
        self.assertEqual(
            sorted(common.M6_FORBIDDEN_WEIGHT_SHA256.values()),
            ["m6_update_14", "m6_update_21", "m6_update_7"],
        )
        for weight in common.M6_FORBIDDEN_WEIGHT_SHA256:
            with self.assertRaises(M7Error) as caught:
                common.assert_initialisation_input("/home/laura/RNAGenesis/configs/rnagenesis/diffusion", weight)
            self.assertEqual(caught.exception.code, "m6_checkpoint_forbidden")
            with self.assertRaises(M7Error):
                common.assert_not_m6_weight(weight)
        self.assertTrue(common.assert_initialisation_input("/home/laura/RNAGenesis/configs/rnagenesis/diffusion", common.m6_contract().B1_WEIGHT_SHA256))

    def test_forbidden_hashes_match_the_tracked_records(self):
        with open(os.path.join(ROOT, "docs/fine_tuning/m6_pilot_implementation.md"), "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("47b2dc9b392ea766eee7e947f0f92f5a039c42ac714326104e719352d20b5924", text)
        with open(os.path.join(ROOT, "docs/log.md"), "r", encoding="utf-8") as handle:
            log = handle.read()
        for weight in common.M6_FORBIDDEN_WEIGHT_SHA256:
            self.assertIn(weight, log)


class CheckpointTreeTests(_TempCase):
    def test_valid_tree_has_exact_signatures(self):
        root = make_tree(self.temp)
        signatures = common.observe_checkpoint_tree_strict(root, self.temp)
        self.assertEqual(sorted(signatures), sorted(common.CHECKPOINT_MEMBERS))
        self.assertTrue(all(item[4] == 1 for item in signatures.values()))
        self.assertEqual(common.observe_checkpoint_tree_strict(root, self.temp), signatures)

    def test_unexpected_missing_and_special_members_rejected(self):
        root = make_tree(self.temp)
        with open(os.path.join(root, "extra.txt"), "wb") as handle:
            handle.write(b"x")
        with self.assertRaises(M7Error) as caught:
            common.observe_checkpoint_tree_strict(root, self.temp)
        self.assertEqual(caught.exception.code, "checkpoint_save_reload_incompatibility")
        self.assertNotIn("extra", caught.exception.detail)
        os.remove(os.path.join(root, "extra.txt"))
        with open(os.path.join(root, "unet", "extra.bin"), "wb") as handle:
            handle.write(b"x")
        with self.assertRaises(M7Error):
            common.observe_checkpoint_tree_strict(root, self.temp)
        os.remove(os.path.join(root, "unet", "extra.bin"))
        os.remove(os.path.join(root, "unet", "config.json"))
        with self.assertRaises(M7Error):
            common.observe_checkpoint_tree_strict(root, self.temp)
        os.mkfifo(os.path.join(root, "unet", "config.json"))
        with self.assertRaises(M7Error) as caught:
            common.observe_checkpoint_tree_strict(root, self.temp)
        self.assertEqual(caught.exception.code, "checkpoint_save_reload_incompatibility")

    def test_hard_linked_leaf_rejected(self):
        root = make_tree(self.temp)
        outside = os.path.join(self.temp, "outside.bin")
        os.link(os.path.join(root, "model_index.json"), outside)
        with self.assertRaises(M7Error) as caught:
            common.observe_checkpoint_tree_strict(root, self.temp)
        self.assertEqual(caught.exception.code, "checkpoint_ancestry_unsafe")
        with self.assertRaises(M7Error) as caught:
            common.stream_sha256(outside, require_single_link=True)
        self.assertEqual(caught.exception.code, "checkpoint_ancestry_unsafe")

    def test_symlinked_leaf_directory_root_and_ancestor_rejected(self):
        root = make_tree(self.temp)
        target = os.path.join(self.temp, "real.bin")
        with open(target, "wb") as handle:
            handle.write(b"x")
        leaf = os.path.join(root, "model_index.json")
        os.remove(leaf)
        os.symlink(target, leaf)
        with self.assertRaises(M7Error):
            common.observe_checkpoint_tree_strict(root, self.temp)
        with self.assertRaises(M7Error):
            common.stream_sha256(leaf)
        other = os.path.join(self.temp, "other")
        os.makedirs(other)
        real = make_tree(other, "ckpt")
        linked_root = os.path.join(self.temp, "linked")
        os.symlink(real, linked_root)
        with self.assertRaises(M7Error) as caught:
            common.observe_checkpoint_tree_strict(linked_root, self.temp)
        self.assertEqual(caught.exception.code, "checkpoint_ancestry_unsafe")
        linked_parent = os.path.join(self.temp, "linked_parent")
        os.symlink(other, linked_parent)
        with self.assertRaises(M7Error) as caught:
            common.observe_checkpoint_tree_strict(os.path.join(linked_parent, "ckpt"), None)
        self.assertEqual(caught.exception.code, "checkpoint_ancestry_unsafe")
        with self.assertRaises(M7Error):
            common.assert_no_symlink_ancestry(os.path.join(linked_parent, "ckpt"))

    def test_symlinked_subdirectory_rejected(self):
        root = make_tree(self.temp)
        elsewhere = os.path.join(self.temp, "elsewhere")
        os.makedirs(elsewhere)
        for member in ("config.json", "diffusion_pytorch_model.safetensors"):
            with open(os.path.join(elsewhere, member), "wb") as handle:
                handle.write(b"x")
        import shutil

        shutil.rmtree(os.path.join(root, "unet"))
        os.symlink(elsewhere, os.path.join(root, "unet"))
        with self.assertRaises(M7Error):
            common.observe_checkpoint_tree_strict(root, self.temp)

    def test_checkpoint_must_be_a_direct_child_of_the_bound_output(self):
        nested = os.path.join(self.temp, "nest")
        os.makedirs(nested)
        root = make_tree(nested)
        with self.assertRaises(M7Error) as caught:
            common.observe_checkpoint_tree_strict(root, self.temp)
        self.assertEqual(caught.exception.code, "checkpoint_overwrite_risk")

    def test_other_device_rejected_where_supported(self):
        root = make_tree(self.temp)
        real_lstat = os.lstat

        def other_device(path):
            measured = real_lstat(path)
            fields = {name: getattr(measured, name) for name in ("st_mode", "st_dev", "st_nlink", "st_size", "st_mtime_ns", "st_ino")}
            if path.endswith("config.json"):
                fields["st_dev"] = measured.st_dev + 1
            return types.SimpleNamespace(**fields)

        with self.assertRaises(M7Error) as caught:
            common.observe_checkpoint_tree_strict(root, self.temp, lstat=other_device)
        self.assertEqual(caught.exception.code, "checkpoint_ancestry_unsafe")
        self.assertTrue(common.observe_checkpoint_tree_strict(root, self.temp, lstat=other_device, check_device=False))

        def other_root_device(path):
            measured = real_lstat(path)
            fields = {name: getattr(measured, name) for name in ("st_mode", "st_dev", "st_nlink", "st_size", "st_mtime_ns", "st_ino")}
            if os.path.abspath(path) == os.path.abspath(root):
                fields["st_dev"] = measured.st_dev + 1
            return types.SimpleNamespace(**fields)

        with self.assertRaises(M7Error) as caught:
            common.observe_checkpoint_tree_strict(root, self.temp, lstat=other_root_device)
        self.assertEqual(caught.exception.code, "checkpoint_ancestry_unsafe")


class StreamingDigestTests(_TempCase):
    def test_streaming_digest_is_bounded_and_correct(self):
        path = os.path.join(self.temp, "blob.bin")
        payload = os.urandom(3 * 1024 * 1024 + 17)
        with open(path, "wb") as handle:
            handle.write(payload)
        sizes = []
        real_read = os.read

        def spy(descriptor, count):
            sizes.append(count)
            return real_read(descriptor, count)

        with mock.patch("os.read", spy):
            value = common.stream_sha256(path, chunk_bytes=1024 * 1024)
        self.assertEqual(value, hashlib.sha256(payload).hexdigest())
        self.assertTrue(sizes and max(sizes) <= 1024 * 1024)
        for bad in (0, -1, 64 * 1024 * 1024 + 1, True, "1"):
            with self.assertRaises(M7Error):
                common.stream_sha256(path, chunk_bytes=bad)

    def test_file_changed_while_hashed_is_detected(self):
        path = os.path.join(self.temp, "blob.bin")
        with open(path, "wb") as handle:
            handle.write(b"a" * 4096)
        real_read = os.read
        state = {"first": True}

        def mutate(descriptor, count):
            data = real_read(descriptor, count)
            if state["first"]:
                state["first"] = False
                with open(path, "ab") as handle:
                    handle.write(b"b")
            return data

        with mock.patch("os.read", mutate):
            with self.assertRaises(M7Error) as caught:
                common.stream_sha256(path, chunk_bytes=1024)
        self.assertEqual(caught.exception.code, "checkpoint_save_reload_incompatibility")

    def test_non_regular_and_missing_targets_refused(self):
        with self.assertRaises(M7Error) as caught:
            common.stream_sha256(self.temp)
        self.assertEqual(caught.exception.code, "checkpoint_ancestry_unsafe")
        with self.assertRaises(M7Error) as caught:
            common.stream_sha256(os.path.join(self.temp, "missing"))
        self.assertEqual(caught.exception.code, "filesystem_error")


class AtomicWriteTests(_TempCase):
    def test_file_then_replace_then_directory_are_flushed_in_order(self):
        events = []
        real_fsync = os.fsync
        real_replace = os.replace

        def fsync(descriptor):
            events.append("fsync_directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "fsync_file")
            real_fsync(descriptor)

        def replace(source, target):
            events.append("replace")
            real_replace(source, target)

        with mock.patch("os.fsync", fsync), mock.patch("os.replace", replace):
            target = common.write_atomic_json(self.temp, "x.json", {"a": 1})
        self.assertEqual(events, ["fsync_file", "replace", "fsync_directory"])
        with open(target, "rb") as handle:
            self.assertEqual(handle.read(), common.canonical_json({"a": 1}))
        self.assertEqual(sorted(os.listdir(self.temp)), ["x.json"])

    def test_short_writes_continue_until_complete(self):
        real_write = os.write

        def one_byte(descriptor, view):
            return real_write(descriptor, bytes(view)[:1])

        with mock.patch("os.write", one_byte):
            target = common.write_atomic_bytes(self.temp, "short.bin", b"abcdef")
        with open(target, "rb") as handle:
            self.assertEqual(handle.read(), b"abcdef")

    def test_failure_and_interrupt_leave_no_partial_and_no_target(self):
        for failure in (OSError("disk"), KeyboardInterrupt(), SystemExit(3)):
            with mock.patch("os.fsync", side_effect=failure):
                with self.assertRaises(type(failure)):
                    common.write_atomic_json(self.temp, "y.json", {"a": 1})
            self.assertEqual(os.listdir(self.temp), [])
        with mock.patch("os.write", return_value=0):
            with self.assertRaises(OSError):
                common.write_atomic_json(self.temp, "z.json", {"a": 1})
        self.assertEqual(os.listdir(self.temp), [])

    def test_exclusive_temporary_refuses_a_stale_partial(self):
        with open(os.path.join(self.temp, "x.json.partial"), "wb") as handle:
            handle.write(b"stale")
        with self.assertRaises(FileExistsError):
            common.write_atomic_json(self.temp, "x.json", {"a": 1})

    def test_checkpoint_tree_flush_covers_every_file_and_directory(self):
        root = make_tree(self.temp)
        kinds = []
        real_fsync = os.fsync

        def fsync(descriptor):
            kinds.append("dir" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file")
            real_fsync(descriptor)

        with mock.patch("os.fsync", fsync):
            common.fsync_checkpoint_tree(root)
        self.assertEqual(kinds.count("file"), 4)
        self.assertGreaterEqual(kinds.count("dir"), 3)


class ConsumptionTests(_TempCase):
    def payload(self):
        return {"authorisation_id": "m7_unit_seed43", "reuse_permitted": False}

    def test_consumption_creates_records_and_flushes_directory_and_run_root(self):
        output = os.path.join(self.temp, "m7_unit_seed43")
        flushed = []
        real_fsync_directory = common.fsync_directory

        def spy(path):
            flushed.append(path)
            real_fsync_directory(path)

        with mock.patch.object(common, "fsync_directory", spy):
            common.consume_output_directory(output, self.payload(), self.temp)
        self.assertIn(output, flushed)
        self.assertIn(self.temp, flushed)
        self.assertTrue(os.path.isfile(os.path.join(output, common.CONSUMPTION_RECORD_NAME)))

    def test_second_use_is_refused_and_leaves_the_directory_alone(self):
        output = os.path.join(self.temp, "m7_unit_seed43")
        common.consume_output_directory(output, self.payload(), self.temp)
        before = sorted(os.listdir(output))
        with self.assertRaises(M7Error) as caught:
            common.consume_output_directory(output, self.payload(), self.temp)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertFalse(getattr(caught.exception, "directory_created", False))
        self.assertEqual(sorted(os.listdir(output)), before)

    def test_shape_and_symlink_refusals(self):
        for bad in (os.path.join(self.temp, "a", "b"), "relative", self.temp + "/../x", "/home/laura/elsewhere/x"):
            with self.assertRaises(M7Error):
                common.consume_output_directory(bad, self.payload(), self.temp)
        real = os.path.join(self.temp, "real")
        os.makedirs(real)
        link = os.path.join(self.temp, "link")
        os.symlink(real, link)
        with self.assertRaises(M7Error):
            common.consume_output_directory(os.path.join(link, "m7_x"), self.payload(), self.temp)

    def test_consumption_record_failure_marks_the_directory_created(self):
        output = os.path.join(self.temp, "m7_unit_seed43")
        with mock.patch.object(common, "write_atomic_json", side_effect=OSError("disk")):
            with self.assertRaises(M7Error) as caught:
                common.consume_output_directory(output, self.payload(), self.temp)
        self.assertEqual(caught.exception.code, "authorization_reuse")
        self.assertTrue(caught.exception.directory_created)
        self.assertTrue(os.path.isdir(output))
        other = os.path.join(self.temp, "m7_unit_seed44")
        with mock.patch.object(common, "write_atomic_json", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt) as interrupted:
                common.consume_output_directory(other, self.payload(), self.temp)
        self.assertTrue(interrupted.exception.directory_created)

    def test_each_entry_directory_is_consumed_independently(self):
        first = os.path.join(self.temp, "m7_unit_seed43")
        second = os.path.join(self.temp, "m7_unit_seed44")
        common.consume_output_directory(first, self.payload(), self.temp)
        self.assertFalse(os.path.lexists(second))
        common.consume_output_directory(second, self.payload(), self.temp)
        self.assertTrue(os.path.isdir(first) and os.path.isdir(second))


class FailureRecordTests(_TempCase):
    CONTEXT = {
        "authorisation_id": "m7_unit_seed43",
        "authorization_commit": "a" * 40,
        "authorization_parent_commit": "b" * 40,
        "executing_implementation_commit": "b" * 40,
        "output_directory": "/x/m7_unit_seed43",
    }

    def progress(self):
        progress = common.new_progress(43, "replicate")
        progress.update(
            {
                "stage": "checkpoint_save",
                "epoch": 3,
                "update": 63,
                "microbatch": None,
                "candidate": {"epoch": 3, "seed": 43},
                "partial_checkpoint": {"directory_name": "ckpt-name", "epoch": 3, "state": "saved_unverified"},
                "retained_checkpoint_epochs": [2, 1],
            }
        )
        return progress

    def read(self):
        import json

        with open(os.path.join(self.temp, common.FAILURE_RECORD_NAME), "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))

    def test_every_base_exception_becomes_a_complete_record(self):
        for index, exc in enumerate((RuntimeError(RNA_MESSAGE), KeyboardInterrupt(), SystemExit(1), OSError("x"), M7Error("identity_mismatch", "bad"))):
            directory = os.path.join(self.temp, "d%d" % index)
            os.makedirs(directory)
            error = common.record_consumed_failure(directory, exc, self.CONTEXT, self.progress(), "manifest.json")
            with open(os.path.join(directory, common.FAILURE_RECORD_NAME), "rb") as handle:
                import json

                record = json.loads(handle.read().decode("utf-8"))
            self.assertEqual(sorted(record), sorted(common.FAILURE_KEYS))
            self.assertEqual((record["seed"], record["epoch"], record["update"], record["stage"]), (43, 3, 63, "checkpoint_save"))
            self.assertEqual(record["candidate"], {"epoch": 3, "seed": 43})
            self.assertEqual(record["partial_checkpoint"]["state"], "saved_unverified")
            self.assertEqual(record["retained_checkpoint_epochs"], [1, 2])
            self.assertFalse(record["resumable"] or record["reuse_permitted"] or record["m7_complete"] or record["scientific_run_completed"])
            self.assertEqual(record["consumption_state"], "consumed_failed")
            self.assertNotIn(RNA_MESSAGE, repr(record))
            self.assertIn(record["code"], common.FAILURE_CODES)
            self.assertIsNone(error.secondary_failure)
        self.assertEqual(common.normalise_exception(KeyboardInterrupt()).code, "interrupted")
        self.assertEqual(common.normalise_exception(SystemExit(2)).code, "interrupted")

    def test_error_context_overrides_progress_and_sequence_detail_is_omitted(self):
        error = M7Error("identity_mismatch", "text " + RNA_MESSAGE, stage="validation", seed=44, epoch=2, update=42, microbatch=3)
        common.record_consumed_failure(self.temp, error, self.CONTEXT, self.progress(), "manifest.json")
        record = self.read()
        self.assertEqual((record["seed"], record["epoch"], record["update"], record["microbatch"], record["stage"]), (44, 2, 42, 3, "validation"))
        self.assertEqual(record["detail"], "failure detail omitted")

    def test_failure_writer_failure_keeps_the_primary_and_reports_the_secondary(self):
        primary = RuntimeError("primary")

        def failing_writer(directory, name, payload):
            raise OSError("cannot write")

        error = common.record_consumed_failure(self.temp, primary, self.CONTEXT, self.progress(), "manifest.json", writer=failing_writer)
        self.assertEqual(error.code, "unexpected_runtime_failure")
        self.assertEqual(error.secondary_failure["class"], "OSError")
        self.assertFalse(os.path.exists(os.path.join(self.temp, common.FAILURE_RECORD_NAME)))
        line = common.format_error_line(error)
        self.assertIn("secondary_failure=", line)
        self.assertIn("unexpected_runtime_failure", line)

        def interrupting_writer(directory, name, payload):
            raise KeyboardInterrupt()

        again = common.record_consumed_failure(self.temp, SystemExit(1), self.CONTEXT, self.progress(), "manifest.json", writer=interrupting_writer)
        self.assertEqual(again.code, "interrupted")
        self.assertEqual(again.secondary_failure["class"], "KeyboardInterrupt")
        with self.assertRaises(KeyboardInterrupt):
            common.record_consumed_failure(self.temp, RuntimeError("x"), self.CONTEXT, self.progress(), "manifest.json", writer=interrupting_writer)

    def test_existing_failure_stays_and_claimed_success_is_removed(self):
        common.write_atomic_json(self.temp, "manifest.json", {"claimed": True})
        common.record_consumed_failure(self.temp, RuntimeError("one"), self.CONTEXT, self.progress(), "manifest.json")
        self.assertFalse(os.path.exists(os.path.join(self.temp, "manifest.json")))
        first = self.read()
        common.record_consumed_failure(self.temp, M7Error("identity_mismatch", "later"), self.CONTEXT, self.progress(), "manifest.json")
        self.assertEqual(self.read(), first)

    def test_unregistered_code_is_recorded_as_incomplete_evidence(self):
        common.record_consumed_failure(self.temp, M7Error("made_up_code", "x"), self.CONTEXT, self.progress(), "manifest.json")
        self.assertEqual(self.read()["code"], "incomplete_evidence_or_manifest")


class EnvironmentTests(_TempCase):
    def parent(self, **extra):
        parent = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/home/laura", "USER": "laura", "SECRET_STRAY": "1"}
        parent.pop("SECRET_STRAY")
        parent.update(extra)
        return parent

    def test_strict_allow_list_and_isolation(self):
        output = os.path.join(self.temp, "m7_unit_seed43")
        os.makedirs(output)
        parent = self.parent(DISPLAY=":0", EDITOR="vi", XDG_SESSION_ID="9", LC_TIME="x", GIT_EDITOR="true")
        before = dict(parent)
        child = common.build_child_environment(parent, 1, output)
        self.assertEqual(parent, before)
        paths = common.isolated_paths(output)
        for key in ("HOME", "TMPDIR", "TEMP", "TMP", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "HF_HOME", "TORCH_HOME", "PYTHONPYCACHEPREFIX"):
            self.assertEqual(child[key], paths[key])
            self.assertTrue(child[key].startswith(output + os.sep))
        allowed = set(common.ENVIRONMENT_ALLOW_LIST) | set(common.OFFLINE_CONTROLS) | set(paths) | {
            "PATH",
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONNOUSERSITE",
            "CUDA_VISIBLE_DEVICES",
            "CUDA_DEVICE_ORDER",
        }
        self.assertTrue(set(child) <= allowed, sorted(set(child) - allowed))
        self.assertEqual(child["PATH"], common.FIXED_CHILD_PATH)
        for dropped in ("DISPLAY", "EDITOR", "XDG_SESSION_ID", "USER", "LC_TIME", "GIT_EDITOR"):
            self.assertNotIn(dropped, child)
        self.assertNotEqual(child["HOME"], "/home/laura")
        self.assertEqual((child["CUDA_VISIBLE_DEVICES"], child["CUDA_DEVICE_ORDER"], child["PYTHONDONTWRITEBYTECODE"]), ("1", "PCI_BUS_ID", "1"))
        for key in common.OFFLINE_CONTROLS:
            self.assertEqual(child[key], "1")
        self.assertTrue(common.assert_child_environment(child, output))

    def test_stray_and_dangerous_parent_variables_are_rejected(self):
        output = os.path.join(self.temp, "m7_unit_seed43")
        os.makedirs(output)
        rejected = (
            {"PYTHONPATH": "/x"},
            {"PYTHONHOME": "/x"},
            {"PYTHONSTARTUP": "/x"},
            {"LD_PRELOAD": "/x.so"},
            {"GIT_DIR": "/x"},
            {"GIT_WORK_TREE": "/x"},
            {"GIT_CONFIG_GLOBAL": "/x"},
            {"GIT_EXEC_PATH": "/x"},
            {"GIT_SSH_COMMAND": "x"},
            {"HF_TOKEN": "x"},
            {"GITHUB_TOKEN": "x"},
            {"AWS_ACCESS_KEY_ID": "x"},
            {"MY_SERVICE_PASSWORD": "x"},
            {"SOME_API_KEY": "x"},
            {"OAUTH_CLIENT_SECRET": "x"},
            {"CUDA_VISIBLE_DEVICES": "0"},
            {"CUDA_DEVICE_ORDER": "FASTEST_FIRST"},
        )
        for extra in rejected:
            with self.assertRaises(M7Error) as caught:
                common.build_child_environment(self.parent(**extra), 1, output)
            self.assertEqual(caught.exception.code, "environment_rejected", extra)
        for benign in ({"GIT_EDITOR": "true"}, {"CUDA_VISIBLE_DEVICES": "1"}, {"TOKENIZERS_PARALLELISM": "false"}):
            common.build_child_environment(self.parent(**benign), 1, output)

    def test_output_inside_a_repository_is_rejected(self):
        for inside in (common.MRES_ROOT + "/x", common.RNAGENESIS_ROOT + "/x"):
            with self.assertRaises(M7Error) as caught:
                common.build_child_environment(self.parent(), 1, inside)
            self.assertEqual(caught.exception.code, "environment_rejected")

    def test_worker_side_check_refuses_stray_names_and_unset_controls(self):
        output = os.path.join(self.temp, "m7_unit_seed43")
        os.makedirs(output)
        child = common.build_child_environment(self.parent(), 1, output)
        stray = dict(child, PYTHONPATH="/x")
        with self.assertRaises(M7Error):
            common.assert_child_environment(stray, output)
        for key in ("HF_HUB_OFFLINE", "HOME", "PYTHONDONTWRITEBYTECODE", "TMPDIR"):
            broken = dict(child)
            broken[key] = "0" if key != "HOME" else "/home/laura"
            with self.assertRaises(M7Error):
                common.assert_child_environment(broken, output)

    def test_isolated_directories_are_created_inside_the_output(self):
        output = os.path.join(self.temp, "m7_unit_seed43")
        os.makedirs(output)
        created = common.create_isolated_directories(output)
        self.assertTrue(created and all(os.path.isdir(path) and path.startswith(output + os.sep) for path in created))


class LdLibraryPathTests(_TempCase):
    """The authorisation-bound ``LD_LIBRARY_PATH``: exact value or nothing, never inherited."""

    VALUE = "/home/laura/miniconda3/envs/rnagenesis-h200/lib:/usr/local/cuda/lib64"

    def parent(self, **extra):
        parent = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        parent.update(extra)
        return parent

    def output(self):
        output = os.path.join(self.temp, "m7_unit_seed43")
        os.makedirs(output, exist_ok=True)
        return output

    def test_a_required_matching_value_is_the_only_one_to_enter_the_child(self):
        output = self.output()
        parent = self.parent(LD_LIBRARY_PATH=self.VALUE)
        before = dict(parent)
        child = common.build_child_environment(parent, 1, output, self.VALUE)
        self.assertEqual(parent, before)
        self.assertEqual(child["LD_LIBRARY_PATH"], self.VALUE)
        paths = common.isolated_paths(output)
        allowed = set(common.ENVIRONMENT_ALLOW_LIST) | set(common.OFFLINE_CONTROLS) | set(paths) | {
            "PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER", "LD_LIBRARY_PATH",
        }
        self.assertTrue(set(child) <= allowed, sorted(set(child) - allowed))
        self.assertEqual(child["PATH"], common.FIXED_CHILD_PATH)
        self.assertTrue(common.assert_child_environment(child, output, self.VALUE))
        record = common.resolve_ld_library_path(parent, self.VALUE)
        self.assertEqual(record, {"bound": True, "passed_to_child": True, "sha256": digest(self.VALUE)})
        self.assertEqual(common.ld_library_path_digest(self.VALUE), digest(self.VALUE))
        self.assertTrue(common.assert_ld_library_path_record(record))
        self.assertEqual(common.observe_child_ld_library_path(child, self.VALUE), record)

    def test_a_required_value_that_is_absent_is_refused_without_naming_a_value(self):
        output = self.output()
        with self.assertRaises(M7Error) as caught:
            common.build_child_environment(self.parent(), 1, output, self.VALUE)
        self.assertEqual(caught.exception.code, "environment_rejected")
        self.assertNotIn(self.VALUE, str(caught.exception))
        with self.assertRaises(M7Error):
            common.resolve_ld_library_path(self.parent(), self.VALUE)

    def test_a_changed_or_unexpected_value_is_refused(self):
        output = self.output()
        for live in (
            self.VALUE + ":/extra/lib",
            "/extra/lib:" + self.VALUE,
            self.VALUE + ":",
            self.VALUE + "/",
            "/home/laura/miniconda3/envs/rnagenesis-h200/lib",
            "/usr/local/cuda/lib64:/home/laura/miniconda3/envs/rnagenesis-h200/lib",
            "",
        ):
            with self.assertRaises(M7Error, msg=live) as caught:
                common.build_child_environment(self.parent(LD_LIBRARY_PATH=live), 1, output, self.VALUE)
            self.assertEqual(caught.exception.code, "environment_rejected")
            self.assertNotIn(live or "<empty>", str(caught.exception).replace(self.VALUE, ""))
            with self.assertRaises(M7Error):
                common.resolve_ld_library_path(self.parent(LD_LIBRARY_PATH=live), self.VALUE)

    def test_an_unbound_authorisation_drops_any_ambient_value(self):
        output = self.output()
        child = common.build_child_environment(self.parent(LD_LIBRARY_PATH=self.VALUE), 1, output, None)
        self.assertNotIn("LD_LIBRARY_PATH", child)
        self.assertEqual(common.resolve_ld_library_path(self.parent(LD_LIBRARY_PATH=self.VALUE), None), common.unbound_ld_library_path_record())
        self.assertEqual(common.resolve_ld_library_path(self.parent(), None), common.unbound_ld_library_path_record())
        self.assertTrue(common.assert_child_environment(child, output))
        self.assertEqual(common.observe_child_ld_library_path(child, None), common.unbound_ld_library_path_record())

    def test_the_default_build_never_inherits_the_parent_value(self):
        output = self.output()
        child = common.build_child_environment(self.parent(LD_LIBRARY_PATH=self.VALUE), 1, output)
        self.assertNotIn("LD_LIBRARY_PATH", child)

    def test_a_live_mapping_that_is_not_a_dict_is_accepted_and_not_mutated(self):
        class Live(dict):
            pass

        record = common.resolve_ld_library_path(Live(LD_LIBRARY_PATH=self.VALUE), self.VALUE)
        self.assertIs(record["bound"], True)
        with self.assertRaises(M7Error):
            common.resolve_ld_library_path(["LD_LIBRARY_PATH"], self.VALUE)

    def test_malformed_bindings_are_refused_on_their_text_alone(self):
        for bad in (
            "",
            " /lib",
            "/lib ",
            "lib",
            "./lib",
            "/lib:",
            ":/lib",
            "/lib::/usr/lib",
            "/lib/../etc",
            "/lib/./x",
            "/lib//x",
            "/lib/",
            "/lib with space",
            "/lib/$HOME",
            "/lib/%s/x\n",
            "/home/laura/data/REF.csv",
            "/home/laura/data/eval/lib",
            common.RNAGENESIS_ROOT + "/.cache/lib",
            "/" + "a" * common.LD_LIBRARY_PATH_MAXIMUM_LENGTH,
            None,
            7,
            ["/lib"],
        ):
            if bad is None:
                self.assertIsNone(common.assert_ld_library_path_binding(bad))
                continue
            with self.assertRaises(M7Error, msg=repr(bad)) as caught:
                common.assert_ld_library_path_binding(bad)
            self.assertEqual(caught.exception.code, "environment_rejected")
        self.assertEqual(common.assert_ld_library_path_binding("/lib"), "/lib")
        self.assertEqual(common.assert_ld_library_path_binding("/usr/lib/x86_64-linux-gnu:/opt/cuda-12.1/lib64"), "/usr/lib/x86_64-linux-gnu:/opt/cuda-12.1/lib64")

    def test_the_worker_side_check_is_exact(self):
        output = self.output()
        child = common.build_child_environment(self.parent(LD_LIBRARY_PATH=self.VALUE), 1, output, self.VALUE)
        for broken in (
            {key: value for key, value in child.items() if key != "LD_LIBRARY_PATH"},
            dict(child, LD_LIBRARY_PATH=self.VALUE + ":/extra"),
        ):
            with self.assertRaises(M7Error):
                common.assert_child_environment(broken, output, self.VALUE)
        unbound = common.build_child_environment(self.parent(), 1, output, None)
        with self.assertRaises(M7Error):
            common.assert_child_environment(dict(unbound, LD_LIBRARY_PATH=self.VALUE), output)
        with self.assertRaises(M7Error):
            common.assert_child_environment(dict(unbound, LD_LIBRARY_PATH=self.VALUE), output, None)
        with self.assertRaises(M7Error):
            common.observe_child_ld_library_path(dict(unbound, LD_LIBRARY_PATH=self.VALUE), None)

    def test_a_worker_that_has_not_yet_read_its_entry_tolerates_only_a_well_formed_name(self):
        output = self.output()
        child = common.build_child_environment(self.parent(LD_LIBRARY_PATH=self.VALUE), 1, output, self.VALUE)
        self.assertTrue(common.assert_child_environment(child, output, ld_library_path_pending=True))
        with self.assertRaises(M7Error):
            common.assert_child_environment(dict(child, LD_LIBRARY_PATH="relative"), output, ld_library_path_pending=True)
        with self.assertRaises(M7Error):
            common.assert_child_environment(child, output)

    def test_the_record_validator_refuses_inconsistent_records(self):
        good = {"bound": True, "passed_to_child": True, "sha256": digest("x")}
        self.assertTrue(common.assert_ld_library_path_record(good))
        for bad in (
            dict(good, sha256=None),
            dict(good, sha256="short"),
            dict(good, passed_to_child=False),
            {"bound": False, "passed_to_child": False, "sha256": digest("x")},
            {"bound": False, "passed_to_child": True, "sha256": None},
            dict(good, bound="yes"),
            dict(good, extra=1),
            {"bound": True},
        ):
            with self.assertRaises(M7Error, msg=str(bad)):
                common.assert_ld_library_path_record(bad)


class GpuBindingTests(unittest.TestCase):
    ENTRY = {
        "cuda_visible_devices": "1",
        "gpu_uuid": "GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f",
        "logical_device": "cuda:0",
        "pci_bus": "00000000:61:00.0",
        "physical_gpu_index": 1,
    }

    def observation(self, **changes):
        base = {
            "cuda_visible_devices": "1",
            "device_count": 1,
            "logical_device": "cuda:0",
            "pci_bus": "00000000:61:00.0",
            "physical_index": 1,
            "source": "nvidia_smi_physical_index",
            "uuid": "GPU-ca3cb287-b8d7-b344-64e3-92193cc2ae5f",
        }
        base.update(changes)
        return base

    def test_matching_observation_passes(self):
        self.assertTrue(common.assert_runtime_gpu_binding(self.ENTRY, self.observation()))
        self.assertTrue(common.assert_runtime_gpu_binding(self.ENTRY, self.observation(source="torch_device_properties")))

    def test_every_mismatch_is_refused(self):
        for changes in (
            {"logical_device": "cuda:1"},
            {"device_count": 2},
            {"cuda_visible_devices": "0"},
            {"physical_index": 0},
            {"uuid": "GPU-00000000-0000-0000-0000-000000000000"},
            {"pci_bus": "00000000:41:00.0"},
            {"source": "guess"},
        ):
            with self.assertRaises(M7Error) as caught:
                common.assert_runtime_gpu_binding(self.ENTRY, self.observation(**changes))
            self.assertEqual(caught.exception.code, "identity_mismatch", changes)
        incomplete = self.observation()
        del incomplete["uuid"]
        with self.assertRaises(M7Error):
            common.assert_runtime_gpu_binding(self.ENTRY, incomplete)


class FreeSpaceTests(unittest.TestCase):
    def stat(self, available):
        return lambda path: types.SimpleNamespace(f_bavail=available // 4096, f_frsize=4096)

    def test_budget_is_integer_arithmetic_and_recorded(self):
        weight = common.m6_contract().B1_WEIGHT_BYTES
        budget = common.free_space_budget("/x", 5, statvfs=self.stat(10**15))
        per = weight + 4 * 1024 * 1024
        subtotal = per * 5 + 2 * 1024**3
        self.assertEqual(budget["required_bytes"], subtotal + subtotal // 10 + 20 * 1024**3)
        self.assertEqual(budget["per_checkpoint_bytes"], per)
        self.assertEqual(budget["checkpoint_count"], 5)
        self.assertTrue(budget["sufficient"])
        self.assertTrue(all(isinstance(value, (int, bool)) for value in budget.values()))

    def test_refusal_below_the_budget_and_bad_counts(self):
        required = common.free_space_budget("/x", 5, statvfs=self.stat(0))["required_bytes"]
        with self.assertRaises(M7Error) as caught:
            common.assert_free_space("/x", 5, statvfs=self.stat(required - 4096))
        self.assertEqual(caught.exception.code, "insufficient_free_space")
        self.assertTrue(common.assert_free_space("/x", 5, statvfs=self.stat(required + 4096))["sufficient"])
        for bad in (0, -1, True, "5"):
            with self.assertRaises(M7Error):
                common.free_space_budget("/x", bad, statvfs=self.stat(10**15))


class RankingTests(unittest.TestCase):
    def test_lowest_mse_first_then_earlier_epoch_on_exact_tie(self):
        self.assertEqual(common.rank_validation_candidates({1: "0.5", 2: "0.4", 3: "0.3", 4: "0.35", 5: "0.31"}), [3, 5, 4, 2, 1])
        self.assertEqual(common.rank_validation_candidates({1: "0.3", 2: "0.3", 3: "0.4", 4: "0.3", 5: "0.5"}), [1, 2, 4, 3, 5])
        self.assertEqual(common.rank_validation_candidates({1: 0.2, 2: 0.2, 3: 0.2, 4: 0.2, 5: 0.2}), [1, 2, 3, 4, 5])
        near = {1: "0.30000000000000004", 2: "0.3", 3: "1", 4: "1", 5: "1"}
        self.assertEqual(common.rank_validation_candidates(near)[:2], [2, 1])

    def test_update_zero_and_other_epochs_cannot_enter_the_ranking(self):
        for bad in (
            {0: "0.1", 1: "0.2", 2: "0.3", 3: "0.4", 4: "0.5", 5: "0.6"},
            {1: "0.2", 2: "0.3", 3: "0.4", 4: "0.5"},
            {1: "0.2", 2: "0.3", 3: "0.4", 4: "0.5", 5: "0.6", 6: "0.7"},
            {1: "nan", 2: "0.3", 3: "0.4", 4: "0.5", 5: "0.6"},
        ):
            with self.assertRaises(M7Error):
                common.rank_validation_candidates(bad)


class SequenceTextTests(unittest.TestCase):
    def test_sequence_text_is_refused_in_evidence(self):
        for bad in ({"sequence": "x"}, {"a": [{"raw_decoded_text": "x"}]}, {"a": RNA_MESSAGE}):
            with self.assertRaises(M7Error):
                common.reject_sequence_text(bad)
        self.assertTrue(common.reject_sequence_text({"a": "ACGU", "b": ["not a sequence"], "c": "d" * 64}))


if __name__ == "__main__":
    unittest.main()

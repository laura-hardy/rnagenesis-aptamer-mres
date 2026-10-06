"""CPU/mock tests for the inactive M6 update-21 diagnostic-generation stage.

No GPU is queried, no checkpoint weight or EncDec weight is read, generation.py
is never run, and TRAIN, VALIDATION, REF, and EVAL are never opened. Accepted
evidence (the schedule, the B1 pool, the closed training manifest) is read
only, and only for hash, size, and recomputation checks. End-to-end runs use a
synthetic world in a temporary directory with fake git, GPU, and generation.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import random
import shutil
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
MODULE_PATH = os.path.join(ROOT, "scripts/modelling/m6_diagnostic_generation.py")
CONFIG_PATH = os.path.join(ROOT, "config/experiments/D1_update21_diagnostic_generation.yaml")
PILOT_CONFIG_PATH = os.path.join(ROOT, "config/experiments/D1_diffusion_pilot.yaml")
RNAGENESIS = "/home/laura/RNAGenesis"
SCHEDULE_DIR = "/home/laura/rnagenesis-mres-runs/m4_b1_development_pool_schedule_d2b2041520d1"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


diag = load_module("m6_diagnostic_generation_under_test", MODULE_PATH)
b1 = diag.b1_runner()
contract = diag.m6_contract()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    with open(path, "rb") as handle:
        return handle.read()


def inactive_config():
    return diag.load_config_bytes(read(CONFIG_PATH))


def real_metrics_module():
    return b1.load_metrics_from_verified_source(read(os.path.join(ROOT, diag.METRICS_RELATIVE)))


def real_cleaner():
    return b1.load_cleaner_from_verified_source(read(str(b1.APPROVED_CLEANER)))


def synthetic_invocation(index, requested):
    return {
        "original_attempt_indexes": [index],
        "actual_chunk_size": 1,
        "expected_batch_positions": [0],
        "target_length": requested,
        "invocation_index": index,
        "max_seq_len": requested + 1,
        "invocation_seed": 44000 + index,
        "batch_num": 1,
    }


def build_attempts(rows):
    """rows: (raw_text, requested_length). Records come from the approved cleaner."""
    cleaner = real_cleaner()
    attempts = []
    for index, (raw, requested) in enumerate(rows):
        attempts.extend(b1.map_invocation_output((raw + "\n").encode("utf-8"), synthetic_invocation(index, requested), cleaner))
    return attempts


def distinct_body(index, length=30):
    """A distinct valid ACGU body per index. Base-4 digits make collisions impossible."""
    digits = []
    value = index
    for _ in range(12):
        digits.append("ACGU"[value % 4])
        value //= 4
    return ("".join(digits) * 4)[:length]


def good_rows(count=1000, length=30):
    return [("11" + distinct_body(i, length), length) for i in range(count)]


TRAIN = ["ACGU" * 8, "GGGAAACCCUUU" * 3, "UUUUAAAACCCCGGGG" * 2]


def guardrail_values(rows, train=TRAIN):
    metrics = real_metrics_module()
    result = diag.evaluate_guardrails(metrics, build_attempts(rows), train)
    return result, {item["id"]: item for item in result["decisions"]}


class InactiveGateTests(unittest.TestCase):
    def test_checked_in_configuration_is_inactive_and_binds_nothing(self):
        config = inactive_config()
        self.assertEqual(diag.classify_configuration(config), "inactive")
        self.assertIs(config["consumable_by_executable_workflow"], False)
        self.assertTrue(diag.assert_inactive_configuration(config))
        block = config["diagnostic_generation_authorisation"]
        for key in ("physical_gpu_index", "gpu_uuid", "pci_bus", "cuda_visible_devices", "output_directory", "evidence_directory",
                    "authorisation_timestamp", "authorisation_id", "scope", "phase", "implementation_file_hashes"):
            self.assertIsNone(block[key], key)
        self.assertEqual(block["permitted_roles"], [])
        self.assertEqual(block["activation_status"], "inactive_no_authorisation")
        self.assertIsNone(config["execution"]["output_directory"])
        text = read(CONFIG_PATH).decode("utf-8")
        body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
        self.assertNotIn("\n  authorization_commit:", body)
        self.assertNotIn("\nauthorization_commit:", body)
        self.assertNotIn("GPU-", body.split("pinned_inputs:")[0])

    def test_static_sections_equal_the_module_definitions(self):
        config = inactive_config()
        expected = diag.expected_static_sections()
        for key in diag.STATIC_SECTION_KEYS:
            self.assertEqual(config[key], expected[key], key)

    def test_each_static_section_is_guarded(self):
        for key in diag.STATIC_SECTION_KEYS:
            config = inactive_config()
            config[key] = {"drifted": True}
            with self.assertRaises(diag.DiagnosticError) as caught:
                diag.assert_inactive_configuration(config)
            self.assertEqual(caught.exception.code, "config_shape")

    def test_inactive_document_with_any_binding_is_rejected(self):
        mutations = [
            ("execution", "authorised", True),
            ("execution", "gpu_identity_bound", True),
            ("execution", "output_directory", "/home/laura/rnagenesis-mres-runs/x"),
            ("diagnostic_generation_authorisation", "physical_gpu_index", 1),
            ("diagnostic_generation_authorisation", "gpu_uuid", "GPU-x"),
            ("diagnostic_generation_authorisation", "authorisation_timestamp", "2026-10-06T00:00:00+11:00"),
            ("diagnostic_generation_authorisation", "consumed", True),
            ("diagnostic_generation_authorisation", "activation_status", "active_unconsumed"),
            ("diagnostic_generation_authorisation", "permitted_roles", ["UPDATE21_CHECKPOINT"]),
            ("diagnostic_generation_authorisation", "implementation_file_hashes", {}),
        ]
        for section, key, value in mutations:
            config = inactive_config()
            config[section][key] = value
            with self.assertRaises(diag.DiagnosticError, msg=(section, key)):
                diag.assert_inactive_configuration(config)

    def test_inactive_configuration_is_refused_before_any_other_work(self):
        calls = []

        def spy(name):
            def inner(*args, **kwargs):
                calls.append(name)
                raise AssertionError(name + " must not be called for an inactive document")
            return inner

        config_bytes = read(CONFIG_PATH)
        deps = diag.Dependencies(
            read_bytes=lambda path: config_bytes if path == diag.CONFIG_PATH else spy("read_bytes:" + path)(),
            lstat=spy("lstat"), git=spy("git"), gpu_preflight=spy("gpu"), mkdir=spy("mkdir"),
            write_exclusive=spy("write"), subprocess_run=spy("subprocess"), sha256_file_fn=spy("hash"),
        )
        with self.assertRaises(diag.DiagnosticError) as caught:
            diag.run(deps)
        self.assertEqual(caught.exception.code, "execution_not_authorised")
        self.assertEqual(calls, [])

    def test_entry_point_accepts_only_help(self):
        self.assertEqual(diag.main(["--help"]), 0)
        self.assertEqual(diag.main(["--checkpoint", "/x"]), 2)
        self.assertEqual(diag.main(["--output-directory", "/x"]), 2)
        with mock.patch.dict(os.environ, {"M6_DIAGNOSTIC_ENABLE_EXECUTION": "1"}):
            self.assertEqual(diag.main([]), 2)
        before = set(os.listdir("/home/laura/rnagenesis-mres-runs"))
        self.assertEqual(diag.main([]), 2)
        self.assertEqual(set(os.listdir("/home/laura/rnagenesis-mres-runs")), before)

    def test_pilot_configuration_is_the_inactive_blob(self):
        data = read(PILOT_CONFIG_PATH)
        blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        self.assertEqual(blob, "4c0ef9b700f0c4566e1fdaa71dc68c25370712f0")
        self.assertEqual(sha(data), "1d31b4bca55c2c22c477220449781bb7b494bd6f26a3f575b547012566e3fe9f")
        self.assertIn(b"consumable_by_executable_workflow: false", data)
        self.assertIn(b"M6_IMPLEMENTATION_READY_FOR_REVIEW_NOT_AUTHORISED", data)


def active_config_for(pins, output, hashes=None):
    config = inactive_config()
    config["pinned_inputs"] = json.loads(json.dumps(pins))
    config["document_status"] = diag.ACTIVE_STATUS
    config["consumable_by_executable_workflow"] = True
    parent = "b" * 40
    block = config["diagnostic_generation_authorisation"]
    block.update(
        {
            "authorisation_id": "m6_d1_update21_diagnostic_test",
            "activation_status": "active_unconsumed",
            "authorization_parent_commit": parent,
            "executing_implementation_commit": parent,
            "phase": diag.ACTIVE_PHASE,
            "permitted_roles": list(diag.ACTIVE_ROLES),
            "logical_device": "cuda:0",
            "physical_gpu_index": 1,
            "gpu_uuid": "GPU-test",
            "pci_bus": "00000000:61:00.0",
            "cuda_visible_devices": "1",
            "output_directory": output,
            "evidence_directory": output,
            "implementation_file_hashes": hashes or {path: sha(read(os.path.join(ROOT, path))) for path in diag.IMPLEMENTATION_FILE_PATHS},
            "authorisation_timestamp": "2026-10-07T09:00:00+11:00",
            "scope": diag.ACTIVE_SCOPE,
        }
    )
    block["session"]["consumption_event"] = diag.CONSUMPTION_EVENT
    execution = config["execution"]
    execution.update(
        {
            "authorised": True,
            "biological_paths_permitted": True,
            "gpu_identity_bound": True,
            "output_directory": output,
            "evidence_directory": output,
            "authorisation_id": block["authorisation_id"],
            "authorization_parent_commit": parent,
            "executing_implementation_commit": parent,
        }
    )
    return config


class ActiveSchemaTests(unittest.TestCase):
    OUTPUT = "/home/laura/rnagenesis-mres-runs/m6_d1_update21_diagnostic_test"

    def active(self):
        return active_config_for(diag.production_pins(), self.OUTPUT)

    def test_a_complete_active_document_validates(self):
        block = diag.assert_active_configuration(self.active())
        self.assertEqual(block["physical_gpu_index"], 1)
        self.assertEqual(tuple(block["permitted_roles"]), diag.ACTIVE_ROLES)

    def test_each_active_field_is_guarded(self):
        mutations = [
            lambda c: c["diagnostic_generation_authorisation"].update(consumed=True),
            lambda c: c["diagnostic_generation_authorisation"].update(reuse_permitted=True),
            lambda c: c["diagnostic_generation_authorisation"].update(permitted_roles=list(diag.ACTIVE_ROLES) + ["VALIDATION_CSV"]),
            lambda c: c["diagnostic_generation_authorisation"].update(permitted_roles=list(diag.ACTIVE_ROLES) + ["REF"]),
            lambda c: c["diagnostic_generation_authorisation"].update(cuda_visible_devices="0"),
            lambda c: c["diagnostic_generation_authorisation"].update(logical_device="cuda:1"),
            lambda c: c["diagnostic_generation_authorisation"].update(physical_gpu_index="1"),
            lambda c: c["diagnostic_generation_authorisation"].update(executing_implementation_commit="c" * 40),
            lambda c: c["diagnostic_generation_authorisation"].update(authorization_parent_commit="XYZ"),
            lambda c: c["diagnostic_generation_authorisation"].update(authorisation_timestamp=None),
            lambda c: c["diagnostic_generation_authorisation"].update(phase="other"),
            lambda c: c["diagnostic_generation_authorisation"].update(scope="other"),
            lambda c: c["diagnostic_generation_authorisation"].update(implementation_file_hashes={"x": "y"}),
            lambda c: c["diagnostic_generation_authorisation"]["session"].update(resume_permitted=True),
            lambda c: c["execution"].update(output_directory="/home/laura/rnagenesis-mres-runs/other"),
            lambda c: c["execution"].update(authorised=False),
            lambda c: c["hard_guardrails"]["rules"][0].update(threshold=0.5),
            lambda c: c["closed_gates"].update(m7_authorised=True),
            lambda c: c["roles"].update(validation="requested"),
        ]
        for mutate in mutations:
            config = self.active()
            mutate(config)
            with self.assertRaises(diag.DiagnosticError):
                diag.assert_active_configuration(config)

    def test_output_directory_must_be_a_new_direct_child_outside_accepted_evidence(self):
        for path in (
            "/tmp/x",
            "/home/laura/rnagenesis-mres-runs/a/b",
            "/home/laura/rnagenesis-mres-runs/",
            diag.TRAINING_EVIDENCE_DIRECTORY,
            diag.B1_POOL_DIRECTORY,
            diag.SCHEDULE_DIRECTORY,
        ):
            config = active_config_for(diag.production_pins(), path)
            with self.assertRaises(diag.DiagnosticError, msg=path):
                diag.assert_active_configuration(config)

    def test_output_path_is_single_use(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "run")
            self.assertTrue(diag.assert_output_directory_absent(target))
            os.mkdir(target)
            with self.assertRaises(diag.DiagnosticError) as caught:
                diag.assert_output_directory_absent(target)
            self.assertEqual(caught.exception.code, "output_directory_exists")
            link = os.path.join(directory, "link")
            os.symlink(target, link)
            with self.assertRaises(diag.DiagnosticError) as caught:
                diag.assert_output_directory_absent(link)
            self.assertEqual(caught.exception.code, "output_directory_symlink")


class ScheduleIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vector = read(os.path.join(SCHEDULE_DIR, "ordered_train_length_vector.json"))
        cls.accepted = read(os.path.join(SCHEDULE_DIR, "development_pool_schedule.json"))

    def test_accepted_hashes_are_the_pinned_constants(self):
        self.assertEqual(sha(self.vector), "7e6cb523a85116fc38788c336ef50c26e0eccc343712aaea89956a73c485bd3c")
        self.assertEqual(sha(self.accepted), "0f527d44ae1029c936391fe81709f991a21811c4349e49c5b6aafb414b1702f0")
        self.assertEqual(diag.SCHEDULE_SHA256, sha(self.accepted))
        self.assertEqual(diag.LENGTH_VECTOR_SHA256, sha(self.vector))

    def test_rebuild_reproduces_the_accepted_schedule_exactly(self):
        schedule, body = diag.rebuild_and_verify_schedule(self.vector, self.accepted)
        self.assertEqual(body, self.accepted)
        self.assertEqual(schedule["total_attempts"], 1000)
        self.assertEqual(schedule["invocation_count"], 112)
        self.assertEqual(schedule["sampling_seed"], 43000)
        self.assertEqual([item["invocation_seed"] for item in schedule["invocations"]], [44000 + i for i in range(112)])
        self.assertEqual(json.loads(self.accepted.decode("utf-8"))["invocations"], schedule["invocations"])
        self.assertTrue(all(item["actual_chunk_size"] <= 16 and item["batch_num"] == 1 for item in schedule["invocations"]))
        self.assertTrue(all(item["max_seq_len"] == item["target_length"] + 1 for item in schedule["invocations"]))

    def test_schedule_forbids_every_replacement_mechanism(self):
        schedule, _ = diag.rebuild_and_verify_schedule(self.vector)
        for flag in ("padding", "duplication", "replacement_of_attempts", "rejection", "resampling", "dropping"):
            self.assertIs(schedule[flag], False)

    def test_a_different_vector_or_schedule_is_refused(self):
        altered = self.vector.replace(b"[", b"[1,", 1)
        with self.assertRaises(diag.DiagnosticError) as caught:
            diag.rebuild_and_verify_schedule(altered)
        self.assertEqual(caught.exception.code, "schedule_hash_mismatch")
        with self.assertRaises(diag.DiagnosticError) as caught:
            diag.rebuild_and_verify_schedule(self.vector, self.accepted + b" ")
        self.assertEqual(caught.exception.code, "schedule_hash_mismatch")
        pins = diag.production_pins()
        pins["schedule"]["schedule"]["sha256"] = "0" * 64
        with self.assertRaises(diag.DiagnosticError) as caught:
            diag.rebuild_and_verify_schedule(self.vector, self.accepted, pins)
        self.assertEqual(caught.exception.code, "schedule_hash_mismatch")

    def test_every_attempt_is_scheduled_exactly_once(self):
        schedule, _ = diag.rebuild_and_verify_schedule(self.vector)
        seen = [index for item in schedule["invocations"] for index in item["original_attempt_indexes"]]
        self.assertEqual(sorted(seen), list(range(1000)))


def synthetic_checkpoint(root):
    directory = os.path.join(root, "update-21-checkpoint")
    members = {
        "model_index.json": b'{"index": 1}\n',
        "scheduler/scheduler_config.json": b'{"scheduler": 1}\n',
        "unet/config.json": b'{"unet": 1}\n',
        "unet/diffusion_pytorch_model.safetensors": b"synthetic raw weights\n",
    }
    for name, data in members.items():
        path = os.path.join(directory, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)
    return directory, {name: {"sha256": sha(data), "bytes": len(data)} for name, data in members.items()}


class CheckpointBindingTests(unittest.TestCase):
    def test_pinned_identity_matches_the_closed_training_manifest(self):
        record = diag.verify_training_evidence(diag.Dependencies())
        self.assertEqual(record["completion_state"], "pilot_completed")
        self.assertEqual(record["consumption_state"], "consumed_successfully")
        self.assertEqual(record["manifest_sha256"], "4b24d5bf5bc392a8f6ee4b8af91adb3582e3a17cac459559632494ec64f8ae52")
        self.assertEqual(diag.CHECKPOINT_MEMBERS[diag.WEIGHT_MEMBER][0], "47b2dc9b392ea766eee7e947f0f92f5a039c42ac714326104e719352d20b5924")
        self.assertTrue(diag.checkpoint_directory().endswith("__update-21__git-6fd611589d7a3365b793c2ca64cf13c29ef5bfc1"))
        self.assertTrue(os.path.isdir(diag.checkpoint_directory()))

    def test_manifest_or_consumption_drift_is_refused(self):
        real = diag.Dependencies()
        manifest_path = os.path.join(diag.TRAINING_EVIDENCE_DIRECTORY, "m6_pilot_manifest.json")
        deps = diag.Dependencies(read_bytes=lambda p: real.read_bytes(p) + b" " if p == manifest_path else real.read_bytes(p))
        with self.assertRaises(diag.DiagnosticError) as caught:
            diag.verify_training_evidence(deps)
        self.assertEqual(caught.exception.code, "training_evidence_invalid")
        failure_path = os.path.join(diag.TRAINING_EVIDENCE_DIRECTORY, "authorization_failure.json")

        def lstat(path):
            return types.SimpleNamespace(st_mode=stat.S_IFREG, st_size=1) if path == failure_path else os.lstat(path)

        with self.assertRaises(diag.DiagnosticError):
            diag.verify_training_evidence(diag.Dependencies(lstat=lstat))

    def test_manifest_hashes_that_differ_from_the_pin_are_refused(self):
        pins = diag.production_pins()
        pins["checkpoint"]["members"][diag.WEIGHT_MEMBER]["sha256"] = "1" * 64
        with self.assertRaises(diag.DiagnosticError) as caught:
            diag.verify_training_evidence(diag.Dependencies(), pins)
        self.assertEqual(caught.exception.code, "checkpoint_identity_mismatch")

    def test_checkpoint_tree_hashes_and_exactness(self):
        with tempfile.TemporaryDirectory() as root:
            directory, members = synthetic_checkpoint(root)
            pins = diag.production_pins()
            pins["checkpoint"].update(directory=directory, members=members)
            record = diag.verify_checkpoint(diag.Dependencies(), pins)
            self.assertEqual(set(record["members"]), set(members))
            with open(os.path.join(directory, "unet/config.json"), "ab") as handle:
                handle.write(b" ")
            with self.assertRaises(diag.DiagnosticError):
                diag.verify_checkpoint(diag.Dependencies(), pins)

    def test_extra_missing_and_symlinked_members_are_refused(self):
        for case in ("extra", "missing", "symlink"):
            with tempfile.TemporaryDirectory() as root:
                directory, members = synthetic_checkpoint(root)
                pins = diag.production_pins()
                pins["checkpoint"].update(directory=directory, members=members)
                if case == "extra":
                    open(os.path.join(directory, "optimizer.bin"), "wb").close()
                elif case == "missing":
                    os.remove(os.path.join(directory, "model_index.json"))
                else:
                    target = os.path.join(root, "elsewhere.json")
                    shutil.move(os.path.join(directory, "model_index.json"), target)
                    os.symlink(target, os.path.join(directory, "model_index.json"))
                with self.assertRaises(diag.DiagnosticError, msg=case):
                    diag.verify_checkpoint(diag.Dependencies(), pins)

    def test_only_the_update_21_directory_is_loadable(self):
        invocation = synthetic_invocation(0, 30)
        argv = diag.build_diagnostic_argv(invocation, diag.checkpoint_directory())
        self.assertEqual(argv[argv.index("--dm_file") + 1], diag.checkpoint_directory())
        self.assertEqual(argv.count("--dm_file"), 1)
        joined = " ".join(argv)
        self.assertNotIn(b1.DIFFUSION_RELATIVE, joined)
        self.assertNotIn("update-7__", joined)
        self.assertNotIn("update-14__", joined)
        self.assertNotIn("checkpoints/Aptamer/diffusion", joined)
        for other in ("7", "14", "0"):
            sibling = diag.checkpoint_directory().replace("update-21__", "update-" + other + "__")
            with self.assertRaises(diag.DiagnosticError) as caught:
                diag.build_diagnostic_argv(invocation, sibling)
            self.assertEqual(caught.exception.code, "unexpected_checkpoint_update")
            with self.assertRaises(diag.DiagnosticError):
                diag.consider_input_path(sibling, "UPDATE21_CHECKPOINT", True, opener=lambda p: self.fail("opened"))
        with self.assertRaises(diag.DiagnosticError):
            diag.build_diagnostic_argv(invocation, b1.DIFFUSION_RELATIVE)

    def test_diagnostic_argv_is_the_b1_contract_with_one_substitution(self):
        schedule, _ = diag.rebuild_and_verify_schedule(read(os.path.join(SCHEDULE_DIR, "ordered_train_length_vector.json")))
        for invocation in (schedule["invocations"][0], schedule["invocations"][57], schedule["invocations"][111]):
            baseline = b1.build_generation_argv(invocation)
            argv = diag.build_diagnostic_argv(invocation, diag.checkpoint_directory())
            differences = [(x, y) for x, y in zip(baseline, argv) if x != y]
            self.assertEqual(differences, [(b1.DIFFUSION_RELATIVE, diag.checkpoint_directory())])
            self.assertEqual(len(baseline), len(argv))
            self.assertEqual(argv[argv.index("--eos_token") + 1], "2")
            self.assertEqual(argv[argv.index("--bos_token") + 1], "1")
            self.assertEqual(argv[argv.index("--seed") + 1], str(invocation["invocation_seed"]))
            self.assertEqual(argv[argv.index("--batch_size") + 1], str(invocation["actual_chunk_size"]))
            self.assertEqual(argv[argv.index("--batch_num") + 1], "1")
            self.assertEqual(argv[argv.index("--max_seq_len") + 1], str(invocation["target_length"] + 1))
            for option in b1.PROHIBITED_ARGV_OPTIONS:
                self.assertNotIn(option, argv)


class B1NonRegenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics = real_metrics_module()
        cls.schedule, _ = diag.rebuild_and_verify_schedule(read(os.path.join(SCHEDULE_DIR, "ordered_train_length_vector.json")))

    def test_accepted_pool_is_read_recomputed_and_not_regenerated(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("generation or writing is forbidden while reading the B1 pool")

        deps = diag.Dependencies(subprocess_run=forbidden, mkdir=forbidden, write_exclusive=forbidden)
        reference = diag.load_b1_reference(deps, self.metrics, self.schedule)
        self.assertEqual(len(reference["attempts"]), 1000)
        self.assertIs(reference["regenerated"], False)
        self.assertIs(reference["rerun"], False)
        self.assertIs(reference["metrics_recomputed_equal_to_accepted"], True)
        summary = self.metrics.summarise_attempts(reference["attempts"])
        self.assertEqual((summary["valid_outputs"], summary["exact_length_hits"], summary["early_eos_observations"]), (1000, 961, 39))

    def test_pool_evidence_drift_is_refused(self):
        real = diag.Dependencies()
        ledger = os.path.join(diag.B1_POOL_DIRECTORY, "development_pool_audited_attempts.jsonl")
        deps = diag.Dependencies(read_bytes=lambda p: real.read_bytes(p)[:-1] if p == ledger else real.read_bytes(p))
        with self.assertRaises(diag.DiagnosticError) as caught:
            diag.load_b1_reference(deps, self.metrics, self.schedule)
        self.assertEqual(caught.exception.code, "b1_pool_evidence_invalid")

    def test_pairing_requires_identical_schedule_fields(self):
        reference = diag.load_b1_reference(diag.Dependencies(), self.metrics, self.schedule)["attempts"]
        paired = copy.deepcopy(reference)
        self.assertTrue(diag.assert_pairing(paired, reference))
        paired[3]["invocation_seed"] += 1
        with self.assertRaises(diag.DiagnosticError) as caught:
            diag.assert_pairing(paired, reference)
        self.assertEqual(caught.exception.code, "pairing_invalid")
        with self.assertRaises(diag.DiagnosticError):
            diag.assert_pairing(reference[:-1], reference)

    def test_accepted_pool_normalisation_reconciles_independently(self):
        reference = diag.load_b1_reference(diag.Dependencies(), self.metrics, self.schedule)["attempts"]
        self.assertTrue(diag.assert_normalisation_reconciles(reference))
        sensitivity = diag.strict_m6_rule_sensitivity(reference)
        self.assertEqual(sensitivity["attempts_the_stricter_helper_would_reject"], 39)
        self.assertEqual(sensitivity["raw_attempts"], 1000)


class NormalisationTests(unittest.TestCase):
    def test_raw_and_normalised_forms_are_both_preserved(self):
        rows = [("11ACGUACGU", 10), ("11ACGUA2", 10), ("1122ACG11", 3), ("11", 5), ("11ACGX", 4), ("", 3), ("ACGU", 4)]
        attempts = build_attempts(rows)
        self.assertEqual([a["raw_decoded_text"] for a in attempts], [r for r, _ in rows])
        self.assertEqual(attempts[0]["cleaned_sequence"], "ACGUACGU")
        self.assertEqual((attempts[1]["cleaned_sequence"], attempts[1]["trailing_boundary_marker_run"]), ("ACGUA", "2"))
        self.assertIs(attempts[1]["early_eos"], True)
        self.assertEqual(attempts[2]["cleaned_sequence"], "ACG")
        self.assertEqual(attempts[2]["leading_boundary_marker_run"], "1122")
        self.assertEqual(attempts[2]["trailing_boundary_marker_run"], "11")
        self.assertIs(attempts[3]["validity"], False)
        self.assertEqual(attempts[3]["raw_decoded_text"], "11")
        self.assertIs(attempts[4]["validity"], False)
        self.assertEqual(attempts[4]["cleaned_sequence"], "ACGX")
        self.assertIs(attempts[5]["validity"], False)
        self.assertEqual(attempts[6]["cleaned_sequence"], "ACGU")
        self.assertTrue(diag.assert_normalisation_reconciles(attempts))

    def test_no_character_is_added_trimmed_or_rewritten_beyond_the_boundary_runs(self):
        attempts = build_attempts([("11AC1GU2", 5), ("11acgu", 4), ("11ACGT", 4)])
        self.assertEqual(attempts[0]["cleaned_sequence"], "AC1GU")
        self.assertIs(attempts[0]["validity"], False)
        self.assertEqual(attempts[1]["cleaned_sequence"], "acgu")
        self.assertIs(attempts[1]["validity"], False)
        self.assertEqual(attempts[2]["cleaned_sequence"], "ACGT")
        self.assertIs(attempts[2]["validity"], False)

    def test_normalisation_failure_is_a_technical_failure(self):
        base = build_attempts([("11ACGUACGU", 10), ("11ACGUA2", 5)])
        for field, value in (
            ("cleaned_sequence", "ACGUACG"),
            ("cleaned_sequence", "ACGUAGGU"),
            ("leading_boundary_marker_run", "1"),
            ("trailing_boundary_marker_run", ""),
            ("raw_length", 99),
            ("cleaned_length", 99),
            ("validity", False),
        ):
            attempts = copy.deepcopy(base)
            target = attempts[1] if field == "trailing_boundary_marker_run" else attempts[0]
            target[field] = value
            with self.assertRaises(diag.DiagnosticError, msg=field) as caught:
                diag.assert_normalisation_reconciles(attempts)
            self.assertEqual(caught.exception.code, "unexpected_output_normalization")

    def test_cleaner_hash_is_pinned(self):
        self.assertEqual(sha(read(str(b1.APPROVED_CLEANER))), diag.CLEANER_SHA256)
        with self.assertRaises(b1.DevelopmentPoolError):
            b1.load_cleaner_from_verified_source(read(str(b1.APPROVED_CLEANER)) + b"#")

    def test_reused_modules_are_hash_pinned(self):
        for name, relative, digest in (
            ("b1", diag.B1_RUNNER_RELATIVE, diag.B1_RUNNER_SHA256),
            ("metrics", diag.METRICS_RELATIVE, diag.METRICS_SHA256),
            ("metrics_config", diag.METRICS_CONFIG_RELATIVE, diag.METRICS_CONFIG_SHA256),
        ):
            self.assertEqual(sha(read(os.path.join(ROOT, relative))), digest, name)
        with self.assertRaises(diag.DiagnosticError):
            diag._load_verified("x", os.path.join(ROOT, diag.B1_RUNNER_RELATIVE), "0" * 64)


class AccountingAndGuardrailTests(unittest.TestCase):
    def test_all_clean_sample_passes_every_guardrail(self):
        result, decisions = guardrail_values(good_rows())
        self.assertTrue(result["checkpoint_eligible"])
        self.assertEqual(list(decisions), [rule[0] for rule in diag.HARD_GUARDRAIL_RULES])
        self.assertTrue(all(item["passed"] for item in decisions.values()))

    def test_thresholds_are_exactly_the_approved_values(self):
        metrics = real_metrics_module()
        self.assertTrue(diag.assert_guardrail_thresholds(metrics))
        self.assertEqual(
            [(i, c, t) for i, c, t, _ in diag.HARD_GUARDRAIL_RULES],
            [("valid_nonempty_acgu_fraction", "minimum", 0.99), ("empty_or_unparseable_fraction", "maximum", 0.01),
             ("unique_fraction", "minimum", 0.95), ("exact_train_match_rate", "maximum", 0.01),
             ("largest_duplicate_share", "maximum", 0.01)],
        )
        drifted = types.SimpleNamespace(
            GUARDRAIL_THRESHOLDS=dict(metrics.GUARDRAIL_THRESHOLDS, unique_fraction={"comparison": "minimum", "threshold": 0.90}),
            HARD_GUARDRAIL_IDS=metrics.HARD_GUARDRAIL_IDS,
        )
        with self.assertRaises(diag.DiagnosticError):
            diag.assert_guardrail_thresholds(drifted)

    def test_valid_fraction_guardrail(self):
        rows = good_rows()
        for i in range(11):
            rows[i] = ("11ACGX" + distinct_body(i, 5), 30)
        result, decisions = guardrail_values(rows)
        self.assertFalse(decisions["valid_nonempty_acgu_fraction"]["passed"])
        self.assertTrue(decisions["empty_or_unparseable_fraction"]["passed"])
        self.assertFalse(result["checkpoint_eligible"])
        rows = good_rows()
        for i in range(10):
            rows[i] = ("11ACGX" + distinct_body(i, 5), 30)
        _, decisions = guardrail_values(rows)
        self.assertTrue(decisions["valid_nonempty_acgu_fraction"]["passed"])

    def test_empty_or_unparseable_guardrail(self):
        rows = good_rows()
        for i in range(11):
            rows[i] = ("11", 30)
        result, decisions = guardrail_values(rows)
        self.assertFalse(decisions["empty_or_unparseable_fraction"]["passed"])
        self.assertAlmostEqual(decisions["empty_or_unparseable_fraction"]["value"], 0.011)
        rows = good_rows()
        for i in range(10):
            rows[i] = ("", 30)
        _, decisions = guardrail_values(rows)
        self.assertTrue(decisions["empty_or_unparseable_fraction"]["passed"])

    def test_unique_fraction_guardrail(self):
        rows = good_rows()
        for group in range(6):
            for k in range(10):
                rows[group * 10 + k] = ("11" + distinct_body(5000 + group), 30)
        result, decisions = guardrail_values(rows)
        self.assertFalse(decisions["unique_fraction"]["passed"])
        self.assertTrue(decisions["largest_duplicate_share"]["passed"])
        self.assertAlmostEqual(decisions["unique_fraction"]["value"], 0.946)

    def test_exact_train_match_guardrail(self):
        # Whole TRAIN cores, distinct from every other generated body.
        train = [distinct_body(10000 + i, 30) for i in range(11)]
        rows = good_rows()
        for i in range(11):
            rows[500 + i] = ("11" + train[i], 30)
        _, decisions = guardrail_values(rows, train)
        self.assertFalse(decisions["exact_train_match_rate"]["passed"])
        self.assertAlmostEqual(decisions["exact_train_match_rate"]["value"], 0.011)
        _, decisions = guardrail_values(rows, train[:10])
        self.assertTrue(decisions["exact_train_match_rate"]["passed"])
        self.assertAlmostEqual(decisions["exact_train_match_rate"]["value"], 0.010)

    def test_largest_duplicate_share_guardrail(self):
        rows = good_rows()
        for i in range(11):
            rows[i] = ("11" + distinct_body(7000), 30)
        _, decisions = guardrail_values(rows)
        self.assertFalse(decisions["largest_duplicate_share"]["passed"])
        self.assertTrue(decisions["unique_fraction"]["passed"])
        rows = good_rows()
        for i in range(10):
            rows[i] = ("11" + distinct_body(7000), 30)
        _, decisions = guardrail_values(rows)
        self.assertTrue(decisions["largest_duplicate_share"]["passed"])

    def test_requested_length_exact_hit_rate_is_reported_not_enforced(self):
        rows = [("11" + distinct_body(i, 30), 45) for i in range(1000)]
        result, decisions = guardrail_values(rows)
        self.assertTrue(result["checkpoint_eligible"])
        self.assertEqual(result["approved_exact_hit_rate"], 0.0)
        self.assertIs(result["exact_hit_rate_is_an_eligibility_threshold"], False)
        self.assertNotIn("exact_hit_rate", decisions)
        summary = real_metrics_module().summarise_attempts(build_attempts(rows))
        self.assertEqual(summary["exact_hit_rate"], 0.0)
        self.assertEqual(summary["exact_hit_rate_denominator"], "raw_attempts")

    def test_empty_valid_denominator_fails_closed(self):
        result, decisions = guardrail_values([("11", 30)] * 20)
        self.assertFalse(result["checkpoint_eligible"])
        self.assertFalse(decisions["unique_fraction"]["passed"])
        self.assertEqual(decisions["unique_fraction"]["status"], "undefined_empty_valid_denominator")

    def test_every_attempt_class_stays_in_its_denominator(self):
        rows = (
            [("11" + distinct_body(i, 30), 30) for i in range(600)]                     # exact hits
            + [("11" + distinct_body(700 + i, 25) + "2", 30) for i in range(100)]       # early EOS
            + [("11" + distinct_body(900 + i, 33), 30) for i in range(80)]              # excess length
            + [("11" + distinct_body(2000, 30), 30) for _ in range(40)]                 # duplicates
            + [("11ACGX" + distinct_body(i, 4), 30) for i in range(120)]                # invalid symbols
            + [("11", 30) for _ in range(60)]                                           # empty body
        )
        attempts = build_attempts(rows)
        summary = real_metrics_module().summarise_attempts(attempts)
        accounting = diag.accounting_from(summary, attempts, 112)
        self.assertEqual(accounting["raw_attempts"], 1000)
        self.assertEqual(accounting["valid_outputs"], 820)
        self.assertEqual(accounting["invalid_outputs"], 180)
        self.assertEqual(accounting["empty_or_unparseable_outputs"], 60)
        self.assertEqual(accounting["early_eos_observations"], 100)
        self.assertEqual(accounting["exact_length_hits"], 640)
        self.assertEqual(accounting["length_mismatches"], 180)
        self.assertEqual(accounting["duplicates"], 39)
        self.assertEqual(accounting["unique_valid_outputs"], 781)
        self.assertEqual(
            accounting["exact_length_hits"] + accounting["length_mismatches"] + accounting["invalid_outputs"], 1000
        )
        self.assertEqual((accounting["replacements"], accounting["resampled_attempts"], accounting["dropped_attempts"]), (0, 0, 0))
        result = diag.evaluate_guardrails(real_metrics_module(), attempts, TRAIN)
        self.assertEqual(result["values"]["valid_nonempty_acgu_fraction"], 0.82)
        self.assertEqual(result["values"]["empty_or_unparseable_fraction"], 0.06)
        self.assertAlmostEqual(result["values"]["unique_fraction"], 781 / 820.0)
        self.assertEqual(result["values"]["largest_duplicate_share"], 40 / 820.0)
        self.assertEqual(summary["exact_hit_rate"], 0.64)


class EditDistanceAndReportTests(unittest.TestCase):
    @staticmethod
    def reference(a, b):
        previous = list(range(len(b) + 1))
        for i, x in enumerate(a, 1):
            current = [i]
            for j, y in enumerate(b, 1):
                current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
            previous = current
        return previous[-1]

    def test_bit_parallel_edit_distance_equals_the_reference(self):
        rng = random.Random(7)
        for _ in range(1500):
            a = "".join(rng.choice("ACGU") for _ in range(rng.randint(0, 45)))
            b = "".join(rng.choice("ACGU") for _ in range(rng.randint(0, 45)))
            self.assertEqual(diag.edit_distance(a, b), self.reference(a, b))
        for a, b in (("", ""), ("A", ""), ("", "ACGU"), ("ACGU", "ACGU"), ("AAAA", "UUUU")):
            self.assertEqual(diag.edit_distance(a, b), self.reference(a, b))

    def test_edit_similarity_is_one_minus_the_longer_length_normalised_distance(self):
        report = diag.report_only_diagnostics(build_attempts([("11ACGU", 4), ("11ACGA", 4)]), ["ACGU", "GGGGGGGG"], lambda q: ("." * len(q), 0.0))
        self.assertEqual(report["maximum_edit_similarity_to_train"], 1.0)
        report = diag.report_only_diagnostics(build_attempts([("11AC", 4)]), ["ACGU"], lambda q: ("." * len(q), 0.0))
        self.assertEqual(report["maximum_edit_similarity_to_train"], 0.5)
        self.assertIn("maximum_edit_similarity_to_train", diag.REPORT_ONLY_ITEMS)
        for text in (read(MODULE_PATH).decode(), read(CONFIG_PATH).decode()):
            self.assertNotIn("maximum_identity_to_train", text)

    def test_nearest_train_is_normalised_by_the_longer_sequence(self):
        self.assertEqual(diag.nearest_train("ACGU", ["ACGU", "GGGG"]), 0.0)
        self.assertEqual(diag.nearest_train("ACGU", ["ACGA"]), 0.25)
        self.assertEqual(diag.nearest_train("AC", ["ACGU"]), 0.5)

    def test_report_only_diagnostics_have_no_thresholds_or_clustering(self):
        attempts = build_attempts([("11" + distinct_body(i, 30 + (i % 3)), 30 + (i % 3)) for i in range(30)] + [("11", 30)])
        fold = lambda sequence: ("(" * 3 + "." * (len(sequence) - 6) + ")" * 3, -4.5)
        report = diag.report_only_diagnostics(attempts, TRAIN, fold)
        self.assertEqual(report["valid_outputs"], 30)
        self.assertFalse(report["thresholds_defined"])
        self.assertFalse(report["clustering_or_embedding_metrics"])
        self.assertEqual(sum(row["raw_attempts"] for row in report["by_requested_length"]), 31)
        self.assertEqual(sum(report["composition"]["nucleotide_counts"].values()), sum(len(a["cleaned_sequence"]) for a in attempts if a["validity"]))
        self.assertEqual(len(report["composition"]["dinucleotide_counts"]), 16)
        self.assertAlmostEqual(report["paired_fraction"]["mean"], 6 / 30.0, places=1)
        self.assertEqual(report["mfe"]["mean"], -4.5)
        self.assertNotIn("maximum_identity_to_train", report)
        distances = [diag.nearest_train(a["cleaned_sequence"], TRAIN) for a in attempts if a["validity"]]
        self.assertEqual(report["maximum_edit_similarity_to_train"], 1.0 - min(distances))
        self.assertIn("not a sequence identity", report["maximum_edit_similarity_definition"])
        forbidden = ("cluster", "embedding", "silhouette", "mmd")
        text = json.dumps(report).lower()
        self.assertFalse([word for word in forbidden if word in text.replace("clustering_or_embedding_metrics", "")])
        self.assertNotIn("threshold", text.replace("thresholds_defined", ""))


class SyntheticWorld(object):
    """A self-contained fake environment for end-to-end mock runs."""

    def __init__(self, root, mode="clean"):
        self.root = root
        self.mode = mode
        self.run_root = os.path.join(root, "runs")
        os.makedirs(self.run_root)
        self.output = os.path.join(self.run_root, "m6_d1_update21_diagnostic_test")
        self.vector = read(os.path.join(SCHEDULE_DIR, "ordered_train_length_vector.json"))
        self.lengths = json.loads(self.vector.decode("utf-8"))
        self.checkpoint_dir, members = synthetic_checkpoint(os.path.join(root, "training_evidence"))
        os.makedirs(os.path.join(root, "training_evidence"), exist_ok=True)
        self.training_dir = os.path.join(root, "training_evidence")
        manifest = {
            "authorisation": {
                "authorisation_id": "synthetic_training",
                "authorization_commit": "1" * 40,
                "consumption_state": "consumed_successfully",
                "executing_implementation_commit": "2" * 40,
            },
            "completion_state": "pilot_completed",
            "diagnostic_generation_status": "not_performed_requires_separate_authorisation",
            "failure_state": None,
            "production_identities": True,
            "ref_eval_access": {"eval_opened": False, "ref_opened": False},
            "warnings": [],
            "weight_checkpoints": [
                {
                    "update": 21,
                    "saved_hashes": {name: item["sha256"] for name, item in members.items()},
                    "state_comparison": {"complete_state_equal": True},
                    "fresh_load_succeeded": True,
                }
            ],
        }
        manifest_bytes = diag.canonical_json(manifest)
        consumption_bytes = diag.canonical_json({"consumption_state": "consumed_output_created"})
        for name, data in (("m6_pilot_manifest.json", manifest_bytes), ("authorization_consumption.json", consumption_bytes)):
            with open(os.path.join(self.training_dir, name), "wb") as handle:
                handle.write(data)
        rng = random.Random(99)
        cores, seen = [], set()
        for length in self.lengths:
            while True:
                core = "".join(rng.choice("ACGU") for _ in range(length))
                if core not in seen:
                    seen.add(core)
                    cores.append(core)
                    break
        self.train_text = ("\n".join(cores) + "\n").encode("utf-8")
        self.train_cores = cores
        self.train_path = os.path.join(root, "synthetic_train.txt")
        with open(self.train_path, "wb") as handle:
            handle.write(self.train_text)
        pins = diag.production_pins()
        pins["training_evidence"].update(
            directory=self.training_dir,
            run_id="synthetic_training",
            authorization_commit="1" * 40,
            executing_implementation_commit="2" * 40,
            manifest={"name": "m6_pilot_manifest.json", "sha256": sha(manifest_bytes), "bytes": len(manifest_bytes)},
            consumption={"name": "authorization_consumption.json", "sha256": sha(consumption_bytes), "bytes": len(consumption_bytes)},
        )
        pins["checkpoint"].update(directory=self.checkpoint_dir, members=members)
        pins["train"].update(path=self.train_path, sha256=sha(self.train_text), bytes=len(self.train_text), count=len(cores))
        self.pins = pins
        self.config_bytes = yaml_bytes(active_config_for(pins, self.output))
        self.calls = []
        self.origin = None
        self.virtual = {diag.CONFIG_PATH: self.config_bytes}
        self.checkpoint_tree_before = self.tree_snapshot(self.checkpoint_dir)

    @staticmethod
    def tree_snapshot(directory):
        snapshot = {}
        for base, _dirs, files in os.walk(directory):
            for name in files:
                path = os.path.join(base, name)
                snapshot[path] = sha(read(path))
        return snapshot

    def read_bytes(self, path):
        path = str(path)
        if path in self.virtual:
            return self.virtual[path]
        with open(path, "rb") as handle:
            return handle.read()

    def git(self, repo, args):
        repo, args = str(repo), list(args)
        head, parent = "a" * 40, "b" * 40
        if repo == diag.MRES_ROOT:
            if args == ["rev-parse", "HEAD"]:
                return head + "\n"
            if args == ["rev-parse", "origin/main"]:
                return (self.origin or parent) + "\n"
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return "main\n"
            if args[0] == "status":
                return ""
            if args == ["rev-parse", "HEAD^@"]:
                return parent + "\n"
            if args[:3] == ["diff", "--name-only", parent]:
                return diag.CONFIG_RELATIVE + "\n"
            if args[0] == "show":
                return self.config_bytes.decode("utf-8")
            if args[0] in ("rev-parse", "hash-object"):
                return "c" * 40 + "\n"
        else:
            if args == ["rev-parse", "HEAD"]:
                return diag.RNAGENESIS_COMMIT + "\n"
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return diag.RNAGENESIS_BRANCH + "\n"
            if args[0] == "status":
                return b1.reviewed_rnagenesis_porcelain()
        raise AssertionError("unexpected git call: %r %r" % (repo, args))

    def sha256_file(self, path):
        if str(path).endswith("pytorch_model.bin"):
            return dict((p, d) for p, d, _s, _r in contract.m5_contract().REQUIRED_MODEL_FILES)["configs/rnagenesis/autoencoder/pytorch_model.bin"]
        return sha(read(path))

    def subprocess_run(self, argv, cwd, env, shell=False):
        self.calls.append({"argv": list(argv), "cwd": cwd, "env": dict(env), "shell": shell})
        index = int(argv[argv.index("--mid_folder") + 1].split("_")[-1])
        size = int(argv[argv.index("--batch_size") + 1])
        target = int(argv[argv.index("--max_seq_len") + 1]) - 1
        lines = []
        for k in range(size):
            generator = random.Random(index * 100 + k)
            body = "".join(generator.choice("ACGU") for _ in range(target))
            line = "11" + body
            if self.mode == "early_eos" and (index + k) % 20 == 0 and target > 5:
                line = "11" + body[:-3] + "2"
            if self.mode == "invalid_block" and index < 15:
                line = "11XXXX" + body[:5]
            if self.mode == "short_output" and index == 5 and k == size - 1 and size > 1:
                continue
            lines.append(line)
        predicted = b1.predicted_generation_path(argv[argv.index("--superfolder") + 1].rsplit("/", 1)[0], {
            "actual_chunk_size": size, "batch_num": 1, "invocation_index": index,
            "invocation_seed": int(argv[argv.index("--seed") + 1]), "max_seq_len": target + 1,
        })
        with open(predicted, "w") as handle:
            handle.write("\n".join(lines) + ("\n" if lines else ""))
        return types.SimpleNamespace(returncode=0)

    def deps(self, **overrides):
        parameters = dict(
            read_bytes=self.read_bytes,
            sha256_file_fn=self.sha256_file,
            environ={"CUDA_VISIBLE_DEVICES": "1", "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "PATH": "/usr/bin"},
            git=self.git,
            gpu_preflight=lambda parent, physical: {
                "physical_index": 1, "uuid": "GPU-test", "pci_bus": "00000000:61:00.0", "logical_device": "cuda:0",
                "device_type": "cuda", "cuda_device_count": 1, "cpu_fallback": False, "other_gpu_fallback": False,
            },
            subprocess_run=self.subprocess_run,
            fold=lambda sequence: ("." * len(sequence), -1.0),
            nearest=lambda sequence, train: 1.0,
        )
        parameters.update(overrides)
        return diag.Dependencies(**parameters)

    def run(self, **overrides):
        return diag.run(self.deps(**overrides), run_root=self.run_root, pins=self.pins)


def yaml_bytes(config):
    import yaml

    return yaml.safe_dump(config, sort_keys=False, default_flow_style=False, width=120).encode("utf-8")


class EndToEndMockTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.runs_before = set(os.listdir(diag.RUN_ROOT))

    def tearDown(self):
        self.assertEqual(set(os.listdir(diag.RUN_ROOT)), self.runs_before, "the real run root was modified")

    def manifest(self, world):
        return json.loads(read(os.path.join(world.output, diag.MANIFEST_NAME)).decode("utf-8"))

    def test_clean_run_completes_without_closing_m6(self):
        world = SyntheticWorld(self.directory)
        outcome = world.run()
        self.assertEqual(outcome["status"], "success")
        self.assertEqual(outcome["guardrail_outcome"], "passed")
        manifest = self.manifest(world)
        self.assertTrue(diag.validate_success_manifest(manifest, world.pins))
        self.assertEqual(manifest["closure"]["m6_complete"], False)
        self.assertEqual(manifest["closure"]["m7_authorised"], False)
        self.assertEqual(manifest["closure"]["checkpoint_selected"], False)
        self.assertEqual(manifest["roles"]["validation"], "not_opened")
        self.assertEqual(manifest["roles"]["ref"], "not_opened")
        self.assertEqual(manifest["roles"]["eval"], "not_opened")
        self.assertEqual(manifest["accounting"]["raw_attempts"], 1000)
        self.assertEqual(manifest["accounting"]["generation_invocations"], 112)
        self.assertIs(manifest["b1_reference"]["regenerated"], False)
        self.assertEqual(
            manifest["checkpoint"]["weights_sha256_before_generation"], manifest["checkpoint"]["weights_sha256_after_generation"]
        )
        self.assertEqual(sorted(os.listdir(world.output)), sorted([
            "authorization_consumption.json", "isolated_runtime_cache", "m6_diagnostic_audited_attempts.jsonl",
            "m6_diagnostic_guardrails.json", "m6_diagnostic_invocation_outputs.json", "m6_diagnostic_manifest.json",
            "m6_diagnostic_manifest_sha256.json", "m6_diagnostic_metrics.json", "m6_diagnostic_raw_attempts.jsonl",
            "m6_diagnostic_report.json", "m6_diagnostic_schedule.json", "python_pycache", "rnagenesis_generation_output",
        ]))
        self.assertEqual(world.tree_snapshot(world.checkpoint_dir), world.checkpoint_tree_before)

    def test_generation_follows_the_accepted_schedule_with_one_call_per_chunk(self):
        world = SyntheticWorld(self.directory)
        world.run()
        schedule = json.loads(read(os.path.join(SCHEDULE_DIR, "development_pool_schedule.json")).decode("utf-8"))
        self.assertEqual(len(world.calls), 112)
        for call, invocation in zip(world.calls, schedule["invocations"]):
            argv = call["argv"]
            self.assertEqual(argv[argv.index("--dm_file") + 1], world.checkpoint_dir)
            self.assertEqual(argv[argv.index("--seed") + 1], str(invocation["invocation_seed"]))
            self.assertEqual(argv[argv.index("--batch_size") + 1], str(invocation["actual_chunk_size"]))
            self.assertEqual(argv[argv.index("--batch_num") + 1], "1")
            self.assertEqual(argv[argv.index("--max_seq_len") + 1], str(invocation["max_seq_len"]))
            self.assertEqual(call["cwd"], b1.GENERATION_CWD)
            self.assertIs(call["shell"], False)
            self.assertEqual(call["env"]["CUDA_VISIBLE_DEVICES"], "1")
            self.assertNotIn(b1.DIFFUSION_RELATIVE, " ".join(argv))
            self.assertNotIn(diag.B1_POOL_DIRECTORY, " ".join(argv))

    def test_raw_text_is_preserved_beside_the_normalised_form(self):
        world = SyntheticWorld(self.directory, mode="early_eos")
        world.run()
        raw_ledger = [json.loads(l) for l in read(os.path.join(world.output, diag.RAW_LEDGER_NAME)).decode().splitlines()]
        audited = [json.loads(l) for l in read(os.path.join(world.output, diag.AUDITED_LEDGER_NAME)).decode().splitlines()]
        self.assertEqual((len(raw_ledger), len(audited)), (1000, 1000))
        self.assertTrue(all("cleaned_sequence" not in row for row in raw_ledger))
        by_index = {row["original_attempt_index"]: row for row in audited}
        file_lines = {}
        generated = os.path.join(world.output, diag.GENERATION_OUTPUT_DIRECTORY)
        for folder in sorted(os.listdir(generated)):
            for name in os.listdir(os.path.join(generated, folder)):
                file_lines[folder] = read(os.path.join(generated, folder, name)).decode().splitlines()
        schedule = json.loads(read(os.path.join(SCHEDULE_DIR, "development_pool_schedule.json")).decode("utf-8"))
        eos = 0
        for invocation in schedule["invocations"]:
            lines = file_lines["invocation_%04d" % invocation["invocation_index"]]
            for position, index in enumerate(invocation["original_attempt_indexes"]):
                row = by_index[index]
                self.assertEqual(row["raw_decoded_text"], lines[position])
                self.assertEqual(raw_ledger[index]["raw_decoded_text"], lines[position])
                self.assertEqual(row["raw_decoded_text"], row["leading_boundary_marker_run"] + row["cleaned_sequence"] + row["trailing_boundary_marker_run"])
                if row["trailing_boundary_marker_run"] == "2":
                    eos += 1
                    self.assertIs(row["early_eos"], True)
        self.assertGreater(eos, 0)
        self.assertEqual(self.manifest(world)["accounting"]["early_eos_observations"], eos)

    def test_invalid_outputs_stay_counted_and_nothing_is_replaced_or_resampled(self):
        world = SyntheticWorld(self.directory, mode="invalid_block")
        outcome = world.run()
        self.assertEqual(outcome["guardrail_outcome"], "failed")
        manifest = self.manifest(world)
        self.assertEqual(len(world.calls), 112)
        accounting = manifest["accounting"]
        self.assertEqual(accounting["raw_attempts"], 1000)
        self.assertGreater(accounting["invalid_outputs"], 10)
        self.assertEqual(accounting["valid_outputs"] + accounting["invalid_outputs"], 1000)
        self.assertEqual((accounting["replacements"], accounting["resampled_attempts"], accounting["dropped_attempts"]), (0, 0, 0))
        self.assertFalse(manifest["hard_guardrails"]["checkpoint_eligible"])
        self.assertIs(manifest["consequence"]["eligible_for_m7"], False)
        self.assertIs(manifest["consequence"]["automatic_rerun"], False)
        self.assertIs(manifest["consequence"]["automatic_learning_rate_fallback"], False)
        self.assertEqual(manifest["closure"]["m6_complete"], False)
        audited = read(os.path.join(world.output, diag.AUDITED_LEDGER_NAME)).decode().splitlines()
        self.assertEqual(len(audited), 1000)

    def test_output_line_count_mismatch_is_a_consumed_failure_without_replacement(self):
        world = SyntheticWorld(self.directory, mode="short_output")
        schedule = json.loads(read(os.path.join(SCHEDULE_DIR, "development_pool_schedule.json")).decode("utf-8"))
        if schedule["invocations"][5]["actual_chunk_size"] < 2:
            self.skipTest("invocation 5 is a single-attempt chunk")
        with self.assertRaises(diag.DiagnosticError) as caught:
            world.run()
        self.assertEqual(caught.exception.code, "output_line_count_mismatch")
        self.assertEqual(len(world.calls), 6)
        self.assertFalse(os.path.exists(os.path.join(world.output, diag.MANIFEST_NAME)))
        failure = json.loads(read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode("utf-8"))
        self.assertEqual(failure["code"], "output_line_count_mismatch")
        self.assertIs(failure["resumable"], False)
        self.assertIs(failure["m6_complete"], False)
        self.assertTrue(os.path.exists(os.path.join(world.output, diag.CONSUMPTION_RECORD_NAME)))

    def test_output_directory_is_single_use(self):
        world = SyntheticWorld(self.directory)
        world.run()
        before = sorted(os.listdir(world.output))
        calls = len(world.calls)
        with self.assertRaises(diag.DiagnosticError) as caught:
            world.run()
        self.assertEqual(caught.exception.code, "output_directory_exists")
        self.assertEqual(len(world.calls), calls)
        self.assertEqual(sorted(os.listdir(world.output)), before)

    def test_unusable_fold_library_is_refused_before_consumption(self):
        world = SyntheticWorld(self.directory)

        def broken(sequence):
            raise ImportError("no RNA module")

        with self.assertRaises(diag.DiagnosticError) as caught:
            world.run(fold=broken)
        self.assertEqual(caught.exception.code, "fold_unavailable")
        self.assertFalse(os.path.exists(world.output))
        self.assertEqual(world.calls, [])

    def test_default_fold_is_the_pinned_viennarna(self):
        try:
            import RNA  # noqa: F401
        except ImportError:
            self.skipTest("ViennaRNA is not importable in this interpreter")
        features = diag.structure_features("GGGGAAAACCCC", diag._default_fold)
        self.assertLess(features["mfe"], 0.0)
        self.assertAlmostEqual(features["paired_fraction"], 8 / 12.0)

    def test_pushed_or_local_authorisation_commit_is_accepted(self):
        for origin in (None, "a" * 40):
            world = SyntheticWorld(tempfile.mkdtemp(dir=self.directory))
            world.origin = origin
            self.assertEqual(world.run()["status"], "success")

    def test_preflight_failure_does_not_consume_the_authorisation(self):
        world = SyntheticWorld(self.directory)
        bad_gpu = lambda parent, physical: {
            "physical_index": 1, "uuid": "GPU-other", "pci_bus": "00000000:61:00.0", "logical_device": "cuda:0",
            "device_type": "cuda", "cuda_device_count": 1, "cpu_fallback": False, "other_gpu_fallback": False,
        }
        with self.assertRaises(diag.DiagnosticError):
            world.run(gpu_preflight=bad_gpu)
        self.assertFalse(os.path.exists(world.output))
        self.assertEqual(world.calls, [])

    def test_provenance_drift_is_refused_before_consumption(self):
        for name, mutate in (
            ("dirty", lambda git: lambda repo, args: " M x\n" if str(repo) == diag.MRES_ROOT and args and args[0] == "status" else git(repo, args)),
            ("rnagenesis", lambda git: lambda repo, args: "f" * 40 + "\n" if str(repo) == diag.RNAGENESIS_ROOT and args == ["rev-parse", "HEAD"] else git(repo, args)),
            ("origin_elsewhere", lambda git: lambda repo, args: ("e" * 40 + "\n") if args == ["rev-parse", "origin/main"] else git(repo, args)),
            ("two_parents", lambda git: lambda repo, args: ("b" * 40 + "\n" + "d" * 40 + "\n") if args == ["rev-parse", "HEAD^@"] else git(repo, args)),
            ("wider_delta", lambda git: lambda repo, args: (diag.CONFIG_RELATIVE + "\nscripts/x.py\n") if args[:2] == ["diff", "--name-only"] else git(repo, args)),
        ):
            world = SyntheticWorld(tempfile.mkdtemp(dir=self.directory))
            with self.assertRaises(diag.DiagnosticError, msg=name):
                world.run(git=mutate(world.git))
            self.assertFalse(os.path.exists(world.output), name)

    def test_normalisation_failure_stops_the_run_and_is_recorded(self):
        world = SyntheticWorld(self.directory)
        original = b1.map_invocation_output

        def corrupt(payload, invocation, cleaner):
            records = original(payload, invocation, cleaner)
            if invocation["invocation_index"] == 3:
                records[0] = dict(records[0], cleaned_sequence=records[0]["cleaned_sequence"][:-1])
            return records

        with mock.patch.object(b1, "map_invocation_output", corrupt):
            with self.assertRaises(diag.DiagnosticError) as caught:
                world.run()
        self.assertIn(caught.exception.code, ("unexpected_output_normalization",))
        failure = json.loads(read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode("utf-8"))
        self.assertEqual(failure["code"], "unexpected_output_normalization")
        self.assertFalse(os.path.exists(os.path.join(world.output, diag.MANIFEST_NAME)))

    def test_checkpoint_change_during_generation_fails_the_run(self):
        world = SyntheticWorld(self.directory)
        original = world.subprocess_run
        weights = os.path.join(world.checkpoint_dir, diag.WEIGHT_MEMBER)

        def tamper(argv, cwd, env, shell=False):
            result = original(argv, cwd, env, shell)
            if len(world.calls) == 40:
                with open(weights, "ab") as handle:
                    handle.write(b"x")
            return result

        with self.assertRaises(diag.DiagnosticError):
            world.run(subprocess_run=tamper)
        self.assertFalse(os.path.exists(os.path.join(world.output, diag.MANIFEST_NAME)))

    def test_ref_eval_and_validation_are_structurally_denied(self):
        opened = []
        opener = lambda path: opened.append(path)
        for path, role in (
            ("/data/EVAL/x.txt", "TRAIN_TEXT_DIAGNOSTIC_ONLY"),
            ("/data/REF/x.txt", "TRAIN_TEXT_DIAGNOSTIC_ONLY"),
            ("/data/ref.csv", "TRAIN_TEXT_DIAGNOSTIC_ONLY"),
            ("/data/eval.csv", "TRAIN_TEXT_DIAGNOSTIC_ONLY"),
            (diag.TRAIN_PATH, "REF"),
            (diag.TRAIN_PATH, "EVAL"),
            ("/home/laura/rnagenesis-mres-data/development/ft_validation.csv", "VALIDATION_CSV"),
            (diag.production_pins()["train"]["path"], "VALIDATION_ARTIFACT"),
        ):
            with self.assertRaises(diag.DiagnosticError, msg=(path, role)) as caught:
                diag.consider_input_path(path, role, True, opener=opener)
            self.assertIn(caught.exception.code, ("ref_or_eval_access", "validation_access_not_requested"))
        for digest in contract.DENIED_HASHES:
            with self.assertRaises(diag.DiagnosticError) as caught:
                diag.consider_input_path(diag.TRAIN_PATH, "TRAIN_TEXT_DIAGNOSTIC_ONLY", True, claimed_hash=digest, opener=opener)
            self.assertEqual(caught.exception.code, "ref_or_eval_access")
        with self.assertRaises(diag.DiagnosticError):
            diag.consider_input_path("/somewhere/else.txt", "TRAIN_TEXT_DIAGNOSTIC_ONLY", True, opener=opener)
        with self.assertRaises(diag.DiagnosticError):
            diag.consider_input_path(diag.TRAIN_PATH, "TRAIN_TEXT_DIAGNOSTIC_ONLY", False, opener=opener)
        self.assertEqual(opened, [])
        for role in ("REF", "EVAL", "VALIDATION_CSV", "VALIDATION_ARTIFACT"):
            self.assertNotIn(role, diag.ACTIVE_ROLES)

    def test_a_ref_named_train_pin_is_refused_before_it_is_read(self):
        world = SyntheticWorld(self.directory)
        refused = os.path.join(self.directory, "ref.csv")
        shutil.copy(world.train_path, refused)
        world.pins["train"]["path"] = refused
        world.config_bytes = yaml_bytes(active_config_for(world.pins, world.output))
        world.virtual[diag.CONFIG_PATH] = world.config_bytes
        reads = []
        real = world.read_bytes
        with self.assertRaises(diag.DiagnosticError) as caught:
            world.run(read_bytes=lambda p: (reads.append(str(p)), real(p))[1])
        self.assertEqual(caught.exception.code, "ref_or_eval_access")
        self.assertNotIn(refused, reads)
        self.assertTrue(os.path.exists(os.path.join(world.output, diag.CONSUMPTION_RECORD_NAME)))
        self.assertTrue(os.path.exists(os.path.join(world.output, diag.FAILURE_RECORD_NAME)))
        self.assertFalse(os.path.exists(os.path.join(world.output, diag.MANIFEST_NAME)))

    def test_train_must_match_the_pinned_identity_and_length_vector(self):
        world = SyntheticWorld(self.directory)
        world.pins["train"]["sha256"] = "0" * 64
        world.config_bytes = yaml_bytes(active_config_for(world.pins, world.output))
        world.virtual[diag.CONFIG_PATH] = world.config_bytes
        with self.assertRaises(diag.DiagnosticError) as caught:
            world.run()
        self.assertEqual(caught.exception.code, "train_identity_mismatch")
        self.assertTrue(os.path.exists(os.path.join(world.output, diag.CONSUMPTION_RECORD_NAME)))
        failure = json.loads(read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode("utf-8"))
        self.assertEqual((failure["code"], failure["stage"]), ("train_identity_mismatch", "train_open"))
        self.assertEqual(world.calls, [])

    def test_the_module_never_writes_into_accepted_evidence(self):
        world = SyntheticWorld(self.directory)
        snapshots = {d: sorted(os.listdir(d)) for d in (diag.TRAINING_EVIDENCE_DIRECTORY, diag.B1_POOL_DIRECTORY, diag.SCHEDULE_DIRECTORY)}
        world.run()
        for directory, names in snapshots.items():
            self.assertEqual(sorted(os.listdir(directory)), names)

    def test_clean_run_leaves_eligibility_open_for_human_review(self):
        world = SyntheticWorld(self.directory)
        world.run()
        manifest = self.manifest(world)
        self.assertIs(manifest["hard_guardrails"]["checkpoint_eligible"], True)
        self.assertIsNone(manifest["consequence"]["eligible_for_m7"])
        self.assertIs(manifest["closure"]["human_review_required"], True)


class ManifestCompletenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp()
        world = SyntheticWorld(cls.directory)
        world.run()
        cls.world = world
        cls.pins = world.pins
        cls.manifest = json.loads(read(os.path.join(world.output, diag.MANIFEST_NAME)).decode("utf-8"))
        cls.raw = read(os.path.join(world.output, diag.MANIFEST_NAME))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, True)

    def test_the_run_manifest_is_canonical_and_complete(self):
        self.assertTrue(diag.validate_success_manifest(self.manifest, self.pins))
        self.assertEqual(set(self.manifest), set(diag.MANIFEST_KEYS))
        self.assertEqual(diag.canonical_json(self.manifest), self.raw)
        self.assertEqual(set(self.manifest["accounting"]), set(diag.ACCOUNTING_KEYS))
        self.assertNotIn("raw_decoded_text", self.raw.decode("utf-8"))

    def test_every_missing_or_unexpected_key_is_rejected(self):
        for key in diag.MANIFEST_KEYS:
            manifest = copy.deepcopy(self.manifest)
            del manifest[key]
            with self.assertRaises(diag.DiagnosticError, msg=key):
                diag.validate_success_manifest(manifest, self.pins)
        manifest = copy.deepcopy(self.manifest)
        manifest["extra"] = 1
        with self.assertRaises(diag.DiagnosticError):
            diag.validate_success_manifest(manifest, self.pins)
        for key in diag.ACCOUNTING_KEYS:
            manifest = copy.deepcopy(self.manifest)
            del manifest["accounting"][key]
            with self.assertRaises(diag.DiagnosticError, msg=key):
                diag.validate_success_manifest(manifest, self.pins)

    def test_contradictory_or_overclaiming_manifests_are_rejected(self):
        mutations = [
            lambda m: m["closure"].update(m6_complete=True),
            lambda m: m["closure"].update(m7_authorised=True),
            lambda m: m["closure"].update(checkpoint_selected=True),
            lambda m: m["closure"].update(human_review_required=False),
            lambda m: m["roles"].update(validation="opened"),
            lambda m: m["roles"].update(ref="opened"),
            lambda m: m["roles"].update(eval="opened"),
            lambda m: m["b1_reference"].update(regenerated=True),
            lambda m: m["b1_reference"].update(rerun=True),
            lambda m: m["checkpoint"].update(update=14),
            lambda m: m["checkpoint"].update(weights_sha256_after_generation="0" * 64),
            lambda m: m["schedule"].update(sha256="0" * 64),
            lambda m: m["accounting"].update(raw_attempts=999),
            lambda m: m["accounting"].update(generation_invocations=111),
            lambda m: m["accounting"].update(replacements=1),
            lambda m: m["accounting"].update(dropped_attempts=1),
            lambda m: m["accounting"].update(invalid_outputs=m["accounting"]["invalid_outputs"] + 1),
            lambda m: m["hard_guardrails"].update(checkpoint_eligible=False),
            lambda m: m["hard_guardrails"].update(exact_hit_rate_is_a_threshold=True),
            lambda m: m["hard_guardrails"]["decisions"].pop(),
            lambda m: m.update(status="failed"),
        ]
        for mutate in mutations:
            manifest = copy.deepcopy(self.manifest)
            mutate(manifest)
            with self.assertRaises(diag.DiagnosticError):
                diag.validate_success_manifest(manifest, self.pins)

    def test_manifest_records_the_five_approved_guardrails_only(self):
        self.assertEqual([d["id"] for d in self.manifest["hard_guardrails"]["decisions"]], [r[0] for r in diag.HARD_GUARDRAIL_RULES])
        self.assertEqual(self.manifest["normalisation"]["authority"], "approved_m1_cleaner")
        self.assertIs(self.manifest["normalisation"]["independent_reconciliation_passed"], True)


class StaticSafetyTests(unittest.TestCase):
    def test_module_has_no_reachable_ref_eval_or_validation_open(self):
        source = read(MODULE_PATH).decode("utf-8")
        self.assertNotIn("import torch", source)
        self.assertNotIn("ft_validation", source)
        self.assertNotIn("validation_artifact", source.replace("VALIDATION_ARTIFACT", ""))
        self.assertNotIn("EVAL_HASH", source)
        self.assertNotIn("REF_HASH", source)

    def test_module_imports_no_training_stack(self):
        tree = ast.parse(read(MODULE_PATH).decode("utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertFalse(imported & {"torch", "accelerate", "diffusers", "transformers", "numpy"})


class ConsumptionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)

    def test_train_and_checkpoint_are_untouched_until_the_output_directory_exists(self):
        world = SyntheticWorld(self.directory)
        events = []
        real_read = world.read_bytes
        real_mkdir = os.mkdir
        sensitive = (world.train_path, world.checkpoint_dir)

        def read_bytes(path):
            events.append(("read", str(path)))
            return real_read(path)

        def hash_file(path):
            events.append(("hash", str(path)))
            return world.sha256_file(path)

        def mkdir(path):
            events.append(("mkdir", str(path)))
            real_mkdir(path)

        def lstat(path):
            events.append(("lstat", str(path)))
            return os.lstat(path)

        world.run(read_bytes=read_bytes, sha256_file_fn=hash_file, mkdir=mkdir, lstat=lstat)
        consumed = events.index(("mkdir", world.output))
        touched = [i for i, (kind, path) in enumerate(events) if kind in ("read", "hash") and path.startswith(sensitive)]
        self.assertTrue(touched)
        self.assertGreater(min(touched), consumed)
        record_written = os.path.exists(os.path.join(world.output, diag.CONSUMPTION_RECORD_NAME))
        self.assertTrue(record_written)

    def test_consumption_record_is_written_before_sensitive_reads(self):
        world = SyntheticWorld(self.directory)
        order = []
        real_write = diag._exclusive_write

        def write(path, data):
            order.append(("write", os.path.basename(path)))
            real_write(path, data)

        def hash_file(path):
            if str(path).startswith(world.checkpoint_dir):
                order.append(("hash", "checkpoint"))
            return world.sha256_file(path)

        world.run(write_exclusive=write, sha256_file_fn=hash_file)
        self.assertEqual(order[0], ("write", diag.CONSUMPTION_RECORD_NAME))
        self.assertLess(order.index(("write", diag.CONSUMPTION_RECORD_NAME)), order.index(("hash", "checkpoint")))

    def test_every_failure_after_consumption_is_recorded_and_consumed(self):
        cases = {
            "checkpoint_hash": lambda w: w.run(sha256_file_fn=lambda p: "0" * 64 if str(p).endswith("config.json") and str(p).startswith(w.checkpoint_dir) else w.sha256_file(p)),
        }
        for name, runner in cases.items():
            world = SyntheticWorld(tempfile.mkdtemp(dir=self.directory))
            with self.assertRaises(diag.DiagnosticError):
                runner(world)
            self.assertTrue(os.path.exists(os.path.join(world.output, diag.CONSUMPTION_RECORD_NAME)), name)
            failure = json.loads(read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode("utf-8"))
            self.assertEqual(failure["stage"], "checkpoint_verification")
            self.assertEqual(failure["checkpoint_state"], "not_read")
            self.assertIs(failure["resumable"], False)
            with self.assertRaises(diag.DiagnosticError) as again:
                world.run()
            self.assertEqual(again.exception.code, "output_directory_exists")

    def test_preflight_failure_touches_neither_train_nor_checkpoint(self):
        world = SyntheticWorld(self.directory)
        touched = []
        real_read = world.read_bytes
        bad_gpu = lambda parent, physical: {"physical_index": 1, "uuid": "GPU-x", "pci_bus": "00000000:61:00.0", "logical_device": "cuda:0",
                                            "device_type": "cuda", "cuda_device_count": 1, "cpu_fallback": False, "other_gpu_fallback": False}

        def read_bytes(path):
            touched.append(str(path))
            return real_read(path)

        with self.assertRaises(diag.DiagnosticError):
            world.run(gpu_preflight=bad_gpu, read_bytes=read_bytes)
        self.assertFalse([p for p in touched if p.startswith((world.train_path, world.checkpoint_dir))])
        self.assertFalse(os.path.exists(world.output))


class InterruptionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)

    def interrupted_run(self, exception_type, at_call=3):
        world = SyntheticWorld(self.directory)
        original = world.subprocess_run

        def interrupt(argv, cwd, env, shell=False):
            if len(world.calls) + 1 == at_call:
                world.calls.append({"argv": list(argv)})
                raise exception_type("ACGUACGUACGUACGU secret message")
            return original(argv, cwd, env, shell)

        with self.assertRaises(exception_type):
            world.run(subprocess_run=interrupt)
        return world

    def test_keyboard_interrupt_and_system_exit_leave_consumed_failure_evidence(self):
        for exception_type in (KeyboardInterrupt, SystemExit):
            shutil.rmtree(self.directory, True)
            self.directory = tempfile.mkdtemp()
            world = self.interrupted_run(exception_type)
            self.assertTrue(os.path.exists(os.path.join(world.output, diag.CONSUMPTION_RECORD_NAME)))
            self.assertFalse(os.path.exists(os.path.join(world.output, diag.MANIFEST_NAME)))
            text = read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode("utf-8")
            failure = json.loads(text)
            self.assertEqual(failure["code"], "interrupted")
            self.assertEqual(failure["stage"], "generation")
            self.assertEqual(failure["invocation_index"], 2)
            self.assertEqual(failure["checkpoint_state"], "verified_before_generation")
            self.assertNotIn("secret", text)
            self.assertNotIn("ACGUACGU", text)
            with self.assertRaises(diag.DiagnosticError):
                world.run()

    def test_interruption_during_the_consumption_write_is_still_recorded(self):
        world = SyntheticWorld(self.directory)
        state = {"first": True}
        real = diag._exclusive_write

        def write(path, data):
            if state["first"]:
                state["first"] = False
                raise KeyboardInterrupt()
            real(path, data)

        with self.assertRaises(KeyboardInterrupt):
            world.run(write_exclusive=write)
        self.assertTrue(os.path.isdir(world.output))
        failure = json.loads(read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode("utf-8"))
        self.assertEqual((failure["code"], failure["stage"]), ("interrupted", "consumption"))
        self.assertFalse(os.path.exists(os.path.join(world.output, diag.MANIFEST_NAME)))


class FailureRecordTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)

    def failed(self, mode=None, **overrides):
        world = SyntheticWorld(self.directory, mode=mode or "clean")
        with self.assertRaises(Exception):
            world.run(**overrides)
        return world, json.loads(read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode("utf-8")), read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode()

    def test_record_has_the_required_fields_and_no_sensitive_text(self):
        def explode(argv, cwd, env, shell=False):
            raise RuntimeError("Traceback ACGUACGUACGUACGU tensor([1., 2.])")

        world, failure, text = self.failed(subprocess_run=explode)
        self.assertEqual(set(failure), set(diag.FAILURE_KEYS))
        self.assertEqual(failure["code"], "unexpected_runtime_failure")
        self.assertEqual(failure["detail"], "unexpected runtime failure; exception_class=RuntimeError")
        for forbidden in ("Traceback", "ACGUACGU", "tensor"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(failure["authorisation_id"], "m6_d1_update21_diagnostic_test")
        self.assertEqual(failure["authorization_commit"], "a" * 40)
        self.assertEqual(failure["authorization_parent_commit"], "b" * 40)
        self.assertEqual(failure["executing_implementation_commit"], "b" * 40)
        self.assertEqual(failure["output_directory"], world.output)
        self.assertEqual(failure["consumption_state"], "consumed_output_created")
        self.assertEqual(failure["gpu"], {"physical_index": 1, "uuid": "GPU-test", "pci_bus": "00000000:61:00.0",
                                          "cuda_visible_devices": "1", "logical_device": "cuda:0"})
        self.assertEqual((failure["stage"], failure["invocation_index"]), ("generation", 0))
        self.assertEqual(failure["checkpoint_state"], "verified_before_generation")
        self.assertEqual((failure["resumable"], failure["reuse_permitted"], failure["m6_complete"], failure["m7_authorised"]),
                         (False, False, False, False))
        self.assertEqual(diag.canonical_json(failure), text.encode("utf-8"))

    def test_invocation_index_and_checkpoint_change_are_recorded(self):
        world = SyntheticWorld(self.directory, mode="short_output")
        schedule = json.loads(read(os.path.join(SCHEDULE_DIR, "development_pool_schedule.json")).decode("utf-8"))
        if schedule["invocations"][5]["actual_chunk_size"] < 2:
            self.skipTest("invocation 5 is a single-attempt chunk")
        with self.assertRaises(diag.DiagnosticError):
            world.run()
        failure = json.loads(read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode("utf-8"))
        self.assertEqual((failure["code"], failure["invocation_index"]), ("output_line_count_mismatch", 5))

    def test_checkpoint_change_state_is_recorded(self):
        world = SyntheticWorld(self.directory)
        original = world.subprocess_run
        weights = os.path.join(world.checkpoint_dir, diag.WEIGHT_MEMBER)

        def tamper(argv, cwd, env, shell=False):
            result = original(argv, cwd, env, shell)
            if len(world.calls) == 112:
                with open(weights, "ab") as handle:
                    handle.write(b"x")
            return result

        with self.assertRaises(diag.DiagnosticError):
            world.run(subprocess_run=tamper)
        failure = json.loads(read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode("utf-8"))
        self.assertEqual(failure["checkpoint_state"], "changed_or_unverifiable_after_generation")
        self.assertIsNone(failure["invocation_index"])


class ExhaustiveManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp()
        cls.world = SyntheticWorld(cls.directory)
        cls.world.run()
        cls.manifest = json.loads(read(os.path.join(cls.world.output, diag.MANIFEST_NAME)).decode("utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, True)

    def validate(self, manifest):
        return diag.validate_success_manifest(manifest, self.world.pins)

    def test_every_nested_dictionary_rejects_a_missing_and_an_extra_key(self):
        def walk(value, path):
            if isinstance(value, dict):
                yield path, value
                for key, child in value.items():
                    if key in ("by_requested_length", "cleaned_length_distribution"):
                        continue
                    for item in walk(child, path + (key,)):
                        yield item

        checked = 0
        for path, node in walk(self.manifest, ()):
            if path and path[0] in ("metrics",) and len(path) > 1:
                continue
            if path == ("provenance", "implementation_file_hashes") or path == ("checkpoint", "members") or path == ("b1_reference", "files") or path == ("provenance", "frozen_encdec_assets"):
                pass
            for key in list(node):
                manifest = copy.deepcopy(self.manifest)
                target = manifest
                for step in path:
                    target = target[step]
                del target[key]
                with self.assertRaises(diag.DiagnosticError, msg=(path, key)):
                    self.validate(manifest)
                checked += 1
            manifest = copy.deepcopy(self.manifest)
            target = manifest
            for step in path:
                target = target[step]
            target["unexpected_extra_key"] = 1
            with self.assertRaises(diag.DiagnosticError, msg=path):
                self.validate(manifest)
        self.assertGreater(checked, 120)

    def test_cross_field_contradictions_are_rejected(self):
        mutations = [
            lambda m: m["authorisation"].update(authorization_commit="e" * 40),
            lambda m: m["authorisation"].update(executing_implementation_commit="e" * 40),
            lambda m: m["gpu"].update(cuda_visible_devices="0"),
            lambda m: m["gpu"].update(logical_device="cuda:1"),
            lambda m: m["provenance"]["mres"].update(head="e" * 40),
            lambda m: m["provenance"]["mres"].update(origin_main="e" * 40),
            lambda m: m["provenance"]["mres"].update(clean=False),
            lambda m: m["provenance"]["rnagenesis"].update(commit="e" * 40),
            lambda m: m["provenance"]["approved_cleaner"].update(sha256="0" * 64),
            lambda m: m["provenance"]["generation_inputs"].append({"relative_path": "configs/rnagenesis/diffusion/unet/config.json", "sha256": "0" * 64}),
            lambda m: m["provenance"].update(diffusion_model="b1"),
            lambda m: m["training_evidence"].update(manifest_sha256="0" * 64),
            lambda m: m["training_evidence"].update(consumption_state="consumed_failed"),
            lambda m: m["checkpoint"]["members"][diag.WEIGHT_MEMBER].update(sha256="0" * 64),
            lambda m: m["checkpoint"].update(weights_sha256_before_generation="0" * 64),
            lambda m: m["checkpoint"].update(directory="/elsewhere"),
            lambda m: m["checkpoint"].update(other_updates_loaded=True),
            lambda m: m["schedule"].update(length_vector_sha256="0" * 64),
            lambda m: m["schedule"].update(raw_attempts=999),
            lambda m: m["b1_reference"].update(evidence_directory="/elsewhere"),
            lambda m: m["b1_reference"]["files"]["development_pool_manifest.json"].update(sha256="0" * 64),
            lambda m: m["normalisation"].update(additional_trimming=True),
            lambda m: m["normalisation"].update(authority="strict_helper"),
            lambda m: m["accounting"].update(unique_valid_outputs=m["accounting"]["unique_valid_outputs"] - 1),
            lambda m: m["accounting"].update(exact_length_hits=m["accounting"]["exact_length_hits"] - 1),
            lambda m: m["metrics"].update(valid_outputs=m["metrics"]["valid_outputs"] - 1),
            lambda m: m["metrics"].update(exact_hit_rate=0.5),
            lambda m: m["hard_guardrails"]["values"].update(unique_fraction=0.5),
            lambda m: m["hard_guardrails"]["decisions"][0].update(passed=False),
            lambda m: m["hard_guardrails"]["decisions"][0].update(threshold=0.5),
            lambda m: m["hard_guardrails"]["decisions"][2].update(comparison="maximum"),
            lambda m: m["consequence"].update(eligible_for_m7=False),
            lambda m: m["consequence"].update(automatic_rerun=True),
            lambda m: m["report_only_diagnostics"].update(thresholds_defined=True),
            lambda m: m["comparison"]["d1_update21"].update(valid_outputs=1),
            lambda m: m["comparison"]["d1_guardrail_values"].update(unique_fraction=0.1),
            lambda m: m["comparison"].update(b1_guardrails_are_an_eligibility_decision=True),
            lambda m: m["roles"].update(validation="opened"),
            lambda m: m["ledgers"].update(metrics_sha256="nothex"),
            lambda m: m["closure"].update(m6_complete=True),
        ]
        for mutate in mutations:
            manifest = copy.deepcopy(self.manifest)
            mutate(manifest)
            with self.assertRaises(diag.DiagnosticError):
                self.validate(manifest)

    def test_written_manifest_is_canonical_and_matches_disk(self):
        raw = read(os.path.join(self.world.output, diag.MANIFEST_NAME))
        self.assertEqual(diag.canonical_json(json.loads(raw.decode())), raw)
        manifest = diag.verify_written_evidence(self.world.output, raw, self.world.deps(), self.world.pins)
        self.assertEqual(manifest, self.manifest)
        self.assertIn("consumption_record_sha256", manifest["ledgers"])

    def test_non_canonical_written_manifest_is_refused(self):
        raw = read(os.path.join(self.world.output, diag.MANIFEST_NAME))
        spaced = raw.replace(b",", b", ", 1)
        with self.assertRaises(diag.DiagnosticError):
            diag.verify_written_evidence(self.world.output, spaced, self.world.deps(), self.world.pins)


class EvidenceReverificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)

    def run_with_corrupted(self, victim):
        world = SyntheticWorld(self.directory)
        real = diag._exclusive_write

        def write(path, data):
            real(path, data[:-1] + b" " if os.path.basename(path) == victim else data)

        with self.assertRaises(diag.DiagnosticError) as caught:
            world.run(write_exclusive=write)
        return world, caught.exception

    def test_every_emitted_evidence_file_is_checked_against_the_manifest(self):
        for victim in list(diag.LEDGER_FILES.values()) + [diag.REPORT_NAME, diag.HASH_REPORT_NAME]:
            shutil.rmtree(self.directory, True)
            self.directory = tempfile.mkdtemp()
            world, error = self.run_with_corrupted(victim)
            if victim == diag.CONSUMPTION_RECORD_NAME:
                self.assertEqual(error.code, "evidence_verification_failed", victim)
            self.assertFalse(os.path.exists(os.path.join(world.output, diag.MANIFEST_NAME)), victim)
            failure = json.loads(read(os.path.join(world.output, diag.FAILURE_RECORD_NAME)).decode("utf-8"))
            self.assertIs(failure["resumable"], False, victim)

    def test_a_manifest_that_fails_independent_validation_is_withdrawn(self):
        world = SyntheticWorld(self.directory)
        real = diag._exclusive_write

        def write(path, data):
            if os.path.basename(path) == diag.MANIFEST_NAME:
                data = data.replace(b'"m6_complete":false', b'"m6_complete":true', 1)
            real(path, data)

        with self.assertRaises(diag.DiagnosticError):
            world.run(write_exclusive=write)
        self.assertFalse(os.path.exists(os.path.join(world.output, diag.MANIFEST_NAME)))
        self.assertTrue(os.path.exists(os.path.join(world.output, diag.FAILURE_RECORD_NAME)))


class ActiveAuthorisationHardeningTests(unittest.TestCase):
    OUTPUT = "/home/laura/rnagenesis-mres-runs/m6_d1_update21_diagnostic_test"

    def config(self):
        return active_config_for(diag.production_pins(), self.OUTPUT)

    def test_output_basename_must_equal_the_authorisation_id(self):
        config = self.config()
        config["diagnostic_generation_authorisation"]["authorisation_id"] = "something_else"
        config["execution"]["authorisation_id"] = "something_else"
        with self.assertRaises(diag.DiagnosticError) as caught:
            diag.assert_active_configuration(config)
        self.assertEqual(caught.exception.code, "authorisation_evidence_mismatch")

    def test_output_and_evidence_directories_must_be_identical(self):
        config = self.config()
        config["diagnostic_generation_authorisation"]["evidence_directory"] = self.OUTPUT + "_other"
        with self.assertRaises(diag.DiagnosticError):
            diag.assert_active_configuration(config)

    def test_timestamp_must_use_the_established_offset_format(self):
        good = "2026-10-07T09:00:00+11:00"
        for bad in ("2026-10-07 09:00:00+11:00", "2026-10-07T09:00:00Z", "2026-10-07T09:00:00+1100", "2026-10-07T09:00:00-05:00",
                    "2026-10-07T09:00+11:00", "7 October 2026", "", 20261007):
            config = self.config()
            config["diagnostic_generation_authorisation"]["authorisation_timestamp"] = bad
            with self.assertRaises(diag.DiagnosticError, msg=repr(bad)):
                diag.assert_active_configuration(config)
        config = self.config()
        config["diagnostic_generation_authorisation"]["authorisation_timestamp"] = good
        self.assertTrue(diag.assert_active_configuration(config))

    def test_symlink_components_in_run_root_or_output_ancestry_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            real_root = os.path.join(directory, "real")
            os.mkdir(real_root)
            link_root = os.path.join(directory, "link")
            os.symlink(real_root, link_root)
            name = "m6_d1_update21_diagnostic_test"
            config = active_config_for(diag.production_pins(), os.path.join(link_root, name))
            with self.assertRaises(diag.DiagnosticError) as caught:
                diag.assert_active_configuration(config, link_root)
            self.assertEqual(caught.exception.code, "output_directory_symlink")
            config = active_config_for(diag.production_pins(), os.path.join(real_root, name))
            os.symlink(real_root, os.path.join(real_root, name))
            with self.assertRaises(diag.DiagnosticError):
                diag.assert_active_configuration(config, real_root)
            os.remove(os.path.join(real_root, name))
            self.assertTrue(diag.assert_active_configuration(config, real_root))
            self.assertTrue(diag.assert_no_symlink_ancestry("/nonexistent/path/below"))

    def test_output_must_stay_a_new_direct_child_of_the_run_root(self):
        for path in (self.OUTPUT + "/nested", "/home/laura/rnagenesis-mres-runs/../m6_d1_update21_diagnostic_test", "/tmp/m6_d1_update21_diagnostic_test"):
            config = active_config_for(diag.production_pins(), path)
            with self.assertRaises(diag.DiagnosticError, msg=path):
                diag.assert_active_configuration(config)


class FinalHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp()
        cls.world = SyntheticWorld(cls.directory)
        cls.world.run()
        cls.output = cls.world.output
        cls.manifest = json.loads(read(os.path.join(cls.output, diag.MANIFEST_NAME)).decode("utf-8"))
        cls.metrics = real_metrics_module()
        schedule, _ = diag.rebuild_and_verify_schedule(read(os.path.join(SCHEDULE_DIR, "ordered_train_length_vector.json")))
        cls.b1_attempts = diag.load_b1_reference(diag.Dependencies(), cls.metrics, schedule)["attempts"]
        config = diag.load_config_bytes(cls.world.config_bytes)
        cls.authorisation = {key: config["diagnostic_generation_authorisation"][key] for key in diag.AUTHORISATION_KEYS}
        cls.expected = {"authorisation": cls.authorisation, "provenance": copy.deepcopy(cls.manifest["provenance"])}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, True)

    def validate(self, manifest, expected=True):
        return diag.validate_success_manifest(manifest, self.world.pins, copy.deepcopy(self.expected) if expected else None)

    def recompute(self):
        return {"metrics": self.metrics, "train_cores": self.world.train_cores, "b1_attempts": self.b1_attempts}

    def copy_output(self):
        target = os.path.join(tempfile.mkdtemp(dir=self.directory), "copy")
        shutil.copytree(self.output, target)
        return target

    def verify(self, output, **kwargs):
        raw = read(os.path.join(output, diag.MANIFEST_NAME))
        return diag.verify_written_evidence(output, raw, self.world.deps(), self.world.pins, self.expected, self.recompute())

    def rewrite(self, output, mutate_manifest=None, mutate_guardrails=None, mutate_report=None):
        """Rewrite files so every hash and structural relationship stays self-consistent."""
        manifest = json.loads(read(os.path.join(output, diag.MANIFEST_NAME)).decode("utf-8"))
        if mutate_guardrails:
            path = os.path.join(output, diag.GUARDRAILS_NAME)
            document = json.loads(read(path).decode("utf-8"))
            mutate_guardrails(document)
            data = diag.canonical_json(document)
            open(path, "wb").write(data)
            manifest["ledgers"]["guardrails_sha256"] = sha(data)
        if mutate_report:
            path = os.path.join(output, diag.REPORT_NAME)
            document = json.loads(read(path).decode("utf-8"))
            mutate_report(document)
            data = diag.canonical_json(document)
            open(path, "wb").write(data)
            manifest["report_only_diagnostics"]["sha256"] = sha(data)
        if mutate_manifest:
            mutate_manifest(manifest)
        raw = diag.canonical_json(manifest)
        open(os.path.join(output, diag.MANIFEST_NAME), "wb").write(raw)
        open(os.path.join(output, diag.HASH_REPORT_NAME), "wb").write(diag.canonical_json({
            "manifest_sha256": sha(raw),
            "raw_ledger_sha256": manifest["ledgers"]["raw_ledger_sha256"],
            "audited_ledger_sha256": manifest["ledgers"]["audited_ledger_sha256"],
        }))
        return manifest

    def test_unaltered_evidence_verifies_with_independent_recomputation(self):
        self.assertEqual(self.verify(self.output), self.manifest)

    def test_implementation_hash_replaced_by_another_valid_sha256_is_rejected(self):
        for path in diag.IMPLEMENTATION_FILE_PATHS:
            manifest = copy.deepcopy(self.manifest)
            manifest["provenance"]["implementation_file_hashes"][path] = "1" * 64
            with self.assertRaises(diag.DiagnosticError, msg=path):
                self.validate(manifest)
        # Consistent with the manifest but not with the active authorisation or the measurement.
        manifest = copy.deepcopy(self.manifest)
        manifest["provenance"]["implementation_file_hashes"][diag.MODULE_RELATIVE] = "1" * 64
        expected = copy.deepcopy(self.expected)
        expected["provenance"]["implementation_file_hashes"][diag.MODULE_RELATIVE] = "1" * 64
        with self.assertRaises(diag.DiagnosticError):
            diag.validate_success_manifest(manifest, self.world.pins, expected)
        expected = copy.deepcopy(self.expected)
        expected["authorisation"]["implementation_file_hashes"][diag.MODULE_RELATIVE] = "2" * 64
        with self.assertRaises(diag.DiagnosticError):
            diag.validate_success_manifest(copy.deepcopy(self.manifest), self.world.pins, expected)

    def test_generation_input_replacement_is_rejected_with_and_without_expected(self):
        for index in range(len(self.manifest["provenance"]["generation_inputs"])):
            manifest = copy.deepcopy(self.manifest)
            manifest["provenance"]["generation_inputs"][index]["sha256"] = "3" * 64
            for with_expected in (True, False):
                with self.assertRaises(diag.DiagnosticError, msg=(index, with_expected)):
                    self.validate(manifest, with_expected)
        manifest = copy.deepcopy(self.manifest)
        manifest["provenance"]["generation_inputs"].pop()
        with self.assertRaises(diag.DiagnosticError):
            self.validate(manifest, False)
        manifest = copy.deepcopy(self.manifest)
        manifest["provenance"]["generation_inputs"][0]["relative_path"] = "generation.py "
        with self.assertRaises(diag.DiagnosticError):
            self.validate(manifest, False)

    def test_encdec_and_patch_hash_or_size_replacement_is_rejected(self):
        for role in self.manifest["provenance"]["frozen_encdec_assets"]:
            for field, value in (("sha256", "4" * 64), ("bytes", self.manifest["provenance"]["frozen_encdec_assets"][role]["bytes"] + 1)):
                manifest = copy.deepcopy(self.manifest)
                manifest["provenance"]["frozen_encdec_assets"][role][field] = value
                for with_expected in (True, False):
                    with self.assertRaises(diag.DiagnosticError, msg=(role, field)):
                        self.validate(manifest, with_expected)

    def test_authorisation_and_gpu_must_equal_the_validated_authorisation(self):
        for mutate in (
            lambda m: m["authorisation"].update(authorisation_id="other"),
            lambda m: m["authorisation"].update(authorization_parent_commit="e" * 40, executing_implementation_commit="e" * 40),
            lambda m: m["gpu"].update(uuid="GPU-other"),
            lambda m: m["gpu"].update(pci_bus="00000000:99:00.0"),
            lambda m: m["gpu"].update(physical_index=2, cuda_visible_devices="2"),
        ):
            manifest = copy.deepcopy(self.manifest)
            mutate(manifest)
            with self.assertRaises(diag.DiagnosticError):
                self.validate(manifest)

    def test_exact_train_match_rate_is_independently_recomputed(self):
        output = self.copy_output()

        def manifest_change(m):
            g = m["hard_guardrails"]
            g["values"]["exact_train_match_rate"] = 0.5
            decision = g["decisions"][3]
            decision.update(value=0.5, passed=False)
            g.update(checkpoint_eligible=False, outcome="failed")
            m["consequence"]["eligible_for_m7"] = False
            m["comparison"]["d1_guardrail_values"]["exact_train_match_rate"] = 0.5

        def guardrail_change(d):
            d["values"]["exact_train_match_rate"] = 0.5
            d["decisions"][3].update(value=0.5, passed=False)
            d["checkpoint_eligible"] = False

        def report_change(d):
            d["comparison"]["d1_guardrail_values"]["exact_train_match_rate"] = 0.5

        manifest = self.rewrite(output, manifest_change, guardrail_change, report_change)
        # The altered evidence is internally consistent, so structural validation alone accepts it.
        self.validate(manifest)
        with self.assertRaises(diag.DiagnosticError) as caught:
            self.verify(output)
        self.assertEqual(caught.exception.code, "evidence_verification_failed")

    def test_metrics_file_altered_consistently_is_rejected_by_recomputation(self):
        output = self.copy_output()
        path = os.path.join(output, diag.METRICS_NAME)
        document = json.loads(read(path).decode("utf-8"))
        document["early_eos_observations"] += 1
        data = diag.canonical_json(document)
        open(path, "wb").write(data)

        def change(m):
            m["metrics"] = document
            m["ledgers"]["metrics_sha256"] = sha(data)
            m["accounting"]["early_eos_observations"] += 1

        self.rewrite(output, change)
        with self.assertRaises(diag.DiagnosticError):
            self.verify(output)

    def test_b1_comparison_altered_consistently_is_rejected(self):
        output = self.copy_output()

        def change_comparison(c):
            c["b1_accepted_pool"]["duplicates"] = 7
            c["b1_accepted_pool"]["unique_valid_outputs"] = 993
            c["b1_guardrail_values"]["unique_fraction"] = 0.993

        manifest = self.rewrite(
            output,
            lambda m: change_comparison(m["comparison"]),
            None,
            lambda d: change_comparison(d["comparison"]),
        )
        self.validate(manifest)
        with self.assertRaises(diag.DiagnosticError) as caught:
            self.verify(output)
        self.assertIn("B1", caught.exception.detail)

    def test_report_or_hash_report_symlink_is_rejected(self):
        for name in (diag.REPORT_NAME, diag.HASH_REPORT_NAME):
            output = self.copy_output()
            path = os.path.join(output, name)
            moved = os.path.join(output, "elsewhere_" + name)
            shutil.move(path, moved)
            os.symlink(moved, path)
            with self.assertRaises(diag.DiagnosticError, msg=name) as caught:
                self.verify(output)
            self.assertEqual(caught.exception.code, "evidence_verification_failed")

    def test_report_or_hash_report_that_is_not_a_regular_file_is_rejected(self):
        for name in (diag.REPORT_NAME, diag.HASH_REPORT_NAME):
            output = self.copy_output()
            path = os.path.join(output, name)
            os.remove(path)
            os.mkdir(path)
            with self.assertRaises(diag.DiagnosticError, msg=name):
                self.verify(output)

    def test_size_mismatch_between_stat_and_read_is_rejected(self):
        real = self.world.deps()
        short = diag.Dependencies(read_bytes=lambda p: real.read_bytes(p)[:-1] if str(p).endswith(diag.REPORT_NAME) else real.read_bytes(p))
        with self.assertRaises(diag.DiagnosticError):
            diag._read_evidence_file(os.path.join(self.output, diag.REPORT_NAME), short)

    def test_output_ancestor_that_is_a_regular_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = os.path.join(directory, "not_a_directory")
            open(blocker, "w").close()
            for path in (os.path.join(blocker, "out"), os.path.join(blocker, "sub", "out")):
                with self.assertRaises(diag.DiagnosticError, msg=path) as caught:
                    diag.assert_no_symlink_ancestry(path)
                self.assertEqual(caught.exception.code, "output_ancestry_not_directory")
            name = "m6_d1_update21_diagnostic_test"
            config = active_config_for(diag.production_pins(), os.path.join(blocker, name))
            with self.assertRaises(diag.DiagnosticError):
                diag.assert_active_configuration(config, blocker)
            real_root = os.path.join(directory, "runs")
            os.mkdir(real_root)
            config = active_config_for(diag.production_pins(), os.path.join(real_root, name))
            self.assertTrue(diag.assert_active_configuration(config, real_root))

    def test_run_with_a_file_as_run_root_never_consumes(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = os.path.join(directory, "runs")
            open(blocker, "w").close()
            world = SyntheticWorld(tempfile.mkdtemp(dir=directory))
            config = active_config_for(world.pins, os.path.join(blocker, "m6_d1_update21_diagnostic_test"))
            world.virtual[diag.CONFIG_PATH] = yaml_bytes(config)
            with self.assertRaises(diag.DiagnosticError):
                diag.run(world.deps(), run_root=blocker, pins=world.pins)
            self.assertEqual(world.calls, [])


class DocumentedPolicyTests(unittest.TestCase):
    def test_review_list_is_replaced_by_the_decided_policy(self):
        text = read(os.path.join(ROOT, "docs/fine_tuning/m6_pilot_implementation.md")).decode("utf-8")
        self.assertNotIn("Unresolved for review", text)
        self.assertIn("**Decided policy.**", text)
        for phrase in ("approved M1 cleaner is the primary normalisation authority", "sensitivity only", "VALIDATION stays unopened",
                       "EncDec assets are rehashed", "edit similarity", "never as sequence identity",
                       "must fetch `origin/main`", "immediately before launch"):
            self.assertIn(phrase, text, phrase)
        self.assertNotIn("maximum identity to TRAIN", text)
        self.assertNotIn("maximum_identity_to_train", text)

    def test_schema_and_protocol_use_the_edit_similarity_name(self):
        for relative in ("docs/fine_tuning/run_manifest_schema.md", "docs/fine_tuning/validation_protocol.md"):
            text = read(os.path.join(ROOT, relative)).decode("utf-8")
            self.assertNotIn("maximum identity to TRAIN", text, relative)
        self.assertIn("maximum edit similarity", read(os.path.join(ROOT, "docs/fine_tuning/validation_protocol.md")).decode())


if __name__ == "__main__":
    unittest.main()

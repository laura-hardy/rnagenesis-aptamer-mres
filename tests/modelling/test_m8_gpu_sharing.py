#!/usr/bin/env python3
"""Adversarial GPU-sharing tests. CPU fakes only. No CUDA and no generation launch."""

from __future__ import annotations

import copy
import csv
import inspect
import io
import json
import os
import shutil
import tempfile
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

import m8_support as support
from test_m8_generation import FakeDeps

generation = support.generation
assemble = support.assemble
M8Error = generation.M8Error

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL_ARM_MANIFESTS = (
    "/home/laura/rnagenesis-mres-runs/m8_b1_block_a_ac371ba_gpu1_attempt1/m8_arm_manifest.json",
    "/home/laura/rnagenesis-mres-runs/m8_b1_block_b_ac371ba_gpu1_attempt1/m8_arm_manifest.json",
    "/home/laura/rnagenesis-mres-runs/m8_d1_seed43_block_a_ac371ba_gpu1_attempt1/m8_arm_manifest.json",
)
FUTURE_GPU0_UUID = "GPU-b3c42ea9-ec47-c854-e469-cd78e443c76b"
RECOMMENDED_SHARED_FREE_BYTES = 32212254720


def snapshot_text(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def probe_for(entry, rows, **overrides):
    text = snapshot_text(rows)
    parsed = generation.parse_compute_app_snapshot(text)
    count = generation.selected_preexisting_compute_count(parsed, entry["gpu_uuid"])
    probe = {
        "compute_app_snapshot": text,
        "compute_app_snapshot_sha256": generation.sha256_bytes(text.encode("utf-8")),
        "cuda_visible_devices": str(entry["physical_gpu"]),
        "filesystem_free_bytes": 10 ** 12,
        "logical_device": "cuda:0",
        "memory_free_bytes": 10 ** 12,
        "memory_total_bytes": 2 * 10 ** 12,
        "memory_used_bytes": 10 ** 12,
        "observation_timestamp": "2026-10-09T00:00:00+00:00",
        "pci_bus": entry["pci_bus"],
        "physical_gpu": entry["physical_gpu"],
        "preexisting_compute_applications_observed": count > 0,
        "preexisting_compute_process_count": count,
        "uuid": entry["gpu_uuid"],
    }
    probe.update(overrides)
    return probe


def declared_probe(entry, rows, count, observed):
    """Build a probe without classifying PIDs, so a bad row can be rejected later."""
    text = snapshot_text(rows)
    return {
        "compute_app_snapshot": text,
        "compute_app_snapshot_sha256": generation.sha256_bytes(text.encode("utf-8")),
        "cuda_visible_devices": str(entry["physical_gpu"]),
        "filesystem_free_bytes": 10 ** 12,
        "logical_device": "cuda:0",
        "memory_free_bytes": 10 ** 12,
        "memory_total_bytes": 2 * 10 ** 12,
        "memory_used_bytes": 10 ** 12,
        "observation_timestamp": "2026-10-09T00:00:00+00:00",
        "pci_bus": entry["pci_bus"],
        "physical_gpu": entry["physical_gpu"],
        "preexisting_compute_applications_observed": observed,
        "preexisting_compute_process_count": count,
        "uuid": entry["gpu_uuid"],
    }


class SharingGateTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="m8share_")
        self._run_root = generation.RUN_ROOT
        generation.RUN_ROOT = self.root

    def tearDown(self):
        generation.RUN_ROOT = self._run_root
        shutil.rmtree(self.root, ignore_errors=True)

    def _entry(self, policy=generation.GPU_SHARING_EXCLUSIVE, arm="b1_block_a"):
        entry = support.generation_entry(arm, os.path.join(self.root, "m8_" + arm + "_share"), self.root)
        entry["gpu_sharing_policy"] = policy
        return entry

    def test_exclusive_zero_passes_and_other_gpu_processes_do_not_count(self):
        entry = self._entry()
        generation.assert_gpu_and_storage(entry, probe_for(entry, []))
        other = probe_for(entry, [("GPU-other", "9", "other-workload", "100 MiB")])
        checked = generation.assert_gpu_and_storage(entry, other)
        self.assertEqual(checked["preexisting_compute_process_count"], 0)
        self.assertFalse(checked["preexisting_compute_applications_observed"])

    def test_exclusive_positive_count_fails_before_consumption(self):
        entry = self._entry()
        rows = [(entry["gpu_uuid"], "9", "other-workload", "100 MiB")]
        with self.assertRaises(M8Error) as caught:
            generation.run_authorised_arm(
                entry,
                _Deps(entry, probe_for(entry, rows)),
                raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256,
            )
        self.assertEqual(caught.exception.code, "gpu_probe_invalid")
        self.assertFalse(os.path.exists(entry["output_directory"]))

    def test_shared_allows_preexisting_processes_and_records_them(self):
        entry = self._entry(generation.GPU_SHARING_SHARED_ALLOWED)
        entry["minimum_free_gpu_memory_bytes"] = 2048
        rows = [
            (entry["gpu_uuid"], "101", "other-workload", "1050 MiB"),
            (entry["gpu_uuid"], "102", "other-workload", "2694 MiB"),
        ]
        probe = probe_for(entry, rows)
        probe["memory_free_bytes"] = 4096
        probe["memory_total_bytes"] = 8192
        probe["memory_used_bytes"] = 4000
        self.assertLess(probe["memory_free_bytes"], RECOMMENDED_SHARED_FREE_BYTES)
        manifest = generation.run_authorised_arm(
            entry,
            _Deps(entry, probe),
            raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256,
        )
        gpu = manifest["gpu"]
        self.assertEqual(gpu["gpu_sharing_policy"], "shared_allowed")
        self.assertTrue(gpu["preexisting_compute_applications_observed"])
        self.assertEqual(gpu["preexisting_compute_process_count"], 2)
        self.assertEqual(gpu["compute_app_snapshot"], probe["compute_app_snapshot"])
        self.assertEqual(gpu["compute_app_snapshot_sha256"], probe["compute_app_snapshot_sha256"])
        self.assertEqual(gpu["observation_timestamp"], probe["observation_timestamp"])
        self.assertEqual(gpu["physical_gpu"], entry["physical_gpu"])
        self.assertEqual(gpu["uuid"], entry["gpu_uuid"])
        self.assertEqual(gpu["pci_bus"], entry["pci_bus"])
        self.assertEqual(gpu["memory_total_bytes"], 8192)
        self.assertEqual(gpu["memory_used_bytes"], 4000)
        self.assertEqual(gpu["memory_free_bytes"], 4096)
        self.assertEqual(gpu["minimum_free_memory_bytes"], 2048)
        self.assertNotIn("compute_processes", gpu)
        child = generation.build_child_environment({}, entry["physical_gpu"], entry["output_directory"], None)
        self.assertEqual(child["CUDA_VISIBLE_DEVICES"], str(entry["physical_gpu"]))
        self.assertEqual(child["CUDA_DEVICE_ORDER"], generation.CUDA_DEVICE_ORDER)

    def test_shared_zero_processes_passes(self):
        entry = self._entry(generation.GPU_SHARING_SHARED_ALLOWED)
        checked = generation.assert_gpu_and_storage(entry, probe_for(entry, []))
        self.assertEqual(checked["preexisting_compute_process_count"], 0)
        block = generation.gpu_manifest_block(entry, checked)
        self.assertEqual(block["gpu_sharing_policy"], "shared_allowed")
        self.assertFalse(block["preexisting_compute_applications_observed"])

    def test_absent_and_unknown_policies_are_rejected(self):
        entry = self._entry()
        absent = copy.deepcopy(entry)
        del absent["gpu_sharing_policy"]
        with self.assertRaises(M8Error) as caught:
            generation.assert_generation_entry_schema(absent)
        self.assertEqual(caught.exception.code, "authorisation_field_missing")
        for value in ("shared", "SHARED", "yes", True, None, ""):
            unknown = copy.deepcopy(entry)
            unknown["gpu_sharing_policy"] = value
            with self.assertRaises(M8Error) as caught:
                generation.assert_generation_entry_schema(unknown)
            self.assertEqual(caught.exception.code, "authorisation_scope_invalid")

    def test_shared_mode_still_rejects_memory_storage_and_identity(self):
        entry = self._entry(generation.GPU_SHARING_SHARED_ALLOWED)
        rows = [(entry["gpu_uuid"], "7", "other-workload", "10 MiB")]
        base = probe_for(entry, rows)
        cases = [
            ("memory_free_bytes", 1, "gpu_probe_invalid"),
            ("filesystem_free_bytes", 1, "insufficient_free_space"),
            ("uuid", "GPU-other", "gpu_probe_invalid"),
            ("pci_bus", "0000:11:22.0", "gpu_probe_invalid"),
            ("physical_gpu", 0, "gpu_probe_invalid"),
        ]
        for field, value, code in cases:
            probe = dict(base)
            probe[field] = value
            if field == "physical_gpu":
                probe["cuda_visible_devices"] = "0"
            with self.subTest(field=field):
                with self.assertRaises(M8Error) as caught:
                    generation.run_authorised_arm(
                        entry,
                        _Deps(entry, probe),
                        raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256,
                    )
                self.assertEqual(caught.exception.code, code)
                self.assertFalse(os.path.exists(entry["output_directory"]))

    def test_malformed_process_evidence_fails(self):
        entry = self._entry(generation.GPU_SHARING_SHARED_ALLOWED)
        rows = [(entry["gpu_uuid"], "7", "other-workload", "10 MiB")]
        complete = probe_for(entry, rows)
        missing = dict(complete)
        del missing["compute_app_snapshot"]
        with self.assertRaises(M8Error) as caught:
            generation.assert_gpu_and_storage(entry, missing)
        self.assertEqual(caught.exception.code, "gpu_probe_invalid")
        bad_hash = dict(complete)
        bad_hash["compute_app_snapshot_sha256"] = "ab" * 32
        with self.assertRaises(M8Error) as caught:
            generation.assert_gpu_and_storage(entry, bad_hash)
        self.assertEqual(caught.exception.code, "gpu_probe_invalid")
        incomplete = dict(complete)
        incomplete["compute_app_snapshot"] = "only,three,cells\n"
        incomplete["compute_app_snapshot_sha256"] = generation.sha256_bytes(incomplete["compute_app_snapshot"].encode("utf-8"))
        with self.assertRaises(M8Error) as caught:
            generation.assert_gpu_and_storage(entry, incomplete)
        self.assertEqual(caught.exception.code, "gpu_probe_invalid")
        labelled = dict(complete)
        labelled["preexisting_compute_applications_observed"] = False
        with self.assertRaises(M8Error) as caught:
            generation.assert_gpu_and_storage(entry, labelled)
        self.assertEqual(caught.exception.code, "gpu_probe_invalid")
        fabricated = probe_for(entry, [])
        fabricated["preexisting_compute_process_count"] = 2
        fabricated["preexisting_compute_applications_observed"] = True
        with self.assertRaises(M8Error) as caught:
            generation.assert_gpu_and_storage(entry, fabricated)
        self.assertEqual(caught.exception.code, "gpu_probe_invalid")
        stale = dict(complete)
        stale["observation_timestamp"] = "yesterday"
        with self.assertRaises(M8Error) as caught:
            generation.assert_gpu_and_storage(entry, stale)
        self.assertEqual(caught.exception.code, "gpu_probe_invalid")


class InactiveRetirementTests(unittest.TestCase):
    def test_checked_in_configuration_cannot_execute_the_retired_or_a_gpu0_id(self):
        document = generation.parse_config(generation.read_m8_config_bytes())
        generation.assert_inactive_configuration(document)
        self.assertEqual(document["authorisation_entries"], [])
        self.assertEqual(document["assembly_authorisation_entries"], [])
        retired = generation.RETIRED_GPU1_SEED44_BLOCK_B
        self.assertEqual(document["retired_unconsumed_authorisations"], [retired])
        self.assertFalse(any(value is True for value in document["execution"].values()))
        text = generation.read_m8_config_bytes().decode("utf-8")
        self.assertNotIn(FUTURE_GPU0_UUID, text)
        self.assertNotIn("shared_allowed", text)
        self.assertNotIn("32212254720", text)
        for authorisation_id in (retired["authorisation_id"], "m8_d1_seed44_block_b_gpu0_shared_attempt1"):
            code = generation.main(["--authorisation-id", authorisation_id])
            self.assertEqual(code, 2)
        self.assertFalse(os.path.lexists(retired["intended_output_directory"]))
        for relative in (
            "scripts/modelling/m8_generation.py",
            "scripts/modelling/m8_assemble.py",
            "config/experiments/M8_raw_generation.yaml",
        ):
            with open(os.path.join(REPO, relative), "r", encoding="utf-8") as handle:
                self.assertNotIn("32212254720", handle.read())

    def test_no_code_terminates_or_uses_a_historical_snapshot_as_authority(self):
        for relative in ("scripts/modelling/m8_generation.py", "scripts/modelling/m8_assemble.py"):
            with open(os.path.join(REPO, relative), "r", encoding="utf-8") as handle:
                text = handle.read()
            for token in ("os.kill", "os.killpg", "signal.SIG", "SIGKILL", "SIGTERM", "SIGSTOP", "pkill", "killall", "--gpu-reset"):
                self.assertNotIn(token, text, token)
        probe = inspect.getsource(generation.ProductionDeps.gpu_probe)
        self.assertIn("/usr/bin/nvidia-smi", probe)
        self.assertIn("COMPUTE_APP_QUERY", probe)
        self.assertIn("selected_preexisting_compute_count", probe)
        self.assertEqual(generation.COMPUTE_APP_QUERY, "gpu_uuid,pid,process_name,used_gpu_memory")
        self.assertNotIn("kill", probe)
        self.assertNotIn("m8-review-archives", probe)
        self.assertNotIn("import torch", probe)
        self.assertEqual(inspect.getsource(generation.run_authorised_arm).count("deps.gpu_probe("), 1)
        self.assertIn("selected_preexisting_compute_count", inspect.getsource(generation.assert_compute_app_evidence))


class SelectedGpuProcessRowTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="m8pid_")
        self._run_root = generation.RUN_ROOT
        generation.RUN_ROOT = self.root

    def tearDown(self):
        generation.RUN_ROOT = self._run_root
        shutil.rmtree(self.root, ignore_errors=True)

    def _entry(self, policy=generation.GPU_SHARING_EXCLUSIVE):
        entry = support.generation_entry("b1_block_a", os.path.join(self.root, "m8_b1_block_a_pid"), self.root)
        entry["gpu_sharing_policy"] = policy
        return entry

    def _assert_selected_pid_rejected(self, pid):
        entry = self._entry()
        rows = [(entry["gpu_uuid"], pid, "other-workload", "10 MiB")]
        parsed = generation.parse_compute_app_snapshot(snapshot_text(rows))
        with self.assertRaises(M8Error) as caught:
            generation.selected_preexisting_compute_count(parsed, entry["gpu_uuid"])
        self.assertEqual(caught.exception.code, "gpu_probe_invalid")
        self.assertIn("indeterminate", caught.exception.detail)
        with self.assertRaises(M8Error) as caught:
            generation.assert_gpu_and_storage(entry, declared_probe(entry, rows, 0, False))
        self.assertEqual(caught.exception.code, "gpu_probe_invalid")
        self.assertIn("indeterminate", caught.exception.detail)

    def test_positive_decimal_selected_gpu_pids_are_counted(self):
        entry = self._entry(generation.GPU_SHARING_SHARED_ALLOWED)
        for pid in ("1", "9", "101", "900163"):
            rows = [
                (entry["gpu_uuid"], pid, "other-workload", "10 MiB"),
                ("GPU-other", "55", "other-workload", "1 MiB"),
            ]
            parsed = generation.parse_compute_app_snapshot(snapshot_text(rows))
            self.assertEqual(generation.selected_preexisting_compute_count(parsed, entry["gpu_uuid"]), 1)
            checked = generation.assert_gpu_and_storage(entry, probe_for(entry, rows))
            self.assertEqual(checked["preexisting_compute_process_count"], 1)
            self.assertTrue(checked["preexisting_compute_applications_observed"])

    def test_multiple_selected_gpu_rows_are_counted_exactly(self):
        entry = self._entry(generation.GPU_SHARING_SHARED_ALLOWED)
        rows = [
            (entry["gpu_uuid"], "101", "other-workload", "10 MiB"),
            ("GPU-other", "7", "other-workload", "1 MiB"),
            (entry["gpu_uuid"], "102", "other-workload", "11 MiB"),
            (entry["gpu_uuid"], "103", "other-workload", "12 MiB"),
        ]
        parsed = generation.parse_compute_app_snapshot(snapshot_text(rows))
        self.assertEqual(generation.selected_preexisting_compute_count(parsed, entry["gpu_uuid"]), 3)
        deps = _CountingDeps(entry, probe_for(entry, rows))
        manifest = generation.run_authorised_arm(
            entry,
            deps,
            raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256,
        )
        self.assertEqual(deps.probe_calls, 1)
        self.assertEqual(manifest["gpu"]["preexisting_compute_process_count"], 3)
        self.assertEqual(manifest["gpu"]["compute_app_snapshot"], deps._probe["compute_app_snapshot"])
        self.assertEqual(manifest["gpu"]["observation_timestamp"], deps._probe["observation_timestamp"])

    def test_selected_gpu_na_pid_fails(self):
        self._assert_selected_pid_rejected("[N/A]")

    def test_selected_gpu_not_found_pid_fails(self):
        self._assert_selected_pid_rejected("[Not Found]")

    def test_selected_gpu_arbitrary_text_pid_fails(self):
        self._assert_selected_pid_rejected("not-a-pid")

    def test_selected_gpu_zero_pid_fails(self):
        self._assert_selected_pid_rejected("0")

    def test_selected_gpu_negative_pid_fails(self):
        self._assert_selected_pid_rejected("-1")

    def test_selected_gpu_empty_pid_fails(self):
        self._assert_selected_pid_rejected("")

    def test_other_gpu_indeterminate_row_does_not_increment_selected_count(self):
        entry = self._entry()
        other_rows = [
            ("GPU-other", "[N/A]", "other-workload", "10 MiB"),
            ("GPU-other", "[Not Found]", "other-workload", "10 MiB"),
            ("GPU-other", "not-a-pid", "other-workload", "10 MiB"),
            ("GPU-other", "0", "other-workload", "10 MiB"),
            ("GPU-other", "-4", "other-workload", "10 MiB"),
            ("GPU-other", "", "other-workload", "10 MiB"),
        ]
        parsed = generation.parse_compute_app_snapshot(snapshot_text(other_rows))
        self.assertEqual(generation.selected_preexisting_compute_count(parsed, entry["gpu_uuid"]), 0)
        checked = generation.assert_gpu_and_storage(entry, probe_for(entry, other_rows))
        self.assertEqual(checked["preexisting_compute_process_count"], 0)
        self.assertFalse(checked["preexisting_compute_applications_observed"])
        mixed = [
            ("GPU-other", "[N/A]", "other-workload", "10 MiB"),
            (entry["gpu_uuid"], "42", "other-workload", "10 MiB"),
        ]
        parsed_mixed = generation.parse_compute_app_snapshot(snapshot_text(mixed))
        self.assertEqual(generation.selected_preexisting_compute_count(parsed_mixed, entry["gpu_uuid"]), 1)

    def test_exclusive_and_shared_allowed_reject_indeterminate_selected_gpu_rows(self):
        pids = ("[N/A]", "[Not Found]", "not-a-pid", "0", "-7", "")
        for policy in (generation.GPU_SHARING_EXCLUSIVE, generation.GPU_SHARING_SHARED_ALLOWED):
            for pid in pids:
                with self.subTest(policy=policy, pid=pid):
                    entry = self._entry(policy)
                    rows = [
                        (entry["gpu_uuid"], "42", "other-workload", "10 MiB"),
                        (entry["gpu_uuid"], pid, "other-workload", "11 MiB"),
                    ]
                    with self.assertRaises(M8Error) as caught:
                        generation.run_authorised_arm(
                            entry,
                            _Deps(entry, declared_probe(entry, rows, 1, True)),
                            raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256,
                        )
                    self.assertEqual(caught.exception.code, "gpu_probe_invalid")
                    self.assertIn("indeterminate", caught.exception.detail)
                    self.assertFalse(os.path.exists(entry["output_directory"]))


class AssemblySharingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="m8shareasm_")
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

    def _source(self, sealed):
        return {"block": sealed["block"], "byte_count": sealed["byte_count"], "path": sealed["path"], "sha256": sealed["sha256"]}

    def _rewrite(self, sealed, name, mutator):
        dest = os.path.join(self.root, name)
        shutil.copytree(os.path.dirname(sealed["path"]), dest)
        manifest_path = os.path.join(dest, generation.MANIFEST_NAME)
        ledger_path = os.path.join(dest, generation.LEDGER_NAME)
        with open(manifest_path, "rb") as handle:
            manifest = json.loads(handle.read().decode("utf-8"))
        with open(ledger_path, "rb") as handle:
            records = [json.loads(line) for line in handle.read().split(b"\n")[:-1]]
        mutator(manifest)
        manifest["run_id"] = name
        manifest["authorization"]["authorisation_id"] = name
        for record in records:
            record["authorization_id"] = name
            record["run_id"] = name
        ledger = b"".join(generation.canonical_bytes(record) for record in records)
        with open(ledger_path, "wb") as handle:
            handle.write(ledger)
        manifest["raw_attempt_ledger_sha256"] = generation.sha256_bytes(ledger)
        manifest["raw_attempt_ledger_byte_count"] = len(ledger)
        manifest["raw_attempt_count"] = len(records)
        blob = generation.canonical_bytes(manifest)
        with open(manifest_path, "wb") as handle:
            handle.write(blob)
        return {
            "block": sealed["block"],
            "byte_count": len(blob),
            "path": manifest_path,
            "sha256": generation.sha256_bytes(blob),
        }

    def _assemble(self, left, right, name):
        from test_m8_revision import _assembly_entry

        entry = _assembly_entry(self.root, [self._source(left), self._source(right)], name)
        return assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)

    def test_historical_exclusive_manifests_assemble(self):
        def historical(manifest):
            gpu = manifest["gpu"]
            manifest["manifest_schema_version"] = generation.HISTORICAL_MANIFEST_SCHEMA_VERSION
            manifest["schema_version"] = generation.HISTORICAL_MANIFEST_SCHEMA_VERSION
            manifest["gpu"] = {
                "compute_processes": 0,
                "logical_device": gpu["logical_device"],
                "memory_free_bytes": gpu["memory_free_bytes"],
                "memory_total_bytes": gpu["memory_total_bytes"],
                "minimum_free_memory_bytes": gpu["minimum_free_memory_bytes"],
                "pci_bus": gpu["pci_bus"],
                "physical_gpu": gpu["physical_gpu"],
                "uuid": gpu["uuid"],
            }

        left = self._rewrite(self.arms["A"], "m8_hist_a", historical)
        right = self._rewrite(self.arms["B"], "m8_hist_b", historical)
        result = self._assemble(left, right, "m8_asm_historical")
        self.assertEqual(result["manifest"]["raw_attempt_count"], 30000)

    def test_shared_manifest_assembles_beside_exclusive(self):
        def shared(manifest):
            gpu = manifest["gpu"]
            text = snapshot_text(
                [
                    (gpu["uuid"], "201", "other-workload", "1050 MiB"),
                    (gpu["uuid"], "202", "other-workload", "2694 MiB"),
                ]
            )
            gpu["gpu_sharing_policy"] = "shared_allowed"
            gpu["compute_app_snapshot"] = text
            gpu["compute_app_snapshot_sha256"] = generation.sha256_bytes(text.encode("utf-8"))
            gpu["preexisting_compute_applications_observed"] = True
            gpu["preexisting_compute_process_count"] = 2

        left = self._rewrite(self.arms["A"], "m8_shared_a", shared)
        result = self._assemble(left, self.arms["B"], "m8_asm_shared")
        self.assertEqual(result["manifest"]["raw_attempt_count"], 30000)

    def test_inconsistent_or_fabricated_sharing_evidence_is_refused(self):
        def bad_hash(manifest):
            manifest["gpu"]["compute_app_snapshot_sha256"] = "cd" * 32

        def exclusive_with_processes(manifest):
            gpu = manifest["gpu"]
            text = snapshot_text([(gpu["uuid"], "9", "other-workload", "10 MiB")])
            gpu["gpu_sharing_policy"] = "exclusive"
            gpu["compute_app_snapshot"] = text
            gpu["compute_app_snapshot_sha256"] = generation.sha256_bytes(text.encode("utf-8"))
            gpu["preexisting_compute_applications_observed"] = True
            gpu["preexisting_compute_process_count"] = 1

        def false_label(manifest):
            manifest["gpu"]["preexisting_compute_applications_observed"] = True
            manifest["gpu"]["preexisting_compute_process_count"] = 1

        def unknown(manifest):
            manifest["gpu"]["gpu_sharing_policy"] = "share"

        def historical_positive(manifest):
            manifest["manifest_schema_version"] = generation.HISTORICAL_MANIFEST_SCHEMA_VERSION
            manifest["schema_version"] = generation.HISTORICAL_MANIFEST_SCHEMA_VERSION
            gpu = manifest["gpu"]
            manifest["gpu"] = {
                "compute_processes": 1,
                "logical_device": gpu["logical_device"],
                "memory_free_bytes": gpu["memory_free_bytes"],
                "memory_total_bytes": gpu["memory_total_bytes"],
                "minimum_free_memory_bytes": gpu["minimum_free_memory_bytes"],
                "pci_bus": gpu["pci_bus"],
                "physical_gpu": gpu["physical_gpu"],
                "uuid": gpu["uuid"],
            }

        def mixed_schema(manifest):
            manifest["manifest_schema_version"] = generation.HISTORICAL_MANIFEST_SCHEMA_VERSION
            manifest["schema_version"] = generation.HISTORICAL_MANIFEST_SCHEMA_VERSION

        cases = (
            ("m8_bad_hash", bad_hash),
            ("m8_exclusive_busy", exclusive_with_processes),
            ("m8_false_label", false_label),
            ("m8_unknown_policy", unknown),
            ("m8_hist_positive", historical_positive),
            ("m8_mixed_schema", mixed_schema),
        )
        for index, (name, mutator) in enumerate(cases):
            with self.subTest(name=name):
                left = self._rewrite(self.arms["A"], name, mutator)
                with self.assertRaises(M8Error) as caught:
                    self._assemble(left, self.arms["B"], "m8_asm_reject_{}".format(index))
                self.assertEqual(caught.exception.code, "assembly_invalid")

    def test_assembly_rejects_indeterminate_selected_gpu_pid_evidence(self):
        def indeterminate(pid, policy):
            def mutator(manifest):
                gpu = manifest["gpu"]
                text = snapshot_text([(gpu["uuid"], pid, "other-workload", "10 MiB")])
                gpu["gpu_sharing_policy"] = policy
                gpu["compute_app_snapshot"] = text
                gpu["compute_app_snapshot_sha256"] = generation.sha256_bytes(text.encode("utf-8"))
                gpu["preexisting_compute_applications_observed"] = False
                gpu["preexisting_compute_process_count"] = 0
            return mutator

        cases = (
            ("[N/A]", "shared_allowed"),
            ("[Not Found]", "shared_allowed"),
            ("not-a-pid", "exclusive"),
            ("0", "shared_allowed"),
            ("-1", "exclusive"),
            ("", "shared_allowed"),
        )
        for index, (pid, policy) in enumerate(cases):
            with self.subTest(pid=pid, policy=policy):
                left = self._rewrite(self.arms["A"], "m8_indet_{}".format(index), indeterminate(pid, policy))
                with self.assertRaises(M8Error) as caught:
                    self._assemble(left, self.arms["B"], "m8_asm_indet_{}".format(index))
                self.assertEqual(caught.exception.code, "assembly_invalid")
                self.assertIn("indeterminate", caught.exception.detail)

    def test_real_historical_arm_gpu_blocks_remain_valid(self):
        for path in REAL_ARM_MANIFESTS:
            with open(path, "rb") as handle:
                manifest = json.loads(handle.read().decode("utf-8"))
            self.assertEqual(manifest["manifest_schema_version"], generation.HISTORICAL_MANIFEST_SCHEMA_VERSION)
            self.assertEqual(tuple(sorted(manifest["gpu"])), generation.HISTORICAL_GPU_KEYS)
            self.assertEqual(manifest["gpu"]["compute_processes"], 0)
            assemble._validate_arm_gpu(manifest["gpu"], manifest["environment"], manifest["manifest_schema_version"])
            self.assertNotIn("gpu_sharing_policy", manifest["gpu"])


class _Deps(FakeDeps):
    def __init__(self, entry, probe):
        super(_Deps, self).__init__(entry)
        self._probe = probe

    def gpu_probe(self, environ):
        return dict(self._probe)


class _CountingDeps(_Deps):
    def __init__(self, entry, probe):
        super(_CountingDeps, self).__init__(entry, probe)
        self.probe_calls = 0

    def gpu_probe(self, environ):
        self.probe_calls += 1
        return super(_CountingDeps, self).gpu_probe(environ)


if __name__ == "__main__":
    unittest.main()

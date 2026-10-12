#!/usr/bin/env python3
"""CPU assembly tests. Generation files do not make assembly runnable."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import uuid

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import m8_support as support

assemble = support.assemble
generation = support.generation
schedule = support.schedule
M8Error = generation.M8Error


def _entry(condition, sources, root=None):
    root = generation.RUN_ROOT if root is None else root
    name = "m8_asm_" + uuid.uuid4().hex
    output = os.path.join(root, name)
    return {
        "activation_status": "active_unconsumed",
        "active_configuration_sha256": "ab" * 32,
        "authorisation_id": name,
        "authorization_parent_commit": "a" * 40,
        "condition_id": condition,
        "consumed": False,
        "executing_implementation_commit": "b" * 40,
        "implementation_file_hashes": support.implementation_file_hashes(),
        "ld_library_path": None,
        "output_directory": output,
        "reuse_permitted": False,
        "run_root": root,
        "single_use": True,
        "sources": sources,
    }


def _binding(sealed):
    return {"block": sealed["block"], "byte_count": sealed["byte_count"], "path": sealed["path"], "sha256": sealed["sha256"]}


class AssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="m8asm_")
        cls._run_root = generation.RUN_ROOT
        generation.RUN_ROOT = cls.root
        cls.b1 = {
            "A": support.materialise_arm(os.path.join(cls.root, "m8_b1_a"), "b1_block_a"),
            "B": support.materialise_arm(os.path.join(cls.root, "m8_b1_b"), "b1_block_b"),
        }
        cls.d1 = {
            "A": support.materialise_arm(os.path.join(cls.root, "m8_d1_a"), "d1_seed43_block_a"),
            "B": support.materialise_arm(os.path.join(cls.root, "m8_d1_b"), "d1_seed44_block_b"),
        }

    @classmethod
    def tearDownClass(cls):
        generation.RUN_ROOT = cls._run_root
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_existing_files_do_not_make_assembly_runnable(self):
        calls = []

        def bomb(*_args, **_kwargs):
            calls.append("side")
            raise AssertionError("side effect")

        original = generation.ProductionDeps
        generation.ProductionDeps = bomb
        saved = assemble.assemble_authorised
        assemble.assemble_authorised = bomb
        try:
            code = assemble.main(["--authorisation-id", "m8_assemble_review"])
        finally:
            generation.ProductionDeps = original
            assemble.assemble_authorised = saved
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])

    def test_b1_and_d1_combine_to_30000_and_ignore_source_order(self):
        cases = (
            (generation.CONDITION_B1, self.b1, None),
            (generation.CONDITION_D1, self.d1, (43, 44)),
        )
        for condition, arms, seeds in cases:
            forward = _entry(condition, [_binding(arms["A"]), _binding(arms["B"])])
            reverse = _entry(condition, [_binding(arms["B"]), _binding(arms["A"])])
            first = assemble.assemble_authorised(forward, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
            second = assemble.assemble_authorised(reverse, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
            self.assertEqual(first["ledger"], second["ledger"])
            self.assertEqual(len(first["records"]), 30000)
            self.assertEqual([row["master_attempt_index"] for row in first["records"]], list(range(30000)))
            blocks = {row["technical_block"] for row in first["records"]}
            self.assertEqual(blocks, {"A", "B"})
            self.assertEqual(sum(1 for row in first["records"] if row["technical_block"] == "A"), 15000)
            self.assertEqual(sum(1 for row in first["records"] if row["technical_block"] == "B"), 15000)
            if seeds is not None:
                for seed in seeds:
                    self.assertEqual(sum(1 for row in first["records"] if row["d1_training_seed"] == seed), 15000)
            by_index = {row["master_attempt_index"]: row["raw_decoded_text"] for row in first["records"]}
            self.assertEqual(by_index[0], "")
            self.assertEqual(by_index[1], "hello")
            self.assertTrue(any(text == "ACGU" for text in by_index.values()))
            self.assertFalse(first["manifest"]["parsing_performed"])
            self.assertFalse(first["manifest"]["filtering_performed"])
            self.assertFalse(first["manifest"]["cleaner_invoked"])
            self.assertFalse(first["manifest"]["deduplication_performed"])
            self.assertFalse(first["manifest"]["metric_computation_performed"])
            self.assertFalse(any(first["manifest"]["sequence_access"].values()))
            self.assertEqual(
                [row["sha256"] for row in first["manifest"]["source_arm_manifests"]],
                [arms["A"]["sha256"], arms["B"]["sha256"]],
            )
            for record in first["records"]:
                self.assertFalse(assemble.FORBIDDEN_RECORD_KEYS.intersection(record))

    def test_missing_extra_duplicate_and_mismatched_arms_fail(self):
        arms = self.b1
        base = [_binding(arms["A"]), _binding(arms["B"])]
        with tempfile.TemporaryDirectory() as root:
            entry = _entry(generation.CONDITION_D1, base, root=generation.RUN_ROOT)
            with self.assertRaises(M8Error):
                assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        swapped = [_binding(arms["B"]), _binding(arms["A"])]
        swapped[0] = dict(swapped[0])
        swapped[0]["block"] = "A"
        with tempfile.TemporaryDirectory() as root:
            entry = _entry(generation.CONDITION_B1, swapped)
            with self.assertRaises(M8Error):
                assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        altered = self._altered_arm(arms["A"], lambda manifest, records: records[:-1])
        with tempfile.TemporaryDirectory() as root:
            entry = _entry(generation.CONDITION_B1, [altered, _binding(arms["B"])])
            with self.assertRaises(M8Error):
                assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        extra = self._altered_arm(
            arms["A"],
            lambda manifest, records: records + [dict(records[-1], master_attempt_index=30000)],
        )
        with tempfile.TemporaryDirectory() as root:
            entry = _entry(generation.CONDITION_B1, [extra, _binding(arms["B"])])
            with self.assertRaises(M8Error):
                assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)
        duplicate = self._altered_arm(
            arms["A"],
            lambda manifest, records: records[:-1] + [dict(records[-1], master_attempt_index=records[-2]["master_attempt_index"])],
        )
        with tempfile.TemporaryDirectory() as root:
            entry = _entry(generation.CONDITION_B1, [duplicate, _binding(arms["B"])])
            with self.assertRaises(M8Error):
                assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)

    def test_wrong_seed_and_altered_raw_text_fail(self):
        def wrong_seed(manifest, records):
            manifest["d1_training_seed"] = 44
            return records

        altered = self._altered_arm(self.d1["A"], wrong_seed)
        with tempfile.TemporaryDirectory() as root:
            entry = _entry(generation.CONDITION_D1, [altered, _binding(self.d1["B"])])
            with self.assertRaises(M8Error):
                assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)

        def wrong_text(manifest, records):
            records[0]["raw_decoded_text"] = records[0]["raw_decoded_text"] + "Z"
            return records

        changed = self._altered_arm(self.b1["A"], wrong_text)
        with tempfile.TemporaryDirectory() as root:
            entry = _entry(generation.CONDITION_B1, [changed, _binding(self.b1["B"])])
            with self.assertRaises(M8Error):
                assemble.assemble_authorised(entry, support.ByteDeps(), raw_config_sha256=support.EXPLICIT_CONFIGURATION_RAW_SHA256)

    def _altered_arm(self, sealed, mutator):
        directory = tempfile.mkdtemp(prefix="m8alt_", dir=self.root)
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
        ledger = b"".join(generation.canonical_bytes(record) for record in records)
        with open(ledger_path, "wb") as handle:
            handle.write(ledger)
        manifest["raw_attempt_ledger_sha256"] = generation.sha256_bytes(ledger)
        manifest["raw_attempt_count"] = len(records)
        blob = generation.canonical_bytes(manifest)
        with open(manifest_path, "wb") as handle:
            handle.write(blob)
        return {"block": sealed["block"], "byte_count": len(blob), "path": manifest_path, "sha256": generation.sha256_bytes(blob)}


if __name__ == "__main__":
    unittest.main()

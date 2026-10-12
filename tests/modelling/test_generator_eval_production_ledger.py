"""Synthetic tests for the M9 production derived-ledger runner.

No sealed source, protected role, model, or evaluation file is opened.
Sequences in this module are constructed literals.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)

import generator_eval_production_ledger as runner

VALID_A = "ACGUACGU"
VALID_B = "GGGGCCCC"
VALID_C = "UUUUAAAA"
RELATIVE = "raw/invocation_0000/seqs_wo_guidance_top_p=0.95_2_16_m8_i0000_seed800000_len20.txt"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def jsonl(records):
    chunks = []
    for record in records:
        chunks.append(json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        chunks.append(b"\n")
    return b"".join(chunks)


def m8_record(condition, record_id, text, training_seed=None, master=0, block="A"):
    label = {
        "B1": "B1_generic_released_rnagenesis",
        "D1": "D1_mres_curated_aptamer_diffusion_adapted",
    }[condition]
    return {
        "authorization_id": "synthetic-auth",
        "batch_number": 0,
        "checkpoint_identity": "synthetic-checkpoint",
        "condition_id": label,
        "d1_training_seed": None if condition == "B1" else training_seed,
        "generation_seed": 800000 + master,
        "invocation_index": 0,
        "line_index": master,
        "master_attempt_index": master,
        "max_seq_len": 21,
        "raw_decoded_text": text,
        "record_id": record_id,
        "requested_biological_length": 20,
        "run_id": "synthetic-run",
        "schema_version": "m8-raw-attempt-1",
        "source_raw_file_relative_path": RELATIVE,
        "source_raw_file_sha256": "ab" * 32,
        "technical_block": block,
        "within_batch_position": 0,
    }


def b2_record(index, sequence):
    encoded = sequence.encode("utf-8") if isinstance(sequence, str) else b"invented"
    return {
        "attempt_index": index,
        "seed": 7,
        "sampled_length": 8,
        "sequence": sequence,
        "valid_acgu": True,
        "sequence_sha256": sha256(encoded),
    }


def read_jsonl(path):
    rows = []
    with open(path, "rb") as handle:
        blob = handle.read()
    text = blob.decode("utf-8")
    if "\r" in text:
        raise AssertionError("CR")
    if not text.endswith("\n"):
        raise AssertionError("final LF")
    for line in text.split("\n")[:-1]:
        rows.append(json.loads(line))
    return rows, blob


class ProductionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = self.temp.name
        self.sources = os.path.join(self.root, "sources")
        self.output = os.path.join(self.root, "out")
        os.makedirs(self.sources)
        self.manifest_path = os.path.join(self.sources, "source-manifest.json")
        self._write_fixture()

    def tearDown(self):
        self.temp.cleanup()

    def _write_fixture(self, b1_hash=None):
        b0_a = ("11" + VALID_A + "\n" + VALID_A + "\n").encode("utf-8")
        b0_b = (VALID_B + "\n").encode("utf-8")
        b1_rows = [
            m8_record("B1", "synthetic-b1-0", VALID_A, master=0),
            m8_record("B1", "synthetic-b1-1", VALID_A, master=1),
            m8_record("B1", "synthetic-b1-2", VALID_B, master=2),
            m8_record("B1", "synthetic-b1-3", "", master=3),
            m8_record("B1", "synthetic-b1-4", VALID_A, master=4),
        ]
        b1_rows[4]["raw_decoded_text"] = None
        b1 = jsonl(b1_rows)
        b2 = jsonl([b2_record(0, VALID_A), b2_record(1, "ACGT")])
        d1 = jsonl(
            [
                m8_record("D1", "synthetic-d1-0", VALID_A, training_seed=43, master=0, block="A"),
                m8_record("D1", "synthetic-d1-1", VALID_A, training_seed=43, master=1, block="A"),
                m8_record("D1", "synthetic-d1-2", VALID_C, training_seed=44, master=2, block="B"),
                m8_record("D1", "synthetic-d1-3", "", training_seed=44, master=3, block="B"),
            ]
        )
        self.blobs = {
            "b0-a": b0_a,
            "b0-b": b0_b,
            "b1": b1,
            "b2": b2,
            "d1": d1,
        }
        for name, blob in self.blobs.items():
            with open(os.path.join(self.sources, name), "wb") as handle:
                handle.write(blob)
        manifest = {
            "schema_version": "generator-eval-source-manifest-m9-r1",
            "conditions": {
                "B0": {
                    "logical_artifact_id": "synthetic-b0",
                    "attempt_count": 3,
                    "numeric_raw_concatenation_sha256": sha256(b0_a + b0_b),
                    "source_chunks": [
                        {"logical_artifact_id": "synthetic-b0-a", "seed": 1, "raw_sha256": sha256(b0_a)},
                        {"logical_artifact_id": "synthetic-b0-b", "seed": 2, "raw_sha256": sha256(b0_b)},
                    ],
                },
                "B1": {
                    "logical_artifact_id": "synthetic-b1",
                    "attempt_count": 5,
                    "combined_ledger_sha256": b1_hash or sha256(b1),
                },
                "B2": {
                    "logical_artifact_id": "synthetic-b2",
                    "attempt_count": 2,
                    "raw_jsonl_sha256": sha256(b2),
                },
                "D1": {
                    "logical_artifact_id": "synthetic-d1",
                    "attempt_count": 4,
                    "combined_ledger_sha256": sha256(d1),
                    "seed_allocation": [
                        {"d1_training_seed": 43, "attempts": 2, "technical_block": "A"},
                        {"d1_training_seed": 44, "attempts": 2, "technical_block": "B"},
                    ],
                },
            },
        }
        with open(self.manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
            handle.write("\n")
        self.locator = {
            "B0": {
                "synthetic-b0-a": os.path.join(self.sources, "b0-a"),
                "synthetic-b0-b": os.path.join(self.sources, "b0-b"),
            },
            "B1": {"synthetic-b1": os.path.join(self.sources, "b1")},
            "B2": {"synthetic-b2": os.path.join(self.sources, "b2")},
            "D1": {"synthetic-d1": os.path.join(self.sources, "d1")},
        }

    def _run(self, output=None):
        return runner.run_ledger(
            self.manifest_path,
            output or self.output,
            self.locator,
            production_totals=False,
            invocation={"argv": ["synthetic-fixture-run"], "production_totals": False},
            root=ROOT,
        )

    def _source_hashes(self):
        return {name: sha256(blob) for name, blob in self.blobs.items()}

    def test_miniature_order_duplicates_accounting_and_hashes(self):
        before = self._source_hashes()
        self._run()
        self.assertEqual(before, self._source_hashes())
        b0, b0_blob = read_jsonl(os.path.join(self.output, runner.OUTPUT_NAMES["B0"]))
        b1, b1_blob = read_jsonl(os.path.join(self.output, runner.OUTPUT_NAMES["B1"]))
        b2, b2_blob = read_jsonl(os.path.join(self.output, runner.OUTPUT_NAMES["B2"]))
        d1, d1_blob = read_jsonl(os.path.join(self.output, runner.OUTPUT_NAMES["D1"]))
        combined_path = os.path.join(self.output, runner.OUTPUT_NAMES["combined"])
        with open(combined_path, "rb") as handle:
            combined = handle.read()
        self.assertEqual(combined, b0_blob + b1_blob + b2_blob + d1_blob)
        self.assertEqual([len(b0), len(b1), len(b2), len(d1), combined.count(b"\n")], [3, 5, 2, 4, 14])
        self.assertEqual([row["record_id"] for row in b0], ["b0:seed:1:line:1", "b0:seed:1:line:2", "b0:seed:2:line:1"])
        self.assertEqual([row["record_id"] for row in b1], ["synthetic-b1-%d" % index for index in range(5)])
        self.assertEqual(b0[0]["parsed_sequence"], b0[1]["parsed_sequence"])
        self.assertEqual(b0[0]["valid_sequence_multiplicity"], 2)
        self.assertEqual(b0[1]["valid_sequence_multiplicity"], 2)
        self.assertTrue(b0[0]["is_exact_duplicate_within_condition"])
        self.assertTrue(b0[1]["is_exact_duplicate_within_condition"])
        self.assertEqual(b0[2]["valid_sequence_multiplicity"], 1)
        self.assertFalse(b0[2]["is_exact_duplicate_within_condition"])
        self.assertTrue(all(row["is_valid_canonical"] for row in b0))
        invalid = [row for row in b1 if row["is_valid_canonical"] is False]
        self.assertEqual(len(invalid), 2)
        for row in invalid:
            self.assertIsNone(row["valid_sequence_multiplicity"])
            self.assertIsNone(row["is_exact_duplicate_within_condition"])
            self.assertIsNone(row["parsed_sequence"])
        self.assertEqual(b1[0]["source_raw_file_relative_path"], RELATIVE)
        self.assertEqual(b1[0]["ledger_schema"], runner.PRODUCTION_LEDGER_SCHEMA)
        self.assertEqual(b1[0]["parser_version"], "m9-biological-parser-v1")
        self.assertEqual(b1[0]["adapter_version"], "m9-source-adapter-v2")
        self.assertNotIn(b"/home/", b0_blob + b1_blob + b2_blob + d1_blob)
        self.assertNotIn(b"rnagenesis-mres-runs", b0_blob + b1_blob + b2_blob + d1_blob)
        self.assertEqual(b2[1]["outcome"], "parsed_non_acgu")
        self.assertFalse(b2[1]["is_valid_canonical"])
        self.assertIsNone(b2[1]["valid_sequence_multiplicity"])
        self.assertEqual([row["d1_training_seed"] for row in d1], [43, 43, 44, 44])
        with open(os.path.join(self.output, runner.OUTPUT_NAMES["summary"]), "r", encoding="utf-8") as handle:
            summary_text = handle.read()
            summary = json.loads(summary_text)
        for sequence in (VALID_A, VALID_B, VALID_C, "ACGT"):
            self.assertNotIn(sequence, summary_text)
        self.assertEqual(summary["conditions"]["B0"]["total_attempts"], 3)
        self.assertEqual(summary["conditions"]["B1"]["total_attempts"], 5)
        self.assertEqual(summary["conditions"]["B2"]["total_attempts"], 2)
        self.assertEqual(summary["conditions"]["D1"]["total_attempts"], 4)
        self.assertEqual(summary["overall"]["total_attempts"], 14)
        self.assertEqual(summary["conditions"]["B1"]["valid_canonical_count"], 3)
        self.assertEqual(summary["conditions"]["B1"]["invalid_or_non_sequence_count"], 2)
        self.assertEqual(summary["conditions"]["B1"]["valid_singleton_row_count"], 1)
        self.assertEqual(summary["conditions"]["B1"]["valid_duplicate_member_row_count"], 2)
        self.assertEqual(summary["conditions"]["B1"]["distinct_valid_sequences"], 2)
        self.assertEqual(summary["conditions"]["B1"]["repeated_within_condition_sequence_groups"], 1)
        self.assertEqual(summary["conditions"]["B1"]["maximum_within_condition_multiplicity"], 2)
        self.assertEqual(summary["conditions"]["B1"]["parser_outcome_counts"]["empty_output"], 1)
        self.assertEqual(summary["conditions"]["B1"]["parser_outcome_counts"]["non_sequence_output"], 1)
        self.assertEqual(summary["conditions"]["B2"]["parser_outcome_counts"]["parsed_non_acgu"], 1)
        self.assertEqual(summary["conditions"]["D1"]["d1_training_seed_attempt_counts"], {"43": 2, "44": 2})
        self.assertFalse(summary["cross_condition_overlap_computed"])
        self.assertFalse(summary["overall"]["cross_condition_overlap_computed"])
        self.assertTrue(summary["overall"]["distinct_valid_sequences_are_within_condition_sums"])
        self.assertEqual(summary["overall"]["distinct_valid_sequences"], 7)
        self.assertEqual(summary["overall"]["maximum_within_condition_multiplicity"], 2)
        with open(os.path.join(self.output, runner.OUTPUT_NAMES["manifest"]), "r", encoding="utf-8") as handle:
            manifest_text = handle.read()
            produced = json.loads(manifest_text)
        for sequence in (VALID_A, VALID_B, VALID_C):
            self.assertNotIn(sequence, manifest_text)
        head = subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"], text=True).strip()
        self.assertEqual(produced["runner_git_commit"], head)
        self.assertEqual(produced["parser_contract"]["schema"], "generator-eval-parser-contract-m9-r2")
        self.assertEqual(produced["adapter_version"], "m9-source-adapter-v2")
        self.assertEqual(produced["ledger_schema"], runner.PRODUCTION_LEDGER_SCHEMA)
        contract_path = os.path.join(ROOT, produced["parser_contract"]["relative_path"])
        with open(contract_path, "rb") as handle:
            self.assertEqual(produced["parser_contract"]["sha256"], sha256(handle.read()))
        with open(self.manifest_path, "rb") as handle:
            self.assertEqual(produced["source_manifest"]["sha256"], sha256(handle.read()))
        self.assertEqual(produced["ordering"]["conditions"], ["B0", "B1", "B2", "D1"])
        self.assertFalse(produced["duplicate_policy"]["cross_condition_overlap_computed"])
        files = {
            item["filename"]: item
            for item in produced["outputs"]
        }
        for condition_name, blob in (("B0", b0_blob), ("B1", b1_blob), ("B2", b2_blob), ("D1", d1_blob)):
            record = files[runner.OUTPUT_NAMES[condition_name]]
            self.assertEqual(record["sha256"], sha256(blob))
            self.assertEqual(record["row_count"], blob.count(b"\n"))
        self.assertEqual(files[runner.OUTPUT_NAMES["combined"]]["sha256"], sha256(combined))
        summary_path = os.path.join(self.output, runner.OUTPUT_NAMES["summary"])
        with open(summary_path, "rb") as handle:
            summary_blob = handle.read()
        self.assertEqual(files[runner.OUTPUT_NAMES["summary"]]["sha256"], sha256(summary_blob))
        matched = [item for item in produced["inputs"] if item["logical_artifact_id"] == "synthetic-b1"]
        self.assertEqual(matched[0]["expected_sha256"], matched[0]["recomputed_sha256"])
        self.assertEqual(
            produced["b0_numeric_raw_concatenation_sha256"]["expected_sha256"],
            produced["b0_numeric_raw_concatenation_sha256"]["recomputed_sha256"],
        )

    def test_repeat_run_is_byte_identical_for_ledgers(self):
        self._run()
        second = os.path.join(self.root, "out-2")
        self._run(second)
        for key in ("B0", "B1", "B2", "D1", "combined", "summary"):
            with open(os.path.join(self.output, runner.OUTPUT_NAMES[key]), "rb") as handle:
                first_blob = handle.read()
            with open(os.path.join(second, runner.OUTPUT_NAMES[key]), "rb") as handle:
                second_blob = handle.read()
            self.assertEqual(first_blob, second_blob, key)

    def test_source_hash_mismatch_writes_nothing(self):
        self._write_fixture(b1_hash="11" * 32)
        before = self._source_hashes()
        with self.assertRaises(runner.ProductionLedgerError) as error:
            self._run()
        self.assertEqual(error.exception.code, "source_hash_mismatch")
        self.assertFalse(os.path.exists(self.output))
        self.assertEqual(before, self._source_hashes())
        self.assertEqual([name for name in os.listdir(self.root) if name.startswith(".m9-production-ledger.")], [])

    def test_missing_source_writes_nothing(self):
        os.remove(os.path.join(self.sources, "d1"))
        with self.assertRaises(runner.ProductionLedgerError) as error:
            self._run()
        self.assertEqual(error.exception.code, "source_missing")
        self.assertFalse(os.path.exists(self.output))

    def test_existing_output_is_refused_and_left_unchanged(self):
        self._run()
        with open(os.path.join(self.output, runner.OUTPUT_NAMES["B0"]), "rb") as handle:
            original = handle.read()
        with self.assertRaises(runner.ProductionLedgerError) as error:
            self._run()
        self.assertEqual(error.exception.code, "output_exists")
        with open(os.path.join(self.output, runner.OUTPUT_NAMES["B0"]), "rb") as handle:
            self.assertEqual(handle.read(), original)

    def test_validation_failure_removes_the_temporary_directory(self):
        original = runner.validate_published_directory

        def fail(directory, expected):
            raise runner.ProductionLedgerError("output_validation_failed", "injected")

        runner.validate_published_directory = fail
        try:
            with self.assertRaises(runner.ProductionLedgerError) as error:
                self._run()
        finally:
            runner.validate_published_directory = original
        self.assertEqual(error.exception.code, "output_validation_failed")
        self.assertFalse(os.path.exists(self.output))
        self.assertEqual([name for name in os.listdir(self.root) if name.startswith(".m9-production-ledger.")], [])

    def test_sealed_locator_checks_identity_without_opening_sources(self):
        with open(os.path.join(ROOT, "config/modelling/generator_eval_source_manifest.json"), "r", encoding="utf-8") as handle:
            document = json.load(handle)
        opened = []
        real_open = os.open

        def guarded(path, flags, mode=0o777):
            text = os.fspath(path)
            if "generator_eval_source_manifest" not in text and "generator_eval_parser_contract" not in text:
                if text.endswith(".jsonl") or text.endswith(".txt") or "rnagenesis-mres-runs" in text or "phase4_1" in text:
                    opened.append(text)
                    raise AssertionError("opened")
            return real_open(path, flags, mode)

        os.open = guarded
        try:
            locator = runner.sealed_source_locator(document, ROOT)
        finally:
            os.open = real_open
        self.assertEqual(opened, [])
        self.assertEqual(list(locator["B0"]), [item[0] for item in runner.B0_LOGICAL_FILES])
        self.assertEqual(set(locator["B1"]), {"b1:m8-combined-raw-attempt-ledger"})
        document["conditions"]["B2"]["logical_artifact_id"] = "synthetic-other"
        with self.assertRaises(runner.ProductionLedgerError) as error:
            runner.sealed_source_locator(document, ROOT)
        self.assertEqual(error.exception.code, "source_identity_invalid")

    def _guard_sealed_opens(self):
        opened = []
        real_open = os.open

        def guarded(path, flags, mode=0o777):
            text = os.fspath(path)
            if "generator_eval_source_manifest" not in text and "generator_eval_parser_contract" not in text:
                if text.endswith(".jsonl") or text.endswith(".txt") or "rnagenesis-mres-runs" in text or "phase4_1" in text:
                    opened.append(text)
                    raise AssertionError("opened")
            return real_open(path, flags, mode)

        return opened, real_open, guarded

    def test_altered_frozen_source_manifest_is_refused_before_sources_open(self):
        source = os.path.join(ROOT, "config/modelling/generator_eval_source_manifest.json")
        with open(source, "rb") as handle:
            original = handle.read()
        self.assertEqual(runner._sha256(original), runner.FROZEN_SOURCE_MANIFEST_SHA256)
        altered = bytearray(original)
        altered[-1] ^= 0x01
        altered_path = os.path.join(self.root, "altered-source-manifest.json")
        with open(altered_path, "wb") as handle:
            handle.write(altered)
        opened, real_open, guarded = self._guard_sealed_opens()
        os.open = guarded
        try:
            with self.assertRaises(runner.ProductionLedgerError) as error:
                runner.run_sealed_sources(
                    altered_path,
                    os.path.join(self.root, "sealed-out"),
                    {"argv": ["synthetic-frozen-manifest"], "production_totals": True},
                    root=ROOT,
                )
        finally:
            os.open = real_open
        self.assertEqual(error.exception.code, "frozen_source_manifest_mismatch")
        self.assertEqual(opened, [])
        self.assertFalse(os.path.exists(os.path.join(self.root, "sealed-out")))
        with open(source, "rb") as handle:
            self.assertEqual(handle.read(), original)

    def test_altered_parser_contract_is_refused_before_sources_open(self):
        contract = os.path.join(ROOT, runner.CONTRACT_RELATIVE_PATH)
        with open(contract, "rb") as handle:
            original = handle.read()
        self.assertEqual(runner._sha256(original), runner.FROZEN_PARSER_CONTRACT_SHA256)
        altered = bytearray(original)
        altered[0] ^= 0x01
        relative_dir = os.path.join(self.root, "config", "modelling")
        os.makedirs(relative_dir)
        with open(os.path.join(relative_dir, "generator_eval_parser_contract.json"), "wb") as handle:
            handle.write(altered)
        opened, real_open, guarded = self._guard_sealed_opens()
        os.open = guarded
        try:
            with self.assertRaises(runner.ProductionLedgerError) as error:
                runner.run_sealed_sources(
                    os.path.join(ROOT, "config/modelling/generator_eval_source_manifest.json"),
                    os.path.join(self.root, "sealed-out"),
                    {"argv": ["synthetic-frozen-contract"], "production_totals": True},
                    root=self.root,
                )
        finally:
            os.open = real_open
        self.assertEqual(error.exception.code, "frozen_parser_contract_mismatch")
        self.assertEqual(opened, [])
        self.assertFalse(os.path.exists(os.path.join(self.root, "sealed-out")))
        with open(contract, "rb") as handle:
            self.assertEqual(handle.read(), original)

    def test_existing_empty_output_directory_is_refused_and_unchanged(self):
        os.makedirs(self.output)
        with self.assertRaises(runner.ProductionLedgerError) as error:
            runner.publish_output_directory(self.output, [(runner.OUTPUT_NAMES["summary"], b"{}\n")])
        self.assertEqual(error.exception.code, "output_exists")
        self.assertEqual(os.listdir(self.output), [])
        self.assertTrue(os.path.isdir(self.output))
        parent_names = os.listdir(self.root)
        self.assertEqual([name for name in parent_names if name.startswith(".m9-production-ledger.")], [])


if __name__ == "__main__":
    unittest.main()

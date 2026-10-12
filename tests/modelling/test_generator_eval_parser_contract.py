"""Synthetic tests for the frozen four-condition parser contract.

Sequences and artifact hashes in this module are invented. No production
source, protected role, model, or evaluation file is opened. Passing these
tests is not production validation.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import sys
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)

import generator_eval_derived_ledger as ledger
import generator_eval_parser as biological
import generator_eval_source_adapters as adapters

FIXTURE = os.path.join(
    ROOT, "tests", "modelling", "fixtures", "generator_eval_parser", "synthetic_cases.json"
)
CONTRACT = os.path.join(ROOT, "config", "modelling", "generator_eval_parser_contract.json")
MANIFEST = os.path.join(ROOT, "config", "modelling", "generator_eval_source_manifest.json")
CONTRACT_DOC = os.path.join(ROOT, "docs", "fine_tuning", "m9_parser_contract.md")
DISTINCTIVE_VALID = "ACGUACGUACGU"
DISTINCTIVE_OTHER = "GGGGCCCCUUUUAAAA"


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def reference_strip(raw):
    """Independent leading-then-trailing marker removal. Not the module function."""
    prefix_marks = []
    index = 0
    while index < len(raw) and raw[index] in ("1", "2"):
        prefix_marks.append(raw[index])
        index += 1
    suffix_marks = []
    end = len(raw) - 1
    while end >= index and raw[end] in ("1", "2"):
        suffix_marks.append(raw[end])
        end -= 1
    prefix = "".join(prefix_marks)
    suffix = "".join(reversed(suffix_marks))
    body = raw[index:end + 1]
    return prefix, body, suffix


def reference_classify(value):
    if not isinstance(value, str):
        return "non_sequence_output", None, None, None
    prefix, body, suffix = reference_strip(value)
    if body == "":
        return "empty_output", None, prefix, suffix
    if body != "" and all(character in "ACGU" for character in body):
        return "valid_canonical_sequence", body, prefix, suffix
    return "parsed_non_acgu", body, prefix, suffix


def reference_split(text):
    """Independent LF/CRLF splitter. A final newline does not add a record."""
    if text == "":
        return []
    records = []
    current = []
    for character in text:
        if character == "\n":
            record = "".join(current)
            if record.endswith("\r"):
                record = record[:-1]
            records.append(record)
            current = []
            continue
        current.append(character)
    if not text.endswith("\n"):
        records.append("".join(current))
    return records


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def m8_record(condition, record_id, text, training_seed=None, master=0):
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
        "invocation_index": master,
        "line_index": 0,
        "master_attempt_index": master,
        "max_seq_len": 21,
        "raw_decoded_text": text,
        "record_id": record_id,
        "requested_biological_length": 20,
        "run_id": "synthetic-run",
        "schema_version": "m8-raw-attempt-1",
        "source_raw_file_relative_path": "synthetic-raw-token",
        "source_raw_file_sha256": "ab" * 32,
        "technical_block": "A" if condition == "B1" or training_seed == 43 else "B",
        "within_batch_position": 0,
    }


def b2_record(index, sequence, seed=99, valid_acgu=True, sampled_length=4):
    encoded = sequence.encode("utf-8") if isinstance(sequence, str) else b"invented"
    return {
        "attempt_index": index,
        "seed": seed,
        "sampled_length": sampled_length,
        "sequence": sequence,
        "valid_acgu": valid_acgu,
        "sequence_sha256": sha256(encoded),
    }


def jsonl(records):
    chunks = []
    for record in records:
        chunks.append(json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        chunks.append(b"\n")
    return b"".join(chunks)


def b0_metadata(raw, seed=7):
    return {
        "chunk_id": "synthetic-chunk-%d" % seed,
        "nominal_max_seq_len": 37,
        "seed": seed,
        "source_artifact_id": "synthetic-b0-artifact",
        "source_artifact_sha256": sha256(raw),
    }


class ReferenceEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_json(FIXTURE)

    def test_string_cases_match_independent_reference_and_fixture(self):
        self.assertGreaterEqual(len(self.fixture["string_cases"]), 14)
        for case in self.fixture["string_cases"]:
            prefix, body, suffix = biological.strip_boundary_markers(case["raw"])
            reference = reference_strip(case["raw"])
            self.assertEqual((prefix, body, suffix), reference, case["id"])
            self.assertEqual((prefix, body, suffix), (case["prefix"], case["body"], case["suffix"]), case["id"])
            self.assertEqual(prefix + body + suffix, case["raw"], case["id"])
            parsed = biological.parse_biological_text(case["raw"])
            outcome, sequence, ref_prefix, ref_suffix = reference_classify(case["raw"])
            self.assertEqual(parsed["outcome"], outcome, case["id"])
            self.assertEqual(parsed["outcome"], case["outcome"], case["id"])
            self.assertEqual(parsed["parsed_sequence"], sequence, case["id"])
            self.assertEqual((parsed["removed_prefix"], parsed["removed_suffix"]), (ref_prefix, ref_suffix), case["id"])
            if case["outcome"] == "valid_canonical_sequence":
                self.assertIsNone(parsed["failure_reason"], case["id"])
                self.assertEqual(parsed["parsed_length"], len(case["body"]), case["id"])
            elif case["outcome"] == "empty_output":
                self.assertIsNone(parsed["parsed_sequence"], case["id"])
                self.assertEqual(parsed["failure_reason"], "empty_output", case["id"])
                self.assertEqual(parsed["parsed_length"], 0, case["id"])
            else:
                self.assertEqual(parsed["parsed_sequence"], case["body"], case["id"])
                self.assertEqual(parsed["failure_reason"], "parsed_non_acgu", case["id"])

    def test_marker_only_strings_are_not_preclassified_as_non_acgu(self):
        for raw in ("1", "2", "12", "21", "1122", "222"):
            parsed = biological.parse_biological_text(raw)
            self.assertEqual(parsed["outcome"], "empty_output", raw)
            self.assertEqual(parsed["removed_prefix"], raw, raw)
            self.assertEqual(parsed["removed_suffix"], "", raw)
            self.assertNotEqual(reference_classify(raw)[0], "parsed_non_acgu", raw)

    def test_split_matches_independent_reference(self):
        for case in self.fixture["split_cases"]:
            module_records = biological.split_raw_records(case["text"])
            self.assertEqual(module_records, reference_split(case["text"]), case["id"])
            self.assertEqual(module_records, case["records"], case["id"])
            as_bytes = case["text"].encode("utf-8")
            decoded = [blob.decode("utf-8") for blob in biological.split_raw_record_bytes(as_bytes)]
            self.assertEqual(decoded, module_records, case["id"])

    def test_generated_grid_matches_reference_strip(self):
        fragments = ("", "1", "2", "A", "C", "G", "U", "T", "a", " ", "11", "22")
        for left in fragments:
            for middle in fragments:
                for right in fragments:
                    raw = left + middle + right
                    self.assertEqual(biological.strip_boundary_markers(raw), reference_strip(raw))

    def test_non_string_payloads_match_reference(self):
        for case in self.fixture["non_string_cases"]:
            parsed = biological.parse_biological_text(case["payload"])
            outcome, sequence, _prefix, _suffix = reference_classify(case["payload"])
            self.assertEqual(parsed["outcome"], case["outcome"], case["id"])
            self.assertEqual(parsed["outcome"], outcome, case["id"])
            self.assertIsNone(parsed["parsed_sequence"], case["id"])
            self.assertIsNone(sequence, case["id"])
            self.assertEqual(parsed["failure_reason"], "non_sequence_output", case["id"])

    def test_invalid_utf8_payload_is_unparseable_before_source_adaptation(self):
        parsed = biological.parse_biological_text(b"\xff")
        self.assertEqual(parsed["outcome"], "unparseable_output")
        self.assertIsNone(parsed["parsed_sequence"])


class AdapterTests(unittest.TestCase):
    def test_b0_stable_ids_order_and_unavailable_requested_length(self):
        raw = b"11ACGU\r\n\nACGU2\n"
        rows = adapters.adapt_b0(raw, b0_metadata(raw, seed=99))
        self.assertEqual([row["record_id"] for row in rows], [
            "b0:seed:99:line:1",
            "b0:seed:99:line:2",
            "b0:seed:99:line:3",
        ])
        self.assertEqual([row["parsed_sequence"] for row in rows], ["ACGU", None, "ACGU"])
        self.assertEqual(rows[1]["outcome"], "empty_output")
        for row in rows:
            self.assertEqual(row["b0_seed"], 99)
            self.assertEqual(row["b0_chunk_id"], "synthetic-chunk-99")
            self.assertEqual(row["nominal_max_seq_len"], 37)
            self.assertIsNone(row["requested_biological_length"])
            self.assertFalse(row["requested_biological_length_available"])
            self.assertIsNone(row["max_seq_len"])
            self.assertEqual(row["source_artifact_sha256"], sha256(raw))
            self.assertIsNone(row["d1_training_seed"])
        metadata = b0_metadata(raw, seed=99)
        metadata["requested_biological_length"] = 36
        with self.assertRaises(biological.ParserContractError) as refused:
            adapters.adapt_b0(raw, metadata)
        self.assertEqual(refused.exception.code, "b0_requested_length_unavailable")

    def test_b0_empty_file_and_only_newline(self):
        empty = b""
        self.assertEqual(adapters.adapt_b0(empty, b0_metadata(empty, seed=3)), [])
        only_newline = b"\n"
        rows = adapters.adapt_b0(only_newline, b0_metadata(only_newline, seed=3))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_id"], "b0:seed:3:line:1")
        self.assertEqual(rows[0]["outcome"], "empty_output")

    def test_b0_invalid_utf8_keeps_the_attempt(self):
        raw = b"ACGU\n\xff\n"
        rows = adapters.adapt_b0(raw, b0_metadata(raw, seed=8))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["outcome"], "valid_canonical_sequence")
        self.assertEqual(rows[1]["outcome"], "unparseable_output")
        self.assertEqual(rows[1]["record_id"], "b0:seed:8:line:2")
        self.assertIsNone(rows[1]["parsed_sequence"])

    def test_b1_preserves_record_id_and_null_training_seed(self):
        records = [
            m8_record("B1", "synthetic-b1-00002", "11" + DISTINCTIVE_VALID, master=2),
            m8_record("B1", "synthetic-b1-00000", "", master=0),
        ]
        raw = jsonl(records)
        rows = adapters.adapt_b1(raw, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual([row["record_id"] for row in rows], ["synthetic-b1-00002", "synthetic-b1-00000"])
        self.assertEqual(rows[0]["parsed_sequence"], DISTINCTIVE_VALID)
        self.assertEqual(rows[0]["master_attempt_index"], 2)
        self.assertEqual(rows[0]["generation_seed"], 800002)
        self.assertEqual(rows[0]["invocation_index"], 2)
        self.assertEqual(rows[0]["requested_biological_length"], 20)
        self.assertEqual(rows[0]["max_seq_len"], 21)
        self.assertEqual(rows[0]["technical_block"], "A")
        self.assertEqual(rows[0]["checkpoint_identity"], "synthetic-checkpoint")
        self.assertEqual(rows[0]["source_raw_file_sha256"], "ab" * 32)
        self.assertIsNone(rows[0]["d1_training_seed"])
        self.assertIsNone(rows[1]["parsed_sequence"])
        self.assertEqual(rows[1]["outcome"], "empty_output")
        numbered = m8_record("B1", "synthetic-b1-seeded", "ACGU", master=1)
        numbered["d1_training_seed"] = 43
        bad = jsonl([numbered])
        with self.assertRaises(biological.ParserContractError) as error:
            adapters.adapt_b1(bad, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=sha256(bad))
        self.assertEqual(error.exception.code, "d1_training_seed_invalid")

    def test_d1_preserves_ids_and_observed_seeds_without_weighting(self):
        records = [
            m8_record("D1", "synthetic-d1-a", DISTINCTIVE_VALID, training_seed=43, master=4),
            m8_record("D1", "synthetic-d1-a2", DISTINCTIVE_VALID, training_seed=43, master=5),
            m8_record("D1", "synthetic-d1-b", DISTINCTIVE_OTHER, training_seed=44, master=1),
        ]
        raw = jsonl(records)
        rows = adapters.adapt_d1(raw, source_artifact_id="synthetic-d1-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual([row["record_id"] for row in rows], ["synthetic-d1-a", "synthetic-d1-a2", "synthetic-d1-b"])
        self.assertEqual([row["d1_training_seed"] for row in rows], [43, 43, 44])
        self.assertTrue(all(row["equal_seed_weighting_applied"] is False for row in rows))
        accounting = ledger.sequence_free_accounting(rows)
        self.assertEqual(accounting["d1_observed_counts_by_training_seed"], {"43": 2, "44": 1})
        self.assertFalse(accounting["equal_seed_weighting_applied"])
        self.assertEqual(accounting["weighting"], "observed_counts_only")
        self.assertEqual(accounting["raw_source_attempts"], 3)
        self.assertEqual(accounting["valid_canonical_sequences"], 3)
        missing_seed = m8_record("D1", "synthetic-d1-missing", "ACGU", training_seed=43, master=0)
        missing_seed["d1_training_seed"] = None
        bad = jsonl([missing_seed])
        with self.assertRaises(biological.ParserContractError) as error:
            adapters.adapt_d1(bad, source_artifact_id="synthetic-d1-artifact", source_artifact_sha256=sha256(bad))
        self.assertEqual(error.exception.code, "d1_training_seed_invalid")

    def test_b2_ids_empirical_null_seed_and_recomputed_validity(self):
        records = [
            b2_record(2, DISTINCTIVE_VALID, seed=99, valid_acgu=False),
            b2_record(0, "ACGT", seed=7, valid_acgu=True, sampled_length=40),
            b2_record(1, DISTINCTIVE_VALID, seed=99, valid_acgu=True),
        ]
        raw = jsonl(records)
        rows = adapters.adapt_b2(raw, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual([row["record_id"] for row in rows], ["b2:attempt:00002", "b2:attempt:00000", "b2:attempt:00001"])
        self.assertEqual(rows[0]["outcome"], "valid_canonical_sequence")
        self.assertFalse(rows[0]["source_valid_acgu_claim"])
        self.assertEqual(rows[0]["empirical_null_seed"], 99)
        self.assertIsNone(rows[0]["d1_training_seed"])
        self.assertIsNone(rows[0]["generation_seed"])
        self.assertEqual(rows[1]["outcome"], "parsed_non_acgu")
        self.assertEqual(rows[1]["parsed_sequence"], "ACGT")
        self.assertTrue(rows[1]["source_valid_acgu_claim"])
        self.assertEqual(rows[1]["sampled_length"], 40)
        self.assertEqual(rows[1]["parsed_length"], 4)
        self.assertEqual(rows[1]["empirical_null_seed"], 7)

    def test_non_string_m8_field_preserves_id_without_a_sequence(self):
        record = m8_record("B1", "synthetic-b1-number", "ACGU", master=3)
        record["raw_decoded_text"] = 1
        raw = jsonl([record])
        rows = adapters.adapt_b1(raw, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_id"], "synthetic-b1-number")
        self.assertEqual(rows[0]["outcome"], "non_sequence_output")
        self.assertIsNone(rows[0]["parsed_sequence"])
        self.assertEqual(rows[0]["master_attempt_index"], 3)

    def test_source_hash_on_rows_is_the_recomputed_digest(self):
        raw = jsonl([m8_record("B1", "synthetic-b1-hash", "ACGU", master=0)])
        expected = sha256(raw)
        rows = adapters.adapt_b1(
            raw,
            source_artifact_id="synthetic-b1-artifact",
            source_artifact_sha256=expected,
        )
        self.assertEqual(rows[0]["source_artifact_sha256"], expected)
        self.assertIsNot(rows[0]["source_artifact_sha256"], expected)

    def test_low_validity_and_duplicate_sequences_are_retained(self):
        records = [
            b2_record(0, DISTINCTIVE_VALID, seed=99),
            b2_record(1, "", seed=99),
            b2_record(2, "ACGT", seed=99, valid_acgu=True),
            b2_record(3, DISTINCTIVE_VALID, seed=99),
            b2_record(4, "AC GU", seed=99, valid_acgu=True),
        ]
        records[1]["sequence"] = ""
        raw = jsonl(records)
        rows = adapters.adapt_b2(raw, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual(len(rows), 5)
        accounting = ledger.sequence_free_accounting(rows)
        self.assertEqual(accounting["raw_source_attempts"], 5)
        self.assertEqual(accounting["valid_canonical_sequences"], 2)
        self.assertEqual(accounting["unique_valid_sequences"], 1)
        self.assertEqual(accounting["duplicate_excess"], 1)
        self.assertLess(accounting["valid_canonical_sequences"], accounting["raw_source_attempts"])
        self.assertEqual(rows[0]["parsed_sequence"], rows[3]["parsed_sequence"])
        self.assertNotEqual(rows[0]["record_id"], rows[3]["record_id"])


class SourceIntegrityTests(unittest.TestCase):
    def _b1(self, text="ACGU", record_id="synthetic-b1-integrity"):
        raw = jsonl([m8_record("B1", record_id, text, master=0)])
        return raw, sha256(raw)

    def _assert_recomputed(self, rows, expected):
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["source_artifact_sha256"], expected)
            self.assertIsNot(row["source_artifact_sha256"], expected)
            self.assertNotEqual(row["source_artifact_sha256"], "ab" * 32)

    def test_matching_hash_is_recomputed_for_every_bytes_adapter(self):
        b0 = bytearray(b"ACGU\n")
        b0_expected = sha256(bytes(b0))
        metadata = b0_metadata(bytes(b0), seed=7)
        metadata["source_artifact_sha256"] = b0_expected
        b0_rows = adapters.adapt_b0(b0, metadata)
        self._assert_recomputed(b0_rows, b0_expected)

        b1, b1_expected = self._b1()
        self._assert_recomputed(
            adapters.adapt_b1(b1, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=b1_expected),
            b1_expected,
        )
        d1 = jsonl([m8_record("D1", "synthetic-d1-integrity", "ACGU", training_seed=43, master=0)])
        d1_expected = sha256(d1)
        self._assert_recomputed(
            adapters.adapt_d1(d1, source_artifact_id="synthetic-d1-artifact", source_artifact_sha256=d1_expected),
            d1_expected,
        )
        b2 = jsonl([b2_record(0, "ACGU", seed=99)])
        b2_expected = sha256(b2)
        self._assert_recomputed(
            adapters.adapt_b2(b2, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=b2_expected),
            b2_expected,
        )

    def test_mismatched_and_malformed_hashes_fail_closed_before_parsing(self):
        malformed_json = b"{not-json}\n"
        arbitrary = load_json(FIXTURE)["invented_sha256"]["beta"]
        self.assertNotEqual(arbitrary, sha256(malformed_json))
        cases = (
            ("B1", "synthetic-b1-artifact", lambda digest: adapters.adapt_b1(
                malformed_json, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=digest
            )),
            ("D1", "synthetic-d1-artifact", lambda digest: adapters.adapt_d1(
                malformed_json, source_artifact_id="synthetic-d1-artifact", source_artifact_sha256=digest
            )),
            ("B2", "synthetic-b2-artifact", lambda digest: adapters.adapt_b2(
                malformed_json, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=digest
            )),
        )
        for label, _artifact, call in cases:
            with self.assertRaises(biological.ParserContractError) as mismatch:
                call(arbitrary)
            self.assertEqual(mismatch.exception.code, "source_artifact_sha256_mismatch", label)
            with self.assertRaises(biological.ParserContractError) as container:
                call(sha256(malformed_json))
            self.assertEqual(container.exception.code, "source_container_invalid", label)
            for bad in ("AB" * 32, "ab" * 31, "gg" * 32, "", None):
                with self.assertRaises(biological.ParserContractError) as invalid:
                    call(bad)
                self.assertEqual(invalid.exception.code, "source_artifact_sha256_invalid", (label, bad))

        raw = b"ACGU\n\xff\n"
        metadata = b0_metadata(raw, seed=8)
        metadata["source_artifact_sha256"] = arbitrary
        with self.assertRaises(biological.ParserContractError) as b0_mismatch:
            adapters.adapt_b0(raw, metadata)
        self.assertEqual(b0_mismatch.exception.code, "source_artifact_sha256_mismatch")
        metadata["source_artifact_sha256"] = "AB" * 32
        with self.assertRaises(biological.ParserContractError) as b0_invalid:
            adapters.adapt_b0(raw, metadata)
        self.assertEqual(b0_invalid.exception.code, "source_artifact_sha256_invalid")

    def test_decoded_objects_are_refused_and_do_not_copy_a_caller_hash(self):
        arbitrary = load_json(FIXTURE)["invented_sha256"]["alpha"]
        decoded = [m8_record("B1", "synthetic-b1-list", "ACGU", master=0)]
        for call in (
            lambda: adapters.adapt_b0(decoded, b0_metadata(b"ACGU\n", seed=7)),
            lambda: adapters.adapt_b1(decoded, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=arbitrary),
            lambda: adapters.adapt_d1(decoded, source_artifact_id="synthetic-d1-artifact", source_artifact_sha256=arbitrary),
            lambda: adapters.adapt_b2(decoded, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=arbitrary),
        ):
            with self.assertRaises(biological.ParserContractError) as refused:
                call()
            self.assertEqual(refused.exception.code, "decoded_source_refused")
            self.assertNotIn(arbitrary, str(refused.exception))


class ContainerFailureTests(unittest.TestCase):
    def test_b0_undecodable_record_keeps_seed_and_line_identity(self):
        raw = b"ACGU\n\xff\n"
        rows = adapters.adapt_b0(raw, b0_metadata(raw, seed=8))
        self.assertEqual([row["record_id"] for row in rows], ["b0:seed:8:line:1", "b0:seed:8:line:2"])
        self.assertEqual(rows[0]["outcome"], "valid_canonical_sequence")
        self.assertEqual(rows[1]["outcome"], "unparseable_output")
        self.assertIsNone(rows[1]["parsed_sequence"])

    def test_same_undecodable_bytes_fail_jsonl_sources(self):
        raw = b"\xff\n"
        digest = sha256(raw)
        for call in (
            lambda: adapters.adapt_b1(raw, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=digest),
            lambda: adapters.adapt_d1(raw, source_artifact_id="synthetic-d1-artifact", source_artifact_sha256=digest),
            lambda: adapters.adapt_b2(raw, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=digest),
        ):
            with self.assertRaises(biological.ParserContractError) as error:
                call()
            self.assertEqual(error.exception.code, "source_container_invalid")

    def test_malformed_json_and_partial_corruption_fail_the_source(self):
        valid = m8_record("B1", "synthetic-b1-kept", "ACGU", master=0)
        raw = jsonl([valid]) + b"{not-json}\n"
        with self.assertRaises(biological.ParserContractError) as error:
            adapters.adapt_b1(raw, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual(error.exception.code, "source_container_invalid")
        non_object = json.dumps("ACGU").encode("utf-8") + b"\n"
        with self.assertRaises(biological.ParserContractError) as structural:
            adapters.adapt_b2(
                non_object,
                source_artifact_id="synthetic-b2-artifact",
                source_artifact_sha256=sha256(non_object),
            )
        self.assertEqual(structural.exception.code, "source_container_invalid")

    def test_missing_b1_identity_and_incomplete_provenance_fail_closed(self):
        missing = m8_record("B1", "synthetic-b1-missing", "ACGU", master=4)
        del missing["record_id"]
        raw = jsonl([missing])
        with self.assertRaises(biological.ParserContractError) as identity:
            adapters.adapt_b1(raw, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual(identity.exception.code, "source_attempt_identity_unrecoverable")
        incomplete = m8_record("B1", "synthetic-b1-partial", "ACGU", master=4)
        del incomplete["batch_number"]
        raw = jsonl([incomplete])
        with self.assertRaises(biological.ParserContractError) as provenance:
            adapters.adapt_b1(raw, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual(provenance.exception.code, "source_provenance_invalid")

    def test_duplicate_source_identity_fails_b1_d1_and_b2(self):
        b1 = jsonl([
            m8_record("B1", "synthetic-b1-same", "ACGU", master=0),
            m8_record("B1", "synthetic-b1-same", "GGGG", master=1),
        ])
        with self.assertRaises(biological.ParserContractError) as b1_error:
            adapters.adapt_b1(b1, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=sha256(b1))
        self.assertEqual(b1_error.exception.code, "source_attempt_identity_duplicated")
        d1 = jsonl([
            m8_record("D1", "synthetic-d1-same", "ACGU", training_seed=43, master=0),
            m8_record("D1", "synthetic-d1-same", "ACGU", training_seed=44, master=1),
        ])
        with self.assertRaises(biological.ParserContractError) as d1_error:
            adapters.adapt_d1(d1, source_artifact_id="synthetic-d1-artifact", source_artifact_sha256=sha256(d1))
        self.assertEqual(d1_error.exception.code, "source_attempt_identity_duplicated")
        b2 = jsonl([
            b2_record(3, "ACGU", seed=99),
            b2_record(3, "GGGG", seed=7),
        ])
        with self.assertRaises(biological.ParserContractError) as b2_error:
            adapters.adapt_b2(b2, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=sha256(b2))
        self.assertEqual(b2_error.exception.code, "source_attempt_identity_duplicated")

    def test_missing_b2_attempt_index_is_not_invented(self):
        record = b2_record(4, "ACGU", seed=99)
        del record["attempt_index"]
        raw = jsonl([record])
        with self.assertRaises(biological.ParserContractError) as error:
            adapters.adapt_b2(raw, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual(error.exception.code, "source_attempt_identity_unrecoverable")
        self.assertNotIn("b2:attempt:", str(error.exception))

    def test_schema_valid_null_payload_is_an_accounted_outcome(self):
        b1 = m8_record("B1", "synthetic-b1-null", "ACGU", master=6)
        b1["raw_decoded_text"] = None
        raw = jsonl([b1])
        rows = adapters.adapt_b1(raw, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_id"], "synthetic-b1-null")
        self.assertEqual(rows[0]["outcome"], "non_sequence_output")
        self.assertEqual(rows[0]["master_attempt_index"], 6)
        self.assertIsNone(rows[0]["parsed_sequence"])
        self.assertIsNone(rows[0]["d1_training_seed"])
        d1 = m8_record("D1", "synthetic-d1-null", "ACGU", training_seed=44, master=2)
        d1["raw_decoded_text"] = None
        raw = jsonl([d1])
        rows = adapters.adapt_d1(raw, source_artifact_id="synthetic-d1-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual(rows[0]["record_id"], "synthetic-d1-null")
        self.assertEqual(rows[0]["outcome"], "non_sequence_output")
        self.assertEqual(rows[0]["d1_training_seed"], 44)
        b2 = b2_record(8, "ACGU", seed=99)
        b2["sequence"] = None
        raw = jsonl([b2])
        rows = adapters.adapt_b2(raw, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=sha256(raw))
        self.assertEqual(rows[0]["record_id"], "b2:attempt:00008")
        self.assertEqual(rows[0]["attempt_index"], 8)
        self.assertEqual(rows[0]["outcome"], "non_sequence_output")
        self.assertEqual(rows[0]["empirical_null_seed"], 99)
        self.assertIsNone(rows[0]["parsed_sequence"])


class LedgerTests(unittest.TestCase):
    def _rows(self):
        raw = jsonl([
            b2_record(1, DISTINCTIVE_VALID, seed=99),
            b2_record(0, DISTINCTIVE_OTHER, seed=99),
        ])
        return adapters.adapt_b2(raw, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=sha256(raw)), sha256(raw)

    def test_deterministic_jsonl_and_replay_hash(self):
        rows, _source_hash = self._rows()
        first = ledger.construct_derived_ledger(rows)
        second = ledger.construct_derived_ledger(rows)
        self.assertEqual(first["canonical_jsonl"], second["canonical_jsonl"])
        self.assertTrue(first["canonical_jsonl"].endswith(b"\n"))
        self.assertEqual(first["canonical_jsonl"].count(b"\n"), 2)
        self.assertEqual(first["derived_ledger_sha256"], sha256(first["canonical_jsonl"]))
        self.assertFalse(first["expected_sha256_was_required"])
        self.assertFalse(first["synthetic_execution_is_production_validation"])
        self.assertFalse(first["production_derived_ledger"])
        replay = ledger.construct_derived_ledger(rows, expected_sha256=first["derived_ledger_sha256"])
        self.assertEqual(replay["derived_ledger_sha256"], first["derived_ledger_sha256"])
        with self.assertRaises(biological.ParserContractError) as mismatch:
            ledger.construct_derived_ledger(rows, expected_sha256="11" * 32)
        self.assertEqual(mismatch.exception.code, "derived_ledger_sha256_mismatch")

    def test_missing_duplicate_and_extra_ids_fail_closed(self):
        rows, source_hash = self._rows()
        source_ids = [row["record_id"] for row in rows]
        self.assertTrue(ledger.assert_attempt_identity(source_ids, rows, source_hash))
        with self.assertRaises(biological.ParserContractError) as missing:
            ledger.assert_attempt_identity(source_ids, rows[:-1], source_hash)
        self.assertEqual(missing.exception.code, "attempt_id_missing")
        duplicated = rows + [copy.deepcopy(rows[0])]
        with self.assertRaises(biological.ParserContractError) as duplicate:
            ledger.assert_attempt_identity(source_ids, duplicated, source_hash)
        self.assertEqual(duplicate.exception.code, "attempt_id_duplicated")
        extra = copy.deepcopy(rows)
        extra.append(copy.deepcopy(rows[0]))
        extra[-1]["record_id"] = "b2:attempt:00009"
        with self.assertRaises(biological.ParserContractError) as extra_error:
            ledger.assert_attempt_identity(source_ids, extra, source_hash)
        self.assertEqual(extra_error.exception.code, "attempt_id_extra")
        reordered = [rows[1], rows[0]]
        with self.assertRaises(biological.ParserContractError) as order:
            ledger.assert_attempt_identity(source_ids, reordered, source_hash)
        self.assertEqual(order.exception.code, "attempt_id_reordered")

    def test_accounting_has_no_sequence_text(self):
        rows, _source_hash = self._rows()
        accounting = ledger.sequence_free_accounting(rows)
        encoded = json.dumps(accounting, sort_keys=True)
        self.assertNotIn(DISTINCTIVE_VALID, encoded)
        self.assertNotIn(DISTINCTIVE_OTHER, encoded)
        self.assertFalse(accounting["sequence_strings_emitted"])
        self.assertEqual(accounting["successfully_parsed_outputs"], 2)
        self.assertEqual(accounting["duplicate_excess"], 0)
        self.assertIsNone(accounting["d1_observed_counts_by_training_seed"])
        self.assertEqual(accounting["failure_reason_counts"]["empty_output"], 0)


class FirewallTests(unittest.TestCase):
    def test_path_role_filename_unlock_and_mutation_are_refused(self):
        import pathlib

        raw = b"ACGU\n"
        with self.assertRaises(biological.ParserContractError) as path_object:
            adapters.adapt_b0(pathlib.Path("/tmp/synthetic-not-opened"), b0_metadata(raw))
        self.assertEqual(path_object.exception.code, "filesystem_path_refused")
        with self.assertRaises(biological.ParserContractError) as run_root:
            adapters.adapt_b0("/home/laura/rnagenesis-mres-runs/m8_b1_combined", b0_metadata(raw))
        self.assertEqual(run_root.exception.code, "production_run_root_refused")
        with self.assertRaises(biological.ParserContractError) as role:
            adapters.adapt_b1(raw, source_artifact_id="synthetic-b1-artifact", source_artifact_sha256=sha256(raw), role="EVAL")
        self.assertEqual(role.exception.code, "role_refused")
        for role_name in ("TRAIN", "VALIDATION", "REF"):
            with self.assertRaises(biological.ParserContractError) as refused_role:
                adapters.adapt_d1(
                    raw,
                    source_artifact_id="synthetic-d1-artifact",
                    source_artifact_sha256=sha256(raw),
                    data_role=role_name,
                )
            self.assertEqual(refused_role.exception.code, "role_refused")
        with self.assertRaises(biological.ParserContractError) as filename:
            adapters.adapt_b2(b"", source_artifact_id="corpus_final.txt", source_artifact_sha256="aa" * 32)
        self.assertEqual(filename.exception.code, "filename_refused")
        for basename in ("ft_train.csv", "ft_validation.csv", "ref.csv", "eval.csv"):
            with self.assertRaises(biological.ParserContractError) as named:
                ledger.construct_derived_ledger([], filename=basename)
            self.assertEqual(named.exception.code, "filename_refused")
        with self.assertRaises(biological.ParserContractError) as unlock:
            ledger.construct_derived_ledger([], eval_unlock=True)
        self.assertEqual(unlock.exception.code, "eval_unlock_refused")
        records = [b2_record(index, "ACGU", seed=99) for index in range(2)]
        payload = jsonl(records)
        rows = adapters.adapt_b2(payload, source_artifact_id="synthetic-b2-artifact", source_artifact_sha256=sha256(payload))
        for operation in ("replenish", "filter", "deduplicate", "drop"):
            with self.assertRaises(biological.ParserContractError) as mutation:
                ledger.construct_derived_ledger(rows, operation=operation)
            self.assertEqual(mutation.exception.code, "mutation_refused")
            self.assertEqual(len(rows), 2)

    def test_sequence_text_is_not_treated_as_a_path_or_role_request(self):
        parsed = biological.parse_biological_text("AC/GU")
        self.assertEqual(parsed["outcome"], "parsed_non_acgu")
        self.assertEqual(parsed["parsed_sequence"], "AC/GU")
        role_spelling = biological.parse_biological_text("EVAL")
        self.assertEqual(role_spelling["outcome"], "parsed_non_acgu")
        self.assertEqual(role_spelling["parsed_sequence"], "EVAL")

    def test_implementation_modules_do_not_call_open(self):
        for filename in (
            "generator_eval_parser.py",
            "generator_eval_source_adapters.py",
            "generator_eval_derived_ledger.py",
        ):
            path = os.path.join(MODELLING, filename)
            with open(path, "r", encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                    self.fail(filename + " calls open")


class ContractDocumentTests(unittest.TestCase):
    def test_parser_contract_status_and_pins(self):
        document = load_json(CONTRACT)
        self.assertEqual(document["schema_version"], biological.PARSER_CONTRACT_SCHEMA)
        self.assertEqual(document["status"], biological.STATUS)
        self.assertEqual(document["status"], "M9_PARSER_IMPLEMENTED_SYNTHETIC_ONLY_NOT_AUTHORISED_FOR_PRODUCTION")
        self.assertFalse(document["production_execution_authorised"])
        self.assertFalse(document["production_derived_ledger_creation_authorised"])
        self.assertFalse(document["production_parsing_performed"])
        self.assertFalse(document["synthetic_execution_is_production_validation"])
        pins = document["pinned_parser_provenance"]
        self.assertEqual(pins["rnagenesis_repository_commit"], biological.PINNED_RNAGENESIS_COMMIT)
        self.assertEqual(pins["cleaner_repository_path"], biological.PINNED_CLEANER_PATH)
        self.assertEqual(pins["cleaner_introducing_commit"], biological.PINNED_CLEANER_INTRODUCING_COMMIT)
        self.assertEqual(pins["cleaner_git_blob"], biological.PINNED_CLEANER_GIT_BLOB)
        self.assertEqual(pins["cleaner_file_sha256"], biological.PINNED_CLEANER_SHA256)
        self.assertFalse(document["source_adapters"]["B0"]["nominal_max_seq_len_is_requested_biological_length"])
        self.assertFalse(document["source_adapters"]["B2"]["seed_42_is_a_general_parser_rule"])
        integrity = document["source_integrity"]
        self.assertTrue(integrity["bytes_adapters_hash_exact_supplied_bytes"])
        self.assertTrue(integrity["expected_hash_compared_before_trusted_parsing"])
        self.assertTrue(integrity["mismatch_fails_closed"])
        self.assertTrue(integrity["derived_rows_carry_recomputed_digest"])
        self.assertTrue(integrity["caller_supplied_hash_is_not_copied"])
        self.assertTrue(integrity["decoded_objects_are_not_a_production_entry_point"])
        self.assertEqual(document["public_api"]["accepts"], ["in-memory source bytes"])
        layers = document["failure_layers"]
        self.assertIn("different layers", layers["statement"])
        self.assertTrue(layers["do_not_invent_b1_or_d1_record_id"])
        self.assertTrue(layers["do_not_invent_b2_attempt_index"])
        self.assertTrue(layers["unparseable_output_requires_unique_source_attempt"])
        self.assertTrue(layers["b0_byte_boundaries_and_chunk_metadata_establish_identity_before_decode"])
        self.assertTrue(layers["malformed_json_without_recoverable_identity_fails_the_source"])
        utf8 = document["utf8_extension"]
        self.assertIn("On valid UTF-8 records", utf8["valid_utf8_records"])
        self.assertIn("unparseable_output", utf8["failure_accounting"])
        self.assertTrue(utf8["not_a_change_to_boundary_removal_or_biological_validity"])
        self.assertTrue(utf8["not_permission_to_continue_after_source_hash_failure_or_loss_of_attempt_identity"])
        self.assertIn("does not claim byte-for-byte behavioural identity", utf8["whole_file_utf8_failure"])
        self.assertTrue(utf8["sealed_sources_expected_to_pass_source_integrity_gates"])
        self.assertFalse(utf8["production_parsing_performed_on_this_branch"])
        self.assertIn("does not claim byte-for-byte behavioural identity", document["pinned_parser_provenance"]["local_reproduction_scope"])

    def test_parser_contract_document_states_the_utf8_extension(self):
        with open(CONTRACT_DOC, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn(
            "On valid UTF-8 records, splitting, boundary removal, and validity classification reproduce the pinned RNAGenesis cleaner.",
            text,
        )
        self.assertIn(
            "The M9 source-adapter layer deliberately extends failure accounting by allowing a uniquely identifiable undecodable record to be represented as `unparseable_output`.",
            text,
        )
        self.assertIn("This is not a change to boundary removal or biological validity.", text)
        self.assertIn("It is not permission to continue after a source-hash failure or loss of attempt identity.", text)
        self.assertIn("byte-for-byte behavioural identity with the pinned cleaner for whole-file UTF-8 failure", text)
        self.assertIn("The sealed source artifacts are expected to pass their source-integrity gates.", text)
        self.assertIn("This branch has not run production parsing.", text)
        self.assertIn("Source-container integrity and biological-output classification are different layers.", text)

    def test_source_manifest_is_identity_not_production_parsing(self):
        document = load_json(MANIFEST)
        self.assertEqual(document["schema_version"], biological.SOURCE_MANIFEST_SCHEMA)
        self.assertEqual(document["status"], "FROZEN_SOURCE_IDENTITY_CONTRACT_NOT_EVIDENCE_OF_PRODUCTION_PARSING")
        self.assertFalse(document["production_parsing_performed"])
        self.assertFalse(document["evidence_of_production_parsing"])
        self.assertFalse(document["filesystem_path_is_scientific_identity"])
        self.assertFalse(document["ref_is_an_input"])
        self.assertFalse(document["eval_is_an_input"])
        self.assertFalse(document["synthetic_execution_is_production_validation"])
        self.assertIn("replenishment", document["prohibited_operations"])
        self.assertIn("filtering", document["prohibited_operations"])
        self.assertIn("source_rewriting", document["prohibited_operations"])
        self.assertEqual(document["conditions"]["B0"]["attempt_count"], 30080)
        self.assertEqual(len(document["conditions"]["B0"]["source_chunks"]), 10)
        self.assertEqual(
            document["conditions"]["B0"]["numeric_raw_concatenation_sha256"],
            "ed612277105c6b8747fc7365cc6b67fa8a94e8e5e8e64ee535ecadcb37ff4aaa",
        )
        self.assertEqual(
            document["conditions"]["B0"]["checksum_manifest"]["sha256"],
            "ad3a75fe157248be50427757357cbc5c060be3ddb664d3be64ef178ac90b85c3",
        )
        self.assertIsNone(document["conditions"]["B0"]["biological_requested_length"])
        self.assertFalse(document["conditions"]["B0"]["later_production_seed_order_used_by_parser"])
        self.assertEqual(document["conditions"]["B1"]["attempt_count"], 30000)
        self.assertEqual(
            document["conditions"]["B1"]["combined_ledger_sha256"],
            "37ba0e1b852a6b8492a816a4adc0c6bfee15a554ba28a8ba5dd91d9e32a255d9",
        )
        self.assertEqual(
            document["conditions"]["B1"]["assembly_manifest_sha256"],
            "f217e2e8ce922eef42b5f761159c7d96b7938585b4840922321454076d95d458",
        )
        self.assertEqual(document["conditions"]["B2"]["attempt_count"], 30000)
        self.assertEqual(document["conditions"]["B2"]["empirical_null_seed"], 42)
        self.assertFalse(document["conditions"]["B2"]["empirical_null_seed_is_parser_rule"])
        self.assertEqual(
            document["conditions"]["B2"]["raw_jsonl_sha256"],
            "bbe35f448db0d7fc02ad0156865798382b0b41e9ad047b4e52eddf7cff740c83",
        )
        self.assertEqual(
            document["conditions"]["B2"]["manifest_sha256"],
            "31c07fb966c462263307569b383b112ecfb39725adb9b1b2fd2f93a95d3d8baa",
        )
        self.assertEqual(document["conditions"]["D1"]["attempt_count"], 30000)
        self.assertEqual(
            document["conditions"]["D1"]["combined_ledger_sha256"],
            "cedcc36133f5dfb3678e1560c6d6bab703136fe89e512e939b9f93a9a6361de9",
        )
        self.assertEqual(
            document["conditions"]["D1"]["assembly_manifest_sha256"],
            "5ec79e1485b201d801ca819d9d60a2ee4383abd9cccfbbb011c6e11a9a59bbcb",
        )
        allocation = document["conditions"]["D1"]["seed_allocation"]
        self.assertEqual([item["attempts"] for item in allocation], [15000, 15000])
        self.assertEqual([item["d1_training_seed"] for item in allocation], [43, 44])
        self.assertFalse(document["conditions"]["D1"]["equal_seed_weighting_applied"])
        self.assertEqual(
            document["m7_selected_set"]["selected_set_sha256"],
            "af0c0e555a8b878feadeb17fcbde18d8b780819a42d9e0cc547d2fc0c6895f8f",
        )
        self.assertEqual(
            document["m7_selected_set"]["manifest_sha256"],
            "49b218e3df74825e1931148e2f65b25aae057c822e2ab32d44c2960b1587c91c",
        )
        self.assertEqual(
            document["checkpoint_weight_sha256"]["seed_43"],
            "c0797888bde9033cc15b056c8c09e70b9f7fba0fb21b1f3840a4f1efb77031ab",
        )
        self.assertEqual(
            document["checkpoint_weight_sha256"]["seed_44"],
            "d0fcb5174230b8bbbc6bfe59eabda9b37687c03800012bc1a6981cc215469ed5",
        )
        self.assertFalse(document["excluded_sources"]["sequence_comparison"])
        self.assertGreaterEqual(len(document["excluded_sources"]["lineages"]), 3)
        encoded = json.dumps(document)
        self.assertNotIn("/home/laura/rnagenesis-mres-runs", encoded)
        self.assertNotIn("corpus_final.txt", encoded)
        self.assertNotIn("eval.csv", encoded)


if __name__ == "__main__":
    unittest.main()

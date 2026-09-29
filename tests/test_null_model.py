"""Synthetic tests for the B2 empirical-null generator.

These tests do not read biological TRAIN, VALIDATION, REF, or EVAL files.
Test-only fixture authorization is not a biological run and must not write
under /home/laura/rnagenesis-mres-runs/.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import inspect
import io
import json
import os
import re
import socket
import tempfile
import unittest
from pathlib import Path

import numpy as np

import importlib.util

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "null_model", ROOT / "scripts" / "null_model.py"
)
null_model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(null_model)

SECRET = "GGGGCCCCAAAACCCCUUUUACAUCGAUCG"
BIOLOGICAL_TRAIN = Path(
    "/home/laura/rnagenesis-mres-data/development/corpus_final.txt"
)
RUNS_ROOT = Path("/home/laura/rnagenesis-mres-runs")
PROBE = RUNS_ROOT / "m4-stage2a-must-not-be-created"


def _sequences_from_indexes(count):
    alphabet = "ACGU"
    sequences = []
    for index in range(count):
        value = index + 1
        chars = []
        while value:
            chars.append(alphabet[value % 4])
            value //= 4
        sequences.append("A" + "".join(reversed(chars)))
    return sequences


def _independent_sample(n, freqs, lengths, seed):
    rng = np.random.default_rng(seed)
    bases = list(freqs.keys())
    probs = [freqs[base] for base in bases]
    sampled = rng.choice(lengths, size=n, replace=True)
    sequences = []
    for length in sampled:
        sequences.append("".join(rng.choice(bases, size=length, p=probs)))
    return sequences


class LegacyStatisticalTests(unittest.TestCase):
    def test_legacy_statistical_behavior_on_small_fixture(self):
        sequences = ["AA", "C", "UUU", "G"]
        freqs, lengths = null_model.get_corpus_stats(sequences)
        self.assertEqual(list(freqs.keys()), ["A", "C", "U", "G"])
        self.assertEqual(lengths, [2, 1, 3, 1])
        generated = null_model.generate_null_sequences(8, freqs, lengths, seed=42)
        self.assertEqual(generated, _independent_sample(8, freqs, lengths, 42))
        stats = null_model.compute_corpus_statistics(sequences)
        for index, base in enumerate("ACUG"):
            self.assertEqual(np.float64(freqs[base]), stats["probabilities"][index])

    def test_same_seed_repeats(self):
        freqs = {"A": 0.4, "C": 0.3, "U": 0.2, "G": 0.1}
        lengths = [3, 5, 8]
        first = null_model.generate_null_sequences(12, freqs, lengths, seed=42)
        second = null_model.generate_null_sequences(12, freqs, lengths, seed=42)
        self.assertEqual(first, second)

    def test_different_seed_changes_result(self):
        freqs = {"A": 0.4, "C": 0.3, "U": 0.2, "G": 0.1}
        lengths = [4, 7, 9, 12]
        first = null_model.generate_null_sequences(25, freqs, lengths, seed=42)
        second = null_model.generate_null_sequences(25, freqs, lengths, seed=43)
        self.assertNotEqual(first, second)

    def test_length_draw_precedes_nucleotide_draws(self):
        calls = []
        real_factory = np.random.default_rng

        class Spy(object):
            def __init__(self, seed):
                self._rng = real_factory(seed)

            def choice(self, values, size=None, replace=True, p=None):
                result = self._rng.choice(values, size=size, replace=replace, p=p)
                calls.append(
                    {
                        "size": int(size) if np.ndim(size) == 0 else list(size),
                        "replace": replace,
                        "has_p": p is not None,
                        "result": result,
                    }
                )
                return result

        freqs = {"A": 0.5, "C": 0.25, "U": 0.25, "G": 0.0}
        lengths = [2, 5]
        original = null_model.np.random.default_rng
        null_model.np.random.default_rng = Spy
        try:
            null_model.generate_null_sequences(4, freqs, lengths, seed=7)
        finally:
            null_model.np.random.default_rng = original
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[0]["size"], 4)
        self.assertTrue(calls[0]["replace"])
        self.assertFalse(calls[0]["has_p"])
        sampled_lengths = [int(value) for value in calls[0]["result"]]
        self.assertEqual(len(calls) - 1, 4)
        for call, sampled_length in zip(calls[1:], sampled_lengths):
            self.assertTrue(call["has_p"])
            self.assertEqual(call["size"], sampled_length)

    def test_probability_order_is_acug(self):
        stats = null_model.compute_corpus_statistics(["A", "C", "U", "G", "A"])
        self.assertEqual(stats["probability_order"], ["A", "C", "U", "G"])
        self.assertEqual(stats["nucleotide_count_order"], ["A", "C", "U", "G"])
        self.assertEqual(
            [stats["nucleotide_counts"][base] for base in "ACUG"],
            [2, 1, 1, 1],
        )
        freqs = null_model.frequencies_from_probabilities(stats["probabilities"])
        self.assertEqual(list(freqs.keys()), ["A", "C", "U", "G"])

    def test_float64_probabilities_and_absolute_tolerance(self):
        stats = null_model.compute_corpus_statistics(["A", "C", "U", "G"])
        self.assertEqual(stats["probabilities"].dtype, np.dtype(np.float64))
        self.assertEqual(null_model.RELATIVE_SUM_TOLERANCE, 0.0)
        self.assertEqual(null_model.ABSOLUTE_SUM_TOLERANCE, 1e-12)
        null_model.validate_probabilities(stats["probabilities"])
        outside = np.array([1.0 + 1e-9, 0.0, 0.0, 0.0], dtype=np.float64)
        self.assertTrue(np.isclose(outside.sum(), 1.0, rtol=1e-6, atol=0.0))
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.validate_probabilities(outside)
        self.assertEqual(ctx.exception.code, "probability_sum_tolerance")
        negative = np.array([-1e-12, 1.0, 0.0, 1e-12], dtype=np.float64)
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.validate_probabilities(negative)
        self.assertEqual(ctx.exception.code, "probability_negative")
        non_finite = np.array([np.nan, 0.0, 0.0, 0.0], dtype=np.float64)
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.validate_probabilities(non_finite)
        self.assertEqual(ctx.exception.code, "probability_not_finite")
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.probabilities_from_counts({"A": 0, "C": 0, "U": 0, "G": 0})
        self.assertEqual(ctx.exception.code, "zero_nucleotides")


class InputValidationTests(unittest.TestCase):
    def _assert_secret_absent(self, error):
        text = "{} {}".format(error.code, error.detail)
        self.assertNotIn(SECRET, text)
        self.assertNotIn(SECRET.lower(), text)

    def test_reject_empty_input(self):
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.parse_train_text_bytes(b"")
        self.assertEqual(ctx.exception.code, "empty_input")
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.compute_corpus_statistics([])
        self.assertEqual(ctx.exception.code, "empty_corpus")

    def test_reject_blank_lines(self):
        raw = (SECRET + "\n\nACGU\n").encode("utf-8")
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.parse_train_text_bytes(raw)
        self.assertEqual(ctx.exception.code, "blank_line")
        self._assert_secret_absent(ctx.exception)

    def test_reject_t_lowercase_whitespace_and_ambiguity(self):
        cases = {
            b"ACGT\n": "thymine_rejected",
            (SECRET.lower() + "\n").encode("utf-8"): "lowercase_rejected",
            b"ACGU \n": "whitespace_rejected",
            b"\tACGU\n": "whitespace_rejected",
            b"ACGUN\n": "ambiguity_symbol_rejected",
            b"ACGUR\n": "ambiguity_symbol_rejected",
        }
        for raw, code in cases.items():
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.parse_train_text_bytes(raw)
            self.assertEqual(ctx.exception.code, code)
            self._assert_secret_absent(ctx.exception)

    def test_reject_duplicates(self):
        sequences = [SECRET, "ACGU", SECRET]
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.enforce_sequence_contract(sequences, 3, 3)
        self.assertEqual(ctx.exception.code, "duplicate_sequence")
        self._assert_secret_absent(ctx.exception)

    def test_reject_wrong_production_count(self):
        sequences = _sequences_from_indexes(3)
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.enforce_sequence_contract(
                sequences,
                null_model.EXPECTED_SEQUENCE_COUNT,
                null_model.EXPECTED_UNIQUE_COUNT,
            )
        self.assertEqual(ctx.exception.code, "sequence_count_mismatch")
        self.assertIn("expected_count=669", ctx.exception.detail)
        for sequence in sequences:
            self.assertNotIn(sequence, str(ctx.exception))

    def test_reject_wrong_sha256(self):
        raw = (SECRET + "\n").encode("utf-8")
        actual = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.enforce_sha256(actual, null_model.TRAIN_TEXT_SHA256)
        self.assertEqual(ctx.exception.code, "sha256_mismatch")
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertEqual(
            null_model.TRAIN_TEXT_SHA256,
            "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d",
        )

    def test_refuse_prohibited_filenames_and_roles(self):
        for name in ("ft_train.csv", "ft_validation.csv", "ref.csv", "eval.csv"):
            path = Path(tempfile.gettempdir()) / name
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.reject_prohibited_input_path(path, "TRAIN_TEXT")
            self.assertEqual(ctx.exception.code, "prohibited_input")
            self.assertFalse(path.exists())
        for role in ("REF", "EVAL"):
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.reject_prohibited_input_path("corpus_final.txt", role)
            self.assertEqual(ctx.exception.code, "ref_eval_access_prohibited")

    def test_synthetic_669_count_and_uniqueness(self):
        sequences = _sequences_from_indexes(669)
        self.assertEqual(len(sequences), 669)
        self.assertEqual(len(set(sequences)), 669)
        unique = null_model.enforce_sequence_contract(sequences, 669, 669)
        self.assertEqual(unique, 669)
        with self.assertRaises(null_model.NullModelError):
            null_model.enforce_sequence_contract(sequences[:-1], 669, 669)
        with self.assertRaises(null_model.NullModelError):
            null_model.enforce_sequence_contract(sequences + ["ACGUACGU"], 669, 669)
        duplicated = list(sequences)
        duplicated[-1] = duplicated[0]
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.enforce_sequence_contract(duplicated, 669, 669)
        self.assertEqual(ctx.exception.code, "duplicate_sequence")
        self.assertNotIn(duplicated[0], str(ctx.exception))
        payload = ("\n".join(sequences) + "\n").encode("utf-8")
        parsed = null_model.parse_train_text_bytes(payload)
        self.assertEqual(parsed, sequences)
        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            fixture = Path(directory) / "corpus_final.txt"
            fixture.write_bytes(payload)
            self.assertNotEqual(
                hashlib.sha256(fixture.read_bytes()).hexdigest(),
                null_model.TRAIN_TEXT_SHA256,
            )
            self.assertNotEqual(fixture.resolve(), BIOLOGICAL_TRAIN)

    def test_no_silent_normalisation(self):
        self.assertEqual(null_model.parse_train_text_bytes(b"ACGU\n"), ["ACGU"])
        self.assertEqual(null_model.parse_train_text_bytes(b"ACGU"), ["ACGU"])
        for raw in (b"acgu\n", b"ACGT\n", b" ACGU\n", b"ACGU \n", b"ACGU\t\n"):
            with self.assertRaises(null_model.NullModelError):
                null_model.parse_train_text_bytes(raw)


class JsonlAndRetentionTests(unittest.TestCase):
    def _records(self, n=4, seed=42):
        sequences = ["A", "AC", "ACGU"]
        stats = null_model.compute_corpus_statistics(sequences)
        freqs = null_model.frequencies_from_probabilities(stats["probabilities"])
        return null_model.build_raw_records(n, freqs, stats["lengths"], seed)

    def test_canonical_jsonl_bytes(self):
        data = null_model.serialize_jsonl(self._records())
        self.assertIsInstance(data, bytes)
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", data)
        self.assertTrue(data.endswith(b"\n"))
        text = data.decode("utf-8")
        self.assertFalse(text.startswith("\ufeff"))
        lines = text.split("\n")
        self.assertEqual(lines[-1], "")
        for line in lines[:-1]:
            pairs = json.loads(line, object_pairs_hook=list)
            self.assertEqual(
                [key for key, _value in pairs],
                list(null_model.RAW_RECORD_KEYS),
            )
            self.assertNotIn(" ", line.split('"sequence":"')[0])
            parsed = json.loads(line)
            again = json.dumps(
                {key: parsed[key] for key in null_model.RAW_RECORD_KEYS},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            self.assertEqual(line, again)

    def test_all_attempts_retained_including_duplicates(self):
        stats = null_model.compute_corpus_statistics(["A"])
        freqs = null_model.frequencies_from_probabilities(stats["probabilities"])
        records = null_model.build_raw_records(6, freqs, stats["lengths"], 42)
        self.assertEqual(len(records), 6)
        self.assertEqual([record["sequence"] for record in records], ["A"] * 6)
        self.assertEqual(null_model.unique_count_diagnostic(records), 1)
        data = null_model.serialize_jsonl(records)
        self.assertEqual(data.count(b"\n"), 6)

    def test_attempt_indexes_are_contiguous_and_zero_based(self):
        records = self._records(5)
        self.assertEqual([record["attempt_index"] for record in records], [0, 1, 2, 3, 4])

    def test_sequence_hashes_match_utf8_bytes_without_newline(self):
        records = self._records()
        for record in records:
            digest = hashlib.sha256(record["sequence"].encode("utf-8")).hexdigest()
            self.assertEqual(record["sequence_sha256"], digest)
            self.assertNotEqual(
                digest,
                hashlib.sha256((record["sequence"] + "\n").encode("utf-8")).hexdigest(),
            )
            self.assertTrue(record["valid_acgu"])
            self.assertEqual(record["sampled_length"], len(record["sequence"]))


PINNED_SMALL_FIXTURE_JSONL = (
    b'{"attempt_index":0,"seed":42,"sampled_length":2,"sequence":"GU","valid_acgu":true,"sequence_sha256":"86856a090297ec6f5f6a6eb3b7b7837f79cd941ea499c5a8b4c0bc9bced1b1ca"}\n'
    b'{"attempt_index":1,"seed":42,"sampled_length":1,"sequence":"A","valid_acgu":true,"sequence_sha256":"559aead08264d5795d3909718cdd05abd49572e84fe55590eef31a88a08fdffd"}\n'
    b'{"attempt_index":2,"seed":42,"sampled_length":3,"sequence":"GUU","valid_acgu":true,"sequence_sha256":"54f2d3e5536e4e0d59d3e60a65ac9449102792e49c5375db8febfbddcce7f084"}\n'
    b'{"attempt_index":3,"seed":42,"sampled_length":1,"sequence":"A","valid_acgu":true,"sequence_sha256":"559aead08264d5795d3909718cdd05abd49572e84fe55590eef31a88a08fdffd"}\n'
)
PINNED_SMALL_SEQUENCES = ["AA", "C", "UUU", "G"]


def _git_stdout(*args):
    completed = __import__("subprocess").run(
        ["git"] + list(args),
        cwd=str(ROOT),
        stdout=__import__("subprocess").PIPE,
        stderr=__import__("subprocess").PIPE,
        check=True,
    )
    return completed.stdout.decode("utf-8").strip()


def _synthetic_config(digest, sequence_count, attempt_count, seed):
    return "\n".join(
        [
            "document_status: APPROVED_FOR_SCIENTIFIC_EXECUTION",
            "consumable_by_executable_workflow: true",
            "test_only_synthetic_fixture: true",
            "biological_run: false",
            "schema_version: m4-stage1-draft-1",
            "experiment_id: synthetic_not_biological",
            "condition_manifest_label: synthetic_condition",
            "human_approval:",
            "  approving_person: Synthetic Approver",
            "  approval_date: 1 January 2000",
            '  approval_recorded_timestamp: "2000-01-01T00:00:00+00:00"',
            "  approval_source: unit test fixture",
            "  approval_scope: synthetic test only",
            "  explicitly_not_approved:",
            "    - scientific_execution",
            "    - B2_generation",
            "    - biological_data_runs",
            "  m4_complete: false",
            "scientific_execution_authorisation:",
            "  authorisation_id: synthetic_not_a_biological_run",
            "  authorisation_active: true",
            "  activation_status: active_single_run",
            '  activation_recorded_timestamp: "2000-01-01T00:00:00+00:00"',
            "  intended_scope_approval: synthetic fixture authorization for this test invocation only",
            "  approved_by: Synthetic Approver",
            "  approval_date: 1 January 2000",
            '  approval_recorded_timestamp: "2000-01-01T00:00:00+00:00"',
            "  approval_source: unit test fixture",
            "  scope: synthetic test invocation only",
            "  executing_implementation_commit: synthetic",
            "  branch: synthetic",
            "  condition: synthetic_condition",
            "  output_directory: synthetic-output-not-a-production-run",
            "  train_text_path: synthetic/corpus.txt",
            '  train_text_sha256: "{}"'.format(digest),
            "  expected_records: {}".format(sequence_count),
            "  expected_unique_records: {}".format(sequence_count),
            '  alphabet: "^[ACGU]+$"',
            "  raw_attempt_count: {}".format(attempt_count),
            "  seed: {}".format(seed),
            "  rng: numpy.random.default_rng",
            "  device: CPU only",
            "  gpu_use: prohibited",
            "  model_loading: prohibited",
            "  ref_access: prohibited",
            "  eval_access: prohibited",
            "  overwrite_or_append: prohibited",
            "  single_run_only: true",
            "  revoke_after_completed_or_failed_invocation: true",
            "  second_attempt_requires_new_directory_and_new_human_authorisation: true",
            "  success_claimed: false",
            "  m4_complete: false",
            "input:",
            "  expected_sha256: {}".format(digest),
            "  expected_sequence_count: {}".format(sequence_count),
            "  expected_unique_count: {}".format(sequence_count),
            "sampler:",
            "  seed: {}".format(seed),
            "  raw_sequence_count: {}".format(attempt_count),
            "",
        ]
    )


def _contract_document(train_sha):
    return {
        "contract_id": "rnagenesis_corrected_669_core_m0",
        "corpus_commit": "synthetic-corpus-not-biological",
        "roles": {
            "TRAIN_TEXT": {
                "path": "synthetic/corpus.txt",
                "sha256": train_sha,
                "allowed": ["fit"],
                "authoritative_rnagenesis_fitting_input": True,
            },
            "REF": {
                "sha256": "11" * 32,
                "allowed": ["aptarank_calibrate"],
                "available_during_generator_development": False,
            },
            "EVAL": {
                "sha256": "22" * 32,
                "allowed": ["final_evaluate_after_unlock"],
                "available_during_generator_development": False,
            },
        },
        "access_policy": {
            "development_read_allowlist": ["TRAIN", "TRAIN_TEXT", "VALIDATION"],
        },
    }


def _materialize(root, sequences, attempt_count, seed, mutate_contract=None, expected_contract_sha=None):
    payload = ("\n".join(sequences) + "\n").encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    train = root / "synthetic_train.txt"
    train.write_bytes(payload)
    document = _contract_document(digest)
    if mutate_contract is not None:
        mutate_contract(document)
    contract_bytes = json.dumps(document, separators=(",", ":")).encode("utf-8") + b"\n"
    contract_path = root / "frozen_data_contract.json"
    contract_path.write_bytes(contract_bytes)
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()
    config_path = root / "synthetic_b2.yaml"
    config_path.write_text(
        _synthetic_config(digest, len(sequences), attempt_count, seed),
        encoding="utf-8",
    )
    run_root = root / "surrogate-runs"
    run_root.mkdir()
    fixture = null_model.TestOnlySyntheticFixture(
        fixture_root=root,
        config_path=config_path,
        contract_path=contract_path,
        input_path=train,
        run_root=run_root,
        attempt_count=attempt_count,
        seed=seed,
        expected_contract_sha256=(
            contract_sha if expected_contract_sha is None else expected_contract_sha
        ),
    )
    return fixture, payload, digest, run_root


ONE_RUN_OUTPUT_DIRECTORY = (
    "/home/laura/rnagenesis-mres-runs/m4_b2_empirical_null_2d9ec89_attempt1"
)
ATTEMPT2_OUTPUT_DIRECTORY = (
    "/home/laura/rnagenesis-mres-runs/m4_b2_empirical_null_6f82878_attempt2"
)
ATTEMPT2_AUTHORISATION_ID = "m4_b2_empirical_null_6f82878_attempt2"
ATTEMPT2_IMPLEMENTATION_COMMIT = "6f82878a7bbde78c74f91181c672d2d4df74b5cc"
ATTEMPT2_AUTHORIZATION_COMMIT = "dab6c7e2453a6e510d87aecc58c56079ffe8e671"
ATTEMPT2_MANIFEST_SCHEMA = "m4-b2-run-manifest-2"
ATTEMPT2_MANIFEST_SHA256 = "31c07fb966c462263307569b383b112ecfb39725adb9b1b2fd2f93a95d3d8baa"
ATTEMPT2_MANIFEST_BYTES = 12496
ATTEMPT2_RAW_BYTES = 6787972
ATTEMPT2_LOCAL_START = "2026-09-29T23:09:40.097289+10:00"
ATTEMPT2_LOCAL_END = "2026-09-29T23:09:41.425559+10:00"
ATTEMPT2_REVOCATION_TIMESTAMP = "2026-09-29T23:45:10+10:00"
B2_ACCEPTANCE_TIMESTAMP = "2026-09-29T23:45:10+10:00"
PRIOR_RAW_SHA256 = "bbe35f448db0d7fc02ad0156865798382b0b41e9ad047b4e52eddf7cff740c83"
PRIOR_MANIFEST_SHA256 = "5c25568a08e2b0b1ec8f30c940755bcad3426115b7d1bb327acc1ce55aa8ccf2"
REVOCATION_ONLY_AUTHORISATION_KEYS = (
    "revocation_recorded_timestamp",
    "single_invocation_consumed",
    "reuse_of_same_authorisation_prohibited",
    "reuse_of_same_output_directory_prohibited",
)
AUTHORISATION_TEST_OUTPUT = (
    "/home/laura/rnagenesis-mres-runs/m4_b2_authorisation_test_exact_must_not_exist"
)
AUTHORISATION_TEST_SIBLING = (
    "/home/laura/rnagenesis-mres-runs/m4_b2_authorisation_test_sibling_must_not_exist"
)
ONE_RUN_AUTHORISATION = {
    "authorisation_id": "m4_b2_empirical_null_2d9ec89_attempt1",
    "authorisation_active": True,
    "activation_status": "active_single_run",
    "activation_recorded_timestamp": "2026-09-29T18:18:04+10:00",
    "intended_scope_approval": (
        "Laura Hardy approved this one-run scope on 29 September 2026. "
        "That approval authorized the now-consumed CPU-only B2 invocation at the named "
        "output directory. The executing implementation commit was "
        "70f950434501964dd179760aa4fc82766df74289. The authorization is revoked. "
        "It does not claim that the run succeeded and does not complete M4.\n"
    ),
    "approved_by": "Laura Hardy",
    "approval_date": "29 September 2026",
    "approval_recorded_timestamp": "2026-09-29T17:29:06+10:00",
    "approval_source": "explicit human approval in the M4 review chat",
    "scope": "one CPU-only B2 empirical-null run",
    "executing_implementation_commit": "70f950434501964dd179760aa4fc82766df74289",
    "branch": "main",
    "condition": "B2_train_matched_empirical_null",
    "output_directory": ONE_RUN_OUTPUT_DIRECTORY,
    "train_text_path": "/home/laura/rnagenesis-mres-data/development/corpus_final.txt",
    "train_text_sha256": "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d",
    "expected_records": 669,
    "expected_unique_records": 669,
    "alphabet": "^[ACGU]+$",
    "raw_attempt_count": 30000,
    "seed": 42,
    "rng": "numpy.random.default_rng",
    "device": "CPU only",
    "gpu_use": "prohibited",
    "model_loading": "prohibited",
    "ref_access": "prohibited",
    "eval_access": "prohibited",
    "overwrite_or_append": "prohibited",
    "single_run_only": True,
    "revoke_after_completed_or_failed_invocation": True,
    "second_attempt_requires_new_directory_and_new_human_authorisation": True,
    "success_claimed": False,
    "m4_complete": False,
}
REVOCATION_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{2}:[0-9]{2}$"
)
MANIFEST_PROVENANCE_DEFECT = (
    "manifest.json contains the earlier Stage 1 implementation-only "
    "human_approval record, whose explicitly_not_approved list includes "
    "scientific_execution and B2_generation. It does not serialize the later "
    "active scientific_execution_authorisation block. The committed executable "
    "configuration and repository provenance show that the run was authorized, "
    "but the manifest is internally misleading and must not yet be treated as "
    "a complete authorization record."
)


def _repository_b2_config_path():
    return ROOT / "config" / "experiments" / "B2_empirical_null.yaml"


def _load_repository_b2_config():
    import yaml

    text = _repository_b2_config_path().read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise AssertionError("repository B2 configuration root must be a mapping")
    return loaded, text


def _execution_gates(loaded):
    execution = loaded.get("execution")
    if not isinstance(execution, dict):
        return (loaded.get("document_status"), loaded.get("consumable_by_executable_workflow"), None)
    return (
        loaded.get("document_status"),
        loaded.get("consumable_by_executable_workflow"),
        execution.get("authorised"),
    )


def _gates_are_open(loaded):
    status, consumable, authorised = _execution_gates(loaded)
    return (
        status == "APPROVED_FOR_SCIENTIFIC_EXECUTION"
        and consumable is True
        and authorised is True
    )


def _gates_are_closed(loaded):
    status, consumable, authorised = _execution_gates(loaded)
    return (
        status == "APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION"
        and consumable is False
        and authorised is False
        and "scientific_execution_authorisation" not in loaded
    )


def _assert_every_m4_complete_is_false(test, value):
    if isinstance(value, dict):
        if "m4_complete" in value:
            test.assertIs(value["m4_complete"], False)
        for child in value.values():
            _assert_every_m4_complete_is_false(test, child)
    elif isinstance(value, list):
        for child in value:
            _assert_every_m4_complete_is_false(test, child)


def _non_executable_config():
    """In-memory configuration that must fail the execution gate."""
    return {
        "document_status": "APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION",
        "consumable_by_executable_workflow": False,
        "execution": {"authorised": False},
    }


def _is_completed_evidence_path(path):
    """True for either recorded evidence directory or a child. Does not touch it."""
    text = os.path.normpath(os.fspath(path))
    for root in (ONE_RUN_OUTPUT_DIRECTORY, ATTEMPT2_OUTPUT_DIRECTORY):
        root_norm = os.path.normpath(root)
        if text == root_norm or text.startswith(root_norm + os.sep):
            return True
    return False


def _install_evidence_inspection_guard():
    """Refuse filesystem inspection of either real evidence directory."""
    real = {
        "stat": os.stat,
        "lstat": os.lstat,
        "open": os.open,
        "listdir": os.listdir,
        "scandir": os.scandir,
        "exists": os.path.exists,
        "lexists": os.path.lexists,
        "realpath": os.path.realpath,
        "isdir": os.path.isdir,
        "path_exists": Path.exists,
        "path_is_dir": Path.is_dir,
        "path_stat": Path.stat,
        "path_lstat": Path.lstat,
        "path_open": Path.open,
        "path_read_bytes": Path.read_bytes,
        "path_read_text": Path.read_text,
        "path_iterdir": Path.iterdir,
    }

    def check(path):
        if isinstance(path, int):
            return
        try:
            text = os.fspath(path)
        except TypeError:
            return
        if isinstance(text, bytes):
            text = os.fsdecode(text)
        if not isinstance(text, str):
            return
        if _is_completed_evidence_path(text):
            raise AssertionError("real evidence directory was inspected")

    def guarded_stat(path, *args, **kwargs):
        check(path)
        return real["stat"](path, *args, **kwargs)

    def guarded_lstat(path, *args, **kwargs):
        check(path)
        return real["lstat"](path, *args, **kwargs)

    def guarded_open(path, *args, **kwargs):
        check(path)
        return real["open"](path, *args, **kwargs)

    def guarded_listdir(path, *args, **kwargs):
        check(path)
        return real["listdir"](path, *args, **kwargs)

    def guarded_scandir(path, *args, **kwargs):
        check(path)
        return real["scandir"](path, *args, **kwargs)

    def guarded_exists(path):
        check(path)
        return real["exists"](path)

    def guarded_lexists(path):
        check(path)
        return real["lexists"](path)

    def guarded_realpath(path):
        check(path)
        return real["realpath"](path)

    def guarded_isdir(path):
        check(path)
        return real["isdir"](path)

    def guarded_path_exists(path_self):
        check(path_self)
        return real["path_exists"](path_self)

    def guarded_path_is_dir(path_self):
        check(path_self)
        return real["path_is_dir"](path_self)

    def guarded_path_stat(path_self, *args, **kwargs):
        check(path_self)
        return real["path_stat"](path_self, *args, **kwargs)

    def guarded_path_lstat(path_self, *args, **kwargs):
        check(path_self)
        return real["path_lstat"](path_self, *args, **kwargs)

    def guarded_path_open(path_self, *args, **kwargs):
        check(path_self)
        return real["path_open"](path_self, *args, **kwargs)

    def guarded_path_read_bytes(path_self):
        check(path_self)
        return real["path_read_bytes"](path_self)

    def guarded_path_read_text(path_self, *args, **kwargs):
        check(path_self)
        return real["path_read_text"](path_self, *args, **kwargs)

    def guarded_path_iterdir(path_self):
        check(path_self)
        return real["path_iterdir"](path_self)

    os.stat = guarded_stat
    os.lstat = guarded_lstat
    os.open = guarded_open
    os.listdir = guarded_listdir
    os.scandir = guarded_scandir
    os.path.exists = guarded_exists
    os.path.lexists = guarded_lexists
    os.path.realpath = guarded_realpath
    os.path.isdir = guarded_isdir
    Path.exists = guarded_path_exists
    Path.is_dir = guarded_path_is_dir
    Path.stat = guarded_path_stat
    Path.lstat = guarded_path_lstat
    Path.open = guarded_path_open
    Path.read_bytes = guarded_path_read_bytes
    Path.read_text = guarded_path_read_text
    Path.iterdir = guarded_path_iterdir
    return real


def _restore_evidence_inspection_guard(real):
    os.stat = real["stat"]
    os.lstat = real["lstat"]
    os.open = real["open"]
    os.listdir = real["listdir"]
    os.scandir = real["scandir"]
    os.path.exists = real["exists"]
    os.path.lexists = real["lexists"]
    os.path.realpath = real["realpath"]
    os.path.isdir = real["isdir"]
    Path.exists = real["path_exists"]
    Path.is_dir = real["path_is_dir"]
    Path.stat = real["path_stat"]
    Path.lstat = real["path_lstat"]
    Path.open = real["path_open"]
    Path.read_bytes = real["path_read_bytes"]
    Path.read_text = real["path_read_text"]
    Path.iterdir = real["path_iterdir"]


def _refuse_completed_evidence_access(path):
    if _is_completed_evidence_path(path):
        raise AssertionError("completed evidence path was used")


def _refuse_biological_read(path_self, real_read, events):
    text = os.path.normpath(str(path_self))
    events.append(text)
    if text.endswith("corpus_final.txt") or "rnagenesis-mres-data" in text:
        raise AssertionError("biological TRAIN_TEXT was opened")
    _refuse_completed_evidence_access(text)
    return real_read(path_self)


def _stage1_protocol_approval():
    """Stage 1 list that must not be readable as the invocation authority."""
    return {
        "approving_person": "Stage One Approver",
        "approval_date": "29 September 2026",
        "approval_recorded_timestamp": "2026-09-29T14:57:40+10:00",
        "approval_source": "formal human approval in the M4 review chat",
        "approval_scope": "Stage 1 protocol package for M4 implementation only",
        "explicitly_not_approved": [
            "scientific_execution",
            "biological_data_runs",
            "B2_generation",
        ],
        "m4_complete": False,
    }


def _observed_manifest_inputs(approval, scientific):
    stats = null_model.compute_corpus_statistics(PINNED_SMALL_SEQUENCES)
    return {
        "approval": approval,
        "scientific_execution_authorisation": scientific,
        "git": {
            "mres_commit": "a" * 40,
            "mres_upstream_sha": "b" * 40,
            "branch": "main",
            "dirty": False,
            "patch_sha256": None,
            "patch_sha256_reason": "working tree clean; patch hash is not applicable",
        },
        "stats": stats,
        "access_log": [],
        "attempt_count": 4,
        "retained_count": 4,
        "schema_version": "m4-stage1-draft-1",
        "experiment_id": "B2_empirical_null_draft",
        "condition_identifier": "B2_train_matched_empirical_null",
        "run_identifier": "authorisation-test-not-evidence",
        "attempt_identifier": "invocation-0",
        "started_at": "2026-09-29T00:00:00+10:00",
        "ended_at": "2026-09-29T00:00:01+10:00",
        "hostname": "synthetic-host",
        "frozen_corpus_commit": "synthetic-corpus-not-biological",
        "config_path": "synthetic-config-not-a-file",
        "config_sha256": "c" * 64,
        "contract_path": "synthetic-contract-not-a-file",
        "contract_sha256": "d" * 64,
        "input_path": "synthetic-train-not-biological",
        "expected_input_sha256": "e" * 64,
        "actual_input_sha256": "e" * 64,
        "expected_sequence_count": 4,
        "actual_sequence_count": 4,
        "expected_unique_count": 4,
        "actual_unique_count": 4,
        "seed": 42,
        "unique_count_diagnostic": 4,
        "command": "synthetic-manifest-test",
        "output_path": AUTHORISATION_TEST_OUTPUT + "/" + null_model.RAW_JSONL_FILENAME,
        "output_byte_count": len(PINNED_SMALL_FIXTURE_JSONL),
        "output_sha256": hashlib.sha256(PINNED_SMALL_FIXTURE_JSONL).hexdigest(),
        "warnings": [],
        "retries": [],
        "deviations": [],
        "stopping_reason": "completed_sampling_and_wrote_closed_output",
        "gpu_api_invoked": False,
    }


def _authorised_production_config(output_directory=AUTHORISATION_TEST_OUTPUT):
    """In-memory open gate. Independent of the repository B2 file."""
    block = dict(ONE_RUN_AUTHORISATION)
    block["authorisation_active"] = True
    block["output_directory"] = output_directory
    block["success_claimed"] = False
    block["m4_complete"] = False
    return {
        "document_status": "APPROVED_FOR_SCIENTIFIC_EXECUTION",
        "consumable_by_executable_workflow": True,
        "execution": {"authorised": True},
        "condition_manifest_label": block["condition"],
        "schema_version": "m4-stage1-draft-1",
        "experiment_id": "B2_empirical_null_draft",
        "input": {
            "expected_development_path": block["train_text_path"],
            "expected_sha256": block["train_text_sha256"],
            "expected_sequence_count": block["expected_records"],
            "expected_unique_count": block["expected_unique_records"],
            "alphabet": block["alphabet"],
        },
        "sampler": {
            "seed": block["seed"],
            "proposed_seed": block["seed"],
            "raw_sequence_count": block["raw_attempt_count"],
            "numpy_generator": block["rng"],
        },
        "scientific_execution_authorisation": block,
    }


def _invoke_guarded_production(
    output, config, intercept_contract=False, record_containment_only=False
):
    """Run production with an injected config and refuse biological access."""
    events = []
    created = {"count": 0}
    contract_attempts = {"count": 0}
    containment = []
    real_read = Path.read_bytes
    real_load = null_model.load_b2_config_bytes
    real_mkdir = os.mkdir
    real_resolve = null_model.resolve_fixed_repository_file
    real_open = null_model._open_verified_contract
    real_create = null_model.create_output_directory
    real_write = null_model.exclusive_fsync_write
    real_validate = null_model.validate_output_containment

    def read_spy(path_self):
        text = os.path.normpath(str(path_self))
        events.append(text)
        if text.endswith("corpus_final.txt") or "rnagenesis-mres-data" in text:
            raise AssertionError("biological TRAIN_TEXT was opened")
        if text.endswith("frozen_data_contract.json"):
            raise AssertionError("frozen contract was opened")
        if text.endswith("ref.csv") or text.endswith("eval.csv"):
            raise AssertionError("REF or EVAL was opened")
        _refuse_completed_evidence_access(text)
        return real_read(path_self)

    def load_spy(_raw):
        return config

    def mkdir_spy(path, mode=0o777):
        created["count"] += 1
        raise AssertionError("directory creation was attempted")

    def resolve_spy(root, relative, role):
        if role == "contract":
            contract_attempts["count"] += 1
            if intercept_contract:
                raise null_model.NullModelError(
                    "intercepted_before_contract",
                    "authorisation checks passed; contract open was intercepted",
                )
            raise AssertionError("frozen contract resolve was attempted")
        return real_resolve(root, relative, role)

    def open_spy(*_args, **_kwargs):
        raise AssertionError("frozen contract was opened")

    def create_spy(_path):
        created["count"] += 1
        raise AssertionError("directory creation was attempted")

    def write_spy(*_args, **_kwargs):
        raise AssertionError("output write was attempted")

    def validate_spy(path, run_root):
        containment.append(
            (os.path.normpath(str(path)), os.path.normpath(str(run_root)))
        )
        if record_containment_only:
            return Path(os.path.normpath(str(path)))
        return real_validate(path, run_root)

    Path.read_bytes = read_spy
    null_model.load_b2_config_bytes = load_spy
    os.mkdir = mkdir_spy
    null_model.resolve_fixed_repository_file = resolve_spy
    null_model._open_verified_contract = open_spy
    null_model.create_output_directory = create_spy
    null_model.exclusive_fsync_write = write_spy
    null_model.validate_output_containment = validate_spy
    try:
        try:
            null_model.run_b2_production(str(output))
            error = None
        except null_model.NullModelError as exc:
            error = exc
    finally:
        Path.read_bytes = real_read
        null_model.load_b2_config_bytes = real_load
        os.mkdir = real_mkdir
        null_model.resolve_fixed_repository_file = real_resolve
        null_model._open_verified_contract = real_open
        null_model.create_output_directory = real_create
        null_model.exclusive_fsync_write = real_write
        null_model.validate_output_containment = real_validate
    return {
        "error": error,
        "events": events,
        "created": created["count"],
        "contract_attempts": contract_attempts["count"],
        "containment": containment,
    }


class OutputConfigAndManifestTests(unittest.TestCase):
    def setUp(self):
        self._evidence_guard = _install_evidence_inspection_guard()

    def tearDown(self):
        _restore_evidence_inspection_guard(self._evidence_guard)
        self.assertFalse(PROBE.exists())

    def test_existing_output_directory_refused(self):
        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            root = Path(directory)
            run_root = root / "surrogate-runs"
            run_root.mkdir()
            existing = run_root / "empty-run"
            existing.mkdir()
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.validate_output_containment(existing, run_root)
            self.assertEqual(ctx.exception.code, "output_directory_exists")
            self.assertEqual(list(existing.iterdir()), [])
            nonempty = run_root / "nonempty-run"
            nonempty.mkdir()
            (nonempty / "kept.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.validate_output_containment(nonempty, run_root)
            self.assertEqual(ctx.exception.code, "output_directory_exists")
            self.assertEqual((nonempty / "kept.txt").read_text(encoding="utf-8"), "keep")
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.validate_output_containment(RUNS_ROOT, null_model.PRODUCTION_RUN_ROOT)
        self.assertEqual(ctx.exception.code, "output_not_a_child")

    def test_output_outside_run_root_refused(self):
        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            root = Path(directory)
            run_root = root / "surrogate-runs"
            run_root.mkdir()
            outside = root / "not-a-run"
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.validate_output_containment(outside, run_root)
            self.assertEqual(ctx.exception.code, "output_not_a_child")
            self.assertFalse(outside.exists())
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.validate_output_containment(run_root, run_root)
            self.assertEqual(ctx.exception.code, "output_not_a_child")
            escaped = run_root / ".." / "escaped-run"
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.validate_output_containment(escaped, run_root)
            self.assertEqual(ctx.exception.code, "output_path_escapes_root")
            self.assertFalse((root / "escaped-run").exists())
            outside_dir = root / "outside"
            outside_dir.mkdir()
            link = run_root / "linked-parent"
            link.symlink_to(outside_dir, target_is_directory=True)
            candidate = link / "child-run"
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.validate_output_containment(candidate, run_root)
            self.assertEqual(ctx.exception.code, "output_symlink_escape")
            self.assertFalse((outside_dir / "child-run").exists())

    def test_cli_exposes_only_output_dir_and_help(self):
        help_buffer = io.StringIO()
        with contextlib.redirect_stdout(help_buffer):
            with self.assertRaises(SystemExit) as ctx:
                null_model.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        help_text = help_buffer.getvalue()
        self.assertIn("--output-dir", help_text)
        self.assertIn("--help", help_text)
        self.assertNotIn("--repo-root", help_text)
        self.assertNotIn("--config", help_text)
        self.assertNotIn("--input", help_text)
        self.assertNotIn("--authoris", help_text)
        self.assertNotIn("--authoriz", help_text)
        signature = inspect.signature(null_model.run_b2_production)
        self.assertEqual(list(signature.parameters), ["output_dir", "command"])
        source = inspect.getsource(null_model.main)
        self.assertNotIn("execute_test_only_synthetic", source)
        self.assertNotIn("os.environ", source)

    def test_removed_cli_flags_are_rejected_without_opening_files(self):
        opened = []
        original = Path.read_bytes

        def spy(path_self):
            opened.append(str(path_self))
            return original(path_self)

        Path.read_bytes = spy
        try:
            with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
                output = str(Path(directory) / "would-be-run")
                for extra in (
                    ["--repo-root", "/tmp/not-a-repo"],
                    ["--config", str(Path(directory) / "other.yaml")],
                    ["--input", str(Path(directory) / "other.txt")],
                ):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as ctx:
                            null_model.main(["--output-dir", output] + extra)
                    self.assertEqual(ctx.exception.code, 2)
                    self.assertFalse(Path(output).exists())
        finally:
            Path.read_bytes = original
        self.assertEqual(opened, [])

    def test_repository_config_fails_before_contract_train_or_output(self):
        """A non-executable config stops before contract, TRAIN, or output work.

        The refusal uses an explicit in-memory configuration. It does not
        assume the repository B2 file is non-executable.
        """
        config_path = _repository_b2_config_path()
        non_executable = _non_executable_config()
        self.assertIs(non_executable["consumable_by_executable_workflow"], False)
        self.assertEqual(
            non_executable["document_status"],
            "APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION",
        )
        self.assertIs(non_executable["execution"]["authorised"], False)
        events = []
        parsed = {"count": 0}
        real_read = Path.read_bytes
        real_lstat = os.lstat
        real_load = null_model.load_b2_config_bytes
        real_validate = null_model.validate_output_containment
        real_mkdir = os.mkdir
        validated = {"count": 0}
        created = {"count": 0}

        def read_spy(path_self):
            events.append(("read", os.path.normpath(str(path_self))))
            return _refuse_biological_read(path_self, real_read, [])

        def lstat_spy(path):
            text = os.path.normpath(os.fspath(path))
            events.append(("lstat", text))
            _refuse_completed_evidence_access(text)
            return real_lstat(path)

        def load_spy(raw):
            parsed["count"] += 1
            parsed["saw_repository_bytes"] = raw == config_path.read_bytes()
            return non_executable

        def validate_spy(path, run_root):
            validated["count"] += 1
            return real_validate(path, run_root)

        def mkdir_spy(path, mode=0o777):
            created["count"] += 1
            raise AssertionError("directory creation was attempted")

        Path.read_bytes = read_spy
        os.lstat = lstat_spy
        null_model.load_b2_config_bytes = load_spy
        null_model.validate_output_containment = validate_spy
        previous = os.environ.get("M4_STAGE2A_TEST_ONLY")
        os.environ["M4_STAGE2A_TEST_ONLY"] = "1"
        try:
            with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
                os.mkdir = mkdir_spy
                output = Path(directory) / "would-be-run"
                stderr = io.StringIO()
                with self.assertRaises(null_model.NullModelError) as ctx:
                    null_model.run_b2_production(str(output))
                self.assertEqual(ctx.exception.code, "execution_not_authorised")
                self.assertIn("consumable_by_executable_workflow=False", ctx.exception.detail)
                self.assertIn(
                    "document_status=APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION",
                    ctx.exception.detail,
                )
                self.assertFalse(output.exists())
                with contextlib.redirect_stderr(stderr):
                    code = null_model.main(["--output-dir", str(output)])
                self.assertEqual(code, 1)
                self.assertFalse(output.exists())
                self.assertNotIn(SECRET, stderr.getvalue())
                self.assertFalse(Path(AUTHORISATION_TEST_SIBLING).exists())
                with self.assertRaises(null_model.NullModelError) as sibling_ctx:
                    null_model.run_b2_production(AUTHORISATION_TEST_SIBLING)
                self.assertEqual(sibling_ctx.exception.code, "execution_not_authorised")
                self.assertFalse(Path(AUTHORISATION_TEST_SIBLING).exists())
        finally:
            Path.read_bytes = real_read
            os.lstat = real_lstat
            null_model.load_b2_config_bytes = real_load
            null_model.validate_output_containment = real_validate
            os.mkdir = real_mkdir
            if previous is None:
                os.environ.pop("M4_STAGE2A_TEST_ONLY", None)
            else:
                os.environ["M4_STAGE2A_TEST_ONLY"] = previous
        self.assertGreaterEqual(parsed["count"], 1)
        self.assertIs(parsed["saw_repository_bytes"], True)
        self.assertEqual(validated["count"], 0)
        self.assertEqual(created["count"], 0)
        config_norm = os.path.normpath(str(config_path))
        contract_norm = os.path.normpath(
            str(ROOT / "config" / "modelling" / "frozen_data_contract.json")
        )
        lstat_at = [
            index
            for index, (kind, path) in enumerate(events)
            if kind == "lstat" and path == config_norm
        ]
        read_at = [
            index
            for index, (kind, path) in enumerate(events)
            if kind == "read" and path == config_norm
        ]
        self.assertTrue(lstat_at)
        self.assertTrue(read_at)
        self.assertLess(lstat_at[0], read_at[0])
        self.assertFalse(any(path == contract_norm and kind == "read" for kind, path in events))
        self.assertFalse(any(path.endswith("corpus_final.txt") for _kind, path in events))
        self.assertFalse(any("rnagenesis-mres-data" in path for _kind, path in events))

    def test_repository_b2_configuration_execution_state_is_consistent(self):
        """Execution is closed. Attempt 2 is the accepted formal B2 evidence.

        Evidence paths, hashes, byte counts, and revocation structure come from the parsed YAML only.
        This test does not inspect either real evidence directory.
        """
        loaded, text = _load_repository_b2_config()
        self.assertNotIn("scientific_execution_authorisation", loaded)
        self.assertEqual(
            _execution_gates(loaded),
            (
                "APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION",
                False,
                False,
            ),
        )
        self.assertFalse(_gates_are_open(loaded))
        self.assertTrue(_gates_are_closed(loaded))
        self.assertNotIn("authorisation_active: true", text)
        self.assertNotIn("activation_status: active_single_run", text)
        self.assertNotIn("document_status: APPROVED_FOR_SCIENTIFIC_EXECUTION", text)
        self.assertNotIn("consumable_by_executable_workflow: true", text)
        self.assertNotIn("authorised: true", text)
        self.assertIs(loaded["human_approval"]["m4_complete"], False)
        self.assertIs(loaded["stage_2a_correction"]["success_claimed"], False)
        self.assertIs(loaded["stage_2a_correction"]["m4_complete"], False)
        self.assertIs(loaded["stage_2a_correction"]["execution_authorised"], False)
        self.assertEqual(loaded["stage_2a_correction"]["first_implementation"], "failed_review")
        self.assertEqual(loaded["stage_2a_correction"]["corrected_implementation"], "under_review")
        self.assertIs(loaded["execution"]["evidence_directory_created_by_this_stage"], True)
        self.assertEqual(
            loaded["execution"]["evidence_directory_created_by_this_stage_refers_to"],
            "completed_first_invocation",
        )
        self.assertIs(loaded["execution"]["attempt2_output_directory_created"], True)
        self.assertEqual(
            loaded["execution"]["attempt2_output_directory"],
            ATTEMPT2_OUTPUT_DIRECTORY,
        )
        self.assertIn(
            "evidence_directory_created_by_this_stage refers to the completed first",
            loaded["execution"]["runner_gate"],
        )
        self.assertIn("Those execution gates are closed.", loaded["execution"]["runner_gate"])
        self.assertIn(
            "There is no active scientific_execution_authorisation.",
            loaded["execution"]["runner_gate"],
        )
        self.assertNotIn(
            "The attempt-2 directory has not been created",
            loaded["execution"]["runner_gate"],
        )
        self.assertEqual(loaded["sampler"]["seed"], 42)
        self.assertEqual(loaded["sampler"]["proposed_seed"], 42)
        self.assertEqual(loaded["sampler"]["raw_sequence_count"], 30000)
        self.assertEqual(loaded["sampler"]["numpy_generator"], "numpy.random.default_rng")
        self.assertEqual(
            loaded["input"]["expected_sha256"],
            "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d",
        )
        self.assertEqual(loaded["input"]["expected_sequence_count"], 669)
        self.assertEqual(loaded["input"]["expected_unique_count"], 669)
        self.assertEqual(loaded["input"]["alphabet"], "^[ACGU]+$")
        self.assertEqual(
            loaded["condition_manifest_label"],
            "B2_train_matched_empirical_null",
        )
        self.assertEqual(text.count(ONE_RUN_OUTPUT_DIRECTORY), 3)
        self.assertEqual(text.count(ATTEMPT2_OUTPUT_DIRECTORY), 4)
        self.assertNotIn("success_claimed: true", text)
        self.assertNotIn("m4_complete: true", text)
        self.assertIn("b2_condition_complete: true", text)
        _assert_every_m4_complete_is_false(self, loaded)
        archived_records = loaded["prior_scientific_execution_authorisations"]
        self.assertEqual(len(archived_records), 2)
        archived = archived_records[0]
        expected_archived = dict(ONE_RUN_AUTHORISATION)
        expected_archived["authorisation_active"] = False
        expected_archived["activation_status"] = "revoked_after_completed_single_invocation"
        expected_archived["revocation_recorded_timestamp"] = "2026-09-29T18:40:21+10:00"
        expected_archived["single_invocation_consumed"] = True
        expected_archived["reuse_of_same_authorisation_prohibited"] = True
        expected_archived["reuse_of_same_output_directory_prohibited"] = True
        self.assertEqual(archived, expected_archived)
        self.assertRegex(
            archived["revocation_recorded_timestamp"],
            REVOCATION_TIMESTAMP_PATTERN,
        )
        self.assertNotEqual(
            archived["revocation_recorded_timestamp"],
            archived["activation_recorded_timestamp"],
        )
        self.assertIs(archived["authorisation_active"], False)
        self.assertIs(archived["single_invocation_consumed"], True)
        self.assertIs(archived["reuse_of_same_authorisation_prohibited"], True)
        self.assertIs(archived["reuse_of_same_output_directory_prohibited"], True)
        self.assertEqual(archived["authorisation_id"], "m4_b2_empirical_null_2d9ec89_attempt1")
        self.assertEqual(
            archived["executing_implementation_commit"],
            "70f950434501964dd179760aa4fc82766df74289",
        )
        self.assertEqual(archived["output_directory"], ONE_RUN_OUTPUT_DIRECTORY)
        self.assertEqual(archived["seed"], 42)
        self.assertIs(archived["success_claimed"], False)
        self.assertIs(archived["m4_complete"], False)
        attempt2 = archived_records[1]
        preserved_attempt2 = {
            "authorisation_id": ATTEMPT2_AUTHORISATION_ID,
            "authorisation_active": True,
            "activation_status": "active_single_run",
            "activation_recorded_timestamp": "2026-09-29T22:43:52+10:00",
            "intended_scope_approval": (
                "Laura Hardy approved this one-run scope on 29 September 2026. "
                "That approval authorizes one CPU-only corrected-manifest B2 reproducibility "
                "run at the named output directory. The executing implementation commit "
                "is 6f82878a7bbde78c74f91181c672d2d4df74b5cc. Seed 42 is deliberately "
                "reused to test deterministic reproduction of the first run. This is not "
                "an additional stochastic seed or independent replicate. It does not "
                "claim that the run succeeded and does not complete M4.\n"
            ),
            "approved_by": "Laura Hardy",
            "approval_date": "29 September 2026",
            "approval_recorded_timestamp": "2026-09-29T22:43:52+10:00",
            "approval_source": (
                "explicit human decision in the M4 review chat to fix the manifest "
                "and perform a new run"
            ),
            "scope": "one CPU-only corrected-manifest B2 reproducibility run",
            "executing_implementation_commit": ATTEMPT2_IMPLEMENTATION_COMMIT,
            "branch": "main",
            "condition": "B2_train_matched_empirical_null",
            "output_directory": ATTEMPT2_OUTPUT_DIRECTORY,
            "train_text_path": (
                "/home/laura/rnagenesis-mres-data/development/corpus_final.txt"
            ),
            "train_text_sha256": (
                "d6cbc41a36b4a83e393e5593598a2bda246bc6e9df151d236381885734e05c9d"
            ),
            "expected_records": 669,
            "expected_unique_records": 669,
            "alphabet": "^[ACGU]+$",
            "raw_attempt_count": 30000,
            "seed": 42,
            "rng": "numpy.random.default_rng",
            "device": "CPU only",
            "gpu_use": "prohibited",
            "model_loading": "prohibited",
            "ref_access": "prohibited",
            "eval_access": "prohibited",
            "overwrite_or_append": "prohibited",
            "single_run_only": True,
            "revoke_after_completed_or_failed_invocation": True,
            "second_attempt_requires_new_directory_and_new_human_authorisation": True,
            "success_claimed": False,
            "m4_complete": False,
        }
        expected_attempt2 = dict(preserved_attempt2)
        expected_attempt2["authorisation_active"] = False
        expected_attempt2["activation_status"] = "revoked_after_completed_single_invocation"
        expected_attempt2["revocation_recorded_timestamp"] = ATTEMPT2_REVOCATION_TIMESTAMP
        expected_attempt2["single_invocation_consumed"] = True
        expected_attempt2["reuse_of_same_authorisation_prohibited"] = True
        expected_attempt2["reuse_of_same_output_directory_prohibited"] = True
        self.assertEqual(attempt2, expected_attempt2)
        for revoked in (archived, attempt2):
            self.assertIs(revoked["authorisation_active"], False)
            self.assertEqual(
                revoked["activation_status"],
                "revoked_after_completed_single_invocation",
            )
            self.assertRegex(revoked["revocation_recorded_timestamp"], REVOCATION_TIMESTAMP_PATTERN)
            self.assertNotEqual(
                revoked["revocation_recorded_timestamp"],
                revoked["activation_recorded_timestamp"],
            )
            self.assertIs(revoked["single_invocation_consumed"], True)
            self.assertIs(revoked["reuse_of_same_authorisation_prohibited"], True)
            self.assertIs(revoked["reuse_of_same_output_directory_prohibited"], True)
            self.assertIs(revoked["success_claimed"], False)
            self.assertIs(revoked["m4_complete"], False)
            self.assertEqual(revoked["seed"], 42)
        self.assertNotEqual(attempt2["authorisation_id"], archived["authorisation_id"])
        self.assertNotEqual(attempt2["output_directory"], archived["output_directory"])
        self.assertEqual(attempt2["executing_implementation_commit"], ATTEMPT2_IMPLEMENTATION_COMMIT)
        self.assertEqual(attempt2["approval_recorded_timestamp"], "2026-09-29T22:43:52+10:00")
        self.assertEqual(attempt2["activation_recorded_timestamp"], "2026-09-29T22:43:52+10:00")
        executable_keys = set(null_model.SCIENTIFIC_EXECUTION_AUTHORISATION_KEYS)
        self.assertEqual(
            set(attempt2) - executable_keys,
            set(REVOCATION_ONLY_AUTHORISATION_KEYS),
        )
        comparison = loaded["reproducibility_comparison"]
        self.assertEqual(comparison["seed"], 42)
        self.assertIn("deliberately reused", comparison["seed_reuse_meaning"])
        self.assertIn("not an additional stochastic seed", comparison["seed_reuse_meaning"])
        self.assertIn("independent replicate", comparison["seed_reuse_meaning"])
        self.assertEqual(comparison["expected_prior_raw_sha256"], PRIOR_RAW_SHA256)
        self.assertIn("must match this hash exactly", comparison["decision_rule"])
        self.assertIn(
            "stop without accepting either run",
            comparison["decision_rule"],
        )
        self.assertIs(comparison["new_manifest_hash_expected_to_differ"], True)
        self.assertIn(
            "schema and authorization provenance are corrected",
            comparison["new_manifest_hash_difference_reason"],
        )
        self.assertNotIn("expected_prior_raw_sha256", attempt2)
        invocation = loaded["completed_invocation"]
        self.assertEqual(
            invocation,
            {
                "invocation_status": "completed_exit_0",
                "evidence_acceptance_status": (
                    "superseded_as_evidence_package_raw_output_remains_valid"
                ),
                "manifest_review_status": "provenance_defect_found",
                "success_claimed": False,
                "m4_complete": False,
                "authorization_commit": "cc5d6f612164fb3da717d0f68b9904046614b77f",
                "executing_implementation_commit": (
                    "70f950434501964dd179760aa4fc82766df74289"
                ),
                "run_identifier": "m4_b2_empirical_null_2d9ec89_attempt1",
                "attempt_identifier": "invocation-0",
                "local_start": "2026-09-29T18:28:53.237801+10:00",
                "local_end": "2026-09-29T18:28:54.416348+10:00",
                "exit_status": 0,
                "requested_count": 30000,
                "raw_count": 30000,
                "retained_count": 30000,
                "unique_diagnostic_count": 30000,
                "dropped_count": 0,
                "raw_evidence_path": (
                    ONE_RUN_OUTPUT_DIRECTORY + "/b2_empirical_null_raw.jsonl"
                ),
                "raw_evidence_byte_count": 6787972,
                "raw_evidence_sha256": (
                    "bbe35f448db0d7fc02ad0156865798382b0b41e9ad047b4e52eddf7cff740c83"
                ),
                "manifest_path": ONE_RUN_OUTPUT_DIRECTORY + "/manifest.json",
                "manifest_byte_count": 9001,
                "manifest_sha256": (
                    "5c25568a08e2b0b1ec8f30c940755bcad3426115b7d1bb327acc1ce55aa8ccf2"
                ),
                "device_backend": "cpu_numpy",
                "gpu_api_invoked": False,
                "ref_opened": False,
                "eval_opened": False,
                "repository_clean_during_execution": True,
                "manifest_provenance_defect": MANIFEST_PROVENANCE_DEFECT,
                "evidence_package_disposition": "superseded_by_attempt_2",
                "supersession_reason": (
                    "legacy manifest omitted the active scientific-execution "
                    "authorization and retained misleading Stage 1 approval metadata"
                ),
                "raw_scientific_output_remains_valid": True,
                "raw_scientific_output_byte_identical_to_accepted_attempt2": True,
                "original_evidence_remains_immutable_and_retained": True,
                "selected_as_formal_b2_evidence_package": False,
            },
        )
        self.assertIs(invocation["success_claimed"], False)
        self.assertIs(invocation["m4_complete"], False)
        self.assertIs(invocation["raw_scientific_output_remains_valid"], True)
        self.assertIs(invocation["selected_as_formal_b2_evidence_package"], False)
        self.assertNotIn("scientifically invalid", invocation["manifest_provenance_defect"])
        self.assertNotIn("invalid", invocation["supersession_reason"])
        attempt2_invocation = loaded["completed_invocation_attempt2"]
        self.assertEqual(
            attempt2_invocation,
            {
                "invocation_status": "completed_exit_0",
                "success_claimed": False,
                "m4_complete": False,
                "run_identifier": ATTEMPT2_AUTHORISATION_ID,
                "attempt_identifier": "invocation-0",
                "local_start": ATTEMPT2_LOCAL_START,
                "local_end": ATTEMPT2_LOCAL_END,
                "authorization_commit": ATTEMPT2_AUTHORIZATION_COMMIT,
                "executing_implementation_commit": ATTEMPT2_IMPLEMENTATION_COMMIT,
                "manifest_schema_version": ATTEMPT2_MANIFEST_SCHEMA,
                "exit_status": 0,
                "requested_count": 30000,
                "raw_count": 30000,
                "retained_count": 30000,
                "unique_diagnostic_count": 30000,
                "dropped_count": 0,
                "raw_evidence_path": (
                    ATTEMPT2_OUTPUT_DIRECTORY + "/b2_empirical_null_raw.jsonl"
                ),
                "raw_evidence_byte_count": ATTEMPT2_RAW_BYTES,
                "raw_evidence_sha256": PRIOR_RAW_SHA256,
                "manifest_path": ATTEMPT2_OUTPUT_DIRECTORY + "/manifest.json",
                "manifest_byte_count": ATTEMPT2_MANIFEST_BYTES,
                "manifest_sha256": ATTEMPT2_MANIFEST_SHA256,
                "device_backend": "cpu_numpy",
                "gpu_api_invoked": False,
                "ref_opened": False,
                "eval_opened": False,
                "repository_clean_during_execution": True,
                "warnings": [],
                "retries": [],
                "deviations": [],
                "raw_byte_identical_to_attempt1": True,
                "prior_raw_sha256_matched": True,
            },
        )
        self.assertIs(attempt2_invocation["raw_byte_identical_to_attempt1"], True)
        self.assertIs(attempt2_invocation["prior_raw_sha256_matched"], True)
        self.assertEqual(attempt2_invocation["raw_evidence_sha256"], invocation["raw_evidence_sha256"])
        self.assertNotEqual(
            attempt2_invocation["manifest_sha256"],
            invocation["manifest_sha256"],
        )
        self.assertEqual(attempt2_invocation["manifest_schema_version"], "m4-b2-run-manifest-2")
        acceptance = loaded["b2_evidence_acceptance"]
        self.assertEqual(
            acceptance,
            {
                "status": "accepted",
                "accepted_by": "Laura Hardy",
                "acceptance_date": "29 September 2026",
                "acceptance_recorded_timestamp": B2_ACCEPTANCE_TIMESTAMP,
                "acceptance_source": "explicit human approval in the M4 review chat",
                "accepted_run": "attempt 2",
                "accepted_authorisation_id": ATTEMPT2_AUTHORISATION_ID,
                "accepted_raw_sha256": PRIOR_RAW_SHA256,
                "accepted_manifest_sha256": ATTEMPT2_MANIFEST_SHA256,
                "deterministic_reproduction_of_attempt1": "passed",
                "raw_files_byte_identical": True,
                "corrected_authorization_provenance": "passed",
                "b2_condition_complete": True,
                "m4_complete": False,
            },
        )
        self.assertIs(acceptance["b2_condition_complete"], True)
        self.assertIs(acceptance["m4_complete"], False)
        self.assertEqual(acceptance["accepted_run"], "attempt 2")
        self.assertNotEqual(acceptance["accepted_authorisation_id"], invocation["run_identifier"])
        self.assertRegex(acceptance["acceptance_recorded_timestamp"], REVOCATION_TIMESTAMP_PATTERN)

    def _assert_repository_invocation_avoids_evidence(self, result):
        self.assertIsNotNone(result["error"])
        self.assertEqual(result["created"], 0)
        self.assertFalse(any(_is_completed_evidence_path(path) for path in result["events"]))
        self.assertFalse(any(path.endswith("corpus_final.txt") for path in result["events"]))
        self.assertFalse(any("rnagenesis-mres-data" in path for path in result["events"]))
        self.assertFalse(
            any(path.endswith("frozen_data_contract.json") for path in result["events"])
        )
        self.assertFalse(
            any(
                path.endswith("ref.csv")
                or path.endswith("eval.csv")
                or path.endswith(".pt")
                or path.endswith(".bin")
                or path.endswith(".safetensors")
                or "checkpoint" in path
                for path in result["events"]
            )
        )

    def test_closed_repository_refuses_former_output_paths_before_contract(self):
        """Closed gates refuse both consumed directories before contract or creation."""
        loaded, _text = _load_repository_b2_config()
        self.assertTrue(_gates_are_closed(loaded))
        self.assertNotIn("scientific_execution_authorisation", loaded)
        archived = loaded["prior_scientific_execution_authorisations"]
        self.assertEqual(
            [record["output_directory"] for record in archived],
            [ONE_RUN_OUTPUT_DIRECTORY, ATTEMPT2_OUTPUT_DIRECTORY],
        )
        for output in (
            ATTEMPT2_OUTPUT_DIRECTORY,
            ONE_RUN_OUTPUT_DIRECTORY,
            AUTHORISATION_TEST_SIBLING,
        ):
            result = _invoke_guarded_production(
                output,
                loaded,
                intercept_contract=True,
                record_containment_only=True,
            )
            self.assertEqual(result["error"].code, "execution_not_authorised", output)
            self.assertIn("consumable_by_executable_workflow=False", result["error"].detail)
            self.assertIn(
                "document_status=APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION",
                result["error"].detail,
            )
            self.assertEqual(result["contract_attempts"], 0, output)
            self.assertEqual(result["created"], 0, output)
            self.assertEqual(result["containment"], [], output)
            self._assert_repository_invocation_avoids_evidence(result)
        self.assertFalse(Path(AUTHORISATION_TEST_SIBLING).exists())

    def test_closed_repository_file_refuses_before_contract_train_evidence_or_writes(self):
        """The repository file itself stops before contract, TRAIN, evidence, or writes."""
        loaded, _text = _load_repository_b2_config()
        self.assertTrue(_gates_are_closed(loaded))
        events = []
        created = {"count": 0}
        real_read = Path.read_bytes
        real_mkdir = os.mkdir
        real_create = null_model.create_output_directory
        real_write = null_model.exclusive_fsync_write
        real_open = null_model._open_verified_contract
        real_resolve = null_model.resolve_fixed_repository_file

        def read_spy(path_self):
            text = os.path.normpath(str(path_self))
            events.append(text)
            if text.endswith("corpus_final.txt") or "rnagenesis-mres-data" in text:
                raise AssertionError("biological TRAIN_TEXT was opened")
            if text.endswith("frozen_data_contract.json"):
                raise AssertionError("frozen contract was opened")
            if text.endswith("ref.csv") or text.endswith("eval.csv"):
                raise AssertionError("REF or EVAL was opened")
            if text.endswith(".pt") or text.endswith(".bin") or text.endswith(".safetensors"):
                raise AssertionError("model checkpoint was opened")
            if "checkpoint" in text:
                raise AssertionError("checkpoint path was opened")
            _refuse_completed_evidence_access(text)
            return real_read(path_self)

        def mkdir_spy(path, mode=0o777):
            created["count"] += 1
            raise AssertionError("directory creation was attempted")

        def create_spy(_path):
            created["count"] += 1
            raise AssertionError("directory creation was attempted")

        def write_spy(*_args, **_kwargs):
            raise AssertionError("output write was attempted")

        def open_spy(*_args, **_kwargs):
            raise AssertionError("frozen contract was opened")

        def resolve_spy(root, relative, role):
            if role == "contract":
                raise AssertionError("frozen contract resolve was attempted")
            return real_resolve(root, relative, role)

        Path.read_bytes = read_spy
        null_model.create_output_directory = create_spy
        null_model.exclusive_fsync_write = write_spy
        null_model._open_verified_contract = open_spy
        null_model.resolve_fixed_repository_file = resolve_spy
        try:
            with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
                os.mkdir = mkdir_spy
                output = Path(directory) / "would-be-run"
                try:
                    for candidate in (
                        str(output),
                        ATTEMPT2_OUTPUT_DIRECTORY,
                        ONE_RUN_OUTPUT_DIRECTORY,
                        AUTHORISATION_TEST_SIBLING,
                    ):
                        with self.assertRaises(null_model.NullModelError) as ctx:
                            null_model.run_b2_production(candidate)
                        self.assertEqual(ctx.exception.code, "execution_not_authorised")
                        self.assertIn(
                            "consumable_by_executable_workflow=False",
                            ctx.exception.detail,
                        )
                        self.assertFalse(output.exists())
                finally:
                    os.mkdir = real_mkdir
        finally:
            Path.read_bytes = real_read
            os.mkdir = real_mkdir
            null_model.create_output_directory = real_create
            null_model.exclusive_fsync_write = real_write
            null_model._open_verified_contract = real_open
            null_model.resolve_fixed_repository_file = real_resolve
        self.assertEqual(created["count"], 0)
        self.assertFalse(any(_is_completed_evidence_path(path) for path in events))
        self.assertFalse(any(path.endswith("corpus_final.txt") for path in events))
        self.assertFalse(any("rnagenesis-mres-data" in path for path in events))
        self.assertFalse(any(path.endswith("frozen_data_contract.json") for path in events))
        self.assertFalse(Path(AUTHORISATION_TEST_SIBLING).exists())

    def test_revoked_archived_authorisations_cannot_be_executed(self):
        """Consumed archived blocks stay non-executable, including after an in-memory reopen."""
        loaded, _text = _load_repository_b2_config()
        self.assertNotIn("scientific_execution_authorisation", loaded)
        archived_records = loaded["prior_scientific_execution_authorisations"]
        self.assertEqual(len(archived_records), 2)
        self.assertNotEqual(
            archived_records[0]["authorisation_id"],
            archived_records[1]["authorisation_id"],
        )
        self.assertNotEqual(
            archived_records[0]["output_directory"],
            archived_records[1]["output_directory"],
        )
        for archived in archived_records:
            consumed = copy.deepcopy(loaded)
            consumed["scientific_execution_authorisation"] = copy.deepcopy(archived)
            result = _invoke_guarded_production(
                archived["output_directory"],
                consumed,
                record_containment_only=True,
            )
            self.assertEqual(result["error"].code, "execution_not_authorised")
            self.assertEqual(result["contract_attempts"], 0)
            self.assertEqual(result["containment"], [])
            self.assertEqual(result["created"], 0)
            self._assert_repository_invocation_avoids_evidence(result)
            reopened = copy.deepcopy(loaded)
            reopened["document_status"] = "APPROVED_FOR_SCIENTIFIC_EXECUTION"
            reopened["consumable_by_executable_workflow"] = True
            reopened["execution"]["authorised"] = True
            reopened["scientific_execution_authorisation"] = copy.deepcopy(archived)
            inactive_result = _invoke_guarded_production(
                AUTHORISATION_TEST_OUTPUT,
                reopened,
                record_containment_only=True,
            )
            self.assertEqual(inactive_result["error"].code, "execution_not_authorised")
            self.assertIn("authorisation_active is not true", inactive_result["error"].detail)
            self.assertEqual(inactive_result["contract_attempts"], 0)
            self.assertEqual(inactive_result["created"], 0)
            self._assert_repository_invocation_avoids_evidence(inactive_result)
            reactivated = copy.deepcopy(archived)
            reactivated["authorisation_active"] = True
            reactivated["activation_status"] = "active_single_run"
            schema_config = copy.deepcopy(reopened)
            schema_config["scientific_execution_authorisation"] = reactivated
            schema_result = _invoke_guarded_production(
                archived["output_directory"],
                schema_config,
                record_containment_only=True,
            )
            self.assertEqual(schema_result["error"].code, "execution_not_authorised")
            self.assertIn("executable schema", schema_result["error"].detail)
            self.assertEqual(schema_result["contract_attempts"], 0)
            self.assertEqual(schema_result["created"], 0)
            self._assert_repository_invocation_avoids_evidence(schema_result)

    def test_later_revocation_closes_attempt2_without_evidence_directories(self):
        """Revoking an otherwise open authorization does not inspect evidence directories."""
        loaded, _text = _load_repository_b2_config()
        self.assertTrue(_gates_are_closed(loaded))
        closed_result = _invoke_guarded_production(
            ATTEMPT2_OUTPUT_DIRECTORY,
            loaded,
            record_containment_only=True,
        )
        self.assertEqual(closed_result["error"].code, "execution_not_authorised")
        self.assertIn("consumable_by_executable_workflow=False", closed_result["error"].detail)
        self.assertEqual(closed_result["contract_attempts"], 0)
        self.assertEqual(closed_result["containment"], [])
        self._assert_repository_invocation_avoids_evidence(closed_result)
        inactive = _authorised_production_config()
        inactive["scientific_execution_authorisation"]["authorisation_active"] = False
        inactive["scientific_execution_authorisation"]["activation_status"] = (
            "revoked_after_completed_single_invocation"
        )
        inactive_result = _invoke_guarded_production(
            AUTHORISATION_TEST_OUTPUT,
            inactive,
            record_containment_only=True,
        )
        self.assertEqual(inactive_result["error"].code, "execution_not_authorised")
        self.assertEqual(inactive_result["contract_attempts"], 0)
        self.assertEqual(inactive_result["containment"], [])
        self.assertIs(inactive["scientific_execution_authorisation"]["success_claimed"], False)
        self.assertIs(inactive["scientific_execution_authorisation"]["m4_complete"], False)
        self._assert_repository_invocation_avoids_evidence(inactive_result)

    def _assert_stopped_before_biological_access(self, result):
        self.assertIsNotNone(result["error"])
        self.assertEqual(result["created"], 0)
        self.assertFalse(any(path.endswith("corpus_final.txt") for path in result["events"]))
        self.assertFalse(any("rnagenesis-mres-data" in path for path in result["events"]))
        self.assertFalse(any(path.endswith("frozen_data_contract.json") for path in result["events"]))
        self.assertFalse(
            any(path.endswith("ref.csv") or path.endswith("eval.csv") for path in result["events"])
        )
        self.assertFalse(Path(AUTHORISATION_TEST_OUTPUT).exists())
        self.assertFalse(Path(AUTHORISATION_TEST_SIBLING).exists())
        self.assertFalse(any(_is_completed_evidence_path(path) for path in result["events"]))

    def test_authorised_config_rejects_sibling_before_biological_access(self):
        """A different run-root child is output_not_authorised before any write."""
        self.assertFalse(Path(AUTHORISATION_TEST_SIBLING).exists())
        self.assertFalse(Path(AUTHORISATION_TEST_OUTPUT).exists())
        result = _invoke_guarded_production(
            AUTHORISATION_TEST_SIBLING,
            _authorised_production_config(),
        )
        self.assertEqual(result["error"].code, "output_not_authorised")
        self.assertEqual(result["contract_attempts"], 0)
        self._assert_stopped_before_biological_access(result)
        roots = {root for _path, root in result["containment"]}
        self.assertEqual(roots, {os.path.normpath(str(null_model.PRODUCTION_RUN_ROOT))})
        contained = [path for path, _root in result["containment"]]
        self.assertIn(os.path.normpath(AUTHORISATION_TEST_OUTPUT), contained)
        self.assertIn(os.path.normpath(AUTHORISATION_TEST_SIBLING), contained)

    def test_authorised_config_rejects_output_outside_run_root_before_biological_access(self):
        outside = "/tmp/m4-b2-authorisation-outside-must-not-exist"
        self.assertFalse(Path(outside).exists())
        self.assertFalse(null_model._is_relative_to(Path(outside), RUNS_ROOT))
        result = _invoke_guarded_production(outside, _authorised_production_config())
        self.assertEqual(result["error"].code, "output_not_a_child")
        self.assertEqual(result["contract_attempts"], 0)
        self._assert_stopped_before_biological_access(result)
        self.assertFalse(Path(outside).exists())
        roots = {root for _path, root in result["containment"]}
        self.assertEqual(roots, {os.path.normpath(str(null_model.PRODUCTION_RUN_ROOT))})

    def test_exact_authorised_output_stops_before_contract_train_or_creation(self):
        result = _invoke_guarded_production(
            AUTHORISATION_TEST_OUTPUT,
            _authorised_production_config(),
            intercept_contract=True,
        )
        self.assertEqual(result["error"].code, "intercepted_before_contract")
        self.assertEqual(result["contract_attempts"], 1)
        self._assert_stopped_before_biological_access(result)
        contained = [path for path, _root in result["containment"]]
        self.assertIn(os.path.normpath(AUTHORISATION_TEST_OUTPUT), contained)
        self.assertTrue(
            all(
                root == os.path.normpath(str(null_model.PRODUCTION_RUN_ROOT))
                for _path, root in result["containment"]
            )
        )

    def test_authorisation_mismatches_fail_before_biological_access(self):
        block_cases = (
            ("seed", 43),
            ("raw_attempt_count", 29999),
            ("train_text_sha256", "0" * 64),
            ("train_text_path", "/tmp/not-train-text.txt"),
            ("condition", "other_condition"),
            ("gpu_use", "allowed"),
            ("model_loading", "allowed"),
            ("ref_access", "allowed"),
            ("eval_access", "allowed"),
            ("device", "GPU"),
            ("overwrite_or_append", "allowed"),
            ("single_run_only", False),
            ("authorisation_active", False),
            ("success_claimed", True),
            ("m4_complete", True),
            ("rng", "random.Random"),
            ("alphabet", "^[ACGT]+$"),
            ("expected_records", 670),
            ("expected_unique_records", 668),
        )
        for key, value in block_cases:
            config = _authorised_production_config()
            config["scientific_execution_authorisation"][key] = value
            result = _invoke_guarded_production(AUTHORISATION_TEST_OUTPUT, config)
            self.assertEqual(result["error"].code, "execution_not_authorised", key)
            self.assertEqual(result["contract_attempts"], 0, key)
            self._assert_stopped_before_biological_access(result)
        config_cases = (
            ("sampler", "seed", 43, "production_parameters"),
            ("sampler", "raw_sequence_count", 10, "production_parameters"),
            ("input", "expected_sha256", "ab" * 32, "production_input_contract"),
            ("input", "expected_development_path", "/tmp/not-train-text.txt", "execution_not_authorised"),
            (None, "condition_manifest_label", "other_condition", "execution_not_authorised"),
        )
        for parent, key, value, code in config_cases:
            config = _authorised_production_config()
            if parent is None:
                config[key] = value
            else:
                config[parent][key] = value
            result = _invoke_guarded_production(AUTHORISATION_TEST_OUTPUT, config)
            self.assertEqual(result["error"].code, code, parent or key)
            self.assertEqual(result["contract_attempts"], 0, parent or key)
            self._assert_stopped_before_biological_access(result)

    def test_noncanonical_authorised_output_is_refused_before_biological_access(self):
        for output_directory in (
            AUTHORISATION_TEST_OUTPUT + "/",
            "m4_b2_authorisation_test_exact_must_not_exist",
            "/home/laura/rnagenesis-mres-runs/./m4_b2_authorisation_test_exact_must_not_exist",
        ):
            result = _invoke_guarded_production(
                AUTHORISATION_TEST_OUTPUT,
                _authorised_production_config(output_directory=output_directory),
            )
            self.assertEqual(result["error"].code, "output_not_authorised", output_directory)
            self.assertEqual(result["contract_attempts"], 0, output_directory)
            self._assert_stopped_before_biological_access(result)

    def test_fixed_config_identity_is_checked_before_open(self):
        events = []
        real_read = Path.read_bytes
        real_lstat = os.lstat

        def read_spy(path_self):
            events.append("read")
            return real_read(path_self)

        def lstat_spy(path):
            _refuse_completed_evidence_access(path)
            events.append("lstat")
            return real_lstat(path)

        Path.read_bytes = read_spy
        os.lstat = lstat_spy
        try:
            with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
                root = Path(directory)
                decoy = root / "other.yaml"
                decoy.write_text("consumable_by_executable_workflow: true\n", encoding="utf-8")
                events[:] = []
                with self.assertRaises(null_model.NullModelError) as ctx:
                    null_model.resolve_fixed_repository_file(root, Path("other.yaml"), "config")
                self.assertEqual(ctx.exception.code, "config_identity")
                self.assertEqual(events, [])
                self.assertEqual(decoy.read_text(encoding="utf-8"), "consumable_by_executable_workflow: true\n")
        finally:
            Path.read_bytes = real_read
            os.lstat = real_lstat

    def test_config_symlink_is_refused_before_open(self):
        events = []
        real_read = Path.read_bytes

        def read_spy(path_self):
            events.append(str(path_self))
            return real_read(path_self)

        Path.read_bytes = read_spy
        try:
            with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
                root = Path(directory)
                experiments = root / "config" / "experiments"
                experiments.mkdir(parents=True)
                real = experiments / "real.yaml"
                real.write_text(
                    "document_status: APPROVED_FOR_SCIENTIFIC_EXECUTION\n",
                    encoding="utf-8",
                )
                link = experiments / "B2_empirical_null.yaml"
                link.symlink_to(real)
                with self.assertRaises(null_model.NullModelError) as ctx:
                    null_model.resolve_fixed_repository_file(
                        root,
                        null_model.B2_CONFIG_RELATIVE,
                        "config",
                    )
                self.assertEqual(ctx.exception.code, "config_symlink")
        finally:
            Path.read_bytes = real_read
        self.assertEqual(events, [])

    def test_wrong_frozen_contract_hash_is_refused_before_train_open(self):
        opened = []
        real_read = Path.read_bytes

        def spy(path_self):
            opened.append(os.path.normpath(str(path_self)))
            return real_read(path_self)

        Path.read_bytes = spy
        try:
            with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
                root = Path(directory)
                fixture, _payload, _digest, run_root = _materialize(
                    root,
                    ["AC", "GU"],
                    attempt_count=2,
                    seed=1,
                    expected_contract_sha="0" * 64,
                )
                output = run_root / "bad-contract-hash"
                with self.assertRaises(null_model.NullModelError) as ctx:
                    null_model.execute_test_only_synthetic(fixture, output)
                self.assertEqual(ctx.exception.code, "frozen_contract_hash")
                self.assertFalse(output.exists())
        finally:
            Path.read_bytes = real_read
        self.assertFalse(any(path.endswith("synthetic_train.txt") for path in opened))

    def test_wrong_contract_id_role_or_train_hash_is_refused(self):
        cases = []

        def wrong_id(document):
            document["contract_id"] = "not-the-authorised-contract"

        def wrong_role(document):
            document["roles"]["TRAIN_TEXT"]["allowed"] = ["not_fit"]

        def wrong_hash(document):
            document["roles"]["TRAIN_TEXT"]["sha256"] = "ab" * 32

        def production_hash(document):
            document["roles"]["TRAIN_TEXT"]["sha256"] = null_model.TRAIN_TEXT_SHA256

        for name, mutate, code in (
            ("id", wrong_id, "frozen_contract_id"),
            ("role", wrong_role, "train_text_not_authorised_for_fitting"),
            ("hash", wrong_hash, "train_text_contract_hash"),
            ("production_hash", production_hash, "train_text_contract_hash"),
        ):
            cases.append((name, mutate, code))
        for _name, mutate, code in cases:
            with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
                root = Path(directory)
                opened = []
                real_read = Path.read_bytes

                def spy(path_self, opened=opened):
                    opened.append(os.path.normpath(str(path_self)))
                    return real_read(path_self)

                Path.read_bytes = spy
                try:
                    fixture, _payload, _digest, run_root = _materialize(
                        root,
                        ["AC", "GU"],
                        attempt_count=2,
                        seed=1,
                        mutate_contract=mutate,
                    )
                    output = run_root / "bad-contract"
                    with self.assertRaises(null_model.NullModelError) as ctx:
                        null_model.execute_test_only_synthetic(fixture, output)
                    self.assertEqual(ctx.exception.code, code)
                    self.assertFalse(output.exists())
                    self.assertFalse(any(path.endswith("synthetic_train.txt") for path in opened))
                finally:
                    Path.read_bytes = real_read

    def test_test_only_production_refusals_are_executed(self):
        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            root = Path(directory)
            fixture, payload, _digest, run_root = _materialize(
                root,
                ["ACGU", "UUAA"],
                attempt_count=2,
                seed=4,
            )
            output = run_root / "refused"
            development = Path(
                "/home/laura/rnagenesis-mres-data/development/m4-stage2a-must-not-exist.txt"
            )
            fixture.input_path = development
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.execute_test_only_synthetic(fixture, output)
            self.assertEqual(ctx.exception.code, "test_only_biological_input")
            self.assertIn("development root", ctx.exception.detail)
            self.assertFalse(development.exists())
            self.assertFalse(output.exists())

            fixture.input_path = BIOLOGICAL_TRAIN
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.execute_test_only_synthetic(fixture, output)
            self.assertEqual(ctx.exception.code, "test_only_biological_input")
            self.assertIn("production TRAIN_TEXT path", ctx.exception.detail)
            self.assertFalse(output.exists())

            fixture.input_path = root / "synthetic_train.txt"
            fixture.run_root = RUNS_ROOT
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.execute_test_only_synthetic(fixture, RUNS_ROOT / "m4-stage2a-must-not-be-created")
            self.assertEqual(ctx.exception.code, "test_only_production_run_root")
            self.assertFalse(PROBE.exists())

            fixture.run_root = run_root
            real_sha = null_model._sha256_bytes

            def fake_sha(data):
                if data == payload:
                    return null_model.TRAIN_TEXT_SHA256
                return real_sha(data)

            null_model._sha256_bytes = fake_sha
            try:
                with self.assertRaises(null_model.NullModelError) as ctx:
                    null_model.execute_test_only_synthetic(fixture, output)
                self.assertEqual(ctx.exception.code, "biological_hash_refused_in_test_only")
                self.assertFalse(output.exists())
            finally:
                null_model._sha256_bytes = real_sha
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.refuse_test_only_train_hash(null_model.TRAIN_TEXT_SHA256)
            self.assertEqual(ctx.exception.code, "biological_hash_refused_in_test_only")

    def test_surrogate_child_is_created_and_manifest_is_observed(self):
        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            root = Path(directory)
            fixture, _payload, digest, run_root = _materialize(
                root,
                PINNED_SMALL_SEQUENCES,
                attempt_count=4,
                seed=42,
            )
            output = run_root / "synthetic-success"
            self.assertFalse(output.exists())
            result = null_model.execute_test_only_synthetic(
                fixture,
                output,
                command="synthetic-test-only",
            )
            self.assertTrue(output.is_dir())
            self.assertEqual(result["retained_count"], 4)
            raw = (output / null_model.RAW_JSONL_FILENAME).read_bytes()
            self.assertEqual(raw, PINNED_SMALL_FIXTURE_JSONL)
            self.assertEqual(result["raw_sha256"], hashlib.sha256(raw).hexdigest())
            manifest_bytes = (output / "manifest.json").read_bytes()
            self.assertTrue(manifest_bytes.endswith(b"\n"))
            self.assertEqual(manifest_bytes.count(b"\n"), 1)
            self.assertNotIn(b"\r", manifest_bytes)
            self.assertFalse(manifest_bytes.startswith(b"\xef\xbb\xbf"))
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            self.assertEqual(manifest["rng"]["seed"], 42)
            self.assertEqual(manifest["generation_accounting"]["requested_count"], 4)
            self.assertEqual(manifest["input"]["path"], str(root / "synthetic_train.txt"))
            self.assertEqual(manifest["input"]["role"], "TRAIN_TEXT")
            self.assertEqual(manifest["input"]["expected_sha256"], digest)
            self.assertEqual(manifest["input"]["actual_sha256"], digest)
            config_bytes = (root / "synthetic_b2.yaml").read_bytes()
            self.assertEqual(
                manifest["configuration"]["sha256"],
                hashlib.sha256(config_bytes).hexdigest(),
            )
            self.assertEqual(manifest["configuration"]["path"], str(root / "synthetic_b2.yaml"))
            contract_bytes = (root / "frozen_data_contract.json").read_bytes()
            self.assertEqual(
                manifest["frozen_contract"]["sha256"],
                hashlib.sha256(contract_bytes).hexdigest(),
            )
            self.assertEqual(
                manifest["frozen_contract"]["path"],
                str(root / "frozen_data_contract.json"),
            )
            self.assertRegex(manifest["timestamps"]["start"], r"(Z|[+-]\d{2}:\d{2})$")
            self.assertRegex(manifest["timestamps"]["end"], r"(Z|[+-]\d{2}:\d{2})$")
            self.assertEqual(manifest["hostname"], socket.gethostname())
            self.assertEqual(manifest["repository_provenance"]["mres_commit"], _git_stdout("rev-parse", "HEAD"))
            self.assertEqual(
                manifest["repository_provenance"]["mres_upstream_sha"],
                _git_stdout("rev-parse", "origin/main"),
            )
            self.assertEqual(
                manifest["repository_provenance"]["branch"],
                _git_stdout("rev-parse", "--abbrev-ref", "HEAD"),
            )
            dirty = _git_stdout("status", "--porcelain") != ""
            self.assertEqual(manifest["repository_provenance"]["dirty"], dirty)
            if dirty:
                self.assertIsInstance(manifest["repository_provenance"]["patch_sha256"], str)
            else:
                self.assertIsNone(manifest["repository_provenance"]["patch_sha256"])
            self.assertEqual(manifest["command"], "synthetic-test-only")
            self.assertIn(
                "test_only_synthetic_fixture_not_a_biological_run",
                manifest["deviations"],
            )
            self.assertEqual(manifest["overwrite_refusal_check"]["result"], "passed_exclusive_create")
            self.assertIs(manifest["overwrite_refusal_check"]["exist_ok"], False)
            self.assertEqual(manifest["overwrite_refusal_check"]["creation_primitive"], "os.mkdir")
            self.assertNotIn("UNKNOWN_UNTIL_RUN", manifest_bytes.decode("utf-8"))
            self.assertNotIn('"human_approval"', manifest_bytes.decode("utf-8"))
            self.assertEqual(
                list(manifest),
                list(null_model.MANIFEST_TOP_LEVEL_KEYS),
            )
            self.assertEqual(list(manifest)[0], "manifest_schema_version")
            self.assertEqual(
                manifest["manifest_schema_version"],
                "m4-b2-run-manifest-2",
            )
            self.assertEqual(manifest["schema_version"], "m4-stage1-draft-1")
            self.assertTrue(
                manifest_bytes.startswith(
                    b'{"manifest_schema_version":"m4-b2-run-manifest-2",'
                )
            )
            protocol = manifest["protocol_implementation_approval"]
            self.assertEqual(
                list(protocol),
                list(null_model.PROTOCOL_IMPLEMENTATION_APPROVAL_KEYS),
            )
            self.assertNotIn("document_status", protocol)
            self.assertNotIn("consumable_by_executable_workflow", protocol)
            self.assertNotIn("configuration_sha256", protocol)
            self.assertEqual(
                protocol["configuration_document_status_at_invocation"],
                "APPROVED_FOR_SCIENTIFIC_EXECUTION",
            )
            self.assertIs(
                protocol["configuration_consumable_by_executable_workflow_at_invocation"],
                True,
            )
            self.assertEqual(
                protocol["source_configuration_sha256"],
                manifest["configuration"]["sha256"],
            )
            self.assertEqual(
                manifest["approval_status"],
                protocol["configuration_document_status_at_invocation"],
            )
            self.assertIs(
                manifest["consumable_by_executable_workflow"],
                protocol[
                    "configuration_consumable_by_executable_workflow_at_invocation"
                ],
            )
            self.assertEqual(protocol["approving_person"], "Synthetic Approver")
            self.assertIs(protocol["m4_complete"], False)
            self.assertIs(protocol["authorizes_scientific_execution"], False)
            self.assertIs(protocol["authorizes_this_invocation"], False)
            self.assertEqual(
                protocol["explicitly_not_approved"],
                ["scientific_execution", "B2_generation", "biological_data_runs"],
            )
            self.assertIn(
                "does not revoke scientific_execution_authorisation",
                protocol["explicitly_not_approved_scope"],
            )
            self.assertIn(
                "does not mean this invocation lacked scientific-execution approval",
                protocol["explicitly_not_approved_scope"],
            )
            import yaml

            synthetic_block = yaml.safe_load(config_bytes.decode("utf-8"))[
                "scientific_execution_authorisation"
            ]
            scientific = manifest["scientific_execution_authorisation"]
            self.assertEqual(
                list(scientific),
                list(null_model.SCIENTIFIC_EXECUTION_AUTHORISATION_KEYS),
            )
            for key in null_model.SCIENTIFIC_EXECUTION_AUTHORISATION_KEYS:
                self.assertEqual(scientific[key], synthetic_block[key])
            self.assertNotEqual(
                scientific["output_directory"],
                ONE_RUN_OUTPUT_DIRECTORY,
            )
            relationship = manifest["authorisation_relationship"]
            self.assertIs(
                relationship["scientific_execution_record_authorized_this_invocation"],
                True,
            )
            self.assertIs(
                relationship[
                    "explicitly_not_approved_does_not_revoke_scientific_execution_authorisation"
                ],
                True,
            )
            self.assertIn(
                "This invocation was authorized by scientific_execution_authorisation.",
                relationship["statement"],
            )
            self.assertEqual(
                null_model.serialize_manifest(manifest),
                manifest_bytes,
            )
            self.assertEqual(manifest["exit_status"], 0)
            self.assertEqual(manifest["rng"]["numpy_version"], __import__("numpy").__version__)
            self.assertEqual(manifest["interpreter"]["python_version"], __import__("sys").version)
            self.assertEqual(manifest["raw_output"]["byte_count"], len(raw))
            self.assertEqual(manifest["raw_output"]["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertFalse(str(output).startswith(str(RUNS_ROOT)))
            for record in raw.decode("utf-8").splitlines():
                parsed = json.loads(record)
                self.assertEqual(parsed["sampled_length"], len(parsed["sequence"]))

    def test_expected_and_actual_fields_are_distinct(self):
        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            root = Path(directory)
            fixture, _payload, _digest, run_root = _materialize(
                root,
                PINNED_SMALL_SEQUENCES,
                attempt_count=4,
                seed=42,
            )
            output = run_root / "field-split"
            null_model.execute_test_only_synthetic(fixture, output, command="synthetic-test-only")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            accounting = manifest["generation_accounting"]
            self.assertIn("rows_dropped_expected", accounting)
            self.assertIn("rows_dropped_actual", accounting)
            self.assertEqual(accounting["rows_dropped_expected"], 0)
            self.assertEqual(accounting["rows_dropped_actual"], 0)
            self.assertIs(manifest["ref_opened_expected"], False)
            self.assertIs(manifest["eval_opened_expected"], False)
            self.assertEqual(
                manifest["ref_opened_actual"],
                any(entry["role"] == "REF" for entry in manifest["access_log"]),
            )
            self.assertEqual(
                manifest["eval_opened_actual"],
                any(entry["role"] == "EVAL" for entry in manifest["access_log"]),
            )
            self.assertIs(manifest["ref_opened_actual"], False)
            self.assertIs(manifest["eval_opened_actual"], False)
            self.assertIs(manifest["gpu_used_expected"], False)
            self.assertEqual(manifest["device_backend_actual"], "cpu_numpy")
            self.assertIs(manifest["gpu_api_invoked_actual"], False)
            roles = [entry["role"] for entry in manifest["access_log"]]
            self.assertEqual(roles, ["B2_CONFIG", "FROZEN_CONTRACT", "TRAIN_TEXT"])

    def test_reread_mismatch_is_not_treated_as_the_memory_hash(self):
        real_read = Path.read_bytes

        def tamper(path_self):
            data = real_read(path_self)
            if path_self.name == null_model.RAW_JSONL_FILENAME:
                return data + b"TAMPER"
            return data

        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            root = Path(directory)
            fixture, _payload, _digest, run_root = _materialize(
                root,
                PINNED_SMALL_SEQUENCES,
                attempt_count=4,
                seed=42,
            )
            output = run_root / "reread-mismatch"
            Path.read_bytes = tamper
            try:
                with self.assertRaises(null_model.NullModelError) as ctx:
                    null_model.execute_test_only_synthetic(fixture, output)
                self.assertEqual(ctx.exception.code, "output_reread_mismatch")
            finally:
                Path.read_bytes = real_read
            self.assertTrue((output / "failure_status.json").is_file())
            self.assertFalse((output / "manifest.json").exists())
            self.assertNotIn(b"TAMPER", (output / null_model.RAW_JSONL_FILENAME).read_bytes())

    def test_zero_and_short_writes_fail(self):
        real_write = os.write

        def zero_then_real(descriptor, data):
            zero_then_real.calls += 1
            if zero_then_real.calls == 1:
                return 0
            return real_write(descriptor, data)

        zero_then_real.calls = 0

        def short_then_zero(descriptor, data):
            short_then_zero.calls += 1
            if short_then_zero.calls == 1:
                return 1
            if short_then_zero.calls == 2:
                return 0
            return real_write(descriptor, data)

        short_then_zero.calls = 0
        for wrapped in (zero_then_real, short_then_zero):
            with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
                root = Path(directory)
                fixture, _payload, _digest, run_root = _materialize(
                    root,
                    ["AC", "GU"],
                    attempt_count=2,
                    seed=3,
                )
                output = run_root / "short-write"
                os.write = wrapped
                try:
                    with self.assertRaises(null_model.NullModelError) as ctx:
                        null_model.execute_test_only_synthetic(fixture, output)
                    self.assertEqual(ctx.exception.code, "output_short_write")
                finally:
                    os.write = real_write
                self.assertTrue(output.is_dir())
                self.assertTrue((output / "failure_status.json").is_file())
                self.assertFalse((output / "manifest.json").exists())
                failure = (output / "failure_status.json").read_text(encoding="utf-8")
                self.assertIn("output_short_write", failure)
                self.assertIn('"scientific_run_completed":false', failure.replace(" ", ""))

    def test_mkdir_race_fails_closed(self):
        real_mkdir = os.mkdir

        def compete(path, mode=0o777):
            real_mkdir(path, mode)
            raise FileExistsError(path)

        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            root = Path(directory)
            fixture, _payload, _digest, run_root = _materialize(
                root,
                ["AC", "GU"],
                attempt_count=2,
                seed=3,
            )
            output = run_root / "race-run"
            os.mkdir = compete
            try:
                with self.assertRaises(null_model.NullModelError) as ctx:
                    null_model.execute_test_only_synthetic(fixture, output)
                self.assertEqual(ctx.exception.code, "output_directory_exists")
            finally:
                os.mkdir = real_mkdir
            self.assertTrue(output.is_dir())
            self.assertEqual(list(output.iterdir()), [])

    def test_post_creation_failure_writes_failure_status(self):
        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            root = Path(directory)
            sequences = [SECRET, "ACGU"]
            fixture, _payload, _digest, run_root = _materialize(
                root,
                sequences,
                attempt_count=2,
                seed=5,
                mutate_contract=None,
            )
            fixture.fail_after_directory_creation = True
            output = run_root / "failed-run"
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.execute_test_only_synthetic(fixture, output)
            self.assertEqual(ctx.exception.code, "injected_test_failure")
            self.assertNotIn(SECRET, str(ctx.exception))
            failure_path = output / "failure_status.json"
            failure = failure_path.read_text(encoding="utf-8")
            self.assertIn("FAILED", failure)
            self.assertIn("injected_test_failure", failure)
            self.assertIn('"scientific_run_completed":false', failure.replace(" ", ""))
            self.assertNotIn(SECRET, failure)
            self.assertFalse((output / "manifest.json").exists())
            self.assertFalse((output / null_model.RAW_JSONL_FILENAME).exists())
            original = failure_path.read_bytes()
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.write_failure_status(
                    output,
                    null_model.NullModelError("other_error", "must not overwrite"),
                )
            self.assertEqual(ctx.exception.code, "output_file_exists")
            self.assertEqual(failure_path.read_bytes(), original)
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.execute_test_only_synthetic(fixture, output)
            self.assertEqual(ctx.exception.code, "output_directory_exists")

    def test_failure_status_write_failure_preserves_original_error(self):
        real_write = null_model.exclusive_fsync_write

        def wrapped(path, data):
            if Path(path).name == "failure_status.json":
                raise null_model.NullModelError(
                    "failure_status_unwritable",
                    "failure status could not be written",
                )
            return real_write(path, data)

        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            root = Path(directory)
            fixture, _payload, _digest, run_root = _materialize(
                root,
                [SECRET, "ACGU"],
                attempt_count=2,
                seed=5,
            )
            fixture.fail_after_directory_creation = True
            output = run_root / "secondary-failure"
            stderr = io.StringIO()
            null_model.exclusive_fsync_write = wrapped
            try:
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(null_model.NullModelError) as ctx:
                        null_model.execute_test_only_synthetic(fixture, output)
            finally:
                null_model.exclusive_fsync_write = real_write
            self.assertEqual(ctx.exception.code, "injected_test_failure")
            self.assertEqual(
                ctx.exception.secondary_failure["code"],
                "failure_status_unwritable",
            )
            self.assertNotIn(SECRET, str(ctx.exception))
            self.assertNotIn(SECRET, ctx.exception.secondary_failure["detail"])
            self.assertIn("secondary_failure:", stderr.getvalue())
            self.assertIn("failure_status_unwritable", stderr.getvalue())
            self.assertFalse((output / "failure_status.json").exists())
            self.assertFalse((output / "manifest.json").exists())

    def test_missing_parent_is_a_sanitized_null_model_error(self):
        with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
            root = Path(directory)
            run_root = root / "surrogate-runs"
            run_root.mkdir()
            missing = run_root / "missing-parent" / "child"
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.validate_output_containment(missing, run_root)
            self.assertEqual(ctx.exception.code, "output_parent_missing")
            with self.assertRaises(null_model.NullModelError) as ctx:
                null_model.create_output_directory(missing)
            self.assertEqual(ctx.exception.code, "output_parent_missing")
            self.assertFalse(missing.exists())

    def test_future_authorised_manifest_records_distinct_approval_records(self):
        """A future authorized manifest uses the gate's snapshot, not human_approval."""
        events = []
        real_read = Path.read_bytes

        def read_spy(path_self):
            text = os.path.normpath(str(path_self))
            events.append(text)
            if text.endswith("corpus_final.txt") or "rnagenesis-mres-data" in text:
                raise AssertionError("biological TRAIN_TEXT was opened")
            if text.endswith("frozen_data_contract.json"):
                raise AssertionError("frozen contract was opened")
            _refuse_completed_evidence_access(text)
            return real_read(path_self)

        config = _authorised_production_config()
        config["human_approval"] = _stage1_protocol_approval()
        source_block = config["scientific_execution_authorisation"]
        expected_snapshot = {
            key: source_block[key]
            for key in null_model.SCIENTIFIC_EXECUTION_AUTHORISATION_KEYS
        }
        block = {
            key: source_block[key]
            for key in reversed(null_model.SCIENTIFIC_EXECUTION_AUTHORISATION_KEYS)
        }
        self.assertNotEqual(
            list(block),
            list(null_model.SCIENTIFIC_EXECUTION_AUTHORISATION_KEYS),
        )
        config["scientific_execution_authorisation"] = block
        Path.read_bytes = read_spy
        try:
            resolved, snapshot = null_model.assert_scientific_execution_authorisation(
                config,
                AUTHORISATION_TEST_OUTPUT,
            )
            block["seed"] = 99
            block["approved_by"] = "Reconstructed Approver"
            config["sampler"]["seed"] = 99
            config["input"]["expected_sha256"] = "f" * 64
            approval = null_model.approval_from_config(config, "c" * 64)
            manifest = null_model.build_observed_success_manifest(
                _observed_manifest_inputs(approval, snapshot)
            )
        finally:
            Path.read_bytes = real_read
        self.assertEqual(str(resolved), AUTHORISATION_TEST_OUTPUT)
        self.assertEqual(snapshot["output_directory"], AUTHORISATION_TEST_OUTPUT)
        self.assertEqual(snapshot["seed"], 42)
        self.assertEqual(snapshot["approved_by"], "Laura Hardy")
        for key in null_model.SCIENTIFIC_EXECUTION_AUTHORISATION_KEYS:
            self.assertEqual(snapshot[key], expected_snapshot[key], key)
        self.assertIs(manifest["scientific_execution_authorisation"], snapshot)
        self.assertEqual(list(manifest)[0], "manifest_schema_version")
        self.assertEqual(manifest["manifest_schema_version"], "m4-b2-run-manifest-2")
        self.assertEqual(manifest["schema_version"], "m4-stage1-draft-1")
        self.assertNotIn("human_approval", manifest)
        self.assertEqual(list(manifest), list(null_model.MANIFEST_TOP_LEVEL_KEYS))
        protocol = manifest["protocol_implementation_approval"]
        self.assertNotIn("document_status", protocol)
        self.assertNotIn("consumable_by_executable_workflow", protocol)
        self.assertNotIn("configuration_sha256", protocol)
        self.assertEqual(
            protocol["configuration_document_status_at_invocation"],
            config["document_status"],
        )
        self.assertIs(
            protocol["configuration_consumable_by_executable_workflow_at_invocation"],
            config["consumable_by_executable_workflow"],
        )
        self.assertEqual(protocol["source_configuration_sha256"], "c" * 64)
        self.assertEqual(
            manifest["approval_status"],
            protocol["configuration_document_status_at_invocation"],
        )
        self.assertIs(
            manifest["consumable_by_executable_workflow"],
            protocol["configuration_consumable_by_executable_workflow_at_invocation"],
        )
        self.assertEqual(
            list(protocol),
            list(null_model.PROTOCOL_IMPLEMENTATION_APPROVAL_KEYS),
        )
        self.assertEqual(protocol["record_role"], "stage_1_protocol_implementation_approval")
        self.assertIs(protocol["authorizes_scientific_execution"], False)
        self.assertIs(protocol["authorizes_this_invocation"], False)
        self.assertIn("scientific_execution", protocol["explicitly_not_approved"])
        self.assertIn("B2_generation", protocol["explicitly_not_approved"])
        self.assertIn(
            "does not revoke scientific_execution_authorisation",
            protocol["explicitly_not_approved_scope"],
        )
        self.assertIn(
            "does not mean this invocation lacked scientific-execution approval",
            protocol["explicitly_not_approved_scope"],
        )
        self.assertIn(
            "scientific_execution_authorisation did authorize this invocation",
            protocol["authorizes_this_invocation_meaning"],
        )
        relationship = manifest["authorisation_relationship"]
        self.assertEqual(
            list(relationship),
            list(null_model.AUTHORISATION_RELATIONSHIP_KEYS),
        )
        self.assertIs(
            relationship["scientific_execution_record_authorized_this_invocation"],
            True,
        )
        self.assertIs(relationship["protocol_record_authorized_scientific_execution"], False)
        self.assertIs(
            relationship[
                "explicitly_not_approved_does_not_revoke_scientific_execution_authorisation"
            ],
            True,
        )
        self.assertEqual(
            relationship["statement"],
            null_model.AUTHORISATION_RELATIONSHIP_STATEMENT,
        )
        self.assertTrue(
            relationship["statement"].startswith(
                "This invocation was authorized by scientific_execution_authorisation."
            )
        )
        self.assertIn("protocol implementation only", relationship["statement"])
        self.assertIn("does not revoke", relationship["statement"])
        builder_source = inspect.getsource(null_model.build_observed_success_manifest)
        self.assertNotIn('"human_approval":', builder_source)
        self.assertNotIn("'human_approval':", builder_source)
        self.assertNotIn("config.get", builder_source)
        first = null_model.serialize_manifest(manifest)
        second = null_model.serialize_manifest(manifest)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        self.assertEqual(first.count(b"\n"), 1)
        self.assertNotIn(b"\r", first)
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b'"human_approval"', first)
        parsed_pairs = json.loads(first.decode("utf-8"), object_pairs_hook=list)
        serialized_keys = [key for key, _value in parsed_pairs]
        self.assertEqual(serialized_keys, list(null_model.MANIFEST_TOP_LEVEL_KEYS))
        self.assertEqual(serialized_keys[0], "manifest_schema_version")
        self.assertEqual(
            parsed_pairs[0][1],
            "m4-b2-run-manifest-2",
        )
        self.assertNotIn("human_approval", serialized_keys)
        parsed = json.loads(first.decode("utf-8"))
        self.assertEqual(
            list(parsed["scientific_execution_authorisation"]),
            list(null_model.SCIENTIFIC_EXECUTION_AUTHORISATION_KEYS),
        )
        self.assertEqual(
            null_model.serialize_manifest(parsed),
            first,
        )
        self.assertFalse(any(_is_completed_evidence_path(path) for path in events))
        self.assertFalse(Path(AUTHORISATION_TEST_OUTPUT).exists())
        self.assertFalse(_is_completed_evidence_path(AUTHORISATION_TEST_OUTPUT))

    def test_unexpected_authorisation_key_fails_before_access(self):
        """An extra active-block key is rejected before contract, data, or output."""
        config = _authorised_production_config()
        config["scientific_execution_authorisation"]["revocation_recorded_timestamp"] = (
            "2026-09-29T18:40:21+10:00"
        )
        result = _invoke_guarded_production(AUTHORISATION_TEST_OUTPUT, config)
        self.assertEqual(result["error"].code, "execution_not_authorised")
        self.assertEqual(result["contract_attempts"], 0)
        self.assertEqual(result["created"], 0)
        self._assert_stopped_before_biological_access(result)
        self.assertFalse(
            any(_is_completed_evidence_path(path) for path in result["events"])
        )
        self.assertFalse(
            any(
                path.endswith(".pt")
                or path.endswith(".bin")
                or path.endswith(".safetensors")
                or "checkpoint" in path
                for path in result["events"]
            )
        )

    def test_missing_inactive_or_incomplete_authorisation_fails_before_access(self):
        """Scientific authorization defects stop before contract, data, or output."""
        cases = []
        missing = _authorised_production_config()
        missing.pop("scientific_execution_authorisation")
        cases.append(("missing", missing))
        inactive = _authorised_production_config()
        inactive["scientific_execution_authorisation"]["authorisation_active"] = False
        cases.append(("inactive", inactive))
        revoked = _authorised_production_config()
        revoked["scientific_execution_authorisation"]["activation_status"] = (
            "revoked_after_completed_single_invocation"
        )
        cases.append(("revoked_status", revoked))
        inconsistent = _authorised_production_config()
        inconsistent["scientific_execution_authorisation"]["train_text_sha256"] = "ab" * 32
        cases.append(("inconsistent_hash", inconsistent))
        for key in null_model.SCIENTIFIC_EXECUTION_AUTHORISATION_KEYS:
            incomplete = _authorised_production_config()
            del incomplete["scientific_execution_authorisation"][key]
            cases.append(("incomplete_" + key, incomplete))
        for name, config in cases:
            result = _invoke_guarded_production(AUTHORISATION_TEST_OUTPUT, config)
            self.assertIn(
                result["error"].code,
                ("execution_not_authorised", "output_not_authorised"),
                name,
            )
            self.assertEqual(result["contract_attempts"], 0, name)
            self.assertEqual(result["created"], 0, name)
            self._assert_stopped_before_biological_access(result)
            self.assertFalse(
                any(_is_completed_evidence_path(path) for path in result["events"]),
                name,
            )
            self.assertFalse(
                any(
                    path.endswith(".pt")
                    or path.endswith(".bin")
                    or path.endswith(".safetensors")
                    or "checkpoint" in path
                    for path in result["events"]
                ),
                name,
            )

    def test_pinned_small_fixture_jsonl_bytes(self):
        stats = null_model.compute_corpus_statistics(PINNED_SMALL_SEQUENCES)
        freqs = null_model.frequencies_from_probabilities(stats["probabilities"])
        records = null_model.build_raw_records(4, freqs, stats["lengths"], 42)
        self.assertEqual(null_model.serialize_jsonl(records), PINNED_SMALL_FIXTURE_JSONL)
        for record in records:
            self.assertEqual(record["sampled_length"], len(record["sequence"]))

    def test_bypassing_execution_gate_does_not_skip_output_binding(self):
        """Replacing the old gate does not authorise a different run-root child."""
        real_gate = null_model.assert_execution_authorised

        def allow(_config):
            return None

        null_model.assert_execution_authorised = allow
        try:
            result = _invoke_guarded_production(
                AUTHORISATION_TEST_SIBLING,
                _authorised_production_config(),
            )
        finally:
            null_model.assert_execution_authorised = real_gate
        self.assertEqual(result["error"].code, "output_not_authorised")
        self.assertEqual(result["contract_attempts"], 0)
        self._assert_stopped_before_biological_access(result)
        roots = {root for _path, root in result["containment"]}
        self.assertEqual(roots, {os.path.normpath(str(null_model.PRODUCTION_RUN_ROOT))})

    def test_removed_old_runner_entrypoint_is_not_used(self):
        parameters = inspect.signature(null_model.run_b2_production).parameters
        self.assertEqual(list(parameters), ["output_dir", "command"])

    def test_diagnostics_do_not_print_sequence_contents(self):
        with self.assertRaises(null_model.NullModelError) as ctx:
            null_model.parse_train_text_bytes(b"\n")
        self.assertNotIn(SECRET, str(ctx.exception))
        with self.assertRaises(null_model.NullModelError) as ctx:
            parsed = null_model.parse_train_text_bytes((SECRET + "\nACGU\n").encode("utf-8"))
            null_model.enforce_sequence_contract(parsed + [parsed[0]], 3, 3)
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertNotIn(SECRET, null_model.NullModelError("sha256_mismatch", "hash mismatch").detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)

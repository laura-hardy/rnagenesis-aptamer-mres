"""Synthetic tests for the B2 empirical-null generator.

These tests do not read biological TRAIN, VALIDATION, REF, or EVAL files.
Test-only fixture authorization is not a biological run and must not write
under /home/laura/rnagenesis-mres-runs/.
"""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import io
import json
import os
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
            "    - biological_data_runs",
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


class OutputConfigAndManifestTests(unittest.TestCase):
    def tearDown(self):
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
        config_path = ROOT / "config" / "experiments" / "B2_empirical_null.yaml"
        text = config_path.read_text(encoding="utf-8")
        self.assertIn("consumable_by_executable_workflow: false", text)
        self.assertIn("document_status: APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION", text)
        self.assertIn("m4_complete: false", text)
        import yaml

        loaded = yaml.safe_load(text)
        self.assertIs(loaded["consumable_by_executable_workflow"], False)
        self.assertEqual(
            loaded["document_status"],
            "APPROVED_FOR_M4_IMPLEMENTATION_NOT_EXECUTION",
        )
        self.assertIs(loaded["human_approval"]["m4_complete"], False)
        self.assertEqual(loaded["stage_2a_correction"]["first_implementation"], "failed_review")
        self.assertEqual(loaded["stage_2a_correction"]["corrected_implementation"], "under_review")
        self.assertIs(loaded["stage_2a_correction"]["execution_authorised"], False)
        self.assertIs(loaded["stage_2a_correction"]["success_claimed"], False)
        events = []
        real_read = Path.read_bytes
        real_lstat = os.lstat
        real_validate = null_model.validate_output_containment
        validated = {"count": 0}

        def read_spy(path_self):
            events.append(("read", os.path.normpath(str(path_self))))
            return real_read(path_self)

        def lstat_spy(path):
            events.append(("lstat", os.path.normpath(str(path))))
            return real_lstat(path)

        def validate_spy(path, run_root):
            validated["count"] += 1
            return real_validate(path, run_root)

        Path.read_bytes = read_spy
        os.lstat = lstat_spy
        null_model.validate_output_containment = validate_spy
        previous = os.environ.get("M4_STAGE2A_TEST_ONLY")
        os.environ["M4_STAGE2A_TEST_ONLY"] = "1"
        try:
            with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
                output = Path(directory) / "would-be-run"
                stderr = io.StringIO()
                with self.assertRaises(null_model.NullModelError) as ctx:
                    null_model.run_b2_production(str(output))
                self.assertEqual(ctx.exception.code, "execution_not_authorised")
                self.assertIn("consumable_by_executable_workflow=False", ctx.exception.detail)
                self.assertFalse(output.exists())
                with contextlib.redirect_stderr(stderr):
                    code = null_model.main(["--output-dir", str(output)])
                self.assertEqual(code, 1)
                self.assertFalse(output.exists())
                self.assertNotIn(SECRET, stderr.getvalue())
        finally:
            Path.read_bytes = real_read
            os.lstat = real_lstat
            null_model.validate_output_containment = real_validate
            if previous is None:
                os.environ.pop("M4_STAGE2A_TEST_ONLY", None)
            else:
                os.environ["M4_STAGE2A_TEST_ONLY"] = previous
        self.assertEqual(validated["count"], 0)
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

    def test_fixed_config_identity_is_checked_before_open(self):
        events = []
        real_read = Path.read_bytes
        real_lstat = os.lstat

        def read_spy(path_self):
            events.append("read")
            return real_read(path_self)

        def lstat_spy(path):
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
            self.assertEqual(manifest["human_approval"]["approving_person"], "Synthetic Approver")
            self.assertIs(manifest["human_approval"]["m4_complete"], False)
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

    def test_pinned_small_fixture_jsonl_bytes(self):
        stats = null_model.compute_corpus_statistics(PINNED_SMALL_SEQUENCES)
        freqs = null_model.frequencies_from_probabilities(stats["probabilities"])
        records = null_model.build_raw_records(4, freqs, stats["lengths"], 42)
        self.assertEqual(null_model.serialize_jsonl(records), PINNED_SMALL_FIXTURE_JSONL)
        for record in records:
            self.assertEqual(record["sampled_length"], len(record["sequence"]))

    def test_production_output_root_is_pinned_after_the_contract(self):
        opened = []
        real_read = Path.read_bytes
        real_gate = null_model.assert_execution_authorised
        seen = {}

        def read_spy(path_self):
            text = os.path.normpath(str(path_self))
            if text.endswith("corpus_final.txt") or "rnagenesis-mres-data" in text:
                raise AssertionError("biological data was opened")
            opened.append(text)
            return real_read(path_self)

        def allow(_config):
            return None

        real_validate = null_model.validate_output_containment

        def validate_spy(path, run_root):
            seen["run_root"] = run_root
            return real_validate(path, run_root)

        Path.read_bytes = read_spy
        null_model.assert_execution_authorised = allow
        null_model.validate_output_containment = validate_spy
        try:
            with tempfile.TemporaryDirectory(prefix="m4-stage2a-synthetic-") as directory:
                output = Path(directory) / "outside-run"
                with self.assertRaises(null_model.NullModelError) as ctx:
                    null_model.run_b2_production(str(output))
                self.assertEqual(ctx.exception.code, "output_not_a_child")
                self.assertEqual(Path(seen["run_root"]), null_model.PRODUCTION_RUN_ROOT)
                self.assertFalse(output.exists())
        finally:
            Path.read_bytes = real_read
            null_model.assert_execution_authorised = real_gate
            null_model.validate_output_containment = real_validate
        self.assertTrue(any(path.endswith("frozen_data_contract.json") for path in opened))
        self.assertTrue(any(path.endswith("B2_empirical_null.yaml") for path in opened))

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

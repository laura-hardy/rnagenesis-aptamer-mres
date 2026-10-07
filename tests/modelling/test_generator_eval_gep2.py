"""Synthetic GEP-2 analysis tests.

No EVAL, REF, VALIDATION, TRAIN, pool, checkpoint, or biological sequence
record is opened. Sequences in this module are constructed literals.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import unittest
from contextlib import redirect_stdout
from io import StringIO

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_analysis():
    path = os.path.join(ROOT, "scripts/modelling/generator_eval_analysis.py")
    spec = importlib.util.spec_from_file_location("generator_eval_analysis_gep2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analysis = load_analysis()
preflight = analysis._preflight()
LENGTH_VECTOR_SHA = "8e5d7171e0ec11d9d67f0f69da81f94ae3871370f35f89c0166c064521242b3a"


def provenance(base=88000, sampling=99001, length_vector_sha256=None):
    return {
        "target_length_sampling_seed": sampling,
        "length_vector_sha256": LENGTH_VECTOR_SHA if length_vector_sha256 is None else length_vector_sha256,
        "generation_seed_base": base,
        "seed_formula": "generation_seed_base + invocation_index",
        "max_seq_len_formula": "requested_target_length + 1",
        "max_chunk_size": 16,
        "batch_num": 1,
    }


def record(record_id, condition):
    row = {key: None for key in preflight.RECORD_KEYS}
    row["record_id"] = record_id
    row["condition"] = condition
    row["data_role"] = "SYNTHETIC"
    row["length_regime"] = preflight.LENGTH_REGIMES[condition]
    return row


def mark_valid(row, sequence):
    row["sequence"] = sequence
    row["parsed_status"] = True
    row["alphabet_valid"] = True
    row["cleaning_status"] = "cleaned"
    row["cleaning_version"] = "gep2-synthetic-cleaner"
    row["observed_length"] = len(sequence)
    return row


def mark_invalid_nonempty(row, sequence):
    row["sequence"] = sequence
    row["parsed_status"] = True
    row["alphabet_valid"] = False
    row["cleaning_status"] = "rejected"
    row["cleaning_version"] = "gep2-synthetic-cleaner"
    row["observed_length"] = len(sequence)
    return row


def mark_unparsed(row):
    row["sequence"] = None
    row["parsed_status"] = False
    row["alphabet_valid"] = False
    row["cleaning_status"] = "not_applicable"
    row["cleaning_version"] = None
    row["observed_length"] = None
    return row


def add_schedule(row, *, invocation_index, batch_position, attempt, requested, base=88000, sampling=99001, chunk=None, length_vector_sha256=None):
    row["original_attempt_index"] = attempt
    row["invocation_index"] = invocation_index
    row["batch_position"] = batch_position
    row["requested_target_length"] = requested
    row["requested_length"] = requested
    row["max_seq_len"] = requested + 1
    row["invocation_seed"] = base + invocation_index
    row["generation_seed"] = base + invocation_index
    row["length_sampling_seed"] = sampling
    row["generation_chunk_id"] = chunk or ("chunk-m%d" % invocation_index)
    row["length_schedule_provenance"] = provenance(base, sampling, length_vector_sha256)
    return row


def b0_row(record_id, sequence="ACGUACGUACGUACGUACGUACGUACGUACGUACGU", seed=96001):
    row = record(record_id, "B0")
    mark_valid(row, sequence)
    row["requested_length"] = None
    row["historical_generation_seed"] = seed
    row["historical_batch_index"] = 0
    row["nominal_max_seq_len"] = 37
    row["checkpoint_id"] = "gep2-synthetic-b0"
    return row


def b2_row(record_id, sequence="UUUUCCCC", seed=77001):
    row = record(record_id, "B2")
    mark_valid(row, sequence)
    row["requested_length"] = len(sequence)
    row["empirical_null_seed"] = seed
    return row


def b1_row(record_id, sequence, *, invocation_index=1, batch_position=0, attempt=0, requested=None, chunk=None, base=88000, length_vector_sha256=None):
    row = record(record_id, "B1")
    mark_valid(row, sequence)
    requested = len(sequence) if requested is None else requested
    add_schedule(
        row,
        invocation_index=invocation_index,
        batch_position=batch_position,
        attempt=attempt,
        requested=requested,
        chunk=chunk,
        base=base,
        length_vector_sha256=length_vector_sha256,
    )
    row["length_condition_seed"] = 88111
    row["checkpoint_id"] = "gep2-synthetic-b1"
    return row


def d1_row(record_id, sequence, training_seed, *, invocation_index=1, batch_position=0, attempt=0, requested=None, chunk=None, base=88000, length_vector_sha256=None):
    row = record(record_id, "D1")
    mark_valid(row, sequence)
    requested = len(sequence) if requested is None else requested
    add_schedule(
        row,
        invocation_index=invocation_index,
        batch_position=batch_position,
        attempt=attempt,
        requested=requested,
        chunk=chunk,
        base=base,
        length_vector_sha256=length_vector_sha256,
    )
    row["training_seed"] = training_seed
    row["checkpoint_id"] = "gep2-synthetic-d1"
    return row


def reference(sequence_id, sequence, label=None):
    entry = {"sequence_id": sequence_id, "sequence": sequence}
    if label is not None:
        entry["s6_length_stratum"] = label
    return entry


def envelope(records, train, reference_rows, **extra):
    document = {
        "fixture_role": "SYNTHETIC",
        "reference_role": "synthetic_eval_stand_in",
        "reference_id": "gep2-synthetic-reference",
        "train_collection_role": "synthetic_train_stand_in",
        "synthetic_train_cores": list(train),
        "synthetic_reference_sequences": list(reference_rows),
        "stratified": False,
        "records": records,
    }
    document.update(extra)
    return document


def schedule_producer(total=2, formula="44000 + invocation_index", max_formula="sampled_target_length + 1", base=44000, max_seq_offset=1):
    ordered = [4, 8]
    invocations = []
    for index in range(total):
        target = ordered[index % len(ordered)]
        invocations.append(
            {
                "invocation_index": index,
                "invocation_seed": base + index,
                "target_length": target,
                "max_seq_len": target + max_seq_offset,
                "batch_num": 1,
                "actual_chunk_size": 1,
                "original_attempt_indexes": [index],
            }
        )
    return {
        "sampling_seed": 43000,
        "generation_seed_base": base,
        "seed_formula": formula,
        "max_seq_len_formula": max_formula,
        "max_chunk_size": 16,
        "batch_num": 1,
        "total_attempts": total,
        "sampled_target_lengths": [ordered[index % len(ordered)] for index in range(total)],
        "ordered_lengths": ordered,
        "length_vector_sha256": analysis._length_vector_sha256(ordered),
        "invocations": invocations,
    }


def default_schedule_producer():
    """Schedule that records the same provenance as the default B1 and D1 rows."""
    ordered = [8]
    base = 88000
    sampling = 99001
    return {
        "sampling_seed": sampling,
        "generation_seed_base": base,
        "seed_formula": "generation_seed_base + invocation_index",
        "max_seq_len_formula": "requested_target_length + 1",
        "max_chunk_size": 16,
        "batch_num": 1,
        "total_attempts": 1,
        "sampled_target_lengths": [8],
        "ordered_lengths": ordered,
        "length_vector_sha256": analysis._length_vector_sha256(ordered),
        "invocations": [
            {
                "invocation_index": 1,
                "invocation_seed": base + 1,
                "target_length": 8,
                "max_seq_len": 9,
                "batch_num": 1,
                "actual_chunk_size": 1,
                "original_attempt_indexes": [0],
                "expected_batch_positions": [0],
            }
        ],
    }


def default_document():
    schedule = default_schedule_producer()
    digest = schedule["length_vector_sha256"]
    rows = [
        b0_row("b0-valid"),
        b1_row("b1-match", "ACGUACGU", invocation_index=1, batch_position=0, attempt=0, length_vector_sha256=digest),
        d1_row("d1-match", "ACGUACGA", 91001, invocation_index=1, batch_position=0, attempt=0, length_vector_sha256=digest),
        b2_row("b2-valid"),
    ]
    return envelope(
        rows,
        ["UUUUUUUU", "CCCCCCCC"],
        [reference("ref-a", "ACGUACGU"), reference("ref-b", "GGGGCCCC")],
        schedule_producer=schedule,
        b2_producer_batch=[{"record_id": "b2-producer", "seed": 77001}],
    )


def parse_gc_document():
    valid_a = b1_row("gc-a", "GGGGGGGG", invocation_index=1, batch_position=0, attempt=0)
    valid_b = b1_row("gc-b", "GGGGGGGG", invocation_index=1, batch_position=1, attempt=1)
    valid_c = b1_row("gc-c", "AAAAAAAA", invocation_index=1, batch_position=2, attempt=2)
    invalid = b1_row("gc-invalid", "ACGUACGU", invocation_index=1, batch_position=3, attempt=3)
    mark_invalid_nonempty(invalid, "ACGTACGT")
    empty = b1_row("gc-empty", "ACGUACGU", invocation_index=1, batch_position=4, attempt=4)
    mark_unparsed(empty)
    empty["requested_length"] = 8
    d1 = d1_row("gc-d1", "ACGUACGU", 91001, invocation_index=2, batch_position=0, attempt=0)
    return envelope(
        [valid_a, valid_b, valid_c, invalid, empty, d1, b0_row("gc-b0"), b2_row("gc-b2")],
        ["UUUUUUUU"],
        [reference("ref-gc", "ACGUACGU")],
    )


def headlines(edit, nucleotide, dinucleotide):
    return {
        "nearest_reference_normalized_edit_distance.median": edit,
        "nucleotide_total_variation_to_reference": nucleotide,
        "dinucleotide_total_variation_to_reference": dinucleotide,
    }


class SpecContractTests(unittest.TestCase):
    def test_source_hash_metric_count_draft_and_no_aggregate(self):
        spec = preflight.load_metric_spec()
        ids = [metric["metric_id"] for metric in spec["metrics"]]
        self.assertEqual(len(ids), 35)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(spec["freeze_status"], "draft")
        self.assertFalse(spec["aggregate_generator_quality_score"])
        self.assertEqual(spec["governing_plan"]["version"], "3.0")
        self.assertEqual(spec["governing_plan"]["sha256"], "e6193d0d14245049c218b4da0ef8059fb63b2f31e4885b3457cd44e41b76c50c")
        analysis_path = os.path.join(ROOT, "scripts/modelling/generator_eval_analysis.py")
        with open(analysis_path, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        for metric_id in preflight.GEP2_IMPLEMENTED_METRIC_IDS:
            metric = next(item for item in spec["metrics"] if item["metric_id"] == metric_id)
            self.assertEqual(metric["code_revision"]["path"], "scripts/modelling/generator_eval_analysis.py")
            self.assertEqual(metric["code_revision"]["sha256"], digest)
            self.assertTrue(metric["denominator_and_filters"])
            self.assertTrue(metric["units"])
            self.assertTrue(metric["expected_range"])
            self.assertTrue(metric["length_treatment"])
            self.assertTrue(metric["seed_or_block_treatment"])
            self.assertTrue(metric["missing_failure_handling"])
        for metric_id in preflight.GEP2_CLOSENESS_METRIC_IDS:
            metric = next(item for item in spec["metrics"] if item["metric_id"] == metric_id)
            self.assertEqual(metric["scientific_role"], "closeness")
            self.assertEqual(metric["direction"], "lower")
            self.assertEqual(metric["reference_role"], "synthetic_eval_stand_in")
            self.assertIn("formal M9C unlock supplies unique EVAL cores", metric["calculation_summary"])
        self.assertNotIn("combined_quality_score", ids)
        self.assertNotIn("combined_closeness_score", ids)
        self.assertNotIn("confidence_interval", ids)
        self.assertNotIn("mixed", ids)
        self.assertNotIn("maximum_identity_to_TRAIN", ids)
        self.assertNotIn("nucleotide_total_variation_to_train", ids)

    def test_frozen_spec_missing_hash_aggregate_and_alias_are_refused(self):
        frozen = copy.deepcopy(preflight.load_metric_spec())
        frozen["freeze_status"] = "frozen"
        with self.assertRaises(preflight.GeneratorEvalContractError) as caught:
            preflight.validate_metric_spec(frozen, require_draft=True)
        self.assertEqual(caught.exception.code, "metric_spec_frozen_in_gep1")
        missing = copy.deepcopy(preflight.load_metric_spec())
        missing["metrics"][-1]["code_revision"] = {"path": "scripts/modelling/generator_eval_analysis.py"}
        with self.assertRaises(preflight.GeneratorEvalContractError) as caught:
            preflight.validate_metric_spec(missing, require_draft=True)
        self.assertEqual(caught.exception.code, "revision_invalid")
        aggregate = copy.deepcopy(preflight.load_metric_spec())
        aggregate["aggregate_generator_quality_score"] = True
        with self.assertRaises(preflight.GeneratorEvalContractError) as caught:
            preflight.validate_metric_spec(aggregate, require_draft=True)
        self.assertEqual(caught.exception.code, "aggregate_score_forbidden")
        alias = copy.deepcopy(preflight.load_metric_spec())
        alias["metrics"].append(copy.deepcopy(alias["metrics"][-1]))
        alias["metrics"][-1]["metric_id"] = "maximum_identity_to_TRAIN"
        with self.assertRaises(preflight.GeneratorEvalContractError) as caught:
            preflight.validate_metric_spec(alias, require_draft=True)
        self.assertEqual(caught.exception.code, "unknown_metric_alias")
        role = copy.deepcopy(preflight.load_metric_spec())
        closeness = next(metric for metric in role["metrics"] if metric["metric_id"] == "nearest_reference_normalized_edit_distance")
        closeness["reference_role"] = "EVAL"
        with self.assertRaises(preflight.GeneratorEvalContractError) as caught:
            preflight.validate_metric_spec(role, require_draft=True)
        self.assertIn(caught.exception.code, ("closeness_runtime_role_refused", "reference_role_refused"))


class ParsingAndGcTests(unittest.TestCase):
    def test_successfully_parsed_differs_from_legacy_parsed_outputs(self):
        document = parse_gc_document()
        report = analysis.analyse(document)
        b1 = report["conditions"]["B1"]
        self.assertEqual(b1["successfully_parsed_outputs"], 4)
        self.assertEqual(b1["parsed_outputs"], 5)
        self.assertGreater(b1["parsed_outputs"], b1["successfully_parsed_outputs"])
        self.assertEqual(b1["m4_summary"]["valid_outputs"], 3)
        self.assertEqual(analysis.successfully_parsed_outputs([{"sequence": "ACGTACGT"}, {"sequence": None}, {"sequence": ""}]), 1)

    def test_pooled_gc_keeps_duplicates_and_is_null_without_bases(self):
        # GGGGGGGG, GGGGGGGG, AAAAAAAA: G=16, total=24, GC=16/24.
        # Unique rows would be G=8 and A=8, GC=8/16.
        sequences = ["GGGGGGGG", "GGGGGGGG", "AAAAAAAA"]
        self.assertEqual(analysis.pooled_gc_fraction(sequences), 16 / 24)
        self.assertNotEqual(analysis.pooled_gc_fraction(sequences), 8 / 16)
        self.assertIsNone(analysis.pooled_gc_fraction([]))
        report = analysis.analyse(parse_gc_document())
        self.assertEqual(report["conditions"]["B1"]["pooled_gc_fraction"], 16 / 24)
        self.assertEqual(report["conditions"]["B1"]["generated_valid_row_denominator"], 3)
        self.assertEqual(report["conditions"]["B1"]["generated_unique_valid_count"], 2)


class ReferenceValidationTests(unittest.TestCase):
    def assert_refused(self, document, code):
        called = []

        def after(prepared):
            called.append(prepared)

        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.analyse(document, _after_validation=after)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(called, [])
        self.assertNotIn("ACGUACGU", caught.exception.detail)
        self.assertNotIn("ACGTACGU", caught.exception.detail)

    def test_empty_and_noncanonical_train_are_rejected_before_metrics(self):
        empty = default_document()
        empty["synthetic_train_cores"] = []
        self.assert_refused(empty, "train_reference_invalid")
        bad = default_document()
        bad["synthetic_train_cores"] = ["ACGTACGU"]
        self.assert_refused(bad, "train_reference_invalid")

    def test_empty_duplicate_and_noncanonical_reference_are_rejected(self):
        empty = default_document()
        empty["synthetic_reference_sequences"] = []
        self.assert_refused(empty, "reference_empty")
        duplicate = default_document()
        duplicate["synthetic_reference_sequences"] = [
            reference("ref-a", "ACGUACGU"),
            reference("ref-b", "ACGUACGU"),
        ]
        self.assert_refused(duplicate, "reference_sequences_not_unique")
        bad = default_document()
        bad["synthetic_reference_sequences"] = [reference("ref-a", "ACGTACGU")]
        self.assert_refused(bad, "reference_noncanonical")

    def test_nonsynthetic_reference_roles_are_rejected(self):
        for role in ("EVAL", "REF", "VALIDATION", "TRAIN"):
            document = default_document()
            document["reference_role"] = role
            self.assert_refused(document, "reference_role_refused")

    def test_path_inputs_are_rejected(self):
        document = default_document()
        document["input_path"] = "synthetic_default_analysis.json"
        self.assert_refused(document, "path_input_refused")
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.load_named_fixture("../generator_eval_gep1/synthetic_empty.json")
        self.assertEqual(caught.exception.code, "path_input_refused")
        self.assertEqual(analysis.main(["eval.csv"]), 2)
        self.assertEqual(analysis.main(["--input", "pools/final.json"]), 2)


class ClosenessTests(unittest.TestCase):
    def test_hand_calculated_distance_and_total_variation_keep_duplicates(self):
        generated = ["ACACACAC", "ACACACAC"]
        reference_rows = ["AGACACAC"]
        distance = analysis._m6().edit_distance("ACACACAC", "AGACACAC")
        self.assertEqual(distance, 1)
        nearest = analysis.nearest_reference_normalized_edit_distance(generated, reference_rows)
        self.assertEqual(nearest["median"], 1 / 8)
        self.assertEqual(nearest["quantiles"]["count"], 2)
        self.assertEqual(nearest["generated_valid_row_denominator"], 2)
        self.assertEqual(nearest["generated_unique_valid_count"], 1)
        self.assertEqual(nearest["reference_unique_core_denominator"], 1)
        # Generated bases: ACACACAC twice -> A8 C8, total 16.
        # Reference AGACACAC -> A4 C3 G1, total 8.
        nucleotide_l1 = abs(8 / 16 - 4 / 8) + abs(8 / 16 - 3 / 8) + abs(0 - 1 / 8) + abs(0 - 0)
        nucleotide = analysis.nucleotide_total_variation_to_reference(generated, reference_rows)
        self.assertEqual(nucleotide["value"], 0.5 * nucleotide_l1)
        # Generated pairs per copy: AC,CA,AC,CA,AC,CA,AC -> AC4 CA3; twice -> AC8 CA6, total 14.
        # Reference pairs: AG,GA,AC,CA,AC,CA,AC -> AG1 GA1 AC3 CA2, total 7.
        generated_pairs = {"AC": 8, "CA": 6}
        reference_pairs = {"AG": 1, "GA": 1, "AC": 3, "CA": 2}
        keys = set(generated_pairs) | set(reference_pairs)
        dinucleotide_l1 = sum(abs(generated_pairs.get(key, 0) / 14 - reference_pairs.get(key, 0) / 7) for key in keys)
        dinucleotide = analysis.dinucleotide_total_variation_to_reference(generated, reference_rows)
        self.assertEqual(dinucleotide["value"], 0.5 * dinucleotide_l1)
        self.assertIsNone(analysis.dinucleotide_total_variation_to_reference(["A", "A"], ["C"])["value"])
        self.assertEqual(
            analysis.dinucleotide_total_variation_to_reference(["A", "A"], ["C"])["undefined_reason"],
            "no_overlapping_dinucleotides",
        )

    def test_stratified_results_require_explicit_s6_labels(self):
        short_b1 = b1_row("st-b1-s", "AAAAAAAA", invocation_index=1, batch_position=0, attempt=0)
        long_b1 = b1_row("st-b1-l", "GGGGGGGG", invocation_index=1, batch_position=1, attempt=1)
        short_d1 = d1_row("st-d1-s", "AAAAAAAA", 91001, invocation_index=1, batch_position=0, attempt=0)
        long_d1 = d1_row("st-d1-l", "ACGUACGU", 91001, invocation_index=1, batch_position=1, attempt=1, requested=8)
        b0 = b0_row("st-b0")
        b2 = b2_row("st-b2")
        for row, label in (
            (short_b1, "short"),
            (long_b1, "long"),
            (short_d1, "short"),
            (long_d1, "long"),
            (b0, "long"),
            (b2, "short"),
        ):
            row["s6_length_stratum"] = label
            row["s6_assignment_provenance"] = "s6-gep2-synthetic-assignment"
        document = envelope(
            [short_b1, long_b1, short_d1, long_d1, b2, b0],
            ["UUUUUUUU"],
            [reference("ref-s", "AAAAAAAA", "short"), reference("ref-l", "GGGGGGGG", "long")],
            stratified=True,
            s6_assignment_provenance="s6-gep2-synthetic-assignment",
        )
        # Length 8 labelled long must stay long. It is not inferred to be short.
        self.assertEqual(len(long_d1["sequence"]), 8)
        report = analysis.analyse(document)
        short = report["conditions"]["D1"]["stratified"]["short"]
        long = report["conditions"]["D1"]["stratified"]["long"]
        self.assertEqual(short["generated_valid_row_denominator"], 1)
        self.assertEqual(long["generated_valid_row_denominator"], 1)
        self.assertEqual(short["reference_unique_core_denominator"], 1)
        self.assertEqual(long["pooled_gc_fraction"], 0.5)
        self.assertEqual(short["pooled_gc_fraction"], 0.0)
        self.assertFalse(report["s6_stratum_inferred_from_length"])
        missing = copy.deepcopy(document)
        del missing["records"][0]["s6_length_stratum"]
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.analyse(missing)
        self.assertEqual(caught.exception.code, "s6_label_missing")
        inconsistent = copy.deepcopy(document)
        inconsistent["records"][0]["s6_assignment_provenance"] = "other-token"
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.analyse(inconsistent)
        self.assertEqual(caught.exception.code, "s6_provenance_inconsistent")
        absent = copy.deepcopy(document)
        absent["s6_assignment_provenance"] = ""
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.analyse(absent)
        self.assertEqual(caught.exception.code, "s6_provenance_missing")


class SeedAndDirectionTests(unittest.TestCase):
    def test_every_directional_state(self):
        cases = [
            (headlines(1, 1, 1), headlines(0, 0, 0), "d1_closer_or_tied"),
            (headlines(0, 0, 0), headlines(1, 1, 1), "d1_farther_or_tied"),
            (headlines(1, 0, 1), headlines(0, 1, 1), "mixed"),
            (headlines(0.25, 0.5, 0.5), headlines(0.25, 0.5, 0.5), "all_tied"),
            (headlines(1, 1, 1), headlines(0, 1, 1), "d1_closer_or_tied"),
            (headlines(0, 0, 0), headlines(1, 0, 0), "d1_farther_or_tied"),
            (headlines(None, 0, 0), headlines(0, 0, 0), "not_applicable"),
        ]
        for b1, d1, label in cases:
            result = analysis.directional_consistency(b1, d1)
            self.assertEqual(result["label"], label)
            self.assertFalse(result["label_is_a_score"])
            self.assertFalse(result["replaces_the_three_metrics"])
            self.assertFalse(result["applied_to_b0"])
            self.assertFalse(result["applied_to_b2"])

    def test_sequence_example_is_mixed(self):
        # Reference AAAAAAAA+CCCCCCCC is half A and half C.
        # B1 AAACAAAA is nearer that pool in composition than D1 AAAAAAAA,
        # while D1 is an exact edit of the A reference and B1 is not.
        b1 = b1_row("mix-b1", "AAACAAAA")
        d1 = d1_row("mix-d1", "AAAAAAAA", 91001)
        document = envelope(
            [b1, d1, b0_row("mix-b0"), b2_row("mix-b2")],
            ["UUUUUUUU"],
            [reference("ref-a", "AAAAAAAA"), reference("ref-c", "CCCCCCCC")],
        )
        report = analysis.analyse(document)
        self.assertEqual(report["b1_d1_directional_consistency"]["label"], "mixed")
        differences = report["b1_d1_directional_consistency"]["differences"]
        self.assertLess(differences["nearest_reference_normalized_edit_distance.median"]["d1_minus_b1"], 0)
        self.assertGreater(differences["nucleotide_total_variation_to_reference"]["d1_minus_b1"], 0)

    def test_one_seed_omits_the_range_and_chunks_are_not_replicates(self):
        first = d1_row("one-a", "ACGUACGU", 91001, invocation_index=1, batch_position=0, attempt=0, chunk="chunk-m1")
        second = d1_row("one-b", "GGGGCCCC", 91001, invocation_index=2, batch_position=0, attempt=1, chunk="chunk-m2")
        document = envelope(
            [first, second, b1_row("one-b1", "ACGUACGU"), b0_row("one-b0"), b2_row("one-b2")],
            ["UUUUUUUU"],
            [reference("ref-a", "ACGUACGU")],
        )
        report = analysis.analyse(document)
        seeds = report["d1_by_training_seed"]
        self.assertEqual(seeds["d1_training_seed_count"], 1)
        self.assertIsNone(seeds["observed_range"])
        self.assertEqual(seeds["uncertainty_statement"], "Uncertainty excludes training-run variability.")
        self.assertIn("generation_chunk_id", seeds["not_training_replicate_units"])
        self.assertIn("invocation_index", seeds["not_training_replicate_units"])
        self.assertIn("generation_seed", seeds["not_training_replicate_units"])
        self.assertEqual(len(seeds["by_training_seed"]), 1)
        self.assertEqual(seeds["by_training_seed"][0]["row_count"], 2)

    def test_two_seeds_report_an_allowlisted_observed_range(self):
        hit = d1_row("two-hit", "ACGUACGU", 91001, invocation_index=1, batch_position=0, attempt=0)
        miss = d1_row("two-miss", "GGGGAAAA", 91002, invocation_index=2, batch_position=0, attempt=0, requested=4)
        document = envelope(
            [hit, miss, b1_row("two-b1", "ACGUACGU"), b0_row("two-b0"), b2_row("two-b2")],
            ["UUUUUUUU"],
            [reference("ref-a", "ACGUACGU")],
        )

        def fold(sequence):
            if sequence.startswith("G"):
                return ("." * len(sequence), -1.0 * len(sequence))
            return ("(" * len(sequence), -3.0 * len(sequence))

        report = analysis.analyse(document, fold=fold)
        seeds = report["d1_by_training_seed"]
        self.assertEqual(seeds["d1_training_seeds"], [91001, 91002])
        self.assertEqual(len(seeds["by_training_seed"]), 2)
        observed = seeds["observed_range"]
        self.assertEqual(observed["exact_hit_rate"], {"minimum": 0.0, "maximum": 1.0, "undefined_reason": None})
        self.assertIn("nearest_reference_normalized_edit_distance.median", observed)
        self.assertIn("mfe_per_nt.median", observed)
        self.assertIn("paired_fraction.median", observed)
        self.assertNotIn("p25", observed)
        self.assertNotIn("confidence_interval", seeds)
        self.assertFalse(seeds["observed_range_is_a_confidence_interval"])
        self.assertIn("observed range", seeds["uncertainty_statement"])
        self.assertNotIn("confidence interval is computed", seeds["uncertainty_statement"])
        self.assertIn("not a confidence interval", seeds["uncertainty_statement"])
        quantiles = seeds["by_training_seed"][0]["closeness"]["nearest_reference_normalized_edit_distance"]["quantiles"]
        self.assertIn("p25", quantiles)
        self.assertNotIn("nearest_reference_normalized_edit_distance.p25", observed)


class BlockScheduleAndPanelTests(unittest.TestCase):
    def test_matched_incompatible_and_one_sided_blocks(self):
        b1_match = b1_row("blk-b1", "ACGUACGU", invocation_index=1, batch_position=0, attempt=0, chunk="chunk-shared")
        d1_match = d1_row("blk-d1", "ACGUACGA", 91001, invocation_index=1, batch_position=0, attempt=0, chunk="chunk-other")
        b1_bad = b1_row("blk-b1-bad", "GGGGCCCC", invocation_index=2, batch_position=0, attempt=1, chunk="chunk-shared")
        d1_bad = d1_row("blk-d1-bad", "GGGGCCCA", 91001, invocation_index=2, batch_position=0, attempt=1, base=88010, chunk="chunk-shared")
        b1_only = b1_row("blk-b1-only", "AAAAAAAA", invocation_index=3, batch_position=0, attempt=2, chunk="chunk-shared")
        d1_only = d1_row("blk-d1-only", "CCCCCCCC", 91001, invocation_index=4, batch_position=0, attempt=2, chunk="chunk-shared")
        document = envelope(
            [b1_match, d1_match, b1_bad, d1_bad, b1_only, d1_only, b0_row("blk-b0"), b2_row("blk-b2")],
            ["UUUUUUUU"],
            [reference("ref-a", "ACGUACGU")],
        )
        report = analysis.analyse(document)
        blocks = report["matched_b1_d1_blocks"]
        self.assertEqual(blocks["matched_invocation_indexes"], [1])
        self.assertEqual(blocks["incompatible_invocation_indexes"], [2])
        self.assertEqual(blocks["b1_only_invocation_indexes"], [3])
        self.assertEqual(blocks["d1_only_invocation_indexes"], [4])
        self.assertFalse(blocks["generation_chunk_label_is_sufficient_evidence"])
        self.assertFalse(blocks["schedule_blocks_are_training_replicates"])
        self.assertFalse(blocks["p_values_computed"])
        matched = blocks["matched_blocks"][0]
        self.assertTrue(matched["pairing_predicate_passed"])
        self.assertIsNone(matched["p_value"])
        self.assertIsNone(matched["confidence_interval"])
        self.assertFalse(matched["is_training_replicate"])
        self.assertFalse(matched["is_independent_biological_replicate"])
        self.assertGreater(matched["d1_minus_b1"]["nearest_reference_normalized_edit_distance.median"]["d1_minus_b1"], 0)
        self.assertIn("chunk-shared", blocks["incompatible_blocks"][0]["generation_chunk_ids"])
        self.assertIn("invocation_seed", blocks["incompatible_blocks"][0]["reasons"])

    def test_schedule_mapper_checks_arithmetic_and_does_not_satisfy_the_budget(self):
        mapped = analysis.map_schedule_provenance(schedule_producer())
        self.assertEqual(mapped["target_length_sampling_seed"], 43000)
        self.assertNotIn("sampling_seed", mapped)
        self.assertEqual(mapped["seed_formula"], "generation_seed_base + invocation_index")
        self.assertEqual(mapped["max_seq_len_formula"], "requested_target_length + 1")
        self.assertFalse(mapped["production_budget_satisfied"])
        alias = schedule_producer(max_formula="requested_length_plus_1")
        self.assertEqual(analysis.map_schedule_provenance(alias)["max_seq_len_formula"], "requested_target_length + 1")
        broken = schedule_producer(max_seq_offset=2)
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.map_schedule_provenance(broken)
        self.assertEqual(caught.exception.code, "schedule_invalid")
        large = schedule_producer(total=1000)
        large["max_chunk_size"] = 16
        mapped_large = analysis.map_schedule_provenance(large)
        self.assertEqual(mapped_large["attempt_count"], 1000)
        self.assertEqual(mapped_large["final_d1_attempt_budget"], 30000)
        self.assertFalse(mapped_large["production_budget_satisfied"])
        self.assertFalse(mapped_large["diagnostic_attempt_count_is_final_d1_budget"])

    def test_b2_mapper_rejects_generic_seed_and_does_not_assume_42(self):
        mapped = analysis.map_b2_producer_batch([{"record_id": "b2-a", "seed": 99}, {"record_id": "b2-b", "seed": 99}])
        self.assertEqual(mapped["empirical_null_seed"], 99)
        self.assertTrue(all("seed" not in row and "training_seed" not in row for row in mapped["records"]))
        self.assertFalse(mapped["production_seed_42_assumed"])
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.map_b2_producer_batch([{"seed": 99}, {"seed": 100}])
        self.assertEqual(caught.exception.code, "b2_multiple_seeds")
        with self.assertRaises(analysis.AnalysisContractError):
            analysis.map_b2_producer_batch([{"seed": "99"}])
        with self.assertRaises(analysis.AnalysisContractError):
            analysis.map_b2_producer_batch([{"seed": 7, "training_seed": 7}])

    def test_b0_exact_hit_is_not_applicable_and_external(self):
        report = analysis.analyse(default_document())
        panel = report["b0_panel"]
        self.assertTrue(panel["external_comparator"])
        self.assertEqual(panel["length_regime"], "historical_37nt")
        self.assertEqual(panel["requested_biological_length"], "unavailable")
        self.assertEqual(panel["exact_hit_applicability"], "not_applicable")
        self.assertFalse(panel["included_in_b1_d1_controlled_comparison"])
        self.assertFalse(panel["included_in_directional_consistency"])
        self.assertFalse(panel["historical_generation_seeds_are_training_replicates"])
        self.assertEqual(report["conditions"]["B0"]["accounting"]["exact_hit_applicability"], "not_applicable")
        self.assertIsNone(report["conditions"]["B0"]["accounting"]["exact_hit_rate"])

    def test_guardrail_failure_stays_visible(self):
        first = d1_row("guard-a", "ACGUACGU", 91001, invocation_index=1, batch_position=0, attempt=0)
        second = d1_row("guard-b", "ACGUACGU", 91001, invocation_index=1, batch_position=1, attempt=1)
        document = envelope(
            [first, second, b1_row("guard-b1", "GGGGCCCC"), b0_row("guard-b0"), b2_row("guard-b2")],
            ["UUUUUUUU"],
            [reference("ref-a", "GGGGCCCC")],
        )
        report = analysis.analyse(document)
        failures = report["guardrail_policy"]["failures"]
        self.assertTrue(any(item["id"] == "largest_duplicate_share" for item in failures))
        self.assertTrue(any(item["id"] == "unique_fraction" for item in failures))
        self.assertFalse(report["guardrail_policy"]["failure_authorizes_replacement"])
        self.assertFalse(report["guardrail_policy"]["failure_authorizes_exclusion_after_eval"])
        self.assertFalse(report["guardrail_policy"]["failure_is_a_closeness_vote"])
        self.assertFalse(report["guardrail_policy"]["final_pool_used"])

    def test_injected_fold_is_deterministic_and_viennarna_is_not_used(self):
        with open(os.path.join(ROOT, "scripts/modelling/generator_eval_analysis.py"), encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("ViennaRNA", source)
        self.assertNotIn("import RNA", source)
        calls = []

        def fold(sequence):
            calls.append(sequence)
            return ("." * len(sequence), -2.0 * len(sequence))

        report = analysis.analyse(default_document(), fold=fold)
        self.assertTrue(calls)
        self.assertFalse(report["viennarna_called"])
        self.assertEqual(report["conditions"]["D1"]["structure"]["mfe_per_nt.median"], -2.0)
        self.assertEqual(report["conditions"]["D1"]["structure"]["paired_fraction.median"], 0.0)
        self.assertFalse(report["conditions"]["D1"]["structure"]["new_mfe_formula_defined"])

    def test_empty_and_all_invalid_inputs_do_not_fabricate_values(self):
        empty = envelope([], ["UUUUUUUU"], [reference("ref-a", "ACGUACGU")])
        empty_report = analysis.analyse(empty)
        self.assertIsNone(empty_report["conditions"]["B1"]["pooled_gc_fraction"])
        self.assertIsNone(empty_report["conditions"]["D1"]["closeness"]["nearest_reference_normalized_edit_distance"]["value"])
        self.assertEqual(empty_report["b1_d1_directional_consistency"]["label"], "not_applicable")
        invalid = b1_row("bad-b1", "ACGUACGU")
        mark_invalid_nonempty(invalid, "ACGTACGT")
        unparsed = d1_row("bad-d1", "ACGUACGU", 91001, invocation_index=2)
        mark_unparsed(unparsed)
        unparsed["requested_length"] = 8
        report = analysis.analyse(envelope([invalid, unparsed, b0_row("bad-b0"), b2_row("bad-b2")], ["UUUUUUUU"], [reference("ref-a", "ACGUACGU")]))
        self.assertEqual(report["conditions"]["B1"]["successfully_parsed_outputs"], 1)
        self.assertEqual(report["conditions"]["B1"]["generated_valid_row_denominator"], 0)
        self.assertIsNone(report["conditions"]["B1"]["pooled_gc_fraction"])
        self.assertIsNone(report["conditions"]["B1"]["closeness"]["nucleotide_total_variation_to_reference"]["value"])
        self.assertNotEqual(report["conditions"]["B1"]["closeness"]["nucleotide_total_variation_to_reference"]["value"], 0)

    def test_report_and_cli_contain_no_sequences_or_held_out_data(self):
        document = default_document()
        report = analysis.analyse(document)
        encoded = json.dumps(report)
        sequences = ["ACGUACGU", "ACGUACGA", "GGGGCCCC", "UUUUUUUU", "CCCCCCCC", "UUUUCCCC"]
        sequences.append("ACGUACGUACGUACGUACGUACGUACGUACGUACGU")
        for sequence in sequences:
            self.assertNotIn(sequence, encoded)
        self.assertNotIn("EVAL", report["reference_role"])
        self.assertFalse(report["production_train_loaded"])
        self.assertFalse(report["production_pools_loaded"])
        self.assertFalse(report["checkpoints_loaded"])
        buffer = StringIO()
        with redirect_stdout(buffer):
            status = analysis.main([])
        text = buffer.getvalue()
        self.assertEqual(status, 0)
        self.assertIn("mode: synthetic_analysis", text)
        self.assertIn("EVAL access: locked", text)
        self.assertIn("only synthetic TRAIN/reference fixtures used", text)
        self.assertIn("no EVAL, REF or VALIDATION data loaded", text)
        self.assertIn("metric_count: 35", text)
        self.assertIn("unresolved_item_count: 6", text)
        for sequence in sequences:
            self.assertNotIn(sequence, text)
        formula_hashes = {
            "scripts/modelling/m4_diagnostic_metrics.py": "eebb6c8faf0d909bd907cd1e1e09c75908676ffe3e4eb04842f09b943b9d9e56",
            "scripts/modelling/m6_diagnostic_generation.py": "83f299bea7ec69406c898ad0e971bebf06056beb58649de0c25a5cc6d7195726",
            "config/modelling/validation_metrics_v1.yaml": "d30006c6f2b94be89ee2c7721b701e76e6835142a1af9f49997ba0d5baadf4bb",
        }
        for relative, digest in formula_hashes.items():
            with open(os.path.join(ROOT, relative), "rb") as handle:
                payload = handle.read()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)


class ReviewedCoverageTests(unittest.TestCase):
    def _closeness_keys(self):
        return (
            "nearest_reference_normalized_edit_distance",
            "nucleotide_total_variation_to_reference",
            "dinucleotide_total_variation_to_reference",
        )

    def test_b0_and_b2_report_closeness_gc_and_denominators(self):
        report = analysis.analyse(default_document())
        for condition in ("B0", "B1", "B2", "D1"):
            block = report["conditions"][condition]
            self.assertEqual(block["successfully_parsed_outputs"], 1)
            self.assertEqual(block["raw_attempts"], 1)
            self.assertEqual(block["generated_valid_row_denominator"], 1)
            self.assertEqual(block["generated_unique_valid_count"], 1)
            self.assertEqual(block["reference_unique_core_denominator"], 2)
            self.assertIsNotNone(block["pooled_gc_fraction"])
            self.assertIsNone(block["pooled_gc_undefined_reason"])
            for key in self._closeness_keys():
                metric = block["closeness"][key]
                self.assertIsNotNone(metric["value"])
                self.assertIsNone(metric["undefined_reason"])
                self.assertEqual(metric["generated_valid_row_denominator"], 1)
                self.assertEqual(metric["generated_unique_valid_count"], 1)
                self.assertEqual(metric["reference_unique_core_denominator"], 2)
                self.assertEqual(metric["direction"], "lower")
        b0 = report["conditions"]["B0"]
        self.assertEqual(b0["exact_hit_applicability"], "not_applicable")
        self.assertIsNone(b0["exact_hit_rate"])
        self.assertNotEqual(b0["exact_hit_rate"], 0)
        self.assertEqual(b0["accounting"]["exact_hit_applicability"], "not_applicable")
        self.assertIsNone(b0["accounting"]["exact_hit_rate"])
        self.assertEqual(b0["requested_biological_length"], "unavailable")
        self.assertEqual(b0["parsed_outputs"], 1)
        self.assertEqual(b0["parsed_outputs_applicability"], "applicable")
        self.assertIsNone(b0["parsed_outputs_status_reason"])
        self.assertEqual(b0["output_accounting"]["parsed_outputs"], b0["raw_attempts"])
        self.assertEqual(b0["older_m4_metrics"]["parsed_outputs"]["value"], 1)
        self.assertEqual(b0["older_m4_metrics"]["exact_hit_rate"]["applicability"], "not_applicable")
        self.assertIsNone(b0["checkpoint_eligible"])
        self.assertFalse(b0["closeness_in_directional_consistency"])
        self.assertFalse(b0["included_in_b1_d1_controlled_comparison"])
        b2 = report["conditions"]["B2"]
        self.assertEqual(b2["empirical_null_seed"], 77001)
        self.assertFalse(b2["is_training_replicate"])
        self.assertFalse(b2["rows_are_training_replicates"])
        self.assertFalse(b2["closeness_in_directional_consistency"])
        self.assertFalse(b2["included_in_b1_d1_controlled_comparison"])
        self.assertEqual(b2["parsed_outputs"], 1)
        self.assertEqual(b2["parsed_outputs_applicability"], "applicable")
        self.assertEqual(b2["older_m4_metrics"]["parsed_outputs"]["value"], 1)
        self.assertEqual(b2["exact_hit_rate"], 1.0)
        self.assertEqual(b2["exact_hit_rate"], b2["accounting"]["exact_hit_rate"])
        self.assertEqual(b2["exact_hit_rate"], b2["older_m4_metrics"]["exact_hit_rate"]["value"])
        self.assertIsNone(b2["checkpoint_eligible"])
        consistency = report["b1_d1_directional_consistency"]
        self.assertEqual(consistency["applies_to_conditions"], ["B1", "D1"])
        self.assertFalse(consistency["applied_to_b0"])
        self.assertFalse(consistency["applied_to_b2"])
        self.assertFalse(report["matched_b1_d1_blocks"]["includes_b0"])
        self.assertFalse(report["matched_b1_d1_blocks"]["includes_b2"])
        self.assertEqual(report["b0_panel"]["exact_hit_applicability"], "not_applicable")
        schedule = report["schedule_provenance"]
        self.assertFalse(schedule["diagnostic_attempt_count_is_final_d1_budget"])
        self.assertEqual(schedule["final_d1_attempt_budget"], 30000)
        self.assertFalse(schedule["production_budget_satisfied"])

    def test_stratified_b0_and_b2_keep_short_and_long_results(self):
        short_b1 = b1_row("rev-b1-s", "AAAAAAAA", invocation_index=1, batch_position=0, attempt=0)
        long_b1 = b1_row("rev-b1-l", "GGGGGGGG", invocation_index=1, batch_position=1, attempt=1)
        short_d1 = d1_row("rev-d1-s", "AAAAAAAA", 91001, invocation_index=1, batch_position=0, attempt=0)
        long_d1 = d1_row("rev-d1-l", "ACGUACGU", 91001, invocation_index=1, batch_position=1, attempt=1)
        b0 = b0_row("rev-b0")
        b2 = b2_row("rev-b2")
        for row, label in (
            (short_b1, "short"),
            (long_b1, "long"),
            (short_d1, "short"),
            (long_d1, "long"),
            (b0, "long"),
            (b2, "short"),
        ):
            row["s6_length_stratum"] = label
            row["s6_assignment_provenance"] = "s6-gep2-synthetic-assignment"
        document = envelope(
            [short_b1, long_b1, short_d1, long_d1, b2, b0],
            ["UUUUUUUU"],
            [reference("ref-s", "AAAAAAAA", "short"), reference("ref-l", "GGGGGGGG", "long")],
            stratified=True,
            s6_assignment_provenance="s6-gep2-synthetic-assignment",
        )
        report = analysis.analyse(document)
        for condition in ("B0", "B1", "B2", "D1"):
            stratified = report["conditions"][condition]["stratified"]
            self.assertEqual(set(stratified), {"short", "long"})
            for label in ("short", "long"):
                stratum = stratified[label]
                self.assertIn("pooled_gc_fraction", stratum)
                self.assertIn("successfully_parsed_outputs", stratum)
                self.assertIn("parsed_outputs", stratum)
                self.assertIn("closeness", stratum)
                for key in self._closeness_keys():
                    self.assertIn("generated_valid_row_denominator", stratum["closeness"][key])
                    self.assertIn("reference_unique_core_denominator", stratum["closeness"][key])
                self.assertFalse(stratum["stratum_inferred_from_length"])
        self.assertEqual(report["conditions"]["B0"]["stratified"]["long"]["generated_valid_row_denominator"], 1)
        self.assertEqual(report["conditions"]["B0"]["stratified"]["short"]["generated_valid_row_denominator"], 0)
        self.assertIsNone(report["conditions"]["B0"]["stratified"]["short"]["pooled_gc_fraction"])
        self.assertEqual(report["conditions"]["B0"]["stratified"]["short"]["pooled_gc_undefined_reason"], "no_canonical_bases")
        self.assertEqual(report["conditions"]["B2"]["stratified"]["short"]["generated_valid_row_denominator"], 1)
        self.assertEqual(report["conditions"]["B0"]["stratified"]["short"]["parsed_outputs"], 0)
        self.assertEqual(report["conditions"]["B0"]["stratified"]["short"]["parsed_outputs_applicability"], "applicable")
        self.assertEqual(report["conditions"]["B0"]["stratified"]["long"]["parsed_outputs"], 1)

    def test_empty_ledger_counts_are_zero_and_ratios_stay_null(self):
        report = analysis.analyse(envelope([], ["UUUUUUUU"], [reference("ref-a", "ACGUACGU")]))
        for condition in ("B0", "B1", "B2", "D1"):
            block = report["conditions"][condition]
            self.assertEqual(block["accounting"]["attempted"], 0)
            self.assertEqual(block["accounting"]["valid_acgu"], 0)
            self.assertEqual(block["accounting"]["unique_valid"], 0)
            self.assertEqual(block["successfully_parsed_outputs"], 0)
            self.assertEqual(block["raw_attempts"], 0)
            self.assertEqual(block["generated_valid_row_denominator"], 0)
            self.assertEqual(block["generated_unique_valid_count"], 0)
            self.assertIsNone(block["pooled_gc_fraction"])
            self.assertEqual(block["pooled_gc_undefined_reason"], "no_canonical_bases")
            self.assertNotEqual(block["pooled_gc_fraction"], 0)
            for key in self._closeness_keys():
                metric = block["closeness"][key]
                self.assertIsNone(metric["value"])
                self.assertIsNotNone(metric["undefined_reason"])
                self.assertNotEqual(metric["value"], 0)
            self.assertIsNone(block["structure"]["mfe_per_nt"])
            self.assertIsNone(block["structure"]["paired_fraction"])
            self.assertIsNotNone(block["structure"]["undefined_reason"])
        self.assertEqual(report["conditions"]["B1"]["parsed_outputs"], 0)
        self.assertEqual(report["conditions"]["D1"]["parsed_outputs"], 0)
        self.assertEqual(report["conditions"]["B1"]["parsed_outputs_applicability"], "applicable")
        self.assertEqual(report["conditions"]["B0"]["parsed_outputs"], 0)
        self.assertEqual(report["conditions"]["B0"]["parsed_outputs_applicability"], "applicable")
        self.assertEqual(report["conditions"]["B2"]["parsed_outputs"], 0)
        self.assertEqual(report["conditions"]["B2"]["parsed_outputs_applicability"], "applicable")
        self.assertEqual(report["conditions"]["B0"]["exact_hit_applicability"], "not_applicable")
        self.assertIsNone(report["conditions"]["B0"]["exact_hit_rate"])
        self.assertEqual(report["conditions"]["B2"]["exact_hit_rate"], 0.0)
        self.assertEqual(report["conditions"]["B2"]["accounting"]["exact_hit_rate"], 0.0)
        self.assertEqual(report["conditions"]["B2"]["older_m4_metrics"]["exact_hit_rate"]["value"], 0.0)
        self.assertIsNone(report["conditions"]["B0"]["guardrail_values"]["unique_fraction"])
        self.assertIsNone(report["conditions"]["B2"]["guardrail_values"]["exact_train_match_rate"])
        self.assertIsNone(report["conditions"]["B0"]["checkpoint_eligible"])
        self.assertIsNone(report["conditions"]["B2"]["checkpoint_eligible"])
        self.assertIsNone(report["conditions"]["B1"]["guardrail_values"]["unique_fraction"])
        self.assertNotEqual(report["conditions"]["B1"]["guardrail_values"]["unique_fraction"], 0)

    def test_internally_valid_unrelated_schedule_is_rejected(self):
        unrelated = schedule_producer()
        mapped = analysis.map_schedule_provenance(unrelated)
        self.assertEqual(mapped["attempt_count"], 2)
        self.assertFalse(mapped["diagnostic_attempt_count_is_final_d1_budget"])
        self.assertEqual(mapped["final_d1_attempt_budget"], 30000)
        document = default_document()
        document["schedule_producer"] = unrelated
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.analyse(document)
        self.assertEqual(caught.exception.code, "schedule_ledger_mismatch")
        self.assertNotIn("ACGUACGU", caught.exception.detail)

    def test_duplicate_and_inconsistent_invocation_coverage_is_rejected(self):
        duplicate = schedule_producer(total=2)
        duplicate["invocations"][1]["invocation_index"] = 0
        duplicate["invocations"][1]["invocation_seed"] = duplicate["generation_seed_base"]
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.map_schedule_provenance(duplicate)
        self.assertEqual(caught.exception.code, "schedule_invalid")
        inconsistent = schedule_producer()
        inconsistent["sampled_target_lengths"][0] = 7
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.map_schedule_provenance(inconsistent)
        self.assertEqual(caught.exception.code, "schedule_invalid")
        extra = default_document()
        extra["records"].append(
            b1_row(
                "extra-b1",
                "GGGGCCCC",
                invocation_index=2,
                batch_position=0,
                attempt=1,
                length_vector_sha256=extra["schedule_producer"]["length_vector_sha256"],
            )
        )
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.analyse(extra)
        self.assertEqual(caught.exception.code, "schedule_ledger_mismatch")
        missing = default_document()
        missing["records"] = [row for row in missing["records"] if row["condition"] != "B1"]
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.analyse(missing)
        self.assertEqual(caught.exception.code, "schedule_ledger_mismatch")

    def test_two_d1_training_seeds_in_one_invocation_stay_separate(self):
        b1 = b1_row("two-seed-b1", "ACGUACGU", invocation_index=1, batch_position=0, attempt=0)
        first = d1_row("two-seed-d1-a", "ACGUACGA", 91001, invocation_index=1, batch_position=0, attempt=0)
        second = d1_row("two-seed-d1-b", "GGGGCCCC", 91002, invocation_index=1, batch_position=0, attempt=0)
        document = envelope(
            [b1, first, second, b0_row("two-seed-b0"), b2_row("two-seed-b2")],
            ["UUUUUUUU"],
            [reference("ref-a", "ACGUACGU")],
        )
        report = analysis.analyse(document)
        blocks = report["matched_b1_d1_blocks"]["matched_blocks"]
        self.assertEqual(len(blocks), 2)
        self.assertEqual([block["training_seed"] for block in blocks], [91001, 91002])
        self.assertEqual({block["invocation_index"] for block in blocks}, {1})
        for block in blocks:
            self.assertEqual(block["d1"]["generated_valid_row_denominator"], 1)
            self.assertEqual(block["b1"]["generated_valid_row_denominator"], 1)
            self.assertNotEqual(block["d1"]["generated_valid_row_denominator"], 2)
            self.assertFalse(block["pooled_across_d1_training_seeds"])
            self.assertFalse(block["is_training_replicate"])
            self.assertIsNone(block["p_value"])
            self.assertIsNone(block["confidence_interval"])
            self.assertTrue(block["b1_comparator_reused_across_d1_training_seeds"])
            self.assertFalse(block["b1_reuse_creates_additional_independent_b1_replicates"])
            self.assertIn("does not create additional independent B1 replicates", block["b1_reuse_statement"])
            self.assertEqual(block["d1"]["training_seed"], block["training_seed"])
            for key in self._closeness_keys():
                self.assertIn(key, block["b1"]["closeness_values"])
                self.assertIn(key, block["d1"]["closeness_values"])
            self.assertIn("nearest_reference_normalized_edit_distance.median", block["d1_minus_b1"])
            self.assertIn("nucleotide_total_variation_to_reference", block["d1_minus_b1"])
            self.assertIn("dinucleotide_total_variation_to_reference", block["d1_minus_b1"])
            self.assertIn("directional_consistency", block)
        self.assertTrue(report["matched_b1_d1_blocks"]["b1_comparator_reused_across_d1_training_seeds"])
        self.assertFalse(report["matched_b1_d1_blocks"]["b1_reuse_creates_additional_independent_b1_replicates"])
        self.assertFalse(report["matched_b1_d1_blocks"]["matched_blocks_pool_d1_training_seeds"])

    def test_metric_spec_length_treatment_distinguishes_the_three_closeness_metrics(self):
        spec = preflight.load_metric_spec()
        by_id = {metric["metric_id"]: metric for metric in spec["metrics"]}
        nearest = by_id["nearest_reference_normalized_edit_distance"]
        nucleotide = by_id["nucleotide_total_variation_to_reference"]
        dinucleotide = by_id["dinucleotide_total_variation_to_reference"]
        self.assertIn("longer sequence", nearest["length_treatment"].lower())
        self.assertIn("pooled", nucleotide["length_treatment"].lower())
        self.assertIn("base", nucleotide["length_treatment"].lower())
        self.assertNotIn("longer sequence", nucleotide["length_treatment"].lower())
        self.assertIn("overlapping", dinucleotide["length_treatment"].lower())
        self.assertIn("shorter than 2", dinucleotide["length_treatment"].lower())
        self.assertNotIn("longer sequence", dinucleotide["length_treatment"].lower())
        self.assertEqual(spec["freeze_status"], "draft")
        for metric in (nearest, nucleotide, dinucleotide):
            handling = metric["missing_failure_handling"].lower()
            self.assertNotIn("paired fraction", handling)
            self.assertNotIn("null paired", handling)
            self.assertIn("caller", handling)
            self.assertIn("empty generated", handling)
            self.assertEqual(metric["direction"], "lower")
            self.assertEqual(metric["freeze_status"], "draft")
            self.assertEqual(metric["reference_role"], "synthetic_eval_stand_in")
            self.assertIn("B0", metric["condition_scope"])
            self.assertIn("B1", metric["condition_scope"])
            self.assertIn("B2", metric["condition_scope"])
            self.assertIn("D1", metric["condition_scope"])
            self.assertIn("not_applicable", metric["condition_scope"])
            self.assertIn("Synthetic-reference-only", metric["calculation_summary"])


def length_schedule(ordered, sampled):
    base = 44000
    invocations = []
    for index, target in enumerate(sampled):
        invocations.append(
            {
                "invocation_index": index,
                "invocation_seed": base + index,
                "target_length": target,
                "max_seq_len": target + 1,
                "batch_num": 1,
                "actual_chunk_size": 1,
                "original_attempt_indexes": [index],
            }
        )
    return {
        "sampling_seed": 43000,
        "generation_seed_base": base,
        "seed_formula": "%d + invocation_index" % base,
        "max_seq_len_formula": "sampled_target_length + 1",
        "max_chunk_size": 16,
        "batch_num": 1,
        "total_attempts": len(sampled),
        "sampled_target_lengths": list(sampled),
        "ordered_lengths": list(ordered),
        "length_vector_sha256": analysis._length_vector_sha256(list(ordered)),
        "invocations": invocations,
    }


def partition_schedule():
    ordered = [8]
    base = 88000
    sampling = 99001
    digest = analysis._length_vector_sha256(ordered)
    return {
        "sampling_seed": sampling,
        "generation_seed_base": base,
        "seed_formula": "generation_seed_base + invocation_index",
        "max_seq_len_formula": "requested_target_length + 1",
        "max_chunk_size": 16,
        "batch_num": 1,
        "total_attempts": 2,
        "sampled_target_lengths": [8, 8],
        "ordered_lengths": ordered,
        "length_vector_sha256": digest,
        "invocations": [
            {
                "invocation_index": 1,
                "invocation_seed": base + 1,
                "target_length": 8,
                "max_seq_len": 9,
                "batch_num": 1,
                "original_attempt_indexes": [0, 1],
                "expected_batch_positions": [0, 1],
            }
        ],
    }, digest


def partition_rows(digest, d1_rows):
    common = {"length_vector_sha256": digest, "base": 88000, "invocation_index": 1, "requested": 8}
    b1_rows = [
        b1_row("part-b1-a", "AAAAAAAA", batch_position=0, attempt=0, **common),
        b1_row("part-b1-b", "GGGGGGGG", batch_position=1, attempt=1, **common),
    ]
    return b1_rows + d1_rows + [b0_row("part-b0"), b2_row("part-b2")]


class Revision2ContractTests(unittest.TestCase):
    def test_sampled_lengths_must_occur_in_the_source_vector(self):
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.map_schedule_provenance(length_schedule([99], [4, 8]))
        self.assertEqual(caught.exception.code, "schedule_invalid")
        reused = analysis.map_schedule_provenance(length_schedule([8], [8, 8]))
        self.assertEqual(reused["attempt_count"], 2)
        repeated_source = analysis.map_schedule_provenance(length_schedule([4, 4], [4, 4]))
        self.assertEqual(repeated_source["attempt_count"], 2)
        self.assertFalse(reused["d1_training_seeds_each_receive_full_budget"])
        self.assertTrue(reused["final_d1_attempt_budget_is_total_across_retained_seeds"])

    def test_two_d1_seeds_may_partition_one_schedule(self):
        schedule, digest = partition_schedule()
        common = {"length_vector_sha256": digest, "base": 88000, "invocation_index": 1, "requested": 8}
        rows = partition_rows(
            digest,
            [
                d1_row("part-d1-a", "AAAAAAAA", 91001, batch_position=0, attempt=0, **common),
                d1_row("part-d1-b", "GGGGGGGG", 91002, batch_position=1, attempt=1, **common),
            ],
        )
        report = analysis.analyse(
            envelope(rows, ["UUUUUUUU"], [reference("ref-a", "AAAAAAAA")], schedule_producer=schedule)
        )
        binding = report["schedule_provenance"]["ledger_binding"]
        self.assertEqual(binding["scheduled_attempt_count"], 2)
        self.assertEqual(binding["b1_attempt_count"], 2)
        self.assertEqual(binding["d1_attempt_count"], 2)
        self.assertNotEqual(binding["d1_attempt_count"], binding["scheduled_attempt_count"] * 2)
        self.assertEqual(
            sum(item["attempt_count"] for item in binding["d1_attempt_count_by_training_seed"]),
            binding["scheduled_attempt_count"],
        )
        self.assertEqual(
            binding["d1_attempt_count_by_training_seed"],
            [{"training_seed": 91001, "attempt_count": 1}, {"training_seed": 91002, "attempt_count": 1}],
        )
        self.assertTrue(binding["d1_union_covers_schedule_exactly_once"])
        self.assertTrue(binding["final_d1_attempt_budget_is_total_across_retained_seeds"])
        self.assertFalse(binding["d1_training_seeds_each_receive_full_budget"])
        self.assertFalse(binding["production_budget_satisfied"])
        self.assertEqual(report["d1_by_training_seed"]["d1_training_seeds"], [91001, 91002])
        self.assertEqual(
            [block["row_count"] for block in report["d1_by_training_seed"]["by_training_seed"]],
            [1, 1],
        )
        blocks = {block["training_seed"]: block for block in report["matched_b1_d1_blocks"]["matched_blocks"]}
        self.assertEqual(sorted(blocks), [91001, 91002])
        only_a = analysis.nucleotide_total_variation_to_reference(["AAAAAAAA"], ["AAAAAAAA"])
        pooled = analysis.nucleotide_total_variation_to_reference(["AAAAAAAA", "GGGGGGGG"], ["AAAAAAAA"])
        self.assertEqual(blocks[91001]["original_attempt_indexes"], [0])
        self.assertEqual(blocks[91002]["original_attempt_indexes"], [1])
        for seed, attempt in ((91001, [0]), (91002, [1])):
            block = blocks[seed]
            self.assertEqual(block["b1_original_attempt_indexes"], attempt)
            self.assertEqual(block["b1"]["generated_valid_row_denominator"], 1)
            self.assertEqual(block["d1"]["generated_valid_row_denominator"], 1)
            self.assertEqual(block["b1_invocation_row_count"], 2)
            self.assertFalse(block["compared_with_entire_b1_invocation"])
            self.assertFalse(block["pooled_across_d1_training_seeds"])
            self.assertFalse(block["b1_comparator_reused_across_d1_training_seeds"])
        self.assertEqual(
            blocks[91001]["b1"]["closeness_values"]["nucleotide_total_variation_to_reference"],
            only_a["value"],
        )
        self.assertNotEqual(
            blocks[91001]["b1"]["closeness_values"]["nucleotide_total_variation_to_reference"],
            pooled["value"],
        )
        self.assertFalse(report["matched_b1_d1_blocks"]["matched_blocks_pool_d1_training_seeds"])

    def test_repeated_missing_and_extra_d1_attempts_are_rejected(self):
        schedule, digest = partition_schedule()
        common = {"length_vector_sha256": digest, "base": 88000, "invocation_index": 1, "requested": 8}

        def run(d1_rows):
            document = envelope(
                partition_rows(digest, d1_rows),
                ["UUUUUUUU"],
                [reference("ref-a", "AAAAAAAA")],
                schedule_producer=schedule,
            )
            analysis.analyse(document)

        repeated = [
            d1_row("rep-a0", "AAAAAAAA", 91001, batch_position=0, attempt=0, **common),
            d1_row("rep-a1", "GGGGGGGG", 91001, batch_position=1, attempt=1, **common),
            d1_row("rep-b0", "AAAAAAAA", 91002, batch_position=0, attempt=0, **common),
            d1_row("rep-b1", "GGGGGGGG", 91002, batch_position=1, attempt=1, **common),
        ]
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            run(repeated)
        self.assertEqual(caught.exception.code, "schedule_ledger_mismatch")
        missing = [d1_row("miss-a", "AAAAAAAA", 91001, batch_position=0, attempt=0, **common)]
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            run(missing)
        self.assertEqual(caught.exception.code, "schedule_ledger_mismatch")
        duplicated = [
            d1_row("dup-a", "AAAAAAAA", 91001, batch_position=0, attempt=0, **common),
            d1_row("dup-b", "AAAAAAAA", 91002, batch_position=0, attempt=0, **common),
            d1_row("dup-c", "GGGGGGGG", 91001, batch_position=1, attempt=1, **common),
        ]
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            run(duplicated)
        self.assertEqual(caught.exception.code, "schedule_ledger_mismatch")
        extra = [
            d1_row("extra-a", "AAAAAAAA", 91001, batch_position=0, attempt=0, **common),
            d1_row("extra-b", "GGGGGGGG", 91002, batch_position=1, attempt=1, **common),
            d1_row("extra-c", "CCCCCCCC", 91002, invocation_index=2, batch_position=0, attempt=2, requested=8, length_vector_sha256=digest),
        ]
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            run(extra)
        self.assertEqual(caught.exception.code, "schedule_ledger_mismatch")
        unassigned = schedule_producer()
        for invocation in unassigned["invocations"]:
            del invocation["original_attempt_indexes"]
        document = default_document()
        document["schedule_producer"] = unassigned
        with self.assertRaises(analysis.AnalysisContractError) as caught:
            analysis.analyse(document)
        self.assertEqual(caught.exception.code, "schedule_ledger_mismatch")
        self.assertIn("global D1 attempt assignment", caught.exception.detail)

    def test_b0_and_b2_accounting_is_numeric_and_descriptive(self):
        matched = b0_row("acct-b0-match", sequence="UUUUUUUU")
        duplicate = b0_row("acct-b0-dup", sequence="UUUUUUUU", seed=96002)
        invalid = b0_row("acct-b0-bad")
        mark_invalid_nonempty(invalid, "ACGTACGT")
        empty = b0_row("acct-b0-empty")
        mark_unparsed(empty)
        hit = b2_row("acct-b2-hit", sequence="AAAA")
        miss = b2_row("acct-b2-miss", sequence="AAAAAAAA")
        miss["requested_length"] = 4
        rejected = b2_row("acct-b2-bad", sequence="UUUUCCCC")
        mark_invalid_nonempty(rejected, "ACGTACGT")
        document = envelope(
            [
                matched,
                duplicate,
                invalid,
                empty,
                hit,
                miss,
                rejected,
                b1_row("acct-b1", "ACGUACGU"),
                d1_row("acct-d1", "ACGUACGA", 91001),
            ],
            ["UUUUUUUU"],
            [reference("ref-a", "AAAAAAAA")],
        )
        report = analysis.analyse(document)
        metrics = analysis._m4()
        b0 = report["conditions"]["B0"]
        b2 = report["conditions"]["B2"]
        self.assertEqual(b0["raw_attempts"], 4)
        self.assertEqual(b0["parsed_outputs"], 4)
        self.assertEqual(b0["successfully_parsed_outputs"], 3)
        self.assertEqual(b0["output_accounting"]["valid_outputs"], 2)
        self.assertEqual(b0["output_accounting"]["invalid_outputs"], 2)
        self.assertEqual(b0["output_accounting"]["empty_or_unparseable_outputs"], 1)
        self.assertEqual(b0["output_accounting"]["unique_valid_outputs"], 1)
        self.assertEqual(b0["output_accounting"]["duplicates"], 1)
        self.assertEqual(b0["output_accounting"]["largest_duplicate_multiplicity"], 2)
        self.assertEqual(b0["output_accounting"]["largest_duplicate_share"], 1.0)
        self.assertEqual(b0["output_accounting"]["largest_duplicate_share_denominator"], "valid_outputs")
        self.assertEqual(b0["output_accounting"]["largest_duplicate_share_denominator_count"], 2)
        self.assertEqual(b0["guardrail_values"]["exact_train_match_rate"], 1.0)
        self.assertEqual(b0["guardrail_values"]["valid_nonempty_acgu_fraction"], 2 / 4)
        self.assertEqual(b0["exact_hit_applicability"], "not_applicable")
        self.assertIsNone(b0["exact_hit_rate"])
        self.assertIsNone(b0["accounting"]["exact_hit_rate"])
        self.assertEqual(b0["older_m4_metrics"]["exact_hit_rate"]["applicability"], "not_applicable")
        self.assertEqual(b0["older_m6_metrics"]["per_requested_length_exact_hit_rate"]["applicability"], "not_applicable")
        self.assertEqual(b0["older_m4_metrics"]["eos_marker_observations"]["applicability"], "not_applicable")
        self.assertEqual(b2["raw_attempts"], 3)
        self.assertEqual(b2["parsed_outputs"], 3)
        self.assertEqual(b2["successfully_parsed_outputs"], 3)
        self.assertEqual(b2["output_accounting"]["valid_outputs"], 2)
        self.assertEqual(b2["output_accounting"]["invalid_outputs"], 1)
        self.assertEqual(b2["output_accounting"]["empty_or_unparseable_outputs"], 0)
        self.assertEqual(b2["output_accounting"]["unique_valid_outputs"], 2)
        self.assertEqual(b2["output_accounting"]["duplicates"], 0)
        self.assertEqual(b2["output_accounting"]["largest_duplicate_multiplicity"], 1)
        self.assertEqual(b2["output_accounting"]["largest_duplicate_share"], 0.5)
        self.assertEqual(b2["guardrail_values"]["exact_train_match_rate"], 0.0)
        self.assertEqual(b2["exact_hit_rate"], 1 / 3)
        self.assertEqual(b2["accounting"]["exact_hit_rate"], b2["exact_hit_rate"])
        self.assertEqual(b2["older_m4_metrics"]["exact_hit_rate"]["value"], b2["exact_hit_rate"])
        self.assertEqual(b2["older_m4_metrics"]["exact_hit_rate"]["applicability"], "applicable")
        per_length = b2["older_m6_metrics"]["per_requested_length_exact_hit_rate"]
        self.assertEqual(per_length["applicability"], "applicable")
        by_length = {item["requested_length"]: item for item in per_length["value"]}
        self.assertEqual(by_length[4]["exact_hit_rate"], 0.5)
        self.assertEqual(by_length[4]["raw_attempts"], 2)
        self.assertEqual(by_length[8]["exact_hit_rate"], 0.0)
        self.assertEqual(by_length[8]["raw_attempts"], 1)
        failures = {item["condition"] for item in report["guardrail_policy"]["failures"]}
        for block in (b0, b2):
            self.assertIsNone(block["checkpoint_eligible"])
            self.assertFalse(block["checkpoint_eligibility_applied"])
            self.assertEqual(block["guardrail_failures"], [])
            self.assertNotIn("invocation_seed", block)
            for decision in block["guardrail_decisions"]:
                self.assertIsNone(decision["passed"])
                self.assertEqual(decision["status"], "descriptive_not_checkpoint_eligibility")
                self.assertFalse(decision["is_checkpoint_eligibility_decision"])
                self.assertFalse(decision["is_a_closeness_vote"])
                rule = metrics.GUARDRAIL_THRESHOLDS[decision["id"]]
                self.assertEqual(decision["comparison"], rule["comparison"])
                self.assertEqual(decision["threshold"], rule["threshold"])
                self.assertEqual(decision["threshold_provenance"], "m4_diagnostic_metrics.GUARDRAIL_THRESHOLDS")
                self.assertIn("denominator_count", decision)
        self.assertNotIn("B0", failures)
        self.assertNotIn("B2", failures)

    def test_empty_b0_and_b2_ratios_stay_null(self):
        report = analysis.analyse(envelope([], ["UUUUUUUU"], [reference("ref-a", "ACGUACGU")]))
        for condition in ("B0", "B2"):
            block = report["conditions"][condition]
            accounting = block["output_accounting"]
            self.assertEqual(block["raw_attempts"], 0)
            self.assertEqual(block["parsed_outputs"], 0)
            self.assertEqual(accounting["successfully_parsed_outputs"], 0)
            self.assertEqual(accounting["valid_outputs"], 0)
            self.assertEqual(accounting["invalid_outputs"], 0)
            self.assertEqual(accounting["empty_or_unparseable_outputs"], 0)
            self.assertEqual(accounting["unique_valid_outputs"], 0)
            self.assertEqual(accounting["duplicates"], 0)
            self.assertEqual(accounting["largest_duplicate_multiplicity"], 0)
            self.assertIsNone(accounting["largest_duplicate_share"])
            self.assertNotEqual(accounting["largest_duplicate_share"], 0)
            for guardrail_id in analysis._m4().HARD_GUARDRAIL_IDS:
                self.assertIsNone(block["guardrail_values"][guardrail_id])
                self.assertNotEqual(block["guardrail_values"][guardrail_id], 0)
                decision = next(item for item in block["guardrail_decisions"] if item["id"] == guardrail_id)
                self.assertIsNone(decision["value"])
                self.assertIsNone(decision["passed"])
                self.assertEqual(decision["status"], "descriptive_not_checkpoint_eligibility")
            self.assertIsNone(block["checkpoint_eligible"])
        self.assertIsNone(report["conditions"]["B0"]["exact_hit_rate"])
        self.assertEqual(report["conditions"]["B0"]["exact_hit_applicability"], "not_applicable")
        b2 = report["conditions"]["B2"]
        self.assertEqual(b2["exact_hit_rate"], 0.0)
        self.assertEqual(b2["accounting"]["exact_hit_rate"], 0.0)
        self.assertEqual(b2["older_m4_metrics"]["exact_hit_rate"]["value"], 0.0)

    def test_schedule_independent_accounting_matches_projected_ledgers(self):
        document = parse_gc_document()
        report = analysis.analyse(document)
        rows = preflight.validate_records(document["records"])
        metrics = analysis._m4()
        for condition in ("B1", "D1"):
            selected = [row for row in rows if row["condition"] == condition]
            independent = analysis.schedule_independent_output_accounting(selected, document["synthetic_train_cores"])
            summary = report["conditions"][condition]["m4_summary"]
            for key in (
                "raw_attempts",
                "parsed_outputs",
                "valid_outputs",
                "invalid_outputs",
                "empty_or_unparseable_outputs",
                "unique_valid_outputs",
                "duplicates",
                "largest_duplicate_multiplicity",
                "largest_duplicate_share",
            ):
                self.assertEqual(independent[key], summary[key])
                self.assertEqual(report["conditions"][condition]["output_accounting"][key], summary[key])
            self.assertEqual(independent["parsed_outputs"], independent["raw_attempts"])
            evaluation = metrics.evaluate_hard_guardrails(
                analysis._project_attempts(selected),
                document["synthetic_train_cores"],
            )
            for guardrail_id in metrics.HARD_GUARDRAIL_IDS:
                self.assertEqual(independent["guardrail_values"][guardrail_id], evaluation["values"][guardrail_id])
            self.assertIsNone(independent["checkpoint_eligible"])
            self.assertIs(type(evaluation["checkpoint_eligible"]), bool)
            if condition == "B1":
                self.assertGreater(independent["parsed_outputs"], independent["successfully_parsed_outputs"])


def write_fixtures():
    destination = os.path.join(ROOT, "tests/modelling/fixtures/generator_eval_gep2")
    os.makedirs(destination, exist_ok=True)
    documents = {
        "synthetic_default_analysis.json": default_document(),
        "synthetic_parse_gc.json": parse_gc_document(),
        "synthetic_one_d1_seed.json": envelope(
            [
                d1_row("file-one-a", "ACGUACGU", 91001, invocation_index=1, attempt=0, chunk="chunk-m1"),
                d1_row("file-one-b", "GGGGCCCC", 91001, invocation_index=2, attempt=1, chunk="chunk-m2"),
                b1_row("file-one-b1", "ACGUACGU"),
                b0_row("file-one-b0"),
                b2_row("file-one-b2"),
            ],
            ["UUUUUUUU"],
            [reference("ref-a", "ACGUACGU")],
        ),
        "synthetic_two_d1_seeds.json": envelope(
            [
                d1_row("file-two-a", "ACGUACGU", 91001, invocation_index=1, attempt=0),
                d1_row("file-two-b", "GGGGAAAA", 91002, invocation_index=2, attempt=0, requested=4),
                b1_row("file-two-b1", "ACGUACGU"),
                b0_row("file-two-b0"),
                b2_row("file-two-b2"),
            ],
            ["UUUUUUUU"],
            [reference("ref-a", "ACGUACGU")],
        ),
        "synthetic_closeness_duplicates.json": envelope(
            [
                b1_row("close-a", "ACACACAC", invocation_index=1, batch_position=0, attempt=0),
                b1_row("close-b", "ACACACAC", invocation_index=1, batch_position=1, attempt=1),
                d1_row("close-d1", "AGACACAC", 91001, invocation_index=1, batch_position=0, attempt=0),
                b0_row("close-b0"),
                b2_row("close-b2"),
            ],
            ["UUUUUUUU"],
            [reference("ref-close", "AGACACAC")],
        ),
        "synthetic_mixed_direction.json": envelope(
            [
                b1_row("mix-b1", "AAACAAAA"),
                d1_row("mix-d1", "AAAAAAAA", 91001),
                b0_row("mix-b0"),
                b2_row("mix-b2"),
            ],
            ["UUUUUUUU"],
            [reference("ref-a", "AAAAAAAA"), reference("ref-c", "CCCCCCCC")],
        ),
        "synthetic_guardrail_failure.json": envelope(
            [
                d1_row("guard-a", "ACGUACGU", 91001, invocation_index=1, batch_position=0, attempt=0),
                d1_row("guard-b", "ACGUACGU", 91001, invocation_index=1, batch_position=1, attempt=1),
                b1_row("guard-b1", "GGGGCCCC"),
                b0_row("guard-b0"),
                b2_row("guard-b2"),
            ],
            ["UUUUUUUU"],
            [reference("ref-a", "GGGGCCCC")],
        ),
        "synthetic_empty_generated.json": envelope([], ["UUUUUUUU"], [reference("ref-a", "ACGUACGU")]),
        "synthetic_all_invalid.json": envelope(
            [
                mark_invalid_nonempty(b1_row("file-bad-b1", "ACGUACGU"), "ACGTACGT"),
                mark_unparsed(d1_row("file-bad-d1", "ACGUACGU", 91001, invocation_index=2)),
                b0_row("file-bad-b0"),
                b2_row("file-bad-b2"),
            ],
            ["UUUUUUUU"],
            [reference("ref-a", "ACGUACGU")],
        ),
    }
    unparsed = documents["synthetic_all_invalid.json"]["records"][1]
    unparsed["requested_length"] = 8
    stratified_rows = [
        b1_row("file-st-b1-s", "AAAAAAAA", invocation_index=1, batch_position=0, attempt=0),
        b1_row("file-st-b1-l", "GGGGGGGG", invocation_index=1, batch_position=1, attempt=1),
        d1_row("file-st-d1-s", "AAAAAAAA", 91001, invocation_index=1, batch_position=0, attempt=0),
        d1_row("file-st-d1-l", "ACGUACGU", 91001, invocation_index=1, batch_position=1, attempt=1),
        b0_row("file-st-b0"),
        b2_row("file-st-b2"),
    ]
    for row, label in zip(stratified_rows, ("short", "long", "short", "long", "long", "short")):
        row["s6_length_stratum"] = label
        row["s6_assignment_provenance"] = "s6-gep2-synthetic-assignment"
    documents["synthetic_stratified.json"] = envelope(
        stratified_rows,
        ["UUUUUUUU"],
        [reference("ref-s", "AAAAAAAA", "short"), reference("ref-l", "GGGGGGGG", "long")],
        stratified=True,
        s6_assignment_provenance="s6-gep2-synthetic-assignment",
    )
    documents["synthetic_matched_blocks.json"] = envelope(
        [
            b1_row("file-blk-b1", "ACGUACGU", invocation_index=1, batch_position=0, attempt=0, chunk="chunk-shared"),
            d1_row("file-blk-d1", "ACGUACGA", 91001, invocation_index=1, batch_position=0, attempt=0, chunk="chunk-other"),
            b1_row("file-blk-b1-bad", "GGGGCCCC", invocation_index=2, batch_position=0, attempt=1, chunk="chunk-shared"),
            d1_row("file-blk-d1-bad", "GGGGCCCA", 91001, invocation_index=2, batch_position=0, attempt=1, base=88010, chunk="chunk-shared"),
            b1_row("file-blk-b1-only", "AAAAAAAA", invocation_index=3, batch_position=0, attempt=2, chunk="chunk-shared"),
            d1_row("file-blk-d1-only", "CCCCCCCC", 91001, invocation_index=4, batch_position=0, attempt=2, chunk="chunk-shared"),
            b0_row("file-blk-b0"),
            b2_row("file-blk-b2"),
        ],
        ["UUUUUUUU"],
        [reference("ref-a", "ACGUACGU")],
    )
    for name, document in documents.items():
        target = os.path.join(destination, name)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2)
            handle.write("\n")


if __name__ == "__main__":
    unittest.main()

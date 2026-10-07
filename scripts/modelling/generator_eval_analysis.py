#!/usr/bin/env python3
"""GEP-2 synthetic generator-evaluation analysis.

This module is pure and synthetic-capable. Importing it does not open a
data file. It has no EVAL loader and it does not accept a filesystem path
from the command line. Metric arithmetic for edit distance, composition,
total variation, quantiles, guardrails, and structure reuses the
generator-eval-prep M4 and M6 functions. This module does not redefine
those formulas and it does not import or execute an external folding library.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys

CANONICAL_SEQUENCE = re.compile(r"^[ACGU]+$")
NUMERIC_SEED_FORMULA = re.compile(r"^([0-9]+) \+ invocation_index$")
CANONICAL_SEED_FORMULA = "generation_seed_base + invocation_index"
CANONICAL_MAX_SEQ_LEN_FORMULA = "requested_target_length + 1"
ACCEPTED_MAX_SEQ_LEN_FORMULAS = (
    "sampled_target_length + 1",
    "requested_length_plus_1",
    CANONICAL_MAX_SEQ_LEN_FORMULA,
)
SYNTHETIC_REFERENCE_ROLE = "synthetic_eval_stand_in"
SYNTHETIC_TRAIN_ROLE = "synthetic_train_stand_in"
FORBIDDEN_REFERENCE_ROLES = ("EVAL", "REF", "VALIDATION", "TRAIN")
S6_LABELS = ("short", "long")
FINAL_D1_ATTEMPT_BUDGET = 30000
ONE_D1_SEED_STATEMENT = "Uncertainty excludes training-run variability."
OBSERVED_RANGE_STATEMENT = (
    "This is an observed range across D1 training seeds. It is not a confidence interval."
)
B1_REUSE_STATEMENT = (
    "The same B1 comparator is shown against multiple D1 training seeds. "
    "This reuse does not create additional independent B1 replicates."
)
B0_M4_NOT_APPLICABLE = (
    "b0_historical_comparator_has_no_requested_length_attempt_ledger"
)
B2_M4_NOT_APPLICABLE = "b2_empirical_null_is_not_an_m4_attempt_ledger"
DESCRIPTIVE_GUARDRAIL_STATUS = "descriptive_not_checkpoint_eligibility"
SCHEDULE_EVIDENCE_NOT_AVAILABLE = "evaluation_record_lacks_eos_or_schedule_evidence"
LEGACY_PARSED_RULE = "schema_valid_ledger_parsed_outputs_equals_raw_attempts"
OUTPUT_ACCOUNTING_FIELDS = (
    "raw_attempts",
    "parsed_outputs",
    "valid_outputs",
    "invalid_outputs",
    "empty_or_unparseable_outputs",
    "unique_valid_outputs",
    "duplicates",
    "largest_duplicate_multiplicity",
    "largest_duplicate_share",
)
FIXTURE_RELATIVE = "tests/modelling/fixtures/generator_eval_gep2"
DEFAULT_FIXTURE_NAME = "synthetic_default_analysis.json"
MAX_FIXTURE_BYTES = 65536
PATH_INPUT_KEYS = (
    "path",
    "filename",
    "input_path",
    "train_path",
    "eval_path",
    "reference_path",
    "pool_path",
    "checkpoint_path",
    "manifest_path",
    "schedule_path",
    "unlock",
    "eval_unlock",
)
CLOSENESS_HEADLINE_KEYS = (
    "nearest_reference_normalized_edit_distance.median",
    "nucleotide_total_variation_to_reference",
    "dinucleotide_total_variation_to_reference",
)
OBSERVED_RANGE_KEYS = (
    "exact_hit_rate",
    "valid_nonempty_acgu_fraction",
    "empty_or_unparseable_fraction",
    "unique_fraction",
    "exact_train_match_rate",
    "largest_duplicate_share",
    "pooled_gc_fraction",
    "nearest_reference_normalized_edit_distance.median",
    "nucleotide_total_variation_to_reference",
    "dinucleotide_total_variation_to_reference",
)
FOLD_RANGE_KEYS = (
    "mfe_per_nt.median",
    "paired_fraction.median",
)
NOT_TRAINING_REPLICATE_UNITS = (
    "record_id",
    "candidate_row",
    "generation_chunk_id",
    "generation_seed",
    "invocation_seed",
    "invocation_index",
    "batch_position",
    "original_attempt_index",
    "length_sampling_seed",
    "length_condition_seed",
    "empirical_null_seed",
    "historical_generation_seed",
)
M4_SUMMARY_KEYS = (
    "raw_attempts",
    "parsed_outputs",
    "valid_outputs",
    "invalid_outputs",
    "empty_or_unparseable_outputs",
    "exact_length_hits",
    "exact_hit_rate",
    "exact_hit_rate_denominator",
    "unique_valid_outputs",
    "duplicates",
    "largest_duplicate_multiplicity",
    "largest_duplicate_share",
)
_MODULES = {}


class AnalysisContractError(ValueError):
    """The synthetic analysis contract refused the request."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        self.errors = [{"code": code, "detail": detail}]
        super().__init__(code + ": " + detail)


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_module(filename, name):
    cached = _MODULES.get(name)
    if cached is not None:
        return cached
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULES[name] = module
    return module


def _preflight():
    return _load_module("generator_eval_preflight.py", "gep2_preflight_dep")


def _m4():
    return _load_module("m4_diagnostic_metrics.py", "gep2_m4_dep")


def _m6():
    return _load_module("m6_diagnostic_generation.py", "gep2_m6_dep")


def successfully_parsed_outputs(rows):
    """Count nonempty extracted sequences before A/C/G/U filtering.

    This is not the legacy M4 parsed predicate. An empty or unparseable
    output is not successfully parsed. A nonempty alphabet-invalid output is.
    """
    if not isinstance(rows, list):
        raise AnalysisContractError("records_invalid", "generated rows must be a list")
    return sum(isinstance(row, dict) and isinstance(row.get("sequence"), str) and row.get("sequence") != "" for row in rows)


def pooled_gc_fraction(sequences):
    """(count_G + count_C) / total canonical bases. Duplicates stay in the pool."""
    if not isinstance(sequences, list):
        raise AnalysisContractError("gc_population_invalid", "GC population must be a list")
    counts = {base: 0 for base in "ACGU"}
    for sequence in sequences:
        if not isinstance(sequence, str) or CANONICAL_SEQUENCE.fullmatch(sequence) is None:
            raise AnalysisContractError("gc_population_invalid", "GC population is not canonical A/C/G/U")
        for base in sequence:
            counts[base] += 1
    total = sum(counts.values())
    if total == 0:
        return None
    return (counts["G"] + counts["C"]) / total


def _undefined_metric(reason, **denominators):
    result = {
        "value": None,
        "median": None,
        "quantiles": None,
        "undefined_reason": reason,
        "direction": "lower",
    }
    result.update(denominators)
    return result


def _reference_cores(reference_sequences):
    if not isinstance(reference_sequences, list) or not reference_sequences:
        return None, "reference_empty"
    seen = set()
    cores = []
    for sequence in reference_sequences:
        if not isinstance(sequence, str) or CANONICAL_SEQUENCE.fullmatch(sequence) is None:
            return None, "reference_noncanonical"
        if sequence in seen:
            return None, "reference_sequences_not_unique"
        seen.add(sequence)
        cores.append(sequence)
    return cores, None


def _generated_sequences(generated_sequences):
    if not isinstance(generated_sequences, list):
        return None, "generated_population_invalid"
    sequences = []
    for sequence in generated_sequences:
        if not isinstance(sequence, str) or CANONICAL_SEQUENCE.fullmatch(sequence) is None:
            return None, "generated_population_invalid"
        sequences.append(sequence)
    if not sequences:
        return None, "no_valid_generated_rows"
    return sequences, None


def _denominators(generated, cores):
    generated_rows = generated or []
    return {
        "generated_valid_row_denominator": len(generated_rows),
        "generated_unique_valid_count": len(set(generated_rows)),
        "reference_unique_core_denominator": 0 if cores is None else len(cores),
    }


def nearest_reference_normalized_edit_distance(generated_sequences, reference_sequences):
    """Quantiles of longer-sequence-normalised nearest-reference edit distance.

    Valid generated rows keep their duplicates. The headline scalar is the
    median. Lower means closer. A null result is not replaced with zero.
    """
    cores, core_reason = _reference_cores(reference_sequences)
    generated, generated_reason = _generated_sequences(generated_sequences) if core_reason is None else (None, None)
    denominators = _denominators(generated if generated is not None else generated_sequences if isinstance(generated_sequences, list) else [], cores)
    reason = core_reason or generated_reason
    if reason is not None:
        return _undefined_metric(reason, **denominators)
    metrics = _m6()
    nearest = {}
    for sequence in sorted(set(generated)):
        nearest[sequence] = metrics.nearest_train(sequence, cores)
    distances = [nearest[sequence] for sequence in generated]
    quantiles = metrics._quantiles(distances)
    return {
        "value": quantiles["median"],
        "median": quantiles["median"],
        "quantiles": quantiles,
        "undefined_reason": None,
        "direction": "lower",
        **denominators,
    }


def _total_variation_to_reference(generated_sequences, reference_sequences, fraction_key, empty_fraction_reason):
    cores, core_reason = _reference_cores(reference_sequences)
    generated, generated_reason = _generated_sequences(generated_sequences) if core_reason is None else (None, None)
    population = generated if generated is not None else generated_sequences if isinstance(generated_sequences, list) else []
    denominators = _denominators(population, cores)
    reason = core_reason or generated_reason
    if reason is not None:
        return _undefined_metric(reason, **denominators)
    metrics = _m6()
    left = metrics.composition(generated)[fraction_key]
    right = metrics.composition(cores)[fraction_key]
    value = metrics.total_variation(left, right)
    if value is None:
        return _undefined_metric(empty_fraction_reason, **denominators)
    return {
        "value": value,
        "median": None,
        "quantiles": None,
        "undefined_reason": None,
        "direction": "lower",
        **denominators,
    }


def nucleotide_total_variation_to_reference(generated_sequences, reference_sequences):
    """0.5 * L1 distance between pooled nucleotide fractions. Lower means closer."""
    return _total_variation_to_reference(
        generated_sequences,
        reference_sequences,
        "nucleotide_fractions",
        "no_canonical_bases",
    )


def dinucleotide_total_variation_to_reference(generated_sequences, reference_sequences):
    """0.5 * L1 distance between pooled overlapping-dinucleotide fractions."""
    return _total_variation_to_reference(
        generated_sequences,
        reference_sequences,
        "dinucleotide_fractions",
        "no_overlapping_dinucleotides",
    )


def directional_consistency(b1_headlines, d1_headlines):
    """Descriptive D1-minus-B1 label for the three closeness headlines.

    The label is not a score, a vote count, a threshold, or a hypothesis test.
    It does not replace the three metrics. It is not applied to B0 or B2.
    """
    if not isinstance(b1_headlines, dict) or not isinstance(d1_headlines, dict):
        raise AnalysisContractError("directional_consistency_invalid", "closeness headlines must be objects")
    differences = {}
    relations = []
    undefined = False
    for key in CLOSENESS_HEADLINE_KEYS:
        left = b1_headlines.get(key)
        right = d1_headlines.get(key)
        if left is None or right is None or isinstance(left, bool) or isinstance(right, bool):
            undefined = True
            differences[key] = {"d1_minus_b1": None, "relation": "undefined"}
            continue
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            undefined = True
            differences[key] = {"d1_minus_b1": None, "relation": "undefined"}
            continue
        delta = right - left
        if delta < 0:
            relation = "d1_closer"
        elif delta > 0:
            relation = "d1_farther"
        else:
            relation = "tie"
        relations.append(relation)
        differences[key] = {"d1_minus_b1": delta, "relation": relation}
    if undefined or len(relations) != len(CLOSENESS_HEADLINE_KEYS):
        label = "not_applicable"
    elif all(relation == "tie" for relation in relations):
        label = "all_tied"
    else:
        closer = any(relation == "d1_closer" for relation in relations)
        farther = any(relation == "d1_farther" for relation in relations)
        if closer and farther:
            label = "mixed"
        elif closer:
            label = "d1_closer_or_tied"
        elif farther:
            label = "d1_farther_or_tied"
        else:
            label = "all_tied"
    return {
        "label": label,
        "differences": differences,
        "label_is_a_score": False,
        "label_is_a_vote_count": False,
        "label_is_a_threshold": False,
        "label_is_a_hypothesis_test": False,
        "replaces_the_three_metrics": False,
        "applies_to_conditions": ["B1", "D1"],
        "applied_to_b0": False,
        "applied_to_b2": False,
    }


def _length_vector_sha256(values):
    payload = json.dumps(list(values), separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
    return hashlib.sha256(payload).hexdigest()


def map_schedule_provenance(producer):
    """Normalize a synthetic schedule dictionary into the GEP provenance contract.

    Arithmetic is checked. Formula text is not trusted by itself. The
    1,000-attempt diagnostic count is reported as supplied and is not treated
    as the 30,000-attempt final D1 budget. This package never declares that
    production budget satisfied.
    """
    if not isinstance(producer, dict):
        raise AnalysisContractError("schedule_invalid", "a synthetic schedule must be an object")
    if "sampling_seed" in producer and "target_length_sampling_seed" in producer:
        if producer["sampling_seed"] != producer["target_length_sampling_seed"]:
            raise AnalysisContractError("schedule_invalid", "sampling seed aliases disagree")
        sampling_seed = producer["sampling_seed"]
    elif "sampling_seed" in producer:
        sampling_seed = producer["sampling_seed"]
    elif "target_length_sampling_seed" in producer:
        sampling_seed = producer["target_length_sampling_seed"]
    else:
        raise AnalysisContractError("schedule_invalid", "the length-sampling seed is missing")
    if type(sampling_seed) is not int or sampling_seed < 0:
        raise AnalysisContractError("schedule_invalid", "the length-sampling seed is not a nonnegative integer")
    base = producer.get("generation_seed_base")
    if type(base) is not int or base < 0:
        raise AnalysisContractError("schedule_invalid", "generation_seed_base is not a nonnegative integer")
    formula = producer.get("seed_formula")
    numeric = NUMERIC_SEED_FORMULA.fullmatch(formula) if isinstance(formula, str) else None
    if numeric is not None:
        if int(numeric.group(1)) != base:
            raise AnalysisContractError("schedule_invalid", "the numeric seed formula does not match generation_seed_base")
    elif formula != CANONICAL_SEED_FORMULA:
        raise AnalysisContractError("schedule_invalid", "the seed formula is not a recognized producer representation")
    max_formula = producer.get("max_seq_len_formula")
    if max_formula not in ACCEPTED_MAX_SEQ_LEN_FORMULAS:
        raise AnalysisContractError("schedule_invalid", "the max_seq_len formula is not a recognized producer representation")
    chunk_size = producer.get("max_chunk_size")
    batch_num = producer.get("batch_num")
    total = producer.get("total_attempts")
    if type(chunk_size) is not int or chunk_size < 1:
        raise AnalysisContractError("schedule_invalid", "max_chunk_size is not a positive integer")
    if type(batch_num) is not int or batch_num < 0:
        raise AnalysisContractError("schedule_invalid", "batch_num is not a nonnegative integer")
    if type(total) is not int or total < 1:
        raise AnalysisContractError("schedule_invalid", "total attempt count is not a positive integer")
    vector = producer.get("source_ordered_length_vector")
    ordered = producer.get("ordered_lengths")
    claimed = producer.get("length_vector_sha256")
    if isinstance(vector, dict):
        if ordered is None:
            ordered = vector.get("values")
        if claimed is None:
            claimed = vector.get("sha256")
        elif vector.get("sha256") not in (None, claimed):
            raise AnalysisContractError("schedule_invalid", "length-vector hashes disagree")
    if not isinstance(ordered, list) or not ordered:
        raise AnalysisContractError("schedule_invalid", "the ordered length vector is missing")
    if any(type(value) is not int or value < 1 for value in ordered):
        raise AnalysisContractError("schedule_invalid", "the ordered length vector is not positive integers")
    source_lengths = set(ordered)
    digest = _length_vector_sha256(ordered)
    if not isinstance(claimed, str) or claimed != digest:
        raise AnalysisContractError("schedule_invalid", "length-vector sha256 does not match the ordered lengths")
    sampled = producer.get("sampled_target_lengths")
    if sampled is not None:
        if not isinstance(sampled, list) or len(sampled) != total:
            raise AnalysisContractError("schedule_invalid", "sampled target lengths do not match the attempt count")
        if any(type(value) is not int or value < 1 for value in sampled):
            raise AnalysisContractError("schedule_invalid", "a sampled target length is not a positive integer")
        if any(value not in source_lengths for value in sampled):
            raise AnalysisContractError(
                "schedule_invalid",
                "a sampled target length is absent from the source ordered-length vector",
            )
    invocations = producer.get("invocations")
    if not isinstance(invocations, list) or not invocations:
        raise AnalysisContractError("schedule_invalid", "schedule invocations are required to verify seed arithmetic")
    seen_attempts = []
    seen_invocation_indexes = set()
    normalized_invocations = []
    accounted = 0
    for invocation in invocations:
        if not isinstance(invocation, dict):
            raise AnalysisContractError("schedule_invalid", "a schedule invocation is not an object")
        index = invocation.get("invocation_index")
        seed = invocation.get("invocation_seed")
        if type(index) is not int or index < 0 or type(seed) is not int or isinstance(index, bool) or isinstance(seed, bool):
            raise AnalysisContractError("schedule_invalid", "an invocation index or seed is not an integer")
        if index in seen_invocation_indexes:
            raise AnalysisContractError("schedule_invalid", "invocation identities are not unique")
        seen_invocation_indexes.add(index)
        if seed != base + index:
            raise AnalysisContractError("schedule_invalid", "invocation_seed is not generation_seed_base + invocation_index")
        target = _invocation_target_length(invocation)
        if target not in source_lengths:
            raise AnalysisContractError(
                "schedule_invalid",
                "a sampled target length is absent from the source ordered-length vector",
            )
        max_seq_len = invocation.get("max_seq_len")
        if type(max_seq_len) is not int or isinstance(max_seq_len, bool) or max_seq_len != target + 1:
            raise AnalysisContractError("schedule_invalid", "max_seq_len is not the target length plus 1")
        if "batch_num" in invocation and invocation["batch_num"] != batch_num:
            raise AnalysisContractError("schedule_invalid", "an invocation batch_num disagrees with the schedule")
        indexes = invocation.get("original_attempt_indexes")
        actual = invocation.get("actual_chunk_size")
        batch_positions = None
        if indexes is not None:
            if not isinstance(indexes, list) or not indexes or any(type(item) is not int or isinstance(item, bool) or item < 0 for item in indexes):
                raise AnalysisContractError("schedule_invalid", "original attempt indexes are invalid")
            if len(indexes) != len(set(indexes)):
                raise AnalysisContractError("schedule_invalid", "an invocation repeats an original attempt index")
            if actual is not None and actual != len(indexes):
                raise AnalysisContractError("schedule_invalid", "actual_chunk_size does not match the attempt indexes")
            actual = len(indexes)
            batch_positions = list(range(len(indexes)))
            supplied_positions = invocation.get("expected_batch_positions")
            if supplied_positions is not None and supplied_positions != batch_positions:
                raise AnalysisContractError("schedule_invalid", "batch positions are not the invocation order")
            seen_attempts.extend(indexes)
        if actual is None or type(actual) is not int or isinstance(actual, bool) or actual < 1 or actual > chunk_size:
            raise AnalysisContractError("schedule_invalid", "a chunk size is outside max_chunk_size")
        accounted += actual
        normalized_invocations.append(
            {
                "invocation_index": index,
                "invocation_seed": seed,
                "requested_target_length": target,
                "max_seq_len": max_seq_len,
                "batch_num": batch_num,
                "original_attempt_indexes": None if indexes is None else list(indexes),
                "batch_positions": batch_positions,
            }
        )
    if accounted != total:
        raise AnalysisContractError("schedule_invalid", "invocation chunks do not match the supplied attempt count")
    if seen_attempts:
        if len(seen_attempts) != len(set(seen_attempts)) or sorted(seen_attempts) != list(range(total)):
            raise AnalysisContractError("schedule_invalid", "attempt indexes do not match the supplied attempt count")
    if isinstance(sampled, list) and seen_attempts:
        for invocation in normalized_invocations:
            for attempt in invocation["original_attempt_indexes"]:
                if sampled[attempt] != invocation["requested_target_length"]:
                    raise AnalysisContractError(
                        "schedule_invalid",
                        "a sampled target length does not match its invocation",
                    )
    return {
        "target_length_sampling_seed": sampling_seed,
        "length_vector_sha256": digest,
        "ordered_length_count": len(ordered),
        "generation_seed_base": base,
        "seed_formula": CANONICAL_SEED_FORMULA,
        "max_seq_len_formula": CANONICAL_MAX_SEQ_LEN_FORMULA,
        "max_chunk_size": chunk_size,
        "batch_num": batch_num,
        "attempt_count": total,
        "invocation_count": len(invocations),
        "invocations": normalized_invocations,
        "sampled_target_lengths": None if sampled is None else list(sampled),
        "invocation_identities_unique": True,
        "producer_seed_formula": formula,
        "producer_max_seq_len_formula": max_formula,
        "production_budget_satisfied": False,
        "final_d1_attempt_budget": FINAL_D1_ATTEMPT_BUDGET,
        "final_d1_attempt_budget_is_total_across_retained_seeds": True,
        "d1_training_seeds_each_receive_full_budget": False,
        "diagnostic_attempt_count_is_final_d1_budget": False,
        "sampling_seed_retained": False,
    }


def _expected_schedule_attempts(mapped):
    """Map each original attempt index to the producer fields the ledger must repeat."""
    sampled = mapped.get("sampled_target_lengths")
    if not isinstance(sampled, list) or len(sampled) != mapped["attempt_count"]:
        raise AnalysisContractError(
            "schedule_ledger_mismatch",
            "the schedule does not name a sampled target length for every attempt",
        )
    expected = {}
    for invocation in mapped["invocations"]:
        indexes = invocation.get("original_attempt_indexes")
        positions = invocation.get("batch_positions")
        if not isinstance(indexes, list) or not isinstance(positions, list) or len(indexes) != len(positions):
            raise AnalysisContractError(
                "schedule_ledger_mismatch",
                "the producer does not assign original attempt indexes, so a global D1 attempt assignment across training seeds cannot be established",
            )
        for position, attempt in zip(positions, indexes):
            if attempt in expected:
                raise AnalysisContractError("schedule_ledger_mismatch", "the schedule repeats an original attempt index")
            expected[attempt] = {
                "invocation_index": invocation["invocation_index"],
                "invocation_seed": invocation["invocation_seed"],
                "batch_position": position,
                "requested_target_length": invocation["requested_target_length"],
                "max_seq_len": invocation["max_seq_len"],
                "sampled_target_length": sampled[attempt],
            }
    if sorted(expected) != list(range(mapped["attempt_count"])):
        raise AnalysisContractError(
            "schedule_ledger_mismatch",
            "scheduled attempts do not cover every original attempt index",
        )
    return expected


def _ledger_label(condition, training_seed):
    if condition == "B1":
        return "B1"
    return "D1 training_seed %s" % training_seed


def _assert_row_matches_schedule(mapped, required, condition, training_seed, row):
    label = _ledger_label(condition, training_seed)
    comparisons = (
        ("invocation_index", row["invocation_index"], required["invocation_index"]),
        ("invocation_seed", row["invocation_seed"], required["invocation_seed"]),
        ("generation_seed", row["generation_seed"], required["invocation_seed"]),
        ("batch_position", row["batch_position"], required["batch_position"]),
        ("requested_target_length", row["requested_target_length"], required["requested_target_length"]),
        ("max_seq_len", row["max_seq_len"], required["max_seq_len"]),
        ("sampled_target_length", row["requested_target_length"], required["sampled_target_length"]),
    )
    for field, actual, wanted in comparisons:
        if actual != wanted:
            raise AnalysisContractError(
                "schedule_ledger_mismatch",
                label + " " + field + " does not match the schedule",
            )
    provenance = row["length_schedule_provenance"]
    if not isinstance(provenance, dict):
        raise AnalysisContractError("schedule_ledger_mismatch", label + " length-schedule provenance is missing")
    provenance_fields = (
        ("target_length_sampling_seed", mapped["target_length_sampling_seed"]),
        ("length_vector_sha256", mapped["length_vector_sha256"]),
        ("generation_seed_base", mapped["generation_seed_base"]),
        ("seed_formula", mapped["seed_formula"]),
        ("max_seq_len_formula", mapped["max_seq_len_formula"]),
        ("max_chunk_size", mapped["max_chunk_size"]),
        ("batch_num", mapped["batch_num"]),
    )
    for field, wanted in provenance_fields:
        if provenance.get(field) != wanted:
            raise AnalysisContractError(
                "schedule_ledger_mismatch",
                label + " " + field + " does not match the schedule",
            )
    if row["length_sampling_seed"] != mapped["target_length_sampling_seed"]:
        raise AnalysisContractError(
            "schedule_ledger_mismatch",
            label + " target-length sampling seed does not match the schedule",
        )


def _assert_ledger_matches_schedule(mapped, expected, condition, training_seed, ledger):
    """Require one ledger to cover the scheduled attempt set exactly once."""
    label = _ledger_label(condition, training_seed)
    by_attempt = {}
    for row in ledger:
        attempt = row["original_attempt_index"]
        if attempt in by_attempt:
            raise AnalysisContractError("schedule_ledger_mismatch", label + " repeats an original attempt index")
        if attempt not in expected:
            raise AnalysisContractError("schedule_ledger_mismatch", label + " has attempts that are not in the schedule")
        by_attempt[attempt] = row
    if sorted(by_attempt) != sorted(expected):
        raise AnalysisContractError("schedule_ledger_mismatch", label + " is missing scheduled attempts")
    for attempt, row in by_attempt.items():
        _assert_row_matches_schedule(mapped, expected[attempt], condition, training_seed, row)


def _bind_d1_attempt_union(mapped, expected, rows):
    """Cover the scheduled attempts once across retained D1 training seeds.

    A seed may hold a subset. The union must equal the schedule, and an attempt
    identity may not occur on more than one retained seed. This does not give
    every seed the full attempt budget.
    """
    seen = {}
    counts = {}
    for row in rows:
        if row["condition"] != "D1":
            continue
        seed = row["training_seed"]
        attempt = row["original_attempt_index"]
        if attempt in seen:
            raise AnalysisContractError(
                "schedule_ledger_mismatch",
                "D1 attempt identities are duplicated across training seeds",
            )
        if attempt not in expected:
            raise AnalysisContractError(
                "schedule_ledger_mismatch",
                "D1 has attempts that are not in the schedule",
            )
        _assert_row_matches_schedule(mapped, expected[attempt], "D1", seed, row)
        seen[attempt] = seed
        counts[seed] = counts.get(seed, 0) + 1
    if sorted(seen) != sorted(expected):
        raise AnalysisContractError(
            "schedule_ledger_mismatch",
            "D1 training-seed ledgers are missing scheduled attempts",
        )
    total = sum(counts.values())
    if total != len(expected):
        raise AnalysisContractError(
            "schedule_ledger_mismatch",
            "D1 attempt counts do not sum to the scheduled attempt count",
        )
    return counts, total


def bind_schedule_to_ledgers(mapped, rows):
    """Bind one global attempt schedule to B1 and to the D1 seed union.

    B1 must cover every scheduled attempt. D1 training seeds together must
    cover those attempts exactly once. Each D1 row must match the scheduled
    fields for its own attempt. Seeds stay identifiable and are not pooled.
    A producer that does not name original attempt indexes fails closed instead
    of assuming that every training seed received the full schedule.
    """
    if not isinstance(mapped, dict) or not isinstance(rows, list):
        raise AnalysisContractError("schedule_ledger_mismatch", "the schedule cannot be bound to the ledger")
    expected = _expected_schedule_attempts(mapped)
    b1_rows = [row for row in rows if row["condition"] == "B1"]
    _assert_ledger_matches_schedule(mapped, expected, "B1", None, b1_rows)
    counts, total = _bind_d1_attempt_union(mapped, expected, rows)
    d1_seeds = sorted(counts)
    checked = ["B1"]
    checked.extend(_ledger_label("D1", seed) for seed in d1_seeds)
    by_seed = [
        {"training_seed": seed, "attempt_count": counts[seed]}
        for seed in d1_seeds
    ]
    return {
        "scheduled_attempt_count": len(expected),
        "b1_attempt_count": len(b1_rows),
        "d1_attempt_count": total,
        "d1_attempt_count_by_training_seed": by_seed,
        "d1_union_covers_schedule_exactly_once": True,
        "d1_training_seeds": d1_seeds,
        "ledgers_checked": checked,
        "d1_training_seeds_pooled": False,
        "diagnostic_attempt_count_is_final_d1_budget": False,
        "final_d1_attempt_budget": FINAL_D1_ATTEMPT_BUDGET,
        "final_d1_attempt_budget_is_total_across_retained_seeds": True,
        "d1_training_seeds_each_receive_full_budget": False,
        "production_budget_satisfied": False,
    }


def _invocation_target_length(invocation):
    present = []
    for key in ("target_length", "sampled_target_length", "requested_target_length"):
        if key in invocation and invocation[key] is not None:
            present.append(invocation[key])
    if len(present) != 1 and len(set(present)) != 1:
        raise AnalysisContractError("schedule_invalid", "an invocation target length is missing or inconsistent")
    target = present[0]
    if type(target) is not int or target < 1:
        raise AnalysisContractError("schedule_invalid", "an invocation target length is not a positive integer")
    return target


def map_b2_producer_batch(records):
    """Map the producer field seed onto empirical_null_seed.

    The generic seed key is removed. training_seed is never created. Exactly
    one integer seed is required. Production seed 42 is not assumed.
    """
    if not isinstance(records, list) or not records:
        raise AnalysisContractError("b2_seed_invalid", "the synthetic B2 batch is empty")
    mapped = []
    seeds = []
    for record in records:
        if not isinstance(record, dict):
            raise AnalysisContractError("b2_seed_invalid", "a B2 producer record is not an object")
        if "training_seed" in record:
            raise AnalysisContractError("b2_seed_invalid", "the B2 mapper does not create or accept training_seed")
        if "seed" not in record or type(record["seed"]) is not int:
            raise AnalysisContractError("b2_seed_invalid", "the B2 producer field seed must be one integer")
        if "empirical_null_seed" in record:
            raise AnalysisContractError("b2_seed_invalid", "a B2 producer record already has empirical_null_seed")
        seeds.append(record["seed"])
        rewritten = {key: value for key, value in record.items() if key != "seed"}
        rewritten["empirical_null_seed"] = record["seed"]
        if "seed" in rewritten or "training_seed" in rewritten:
            raise AnalysisContractError("b2_seed_invalid", "generic seed survived B2 mapping")
        mapped.append(rewritten)
    if len(set(seeds)) != 1:
        raise AnalysisContractError("b2_multiple_seeds", "the synthetic B2 batch has more than one seed")
    return {
        "records": mapped,
        "empirical_null_seed": seeds[0],
        "b2_seed_count": 1,
        "training_seed_created": False,
        "generic_seed_retained": False,
        "production_seed_42_assumed": False,
        "rows_are_training_replicates": False,
    }


def _nonempty_text(value):
    return isinstance(value, str) and value.strip() != ""


def _reject_path_inputs(document):
    for key in PATH_INPUT_KEYS:
        if key in document:
            raise AnalysisContractError("path_input_refused", "the analysis does not accept paths or an EVAL unlock")


def _reference_entries(document):
    role = document.get("reference_role")
    if role in FORBIDDEN_REFERENCE_ROLES or role != SYNTHETIC_REFERENCE_ROLE:
        raise AnalysisContractError("reference_role_refused", "the reference role is not synthetic_eval_stand_in")
    if document.get("train_collection_role") != SYNTHETIC_TRAIN_ROLE:
        raise AnalysisContractError("train_collection_role_refused", "the TRAIN stand-in role is not synthetic")
    reference_id = document.get("reference_id")
    if not _nonempty_text(reference_id):
        raise AnalysisContractError("reference_id_invalid", "the synthetic reference id is missing")
    entries = document.get("synthetic_reference_sequences")
    if not isinstance(entries, list) or not entries:
        raise AnalysisContractError("reference_empty", "the synthetic reference is empty")
    sequences = []
    sequence_ids = []
    labelled = []
    for entry in entries:
        if isinstance(entry, str):
            raise AnalysisContractError("reference_id_invalid", "a synthetic reference sequence lacks a stable id")
        if not isinstance(entry, dict):
            raise AnalysisContractError("reference_invalid", "a synthetic reference entry is not an object")
        sequence_id = entry.get("sequence_id")
        sequence = entry.get("sequence")
        if not _nonempty_text(sequence_id):
            raise AnalysisContractError("reference_id_invalid", "a synthetic reference sequence id is missing")
        if not isinstance(sequence, str) or CANONICAL_SEQUENCE.fullmatch(sequence) is None:
            raise AnalysisContractError("reference_noncanonical", "a synthetic reference sequence is not canonical A/C/G/U")
        sequence_ids.append(sequence_id)
        sequences.append(sequence)
        labelled.append(entry.get("s6_length_stratum"))
    if len(sequence_ids) != len(set(sequence_ids)):
        raise AnalysisContractError("reference_id_invalid", "synthetic reference sequence ids are not unique")
    if len(sequences) != len(set(sequences)):
        raise AnalysisContractError("reference_sequences_not_unique", "synthetic reference sequences are not unique")
    return sequences, labelled


def _train_cores(document):
    cores = document.get("synthetic_train_cores")
    if not isinstance(cores, list) or not cores:
        raise AnalysisContractError("train_reference_invalid", "the synthetic TRAIN collection is empty")
    for core in cores:
        if not isinstance(core, str) or CANONICAL_SEQUENCE.fullmatch(core) is None:
            raise AnalysisContractError("train_reference_invalid", "a synthetic TRAIN core is not canonical A/C/G/U")
    return list(cores)


def _s6_checks(document, records, reference_labels):
    stratified = document.get("stratified")
    if type(stratified) is not bool:
        raise AnalysisContractError("stratification_invalid", "stratified must be a boolean")
    if not stratified:
        return False, None, {}
    provenance = document.get("s6_assignment_provenance")
    if not _nonempty_text(provenance):
        raise AnalysisContractError("s6_provenance_missing", "stratified output requires one shared S6 provenance token")
    labels = {}
    if not isinstance(records, list):
        raise AnalysisContractError("records_invalid", "generated rows must be a list")
    for record in records:
        if not isinstance(record, dict):
            raise AnalysisContractError("s6_label_missing", "a generated row lacks an explicit S6 label")
        label = record.get("s6_length_stratum")
        if label not in S6_LABELS:
            raise AnalysisContractError("s6_label_missing", "a generated row lacks an explicit frozen S6 label of short or long")
        record_provenance = record.get("s6_assignment_provenance")
        if record_provenance is not None and record_provenance != provenance:
            raise AnalysisContractError("s6_provenance_inconsistent", "S6 provenance tokens disagree")
        record_id = record.get("record_id")
        if _nonempty_text(record_id):
            labels[record_id] = label
    if any(label not in S6_LABELS for label in reference_labels):
        raise AnalysisContractError("s6_label_missing", "a reference sequence lacks an explicit frozen S6 label of short or long")
    return True, provenance, labels


def prepare_analysis_inputs(document):
    """Fail closed before M4, M6, folding, or closeness calculation."""
    if not isinstance(document, dict):
        raise AnalysisContractError("analysis_input_invalid", "the analysis input must be an object")
    _reject_path_inputs(document)
    if document.get("fixture_role") != "SYNTHETIC":
        raise AnalysisContractError("data_role_refused", "the analysis fixture role is not synthetic")
    sequences, reference_labels = _reference_entries(document)
    cores = _train_cores(document)
    records = document.get("records")
    stratified, provenance, labels = _s6_checks(document, records, reference_labels)
    schedule = None
    if "schedule_producer" in document:
        schedule = map_schedule_provenance(document["schedule_producer"])
    b2_mapping = None
    if "b2_producer_batch" in document:
        b2_mapping = map_b2_producer_batch(document["b2_producer_batch"])
    preflight = _preflight()
    rows = preflight.validate_records(records)
    if b2_mapping is not None:
        record_seeds = sorted({row["empirical_null_seed"] for row in rows if row["condition"] == "B2"})
        if record_seeds != [b2_mapping["empirical_null_seed"]]:
            raise AnalysisContractError("b2_seed_invalid", "mapped B2 seed does not match the synthetic batch")
    d1_rows = [row for row in rows if row["condition"] == "D1"]
    if any(type(row["training_seed"]) is not int for row in d1_rows):
        raise AnalysisContractError("d1_training_seed_provenance_missing", "every D1 row must have exactly one training_seed")
    if schedule is not None:
        schedule = dict(schedule)
        schedule["ledger_binding"] = bind_schedule_to_ledgers(schedule, rows)
    if stratified and any(row["record_id"] not in labels for row in rows):
        raise AnalysisContractError("s6_label_missing", "a generated row lacks an explicit frozen S6 label of short or long")
    reference_by_stratum = None
    if stratified:
        reference_by_stratum = {"short": [], "long": []}
        for sequence, label in zip(sequences, reference_labels):
            reference_by_stratum[label].append(sequence)
    return {
        "rows": rows,
        "train_cores": cores,
        "reference_sequences": sequences,
        "reference_labels": reference_labels,
        "reference_by_stratum": reference_by_stratum,
        "reference_id": document["reference_id"],
        "reference_role": SYNTHETIC_REFERENCE_ROLE,
        "stratified": stratified,
        "s6_assignment_provenance": provenance,
        "labels_by_record_id": labels,
        "schedule": schedule,
        "b2_mapping": b2_mapping,
        "fold_supplied": False,
    }


def _valid_sequences(rows):
    preflight = _preflight()
    return [row["sequence"] for row in rows if preflight._row_is_valid(row)]


def _closeness_population(generated, reference):
    nearest = nearest_reference_normalized_edit_distance(generated, reference)
    nucleotide = nucleotide_total_variation_to_reference(generated, reference)
    dinucleotide = dinucleotide_total_variation_to_reference(generated, reference)
    headlines = {
        "nearest_reference_normalized_edit_distance.median": nearest["median"],
        "nucleotide_total_variation_to_reference": nucleotide["value"],
        "dinucleotide_total_variation_to_reference": dinucleotide["value"],
    }
    return {
        "nearest_reference_normalized_edit_distance": nearest,
        "nucleotide_total_variation_to_reference": nucleotide,
        "dinucleotide_total_variation_to_reference": dinucleotide,
        "headlines": headlines,
        "combined": False,
    }


def _train_nested(generated, train_cores):
    if not generated:
        return {
            "nucleotide_total_variation_to_train": None,
            "dinucleotide_total_variation_to_train": None,
            "undefined_reason": "no_valid_generated_rows",
            "role": "nested_descriptive_output",
            "is_a_closeness_metric": False,
            "is_a_quality_vote": False,
            "separate_metric_id": False,
        }
    metrics = _m6()
    sample = metrics.composition(generated)
    reference = metrics.composition(list(train_cores))
    return {
        "nucleotide_total_variation_to_train": metrics.total_variation(
            sample["nucleotide_fractions"], reference["nucleotide_fractions"]
        ),
        "dinucleotide_total_variation_to_train": metrics.total_variation(
            sample["dinucleotide_fractions"], reference["dinucleotide_fractions"]
        ),
        "undefined_reason": None,
        "role": "nested_descriptive_output",
        "is_a_closeness_metric": False,
        "is_a_quality_vote": False,
        "separate_metric_id": False,
    }


def _project_attempts(rows):
    preflight = _preflight()
    attempts = []
    for row in sorted(rows, key=lambda item: item["record_id"]):
        attempt = preflight.project_m4_attempt(row, len(attempts))
        if attempt is not None:
            attempts.append(attempt)
    return attempts


def _guardrail_headlines(evaluation):
    headlines = {}
    decisions = []
    for decision in evaluation["decisions"]:
        evaluated = decision["status"] == "evaluated"
        recorded = {
            "id": decision["id"],
            "value": decision["value"] if evaluated else None,
            "comparison": decision["comparison"],
            "threshold": decision["threshold"],
            "passed": decision["passed"] if evaluated else None,
            "status": decision["status"],
            "undefined_reason": None if evaluated else decision["status"],
        }
        decisions.append(recorded)
        headlines[decision["id"]] = recorded["value"]
    failures = [item["id"] for item in decisions if item["status"] == "evaluated" and item["passed"] is not True]
    return headlines, decisions, failures


def _blank_structure(reason, fold_injected):
    return {
        "viennarna_called": False,
        "fold_injected": fold_injected,
        "mfe": None,
        "mfe_per_nt": None,
        "paired_fraction": None,
        "mfe_per_nt.median": None,
        "paired_fraction.median": None,
        "undefined_reason": reason,
        "new_mfe_formula_defined": False,
        "aptarank_normalized_mfe": False,
    }


def _structure_quantiles(mfe_values, per_nt_values, paired_values):
    metrics = _m6()
    mfe = metrics._quantiles(mfe_values)
    per_nt = metrics._quantiles(per_nt_values)
    paired = metrics._quantiles(paired_values)
    return {
        "viennarna_called": False,
        "fold_injected": True,
        "mfe": mfe,
        "mfe_per_nt": per_nt,
        "paired_fraction": paired,
        "mfe_per_nt.median": None if per_nt is None else per_nt["median"],
        "paired_fraction.median": None if paired is None else paired["median"],
        "undefined_reason": None if per_nt is not None else "no_valid_generated_rows",
        "new_mfe_formula_defined": False,
        "aptarank_normalized_mfe": False,
    }


def _structure_block(attempts, train_cores, fold):
    if fold is None:
        return _blank_structure("no_synthetic_fold_supplied", False)
    if not attempts:
        return _blank_structure("no_projected_attempts", True)
    report = _m6().report_only_diagnostics(attempts, train_cores, fold)
    mfe = report["mfe"]
    per_nt = report["mfe_per_nt"]
    paired = report["paired_fraction"]
    return {
        "viennarna_called": False,
        "fold_injected": True,
        "mfe": mfe,
        "mfe_per_nt": per_nt,
        "paired_fraction": paired,
        "mfe_per_nt.median": None if per_nt is None else per_nt["median"],
        "paired_fraction.median": None if paired is None else paired["median"],
        "undefined_reason": None if per_nt is not None else "no_valid_generated_rows",
        "new_mfe_formula_defined": False,
        "aptarank_normalized_mfe": False,
    }


def _structure_from_sequences(sequences, fold):
    """Structure quantiles without inventing an attempt-ledger schedule."""
    if fold is None:
        return _blank_structure("no_synthetic_fold_supplied", False)
    if not sequences:
        return _blank_structure("no_valid_generated_rows", True)
    metrics = _m6()
    features = {sequence: metrics.structure_features(sequence, fold) for sequence in sorted(set(sequences))}
    return _structure_quantiles(
        [features[sequence]["mfe"] for sequence in sequences],
        [features[sequence]["mfe_per_nt"] for sequence in sequences],
        [features[sequence]["paired_fraction"] for sequence in sequences],
    )


def _not_applicable_metric(reason):
    return {"value": None, "applicability": "not_applicable", "status_reason": reason}


def _applicable_metric(value, reason=None):
    return {"value": value, "applicability": "applicable", "status_reason": reason}


def _older_m4_metrics(summary, empty_ledger):
    metrics = _m4()
    report = {}
    for metric_id in metrics.IMPLEMENTED_METRIC_IDS:
        if metric_id not in summary:
            report[metric_id] = _not_applicable_metric("not_in_m4_summary_keys")
            continue
        value = summary[metric_id]
        reason = None
        if metric_id == "largest_duplicate_share" and value is None:
            reason = summary.get("largest_duplicate_share_status") or "undefined_empty_valid_denominator"
        elif metric_id == "exact_hit_rate" and empty_ledger:
            reason = "m4_empty_raw_attempt_rate_is_defined_as_zero"
        elif isinstance(value, dict) and value.get("rate") == 0.0 and empty_ledger:
            reason = "m4_empty_denominator_rate_is_defined_as_zero"
        report[metric_id] = _applicable_metric(value, reason)
    return report


def _m4_not_projected(reason, exact_hit_reason=None):
    metrics = _m4()
    older = {}
    for metric_id in metrics.IMPLEMENTED_METRIC_IDS:
        status = exact_hit_reason if metric_id in (
            "exact_length_hits",
            "exact_hit_rate",
            "exact_hit_rate_valid_outputs_diagnostic",
        ) and exact_hit_reason else reason
        older[metric_id] = _not_applicable_metric(status)
    return {
        "parsed_outputs": None,
        "parsed_outputs_source": "not_projected",
        "parsed_outputs_applicability": "not_applicable",
        "parsed_outputs_status_reason": reason,
        "m4_summary": None,
        "m4_applicability": "not_applicable",
        "m4_status_reason": reason,
        "exact_hit_rate": None,
        "exact_hit_applicability": "not_applicable" if exact_hit_reason else "not_applicable",
        "exact_hit_status_reason": exact_hit_reason or reason,
        "exact_hit_source": "not_projected",
        "guardrail_values": {guardrail_id: None for guardrail_id in metrics.HARD_GUARDRAIL_IDS},
        "guardrail_decisions": [
            {
                "id": guardrail_id,
                "value": None,
                "comparison": metrics.GUARDRAIL_THRESHOLDS[guardrail_id]["comparison"],
                "threshold": metrics.GUARDRAIL_THRESHOLDS[guardrail_id]["threshold"],
                "passed": None,
                "status": "not_applicable",
                "undefined_reason": reason,
            }
            for guardrail_id in metrics.HARD_GUARDRAIL_IDS
        ],
        "guardrail_failures": [],
        "checkpoint_eligible": None,
        "older_m4_metrics": older,
        "m6_report_only_diagnostics_applicability": "not_applicable",
        "m6_report_only_diagnostics_status_reason": reason,
    }


def _projected_m4_metrics(rows, train_cores):
    attempts = _project_attempts(rows)
    summary_full = _m4().summarise_attempts(attempts)
    summary = {key: summary_full[key] for key in M4_SUMMARY_KEYS}
    summary["largest_duplicate_share_status"] = summary_full["largest_duplicate_share_status"]
    evaluation = _m4().evaluate_hard_guardrails(attempts, train_cores)
    headlines, decisions, failures = _guardrail_headlines(evaluation)
    empty_ledger = not attempts
    if empty_ledger:
        failures = []
        checkpoint_eligible = None
    else:
        checkpoint_eligible = evaluation["checkpoint_eligible"]
    exact_hit_reason = "m4_empty_raw_attempt_rate_is_defined_as_zero" if empty_ledger else None
    return {
        "parsed_outputs": summary["parsed_outputs"],
        "parsed_outputs_source": "m4_diagnostic_metrics.summarise_attempts",
        "parsed_outputs_applicability": "applicable",
        "parsed_outputs_status_reason": None,
        "m4_summary": {key: summary[key] for key in M4_SUMMARY_KEYS},
        "m4_applicability": "applicable",
        "m4_status_reason": None if not empty_ledger else "schema_valid_empty_ledger",
        "exact_hit_rate": summary["exact_hit_rate"],
        "exact_hit_applicability": "applicable",
        "exact_hit_status_reason": exact_hit_reason,
        "exact_hit_source": "m4_diagnostic_metrics.summarise_attempts",
        "guardrail_values": headlines,
        "guardrail_decisions": decisions,
        "guardrail_failures": failures,
        "checkpoint_eligible": checkpoint_eligible,
        "older_m4_metrics": _older_m4_metrics(summary_full, empty_ledger),
        "m6_report_only_diagnostics_applicability": "applicable",
        "m6_report_only_diagnostics_status_reason": None,
        "attempts": attempts,
        "per_requested_length_exact_hit_rate": _applicable_metric(
            [
                {
                    "requested_target_length": row["requested_target_length"],
                    "raw_attempts": row["raw_attempts"],
                    "exact_length_hits": row["exact_length_hits"],
                    "exact_hit_rate": row["exact_hit_rate"],
                }
                for row in summary_full["by_requested_length"]
            ],
            "schema_valid_empty_ledger" if empty_ledger else None,
        ),
    }


def _older_m6_metrics(generated, train_cores, structure, per_length_metric):
    """Schedule-free M6 descriptions, plus an explicit status for ledger-only metrics."""
    metrics = _m6()
    if not generated:
        nearest = _applicable_metric(None, "no_valid_generated_rows")
        similarity = _applicable_metric(None, "no_valid_generated_rows")
    else:
        nearest_map = {sequence: metrics.nearest_train(sequence, train_cores) for sequence in sorted(set(generated))}
        distances = [nearest_map[sequence] for sequence in generated]
        nearest = _applicable_metric(metrics._quantiles(distances), None)
        similarity = _applicable_metric(1.0 - min(distances), None)

    def from_structure(key):
        return {
            "value": structure.get(key),
            "applicability": "applicable",
            "status_reason": structure.get("undefined_reason"),
        }

    return {
        "nearest_train_normalized_edit_distance": nearest,
        "maximum_edit_similarity_to_train": similarity,
        "mfe": from_structure("mfe"),
        "mfe_per_nt": from_structure("mfe_per_nt"),
        "paired_fraction": from_structure("paired_fraction"),
        "per_requested_length_exact_hit_rate": per_length_metric,
    }


def _evaluation_row_counts(rows, train_cores):
    """Schedule-free counts. A schema-valid ledger keeps parsed_outputs == raw_attempts.

    Duplicate arithmetic is m4_diagnostic_metrics._duplicate_summary. This does
    not invent invocation seeds, EOS markers, or schedule provenance.
    """
    if not isinstance(rows, list):
        raise AnalysisContractError("records_invalid", "generated rows must be a list")
    if not isinstance(train_cores, (list, tuple)):
        raise AnalysisContractError("train_reference_invalid", "the synthetic TRAIN collection is missing")
    preflight = _preflight()
    metrics = _m4()
    valid_sequences = []
    empty_or_unparseable = 0
    for row in rows:
        if not isinstance(row, dict):
            raise AnalysisContractError("records_invalid", "a generated row is not an object")
        sequence = row.get("sequence")
        if preflight._row_is_valid(row):
            valid_sequences.append(sequence)
        elif sequence in (None, ""):
            empty_or_unparseable += 1
    duplicate = metrics._duplicate_summary(valid_sequences)
    raw = len(rows)
    valid = len(valid_sequences)
    train = set(train_cores)
    return {
        "raw_attempts": raw,
        "parsed_outputs": raw,
        "valid_outputs": valid,
        "invalid_outputs": raw - valid,
        "empty_or_unparseable_outputs": empty_or_unparseable,
        "unique_valid_outputs": duplicate["unique_valid_outputs"],
        "duplicates": duplicate["duplicates"],
        "largest_duplicate_multiplicity": duplicate["largest_duplicate_multiplicity"],
        "largest_duplicate_share": duplicate["largest_duplicate_share"],
        "largest_duplicate_share_status": duplicate["largest_duplicate_share_status"],
        "exact_train_matches": sum(sequence in train for sequence in valid_sequences),
    }


def _defined_ratio(numerator, denominator):
    if denominator == 0:
        return None
    return numerator / denominator


def _output_accounting_block(counts, successfully_parsed):
    metrics = _m4()
    valid = counts["valid_outputs"]
    raw = counts["raw_attempts"]
    share = counts["largest_duplicate_share"]
    return {
        "raw_attempts": raw,
        "parsed_outputs": counts["parsed_outputs"],
        "successfully_parsed_outputs": successfully_parsed,
        "valid_outputs": counts["valid_outputs"],
        "invalid_outputs": counts["invalid_outputs"],
        "empty_or_unparseable_outputs": counts["empty_or_unparseable_outputs"],
        "unique_valid_outputs": counts["unique_valid_outputs"],
        "duplicates": counts["duplicates"],
        "largest_duplicate_multiplicity": counts["largest_duplicate_multiplicity"],
        "largest_duplicate_share": share,
        "parsed_outputs_rule": LEGACY_PARSED_RULE,
        "parsed_outputs_equals_raw_attempts": counts["parsed_outputs"] == raw,
        "largest_duplicate_share_numerator": metrics.LARGEST_DUPLICATE_SHARE_NUMERATOR,
        "largest_duplicate_share_denominator": metrics.LARGEST_DUPLICATE_SHARE_DENOMINATOR,
        "largest_duplicate_share_denominator_count": valid,
        "largest_duplicate_share_undefined_reason": None if valid else "undefined_empty_valid_denominator",
        "denominators": {
            "raw_attempts": raw,
            "parsed_outputs": raw,
            "successfully_parsed_outputs": raw,
            "valid_outputs": raw,
            "invalid_outputs": raw,
            "empty_or_unparseable_outputs": raw,
            "unique_valid_outputs": valid,
            "duplicates": valid,
            "largest_duplicate_multiplicity": valid,
            "largest_duplicate_share": valid,
        },
    }


def _descriptive_guardrail_report(counts):
    """Report the five schedule-independent guardrails without an eligibility decision."""
    metrics = _m4()
    raw = counts["raw_attempts"]
    valid = counts["valid_outputs"]
    share = counts["largest_duplicate_share"]
    multiplicity = counts["largest_duplicate_multiplicity"]
    specifications = (
        (
            "valid_nonempty_acgu_fraction",
            counts["valid_outputs"],
            raw,
            "raw_attempts",
            "undefined_empty_raw_attempt_denominator",
        ),
        (
            "empty_or_unparseable_fraction",
            counts["empty_or_unparseable_outputs"],
            raw,
            "raw_attempts",
            "undefined_empty_raw_attempt_denominator",
        ),
        (
            "unique_fraction",
            counts["unique_valid_outputs"],
            valid,
            "valid_outputs",
            "undefined_empty_valid_denominator",
        ),
        (
            "exact_train_match_rate",
            counts["exact_train_matches"],
            valid,
            "valid_outputs",
            "undefined_empty_valid_denominator",
        ),
        (
            "largest_duplicate_share",
            multiplicity if valid else None,
            valid,
            "valid_outputs",
            "undefined_empty_valid_denominator",
        ),
    )
    values = {}
    decisions = []
    for guardrail_id, numerator, denominator, denominator_name, undefined_reason in specifications:
        rule = metrics.GUARDRAIL_THRESHOLDS[guardrail_id]
        if guardrail_id == "largest_duplicate_share":
            value = share
            reason = None if denominator else undefined_reason
        else:
            value = _defined_ratio(numerator, denominator)
            reason = None if denominator else undefined_reason
        values[guardrail_id] = value
        decisions.append(
            {
                "id": guardrail_id,
                "value": value,
                "numerator": numerator,
                "denominator": denominator_name,
                "denominator_count": denominator,
                "comparison": rule["comparison"],
                "threshold": rule["threshold"],
                "threshold_provenance": "m4_diagnostic_metrics.GUARDRAIL_THRESHOLDS",
                "passed": None,
                "status": DESCRIPTIVE_GUARDRAIL_STATUS,
                "undefined_reason": reason,
                "is_checkpoint_eligibility_decision": False,
                "is_a_closeness_vote": False,
            }
        )
    return values, decisions


def _requested_length_exact_hit(rows):
    """Overall and per-requested-length exact hits from recorded requested_length."""
    preflight = _preflight()
    metrics = _m4()
    by_length = {}
    hits = 0
    for row in rows:
        requested = row["requested_length"]
        bucket = by_length.setdefault(requested, {"raw_attempts": 0, "exact_length_hits": 0})
        bucket["raw_attempts"] += 1
        if preflight._row_is_valid(row) and row["observed_length"] == requested:
            hits += 1
            bucket["exact_length_hits"] += 1
    raw = len(rows)
    per_length = []
    for requested in sorted(by_length):
        item = by_length[requested]
        per_length.append(
            {
                "requested_length": requested,
                "raw_attempts": item["raw_attempts"],
                "exact_length_hits": item["exact_length_hits"],
                "exact_hit_rate": metrics._rate(item["exact_length_hits"], item["raw_attempts"]),
                "exact_hit_rate_denominator": "raw_attempts",
            }
        )
    return {
        "exact_length_hits": hits,
        "exact_hit_rate": metrics._rate(hits, raw),
        "exact_hit_rate_denominator": "raw_attempts",
        "by_requested_length": per_length,
        "undefined_reason": "m4_empty_raw_attempt_rate_is_defined_as_zero" if raw == 0 else None,
    }


def schedule_independent_output_accounting(rows, train_cores):
    """Accounting and descriptive guardrails that do not need an M4 attempt ledger."""
    counts = _evaluation_row_counts(rows, train_cores)
    values, decisions = _descriptive_guardrail_report(counts)
    parsed = successfully_parsed_outputs(rows)
    return {
        **{key: counts[key] for key in OUTPUT_ACCOUNTING_FIELDS},
        "successfully_parsed_outputs": parsed,
        "exact_train_matches": counts["exact_train_matches"],
        "output_accounting": _output_accounting_block(counts, parsed),
        "guardrail_values": values,
        "guardrail_decisions": decisions,
        "checkpoint_eligible": None,
        "checkpoint_eligibility_applied": False,
    }


def _older_descriptive_metrics(counts, exact_hit, exact_hit_reason):
    metrics = _m4()
    report = {}
    for metric_id in metrics.IMPLEMENTED_METRIC_IDS:
        if metric_id in OUTPUT_ACCOUNTING_FIELDS:
            value = counts[metric_id]
            reason = None
            if metric_id == "largest_duplicate_share" and value is None:
                reason = counts["largest_duplicate_share_status"]
            report[metric_id] = _applicable_metric(value, reason)
            continue
        if metric_id == "exact_length_hits":
            if exact_hit is None:
                report[metric_id] = _not_applicable_metric(exact_hit_reason)
            else:
                report[metric_id] = _applicable_metric(exact_hit["exact_length_hits"], exact_hit["undefined_reason"])
            continue
        if metric_id == "exact_hit_rate":
            if exact_hit is None:
                report[metric_id] = _not_applicable_metric(exact_hit_reason)
            else:
                report[metric_id] = _applicable_metric(exact_hit["exact_hit_rate"], exact_hit["undefined_reason"])
            continue
        if metric_id == "exact_hit_rate_valid_outputs_diagnostic":
            if exact_hit is None:
                report[metric_id] = _not_applicable_metric(exact_hit_reason)
            else:
                valid = counts["valid_outputs"]
                report[metric_id] = _applicable_metric(
                    {
                        "label": metrics.VALID_ONLY_EXACT_HIT_LABEL,
                        "rate": metrics._rate(exact_hit["exact_length_hits"], valid),
                        "denominator": "valid_outputs",
                        "replaces_approved_raw_attempt_metric": False,
                    },
                    "m4_empty_denominator_rate_is_defined_as_zero" if valid == 0 else None,
                )
            continue
        report[metric_id] = _not_applicable_metric(SCHEDULE_EVIDENCE_NOT_AVAILABLE)
    return report


def _descriptive_ledger_metrics(rows, train_cores, m4_reason, exact_hit_reason, use_requested_length):
    independent = schedule_independent_output_accounting(rows, train_cores)
    counts = _evaluation_row_counts(rows, train_cores)
    exact_hit = _requested_length_exact_hit(rows) if use_requested_length else None
    per_length = (
        _applicable_metric(
            exact_hit["by_requested_length"],
            "schema_valid_empty_ledger" if not rows else None,
        )
        if use_requested_length
        else _not_applicable_metric(exact_hit_reason)
    )
    exact_hit_value = None if exact_hit is None else exact_hit["exact_hit_rate"]
    return {
        "parsed_outputs": independent["parsed_outputs"],
        "parsed_outputs_source": LEGACY_PARSED_RULE,
        "parsed_outputs_applicability": "applicable",
        "parsed_outputs_status_reason": None,
        "m4_summary": {key: independent[key] for key in OUTPUT_ACCOUNTING_FIELDS},
        "m4_applicability": "schedule_independent",
        "m4_status_reason": m4_reason,
        "attempt_ledger_projection": "not_applicable",
        "attempt_ledger_projection_reason": m4_reason,
        "exact_length_hits": None if exact_hit is None else exact_hit["exact_length_hits"],
        "exact_hit_rate": exact_hit_value,
        "exact_hit_applicability": "applicable" if use_requested_length else "not_applicable",
        "exact_hit_status_reason": exact_hit["undefined_reason"] if use_requested_length else exact_hit_reason,
        "exact_hit_source": "evaluation_record_requested_length" if use_requested_length else "not_applicable",
        "exact_hit_rate_denominator": None if exact_hit is None else exact_hit["exact_hit_rate_denominator"],
        "guardrail_values": independent["guardrail_values"],
        "guardrail_decisions": independent["guardrail_decisions"],
        "guardrail_failures": [],
        "checkpoint_eligible": None,
        "checkpoint_eligibility_applied": False,
        "older_m4_metrics": _older_descriptive_metrics(counts, exact_hit, exact_hit_reason),
        "per_requested_length_exact_hit_rate": per_length,
        "output_accounting": independent["output_accounting"],
        "counts": counts,
    }


def _population_metrics(rows, reference, train_cores, fold, project_m4=True, m4_reason=None, exact_hit_reason=None, use_requested_length=False):
    generated = _valid_sequences(rows)
    gc = pooled_gc_fraction(generated) if generated else None
    closeness = _closeness_population(generated, reference)
    successfully_parsed = successfully_parsed_outputs(rows)
    if project_m4:
        projected = _projected_m4_metrics(rows, train_cores)
        attempts = projected.pop("attempts")
        structure = _structure_block(attempts, train_cores, fold)
        if fold is None:
            m6_applicability = "not_applicable"
            m6_reason = "no_synthetic_fold_supplied"
        elif not attempts:
            m6_applicability = "not_applicable"
            m6_reason = "no_projected_attempts"
        else:
            m6_applicability = "applicable"
            m6_reason = None
        raw_attempts = projected["m4_summary"]["raw_attempts"]
        raw_source = "m4_diagnostic_metrics.summarise_attempts"
        output_accounting = _output_accounting_block(projected["m4_summary"], successfully_parsed)
    else:
        projected = _descriptive_ledger_metrics(rows, train_cores, m4_reason, exact_hit_reason, use_requested_length)
        projected.pop("counts", None)
        output_accounting = projected.pop("output_accounting")
        structure = _structure_from_sequences(generated, fold)
        m6_applicability = "not_applicable"
        m6_reason = m4_reason
        raw_attempts = output_accounting["raw_attempts"]
        raw_source = "evaluation_ledger_rows"
    per_length = projected.pop("per_requested_length_exact_hit_rate", _not_applicable_metric(exact_hit_reason or m4_reason))
    projected.pop("m6_report_only_diagnostics_applicability", None)
    projected.pop("m6_report_only_diagnostics_status_reason", None)
    return {
        "successfully_parsed_outputs": successfully_parsed,
        "raw_attempts": raw_attempts,
        "raw_attempts_source": raw_source,
        "output_accounting": output_accounting,
        **projected,
        "pooled_gc_fraction": gc,
        "pooled_gc_undefined_reason": None if generated else "no_canonical_bases",
        "closeness": closeness,
        "train_nested_descriptive": _train_nested(generated, train_cores),
        "structure": structure,
        "older_m6_metrics": _older_m6_metrics(generated, train_cores, structure, per_length),
        "m6_report_only_diagnostics_applicability": m6_applicability,
        "m6_report_only_diagnostics_status_reason": m6_reason,
        "generated_valid_row_denominator": len(generated),
        "generated_unique_valid_count": len(set(generated)),
        "reference_unique_core_denominator": len(reference),
        "row_count": len(rows),
        "is_training_replicate": False,
    }


def _stratum_parsed_outputs(selected, project_m4):
    if not project_m4:
        return len(selected), "applicable"
    summary = _m4().summarise_attempts(_project_attempts(selected))
    return summary["parsed_outputs"], "applicable"


def _stratified_populations(rows, prepared, fold, project_m4=True, parsed_status_reason=None):
    if not prepared["stratified"]:
        return None
    result = {}
    for label in S6_LABELS:
        selected = [row for row in rows if prepared["labels_by_record_id"].get(row["record_id"]) == label]
        reference = prepared["reference_by_stratum"][label]
        generated = _valid_sequences(selected)
        if not reference:
            closeness = _closeness_population([], [])
            closeness["nearest_reference_normalized_edit_distance"]["undefined_reason"] = "no_reference_sequences_in_stratum"
            closeness["nucleotide_total_variation_to_reference"]["undefined_reason"] = "no_reference_sequences_in_stratum"
            closeness["dinucleotide_total_variation_to_reference"]["undefined_reason"] = "no_reference_sequences_in_stratum"
            for key in CLOSENESS_HEADLINE_KEYS:
                closeness["headlines"][key] = None
        else:
            closeness = _closeness_population(generated, reference)
        parsed_outputs, parsed_applicability = _stratum_parsed_outputs(selected, project_m4)
        result[label] = {
            "raw_attempts": len(selected),
            "successfully_parsed_outputs": successfully_parsed_outputs(selected),
            "parsed_outputs": parsed_outputs,
            "parsed_outputs_applicability": parsed_applicability,
            "parsed_outputs_status_reason": None if parsed_applicability == "applicable" else parsed_status_reason,
            "pooled_gc_fraction": pooled_gc_fraction(generated) if generated else None,
            "pooled_gc_undefined_reason": None if generated else "no_canonical_bases",
            "closeness": closeness,
            "generated_valid_row_denominator": len(generated),
            "generated_unique_valid_count": len(set(generated)),
            "reference_unique_core_denominator": len(reference),
            "row_count": len(selected),
            "stratum_inferred_from_length": False,
        }
    return result


def _condition_block(condition, rows, prepared, fold):
    preflight = _preflight()
    accounting = preflight._accounting(rows, condition)
    reference = prepared["reference_sequences"]
    train_cores = prepared["train_cores"]
    if condition == "B0":
        block = _population_metrics(
            rows,
            reference,
            train_cores,
            fold,
            project_m4=False,
            m4_reason=B0_M4_NOT_APPLICABLE,
            exact_hit_reason=preflight.B0_EXACT_HIT_NOT_APPLICABLE,
        )
        block["external_historical_comparator"] = True
        block["requested_biological_length"] = "unavailable"
        block["closeness_in_directional_consistency"] = False
        block["included_in_b1_d1_controlled_comparison"] = False
        project_m4 = False
        parsed_status_reason = B0_M4_NOT_APPLICABLE
    elif condition == "B2":
        block = _population_metrics(
            rows,
            reference,
            train_cores,
            fold,
            project_m4=False,
            m4_reason=B2_M4_NOT_APPLICABLE,
            use_requested_length=True,
        )
        seeds = sorted({row["empirical_null_seed"] for row in rows})
        block["empirical_null_seed"] = seeds[0] if len(seeds) == 1 else None
        block["empirical_null_seed_count"] = len(seeds)
        block["empirical_null_seed_status_reason"] = None if len(seeds) == 1 else "no_b2_rows"
        block["rows_are_training_replicates"] = False
        accounting["exact_length_hits"] = block["exact_length_hits"]
        accounting["exact_hit_rate"] = block["exact_hit_rate"]
        accounting["exact_hit_rate_denominator"] = block["exact_hit_rate_denominator"]
        accounting["exact_hit_applicability"] = block["exact_hit_applicability"]
        block["closeness_in_directional_consistency"] = False
        block["included_in_b1_d1_controlled_comparison"] = False
        project_m4 = False
        parsed_status_reason = B2_M4_NOT_APPLICABLE
    else:
        block = _population_metrics(rows, reference, train_cores, fold)
        block["closeness_in_directional_consistency"] = True
        block["included_in_b1_d1_controlled_comparison"] = True
        project_m4 = True
        parsed_status_reason = None
    block["condition"] = condition
    block["accounting"] = accounting
    block["stratified"] = _stratified_populations(
        rows,
        prepared,
        fold,
        project_m4=project_m4,
        parsed_status_reason=parsed_status_reason,
    )
    block["is_training_replicate"] = False
    return block


def _b0_panel(rows):
    preflight = _preflight()
    provenance = preflight._b0_provenance(rows)
    return {
        "external_comparator": bool(rows),
        "length_regime": "historical_37nt" if rows else None,
        "nominal_max_seq_len": 37 if rows else None,
        "requested_biological_length": "unavailable",
        "exact_hit_applicability": "not_applicable",
        "exact_hit_status_reason": preflight.B0_EXACT_HIT_NOT_APPLICABLE,
        "included_in_b1_d1_controlled_comparison": False,
        "included_in_directional_consistency": False,
        "historical_generation_seeds_are_training_replicates": False if rows else None,
        "historical_batches_are_training_replicates": False if rows else None,
        "candidate_rows_are_training_replicates": False if rows else None,
        "provenance": provenance,
    }


def _headline_value(block, key):
    if key == "exact_hit_rate":
        return block.get("exact_hit_rate")
    if key == "pooled_gc_fraction":
        return block.get("pooled_gc_fraction")
    if key in block.get("guardrail_values", {}):
        return block["guardrail_values"][key]
    if key == "nearest_reference_normalized_edit_distance.median":
        return block["closeness"]["headlines"][key]
    if key in ("nucleotide_total_variation_to_reference", "dinucleotide_total_variation_to_reference"):
        return block["closeness"]["headlines"][key]
    if key == "mfe_per_nt.median":
        return block["structure"]["mfe_per_nt.median"]
    if key == "paired_fraction.median":
        return block["structure"]["paired_fraction.median"]
    return None


def _observed_range(seed_blocks, fold_supplied):
    keys = list(OBSERVED_RANGE_KEYS)
    if fold_supplied:
        keys.extend(FOLD_RANGE_KEYS)
    observed = {}
    for key in keys:
        values = [_headline_value(block, key) for block in seed_blocks]
        if any(value is None for value in values):
            observed[key] = {
                "minimum": None,
                "maximum": None,
                "undefined_reason": "undefined_for_at_least_one_training_seed",
            }
            continue
        observed[key] = {"minimum": min(values), "maximum": max(values), "undefined_reason": None}
    return observed


def _d1_seed_report(rows, prepared, fold):
    seeds = sorted({row["training_seed"] for row in rows})
    blocks = []
    for seed in seeds:
        selected = [row for row in rows if row["training_seed"] == seed]
        block = _population_metrics(selected, prepared["reference_sequences"], prepared["train_cores"], fold)
        block["training_seed"] = seed
        block["stratified"] = _stratified_populations(selected, prepared, fold)
        block["is_training_replicate_unit"] = True
        blocks.append(block)
    if len(seeds) == 1:
        return {
            "d1_training_seeds": seeds,
            "d1_training_seed_count": 1,
            "by_training_seed": blocks,
            "observed_range": None,
            "observed_range_omitted_reason": "single_d1_training_seed",
            "observed_range_is_a_confidence_interval": False,
            "one_d1_training_seed_limitation": True,
            "uncertainty_excludes_training_run_variability": True,
            "uncertainty_statement": ONE_D1_SEED_STATEMENT,
            "training_replicate_unit": "training_seed",
            "not_training_replicate_units": list(NOT_TRAINING_REPLICATE_UNITS),
        }
    if len(seeds) == 0:
        return {
            "d1_training_seeds": [],
            "d1_training_seed_count": 0,
            "by_training_seed": [],
            "observed_range": None,
            "observed_range_omitted_reason": "no_d1_training_seed",
            "observed_range_is_a_confidence_interval": False,
            "one_d1_training_seed_limitation": False,
            "uncertainty_excludes_training_run_variability": False,
            "uncertainty_statement": "No D1 training seed is present.",
            "training_replicate_unit": "training_seed",
            "not_training_replicate_units": list(NOT_TRAINING_REPLICATE_UNITS),
        }
    return {
        "d1_training_seeds": seeds,
        "d1_training_seed_count": len(seeds),
        "by_training_seed": blocks,
        "observed_range": _observed_range(blocks, fold is not None),
        "observed_range_omitted_reason": None,
        "observed_range_is_a_confidence_interval": False,
        "one_d1_training_seed_limitation": False,
        "uncertainty_excludes_training_run_variability": False,
        "uncertainty_statement": OBSERVED_RANGE_STATEMENT,
        "training_replicate_unit": "training_seed",
        "not_training_replicate_units": list(NOT_TRAINING_REPLICATE_UNITS),
    }


def _block_closeness(rows, reference):
    generated = _valid_sequences(rows)
    return _closeness_population(generated, reference)


def _closeness_side(closeness, training_seed=None):
    nearest = closeness["nearest_reference_normalized_edit_distance"]
    side = {
        "headlines": closeness["headlines"],
        "closeness_values": {
            "nearest_reference_normalized_edit_distance": nearest["value"],
            "nucleotide_total_variation_to_reference": closeness["nucleotide_total_variation_to_reference"]["value"],
            "dinucleotide_total_variation_to_reference": closeness["dinucleotide_total_variation_to_reference"]["value"],
        },
        "generated_valid_row_denominator": nearest["generated_valid_row_denominator"],
        "generated_unique_valid_count": nearest["generated_unique_valid_count"],
        "reference_unique_core_denominator": nearest["reference_unique_core_denominator"],
    }
    if training_seed is not None:
        side["training_seed"] = training_seed
    return side


def _matched_blocks(rows, prepared):
    preflight = _preflight()
    structure = preflight.matched_schedule_structure(rows)
    metrics = _m6()
    reference = prepared["reference_sequences"]
    b1_by_index = {}
    d1_by_seed = {}
    for row in rows:
        if row["condition"] == "B1" and row["invocation_index"] is not None:
            b1_by_index.setdefault(row["invocation_index"], []).append(row)
        elif row["condition"] == "D1" and row["invocation_index"] is not None:
            d1_by_seed.setdefault((row["training_seed"], row["invocation_index"]), []).append(row)
    seeds_for_index = {}
    for seed, index in d1_by_seed:
        seeds_for_index.setdefault(index, set()).add(seed)
    matched = []
    incompatible = []
    for block in structure["matched_schedule_blocks"]:
        index = block["invocation_index"]
        b1_rows = b1_by_index.get(index, [])
        for seed in sorted(seeds_for_index.get(index, ())):
            d1_rows = d1_by_seed[(seed, index)]
            d1_attempt_ids = {row["original_attempt_index"] for row in d1_rows}
            b1_subset = [row for row in b1_rows if row["original_attempt_index"] in d1_attempt_ids]
            b1_attempts = _project_attempts(b1_subset)
            d1_attempts = _project_attempts(d1_rows)
            pairing_passed = False
            pairing_reason = None
            try:
                metrics.assert_pairing(d1_attempts, b1_attempts)
                pairing_passed = True
            except metrics.DiagnosticError as exc:
                pairing_reason = exc.code
            attempt_indexes = sorted(d1_attempt_ids)
            b1_attempt_indexes = sorted(row["original_attempt_index"] for row in b1_subset)
            if not pairing_passed:
                incompatible.append(
                    {
                        "invocation_index": index,
                        "training_seed": seed,
                        "original_attempt_indexes": attempt_indexes,
                        "b1_original_attempt_indexes": b1_attempt_indexes,
                        "reasons": [pairing_reason or "pairing_invalid"],
                        "generation_chunk_ids": sorted({row["generation_chunk_id"] for row in b1_subset + d1_rows}),
                        "included_in_controlled_comparison": False,
                        "is_training_replicate": False,
                        "chunk_label_is_sufficient": False,
                        "pooled_across_d1_training_seeds": False,
                        "compared_with_entire_b1_invocation": False,
                    }
                )
                continue
            b1_closeness = _block_closeness(b1_subset, reference)
            d1_closeness = _block_closeness(d1_rows, reference)
            comparison = directional_consistency(b1_closeness["headlines"], d1_closeness["headlines"])
            entire_invocation = (
                len(b1_subset) == len(b1_rows)
                and {row["original_attempt_index"] for row in b1_rows} == d1_attempt_ids
            )
            matched.append(
                {
                    "training_seed": seed,
                    "invocation_index": index,
                    "original_attempt_indexes": attempt_indexes,
                    "b1_original_attempt_indexes": b1_attempt_indexes,
                    "b1_invocation_row_count": len(b1_rows),
                    "compared_with_entire_b1_invocation": entire_invocation,
                    "compatible": True,
                    "pairing_predicate": "m6_diagnostic_generation.assert_pairing",
                    "pairing_predicate_passed": True,
                    "pairing_failure": None,
                    "is_training_replicate": False,
                    "is_independent_biological_replicate": False,
                    "is_significance_test_unit": False,
                    "pooled_across_d1_training_seeds": False,
                    "b1": _closeness_side(b1_closeness),
                    "d1": _closeness_side(d1_closeness, seed),
                    "d1_minus_b1": comparison["differences"],
                    "directional_consistency": comparison["label"],
                    "p_value": None,
                    "confidence_interval": None,
                }
            )
    for block in structure["incompatible_schedule_blocks"]:
        index = block["invocation_index"]
        incompatible.append(
            {
                "invocation_index": index,
                "training_seeds": sorted(seeds_for_index.get(index, ())),
                "reasons": list(block["reasons"]),
                "generation_chunk_ids": list(block["generation_chunk_ids"]),
                "included_in_controlled_comparison": False,
                "is_training_replicate": False,
                "chunk_label_is_sufficient": False,
                "pooled_across_d1_training_seeds": False,
            }
        )
    reused_identities = set()
    seeds_by_identity = {}
    for block in matched:
        identity = (block["invocation_index"], tuple(block["original_attempt_indexes"]))
        seeds_by_identity.setdefault(identity, set()).add(block["training_seed"])
    for identity, seeds in seeds_by_identity.items():
        if len(seeds) > 1:
            reused_identities.add(identity)
    for block in matched:
        identity = (block["invocation_index"], tuple(block["original_attempt_indexes"]))
        reused = identity in reused_identities
        block["b1_comparator_reused_across_d1_training_seeds"] = reused
        block["b1_reuse_creates_additional_independent_b1_replicates"] = False
        block["b1_reuse_statement"] = B1_REUSE_STATEMENT if reused else None
    matched.sort(key=lambda block: (block["invocation_index"], block["training_seed"]))
    incompatible_indexes = list(structure["incompatible_invocation_indexes"])
    for block in incompatible:
        if block["invocation_index"] not in incompatible_indexes:
            incompatible_indexes.append(block["invocation_index"])
    return {
        "matched_blocks": matched,
        "incompatible_blocks": incompatible,
        "b1_only_blocks": structure["b1_only_schedule_blocks"],
        "d1_only_blocks": structure["d1_only_schedule_blocks"],
        "matched_invocation_indexes": sorted({block["invocation_index"] for block in matched}),
        "incompatible_invocation_indexes": incompatible_indexes,
        "b1_only_invocation_indexes": structure["b1_only_invocation_indexes"],
        "d1_only_invocation_indexes": structure["d1_only_invocation_indexes"],
        "generation_chunk_label_is_sufficient_evidence": False,
        "schedule_blocks_are_training_replicates": False,
        "schedule_blocks_are_independent_biological_replicates": False,
        "matched_blocks_pool_d1_training_seeds": False,
        "b1_comparator_reused_across_d1_training_seeds": bool(reused_identities),
        "b1_reuse_creates_additional_independent_b1_replicates": False,
        "b1_reuse_statement": B1_REUSE_STATEMENT if reused_identities else None,
        "p_values_computed": False,
        "confidence_intervals_computed": False,
        "includes_b0": False,
        "includes_b2": False,
    }


def _guardrail_policy(condition_blocks):
    failures = []
    for name, block in condition_blocks.items():
        for guardrail_id in block.get("guardrail_failures", []):
            failures.append({"condition": name, "id": guardrail_id})
    return {
        "failures": failures,
        "failure_remains_visible": True,
        "failure_authorizes_replacement": False,
        "failure_authorizes_exclusion_after_eval": False,
        "failure_is_a_closeness_vote": False,
        "final_pool_used": False,
    }


def _sequence_strings(prepared):
    sequences = set(prepared["train_cores"]) | set(prepared["reference_sequences"])
    for row in prepared["rows"]:
        if isinstance(row.get("sequence"), str) and row["sequence"]:
            sequences.add(row["sequence"])
    return sequences


def _assert_no_sequence_strings(report, sequences):
    encoded = json.dumps(report, sort_keys=True)
    for sequence in sequences:
        if sequence and sequence in encoded:
            raise AnalysisContractError("sequence_leak", "the analysis report contains a sequence string")


def calculate_analysis(prepared, fold=None):
    """Calculate metrics for inputs that have already passed the closed checks."""
    rows = prepared["rows"]
    by_condition = {}
    for condition in ("B0", "B1", "B2", "D1"):
        selected = [row for row in rows if row["condition"] == condition]
        by_condition[condition] = _condition_block(condition, selected, prepared, fold)
    b1_headlines = by_condition["B1"].get("closeness", {}).get("headlines")
    d1_headlines = by_condition["D1"].get("closeness", {}).get("headlines")
    if b1_headlines is None or d1_headlines is None:
        consistency = directional_consistency(
            {key: None for key in CLOSENESS_HEADLINE_KEYS},
            {key: None for key in CLOSENESS_HEADLINE_KEYS},
        )
    else:
        consistency = directional_consistency(b1_headlines, d1_headlines)
    d1_rows = [row for row in rows if row["condition"] == "D1"]
    report = {
        "schema_version": "generator-eval-analysis-gep2-r2",
        "package_id": "GEP-2",
        "mode": "synthetic_analysis",
        "eval_access": "locked",
        "status": "completed",
        "reference_role": prepared["reference_role"],
        "reference_id": prepared["reference_id"],
        "synthetic_train_core_count": len(prepared["train_cores"]),
        "synthetic_reference_unique_count": len(prepared["reference_sequences"]),
        "synthetic_train_and_reference_fixtures_only": True,
        "no_eval_data_loaded": True,
        "no_ref_or_validation_data_loaded": True,
        "no_eval_ref_or_validation_data_loaded": True,
        "production_train_loaded": False,
        "production_pools_loaded": False,
        "checkpoints_loaded": False,
        "viennarna_called": False,
        "aggregate_generator_quality_score": False,
        "combined_closeness_score": False,
        "conditions": by_condition,
        "b0_panel": _b0_panel([row for row in rows if row["condition"] == "B0"]),
        "b1_d1_directional_consistency": consistency,
        "d1_by_training_seed": _d1_seed_report(d1_rows, prepared, fold),
        "matched_b1_d1_blocks": _matched_blocks(rows, prepared),
        "schedule_provenance": prepared["schedule"],
        "b2_seed_mapping": None
        if prepared["b2_mapping"] is None
        else {
            "empirical_null_seed": prepared["b2_mapping"]["empirical_null_seed"],
            "b2_seed_count": prepared["b2_mapping"]["b2_seed_count"],
            "training_seed_created": False,
            "generic_seed_retained": False,
            "production_seed_42_assumed": False,
            "rows_are_training_replicates": False,
        },
        "guardrail_policy": _guardrail_policy(by_condition),
        "stratified": prepared["stratified"],
        "s6_stratum_inferred_from_length": False,
    }
    _assert_no_sequence_strings(report, _sequence_strings(prepared))
    return report


def analyse(document, fold=None, _after_validation=None):
    """Validate synthetic inputs, then calculate. Validation failures do not calculate."""
    prepared = prepare_analysis_inputs(document)
    if _after_validation is not None:
        return _after_validation(prepared)
    return calculate_analysis(prepared, fold=fold)


def fixture_root():
    return os.path.join(_repo_root(), FIXTURE_RELATIVE)


def load_named_fixture(name):
    """Load one synthetic GEP-2 fixture by basename. Paths are refused."""
    if not isinstance(name, str) or name != os.path.basename(name) or name in ("", ".", ".."):
        raise AnalysisContractError("path_input_refused", "fixture names cannot be paths")
    if "/" in name or "\\" in name or name.startswith("."):
        raise AnalysisContractError("path_input_refused", "fixture names cannot be paths")
    root = os.path.realpath(fixture_root())
    path = os.path.realpath(os.path.join(root, name))
    if path != root and not path.startswith(root + os.sep):
        raise AnalysisContractError("path_input_refused", "the fixture is outside the synthetic directory")
    if not os.path.isfile(path):
        raise AnalysisContractError("fixture_missing", "the synthetic fixture is missing")
    if os.path.getsize(path) > MAX_FIXTURE_BYTES:
        raise AnalysisContractError("fixture_too_large", "the synthetic fixture exceeds the size bound")
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    return document


def render_analysis_text(report):
    """Print counts, hashes, statuses, metric names, and denominators only."""
    consistency = report["b1_d1_directional_consistency"]
    seeds = report["d1_by_training_seed"]
    lines = [
        "GEP-2 synthetic generator-evaluation analysis",
        "mode: synthetic_analysis",
        "status: " + report["status"],
        "EVAL access: locked",
        "only synthetic TRAIN/reference fixtures used",
        "no EVAL, REF or VALIDATION data loaded",
        "reference_role: " + report["reference_role"],
        "reference_id: " + report["reference_id"],
        "synthetic_train_core_count: %d" % report["synthetic_train_core_count"],
        "synthetic_reference_unique_count: %d" % report["synthetic_reference_unique_count"],
        "aggregate_generator_quality_score: false",
        "combined_closeness_score: false",
        "viennarna_called: false",
        "production_pools_loaded: false",
        "directional_consistency: " + consistency["label"],
        "d1_training_seed_count: %d" % seeds["d1_training_seed_count"],
        "one_d1_training_seed_limitation: " + json.dumps(seeds["one_d1_training_seed_limitation"]),
        "observed_range_is_a_confidence_interval: false",
    ]
    if seeds["uncertainty_statement"]:
        lines.append(seeds["uncertainty_statement"])
    for condition in ("B0", "B1", "B2", "D1"):
        block = report["conditions"][condition]
        lines.append(
            "%s: rows=%d successfully_parsed_outputs=%s valid_rows=%s"
            % (
                condition,
                block["row_count"],
                block["successfully_parsed_outputs"],
                block.get("generated_valid_row_denominator", block.get("accounting", {}).get("valid_acgu")),
            )
        )
    b1 = report["conditions"]["B1"]
    if "closeness" in b1:
        lines.append("closeness_metrics: nearest_reference_normalized_edit_distance nucleotide_total_variation_to_reference dinucleotide_total_variation_to_reference")
        lines.append("pooled_gc_fraction_defined: " + json.dumps(b1["pooled_gc_fraction"] is not None))
        nearest = b1["closeness"]["nearest_reference_normalized_edit_distance"]
        lines.append("b1_generated_valid_row_denominator: %d" % nearest["generated_valid_row_denominator"])
        lines.append("b1_generated_unique_valid_count: %d" % nearest["generated_unique_valid_count"])
        lines.append("b1_reference_unique_core_denominator: %d" % nearest["reference_unique_core_denominator"])
    lines.append("b0_exact_hit_applicability: " + json.dumps(report["b0_panel"]["exact_hit_applicability"]))
    lines.append("b0_external_comparator: " + json.dumps(report["b0_panel"]["external_comparator"]))
    lines.append("guardrail_failure_count: %d" % len(report["guardrail_policy"]["failures"]))
    lines.append("guardrail_failure_authorizes_replacement: false")
    schedule = report["schedule_provenance"]
    if schedule is not None:
        lines.append("schedule_attempt_count: %d" % schedule["attempt_count"])
        lines.append("production_budget_satisfied: false")
        lines.append("final_d1_attempt_budget: %d" % schedule["final_d1_attempt_budget"])
        lines.append("final_d1_attempt_budget_is_total_across_retained_seeds: true")
        lines.append("d1_training_seeds_each_receive_full_budget: false")
        binding = schedule.get("ledger_binding")
        if isinstance(binding, dict):
            lines.append("scheduled_attempt_count: %d" % binding["scheduled_attempt_count"])
            lines.append("b1_attempt_count: %d" % binding["b1_attempt_count"])
            lines.append("d1_attempt_count: %d" % binding["d1_attempt_count"])
            lines.append("d1_union_covers_schedule_exactly_once: true")
        lines.append("length_vector_sha256: " + schedule["length_vector_sha256"])
    b2 = report["b2_seed_mapping"]
    if b2 is not None:
        lines.append("b2_empirical_null_seed_count: %d" % b2["b2_seed_count"])
        lines.append("b2_production_seed_42_assumed: false")
    lines.append("matched_invocation_indexes: " + json.dumps(report["matched_b1_d1_blocks"]["matched_invocation_indexes"]))
    lines.append("incompatible_invocation_indexes: " + json.dumps(report["matched_b1_d1_blocks"]["incompatible_invocation_indexes"]))
    lines.append("b1_only_invocation_indexes: " + json.dumps(report["matched_b1_d1_blocks"]["b1_only_invocation_indexes"]))
    lines.append("d1_only_invocation_indexes: " + json.dumps(report["matched_b1_d1_blocks"]["d1_only_invocation_indexes"]))
    lines.append("no sequence strings")
    return "\n".join(lines) + "\n"


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        sys.stderr.write("gep2_cli_rejected: the analysis command does not accept paths or an EVAL unlock\n")
        return 2
    document = load_named_fixture(DEFAULT_FIXTURE_NAME)
    report = analyse(document)
    spec = _preflight().load_metric_spec()
    unresolved = sum(item.get("status") == "unresolved" for item in spec["blocking_items"])
    text = render_analysis_text(report)
    prefix = [
        "metric_count: %d" % len(spec["metrics"]),
        "unresolved_item_count: %d" % unresolved,
        "metric_ids: " + ",".join(metric["metric_id"] for metric in spec["metrics"]),
    ]
    sys.stdout.write("\n".join(prefix) + "\n" + text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

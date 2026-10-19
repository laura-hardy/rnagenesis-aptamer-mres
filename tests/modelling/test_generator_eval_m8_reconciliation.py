"""Synthetic M8 protocol-reconciliation checks.

No REF, EVAL, VALIDATION, TRAIN, production generation, checkpoint, or model
result is opened. Sequences in this module are constructed literals.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import unittest
from fractions import Fraction

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOW_VALIDITY = os.path.join(
    ROOT,
    "tests/modelling/fixtures/generator_eval_m8/synthetic_low_validity_no_replenishment.json",
)


def load_module(filename, name):
    path = os.path.join(ROOT, "scripts/modelling", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gep1 = load_module("generator_eval_preflight.py", "generator_eval_preflight_m8")
analysis = load_module("generator_eval_analysis.py", "generator_eval_analysis_m8")


def load_helpers():
    path = os.path.join(ROOT, "tests/modelling/test_generator_eval_gep2.py")
    spec = importlib.util.spec_from_file_location("generator_eval_gep2_helpers_m8", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helpers = load_helpers()


def raw_bundle(condition, attempts):
    document = {
        "contract": gep1.SYNTHETIC_RAW_CONTRACT,
        "condition": condition,
        "attempts": attempts,
    }
    return json.dumps(document, sort_keys=True).encode("utf-8")


def manifest_for(raw, expected=None, expected_derived_hash=None, source_id="synthetic-m8-bundle"):
    """Source manifest only. The derived-ledger hash is not a parse prerequisite."""
    source_hash = hashlib.sha256(raw).hexdigest()
    manifest = {
        "source_artifact_id": source_id,
        "source_artifact_sha256": source_hash,
        "source_byte_size": len(raw),
        "parser_adapter_version": gep1.SYNTHETIC_PARSER_ADAPTER_VERSION,
        "replenishment_prohibited": gep1.REPLENISHMENT_PROHIBITED_STATEMENT,
    }
    if expected is not None:
        manifest["expected_attempt_count"] = expected
    if expected_derived_hash is not None:
        manifest["expected_derived_ledger_sha256"] = expected_derived_hash
    return manifest, source_hash


def parse_bundle(raw, expected=None):
    manifest, source_hash = manifest_for(raw, expected=expected)
    return gep1.parse_synthetic_raw_bundle(raw, manifest), source_hash


def controlled_source(row, keys, text):
    source = {}
    for key in keys:
        if key == "raw_text":
            source[key] = text
        else:
            source[key] = row[key]
    return source


class RawPayloadTests(unittest.TestCase):
    def test_raw_bytes_hash_and_attempt_join_are_stable(self):
        with open(LOW_VALIDITY, "rb") as handle:
            raw = handle.read()
        original = bytes(raw)
        before = hashlib.sha256(raw).hexdigest()
        parsed, source_hash = parse_bundle(raw, expected=5)
        after = hashlib.sha256(raw).hexdigest()
        self.assertEqual(raw, original)
        self.assertEqual(before, after)
        self.assertEqual(parsed["raw_bytes_sha256_before"], before)
        self.assertEqual(parsed["raw_bytes_sha256_after"], after)
        self.assertTrue(parsed["raw_bytes_unchanged"])
        self.assertEqual(parsed["source_artifact_sha256"], source_hash)
        self.assertEqual(parsed["attempt_count"], 5)
        self.assertEqual(parsed["source_attempt_ids"], [row["record_id"] for row in parsed["derived_rows"]])
        self.assertTrue(all(row["source_artifact_sha256"] == source_hash for row in parsed["derived_rows"]))
        self.assertTrue(all("attempt_id" not in row for row in parsed["derived_rows"]))
        self.assertFalse(parsed["production_file_reader"])
        self.assertFalse(parsed["replenishment_applied"])

    def test_missing_duplicate_and_extra_attempt_ids_fail_closed(self):
        with open(LOW_VALIDITY, "rb") as handle:
            raw = handle.read()
        parsed, _source_hash = parse_bundle(raw, expected=5)
        rows = parsed["derived_rows"]
        ids = parsed["source_attempt_ids"]
        self.assertTrue(gep1.assert_derived_attempt_identity(ids, rows))
        with self.assertRaises(gep1.GeneratorEvalContractError) as missing:
            gep1.assert_derived_attempt_identity(ids, rows[:-1])
        self.assertEqual(missing.exception.code, "attempt_id_missing")
        duplicated = rows + [copy.deepcopy(rows[0])]
        with self.assertRaises(gep1.GeneratorEvalContractError) as duplicate:
            gep1.assert_derived_attempt_identity(ids, duplicated)
        self.assertEqual(duplicate.exception.code, "attempt_id_duplicated")
        extra = copy.deepcopy(rows)
        extra.append(copy.deepcopy(rows[0]))
        extra[-1]["record_id"] = "low-extra"
        with self.assertRaises(gep1.GeneratorEvalContractError) as extra_error:
            gep1.assert_derived_attempt_identity(ids, extra)
        self.assertEqual(extra_error.exception.code, "attempt_id_extra")
        renumbered = []
        for index, row in enumerate(rows):
            changed = copy.deepcopy(row)
            changed["record_id"] = str(index)
            renumbered.append(changed)
        with self.assertRaises(gep1.GeneratorEvalContractError) as renumbered_error:
            gep1.assert_derived_attempt_identity(ids, renumbered)
        self.assertIn(renumbered_error.exception.code, ("attempt_id_missing", "attempt_id_extra", "attempt_id_reordered"))

    def test_low_validity_outcomes_are_retained_without_replenishment(self):
        with open(LOW_VALIDITY, "rb") as handle:
            raw = handle.read()
        parsed, _source_hash = parse_bundle(raw, expected=5)
        rows = parsed["derived_rows"]
        by_id = {row["record_id"]: row for row in rows}
        self.assertEqual(len(rows), 5)
        self.assertEqual(by_id["low-empty"]["parse_outcome"], "empty_output")
        self.assertEqual(by_id["low-empty"]["failure_reason"], "empty_output")
        self.assertIsNone(by_id["low-empty"]["sequence"])
        self.assertEqual(by_id["low-unparseable"]["parse_outcome"], "unparseable_output")
        self.assertEqual(by_id["low-unparseable"]["failure_reason"], "unparseable_output")
        self.assertIsNone(by_id["low-unparseable"]["sequence"])
        self.assertFalse(by_id["low-unparseable"]["parsed_status"])
        self.assertEqual(by_id["low-non-acgu"]["parse_outcome"], "parsed_non_acgu")
        self.assertEqual(by_id["low-non-acgu"]["failure_reason"], "parsed_non_acgu")
        self.assertEqual(by_id["low-non-acgu"]["sequence"], "ACGT")
        self.assertTrue(by_id["low-non-acgu"]["parsed_status"])
        self.assertFalse(by_id["low-non-acgu"]["alphabet_valid"])
        self.assertEqual(by_id["low-dup-1"]["parse_outcome"], "valid_canonical_sequence")
        self.assertIsNone(by_id["low-dup-1"]["failure_reason"])
        self.assertTrue(gep1._row_is_valid(by_id["low-dup-1"]))
        self.assertTrue(gep1._row_is_valid(by_id["low-dup-2"]))
        accounting = gep1._accounting(rows, "B2")
        self.assertEqual(accounting["attempted"], 5)
        self.assertEqual(accounting["valid_acgu"], 2)
        self.assertLess(accounting["valid_acgu"], accounting["attempted"])
        self.assertEqual(accounting["failure_reason_counts"]["empty_output"], 1)
        self.assertEqual(accounting["failure_reason_counts"]["unparseable_output"], 1)
        self.assertEqual(accounting["failure_reason_counts"]["parsed_non_acgu"], 1)
        self.assertEqual(accounting["failure_reason_counts"]["non_sequence_output"], 0)
        self.assertEqual(accounting["valid_canonical_sequence_count"], 2)
        self.assertFalse(accounting["failure_reason_counts_emit_sequence_strings"])
        shareable = json.dumps(accounting, sort_keys=True)
        self.assertNotIn("ACGT", shareable)
        self.assertNotIn("ACGU", shareable)
        manifest, _source_hash = manifest_for(raw, expected=8)
        with self.assertRaises(gep1.GeneratorEvalContractError) as mismatch:
            gep1.parse_synthetic_raw_bundle(raw, manifest)
        self.assertEqual(mismatch.exception.code, "expected_attempt_count_mismatch")

    def test_three_identical_valid_attempts_keep_primary_multiplicity(self):
        attempts = [
            {"record_id": "trip-%d" % index, "raw_text": "ACGU", "empirical_null_seed": 3, "requested_length": 4}
            for index in (1, 2, 3)
        ]
        raw = raw_bundle("B2", attempts)
        parsed, _source_hash = parse_bundle(raw, expected=3)
        accounting = analysis.schedule_independent_output_accounting(parsed["derived_rows"], ["UUUU"])
        block = accounting["output_accounting"]
        self.assertEqual(block["valid_outputs"], 3)
        self.assertEqual(block["unique_valid_outputs"], 1)
        self.assertEqual(block["duplicates"], 2)
        self.assertEqual(block["duplicate_excess"], 2)
        self.assertEqual(block["largest_duplicate_multiplicity"], 3)
        self.assertEqual(block["multiplicity_histogram"], [{"multiplicity": 3, "distinct_valid_sequences": 1}])
        self.assertFalse(block["multiplicity_histogram_emits_sequence_strings"])
        self.assertFalse(block["multiplicity_histogram_emits_sequence_to_count_mapping"])
        sequences = ["ACGU", "ACGU", "ACGU"]
        before = copy.deepcopy(block)
        sensitivity = analysis.unique_only_sensitivity(sequences)
        self.assertEqual(block, before)
        self.assertEqual(sensitivity["primary_valid_attempt_count"], 3)
        self.assertEqual(sensitivity["unique_valid_count"], 1)
        self.assertFalse(sensitivity["replaces_primary_result"])
        self.assertEqual(analysis.multiplicity_histogram(sequences), [{"multiplicity": 3, "distinct_valid_sequences": 1}])


class BiologicalValidityTests(unittest.TestCase):
    def test_b1_b2_d1_and_b0_share_validity_and_b0_length_stays_unavailable(self):
        valid_text = "ACGUACGU"
        invalid_text = "ACGTACGT"
        self.assertTrue(gep1.biological_validity(valid_text))
        self.assertFalse(gep1.biological_validity(invalid_text))
        b1 = controlled_source(helpers.b1_row("shared-b1", valid_text), gep1.SYNTHETIC_B1_SOURCE_KEYS, valid_text)
        d1 = controlled_source(helpers.d1_row("shared-d1", valid_text, 7), gep1.SYNTHETIC_D1_SOURCE_KEYS, valid_text)
        b2 = {"record_id": "shared-b2", "raw_text": valid_text, "empirical_null_seed": 3, "requested_length": len(valid_text)}
        parsed = {}
        for condition, attempts in (("B1", [b1]), ("D1", [d1]), ("B2", [b2])):
            raw = raw_bundle(condition, attempts)
            result, source_hash = parse_bundle(raw, expected=1)
            parsed[condition] = result["derived_rows"][0]
            self.assertEqual(parsed[condition]["source_artifact_sha256"], source_hash)
            self.assertEqual(parsed[condition]["record_id"], attempts[0]["record_id"])
        self.assertEqual(
            [gep1.biological_validity(parsed[condition]["sequence"]) for condition in ("B1", "B2", "D1")],
            [True, True, True],
        )
        invalid_b2 = dict(b2)
        invalid_b2["record_id"] = "shared-b2-invalid"
        invalid_b2["raw_text"] = invalid_text
        invalid_rows = {
            "B1": controlled_source(helpers.b1_row("shared-b1-invalid", valid_text), gep1.SYNTHETIC_B1_SOURCE_KEYS, invalid_text),
            "D1": controlled_source(helpers.d1_row("shared-d1-invalid", valid_text, 7), gep1.SYNTHETIC_D1_SOURCE_KEYS, invalid_text),
            "B2": invalid_b2,
        }
        flags = []
        for condition, attempt in invalid_rows.items():
            raw = raw_bundle(condition, [attempt])
            result, _source_hash = parse_bundle(raw, expected=1)
            flags.append(gep1.biological_validity(result["derived_rows"][0]["sequence"]))
        self.assertEqual(flags, [False, False, False])
        source_hash = "ab" * 32
        adapted = gep1.adapt_synthetic_b0_source(
            {
                "record_id": "synthetic-b0-1",
                "historical_text": valid_text,
                "historical_generation_seed": 11,
                "historical_batch_index": 0,
                "nominal_max_seq_len": 37,
                "checkpoint_id": "synthetic-b0-adapter",
            },
            source_hash,
        )
        self.assertEqual(adapted["record_id"], "synthetic-b0-1")
        self.assertEqual(adapted["source_artifact_sha256"], source_hash)
        self.assertIsNone(adapted["requested_length"])
        self.assertIsNone(adapted["requested_target_length"])
        self.assertEqual(adapted["nominal_max_seq_len"], 37)
        self.assertEqual(adapted["observed_length"], len(valid_text))
        self.assertNotEqual(adapted["observed_length"], adapted["nominal_max_seq_len"])
        self.assertTrue(gep1.biological_validity(adapted["sequence"]))
        self.assertEqual(gep1.biological_validity(adapted["sequence"]), gep1.biological_validity(parsed["B1"]["sequence"]))
        validated = gep1.validate_records([adapted])
        self.assertFalse(gep1.matched_schedule_structure(validated)["b0_in_matched_b1_d1_controlled_comparison"])
        with self.assertRaises(gep1.GeneratorEvalContractError) as claim:
            gep1.assess_claim([adapted], {"kind": "matched_b1_d1_controlled_comparison", "include_conditions": ["B0", "B1", "D1"]})
        self.assertEqual(claim.exception.code, "b0_forbidden_in_matched_b1_d1_controlled_comparison")
        inferred = {
            "record_id": "synthetic-b0-2",
            "historical_text": valid_text,
            "historical_generation_seed": 11,
            "historical_batch_index": 0,
            "nominal_max_seq_len": 37,
            "checkpoint_id": "synthetic-b0-adapter",
            "cleaned_length": len(valid_text),
        }
        with self.assertRaises(gep1.GeneratorEvalContractError) as extra_field:
            gep1.adapt_synthetic_b0_source(inferred, source_hash)
        self.assertEqual(extra_field.exception.code, "b0_source_invalid")


class ProvenanceTypeTests(unittest.TestCase):
    def test_strict_provenance_types_fail_before_attempt_arithmetic(self):
        raw = raw_bundle(
            "B2",
            [{"record_id": "typed-1", "raw_text": "ACGU", "empirical_null_seed": 3, "requested_length": 4}],
        )
        manifest, _source_hash = manifest_for(raw, expected=1)
        replacements = (
            ("source_byte_size", True),
            ("source_byte_size", 1.0),
            ("source_artifact_id", ["synthetic-container"]),
            ("source_artifact_sha256", None),
            ("replenishment_prohibited", True),
            ("expected_attempt_count", None),
            ("expected_attempt_count", 1.5),
            ("expected_derived_ledger_sha256", {"sha256": "ab" * 32}),
            ("derived_ledger_sha256", "ab" * 32),
        )
        for key, value in replacements:
            mutated = copy.deepcopy(manifest)
            mutated[key] = value
            with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
                gep1.parse_synthetic_raw_bundle(raw, mutated)
            self.assertEqual(caught.exception.code, "provenance_type_invalid")
        mutated = copy.deepcopy(manifest)
        mutated["source_artifact_sha256"] = "G" * 64
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_provenance_manifest(mutated)
        self.assertEqual(caught.exception.code, "provenance_sha256_invalid")
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.parse_synthetic_raw_bundle("/tmp/production-m8.json", manifest)
        self.assertEqual(caught.exception.code, "raw_payload_type_invalid")
        bad_pools = (
            {"pooling_policy": "equal_training_seed_mixture", "policy_verified": True, "participating_training_seeds": [True, 19]},
            {"pooling_policy": "equal_training_seed_mixture", "policy_verified": True, "participating_training_seeds": [7.0, 19]},
            {"pooling_policy": "equal_training_seed_mixture", "policy_verified": True, "participating_training_seeds": {"seed": 7}},
            {"pooling_policy": "equal_training_seed_mixture", "policy_verified": True, "participating_training_seeds": [None]},
        )
        for pooling in bad_pools:
            with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
                gep1.validate_d1_pooling_provenance(pooling)
            self.assertEqual(caught.exception.code, "pooling_type_invalid")


class D1PoolingTests(unittest.TestCase):
    def _rows(self):
        rows = []
        for index in range(4):
            if index == 0:
                row = helpers.d1_row("seed-a-%d" % index, "GGGG", 7, invocation_index=1, batch_position=index, attempt=index)
            else:
                row = helpers.d1_row("seed-a-%d" % index, "GGGG", 7, invocation_index=1, batch_position=index, attempt=index)
                helpers.mark_unparsed(row)
            rows.append(row)
        for index in range(4):
            if index == 0:
                row = helpers.d1_row("seed-b-%d" % index, "AAAA", 19, invocation_index=1, batch_position=index, attempt=index)
                helpers.mark_invalid_nonempty(row, "ACGT")
            else:
                row = helpers.d1_row("seed-b-%d" % index, "AAAA", 19, invocation_index=1, batch_position=index, attempt=index)
            rows.append(row)
        return rows

    def test_equal_seed_mixture_uses_supplied_labels_and_leaves_raw_counts_observed(self):
        rows = gep1.validate_records(self._rows())
        pooling = {
            "pooling_policy": "equal_training_seed_mixture",
            "policy_verified": True,
            "participating_training_seeds": [7, 19],
        }
        validated = gep1.validate_d1_pooling_provenance(pooling)
        report = analysis.valid_conditional_equal_seed_mixture(rows, validated)
        per_seed = {item["training_seed"]: item for item in report["per_seed"]}
        self.assertEqual(per_seed[7]["raw_attempts"], 4)
        self.assertEqual(per_seed[19]["raw_attempts"], 4)
        self.assertEqual(per_seed[7]["valid_outputs"], 1)
        self.assertEqual(per_seed[19]["valid_outputs"], 3)
        self.assertNotEqual(per_seed[7]["valid_outputs"], per_seed[19]["valid_outputs"])
        self.assertEqual(report["raw_attempts"], 8)
        self.assertEqual(report["weights"], [0.5, 0.5])
        self.assertEqual(per_seed[7]["weight"], 0.5)
        self.assertEqual(per_seed[19]["weight"], 0.5)
        self.assertEqual(report["equal_mixture"]["pooled_gc_fraction"], 0.5)
        self.assertEqual(report["concatenated_valid_conditional"]["pooled_gc_fraction"], 0.25)
        self.assertNotEqual(
            report["equal_mixture"]["pooled_gc_fraction"],
            report["concatenated_valid_conditional"]["pooled_gc_fraction"],
        )
        self.assertEqual(report["global_valid_outputs"], 4)
        self.assertEqual(report["global_duplicate_excess"], 2)
        self.assertFalse(report["equal_seed_weighting_applied_to_raw_counts"])
        self.assertFalse(report["equal_seed_weighting_applied_to_global_duplicates"])
        self.assertFalse(report["is_confidence_interval"])
        self.assertFalse(report["is_evidence_from_many_training_replicates"])
        self.assertTrue(report["generated_rows_are_nested_monte_carlo_samples"])
        self.assertFalse(report["generated_rows_are_model_replicates"])
        self.assertEqual(report["raw_attempts_aggregation_basis"], "actual attempt accounting")
        self.assertEqual(report["actual_attempt_level_validity_rate"], 0.5)
        self.assertEqual(report["equal_seed_mean_validity_rate"], 0.5)
        self.assertEqual(per_seed[7]["validity_rate"], 0.25)
        self.assertEqual(per_seed[19]["validity_rate"], 0.75)
        self.assertEqual(
            report["equal_mixture"]["aggregation_basis"],
            "equal-training-seed valid-conditional mixture",
        )
        self.assertFalse(report["concatenated_valid_conditional"]["used_as_pooled_headline"])
        self.assertFalse(report["concatenated_valid_conditional"]["used_as_directional_consistency"])
        unverified = gep1.validate_d1_pooling_provenance(
            {
                "pooling_policy": "unverified",
                "policy_verified": False,
                "participating_training_seeds": [7, 19],
            }
        )
        unavailable = analysis.valid_conditional_equal_seed_mixture(rows, unverified)
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(unavailable["unavailable_reason"], "pooling_policy_not_verified")
        self.assertIsNone(unavailable["equal_mixture"]["pooled_gc_fraction"])
        self.assertEqual(unavailable["raw_attempts"], 8)
        self.assertIsNone(unavailable["weights"])
        self.assertEqual(unavailable["per_seed"][0]["raw_attempts"], 4)
        self.assertIsNone(unavailable["equal_seed_mean_validity_rate"])

    def test_equal_seed_direction_disagrees_with_concatenated_rows(self):
        rows = [helpers.d1_row("near-valid", "AAAAAAAA", 7, invocation_index=1, batch_position=0, attempt=0)]
        for index in range(1, 4):
            invalid = helpers.d1_row("near-invalid-%d" % index, "AAAAAAAA", 7, invocation_index=1, batch_position=index, attempt=index)
            helpers.mark_unparsed(invalid)
            rows.append(invalid)
        for index in range(3):
            rows.append(helpers.d1_row("far-%d" % index, "CCCCCCCC", 19, invocation_index=1, batch_position=index, attempt=index))
        b1 = helpers.b1_row("dir-b1", "AAAACCCC", invocation_index=1, batch_position=0, attempt=0)
        reference_rows = [helpers.reference("ref-a", "AAAAAAAA")]
        provenance = {
            "pooling_policy": "equal_training_seed_mixture",
            "policy_verified": True,
            "participating_training_seeds": [7, 19],
        }
        document = helpers.envelope(
            rows + [b1, helpers.b0_row("dir-b0"), helpers.b2_row("dir-b2")],
            ["UUUUUUUU"],
            reference_rows,
            d1_pooling_provenance=provenance,
        )
        report = analysis.analyse(document)
        consistency = report["b1_d1_directional_consistency"]
        self.assertEqual(consistency["label"], "d1_closer_or_tied")
        self.assertEqual(consistency["aggregation_basis"], "equal-training-seed valid-conditional mixture")
        self.assertFalse(consistency["uses_unlabelled_concatenated_d1_fallback"])
        self.assertEqual(report["conditions"]["D1"]["pooled_gc_aggregation_basis"], "equal-training-seed valid-conditional mixture")
        pooling = report["d1_valid_conditional_pooling"]
        per_seed = {item["training_seed"]: item for item in pooling["per_seed"]}
        self.assertEqual(per_seed[7]["raw_attempts"], 4)
        self.assertEqual(per_seed[7]["valid_outputs"], 1)
        self.assertEqual(per_seed[7]["validity_rate"], 0.25)
        self.assertEqual(per_seed[19]["raw_attempts"], 3)
        self.assertEqual(per_seed[19]["valid_outputs"], 3)
        self.assertEqual(per_seed[19]["validity_rate"], 1.0)
        self.assertEqual(pooling["actual_attempt_level_validity_rate"], 4 / 7)
        self.assertEqual(pooling["equal_seed_mean_validity_rate"], (0.25 + 1.0) / 2)
        self.assertNotEqual(pooling["actual_attempt_level_validity_rate"], pooling["equal_seed_mean_validity_rate"])
        self.assertFalse(pooling["equal_seed_weighting_applied_to_raw_counts"])
        self.assertFalse(pooling["equal_seed_weighting_applied_to_global_duplicates"])
        reference = ["AAAAAAAA"]
        concatenated = ["AAAAAAAA", "CCCCCCCC", "CCCCCCCC", "CCCCCCCC"]
        b1_sequences = ["AAAACCCC"]
        concatenated_headlines = {
            "nearest_reference_normalized_edit_distance.median": analysis.nearest_reference_normalized_edit_distance(concatenated, reference)["median"],
            "nucleotide_total_variation_to_reference": analysis.nucleotide_total_variation_to_reference(concatenated, reference)["value"],
            "dinucleotide_total_variation_to_reference": analysis.dinucleotide_total_variation_to_reference(concatenated, reference)["value"],
        }
        b1_headlines = {
            "nearest_reference_normalized_edit_distance.median": analysis.nearest_reference_normalized_edit_distance(b1_sequences, reference)["median"],
            "nucleotide_total_variation_to_reference": analysis.nucleotide_total_variation_to_reference(b1_sequences, reference)["value"],
            "dinucleotide_total_variation_to_reference": analysis.dinucleotide_total_variation_to_reference(b1_sequences, reference)["value"],
        }
        concatenated_label = analysis.directional_consistency(b1_headlines, concatenated_headlines)["label"]
        self.assertEqual(concatenated_label, "d1_farther_or_tied")
        self.assertNotEqual(consistency["label"], concatenated_label)
        self.assertNotEqual(
            report["conditions"]["D1"]["closeness"]["nearest_reference_normalized_edit_distance"]["median"],
            concatenated_headlines["nearest_reference_normalized_edit_distance.median"],
        )
        absent = helpers.envelope(
            rows + [b1, helpers.b0_row("dir-b0-absent"), helpers.b2_row("dir-b2-absent")],
            ["UUUUUUUU"],
            reference_rows,
        )
        unavailable = analysis.analyse(absent)
        self.assertEqual(unavailable["b1_d1_directional_consistency"]["label"], "not_applicable")
        self.assertEqual(unavailable["b1_d1_directional_consistency"]["unavailable_reason"], "pooling_policy_not_verified")
        self.assertFalse(unavailable["b1_d1_directional_consistency"]["uses_unlabelled_concatenated_d1_fallback"])
        self.assertIsNone(unavailable["conditions"]["D1"]["pooled_gc_fraction"])
        self.assertEqual(unavailable["conditions"]["D1"]["accounting"]["attempted"], 7)
        self.assertEqual(unavailable["d1_by_training_seed"]["d1_training_seed_count"], 2)
        empty_seed = []
        for index in range(2):
            invalid = helpers.d1_row("empty-seed-%d" % index, "AAAAAAAA", 19, invocation_index=2, batch_position=index, attempt=index)
            helpers.mark_unparsed(invalid)
            empty_seed.append(invalid)
        kept = [row for row in rows if row["training_seed"] == 7]
        dropped = helpers.envelope(
            kept + empty_seed + [b1, helpers.b0_row("dir-b0-drop"), helpers.b2_row("dir-b2-drop")],
            ["UUUUUUUU"],
            reference_rows,
            d1_pooling_provenance=provenance,
        )
        withheld = analysis.analyse(dropped)
        self.assertIsNone(withheld["conditions"]["D1"]["pooled_gc_fraction"])
        self.assertEqual(
            withheld["conditions"]["D1"]["pooled_gc_undefined_reason"],
            "undefined_valid_conditional_metric_for_at_least_one_training_seed",
        )
        self.assertEqual(withheld["b1_d1_directional_consistency"]["label"], "not_applicable")
        self.assertFalse(withheld["b1_d1_directional_consistency"]["uses_unlabelled_concatenated_d1_fallback"])
        self.assertEqual(withheld["d1_valid_conditional_pooling"]["per_seed"][1]["raw_attempts"], 2)

    def test_exact_half_weight_inclusive_median_stays_on_the_lower_value(self):
        lower_value = 0
        higher_value = 1
        observations = [(lower_value, Fraction(1, 12), "a-%d" % index) for index in range(6)]
        observations.append((higher_value, Fraction(1, 2), "b-0"))
        direct = analysis.weighted_empirical_quantiles(observations)
        reversed_direct = analysis.weighted_empirical_quantiles(list(reversed(observations)))
        self.assertEqual(direct, reversed_direct)
        self.assertEqual(sum((weight for _value, weight, _attempt in observations[:6]), Fraction(0)), Fraction(1, 2))
        self.assertEqual(direct["total_weight_exact"], {"numerator": 1, "denominator": 1})
        self.assertEqual(direct["median"], lower_value)
        self.assertEqual(direct["probabilities_exact"]["p25"], {"numerator": 1, "denominator": 4})
        self.assertEqual(direct["probabilities_exact"]["median"], {"numerator": 1, "denominator": 2})
        self.assertEqual(direct["probabilities_exact"]["p75"], {"numerator": 3, "denominator": 4})
        self.assertFalse(direct["float_boundary_fallback"])
        self.assertEqual(direct["quantile_rule"], "inclusive_cumulative_weight_exact_v2")
        self.assertNotIn("Fraction", json.dumps(direct))

        def selected(probability):
            running = Fraction(0)
            for value, weight, _attempt in sorted(observations, key=lambda item: (item[0], item[2])):
                running += weight
                if running >= probability:
                    return value
            raise AssertionError("exact probability was not reached")

        self.assertEqual(direct["p25"], selected(Fraction(1, 4)))
        self.assertEqual(direct["median"], selected(Fraction(1, 2)))
        self.assertEqual(direct["p75"], selected(Fraction(3, 4)))
        self.assertEqual(direct["p25"], lower_value)
        self.assertEqual(direct["p75"], higher_value)
        float_running = 0.0
        for _index in range(6):
            float_running += 1.0 / 12.0
        self.assertLess(float_running, 0.5)

        seed_a = 7
        seed_b = 19
        rows = [
            helpers.d1_row("low-%02d" % index, "AAAAAAAA", seed_a, invocation_index=1, batch_position=index, attempt=index)
            for index in range(6)
        ]
        rows.append(helpers.d1_row("high-00", "CCCCCCCC", seed_b, invocation_index=1, batch_position=6, attempt=6))
        b1 = helpers.b1_row("boundary-b1", "AAAACCCC", invocation_index=1, batch_position=0, attempt=0)
        reference_rows = [helpers.reference("ref-boundary", "AAAAAAAA")]
        provenance = {
            "pooling_policy": "equal_training_seed_mixture",
            "policy_verified": True,
            "participating_training_seeds": [seed_a, seed_b],
        }

        def document_for(d1_rows):
            return helpers.envelope(
                list(d1_rows) + [b1, helpers.b0_row("boundary-b0"), helpers.b2_row("boundary-b2")],
                ["UUUUUUUU"],
                reference_rows,
                d1_pooling_provenance=provenance,
            )

        report = analysis.analyse(document_for(rows))
        reversed_report = analysis.analyse(document_for(reversed(rows)))
        pooling = report["d1_valid_conditional_pooling"]
        per_seed = {item["training_seed"]: item for item in pooling["per_seed"]}
        quantiles = report["conditions"]["D1"]["closeness"]["nearest_reference_normalized_edit_distance"]["quantiles"]
        reversed_quantiles = reversed_report["conditions"]["D1"]["closeness"]["nearest_reference_normalized_edit_distance"]["quantiles"]
        consistency = report["b1_d1_directional_consistency"]
        distance_key = "nearest_reference_normalized_edit_distance.median"
        self.assertEqual(per_seed[seed_a]["valid_outputs"], 6)
        self.assertEqual(per_seed[seed_b]["valid_outputs"], 1)
        self.assertEqual(per_seed[seed_a]["collective_weight_exact"], {"numerator": 1, "denominator": 2})
        self.assertEqual(per_seed[seed_b]["collective_weight_exact"], {"numerator": 1, "denominator": 2})
        self.assertEqual(quantiles["total_weight_exact"], {"numerator": 1, "denominator": 1})
        self.assertEqual(quantiles["median"], direct["median"])
        self.assertEqual(quantiles["p25"], direct["p25"])
        self.assertEqual(quantiles["p75"], direct["p75"])
        self.assertEqual(quantiles, reversed_quantiles)
        self.assertEqual(consistency, reversed_report["b1_d1_directional_consistency"])
        self.assertEqual(report["conditions"]["D1"]["closeness"]["headlines"][distance_key], quantiles["median"])
        self.assertEqual(
            consistency["differences"][distance_key]["d1_minus_b1"],
            quantiles["median"] - report["conditions"]["B1"]["closeness"]["headlines"][distance_key],
        )
        self.assertEqual(consistency["differences"][distance_key]["relation"], "d1_closer")
        self.assertEqual(consistency["d1_headline_source"], "equal_training_seed_mixture")
        self.assertEqual(consistency["aggregation_basis"], "equal-training-seed valid-conditional mixture")
        self.assertFalse(consistency["uses_unlabelled_concatenated_d1_fallback"])
        self.assertFalse(quantiles["float_boundary_fallback"])
        self.assertFalse(pooling["concatenated_valid_conditional"]["used_as_pooled_headline"])
        self.assertFalse(pooling["concatenated_valid_conditional"]["used_as_directional_consistency"])
        self.assertEqual(report["schema_version"], "generator-eval-analysis-gep2-r5")
        spec = gep1.load_metric_spec()
        self.assertEqual(spec["schema_version"], "generator-eval-metric-spec-gep2-draft-r4")
        self.assertEqual(spec["d1_valid_conditional_pooling"]["weighted_quantile_rule"], analysis.WEIGHTED_QUANTILE_RULE)


class ParserFailureTests(unittest.TestCase):
    def test_non_sequence_payloads_remain_one_row_per_attempt(self):
        payloads = (
            ("adv-null", None, "unparseable_output", None),
            ("adv-empty", "", "empty_output", None),
            ("adv-list", ["ACGU"], "non_sequence_output", None),
            ("adv-dict", {"sequence": "ACGU"}, "non_sequence_output", None),
            ("adv-int", 4, "non_sequence_output", None),
            ("adv-bool", True, "non_sequence_output", None),
            ("adv-nonacgu", "ACGT", "parsed_non_acgu", "ACGT"),
            ("adv-valid", "ACGU", "valid_canonical_sequence", "ACGU"),
        )
        attempts = [
            {
                "record_id": record_id,
                "raw_text": payload,
                "empirical_null_seed": 3,
                "requested_length": 4,
            }
            for record_id, payload, _reason, _sequence in payloads
        ]
        raw = raw_bundle("B2", attempts)
        parsed, source_hash = parse_bundle(raw, expected=len(payloads))
        rows = parsed["derived_rows"]
        self.assertEqual(len(rows), len(payloads))
        self.assertEqual([row["record_id"] for row in rows], [item[0] for item in payloads])
        self.assertEqual(parsed["source_attempt_ids"], [item[0] for item in payloads])
        self.assertEqual(parsed["provenance"]["derived_row_count"], len(payloads))
        self.assertNotIn("derived_ledger_sha256", manifest_for(raw, expected=len(payloads))[0])
        for row, (record_id, _payload, reason, sequence) in zip(rows, payloads):
            self.assertEqual(row["record_id"], record_id)
            self.assertEqual(row["source_artifact_sha256"], source_hash)
            self.assertEqual(row["failure_reason"], None if reason == "valid_canonical_sequence" else reason)
            self.assertEqual(row["parse_outcome"], reason)
            self.assertEqual(row["sequence"], sequence)
        accounting = gep1._accounting(rows, "B2")
        self.assertEqual(accounting["attempted"], 8)
        self.assertEqual(accounting["valid_acgu"], 1)
        self.assertEqual(accounting["failure_reason_counts"]["unparseable_output"], 1)
        self.assertEqual(accounting["failure_reason_counts"]["empty_output"], 1)
        self.assertEqual(accounting["failure_reason_counts"]["non_sequence_output"], 4)
        self.assertEqual(accounting["failure_reason_counts"]["parsed_non_acgu"], 1)
        self.assertEqual(accounting["valid_canonical_sequence_count"], 1)
        shareable = json.dumps(
            {
                "failure_reason_counts": accounting["failure_reason_counts"],
                "provenance": parsed["provenance"],
            },
            sort_keys=True,
        )
        self.assertNotIn("ACGT", shareable)
        self.assertNotIn("ACGU", shareable)
        self.assertIn("non_sequence_output", shareable)
        inconsistent = {key: rows[0][key] for key in gep1.RECORD_KEYS}
        inconsistent["source_artifact_sha256"] = rows[0]["source_artifact_sha256"]
        inconsistent["parse_outcome"] = "valid_canonical_sequence"
        inconsistent["failure_reason"] = "empty_output"
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.validate_records([inconsistent])
        self.assertIn("parser_outcome_inconsistent", [item["code"] for item in caught.exception.errors])


class DerivedProvenanceTests(unittest.TestCase):
    def test_first_parse_does_not_require_a_derived_hash_and_replay_checks_it(self):
        raw = raw_bundle(
            "B2",
            [{"record_id": "replay-1", "raw_text": "ACGU", "empirical_null_seed": 3, "requested_length": 4}],
        )
        manifest, _source_hash = manifest_for(raw, expected=1)
        self.assertNotIn("derived_ledger_sha256", manifest)
        self.assertNotIn("expected_derived_ledger_sha256", manifest)
        first = gep1.parse_synthetic_raw_bundle(raw, manifest)
        digest = first["provenance"]["derived_ledger_sha256"]
        self.assertEqual(first["derived_ledger_sha256"], digest)
        self.assertEqual(first["provenance"]["derived_row_count"], 1)
        self.assertEqual(first["provenance"]["parser_adapter_version"], gep1.SYNTHETIC_PARSER_ADAPTER_VERSION)
        self.assertEqual(first["provenance"]["replenishment_prohibited"], gep1.REPLENISHMENT_PROHIBITED_STATEMENT)
        replay_manifest, _source_hash = manifest_for(raw, expected=1, expected_derived_hash=digest)
        second = gep1.parse_synthetic_raw_bundle(raw, replay_manifest)
        self.assertEqual(second["provenance"]["derived_ledger_sha256"], digest)
        mismatched, _source_hash = manifest_for(raw, expected=1, expected_derived_hash="ab" * 32)
        with self.assertRaises(gep1.GeneratorEvalContractError) as caught:
            gep1.parse_synthetic_raw_bundle(raw, mismatched)
        self.assertEqual(caught.exception.code, "derived_ledger_sha256_mismatch")


class AttemptIdentityScalingTests(unittest.TestCase):
    def test_source_order_is_checked_with_membership_structures(self):
        digest = "ab" * 32
        ids = ["id-%04d" % index for index in range(2000)]
        rows = [{"record_id": record_id, "source_artifact_sha256": digest} for record_id in ids]
        self.assertTrue(gep1.assert_derived_attempt_identity(ids, rows))
        swapped = [dict(row) for row in rows]
        swapped[0], swapped[1] = swapped[1], swapped[0]
        with self.assertRaises(gep1.GeneratorEvalContractError) as reordered:
            gep1.assert_derived_attempt_identity(ids, swapped)
        self.assertEqual(reordered.exception.code, "attempt_id_reordered")
        missing = rows[:-1]
        with self.assertRaises(gep1.GeneratorEvalContractError) as missing_error:
            gep1.assert_derived_attempt_identity(ids, missing)
        self.assertEqual(missing_error.exception.code, "attempt_id_missing")
        first = gep1.biological_validity("ACGU")
        second = gep1.biological_validity("ACGT")
        self.assertTrue(first)
        self.assertFalse(second)
        cached = gep1._MODULE_CACHE["gep1_m4_biological_validity"]
        self.assertIs(gep1._load_module("m4_diagnostic_metrics.py", "gep1_m4_biological_validity"), cached)


class BoundaryTests(unittest.TestCase):
    def test_existing_boundaries_remain_closed(self):
        _metadata, records = gep1.load_synthetic_fixture(gep1.default_fixture_path())
        rows = gep1.validate_records(records)
        structure = gep1.matched_schedule_structure(rows)
        self.assertFalse(structure["production_schedule_wired"])
        self.assertTrue(all(block["is_training_replicate"] is False for block in structure["matched_schedule_blocks"]))
        self.assertTrue(all(row["training_seed"] is None for row in rows if row["condition"] == "B1"))
        changed = []
        for record in records:
            row = copy.deepcopy(record)
            if row["condition"] == "D1" and row["invocation_index"] == 1:
                row["length_schedule_provenance"] = copy.deepcopy(row["length_schedule_provenance"])
                row["length_schedule_provenance"]["generation_seed_base"] = 88010
                row["invocation_seed"] = 88011
                row["generation_seed"] = 88011
            changed.append(row)
        with self.assertRaises(gep1.GeneratorEvalContractError) as schedule:
            gep1.assess_claim(changed, {"kind": "matched_b1_d1_controlled_comparison", "include_conditions": ["B1", "D1"]})
        self.assertEqual(schedule.exception.code, "matched_schedule_incompatible")
        alias = copy.deepcopy(gep1.load_metric_spec())
        alias["metrics"].append(copy.deepcopy(alias["metrics"][-1]))
        alias["metrics"][-1]["metric_id"] = "combined_quality_score"
        with self.assertRaises(gep1.GeneratorEvalContractError) as combined:
            gep1.validate_metric_spec(alias, require_draft=False)
        self.assertEqual(combined.exception.code, "unknown_metric_alias")
        for role in ("REF", "VALIDATION", "TRAIN", "EVAL"):
            with self.assertRaises(gep1.GeneratorEvalContractError):
                gep1.evaluate_eval_gate(role)
        with self.assertRaises(gep1.GeneratorEvalContractError) as filename:
            gep1.load_synthetic_fixture(os.path.join(gep1.fixture_root(), "eval.csv"))
        self.assertEqual(filename.exception.code, "filename_guard")
        with self.assertRaises(analysis.AnalysisContractError):
            analysis.analyse({"fixture_role": "SYNTHETIC", "eval_path": "eval.csv"})
        item = next(entry for entry in gep1.load_metric_spec()["blocking_items"] if entry["id"] == "viennarna_production_settings_not_pinned")
        self.assertEqual(item["status"], "resolved")
        self.assertIn("RNA.fold(sequence)", item["statement"])
        self.assertIn("ViennaRNA 2.7.0", item["statement"])
        self.assertNotIn("37C", item["statement"])
        report = analysis.analyse(helpers.default_document())
        self.assertFalse(report["viennarna_called"])
        self.assertEqual(report["d1_valid_conditional_pooling"]["status"], "unavailable")
        folded = analysis._structure_from_sequences(["ACGUACGU"], lambda sequence: ("(" * len(sequence), -3.0 * len(sequence)))
        self.assertEqual(folded["mfe"]["median"] if isinstance(folded.get("mfe"), dict) else folded["mfe.median"], -24.0)


if __name__ == "__main__":
    unittest.main()

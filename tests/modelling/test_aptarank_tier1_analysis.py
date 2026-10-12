"""Synthetic ARP-2B joining and accounting tests.

No EVAL, REF, VALIDATION, TRAIN, production pool, or checkpoint is opened.
Sequences stay inside the synthetic fixtures.
"""

from __future__ import annotations

import ast
import copy
import csv
import hashlib
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Context, Decimal, localcontext
from fractions import Fraction

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_module():
    path = os.path.join(ROOT, "scripts/modelling/aptarank_tier1_analysis.py")
    spec = importlib.util.spec_from_file_location("aptarank_tier1_analysis", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


arp2 = load_module()

SEQUENCES = (
    "AAAACCCCGGGGUUUU",
    "ACGUACGUACGUACGU",
    "GGGGUUUUAAAACCCC",
    "UUUUGGGGCCCCAAAA",
)


def codes(error):
    return [item["code"] for item in error.errors]


def bundled():
    return arp2.load_bundled_parts()


def empty_parts():
    return arp2.load_bundled_parts(arp2.EMPTY_FIXTURES)


def analyze(parts, **kwargs):
    return arp2.analyze_tier1(
        parts["private_key"],
        parts["candidate_upload"],
        parts["shortlist_export"],
        parts["failure_accounting"],
        **kwargs,
    )


def csv_table(payload):
    rows = list(csv.reader(io.StringIO(payload.decode("utf-8"), newline="")))
    return rows[0], rows[1:]


def csv_bytes(header, data):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(data)
    return buffer.getvalue().encode("utf-8")


def key_document(parts):
    return json.loads(parts["private_key"].decode("utf-8"))


def failure_document(parts):
    return json.loads(parts["failure_accounting"].decode("utf-8"))


def diagnostic(report, candidate_id):
    matches = [
        item
        for item in report["synthetic_candidate_diagnostics"]
        if item["candidate_id"] == candidate_id
    ]
    if len(matches) != 1:
        raise AssertionError(candidate_id)
    return matches[0]


def assert_no_sequences(testcase, payload):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    for sequence in SEQUENCES:
        testcase.assertNotIn(sequence, text)


class SpecContractTests(unittest.TestCase):
    def test_shipped_spec_is_draft_and_blocked(self):
        spec, spec_bytes = arp2.load_spec()
        self.assertEqual(spec["package_id"], "ARP-2B")
        self.assertEqual(spec["schema_version"], "aptarank-tier1-arp2b-draft-r2")
        self.assertEqual(spec["status"], "draft")
        self.assertIs(spec["deployment_verified"], False)
        self.assertEqual(spec["eval_access"], "locked")
        self.assertEqual(spec["scorer_owner"], "deployed AptaRank UI")
        self.assertIs(spec["scientific_result"], False)
        self.assertIs(spec["full_tier1_statistical_analysis"], False)
        self.assertIs(spec["aggregate_tier1_tier2_score"], False)
        self.assertIs(spec["provisional_camera_ready_formula_adopted"], False)
        self.assertEqual(spec["implemented"], list(arp2.IMPLEMENTED))
        self.assertEqual(spec["blocked_outputs"], [dict(item) for item in arp2.BLOCKED_OUTPUTS])
        self.assertEqual(spec["unresolved_ids"], ["U%d" % index for index in range(1, 39)])
        self.assertEqual(
            [item["id"] for item in spec["unresolved_register"]],
            spec["unresolved_ids"],
        )
        for item in spec["unresolved_register"]:
            self.assertEqual(item["status"], "unresolved")
            self.assertIsNone(item["value"])
            self.assertTrue(item["note"].strip())
        constants = spec["production_design_constants"]
        self.assertEqual(constants["ref_calibration_cores"], 113)
        self.assertEqual(constants["eval_cores"], 154)
        self.assertEqual(constants["blinded_input_rows_before_technical_rejection"], 308)
        self.assertEqual(constants["eval_clusters_before_technical_rejection"], 79)
        self.assertIs(constants["enforce_on_synthetic_fixtures"], False)
        self.assertEqual(constants["fixture_count_label"], "synthetic")
        self.assertIs(spec["interpretation_boundary"]["binding_interpretation"], False)
        self.assertIs(spec["interpretation_boundary"]["affinity_interpretation"], False)
        self.assertIs(spec["interpretation_boundary"]["selectivity_interpretation"], False)
        self.assertIs(spec["interpretation_boundary"]["uniform_controls_are_synthetic_floor"], True)
        self.assertIs(spec["arp2a_reconciliation"]["modified_by_arp2b"], False)
        self.assertIs(spec["arp1_dependency"]["modified_by_arp2b"], False)
        for flag in arp2.SCORING_BOUNDARY_FLAGS:
            self.assertIs(spec["scoring_boundary"][flag], False)
        with open(os.path.join(ROOT, arp2.GOVERNING_PLAN_RELATIVE), "rb") as handle:
            plan_hash = hashlib.sha256(handle.read()).hexdigest()
        with open(os.path.join(ROOT, arp2.ARP2A_RELATIVE), "rb") as handle:
            arp2a_hash = hashlib.sha256(handle.read()).hexdigest()
        with open(os.path.join(ROOT, "scripts/modelling/aptarank_tier1_analysis.py"), "rb") as handle:
            module_hash = hashlib.sha256(handle.read()).hexdigest()
        with open(arp2.spec_path(), "rb") as handle:
            stored_spec_hash = hashlib.sha256(handle.read()).hexdigest()
        with open(os.path.join(ROOT, spec["arp1_dependency"]["module_path"]), "rb") as handle:
            arp1_module_hash = hashlib.sha256(handle.read()).hexdigest()
        with open(os.path.join(ROOT, spec["arp1_dependency"]["spec_path"]), "rb") as handle:
            arp1_spec_hash = hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(plan_hash, spec["governing_plan"]["sha256"])
        self.assertEqual(arp2a_hash, spec["arp2a_reconciliation"]["sha256"])
        self.assertEqual(module_hash, spec["analysis_module"]["sha256"])
        self.assertEqual(arp1_module_hash, spec["arp1_dependency"]["module_sha256"])
        self.assertEqual(arp1_spec_hash, spec["arp1_dependency"]["spec_sha256"])
        self.assertEqual(
            spec["arp1_dependency"]["module_sha256"],
            "eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01",
        )
        self.assertEqual(
            spec["arp1_dependency"]["spec_sha256"],
            "3c9ac25c74939026f778b7eb8e627c4785734e992a8401e79691c375b565b96b",
        )
        self.assertEqual(hashlib.sha256(spec_bytes).hexdigest(), stored_spec_hash)

    def test_spec_rejects_verification_unlock_and_formula_adoption(self):
        spec, _spec_bytes = arp2.load_spec()
        verified = copy.deepcopy(spec)
        verified["deployment_verified"] = True
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.validate_spec_document(verified)
        self.assertEqual(caught.exception.code, "deployment_verified_refused")
        unlocked = copy.deepcopy(spec)
        unlocked["eval_access"] = "unlocked"
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.validate_spec_document(unlocked)
        self.assertEqual(caught.exception.code, "eval_access_refused")
        adopted = copy.deepcopy(spec)
        adopted["provisional_camera_ready_formula_adopted"] = True
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.validate_spec_document(adopted)
        self.assertEqual(caught.exception.code, "provisional_formula_refused")
        combined = copy.deepcopy(spec)
        combined["aggregate_tier1_tier2_score"] = True
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.validate_spec_document(combined)
        self.assertEqual(caught.exception.code, "combined_score_refused")
        closed = copy.deepcopy(spec)
        closed["unresolved_register"][29]["value"] = "selected"
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.validate_spec_document(closed)
        self.assertEqual(caught.exception.code, "spec_invalid")


class PrivateKeyTests(unittest.TestCase):
    def test_invalid_private_key_types_fail_before_set_sort_or_lookup(self):
        class Explosive:
            def __hash__(self):
                raise AssertionError("candidate id was hashed")

            def __eq__(self, other):
                raise AssertionError("candidate id was compared")

        calls = {"set": 0, "sorted": 0}
        builtin_set = set
        builtin_sorted = sorted

        def spy_set(*args, **kwargs):
            calls["set"] += 1
            return builtin_set(*args, **kwargs)

        def spy_sorted(*args, **kwargs):
            calls["sorted"] += 1
            return builtin_sorted(*args, **kwargs)

        document = {
            "fixture_role": "synthetic_private_key",
            "count_label": "synthetic",
            "candidates": [
                {
                    "candidate_id": Explosive(),
                    "class_label": "real",
                    "pair_id": "SYN-PAIR-01",
                    "parent_core_id": "SYN-PARENT-01",
                    "cluster_id": "SYN-CLUSTER-01",
                    "length": 16,
                }
            ],
        }
        try:
            arp2.set = spy_set
            arp2.sorted = spy_sorted
            with self.assertRaises(arp2.AptaRankTier1Error) as caught:
                arp2.validate_private_key(document)
            self.assertEqual(caught.exception.code, "invalid_private_key_identifier")
            self.assertEqual(calls, {"set": 0, "sorted": 0})
            for field, value, code in (
                ("length", True, "invalid_private_key_length"),
                ("length", False, "invalid_private_key_length"),
                ("length", 16.0, "invalid_private_key_length"),
                ("length", "16", "invalid_private_key_length"),
                ("length", 0, "invalid_private_key_length"),
                ("length", -4, "invalid_private_key_length"),
                ("candidate_id", None, "invalid_private_key_identifier"),
                ("candidate_id", 4, "invalid_private_key_identifier"),
                ("candidate_id", True, "invalid_private_key_identifier"),
                ("class_label", True, "invalid_private_key_class_label"),
                ("class_label", None, "invalid_private_key_class_label"),
                ("pair_id", {"bad": 1}, "invalid_private_key_identifier"),
            ):
                row = {
                    "candidate_id": "SYN-REAL-01",
                    "class_label": "real",
                    "pair_id": "SYN-PAIR-01",
                    "parent_core_id": "SYN-PARENT-01",
                    "cluster_id": "SYN-CLUSTER-01",
                    "length": 16,
                }
                row[field] = value
                probe = {
                    "fixture_role": "synthetic_private_key",
                    "count_label": "synthetic",
                    "candidates": [row],
                }
                calls["set"] = 0
                calls["sorted"] = 0
                with self.assertRaises(arp2.AptaRankTier1Error) as caught:
                    arp2.validate_private_key(probe)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(calls["set"], 0)
                self.assertEqual(calls["sorted"], 0)
                self.assertNotIsInstance(caught.exception.__cause__, TypeError)
        finally:
            del arp2.set
            del arp2.sorted

    def test_pair_composition_and_agreement_fail(self):
        base = key_document(bundled())
        cases = (
            ("pair_class_composition", 1, "real"),
            ("pair_class_composition", 0, "uniform_control"),
        )
        for code, index, label in cases:
            document = copy.deepcopy(base)
            document["candidates"][index]["class_label"] = label
            with self.assertRaises(arp2.AptaRankTier1Error) as caught:
                arp2.validate_private_key(document)
            self.assertEqual(caught.exception.code, code)
        for field, value in (
            ("parent_core_id", "SYN-PARENT-99"),
            ("cluster_id", "SYN-CLUSTER-99"),
            ("length", 15),
        ):
            document = copy.deepcopy(base)
            document["candidates"][1][field] = value
            with self.assertRaises(arp2.AptaRankTier1Error) as caught:
                arp2.validate_private_key(document)
            self.assertEqual(caught.exception.code, "pair_field_inconsistency")
            self.assertIn(field, caught.exception.detail)
        three = copy.deepcopy(base)
        extra = copy.deepcopy(three["candidates"][0])
        extra["candidate_id"] = "SYN-REAL-99"
        extra["class_label"] = "real"
        three["candidates"].append(extra)
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.validate_private_key(three)
        self.assertEqual(caught.exception.code, "pair_cardinality")
        split = copy.deepcopy(base)
        split["candidates"][1]["pair_id"] = "SYN-PAIR-99"
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.validate_private_key(split)
        self.assertEqual(caught.exception.code, "pair_cardinality")
        self.assertIn("pair_cardinality", codes(caught.exception))


class JoinAndAccountingTests(unittest.TestCase):
    def test_permuting_export_rows_leaves_the_report_unchanged(self):
        parts = bundled()
        original = analyze(parts)
        header, data = csv_table(parts["shortlist_export"])
        for permuted in (list(reversed(data)), data[1:] + data[:1], [data[2], data[0], data[1]]):
            updated = dict(parts)
            updated["shortlist_export"] = csv_bytes(header, permuted)
            self.assertEqual(analyze(updated), original)

    def test_row_position_join_would_fail_the_fixture(self):
        parts = bundled()
        document = key_document(parts)
        _header, data = csv_table(parts["shortlist_export"])
        key_ids = [row["candidate_id"] for row in document["candidates"]]
        export_ids = [row[1] for row in data]
        self.assertNotEqual(len(key_ids), len(export_ids))
        self.assertNotEqual(key_ids[0], export_ids[0])
        self.assertEqual(data[0][2], "8.00")
        report = analyze(parts)
        self.assertIs(report["join_uses_row_position"], False)
        self.assertEqual(report["join_key"], "candidate_id")
        self.assertEqual(report["arithmetic_means"]["real"]["numerator"], "2.50")
        self.assertNotEqual(report["arithmetic_means"]["real"]["value"], "8.00")
        self.assertEqual(diagnostic(report, "SYN-REAL-01")["score_token"], "2.50")
        self.assertEqual(diagnostic(report, "SYN-CTRL-01")["score_token"], "8.00")

    def test_complete_pairs_record_count_and_real_minus_control_direction(self):
        parts = bundled()
        header, data = csv_table(parts["shortlist_export"])
        data.append(["4", "SYN-CTRL-02", "4.00", "not evaluated", "fail", "16", SEQUENCES[3]])
        failures = failure_document(parts)
        failures["failures"] = []
        updated = dict(parts)
        updated["shortlist_export"] = csv_bytes(header, list(reversed(data)))
        updated["failure_accounting"] = failures
        report = analyze(updated)
        self.assertEqual(report["complete_pair_count"], 2)
        self.assertEqual(report["incomplete_pair_count"], 0)
        self.assertEqual(report["paired_difference_count"], 2)
        self.assertEqual(
            report["paired_difference_directions"],
            [
                {"pair_id": "SYN-PAIR-01", "direction": "real_minus_control"},
                {"pair_id": "SYN-PAIR-02", "direction": "real_minus_control"},
            ],
        )
        self.assertEqual(report["paired_difference_method_status"], "eligible_count_only_functional_blocked")
        self.assertIsNone(report["blocked_outputs"]["aggregate_paired_effect_functional_and_ci"]["value"])
        self.assertEqual(report["evaluable_counts_by_class"]["real"], 2)
        self.assertEqual(report["evaluable_counts_by_class"]["uniform_control"], 2)
        self.assertEqual(diagnostic(report, "SYN-REAL-02")["score_token"], "0")
        self.assertEqual(report["arithmetic_means"]["uniform_control"]["value"], "6.00")
        self.assertEqual(report["arithmetic_means"]["uniform_control"]["denominator"], 2)

    def test_technical_failure_is_not_zero_and_exported_zero_stays_evaluable(self):
        report = analyze(bundled())
        failed = diagnostic(report, "SYN-CTRL-02")
        zero = diagnostic(report, "SYN-REAL-02")
        self.assertEqual(failed["disposition"], "technical_failure")
        self.assertIsNone(failed["score_token"])
        self.assertIs(failed["evaluable"], False)
        self.assertIs(failed["numeric_zero_retained"], False)
        self.assertIs(failed["missing_result_stored_as_zero"], False)
        self.assertTrue(failed["failure_reason"].strip())
        self.assertEqual(zero["disposition"], "exported")
        self.assertEqual(zero["score_token"], "0")
        self.assertIs(zero["evaluable"], True)
        self.assertIs(zero["numeric_zero_retained"], True)
        self.assertIs(report["missing_results_are_zero"], False)
        self.assertEqual(report["rows_imputed_as_zero"], 0)
        self.assertEqual(report["technical_failure_counts_by_class"], {"real": 0, "uniform_control": 1})
        self.assertEqual(report["evaluable_counts_by_class"], {"real": 2, "uniform_control": 1})
        self.assertEqual(report["arithmetic_means"]["uniform_control"]["value"], "8.00")
        self.assertEqual(report["arithmetic_means"]["uniform_control"]["denominator"], 1)
        self.assertEqual(report["arithmetic_means"]["uniform_control"]["numerator"], "8.00")
        self.assertEqual(report["arithmetic_means"]["real"]["value"], "1.25")
        self.assertEqual(report["arithmetic_means"]["real"]["numerator"], "2.50")
        self.assertEqual(report["arithmetic_means"]["real"]["denominator"], 2)
        self.assertEqual(diagnostic(report, "SYN-REAL-01")["score_token"], "2.50")

    def test_surviving_member_stays_in_group_mean_and_pair_is_excluded(self):
        report = analyze(bundled())
        self.assertEqual(report["input_candidate_count"], 4)
        self.assertEqual(report["input_pair_count"], 2)
        self.assertEqual(report["cluster_count_before_technical_rejection"], 2)
        self.assertEqual(report["input_counts_by_class"], {"real": 2, "uniform_control": 2})
        self.assertEqual(report["complete_pair_count"], 1)
        self.assertEqual(report["incomplete_pair_count"], 1)
        self.assertEqual(report["paired_difference_count"], 1)
        self.assertEqual(report["paired_difference_directions"], [{"pair_id": "SYN-PAIR-01", "direction": "real_minus_control"}])
        self.assertEqual(len(report["incomplete_pairs"]), 1)
        incomplete = report["incomplete_pairs"][0]
        self.assertEqual(incomplete["pair_id"], "SYN-PAIR-02")
        self.assertIs(incomplete["excluded_from_paired_differences"], True)
        self.assertIs(incomplete["surviving_member_remains_in_group_mean"], True)
        self.assertIn("SYN-CTRL-02", incomplete["reason"])
        self.assertIn("unpaired group", incomplete["reason"])
        self.assertIn("excluded from paired differences", incomplete["reason"])
        self.assertEqual(report["arithmetic_means"]["real"]["denominator"], 2)
        self.assertEqual(report["fixture_count_label"], "synthetic")
        self.assertIs(report["production_design_constants"]["applied_to_this_report"], False)
        self.assertNotEqual(report["input_candidate_count"], 308)
        self.assertNotEqual(report["cluster_count_before_technical_rejection"], 79)

    def test_shared_cluster_is_counted_once_before_rejection(self):
        parts = bundled()
        document = key_document(parts)
        for row in document["candidates"]:
            row["cluster_id"] = "SYN-CLUSTER-01"
        updated = dict(parts)
        updated["private_key"] = document
        report = analyze(updated)
        self.assertEqual(report["cluster_count_before_technical_rejection"], 1)
        self.assertEqual(report["input_pair_count"], 2)
        self.assertEqual(report["technical_failure_counts_by_class"]["uniform_control"], 1)

    def test_missing_without_explicit_failure_fails_closed(self):
        parts = bundled()
        failures = failure_document(parts)
        failures["failures"] = []
        updated = dict(parts)
        updated["failure_accounting"] = failures
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            analyze(updated)
        self.assertEqual(caught.exception.code, "missing_candidate_id")
        self.assertIn("SYN-CTRL-02", caught.exception.detail)

    def test_export_and_failure_for_the_same_candidate_fails_closed(self):
        parts = bundled()
        failures = failure_document(parts)
        failures["failures"].append(
            {"candidate_id": "SYN-REAL-01", "reason": "synthetic duplicate accounting that must fail closed"}
        )
        updated = dict(parts)
        updated["failure_accounting"] = failures
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            analyze(updated)
        self.assertIn("candidate_accounted_twice", codes(caught.exception))

    def test_duplicate_unexpected_and_malformed_ids_fail_closed(self):
        parts = bundled()
        header, data = csv_table(parts["shortlist_export"])
        duplicate = dict(parts)
        copied = list(data[0])
        copied[0] = "9"
        duplicate["shortlist_export"] = csv_bytes(header, data + [copied])
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            analyze(duplicate)
        self.assertIn("duplicate_exported_id", codes(caught.exception))
        unexpected = dict(parts)
        unexpected["shortlist_export"] = csv_bytes(
            header,
            data + [["9", "SYN-EXTRA-01", "1.00", "not evaluated", "pass", "16", SEQUENCES[0]]],
        )
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            analyze(unexpected)
        self.assertIn("unexpected_candidate_id", codes(caught.exception))
        malformed = dict(parts)
        broken = [list(data[0])]
        broken[0][1] = "bad id"
        malformed["shortlist_export"] = csv_bytes(header, broken + data[1:])
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            analyze(malformed)
        self.assertIn("empty_id", codes(caught.exception))
        key = key_document(parts)
        key["candidates"][0]["candidate_id"] = "bad id"
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.validate_private_key(key)
        self.assertEqual(caught.exception.code, "invalid_private_key_identifier")
        duplicated_key = key_document(parts)
        duplicated_key["candidates"][2]["candidate_id"] = "SYN-REAL-01"
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.validate_private_key(duplicated_key)
        self.assertEqual(caught.exception.code, "duplicate_private_key_candidate_id")
        extra_failure = failure_document(parts)
        extra_failure["failures"].append(
            {"candidate_id": "SYN-EXTRA-01", "reason": "synthetic unexpected failure"}
        )
        unexpected_failure = dict(parts)
        unexpected_failure["failure_accounting"] = extra_failure
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            analyze(unexpected_failure)
        self.assertIn("unexpected_failure_id", codes(caught.exception))

    def test_nonfinite_score_sequence_change_and_blank_reason_fail_closed(self):
        parts = bundled()
        header, data = csv_table(parts["shortlist_export"])
        nonfinite = dict(parts)
        broken = [list(row) for row in data]
        broken[0][2] = "nan"
        nonfinite["shortlist_export"] = csv_bytes(header, broken)
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            analyze(nonfinite)
        self.assertIn("nonfinite_aptamer_likeness", codes(caught.exception))
        changed = dict(parts)
        rewritten = [list(row) for row in data]
        rewritten[2][6] = "ACGUACGUACGUACGG"
        changed["shortlist_export"] = csv_bytes(header, rewritten)
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            analyze(changed)
        self.assertIn("sequence_changed", codes(caught.exception))
        assert_no_sequences(self, str(caught.exception))
        self.assertNotIn("ACGUACGUACGUACGG", str(caught.exception))
        failures = failure_document(parts)
        failures["failures"][0]["reason"] = "  "
        blank = dict(parts)
        blank["failure_accounting"] = failures
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            analyze(blank)
        self.assertIn("missing_failure_reason", codes(caught.exception))

    def test_empty_synthetic_input_returns_zero_counts_and_undefined_reasons(self):
        report = analyze(empty_parts())
        self.assertEqual(report["input_candidate_count"], 0)
        self.assertEqual(report["input_pair_count"], 0)
        self.assertEqual(report["cluster_count_before_technical_rejection"], 0)
        self.assertEqual(report["input_counts_by_class"], {"real": 0, "uniform_control": 0})
        self.assertEqual(report["evaluable_counts_by_class"], {"real": 0, "uniform_control": 0})
        self.assertEqual(report["technical_failure_counts_by_class"], {"real": 0, "uniform_control": 0})
        self.assertEqual(report["complete_pair_count"], 0)
        self.assertEqual(report["incomplete_pair_count"], 0)
        self.assertEqual(report["incomplete_pairs"], [])
        self.assertEqual(report["paired_difference_count"], 0)
        self.assertEqual(report["paired_difference_directions"], [])
        self.assertEqual(report["rows_imputed_as_zero"], 0)
        for label in ("real", "uniform_control"):
            mean = report["arithmetic_means"][label]
            self.assertIsNone(mean["value"])
            self.assertEqual(mean["denominator"], 0)
            self.assertIs(mean["undefined"], True)
            self.assertIn("undefined", mean["reason"])
        self.assertIsNone(report["blocked_outputs"]["median_and_iqr"]["value"])
        self.assertNotEqual(report["blocked_outputs"]["median_and_iqr"]["value"], 0)
        self.assertEqual(report["fixture_count_label"], "synthetic")

    def test_no_report_contains_a_sequence_string(self):
        reports = [analyze(bundled()), analyze(empty_parts())]
        parts = bundled()
        header, data = csv_table(parts["shortlist_export"])
        data.append(["4", "SYN-CTRL-02", "4.00", "not evaluated", "fail", "16", SEQUENCES[3]])
        failures = failure_document(parts)
        failures["failures"] = []
        complete = dict(parts)
        complete["shortlist_export"] = csv_bytes(header, data)
        complete["failure_accounting"] = failures
        reports.append(analyze(complete))
        rendered = arp2.render_report(reports[0])
        for report in reports:
            assert_no_sequences(self, report)
            assert_no_sequences(self, arp2.render_report(report))
        assert_no_sequences(self, rendered)
        self.assertIs(reports[0]["candidate_level_biological_table"], False)


class BlockedOutputTests(unittest.TestCase):
    def test_statistics_remain_blocked(self):
        report = analyze(bundled())
        expected = {
            "median_and_iqr": ["U30"],
            "aggregate_paired_effect_functional_and_ci": ["U31"],
            "auroc": ["U29", "U32"],
            "shuffle_pass_rates_or_interpretation": ["U19", "U21", "U33"],
            "secondary_paired_test": ["U34"],
            "bootstrap_intervals": ["U35", "U36", "U37", "U38"],
            "component_table_without_verified_deployment": ["U%d" % index for index in range(1, 12)],
            "local_scorer_recomputation": ["U%d" % index for index in range(1, 22)],
            "uniform_control_generation": ["U22", "U23", "U24"],
            "opaque_production_ids": ["U25", "U26"],
            "full_ranking_schema": ["U27", "U28", "U29"],
        }
        self.assertEqual(list(report["blocked_outputs"]), list(expected))
        for name, blocking_ids in expected.items():
            item = report["blocked_outputs"][name]
            self.assertIsNone(item["value"])
            self.assertEqual(item["blocking_ids"], blocking_ids)
            self.assertTrue(item["reason"].strip())
        self.assertIs(report["full_tier1_statistical_analysis"], False)
        self.assertIs(report["deployment_verified"], False)
        self.assertEqual(report["eval_access"], "locked")
        for flag in report["local_recomputations"].values():
            self.assertIs(flag, False)

    def test_recomputation_requests_fail_explicitly(self):
        parts = bundled()
        for name in arp2.RECOMPUTATION_REQUESTS:
            with self.assertRaises(arp2.AptaRankTier1Error) as caught:
                arp2.refuse_local_recomputation(name)
            self.assertEqual(caught.exception.code, "recomputation_refused")
            self.assertIn("U1", caught.exception.detail)
            self.assertIn("U21", caught.exception.detail)
            with self.assertRaises(arp2.AptaRankTier1Error) as caught:
                analyze(parts, recompute=name)
            self.assertEqual(caught.exception.code, "recomputation_refused")
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.refuse_local_recomputation("not_a_component")
        self.assertEqual(caught.exception.code, "recomputation_refused")
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.refuse_blocked_operation("generate_uniform_controls")
        self.assertEqual(caught.exception.code, "control_generation_refused")
        self.assertIn("U22", caught.exception.detail)
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.refuse_blocked_operation("create_opaque_production_ids")
        self.assertEqual(caught.exception.code, "opaque_production_id_refused")
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.refuse_blocked_operation("full_ranking_schema")
        self.assertEqual(caught.exception.code, "full_ranking_schema_refused")

    def test_no_combined_tier_score_exists(self):
        spec, _spec_bytes = arp2.load_spec()
        report = analyze(bundled())
        self.assertIs(spec["aggregate_tier1_tier2_score"], False)
        self.assertIs(report["aggregate_tier1_tier2_score"], False)
        self.assertIs(spec["interpretation_boundary"]["aggregate_tier1_tier2_score"], False)

        def walk(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if "tier" in key:
                        self.assertNotIn(type(child), (int, float))
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(spec)
        walk(report)
        self.assertNotIn("combined_tier1_tier2_score", report)
        self.assertNotIn("combined_tier1_tier2_score", spec)

    def test_analysis_module_does_not_import_generator_metrics(self):
        path = os.path.join(ROOT, "scripts/modelling/aptarank_tier1_analysis.py")
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
                imported.extend(alias.name for alias in node.names)
        for name in imported:
            self.assertNotIn("generator_eval", name)
            self.assertNotIn("m6_diagnostic", name)
            self.assertNotIn("s6_profile", name)
        for forbidden in ("mfe_per_nt", "pooled_gc_fraction", "percentile_bundle", "wilcoxon"):
            self.assertNotIn(forbidden, source)


class CommandLineTests(unittest.TestCase):
    def run_main(self, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = arp2.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_rejects_paths_roles_and_eval_unlock(self):
        for args in (
            ["eval.csv"],
            ["EVAL"],
            ["REF"],
            ["VALIDATION"],
            ["TRAIN"],
            ["--unlock-eval"],
            ["--eval-unlock"],
            ["production_pool.csv"],
            ["checkpoint.pt"],
            ["tests/modelling/fixtures/aptarank_arp2/synthetic_private_key.json"],
            ["--help"],
        ):
            code, stdout, stderr = self.run_main(args)
            self.assertEqual(code, 2, args)
            self.assertEqual(stdout, "")
            self.assertIn("arp2b_cli_rejected", stderr)
            self.assertIn("EVAL unlock", stderr)
            assert_no_sequences(self, stderr)
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.load_fixture_bytes("eval.csv")
        self.assertEqual(caught.exception.code, "fixture_name_refused")
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.analyze_tier1("EVAL", b"", b"", b"")
        self.assertEqual(caught.exception.code, "path_refused")

    def test_no_argument_run_uses_only_synthetic_fixtures(self):
        previous = os.environ.get("APTARANK_EVAL_UNLOCK")
        os.environ["APTARANK_EVAL_UNLOCK"] = "1"
        try:
            code, stdout, stderr = self.run_main([])
        finally:
            if previous is None:
                os.environ.pop("APTARANK_EVAL_UNLOCK", None)
            else:
                os.environ["APTARANK_EVAL_UNLOCK"] = previous
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn(arp2.SYNTHETIC_ONLY_STATEMENT, stdout)
        self.assertIn("used only synthetic fixtures", stdout)
        self.assertIn("loaded no EVAL, REF, VALIDATION, TRAIN, production pool or checkpoint", stdout)
        self.assertIn("spec_status: draft", stdout)
        self.assertIn("schema_version: aptarank-tier1-arp2b-draft-r2", stdout)
        self.assertIn("deployment_verified: false", stdout)
        spec, spec_bytes = arp2.load_spec()
        revision = arp2.demonstration_revision(spec, spec_bytes)
        self.assertIn("analysis_module_sha256: " + revision["analysis_module_sha256"], stdout)
        self.assertIn("analysis_spec_sha256: " + revision["analysis_spec_sha256"], stdout)
        self.assertIn("governing_plan_sha256: " + revision["governing_plan_sha256"], stdout)
        self.assertIn("arp2a_sha256: " + revision["arp2a_sha256"], stdout)
        self.assertIn("arp1_module_sha256: " + revision["arp1_module_sha256"], stdout)
        self.assertIn("arp1_spec_sha256: " + revision["arp1_spec_sha256"], stdout)
        self.assertEqual(revision["analysis_spec_sha256"], hashlib.sha256(spec_bytes).hexdigest())
        self.assertIn("eval_access: locked", stdout)
        self.assertIn("fixture_count_label: synthetic", stdout)
        self.assertIn("input_candidate_count: 4", stdout)
        self.assertIn("paired_difference_count: 1", stdout)
        self.assertIn("median_and_iqr: null U30", stdout)
        self.assertIn("aggregate_tier1_tier2_score: false", stdout)
        self.assertIn("full_tier1_statistical_analysis: false", stdout)
        assert_no_sequences(self, stdout)


def replace_upload_sequence(parts, candidate_id, sequence):
    header, data = csv_table(parts["candidate_upload"])
    rows = []
    for row in data:
        copied = list(row)
        if copied[0] == candidate_id:
            copied[1] = sequence
        rows.append(copied)
    updated = dict(parts)
    updated["candidate_upload"] = csv_bytes(header, rows)
    return updated


def replace_export_sequence(parts, candidate_id, sequence):
    header, data = csv_table(parts["shortlist_export"])
    rows = []
    for row in data:
        copied = list(row)
        if copied[1] == candidate_id:
            copied[6] = sequence
        rows.append(copied)
    updated = dict(parts)
    updated["shortlist_export"] = csv_bytes(header, rows)
    return updated


def replace_export_score(parts, candidate_id, score):
    header, data = csv_table(parts["shortlist_export"])
    rows = []
    for row in data:
        copied = list(row)
        if copied[1] == candidate_id:
            copied[2] = score
        rows.append(copied)
    updated = dict(parts)
    updated["shortlist_export"] = csv_bytes(header, rows)
    return updated


class ArithmeticMeanTests(unittest.TestCase):
    def test_one_third_is_defined_exactly(self):
        with localcontext(Context(prec=6)):
            result = arp2._arithmetic_mean(["1", "0", "0"])
        self.assertEqual(result["exact_numerator"], "1")
        self.assertEqual(result["exact_denominator"], "3")
        self.assertEqual("%s/%s" % (result["exact_numerator"], result["exact_denominator"]), "1/3")
        self.assertIs(result["undefined"], False)
        self.assertIsNone(result["reason"])
        self.assertIsNone(result["value"])
        self.assertEqual(result["score_tokens"], ["1", "0", "0"])
        self.assertEqual(result["denominator"], 3)
        approximation = result["decimal_approximation"]
        self.assertEqual(approximation["precision"], arp2.MEAN_APPROXIMATION_PRECISION)
        self.assertEqual(approximation["rounding"], "ROUND_HALF_EVEN")
        self.assertIs(approximation["exact"], False)
        self.assertTrue(approximation["text"].startswith("0.333"))
        self.assertNotIn("undefined", json.dumps(approximation))
        self.assertEqual(Fraction(result["exact_numerator"]) / Fraction(result["exact_denominator"]), Fraction(1, 3))

    def test_high_precision_tokens_keep_the_exact_numerator(self):
        token = "0." + ("1" * 40)
        with localcontext(Context(prec=6)):
            result = arp2._arithmetic_mean([token, "0"])
        self.assertIs(result["undefined"], False)
        self.assertEqual(result["exact_numerator"], "1" * 40)
        self.assertEqual(result["exact_denominator"], "2" + ("0" * 40))
        self.assertEqual(result["score_tokens"], [token, "0"])
        self.assertIsNone(result["decimal_approximation"])
        exact = Fraction(int(result["exact_numerator"]), int(result["exact_denominator"]))
        self.assertEqual(exact, Fraction(Decimal(token)) / 2)
        self.assertEqual(Fraction(Decimal(result["value"])), exact)
        self.assertGreater(len(result["value"].split(".")[1]), 6)

    def test_negative_finite_scores_have_an_exact_mean(self):
        with localcontext(Context(prec=6)):
            result = arp2._arithmetic_mean(["-1.50", "0"])
        self.assertIs(result["undefined"], False)
        self.assertIsNone(result["reason"])
        self.assertEqual(result["exact_numerator"], "-3")
        self.assertEqual(result["exact_denominator"], "4")
        self.assertEqual(result["value"], "-0.75")
        self.assertEqual(result["numerator"], "-1.50")
        self.assertEqual(result["score_tokens"], ["-1.50", "0"])
        updated = replace_export_score(bundled(), "SYN-REAL-01", "-1.50")
        report = analyze(updated)
        mean = report["arithmetic_means"]["real"]
        self.assertIs(mean["undefined"], False)
        self.assertEqual(mean["exact_numerator"], "-3")
        self.assertEqual(mean["exact_denominator"], "4")
        self.assertEqual(mean["value"], "-0.75")
        self.assertEqual(diagnostic(report, "SYN-REAL-01")["score_token"], "-1.50")

    def test_exported_numeric_zero_stays_a_defined_rational(self):
        result = arp2._arithmetic_mean(["0"])
        self.assertIs(result["undefined"], False)
        self.assertEqual(result["exact_numerator"], "0")
        self.assertEqual(result["exact_denominator"], "1")
        self.assertEqual(result["value"], "0")
        self.assertEqual(result["score_tokens"], ["0"])
        self.assertIsNone(result["decimal_approximation"])
        report = analyze(bundled())
        mean = report["arithmetic_means"]["real"]
        self.assertIs(mean["undefined"], False)
        self.assertEqual(mean["value"], "1.25")
        self.assertEqual(mean["numerator"], "2.50")
        self.assertEqual(mean["denominator"], 2)
        self.assertEqual(mean["exact_numerator"], "5")
        self.assertEqual(mean["exact_denominator"], "4")
        self.assertIn("0", mean["score_tokens"])
        self.assertEqual(report["arithmetic_means"]["uniform_control"]["value"], "8.00")
        self.assertEqual(report["arithmetic_means"]["uniform_control"]["exact_numerator"], "8")
        self.assertEqual(report["arithmetic_means"]["uniform_control"]["exact_denominator"], "1")

    def test_empty_input_stays_undefined(self):
        result = arp2._arithmetic_mean([])
        self.assertIsNone(result["value"])
        self.assertIsNone(result["numerator"])
        self.assertIsNone(result["exact_numerator"])
        self.assertIsNone(result["exact_denominator"])
        self.assertEqual(result["denominator"], 0)
        self.assertIs(result["undefined"], True)
        self.assertIn("undefined", result["reason"])
        self.assertEqual(result["score_tokens"], [])
        self.assertIsNone(result["decimal_approximation"])


class ReviewedSpecificationTests(unittest.TestCase):
    def analysis_parts(self):
        parts = bundled()
        return (
            parts["private_key"],
            parts["candidate_upload"],
            parts["shortlist_export"],
            parts["failure_accounting"],
        )

    def test_changed_governing_plan_hash_blocks_analysis(self):
        self.assert_patched_source_blocks(
            arp2.GOVERNING_PLAN_RELATIVE,
            "governing_plan_hash_mismatch",
        )

    def test_changed_arp2a_hash_blocks_analysis(self):
        self.assert_patched_source_blocks(
            arp2.ARP2A_RELATIVE,
            "arp2a_hash_mismatch",
        )

    def test_changed_arp1_dependency_hash_blocks_analysis(self):
        self.assert_patched_source_blocks(
            "scripts/modelling/aptarank_io_preflight.py",
            "arp1_module_hash_mismatch",
        )
        self.assert_patched_source_blocks(
            "config/modelling/aptarank_io_spec.json",
            "arp1_spec_hash_mismatch",
        )

    def assert_patched_source_blocks(self, relative, code):
        original = arp2.arp1.read_bytes
        target = os.path.realpath(os.path.join(ROOT, relative))

        def patched(path):
            payload = original(path)
            if os.path.realpath(path) == target:
                return payload + b"\n"
            return payload

        arp2.arp1.read_bytes = patched
        try:
            with self.assertRaises(arp2.AptaRankTier1Error) as caught:
                analyze(bundled())
            self.assertEqual(caught.exception.code, code)
        finally:
            arp2.arp1.read_bytes = original

    def test_mismatched_specification_bytes_and_object_block_analysis(self):
        spec, spec_bytes = arp2.load_spec()
        injected = copy.deepcopy(spec)
        injected["unresolved_register"][0]["note"] += " mismatched object"
        arp2.validate_spec_document(injected)
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2._analyze_tier1(injected, spec_bytes, *self.analysis_parts())
        self.assertEqual(caught.exception.code, "spec_bytes_mismatch")
        self.assertNotIn("mismatched object", caught.exception.detail)
        payload = json.dumps(injected).encode("utf-8")
        self.assertNotEqual(payload, spec_bytes)
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2._analyze_tier1(injected, payload, *self.analysis_parts())
        self.assertEqual(caught.exception.code, "spec_bytes_mismatch")

    def test_caller_injected_schema_valid_specification_is_refused(self):
        spec, spec_bytes = arp2.load_spec()
        injected = copy.deepcopy(spec)
        injected["unresolved_register"][0]["note"] += " caller injection"
        arp2.validate_spec_document(injected)
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.analyze_tier1(
                *self.analysis_parts(),
                spec=injected,
                spec_bytes=spec_bytes,
            )
        self.assertEqual(caught.exception.code, "spec_injection_refused")
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.analyze_tier1(*self.analysis_parts(), spec=spec, spec_bytes=spec_bytes)
        self.assertEqual(caught.exception.code, "spec_injection_refused")


class ParentCoreAndSequenceTests(unittest.TestCase):
    def test_two_pairs_cannot_share_one_parent_core(self):
        document = key_document(bundled())
        document["candidates"][2]["parent_core_id"] = "SYN-PARENT-01"
        document["candidates"][3]["parent_core_id"] = "SYN-PARENT-01"
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            arp2.validate_private_key(document)
        self.assertEqual(caught.exception.code, "duplicate_parent_core_across_pairs")
        self.assertIn("SYN-PARENT-01", caught.exception.detail)
        assert_no_sequences(self, str(caught.exception))
        for sequence in SEQUENCES:
            self.assertNotIn(sequence, caught.exception.detail)
        parts = dict(bundled())
        parts["private_key"] = document
        with self.assertRaises(arp2.AptaRankTier1Error) as caught:
            analyze(parts)
        self.assertIn("duplicate_parent_core_across_pairs", codes(caught.exception))
        assert_no_sequences(self, str(caught.exception))

    def test_duplicate_sequences_under_different_ids_fail_closed(self):
        cases = (
            ("SYN-REAL-02", "SYN-REAL-01", SEQUENCES[0], True),
            ("SYN-CTRL-02", "SYN-CTRL-01", SEQUENCES[1], False),
            ("SYN-CTRL-01", "SYN-REAL-01", SEQUENCES[0], True),
        )
        for changed_id, source_id, sequence, in_export in cases:
            parts = replace_upload_sequence(bundled(), changed_id, sequence)
            if in_export:
                parts = replace_export_sequence(parts, changed_id, sequence)
            with self.assertRaises(arp2.AptaRankTier1Error) as caught:
                analyze(parts)
            self.assertIn("duplicate_candidate_sequence", codes(caught.exception))
            self.assertIn(changed_id, caught.exception.detail)
            self.assertIn(source_id, caught.exception.detail)
            self.assertNotIn(sequence, str(caught.exception))
            assert_no_sequences(self, str(caught.exception))
            self.assertNotIn(sequence, json.dumps(caught.exception.errors))


if __name__ == "__main__":
    unittest.main()

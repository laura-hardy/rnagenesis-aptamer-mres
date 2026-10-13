"""Synthetic checks for the M9C-2 descriptive REF summary.

Sequences and identities in this module are invented. The tests do not open
REF, EVAL, TRAIN, VALIDATION, a production candidate, a model, or a checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest

import numpy as np

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
PREPARATION = os.path.join(ROOT, "scripts", "data_preparation")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)
if PREPARATION not in sys.path:
    sys.path.insert(0, PREPARATION)

import aptarank_descriptive_ref_summary as summary

CONTRACT_SHA256 = "3a662b960ab3e4a70b7515acdd532d45e93e31e80ff3025922d04f7df9d0fab4"
COMPONENT_NAMES = summary.COMPONENT_NAMES


def _core(serial, length):
    alphabet = "ACGU"
    value = serial + 1
    suffix = ""
    while value:
        value, digit = divmod(value, 4)
        suffix = alphabet[digit] + suffix
    if len(suffix) >= length:
        raise AssertionError("synthetic core suffix does not fit")
    return ("A" * (length - len(suffix))) + suffix


def _row(serial, core):
    return {
        "scientific_identity_id": "synthetic-descriptive-%04d" % serial,
        "sequence_core": core,
        "sequence_core_sha256": hashlib.sha256(core.encode("utf-8")).hexdigest(),
        "partition": "REF",
        "canonical_target_name": "Synthetic descriptive target",
        "pdb_id": "",
    }


def _components(serial, stratum_code):
    base = float(serial + 1) + stratum_code
    return {
        "mfe_norm": base,
        "ensemble_defect": base + 0.25,
        "positional_entropy_mean": base + 0.5,
        "stem_fraction": ((serial % 7) + 1) / 8.0,
        "gc_fraction": ((serial % 5) + 1) / 6.0,
    }


def _population():
    rows = []
    components = {}
    serial = 0
    short_cores = []
    long_cores = []
    for index in range(summary.SHORT_CORES):
        core = _core(index, 30)
        short_cores.append(core)
        rows.append(_row(serial, core))
        components[core] = _components(index, 0.0)
        serial += 1
    for index in range(summary.LONG_CORES):
        core = _core(1000 + index, 80)
        long_cores.append(core)
        rows.append(_row(serial, core))
        components[core] = _components(index, 100.0)
        serial += 1
    for index in range(summary.DUPLICATE_CORE_COLLAPSES):
        rows.append(_row(serial, short_cores[index]))
        serial += 1
    return rows, components, short_cores, long_cores


def _expected(records, name):
    values = np.asarray([record[name] for record in records], dtype=float)
    first, median, third = np.percentile(values, [25.0, 50.0, 75.0], method="linear")
    return {
        "successful_count": int(values.size),
        "error_or_missing_count": 0,
        "mean": float(np.mean(values)),
        "population_standard_deviation": float(np.std(values, ddof=0)),
        "minimum": float(np.min(values)),
        "first_quartile": float(first),
        "median": float(median),
        "third_quartile": float(third),
        "maximum": float(np.max(values)),
    }


class DescriptiveRefSummaryTests(unittest.TestCase):
    def test_contract_pin_and_closed_flags(self):
        path = os.path.join(ROOT, summary.CONTRACT_RELATIVE)
        with open(path, "rb") as handle:
            self.assertEqual(hashlib.sha256(handle.read()).hexdigest(), CONTRACT_SHA256)
        self.assertEqual(summary.CONTRACT_SHA256, CONTRACT_SHA256)
        document = summary.load_pinned_contract()
        self.assertEqual(document["status"], summary.STATUS)
        self.assertFalse(document["m9c_complete"])
        self.assertFalse(document["eval_unlocked"])
        self.assertFalse(document["production_summary_executed"])
        self.assertFalse(document["local_calibration"])
        self.assertFalse(document["governing_plan_modified"])
        self.assertFalse(document["generator_viennarna_pin"]["resolved_in_this_preparation"])
        plan_path = os.path.join(ROOT, summary.PLAN_RELATIVE)
        with open(plan_path, "rb") as handle:
            self.assertEqual(hashlib.sha256(handle.read()).hexdigest(), summary.PLAN_SHA256)

    def test_linear_percentile_and_population_deviation(self):
        record = summary.aggregate_component([1, 2, 3, 4])
        self.assertEqual(record["successful_count"], 4)
        self.assertEqual(record["error_or_missing_count"], 0)
        self.assertEqual(record["mean"], 2.5)
        self.assertAlmostEqual(record["population_standard_deviation"], 5 ** 0.5 / 2)
        self.assertEqual(record["minimum"], 1.0)
        self.assertEqual(record["first_quartile"], 1.75)
        self.assertEqual(record["median"], 2.5)
        self.assertEqual(record["third_quartile"], 3.25)
        self.assertEqual(record["maximum"], 4.0)
        self.assertEqual(record["percentile_convention"], "numpy_percentile_linear")
        self.assertEqual(record["population_standard_deviation_divisor"], "n")

    def test_frozen_gmm_matches_s6_without_refitting(self):
        from adapters.s6_profile import gmm_posterior_assignment

        document = summary.load_pinned_contract()
        gmm = document["length_regime"]
        self.assertFalse(gmm["refit"])
        lengths = list(range(20, 101))
        local = summary.assign_length_regimes(lengths, gmm)
        reviewed = gmm_posterior_assignment(
            lengths,
            {"means": gmm["means"], "variances": gmm["variances"], "weights": gmm["weights"]},
        )
        self.assertTrue(np.array_equal(local, reviewed))
        self.assertEqual(int(summary.assign_length_regimes([30], gmm)[0]), 0)
        self.assertEqual(int(summary.assign_length_regimes([80], gmm)[0]), 1)

    def test_measured_components_follow_the_reviewed_fold(self):
        import RNA

        sequence = "GGGAAACCC"
        measured = summary.measure_sequence(sequence)
        model = RNA.md()
        model.uniq_ML = 1
        compound = RNA.fold_compound(sequence, model)
        dot_bracket, mfe = compound.mfe()
        compound.exp_params_rescale(mfe)
        compound.pf()
        entropy = [float(value) for value in compound.positional_entropy()[1:]]
        self.assertEqual(measured["gc_fraction"], 6 / 9)
        self.assertEqual(measured["mfe_norm"], float(mfe) / 9)
        self.assertEqual(measured["ensemble_defect"], float(compound.ensemble_defect(dot_bracket)))
        self.assertEqual(measured["positional_entropy_mean"], sum(entropy) / 9)
        self.assertEqual(dot_bracket, "(((...)))")
        self.assertEqual(measured["stem_fraction"], 6 / 9)
        self.assertEqual(measured, summary.measure_sequence(sequence))
        self.assertNotIn("sequence", measured)

    def test_summary_uses_first_occurrence_and_required_strata(self):
        rows, components, short_cores, long_cores = _population()
        result = summary.summarize_descriptive_reference(rows, components)
        self.assertEqual(result["source_row_count"], 131)
        self.assertEqual(result["retained_core_count"], 113)
        self.assertEqual(result["duplicate_core_collapses"], 18)
        self.assertEqual(result["regime_counts"], {"short": 65, "long": 48})
        self.assertFalse(result["calibration"])
        self.assertEqual(result["label"], "descriptive_not_aptarank_calibration")
        self.assertEqual(set(result["strata"]), {"all", "short", "long"})
        short_records = [components[core] for core in short_cores]
        long_records = [components[core] for core in long_cores]
        pooled = short_records + long_records
        for name in COMPONENT_NAMES:
            for stratum, records, count in (
                ("all", pooled, 113),
                ("short", short_records, 65),
                ("long", long_records, 48),
            ):
                actual = result["strata"][stratum][name]
                expected = _expected(records, name)
                self.assertEqual(actual["successful_count"], count)
                self.assertEqual(actual["error_or_missing_count"], 0)
                for key, value in expected.items():
                    self.assertEqual(actual[key], value)
                self.assertEqual(actual["percentile_convention"], "numpy_percentile_linear")
        encoded = json.dumps(result)
        for core in short_cores + long_cores:
            self.assertNotIn(core, encoded)
        self.assertNotIn("sequence_core", encoded)
        self.assertNotIn("empirical_cdf", encoded)
        self.assertNotIn("shuffle", encoded)

    def test_count_component_and_path_rejections(self):
        rows, components, short_cores, _long_cores = _population()
        shortened = rows[:-1]
        with self.assertRaises(summary.DescriptiveRefError) as collapsed:
            summary.summarize_descriptive_reference(shortened, components)
        self.assertEqual(collapsed.exception.code, "count_mismatch")

        relabelled = []
        replaced = False
        for row in rows:
            if not replaced and row["sequence_core"] == short_cores[-1]:
                core = _core(4242, 80)
                relabelled.append(_row(9000, core))
                replaced = True
            else:
                relabelled.append(row)
        relabelled_components = dict(components)
        del relabelled_components[short_cores[-1]]
        relabelled_components[_core(4242, 80)] = _components(0, 100.0)
        with self.assertRaises(summary.DescriptiveRefError) as regimes:
            summary.summarize_descriptive_reference(relabelled, relabelled_components)
        self.assertEqual(regimes.exception.code, "count_mismatch")

        non_finite = dict(components)
        non_finite[short_cores[0]] = dict(non_finite[short_cores[0]])
        non_finite[short_cores[0]]["mfe_norm"] = float("nan")
        with self.assertRaises(summary.DescriptiveRefError) as bad_value:
            summary.summarize_descriptive_reference(rows, non_finite)
        self.assertEqual(bad_value.exception.code, "non_finite_component")

        missing = dict(components)
        missing[short_cores[0]] = dict(missing[short_cores[0]])
        del missing[short_cores[0]]["ensemble_defect"]
        with self.assertRaises(summary.DescriptiveRefError) as bad_key:
            summary.summarize_descriptive_reference(rows, missing)
        self.assertEqual(bad_key.exception.code, "missing_component")

        with self.assertRaises(summary.DescriptiveRefError) as path:
            summary.summarize_descriptive_reference(os.path.join(ROOT, "data", "processed", "ref.csv"), components)
        self.assertEqual(path.exception.code, "filesystem_path_refused")
        with self.assertRaises(summary.DescriptiveRefError):
            summary.measure_sequence("data/processed/ref.csv")

    def test_command_checks_pins_without_arguments(self):
        completed = subprocess.run(
            [sys.executable, os.path.join(MODELLING, "aptarank_descriptive_ref_summary.py")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.splitlines(), [summary.STATUS, CONTRACT_SHA256])
        refused = subprocess.run(
            [sys.executable, os.path.join(MODELLING, "aptarank_descriptive_ref_summary.py"), "data/processed/ref.csv"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(refused.returncode, 1)
        self.assertIn("filesystem_path_refused", refused.stderr)


if __name__ == "__main__":
    unittest.main()

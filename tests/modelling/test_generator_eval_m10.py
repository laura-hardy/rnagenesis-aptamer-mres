"""Synthetic tests for the inactive M10 pathway.

These tests do not open EVAL or the biological generated ledgers. The only
repository data they read are the frozen sequence-free M9A summaries and the
code and plan files needed to check hashes.
"""

from __future__ import annotations

import builtins
import copy
import hashlib
import importlib.util
import inspect
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LONG_REFERENCE = "GGGGGGGGCCCCCCCCCCCC"
LONG_D1 = "UUUUUUUUUUUUUUUUUUUU"


def load_module():
    path = os.path.join(ROOT, "scripts/modelling/generator_eval_m10.py")
    spec = importlib.util.spec_from_file_location("generator_eval_m10_synthetic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m10 = load_module()


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def blank(record_id, condition, source):
    row = {key: None for key in m10.PRODUCTION_ROW_FIELDS}
    row["record_id"] = record_id
    row["condition"] = condition
    row["source_artifact_sha256"] = digest(source)
    row["ledger_schema"] = m10.PRODUCTION_LEDGER_SCHEMA
    row["equal_seed_weighting_applied"] = False
    row["requested_biological_length_available"] = False
    row["is_valid_canonical"] = False
    row["valid_sequence_multiplicity"] = None
    row["is_exact_duplicate_within_condition"] = None
    return row


def mark_valid(row, sequence, multiplicity):
    row["outcome"] = "valid_canonical_sequence"
    row["failure_reason"] = None
    row["parsed_sequence"] = sequence
    row["parsed_length"] = len(sequence)
    row["is_valid_canonical"] = True
    row["valid_sequence_multiplicity"] = multiplicity
    row["is_exact_duplicate_within_condition"] = multiplicity > 1
    return row


def mark_empty(row):
    row["outcome"] = "empty_output"
    row["failure_reason"] = "empty_output"
    row["parsed_sequence"] = None
    row["parsed_length"] = None
    return row


def mark_non_acgu(row):
    row["outcome"] = "parsed_non_acgu"
    row["failure_reason"] = "parsed_non_acgu"
    row["parsed_sequence"] = "ACGTACGT"
    row["parsed_length"] = 8
    return row


def controlled(record_id, condition, source, block, seed, generation_seed, master, position, invocation, requested):
    row = blank(record_id, condition, source)
    row["technical_block"] = block
    row["checkpoint_identity"] = "synthetic-checkpoint-" + condition.lower()
    row["d1_training_seed"] = seed
    row["generation_seed"] = generation_seed
    row["master_attempt_index"] = master
    row["within_batch_position"] = position
    row["invocation_index"] = invocation
    row["requested_biological_length"] = requested
    row["requested_biological_length_available"] = True
    row["max_seq_len"] = requested + 1
    return row


def ledgers():
    b1_source = "synthetic-b1"
    d1_source = "synthetic-d1"
    b1 = [
        controlled("b1-a-0", "B1", b1_source, "A", None, 50043, 0, 0, 0, 8),
        controlled("b1-a-1", "B1", b1_source, "A", None, 50043, 1, 1, 0, 8),
        controlled("b1-a-2", "B1", b1_source, "A", None, 50043, 2, 2, 0, 8),
        controlled("b1-b-0", "B1", b1_source, "B", None, 50044, 10, 0, 1, 20),
        controlled("b1-b-1", "B1", b1_source, "B", None, 50044, 11, 1, 1, 20),
        controlled("b1-b-2", "B1", b1_source, "B", None, 50044, 12, 2, 1, 20),
    ]
    d1 = [
        controlled("d1-a-0", "D1", d1_source, "A", 43, 50043, 0, 0, 0, 8),
        controlled("d1-a-1", "D1", d1_source, "A", 43, 50043, 1, 1, 0, 8),
        controlled("d1-a-2", "D1", d1_source, "A", 43, 50043, 2, 2, 0, 8),
        controlled("d1-b-0", "D1", d1_source, "B", 44, 50044, 10, 0, 1, 20),
        controlled("d1-b-1", "D1", d1_source, "B", 44, 50044, 11, 1, 1, 20),
        controlled("d1-b-2", "D1", d1_source, "B", 44, 50044, 12, 2, 1, 20),
    ]
    mark_valid(b1[0], "CCCCCCCC", 2)
    mark_valid(b1[1], "CCCCCCCC", 2)
    mark_non_acgu(b1[2])
    mark_valid(b1[3], LONG_REFERENCE, 3)
    mark_valid(b1[4], LONG_REFERENCE, 3)
    mark_valid(b1[5], LONG_REFERENCE, 3)
    mark_valid(d1[0], "ACGUACGU", 1)
    mark_empty(d1[1])
    mark_empty(d1[2])
    mark_valid(d1[3], LONG_D1, 3)
    mark_valid(d1[4], LONG_D1, 3)
    mark_valid(d1[5], LONG_D1, 3)
    b0_valid = blank("b0-valid", "B0", "synthetic-b0")
    b0_valid["b0_seed"] = 4201
    b0_valid["b0_chunk_id"] = 1
    b0_valid["nominal_max_seq_len"] = 37
    mark_valid(b0_valid, "UUUUAAAA", 1)
    b0_empty = blank("b0-empty", "B0", "synthetic-b0")
    b0_empty["b0_seed"] = 4201
    b0_empty["b0_chunk_id"] = 1
    b0_empty["nominal_max_seq_len"] = 37
    mark_empty(b0_empty)
    b2_valid = blank("b2-valid", "B2", "synthetic-b2")
    b2_valid["empirical_null_seed"] = 7
    b2_valid["sampled_length"] = 8
    b2_valid["attempt_index"] = 0
    mark_valid(b2_valid, "GGGGCCGG", 1)
    b2_empty = blank("b2-empty", "B2", "synthetic-b2")
    b2_empty["empirical_null_seed"] = 7
    b2_empty["sampled_length"] = 8
    b2_empty["attempt_index"] = 1
    mark_empty(b2_empty)
    return {"B0": [b0_valid, b0_empty], "B1": b1, "B2": [b2_valid, b2_empty], "D1": d1}


def synthetic_eval():
    return [
        {
            "role": "synthetic_eval_stand_in",
            "sequence_id": "synthetic-eval-short",
            "sequence_core": "ACGUACGU",
            "cluster_id": "synthetic-cluster-short",
        },
        {
            "role": "synthetic_eval_stand_in",
            "sequence_id": "synthetic-eval-long",
            "sequence_core": LONG_REFERENCE,
            "cluster_id": "synthetic-cluster-long",
        },
    ]


def protected_eval_csv(rows):
    """Build in-memory identity-row bytes. This helper does not open a file."""
    fields = (
        "scientific_identity_id",
        "sequence_id",
        "sequence_core",
        "cluster_id",
        "sequence_length_core",
    )
    lines = [",".join(fields)]
    for row in rows:
        cells = []
        for field in fields:
            value = row.get(field, "")
            cells.append("" if value is None else str(value))
        lines.append(",".join(cells))
    return ("\n".join(lines) + "\n").encode("utf-8")


def identity_row(identity, sequence_id, sequence, cluster, length=""):
    return {
        "scientific_identity_id": identity,
        "sequence_id": sequence_id,
        "sequence_core": sequence,
        "cluster_id": cluster,
        "sequence_length_core": length,
    }


def document():
    return {
        "fixture_role": "SYNTHETIC",
        "reference_role": "synthetic_eval_stand_in",
        "ledgers": ledgers(),
        "synthetic_eval": synthetic_eval(),
    }


def deterministic_fold(calls):
    def fold(sequence):
        calls.append(sequence)
        characters = []
        for index, base in enumerate(sequence):
            if base == "A":
                characters.append(".")
            elif index % 2 == 0:
                characters.append("(")
            else:
                characters.append(")")
        return "".join(characters), -0.2 * sequence.count("G") - 0.1 * len(sequence)

    return fold


def forbidden_keys(value, found):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in m10.FORBIDDEN_REPORT_KEYS:
                found.append(key)
            forbidden_keys(item, found)
    elif isinstance(value, list):
        for item in value:
            forbidden_keys(item, found)


class PathwayTests(unittest.TestCase):
    def test_contract_dispositions_and_frozen_unauthorized_status(self):
        spec = m10.analysis._preflight().load_metric_spec()
        self.assertEqual(spec["freeze_status"], "frozen")
        self.assertTrue(spec["m10_draft_contract"]["labelled_frozen"])
        self.assertTrue(spec["m10_draft_contract"]["labelled_production_ready"])
        self.assertEqual(
            spec["m10_draft_contract"]["implementation_readiness"]["metric_specification"],
            "frozen_and_production_ready",
        )
        self.assertEqual(
            spec["m10_draft_contract"]["implementation_readiness"]["eval_opening"],
            "not_yet_authorized",
        )
        self.assertNotIn("remains draft", spec["m10_draft_contract"]["inactive_pathway_supersession"]["statement"])
        self.assertNotIn("not production-ready", spec["m10_draft_contract"]["inactive_pathway_supersession"]["statement"])
        self.assertEqual(spec["governing_plan"]["path"], "docs/aptarank_full_mres_thesis_evaluation_plan_v3_4.md")
        self.assertEqual(spec["governing_plan"]["version"], "3.4")
        self.assertEqual(spec["governing_plan"]["revision_date"], "17 October 2026")
        with open(os.path.join(ROOT, spec["governing_plan"]["path"]), "rb") as handle:
            plan_hash = hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(spec["governing_plan"]["sha256"], plan_hash)
        historical = spec["historical_m9c_plan"]
        self.assertEqual(historical["path"], "docs/aptarank_full_mres_thesis_evaluation_plan_v3_3.md")
        self.assertEqual(historical["version"], "3.3")
        self.assertEqual(historical["revision_date"], "12 October 2026")
        self.assertEqual(historical["role"], "m9c_frozen_historical")
        with open(os.path.join(ROOT, historical["path"]), "rb") as handle:
            historical_hash = hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(historical["sha256"], historical_hash)
        self.assertEqual(
            {item["id"]: item["m10_disposition"] for item in spec["blocking_items"] if "m10_disposition" in item},
            m10.analysis._preflight().M10_BLOCKING_DISPOSITIONS,
        )
        self.assertFalse(any(item["status"] == "unresolved" for item in spec["blocking_items"]))
        self.assertTrue(
            set(m10.analysis._preflight().M10_BLOCKING_DISPOSITIONS)
            <= {item["id"] for item in spec["blocking_items"] if item["status"] == "resolved"}
        )
        closeness = [metric for metric in spec["metrics"] if metric["scientific_role"] == "closeness"]
        self.assertEqual(
            [metric["reference_role"] for metric in closeness],
            ["authorized_eval_unique_cores"] * 3,
        )
        required = {item["id"]: item["status"] for item in spec["m10_draft_contract"]["required_implementation_work"]}
        for item_id in ("ledger_adapter", "authorized_eval_adapter", "sequence_free_report_writer"):
            self.assertEqual(required[item_id], "required")

    def test_pathway_preserves_rows_pairing_parsing_train_and_structure(self):
        calls = []
        opened = []
        real_open = builtins.open

        def guarded_open(path, *args, **kwargs):
            text = os.fspath(path)
            opened.append(text)
            base = os.path.basename(text)
            if base in {"eval.csv", "ref.csv", "ft_train.csv", "ft_validation.csv", "corpus_final.csv", "corpus_final.txt"}:
                raise AssertionError(text)
            if "derived_attempt_ledger" in base:
                raise AssertionError(text)
            return real_open(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            output_dir = os.path.join(temporary, "m10-synthetic")
            builtins.open = guarded_open
            try:
                report = m10.run_synthetic(
                    document(),
                    output_dir,
                    m10.synthetic_authorization(),
                    deterministic_fold(calls),
                    root=ROOT,
                )
            finally:
                builtins.open = real_open
            self.assertEqual(len(calls), len(set(calls)))
            self.assertEqual(len(calls), report["structure"]["distinct_fold_count"])
            self.assertEqual(
                stat.S_IMODE(os.stat(os.path.join(output_dir, "m10_derived_evidence.json")).st_mode),
                0o600,
            )
            self.assertEqual(
                stat.S_IMODE(os.stat(os.path.join(output_dir, "m10_sequence_free_report.json")).st_mode),
                0o644,
            )
            self.assertIn("CCCCCCCC", calls)
            self.assertEqual(calls.count("CCCCCCCC"), 1)
            b1 = report["accounting"]["B1"]
            self.assertEqual(b1["attempted"], 6)
            self.assertEqual(b1["successfully_parsed_outputs"], 6)
            self.assertEqual(b1["parsed_outputs"]["value"], 6)
            self.assertEqual(b1["parsed_outputs"]["label"], "internal_schema_valid_record_audit")
            self.assertFalse(b1["parsed_outputs"]["thesis_facing"])
            self.assertEqual(b1["valid_acgu"], 5)
            d1_accounting = report["accounting"]["D1"]
            self.assertEqual(d1_accounting["successfully_parsed_outputs"], 4)
            self.assertEqual(d1_accounting["parsed_outputs"]["value"], 6)
            self.assertEqual(d1_accounting["valid_acgu"], 4)
            self.assertEqual(b1["duplicate_excess"], 3)
            self.assertEqual(b1["invalid"], 1)
            self.assertEqual(report["exclusions_and_failures"]["B1"]["parsed_non_acgu"], 1)
            self.assertEqual(report["exclusions_and_failures"]["D1"]["empty_output"], 2)
            blocks = {block["block"]: block for block in report["matched_blocks"]}
            self.assertEqual(set(blocks), {"A", "B"})
            self.assertEqual(blocks["A"]["d1_training_seed"], 43)
            self.assertEqual(blocks["B"]["d1_training_seed"], 44)
            self.assertEqual(blocks["A"]["generation_seeds"], [50043])
            self.assertEqual(blocks["B"]["generation_seeds"], [50044])
            self.assertFalse(blocks["A"]["is_training_replicate"])
            self.assertFalse(blocks["A"]["is_significance_test_unit"])
            adapted = m10.adapt_frozen_ledgers(ledgers())
            self.assertEqual(sum(adapted["row_counts"].values()), 16)
            self.assertTrue(adapted["invalid_rows_retained"])
            self.assertTrue(adapted["duplicate_rows_retained"])
            d1_rows = [row for row in adapted["rows"] if row["condition"] == "D1"]
            reference = ["ACGUACGU", LONG_REFERENCE]
            equal_seed = report["closeness"]["d1_equal_seed"]
            independent = m10._equal_seed_closeness(d1_rows, reference)
            self.assertEqual(
                equal_seed["nearest_reference_normalized_edit_distance"]["value"],
                independent["nearest_reference_normalized_edit_distance"]["value"],
            )
            concatenated = m10.analysis.nearest_reference_normalized_edit_distance(
                m10._valid_sequences(d1_rows),
                reference,
            )
            self.assertNotEqual(
                equal_seed["nearest_reference_normalized_edit_distance"]["value"],
                concatenated["median"],
            )
            self.assertFalse(equal_seed["equal_seed_pooled_novelty_invented"])
            seed_43 = report["structure"]["by_d1_training_seed"]["43"]["mfe_per_nt"]["median"]
            seed_44 = report["structure"]["by_d1_training_seed"]["44"]["mfe_per_nt"]["median"]
            self.assertNotEqual(seed_43, seed_44)
            self.assertFalse(report["structure"]["equal_seed_pooled"])
            self.assertFalse(report["structure"]["structure_distance_defined"])
            exact = m10.load_allowlisted_train_summaries(ROOT)["exact"]["document"]
            self.assertEqual(
                report["frozen_m9a_train"]["exact"]["per_d1_training_seed"]["43"],
                exact["d1"]["seed_43_valid_conditional_row_rate"],
            )
            self.assertEqual(
                report["frozen_m9a_train"]["nearest"]["per_d1_training_seed"]["44"]["valid_row_count"],
                15000,
            )
            self.assertFalse(report["frozen_m9a_train"]["metrics_recomputed"])
            self.assertFalse(report["frozen_m9a_train"]["equal_seed_pooled_novelty_invented"])
            self.assertEqual(report["b2_limitations"]["empirical_null_seed"], 7)
            self.assertTrue(report["b2_limitations"]["single_seed_limitation"])
            self.assertFalse(report["b0_panel"]["included_in_matched_b1_d1_comparison"])
            self.assertEqual(report["b0_panel"]["requested_length"], "unavailable")
            self.assertEqual(report["eval_validation_expectations"]["unique_cores"], 154)
            self.assertEqual(report["eval_validation_expectations"]["clusters"], 79)
            self.assertFalse(report["clusters_weight_formulas"])
            self.assertFalse(report["clusters_trigger_resampling"])
            self.assertEqual(
                report["closeness"]["by_condition"]["D1"]["nearest_reference_normalized_edit_distance"][
                    "reference_unique_core_denominator"
                ],
                2,
            )
            found = []
            forbidden_keys(report, found)
            self.assertEqual(found, [])
            encoded = json.dumps(report)
            for sequence in ("CCCCCCCC", "ACGUACGU", "ACGTACGT", LONG_REFERENCE, LONG_D1, "UUUUAAAA", "GGGGCCGG"):
                self.assertNotIn(sequence, encoded)
            derived_path = os.path.join(output_dir, "m10_derived_evidence.json")
            report_path = os.path.join(output_dir, "m10_sequence_free_report.json")
            with real_open(derived_path, "rb") as handle:
                derived_bytes = handle.read()
            with real_open(report_path, "rb") as handle:
                report_bytes = handle.read()
            self.assertIn(b"ACGUACGU", derived_bytes)
            self.assertNotIn(b"ACGUACGU", report_bytes)
            second = os.path.join(temporary, "m10-synthetic-repeat")
            calls.clear()
            m10.run_synthetic(document(), second, m10.synthetic_authorization(), deterministic_fold(calls), root=ROOT)
            with real_open(os.path.join(second, "m10_sequence_free_report.json"), "rb") as handle:
                self.assertEqual(handle.read(), report_bytes)

    def test_block_binding_rejects_cross_family_missing_duplicate_and_incompatible(self):
        adapted = m10.adapt_frozen_ledgers(ledgers())["rows"]
        bound = m10.bind_matched_blocks(adapted)
        self.assertEqual([block["block"] for block in bound], ["A", "B"])
        cross = copy.deepcopy(adapted)
        for row in cross:
            if row["record_id"] == "d1-b-0":
                row["technical_block"] = "A"
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.bind_matched_blocks(cross)
        self.assertEqual(caught.exception.code, "cross_family_match")
        missing = [row for row in adapted if row["record_id"] != "d1-a-2"]
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.bind_matched_blocks(missing)
        self.assertEqual(caught.exception.code, "missing_pairing_row")
        duplicate = copy.deepcopy(adapted)
        extra = copy.deepcopy(next(row for row in duplicate if row["record_id"] == "b1-a-2"))
        extra["record_id"] = "b1-a-2-copy"
        duplicate.append(extra)
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.bind_matched_blocks(duplicate)
        self.assertEqual(caught.exception.code, "duplicate_pairing_key")
        incompatible = copy.deepcopy(adapted)
        for row in incompatible:
            if row["record_id"] == "d1-a-0":
                row["generation_seed"] = 50099
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.bind_matched_blocks(incompatible)
        self.assertEqual(caught.exception.code, "incompatible_schedule")

    def test_eval_stand_in_and_authorized_adapter_fail_closed(self):
        duplicate = synthetic_eval()
        duplicate.append(dict(duplicate[0], sequence_id="synthetic-eval-copy"))
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.adapt_synthetic_eval_stand_in(duplicate)
        self.assertEqual(caught.exception.code, "duplicate_eval_core")
        stand_in = m10.adapt_synthetic_eval_stand_in(synthetic_eval())
        self.assertEqual(stand_in["role"], "synthetic_eval_stand_in")
        self.assertFalse(stand_in["production_eval_opened"])
        self.assertEqual(stand_in["validation_expectations"]["identities"], 181)
        self.assertEqual(stand_in["validation_expectations"]["short_cores"], 89)
        self.assertEqual(stand_in["validation_expectations"]["long_cores"], 65)
        self.assertFalse(stand_in["validation_expectations"]["clusters_weight_formulas"])

        class Sentinel:
            def __bytes__(self):
                raise AssertionError("unauthorized payload was inspected")

        with self.assertRaises(m10.M10ContractError) as caught:
            m10.adapt_authorized_eval(Sentinel(), None)
        self.assertEqual(caught.exception.code, "eval_adapter_unauthorized")
        authorization = {"m10_execution_authorized": True, "open_eval": True, "payload_is_bytes": True}
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.adapt_authorized_eval(b"synthetic-eval-stand-in\n", authorization)
        self.assertEqual(caught.exception.code, "eval_hash_mismatch")
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.adapt_authorized_eval(os.path.join(ROOT, "data", "interim", "s7b_partition", "eval.csv"), authorization)
        self.assertEqual(caught.exception.code, "eval_path_refused")
        self.assertFalse(hasattr(m10, "validate_eval_identity_table"))
        shaped = (
            "sequence_id,sequence_core,cluster_id\n"
            "noncanonical,ACGT,c\n"
        ).encode("utf-8")
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.adapt_authorized_eval(shaped, None)
        self.assertEqual(caught.exception.code, "eval_adapter_unauthorized")
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.adapt_authorized_eval(shaped, authorization)
        self.assertEqual(caught.exception.code, "eval_hash_mismatch")

    def test_unauthorized_and_existing_output_do_not_open_protected_inputs(self):
        opened = []
        real_open = builtins.open

        def guarded_open(path, *args, **kwargs):
            text = os.fspath(path)
            opened.append(text)
            base = os.path.basename(text)
            if base == "eval.csv" or "derived_attempt_ledger" in base:
                raise AssertionError(text)
            return real_open(path, *args, **kwargs)

        builtins.open = guarded_open
        try:
            with self.assertRaises(m10.M10ContractError) as caught:
                m10.run_synthetic(document(), os.path.join(tempfile.gettempdir(), "m10-should-not-exist"), None, deterministic_fold([]), root=ROOT)
            self.assertEqual(caught.exception.code, "m10_unauthorized")
            self.assertEqual(opened, [])
            produced = dict(m10.synthetic_authorization())
            produced["production_execution"] = True
            with self.assertRaises(m10.M10ContractError) as caught:
                m10.run_synthetic(document(), os.path.join(tempfile.gettempdir(), "m10-should-not-exist"), produced, deterministic_fold([]), root=ROOT)
            self.assertEqual(caught.exception.code, "m10_unauthorized")
            self.assertEqual(opened, [])
        finally:
            builtins.open = real_open
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = os.path.join(temporary, "already")
            os.mkdir(output_dir)
            with self.assertRaises(m10.M10ContractError) as caught:
                m10.run_synthetic(document(), output_dir, m10.synthetic_authorization(), deterministic_fold([]), root=ROOT)
            self.assertEqual(caught.exception.code, "output_exists")
            self.assertEqual(os.listdir(output_dir), [])

    def test_s6_assignment_uses_sequence_length_and_keeps_invalid_rows(self):
        adapted = m10.adapt_frozen_ledgers(ledgers())
        by_id = {row["record_id"]: row for row in adapted["rows"]}
        empty = by_id["d1-a-1"]
        self.assertIsNone(empty["sequence"])
        self.assertIsNone(empty["s6_length_stratum"])
        self.assertEqual(empty["s6_length_stratum_applicability"], "not_applicable")
        self.assertNotIn("s6_length_stratum", ledgers()["D1"][1])
        observed = by_id["b1-b-0"]
        self.assertEqual(observed["requested_length"], 20)
        self.assertEqual(observed["s6_input_length"], len(LONG_REFERENCE))
        self.assertEqual(observed["s6_length_stratum"], m10.s6_assignment.assign_label(len(LONG_REFERENCE)))
        self.assertNotEqual(observed["s6_length_input"], "requested_length")
        mismatched = ledgers()
        mismatched["B1"][0]["requested_biological_length"] = 80
        mismatched["B1"][0]["max_seq_len"] = 81
        relabelled = m10.adapt_frozen_ledgers(mismatched)
        short_row = next(row for row in relabelled["rows"] if row["record_id"] == "b1-a-0")
        self.assertEqual(short_row["requested_length"], 80)
        self.assertEqual(short_row["s6_input_length"], len("CCCCCCCC"))
        self.assertEqual(short_row["s6_length_stratum"], m10.s6_assignment.assign_label(len("CCCCCCCC")))
        self.assertEqual(relabelled["row_counts"]["D1"], 6)
        stand_in = synthetic_eval()
        stand_in[0]["sequence_core"] = "A"
        stand_in[0]["sequence_length_core"] = 80
        assigned = m10.adapt_synthetic_eval_stand_in(stand_in)
        stored = next(core for core in assigned["cores"] if core["sequence_id"] == "synthetic-eval-short")
        self.assertEqual(stored["s6_input_length_source"], "sequence_length_core")
        self.assertEqual(stored["s6_input_length"], 80)
        self.assertEqual(stored["s6_length_stratum"], m10.s6_assignment.assign_label(80))
        self.assertEqual(m10.s6_assignment.label_from_responsibilities((0.5, 0.5)), "short")
        provenance = assigned["s6_assignment"]
        self.assertEqual(provenance["assignment_method"], "gmm_k2_maximum_posterior")
        self.assertEqual(provenance["component_0"], "short")
        self.assertEqual(provenance["component_1"], "long")
        self.assertEqual(provenance["tie_assignment"], "short")
        self.assertFalse(provenance["requested_length_is_input"])
        self.assertFalse(provenance["refit"])
        self.assertEqual(len(provenance["parameter_sha256"]), 64)
        self.assertIsNone(provenance["artefact_sha256"])
        self.assertEqual(provenance["artefact_absence_classification"], "provenance_limitation")
        self.assertFalse(provenance["parameter_record_hash_substituted_for_artefact"])
        self.assertNotEqual(provenance["artefact_sha256"], provenance["parameter_sha256"])

    def test_short_canonical_outputs_pass_and_deliberate_leaks_fail(self):
        rows = ledgers()
        replacements = {"b0-valid": "A", "b2-valid": "CC", "d1-a-0": "CAA"}
        for condition_rows in rows.values():
            for row in condition_rows:
                sequence = replacements.get(row["record_id"])
                if sequence is None:
                    continue
                row["parsed_sequence"] = sequence
                row["parsed_length"] = len(sequence)
        payload = document()
        payload["ledgers"] = rows
        with tempfile.TemporaryDirectory() as temporary:
            report = m10.run_synthetic(
                payload,
                os.path.join(temporary, "m10-short"),
                m10.synthetic_authorization(),
                deterministic_fold([]),
                root=ROOT,
            )
        self.assertEqual(report["accounting"]["B0"]["valid_acgu"], 1)
        self.assertEqual(report["accounting"]["B0"]["attempted"], 2)
        self.assertEqual(report["accounting"]["B0"]["s6_length_stratum_not_applicable"], 1)
        self.assertEqual(report["accounting"]["D1"]["attempted"], 6)
        self.assertEqual(report["accounting"]["D1"]["s6_length_stratum_not_applicable"], 2)
        self.assertEqual(report["s6_assignment"]["invalid_without_usable_sequence"], "not_applicable")
        leaked = copy.deepcopy(report)
        leaked["accounting"]["B0"]["notes"] = "A"
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.assert_public_report_sequence_free(leaked, {"A", "CC", "CAA"})
        self.assertEqual(caught.exception.code, "sequence_leak")
        embedded = copy.deepcopy(report)
        embedded["scientific_limitations"] = list(embedded["scientific_limitations"]) + ["deliberate ACGUACGU leak"]
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.assert_public_report_sequence_free(embedded, {"A", "ACGUACGU"})
        self.assertEqual(caught.exception.code, "sequence_leak")
        structural = copy.deepcopy(report)
        m10.assert_public_report_sequence_free(structural, {"A", "CC", "CAA"})

    def test_metric_spec_assigns_s6_labels_from_core_length(self):
        spec = m10.analysis._preflight().load_metric_spec()
        statement = m10.analysis._preflight().S6_ASSIGNMENT_STATEMENT
        seen = set()
        for metric in spec["metrics"]:
            encoded = json.dumps(metric)
            self.assertNotIn("not inferred from sequence length", encoded.lower())
            self.assertNotIn("never inferred from sequence length", encoded.lower())
            if metric["metric_id"] in m10.analysis._preflight().S6_ASSIGNMENT_METRIC_IDS:
                self.assertIn(statement, metric["length_treatment"])
                seen.add(metric["metric_id"])
        self.assertEqual(seen, set(m10.analysis._preflight().S6_ASSIGNMENT_METRIC_IDS))

    def test_s6_configuration_hash_changes_invalidate_recorded_evidence(self):
        required = (
            "scripts/modelling/generator_eval_s6_assignment.py",
            "config/global_s7b_partition.json",
            "config/global_s7c_ft_train_validation.json",
            "config/global_s7d_final_build.json",
        )
        self.assertTrue(set(required).issubset(m10.HASHED_CODE_PATHS))
        with tempfile.TemporaryDirectory() as temporary:
            report = m10.run_synthetic(
                document(),
                os.path.join(temporary, "m10-hash-evidence"),
                m10.synthetic_authorization(),
                deterministic_fold([]),
                root=ROOT,
            )
        recorded = report["code_and_configuration_hashes"]
        self.assertEqual(recorded, m10._code_hashes(ROOT))
        for relative in required:
            self.assertEqual(len(recorded[relative]), 64)
        with tempfile.TemporaryDirectory() as temporary:
            for relative in m10.HASHED_CODE_PATHS:
                destination = os.path.join(temporary, relative)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy(os.path.join(ROOT, relative), destination)
            self.assertEqual(m10._code_hashes(temporary), recorded)
            for relative in required:
                path = os.path.join(temporary, relative)
                with open(path, "ab") as handle:
                    handle.write(b"\n")
                changed = m10._code_hashes(temporary)
                self.assertNotEqual(changed, recorded)
                self.assertNotEqual(changed[relative], recorded[relative])
                for other in required:
                    if other != relative:
                        self.assertEqual(changed[other], recorded[other])
                shutil.copy(os.path.join(ROOT, relative), path)
            self.assertEqual(m10._code_hashes(temporary), recorded)

    def test_absent_artefact_is_not_replaced_by_the_parameter_hash(self):
        assignment = m10.s6_assignment
        with tempfile.TemporaryDirectory() as temporary:
            for relative in assignment.PARAMETER_CONFIGS:
                destination = os.path.join(temporary, relative)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy(os.path.join(ROOT, relative), destination)
            absent = assignment.provenance(temporary)
            self.assertFalse(absent["artefact_present"])
            self.assertIsNone(absent["artefact_sha256"])
            self.assertEqual(absent["artefact_absence_classification"], "provenance_limitation")
            self.assertFalse(absent["parameter_record_hash_substituted_for_artefact"])
            self.assertNotEqual(absent["artefact_sha256"], absent["parameter_sha256"])
            parameters = assignment.frozen_parameters(temporary)
            blob = json.dumps({"gmm_2": parameters}, sort_keys=True).encode("utf-8")
            artefact = os.path.join(temporary, assignment.ARTEFACT_RELATIVE)
            os.makedirs(os.path.dirname(artefact), exist_ok=True)
            with open(artefact, "wb") as handle:
                handle.write(blob)
            present = assignment.provenance(temporary)
            self.assertTrue(present["artefact_present"])
            self.assertIsNone(present["artefact_absence_classification"])
            self.assertEqual(present["artefact_sha256"], hashlib.sha256(blob).hexdigest())
            self.assertNotEqual(present["artefact_sha256"], present["parameter_sha256"])
            self.assertFalse(present["parameter_record_hash_substituted_for_artefact"])
            with open(artefact, "wb") as handle:
                handle.write(b'{"gmm_2": {"means": [1, 2], "variances": [1, 1], "weights": [0.5, 0.5]}}')
            with self.assertRaises(assignment.S6AssignmentError) as caught:
                assignment.provenance(temporary)
            self.assertEqual(caught.exception.code, "s6_artefact_invalid")

    def test_assign_label_matches_original_gmm_posterior_for_lengths_1_to_1000(self):
        data_preparation = os.path.join(ROOT, "scripts", "data_preparation")
        if data_preparation not in sys.path:
            sys.path.insert(0, data_preparation)
        from adapters.s6_profile import gmm_posterior_assignment

        parameters = m10.s6_assignment.frozen_parameters(ROOT)
        lengths = list(range(1, 1001))
        components = gmm_posterior_assignment(lengths, parameters)
        mismatches = []
        for length, component in zip(lengths, components):
            expected = "short" if int(component) == 0 else "long"
            observed = m10.s6_assignment.assign_label(length, parameters)
            if observed != expected:
                mismatches.append((length, int(component), observed))
        self.assertEqual(mismatches, [])
        self.assertEqual(len(lengths), 1000)


def viennarna_evidence(**overrides):
    evidence = {
        "interpreter": m10.PINNED_INTERPRETER,
        "python_version": "3.8.13",
        "package_name": "viennarna",
        "package_version": "2.7.0",
        "metadata_version": "2.7.0",
        "package_build": "py38pl5321hd78456e_0",
        "metadata_path": "/synthetic/conda-meta/viennarna.json",
        "call": "RNA.fold(sequence)",
        "model_details_altered": False,
        "model_details_set_by_code": False,
    }
    evidence.update(overrides)
    return evidence


def smoke_fold(calls):
    def fold(sequence):
        calls.append(sequence)
        return "." * len(sequence), -1.0

    return fold


def paired_schedule(per_block):
    rows = []
    for block, seed, generation_seed in (("A", 43, 800000), ("B", 44, 900000)):
        for index in range(per_block):
            shared = {
                "generation_seed": generation_seed,
                "master_attempt_index": index,
                "within_batch_position": index % 16,
                "requested_length": 40,
                "invocation_index": index // 16,
            }
            rows.append(
                dict(
                    shared,
                    condition="B1",
                    technical_block=block,
                    d1_training_seed=None,
                    record_id="b1-" + block + "-" + str(index),
                )
            )
            rows.append(
                dict(
                    shared,
                    condition="D1",
                    technical_block=block,
                    d1_training_seed=seed,
                    record_id="d1-" + block + "-" + str(index),
                )
            )
    rows.append({"condition": "B0", "technical_block": None, "d1_training_seed": None, "record_id": "b0-outside"})
    rows.append({"condition": "B2", "technical_block": None, "d1_training_seed": None, "record_id": "b2-outside"})
    return rows


def synthetic_prepared():
    adapted = m10.adapt_frozen_ledgers(ledgers())
    rows = adapted["rows"]
    bound = m10.bind_matched_blocks(rows)
    blocks = []
    for block in bound:
        blocks.append(
            {
                "block": block["block"],
                "technical_block": block["technical_block"],
                "d1_training_seed": block["d1_training_seed"],
                "b1_attempts": len(block["b1_rows"]),
                "d1_attempts": len(block["d1_rows"]),
                "paired_row_count": block["paired_row_count"],
                "generation_seed_count": len(block["generation_seeds"]),
                "one_to_one": True,
                "is_training_replicate": False,
                "is_significance_test_unit": False,
            }
        )
    denominators = {}
    for condition in ("B0", "B1", "B2", "D1"):
        denominators[condition] = m10._observed_denominators([row for row in rows if row["condition"] == condition])
    identities = {}
    for condition in ("B0", "B1", "B2", "D1"):
        identities[condition] = {
            "relative_path": "synthetic/" + condition + ".jsonl",
            "path": "/synthetic/" + condition + ".jsonl",
            "sha256": "ab" * 32,
            "byte_count": adapted["row_counts"][condition],
            "attempts": adapted["row_counts"][condition],
        }
    return {
        "fixture_role": "SYNTHETIC",
        "identity": {
            "source_manifest": {
                "relative_path": "synthetic/source_manifest.json",
                "path": "/synthetic/source_manifest.json",
                "sha256": "cd" * 32,
            },
            "accounting_summary": {
                "relative_path": "synthetic/accounting.json",
                "path": "/synthetic/accounting.json",
                "sha256": "ef" * 32,
                "sequence_strings_emitted": False,
            },
            "ledgers": identities,
            "b2_empirical_null_seed": 7,
            "excluded_sources": {"method": "synthetic", "sequence_comparison": False, "lineages": []},
        },
        "denominators": denominators,
        "schedule": {
            "status": "passed",
            "validation": "synthetic_fixture",
            "blocks": blocks,
            "b0_attempts_outside_blocks": 2,
            "b2_attempts_outside_blocks": 2,
            "b0_included_in_matched_blocks": False,
            "b2_included_in_matched_blocks": False,
            "cross_family_rows": 0,
            "missing_pairing_rows": 0,
            "duplicated_pairing_rows": 0,
            "extra_pairing_rows": 0,
        },
        "sequences_for_leak_check": [row["sequence"] for row in rows if isinstance(row.get("sequence"), str)],
        "frozen_configuration_hashes": {
            "metric_spec_role": "pinned_frozen_production_ready",
            "metric_spec_freeze_status": "frozen",
            "metric_spec_production_ready": True,
        },
    }


class ProtectedEvalIdentityAdapterTests(unittest.TestCase):
    """Protected EVAL rows are scientific identities. Shared cores collapse.

    These tests pass bytes to the parser. They do not open repository EVAL.
    The synthetic stand-in stays one row per unique core.
    """

    def setUp(self):
        self.real_open = builtins.open
        self.real_os_open = os.open
        self.opened = []

        def guarded_open(path, *args, **kwargs):
            text = os.fspath(path)
            self.opened.append(text)
            if os.path.basename(text) == "eval.csv":
                raise AssertionError(text)
            return self.real_open(path, *args, **kwargs)

        def guarded_os_open(path, flags, mode=0o777, *, dir_fd=None):
            text = os.fspath(path)
            self.opened.append(text)
            if os.path.basename(text) == "eval.csv":
                raise AssertionError(text)
            return self.real_os_open(path, flags, mode, dir_fd=dir_fd)

        builtins.open = guarded_open
        os.open = guarded_os_open

    def tearDown(self):
        builtins.open = self.real_open
        os.open = self.real_os_open
        self.assertFalse(any(os.path.basename(path) == "eval.csv" for path in self.opened))

    def test_shared_sequence_id_collapses_to_one_core(self):
        identities, cores = m10._parse_eval_csv(
            protected_eval_csv(
                [
                    identity_row("S5I_synthetic_a", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8),
                    identity_row("S5I_synthetic_b", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8),
                ]
            )
        )
        self.assertEqual(len(identities), 2)
        self.assertEqual(len(cores), 1)
        core = cores[0]
        self.assertEqual(core["identity_count"], 2)
        self.assertEqual(core["weight"], 1)
        self.assertEqual(core["sequence_id"], "S5SEQ_synthetic_shared")
        self.assertEqual(core["sequence_core"], "ACGUACGU")
        self.assertEqual(core["cluster_id"], "synthetic-cluster")
        self.assertNotIn("scientific_identity_id", core)

    def test_duplicated_scientific_identity_id_fails(self):
        payload = protected_eval_csv(
            [
                identity_row("S5I_synthetic_a", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8),
                identity_row("S5I_synthetic_a", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8),
            ]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(payload)
        self.assertEqual(caught.exception.code, "duplicate_scientific_identity_id")
        missing = protected_eval_csv(
            [identity_row("", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8)]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(missing)
        self.assertEqual(caught.exception.code, "duplicate_scientific_identity_id")

    def test_repeated_sequence_id_with_different_cores_fails(self):
        payload = protected_eval_csv(
            [
                identity_row("S5I_synthetic_a", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8),
                identity_row("S5I_synthetic_b", "S5SEQ_synthetic_shared", "AAACCCGGG", "synthetic-cluster-b", 9),
            ]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(payload)
        self.assertEqual(caught.exception.code, "sequence_id_core_conflict")

    def test_one_core_with_different_sequence_ids_fails(self):
        payload = protected_eval_csv(
            [
                identity_row("S5I_synthetic_a", "S5SEQ_synthetic_one", "ACGUACGU", "synthetic-cluster", 8),
                identity_row("S5I_synthetic_b", "S5SEQ_synthetic_two", "ACGUACGU", "synthetic-cluster", 8),
            ]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(payload)
        self.assertEqual(caught.exception.code, "sequence_id_core_conflict")

    def test_repeated_core_with_conflicting_cluster_or_length_fails(self):
        cluster = protected_eval_csv(
            [
                identity_row("S5I_synthetic_a", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8),
                identity_row("S5I_synthetic_b", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster-other", 8),
            ]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(cluster)
        self.assertEqual(caught.exception.code, "eval_core_conflict")
        short = m10.s6_assignment.assign_sequence("ACGUACGU", "8")
        long = m10.s6_assignment.assign_sequence("ACGUACGU", "80")
        self.assertNotEqual(short["s6_length_stratum"], long["s6_length_stratum"])
        length = protected_eval_csv(
            [
                identity_row("S5I_synthetic_a", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8),
                identity_row("S5I_synthetic_b", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 80),
            ]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(length)
        self.assertEqual(caught.exception.code, "eval_core_conflict")
        stored = protected_eval_csv(
            [
                identity_row("S5I_synthetic_a", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8),
                identity_row("S5I_synthetic_b", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", ""),
            ]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(stored)
        self.assertEqual(caught.exception.code, "eval_core_conflict")

    def test_identity_count_and_core_count_remain_distinct(self):
        identities, cores = m10._parse_eval_csv(
            protected_eval_csv(
                [
                    identity_row("S5I_synthetic_a", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8),
                    identity_row("S5I_synthetic_b", "S5SEQ_synthetic_shared", "ACGUACGU", "synthetic-cluster", 8),
                    identity_row("S5I_synthetic_c", "S5SEQ_synthetic_only", "AAACCCGGG", "synthetic-cluster-only", 9),
                ]
            )
        )
        self.assertEqual(len(identities), 3)
        self.assertEqual(len(cores), 2)
        self.assertNotEqual(len(identities), len(cores))
        self.assertEqual(sum(core["identity_count"] for core in cores), 3)
        self.assertEqual([core["identity_count"] for core in cores], [2, 1])
        self.assertTrue(all(core["weight"] == 1 for core in cores))
        self.assertEqual(cores[0]["sequence_id"], "S5SEQ_synthetic_shared")
        self.assertEqual(
            m10.EVAL_EXPECTATIONS,
            {"identities": 181, "unique_cores": 154, "clusters": 79, "short_cores": 89, "long_cores": 65},
        )

    def test_missing_sequence_core_or_cluster_fails_closed(self):
        missing_sequence_id = protected_eval_csv(
            [identity_row("S5I_synthetic_a", "", "ACGUACGU", "synthetic-cluster", 8)]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(missing_sequence_id)
        self.assertEqual(caught.exception.code, "duplicate_sequence_id")
        identity_only = (
            "scientific_identity_id,sequence_core,cluster_id\n"
            "S5I_synthetic_a,ACGUACGU,synthetic-cluster\n"
        ).encode("utf-8")
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(identity_only)
        self.assertEqual(caught.exception.code, "duplicate_sequence_id")
        missing_core = protected_eval_csv(
            [identity_row("S5I_synthetic_a", "S5SEQ_synthetic", "", "synthetic-cluster", "")]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(missing_core)
        self.assertEqual(caught.exception.code, "eval_noncanonical")
        invalid_core = protected_eval_csv(
            [identity_row("S5I_synthetic_a", "S5SEQ_synthetic", "ACGT", "synthetic-cluster", 4)]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(invalid_core)
        self.assertEqual(caught.exception.code, "eval_noncanonical")
        missing_cluster = protected_eval_csv(
            [identity_row("S5I_synthetic_a", "S5SEQ_synthetic", "ACGUACGU", "", 8)]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(missing_cluster)
        self.assertEqual(caught.exception.code, "eval_cluster_missing")
        invalid_length = protected_eval_csv(
            [identity_row("S5I_synthetic_a", "S5SEQ_synthetic", "ACGUACGU", "synthetic-cluster", "nope")]
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10._parse_eval_csv(invalid_length)
        self.assertEqual(caught.exception.code, "stored_length_invalid")

    def test_unauthorized_adapter_rejects_before_payload_inspection(self):
        class Sentinel:
            def __bytes__(self):
                raise AssertionError("unauthorized payload was inspected")

        with self.assertRaises(m10.M10ContractError) as caught:
            m10.adapt_authorized_eval(Sentinel(), None)
        self.assertEqual(caught.exception.code, "eval_adapter_unauthorized")

    def test_synthetic_core_level_adapter_still_rejects_repeated_sequence_ids(self):
        rows = synthetic_eval()
        rows.append(dict(rows[0]))
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.adapt_synthetic_eval_stand_in(rows)
        self.assertEqual(caught.exception.code, "duplicate_sequence_id")
        copied = synthetic_eval()
        copied.append(dict(copied[0], sequence_id="synthetic-eval-copy"))
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.adapt_synthetic_eval_stand_in(copied)
        self.assertEqual(caught.exception.code, "duplicate_eval_core")


class ProductionReadinessTests(unittest.TestCase):
    def test_generated_preflight_cannot_open_eval(self):
        parameters = inspect.signature(m10.run_generated_input_preflight).parameters
        self.assertFalse(any("eval" in name for name in parameters))
        source = inspect.getsource(m10.run_generated_input_preflight)
        self.assertNotIn("read_frozen_eval_once", source)
        self.assertNotIn("run_authorized_production", source)
        allowlist = " ".join(
            [
                m10.SOURCE_MANIFEST_RELATIVE,
                m10.ACCOUNTING_SUMMARY_RELATIVE,
                m10.CONTRACT_RELATIVE_PATH,
            ]
            + [item[0] for item in m10.FROZEN_LEDGER_FILES.values()]
        )
        self.assertNotIn("eval.csv", allowlist)
        self.assertNotIn("ft_train.csv", allowlist)
        self.assertNotIn("ref.csv", allowlist)
        opened = []
        real_os_open = os.open
        real_builtin_open = builtins.open

        def guarded_os_open(path, flags, mode=0o777):
            text = os.fspath(path)
            opened.append(text)
            if os.path.basename(text) == "eval.csv":
                raise AssertionError(text)
            return real_os_open(path, flags, mode)

        def guarded_builtin_open(path, *args, **kwargs):
            text = os.fspath(path)
            opened.append(text)
            if os.path.basename(text) == "eval.csv":
                raise AssertionError(text)
            return real_builtin_open(path, *args, **kwargs)

        def refuse_eval(*args, **kwargs):
            raise AssertionError("preflight opened EVAL")

        with tempfile.TemporaryDirectory() as temporary:
            eval_path = os.path.join(temporary, "eval.csv")
            with real_builtin_open(eval_path, "wb") as handle:
                handle.write(b"sequence_id,sequence_core\n")
            os.open = guarded_os_open
            builtins.open = guarded_builtin_open
            m10.read_frozen_eval_once = refuse_eval
            try:
                with self.assertRaises(m10.M10ContractError) as caught:
                    m10.run_generated_input_preflight(
                        os.path.join(temporary, "preflight.json"),
                        m10.generated_preflight_authorization(),
                        root=temporary,
                    )
                self.assertIn(caught.exception.code, {"generated_input_missing", "generated_path_refused", "protected_input_refused"})
                with self.assertRaises(m10.M10ContractError) as caught:
                    m10.run_generated_input_preflight(
                        os.path.join(temporary, "preflight.json"),
                        m10.production_authorization(),
                        root=temporary,
                    )
                self.assertEqual(caught.exception.code, "preflight_unauthorized")
            finally:
                os.open = real_os_open
                builtins.open = real_builtin_open
                m10.read_frozen_eval_once = real_read_eval
        self.assertNotIn(eval_path, opened)
        self.assertFalse(any(os.path.basename(path) == "eval.csv" for path in opened))

    def test_unauthorized_production_does_not_inspect_eval(self):
        class Sentinel:
            def __fspath__(self):
                raise AssertionError("EVAL path inspected")

            def __call__(self):
                raise AssertionError("EVAL payload inspected")

            def __getattribute__(self, name):
                raise AssertionError("EVAL access inspected")

        sentinel = Sentinel()
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.run_authorized_production(sentinel, None, eval_access=sentinel, seams=sentinel)
        self.assertEqual(caught.exception.code, "production_unauthorized")
        almost = m10.production_authorization()
        almost["open_eval"] = False
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.run_authorized_production(sentinel, almost, eval_access=sentinel, seams=sentinel)
        self.assertEqual(caught.exception.code, "production_unauthorized")

    def test_non_eval_checks_precede_the_authorized_eval_read(self):
        class OrderSeams:
            def __init__(self, fail_at=None):
                self.events = []
                self.fail_at = fail_at

            def _mark(self, name):
                self.events.append(name)
                if self.fail_at == name:
                    raise m10.M10ContractError("viennarna_version_mismatch", "stopped before EVAL")

            def output_directory(self, output_dir):
                self._mark("output_directory")

            def generated_inputs(self):
                self._mark("generated_input_hashes")
                return {"schedule": {"status": "passed"}}

            def schedule(self, generated):
                self._mark("schedule")
                return generated["schedule"]

            def configuration_hashes(self):
                self._mark("frozen_configuration")
                # Seam stand-in for the later freeze. The repository specification stays draft.
                return {
                    "metric_spec_freeze_status": "frozen",
                    "metric_spec_production_ready": True,
                    "metric_spec_sha256": "ab" * 32,
                }

            def viennarna(self):
                self._mark("viennarna")
                return {}

            def open_eval_once(self):
                self._mark("eval")
                return b"unauthorized-stand-in"

        seams = OrderSeams()
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.run_authorized_production(
                os.path.join(tempfile.gettempdir(), "m10-order"),
                m10.production_authorization(),
                seams=seams,
            )
        self.assertEqual(caught.exception.code, "eval_hash_mismatch")
        self.assertEqual(
            seams.events,
            [
                "output_directory",
                "generated_input_hashes",
                "schedule",
                "frozen_configuration",
                "viennarna",
                "eval",
            ],
        )
        self.assertEqual(seams.events.count("eval"), 1)
        stopped = OrderSeams(fail_at="viennarna")
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.run_authorized_production(
                os.path.join(tempfile.gettempdir(), "m10-order"),
                m10.production_authorization(),
                seams=stopped,
            )
        self.assertEqual(caught.exception.code, "viennarna_version_mismatch")
        self.assertNotIn("eval", stopped.events)

    def test_viennarna_version_and_build_mismatch_refuse_before_folding(self):
        calls = []
        fold = smoke_fold(calls)
        mismatches = (
            ({"package_version": "2.7.2", "metadata_version": "2.7.2"}, "viennarna_version_mismatch"),
            ({"package_build": "py38_0"}, "viennarna_build_mismatch"),
            ({"interpreter": "/usr/bin/python"}, "viennarna_interpreter_mismatch"),
            ({"model_details_altered": True}, "viennarna_model_altered"),
        )
        for overrides, code in mismatches:
            calls.clear()
            with self.assertRaises(m10.M10ContractError) as caught:
                m10.run_synthetic_viennarna_smoke(viennarna_evidence(**overrides), fold=fold)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(calls, [])
        source = inspect.getsource(m10.production_fold)
        self.assertIn("return RNA.fold(sequence)", source)
        self.assertNotIn("RNA.md", source)
        self.assertNotIn("temperature", source)
        self.assertNotIn("uniq_ML", source)
        evidence = m10.collect_viennarna_evidence()
        self.assertEqual(evidence["package_version"], "2.7.0")
        self.assertEqual(evidence["package_build"], "py38pl5321hd78456e_0")
        self.assertEqual(evidence["interpreter"], m10.PINNED_INTERPRETER)
        self.assertFalse(evidence["model_details_altered"])
        smoke = m10.run_synthetic_viennarna_smoke(evidence)
        self.assertFalse(smoke["scientific_result"])
        self.assertEqual(smoke["fold_calls"], 1)
        self.assertTrue(smoke["structure_length_matches_sequence"])
        self.assertNotIn(m10.SYNTHETIC_SMOKE_SEQUENCE, json.dumps(smoke))

    def test_distinct_sequence_fold_cache_reuses_duplicate_attempts(self):
        calls = []
        summary = m10.summarize_cached_structure(["CCCC", "CCCC", "GGGG"], deterministic_fold(calls))
        self.assertEqual(calls, ["CCCC", "GGGG"])
        self.assertEqual(summary["valid_row_count"], 3)
        self.assertEqual(summary["distinct_valid_sequence_count"], 2)
        self.assertEqual(summary["fold_calls_for_new_sequences"], 2)
        self.assertIn("median", summary["mfe_per_nt"])
        self.assertIn("median", summary["paired_fraction"])
        self.assertFalse(summary["structure_distance_defined"])
        self.assertNotIn("structure_distance", summary)
        self.assertTrue(summary["distinct_sequences_folded_once"])
        self.assertTrue(summary["duplicate_attempts_reuse_cache"])
        cache = {}
        m10.summarize_cached_structure(["CCCC"], deterministic_fold(calls), cache)
        calls.clear()
        reused = m10.summarize_cached_structure(["CCCC", "CCCC"], deterministic_fold(calls), cache)
        self.assertEqual(calls, [])
        self.assertEqual(reused["fold_calls_for_new_sequences"], 0)
        self.assertEqual(reused["valid_row_count"], 2)

    def test_production_block_pair_validation(self):
        small = paired_schedule(1)
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.validate_production_matched_blocks(small)
        self.assertEqual(caught.exception.code, "schedule_count_mismatch")
        cross = paired_schedule(1)
        for row in cross:
            if row["record_id"] == "d1-B-0":
                row["technical_block"] = "A"
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.validate_production_matched_blocks(cross)
        self.assertEqual(caught.exception.code, "cross_family_match")
        missing = paired_schedule(1)
        missing.append(
            {
                "condition": "D1",
                "technical_block": "A",
                "d1_training_seed": 43,
                "record_id": "d1-extra",
                "generation_seed": 800000,
                "master_attempt_index": 99,
                "within_batch_position": 0,
                "requested_length": 40,
                "invocation_index": 9,
            }
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.validate_production_matched_blocks(missing)
        self.assertEqual(caught.exception.code, "missing_pairing_row")
        extra = paired_schedule(1)
        extra.append(
            {
                "condition": "B1",
                "technical_block": "B",
                "d1_training_seed": None,
                "record_id": "b1-extra",
                "generation_seed": 900000,
                "master_attempt_index": 99,
                "within_batch_position": 1,
                "requested_length": 40,
                "invocation_index": 9,
            }
        )
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.validate_production_matched_blocks(extra)
        self.assertEqual(caught.exception.code, "extra_pairing_row")
        duplicate = paired_schedule(1)
        copied = dict(next(row for row in duplicate if row["record_id"] == "b1-A-0"))
        copied["record_id"] = "b1-A-copy"
        duplicate.append(copied)
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.validate_production_matched_blocks(duplicate)
        self.assertEqual(caught.exception.code, "duplicate_pairing_key")
        invaded = paired_schedule(1)
        for row in invaded:
            if row["condition"] == "B0":
                row["technical_block"] = "A"
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.validate_production_matched_blocks(invaded)
        self.assertEqual(caught.exception.code, "schedule_condition_invalid")
        schedule = m10.validate_production_matched_blocks(paired_schedule(15000))
        self.assertEqual(schedule["status"], "passed")
        self.assertEqual(schedule["validation"], "one_to_one_frozen_pairing_keys")
        self.assertFalse(schedule["b0_included_in_matched_blocks"])
        self.assertFalse(schedule["b2_included_in_matched_blocks"])
        self.assertEqual(schedule["b0_attempts_outside_blocks"], 1)
        self.assertEqual(schedule["b2_attempts_outside_blocks"], 1)
        self.assertEqual(schedule["cross_family_rows"], 0)
        self.assertEqual(schedule["missing_pairing_rows"], 0)
        self.assertEqual(schedule["duplicated_pairing_rows"], 0)
        self.assertEqual(schedule["extra_pairing_rows"], 0)
        blocks = {block["block"]: block for block in schedule["blocks"]}
        self.assertEqual(blocks["A"]["d1_training_seed"], 43)
        self.assertEqual(blocks["B"]["d1_training_seed"], 44)
        self.assertEqual(blocks["A"]["b1_attempts"], 15000)
        self.assertEqual(blocks["A"]["d1_attempts"], 15000)
        self.assertEqual(blocks["B"]["paired_row_count"], 15000)
        self.assertTrue(blocks["A"]["one_to_one"])
        self.assertFalse(blocks["A"]["is_training_replicate"])
        encoded = json.dumps(schedule)
        self.assertNotIn("b1-A-0", encoded)
        self.assertNotIn("parsed_sequence", encoded)

    def test_existing_output_is_refused(self):
        calls = []
        with tempfile.TemporaryDirectory() as temporary:
            output_path = os.path.join(temporary, "preflight.json")
            with open(output_path, "wb") as handle:
                handle.write(b"{}\n")
            with self.assertRaises(m10.M10ContractError) as caught:
                m10.run_generated_input_preflight(
                    output_path,
                    m10.generated_preflight_authorization(),
                    inputs=synthetic_prepared(),
                    fold=smoke_fold(calls),
                    viennarna_evidence=viennarna_evidence(),
                    root=ROOT,
                )
            self.assertEqual(caught.exception.code, "output_exists")
            self.assertEqual(calls, [])
            with open(output_path, "rb") as handle:
                self.assertEqual(handle.read(), b"{}\n")
            nested = os.path.join(ROOT, "results", "m10_should_not_create.json")
            with self.assertRaises(m10.M10ContractError) as caught:
                m10.publish_sequence_free_json(nested, {"schema": "synthetic"}, ROOT)
            self.assertEqual(caught.exception.code, "biological_output_refused")
            self.assertFalse(os.path.exists(nested))
            existing = os.path.join(temporary, "already")
            os.mkdir(existing)
            with self.assertRaises(m10.M10ContractError) as caught:
                m10.check_production_output_directory(existing)
            self.assertEqual(caught.exception.code, "output_exists")

    def test_sequence_free_preflight_omits_sequences_and_metric_values(self):
        calls = []
        prepared = synthetic_prepared()
        sequences = list(prepared["sequences_for_leak_check"]) + [m10.SYNTHETIC_SMOKE_SEQUENCE, "ACGTACGT"]
        record_ids = [row["record_id"] for condition_rows in ledgers().values() for row in condition_rows]
        with tempfile.TemporaryDirectory() as temporary:
            output_path = os.path.join(temporary, "preflight.json")
            published = m10.run_generated_input_preflight(
                output_path,
                m10.generated_preflight_authorization(),
                inputs=prepared,
                fold=smoke_fold(calls),
                viennarna_evidence=viennarna_evidence(),
                root=ROOT,
            )
            self.assertFalse(published["eval_opened"])
            self.assertEqual(calls, [m10.SYNTHETIC_SMOKE_SEQUENCE])
            with open(output_path, "r", encoding="utf-8") as handle:
                text = handle.read()
            with open(published["smoke_path"], "r", encoding="utf-8") as handle:
                smoke_text = handle.read()
            document = json.loads(text)
            with self.assertRaises(m10.M10ContractError) as caught:
                m10.publish_sequence_free_json(output_path, document, ROOT)
            self.assertEqual(caught.exception.code, "output_exists")
        for sequence in sequences:
            self.assertNotIn(sequence, text)
            self.assertNotIn(sequence, smoke_text)
        for record_id in record_ids:
            self.assertNotIn(record_id, text)
        self.assertNotIn("eval.csv", text)
        self.assertNotIn("-1.0", text)
        self.assertNotIn('"structure_distance":', text)
        document = json.loads(text)
        self.assertFalse(document["scientific_result"])
        self.assertEqual(document["metric_spec_freeze_status"], "frozen")
        self.assertTrue(document["production_ready"])
        self.assertFalse(document["eval_opened"])
        self.assertFalse(document["m10_execution_authorized"])
        self.assertFalse(document["production_execution_invoked"])
        self.assertEqual(document["readiness"]["biological_production_execution"], "not_yet_authorized")
        self.assertEqual(document["readiness"]["generated_input_preflight"], "implemented_and_synthetically_verified")
        self.assertFalse(document["readiness"]["structure_distance_defined"])
        self.assertEqual(document["counts"]["B1"]["attempts"], 6)
        self.assertEqual(document["counts"]["D1"]["invalid_retained"], 2)

    def test_denominator_mismatch_is_a_blocker_and_rows_stay(self):
        adapted = m10.adapt_frozen_ledgers(ledgers())
        accounting = {
            "conditions": {
                condition: {"total_attempts": 1, "distinct_valid_sequences": 1, "valid_canonical_count": 1}
                for condition in ("B0", "B1", "B2", "D1")
            }
        }
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.validate_generated_denominators(adapted, accounting)
        self.assertEqual(caught.exception.code, "denominator_mismatch")
        self.assertEqual(sum(adapted["row_counts"].values()), 16)
        self.assertFalse(adapted["rows_dropped"])

    def test_metric_spec_is_frozen_and_execution_stays_unauthorized(self):
        spec = m10.analysis._preflight().load_metric_spec()
        self.assertEqual(spec["freeze_status"], "frozen")
        self.assertTrue(all(metric["freeze_status"] == "frozen" for metric in spec["metrics"]))
        contract = spec["m10_draft_contract"]
        self.assertEqual(contract["document_status"], "frozen")
        self.assertTrue(contract["labelled_production_ready"])
        self.assertTrue(contract["labelled_frozen"])
        self.assertEqual(contract["implementation_readiness"]["metric_specification"], "frozen_and_production_ready")
        self.assertEqual(contract["implementation_readiness"]["biological_production_execution"], "not_yet_authorized")
        self.assertIn("frozen and production-ready", contract["inactive_pathway_supersession"]["statement"])
        self.assertIn("Production execution remains unauthorized", contract["inactive_pathway_supersession"]["statement"])
        self.assertEqual(m10.FROZEN_METRIC_SPEC_SHA256, m10._sha256_file(os.path.join(ROOT, m10.METRIC_SPEC_RELATIVE)))
        self.assertTrue(contract["production_report_writer_exists"])
        self.assertNotIn("does not yet exist", json.dumps(contract))
        self.assertIn("not an active implementation blocker", contract["inactive_pathway_supersession"]["statement"])
        self.assertTrue(contract["generated_input_preflight_writer_exists"])
        readiness = contract["implementation_readiness"]
        self.assertEqual(readiness["generated_input_preflight"], "implemented_and_synthetically_verified")
        self.assertEqual(readiness["authorized_production_execution"], "implemented_not_invoked")
        self.assertEqual(readiness["biological_production_execution"], "not_yet_authorized")
        self.assertEqual(readiness["eval_opening"], "not_yet_authorized")
        required = {item["id"]: item for item in contract["required_implementation_work"]}
        for item_id in ("ledger_adapter", "authorized_eval_adapter", "matched_block_binding", "structure_execution", "sequence_free_report_writer"):
            self.assertEqual(required[item_id]["status"], "required")
            self.assertEqual(required[item_id]["implementation_readiness"], "implemented_and_synthetically_verified")
            self.assertEqual(required[item_id]["biological_production_execution"], "not_yet_authorized")


real_read_eval = m10.read_frozen_eval_once


def frozen_seam_attestation():
    """Attestation a future freeze seam would return. It does not edit the specification."""
    return {
        "metric_spec_freeze_status": "frozen",
        "metric_spec_production_ready": True,
        "metric_spec_sha256": "cd" * 32,
    }


FROZEN_CANDIDATE_STATEMENT = (
    "The executable metric specification is frozen and production-ready. "
    "Production execution remains unauthorized. "
    "M10 execution remains unauthorized. EVAL access remains unauthorized. "
    "The ledger adapter, single-read EVAL adapter, matched schedule, structure wrapper and distinct-sequence cache, "
    "and production writer are implemented and synthetically verified. They have not run biologically. "
    "Awaiting authorization is not an active implementation blocker. "
    "The production publication pathway stays uninvoked. "
    "Every retained metric has an explicit production output location or an explicit audit-only or inherited disposition."
)


def frozen_candidate_spec():
    """In-memory frozen candidate. This does not write the on-disk specification."""
    spec = copy.deepcopy(m10.analysis._preflight().load_metric_spec())
    spec["freeze_status"] = "frozen"
    for metric in spec["metrics"]:
        metric["freeze_status"] = "frozen"
    contract = spec["m10_draft_contract"]
    contract["document_status"] = "frozen"
    contract["labelled_frozen"] = True
    contract["labelled_production_ready"] = True
    contract["implementation_readiness"]["metric_specification"] = "frozen_and_production_ready"
    contract["inactive_pathway_supersession"]["statement"] = FROZEN_CANDIDATE_STATEMENT
    for item in spec["blocking_items"]:
        if item.get("status") == "unresolved":
            item["status"] = "resolved"
    return spec


def partial_top_level_spec():
    """Top-level freeze flags only. Metric rows and the contract stay draft."""
    spec = copy.deepcopy(m10.analysis._preflight().load_metric_spec())
    spec["freeze_status"] = "frozen"
    for metric in spec["metrics"]:
        metric["freeze_status"] = "draft"
    contract = spec["m10_draft_contract"]
    contract["document_status"] = "draft"
    contract["labelled_frozen"] = True
    contract["labelled_production_ready"] = True
    contract["implementation_readiness"]["metric_specification"] = "draft_not_frozen"
    contract["inactive_pathway_supersession"]["statement"] = (
        "This specification remains draft and is not production-ready. Production execution remains unauthorized."
    )
    return spec


def synthetic_eval_payload():
    """One identity row per unique core for the authorized synthetic seam.

    Shared-core collapse is covered by the protected identity-row tests. This
    fixture stays one identity per core, which is a valid special case.
    """
    cores = (
        ("S5I_synthetic_short", "synthetic-eval-short", "ACGUACGU", "synthetic-cluster-short"),
        ("S5I_synthetic_long", "synthetic-eval-long", LONG_REFERENCE, "synthetic-cluster-long"),
        ("S5I_synthetic_only", "synthetic-eval-only", "AAACCCGGG", "synthetic-cluster-only"),
    )
    lines = ["scientific_identity_id,sequence_id,sequence_core,cluster_id"]
    labels = []
    for identity, sequence_id, sequence, cluster_id in cores:
        lines.append(",".join((identity, sequence_id, sequence, cluster_id)))
        labels.append(m10.s6_assignment.assign_label(len(sequence)))
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    expectations = {
        "identities": len(cores),
        "unique_cores": len(cores),
        "clusters": len({cluster_id for _, _, _, cluster_id in cores}),
        "short_cores": sum(label == "short" for label in labels),
        "long_cores": sum(label == "long" for label in labels),
    }
    return payload, expectations, [sequence for _, _, sequence, _ in cores]


class CompletingSeams:
    """Injected production seam. It never opens the repository EVAL file."""

    def __init__(self, payload, rows):
        self.payload = payload
        self.rows = rows
        self.events = []
        self.eval_reads = 0

    def output_directory(self, output_dir):
        self.events.append("output_directory")
        m10.check_production_output_directory(output_dir)

    def generated_inputs(self):
        self.events.append("generated_input_hashes")
        return {
            "schedule": {"status": "passed", "validation": "synthetic_authorized_seam"},
            "private_adapted_rows": self.rows,
            "identity": {
                "source_manifest": {"relative_path": "synthetic/source_manifest.json", "sha256": "ab" * 32},
                "ledgers": {"B0": {"sha256": "cd" * 32, "attempts": 2}},
            },
            "denominators": {"B0": {"attempts": 2}, "B1": {"attempts": 6}, "B2": {"attempts": 2}, "D1": {"attempts": 6}},
        }

    def schedule(self, generated):
        self.events.append("schedule")
        return generated["schedule"]

    def configuration_hashes(self):
        self.events.append("frozen_configuration")
        return frozen_seam_attestation()

    def viennarna(self):
        self.events.append("viennarna")
        return viennarna_evidence()

    def open_eval_once(self):
        self.events.append("eval")
        self.eval_reads += 1
        return self.payload


class AuthorizedProductionPathwayTests(unittest.TestCase):
    def test_draft_or_unpinned_spec_fails_before_eval_access(self):
        opened = []
        real_open = builtins.open

        def guarded_open(path, *args, **kwargs):
            text = os.fspath(path)
            opened.append(text)
            if os.path.basename(text) == "eval.csv":
                raise AssertionError(text)
            return real_open(path, *args, **kwargs)

        builtins.open = guarded_open
        try:
            decision = m10.assert_production_metric_spec_gate(ROOT)
        finally:
            builtins.open = real_open
        self.assertFalse(any(os.path.basename(path) == "eval.csv" for path in opened))
        self.assertEqual(decision["metric_spec_freeze_status"], "frozen")
        self.assertTrue(decision["metric_spec_production_ready"])
        self.assertEqual(decision["metric_spec_sha256"], m10.FROZEN_METRIC_SPEC_SHA256)
        drafted = {
            "freeze_status": "draft",
            "m10_draft_contract": {"labelled_frozen": False, "labelled_production_ready": False},
        }
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.production_metric_spec_decision(drafted, "ab" * 32, "ab" * 32)
        self.assertEqual(caught.exception.code, "metric_spec_unfrozen")
        labelled = {
            "freeze_status": "frozen",
            "m10_draft_contract": {"labelled_frozen": True, "labelled_production_ready": True},
        }
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.production_metric_spec_decision(labelled, "ab" * 32, None)
        self.assertEqual(caught.exception.code, "metric_spec_hash_unpinned")
        self.assertRegex(m10.FROZEN_METRIC_SPEC_SHA256, r"[0-9a-f]{64}")
        spec = m10.analysis._preflight().load_metric_spec()
        self.assertEqual(spec["freeze_status"], "frozen")
        self.assertTrue(spec["m10_draft_contract"]["labelled_frozen"])
        self.assertTrue(spec["m10_draft_contract"]["labelled_production_ready"])

        class DraftSeams(CompletingSeams):
            def configuration_hashes(self):
                self.events.append("frozen_configuration")
                return m10.production_metric_spec_decision(drafted, "ab" * 32, "ab" * 32)

            def open_eval_once(self):
                raise AssertionError("EVAL accessed")

        seams = DraftSeams(b"", [])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(m10.M10ContractError) as caught:
                m10.run_authorized_production(
                    os.path.join(temporary, "m10-draft-gate"),
                    m10.production_authorization(),
                    seams=seams,
                    fold=smoke_fold([]),
                    root=ROOT,
                )
        self.assertEqual(caught.exception.code, "metric_spec_unfrozen")
        self.assertEqual(seams.events, ["output_directory", "generated_input_hashes", "schedule", "frozen_configuration"])
        self.assertNotIn("eval", seams.events)

    def test_candidate_frozen_spec_checks_revisions_before_eval(self):
        pin = "cd" * 32
        consistent = frozen_candidate_spec()
        decision = m10.production_metric_spec_decision(consistent, pin, pin)
        self.assertEqual(decision["metric_spec_freeze_status"], "frozen")
        self.assertTrue(decision["metric_spec_production_ready"])
        self.assertEqual(
            m10.FROZEN_METRIC_SPEC_SHA256,
            m10._sha256_file(os.path.join(ROOT, m10.METRIC_SPEC_RELATIVE)),
        )
        on_disk = m10.analysis._preflight().load_metric_spec()
        self.assertEqual(on_disk["freeze_status"], "frozen")
        self.assertTrue(on_disk["m10_draft_contract"]["labelled_production_ready"])
        for field in ("code_revision", "config_revision"):
            mutated = frozen_candidate_spec()
            mutated["metrics"][0][field]["sha256"] = "ab" * 32

            class RevisionSeams(CompletingSeams):
                def configuration_hashes(self):
                    self.events.append("frozen_configuration")
                    return m10.production_metric_spec_decision(mutated, pin, pin)

                def open_eval_once(self):
                    self.events.append("eval")
                    raise AssertionError("EVAL accessed")

            seams = RevisionSeams(b"", [])
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(m10.M10ContractError) as caught:
                    m10.run_authorized_production(
                        os.path.join(temporary, "m10-revision-gate"),
                        m10.production_authorization(),
                        seams=seams,
                        fold=smoke_fold([]),
                        root=ROOT,
                    )
            self.assertEqual(caught.exception.code, "source_hash_mismatch")
            self.assertNotIn("eval", seams.events)
            self.assertEqual(seams.events, ["output_directory", "generated_input_hashes", "schedule", "frozen_configuration"])

    def _reject_before_eval(self, document, code):
        pin = "cd" * 32

        class RefuseEval(CompletingSeams):
            def configuration_hashes(self):
                self.events.append("frozen_configuration")
                return m10.production_metric_spec_decision(document, pin, pin)

            def open_eval_once(self):
                self.events.append("eval")
                raise AssertionError("EVAL accessed")

        seams = RefuseEval(b"", [])
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(m10.M10ContractError) as caught:
                m10.run_authorized_production(
                    os.path.join(temporary, "m10-freeze-gate"),
                    m10.production_authorization(),
                    seams=seams,
                    fold=smoke_fold([]),
                    root=ROOT,
                )
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("eval", seams.events)
        self.assertEqual(seams.events, ["output_directory", "generated_input_hashes", "schedule", "frozen_configuration"])
        on_disk = m10.analysis._preflight().load_metric_spec()
        self.assertEqual(on_disk["freeze_status"], "frozen")
        self.assertTrue(all(metric["freeze_status"] == "frozen" for metric in on_disk["metrics"]))
        self.assertEqual(on_disk["m10_draft_contract"]["document_status"], "frozen")
        self.assertTrue(on_disk["m10_draft_contract"]["labelled_production_ready"])
        self.assertEqual(m10.FROZEN_METRIC_SPEC_SHA256, m10._sha256_file(os.path.join(ROOT, m10.METRIC_SPEC_RELATIVE)))

    def test_partial_top_level_freeze_fails_before_eval(self):
        self._reject_before_eval(partial_top_level_spec(), "metric_row_unfrozen")

    def test_incomplete_frozen_candidate_fails_before_eval(self):
        draft_row = frozen_candidate_spec()
        draft_row["metrics"][0]["freeze_status"] = "draft"
        self._reject_before_eval(draft_row, "metric_row_unfrozen")
        draft_contract = frozen_candidate_spec()
        draft_contract["m10_draft_contract"]["document_status"] = "draft"
        self._reject_before_eval(draft_contract, "metric_spec_contract_unfrozen")
        unresolved = frozen_candidate_spec()
        unresolved["blocking_items"][0]["status"] = "unresolved"
        self._reject_before_eval(unresolved, "blocking_item_unresolved")
        wrong_role = frozen_candidate_spec()
        closeness = next(metric for metric in wrong_role["metrics"] if metric["scientific_role"] == "closeness")
        closeness["reference_role"] = "synthetic_eval_stand_in"
        self._reject_before_eval(wrong_role, "production_reference_role_refused")

    def test_stale_draft_wording_or_readiness_fails_before_eval(self):
        remains_draft = frozen_candidate_spec()
        remains_draft["m10_draft_contract"]["inactive_pathway_supersession"]["statement"] += " This specification remains draft."
        self._reject_before_eval(remains_draft, "metric_spec_draft_wording")
        not_ready = frozen_candidate_spec()
        not_ready["m10_draft_contract"]["inactive_pathway_supersession"]["statement"] = FROZEN_CANDIDATE_STATEMENT.replace(
            "is frozen and production-ready",
            "is frozen and not production-ready",
        )
        self._reject_before_eval(not_ready, "metric_spec_draft_wording")
        draft_readiness = frozen_candidate_spec()
        draft_readiness["m10_draft_contract"]["implementation_readiness"]["metric_specification"] = "draft_not_frozen"
        self._reject_before_eval(draft_readiness, "metric_spec_readiness_unfrozen")

    def test_changed_s6_parameters_or_s7_hashes_fail_before_eval(self):
        self.assertEqual(
            m10.FROZEN_S6_PARAMETER_SHA256,
            "8e2e20cfe1fa68ba53beec8df9aa9a64a9a2144dc9006fbbf5f8eb064f01df0f",
        )
        self.assertEqual(
            dict(m10.FROZEN_S7_CONFIGURATION_SHA256),
            {
                "config/global_s7b_partition.json": "c62553344748fc8c322869d68a46f69e653dee5641bf5f208dcb776e597c9550",
                "config/global_s7c_ft_train_validation.json": "e07f5af0de56beff4cefe75854493eaa3f696b9bc20c554ce2261033165f0873",
                "config/global_s7d_final_build.json": "abd3e1b29f422848aabd309ab0bb985731b9fb3941ddfbd2ec0f43d31a98b475",
            },
        )
        live = m10._s6_provenance(ROOT)
        captured = m10._code_hashes(ROOT)
        attestation = m10.assert_frozen_s6_and_s7(captured, live)
        self.assertFalse(live["artefact_present"])
        self.assertIsNone(live["artefact_sha256"])
        self.assertEqual(live["artefact_absence_classification"], "provenance_limitation")
        self.assertFalse(live["parameter_record_hash_substituted_for_artefact"])
        self.assertNotEqual(live["artefact_sha256"], live["parameter_sha256"])
        self.assertEqual(attestation["s6_parameter_sha256"], m10.FROZEN_S6_PARAMETER_SHA256)
        self.assertEqual(attestation["code_inventory_disposition"], "captured")
        self.assertEqual(attestation["metric_calculation_revisions"], "validated_through_metric_specification")
        self.assertEqual(attestation["production_runner_path"], "scripts/modelling/generator_eval_m10.py")
        self.assertEqual(attestation["production_runner_sha256"], captured["scripts/modelling/generator_eval_m10.py"])
        substituted = dict(live)
        substituted["artefact_sha256"] = substituted["parameter_sha256"]
        substituted["parameter_record_hash_substituted_for_artefact"] = True
        with self.assertRaises(m10.M10ContractError) as caught:
            m10.assert_frozen_s6_and_s7(captured, substituted)
        self.assertEqual(caught.exception.code, "s6_artefact_invalid")
        payload, _, _ = synthetic_eval_payload()
        rows = m10.adapt_frozen_ledgers(ledgers())["rows"]
        original_s6 = m10._s6_provenance
        original_code = m10._code_hashes
        cases = (
            ("s6_parameter_hash_mismatch", "parameter"),
            ("s7_configuration_hash_mismatch", "config/global_s7b_partition.json"),
            ("s7_configuration_hash_mismatch", "config/global_s7c_ft_train_validation.json"),
            ("s7_configuration_hash_mismatch", "config/global_s7d_final_build.json"),
        )
        for code, target in cases:

            class RefuseEval(CompletingSeams):
                def open_eval_once(self):
                    self.events.append("eval")
                    raise AssertionError("EVAL accessed")

            def patched_s6(root, target=target):
                value = dict(original_s6(root))
                if target == "parameter":
                    value["parameter_sha256"] = "ab" * 32
                return value

            def patched_code(root, target=target):
                value = dict(original_code(root))
                if target != "parameter":
                    value[target] = "ab" * 32
                return value

            seams = RefuseEval(payload, rows)
            m10._s6_provenance = patched_s6
            m10._code_hashes = patched_code
            try:
                with tempfile.TemporaryDirectory() as temporary:
                    with self.assertRaises(m10.M10ContractError) as caught:
                        m10.run_authorized_production(
                            os.path.join(temporary, "m10-s6-s7-gate"),
                            m10.production_authorization(),
                            seams=seams,
                            fold=deterministic_fold([]),
                            root=ROOT,
                        )
            finally:
                m10._s6_provenance = original_s6
                m10._code_hashes = original_code
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn("eval", seams.events)

    def test_train_summary_failure_never_calls_the_eval_seam(self):
        payload, _, _ = synthetic_eval_payload()
        rows = m10.adapt_frozen_ledgers(ledgers())["rows"]

        class RefuseEval(CompletingSeams):
            def open_eval_once(self):
                self.events.append("eval")
                raise AssertionError("EVAL accessed")

        seams = RefuseEval(payload, rows)
        original = m10.FROZEN_TRAIN_SUMMARIES
        m10.FROZEN_TRAIN_SUMMARIES = tuple((key, relative, "0" * 64) for key, relative, _expected in original)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(m10.M10ContractError) as caught:
                    m10.run_authorized_production(
                        os.path.join(temporary, "m10-train-gate"),
                        m10.production_authorization(),
                        seams=seams,
                        fold=deterministic_fold([]),
                        root=ROOT,
                    )
        finally:
            m10.FROZEN_TRAIN_SUMMARIES = original
        self.assertEqual(caught.exception.code, "train_hash_mismatch")
        self.assertNotIn("eval", seams.events)
        self.assertLess(seams.events.index("viennarna"), len(seams.events))
        self.assertEqual(
            seams.events,
            ["output_directory", "generated_input_hashes", "schedule", "frozen_configuration", "viennarna"],
        )

    def test_code_inventory_and_s6_provenance_fail_before_eval(self):
        payload, _, _ = synthetic_eval_payload()
        rows = m10.adapt_frozen_ledgers(ledgers())["rows"]

        class RefuseEval(CompletingSeams):
            def open_eval_once(self):
                self.events.append("eval")
                raise AssertionError("EVAL accessed")

        cases = (
            ("_code_hashes", "code_inventory_missing", "inventory missing"),
            ("_s6_provenance", "s6_provenance_missing", "s6 provenance missing"),
        )
        for name, code, detail in cases:
            seams = RefuseEval(payload, rows)
            original = getattr(m10, name)

            def fail(_root, detail=detail, code=code):
                raise m10.M10ContractError(code, detail)

            setattr(m10, name, fail)
            try:
                with tempfile.TemporaryDirectory() as temporary:
                    with self.assertRaises(m10.M10ContractError) as caught:
                        m10.run_authorized_production(
                            os.path.join(temporary, "m10-" + code),
                            m10.production_authorization(),
                            seams=seams,
                            fold=deterministic_fold([]),
                            root=ROOT,
                        )
            finally:
                setattr(m10, name, original)
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn("eval", seams.events)

    def test_synthetic_authorized_seam_publishes_the_section5_result_once(self):
        payload, expectations, eval_sequences = synthetic_eval_payload()
        self.assertEqual(expectations["short_cores"] + expectations["long_cores"], expectations["unique_cores"])
        rows = m10.adapt_frozen_ledgers(ledgers())["rows"]
        calls = []
        seams = CompletingSeams(payload, rows)
        opened = []
        real_open = builtins.open
        real_os_open = os.open
        original_hash = m10.FROZEN_EVAL_SHA256
        original_expectations = dict(m10.EVAL_EXPECTATIONS)
        original_reader = m10.read_frozen_eval_once

        def guarded_open(path, *args, **kwargs):
            text = os.fspath(path)
            opened.append(text)
            if os.path.basename(text) == "eval.csv":
                raise AssertionError(text)
            return real_open(path, *args, **kwargs)

        def guarded_os_open(path, flags, mode=0o777, *, dir_fd=None):
            text = os.fspath(path)
            opened.append(text)
            if os.path.basename(text) == "eval.csv":
                raise AssertionError(text)
            return real_os_open(path, flags, mode)

        def refuse_repository_eval(*args, **kwargs):
            raise AssertionError("repository EVAL reader was called")

        m10.FROZEN_EVAL_SHA256 = hashlib.sha256(payload).hexdigest()
        m10.EVAL_EXPECTATIONS = expectations
        m10.read_frozen_eval_once = refuse_repository_eval
        with tempfile.TemporaryDirectory() as temporary:
            builtins.open = guarded_open
            os.open = guarded_os_open
            try:
                output_dir = os.path.join(temporary, "m10-production")
                existing = os.path.join(temporary, "existing-run")
                os.mkdir(existing)
                with real_open(os.path.join(existing, "keep.txt"), "w", encoding="utf-8") as handle:
                    handle.write("keep")
                with self.assertRaises(m10.M10ContractError) as caught:
                    m10.run_authorized_production(
                        existing,
                        m10.production_authorization(),
                        seams=seams,
                        fold=deterministic_fold(calls),
                        root=ROOT,
                    )
                self.assertEqual(caught.exception.code, "output_exists")
                self.assertEqual(seams.eval_reads, 0)
                self.assertEqual(os.listdir(existing), ["keep.txt"])
                published = m10.run_authorized_production(
                    output_dir,
                    m10.production_authorization(),
                    seams=seams,
                    fold=deterministic_fold(calls),
                    root=ROOT,
                )
                self.assertEqual(seams.eval_reads, 1)
                self.assertEqual(seams.events.count("eval"), 1)
                self.assertLess(seams.events.index("viennarna"), seams.events.index("eval"))
                self.assertEqual(
                    [name for name in seams.events if name == "eval"],
                    ["eval"],
                )
                report_path = os.path.join(output_dir, "m10_sequence_free_report.json")
                derived_path = os.path.join(output_dir, "m10_derived_evidence.json")
                manifest_path = os.path.join(output_dir, "m10_run_manifest.json")
                sums_path = os.path.join(output_dir, "SHA256SUMS")
                with real_open(report_path, "rb") as handle:
                    report_bytes = handle.read()
                with real_open(derived_path, "rb") as handle:
                    derived_bytes = handle.read()
                with real_open(manifest_path, "rb") as handle:
                    manifest_bytes = handle.read()
                with real_open(sums_path, "rb") as handle:
                    sums_bytes = handle.read()
                report = json.loads(report_bytes.decode("utf-8"))
                derived = json.loads(derived_bytes.decode("utf-8"))
                manifest = json.loads(manifest_bytes.decode("utf-8"))
                self.assertEqual(published["eval_read_count"], 1)
                self.assertEqual(published["files"], ["m10_derived_evidence.json", "m10_sequence_free_report.json", "m10_run_manifest.json", "SHA256SUMS"])
                self.assertEqual(report["schema"], m10.PRODUCTION_SCHEMA)
                self.assertEqual(report["status"], "section5_calculation_complete")
                self.assertNotIn("synthetic_inactive_pathway", report_bytes.decode("utf-8"))
                self.assertTrue(report["eval_opened"])
                self.assertEqual(report["eval_read_count"], 1)
                self.assertTrue(report["viennarna_called"])
                self.assertEqual(report["viennarna_call"], "RNA.fold(sequence)")
                self.assertEqual(report["metric_spec"]["source"], "production_gate_attestation")
                self.assertNotEqual(report["metric_spec"]["freeze_status"], "draft")
                self.assertEqual(report["code_inventory_disposition"], "captured")
                self.assertEqual(report["metric_calculation_revisions"], "validated_through_metric_specification")
                self.assertEqual(report["production_runner_path"], "scripts/modelling/generator_eval_m10.py")
                self.assertEqual(
                    report["production_runner_sha256"],
                    report["code_and_configuration_hashes"]["scripts/modelling/generator_eval_m10.py"],
                )
                self.assertEqual(report["frozen_s6_parameter_sha256"], m10.FROZEN_S6_PARAMETER_SHA256)
                self.assertEqual(report["frozen_s7_configuration_sha256"], dict(m10.FROZEN_S7_CONFIGURATION_SHA256))
                self.assertFalse(report["s6_parameter_record_hash_substituted_for_artefact"])
                self.assertIsNone(report["s6_assignment"]["artefact_sha256"])
                self.assertEqual(report["s6_assignment"]["artefact_absence_classification"], "provenance_limitation")
                self.assertEqual(derived["layer"], "protected_derived_evidence")
                self.assertTrue(derived["contains_sequences"])
                self.assertEqual(report["layer"], "sequence_free_aggregate_report")
                self.assertFalse(report["contains_sequences"])
                self.assertFalse(manifest["contains_sequences"])
                self.assertEqual(stat.S_IMODE(os.stat(derived_path).st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(os.stat(report_path).st_mode), 0o644)
                self.assertEqual(stat.S_IMODE(os.stat(manifest_path).st_mode), 0o644)
                self.assertEqual(stat.S_IMODE(os.stat(sums_path).st_mode), 0o644)
                by_id = {record["record_id"]: record for record in derived["records"]}
                self.assertEqual(len(by_id), len(derived["records"]))
                b1_first = by_id["b1-a-0"]
                self.assertEqual(b1_first["record_id"], "b1-a-0")
                self.assertEqual(b1_first["checkpoint_identity"], "synthetic-checkpoint-b1")
                self.assertIsNone(b1_first["d1_training_seed"])
                self.assertEqual(b1_first["technical_block"], "A")
                self.assertEqual(b1_first["generation_seed"], 50043)
                self.assertEqual(b1_first["master_attempt_index"], 0)
                self.assertEqual(b1_first["within_batch_position"], 0)
                self.assertEqual(b1_first["invocation_index"], 0)
                self.assertEqual(b1_first["requested_length"], 8)
                self.assertEqual(b1_first["observed_length"], 8)
                self.assertEqual(b1_first["cleaning_status"], "cleaned")
                self.assertEqual(b1_first["cleaning_version"], "m9-biological-parser-v1")
                self.assertEqual(len(b1_first["source_artifact_sha256"]), 64)
                self.assertEqual(b1_first["fold_cache_disposition"], "computed_on_this_row")
                self.assertEqual(by_id["b1-a-1"]["fold_cache_disposition"], "reused_from_earlier_row")
                self.assertEqual(by_id["b1-a-2"]["fold_cache_disposition"], "not_folded")
                self.assertEqual(by_id["b1-a-2"]["cleaning_status"], "rejected")
                self.assertNotIn("fold_reused_from_distinct_sequence_cache", b1_first)
                self.assertEqual(by_id["d1-a-0"]["d1_training_seed"], 43)
                self.assertEqual(by_id["d1-b-0"]["d1_training_seed"], 44)
                self.assertEqual(by_id["b0-valid"]["b0_seed"], 4201)
                self.assertEqual(by_id["b0-valid"]["b0_chunk_id"], 1)
                self.assertIsNone(by_id["b0-valid"]["checkpoint_identity"])
                self.assertEqual(by_id["b0-empty"]["cleaning_status"], "not_applicable")
                self.assertIsNone(by_id["b0-empty"]["cleaning_version"])
                self.assertEqual(by_id["b2-valid"]["attempt_index"], 0)
                self.assertEqual(by_id["b2-valid"]["empirical_null_seed"], 7)
                self.assertIsNone(by_id["b2-valid"]["technical_block"])
                valid_rows = [row for row in rows if row["is_valid_canonical"] is True]
                unique_valid = len({row["sequence"] for row in valid_rows})
                dispositions = report["structure"]["fold_cache_disposition_counts"]
                self.assertEqual(dispositions["computed_on_this_row"], unique_valid)
                self.assertEqual(dispositions["reused_from_earlier_row"], len(valid_rows) - unique_valid)
                self.assertEqual(dispositions["not_folded"], len(rows) - len(valid_rows))
                self.assertEqual(
                    report["structure"]["population"]["generated_quantiles"],
                    "valid attempt rows with duplicate-attempt weighting",
                )
                self.assertTrue(report["structure"]["population"]["distinct_valid_sequences_folded_once"])
                self.assertTrue(report["structure"]["population"]["eval_unique_cores_once_each"])
                provenance = report["provenance_by_condition"]
                self.assertEqual(provenance["B1"]["checkpoint_identities"], ["synthetic-checkpoint-b1"])
                self.assertEqual(provenance["B1"]["d1_training_seeds"], [])
                self.assertEqual(provenance["B1"]["technical_blocks"], ["A", "B"])
                self.assertEqual(provenance["D1"]["d1_training_seeds"], [43, 44])
                self.assertEqual(provenance["B0"]["b0_chunk_ids"], [1])
                self.assertEqual(provenance["B0"]["requested_length"], "unavailable")
                self.assertEqual(provenance["B2"]["empirical_null_seeds"], [7])
                self.assertEqual(provenance["B1"]["cleaning_status_counts"]["cleaned"], 5)
                self.assertEqual(provenance["B1"]["cleaning_status_counts"]["rejected"], 1)
                provenance_text = json.dumps(provenance)
                for record_id in ("b1-a-0", "d1-a-0", "b0-valid", "b2-valid", "synthetic-eval-only"):
                    self.assertNotIn(record_id, provenance_text)
                self.assertFalse(provenance["B1"]["record_identifiers_emitted"])
                self.assertFalse(provenance["B1"]["sequences_emitted"])
                self.assertEqual(set(manifest), {"schema", "contains_sequences", "eval_read_count", "inputs", "code", "configuration", "environment", "outputs"})
                sequences = set(eval_sequences)
                sequences.update(row["sequence"] for row in rows if isinstance(row.get("sequence"), str))
                for sequence in sequences:
                    self.assertIn(sequence.encode("utf-8"), derived_bytes)
                    self.assertNotIn(sequence.encode("utf-8"), report_bytes)
                    self.assertNotIn(sequence.encode("utf-8"), manifest_bytes)
                    self.assertNotIn(sequence.encode("utf-8"), sums_bytes)
                self.assertNotIn(b"ACGTACGT", report_bytes)
                self.assertIn(b"ACGTACGT", derived_bytes)
                for record_id in ("b1-a-0", "d1-a-0", "synthetic-eval-only"):
                    self.assertNotIn(record_id, report_bytes.decode("utf-8"))
                self.assertEqual(len(calls), len(set(calls)))
                self.assertEqual(calls.count("CCCCCCCC"), 1)
                self.assertEqual(calls.count("ACGUACGU"), 1)
                self.assertIn("AAACCCGGG", calls)
                self.assertEqual(report["structure"]["distinct_fold_count"], len(calls))
                self.assertEqual(report["denominators"]["distinct_folded_sequences"], len(calls))
                self.assertEqual(report["denominators"]["reference_core_weight"], 1)
                self.assertEqual(report["reference"]["unique_core_count"], expectations["unique_cores"])
                self.assertTrue(all(core["weight"] == 1 and core["included_once"] is True for core in derived["eval_cores"]))
                self.assertEqual(len(derived["eval_cores"]), expectations["unique_cores"])
                b1 = report["metrics"]["by_condition"]["B1"]
                self.assertEqual(b1["raw_attempts"], 6)
                self.assertEqual(b1["valid_outputs"], 5)
                self.assertEqual(b1["unique_valid_outputs"], 2)
                self.assertEqual(report["exact_duplicate_diversity"]["by_condition"]["B1"]["duplicate_excess"], 3)
                self.assertEqual(report["structure"]["by_condition"]["B1"]["valid_row_denominator"], 5)
                self.assertEqual(report["structure"]["by_condition"]["B1"]["distinct_valid_sequence_count"], 2)
                self.assertIn("median", report["structure"]["by_condition"]["D1"]["mfe"])
                self.assertIn("median", report["structure"]["by_condition"]["D1"]["mfe_per_nt"])
                self.assertIn("median", report["structure"]["by_condition"]["D1"]["paired_fraction"])
                self.assertEqual(set(report["d1_by_training_seed"]), {"43", "44"})
                blocks = {block["block"]: block for block in report["matched_blocks"]}
                self.assertEqual(blocks["A"]["d1_training_seed"], 43)
                self.assertEqual(blocks["B"]["d1_training_seed"], 44)
                self.assertIn(report["directional_consistency"]["b1_versus_d1"]["agreement"], {"agreement", "disagreement"})
                self.assertFalse(report["directional_consistency"]["b1_versus_d1"]["agreement_is_a_score"])
                self.assertIn("A", report["directional_consistency"]["by_matched_block"])
                self.assertIn("B", report["directional_consistency"]["by_matched_block"])
                self.assertFalse(report["observed_range_across_training_seeds"]["is_confidence_interval"])
                self.assertIn("mfe_per_nt", report["observed_range_across_training_seeds"])
                self.assertEqual(report["observed_generation_seed_ranges"]["matched_blocks"]["A"]["minimum"], 50043)
                self.assertEqual(report["observed_generation_seed_ranges"]["matched_blocks"]["B"]["maximum"], 50044)
                b0_length = report["by_requested_length"]["B0"]
                self.assertEqual(b0_length["applicability"], "not_applicable")
                self.assertEqual(b0_length["requested_length"], "unavailable")
                self.assertEqual(b0_length["strata"], [])
                self.assertIsNone(report["metrics"]["by_condition"]["B0"]["exact_hit_rate"]["value"])
                self.assertEqual(report["b0_panel"]["requested_length"], "unavailable")
                for metric_id in (
                    "nearest_reference_normalized_edit_distance",
                    "nucleotide_total_variation_to_reference",
                    "dinucleotide_total_variation_to_reference",
                ):
                    self.assertIn(metric_id, report["closeness"]["by_condition"]["D1"])
                self.assertFalse(report["closeness"]["combined"])
                self.assertFalse(report["frozen_m9a_train"]["metrics_recomputed"])
                self.assertIn("43", report["frozen_m9a_train"]["exact"]["per_d1_training_seed"])
                self.assertIn("44", report["frozen_m9a_train"]["nearest"]["per_d1_training_seed"])
                found = []
                forbidden_keys(report, found)
                forbidden_keys(manifest, found)
                self.assertEqual(found, [])
                lines = sums_bytes.decode("utf-8").splitlines()
                self.assertEqual(
                    [line.split("  ", 1)[1] for line in lines],
                    ["m10_derived_evidence.json", "m10_sequence_free_report.json", "m10_run_manifest.json"],
                )
                self.assertNotIn("SHA256SUMS", [line.split("  ", 1)[1] for line in lines])
                for line in lines:
                    digest, name = line.split("  ", 1)
                    with real_open(os.path.join(output_dir, name), "rb") as handle:
                        self.assertEqual(digest, hashlib.sha256(handle.read()).hexdigest())
                self.assertEqual(manifest["outputs"]["m10_sequence_free_report.json"], hashlib.sha256(report_bytes).hexdigest())
                before = {}
                for name in os.listdir(output_dir):
                    with real_open(os.path.join(output_dir, name), "rb") as handle:
                        before[name] = hashlib.sha256(handle.read()).hexdigest()
                with self.assertRaises(m10.M10ContractError) as caught:
                    m10.run_authorized_production(
                        output_dir,
                        m10.production_authorization(),
                        seams=seams,
                        fold=deterministic_fold(calls),
                        root=ROOT,
                    )
                self.assertEqual(caught.exception.code, "output_exists")
                self.assertEqual(seams.eval_reads, 1)
                after = {}
                for name in os.listdir(output_dir):
                    with real_open(os.path.join(output_dir, name), "rb") as handle:
                        after[name] = hashlib.sha256(handle.read()).hexdigest()
                self.assertEqual(before, after)
                on_disk = m10.analysis._preflight().load_metric_spec()
                self.assertEqual(on_disk["freeze_status"], "frozen")
                self.assertTrue(on_disk["m10_draft_contract"]["labelled_production_ready"])
                self.assertEqual(
                    on_disk["m10_draft_contract"]["implementation_readiness"]["eval_opening"],
                    "not_yet_authorized",
                )
            finally:
                builtins.open = real_open
                os.open = real_os_open
        m10.FROZEN_EVAL_SHA256 = original_hash
        m10.EVAL_EXPECTATIONS = original_expectations
        m10.read_frozen_eval_once = original_reader
        self.assertFalse(any(os.path.basename(path) == "eval.csv" for path in opened))


if __name__ == "__main__":
    unittest.main()

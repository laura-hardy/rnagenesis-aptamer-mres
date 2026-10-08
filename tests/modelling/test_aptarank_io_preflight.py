"""Synthetic ARP-1 interface-contract tests.

No EVAL, REF, VALIDATION, TRAIN, production pool, or checkpoint is opened.
Sequences stay inside the synthetic fixtures.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_module():
    path = os.path.join(ROOT, "scripts/modelling/aptarank_io_preflight.py")
    spec = importlib.util.spec_from_file_location("aptarank_io_preflight", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


arp1 = load_module()

SEQUENCES = (
    "AAAACCCCGGGGUUUU",
    "ACACACACACACACAC",
    "UUUUGGGGAAAACCCC",
    "CGCGCGCGCGCGCGCG",
    "GGGGAAAACCCCUUUU",
    "CCCCCCCCCCCCCCCC",
    "AAAUUUCCCGGGAAAU",
)


def codes(error):
    return [item["code"] for item in error.errors]


def valid_parts():
    return arp1.load_bundled_parts()


def validate(parts, spec=None, spec_bytes=None):
    if spec is None or spec_bytes is None:
        loaded, loaded_bytes = arp1.load_spec()
        if spec is None:
            spec = loaded
        if spec_bytes is None:
            spec_bytes = loaded_bytes
    return arp1.validate_interface(parts, spec, spec_bytes)


HASH_FIELD_FOR_ROLE = {
    "candidate_upload": "candidate_upload_sha256",
    "reference_upload": "reference_upload_sha256",
    "shortlist_export": "shortlist_export_sha256",
    "failure_accounting": "failure_accounting_sha256",
    "expected_cell_manifest": "expected_cell_manifest_sha256",
}


def csv_data_row_count(payload):
    body = payload[len(arp1.UTF8_BOM):] if payload.startswith(arp1.UTF8_BOM) else payload
    rows = list(csv.reader(io.StringIO(body.decode("utf-8"), newline="")))
    return max(0, len(rows) - 1)


def replace(parts, role, payload):
    """Swap one synthetic part and refresh provenance cross-links to those bytes.

    Logical failure tests use this so a substituted fixture is not also a stale
    hash or a stale row count. Cross-link tests replace the provenance record
    itself and do not refresh it.
    """
    updated = dict(parts)
    updated[role] = payload
    if role not in HASH_FIELD_FOR_ROLE:
        return updated
    provenance = json.loads(updated["provenance"].decode("utf-8"))
    provenance[HASH_FIELD_FOR_ROLE[role]] = hashlib.sha256(payload).hexdigest()
    if role == "shortlist_export":
        provenance["exported_row_count"] = csv_data_row_count(payload)
    elif role == "failure_accounting":
        provenance["failed_row_count"] = len(json.loads(payload.decode("utf-8"))["failures"])
    elif role == "expected_cell_manifest":
        provenance["expected_row_count"] = len(json.loads(payload.decode("utf-8"))["expected_candidate_ids"])
    updated["provenance"] = json.dumps(provenance).encode("utf-8")
    return updated


def csv_table(payload):
    rows = list(csv.reader(io.StringIO(payload.decode("utf-8"), newline="")))
    return rows[0], rows[1:]


def csv_bytes(header, data):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(data)
    return buffer.getvalue().encode("utf-8")


def rows_as_dicts(payload):
    header, data = csv_table(payload)
    return [{column: row[index] for index, column in enumerate(header)} for row in data]


class SpecContractTests(unittest.TestCase):
    def test_shipped_spec_is_draft_and_unresolved(self):
        spec, spec_bytes = arp1.load_spec()
        self.assertEqual(spec["package_id"], "ARP-1")
        self.assertEqual(spec["schema_version"], "aptarank-io-arp1-draft-r3")
        self.assertEqual(spec["schema_version"], arp1.SCHEMA_VERSION)
        self.assertEqual(spec["provenance_record_schema"]["recorded_count_type"], arp1.RECORDED_COUNT_TYPE)
        self.assertIn("nonnegative JSON integers", spec["provenance_record_schema"]["recorded_count_type"])
        self.assertIn("Booleans and floats are excluded", spec["provenance_record_schema"]["recorded_count_type"])
        self.assertEqual(spec["status"], "draft")
        self.assertIs(spec["deployment_verified"], False)
        self.assertIs(spec["scientific_result"], False)
        self.assertIs(spec["combined_tier1_tier2_score"], False)
        self.assertEqual(spec["candidate_upload_column_order"], list(arp1.CANDIDATE_COLUMNS))
        self.assertEqual(spec["reference_upload_column_order"], list(arp1.REFERENCE_COLUMNS))
        self.assertEqual(len(spec["reference_upload_column_order"]), 5)
        self.assertEqual(spec["shortlist_export_column_order"], list(arp1.SHORTLIST_COLUMNS))
        self.assertEqual(spec["column_types"], arp1.COLUMN_TYPES)
        self.assertEqual(
            [item["id"] for item in spec["unresolved_interface_questions"]],
            list(arp1.UNRESOLVED_QUESTION_IDS),
        )
        for item in spec["unresolved_interface_questions"]:
            self.assertEqual(item["status"], "unresolved")
            self.assertIsNone(item["value"])
        raw_score = spec["raw_tier2_geometric_score"]
        self.assertEqual(raw_score["availability"], "unresolved")
        self.assertIsNone(raw_score["equation"])
        self.assertIsNone(raw_score["direction"])
        self.assertEqual(raw_score["comparison_scope"], "unresolved")
        self.assertIs(raw_score["absence_from_provisional_shortlist_is_not_definitional"], True)
        self.assertIs(raw_score["observed_in_provisional_shortlist_export"], False)
        self.assertIsNone(spec["control_bank"]["identifier"])
        self.assertIsNone(spec["control_bank"]["sha256"])
        self.assertIsNone(spec["control_bank"]["provenance"])
        self.assertEqual(spec["control_bank"]["status"], "unresolved")
        self.assertIs(spec["deployment_identity"]["deployment_verified"], False)
        self.assertIsNone(spec["synthetic_run_profiles"]["target_free_rigorous_style"]["preset_value"])
        self.assertIsNone(spec["synthetic_run_profiles"]["target_free_rigorous_style"]["shuffle_threshold"])
        self.assertEqual(spec["sha256_requirements"]["algorithm"], "SHA-256")
        self.assertIs(spec["sha256_requirements"]["provenance_record_includes_own_sha256"], False)
        self.assertEqual(spec["sha256_requirements"]["hashing_boundary"], arp1.PROVENANCE_HASH_BOUNDARY)
        self.assertIs(spec["provenance_record_schema"]["includes_own_sha256"], False)
        self.assertNotIn("provenance_record_sha256", spec["required_ui_provenance_capture_fields"])
        self.assertNotIn("provenance_record_sha256", spec["provenance_record_schema"]["required_keys"])
        self.assertTrue(set(spec["required_ui_provenance_capture_fields"]).issubset(spec["provenance_record_schema"]["required_keys"]))
        self.assertEqual(spec["column_types"]["reference_upload"]["target_pdb_id"], "nullable_uninterpreted_string")
        self.assertIn("unique-core", spec["rules"]["nullable_target_pdb_id"])
        self.assertIn("inventing structural evidence", spec["rules"]["nullable_target_pdb_id"])
        self.assertIn("encoding normalization", spec["rules"]["utf8_bom"])
        self.assertIn("not schema adaptation", spec["rules"]["utf8_bom"])
        self.assertIn("reviewed specification revision", spec["schema_change_policy"])
        self.assertIs(spec["interpretation_boundary"]["binding_interpretation"], False)
        self.assertIs(spec["interpretation_boundary"]["affinity_interpretation"], False)
        self.assertIs(spec["interpretation_boundary"]["selectivity_interpretation"], False)
        self.assertIs(spec["provisional_interface_evidence"]["validation_outcomes_reused"], False)
        self.assertIs(spec["provisional_interface_evidence"]["target_decisions_reused"], False)
        with open(os.path.join(ROOT, arp1.GOVERNING_PLAN_RELATIVE), "rb") as handle:
            plan_bytes = handle.read()
        self.assertEqual(hashlib.sha256(plan_bytes).hexdigest(), spec["governing_plan"]["sha256"])
        with open(arp1.spec_path(), "rb") as handle:
            self.assertEqual(hashlib.sha256(spec_bytes).hexdigest(), hashlib.sha256(handle.read()).hexdigest())

    def test_spec_rejects_verification_and_an_invented_equation(self):
        spec, spec_bytes = arp1.load_spec()
        verified = json.loads(spec_bytes)
        verified["deployment_verified"] = True
        with self.assertRaises(arp1.AptaRankIOError) as caught:
            arp1.validate_interface(valid_parts(), verified, json.dumps(verified).encode("utf-8"))
        self.assertEqual(caught.exception.code, "deployment_verified_refused")
        drifted = json.loads(spec_bytes)
        drifted["shortlist_export_column_order"] = ["sequence", "len", "shuffle", "compatibility", "aptamer-likeness", "candidate", "rank"]
        with self.assertRaises(arp1.AptaRankIOError) as caught:
            arp1.validate_spec_document(drifted)
        self.assertEqual(caught.exception.code, "spec_schema_drift")
        invented = json.loads(spec_bytes)
        invented["raw_tier2_geometric_score"]["equation"] = "invented"
        with self.assertRaises(arp1.AptaRankIOError) as caught:
            arp1.validate_spec_document(invented)
        self.assertEqual(caught.exception.code, "spec_invalid")

    def test_reconciliation_records_reviewer_supplied_hashes_without_claiming_inspection(self):
        path = os.path.join(ROOT, "docs/aptarank_arp1_interface_reconciliation.md")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("reviewer-supplied interface observations", text)
        self.assertIn("does not claim that Cursor inspected", text)
        self.assertIn("source directory was not clean", text)
        self.assertIn("not the complete provenance", text)
        self.assertIn("d583cd1710d8772b206e3ecb9308c0fb8fcd9bac6bcd02307766700eac56697a", text)
        self.assertIn("e16caf8660b0b38fd97fe47d5d9f102b5575be2511694316a9050ae7c0e872d6", text)
        self.assertIn("9b6a441f408ab850025bd8a275c3f5af5ec0968eb47471f595a899c1f30d7276", text)
        self.assertIn("6cacefa67b418297af03b9ba83a4e86fa586ed7bbbe9ea800d483b448649d43b", text)
        self.assertIn("3c2d02511a4876d30377aee682ea9ae60723317ac64e3c2881ecf4eff96590e3", text)
        self.assertIn("VALIDATION", text)
        self.assertIn("reviewed specification revision", text)
        self.assertIn("not a scientific result", text)
        self.assertIn("deployment_verified", text)
        self.assertIn("aptarank-io-arp1-draft-r3", text)
        self.assertIn("nonnegative JSON integers", text)
        self.assertIn("Booleans and floats are excluded", text)
        self.assertIn("invalid_row_count_type", text)
        self.assertIn("row_count_mismatch", text)
        self.assertIn("invalid_expected_candidate_id", text)
        self.assertIn("invalid_failure_candidate_id", text)
        self.assertIn("invalid_profile_id", text)
        self.assertIn("does not include sequence strings", text)
        self.assertIn("nullable uninterpreted string", text)
        self.assertIn("full unique-core REF calibration set", text)
        self.assertIn("without inventing structural evidence", text)
        self.assertIn("does not contain its own SHA-256", text)
        self.assertIn("self-referential", text)
        self.assertIn("encoding normalization, not schema adaptation", text)
        for sequence in SEQUENCES:
            self.assertNotIn(sequence, text)


class SuccessfulValidationTests(unittest.TestCase):
    def test_valid_target_free_bundle_passes_and_accounts_every_id_once(self):
        parts = valid_parts()
        report = validate(parts)
        text = arp1.render_report(report)
        encoded = json.dumps(report)
        for sequence in SEQUENCES:
            self.assertNotIn(sequence, encoded)
            self.assertNotIn(sequence, text)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["pass_fail"], "pass")
        self.assertEqual(report["spec_status"], "draft")
        self.assertIs(report["deployment_verified"], False)
        self.assertIs(report["scientific_result"], False)
        self.assertIs(report["technical_preflight"], True)
        self.assertIs(report["combined_tier1_tier2_score"], False)
        self.assertIs(report["binding_interpretation"], False)
        self.assertIs(report["affinity_interpretation"], False)
        self.assertIs(report["selectivity_interpretation"], False)
        self.assertIs(report["join_uses_row_position"], False)
        self.assertEqual(report["join_key"], "candidate_id")
        self.assertEqual(report["schemas"]["candidate_upload"], ["id", "sequence"])
        self.assertEqual(
            report["schemas"]["reference_upload"],
            ["id", "sequence", "target_name", "target_pdb_id", "source_reference"],
        )
        self.assertEqual(
            report["schemas"]["shortlist_export"],
            ["rank", "candidate", "aptamer-likeness", "compatibility", "shuffle", "len", "sequence"],
        )
        self.assertNotIn("raw_tier2_geometric_score", report["schemas"]["shortlist_export"])
        self.assertEqual(report["raw_tier2_score_availability"], "unresolved")
        self.assertIsNone(report["raw_tier2_equation"])
        self.assertIsNone(report["raw_tier2_direction"])
        self.assertEqual(report["raw_tier2_comparison_scope"], "unresolved")
        self.assertIs(report["raw_tier2_absence_from_provisional_shortlist_is_not_definitional"], True)
        self.assertIsNone(report["control_bank_identifier"])
        self.assertIsNone(report["control_bank_hash"])
        self.assertIsNone(report["control_bank_provenance"])
        self.assertEqual(report["control_bank_status"], "unresolved")
        self.assertIsNone(report["preset_value"])
        self.assertIsNone(report["deployment_version"])
        self.assertEqual(report["row_accounting"]["candidate_upload_rows"], 3)
        self.assertEqual(report["row_accounting"]["reference_upload_rows"], 2)
        self.assertEqual(report["row_accounting"]["expected_candidates"], 3)
        self.assertEqual(report["row_accounting"]["exported_rows"], 2)
        self.assertEqual(report["row_accounting"]["failed_rows"], 1)
        self.assertEqual(report["row_accounting"]["missing_candidate_ids"], 0)
        self.assertEqual(report["row_accounting"]["extra_exported_ids"], 0)
        self.assertEqual(report["row_accounting"]["silent_drops"], 0)
        self.assertEqual(report["row_accounting"]["rows_imputed_as_zero"], 0)
        self.assertIs(report["impute_missing_as_zero"], False)
        self.assertIs(report["candidates_accounted_exactly_once"], True)
        dispositions = report["candidate_dispositions"]
        self.assertEqual([item["candidate_id"] for item in dispositions], ["opaque-01", "opaque-02", "opaque-03"])
        self.assertEqual([item["disposition"] for item in dispositions], ["exported", "exported", "technical_failure"])
        self.assertEqual(len([item["candidate_id"] for item in dispositions]), len({item["candidate_id"] for item in dispositions}))
        failed = [item for item in dispositions if item["disposition"] == "technical_failure"]
        self.assertEqual(len(failed), 1)
        self.assertTrue(failed[0]["failure_reason_present"])
        self.assertNotIn("opaque-03", report["export_candidate_id_order"])
        for role, payload in parts.items():
            self.assertEqual(report["sha256"][role], hashlib.sha256(payload).hexdigest())
        provenance = json.loads(parts["provenance"].decode("utf-8"))
        self.assertNotIn("provenance_record_sha256", provenance)
        self.assertIs(report["provenance_record_includes_own_sha256"], False)
        self.assertEqual(report["provenance_hash_boundary"], arp1.PROVENANCE_HASH_BOUNDARY)
        self.assertIn(arp1.PROVENANCE_HASH_BOUNDARY, text)
        for field, role in arp1.RECORDED_HASH_FIELDS:
            self.assertEqual(provenance[field], hashlib.sha256(parts[role]).hexdigest())
        self.assertEqual(provenance["expected_row_count"], 3)
        self.assertEqual(provenance["exported_row_count"], 2)
        self.assertEqual(provenance["failed_row_count"], 1)
        self.assertIsNone(provenance["structure_sha256"])
        self.assertIs(provenance["deployment_verified"], False)
        self.assertIs(provenance["ui_capture_complete"], False)
        self.assertEqual(provenance["warnings"], [])
        self.assertEqual(provenance["rerun_lineage"], [])
        for field in arp1.TARGET_SENTINEL_FIELDS:
            self.assertEqual(provenance[field], arp1.TARGET_FREE_SENTINEL)
        for field in arp1.NULL_PROVENANCE_FIELDS:
            self.assertIsNone(provenance[field])
        self.assertFalse(report["data_access"]["eval_loaded"])
        self.assertFalse(report["data_access"]["ref_loaded"])
        self.assertFalse(report["data_access"]["validation_loaded"])
        self.assertFalse(report["data_access"]["train_loaded"])
        self.assertFalse(report["data_access"]["production_pools_loaded"])
        self.assertFalse(report["data_access"]["checkpoints_loaded"])
        self.assertEqual(report["data_access"]["statement"], arp1.NO_PROTECTED_STATEMENT)
        self.assertFalse(report["protected_or_production_data_loaded"])
        self.assertEqual(report["protected_or_production_statement"], arp1.NO_PRODUCTION_STATEMENT)
        self.assertTrue(all(item["status"] == "unresolved" and item["value"] is None for item in report["unresolved_interface_questions"]))
        forbidden = {"combined_score", "composite_score", "aggregate_score", "tier1_tier2_score"}
        self.assertTrue(forbidden.isdisjoint(_keys(report)))
        self.assertTrue(forbidden.isdisjoint(_keys(arp1.load_spec()[0])))

    def test_reordered_export_joins_by_candidate_id_not_row_position(self):
        parts = valid_parts()
        header, data = csv_table(parts["shortlist_export"])
        reversed_rows = list(reversed(data))
        report = validate(replace(parts, "shortlist_export", csv_bytes(header, reversed_rows)))
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["export_candidate_id_order"], ["opaque-02", "opaque-01"])
        self.assertNotEqual(report["export_candidate_id_order"], report["upload_candidate_id_order"][:2])
        self.assertEqual(
            [item["candidate_id"] for item in report["candidate_dispositions"]],
            ["opaque-01", "opaque-02", "opaque-03"],
        )
        upload_rows = rows_as_dicts(parts["candidate_upload"])
        export_rows = [{column: row[index] for index, column in enumerate(header)} for row in reversed_rows]
        self.assertEqual(arp1.sequence_matches_by_id(upload_rows, export_rows), [True, True])
        position_matches = [
            upload_rows[index]["sequence"] == export_rows[index]["sequence"] for index in range(len(export_rows))
        ]
        self.assertIn(False, position_matches)
        self.assertIs(report["join_uses_row_position"], False)

    def test_manifest_order_does_not_replace_the_id_join(self):
        parts = valid_parts()
        manifest = json.loads(parts["expected_cell_manifest"].decode("utf-8"))
        manifest["expected_candidate_ids"] = list(reversed(manifest["expected_candidate_ids"]))
        report = validate(replace(parts, "expected_cell_manifest", json.dumps(manifest).encode("utf-8")))
        self.assertEqual(report["status"], "passed")
        self.assertEqual(
            [item["candidate_id"] for item in report["candidate_dispositions"]],
            ["opaque-03", "opaque-02", "opaque-01"],
        )
        self.assertEqual(report["export_candidate_id_order"], ["opaque-01", "opaque-02"])
        self.assertEqual(
            [item["disposition"] for item in report["candidate_dispositions"]],
            ["technical_failure", "exported", "exported"],
        )

    def test_empty_inputs_have_explicit_zero_accounting(self):
        parts = arp1.load_bundled_parts(arp1.EMPTY_FIXTURES)
        report = validate(parts)
        for field in arp1.ROW_ACCOUNTING_FIELDS:
            self.assertEqual(report["row_accounting"][field], 0, field)
        self.assertEqual(report["candidate_dispositions"], [])
        self.assertEqual(report["export_candidate_id_order"], [])
        self.assertEqual(report["upload_candidate_id_order"], [])
        self.assertIs(report["candidates_accounted_exactly_once"], True)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["raw_tier2_score_availability"], "unresolved")
        self.assertIs(report["deployment_verified"], False)
        self.assertEqual(report["row_accounting"]["expected_candidates"], 0)
        self.assertEqual(report["row_accounting"]["silent_drops"], 0)
        provenance = json.loads(parts["provenance"].decode("utf-8"))
        self.assertEqual(provenance["expected_row_count"], 0)
        self.assertEqual(provenance["exported_row_count"], 0)
        self.assertEqual(provenance["failed_row_count"], 0)
        self.assertIsNone(provenance["structure_sha256"])
        for field, role in arp1.RECORDED_HASH_FIELDS:
            self.assertEqual(provenance[field], hashlib.sha256(parts[role]).hexdigest())


class FailClosedTests(unittest.TestCase):
    def assert_code(self, parts, code, exact=True):
        with self.assertRaises(arp1.AptaRankIOError) as caught:
            validate(parts)
        found = codes(caught.exception)
        if exact:
            self.assertEqual(found, [code])
        else:
            self.assertIn(code, found)
        for item in caught.exception.errors:
            for sequence in SEQUENCES:
                self.assertNotIn(sequence, item["detail"])
        return caught.exception

    def test_duplicate_missing_and_unexpected_candidate_ids(self):
        parts = valid_parts()
        self.assert_code(replace(parts, "candidate_upload", arp1.load_fixture_bytes("duplicate_candidate_id.csv")), "duplicate_candidate_id")
        self.assert_code(replace(parts, "shortlist_export", arp1.load_fixture_bytes("missing_candidate_shortlist.csv")), "missing_candidate_id")
        self.assert_code(replace(parts, "shortlist_export", arp1.load_fixture_bytes("unexpected_candidate_shortlist.csv")), "unexpected_candidate_id")
        header, data = csv_table(parts["shortlist_export"])
        duplicated = list(data[0])
        duplicated[0] = "3"
        data.append(duplicated)
        self.assert_code(replace(parts, "shortlist_export", csv_bytes(header, data)), "duplicate_exported_id")

    def test_silent_drop_is_rejected_and_a_failure_needs_a_reason(self):
        parts = valid_parts()
        error = self.assert_code(
            replace(parts, "failure_accounting", arp1.load_fixture_bytes("empty_failure_accounting.json")),
            "missing_candidate_id",
        )
        self.assertIn("neither exported nor explicitly failed", error.detail)
        self.assertNotIn("zero", error.detail.lower())
        self.assert_code(replace(parts, "failure_accounting", arp1.load_fixture_bytes("failure_missing_reason.json")), "missing_failure_reason")

    def test_sequence_length_schema_and_score_failures(self):
        parts = valid_parts()
        self.assert_code(replace(parts, "shortlist_export", arp1.load_fixture_bytes("silently_changed_sequence_shortlist.csv")), "sequence_changed")
        self.assert_code(replace(parts, "shortlist_export", arp1.load_fixture_bytes("exported_length_mismatch_shortlist.csv")), "length_mismatch")
        self.assert_code(replace(parts, "candidate_upload", arp1.load_fixture_bytes("wrong_column_order.csv")), "schema_mismatch")
        self.assertIn("will not adapt", self.assert_code(replace(parts, "candidate_upload", arp1.load_fixture_bytes("wrong_column_order.csv")), "schema_mismatch").detail)
        header, data = csv_table(parts["shortlist_export"])
        swapped_header = ["sequence", "len", "shuffle", "compatibility", "aptamer-likeness", "candidate", "rank"]
        swapped_data = [list(reversed(row)) for row in data]
        error = self.assert_code(replace(parts, "shortlist_export", csv_bytes(swapped_header, swapped_data)), "schema_mismatch")
        self.assertIn("will not adapt", error.detail)
        self.assert_code(replace(parts, "shortlist_export", arp1.load_fixture_bytes("malformed_aptamer_likeness_shortlist.csv")), "malformed_aptamer_likeness")
        self.assert_code(replace(parts, "shortlist_export", arp1.load_fixture_bytes("nonfinite_aptamer_likeness_shortlist.csv")), "nonfinite_aptamer_likeness")
        for token in ("inf", "-Infinity", "1e309"):
            mutated = [list(row) for row in data]
            mutated[0][header.index("aptamer-likeness")] = token
            self.assert_code(replace(parts, "shortlist_export", csv_bytes(header, mutated)), "nonfinite_aptamer_likeness")
        self.assert_code(replace(parts, "shortlist_export", arp1.load_fixture_bytes("invalid_shuffle_shortlist.csv")), "invalid_shuffle")
        self.assert_code(
            replace(parts, "shortlist_export", arp1.load_fixture_bytes("invalid_target_free_compatibility_shortlist.csv")),
            "invalid_compatibility",
        )

    def test_alphabet_empty_id_reference_rules_and_extra_column(self):
        parts = valid_parts()
        header, data = csv_table(parts["candidate_upload"])
        lowered = [list(row) for row in data]
        lowered[0][1] = lowered[0][1].lower()
        self.assert_code(replace(parts, "candidate_upload", csv_bytes(header, lowered)), "sequence_alphabet", exact=False)
        thymine = [list(row) for row in data]
        thymine[0][1] = "T" * 16
        self.assert_code(replace(parts, "candidate_upload", csv_bytes(header, thymine)), "sequence_alphabet", exact=False)
        blank = [list(row) for row in data]
        blank[0][0] = ""
        self.assert_code(replace(parts, "candidate_upload", csv_bytes(header, blank)), "empty_id", exact=False)
        reference_header, reference_rows = csv_table(parts["reference_upload"])
        self.assertEqual(reference_header, ["id", "sequence", "target_name", "target_pdb_id", "source_reference"])
        duplicated = list(reference_rows)
        duplicated.append(list(reference_rows[0]))
        self.assert_code(replace(parts, "reference_upload", csv_bytes(reference_header, duplicated)), "duplicate_reference_id")
        extra_header = list(header) + ["combined_score"]
        extra_rows = [list(row) + ["1"] for row in data]
        self.assert_code(replace(parts, "candidate_upload", csv_bytes(extra_header, extra_rows)), "schema_mismatch")

    def test_blank_target_pdb_id_passes_and_whitespace_does_not(self):
        parts = valid_parts()
        payload = arp1.load_fixture_bytes("blank_target_pdb_id_reference.csv")
        header, rows = csv_table(payload)
        self.assertEqual(header, ["id", "sequence", "target_name", "target_pdb_id", "source_reference"])
        pdb_index = header.index("target_pdb_id")
        self.assertEqual(rows[0][pdb_index], "")
        self.assertEqual(rows[1][pdb_index], "synthetic-pdb-token-0001")
        self.assertNotIn(b"not_entered_target_free", payload)
        report = validate(replace(parts, "reference_upload", payload))
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["row_accounting"]["reference_upload_rows"], 2)
        self.assertEqual(report["sha256"]["reference_upload"], hashlib.sha256(payload).hexdigest())
        encoded = json.dumps(report)
        for sequence in SEQUENCES:
            self.assertNotIn(sequence, encoded)
        reference_header, reference_rows = csv_table(parts["reference_upload"])
        name_index = reference_header.index("target_name")
        source_index = reference_header.index("source_reference")
        blank_name = [list(row) for row in reference_rows]
        blank_name[0][name_index] = ""
        self.assert_code(replace(parts, "reference_upload", csv_bytes(reference_header, blank_name)), "empty_reference_field")
        blank_source = [list(row) for row in reference_rows]
        blank_source[0][source_index] = ""
        self.assert_code(replace(parts, "reference_upload", csv_bytes(reference_header, blank_source)), "empty_reference_field")
        for token in (" ", "   ", "\t", " synthetic-pdb-token-0000", "synthetic-pdb-token-0000 "):
            mutated = [list(row) for row in reference_rows]
            mutated[0][pdb_index] = token
            self.assert_code(
                replace(parts, "reference_upload", csv_bytes(reference_header, mutated)),
                "invalid_target_pdb_id",
            )

    def test_provenance_cross_links_fail_closed(self):
        parts = valid_parts()
        provenance = json.loads(parts["provenance"].decode("utf-8"))
        upload_fields = ("candidate_upload_sha256", "reference_upload_sha256")
        download_fields = (
            "shortlist_export_sha256",
            "failure_accounting_sha256",
            "expected_cell_manifest_sha256",
        )
        for field in upload_fields + download_fields:
            mutated = dict(provenance)
            mutated[field] = "0" * 64
            self.assertNotEqual(mutated[field], provenance[field])
            self.assert_code(
                replace(parts, "provenance", json.dumps(mutated).encode("utf-8")),
                "fixture_hash_mismatch",
            )
        for field in ("expected_row_count", "exported_row_count", "failed_row_count"):
            mutated = dict(provenance)
            mutated[field] = provenance[field] + 1
            self.assert_code(
                replace(parts, "provenance", json.dumps(mutated).encode("utf-8")),
                "row_count_mismatch",
            )
        mutated = dict(provenance)
        del mutated["numbering"]
        self.assert_code(
            replace(parts, "provenance", json.dumps(mutated).encode("utf-8")),
            "missing_provenance_field",
        )
        mutated = dict(provenance)
        mutated["provenance_record_sha256"] = hashlib.sha256(parts["provenance"]).hexdigest()
        self.assert_code(
            replace(parts, "provenance", json.dumps(mutated).encode("utf-8")),
            "unexpected_provenance_field",
        )

    def test_leading_bom_is_stripped_for_decoding_and_original_bytes_are_hashed(self):
        bom_files = (
            ("candidate_upload", "bom_candidate_upload.csv"),
            ("reference_upload", "bom_reference_upload.csv"),
            ("shortlist_export", "bom_shortlist_export.csv"),
        )
        updated = valid_parts()
        originals = {}
        for role, name in bom_files:
            payload = arp1.load_fixture_bytes(name)
            self.assertTrue(payload.startswith(arp1.UTF8_BOM))
            self.assertNotIn(arp1.UTF8_BOM, payload[len(arp1.UTF8_BOM):])
            originals[role] = payload
            updated = replace(updated, role, payload)
        report = validate(updated)
        self.assertEqual(report["status"], "passed")
        encoded = json.dumps(report)
        text = arp1.render_report(report)
        for sequence in SEQUENCES:
            self.assertNotIn(sequence, encoded)
            self.assertNotIn(sequence, text)
        for role, payload in originals.items():
            original_hash = hashlib.sha256(payload).hexdigest()
            stripped_hash = hashlib.sha256(payload[len(arp1.UTF8_BOM):]).hexdigest()
            self.assertNotEqual(original_hash, stripped_hash)
            self.assertEqual(report["sha256"][role], original_hash)
        header, data = csv_table(arp1.load_fixture_bytes("wrong_column_order.csv"))
        bom_wrong = arp1.UTF8_BOM + csv_bytes(header, data)
        error = self.assert_code(replace(valid_parts(), "candidate_upload", bom_wrong), "schema_mismatch")
        self.assertIn("will not adapt", error.detail)
        parts = valid_parts()
        candidate = parts["candidate_upload"]
        split_at = candidate.index(b"\n") + 1
        misplaced = candidate[:split_at] + arp1.UTF8_BOM + candidate[split_at:]
        self.assert_code(replace(parts, "candidate_upload", misplaced), "unexpected_bom")
        doubled = arp1.UTF8_BOM + arp1.UTF8_BOM + candidate
        self.assert_code(replace(parts, "candidate_upload", doubled), "unexpected_bom")

    def test_provenance_cannot_resolve_the_open_deployment_questions(self):
        parts = valid_parts()
        provenance = json.loads(parts["provenance"].decode("utf-8"))
        provenance["raw_tier2_equation"] = "invented"
        self.assert_code(replace(parts, "provenance", json.dumps(provenance).encode("utf-8")), "unresolved_field_must_stay_unresolved")
        provenance = json.loads(parts["provenance"].decode("utf-8"))
        provenance["deployment_verified"] = True
        self.assert_code(replace(parts, "provenance", json.dumps(provenance).encode("utf-8")), "deployment_verified_refused")
        provenance = json.loads(parts["provenance"].decode("utf-8"))
        provenance["canonical_target"] = "synthetic-target-decision"
        self.assert_code(replace(parts, "provenance", json.dumps(provenance).encode("utf-8")), "target_value_not_allowed_in_profile")
        provenance = json.loads(parts["provenance"].decode("utf-8"))
        provenance["structure_or_pdb"] = "synthetic-structure"
        self.assert_code(replace(parts, "provenance", json.dumps(provenance).encode("utf-8")), "target_value_not_allowed_in_profile")
        provenance = json.loads(parts["provenance"].decode("utf-8"))
        provenance["structure_sha256"] = "ab" * 32
        self.assert_code(replace(parts, "provenance", json.dumps(provenance).encode("utf-8")), "target_value_not_allowed_in_profile")

    def test_row_counts_require_exact_nonnegative_integers(self):
        counted = (
            ("expected_row_count", 3),
            ("exported_row_count", 2),
            ("failed_row_count", 1),
        )
        parts = valid_parts()
        provenance = json.loads(parts["provenance"].decode("utf-8"))
        for field, count in counted:
            self.assertIs(type(provenance[field]), int)
            self.assertEqual(provenance[field], count)
            confirmed = dict(provenance)
            confirmed[field] = count
            report = validate(replace(parts, "provenance", json.dumps(confirmed).encode("utf-8")))
            self.assertEqual(report["status"], "passed")
            matching_float = float(count)
            self.assertEqual(matching_float, count)
            for value in (True, False, matching_float, str(count), -1):
                mutated = dict(provenance)
                mutated[field] = value
                self.assert_code(
                    replace(parts, "provenance", json.dumps(mutated).encode("utf-8")),
                    "invalid_row_count_type",
                )
        empty = arp1.load_bundled_parts(arp1.EMPTY_FIXTURES)
        empty_provenance = json.loads(empty["provenance"].decode("utf-8"))
        for field in ("expected_row_count", "exported_row_count", "failed_row_count"):
            self.assertEqual(empty_provenance[field], 0)
            self.assertIs(type(empty_provenance[field]), int)
            confirmed = dict(empty_provenance)
            confirmed[field] = 0
            report = validate(replace(empty, "provenance", json.dumps(confirmed).encode("utf-8")))
            self.assertEqual(report["status"], "passed")
            for value in (False, True, 0.0, "0", -1):
                mutated = dict(empty_provenance)
                mutated[field] = value
                self.assert_code(
                    replace(empty, "provenance", json.dumps(mutated).encode("utf-8")),
                    "invalid_row_count_type",
                )

    def test_malformed_json_identifiers_are_rejected_before_reconciliation(self):
        malformed = (
            {"nested": SEQUENCES[0]},
            [SEQUENCES[0]],
            None,
            True,
            False,
        )
        parts = valid_parts()
        manifest = json.loads(parts["expected_cell_manifest"].decode("utf-8"))
        manifest["expected_candidate_ids"] = list(malformed)
        error = self.assert_code(
            replace(parts, "expected_cell_manifest", json.dumps(manifest).encode("utf-8")),
            "invalid_expected_candidate_id",
            exact=False,
        )
        self.assertEqual(codes(error), ["invalid_expected_candidate_id"] * len(malformed))
        self.assertIsInstance(error, arp1.AptaRankIOError)
        for value in malformed:
            fresh = json.loads(parts["expected_cell_manifest"].decode("utf-8"))
            fresh["expected_candidate_ids"] = [value]
            caught = self.assert_code(
                replace(parts, "expected_cell_manifest", json.dumps(fresh).encode("utf-8")),
                "invalid_expected_candidate_id",
            )
            self.assertIsInstance(caught, arp1.AptaRankIOError)
            failure = json.loads(parts["failure_accounting"].decode("utf-8"))
            failure["failures"] = [{"candidate_id": value, "reason": "synthetic technical failure"}]
            caught = self.assert_code(
                replace(parts, "failure_accounting", json.dumps(failure).encode("utf-8")),
                "invalid_failure_candidate_id",
            )
            self.assertIsInstance(caught, arp1.AptaRankIOError)
            for role, label in (
                ("expected_cell_manifest", "expected-cell manifest"),
                ("failure_accounting", "failure accounting"),
                ("provenance", "provenance"),
            ):
                document = json.loads(parts[role].decode("utf-8"))
                document["profile_id"] = value
                caught = self.assert_code(
                    replace(parts, role, json.dumps(document).encode("utf-8")),
                    "invalid_profile_id",
                )
                self.assertIsInstance(caught, arp1.AptaRankIOError)
                self.assertIn(label, caught.detail)


class CommandLineTests(unittest.TestCase):
    def run_main(self, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = arp1.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_rejects_paths_unlock_flags_and_other_arguments(self):
        for args in (
            ["eval.csv"],
            ["--unlock"],
            ["--eval-unlock"],
            ["--path", "tests/modelling/fixtures/aptarank_arp1/valid_candidate_upload.csv"],
            ["tests/modelling/fixtures/aptarank_arp1/valid_candidate_upload.csv"],
            ["--help"],
            ["-h"],
            ["--production"],
        ):
            code, stdout, stderr = self.run_main(args)
            self.assertEqual(code, 2, args)
            self.assertEqual(stdout, "")
            self.assertIn("arp1_cli_rejected", stderr)
            for sequence in SEQUENCES:
                self.assertNotIn(sequence, stderr)

    def test_no_argument_run_uses_only_synthetic_fixtures(self):
        code, stdout, stderr = self.run_main([])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("spec_status: draft", stdout)
        self.assertIn("deployment_verified: false", stdout)
        self.assertIn("raw_tier2_score_availability: unresolved", stdout)
        self.assertIn("raw_tier2_equation: null", stdout)
        self.assertIn("raw_tier2_direction: null", stdout)
        self.assertIn(arp1.NO_PROTECTED_STATEMENT, stdout)
        self.assertIn(arp1.NO_PRODUCTION_STATEMENT, stdout)
        self.assertIn("No protected or production data were loaded.", stdout)
        self.assertIn(arp1.TECHNICAL_NOT_SCIENTIFIC, stdout)
        self.assertIn("scientific_result: false", stdout)
        self.assertIn("combined_tier1_tier2_score: false", stdout)
        for sequence in SEQUENCES:
            self.assertNotIn(sequence, stdout)
        with self.assertRaises(arp1.AptaRankIOError) as caught:
            arp1.load_fixture_bytes("eval.csv")
        self.assertEqual(caught.exception.code, "fixture_name_refused")
        with self.assertRaises(arp1.AptaRankIOError) as caught:
            arp1.load_fixture_bytes("../eval.csv")
        self.assertEqual(caught.exception.code, "fixture_name_refused")


def _keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


if __name__ == "__main__":
    unittest.main()

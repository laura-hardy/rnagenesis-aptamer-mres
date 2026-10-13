"""Synthetic-only checks for the M9C-1 reference-upload policy.

Sequences, identities, and target labels in this module are invented. The
tests do not open REF, EVAL, or a production candidate source.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)

import aptarank_reference_upload as upload

CONTRACT_SHA256 = "980e7d1b9ce8a8c4c86a88dc99df280f05485b7c4fb2fdfd600fdea7a0665f9e"
CORE_A = "ACGUACGUACGUACGUACGU"
CORE_B = "GCAUGCAUGCAUGCAUGCAU"
CORE_C = "ACGU"


def _read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _clustered_columns():
    dedup = ast.parse(_read_text(os.path.join(ROOT, "scripts", "data_preparation", "adapters", "s5_exact_dedup.py")))
    columns = None
    for node in dedup.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "CORPUS_DEDUP_COLUMNS":
            columns = list(ast.literal_eval(node.value))
    cluster = ast.parse(_read_text(os.path.join(ROOT, "scripts", "data_preparation", "adapters", "s5_final_clustering.py")))
    extra = None
    for node in cluster.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "CORPUS_CLUSTERED_FINAL_COLUMNS":
            extra = [elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)]
    return columns + extra


def _document():
    return upload.load_pinned_contract()


def _source_bytes(records, *, header=None, digest_for=None):
    document = _document()
    columns = list(document["source_schema"]["columns"] if header is None else header)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for record in records:
        row = {column: "" for column in columns}
        row.update(record)
        core = row.get("sequence_core", "")
        if digest_for is not None and "sequence_core_sha256" in row:
            row["sequence_core_sha256"] = digest_for
        elif core and "sequence_core_sha256" in row and row["sequence_core_sha256"] == "":
            row["sequence_core_sha256"] = hashlib.sha256(core.encode("utf-8")).hexdigest()
        if "partition" in row and row["partition"] == "":
            row["partition"] = "REF"
        writer.writerow({column: row[column] for column in columns})
    return buffer.getvalue().encode("utf-8")


def _identity(number, core, **overrides):
    row = {
        "scientific_identity_id": "S5I_synthetic_%02d" % number,
        "sequence_core": core,
        "canonical_target_name": "Synthetic target %02d" % number,
        "pdb_id": "",
        "publication": "Synthetic publication %02d" % number,
        "partition": "REF",
    }
    row.update(overrides)
    return row


def _parsed_upload(payload):
    text = payload.decode("utf-8")
    table = list(csv.reader(io.StringIO(text, newline="")))
    header, rows = table[0], table[1:]
    return header, [dict(zip(header, row)) for row in rows]


class ReferenceUploadTests(unittest.TestCase):
    def test_contract_pins_and_status(self):
        contract_path = os.path.join(ROOT, upload.CONTRACT_RELATIVE)
        with open(contract_path, "rb") as handle:
            self.assertEqual(hashlib.sha256(handle.read()).hexdigest(), CONTRACT_SHA256)
        self.assertEqual(upload.CONTRACT_SHA256, CONTRACT_SHA256)
        document = _document()
        self.assertEqual(document["status"], "POLICY_FROZEN_ONE_COLUMN_REFERENCE_UPLOAD_PUBLICATION_NOT_RETRIED")
        self.assertEqual(document["schema_version"], "m9c-reference-upload-v2")
        interface = document["reference_upload_interface"]
        self.assertEqual(interface["columns"], ["sequence"])
        self.assertEqual(interface["rejected_columns"], ["id", "target_name", "target_pdb_id", "source_reference"])
        self.assertEqual(interface["target_configuration"], "supplied_separately")
        self.assertFalse(interface["provenance_fields_in_upload"])
        self.assertTrue(interface["unique_sequences"])
        self.assertFalse(interface["normalization"])
        self.assertFalse(interface["sequence_rewriting"])
        self.assertFalse(interface["private_ledger_is_aptarank_input"])
        self.assertTrue(interface["supersedes_five_column_reference_upload"])
        self.assertEqual(interface["supersession_scope"], "m9c_reference_upload_only")
        self.assertEqual(interface["historical_m9b_artifacts"], "preserved")
        self.assertFalse(interface["historical_m9b_results_rewritten"])
        self.assertFalse(interface["candidate_and_export_behavior_changed"])
        self.assertEqual(document["outputs"]["reference_upload_columns"], ["sequence"])
        self.assertEqual(document["outputs"]["duplicate_provenance_fields"], list(upload.LEDGER_KEYS))
        self.assertFalse(document["outputs"]["duplicate_provenance_is_aptarank_input"])
        self.assertEqual(document["retention"]["upload_fields_from_first_identity"], {"sequence": "sequence_core"})
        self.assertEqual(document["retention"]["provenance_upload_row_number"], "deterministic_1_based")
        attempt = document["first_failed_publication_attempt"]
        self.assertEqual(attempt["attempt"], 1)
        self.assertEqual(attempt["parent_commit"], "3d5a4beafc723ab154a2ff7d3a6d6835841b3b48")
        self.assertEqual(attempt["obsolete_contract_sha256"], "eb082923fbd79ccc05a9833e0f18e40094e8384bd2104392eee6cd46bc55f591")
        self.assertTrue(attempt["ref_opened"])
        self.assertTrue(attempt["ref_verified"])
        self.assertTrue(attempt["preparation_stopped"])
        self.assertEqual(attempt["stop_reason"], "obsolete_five_column_contract_required_publication")
        self.assertEqual(attempt["observed_error_code"], "missing_required_field")
        self.assertEqual(attempt["observed_error_field"], "publication")
        self.assertFalse(attempt["output_published"])
        self.assertFalse(attempt["aptarank_run"])
        self.assertFalse(attempt["retried"])
        self.assertEqual(document["outputs"]["production_directory"], upload.PRODUCTION_DESTINATION)
        self.assertEqual(document["outputs"]["publication_method"], upload.PRODUCTION_PUBLICATION_METHOD)
        self.assertFalse(document["outputs"]["publication_invoked"])
        self.assertTrue(document["outputs"]["existing_destination_refused"])
        self.assertTrue(document["inputs"]["sealed_publication_requires_invocation"])
        self.assertFalse(document["outputs"]["written_by_default"])
        self.assertTrue(document["production_inputs_opened"])
        self.assertTrue(document["ref_opened"])
        self.assertFalse(document["eval_opened"])
        self.assertFalse(document["production_candidates_opened"])
        self.assertFalse(document["scientific_result"])
        self.assertFalse(document["aptarank_execution"])
        self.assertFalse(document["deployment_verified"])
        self.assertFalse(document["local_calibration"])
        self.assertFalse(document["local_calibration_substitute"])
        self.assertEqual(document["calibration"]["performer"], "aptarank")
        self.assertEqual(document["calibration"]["method"], "single_pooled_empirical_ref")
        self.assertFalse(document["calibration"]["project_implementation"])
        expected = document["expected_live_ui_result"]
        self.assertEqual(expected["label"], "expectation_not_observed_ui_result")
        self.assertEqual(expected["expected_ui_accepted_count"], 113)
        self.assertEqual(expected["expected_ui_dropped_count"], 0)
        self.assertEqual(expected["source_identity_rows"], 131)
        self.assertEqual(expected["duplicate_core_collapses"], 18)
        self.assertEqual(expected["other_result"], "stop_m9c")
        self.assertFalse(expected["aptarank_ui_executed"])
        self.assertIsNone(expected["observed_ui_accepted_count"])
        self.assertIsNone(expected["observed_ui_dropped_count"])
        self.assertNotIn("live_result", document)
        self.assertFalse(document["retention"]["later_rows_are_biological_or_quality_exclusions"])
        self.assertTrue(document["sealed_review_authorized"])
        self.assertTrue(upload.SEALED_REVIEW_AUTHORIZED)
        self.assertFalse(upload.SEALED_ENTRY_POINT_INVOKED)
        self.assertEqual(document["external_ref"]["byte_size"], 211993)
        self.assertEqual(document["external_ref"]["locator"], upload.EXTERNAL_REF_LOCATOR)
        self.assertEqual(
            document["external_ref"]["locator"],
            "opened_and_verified_in_attempt_1_corrected_retry_not_invoked",
        )
        self.assertTrue(document["external_ref"]["review_authorized"])
        self.assertEqual(document["outputs"]["atomic_members"], list(upload.OUTPUT_MEMBERS))
        self.assertFalse(document["outputs"]["sealed_entry_point_invoked"])
        self.assertFalse(document["outputs"]["written_by_default"])
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.assertEqual(upload.main([]), 0)
        self.assertEqual(buffer.getvalue(), upload.STATUS + "\n")

    def test_source_header_is_the_clustered_corpus_schema(self):
        document = _document()
        self.assertEqual(document["source_schema"]["columns"], _clustered_columns())
        self.assertEqual(len(document["source_schema"]["columns"]), 85)
        self.assertNotIn("ft_split", document["source_schema"]["columns"])

    def test_first_occurrence_keeps_the_first_identity(self):
        payload = _source_bytes(
            [
                _identity(1, CORE_B, canonical_target_name="Beta, target", pdb_id="1BBB", publication="Doe et al. 2020"),
                _identity(2, CORE_A, canonical_target_name="Alpha target", pdb_id="", publication="Alpha source"),
                _identity(3, CORE_B, canonical_target_name="Later beta", pdb_id="9ZZZ", publication="Later source"),
                _identity(4, CORE_C, canonical_target_name="Short target", pdb_id="", publication="Short source"),
            ]
        )
        prepared = upload.prepare_reference_upload(payload)
        header, rows = _parsed_upload(prepared["reference_upload"])
        self.assertEqual(header, ["sequence"])
        self.assertEqual(list(rows[0]), ["sequence"])
        self.assertEqual([row["sequence"] for row in rows], [CORE_B, CORE_A, CORE_C])
        upload_text = prepared["reference_upload"].decode("utf-8")
        self.assertEqual(upload_text.splitlines()[0], "sequence")
        for forbidden in ("id", "target_name", "target_pdb_id", "source_reference", "S5I_synthetic_01", "Beta, target", "1BBB", "Doe et al. 2020", "Later beta", "9ZZZ"):
            self.assertNotIn(forbidden, upload_text)
        self.assertEqual(prepared["source_row_count"], 4)
        self.assertEqual(prepared["prepared_upload_row_count"], 3)
        self.assertNotIn("accepted_count", prepared)
        self.assertNotIn("dropped_count", prepared)
        self.assertEqual(prepared["duplicate_core_collapses"], 1)
        self.assertFalse(prepared["production_ref_identity_verified"])
        ledger = [json.loads(line) for line in prepared["duplicate_provenance"].decode("utf-8").splitlines()]
        self.assertEqual([item["upload_row_number"] for item in ledger], [1, 2, 3])
        self.assertEqual(ledger[0]["retained_id"], "S5I_synthetic_01")
        self.assertEqual(ledger[0]["source_identities"], ["S5I_synthetic_01", "S5I_synthetic_03"])
        self.assertEqual(ledger[0]["collapsed_source_identities"], ["S5I_synthetic_03"])
        self.assertEqual(ledger[1]["collapsed_source_identities"], [])
        self.assertEqual(sum(len(item["collapsed_source_identities"]) for item in ledger), 1)
        for core in (CORE_A, CORE_B, CORE_C):
            self.assertNotIn(core, prepared["duplicate_provenance"].decode("utf-8"))
            self.assertNotIn(core, prepared["preparation_manifest"].decode("utf-8"))
        manifest = json.loads(prepared["preparation_manifest"].decode("utf-8"))
        self.assertEqual(manifest["status"], "REFERENCE_UPLOAD_PREPARED_APTARANK_NOT_RUN")
        self.assertNotEqual(manifest["status"], upload.STATUS)
        self.assertEqual(manifest["publication_attempt"], 2)
        self.assertIs(type(manifest["publication_attempt"]), int)
        self.assertEqual(manifest["prepared_upload_row_count"], 3)
        self.assertNotIn("accepted_count", manifest)
        self.assertNotIn("dropped_count", manifest)
        self.assertNotIn("live_result", manifest)
        self.assertFalse(manifest["local_calibration"])
        self.assertFalse(manifest["production_ref_identity_verified"])
        self.assertFalse(manifest["aptarank_ui_executed"])
        self.assertIsNone(manifest["observed_ui_accepted_count"])
        self.assertIsNone(manifest["observed_ui_dropped_count"])
        self.assertNotIn("sequence_core", manifest)

    def test_one_column_header_and_113_style_collapse_preserve_order(self):
        def core_token(index):
            alphabet = "ACGU"
            chars = []
            value = index
            for _ in range(4):
                chars.append(alphabet[value % 4])
                value //= 4
            return "GG" + "".join(reversed(chars)) + "UU"

        first_seen = []
        seen = set()
        prefix = [5, 1, 5, 0, 1]
        for index in prefix + [index for index in range(113) if index not in (5, 1, 0)]:
            if index not in seen:
                first_seen.append(index)
                seen.add(index)
        self.assertEqual(len(first_seen), 113)
        source_order = prefix + [index for index in range(113) if index not in (5, 1, 0)] + [first_seen[0]] * 16
        self.assertEqual(len(source_order), 131)
        self.assertEqual(len(source_order) - len(set(source_order)), 18)
        records = []
        for row_number, core_index in enumerate(source_order, start=1):
            records.append(
                _identity(
                    row_number,
                    core_token(core_index),
                    canonical_target_name="TARGET-NOT-UPLOADED-%02d" % row_number,
                    pdb_id=" PDB-NOT-UPLOADED",
                    publication="",
                )
            )
        prepared = upload.prepare_reference_upload(_source_bytes(records))
        header, rows = _parsed_upload(prepared["reference_upload"])
        self.assertEqual(header, ["sequence"])
        self.assertEqual([row["sequence"] for row in rows], [core_token(index) for index in first_seen])
        self.assertNotEqual([row["sequence"] for row in rows], sorted(row["sequence"] for row in rows))
        upload_text = prepared["reference_upload"].decode("utf-8")
        self.assertEqual(upload_text.splitlines()[0], "sequence")
        for forbidden in ("id", "target_name", "target_pdb_id", "source_reference", "TARGET-NOT-UPLOADED", "PDB-NOT-UPLOADED"):
            self.assertNotIn(forbidden, upload_text)
        self.assertEqual(prepared["source_row_count"], 131)
        self.assertEqual(prepared["prepared_upload_row_count"], 113)
        self.assertEqual(prepared["duplicate_core_collapses"], 18)
        self.assertFalse(prepared["production_ref_identity_verified"])
        ledger = [json.loads(line) for line in prepared["duplicate_provenance"].decode("utf-8").splitlines()]
        self.assertEqual([item["upload_row_number"] for item in ledger], list(range(1, 114)))
        ledger_text = prepared["duplicate_provenance"].decode("utf-8")
        groups = {}
        for row_number, core_index in enumerate(source_order, start=1):
            identity = "S5I_synthetic_%02d" % row_number
            groups.setdefault(core_index, []).append(identity)
        for item, core_index in zip(ledger, first_seen):
            identities = groups[core_index]
            self.assertEqual(list(item), ["upload_row_number", "retained_id", "source_identities", "collapsed_source_identities"])
            self.assertEqual(item["retained_id"], identities[0])
            self.assertEqual(item["source_identities"], identities)
            self.assertEqual(item["collapsed_source_identities"], identities[1:])
            self.assertNotIn(core_token(core_index), ledger_text)
        self.assertEqual(sum(len(item["collapsed_source_identities"]) for item in ledger), 18)
        self.assertEqual(upload.validate_reference_upload(prepared["reference_upload"]), [core_token(index) for index in first_seen])

    def test_finished_upload_refuses_duplicate_sequences_and_metadata_columns(self):
        duplicate = ("sequence\n%s\n%s\n" % (CORE_A, CORE_A)).encode("utf-8")
        with self.assertRaises(upload.ReferenceUploadError) as caught:
            upload.validate_reference_upload(duplicate)
        self.assertEqual(caught.exception.code, "duplicate_sequence")
        five_column = b"id,sequence,target_name,target_pdb_id,source_reference\nS5I,ACGUACGUACGUACGUACGU,Target,1ABC,Paper\n"
        with self.assertRaises(upload.ReferenceUploadError) as caught_header:
            upload.validate_reference_upload(five_column)
        self.assertEqual(caught_header.exception.code, "upload_header_invalid")
        for payload in (
            b"sequence,id\nACGUACGUACGUACGUACGU,S5I\n",
            b"Sequence\nACGUACGUACGUACGUACGU\n",
            b"id\nACGUACGUACGUACGUACGU\n",
            b"target_name\nACGUACGUACGUACGUACGU\n",
            b"target_pdb_id\nACGUACGUACGUACGUACGU\n",
            b"source_reference\nACGUACGUACGUACGUACGU\n",
            b"\xef\xbb\xbfsequence\nACGUACGUACGUACGUACGU\n",
        ):
            with self.assertRaises(upload.ReferenceUploadError) as caught_meta:
                upload.validate_reference_upload(payload)
            self.assertEqual(caught_meta.exception.code, "upload_header_invalid")
        jagged = ("sequence\n%s,S5I_synthetic_01\n" % CORE_A).encode("utf-8")
        with self.assertRaises(upload.ReferenceUploadError) as caught_jagged:
            upload.validate_reference_upload(jagged)
        self.assertEqual(caught_jagged.exception.code, "metadata_column_refused")
        thymine = b"sequence\nACGTACGTACGTACGTACGT\n"
        with self.assertRaises(upload.ReferenceUploadError) as caught_thymine:
            upload.validate_reference_upload(thymine)
        self.assertEqual(caught_thymine.exception.code, "noncanonical_core")
        lowered = ("sequence\n%s\n" % CORE_A.lower()).encode("utf-8")
        with self.assertRaises(upload.ReferenceUploadError) as caught_lower:
            upload.validate_reference_upload(lowered)
        self.assertEqual(caught_lower.exception.code, "noncanonical_core")
        spaced = ("sequence\n%s \n" % CORE_A).encode("utf-8")
        with self.assertRaises(upload.ReferenceUploadError) as caught_space:
            upload.validate_reference_upload(spaced)
        self.assertEqual(caught_space.exception.code, "noncanonical_core")
        accepted = upload.validate_reference_upload(("sequence\n%s\n%s\n" % (CORE_B, CORE_A)).encode("utf-8"))
        self.assertEqual(accepted, [CORE_B, CORE_A])

    def test_duplicate_identity_fails_closed(self):
        payload = _source_bytes(
            [
                _identity(1, CORE_A),
                _identity(1, CORE_B),
            ]
        )
        with self.assertRaises(upload.ReferenceUploadError) as caught:
            upload.prepare_reference_upload(payload)
        self.assertEqual(caught.exception.code, "duplicate_identity")

    def test_noncanonical_core_is_not_converted(self):
        thymine = "ACGTACGTACGTACGTACGT"
        payload = _source_bytes([_identity(1, thymine)])
        with self.assertRaises(upload.ReferenceUploadError) as caught:
            upload.prepare_reference_upload(payload)
        self.assertEqual(caught.exception.code, "noncanonical_core")
        self.assertNotIn(thymine, caught.exception.detail)
        self.assertNotIn(thymine.replace("T", "U"), caught.exception.detail)
        lowered = _source_bytes([_identity(2, CORE_A.lower())])
        with self.assertRaises(upload.ReferenceUploadError) as caught_lower:
            upload.prepare_reference_upload(lowered)
        self.assertEqual(caught_lower.exception.code, "noncanonical_core")

    def test_missing_identity_fails_and_blank_provenance_is_not_an_exclusion(self):
        missing = _source_bytes([_identity(1, CORE_A, scientific_identity_id="")])
        with self.assertRaises(upload.ReferenceUploadError) as caught:
            upload.prepare_reference_upload(missing)
        self.assertEqual(caught.exception.code, "missing_required_field")
        kept = upload.prepare_reference_upload(
            _source_bytes(
                [
                    _identity(
                        1,
                        CORE_A,
                        canonical_target_name="  ",
                        pdb_id=" 1ABC",
                        publication="",
                    )
                ]
            )
        )
        header, rows = _parsed_upload(kept["reference_upload"])
        self.assertEqual(header, ["sequence"])
        self.assertEqual(rows, [{"sequence": CORE_A}])
        self.assertNotIn("1ABC", kept["reference_upload"].decode("utf-8"))
        self.assertEqual(kept["duplicate_core_collapses"], 0)

    def test_malformed_schema_and_wrong_partition_fail_closed(self):
        document = _document()
        columns = list(document["source_schema"]["columns"])
        swapped = list(columns)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        payload = _source_bytes([_identity(1, CORE_A)], header=swapped)
        with self.assertRaises(upload.ReferenceUploadError) as caught:
            upload.prepare_reference_upload(payload)
        self.assertEqual(caught.exception.code, "schema_mismatch")
        foreign = _source_bytes([_identity(1, CORE_A, partition="FT")])
        with self.assertRaises(upload.ReferenceUploadError) as caught_partition:
            upload.prepare_reference_upload(foreign)
        self.assertEqual(caught_partition.exception.code, "schema_mismatch")

    def test_core_digest_mismatch_fails_closed(self):
        payload = _source_bytes([_identity(1, CORE_A)], digest_for="0" * 64)
        with self.assertRaises(upload.ReferenceUploadError) as caught:
            upload.prepare_reference_upload(payload)
        self.assertEqual(caught.exception.code, "digest_mismatch")
        self.assertNotIn(CORE_A, caught.exception.detail)

    def test_production_identity_flag_rejects_a_different_digest(self):
        payload = _source_bytes([_identity(1, CORE_A)])
        with self.assertRaises(upload.ReferenceUploadError) as caught:
            upload.prepare_reference_upload(payload, enforce_production_identity=True)
        self.assertEqual(caught.exception.code, "digest_mismatch")

    def test_frozen_digest_with_other_counts_stops_m9c(self):
        payload = _source_bytes([_identity(1, CORE_A), _identity(2, CORE_B)])
        real_hash = hashlib.sha256

        def fake(blob):
            if blob == payload:
                return upload.REF_SHA256
            return real_hash(blob).hexdigest()

        with patch.object(upload, "sha256_bytes", side_effect=fake):
            with self.assertRaises(upload.ReferenceUploadError) as caught:
                upload.prepare_reference_upload(payload)
        self.assertEqual(caught.exception.code, "conflicting_row_count")
        self.assertIn("sealed REF preparation accounting", caught.exception.detail)
        self.assertNotIn("live REF accounting", caught.exception.detail)
        self.assertIn("M9C stops", caught.exception.detail)
        self.assertIn("2 prepared upload rows", caught.exception.detail)
        self.assertIn("113 accepted and 0 dropped", caught.exception.detail)

    def test_simulated_production_preparation_cannot_populate_observed_ui_counts(self):
        def core(index):
            body = f"{index:08b}".replace("0", "A").replace("1", "C")
            return "GUGU" + body + "GUGU"

        rows = [_identity(index + 1, core(index)) for index in range(113)]
        rows.extend(_identity(114 + index, core(index)) for index in range(18))
        self.assertEqual(len(rows), 131)
        payload = _source_bytes(rows)
        real_hash = hashlib.sha256

        def fake(blob):
            if blob == payload:
                return upload.REF_SHA256
            return real_hash(blob).hexdigest()

        with patch.object(upload, "sha256_bytes", side_effect=fake):
            prepared = upload.prepare_reference_upload(payload, enforce_production_identity=True)
            with self.assertRaises(upload.ReferenceUploadError) as caught:
                upload.prepare_reference_upload(
                    payload,
                    enforce_production_identity=True,
                    observed_ui_accepted_count=113,
                    observed_ui_dropped_count=0,
                )
        self.assertEqual(caught.exception.code, "ui_observation_refused")
        manifest = json.loads(prepared["preparation_manifest"].decode("utf-8"))
        self.assertEqual(manifest["status"], upload.MANIFEST_STATUS)
        self.assertNotEqual(manifest["status"], upload.STATUS)
        self.assertEqual(manifest["publication_attempt"], 2)
        self.assertTrue(prepared["production_ref_identity_verified"])
        self.assertTrue(manifest["production_ref_identity_verified"])
        self.assertEqual(manifest["prepared_upload_row_count"], 113)
        self.assertEqual(manifest["source_row_count"], 131)
        self.assertEqual(manifest["duplicate_core_collapses"], 18)
        self.assertFalse(manifest["aptarank_ui_executed"])
        self.assertIsNone(manifest["observed_ui_accepted_count"])
        self.assertIsNone(manifest["observed_ui_dropped_count"])
        text = prepared["preparation_manifest"].decode("utf-8")
        self.assertIn('"aptarank_ui_executed":false', text)
        self.assertIn('"observed_ui_accepted_count":null', text)
        self.assertIn('"observed_ui_dropped_count":null', text)
        self.assertNotIn('"observed_ui_accepted_count":113', text)
        self.assertNotIn('"accepted_count"', text)
        self.assertNotIn('"dropped_count"', text)
        self.assertNotIn('"live_result"', text)

    def test_paths_and_sealed_locator_do_not_open_inputs(self):
        with patch("builtins.open", side_effect=AssertionError("opened")):
            with self.assertRaises(upload.ReferenceUploadError) as caught_path:
                upload.prepare_reference_upload(os.path.join("data", "processed", "ref.csv"))
            self.assertEqual(caught_path.exception.code, "filesystem_path_refused")
        with self.assertRaises(upload.ReferenceUploadError) as caught_runner:
            upload.main(["--live"])
        self.assertEqual(caught_runner.exception.code, "production_runner_refused")
        source = _read_text(os.path.join(MODELLING, "aptarank_reference_upload.py"))
        tree = ast.parse(source)
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        def first_call(function):
            for statement in function.body:
                if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
                    continue
                self.assertIsInstance(statement, ast.Expr)
                self.assertIsInstance(statement.value, ast.Call)
                return statement.value
            self.fail("missing call")

        sealed_call = first_call(functions["prepare_sealed_reference"])
        self.assertEqual(sealed_call.func.id, "_require_sealed_invocation")
        self.assertFalse(upload.SEALED_ENTRY_POINT_INVOKED)
        main_calls = []
        for child in ast.walk(functions["main"]):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                main_calls.append(child.func.id)
        self.assertNotIn("prepare_sealed_reference", main_calls)
        self.assertNotIn("_read_external_ref", main_calls)
        reader_call = first_call(functions["_read_external_ref"])
        self.assertEqual(reader_call.func.id, "_require_sealed_invocation")
        size_check = ast.dump(functions["_read_pinned_ref_bytes"])
        self.assertLess(size_check.index("st_size"), size_check.index("id='open'"))
        self.assertNotIn("prepare_sealed_reference", main_calls)
        self.assertNotIn("publish_sealed_reference_preparation", main_calls)
        self.assertNotIn("_publish_prepared_directory", main_calls)
        self.assertNotIn("_read_pinned_ref_bytes", main_calls)

    def test_atomic_wrapper_writes_caller_bytes_without_the_sealed_entry_point(self):
        prepared = {
            "reference_upload": b"id,sequence\n",
            "duplicate_provenance": b"{}\n",
            "preparation_manifest": b'{"aptarank_ui_executed":false}\n',
        }
        with patch.object(upload, "prepare_sealed_reference", side_effect=AssertionError("invoked")):
            with patch.object(upload, "_read_external_ref", side_effect=AssertionError("read")):
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(upload.ReferenceUploadError) as caught_ui:
                        upload.write_sealed_preparation_outputs(directory, {**prepared, "observed_ui_accepted_count": 113})
                    self.assertEqual(caught_ui.exception.code, "ui_observation_refused")
                    self.assertEqual(os.listdir(directory), [])
                    for relative in ("data", "results"):
                        protected = os.path.join(upload.repo_root(), relative, "child")
                        with self.assertRaises(upload.ReferenceUploadError) as caught_protected:
                            upload.write_sealed_preparation_outputs(protected, prepared)
                        self.assertEqual(caught_protected.exception.code, "output_refused")
                    link = os.path.join(directory, "linked")
                    os.symlink(directory, link)
                    with self.assertRaises(upload.ReferenceUploadError) as caught_link:
                        upload.write_sealed_preparation_outputs(link, prepared)
                    self.assertEqual(caught_link.exception.code, "output_refused")
                    with patch("os.write", side_effect=OSError("short write")):
                        with self.assertRaises(OSError):
                            upload.write_sealed_preparation_outputs(directory, prepared)
                    self.assertEqual(os.listdir(directory), ["linked"])
                    written = upload.write_sealed_preparation_outputs(directory, prepared)
                    for name, blob in (
                        ("reference_upload.csv", prepared["reference_upload"]),
                        ("duplicate_provenance.jsonl", prepared["duplicate_provenance"]),
                        ("preparation_manifest.json", prepared["preparation_manifest"]),
                    ):
                        path = os.path.join(directory, name)
                        info = os.lstat(path)
                        self.assertFalse(stat.S_ISLNK(info.st_mode))
                        self.assertTrue(stat.S_ISREG(info.st_mode))
                        with open(path, "rb") as handle:
                            self.assertEqual(handle.read(), blob)
                        self.assertEqual(written[name], path)
                    self.assertFalse(any(name.endswith(".partial") for name in os.listdir(directory)))
                    with self.assertRaises(upload.ReferenceUploadError) as caught_exists:
                        upload.write_sealed_preparation_outputs(directory, prepared)
                    self.assertEqual(caught_exists.exception.code, "output_exists")

    def test_target_mapping_digests_are_recorded_separately(self):
        document = _document()
        mapping = document["frozen_target_mapping"]
        self.assertEqual(mapping["structure_file_sha256"], "2e185a205c9be0bf76484e8ffb96ae225880723ed68eaaf25dffbbccaf01ff51")
        self.assertEqual(mapping["selection_record_sha256"], "08f0c96af349ce4909d40c3004804317661777f72828cd807823341e0e4f0d04")
        self.assertEqual(mapping["aptarank_target_upload_sha256"], "46471bb0643125ce86300ec050d6f0d3a09faa1d06dc325141c67cd1acdd5922")
        self.assertTrue(mapping["aptarank_target_upload_recorded_separately"])
        self.assertFalse(mapping["files_opened"])
        structure = b"synthetic-structure"
        selection = b"synthetic-selection"
        target_upload = b"synthetic-target-upload"
        real_hash = hashlib.sha256

        def fake(blob):
            if blob == structure:
                return upload.STRUCTURE_FILE_SHA256
            if blob == selection:
                return upload.SELECTION_RECORD_SHA256
            if blob == target_upload:
                return upload.TARGET_UPLOAD_SHA256
            return real_hash(blob).hexdigest()

        with patch.object(upload, "sha256_bytes", side_effect=fake):
            verified = upload.verify_frozen_target_mapping(structure, selection, target_upload)
            with self.assertRaises(upload.ReferenceUploadError) as caught:
                upload.verify_frozen_target_mapping(selection, structure, target_upload)
        self.assertEqual(caught.exception.code, "digest_mismatch")
        self.assertEqual(verified["structure_file_sha256"], mapping["structure_file_sha256"])
        self.assertEqual(verified["selection_record_sha256"], mapping["selection_record_sha256"])
        self.assertEqual(verified["aptarank_target_upload_sha256"], mapping["aptarank_target_upload_sha256"])
        self.assertNotEqual(verified["structure_file_sha256"], verified["aptarank_target_upload_sha256"])
        with self.assertRaises(upload.ReferenceUploadError) as caught_path:
            upload.verify_frozen_target_mapping(structure, selection, "target-upload.txt")
        self.assertEqual(caught_path.exception.code, "filesystem_path_refused")

    def test_module_does_not_calibrate_or_open_arbitrary_paths(self):
        source_path = os.path.join(MODELLING, "aptarank_reference_upload.py")
        source = _read_text(source_path)
        tree = ast.parse(source)
        imported = set()
        defined = set()
        opens = []

        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self.stack = []

            def visit_FunctionDef(self, node):
                defined.add(node.name)
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_Call(self, node):
                name = None
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name == "open":
                    opens.append(self.stack[-1] if self.stack else "<module>")
                self.generic_visit(node)

        visitor = Visitor()
        visitor.visit(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & {"numpy", "scipy", "sklearn", "RNA", "viennarna", "requests"})
        self.assertFalse(defined & {"calibrate", "fit_reference_distribution", "empirical_cdf", "score_candidates"})
        self.assertEqual(
            sorted(opens),
            [
                "_fsync_directory",
                "_read_pinned_file",
                "_read_pinned_ref_bytes",
                "_reread_verified_members",
                "_write_atomic_bytes",
                "_write_atomic_bytes",
            ],
        )
        self.assertNotIn("eval.csv", source)

    def setUp(self):
        parent = os.path.dirname(upload.PRODUCTION_DESTINATION)
        self._publication_partials = sorted(name for name in os.listdir(parent) if ".partial." in name)
        self.assertFalse(os.path.lexists(upload.PRODUCTION_DESTINATION))

    def tearDown(self):
        self.assertFalse(os.path.lexists(upload.PRODUCTION_DESTINATION))
        parent = os.path.dirname(upload.PRODUCTION_DESTINATION)
        partials = sorted(name for name in os.listdir(parent) if ".partial." in name)
        self.assertEqual(partials, self._publication_partials)

    def test_only_the_exact_production_destination_is_allowed(self):
        self.assertEqual(
            upload.PRODUCTION_DESTINATION,
            "/home/laura/rnagenesis-mres-worktrees/generator-eval-prep/results/fine_tuning/m9_generator_evaluation/m9c_reference_preparation",
        )
        self.assertEqual(upload.preflight_publication_destination(upload.PRODUCTION_DESTINATION), upload.PRODUCTION_DESTINATION)
        repo = upload.repo_root()
        refused = (
            (os.path.join(repo, "results"), "another results path"),
            (os.path.join(repo, "results", "other"), "another results path"),
            (os.path.join(repo, "results", "fine_tuning", "m9_generator_evaluation"), "another results path"),
            (os.path.join(repo, "results", "fine_tuning", "m9_generator_evaluation", "m9a_train_leakage"), "another results path"),
            (upload.PRODUCTION_DESTINATION + "/child", "another results path"),
            (os.path.join(repo, "data"), "under data"),
            (os.path.join(repo, "data", "processed"), "under data"),
            (os.path.join(repo, "data", "processed", "ref.csv"), "under data"),
        )
        for path, detail in refused:
            with self.assertRaises(upload.ReferenceUploadError) as caught:
                upload.preflight_publication_destination(path)
            self.assertEqual(caught.exception.code, "output_refused", path)
            self.assertIn(detail, caught.exception.detail)
        for path in (
            "results/fine_tuning/m9_generator_evaluation/m9c_reference_preparation",
            upload.PRODUCTION_DESTINATION + "/",
            os.path.join(repo, "results", "..", "results", "fine_tuning", "m9_generator_evaluation", "m9c_reference_preparation"),
        ):
            with self.assertRaises(upload.ReferenceUploadError) as caught_relative:
                upload.preflight_publication_destination(path)
            self.assertEqual(caught_relative.exception.code, "output_refused")
        prepared = {
            "reference_upload": b"id,sequence\n",
            "duplicate_provenance": b"{}\n",
            "preparation_manifest": b"{}\n",
        }
        with self.assertRaises(upload.ReferenceUploadError) as caught_writer:
            upload.write_sealed_preparation_outputs(upload.PRODUCTION_DESTINATION, prepared)
        self.assertEqual(caught_writer.exception.code, "output_refused")
        with tempfile.TemporaryDirectory() as parent:
            linked_parent = os.path.join(parent, "linked")
            os.symlink(parent, linked_parent)
            with self.assertRaises(upload.ReferenceUploadError) as caught_link:
                upload._publish_prepared_directory(os.path.join(linked_parent, "m9c_reference_preparation"), _synthetic_prepared())
            self.assertEqual(caught_link.exception.code, "output_refused")
            self.assertEqual(os.listdir(parent), ["linked"])

    def test_publication_rejects_a_pre_retry_contract_status_or_other_attempt(self):
        prepared = _synthetic_prepared()
        manifest = json.loads(prepared["preparation_manifest"].decode("utf-8"))
        self.assertEqual(manifest["status"], "REFERENCE_UPLOAD_PREPARED_APTARANK_NOT_RUN")
        self.assertNotEqual(manifest["status"], "POLICY_FROZEN_ONE_COLUMN_REFERENCE_UPLOAD_PUBLICATION_NOT_RETRIED")
        self.assertEqual(manifest["publication_attempt"], 2)

        def refuse(changed):
            blob = (json.dumps(changed, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
            bad = dict(prepared)
            bad["preparation_manifest"] = blob
            bad["preparation_manifest_sha256"] = hashlib.sha256(blob).hexdigest()
            with tempfile.TemporaryDirectory() as parent:
                destination = os.path.join(parent, "m9c_reference_preparation")
                with self.assertRaises(upload.ReferenceUploadError) as caught:
                    upload._publish_prepared_directory(destination, bad)
                self.assertEqual(caught.exception.code, "manifest_invalid")
                self.assertFalse(os.path.lexists(destination))

        copied = dict(manifest)
        copied["status"] = upload.STATUS
        refuse(copied)
        copied = dict(manifest)
        copied["publication_attempt"] = 1
        refuse(copied)
        copied = dict(manifest)
        copied["publication_attempt"] = True
        refuse(copied)

    def test_publication_preflight_precedes_ref_and_stays_uninvoked(self):
        source = _read_text(os.path.join(MODELLING, "aptarank_reference_upload.py"))
        tree = ast.parse(source)
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}

        class Order(ast.NodeVisitor):
            def __init__(self):
                self.names = []

            def visit_Call(self, node):
                if isinstance(node.func, ast.Name):
                    self.names.append(node.func.id)
                self.generic_visit(node)

        order = Order()
        order.visit(functions["publish_sealed_reference_preparation"])
        self.assertLess(order.names.index("load_pinned_contract"), order.names.index("preflight_publication_destination"))
        self.assertLess(order.names.index("preflight_publication_destination"), order.names.index("_read_pinned_ref_bytes"))
        self.assertLess(order.names.index("_read_pinned_ref_bytes"), order.names.index("prepare_reference_upload"))
        self.assertLess(order.names.index("prepare_reference_upload"), order.names.index("_publish_prepared_directory"))
        self.assertNotIn("prepare_sealed_reference", order.names)
        self.assertNotIn("_read_external_ref", order.names)
        self.assertFalse(upload.SEALED_ENTRY_POINT_INVOKED)
        events = []
        real_load = upload.load_pinned_contract
        real_preflight = upload.preflight_publication_destination

        def load():
            events.append("contract")
            return real_load()

        def preflight(directory):
            events.append("preflight")
            self.assertEqual(directory, upload.PRODUCTION_DESTINATION)
            return real_preflight(directory)

        def read_ref():
            events.append("ref")
            raise upload.ReferenceUploadError("digest_mismatch", "synthetic stop before publication")

        with patch.object(upload, "load_pinned_contract", side_effect=load):
            with patch.object(upload, "preflight_publication_destination", side_effect=preflight):
                with patch.object(upload, "_read_pinned_ref_bytes", side_effect=read_ref):
                    with patch.object(upload, "prepare_sealed_reference", side_effect=AssertionError("sealed entry")):
                        with patch.object(upload, "_publish_prepared_directory", side_effect=AssertionError("published")):
                            with self.assertRaises(upload.ReferenceUploadError) as caught:
                                upload.publish_sealed_reference_preparation(invoke=True)
        self.assertEqual(caught.exception.code, "digest_mismatch")
        self.assertEqual(events, ["contract", "preflight", "ref"])
        with patch.object(upload, "_read_pinned_ref_bytes", side_effect=AssertionError("ref")):
            with patch.object(upload, "load_pinned_contract", side_effect=AssertionError("contract")):
                with patch("os.lstat", side_effect=AssertionError("lstat")):
                    with self.assertRaises(upload.ReferenceUploadError) as caught_idle:
                        upload.publish_sealed_reference_preparation()
                    self.assertEqual(caught_idle.exception.code, "sealed_publication_not_invoked")
                    with self.assertRaises(upload.ReferenceUploadError) as caught_false:
                        upload.publish_sealed_reference_preparation(invoke=False)
                    self.assertEqual(caught_false.exception.code, "sealed_publication_not_invoked")
        with patch.object(upload, "_read_pinned_ref_bytes", side_effect=AssertionError("ref")):
            with self.assertRaises(upload.ReferenceUploadError) as caught_ui:
                upload.publish_sealed_reference_preparation(invoke=True, observed_ui_accepted_count=113)
            self.assertEqual(caught_ui.exception.code, "ui_observation_refused")
        real_lstat = os.lstat

        def existing_directory(path):
            if path == upload.PRODUCTION_DESTINATION:
                return os.stat_result((stat.S_IFDIR, 0, 0, 1, 0, 0, 0, 0, 0, 0))
            return real_lstat(path)

        def existing_symlink(path):
            if path == upload.PRODUCTION_DESTINATION:
                return os.stat_result((stat.S_IFLNK, 0, 0, 1, 0, 0, 0, 0, 0, 0))
            return real_lstat(path)

        with patch("os.lstat", side_effect=existing_directory):
            with patch.object(upload, "_read_pinned_ref_bytes", side_effect=AssertionError("ref")):
                with self.assertRaises(upload.ReferenceUploadError) as caught_exists:
                    upload.publish_sealed_reference_preparation(invoke=True)
        self.assertEqual(caught_exists.exception.code, "output_exists")
        self.assertIn("empty directory", caught_exists.exception.detail)
        with patch("os.lstat", side_effect=existing_symlink):
            with patch.object(upload, "_read_pinned_ref_bytes", side_effect=AssertionError("ref")):
                with self.assertRaises(upload.ReferenceUploadError) as caught_symlink:
                    upload.publish_sealed_reference_preparation(invoke=True)
        self.assertEqual(caught_symlink.exception.code, "output_refused")
        self.assertIn("symlink", caught_symlink.exception.detail)

    def test_verified_temporary_sibling_publishes_with_one_rename(self):
        prepared = _synthetic_prepared()
        with tempfile.TemporaryDirectory() as parent:
            destination = os.path.join(parent, "m9c_reference_preparation")
            decoy = os.path.join(parent, ".m9c_reference_preparation.partial.keep")
            os.mkdir(decoy)
            with open(os.path.join(decoy, "keep.txt"), "wb") as handle:
                handle.write(b"keep")
            renamed = []
            real_rename = upload._rename_noreplace

            def spy(source, target):
                renamed.append((os.path.basename(source), target))
                self.assertEqual(os.path.dirname(source), parent)
                self.assertIn(".partial.", os.path.basename(source))
                self.assertEqual(sorted(os.listdir(source)), sorted(upload.OUTPUT_MEMBERS))
                real_rename(source, target)
                self.assertFalse(os.path.lexists(source))

            with patch.object(upload, "_rename_noreplace", side_effect=spy):
                published = upload._publish_prepared_directory(destination, prepared)
            self.assertEqual(published, destination)
            self.assertEqual(len(renamed), 1)
            self.assertEqual(renamed[0][1], destination)
            for name, key in (
                ("reference_upload.csv", "reference_upload"),
                ("duplicate_provenance.jsonl", "duplicate_provenance"),
                ("preparation_manifest.json", "preparation_manifest"),
            ):
                path = os.path.join(destination, name)
                info = os.lstat(path)
                self.assertFalse(stat.S_ISLNK(info.st_mode))
                self.assertTrue(stat.S_ISREG(info.st_mode))
                with open(path, "rb") as handle:
                    blob = handle.read()
                self.assertEqual(blob, prepared[key])
                self.assertEqual(hashlib.sha256(blob).hexdigest(), prepared[key + "_sha256"])
            manifest = json.loads(prepared["preparation_manifest"].decode("utf-8"))
            self.assertFalse(manifest["aptarank_ui_executed"])
            self.assertIsNone(manifest["observed_ui_accepted_count"])
            self.assertIsNone(manifest["observed_ui_dropped_count"])
            self.assertNotIn("accepted_count", manifest)
            self.assertEqual(sorted(os.listdir(parent)), [".m9c_reference_preparation.partial.keep", "m9c_reference_preparation"])
            with open(os.path.join(decoy, "keep.txt"), "rb") as handle:
                self.assertEqual(handle.read(), b"keep")
            with self.assertRaises(upload.ReferenceUploadError) as caught_again:
                upload._publish_prepared_directory(destination, prepared)
            self.assertEqual(caught_again.exception.code, "output_exists")
            self.assertEqual(sorted(os.listdir(destination)), sorted(upload.OUTPUT_MEMBERS))

    def test_publication_failure_removes_only_that_temporary_directory(self):
        prepared = _synthetic_prepared()
        with tempfile.TemporaryDirectory() as parent:
            destination = os.path.join(parent, "m9c_reference_preparation")
            decoy = os.path.join(parent, ".m9c_reference_preparation.partial.keep")
            unrelated = os.path.join(parent, "unrelated")
            os.mkdir(decoy)
            os.mkdir(unrelated)
            with open(os.path.join(decoy, "keep.txt"), "wb") as handle:
                handle.write(b"keep")
            with open(os.path.join(unrelated, "safe.txt"), "wb") as handle:
                handle.write(b"safe")
            os.mkdir(destination)
            with self.assertRaises(upload.ReferenceUploadError) as caught_empty:
                upload._publish_prepared_directory(destination, prepared)
            self.assertEqual(caught_empty.exception.code, "output_exists")
            self.assertIn("empty directory", caught_empty.exception.detail)
            self.assertEqual(os.listdir(destination), [])
            os.rmdir(destination)
            elsewhere = os.path.join(parent, "elsewhere")
            os.mkdir(elsewhere)
            os.symlink(elsewhere, destination)
            with self.assertRaises(upload.ReferenceUploadError) as caught_link:
                upload._publish_prepared_directory(destination, prepared)
            self.assertEqual(caught_link.exception.code, "output_refused")
            self.assertIn("symlink", caught_link.exception.detail)
            self.assertEqual(os.listdir(elsewhere), [])
            os.unlink(destination)
            os.rmdir(elsewhere)
            real_read = os.read

            def corrupt(descriptor, size):
                data = real_read(descriptor, size)
                if data == b"":
                    return data
                return b"\x00" + data[1:]

            with patch("os.read", side_effect=corrupt):
                with self.assertRaises(upload.ReferenceUploadError) as caught_verify:
                    upload._publish_prepared_directory(destination, prepared)
            self.assertEqual(caught_verify.exception.code, "publication_verify_failed")
            self.assertFalse(os.path.lexists(destination))
            with patch.object(upload, "_rename_noreplace", side_effect=OSError(16, "busy")):
                with self.assertRaises(OSError):
                    upload._publish_prepared_directory(destination, prepared)
            self.assertFalse(os.path.lexists(destination))
            with patch("os.write", side_effect=OSError("short write")):
                with self.assertRaises(OSError):
                    upload._publish_prepared_directory(destination, prepared)
            self.assertFalse(os.path.lexists(destination))
            bad = dict(prepared)
            manifest = json.loads(bad["preparation_manifest"].decode("utf-8"))
            manifest["observed_ui_accepted_count"] = 113
            encoded = (json.dumps(manifest, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
            bad["preparation_manifest"] = encoded
            bad["preparation_manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
            with self.assertRaises(upload.ReferenceUploadError) as caught_ui:
                upload._publish_prepared_directory(destination, bad)
            self.assertEqual(caught_ui.exception.code, "ui_observation_refused")
            self.assertFalse(os.path.lexists(destination))
            self.assertEqual(sorted(os.listdir(parent)), [".m9c_reference_preparation.partial.keep", "unrelated"])
            with open(os.path.join(decoy, "keep.txt"), "rb") as handle:
                self.assertEqual(handle.read(), b"keep")
            with open(os.path.join(unrelated, "safe.txt"), "rb") as handle:
                self.assertEqual(handle.read(), b"safe")
        repo = upload.repo_root()
        for path, detail in (
            (os.path.join(repo, "data", "m9c_reference_preparation"), "under data"),
            (os.path.join(repo, "results", "m9c_reference_preparation"), "another results path"),
        ):
            self.assertFalse(os.path.lexists(path))
            with self.assertRaises(upload.ReferenceUploadError) as caught_protected:
                upload._publish_prepared_directory(path, prepared)
            self.assertEqual(caught_protected.exception.code, "output_refused")
            self.assertIn(detail, caught_protected.exception.detail)
            self.assertFalse(os.path.lexists(path))

    def test_upload_and_provenance_stay_ignored_and_manifest_stays_untracked(self):
        directory = "results/fine_tuning/m9_generator_evaluation/m9c_reference_preparation"
        ignored = {
            directory + "/reference_upload.csv": "reference_upload.csv",
            directory + "/duplicate_provenance.jsonl": "duplicate_provenance.jsonl",
        }
        for relative, name in ignored.items():
            completed = subprocess.run(
                ["git", "check-ignore", "-v", "--no-index", relative],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn(name, completed.stdout)
        manifest = directory + "/preparation_manifest.json"
        completed = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", manifest],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(os.path.lexists(os.path.join(ROOT, directory)))


def _synthetic_prepared():
    payload = _source_bytes(
        [
            _identity(1, CORE_B, canonical_target_name="Beta target", publication="Synthetic publication 01"),
            _identity(2, CORE_A, canonical_target_name="Alpha target", publication="Synthetic publication 02"),
            _identity(3, CORE_B, canonical_target_name="Later beta", publication="Synthetic publication 03"),
        ]
    )
    return upload.prepare_reference_upload(payload)


if __name__ == "__main__":
    unittest.main()

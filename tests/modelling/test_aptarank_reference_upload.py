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
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)

import aptarank_reference_upload as upload

CONTRACT_SHA256 = "21a46064edf346d2eba1f369f80290d7801818ee038442f1092e80219428a21b"
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
        self.assertEqual(document["status"], "POLICY_FROZEN_REF_UNOPENED")
        self.assertFalse(document["ref_opened"])
        self.assertFalse(document["eval_opened"])
        self.assertFalse(document["production_candidates_opened"])
        self.assertFalse(document["local_calibration"])
        self.assertEqual(document["calibration"]["performer"], "aptarank")
        self.assertEqual(document["calibration"]["method"], "single_pooled_empirical_ref")
        self.assertFalse(document["calibration"]["project_implementation"])
        self.assertEqual(document["live_result"]["accepted"], 113)
        self.assertEqual(document["live_result"]["dropped"], 0)
        self.assertEqual(document["live_result"]["source_identity_rows"], 131)
        self.assertEqual(document["live_result"]["duplicate_core_collapses"], 18)
        self.assertEqual(document["live_result"]["other_result"], "stop_m9c")
        self.assertFalse(document["retention"]["later_rows_are_biological_or_quality_exclusions"])
        self.assertFalse(document["sealed_review_authorized"])
        self.assertFalse(upload.SEALED_REVIEW_AUTHORIZED)
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
        self.assertEqual(header, ["id", "sequence", "target_name", "target_pdb_id", "source_reference"])
        self.assertEqual([row["sequence"] for row in rows], [CORE_B, CORE_A, CORE_C])
        self.assertEqual(rows[0]["id"], "S5I_synthetic_01")
        self.assertEqual(rows[0]["target_name"], "Beta, target")
        self.assertEqual(rows[0]["target_pdb_id"], "1BBB")
        self.assertEqual(rows[0]["source_reference"], "Doe et al. 2020")
        self.assertEqual(rows[1]["target_pdb_id"], "")
        self.assertNotIn("Later beta", prepared["reference_upload"].decode("utf-8"))
        self.assertNotIn("9ZZZ", prepared["reference_upload"].decode("utf-8"))
        self.assertEqual(prepared["source_row_count"], 4)
        self.assertEqual(prepared["accepted_count"], 3)
        self.assertEqual(prepared["dropped_count"], 0)
        self.assertEqual(prepared["duplicate_core_collapses"], 1)
        ledger = [json.loads(line) for line in prepared["duplicate_provenance"].decode("utf-8").splitlines()]
        self.assertEqual(ledger[0]["retained_id"], "S5I_synthetic_01")
        self.assertEqual(ledger[0]["source_identities"], ["S5I_synthetic_01", "S5I_synthetic_03"])
        self.assertEqual(ledger[0]["collapsed_source_identities"], ["S5I_synthetic_03"])
        self.assertEqual(ledger[1]["collapsed_source_identities"], [])
        self.assertEqual(sum(len(item["collapsed_source_identities"]) for item in ledger), 1)
        for core in (CORE_A, CORE_B, CORE_C):
            self.assertNotIn(core, prepared["duplicate_provenance"].decode("utf-8"))
            self.assertNotIn(core, prepared["preparation_manifest"].decode("utf-8"))
        manifest = json.loads(prepared["preparation_manifest"].decode("utf-8"))
        self.assertEqual(manifest["dropped_count"], 0)
        self.assertFalse(manifest["local_calibration"])
        self.assertFalse(manifest["live_result"])
        self.assertNotIn("sequence_core", manifest)

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

    def test_missing_required_field_and_bad_pdb_fail_closed(self):
        missing = _source_bytes([_identity(1, CORE_A, publication="")])
        with self.assertRaises(upload.ReferenceUploadError) as caught:
            upload.prepare_reference_upload(missing)
        self.assertEqual(caught.exception.code, "missing_required_field")
        blank_target = _source_bytes([_identity(1, CORE_A, canonical_target_name="  ")])
        with self.assertRaises(upload.ReferenceUploadError) as caught_target:
            upload.prepare_reference_upload(blank_target)
        self.assertEqual(caught_target.exception.code, "missing_required_field")
        padded = _source_bytes([_identity(1, CORE_A, pdb_id=" 1ABC")])
        with self.assertRaises(upload.ReferenceUploadError) as caught_pdb:
            upload.prepare_reference_upload(padded)
        self.assertEqual(caught_pdb.exception.code, "invalid_target_pdb_id")
        kept = upload.prepare_reference_upload(_source_bytes([_identity(1, CORE_A, pdb_id="")]))
        _, rows = _parsed_upload(kept["reference_upload"])
        self.assertEqual(rows[0]["target_pdb_id"], "")

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

    def test_live_flag_rejects_a_different_digest(self):
        payload = _source_bytes([_identity(1, CORE_A)])
        with self.assertRaises(upload.ReferenceUploadError) as caught:
            upload.prepare_reference_upload(payload, live=True)
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
        self.assertIn("M9C stops", caught.exception.detail)
        self.assertIn("2 accepted", caught.exception.detail)
        self.assertIn("0 dropped", caught.exception.detail)

    def test_paths_and_sealed_locator_do_not_open_inputs(self):
        with patch("builtins.open", side_effect=AssertionError("opened")):
            with self.assertRaises(upload.ReferenceUploadError) as caught_path:
                upload.prepare_reference_upload("data/processed/ref.csv")
            self.assertEqual(caught_path.exception.code, "filesystem_path_refused")
            with self.assertRaises(upload.ReferenceUploadError) as caught_sealed:
                upload.prepare_sealed_reference()
            self.assertEqual(caught_sealed.exception.code, "review_required")
        with self.assertRaises(upload.ReferenceUploadError) as caught_runner:
            upload.main(["--live"])
        self.assertEqual(caught_runner.exception.code, "production_runner_refused")

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
        self.assertEqual(sorted(opens), ["_read_external_ref", "_read_pinned_file"])
        self.assertNotIn("eval.csv", source)


if __name__ == "__main__":
    unittest.main()

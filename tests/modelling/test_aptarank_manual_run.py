"""Synthetic-only checks for M9B-4 manual-run provenance.

Target names, residue tokens, and hashes in this module are invented. No
protected ledger, target-selection directory, or AptaRank export is opened.
Passing these tests does not select a target or verify a live deployment.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import sys
import unittest
from contextlib import redirect_stdout

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)

import aptarank_candidate_preparation as preparation
import aptarank_manual_run as manual

CONTRACT_SHA256 = "f1ed83b155c787c51e3d23198db1e5bc4a72c28e0c2a0adc5675b294c0f93125"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
PREPARATION_SHA256 = "3bcfbdf14cd7e777a0b2746f91d0335ba4876195f5012610157e5aa23e083096"
PREPARATION_MODULE_SHA256 = "a4f5b047f2803e775d9521c226287487412495055446e192681957c3d42879ca"
PARSER_MODULE_SHA256 = "4a59ff8e557ee1948410c7f705a9c3772fe2570d4255b0d2185acee99137eaa2"
PREVIOUS_PREPARATION_SHA256 = "99c0ff690f716e6b4560a22d04d9a968e7f039288454cc3669c89a1beb65f3b9"


def digest(label):
    return hashlib.sha256(b"m9b4-" + label.encode("ascii")).hexdigest()


def reorder_keys(value):
    if type(value) is dict:
        return {key: reorder_keys(value[key]) for key in reversed(list(value))}
    if type(value) is list:
        return [reorder_keys(item) for item in value]
    return value


def target_record(**overrides):
    record = {
        "schema_version": manual.TARGET_SCHEMA,
        "configuration_id": "synthetic-config",
        "target_id": "synthetic-target",
        "display_name": "Synthetic target",
        "selection_status": manual.SELECTION_STATUS,
        "structure_id": "1SYN",
        "chain_id": "A",
        "binding_mode": "synthetic mode",
        "site_definition_method": "selected_residues",
        "selected_site_residues": ["12", "15A", "100"],
        "frozen_site_rule": None,
        "structure_file_sha256": digest("structure"),
        "target_selection_record_sha256": digest("selection"),
        "notes": None,
    }
    record.update(overrides)
    return record


def run_record(**overrides):
    record = {
        "schema_version": manual.RUN_SCHEMA,
        "run_id": "synthetic-run-1",
        "state": "prepared",
        "operator": "Synthetic Operator",
        "target_configuration_sha256": digest("target"),
        "preparation_manifest_sha256": digest("manifest"),
        "candidate_upload_sha256": digest("upload"),
        "private_membership_key_sha256": digest("private"),
        "reference_file_sha256": digest("reference"),
        "expected_candidate_count": 4,
        "deployment_id": "synthetic-deployment",
        "requested_preset": "synthetic-preset",
        "effective_settings": {"effective_preset": None, "live_export_behavior": "unresolved"},
        "warnings": ["synthetic warning"],
        "parent_run_id": None,
        "rerun_reason": None,
    }
    record.update(overrides)
    return record


def completed_record(**overrides):
    record = run_record(
        state="completed",
        started_at="2026-10-12T10:00:00Z",
        completed_at="2026-10-12T10:05:00Z",
        exported_count=2,
        missing_count=1,
        rejected_count=1,
        failed_count=0,
        raw_export_sha256=digest("export"),
        run_artefact_sha256=None,
    )
    record.update(overrides)
    return record


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


class ManualRunTests(unittest.TestCase):
    def assert_code(self, code, func):
        with self.assertRaises(manual.ManualRunError) as caught:
            func()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_contract_pins(self):
        payload = read_bytes(manual.contract_path())
        self.assertEqual(hashlib.sha256(payload).hexdigest(), CONTRACT_SHA256)
        self.assertEqual(manual.CONTRACT_SHA256, CONTRACT_SHA256)
        document = manual.load_pinned_contract()
        self.assertEqual(document["status"], manual.STATUS)
        self.assertIs(document["deployment_verified"], False)
        self.assertIs(document["effective_preset_resolved"], False)
        self.assertEqual(document["live_export_behavior"], "unresolved")
        self.assertIs(document["target_selected_by_package"], False)
        self.assertIs(document["structure_file_inspected"], False)
        self.assertIs(document["reasons_invented"], False)
        self.assertEqual(document["governing_plan"]["sha256"], PLAN_SHA256)
        self.assertEqual(document["candidate_preparation_contract"]["sha256"], PREPARATION_SHA256)
        reused = {item["role"]: item for item in document["reused_modules"]}
        self.assertEqual(reused["candidate_preparation_module"]["sha256"], PREPARATION_MODULE_SHA256)
        self.assertEqual(reused["record_parser_module"]["sha256"], PARSER_MODULE_SHA256)
        mutated = json.loads(json.dumps(document))
        mutated["live_export_behavior"] = "require_complete"
        self.assert_code("spec_invalid", lambda: manual.validate_contract_document(mutated))

    def test_valid_prepared_and_completed_records(self):
        prepared = manual.validate_manual_run(run_record())
        self.assertEqual(prepared["state"], "prepared")
        self.assertEqual(list(prepared), list(manual.PREPARED_KEYS))
        self.assertEqual(prepared["warnings"], ["synthetic warning"])
        self.assertIsNone(prepared["effective_settings"]["effective_preset"])
        self.assertEqual(prepared["effective_settings"]["live_export_behavior"], "unresolved")
        self.assertIsNone(prepared["parent_run_id"])
        self.assertIsNone(prepared["rerun_reason"])
        completed = manual.validate_manual_run(completed_record())
        self.assertEqual(list(completed), list(manual.COMPLETED_KEYS))
        self.assertEqual(
            completed["exported_count"] + completed["missing_count"] + completed["rejected_count"] + completed["failed_count"],
            completed["expected_candidate_count"],
        )
        self.assertIsNone(completed["run_artefact_sha256"])
        self.assertNotIn("missing_reason", completed)
        self.assertNotIn("failed_reason", completed)
        with_artefact = manual.validate_manual_run(completed_record(run_artefact_sha256=digest("artefact")))
        self.assertEqual(with_artefact["run_artefact_sha256"], digest("artefact"))
        frozen = manual.validate_target_configuration(
            target_record(
                site_definition_method="frozen_site_rule",
                selected_site_residues=None,
                frozen_site_rule="frozen pocket rule recorded before M9B",
                notes="short synthetic note",
            )
        )
        self.assertIsNone(frozen["selected_site_residues"])
        self.assertEqual(frozen["frozen_site_rule"], "frozen pocket rule recorded before M9B")
        self.assertEqual(frozen["notes"], "short synthetic note")
        self.assertEqual(frozen["selection_status"], "completed_independently_before_m9b")
        residues = manual.validate_target_configuration(target_record())
        self.assertEqual(residues["selected_site_residues"], ["12", "15A", "100"])

    def test_serialization_is_deterministic(self):
        original = target_record()
        snapshot = copy.deepcopy(original)
        first = manual.target_configuration_bytes(original)
        self.assertEqual(original, snapshot)
        second = manual.target_configuration_bytes(json.loads(first))
        self.assertEqual(first, second)
        self.assertEqual(manual.target_configuration_bytes(reorder_keys(original)), first)
        pretty = json.dumps(original, indent=2).encode("utf-8")
        self.assertNotEqual(pretty, first)
        self.assertEqual(manual.target_configuration_bytes(pretty), first)
        self.assertEqual(
            manual.validate_target_configuration(reorder_keys(original)),
            manual.validate_target_configuration(original),
        )
        run = completed_record(warnings=["synthetic warning", "second synthetic warning"])
        payload = manual.manual_run_bytes(run)
        self.assertEqual(payload, manual.manual_run_bytes(json.loads(payload)))
        self.assertEqual(payload, manual.manual_run_bytes(reorder_keys(run)))
        self.assertTrue(payload.endswith(b"\n"))
        self.assertEqual(payload.count(b"\n"), 1)
        self.assertNotIn(b": ", payload)
        self.assertNotIn(b", ", payload)

    def test_hash_binding(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_aptarank_candidate_preparation.py")
        spec = importlib.util.spec_from_file_location("m9b2_fixtures_for_m9b4", path)
        fixtures = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixtures)
        prepared = preparation.prepare_candidates(
            records=fixtures.build_pool(100),
            membership_count=100,
            blinding_key=fixtures.TEST_KEY,
        )
        target_bytes = manual.target_configuration_bytes(target_record())
        manifest_bytes = prepared["preparation_manifest"]
        upload_bytes = prepared["candidate_upload"]
        private_bytes = prepared["private_membership_key"]
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        self.assertEqual(manifest["candidate_upload_sha256"], hashlib.sha256(upload_bytes).hexdigest())
        self.assertEqual(manifest["private_membership_key_sha256"], hashlib.sha256(private_bytes).hexdigest())
        run_bytes = manual.manual_run_bytes(
            run_record(
                target_configuration_sha256=hashlib.sha256(target_bytes).hexdigest(),
                preparation_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                candidate_upload_sha256=hashlib.sha256(upload_bytes).hexdigest(),
                private_membership_key_sha256=hashlib.sha256(private_bytes).hexdigest(),
            )
        )
        receipt = manual.bind_existing_artifacts(
            manual_run=run_bytes,
            target_configuration=target_bytes,
            preparation_manifest=manifest_bytes,
            candidate_upload=upload_bytes,
            private_membership_key=private_bytes,
        )
        self.assertIs(receipt["bound"], True)
        self.assertEqual(receipt["manual_run_state"], "prepared")
        self.assertEqual(receipt["preparation_contract_sha256"], PREPARATION_SHA256)
        self.assertEqual(receipt["candidate_upload_sha256"], manifest["candidate_upload_sha256"])
        self.assertEqual(receipt["private_membership_key_sha256"], manifest["private_membership_key_sha256"])
        self.assertEqual(receipt["preparation_manifest_sha256"], hashlib.sha256(manifest_bytes).hexdigest())
        self.assertEqual(receipt["target_configuration_sha256"], hashlib.sha256(target_bytes).hexdigest())
        self.assertIs(receipt["deployment_verified"], False)
        self.assertIs(receipt["effective_preset_resolved"], False)
        self.assertEqual(receipt["live_export_behavior"], "unresolved")
        self.assertIs(receipt["structure_file_inspected"], False)
        self.assertIs(receipt["reasons_invented"], False)
        receipt_text = json.dumps(receipt)
        self.assertNotIn("cand_", receipt_text)
        sequence = upload_bytes.decode("utf-8").splitlines()[1].split(",", 1)[1]
        self.assertNotIn(sequence, receipt_text)
        self.assert_code(
            "binding_mismatch",
            lambda: manual.bind_existing_artifacts(
                manual_run=run_bytes,
                target_configuration=target_bytes,
                preparation_manifest=manifest_bytes,
                candidate_upload=upload_bytes + b"\n",
                private_membership_key=private_bytes,
            ),
        )
        self.assert_code(
            "binding_mismatch",
            lambda: manual.bind_existing_artifacts(
                manual_run=run_bytes,
                target_configuration=target_bytes,
                preparation_manifest=manifest_bytes,
                candidate_upload=upload_bytes,
                private_membership_key=private_bytes + b"\n",
            ),
        )
        other_target = manual.target_configuration_bytes(target_record(notes="different synthetic note"))
        self.assert_code(
            "binding_mismatch",
            lambda: manual.bind_existing_artifacts(
                manual_run=run_bytes,
                target_configuration=other_target,
                preparation_manifest=manifest_bytes,
                candidate_upload=upload_bytes,
                private_membership_key=private_bytes,
            ),
        )
        wrong_upload = manual.manual_run_bytes(
            run_record(
                target_configuration_sha256=hashlib.sha256(target_bytes).hexdigest(),
                preparation_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                candidate_upload_sha256=digest("other-upload"),
                private_membership_key_sha256=hashlib.sha256(private_bytes).hexdigest(),
            )
        )
        self.assert_code(
            "binding_mismatch",
            lambda: manual.bind_existing_artifacts(
                manual_run=wrong_upload,
                target_configuration=target_bytes,
                preparation_manifest=manifest_bytes,
                candidate_upload=upload_bytes,
                private_membership_key=private_bytes,
            ),
        )
        shifted = json.loads(manifest_bytes.decode("utf-8"))
        shifted["pins"] = [
            dict(pin) if pin.get("role") != "preparation_contract" else {**pin, "sha256": PREVIOUS_PREPARATION_SHA256}
            for pin in shifted["pins"]
        ]
        shifted_bytes = preparation.canonical_json_bytes(shifted) + b"\n"
        self.assert_code(
            "pin_mismatch",
            lambda: manual.bind_existing_artifacts(
                manual_run=run_bytes,
                target_configuration=target_bytes,
                preparation_manifest=shifted_bytes,
                candidate_upload=upload_bytes,
                private_membership_key=private_bytes,
            ),
        )

    def test_malformed_hashes_and_unknown_fields(self):
        self.assert_code(
            "hash_malformed",
            lambda: manual.validate_target_configuration(target_record(structure_file_sha256=digest("structure").upper())),
        )
        self.assert_code(
            "hash_malformed",
            lambda: manual.validate_manual_run(run_record(reference_file_sha256="abcd")),
        )
        self.assert_code(
            "hash_malformed",
            lambda: manual.validate_manual_run(run_record(candidate_upload_sha256=None)),
        )
        self.assert_code(
            "unknown_field",
            lambda: manual.validate_target_configuration(target_record(biological_summary="not allowed")),
        )
        self.assert_code(
            "unknown_field",
            lambda: manual.validate_manual_run(run_record(score=1)),
        )
        self.assert_code(
            "unknown_field",
            lambda: manual.validate_manual_run(completed_record(missing_reason="not recorded")),
        )
        self.assert_code(
            "unknown_field",
            lambda: manual.validate_manual_run(run_record(started_at="2026-10-12T10:00:00Z")),
        )
        self.assert_code(
            "effective_settings_unresolved",
            lambda: manual.validate_manual_run(
                run_record(effective_settings={"effective_preset": "rigorous", "live_export_behavior": "unresolved"})
            ),
        )

    def test_missing_target_fields_and_invalid_residues(self):
        missing = target_record()
        del missing["display_name"]
        self.assert_code("target_field_missing", lambda: manual.validate_target_configuration(missing))
        self.assert_code(
            "empty_field",
            lambda: manual.validate_target_configuration(target_record(display_name="")),
        )
        self.assert_code(
            "selection_status_invalid",
            lambda: manual.validate_target_configuration(target_record(selection_status="completed")),
        )
        for residue in ("0", "01", "12a", 12, "A:12", ""):
            self.assert_code(
                "residue_invalid",
                lambda residue=residue: manual.validate_target_configuration(
                    target_record(selected_site_residues=["12", residue])
                ),
            )
        self.assert_code(
            "residue_duplicate",
            lambda: manual.validate_target_configuration(target_record(selected_site_residues=["15", "15"])),
        )
        self.assert_code(
            "residue_invalid",
            lambda: manual.validate_target_configuration(target_record(selected_site_residues=[])),
        )
        self.assert_code(
            "site_conflict",
            lambda: manual.validate_target_configuration(
                target_record(frozen_site_rule="frozen pocket rule recorded before M9B")
            ),
        )
        self.assert_code(
            "site_invalid",
            lambda: manual.validate_target_configuration(
                target_record(
                    site_definition_method="frozen_site_rule",
                    selected_site_residues=None,
                    frozen_site_rule=None,
                )
            ),
        )

    def test_count_mismatch_and_incomplete_completed_records(self):
        mismatch = self.assert_code(
            "count_mismatch",
            lambda: manual.validate_manual_run(completed_record(expected_candidate_count=3)),
        )
        self.assertNotIn("reason", mismatch.detail)
        self.assert_code(
            "count_invalid",
            lambda: manual.validate_manual_run(completed_record(failed_count=True)),
        )
        incomplete = completed_record()
        del incomplete["started_at"]
        self.assert_code("completed_field_missing", lambda: manual.validate_manual_run(incomplete))
        self.assert_code(
            "completed_incomplete",
            lambda: manual.validate_manual_run(completed_record(raw_export_sha256=None)),
        )
        self.assert_code(
            "completed_incomplete",
            lambda: manual.validate_manual_run(completed_record(completed_at=None)),
        )
        self.assert_code(
            "timestamp_invalid",
            lambda: manual.validate_manual_run(completed_record(completed_at="2026-10-12T09:00:00Z")),
        )

    def test_rerun_lineage(self):
        valid = manual.validate_manual_run(
            completed_record(parent_run_id="synthetic-run-0", rerun_reason="synthetic rerun reason")
        )
        self.assertEqual(valid["parent_run_id"], "synthetic-run-0")
        self.assertEqual(valid["rerun_reason"], "synthetic rerun reason")
        self.assert_code(
            "rerun_lineage_invalid",
            lambda: manual.validate_manual_run(run_record(parent_run_id="synthetic-run-0", rerun_reason=None)),
        )
        self.assert_code(
            "rerun_lineage_invalid",
            lambda: manual.validate_manual_run(run_record(parent_run_id="synthetic-run-0", rerun_reason="")),
        )
        self.assert_code(
            "rerun_lineage_invalid",
            lambda: manual.validate_manual_run(run_record(rerun_reason="synthetic rerun reason")),
        )
        self.assert_code(
            "rerun_lineage_invalid",
            lambda: manual.validate_manual_run(
                run_record(parent_run_id="synthetic-run-1", rerun_reason="synthetic rerun reason")
            ),
        )

    def test_paths_are_refused(self):
        self.assert_code(
            "filesystem_path_refused",
            lambda: manual.validate_target_configuration(pathlib.Path("/tmp/target.json")),
        )
        self.assert_code(
            "filesystem_path_refused",
            lambda: manual.validate_target_configuration(target_record(structure_id="/tmp/structure.pdb")),
        )
        self.assert_code(
            "filesystem_path_refused",
            lambda: manual.validate_target_configuration(target_record(notes="results/target.json")),
        )
        self.assert_code(
            "filename_refused",
            lambda: manual.validate_target_configuration(target_record(structure_id="ref.csv")),
        )
        self.assert_code(
            "filesystem_path_refused",
            lambda: manual.validate_manual_run("/tmp/manual-run.json"),
        )
        self.assert_code(
            "filesystem_path_refused",
            lambda: manual.bind_existing_artifacts(
                manual_run=b"{}",
                target_configuration=b"{}",
                preparation_manifest=b"{}",
                candidate_upload="/tmp/candidate_upload.csv",
                private_membership_key=b"{}",
            ),
        )
        self.assert_code("filesystem_path_refused", lambda: manual.validate_manual_run(run_record(), path="/tmp/not-used"))
        self.assert_code("role_refused", lambda: manual.validate_target_configuration(target_record(), role="TRAIN"))
        self.assert_code("eval_unlock_refused", lambda: manual.validate_manual_run(run_record(), eval_unlock=True))

    def test_no_production_entry_point_or_filesystem_reader(self):
        source = read_bytes(os.path.join(MODELLING, "aptarank_manual_run.py")).decode("utf-8")
        tree = ast.parse(source)
        imported = set()
        functions = set()

        class CallVisitor(ast.NodeVisitor):
            def __init__(self):
                self.stack = []
                self.calls = []

            def visit_FunctionDef(self, node):
                self.stack.append(node.name)
                functions.add(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_Call(self, node):
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                else:
                    name = None
                if name in {"open", "lstat", "read_bytes", "read_text"}:
                    owner = self.stack[-1] if self.stack else "<module>"
                    self.calls.append((owner, name))
                self.generic_visit(node)

        visitor = CallVisitor()
        visitor.visit(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & {"random", "requests", "urllib", "streamlit", "pathlib", "sqlite3"})
        self.assertEqual(visitor.calls, [("_read_pinned_file", "lstat"), ("_read_pinned_file", "open")])
        readers = sorted(name for name in functions if "read" in name or "open" in name)
        self.assertEqual(readers, ["_read_pinned_file"])
        for name in (
            "run_production",
            "score_candidates",
            "empirical_cdf",
            "reproduce_aptarank",
            "publish_directory",
            "prepare_candidates",
            "select_memberships",
            "validate_export",
        ):
            self.assertNotIn(name, functions)
            self.assertNotIn(name, source)
        for needle in (
            "/home/" + "laura/rnagenesis-mres-runs",
            "ft_" + "train.csv",
            "ft_" + "validation.csv",
            "corpus_" + "final",
            "eval" + ".csv",
            "ref" + ".csv",
        ):
            self.assertNotIn(needle, source)
        self.assert_code("production_runner_refused", lambda: manual.main(["validate"]))
        with redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(manual.main([]), 0)
        self.assertEqual(captured.getvalue().strip(), manual.STATUS)


if __name__ == "__main__":
    unittest.main()

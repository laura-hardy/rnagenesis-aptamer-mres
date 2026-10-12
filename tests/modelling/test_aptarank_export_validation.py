"""Synthetic-only checks for M9B-3 downloaded-export validation.

Sequences, ids, and rejection text in this module are invented. No protected
ledger, production upload, or AptaRank download is opened. Passing these tests
does not verify a live export.
"""

from __future__ import annotations

import ast
import copy
import csv
import hashlib
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

import aptarank_export_validation as validation

CONTRACT_SHA256 = "91c318459789bb95eeca169cc398941b71b2f73856a416ea308142ebffd43a1f"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
EVIDENCE_SHA256 = "0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b"
PREPARATION_SHA256 = "3bcfbdf14cd7e777a0b2746f91d0335ba4876195f5012610157e5aa23e083096"
EVIDENCE_MODULE_SHA256 = "08e780e03108c0008174a4559840ce59a56d567b99376d3ad0272eb29a69bbcb"
PREPARATION_MODULE_SHA256 = "a4f5b047f2803e775d9521c226287487412495055446e192681957c3d42879ca"
IO_MODULE_SHA256 = "eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01"
PARSER_MODULE_SHA256 = "4a59ff8e557ee1948410c7f705a9c3772fe2570d4255b0d2185acee99137eaa2"
ARTIFACT_SHA = hashlib.sha256(b"m9b3-synthetic-artifact").hexdigest()
ALPHA = "ACGU" * 5
BRAVO = "UUUUACGUACGUACGUACGU"
CHARLIE = "GGGG" + ("ACGU" * 5)
NOVEL = ("ACGU" * 4) + "UUUU"
EXPORT_HEADER = ["rank", "candidate", "aptamer-likeness", "compatibility", "shuffle", "len", "sequence"]
ROLES = {
    "B0": "external_baseline",
    "B1": "primary_causal_comparison",
    "B2": "secondary_data_scale_comparator",
    "D1": "primary_causal_comparison",
}
CALLER_REASON = "synthetic caller reason alpha"


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def csv_bytes(header, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def provenance(condition, seed=None, sampled_length=20):
    if condition == "B0":
        return {
            "b0_seed": 7,
            "b0_chunk_id": "synthetic-chunk",
            "line_number": 1,
            "source_artifact_id": "synthetic-m9b3-artifact",
            "source_artifact_sha256": ARTIFACT_SHA,
        }
    if condition == "B2":
        return {
            "attempt_index": 1,
            "empirical_null_seed": 7,
            "sampled_length": sampled_length,
            "source_artifact_id": "synthetic-m9b3-artifact",
            "source_artifact_sha256": ARTIFACT_SHA,
        }
    return {
        "checkpoint_identity": "synthetic-checkpoint",
        "generation_seed": 1001,
        "requested_biological_length": 20,
        "invocation_index": 1,
        "master_attempt_index": 1,
        "technical_block": "B" if seed == 44 else "A",
        "source_artifact_id": "synthetic-m9b3-artifact",
        "source_artifact_sha256": ARTIFACT_SHA,
        "d1_training_seed": None if condition == "B1" else seed,
    }


def membership(candidate_id, condition, length, source_identity, seed=None, sampled_length=20):
    return {
        "candidate_id": candidate_id,
        "condition": condition,
        "comparison_role": ROLES[condition],
        "length": length,
        "multiplicity": 1,
        "source_occurrences": [
            {
                "source_identity": source_identity,
                "provenance": provenance(condition, seed=seed, sampled_length=sampled_length),
            }
        ],
    }


def base_memberships():
    return [
        membership("cand_alpha", "B1", 20, "synthetic-src-b1-alpha"),
        membership("cand_alpha", "D1", 20, "synthetic-src-d1-alpha", seed=43),
        membership("cand_bravo", "B0", 20, "synthetic-src-b0-bravo"),
        membership("cand_charlie", "B2", 24, "synthetic-src-b2-charlie", sampled_length=24),
    ]


def base_upload_rows():
    return [
        ["cand_alpha", ALPHA],
        ["cand_bravo", BRAVO],
        ["cand_charlie", CHARLIE],
    ]


def base_export_rows():
    return [
        ["1", "cand_charlie", "0.900", "strong", "pass", "24", CHARLIE],
        ["2", "cand_alpha", "0.500", "weak", "\u2014", "20", ALPHA],
        ["3", "cand_bravo", "0.500", "not evaluated", "fail", "20", BRAVO],
    ]


def upload_bytes(rows=None):
    return csv_bytes(["id", "sequence"], base_upload_rows() if rows is None else rows)


def private_bytes(rows=None):
    documents = base_memberships() if rows is None else rows
    lines = [
        json.dumps(document, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        for document in documents
    ]
    return b"\n".join(lines) + b"\n"


def export_bytes(rows=None):
    return csv_bytes(EXPORT_HEADER, base_export_rows() if rows is None else rows)


def rejection_bytes(records):
    lines = [
        json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        for record in records
    ]
    return b"\n".join(lines) + b"\n"


def joined_rows(result):
    return [json.loads(line) for line in result["joined_candidates"].decode("utf-8").splitlines() if line]


def manifest_of(result):
    return json.loads(result["validation_manifest"].decode("ascii"))


def source_identities():
    return [
        occurrence["source_identity"]
        for row in base_memberships()
        for occurrence in row["source_occurrences"]
    ]


class ExportValidationTests(unittest.TestCase):
    def validate(self, upload=None, private=None, export=None, policy="require_complete", rejection=None, **kwargs):
        return validation.validate_export(
            candidate_upload=upload_bytes() if upload is None else upload,
            private_membership_key=private_bytes() if private is None else private,
            shortlist_export=export_bytes() if export is None else export,
            missing_row_policy=policy,
            rejection_records=rejection,
            **kwargs,
        )

    def test_contract_and_reused_pins(self):
        payload = read_bytes(validation.contract_path())
        self.assertEqual(hashlib.sha256(payload).hexdigest(), CONTRACT_SHA256)
        self.assertEqual(validation.CONTRACT_SHA256, CONTRACT_SHA256)
        document = validation.load_pinned_contract()
        self.assertEqual(document["status"], validation.STATUS)
        self.assertEqual(document["governing_plan"]["sha256"], PLAN_SHA256)
        self.assertEqual(document["evidence_contract"]["sha256"], EVIDENCE_SHA256)
        self.assertEqual(document["candidate_preparation_contract"]["sha256"], PREPARATION_SHA256)
        self.assertIs(document["scores_recomputed"], False)
        self.assertEqual(document["live_export_behavior"], "unresolved")
        self.assertIsNone(document["missing_row_policy"]["default"])
        self.assertIs(document["export_schema"]["arp1_target_free_profile_is_the_public_token_set"], False)
        reused = {item["role"]: item["sha256"] for item in document["reused_modules"]}
        self.assertEqual(reused["evidence_contract_module"], EVIDENCE_MODULE_SHA256)
        self.assertEqual(reused["candidate_preparation_module"], PREPARATION_MODULE_SHA256)
        self.assertEqual(reused["aptarank_io_module"], IO_MODULE_SHA256)
        self.assertEqual(reused["record_parser_module"], PARSER_MODULE_SHA256)
        self.assertEqual(document["export_schema"]["columns"], list(validation.EXPORT_COLUMNS))
        self.assertIn("\u2014", document["export_schema"]["shuffle_tokens"])
        self.assertIn("weak", document["export_schema"]["compatibility_tokens"])

    def test_pin_drift_fails_closed(self):
        document = validation.load_pinned_contract()
        blobs = {
            "export_validation_contract": read_bytes(validation.contract_path()),
            "governing_plan": read_bytes(os.path.join(ROOT, validation.PLAN_RELATIVE)),
            "evidence_contract": read_bytes(os.path.join(ROOT, validation.EVIDENCE_CONTRACT_RELATIVE)),
            "candidate_preparation_contract": read_bytes(os.path.join(ROOT, validation.PREPARATION_CONTRACT_RELATIVE)),
            "evidence_contract_module": read_bytes(os.path.join(ROOT, validation.EVIDENCE_MODULE_RELATIVE)),
            "candidate_preparation_module": read_bytes(os.path.join(ROOT, validation.PREPARATION_MODULE_RELATIVE)),
            "aptarank_io_module": read_bytes(os.path.join(ROOT, validation.IO_MODULE_RELATIVE)),
            "record_parser_module": read_bytes(os.path.join(ROOT, validation.PARSER_MODULE_RELATIVE)),
        }
        validation.verify_external_pins(document, blobs)
        mutated = json.loads(json.dumps(document))
        mutated["governing_plan"]["sha256"] = "0" * 64
        with self.assertRaises(validation.ExportValidationError) as caught:
            validation.validate_contract_document(mutated)
        self.assertEqual(caught.exception.code, "spec_invalid")
        mutated = json.loads(json.dumps(document))
        mutated["candidate_preparation_contract"]["sha256"] = "0" * 64
        with self.assertRaises(validation.ExportValidationError) as caught:
            validation.validate_contract_document(mutated)
        self.assertEqual(caught.exception.code, "spec_invalid")
        for role in validation.PIN_ROLES:
            changed = dict(blobs)
            changed[role] = blobs[role] + b" "
            with self.assertRaises(validation.ExportValidationError) as caught:
                validation.verify_external_pins(document, changed)
            self.assertEqual(caught.exception.code, "pin_mismatch")
        evidence = json.loads(json.dumps(validation._evidence().load_contract()[0]))
        for fact in evidence["facts"]:
            if fact["id"] == "export_tokens":
                fact["statement"] = "tokens were removed"
        preparation = validation._preparation().load_pinned_contract()
        with self.assertRaises(validation.ExportValidationError) as caught:
            validation.assert_reused_definitions(evidence, preparation)
        self.assertEqual(caught.exception.code, "pin_mismatch")
        drifted = json.loads(json.dumps(preparation))
        drifted["outputs"]["private_membership_key"]["keys"] = ["candidate_id"]
        with self.assertRaises(validation.ExportValidationError) as caught:
            validation.assert_reused_definitions(validation._evidence().load_contract()[0], drifted)
        self.assertEqual(caught.exception.code, "pin_mismatch")
        unresolved = json.loads(json.dumps(validation._evidence().load_contract()[0]))
        for item in unresolved["unresolved_deployment_items"]["items"]:
            if item["id"] == "live_export_behavior":
                item["value"] = "resolved"
        with self.assertRaises(validation.ExportValidationError) as caught:
            validation.assert_reused_definitions(unresolved, preparation)
        self.assertEqual(caught.exception.code, "pin_mismatch")

    def test_shuffled_export_joins_by_opaque_id(self):
        forward = self.validate()
        reversed_rows = list(reversed(base_export_rows()))
        backward = self.validate(export=export_bytes(reversed_rows))
        self.assertEqual(backward["joined_candidates"], forward["joined_candidates"])
        rows = joined_rows(forward)
        by_id = {row["candidate_id"]: row for row in rows}
        self.assertEqual(by_id["cand_alpha"]["sequence"], ALPHA)
        self.assertEqual(by_id["cand_bravo"]["sequence"], BRAVO)
        self.assertEqual(by_id["cand_charlie"]["sequence"], CHARLIE)
        self.assertEqual([row["candidate_id"] for row in rows], ["cand_charlie", "cand_alpha", "cand_bravo"])
        self.assertEqual(by_id["cand_alpha"]["compatibility"], "weak")
        self.assertEqual(by_id["cand_alpha"]["shuffle"], "\u2014")
        self.assertEqual(by_id["cand_bravo"]["compatibility"], "not evaluated")
        self.assertEqual(by_id["cand_charlie"]["aptamer-likeness"], "0.900")
        self.assertEqual(manifest_of(forward)["shortlist_export_sha256"], hashlib.sha256(export_bytes()).hexdigest())
        self.assertNotEqual(
            manifest_of(backward)["shortlist_export_sha256"],
            manifest_of(forward)["shortlist_export_sha256"],
        )

    def test_shared_condition_memberships_are_preserved(self):
        result = self.validate()
        rows = joined_rows(result)
        alpha = next(row for row in rows if row["candidate_id"] == "cand_alpha")
        self.assertEqual([item["condition"] for item in alpha["memberships"]], ["B1", "D1"])
        self.assertEqual(
            [item["comparison_role"] for item in alpha["memberships"]],
            ["primary_causal_comparison", "primary_causal_comparison"],
        )
        self.assertEqual(
            [item["source_occurrences"][0]["source_identity"] for item in alpha["memberships"]],
            ["synthetic-src-b1-alpha", "synthetic-src-d1-alpha"],
        )
        self.assertIsNone(alpha["memberships"][0]["source_occurrences"][0]["provenance"]["d1_training_seed"])
        self.assertEqual(alpha["memberships"][1]["source_occurrences"][0]["provenance"]["d1_training_seed"], 43)
        self.assertNotIn("sequence", alpha["memberships"][0])
        manifest = manifest_of(result)
        self.assertEqual(manifest["upload_row_count"], 3)
        self.assertEqual(manifest["private_membership_count"], 4)
        self.assertEqual(
            manifest["private_membership_count_by_condition"],
            [
                {"condition": "B0", "membership_count": 1},
                {"condition": "B1", "membership_count": 1},
                {"condition": "B2", "membership_count": 1},
                {"condition": "D1", "membership_count": 1},
            ],
        )
        text = result["validation_manifest"].decode("ascii")
        self.assertNotIn("shared", text)
        self.assertNotIn("overlap", text)

    def test_ties_use_exported_scores_and_ascending_ids(self):
        result = self.validate()
        self.assertEqual(
            [(row["candidate_id"], row["rank"], row["aptamer-likeness"]) for row in joined_rows(result)],
            [("cand_charlie", 1, "0.900"), ("cand_alpha", 2, "0.500"), ("cand_bravo", 3, "0.500")],
        )
        swapped = copy.deepcopy(base_export_rows())
        swapped[1][0] = "3"
        swapped[2][0] = "2"
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(export=export_bytes(swapped))
        self.assertEqual(caught.exception.code, "rank_order")
        self.assertNotIn(ALPHA, caught.exception.detail)
        gapped = copy.deepcopy(base_export_rows())
        gapped[2][0] = "4"
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(export=export_bytes(gapped))
        self.assertEqual(caught.exception.code, "rank_order")
        signed = copy.deepcopy(base_export_rows())
        signed[0][0] = "3"
        signed[0][2] = "-1"
        signed[1][0] = "1"
        signed[1][2] = "2.5"
        signed[2][0] = "2"
        signed[2][2] = "2.5"
        signed_result = self.validate(export=export_bytes(signed))
        self.assertEqual(
            [(row["candidate_id"], row["rank"], row["aptamer-likeness"]) for row in joined_rows(signed_result)],
            [("cand_alpha", 1, "2.5"), ("cand_bravo", 2, "2.5"), ("cand_charlie", 3, "-1")],
        )

    def test_missing_extra_and_duplicate_ids(self):
        kept = [row for row in base_export_rows() if row[1] != "cand_bravo"]
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(export=export_bytes(kept))
        self.assertEqual(caught.exception.code, "missing_candidate_id")
        self.assertEqual(caught.exception.disposition, "missing")
        self.assertIsNone(caught.exception.rejection_reason)
        self.assertNotIn(BRAVO, caught.exception.detail)
        self.assertNotIn("threshold", caught.exception.detail)
        extra = base_export_rows() + [["4", "cand_delta", "0.100", "moderate", "pass", "20", NOVEL]]
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(export=export_bytes(extra))
        self.assertEqual(caught.exception.code, "unknown_exported_id")
        self.assertIn("cand_delta", caught.exception.detail)
        self.assertNotIn(NOVEL, caught.exception.detail)
        duplicated = base_export_rows() + [list(base_export_rows()[1])]
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(export=export_bytes(duplicated))
        self.assertEqual(caught.exception.code, "duplicate_exported_id")
        repeated_upload = base_upload_rows() + [["cand_alpha", ALPHA]]
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(upload=upload_bytes(repeated_upload))
        self.assertEqual(caught.exception.code, "duplicate_candidate_id")
        repeated_key = base_memberships() + [membership("cand_bravo", "B0", 20, "synthetic-src-b0-bravo-copy")]
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(private=private_bytes(repeated_key))
        self.assertEqual(caught.exception.code, "duplicate_membership")

    def test_sequence_and_id_substitution(self):
        substituted = copy.deepcopy(base_export_rows())
        substituted[1][6] = BRAVO
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(export=export_bytes(substituted))
        self.assertEqual(caught.exception.code, "sequence_substituted")
        self.assertIn("cand_alpha", caught.exception.detail)
        self.assertIn("cand_bravo", caught.exception.detail)
        self.assertNotIn(ALPHA, caught.exception.detail)
        self.assertNotIn(BRAVO, caught.exception.detail)
        novel = copy.deepcopy(base_export_rows())
        novel[1][6] = NOVEL
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(export=export_bytes(novel))
        self.assertEqual(caught.exception.code, "sequence_mismatch")
        self.assertNotIn(NOVEL, caught.exception.detail)
        replaced = copy.deepcopy(base_export_rows())
        replaced[1][1] = "cand_delta"
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(export=export_bytes(replaced))
        self.assertEqual(caught.exception.code, "unknown_exported_id")
        self.assertNotEqual(caught.exception.code, "sequence_substituted")
        self.assertNotIn(ALPHA, caught.exception.detail)

    def test_malformed_numeric_and_categorical_fields(self):
        cases = [
            (0, "0", "malformed_rank"),
            (0, "01", "malformed_rank"),
            (0, "-1", "malformed_rank"),
            (0, "1.0", "malformed_rank"),
            (2, "nan", "nonfinite_aptamer_likeness"),
            (2, "inf", "nonfinite_aptamer_likeness"),
            (2, "abc", "malformed_aptamer_likeness"),
            (2, "", "malformed_aptamer_likeness"),
            (5, "20.0", "malformed_length"),
            (5, "-1", "malformed_length"),
            (5, "020", "malformed_length"),
            (5, "19", "length_mismatch"),
            (3, "Strong", "invalid_compatibility"),
            (3, "not_evaluated", "invalid_compatibility"),
            (3, "", "invalid_compatibility"),
            (4, "Pass", "invalid_shuffle"),
            (4, "-", "invalid_shuffle"),
            (4, "\u2013", "invalid_shuffle"),
            (4, "", "invalid_shuffle"),
            (1, "", "malformed_candidate_id"),
            (1, "cand alpha", "malformed_candidate_id"),
        ]
        for index, value, code in cases:
            rows = copy.deepcopy(base_export_rows())
            rows[1][index] = value
            with self.assertRaises(validation.ExportValidationError) as caught:
                self.validate(export=export_bytes(rows))
            self.assertEqual(caught.exception.code, code, msg="%s -> %s" % (value, caught.exception.code))
            self.assertNotIn(ALPHA, caught.exception.detail)
        swapped = list(EXPORT_HEADER)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(export=csv_bytes(swapped, base_export_rows()))
        self.assertEqual(caught.exception.code, "schema_mismatch")
        bad_length = base_memberships()
        bad_length[0] = dict(bad_length[0])
        bad_length[0]["length"] = 21
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(private=private_bytes(bad_length))
        self.assertEqual(caught.exception.code, "length_mismatch")
        self.assertNotIn(ALPHA, caught.exception.detail)
        mismatched = base_memberships()
        mismatched[0] = dict(mismatched[0])
        mismatched[0]["multiplicity"] = 2
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(private=private_bytes(mismatched))
        self.assertEqual(caught.exception.code, "multiplicity_mismatch")

    def test_partial_export_and_explicit_rejections(self):
        kept = [row for row in base_export_rows() if row[1] != "cand_bravo"]
        partial = self.validate(export=export_bytes(kept), policy="allow_partial")
        rows = {row["candidate_id"]: row for row in joined_rows(partial)}
        self.assertEqual(rows["cand_bravo"]["disposition"], "missing")
        self.assertIsNone(rows["cand_bravo"]["rejection_reason"])
        self.assertIsNone(rows["cand_bravo"]["rank"])
        self.assertIsNone(rows["cand_bravo"]["aptamer-likeness"])
        self.assertIsNone(rows["cand_bravo"]["compatibility"])
        self.assertIsNone(rows["cand_bravo"]["shuffle"])
        self.assertEqual(rows["cand_bravo"]["sequence"], BRAVO)
        self.assertEqual(rows["cand_bravo"]["length"], 20)
        self.assertEqual([item["condition"] for item in rows["cand_bravo"]["memberships"]], ["B0"])
        bravo_line = [
            line
            for line in partial["joined_candidates"].decode("utf-8").splitlines()
            if "cand_bravo" in line
        ][0]
        self.assertIn('"aptamer-likeness":null', bravo_line)
        self.assertNotIn('"rank":0', bravo_line)
        self.assertNotIn('"aptamer-likeness":0', bravo_line)
        manifest = manifest_of(partial)
        self.assertEqual(manifest["missing_row_policy"], "allow_partial")
        self.assertEqual(manifest["exported_row_count"], 2)
        self.assertEqual(manifest["missing_row_count"], 1)
        self.assertEqual(manifest["rejected_row_count"], 0)
        self.assertIs(manifest["impute_missing_as_zero"], False)
        self.assertIs(manifest["rejection_reasons_invented"], False)
        empty = self.validate(export=export_bytes([]), policy="allow_partial")
        self.assertEqual({row["disposition"] for row in joined_rows(empty)}, {"missing"})
        self.assertTrue(all(row["rejection_reason"] is None for row in joined_rows(empty)))
        ledger = rejection_bytes([{"candidate_id": "cand_bravo", "reason": CALLER_REASON}])
        rejected = self.validate(export=export_bytes(kept), policy="require_complete", rejection=ledger)
        rejected_rows = {row["candidate_id"]: row for row in joined_rows(rejected)}
        self.assertEqual(rejected_rows["cand_bravo"]["disposition"], "rejected")
        self.assertEqual(rejected_rows["cand_bravo"]["rejection_reason"], CALLER_REASON)
        self.assertIsNone(rejected_rows["cand_bravo"]["aptamer-likeness"])
        self.assertEqual(rejected_rows["cand_alpha"]["disposition"], "exported")
        self.assertEqual(manifest_of(rejected)["rejected_row_count"], 1)
        self.assertEqual(manifest_of(rejected)["missing_row_count"], 0)
        self.assertNotIn(CALLER_REASON, rejected["validation_manifest"].decode("ascii"))
        self.assertIn(CALLER_REASON, rejected["joined_candidates"].decode("utf-8"))
        only_charlie = [row for row in base_export_rows() if row[1] == "cand_charlie"]
        only_charlie[0][0] = "1"
        mixed = self.validate(
            export=export_bytes(only_charlie),
            policy="allow_partial",
            rejection=rejection_bytes([{"candidate_id": "cand_alpha", "reason": CALLER_REASON}]),
        )
        dispositions = {row["candidate_id"]: row["disposition"] for row in joined_rows(mixed)}
        self.assertEqual(
            dispositions,
            {"cand_charlie": "exported", "cand_alpha": "rejected", "cand_bravo": "missing"},
        )
        reasons = {row["candidate_id"]: row["rejection_reason"] for row in joined_rows(mixed)}
        self.assertEqual(reasons["cand_alpha"], CALLER_REASON)
        self.assertIsNone(reasons["cand_bravo"])
        self.assertIsNone(reasons["cand_charlie"])
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(
                export=export_bytes(only_charlie),
                policy="require_complete",
                rejection=rejection_bytes([{"candidate_id": "cand_alpha", "reason": CALLER_REASON}]),
            )
        self.assertEqual(caught.exception.code, "missing_candidate_id")
        self.assertIn("cand_bravo", caught.exception.detail)
        self.assertIsNone(caught.exception.rejection_reason)
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(rejection=rejection_bytes([{"candidate_id": "cand_bravo", "reason": "   "}]))
        self.assertEqual(caught.exception.code, "missing_rejection_reason")
        self.assertIsNone(caught.exception.rejection_reason)
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(rejection=ledger)
        self.assertEqual(caught.exception.code, "candidate_accounted_twice")
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(policy=None)
        self.assertEqual(caught.exception.code, "missing_row_policy_missing")
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(policy="infer")
        self.assertEqual(caught.exception.code, "missing_row_policy_invalid")

    def test_deterministic_serialization(self):
        first = self.validate()
        second = self.validate()
        self.assertEqual(second["joined_candidates"], first["joined_candidates"])
        self.assertEqual(second["validation_manifest"], first["validation_manifest"])
        reversed_key = list(reversed(base_memberships()))
        reordered = self.validate(private=private_bytes(reversed_key))
        self.assertEqual(reordered["joined_candidates"], first["joined_candidates"])
        reversed_upload = list(reversed(base_upload_rows()))
        self.assertEqual(self.validate(upload=upload_bytes(reversed_upload))["joined_candidates"], first["joined_candidates"])
        shuffled_provenance = base_memberships()
        provenance_document = shuffled_provenance[0]["source_occurrences"][0]["provenance"]
        shuffled_provenance[0]["source_occurrences"][0]["provenance"] = {
            key: provenance_document[key] for key in reversed(list(provenance_document))
        }
        self.assertEqual(self.validate(private=private_bytes(shuffled_provenance))["joined_candidates"], first["joined_candidates"])
        bom = b"\xef\xbb\xbf" + export_bytes()
        bom_result = self.validate(export=bom)
        self.assertEqual(bom_result["joined_candidates"], first["joined_candidates"])
        self.assertNotEqual(manifest_of(bom_result)["shortlist_export_sha256"], manifest_of(first)["shortlist_export_sha256"])
        self.assertTrue(first["joined_candidates"].splitlines()[0].startswith(b'{"candidate_id":'))
        digest = first["validation_manifest_sha256"]
        self.assertEqual(digest, hashlib.sha256(first["validation_manifest"]).hexdigest())
        self.assertNotIn(digest.encode("ascii"), first["validation_manifest"])
        self.assertNotIn(b"validation_manifest_sha256", first["validation_manifest"])

    def test_manifest_is_sequence_free(self):
        result = self.validate()
        manifest = result["validation_manifest"]
        text = manifest.decode("ascii")
        for sequence in (ALPHA, BRAVO, CHARLIE):
            self.assertNotIn(sequence.encode("ascii"), manifest)
            self.assertIn(sequence.encode("ascii"), result["joined_candidates"])
        for candidate_id in ("cand_alpha", "cand_bravo", "cand_charlie"):
            self.assertNotIn(candidate_id.encode("ascii"), manifest)
        for identity in source_identities():
            self.assertNotIn(identity.encode("ascii"), manifest)
            self.assertIn(identity.encode("ascii"), result["joined_candidates"])
        for score in ("0.900", "0.500"):
            self.assertNotIn(score, text)
        for token in ("overlap", "jaccard", "leakage", "nearest"):
            self.assertNotIn(token, text)
        self.assertNotIn(b"cand_", manifest)
        parsed = manifest_of(result)
        self.assertIs(parsed["production_inputs_opened"], False)
        self.assertIs(parsed["aptarank_executed"], False)
        self.assertIs(parsed["scientific_result"], False)
        self.assertIs(parsed["deployment_verified"], False)
        self.assertIs(parsed["scores_recomputed"], False)
        self.assertIs(parsed["biological_summaries_calculated"], False)
        self.assertEqual(parsed["live_export_behavior"], "unresolved")
        self.assertIs(parsed["join_uses_row_position"], False)
        self.assertEqual(parsed["join_key"], "opaque_candidate_id")

    def test_filesystem_paths_and_production_entry_are_refused(self):
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(path="/tmp/not-used")
        self.assertEqual(caught.exception.code, "filesystem_path_refused")
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(upload=pathlib.Path("/tmp/candidate-upload.csv"))
        self.assertEqual(caught.exception.code, "filesystem_path_refused")
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(export="/tmp/does-not-exist-m9b3.csv")
        self.assertEqual(caught.exception.code, "filesystem_path_refused")
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(private="results/private_membership_key.jsonl")
        self.assertEqual(caught.exception.code, "filesystem_path_refused")
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(role="TRAIN")
        self.assertEqual(caught.exception.code, "role_refused")
        with self.assertRaises(validation.ExportValidationError) as caught:
            self.validate(eval_unlock=True)
        self.assertEqual(caught.exception.code, "eval_unlock_refused")
        source = read_bytes(os.path.join(MODELLING, "aptarank_export_validation.py")).decode("utf-8")
        tree = ast.parse(source)
        imported = set()
        functions = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.FunctionDef):
                functions.add(node.name)
        self.assertFalse(imported & {"random", "requests", "urllib", "streamlit"})
        for name in ("score_candidates", "empirical_cdf", "run_production", "reproduce_aptarank"):
            self.assertNotIn(name, functions)
        for needle in (
            "/home/" + "laura/rnagenesis-mres-runs",
            "ft_" + "train.csv",
            "ft_" + "validation.csv",
            "corpus_" + "final",
            "eval" + ".csv",
            "ref" + ".csv",
        ):
            self.assertNotIn(needle, source)
        with self.assertRaises(validation.ExportValidationError) as caught:
            validation.main(["validate"])
        self.assertEqual(caught.exception.code, "production_runner_refused")
        with redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(validation.main([]), 0)
        self.assertEqual(captured.getvalue().strip(), validation.STATUS)


if __name__ == "__main__":
    unittest.main()

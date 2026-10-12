"""Synthetic-only checks for M9B-2 candidate preparation.

Sequences, source identities, and blinding keys in this module are invented.
No protected ledger is opened. Passing these tests does not choose a
production sample or instantiate a production blinding key.
"""

from __future__ import annotations

import ast
import copy
import csv
import hashlib
import hmac
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELLING = os.path.join(ROOT, "scripts", "modelling")
if MODELLING not in sys.path:
    sys.path.insert(0, MODELLING)

import aptarank_candidate_preparation as preparation

CONTRACT_SHA256 = "3bcfbdf14cd7e777a0b2746f91d0335ba4876195f5012610157e5aa23e083096"
PLAN_SHA256 = "b23094cf976de49fc8efb987ee5cbd6584b37c750e1e6eb4351d11f9d65f23fe"
EVIDENCE_SHA256 = "0494ea740b1a2402032bfa695c23a422b142cda6a2bc043d1da87dbb9ddb092b"
IO_SPEC_SHA256 = "46ba6c8be873dad4c086e9f6b889b51702ba31212fa502d00f26e267a22da732"
IO_MODULE_SHA256 = "eb71cb67447142f0b8ea1ac87575adfd067824b96fb552c8ace016ad00c43c01"
EVIDENCE_MODULE_SHA256 = "08e780e03108c0008174a4559840ce59a56d567b99376d3ad0272eb29a69bbcb"
TEST_KEY = b"M9B2-TEST-ONLY-BLINDING-KEY!!!!!"
OTHER_TEST_KEY = b"M9B2-TEST-ONLY-BLINDING-KEYB!!!!"
ARTIFACT_SHA = hashlib.sha256(b"m9b2-synthetic-artifact").hexdigest()
SAMPLING_DOMAIN = "m9b2-candidate-sample-v1"
SAMPLING_SEED = "m9b2-fixed-sampling-seed-v1"
ID_DOMAIN = "m9b2-candidate-id-v1"


def sequence_for(index, length=20):
    alphabet = "ACGU"
    chars = ["U"]
    value = index
    for _ in range(length - 1):
        chars.append(alphabet[value % 4])
        value //= 4
    if value:
        raise AssertionError("sequence space exhausted")
    return "".join(chars)


def provenance_for(condition, index, seed=None, requested_length=20, sampled_length=20):
    if condition == "B0":
        return {
            "b0_seed": 7,
            "b0_chunk_id": "synthetic-chunk",
            "line_number": index,
            "source_artifact_id": "synthetic-m9b2-artifact",
            "source_artifact_sha256": ARTIFACT_SHA,
        }
    if condition == "B2":
        return {
            "attempt_index": index,
            "empirical_null_seed": 7,
            "sampled_length": sampled_length,
            "source_artifact_id": "synthetic-m9b2-artifact",
            "source_artifact_sha256": ARTIFACT_SHA,
        }
    return {
        "checkpoint_identity": "synthetic-checkpoint",
        "generation_seed": 1000 + index,
        "requested_biological_length": requested_length,
        "invocation_index": index,
        "master_attempt_index": index,
        "technical_block": "B" if seed == 44 else "A",
        "source_artifact_id": "synthetic-m9b2-artifact",
        "source_artifact_sha256": ARTIFACT_SHA,
        "d1_training_seed": None if condition == "B1" else seed,
    }


def membership(condition, index, sequence, seed=None, requested_length=20, sampled_length=20):
    seed_label = "na" if seed is None else str(seed)
    return {
        "condition": condition,
        "sequence": sequence,
        "length": len(sequence),
        "multiplicity": 1,
        "source_occurrences": [
            {
                "source_identity": "synthetic-%s-%s-%04d" % (condition, seed_label, index),
                "provenance": provenance_for(
                    condition,
                    index,
                    seed=seed,
                    requested_length=requested_length,
                    sampled_length=sampled_length,
                ),
            }
        ],
    }


def source_ids(row):
    return [item["source_identity"] for item in row["source_occurrences"]]


def training_seed(row):
    return row["source_occurrences"][0]["provenance"]["d1_training_seed"]


def occurrence_copy(occurrence, source_identity, **provenance_updates):
    provenance = dict(occurrence["provenance"])
    provenance.update(provenance_updates)
    return {"source_identity": source_identity, "provenance": provenance}


def canonical_occurrences(condition, occurrences):
    """Independent canonical order: recorded provenance keys, then source identity."""
    keys = {
        "B0": ("b0_seed", "b0_chunk_id", "line_number", "source_artifact_id", "source_artifact_sha256"),
        "B1": (
            "checkpoint_identity",
            "generation_seed",
            "requested_biological_length",
            "invocation_index",
            "master_attempt_index",
            "technical_block",
            "source_artifact_id",
            "source_artifact_sha256",
            "d1_training_seed",
        ),
        "B2": (
            "attempt_index",
            "empirical_null_seed",
            "sampled_length",
            "source_artifact_id",
            "source_artifact_sha256",
        ),
        "D1": (
            "checkpoint_identity",
            "generation_seed",
            "requested_biological_length",
            "invocation_index",
            "master_attempt_index",
            "technical_block",
            "source_artifact_id",
            "source_artifact_sha256",
            "d1_training_seed",
        ),
    }[condition]

    def token(value):
        if type(value) is int:
            return (0, value, b"")
        if type(value) is str:
            return (1, 0, value.encode("utf-8"))
        if value is None:
            return (2, 0, b"")
        raise AssertionError("unexpected provenance value")

    def sort_key(occurrence):
        ordered = [token(occurrence["provenance"][key]) for key in keys]
        ordered.append((1, 0, occurrence["source_identity"].encode("utf-8")))
        return tuple(ordered)

    return sorted(occurrences, key=sort_key)


def selected_sequences(result, condition):
    table = {row["id"]: row["sequence"] for row in upload_table(result)}
    return [table[row["candidate_id"]] for row in private_rows(result) if row["condition"] == condition]


def build_pool(per_condition, extra_non_d1=0, extra_per_seed=0, shared=False):
    if per_condition % 2:
        raise AssertionError("D1 membership count must be even")
    rows = []
    serial = 1
    shared_sequence = sequence_for(0)
    for condition in ("B0", "B1", "B2"):
        for offset in range(per_condition + extra_non_d1):
            sequence = shared_sequence if shared and offset == 0 else sequence_for(serial)
            rows.append(membership(condition, serial, sequence))
            serial += 1
    for seed in (43, 44):
        for offset in range(per_condition // 2 + extra_per_seed):
            sequence = shared_sequence if shared and seed == 43 and offset == 0 else sequence_for(serial)
            rows.append(membership("D1", serial, sequence, seed=seed))
            serial += 1
    identities = [identity for row in rows for identity in source_ids(row)]
    pairs = [(row["condition"], row["sequence"]) for row in rows]
    if len(identities) != len(set(identities)) or len(pairs) != len(set(pairs)):
        raise AssertionError("synthetic memberships collided")
    return rows


def independent_priority(condition, sequence):
    blob = b""
    for part in (SAMPLING_DOMAIN, SAMPLING_SEED, condition, sequence):
        encoded = part.encode("utf-8")
        blob += len(encoded).to_bytes(4, "big") + encoded
    return hashlib.sha256(blob).digest()


def legacy_attempt_priority(condition, source_identity, sequence):
    """Rejected ranking. It changes when a different duplicate attempt is chosen."""
    blob = b""
    for part in (SAMPLING_DOMAIN, SAMPLING_SEED, condition, source_identity, sequence):
        encoded = part.encode("utf-8")
        blob += len(encoded).to_bytes(4, "big") + encoded
    return hashlib.sha256(blob).digest()


def independent_candidate_id(sequence, key):
    blob = b""
    for part in (ID_DOMAIN, sequence):
        encoded = part.encode("utf-8")
        blob += len(encoded).to_bytes(4, "big") + encoded
    return "cand_" + hmac.new(key, blob, hashlib.sha256).digest()[:16].hex()


def independent_selection(rows, membership_count):
    def rank(row):
        return (
            independent_priority(row["condition"], row["sequence"]),
            row["sequence"].encode("utf-8"),
        )

    selected = []
    for condition in ("B0", "B1", "B2"):
        pool = [row for row in rows if row["condition"] == condition]
        selected.extend(sorted(pool, key=rank)[:membership_count])
    for seed in (43, 44):
        pool = [row for row in rows if row["condition"] == "D1" and training_seed(row) == seed]
        selected.extend(sorted(pool, key=rank)[: membership_count // 2])
    return [(row["condition"], tuple(source_ids(row))) for row in selected]


def private_rows(result):
    return [json.loads(line) for line in result["private_membership_key"].decode("utf-8").splitlines()]


def manifest_of(result):
    return json.loads(result["preparation_manifest"].decode("utf-8"))


def upload_table(result):
    return list(csv.DictReader(io.StringIO(result["candidate_upload"].decode("utf-8"), newline="")))


def reorder(value):
    if type(value) is dict:
        return {key: reorder(value[key]) for key in reversed(list(value))}
    return value


def jsonl_bytes(rows):
    lines = [json.dumps(reorder(row), separators=(",", ":")).encode("utf-8") for row in reversed(rows)]
    return b"\r\n".join(lines) + b"\r\n"


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class CandidatePreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if len(TEST_KEY) != 32 or len(OTHER_TEST_KEY) != 32 or TEST_KEY == OTHER_TEST_KEY:
            raise AssertionError("synthetic blinding keys must be distinct 32-byte values")
        cls.exact = {count: build_pool(count) for count in (100, 150, 200)}
        cls.shared = build_pool(100, shared=True)
        cls.sampling_rows = build_pool(100, extra_non_d1=10, extra_per_seed=10)

    def prepare(self, rows, membership_count=100, blinding_key=TEST_KEY, **kwargs):
        return preparation.prepare_candidates(
            records=rows,
            membership_count=membership_count,
            blinding_key=blinding_key,
            **kwargs,
        )

    def test_contract_and_reused_pins(self):
        payload = read_bytes(preparation.contract_path())
        self.assertEqual(hashlib.sha256(payload).hexdigest(), CONTRACT_SHA256)
        self.assertEqual(preparation.CONTRACT_SHA256, CONTRACT_SHA256)
        document = preparation.load_pinned_contract()
        self.assertEqual(document["status"], preparation.STATUS)
        self.assertEqual(document["governing_plan"]["sha256"], PLAN_SHA256)
        self.assertEqual(document["evidence_contract"]["sha256"], EVIDENCE_SHA256)
        reused = {item["role"]: item for item in document["reused_specifications_and_modules"]}
        self.assertEqual(reused["aptarank_io_specification"]["sha256"], IO_SPEC_SHA256)
        self.assertEqual(reused["aptarank_io_module"]["sha256"], IO_MODULE_SHA256)
        self.assertEqual(reused["evidence_contract_module"]["sha256"], EVIDENCE_MODULE_SHA256)
        self.assertIsNone(document["production_membership_count"])
        self.assertIsNone(document["production_blinding_key"])
        self.assertIs(document["production_runner"], False)
        self.assertIs(document["sealed_production_entry_point"], False)

    def test_fail_closed_plan_evidence_module_and_specification_pins(self):
        document = preparation.load_pinned_contract()
        blobs = {
            "preparation_contract": read_bytes(preparation.contract_path()),
            "governing_plan": read_bytes(os.path.join(ROOT, preparation.PLAN_RELATIVE)),
            "evidence_contract": read_bytes(os.path.join(ROOT, preparation.EVIDENCE_CONTRACT_RELATIVE)),
            "aptarank_io_specification": read_bytes(os.path.join(ROOT, preparation.IO_SPEC_RELATIVE)),
            "aptarank_io_module": read_bytes(os.path.join(ROOT, preparation.IO_MODULE_RELATIVE)),
            "evidence_contract_module": read_bytes(os.path.join(ROOT, preparation.EVIDENCE_MODULE_RELATIVE)),
        }
        preparation.verify_external_pins(document, blobs)
        mutated = json.loads(json.dumps(document))
        mutated["governing_plan"]["sha256"] = "0" * 64
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            preparation.validate_contract_document(mutated)
        self.assertEqual(caught.exception.code, "spec_invalid")
        for role in (
            "governing_plan",
            "evidence_contract",
            "aptarank_io_specification",
            "aptarank_io_module",
            "evidence_contract_module",
        ):
            changed = dict(blobs)
            changed[role] = blobs[role] + b" "
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                preparation.verify_external_pins(document, changed)
            self.assertEqual(caught.exception.code, "pin_mismatch")
        evidence = preparation._evidence().load_contract()[0]
        facts = []
        for fact in evidence["facts"]:
            copied = dict(fact)
            if copied["id"] == "length_limits":
                copied["statement"] = "bounds were removed"
            facts.append(copied)
        evidence["facts"] = facts
        spec = {
            "candidate_upload_column_order": ["id", "sequence"],
            "column_types": {"candidate_upload": {"id": "nonempty_opaque_id", "sequence": "uppercase_acgu"}},
        }
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            preparation.assert_reused_validators(evidence, spec)
        self.assertEqual(caught.exception.code, "pin_mismatch")
        with self.assertRaises(preparation.CandidatePreparationError):
            preparation.assert_reused_validators(
                preparation._evidence().load_contract()[0],
                {"candidate_upload_column_order": ["sequence"], "column_types": {}},
            )

    def test_exact_allowed_sample_sizes_and_rejection_of_others(self):
        expected_seeds = {200: 100, 150: 75, 100: 50}
        for count, per_seed in expected_seeds.items():
            result = self.prepare(self.exact[count], membership_count=count)
            manifest = manifest_of(result)
            self.assertEqual(
                [item["requested_membership_count"] for item in manifest["requested_membership_count_per_condition"]],
                [count, count, count, count],
            )
            self.assertEqual(
                [item["selected_membership_count"] for item in manifest["selected_membership_count_per_condition"]],
                [count, count, count, count],
            )
            self.assertEqual(
                manifest["d1_selected_membership_count_by_training_seed"],
                [
                    {"training_seed": 43, "selected_membership_count": per_seed},
                    {"training_seed": 44, "selected_membership_count": per_seed},
                ],
            )
            self.assertEqual(len(private_rows(result)), count * 4)
        for rejected in (0, 1, 50, 99, 101, 149, 151, 199, 201, 250, 800, -100, True, False, 100.0, "100", None):
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                self.prepare(self.exact[100], membership_count=rejected)
            self.assertEqual(caught.exception.code, "membership_count_invalid")

    def test_alphabet_length_identity_and_membership_gates(self):
        for sequence in ("acgu" * 5, "ACGT" * 5, "ACGU" * 4 + "NACGU", ""):
            row = membership("B1", 1, sequence_for(1))
            row["sequence"] = sequence
            row["length"] = len(sequence)
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                self.prepare([row])
            self.assertEqual(caught.exception.code, "sequence_invalid")
        for sequence, code in (("A" * 19, "length_ineligible"), ("A" * 101, "length_ineligible")):
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                self.prepare([membership("B1", 1, sequence)])
            self.assertEqual(caught.exception.code, code)
        mismatched = membership("B1", 1, sequence_for(1))
        mismatched["length"] = 21
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare([mismatched])
        self.assertEqual(caught.exception.code, "length_invalid")
        duplicated = [membership("B0", 1, sequence_for(1)), membership("B1", 2, sequence_for(2))]
        duplicated[1]["source_occurrences"][0]["source_identity"] = source_ids(duplicated[0])[0]
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(duplicated)
        self.assertEqual(caught.exception.code, "duplicate_source_identity")
        repeated_sequence = sequence_for(3)
        repeated = [membership("B0", 1, repeated_sequence), membership("B0", 2, repeated_sequence)]
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(repeated)
        self.assertEqual(caught.exception.code, "repeated_within_condition_membership")
        self.assertNotIn(repeated_sequence, caught.exception.detail)
        scored = membership("B1", 1, sequence_for(4))
        scored["score"] = 0
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare([scored])
        self.assertEqual(caught.exception.code, "input_invalid")

    def test_seed_roles_are_not_invented(self):
        b1 = membership("B1", 1, sequence_for(1))
        b1["source_occurrences"][0]["provenance"]["d1_training_seed"] = 43
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare([b1])
        self.assertEqual(caught.exception.code, "d1_training_seed_invalid")
        for condition in ("B0", "B2"):
            row = membership(condition, 1, sequence_for(1))
            row["source_occurrences"][0]["provenance"]["d1_training_seed"] = None
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                self.prepare([row])
            self.assertEqual(caught.exception.code, "provenance_invalid")
        for seed in (42, 45, None, True):
            row = membership("D1", 1, sequence_for(1), seed=43)
            row["source_occurrences"][0]["provenance"]["d1_training_seed"] = seed
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                self.prepare([row])
            self.assertEqual(caught.exception.code, "d1_training_seed_invalid")
        swapped = membership("D1", 1, sequence_for(1), seed=43)
        swapped["source_occurrences"][0]["provenance"]["technical_block"] = "B"
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare([swapped])
        self.assertEqual(caught.exception.code, "d1_training_seed_invalid")

    def test_input_order_invariance_and_byte_payload(self):
        forward = self.prepare(self.exact[100])
        backward = self.prepare(list(reversed(self.exact[100])))
        rotated = self.prepare(self.exact[100][40:] + self.exact[100][:40])
        self.assertEqual(forward["candidate_upload"], backward["candidate_upload"])
        self.assertEqual(forward["private_membership_key"], rotated["private_membership_key"])
        self.assertEqual(forward["preparation_manifest"], backward["preparation_manifest"])
        self.assertEqual(forward["candidate_upload"], self.prepare(self.exact[100])["candidate_upload"])
        from_bytes = preparation.prepare_candidates(
            payload=jsonl_bytes(self.exact[100]),
            membership_count=100,
            blinding_key=TEST_KEY,
        )
        self.assertEqual(from_bytes["candidate_upload"], forward["candidate_upload"])
        self.assertEqual(from_bytes["private_membership_key"], forward["private_membership_key"])
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            preparation.prepare_candidates(
                records=self.exact[100],
                payload=jsonl_bytes(self.exact[100]),
                membership_count=100,
                blinding_key=TEST_KEY,
            )
        self.assertEqual(caught.exception.code, "input_ambiguous")
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            preparation.prepare_candidates(membership_count=100, blinding_key=TEST_KEY)
        self.assertEqual(caught.exception.code, "input_missing")

    def test_deterministic_sampling_and_exact_d1_balance(self):
        result = self.prepare(self.sampling_rows)
        observed = [(row["condition"], tuple(source_ids(row))) for row in private_rows(result)]
        self.assertEqual(observed, independent_selection(self.sampling_rows, 100))
        seeds = [training_seed(row) for row in private_rows(result) if row["condition"] == "D1"]
        self.assertEqual(seeds, [43] * 50 + [44] * 50)
        sample = self.sampling_rows[0]
        self.assertEqual(
            preparation.membership_priority(sample["condition"], sample["sequence"]),
            independent_priority(sample["condition"], sample["sequence"]),
        )
        self.assertNotIn("source_identity", preparation.membership_priority.__code__.co_varnames)

    def test_shortage_is_exact_and_does_not_replenish_d1_seeds(self):
        short_b0 = [row for row in self.exact[100] if "synthetic-B0-na-0001" not in source_ids(row)]
        self.assertEqual(sum(1 for row in short_b0 if row["condition"] == "B0"), 99)
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(short_b0)
        self.assertEqual(caught.exception.code, "shortage")
        self.assertEqual(
            caught.exception.shortage,
            [
                {
                    "stratum": "condition",
                    "condition": "B0",
                    "requested_membership_count": 100,
                    "eligible_membership_count": 99,
                    "shortage": 1,
                }
            ],
        )
        dropped = False
        short_seed = []
        for row in self.exact[100]:
            if not dropped and row["condition"] == "D1" and training_seed(row) == 44:
                dropped = True
                continue
            short_seed.append(row)
        self.assertTrue(dropped)
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(short_seed)
        self.assertEqual(
            caught.exception.shortage,
            [
                {
                    "stratum": "d1_training_seed",
                    "condition": "D1",
                    "training_seed": 44,
                    "requested_membership_count": 50,
                    "eligible_membership_count": 49,
                    "shortage": 1,
                }
            ],
        )
        only_44 = [
            row
            for row in self.exact[100]
            if not (row["condition"] == "D1" and training_seed(row) == 43)
        ]
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(only_44)
        self.assertEqual([item["training_seed"] for item in caught.exception.shortage], [43])
        self.assertEqual(caught.exception.shortage[0]["eligible_membership_count"], 0)
        self.assertEqual(caught.exception.shortage[0]["requested_membership_count"], 50)

    def test_blinding_key_changes_ids_without_changing_membership(self):
        first = self.prepare(self.shared, blinding_key=TEST_KEY)
        second = self.prepare(self.shared, blinding_key=OTHER_TEST_KEY)
        def membership_view(result):
            return [
                (row["condition"], row["multiplicity"], row["source_occurrences"], row["length"])
                for row in private_rows(result)
            ]
        self.assertEqual(membership_view(first), membership_view(second))
        self.assertEqual(
            [row["sequence"] for row in upload_table(first)],
            [row["sequence"] for row in upload_table(second)],
        )
        self.assertNotEqual(
            [row["candidate_id"] for row in private_rows(first)],
            [row["candidate_id"] for row in private_rows(second)],
        )

    def test_opaque_ids_and_shared_upload_row(self):
        result = self.prepare(self.shared)
        rows = private_rows(result)
        table = upload_table(result)
        by_sequence = {row["sequence"]: row["id"] for row in table}
        shared = sequence_for(0)
        self.assertEqual(len(table), len(by_sequence))
        self.assertEqual([row["sequence"] for row in table].count(shared), 1)
        self.assertEqual(sum(1 for row in rows if row["candidate_id"] == by_sequence[shared]), 4)
        self.assertEqual(manifest_of(result)["upload_row_count"], 397)
        self.assertEqual(len(rows), 400)
        self.assertEqual(result["candidate_upload"].splitlines()[0], b"id,sequence")
        self.assertTrue(result["candidate_upload"].endswith(b"\n"))
        self.assertNotIn(b"\r", result["candidate_upload"])
        for row in rows:
            candidate_id = row["candidate_id"]
            self.assertRegex(candidate_id, r"^cand_[0-9a-f]{32}\Z")
            for identity in source_ids(row):
                self.assertNotIn(identity, candidate_id)
            self.assertNotIn(row["condition"], candidate_id)
            self.assertNotIn(row["comparison_role"], candidate_id)
            self.assertNotIn("synthetic", candidate_id)
            sequence = next(item for item, candidate in by_sequence.items() if candidate == candidate_id)
            self.assertNotIn(sequence, candidate_id)
            self.assertEqual(candidate_id, independent_candidate_id(sequence, TEST_KEY))
        roles = {row["condition"]: row["comparison_role"] for row in rows}
        self.assertEqual(
            roles,
            {
                "B0": "external_baseline",
                "B1": "primary_causal_comparison",
                "B2": "secondary_data_scale_comparator",
                "D1": "primary_causal_comparison",
            },
        )

    def test_provenance_is_preserved_and_lengths_stay_exact(self):
        rows = build_pool(100)
        for row in rows:
            if row["condition"] == "B1":
                row["source_occurrences"][0]["provenance"]["technical_block"] = "B"
                row["source_occurrences"][0]["provenance"]["requested_biological_length"] = 40
        long_row = next(row for row in rows if row["condition"] == "B1")
        long_sequence = sequence_for(900000, 100)
        long_row["sequence"] = long_sequence
        long_row["length"] = 100
        boundary = next(row for row in rows if row["condition"] == "B0")
        boundary["sequence"] = sequence_for(900001, 20)
        boundary["length"] = 20
        result = self.prepare(rows)
        private = private_rows(result)
        b1 = next(row for row in private if source_ids(long_row)[0] in source_ids(row))
        b1_provenance = b1["source_occurrences"][0]["provenance"]
        self.assertEqual(b1["length"], 100)
        self.assertEqual(b1["multiplicity"], 1)
        self.assertIsNone(b1_provenance["d1_training_seed"])
        self.assertEqual(b1_provenance["technical_block"], "B")
        self.assertEqual(b1_provenance["requested_biological_length"], 40)
        self.assertNotIn("sequence", b1)
        self.assertNotIn("sequence", b1["source_occurrences"][0])
        self.assertNotIn(long_sequence.encode("ascii"), result["private_membership_key"])
        upload = {row["sequence"]: row["id"] for row in upload_table(result)}
        self.assertEqual(upload[long_sequence], b1["candidate_id"])
        b0 = next(row for row in private if row["condition"] == "B0")
        self.assertEqual(b0["source_occurrences"][0]["provenance"]["b0_seed"], 7)
        self.assertNotIn("d1_training_seed", b0["source_occurrences"][0]["provenance"])
        b2 = next(row for row in private if row["condition"] == "B2")
        self.assertEqual(b2["source_occurrences"][0]["provenance"]["empirical_null_seed"], 7)
        self.assertNotIn("d1_training_seed", b2["source_occurrences"][0]["provenance"])
        self.assertEqual(boundary["length"], 20)

    def test_manifest_has_no_forbidden_metrics_or_identifiers(self):
        result = self.prepare(self.shared)
        manifest = manifest_of(result)
        payload = result["preparation_manifest"]
        text = payload.decode("ascii")
        self.assertNotIn(b"cand_", payload)
        self.assertNotIn(TEST_KEY, payload)
        self.assertNotIn(TEST_KEY.hex().encode("ascii"), payload)
        for token in ("overlap", "jaccard", "leakage", "nearest"):
            self.assertNotIn(token, text)
        for row in self.shared:
            self.assertNotIn(row["sequence"], text)
            for identity in source_ids(row):
                self.assertNotIn(identity, text)
        self.assertEqual(manifest["status"], preparation.STATUS)
        self.assertIs(manifest["synthetic"], True)
        self.assertIs(manifest["production_inputs_opened"], False)
        self.assertIs(manifest["production_membership_sample_instantiated"], False)
        self.assertIs(manifest["production_blinding_key_instantiated"], False)
        self.assertIs(manifest["production_upload_instantiated"], False)
        self.assertIs(manifest["aptarank_executed"], False)
        self.assertIs(manifest["scientific_result"], False)
        self.assertNotIn("preparation_manifest_sha256", manifest)
        pins = {item["role"]: item["sha256"] for item in manifest["pins"]}
        self.assertEqual(pins["governing_plan"], PLAN_SHA256)
        self.assertEqual(pins["evidence_contract"], EVIDENCE_SHA256)
        self.assertEqual(pins["aptarank_io_specification"], IO_SPEC_SHA256)
        self.assertEqual(pins["aptarank_io_module"], IO_MODULE_SHA256)
        self.assertEqual(pins["evidence_contract_module"], EVIDENCE_MODULE_SHA256)
        self.assertEqual(pins["preparation_contract"], CONTRACT_SHA256)
        module_bytes = read_bytes(os.path.join(MODELLING, "aptarank_candidate_preparation.py"))
        self.assertEqual(pins["preparation_module"], hashlib.sha256(module_bytes).hexdigest())
        self.assertEqual(manifest["candidate_upload_sha256"], result["candidate_upload_sha256"])
        self.assertEqual(manifest["private_membership_key_sha256"], result["private_membership_key_sha256"])

    def test_hmac_collision_fails_closed_and_keys_are_checked(self):
        owners = {}
        collided = None
        for index in range(1, 5000):
            sequence = sequence_for(index)
            digest = hmac.new(
                TEST_KEY,
                preparation.length_delimited_bytes([ID_DOMAIN, sequence]),
                hashlib.sha256,
            ).digest()
            prefix = digest[:1]
            if prefix in owners:
                collided = (owners[prefix], sequence)
                break
            owners[prefix] = sequence
        self.assertIsNotNone(collided)
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            preparation.assign_candidate_ids(collided, TEST_KEY, 1)
        self.assertEqual(caught.exception.code, "opaque_id_collision")
        self.assertIn("not lengthened", caught.exception.detail)
        self.assertEqual(len(preparation.assign_candidate_ids(collided, TEST_KEY, 16)), 2)
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(self.exact[100], truncation_bytes=1)
        self.assertEqual(caught.exception.code, "firewall_invalid")
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(self.exact[100], blinding_key=None)
        self.assertEqual(caught.exception.code, "blinding_key_missing")
        for malformed in (b"", b"short", TEST_KEY + b"!", TEST_KEY[:-1], bytearray(TEST_KEY), "M" * 32, 32):
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                self.prepare(self.exact[100], blinding_key=malformed)
            self.assertEqual(caught.exception.code, "blinding_key_malformed")

    def test_output_firewall(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            os.chdir(tmp)
            try:
                result = self.prepare(self.exact[100])
            finally:
                os.chdir(previous)
            self.assertEqual(os.listdir(tmp), [])
            self.assertTrue(result["candidate_upload"])
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(self.exact[100], path="/tmp/not-used")
        self.assertEqual(caught.exception.code, "filesystem_path_refused")
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(self.exact[100], role="TRAIN")
        self.assertEqual(caught.exception.code, "role_refused")
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            preparation.prepare_candidates(
                payload="/tmp/memberships.jsonl",
                membership_count=100,
                blinding_key=TEST_KEY,
            )
        self.assertEqual(caught.exception.code, "filesystem_path_refused")
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(self.exact[100], operation="deduplicate")
        self.assertEqual(caught.exception.code, "mutation_refused")

    def test_atomic_publication(self):
        result = self.prepare(self.exact[100])
        with tempfile.TemporaryDirectory() as tmp:
            destination = os.path.join(tmp, "prepared-out")
            calls = []
            original = preparation.os.rename

            def spy(source, target):
                calls.append((source, target))
                return original(source, target)

            preparation.os.rename = spy
            try:
                published = preparation.publish_preparation(destination, result)
            finally:
                preparation.os.rename = original
            self.assertEqual(published, os.path.abspath(destination))
            self.assertEqual(len(calls), 1)
            self.assertTrue(os.path.basename(calls[0][0]).startswith(preparation.TEMP_PREFIX))
            self.assertEqual(calls[0][1], os.path.abspath(destination))
            self.assertEqual(
                sorted(os.listdir(destination)),
                ["candidate_upload.csv", "preparation_manifest.json", "private_membership_key.jsonl"],
            )
            self.assertEqual(read_bytes(os.path.join(destination, "candidate_upload.csv")), result["candidate_upload"])
            self.assertEqual(
                read_bytes(os.path.join(destination, "private_membership_key.jsonl")),
                result["private_membership_key"],
            )
            self.assertEqual(
                read_bytes(os.path.join(destination, "preparation_manifest.json")),
                result["preparation_manifest"],
            )
            self.assertEqual([name for name in os.listdir(tmp) if name.startswith(preparation.TEMP_PREFIX)], [])
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                preparation.publish_preparation(destination, result)
            self.assertEqual(caught.exception.code, "destination_directory")
            file_destination = os.path.join(tmp, "already.txt")
            with open(file_destination, "wb") as handle:
                handle.write(b"present")
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                preparation.publish_preparation(file_destination, result)
            self.assertEqual(caught.exception.code, "destination_file")
            link_destination = os.path.join(tmp, "linked")
            os.symlink(file_destination, link_destination)
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                preparation.publish_preparation(link_destination, result)
            self.assertEqual(caught.exception.code, "destination_symlink")
            results_destination = os.path.join(tmp, "results", "out")
            os.makedirs(os.path.dirname(results_destination))
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                preparation.publish_preparation(results_destination, result)
            self.assertEqual(caught.exception.code, "publication_refused")
            parent_link = os.path.join(tmp, "parent-link")
            os.symlink(tmp, parent_link)
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                preparation.publish_preparation(os.path.join(parent_link, "child"), result)
            self.assertEqual(caught.exception.code, "destination_parent_invalid")
            bad = dict(result)
            bad["candidate_upload_sha256"] = "0" * 64
            bad_destination = os.path.join(tmp, "bad-out")
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                preparation.publish_preparation(bad_destination, bad)
            self.assertEqual(caught.exception.code, "publication_validation_failed")
            self.assertFalse(os.path.exists(bad_destination))
            self.assertEqual([name for name in os.listdir(tmp) if name.startswith(preparation.TEMP_PREFIX)], [])

            def fail_reread(temp, payloads, expected):
                raise preparation.CandidatePreparationError("publication_validation_failed", "injected read-back failure")

            original_reread = preparation._reread_temp
            preparation._reread_temp = fail_reread
            cleanup_destination = os.path.join(tmp, "cleanup-out")
            try:
                with self.assertRaises(preparation.CandidatePreparationError) as caught:
                    preparation.publish_preparation(cleanup_destination, result)
            finally:
                preparation._reread_temp = original_reread
            self.assertEqual(caught.exception.code, "publication_validation_failed")
            self.assertFalse(os.path.exists(cleanup_destination))
            self.assertEqual([name for name in os.listdir(tmp) if name.startswith(preparation.TEMP_PREFIX)], [])
            self.assertFalse(stat.S_ISLNK(os.lstat(destination).st_mode))

    def _b1_duplicate_pool(self):
        """Distinct B1 sequences with same-block and cross-block duplicate attempts.

        The dropped sequence also carries a probe attempt whose source identity
        would change a ranking that used one chosen attempt.
        """
        rows = copy.deepcopy(self.sampling_rows)
        ranked = sorted(
            [row for row in rows if row["condition"] == "B1"],
            key=lambda row: (independent_priority("B1", row["sequence"]), row["sequence"].encode("utf-8")),
        )
        self.assertGreater(len(ranked), 100)
        same_block = ranked[0]
        across_blocks = ranked[1]
        dropped = ranked[100]
        same_original = same_block["source_occurrences"][0]
        same_added = occurrence_copy(
            same_original,
            "synthetic-B1-same-block-extra",
            invocation_index=0,
            master_attempt_index=0,
        )
        self.assertEqual(same_added["provenance"]["technical_block"], same_original["provenance"]["technical_block"])
        self.assertLess(same_added["provenance"]["invocation_index"], same_original["provenance"]["invocation_index"])
        same_block["source_occurrences"] = [same_original, same_added]
        same_block["multiplicity"] = 2
        cross_original = across_blocks["source_occurrences"][0]
        cross_added = occurrence_copy(cross_original, "synthetic-B1-other-block-extra", technical_block="B")
        self.assertEqual(cross_original["provenance"]["technical_block"], "A")
        self.assertEqual(cross_added["provenance"]["technical_block"], "B")
        across_blocks["source_occurrences"] = [cross_added, cross_original]
        across_blocks["multiplicity"] = 2
        probe = None
        original_dropped = dropped["source_occurrences"][0]
        for index in range(5000):
            candidate = "synthetic-A-probe-%05d" % index
            probe_occurrence = occurrence_copy(original_dropped, candidate, invocation_index=0)
            dropped["source_occurrences"] = [probe_occurrence, original_dropped]
            dropped["multiplicity"] = 2

            def legacy_rank(row):
                identity = row["source_occurrences"][0]["source_identity"]
                return (
                    legacy_attempt_priority("B1", identity, row["sequence"]),
                    identity.encode("utf-8"),
                    row["sequence"].encode("utf-8"),
                )

            legacy_chosen = [
                row["sequence"]
                for row in sorted((row for row in rows if row["condition"] == "B1"), key=legacy_rank)[:100]
            ]
            if dropped["sequence"] in legacy_chosen:
                probe = candidate
                break
        self.assertIsNotNone(probe)
        oracle = [row["sequence"] for row in ranked[:100]]
        self.assertNotIn(dropped["sequence"], oracle)
        return {
            "rows": rows,
            "oracle": oracle,
            "same_block": same_block,
            "across_blocks": across_blocks,
            "dropped": dropped,
            "probe": probe,
        }

    def test_duplicate_b1_attempts_same_block_and_across_blocks(self):
        fixture = self._b1_duplicate_pool()
        result = self.prepare(fixture["rows"])
        self.assertEqual(selected_sequences(result, "B1"), fixture["oracle"])
        self.assertNotIn(fixture["dropped"]["sequence"], selected_sequences(result, "B1"))
        self.assertNotIn(fixture["probe"].encode("ascii"), result["private_membership_key"])
        private = private_rows(result)
        same = next(row for row in private if "synthetic-B1-same-block-extra" in source_ids(row))
        across = next(row for row in private if "synthetic-B1-other-block-extra" in source_ids(row))
        self.assertEqual(
            [item["provenance"]["technical_block"] for item in same["source_occurrences"]],
            ["A", "A"],
        )
        self.assertEqual(
            [item["source_identity"] for item in same["source_occurrences"]],
            ["synthetic-B1-same-block-extra", source_ids(fixture["same_block"])[0]],
        )
        self.assertEqual(same["multiplicity"], 2)
        self.assertEqual(
            [item["provenance"]["technical_block"] for item in across["source_occurrences"]],
            ["A", "B"],
        )
        self.assertEqual(
            [item["source_identity"] for item in across["source_occurrences"]],
            [source_ids(fixture["across_blocks"])[1], "synthetic-B1-other-block-extra"],
        )
        self.assertEqual(across["multiplicity"], 2)
        self.assertEqual(len(private), 400)
        seeds = [training_seed(row) for row in private if row["condition"] == "D1"]
        self.assertEqual(seeds, [43] * 50 + [44] * 50)
        self.assertEqual(
            preparation.membership_priority("B1", fixture["same_block"]["sequence"]),
            independent_priority("B1", fixture["same_block"]["sequence"]),
        )

    def test_distinct_sequence_input_order_is_invariant(self):
        fixture = self._b1_duplicate_pool()
        forward = self.prepare(fixture["rows"])
        reversed_rows = []
        for row in reversed(fixture["rows"]):
            copied = copy.deepcopy(row)
            copied["source_occurrences"] = list(reversed(copied["source_occurrences"]))
            reversed_rows.append(reorder(copied))
        backward = self.prepare(reversed_rows)
        self.assertEqual(backward["candidate_upload"], forward["candidate_upload"])
        self.assertEqual(backward["private_membership_key"], forward["private_membership_key"])
        self.assertEqual(backward["preparation_manifest"], forward["preparation_manifest"])
        self.assertEqual(selected_sequences(backward, "B1"), fixture["oracle"])

    def test_complete_provenance_retention(self):
        fixture = self._b1_duplicate_pool()
        result = self.prepare(fixture["rows"])
        private = private_rows(result)
        upload = {row["id"]: row["sequence"] for row in upload_table(result)}
        grouped = {(row["condition"], row["sequence"]): row for row in fixture["rows"]}
        retained_ids = []
        for row in private:
            self.assertNotIn("sequence", row)
            sequence = upload[row["candidate_id"]]
            self.assertNotIn(sequence.encode("ascii"), result["private_membership_key"])
            source = grouped[(row["condition"], sequence)]
            expected = canonical_occurrences(row["condition"], source["source_occurrences"])
            self.assertEqual(row["source_occurrences"], expected)
            self.assertEqual(row["multiplicity"], len(expected))
            self.assertEqual(row["multiplicity"], source["multiplicity"])
            retained_ids.extend(source_ids(row))
        unselected = [
            identity
            for row in fixture["rows"]
            for identity in source_ids(row)
            if identity not in retained_ids
        ]
        self.assertIn(fixture["probe"], unselected)
        for identity in unselected:
            self.assertNotIn(identity.encode("ascii"), result["private_membership_key"])
        manifest_text = result["preparation_manifest"].decode("ascii")
        self.assertNotIn(b"cand_", result["preparation_manifest"])
        for token in ("overlap", "jaccard", "leakage", "nearest"):
            self.assertNotIn(token, manifest_text)
        for row in fixture["rows"]:
            self.assertNotIn(row["sequence"], manifest_text)
            for identity in source_ids(row):
                self.assertNotIn(identity, manifest_text)

    def test_multiplicity_mismatch_fails_closed(self):
        sequence = sequence_for(7)
        base = membership("B1", 1, sequence)
        extra = occurrence_copy(base["source_occurrences"][0], "synthetic-B1-extra-attempt", invocation_index=2)
        mismatched = []
        declared_high = copy.deepcopy(base)
        declared_high["multiplicity"] = 2
        mismatched.append(declared_high)
        declared_low = copy.deepcopy(base)
        declared_low["source_occurrences"] = [base["source_occurrences"][0], extra]
        declared_low["multiplicity"] = 1
        mismatched.append(declared_low)
        zero = copy.deepcopy(base)
        zero["multiplicity"] = 0
        zero["source_occurrences"] = []
        mismatched.append(zero)
        boolean = copy.deepcopy(base)
        boolean["multiplicity"] = True
        mismatched.append(boolean)
        for row in mismatched:
            with self.assertRaises(preparation.CandidatePreparationError) as caught:
                self.prepare([row])
            self.assertEqual(caught.exception.code, "multiplicity_mismatch")
            self.assertNotIn(sequence, caught.exception.detail)
        ungrouped = [membership("B1", 1, sequence), membership("B1", 2, sequence)]
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(ungrouped)
        self.assertEqual(caught.exception.code, "repeated_within_condition_membership")
        self.assertNotIn(sequence, caught.exception.detail)
        duplicated_identity = copy.deepcopy(base)
        duplicated_identity["source_occurrences"] = [
            base["source_occurrences"][0],
            occurrence_copy(base["source_occurrences"][0], source_ids(base)[0], invocation_index=3),
        ]
        duplicated_identity["multiplicity"] = 2
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare([duplicated_identity])
        self.assertEqual(caught.exception.code, "duplicate_source_identity")

    def test_ambiguous_d1_provenance_fails_closed(self):
        rows = copy.deepcopy(self.exact[100])
        target = next(row for row in rows if row["condition"] == "D1" and training_seed(row) == 43)
        original = target["source_occurrences"][0]
        other_seed = occurrence_copy(
            original,
            "synthetic-D1-seed-44-attempt",
            d1_training_seed=44,
            technical_block="B",
            invocation_index=0,
        )
        target["source_occurrences"] = [other_seed, original]
        target["multiplicity"] = 2
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            self.prepare(rows)
        self.assertEqual(caught.exception.code, "ambiguous_d1_provenance")
        self.assertNotIn(target["sequence"], caught.exception.detail)
        self.assertIn("no seed is invented or assigned", caught.exception.detail)
        balanced = copy.deepcopy(self.exact[100])
        kept = next(row for row in balanced if row["condition"] == "D1" and training_seed(row) == 43)
        kept_original = kept["source_occurrences"][0]
        same_seed = occurrence_copy(kept_original, "synthetic-D1-same-seed-extra", invocation_index=0)
        kept["source_occurrences"] = [kept_original, same_seed]
        kept["multiplicity"] = 2
        result = self.prepare(balanced)
        manifest = manifest_of(result)
        self.assertEqual(
            manifest["d1_selected_membership_count_by_training_seed"],
            [
                {"training_seed": 43, "selected_membership_count": 50},
                {"training_seed": 44, "selected_membership_count": 50},
            ],
        )
        self.assertEqual(len(private_rows(result)), 400)
        retained = next(row for row in private_rows(result) if "synthetic-D1-same-seed-extra" in source_ids(row))
        self.assertEqual(retained["multiplicity"], 2)
        self.assertEqual(
            [item["provenance"]["d1_training_seed"] for item in retained["source_occurrences"]],
            [43, 43],
        )
        self.assertEqual(
            [item["source_identity"] for item in retained["source_occurrences"]],
            ["synthetic-D1-same-seed-extra", source_ids(kept)[0]],
        )
        self.assertNotIn("sequence", retained)
        self.assertNotIn(kept["sequence"].encode("ascii"), result["private_membership_key"])
        manifest_text = result["preparation_manifest"].decode("ascii")
        self.assertNotIn(kept["sequence"], manifest_text)
        self.assertNotIn("synthetic-D1-same-seed-extra", manifest_text)
        self.assertNotIn(b"cand_", result["preparation_manifest"])

    def test_module_has_no_production_runner_or_protected_locator(self):
        source_path = os.path.join(MODELLING, "aptarank_candidate_preparation.py")
        source = read_text(source_path)
        contract = read_text(preparation.contract_path())
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
        self.assertNotIn("run_production", functions)
        self.assertNotIn("score_candidates", functions)
        needles = (
            "/home/" + "laura/rnagenesis-mres-runs",
            "ft_" + "train.csv",
            "ft_" + "validation.csv",
            "corpus_" + "final",
            "eval" + ".csv",
            "ref" + ".csv",
        )
        for needle in needles:
            self.assertNotIn(needle, source)
            self.assertNotIn(needle, contract)
        with self.assertRaises(preparation.CandidatePreparationError) as caught:
            preparation.main(["prepare"])
        self.assertEqual(caught.exception.code, "production_runner_refused")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(preparation.main([]), 0)


if __name__ == "__main__":
    unittest.main()

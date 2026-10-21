"""Focused synthetic tests for the Section 9 production-preparation adapter."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from scripts.modelling import aptarank_section9_prepare_candidates as section9


ARTIFACT_SHA = "a" * 64


def csv_payload(condition: str, rows: list[dict[str, str]]) -> bytes:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=list(section9.SOURCES[condition]["header"]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue().encode("utf-8")


def source_row(condition: str, sequence: str, multiplicity: int = 1) -> dict[str, str]:
    common = {
        "condition": condition,
        "source_candidate_id": condition + "-U00001",
        "sequence": sequence,
        "sequence_length": str(len(sequence)),
        "condition_multiplicity": str(multiplicity),
        "first_record_id": condition.lower() + ":record:1",
    }
    if condition == "B0":
        common.update({"b0_seed": "4201", "b0_chunk_id": "b0:chunk:1:seed:4201"})
    elif condition == "B1":
        common.update({"technical_block": "A", "checkpoint_identity": "b1:checkpoint"})
    elif condition == "B2":
        common.update({"empirical_null_seed": "42"})
    else:
        common.update({"d1_training_seed": "43", "technical_block": "A"})
    return common


def membership_row(condition: str, occurrence: int = 1, multiplicity: int = 1) -> dict[str, object]:
    record_id = condition.lower() + ":record:" + str(occurrence)
    row = {
        "condition": condition,
        "source_candidate_id": condition + "-U00001",
        "record_id": record_id,
        "multiplicity_group": condition + "-U00001",
        "condition_multiplicity": multiplicity,
        "parsed_length": 20,
        "first_record_id": condition.lower() + ":record:1",
        "is_valid_canonical": True,
        "occurrence_index": occurrence,
        "is_first_occurrence": occurrence == 1,
        "source_artifact_id": condition.lower() + ":artifact",
        "source_artifact_sha256": ARTIFACT_SHA,
    }
    if condition == "B0":
        row.update({"b0_seed": 4201, "b0_chunk_id": "b0:chunk:1:seed:4201", "line_number": occurrence})
    elif condition in ("B1", "D1"):
        row.update({
            "checkpoint_identity": condition.lower() + ":checkpoint",
            "generation_seed": 800000,
            "requested_biological_length": 20,
            "invocation_index": 0,
            "master_attempt_index": occurrence - 1,
            "technical_block": "A",
            "d1_training_seed": None if condition == "B1" else 43,
        })
    else:
        row.update({"attempt_index": 0, "empirical_null_seed": 42, "sampled_length": 20})
    return row


def sequence_for(index: int, length: int = 20) -> str:
    alphabet = "ACGU"
    output = []
    value = index
    for _ in range(length):
        output.append(alphabet[value % 4])
        value //= 4
    return "".join(output)


class Section9PreparationTests(unittest.TestCase):
    def test_flat_provenance_join_builds_exact_m9b_records(self):
        sequences = {condition: sequence_for(index + 1) for index, condition in enumerate(section9.CONDITIONS)}
        payloads = {
            condition: csv_payload(condition, [source_row(condition, sequences[condition], 2 if condition == "B1" else 1)])
            for condition in section9.CONDITIONS
        }
        membership_rows = [membership_row("B0")]
        membership_rows.extend([membership_row("B1", 1, 2), membership_row("B1", 2, 2)])
        membership_rows.extend([membership_row("B2"), membership_row("D1")])
        membership = b"".join(
            json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n" for row in membership_rows
        )
        replacements = {
            condition: {**section9.SOURCES[condition], "rows": 1, "eligible": 1, "below": 0, "above": 0}
            for condition in section9.CONDITIONS
        }
        with patch.dict(section9.SOURCES, replacements, clear=True):
            records, sources, accounting = section9.build_records(
                payloads,
                membership,
                expected_attempt_rows=5,
                expected_attempt_rows_by_condition={"B0": 1, "B1": 2, "B2": 1, "D1": 1},
            )
        self.assertEqual(len(records), 4)
        b1 = next(row for row in records if row["condition"] == "B1")
        self.assertEqual(b1["multiplicity"], 2)
        self.assertEqual([item["source_identity"] for item in b1["source_occurrences"]], ["b1:record:1", "b1:record:2"])
        self.assertIsNone(b1["source_occurrences"][0]["provenance"]["d1_training_seed"])
        d1 = next(row for row in records if row["condition"] == "D1")
        self.assertEqual(d1["source_occurrences"][0]["provenance"]["d1_training_seed"], 43)
        self.assertEqual(accounting["attempt_membership_rows"], 5)
        self.assertEqual(accounting["eligible_unique_rows_by_condition"], {condition: 1 for condition in section9.CONDITIONS})
        self.assertEqual(set(sources), set(section9.CONDITIONS))

    def test_selected_source_key_preserves_800_memberships_and_d1_balance(self):
        upload_rows = []
        private_rows = []
        sources = {condition: {} for condition in section9.CONDITIONS}
        serial = 0
        for condition in section9.CONDITIONS:
            for offset in range(200):
                sequence = sequence_for(serial + 1)
                candidate_id = "cand_" + format(serial + 1, "032x")
                source_id = condition + "-U" + format(offset + 1, "05d")
                upload_rows.append({"id": candidate_id, "sequence": sequence})
                sources[condition][source_id] = {
                    "sequence": sequence,
                    "length": len(sequence),
                    "multiplicity": 1,
                }
                provenance = {}
                if condition == "D1":
                    provenance["d1_training_seed"] = 43 if offset < 100 else 44
                if condition == "B1":
                    provenance["technical_block"] = "A" if offset < 100 else "B"
                private_rows.append({
                    "candidate_id": candidate_id,
                    "condition": condition,
                    "length": len(sequence),
                    "multiplicity": 1,
                    "source_occurrences": [{"source_identity": condition.lower() + ":" + str(offset), "provenance": provenance}],
                })
                serial += 1
        handle = io.StringIO(newline="")
        writer = csv.DictWriter(handle, fieldnames=["id", "sequence"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(upload_rows)
        upload = handle.getvalue().encode("utf-8")
        private_key = b"".join(
            json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n" for row in private_rows
        )
        source_key, summary = section9.selected_source_key(upload, private_key, sources)
        document = json.loads(source_key)
        self.assertEqual(len(document["memberships"]), 800)
        self.assertEqual(summary["selected_memberships_by_condition"], {condition: 200 for condition in section9.CONDITIONS})
        self.assertEqual(summary["d1_selected_by_training_seed"], {"43": 100, "44": 100})
        self.assertEqual(summary["b1_selected_memberships_touching_block"], {"A": 100, "B": 100})
        self.assertNotIn(sequence_for(1), source_key.decode("utf-8"))

    def test_run_sheet_freezes_evaluation_preset_and_ndm1_target(self):
        upload = b"id,sequence\ncand_00000000000000000000000000000001,ACGUACGUACGUACGUACGU\n"
        expected = section9.expected_cells(upload)
        target = section9.target_settings()
        run = json.loads(section9.run_sheet(upload, b"key\n", b"source\n", expected, target))
        self.assertEqual(run["settings"]["preset"], "Evaluation")
        self.assertEqual(run["settings"]["candidate_shuffled_controls"], 99)
        self.assertEqual(run["settings"]["ensemble_samples"], 200)
        self.assertEqual(run["settings"]["expected_scoring_signature"], "95a49467ef3c6186")
        target_document = json.loads(target)
        self.assertEqual(target_document["pdb_id"], "5ZGX")
        self.assertEqual(target_document["prepared_target_identifier"], "0fde4d5e4370")
        self.assertEqual(target_document["target_site_residues"], [120, 122, 124, 189, 208, 250])

    def test_publication_refuses_existing_destination_and_preserves_private_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "restricted"
            files = {"secret.bin": b"x" * 32, "key.json": b"{}\n"}
            section9.publish_directory(destination, files, set(files))
            self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
            self.assertEqual((destination / "secret.bin").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(section9.PreparationError):
                section9.publish_directory(destination, files, set(files))


if __name__ == "__main__":
    unittest.main()

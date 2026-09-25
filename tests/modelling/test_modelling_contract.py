"""Synthetic boundary tests; no biological corpus files or GPU dependencies."""
import copy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "modelling_contract", ROOT / "scripts/modelling/verify_modelling_contract.py"
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def fixture(role="TRAIN"):
    rows = []
    for index, core in enumerate(("ACGU", "GCAA")):
        rows.append({
            "scientific_identity_id": f"synthetic_{index}",
            "sequence_core": core, "sequence_core_sha256": hashlib.sha256(core.encode()).hexdigest(),
            "sequence_length_core": str(len(core)), "cluster_id": f"cluster_{index}",
            "canonical_target_name": f"target_{index}", "partition": "FT", "ft_split": role,
        })
    spec = {
        "counts": {"identities": 2, "cores": 2, "clusters": 2, "targets": 2},
        "identity_set_hash": hashlib.sha256("\n".join(
            f'{r["scientific_identity_id"]}\t{r["cluster_id"]}\t{r["sequence_core_sha256"]}' for r in rows
        ).encode()).hexdigest(),
        "cluster_set_hash": hashlib.sha256(b"cluster_0\ncluster_1").hexdigest(),
    }
    return rows, spec


def csv_bytes(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


class ContractBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT / m.CONTRACT_PATH).read_text())

    def test_restricted_and_unknown_roles_denied_before_any_file_read(self):
        for role, purpose in (("REF", "fit"), ("REF", "aptarank_calibrate"),
                              ("EVAL", "fit"), ("EVAL", "final_evaluate_after_unlock"),
                              ("UNKNOWN", "fit")):
            with self.subTest(role=role, purpose=purpose), patch.object(Path, "read_bytes") as read:
                with self.assertRaisesRegex(m.ContractError, "prohibited"):
                    m.read_authorized(self.contract, role, purpose, Path("/unused"))
                read.assert_not_called()

    def test_validation_fitting_denied_before_read(self):
        with patch.object(Path, "read_bytes") as read:
            with self.assertRaisesRegex(m.ContractError, "prohibited"):
                m.read_authorized(self.contract, "VALIDATION", "fit", Path("/unused"))
            read.assert_not_called()

    def test_permission_tampering_denied_before_read(self):
        altered = copy.deepcopy(self.contract)
        altered["roles"]["TRAIN"]["allowed"].append("checkpoint_select")
        with patch.object(Path, "read_bytes") as read:
            with self.assertRaisesRegex(m.ContractError, "invalid role permissions"):
                m.read_authorized(altered, "TRAIN", "fit", Path("/unused"))
            read.assert_not_called()

    def test_changed_frozen_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "corpus_final.txt").write_text("ACGU\n")
            with self.assertRaisesRegex(m.ContractError, "SHA256 mismatch"):
                m.read_authorized(self.contract, "TRAIN_TEXT", "fit", folder)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "corpus_final.txt").symlink_to(folder / "not_present")
            with self.assertRaisesRegex(m.ContractError, "symlinks"):
                m.read_authorized(self.contract, "TRAIN_TEXT", "fit", folder)

    def test_development_directory_denies_extra_files_without_opening_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in ("ft_train.csv", "ft_validation.csv", "corpus_final.txt"):
                (folder / name).touch()
            m.check_development_directory(self.contract, folder)
            for name in ("ref.csv", "eval.csv", "corpus_final.csv", "unexpected"):
                extra = folder / name
                extra.touch()
                with self.subTest(name=name), patch.object(Path, "read_bytes") as read:
                    with self.assertRaisesRegex(m.ContractError, "exactly"):
                        m.verify(self.contract, folder, "development")
                    read.assert_not_called()
                extra.unlink()

    def test_valid_synthetic_csv_and_text(self):
        rows, spec = fixture()
        self.assertEqual(m.check_csv(csv_bytes(rows), "TRAIN", spec), rows)
        self.assertEqual(m.check_train_text(b"ACGU\nGCAA\n", rows,
                         {"counts": {"lines": 2, "unique_cores": 2}}), ["ACGU", "GCAA"])

    def test_noncanonical_sequences_are_rejected_without_normalisation(self):
        for invalid in ("ACGT", "acgu", " ACGU", "ACGU ", "ACGN", ""):
            rows, spec = fixture()
            rows[0]["sequence_core"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(m.ContractError):
                m.check_csv(csv_bytes(rows), "TRAIN", spec)

    def test_mislabelled_csv_role_is_rejected(self):
        rows, spec = fixture("VALIDATION")
        with self.assertRaisesRegex(m.ContractError, "role assignment"):
            m.check_csv(csv_bytes(rows), "TRAIN", spec)

    def test_duplicate_and_reordered_train_text_rejected(self):
        rows, _ = fixture()
        spec = {"counts": {"lines": 2, "unique_cores": 2}}
        for raw in (b"ACGU\nACGU\n", b"GCAA\nACGU\n", b"ACGU\n"):
            with self.subTest(raw=raw), self.assertRaises(m.ContractError):
                m.check_train_text(raw, rows, spec)

    def test_each_semantic_overlap_is_rejected(self):
        train, _ = fixture()
        validation = [{"sequence_core": "UUCC", "cluster_id": "other", "scientific_identity_id": "other"}]
        self.assertTrue(all(v == 0 for v in m.check_overlap(train, validation).values()))
        for column in ("sequence_core", "cluster_id", "scientific_identity_id"):
            changed = copy.deepcopy(validation)
            changed[0][column] = train[0][column]
            with self.subTest(column=column), self.assertRaisesRegex(m.ContractError, column):
                m.check_overlap(train, changed)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(m.ContractError, "Duplicate JSON key"):
            m.parse_json('{"eval_locked": true, "eval_locked": false}')


if __name__ == "__main__":
    unittest.main()

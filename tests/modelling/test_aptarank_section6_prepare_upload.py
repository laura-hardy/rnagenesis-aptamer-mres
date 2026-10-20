"""Focused filesystem tests for the Section 6 production-preparation adapter."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODELLING = ROOT / "scripts/modelling"
if str(MODELLING) not in sys.path:
    sys.path.insert(0, str(MODELLING))

import aptarank_section6_prepare_upload as preparation


@unittest.skipUnless(sys.platform == "darwin", "the production adapter is Mac-local")
class Section6PreparationFilesystemTests(unittest.TestCase):
    def test_destination_boundaries(self):
        public = ROOT / "data/aptarank_eval/sequence/synthetic-test"
        restricted = Path("/private/tmp/section6-restricted-synthetic-test")
        self.assertEqual(
            preparation.validate_destinations(ROOT, public, restricted),
            str(restricted),
        )
        with self.assertRaises(preparation.PreparationError):
            preparation.validate_destinations(ROOT, public, ROOT / "data/aptarank_eval/restricted/test")
        with self.assertRaises(preparation.PreparationError):
            preparation.validate_destinations(ROOT, ROOT / "results/test", restricted)

    def test_atomic_publication_refuses_an_existing_empty_directory(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as parent_text:
            parent = Path(parent_text)
            destination = parent / "package"
            destination.mkdir()
            with self.assertRaises(preparation.PreparationError):
                preparation.publish(destination, {"record.txt": (b"new\n", 0o600)})
            self.assertEqual(list(destination.iterdir()), [])

    def test_atomic_publication_refuses_a_racing_destination(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as parent_text:
            parent = Path(parent_text)
            destination = parent / "package"
            original = preparation.rename_noreplace

            def create_destination_then_rename(source, target):
                target.mkdir()
                original(source, target)

            with mock.patch.object(preparation, "rename_noreplace", side_effect=create_destination_then_rename):
                with self.assertRaises(preparation.PreparationError):
                    preparation.publish(destination, {"record.txt": (b"new\n", 0o600)})
            self.assertTrue(destination.is_dir())
            self.assertEqual(list(destination.iterdir()), [])
            self.assertEqual(list(parent.glob(".package.*")), [])

    def test_failed_publication_reports_cleanup_failure(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as parent_text:
            destination = Path(parent_text) / "package"
            with mock.patch.object(preparation, "rename_noreplace", side_effect=OSError("publish failed")):
                with mock.patch.object(preparation, "cleanup_temporary", side_effect=OSError("cleanup failed")):
                    with self.assertRaisesRegex(preparation.PreparationError, "cleanup also failed"):
                        preparation.publish(destination, {"record.txt": (b"new\n", 0o600)})

    def test_public_failure_retains_published_restricted_output(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as parent_text:
            parent = Path(parent_text)
            restricted = parent / "restricted"
            public = parent / "public"
            original = preparation.publish
            calls = 0

            def publish_restricted_then_fail(destination, files):
                nonlocal calls
                calls += 1
                if calls == 1:
                    original(destination, files)
                    return
                raise OSError("public publish failed")

            with mock.patch.object(preparation, "publish", side_effect=publish_restricted_then_fail):
                with self.assertRaisesRegex(preparation.PreparationError, "restricted output was retained"):
                    preparation.publish_outputs(
                        restricted,
                        {"secret.bin": (b"secret", 0o600)},
                        public,
                        {"upload.csv": (b"id,sequence\n", 0o600)},
                    )
            self.assertEqual((restricted / "secret.bin").read_bytes(), b"secret")
            self.assertFalse(public.exists())

    def test_successful_publication_is_durable_and_non_overwriting(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as parent_text:
            destination = Path(parent_text) / "package"
            preparation.publish(destination, {"nested/record.txt": (b"value\n", 0o600)})
            record = destination / "nested/record.txt"
            self.assertEqual(record.read_bytes(), b"value\n")
            self.assertEqual(record.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(preparation.PreparationError):
                preparation.publish(destination, {"nested/record.txt": (b"replacement\n", 0o600)})
            self.assertEqual(record.read_bytes(), b"value\n")


if __name__ == "__main__":
    unittest.main()

"""Focused tests for the read-only raw-data inventory script."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from inventory_raw_data import (  # noqa: E402
    INVENTORY_COLUMNS,
    FileInspection,
    enrich_inventory_rows,
    human_size,
    is_transient_raw_file,
    load_previous_inventory,
    match_sequence_columns,
    recommend_s0_status,
    redact_sequence_like_column_names,
)

# Contiguous nucleotide strings of this length must not appear in tracked outputs.
UNREDACTED_NT_RE = re.compile(r"[ACGTUNacgtun]{20,}")


def test_inventory_columns_include_extended_fields() -> None:
    for col in (
        "documentation_files",
        "recommended_S0_status",
        "change_since_previous_inventory",
        "current_hash",
        "readme_notes",
    ):
        assert col in INVENTORY_COLUMNS


def test_match_sequence_columns_prefers_real_sequence() -> None:
    cols = [
        "sequence_version",
        "sequence_length",
        "sequence_deposited",
        "target_raw",
    ]
    assert match_sequence_columns(cols)[0] == "sequence_deposited"


def test_human_size() -> None:
    assert human_size(500) == "500 B"
    assert "KB" in human_size(2048)


def test_redact_sequence_like_column_names_headerless_three_col() -> None:
    # Build a ≥20-nt synthetic token at runtime so the tracked test file itself
    # does not contain a contiguous nucleotide run of length 20+.
    seq_token = ("ACGT" * 5) + "A"  # 21 nt
    colnames = [seq_token, "3.037", "-2.599"]
    assert len(re.sub(r"\s+", "", seq_token)) >= 20
    assert redact_sequence_like_column_names(colnames) == "headerless_three_column_file"
    assert UNREDACTED_NT_RE.search(redact_sequence_like_column_names(colnames)) is None
    source = Path(__file__).read_text(encoding="utf-8")
    assert UNREDACTED_NT_RE.search(source) is None


def test_recommend_s0_ignores_excel_lock_and_ds_store() -> None:
    lock = FileInspection(
        relative_path="data/raw/x/~$extracted_data.xlsx",
        top_level_source="x",
        file_name="~$extracted_data.xlsx",
        extension="xlsx",
        file_size_bytes=1,
        file_size_human="1 B",
        last_modified="",
    )
    ds = FileInspection(
        relative_path="data/raw/.DS_Store",
        top_level_source="(raw_root)",
        file_name=".DS_Store",
        extension="",
        file_size_bytes=1,
        file_size_human="1 B",
        last_modified="",
    )
    assert recommend_s0_status(lock) == "not_relevant_to_protein_aptamer_corpus"
    assert recommend_s0_status(ds) == "not_relevant_to_protein_aptamer_corpus"


@pytest.mark.parametrize(
    "name",
    [
        ".DS_Store",
        ".ds_store",
        ".Rhistory",
        ".rhistory",
        "~$extracted_data.xlsx",
        "~$workbook.xlsx",
        "Thumbs.db",
        "thumbs.db",
        "desktop.ini",
        "Desktop.ini",
    ],
)
def test_transient_basenames_are_excluded(name: str) -> None:
    assert is_transient_raw_file(name) is True
    assert is_transient_raw_file(Path("data/raw/demo") / name) is True


def test_legitimate_hidden_research_file_is_not_transient() -> None:
    assert is_transient_raw_file(".hidden_selection_notes.csv") is False
    assert is_transient_raw_file("data/raw/demo/.aptamer_manifest.csv") is False
    assert is_transient_raw_file("table6_d9_ndm1_sequences.csv") is False


def test_transient_changes_do_not_reduce_substantive_hash_success(
    tmp_path: Path,
) -> None:
    prior_path = tmp_path / "prior.csv"
    with prior_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["relative_path", "sha256", "row_count", "column_names"],
        )
        w.writeheader()
        w.writerow(
            {
                "relative_path": "data/raw/demo/source.csv",
                "sha256": "abc",
                "row_count": "2",
                "column_names": "id|label",
            }
        )
        w.writerow(
            {
                "relative_path": "data/raw/demo/.DS_Store",
                "sha256": "old_ds",
                "row_count": "",
                "column_names": "",
            }
        )
        w.writerow(
            {
                "relative_path": "data/raw/demo/~$lock.xlsx",
                "sha256": "old_lock",
                "row_count": "",
                "column_names": "",
            }
        )
    previous = load_previous_inventory(prior_path)
    # Only the substantive file is present in the new inventory rows; transient
    # prior paths are filtered by enrich_inventory_rows.
    row = FileInspection(
        relative_path="data/raw/demo/source.csv",
        top_level_source="demo",
        file_name="source.csv",
        extension="csv",
        file_size_bytes=10,
        file_size_human="10 B",
        last_modified="",
        sha256="abc",
        row_count="2",
        column_names="id|label",
    )
    changes = enrich_inventory_rows(
        [row],
        previous=previous,
        docs_by_source={},
        repo_root=REPO_ROOT,
    )
    assert changes["n_unchanged"] == 1
    assert changes["n_modified"] == 0
    assert changes["n_removed"] == 0
    assert changes["removed"] == []


def test_ignored_transient_paths_reported_in_summary_shape() -> None:
    # Contract for the summary payload written by main(): aggregate count + paths.
    payload = {
        "n_ignored_on_disk": 2,
        "paths_on_disk": [
            "data/raw/.DS_Store",
            "data/raw/demo/.Rhistory",
        ],
        "n_previous_inventory_transient_paths": 1,
        "previous_inventory_transient_paths": [
            "data/raw/demo/~$lock.xlsx",
        ],
    }
    assert payload["n_ignored_on_disk"] == len(payload["paths_on_disk"])
    assert all(is_transient_raw_file(p) for p in payload["paths_on_disk"])
    assert all(
        is_transient_raw_file(p) for p in payload["previous_inventory_transient_paths"]
    )
    blob = json.dumps(payload)
    assert UNREDACTED_NT_RE.search(blob) is None


def test_inventory_deterministic_sort_key_for_substantive_rows() -> None:
    rows = [
        FileInspection(
            relative_path="data/raw/b/file.csv",
            top_level_source="b",
            file_name="file.csv",
            extension="csv",
            file_size_bytes=1,
            file_size_human="1 B",
            last_modified="",
            sha256="1",
        ),
        FileInspection(
            relative_path="data/raw/a/file.csv",
            top_level_source="a",
            file_name="file.csv",
            extension="csv",
            file_size_bytes=1,
            file_size_human="1 B",
            last_modified="",
            sha256="2",
        ),
    ]
    ordered = sorted(rows, key=lambda r: r.relative_path)
    assert [r.relative_path for r in ordered] == [
        "data/raw/a/file.csv",
        "data/raw/b/file.csv",
    ]
    # Transient names never participate in the authoritative row set.
    assert not any(is_transient_raw_file(r.relative_path) for r in ordered)


def test_recommend_s0_excludes_latent_coordinate_file() -> None:
    latent = FileInspection(
        relative_path="data/raw/Aptadiff_datasetA/datasetA_IGFBP3_x_z.csv",
        top_level_source="Aptadiff_datasetA",
        file_name="datasetA_IGFBP3_x_z.csv",
        extension="csv",
        file_size_bytes=10,
        file_size_human="10 B",
        last_modified="",
        apparent_role="latent_coordinate_or_embedding",
    )
    assert recommend_s0_status(latent) == "not_relevant_to_protein_aptamer_corpus"


def test_enrich_same_hash_not_false_modified(tmp_path: Path) -> None:
    prior_path = tmp_path / "prior.csv"
    with prior_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["relative_path", "sha256", "row_count", "column_names"],
        )
        w.writeheader()
        w.writerow(
            {
                "relative_path": "data/raw/AptaDB/aptamer.csv",
                "sha256": "abc",
                "row_count": "1293",
                "column_names": "Apta_index|Sequence|Molarity of 1 µg/µl solution",
            }
        )
    previous = load_previous_inventory(prior_path)
    row = FileInspection(
        relative_path="data/raw/AptaDB/aptamer.csv",
        top_level_source="AptaDB",
        file_name="aptamer.csv",
        extension="csv",
        file_size_bytes=10,
        file_size_human="10 B",
        last_modified="",
        sha256="abc",
        row_count="1293",
        column_names="Apta_index|Sequence|Molarity of 1 Âµg/Âµl solution",
    )
    changes = enrich_inventory_rows(
        [row],
        previous=previous,
        docs_by_source={},
        repo_root=REPO_ROOT,
    )
    assert row.change_since_previous_inventory.startswith("unchanged")
    assert changes["n_modified"] == 0
    assert changes["n_unchanged"] == 1


@pytest.mark.skipif(
    not (REPO_ROOT / "docs" / "data_curation" / "raw_data_inventory.csv").is_file(),
    reason="inventory CSV not generated yet",
)
def test_current_inventory_covers_no_li_et_al() -> None:
    inv = REPO_ROOT / "docs" / "data_curation" / "raw_data_inventory.csv"
    rows = list(csv.DictReader(inv.open(encoding="utf-8")))
    assert rows
    assert all("li_et_al" not in r["relative_path"] for r in rows)
    paths = {r["relative_path"] for r in rows}
    assert "data/raw/AptaDB/interaction.csv" in paths
    assert "data/raw/riboaptamer/all_sequences_509_rows.csv" in paths


@pytest.mark.skipif(
    not (REPO_ROOT / "docs" / "data_curation" / "raw_data_inventory.csv").is_file(),
    reason="inventory CSV not generated yet",
)
def test_tracked_inventory_csv_has_no_unredacted_nucleotide_strings() -> None:
    inv = REPO_ROOT / "docs" / "data_curation" / "raw_data_inventory.csv"
    text = inv.read_text(encoding="utf-8")
    match = UNREDACTED_NT_RE.search(text)
    assert match is None, f"unredacted nucleotide run in inventory CSV: {match.group(0)[:40]}"


@pytest.mark.skipif(
    not (REPO_ROOT / "docs" / "data_curation" / "raw_data_inventory_summary.json").is_file(),
    reason="inventory summary JSON not generated yet",
)
def test_tracked_inventory_json_has_no_unredacted_nucleotide_strings() -> None:
    path = REPO_ROOT / "docs" / "data_curation" / "raw_data_inventory_summary.json"
    text = path.read_text(encoding="utf-8")
    match = UNREDACTED_NT_RE.search(text)
    assert match is None, f"unredacted nucleotide run in inventory JSON: {match.group(0)[:40]}"
    summary = json.loads(text)
    overlap = summary.get("overlap", {})
    assert "cross_file_sequence_overlap_sample" not in overlap
    assert "cross_file_sequence_target_pair_overlap_sample" not in overlap
    assert "n_cross_file_sequence_overlaps" in overlap
    assert "n_cross_file_sequence_target_pair_overlaps" in overlap


@pytest.mark.skipif(
    not (REPO_ROOT / "docs" / "data_curation" / "raw_data_inventory.csv").is_file(),
    reason="inventory CSV not generated yet",
)
def test_igfbp3_x_z_classified_as_latent_not_sequence_input() -> None:
    inv = REPO_ROOT / "docs" / "data_curation" / "raw_data_inventory.csv"
    rows = {r["relative_path"]: r for r in csv.DictReader(inv.open(encoding="utf-8"))}
    key = "data/raw/Aptadiff_datasetA/datasetA_IGFBP3_x_z.csv"
    assert key in rows
    row = rows[key]
    assert row["column_names"] == "headerless_three_column_file"
    assert UNREDACTED_NT_RE.search(row["column_names"] or "") is None
    assert row["apparent_role"] == "latent_coordinate_or_embedding"
    assert row["recommended_S0_status"] == "not_relevant_to_protein_aptamer_corpus"
    assert "latent" in (row["sequence_type"] or "").lower()
    assert not (row.get("sequence_column_candidates") or "").strip()

"""Tests for S0a source-registry validation (no biological sequences)."""

from __future__ import annotations

import csv
import gzip
import hashlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from s0_build_registry import (  # noqa: E402
    REQUIRED_COLUMNS,
    RegistryError,
    RegistrySpecRow,
    build_registry,
    count_csv_data_rows,
    count_ntriples_gzip_statements,
    detect_csv_text_encoding,
    load_registry_spec,
    main,
    validate_registered_file,
)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_utf8_sig_csv(
    path: Path, fieldnames: list[str], rows: list[dict[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _synthetic_input_rows(n: int = 3) -> list[dict[str, str]]:
    """Non-biological placeholder rows (no aptamer-like sequences)."""
    return [
        {
            "record_id": str(i),
            "label": f"item_{i}",
            "payload": f"token-{i}-AAAA",
        }
        for i in range(1, n + 1)
    ]


def _make_repo_tree(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "demo").mkdir(parents=True)
    (repo / "data" / "interim" / "registry").mkdir(parents=True)
    return repo


def _hash_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _spec_row(
    *,
    source_key: str = "demo",
    source_dataset: str = "demo_v1",
    path: str = "data/raw/demo/demo.csv",
    sha256: str,
    n_rows_expected: int = 3,
    tier: str = "1",
    redistribution_status: str = "unknown",
    notes: str = "synthetic fixture",
) -> dict[str, str]:
    return {
        "source_key": source_key,
        "source_dataset": source_dataset,
        "path": path,
        "sha256": sha256,
        "n_rows_expected": str(n_rows_expected),
        "snapshot_date": "2026-08-04",
        "tier": tier,
        "redistribution_status": redistribution_status,
        "notes": notes,
    }


def _inventory_row(
    *,
    relative_path: str,
    sha256: str,
    row_count: str = "3",
    recommended_s0_status: str = "include_as_authoritative_input",
) -> dict[str, str]:
    return {
        "relative_path": relative_path,
        "sha256": sha256,
        "row_count": row_count,
        "recommended_S0_status": recommended_s0_status,
    }


def _write_minimal_inventory(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "relative_path",
        "sha256",
        "row_count",
        "recommended_S0_status",
    ]
    _write_csv(path, fieldnames, rows)


@pytest.fixture
def demo_repo(tmp_path: Path) -> Path:
    repo = _make_repo_tree(tmp_path)
    input_path = repo / "data" / "raw" / "demo" / "demo.csv"
    _write_utf8_sig_csv(
        input_path,
        ["record_id", "label", "payload"],
        _synthetic_input_rows(3),
    )
    digest = _hash_path(input_path)
    spec_path = repo / "config" / "source_registry.csv"
    _write_csv(
        spec_path,
        list(REQUIRED_COLUMNS),
        [_spec_row(sha256=digest, n_rows_expected=3)],
    )
    inv_path = repo / "docs" / "data_curation" / "raw_data_inventory.csv"
    _write_minimal_inventory(
        inv_path,
        [
            _inventory_row(
                relative_path="data/raw/demo/demo.csv",
                sha256=digest,
                row_count="3",
            )
        ],
    )
    return repo


def test_successful_validation_and_deterministic_output(demo_repo: Path) -> None:
    output = demo_repo / "data" / "interim" / "registry" / "source_registry.csv"
    result = build_registry(
        repo_root=demo_repo,
        registry_spec=demo_repo / "config" / "source_registry.csv",
        inventory_path=demo_repo / "docs" / "data_curation" / "raw_data_inventory.csv",
        output_path=output,
    )
    assert result.validated == 1
    assert len(result.rows) == 1
    assert output.is_file()
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0].keys()) == list(REQUIRED_COLUMNS)
    assert rows[0]["source_key"] == "demo"
    assert rows[0]["path"] == "data/raw/demo/demo.csv"
    text = output.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "\r" not in text


def test_embedded_newline_row_count(tmp_path: Path) -> None:
    path = tmp_path / "embedded.csv"
    # One header + two logical data rows; second field embeds a newline.
    content = 'id,note\n1,"line1\nline2"\n2,plain\n'
    path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
    assert count_csv_data_rows(path) == 2
    # Physical newlines exceed logical data rows.
    assert path.read_text(encoding="utf-8-sig").count("\n") > 2


def test_sha256_mismatch_hard_failure(demo_repo: Path) -> None:
    spec = demo_repo / "config" / "source_registry.csv"
    rows = list(csv.DictReader(spec.open(encoding="utf-8", newline="")))
    rows[0]["sha256"] = "0" * 64
    _write_csv(spec, list(REQUIRED_COLUMNS), rows)
    with pytest.raises(RegistryError, match="SHA-256 mismatch"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=spec,
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


def test_row_count_mismatch_hard_failure(demo_repo: Path) -> None:
    spec = demo_repo / "config" / "source_registry.csv"
    rows = list(csv.DictReader(spec.open(encoding="utf-8", newline="")))
    rows[0]["n_rows_expected"] = "999"
    _write_csv(spec, list(REQUIRED_COLUMNS), rows)
    with pytest.raises(RegistryError, match="Row-count mismatch"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=spec,
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


def test_missing_registered_input_hard_failure(demo_repo: Path) -> None:
    (demo_repo / "data" / "raw" / "demo" / "demo.csv").unlink()
    with pytest.raises(RegistryError, match="missing"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=demo_repo / "config" / "source_registry.csv",
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


def test_inconsistent_source_dataset_for_same_key_rejected(demo_repo: Path) -> None:
    digest = _hash_path(demo_repo / "data" / "raw" / "demo" / "demo.csv")
    other = demo_repo / "data" / "raw" / "demo" / "other.csv"
    _write_utf8_sig_csv(
        other, ["record_id", "label", "payload"], _synthetic_input_rows(2)
    )
    other_digest = _hash_path(other)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(sha256=digest, n_rows_expected=3),
            _spec_row(
                source_key="demo",
                source_dataset="demo_v2",
                path="data/raw/demo/other.csv",
                sha256=other_digest,
                n_rows_expected=2,
            ),
        ],
    )
    with pytest.raises(RegistryError, match="inconsistent source_dataset"):
        load_registry_spec(demo_repo / "config" / "source_registry.csv")


def test_duplicate_registered_path_rejection(demo_repo: Path) -> None:
    digest = _hash_path(demo_repo / "data" / "raw" / "demo" / "demo.csv")
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(sha256=digest, n_rows_expected=3),
            _spec_row(
                source_key="demo2",
                source_dataset="demo_v2",
                path="data/raw/demo/demo.csv",
                sha256=digest,
                n_rows_expected=3,
            ),
        ],
    )
    with pytest.raises(RegistryError, match="Duplicate registered path"):
        load_registry_spec(demo_repo / "config" / "source_registry.csv")


def test_missing_or_extra_columns_rejection(demo_repo: Path) -> None:
    bad = demo_repo / "config" / "bad_registry.csv"
    _write_csv(
        bad,
        ["source_key", "path", "sha256"],
        [{"source_key": "x", "path": "data/raw/demo/demo.csv", "sha256": "0" * 64}],
    )
    with pytest.raises(RegistryError, match="columns must match exactly"):
        load_registry_spec(bad)

    extra_cols = list(REQUIRED_COLUMNS) + ["extra"]
    row = _spec_row(sha256="a" * 64)
    row["extra"] = "nope"
    _write_csv(bad, extra_cols, [row])
    with pytest.raises(RegistryError, match="columns must match exactly"):
        load_registry_spec(bad)


def test_invalid_sha256_rejection(demo_repo: Path) -> None:
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [_spec_row(sha256="NOT_A_HASH")],
    )
    with pytest.raises(RegistryError, match="Invalid SHA-256"):
        load_registry_spec(demo_repo / "config" / "source_registry.csv")


def test_empty_snapshot_date_rejection(demo_repo: Path) -> None:
    digest = _hash_path(demo_repo / "data" / "raw" / "demo" / "demo.csv")
    row = _spec_row(sha256=digest, n_rows_expected=3)
    row["snapshot_date"] = ""
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [row],
    )
    with pytest.raises(
        RegistryError, match="missing required nonempty field\\(s\\): snapshot_date"
    ):
        load_registry_spec(demo_repo / "config" / "source_registry.csv")


def test_path_outside_data_raw_rejection(demo_repo: Path) -> None:
    outside = demo_repo / "docs" / "not_raw.csv"
    _write_utf8_sig_csv(
        outside, ["record_id", "label", "payload"], _synthetic_input_rows(1)
    )
    digest = _hash_path(outside)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                path="docs/not_raw.csv",
                sha256=digest,
                n_rows_expected=1,
            )
        ],
    )
    with pytest.raises(RegistryError, match="beneath data/raw"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=demo_repo / "config" / "source_registry.csv",
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


def test_directory_registered_as_file_rejection(demo_repo: Path) -> None:
    digest = "b" * 64
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                path="data/raw/demo",
                sha256=digest,
                n_rows_expected=0,
            )
        ],
    )
    with pytest.raises(RegistryError, match="directory"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=demo_repo / "config" / "source_registry.csv",
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


def test_html_input_rejection(demo_repo: Path) -> None:
    html_dir = demo_repo / "data" / "raw" / "demo" / "html"
    html_dir.mkdir(parents=True)
    html_file = html_dir / "page_001.html"
    html_file.write_text("<html></html>", encoding="utf-8")
    digest = _hash_path(html_file)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                path="data/raw/demo/html/page_001.html",
                sha256=digest,
                n_rows_expected=0,
            )
        ],
    )
    with pytest.raises(RegistryError, match="HTML cache"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=demo_repo / "config" / "source_registry.csv",
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


def test_fixtures_input_rejection(demo_repo: Path) -> None:
    fixtures = demo_repo / "data" / "raw" / "demo" / "fixtures"
    fixtures.mkdir(parents=True)
    fixture_file = fixtures / "sample.csv"
    _write_utf8_sig_csv(
        fixture_file, ["record_id", "label", "payload"], _synthetic_input_rows(1)
    )
    digest = _hash_path(fixture_file)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                path="data/raw/demo/fixtures/sample.csv",
                sha256=digest,
                n_rows_expected=1,
            )
        ],
    )
    with pytest.raises(RegistryError, match="Fixture"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=demo_repo / "config" / "source_registry.csv",
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


def test_excel_lock_file_rejection(demo_repo: Path) -> None:
    lock = demo_repo / "data" / "raw" / "demo" / "~$locked.xlsx"
    lock.write_bytes(b"lock")
    digest = _hash_path(lock)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                path="data/raw/demo/~$locked.xlsx",
                sha256=digest,
                n_rows_expected=0,
            )
        ],
    )
    with pytest.raises(RegistryError, match="Excel lock"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=demo_repo / "config" / "source_registry.csv",
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


def test_explicit_aptabase_raw_rejection(demo_repo: Path) -> None:
    raw_dir = demo_repo / "data" / "raw" / "aptabase"
    raw_dir.mkdir(parents=True)
    raw_csv = raw_dir / "aptabase_raw.csv"
    _write_utf8_sig_csv(
        raw_csv, ["record_id", "label", "payload"], _synthetic_input_rows(1)
    )
    digest = _hash_path(raw_csv)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                source_key="aptabase",
                source_dataset="aptabase_raw_forbidden",
                path="data/raw/aptabase/aptabase_raw.csv",
                sha256=digest,
                n_rows_expected=1,
            )
        ],
    )
    with pytest.raises(RegistryError, match="[Ff]orbidden"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=demo_repo / "config" / "source_registry.csv",
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


def test_explicit_riboaptamer_truncated_rejection(demo_repo: Path) -> None:
    truncated_dir = demo_repo / "data" / "raw" / "riboaptamer"
    truncated_dir.mkdir(parents=True)
    truncated = truncated_dir / "rna_aptamer_seqs.csv"
    _write_utf8_sig_csv(
        truncated, ["record_id", "label", "payload"], _synthetic_input_rows(1)
    )
    digest = _hash_path(truncated)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                source_key="riboaptamer",
                source_dataset="riboaptamer_truncated_forbidden",
                path="data/raw/riboaptamer/rna_aptamer_seqs.csv",
                sha256=digest,
                n_rows_expected=1,
            )
        ],
    )
    with pytest.raises(RegistryError, match="truncated RiboAptamer"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=demo_repo / "config" / "source_registry.csv",
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


def test_inventory_hash_disagreement_warning(demo_repo: Path) -> None:
    inv = demo_repo / "docs" / "data_curation" / "raw_data_inventory.csv"
    digest = _hash_path(demo_repo / "data" / "raw" / "demo" / "demo.csv")
    _write_minimal_inventory(
        inv,
        [
            _inventory_row(
                relative_path="data/raw/demo/demo.csv",
                sha256="c" * 64,
                row_count="3",
            )
        ],
    )
    result = build_registry(
        repo_root=demo_repo,
        registry_spec=demo_repo / "config" / "source_registry.csv",
        inventory_path=inv,
        output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
    )
    assert any("inventory sha256" in w for w in result.warnings)
    assert result.validated == 1
    assert digest == _hash_path(demo_repo / "data" / "raw" / "demo" / "demo.csv")


def test_inventory_status_disagreement_warning_without_failure(
    demo_repo: Path,
) -> None:
    inv = demo_repo / "docs" / "data_curation" / "raw_data_inventory.csv"
    digest = _hash_path(demo_repo / "data" / "raw" / "demo" / "demo.csv")
    _write_minimal_inventory(
        inv,
        [
            _inventory_row(
                relative_path="data/raw/demo/demo.csv",
                sha256=digest,
                row_count="3",
                recommended_s0_status="derived_output_not_raw_input",
            )
        ],
    )
    result = build_registry(
        repo_root=demo_repo,
        registry_spec=demo_repo / "config" / "source_registry.csv",
        inventory_path=inv,
        output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
    )
    status_warnings = [w for w in result.warnings if "recommended_S0_status=" in w]
    assert len(status_warnings) == 1
    assert "Inventory warning for demo:" in status_warnings[0]
    assert not any("AptaBase inventory override" in w for w in result.warnings)
    assert result.validated == 1


def test_aptabase_inventory_overrides_emit_exactly_two_warnings(
    demo_repo: Path,
) -> None:
    """Cleaned-file and forbidden-raw mismatches each produce one warning."""
    cleaned = demo_repo / "data" / "raw" / "aptabase" / "aptabase_cleaned.csv"
    cleaned.parent.mkdir(parents=True, exist_ok=True)
    _write_utf8_sig_csv(
        cleaned, ["record_id", "label", "payload"], _synthetic_input_rows(2)
    )
    digest = _hash_path(cleaned)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                source_key="aptabase",
                source_dataset="aptabase_cleaned_scrape_2026-07-20",
                path="data/raw/aptabase/aptabase_cleaned.csv",
                sha256=digest,
                n_rows_expected=2,
                notes="synthetic aptabase registration",
            )
        ],
    )
    inv = demo_repo / "docs" / "data_curation" / "raw_data_inventory.csv"
    _write_minimal_inventory(
        inv,
        [
            _inventory_row(
                relative_path="data/raw/aptabase/aptabase_cleaned.csv",
                sha256=digest,
                row_count="2",
                recommended_s0_status="derived_output_not_raw_input",
            ),
            _inventory_row(
                relative_path="data/raw/aptabase/aptabase_raw.csv",
                sha256="d" * 64,
                row_count="2",
                recommended_s0_status="include_as_authoritative_input",
            ),
        ],
    )
    result = build_registry(
        repo_root=demo_repo,
        registry_spec=demo_repo / "config" / "source_registry.csv",
        inventory_path=inv,
        output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
    )
    assert result.validated == 1
    assert len(result.warnings) == 2
    cleaned_warnings = [
        w
        for w in result.warnings
        if "classifies data/raw/aptabase/aptabase_cleaned.csv as a derived output"
        in w
    ]
    raw_warnings = [
        w
        for w in result.warnings
        if "recommends data/raw/aptabase/aptabase_raw.csv" in w
        and "forbidden pipeline input" in w
    ]
    assert len(cleaned_warnings) == 1
    assert len(raw_warnings) == 1
    assert not any(
        "Inventory warning for aptabase: inventory recommended_S0_status=" in w
        for w in result.warnings
    )


def test_byte_identical_output_across_two_runs(demo_repo: Path) -> None:
    output = demo_repo / "data" / "interim" / "registry" / "source_registry.csv"
    args = dict(
        repo_root=demo_repo,
        registry_spec=demo_repo / "config" / "source_registry.csv",
        inventory_path=demo_repo / "docs" / "data_curation" / "raw_data_inventory.csv",
        output_path=output,
    )
    build_registry(**args)
    first = output.read_bytes()
    build_registry(**args)
    second = output.read_bytes()
    assert first == second


def test_no_modification_of_registered_input(demo_repo: Path) -> None:
    input_path = demo_repo / "data" / "raw" / "demo" / "demo.csv"
    before = input_path.read_bytes()
    before_mtime = input_path.stat().st_mtime_ns
    build_registry(
        repo_root=demo_repo,
        registry_spec=demo_repo / "config" / "source_registry.csv",
        inventory_path=demo_repo / "docs" / "data_curation" / "raw_data_inventory.csv",
        output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
    )
    assert input_path.read_bytes() == before
    assert input_path.stat().st_mtime_ns == before_mtime


def test_no_absolute_local_path_in_output(demo_repo: Path) -> None:
    output = demo_repo / "data" / "interim" / "registry" / "out.csv"
    build_registry(
        repo_root=demo_repo,
        registry_spec=demo_repo / "config" / "source_registry.csv",
        inventory_path=demo_repo / "docs" / "data_curation" / "raw_data_inventory.csv",
        output_path=output,
    )
    text = output.read_text(encoding="utf-8")
    assert str(demo_repo) not in text
    assert "/Users/" not in text
    assert "C:\\" not in text


def test_cli_resolves_relative_to_repo_root(demo_repo: Path, monkeypatch, capsys) -> None:
    # Run from a different cwd; relative paths must still resolve via repo root.
    outside = demo_repo.parent / "elsewhere"
    outside.mkdir()
    monkeypatch.chdir(outside)
    code = main(
        [
            "--repo-root",
            str(demo_repo),
            "--registry-spec",
            "config/source_registry.csv",
            "--inventory",
            "docs/data_curation/raw_data_inventory.csv",
            "--output",
            "data/interim/registry/source_registry.csv",
        ]
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "registered_sources=1" in captured.out
    assert "AAAA" not in captured.out  # synthetic payload must not be dumped
    assert (demo_repo / "data" / "interim" / "registry" / "source_registry.csv").is_file()


def _write_minimal_xlsx(path: Path, rows: list[list[object]]) -> None:
    """Write a minimal OOXML workbook via ZIP/XML (no openpyxl dependency)."""
    import zipfile
    from xml.etree.ElementTree import Element, SubElement, tostring

    path.parent.mkdir(parents=True, exist_ok=True)
    shared: list[str] = []

    def share(text: str) -> int:
        shared.append(text)
        return len(shared) - 1

    sheet = Element(
        "worksheet",
        {
            "xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        },
    )
    sheet_data = SubElement(sheet, "sheetData")
    for r_idx, row_vals in enumerate(rows, start=1):
        row_el = SubElement(sheet_data, "row", {"r": str(r_idx)})
        for c_idx, value in enumerate(row_vals):
            if value is None or value == "":
                continue
            col = chr(ord("A") + c_idx)
            cell_ref = f"{col}{r_idx}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                c_el = SubElement(row_el, "c", {"r": cell_ref})
                v_el = SubElement(c_el, "v")
                v_el.text = str(value)
            else:
                idx = share(str(value))
                c_el = SubElement(row_el, "c", {"r": cell_ref, "t": "s"})
                v_el = SubElement(c_el, "v")
                v_el.text = str(idx)

    ss_root = Element(
        "sst",
        {
            "xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "count": str(len(shared)),
            "uniqueCount": str(len(shared)),
        },
    )
    for text in shared:
        si = SubElement(ss_root, "si")
        t = SubElement(si, "t")
        t.text = text

    wb = Element(
        "workbook",
        {"xmlns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"},
    )
    wb.set(
        "xmlns:r",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    )
    sheets = SubElement(wb, "sheets")
    SubElement(
        sheets,
        "sheet",
        {
            "name": "Sheet1",
            "sheetId": "1",
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id": "rId1",
        },
    )
    rels = Element(
        "Relationships",
        {
            "xmlns": "http://schemas.openxmlformats.org/package/2006/relationships",
        },
    )
    SubElement(
        rels,
        "Relationship",
        {
            "Id": "rId1",
            "Type": (
                "http://schemas.openxmlformats.org/officeDocument/2006/"
                "relationships/officeDocument"
            ),
            "Target": "xl/workbook.xml",
        },
    )
    wb_rels = Element(
        "Relationships",
        {
            "xmlns": "http://schemas.openxmlformats.org/package/2006/relationships",
        },
    )
    SubElement(
        wb_rels,
        "Relationship",
        {
            "Id": "rId1",
            "Type": (
                "http://schemas.openxmlformats.org/officeDocument/2006/"
                "relationships/worksheet"
            ),
            "Target": "worksheets/sheet1.xml",
        },
    )
    content_types = Element(
        "Types",
        {"xmlns": "http://schemas.openxmlformats.org/package/2006/content-types"},
    )
    SubElement(
        content_types,
        "Default",
        {
            "Extension": "rels",
            "ContentType": (
                "application/vnd.openxmlformats-package.relationships+xml"
            ),
        },
    )
    SubElement(
        content_types,
        "Default",
        {"Extension": "xml", "ContentType": "application/xml"},
    )
    SubElement(
        content_types,
        "Override",
        {
            "PartName": "/xl/workbook.xml",
            "ContentType": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet.main+xml"
            ),
        },
    )
    SubElement(
        content_types,
        "Override",
        {
            "PartName": "/xl/worksheets/sheet1.xml",
            "ContentType": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.worksheet+xml"
            ),
        },
    )
    SubElement(
        content_types,
        "Override",
        {
            "PartName": "/xl/sharedStrings.xml",
            "ContentType": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sharedStrings+xml"
            ),
        },
    )

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", tostring(content_types))
        zf.writestr("_rels/.rels", tostring(rels))
        zf.writestr("xl/workbook.xml", tostring(wb))
        zf.writestr("xl/_rels/workbook.xml.rels", tostring(wb_rels))
        zf.writestr("xl/sharedStrings.xml", tostring(ss_root))
        zf.writestr("xl/worksheets/sheet1.xml", tostring(sheet))


def test_xlsx_registry_validation_success(tmp_path: Path) -> None:
    from s0_build_registry import count_xlsx_physical_data_rows, validate_registered_file

    repo = _make_repo_tree(tmp_path)
    xlsx = repo / "data" / "raw" / "demo" / "demo.xlsx"
    _write_minimal_xlsx(
        xlsx,
        [
            ["id", "payload"],
            ["a", "token-1"],
            ["b", "token-2"],
            ["c", "token-3"],
        ],
    )
    assert count_xlsx_physical_data_rows(xlsx) == 3
    row = RegistrySpecRow(
        source_key="xlsx_demo",
        source_dataset="xlsx_demo_v1",
        path="data/raw/demo/demo.xlsx",
        sha256=_hash_path(xlsx),
        n_rows_expected=3,
        snapshot_date="2026-08-05",
        tier="eval",
        redistribution_status="unknown",
        notes="physical worksheet layout row count",
    )
    validate_registered_file(repo, row)


def test_xlsx_registry_rejects_lock_file_and_row_mismatch(tmp_path: Path) -> None:
    from s0_build_registry import (
        RegistryError,
        assert_path_allowed,
        count_xlsx_physical_data_rows,
        validate_registered_file,
    )

    repo = _make_repo_tree(tmp_path)
    lock = repo / "data" / "raw" / "demo" / "~$demo.xlsx"
    lock.write_bytes(b"lock")
    with pytest.raises(RegistryError):
        assert_path_allowed(repo, "data/raw/demo/~$demo.xlsx")

    xlsx = repo / "data" / "raw" / "demo" / "demo.xlsx"
    _write_minimal_xlsx(xlsx, [["h"], ["1"], ["2"]])
    assert count_xlsx_physical_data_rows(xlsx) == 2
    row = RegistrySpecRow(
        source_key="xlsx_demo",
        source_dataset="xlsx_demo_v1",
        path="data/raw/demo/demo.xlsx",
        sha256=_hash_path(xlsx),
        n_rows_expected=99,
        snapshot_date="2026-08-05",
        tier="eval",
        redistribution_status="unknown",
        notes="mismatch",
    )
    with pytest.raises(RegistryError, match="Row-count mismatch"):
        validate_registered_file(repo, row)


def test_same_source_key_same_dataset_multiple_paths_allowed(demo_repo: Path) -> None:
    digest = _hash_path(demo_repo / "data" / "raw" / "demo" / "demo.csv")
    other = demo_repo / "data" / "raw" / "demo" / "lookup.csv"
    _write_utf8_sig_csv(
        other, ["record_id", "label", "payload"], _synthetic_input_rows(2)
    )
    other_digest = _hash_path(other)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(sha256=digest, n_rows_expected=3),
            _spec_row(
                source_key="demo",
                source_dataset="demo_v1",
                path="data/raw/demo/lookup.csv",
                sha256=other_digest,
                n_rows_expected=2,
            ),
        ],
    )
    rows = load_registry_spec(demo_repo / "config" / "source_registry.csv")
    assert len(rows) == 2
    assert {row.path for row in rows} == {
        "data/raw/demo/demo.csv",
        "data/raw/demo/lookup.csv",
    }
    result = build_registry(
        repo_root=demo_repo,
        registry_spec=demo_repo / "config" / "source_registry.csv",
        inventory_path=demo_repo / "docs" / "data_curation" / "raw_data_inventory.csv",
        output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
    )
    assert result.validated == 2
    written = list(
        csv.DictReader(
            (demo_repo / "data" / "interim" / "registry" / "out.csv").open(
                encoding="utf-8", newline=""
            )
        )
    )
    assert [row["path"] for row in written] == [
        "data/raw/demo/demo.csv",
        "data/raw/demo/lookup.csv",
    ]


def test_same_source_dataset_different_source_key_rejected(demo_repo: Path) -> None:
    digest = _hash_path(demo_repo / "data" / "raw" / "demo" / "demo.csv")
    other = demo_repo / "data" / "raw" / "demo" / "other.csv"
    _write_utf8_sig_csv(
        other, ["record_id", "label", "payload"], _synthetic_input_rows(1)
    )
    other_digest = _hash_path(other)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(sha256=digest, n_rows_expected=3),
            _spec_row(
                source_key="demo2",
                source_dataset="demo_v1",
                path="data/raw/demo/other.csv",
                sha256=other_digest,
                n_rows_expected=1,
            ),
        ],
    )
    with pytest.raises(RegistryError, match="Duplicate source_dataset"):
        load_registry_spec(demo_repo / "config" / "source_registry.csv")


def test_latin1_csv_row_count_fallback(tmp_path: Path) -> None:
    path = tmp_path / "latin1.csv"
    # Non-biological payload; 0xA6 is not valid UTF-8.
    header = b"id,label,note\n"
    row1 = b"1,item_1,token-1\n"
    row2 = b"2,item_2,token-" + bytes([0xA6]) + b"-latin1\n"
    path.write_bytes(header + row1 + row2)
    assert detect_csv_text_encoding(path) == "latin-1"
    assert count_csv_data_rows(path) == 2
    utf8_path = tmp_path / "utf8.csv"
    utf8_path.write_bytes(b"\xef\xbb\xbfid,label\n1,a\n2,b\n")
    assert detect_csv_text_encoding(utf8_path) == "utf-8-sig"
    assert count_csv_data_rows(utf8_path) == 2


def test_aptadb_nonprotein_lookup_registration_rejected(demo_repo: Path) -> None:
    forbidden = demo_repo / "data" / "raw" / "AptaDB" / "molecule.csv"
    forbidden.parent.mkdir(parents=True)
    _write_utf8_sig_csv(
        forbidden, ["record_id", "label", "payload"], _synthetic_input_rows(1)
    )
    digest = _hash_path(forbidden)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                source_key="aptadb",
                source_dataset="aptadb_official_export_2026-08",
                path="data/raw/AptaDB/molecule.csv",
                sha256=digest,
                n_rows_expected=1,
            )
        ],
    )
    with pytest.raises(RegistryError, match="non-protein lookup"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=demo_repo / "config" / "source_registry.csv",
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


@pytest.mark.parametrize(
    "relative_path",
    [
        "data/raw/Aptadiff_datasetA/datasetA_IGFBP3_x_z.csv",
        "data/raw/Aptadiff_otherdata/datasetC.fastq",
        "data/raw/Aptadiff_otherdata/datasetD.fastq",
        "data/raw/Aptadiff_datasetA/aptadiff_repo_readme.rtf",
    ],
)
def test_aptadiff_companion_registration_rejected(
    demo_repo: Path,
    relative_path: str,
) -> None:
    forbidden = demo_repo / relative_path
    forbidden.parent.mkdir(parents=True, exist_ok=True)
    forbidden.write_bytes(b"synthetic-token\n")
    digest = _hash_path(forbidden)
    _write_csv(
        demo_repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        [
            _spec_row(
                source_key="aptadiff_a",
                source_dataset="aptadiff_forbidden_companion",
                path=relative_path,
                sha256=digest,
                n_rows_expected=1,
            )
        ],
    )
    with pytest.raises(RegistryError, match="Forbidden AptaDiff companion"):
        build_registry(
            repo_root=demo_repo,
            registry_spec=demo_repo / "config" / "source_registry.csv",
            inventory_path=demo_repo
            / "docs"
            / "data_curation"
            / "raw_data_inventory.csv",
            output_path=demo_repo / "data" / "interim" / "registry" / "out.csv",
        )


SYNTHETIC_NT_STATEMENTS = [
    "<http://example.org/s1> <http://example.org/p1> <http://example.org/o1> .",
    "<http://example.org/s1> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://example.org/Item> .",
    "<http://example.org/s2> <http://example.org/p2> \"synthetic-token\" .",
]


def _write_nt_gz(path: Path, statements: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for statement in statements:
            handle.write(statement.rstrip("\n") + "\n")


def test_nt_gz_validates_compressed_sha_and_statement_count(tmp_path: Path) -> None:
    repo = _make_repo_tree(tmp_path)
    nt_path = repo / "data" / "raw" / "demo" / "demo.nt.gz"
    _write_nt_gz(nt_path, SYNTHETIC_NT_STATEMENTS)
    digest = _hash_path(nt_path)
    assert count_ntriples_gzip_statements(nt_path) == 3
    row = RegistrySpecRow(
        source_key="demo",
        source_dataset="demo_v1",
        path="data/raw/demo/demo.nt.gz",
        sha256=digest,
        n_rows_expected=3,
        snapshot_date="2026-09-08",
        tier="1",
        redistribution_status="unknown",
        notes="synthetic ntriples gzip",
    )
    validate_registered_file(repo, row)
    assert not (nt_path.parent / "demo.nt").exists()


def test_nt_gz_statement_count_mismatch_fails_closed(tmp_path: Path) -> None:
    repo = _make_repo_tree(tmp_path)
    nt_path = repo / "data" / "raw" / "demo" / "demo.nt.gz"
    _write_nt_gz(nt_path, SYNTHETIC_NT_STATEMENTS)
    row = RegistrySpecRow(
        source_key="demo",
        source_dataset="demo_v1",
        path="data/raw/demo/demo.nt.gz",
        sha256=_hash_path(nt_path),
        n_rows_expected=99,
        snapshot_date="2026-09-08",
        tier="1",
        redistribution_status="unknown",
        notes="mismatch",
    )
    with pytest.raises(RegistryError, match="statement-count mismatch"):
        validate_registered_file(repo, row)


def test_nt_gz_corrupt_gzip_fails_closed(tmp_path: Path) -> None:
    repo = _make_repo_tree(tmp_path)
    nt_path = repo / "data" / "raw" / "demo" / "demo.nt.gz"
    nt_path.write_bytes(b"this is not gzip compressed ntriples")
    row = RegistrySpecRow(
        source_key="demo",
        source_dataset="demo_v1",
        path="data/raw/demo/demo.nt.gz",
        sha256=_hash_path(nt_path),
        n_rows_expected=1,
        snapshot_date="2026-09-08",
        tier="1",
        redistribution_status="unknown",
        notes="corrupt",
    )
    with pytest.raises(RegistryError, match="corrupt|could not be read"):
        validate_registered_file(repo, row)


def test_nt_gz_skips_comments_and_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "comments.nt.gz"
    _write_nt_gz(
        path,
        [
            "# comment only",
            "",
            "<http://example.org/s> <http://example.org/p> <http://example.org/o> .",
            "   ",
            "<http://example.org/s2>\t<http://example.org/p2>\t<http://example.org/o2> .",
        ],
    )
    assert count_ntriples_gzip_statements(path) == 2


def test_multifile_aptamerbase_source_accepted_by_registry_rules(
    tmp_path: Path,
) -> None:
    repo = _make_repo_tree(tmp_path)
    csv_path = repo / "data" / "raw" / "aptamerbase" / "aptamerbase_aptamers.csv"
    nt_path = (
        repo / "data" / "raw" / "aptamerbase" / "aptamerbase.freebase.extract.nt.gz"
    )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_utf8_sig_csv(
        csv_path, ["record_id", "label", "payload"], _synthetic_input_rows(2)
    )
    _write_nt_gz(nt_path, SYNTHETIC_NT_STATEMENTS)
    csv_digest = _hash_path(csv_path)
    nt_digest = _hash_path(nt_path)
    spec_rows = [
        _spec_row(
            source_key="aptamerbase",
            source_dataset="aptamerbase_export_2026-06-24",
            path="data/raw/aptamerbase/aptamerbase_aptamers.csv",
            sha256=csv_digest,
            n_rows_expected=2,
            notes="csv spine",
        ),
        _spec_row(
            source_key="aptamerbase",
            source_dataset="aptamerbase_export_2026-06-24",
            path="data/raw/aptamerbase/aptamerbase.freebase.extract.nt.gz",
            sha256=nt_digest,
            n_rows_expected=3,
            notes="supporting rdf",
        ),
    ]
    _write_csv(
        repo / "config" / "source_registry.csv",
        list(REQUIRED_COLUMNS),
        spec_rows,
    )
    parsed = load_registry_spec(repo / "config" / "source_registry.csv")
    assert len(parsed) == 2
    assert {row.source_key for row in parsed} == {"aptamerbase"}
    assert {row.source_dataset for row in parsed} == {
        "aptamerbase_export_2026-06-24"
    }
    _write_minimal_inventory(
        repo / "docs" / "data_curation" / "raw_data_inventory.csv",
        [
            _inventory_row(
                relative_path="data/raw/aptamerbase/aptamerbase_aptamers.csv",
                sha256=csv_digest,
                row_count="2",
            ),
            _inventory_row(
                relative_path="data/raw/aptamerbase/aptamerbase.freebase.extract.nt.gz",
                sha256=nt_digest,
                row_count="3",
            ),
        ],
    )
    result = build_registry(
        repo_root=repo,
        registry_spec=repo / "config" / "source_registry.csv",
        inventory_path=repo / "docs" / "data_curation" / "raw_data_inventory.csv",
        output_path=repo / "data" / "interim" / "registry" / "out.csv",
    )
    assert result.validated == 2
    written = list(
        csv.DictReader(
            (repo / "data" / "interim" / "registry" / "out.csv").open(
                encoding="utf-8", newline=""
            )
        )
    )
    assert [row["n_rows_expected"] for row in written] == ["3", "2"]
    assert written[0]["path"].endswith(".nt.gz")
    assert written[1]["path"].endswith("aptamerbase_aptamers.csv")


def test_tracked_aptamerbase_csv_registration_unchanged() -> None:
    rows = load_registry_spec(REPO_ROOT / "config" / "source_registry.csv")
    csv_rows = [
        row
        for row in rows
        if row.path == "data/raw/aptamerbase/aptamerbase_aptamers.csv"
    ]
    assert len(csv_rows) == 1
    row = csv_rows[0]
    assert row.source_key == "aptamerbase"
    assert row.source_dataset == "aptamerbase_export_2026-06-24"
    assert row.sha256 == (
        "40b329551b225a29ee2c656cf6b59b98ff686a981968b856685cdc7c222a784c"
    )
    assert row.n_rows_expected == 2128
    assert row.snapshot_date == "2026-06-24"
    assert row.tier == "1"
    assert row.redistribution_status == "unknown"


def test_tracked_source_dataset_still_belongs_to_one_source_key() -> None:
    rows = load_registry_spec(REPO_ROOT / "config" / "source_registry.csv")
    dataset_to_keys: dict[str, set[str]] = {}
    for row in rows:
        dataset_to_keys.setdefault(row.source_dataset, set()).add(row.source_key)
    assert all(len(keys) == 1 for keys in dataset_to_keys.values())
    aptamerbase = [row for row in rows if row.source_key == "aptamerbase"]
    assert len(aptamerbase) == 2
    assert {row.source_dataset for row in aptamerbase} == {
        "aptamerbase_export_2026-06-24"
    }
    aptadb = [row for row in rows if row.source_key == "aptadb"]
    assert len(aptadb) == 3
    keys_to_count = {}
    for row in rows:
        keys_to_count[row.source_key] = keys_to_count.get(row.source_key, 0) + 1
    assert keys_to_count["aptabase"] == 1
    assert keys_to_count["ena"] == 1

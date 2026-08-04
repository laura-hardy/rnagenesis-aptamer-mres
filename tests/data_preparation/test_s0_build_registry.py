"""Tests for S0a source-registry validation (no biological sequences)."""

from __future__ import annotations

import csv
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
    build_registry,
    count_csv_data_rows,
    load_registry_spec,
    main,
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


def test_duplicate_source_key_rejection(demo_repo: Path) -> None:
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
    with pytest.raises(RegistryError, match="Duplicate source_key"):
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

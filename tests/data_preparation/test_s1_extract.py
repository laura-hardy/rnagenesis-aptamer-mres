"""Tests for the generic S1 extraction runner (synthetic fixtures only)."""

from __future__ import annotations

import csv
import hashlib
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "data_preparation"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase import APTABASE_INPUT_COLUMNS  # noqa: E402
from s0_build_registry import REQUIRED_COLUMNS, RegistryError  # noqa: E402
from s1_extract import (  # noqa: E402
    S1ExtractError,
    main,
    run_s1_extraction,
)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_aptabase_input(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(APTABASE_INPUT_COLUMNS),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in APTABASE_INPUT_COLUMNS})


def _blank_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in APTABASE_INPUT_COLUMNS}
    row.update(overrides)
    return row


def _hash_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "data_curation").mkdir(parents=True)
    (repo / "scripts" / "data_preparation").mkdir(parents=True)
    (repo / "config").mkdir(parents=True)
    (repo / "data" / "raw" / "aptabase").mkdir(parents=True)
    (repo / "data" / "interim" / "extracted").mkdir(parents=True)
    return repo


def _install_registry(
    repo: Path,
    *,
    relative_path: str,
    sha256: str,
    n_rows: int,
    source_key: str = "aptabase",
    source_dataset: str = "aptabase_demo_v1",
) -> Path:
    spec = repo / "config" / "source_registry.csv"
    _write_csv(
        spec,
        list(REQUIRED_COLUMNS),
        [
            {
                "source_key": source_key,
                "source_dataset": source_dataset,
                "path": relative_path,
                "sha256": sha256,
                "n_rows_expected": str(n_rows),
                "snapshot_date": "2026-08-05",
                "tier": "1",
                "redistribution_status": "unknown",
                "notes": "synthetic",
            }
        ],
    )
    return spec


def _demo_rows() -> list[dict[str, str]]:
    return [
        _blank_row(
            record_id="1",
            sequence_raw="ACGUACGU",
            target_specific="Protein A",
            aptamer_name="A1",
            reference="Ref1",
            doi="10.1/a",
            pmid="11",
        ),
        _blank_row(
            record_id="2",
            sequence_raw="",
            target_general="Cell B",
            target_specific="N/A",
            aptamer_name="",
            reference="",
            doi="",
            pmid="",
        ),
    ]


@pytest.fixture
def synthetic_repo(tmp_path: Path) -> Path:
    repo = _make_repo(tmp_path)
    input_path = repo / "data" / "raw" / "aptabase" / "aptabase_cleaned.csv"
    rows = _demo_rows()
    _write_aptabase_input(input_path, rows)
    digest = _hash_path(input_path)
    _install_registry(
        repo,
        relative_path="data/raw/aptabase/aptabase_cleaned.csv",
        sha256=digest,
        n_rows=len(rows),
    )
    return repo


def test_registry_path_used_not_hardcoded(synthetic_repo: Path, tmp_path: Path) -> None:
    """Runner must resolve the input via the registry specification path."""
    # Move file to an alternate registered location and update registry only.
    alt_rel = "data/raw/aptabase/alternate_cleaned.csv"
    src = synthetic_repo / "data" / "raw" / "aptabase" / "aptabase_cleaned.csv"
    dest = synthetic_repo / alt_rel
    dest.write_bytes(src.read_bytes())
    src.unlink()
    digest = _hash_path(dest)
    _install_registry(
        synthetic_repo,
        relative_path=alt_rel,
        sha256=digest,
        n_rows=2,
    )
    result = run_s1_extraction(
        repo_root=synthetic_repo,
        source_key="aptabase",
        registry_spec=synthetic_repo / "config" / "source_registry.csv",
        output_dir=Path("data/interim/extracted"),
    )
    assert result.stats.input_rows == 2
    assert result.registered_path == alt_rel


def test_sha_mismatch_fails_before_adapter(synthetic_repo: Path) -> None:
    spec = synthetic_repo / "config" / "source_registry.csv"
    rows = list(csv.DictReader(spec.open(encoding="utf-8", newline="")))
    rows[0]["sha256"] = "0" * 64
    _write_csv(spec, list(REQUIRED_COLUMNS), rows)
    with pytest.raises((RegistryError, S1ExtractError), match="SHA-256|sha256"):
        run_s1_extraction(
            repo_root=synthetic_repo,
            source_key="aptabase",
            registry_spec=spec,
            output_dir=Path("data/interim/extracted"),
        )
    out = synthetic_repo / "data" / "interim" / "extracted" / "aptabase_extracted.csv"
    assert not out.exists()


def test_row_count_mismatch_fails_before_adapter(synthetic_repo: Path) -> None:
    spec = synthetic_repo / "config" / "source_registry.csv"
    rows = list(csv.DictReader(spec.open(encoding="utf-8", newline="")))
    rows[0]["n_rows_expected"] = "999"
    _write_csv(spec, list(REQUIRED_COLUMNS), rows)
    with pytest.raises((RegistryError, S1ExtractError), match="[Rr]ow"):
        run_s1_extraction(
            repo_root=synthetic_repo,
            source_key="aptabase",
            registry_spec=spec,
            output_dir=Path("data/interim/extracted"),
        )
    out = synthetic_repo / "data" / "interim" / "extracted" / "aptabase_extracted.csv"
    assert not out.exists()


def test_unknown_adapter_rejected(synthetic_repo: Path) -> None:
    with pytest.raises(S1ExtractError, match="Unknown S1 adapter|not present"):
        run_s1_extraction(
            repo_root=synthetic_repo,
            source_key="not_a_real_source",
            registry_spec=synthetic_repo / "config" / "source_registry.csv",
            output_dir=Path("data/interim/extracted"),
        )


def test_forbidden_companion_cannot_be_substituted(
    synthetic_repo: Path,
) -> None:
    raw_path = synthetic_repo / "data" / "raw" / "aptabase" / "aptabase_raw.csv"
    cleaned = synthetic_repo / "data" / "raw" / "aptabase" / "aptabase_cleaned.csv"
    raw_path.write_bytes(cleaned.read_bytes())
    digest = _hash_path(raw_path)
    _install_registry(
        synthetic_repo,
        relative_path="data/raw/aptabase/aptabase_raw.csv",
        sha256=digest,
        n_rows=2,
    )
    with pytest.raises((RegistryError, S1ExtractError), match="[Ff]orbidden"):
        run_s1_extraction(
            repo_root=synthetic_repo,
            source_key="aptabase",
            registry_spec=synthetic_repo / "config" / "source_registry.csv",
            output_dir=Path("data/interim/extracted"),
        )


def test_output_directory_created_beneath_interim(synthetic_repo: Path) -> None:
    out_rel = Path("data/interim/extracted/nested")
    result = run_s1_extraction(
        repo_root=synthetic_repo,
        source_key="aptabase",
        registry_spec=synthetic_repo / "config" / "source_registry.csv",
        output_dir=out_rel,
    )
    assert result.output_canonical.is_file()
    assert "data/interim" in result.output_canonical.as_posix()


def test_outputs_deterministic_across_runs(synthetic_repo: Path) -> None:
    kwargs = dict(
        repo_root=synthetic_repo,
        source_key="aptabase",
        registry_spec=synthetic_repo / "config" / "source_registry.csv",
        output_dir=Path("data/interim/extracted"),
    )
    run_s1_extraction(**kwargs)
    c1 = (synthetic_repo / "data/interim/extracted/aptabase_extracted.csv").read_bytes()
    s1 = (
        synthetic_repo / "data/interim/extracted/aptabase_source_metadata.csv"
    ).read_bytes()
    r1 = (synthetic_repo / "data/interim/extracted/aptabase_s1_report.md").read_bytes()
    run_s1_extraction(**kwargs)
    assert (
        synthetic_repo / "data/interim/extracted/aptabase_extracted.csv"
    ).read_bytes() == c1
    assert (
        synthetic_repo / "data/interim/extracted/aptabase_source_metadata.csv"
    ).read_bytes() == s1
    # Report includes the same aggregate content; hashes in report are stable.
    assert (
        synthetic_repo / "data/interim/extracted/aptabase_s1_report.md"
    ).read_bytes() == r1


def test_no_absolute_path_in_outputs(synthetic_repo: Path) -> None:
    result = run_s1_extraction(
        repo_root=synthetic_repo,
        source_key="aptabase",
        registry_spec=synthetic_repo / "config" / "source_registry.csv",
        output_dir=Path("data/interim/extracted"),
    )
    abs_root = str(synthetic_repo.resolve())
    for path in (
        result.output_canonical,
        result.output_sidecar,
        result.output_report,
    ):
        text = path.read_text(encoding="utf-8")
        assert abs_root not in text


def test_no_sequences_printed_to_stdout_stderr(synthetic_repo: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(
            [
                "--source",
                "aptabase",
                "--registry-spec",
                "config/source_registry.csv",
                "--output-dir",
                "data/interim/extracted",
                "--repo-root",
                str(synthetic_repo),
            ]
        )
    assert code == 0
    combined = stdout.getvalue() + stderr.getvalue()
    assert "ACGUACGU" not in combined
    assert "sequence_raw=" not in combined
    assert "input_rows=2" in combined


def test_aggregate_report_contains_no_sequence_values(synthetic_repo: Path) -> None:
    result = run_s1_extraction(
        repo_root=synthetic_repo,
        source_key="aptabase",
        registry_spec=synthetic_repo / "config" / "source_registry.csv",
        output_dir=Path("data/interim/extracted"),
    )
    report = result.output_report.read_text(encoding="utf-8")
    assert "ACGUACGU" not in report
    assert "aptabase:1" not in report
    assert "nonempty sequence_raw" in report


def test_canonical_and_sidecar_row_counts_match(synthetic_repo: Path) -> None:
    result = run_s1_extraction(
        repo_root=synthetic_repo,
        source_key="aptabase",
        registry_spec=synthetic_repo / "config" / "source_registry.csv",
        output_dir=Path("data/interim/extracted"),
    )
    assert result.stats.canonical_rows == result.stats.sidecar_rows == 2


def test_atomic_write_failure_leaves_no_partial_final(
    synthetic_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = synthetic_repo / "data" / "interim" / "extracted"
    final = out_dir / "aptabase_extracted.csv"
    final.write_text("prior\n", encoding="utf-8")

    import common.corpus_schema as schema_mod

    real_replace = Path.replace

    def boom(self: Path, target: Path) -> Path:  # noqa: ANN001
        if target.name == "aptabase_extracted.csv":
            raise OSError("simulated replace failure")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError, match="simulated replace failure"):
        run_s1_extraction(
            repo_root=synthetic_repo,
            source_key="aptabase",
            registry_spec=synthetic_repo / "config" / "source_registry.csv",
            output_dir=Path("data/interim/extracted"),
        )
    assert final.read_text(encoding="utf-8") == "prior\n"
    assert list(out_dir.glob(".aptabase_extracted.csv.*.tmp")) == []
    del schema_mod


def test_running_from_different_cwd_works(
    synthetic_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    result = run_s1_extraction(
        repo_root=synthetic_repo,
        source_key="aptabase",
        registry_spec=Path("config/source_registry.csv"),
        output_dir=Path("data/interim/extracted"),
    )
    assert result.stats.input_rows == 2
    assert result.output_canonical.is_file()


def test_no_real_raw_files_read_by_tests(synthetic_repo: Path) -> None:
    """Guard: the synthetic repo must not point at the real AptaBase snapshot."""
    real = REPO_ROOT / "data" / "raw" / "aptabase" / "aptabase_cleaned.csv"
    synthetic = synthetic_repo / "data" / "raw" / "aptabase" / "aptabase_cleaned.csv"
    assert synthetic.resolve() != real.resolve()
    assert _hash_path(synthetic) != _hash_path(real)
    run_s1_extraction(
        repo_root=synthetic_repo,
        source_key="aptabase",
        registry_spec=synthetic_repo / "config" / "source_registry.csv",
        output_dir=Path("data/interim/extracted"),
    )


def test_production_row_count_gate_rejects_non_610_via_read(
    tmp_path: Path,
) -> None:
    """Production read_aptabase_rows hard-fails unless row count is 610."""
    from adapters.aptabase import read_aptabase_rows

    path = tmp_path / "small.csv"
    _write_aptabase_input(path, _demo_rows())
    with pytest.raises(Exception, match="610"):
        read_aptabase_rows(path)

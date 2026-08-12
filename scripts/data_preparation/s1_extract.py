#!/usr/bin/env python3
"""S1: verbatim extraction of a registered source into the canonical corpus.

Resolves the selected source from the tracked registry, validates hash and row
count before adapter execution, and writes deterministic canonical, sidecar and
report artefacts under data/interim/extracted/. Does not run S2 normalisation,
filtering, parking, or deduplication.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase import (  # noqa: E402
    AptaBaseAdapterError,
    AptaBaseExtractionResult,
    extract_aptabase,
    write_sidecar_csv_atomic as write_aptabase_sidecar_csv_atomic,
)
from adapters.utexas import (  # noqa: E402
    UTexasAdapterError,
    UTexasExtractionResult,
    extract_utexas,
    write_sidecar_csv_atomic as write_utexas_sidecar_csv_atomic,
)
from common.corpus_schema import (  # noqa: E402
    CorpusSchemaError,
    write_corpus_csv_atomic,
)
from s0_build_registry import (  # noqa: E402
    RegistryError,
    RegistrySpecRow,
    find_repo_root,
    load_registry_spec,
    resolve_registered_path,
    sha256_file,
    validate_registered_file,
)

# Lowercase basenames — matching is case-insensitive so forbidden companions
# cannot be bypassed via case variants on case-insensitive filesystems.
FORBIDDEN_COMPANION_BASENAMES = frozenset(
    {
        "aptabase_raw.csv",
        "aptamer search page 1.html",
        "aptamer search page 2.html",
        "aptamer search page 37.html",
        "aptamer search page 61.html",
    }
)


class S1ExtractError(ValueError):
    """Hard failure during S1 extraction orchestration."""


@dataclass(frozen=True)
class S1RunResult:
    """Aggregate outcome of one S1 extraction run."""

    source_key: str
    source_dataset: str
    registered_path: str
    registered_sha256: str
    observed_sha256: str
    sha256_ok: bool
    input_hash_before: str
    input_hash_after: str
    input_hash_unchanged: bool
    deterministic_rerun_ok: bool | None
    stats: Any
    output_canonical: Path
    output_sidecar: Path
    output_report: Path


AdapterFn = Callable[..., AptaBaseExtractionResult | UTexasExtractionResult]


def _get_adapter(source_key: str) -> AdapterFn:
    if source_key == "aptabase":
        return extract_aptabase
    if source_key == "utexas":
        return extract_utexas
    raise S1ExtractError(f"Unknown S1 adapter for source_key={source_key!r}")


def _resolve_source_row(
    rows: Sequence[RegistrySpecRow],
    source_key: str,
) -> RegistrySpecRow:
    matches = [row for row in rows if row.source_key == source_key]
    if not matches:
        available = ", ".join(sorted(r.source_key for r in rows)) or "(none)"
        raise S1ExtractError(
            f"Source key {source_key!r} is not present in the registry "
            f"specification; available: {available}"
        )
    if len(matches) > 1:
        raise S1ExtractError(
            f"Duplicate source_key in registry specification: {source_key!r}"
        )
    return matches[0]


def _assert_not_forbidden_companion(relative_path: str) -> None:
    lower = relative_path.replace("\\", "/").lower()
    name_lower = Path(lower).name
    if name_lower in FORBIDDEN_COMPANION_BASENAMES:
        raise S1ExtractError(
            f"Forbidden AptaBase companion cannot be used as S1 input: "
            f"{relative_path}"
        )
    if "/html/" in f"/{lower}/" or lower.endswith("/html"):
        raise S1ExtractError(
            f"HTML cache paths are forbidden S1 inputs: {relative_path}"
        )
    if "/fixtures/" in f"/{lower}/" or lower.endswith("/fixtures"):
        raise S1ExtractError(
            f"Fixture paths are forbidden S1 inputs: {relative_path}"
        )


def _assert_output_dir_allowed(repo_root: Path, output_dir: Path) -> Path:
    """Require outputs under ``data/interim`` (resolved relative to repo root)."""
    resolved = output_dir if output_dir.is_absolute() else (repo_root / output_dir)
    resolved = resolved.resolve()
    interim_root = (repo_root / "data" / "interim").resolve()
    try:
        resolved.relative_to(interim_root)
    except ValueError as exc:
        raise S1ExtractError(
            "S1 output directory must lie beneath data/interim/: "
            f"{output_dir}"
        ) from exc
    # Refuse writing under data/raw via this runner.
    raw_root = (repo_root / "data" / "raw").resolve()
    try:
        resolved.relative_to(raw_root)
    except ValueError:
        pass
    else:
        raise S1ExtractError(
            f"Refusing to write S1 outputs under data/raw/: {output_dir}"
        )
    return resolved


def _relative_display(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        # Avoid leaking absolute machine paths into reports; use basename.
        return path.name


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
        temp_path.replace(path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def build_aptabase_s1_report(
    *,
    repo_root: Path,
    registry_row: RegistrySpecRow,
    result: S1RunResult,
) -> str:
    """Build an aggregate-only Markdown S1 report (no sequences or IDs)."""
    stats = result.stats
    lines = [
        "# AptaBase S1 extraction report",
        "",
        "## Registered source",
        "",
        f"- Registered path: `{registry_row.path}`",
        f"- Registered source dataset: `{registry_row.source_dataset}`",
        f"- Registered SHA-256: `{registry_row.sha256}`",
        f"- Observed SHA-256: `{result.observed_sha256}`",
        f"- SHA-256 agreement: `{'pass' if result.sha256_ok else 'fail'}`",
        f"- Registered n_rows_expected: `{registry_row.n_rows_expected}`",
        f"- Redistribution status: `{registry_row.redistribution_status}`",
        "",
        "## Row counts",
        "",
        f"- Input rows: `{stats.input_rows}`",
        f"- Canonical output rows: `{stats.canonical_rows}`",
        f"- Sidecar rows: `{stats.sidecar_rows}`",
        f"- Unique native IDs: `{stats.unique_native_ids}`",
        f"- Unique canonical IDs: `{stats.unique_record_ids}`",
        "",
        "## Sequence retention (verbatim; no cleaning)",
        "",
        f"- Records with nonempty sequence_raw: `{stats.nonempty_sequences}`",
        f"- Records with missing sequence_raw: `{stats.missing_sequences}`",
        f"- Exact-copy validation for sequence_raw: "
        f"`{'pass' if stats.sequence_exact_copy_ok else 'fail'}`",
        "",
        "## Target mapping (raw only)",
        "",
        f"- Records using target_specific: `{stats.target_specific_used}`",
        f"- Records falling back to target_general: "
        f"`{stats.target_general_fallback}`",
        f"- Records with no usable raw target: `{stats.target_empty}`",
        "",
        "## Publication fields",
        "",
        f"- Nonempty publication: `{stats.nonempty_publication}`",
        f"- Nonempty DOI: `{stats.nonempty_doi}`",
        f"- Nonempty PMID: `{stats.nonempty_pmid}`",
        "",
        "## Source-metadata diagnostics (not canonical decisions)",
        "",
        f"- Rows with source parsing warnings: "
        f"`{stats.rows_with_parse_warnings}`",
        f"- Rows with source duplicate-group annotations: "
        f"`{stats.rows_with_duplicate_group}`",
        "",
        "## Integrity",
        "",
        f"- Source-input hash before: `{result.input_hash_before}`",
        f"- Source-input hash after: `{result.input_hash_after}`",
        f"- Source-input pre/post hash result: "
        f"`{'pass' if result.input_hash_unchanged else 'fail'}`",
        (
            f"- Deterministic rerun result: "
            f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
            if result.deterministic_rerun_ok is not None
            else "- Deterministic rerun result: `not_checked`"
        ),
        "",
        "## Outputs",
        "",
        f"- Canonical: `{_relative_display(result.output_canonical, repo_root)}`",
        f"- Sidecar: `{_relative_display(result.output_sidecar, repo_root)}`",
        f"- Report: `{_relative_display(result.output_report, repo_root)}`",
        "",
        "## Stage boundary",
        "",
        "- S1 only: no S2 normalisation, trimming, filtering, parking,",
        "  deduplication, molecule inference, T→U conversion, or affinity",
        "  interpretation was performed.",
        "",
    ]
    return "\n".join(lines)


def build_utexas_s1_report(
    *,
    repo_root: Path,
    registry_row: RegistrySpecRow,
    result: S1RunResult,
) -> str:
    """Build an aggregate-only Markdown UTexas S1 report (no sequences)."""
    stats = result.stats
    lines = [
        "# UTexas S1 extraction report",
        "",
        "## Registered source",
        "",
        f"- Registered path: `{registry_row.path}`",
        f"- Registered source dataset: `{registry_row.source_dataset}`",
        f"- Workbook sheet: `{stats.sheet_name}`",
        f"- Registered SHA-256: `{registry_row.sha256}`",
        f"- Observed SHA-256: `{result.observed_sha256}`",
        f"- SHA-256 agreement: `{'pass' if result.sha256_ok else 'fail'}`",
        f"- Registered n_rows_expected: `{registry_row.n_rows_expected}`",
        f"- Redistribution status: `{registry_row.redistribution_status}`",
        "",
        "## Row counts",
        "",
        f"- Expected physical source rows: `{registry_row.n_rows_expected}`",
        f"- Extracted rows (canonical): `{stats.canonical_rows}`",
        f"- Sidecar rows: `{stats.sidecar_rows}`",
        f"- Unique native IDs: `{stats.unique_native_ids}`",
        f"- Unique canonical record IDs: `{stats.unique_record_ids}`",
        f"- Nonempty source records (nonempty sequence_raw): "
        f"`{stats.nonempty_sequences}`",
        f"- Blank source records (empty sequence_raw): "
        f"`{stats.missing_sequences}`",
        "",
        "## Native-ID strategy",
        "",
        f"- Strategy: `{stats.native_id_strategy}`",
        "- Source `Serial Number` is preserved only in the sidecar; it is not",
        "  used as `native_id` because it is duplicated and absent on blank",
        "  physical rows.",
        "",
        "## Source Serial Number statistics",
        "",
        f"- Populated Serial Number values: `{stats.populated_serials}`",
        f"- Unique Serial Number values: `{stats.unique_serials}`",
        f"- Duplicate Serial Number keys: `{stats.duplicate_serial_keys}`",
        f"- Rows participating in duplicated keys: "
        f"`{stats.rows_in_duplicate_serial_groups}`",
        f"- Blank Serial Number values: `{stats.blank_serials}`",
        "",
        "## Canonical mapping summary",
        "",
        "- `Aptamer Sequence` → `sequence_raw` (verbatim; no cleaning)",
        "- `Target ` (trailing space retained in source header) → "
        "`target_name_raw` (verbatim)",
        "- `Citation` → `publication`",
        "- `Journal DOI` → `doi` (verbatim source value)",
        "- `Link to PubMed Entry` → `pubmed_id` only when a numeric PMID can be",
        "  extracted deterministically from the source string; otherwise empty",
        "- `Name of Aptamer` → optional JSON `notes` when nonempty",
        "- All 28 original UTexas columns + worksheet row → source-metadata",
        "  sidecar",
        "",
        "## Sequence and target retention (verbatim; no cleaning)",
        "",
        f"- Records with nonempty sequence_raw: `{stats.nonempty_sequences}`",
        f"- Records with empty sequence_raw: `{stats.missing_sequences}`",
        f"- Exact-copy validation for sequence_raw: "
        f"`{'pass' if stats.sequence_exact_copy_ok else 'fail'}`",
        f"- Records with nonempty target_name_raw: `{stats.nonempty_targets}`",
        f"- Records with empty target_name_raw: `{stats.missing_targets}`",
        f"- Exact-copy validation for target_name_raw: "
        f"`{'pass' if stats.target_exact_copy_ok else 'fail'}`",
        "",
        "## Publication fields",
        "",
        f"- Nonempty publication: `{stats.nonempty_publication}`",
        f"- Nonempty DOI: `{stats.nonempty_doi}`",
        f"- Nonempty PMID (deterministically extracted): "
        f"`{stats.nonempty_pmid}`",
        "",
        "## Source-metadata sidecar",
        "",
        f"- Sidecar rows: `{stats.sidecar_rows}`",
        "- Sidecar retains worksheet row number and all original UTexas",
        "  columns, including Serial Number, molecule/chemistry text,",
        "  affinity/Kd fields, pool metadata, buffer conditions, citations,",
        "  and currently unused source fields.",
        "",
        "## Validation results",
        "",
        f"- SHA-256 agreement: `{'pass' if result.sha256_ok else 'fail'}`",
        f"- Row retention (rows_in == rows_out == "
        f"{registry_row.n_rows_expected}): "
        f"`{'pass' if stats.canonical_rows == registry_row.n_rows_expected else 'fail'}`",
        f"- Unique native/record IDs: "
        f"`{'pass' if stats.unique_native_ids == stats.canonical_rows and stats.unique_record_ids == stats.canonical_rows else 'fail'}`",
        f"- Sequence exact-copy: "
        f"`{'pass' if stats.sequence_exact_copy_ok else 'fail'}`",
        f"- Target exact-copy: "
        f"`{'pass' if stats.target_exact_copy_ok else 'fail'}`",
        "",
        "## Integrity / raw-data immutability",
        "",
        f"- Source-input hash before: `{result.input_hash_before}`",
        f"- Source-input hash after: `{result.input_hash_after}`",
        f"- Source-input pre/post hash result: "
        f"`{'pass' if result.input_hash_unchanged else 'fail'}`",
        (
            f"- Deterministic rerun result: "
            f"`{'pass' if result.deterministic_rerun_ok else 'fail'}`"
            if result.deterministic_rerun_ok is not None
            else "- Deterministic rerun result: `not_checked`"
        ),
        "",
        "## Outputs",
        "",
        f"- Canonical: `{_relative_display(result.output_canonical, repo_root)}`",
        f"- Sidecar: `{_relative_display(result.output_sidecar, repo_root)}`",
        f"- Report: `{_relative_display(result.output_report, repo_root)}`",
        "",
        "## Stage boundary",
        "",
        "- S1 only: no sequence cleaning, alphabet conversion, molecule",
        "  classification, length filtering, trimming, target normalisation,",
        "  evidence scoring, parking, or deduplication was performed.",
        "- No S2 normalisation was started.",
        "",
        "## Pipeline status",
        "",
        "- UTexas S1 complete.",
        "- UTexas S2 has not started.",
        "- No UTexas records are yet authorised for global S4.",
        "",
    ]
    return "\n".join(lines)


def run_s1_extraction(
    *,
    repo_root: Path,
    source_key: str,
    registry_spec: Path,
    output_dir: Path,
    check_deterministic_rerun: bool = False,
) -> S1RunResult:
    """Execute S1 extraction for one registered source."""
    repo_root = repo_root.resolve()
    registry_spec = (
        registry_spec
        if registry_spec.is_absolute()
        else (repo_root / registry_spec).resolve()
    )
    output_dir = _assert_output_dir_allowed(repo_root, output_dir)

    if not registry_spec.is_file():
        raise S1ExtractError(f"Registry specification not found: {registry_spec}")

    spec_rows = load_registry_spec(registry_spec)
    row = _resolve_source_row(spec_rows, source_key)
    _assert_not_forbidden_companion(row.path)

    adapter = _get_adapter(source_key)

    # Validate hash and row count before adapter execution.
    validate_registered_file(repo_root, row)
    input_path = resolve_registered_path(repo_root, row.path)
    hash_before = sha256_file(input_path)
    if hash_before != row.sha256:
        raise S1ExtractError(
            f"SHA-256 mismatch before adapter execution for {source_key!r}"
        )

    if source_key in {"aptabase", "utexas"}:
        extraction = adapter(
            input_path,
            source_dataset=row.source_dataset,
            redistribution_status=row.redistribution_status,
            expected_rows=row.n_rows_expected,
        )
    else:
        raise S1ExtractError(f"No extraction path for source_key={source_key!r}")

    hash_after = sha256_file(input_path)
    if hash_after != hash_before:
        raise S1ExtractError(
            f"Source input was modified during S1 extraction: {row.path}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = output_dir / f"{source_key}_extracted.csv"
    sidecar_path = output_dir / f"{source_key}_source_metadata.csv"
    report_path = output_dir / f"{source_key}_s1_report.md"

    write_corpus_csv_atomic(canonical_path, extraction.canonical_rows)
    if source_key == "aptabase":
        write_aptabase_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)
        report_builder = build_aptabase_s1_report
    elif source_key == "utexas":
        write_utexas_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)
        report_builder = build_utexas_s1_report
    else:
        raise S1ExtractError(f"No sidecar writer for source_key={source_key!r}")

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        # Re-extract into temporary sibling files and compare bytes.
        fd_c, tmp_c_name = tempfile.mkstemp(
            prefix=f".{source_key}_extracted.",
            suffix=".csv.tmp",
            dir=str(output_dir),
        )
        os.close(fd_c)
        tmp_c = Path(tmp_c_name)
        fd_s, tmp_s_name = tempfile.mkstemp(
            prefix=f".{source_key}_sidecar.",
            suffix=".csv.tmp",
            dir=str(output_dir),
        )
        os.close(fd_s)
        tmp_s = Path(tmp_s_name)
        try:
            second = adapter(
                input_path,
                source_dataset=row.source_dataset,
                redistribution_status=row.redistribution_status,
                expected_rows=row.n_rows_expected,
            )
            write_corpus_csv_atomic(tmp_c, second.canonical_rows)
            if source_key == "aptabase":
                write_aptabase_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            else:
                write_utexas_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            deterministic_ok = (
                tmp_c.read_bytes() == canonical_path.read_bytes()
                and tmp_s.read_bytes() == sidecar_path.read_bytes()
            )
            if not deterministic_ok:
                raise S1ExtractError(
                    "S1 outputs were not byte-identical across deterministic rerun"
                )
        finally:
            if tmp_c.exists():
                tmp_c.unlink()
            if tmp_s.exists():
                tmp_s.unlink()

    run_result = S1RunResult(
        source_key=source_key,
        source_dataset=row.source_dataset,
        registered_path=row.path,
        registered_sha256=row.sha256,
        observed_sha256=hash_before,
        sha256_ok=hash_before == row.sha256,
        input_hash_before=hash_before,
        input_hash_after=hash_after,
        input_hash_unchanged=hash_before == hash_after,
        deterministic_rerun_ok=deterministic_ok,
        stats=extraction.stats,
        output_canonical=canonical_path,
        output_sidecar=sidecar_path,
        output_report=report_path,
    )

    report_text = report_builder(
        repo_root=repo_root,
        registry_row=row,
        result=run_result,
    )
    _write_text_atomic(report_path, report_text)

    # Confirm no absolute machine path leaked into report text.
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S1ExtractError(
            "S1 report must not contain absolute repository paths"
        )

    return run_result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "S1: extract a registered source into the canonical corpus schema "
            "with a complete source-metadata sidecar."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Registry source_key to extract (e.g. aptabase, utexas)",
    )
    parser.add_argument(
        "--registry-spec",
        type=Path,
        default=None,
        help="Tracked registry specification CSV (default: config/source_registry.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory beneath data/interim "
            "(default: data/interim/extracted)"
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detected)",
    )
    parser.add_argument(
        "--check-deterministic-rerun",
        action="store_true",
        help="Re-run extraction once and require byte-identical outputs",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        repo_root = (
            args.repo_root.resolve()
            if args.repo_root is not None
            else find_repo_root(Path(__file__).resolve())
        )
        if not repo_root.is_dir():
            raise S1ExtractError(f"Repository root does not exist: {repo_root}")

        registry_spec = (
            args.registry_spec
            if args.registry_spec is not None
            else Path("config/source_registry.csv")
        )
        output_dir = (
            args.output_dir
            if args.output_dir is not None
            else Path("data/interim/extracted")
        )

        result = run_s1_extraction(
            repo_root=repo_root,
            source_key=args.source,
            registry_spec=registry_spec,
            output_dir=output_dir,
            check_deterministic_rerun=args.check_deterministic_rerun,
        )
    except (
        S1ExtractError,
        RegistryError,
        AptaBaseAdapterError,
        UTexasAdapterError,
        CorpusSchemaError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    stats = result.stats
    # Aggregate counts only — never print sequence values.
    print(
        f"source={result.source_key}\n"
        f"input_rows={stats.input_rows}\n"
        f"canonical_rows={stats.canonical_rows}\n"
        f"sidecar_rows={stats.sidecar_rows}\n"
        f"nonempty_sequences={stats.nonempty_sequences}\n"
        f"missing_sequences={stats.missing_sequences}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

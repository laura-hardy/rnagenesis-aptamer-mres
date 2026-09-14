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
from typing import Any, Callable, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from adapters.aptabase import (  # noqa: E402
    AptaBaseAdapterError,
    AptaBaseExtractionResult,
    extract_aptabase,
    write_sidecar_csv_atomic as write_aptabase_sidecar_csv_atomic,
)
from adapters.aptadiff import (  # noqa: E402
    APTADIFF_SOURCE_KEYS,
    FORBIDDEN_APTADIFF_BASENAMES,
    AptaDiffAdapterError,
    AptaDiffExtractionResult,
    extract_aptadiff_a,
    extract_aptadiff_b,
    required_basename_for_source,
    write_sidecar_csv_atomic as write_aptadiff_sidecar_csv_atomic,
)
from adapters.aptamerbase import (  # noqa: E402
    AptamerBaseAdapterError,
    AptamerBaseExtractionResult,
    extract_aptamerbase,
    write_sidecar_csv_atomic as write_aptamerbase_sidecar_csv_atomic,
)
from adapters.aptadb import (  # noqa: E402
    AptaDBAdapterError,
    extract_aptadb,
    write_sidecar_csv_atomic as write_aptadb_sidecar_csv_atomic,
    write_unlinked_csv_atomic as write_aptadb_unlinked_csv_atomic,
)
from adapters.aptaindex import (  # noqa: E402
    AptaIndexAdapterError,
    AptaIndexExtractionResult,
    extract_aptaindex,
    write_canonical_csv_atomic as write_aptaindex_canonical_csv_atomic,
    write_sidecar_csv_atomic as write_aptaindex_sidecar_csv_atomic,
)
from adapters.ena import (  # noqa: E402
    EnaAdapterError,
    EnaExtractionResult,
    extract_ena,
    write_sidecar_csv_atomic as write_ena_sidecar_csv_atomic,
)
from adapters.ncbi_nuc import (  # noqa: E402
    NcbiNucAdapterError,
    NcbiNucRegisteredInput,
    extract_ncbi_nuc,
    write_sidecar_csv_atomic as write_ncbi_nuc_sidecar_csv_atomic,
)
from adapters.riboaptamer import (  # noqa: E402
    RiboAptamerAdapterError,
    RiboAptamerExtractionResult,
    extract_riboaptamer,
    write_sidecar_csv_atomic as write_riboaptamer_sidecar_csv_atomic,
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
    rows_for_source_key,
    sha256_file,
    validate_registered_file,
)

APTADB_ROLE_BY_BASENAME = {
    "interaction.csv": "interaction",
    "aptamer.csv": "aptamer",
    "protein.csv": "protein",
}

APTAMERBASE_ROLE_BY_BASENAME = {
    "aptamerbase_aptamers.csv": "spine",
    "aptamerbase.freebase.extract.nt.gz": "supporting_rdf",
}

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
FORBIDDEN_RIBOAPTAMER_TRUNCATED_BASENAMES = frozenset(
    {
        "rna_aptamer_seqs.csv",
        "rna_aptamer_seqs.xlsx",
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
    output_unlinked: Path | None = None
    registered_paths: tuple[str, ...] = ()


AdapterFn = Callable[
    ...,
    AptaBaseExtractionResult
    | AptamerBaseExtractionResult
    | AptaDiffExtractionResult
    | UTexasExtractionResult
    | RiboAptamerExtractionResult
    | AptaIndexExtractionResult
    | EnaExtractionResult,
]


def _get_adapter(source_key: str) -> AdapterFn:
    if source_key == "aptabase":
        return extract_aptabase
    if source_key == "aptamerbase":
        return extract_aptamerbase
    if source_key == "utexas":
        return extract_utexas
    if source_key == "riboaptamer":
        return extract_riboaptamer
    if source_key == "aptaindex":
        return extract_aptaindex
    if source_key == "ena":
        return extract_ena
    if source_key == "aptadiff_a":
        return extract_aptadiff_a
    if source_key == "aptadiff_b":
        return extract_aptadiff_b
    raise S1ExtractError(f"Unknown S1 adapter for source_key={source_key!r}")


def _resolve_source_rows(
    rows: Sequence[RegistrySpecRow],
    source_key: str,
) -> list[RegistrySpecRow]:
    matches = rows_for_source_key(rows, source_key)
    if not matches:
        available = ", ".join(sorted({r.source_key for r in rows})) or "(none)"
        raise S1ExtractError(
            f"Source key {source_key!r} is not present in the registry "
            f"specification; available: {available}"
        )
    datasets = {row.source_dataset for row in matches}
    if len(datasets) != 1:
        raise S1ExtractError(
            f"Source key {source_key!r} has inconsistent source_dataset "
            f"values: {sorted(datasets)}"
        )
    return matches


def _resolve_single_source_row(
    rows: Sequence[RegistrySpecRow],
    source_key: str,
) -> RegistrySpecRow:
    matches = _resolve_source_rows(rows, source_key)
    if len(matches) != 1:
        raise S1ExtractError(
            f"Source key {source_key!r} expects a single registered path; "
            f"got {len(matches)}"
        )
    return matches[0]


def _resolve_aptadb_roles(
    rows: Sequence[RegistrySpecRow],
) -> dict[str, RegistrySpecRow]:
    matches = _resolve_source_rows(rows, "aptadb")
    by_role: dict[str, RegistrySpecRow] = {}
    for row in matches:
        basename = Path(row.path).name.lower()
        role = APTADB_ROLE_BY_BASENAME.get(basename)
        if role is None:
            raise S1ExtractError(
                f"Unrecognised AptaDB registered basename {Path(row.path).name!r}; "
                "expected interaction.csv, aptamer.csv, or protein.csv"
            )
        if role in by_role:
            raise S1ExtractError(
                f"Duplicate AptaDB registered role {role!r}"
            )
        by_role[role] = row
    missing = {"interaction", "aptamer", "protein"} - set(by_role)
    if missing:
        raise S1ExtractError(
            f"AptaDB registry is missing required file role(s): "
            f"{sorted(missing)}"
        )
    if len(matches) != 3:
        raise S1ExtractError(
            f"AptaDB expects exactly three registered paths; got {len(matches)}"
        )
    return by_role


def _resolve_aptamerbase_roles(
    rows: Sequence[RegistrySpecRow],
) -> dict[str, RegistrySpecRow]:
    """Resolve AptamerBase files by basename: CSV spine vs supporting RDF."""
    matches = _resolve_source_rows(rows, "aptamerbase")
    by_role: dict[str, RegistrySpecRow] = {}
    for row in matches:
        basename = Path(row.path).name.lower()
        role = APTAMERBASE_ROLE_BY_BASENAME.get(basename)
        if role is None:
            raise S1ExtractError(
                f"Unrecognised AptamerBase registered basename "
                f"{Path(row.path).name!r}; expected aptamerbase_aptamers.csv "
                "or aptamerbase.freebase.extract.nt.gz"
            )
        if role in by_role:
            raise S1ExtractError(
                f"Duplicate AptamerBase registered role {role!r}"
            )
        by_role[role] = row
    if "spine" not in by_role:
        raise S1ExtractError(
            "AptamerBase registry is missing the CSV row spine "
            "(aptamerbase_aptamers.csv)"
        )
    return by_role


def _assert_not_forbidden_companion(relative_path: str) -> None:
    lower = relative_path.replace("\\", "/").lower()
    name_lower = Path(lower).name
    if name_lower in FORBIDDEN_RIBOAPTAMER_TRUNCATED_BASENAMES:
        raise S1ExtractError(
            "Forbidden superseded truncated RiboAptamer export cannot be "
            f"used as S1 input: {relative_path}"
        )
    if name_lower in FORBIDDEN_COMPANION_BASENAMES:
        raise S1ExtractError(
            f"Forbidden AptaBase companion cannot be used as S1 input: "
            f"{relative_path}"
        )
    if name_lower in FORBIDDEN_APTADIFF_BASENAMES:
        raise S1ExtractError(
            "Forbidden AptaDiff companion cannot be used as S1 input: "
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


def build_aptamerbase_s1_report(
    *,
    repo_root: Path,
    registry_row: RegistrySpecRow,
    result: S1RunResult,
) -> str:
    """Build an aggregate-only Markdown AptamerBase S1 report (no sequences)."""
    stats = result.stats
    lines = [
        "# AptamerBase S1 extraction report",
        "",
        "## SOURCE",
        "",
        f"- source_key: `{result.source_key}`",
        f"- source_dataset: `{registry_row.source_dataset}`",
        f"- path: `{registry_row.path}`",
        f"- SHA-256: `{registry_row.sha256}`",
        f"- Observed SHA-256: `{result.observed_sha256}`",
        f"- SHA-256 agreement: `{'pass' if result.sha256_ok else 'fail'}`",
        f"- registered rows: `{registry_row.n_rows_expected}`",
        f"- redistribution_status: `{registry_row.redistribution_status}`",
        "",
        "## RECONCILIATION",
        "",
        f"- rows in: `{stats.input_rows}`",
        f"- canonical rows: `{stats.canonical_rows}`",
        f"- sidecar rows: `{stats.sidecar_rows}`",
        f"- unique record_id: `{stats.unique_record_ids}`",
        f"- unique native_id: `{stats.unique_native_ids}`",
        f"- first native ID: `{stats.first_native_id}`",
        f"- last native ID: `{stats.last_native_id}`",
        f"- source order preserved: "
        f"`{'pass' if stats.order_preserved else 'fail'}`",
        f"- exact sequence_raw copy: "
        f"`{'pass' if stats.sequence_exact_copy_ok else 'fail'}`",
        "- S1 records filtered, rejected, or parked: `0`",
        "",
        "## Native-ID strategy",
        "",
        f"- Strategy: `{stats.native_id_strategy}`",
        "- Source Freebase `id` is preserved only in the sidecar; it is not",
        "  used as `native_id` because it is duplicated across physical rows.",
        f"- Unique Freebase IDs: `{stats.unique_freebase_ids}`",
        f"- Duplicated Freebase ID groups: `{stats.duplicate_freebase_id_groups}`",
        f"- Rows involved in duplicated Freebase ID groups: "
        f"`{stats.rows_in_duplicate_freebase_id_groups}`",
        "",
        "## SOURCE GRAIN",
        "",
        "- This is a flattened Freebase/RDF-style export. One physical CSV",
        "  row is not necessarily one biological aptamer.",
        "- S1 retains every physical row. No row consolidation occurred.",
        f"- Exact duplicate complete-row groups: "
        f"`{stats.exact_duplicate_complete_row_groups}`",
        f"- Rows in those groups: "
        f"`{stats.rows_in_exact_duplicate_complete_row_groups}`",
        f"- Excess complete-row duplicates: "
        f"`{stats.exact_duplicate_complete_row_excess}`",
        "- Duplicate complete rows, repeated Freebase IDs, repeated",
        "  sequences, parent/minimal-aptamer expansions, structure-topic",
        "  rows, blank sequences, and textual `n/a` sequences are retained.",
        "- This is not an S1 defect.",
        "",
        "## Source type (sidecar diagnostics only; not eligibility)",
        "",
    ]
    for name, count in stats.type_counts.items():
        label = name if name != "" else "<blank>"
        lines.append(f"- `{label}`: `{count}`")
    lines.extend(
        [
            "",
            "## SEQUENCE RAW STATUS",
            "",
            f"- empty `sequence` (empty string): `{stats.empty_sequences}`",
            f"- exact textual `n/a`: `{stats.sequence_na_text}`",
            f"- other nonempty: `{stats.other_nonempty_sequences}`",
            "- Textual `n/a` is preserved verbatim and is not treated as",
            "  missing. Alphabet is not classified at S1.",
            "",
            "## TARGET",
            "",
            f"- target_name_raw populated: `{stats.nonempty_targets}`",
            "- Source `label` is a composite Freebase export label, not a",
            "  documented raw-target column. It is preserved sidecar-only",
            "  pending later target extraction.",
            "",
            "## Publication / grouping fields",
            "",
            f"- nonempty publication: `{stats.nonempty_publication}`",
            f"- nonempty DOI: `{stats.nonempty_doi}`",
            f"- nonempty PMID: `{stats.nonempty_pmid}`",
            "- accession, experiment_group_id, and",
            "  near_duplicate_family_id remain empty.",
            "",
            "## SOURCE METADATA",
            "",
            f"- Sidecar rows: `{stats.sidecar_rows}`",
            "- Sidecar retains the CSV data-row number, native_id, and all",
            "  14 original AptamerBase columns, including type, Freebase id,",
            "  label, sequence, sequence_length, and the relationship /",
            "  structure / evidence / application / modification fields.",
            f"- has_mutational_analysis true/false/blank: "
            f"`{stats.has_mutational_analysis_true}` / "
            f"`{stats.has_mutational_analysis_false}` / "
            f"`{stats.has_mutational_analysis_blank}`",
            f"- has_experimentally_determined_structure true/false/blank: "
            f"`{stats.has_experimentally_determined_structure_true}` / "
            f"`{stats.has_experimentally_determined_structure_false}` / "
            f"`{stats.has_experimentally_determined_structure_blank}`",
            f"- nonempty has_minimal_aptamer (relationship URI, not a",
            f"  canonical cluster field): `{stats.has_minimal_aptamer_nonempty}`",
            f"- nonempty is_minimal_aptamer_of: "
            f"`{stats.is_minimal_aptamer_of_nonempty}`",
            f"- nonempty has_application: `{stats.has_application_nonempty}`",
            f"- nonempty has_modification_details: "
            f"`{stats.has_modification_details_nonempty}`",
            f"- nonempty has_secondary_structure: "
            f"`{stats.has_secondary_structure_nonempty}`",
            f"- nonempty has_predicted_secondary_structure: "
            f"`{stats.has_predicted_secondary_structure_nonempty}`",
            f"- nonempty has_sequence_pattern: "
            f"`{stats.has_sequence_pattern_nonempty}`",
            "- Structure and evidence fields are preserved but uninterpreted.",
            "  They do not populate canonical PDB or evidence fields.",
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
            f"- No row consolidation: "
            f"`{'pass' if stats.no_row_consolidation else 'fail'}`",
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
            "## DEFERRED",
            "",
            "- molecule type unresolved",
            "- chemistry unresolved",
            "- no T→U",
            "- no sequence normalisation",
            "- no constant trimming",
            "- no target extraction/canonicalisation",
            "- no evidence scoring",
            "- no affinity normalisation",
            "- no PDB mapping",
            "- no leakage",
            "- no filtering/parking/rejection",
            "- no deduplication/clustering",
            "- no CHECKPOINT-1",
            "- no global S4",
            "",
            "## Pipeline status",
            "",
            "- AptamerBase S0 complete.",
            "- AptamerBase S1 complete.",
            "- AptamerBase S2 has not started.",
            "- No AptamerBase record is authorised for global S4.",
            "",
        ]
    )
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


def build_aptadb_s1_report(
    *,
    repo_root: Path,
    registry_rows: Mapping[str, RegistrySpecRow],
    result: S1RunResult,
) -> str:
    """Build an aggregate-only Markdown AptaDB S1 report (no sequences)."""
    stats = result.stats
    interaction = registry_rows["interaction"]
    aptamer = registry_rows["aptamer"]
    protein = registry_rows["protein"]
    lines = [
        "# AptaDB S1 extraction report",
        "",
        "## Registered source",
        "",
        "- Logical source_key: `aptadb`",
        f"- Registered source dataset: `{interaction.source_dataset}`",
        f"- Redistribution status: `{interaction.redistribution_status}`",
        f"- Interaction path: `{interaction.path}`",
        f"- Interaction SHA-256: `{interaction.sha256}`",
        f"- Interaction n_rows_expected: `{interaction.n_rows_expected}`",
        f"- Aptamer path: `{aptamer.path}`",
        f"- Aptamer SHA-256: `{aptamer.sha256}`",
        f"- Aptamer n_rows_expected: `{aptamer.n_rows_expected}`",
        f"- Protein path: `{protein.path}`",
        f"- Protein SHA-256: `{protein.sha256}`",
        f"- Protein n_rows_expected: `{protein.n_rows_expected}`",
        f"- SHA-256 agreement (all three files): "
        f"`{'pass' if result.sha256_ok else 'fail'}`",
        "",
        "## Grain and identifiers",
        "",
        "- Spine: `interaction.csv` (one canonical row per interaction)",
        f"- Native-ID strategy: `{stats.native_id_strategy}`",
        "- Duplicate `(Apta_index, TargetID)` pairs are retained as separate",
        "  interaction records because `Index` is unique.",
        "- Aptamers without interaction rows are not materialised as canonical",
        "  records. They are listed in the unlinked-aptamer reconciliation",
        "  artefact for later S3 `missing_target` rejection logging.",
        "",
        "## Row counts",
        "",
        f"- Interaction input rows: `{stats.input_rows}`",
        f"- Canonical output rows: `{stats.canonical_rows}`",
        f"- Sidecar rows: `{stats.sidecar_rows}`",
        f"- Unique native IDs: `{stats.unique_native_ids}`",
        f"- Unique canonical record IDs: `{stats.unique_record_ids}`",
        f"- Aptamer lookup rows: `{stats.aptamer_rows}`",
        f"- Protein lookup rows: `{stats.protein_rows}`",
        "",
        "## Joins and sequence agreement",
        "",
        f"- Successful Apta_index joins: `{stats.aptamer_joins}`",
        f"- Failed Apta_index joins: `{stats.failed_aptamer_joins}`",
        f"- Sequence mismatches (interaction vs aptamer Sequence): "
        f"`{stats.sequence_mismatches}`",
        f"- Canonical sequence_raw exact-copy from aptamer.csv.Sequence: "
        f"`{'pass' if stats.sequence_exact_copy_ok else 'fail'}`",
        f"- Protein interactions: `{stats.protein_interactions}`",
        f"- Successful protein TargetID joins: `{stats.protein_joins}`",
        f"- Failed protein joins: `{stats.failed_protein_joins}`",
        f"- Protein-table rows represented in interactions: "
        f"`{stats.proteins_represented}`",
        f"- Non-protein interactions: `{stats.nonprotein_interactions}`",
        "",
        "## Target chemistry (source labels; not canonical target_type)",
        "",
    ]
    for name, count in sorted(stats.target_chemistry_counts.items()):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(
        [
            "",
            "## Canonical mapping summary",
            "",
            "- `aptamer.csv.Sequence` → `sequence_raw` (verbatim; no cleaning)",
            "- `interaction.csv.Index` → `native_id`; `record_id = aptadb:{Index}`",
            "- Protein interactions: `protein.csv.Protein names` → "
            "`target_name_raw`",
            "- Molecule/Cell/Other: `target_name_raw` left empty "
            "(lookup tables not registered)",
            "- `Reference(pubmed ID)` → `pubmed_id` verbatim",
            "- `publication` is left empty (PMID is not publication text)",
            "- Apta_index and aptamer description → optional JSON `notes`",
            "",
            "## Sequence retention (verbatim; no cleaning)",
            "",
            f"- Records with nonempty sequence_raw: `{stats.nonempty_sequences}`",
            f"- Records with missing sequence_raw: `{stats.missing_sequences}`",
            f"- Records with nonempty target_name_raw: "
            f"`{stats.nonempty_target_name_raw}`",
            f"- Records with empty target_name_raw: "
            f"`{stats.empty_target_name_raw}`",
            f"- Nonempty pubmed_id: `{stats.nonempty_pmid}`",
            f"- Nonempty publication: `{stats.nonempty_publication}`",
            "",
            "## Unlinked aptamers (not in canonical output)",
            "",
            f"- Aptamer rows with no interaction: `{stats.unlinked_aptamers}`",
            "- Planned later S3 reason: `missing_target`",
            "- Chemistry breakdown:",
        ]
    )
    for name, count in sorted(stats.unlinked_chemistry_counts.items()):
        lines.append(f"  - `{name}`: `{count}`")
    unlinked_display = (
        _relative_display(result.output_unlinked, repo_root)
        if result.output_unlinked is not None
        else "(not written)"
    )
    lines.extend(
        [
            "",
            "## Source-metadata sidecar",
            "",
            f"- Sidecar rows: `{stats.sidecar_rows}`",
            "- Sidecar retains interaction, aptamer and (when joined) protein",
            "  source fields, including both Sequence columns, buffer, PMID,",
            "  UniProt/PDB metadata, join diagnostics, and the unnamed trailing",
            "  interaction field.",
            f"- Interaction rows with a nonempty unnamed trailing field: "
            f"`{stats.unnamed_trailing_nonempty}`",
            "- The nonempty trailing-field value is preserved verbatim and is",
            "  not interpreted.",
            "",
            "## Validation results",
            "",
            f"- SHA-256 agreement: `{'pass' if result.sha256_ok else 'fail'}`",
            f"- Interaction row retention "
            f"(rows_in == rows_out == {interaction.n_rows_expected}): "
            f"`{'pass' if stats.canonical_rows == interaction.n_rows_expected else 'fail'}`",
            f"- Unique native/record IDs: "
            f"`{'pass' if stats.unique_native_ids == stats.canonical_rows and stats.unique_record_ids == stats.canonical_rows else 'fail'}`",
            f"- Sequence exact-copy / zero mismatches: "
            f"`{'pass' if stats.sequence_exact_copy_ok and stats.sequence_mismatches == 0 else 'fail'}`",
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
            f"- Unlinked aptamers: `{unlinked_display}`",
            f"- Report: `{_relative_display(result.output_report, repo_root)}`",
            "",
            "## Stage boundary",
            "",
            "- S1 only: no sequence cleaning, alphabet conversion, molecule",
            "  classification, length filtering, trimming, target normalisation,",
            "  UniProt search, evidence scoring, parking, leakage, or",
            "  deduplication was performed.",
            "- Canonical `target_type`, `target_uniprot`, `pdb_id` and evidence",
            "  fields remain empty. Non-protein TargetIDs are preserved only in",
            "  the sidecar.",
            "- No S2 normalisation was started.",
            "",
            "## Pipeline status",
            "",
            "- AptaDB S1 complete.",
            "- AptaDB S2 has not started.",
            "- No AptaDB records are yet authorised for global S4.",
            "",
        ]
    )
    return "\n".join(lines)


def build_riboaptamer_s1_report(
    *,
    repo_root: Path,
    registry_row: RegistrySpecRow,
    result: S1RunResult,
) -> str:
    """Build an aggregate-only Markdown RiboAptamer S1 report (no sequences)."""
    stats = result.stats
    lines = [
        "# RiboAptamer S1 extraction report",
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
        f"- Unique canonical record IDs: `{stats.unique_record_ids}`",
        f"- First native ID: `{stats.first_native_id}`",
        f"- Last native ID: `{stats.last_native_id}`",
        f"- S1 records filtered, rejected, or parked: `0`",
        "",
        "## Native-ID strategy",
        "",
        f"- Strategy: `{stats.native_id_strategy}`",
        "- Source `Sequence Name` is preserved only in the sidecar; it is not",
        "  used as `native_id` because three identifiers are duplicated.",
        f"- Unique Sequence Name values: `{stats.unique_sequence_names}`",
        f"- Duplicate Sequence Name keys: `{stats.duplicate_sequence_name_keys}`",
        f"- Rows participating in duplicated Sequence Name keys: "
        f"`{stats.rows_in_duplicate_sequence_name_groups}`",
        "- Exact duplicate source rows remain separate S1 records.",
        "",
        "## Canonical mapping summary",
        "",
        "- `Sequence` → `sequence_raw` (verbatim; no cleaning)",
        "- 1-based CSV data-row number → `native_id` (`001`…`509`)",
        "- `record_id` = `riboaptamer:{native_id}`",
        "- No canonical target column exists; `target_name_raw` is empty",
        "- Source `Category` → optional JSON `notes` as `category_prior`",
        "- Source `Type` is a source target-class field and is sidecar-only;",
        "  it is not experimental molecule type and is not copied to",
        "  `molecule_type` or `target_type`",
        "- `PubMed Link` → `pubmed_id` only when a numeric PMID can be",
        "  extracted from an unambiguous PubMed URL; otherwise empty",
        "- `Article name` is a clone/variant label, not a publication citation",
        "- `publication` and `doi` remain empty; no DOI is invented from",
        "  non-PubMed URLs",
        "- `Affinity (Kd)` and `mmCIF Download URL` remain sidecar-only",
        "",
        "## Sequence and target retention (verbatim; no cleaning)",
        "",
        f"- Records with nonempty sequence_raw: `{stats.nonempty_sequences}`",
        f"- Records with empty sequence_raw: `{stats.missing_sequences}`",
        f"- Exact-copy validation for sequence_raw: "
        f"`{'pass' if stats.sequence_exact_copy_ok else 'fail'}`",
        f"- Records with empty target_name_raw: `{stats.empty_target_name_raw}`",
        f"- Records with nonempty target_name_raw: "
        f"`{stats.nonempty_target_name_raw}`",
        "",
        "## Publication fields",
        "",
        f"- Nonempty publication: `{stats.nonempty_publication}`",
        f"- Nonempty DOI: `{stats.nonempty_doi}`",
        f"- Nonempty PMID (unambiguous PubMed URL parse): "
        f"`{stats.nonempty_pmid}`",
        "",
        "## Source-metadata sidecar",
        "",
        f"- Sidecar rows: `{stats.sidecar_rows}`",
        "- Sidecar retains the CSV data-row number / native_id and all 13",
        "  original RiboAptamer columns, including Sequence Name, Aptamer",
        "  Name, Category, Type, Article name, Sequence, Length, GC Content,",
        "  Discovery Year, Affinity (Kd), Description, PubMed Link, and",
        "  mmCIF Download URL.",
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
        f"- Canonical target inference at S1: "
        f"`{'none' if stats.nonempty_target_name_raw == 0 else 'fail'}`",
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
        "  classification, length filtering, trimming, target extraction,",
        "  target-type classification, evidence scoring, affinity",
        "  normalisation, parking, eligibility filtering, leakage, or",
        "  deduplication was performed.",
        "- No S2 normalisation was started.",
        "",
        "## Pipeline status",
        "",
        "- RiboAptamer S1 complete.",
        "- RiboAptamer S2 has not started.",
        "- No RiboAptamer records are yet authorised for global S4.",
        "",
    ]
    return "\n".join(lines)


def build_aptadiff_s1_report(
    *,
    repo_root: Path,
    registry_row: RegistrySpecRow,
    result: S1RunResult,
) -> str:
    """Build an aggregate-only Markdown AptaDiff A/B S1 report (no sequences)."""
    stats = result.stats
    source_key = result.source_key
    dataset_label = stats.dataset_label
    lines = [
        f"# AptaDiff Dataset {dataset_label} S1 extraction report",
        "",
        "## SOURCE",
        "",
        f"- source_key: `{source_key}`",
        f"- source_dataset: `{registry_row.source_dataset}`",
        f"- path: `{registry_row.path}`",
        f"- SHA-256: `{registry_row.sha256}`",
        f"- Observed SHA-256: `{result.observed_sha256}`",
        f"- SHA-256 agreement: `{'pass' if result.sha256_ok else 'fail'}`",
        f"- registered rows: `{registry_row.n_rows_expected}`",
        f"- redistribution_status: `{registry_row.redistribution_status}`",
        f"- AptaDiff dataset: `{dataset_label}`",
        f"- documented source target (sidecar only): `{stats.documented_target}`",
        "",
        "## RECONCILIATION",
        "",
        f"- rows in: `{stats.input_rows}`",
        f"- canonical rows: `{stats.canonical_rows}`",
        f"- sidecar rows: `{stats.sidecar_rows}`",
        f"- unique record_id: `{stats.unique_record_ids}`",
        f"- unique native_id: `{stats.unique_native_ids}`",
        f"- first native ID: `{stats.first_native_id}`",
        f"- last native ID: `{stats.last_native_id}`",
        f"- source order preserved: "
        f"`{'pass' if stats.order_preserved else 'fail'}`",
        f"- exact sequence_raw copy: "
        f"`{'pass' if stats.sequence_exact_copy_ok else 'fail'}`",
        f"- exact sidecar p6 copy: "
        f"`{'pass' if stats.p6_exact_copy_ok else 'fail'}`",
        "- S1 records filtered, rejected, or parked: `0`",
        "",
        "## Native-ID strategy",
        "",
        f"- Strategy: `{stats.native_id_strategy}`",
        f"- `record_id` = `{source_key}:{{native_id}}`",
        "- Sequence is not used as `native_id`.",
        "",
        "## Canonical mapping summary",
        "",
        "- source `seq` → `sequence_raw` (verbatim; no cleaning)",
        "- source `p6` is sidecar-only and is not mapped to affinity or evidence",
        "- no canonical target column exists; `target_name_raw` is empty",
        "- documented Dataset A/B target identity is sidecar-only",
        "",
        "## SEQUENCE RAW STATUS",
        "",
        f"- nonempty sequence_raw: `{stats.nonempty_sequences}`",
        f"- missing sequence_raw: `{stats.missing_sequences}`",
        f"- unique sequences: `{stats.unique_sequences}`",
        f"- duplicate sequence groups: `{stats.duplicate_sequence_groups}`",
        f"- rows in duplicated sequence groups: "
        f"`{stats.rows_in_duplicate_sequence_groups}`",
        f"- length-36 sequences: `{stats.length_36}`",
        f"- other lengths: `{stats.other_lengths}`",
        f"- A/C/G/T-only (diagnostic, not an exclusion): `{stats.acgt_only}`",
        f"- N-containing retained (not repaired or excluded): "
        f"`{stats.n_containing}`",
        "- Alphabet is not classified at S1. N-containing rows are retained.",
        "",
        "## TARGET",
        "",
        f"- target_name_raw populated: `{stats.nonempty_target_name_raw}`",
        "- There is no per-row target column. Documented IGFBP3/PTK7",
        "  identity is preserved only in the source-metadata sidecar.",
        "- Canonical target, UniProt, target type/family/Pfam, and",
        "  evidence fields remain empty.",
        "",
        "## p6 (source field; uninterpreted)",
        "",
        f"- exact sidecar copy: "
        f"`{'pass' if stats.p6_exact_copy_ok else 'fail'}`",
        f"- all p6 tokens integer: `{stats.p6_all_integer}`",
        f"- p6 min/median/max (diagnostic only): `{stats.p6_min}` / "
        f"`{stats.p6_median}` / `{stats.p6_max}`",
        "- p6 is not treated as affinity, evidence, a binding score, or",
        "  a sampling/capping weight at S1.",
        "",
        "## SOURCE METADATA",
        "",
        f"- Sidecar rows: `{stats.sidecar_rows}`",
        "- Sidecar retains record_id, native_id, the CSV data-row",
        "  ordinal, original seq, original p6, Dataset A/B identity,",
        "  documented source target, and target provenance.",
        "- Derived x_z coordinates are not included.",
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
        f"- p6 exact-copy: "
        f"`{'pass' if stats.p6_exact_copy_ok else 'fail'}`",
        f"- No row consolidation: "
        f"`{'pass' if stats.no_row_consolidation else 'fail'}`",
        f"- Canonical target inference at S1: "
        f"`{'none' if stats.nonempty_target_name_raw == 0 else 'fail'}`",
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
        "## DEFERRED",
        "",
        "- molecule type unresolved; S1 is molecule-neutral",
        "- chemistry unresolved",
        "- no T→U",
        "- no sequence normalisation",
        "- no constant-region inference or trimming",
        "- no target canonicalisation",
        "- no evidence scoring",
        "- no affinity mapping from p6",
        "- no leakage",
        "- no filtering/parking/rejection",
        "- no capping or downsampling",
        "- no deduplication/clustering",
        "- no CHECKPOINT-1",
        "- no global S4",
        "- Dataset A x_z latent-coordinate file is not a corpus input",
        "- Dataset C/D are not companion inputs",
        "",
        "## Pipeline status",
        "",
        f"- AptaDiff Dataset {dataset_label} S0 complete.",
        f"- AptaDiff Dataset {dataset_label} S1 complete.",
        f"- AptaDiff Dataset {dataset_label} S2 has not started.",
        f"- No AptaDiff Dataset {dataset_label} record is authorised for global S4.",
        "",
    ]
    return "\n".join(lines)


def build_aptaindex_s1_report(
    *,
    repo_root: Path,
    registry_row: RegistrySpecRow,
    result: S1RunResult,
) -> str:
    """Build an aggregate-only Markdown AptaIndex S1 report (no sequences)."""
    stats = result.stats
    lines = [
        "# AptaIndex S1 extraction report",
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
        f"- Unique canonical record IDs: `{stats.unique_record_ids}`",
        f"- First native ID: `{stats.first_native_id}`",
        f"- Last native ID: `{stats.last_native_id}`",
        f"- S1 records filtered, rejected, or parked: `0`",
        "",
        "## Native-ID strategy",
        "",
        f"- Strategy: `{stats.native_id_strategy}`",
        "- Source `Title` is preserved only in the sidecar; it is not used as",
        "  `native_id` because it is duplicated across rows.",
        f"- Unique Title values: `{stats.unique_titles}`",
        f"- Duplicate Title keys: `{stats.duplicate_title_keys}`",
        f"- Rows participating in duplicated Title keys: "
        f"`{stats.rows_in_duplicate_title_groups}`",
        "- Duplicate Titles remain separate S1 records.",
        "",
        "## Canonical mapping summary",
        "",
        "- `Sequence` → `sequence_raw` (verbatim; no chemical-notation parsing)",
        "- 1-based CSV data-row number → `native_id` (`0001`…`1050`)",
        "- `record_id` = `aptaindex:{native_id}`",
        "- `Target` → `target_name_raw` (verbatim; blanks retained)",
        "- `Reference` → `publication` (verbatim mixed citation text)",
        "- `doi` and `pubmed_id` remain empty; AptaIndex has no dedicated",
        "  DOI/PMID columns and S1 does not add a citation parser",
        "- Source `Type`, `Target Type`, and affinity columns remain",
        "  sidecar-only and are not copied into canonical molecule,",
        "  chemistry, target-type, or affinity fields",
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
        f"- Nonempty publication (verbatim Reference): "
        f"`{stats.nonempty_publication}`",
        f"- Nonempty DOI: `{stats.nonempty_doi}`",
        f"- Nonempty PMID: `{stats.nonempty_pmid}`",
        "",
        "## Source Type (sidecar diagnostics only; not canonical)",
        "",
    ]
    for name, count in stats.type_counts.items():
        label = name if name != "" else "<blank>"
        lines.append(f"- `{label}`: `{count}`")
    lines.extend(
        [
            "",
            "## Source-metadata sidecar",
            "",
            f"- Sidecar rows: `{stats.sidecar_rows}`",
            "- Sidecar retains the CSV data-row number / native_id and all 14",
            "  original AptaIndex columns, including Title, Type, Target,",
            "  Affinity Type, Affinity, Affinity Units, Refolding Protocol,",
            "  Binding Conditions, Temp, Sequence, Molecular Weight,",
            "  Comments, Reference, and Target Type.",
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
            "- S1 only: no chemical-notation parsing, sequence cleaning,",
            "  alphabet conversion, molecule classification, length",
            "  filtering, trimming, target normalisation, target-type",
            "  classification, evidence scoring, affinity normalisation,",
            "  parking, eligibility filtering, leakage, or deduplication",
            "  was performed.",
            "- No S2 normalisation was started.",
            "",
            "## Pipeline status",
            "",
            "- AptaIndex S1 complete.",
            "- AptaIndex S2 has not started.",
            "- No AptaIndex records are yet authorised for global S4.",
            "",
        ]
    )
    return "\n".join(lines)


def build_ena_s1_report(
    *,
    repo_root: Path,
    registry_row: RegistrySpecRow,
    result: S1RunResult,
) -> str:
    """Build an aggregate-only Markdown ENA S1 report (no sequences)."""
    stats = result.stats
    lines = [
        "# ENA S1 extraction report",
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
        f"- Unique canonical record IDs: `{stats.unique_record_ids}`",
        f"- S1 records filtered, rejected, parked, or deduplicated: `0`",
        "",
        "## Native-ID strategy",
        "",
        f"- Strategy: `{stats.native_id_strategy}`",
        "- `native_id` is the source `review_unit_id`.",
        "- `record_id` is `ena:{review_unit_id}`.",
        "- Supporting `review_unit_ids` remain sidecar provenance and are",
        "  not used as identity and are not split.",
        "",
        "## Canonical mapping summary",
        "",
        "- Reviewed source `sequence` → `sequence_raw` (verbatim; no",
        "  uppercase, whitespace strip, T→U, or alphabet inspection)",
        "- Source `target` → `target_name_raw` (verbatim; no canonicalisation)",
        "- `publication`, `doi`, and `pubmed_id` remain empty; source",
        "  `representative_title`, `references`, `doi_values`, and",
        "  `pubmed_values` stay in the sidecar",
        "- Canonical `binding_evidence_type` / `binding_evidence_score` /",
        "  affinity fields remain empty; source evidence fields stay in",
        "  the sidecar for later global S4",
        "- Canonical `experiment_group_id` and `near_duplicate_family_id`",
        "  remain empty because those fields are forbidden at S1; primary",
        "  grouping and family provenance are sidecar-only",
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
        f"- Source sequence_corrected_applied=1 rows retained as sidecar "
        f"provenance: `{stats.sequence_corrections_applied}`",
        f"- Source target_corrected_applied=1 rows retained as sidecar "
        f"provenance: `{stats.target_corrections_applied}`",
        "",
        "## Publication / evidence fields",
        "",
        f"- Nonempty canonical publication: `{stats.nonempty_publication}`",
        f"- Nonempty canonical DOI: `{stats.nonempty_doi}`",
        f"- Nonempty canonical PMID: `{stats.nonempty_pmid}`",
        "",
        "## Experiment-group provenance (sidecar only)",
        "",
        f"- Populated primary source experiment_group_id: "
        f"`{stats.populated_primary_experiment_groups}`",
        f"- Distinct primary experiment_group_id values: "
        f"`{stats.distinct_primary_experiment_groups}`",
        "- Supporting `experiment_group_ids` are preserved separately and",
        "  are not treated as the primary grouping key.",
        f"- Consolidated source rows (consolidated_from_n_units>1) retained "
        f"unsplit: `{stats.consolidated_rows}`",
        "",
        "## Near-duplicate family provenance (sidecar only)",
        "",
        f"- Original blank source family IDs: `{stats.blank_source_family_ids}`",
        f"- Original nonblank source family IDs: "
        f"`{stats.nonblank_source_family_ids}`",
        f"- Materialised singleton family IDs: "
        f"`{stats.materialised_singleton_family_ids}`",
        f"- Unique materialised singleton family IDs: "
        f"`{stats.unique_materialised_singleton_ids}`",
        f"- Pipe-delimited consolidated source family rows retained unsplit: "
        f"`{stats.pipe_family_rows}`",
        "- Blank source family means singleton, not unknown. Effective IDs",
        "  use `ena_singleton_{review_unit_id}` with family size 1.",
        "- Original source family ID/size values are not rewritten.",
        "",
        "## Source-metadata sidecar",
        "",
        f"- Sidecar rows: `{stats.sidecar_rows}`",
        "- Sidecar retains all 37 original ENA columns verbatim plus",
        "  `record_id` and three derived family-provenance fields:",
        "  effective family ID, effective family size, and original",
        "  family-ID missingness.",
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
        "- S1 only: no T→U conversion, sequence normalisation, molecule or",
        "  chemistry classification, length filtering, trimming, target",
        "  canonicalisation, evidence scoring, parking, eligibility",
        "  filtering, leakage, clustering, balancing, or deduplication",
        "  was performed.",
        "- The 679-versus-676 processed-export difference is deferred to",
        "  ENA CHECKPOINT-1.",
        "- No S2 normalisation was started.",
        "",
        "## Pipeline status",
        "",
        "- ENA S1 complete.",
        "- ENA S2 has not started.",
        "- No ENA records are yet authorised for global S4.",
        "",
    ]
    return "\n".join(lines)


def _combined_hash_token(role_hashes: Mapping[str, str]) -> str:
    return "|".join(
        f"{role}:{role_hashes[role]}"
        for role in ("interaction", "aptamer", "protein")
    )


def _run_aptadb_s1(
    *,
    repo_root: Path,
    spec_rows: Sequence[RegistrySpecRow],
    output_dir: Path,
    check_deterministic_rerun: bool,
) -> S1RunResult:
    roles = _resolve_aptadb_roles(spec_rows)
    for row in roles.values():
        _assert_not_forbidden_companion(row.path)
        validate_registered_file(repo_root, row)

    resolved = {
        role: resolve_registered_path(repo_root, row.path)
        for role, row in roles.items()
    }
    hashes_before = {
        role: sha256_file(path) for role, path in resolved.items()
    }
    for role, row in roles.items():
        if hashes_before[role] != row.sha256:
            raise S1ExtractError(
                f"SHA-256 mismatch before adapter execution for aptadb "
                f"{role} file {row.path}"
            )

    extraction = extract_aptadb(
        interaction_path=resolved["interaction"],
        aptamer_path=resolved["aptamer"],
        protein_path=resolved["protein"],
        source_dataset=roles["interaction"].source_dataset,
        redistribution_status=roles["interaction"].redistribution_status,
        expected_interaction_rows=roles["interaction"].n_rows_expected,
        expected_aptamer_rows=roles["aptamer"].n_rows_expected,
        expected_protein_rows=roles["protein"].n_rows_expected,
    )

    hashes_after = {role: sha256_file(path) for role, path in resolved.items()}
    if hashes_after != hashes_before:
        raise S1ExtractError(
            "One or more AptaDB source inputs were modified during S1 extraction"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = output_dir / "aptadb_extracted.csv"
    sidecar_path = output_dir / "aptadb_source_metadata.csv"
    unlinked_path = output_dir / "aptadb_unlinked_aptamers.csv"
    report_path = output_dir / "aptadb_s1_report.md"

    write_corpus_csv_atomic(canonical_path, extraction.canonical_rows)
    write_aptadb_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)
    write_aptadb_unlinked_csv_atomic(unlinked_path, extraction.unlinked_rows)

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        fd_c, tmp_c_name = tempfile.mkstemp(
            prefix=".aptadb_extracted.",
            suffix=".csv.tmp",
            dir=str(output_dir),
        )
        os.close(fd_c)
        tmp_c = Path(tmp_c_name)
        fd_s, tmp_s_name = tempfile.mkstemp(
            prefix=".aptadb_sidecar.",
            suffix=".csv.tmp",
            dir=str(output_dir),
        )
        os.close(fd_s)
        tmp_s = Path(tmp_s_name)
        fd_u, tmp_u_name = tempfile.mkstemp(
            prefix=".aptadb_unlinked.",
            suffix=".csv.tmp",
            dir=str(output_dir),
        )
        os.close(fd_u)
        tmp_u = Path(tmp_u_name)
        try:
            second = extract_aptadb(
                interaction_path=resolved["interaction"],
                aptamer_path=resolved["aptamer"],
                protein_path=resolved["protein"],
                source_dataset=roles["interaction"].source_dataset,
                redistribution_status=roles["interaction"].redistribution_status,
                expected_interaction_rows=roles["interaction"].n_rows_expected,
                expected_aptamer_rows=roles["aptamer"].n_rows_expected,
                expected_protein_rows=roles["protein"].n_rows_expected,
            )
            write_corpus_csv_atomic(tmp_c, second.canonical_rows)
            write_aptadb_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            write_aptadb_unlinked_csv_atomic(tmp_u, second.unlinked_rows)
            deterministic_ok = (
                tmp_c.read_bytes() == canonical_path.read_bytes()
                and tmp_s.read_bytes() == sidecar_path.read_bytes()
                and tmp_u.read_bytes() == unlinked_path.read_bytes()
            )
            if not deterministic_ok:
                raise S1ExtractError(
                    "S1 outputs were not byte-identical across deterministic rerun"
                )
        finally:
            for tmp in (tmp_c, tmp_s, tmp_u):
                if tmp.exists():
                    tmp.unlink()

    hash_before_token = _combined_hash_token(hashes_before)
    hash_after_token = _combined_hash_token(hashes_after)
    spine = roles["interaction"]
    run_result = S1RunResult(
        source_key="aptadb",
        source_dataset=spine.source_dataset,
        registered_path=spine.path,
        registered_sha256=spine.sha256,
        observed_sha256=hashes_before["interaction"],
        sha256_ok=all(
            hashes_before[role] == row.sha256 for role, row in roles.items()
        ),
        input_hash_before=hash_before_token,
        input_hash_after=hash_after_token,
        input_hash_unchanged=hashes_before == hashes_after,
        deterministic_rerun_ok=deterministic_ok,
        stats=extraction.stats,
        output_canonical=canonical_path,
        output_sidecar=sidecar_path,
        output_report=report_path,
        output_unlinked=unlinked_path,
        registered_paths=tuple(roles[role].path for role in ("interaction", "aptamer", "protein")),
    )
    report_text = build_aptadb_s1_report(
        repo_root=repo_root,
        registry_rows=roles,
        result=run_result,
    )
    _write_text_atomic(report_path, report_text)
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S1ExtractError(
            "S1 report must not contain absolute repository paths"
        )
    return run_result


def _ncbi_nuc_hash_token(
    rows: Sequence[RegistrySpecRow],
    hashes: Mapping[str, str],
) -> str:
    return "|".join(f"{row.path}:{hashes[row.path]}" for row in rows)


def build_ncbi_nuc_s1_report(
    *,
    repo_root: Path,
    registry_rows: Sequence[RegistrySpecRow],
    result: S1RunResult,
) -> str:
    """Build an aggregate-only Markdown NCBI Nucleotide S1 report."""
    stats = result.stats
    pmid_ids = ", ".join(f"`{item}`" for item in stats.pmid_native_ids) or "(none)"
    lines = [
        "# NCBI Nucleotide S1 extraction report",
        "",
        "## Registered source",
        "",
        "- Logical source_key: `ncbi_nuc`",
        f"- source_dataset: `{result.source_dataset}`",
        f"- Registered GenBank files: `{len(registry_rows)}`",
        f"- Redistribution status: `{registry_rows[0].redistribution_status}`",
        f"- snapshot_date `{registry_rows[0].snapshot_date}` is a local",
        "  source-snapshot/download-date proxy for this logical source,",
        "  not an NCBI database release date.",
        "- Filenames are opaque local downloads and are not biological IDs.",
        "- Registry order is the processing order (not filesystem glob order).",
        "",
        "## Registered files",
        "",
    ]
    for row in registry_rows:
        lines.append(
            f"- `{row.path}` SHA-256 `{row.sha256}` "
            f"n_rows_expected=`{row.n_rows_expected}`"
        )
    lines.extend(
        [
            "",
            "## SHA-256 agreement",
            "",
            f"- Combined observed SHA-256 token: `{result.observed_sha256}`",
            f"- SHA-256 agreement: `{'pass' if result.sha256_ok else 'fail'}`",
            "",
            "## RECONCILIATION",
            "",
            f"- files in: `{stats.input_files}`",
            f"- parsed GenBank records in: `{stats.input_rows}`",
            f"- canonical rows: `{stats.canonical_rows}`",
            f"- sidecar rows: `{stats.sidecar_rows}`",
            f"- unique record_id: `{stats.unique_record_ids}`",
            f"- unique native_id: `{stats.unique_native_ids}`",
            f"- first native ID: `{stats.first_native_id}`",
            f"- last native ID: `{stats.last_native_id}`",
            f"- source order preserved: "
            f"`{'pass' if stats.order_preserved else 'fail'}`",
            f"- ORIGIN exact-copy into sequence_raw: "
            f"`{'pass' if stats.sequence_exact_copy_ok else 'fail'}`",
            f"- ORIGIN length agrees with LOCUS length: "
            f"`{stats.origin_length_matches_locus}`",
            "- S1 records filtered, rejected, or parked: `0`",
            "",
            "## Native-ID strategy",
            "",
            f"- Strategy: `{stats.native_id_strategy}`",
            "- `record_id` = `ncbi_nuc:{ACCESSION}`",
            "- LOCUS and VERSION are sidecar provenance only.",
            "- Opaque local filenames are sidecar provenance only.",
            "",
            "## Canonical mapping summary",
            "",
            "- ORIGIN residue letters → `sequence_raw` after removing only",
            "  GenBank display line numbers, grouping spaces, and line breaks",
            "- Deposited letter case is preserved; Biopython `str(record.seq)`",
            "  is not used as `sequence_raw` because it uppercases",
            "- No T→U, no U→T, no IUPAC/N removal, no trimming",
            "- `target_name_raw` is empty; DEFINITION/COMMENT/reference titles",
            "  remain sidecar context for later target resolution",
            "- Canonical `accession` remains empty under the live S1 stage guard",
            "- Canonical `publication` remains empty because records mix",
            "  article, patent, and direct-submission references",
            "- Canonical `doi` is empty unless a structured GenBank DOI exists",
            "- Canonical `pubmed_id` is populated only when exactly one",
            "  unambiguous structured PUBMED value exists",
            "",
            "## SEQUENCE RAW STATUS",
            "",
            f"- nonempty sequence_raw: `{stats.nonempty_sequences}`",
            f"- missing sequence_raw: `{stats.missing_sequences}`",
            "- Alphabet/molecule/chemistry are not classified at S1.",
            "",
            "## TARGET",
            "",
            f"- target_name_raw populated: `{stats.nonempty_target_name_raw}`",
            f"- target_name_raw empty: `{stats.empty_target_name_raw}`",
            "- No record was split into multiple (sequence, target) rows.",
            "",
            "## Publication fields",
            "",
            f"- nonempty canonical publication: `{stats.nonempty_publication}`",
            f"- nonempty canonical DOI: `{stats.nonempty_doi}`",
            f"- nonempty canonical PMID: `{stats.nonempty_pmid}`",
            f"- ACCESSIONS with exactly one structured PMID: {pmid_ids}",
            "",
            "## SOURCE METADATA",
            "",
            f"- Sidecar rows: `{stats.sidecar_rows}`",
            "- Sidecar retains registered path, basename, file SHA-256,",
            "  LOCUS fields, ACCESSION, VERSION, GI, DEFINITION, COMMENT,",
            "  keywords, source organism, source /mol_type, FEATURES,",
            "  complete REFERENCES, dbxrefs, ORIGIN length, and ORIGIN",
            "  residues.",
            "",
            "## Validation results",
            "",
            f"- SHA-256 agreement: `{'pass' if result.sha256_ok else 'fail'}`",
            f"- Record retention (records_in == rows_out == "
            f"{stats.input_rows}): "
            f"`{'pass' if stats.canonical_rows == stats.input_rows else 'fail'}`",
            f"- Unique native/record IDs: "
            f"`{'pass' if stats.unique_native_ids == stats.canonical_rows and stats.unique_record_ids == stats.canonical_rows else 'fail'}`",
            f"- Sequence exact-copy: "
            f"`{'pass' if stats.sequence_exact_copy_ok else 'fail'}`",
            f"- Canonical target inference at S1: "
            f"`{'none' if stats.nonempty_target_name_raw == 0 else 'fail'}`",
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
            "## DEFERRED",
            "",
            "- molecule identity not assigned",
            "- chemistry not assigned",
            "- no T→U",
            "- no sequence normalisation or trimming",
            "- aptamer/non-aptamer status not adjudicated",
            "- construct/core not adjudicated",
            "- no record rejected or parked",
            "- no target canonicalisation",
            "- no UniProt/Pfam/family assignment",
            "- no evidence score or E1–E5",
            "- no affinity normalisation",
            "- no leakage exclusion",
            "- NO NCBI↔ENA DEDUPLICATION",
            "- no within-NCBI deduplication, clustering, balancing, or partition",
            "- no CHECKPOINT-1",
            "- no global S4",
            "",
            "## Pipeline status",
            "",
            "- NCBI Nucleotide S0 complete.",
            "- NCBI Nucleotide S1 complete.",
            "- NCBI Nucleotide S2 has not started.",
            "- No NCBI Nucleotide record is authorised for global S4.",
            "",
        ]
    )
    return "\n".join(lines)


def _run_ncbi_nuc_s1(
    *,
    repo_root: Path,
    spec_rows: Sequence[RegistrySpecRow],
    output_dir: Path,
    check_deterministic_rerun: bool,
) -> S1RunResult:
    matches = _resolve_source_rows(spec_rows, "ncbi_nuc")
    for row in matches:
        _assert_not_forbidden_companion(row.path)
        suffix = Path(row.path).suffix.lower()
        if suffix not in {".gb", ".gbk", ".genbank"}:
            raise S1ExtractError(
                f"ncbi_nuc registered path must be a GenBank flatfile; "
                f"got {row.path}"
            )
        validate_registered_file(repo_root, row)

    resolved = {
        row.path: resolve_registered_path(repo_root, row.path) for row in matches
    }
    hashes_before = {
        row.path: sha256_file(resolved[row.path]) for row in matches
    }
    for row in matches:
        if hashes_before[row.path] != row.sha256:
            raise S1ExtractError(
                f"SHA-256 mismatch before adapter execution for ncbi_nuc "
                f"file {row.path}"
            )

    registered_inputs = [
        NcbiNucRegisteredInput(
            path=resolved[row.path],
            relative_path=row.path,
            sha256=row.sha256,
            n_rows_expected=row.n_rows_expected,
        )
        for row in matches
    ]
    expected_records = sum(row.n_rows_expected for row in matches)
    extraction = extract_ncbi_nuc(
        registered_inputs,
        source_dataset=matches[0].source_dataset,
        redistribution_status=matches[0].redistribution_status,
        expected_records=expected_records,
    )

    hashes_after = {
        row.path: sha256_file(resolved[row.path]) for row in matches
    }
    if hashes_after != hashes_before:
        raise S1ExtractError(
            "Source input was modified during S1 extraction of ncbi_nuc"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = output_dir / "ncbi_nuc_extracted.csv"
    sidecar_path = output_dir / "ncbi_nuc_source_metadata.csv"
    report_path = output_dir / "ncbi_nuc_s1_report.md"
    write_corpus_csv_atomic(canonical_path, extraction.canonical_rows)
    write_ncbi_nuc_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)

    deterministic_ok: bool | None = None
    if check_deterministic_rerun:
        fd_c, tmp_c_name = tempfile.mkstemp(
            prefix=".ncbi_nuc_extracted.",
            suffix=".csv.tmp",
            dir=str(output_dir),
        )
        os.close(fd_c)
        tmp_c = Path(tmp_c_name)
        fd_s, tmp_s_name = tempfile.mkstemp(
            prefix=".ncbi_nuc_sidecar.",
            suffix=".csv.tmp",
            dir=str(output_dir),
        )
        os.close(fd_s)
        tmp_s = Path(tmp_s_name)
        try:
            second = extract_ncbi_nuc(
                registered_inputs,
                source_dataset=matches[0].source_dataset,
                redistribution_status=matches[0].redistribution_status,
                expected_records=expected_records,
            )
            write_corpus_csv_atomic(tmp_c, second.canonical_rows)
            write_ncbi_nuc_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            deterministic_ok = (
                tmp_c.read_bytes() == canonical_path.read_bytes()
                and tmp_s.read_bytes() == sidecar_path.read_bytes()
            )
            if not deterministic_ok:
                raise S1ExtractError(
                    "S1 outputs were not byte-identical across deterministic rerun"
                )
        finally:
            for tmp in (tmp_c, tmp_s):
                if tmp.exists():
                    tmp.unlink()

    hash_before_token = _ncbi_nuc_hash_token(matches, hashes_before)
    hash_after_token = _ncbi_nuc_hash_token(matches, hashes_after)
    run_result = S1RunResult(
        source_key="ncbi_nuc",
        source_dataset=matches[0].source_dataset,
        registered_path=matches[0].path,
        registered_sha256=matches[0].sha256,
        observed_sha256=hash_before_token,
        sha256_ok=all(
            hashes_before[row.path] == row.sha256 for row in matches
        ),
        input_hash_before=hash_before_token,
        input_hash_after=hash_after_token,
        input_hash_unchanged=hashes_before == hashes_after,
        deterministic_rerun_ok=deterministic_ok,
        stats=extraction.stats,
        output_canonical=canonical_path,
        output_sidecar=sidecar_path,
        output_report=report_path,
        registered_paths=tuple(row.path for row in matches),
    )
    report_text = build_ncbi_nuc_s1_report(
        repo_root=repo_root,
        registry_rows=matches,
        result=run_result,
    )
    _write_text_atomic(report_path, report_text)
    abs_root = str(repo_root.resolve())
    if abs_root in report_text:
        raise S1ExtractError(
            "S1 report must not contain absolute repository paths"
        )
    return run_result


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
    if source_key == "aptadb":
        return _run_aptadb_s1(
            repo_root=repo_root,
            spec_rows=spec_rows,
            output_dir=output_dir,
            check_deterministic_rerun=check_deterministic_rerun,
        )
    if source_key == "ncbi_nuc":
        return _run_ncbi_nuc_s1(
            repo_root=repo_root,
            spec_rows=spec_rows,
            output_dir=output_dir,
            check_deterministic_rerun=check_deterministic_rerun,
        )

    if source_key == "aptamerbase":
        aptamerbase_roles = _resolve_aptamerbase_roles(spec_rows)
        row = aptamerbase_roles["spine"]
        registered_paths = tuple(
            item.path for item in _resolve_source_rows(spec_rows, source_key)
        )
    else:
        row = _resolve_single_source_row(spec_rows, source_key)
        registered_paths = (row.path,)
    _assert_not_forbidden_companion(row.path)
    if source_key in APTADIFF_SOURCE_KEYS:
        required = required_basename_for_source(source_key)
        actual = Path(row.path).name
        if actual.lower() != required.lower():
            raise S1ExtractError(
                f"{source_key} S1 input must be {required}; got {row.path}"
            )

    adapter = _get_adapter(source_key)

    # Validate hash and row count before adapter execution.
    validate_registered_file(repo_root, row)
    input_path = resolve_registered_path(repo_root, row.path)
    hash_before = sha256_file(input_path)
    if hash_before != row.sha256:
        raise S1ExtractError(
            f"SHA-256 mismatch before adapter execution for {source_key!r}"
        )

    if source_key in {
        "aptabase",
        "aptamerbase",
        "utexas",
        "riboaptamer",
        "aptaindex",
        "ena",
        "aptadiff_a",
        "aptadiff_b",
    }:
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

    if source_key == "aptaindex":
        write_aptaindex_canonical_csv_atomic(canonical_path, extraction.canonical_rows)
    else:
        write_corpus_csv_atomic(canonical_path, extraction.canonical_rows)
    if source_key == "aptabase":
        write_aptabase_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)
        report_builder = build_aptabase_s1_report
    elif source_key == "aptamerbase":
        write_aptamerbase_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)
        report_builder = build_aptamerbase_s1_report
    elif source_key == "utexas":
        write_utexas_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)
        report_builder = build_utexas_s1_report
    elif source_key == "riboaptamer":
        write_riboaptamer_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)
        report_builder = build_riboaptamer_s1_report
    elif source_key == "aptaindex":
        write_aptaindex_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)
        report_builder = build_aptaindex_s1_report
    elif source_key == "ena":
        write_ena_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)
        report_builder = build_ena_s1_report
    elif source_key in APTADIFF_SOURCE_KEYS:
        write_aptadiff_sidecar_csv_atomic(sidecar_path, extraction.sidecar_rows)
        report_builder = build_aptadiff_s1_report
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
            if source_key == "aptaindex":
                write_aptaindex_canonical_csv_atomic(tmp_c, second.canonical_rows)
            else:
                write_corpus_csv_atomic(tmp_c, second.canonical_rows)
            if source_key == "aptabase":
                write_aptabase_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            elif source_key == "aptamerbase":
                write_aptamerbase_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            elif source_key == "utexas":
                write_utexas_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            elif source_key == "aptaindex":
                write_aptaindex_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            elif source_key == "ena":
                write_ena_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            elif source_key == "riboaptamer":
                write_riboaptamer_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            elif source_key in APTADIFF_SOURCE_KEYS:
                write_aptadiff_sidecar_csv_atomic(tmp_s, second.sidecar_rows)
            else:
                raise S1ExtractError(
                    f"No sidecar writer for source_key={source_key!r}"
                )
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
        registered_paths=registered_paths,
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
        help="Registry source_key to extract (e.g. aptabase, aptamerbase, utexas, aptadb, riboaptamer, aptaindex, ena, aptadiff_a, aptadiff_b, ncbi_nuc)",
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
        AptamerBaseAdapterError,
        AptaDiffAdapterError,
        AptaDBAdapterError,
        AptaIndexAdapterError,
        EnaAdapterError,
        NcbiNucAdapterError,
        RiboAptamerAdapterError,
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
